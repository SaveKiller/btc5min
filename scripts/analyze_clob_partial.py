"""Classifica round con quote partial: no liquidità (delta alto) vs CLOB sospetto.

Uso:
  python scripts/analyze_clob_partial.py <delta_threshold_usd> [data_dir] [log_path]

Scrive report JSON in data/reports/clob_partial_<timestamp>.json
e confronta con data/reports/clob_partial_baseline.json se presente.
"""
import json
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.book import BookSnapshot, tick_quotes_missing

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "data" / "reports" / "clob_partial_baseline.json"
RECORD_FMT_V5 = "<Q f 6f"
RECORD_SIZE_V5 = struct.calcsize(RECORD_FMT_V5)
RECORD_FMT_V6 = "<Q f 6f Q"
RECORD_SIZE_V6 = struct.calcsize(RECORD_FMT_V6)
HEADER_FMT = "<4sHII B x I d d d d d d d"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
LOW_DELTA_PARTIAL_MIN = 10


def read_round_file(path: Path) -> tuple[dict, np.ndarray, list[BookSnapshot]]:
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise Exception(f"file too small: {path}")
    (magic, version, market_start_ts, market_end_ts, outcome, tick_count, fee_rate,
     ptb_price, ptb_chainlink, ptb_gamma, final_price, final_chainlink, final_gamma) = struct.unpack(
        HEADER_FMT, raw[:HEADER_SIZE])
    if magic != b"BTC5":
        raise Exception(f"bad magic in {path}")
    if version not in (5, 6):
        raise Exception(f"unsupported version {version} in {path}")
    ncol = 8 if version == 5 else 9
    rec_size = RECORD_SIZE_V5 if version == 5 else RECORD_SIZE_V6
    ticks = np.zeros((tick_count, ncol), dtype=np.float64)
    books: list[BookSnapshot] = []
    offset = HEADER_SIZE
    for i in range(tick_count):
        if version == 5:
            ticks[i, :8] = struct.unpack(RECORD_FMT_V5, raw[offset:offset + rec_size])
        else:
            ticks[i] = struct.unpack(RECORD_FMT_V6, raw[offset:offset + rec_size])
        offset += rec_size
        snap, offset = BookSnapshot.from_bytes(raw, offset)
        books.append(snap)
    header = {
        "version": version, "market_start_ts": market_start_ts, "market_end_ts": market_end_ts,
        "outcome": outcome, "tick_count": tick_count, "fee_rate": fee_rate,
        "ptb_chainlink": ptb_chainlink,
    }
    return header, ticks, books


def find_bin_files(data_dir: Path) -> list[Path]:
    flat = sorted(data_dir.glob("bin/btc5m_*.bin"))
    if flat:
        return flat
    return sorted(data_dir.glob("**/btc5m_*.bin"))


def book_fully_blocked(snap: BookSnapshot) -> bool:
    return not (snap.up_bids or snap.up_asks or snap.down_bids or snap.down_asks)


def book_certainty_skew(snap: BookSnapshot) -> bool:
    if book_fully_blocked(snap):
        return False
    up_dead = not snap.up_bids and not snap.up_asks
    down_dead = not snap.down_bids and not snap.down_asks
    if up_dead != down_dead:
        return True
    for bids, asks in ((snap.up_bids, snap.up_asks), (snap.down_bids, snap.down_asks)):
        if bids and not asks:
            return True
        if asks and not bids:
            return True
    return False


def load_clob_drops(log_path: Path) -> set[int]:
    if not log_path.exists():
        return set()
    out = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = re.search(r"clob round (\d+) ws drop", line)
        if m:
            out.add(int(m.group(1)))
    return out


def classify_partial(
    partial_idx: list[int],
    ticks: np.ndarray,
    books: list[BookSnapshot],
    ptb_chainlink: float,
    delta_threshold: float,
    clob_log: bool,
) -> dict:
    partial_secs = sorted(int(round(ticks[i, 1])) for i in partial_idx)
    min_p, max_p = min(partial_secs), max(partial_secs)
    tail_only = max_p <= 60
    opening_partial = min_p >= 240
    mid_partial = not tail_only and not opening_partial

    deltas = [abs(float(ticks[i, 6]) - ptb_chainlink) for i in partial_idx]
    high_n = sum(1 for d in deltas if d >= delta_threshold)
    low_n = len(deltas) - high_n
    min_d, max_d = min(deltas), max(deltas)

    last_full_idx: int | None = None
    last_full_prob: int | None = None
    for i, row in enumerate(ticks):
        if tick_quotes_missing(row):
            continue
        last_full_idx = i
        up_mid = (row[2] + row[3]) / 2
        down_mid = (row[4] + row[5]) / 2
        last_full_prob = round(max(up_mid, down_mid) * 100)

    snap = books[last_full_idx] if last_full_idx is not None else books[partial_idx[0]]
    fully_blocked = book_fully_blocked(snap)
    certainty = book_certainty_skew(snap)

    if min_p >= 240:
        verdict = "warmup"
    elif opening_partial and low_n < LOW_DELTA_PARTIAL_MIN:
        verdict = "warmup"
    elif high_n == len(deltas) or (max_d >= delta_threshold and low_n < LOW_DELTA_PARTIAL_MIN):
        verdict = "no_liquidity"
    elif last_full_prob is not None and last_full_prob >= 99:
        verdict = "no_liquidity"
    elif tail_only and last_full_prob is not None and last_full_prob >= 97:
        verdict = "certainty_skew"
    elif certainty and not fully_blocked and low_n == 0:
        verdict = "certainty_skew"
    elif low_n >= LOW_DELTA_PARTIAL_MIN and mid_partial:
        verdict = "clob_suspect"
    elif low_n >= LOW_DELTA_PARTIAL_MIN and fully_blocked and not opening_partial:
        verdict = "clob_suspect"
    elif low_n > 0 and high_n > 0:
        verdict = "mixed"
    elif high_n > low_n:
        verdict = "no_liquidity"
    else:
        verdict = "mixed"

    return {
        "partial_ticks": len(partial_idx),
        "partial_sec": f"{max_p}-{min_p}",
        "tail_only": tail_only,
        "opening_partial": opening_partial,
        "mid_partial": mid_partial,
        "delta_at_partial": {"min": round(min_d), "max": round(max_d), "high_ticks": high_n, "low_ticks": low_n},
        "last_full_prob": last_full_prob,
        "last_book": (
            f"up={len(snap.up_bids)}b/{len(snap.up_asks)}a "
            f"down={len(snap.down_bids)}b/{len(snap.down_asks)}a"
        ),
        "fully_blocked": fully_blocked,
        "certainty_book": certainty,
        "clob_ws_drop": clob_log,
        "verdict": verdict,
    }


