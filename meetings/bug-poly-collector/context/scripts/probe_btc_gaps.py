import json
import time
import threading
import websocket

conn_t0 = None
last_btc = None
btc_gaps = []
events = []


def on_open(ws):
    global conn_t0
    conn_t0 = time.time()
    events.append(("open", 0))
    ws.send(json.dumps({
        "action": "subscribe",
        "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}],
    }))

    def ping():
        while True:
            time.sleep(5)
            try:
                ws.send("ping")
            except Exception:
                return

    threading.Thread(target=ping, daemon=True).start()


def on_message(ws, raw):
    global last_btc
    if not raw or raw.upper() == "PONG":
        return
    msg = json.loads(raw)
    if msg.get("topic") != "crypto_prices_chainlink":
        return
    if (msg.get("payload") or {}).get("symbol") != "btc/usd":
        return
    t = time.time() - conn_t0
    if last_btc is not None:
        btc_gaps.append(t - last_btc)
    last_btc = t


def on_close(ws, code, msg):
    events.append(("close", round(time.time() - conn_t0, 2), code, str(msg)))


def on_error(ws, err):
    events.append(("error", round(time.time() - conn_t0, 2), str(err)))


duration = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 600
ws = websocket.WebSocketApp(
    "wss://ws-live-data.polymarket.com",
    on_open=on_open, on_message=on_message, on_close=on_close, on_error=on_error,
)
threading.Thread(target=lambda: ws.run_forever(ping_interval=None), daemon=True).start()
time.sleep(duration)
ws.close()
time.sleep(1)
print("duration", duration)
print("btc_ticks", len(btc_gaps) + (1 if last_btc else 0))
print("max_btc_gap", round(max(btc_gaps), 2) if btc_gaps else None)
print("p95_btc_gap", round(sorted(btc_gaps)[int(len(btc_gaps) * 0.95)], 2) if len(btc_gaps) > 1 else None)
print("server_events", events)
