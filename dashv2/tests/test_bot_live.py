"""Test actor/source, bot attach, ACL server helpers, random bot, live stub."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from dashv2.bots import list_bot_infos, load_bot
from dashv2.bots.random_bot import RandomBot, create_bot
from dashv2.config import load_config
from dashv2.engine import ReplayEngine, _actor_from_payload
from dashv2.engine.plugins.live import LiveEngine
from dashv2.history import append_settled_orders, create_account, order_rows_from_ledger
from dashv2.orders import OrderEngine
from dashv2.server import _BOT_CMDS, _HUMAN_CMDS
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
        b = eng.place("Down", 10.0, 190, tick, book, 0.02, "acc1", "bot")
        self.assertEqual(u["source"], "user")
        self.assertEqual(b["source"], "bot")

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

    def test_attach_allowed_without_round(self):
        eng = self._engine()
        self.assertTrue(eng._bot_attach_allowed())
        res = eng._cmd_bot_select({"bot_id": "random"})
        self.assertEqual(res["selected_bot_id"], "random")
        self.assertTrue(res["bot_active"])
        self.assertEqual(res["strategies"], [{"id": "random", "active": True}])

    def test_detach_clears_strategies_snapshot(self):
        eng = self._engine()
        eng._cmd_bot_select({"bot_id": "random"})
        res = eng._cmd_bot_select({"bot_id": None})
        self.assertIsNone(res["selected_bot_id"])
        self.assertEqual(res["strategies"], [])
        self.assertFalse(res["bot_active"])

    def test_attach_blocked_while_playing(self):
        eng = self._engine()
        eng.loaded = MagicMock()
        eng.sec = 250
        eng.playing = True
        self.assertFalse(eng._bot_attach_allowed())
        with self.assertRaises(Exception):
            eng._cmd_bot_select({"bot_id": "random"})

    def test_attach_allowed_while_paused_mid_round(self):
        eng = self._engine()
        eng.loaded = MagicMock()
        eng.sec = 250
        eng.playing = False
        eng._round_advanced = True
        self.assertTrue(eng._bot_attach_allowed())
        res = eng._cmd_bot_select({"bot_id": "random"})
        self.assertEqual(res["selected_bot_id"], "random")

    def test_attach_allowed_after_round_end(self):
        eng = self._engine()
        eng.loaded = MagicMock()
        eng.sec = 0
        eng.playing = False
        eng.round_ended = True
        self.assertTrue(eng._bot_attach_allowed())
        res = eng._cmd_bot_select({"bot_id": "random"})
        self.assertEqual(res["selected_bot_id"], "random")

    def test_set_active_toggles_and_blocks_bot_orders(self):
        eng = self._engine()
        eng._cmd_bot_select({"bot_id": "random"})
        self.assertTrue(eng.bot_active)
        res = eng._cmd_bot_set_active({"active": False})
        self.assertFalse(res["bot_active"])
        with self.assertRaises(Exception):
            eng._require_bot_trading("bot")
        eng._require_bot_trading("user")
        eng._cmd_bot_set_active({"active": True})
        eng._require_bot_trading("bot")

    def test_set_active_requires_selected_bot(self):
        eng = self._engine()
        with self.assertRaises(Exception):
            eng._cmd_bot_set_active({"active": True})


class TestServerAcl(unittest.TestCase):
    def test_bot_cannot_seek(self):
        self.assertNotIn("replay.seek", _BOT_CMDS)
        self.assertIn("replay.seek", _HUMAN_CMDS)
        self.assertIn("order.place", _BOT_CMDS)
        self.assertIn("bot.set_active", _HUMAN_CMDS)
        self.assertNotIn("bot.set_active", _BOT_CMDS)


class TestRandomBot(unittest.TestCase):
    def test_discovery_and_tick_action(self):
        infos = list_bot_infos()
        self.assertTrue(any(b["id"] == "random" for b in infos))
        bot = load_bot("random")
        self.assertIsInstance(bot, RandomBot)
        tick = {"tradable": True}
        session = {"tradable": True, "round_ended": False}
        # seed 42: deterministic enough to get some places over many ticks
        actions = []
        for _ in range(50):
            actions.extend(bot.on_tick(tick, session, {"open": []}))
        self.assertTrue(any(a["cmd"] == "order.place" for a in actions))


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
