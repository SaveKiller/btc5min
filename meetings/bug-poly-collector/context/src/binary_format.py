import struct
import numpy as np
from pathlib import Path

from src.book import BookSnapshot

MAGIC = b"BTC5"
VERSION = 3
HEADER_FMT = "<4sHII d B x d I d 20x"
RECORD_FMT = "<Q f 6f"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
RECORD_SIZE = struct.calcsize(RECORD_FMT)
OUTCOME_NAMES = {0: "unknown", 1: "Up", 2: "Down"}
OUTCOME_FROM_NAME = {"Up": 1, "Down": 2}


def _pack_header(header: dict) -> bytes:
    return struct.pack(
        HEADER_FMT, MAGIC, VERSION, header["market_start_ts"], header["market_end_ts"],
        header["price_to_beat"], header["outcome"], header["final_chainlink"],
        header["tick_count"], header["fee_rate"])


def _unpack_header(raw: bytes) -> dict:
    if len(raw) < HEADER_SIZE:
        raise Exception(f"file too small: {len(raw)} bytes")
    magic, version, market_start_ts, market_end_ts, price_to_beat, outcome, final_chainlink, tick_count, fee_rate = struct.unpack(
        HEADER_FMT, raw[:HEADER_SIZE])
    if version != VERSION:
        raise Exception(f"unsupported version {version}, expected {VERSION}")
    return {
        "magic": magic, "version": version, "market_start_ts": market_start_ts,
        "market_end_ts": market_end_ts, "price_to_beat": price_to_beat, "outcome": outcome,
        "final_chainlink": final_chainlink, "tick_count": tick_count, "fee_rate": fee_rate,
    }


def write_round(path: str, header: dict, ticks: np.ndarray, book_snapshots: list[BookSnapshot]) -> None:
    if ticks.ndim != 2 or ticks.shape[1] != 8:
        raise Exception(f"ticks must be shape (N, 8), got {ticks.shape}")
    tick_count = ticks.shape[0]
    if tick_count != len(book_snapshots):
        raise Exception(f"ticks/book_snapshots length mismatch: {tick_count} vs {len(book_snapshots)}")
    if tick_count != header["tick_count"]:
        raise Exception(f"ticks/header tick_count mismatch: {tick_count} vs {header['tick_count']}")
    with open(path, "wb") as f:
        f.write(_pack_header(header))
        for i, row in enumerate(ticks):
            f.write(struct.pack(RECORD_FMT, int(row[0]), float(row[1]), float(row[2]), float(row[3]),
                float(row[4]), float(row[5]), float(row[6]), float(row[7])))
            f.write(book_snapshots[i].to_bytes())


def read_round(path: str) -> tuple[dict, np.ndarray, list[BookSnapshot]]:
    raw = Path(path).read_bytes()
    header = _unpack_header(raw)
    tick_count = header["tick_count"]
    ticks = np.zeros((tick_count, 8), dtype=np.float64)
    book_snapshots: list[BookSnapshot] = []
    offset = HEADER_SIZE
    for i in range(tick_count):
        if offset + RECORD_SIZE > len(raw):
            raise Exception(f"truncated at tick {i} record")
        recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, gain = struct.unpack(
            RECORD_FMT, raw[offset:offset + RECORD_SIZE])
        ticks[i] = [recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, gain]
        offset += RECORD_SIZE
        snap, offset = BookSnapshot.from_bytes(raw, offset)
        book_snapshots.append(snap)
    if offset != len(raw):
        raise Exception(f"file size mismatch: parsed {offset} bytes, file has {len(raw)}")
    return header, ticks, book_snapshots


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
