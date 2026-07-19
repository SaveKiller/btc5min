"""Test repository sessioni backtest (history/simulations/)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dashv2.simulations import (
    create_simulation, delete_simulation, list_simulations,
    load_simulation, simulation_label,
)


class TestSimulations(unittest.TestCase):
    def test_create_list_load_delete(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            table = {"hours": [], "total": {"rounds": 1, "traded": 1, "pos": 1, "neg": 0, "flat": 0, "pnl_sum": 1.0, "pnl_avg": 1.0}}
            summary = {
                "name": "prudence-80-1", "day_from": "2026-07-10", "day_to": "2026-07-18",
                "workers": 10, "elapsed_sec": 1.2, "skipped": 0, "errors": 0, "rounds": 1,
            }
            rounds = [{"market_start_ts": 1, "hour_utc": 12, "ok": True, "pnl_usd": 1.0, "traded": True}]
            sim = create_simulation(
                hist, strategy_id="abc123", strategy_name="prudence-80-1",
                day_from="2026-07-10", day_to="2026-07-18",
                summary=summary, table=table, rounds=rounds,
            )
            self.assertEqual(sim["strategy_name"], "prudence-80-1")
            self.assertEqual(len(sim["rounds"]), 1)
            items = list_simulations(hist)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], sim["id"])
            self.assertIn("prudence-80-1", items[0]["label"])
            self.assertIn("2026-07-10→18", items[0]["label"])
            loaded = load_simulation(hist, sim["id"])
            self.assertEqual(loaded["rounds"][0]["pnl_usd"], 1.0)
            self.assertEqual(loaded["table"]["total"]["rounds"], 1)
            delete_simulation(hist, sim["id"])
            self.assertEqual(list_simulations(hist), [])

    def test_label_range_abbrev(self):
        data = {
            "strategy_name": "s1", "created_at_utc": "2026-07-19T15:24:00Z",
            "day_from": "2026-07-10", "day_to": "2026-07-18",
        }
        self.assertEqual(simulation_label(data), "s1 · 2026-07-19 15:24 · 2026-07-10→18")
        data2 = {**data, "day_from": "2026-06-28", "day_to": "2026-07-02"}
        self.assertEqual(simulation_label(data2), "s1 · 2026-07-19 15:24 · 2026-06-28→07-02")


if __name__ == "__main__":
    unittest.main()
