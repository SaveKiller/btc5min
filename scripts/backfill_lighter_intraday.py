"""Backfill header intraday: Hk sui .txt Lighter gia presenti (idempotente)."""

import re
import sys
from multiprocessing import Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.lighter_ticks import hour_band
from src.setup import TICKS_ROOT

_DEFAULT_ROUNDS = Path(TICKS_ROOT) / "lighter-rounds5m"

_START_TS_HDR_RE = re.compile(r"^\s*market_start_ts:\s*(\d+)")


def _parse_start_ts(lines: list[str]) -> int:
    for line in lines:
        m = _START_TS_HDR_RE.match(line)
        if m:
            return int(m.group(1))
    raise Exception("market_start_ts not found in header")


def patch_intraday(path: Path, dry_run: bool = False) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("header:"):
        raise Exception(f"{path}: expected header:")
    lines = text.splitlines(keepends=True)
    data_i = None
    end_i = None
    has_intraday = False
    for i, line in enumerate(lines):
        if line.rstrip("\n") == "data:":
            data_i = i
            break
        if line.startswith("  intraday:"):
            has_intraday = True
        if line.startswith("  market_end_ts:"):
            end_i = i
    if data_i is None:
        raise Exception(f"{path}: data: section not found")
    if has_intraday:
        return "present"
    if end_i is None:
        raise Exception(f"{path}: market_end_ts not found in header")
    start_ts = _parse_start_ts(lines[:data_i])
    intraday_line = f"  intraday: H{hour_band(start_ts)}\n"
    if dry_run:
        return "would_patch"
    lines.insert(end_i + 1, intraday_line)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(path)
    return "patched"


def _worker(path_str: str) -> tuple[str, str]:
    return path_str, patch_intraday(Path(path_str))


def _iter_txt(rounds_root: Path) -> list[Path]:
    if not rounds_root.is_dir():
        raise Exception(f"lighter rounds directory not found: {rounds_root}")
    return sorted(rounds_root.rglob("btc5m_*.txt"))


def cmd_all(rounds_root: Path, workers: int, dry_run: bool) -> None:
    paths = _iter_txt(rounds_root)
    if not paths:
        raise Exception("no lighter round txt files found")
    stats = {"patched": 0, "present": 0, "would_patch": 0, "errors": 0}
    if dry_run:
        for path in paths:
            try:
                stats[patch_intraday(path, dry_run=True)] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR {path}: {e}", flush=True)
    elif workers == 1:
        for path in paths:
            try:
                stats[patch_intraday(path)] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR {path}: {e}", flush=True)
    else:
        with Pool(workers) as pool:
            for path_str, status in pool.imap_unordered(_worker, [str(p) for p in paths], chunksize=64):
                if status == "patched":
                    stats["patched"] += 1
                elif status == "present":
                    stats["present"] += 1
                else:
                    stats["errors"] += 1
                    print(f"ERROR {path_str}: unexpected status {status}", flush=True)
    n = len(paths)
    print(
        f"done: files={n} patched={stats['patched']} present={stats['present']} "
        f"would_patch={stats['would_patch']} errors={stats['errors']}",
        flush=True,
    )
    if stats["errors"]:
        raise Exception(f"backfill finished with {stats['errors']} errors")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    root = _DEFAULT_ROUNDS
    workers = 8
    if len(args) == 1:
        if args[0].isdigit():
            workers = int(args[0])
        else:
            root = Path(args[0])
    elif len(args) == 2:
        root = Path(args[0])
        workers = int(args[1])
    elif len(args) > 2:
        raise Exception(
            "usage: backfill_lighter_intraday.py [rounds_root] [workers] [--dry-run]"
        )
    if workers < 1:
        raise Exception(f"workers must be >= 1, got {workers}")
    print(f"root: {root}", flush=True)
    print(f"workers: {workers} dry_run: {dry_run}", flush=True)
    cmd_all(root, workers, dry_run)


if __name__ == "__main__":
    main()
