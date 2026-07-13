"""Test delta_win v2: estrazione, predizione A/B, renderer e backfill."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.delta_win import (
    delta_win_a_column_width, delta_win_txt_matches_artifact, format_delta_win_a_cell, format_delta_win_b_cell, load_delta_win_artifact,
    lookup_delta_win_a_pool, parse_delta_txt, parse_quote_side, predict_delta_win_a, predict_delta_win_a_window, predict_delta_win_b,
    _format_delta_win_a_from_pool, _DW_A_PCT_W,
)
from src.delta_win_bands import (
    DELTA_LOOKUP_MAX, clamp_delta, fit_window_for_sec_h, pool_in_range, window_bounds,
)
from src.clob_api import side_from_chainlink
from src.settlement import outcome_from_prices
from src.lighter_txt_format import render_lighter_round_txt
from src.listats import li_delta_win_samples, read_lighter_data_rows
from src.setup import DELTA_WIN_SEC_END, DELTA_WIN_SEC_START, DELTA_WIN_SECS, VOLATILITY_WINDOWS_SEC


def _synthetic_ticks() -> np.ndarray:
    rows = []
    for sec in range(300, 0, -1):
        recv = 1_700_000_000_000 + (300 - sec) * 1000
        mid = 100_000.0 + (300 - sec) * 0.5
        rows.append([recv, float(sec), np.nan, np.nan, np.nan, np.nan, mid, np.nan, recv - 100])
    return np.array(rows, dtype=np.float64)


class DeltaWinTests(unittest.TestCase):
    def test_window_bounds(self):
        self.assertEqual(window_bounds(0), (0, 2))
        self.assertEqual(window_bounds(1), (0, 3))
        self.assertEqual(window_bounds(33), (31, 35))
        self.assertEqual(window_bounds(150), (148, 150))
        self.assertEqual(window_bounds(clamp_delta(180)), (148, 150))

    def test_pool_empirico_n(self):
        samples = [{"sec": 90, "abs_delta": 21, "y_win": 1, "intraday_h": 2} for _ in range(18)]
        samples += [{"sec": 90, "abs_delta": 21, "y_win": 0, "intraday_h": 2} for _ in range(12)]
        pool = pool_in_range(samples, 19, 23)
        self.assertEqual(len(pool), 30)
        self.assertEqual(sum(s["y_win"] for s in pool), 18)
        table = fit_window_for_sec_h(samples, 90, 2, min_samples=30)
        slot = table["21"]
        self.assertAlmostEqual(slot["p_win"], 0.6)
        self.assertEqual(slot["n"], 30)
        self.assertEqual(slot["lo"], 19)
        self.assertEqual(slot["hi"], 23)

    def test_min_samples_no_slot(self):
        samples = [{"sec": 90, "abs_delta": 21, "y_win": 1, "intraday_h": 2} for _ in range(15)]
        table = fit_window_for_sec_h(samples, 90, 2, min_samples=30)
        self.assertIn("21", table)
        self.assertNotIn("p_win", table["21"])

    def test_sub_threshold_pool_without_pwin(self):
        samples = [{"sec": 90, "abs_delta": 21, "y_win": 1, "intraday_h": 2} for _ in range(20)]
        samples += [{"sec": 90, "abs_delta": 21, "y_win": 0, "intraday_h": 2} for _ in range(5)]
        table = fit_window_for_sec_h(samples, 90, 2, min_samples=30)
        slot = table["21"]
        self.assertEqual(slot["n"], 25)
        self.assertNotIn("p_win", slot)

    def test_sparse_no_percent(self):
        self.assertEqual(format_delta_win_a_cell(None, 29, sparse=True), "    [n=29*]")
        art = load_delta_win_artifact()
        min_n = int(art["delta_win_window_min_samples"])
        for sec in DELTA_WIN_SECS:
            for d in range(0, 151):
                pool = lookup_delta_win_a_pool(sec, d, 2, art)
                if pool is None or pool.get("p_win") is not None:
                    continue
                if int(pool["n"]) >= min_n:
                    continue
                cell = _format_delta_win_a_from_pool(pool, art)
                self.assertNotIn("%", cell)
                self.assertIn("[n=", cell)
                self.assertTrue(cell.endswith("*]"))
                self.assertEqual(cell.index("["), _DW_A_PCT_W)
                return
        self.skipTest("no sub-threshold pool slot in artifact")

    def test_h_filter(self):
        samples = []
        for i in range(20):
            samples.append({"sec": 90, "abs_delta": 21, "y_win": 1, "intraday_h": 2})
        for i in range(20):
            samples.append({"sec": 90, "abs_delta": 21, "y_win": 0, "intraday_h": 6})
        table_h2 = fit_window_for_sec_h(samples, 90, 2, min_samples=20)
        table_h6 = fit_window_for_sec_h(samples, 90, 6, min_samples=20)
        self.assertEqual(table_h2["21"]["p_win"], 1.0)
        self.assertEqual(table_h6["21"]["p_win"], 0.0)

    def test_sec_h_index(self):
        from src.delta_win_bands import fit_window_for_bucket
        from src.delta_win_index import build_sec_h_index, sec_buckets
        samples = [
            {"sec": 90, "intraday_h": 2, "abs_delta": 21, "y_win": 1},
            {"sec": 90, "intraday_h": 2, "abs_delta": 22, "y_win": 0},
            {"sec": 91, "intraday_h": 3, "abs_delta": 21, "y_win": 1},
        ]
        idx = build_sec_h_index(samples)
        self.assertEqual(len(idx[(90, 2)]), 2)
        by_sec = sec_buckets(samples)
        self.assertEqual(len(by_sec[90]), 2)
        self.assertEqual(fit_window_for_bucket([], 90, 10), {})

    def test_secs_from_setup(self):
        self.assertGreater(DELTA_WIN_SEC_START, DELTA_WIN_SEC_END)
        self.assertEqual(DELTA_WIN_SECS[0], DELTA_WIN_SEC_END)
        self.assertEqual(DELTA_WIN_SECS[-1], DELTA_WIN_SEC_START)
        self.assertEqual(list(DELTA_WIN_SECS), list(range(DELTA_WIN_SEC_END, DELTA_WIN_SEC_START + 1)))

    def test_delta_win_txt_matches_artifact(self):
        art = load_delta_win_artifact()
        old_range = "  delta_win_sec_start: 180\n"
        new_lines = [
            "header:\n",
            f"  delta_win_model_version: {art['model_version']}\n",
            f"  delta_win_hour_bands_hash: {art['hour_bands_hash']}\n",
            f"  delta_win_band_stratify: {art['delta_win_band_stratify']}\n",
            f"  delta_win_lookup_max: {art['delta_lookup_max']}\n",
            f"  delta_win_window_half_base: {art['delta_win_window_half_base']}\n",
            f"  delta_win_window_min_samples: {art['delta_win_window_min_samples']}\n",
            old_range,
            "  delta_win_sec_end: 5\n",
            "data:\n",
        ]
        self.assertFalse(delta_win_txt_matches_artifact(new_lines, art))
        good_lines = [
            l if not l.startswith("  delta_win_sec_start:") else f"  delta_win_sec_start: {art['sec_start']}\n"
            for l in new_lines
        ]
        good_lines = [
            l if not l.startswith("  delta_win_sec_end:") else f"  delta_win_sec_end: {art['sec_end']}\n"
            for l in good_lines
        ]
        self.assertTrue(delta_win_txt_matches_artifact(good_lines, art))
        self.assertEqual(parse_delta_txt("0$"), 0)
        self.assertEqual(parse_delta_txt("+0$"), 0)
        self.assertIsNone(parse_delta_txt("---"))

    def test_quote_side(self):
        self.assertEqual(parse_quote_side("UP"), "Up")
        self.assertEqual(parse_quote_side("DOWN"), "Down")

    def test_format_cells(self):
        self.assertEqual(format_delta_win_b_cell(0.876), "88%")
        self.assertEqual(format_delta_win_b_cell(None), "---")
        self.assertEqual(format_delta_win_a_cell(0.876, 412), "88% [n=412]")
        self.assertEqual(format_delta_win_a_cell(None, 29, sparse=True), "    [n=29*]")
        self.assertEqual(format_delta_win_a_cell(0.5, 500), "50% [n=500]")
        self.assertEqual(format_delta_win_a_cell(0.99, 510), "99% [n=510]")
        self.assertEqual(format_delta_win_a_cell(1.0, 39), "100%[n=39]")
        self.assertEqual(format_delta_win_a_cell(None, 0), "---")
        self.assertEqual(delta_win_a_column_width(), 28)
        art = load_delta_win_artifact()
        mx = 0
        for h in range(1, 7):
            for sec in DELTA_WIN_SECS:
                for slot in art["delta_window_by_sec_h"][str(h)][str(sec)].values():
                    if "p_win" not in slot:
                        continue
                    cell = format_delta_win_a_cell(float(slot["p_win"]), int(slot["n"]))
                    mx = max(mx, len(cell))
        self.assertLessEqual(mx, delta_win_a_column_width())

    def test_artifact_load_and_predict_ab(self):
        art = load_delta_win_artifact()
        vols_low = {w: 10 for w in VOLATILITY_WINDOWS_SEC}
        vols_high = {w: 80 for w in VOLATILITY_WINDOWS_SEC}
        for sec in DELTA_WIN_SECS:
            pa_lo = predict_delta_win_a(sec, 5, 2, art)
            pa_hi = predict_delta_win_a(sec, 200, 2, art)
            pb_lo = predict_delta_win_b(sec, 5, vols_low, 1, art)
            pb_hi = predict_delta_win_b(sec, 5, vols_high, 6, art)
            for p in (pb_lo, pb_hi):
                self.assertIsNotNone(p)
                self.assertGreaterEqual(p, 0.0)
                self.assertLessEqual(p, 1.0)
            for p in (pa_lo, pa_hi):
                if p is not None:
                    self.assertGreaterEqual(p, 0.0)
                    self.assertLessEqual(p, 1.0)
            if pa_lo is not None and pa_hi is not None:
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
        self.assertIn("n=", row90)
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
        self.assertIn("n=", row90)
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
            self.assertEqual(li_delta_win_samples(p), [])

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
        self.assertIn("delta_window", samples[0])

        root = Path(r"H:/ticks/lighter-rounds5m")
        if not root.is_dir():
            self.skipTest("lighter dataset not mounted")
        sample = next(root.rglob("btc5m_*.txt"))
        recs = li_delta_win_samples(sample)
        self.assertEqual(len(recs), len(DELTA_WIN_SECS))
        rows = read_lighter_data_rows(sample)
        self.assertEqual(len(rows), 300)


if __name__ == "__main__":
    unittest.main()
