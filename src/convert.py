import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.binary_format import OUTCOME_NAMES, read_round, txt_path_for_bin
from src.book import tick_quotes_missing
from src.clob_api import majority_side, side_from_chainlink
from src.risk import (
    compute_risk_state, ELIGIBLE_COL_W, format_risk_tokens, RQ_COL_W, RZ_COL_W, RZ_GAP, risk_column_width,
)
from src.settlement import outcome_from_prices
from src.setup import (
    RISK_LABEL_SOURCE, RISK_MIN_VOL_COVERAGE_RATIO, RISK_MODEL_VERSION, RISK_PRIMARY_VOL_WINDOW_SEC,
    RISK_PROBABILITY_BUCKETS, RISK_PTB_SOURCE, RISK_TARGET, STALL_RECONNECT_SEC, VOLATILITY_MIN_CHANGES,
    VOLATILITY_WINDOWS_SEC,
)
from src.vol_stats import chainlink_stale, compute_vol_stats_by_window, tick_sec as _tick_sec

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fmt_price(v: float) -> str:
    if math.isnan(v):
        return "nan"
    return f"{v:.2f}"


def sampled_rows(ticks: np.ndarray, ptb_chainlink: float) -> list[tuple[int, float, float, float, float, float]]:
    """Una riga per tick campionato, ordinati per sec decrescente. Nessun forward-fill."""
    if ticks.shape[0] == 0:
        raise Exception("no ticks to convert")
    rows = []
    for row in ticks:
        sec = int(math.floor(row[1] + 0.5))
        up_mid = (row[2] + row[3]) / 2
        down_mid = (row[4] + row[5]) / 2
        rows.append((sec, up_mid, down_mid, row[6], ptb_chainlink, row[7]))
    rows.sort(key=lambda r: -r[0])
    return rows


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
    return len(f"V{window_sec}=9999")


def format_vol_token(window_sec: int, vol_usd: float) -> str:
    w = _vol_token_width(window_sec)
    if math.isnan(vol_usd):
        body = f"V{window_sec}=---"
    else:
        body = f"V{window_sec}={round(vol_usd)}"
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


def format_table_row(sec: str, time: str, quote: str, delta: str, gain_val: str, btc_val: str,
        vol_tokens: str, risk_tokens: str) -> str:
    vol_w = vol_column_width()
    risk_w = risk_column_width()
    return (
        f"{sec:>3}  {time:>5}  {quote:<9}  "
        f"{delta:>5}  gain={gain_val:>6}  btc={btc_val:>10}  {vol_tokens:<{vol_w}}  {risk_tokens:<{risk_w}}"
    )


def format_gain_pct(gain: float) -> str:
    return f"{gain * 100:.1f}%"


def format_column_header() -> str:
    vol_hdr = format_vol_header()
    risk_hdr = f"{'Rq':>{RQ_COL_W}}{' ' * RZ_GAP}{'Rz':>{RZ_COL_W}} {'eligible':>{ELIGIBLE_COL_W}}"
    return (
        f"{'sec':>3}  {'time':>5}  {'quote':<9}  "
        f"{'delta':>5}  {'gain%':>11}  {'btc':>14}  {vol_hdr}  {risk_hdr}"
    )


def format_separator() -> str:
    return "-" * len(format_column_header())


def format_data_row_partial(sec: int, side: str, chainlink: float, ptb: float, stale: bool,
        vol_tokens: str, risk_tokens: str) -> str:
    return format_table_row(
        str(sec), format_mmss(sec), format_quote_partial(side),
        format_delta_cell(chainlink, ptb, stale), "  ---", f"{chainlink:.2f}", vol_tokens, risk_tokens,
    )


def format_data_row(sec: int, up_prob: int, down_prob: int, chainlink: float, ptb: float, gain: float,
        stale: bool, vol_tokens: str, risk_tokens: str) -> str:
    return format_table_row(
        str(sec), format_mmss(sec), format_quote(up_prob, down_prob),
        format_delta_cell(chainlink, ptb, stale), format_gain_pct(gain), f"{chainlink:.2f}", vol_tokens, risk_tokens,
    )


def read_txt_warnings(txt_path: str) -> list[str]:
    p = Path(txt_path)
    if not p.exists():
        return []
    warnings: list[str] = []
    in_warnings = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line == "  warnings:":
            in_warnings = True
            continue
        if in_warnings:
            if line.startswith("    - "):
                warnings.append(line[6:])
            else:
                break
    return warnings


