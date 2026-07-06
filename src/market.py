import json
import logging
import time
from datetime import datetime, timezone

import httpx

for _name in ("httpx", "httpcore", "h2"):
    logging.getLogger(_name).setLevel(logging.WARNING)

GAMMA_URL = "https://gamma-api.polymarket.com/events"
INTERVAL_SECS = {"5m": 300, "15m": 900, "1h": 3600}


def current_round_start_ts(interval: str) -> int:
    step = INTERVAL_SECS[interval]
    return int(time.time()) // step * step


def next_round_start_ts(start_ts: int, interval: str) -> int:
    return start_ts + INTERVAL_SECS[interval]


def build_slug(asset: str, interval: str, start_ts: int) -> str:
    return f"{asset}-updown-{interval}-{start_ts}"


def fetch_event(slug: str) -> dict:
    r = httpx.get(GAMMA_URL, params={"slug": slug}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise Exception(f"gamma event not found: {slug}")
    return data[0]


def parse_market(event: dict) -> dict:
    markets = event["markets"]
    if not markets:
        raise Exception("event has no markets")
    m = markets[0]
    outcomes = json.loads(m["outcomes"])
    if outcomes != ["Up", "Down"]:
        raise Exception(f"unexpected outcomes order: {outcomes}")
    token_ids = json.loads(m["clobTokenIds"])
    start_raw = event.get("eventStartTime") or event.get("startTime") or m.get("startDate")
    end_raw = m["endDate"]
    start_ts = int(datetime.fromisoformat(start_raw.replace("Z", "+00:00")).timestamp())
    end_ts = int(datetime.fromisoformat(end_raw.replace("Z", "+00:00")).timestamp())
    meta = event.get("eventMetadata") or {}
    price_to_beat = float(meta["priceToBeat"]) if meta.get("priceToBeat") is not None else None
    final_price = float(meta["finalPrice"]) if meta.get("finalPrice") is not None else None
    outcome = None
    if m.get("closed"):
        prices = json.loads(m["outcomePrices"])
        if prices[0] == "1":
            outcome = "Up"
        elif prices[1] == "1":
            outcome = "Down"
    if outcome is None and m.get("outcomePrices"):
        prices = [float(x) for x in json.loads(m["outcomePrices"])]
        if prices[0] >= 0.9:
            outcome = "Up"
        elif prices[1] >= 0.9:
            outcome = "Down"
    settled = bool(m.get("closed")) or outcome is not None
    return {
        "slug": event["slug"], "condition_id": m["conditionId"],
        "up_token_id": token_ids[0], "down_token_id": token_ids[1],
        "market_start_ts": start_ts, "market_end_ts": end_ts,
        "price_to_beat": price_to_beat, "final_chainlink": final_price, "outcome": outcome,
        "closed": settled,
    }


def fetch_market_by_slug(asset: str, interval: str, start_ts: int) -> dict:
    slug = build_slug(asset, interval, start_ts)
    return parse_market(fetch_event(slug))


def wait_for_market(asset: str, interval: str, start_ts: int, timeout_sec: float = 120) -> dict:
    deadline = time.time() + timeout_sec
    last_err = None
    while time.time() < deadline:
        try:
            return fetch_market_by_slug(asset, interval, start_ts)
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise Exception(f"market not available after {timeout_sec}s: {last_err}")
