"""Diagnostica PTB: formato timestamp e cattura al bordo round."""
import json
import threading
import time
from datetime import datetime, timezone

import websocket

from src.feed_chainlink import ts_to_ms
from src.round_state import RoundState

RTDS = "wss://ws-live-data.polymarket.com"


def inspect_messages() -> None:
    print("=== raw messages ===")
    live_ts = []
    batch_ts = []
    done = threading.Event()

    def on_message(ws, raw):
        nonlocal live_ts, batch_ts
        if not raw or raw == "PONG": return
        msg = json.loads(raw)
        p = msg.get("payload") or {}
        if "value" in p:
            ts = int(p["timestamp"])
            live_ts.append(ts)
            print(f"LIVE raw_ts={ts} norm_ms={ts_to_ms(ts)} value={p['value']}")
        elif "data" in p:
            pts = p["data"]
            print(f"BATCH count={len(pts)}")
            for pt in pts[:2]:
                ts = int(pt["timestamp"])
                batch_ts.append(ts)
                print(f"  batch raw_ts={ts} norm_ms={ts_to_ms(ts)} value={pt['value']}")
            if len(pts) > 2:
                pt = pts[-1]
                ts = int(pt["timestamp"])
                print(f"  batch last raw_ts={ts} norm_ms={ts_to_ms(ts)}")
        if len(live_ts) + len(batch_ts) >= 6: done.set(); ws.close()

    ws = websocket.WebSocketApp(RTDS, on_message=on_message)
    t = threading.Thread(target=lambda: ws.run_forever(ping_interval=20, ping_timeout=20), daemon=True)
    t.start()
    done.wait(timeout=30)
    ws.close()
    if live_ts: print(f"live ts digit lens: {[len(str(t)) for t in live_ts]}")
    if batch_ts: print(f"batch ts digit lens: {[len(str(t)) for t in batch_ts]}")


def test_feed_capture() -> None:
    step = 300
    start_ts = int(time.time()) // step * step + step
    wait = start_ts - time.time() - 12
    if wait > 0:
        print(f"waiting {wait:.0f}s until T-12 for round {start_ts}")
        time.sleep(wait)

    state = RoundState(start_ts, start_ts, start_ts + step, "up", "down", 0.072)
    from src.feed_chainlink import ChainlinkFeed
    feed = ChainlinkFeed.get()
    feed.configure("btc")
    feed.start()
    feed.register(state)
    start_ms = start_ts * 1000
    print(f"round {start_ts} = {datetime.fromtimestamp(start_ts, tz=timezone.utc)}")
    print(f"start_ms={start_ms}")

    while time.time() < start_ts + 20:
        if state.price_to_beat is not None:
            print(f"CAPTURED ptb={state.price_to_beat} ptb_ts_ms={state._ptb_ts_ms} lag_ms={state._ptb_ts_ms - start_ms}")
            break
        time.sleep(0.1)
    else:
        print(f"FAILED after 20s price={state.chainlink_price} ptb={state.price_to_beat}")

    state.stop.set()
    feed.unregister(state)


def main() -> None:
    try: inspect_messages()
    except Exception as e: print("inspect failed:", e)
    try: test_feed_capture()
    except Exception as e: print("capture test failed:", e)


if __name__ == "__main__":
    main()
