from __future__ import annotations

import unittest
from pathlib import Path

from dashv2.batch.listing import list_batch_rounds


class FakeRepo:
    def __init__(self):
        self._items = [
            {"market_start_ts": 1784419200, "day_utc": "2026-07-19", "valid": True},  # 00:00
            {"market_start_ts": 1784469600, "day_utc": "2026-07-19", "valid": True},  # 14:00
            {"market_start_ts": 1784469600 + 300, "day_utc": "2026-07-19", "valid": False},
            {"market_start_ts": 1784332800, "day_utc": "2026-07-18", "valid": True},
        ]
        self._bins = {
            i["market_start_ts"]: Path(f"/tmp/{i['market_start_ts']}.bin")
            for i in self._items
            if i["valid"]
        }

    def list_picker(self):
        return list(self._items)

    def bin_path(self, mts: int) -> Path:
        return self._bins[mts]


class TestListing(unittest.TestCase):
    def test_range_inclusive(self):
        paths, skipped = list_batch_rounds(FakeRepo(), "2026-07-19", "2026-07-19")
        self.assertEqual(len(paths), 2)
        self.assertEqual(skipped, 1)
        hours = {p["hour_utc"] for p in paths}
        self.assertEqual(hours, {0, 14})


if __name__ == "__main__":
    unittest.main()
