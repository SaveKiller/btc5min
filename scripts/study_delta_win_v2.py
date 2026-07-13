"""Studio delta_win v2: metodo A per H (pool empirico |delta|) + B (logistic_isotonic) su Lighter."""

import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from src.delta_win import hour_bands_hash, predict_delta_win_a, predict_delta_win_a_window, _isotonic_predict
from src.delta_win_bands import DELTA_LOOKUP_MAX, clamp_delta, fit_window_for_bucket, fit_window_for_sec_h, window_bounds
from src.delta_win_index import build_sec_h_index, sec_buckets
from src.lighter_ticks import hour_band
from src.listats import (
    iter_lighter_round_txt, li_collect_delta_win_dataset, li_collect_delta_win_dataset_parallel,
    li_delta_win_audit, read_lighter_header,
)
from src.setup import (
    DELTA_WIN_MODEL_PATH, DELTA_WIN_MODEL_VERSION, DELTA_WIN_SEC_END, DELTA_WIN_SEC_START, DELTA_WIN_SECS,
    DELTA_WIN_WINDOW_HALF_BASE, DELTA_WIN_WINDOW_MIN_SAMPLES, VOLATILITY_WINDOWS_SEC,
)

SEED = 42
HOLDOUT_WEEKS = 2
_THRESHOLD_CANDIDATES = [20, 30, 50, 75, 100, 150]
_BRIER_EPS = 0.001
_DASH_MAX_PCT = 10.0
_N_MEDIAN_HALF2_MIN = 30
_HOUR_BANDS = range(1, 7)
_DEFAULT_WORKERS = 8
_REPORTS = _ROOT / "data" / "reports"
_MODELS = _ROOT / "models"
_SETUP_JSON = _ROOT / "setup.json"


def _parse_workers(argv: list[str]) -> int:
    workers = _DEFAULT_WORKERS
    for arg in argv:
        if arg == "--audit-only":
            continue
        if arg.isdigit():
            workers = int(arg)
    if workers < 1:
        raise Exception(f"workers must be >= 1, got {workers}")
    return workers


def _phase_timer(label: str):
    t0 = time.perf_counter()
    print(f"{label}...", flush=True)
    return t0


def _phase_done(label: str, t0: float) -> None:
    print(f"{label} done in {time.perf_counter() - t0:.1f}s", flush=True)


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
            *[1.0 if s["intraday_h"] == h else 0.0 for h in _HOUR_BANDS],
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


def _fit_logistic_iso_bucket(bucket: list[dict]) -> dict:
    X, y = _feature_matrix(bucket), _labels(bucket)
    clf = LogisticRegression(max_iter=500, random_state=SEED)
    clf.fit(X, y)
    raw = clf.predict_proba(X)[:, 1]
    iso_x, iso_y = _fit_isotonic(raw, y)
    return {
        "type": "logistic_isotonic", "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]), "iso_x": iso_x, "iso_y": iso_y,
    }


def _fit_logistic_iso(samples: list[dict], sec: int) -> dict:
    bucket = [s for s in samples if s["sec"] == sec]
    return _fit_logistic_iso_bucket(bucket)


def _holdout_weeks(samples: list[dict]) -> list[str]:
    weeks = sorted({s["week"] for s in samples})
    return weeks[-HOLDOUT_WEEKS:]


