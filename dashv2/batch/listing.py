"""Listing round validi per range di giorni UTC (batch Stats)."""
from __future__ import annotations

from datetime import datetime, timezone


def list_batch_rounds(repo, day_from: str, day_to: str) -> tuple[list[dict], int]:
    """Ritorna i round validi in [day_from, day_to] e il conteggio degli invalidi saltati."""
    out: list[dict] = []
    skipped = 0
    for e in repo.list_picker():
        day = e["day_utc"]
        if day < day_from or day > day_to:
            continue
        if not e["valid"]:
            skipped += 1
            continue
        mts = int(e["market_start_ts"])
        hour = datetime.fromtimestamp(mts, timezone.utc).hour
        out.append({
            "market_start_ts": mts,
            "bin_path": str(repo.bin_path(mts)),
            "hour_utc": hour,
            "day_utc": day,
        })
    out.sort(key=lambda x: x["market_start_ts"])
    return out, skipped
