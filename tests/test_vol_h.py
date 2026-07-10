import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from src.lighter_ticks import _HOUR_BANDS_PATH, _hour_bands_cache, hour_band, load_hour_bands, utc_dow_hour
from src.vol_h import (
    HOLDOUT_WEEKS, K_MAX, K_MIN, MIN_CELLS_PER_H, MIN_INTERVAL_BY_PROFILE, TRAIN_WEEKS,
    bootstrap_stability, build_profile_sessions, cell_aggregates, night_peak_ok,
    segment_hours_dp, select_k, sessions_to_lookup, split_train_holdout,
)


def _ts_for_dow_hour(dow: int, hour: int) -> int:
    base = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
    dt = base + timedelta(days=dow, hours=hour)
    got_dow, got_hour = dt.weekday(), dt.hour
    if got_dow != dow or got_hour != hour:
        raise Exception(f"bad ts helper dow={dow} hour={hour} got {got_dow},{got_hour}")
    return int(dt.timestamp())


def _synthetic_windows() -> list[dict]:
    """11 settimane, RV300 dipende da profilo/ora (notte bassa, picco alto)."""
    windows = []
    wid = 0
    for week in range(11):
        for dow in range(7):
            for hour in range(24):
                for _ in range(12):
                    base = 30.0
                    if dow <= 3:
                        if 3 <= hour <= 8:
                            base = 35.0 + hour
                        elif 13 <= hour <= 16:
                            base = 90.0 + hour * 2
                        elif 9 <= hour <= 12:
                            base = 55.0 + hour
                        else:
                            base = 45.0 + hour * 0.5
                    elif dow == 4:
                        base = 50.0 + hour
                    elif dow == 5:
                        base = 32.0 + hour * 0.3
                    else:
                        base = 30.0 + hour * 0.2
                    windows.append({
                        "start_ts": 1_700_000_000 + wid,
                        "dow": dow,
                        "hour": hour,
                        "week_idx": week,
                        "rv300": base + np.random.default_rng(wid).normal(0, 2),
                        "v60_med": base * 0.35,
                    })
                    wid += 1
    return windows


class VolHTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        np.random.seed(42)
        cls.windows = _synthetic_windows()

    def test_temporal_split_no_leakage(self):
        train, holdout, weeks = split_train_holdout(self.windows)
        train_w = {w["week_idx"] for w in train}
        hold_w = {w["week_idx"] for w in holdout}
        self.assertEqual(len(train_w), TRAIN_WEEKS)
        self.assertEqual(len(hold_w), HOLDOUT_WEEKS)
        self.assertTrue(train_w.isdisjoint(hold_w))
        self.assertEqual(min(hold_w), weeks[TRAIN_WEEKS])

    def test_segment_min_interval(self):
        med = np.array([10.0 + h * 3 for h in range(24)])
        br = segment_hours_dp(med, 4, MIN_INTERVAL_BY_PROFILE["mon_thu"])
        for i in range(len(br) - 1):
            self.assertGreaterEqual(br[i + 1] - br[i], MIN_INTERVAL_BY_PROFILE["mon_thu"])

    def test_night_peak_separation(self):
        train, holdout, _ = split_train_holdout(self.windows)
        cells = cell_aggregates(train)
        sessions, _ = build_profile_sessions(cells)
        sel = select_k(cells, sessions, holdout)
        lookup = sel["chosen"]["lookup"]
        self.assertTrue(night_peak_ok(lookup))
        night = {lookup[str(d)][str(h)] for d in range(4) for h in range(3, 9)}
        peak = {lookup[str(d)][str(h)] for d in range(4) for h in range(13, 17)}
        self.assertNotEqual(night, peak)

    def test_k_range_and_coverage(self):
        train, holdout, _ = split_train_holdout(self.windows)
        cells = cell_aggregates(train)
        sessions, _ = build_profile_sessions(cells)
        sel = select_k(cells, sessions, holdout)
        k = sel["chosen"]["k"]
        lookup = sel["chosen"]["lookup"]
        self.assertGreaterEqual(k, K_MIN)
        self.assertLessEqual(k, K_MAX)
        assigned = sum(1 for d in range(7) for h in range(24))
        self.assertEqual(assigned, 168)
        for d in range(7):
            for h in range(24):
                self.assertIn(str(h), lookup[str(d)])

    def test_min_cells_per_h(self):
        train, holdout, _ = split_train_holdout(self.windows)
        cells = cell_aggregates(train)
        sessions, _ = build_profile_sessions(cells)
        sel = select_k(cells, sessions, holdout)
        lookup, h_meta, k_eff = sessions_to_lookup(sessions, cells, sel["chosen"]["k"])
        for h in range(1, k_eff + 1):
            self.assertGreaterEqual(h_meta[h]["n_cells"], MIN_CELLS_PER_H)

    def test_determinism(self):
        train, holdout, _ = split_train_holdout(self.windows)
        cells = cell_aggregates(train)
        sessions, _ = build_profile_sessions(cells)
        a = select_k(cells, sessions, holdout)["chosen"]["lookup"]
        b = select_k(cells, sessions, holdout)["chosen"]["lookup"]
        self.assertEqual(a, b)

    def test_holdout_monotone_medians(self):
        train, holdout, _ = split_train_holdout(self.windows)
        cells = cell_aggregates(train)
        sessions, _ = build_profile_sessions(cells)
        chosen = select_k(cells, sessions, holdout)["chosen"]
        meds = [chosen["holdout_h_medians"][str(h)] for h in sorted(int(x) for x in chosen["holdout_h_medians"])]
        self.assertTrue(all(meds[i] <= meds[i + 1] for i in range(len(meds) - 1)))

    def test_hour_band_reads_canonical_map(self):
        train, holdout, _ = split_train_holdout(self.windows)
        cells = cell_aggregates(train)
        sessions, _ = build_profile_sessions(cells)
        chosen = select_k(cells, sessions, holdout)["chosen"]
        payload = {"method_version": "test", "k": chosen["k"], "lookup": chosen["lookup"]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(payload, f)
            tmp = Path(f.name)
        orig = _HOUR_BANDS_PATH
        orig_cache = _hour_bands_cache
        try:
            import src.lighter_ticks as lt
            lt._HOUR_BANDS_PATH = tmp
            lt._hour_bands_cache = None
            for d in range(7):
                for h in range(24):
                    ts = _ts_for_dow_hour(d, h)
                    self.assertEqual(hour_band(ts), chosen["lookup"][str(d)][str(h)])
        finally:
            lt._HOUR_BANDS_PATH = orig
            lt._hour_bands_cache = orig_cache
            tmp.unlink(missing_ok=True)

    def test_canonical_hour_bands_file(self):
        if not _HOUR_BANDS_PATH.is_file():
            self.skipTest("hour_bands.json not generated yet")
        import src.lighter_ticks as lt
        lt._hour_bands_cache = None
        data = load_hour_bands()
        k = data["k"]
        self.assertGreaterEqual(k, K_MIN)
        self.assertLessEqual(k, K_MAX)
        for d in range(7):
            for h in range(24):
                ts = _ts_for_dow_hour(d, h)
                hb = hour_band(ts)
                self.assertEqual(hb, int(data["lookup"][str(d)][str(h)]))
                self.assertGreaterEqual(hb, 1)
                self.assertLessEqual(hb, k)
        lt._hour_bands_cache = None
        import src.lighter_ticks as lt
        orig = lt._HOUR_BANDS_PATH
        lt._HOUR_BANDS_PATH = Path("__missing_hour_bands__.json")
        lt._hour_bands_cache = None
        try:
            with self.assertRaises(Exception):
                hour_band(1_780_000_000)
        finally:
            lt._HOUR_BANDS_PATH = orig
            lt._hour_bands_cache = None


if __name__ == "__main__":
    unittest.main()
