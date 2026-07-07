import copy
import json
import logging
import threading
import time

import websocket

from src.round_state import RoundState

log = logging.getLogger("clob")
CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class ClobThread(threading.Thread):
    def __init__(self, state: RoundState):
        super().__init__(daemon=True, name=f"clob-{state.start_ts}")
        self.state = state
        self._ws: websocket.WebSocketApp | None = None
        self._intentional_close = False

    def run(self) -> None:
        while not self.state.stop.is_set() and time.time() < self.state.market_end_ts:
            try:
                self._run_once()
            except Exception as e:
                if self.state.stop.is_set(): break
                log.info("clob round %s reconnect after: %s", self.state.start_ts, e)
                time.sleep(0.5)

    def _close_ws(self, intentional: bool = True) -> None:
        self._intentional_close = intentional
        if self._ws: self._ws.close()

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        pass

    def _on_error(self, ws, error) -> None:
        if self._intentional_close or self.state.stop.is_set():
            return
        log.info("clob round %s ws drop: %s", self.state.start_ts, error)

    def _watch_stop(self) -> None:
        while not self.state.stop.is_set():
            time.sleep(0.2)
        self._close_ws(intentional=True)

    def _run_once(self) -> None:
        self._ws = websocket.WebSocketApp(
            CLOB_WS_URL, on_open=self._on_open, on_message=self._on_message,
            on_close=self._on_close, on_error=self._on_error)
        watcher = threading.Thread(target=self._watch_stop, daemon=True, name=f"clob-stop-{self.state.start_ts}")
        watcher.start()
        while not self.state.stop.is_set() and time.time() < self.state.market_end_ts:
            self._intentional_close = False
            self._ws.run_forever(ping_interval=30, ping_timeout=10)
            if self.state.stop.is_set() or self._intentional_close:
                return
            time.sleep(0.5)

    def _on_open(self, ws) -> None:
        ws.send(json.dumps({
            "assets_ids": [self.state.up_token_id, self.state.down_token_id],
            "type": "market", "custom_feature_enabled": True,
        }))

    def _on_message(self, ws, raw: str) -> None:
        if raw == "PONG": return
        msg = json.loads(raw)
        if isinstance(msg, list):
            for item in msg:
                if item.get("bids") is not None or item.get("asks") is not None:
                    self._apply_book(item)
            return
        self._handle(msg)

    def _handle(self, msg: dict) -> None:
        event_type = msg.get("event_type")
        if event_type == "book": self._apply_book(msg)
        elif event_type == "best_bid_ask": self._apply_best(msg)
        elif event_type == "price_change": self._apply_changes(msg)

    def _book_for(self, asset_id: str):
        if asset_id == self.state.up_token_id: return self.state.up_book
        if asset_id == self.state.down_token_id: return self.state.down_book
        raise Exception(f"unknown asset_id: {asset_id}")

    def _apply_book(self, msg: dict) -> None:
        with self.state.lock:
            book = self._book_for(msg["asset_id"])
            book.replace_side(msg.get("bids") or [], msg.get("asks") or [])

    def _apply_best(self, msg: dict) -> None:
        with self.state.lock:
            book = self._book_for(msg["asset_id"])
            bid, ask = float(msg["best_bid"]), float(msg["best_ask"])
            if book.bids: book.bids[0] = (bid, book.bids[0][1])
            else: book.bids = [(bid, 1.0)]
            if book.asks: book.asks[0] = (ask, book.asks[0][1])
            else: book.asks = [(ask, 1.0)]
            book.bids.sort(key=lambda t: -t[0])
            book.asks.sort(key=lambda t: t[0])

    def _apply_changes(self, msg: dict) -> None:
        with self.state.lock:
            for ch in msg.get("price_changes") or []:
                book = self._book_for(ch["asset_id"])
                price, size = float(ch["price"]), float(ch["size"])
                book.update_level(price, size, ch["side"])
                bb, ba = ch.get("best_bid"), ch.get("best_ask")
                if bb not in (None, "", "0") and book.bids:
                    book.bids[0] = (float(bb), book.bids[0][1])
                if ba not in (None, "", "0") and book.asks:
                    book.asks[0] = (float(ba), book.asks[0][1])
                book.bids.sort(key=lambda t: -t[0])
                book.asks.sort(key=lambda t: t[0])


def snapshot_books(state: RoundState):
    with state.lock:
        up = copy.deepcopy(state.up_book)
        down = copy.deepcopy(state.down_book)
        cl = state.chainlink_price
        ptb = state.price_to_beat
    if cl is None: raise Exception("chainlink price missing at sample")
    from src.book import BookSnapshot
    return BookSnapshot(
        copy.deepcopy(up.bids), copy.deepcopy(up.asks),
        copy.deepcopy(down.bids), copy.deepcopy(down.asks),
        up.best_bid(), up.quote_ask(), down.best_bid(), down.quote_ask()), cl, ptb


def snapshot_chainlink(state: RoundState) -> tuple[float, float | None]:
    with state.lock:
        cl = state.chainlink_price
        ptb = state.price_to_beat
    if cl is None:
        raise Exception("chainlink price missing at sample")
    return cl, ptb
