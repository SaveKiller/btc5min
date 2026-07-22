"""Motore ordini replay: BUY walk, MTM bid walk, close, settlement."""

from __future__ import annotations

from uuid import uuid4

from src.book import BookSnapshot
from src.clob_api import market_buy_walk, market_sell_walk


class OrderEngine:
    def __init__(self, default_size_up: float, default_size_down: float) -> None:
        self.size_up_usd = default_size_up
        self.size_down_usd = default_size_down
        self.open_orders: list[dict] = []
        self.closed_orders: list[dict] = []

    def clear_positions(self) -> None:
        self.open_orders.clear()
        self.closed_orders.clear()

    def reset(self, default_size_up: float, default_size_down: float) -> None:
        self.size_up_usd = default_size_up
        self.size_down_usd = default_size_down
        self.open_orders.clear()
        self.closed_orders.clear()

    def set_size(self, side: str, size_usd: float) -> None:
        if size_usd <= 0: raise Exception(f"invalid size_usd: {size_usd}")
        if side == "Up": self.size_up_usd = size_usd
        elif side == "Down": self.size_down_usd = size_usd
        else: raise Exception(f"invalid side: {side!r}")

    def preview(self, side: str, size_usd: float, sec: int, tick: dict, book: BookSnapshot, fee_rate: float) -> dict:
        if tick.get("gap") or tick.get("partial"):
            raise Exception(f"tick not tradable sec={sec}")
        asks, entry_ask = self._side_asks(side, tick, book)
        walk = market_buy_walk(asks, size_usd, fee_rate, quote_ask=entry_ask)
        roi = walk["shares"] / size_usd - 1.0
        payout = walk["shares"]
        return {
            "side": side, "size_usd": size_usd, "sec": sec, "best_ask_c": int(round(entry_ask * 100)),
            "avg_price": walk["avg_price"], "shares": walk["shares"], "fee_usd": walk["total_fee"],
            "roi_if_win": roi, "payout_if_win_usd": payout, "profit_if_win_usd": payout - size_usd,
        }

    def place(self, side: str, size_usd: float, sec: int, tick: dict, book: BookSnapshot, fee_rate: float, account_id: str, source: str, strategy_id: str | None = None, reason: str | None = None) -> dict:
        if source not in ("user", "bot"):
            raise Exception(f"invalid order source: {source!r}")
        if source == "bot" and not strategy_id:
            raise Exception("bot order requires strategy_id")
        preview = self.preview(side, size_usd, sec, tick, book, fee_rate)
        entry = self._entry_ctx(side, sec, tick)
        order = {
            "id": uuid4().hex[:12], "account_id": account_id, "source": source,
            "strategy_id": strategy_id, "side": side, "entry_sec": entry["sec"],
            "entry_delta_usd": entry["delta_usd"], "entry_quote": entry["quote"],
            "size_usd": size_usd, "shares": preview["shares"], "entry_btc": tick["chainlink_btc"],
            "best_ask": preview["avg_price"], "best_ask_c": preview["best_ask_c"],
            "avg_entry_price": preview["avg_price"], "entry_fee_usd": preview["fee_usd"],
            "payout_if_win_usd": preview["payout_if_win_usd"], "profit_if_win_usd": preview["profit_if_win_usd"],
            "mtm_usd": None, "mtm_available": False, "close_enabled": False,
            "reason": reason,
        }
        self.open_orders.append(order)
        return order

    def close(self, order_id: str, sec: int, tick: dict, book: BookSnapshot, fee_rate: float, reason: str | None = None) -> dict:
        order = self._find_open(order_id)
        if tick.get("gap") or tick.get("partial"):
            raise Exception(f"tick not tradable for close sec={sec}")
        mtm = self._mtm(order, tick, book, fee_rate)
        if not mtm["mtm_available"]:
            raise Exception(f"cannot close order {order_id}: insufficient bid liquidity")
        exit_ctx = self._exit_ctx(order["side"], sec, tick)
        closed = {
            **order, "exit_sec": exit_ctx["sec"], "exit_delta_usd": exit_ctx["delta_usd"],
            "exit_quote": exit_ctx["quote"], "exit_btc": tick["chainlink_btc"],
            "exit_price": mtm["avg_exit_price"], "exit_fee_usd": mtm["exit_fee_usd"],
            "proceeds_usd": mtm["proceeds_usd"], "pnl_usd": mtm["proceeds_usd"] - order["size_usd"],
            "result": "closed", "close_type": "manual",
            "close_reason": reason if reason is not None else ("manual" if order.get("source") == "user" else order.get("reason")),
        }
        self.open_orders = [o for o in self.open_orders if o["id"] != order_id]
        self.closed_orders.append(closed)
        return closed

    def cancel(self, order_id: str) -> dict:
        order = self._find_open(order_id)
        self.open_orders = [o for o in self.open_orders if o["id"] != order_id]
        return order

    def settle_open(self, outcome: str, sec: int, final_btc: float, tick: dict | None = None, ptb_chainlink: float | None = None) -> list[dict]:
        settled: list[dict] = []
        for order in list(self.open_orders):
            won = outcome == order["side"]
            pnl = order["profit_if_win_usd"] if won else -order["size_usd"]
            exit_ctx = self._exit_ctx(order["side"], sec, tick, settlement_won=won, final_btc=final_btc, ptb_chainlink=ptb_chainlink)
            settled.append({
                **order, "exit_sec": exit_ctx["sec"], "exit_delta_usd": exit_ctx["delta_usd"],
                "exit_quote": exit_ctx["quote"], "exit_btc": final_btc,
                "exit_price": 1.0 if won else 0.0, "exit_fee_usd": 0.0,
                "proceeds_usd": order["payout_if_win_usd"] if won else 0.0,
                "pnl_usd": pnl, "result": "won" if won else "lost", "close_type": "settlement",
            })
        self.closed_orders.extend(settled)
        self.open_orders.clear()
        return settled

    def revalue_mtm(self, sec: int, tick: dict, book: BookSnapshot, fee_rate: float) -> None:
        for order in self.open_orders:
            mtm = self._mtm(order, tick, book, fee_rate)
            order["mtm_usd"] = mtm["mtm_usd"]
            order["mtm_available"] = mtm["mtm_available"]
            order["close_enabled"] = mtm["mtm_available"] and not tick.get("gap") and not tick.get("partial")

    def preview_snapshot(self, sec: int, tick: dict, book: BookSnapshot, fee_rate: float) -> dict:
        snap = self.snapshot()
        if tick.get("gap") or tick.get("partial"):
            return snap
        open_preview = []
        for order in self.open_orders:
            o = dict(order)
            mtm = self._mtm(order, tick, book, fee_rate)
            o["mtm_usd"] = mtm["mtm_usd"]
            o["mtm_available"] = mtm["mtm_available"]
            o["close_enabled"] = mtm["mtm_available"] and order["entry_sec"] <= sec
            open_preview.append(o)
        return {**snap, "open": open_preview}

    def prune_seek(self, sec: int) -> None:
        """Seek: elimina ordini non ancora aperti; riapre close manuali tra entry e exit."""
        self.open_orders = [o for o in self.open_orders if o["entry_sec"] >= sec]
        revived: list[dict] = []
        kept_closed: list[dict] = []
        for c in self.closed_orders:
            if c.get("close_type") != "manual":
                kept_closed.append(c)
                continue
            if c["exit_sec"] >= sec:
                # Chiusura già avvenuta rispetto al cursore → resta closed.
                kept_closed.append(c)
                continue
            if c["entry_sec"] >= sec:
                # Tra entry e exit → riapri con i dati originari.
                base = {k: v for k, v in c.items() if k not in (
                    "exit_sec", "exit_delta_usd", "exit_quote", "exit_btc", "exit_price", "exit_fee_usd",
                    "proceeds_usd", "pnl_usd", "result", "close_type", "close_reason",
                )}
                base["mtm_usd"] = None
                base["mtm_available"] = False
                base["close_enabled"] = False
                revived.append(base)
            # else: cursore prima di entry → elimina del tutto
        self.open_orders.extend(revived)
        self.closed_orders = kept_closed

    def snapshot(self) -> dict:
        return {
            "size_up_usd": self.size_up_usd, "size_down_usd": self.size_down_usd,
            "open": list(self.open_orders), "closed": list(self.closed_orders),
        }

    def _find_open(self, order_id: str) -> dict:
        for o in self.open_orders:
            if o["id"] == order_id: return o
        raise Exception(f"open order not found: {order_id}")

    def _entry_ctx(self, side: str, sec: int, tick: dict) -> dict:
        return {
            "sec": sec,
            "delta_usd": float(tick["delta_usd"]) if tick.get("delta_usd") is not None else None,
            "quote": self._side_ask_quote(side, tick),
        }

    def _exit_ctx(self, side: str, sec: int, tick: dict | None, *, settlement_won: bool | None = None,
                  final_btc: float | None = None, ptb_chainlink: float | None = None) -> dict:
        if settlement_won is not None:
            quote = 1.0 if settlement_won else 0.0
        elif tick is not None:
            quote = self._side_bid_quote(side, tick)
        else:
            quote = None
        delta = None
        if tick is not None and tick.get("delta_usd") is not None:
            delta = float(tick["delta_usd"])
        elif final_btc is not None and ptb_chainlink is not None:
            delta = float(final_btc) - float(ptb_chainlink)
        return {"sec": sec, "delta_usd": delta, "quote": quote}

    def _side_ask_quote(self, side: str, tick: dict) -> float | None:
        if side == "Up":
            q = tick.get("up_ask")
        elif side == "Down":
            q = tick.get("down_ask")
        else:
            raise Exception(f"invalid side: {side!r}")
        return float(q) if q is not None else None

    def _side_bid_quote(self, side: str, tick: dict) -> float | None:
        if side == "Up":
            q = tick.get("up_bid")
        elif side == "Down":
            q = tick.get("down_bid")
        else:
            raise Exception(f"invalid side: {side!r}")
        return float(q) if q is not None else None

    def _side_asks(self, side: str, tick: dict, book: BookSnapshot) -> tuple[list, float]:
        if side == "Up":
            return book.up_asks, float(tick["up_ask"])
        if side == "Down":
            return book.down_asks, float(tick["down_ask"])
        raise Exception(f"invalid side: {side!r}")

    def _side_bids(self, side: str, tick: dict, book: BookSnapshot) -> tuple[list, float | None]:
        if side == "Up":
            return book.up_bids, tick["up_bid"]
        if side == "Down":
            return book.down_bids, tick["down_bid"]
        raise Exception(f"invalid side: {side!r}")

    def _settlement_pnl_if_certain(self, order: dict, tick: dict, book: BookSnapshot) -> float | None:
        """PnL a settlement quando il mercato è deciso ma non c'è liquidità bid per chiudere."""
        if tick.get("gap") or tick.get("partial"):
            return None
        maj = tick.get("majority_side")
        if maj not in ("Up", "Down"):
            return None

        def side_mid(side: str) -> float | None:
            if side == "Up":
                b, a = tick.get("up_bid"), tick.get("up_ask")
            else:
                b, a = tick.get("down_bid"), tick.get("down_ask")
            if b is None or a is None:
                return None
            return (float(b) + float(a)) / 2.0

        win_mid = side_mid(maj)
        if win_mid is None or win_mid < 0.97:
            return None
        lose = "Down" if maj == "Up" else "Up"
        lose_mid = side_mid(lose)
        if lose_mid is not None and lose_mid > 0.05:
            return None
        my_bids, _ = self._side_bids(order["side"], tick, book)
        if my_bids and win_mid < 0.99:
            return None
        if order["side"] == maj:
            return float(order["profit_if_win_usd"])
        return -float(order["size_usd"])

    def _mtm(self, order: dict, tick: dict, book: BookSnapshot, fee_rate: float) -> dict:
        est = self._settlement_pnl_if_certain(order, tick, book)
        if est is not None:
            return {
                "mtm_usd": est, "mtm_available": False,
                "proceeds_usd": None, "avg_exit_price": None, "exit_fee_usd": None,
            }
        bids, quote_bid = self._side_bids(order["side"], tick, book)
        try:
            sell = market_sell_walk(bids, order["shares"], fee_rate, quote_bid=quote_bid)
            proceeds = sell["proceeds_usd"]
            return {
                "mtm_usd": proceeds - order["size_usd"], "mtm_available": True,
                "proceeds_usd": proceeds, "avg_exit_price": sell["avg_price"], "exit_fee_usd": sell["total_fee"],
            }
        except Exception:
            return {"mtm_usd": None, "mtm_available": False, "proceeds_usd": None, "avg_exit_price": None, "exit_fee_usd": None}
