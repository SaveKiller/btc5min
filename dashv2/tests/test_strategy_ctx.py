"""Test candles_5m nel ctx strategy (batch + helper)."""

from __future__ import annotations

import unittest

from dashv2.batch.ctx import build_candles_5m, build_strategy_ctx
from dashv2.rounds import LoadedRound, round_candle_ohlc


def _loaded(mts: int = 1784469900) -> LoadedRound:
    return LoadedRound(
        market_start_ts=mts,
        market_end_ts=mts + 300,
        fee_rate=0.02,
        ptb_chainlink=100.0,
        outcome_code=1,
        outcome_name="Up",
        final_chainlink=101.0,
        ticks_by_sec={
            300: {"chainlink_btc": 100.0, "chainlink_stale": False},
            200: {"chainlink_btc": 102.0, "chainlink_stale": False},
            100: {"chainlink_btc": 99.0, "chainlink_stale": False},
        },
        books_by_sec={},
        all_secs=set(range(1, 301)),
    )


class TestStrategyCtx(unittest.TestCase):
    def test_round_candle_ohlc_causal(self):
        loaded = _loaded()
        c300 = round_candle_ohlc(loaded, 300)
        self.assertEqual(c300["time"], loaded.market_start_ts)
        self.assertEqual(c300["open"], 100.0)
        self.assertEqual(c300["close"], 100.0)
        c200 = round_candle_ohlc(loaded, 200)
        self.assertEqual(c200["close"], 102.0)
        self.assertEqual(c200["high"], 102.0)
        c100 = round_candle_ohlc(loaded, 100)
        self.assertEqual(c100["low"], 99.0)

    def test_build_candles_5m_prev_plus_current(self):
        loaded = _loaded()
        prev = [
            {"time": 1784469600, "open": 90.0, "high": 95.0, "low": 89.0, "close": 94.0},
        ]
        out = build_candles_5m(prev, loaded, 200)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["time"], 1784469600)
        self.assertEqual(out[1]["time"], loaded.market_start_ts)
        self.assertEqual(out[1]["close"], 102.0)

    def test_build_strategy_ctx_requires_candles_5m(self):
        tick = {
            "sec": 200, "tradable": True, "chainlink_btc": 100.0, "delta_usd": 1,
            "liq2_ask_usd": None, "up_ask_c": 55, "up_bid_c": 53, "down_ask_c": 45, "down_bid_c": 43,
            "up_mid_c": 54, "down_mid_c": 44, "majority_side": "Up", "vol": {}, "risk": {},
            "dwin_ref_side": None, "dwin_a": None, "dwin_b": None,
            "candles_5m": [{"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}],
        }
        session = {"ptb_chainlink": 99.0, "market_start_ts": 1784469900}
        ctx = build_strategy_ctx(tick, session, [], bot_active=True)
        self.assertEqual(ctx["candles_5m"][0]["close"], 1.5)
        self.assertEqual(ctx["market_start_ts"], 1784469900)


if __name__ == "__main__":
    unittest.main()
