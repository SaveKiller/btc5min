"""Test seek timeline, history filter anti-spoiler."""

import json
import tempfile
import unittest
from pathlib import Path

from dashv2.history import visible_history, write_run
from dashv2.orders import OrderEngine
from src.book import BookSnapshot


def _book(up_ask=0.55, down_ask=0.45):
    return BookSnapshot(
        [(up_ask - 0.02, 1000)], [(up_ask, 1000)], [(down_ask - 0.02, 1000)], [(down_ask, 1000)],
        up_ask - 0.02, up_ask, down_ask - 0.02, down_ask)


class TestSeekAndHistory(unittest.TestCase):
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