def analyze_round(bin_path: Path, clob_drops: set[int], delta_threshold: float) -> dict | None:
    header, ticks, books = read_round_file(bin_path)
    start_ts = header["market_start_ts"]
    ptb = header["ptb_chainlink"]
    partial_idx = [i for i, row in enumerate(ticks) if tick_quotes_missing(row)]
    if not partial_idx:
        return None
    info = classify_partial(partial_idx, ticks, books, ptb, delta_threshold, start_ts in clob_drops)
    info["start_ts"] = start_ts
    info["bin_version"] = header["version"]
    return info


def load_baseline() -> dict | None:
    if not BASELINE.exists():
        return None
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def compare_baseline(results: list[dict], baseline: dict) -> list[str]:
    reviewed = {r["start_ts"]: r for r in baseline.get("manual_reviews", [])}
    notes = []
    for r in results:
        ts = r["start_ts"]
        if ts not in reviewed:
            continue
        exp = reviewed[ts]["verdict"]
        if r["verdict"] != exp:
            notes.append(f"{ts}: auto={r['verdict']} atteso={exp} (review manuale)")
    for ts in baseline.get("pending_reviews", []):
        match = next((r for r in results if r["start_ts"] == ts), None)
        if match:
            notes.append(f"{ts}: pending review -> auto={match['verdict']}")
    return notes


def write_report(
    data_dir: Path,
    log_path: Path,
    delta_threshold: float,
    results: list[dict],
    errors: list[tuple[str, str]],
    clob_drops: set[int],
    baseline_notes: list[str],
) -> Path:
    reports_dir = data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"clob_partial_{ts}.json"

    by_v: dict[str, list] = {}
    for r in results:
        by_v.setdefault(r["verdict"], []).append(r)

    payload = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "log_path": str(log_path),
        "delta_threshold_usd": delta_threshold,
        "baseline_path": str(BASELINE) if BASELINE.exists() else None,
        "rounds_total": len(find_bin_files(data_dir)),
        "rounds_with_partial": len(results),
        "clob_ws_drop_in_log": len(clob_drops),
        "read_errors": [{"file": n, "error": e} for n, e in errors],
        "summary": {v: len(g) for v, g in sorted(by_v.items())},
        "baseline_comparison": baseline_notes,
        "rounds": sorted(results, key=lambda x: x["start_ts"]),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception("usage: analyze_clob_partial.py <delta_threshold_usd> [data_dir] [log_path]")
    delta_threshold = float(sys.argv[1])
    data_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data"
    log_path = Path(sys.argv[3]) if len(sys.argv) > 3 else data_dir / "collector-poly.log"

    clob_drops = load_clob_drops(log_path)
    results, errors = [], []
    for p in find_bin_files(data_dir):
        try:
            r = analyze_round(p, clob_drops, delta_threshold)
            if r:
                results.append(r)
        except Exception as e:
            errors.append((p.name, str(e)))

    baseline = load_baseline()
    baseline_notes = compare_baseline(results, baseline) if baseline else []

    by_v: dict[str, list] = {}
    for r in results:
        by_v.setdefault(r["verdict"], []).append(r)

    print(f"data_dir: {data_dir}")
    print(f"delta_threshold: {delta_threshold}$")
    print(f"Round totali: {len(find_bin_files(data_dir))}")
    print(f"Con tick partial: {len(results)}")
    print(f"Errori lettura: {len(errors)}")
    print(f"CLOB ws drop nel log: {len(clob_drops)}\n")

    for v in ("clob_suspect", "mixed", "certainty_skew", "no_liquidity", "warmup"):
        g = by_v.get(v, [])
        print(f"=== {v}: {len(g)} ===")
        for r in sorted(g, key=lambda x: -x["partial_ticks"])[:20]:
            d = r["delta_at_partial"]
            drop = " [log]" if r["clob_ws_drop"] else ""
            print(
                f"  {r['start_ts']} n={r['partial_ticks']:3d} sec={r['partial_sec']:7s} "
                f"delta={d['min']}-{d['max']}$ (hi={d['high_ticks']} lo={d['low_ticks']}) "
                f"last={r['last_full_prob']}c{drop}"
            )
        if len(g) > 20:
            print(f"  ... +{len(g) - 20} altri")
        print()

    if baseline_notes:
        print("=== Confronto baseline ===")
        for n in baseline_notes:
            print(f"  {n}")
        print()

    out_path = write_report(data_dir, log_path, delta_threshold, results, errors, clob_drops, baseline_notes)
    print(f"Report: {out_path}")


if __name__ == "__main__":
    main()
