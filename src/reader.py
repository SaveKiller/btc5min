import csv
import sys
from pathlib import Path

from src.binary_format import OUTCOME_NAMES, read_round, read_warnings


def print_round(path: str, csv_path: str | None = None) -> None:
    header, ticks = read_round(path)
    print(f"file: {path}")
    print(f"  market_start_ts: {header['market_start_ts']}")
    print(f"  market_end_ts: {header['market_end_ts']}")
    print(f"  price_to_beat: {header['price_to_beat']:.2f}")
    print(f"  outcome: {OUTCOME_NAMES[header['outcome']]}")
    print(f"  final_chainlink: {header['final_chainlink']}")
    print(f"  tick_count: {header['tick_count']}")
    for w in read_warnings(path):
        print(f"  WARNING: {w}")
    n = len(ticks)
    print(f"  first secs_to_expiry: {ticks[0, 1]:.2f}")
    print(f"  last secs_to_expiry: {ticks[-1, 1]:.2f}")
    print(f"  up_ask range: {ticks[:, 3].min():.3f} - {ticks[:, 3].max():.3f}")
    print(f"  down_ask range: {ticks[:, 5].min():.3f} - {ticks[:, 5].max():.3f}")
    gmin, gmax = ticks[:, 7].min() * 100, ticks[:, 7].max() * 100
    print(f"  majority_gain range: {gmin:.1f}% - {gmax:.1f}%")
    print("  first 5 ticks:")
    for row in ticks[:5]:
        print(f"    sec={row[1]:.1f} up={row[2]:.2f}/{row[3]:.2f} down={row[4]:.2f}/{row[5]:.2f} btc={row[6]:.1f} gain={row[7]*100:.1f}%")
    print("  last 5 ticks:")
    for row in ticks[-5:]:
        print(f"    sec={row[1]:.1f} up={row[2]:.2f}/{row[3]:.2f} down={row[4]:.2f}/{row[5]:.2f} btc={row[6]:.1f} gain={row[7]*100:.1f}%")
    if csv_path:
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["recv_ts_ms", "secs_to_expiry", "up_bid", "up_ask", "down_bid", "down_ask", "chainlink_btc", "majority_gain"])
            for row in ticks:
                w.writerow(row.tolist())
        print(f"  csv written: {csv_path}")


def main() -> None:
    if len(sys.argv) < 2:
        raise Exception("usage: python -m src.reader <file.bin> [--csv out.csv]")
    path = sys.argv[1]
    csv_path = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2] == "--csv" else None
    print_round(path, csv_path)


if __name__ == "__main__":
    main()
