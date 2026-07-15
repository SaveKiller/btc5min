"""Indice round anti-spoiler, merge bin+txt, candele 5m."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dashv2.txt_rows import parse_txt_data_rows, txt_path_for_bin_path
from src.binary_format import OUTCOME_NAMES, read_round
from src.book import BookSnapshot
from src.clob_api import majority_side


def sec_from_secs_to_expiry(secs_to_expiry: float) -> int:
    return int(math.floor(secs_to_expiry + 0.5))


def _is_nan(v: float) -> bool:
    return math.isnan(v)


def _utc_label(market_start_ts: int) -> str:
    dt = datetime.fromtimestamp(market_start_ts, tz=timezone.utc)
    return dt.strftime("%d/%m/%Y | %H:%M:%S")


def _day_key(market_start_ts: int) -> str:
    return datetime.fromtimestamp(market_start_ts, tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass
class RoundIndexEntry:
    market_start_ts: int
    label: str
    day_utc: str
    valid: bool
    reason: str | None


@dataclass
class LoadedRound:
    market_start_ts: int
    market_end_ts: int
    fee_rate: float
    ptb_chainlink: float
    outcome_code: int
    outcome_name: str
    final_chainlink: float
    ticks_by_sec: dict[int, dict]
    books_by_sec: dict[int, BookSnapshot]
    all_secs: set[int]


class RoundRepository:
    def __init__(self, data_dir: Path, stall_reconnect_sec: float) -> None:
        self.data_dir = data_dir
        self.stall_reconnect_sec = stall_reconnect_sec
        self._bins: dict[int, Path] = {}
        self._index: list[RoundIndexEntry] = []
        self._scan()

    def _scan(self) -> None:
        self._bins.clear()
        entries: list[RoundIndexEntry] = []
        for bin_path in sorted(self.data_dir.glob("**/bin/btc5m_*.bin"), key=lambda p: p.stat().st_mtime, reverse=True):
            parts = bin_path.stem.split("_")
            if len(parts) < 3:
                continue
            market_start_ts = int(parts[1])
            if market_start_ts in self._bins:
                continue
            self._bins[market_start_ts] = bin_path
            txt_path = txt_path_for_bin_path(bin_path)
            valid = txt_path.is_file()
            reason = None if valid else "missing txt pair"
            entries.append(RoundIndexEntry(
                market_start_ts=market_start_ts, label=_utc_label(market_start_ts),
                day_utc=_day_key(market_start_ts), valid=valid, reason=reason))
        self._index = entries

    def list_days(self) -> list[dict]:
        counts: dict[str, int] = {}
        for e in self._index:
            counts[e.day_utc] = counts.get(e.day_utc, 0) + 1
        return [{"day_utc": d, "count": counts[d]} for d in sorted(counts.keys(), reverse=True)]

    def list_nav_ts(self) -> list[int]:
        return sorted(e.market_start_ts for e in self._index if e.valid)

    def list_picker_day(self, day_utc: str) -> list[dict]:
        return [
            {"market_start_ts": e.market_start_ts, "label": e.label, "valid": e.valid, "reason": e.reason}
            for e in self._index if e.day_utc == day_utc
        ]

    def list_picker(self) -> list[dict]:
        return [{"market_start_ts": e.market_start_ts, "label": e.label, "day_utc": e.day_utc, "valid": e.valid, "reason": e.reason} for e in self._index]

    def load(self, market_start_ts: int) -> LoadedRound:
        entry = next((e for e in self._index if e.market_start_ts == market_start_ts), None)
        if entry is None: raise Exception(f"round not in index: {market_start_ts}")
        if not entry.valid: raise Exception(f"round invalid: {entry.reason}")
        bin_path = self._bins[market_start_ts]
        txt_path = txt_path_for_bin_path(bin_path)
        header, ticks, books = read_round(str(bin_path))
        txt_rows = parse_txt_data_rows(txt_path)
        ptb = float(header["ptb_chainlink"])
        fee_rate = float(header["fee_rate"])
        by_sec: dict[int, dict] = {}
        books_by_sec: dict[int, BookSnapshot] = {}
        all_secs: set[int] = set(range(1, 301))
        for i, row in enumerate(ticks):
            sec = sec_from_secs_to_expiry(float(row[1]))
            if sec not in txt_rows:
                raise Exception(f"txt missing sec {sec} for market_start_ts={market_start_ts}")
            recv_ts_ms = int(row[0])
            chainlink_recv_ms = int(row[8])
            chainlink_btc = float(row[6])
            up_bid, up_ask = float(row[2]), float(row[3])
            down_bid, down_ask = float(row[4]), float(row[5])
            partial = _is_nan(up_bid) or _is_nan(up_ask) or _is_nan(down_bid) or _is_nan(down_ask)
            stale = (recv_ts_ms - chainlink_recv_ms) > (self.stall_reconnect_sec * 1000)
            delta_usd = None if stale else int(round(chainlink_btc - ptb))
            up_mid_c = down_mid_c = None
            maj = None
            gap = False
            if not partial:
                up_mid_c = int(round(((up_bid + up_ask) / 2) * 100))
                down_mid_c = int(round(((down_bid + down_ask) / 2) * 100))
                maj = majority_side(up_bid, up_ask, down_bid, down_ask)
            else:
                gap = True
            txt = txt_rows[sec]
            by_sec[sec] = {
                "sec": sec, "recv_ts_ms": recv_ts_ms, "chainlink_btc": None if stale else chainlink_btc,
                "chainlink_stale": stale, "up_bid": None if partial else up_bid, "up_ask": None if partial else up_ask,
                "down_bid": None if partial else down_bid, "down_ask": None if partial else down_ask,
                "delta_usd": delta_usd, "partial": partial, "gap": gap,
                "up_mid_c": up_mid_c, "down_mid_c": down_mid_c, "majority_side": maj,
                "vol": txt["vol"], "rq": txt["rq"], "rs": txt["rs"],
                "dwin_a": txt["dwin_a"], "dwin_b_pct": txt["dwin_b_pct"],
            }
            books_by_sec[sec] = books[i]
        return LoadedRound(
            market_start_ts=int(header["market_start_ts"]), market_end_ts=int(header["market_end_ts"]),
            fee_rate=fee_rate, ptb_chainlink=ptb, outcome_code=int(header["outcome"]),
            outcome_name=OUTCOME_NAMES[int(header["outcome"])], final_chainlink=float(header["final_chainlink"]),
            ticks_by_sec=by_sec, books_by_sec=books_by_sec, all_secs=all_secs)

    def previous_candles(self, market_start_ts: int, count: int) -> list[dict]:
        """Candele 5m precedenti più vicine; buchi temporali restano buchi (nessun fill)."""
        slots = [market_start_ts - 300 * (i + 1) for i in range(count)]
        candles: list[dict] = []
        for start_ts in sorted(slots):
            if start_ts not in self._bins: continue
            try:
                header, ticks, _ = read_round(str(self._bins[start_ts]))
                prices = [float(row[6]) for row in ticks if not _is_nan(float(row[6]))]
                if not prices: continue
                candles.append({
                    "time": int(header["market_start_ts"]), "open": prices[0],
                    "high": max(prices), "low": min(prices), "close": prices[-1],
                })
            except Exception:
                continue
        return candles

    def current_candle(self, loaded: LoadedRound, sec: int) -> dict:
        """Candela del round corrente solo con tick già raggiunti (sec >= replay sec)."""
        prices = [
            t["chainlink_btc"] for s, t in loaded.ticks_by_sec.items()
            if s >= sec and t["chainlink_btc"] is not None and not t["chainlink_stale"]
        ]
        if not prices:
            open_p = loaded.ptb_chainlink
            return {"time": loaded.market_start_ts, "open": open_p, "high": open_p, "low": open_p, "close": open_p}
        return {
            "time": loaded.market_start_ts, "open": loaded.ptb_chainlink,
            "high": max(prices + [loaded.ptb_chainlink]), "low": min(prices + [loaded.ptb_chainlink]),
            "close": prices[-1],
        }
