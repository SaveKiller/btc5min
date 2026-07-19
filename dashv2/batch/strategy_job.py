"""Job headless: backtest di una strategy su un singolo LoadedRound."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from dashv2.batch.ctx import build_strategy_ctx
from dashv2.engine.plugins.replay import _public_tick
from dashv2.orders import OrderEngine
from dashv2.rounds import LoadedRound


def _load_module(module_path: Path, strategy_id: str):
    """Import diretto del file strategy (senza Socket.IO)."""
    name = f"dashv2_batch_strategy_{strategy_id}"
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _apply(engine: OrderEngine, act: dict, sid: str, sec: int, tick, book, fee: float, action_errors: list) -> None:
    """Applica un'azione order.*; errori loggati senza abortire il round."""
    cmd = act["cmd"]
    try:
        if cmd == "order.place":
            engine.place(
                act["side"], float(act["size_usd"]), sec, tick, book, fee,
                "batch", "bot", sid, act.get("reason"),
            )
        elif cmd == "order.close":
            engine.close(act["order_id"], sec, tick, book, fee, reason=act.get("reason"))
        elif cmd == "order.cancel":
            engine.cancel(act["order_id"])
        else:
            raise Exception(f"unknown cmd {cmd}")
    except Exception as e:
        msg = str(e)
        print(f"batch strategy action error: {msg}", flush=True)
        action_errors.append(msg)


def _dispatch(mod, hook: str, ctx: dict, engine: OrderEngine, sid: str, sec: int, tick, book, fee: float, action_errors: list) -> None:
    # Come StrategyRunner.dispatch: strategy_id iniettato al momento della chiamata hook
    actions = getattr(mod, hook)({**ctx, "strategy_id": sid}) or []
    for act in actions:
        _apply(engine, act, sid, sec, tick, book, fee, action_errors)


def run_strategy_round(
    *,
    loaded: LoadedRound,
    module_path: Path,
    strategy_id: str,
    size_up: float,
    size_down: float,
) -> dict:
    """Esegue backtest headless di un round; non scrive history/accounts."""
    hour_utc = datetime.fromtimestamp(loaded.market_start_ts, timezone.utc).hour
    base = {
        "market_start_ts": loaded.market_start_ts,
        "hour_utc": hour_utc,
        "ok": False,
        "error": None,
        "pnl_usd": 0.0,
        "n_orders": 0,
        "n_wins": 0,
        "n_losses": 0,
        "traded": False,
    }
    try:
        mod = _load_module(module_path, strategy_id)
        engine = OrderEngine(size_up, size_down)
        session = {
            "ptb_chainlink": loaded.ptb_chainlink,
            "market_start_ts": loaded.market_start_ts,
        }
        action_errors: list[str] = []
        last_public: dict | None = None
        seq = 0

        for sec in range(300, 0, -1):
            seq += 1
            tick = loaded.ticks_by_sec.get(sec)
            gap = tick is None or tick.get("gap", False)
            book = None if gap else loaded.books_by_sec.get(sec)
            public = _public_tick(tick, sec, seq, gap, book)
            last_public = public
            if not gap and tick is not None and book is not None:
                engine.revalue_mtm(sec, tick, book, loaded.fee_rate)
            ctx = build_strategy_ctx(public, session, engine.open_orders, bot_active=True)
            if sec == 300:
                _dispatch(mod, "on_round_start", ctx, engine, strategy_id, sec, tick, book, loaded.fee_rate, action_errors)
                ctx = build_strategy_ctx(public, session, engine.open_orders, bot_active=True)
            _dispatch(mod, "on_tick", ctx, engine, strategy_id, sec, tick, book, loaded.fee_rate, action_errors)

        settled = engine.settle_open(loaded.outcome_name, 0, loaded.final_chainlink)
        end_ctx = build_strategy_ctx(
            last_public if last_public is not None else _public_tick(None, 0, seq + 1, True, None),
            session,
            engine.open_orders,
            bot_active=True,
        )
        end_ctx["round_end"] = {
            "outcome": loaded.outcome_name,
            "outcome_label": loaded.outcome_name.upper(),
            "final_chainlink": loaded.final_chainlink,
            "settled_orders": settled,
        }
        _dispatch(mod, "on_round_end", end_ctx, engine, strategy_id, 0, None, None, loaded.fee_rate, action_errors)

        closed = engine.closed_orders
        pnl = sum(o["pnl_usd"] for o in closed)
        n_wins = sum(1 for o in closed if o.get("result") == "won")
        n_losses = sum(1 for o in closed if o.get("result") == "lost")
        return {
            **base,
            "ok": True,
            "pnl_usd": pnl,
            "n_orders": len(closed),
            "n_wins": n_wins,
            "n_losses": n_losses,
            "traded": len(closed) > 0,
        }
    except Exception as e:
        print(f"batch strategy round error: {e}", flush=True)
        return {**base, "ok": False, "error": str(e)}
