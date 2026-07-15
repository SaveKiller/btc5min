"""History JSON immutabile per ogni replay completato."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_run(history_dir: Path, market_start_ts: int, run: dict) -> Path:
    run_id = run.get("run_id") or uuid.uuid4().hex[:12]
    name = f"btc5m_{market_start_ts}_{run_id}.json"
    path = history_dir / name
    tmp = path.with_suffix(".tmp")
    payload = {**run, "run_id": run_id, "saved_at_utc": _utc_now_iso()}
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)
    return path


def list_runs(history_dir: Path) -> list[dict]:
    runs: list[dict] = []
    for path in sorted(history_dir.glob("btc5m_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        runs.append({
            "run_id": data["run_id"], "market_start_ts": data["market_start_ts"],
            "saved_at_utc": data.get("saved_at_utc"), "path": str(path.name),
            "outcome": data.get("outcome"), "total_pnl_usd": data.get("total_pnl_usd", 0),
            "orders": data.get("orders", []),
        })
    return runs


def visible_history(runs: list[dict], active_market_start_ts: int | None, round_settled: bool) -> list[dict]:
    """Filtra run precedenti del round attivo fino al settlement."""
    out: list[dict] = []
    for run in runs:
        if active_market_start_ts is not None and run["market_start_ts"] == active_market_start_ts and not round_settled:
            continue
        out.append(run)
    return out


def history_rows(runs: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for run in runs:
        rows.extend(order_rows_for_run(run["market_start_ts"], run.get("orders", []), run["run_id"]))
    return rows


def order_rows_for_run(market_start_ts: int, orders: list[dict], run_id: str = "") -> list[dict]:
    dt = datetime.fromtimestamp(market_start_ts, tz=timezone.utc)
    rows: list[dict] = []
    for o in orders:
        if o.get("close_type") not in ("manual", "settlement"):
            continue
        rows.append({
            "date_utc": dt.strftime("%d/%m/%Y"), "time_utc": dt.strftime("%H:%M:%S"),
            "direction": o["side"], "size_usd": o["size_usd"], "entry_sec": o["entry_sec"],
            "exit_sec": o.get("exit_sec"), "entry_btc": o.get("entry_btc"), "exit_btc": o.get("exit_btc"),
            "result": o.get("result"), "pnl_usd": o.get("pnl_usd"),
            "market_start_ts": market_start_ts, "run_id": run_id,
        })
    return rows
