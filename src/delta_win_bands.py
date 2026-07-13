"""Lookup |delta| 0-150 per delta_win metodo A: pool empirico per H, finestra fissa ±half_base."""

import numpy as np

from src.setup import DELTA_WIN_WINDOW_HALF_BASE

DELTA_LOOKUP_MAX = 150


def clamp_delta(abs_delta: int, max_delta: int = DELTA_LOOKUP_MAX) -> int:
    return min(abs_delta, max_delta)


def window_bounds(d: int, max_delta: int = DELTA_LOOKUP_MAX, half: int = DELTA_WIN_WINDOW_HALF_BASE) -> tuple[int, int]:
    return max(0, d - half), min(max_delta, d + half)


def pool_in_range(sec_samples: list[dict], lo: int, hi: int) -> list[dict]:
    return [s for s in sec_samples if lo <= s["abs_delta"] <= hi]


def fit_window_for_bucket(sec_samples: list[dict], sec: int, min_samples: int,
        half_base: int = DELTA_WIN_WINDOW_HALF_BASE, max_delta: int = DELTA_LOOKUP_MAX) -> dict[str, dict]:
    if not sec_samples:
        return {}
    deltas = np.asarray([s["abs_delta"] for s in sec_samples], dtype=np.int32)
    wins = np.asarray([s["y_win"] for s in sec_samples], dtype=np.float64)
    out: dict[str, dict] = {}
    for center_d in range(max_delta + 1):
        lo, hi = window_bounds(center_d, max_delta, half_base)
        mask = (deltas >= lo) & (deltas <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        slot: dict = {"n": n, "lo": lo, "hi": hi, "half": half_base}
        if n >= min_samples:
            slot["p_win"] = float(wins[mask].mean())
        out[str(center_d)] = slot
    return out


def fit_window_for_sec_h(samples: list[dict], sec: int, intraday_h: int, min_samples: int,
        half_base: int = DELTA_WIN_WINDOW_HALF_BASE, max_delta: int = DELTA_LOOKUP_MAX) -> dict[str, dict]:
    sec_samples = [s for s in samples if s["sec"] == sec and s["intraday_h"] == intraday_h]
    if not sec_samples:
        raise Exception(f"no samples for sec={sec} intraday_h={intraday_h}")
    return fit_window_for_bucket(sec_samples, sec, min_samples, half_base, max_delta)
