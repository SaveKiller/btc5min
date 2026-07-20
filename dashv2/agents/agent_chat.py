"""Persistenza thread chat AI Agent per session_id."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def agent_dir(history_dir: Path) -> Path:
    root = history_dir / "agent"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _thread_path(history_dir: Path, session_id: str) -> Path:
    d = agent_dir(history_dir) / f"session_{session_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d / "thread.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_thread(history_dir: Path, session_id: str) -> list[dict]:
    path = _thread_path(history_dir, session_id)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["messages"])


def thread_has_chat(history_dir: Path, session_id: str) -> bool:
    """True se esiste un thread con almeno un messaggio (non crea cartelle)."""
    path = history_dir / "agent" / f"session_{session_id}" / "thread.json"
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return bool(data["messages"])


def save_thread(history_dir: Path, session_id: str, messages: list[dict], account_id: str | None = None) -> None:
    path = _thread_path(history_dir, session_id)
    payload = {
        "session_id": session_id,
        "updated_at_utc": _utc_now_iso(),
        "messages": messages,
    }
    if account_id is not None:
        payload["account_id"] = account_id
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def append_message(
    history_dir: Path, session_id: str, role: str, content: str, account_id: str | None = None,
) -> dict:
    messages = load_thread(history_dir, session_id)
    msg = {"role": role, "content": content, "ts": _utc_now_iso()}
    messages.append(msg)
    save_thread(history_dir, session_id, messages, account_id=account_id)
    return msg


def delete_thread(history_dir: Path, session_id: str) -> None:
    """Cancella la cartella chat della sessione."""
    import shutil
    d = agent_dir(history_dir) / f"session_{session_id}"
    if d.is_dir():
        shutil.rmtree(d)


def clear_thread(history_dir: Path, session_id: str, account_id: str | None = None) -> None:
    save_thread(history_dir, session_id, [], account_id=account_id)
