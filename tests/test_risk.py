import math
import unittest

import numpy as np

from src.binary_format import read_round
from src.risk import compute_risk_state, compute_side_risks, prob_to_r
from src.txt_format import format_risk_tokens
from src.setup import RISK_PROBABILITY_BUCKETS, RISK_PRIMARY_VOL_WINDOW_SEC
from src.vol_stats import compute_vol_stats_by_window, tick_sec


def _make_tick(sec: float, up_bid: float, up_ask: float, down_bid: float, down_ask: float,
        btc: float, recv_ms: int = 1_000_000, cl_recv_ms: int = 999_000) -> np.ndarray:
    return np.array([recv_ms, sec, up_bid, up_ask, down_bid, down_ask, btc, 0.1, cl_recv_ms], dtype=np.float64)


class RiskTests(unittest.TestCase):
    def test_prob_to_r_bucket_edges(self):
        self.assertEqual(prob_to_r(0.0), 1)
        self.assertEqual(prob_to_r(RISK_PROBABILITY_BUCKETS[0] - 1e-12), 1)
        self.assertEqual(prob_to_r(RISK_PROBABILITY_BUCKETS[0]), 2)
        self.assertEqual(prob_to_r(0.5), 9)
        self.assertEqual(prob_to_r(1.0), 9)

    def test_no_lookahead(self):
        path = "data/2026-07-09/bin/btc5m_1783558200_0050.bin"
        header, ticks, _ = read_round(path)
        ptb = header["ptb_chainlink"]
        base = compute_risk_state(ticks, ptb)
        mutated = ticks.copy()
        for i in range(ticks.shape[0]):
            if tick_sec(ticks[i]) < 120:
                mutated[i, 6] += 500.0
        after = compute_risk_state(mutated, ptb)
        for i in range(ticks.shape[0]):
            if tick_sec(ticks[i]) >= 180:
                self.assertEqual(base[i].Rq, after[i].Rq)
                self.assertEqual(base[i].Rs, after[i].Rs)

    def test_batch_matches_incremental(self):
        path = "data/2026-07-09/bin/btc5m_1783558200_0050.bin"
        header, ticks, _ = read_round(path)
        ptb = header["ptb_chainlink"]
        batch = compute_risk_state(ticks, ptb)
        for n in range(50, ticks.shape[0], 17):
            partial = compute_risk_state(ticks[:n], ptb)
            for i in range(n):
                self.assertEqual(batch[i].Rq, partial[i].Rq)
                self.assertEqual(batch[i].Rs, partial[i].Rs)

    def test_partial_tick(self):
        row = _make_tick(120.0, float("nan"), float("nan"), float("nan"), float("nan"), 62000.0)
        ticks = np.array([row])
        risk = compute_risk_state(ticks, 61900.0)[0]
        self.assertIsNone(risk.Rq)
        self.assertEqual(risk.rq_reason, "partial")
        self.assertIsNone(risk.Rs)
        self.assertEqual(risk.rs_reason, "partial")
        self.assertEqual(risk.eligible, "no")

    def test_tie_tick(self):
        row = _make_tick(120.0, 0.50, 0.50, 0.50, 0.50, 62000.0)
        ticks = np.array([row])
        risk = compute_risk_state(ticks, 61900.0)[0]
        self.assertIsNone(risk.Rq)
        self.assertEqual(risk.rq_reason, "tie")
        self.assertIsNone(risk.Rs)
        self.assertEqual(risk.rs_reason, "tie")

    def test_rs_stable_on_majority_flip(self):
        ptb = 64008.09
        btc = 64027.3
        down_row = _make_tick(65.0, 0.47, 0.48, 0.52, 0.53, btc)
        up_row = _make_tick(64.0, 0.57, 0.58, 0.42, 0.43, btc)
        ticks = np.array([down_row, up_row])
        risks = compute_risk_state(ticks, ptb)
        self.assertEqual(risks[0].side, "Down")
        self.assertEqual(risks[1].side, "Up")
        self.assertEqual(risks[0].Rs, risks[1].Rs)

    def test_side_risks_match_canonical_feed(self):
        path = "data/2026-07-09/bin/btc5m_1783558200_0050.bin"
        header, ticks, _ = read_round(path)
        ptb = header["ptb_chainlink"]
        canonical = compute_risk_state(ticks, ptb)
        per_side = compute_side_risks(ticks, ptb)
        from src.clob_api import side_from_chainlink
        for i in range(ticks.shape[0]):
            maj = canonical[i].side
            delta_side = side_from_chainlink(float(ticks[i, 6]), ptb)
            if maj is not None:
                self.assertEqual(per_side[i][maj]["rq"], canonical[i].Rq)
            self.assertEqual(per_side[i][delta_side]["rs"], canonical[i].Rs)

    def test_side_risks_minority_higher_rq(self):
        row = _make_tick(120.0, 0.40, 0.41, 0.58, 0.59, 62000.0)
        per_side = compute_side_risks(np.array([row]), 61900.0)[0]
        self.assertLess(per_side["Down"]["rq"], per_side["Up"]["rq"])

    def test_format_risk_tokens_spacing(self):
        path = "data/2026-07-09/bin/btc5m_1783558200_0050.bin"
        header, ticks, _ = read_round(path)
        risk = compute_risk_state(ticks, header["ptb_chainlink"])[100]
        tokens = format_risk_tokens(risk)
        self.assertIn("   Rs ", tokens)
        self.assertNotIn("=", tokens)
        row = _make_tick(120.0, float("nan"), float("nan"), float("nan"), float("nan"), 62000.0)
        partial = compute_risk_state(np.array([row]), 61900.0)[0]
        self.assertIn("Rs -", format_risk_tokens(partial))

    def test_vol_window_past_only(self):
        path = "data/2026-07-09/bin/btc5m_1783558200_0050.bin"
        _, ticks, _ = read_round(path)
        stats = compute_vol_stats_by_window(ticks, 15.0)
        w = RISK_PRIMARY_VOL_WINDOW_SEC
        sec300 = [i for i in range(ticks.shape[0]) if tick_sec(ticks[i]) == 300][0]
        sec240 = [i for i in range(ticks.shape[0]) if tick_sec(ticks[i]) == 240][0]
        self.assertTrue(math.isnan(stats[w]["vol_usd"][sec300]))
        self.assertFalse(math.isnan(stats[w]["vol_usd"][sec240]))


if __name__ == "__main__":
    unittest.main()
