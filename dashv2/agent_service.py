"""Servizio AI Agent: contesto, tool controllati, turno Grok via Cursor SDK."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from dashv2.agent_chat import append_message, load_thread
from dashv2.config import reload_agent_system_prompt
from dashv2.cursor_client import call_model
from dashv2.execution_log import execution_session_meta, read_execution_session
from dashv2.history import account_summary, accounts_dir, load_account, order_rows_from_ledger
from dashv2.strategies import list_strategies, load_strategy, module_path, strategies_dir

_TOOL_FENCE_RE = re.compile(r"```tool\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_MAX_TOOL_ROUNDS = 3
_HISTORY_RECENT = 40
_THREAD_TAIL = 30
_EXEC_TAIL = 40


class AgentService:
    """Orchestrazione chat: snapshot contesto + loop tool + call_model."""

    def __init__(self, cfg: dict, tool_ctx_fn) -> None:
        self.cfg = cfg
        self.history_dir = Path(cfg["history_dir"])
        self.strategies_root = strategies_dir(self.history_dir)
        self.accounts_root = accounts_dir(self.history_dir)
        self._tool_ctx_fn = tool_ctx_fn  # callable → dict live (session, selected_strategy_id, …)
        self._apply_rules_fn = None  # set dal server: (sid, rules, name, desc) → strategy summary

    def set_apply_rules_fn(self, fn) -> None:
        self._apply_rules_fn = fn

    def run_turn(self, session_id: str, account_id: str, user_text: str) -> dict:
        append_message(self.history_dir, session_id, "user", user_text, account_id=account_id)
        system = reload_agent_system_prompt()
        live = self._tool_ctx_fn()
        context = self._build_context(account_id, live)
        thread = load_thread(self.history_dir, session_id)[-_THREAD_TAIL:]
        tool_catalog = self._tool_catalog_text()
        messages_blob = self._format_thread(thread)
        prompt = (
            f"{system}\n\n"
            f"=== TOOL DISPONIBILI ===\n{tool_catalog}\n\n"
            f"=== CONTESTO CORRENTE ===\n{context}\n\n"
            f"=== CRONOLOGIA CHAT ===\n{messages_blob}\n\n"
            "Rispondi al messaggio utente. Se ti serve un tool, usa solo il fence ```tool."
        )
        model = self.cfg["agent_cursor_model"]
        reply = None
        with tempfile.TemporaryDirectory(prefix="dashv2-agent-") as td:
            for _ in range(_MAX_TOOL_ROUNDS + 1):
                raw = call_model(
                    prompt, model_id=model["id"], params=model["params"], cwd=td,
                    reject_meta=False,
                )
                tool_req = self._parse_tool(raw)
                if tool_req is None:
                    reply = raw.strip()
                    break
                try:
                    result = self._run_tool(tool_req["tool"], tool_req.get("args") or {}, account_id, live)
                except Exception as e:
                    result = {"error": str(e)}
                prompt = (
                    f"{system}\n\n"
                    f"=== TOOL RESULT ({tool_req['tool']}) ===\n"
                    f"{json.dumps(result, ensure_ascii=False, indent=2)}\n\n"
                    f"=== CONTESTO CORRENTE ===\n{context}\n\n"
                    f"=== CRONOLOGIA CHAT ===\n{messages_blob}\n\n"
                    "Continua: rispondi all'utente in italiano, oppure richiedi un altro tool "
                    "(usa SOLO i nomi tool elencati nel catalogo)."
                )
            if reply is None:
                reply = raw.strip()
        msg = append_message(self.history_dir, session_id, "assistant", reply, account_id=account_id)
        proposed = self._extract_proposed_rules(reply)
        return {"message": msg, "proposed_rules": proposed}

    def _tool_catalog_text(self) -> str:
        return (
            "Nomi tool ESATTI (non inventare varianti):\n"
            "strategy.list args={}\n"
            "strategy.get args={strategy_id}\n"
            "account.summary args={}\n"
            "history.recent args={limit?}\n"
            "session.snapshot args={}\n"
            "exec_log.session args={session_id?}\n"
            "round.summary args={market_start_ts}\n"
            "round.tick args={market_start_ts, sec}  # un solo sec alla volta\n"
            "rounds.list args={day_utc}\n"
            "strategy.apply_rules args={strategy_id, rules, name?, description?, confirm:true}\n"
        )

    def _normalize_tool_name(self, name: str) -> str:
        aliases = {
            "round.ticks": "round.tick",
            "rounds.tick": "round.tick",
            "round.get_tick": "round.tick",
            "round.get": "round.summary",
        }
        return aliases.get(name, name)

    def _build_context(self, account_id: str, live: dict) -> str:
        data = load_account(self.accounts_root, account_id)
        summary = account_summary(data)
        strategies = list_strategies(self.strategies_root)
        strat_lines = [
            f"- {s['id']}: {s['name']} ({s['type']}) — {(s.get('description') or '')[:120]}"
            for s in strategies[:30]
        ]
        selected_id = live.get("selected_strategy_id")
        selected_block = ""
        if selected_id:
            s = load_strategy(self.strategies_root, selected_id)
            py = ""
            mp = module_path(self.strategies_root, selected_id)
            if mp.is_file():
                py = mp.read_text(encoding="utf-8")[:8000]
            selected_block = (
                f"\nStrategia selezionata {selected_id} ({s['name']}):\n"
                f"RULES:\n{s.get('rules', '')}\n\nPYTHON:\n{py}\n"
            )
        live_sid = live.get("session_id")
        focus_sid = live.get("agent_session_id") or live_sid
        is_live = bool(focus_sid and focus_sid == live_sid)
        meta = execution_session_meta(self.history_dir, focus_sid) if focus_sid else {
            "session_id": None, "market_start_ts": None, "last_sec": None,
            "n_events": 0, "strategy_ids": [],
        }
        if is_live:
            mts = live.get("market_start_ts") or meta.get("market_start_ts")
            sec = live.get("sec")
            strategy_ids = list(live.get("active_strategy_ids") or [])
        else:
            mts = meta.get("market_start_ts")
            sec = 0
            strategy_ids = list(meta.get("strategy_ids") or [])
        exec_tail = read_execution_session(self.history_dir, focus_sid, limit=_EXEC_TAIL) if focus_sid else []
        all_rows = order_rows_from_ledger(data.get("orders", []))
        session_orders = [r for r in all_rows if r.get("session_id") == focus_sid][:_HISTORY_RECENT]
        return json.dumps({
            "account": summary,
            "strategies": strat_lines,
            "selected_strategy_id": selected_id,
            "selected_detail": selected_block,
            "session": {
                "session_id": focus_sid,
                "is_live": is_live,
                "market_start_ts": mts,
                "sec": sec,
                "n_events": meta.get("n_events"),
                "strategy_ids": strategy_ids,
                "bot_active": live.get("bot_active") if is_live else False,
                "active_strategy_ids": strategy_ids,
            },
            "live_engine": {
                "loaded": live.get("loaded"),
                "market_start_ts": live.get("market_start_ts"),
                "session_id": live_sid,
                "sec": live.get("sec"),
            },
            "session_orders": session_orders,
            "exec_log_tail": exec_tail,
        }, ensure_ascii=False, indent=2)

    def _format_thread(self, thread: list[dict]) -> str:
        lines = []
        for m in thread:
            lines.append(f"{m['role'].upper()}: {m['content']}")
        return "\n\n".join(lines)

    def _parse_tool(self, text: str) -> dict | None:
        m = _TOOL_FENCE_RE.search(text)
        if not m:
            return None
        return json.loads(m.group(1).strip())

    def _extract_proposed_rules(self, reply: str) -> dict | None:
        """Estrae blocco rules proposto se presente (```rules ... ```)."""
        m = re.search(r"```rules\s*\n(.*?)```", reply, re.DOTALL | re.IGNORECASE)
        if not m:
            return None
        return {"rules": m.group(1).strip()}

    def _run_tool(self, name: str, args: dict, account_id: str, live: dict) -> dict:
        name = self._normalize_tool_name(name)
        if name == "strategy.list":
            return {"strategies": list_strategies(self.strategies_root)}
        if name == "strategy.get":
            sid = args["strategy_id"]
            data = load_strategy(self.strategies_root, sid)
            py = ""
            mp = module_path(self.strategies_root, sid)
            if mp.is_file():
                py = mp.read_text(encoding="utf-8")
            return {"strategy": data, "python_source": py}
        if name == "account.summary":
            data = load_account(self.accounts_root, account_id)
            return {"account": account_summary(data)}
        if name == "history.recent":
            limit = int(args["limit"]) if "limit" in args else _HISTORY_RECENT
            data = load_account(self.accounts_root, account_id)
            rows = order_rows_from_ledger(data.get("orders", []))
            return {"rows": rows[:limit]}
        if name == "session.snapshot":
            focus = live.get("agent_session_id") or live.get("session_id")
            meta = execution_session_meta(self.history_dir, focus) if focus else {}
            is_live = bool(focus and focus == live.get("session_id"))
            return {
                "session_id": focus,
                "is_live": is_live,
                "market_start_ts": live.get("market_start_ts") if is_live else meta.get("market_start_ts"),
                "sec": live.get("sec") if is_live else meta.get("last_sec"),
                "bot_active": live.get("bot_active") if is_live else False,
                "active_strategy_ids": live.get("active_strategy_ids") if is_live else [],
                "live_engine_session_id": live.get("session_id"),
            }
        if name == "exec_log.session":
            sid = args.get("session_id") or live.get("agent_session_id") or live.get("session_id")
            if not sid:
                raise Exception("no session_id for exec_log")
            return {"session_id": sid, "rows": read_execution_session(self.history_dir, sid)}
        if name == "round.summary":
            return live["round_tools"].summary(int(args["market_start_ts"]))
        if name == "round.tick":
            mts = int(args["market_start_ts"])
            if "secs" in args:
                return {"ticks": [live["round_tools"].tick(mts, int(s)) for s in args["secs"]]}
            return live["round_tools"].tick(mts, int(args["sec"]))
        if name == "rounds.list":
            return {"rounds": live["round_tools"].list_day(str(args["day_utc"]))}
        if name == "strategy.apply_rules":
            if not args.get("confirm"):
                return {"error": "confirm=true required; explain rules first and wait for user confirmation"}
            if self._apply_rules_fn is None:
                raise Exception("apply_rules not configured")
            return self._apply_rules_fn(
                args["strategy_id"], args["rules"],
                args.get("name"), args.get("description"),
            )
        raise Exception(f"unknown tool: {name}")
