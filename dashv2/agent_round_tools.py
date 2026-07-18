"""Helper round per tool AI Agent (summary / tick / list day)."""

from __future__ import annotations

from dashv2.rounds import RoundRepository


class AgentRoundTools:
    """Lettura round dal repository senza passare dalla UI."""

    def __init__(self, repo: RoundRepository) -> None:
        self.repo = repo

    def list_day(self, day_utc: str) -> list[dict]:
        return self.repo.list_picker_day(day_utc)

    def summary(self, market_start_ts: int) -> dict:
        loaded = self.repo.load(market_start_ts)
        return {
            "market_start_ts": loaded.market_start_ts,
            "market_end_ts": loaded.market_end_ts,
            "ptb_chainlink": loaded.ptb_chainlink,
            "fee_rate": loaded.fee_rate,
            "outcome_name": loaded.outcome_name,
            "final_chainlink": loaded.final_chainlink,
            "tick_count": len(loaded.ticks_by_sec),
        }

    def tick(self, market_start_ts: int, sec: int) -> dict:
        loaded = self.repo.load(market_start_ts)
        tick = loaded.ticks_by_sec.get(sec)
        if tick is None:
            raise Exception(f"no tick sec={sec} for {market_start_ts}")
        out = {
            "sec": tick["sec"],
            "chainlink_btc": tick.get("chainlink_btc"),
            "delta_usd": tick.get("delta_usd"),
            "gap": tick.get("gap"),
            "partial": tick.get("partial"),
            "up_bid": tick.get("up_bid"),
            "up_ask": tick.get("up_ask"),
            "down_bid": tick.get("down_bid"),
            "down_ask": tick.get("down_ask"),
            "up_mid_c": tick.get("up_mid_c"),
            "down_mid_c": tick.get("down_mid_c"),
            "majority_side": tick.get("majority_side"),
            "vol": tick.get("vol"),
            "side_risk": tick.get("side_risk"),
            "dwin_a": tick.get("dwin_a"),
            "dwin_b_pct": tick.get("dwin_b_pct"),
        }
        if tick.get("up_ask") is not None:
            out["up_ask_c"] = int(round(tick["up_ask"] * 100))
            out["up_bid_c"] = int(round(tick["up_bid"] * 100))
            out["down_ask_c"] = int(round(tick["down_ask"] * 100))
            out["down_bid_c"] = int(round(tick["down_bid"] * 100))
        return out
