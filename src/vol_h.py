"""Fasce H intraday: profili calendario, segmentazione oraria contigua, selezione k."""

import math
import random
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

METHOD_VERSION = "intraday_profile_v1"
PROFILE_DOWS = {
    "mon_thu": frozenset({0, 1, 2, 3}),
    "fri": frozenset({4}),
    "sat": frozenset({5}),
    "sun": frozenset({6}),
}
DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_INTERVAL_BY_PROFILE = {
    "mon_thu": 2,
    "fri": 6,
    "sat": 6,
    "sun": 6,
}
MIN_CELLS_PER_H = 6
K_MIN, K_MAX = 5, 10
TRAIN_WEEKS = 8
HOLDOUT_WEEKS = 3
BOOTSTRAP_N = 40
BOOTSTRAP_SEED = 42
NIGHT_HOURS = range(3, 9)
PEAK_HOURS = range(13, 17)


@dataclass
class Session:
    profile: str
    hour_start: int
    hour_end: int
    median_rv300: float
    median_v60: float
    n_windows: int
    cells: list[tuple[int, int]]


def profile_for_dow(dow: int) -> str:
    for name, dows in PROFILE_DOWS.items():
        if dow in dows:
            return name
    raise Exception(f"invalid dow {dow}")


def week_idx_from_epoch(start_ts: int, epoch: int) -> int:
    return (start_ts - epoch) // (7 * 86400)


def split_train_holdout(windows: list[dict]) -> tuple[list[dict], list[dict], list[int]]:
    weeks = sorted({w["week_idx"] for w in windows})
    if len(weeks) < TRAIN_WEEKS + HOLDOUT_WEEKS:
        raise Exception(f"need {TRAIN_WEEKS + HOLDOUT_WEEKS} weeks, got {len(weeks)}")
    train_w = set(weeks[:TRAIN_WEEKS])
    hold_w = set(weeks[TRAIN_WEEKS: TRAIN_WEEKS + HOLDOUT_WEEKS])
    train = [w for w in windows if w["week_idx"] in train_w]
    holdout = [w for w in windows if w["week_idx"] in hold_w]
    return train, holdout, weeks


def cell_aggregates(windows: list[dict]) -> dict[tuple[int, int], dict]:
    rv: dict[tuple[int, int], list[float]] = defaultdict(list)
    v60: dict[tuple[int, int], list[float]] = defaultdict(list)
    for w in windows:
        key = (w["dow"], w["hour"])
        rv[key].append(w["rv300"])
        v60[key].append(w["v60_med"])
    out = {}
    for key in rv:
        out[key] = {
            "dow": key[0],
            "hour": key[1],
            "median_rv300": float(np.median(rv[key])),
            "median_v60": float(np.median(v60[key])),
            "iqr_rv300": float(np.percentile(rv[key], 75) - np.percentile(rv[key], 25)),
            "n": len(rv[key]),
        }
    return out


def profile_hour_medians(cells: dict[tuple[int, int], dict], profile: str) -> np.ndarray:
    dows = PROFILE_DOWS[profile]
    med = np.zeros(24, dtype=np.float64)
    for h in range(24):
        vals = [cells[(d, h)]["median_rv300"] for d in dows if (d, h) in cells]
        if not vals:
            raise Exception(f"profile {profile} hour {h}: no train cells")
        med[h] = float(np.median(vals))
    return med


def _segment_sse(vals: np.ndarray) -> float:
    if len(vals) == 0:
        return 0.0
    m = float(np.mean(vals))
    return float(np.sum((vals - m) ** 2))


def segment_hours_dp(hour_medians: np.ndarray, n_seg: int, min_len: int) -> list[int]:
    log_v = np.log(hour_medians)
    n = 24
    if n_seg * min_len > n:
        raise Exception(f"cannot split 24h into {n_seg} segments min_len={min_len}")
    sse = np.full((n + 1, n_seg + 1), np.inf)
    bk = np.zeros((n + 1, n_seg + 1), dtype=int)
    sse[0, 0] = 0.0
    for c in range(1, n_seg + 1):
        for i in range(c * min_len, n + 1):
            for j in range((c - 1) * min_len, i - min_len + 1):
                cost = sse[j, c - 1] + _segment_sse(log_v[j:i])
                if cost < sse[i, c]:
                    sse[i, c] = cost
                    bk[i, c] = j
    if math.isinf(sse[n, n_seg]):
        raise Exception(f"segment_hours_dp failed n_seg={n_seg}")
    breaks = [n]
    j = n
    for c in range(n_seg, 0, -1):
        j = int(bk[j, c])
        breaks.append(j)
    breaks.reverse()
    if breaks[0] != 0 or breaks[-1] != n:
        raise Exception(f"bad breaks {breaks}")
    return breaks


