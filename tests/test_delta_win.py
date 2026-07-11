"""Test delta_win v2: estrazione, predizione A/B, renderer e backfill."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.delta_win import (
    delta_win_a_column_width, format_delta_win_a_cell, format_delta_win_b_cell, load_delta_win_artifact,
    parse_delta_txt, parse_quote_side, predict_delta_win_a, predict_delta_win_b,
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

    def test_format_cells(self):
        self.assertEqual(format_delta_win_b_cell(0.876), "88%")
        self.assertEqual(format_delta_win_b_cell(None), "---")
        self.assertEqual(format_delta_win_a_cell(0.876, 12, 26), "88% [12$-26$]")
        self.assertEqual(format_delta_win_a_cell(0.5, 0, 0), "50% [0$]")
        self.assertEqual(delta_win_a_column_width(), 15)
        art = load_delta_win_artifact()
        mx = 0
        for sec_key, bands in art["bands_by_sec"].items():
            for b in bands:
                cell = format_delta_win_a_cell(float(b["p_win"]), int(b["lo"]), int(b["hi"]))
                mx = max(mx, len(cell))
        self.assertLessEqual(mx, delta_win_a_column_width())

    def test_artifact_load_and_predict_ab(self):
        art = load_delta_win_artifact()
        vols_low = {w: 10 for w in VOLATILITY_WINDOWS_SEC}
        vols_high = {w: 80 for w in VOLATILITY_WINDOWS_SEC}
        for sec in DELTA_WIN_CHECKPOINTS:
            pa_lo = predict_delta_win_a(sec, 5, art)
            pa_hi = predict_delta_win_a(sec, 200, art)
            pb_lo = predict_delta_win_b(sec, 5, vols_low, 1, art)
            pb_hi = predict_delta_win_b(sec, 5, vols_high, 6, art)
            for p in (pa_lo, pa_hi, pb_lo, pb_hi):
                self.assertIsNotNone(p)
                self.assertGreaterEqual(p, 0.0)
                self.assertLessEqual(p, 1.0)
            self.assertGreaterEqual(pa_hi, pa_lo)

    def test_renderer_dual_columns_before_btc(self):
        art = load_delta_win_artifact()
        header = {
            "market_start_ts": 1783238400, "market_end_ts": 1783238700, "intraday_h": 2,
            "ptb_price": 100000.0, "ptb_chainlink": 100000.0, "ptb_gamma": 100000.0,
            "final_price": 100010.0, "final_chainlink": 100010.0, "final_gamma": 100010.0,
            "outcome_lighter": "Up", "outcome": 1, "outcome_agreement": True,
            "delta_lighter": 10.0, "delta_chainlink": 10.0, "move_error": 0.0, "tick_count": 300,
        }
        txt = render_lighter_round_txt(header, _synthetic_ticks(), [], art)
        header_line = next(l for l in txt.splitlines() if l.startswith("sec"))
        btc_i = header_line.index("btc")
        self.assertIn("DWinA", header_line)
        self.assertIn("DWinB", header_line)
        dwa_i = header_line.index("DWinA")
        self.assertLess(dwa_i, btc_i)
        row90 = next(l for l in txt.splitlines() if l.split() and l.split()[0] == "90")
        parts = row90.split()
        btc_i_row = next(i for i, p in enumerate(parts) if p.endswith("$") and p[:-1].isdigit())
        self.assertIn("%", parts[btc_i_row - 1])
        row299 = next(l for l in txt.splitlines() if l.split() and l.split()[0] == "299")
        btc_pos = row299.index("100000$")
        dw_slice = row299[row299.index("0$") + 2:btc_pos]
        self.assertNotIn("%", dw_slice)
        self.assertNotIn("[", dw_slice)

    def test_dw_block_width_and_alignment(self):
        from src.binary_format import read_round
        from src.delta_win import delta_win_block_width, delta_win_data_header, delta_win_row_part, load_delta_win_artifact
        from src.txt_format import render_round_txt
        art = load_delta_win_artifact()
        vols = {w: 20 for w in VOLATILITY_WINDOWS_SEC}
        blk = delta_win_block_width()
        self.assertEqual(len(delta_win_data_header()), blk)
        self.assertEqual(len(delta_win_row_part(90, 50, vols, 2, True, art)), blk)
        self.assertEqual(len(delta_win_row_part(299, 0, vols, 2, False, art)), blk)
        path = Path("data/2026-07-09/bin/btc5m_1783558200_0050.bin")
        if not path.is_file():
            self.skipTest("sample bin not present")
        header, ticks, _ = read_round(str(path))
        txt = render_round_txt(header, ticks, [])
        col_hdr = next(l for l in txt.splitlines() if l.startswith("sec"))
        vol_i = col_hdr.index("V30")
        btc_start = vol_i - 10
        data_lines = [l for l in txt.splitlines() if l.split() and l.split()[0].isdigit()]
        for line in data_lines:
            self.assertEqual(len(line[btc_start:btc_start + 8]), 8)
            self.assertEqual(line[btc_start + 8:vol_i], "  ")
            self.assertEqual(len(line[btc_start - 2 - blk:btc_start - 2]), blk)

    def test_renderer_real_txt_dual_columns(self):
        from src.binary_format import read_round
        from src.txt_format import render_round_txt
        path = Path("data/2026-07-09/bin/btc5m_1783558200_0050.bin")
        if not path.is_file():
            self.skipTest("sample bin not present")
        header, ticks, _ = read_round(str(path))
        txt = render_round_txt(header, ticks, [])
        header_line = next(l for l in txt.splitlines() if l.startswith("sec"))
        self.assertIn("DWinA", header_line)
        self.assertIn("DWinB", header_line)
        self.assertLess(header_line.index("DWinA"), header_line.index("btc"))
        row90 = next(l for l in txt.splitlines() if l.split() and l.split()[0] == "90")
        self.assertIn("[", row90)
        self.assertIn("%", row90)
        import re
        gap = re.search(r"(\d+\.\d%|  ---)( *)(\d+% \[)", row90)
        self.assertIsNotNone(gap)
        self.assertEqual(len(gap.group(2)), 2)

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
        from scripts.eval_delta_win_v2_compare import collect_real_samples
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
        self.assertIn("p_a", samples[0])
        self.assertIn("p_b", samples[0])

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
