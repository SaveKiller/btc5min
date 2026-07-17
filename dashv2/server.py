"""Flask-SocketIO bridge: pagina statica + pipe verso processo dati + co-controller bot."""

from __future__ import annotations

import threading
import uuid
from multiprocessing.connection import Connection
from pathlib import Path

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from dashv2 import ipc

_STATIC = Path(__file__).resolve().parent / "static"
_ACK_TIMEOUT_SEC = 30.0
_ROUND_LOAD_TIMEOUT_SEC = 120.0

# Comandi che il bot può emettere verso il server (protocollo 12B).
_BOT_CMDS = frozenset({
    "order.size", "order.preview", "order.place", "order.close", "order.cancel",
    "session.sync", "consult.send",
})
_BOT_TRADE_CMDS = frozenset({"order.place", "order.close", "order.cancel"})
_HUMAN_CMDS = frozenset({
    "round.load", "rounds.list", "replay.play", "replay.pause", "replay.speed",
    "replay.seek", "replay.preview", "order.size", "order.preview", "order.place",
    "order.close", "order.cancel", "account.list", "account.select", "account.create",
    "account.rename", "account.update", "bot.list", "bot.select", "bot.set_active",
    "session.sync", "consult.send",
})


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
        self._human_sid: str | None = None
        self._bot_sid: str | None = None
        self._sid_role: dict[str, str] = {}
        self._bot_active = False
        self._selected_strategy_id: str | None = None
        self._register_routes()
        self._register_socketio()
        threading.Thread(target=self._evt_reader_loop, daemon=True).start()

    def run(self) -> None:
        self.socketio.run(self.app, host=self.cfg["host"], port=self.cfg["port"], allow_unsafe_werkzeug=True)

    def _register_routes(self) -> None:
        @self.app.route("/")
        def index():
            return send_from_directory(_STATIC, "index.html")

    def _role_for_sid(self, sid: str) -> str | None:
        return self._sid_role.get(sid)

    def _broadcast(self, name: str, payload: dict) -> None:
        for sid in (self._human_sid, self._bot_sid):
            if sid:
                self.socketio.emit(name, payload, to=sid)

    def _forward_strategy_load(self, strategy_id: str | None) -> None:
        """Stato già in engine; push esplicito al processo bot."""
        self._selected_strategy_id = strategy_id
        if self._bot_sid is None:
            return
        self.socketio.emit("strategy.load", {"strategy_id": strategy_id}, to=self._bot_sid)

    def _resync_bot_strategy(self) -> None:
        """Al (ri)connect del bot: riallinea strategy dallo stato engine."""
        try:
            st = self._request_to_data("bot.list", {}, actor="user")
        except Exception as e:
            print(f"bot resync failed: {e}", flush=True)
            return
        self._bot_active = bool(st.get("bot_active"))
        self._forward_strategy_load(st.get("selected_bot_id"))

    def _register_socketio(self) -> None:
        @self.socketio.on("connect")
        def on_connect(auth=None):
            from flask import request
            role = "human"
            if isinstance(auth, dict) and auth.get("role") == "bot":
                role = "bot"
            if role == "human":
                if self._human_sid is not None:
                    return False
                self._human_sid = request.sid
            else:
                if self._bot_sid is not None:
                    return False
                self._bot_sid = request.sid
                threading.Thread(target=self._resync_bot_strategy, daemon=True).start()
            self._sid_role[request.sid] = role

        @self.socketio.on("disconnect")
        def on_disconnect():
            from flask import request
            sid = request.sid
            role = self._sid_role.pop(sid, None)
            if role == "human" and sid == self._human_sid:
                self._human_sid = None
                try:
                    self._request_to_data("replay.pause", {}, actor="user")
                except Exception:
                    pass
            elif role == "bot" and sid == self._bot_sid:
                self._bot_sid = None
                print("bot client disconnected", flush=True)
                self._broadcast("bot.status", {
                    "loaded": self._selected_strategy_id is not None, "reason": "disconnected",
                    "selected_bot_id": self._selected_strategy_id, "bot_active": self._bot_active,
                    "bot_connected": False,
                })

        @self.socketio.on("consult.send")
        def on_consult_send(payload):
            from flask import request
            role = self._role_for_sid(request.sid)
            if role is None:
                return {"error": "not controller"}
            msg = dict(payload or {})
            msg.setdefault("id", uuid.uuid4().hex[:12])
            msg["from"] = "user" if role == "human" else "bot"
            peer = self._bot_sid if role == "human" else self._human_sid
            if peer:
                self.socketio.emit("consult.message", msg, to=peer)
            self.socketio.emit("consult.message", msg, to=request.sid)
            return {"ok": True}

        for evt in sorted(_HUMAN_CMDS - {"consult.send"}):
            self._bind_command(evt)

    def _bind_command(self, cmd: str) -> None:
        @self.socketio.on(cmd)
        def handler(payload, _cmd=cmd):
            from flask import request
            role = self._role_for_sid(request.sid)
            if role is None:
                return {"error": "not controller"}
            if role == "bot" and _cmd not in _BOT_CMDS:
                return {"error": "bot not allowed"}
            if role == "bot" and _cmd in _BOT_TRADE_CMDS and not self._bot_active:
                return {"error": "bot inactive"}
            if role == "human" and _cmd not in _HUMAN_CMDS:
                return {"error": "not allowed"}
            actor = "bot" if role == "bot" else "user"
            if _cmd == "round.load":
                self._round_load_async(payload or {}, actor=actor)
                return {"ok": True}
            try:
                result = self._request_to_data(_cmd, payload or {}, timeout=_ACK_TIMEOUT_SEC, actor=actor)
                if _cmd == "bot.select":
                    self._bot_active = bool(result.get("bot_active"))
                    self._forward_strategy_load(result.get("selected_bot_id"))
                elif _cmd == "bot.set_active":
                    self._bot_active = bool(result.get("bot_active"))
                return result
            except Exception as e:
                return {"error": str(e)}

    def _round_load_async(self, payload: dict, actor: str) -> None:
        def _run():
            try:
                self._request_to_data("round.load", payload, timeout=_ROUND_LOAD_TIMEOUT_SEC, actor=actor)
            except Exception as e:
                self._broadcast("error", {"message": str(e)})
        threading.Thread(target=_run, daemon=True).start()

    def _request_to_data(self, cmd: str, payload: dict, timeout: float = _ACK_TIMEOUT_SEC, actor: str = "user") -> dict:
        body = {**payload, "actor": actor}
        req = ipc.make_request(cmd, body)
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
            if name == "bot.status" and "bot_active" in payload:
                self._bot_active = bool(payload["bot_active"])
                if "selected_bot_id" in payload:
                    self._selected_strategy_id = payload.get("selected_bot_id")
            self._broadcast(name, payload)


def run_server_process(cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
    ServerBridge(cfg, cmd_conn, evt_conn).run()
