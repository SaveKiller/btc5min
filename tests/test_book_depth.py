"""Truncate book depth allo snapshot: counts ≤ N, BBO invariato."""
import unittest
from unittest.mock import MagicMock

from src.book import OrderBook, truncate_side
from src.feed_clob import snapshot_books
from src.setup import BOOK_DEPTH


class TestBookDepth(unittest.TestCase):
    def test_truncate_side(self):
        levels = [(0.50 - i * 0.01, 10.0) for i in range(12)]
        out = truncate_side(levels, 8)
        self.assertEqual(len(out), 8)
        self.assertEqual(out[0], levels[0])
        self.assertEqual(out[-1], levels[7])

    def test_snapshot_truncates_and_keeps_bbo(self):
        self.assertEqual(BOOK_DEPTH, 8)
        up = OrderBook()
        down = OrderBook()
        up.bids = [(0.60 - i * 0.01, float(i + 1)) for i in range(15)]
        up.asks = [(0.61 + i * 0.01, float(i + 1)) for i in range(15)]
        down.bids = [(0.39 - i * 0.01, float(i + 1)) for i in range(12)]
        down.asks = [(0.40 + i * 0.01, float(i + 1)) for i in range(12)]
        state = MagicMock()
        state.lock = MagicMock()
        state.lock.__enter__ = MagicMock(return_value=None)
        state.lock.__exit__ = MagicMock(return_value=False)
        state.up_book = up
        state.down_book = down
        state.chainlink_price = 100000.0
        state.chainlink_recv_ms = 1
        state.ptb_gamma = None
        state.ptb_chainlink = 99900.0
        snap, cl, ptb, cl_recv = snapshot_books(state)
        self.assertEqual(cl, 100000.0)
        self.assertLessEqual(len(snap.up_bids), BOOK_DEPTH)
        self.assertLessEqual(len(snap.up_asks), BOOK_DEPTH)
        self.assertLessEqual(len(snap.down_bids), BOOK_DEPTH)
        self.assertLessEqual(len(snap.down_asks), BOOK_DEPTH)
        self.assertEqual(len(snap.up_bids), BOOK_DEPTH)
        self.assertEqual(len(snap.up_asks), BOOK_DEPTH)
        self.assertEqual(snap.up_bid, up.bids[0][0])
        self.assertEqual(snap.up_ask, up.asks[0][0])
        self.assertEqual(snap.down_bid, down.bids[0][0])
        self.assertEqual(snap.down_ask, down.asks[0][0])
        self.assertEqual(snap.up_bids[0][0], snap.up_bid)
        self.assertEqual(snap.up_asks[0][0], snap.up_ask)


if __name__ == "__main__":
    unittest.main()
