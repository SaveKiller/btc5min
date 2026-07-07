import logging
import sys

from src.convert import format_delta

_sample = logging.getLogger("sample")
_sample.propagate = False
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(message)s"))
_sample.addHandler(_handler)
_sample.setLevel(logging.INFO)


def log_sample(start_ts: int, countdown_sec: int, side: str, majority_ask: float,
        chainlink: float, price_to_beat: float | None) -> None:
    ptb_s = f"{price_to_beat:.2f}" if price_to_beat is not None else "-"
    delta_s = format_delta(chainlink, price_to_beat) if price_to_beat is not None else "-"
    _sample.info(
        "round=%s sec=%3d %s %.2f btc=%.2f ptb=%s delta=%s",
        start_ts, countdown_sec, side.upper(), majority_ask, chainlink, ptb_s, delta_s)
    sys.stderr.flush()


def log_sample_partial(start_ts: int, countdown_sec: int, side: str,
        chainlink: float, price_to_beat: float) -> None:
    delta_s = format_delta(chainlink, price_to_beat)
    _sample.info(
        "round=%s sec=%3d %s --- btc=%.2f ptb=%.2f delta=%s",
        start_ts, countdown_sec, side.upper(), chainlink, price_to_beat, delta_s)
    sys.stderr.flush()
