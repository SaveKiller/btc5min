# Aggregazione per ora UTC delle row di backtest strategia.
from __future__ import annotations
from dashv2.batch.markets import UTC_HOUR_MARKETS


def reduce_analyze_fallback(per_round: list[dict]) -> str:
    """Markdown minimale se il modulo analyze non espone reduce_results."""
    n_ok = sum(1 for r in per_round if r.get("ok"))
    return f"# Stats\n\nrounds_ok: {n_ok}\nrounds_total: {len(per_round)}\n"


def reduce_strategy_rows(rows: list[dict]) -> dict:
    """Riduce le row strategia in 24 bucket orari + totale."""
    buckets = [
        {"hour": f"{h:02d}:00", "market": UTC_HOUR_MARKETS[h], "rounds": 0, "traded": 0,
         "pos": 0, "neg": 0, "flat": 0, "pnl_sum": 0.0, "pnl_avg": 0.0}
        for h in range(24)
    ]
    for r in rows:
        if not r["ok"]:
            continue
        b = buckets[int(r["hour_utc"])]
        b["rounds"] += 1
        if r["traded"]:
            b["traded"] += 1
        pnl = float(r["pnl_usd"])
        b["pnl_sum"] += pnl
        if pnl > 0:
            b["pos"] += 1
        elif pnl < 0:
            b["neg"] += 1
        else:
            b["flat"] += 1
    for b in buckets:
        if b["rounds"]:
            b["pnl_avg"] = b["pnl_sum"] / b["rounds"]
    total = {"rounds": 0, "traded": 0, "pos": 0, "neg": 0, "flat": 0, "pnl_sum": 0.0, "pnl_avg": 0.0}
    for b in buckets:
        for k in ("rounds", "traded", "pos", "neg", "flat"):
            total[k] += b[k]
        total["pnl_sum"] += b["pnl_sum"]
    if total["rounds"]:
        total["pnl_avg"] = total["pnl_sum"] / total["rounds"]
    return {"hours": buckets, "total": total}
