"""Repository account JSON: un file per account con ledger ordini."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def accounts_dir(history_dir: Path) -> Path:
    root = history_dir / "accounts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _account_path(accounts_root: Path, account_id: str) -> Path:
    return accounts_root / f"account_{account_id}.json"


def _state_path(accounts_root: Path) -> Path:
    return accounts_root / "_state.json"


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def load_active_account_id(accounts_root: Path) -> str | None:
    path = _state_path(accounts_root)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    aid = data.get("active_account_id")
    if aid is None:
        return None
    if not _account_path(accounts_root, aid).is_file():
        return None
    return aid


def save_active_account_id(accounts_root: Path, account_id: str | None) -> None:
    _atomic_write(_state_path(accounts_root), {"active_account_id": account_id, "saved_at_utc": _utc_now_iso()})


def load_account(accounts_root: Path, account_id: str) -> dict:
    path = _account_path(accounts_root, account_id)
    if not path.is_file():
        raise Exception(f"account not found: {account_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_accounts(accounts_root: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(accounts_root.glob("account_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(account_summary(data))
    return out


def account_summary(data: dict) -> dict:
    stats = compute_stats(data)
    return {
        "id": data["id"], "name": data["name"], "note": data.get("note", ""),
        "initial_balance_usd": data["initial_balance_usd"], "created_at_utc": data["created_at_utc"],
        "updated_at_utc": data.get("updated_at_utc"), **stats,
    }


def compute_stats(data: dict) -> dict:
    orders = [o for o in data.get("orders", []) if o.get("close_type") in ("manual", "settlement")]
    realized = sum(float(o.get("pnl_usd", 0)) for o in orders)
    initial = float(data["initial_balance_usd"])
    wins = sum(1 for o in orders if float(o.get("pnl_usd", 0)) > 0)
    losses = sum(1 for o in orders if float(o.get("pnl_usd", 0)) < 0)
    staked = sum(float(o["size_usd"]) for o in orders)
    n = len(orders)
    decided = wins + losses
    return {
        "current_balance_usd": initial + realized, "realized_pnl_usd": realized,
        "gain_pct": (realized / initial * 100.0) if initial else 0.0,
        "wins": wins, "losses": losses,
        "win_rate_pct": (wins / decided * 100.0) if decided else 0.0,
        "order_count": n, "total_staked_usd": staked,
        "avg_stake_usd": (staked / n) if n else 0.0,
    }


def create_account(accounts_root: Path, name: str, initial_balance_usd: float, note: str) -> dict:
    name = name.strip()
    if not name:
        raise Exception("account name required")
    account_id = uuid.uuid4().hex[:12]
    now = _utc_now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION, "id": account_id, "name": name, "note": note.strip(),
        "initial_balance_usd": float(initial_balance_usd), "created_at_utc": now,
        "updated_at_utc": now, "orders": [],
    }
    _atomic_write(_account_path(accounts_root, account_id), payload)
    return payload


def rename_account(accounts_root: Path, account_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        raise Exception("account name required")
    data = load_account(accounts_root, account_id)
    data["name"] = name
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_account_path(accounts_root, account_id), data)
    return data


def update_account(accounts_root: Path, account_id: str, name: str, initial_balance_usd: float, note: str) -> dict:
    name = name.strip()
    if not name:
        raise Exception("account name required")
    data = load_account(accounts_root, account_id)
    data["name"] = name
    data["initial_balance_usd"] = float(initial_balance_usd)
    data["note"] = note.strip()
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_account_path(accounts_root, account_id), data)
    return data


def append_settled_orders(accounts_root: Path, account_id: str, market_start_ts: int, session_id: str, session_started_at_utc: str, outcome: str, orders: list[dict]) -> dict:
    data = load_account(accounts_root, account_id)
    for o in orders:
        if o.get("close_type") not in ("manual", "settlement"):
            continue
        entry = {
            **o, "market_start_ts": market_start_ts, "session_id": session_id,
            "session_started_at_utc": session_started_at_utc, "outcome": outcome, "saved_at_utc": _utc_now_iso(),
        }
        data["orders"].append(entry)
    data["updated_at_utc"] = _utc_now_iso()
    _atomic_write(_account_path(accounts_root, account_id), data)
    return data


def visible_orders(orders: list[dict], active_market_start_ts: int | None, round_settled: bool) -> list[dict]:
    out: list[dict] = []
    for o in orders:
        if active_market_start_ts is not None and o.get("market_start_ts") == active_market_start_ts and not round_settled:
            continue
        out.append(o)
    return out


def _session_display(o: dict) -> tuple[str, str]:
    raw = o.get("session_started_at_utc") or o.get("saved_at_utc")
    if not raw:
        return "—", "—"
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.strftime("%d/%m"), dt.strftime("%H:%M")


def _session_sort_ts(o: dict) -> int:
    raw = o.get("session_started_at_utc") or o.get("saved_at_utc")
    if not raw:
        return 0
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return int(dt.timestamp())


def order_rows_from_ledger(orders: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for o in orders:
        if o.get("close_type") not in ("manual", "settlement"):
            continue
        mts = int(o["market_start_ts"])
        outcome = o.get("outcome")
        dt = datetime.fromtimestamp(mts, tz=timezone.utc)
        session_date, session_time = _session_display(o)
        rows.append({
            "date_utc": dt.strftime("%d/%m"), "time_utc": dt.strftime("%H:%M"),
            "session_date_utc": session_date, "session_time_utc": session_time,
            "session_started_at_utc": o.get("session_started_at_utc") or o.get("saved_at_utc") or "",
            "session_sort_ts": _session_sort_ts(o),
            "direction": o["side"], "outcome": outcome,
            "size_usd": o["size_usd"], "entry_sec": o["entry_sec"],
            "exit_sec": o.get("exit_sec"),
            "entry_quote_c": _entry_quote_c(o), "exit_quote_c": _exit_quote_c(o),
            "pnl_usd": o.get("pnl_usd"),
            "payout_usd": _settlement_payout_usd(o, outcome),
            "final_pnl_usd": _settlement_pnl_usd(o, outcome),
            "market_start_ts": mts, "session_id": o.get("session_id") or o.get("run_id", ""),
        })
    rows.sort(key=lambda r: (r["session_sort_ts"], r["market_start_ts"], r.get("entry_sec", 0)), reverse=True)
    return rows


def order_rows_for_run(market_start_ts: int, orders: list[dict], session_id: str = "", session_started_at_utc: str = "", outcome: str | None = None) -> list[dict]:
    enriched = [{
        **o, "market_start_ts": market_start_ts, "session_id": session_id,
        "session_started_at_utc": session_started_at_utc, "outcome": outcome,
    } for o in orders]
    return order_rows_from_ledger(enriched)


def _entry_quote_c(o: dict) -> int | None:
    if o.get("best_ask_c") is not None:
        return int(o["best_ask_c"])
    if o.get("avg_entry_price") is not None:
        return int(round(float(o["avg_entry_price"]) * 100))
    if o.get("best_ask") is not None:
        return int(round(float(o["best_ask"]) * 100))
    return None


def _exit_quote_c(o: dict) -> int | None:
    if o.get("close_type") == "settlement":
        if o.get("result") == "won":
            return 100
        if o.get("result") == "lost":
            return 0
    if o.get("exit_price") is not None:
        return int(round(float(o["exit_price"]) * 100))
    return None


def _settlement_payout_usd(o: dict, outcome: str | None) -> float | None:
    if outcome not in ("Up", "Down"):
        return None
    if outcome == o["side"]:
        return float(o["payout_if_win_usd"])
    return 0.0


def _settlement_pnl_usd(o: dict, outcome: str | None) -> float | None:
    if outcome not in ("Up", "Down"):
        return None
    if outcome == o["side"]:
        return float(o["profit_if_win_usd"])
    return -float(o["size_usd"])
