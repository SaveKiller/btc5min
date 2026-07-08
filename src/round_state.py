import logging
import threading

from src.book import BookSnapshot, OrderBook
from src.round_buffer import RoundBuffer

log = logging.getLogger("round")


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
        self.ptb_chainlink: float | None = None
        self.final_chainlink: float | None = None
        self.ptb_gamma: float | None = None
        self.final_gamma: float | None = None
        self.gamma_outcome: str | None = None
        self._ptb_start_ms = market_start_ts * 1000
        self._final_end_ms = market_end_ts * 1000
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
            if ts_ms <= self._ptb_start_ms:
                self.ptb_chainlink = value
            if ts_ms <= self._final_end_ms:
                self.final_chainlink = value

    def apply_chainlink(self, value: float, ts_ms: int, recv_ms: int) -> None:
        with self.lock:
            self.chainlink_price = value
            self.chainlink_ts_ms = ts_ms
            if ts_ms <= self._ptb_start_ms:
                self.ptb_chainlink = value
            if ts_ms <= self._final_end_ms:
                self.final_chainlink = value

    def apply_gamma_ptb(self, value: float) -> bool:
        with self.lock:
            if self.ptb_gamma is not None:
                return False
            self.ptb_gamma = value
        log.info("round %s ptb_gamma=%.2f", self.start_ts, value)
        return True

    def apply_gamma_final(self, value: float) -> bool:
        with self.lock:
            if self.final_gamma is not None:
                return False
            self.final_gamma = value
        return True

    def apply_gamma_outcome(self, outcome: str) -> bool:
        with self.lock:
            if self.gamma_outcome is None:
                self.gamma_outcome = outcome
                return True
            return False

    def display_ptb(self) -> float | None:
        with self.lock:
            if self.ptb_gamma is not None:
                return self.ptb_gamma
            return self.ptb_chainlink

    def ensure_ptb_chainlink(self) -> bool:
        with self.lock:
            if self.ptb_chainlink is not None:
                return False
            if self.chainlink_price is None or self.chainlink_ts_ms is None:
                return False
            if self.chainlink_ts_ms > self._ptb_start_ms:
                return False
            self.ptb_chainlink = self.chainlink_price
            return True

    def ensure_final_chainlink(self) -> bool:
        with self.lock:
            if self.final_chainlink is not None:
                return False
            if self.chainlink_price is None or self.chainlink_ts_ms is None:
                return False
            if self.chainlink_ts_ms > self._final_end_ms:
                return False
            self.final_chainlink = self.chainlink_price
            return True

    def require_chainlink_prices(self) -> tuple[float, float]:
        with self.lock:
            if self.ptb_chainlink is None:
                raise Exception(f"ptb_chainlink missing for round {self.start_ts}")
            if self.final_chainlink is None:
                raise Exception(f"final_chainlink missing for round {self.start_ts}")
            return self.ptb_chainlink, self.final_chainlink

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
