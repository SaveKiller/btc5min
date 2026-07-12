"""Confronto delta_win v2 metodo A vs B su round reali Chainlink (label Gamma)."""

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from src.binary_format import read_round
from src.clob_api import side_from_chainlink
from src.convert import iter_round_bin_paths
from src.delta_win import load_delta_win_artifact, predict_delta_win_a, predict_delta_win_b
from src.delta_win_bands import clamp_delta, window_bounds
from src.lighter_ticks import hour_band
from src.settlement import outcome_from_prices
from src.setup import DELTA_WIN_CHECKPOINTS, VOLATILITY_WINDOWS_SEC
from src.txt_format import compute_trailing_vols, chainlink_stale_row
from src.vol_stats import tick_sec

_DATA_DIR = _ROOT / "data"
_REPORTS = _DATA_DIR / "reports"


def brier(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def log_loss(probs: list[float], labels: list[int]) -> float:
    eps = 1e-12
    return -sum(y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(probs, labels)) / len(probs)


def _stale_in_vol_window(ticks: np.ndarray, sec_index: dict[int, int], sec: int, window: int) -> bool:
    from src.vol_stats import vol_window_countdown_secs
    for s in vol_window_countdown_secs(sec, window):
        if s not in sec_index:
            raise Exception(f"missing sec {s}")
        ti = sec_index[s]
        if chainlink_stale_row(ticks[ti, 0], ticks[ti, 8]):
            return True
    return False


def _window_label(abs_delta: int) -> str:
    d = clamp_delta(abs_delta)
    lo, hi = window_bounds(d)
    return f"{lo}-{hi}"


def collect_real_samples(bin_paths: list[Path], artifact: dict) -> list[dict]:
    samples: list[dict] = []
    for bp in bin_paths:
        header, ticks, _ = read_round(str(bp))
        if math.isnan(header["ptb_gamma"]) or math.isnan(header["final_gamma"]):
            continue
        outcome = outcome_from_prices(header["final_gamma"], header["ptb_gamma"])
        ptb = header["ptb_chainlink"]
        start_ts = header["market_start_ts"]
        intraday_h = hour_band(start_ts)
        vols = compute_trailing_vols(ticks)
        sec_index = {tick_sec(ticks[i]): i for i in range(ticks.shape[0])}
        day = bp.parent.parent.name
        for sec in DELTA_WIN_CHECKPOINTS:
            if sec not in sec_index:
                raise Exception(f"{bp}: missing checkpoint sec={sec}")
            if _stale_in_vol_window(ticks, sec_index, sec, max(VOLATILITY_WINDOWS_SEC)):
                continue
            ti = sec_index[sec]
            if chainlink_stale_row(ticks[ti, 0], ticks[ti, 8]):
                continue
            vol_dict: dict[int, int] = {}
            for w in VOLATILITY_WINDOWS_SEC:
                v = vols[w][ti]
                if math.isnan(v):
                    break
                vol_dict[w] = round(v)
            else:
                abs_delta = abs(round(float(ticks[ti, 6]) - ptb))
                side = side_from_chainlink(float(ticks[ti, 6]), ptb)
                y_win = 1 if side == outcome else 0
                pa = predict_delta_win_a(sec, abs_delta, artifact)
                pb = predict_delta_win_b(sec, abs_delta, vol_dict, intraday_h, artifact)
                samples.append({
                    "bin": bp.name, "day": day, "start_ts": start_ts, "sec": sec, "intraday_h": intraday_h,
                    "abs_delta": abs_delta, "vols": vol_dict, "side": side, "outcome": outcome, "y_win": y_win,
                    "p_a": pa, "p_b": pb, "delta_window": _window_label(abs_delta),
                })
    return samples


def _metrics(rows: list[dict], key: str) -> dict:
    if not rows:
        return {"n": 0}
    probs = [r[key] for r in rows]
    labels = [r["y_win"] for r in rows]
    return {
        "n": len(rows), "win_rate": sum(labels) / len(labels),
        "brier": brier(probs, labels), "log_loss": log_loss(probs, labels),
    }


def _group_metrics(samples: list[dict], key_fn, pkey: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        groups[str(key_fn(s))].append(s)
    return {k: _metrics(v, pkey) for k, v in sorted(groups.items())}


def _window_observed(samples: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        groups[f"sec={s['sec']} window={s['delta_window']}"].append(s)
    out = {}
    for k, rows in sorted(groups.items()):
        labels = [r["y_win"] for r in rows]
        pa = [r["p_a"] for r in rows]
        out[k] = {
            "n": len(rows), "win_rate_observed": sum(labels) / len(labels),
            "p_a_mean": float(np.mean(pa)),
        }
    return out


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR
    artifact = load_delta_win_artifact()
    bin_paths = iter_round_bin_paths(data_dir)
    if not bin_paths:
        raise Exception(f"no bin files under {data_dir}")
    samples = collect_real_samples(bin_paths, artifact)
    if not samples:
        raise Exception("no eligible real checkpoint samples with gamma labels")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "artifact_version": artifact["model_version"],
        "artifact_methods": artifact["methods"],
        "round_bins_scanned": len(bin_paths),
        "eligible_samples": len(samples),
        "method_a": {
            "overall": _metrics(samples, "p_a"),
            "by_checkpoint": _group_metrics(samples, lambda s: s["sec"], "p_a"),
            "by_intraday_h": _group_metrics(samples, lambda s: s["intraday_h"], "p_a"),
            "by_window_observed": _window_observed(samples),
        },
        "method_b": {
            "overall": _metrics(samples, "p_b"),
            "by_checkpoint": _group_metrics(samples, lambda s: s["sec"], "p_b"),
            "by_intraday_h": _group_metrics(samples, lambda s: s["intraday_h"], "p_b"),
        },
    }
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = _REPORTS / f"delta_win_compare_{ts}.json"
    out.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(f"written {out}")
    print(f"samples={len(samples)} A_brier={report['method_a']['overall']['brier']:.5f} B_brier={report['method_b']['overall']['brier']:.5f}")


if __name__ == "__main__":
    main()
