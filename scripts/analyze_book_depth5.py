"""Analisi liquidità orderbook: full depth vs top-5 livelli.

Per ogni tick completo di ogni round .bin misura:
- USD massimi spendibili in market-buy (fee incluse) su ask top-5 vs full
- se BET_USD tipici ($50/$100/$200/$500) sono fillabili a depth 5
- BBO (best bid/ask): deve essere identico (top-5 include il livello 0)
- "quota effettiva": VWAP size-weighted sugli ask (cent) top-5 vs full vs best ask

Uso:
  python scripts/analyze_book_depth5.py [data_dir] [depth]

Default: data/ , depth=5. Report in data/reports/book_depth5_<ts>.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.binary_format import read_round
from src.book import BookSide, tick_quotes_missing
from src.clob_api import BET_USD, majority_side

DEPTH_DEFAULT = 5
PROBE_SIZES = (50.0, 100.0, 200.0, 500.0)


def find_bins(data_dir: Path) -> list[Path]:
    flat = sorted(data_dir.glob("bin/btc5m_*.bin"))
    if flat:
        return flat
    return sorted(data_dir.glob("**/btc5m_*.bin"))


def top_n(levels: BookSide, n: int, asks: bool) -> BookSide:
    ordered = sorted(levels, key=lambda t: t[0] if asks else -t[0])
    return ordered[:n]


def ask_notional_usd(asks: BookSide, fee_rate: float) -> float:
    """Budget massimo (cost+fee) spendibile camminando gli ask dati."""
    total = 0.0
    for p, size in sorted(asks, key=lambda t: t[0]):
        total += size * p * (1.0 + fee_rate * (1.0 - p))
    return total


def ask_vwap_c(asks: BookSide) -> float | None:
    """Prezzo medio size-weighted in centesimi; None se vuoto."""
    if not asks:
        return None
    num = sum(p * s for p, s in asks)
    den = sum(s for _, s in asks)
    if den <= 0:
        return None
    return (num / den) * 100.0


def side_asks(snap, side: str) -> tuple[BookSide, float]:
    if side == "Up":
        return snap.up_asks, snap.up_ask
    return snap.down_asks, snap.down_ask


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else DEPTH_DEFAULT
    bins = find_bins(data_dir)
    if not bins:
        raise Exception(f"no .bin under {data_dir}")

    liq5: list[float] = []
    liq_full: list[float] = []
    ratio5: list[float] = []
    vwap5_c: list[float] = []
    vwap_full_c: list[float] = []
    best_ask_c: list[float] = []
    vwap5_minus_best: list[float] = []
    vwap_full_minus_best: list[float] = []
    vwap5_minus_full: list[float] = []
    levels_ask: list[int] = []
    fill_ok = {s: 0 for s in PROBE_SIZES}
    fill_ok_full = {s: 0 for s in PROBE_SIZES}
    n_complete = 0
    n_partial = 0
    n_bbo_mismatch = 0
    n_rounds = 0
    t0 = time.perf_counter()

    for i, path in enumerate(bins):
        header, ticks, books = read_round(str(path))
        fee = float(header["fee_rate"])
        n_rounds += 1
        for row, snap in zip(ticks, books):
            if tick_quotes_missing(row):
                n_partial += 1
                continue
            n_complete += 1
            side = majority_side(row[2], row[3], row[4], row[5])
            asks, quote_ask = side_asks(snap, side)
            asks5 = top_n(asks, depth, asks=True)

            # BBO: top-N non sposta best ask/bid (livello 0)
            for full, trunc in (
                (snap.up_bids, top_n(snap.up_bids, depth, False)),
                (snap.up_asks, top_n(snap.up_asks, depth, True)),
                (snap.down_bids, top_n(snap.down_bids, depth, False)),
                (snap.down_asks, top_n(snap.down_asks, depth, True)),
            ):
                if full and trunc and abs(full[0][0] - trunc[0][0]) > 1e-12:
                    n_bbo_mismatch += 1
                    break

            a5 = ask_notional_usd(asks5, fee)
            af = ask_notional_usd(asks, fee)
            liq5.append(a5)
            liq_full.append(af)
            if af > 1e-9:
                ratio5.append(a5 / af)
            levels_ask.append(len(asks))

            ba_c = quote_ask * 100.0
            best_ask_c.append(ba_c)
            v5 = ask_vwap_c(asks5)
            vf = ask_vwap_c(asks)
            if v5 is not None:
                vwap5_c.append(v5)
                vwap5_minus_best.append(v5 - ba_c)
            if vf is not None:
                vwap_full_c.append(vf)
                vwap_full_minus_best.append(vf - ba_c)
            if v5 is not None and vf is not None:
                vwap5_minus_full.append(v5 - vf)

            for s in PROBE_SIZES:
                if a5 + 1e-9 >= s:
                    fill_ok[s] += 1
                if af + 1e-9 >= s:
                    fill_ok_full[s] += 1

        if (i + 1) % 200 == 0 or i + 1 == len(bins):
            elapsed = time.perf_counter() - t0
            print(f"  {i + 1}/{len(bins)} rounds  complete_ticks={n_complete}  {elapsed:.1f}s", flush=True)

    def pct(xs: list[float], p: float) -> float:
        return float(np.percentile(xs, p)) if xs else float("nan")

    def mean(xs: list[float]) -> float:
        return float(np.mean(xs)) if xs else float("nan")

    report = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_dir": str(data_dir),
        "depth": depth,
        "rounds": n_rounds,
        "ticks_complete": n_complete,
        "ticks_partial": n_partial,
        "bbo_mismatch_ticks": n_bbo_mismatch,
        "note_bbo": (
            "Best bid/ask (quota UI da mid BBO) NON cambia truncando a top-N: "
            "il livello 0 resta. Cambia la liquidità walk e il VWAP sui livelli più profondi."
        ),
        "majority_ask_levels": {
            "mean": mean(levels_ask),
            "p50": pct(levels_ask, 50),
            "p90": pct(levels_ask, 90),
            "max": float(max(levels_ask)) if levels_ask else None,
        },
        "majority_ask_liquidity_usd": {
            f"top{depth}": {
                "mean": mean(liq5),
                "p10": pct(liq5, 10),
                "p50": pct(liq5, 50),
                "p90": pct(liq5, 90),
            },
            "full": {
                "mean": mean(liq_full),
                "p10": pct(liq_full, 10),
                "p50": pct(liq_full, 50),
                "p90": pct(liq_full, 90),
            },
            "ratio_topN_over_full": {
                "mean": mean(ratio5),
                "p10": pct(ratio5, 10),
                "p50": pct(ratio5, 50),
                "p90": pct(ratio5, 90),
            },
        },
        "fillable_fraction_majority_ask": {
            str(int(s)): {
                f"top{depth}": fill_ok[s] / n_complete if n_complete else None,
                "full": fill_ok_full[s] / n_complete if n_complete else None,
            }
            for s in PROBE_SIZES
        },
        "quote_cents_majority_ask": {
            "best_ask_mean": mean(best_ask_c),
            f"vwap_top{depth}_mean": mean(vwap5_c),
            "vwap_full_mean": mean(vwap_full_c),
            f"vwap_top{depth}_minus_best_ask_mean": mean(vwap5_minus_best),
            "vwap_full_minus_best_ask_mean": mean(vwap_full_minus_best),
            f"vwap_top{depth}_minus_vwap_full_mean": mean(vwap5_minus_full),
        },
        "reference_bet_usd": BET_USD,
    }

    out_dir = data_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"book_depth5_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"rounds={n_rounds}  complete_ticks={n_complete}  partial={n_partial}")
    print(f"bbo_mismatch={n_bbo_mismatch}  (atteso 0: top-{depth} non sposta best bid/ask)")
    print()
    print(f"--- Liquidita ASK lato maggioritario (USD fee-incluse), depth={depth} ---")
    m = report["majority_ask_liquidity_usd"]
    print(f"  top{depth}: mean=${m[f'top{depth}']['mean']:.1f}  p50=${m[f'top{depth}']['p50']:.1f}  "
          f"p10=${m[f'top{depth}']['p10']:.1f}  p90=${m[f'top{depth}']['p90']:.1f}")
    print(f"  full:   mean=${m['full']['mean']:.1f}  p50=${m['full']['p50']:.1f}  "
          f"p10=${m['full']['p10']:.1f}  p90=${m['full']['p90']:.1f}")
    print(f"  ratio top{depth}/full: mean={m['ratio_topN_over_full']['mean']:.3f}  "
          f"p50={m['ratio_topN_over_full']['p50']:.3f}")
    print()
    print("--- Frazione tick dove il market-buy e' fillabile ---")
    for s in PROBE_SIZES:
        f5 = fill_ok[s] / n_complete
        ff = fill_ok_full[s] / n_complete
        print(f"  ${s:.0f}: top{depth}={f5:.1%}  full={ff:.1%}")
    print()
    q = report["quote_cents_majority_ask"]
    print("--- Quota (cent) ASK maggioritario ---")
    print(f"  best_ask mean:     {q['best_ask_mean']:.2f}c")
    print(f"  VWAP top{depth} mean:   {q[f'vwap_top{depth}_mean']:.2f}c  "
          f"(delta vs best: {q[f'vwap_top{depth}_minus_best_ask_mean']:+.2f}c)")
    print(f"  VWAP full mean:    {q['vwap_full_mean']:.2f}c  "
          f"(delta vs best: {q['vwap_full_minus_best_ask_mean']:+.2f}c)")
    print(f"  VWAP top{depth} - VWAP full mean: {q[f'vwap_top{depth}_minus_vwap_full_mean']:+.2f}c")
    print()
    print(f"report: {out_path}")


if __name__ == "__main__":
    main()
