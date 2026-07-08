import csv
import math
import sys
from pathlib import Path

from src.binary_format import OUTCOME_NAMES, read_round, read_warnings


def _fmt_price(v: float) -> str:
    if math.isnan(v):
        return "nan"
    return f"{v:.2f}"


def print_round(path: str, csv_path: str | None = None, book_sec: int | None = None) -> None:
    header, ticks, books = read_round(path)
    print(f"file: {path}")
    print(f"  market_start_ts: {header['market_start_ts']}")
    print(f"  market_end_ts: {header['market_end_ts']}")
    print(f"  ptb_price: {_fmt_price(header['ptb_price'])}")
    print(f"  ptb_chainlink: {_fmt_price(header['ptb_chainlink'])}")
    print(f"  ptb_gamma: {_fmt_price(header['ptb_gamma'])}")
    print(f"  final_price: {_fmt_price(header['final_price'])}")
    print(f"  final_chainlink: {_fmt_price(header['final_chainlink'])}")
    print(f"  final_gamma: {_fmt_price(header['final_gamma'])}")
    print(f"  outcome: {OUTCOME_NAMES[header['outcome']]}")
    print(f"  tick_count: {header['tick_count']}")
    print(f"  fee_rate: {header['fee_rate']}")
    for w in read_warnings(path):
        print(f"  WARNING: {w}")
    n = len(ticks)
    print(f"  first secs_to_expiry: {ticks[0, 1]:.2f}")
    print(f"  last secs_to_expiry: {ticks[-1, 1]:.2f}")
    print(f"  up_ask range: {ticks[:, 3].min():.3f} - {ticks[:, 3].max():.3f}")
    print(f"  down_ask range: {ticks[:, 5].min():.3f} - {ticks[:, 5].max():.3f}")
    gmin, gmax = ticks[:, 7].min() * 100, ticks[:, 7].max() * 100
    print(f"  majority_gain range: {gmin:.1f}% - {gmax:.1f}%")
    avg_levels = sum(
        len(s.up_bids) + len(s.up_asks) + len(s.down_bids) + len(s.down_asks) for s in books) / max(n, 1) / 4
    print(f"  avg levels per side: {avg_levels:.1f}")
    print("  first 5 ticks:")
    for row in ticks[:5]:
        print(f"    sec={row[1]:.1f} up={row[2]:.2f}/{row[3]:.2f} down={row[4]:.2f}/{row[5]:.2f} btc={row[6]:.1f} gain={row[7]*100:.1f}%")
    print("  last 5 ticks:")
    for row in ticks[-5:]:
        print(f"    sec={row[1]:.1f} up={row[2]:.2f}/{row[3]:.2f} down={row[4]:.2f}/{row[5]:.2f} btc={row[6]:.1f} gain={row[7]*100:.1f}%")
    if book_sec is not None:
        idx = min(range(n), key=lambda i: abs(ticks[i, 1] - book_sec))
        snap = books[idx]
        sec = int(math.floor(ticks[idx, 1] + 0.5))
        print(f"\n  book dump sec={sec} (tick {idx}):")
        for label, levels in [("up_bids", snap.up_bids), ("up_asks", snap.up_asks),
                ("down_bids", snap.down_bids), ("down_asks", snap.down_asks)]:
            print(f"    {label} ({len(levels)} levels):")
            for p, s in levels[:20]:
                print(f"      {p:.4f} x {s:.2f}")
            if len(levels) > 20:
                print(f"      ... +{len(levels) - 20} more")
    if csv_path:
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["recv_ts_ms", "secs_to_expiry", "up_bid", "up_ask", "down_bid", "down_ask", "chainlink_btc", "majority_gain"])
            for row in ticks:
                w.writerow(row.tolist())
        print(f"  csv written: {csv_path}")


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception("usage: python -m src.reader <file.bin> [--csv out.csv] [--book-sec N]")
    path = sys.argv[1]
    csv_path = None
    book_sec = None
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--csv" and i + 1 < len(sys.argv):
            csv_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--book-sec" and i + 1 < len(sys.argv):
            book_sec = int(sys.argv[i + 1])
            i += 2
        else:
            raise Exception(f"unknown arg: {sys.argv[i]}")
    print_round(path, csv_path, book_sec)


if __name__ == "__main__":
    main()
