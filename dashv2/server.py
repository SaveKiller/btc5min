"""Flask-SocketIO bridge: pagina statica + pipe verso processo dati + co-controller bot."""

from __future__ import annotations

import threading
import uuid
from multiprocessing.connection import Connection
from pathlib import Path

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from dashv2 import ipc
from dashv2.agents.agent_chat import load_thread
from dashv2.agents.agent_round_tools import AgentRoundTools
from dashv2.agents.agent_service import AgentService
from dashv2.batch.analyze_job import load_reduce_results
from dashv2.batch.listing import list_batch_rounds
from dashv2.batch.reduce import reduce_analyze_fallback, reduce_strategy_rows
from dashv2.batch.runner import BatchCancelled, RoundBatchRunner
from dashv2.config import reload_strategy_codegen_system_prompt
from dashv2.execution_log import execution_session_meta
from dashv2.rounds import RoundRepository
from dashv2.sessions import delete_session, list_sessions_for_account
from dashv2.simulations import (
    create_simulation, delete_simulation, list_simulations, load_simulation,
    load_round_orders, simulation_has_orders, simulation_label,
)
from dashv2.stats_modules import delete_analyze, list_analyzes, module_path as analyze_module_path
from dashv2.stats_service import StatsService, append_stats_message, clear_stats_thread, load_stats_thread
from dashv2.strategies import (
    load_strategy, module_path as strategy_module_path, strategies_dir, write_module,
)
from dashv2.agents.strategy_codegen import generate_coded_rules, generate_strategy_module

_STATIC = Path(__file__).resolve().parent / "static"
_ACK_TIMEOUT_SEC = 30.0
_ROUND_LOAD_TIMEOUT_SEC = 120.0
_AGENT_CHAT_TIMEOUT_SEC = 600.0

