from src.binary_format import OUTCOME_FROM_NAME


def outcome_from_prices(final: float, ptb: float) -> str:
    return "Up" if final >= ptb else "Down"


def build_round_header(
    price_to_beat: float,
    final_chainlink: float,
    market_start_ts: int,
    market_end_ts: int,
) -> dict:
    if price_to_beat is None:
        raise Exception("gamma priceToBeat missing")
    if final_chainlink is None:
        raise Exception("final_chainlink missing")
    outcome = outcome_from_prices(final_chainlink, price_to_beat)
    return {
        "market_start_ts": market_start_ts,
        "market_end_ts": market_end_ts,
        "price_to_beat": price_to_beat,
        "outcome": OUTCOME_FROM_NAME[outcome],
        "final_chainlink": final_chainlink,
    }
