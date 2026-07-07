import threading

from src.book import BookSnapshot, OrderBook
from src.round_buffer import RoundBuffer


class RoundState:
    def __init__(self, start_ts: int, market_start_ts: int, market_end_ts: int,
            up_token_id: str, down_token_id: str, fee_rate: float):
        self.lock = threading.Lock()
        self.start_ts = start_ts
        self.market_start_ts = market_start_ts
        self.market_end_ts = market_end_ts
        self.up_token_id = up_token_id
        self.down_token_id = down_token_id
        self.fee_rate = fee_rate
        self.chainlink_price: float | None = None
        self.chainlink_ts_ms: int | None = None
        self.price_to_beat: float | None = None
        self.final_chainlink: float | None = None
        self._ptb_start_ms = market_start_ts * 1000
        self._ptb_ts_ms: int | None = None
        self._final_end_ms = market_end_ts * 1000
        self._final_ts_ms: int | None = None
        self._final_source: str | None = None
        self.up_book = OrderBook()
        self.down_book = OrderBook()
        self.buffer = RoundBuffer()
        self.book_snapshots: list[BookSnapshot] = []
        self.last_countdown_sec: int | None = None
        self.stop = threading.Event()
        self.chainlink_done = threading.Event()

    def prime_chainlink(self, value: float, ts_ms: int) -> None:
        with self.lock:
            self.chainlink_price = value
            self.chainlink_ts_ms = ts_ms

    def apply_chainlink(self, value: float, ts_ms: int, recv_ms: int) -> None:
        with self.lock:
            self.chainlink_price = value
            self.chainlink_ts_ms = ts_ms
            if ts_ms < self._ptb_start_ms: return
            if self._ptb_ts_ms is None or ts_ms < self._ptb_ts_ms:
                self._ptb_ts_ms = ts_ms
                self.price_to_beat = value
            if ts_ms >= self._final_end_ms:
                self._final_ts_ms = ts_ms
                self.final_chainlink = value
                self._final_source = "oracle"
            elif recv_ms >= self._final_end_ms and self._final_source != "oracle":
                if self._final_ts_ms is None:
                    self._final_ts_ms = ts_ms
                    self.final_chainlink = value
                    self._final_source = "recv"

    def chainlink_ready(self) -> bool:
        with self.lock:
            return self.chainlink_price is not None

    def books_ready(self) -> bool:
        try:
            self.up_book.best_bid()
            self.down_book.best_bid()
            self.up_book.quote_ask()
            self.down_book.quote_ask()
            return True
        except Exception:
            return False
