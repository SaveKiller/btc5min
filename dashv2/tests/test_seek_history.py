"""Test seek timeline, history filter anti-spoiler."""

import json
import tempfile
import unittest
from pathlib import Path

from dashv2.history import order_rows_for_run, visible_history, write_run
from dashv2.orders import OrderEngine
from src.book import BookSnapshot


def _book(up_ask=0.55, down_ask=0.45):
    return BookSnapshot(
        [(up_ask - 0.02, 1000)], [(up_ask, 1000)], [(down_ask - 0.02, 1000)], [(down_ask, 1000)],
        up_ask - 0.02, up_ask, down_ask - 0.02, down_ask)


class TestSeekAndHistory(unittest.TestCase):
    def test_cancel_removes_open_without_history(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        order = eng.place("Up", 10.0, 200, tick, book, 0.02)
        eng.cancel(order["id"])
        self.assertEqual(eng.open_orders, [])
        self.assertEqual(eng.closed_orders, [])

    def test_prune_seek_reopens_manual_close(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        eng.place("Up", 10.0, 200, tick, book, 0.02)
        eng.close(eng.open_orders[0]["id"], 150, tick, book, 0.02)
        self.assertEqual(len(eng.open_orders), 0)
        eng.prune_seek(180)
        self.assertEqual(len(eng.open_orders), 1)
        self.assertEqual(len(eng.closed_orders), 0)

    def test_prune_seek_forward_keeps_open_order(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        eng.place("Up", 10.0, 200, tick, book, 0.02)
        eng.prune_seek(100)
        self.assertEqual(len(eng.open_orders), 1)

    def test_prune_seek_backward_removes_future_order(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        eng.place("Up", 10.0, 200, tick, book, 0.02)
        eng.prune_seek(250)
        self.assertEqual(len(eng.open_orders), 0)

    def test_visible_history_hides_active_until_settled(self):
        runs = [{"market_start_ts": 100, "run_id": "a", "orders": []}]
        hidden = visible_history(runs, active_market_start_ts=100, round_settled=False)
        self.assertEqual(hidden, [])
        shown = visible_history(runs, active_market_start_ts=100, round_settled=True)
        self.assertEqual(len(shown), 1)

    def test_write_run_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_run(Path(td), 12345, {"market_start_ts": 12345, "orders": [], "outcome": "Up"})
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("Up", path.name)
            self.assertEqual(data["outcome"], "Up")

    def test_order_rows_quotes_and_payout(self):
        orders = [
            {
                "side": "Up", "size_usd": 10.0, "entry_sec": 200, "exit_sec": 50,
                "best_ask_c": 67, "exit_price": 0.79, "payout_if_win_usd": 14.5, "profit_if_win_usd": 4.5,
                "pnl_usd": 2.1, "result": "closed", "close_type": "manual",
            },
            {
                "side": "Down", "size_usd": 20.0, "entry_sec": 180, "exit_sec": 0,
                "best_ask_c": 55, "exit_price": 1.0, "payout_if_win_usd": 36.0, "profit_if_win_usd": 16.0,
                "pnl_usd": 16.0, "result": "won", "close_type": "settlement",
            },
            {
                "side": "Up", "size_usd": 15.0, "entry_sec": 150, "exit_sec": 0,
                "best_ask_c": 40, "exit_price": 0.0, "payout_if_win_usd": 37.5, "profit_if_win_usd": 22.5,
                "pnl_usd": -15.0, "result": "lost", "close_type": "settlement",
            },
        ]
        rows = order_rows_for_run(12345, orders, "run1", "Down")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["entry_quote_c"], 67)
        self.assertEqual(rows[0]["exit_quote_c"], 79)
        self.assertEqual(rows[0]["payout_usd"], 0.0)
        self.assertEqual(rows[0]["final_pnl_usd"], -10.0)
        self.assertEqual(rows[1]["exit_quote_c"], 100)
        self.assertEqual(rows[1]["payout_usd"], 36.0)
        self.assertEqual(rows[1]["final_pnl_usd"], 16.0)
        self.assertEqual(rows[1]["pnl_usd"], 16.0)
        self.assertEqual(rows[2]["exit_quote_c"], 0)
        self.assertEqual(rows[2]["payout_usd"], 0.0)
        self.assertEqual(rows[2]["final_pnl_usd"], -15.0)
        self.assertEqual(rows[2]["pnl_usd"], -15.0)
        self.assertEqual(rows[0]["outcome"], "Down")

    def test_order_rows_without_outcome(self):
        orders = [{
            "side": "Up", "size_usd": 10.0, "entry_sec": 200, "exit_sec": 120,
            "best_ask_c": 67, "exit_price": 0.79, "payout_if_win_usd": 14.5, "profit_if_win_usd": 4.5,
            "pnl_usd": 2.1, "result": "closed", "close_type": "manual",
        }]
        rows = order_rows_for_run(12345, orders, "run1")
        self.assertIsNone(rows[0]["outcome"])
        self.assertIsNone(rows[0]["payout_usd"])
        self.assertIsNone(rows[0]["final_pnl_usd"])
