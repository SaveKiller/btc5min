from src.binary_format import OUTCOME_FROM_NAME
from src.setup import price_decimals, round_price


def outcome_from_prices(final: float, ptb: float) -> str:
    return "Up" if final >= ptb else "Down"


def build_round_header(
    market_start_ts: int, market_end_ts: int, fee_rate: float, ticks, state, asset: str,
) -> dict:
    ptb_chainlink, final_chainlink = state.require_chainlink_prices()
    if state.gamma_outcome:
        outcome = OUTCOME_FROM_NAME[state.gamma_outcome]
    else:
        outcome = OUTCOME_FROM_NAME[outcome_from_prices(final_chainlink, ptb_chainlink)]
    nd = price_decimals(asset)
    ptb_gamma = float("nan") if state.ptb_gamma is None else round(state.ptb_gamma, nd)
    return {
        "market_start_ts": market_start_ts,
        "market_end_ts": market_end_ts,
        "outcome": outcome,
        "tick_count": len(ticks),
        "fee_rate": fee_rate,
        "ptb_price": round_price(ticks[0, 6], asset),
        "ptb_chainlink": round_price(ptb_chainlink, asset),
        "ptb_gamma": ptb_gamma,
        "final_price": round_price(ticks[-1, 6], asset),
        "final_chainlink": round_price(final_chainlink, asset),
        "final_gamma": float("nan"),
    }
