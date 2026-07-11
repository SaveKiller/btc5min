"""Campionamento causale round 5m da tick Lighter (301 confini → 300 righe feed)."""

import math
from dataclasses import dataclass

import numpy as np

WINDOW_SEC = 300
STALE_MS = 1000
NAN = float("nan")


@dataclass
class LighterSample:
    mid: float
    boundary_ms: int
    sample_ts_ms: int
    sample_age_ms: int


def load_csv_ticks(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CSV timestamp,ask,bid,nonce → array ordinati per timestamp ms."""
    ts_list: list[int] = []
    bid_list: list[float] = []
    ask_list: list[float] = []
    with open(path, "rb", buffering=1 << 20) as f:
        next(f)
        for line in f:
            i1 = line.find(b",")
            i2 = line.find(b",", i1 + 1)
            i3 = line.find(b",", i2 + 1)
            ts_list.append(int(line[:i1]))
            ask_list.append(float(line[i1 + 1 : i2]))
            bid_list.append(float(line[i2 + 1 : i3]))
    if not ts_list:
        raise Exception(f"empty lighter csv: {path}")
    ts = np.asarray(ts_list, dtype=np.int64)
    bid = np.asarray(bid_list, dtype=np.float64)
    ask = np.asarray(ask_list, dtype=np.float64)
    order = np.argsort(ts, kind="mergesort")
    return ts[order], bid[order], ask[order]


def _last_idx_at_or_before(ts: np.ndarray, boundary_ms: int) -> int | None:
    idx = int(np.searchsorted(ts, boundary_ms, side="right")) - 1
    if idx < 0:
        return None
    return idx


def sample_round(ts: np.ndarray, bid: np.ndarray, ask: np.ndarray, start_ts: int) -> list[LighterSample]:
    """301 campioni causali k=0..300 su confini T+k secondi."""
    if start_ts % WINDOW_SEC != 0:
        raise Exception(f"start_ts not 5min aligned: {start_ts}")
    out: list[LighterSample] = []
    for k in range(WINDOW_SEC + 1):
        boundary_ms = (start_ts + k) * 1000
        idx = _last_idx_at_or_before(ts, boundary_ms)
        if idx is None:
            raise Exception(f"no lighter tick at or before boundary k={k} ts={start_ts + k}")
        sample_ts = int(ts[idx])
        mid = (float(ask[idx]) + float(bid[idx])) * 0.5
        out.append(LighterSample(
            mid=mid, boundary_ms=boundary_ms, sample_ts_ms=sample_ts,
            sample_age_ms=boundary_ms - sample_ts))
    return out


def lighter_stale(sample_age_ms: int) -> bool:
    return sample_age_ms > STALE_MS


def build_ticks_array(samples: list[LighterSample]) -> np.ndarray:
    """300 righe tick-compatible (k=0..299, sec 300→1). Colonne come read_round ticks."""
    if len(samples) != WINDOW_SEC + 1:
        raise Exception(f"expected {WINDOW_SEC + 1} boundary samples, got {len(samples)}")
    rows = []
    for k in range(WINDOW_SEC):
        s = samples[k]
        rows.append([
            float(s.boundary_ms), float(WINDOW_SEC - k),
            NAN, NAN, NAN, NAN, s.mid, NAN, float(s.sample_ts_ms),
        ])
    return np.asarray(rows, dtype=np.float64)
