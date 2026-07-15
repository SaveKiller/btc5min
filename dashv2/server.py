"""Flask-SocketIO bridge: pagina statica + pipe verso processo dati."""

from __future__ import annotations

import threading
from multiprocessing.connection import Connection
from pathlib import Path

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from dashv2 import ipc

_STATIC = Path(__file__).resolve().parent / "static"
_ACK_TIMEOUT_SEC = 30.0
_ROUND_LOAD_TIMEOUT_SEC = 120.0


class ServerBridge:
    def __init__(self, cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
        self.cfg = cfg
        self.cmd_conn = cmd_conn
        self.evt_conn = evt_conn
        self.app = Flask(__name__, static_folder=str(_STATIC), static_url_path="")
        self.socketio = SocketIO(self.app, cors_allowed_origins=[], async_mode="threading")
        self._pending: dict[str, threading.Event] = {}
        self._pending_result: dict[str, dict] = {}
        self._pending_lock = threading.Lock()
        self._pipe_lock = threading.Lock()
        self._controller_sid: str | None = None
        self._register_routes()
        self._register_socketio()
        threading.Thread(target=self._evt_reader_loop, daemon=True).start()

    def run(self) -> None:
        self.socketio.run(self.app, host=self.cfg["host"], port=self.cfg["port"], allow_unsafe_werkzeug=True)

    def _register_routes(self) -> None:
        @self.app.route("/")
        def index():
            return send_from_directory(_STATIC, "index.html")

    def _register_socketio(self) -> None:
        @self.socketio.on("connect")
        def on_connect():
            from flask import request
            if self._controller_sid is not None:
                return False
            self._controller_sid = request.sid

        @self.socketio.on("disconnect")
        def on_disconnect():
            from flask import request
            if request.sid == self._controller_sid:
                self._controller_sid = None
                try:
                    self._request_to_data("replay.pause", {})
                except Exception:
                    pass

        for evt in ("round.load", "rounds.list", "replay.play", "replay.pause", "replay.speed", "replay.seek", "replay.preview", "order.size", "order.preview", "order.place", "order.close", "order.cancel", "account.list", "account.select", "account.create", "account.rename", "account.update", "session.sync"):
            self._bind_command(evt)

    def _bind_command(self, cmd: str) -> None:
        @self.socketio.on(cmd)
        def handler(payload, _cmd=cmd):
            from flask import request
            if request.sid != self._controller_sid:
                return {"error": "not controller"}
            if _cmd == "round.load":
                self._round_load_async(payload or {})
                return {"ok": True}
            try:
                return self._request_to_data(_cmd, payload or {}, timeout=_ACK_TIMEOUT_SEC)
            except Exception as e:
                return {"error": str(e)}

    def _round_load_async(self, payload: dict) -> None:
        def _run():
            try:
                self._request_to_data("round.load", payload, timeout=_ROUND_LOAD_TIMEOUT_SEC)
            except Exception as e:
                if self._controller_sid:
                    self.socketio.emit("error", {"message": str(e)}, to=self._controller_sid)
        threading.Thread(target=_run, daemon=True).start()

    def _request_to_data(self, cmd: str, payload: dict, timeout: float = _ACK_TIMEOUT_SEC) -> dict:
        req = ipc.make_request(cmd, payload)
        ev = threading.Event()
        rid = req["request_id"]
        with self._pending_lock:
            self._pending[rid] = ev
        with self._pipe_lock:
            self.cmd_conn.send(req)
        if not ev.wait(timeout):
            with self._pending_lock:
                self._pending.pop(rid, None)
                self._pending_result.pop(rid, None)
            raise Exception(f"ipc timeout waiting for {cmd}")
        with self._pending_lock:
            self._pending.pop(rid, None)
            res = self._pending_result.pop(rid, {"error": "missing response"})
        if "error" in res: raise Exception(res["error"])
        return res.get("payload") or {}

    def _evt_reader_loop(self) -> None:
        while True:
            if not self.evt_conn.poll(0.1):
                continue
            msg = self.evt_conn.recv()
            if ipc.is_response(msg):
                rid = msg.get("request_id")
                with self._pending_lock:
                    ev = self._pending.get(rid)
                    if ev is not None:
                        if "error" in msg:
                            self._pending_result[rid] = {"error": msg["error"]}
                        else:
                            self._pending_result[rid] = {"payload": msg.get("payload") or {}}
                        ev.set()
                continue
            if not ipc.is_event(msg):
                continue
            name, payload = msg["name"], msg.get("payload") or {}
            if self._controller_sid:
                self.socketio.emit(name, payload, to=self._controller_sid)


def run_server_process(cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
    ServerBridge(cfg, cmd_conn, evt_conn).run()
