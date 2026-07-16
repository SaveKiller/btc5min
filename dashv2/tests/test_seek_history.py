"""Test seek timeline, account history, anti-spoiler."""

import json
import tempfile
import unittest
from pathlib import Path

from dashv2.history import (
    account_summary, append_settled_orders, compute_stats, create_account, list_accounts,
    load_account, order_rows_for_run, order_rows_from_ledger, rename_account, update_account,
    visible_orders,
)
from dashv2.orders import OrderEngine
from src.book import BookSnapshot

ACCOUNT_ID = "testacct0001"


def _book(up_ask=0.55, down_ask=0.45):
    return BookSnapshot(
        [(up_ask - 0.02, 1000)], [(up_ask, 1000)], [(down_ask - 0.02, 1000)], [(down_ask, 1000)],
        up_ask - 0.02, up_ask, down_ask - 0.02, down_ask)


class TestSeekAndHistory(unittest.TestCase):
    def test_cancel_removes_open_without_history(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        order = eng.place("Up", 10.0, 200, tick, book, 0.02, ACCOUNT_ID, "user")
        eng.cancel(order["id"])
        self.assertEqual(eng.open_orders, [])
        self.assertEqual(eng.closed_orders, [])

    def test_prune_seek_reopens_manual_close(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        eng.place("Up", 10.0, 200, tick, book, 0.02, ACCOUNT_ID, "user")
        eng.close(eng.open_orders[0]["id"], 150, tick, book, 0.02)
        self.assertEqual(len(eng.open_orders), 0)
        eng.prune_seek(180)
        self.assertEqual(len(eng.open_orders), 1)
        self.assertEqual(len(eng.closed_orders), 0)

    def test_prune_seek_forward_keeps_open_order(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        eng.place("Up", 10.0, 200, tick, book, 0.02, ACCOUNT_ID, "user")
        eng.prune_seek(100)
        self.assertEqual(len(eng.open_orders), 1)

    def test_prune_seek_backward_removes_future_order(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        eng.place("Up", 10.0, 200, tick, book, 0.02, ACCOUNT_ID, "user")
        eng.prune_seek(250)
        self.assertEqual(len(eng.open_orders), 0)

    def test_visible_orders_hides_active_until_settled(self):
        orders = [{"market_start_ts": 100, "close_type": "settlement", "side": "Up", "size_usd": 10, "entry_sec": 200, "pnl_usd": 5}]
        hidden = visible_orders(orders, active_market_start_ts=100, round_settled=False)
        self.assertEqual(hidden, [])
        shown = visible_orders(orders, active_market_start_ts=100, round_settled=True)
        self.assertEqual(len(shown), 1)

    def test_create_account_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = create_account(root, "Main", 10000.0, "note")
            path = root / f"account_{data['id']}.json"
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["name"], "Main")
            self.assertEqual(loaded["initial_balance_usd"], 10000.0)
            self.assertEqual(loaded["note"], "note")

    def test_append_orders_and_stats(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = create_account(root, "Main", 1000.0, "")
            aid = data["id"]
            orders = [{
                "side": "Up", "size_usd": 100.0, "entry_sec": 200, "exit_sec": 0,
                "best_ask_c": 55, "exit_price": 1.0, "payout_if_win_usd": 180.0, "profit_if_win_usd": 80.0,
                "pnl_usd": 80.0, "result": "won", "close_type": "settlement",
            }]
            append_settled_orders(root, aid, 12345, "sess1", "2026-07-15T13:35:00Z", "Up", orders, "replay")
            loaded = load_account(root, aid)
            stats = compute_stats(loaded)
            self.assertEqual(stats["wins"], 1)
            self.assertEqual(stats["current_balance_usd"], 1080.0)
            self.assertEqual(stats["gain_pct"], 8.0)
            self.assertEqual(loaded["orders"][0]["session_id"], "sess1")
            self.assertEqual(loaded["orders"][0]["session_started_at_utc"], "2026-07-15T13:35:00Z")

    def test_rename_and_update_account(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = create_account(root, "A", 500.0, "old")
            aid = data["id"]
            rename_account(root, aid, "B")
            updated = update_account(root, aid, "B2", 750.0, "new")
            self.assertEqual(updated["name"], "B2")
            self.assertEqual(updated["initial_balance_usd"], 750.0)
            self.assertEqual(updated["note"], "new")
            summaries = list_accounts(root)
            self.assertEqual(summaries[0]["name"], "B2")

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
        rows = order_rows_for_run(12345, orders, "sess1", "2026-07-15T13:35:00Z", "Down")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["session_id"], "sess1")
        self.assertEqual(rows[0]["session_date_utc"], "15/07")
        self.assertEqual(rows[0]["session_time_utc"], "13:35")
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
        rows = order_rows_for_run(12345, orders, "sess1", "2026-07-15T13:35:00Z")
        self.assertIsNone(rows[0]["outcome"])
        self.assertEqual(rows[0]["session_id"], "sess1")
        self.assertIsNone(rows[0]["payout_usd"])
        self.assertIsNone(rows[0]["final_pnl_usd"])

    def test_account_summary_includes_stats(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = create_account(root, "Stats", 2000.0, "x")
            summary = account_summary(data)
            self.assertEqual(summary["current_balance_usd"], 2000.0)
            self.assertEqual(summary["order_count"], 0)

    def test_order_rows_from_ledger_sort_by_session(self):
        ledger = [
            {
                "market_start_ts": 200, "close_type": "settlement", "side": "Up", "size_usd": 10,
                "entry_sec": 50, "pnl_usd": 1, "outcome": "Up", "session_id": "old",
                "session_started_at_utc": "2026-07-14T10:00:00Z",
                "payout_if_win_usd": 18.0, "profit_if_win_usd": 8.0,
            },
            {
                "market_start_ts": 100, "close_type": "manual", "side": "Down", "size_usd": 20,
                "entry_sec": 80, "exit_sec": 40, "pnl_usd": -2, "outcome": None, "session_id": "new",
                "session_started_at_utc": "2026-07-15T10:00:00Z",
                "payout_if_win_usd": 36.0, "profit_if_win_usd": 16.0,
            },
        ]
        rows = order_rows_from_ledger(ledger)
        self.assertEqual(rows[0]["session_id"], "new")
        self.assertEqual(rows[1]["session_id"], "old")

    def test_order_rows_legacy_run_id(self):
        ledger = [{
            "market_start_ts": 100, "close_type": "settlement", "side": "Up", "size_usd": 10,
            "entry_sec": 50, "pnl_usd": 1, "outcome": "Up", "run_id": "legacy1",
            "payout_if_win_usd": 18.0, "profit_if_win_usd": 8.0,
        }]
        rows = order_rows_from_ledger(ledger)
        self.assertEqual(rows[0]["session_id"], "legacy1")

    def test_mtm_settlement_estimate_when_no_bid_liquidity(self):
        eng = OrderEngine(100, 100)
        tick = {
            "chainlink_btc": 90000.0, "partial": False, "gap": False,
            "up_bid": 0.98, "up_ask": 0.99, "down_bid": 0.01, "down_ask": 0.02,
            "majority_side": "Up",
        }
        book = BookSnapshot([], [(0.99, 1000)], [], [(0.02, 1000)], 0.98, 0.99, 0.01, 0.02)
        order = eng.place("Up", 100.0, 120, tick, book, 0.02, ACCOUNT_ID, "user")
        eng.revalue_mtm(100, tick, book, 0.02)
        self.assertFalse(eng.open_orders[0]["mtm_available"])
        self.assertAlmostEqual(eng.open_orders[0]["mtm_usd"], order["profit_if_win_usd"])
        eng.open_orders[0]["side"] = "Down"
        eng.revalue_mtm(100, tick, book, 0.02)
        self.assertAlmostEqual(eng.open_orders[0]["mtm_usd"], -100.0)
