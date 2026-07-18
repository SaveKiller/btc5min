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
        self.assertIn("valid", days[0])
        # sequenza calendario continua tra min e max
        from datetime import datetime, timedelta, timezone
        first = datetime.strptime(days[-1]["day_utc"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        last = datetime.strptime(days[0]["day_utc"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        self.assertEqual(len(days), (last - first).days + 1)

    def test_picker_day_fills_missing_slots(self):
        days = [d for d in self.repo.list_days() if d["valid"]]
        if not days:
            self.skipTest("no rounds in data/")
        day = days[0]["day_utc"]
        picker = self.repo.list_picker_day(day)
        self.assertEqual(len(picker), 288)
        present = [r for r in picker if r["present"]]
        missing = [r for r in picker if not r["present"]]
        self.assertGreater(len(present), 0)
        for r in missing:
            self.assertFalse(r["valid"])
            self.assertEqual(r["reason"], "missing round")
        # slot allineati ogni 300s
        for i in range(1, len(picker)):
            self.assertEqual(picker[i]["market_start_ts"] - picker[i - 1]["market_start_ts"], 300)

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
