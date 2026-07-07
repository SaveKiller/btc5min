import json
import time
import threading
import websocket

events = []
conn_t0 = None
last_msg = None


def log(evt, **data):
    events.append({"t": round(time.time() - conn_t0, 2) if conn_t0 else 0, "evt": evt, **data})


def on_open(ws):
    global conn_t0
    conn_t0 = time.time()
    log("open")
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
    global last_msg
    now = time.time()
    gap = round(now - last_msg, 2) if last_msg else None
    last_msg = now
    if raw and raw.upper() != "PONG":
        try:
            msg = json.loads(raw)
            topic = msg.get("topic")
            sym = (msg.get("payload") or {}).get("symbol")
            log("msg", topic=topic, symbol=sym, gap=gap)
        except Exception:
            log("msg_raw", gap=gap, len=len(raw))
    else:
        log("pong", gap=gap)


def on_close(ws, code, msg):
    log("close", code=code, msg=str(msg), age=round(time.time() - conn_t0, 2))


def on_error(ws, err):
    log("error", err=str(err), age=round(time.time() - conn_t0, 2))


ws = websocket.WebSocketApp(
    "wss://ws-live-data.polymarket.com",
    on_open=on_open, on_message=on_message, on_close=on_close, on_error=on_error,
)
threading.Thread(target=lambda: ws.run_forever(ping_interval=None), daemon=True).start()
time.sleep(120)
ws.close()
time.sleep(1)
print(json.dumps(events, indent=2))
print("TOTAL", len(events))
