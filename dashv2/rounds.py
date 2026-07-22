"""Indice round anti-spoiler, merge bin+txt, candele 5m."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashv2.txt_rows import parse_txt_data_rows, txt_path_for_bin_path
from src.binary_format import OUTCOME_NAMES, read_round
from src.round_index import load_or_build_index
from src.book import BookSnapshot
from src.clob_api import majority_side
from src.risk import compute_side_risks


def sec_from_secs_to_expiry(secs_to_expiry: float) -> int:
    return int(math.floor(secs_to_expiry + 0.5))


def _is_nan(v: float) -> bool:
    return math.isnan(v)


def _utc_label(market_start_ts: int) -> str:
    dt = datetime.fromtimestamp(market_start_ts, tz=timezone.utc)
    return dt.strftime("%d/%m/%Y | %H:%M:%S")


def _day_key(market_start_ts: int) -> str:
    return datetime.fromtimestamp(market_start_ts, tz=timezone.utc).strftime("%Y-%m-%d")


ROUND_STEP_SEC = 300
SLOTS_PER_DAY = 24 * 12  # 288 round da 5m in un giorno UTC


def _day_start_ts(day_utc: str) -> int:
    return int(datetime.strptime(day_utc, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def _iter_calendar_days(day_from: str, day_to: str):
    """Giorni UTC inclusivi da day_from a day_to (YYYY-MM-DD)."""
    cur = datetime.strptime(day_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(day_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    while cur <= end:
        yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


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
        self._ohlc_cache: dict[int, dict | None] = {}
        self._scan()

    def _scan(self) -> None:
        self._bins.clear()
        self._ohlc_cache.clear()
        raw = load_or_build_index(self.data_dir)
        entries: list[RoundIndexEntry] = []
        for market_start_ts in sorted(raw):
            entry = raw[market_start_ts]
            bin_path = self.data_dir / entry["bin"]
            self._bins[market_start_ts] = bin_path
            entries.append(RoundIndexEntry(
                market_start_ts=market_start_ts, label=_utc_label(market_start_ts),
                day_utc=_day_key(market_start_ts), valid=bool(entry["valid"]),
                reason=entry.get("reason")))
        self._index = entries

    def list_days(self) -> list[dict]:
        counts: dict[str, int] = {}
        for e in self._index:
            counts[e.day_utc] = counts.get(e.day_utc, 0) + 1
        if not counts:
            return []
        days = []
        for d in _iter_calendar_days(min(counts), max(counts)):
            n = counts.get(d, 0)
            days.append({"day_utc": d, "count": n, "valid": n > 0})
        days.reverse()
        return days

    def list_nav_ts(self) -> list[int]:
        return sorted(e.market_start_ts for e in self._index if e.valid)

    def list_picker_day(self, day_utc: str) -> list[dict]:
        """Tutti i 288 slot 5m del giorno UTC; assenti → valid=False, present=False."""
        by_ts = {e.market_start_ts: e for e in self._index if e.day_utc == day_utc}
        start = _day_start_ts(day_utc)
        out = []
        for i in range(SLOTS_PER_DAY):
            ts = start + i * ROUND_STEP_SEC
            e = by_ts.get(ts)
            if e is None:
                out.append({
                    "market_start_ts": ts, "label": _utc_label(ts),
                    "valid": False, "present": False, "reason": "missing round",
                })
            else:
                out.append({
                    "market_start_ts": e.market_start_ts, "label": e.label,
                    "valid": e.valid, "present": True, "reason": e.reason,
                })
        return out

    def list_picker(self) -> list[dict]:
        return [{"market_start_ts": e.market_start_ts, "label": e.label, "day_utc": e.day_utc, "valid": e.valid, "reason": e.reason} for e in self._index]

    def bin_path(self, market_start_ts: int) -> Path:
        return self._bins[market_start_ts]

    def load(self, market_start_ts: int) -> LoadedRound:
        entry = next((e for e in self._index if e.market_start_ts == market_start_ts), None)
        if entry is None: raise Exception(f"round not in index: {market_start_ts}")
        if not entry.valid: raise Exception(f"round invalid: {entry.reason}")
        return load_bin(self._bins[market_start_ts], self.stall_reconnect_sec)

    def _candle_ohlc(self, start_ts: int) -> dict | None:
        if start_ts in self._ohlc_cache:
            return self._ohlc_cache[start_ts]
        try:
            header, ticks, _ = read_round(str(self._bins[start_ts]))
            prices = [float(row[6]) for row in ticks if not _is_nan(float(row[6]))]
            candle = None if not prices else {
                "time": int(header["market_start_ts"]), "open": prices[0],
                "high": max(prices), "low": min(prices), "close": prices[-1],
            }
        except Exception:
            candle = None
        self._ohlc_cache[start_ts] = candle
        return candle

    def candles(self, before_ts: int | None) -> list[dict]:
        """Tutte le candele disponibili (cache OHLC); se before_ts, solo time < before_ts."""
        times = sorted(ts for ts in self._bins if before_ts is None or ts < before_ts)
        return [c for ts in times if (c := self._candle_ohlc(ts))]

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


def load_bin(bin_path: Path | str, stall_reconnect_sec: float) -> LoadedRound:
    """Carica un round da path .bin (+ .txt), senza scan dell'intero data_dir."""
    bin_path = Path(bin_path)
    txt_path = txt_path_for_bin_path(bin_path)
    if not txt_path.is_file():
        raise Exception(f"missing txt pair: {txt_path}")
    header, ticks, books = read_round(str(bin_path))
    market_start_ts = int(header["market_start_ts"])
    txt_rows = parse_txt_data_rows(txt_path)
    ptb = float(header["ptb_chainlink"])
    fee_rate = float(header["fee_rate"])
    side_risks = compute_side_risks(ticks, ptb)
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
        stale = (recv_ts_ms - chainlink_recv_ms) > (stall_reconnect_sec * 1000)
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
            "vol": txt["vol"], "side_risk": side_risks[i],
            "dwin_a": txt["dwin_a"], "dwin_b_pct": txt["dwin_b_pct"],
        }
        books_by_sec[sec] = books[i]
    return LoadedRound(
        market_start_ts=market_start_ts, market_end_ts=int(header["market_end_ts"]),
        fee_rate=fee_rate, ptb_chainlink=ptb, outcome_code=int(header["outcome"]),
        outcome_name=OUTCOME_NAMES[int(header["outcome"])], final_chainlink=float(header["final_chainlink"]),
        ticks_by_sec=by_sec, books_by_sec=books_by_sec, all_secs=all_secs)
