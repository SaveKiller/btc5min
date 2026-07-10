import math

import numpy as np

from src.setup import RISK_MIN_VOL_COVERAGE_RATIO, VOLATILITY_MIN_CHANGES, VOLATILITY_WINDOWS_SEC


def chainlink_stale(sample_recv_ms: float, chainlink_recv_ms: float, stall_sec: float) -> bool:
    return (sample_recv_ms - chainlink_recv_ms) > stall_sec * 1000


def tick_sec(row: np.ndarray) -> int:
    return int(math.floor(row[1] + 0.5))


def compute_vol_window_stats(ticks: np.ndarray, window_sec: int, min_changes: int, stall_sec: float) -> dict[str, np.ndarray]:
    n = ticks.shape[0]
    secs = [tick_sec(ticks[i]) for i in range(n)]
    btcs = ticks[:, 6]
    vol_usd = np.full(n, np.nan)
    n_pairs = np.zeros(n, dtype=np.int32)
    sigma_w = np.full(n, np.nan)
    coverage = np.zeros(n, dtype=np.float64)
    stale_in_window = np.zeros(n, dtype=bool)
    valid = np.zeros(n, dtype=bool)
    for i in range(n):
        sec_i = secs[i]
        hi = sec_i + window_sec - 1
        idxs = [j for j in range(n) if sec_i <= secs[j] <= hi]
        sec_seen = {secs[j] for j in idxs}
        coverage[i] = len(sec_seen) / window_sec
        if len(idxs) < 2: continue
        stale_in_window[i] = any(chainlink_stale(ticks[j, 0], ticks[j, 8], stall_sec) for j in idxs)
        w_btcs = [float(btcs[j]) for j in idxs]
        deltas = [w_btcs[k] - w_btcs[k - 1] for k in range(1, len(w_btcs))]
        n_pairs[i] = len(deltas)
        if len(deltas) < min_changes: continue
        std_d = float(np.std(deltas, ddof=1))
        sigma_w[i] = std_d
        vol_usd[i] = std_d * math.sqrt(len(deltas))
        row_stale = chainlink_stale(ticks[i, 0], ticks[i, 8], stall_sec)
        if (not row_stale and not stale_in_window[i]
                and coverage[i] >= RISK_MIN_VOL_COVERAGE_RATIO and std_d > 1e-9):
            valid[i] = True
    return {
        "vol_usd": vol_usd, "n_pairs": n_pairs, "sigma_w": sigma_w,
        "coverage": coverage, "stale_in_window": stale_in_window, "valid": valid,
    }


def compute_vol_stats_by_window(ticks: np.ndarray, stall_sec: float) -> dict[int, dict[str, np.ndarray]]:
    return {w: compute_vol_window_stats(ticks, w, VOLATILITY_MIN_CHANGES, stall_sec) for w in VOLATILITY_WINDOWS_SEC}
