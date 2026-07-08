from src.binary_format import OUTCOME_FROM_NAME


def outcome_from_prices(final: float, ptb: float) -> str:
    return "Up" if final >= ptb else "Down"


def build_round_header(
    market_start_ts: int, market_end_ts: int, fee_rate: float, ticks, state,
) -> dict:
    ptb_chainlink, final_chainlink = state.require_chainlink_prices()
    if state.gamma_outcome:
        outcome = OUTCOME_FROM_NAME[state.gamma_outcome]
    else:
        outcome = OUTCOME_FROM_NAME[outcome_from_prices(final_chainlink, ptb_chainlink)]
    ptb_gamma = float("nan") if state.ptb_gamma is None else round(state.ptb_gamma, 2)
    return {
        "market_start_ts": market_start_ts,
        "market_end_ts": market_end_ts,
        "outcome": outcome,
        "tick_count": len(ticks),
        "fee_rate": fee_rate,
        "ptb_price": round(float(ticks[0, 6]), 2),
        "ptb_chainlink": round(ptb_chainlink, 2),
        "ptb_gamma": ptb_gamma,
        "final_price": round(float(ticks[-1, 6]), 2),
        "final_chainlink": round(final_chainlink, 2),
        "final_gamma": float("nan"),
    }
