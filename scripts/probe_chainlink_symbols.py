"""Probe RTDS Chainlink symbols for a few seconds."""
from __future__ import annotations

import json
import sys
import threading
import time

import websocket

RTDS = "wss://ws-live-data.polymarket.com"
SYMBOLS = [s.strip() for s in sys.argv[1].split(",")] if len(sys.argv) > 1 else [
    "btc/usd", "eth/usd", "sol/usd", "xrp/usd", "doge/usd", "bnb/usd", "hype/usd"]
seen: dict[str, float] = {}
lock = threading.Lock()
done = threading.Event()


def on_message(ws, raw):
    if not raw or raw.upper() == "PONG":
        return
    msg = json.loads(raw)
    if msg.get("topic") != "crypto_prices_chainlink":
        return
    payload = msg.get("payload") or {}
    sym = payload.get("symbol")
    if sym not in SYMBOLS:
        return
    val = None
    if "value" in payload:
        val = float(payload["value"])
    elif "data" in payload and payload["data"]:
        val = float(payload["data"][-1]["value"])
    if val is None:
        return
    with lock:
        seen[sym] = val
        if len(seen) >= len(SYMBOLS):
            done.set()
            ws.close()


def on_open(ws):
    ws.send(json.dumps({
        "action": "subscribe",
        "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}],
    }))


ws = websocket.WebSocketApp(RTDS, on_message=on_message, on_open=on_open)
t = threading.Thread(target=lambda: ws.run_forever(ping_interval=20, ping_timeout=20), daemon=True)
t.start()
done.wait(timeout=25)
ws.close()
for s in SYMBOLS:
    print(f"{s}: {seen.get(s, 'MISSING')}")
missing = [s for s in SYMBOLS if s not in seen]
if missing:
    raise SystemExit(f"missing symbols: {missing}")
