"""Test actor/source, bot attach, ACL server helpers, strategies JSON, live stub."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from dashv2.bots import list_bot_infos
from dashv2.config import load_config
from dashv2.engine import ReplayEngine, _actor_from_payload
from dashv2.engine.plugins.live import LiveEngine
from dashv2.history import append_settled_orders, create_account, order_rows_from_ledger
from dashv2.orders import OrderEngine
from dashv2.server import _BOT_CMDS, _HUMAN_CMDS
from dashv2.strategies import create_strategy, list_strategies, load_active_ids, strategies_dir
from src.book import BookSnapshot


def _book(up_ask=0.55, down_ask=0.45):
    return BookSnapshot(
        [(up_ask - 0.02, 1000)], [(up_ask, 1000)], [(down_ask - 0.02, 1000)], [(down_ask, 1000)],
        up_ask - 0.02, up_ask, down_ask - 0.02, down_ask)


class TestActorSource(unittest.TestCase):
    def test_place_tags_source(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        book = _book()
        u = eng.place("Up", 10.0, 200, tick, book, 0.02, "acc1", "user")
        b = eng.place("Down", 10.0, 190, tick, book, 0.02, "acc1", "bot", strategy_id="strat1")
        self.assertEqual(u["source"], "user")
        self.assertIsNone(u["strategy_id"])
        self.assertEqual(b["source"], "bot")
        self.assertEqual(b["strategy_id"], "strat1")

    def test_bot_place_requires_strategy_id(self):
        eng = OrderEngine(100, 100)
        tick = {"chainlink_btc": 90000.0, "partial": False, "gap": False, "up_ask": 0.55, "up_bid": 0.53, "down_ask": 0.45, "down_bid": 0.43}
        with self.assertRaises(Exception):
            eng.place("Up", 10.0, 200, tick, _book(), 0.02, "acc1", "bot")

    def test_actor_from_payload(self):
        self.assertEqual(_actor_from_payload({"actor": "bot"}), "bot")
        self.assertEqual(_actor_from_payload({}), "user")
        with self.assertRaises(Exception):
            _actor_from_payload({"actor": "alien"})

    def test_ledger_keeps_source_and_round_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = create_account(root, "A", 1000.0, "")
            orders = [{
                "id": "o1", "account_id": data["id"], "source": "bot", "side": "Up", "entry_sec": 200,
                "size_usd": 10, "close_type": "settlement", "result": "won", "pnl_usd": 5,
                "payout_if_win_usd": 15, "profit_if_win_usd": 5, "best_ask_c": 55, "exit_sec": 0,
            }]
            append_settled_orders(root, data["id"], 100, "s1", "2026-07-16T10:00:00Z", "Up", orders, "replay")
            rows = order_rows_from_ledger(
                __import__("json").loads((root / f"account_{data['id']}.json").read_text(encoding="utf-8"))["orders"])
            self.assertEqual(rows[0]["source"], "bot")
            self.assertEqual(rows[0]["round_source"], "replay")


class TestBotAttach(unittest.TestCase):
    def _engine(self):
        cfg = {
            "data_dir": Path("."), "history_dir": Path(tempfile.mkdtemp()),
            "default_order_size_usd": 100, "stall_reconnect_sec": 15,
            "chart_previous_candles": 1, "host": "127.0.0.1", "port": 8780,
            "engine_plugin": "replay",
        }
        cfg["history_dir"].mkdir(parents=True, exist_ok=True)
        eng = ReplayEngine(cfg, MagicMock(), MagicMock())
        eng.evt_conn.send = MagicMock()
        return eng

    def test_set_active_without_strategies(self):
        eng = self._engine()
        res = eng._cmd_bot_set_active({"active": True})
        self.assertTrue(res["bot_active"])
        eng._require_bot_trading("bot")
        eng._cmd_bot_set_active({"active": False})
        with self.assertRaises(Exception):
            eng._require_bot_trading("bot")

    def test_load_unload_strategy(self):
        eng = self._engine()
        created = eng._cmd_strategy_create({
            "name": "Alpha", "type": "deterministic", "description": "test",
            "rules": "buy up", "module_file": "strategy_x.py", "strategy_id": "aaa111bbb222",
        })
        sid = created["strategy"]["id"]
        res = eng._cmd_strategy_load({"strategy_id": sid})
        self.assertEqual(res["active_strategy_ids"], [sid])
        self.assertEqual(load_active_ids(eng.strategies_root), [sid])
        with self.assertRaises(Exception):
            eng._cmd_strategy_load({"strategy_id": sid})
        res = eng._cmd_strategy_unload({"strategy_id": sid})
        self.assertEqual(res["active_strategy_ids"], [])

    def test_load_allowed_while_playing(self):
        eng = self._engine()
        created = eng._cmd_strategy_create({"name": "Beta", "type": "inferential", "description": ""})
        sid = created["strategy"]["id"]
        eng.playing = True
        res = eng._cmd_strategy_load({"strategy_id": sid})
        self.assertEqual(res["active_strategy_ids"], [sid])

    def test_delete_removes_from_active(self):
        eng = self._engine()
        created = eng._cmd_strategy_create({"name": "Gamma", "type": "agentic", "description": "x"})
        sid = created["strategy"]["id"]
        eng._cmd_strategy_load({"strategy_id": sid})
        eng._cmd_strategy_delete({"strategy_id": sid})
        self.assertEqual(eng.active_strategy_ids, [])
        self.assertEqual(list_strategies(eng.strategies_root), [])

    def test_restart_after_round_end_new_session(self):
        eng = self._engine()
        eng.loaded = MagicMock()
        eng.loaded.market_start_ts = 1
        eng.loaded.ptb_chainlink = 90000.0
        eng.loaded.ticks_by_sec = {}
        eng.loaded.books_by_sec = {}
        eng.session_id = "oldsession01"
        eng.session_started_at_utc = "2026-01-01T00:00:00Z"
        eng.round_ended = True
        eng.repo = MagicMock()
        eng.repo.current_candle = MagicMock(return_value=None)
        eng.repo.previous_candles = MagicMock(return_value=[])
        res = eng._restart_round(playing=False, sec=300)
        self.assertTrue(res["restarted"])
        self.assertFalse(eng.round_ended)
        self.assertNotEqual(eng.session_id, "oldsession01")
        self.assertNotEqual(eng.session_started_at_utc, "2026-01-01T00:00:00Z")


class TestStrategiesRepo(unittest.TestCase):
    def test_create_list_update_by_type(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            a = create_strategy(
                root, "A", "deterministic", "alpha desc",
                rules="r", module_file="strategy_a.py", strategy_id="abc123abc123")
            create_strategy(root, "B", "inferential", "")
            self.assertEqual(len(list_strategies(root)), 2)
            self.assertEqual(len(list_strategies(root, "deterministic")), 1)
            from dashv2.strategies import update_strategy
            updated = update_strategy(root, a["id"], "A2", "new desc", rules="r2")
            self.assertEqual(updated["name"], "A2")
            self.assertEqual(updated["description"], "new desc")
            self.assertEqual(updated["rules"], "r2")


class TestServerAcl(unittest.TestCase):
    def test_bot_cannot_seek(self):
        self.assertNotIn("replay.seek", _BOT_CMDS)
        self.assertIn("replay.seek", _HUMAN_CMDS)
        self.assertIn("order.place", _BOT_CMDS)
        self.assertIn("bot.set_active", _HUMAN_CMDS)
        self.assertNotIn("bot.set_active", _BOT_CMDS)
        self.assertIn("strategy.create", _HUMAN_CMDS)
        self.assertIn("strategy.update", _HUMAN_CMDS)
        self.assertIn("strategy.clone", _HUMAN_CMDS)
        self.assertNotIn("bot.select", _HUMAN_CMDS)
        self.assertNotIn("strategy.rename", _HUMAN_CMDS)


class TestBotDiscovery(unittest.TestCase):
    def test_no_random_plugin(self):
        infos = list_bot_infos()
        self.assertFalse(any(b["id"] == "random" for b in infos))


class TestLiveStub(unittest.TestCase):
    def test_live_rejects_trading(self):
        cfg = {
            "default_order_size_usd": 100, "host": "127.0.0.1", "port": 8780,
            "engine_plugin": "live",
        }
        cmd, evt = MagicMock(), MagicMock()
        eng = LiveEngine(cfg, cmd, evt)
        sent = []
        evt.send = lambda m: sent.append(m)
        eng._handle_cmd({"kind": "request", "request_id": "r1", "cmd": "order.place", "payload": {}})
        self.assertTrue(any(m.get("error") == "live engine plugin not implemented" for m in sent))

    def test_config_requires_engine_plugin(self):
        cfg = load_config()
        self.assertIn(cfg["engine_plugin"], ("replay", "live", None))


if __name__ == "__main__":
    unittest.main()
