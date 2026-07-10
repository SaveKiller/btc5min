"""Studio fascie H intraday: Lighter → profili calendario → mappa canonica hour_bands.json."""

import json
import math
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.binary_format import read_round
from src.lighter_ticks import (
    day_start_ts_from_path, iter_day_windows, load_day_mid_by_sec, round_vol_metrics_from_ticks,
    utc_dow_hour, window_vol_metrics, WINDOW_SEC,
)
from src.setup import RISK_MIN_VOL_COVERAGE_RATIO
from src.vol_h import (
    METHOD_VERSION, HOLDOUT_WEEKS, TRAIN_WEEKS, bootstrap_stability, build_canonical_map,
    build_profile_sessions, cell_aggregates, split_train_holdout, select_k, week_idx_from_epoch,
)

LIGHTER_ROOT = Path(r"H:\ticks\lighter-fullrawticks\btc")
_DATA = _ROOT / "data"
_REPORTS = _DATA / "reports"
_HOUR_BANDS = _ROOT / "hour_bands.json"


def scan_lighter_windows() -> tuple[list[dict], dict]:
    """Conserva ogni finestra valida per split/bootstrap senza rileggere i CSV."""
    windows: list[dict] = []
    total_windows = 0
    skipped_coverage = 0
    days = sorted(LIGHTER_ROOT.rglob("raw-btc-*.csv"))
    if not days:
        raise Exception(f"no lighter csv under {LIGHTER_ROOT}")
    epoch = day_start_ts_from_path(str(days[0]))
    for csv_path in days:
        t0 = time.time()
        by_sec = load_day_mid_by_sec(str(csv_path))
        day_start = day_start_ts_from_path(str(csv_path))
        day_used = 0
        for start_ts, mids, cov in iter_day_windows(by_sec, day_start):
            total_windows += 1
            if cov < RISK_MIN_VOL_COVERAGE_RATIO:
                skipped_coverage += 1
                continue
            if any(math.isnan(m) for m in mids):
                skipped_coverage += 1
                continue
            m = window_vol_metrics(mids, start_ts)
            dow, hour = utc_dow_hour(start_ts)
            windows.append({
                "start_ts": start_ts,
                "dow": dow,
                "hour": hour,
                "week_idx": week_idx_from_epoch(start_ts, epoch),
                "rv300": m["rv300"],
                "v60_med": m["v60_med"],
            })
            day_used += 1
        print(f"lighter {csv_path.name}: {day_used} windows in {time.time()-t0:.1f}s", flush=True)
    coverage = {
        "days": len(days),
        "total_windows": total_windows,
        "skipped_coverage": skipped_coverage,
        "used_windows": len(windows),
        "epoch_week0_ts": epoch,
    }
    return windows, coverage


def hour_dow_matrix(cells: dict) -> dict:
    out = {}
    for (dow, hour), c in cells.items():
        out[f"{dow}_{hour}"] = c
    return out


def validate_chainlink_rounds(lookup: dict[str, dict[str, int]], data_dir: Path) -> dict:
    dates = sorted(
        p.name for p in data_dir.iterdir()
        if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", p.name) and (p / "bin").is_dir()
    )
    if not dates:
        raise Exception(f"no validation dates under {data_dir}")
    by_h: dict[int, list[dict]] = defaultdict(list)
    for date in dates:
        for bp in sorted((data_dir / date / "bin").glob("*.bin")):
            header, ticks, _ = read_round(str(bp))
            start = header["market_start_ts"]
            if start % WINDOW_SEC != 0:
                raise Exception(f"round not 5min aligned: {start}")
            dow, hour = utc_dow_hour(start)
            h = lookup[str(dow)][str(hour)]
            m = round_vol_metrics_from_ticks(ticks)
            by_h[h].append({"start_ts": start, "rv300": m["rv300"], "v60_med": m["v60_med"]})
    h_keys = sorted(by_h.keys())
    summary = {}
    med_rv = []
    for h in h_keys:
        rows = by_h[h]
        rv = [r["rv300"] for r in rows if not math.isnan(r["rv300"])]
        v60 = [r["v60_med"] for r in rows if not math.isnan(r["v60_med"])]
        summary[f"H{h}"] = {
            "n_rounds": len(rows),
            "median_rv300": round(float(np.median(rv)), 1) if rv else None,
            "median_v60": round(float(np.median(v60)), 1) if v60 else None,
        }
        if rv:
            med_rv.append((h, float(np.median(rv))))
    distinct_h = len(h_keys)
    if distinct_h < 2:
        return {
            "dates": dates,
            "total_rounds": sum(len(by_h[h]) for h in h_keys),
            "by_h": summary,
            "status": "not_testable",
            "reason": f"only {distinct_h} distinct H in local rounds",
        }
    mono = all(med_rv[i][1] <= med_rv[i + 1][1] for i in range(len(med_rv) - 1))
    return {
        "dates": dates,
        "total_rounds": sum(len(by_h[h]) for h in h_keys),
        "by_h": summary,
        "status": "ok",
        "monotone_median_rv300": mono,
        "distinct_h": distinct_h,
    }


