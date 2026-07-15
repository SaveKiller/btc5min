"""Rq/Rs per lato nel payload tick della dashboard."""

import unittest

from dashv2.engine import _public_tick


def _tick(**kw):
    base = {
        "chainlink_btc": 90000.0, "chainlink_stale": False, "delta_usd": -50,
        "dwin_a": {"p_win": 0.29, "n": 409}, "dwin_b_pct": 28,
        "partial": False, "gap": False, "up_mid_c": 12, "down_mid_c": 89,
        "up_ask": 0.12, "down_ask": 0.89, "majority_side": "Down",
        "vol": {}, "side_risk": {
            "Up": {"rq": 8, "rs": 7},
            "Down": {"rq": 3, "rs": 1},
        },
    }
    base.update(kw)
    return base


class TestSideRiskPublic(unittest.TestCase):
    def test_per_side_risk_in_tick(self):
        pub = _public_tick(_tick(), 200, 1, False)
        self.assertEqual(pub["risk"]["Up"]["rq"], 8)
        self.assertEqual(pub["risk"]["Up"]["rs"], 7)
        self.assertEqual(pub["risk"]["Down"]["rq"], 3)
        self.assertEqual(pub["risk"]["Down"]["rs"], 1)

    def test_gap_clears_side_risk(self):
        pub = _public_tick(None, 200, 1, True)
        self.assertIsNone(pub["risk"]["Up"]["rq"])
        self.assertIsNone(pub["risk"]["Down"]["rs"])


if __name__ == "__main__":
    unittest.main()
