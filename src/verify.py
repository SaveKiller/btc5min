import re
import sys
from pathlib import Path

import numpy as np

from src.binary_format import read_round, RECORD_SIZE, HEADER_SIZE, MAGIC, VERSION


def verify_round(path: str) -> list[str]:
    errors = []
    p = Path(path)
    if not p.exists():
        return [f"V1: file not found: {path}"]
    raw = p.read_bytes()
    try:
        header, ticks = read_round(path)
    except Exception as e:
        return [f"V1: read failed: {e}"]
    tick_count = header["tick_count"]
    if len(raw) != HEADER_SIZE + tick_count * RECORD_SIZE:
        errors.append(f"V1: size {len(raw)} != {HEADER_SIZE + tick_count * RECORD_SIZE}")
    if header["magic"] != MAGIC:
        errors.append(f"V2: bad magic {header['magic']}")
    if header["version"] != VERSION:
        errors.append(f"V2: bad version {header['version']}")
    if tick_count <= 0:
        errors.append("V3: tick_count must be > 0")
    m = re.search(r"_(\d+)\.bin$", p.name)
    if not m:
        errors.append(f"V4: cannot parse start_ts from filename {p.name}")
    elif int(m.group(1)) != header["market_start_ts"]:
        errors.append(f"V4: filename ts {m.group(1)} != header {header['market_start_ts']}")
    if header["market_end_ts"] - header["market_start_ts"] != 300:
        errors.append(f"V5: round duration != 300s")
    if tick_count > 1:
        secs = ticks[:, 1]
        for i in range(len(secs) - 1):
            if secs[i] + 0.5 < secs[i + 1]:
                errors.append(f"V6: secs_to_expiry not decreasing at tick {i}")
                break
    for i, row in enumerate(ticks):
        for j in range(2, 6):
            if not (0.0 <= row[j] <= 1.0):
                errors.append(f"V7: price out of range tick {i} col {j}: {row[j]}")
                break
        if row[3] < row[2] or row[5] < row[4]:
            errors.append(f"V8: spread invalid tick {i}")
            break
    if header["price_to_beat"] <= 0:
        errors.append("V9: price_to_beat missing")
    if header["outcome"] not in (1, 2):
        errors.append(f"V10: outcome not set: {header['outcome']}")
    if header["final_chainlink"] <= 0:
        errors.append("V11: final_chainlink missing")
    if tick_count > 0:
        if ticks[0, 1] < 295:
            errors.append(f"V12: first tick secs_to_expiry {ticks[0, 1]} < 295")
        if ticks[-1, 1] > 10:
            errors.append(f"V12: last tick secs_to_expiry {ticks[-1, 1]} > 10")
    expected_up = 1 if header["final_chainlink"] >= header["price_to_beat"] else 2
    if header["outcome"] != expected_up:
        errors.append(f"V13: outcome {header['outcome']} != expected {expected_up}")
    for i, row in enumerate(ticks):
        gain = row[7]
        if gain < -1.0:
            errors.append(f"V14: majority_gain {gain} < -1 at tick {i}")
            break
    return errors


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception("usage: python -m src.verify <file.bin|directory>")
    target = Path(sys.argv[1])
    paths = sorted(target.glob("*.bin")) if target.is_dir() else [target]
    if not paths:
        raise Exception(f"no .bin files in {target}")
    for path in paths:
        errs = verify_round(str(path))
        if errs:
            print(f"FAIL {path}")
            for e in errs:
                print(f"  {e}")
        else:
            print(f"OK {path}")


if __name__ == "__main__":
    main()
