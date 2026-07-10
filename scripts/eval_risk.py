import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from src.binary_format import OUTCOME_NAMES, read_round
from src.book import tick_quotes_missing
from src.clob_api import majority_side
from src.convert import iter_round_bin_paths
from src.risk import compute_risk_state
from src.setup import (
    RISK_FLIP_HYSTERESIS_C, RISK_FLIP_PERSIST_SEC, RISK_MODEL_VERSION, RISK_PRIMARY_VOL_WINDOW_SEC,
    STALL_RECONNECT_SEC, VOLATILITY_WINDOWS_SEC,
)
from src.vol_stats import chainlink_stale, tick_sec

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_REPORTS = _DATA_DIR / "reports"
_SEC_BANDS = [(121, 180), (61, 120), (31, 60), (1, 30)]


def brier_score(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def log_loss(probs: list[float], labels: list[int]) -> float:
    eps = 1e-12
    return -sum(y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(probs, labels)) / len(probs)


def auc_rank(probs: list[float], labels: list[int]) -> float:
  # AUC Mann-Whitney su etichette binarie
    pos = [p for p, y in zip(probs, labels) if y == 1]
    neg = [p for p, y in zip(probs, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    wins = sum(1 for p in pos for n in neg if p > n) + 0.5 * sum(1 for p in pos for n in neg if p == n)
    return wins / (len(pos) * len(neg))


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return center - margin, center + margin


def eligible_row(row, risk, ptb: float) -> tuple[bool, str]:
    if tick_quotes_missing(row):
        return False, "partial"
    if risk.rq_reason == "tie":
        return False, "tie"
    if chainlink_stale(row[0], row[8], STALL_RECONNECT_SEC):
        return False, "stale"
    return True, "ok"


def collect_samples(bin_paths: list[Path]) -> list[dict]:
    samples = []
    for bp in bin_paths:
        header, ticks, _ = read_round(str(bp))
        if header["outcome"] not in (1, 2):
            continue
        outcome = OUTCOME_NAMES[header["outcome"]]
        ptb = header["ptb_chainlink"]
        risks = compute_risk_state(ticks, ptb)
        for i, row in enumerate(ticks):
            sec = tick_sec(row)
            if sec > 180:
                continue
            risk = risks[i]
            ok, reason = eligible_row(row, risk, ptb)
            if not ok:
                continue
            side = majority_side(row[2], row[3], row[4], row[5])
            y_loss = 1 if side != outcome else 0
            rec = {
                "bin": bp.name, "sec": sec, "side": side, "y_loss": y_loss, "gain": float(row[7]),
                "Pq0": risk.Pq0, "eligible": risk.eligible,
            }
            for w in VOLATILITY_WINDOWS_SEC:
                rec[f"Pz_{w}"] = risk.Pz_by_window[w]
            pz_vals = [risk.Pz_by_window[w] for w in VOLATILITY_WINDOWS_SEC if not math.isnan(risk.Pz_by_window[w])]
            rec["Pz_max"] = max(pz_vals) if pz_vals else float("nan")
            rec["Pmax"] = max(rec["Pq0"], rec["Pz_max"]) if pz_vals else rec["Pq0"]
            samples.append(rec)
    return samples


def metrics_for_model(samples: list[dict], prob_key: str) -> dict:
    rows = [s for s in samples if not math.isnan(s[prob_key])]
    if not rows:
        return {"n": 0}
    probs = [s[prob_key] for s in rows]
    labels = [s["y_loss"] for s in rows]
    return {
        "n": len(rows), "loss_rate": sum(labels) / len(labels),
        "brier": brier_score(probs, labels), "log_loss": log_loss(probs, labels),
        "auc": auc_rank(probs, labels),
    }


def metrics_by_sec_band(samples: list[dict], prob_key: str) -> dict:
    out = {}
    for lo, hi in _SEC_BANDS:
        band = [s for s in samples if lo <= s["sec"] <= hi and not math.isnan(s[prob_key])]
        if not band:
            continue
        probs = [s[prob_key] for s in band]
        labels = [s["y_loss"] for s in band]
        out[f"{lo}-{hi}"] = {"n": len(band), "loss_rate": sum(labels) / len(labels), "brier": brier_score(probs, labels)}
    return out


def reliability_buckets(samples: list[dict], prob_key: str) -> list[dict]:
    edges = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 1.01]
    out = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        band = [s for s in samples if lo <= s[prob_key] < hi]
        if not band:
            continue
        k = sum(s["y_loss"] for s in band)
        n = len(band)
        lo_ci, hi_ci = wilson_ci(k, n)
        out.append({
            "p_lo": lo, "p_hi": hi, "n": n, "loss_rate": k / n,
            "wilson_lo": lo_ci, "wilson_hi": hi_ci,
        })
    return out


def round_weighted_loss(samples: list[dict], prob_key: str) -> float:
    by_round: dict[str, list[int]] = {}
    for s in samples:
        if math.isnan(s[prob_key]):
            continue
        by_round.setdefault(s["bin"], []).append(s["y_loss"])
    if not by_round:
        return float("nan")
    return sum(sum(v) / len(v) for v in by_round.values()) / len(by_round)


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR
    bin_paths = iter_round_bin_paths(data_dir)
    samples = collect_samples(bin_paths)
    models = ["Pq0"] + [f"Pz_{w}" for w in VOLATILITY_WINDOWS_SEC] + ["Pmax"]
    summary = {m: metrics_for_model(samples, m) for m in models}
    by_band = {m: metrics_by_sec_band(samples, m) for m in models}
    reliability = {m: reliability_buckets(samples, m) for m in ["Pq0", f"Pz_{RISK_PRIMARY_VOL_WINDOW_SEC}", "Pmax"]}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "risk_model_version": RISK_MODEL_VERSION,
        "data_dir": str(data_dir),
        "round_bins": len(bin_paths),
        "eligible_samples": len(samples),
        "sec_max": 180,
        "filters": ["no_partial", "no_tie", "no_stale_row"],
        "flip_diag_params": {
            "hysteresis_c": RISK_FLIP_HYSTERESIS_C, "persist_sec": RISK_FLIP_PERSIST_SEC,
        },
        "summary": summary,
        "by_sec_band": by_band,
        "reliability": reliability,
        "round_weighted_loss_rate": {m: round_weighted_loss(samples, m) for m in models},
        "note": "preview only, single-day data, not statistically significant",
    }
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = _REPORTS / f"risk_eval_{ts}.json"
    out_path.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(f"written {out_path}")
    print(f"eligible_samples={len(samples)} rounds={len(bin_paths)}")
    for m in models:
        s = summary[m]
        if s.get("n", 0) == 0:
            continue
        print(f"  {m}: n={s['n']} loss={s['loss_rate']:.4f} brier={s['brier']:.5f} auc={s['auc']:.5f}")


if __name__ == "__main__":
    main()
