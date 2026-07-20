"""Entry top-level pickleable per ProcessPool (Windows spawn)."""

from __future__ import annotations

from pathlib import Path

from dashv2.batch.analyze_job import run_analyze_round
from dashv2.batch.strategy_job import run_strategy_round
from dashv2.rounds import load_bin


def _market_start_ts(task: dict) -> int:
    if "market_start_ts" in task:
        return int(task["market_start_ts"])
    return int(Path(task["bin_path"]).stem.split("_")[1])


def process_task(task: dict) -> dict:
    """Esegue un job strategy|analyze su un round; dict pickle-friendly."""
    mts = _market_start_ts(task)
    hour_utc = int(task["hour_utc"])
    base = {"market_start_ts": mts, "hour_utc": hour_utc, "ok": False, "error": None}
    try:
        # load_bin: niente RoundRepository/_scan su tutto data_dir per ogni task.
        loaded = load_bin(Path(task["bin_path"]), float(task["stall_reconnect_sec"]))
        job = task["job"]
        if job == "strategy":
            return run_strategy_round(
                loaded=loaded,
                module_path=Path(task["module_path"]),
                strategy_id=task["strategy_id"],
                size_up=float(task["size_up"]),
                size_down=float(task["size_down"]),
            )
        if job == "analyze":
            return run_analyze_round(
                loaded,
                Path(task["module_path"]),
                orders=task["orders"] if "orders" in task else None,
                strategy=task["strategy"] if "strategy" in task else None,
            )
        raise Exception(f"unknown job: {job}")
    except Exception as e:
        print(f"batch worker error: {e}", flush=True)
        return {**base, "ok": False, "error": str(e)}
