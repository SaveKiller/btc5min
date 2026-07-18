"""Repository strategy JSON: un file per strategy + stato active_ids + modulo .py."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
STRATEGY_TYPES = ("deterministic", "inferential", "agentic")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strategies_dir(history_dir: Path) -> Path:
    root = history_dir / "strategies"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _strategy_path(root: Path, strategy_id: str) -> Path:
    return root / f"strategy_{strategy_id}.json"


def module_path(root: Path, strategy_id: str) -> Path:
    return root / f"strategy_{strategy_id}.py"


def _state_path(root: Path) -> Path:
    return root / "_state.json"


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def write_module(root: Path, strategy_id: str, source: str) -> str:
    """Scrive strategy_{id}.py e restituisce il nome file."""
    name = f"strategy_{strategy_id}.py"
    module_path(root, strategy_id).write_text(source, encoding="utf-8")
    return name


def strategy_summary(data: dict) -> dict:
    return {
        "id": data["id"], "name": data["name"], "type": data["type"],
        "description": data["description"], "rules": data.get("rules", ""),
        "module_file": data.get("module_file"),
        "created_at_utc": data["created_at_utc"], "updated_at_utc": data["updated_at_utc"],
    }


def load_strategy(root: Path, strategy_id: str) -> dict:
    path = _strategy_path(root, strategy_id)
    if not path.is_file():
        raise Exception(f"strategy not found: {strategy_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_strategies(root: Path, strategy_type: str | None = None) -> list[dict]:
    out: list[dict] = []
    for path in sorted(root.glob("strategy_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        if strategy_type is not None and data["type"] != strategy_type:
            continue
        out.append(strategy_summary(data))
    return out


def create_strategy(
    root: Path, name: str, strategy_type: str, description: str,
    rules: str = "", module_file: str | None = None, strategy_id: str | None = None,
) -> dict:
    name = name.strip()
    if not name:
        raise Exception("strategy name required")
    if strategy_type not in STRATEGY_TYPES:
        raise Exception(f"invalid strategy type: {strategy_type}")
    if strategy_type == "deterministic" and not rules.strip():
        raise Exception("deterministic strategy requires rules")
    if strategy_type == "deterministic" and not module_file:
        raise Exception("deterministic strategy requires module_file")
    sid = strategy_id or uuid.uuid4().hex[:12]
    now = _utc_now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION, "id": sid, "name": name,
        "type": strategy_type, "description": description.strip(),
        "rules": rules, "module_file": module_file, "params": {},
        "created_at_utc": now, "updated_at_utc": now,
    }
    _atomic_write(_strategy_path(root, sid), payload)
    return payload


def update_strategy(
    root: Path, strategy_id: str, name: str, description: str,
    rules: str | None = None, module_file: str | None = None,
) -> dict:
    name = name.strip()
    if not name:
        raise Exception("strategy name required")
    data = load_strategy(root, strategy_id)
    data["name"] = name
    data["description"] = description.strip()
    if rules is not None:
        data["rules"] = rules
        if data["type"] == "deterministic" and not rules.strip():
            raise Exception("deterministic strategy requires rules")
    if module_file is not None:
        data["module_file"] = module_file
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_strategy_path(root, strategy_id), data)
    return data


def delete_strategy(root: Path, strategy_id: str) -> None:
    path = _strategy_path(root, strategy_id)
    if not path.is_file():
        raise Exception(f"strategy not found: {strategy_id}")
    path.unlink()
    py = module_path(root, strategy_id)
    if py.is_file():
        py.unlink()


def load_active_ids(root: Path) -> list[str]:
    path = _state_path(root)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = data["active_ids"]
    return [sid for sid in ids if _strategy_path(root, sid).is_file()]


def save_active_ids(root: Path, active_ids: list[str]) -> None:
    _atomic_write(_state_path(root), {"active_ids": list(active_ids), "saved_at_utc": _utc_now_iso()})
