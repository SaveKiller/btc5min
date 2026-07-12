"""Studio delta_win v2: metodo A (griglia |delta|) + B (logistic_isotonic) su tutto Lighter."""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from src.delta_win import hour_bands_hash, predict_delta_win_a
from src.delta_win_bands import DELTA_LOOKUP_MAX, DELTA_WINDOW_HALF, fit_delta_p_for_sec
from src.listats import li_collect_delta_win_dataset, li_delta_win_audit
from src.setup import (
    DELTA_WIN_BAND_MIN_SAMPLES, DELTA_WIN_CHECKPOINTS, DELTA_WIN_MODEL_PATH,
    DELTA_WIN_MODEL_VERSION, VOLATILITY_WINDOWS_SEC,
)

SEED = 42
HOLDOUT_WEEKS = 2
_REPORTS = _ROOT / "data" / "reports"
_MODELS = _ROOT / "models"


def brier(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def _feature_matrix(samples: list[dict]) -> np.ndarray:
    rows = []
    for s in samples:
        rows.append([
            math.log1p(s["abs_delta"]),
            *[math.log1p(s["vols"][w]) for w in VOLATILITY_WINDOWS_SEC],
            *[1.0 if s["intraday_h"] == h else 0.0 for h in range(1, 7)],
        ])
    return np.asarray(rows, dtype=np.float64)


def _labels(samples: list[dict]) -> np.ndarray:
    return np.asarray([s["y_win"] for s in samples], dtype=np.int32)


def _fit_isotonic(probs: np.ndarray, labels: np.ndarray) -> tuple[list[float], list[float]]:
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(probs, labels)
    xs = np.linspace(0.0, 1.0, 21)
    ys = iso.predict(xs)
    return xs.tolist(), ys.tolist()


def _fit_logistic_iso(samples: list[dict], sec: int) -> dict:
    tr = [s for s in samples if s["sec"] == sec]
    X, y = _feature_matrix(tr), _labels(tr)
    clf = LogisticRegression(max_iter=500, random_state=SEED)
    clf.fit(X, y)
    raw = clf.predict_proba(X)[:, 1]
    iso_x, iso_y = _fit_isotonic(raw, y)
    return {
        "type": "logistic_isotonic", "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]), "iso_x": iso_x, "iso_y": iso_y,
    }


def _holdout_weeks(samples: list[dict]) -> list[str]:
    weeks = sorted({s["week"] for s in samples})
    return weeks[-HOLDOUT_WEEKS:]


def _delta_p_diag(table: dict[str, dict]) -> dict:
    ns = [v["n"] for v in table.values()]
    merged = sum(1 for v in table.values() if v["merge_radius"] > 0)
    return {"slot_count": len(table), "merged_slots": merged, "n_min": min(ns), "n_max": max(ns)}


def _diagnostic_holdout(samples: list[dict], artifact: dict, logistic_by_sec: dict) -> dict:
    hold_w = set(_holdout_weeks(samples))
    hold = [s for s in samples if s["week"] in hold_w]
    pa, pb, labels = [], [], []
    for s in hold:
        sk = str(s["sec"])
        pa.append(predict_delta_win_a(s["sec"], s["abs_delta"], artifact))
        m = logistic_by_sec[sk]
        x = float(np.dot(_feature_matrix([s])[0], np.asarray(m["coef"])) + m["intercept"])
        raw = 1.0 / (1.0 + math.exp(-x))
        from src.delta_win import _isotonic_predict
        pb.append(_isotonic_predict(raw, m["iso_x"], m["iso_y"]))
        labels.append(s["y_win"])
    return {
        "holdout_weeks": sorted(hold_w), "n": len(hold),
        "band_brier": brier(pa, labels), "logistic_brier": brier(pb, labels),
    }


def main() -> None:
    print("collecting lighter checkpoint samples...", flush=True)
    audit = li_delta_win_audit()
    samples = li_collect_delta_win_dataset()
    delta_p_by_sec: dict[str, dict] = {}
    logistic_by_sec: dict[str, dict] = {}
    delta_diag: dict[str, dict] = {}
    for sec in DELTA_WIN_CHECKPOINTS:
        table = fit_delta_p_for_sec(samples, sec)
        delta_p_by_sec[str(sec)] = table
        logistic_by_sec[str(sec)] = _fit_logistic_iso(samples, sec)
        ins_p = [predict_delta_win_a(s["sec"], s["abs_delta"], {"delta_p_by_sec": delta_p_by_sec}) for s in samples if s["sec"] == sec]
        ins_y = [s["y_win"] for s in samples if s["sec"] == sec]
        delta_diag[str(sec)] = {
            **_delta_p_diag(table),
            "in_sample_brier": brier(ins_p, ins_y),
        }
    ts_vals = [s["start_ts"] for s in samples]
    artifact = {
        "model_version": DELTA_WIN_MODEL_VERSION,
        "methods": ["delta_band_lookup", "logistic_isotonic"],
        "status": "synthetic_calibrated",
        "target": "delta_side_wins_gamma_outcome",
        "label_source": "gamma_official_excluding_agreement_nan",
        "checkpoints": list(DELTA_WIN_CHECKPOINTS),
        "hour_bands_hash": hour_bands_hash(),
        "vol_windows_sec": list(VOLATILITY_WINDOWS_SEC),
        "band_min_samples": DELTA_WIN_BAND_MIN_SAMPLES,
        "delta_lookup_max": DELTA_LOOKUP_MAX,
        "delta_window_half": DELTA_WINDOW_HALF,
        "training_sample_count": len(samples),
        "training_start_ts_min": min(ts_vals),
        "training_start_ts_max": max(ts_vals),
        "delta_p_by_sec": delta_p_by_sec,
        "logistic_by_sec": logistic_by_sec,
    }
    _MODELS.mkdir(parents=True, exist_ok=True)
    model_path = _ROOT / DELTA_WIN_MODEL_PATH
    model_path.write_text(json.dumps(artifact, indent=4), encoding="utf-8")
    holdout_diag = _diagnostic_holdout(samples, artifact, logistic_by_sec)
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = _REPORTS / f"delta_win_study_v2_{ts}.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": audit, "sample_count": len(samples),
        "delta_p_diagnostics_by_sec": delta_diag,
        "holdout_diagnostic_no_refit": holdout_diag,
        "artifact_path": str(model_path),
    }
    report_path.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(f"written {model_path}")
    print(f"written {report_path}")
    print(f"holdout band_brier={holdout_diag['band_brier']:.5f} logistic_brier={holdout_diag['logistic_brier']:.5f}")


if __name__ == "__main__":
    main()
