"""Test packaging zip offline: niente account/history runtime del PC sorgente."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.dashv2_pack import _assert_pack_has_no_runtime_history, main


class TestDashv2Pack(unittest.TestCase):
    def test_full_pack_excludes_runtime_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "dashv2").mkdir()
            (root / "src").mkdir()
            (root / "models").mkdir()
            (root / "data" / "_ticks_stub").mkdir(parents=True)
            (root / "dashv2.bat").write_text("@echo off\n", encoding="utf-8")
            (root / "install.bat").write_text("@echo off\n", encoding="utf-8")
            (root / "requirements-dashv2-offline.txt").write_text("flask\n", encoding="utf-8")
            (root / "hour_bands.json").write_text("{}", encoding="utf-8")
            (root / "setup.json").write_text(json.dumps({"ticks_root": "data"}), encoding="utf-8")
            (root / ".env").write_text("CURSOR_API_KEY=test\n", encoding="utf-8")
            (root / "models" / "delta_win_v2.json").write_text("{}", encoding="utf-8")
            (root / "dashv2" / "setup.json").write_text(
                json.dumps({
                    "data_dir": "../data",
                    "history_dir": "history",
                    "host": "127.0.0.1",
                    "port": 8780,
                    "default_order_size_usd": 100,
                    "stats_workers": 1,
                    "stall_reconnect_sec": 15,
                    "engine_plugin": "replay",
                    "cursor_label": "x",
                    "agent_cursor_label": "x",
                    "cursor_models": [],
                    "all_tabs": [
                        "candles", "accounts", "strategy", "backtest", "backtest_analysis", "round_chat",
                    ],
                    "hide_tabs": [],
                }),
                encoding="utf-8",
            )
            (root / "dashv2" / "__init__.py").write_text("", encoding="utf-8")
            (root / "dashv2" / "history.py").write_text("# module\n", encoding="utf-8")
            hist = root / "dashv2" / "history" / "accounts"
            hist.mkdir(parents=True)
            (hist / "account_dev123.json").write_text(
                json.dumps({"id": "dev123", "name": "rosso", "orders": [{"close_type": "manual"}]}),
                encoding="utf-8",
            )
            (hist / "_state.json").write_text('{"active_account_id":"dev123"}', encoding="utf-8")
            out = root / "pack.zip"
            import sys
            argv = sys.argv
            sys.argv = ["dashv2_pack.py", "--output", str(out), "--repo-root", str(root)]
            try:
                main()
            finally:
                sys.argv = argv
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
                self.assertIn("dashv2/history.py", names)
                self.assertIn("install.bat", names)
                self.assertIn("dashv2/history/accounts/.keep", names)
                self.assertNotIn("dashv2/history/accounts/account_dev123.json", names)
                self.assertNotIn("dashv2/history/accounts/_state.json", names)
                class _NamesOnly:
                    def list_names(self): return names
                _assert_pack_has_no_runtime_history(_NamesOnly())


if __name__ == "__main__":
    unittest.main()
