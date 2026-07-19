"""Processo bot: client Socket.IO; carica moduli strategy e emette order.*."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import socketio

from dashv2.bots.runner import StrategyRunner
from dashv2.strategies import strategies_dir


def run_bot_process(cfg: dict) -> None:
    _run_bot(cfg)


def _run_bot(cfg: dict) -> None:
    host, port = cfg["host"], int(cfg["port"])
    root = strategies_dir(Path(cfg["history_dir"]))
    runner = StrategyRunner(root)
    sio = socketio.Client(reconnection=True, reconnection_delay=0.5, reconnection_delay_max=3.0)
    active = False
    strategy_ids: list[str] = []
    last_tick: dict | None = None
    last_orders: dict | None = None
    last_session: dict | None = None

    def _sync_strategies(ids: list[str]) -> None:
        nonlocal strategy_ids
        strategy_ids = list(ids)
        try:
            runner.sync(strategy_ids)
        except Exception as e:
            print(f"bot: strategy sync error: {e}", flush=True)
        print(f"bot: strategies synced ids={strategy_ids}", flush=True)

    def _emit_actions(pairs: list[tuple[str, dict]]) -> None:
        for sid, act in pairs:
            cmd = act["cmd"]
            payload = {k: v for k, v in act.items() if k != "cmd"}
            payload["strategy_id"] = sid
            sio.emit(cmd, payload, callback=lambda *_a: None)

    def _ctx() -> dict:
        tick = last_tick or {}
        orders = last_orders or {}
        session = last_session or {}
        return {
            "sec": tick.get("sec"),
            "tradable": tick.get("tradable"),
            "chainlink_btc": tick.get("chainlink_btc"),
            "delta_usd": tick.get("delta_usd"),
            "ptb_chainlink": session.get("ptb_chainlink"),
            "liq2_ask_usd": tick.get("liq2_ask_usd"),
            "market_start_ts": session.get("market_start_ts"),
            "up_ask_c": tick.get("up_ask_c"), "up_bid_c": tick.get("up_bid_c"),
            "down_ask_c": tick.get("down_ask_c"), "down_bid_c": tick.get("down_bid_c"),
            "up_mid_c": tick.get("up_mid_c"), "down_mid_c": tick.get("down_mid_c"),
            "majority_side": tick.get("majority_side"),
            "vol": tick.get("vol") or {},
            "risk": tick.get("risk") or {},
            "dwin_ref_side": tick.get("dwin_ref_side"),
            "dwin_a": tick.get("dwin_a"), "dwin_b": tick.get("dwin_b"),
            "open_orders": list(orders.get("open") or []),
            "bot_active": active,
        }

    @sio.event
    def connect():
        print("bot connected", flush=True)
        sio.emit("session.sync", {}, callback=lambda *_args: None)

    @sio.event
    def disconnect():
        print("bot disconnected", flush=True)

    @sio.on("strategy.sync")
    def on_strategy_sync(payload):
        _sync_strategies(payload.get("strategy_ids") or [])

    @sio.on("session")
    def on_session(payload):
        nonlocal active, last_session
        last_session = payload
        if "bot_active" in payload:
            active = bool(payload["bot_active"])
        if payload.get("sec") == 300 and payload.get("loaded") and not payload.get("round_ended"):
            if active and strategy_ids:
                _emit_actions(runner.dispatch("on_round_start", strategy_ids, _ctx()))

    @sio.on("bot.status")
    def on_bot_status(payload):
        nonlocal active
        if "bot_active" in payload:
            active = bool(payload["bot_active"])
        if "active_strategy_ids" in payload:
            _sync_strategies(payload.get("active_strategy_ids") or [])

    @sio.on("orders")
    def on_orders(payload):
        nonlocal last_orders
        last_orders = payload

    @sio.on("tick")
    def on_tick(payload):
        nonlocal last_tick
        if payload.get("preview"):
            return
        last_tick = payload
        if not active or not strategy_ids:
            return
        _emit_actions(runner.dispatch("on_tick", strategy_ids, _ctx()))

    @sio.on("round_end")
    def on_round_end(payload):
        if not active or not strategy_ids:
            return
        ctx = {**_ctx(), "round_end": payload}
        _emit_actions(runner.dispatch("on_round_end", strategy_ids, ctx))

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
    _run_bot({"host": host, "port": port, "history_dir": Path("history")})


if __name__ == "__main__":
    main()