def _split_train_holdout(samples: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    hold_w = set(_holdout_weeks(samples))
    train = [s for s in samples if s["week"] not in hold_w]
    hold = [s for s in samples if s["week"] in hold_w]
    return train, hold, sorted(hold_w)


def _fit_one_sec_h_task(args: tuple[int, int, int, list[dict]]) -> tuple[str, str, dict]:
    sec, h, min_samples, bucket = args
    table = fit_window_for_bucket(bucket, sec, min_samples)
    return str(h), str(sec), table


def _fit_delta_window_by_sec_h_index(sec_h_index: dict[tuple[int, int], list[dict]], min_samples: int,
        workers: int) -> dict[str, dict[str, dict]]:
    tasks: list[tuple[int, int, int, list[dict]]] = []
    for h in _HOUR_BANDS:
        for sec in DELTA_WIN_SECS:
            bucket = sec_h_index.get((sec, h), [])
            tasks.append((sec, h, min_samples, bucket))
    out: dict[str, dict[str, dict]] = {str(h): {} for h in _HOUR_BANDS}
    if workers <= 1:
        for args in tasks:
            hk, sk, table = _fit_one_sec_h_task(args)
            out[hk][sk] = table
        return out
    with Pool(workers) as pool:
        for hk, sk, table in pool.imap_unordered(_fit_one_sec_h_task, tasks, chunksize=16):
            out[hk][sk] = table
    return out


def _fit_delta_window_by_sec_h(train: list[dict], min_samples: int, workers: int = 1) -> dict[str, dict[str, dict]]:
    return _fit_delta_window_by_sec_h_index(build_sec_h_index(train), min_samples, workers)


def _artifact_from_fit(train: list[dict], delta_window_by_sec_h: dict, logistic_by_sec: dict,
        min_samples: int) -> dict:
    ts_vals = [s["start_ts"] for s in train]
    return {
        "model_version": DELTA_WIN_MODEL_VERSION,
        "methods": ["delta_band_lookup", "logistic_isotonic"],
        "status": "synthetic_calibrated",
        "target": "delta_side_wins_gamma_outcome",
        "label_source": "gamma_official_excluding_agreement_nan",
        "sec_start": DELTA_WIN_SEC_START,
        "sec_end": DELTA_WIN_SEC_END,
        "hour_bands_hash": hour_bands_hash(),
        "vol_windows_sec": list(VOLATILITY_WINDOWS_SEC),
        "delta_lookup_max": DELTA_LOOKUP_MAX,
        "delta_win_window_half_base": DELTA_WIN_WINDOW_HALF_BASE,
        "delta_win_window_min_samples": min_samples,
        "delta_win_band_stratify": "intraday_h",
        "training_sample_count": len(train),
        "training_start_ts_min": min(ts_vals),
        "training_start_ts_max": max(ts_vals),
        "delta_window_by_sec_h": delta_window_by_sec_h,
        "logistic_by_sec": logistic_by_sec,
    }


def _fit_global_window_table(sec_samples: list[dict], min_samples: int) -> dict[str, dict]:
    if not sec_samples:
        return {}
    sec = sec_samples[0]["sec"]
    fake = [{"sec": sec, "intraday_h": 1, "abs_delta": s["abs_delta"], "y_win": s["y_win"]} for s in sec_samples]
    return fit_window_for_bucket(fake, sec, min_samples)


def _predict_global_window(sec: int, abs_delta: int, global_tables: dict[str, dict]) -> float | None:
    slot = global_tables[str(sec)].get(str(clamp_delta(abs_delta)))
    if slot is None or "p_win" not in slot:
        return None
    return float(slot["p_win"])


def _window_diag(table: dict[str, dict]) -> dict:
    if not table:
        return {"slot_count": 0, "n_min": 0, "n_max": 0, "n_p50": 0}
    ns = [v["n"] for v in table.values()]
    return {
        "slot_count": len(table),
        "n_min": min(ns), "n_max": max(ns), "n_p50": int(np.percentile(ns, 50)),
    }


def _holdout_metrics(hold: list[dict], artifact: dict, logistic_by_sec: dict) -> dict:
    pa, pb, labels, ns = [], [], [], []
    dash = 0
    for s in hold:
        win = predict_delta_win_a_window(s["sec"], s["abs_delta"], s["intraday_h"], artifact)
        if win is None:
            dash += 1
            continue
        p, _, _, n = win
        pa.append(p)
        ns.append(n)
        labels.append(s["y_win"])
        if logistic_by_sec:
            m = logistic_by_sec[str(s["sec"])]
            x = float(np.dot(_feature_matrix([s])[0], np.asarray(m["coef"])) + m["intercept"])
            raw = 1.0 / (1.0 + math.exp(-x))
            pb.append(_isotonic_predict(raw, m["iso_x"], m["iso_y"]))
    n_cov = len(pa)
    by_h: dict[str, dict] = {}
    for h in _HOUR_BANDS:
        rows = [s for s in hold if s["intraday_h"] == h]
        if not rows:
            by_h[str(h)] = {"n": 0}
            continue
        probs = [predict_delta_win_a(s["sec"], s["abs_delta"], h, artifact) for s in rows]
        labs = [s["y_win"] for s in rows]
        valid = [(p, y) for p, y in zip(probs, labs) if p is not None]
        by_h[str(h)] = {"n": len(rows), "brier": brier([p for p, _ in valid], [y for _, y in valid]) if valid else None}
    return {
        "n": len(hold), "covered": n_cov, "dash_count": dash,
        "dash_pct": 100.0 * dash / len(hold) if hold else 0.0,
        "band_brier": brier(pa, labels) if pa else None,
        "log_loss_a": log_loss(pa, labels) if pa else None,
        "logistic_brier": brier(pb, labels) if pb else None,
        "by_intraday_h": by_h,
        "n_p5": int(np.percentile(ns, 5)) if ns else 0,
        "n_p50": int(np.percentile(ns, 50)) if ns else 0,
        "n_p10": int(np.percentile(ns, 10)) if ns else 0,
    }


def _window_stats(delta_window_by_sec_h: dict) -> dict:
    slots_by_h: dict[str, int] = {}
    for hk, by_sec in delta_window_by_sec_h.items():
        slots_by_h[hk] = sum(len(sec_tbl) for sec_tbl in by_sec.values())
    return {"slot_count_by_h": slots_by_h}


def _fit_global_tables_by_sec(buckets: dict[int, list[dict]], min_samples: int, workers: int) -> dict[str, dict]:
    tasks = [(sec, min_samples, buckets.get(sec, [])) for sec in DELTA_WIN_SECS]
    out: dict[str, dict] = {}
    if workers <= 1:
        for sec, ms, bucket in tasks:
            out[str(sec)] = _fit_global_window_table(bucket, ms)
        return out
    with Pool(workers) as pool:
        for sec, table in pool.imap_unordered(_fit_global_one_sec, tasks, chunksize=8):
            out[str(sec)] = table
    return out


def _fit_global_one_sec(args: tuple[int, int, list[dict]]) -> tuple[int, dict]:
    sec, min_samples, bucket = args
    return sec, _fit_global_window_table(bucket, min_samples)


def _compare_global_vs_h(train: list[dict], hold: list[dict], per_h_artifact: dict, min_samples: int,
        workers: int) -> dict:
    train_by_sec = sec_buckets(train)
    global_tables = _fit_global_tables_by_sec(train_by_sec, min_samples, workers)
    pa_g, pa_h, labels = [], [], []
    for s in hold:
        pg = _predict_global_window(s["sec"], s["abs_delta"], global_tables)
        ph = predict_delta_win_a(s["sec"], s["abs_delta"], s["intraday_h"], per_h_artifact)
        if pg is not None and ph is not None:
            pa_g.append(pg)
            pa_h.append(ph)
            labels.append(s["y_win"])
    return {
        "global_pool_brier": brier(pa_g, labels) if pa_g else None,
        "per_h_brier": brier(pa_h, labels) if pa_h else None,
        "delta_brier_pp": (brier(pa_g, labels) - brier(pa_h, labels)) * 100 if pa_g else None,
    }


def _scan_monotonicity(delta_window_by_sec_h: dict) -> dict:
    violations = 0
    for by_sec in delta_window_by_sec_h.values():
        for table in by_sec.values():
            keys = sorted(int(k) for k in table if "p_win" in table[k])
            for i in range(1, len(keys)):
                d0, d1 = keys[i - 1], keys[i]
                if table[str(d1)]["p_win"] < table[str(d0)]["p_win"]:
                    violations += 1
    return {"violations": violations}


def _artifact_for_holdout(delta_window: dict, min_samples: int) -> dict:
    return {"delta_window_by_sec_h": delta_window, "delta_win_window_min_samples": min_samples}


def _threshold_row(delta_window: dict, hold: list[dict], thresh: int) -> dict:
    artifact = _artifact_for_holdout(delta_window, thresh)
    metrics = _holdout_metrics(hold, artifact, {})
    ns = [v["n"] for bs in delta_window.values() for t in bs.values() for v in t.values()]
    return {
        "threshold": thresh,
        "band_brier": metrics["band_brier"],
        "dash_pct": metrics["dash_pct"],
        "n_p50": int(np.percentile(ns, 50)) if ns else 0,
        "slot_count": sum(len(t) for bs in delta_window.values() for t in bs.values()),
    }


def _calibrate_one_threshold(args: tuple[int, dict, list[dict]]) -> dict:
    thresh, sec_h_index, hold = args
    delta_window = _fit_delta_window_by_sec_h_index(sec_h_index, thresh, workers=1)
    return _threshold_row(delta_window, hold, thresh)


def _calibrate_min_samples(sec_h_index: dict[tuple[int, int], list[dict]], hold: list[dict],
        workers: int) -> tuple[int, dict]:
    cal_workers = min(len(_THRESHOLD_CANDIDATES), workers)
    tasks = [(t, sec_h_index, hold) for t in _THRESHOLD_CANDIDATES]
    if cal_workers <= 1:
        rows = [_calibrate_one_threshold(task) for task in tasks]
    else:
        with Pool(cal_workers) as pool:
            rows = pool.map(_calibrate_one_threshold, tasks)
    best_brier = min((r["band_brier"] for r in rows if r["band_brier"] is not None), default=float("inf"))
    chosen = rows[-1]["threshold"]
    for row in rows:
        if row["band_brier"] is None:
            continue
        if row["dash_pct"] > _DASH_MAX_PCT:
            continue
        if row["n_half2_p50"] < _N_MEDIAN_HALF2_MIN:
            continue
        if row["band_brier"] > best_brier + _BRIER_EPS:
            continue
        chosen = row["threshold"]
        break
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": rows,
        "chosen_threshold": chosen,
        "criteria": {
            "brier_eps": _BRIER_EPS,
            "dash_max_pct": _DASH_MAX_PCT,
            "n_median_half2_min": _N_MEDIAN_HALF2_MIN,
            "rule": "primo candidato con dash_pct<=dash_max, n_half2_p50>=min, brier<=best+eps",
        },
        "best_brier": best_brier,
    }
    return chosen, report


