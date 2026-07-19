"""Test AI agent chat persistenza, sessioni, tool parse, exec log (senza Cursor live)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashv2.agent_chat import append_message, clear_thread, load_thread
from dashv2.agent_service import AgentService
from dashv2.execution_log import append_execution, read_execution_session
from dashv2.history import accounts_dir, create_account
from dashv2.sessions import create_session, list_sessions_for_account, load_session


class TestSessionsStore(unittest.TestCase):
    def test_create_and_list_by_account(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            create_session(root, "s1", "accA", 100, "2026-01-01T00:00:00Z", ["st1"])
            create_session(root, "s2", "accB", 200, "2026-01-02T00:00:00Z", [])
            create_session(root, "s3", "accA", 300, "2026-01-03T00:00:00Z", [])
            data = load_session(root, "s1")
            self.assertEqual(data["account_id"], "accA")
            listed = list_sessions_for_account(root, "accA")
            self.assertEqual([x["session_id"] for x in listed], ["s3", "s1"])
            self.assertFalse(listed[0]["has_chat"])
            append_message(root, "s1", "user", "ciao", account_id="accA")
            listed2 = list_sessions_for_account(root, "accA")
            by_id = {x["session_id"]: x for x in listed2}
            self.assertTrue(by_id["s1"]["has_chat"])
            self.assertFalse(by_id["s3"]["has_chat"])
            self.assertEqual(list_sessions_for_account(root, "accB")[0]["session_id"], "s2")


    def test_delete_session_clears_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            from dashv2.history import append_settled_orders, load_account
            from dashv2.sessions import delete_session
            accounts = accounts_dir(root)
            acc = create_account(accounts, "A", 1000, "")
            create_session(root, "del1", acc["id"], 100, "2026-01-01T00:00:00Z", [])
            append_settled_orders(
                accounts, acc["id"], 100, "del1", "2026-01-01T00:00:00Z", "Up",
                [{"id": "o1", "side": "Up", "size_usd": 10, "entry_sec": 100,
                  "close_type": "settlement", "pnl_usd": 1, "source": "user"}],
                "replay",
            )
            append_execution(root, {
                "session_id": "del1", "market_start_ts": 100, "sec": 50,
                "cmd": "order.place", "side": "Up", "size_usd": 10, "source": "user",
            })
            append_message(root, "del1", "user", "ciao", account_id=acc["id"])
            delete_session(root, "del1")
            with self.assertRaises(Exception):
                load_session(root, "del1")
            self.assertEqual(load_thread(root, "del1"), [])
            self.assertFalse((root / "executions" / "del1.jsonl").is_file())
            data = load_account(accounts, acc["id"])
            self.assertEqual(data["orders"], [])


class TestAgentChat(unittest.TestCase):
    def test_thread_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            append_message(root, "sess1", "user", "ciao", account_id="acc1")
            append_message(root, "sess1", "assistant", "risposta", account_id="acc1")
            msgs = load_thread(root, "sess1")
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["role"], "user")
            path = root / "agent" / "session_sess1" / "thread.json"
            self.assertTrue(path.is_file())
            clear_thread(root, "sess1")
            self.assertEqual(load_thread(root, "sess1"), [])


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
                "loaded": False, "selected_strategy_id": None, "session_id": "sessX",
                "agent_session_id": "sessX",
                "round_tools": None, "bot_active": False, "active_strategy_ids": [],
            })
            with patch("dashv2.agent_service.call_model", return_value="Ciao, parliamo di strategie."):
                res = svc.run_turn("sessX", acc["id"], "aiuto")
            self.assertIn("strategie", res["message"]["content"])
            self.assertEqual(len(load_thread(history, "sessX")), 2)


if __name__ == "__main__":
    unittest.main()
