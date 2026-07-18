"""Flask-SocketIO bridge: pagina statica + pipe verso processo dati + co-controller bot."""

from __future__ import annotations

import threading
import uuid
from multiprocessing.connection import Connection
from pathlib import Path

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from dashv2 import ipc
from dashv2.config import reload_strategy_codegen_system_prompt
from dashv2.strategies import strategies_dir, write_module
from dashv2.strategy_codegen import generate_strategy_module

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
    "account.rename", "account.update", "bot.list", "bot.set_active",
    "strategy.list", "strategy.create", "strategy.update", "strategy.delete",
    "strategy.load", "strategy.unload", "session.sync", "consult.send",
})
_STRATEGY_GEN_CMDS = frozenset({"strategy.create", "strategy.update"})


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
        self._active_strategy_ids: list[str] = []
        self.strategies_root = strategies_dir(Path(cfg["history_dir"]))
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

    def _emit_generate(self, phase: str, message: str = "", strategy_id: str | None = None) -> None:
        payload = {"phase": phase, "message": message}
        if strategy_id is not None:
            payload["strategy_id"] = strategy_id
        if self._human_sid:
            self.socketio.emit("strategy.generate", payload, to=self._human_sid)

    def _forward_strategy_sync(self, strategy_ids: list[str] | None) -> None:
        """Stato già in engine; push esplicito al processo bot."""
        ids = list(strategy_ids or [])
        self._active_strategy_ids = ids
        if self._bot_sid is None:
            return
        self.socketio.emit("strategy.sync", {"strategy_ids": ids}, to=self._bot_sid)

    def _resync_bot_strategy(self) -> None:
        """Al (ri)connect del bot: riallinea strategy dallo stato engine."""
        try:
            st = self._request_to_data("bot.list", {}, actor="user")
        except Exception as e:
            print(f"bot resync failed: {e}", flush=True)
            return
        self._bot_active = bool(st.get("bot_active"))
        self._forward_strategy_sync(st.get("active_strategy_ids") or [])

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
                    "loaded": bool(self._active_strategy_ids), "reason": "disconnected",
                    "active_strategy_ids": list(self._active_strategy_ids),
                    "bot_active": self._bot_active, "bot_connected": False,
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

        for evt in sorted(_HUMAN_CMDS - {"consult.send"} - _STRATEGY_GEN_CMDS):
            self._bind_command(evt)
        self._bind_strategy_create()
        self._bind_strategy_update()

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
                if _cmd == "bot.set_active":
                    self._bot_active = bool(result.get("bot_active"))
                elif _cmd in ("strategy.load", "strategy.unload", "strategy.delete"):
                    self._forward_strategy_sync(result.get("active_strategy_ids") or [])
                return result
            except Exception as e:
                return {"error": str(e)}

    def _bind_strategy_create(self) -> None:
        @self.socketio.on("strategy.create")
        def handler(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                return self._strategy_create_with_codegen(payload or {})
            except Exception as e:
                self._emit_generate("error", str(e))
                return {"error": str(e)}

    def _bind_strategy_update(self) -> None:
        @self.socketio.on("strategy.update")
        def handler(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                return self._strategy_update_with_codegen(payload or {})
            except Exception as e:
                self._emit_generate("error", str(e))
                return {"error": str(e)}

    def _codegen_source(self, rules: str) -> str:
        model = self.cfg["cursor_model"]
        system_prompt = reload_strategy_codegen_system_prompt()
        self.cfg["strategy_codegen_system_prompt"] = system_prompt
        self._emit_generate("generating", f"Generating with {model['label']}…")
        source = generate_strategy_module(
            rules, model_id=model["id"], params=model["params"],
            system_prompt=system_prompt,
        )
        self._emit_generate("validating", "Validating generated module…")
        return source

    def _strategy_create_with_codegen(self, body: dict) -> dict:
        stype = body["type"]
        rules = body.get("rules") or ""
        module_file = None
        strategy_id = None
        if stype == "deterministic":
            source = self._codegen_source(rules)
            strategy_id = uuid.uuid4().hex[:12]
            self._emit_generate("saving", "Saving strategy…", strategy_id)
            module_file = write_module(self.strategies_root, strategy_id, source)
        ipc_payload = {
            "name": body["name"], "type": stype, "description": body.get("description") or "",
            "rules": rules, "module_file": module_file, "strategy_id": strategy_id,
        }
        try:
            result = self._request_to_data("strategy.create", ipc_payload, actor="user")
        except Exception:
            if strategy_id is not None:
                py = self.strategies_root / f"strategy_{strategy_id}.py"
                if py.is_file():
                    py.unlink()
            raise
        self._emit_generate("done", "Strategy ready", (result.get("strategy") or {}).get("id"))
        return result

    def _strategy_update_with_codegen(self, body: dict) -> dict:
        sid = body["strategy_id"]
        rules = body.get("rules")
        module_file = None
        if body.get("rules_changed") and rules is not None:
            source = self._codegen_source(rules)
            self._emit_generate("saving", "Saving strategy…", sid)
            module_file = write_module(self.strategies_root, sid, source)
        ipc_payload = {
            "strategy_id": sid, "name": body["name"],
            "description": body.get("description") or "",
            "rules": rules, "module_file": module_file,
        }
        result = self._request_to_data("strategy.update", ipc_payload, actor="user")
        self._emit_generate("done", "Strategy updated", sid)
        return result

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
                if "active_strategy_ids" in payload:
                    self._active_strategy_ids = list(payload.get("active_strategy_ids") or [])
            self._broadcast(name, payload)


def run_server_process(cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
    ServerBridge(cfg, cmd_conn, evt_conn).run()
