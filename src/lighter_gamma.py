"""Prefetch Gamma giornaliero per build round Lighter (cache jsonl + lock tra processi)."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.lighter_sampling import WINDOW_SEC

BTC5M_SERIES_ID = "10684"
GAMMA_EVENTS_KEYSET = "https://gamma-api.polymarket.com/events/keyset"
GAMMA_CACHE_NAME = "_gamma_cache.jsonl"

_broker: "GammaBroker | None" = None


def _day_round_starts(day_start: int) -> list[int]:
    day_end = day_start + 86400
    t = day_start
    starts: list[int] = []
    while t + WINDOW_SEC < day_end:
        starts.append(t)
        t += WINDOW_SEC
    return starts


def _load_cache_file(cache_path: Path) -> dict[int, dict]:
    cache: dict[int, dict] = {}
    if not cache_path.is_file():
        return cache
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cache[int(row["start_ts"])] = row
    return cache


def _append_cache_row(cache_path: Path, row: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _parse_gamma_event(ev: dict) -> dict:
    slug = ev["slug"]
    if not slug.startswith("btc-updown-5m-"):
        raise Exception(f"unexpected gamma event slug: {slug}")
    start_ts = int(slug.rsplit("-", 1)[-1])
    meta = ev.get("eventMetadata") or {}
    ptb = meta.get("priceToBeat")
    final = meta.get("finalPrice")
    markets = ev["markets"]
    if not markets:
        raise Exception(f"gamma event has no markets: {slug}")
    m = markets[0]
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
    return {
        "start_ts": start_ts,
        "ptb": ptb,
        "final": final,
        "outcome": outcome,
        "fetched_at": int(time.time()),
    }


def _fetch_day_events(day_start_ts: int) -> dict[int, dict]:
    day_end_ts = day_start_ts + 86400
    start_dt = datetime.fromtimestamp(day_start_ts, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(day_end_ts, tz=timezone.utc)
    params = {
        "closed": "true",
        "series_id": BTC5M_SERIES_ID,
        "end_date_min": start_dt.isoformat().replace("+00:00", "Z"),
        "end_date_max": end_dt.isoformat().replace("+00:00", "Z"),
        "order": "endDate",
        "ascending": "false",
        "limit": 500,
    }
    rows: dict[int, dict] = {}
    while True:
        r = httpx.get(GAMMA_EVENTS_KEYSET, params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
        for ev in payload["events"]:
            if not ev.get("slug", "").startswith("btc-updown-5m-"):
                continue
            row = _parse_gamma_event(ev)
            rows[row["start_ts"]] = row
        cursor = payload.get("next_cursor")
        if not cursor:
            break
        params["after_cursor"] = cursor
    return rows


class GammaBroker:
    """Cache Gamma con prefetch giornaliero bulk; lock per scrittura cache tra processi."""

    def __init__(self, cache_path: Path, lock, shared_cache):
        self.cache_path = cache_path
        self.lock = lock
        self.shared_cache = shared_cache

    @classmethod
    def local(cls, cache_path: Path) -> "GammaBroker":
        from threading import Lock
        return cls(cache_path, Lock(), _load_cache_file(cache_path))

    @classmethod
    def shared(cls, manager, cache_path: Path) -> "GammaBroker":
        shared_cache = manager.dict()
        for ts, row in _load_cache_file(cache_path).items():
            shared_cache[ts] = row
        return cls(cache_path, manager.Lock(), shared_cache)

    def ensure_gamma_day(self, day_start_ts: int) -> int:
        needed = _day_round_starts(day_start_ts)
        if all(t in self.shared_cache for t in needed):
            return 0
        with self.lock:
            if all(t in self.shared_cache for t in needed):
                return 0
            bulk = _fetch_day_events(day_start_ts)
            added = 0
            for t in needed:
                if t in self.shared_cache:
                    continue
                if t in bulk:
                    row = bulk[t]
                else:
                    row = {
                        "start_ts": t,
                        "ptb": None,
                        "final": None,
                        "outcome": None,
                        "error": f"gamma day bulk missing start_ts {t}",
                        "fetched_at": int(time.time()),
                    }
                self.shared_cache[t] = row
                _append_cache_row(self.cache_path, row)
                added += 1
            return added

    def fetch(self, start_ts: int) -> dict:
        if start_ts not in self.shared_cache:
            raise Exception(f"gamma cache miss start_ts={start_ts}, call ensure_gamma_day first")
        return dict(self.shared_cache[start_ts])


def install_broker(broker: GammaBroker) -> None:
    global _broker
    _broker = broker


def ensure_gamma_day(day_start_ts: int) -> int:
    if _broker is None:
        raise Exception("gamma broker not installed")
    return _broker.ensure_gamma_day(day_start_ts)


def fetch_gamma(start_ts: int) -> dict:
    if _broker is None:
        raise Exception("gamma broker not installed")
    return _broker.fetch(start_ts)


def init_worker_broker(cache_path: str, lock, shared_cache) -> None:
    install_broker(GammaBroker(Path(cache_path), lock, shared_cache))
