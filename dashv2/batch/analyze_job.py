"""Job headless: analyze_round su un singolo LoadedRound."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from dashv2.rounds import LoadedRound


def build_round_view(
    loaded: LoadedRound,
    orders: list[dict] | None = None,
    strategy: dict | None = None,
) -> dict:
    """Vista read-only del round; orders/strategy se analyze su simulation."""
    secs = sorted(loaded.ticks_by_sec)
    view = {
        "market_start_ts": loaded.market_start_ts,
        "hour_utc": datetime.fromtimestamp(loaded.market_start_ts, timezone.utc).hour,
        "outcome": loaded.outcome_name,
        "ptb_chainlink": loaded.ptb_chainlink,
        "final_chainlink": loaded.final_chainlink,
        "fee_rate": loaded.fee_rate,
        "secs": secs,
        "ticks": [loaded.ticks_by_sec[s] for s in secs],
    }
    if orders is not None:
        view["orders"] = orders
    if strategy is not None:
        view["strategy"] = strategy
    return view


def _load_module(module_path: Path):
    """Import diretto del file analyze."""
    name = f"dashv2_batch_analyze_{module_path.stem}_{id(module_path)}"
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_reduce_results(module_path: Path):
    """Ritorna reduce_results del modulo, o None se assente."""
    mod = _load_module(module_path)
    return getattr(mod, "reduce_results", None)


def run_analyze_round(
    loaded: LoadedRound,
    module_path: Path,
    orders: list[dict] | None = None,
    strategy: dict | None = None,
) -> dict:
    """Esegue analyze_round sul round; merge metriche + ok/error."""
    hour_utc = datetime.fromtimestamp(loaded.market_start_ts, timezone.utc).hour
    base = {
        "market_start_ts": loaded.market_start_ts,
        "hour_utc": hour_utc,
        "ok": False,
        "error": None,
    }
    try:
        mod = _load_module(module_path)
        metrics = mod.analyze_round(build_round_view(loaded, orders=orders, strategy=strategy))
        return {**base, **metrics, "ok": True, "error": None}
    except Exception as e:
        print(f"batch analyze round error: {e}", flush=True)
        return {**base, "ok": False, "error": str(e)}
