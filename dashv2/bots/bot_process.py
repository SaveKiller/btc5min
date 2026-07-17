"""Processo bot: client Socket.IO sempre connesso; strategie caricate a runtime."""

from __future__ import annotations

import sys
import time
import uuid

import socketio

from dashv2.bots import load_bot

_TRADE_CMDS = frozenset({"order.place", "order.close", "order.cancel"})


def run_bot_process(cfg: dict) -> None:
    _run_bot(cfg["host"], int(cfg["port"]))


def _run_bot(host: str, port: int) -> None:
    sio = socketio.Client(reconnection=True, reconnection_delay=0.5, reconnection_delay_max=3.0)
    session: dict | None = None
    orders: dict | None = None
    armed = False
    active = False
    strategies: dict[str, object] = {}

    def _emit_actions(actions: list[dict]) -> None:
        for a in actions:
            cmd, payload = a["cmd"], a.get("payload") or {}
            if not active and cmd in _TRADE_CMDS:
                continue
            sio.emit(cmd, payload, callback=lambda *_args: None)

    def _fanout(method: str, *args) -> None:
        actions: list[dict] = []
        for plugin in strategies.values():
            actions.extend(getattr(plugin, method)(*args))
        _emit_actions(actions)

    def _load_strategy(strategy_id: str | None) -> None:
        nonlocal strategies
        strategies = {}
        if strategy_id is None:
            print("bot: strategies cleared", flush=True)
            return
        strategies[strategy_id] = load_bot(strategy_id)
        print(f"bot: strategy loaded id={strategy_id}", flush=True)

    @sio.event
    def connect():
        print("bot connected (empty shell until strategy.load)", flush=True)
        sio.emit("session.sync", {}, callback=lambda *_args: None)

    @sio.event
    def disconnect():
        print("bot disconnected", flush=True)

    @sio.on("strategy.load")
    def on_strategy_load(payload):
        _load_strategy(payload.get("strategy_id"))

    @sio.on("session")
    def on_session(payload):
        nonlocal session, armed, active
        session = payload
        if "bot_active" in payload:
            active = bool(payload["bot_active"])
        if payload.get("preview"):
            return
        if not strategies:
            return
        if payload.get("loaded") and payload.get("sec") == 300 and not payload.get("round_ended"):
            if not armed:
                armed = True
                _fanout("on_round_start", payload)
        _fanout("on_session", payload)

    @sio.on("tick")
    def on_tick(payload):
        if payload.get("preview") or not strategies:
            return
        _fanout("on_tick", payload, session, orders)

    @sio.on("orders")
    def on_orders(payload):
        nonlocal orders
        if payload.get("preview"):
            return
        orders = payload
        if strategies:
            _fanout("on_orders", payload)

    @sio.on("action")
    def on_action(payload):
        if strategies:
            _fanout("on_action", payload)

    @sio.on("consult.message")
    def on_consult(payload):
        if payload.get("from") == "bot" or not strategies:
            return
        for plugin in strategies.values():
            for a in plugin.on_consult(payload):
                if a["cmd"] in ("consult.reply", "consult.send"):
                    msg = a.get("payload") or {}
                    msg.setdefault("id", uuid.uuid4().hex[:12])
                    msg.setdefault("from", "bot")
                    sio.emit("consult.send", msg)
                else:
                    _emit_actions([a])

    @sio.on("round_end")
    def on_round_end(payload):
        nonlocal armed
        if strategies:
            _fanout("on_round_end", payload)
        armed = False

    @sio.on("bot.status")
    def on_bot_status(payload):
        nonlocal active
        if "bot_active" in payload:
            active = bool(payload["bot_active"])

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
