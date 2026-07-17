"""Plugin Engine live (stub): contratto IPC comune, senza Polymarket reale."""

from __future__ import annotations

from multiprocessing.connection import Connection

from dashv2 import ipc

# Env vars previsti per live reale (non letti dallo stub):
# POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE, POLY_PRIVATE_KEY


class LiveEngine:
    """Plugin live stub: bootstrap/sync ok; trading/account Polymarket non implementati."""

    plugin_id = "live"

    def __init__(self, cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
        self.cfg = cfg
        self.cmd_conn = cmd_conn
        self.evt_conn = evt_conn
        self.engine_plugin = "live"
        self.account_backend = "polymarket"

    def run(self) -> None:
        self.evt_conn.send(ipc.make_event("bootstrap", self._bootstrap_payload()))
        self.evt_conn.send(ipc.make_event("accounts", {
            "accounts": [], "active_account_id": None, "active": None,
            "account_backend": self.account_backend,
        }))
        self.evt_conn.send(ipc.make_event("error", {
            "message": "live engine plugin not implemented", "feed": {"state": "paused"},
        }))
        while True:
            while self.cmd_conn.poll(0.1):
                self._handle_cmd(self.cmd_conn.recv())

    def _bootstrap_payload(self) -> dict:
        return {
            "round_days": [], "round_nav": [],
            "default_order_size_usd": self.cfg["default_order_size_usd"],
            "host": self.cfg["host"], "port": self.cfg["port"],
            "accounts": [], "active_account_id": None,
            "engine_plugin": self.engine_plugin, "account_backend": self.account_backend,
            "bots": [], "selected_bot_id": None, "bot_attach_allowed": False, "bot_active": False,
        }

    def _handle_cmd(self, msg: dict) -> None:
        rid, cmd = msg["request_id"], msg["cmd"]
        if cmd == "session.sync":
            self.evt_conn.send(ipc.make_event("bootstrap", self._bootstrap_payload()))
            self.evt_conn.send(ipc.make_event("session", {
                "loaded": False, "engine_plugin": self.engine_plugin,
                "account_backend": self.account_backend, "selected_bot_id": None,
                "bot_attach_allowed": False, "bot_active": False,
                "account_switch_locked": False, "replay_speed": 1,
            }))
            self.evt_conn.send(ipc.make_response(rid, {"ok": True}))
            return
        if cmd in ("bot.list", "bot.select", "bot.set_active", "account.list"):
            self.evt_conn.send(ipc.make_response(rid, {"ok": True, "bots": [], "accounts": [],
                                                       "selected_bot_id": None, "active_account_id": None,
                                                       "bot_attach_allowed": False, "bot_active": False}))
            return
        self.evt_conn.send(ipc.make_error(rid, "live engine plugin not implemented"))
