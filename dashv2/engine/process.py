"""Processo Engine: shell stabile, pipe col server, una plugin a startup."""

from __future__ import annotations

import time
from multiprocessing.connection import Connection

from dashv2 import ipc


def load_engine_plugin(plugin_id: str | None, cfg: dict, cmd_conn: Connection, evt_conn: Connection):
    """Carica il plugin; None → shell vuota (nessun dominio)."""
    if plugin_id is None:
        return None
    if plugin_id == "replay":
        from dashv2.engine.plugins.replay import ReplayEngine
        return ReplayEngine(cfg, cmd_conn, evt_conn)
    if plugin_id == "live":
        from dashv2.engine.plugins.live import LiveEngine
        return LiveEngine(cfg, cmd_conn, evt_conn)
    raise Exception(f"unknown engine plugin: {plugin_id}")


def run_engine_process(cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
    plugin_id = cfg["engine_plugin"]
    plugin = load_engine_plugin(plugin_id, cfg, cmd_conn, evt_conn)
    if plugin is None:
        _run_empty_engine(cmd_conn, evt_conn)
        return
    print(f"engine: plugin loaded id={plugin_id}", flush=True)
    plugin.run()


def _run_empty_engine(cmd_conn: Connection, evt_conn: Connection) -> None:
    """Shell senza plugin: pipe viva, nessun tick/account/trading."""
    print("engine: empty shell (no plugin)", flush=True)
    evt_conn.send(ipc.make_event("bootstrap", {
        "round_days": [], "round_nav": [], "accounts": [], "active_account_id": None,
        "engine_plugin": None, "account_backend": None,
        "bots": [], "selected_bot_id": None, "bot_attach_allowed": False, "bot_active": False,
    }))
    while True:
        while cmd_conn.poll(0.1):
            msg = cmd_conn.recv()
            rid, cmd = msg["request_id"], msg["cmd"]
            if cmd == "session.sync":
                evt_conn.send(ipc.make_event("session", {
                    "loaded": False, "engine_plugin": None, "account_backend": None,
                    "selected_bot_id": None, "bot_attach_allowed": False, "bot_active": False,
                    "account_switch_locked": False, "replay_speed": 1,
                }))
                evt_conn.send(ipc.make_response(rid, {"ok": True}))
            else:
                evt_conn.send(ipc.make_error(rid, "no engine plugin loaded"))
        time.sleep(0.02)