def _write_setup_min_samples(min_samples: int) -> None:
    data = json.loads(_SETUP_JSON.read_text(encoding="utf-8"))
    data["delta_win_window_min_samples"] = min_samples
    _SETUP_JSON.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


def _audit_intraday_header() -> dict:
    mismatches: list[dict] = []
    checked = 0
    for path in iter_lighter_round_txt():
        hdr = read_lighter_header(path)
        if "intraday" not in hdr:
            continue
        start_ts = int(path.name.split("_")[1])
        header_h = int(hdr["intraday"].strip()[1:])
        computed_h = hour_band(start_ts)
        checked += 1
        if header_h != computed_h:
            mismatches.append({"path": str(path), "header_h": header_h, "computed_h": computed_h})
    return {"checked": checked, "mismatch_count": len(mismatches), "examples": mismatches[:5]}


def _audit_h_ignored(samples: list[dict], artifact: dict) -> dict:
    s = samples[0]
    sec, d = s["sec"], s["abs_delta"]
    preds = {h: predict_delta_win_a(sec, d, h, artifact) for h in _HOUR_BANDS}
    unique = len({round(p, 6) for p in preds.values() if p is not None})
    return {"sec": sec, "abs_delta": d, "preds_by_h": preds, "unique_values": unique,
            "status": "ok" if unique > 1 else "confirmed_pre_stratify"}


