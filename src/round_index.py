"""Indice persistente round .bin in data/ (picker dashV2, sync, batch)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.binary_format import txt_path_for_bin

INDEX_VERSION = 1
INDEX_NAME = "rounds_index.json"


def index_path(data_dir: Path) -> Path:
    return Path(data_dir) / INDEX_NAME


def _entry_from_bin(data_dir: Path, bin_path: Path) -> dict:
    txt_path = txt_path_for_bin(str(bin_path))
    valid = txt_path.is_file()
    return {
        "bin": bin_path.relative_to(data_dir).as_posix(),
        "valid": valid,
        "reason": None if valid else "missing txt pair",
    }


def _ts_from_bin(bin_path: Path) -> int:
    parts = bin_path.stem.split("_")
    if len(parts) < 3:
        raise Exception(f"invalid bin name: {bin_path.name}")
    return int(parts[1])


def scan_bins(data_dir: Path) -> dict[int, dict]:
    """Scan completo data_dir; in caso di duplicati per ts tiene il .bin più recente."""
    data_dir = Path(data_dir)
    entries: dict[int, dict] = {}
    mtimes: dict[int, float] = {}
    for bin_path in data_dir.glob("**/bin/btc5m_*.bin"):
        ts = _ts_from_bin(bin_path)
        mtime = bin_path.stat().st_mtime
        if ts in entries and mtime <= mtimes[ts]:
            continue
        entries[ts] = _entry_from_bin(data_dir, bin_path)
        mtimes[ts] = mtime
    return entries


def load_index_file(path: Path) -> dict[int, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw["v"] != INDEX_VERSION:
        raise Exception(f"unsupported rounds index version: {raw['v']}")
    return {int(ts): dict(entry) for ts, entry in raw["entries"].items()}


def save_index(data_dir: Path, entries: dict[int, dict]) -> Path:
    data_dir = Path(data_dir)
    path = index_path(data_dir)
    payload = {
        "v": INDEX_VERSION,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entries": {str(ts): entry for ts, entry in sorted(entries.items())},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def reconcile_index(data_dir: Path, entries: dict[int, dict]) -> bool:
    """Allinea entries a disco: nuovi bin, path cambiati, rimozioni."""
    data_dir = Path(data_dir)
    changed = False
    on_disk: dict[int, tuple[Path, float]] = {}
    for bin_path in data_dir.glob("**/bin/btc5m_*.bin"):
        ts = _ts_from_bin(bin_path)
        mtime = bin_path.stat().st_mtime
        if ts not in on_disk or mtime > on_disk[ts][1]:
            on_disk[ts] = (bin_path, mtime)
    for ts, (bin_path, _) in on_disk.items():
        entry = _entry_from_bin(data_dir, bin_path)
        if entries.get(ts) != entry:
            entries[ts] = entry
            changed = True
    for ts in [t for t in entries if t not in on_disk]:
        del entries[ts]
        changed = True
    return changed


def load_or_build_index(data_dir: Path) -> dict[int, dict]:
    """Carica JSON; se assente fa scan completo; altrimenti reconcile incrementale."""
    data_dir = Path(data_dir)
    path = index_path(data_dir)
    if not path.is_file():
        entries = scan_bins(data_dir)
        save_index(data_dir, entries)
        return entries
    entries = load_index_file(path)
    if reconcile_index(data_dir, entries):
        save_index(data_dir, entries)
    return entries


def upsert_bins(data_dir: Path, bin_paths: list[Path]) -> None:
    """Aggiorna l'indice dopo sync o scrittura collector."""
    data_dir = Path(data_dir)
    path = index_path(data_dir)
    entries = load_index_file(path) if path.is_file() else {}
    changed = False
    for bin_path in bin_paths:
        bin_path = Path(bin_path)
        if not bin_path.is_file():
            raise Exception(f"bin missing for index upsert: {bin_path}")
        ts = _ts_from_bin(bin_path)
        entry = _entry_from_bin(data_dir, bin_path)
        if entries.get(ts) != entry:
            entries[ts] = entry
            changed = True
    if reconcile_index(data_dir, entries):
        changed = True
    if changed or not path.is_file():
        save_index(data_dir, entries)


def remove_bins(data_dir: Path, bin_paths: list[Path]) -> None:
    """Rimuove voci dall'indice (es. tail trim sync)."""
    data_dir = Path(data_dir)
    path = index_path(data_dir)
    if not path.is_file():
        return
    entries = load_index_file(path)
    changed = False
    for bin_path in bin_paths:
        ts = _ts_from_bin(Path(bin_path))
        if ts in entries:
            del entries[ts]
            changed = True
    if changed:
        save_index(data_dir, entries)
