"""Feed .txt round sintetici Lighter (formato ridotto, audit header)."""

import math

import numpy as np

from src.binary_format import OUTCOME_NAMES
from src.clob_api import side_from_chainlink
from src.lighter_risk import compute_lighter_rd
from src.lighter_sampling import STALE_MS, lighter_stale
from src.setup import (
    RISK_MIN_VOL_COVERAGE_RATIO, RISK_MODEL_VERSION, RISK_PRIMARY_VOL_WINDOW_SEC,
    RISK_PROBABILITY_BUCKETS, RISK_TARGET, VOLATILITY_MIN_CHANGES, VOLATILITY_WINDOWS_SEC,
)
from src.txt_format import (
    _fmt_price, format_btc_cell, format_delta_cell, format_mmss, format_utc_ts,
    format_vol_header, format_vol_token, vol_column_width,
)
from src.vol_stats import compute_vol_stats_by_window, tick_sec as _tick_sec

RD_COL_W = 4
_STALL_SEC = 1.0


def _fmt_delta_audit(v: float) -> str:
    if math.isnan(v):
        return "nan"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}"


def format_quote_side(side: str) -> str:
    label = "UP" if side == "Up" else "DOWN"
    return label.ljust(9)


def format_rd_token(value: int | None) -> str:
    if value is None:
        return "Rd -"
    return f"Rd {value}"


def _lighter_stale_row(boundary_ms: float, sample_ts_ms: float) -> bool:
    return lighter_stale(int(boundary_ms - sample_ts_ms))


def compute_lighter_vols(ticks: np.ndarray) -> dict[int, np.ndarray]:
    stats = compute_vol_stats_by_window(ticks, _STALL_SEC)
    out: dict[int, np.ndarray] = {}
    for w in VOLATILITY_WINDOWS_SEC:
        vol = stats[w]["vol_usd"].copy()
        for i in range(ticks.shape[0]):
            if _lighter_stale_row(ticks[i, 0], ticks[i, 8]):
                vol[i] = np.nan
        out[w] = vol
    return out


def _format_lighter_table_row(sec: str, time: str, quote: str, delta: str, btc_val: str,
        vol_tokens: str, rd_token: str) -> str:
    vol_w = vol_column_width()
    return (
        f"{sec:>3}  {time:>5}  {quote:<9}  "
        f"{delta:>5}  {btc_val:>8}  {vol_tokens:<{vol_w}}  {rd_token:>{RD_COL_W + 1}}"
    )


def _lighter_column_header() -> str:
    vol_hdr = format_vol_header()
    return (
        f"{'sec':>3}  {'time':>5}  {'quote':<9}  "
        f"{'delta':>5}  {'btc':>8}  {vol_hdr}  {'Rd':>{RD_COL_W}}"
    )


def render_lighter_round_txt(header: dict, ticks: np.ndarray, warnings: list[str]) -> str:
    ptb = header["ptb_chainlink"]
    vols = compute_lighter_vols(ticks)
    rd_vals = compute_lighter_rd(ticks, ptb)
    stale_ticks = sum(1 for row in ticks if _lighter_stale_row(row[0], row[8]))
    agreement = header["outcome_agreement"]
    if agreement is True:
        agreement_s = "TRUE"
    elif agreement is False:
        agreement_s = "FALSE"
    else:
        agreement_s = "nan"
    lines = ["header:",
        f"  source: lighter_synthetic",
        f"  market_start_ts: {header['market_start_ts']} ({format_utc_ts(header['market_start_ts'])})",
        f"  market_end_ts: {header['market_end_ts']} ({format_utc_ts(header['market_end_ts'])})",
        f"  intraday: H{header['intraday_h']}",
        f"  ptb_price: {_fmt_price(header['ptb_price'])}",
        f"  ptb_chainlink: {_fmt_price(header['ptb_chainlink'])}",
        f"  ptb_gamma: {_fmt_price(header['ptb_gamma'])}",
        f"  final_price: {_fmt_price(header['final_price'])}",
        f"  final_chainlink: {_fmt_price(header['final_chainlink'])}",
        f"  final_gamma: {_fmt_price(header['final_gamma'])}",
        f"  outcome_lighter: {header['outcome_lighter']}",
        f"  outcome: {OUTCOME_NAMES[header['outcome']]}",
        f"  outcome_agreement: {agreement_s}",
        f"  delta_lighter: {_fmt_delta_audit(header['delta_lighter'])}",
        f"  delta_chainlink: {_fmt_delta_audit(header['delta_chainlink'])}",
        f"  move_error: {_fmt_delta_audit(header['move_error'])}",
        f"  tick_count: {header['tick_count']}",
        f"  fee_rate: nan",
        f"  stale_sec: {STALE_MS / 1000}",
        f"  stale_ticks: {stale_ticks}",
        f"  vol_windows_sec: {VOLATILITY_WINDOWS_SEC}",
        f"  vol_min_changes: {VOLATILITY_MIN_CHANGES}",
        f"  vol_unit: usd_trailing",
        f"  risk_model_version: {RISK_MODEL_VERSION}",
        f"  risk_status: experimental_uncalibrated",
        f"  risk_target: {RISK_TARGET}",
        f"  risk_label_source: gamma_official_when_available",
        f"  risk_ptb_source: lighter_mid",
        f"  risk_primary_vol_window_sec: {RISK_PRIMARY_VOL_WINDOW_SEC}",
        f"  risk_min_vol_coverage_ratio: {RISK_MIN_VOL_COVERAGE_RATIO}",
        f"  risk_probability_buckets: {RISK_PROBABILITY_BUCKETS}",
        f"  risk_variants: [Rd]"]
    if warnings:
        lines.append("  warnings:")
        for w in warnings:
            lines.append(f"    - {w}")
    lines.extend(["", "data:", _lighter_column_header(), "-" * len(_lighter_column_header())])
    indexed = [(_tick_sec(row), i, row) for i, row in enumerate(ticks)]
    indexed.sort(key=lambda t: -t[0])
    for sec, tick_idx, row in indexed:
        chainlink = float(row[6])
        stale = _lighter_stale_row(row[0], row[8])
        side = side_from_chainlink(chainlink, ptb)
        vol_tokens = "  ".join(format_vol_token(w, vols[w][tick_idx]) for w in VOLATILITY_WINDOWS_SEC)
        lines.append(_format_lighter_table_row(
            str(sec), format_mmss(sec), format_quote_side(side),
            format_delta_cell(chainlink, ptb, stale), format_btc_cell(chainlink),
            vol_tokens, format_rd_token(rd_vals[tick_idx])))
    return "\n".join(lines) + "\n"
