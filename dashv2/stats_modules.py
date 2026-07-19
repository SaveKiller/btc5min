"""Repository analyze JSON: un file per analyze + modulo .py sotto history/stats."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stats_dir(history_dir: Path) -> Path:
    root = history_dir / "stats"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _analyze_path(root: Path, analyze_id: str) -> Path:
    return root / f"analyze_{analyze_id}.json"


def module_path(history_dir: Path, analyze_id: str) -> Path:
    return stats_dir(history_dir) / f"analyze_{analyze_id}.py"


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def analyze_summary(data: dict) -> dict:
    return {
        "id": data["id"], "name": data["name"], "rules": data["rules"],
        "module_file": data.get("module_file"),
        "created_at_utc": data["created_at_utc"], "updated_at_utc": data["updated_at_utc"],
    }


def create_analyze(history_dir: Path, name: str, rules: str) -> dict:
    name = name.strip()
    if not name:
        raise Exception("analyze name required")
    if not rules.strip():
        raise Exception("analyze rules required")
    root = stats_dir(history_dir)
    aid = uuid.uuid4().hex[:12]
    now = _utc_now_iso()
    module_file = f"analyze_{aid}.py"
    payload = {
        "schema_version": SCHEMA_VERSION, "id": aid, "name": name,
        "rules": rules, "module_file": module_file,
        "created_at_utc": now, "updated_at_utc": now,
    }
    _atomic_write(_analyze_path(root, aid), payload)
    return payload


def write_analyze_module(history_dir: Path, analyze_id: str, source: str) -> Path:
    """Scrive analyze_{id}.py e aggiorna module_file nel JSON."""
    root = stats_dir(history_dir)
    path = _analyze_path(root, analyze_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    py = module_path(history_dir, analyze_id)
    py.write_text(source, encoding="utf-8")
    data["module_file"] = py.name
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(path, data)
    return py


def load_analyze(history_dir: Path, analyze_id: str) -> dict:
    path = _analyze_path(stats_dir(history_dir), analyze_id)
    if not path.is_file():
        raise Exception(f"analyze not found: {analyze_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def set_analyze_rules(history_dir: Path, analyze_id: str, rules: str) -> dict:
    """Aggiorna rules + updated_at sul JSON analyze."""
    root = stats_dir(history_dir)
    path = _analyze_path(root, analyze_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rules"] = rules
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(path, data)
    return data


def list_analyzes(history_dir: Path) -> list[dict]:
    root = stats_dir(history_dir)
    out: list[dict] = []
    for path in sorted(root.glob("analyze_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(analyze_summary(data))
    return out


def delete_analyze(history_dir: Path, analyze_id: str) -> None:
    root = stats_dir(history_dir)
    path = _analyze_path(root, analyze_id)
    if not path.is_file():
        raise Exception(f"analyze not found: {analyze_id}")
    path.unlink()
    py = module_path(history_dir, analyze_id)
    if py.is_file():
        py.unlink()
