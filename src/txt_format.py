"""Regole uniche di formattazione del feed .txt round (da .bin)."""

import math
from datetime import datetime, timezone

import numpy as np

from src.binary_format import OUTCOME_NAMES
from src.book import tick_quotes_missing
from src.clob_api import majority_side, side_from_chainlink
from src.delta_win import (
    delta_win_block_width, delta_win_data_header, delta_win_header_lines, delta_win_row_part, load_delta_win_artifact,
)
from src.lighter_ticks import hour_band
from src.risk import TickRisk, compute_risk_state
from src.setup import (
    RISK_LABEL_SOURCE, RISK_MIN_VOL_COVERAGE_RATIO, RISK_MODEL_VERSION,
    RISK_PRIMARY_VOL_WINDOW_SEC, RISK_PROBABILITY_BUCKETS, RISK_PTB_SOURCE, RISK_TARGET,
    STALL_RECONNECT_SEC, VOLATILITY_MIN_CHANGES, VOLATILITY_WINDOWS_SEC, delta_win_sec_active,
)
from src.vol_stats import chainlink_stale, compute_vol_stats_by_window, tick_sec as _tick_sec

RQ_COL_W = 4
RD_COL_W = 4
RD_GAP = 3


def risk_column_width() -> int:
    return RQ_COL_W + RD_GAP + RD_COL_W


def _fmt_price(v: float) -> str:
    if math.isnan(v):
        return "nan"
    return f"{v:.2f}"


