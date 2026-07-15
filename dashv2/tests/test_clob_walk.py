"""Test walk CLOB BUY/SELL e regressione market_buy_gain."""

import unittest

from src.clob_api import BET_USD, market_buy_gain, market_buy_walk, market_sell_walk


class TestClobWalk(unittest.TestCase):
    def test_buy_walk_all_or_nothing(self):
        asks = [(0.50, 10.0), (0.55, 10.0)]
        walk = market_buy_walk(asks, 5.0, 0.02)
        self.assertGreater(walk["shares"], 0)
        with self.assertRaises(Exception):
            market_buy_walk(asks, 5000.0, 0.02)

    def test_sell_walk(self):
        bids = [(0.60, 5.0), (0.55, 20.0)]
        sell = market_sell_walk(bids, 3.0, 0.02)
        self.assertAlmostEqual(sell["shares_sold"], 3.0, places=4)
        with self.assertRaises(Exception):
            market_sell_walk(bids, 100.0, 0.02)

    def test_market_buy_gain_unchanged(self):
        asks = [(0.40, 100.0), (0.45, 100.0)]
        roi = market_buy_gain(asks, BET_USD, 0.02)
        self.assertGreater(roi, 0)
