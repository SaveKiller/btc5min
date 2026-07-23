import math
import re
import sys
from pathlib import Path

from src.binary_format import MAGIC, VERSION, read_round
from src.book import tick_quotes_missing
from src.clob_api import BET_USD, majority_side, market_buy_gain
from src.market import INTERVAL_SECS

# Settlement arrotonda ptb/final_price (price_decimals); i tick hanno chainlink grezzo.
# Sotto questa soglia non loggare: rumore di arrotondamento, non anomalia dati.
V19_DIAG_THRESHOLD_USD = 5.0


def _levels_sorted(levels, descending: bool) -> bool:
    if len(levels) < 2:
        return True
    for i in range(len(levels) - 1):
        if descending and levels[i][0] < levels[i + 1][0]:
            return False
        if not descending and levels[i][0] > levels[i + 1][0]:
            return False
    return True


def _quote_close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def verify_round(path: str) -> tuple[list[str], list[str]]:
    errors = []
    diagnostics = []
    p = Path(path)
    if not p.exists():
        return [f"V1: file not found: {path}"], []
    try:
        header, ticks, books = read_round(path)
    except Exception as e:
        return [f"V1: read failed: {e}"], []
    tick_count = header["tick_count"]
    if header["magic"] != MAGIC:
        errors.append(f"V2: bad magic {header['magic']}")
    if header["version"] != VERSION:
        errors.append(f"V2: bad version {header['version']}")
    if tick_count <= 0:
        errors.append("V3: tick_count must be > 0")
    m = re.search(r"_(\d+)_\d{4}\.bin$", p.name)
    if not m:
        errors.append(f"V4: cannot parse start_ts from filename {p.name}")
    elif int(m.group(1)) != header["market_start_ts"]:
        errors.append(f"V4: filename ts {m.group(1)} != header {header['market_start_ts']}")
    duration = header["market_end_ts"] - header["market_start_ts"]
    if duration not in INTERVAL_SECS.values():
        errors.append(f"V5: round duration {duration}s not in {sorted(INTERVAL_SECS.values())}")
    if tick_count > 1:
        secs = ticks[:, 1]
        for i in range(len(secs) - 1):
            if secs[i] + 0.5 < secs[i + 1]:
                errors.append(f"V6: secs_to_expiry not decreasing at tick {i}")
                break
    for i, row in enumerate(ticks):
        if tick_quotes_missing(row):
            continue
        for j in range(2, 6):
            if not (0.0 <= row[j] <= 1.0):
                errors.append(f"V7: price out of range tick {i} col {j}: {row[j]}")
                break
        if row[3] < row[2] or row[5] < row[4]:
            errors.append(f"V8: spread invalid tick {i}")
            break
    if header["ptb_chainlink"] <= 0:
        errors.append("V9: ptb_chainlink missing")
    if header["outcome"] not in (1, 2):
        errors.append(f"V10: outcome not set: {header['outcome']}")
    if header["final_chainlink"] <= 0:
        errors.append("V11: final_chainlink missing")
    if header.get("fee_rate", 0) <= 0:
        errors.append("V11b: fee_rate missing")
    if header["final_price"] <= 0:
        errors.append("V11c: final_price missing")
    if header["ptb_price"] <= 0:
        errors.append("V11d: ptb_price missing")
    if tick_count > 0 and duration in INTERVAL_SECS.values():
        first_min = duration - 5
        if ticks[0, 1] < first_min:
            errors.append(f"V12: first tick secs_to_expiry {ticks[0, 1]} < {first_min}")
        if ticks[-1, 1] > 10:
            errors.append(f"V12: last tick secs_to_expiry {ticks[-1, 1]} > 10")
    if tick_count > 0:
        diff_ptb = abs(header["ptb_price"] - ticks[0, 6])
        if diff_ptb > V19_DIAG_THRESHOLD_USD:
            diagnostics.append(
                f"V19a: ptb_price={header['ptb_price']} vs tick0={ticks[0, 6]:.4f} diff={diff_ptb:.2f}")
        diff_final = abs(header["final_price"] - ticks[-1, 6])
        if diff_final > V19_DIAG_THRESHOLD_USD:
            diagnostics.append(
                f"V19b: final_price={header['final_price']} vs tickN={ticks[-1, 6]:.4f} diff={diff_final:.2f}")
    for i, row in enumerate(ticks):
        if tick_quotes_missing(row):
            continue
        gain = row[7]
        if math.isnan(gain):
            continue
        if gain < -1.0:
            errors.append(f"V14: majority_gain {gain} < -1 at tick {i}")
            break
    if len(books) != tick_count:
        errors.append(f"V15: book_snapshots {len(books)} != tick_count {tick_count}")
    for i, (row, snap) in enumerate(zip(ticks, books)):
        if tick_quotes_missing(row):
            continue
        if snap.up_bids and not _quote_close(row[2], snap.up_bids[0][0]):
            errors.append(f"V16: up_bid mismatch tick {i}: {row[2]} vs {snap.up_bids[0][0]}")
            break
        if snap.up_asks and not _quote_close(row[3], snap.up_asks[0][0]):
            errors.append(f"V16: up_ask mismatch tick {i}: {row[3]} vs {snap.up_asks[0][0]}")
            break
        if snap.down_bids and not _quote_close(row[4], snap.down_bids[0][0]):
            errors.append(f"V16: down_bid mismatch tick {i}: {row[4]} vs {snap.down_bids[0][0]}")
            break
        if snap.down_asks and not _quote_close(row[5], snap.down_asks[0][0]):
            errors.append(f"V16: down_ask mismatch tick {i}: {row[5]} vs {snap.down_asks[0][0]}")
            break
        for side_name, levels in [("up_bids", snap.up_bids), ("up_asks", snap.up_asks),
                ("down_bids", snap.down_bids), ("down_asks", snap.down_asks)]:
            desc = side_name.endswith("bids")
            if not _levels_sorted(levels, desc):
                errors.append(f"V17: {side_name} not sorted at tick {i}")
                break
            for p, s in levels:
                if not (0.0 <= p <= 1.0):
                    errors.append(f"V17: {side_name} price out of range at tick {i}: {p}")
                    break
                if s < 0:
                    errors.append(f"V17: {side_name} negative size at tick {i}: {s}")
                    break
        else:
            continue
        break
    if not errors and tick_count > 0:
        checked = 0
        for idx in range(tick_count):
            row = ticks[idx]
            if tick_quotes_missing(row):
                continue
            snap = books[idx]
            side = majority_side(row[2], row[3], row[4], row[5])
            asks = snap.up_asks if side == "Up" else snap.down_asks
            quote = row[3] if side == "Up" else row[5]
            expected = market_buy_gain(asks, BET_USD, header["fee_rate"], quote_ask=quote)
            if not _quote_close(row[7], expected, tol=1e-4):
                errors.append(f"V18: gain mismatch tick {idx}: stored {row[7]} vs recomputed {expected}")
                break
            checked += 1
            if checked >= 2:
                break
    return errors, diagnostics


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception("usage: python -m src.verify <file.bin|directory>")
    target = Path(sys.argv[1])
    paths = sorted(target.rglob("*.bin")) if target.is_dir() else [target]
    if not paths:
        raise Exception(f"no .bin files in {target}")
    for path in paths:
        errs, diags = verify_round(str(path))
        if errs:
            print(f"FAIL {path}")
            for e in errs:
                print(f"  {e}")
        else:
            try:
                header, _, _ = read_round(str(path))
                notes = []
                if math.isnan(header["ptb_gamma"]):
                    notes.append("ptb_gamma pending")
                if math.isnan(header["final_gamma"]):
                    notes.append("final_gamma pending")
                suffix = f" ({', '.join(notes)})" if notes else ""
            except Exception:
                suffix = ""
            print(f"OK {path}{suffix}")
        for d in diags:
            print(f"  NOTE {d}")


if __name__ == "__main__":
    main()
