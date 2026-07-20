"""ACL: comandi stats.* solo human, non inoltrati al bot."""

from __future__ import annotations

import unittest

from dashv2.server import _BOT_CMDS, _HUMAN_CMDS, _STATS_CMDS


class TestStatsAcl(unittest.TestCase):
    def test_stats_cmds_human_only(self):
        self.assertIn("stats.backtest.start", _HUMAN_CMDS)
        self.assertIn("stats.analyze.start", _HUMAN_CMDS)
        self.assertIn("stats.job.cancel", _HUMAN_CMDS)
        self.assertIn("stats.chat.send", _HUMAN_CMDS)
        self.assertIn("stats.chat.history", _HUMAN_CMDS)
        self.assertIn("stats.chat.clear", _HUMAN_CMDS)
        self.assertIn("stats.rules.apply", _HUMAN_CMDS)
        self.assertIn("stats.analyze.list", _HUMAN_CMDS)
        self.assertIn("stats.analyze.delete", _HUMAN_CMDS)
        self.assertIn("stats.simulation.list", _HUMAN_CMDS)
        self.assertIn("stats.simulation.load", _HUMAN_CMDS)
        self.assertIn("stats.simulation.delete", _HUMAN_CMDS)
        for cmd in _STATS_CMDS:
            self.assertIn(cmd, _HUMAN_CMDS)
            self.assertNotIn(cmd, _BOT_CMDS)

    def test_stats_set_matches_expected(self):
        self.assertEqual(_STATS_CMDS, frozenset({
            "stats.backtest.start", "stats.analyze.start", "stats.job.cancel",
            "stats.chat.send", "stats.chat.history", "stats.chat.clear", "stats.rules.apply",
            "stats.analyze.list", "stats.analyze.delete",
            "stats.simulation.list", "stats.simulation.load", "stats.simulation.delete",
        }))


if __name__ == "__main__":
    unittest.main()
