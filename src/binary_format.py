import struct
import numpy as np
from pathlib import Path

MAGIC = b"BTC5"
VERSION = 2
HEADER_FMT = "<4sHII d B x d I 28x"
RECORD_FMT = "<Q f 6f"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
RECORD_SIZE = struct.calcsize(RECORD_FMT)
OUTCOME_NAMES = {0: "unknown", 1: "Up", 2: "Down"}
OUTCOME_FROM_NAME = {"Up": 1, "Down": 2}


def write_round(path: str, header: dict, ticks: np.ndarray) -> None:
    if ticks.ndim != 2 or ticks.shape[1] != 8:
        raise Exception(f"ticks must be shape (N, 8), got {ticks.shape}")
    tick_count = ticks.shape[0]
    with open(path, "wb") as f:
        f.write(struct.pack(
            HEADER_FMT, MAGIC, VERSION, header["market_start_ts"], header["market_end_ts"],
            header["price_to_beat"], header["outcome"], header["final_chainlink"], tick_count))
        for row in ticks:
            f.write(struct.pack(RECORD_FMT, int(row[0]), float(row[1]), float(row[2]), float(row[3]),
                float(row[4]), float(row[5]), float(row[6]), float(row[7])))


def read_round(path: str) -> tuple[dict, np.ndarray]:
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < HEADER_SIZE:
        raise Exception(f"file too small: {len(raw)} bytes")
    magic, version, market_start_ts, market_end_ts, price_to_beat, outcome, final_chainlink, tick_count = struct.unpack(
        HEADER_FMT, raw[:HEADER_SIZE])
    if version != VERSION:
        raise Exception(f"unsupported version {version}, expected {VERSION}")
    expected = HEADER_SIZE + tick_count * RECORD_SIZE
    if len(raw) != expected:
        raise Exception(f"file size mismatch: {len(raw)} != {expected}")
    ticks = np.zeros((tick_count, 8), dtype=np.float64)
    offset = HEADER_SIZE
    for i in range(tick_count):
        recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, gain = struct.unpack(
            RECORD_FMT, raw[offset:offset + RECORD_SIZE])
        ticks[i] = [recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, gain]
        offset += RECORD_SIZE
    header = {
        "magic": magic, "version": version, "market_start_ts": market_start_ts,
        "market_end_ts": market_end_ts, "price_to_beat": price_to_beat, "outcome": outcome,
        "final_chainlink": final_chainlink, "tick_count": tick_count,
    }
    return header, ticks


def round_filename(asset: str, interval: str, market_start_ts: int) -> str:
    return f"{asset}{interval}_{market_start_ts}.bin"


def warn_path(bin_path: str) -> str:
    return str(Path(bin_path).with_suffix(".warn"))


def write_warnings(bin_path: str, warnings: list[str]) -> None:
    path = Path(warn_path(bin_path))
    if warnings:
        path.write_text("\n".join(warnings) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def read_warnings(bin_path: str) -> list[str]:
    path = Path(warn_path(bin_path))
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]
