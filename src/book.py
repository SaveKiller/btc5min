from dataclasses import dataclass, field

BookSide = list[tuple[float, float]]


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
