"""Caricamento tick Lighter BTC (CSV mid 1Hz) e metriche vol su finestre 300s."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.setup import VOLATILITY_MIN_CHANGES
from src.vol_stats import tick_sec

WINDOW_SEC = 300
_ROOT = Path(__file__).resolve().parent.parent
_HOUR_BANDS_PATH = _ROOT / "hour_bands.json"
_hour_bands_cache: dict | None = None


def load_day_mid_by_sec(csv_path: str) -> dict[int, float]:
    """Ultimo mid per secondo UTC da CSV Lighter timestamp,ask,bid,nonce."""
    by_sec: dict[int, float] = {}
    with open(csv_path, "rb", buffering=1 << 20) as f:
        next(f)
        for line in f:
            i1 = line.find(b",")
            i2 = line.find(b",", i1 + 1)
            i3 = line.find(b",", i2 + 1)
            ts_ms = int(line[:i1])
            ask = float(line[i1 + 1 : i2])
            bid = float(line[i2 + 1 : i3])
            by_sec[ts_ms // 1000] = (ask + bid) * 0.5
    return by_sec


def iter_day_windows(by_sec: dict[int, float], day_start_ts: int):
    """Finestre 300s allineate a confini 5 min UTC; yield (start_ts, mids[300], coverage)."""
    day_end = day_start_ts + 86400
    t = day_start_ts
    while t + WINDOW_SEC <= day_end:
        if t % WINDOW_SEC != 0:
            raise Exception(f"window not 5min aligned: {t}")
        mids = []
        filled = 0
        for i in range(WINDOW_SEC):
            sec = t + i
            if sec in by_sec:
                mids.append(by_sec[sec])
                filled += 1
            else:
                mids.append(float("nan"))
        yield t, mids, filled / WINDOW_SEC
        t += WINDOW_SEC


def day_start_ts_from_path(csv_path: str) -> int:
    name = Path(csv_path).stem  # raw-btc-2026-04-06
    date_s = name.removeprefix("raw-btc-")
    d = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def _vol_from_deltas(deltas: np.ndarray) -> float:
    if len(deltas) < VOLATILITY_MIN_CHANGES:
        return float("nan")
    std_d = float(np.std(deltas, ddof=1))
    return std_d * math.sqrt(len(deltas))


def fast_window_metrics(mids: list[float]) -> dict[str, float]:
    """RV300 e mediane V30/V60/V120 su griglia 1Hz (equivalente vol_stats, O(n*W))."""
    arr = np.asarray(mids, dtype=np.float64)
    n = len(arr)
    rv300 = _vol_from_deltas(np.diff(arr))
    v30, v60, v120 = [], [], []
    for sec in range(60, 241):
        start = n - sec
        for w, bucket in ((30, v30), (60, v60), (120, v120)):
            seg = arr[start : start + w]
            if len(seg) < 2:
                continue
            v = _vol_from_deltas(np.diff(seg))
            if not math.isnan(v):
                bucket.append(v)
    return {
        "rv300": rv300,
        "v30_med": float(np.median(v30)) if v30 else float("nan"),
        "v60_med": float(np.median(v60)) if v60 else float("nan"),
        "v120_med": float(np.median(v120)) if v120 else float("nan"),
    }


def window_vol_metrics(mids: list[float], start_ts: int) -> dict[str, float]:
    if any(math.isnan(m) for m in mids):
        raise Exception("window_vol_metrics requires full mids without nan")
    return fast_window_metrics(mids)


def round_vol_metrics_from_ticks(ticks: np.ndarray) -> dict[str, float]:
    """Metriche vol su round .bin (chainlink_btc su griglia 1Hz)."""
    pairs = [(tick_sec(ticks[i]), float(ticks[i, 6])) for i in range(ticks.shape[0])]
    pairs.sort(key=lambda x: -x[0])
    mids = [p[1] for p in pairs]
    if len(mids) != WINDOW_SEC:
        raise Exception(f"expected {WINDOW_SEC} ticks, got {len(mids)}")
    return fast_window_metrics(mids)


def utc_dow_hour(start_ts: int) -> tuple[int, int]:
    dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    return dt.weekday(), dt.hour


def load_hour_bands() -> dict:
    global _hour_bands_cache
    if _hour_bands_cache is None:
        if not _HOUR_BANDS_PATH.is_file():
            raise Exception(f"hour_bands.json not found: {_HOUR_BANDS_PATH}")
        _hour_bands_cache = json.loads(_HOUR_BANDS_PATH.read_text(encoding="utf-8"))
    return _hour_bands_cache


def hour_band(market_start_ts: int) -> int:
    """Fascia H (1..k) da mappa canonica hour_bands.json e market_start_ts UTC."""
    data = load_hour_bands()
    k = data["k"]
    lookup = data["lookup"]
    dow, hour = utc_dow_hour(market_start_ts)
    if str(dow) not in lookup:
        raise Exception(f"hour_bands lookup missing dow={dow}")
    if str(hour) not in lookup[str(dow)]:
        raise Exception(f"hour_bands lookup missing dow={dow} hour={hour}")
    h = int(lookup[str(dow)][str(hour)])
    if h < 1 or h > k:
        raise Exception(f"hour_band invalid H={h} for k={k}")
    return h
