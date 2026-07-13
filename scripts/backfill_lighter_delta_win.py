"""Backfill colonne delta_win e header modello v2 sui .txt Lighter (idempotente)."""

import sys
from multiprocessing import Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.delta_win import delta_win_header_lines, delta_win_row_from_data, delta_win_txt_matches_artifact, load_delta_win_artifact, parse_intraday_h
from src.lighter_txt_format import _lighter_column_header
from src.listats import read_lighter_data_rows, read_lighter_header
from src.setup import TICKS_ROOT

_DEFAULT_ROUNDS = Path(TICKS_ROOT) / "lighter-rounds5m"
_DW_HDR_KEY = "delta_win_model_version"


def _data_header_ok(col_hdr: str) -> bool:
    return col_hdr.strip() == _lighter_column_header().strip()


def _has_v2_header(lines: list[str]) -> bool:
    for line in lines:
        if line.startswith(f"  {_DW_HDR_KEY}:"):
            return int(line.split(":", 1)[1].strip()) >= 2
        if line.rstrip("\n") == "data:":
            break
    return False


def _is_btc_cell(token: str) -> bool:
    return token.endswith("$") and token[:-1].isdigit()


def _rebuild_lighter_row(stripped: str, sec: int, row: dict, by_sec: dict, intraday_h: int, artifact: dict) -> str:
    parts = stripped.split()
    rs_i = parts.index("Rs")
    btc_i = next(i for i in range(4, rs_i) if _is_btc_cell(parts[i]))
    prefix = "  ".join(parts[:4])
    btc = parts[btc_i]
    vol = "  ".join(parts[btc_i + 1:rs_i])
    rs = " ".join(parts[rs_i:])
    dw = delta_win_row_from_data(sec, row, by_sec, intraday_h, artifact)
    if dw:
        return f"{prefix}  {dw}  {btc}  {vol}  {rs}"
    return f"{prefix}  {btc}  {vol}  {rs}"


def patch_delta_win(path: Path, artifact: dict, dry_run: bool = False) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not text.startswith("header:"):
        raise Exception(f"{path}: expected header:")
    data_i = next(i for i, l in enumerate(lines) if l.rstrip("\n") == "data:")
    col_hdr = lines[data_i + 1].rstrip("\n")
    if _has_v2_header(lines) and _data_header_ok(col_hdr) and delta_win_txt_matches_artifact(lines, artifact):
        return "present"
    hdr = read_lighter_header(path)
    start_ts = int(hdr["market_start_ts"].split()[0])
    intraday_h = parse_intraday_h(hdr, start_ts)
    data_rows = read_lighter_data_rows(path)
    by_sec = {r["sec"]: r for r in data_rows}
    new_body = []
    for line in lines[data_i + 3:]:
        stripped = line.rstrip("\n")
        parts = stripped.split()
        if len(parts) < 10 or not parts[0].isdigit():
            continue
        sec = int(parts[0])
        row = by_sec[sec]
        new_body.append(_rebuild_lighter_row(stripped, sec, row, by_sec, intraday_h, artifact) + "\n")
    if dry_run:
        return "would_patch"
    cleaned = [l for l in lines if not l.startswith("  delta_win_")]
    data_i = next(i for i, l in enumerate(cleaned) if l.rstrip("\n") == "data:")
    if not _has_v2_header(cleaned):
        for i, line in enumerate(cleaned):
            if line.rstrip("\n") == "  risk_variants: [Rs]":
                block = [l + "\n" for l in delta_win_header_lines(artifact)]
                cleaned[i + 1:i + 1] = block
                data_i += len(block)
                break
    sep = "-" * len(_lighter_column_header()) + "\n"
    new_lines = cleaned[:data_i + 1]
    new_lines.append(_lighter_column_header() + "\n")
    new_lines.append(sep)
    new_lines.extend(new_body)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(new_lines), encoding="utf-8")
    tmp.replace(path)
    return "patched"


_artifact: dict | None = None


def _worker(path_str: str) -> tuple[str, str]:
    global _artifact
    return path_str, patch_delta_win(Path(path_str), _artifact)


def _init_pool(artifact: dict) -> None:
    global _artifact
    _artifact = artifact


def cmd_all(rounds_root: Path, workers: int, dry_run: bool) -> None:
    artifact = load_delta_win_artifact()
    paths = sorted(rounds_root.rglob("btc5m_*.txt"))
    if not paths:
        raise Exception(f"no lighter round txt under {rounds_root}")
    stats = {"patched": 0, "present": 0, "would_patch": 0, "errors": 0}
    targets = paths if not dry_run else paths[:50]
    if dry_run:
        for path in targets:
            try:
                stats[patch_delta_win(path, artifact, dry_run=True)] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR {path}: {e}", flush=True)
    elif workers == 1:
        for path in paths:
            try:
                stats[patch_delta_win(path, artifact)] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR {path}: {e}", flush=True)
    else:
        with Pool(workers, initializer=_init_pool, initargs=(artifact,)) as pool:
            for path_str, status in pool.imap_unordered(_worker, [str(p) for p in paths], chunksize=64):
                if status == "patched":
                    stats["patched"] += 1
                elif status == "present":
                    stats["present"] += 1
                else:
                    stats["errors"] += 1
                    print(f"ERROR {path_str}: unexpected status {status}", flush=True)
    print(
        f"done: files={len(paths)} patched={stats['patched']} present={stats['present']} "
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
        workers = int(args[0]) if args[0].isdigit() else 8
        if not args[0].isdigit():
            root = Path(args[0])
    elif len(args) == 2:
        root = Path(args[0])
        workers = int(args[1])
    elif len(args) > 2:
        raise Exception("usage: backfill_lighter_delta_win.py [rounds_root] [workers] [--dry-run]")
    if workers < 1:
        raise Exception(f"workers must be >= 1, got {workers}")
    if not root.is_dir():
        raise Exception(f"lighter rounds directory not found: {root}")
    print(f"root: {root} workers: {workers} dry_run: {dry_run}", flush=True)
    cmd_all(root, workers, dry_run)


if __name__ == "__main__":
    main()
