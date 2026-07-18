"""Log jsonl di esecuzione ordini per session_id (fatti + reason)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def executions_dir(history_dir: Path) -> Path:
    root = history_dir / "executions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def delete_execution_session(history_dir: Path, session_id: str) -> None:
    path = executions_dir(history_dir) / f"{session_id}.jsonl"
    if path.is_file():
        path.unlink()


def append_execution(history_dir: Path, row: dict) -> None:
    session_id = row["session_id"]
    path = executions_dir(history_dir) / f"{session_id}.jsonl"
    payload = {"ts": _utc_now_iso(), **row}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_execution_session(history_dir: Path, session_id: str, limit: int = 200) -> list[dict]:
    path = executions_dir(history_dir) / f"{session_id}.jsonl"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines[-limit:]:
        if line.strip():
            out.append(json.loads(line))
    return out


def execution_session_meta(history_dir: Path, session_id: str) -> dict:
    """Meta da file jsonl (o stub se file assente)."""
    path = executions_dir(history_dir) / f"{session_id}.jsonl"
    if not path.is_file():
        return {
            "session_id": session_id,
            "market_start_ts": None,
            "last_sec": None,
            "n_events": 0,
            "updated_at_utc": None,
            "strategy_ids": [],
        }
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = [json.loads(ln) for ln in lines]
    strategy_ids: list[str] = []
    begin_ids: list[str] | None = None
    mts = None
    last_sec = None
    n_events = 0
    for r in rows:
        cmd = r.get("cmd")
        if cmd == "session.begin":
            begin_ids = list(r.get("active_strategy_ids") or [])
            if mts is None:
                mts = r.get("market_start_ts")
            continue
        n_events += 1
        sid = r.get("strategy_id")
        if sid and sid not in strategy_ids:
            strategy_ids.append(sid)
        if mts is None:
            mts = r.get("market_start_ts")
        if r.get("sec") is not None:
            last_sec = r.get("sec")
    if begin_ids is not None:
        strategy_ids = begin_ids
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return {
        "session_id": session_id,
        "market_start_ts": mts,
        "last_sec": last_sec,
        "n_events": n_events,
        "updated_at_utc": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy_ids": strategy_ids,
    }


def list_execution_sessions(history_dir: Path, live_session_id: str | None = None) -> list[dict]:
    """Elenco sessioni da history/executions, più la live se non ha ancora jsonl."""
    root = executions_dir(history_dir)
    items: list[dict] = []
    seen: set[str] = set()
    for path in root.glob("*.jsonl"):
        sid = path.stem
        seen.add(sid)
        items.append(execution_session_meta(history_dir, sid))
    if live_session_id and live_session_id not in seen:
        items.append(execution_session_meta(history_dir, live_session_id))
    items.sort(key=lambda x: x.get("updated_at_utc") or "", reverse=True)
    if live_session_id:
        for i, it in enumerate(items):
            if it["session_id"] == live_session_id:
                items.insert(0, items.pop(i))
                break
    return items
