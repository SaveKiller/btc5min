"""Entry top-level pickleable per ProcessPool (Windows spawn)."""

from __future__ import annotations

from pathlib import Path

from dashv2.batch.analyze_job import run_analyze_round
from dashv2.batch.strategy_job import run_strategy_round
from dashv2.rounds import RoundRepository, load_bin

_repo_cache: dict[tuple[str, float], RoundRepository] = {}


def _repo_for_bin(bin_path: Path, stall_reconnect_sec: float) -> RoundRepository:
    data_dir = bin_path.parent.resolve()
    key = (str(data_dir), stall_reconnect_sec)
    repo = _repo_cache.get(key)
    if repo is None:
        repo = RoundRepository(data_dir, stall_reconnect_sec)
        _repo_cache[key] = repo
    return repo


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
            bin_path = Path(task["bin_path"])
            stall = float(task["stall_reconnect_sec"])
            prev_candles = _repo_for_bin(bin_path, stall).candles(before_ts=mts)
            return run_strategy_round(
                loaded=loaded,
                module_path=Path(task["module_path"]),
                strategy_id=task["strategy_id"],
                size_up=float(task["size_up"]),
                size_down=float(task["size_down"]),
                prev_candles=prev_candles,
            )
        if job == "analyze":
            out = run_analyze_round(
                loaded,
                Path(task["module_path"]),
                orders=task["orders"] if "orders" in task else None,
                strategy=task["strategy"] if "strategy" in task else None,
            )
            out["simulation_id"] = task["simulation_id"]
            return out
        raise Exception(f"unknown job: {job}")
    except Exception as e:
        print(f"batch worker error: {e}", flush=True)
        err = {**base, "ok": False, "error": str(e)}
        if task["job"] == "analyze":
            err["simulation_id"] = task["simulation_id"]
        return err
