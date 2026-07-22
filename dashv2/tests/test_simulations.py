"""Test repository sessioni backtest (history/simulations/)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dashv2.simulations import (
    compute_balance_stats, create_simulation, delete_simulation, list_simulations,
    load_round_orders, load_simulation, session_capital_size_usd,
    simulation_has_orders, simulation_label,
)


class TestSimulations(unittest.TestCase):
    def test_create_list_load_delete_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            table = {"hours": [], "total": {"rounds": 1, "traded": 1, "pos": 1, "neg": 0, "flat": 0, "pnl_sum": 1.0, "pos_sum": 1.0, "neg_sum": 0.0, "pnl_avg_pos": 1.0, "pnl_avg_neg": None}}
            summary = {
                "name": "prudence-80-1", "day_from": "2026-07-10", "day_to": "2026-07-18",
                "workers": 10, "elapsed_sec": 1.2, "skipped": 0, "errors": 0, "rounds": 1,
            }
            rounds = [{
                "market_start_ts": 1, "hour_utc": 12, "ok": True, "error": None,
                "pnl_usd": 1.0, "n_orders": 1, "n_wins": 1, "n_losses": 0, "traded": True,
                "action_errors": [],
                "orders": [{
                    "id": "ord1", "side": "Up", "entry_sec": 200, "exit_sec": 0,
                    "size_usd": 10.0, "shares": 18.0, "avg_entry_price": 0.55,
                    "best_ask": 0.55, "best_ask_c": 55, "entry_fee_usd": 0.1,
                    "exit_fee_usd": 0.0, "entry_btc": 90000.0, "exit_btc": 90100.0,
                    "exit_price": 1.0, "proceeds_usd": 18.0, "pnl_usd": 8.0,
                    "result": "won", "close_type": "settlement", "reason": None,
                    "close_reason": None, "payout_if_win_usd": 18.0, "profit_if_win_usd": 8.0,
                    "account_id": "batch", "source": "bot", "strategy_id": "abc123",
                }],
            }]
            sim = create_simulation(
                hist, strategy_id="abc123", strategy_name="prudence-80-1",
                strategy_version=3,
                day_from="2026-07-10", day_to="2026-07-18",
                summary=summary, table=table, rounds=rounds,
            )
            self.assertEqual(sim["strategy_name"], "prudence-80-1")
            self.assertEqual(sim["strategy_version"], 3)
            self.assertTrue(sim["has_orders"])
            self.assertEqual(len(sim["rounds"]), 1)
            self.assertNotIn("orders", sim["rounds"][0])
            self.assertEqual(sim["rounds"][0]["stake_usd"], 10.0)
            self.assertTrue((hist / "simulations" / f"simulation_{sim['id']}.sqlite").is_file())
            items = list_simulations(hist)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], sim["id"])
            self.assertEqual(items[0]["pnl_total"], 1.0)
            self.assertTrue(items[0]["has_orders"])
            self.assertIn("prudence-80-1 v3", items[0]["label"])
            loaded = load_simulation(hist, sim["id"])
            self.assertEqual(loaded["rounds"][0]["pnl_usd"], 1.0)
            self.assertEqual(loaded["rounds"][0]["stake_usd"], 10.0)
            self.assertEqual(loaded["table"]["total"]["rounds"], 1)
            self.assertEqual(loaded["strategy_version"], 3)
            self.assertTrue(simulation_has_orders(hist, sim["id"]))
            self.assertIn("bal_max", sim["summary"])
            self.assertIn("bal_min", sim["summary"])
            self.assertIn("bal_used", sim["summary"])
            self.assertEqual(sim["summary"]["bal_used"], 10.0)
            self.assertEqual(sim["summary"]["bal_max"], 1.0)
            self.assertEqual(sim["summary"]["bal_min"], 0.0)
            orders = load_round_orders(hist, sim["id"], 1)
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]["side"], "Up")
            self.assertEqual(orders[0]["entry_sec"], 200)
            self.assertEqual(orders[0]["result"], "won")
            delete_simulation(hist, sim["id"])
            self.assertEqual(list_simulations(hist), [])

    def test_json_legacy_list_load_no_orders(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            root = hist / "simulations"
            root.mkdir(parents=True)
            payload = {
                "schema_version": 1, "id": "legacyjson01",
                "strategy_id": "s1", "strategy_name": "old", "strategy_version": 1,
                "created_at_utc": "2026-07-19T15:24:00Z",
                "day_from": "2026-07-10", "day_to": "2026-07-18",
                "summary": {"name": "old", "rounds": 1}, "table": {"hours": [], "total": {"rounds": 1, "pnl_sum": 0.0}},
                "rounds": [{"market_start_ts": 9, "hour_utc": 1, "ok": True, "pnl_usd": 0.0, "traded": False}],
            }
            (root / "simulation_legacyjson01.json").write_text(
                __import__("json").dumps(payload), encoding="utf-8",
            )
            items = list_simulations(hist)
            self.assertEqual(len(items), 1)
            self.assertFalse(items[0]["has_orders"])
            loaded = load_simulation(hist, "legacyjson01")
            self.assertFalse(loaded["has_orders"])
            self.assertFalse(simulation_has_orders(hist, "legacyjson01"))
            with self.assertRaises(Exception):
                load_round_orders(hist, "legacyjson01", 9)

    def test_label_range_abbrev(self):
        data = {
            "strategy_name": "s1", "strategy_version": 2,
            "created_at_utc": "2026-07-19T15:24:00Z",
            "day_from": "2026-07-10", "day_to": "2026-07-18",
            "summary": {"rounds": 1},
        }
        self.assertEqual(simulation_label(data), "s1 v2 · 2026-07-19 15:24 · 10 JUL -> 18 JUL · R1")
        data2 = {**data, "day_from": "2026-06-28", "day_to": "2026-07-02"}
        self.assertEqual(simulation_label(data2), "s1 v2 · 2026-07-19 15:24 · 28 JUN -> 02 JUL · R1")

    def test_session_capital_and_balance_used(self):
        bets = [
            {"size_usd": 100.0, "entry_sec": 200, "exit_sec": 100, "pnl_usd": -100.0},
            {"size_usd": 100.0, "entry_sec": 90, "exit_sec": 0, "pnl_usd": 40.0},
        ]
        # Prima open 100 (inject 100); close loss → wallet 0; seconda open inject 100 → 200.
        self.assertEqual(session_capital_size_usd(bets), 200.0)
        rounds = [
            {
                "market_start_ts": 1, "ok": True, "pnl_usd": -100.0,
                "orders": [{"size_usd": 100.0, "entry_sec": 200, "exit_sec": 0, "pnl_usd": -100.0}],
            },
            {
                "market_start_ts": 2, "ok": True, "pnl_usd": 20.0,
                "orders": [{"size_usd": 50.0, "entry_sec": 200, "exit_sec": 0, "pnl_usd": 20.0}],
            },
        ]
        # Round1 stake 100, cum0 → used 100; after cum -100.
        # Round2 stake 50, need 50-(-100)=150 → used 150; cum -80.
        stats = compute_balance_stats(rounds)
        self.assertEqual(stats["bal_used"], 150.0)
        self.assertEqual(stats["bal_max"], 0.0)
        self.assertEqual(stats["bal_min"], -100.0)

    def test_load_backfills_balance_summary(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            table = {"hours": [], "total": {"rounds": 1, "pnl_sum": 1.0}}
            rounds = [{
                "market_start_ts": 1, "hour_utc": 12, "ok": True, "error": None,
                "pnl_usd": 1.0, "n_orders": 1, "n_wins": 1, "n_losses": 0, "traded": True,
                "action_errors": [],
                "orders": [{
                    "id": "ord1", "side": "Up", "entry_sec": 200, "exit_sec": 0,
                    "size_usd": 10.0, "shares": 18.0, "avg_entry_price": 0.55,
                    "best_ask": 0.55, "best_ask_c": 55, "entry_fee_usd": 0.1,
                    "exit_fee_usd": 0.0, "entry_btc": 90000.0, "exit_btc": 90100.0,
                    "exit_price": 1.0, "proceeds_usd": 18.0, "pnl_usd": 8.0,
                    "result": "won", "close_type": "settlement", "reason": None,
                    "close_reason": None, "payout_if_win_usd": 18.0, "profit_if_win_usd": 8.0,
                    "account_id": "batch", "source": "bot", "strategy_id": "abc123",
                }],
            }]
            sim = create_simulation(
                hist, strategy_id="abc123", strategy_name="prudence-80-1",
                strategy_version=3,
                day_from="2026-07-10", day_to="2026-07-18",
                summary={"name": "x", "rounds": 1}, table=table, rounds=rounds,
            )
            import json
            import sqlite3
            path = hist / "simulations" / f"simulation_{sim['id']}.sqlite"
            conn = sqlite3.connect(str(path))
            row = conn.execute("SELECT summary_json FROM meta").fetchone()
            summary = json.loads(row[0])
            del summary["bal_max"]
            del summary["bal_min"]
            del summary["bal_used"]
            conn.execute("UPDATE meta SET summary_json=?", (json.dumps(summary),))
            conn.commit()
            conn.close()
            loaded = load_simulation(hist, sim["id"])
            self.assertEqual(loaded["summary"]["bal_used"], 10.0)
            loaded2 = load_simulation(hist, sim["id"])
            self.assertEqual(loaded2["summary"]["bal_used"], 10.0)


if __name__ == "__main__":
    unittest.main()
