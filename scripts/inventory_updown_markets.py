"""Inventario mercati Polymarket Up/Down: probe slug live per asset×interval."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from src.market import INTERVAL_SECS, build_slug

GAMMA_URL = "https://gamma-api.polymarket.com/events"
CANDIDATE_ASSETS = [
    "btc", "eth", "sol", "xrp", "doge", "bnb", "matic", "avax", "link",
    "ada", "dot", "ltc", "pepe", "wif", "trump", "hype", "sui", "ton",
]
INTERVALS = ["5m", "15m", "1h"]


def probe_pair(client: httpx.Client, asset: str, interval: str, now: float) -> dict | None:
    step = INTERVAL_SECS[interval]
    base = int(now) // step * step
    for ts in (base, base + step, base - step):
        slug = build_slug(asset, interval, ts)
        r = client.get(GAMMA_URL, params={"slug": slug}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            continue
        ev = data[0]
        return {
            "asset": asset,
            "interval": interval,
            "slug": slug,
            "title": ev.get("title"),
            "active": ev.get("active"),
            "closed": ev.get("closed"),
            "url": f"https://polymarket.com/event/{slug}",
            "start_ts": ts,
        }
    return None


def main() -> None:
    now = time.time()
    found = []
    with httpx.Client() as client:
        for asset in CANDIDATE_ASSETS:
            for interval in INTERVALS:
                if interval not in INTERVAL_SECS:
                    continue
                hit = probe_pair(client, asset, interval, now)
                if hit:
                    found.append(hit)
                    print(f"OK {asset} {interval}: {hit['slug']}", file=sys.stderr)
                else:
                    print(f"-- {asset} {interval}: none", file=sys.stderr)
    pairs_5_15 = [r for r in found if r["interval"] in ("5m", "15m")]
    result = {
        "probed_at": int(now),
        "pairs_5m_15m": pairs_5_15,
        "pairs_all_including_1h": found,
        "assets_5m_15m": sorted({r["asset"] for r in pairs_5_15}),
        "count_5m_15m": len(pairs_5_15),
    }
    print(json.dumps(result, indent=4))


if __name__ == "__main__":
    main()
