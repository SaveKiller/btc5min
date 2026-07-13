"""Valutazione esterna delta_win sui round reali Chainlink (label Gamma affidabili)."""

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
from src.delta_win import load_delta_win_artifact, predict_delta_win_b
from src.lighter_ticks import hour_band
from src.settlement import outcome_from_prices
from src.setup import DELTA_WIN_SECS, VOLATILITY_WINDOWS_SEC
from src.txt_format import compute_trailing_vols, chainlink_stale_row
from src.vol_stats import tick_sec

_DATA_DIR = _ROOT / "data"
_REPORTS = _DATA_DIR / "reports"


def brier(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def log_loss(probs: list[float], labels: list[int]) -> float:
    eps = 1e-12
    return -sum(y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(probs, labels)) / len(probs)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return center - margin, center + margin


def _stale_in_vol_window(ticks: np.ndarray, sec_index: dict[int, int], sec: int, window: int) -> bool:
    from src.vol_stats import vol_window_countdown_secs
    for s in vol_window_countdown_secs(sec, window):
        if s not in sec_index:
            raise Exception(f"missing sec {s}")
        ti = sec_index[s]
        if chainlink_stale_row(ticks[ti, 0], ticks[ti, 8]):
            return True
    return False


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
        for sec in DELTA_WIN_SECS:
            if sec not in sec_index:
                raise Exception(f"{bp}: missing delta_win sec={sec}")
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
                p = predict_delta_win_b(sec, abs_delta, vol_dict, intraday_h, artifact)
                samples.append({
                    "bin": bp.name, "day": day, "start_ts": start_ts, "sec": sec, "intraday_h": intraday_h,
                    "abs_delta": abs_delta, "vols": vol_dict, "side": side, "outcome": outcome, "y_win": y_win,
                    "p": p,
                })
    return samples


def _metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    probs = [r["p"] for r in rows]
    labels = [r["y_win"] for r in rows]
    wins = sum(labels)
    lo, hi = wilson_ci(wins, len(labels))
    return {
        "n": len(rows), "win_rate": wins / len(rows), "win_rate_ci": [lo, hi],
        "brier": brier(probs, labels), "log_loss": log_loss(probs, labels),
    }


def _group_metrics(samples: list[dict], key_fn) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        groups[str(key_fn(s))].append(s)
    return {k: _metrics(v) for k, v in sorted(groups.items())}


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR
    artifact = load_delta_win_artifact()
    bin_paths = iter_round_bin_paths(data_dir)
    if not bin_paths:
        raise Exception(f"no bin files under {data_dir}")
    samples = collect_real_samples(bin_paths, artifact)
    if not samples:
        raise Exception("no eligible real delta_win samples with gamma labels")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "artifact_method": "logistic_isotonic",
        "artifact_version": artifact["model_version"],
        "round_bins_scanned": len(bin_paths),
        "eligible_samples": len(samples),
        "overall": _metrics(samples),
        "by_sec": _group_metrics(samples, lambda s: s["sec"]),
        "by_intraday_h": _group_metrics(samples, lambda s: s["intraday_h"]),
        "by_day": _group_metrics(samples, lambda s: s["day"]),
        "feature_shift": {
            "abs_delta_mean": float(np.mean([s["abs_delta"] for s in samples])),
            "v60_mean": float(np.mean([s["vols"][60] for s in samples])),
        },
    }
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = _REPORTS / f"delta_win_real_eval_{ts}.json"
    out.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(f"written {out}")
    print(f"samples={len(samples)} brier={report['overall']['brier']:.5f}")


if __name__ == "__main__":
    main()