def best_n_seg_per_profile(cells: dict[tuple[int, int], dict], profile: str) -> int:
    hour_med = profile_hour_medians(cells, profile)
    log_v = np.log(hour_med)
    min_len = MIN_INTERVAL_BY_PROFILE[profile]
    best_n, best_sse = 0, float("inf")
    max_seg = 24 // min_len
    for n in range(2, max_seg + 1):
        if n * min_len > 24:
            continue
        br = segment_hours_dp(hour_med, n, min_len)
        sse = sum(_segment_sse(log_v[br[i]: br[i + 1]]) for i in range(len(br) - 1))
        if sse < best_sse:
            best_sse, best_n = sse, n
    if best_n == 0:
        raise Exception(f"no segmentation for profile {profile}")
    return best_n


def sessions_for_profile(cells: dict[tuple[int, int], dict], profile: str, n_seg: int) -> list[Session]:
    hour_med = profile_hour_medians(cells, profile)
    min_len = MIN_INTERVAL_BY_PROFILE[profile]
    breaks = segment_hours_dp(hour_med, n_seg, min_len)
    dows = sorted(PROFILE_DOWS[profile])
    sessions = []
    for i in range(len(breaks) - 1):
        h0, h1 = breaks[i], breaks[i + 1]
        sess_cells = [(d, h) for d in dows for h in range(h0, h1)]
        rvs, v60s, nw = [], [], 0
        for c in sess_cells:
            if c in cells:
                rvs.append(cells[c]["median_rv300"])
                v60s.append(cells[c]["median_v60"])
                nw += cells[c]["n"]
            else:
                rvs.append(float(hour_med[c[1]]))
        sessions.append(Session(
            profile=profile,
            hour_start=h0,
            hour_end=h1 - 1,
            median_rv300=float(np.median(rvs)),
            median_v60=float(np.median(v60s)) if v60s else float("nan"),
            n_windows=nw,
            cells=sess_cells,
        ))
    return sessions


def build_profile_sessions(cells: dict[tuple[int, int], dict]) -> tuple[list[Session], dict[str, int]]:
    n_by_profile = {}
    sessions: list[Session] = []
    for profile in ("mon_thu", "fri", "sat", "sun"):
        n_seg = best_n_seg_per_profile(cells, profile)
        n_by_profile[profile] = n_seg
        sessions.extend(sessions_for_profile(cells, profile, n_seg))
    return sessions, n_by_profile


def _jenks_breaks(sorted_vals: np.ndarray, k: int) -> list[int]:
    n = len(sorted_vals)
    if k < 2 or k > n:
        raise Exception(f"jenks: invalid k={k} n={n}")
    sse = np.zeros((n + 1, k + 1))
    bk = np.zeros((n + 1, k + 1), dtype=int)
    sse[0, :] = 0
    sse[:, 0] = float("inf")
    for i in range(1, n + 1):
        sse[i, 1] = _segment_sse(sorted_vals[:i])
        bk[i, 1] = 0
    for c in range(2, k + 1):
        for i in range(c, n + 1):
            best = float("inf")
            best_j = 0
            for j in range(c - 1, i):
                v = sse[j, c - 1] + _segment_sse(sorted_vals[j:i])
                if v < best:
                    best = v
                    best_j = j
            sse[i, c] = best
            bk[i, c] = best_j
    breaks = []
    j = n
    for c in range(k, 1, -1):
        breaks.append(int(bk[j, c]))
        j = int(bk[j, c])
    breaks.sort()
    return breaks


