"""Test AI agent chat persistenza, tool parse, exec log (senza Cursor live)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashv2.agent_chat import append_message, clear_thread, load_thread
from dashv2.agent_service import AgentService
from dashv2.execution_log import append_execution, read_execution_session
from dashv2.history import accounts_dir, create_account


class TestAgentChat(unittest.TestCase):
    def test_thread_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            append_message(root, "acc1", "user", "ciao")
            append_message(root, "acc1", "assistant", "risposta")
            msgs = load_thread(root, "acc1")
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["role"], "user")
            clear_thread(root, "acc1")
            self.assertEqual(load_thread(root, "acc1"), [])


class TestExecutionLog(unittest.TestCase):
    def test_append_and_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            append_execution(root, {
                "session_id": "sess1", "market_start_ts": 1, "sec": 100,
                "cmd": "order.place", "side": "Up", "size_usd": 10, "reason": "test", "source": "bot",
            })
            rows = read_execution_session(root, "sess1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reason"], "test")

    def test_list_sessions_and_meta(self):
        from dashv2.execution_log import execution_session_meta, list_execution_sessions
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            append_execution(root, {
                "session_id": "old1", "market_start_ts": 100, "sec": 50,
                "cmd": "order.place", "strategy_id": "stratA", "side": "Up", "size_usd": 10,
                "reason": "a", "source": "bot",
            })
            append_execution(root, {
                "session_id": "old1", "market_start_ts": 100, "sec": 40,
                "cmd": "order.close", "strategy_id": "stratA", "side": "Up", "size_usd": 10,
                "reason": "b", "source": "bot",
            })
            meta = execution_session_meta(root, "old1")
            self.assertEqual(meta["n_events"], 2)
            self.assertEqual(meta["market_start_ts"], 100)
            self.assertEqual(meta["last_sec"], 40)
            self.assertEqual(meta["strategy_ids"], ["stratA"])
            append_execution(root, {
                "session_id": "withbegin", "market_start_ts": 200, "sec": 300,
                "cmd": "session.begin", "active_strategy_ids": ["s1", "s2"], "source": "engine",
            })
            append_execution(root, {
                "session_id": "withbegin", "market_start_ts": 200, "sec": 100,
                "cmd": "order.place", "strategy_id": "other", "side": "Up", "size_usd": 1,
                "reason": "x", "source": "bot",
            })
            begin_meta = execution_session_meta(root, "withbegin")
            self.assertEqual(begin_meta["strategy_ids"], ["s1", "s2"])
            self.assertEqual(begin_meta["n_events"], 1)
            listed = list_execution_sessions(root, live_session_id="live99")
            self.assertEqual(listed[0]["session_id"], "live99")
            ids = [x["session_id"] for x in listed]
            self.assertIn("old1", ids)


class TestAgentServiceTools(unittest.TestCase):
    def test_parse_and_account_tool(self):
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "history"
            history.mkdir()
            accounts = accounts_dir(history)
            acc = create_account(accounts, "A", 1000, "")
            cfg = {
                "history_dir": history,
                "agent_cursor_model": {"id": "grok-4.5", "label": "Grok 4.5 High", "params": {"effort": "high"}},
            }

            def live():
                return {
                    "loaded": False, "selected_strategy_id": None, "session_id": None,
                    "round_tools": None, "bot_active": False, "active_strategy_ids": [],
                }

            svc = AgentService(cfg, live)
            req = svc._parse_tool('ok\n```tool\n{"tool":"account.summary","args":{}}\n```\n')
            self.assertEqual(req["tool"], "account.summary")
            out = svc._run_tool("account.summary", {}, acc["id"], live())
            self.assertEqual(out["account"]["name"], "A")

    def test_run_turn_mocked(self):
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "history"
            history.mkdir()
            accounts = accounts_dir(history)
            acc = create_account(accounts, "A", 1000, "")
            cfg = {
                "history_dir": history,
                "agent_cursor_model": {"id": "grok-4.5", "label": "Grok 4.5 High", "params": {"effort": "high"}},
            }
            svc = AgentService(cfg, lambda: {
                "loaded": False, "selected_strategy_id": None, "session_id": None,
                "round_tools": None, "bot_active": False, "active_strategy_ids": [],
            })
            with patch("dashv2.agent_service.call_model", return_value="Ciao, parliamo di strategie."):
                res = svc.run_turn(acc["id"], "aiuto")
            self.assertIn("strategie", res["message"]["content"])
            self.assertEqual(len(load_thread(history, acc["id"])), 2)


if __name__ == "__main__":
    unittest.main()
