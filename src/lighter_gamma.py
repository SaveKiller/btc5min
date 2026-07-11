"""Fetch Gamma serializzato per build round Lighter (cache + lock globale tra processi)."""

import json
import time
from pathlib import Path

from src.market import fetch_market_by_slug

GAMMA_SLEEP_SEC = 0.125

_broker: "GammaBroker | None" = None


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


def _http_fetch(start_ts: int) -> dict:
    try:
        m = fetch_market_by_slug("btc", "5m", start_ts)
        return {
            "start_ts": start_ts,
            "ptb": m["price_to_beat"],
            "final": m["final_chainlink"],
            "outcome": m["outcome"],
            "fetched_at": int(time.time()),
        }
    except Exception as e:
        return {
            "start_ts": start_ts, "ptb": None, "final": None, "outcome": None,
            "error": str(e), "fetched_at": int(time.time()),
        }


class GammaBroker:
    """Un solo flusso HTTP verso Gamma; i worker acquisiscono il lock e rispettano lo spacing."""

    def __init__(self, cache_path: Path, sleep_sec: float, lock, shared_cache, last_fetch_at):
        self.cache_path = cache_path
        self.sleep_sec = sleep_sec
        self.lock = lock
        self.shared_cache = shared_cache
        self.last_fetch_at = last_fetch_at

    @classmethod
    def local(cls, cache_path: Path, sleep_sec: float = GAMMA_SLEEP_SEC) -> "GammaBroker":
        from threading import Lock
        lock = Lock()
        shared = _load_cache_file(cache_path)
        broker = cls(cache_path, sleep_sec, lock, shared, [0.0])
        return broker

    @classmethod
    def shared(cls, manager, cache_path: Path, sleep_sec: float = GAMMA_SLEEP_SEC) -> "GammaBroker":
        lock = manager.Lock()
        last_fetch_at = manager.Value("d", 0.0)
        shared_cache = manager.dict()
        for ts, row in _load_cache_file(cache_path).items():
            shared_cache[ts] = row
        return cls(cache_path, sleep_sec, lock, shared_cache, last_fetch_at)

    def fetch(self, start_ts: int) -> dict:
        if start_ts in self.shared_cache:
            return dict(self.shared_cache[start_ts])
        with self.lock:
            if start_ts in self.shared_cache:
                return dict(self.shared_cache[start_ts])
            if isinstance(self.last_fetch_at, list):
                elapsed = time.time() - self.last_fetch_at[0]
                last_ref = self.last_fetch_at
            else:
                elapsed = time.time() - self.last_fetch_at.value
                last_ref = self.last_fetch_at
            wait = self.sleep_sec - elapsed
            if wait > 0:
                time.sleep(wait)
            row = _http_fetch(start_ts)
            self.shared_cache[start_ts] = row
            if isinstance(last_ref, list):
                last_ref[0] = time.time()
            else:
                last_ref.value = time.time()
            _append_cache_row(self.cache_path, row)
        return dict(row)


def install_broker(broker: GammaBroker) -> None:
    global _broker
    _broker = broker


def fetch_gamma(start_ts: int) -> dict:
    if _broker is None:
        raise Exception("gamma broker not installed")
    return _broker.fetch(start_ts)


def init_worker_broker(cache_path: str, sleep_sec: float, lock, shared_cache, last_fetch_at) -> None:
    install_broker(GammaBroker(Path(cache_path), sleep_sec, lock, shared_cache, last_fetch_at))