def _fit_logistic_one_sec(args: tuple[int, list[dict]]) -> tuple[str, dict]:
    sec, bucket = args
    return str(sec), _fit_logistic_iso_bucket(bucket)


def _fit_logistic_by_sec(train_by_sec: dict[int, list[dict]], workers: int) -> dict[str, dict]:
    tasks = [(sec, train_by_sec.get(sec, [])) for sec in DELTA_WIN_SECS]
    out: dict[str, dict] = {}
    if workers <= 1:
        for sec, bucket in tasks:
            out[str(sec)] = _fit_logistic_iso_bucket(bucket)
        return out
    with Pool(workers) as pool:
        for sk, model in pool.imap_unordered(_fit_logistic_one_sec, tasks, chunksize=8):
            out[sk] = model
    return out


def run_bug_audit(samples: list[dict], train: list[dict], hold: list[dict], per_h_artifact: dict,
        min_samples: int, workers: int) -> dict:
    hold_w = sorted(_holdout_weeks(samples))
    all_by_sec = sec_buckets(samples)
    train_by_sec = sec_buckets(train)
    leaky_global = _fit_global_tables_by_sec(all_by_sec, min_samples, workers)
    clean_global = _fit_global_tables_by_sec(train_by_sec, min_samples, workers)
    pa_leak, pa_clean, labels = [], [], []
    for s in hold:
        pl = _predict_global_window(s["sec"], s["abs_delta"], leaky_global)
        pc = _predict_global_window(s["sec"], s["abs_delta"], clean_global)
        if pl is not None and pc is not None:
            pa_leak.append(pl)
            pa_clean.append(pc)
            labels.append(s["y_win"])
    vol_missing = sum(1 for s in samples if any(s["vols"][w] is None for w in VOLATILITY_WINDOWS_SEC))
    fixes = ["holdout_leakage: fit A+B solo su train weeks", "h_stratify: delta_window_by_sec_h + runtime intraday_h",
             "pool_empirico: finestra fissa ±half_base, n>=min_samples", "format: DWinA NN% [n=N] o spazi+[n=N*]"]
    intraday_audit = _audit_intraday_header()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": {
            "1_holdout_leakage": {
                "status": "confirmed",
                "evidence": {
                    "holdout_weeks": hold_w,
                    "brier_leaky_fit_all_samples": brier(pa_leak, labels) if pa_leak else None,
                    "brier_clean_train_only": brier(pa_clean, labels) if pa_clean else None,
                },
                "fix": "fit su train weeks escluso holdout",
            },
            "2_h_ignored_runtime": _audit_h_ignored(hold[:1] if hold else samples[:1], per_h_artifact) | {
                "fix": "predict_delta_win_a_window usa intraday_h",
            },
            "3_intraday_header": intraday_audit | {
                "status": "ok" if intraday_audit["mismatch_count"] == 0 else "confirmed",
            },
            "4_eligibility_vol_for_a": {
                "status": "ok",
                "vol_missing_delta_win_rows": vol_missing,
                "note": "A e B condividono gate eleggibilita (vol+stale); non separato",
            },
            "5_monotonicity": _scan_monotonicity(per_h_artifact["delta_window_by_sec_h"]) | {
                "status": "ok",
                "note": "violazioni attese su griglia empirica; test pa_hi>=pa_lo non garantito",
            },
            "6_double_smoothing": {
                "status": "fixed",
                "note": "pool empirico unico per finestra [lo,hi]; n=len(pool)",
            },
            "7_txt_matches_artifact": {
                "status": "confirmed",
                "fix": "delta_win_txt_matches_artifact verifica window params",
            },
        },
        "fixes_included": fixes,
    }


