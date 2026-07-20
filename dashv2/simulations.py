"""Repository sessioni backtest: un SQLite per run (JSON v1 legacy in sola lettura)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def simulations_dir(history_dir: Path) -> Path:
    root = history_dir / "simulations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sqlite_path(root: Path, simulation_id: str) -> Path:
    return root / f"simulation_{simulation_id}.sqlite"


def _json_path(root: Path, simulation_id: str) -> Path:
    return root / f"simulation_{simulation_id}.json"


def simulation_label(data: dict) -> str:
    """Etichetta dropdown: strategy vN · YYYY-MM-DD HH:MM · day_from→to."""
    dt = data["created_at_utc"][:16].replace("T", " ")
    day_from = data["day_from"]
    day_to = data["day_to"]
    if day_from[:8] == day_to[:8]:
        range_s = f"{day_from}→{day_to[8:]}"
    elif day_from[:5] == day_to[:5]:
        range_s = f"{day_from}→{day_to[5:]}"
    else:
        range_s = f"{day_from}→{day_to}"
    return f"{data['strategy_name']} v{data['strategy_version']} · {dt} · {range_s}"


def simulation_summary(data: dict) -> dict:
    return {
        "id": data["id"], "strategy_id": data["strategy_id"],
        "strategy_name": data["strategy_name"],
        "strategy_version": data["strategy_version"],
        "created_at_utc": data["created_at_utc"],
        "day_from": data["day_from"], "day_to": data["day_to"],
        "has_orders": bool(data.get("has_orders")),
        "label": simulation_label(data),
    }


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE meta (
            id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            strategy_id TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            strategy_version INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            day_from TEXT NOT NULL,
            day_to TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            table_json TEXT NOT NULL
        );
        CREATE TABLE rounds (
            market_start_ts INTEGER PRIMARY KEY,
            hour_utc INTEGER NOT NULL,
            ok INTEGER NOT NULL,
            error TEXT,
            pnl_usd REAL NOT NULL,
            n_orders INTEGER NOT NULL,
            n_wins INTEGER NOT NULL,
            n_losses INTEGER NOT NULL,
            traded INTEGER NOT NULL,
            action_errors_json TEXT NOT NULL
        );
        CREATE TABLE orders (
            order_id TEXT NOT NULL,
            market_start_ts INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            side TEXT,
            entry_sec INTEGER,
            exit_sec INTEGER,
            size_usd REAL,
            shares REAL,
            avg_entry_price REAL,
            best_ask REAL,
            best_ask_c INTEGER,
            entry_fee_usd REAL,
            exit_fee_usd REAL,
            entry_btc REAL,
            exit_btc REAL,
            exit_price REAL,
            proceeds_usd REAL,
            pnl_usd REAL,
            result TEXT,
            close_type TEXT,
            reason TEXT,
            close_reason TEXT,
            payout_if_win_usd REAL,
            profit_if_win_usd REAL,
            account_id TEXT,
            source TEXT,
            strategy_id TEXT,
            PRIMARY KEY (market_start_ts, seq)
        );
        CREATE INDEX idx_orders_ts ON orders(market_start_ts, seq);
    """)


def _meta_dict(row: sqlite3.Row) -> dict:
    return {
        "schema_version": row["schema_version"],
        "id": row["id"],
        "strategy_id": row["strategy_id"],
        "strategy_name": row["strategy_name"],
        "strategy_version": row["strategy_version"],
        "created_at_utc": row["created_at_utc"],
        "day_from": row["day_from"],
        "day_to": row["day_to"],
        "summary": json.loads(row["summary_json"]),
        "table": json.loads(row["table_json"]),
        "has_orders": True,
    }


def _round_from_row(row: sqlite3.Row) -> dict:
    return {
        "market_start_ts": row["market_start_ts"],
        "hour_utc": row["hour_utc"],
        "ok": bool(row["ok"]),
        "error": row["error"],
        "pnl_usd": row["pnl_usd"],
        "n_orders": row["n_orders"],
        "n_wins": row["n_wins"],
        "n_losses": row["n_losses"],
        "traded": bool(row["traded"]),
        "action_errors": json.loads(row["action_errors_json"]),
    }


