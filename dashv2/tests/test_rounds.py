"""Test round repository: indice anti-spoiler, merge, gap."""

import unittest
from pathlib import Path

from dashv2.rounds import RoundRepository, sec_from_secs_to_expiry


class TestRounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data_dir = Path(__file__).resolve().parents[2] / "data"
        if not data_dir.is_dir():
            raise unittest.SkipTest("data/ not available")
        cls.repo = RoundRepository(data_dir, stall_reconnect_sec=15.0)

    def test_list_days(self):
        days = self.repo.list_days()
        if not days:
            self.skipTest("no rounds in data/")
        self.assertIn("day_utc", days[0])
        self.assertIn("count", days[0])
        self.assertGreater(days[0]["count"], 0)

    def test_picker_no_outcome(self):
        picker = self.repo.list_picker()
        if not picker:
            self.skipTest("no rounds in data/")
        for item in picker:
            self.assertIn("market_start_ts", item)
            self.assertIn("label", item)
            self.assertIn("valid", item)
            self.assertNotIn("outcome", item)
            self.assertNotIn("bin_path", item)

    def test_sec_mapping(self):
        self.assertEqual(sec_from_secs_to_expiry(240.4), 240)
        self.assertEqual(sec_from_secs_to_expiry(240.6), 241)

    def test_load_round(self):
        picker = [p for p in self.repo.list_picker() if p["valid"]]
        if not picker:
            self.skipTest("no valid rounds")
        loaded = self.repo.load(picker[0]["market_start_ts"])
        self.assertGreater(len(loaded.ticks_by_sec), 0)
        self.assertIn(loaded.outcome_name, ("Up", "Down", "unknown"))
