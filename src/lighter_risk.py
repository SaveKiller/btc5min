"""Indice Rd su round sintetici Lighter (solo rischio fisico, no Rq)."""

import math

import numpy as np

from src.clob_api import side_from_chainlink
from src.risk import _compute_pz, _delta_signed, prob_to_r
from src.setup import RISK_MIN_VOL_COVERAGE_RATIO, RISK_PRIMARY_VOL_WINDOW_SEC, VOLATILITY_WINDOWS_SEC
from src.lighter_sampling import lighter_stale
from src.vol_stats import compute_vol_stats_by_window

_SIGMA_EPS = 1e-9
_STALL_SEC = 1.0


def compute_lighter_rd(ticks: np.ndarray, ptb: float) -> list[int | None]:
    vol_stats = compute_vol_stats_by_window(ticks, _STALL_SEC)
    n = ticks.shape[0]
    out: list[int | None] = []
    for i in range(n):
        row = ticks[i]
        stale_row = lighter_stale(int(row[0] - row[8]))
        chainlink = float(row[6])
        secs_to_expiry = float(row[1])
        side = side_from_chainlink(chainlink, ptb)
        stats = vol_stats[RISK_PRIMARY_VOL_WINDOW_SEC]
        rd: int | None = None
        if stale_row:
            pass
        elif not stats["valid"][i]:
            pass
        elif stats["sigma_w"][i] <= _SIGMA_EPS:
            pass
        elif stats["coverage"][i] < RISK_MIN_VOL_COVERAGE_RATIO:
            pass
        else:
            delta_signed = _delta_signed(chainlink, ptb, side)
            sigma_w = float(stats["sigma_w"][i])
            pz = _compute_pz(delta_signed, sigma_w, secs_to_expiry)
            rd = prob_to_r(pz)
        out.append(rd)
    return out