def _order_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["order_id"],
        "side": row["side"],
        "entry_sec": row["entry_sec"],
        "exit_sec": row["exit_sec"],
        "size_usd": row["size_usd"],
        "shares": row["shares"],
        "avg_entry_price": row["avg_entry_price"],
        "best_ask": row["best_ask"],
        "best_ask_c": row["best_ask_c"],
        "entry_fee_usd": row["entry_fee_usd"],
        "exit_fee_usd": row["exit_fee_usd"],
        "entry_btc": row["entry_btc"],
        "exit_btc": row["exit_btc"],
        "exit_price": row["exit_price"],
        "proceeds_usd": row["proceeds_usd"],
        "pnl_usd": row["pnl_usd"],
        "result": row["result"],
        "close_type": row["close_type"],
        "reason": row["reason"],
        "close_reason": row["close_reason"],
        "payout_if_win_usd": row["payout_if_win_usd"],
        "profit_if_win_usd": row["profit_if_win_usd"],
        "account_id": row["account_id"],
        "source": row["source"],
        "strategy_id": row["strategy_id"],
    }


def _insert_round(conn: sqlite3.Connection, r: dict) -> None:
    orders = r.get("orders") or []
    conn.execute(
        """INSERT INTO rounds (
            market_start_ts, hour_utc, ok, error, pnl_usd, n_orders, n_wins, n_losses,
            traded, action_errors_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            r["market_start_ts"], r["hour_utc"], int(bool(r["ok"])), r.get("error"),
            float(r.get("pnl_usd") or 0.0), int(r.get("n_orders") or 0),
            int(r.get("n_wins") or 0), int(r.get("n_losses") or 0),
            int(bool(r.get("traded"))), json.dumps(r.get("action_errors") or []),
        ),
    )
    for seq, o in enumerate(orders):
        conn.execute(
            """INSERT INTO orders (
                order_id, market_start_ts, seq, side, entry_sec, exit_sec, size_usd, shares,
                avg_entry_price, best_ask, best_ask_c, entry_fee_usd, exit_fee_usd,
                entry_btc, exit_btc, exit_price, proceeds_usd, pnl_usd,
                result, close_type, reason, close_reason,
                payout_if_win_usd, profit_if_win_usd, account_id, source, strategy_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                o["id"], r["market_start_ts"], seq, o.get("side"), o.get("entry_sec"),
                o.get("exit_sec"), o.get("size_usd"), o.get("shares"),
                o.get("avg_entry_price"), o.get("best_ask"), o.get("best_ask_c"),
                o.get("entry_fee_usd"), o.get("exit_fee_usd"),
                o.get("entry_btc"), o.get("exit_btc"), o.get("exit_price"),
                o.get("proceeds_usd"), o.get("pnl_usd"),
                o.get("result"), o.get("close_type"), o.get("reason"), o.get("close_reason"),
                o.get("payout_if_win_usd"), o.get("profit_if_win_usd"),
                o.get("account_id"), o.get("source"), o.get("strategy_id"),
            ),
        )


