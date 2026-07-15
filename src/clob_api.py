import httpx

from src.book import BookSide

# Puntata simbolica per walk sul book (come UI Polymarket "To win" su $100).
BET_USD = 100.0
_client = httpx.Client(timeout=10.0)


def side_from_chainlink(chainlink: float, price_to_beat: float) -> str:
    return "Up" if chainlink >= price_to_beat else "Down"


def majority_side(up_bid: float, up_ask: float, down_bid: float, down_ask: float) -> str:
    up_mid = (up_bid + up_ask) / 2
    down_mid = (down_bid + down_ask) / 2
    return "Up" if up_mid >= down_mid else "Down"


def _resolve_asks(asks: BookSide, quote_ask: float | None) -> BookSide:
    if asks:
        return asks
    if quote_ask is None or quote_ask < 0.99:
        raise Exception("order book asks empty")
    return [(quote_ask, 1_000_000.0)]


def _resolve_bids(bids: BookSide, quote_bid: float | None) -> BookSide:
    if bids:
        return bids
    if quote_bid is None or quote_bid <= 0.01:
        raise Exception("order book bids empty")
    return [(quote_bid, 1_000_000.0)]


def market_buy_walk(asks: BookSide, amount_usd: float, fee_rate: float, quote_ask: float | None = None) -> dict:
    """Walk BUY fee-included su amount_usd. All-or-nothing: budget residuo > 1e-9 → eccezione."""
    asks = _resolve_asks(asks, quote_ask)
    B = amount_usd
    total_shares = 0.0
    total_fee = 0.0
    total_cost = 0.0
    for p, size in sorted(asks, key=lambda t: t[0]):
        if B <= 1e-9: break
        cost = size * p
        fee = size * fee_rate * p * (1.0 - p)
        if cost + fee <= B + 1e-9:
            total_shares += size
            total_fee += fee
            total_cost += cost
            B -= cost + fee
        else:
            denom = p * (1.0 + fee_rate * (1.0 - p))
            c = B / denom
            if c > size: c = size
            fee = c * fee_rate * p * (1.0 - p)
            total_shares += c
            total_fee += fee
            total_cost += c * p
            B = 0.0
    if B > 1e-6:
        raise Exception(f"insufficient ask liquidity for ${amount_usd:.2f}, unfilled ${B:.4f}")
    avg_price = total_cost / total_shares if total_shares > 0 else 0.0
    return {"shares": total_shares, "avg_price": avg_price, "total_cost": total_cost, "total_fee": total_fee}


def market_sell_walk(bids: BookSide, shares: float, fee_rate: float, quote_bid: float | None = None) -> dict:
    """Walk SELL di shares sui bid; fee dedotta dal proceeds."""
    if shares <= 0: raise Exception(f"invalid sell shares: {shares}")
    bids = _resolve_bids(bids, quote_bid)
    remaining = shares
    proceeds = 0.0
    total_fee = 0.0
    sold = 0.0
    for p, size in sorted(bids, key=lambda t: -t[0]):
        if remaining <= 1e-9: break
        c = min(size, remaining)
        fee = c * fee_rate * p * (1.0 - p)
        proceeds += c * p - fee
        total_fee += fee
        sold += c
        remaining -= c
    if remaining > 1e-6:
        raise Exception(f"insufficient bid liquidity for {shares:.4f} shares, unsold {remaining:.4f}")
    avg_price = (proceeds + total_fee) / sold if sold > 0 else 0.0
    return {"proceeds_usd": proceeds, "total_fee": total_fee, "avg_price": avg_price, "shares_sold": sold}


def market_buy_gain(asks: BookSide, amount_usd: float, fee_rate: float, quote_ask: float | None = None) -> float:
    """ROI frazionario su amount_usd: (payout / amount_usd) - 1. Payout = share ricevute ($1 ciascuna se vinci).
    Es. spendi $100, incassi $140 → ritorna 0.40 (40% nel .txt)."""
    asks = _resolve_asks(asks, quote_ask)
    B = amount_usd
    total_shares = 0.0
    for p, size in sorted(asks, key=lambda t: t[0]):
        if B <= 0: break
        cost = size * p
        fee = size * fee_rate * p * (1.0 - p)
        if cost + fee <= B:
            total_shares += size
            B -= cost + fee
        else:
            denom = p * (1.0 + fee_rate * (1.0 - p))
            c = B / denom
            if c > size: c = size
            total_shares += c
            B = 0.0
    payout_usd = total_shares
    return payout_usd / amount_usd - 1.0


def enrich_gains(buffer, book_snapshots: list, fee_rate: float) -> None:
    if len(buffer) != len(book_snapshots):
        raise Exception(f"buffer/snapshots length mismatch: {len(buffer)} vs {len(book_snapshots)}")
    from src.book import tick_quotes_missing
    for i in range(len(buffer)):
        row = buffer.row(i)
        if tick_quotes_missing(row):
            continue
        side = majority_side(row[2], row[3], row[4], row[5])
        snap = book_snapshots[i]
        if side == "Up":
            asks, quote = snap.up_asks, row[3]
        else:
            asks, quote = snap.down_asks, row[5]
        buffer.set_gain(i, market_buy_gain(asks, BET_USD, fee_rate, quote_ask=quote))


GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


def fetch_fee_rate(condition_id: str) -> float:
    r = _client.get(GAMMA_MARKETS_URL, params={"condition_ids": condition_id})
    r.raise_for_status()
    data = r.json()
    if not data: raise Exception(f"gamma market not found for condition {condition_id}")
    m = data[0]
    if not m.get("feesEnabled"): raise Exception(f"feesEnabled false for condition {condition_id}")
    sched = m.get("feeSchedule")
    if not sched or sched.get("rate") is None:
        raise Exception(f"feeSchedule.rate missing for condition {condition_id}")
    return float(sched["rate"])
