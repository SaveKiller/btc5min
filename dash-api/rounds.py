from __future__ import annotations

import math
from pathlib import Path

from config import DATA_DIR
from protocol import RoundHeader
from src.binary_format import OUTCOME_NAMES, read_round


def _is_nan(v: float) -> bool:
    return math.isnan(v)


def sec_from_secs_to_expiry(secs_to_expiry: float) -> int:
    return int(math.floor(secs_to_expiry + 0.5))


def find_bin_path(market_start_ts: int) -> Path:
    matches = list(DATA_DIR.glob(f"**/bin/btc5m_{market_start_ts}_*.bin"))
    if not matches:
        raise Exception(f"round not found: market_start_ts={market_start_ts}")
    if len(matches) > 1:
        raise Exception(f"ambiguous round paths for market_start_ts={market_start_ts}: {matches}")
    return matches[0]


def list_rounds(limit: int) -> list[dict]:
    bins = sorted(DATA_DIR.glob("**/bin/btc5m_*.bin"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict] = []
    for path in bins[:limit]:
        header, _, _ = read_round(str(path))
        out.append({
            "market_start_ts": int(header["market_start_ts"]),
            "market_end_ts": int(header["market_end_ts"]),
            "outcome": OUTCOME_NAMES[int(header["outcome"])],
            "tick_count": int(header["tick_count"]),
            "bin_path": str(path.relative_to(DATA_DIR.parent)),
        })
    return out


def load_round_header(market_start_ts: int) -> RoundHeader:
    header, _, _ = read_round(str(find_bin_path(market_start_ts)))
    return RoundHeader(
        market_start_ts=int(header["market_start_ts"]),
        market_end_ts=int(header["market_end_ts"]),
        outcome=OUTCOME_NAMES[int(header["outcome"])],
        tick_count=int(header["tick_count"]),
        ptb_chainlink=float(header["ptb_chainlink"]),
        ptb_gamma=None if _is_nan(header["ptb_gamma"]) else float(header["ptb_gamma"]),
        final_chainlink=float(header["final_chainlink"]),
        final_gamma=None if _is_nan(header["final_gamma"]) else float(header["final_gamma"]),
    )


def load_ticks_by_sec(market_start_ts: int, stall_reconnect_sec: float) -> tuple[RoundHeader, dict[int, dict]]:
    header, ticks, _ = read_round(str(find_bin_path(market_start_ts)))
    ptb = float(header["ptb_chainlink"])
    by_sec: dict[int, dict] = {}
    for row in ticks:
        sec = sec_from_secs_to_expiry(float(row[1]))
        recv_ts_ms = int(row[0])
        chainlink_recv_ms = int(row[8])
        chainlink_btc = float(row[6])
        up_bid, up_ask = float(row[2]), float(row[3])
        down_bid, down_ask = float(row[4]), float(row[5])
        gain = float(row[7])
        partial = _is_nan(up_bid) or _is_nan(up_ask) or _is_nan(down_bid) or _is_nan(down_ask)
        stale = (recv_ts_ms - chainlink_recv_ms) > (stall_reconnect_sec * 1000)
        delta_usd = None if stale else int(round(chainlink_btc - ptb))
        by_sec[sec] = {
            "recv_ts_ms": recv_ts_ms,
            "chainlink_btc": None if stale else chainlink_btc,
            "chainlink_stale": stale,
            "up_bid": None if partial else up_bid,
            "up_ask": None if partial else up_ask,
            "down_bid": None if partial else down_bid,
            "down_ask": None if partial else down_ask,
            "delta_usd": delta_usd,
            "majority_gain": None if partial or _is_nan(gain) else gain,
            "partial": partial,
        }
    rh = RoundHeader(
        market_start_ts=int(header["market_start_ts"]),
        market_end_ts=int(header["market_end_ts"]),
        outcome=OUTCOME_NAMES[int(header["outcome"])],
        tick_count=int(header["tick_count"]),
        ptb_chainlink=ptb,
        ptb_gamma=None if _is_nan(header["ptb_gamma"]) else float(header["ptb_gamma"]),
        final_chainlink=float(header["final_chainlink"]),
        final_gamma=None if _is_nan(header["final_gamma"]) else float(header["final_gamma"]),
    )
    return rh, by_sec
