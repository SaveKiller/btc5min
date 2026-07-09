import struct
from datetime import datetime, timezone

import numpy as np
from pathlib import Path

from src.book import BookSnapshot

MAGIC = b"BTC5"
VERSION = 6
HEADER_FMT = "<4sHII B x I d d d d d d d"
OFFSET_PTB_GAMMA = 44
OFFSET_FINAL_GAMMA = 68
HEADER_SIZE = struct.calcsize(HEADER_FMT)
RECORD_FMT = "<Q f 6f Q"
RECORD_SIZE = struct.calcsize(RECORD_FMT)
OUTCOME_NAMES = {0: "unknown", 1: "Up", 2: "Down"}
OUTCOME_FROM_NAME = {"Up": 1, "Down": 2}


def _pack_header(header: dict) -> bytes:
    return struct.pack(
        HEADER_FMT, MAGIC, VERSION, header["market_start_ts"], header["market_end_ts"],
        header["outcome"], header["tick_count"], header["fee_rate"],
        header["ptb_price"], header["ptb_chainlink"], header["ptb_gamma"],
        header["final_price"], header["final_chainlink"], header["final_gamma"])


def _unpack_header(raw: bytes) -> dict:
    if len(raw) < HEADER_SIZE:
        raise Exception(f"file too small: {len(raw)} bytes")
    (magic, version, market_start_ts, market_end_ts, outcome, tick_count, fee_rate,
        ptb_price, ptb_chainlink, ptb_gamma, final_price, final_chainlink, final_gamma) = struct.unpack(
        HEADER_FMT, raw[:HEADER_SIZE])
    if version != VERSION:
        raise Exception(f"unsupported version {version}, expected {VERSION}")
    return {
        "magic": magic, "version": version, "market_start_ts": market_start_ts,
        "market_end_ts": market_end_ts, "outcome": outcome, "tick_count": tick_count,
        "fee_rate": fee_rate, "ptb_price": ptb_price, "ptb_chainlink": ptb_chainlink,
        "ptb_gamma": ptb_gamma, "final_price": final_price, "final_chainlink": final_chainlink,
        "final_gamma": final_gamma,
    }


def _patch_header_double(bin_path: str, offset: int, value: float) -> None:
    with open(bin_path, "r+b") as f:
        f.seek(offset)
        f.write(struct.pack("<d", value))


def patch_ptb_gamma(bin_path: str, value: float) -> None:
    _patch_header_double(bin_path, OFFSET_PTB_GAMMA, value)


def patch_final_gamma(bin_path: str, value: float) -> None:
    _patch_header_double(bin_path, OFFSET_FINAL_GAMMA, value)


def write_round(path: str, header: dict, ticks: np.ndarray, book_snapshots: list[BookSnapshot]) -> None:
    if ticks.ndim != 2 or ticks.shape[1] != 9:
        raise Exception(f"ticks must be shape (N, 9), got {ticks.shape}")
    tick_count = ticks.shape[0]
    if tick_count != len(book_snapshots):
        raise Exception(f"ticks/book_snapshots length mismatch: {tick_count} vs {len(book_snapshots)}")
    if tick_count != header["tick_count"]:
        raise Exception(f"ticks/header tick_count mismatch: {tick_count} vs {header['tick_count']}")
    with open(path, "wb") as f:
        f.write(_pack_header(header))
        for i, row in enumerate(ticks):
            f.write(struct.pack(RECORD_FMT, int(row[0]), float(row[1]), float(row[2]), float(row[3]),
                float(row[4]), float(row[5]), float(row[6]), float(row[7]), int(row[8])))
            f.write(book_snapshots[i].to_bytes())


def read_round(path: str) -> tuple[dict, np.ndarray, list[BookSnapshot]]:
    raw = Path(path).read_bytes()
    header = _unpack_header(raw)
    tick_count = header["tick_count"]
    ticks = np.zeros((tick_count, 9), dtype=np.float64)
    book_snapshots: list[BookSnapshot] = []
    offset = HEADER_SIZE
    for i in range(tick_count):
        if offset + RECORD_SIZE > len(raw):
            raise Exception(f"truncated at tick {i} record")
        (recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, gain,
            chainlink_recv_ms) = struct.unpack(RECORD_FMT, raw[offset:offset + RECORD_SIZE])
        ticks[i] = [recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, gain,
            chainlink_recv_ms]
        offset += RECORD_SIZE
        snap, offset = BookSnapshot.from_bytes(raw, offset)
        book_snapshots.append(snap)
    if offset != len(raw):
        raise Exception(f"file size mismatch: parsed {offset} bytes, file has {len(raw)}")
    return header, ticks, book_snapshots


def _round_day_hhmm(market_start_ts: int) -> tuple[str, str]:
    dt = datetime.fromtimestamp(market_start_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H%M")


def round_basename(asset: str, interval: str, market_start_ts: int) -> str:
    _, hhmm = _round_day_hhmm(market_start_ts)
    return f"{asset}{interval}_{market_start_ts}_{hhmm}"


def round_bin_path(out_dir: Path, asset: str, interval: str, market_start_ts: int) -> Path:
    day, _ = _round_day_hhmm(market_start_ts)
    d = out_dir / day / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{round_basename(asset, interval, market_start_ts)}.bin"


def txt_path_for_bin(bin_path: str) -> Path:
    p = Path(bin_path)
    return p.parent.parent / "txt" / p.with_suffix(".txt").name
