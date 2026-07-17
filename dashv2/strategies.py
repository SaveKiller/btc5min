"""Repository strategy JSON: un file per strategy + stato active_ids."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
STRATEGY_TYPES = ("deterministic", "inferential", "agentic")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strategies_dir(history_dir: Path) -> Path:
    root = history_dir / "strategies"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _strategy_path(root: Path, strategy_id: str) -> Path:
    return root / f"strategy_{strategy_id}.json"


def _state_path(root: Path) -> Path:
    return root / "_state.json"


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def strategy_summary(data: dict) -> dict:
    return {
        "id": data["id"], "name": data["name"], "type": data["type"],
        "description": data["description"],
        "created_at_utc": data["created_at_utc"], "updated_at_utc": data["updated_at_utc"],
    }


def _ensure_description(root: Path, data: dict) -> dict:
    """Migra i JSON creati prima del campo description."""
    if "description" in data:
        return data
    data["description"] = ""
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_strategy_path(root, data["id"]), data)
    return data


def load_strategy(root: Path, strategy_id: str) -> dict:
    path = _strategy_path(root, strategy_id)
    if not path.is_file():
        raise Exception(f"strategy not found: {strategy_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return _ensure_description(root, data)


def list_strategies(root: Path, strategy_type: str | None = None) -> list[dict]:
    out: list[dict] = []
    for path in sorted(root.glob("strategy_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        data = _ensure_description(root, data)
        if strategy_type is not None and data["type"] != strategy_type:
            continue
        out.append(strategy_summary(data))
    return out


def create_strategy(root: Path, name: str, strategy_type: str, description: str) -> dict:
    name = name.strip()
    if not name:
        raise Exception("strategy name required")
    if strategy_type not in STRATEGY_TYPES:
        raise Exception(f"invalid strategy type: {strategy_type}")
    strategy_id = uuid.uuid4().hex[:12]
    now = _utc_now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION, "id": strategy_id, "name": name,
        "type": strategy_type, "description": description.strip(), "params": {},
        "created_at_utc": now, "updated_at_utc": now,
    }
    _atomic_write(_strategy_path(root, strategy_id), payload)
    return payload


def update_strategy(root: Path, strategy_id: str, name: str, description: str) -> dict:
    name = name.strip()
    if not name:
        raise Exception("strategy name required")
    data = load_strategy(root, strategy_id)
    data["name"] = name
    data["description"] = description.strip()
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_strategy_path(root, strategy_id), data)
    return data


def delete_strategy(root: Path, strategy_id: str) -> None:
    path = _strategy_path(root, strategy_id)
    if not path.is_file():
        raise Exception(f"strategy not found: {strategy_id}")
    path.unlink()


def load_active_ids(root: Path) -> list[str]:
    path = _state_path(root)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = data["active_ids"]
    return [sid for sid in ids if _strategy_path(root, sid).is_file()]


def save_active_ids(root: Path, active_ids: list[str]) -> None:
    _atomic_write(_state_path(root), {"active_ids": list(active_ids), "saved_at_utc": _utc_now_iso()})
