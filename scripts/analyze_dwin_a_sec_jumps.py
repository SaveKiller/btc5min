"""Salto DWinA tra secondi contigui con stesso delta sui round reali (.txt)."""

import json
import re
import statistics as stats
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.delta_win import parse_delta_txt

_DATA_DIR = _ROOT / "data"
_REPORTS = _DATA_DIR / "reports"
_DW_A_RE = re.compile(r"^(\d+)%")
_DW_N_RE = re.compile(r"n=(\d+)")
_DELTA_BANDS = [(0, 20), (20, 50), (50, 100), (100, 150), (150, 10**9)]


def parse_dwin_a(cell: str | None) -> tuple[int | None, int | None]:
    if not cell or cell == "---":
        return None, None
    m = _DW_A_RE.match(cell.strip())
    if not m:
        return None, None
    pct = int(m.group(1))
    nm = _DW_N_RE.search(cell)
    return pct, int(nm.group(1)) if nm else None


def _is_btc_cell(token: str) -> bool:
    return token.endswith("$") and token[:-1].isdigit()


def _parse_dwin_a_tokens(parts: list[str], start: int, end: int) -> str | None:
    i = start
    while i < end:
        if parts[i] == "---":
            return "---"
        if parts[i].startswith("["):
            return parts[i]
        if i + 1 < end and parts[i + 1].startswith("["):
            return f"{parts[i]} {parts[i + 1]}"
        if parts[i].endswith("%") and "[" not in parts[i]:
            return parts[i]
        i += 1
    return None


def parse_real_data_row(line: str) -> dict:
    parts = line.split()
    rd_i = parts.index("Rd")
    btc_i = next(i for i in range(6, rd_i) if _is_btc_cell(parts[i]))
    dw_a = _parse_dwin_a_tokens(parts, 6, btc_i)
    return {"sec": int(parts[0]), "delta": parse_delta_txt(parts[4]), "delta_win_a": dw_a}


def parse_round(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    in_data = False
    rows: list[dict] = []
    for line in lines:
        if line.rstrip() == "data:":
            in_data = True
            continue
        if not in_data or not line or line.startswith("-") or line.startswith("sec"):
            continue
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        rows.append(parse_real_data_row(line))
    rows.sort(key=lambda r: r["sec"], reverse=True)
    return rows


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def band_key(abs_delta: int) -> str:
    for lo, hi in _DELTA_BANDS:
        if lo <= abs_delta < hi:
            return f"{lo}-{hi if hi < 1000 else '150+'}"
    raise Exception(f"abs_delta out of bands: {abs_delta}")


def analyze(data_dir: Path, threshold_pp: int = 10) -> dict:
    txt_files = sorted(p for p in data_dir.rglob("btc5m_*.txt") if "lighter" not in str(p).lower())
    pairs_total = pairs_same_delta = pairs_both_dwin = 0
    jumps: list[int] = []
    examples: list[dict] = []
    by_round: list[dict] = []
    band_pairs = {f"{lo}-{hi if hi < 1000 else '150+'}": {"pairs": 0, "gt10": 0, "jumps": []} for lo, hi in _DELTA_BANDS}

    for path in txt_files:
        rows = parse_round(path)
        round_jumps: list[dict] = []
        for a, b in zip(rows, rows[1:]):
            if a["sec"] - b["sec"] != 1:
                continue
            pairs_total += 1
            if a["delta"] is None or b["delta"] is None or a["delta"] != b["delta"]:
                continue
            pairs_same_delta += 1
            pa, na = parse_dwin_a(a["delta_win_a"])
            pb, nb = parse_dwin_a(b["delta_win_a"])
            if pa is None or pb is None:
                continue
            pairs_both_dwin += 1
            jump = abs(pa - pb)
            jumps.append(jump)
            bk = band_key(abs(a["delta"]))
            band_pairs[bk]["pairs"] += 1
            band_pairs[bk]["jumps"].append(jump)
            if jump > threshold_pp:
                band_pairs[bk]["gt10"] += 1
                rec = {
                    "file": str(path.relative_to(_ROOT)).replace("\\", "/"),
                    "sec_hi": a["sec"], "sec_lo": b["sec"],
                    "delta": a["delta"],
                    "dwin_hi": pa, "dwin_lo": pb,
                    "jump_pp": jump,
                    "n_hi": na, "n_lo": nb,
                }
                round_jumps.append(rec)
                examples.append(rec)
        if round_jumps:
            by_round.append({
                "file": str(path.relative_to(_ROOT)).replace("\\", "/"),
                "count": len(round_jumps),
                "max_jump_pp": max(r["jump_pp"] for r in round_jumps),
            })

    jumps_sorted = sorted(jumps)
    n = len(jumps)
    hist = Counter(min(50, (j // 5) * 5) for j in jumps)
    for v in band_pairs.values():
        js = v.pop("jumps")
        v["rate_gt10_pct"] = pct(v["gt10"], v["pairs"])
        v["median_jump_pp"] = round(stats.median(js), 2) if js else None
        v["p95_jump_pp"] = sorted(js)[int(0.95 * (len(js) - 1))] if len(js) > 1 else (js[0] if js else None)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "threshold_pp": threshold_pp,
        "data_dir": str(data_dir),
        "files_scanned": len(txt_files),
        "pairs_consecutive_sec": pairs_total,
        "pairs_same_delta": pairs_same_delta,
        "pairs_both_dwin_a": pairs_both_dwin,
        "pairs_jump_gt_threshold": sum(1 for j in jumps if j > threshold_pp),
        "rate_jump_gt_threshold_pct": pct(sum(1 for j in jumps if j > threshold_pp), pairs_both_dwin),
        "rounds_with_any_jump_gt_threshold": len(by_round),
        "rate_rounds_with_jump_pct": pct(len(by_round), len(txt_files)),
        "jump_pp": {
            "mean": round(stats.mean(jumps), 2) if jumps else None,
            "median": round(stats.median(jumps), 2) if jumps else None,
            "p90": jumps_sorted[int(0.9 * (n - 1))] if n else None,
            "p95": jumps_sorted[int(0.95 * (n - 1))] if n else None,
            "p99": jumps_sorted[int(0.99 * (n - 1))] if n else None,
            "max": max(jumps) if jumps else None,
        },
        "histogram_pp_5bin": {str(k): hist[k] for k in sorted(hist)},
        "by_abs_delta_band": band_pairs,
        "top_examples": sorted(examples, key=lambda r: (-r["jump_pp"], -abs(r["delta"])))[:30],
        "top_rounds": sorted(by_round, key=lambda r: (-r["max_jump_pp"], -r["count"]))[:25],
    }


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR
    threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    report = analyze(data_dir, threshold)
    _REPORTS.mkdir(parents=True, exist_ok=True)
    out = _REPORTS / f"dwin_a_sec_jump_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"files={report['files_scanned']} pairs={report['pairs_both_dwin_a']} "
          f"jump>{threshold}pp={report['pairs_jump_gt_threshold']} ({report['rate_jump_gt_threshold_pct']}%) "
          f"rounds={report['rounds_with_any_jump_gt_threshold']} ({report['rate_rounds_with_jump_pct']}%) "
          f"median={report['jump_pp']['median']}pp p95={report['jump_pp']['p95']}pp max={report['jump_pp']['max']}pp")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
