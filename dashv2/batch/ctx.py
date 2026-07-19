"""Ctx strategy per batch: mirror dei campi di bot_process._ctx."""

from __future__ import annotations


def build_strategy_ctx(
    tick_public: dict,
    session: dict,
    open_orders: list,
    bot_active: bool = True,
) -> dict:
    """Costruisce il dict ctx passato agli hook strategy (allineato al bot live)."""
    return {
        "sec": tick_public.get("sec"),
        "tradable": tick_public.get("tradable"),
        "chainlink_btc": tick_public.get("chainlink_btc"),
        "delta_usd": tick_public.get("delta_usd"),
        "ptb_chainlink": session["ptb_chainlink"],
        "liq2_ask_usd": tick_public.get("liq2_ask_usd"),
        "market_start_ts": session["market_start_ts"],
        "up_ask_c": tick_public.get("up_ask_c"),
        "up_bid_c": tick_public.get("up_bid_c"),
        "down_ask_c": tick_public.get("down_ask_c"),
        "down_bid_c": tick_public.get("down_bid_c"),
        "up_mid_c": tick_public.get("up_mid_c"),
        "down_mid_c": tick_public.get("down_mid_c"),
        "majority_side": tick_public.get("majority_side"),
        "vol": tick_public.get("vol") or {},
        "risk": tick_public.get("risk") or {},
        "dwin_ref_side": tick_public.get("dwin_ref_side"),
        "dwin_a": tick_public.get("dwin_a"),
        "dwin_b": tick_public.get("dwin_b"),
        "open_orders": list(open_orders),
        "bot_active": bot_active,
    }