def publish_hour_bands(canonical: dict, generated_at: str) -> None:
    payload = {
        "method_version": canonical["method_version"],
        "k": canonical["k"],
        "generated_at": generated_at,
        "profile_sessions": canonical["profile_sessions"],
        "intervals": {h: canonical["h_bands"][h]["intervals_utc"] for h in canonical["h_bands"]},
        "lookup": canonical["lookup"],
    }
    _HOUR_BANDS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"written {_HOUR_BANDS}")


def main() -> None:
    print("scan lighter ticks...", flush=True)
    windows, lighter_cov = scan_lighter_windows()
    train, holdout, weeks = split_train_holdout(windows)
    cells_train = cell_aggregates(train)
    cells_all = cell_aggregates(windows)
    sessions, n_by_profile = build_profile_sessions(cells_train)
    selection = select_k(cells_train, sessions, holdout)
    chosen = selection["chosen"]
    canonical = build_canonical_map(chosen, sessions, n_by_profile)
    print("bootstrap stability...", flush=True)
    bootstrap = bootstrap_stability(windows, lighter_cov["epoch_week0_ts"])
    print("validate chainlink rounds...", flush=True)
    validation = validate_chainlink_rounds(chosen["lookup"], _DATA)
    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "method_version": METHOD_VERSION,
        "literature_summary": {
            "weekend_lower": "Wang et al.; Ma & Tanizaki",
            "night_utc_low": "minimo attività ~03-08 UTC",
            "us_eu_overlap_peak": "picco 13-16 UTC feriale",
            "note": "profili calendario + segmentazione oraria contigua, non clustering lineare Mon→Dom",
        },
        "lighter_coverage": lighter_cov,
        "temporal_split": {
            "train_weeks": TRAIN_WEEKS,
            "holdout_weeks": HOLDOUT_WEEKS,
            "week_indices": weeks,
            "train_windows": len(train),
            "holdout_windows": len(holdout),
        },
        "profile_sessions": n_by_profile,
        "hour_dow_matrix_train": hour_dow_matrix(cells_train),
        "hour_dow_matrix_all": hour_dow_matrix(cells_all),
        "sessions": [
            {
                "profile": s.profile,
                "hours": f"{s.hour_start:02d}-{s.hour_end:02d}",
                "median_rv300": round(s.median_rv300, 1),
                "median_v60": round(s.median_v60, 1),
                "n_windows": s.n_windows,
            }
            for s in sessions
        ],
        "k_selection": selection,
        "bootstrap": bootstrap,
        "h_bands": canonical["h_bands"],
        "lookup_table": canonical["lookup"],
        "validation_chainlink": validation,
        "limitations": [
            "Training Lighter apr-giu 2026; validazione Chainlink su date locali",
            "Feed Lighter mid != Chainlink",
            "H è previsione calendario live-safe, non vol intra-round",
        ],
    }
    _REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = _REPORTS / f"vol_h_study_{ts}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    publish_hour_bands(canonical, generated_at)
    print(f"written {out}")
    print(f"H bands: k={chosen['k']} holdout_mse={chosen['holdout_mse']:.1f} silhouette={chosen['silhouette']}")


if __name__ == "__main__":
    main()
