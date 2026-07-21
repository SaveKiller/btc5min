# Aggregazione per ora UTC delle row di backtest strategia.
from __future__ import annotations
from dashv2.batch.markets import UTC_HOUR_MARKETS


def reduce_analyze_fallback(per_round: list[dict]) -> str:
    """Markdown minimale se il modulo analyze non espone reduce_results."""
    n_ok = sum(1 for r in per_round if r.get("ok"))
    return f"# Stats\n\nrounds_ok: {n_ok}\nrounds_total: {len(per_round)}\n"


def _empty_bucket(hour: str, market: str) -> dict:
    return {
        "hour": hour, "market": market,
        "rounds": 0, "traded": 0, "pos": 0, "neg": 0, "flat": 0,
        "pnl_sum": 0.0, "pos_sum": 0.0, "neg_sum": 0.0,
        "pnl_avg_pos": None, "pnl_avg_neg": None,
    }


def _finalize(b: dict) -> dict:
    b["pnl_avg_pos"] = (b["pos_sum"] / b["pos"]) if b["pos"] else None
    b["pnl_avg_neg"] = (b["neg_sum"] / b["neg"]) if b["neg"] else None
    return b


def reduce_strategy_rows(rows: list[dict]) -> dict:
    """Riduce le row strategia in 24 bucket orari + totale."""
    buckets = [_empty_bucket(f"{h:02d}:00", UTC_HOUR_MARKETS[h]) for h in range(24)]
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
            b["pos_sum"] += pnl
        elif pnl < 0:
            b["neg"] += 1
            b["neg_sum"] += pnl
        else:
            b["flat"] += 1
    for b in buckets:
        _finalize(b)
    total = _empty_bucket("", "")
    del total["hour"]
    del total["market"]
    for b in buckets:
        for k in ("rounds", "traded", "pos", "neg", "flat"):
            total[k] += b[k]
        total["pnl_sum"] += b["pnl_sum"]
        total["pos_sum"] += b["pos_sum"]
        total["neg_sum"] += b["neg_sum"]
    _finalize(total)
    return {"hours": buckets, "total": total}
