import math
import os
import re
import sys
from pathlib import Path

from src.binary_format import OUTCOME_NAMES, asset_from_bin_path, read_round, txt_path_for_bin
from src.settlement import outcome_from_prices
from src.txt_format import render_round_txt
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_txt_warnings(txt_path: str) -> list[str]:
    p = Path(txt_path)
    if not p.exists():
        return []
    warnings: list[str] = []
    in_warnings = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line == "  warnings:":
            in_warnings = True
            continue
        if in_warnings:
            if line.startswith("    - "):
                warnings.append(line[6:])
            else:
                break
    return warnings


def warnings_from_header(header: dict) -> list[str]:
    computed = outcome_from_prices(header["final_chainlink"], header["ptb_chainlink"])
    outcome_name = OUTCOME_NAMES[header["outcome"]]
    warnings: list[str] = []
    if math.isnan(header["final_gamma"]):
        warnings.append("outcome from chainlink provisional, not gamma")
    if math.isnan(header["ptb_gamma"]):
        warnings.append("ptb_gamma missing at write")
    if not math.isnan(header["final_gamma"]) and outcome_name != computed:
        warnings.append(f"outcome mismatch gamma={outcome_name} computed={computed}")
    return warnings


def convert_round(bin_path: str, warnings: list[str]) -> str:
    header, ticks, _ = read_round(bin_path)
    return render_round_txt(header, ticks, warnings, asset=asset_from_bin_path(bin_path))


def align_txt_mtime_to_bin(bin_path: Path, txt_path: Path) -> None:
    """Il .txt locale deve riflettere il mtime del .bin (scrittura server o sync tar)."""
    bin_mtime = bin_path.stat().st_mtime
    os.utime(txt_path, (bin_mtime, bin_mtime))


def write_round_txt(bin_path: str, warnings: list[str]) -> None:
    bp = Path(bin_path)
    txt_path = txt_path_for_bin(bin_path)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(convert_round(bin_path, warnings), encoding="utf-8")
    align_txt_mtime_to_bin(bp, txt_path)


def iter_day_dirs(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        raise Exception(f"data dir not found: {data_dir}")
    out: list[Path] = []
    for day_dir in sorted(data_dir.iterdir()):
        if not day_dir.is_dir() or not _DATE_DIR.match(day_dir.name):
            continue
        bin_dir = day_dir / "bin"
        if bin_dir.is_dir() and any(bin_dir.glob("*.bin")):
            out.append(day_dir)
    return out


def iter_round_bin_paths(data_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for day_dir in iter_day_dirs(data_dir):
        paths.extend(sorted((day_dir / "bin").glob("*.bin")))
    return paths


def convert_day_bins(day_dir: Path) -> tuple[str, int]:
    bin_dir = day_dir / "bin"
    count = 0
    for bin_path in sorted(bin_dir.glob("*.bin")):
        bp = str(bin_path)
        write_round_txt(bp, read_txt_warnings(str(txt_path_for_bin(bp))))
        count += 1
    return day_dir.name, count


def _convert_day_worker(day_dir_str: str) -> tuple[str, int]:
    return convert_day_bins(Path(day_dir_str))


def convert_all_round_bins(data_dir: Path) -> None:
    day_dirs = iter_day_dirs(data_dir)
    if not day_dirs:
        raise Exception(f"no .bin files in {data_dir}/YYYY-MM-DD/bin")
    workers = len(day_dirs)
    if workers == 1:
        name, count = convert_day_bins(day_dirs[0])
        print(f"{name}: {count} files", flush=True)
        print(f"Convertiti {count} file in 1 giornata.")
        return
    from multiprocessing import Pool
    print(f"parallel convert: {workers} workers (1 per day)", flush=True)
    with Pool(workers) as pool:
        results = pool.map(_convert_day_worker, [str(d) for d in day_dirs])
    total = 0
    for name, count in sorted(results):
        print(f"{name}: {count} files", flush=True)
        total += count
    print(f"Convertiti {total} file in {len(day_dirs)} giornate.")


def convert_sync_bins(data_dir: Path) -> None:
    bin_paths = iter_round_bin_paths(data_dir)
    converted = 0
    for bin_path in bin_paths:
        bp = str(bin_path)
        txt = txt_path_for_bin(bp)
        if txt.exists() and txt.stat().st_mtime >= bin_path.stat().st_mtime:
            if txt.stat().st_mtime != bin_path.stat().st_mtime:
                align_txt_mtime_to_bin(bin_path, txt)
            continue
        header, _, _ = read_round(bp)
        write_round_txt(bp, warnings_from_header(header))
        print(f"written {txt}")
        converted += 1
    if converted == 0:
        print("Nessun bin da convertire.")
    else:
        print(f"Convertiti {converted} file.")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--sync":
        convert_sync_bins(_DATA_DIR)
        return
    if len(sys.argv) < 2:
        convert_all_round_bins(_DATA_DIR)
        return
    target = Path(sys.argv[1])
    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]
    if target.is_dir():
        for bin_path in sorted(target.rglob("*.bin")):
            bp = str(bin_path)
            txt = txt_path_for_bin(bp)
            write_round_txt(bp, read_txt_warnings(str(txt)))
            print(f"written {txt}")
    else:
        bp = str(target)
        warnings = read_txt_warnings(str(txt_path_for_bin(bp)))
        text = convert_round(bp, warnings)
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
            print(f"written {out_path}")
        else:
            print(text, end="")


if __name__ == "__main__":
    main()
