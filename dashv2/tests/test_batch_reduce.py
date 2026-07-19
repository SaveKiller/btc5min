# dashv2/tests/test_batch_reduce.py
from __future__ import annotations
import unittest
from dashv2.batch.reduce import reduce_strategy_rows
from dashv2.batch.markets import UTC_HOUR_MARKETS

class TestReduceStrategy(unittest.TestCase):
    def test_markets_len_24(self):
        self.assertEqual(len(UTC_HOUR_MARKETS), 24)
        self.assertEqual(UTC_HOUR_MARKETS[14], "Londra, New York")

    def test_bucket_and_total(self):
        rows = [
            {"hour_utc": 14, "ok": True, "pnl_usd": 2.0, "traded": True},
            {"hour_utc": 14, "ok": True, "pnl_usd": -1.0, "traded": True},
            {"hour_utc": 14, "ok": True, "pnl_usd": 0.0, "traded": False},
            {"hour_utc": 9, "ok": True, "pnl_usd": 5.0, "traded": True},
            {"hour_utc": 9, "ok": False, "pnl_usd": 0.0, "traded": False},  # ignored in agg
        ]
        out = reduce_strategy_rows(rows)
        self.assertEqual(len(out["hours"]), 24)
        h14 = out["hours"][14]
        self.assertEqual(h14["hour"], "14:00")
        self.assertEqual(h14["market"], "Londra, New York")
        self.assertEqual(h14["rounds"], 3)
        self.assertEqual(h14["traded"], 2)
        self.assertEqual(h14["pos"], 1)
        self.assertEqual(h14["neg"], 1)
        self.assertEqual(h14["flat"], 1)
        self.assertEqual(h14["pnl_sum"], 1.0)
        self.assertAlmostEqual(h14["pnl_avg"], 1.0 / 3)
        self.assertEqual(out["total"]["rounds"], 4)  # solo ok=True
        self.assertEqual(out["total"]["pnl_sum"], 6.0)
