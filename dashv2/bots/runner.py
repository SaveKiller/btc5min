"""Processo bot-runner: client Socket.IO co-controller."""

from __future__ import annotations

import sys
import time
import uuid

import socketio

from dashv2.bots import load_bot

_TRADE_CMDS = frozenset({"order.place", "order.close", "order.cancel"})


def run_bot_runner(host: str, port: int, bot_id: str) -> None:
    plugin = load_bot(bot_id)
    sio = socketio.Client(reconnection=False)
    session: dict | None = None
    orders: dict | None = None
    armed = False
    active = True

    def _emit_actions(actions: list[dict]) -> None:
        for a in actions:
            cmd, payload = a["cmd"], a.get("payload") or {}
            if not active and cmd in _TRADE_CMDS:
                continue
            sio.emit(cmd, payload, callback=lambda *_args: None)

    @sio.event
    def connect():
        print(f"bot-runner connected bot_id={bot_id}", flush=True)
        sio.emit("session.sync", {}, callback=lambda *_args: None)

    @sio.event
    def disconnect():
        print("bot-runner disconnected", flush=True)

    @sio.on("session")
    def on_session(payload):
        nonlocal session, armed, active
        session = payload
        if "bot_active" in payload:
            active = bool(payload["bot_active"])
        if payload.get("preview"):
            return
        if payload.get("loaded") and payload.get("sec") == 300 and not payload.get("round_ended"):
            if not armed:
                armed = True
                _emit_actions(plugin.on_round_start(payload))
        _emit_actions(plugin.on_session(payload))

    @sio.on("tick")
    def on_tick(payload):
        if payload.get("preview"):
            return
        _emit_actions(plugin.on_tick(payload, session, orders))

    @sio.on("orders")
    def on_orders(payload):
        nonlocal orders
        if payload.get("preview"):
            return
        orders = payload
        _emit_actions(plugin.on_orders(payload))

    @sio.on("action")
    def on_action(payload):
        _emit_actions(plugin.on_action(payload))

    @sio.on("consult.message")
    def on_consult(payload):
        if payload.get("from") == "bot":
            return
        replies = plugin.on_consult(payload)
        for a in replies:
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
        _emit_actions(plugin.on_round_end(payload))
        armed = False

    @sio.on("bot.status")
    def on_bot_status(payload):
        nonlocal active
        if payload.get("selected_bot_id") != bot_id:
            print(f"bot-runner exiting: deselected ({payload.get('selected_bot_id')})", flush=True)
            sio.disconnect()
            return
        if "bot_active" in payload:
            active = bool(payload["bot_active"])

    url = f"http://{host}:{port}"
    sio.connect(url, auth={"role": "bot"}, transports=["websocket", "polling"])
    try:
        while sio.connected:
            time.sleep(0.2)
    finally:
        if sio.connected:
            sio.disconnect()


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    host, port, bot_id = args[0], int(args[1]), args[2]
    run_bot_runner(host, port, bot_id)


if __name__ == "__main__":
    main()
