#!/usr/bin/env python3
"""Rigenera tutti i .txt di un giorno da .bin (price_decimals)."""
import sys
from pathlib import Path

ROOT = Path("/opt/btc5min")
sys.path.insert(0, str(ROOT))

from src.binary_format import txt_path_for_bin
from src.convert import read_txt_warnings, write_round_txt

day = sys.argv[1] if len(sys.argv) > 1 else None
if not day:
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
bin_dir = ROOT / "data" / day / "bin"
n = 0
for bp in sorted(bin_dir.glob("*.bin")):
    write_round_txt(str(bp), read_txt_warnings(str(txt_path_for_bin(str(bp)))))
    n += 1
    if n % 50 == 0:
        print(f"... {n}", flush=True)
print(f"regenerated {n} txt for {day}")
