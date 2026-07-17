"""Processo bot: client Socket.IO sempre connesso; strategie caricate a runtime."""

from __future__ import annotations

import sys
import time

import socketio


def run_bot_process(cfg: dict) -> None:
    _run_bot(cfg["host"], int(cfg["port"]))


def _run_bot(host: str, port: int) -> None:
    sio = socketio.Client(reconnection=True, reconnection_delay=0.5, reconnection_delay_max=3.0)
    active = False
    # Placeholder: id attivi senza runner (la logica strategy arriverà dopo).
    strategy_ids: list[str] = []

    def _sync_strategies(ids: list[str]) -> None:
        nonlocal strategy_ids
        strategy_ids = list(ids)
        print(f"bot: strategies synced ids={strategy_ids}", flush=True)

    @sio.event
    def connect():
        print("bot connected (empty shell until strategy.sync)", flush=True)
        sio.emit("session.sync", {}, callback=lambda *_args: None)

    @sio.event
    def disconnect():
        print("bot disconnected", flush=True)

    @sio.on("strategy.sync")
    def on_strategy_sync(payload):
        _sync_strategies(payload.get("strategy_ids") or [])

    @sio.on("session")
    def on_session(payload):
        nonlocal active
        if "bot_active" in payload:
            active = bool(payload["bot_active"])

    @sio.on("bot.status")
    def on_bot_status(payload):
        nonlocal active
        if "bot_active" in payload:
            active = bool(payload["bot_active"])
        if "active_strategy_ids" in payload:
            _sync_strategies(payload.get("active_strategy_ids") or [])

    url = f"http://{host}:{port}"
    while True:
        try:
            if not sio.connected:
                sio.connect(url, auth={"role": "bot"}, transports=["websocket", "polling"], wait_timeout=10)
            sio.wait()
        except Exception as e:
            print(f"bot connect/loop error: {e}", flush=True)
            time.sleep(0.5)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    host, port = args[0], int(args[1])
    _run_bot(host, port)


if __name__ == "__main__":
    main()
