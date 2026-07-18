"""DWin dal txt: valori grezzi + lato riferimento (segno delta)."""

import unittest

from dashv2.engine import _public_tick


def _tick(**kw):
    base = {
        "chainlink_btc": 90000.0, "chainlink_stale": False, "delta_usd": -50,
        "dwin_a": {"p_win": 0.29, "n": 409}, "dwin_b_pct": 28,
        "partial": False, "gap": False, "up_mid_c": 12, "down_mid_c": 89,
        "up_ask": 0.12, "down_ask": 0.89, "up_bid": 0.11, "down_bid": 0.88, "majority_side": "Down",
        "vol": {}, "side_risk": {
            "Up": {"rq": 8, "rs": 7},
            "Down": {"rq": 3, "rs": 1},
        },
    }
    base.update(kw)
    return base


class TestDwinPublic(unittest.TestCase):
    def test_raw_from_txt_no_flip(self):
        pub = _public_tick(_tick(), 200, 1, False)
        self.assertEqual(pub["dwin_ref_side"], "Down")
        self.assertEqual(pub["dwin_a"]["p_win_pct"], 29)
        self.assertEqual(pub["dwin_b"]["p_win_pct"], 28)
        self.assertEqual(pub["up_bid_c"], 11)
        self.assertEqual(pub["down_bid_c"], 88)

    def test_ref_side_up_when_delta_positive(self):
        pub = _public_tick(_tick(delta_usd=12, majority_side="Up"), 200, 1, False)
        self.assertEqual(pub["dwin_ref_side"], "Up")

    def test_side_risk_passthrough(self):
        pub = _public_tick(_tick(), 200, 1, False)
        self.assertEqual(pub["risk"]["Down"]["rq"], 3)
        self.assertEqual(pub["risk"]["Up"]["rs"], 7)

    def test_gap_clears_dwin(self):
        pub = _public_tick(None, 200, 1, True)
        self.assertIsNone(pub["dwin_a"])
        self.assertIsNone(pub["dwin_ref_side"])
        self.assertIsNone(pub["liq2_ask_usd"])

    def test_liq2_caps_at_two_ask_levels(self):
        # 10 livelli; notional = sum(p*size) solo sui primi 2 (no fee)
        asks = [(0.50 + i * 0.01, 100.0) for i in range(10)]
        book = type("B", (), {"up_asks": [], "down_asks": asks})()
        pub = _public_tick(_tick(), 200, 1, False, book)
        expected = sum(p * s for p, s in asks[:2])
        self.assertAlmostEqual(pub["liq2_ask_usd"], expected)


if __name__ == "__main__":
    unittest.main()
