import math
from dataclasses import dataclass

import numpy as np

from src.book import tick_quotes_missing
from src.clob_api import majority_side, side_from_chainlink
from src.setup import (
    RISK_MIN_VOL_COVERAGE_RATIO, RISK_PRIMARY_VOL_WINDOW_SEC, RISK_PROBABILITY_BUCKETS, RISK_TIE_BAND,
    STALL_RECONNECT_SEC, VOLATILITY_WINDOWS_SEC,
)
from src.vol_stats import chainlink_stale, compute_vol_stats_by_window

_SIGMA_EPS = 1e-9


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_to_r(p: float) -> int:
    for i, threshold in enumerate(RISK_PROBABILITY_BUCKETS):
        if p < threshold:
            return i + 1
    return 9


def format_r_token(name: str, value: int | None) -> str:
    if value is None:
        return f"{name}=-"
    return f"{name}={value}"


RQ_COL_W = 4
RZ_COL_W = 4
RZ_GAP = 2
ELIGIBLE_COL_W = 3


def risk_column_width() -> int:
    return RQ_COL_W + RZ_GAP + RZ_COL_W + 1 + ELIGIBLE_COL_W


@dataclass
class TickRisk:
    Pq0: float
    Rq: int | None
    rq_reason: str | None
    Pz_by_window: dict[int, float]
    Rz_by_window: dict[int, int | None]
    rz_reason_by_window: dict[int, str | None]
    Rz: int | None
    rz_reason: str | None
    eligible: str
    side: str | None
    up_mid: float
    down_mid: float
    z_primary: float


def _is_tie(up_mid: float, down_mid: float) -> bool:
    total = up_mid + down_mid
    if total <= 0:
        raise Exception(f"invalid quote mids: {up_mid} {down_mid}")
    return abs(up_mid - down_mid) / total < RISK_TIE_BAND


def _compute_pq0(up_mid: float, down_mid: float, side: str) -> float:
    p_up = up_mid / (up_mid + down_mid)
    q = p_up if side == "Up" else 1.0 - p_up
    return 1.0 - q


def _compute_pz(delta_signed: float, sigma_w: float, secs_to_expiry: float) -> float:
    sigma_remaining = sigma_w * math.sqrt(secs_to_expiry)
    if sigma_remaining <= _SIGMA_EPS:
        raise Exception("sigma_remaining too small for Pz")
    z = delta_signed / sigma_remaining
    return norm_cdf(-z)


def _delta_signed(chainlink: float, ptb: float, side: str) -> float:
    delta = chainlink - ptb
    return delta if side == "Up" else -delta


def compute_risk_state(ticks: np.ndarray, ptb_chainlink: float) -> list[TickRisk]:
    vol_stats = compute_vol_stats_by_window(ticks, STALL_RECONNECT_SEC)
    n = ticks.shape[0]
    out: list[TickRisk] = []
    for i in range(n):
        row = ticks[i]
        partial = tick_quotes_missing(row)
        stale_row = chainlink_stale(row[0], row[8], STALL_RECONNECT_SEC)
        chainlink = float(row[6])
        secs_to_expiry = float(row[1])
        side: str | None = None
        up_mid = float("nan")
        down_mid = float("nan")
        Pq0 = float("nan")
        Rq: int | None = None
        rq_reason: str | None = None
        if partial:
            rq_reason = "partial"
            side = side_from_chainlink(chainlink, ptb_chainlink)
        else:
            up_mid = (row[2] + row[3]) / 2.0
            down_mid = (row[4] + row[5]) / 2.0
            side = majority_side(row[2], row[3], row[4], row[5])
            if _is_tie(up_mid, down_mid):
                rq_reason = "tie"
            else:
                Pq0 = _compute_pq0(up_mid, down_mid, side)
                Rq = prob_to_r(Pq0)
        Pz_by_window: dict[int, float] = {}
        Rz_by_window: dict[int, int | None] = {}
        rz_reason_by_window: dict[int, str | None] = {}
        z_primary = float("nan")
        for w in VOLATILITY_WINDOWS_SEC:
            stats = vol_stats[w]
            rz_reason: str | None = None
            Pz = float("nan")
            Rz: int | None = None
            if partial:
                rz_reason = "partial"
            elif stale_row:
                rz_reason = "stale"
            elif not stats["valid"][i]:
                if stats["stale_in_window"][i]:
                    rz_reason = "stale"
                elif stats["coverage"][i] < RISK_MIN_VOL_COVERAGE_RATIO:
                    rz_reason = "insufficient_history"
                elif stats["sigma_w"][i] <= _SIGMA_EPS:
                    rz_reason = "zero_vol"
                else:
                    rz_reason = "insufficient_history"
            elif side is None:
                rz_reason = "partial"
            else:
                delta_signed = _delta_signed(chainlink, ptb_chainlink, side)
                sigma_w = float(stats["sigma_w"][i])
                Pz = _compute_pz(delta_signed, sigma_w, secs_to_expiry)
                Rz = prob_to_r(Pz)
                if w == RISK_PRIMARY_VOL_WINDOW_SEC:
                    z_primary = delta_signed / (sigma_w * math.sqrt(secs_to_expiry))
            Pz_by_window[w] = Pz
            Rz_by_window[w] = Rz
            rz_reason_by_window[w] = rz_reason
        Rz_primary = Rz_by_window[RISK_PRIMARY_VOL_WINDOW_SEC]
        rz_reason = rz_reason_by_window[RISK_PRIMARY_VOL_WINDOW_SEC]
        if partial or rq_reason == "tie" or Rq is None or Rz_primary is None:
            eligible = "no"
        else:
            eligible = "yes"
        out.append(TickRisk(
            Pq0=Pq0, Rq=Rq, rq_reason=rq_reason, Pz_by_window=Pz_by_window, Rz_by_window=Rz_by_window,
            rz_reason_by_window=rz_reason_by_window, Rz=Rz_primary, rz_reason=rz_reason, eligible=eligible,
            side=side, up_mid=up_mid, down_mid=down_mid, z_primary=z_primary))
    return out


def format_eligible_cell(eligible: str) -> str:
    return "no" if eligible == "no" else ""


def format_risk_tokens(risk: TickRisk) -> str:
    rq = format_r_token("Rq", risk.Rq)
    rz = format_r_token("Rz", risk.Rz)
    elig = format_eligible_cell(risk.eligible)
    gap = " " * RZ_GAP
    return f"{rq:>{RQ_COL_W}}{gap}{rz:>{RZ_COL_W}} {elig:>{ELIGIBLE_COL_W}}"