def _merge_small_bands(
    session_labels: np.ndarray, sessions: list[Session], k: int,
) -> np.ndarray:
    """Unisce fasce H con meno di MIN_CELLS_PER_H celle alla vicina per mediana RV."""
    labels = session_labels.copy()
    while True:
        h_cells = defaultdict(int)
        for idx, sess in enumerate(sessions):
            h_cells[int(labels[idx]) + 1] += len(sess.cells)
        small = [h for h in range(1, k + 1) if h_cells[h] < MIN_CELLS_PER_H]
        if not small:
            return labels
        h = min(small, key=lambda x: h_cells[x])
        h_meds = {}
        for hi in range(1, k + 1):
            rvs = [sessions[i].median_rv300 for i in range(len(sessions)) if int(labels[i]) + 1 == hi]
            h_meds[hi] = float(np.median(rvs)) if rvs else float("inf")
        neighbors = [x for x in (h - 1, h + 1) if 1 <= x <= k]
        if not neighbors:
            raise Exception(f"cannot merge small band H{h}")
        target = min(neighbors, key=lambda x: abs(h_meds[x] - h_meds[h]))
        for i in range(len(labels)):
            if int(labels[i]) + 1 == h:
                labels[i] = target - 1


def _renumber_labels(labels: np.ndarray, sessions: list[Session]) -> tuple[np.ndarray, int]:
    old_ids = sorted({int(l) + 1 for l in labels})
    medians = {}
    for oid in old_ids:
        rvs = [sessions[i].median_rv300 for i in range(len(sessions)) if int(labels[i]) + 1 == oid]
        medians[oid] = float(np.median(rvs))
    order = sorted(old_ids, key=lambda x: medians[x])
    remap = {old: new for new, old in enumerate(order, 1)}
    new_labels = np.array([remap[int(labels[i]) + 1] - 1 for i in range(len(labels))], dtype=int)
    return new_labels, len(order)


def sessions_to_lookup(sessions: list[Session], cells: dict[tuple[int, int], dict], k: int) -> tuple[dict[str, dict[str, int]], dict[int, dict]]:
    if k < K_MIN or k > K_MAX:
        raise Exception(f"k={k} outside [{K_MIN},{K_MAX}]")
    meds = np.array([s.median_rv300 for s in sessions], dtype=np.float64)
    order = np.argsort(meds)
    sorted_meds = meds[order]
    breaks = _jenks_breaks(sorted_meds, k)
    labels = np.zeros(len(sessions), dtype=int)
    si = 0
    lab = 0
    for b in breaks + [len(sessions)]:
        while si < b:
            labels[int(order[si])] = lab
            si += 1
        lab += 1
    labels = _merge_small_bands(labels, sessions, k)
    labels, k_eff = _renumber_labels(labels, sessions)
    if k_eff < K_MIN:
        raise Exception(f"effective k={k_eff} after merge below {K_MIN}")
    lookup: dict[str, dict[str, int]] = {str(d): {} for d in range(7)}
    h_cells: dict[int, list[tuple[int, int]]] = defaultdict(list)
    h_meta: dict[int, dict] = {}
    for idx, sess in enumerate(sessions):
        h = int(labels[idx]) + 1
        for dow, hour in sess.cells:
            lookup[str(dow)][str(hour)] = h
            h_cells[h].append((dow, hour))
    for dow in range(7):
        for hour in range(24):
            if str(hour) not in lookup[str(dow)]:
                raise Exception(f"missing cell dow={dow} hour={hour}")
    for h in range(1, k_eff + 1):
        if len(h_cells[h]) < MIN_CELLS_PER_H:
            raise Exception(f"H{h} has {len(h_cells[h])} cells, need {MIN_CELLS_PER_H}")
        cell_rvs = [cells[(d, hr)]["median_rv300"] for d, hr in h_cells[h] if (d, hr) in cells]
        h_meta[h] = {
            "n_cells": len(h_cells[h]),
            "cells": [{"dow": d, "hour": hr} for d, hr in h_cells[h]],
            "median_rv300": round(float(np.median(cell_rvs)), 1),
            "rv300_range": [round(min(cell_rvs), 1), round(max(cell_rvs), 1)],
        }
    return lookup, h_meta, k_eff


def night_peak_ok(lookup: dict[str, dict[str, int]]) -> bool:
    night = {lookup[str(d)][str(h)] for d in range(4) for h in NIGHT_HOURS}
    peak = {lookup[str(d)][str(h)] for d in range(4) for h in PEAK_HOURS}
    if len(night) == 1 and len(peak) == 1 and night == peak:
        return False
    return night != peak


