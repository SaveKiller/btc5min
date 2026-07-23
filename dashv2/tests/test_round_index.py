"""Test indice persistente round."""

import json
import tempfile
import unittest
from pathlib import Path

from src.round_index import (
    INDEX_NAME, index_path, load_index_file, load_or_build_index,
    reconcile_index, save_index, scan_bins, upsert_bins,
)


class TestRoundIndex(unittest.TestCase):
    def test_build_save_load(self):
        data_dir = Path(__file__).resolve().parents[2] / "data"
        if not data_dir.is_dir():
            self.skipTest("data/ not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # copia un solo giorno per test veloce
            days = sorted(p for p in data_dir.iterdir() if p.is_dir() and (p / "bin").is_dir())
            if not days:
                self.skipTest("no day dirs in data/")
            day = days[-1]
            (root / day.name / "bin").mkdir(parents=True)
            for f in (day / "bin").glob("btc5m_*.bin"):
                (root / day.name / "bin" / f.name).write_bytes(f.read_bytes())
                txt = f.with_suffix(".txt")
                if txt.is_file():
                    (root / day.name / "bin" / txt.name).write_text(txt.read_text(encoding="utf-8"), encoding="utf-8")
            scanned = scan_bins(root)
            self.assertGreater(len(scanned), 0)
            save_index(root, scanned)
            loaded = load_index_file(index_path(root))
            self.assertEqual(loaded, scanned)

    def test_scan_ignores_nested_data_dir(self):
        """Con data_dir=root repo non deve indicizzare data/YYYY-MM-DD/bin sotto."""
        root = Path(__file__).resolve().parents[2]
        data_dir = root / "data"
        if not data_dir.is_dir():
            self.skipTest("data/ not available")
        if not scan_bins(data_dir):
            self.skipTest("no bins in data/")
        self.assertEqual(scan_bins(root), {})

    def test_load_or_build_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = load_or_build_index(root)
            self.assertEqual(entries, {})
            self.assertTrue(index_path(root).is_file())

    def test_upsert_and_reconcile(self):
        data_dir = Path(__file__).resolve().parents[2] / "data"
        if not data_dir.is_dir():
            self.skipTest("data/ not available")
        bins = list(data_dir.glob("**/bin/btc5m_*.bin"))
        if not bins:
            self.skipTest("no bins in data/")
        src = bins[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = src.parent.parent.name
            dest = root / day / "bin" / src.name
            dest.parent.mkdir(parents=True)
            dest.write_bytes(src.read_bytes())
            txt = src.with_suffix(".txt")
            if txt.is_file():
                (dest.parent / txt.name).write_text(txt.read_text(encoding="utf-8"), encoding="utf-8")
            upsert_bins(root, [dest])
            path = index_path(root)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["v"], 1)
            self.assertEqual(len(raw["entries"]), 1)
            entries = load_or_build_index(root)
            self.assertEqual(len(entries), 1)


if __name__ == "__main__":
    unittest.main()
