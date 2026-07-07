import math
import struct
from dataclasses import dataclass, field

BookSide = list[tuple[float, float]]
QUOTE_NA = float("nan")


def tick_quotes_missing(row) -> bool:
    return math.isnan(float(row[2]))
BOOK_COUNTS_FMT = "<4H"
LEVEL_FMT = "<dd"
BOOK_COUNTS_SIZE = struct.calcsize(BOOK_COUNTS_FMT)
LEVEL_SIZE = struct.calcsize(LEVEL_FMT)


def book_side_to_bytes(levels: BookSide) -> bytes:
    return b"".join(struct.pack(LEVEL_FMT, p, s) for p, s in levels)


def book_side_from_bytes(raw: bytes, offset: int, count: int) -> tuple[BookSide, int]:
    levels: BookSide = []
    for _ in range(count):
        p, s = struct.unpack(LEVEL_FMT, raw[offset:offset + LEVEL_SIZE])
        levels.append((p, s))
        offset += LEVEL_SIZE
    return levels, offset


@dataclass
class OrderBook:
    bids: BookSide = field(default_factory=list)
    asks: BookSide = field(default_factory=list)

    def best_bid(self) -> float:
        if not self.bids: raise Exception("order book bids empty")
        return self.bids[0][0]

    def best_ask(self) -> float:
        if not self.asks: raise Exception("order book asks empty")
        return self.asks[0][0]

    def quote_ask(self) -> float:
        """Ask live; se il token è a 1.00 e non ci sono ask, il mercato è risolto."""
        if self.asks:
            return self.asks[0][0]
        bid = self.best_bid()
        if bid >= 0.99:
            return 1.0
        raise Exception("order book asks empty")

    def replace_side(self, bids_raw: list, asks_raw: list) -> None:
        self.bids = sorted([(float(x["price"]), float(x["size"])) for x in bids_raw], key=lambda t: -t[0])
        self.asks = sorted([(float(x["price"]), float(x["size"])) for x in asks_raw], key=lambda t: t[0])

    def update_level(self, price: float, size: float, side: str) -> None:
        levels = self.bids if side == "BUY" else self.asks
        desc = side == "BUY"
        levels[:] = [(p, s) for p, s in levels if p != price]
        if size > 0: levels.append((price, size))
        levels.sort(key=lambda t: -t[0] if desc else t[0])


@dataclass
class BookSnapshot:
    up_bids: BookSide
    up_asks: BookSide
    down_bids: BookSide
    down_asks: BookSide
    up_bid: float
    up_ask: float
    down_bid: float
    down_ask: float

    def to_bytes(self) -> bytes:
        counts = (len(self.up_bids), len(self.up_asks), len(self.down_bids), len(self.down_asks))
        return struct.pack(BOOK_COUNTS_FMT, *counts) + (
            book_side_to_bytes(self.up_bids) + book_side_to_bytes(self.up_asks)
            + book_side_to_bytes(self.down_bids) + book_side_to_bytes(self.down_asks))

    @staticmethod
    def from_bytes(raw: bytes, offset: int) -> tuple["BookSnapshot", int]:
        n_ub, n_ua, n_db, n_da = struct.unpack(BOOK_COUNTS_FMT, raw[offset:offset + BOOK_COUNTS_SIZE])
        offset += BOOK_COUNTS_SIZE
        up_bids, offset = book_side_from_bytes(raw, offset, n_ub)
        up_asks, offset = book_side_from_bytes(raw, offset, n_ua)
        down_bids, offset = book_side_from_bytes(raw, offset, n_db)
        down_asks, offset = book_side_from_bytes(raw, offset, n_da)
        snap = BookSnapshot(
            up_bids, up_asks, down_bids, down_asks,
            up_bids[0][0] if up_bids else 0.0,
            up_asks[0][0] if up_asks else 1.0,
            down_bids[0][0] if down_bids else 0.0,
            down_asks[0][0] if down_asks else 1.0,
        )
        return snap, offset


def empty_book_snapshot() -> BookSnapshot:
    return BookSnapshot([], [], [], [], QUOTE_NA, QUOTE_NA, QUOTE_NA, QUOTE_NA)
