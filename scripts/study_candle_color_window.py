"""Studio colore candele: P(next Up | ultime W) + streak; cerca W* ottimale su validation."""

import json
import math
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.listats import li_outcome_series

VAL_WEEKS = 2
HOLDOUT_WEEKS = 2
STANDARD_WINDOWS = (10, 20, 50, 120)
W_SEARCH_MIN = 2
W_SEARCH_MAX = 150
STREAK_MAX = 15
MIN_CELL_N = 30
SIGNAL_BRIER_IMPROVE = 0.001
_REPORTS = _ROOT / "data" / "reports"
_MODELS = _ROOT / "models"


def brier(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def log_loss(probs: list[float], labels: list[int]) -> float:
    eps = 1e-12
    return -sum(y * math.log(p + eps) + (1 - y) * math.log(1 - p + eps) for p, y in zip(probs, labels)) / len(probs)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        raise Exception("wilson_ci n=0")
    phat = k / n
    den = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / den
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / den
    return centre - half, centre + half


def _weeks_sorted(series: list[dict]) -> list[str]:
    return sorted({r["week"] for r in series})


def _split_week_sets(series: list[dict]) -> tuple[set[str], set[str], set[str], list[str], list[str]]:
    weeks = _weeks_sorted(series)
    if len(weeks) < VAL_WEEKS + HOLDOUT_WEEKS + 1:
        raise Exception(f"need more weeks for 3-way split, got {weeks}")
    hold_w = weeks[-HOLDOUT_WEEKS:]
    val_w = weeks[-(HOLDOUT_WEEKS + VAL_WEEKS):-HOLDOUT_WEEKS]
    hold_set, val_set = set(hold_w), set(val_w)
    train_set = set(weeks) - hold_set - val_set
    return train_set, val_set, hold_set, val_w, hold_w


def _indices(series: list[dict], week_set: set[str]) -> list[int]:
    return [i for i, r in enumerate(series) if r["week"] in week_set]


def _ys(series: list[dict]) -> list[int]:
    return [r["y_up"] for r in series]


def _fit_count_table(ys: list[int], fit_idx: list[int], w: int) -> dict[int, dict]:
    wins = Counter()
    totals = Counter()
    for t in fit_idx:
        if t < w:
            continue
        k = sum(ys[t - w:t])
        totals[k] += 1
        wins[k] += ys[t]
    table: dict[int, dict] = {}
    for k, n in totals.items():
        p = wins[k] / n
        lo, hi = wilson_ci(wins[k], n)
        table[k] = {"n": n, "wins": wins[k], "p_up": p, "wilson_lo": lo, "wilson_hi": hi}
    return table


def _predict_count(ys: list[int], eval_idx: list[int], w: int, table: dict[int, dict], base: float) -> tuple[list[float], list[int]]:
    probs, labels = [], []
    for t in eval_idx:
        if t < w:
            continue
        k = sum(ys[t - w:t])
        cell = table.get(k)
        if cell is None or cell["n"] < MIN_CELL_N:
            probs.append(base)
        else:
            probs.append(cell["p_up"])
        labels.append(ys[t])
    return probs, labels


def _current_streak(ys: list[int], t: int) -> tuple[int, int]:
    side = ys[t - 1]
    s = 1
    i = t - 2
    while i >= 0 and ys[i] == side and s < STREAK_MAX:
        s += 1
        i -= 1
    return side, s


def _fit_streak_table(ys: list[int], fit_idx: list[int]) -> dict[str, dict]:
    wins = Counter()
    totals = Counter()
    for t in fit_idx:
        if t < 1:
            continue
        side, s = _current_streak(ys, t)
        key = f"{side}:{s}"
        totals[key] += 1
        wins[key] += ys[t]
    table: dict[str, dict] = {}
    for key, n in totals.items():
        p = wins[key] / n
        lo, hi = wilson_ci(wins[key], n)
        table[key] = {"n": n, "wins": wins[key], "p_up": p, "wilson_lo": lo, "wilson_hi": hi}
    return table


def _predict_streak(ys: list[int], eval_idx: list[int], table: dict[str, dict], base: float) -> tuple[list[float], list[int]]:
    probs, labels = [], []
    for t in eval_idx:
        if t < 1:
            continue
        side, s = _current_streak(ys, t)
        key = f"{side}:{s}"
        cell = table.get(key)
        if cell is None or cell["n"] < MIN_CELL_N:
            probs.append(base)
        else:
            probs.append(cell["p_up"])
        labels.append(ys[t])
    return probs, labels


def _metrics(probs: list[float], labels: list[int], base: float) -> dict:
    if not labels:
        raise Exception("empty eval set")
    base_probs = [base] * len(labels)
    return {
        "n": len(labels),
        "brier": brier(probs, labels),
        "log_loss": log_loss(probs, labels),
        "baseline_brier": brier(base_probs, labels),
        "baseline_log_loss": log_loss(base_probs, labels),
        "brier_improve": brier(base_probs, labels) - brier(probs, labels),
        "mean_p": sum(probs) / len(probs),
        "mean_y": sum(labels) / len(labels),
    }


def _autocorr(ys: list[int], max_lag: int) -> dict[str, float]:
    n = len(ys)
    mean = sum(ys) / n
    var = sum((y - mean) ** 2 for y in ys) / n
    if var == 0:
        raise Exception("zero variance in outcome series")
    out: dict[str, float] = {}
    for lag in range(1, max_lag + 1):
        num = sum((ys[i] - mean) * (ys[i - lag] - mean) for i in range(lag, n))
        out[str(lag)] = num / ((n - lag) * var)
    return out


def _table_range(table: dict[int, dict]) -> dict:
    usable = [c for c in table.values() if c["n"] >= MIN_CELL_N]
    if not usable:
        return {"min_p": None, "max_p": None, "cells_ge_min_n": 0}
    ps = [c["p_up"] for c in usable]
    return {"min_p": min(ps), "max_p": max(ps), "cells_ge_min_n": len(usable)}


def _streak_flip_rates(ys: list[int], fit_idx: list[int]) -> dict[str, dict]:
    cont = Counter()
    tot = Counter()
    for t in fit_idx:
        if t < 1:
            continue
        side, s = _current_streak(ys, t)
        tot[s] += 1
        if ys[t] == side:
            cont[s] += 1
    out: dict[str, dict] = {}
    for s in range(1, STREAK_MAX + 1):
        n = tot[s]
        if n == 0:
            continue
        p = cont[s] / n
        lo, hi = wilson_ci(cont[s], n)
        out[str(s)] = {"n": n, "p_continue": p, "wilson_lo": lo, "wilson_hi": hi}
    return out


def _eval_window(ys: list[int], fit_idx: list[int], eval_idx: list[int], w: int, base: float) -> dict:
    table = _fit_count_table(ys, fit_idx, w)
    probs, labels = _predict_count(ys, eval_idx, w, table, base)
    m = _metrics(probs, labels, base)
    m["w"] = w
    m["p_range"] = _table_range(table)
    return m


def _base_rate(ys: list[int], idx: list[int]) -> float:
    if not idx:
        raise Exception("empty index for base rate")
    return sum(ys[i] for i in idx) / len(idx)


def main() -> None:
    print("loading outcome series...", flush=True)
    series = li_outcome_series()
    if len(series) < W_SEARCH_MAX + 100:
        raise Exception(f"series too short: {len(series)}")
    train_set, val_set, hold_set, val_w, hold_w = _split_week_sets(series)
    ys = _ys(series)
    train_idx = _indices(series, train_set)
    val_idx = _indices(series, val_set)
    hold_idx = _indices(series, hold_set)
    fit_select_idx = train_idx  # fit per scegliere W*
    fit_final_idx = sorted(train_idx + val_idx)  # rifit prima del holdout
    base_select = _base_rate(ys, train_idx)
    base_final = _base_rate(ys, fit_final_idx)
    print(
        f"n={len(series)} train={len(train_idx)} val={len(val_idx)} hold={len(hold_idx)} "
        f"val_weeks={val_w} hold_weeks={hold_w} base_rate={base_select:.4f}",
        flush=True,
    )

    print(f"searching W in [{W_SEARCH_MIN},{W_SEARCH_MAX}] on validation...", flush=True)
    search_rows = []
    best_w, best_brier = None, None
    for w in range(W_SEARCH_MIN, W_SEARCH_MAX + 1):
        m = _eval_window(ys, fit_select_idx, val_idx, w, base_select)
        search_rows.append({
            "w": w, "val_brier": m["brier"], "val_brier_improve": m["brier_improve"],
            "val_log_loss": m["log_loss"], "p_range": m["p_range"],
        })
        if best_brier is None or m["brier"] < best_brier:
            best_brier, best_w = m["brier"], w
    print(f"W*={best_w} val_brier={best_brier:.6f}", flush=True)

    standard_hold = {}
    for w in STANDARD_WINDOWS:
        standard_hold[str(w)] = _eval_window(ys, fit_final_idx, hold_idx, w, base_final)

    w_star_hold = _eval_window(ys, fit_final_idx, hold_idx, best_w, base_final)
    count_table_star = _fit_count_table(ys, fit_final_idx, best_w)

    streak_table = _fit_streak_table(ys, fit_final_idx)
    sp, sl = _predict_streak(ys, hold_idx, streak_table, base_final)
    streak_hold = _metrics(sp, sl, base_final)
    streak_flip = _streak_flip_rates(ys, fit_final_idx)
    autocorr = _autocorr(ys, 20)

    hold_best_improve = max(
        [w_star_hold["brier_improve"]]
        + [standard_hold[str(w)]["brier_improve"] for w in STANDARD_WINDOWS]
        + [streak_hold["brier_improve"]]
    )
    has_signal = hold_best_improve >= SIGNAL_BRIER_IMPROVE

    verdict = "noise"
    if has_signal:
        cells = [(k, c["p_up"]) for k, c in count_table_star.items() if c["n"] >= MIN_CELL_N]
        if len(cells) >= 3:
            ks = [k for k, _ in cells]
            ps = [p for _, p in cells]
            mk, mp = sum(ks) / len(ks), sum(ps) / len(ps)
            num = sum((k - mk) * (p - mp) for k, p in cells)
            den = math.sqrt(sum((k - mk) ** 2 for k, _ in cells) * sum((p - mp) ** 2 for _, p in cells))
            corr = num / den if den else 0.0
            if corr > 0.2:
                verdict = "momentum"
            elif corr < -0.2:
                verdict = "mean_reversion"
            else:
                verdict = "weak_mixed"

    report = {
        "n_series": len(series),
        "start_ts_min": series[0]["start_ts"],
        "start_ts_max": series[-1]["start_ts"],
        "val_weeks": val_w,
        "holdout_weeks": hold_w,
        "base_rate_train": base_select,
        "base_rate_fit": base_final,
        "min_cell_n": MIN_CELL_N,
        "signal_brier_improve_threshold": SIGNAL_BRIER_IMPROVE,
        "w_search": {"min": W_SEARCH_MIN, "max": W_SEARCH_MAX, "w_star": best_w, "val_brier": best_brier},
        "w_search_curve": search_rows,
        "holdout_standard_windows": standard_hold,
        "holdout_w_star": w_star_hold,
        "holdout_streak": streak_hold,
        "streak_p_continue": streak_flip,
        "autocorr_lag": autocorr,
        "has_signal": has_signal,
        "verdict": verdict,
        "count_table_w_star": {str(k): v for k, v in sorted(count_table_star.items())},
        "streak_table": streak_table,
    }

    _REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = _REPORTS / "candle_color_window.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {report_path}", flush=True)

    if has_signal:
        artifact = {
            "model_version": 1,
            "status": "synthetic_calibrated",
            "target": "next_candle_up_given_color_history",
            "label_source": "gamma_official_excluding_agreement_nan",
            "w_star": best_w,
            "standard_windows": list(STANDARD_WINDOWS),
            "min_cell_n": MIN_CELL_N,
            "base_rate": base_final,
            "val_weeks": val_w,
            "holdout_weeks": hold_w,
            "count_by_k": {str(k): {"p_up": v["p_up"], "n": v["n"]} for k, v in count_table_star.items()},
            "streak_by_side_len": {k: {"p_up": v["p_up"], "n": v["n"]} for k, v in streak_table.items()},
            "holdout_brier_improve_w_star": w_star_hold["brier_improve"],
            "verdict": verdict,
        }
        art_path = _MODELS / "candle_color_v1.json"
        art_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"wrote {art_path}", flush=True)
    else:
        print("no signal: artifact not written", flush=True)

    print("\n=== summary ===")
    print(f"W* = {best_w} (selected on validation)")
    print(
        f"holdout W* brier={w_star_hold['brier']:.6f} baseline={w_star_hold['baseline_brier']:.6f} "
        f"improve={w_star_hold['brier_improve']:+.6f}"
    )
    for w in STANDARD_WINDOWS:
        m = standard_hold[str(w)]
        print(
            f"holdout W={w} brier={m['brier']:.6f} improve={m['brier_improve']:+.6f} "
            f"p_range=[{m['p_range']['min_p']}, {m['p_range']['max_p']}]"
        )
    print(f"holdout streak improve={streak_hold['brier_improve']:+.6f}")
    print(f"lag1 autocorr={autocorr['1']:.4f}")
    print(f"has_signal={has_signal} verdict={verdict}")


if __name__ == "__main__":
    main()
    sys.exit(0)
