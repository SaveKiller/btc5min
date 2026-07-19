"""Repository sessioni backtest: un JSON per run sotto history/simulations/."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def simulations_dir(history_dir: Path) -> Path:
    root = history_dir / "simulations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sim_path(root: Path, simulation_id: str) -> Path:
    return root / f"simulation_{simulation_id}.json"


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def simulation_label(data: dict) -> str:
    """Etichetta dropdown: strategy · YYYY-MM-DD HH:MM · day_from→to."""
    dt = data["created_at_utc"][:16].replace("T", " ")
    day_from = data["day_from"]
    day_to = data["day_to"]
    if day_from[:8] == day_to[:8]:
        range_s = f"{day_from}→{day_to[8:]}"
    elif day_from[:5] == day_to[:5]:
        range_s = f"{day_from}→{day_to[5:]}"
    else:
        range_s = f"{day_from}→{day_to}"
    return f"{data['strategy_name']} · {dt} · {range_s}"


def simulation_summary(data: dict) -> dict:
    return {
        "id": data["id"], "strategy_id": data["strategy_id"],
        "strategy_name": data["strategy_name"], "created_at_utc": data["created_at_utc"],
        "day_from": data["day_from"], "day_to": data["day_to"],
        "label": simulation_label(data),
    }


def create_simulation(
    history_dir: Path, *, strategy_id: str, strategy_name: str,
    day_from: str, day_to: str, summary: dict, table: dict, rounds: list[dict],
) -> dict:
    """Crea una nuova sessione backtest con tabella + raw per round."""
    root = simulations_dir(history_dir)
    sid = uuid.uuid4().hex[:12]
    now = _utc_now_iso()
    summary_out = {**summary, "created_at_utc": now}
    payload = {
        "schema_version": SCHEMA_VERSION, "id": sid,
        "strategy_id": strategy_id, "strategy_name": strategy_name,
        "created_at_utc": now, "day_from": day_from, "day_to": day_to,
        "summary": summary_out, "table": table, "rounds": rounds,
    }
    _atomic_write(_sim_path(root, sid), payload)
    return payload


def load_simulation(history_dir: Path, simulation_id: str) -> dict:
    path = _sim_path(simulations_dir(history_dir), simulation_id)
    if not path.is_file():
        raise Exception(f"simulation not found: {simulation_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_simulations(history_dir: Path) -> list[dict]:
    root = simulations_dir(history_dir)
    out: list[dict] = []
    for path in sorted(root.glob("simulation_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(simulation_summary(data))
    return out


def delete_simulation(history_dir: Path, simulation_id: str) -> None:
    path = _sim_path(simulations_dir(history_dir), simulation_id)
    if not path.is_file():
        raise Exception(f"simulation not found: {simulation_id}")
    path.unlink()
