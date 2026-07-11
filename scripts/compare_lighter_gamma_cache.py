"""Confronta cache Gamma e round .txt tra baseline per-slug e rebuild bulk."""

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_cache(path: Path) -> dict[int, dict]:
    cache: dict[int, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cache[int(row["start_ts"])] = row
    return cache


def _start_ts_from_txt(path: Path) -> int:
    m = re.match(r"btc5m_(\d+)_", path.name)
    if not m:
        raise Exception(f"unexpected txt name: {path.name}")
    return int(m.group(1))


def _gamma_fields_equal(a: dict, b: dict) -> list[str]:
    diffs: list[str] = []
    for key in ("ptb", "final", "outcome"):
        va, vb = a.get(key), b.get(key)
        if va is None and vb is None:
            continue
        if isinstance(va, float) and isinstance(vb, float):
            if abs(va - vb) > 1e-6:
                diffs.append(f"{key}: {va} vs {vb}")
        elif va != vb:
            diffs.append(f"{key}: {va} vs {vb}")
    return diffs


def compare_caches(baseline: Path, bulk: Path, start_ts_list: list[int]) -> dict:
    base = _load_cache(baseline)
    new = _load_cache(bulk)
    report = {"matched": 0, "missing_in_bulk": [], "missing_in_baseline": [], "field_mismatch": {}}
    for ts in sorted(start_ts_list):
        if ts not in base:
            report["missing_in_baseline"].append(ts)
            continue
        if ts not in new:
            report["missing_in_bulk"].append(ts)
            continue
        diffs = _gamma_fields_equal(base[ts], new[ts])
        if diffs:
            report["field_mismatch"][ts] = diffs
        else:
            report["matched"] += 1
    return report


def compare_txt_dirs(baseline_dir: Path, bulk_dir: Path) -> dict:
    report = {"matched": 0, "missing_in_bulk": [], "missing_in_baseline": [], "content_mismatch": []}
    baseline_files = sorted(baseline_dir.glob("btc5m_*.txt"))
    bulk_names = {p.name for p in bulk_dir.glob("btc5m_*.txt")}
    for bp in baseline_files:
        bulk_path = bulk_dir / bp.name
        if not bulk_path.is_file():
            report["missing_in_bulk"].append(bp.name)
            continue
        if bp.read_bytes() != bulk_path.read_bytes():
            report["content_mismatch"].append(bp.name)
        else:
            report["matched"] += 1
    for name in sorted(bulk_names - {p.name for p in baseline_files}):
        report["missing_in_baseline"].append(name)
    return report


def main() -> None:
    if len(sys.argv) != 6:
        raise Exception(
            "usage: compare_lighter_gamma_cache.py "
            "<baseline_cache.jsonl> <bulk_cache.jsonl> "
            "<baseline_txt_dir> <bulk_txt_dir> <week_iso>")
    baseline_cache = Path(sys.argv[1])
    bulk_cache = Path(sys.argv[2])
    baseline_txt = Path(sys.argv[3]) / sys.argv[5]
    bulk_txt = Path(sys.argv[4]) / sys.argv[5]
    start_ts_list = [_start_ts_from_txt(p) for p in sorted(baseline_txt.glob("btc5m_*.txt"))]
    cache_report = compare_caches(baseline_cache, bulk_cache, start_ts_list)
    txt_report = compare_txt_dirs(baseline_txt, bulk_txt)
    print("cache:", json.dumps(cache_report, indent=2))
    print("txt:", json.dumps({k: v for k, v in txt_report.items() if k != "content_mismatch" or v}, indent=2))
    if cache_report["field_mismatch"] or cache_report["missing_in_bulk"] or cache_report["missing_in_baseline"]:
        raise Exception("cache comparison failed")
    if txt_report["content_mismatch"] or txt_report["missing_in_bulk"] or txt_report["missing_in_baseline"]:
        raise Exception("txt comparison failed")
    print(f"OK: {cache_report['matched']} cache rows, {txt_report['matched']} txt files match")


if __name__ == "__main__":
    main()
