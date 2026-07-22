"""Test job headless strategy su LoadedRound sintetico."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from dashv2.batch.strategy_job import run_strategy_round
from dashv2.rounds import LoadedRound
from src.book import BookSnapshot

_STUB = """
_tick_strategy_ids = []
def on_round_start(ctx): return []
def on_tick(ctx):
    _tick_strategy_ids.append(ctx["strategy_id"])
    if ctx.get("sec") == 200 and ctx.get("tradable"):
        return [{"cmd": "order.place", "side": "Up", "size_usd": 10.0}]
    return []
def on_round_end(ctx): return []
"""


def _book(up_ask=0.55, down_ask=0.45):
    return BookSnapshot(
        [(up_ask - 0.02, 1000)], [(up_ask, 1000)],
        [(down_ask - 0.02, 1000)], [(down_ask, 1000)],
        up_ask - 0.02, up_ask, down_ask - 0.02, down_ask,
    )


def _tick(sec: int, up_ask=0.55, down_ask=0.45) -> dict:
    up_bid, down_bid = up_ask - 0.02, down_ask - 0.02
    return {
        "sec": sec,
        "chainlink_btc": 90000.0,
        "chainlink_stale": False,
        "up_bid": up_bid, "up_ask": up_ask,
        "down_bid": down_bid, "down_ask": down_ask,
        "delta_usd": 10,
        "partial": False,
        "gap": False,
        "up_mid_c": int(round(((up_bid + up_ask) / 2) * 100)),
        "down_mid_c": int(round(((down_bid + down_ask) / 2) * 100)),
        "majority_side": "Up",
        "vol": {},
        "side_risk": {"Up": {"rq": None, "rs": None}, "Down": {"rq": None, "rs": None}},
        "dwin_a": None,
        "dwin_b_pct": None,
    }


def _synthetic_round() -> LoadedRound:
    # 2026-07-19 14:00:00 UTC
    mts = 1784469600
    tick200 = _tick(200)
    book200 = _book()
    return LoadedRound(
        market_start_ts=mts,
        market_end_ts=mts + 300,
        fee_rate=0.02,
        ptb_chainlink=89990.0,
        outcome_code=1,
        outcome_name="Up",
        final_chainlink=90100.0,
        ticks_by_sec={200: tick200},
        books_by_sec={200: book200},
        all_secs=set(range(1, 301)),
    )


class TestStrategyJob(unittest.TestCase):
    def test_place_at_200_settles_win(self):
        loaded = _synthetic_round()
        sid = "stub"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "strategy_stub.py"
            path.write_text(_STUB, encoding="utf-8")
            out = run_strategy_round(
                loaded=loaded,
                module_path=path,
                strategy_id=sid,
                size_up=10.0,
                size_down=10.0,
            )
        mod = sys.modules[f"dashv2_batch_strategy_{sid}"]
        self.assertTrue(mod._tick_strategy_ids)
        self.assertTrue(all(x == sid for x in mod._tick_strategy_ids))
        self.assertTrue(out["ok"], out.get("error"))
        self.assertIsNone(out["error"])
        self.assertEqual(out["market_start_ts"], loaded.market_start_ts)
        self.assertEqual(out["hour_utc"], 14)
        self.assertTrue(out["traded"])
        self.assertEqual(out["n_orders"], 1)
        self.assertEqual(out["n_wins"], 1)
        self.assertEqual(out["n_losses"], 0)
        self.assertGreater(out["pnl_usd"], 0.0)
        self.assertEqual(len(out["orders"]), 1)
        self.assertEqual(out["orders"][0]["side"], "Up")
        self.assertEqual(out["orders"][0]["entry_sec"], 200)
        self.assertEqual(out["orders"][0]["entry_delta_usd"], 10.0)
        self.assertEqual(out["orders"][0]["entry_quote"], 0.55)
        self.assertEqual(out["orders"][0]["exit_sec"], 0)
        self.assertEqual(out["orders"][0]["exit_delta_usd"], 110.0)
        self.assertEqual(out["orders"][0]["exit_quote"], 1.0)
        self.assertEqual(out["orders"][0]["result"], "won")
        self.assertEqual(out["action_errors"], [])


if __name__ == "__main__":
    unittest.main()
