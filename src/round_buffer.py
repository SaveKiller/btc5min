import numpy as np

from src.book import QUOTE_NA


class RoundBuffer:
    def __init__(self):
        self._rows: list[list[float]] = []

    def append(self, recv_ts_ms: int, secs_to_expiry: float, up_bid: float, up_ask: float,
            down_bid: float, down_ask: float, chainlink_btc: float, majority_gain: float,
            chainlink_recv_ms: int) -> None:
        self._rows.append([
            recv_ts_ms, secs_to_expiry, up_bid, up_ask, down_bid, down_ask, chainlink_btc, majority_gain,
            chainlink_recv_ms,
        ])

    def append_partial(self, recv_ts_ms: int, secs_to_expiry: float, chainlink_btc: float,
            chainlink_recv_ms: int) -> None:
        self.append(recv_ts_ms, secs_to_expiry, QUOTE_NA, QUOTE_NA, QUOTE_NA, QUOTE_NA,
            chainlink_btc, QUOTE_NA, chainlink_recv_ms)

    def set_gain(self, i: int, gain: float) -> None:
        self._rows[i][7] = gain

    def row(self, i: int) -> list[float]:
        return self._rows[i]

    def to_numpy(self) -> np.ndarray:
        if not self._rows:
            raise Exception("round buffer is empty")
        return np.array(self._rows, dtype=np.float64)

    def clear(self) -> None:
        self._rows.clear()

    def __len__(self) -> int:
        return len(self._rows)
