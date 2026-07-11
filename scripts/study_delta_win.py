"""Studio delta_win su round Lighter: confronto modelli, calibrazione OOF, artifact versionato."""

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
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from src.delta_win import brownian_win_prob, hour_bands_hash, z_score_w
from src.listats import li_collect_delta_win_dataset, li_delta_win_audit
from src.setup import DELTA_WIN_CHECKPOINTS, DELTA_WIN_MODEL_PATH, DELTA_WIN_MODEL_VERSION, VOLATILITY_WINDOWS_SEC

TRAIN_WEEKS = 9
HOLDOUT_WEEKS = 2
SEED = 42
_REPORTS = _ROOT / "data" / "reports"
_MODELS = _ROOT / "models"


def brier(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def log_loss(probs: list[float], labels: list[int]) -> float:
    eps = 1e-12
    return -sum(y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(probs, labels)) / len(probs)


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


def _apply_iso(p: float, iso_x: list[float], iso_y: list[float]) -> float:
    for i in range(1, len(iso_x)):
        if p <= iso_x[i]:
            x0, x1 = iso_x[i - 1], iso_x[i]
            y0, y1 = iso_y[i - 1], iso_y[i]
            if x1 <= x0:
                return float(y1)
            t = (p - x0) / (x1 - x0)
            return float(y0 + t * (y1 - y0))
    return float(iso_y[-1])


def _split_weeks(samples: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    weeks = sorted({s["week"] for s in samples})
    if len(weeks) < TRAIN_WEEKS + HOLDOUT_WEEKS:
        raise Exception(f"need {TRAIN_WEEKS + HOLDOUT_WEEKS} weeks, got {len(weeks)}")
    train_w = set(weeks[:TRAIN_WEEKS])
    hold_w = set(weeks[TRAIN_WEEKS: TRAIN_WEEKS + HOLDOUT_WEEKS])
    train = [s for s in samples if s["week"] in train_w]
    holdout = [s for s in samples if s["week"] in hold_w]
    return train, holdout, weeks


def _predict_prevalence(train: list[dict], hold: list[dict], sec: int) -> tuple[list[float], dict]:
    tr = [s for s in train if s["sec"] == sec]
    p = sum(s["y_win"] for s in tr) / len(tr)
    probs = [p] * len(hold)
    return probs, {"type": "prevalence", "p": p}


def _predict_brownian(train: list[dict], hold: list[dict], sec: int, vol_w: int = 60) -> tuple[list[float], dict]:
    probs = []
    for s in hold:
        p = brownian_win_prob(s["abs_delta"], s["vols"][vol_w], vol_w, sec)
        probs.append(0.5 if p is None else p)
    return probs, {"type": "brownian", "vol_window": vol_w}


def _predict_lookup(train: list[dict], hold: list[dict], sec: int, vol_w: int = 60) -> tuple[list[float], dict]:
    bins: dict[int, list[int]] = defaultdict(list)
    for s in train:
        if s["sec"] != sec:
            continue
        z = z_score_w(s["abs_delta"], s["vols"][vol_w], vol_w, sec)
        if z is None:
            continue
        b = min(int(z * 2), 40)
        bins[b].append(s["y_win"])
    global_p = sum(s["y_win"] for s in train if s["sec"] == sec) / max(1, sum(1 for s in train if s["sec"] == sec))
    table = []
    for b in range(41):
        ys = bins.get(b, [])
        p = sum(ys) / len(ys) if ys else global_p
        table.append({"z_hi": (b + 1) / 2.0, "p": p})
    probs = []
    for s in hold:
        z = z_score_w(s["abs_delta"], s["vols"][vol_w], vol_w, sec)
        if z is None:
            probs.append(global_p)
            continue
        picked = global_p
        for row in table:
            if z <= row["z_hi"]:
                picked = row["p"]
                break
        probs.append(picked)
    return probs, {"type": "lookup", "vol_window": vol_w, "table": table}


def _predict_logistic_iso(train: list[dict], hold: list[dict], sec: int) -> tuple[list[float], dict, tuple[list[float], list[float]]]:
    tr = [s for s in train if s["sec"] == sec]
    ho = [s for s in hold if s["sec"] == sec]
    X_tr, y_tr = _feature_matrix(tr), _labels(tr)
    clf = LogisticRegression(max_iter=500, random_state=SEED)
    clf.fit(X_tr, y_tr)
    raw = clf.predict_proba(_feature_matrix(ho))[:, 1]
    iso_x, iso_y = _fit_isotonic(raw, _labels(ho))
    probs = [_apply_iso(float(p), iso_x, iso_y) for p in raw]
    spec = {
        "type": "logistic_isotonic", "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]),
        "iso_x": iso_x, "iso_y": iso_y,
    }
    return probs, spec, (iso_x, iso_y)


def _predict_rf_iso(train: list[dict], hold: list[dict], sec: int) -> tuple[list[float], dict]:
    tr = [s for s in train if s["sec"] == sec]
    ho = [s for s in hold if s["sec"] == sec]
    X_tr, y_tr = _feature_matrix(tr), _labels(tr)
    clf = RandomForestClassifier(n_estimators=80, max_depth=6, min_samples_leaf=40, random_state=SEED, n_jobs=-1)
    clf.fit(X_tr, y_tr)
    raw = clf.predict_proba(_feature_matrix(ho))[:, 1]
    iso_x, iso_y = _fit_isotonic(raw, _labels(ho))
    probs = [_apply_iso(float(p), iso_x, iso_y) for p in raw]
    spec = {"type": "rf_isotonic_sklearn", "n_estimators": 80, "max_depth": 6, "iso_x": iso_x, "iso_y": iso_y}
    return probs, spec


def _eval_method(name: str, train: list[dict], holdout: list[dict]) -> dict:
    by_sec_probs: dict[int, list[float]] = {}
    by_sec_labels: dict[int, list[int]] = {}
    specs: dict[str, dict] = {}
    for sec in DELTA_WIN_CHECKPOINTS:
        ho = [s for s in holdout if s["sec"] == sec]
        labels = [s["y_win"] for s in ho]
        if name == "prevalence":
            probs, spec = _predict_prevalence(train, ho, sec)
        elif name == "brownian_v60":
            probs, spec = _predict_brownian(train, ho, sec, 60)
        elif name == "lookup_v60":
            probs, spec = _predict_lookup(train, ho, sec, 60)
        elif name == "logistic_isotonic":
            probs, spec, _ = _predict_logistic_iso(train, ho, sec)
        elif name == "rf_isotonic":
            probs, spec = _predict_rf_iso(train, ho, sec)
        else:
            raise Exception(f"unknown method {name}")
        by_sec_probs[sec] = probs
        by_sec_labels[sec] = labels
        specs[str(sec)] = spec
    all_p = [p for sec in DELTA_WIN_CHECKPOINTS for p in by_sec_probs[sec]]
    all_y = [y for sec in DELTA_WIN_CHECKPOINTS for y in by_sec_labels[sec]]
    week_scores = []
    for w in sorted({s["week"] for s in holdout}):
        wp, wy = [], []
        for sec in DELTA_WIN_CHECKPOINTS:
            for s, p in zip([x for x in holdout if x["week"] == w and x["sec"] == sec], by_sec_probs[sec]):
                wp.append(p)
                wy.append(s["y_win"])
        week_scores.append(brier(wp, wy))
    return {
        "method": name, "brier": brier(all_p, all_y), "log_loss": log_loss(all_p, all_y),
        "week_briers": week_scores, "week_brier_mean": float(np.mean(week_scores)),
        "week_brier_std": float(np.std(week_scores, ddof=1)) if len(week_scores) > 1 else 0.0,
        "specs_by_sec": specs,
    }


def _select_method(results: list[dict]) -> dict:
    order = ["prevalence", "brownian_v60", "lookup_v60", "logistic_isotonic"]
    ranked = [r for r in results if r["method"] in order]
    ranked.sort(key=lambda r: r["brier"])
    best = ranked[0]
    threshold = best["brier"] + best["week_brier_std"]
    for name in order:
        cand = next(r for r in results if r["method"] == name)
        if cand["brier"] <= threshold:
            return cand
    return best


def _fit_final_artifact(samples: list[dict], chosen_method: str) -> dict:
    models_by_sec: dict[str, dict] = {}
    for sec in DELTA_WIN_CHECKPOINTS:
        tr = [s for s in samples if s["sec"] == sec]
        if chosen_method == "prevalence":
            p = sum(s["y_win"] for s in tr) / len(tr)
            models_by_sec[str(sec)] = {"type": "prevalence", "p": p}
        elif chosen_method == "brownian_v60":
            models_by_sec[str(sec)] = {"type": "brownian", "vol_window": 60}
        elif chosen_method == "lookup_v60":
            _, spec = _predict_lookup(tr, tr, sec, 60)
            models_by_sec[str(sec)] = spec
        elif chosen_method == "logistic_isotonic":
            X, y = _feature_matrix(tr), _labels(tr)
            clf = LogisticRegression(max_iter=500, random_state=SEED)
            clf.fit(X, y)
            raw = clf.predict_proba(X)[:, 1]
            iso_x, iso_y = _fit_isotonic(raw, y)
            models_by_sec[str(sec)] = {
                "type": "logistic_isotonic", "coef": clf.coef_[0].tolist(),
                "intercept": float(clf.intercept_[0]), "iso_x": iso_x, "iso_y": iso_y,
            }
        else:
            raise Exception(f"final fit not implemented for {chosen_method}")
    ts = [s["start_ts"] for s in samples]
    return {
        "model_version": DELTA_WIN_MODEL_VERSION,
        "method": chosen_method,
        "status": "synthetic_calibrated",
        "target": "delta_side_wins_gamma_outcome",
        "label_source": "gamma_official_excluding_agreement_nan",
        "checkpoints": list(DELTA_WIN_CHECKPOINTS),
        "hour_bands_hash": hour_bands_hash(),
        "vol_windows_sec": list(VOLATILITY_WINDOWS_SEC),
        "training_sample_count": len(samples),
        "training_start_ts_min": min(ts),
        "training_start_ts_max": max(ts),
        "models_by_sec": models_by_sec,
    }


def main() -> None:
    print("collecting lighter checkpoint samples...", flush=True)
    audit = li_delta_win_audit()
    samples = li_collect_delta_win_dataset()
    train, holdout, weeks = _split_weeks(samples)
    methods = ["prevalence", "brownian_v60", "lookup_v60", "logistic_isotonic", "rf_isotonic"]
    results = [_eval_method(m, train, holdout) for m in methods]
    chosen = _select_method(results)
    artifact = _fit_final_artifact(samples, chosen["method"])
    artifact["holdout"] = {
        "train_weeks": weeks[:TRAIN_WEEKS], "holdout_weeks": weeks[TRAIN_WEEKS: TRAIN_WEEKS + HOLDOUT_WEEKS],
        "chosen_method": chosen["method"], "chosen_brier": chosen["brier"],
        "method_comparison": [{k: r[k] for k in ("method", "brier", "log_loss", "week_brier_mean", "week_brier_std")} for r in results],
    }
    _MODELS.mkdir(parents=True, exist_ok=True)
    model_path = _ROOT / DELTA_WIN_MODEL_PATH
    model_path.write_text(json.dumps(artifact, indent=4), encoding="utf-8")
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = _REPORTS / f"delta_win_study_{ts}.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": audit,
        "sample_count": len(samples),
        "train_count": len(train),
        "holdout_count": len(holdout),
        "weeks": weeks,
        "chosen": chosen,
        "all_methods": results,
        "artifact_path": str(model_path),
    }
    report_path.write_text(json.dumps(report, indent=4), encoding="utf-8")
    print(f"written {model_path}")
    print(f"written {report_path}")
    print(f"chosen={chosen['method']} brier={chosen['brier']:.5f}")


if __name__ == "__main__":
    main()
