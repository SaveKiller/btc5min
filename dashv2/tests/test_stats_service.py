"""Test StatsService thread + extract rules (senza Cursor)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashv2.stats_modules import create_analyze, list_analyzes, load_analyze, set_analyze_rules
from dashv2.stats_service import (
    StatsService,
    append_stats_message,
    extract_proposed_rules,
    load_stats_thread,
)


class TestStatsThread(unittest.TestCase):
    def test_append_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            append_stats_message(hist, "user", "ciao")
            append_stats_message(hist, "assistant", "risposta")
            msgs = load_stats_thread(hist)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["role"], "user")
            self.assertEqual(msgs[1]["content"], "risposta")

    def test_extract_rules_fence(self):
        reply = "Proposta:\n```rules\nconta flip majority\n```\nfine"
        prop = extract_proposed_rules(reply)
        self.assertEqual(prop["rules"], "conta flip majority")
        self.assertIsNone(extract_proposed_rules("niente rules"))


class TestStatsModulesUpdate(unittest.TestCase):
    def test_set_rules_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            data = create_analyze(hist, "A1", "rules v1")
            set_analyze_rules(hist, data["id"], "rules v2")
            loaded = load_analyze(hist, data["id"])
            self.assertEqual(loaded["rules"], "rules v2")
            self.assertEqual(list_analyzes(hist)[0]["rules"], "rules v2")


class TestStatsApplyMock(unittest.TestCase):
    def test_apply_creates_and_writes_module(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td)
            cfg = {
                "history_dir": hist,
                "cursor_model": {"id": "x", "label": "X", "params": {}},
                "agent_cursor_model": {"id": "g", "label": "G", "params": {}},
                "stats_codegen_system_prompt": "sys",
            }
            svc = StatsService(cfg)
            stub = "def analyze_round(round_view):\n    return {}\n"
            with patch("dashv2.stats_service.generate_analyze_module", return_value=stub):
                with patch("dashv2.stats_service.reload_stats_codegen_system_prompt", return_value="sys"):
                    out = svc.apply_rules("conta ticks", None, "MyAnalyze")
            self.assertTrue(out["ok"])
            aid = out["analyze"]["id"]
            py = hist / "stats" / f"analyze_{aid}.py"
            self.assertTrue(py.is_file())
            self.assertIn("analyze_round", py.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