def convert_round(path: str, warnings: list[str]) -> str:
    header, ticks, _ = read_round(path)
    ptb = header["ptb_chainlink"]
    vols_by_window = compute_trailing_vols(ticks)
    risk_states = compute_risk_state(ticks, ptb)
    stale_ticks = sum(1 for row in ticks if chainlink_stale_row(row[0], row[8]))
    lines = ["header:",
        f"  market_start_ts: {header['market_start_ts']} ({format_utc_ts(header['market_start_ts'])})",
        f"  market_end_ts: {header['market_end_ts']} ({format_utc_ts(header['market_end_ts'])})",
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
        f"  risk_variants: [Rq, Rz]"]
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
    indexed = []
    tick_risk_by_idx = {i: risk_states[i] for i in range(len(risk_states))}
    for tick_idx, row in enumerate(ticks):
        indexed.append((_tick_sec(row), row, tick_idx))
    indexed.sort(key=lambda t: -t[0])
    for sec, row, tick_idx in indexed:
        chainlink, gain = row[6], row[7]
        stale = chainlink_stale_row(row[0], row[8])
        vol_tokens = format_vol_tokens(vols_by_window, tick_idx)
        risk_tokens = format_risk_tokens(tick_risk_by_idx[tick_idx])
        if tick_quotes_missing(row):
            side = last_side or side_from_chainlink(chainlink, ptb)
            lines.append(format_data_row_partial(sec, side, chainlink, ptb, stale, vol_tokens, risk_tokens))
            continue
        up_prob = round((row[2] + row[3]) / 2 * 100)
        down_prob = round((row[4] + row[5]) / 2 * 100)
        if not (0 <= up_prob <= 100 and 0 <= down_prob <= 100):
            raise Exception(f"C3: prob out of range sec {sec}: {up_prob}/{down_prob}")
        last_side = majority_side(row[2], row[3], row[4], row[5])
        lines.append(format_data_row(sec, up_prob, down_prob, chainlink, ptb, gain, stale, vol_tokens, risk_tokens))
    return "\n".join(lines) + "\n"


def warnings_from_header(header: dict) -> list[str]:
    computed = outcome_from_prices(header["final_chainlink"], header["ptb_chainlink"])
    outcome_name = OUTCOME_NAMES[header["outcome"]]
    warnings: list[str] = []
    if math.isnan(header["final_gamma"]):
        warnings.append("outcome from chainlink provisional, not gamma")
    if math.isnan(header["ptb_gamma"]):
        warnings.append("ptb_gamma missing at write")
    if not math.isnan(header["final_gamma"]) and outcome_name != computed:
        warnings.append(f"outcome mismatch gamma={outcome_name} computed={computed}")
    return warnings


def write_round_txt(bin_path: str, warnings: list[str]) -> None:
    txt_path = txt_path_for_bin(bin_path)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(convert_round(bin_path, warnings), encoding="utf-8")


def iter_round_bin_paths(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        raise Exception(f"data dir not found: {data_dir}")
    paths: list[Path] = []
    for day_dir in sorted(data_dir.iterdir()):
        if not day_dir.is_dir() or not _DATE_DIR.match(day_dir.name):
            continue
        bin_dir = day_dir / "bin"
        if not bin_dir.is_dir():
            continue
        paths.extend(sorted(bin_dir.glob("*.bin")))
    return paths


def convert_all_round_bins(data_dir: Path) -> None:
    bin_paths = iter_round_bin_paths(data_dir)
    if not bin_paths:
        raise Exception(f"no .bin files in {data_dir}/YYYY-MM-DD/bin")
    for bin_path in bin_paths:
        bp = str(bin_path)
        txt = txt_path_for_bin(bp)
        write_round_txt(bp, read_txt_warnings(str(txt)))
        print(f"written {txt}")


def convert_sync_bins(data_dir: Path) -> None:
    bin_paths = iter_round_bin_paths(data_dir)
    converted = 0
    for bin_path in bin_paths:
        bp = str(bin_path)
        txt = txt_path_for_bin(bp)
        if txt.exists() and txt.stat().st_mtime >= bin_path.stat().st_mtime:
            continue
        header, _, _ = read_round(bp)
        write_round_txt(bp, warnings_from_header(header))
        print(f"written {txt}")
        converted += 1
    if converted == 0:
        print("Nessun bin da convertire.")
    else:
        print(f"Convertiti {converted} file.")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--sync":
        convert_sync_bins(_DATA_DIR)
        return
    if len(sys.argv) < 2:
        convert_all_round_bins(_DATA_DIR)
        return
    target = Path(sys.argv[1])
    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]
    if target.is_dir():
        for bin_path in sorted(target.rglob("*.bin")):
            bp = str(bin_path)
            txt = txt_path_for_bin(bp)
            write_round_txt(bp, read_txt_warnings(str(txt)))
            print(f"written {txt}")
    else:
        bp = str(target)
        txt = txt_path_for_bin(bp)
        warnings = read_txt_warnings(str(txt))
        text = convert_round(bp, warnings)
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
            print(f"written {out_path}")
        else:
            print(text, end="")


if __name__ == "__main__":
    main()
