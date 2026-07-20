"""Repository strategy JSON: un file per strategy + stato active_ids + moduli .py versionati."""

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


def module_path(root: Path, strategy_id: str, version: int) -> Path:
    return root / f"strategy_{strategy_id}_v{version}.py"


def _legacy_module_path(root: Path, strategy_id: str) -> Path:
    return root / f"strategy_{strategy_id}.py"


def _state_path(root: Path) -> Path:
    return root / "_state.json"


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def write_module(root: Path, strategy_id: str, source: str, version: int) -> str:
    """Scrive strategy_{id}_v{N}.py e restituisce il nome file."""
    name = f"strategy_{strategy_id}_v{version}.py"
    module_path(root, strategy_id, version).write_text(source, encoding="utf-8")
    return name


def _version_entry(version: int, rules: str, coded_rules: str, module_file: str | None, created_at: str) -> dict:
    return {
        "version": version, "rules": rules, "coded_rules": coded_rules,
        "module_file": module_file, "created_at_utc": created_at,
    }


def version_snapshot(data: dict, version: int) -> dict:
    """Snapshot immutabile per N; KeyError se assente."""
    for entry in data["versions"]:
        if entry["version"] == version:
            return entry
    raise Exception(f"strategy version not found: {data['id']} v{version}")


def strategy_summary(data: dict) -> dict:
    return {
        "id": data["id"], "name": data["name"], "type": data["type"],
        "description": data["description"], "rules": data["rules"],
        "coded_rules": data["coded_rules"],
        "module_file": data["module_file"],
        "version": data["version"], "versions": data["versions"],
        "created_at_utc": data["created_at_utc"], "updated_at_utc": data["updated_at_utc"],
    }


def _migrate_if_needed(root: Path, data: dict) -> dict:
    """Una tantum: strategy_{id}.py legacy → _v1.py + campi version/versions."""
    if "version" in data and "versions" in data:
        return data
    sid = data["id"]
    now = data.get("updated_at_utc") or _utc_now_iso()
    legacy = _legacy_module_path(root, sid)
    module_file = data.get("module_file")
    if legacy.is_file():
        source = legacy.read_text(encoding="utf-8")
        module_file = write_module(root, sid, source, 1)
        legacy.unlink()
    elif module_file and not str(module_file).endswith("_v1.py"):
        old = root / module_file
        if old.is_file() and old.name == f"strategy_{sid}.py":
            source = old.read_text(encoding="utf-8")
            module_file = write_module(root, sid, source, 1)
            old.unlink()
    data["version"] = 1
    data["module_file"] = module_file
    data["coded_rules"] = data.get("coded_rules") or ""
    data["rules"] = data.get("rules") or ""
    data["versions"] = [
        _version_entry(1, data["rules"], data["coded_rules"], module_file, now),
    ]
    _atomic_write(_strategy_path(root, sid), data)
    return data


def load_strategy(root: Path, strategy_id: str) -> dict:
    path = _strategy_path(root, strategy_id)
    if not path.is_file():
        raise Exception(f"strategy not found: {strategy_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return _migrate_if_needed(root, data)


def list_strategies(root: Path, strategy_type: str | None = None) -> list[dict]:
    out: list[dict] = []
    for path in sorted(root.glob("strategy_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        data = _migrate_if_needed(root, data)
        if strategy_type is not None and data["type"] != strategy_type:
            continue
        out.append(strategy_summary(data))
    return out


def create_strategy(
    root: Path, name: str, strategy_type: str, description: str,
    rules: str, coded_rules: str, module_file: str | None,
    strategy_id: str | None = None,
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
    versions = [_version_entry(1, rules, coded_rules, module_file, now)]
    payload = {
        "schema_version": SCHEMA_VERSION, "id": sid, "name": name,
        "type": strategy_type, "description": description.strip(),
        "rules": rules, "coded_rules": coded_rules, "module_file": module_file,
        "version": 1, "versions": versions,
        "params": {}, "created_at_utc": now, "updated_at_utc": now,
    }
    _atomic_write(_strategy_path(root, sid), payload)
    return payload


def update_strategy(
    root: Path, strategy_id: str, name: str, description: str,
    module_rebuilt: bool,
    rules: str | None = None, module_file: str | None = None,
    coded_rules: str | None = None,
) -> dict:
    """Aggiorna tip (name/description in-place; se module_rebuilt: tip+=1 e append snapshot)."""
    name = name.strip()
    if not name:
        raise Exception("strategy name required")
    data = load_strategy(root, strategy_id)
    data["name"] = name
    data["description"] = description.strip()
    if module_rebuilt:
        if rules is None or module_file is None:
            raise Exception("module_rebuilt requires rules and module_file")
        if data["type"] == "deterministic" and not rules.strip():
            raise Exception("deterministic strategy requires rules")
        new_ver = data["version"] + 1
        now = _utc_now_iso()
        cr = coded_rules if coded_rules is not None else ""
        data["version"] = new_ver
        data["rules"] = rules
        data["coded_rules"] = cr
        data["module_file"] = module_file
        data["versions"].append(_version_entry(new_ver, rules, cr, module_file, now))
    elif rules is not None:
        # Solo metadata tip senza nuova N (es. non-det); deterministic tip rules restano dallo snapshot.
        data["rules"] = rules
        if data["type"] == "deterministic" and not rules.strip():
            raise Exception("deterministic strategy requires rules")
        if coded_rules is not None:
            data["coded_rules"] = coded_rules
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_strategy_path(root, strategy_id), data)
    return data


def delete_strategy(root: Path, strategy_id: str) -> None:
    path = _strategy_path(root, strategy_id)
    if not path.is_file():
        raise Exception(f"strategy not found: {strategy_id}")
    path.unlink()
    for py in root.glob(f"strategy_{strategy_id}_v*.py"):
        py.unlink()
    legacy = _legacy_module_path(root, strategy_id)
    if legacy.is_file():
        legacy.unlink()


def unique_clone_name(root: Path, base_name: str) -> str:
    names = {s["name"] for s in list_strategies(root)}
    candidate = f"{base_name} (copy)"
    if candidate not in names:
        return candidate
    n = 2
    while f"{base_name} (copy {n})" in names:
        n += 1
    return f"{base_name} (copy {n})"


def clone_strategy(root: Path, strategy_id: str) -> dict:
    """Fork: copia tip → nuova strategy v1 (source intatta)."""
    src = load_strategy(root, strategy_id)
    new_id = uuid.uuid4().hex[:12]
    new_name = unique_clone_name(root, src["name"])
    module_file = None
    tip = src["version"]
    src_py = module_path(root, strategy_id, tip)
    if src_py.is_file():
        module_file = write_module(root, new_id, src_py.read_text(encoding="utf-8"), 1)
    elif src["type"] == "deterministic":
        raise Exception(f"missing module for deterministic strategy: {strategy_id} v{tip}")
    return create_strategy(
        root, new_name, src["type"], src["description"],
        rules=src["rules"], coded_rules=src["coded_rules"],
        module_file=module_file, strategy_id=new_id,
    )


def load_active_ids(root: Path) -> list[str]:
    path = _state_path(root)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = data["active_ids"]
    return [sid for sid in ids if _strategy_path(root, sid).is_file()]


def save_active_ids(root: Path, active_ids: list[str]) -> None:
    _atomic_write(_state_path(root), {"active_ids": list(active_ids), "saved_at_utc": _utc_now_iso()})
