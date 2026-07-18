"""Persistenza thread chat AI Agent per account."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def agent_dir(history_dir: Path) -> Path:
    root = history_dir / "agent"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _thread_path(history_dir: Path, account_id: str) -> Path:
    d = agent_dir(history_dir) / f"account_{account_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d / "thread.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_thread(history_dir: Path, account_id: str) -> list[dict]:
    path = _thread_path(history_dir, account_id)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["messages"])


def save_thread(history_dir: Path, account_id: str, messages: list[dict]) -> None:
    path = _thread_path(history_dir, account_id)
    payload = {"account_id": account_id, "updated_at_utc": _utc_now_iso(), "messages": messages}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def append_message(history_dir: Path, account_id: str, role: str, content: str) -> dict:
    messages = load_thread(history_dir, account_id)
    msg = {"role": role, "content": content, "ts": _utc_now_iso()}
    messages.append(msg)
    save_thread(history_dir, account_id, messages)
    return msg


def clear_thread(history_dir: Path, account_id: str) -> None:
    save_thread(history_dir, account_id, [])
