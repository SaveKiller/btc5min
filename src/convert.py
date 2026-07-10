import math
import os
import re
import sys
from pathlib import Path

from src.binary_format import OUTCOME_NAMES, read_round, txt_path_for_bin
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
    return render_round_txt(header, ticks, warnings)


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


def iter_round_bin_paths(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        raise Exception(f"data dir not found: {data_dir}")
    paths: list[Path] = []
    for day_dir in sorted(data_dir.iterdir()):
        if not day_dir.is_dir() or not _DATE_DIR.match(day_dir.name):
            continue
        bin_dir = day_dir / "bin"
        if not bin_dir.is_dir():
            continue
        paths.extend(sorted(bin_dir.glob("*.bin")))
    return paths


def convert_all_round_bins(data_dir: Path) -> None:
    bin_paths = iter_round_bin_paths(data_dir)
    if not bin_paths:
        raise Exception(f"no .bin files in {data_dir}/YYYY-MM-DD/bin")
    for bin_path in bin_paths:
        bp = str(bin_path)
        txt = txt_path_for_bin(bp)
        write_round_txt(bp, read_txt_warnings(str(txt)))
        print(f"written {txt}")


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