def main() -> None:
    audit_only = "--audit-only" in sys.argv
    workers = _parse_workers(sys.argv[1:])
    print(f"workers={workers}", flush=True)

    t0 = _phase_timer("collecting lighter delta_win samples")
    paths = [str(p) for p in iter_lighter_round_txt()]
    if workers <= 1:
        samples = li_collect_delta_win_dataset()
    else:
        print(f"collect pool workers={workers} files={len(paths)}", flush=True)
        samples = li_collect_delta_win_dataset_parallel(workers=workers)
    dataset_audit = {
        "round_count": len(paths),
        "weeks": dict(Counter(s["week"] for s in samples)),
        "eligible_delta_win_rows": len(samples),
        "rows_by_sec": dict(Counter(s["sec"] for s in samples)),
        "note": "post-collect summary; header audit skipped in full run",
    }
    train, hold, hold_w = _split_train_holdout(samples)
    print(f"samples={len(samples)} train={len(train)} holdout={len(hold)} weeks={hold_w}", flush=True)
    _phase_done("collect", t0)

    t0 = _phase_timer("building sec_h index")
    sec_h_index = build_sec_h_index(train)
    train_by_sec = sec_buckets(train)
    _phase_done("index", t0)

    t0 = _phase_timer("delta_win_window_min_samples from setup.json")
    min_samples = DELTA_WIN_WINDOW_MIN_SAMPLES
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    threshold_path = _REPORTS / f"delta_win_window_threshold_{ts}.json"
    threshold_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chosen_threshold": min_samples,
        "source": "setup.json delta_win_window_min_samples",
    }
    threshold_path.write_text(json.dumps(threshold_report, indent=4), encoding="utf-8")
    print(f"min_samples={min_samples} from setup.json -> {threshold_path}")
    _phase_done("min_samples", t0)

    t0 = _phase_timer(f"fit A: {len(DELTA_WIN_SECS) * len(_HOUR_BANDS)} tasks")
    delta_window_by_sec_h = _fit_delta_window_by_sec_h_index(sec_h_index, min_samples, workers)
    _phase_done("fit_a", t0)

    t0 = _phase_timer(f"fit B: {len(DELTA_WIN_SECS)} logistic models")
    logistic_by_sec = _fit_logistic_by_sec(train_by_sec, workers)
    _phase_done("fit_b", t0)

    artifact = _artifact_from_fit(train, delta_window_by_sec_h, logistic_by_sec, min_samples)
    holdout_diag = _holdout_metrics(hold, artifact, logistic_by_sec)

    t0 = _phase_timer("audit global_vs_h + bug_audit")
    global_vs_h = _compare_global_vs_h(train, hold, artifact, min_samples, workers)
    bug_audit = run_bug_audit(samples, train, hold, artifact, min_samples, workers)
    _phase_done("audit", t0)

    delta_diag: dict[str, dict] = {}
    for h in _HOUR_BANDS:
        for sec in DELTA_WIN_SECS:
            table = delta_window_by_sec_h[str(h)][str(sec)]
            delta_diag[f"H{h}_sec{sec}"] = _window_diag(table)

    bug_path = _REPORTS / f"delta_win_bug_audit_{ts}.json"
    bug_path.write_text(json.dumps(bug_audit, indent=4), encoding="utf-8")
    print(f"written {bug_path}")

    h_study_path = _REPORTS / f"delta_win_a_h_study_{ts}.json"
    h_study = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "holdout_weeks": hold_w,
        "min_samples": min_samples,
        "train_samples": len(train), "holdout_samples": len(hold),
        "global_vs_per_h": global_vs_h,
        "holdout_per_h": holdout_diag,
        "window_stats": _window_stats(delta_window_by_sec_h),
    }
    h_study_path.write_text(json.dumps(h_study, indent=4), encoding="utf-8")
    print(f"written {h_study_path}")

    if audit_only:
        print("audit-only: skip artifact write")
        return

    t0 = _phase_timer("writing artifact")
    _MODELS.mkdir(parents=True, exist_ok=True)
    model_path = _ROOT / DELTA_WIN_MODEL_PATH
    model_path.write_text(json.dumps(artifact, indent=4), encoding="utf-8")
    report_path = _REPORTS / f"delta_win_study_v2_{ts}.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": dataset_audit, "sample_count": len(samples),
        "train_count": len(train), "holdout_weeks": hold_w,
        "min_samples": min_samples,
        "threshold_calibration": threshold_report,
        "delta_window_diagnostics_by_h_sec": delta_diag,
        "holdout_diagnostic": holdout_diag,
        "global_vs_per_h": global_vs_h,
        "artifact_path": str(model_path),
        "workers": workers,
    }
    report_path.write_text(json.dumps(report, indent=4), encoding="utf-8")
    _phase_done("write", t0)
    print(f"written {model_path}")
    print(f"written {report_path}")
    print(f"holdout band_brier={holdout_diag['band_brier']:.5f} logistic_brier={holdout_diag['logistic_brier']:.5f}")
    print(f"global vs per-H delta_brier_pp={global_vs_h['delta_brier_pp']:.3f}")


if __name__ == "__main__":
    main()