def holdout_mse(windows: list[dict], lookup: dict[str, dict[str, int]], h_medians: dict[int, float]) -> float:
    if not windows:
        raise Exception("holdout windows empty")
    errs = []
    for w in windows:
        h = lookup[str(w["dow"])][str(w["hour"])]
        errs.append((w["rv300"] - h_medians[h]) ** 2)
    return float(np.mean(errs))


def holdout_h_medians(windows: list[dict], lookup: dict[str, dict[str, int]]) -> dict[int, float]:
    by_h: dict[int, list[float]] = defaultdict(list)
    for w in windows:
        h = lookup[str(w["dow"])][str(w["hour"])]
        by_h[h].append(w["rv300"])
    return {h: float(np.median(vs)) for h, vs in by_h.items()}


def holdout_monotone(h_medians: dict[int, float], k: int) -> bool:
    present = sorted(h for h in h_medians if 1 <= h <= k)
    if len(present) < 2:
        return False
    vals = [h_medians[h] for h in present]
    return all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))


def separation_stats(h_meta: dict[int, dict]) -> dict:
    meds = [h_meta[h]["median_rv300"] for h in sorted(h_meta.keys())]
    gaps = [meds[i + 1] / meds[i] if meds[i] > 0 else 0.0 for i in range(len(meds) - 1)]
    return {"medians": meds, "adjacent_ratios": [round(g, 3) for g in gaps]}


def silhouette_sessions(sessions: list[Session], labels: np.ndarray) -> float:
    vals = np.array([s.median_rv300 for s in sessions], dtype=np.float64)
    if len(set(labels)) < 2:
        return -1.0
    scores = []
    for i in range(len(vals)):
        same = labels == labels[i]
        if np.sum(same) <= 1:
            scores.append(0.0)
            continue
        a = float(np.mean(np.abs(vals[same] - vals[i])))
        b = float("inf")
        for c in set(labels):
            if c == labels[i]:
                continue
            mask = labels == c
            b = min(b, float(np.mean(np.abs(vals[mask] - vals[i]))))
        scores.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(scores))


def evaluate_k(cells: dict, sessions: list[Session], holdout: list[dict], k: int) -> dict:
    lookup, h_meta, k_eff = sessions_to_lookup(sessions, cells, k)
    if k_eff < K_MIN or k_eff > K_MAX:
        raise Exception(f"effective k={k_eff} outside [{K_MIN},{K_MAX}]")
    if not night_peak_ok(lookup):
        raise Exception(f"k={k}: night-peak collapsed")
    h_hold = holdout_h_medians(holdout, lookup)
    if not holdout_monotone(h_hold, k_eff):
        raise Exception(f"k={k}: holdout medians not monotone")
    mse = holdout_mse(holdout, lookup, h_hold)
    labels = np.array([lookup[str(s.cells[0][0])][str(s.cells[0][1])] - 1 for s in sessions])
    sil = silhouette_sessions(sessions, labels)
    return {
        "k": k_eff,
        "k_requested": k,
        "lookup": lookup,
        "h_meta": h_meta,
        "holdout_mse": mse,
        "holdout_h_medians": {str(h): round(v, 1) for h, v in h_hold.items()},
        "silhouette": round(sil, 4),
        "separation": separation_stats(h_meta),
        "night_peak_ok": True,
    }


def select_k(cells: dict, sessions: list[Session], holdout: list[dict]) -> dict:
    results = []
    errors = []
    for k in range(K_MIN, K_MAX + 1):
        try:
            r = evaluate_k(cells, sessions, holdout, k)
            results.append(r)
            errors.append(r["holdout_mse"])
        except Exception as e:
            results.append({"k": k, "error": str(e)})
    valid = [r for r in results if "holdout_mse" in r]
    if not valid:
        raise Exception(f"no k in [{K_MIN},{K_MAX}] passed criteria: {results}")
    best_mse = min(r["holdout_mse"] for r in valid)
    err_std = float(np.std([r["holdout_mse"] for r in valid]))
    threshold = best_mse + err_std
    candidates = sorted([r for r in valid if r["holdout_mse"] <= threshold], key=lambda r: r["k"])
    chosen = candidates[0]
    return {
        "candidates_k5_k10": results,
        "chosen": chosen,
        "best_holdout_mse": best_mse,
        "holdout_mse_threshold": threshold,
    }


