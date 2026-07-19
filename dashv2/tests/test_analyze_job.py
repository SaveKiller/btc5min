"""Test job analyze + reduce Markdown su LoadedRound sintetico."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dashv2.batch.analyze_job import (
    build_round_view,
    load_reduce_results,
    run_analyze_round,
)
from dashv2.batch.reduce import reduce_analyze_fallback
from dashv2.rounds import LoadedRound
from src.book import BookSnapshot

_MOD = '''
def analyze_round(round_view):
    return {"n_ticks": len(round_view["ticks"]), "outcome": round_view["outcome"]}

def reduce_results(per_round):
    n = sum(1 for r in per_round if r.get("ok"))
    return f"# Stats\\n\\nrounds_ok: {n}\\n"
'''

_MOD_NO_REDUCE = '''
def analyze_round(round_view):
    return {"n_ticks": len(round_view["ticks"])}
'''


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
    return LoadedRound(
        market_start_ts=mts,
        market_end_ts=mts + 300,
        fee_rate=0.02,
        ptb_chainlink=89990.0,
        outcome_code=1,
        outcome_name="Up",
        final_chainlink=90100.0,
        ticks_by_sec={200: _tick(200), 100: _tick(100)},
        books_by_sec={200: _book(), 100: _book()},
        all_secs=set(range(1, 301)),
    )


class TestAnalyzeJob(unittest.TestCase):
    def test_build_round_view_keys(self):
        loaded = _synthetic_round()
        view = build_round_view(loaded)
        self.assertEqual(view["market_start_ts"], loaded.market_start_ts)
        self.assertEqual(view["hour_utc"], 14)
        self.assertEqual(view["outcome"], "Up")
        self.assertEqual(view["ptb_chainlink"], 89990.0)
        self.assertEqual(view["final_chainlink"], 90100.0)
        self.assertEqual(view["fee_rate"], 0.02)
        self.assertEqual(view["secs"], [100, 200])
        self.assertEqual([t["sec"] for t in view["ticks"]], [100, 200])

    def test_run_analyze_and_reduce_results(self):
        loaded = _synthetic_round()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "analyze_stub.py"
            path.write_text(_MOD, encoding="utf-8")
            out = run_analyze_round(loaded, path)
            reduce_fn = load_reduce_results(path)

        self.assertTrue(out["ok"], out.get("error"))
        self.assertIsNone(out["error"])
        self.assertEqual(out["market_start_ts"], loaded.market_start_ts)
        self.assertEqual(out["hour_utc"], 14)
        self.assertEqual(out["n_ticks"], 2)
        self.assertEqual(out["outcome"], "Up")
        self.assertIsNotNone(reduce_fn)
        md = reduce_fn([out])
        self.assertEqual(md, "# Stats\n\nrounds_ok: 1\n")

    def test_load_reduce_none_uses_fallback(self):
        loaded = _synthetic_round()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "analyze_no_reduce.py"
            path.write_text(_MOD_NO_REDUCE, encoding="utf-8")
            out = run_analyze_round(loaded, path)
            reduce_fn = load_reduce_results(path)

        self.assertTrue(out["ok"], out.get("error"))
        self.assertIsNone(reduce_fn)
        md = reduce_analyze_fallback([out])
        self.assertIn("# Stats", md)
        self.assertIn("rounds_ok: 1", md)
        self.assertIn("rounds_total: 1", md)


if __name__ == "__main__":
    unittest.main()
