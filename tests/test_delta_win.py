"""Test delta_win: estrazione, predizione, renderer e backfill."""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.delta_win import (
    format_delta_win_cell, load_delta_win_artifact, parse_delta_txt, parse_quote_side,
    predict_delta_win,
)
from src.clob_api import side_from_chainlink
from src.settlement import outcome_from_prices
from src.lighter_txt_format import render_lighter_round_txt
from src.listats import li_checkpoint_samples, read_lighter_data_rows
from src.setup import DELTA_WIN_CHECKPOINTS, VOLATILITY_WINDOWS_SEC


def _synthetic_ticks() -> np.ndarray:
    rows = []
    for sec in range(300, 0, -1):
        recv = 1_700_000_000_000 + (300 - sec) * 1000
        mid = 100_000.0 + (300 - sec) * 0.5
        rows.append([recv, float(sec), np.nan, np.nan, np.nan, np.nan, mid, np.nan, recv - 100])
    return np.array(rows, dtype=np.float64)


class DeltaWinTests(unittest.TestCase):
    def test_parse_delta_zero(self):
        self.assertEqual(parse_delta_txt("0$"), 0)
        self.assertEqual(parse_delta_txt("+0$"), 0)
        self.assertIsNone(parse_delta_txt("---"))

    def test_quote_side(self):
        self.assertEqual(parse_quote_side("UP"), "Up")
        self.assertEqual(parse_quote_side("DOWN"), "Down")

    def test_artifact_load_and_predict(self):
        art = load_delta_win_artifact()
        vols = {w: 20 for w in VOLATILITY_WINDOWS_SEC}
        for sec in DELTA_WIN_CHECKPOINTS:
            p = predict_delta_win(sec, 50, vols, 3, art)
            self.assertIsNotNone(p)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_renderer_checkpoint_column(self):
        art = load_delta_win_artifact()
        header = {
            "market_start_ts": 1783238400, "market_end_ts": 1783238700, "intraday_h": 2,
            "ptb_price": 100000.0, "ptb_chainlink": 100000.0, "ptb_gamma": 100000.0,
            "final_price": 100010.0, "final_chainlink": 100010.0, "final_gamma": 100010.0,
            "outcome_lighter": "Up", "outcome": 1, "outcome_agreement": True,
            "delta_lighter": 10.0, "delta_chainlink": 10.0, "move_error": 0.0, "tick_count": 300,
        }
        txt = render_lighter_round_txt(header, _synthetic_ticks(), [], art)
        self.assertIn("delta_win_model_version:", txt)
        data_section = txt.split("data:", 1)[1]
        header_line = next(l for l in data_section.splitlines() if l.startswith("sec"))
        self.assertIn("delta_win", header_line)
        for sec in DELTA_WIN_CHECKPOINTS:
            row = next(l for l in txt.splitlines() if l.startswith(f"{sec:>3}"))
            self.assertTrue(row.rstrip().endswith("%") or row.rstrip().endswith("---"))
        non_cp = next(l for l in txt.splitlines() if l.split() and l.split()[0] == "299")
        self.assertTrue(non_cp.rstrip().endswith("---"))

    def test_listats_excludes_agreement_nan(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "2615" / "btc5m_1783238400_0000.txt"
            p.parent.mkdir(parents=True)
            art = load_delta_win_artifact()
            header = {
                "market_start_ts": 1783238400, "market_end_ts": 1783238700, "intraday_h": 2,
                "ptb_price": 100000.0, "ptb_chainlink": 100000.0, "ptb_gamma": 100000.0,
                "final_price": 100010.0, "final_chainlink": 100010.0, "final_gamma": 100010.0,
                "outcome_lighter": "Up", "outcome": 1, "outcome_agreement": None,
                "delta_lighter": 10.0, "delta_chainlink": 10.0, "move_error": 0.0, "tick_count": 300,
            }
            p.write_text(render_lighter_round_txt(header, _synthetic_ticks(), [], art), encoding="utf-8")
            self.assertEqual(li_checkpoint_samples(p), [])

    def test_real_eval_label_side_outcome_same_type(self):
        side = side_from_chainlink(100_050.0, 100_000.0)
        outcome = outcome_from_prices(100_010.0, 100_000.0)
        self.assertEqual(side, "Up")
        self.assertEqual(outcome, "Up")
        self.assertEqual(1 if side == outcome else 0, 1)

    def test_real_eval_samples_if_data_present(self):
        from scripts.eval_delta_win_real import collect_real_samples
        from src.convert import iter_round_bin_paths
        data = Path("data")
        if not data.is_dir():
            self.skipTest("data/ not present")
        bins = iter_round_bin_paths(data)
        if not bins:
            self.skipTest("no bin files")
        art = load_delta_win_artifact()
        samples = collect_real_samples(bins[:5], art)
        if not samples:
            self.skipTest("no gamma-labeled samples in first 5 bins")
        self.assertGreater(sum(s["y_win"] for s in samples), 0)

        root = Path(r"H:/ticks/lighter-rounds5m")
        if not root.is_dir():
            self.skipTest("lighter dataset not mounted")
        sample = next(root.rglob("btc5m_*.txt"))
        recs = li_checkpoint_samples(sample)
        self.assertEqual(len(recs), 6)
        rows = read_lighter_data_rows(sample)
        self.assertEqual(len(rows), 300)


if __name__ == "__main__":
    unittest.main()