def format_utc_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_mmss(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def chainlink_stale_row(sample_recv_ms: float, chainlink_recv_ms: float) -> bool:
    return chainlink_stale(sample_recv_ms, chainlink_recv_ms, STALL_RECONNECT_SEC)


def compute_trailing_vols(ticks: np.ndarray) -> dict[int, np.ndarray]:
    stats = compute_vol_stats_by_window(ticks, STALL_RECONNECT_SEC)
    out: dict[int, np.ndarray] = {}
    for w in VOLATILITY_WINDOWS_SEC:
        vol = stats[w]["vol_usd"].copy()
        for i in range(ticks.shape[0]):
            if chainlink_stale_row(ticks[i, 0], ticks[i, 8]):
                vol[i] = np.nan
        out[w] = vol
    return out


def _vol_token_width(window_sec: int) -> int:
    return len(f"V{window_sec} 9999")


def format_vol_token(window_sec: int, vol_usd: float) -> str:
    w = _vol_token_width(window_sec)
    if math.isnan(vol_usd):
        body = f"V{window_sec} ---"
    else:
        body = f"V{window_sec} {round(vol_usd)}"
    return body.ljust(w)


def format_vol_tokens(vols_by_window: dict[int, np.ndarray], tick_idx: int) -> str:
    return "  ".join(format_vol_token(w, vols_by_window[w][tick_idx]) for w in VOLATILITY_WINDOWS_SEC)


def vol_column_width() -> int:
    return sum(_vol_token_width(w) for w in VOLATILITY_WINDOWS_SEC) + max(0, len(VOLATILITY_WINDOWS_SEC) - 1) * 2


def format_vol_header() -> str:
    return "  ".join(f"V{w}".ljust(_vol_token_width(w)) for w in VOLATILITY_WINDOWS_SEC)


def format_delta(chainlink: float, ptb_chainlink: float) -> str:
    d = round(chainlink - ptb_chainlink)
    if d > 0:
        return f"+{d}$"
    if d < 0:
        return f"{d}$"
    return "0$"


def format_delta_cell(chainlink: float, ptb_chainlink: float, stale: bool) -> str:
    if stale:
        return "  ---"
    return format_delta(chainlink, ptb_chainlink)


def format_quote_partial(side: str) -> str:
    if side == "Up":
        return " UP  ---"
    return "DOWN ---"


def format_quote(up_prob: int, down_prob: int) -> str:
    if up_prob == down_prob:
        return f"---- {up_prob:>3}c"
    if up_prob > down_prob:
        return f" UP  {up_prob:>3}c"
    return f"DOWN {down_prob:>3}c"


def format_btc_cell(chainlink: float) -> str:
    return f"{round(chainlink)}$"


def format_gain_pct(gain: float) -> str:
    return f"{gain * 100:.1f}%"


def format_r_token(name: str, value: int | None) -> str:
    if value is None:
        return f"{name} -"
    return f"{name} {value}"


def format_risk_tokens(risk: TickRisk) -> str:
    rq = format_r_token("Rq", risk.Rq)
    rd = format_r_token("Rd", risk.Rd)
    gap = " " * RD_GAP
    return f"{rq:>{RQ_COL_W}}{gap}{rd:>{RD_COL_W}}"


def format_table_row(sec: str, time: str, quote: str, delta: str, gain_val: str, dw_part: str,
        btc_val: str, vol_tokens: str, risk_tokens: str) -> str:
    vol_w = vol_column_width()
    risk_w = risk_column_width()
    dw_w = delta_win_block_width()
    if dw_w:
        dw_part = f"{dw_part:<{dw_w}}"
    return (
        f"{sec:>3}  {time:>5}  {quote:<9}  "
        f"{delta:>5}  {gain_val:>7}  {dw_part}  "
        f"{btc_val:>8}  {vol_tokens:<{vol_w}}  {risk_tokens:<{risk_w}}"
    )


def format_column_header() -> str:
    vol_hdr = format_vol_header()
    risk_hdr = f"{'Rq':>{RQ_COL_W}}{' ' * RD_GAP}{'Rd':>{RD_COL_W}}"
    return (
        f"{'sec':>3}  {'time':>5}  {'quote':<9}  "
        f"{'delta':>5}  {'gain%':>7}  {delta_win_data_header()}  "
        f"{'btc':>8}  {vol_hdr}  {risk_hdr}"
    )


def format_separator() -> str:
    return "-" * len(format_column_header())


def _checkpoint_stale_in_vol_window(indexed: dict[int, int], ticks: np.ndarray, sec: int, window: int) -> bool:
    from src.vol_stats import vol_window_countdown_secs
    for s in vol_window_countdown_secs(sec, window):
        if s not in indexed:
            raise Exception(f"missing sec {s} in ticks")
        ti = indexed[s]
        if chainlink_stale_row(ticks[ti, 0], ticks[ti, 8]):
            return True
    return False


def _delta_win_row(sec: int, tick_idx: int, ticks: np.ndarray, vols: dict[int, np.ndarray],
        ptb: float, intraday_h: int, indexed: dict[int, int], artifact: dict) -> str:
    eligible, abs_delta, vol_dict = _delta_win_eligible(sec, tick_idx, ticks, vols, ptb, indexed)
    return delta_win_row_part(sec, abs_delta, vol_dict, intraday_h, eligible, artifact)


def _delta_win_eligible(sec: int, tick_idx: int, ticks: np.ndarray, vols: dict[int, np.ndarray],
        ptb: float, indexed: dict[int, int]) -> tuple[bool, int, dict[int, int]]:
    if not delta_win_sec_active(sec):
        return False, 0, {}
    if _checkpoint_stale_in_vol_window(indexed, ticks, sec, max(VOLATILITY_WINDOWS_SEC)):
        return False, 0, {}
    if chainlink_stale_row(ticks[tick_idx, 0], ticks[tick_idx, 8]):
        return False, 0, {}
    vol_dict: dict[int, int] = {}
    for w in VOLATILITY_WINDOWS_SEC:
        v = vols[w][tick_idx]
        if math.isnan(v):
            return False, 0, {}
        vol_dict[w] = round(v)
    abs_delta = abs(round(float(ticks[tick_idx, 6]) - ptb))
    return True, abs_delta, vol_dict


def format_data_row_partial(sec: int, side: str, chainlink: float, ptb: float, stale: bool,
        vol_tokens: str, risk_tokens: str, dw_part: str) -> str:
    return format_table_row(
        str(sec), format_mmss(sec), format_quote_partial(side),
        format_delta_cell(chainlink, ptb, stale), "  ---", dw_part, format_btc_cell(chainlink),
        vol_tokens, risk_tokens,
    )


def format_data_row(sec: int, up_prob: int, down_prob: int, chainlink: float, ptb: float, gain: float,
        stale: bool, vol_tokens: str, risk_tokens: str, dw_part: str) -> str:
    return format_table_row(
        str(sec), format_mmss(sec), format_quote(up_prob, down_prob),
        format_delta_cell(chainlink, ptb, stale), format_gain_pct(gain), dw_part, format_btc_cell(chainlink),
        vol_tokens, risk_tokens,
    )


def render_round_txt(header: dict, ticks: np.ndarray, warnings: list[str],
        delta_win_artifact: dict | None = None) -> str:
    artifact = delta_win_artifact if delta_win_artifact is not None else load_delta_win_artifact()
    ptb = header["ptb_chainlink"]
    intraday_h = hour_band(header["market_start_ts"])
    vols_by_window = compute_trailing_vols(ticks)
    risk_states = compute_risk_state(ticks, ptb)
    stale_ticks = sum(1 for row in ticks if chainlink_stale_row(row[0], row[8]))
    lines = ["header:",
        f"  market_start_ts: {header['market_start_ts']} ({format_utc_ts(header['market_start_ts'])})",
        f"  market_end_ts: {header['market_end_ts']} ({format_utc_ts(header['market_end_ts'])})",
        f"  intraday: H{intraday_h}",
        f"  ptb_price: {_fmt_price(header['ptb_price'])}",
        f"  ptb_chainlink: {_fmt_price(header['ptb_chainlink'])}",
        f"  ptb_gamma: {_fmt_price(header['ptb_gamma'])}",
        f"  final_price: {_fmt_price(header['final_price'])}",
        f"  final_chainlink: {_fmt_price(header['final_chainlink'])}",
        f"  final_gamma: {_fmt_price(header['final_gamma'])}",
        f"  outcome: {OUTCOME_NAMES[header['outcome']]}",
        f"  tick_count: {header['tick_count']}",
        f"  fee_rate: {header['fee_rate']}",
        f"  stale_sec: {STALL_RECONNECT_SEC}",
        f"  stale_ticks: {stale_ticks}",
        f"  vol_windows_sec: {VOLATILITY_WINDOWS_SEC}",
        f"  vol_min_changes: {VOLATILITY_MIN_CHANGES}",
        f"  vol_unit: usd_trailing",
        f"  risk_model_version: {RISK_MODEL_VERSION}",
        f"  risk_status: experimental_uncalibrated",
        f"  risk_target: {RISK_TARGET}",
        f"  risk_label_source: {RISK_LABEL_SOURCE}",
        f"  risk_ptb_source: {RISK_PTB_SOURCE}",
        f"  risk_primary_vol_window_sec: {RISK_PRIMARY_VOL_WINDOW_SEC}",
        f"  risk_min_vol_coverage_ratio: {RISK_MIN_VOL_COVERAGE_RATIO}",
        f"  risk_probability_buckets: {RISK_PROBABILITY_BUCKETS}",
        f"  risk_variants: [Rq, Rd]"]
    lines.extend(delta_win_header_lines(artifact))
    if warnings:
        lines.append("  warnings:")
        for w in warnings:
            lines.append(f"    - {w}")
    lines.extend([
        "",
        "data:",
        format_column_header(),
        format_separator(),
    ])
    last_side: str | None = None
    tick_risk_by_idx = {i: risk_states[i] for i in range(len(risk_states))}
    sec_index = {_tick_sec(row): i for i, row in enumerate(ticks)}
    indexed = []
    for tick_idx, row in enumerate(ticks):
        indexed.append((_tick_sec(row), row, tick_idx))
    indexed.sort(key=lambda t: -t[0])
    for sec, row, tick_idx in indexed:
        chainlink, gain = row[6], row[7]
        stale = chainlink_stale_row(row[0], row[8])
        vol_tokens = format_vol_tokens(vols_by_window, tick_idx)
        risk_tokens = format_risk_tokens(tick_risk_by_idx[tick_idx])
        dw_part = _delta_win_row(sec, tick_idx, ticks, vols_by_window, ptb, intraday_h, sec_index, artifact)
        if tick_quotes_missing(row):
            side = last_side or side_from_chainlink(chainlink, ptb)
            lines.append(format_data_row_partial(sec, side, chainlink, ptb, stale, vol_tokens, risk_tokens, dw_part))
            continue
        up_prob = round((row[2] + row[3]) / 2 * 100)
        down_prob = round((row[4] + row[5]) / 2 * 100)
        if not (0 <= up_prob <= 100 and 0 <= down_prob <= 100):
            raise Exception(f"C3: prob out of range sec {sec}: {up_prob}/{down_prob}")
        last_side = majority_side(row[2], row[3], row[4], row[5])
        lines.append(format_data_row(sec, up_prob, down_prob, chainlink, ptb, gain, stale, vol_tokens, risk_tokens, dw_part))
    return "\n".join(lines) + "\n"
