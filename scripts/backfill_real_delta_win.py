"""Backfill delta_win_a/b nei .txt reali rigenerando da .bin (idempotente)."""

import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.binary_format import read_round, txt_path_for_bin
from src.convert import iter_round_bin_paths, read_txt_warnings, warnings_from_header, write_round_txt
from src.delta_win import delta_win_txt_matches_artifact, load_delta_win_artifact
from src.txt_format import format_column_header

_DATA_DIR = _ROOT / "data"
_STUDY_SCRIPT = _ROOT / "scripts" / "study_delta_win_v2.py"
_artifact: dict | None = None


def run_delta_win_study() -> None:
    print(f"running {_STUDY_SCRIPT}...", flush=True)
    r = subprocess.run([sys.executable, str(_STUDY_SCRIPT)], cwd=_ROOT)
    if r.returncode != 0:
        raise Exception(f"study_delta_win_v2.py failed with exit code {r.returncode}")
    import src.delta_win as dw
    dw._artifact_cache = None


def _txt_ok(txt_path: Path) -> bool:
    if not txt_path.is_file():
        return False
    lines = txt_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.rstrip("\n") == "data:" and i + 1 < len(lines):
            if lines[i + 1].strip() != format_column_header().strip():
                return False
            return delta_win_txt_matches_artifact(lines, _artifact)
    return False


def patch_bin(bin_path: Path, dry_run: bool = False) -> str:
    txt_path = txt_path_for_bin(str(bin_path))
    if _txt_ok(txt_path):
        return "present"
    if dry_run:
        return "would_patch"
    warnings = read_txt_warnings(str(txt_path)) if txt_path.is_file() else warnings_from_header(read_round(str(bin_path))[0])
    write_round_txt(str(bin_path), warnings)
    return "patched"


def _init_pool(artifact: dict) -> None:
    global _artifact
    _artifact = artifact


def _worker(bin_str: str) -> tuple[str, str]:
    return bin_str, patch_bin(Path(bin_str))


def cmd_all(data_dir: Path, workers: int, dry_run: bool) -> None:
    global _artifact
    _artifact = load_delta_win_artifact()
    bin_paths = iter_round_bin_paths(data_dir)
    if not bin_paths:
        raise Exception(f"no .bin files under {data_dir}")
    stats = {"patched": 0, "present": 0, "would_patch": 0, "errors": 0}
    targets = bin_paths if not dry_run else bin_paths[:50]
    if dry_run:
        for bp in targets:
            try:
                stats[patch_bin(bp, dry_run=True)] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR {bp}: {e}", flush=True)
    elif workers == 1:
        for bp in bin_paths:
            try:
                stats[patch_bin(bp)] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR {bp}: {e}", flush=True)
    else:
        with Pool(workers, initializer=_init_pool, initargs=(_artifact,)) as pool:
            for bin_str, status in pool.imap_unordered(_worker, [str(p) for p in bin_paths], chunksize=32):
                if status == "patched":
                    stats["patched"] += 1
                elif status == "present":
                    stats["present"] += 1
                elif status == "would_patch":
                    stats["would_patch"] += 1
                else:
                    stats["errors"] += 1
                    print(f"ERROR {bin_str}: unexpected status {status}", flush=True)
    print(
        f"done: bins={len(bin_paths)} patched={stats['patched']} present={stats['present']} "
        f"would_patch={stats['would_patch']} errors={stats['errors']}",
        flush=True,
    )
    if stats["errors"]:
        raise Exception(f"backfill finished with {stats['errors']} errors")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    data_dir = _DATA_DIR
    workers = 8
    if len(args) == 1:
        workers = int(args[0]) if args[0].isdigit() else 8
        if not args[0].isdigit():
            data_dir = Path(args[0])
    elif len(args) == 2:
        data_dir = Path(args[0])
        workers = int(args[1])
    elif len(args) > 2:
        raise Exception("usage: backfill_real_delta_win.py [data_dir] [workers] [--dry-run]")
    if workers < 1:
        raise Exception(f"workers must be >= 1, got {workers}")
    if not data_dir.is_dir():
        raise Exception(f"data directory not found: {data_dir}")
    print(f"data_dir: {data_dir} workers: {workers} dry_run: {dry_run} header_cols: {format_column_header()}", flush=True)
    if not dry_run:
        run_delta_win_study()
    cmd_all(data_dir, workers, dry_run)


if __name__ == "__main__":
    main()
