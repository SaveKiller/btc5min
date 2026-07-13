from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine

from fastapi import WebSocket

from protocol import ws_pong, ws_session, ws_state, ws_tick
from protocol import SessionPayload, StatePayload, TickPayload, StreamMode


class StreamHub:
    """Broadcast tick/state verso tutte le connessioni WS della dashboard."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        raw = json.dumps(message)
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def handle_client_message(self, ws: WebSocket, raw: str) -> None:
        msg = json.loads(raw)
        if msg.get("type") == "ping":
            await ws.send_text(json.dumps(ws_pong()))


class StreamSession:
    """Sessione unica replay/live — emette 1 tick/sec in play, seek solo in replay."""

    def __init__(self, hub: StreamHub, stall_reconnect_sec: float) -> None:
        self.hub = hub
        self.stall_reconnect_sec = stall_reconnect_sec
        self.mode: StreamMode | None = None
        self.header = None
        self.ticks_by_sec: dict[int, dict] = {}
        self.sec = 300
        self.playing = False
        self.seq = 0
        self._play_task: asyncio.Task | None = None
        self._tick_source: Callable[[int], Coroutine[Any, Any, dict | None]] | None = None

    def snapshot(self) -> SessionPayload:
        if self.mode is None or self.header is None:
            raise Exception("no active session")
        return SessionPayload(
            mode=self.mode,
            market_start_ts=self.header.market_start_ts,
            market_end_ts=self.header.market_end_ts,
            ptb_chainlink=self.header.ptb_chainlink,
            outcome=self.header.outcome,
            playing=self.playing,
            sec=self.sec,
        )

    async def start_replay(self, header, ticks_by_sec: dict[int, dict], start_sec: int = 300) -> None:
        await self.stop()
        self.mode = "replay"
        self.header = header
        self.ticks_by_sec = ticks_by_sec
        self.sec = start_sec
        self.playing = False
        self.seq = 0
        self._tick_source = self._replay_tick
        await self.hub.broadcast(ws_session(self.snapshot()))

    async def start_live(self) -> None:
        raise Exception("live mode not wired yet — connect collector feeds in next phase")

    async def seek(self, sec: int) -> None:
        if self.mode != "replay":
            raise Exception("seek only allowed in replay mode")
        if sec < 1 or sec > 300:
            raise Exception(f"sec out of range 1..300: {sec}")
        await self.pause()
        self.sec = sec
        await self.hub.broadcast(ws_state(StatePayload(playing=False, sec=self.sec, reason="seek")))
        tick = await self._emit_tick_for_sec(self.sec)
        if tick:
            await self.hub.broadcast(ws_tick(tick))

    async def play(self) -> None:
        if self.mode is None:
            raise Exception("no active session")
        if self.playing:
            return
        self.playing = True
        await self.hub.broadcast(ws_state(StatePayload(playing=True, sec=self.sec, reason="play")))
        self._play_task = asyncio.create_task(self._play_loop())

    async def pause(self) -> None:
        if not self.playing:
            return
        self.playing = False
        if self._play_task:
            self._play_task.cancel()
            try:
                await self._play_task
            except asyncio.CancelledError:
                pass
            self._play_task = None
        await self.hub.broadcast(ws_state(StatePayload(playing=False, sec=self.sec, reason="pause")))

    async def stop(self) -> None:
        await self.pause()
        if self.mode is not None:
            await self.hub.broadcast(ws_state(StatePayload(playing=False, sec=self.sec, reason="stop")))
        self.mode = None
        self.header = None
        self.ticks_by_sec = {}
        self._tick_source = None

    async def _replay_tick(self, sec: int) -> dict | None:
        return self.ticks_by_sec.get(sec)

    async def _emit_tick_for_sec(self, sec: int) -> TickPayload | None:
        if self._tick_source is None:
            raise Exception("tick source not configured")
        raw = await self._tick_source(sec)
        if raw is None:
            return None
        self.seq += 1
        return TickPayload(seq=self.seq, sec=sec, **raw)

    async def _play_loop(self) -> None:
        try:
            while self.playing and self.sec >= 1:
                tick = await self._emit_tick_for_sec(self.sec)
                if tick:
                    await self.hub.broadcast(ws_tick(tick))
                if self.sec <= 1:
                    await self.pause()
                    await self.hub.broadcast(
                        ws_state(StatePayload(playing=False, sec=1, reason="round_end"))
                    )
                    break
                await asyncio.sleep(1.0)
                self.sec -= 1
        except asyncio.CancelledError:
            raise
