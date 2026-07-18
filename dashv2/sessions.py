"""Registro sessioni: ownership account alla creazione."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dashv2.execution_log import execution_session_meta


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sessions_dir(history_dir: Path) -> Path:
    root = history_dir / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _session_path(history_dir: Path, session_id: str) -> Path:
    return sessions_dir(history_dir) / f"session_{session_id}.json"


def create_session(
    history_dir: Path,
    session_id: str,
    account_id: str,
    market_start_ts: int,
    started_at_utc: str,
    active_strategy_ids: list[str],
) -> dict:
    payload = {
        "session_id": session_id,
        "account_id": account_id,
        "market_start_ts": market_start_ts,
        "started_at_utc": started_at_utc,
        "active_strategy_ids": list(active_strategy_ids),
    }
    path = _session_path(history_dir, session_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return payload


def load_session(history_dir: Path, session_id: str) -> dict:
    path = _session_path(history_dir, session_id)
    if not path.is_file():
        raise Exception(f"session not found: {session_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def delete_session(history_dir: Path, session_id: str) -> dict:
    """Cancella registro, exec log, chat e ordini ledger della sessione."""
    from dashv2.agent_chat import delete_thread
    from dashv2.execution_log import delete_execution_session
    from dashv2.history import accounts_dir, remove_session_orders

    data = load_session(history_dir, session_id)
    account_id = data["account_id"]
    remove_session_orders(accounts_dir(history_dir), account_id, session_id)
    delete_thread(history_dir, session_id)
    delete_execution_session(history_dir, session_id)
    path = _session_path(history_dir, session_id)
    if path.is_file():
        path.unlink()
    return {"session_id": session_id, "account_id": account_id}


def list_sessions_for_account(
    history_dir: Path,
    account_id: str,
    live_session_id: str | None = None,
) -> list[dict]:
    """Sessioni dell'account, merge meta exec log; live in testa se appartiene all'account."""
    items: list[dict] = []
    for path in sessions_dir(history_dir).glob("session_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["account_id"] != account_id:
            continue
        sid = data["session_id"]
        meta = execution_session_meta(history_dir, sid)
        items.append({
            "session_id": sid,
            "account_id": account_id,
            "market_start_ts": data.get("market_start_ts") or meta.get("market_start_ts"),
            "started_at_utc": data.get("started_at_utc"),
            "last_sec": meta.get("last_sec"),
            "n_events": meta.get("n_events") or 0,
            "updated_at_utc": meta.get("updated_at_utc") or data.get("started_at_utc"),
            "strategy_ids": meta.get("strategy_ids") or list(data.get("active_strategy_ids") or []),
        })
    items.sort(key=lambda x: x.get("started_at_utc") or "", reverse=True)
    if live_session_id:
        for i, it in enumerate(items):
            if it["session_id"] == live_session_id:
                items.insert(0, items.pop(i))
                break
    return items