def create_simulation(
    history_dir: Path, *, strategy_id: str, strategy_name: str, strategy_version: int,
    day_from: str, day_to: str, summary: dict, table: dict, rounds: list[dict],
) -> dict:
    """Crea una nuova sessione backtest SQLite (aggregati + orders)."""
    root = simulations_dir(history_dir)
    sid = uuid.uuid4().hex[:12]
    now = _utc_now_iso()
    summary_out = {**summary, "created_at_utc": now}
    path = _sqlite_path(root, sid)
    conn = _connect(path)
    try:
        _init_schema(conn)
        conn.execute(
            """INSERT INTO meta (
                id, schema_version, strategy_id, strategy_name, strategy_version,
                created_at_utc, day_from, day_to, summary_json, table_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                sid, SCHEMA_VERSION, strategy_id, strategy_name, strategy_version,
                now, day_from, day_to, json.dumps(summary_out), json.dumps(table),
            ),
        )
        for r in rounds:
            _insert_round(conn, r)
        conn.commit()
    finally:
        conn.close()
    slim_rounds = [_slim_round(r) for r in rounds]
    return {
        "schema_version": SCHEMA_VERSION, "id": sid,
        "strategy_id": strategy_id, "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "created_at_utc": now, "day_from": day_from, "day_to": day_to,
        "summary": summary_out, "table": table, "rounds": slim_rounds,
        "has_orders": True,
    }


def _slim_round(r: dict) -> dict:
    """Aggregati per UI/Socket: niente lista orders."""
    return {
        "market_start_ts": r["market_start_ts"],
        "hour_utc": r["hour_utc"],
        "ok": r["ok"],
        "error": r.get("error"),
        "pnl_usd": r.get("pnl_usd", 0.0),
        "n_orders": r.get("n_orders", 0),
        "n_wins": r.get("n_wins", 0),
        "n_losses": r.get("n_losses", 0),
        "traded": r.get("traded", False),
        "action_errors": r.get("action_errors") or [],
    }


def _load_sqlite(path: Path) -> dict:
    conn = _connect(path)
    try:
        meta = conn.execute("SELECT * FROM meta LIMIT 1").fetchone()
        if meta is None:
            raise Exception(f"simulation meta missing: {path}")
        data = _meta_dict(meta)
        rows = conn.execute("SELECT * FROM rounds ORDER BY market_start_ts").fetchall()
        data["rounds"] = [_round_from_row(r) for r in rows]
        return data
    finally:
        conn.close()


def _load_json_legacy(root: Path, path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "strategy_version" not in data:
        data["strategy_version"] = 1
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    data["has_orders"] = False
    return data


def load_simulation(history_dir: Path, simulation_id: str) -> dict:
    """Carica meta + rounds aggregati (senza hydratare tutti gli orders)."""
    root = simulations_dir(history_dir)
    sqlite_p = _sqlite_path(root, simulation_id)
    if sqlite_p.is_file():
        return _load_sqlite(sqlite_p)
    json_p = _json_path(root, simulation_id)
    if json_p.is_file():
        return _load_json_legacy(root, json_p)
    raise Exception(f"simulation not found: {simulation_id}")


def load_round_orders(history_dir: Path, simulation_id: str, market_start_ts: int) -> list[dict]:
    """Ordini chiusi di un round (solo SQLite v2)."""
    path = _sqlite_path(simulations_dir(history_dir), simulation_id)
    if not path.is_file():
        raise Exception(f"simulation has no orders store: {simulation_id}")
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE market_start_ts=? ORDER BY seq",
            (market_start_ts,),
        ).fetchall()
        return [_order_from_row(r) for r in rows]
    finally:
        conn.close()


def simulation_has_orders(history_dir: Path, simulation_id: str) -> bool:
    return _sqlite_path(simulations_dir(history_dir), simulation_id).is_file()


def list_simulations(history_dir: Path) -> list[dict]:
    root = simulations_dir(history_dir)
    items: list[tuple[float, dict]] = []
    for path in root.glob("simulation_*.sqlite"):
        conn = _connect(path)
        try:
            meta = conn.execute("SELECT * FROM meta LIMIT 1").fetchone()
            data = _meta_dict(meta)
        finally:
            conn.close()
        items.append((path.stat().st_mtime, simulation_summary(data)))
    for path in root.glob("simulation_*.json"):
        sid = path.stem.removeprefix("simulation_")
        if _sqlite_path(root, sid).is_file():
            continue
        data = _load_json_legacy(root, path)
        items.append((path.stat().st_mtime, simulation_summary(data)))
    items.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in items]


def delete_simulation(history_dir: Path, simulation_id: str) -> None:
    root = simulations_dir(history_dir)
    sqlite_p = _sqlite_path(root, simulation_id)
    json_p = _json_path(root, simulation_id)
    found = False
    if sqlite_p.is_file():
        sqlite_p.unlink()
        found = True
    if json_p.is_file():
        json_p.unlink()
        found = True
    if not found:
        raise Exception(f"simulation not found: {simulation_id}")
