import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.binary_format import OUTCOME_NAMES, read_round, read_warnings
from src.book import tick_quotes_missing
from src.clob_api import majority_side, side_from_chainlink


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


def format_delta(chainlink: float, ptb_chainlink: float) -> str:
    d = round(chainlink - ptb_chainlink)
    if d > 0:
        return f"+{d}$"
    if d < 0:
        return f"{d}$"
    return "0$"


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


def format_table_row(sec: str, time: str, quote: str, delta: str, gain_val: str, btc_val: str) -> str:
    return (
        f"{sec:>3}  {time:>5}  {quote:<9}  "
        f"{delta:>5}  gain={gain_val:>6}  btc={btc_val:>10}"
    )


def format_gain_pct(gain: float) -> str:
    return f"{gain * 100:.1f}%"


def format_column_header() -> str:
    return (
        f"{'sec':>3}  {'time':>5}  {'quote':<9}  "
        f"{'delta':>5}  {'gain%':>11}  {'btc':>14}"
    )


def format_separator() -> str:
    return "-" * len(format_column_header())


def format_data_row_partial(sec: int, side: str, chainlink: float, ptb: float) -> str:
    return format_table_row(
        str(sec), format_mmss(sec), format_quote_partial(side),
        format_delta(chainlink, ptb), "  ---", f"{chainlink:.2f}",
    )


def format_data_row(sec: int, up_prob: int, down_prob: int, chainlink: float, ptb: float, gain: float) -> str:
    return format_table_row(
        str(sec), format_mmss(sec), format_quote(up_prob, down_prob),
        format_delta(chainlink, ptb), format_gain_pct(gain), f"{chainlink:.2f}",
    )


def convert_round(path: str) -> str:
    header, ticks, _ = read_round(path)
    ptb = header["ptb_chainlink"]
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
        f"  fee_rate: {header['fee_rate']}"]
    warn_lines = read_warnings(path)
    if warn_lines:
        lines.append("  warnings:")
        for w in warn_lines:
            lines.append(f"    - {w}")
    lines.extend([
        "",
        "data:",
        format_column_header(),
        format_separator(),
    ])
    last_side: str | None = None
    indexed = []
    for row in ticks:
        sec = int(math.floor(row[1] + 0.5))
        indexed.append((sec, row))
    indexed.sort(key=lambda t: -t[0])
    for sec, row in indexed:
        chainlink, gain = row[6], row[7]
        if tick_quotes_missing(row):
            side = last_side or side_from_chainlink(chainlink, ptb)
            lines.append(format_data_row_partial(sec, side, chainlink, ptb))
            continue
        up_prob = round((row[2] + row[3]) / 2 * 100)
        down_prob = round((row[4] + row[5]) / 2 * 100)
        if not (0 <= up_prob <= 100 and 0 <= down_prob <= 100):
            raise Exception(f"C3: prob out of range sec {sec}: {up_prob}/{down_prob}")
        last_side = majority_side(row[2], row[3], row[4], row[5])
        lines.append(format_data_row(sec, up_prob, down_prob, chainlink, ptb, gain))
    return "\n".join(lines) + "\n"


def write_round_txt(bin_path: str) -> None:
    Path(bin_path).with_suffix(".txt").write_text(convert_round(bin_path), encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception("usage: python -m src.convert <file.bin|dir> [-o out.txt]")
    target = Path(sys.argv[1])
    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]
    if target.is_dir():
        for bin_path in sorted(target.glob("*.bin")):
            write_round_txt(str(bin_path))
            print(f"written {bin_path.with_suffix('.txt')}")
    else:
        text = convert_round(str(target))
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
            print(f"written {out_path}")
        else:
            print(text, end="")


if __name__ == "__main__":
    main()
