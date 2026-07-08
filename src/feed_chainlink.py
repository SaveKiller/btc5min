import json
import logging
import threading
import time

import websocket

from src.round_state import RoundState
from src.setup import (
    PING_INTERVAL_SEC,
    RATE_LIMIT_BACKOFF_SEC,
    RECONNECT_COOLDOWN_SEC,
    STALL_RECONNECT_SEC,
)

log = logging.getLogger("chainlink")
RTDS_URL = "wss://ws-live-data.polymarket.com"


def ts_to_ms(ts: int) -> int:
    return ts * 1000 if ts < 10_000_000_000 else ts


class ChainlinkFeed:
    """Una sola WS RTDS per processo; aggiorna tutti i round registrati."""

    _instance: "ChainlinkFeed | None" = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls) -> "ChainlinkFeed":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reconnect_lock = threading.Lock()
        self._rounds: list[RoundState] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ping_thread: threading.Thread | None = None
        self._ws: websocket.WebSocketApp | None = None
        self._ping_stop = threading.Event()
        self._intentional_close = False
        self._last_msg_ts = 0.0
        self._backoff_sec = 2.0
        self._next_connect_after = 0.0
        self._last_value: float | None = None
        self._last_ts_ms: int | None = None
        self._conn_id = 0
        self.symbol = "btc/usd"

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="chainlink-feed")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._close_ws(intentional=True)
        if self._thread:
            self._thread.join(timeout=5)

    def register(self, state: RoundState) -> None:
        with self._lock:
            if state not in self._rounds:
                self._rounds.append(state)
            if self._last_value is not None and self._last_ts_ms is not None:
                state.prime_chainlink(self._last_value, self._last_ts_ms)

    def unregister(self, state: RoundState) -> None:
        with self._lock:
            if state in self._rounds:
                self._rounds.remove(state)

    def _run(self) -> None:
        while not self._stop.is_set():
            wait = self._next_connect_after - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                self._run_once()
            except Exception as e:
                if self._stop.is_set():
                    break
                log.warning("chainlink ws error: %s", e)
                self._schedule_backoff()

    def _schedule_backoff(self, sec: float | None = None) -> None:
        if sec is not None:
            self._backoff_sec = sec
        else:
            self._backoff_sec = min(self._backoff_sec * 2, 60)
        until = time.time() + self._backoff_sec
        if until > self._next_connect_after:
            self._next_connect_after = until

    def _request_reconnect(self, reason: str, cooldown: float | None = None) -> None:
        with self._reconnect_lock:
            now = time.time()
            cd = cooldown if cooldown is not None else RECONNECT_COOLDOWN_SEC
            if now < self._next_connect_after:
                return
            self._next_connect_after = now + cd
            log.warning("chainlink %s, next connect in %.0fs", reason, cd)
            self._close_ws(intentional=True)

    def _run_once(self) -> None:
        self._ws = websocket.WebSocketApp(
            RTDS_URL, on_open=self._on_open, on_message=self._on_message,
            on_close=self._on_close, on_error=self._on_error)
        while not self._stop.is_set():
            self._intentional_close = False
            self._ws.run_forever(ping_interval=None)
            if self._stop.is_set() or self._intentional_close:
                return
            if time.time() >= self._next_connect_after:
                self._schedule_backoff()
            wait = self._next_connect_after - time.time()
            if wait > 0:
                time.sleep(wait)

    def _close_ws(self, intentional: bool = True) -> None:
        self._intentional_close = intentional
        self._ping_stop.set()
        if self._ws:
            self._ws.close()

    def _on_open(self, ws) -> None:
        self._conn_id += 1
        self._backoff_sec = 2.0
        self._next_connect_after = 0.0
        self._last_msg_ts = time.time()
        ws.send(json.dumps({
            "action": "subscribe",
            "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}],
        }))
        self._ping_stop.set()
        if self._ping_thread and self._ping_thread.is_alive():
            self._ping_thread.join(timeout=1)
        self._ping_stop = threading.Event()
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True, name="chainlink-ping")
        self._ping_thread.start()

    def _ping_loop(self) -> None:
        while not self._ping_stop.is_set() and not self._stop.is_set():
            if self._last_msg_ts:
                btc_age = time.time() - self._last_msg_ts
                if btc_age > STALL_RECONNECT_SEC:
                    self._request_reconnect(f"stall {btc_age:.0f}s")
                    return
            if self._ws:
                try:
                    self._ws.send("ping")
                except Exception:
                    return
            time.sleep(PING_INTERVAL_SEC)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        pass

    def _on_error(self, ws, error) -> None:
        if self._intentional_close or self._stop.is_set():
            return
        err = str(error)
        log.warning("chainlink ws error: %s", error)
        if "429" in err:
            self._schedule_backoff(RATE_LIMIT_BACKOFF_SEC)

    def _on_message(self, ws, raw: str) -> None:
        if not raw or raw.upper() == "PONG":
            return
        msg = json.loads(raw)
        if msg.get("topic") != "crypto_prices_chainlink":
            return
        payload = msg.get("payload") or {}
        if payload.get("symbol") != self.symbol:
            return
        self._last_msg_ts = time.time()
        with self._lock:
            rounds = list(self._rounds)
        if "data" in payload:
            for point in sorted(payload["data"], key=lambda p: int(p["timestamp"])):
                self._dispatch(float(point["value"]), ts_to_ms(int(point["timestamp"])), rounds)
        elif "value" in payload:
            self._dispatch(float(payload["value"]), ts_to_ms(int(payload["timestamp"])), rounds)

    def _dispatch(self, value: float, ts_ms: int, rounds: list[RoundState]) -> None:
        recv_ms = int(time.time() * 1000)
        self._last_value = value
        self._last_ts_ms = ts_ms
        for state in rounds:
            if state.chainlink_done.is_set():
                continue
            state.apply_chainlink(value, ts_ms, recv_ms)