def bootstrap_stability(windows: list[dict], epoch: int) -> dict:
    rng = random.Random(BOOTSTRAP_SEED)
    weeks = sorted({w["week_idx"] for w in windows})
    k_counts: dict[int, int] = defaultdict(int)
    exact = np.zeros((7, 24), dtype=int)
    within1 = np.zeros((7, 24), dtype=int)
    runs = 0
    ref_lookup = None
    for _ in range(BOOTSTRAP_N):
        sample_weeks = [rng.choice(weeks) for _ in weeks]
        boot = [w for w in windows if w["week_idx"] in sample_weeks]
        if len(boot) < 1000:
            continue
        cells = cell_aggregates(boot)
        sessions, _ = build_profile_sessions(cells)
        holdout = [w for w in windows if w["week_idx"] in set(weeks[-HOLDOUT_WEEKS:])]
        try:
            sel = select_k(cells, sessions, holdout)
            k = sel["chosen"]["k"]
            lookup = sel["chosen"]["lookup"]
            k_counts[k] += 1
            runs += 1
            if ref_lookup is None:
                ref_lookup = lookup
                exact[:, :] = 0
                within1[:, :] = 0
            for dow in range(7):
                for hour in range(24):
                    h = lookup[str(dow)][str(hour)]
                    rh = ref_lookup[str(dow)][str(hour)]
                    if h == rh:
                        exact[dow, hour] += 1
                    if abs(h - rh) <= 1:
                        within1[dow, hour] += 1
        except Exception:
            pass
    if runs == 0:
        raise Exception("bootstrap produced no successful runs")
    return {
        "runs": runs,
        "k_distribution": {str(k): v for k, v in sorted(k_counts.items())},
        "exact_agreement_pct": round(100.0 * float(np.mean(exact / runs)), 1),
        "within_1_agreement_pct": round(100.0 * float(np.mean(within1 / runs)), 1),
    }


def lookup_to_h_bands(lookup: dict[str, dict[str, int]], h_meta: dict[int, dict], sessions: list[Session]) -> dict[str, dict]:
    out = {}
    for h in sorted(h_meta.keys()):
        cells = h_meta[h]["cells"]
        intervals = _readable_intervals(cells, lookup, h)
        out[f"H{h}"] = {
            "rv300_median_range": h_meta[h]["rv300_range"],
            "cluster_median_rv300": h_meta[h]["median_rv300"],
            "n_cells": h_meta[h]["n_cells"],
            "intervals_utc": intervals,
            "cells": cells,
        }
    return out


def _readable_intervals(cells: list[dict], lookup: dict[str, dict[str, int]], h: int) -> list[str]:
    by_prof: dict[str, list[int]] = defaultdict(list)
    for c in cells:
        prof = profile_for_dow(c["dow"])
        if lookup[str(c["dow"])][str(c["hour"])] == h:
            by_prof[prof].append(c["hour"])
    lines = []
    for prof in ("mon_thu", "fri", "sat", "sun"):
        if prof not in by_prof:
            continue
        hours = sorted(set(by_prof[prof]))
        lines.extend(_hour_ranges(prof, hours))
    return lines


def _hour_ranges(profile: str, hours: list[int]) -> list[str]:
    if not hours:
        return []
    ranges = []
    start = prev = hours[0]
    for h in hours[1:]:
        if h == prev + 1:
            prev = h
            continue
        ranges.append(f"{profile} {start:02d}-{prev:02d} UTC")
        start = prev = h
    ranges.append(f"{profile} {start:02d}-{prev:02d} UTC")
    return ranges


def build_canonical_map(chosen: dict, sessions: list[Session], n_by_profile: dict) -> dict:
    k = chosen["k"]
    lookup = chosen["lookup"]
    h_meta = chosen["h_meta"]
    return {
        "method_version": METHOD_VERSION,
        "k": k,
        "profile_sessions": n_by_profile,
        "lookup": lookup,
        "h_bands": lookup_to_h_bands(lookup, h_meta, sessions),
    }