# Comandi che il bot può emettere verso il server (protocollo 12B).
_BOT_CMDS = frozenset({
    "order.size", "order.preview", "order.place", "order.close", "order.cancel",
    "session.sync", "consult.send",
})
_BOT_TRADE_CMDS = frozenset({"order.place", "order.close", "order.cancel"})
_HUMAN_CMDS = frozenset({
    "round.load", "round.unload", "rounds.list", "replay.play", "replay.pause", "replay.speed",
    "replay.seek", "replay.preview", "order.size", "order.preview", "order.place",
    "order.close", "order.cancel", "account.list", "account.select", "account.create",
    "account.rename", "account.update", "bot.list", "bot.set_active",
    "strategy.list", "strategy.create", "strategy.update", "strategy.clone", "strategy.delete",
    "strategy.load", "strategy.unload", "session.sync", "consult.send",
    "agent.chat.send", "agent.chat.history", "agent.rules.apply",
    "agent.executions.list", "agent.session.select", "agent.session.delete",
    "stats.backtest.start", "stats.analyze.start", "stats.job.cancel",
    "stats.chat.send", "stats.chat.history", "stats.chat.clear", "stats.rules.apply",
    "stats.analyze.list", "stats.analyze.delete",
    "stats.simulation.list", "stats.simulation.load", "stats.simulation.delete",
})
_STRATEGY_GEN_CMDS = frozenset({"strategy.create", "strategy.update"})
_AGENT_CMDS = frozenset({
    "agent.chat.send", "agent.chat.history", "agent.rules.apply",
    "agent.executions.list", "agent.session.select", "agent.session.delete",
})
_STATS_CMDS = frozenset({
    "stats.backtest.start", "stats.analyze.start", "stats.job.cancel",
    "stats.chat.send", "stats.chat.history", "stats.chat.clear", "stats.rules.apply",
    "stats.analyze.list", "stats.analyze.delete",
    "stats.simulation.list", "stats.simulation.load", "stats.simulation.delete",
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
        self._active_strategy_ids: list[str] = []
        self._active_strategies: list[dict] = []
        self._active_account_id: str | None = None
        self._live_ctx = {
            "loaded": False, "market_start_ts": None, "session_id": None,
            "agent_session_id": None,
            "sec": None, "bot_active": False, "active_strategy_ids": [],
            "active_strategies": [],
            "selected_strategy_id": None,
        }
        self.strategies_root = strategies_dir(Path(cfg["history_dir"]))
        self.round_tools = AgentRoundTools(
            RoundRepository(Path(cfg["data_dir"]), float(cfg["stall_reconnect_sec"])))
        self.agent_service = AgentService(cfg, self._agent_tool_ctx)
        self.agent_service.set_apply_rules_fn(self._agent_apply_rules)
        self._agent_busy = False
        self.stats_service = StatsService(cfg)
        self._stats_busy = False
        self._stats_chat_busy = False
        self._stats_cancel_requested = False
        self._stats_runner: RoundBatchRunner | None = None
        self._stats_day_from: str | None = None
        self._stats_day_to: str | None = None
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

    def _forward_strategy_sync(self, active_strategies: list[dict] | None) -> None:
        """Stato già in engine; push esplicito al processo bot."""
        entries = list(active_strategies or [])
        self._active_strategies = entries
        self._active_strategy_ids = [e["id"] for e in entries]
        if self._bot_sid is None:
            return
        self.socketio.emit("strategy.sync", {"active_strategies": entries}, to=self._bot_sid)

    def _resync_bot_strategy(self) -> None:
        """Al (ri)connect del bot: riallinea strategy dallo stato engine."""
        try:
            st = self._request_to_data("bot.list", {}, actor="user")
        except Exception as e:
            print(f"bot resync failed: {e}", flush=True)
            return
        self._bot_active = bool(st.get("bot_active"))
        self._forward_strategy_sync(st.get("active_strategies") or [])

    def _register_socketio(self) -> None:
        @self.socketio.on("connect")
        def on_connect(auth=None):
            from flask import request
            role = "human"
            if isinstance(auth, dict) and auth.get("role") == "bot":
                role = "bot"
            if role == "human":
                old = self._human_sid
                if old is not None and old != request.sid:
                    self._sid_role.pop(old, None)
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
                    "active_strategies": list(self._active_strategies),
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

        for evt in sorted(_HUMAN_CMDS - {"consult.send"} - _STRATEGY_GEN_CMDS - _AGENT_CMDS - _STATS_CMDS):
            self._bind_command(evt)
        self._bind_strategy_create()
        self._bind_strategy_update()
        self._bind_agent_chat()
        self._bind_stats()

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
                    self._forward_strategy_sync(result.get("active_strategies") or [])
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

    def _agent_tool_ctx(self) -> dict:
        ctx = dict(self._live_ctx)
        ctx["round_tools"] = self.round_tools
        ctx["bot_active"] = self._bot_active
        ctx["active_strategy_ids"] = list(self._active_strategy_ids)
        ctx["active_strategies"] = list(self._active_strategies)
        return ctx

    def _agent_apply_rules(
        self, strategy_id: str, rules: str, name: str | None, description: str | None,
    ) -> dict:
        data = load_strategy(self.strategies_root, strategy_id)
        body = {
            "strategy_id": strategy_id,
            "name": name if name is not None else data["name"],
            "description": description if description is not None else data.get("description") or "",
            "rules": rules,
            "rules_changed": True,
        }
        result = self._strategy_update_with_codegen(body)
        return {"ok": True, "strategy": result.get("strategy")}

    def _agent_focus_payload(self) -> dict:
        history_dir = Path(self.cfg["history_dir"])
        account_id = self._active_account_id
        live_sid = self._live_ctx.get("session_id")
        sessions = (
            list_sessions_for_account(history_dir, account_id, live_session_id=live_sid)
            if account_id else []
        )
        focus = self._live_ctx.get("agent_session_id") or live_sid
        session_ids = {s["session_id"] for s in sessions}
        if focus and focus not in session_ids and focus != live_sid:
            focus = sessions[0]["session_id"] if sessions else None
            self._live_ctx["agent_session_id"] = focus
        elif not focus and sessions:
            focus = sessions[0]["session_id"]
            self._live_ctx["agent_session_id"] = focus
        is_live = bool(focus and focus == live_sid)
        meta = execution_session_meta(history_dir, focus) if focus else {
            "session_id": None, "market_start_ts": None, "last_sec": None, "n_events": 0,
            "strategy_ids": [],
        }
        if is_live:
            mts = self._live_ctx.get("market_start_ts") or meta.get("market_start_ts")
            sec = self._live_ctx.get("sec")
            strategy_ids = list(self._live_ctx.get("active_strategy_ids") or [])
        else:
            row = next((s for s in sessions if s["session_id"] == focus), None)
            mts = (row or {}).get("market_start_ts") or meta.get("market_start_ts")
            sec = 0
            strategy_ids = list((row or {}).get("strategy_ids") or meta.get("strategy_ids") or [])
        return {
            "agent_session_id": focus,
            "is_live": is_live,
            "market_start_ts": mts,
            "sec": sec,
            "n_events": meta.get("n_events") or 0,
            "strategy_ids": strategy_ids,
            "live_session_id": live_sid,
            "sessions": sessions,
        }

    def _emit_agent_focus(self) -> None:
        if self._human_sid:
            self.socketio.emit("agent.session", self._agent_focus_payload(), to=self._human_sid)

    def _set_agent_session(self, session_id: str | None) -> dict:
        self._live_ctx["agent_session_id"] = session_id
        payload = self._agent_focus_payload()
        self._emit_agent_focus()
        return payload

    def _resolve_agent_session_id(self, payload: dict | None) -> str:
        sid = (payload or {}).get("session_id") or (payload or {}).get("agent_session_id")
        sid = sid or self._live_ctx.get("agent_session_id") or self._live_ctx.get("session_id")
        if not sid:
            raise Exception("no session_id")
        return sid

    def _bind_agent_chat(self) -> None:
        @self.socketio.on("agent.chat.history")
        def on_history(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                session_id = self._resolve_agent_session_id(payload)
            except Exception as e:
                return {"error": str(e)}
            return {
                "ok": True,
                "session_id": session_id,
                "messages": load_thread(Path(self.cfg["history_dir"]), session_id),
                "busy": bool(
                    self._agent_busy
                    and self._live_ctx.get("agent_session_id") == session_id
                ),
            }

        @self.socketio.on("agent.session.delete")
        def on_session_delete(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                session_id = self._resolve_agent_session_id(payload)
            except Exception as e:
                return {"error": str(e)}
            live_sid = self._live_ctx.get("session_id")
            if live_sid and live_sid == session_id:
                try:
                    self._request_to_data("round.unload", {}, actor="user")
                except Exception as e:
                    return {"error": str(e)}
            try:
                deleted = delete_session(Path(self.cfg["history_dir"]), session_id)
            except Exception as e:
                return {"error": str(e)}
            if self._live_ctx.get("agent_session_id") == session_id:
                self._live_ctx["agent_session_id"] = None
            focus = self._agent_focus_payload()
            self._emit_agent_focus()
            self._request_to_data("session.sync", {}, actor="user")
            if self._human_sid:
                self.socketio.emit("agent.session.deleted", {
                    "session_id": deleted["session_id"],
                    "account_id": deleted["account_id"],
                    **focus,
                }, to=self._human_sid)
            return {"ok": True, **deleted, **focus}

        @self.socketio.on("agent.executions.list")
        def on_exec_list(_payload=None):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            return {"ok": True, **self._agent_focus_payload()}

        @self.socketio.on("agent.session.select")
        def on_session_select(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            sid = (payload or {}).get("session_id")
            if not sid:
                return {"error": "session_id required"}
            return {"ok": True, **self._set_agent_session(sid)}

        @self.socketio.on("agent.rules.apply")
        def on_rules_apply(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            body = payload or {}
            try:
                result = self._agent_apply_rules(
                    body["strategy_id"], body["rules"], body.get("name"), body.get("description"))
                return result
            except Exception as e:
                self._emit_generate("error", str(e))
                return {"error": str(e)}

        @self.socketio.on("agent.chat.send")
        def on_send(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            body = payload or {}
            account_id = body.get("account_id") or self._active_account_id
            if not account_id:
                return {"error": "no active account"}
            try:
                session_id = self._resolve_agent_session_id(body)
            except Exception as e:
                return {"error": str(e)}
            text = (body.get("text") or "").strip()
            if not text:
                return {"error": "empty message"}
            if self._agent_busy:
                return {"error": "agent busy"}
            if body.get("selected_strategy_id") is not None:
                self._live_ctx["selected_strategy_id"] = body.get("selected_strategy_id")
            self._live_ctx["agent_session_id"] = session_id
            self._agent_busy = True
            if self._human_sid:
                self.socketio.emit(
                    "agent.chat.status",
                    {"phase": "thinking", "detail": "Preparazione…"},
                    to=self._human_sid,
                )

            def _emit_progress(detail: str) -> None:
                sid = self._human_sid
                if sid:
                    self.socketio.emit(
                        "agent.chat.status",
                        {"phase": "thinking", "detail": detail},
                        to=sid,
                    )

            def _run_agent_turn():
                # Thread OS: call_model non deve bloccare l'hub eventlet (ping/reconnect).
                try:
                    result = self.agent_service.run_turn(
                        session_id, account_id, text, on_progress=_emit_progress,
                    )
                    sid = self._human_sid
                    if sid:
                        self.socketio.emit("agent.chat.message", {
                            "message": result["message"],
                            "proposed_rules": result.get("proposed_rules"),
                            "session_id": session_id,
                            "account_id": account_id,
                        }, to=sid)
                except Exception as e:
                    sid = self._human_sid
                    if sid:
                        self.socketio.emit("agent.chat.error", {"message": str(e)}, to=sid)
                finally:
                    self._agent_busy = False
                    sid = self._human_sid
                    if sid:
                        self.socketio.emit("agent.chat.status", {"phase": "idle"}, to=sid)

            threading.Thread(target=_run_agent_turn, daemon=True, name="agent-turn").start()
            return {"ok": True, "accepted": True}

    def _emit_stats(self, name: str, payload: dict) -> None:
        if self._human_sid:
            self.socketio.emit(name, payload, to=self._human_sid)

    def _emit_analyzes(self) -> None:
        self._emit_stats("stats.analyzes", {
            "analyzes": list_analyzes(Path(self.cfg["history_dir"])),
        })

    def _emit_simulations(self, selected_id: str | None = None) -> None:
        payload = {"simulations": list_simulations(Path(self.cfg["history_dir"]))}
        if selected_id is not None:
            payload["selected_id"] = selected_id
        self._emit_stats("stats.simulations", payload)

    def _bind_stats(self) -> None:
        @self.socketio.on("stats.analyze.list")
        def on_list(_payload=None):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            items = list_analyzes(Path(self.cfg["history_dir"]))
            return {"ok": True, "analyzes": items}

        @self.socketio.on("stats.analyze.delete")
        def on_delete(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                delete_analyze(Path(self.cfg["history_dir"]), payload["analyze_id"])
            except Exception as e:
                return {"error": str(e)}
            self._emit_analyzes()
            return {"ok": True}

        @self.socketio.on("stats.simulation.list")
        def on_sim_list(_payload=None):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            return {"ok": True, "simulations": list_simulations(Path(self.cfg["history_dir"]))}

        @self.socketio.on("stats.simulation.load")
        def on_sim_load(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                data = load_simulation(Path(self.cfg["history_dir"]), payload["simulation_id"])
            except Exception as e:
                return {"error": str(e)}
            return {"ok": True, "simulation": data}

        @self.socketio.on("stats.simulation.delete")
        def on_sim_delete(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            try:
                delete_simulation(Path(self.cfg["history_dir"]), payload["simulation_id"])
            except Exception as e:
                return {"error": str(e)}
            self._emit_simulations()
            return {"ok": True}

        @self.socketio.on("stats.job.cancel")
        def on_cancel(_payload=None):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            return self._stats_request_cancel()

        @self.socketio.on("stats.chat.history")
        def on_history(_payload=None):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            return {
                "ok": True,
                "messages": load_stats_thread(Path(self.cfg["history_dir"])),
                "busy": bool(self._stats_chat_busy),
            }

        @self.socketio.on("stats.chat.clear")
        def on_chat_clear(_payload=None):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            if self._stats_chat_busy:
                return {"error": "stats chat busy"}
            clear_stats_thread(Path(self.cfg["history_dir"]))
            return {"ok": True, "messages": []}

        @self.socketio.on("stats.chat.send")
        def on_chat_send(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            body = payload or {}
            text = (body.get("text") or "").strip()
            if not text:
                return {"error": "empty message"}
            simulation_ids = body["simulation_ids"]
            if not simulation_ids:
                return {"error": "simulation_ids required"}
            if self._stats_chat_busy:
                return {"error": "stats chat busy"}
            self._stats_chat_busy = True
            self._emit_stats("stats.chat.status", {"phase": "thinking"})

            def _run():
                try:
                    hist = Path(self.cfg["history_dir"])
                    sims_ctx = []
                    for sid in simulation_ids:
                        sim = load_simulation(hist, sid)
                        sims_ctx.append({
                            "id": sim["id"], "label": simulation_label(sim),
                            "strategy_id": sim["strategy_id"],
                            "strategy_name": sim["strategy_name"],
                            "strategy_version": sim["strategy_version"],
                            "day_from": sim["day_from"], "day_to": sim["day_to"],
                            "summary": sim["summary"],
                        })
                    result = self.stats_service.run_turn(text, sims_ctx)
                    self._emit_stats("stats.chat.message", {
                        "message": result["message"],
                        "proposed_rules": result.get("proposed_rules"),
                    })
                except Exception as e:
                    print(f"stats chat error: {e}", flush=True)
                    self._emit_stats("stats.job.error", {"message": str(e), "kind": "chat"})
                finally:
                    self._stats_chat_busy = False
                    self._emit_stats("stats.chat.status", {"phase": "idle"})

            threading.Thread(target=_run, daemon=True, name="stats-chat").start()
            return {"ok": True, "accepted": True}

        @self.socketio.on("stats.rules.apply")
        def on_rules_apply(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            if self._stats_chat_busy:
                return {"error": "stats chat busy"}
            body = payload or {}
            simulation_ids = body["simulation_ids"]
            rules = body["rules"]
            analyze_id = body.get("analyze_id")
            name = body.get("name")
            self._stats_chat_busy = True
            self._emit_stats("stats.chat.status", {"phase": "thinking"})

            def _run():
                try:
                    result = self.stats_service.apply_rules(rules, analyze_id, name)
                    aid = result["analyze"]["id"]
                    self._emit_stats("stats.analyzes", {
                        "analyzes": list_analyzes(Path(self.cfg["history_dir"])),
                        "applied_id": aid,
                    })
                    started = self._stats_start_job("analyze", {
                        "analyze_id": aid, "simulation_ids": simulation_ids,
                    })
                    if "error" in started:
                        self._emit_stats("stats.job.error", {
                            "message": started["error"], "kind": "apply",
                        })
                except Exception as e:
                    print(f"stats rules.apply error: {e}", flush=True)
                    self._emit_stats("stats.job.error", {"message": str(e), "kind": "apply"})
                finally:
                    self._stats_chat_busy = False
                    self._emit_stats("stats.chat.status", {"phase": "idle"})

            threading.Thread(target=_run, daemon=True, name="stats-apply").start()
            return {"ok": True, "accepted": True}

        @self.socketio.on("stats.backtest.start")
        def on_backtest(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            return self._stats_start_job("backtest", payload or {})

        @self.socketio.on("stats.analyze.start")
        def on_analyze(payload):
            from flask import request
            if self._role_for_sid(request.sid) != "human":
                return {"error": "not allowed"}
            return self._stats_start_job("analyze", payload or {})

    def _stats_request_cancel(self) -> dict:
        """Cancel se job busy (anche prima che _stats_runner sia assegnato)."""
        if not self._stats_busy:
            return {"error": "no job running"}
        self._stats_cancel_requested = True
        runner = self._stats_runner
        if runner is not None:
            runner.cancel()
        return {"ok": True}

    def _stats_start_job(self, kind: str, body: dict) -> dict:
        """Avvia backtest|analyze in thread OS; un solo job alla volta."""
        if self._stats_busy:
            self._emit_stats("stats.job.error", {"message": "job already running", "kind": kind})
            return {"error": "job already running"}
        simulation_ids = body.get("simulation_ids")
        if kind == "analyze":
            simulation_ids = body["simulation_ids"]
            day_from = ""
            day_to = ""
        else:
            day_from = body["day_from"]
            day_to = body["day_to"]
        self._stats_day_from = day_from
        self._stats_day_to = day_to
        # Ordine: clear cancel prima di busy, così cancel post-busy non viene perso.
        self._stats_cancel_requested = False
        self._stats_busy = True

        def _run():
            import time
            t0 = time.monotonic()
            runner = RoundBatchRunner(int(self.cfg["stats_workers"]))
            self._stats_runner = runner
            if self._stats_cancel_requested:
                runner.cancel()
            try:
                repo = RoundRepository(
                    Path(self.cfg["data_dir"]), float(self.cfg["stall_reconnect_sec"]))
                size = float(self.cfg["default_order_size_usd"])
                hist = Path(self.cfg["history_dir"])
                job_day_from = day_from
                job_day_to = day_to
                sim_meta = []
                if kind == "backtest":
                    rounds, skipped = list_batch_rounds(repo, job_day_from, job_day_to)
                    sid = body["strategy_id"]
                    st = load_strategy(strategies_dir(hist), sid)
                    ver = int(body["strategy_version"]) if body.get("strategy_version") is not None else st["version"]
                    mp = strategy_module_path(strategies_dir(hist), sid, ver)
                    label = st["name"]
                    tasks = [{
                        "job": "strategy",
                        "data_dir": str(self.cfg["data_dir"]),
                        "stall_reconnect_sec": float(self.cfg["stall_reconnect_sec"]),
                        "bin_path": r["bin_path"],
                        "market_start_ts": r["market_start_ts"],
                        "hour_utc": r["hour_utc"],
                        "module_path": str(mp),
                        "strategy_id": sid,
                        "size_up": size,
                        "size_down": size,
                    } for r in rounds]
                else:
                    aid = body["analyze_id"]
                    mp = analyze_module_path(hist, aid)
                    label = aid
                    skipped = 0
                    tasks = []
                    days = []
                    for simulation_id in simulation_ids:
                        if not simulation_has_orders(hist, simulation_id):
                            raise Exception(
                                f"simulation has no orders (JSON v1 or missing sqlite): {simulation_id}"
                            )
                        sim = load_simulation(hist, simulation_id)
                        days.append(sim["day_from"])
                        days.append(sim["day_to"])
                        strategy = {
                            "id": sim["strategy_id"],
                            "name": sim["strategy_name"],
                            "version": sim["strategy_version"],
                        }
                        sim_meta.append({
                            "id": sim["id"], "label": simulation_label(sim),
                            "strategy": strategy,
                        })
                        for r in sim["rounds"]:
                            if not r["ok"]:
                                skipped += 1
                                continue
                            mts = int(r["market_start_ts"])
                            tasks.append({
                                "job": "analyze",
                                "data_dir": str(self.cfg["data_dir"]),
                                "stall_reconnect_sec": float(self.cfg["stall_reconnect_sec"]),
                                "bin_path": str(repo.bin_path(mts)),
                                "market_start_ts": mts,
                                "hour_utc": int(r["hour_utc"]),
                                "module_path": str(mp),
                                "orders": load_round_orders(hist, simulation_id, mts),
                                "strategy": strategy,
                                "simulation_id": simulation_id,
                            })
                    job_day_from = min(days)
                    job_day_to = max(days)
                    self._stats_day_from = job_day_from
                    self._stats_day_to = job_day_to

                # Cancel durante listing/prep: niente pool, niente reduce/done.
                if self._stats_cancel_requested:
                    runner.cancel()
                if runner._cancel:
                    raise BatchCancelled()

                def on_progress(done, total, errors):
                    self._emit_stats("stats.job.progress", {
                        "kind": kind, "done": done, "total": total, "errors": errors,
                    })

                results = runner.run(tasks, on_progress)
                elapsed = time.monotonic() - t0
                n_err = sum(1 for r in results if not r["ok"])
                summary = {
                    "name": label, "day_from": job_day_from, "day_to": job_day_to,
                    "workers": int(self.cfg["stats_workers"]),
                    "elapsed_sec": round(elapsed, 2),
                    "skipped": skipped, "errors": n_err, "rounds": len(results),
                }
                if kind == "backtest":
                    table = reduce_strategy_rows(results)
                    sim = create_simulation(
                        hist, strategy_id=sid, strategy_name=label, strategy_version=ver,
                        day_from=job_day_from, day_to=job_day_to,
                        summary=summary, table=table, rounds=results,
                    )
                    self._emit_stats("stats.job.done", {
                        "kind": "backtest", "table": table, "summary": sim["summary"],
                        "simulation_id": sim["id"], "rounds": sim["rounds"],
                    })
                    self._emit_simulations(sim["id"])
                else:
                    summary["simulation_ids"] = [m["id"] for m in sim_meta]
                    reduce_fn = load_reduce_results(mp)
                    sections = []
                    for meta in sim_meta:
                        sid = meta["id"]
                        sim_results = [r for r in results if r["simulation_id"] == sid]
                        md = reduce_fn(sim_results) if reduce_fn else reduce_analyze_fallback(sim_results)
                        sections.append(f"## {meta['label']}\n\n{md}")
                    combined = "\n\n---\n\n".join(sections)
                    result_msg = append_stats_message(hist, "assistant", combined)
                    self._emit_stats("stats.job.done", {
                        "kind": "analyze", "markdown": combined, "summary": summary,
                    })
                    self._emit_stats("stats.chat.message", {"message": result_msg})
            except BatchCancelled:
                print("stats job cancelled", flush=True)
                self._emit_stats("stats.job.cancelled", {"kind": kind})
            except Exception as e:
                print(f"stats job error: {e}", flush=True)
                self._emit_stats("stats.job.error", {"message": str(e), "kind": kind})
            finally:
                self._stats_runner = None
                self._stats_busy = False
                self._stats_cancel_requested = False

        threading.Thread(target=_run, daemon=True, name=f"stats-{kind}").start()
        return {"ok": True, "accepted": True}

    def _codegen_progress(self, phase: str, message: str) -> None:
        self._emit_generate(phase, message)

    def _codegen_source(self, rules: str) -> str:
        model = self.cfg["cursor_model"]
        system_prompt = reload_strategy_codegen_system_prompt()
        self.cfg["strategy_codegen_system_prompt"] = system_prompt
        return generate_strategy_module(
            rules, model_id=model["id"], params=model["params"],
            system_prompt=system_prompt, max_attempts=3,
            model_label=model["label"], on_progress=self._codegen_progress,
        )

    def _codegen_coded_rules(self, source: str) -> str:
        model = self.cfg["cursor_model"]
        try:
            return generate_coded_rules(
                source, model_id=model["id"], params=model["params"], max_attempts=2,
                model_label=model["label"], on_progress=self._codegen_progress,
            )
        except Exception as e:
            print(f"coded_rules generation failed: {e}", flush=True)
            self._emit_generate("coded_rules_warn", f"Coded rules saltate: {e}")
            return ""

    def _strategy_create_with_codegen(self, body: dict) -> dict:
        stype = body["type"]
        rules = body.get("rules") or ""
        module_file = None
        strategy_id = None
        coded_rules = ""
        if stype == "deterministic":
            source = self._codegen_source(rules)
            coded_rules = self._codegen_coded_rules(source)
            strategy_id = uuid.uuid4().hex[:12]
            self._emit_generate("saving", "Salvataggio strategia…", strategy_id)
            module_file = write_module(self.strategies_root, strategy_id, source, 1)
        ipc_payload = {
            "name": body["name"], "type": stype, "description": body.get("description") or "",
            "rules": rules, "coded_rules": coded_rules, "module_file": module_file,
            "strategy_id": strategy_id,
        }
        try:
            result = self._request_to_data("strategy.create", ipc_payload, actor="user")
        except Exception:
            if strategy_id is not None:
                py = strategy_module_path(self.strategies_root, strategy_id, 1)
                if py.is_file():
                    py.unlink()
            raise
        self._emit_generate("done", "Strategia pronta", (result.get("strategy") or {}).get("id"))
        return result

    def _strategy_update_with_codegen(self, body: dict) -> dict:
        sid = body["strategy_id"]
        data = load_strategy(self.strategies_root, sid)
        name = body["name"].strip()
        description = body.get("description") or ""
        rules = body.get("rules")
        rules_changed = bool(body.get("rules_changed") and rules is not None)
        module_file = None
        coded_rules = None
        module_rebuilt = False
        if rules_changed and data["type"] == "deterministic":
            source = self._codegen_source(rules)
            coded_rules = self._codegen_coded_rules(source)
            new_ver = data["version"] + 1
            self._emit_generate("saving", "Salvataggio strategia…", sid)
            module_file = write_module(self.strategies_root, sid, source, new_ver)
            module_rebuilt = True
        ipc_payload = {
            "strategy_id": sid, "name": name, "description": description,
            "module_rebuilt": module_rebuilt,
            "rules": rules if module_rebuilt or data["type"] != "deterministic" else None,
            "module_file": module_file, "coded_rules": coded_rules,
        }
        result = self._request_to_data("strategy.update", ipc_payload, actor="user")
        self._emit_generate("done", "Strategia aggiornata", sid)
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
            if name == "session":
                prev_live = self._live_ctx.get("session_id")
                new_live = payload.get("session_id")
                was_loaded = self._live_ctx.get("loaded")
                self._live_ctx["loaded"] = bool(payload.get("loaded"))
                self._live_ctx["market_start_ts"] = payload.get("market_start_ts")
                self._live_ctx["session_id"] = new_live
                self._live_ctx["sec"] = payload.get("sec")
                if "bot_active" in payload:
                    self._bot_active = bool(payload["bot_active"])
                    self._live_ctx["bot_active"] = self._bot_active
                if "active_strategy_ids" in payload:
                    self._active_strategy_ids = list(payload.get("active_strategy_ids") or [])
                    self._live_ctx["active_strategy_ids"] = list(self._active_strategy_ids)
                if "active_strategies" in payload:
                    self._active_strategies = list(payload.get("active_strategies") or [])
                    self._live_ctx["active_strategies"] = list(self._active_strategies)
                if "active_account_id" in payload:
                    self._active_account_id = payload.get("active_account_id")
                # Nuova sessione live → focus forzato (anche se c'era una storica selezionata).
                if new_live and new_live != prev_live:
                    self._live_ctx["agent_session_id"] = new_live
                    self._broadcast(name, payload)
                    self._emit_agent_focus()
                    continue
                # Unload: live sparisce → ricalcola focus su storico account.
                if was_loaded and not self._live_ctx["loaded"]:
                    self._broadcast(name, payload)
                    self._emit_agent_focus()
                    continue
                if self._live_ctx.get("agent_session_id") == new_live:
                    # Aggiorna Round/Sec live nel context senza cambiare focus.
                    self._broadcast(name, payload)
                    self._emit_agent_focus()
                    continue
            if name == "bot.status" and "bot_active" in payload:
                self._bot_active = bool(payload["bot_active"])
                self._live_ctx["bot_active"] = self._bot_active
                if "active_strategy_ids" in payload:
                    self._active_strategy_ids = list(payload.get("active_strategy_ids") or [])
                    self._live_ctx["active_strategy_ids"] = list(self._active_strategy_ids)
                if "active_strategies" in payload:
                    self._active_strategies = list(payload.get("active_strategies") or [])
                    self._live_ctx["active_strategies"] = list(self._active_strategies)
            if name == "accounts" and "active_account_id" in payload:
                prev_acc = self._active_account_id
                self._active_account_id = payload.get("active_account_id")
                self._broadcast(name, payload)
                if self._active_account_id != prev_acc:
                    self._live_ctx["agent_session_id"] = None
                    self._emit_agent_focus()
                continue
            self._broadcast(name, payload)


def run_server_process(cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
    ServerBridge(cfg, cmd_conn, evt_conn).run()
