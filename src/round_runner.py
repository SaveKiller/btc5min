import logging
import math
import threading
import time
from pathlib import Path

from src.binary_format import round_bin_path, write_round
from src.book import empty_book_snapshot
from src.clob_api import enrich_gains, fetch_fee_rate, majority_side, side_from_chainlink
from src.convert import write_round_txt
from src.feed_chainlink import ChainlinkFeed
from src.feed_clob import ClobThread, snapshot_books, snapshot_chainlink
from src.gamma_patch import GammaPatchWorker
from src.market import fetch_market_by_slug, poll_gamma_outcome, wait_for_market
from src.round_state import RoundState
from src.sample_log import log_sample, log_sample_partial
from src.settlement import build_round_header, outcome_from_prices
from src.setup import GAMMA_POLL_SEC, OUTCOME_WAIT_SEC
from src.verify import verify_round

log = logging.getLogger("round")


def countdown_sec(market_end_ts: int) -> int | None:
    secs = market_end_ts - time.time()
    if secs <= 0: return None
    cd = int(math.floor(secs + 0.5))
    if cd < 1 or cd > 300: return None
    return cd


def _try_gamma_ptb(asset: str, interval: str, start_ts: int, state: RoundState) -> None:
    if state.ptb_gamma is not None:
        return
    try:
        m = fetch_market_by_slug(asset, interval, start_ts)
        if m["price_to_beat"] is not None:
            state.apply_gamma_ptb(m["price_to_beat"])
    except Exception as e:
        log.warning("round %s gamma ptb poll: %s", start_ts, e)


class SamplerThread(threading.Thread):
    def __init__(self, state: RoundState):
        super().__init__(daemon=True, name=f"sampler-{state.start_ts}")
        self.state = state
        self._last_side: str | None = None

    def run(self) -> None:
        while not self.state.stop.is_set() and time.time() < self.state.market_end_ts:
            cd = countdown_sec(self.state.market_end_ts)
            if cd is None or cd == self.state.last_countdown_sec:
                time.sleep(0.05)
                continue
            if not self.state.chainlink_ready():
                time.sleep(0.05)
                continue
            ptb = self.state.display_ptb()
            if ptb is None:
                time.sleep(0.05)
                continue
            if self.state.books_ready():
                snap, chainlink, _, cl_recv = snapshot_books(self.state)
                side = majority_side(snap.up_bid, snap.up_ask, snap.down_bid, snap.down_ask)
                self._last_side = side
                majority_ask = snap.up_ask if side == "Up" else snap.down_ask
                self.state.buffer.append(
                    int(time.time() * 1000), self.state.market_end_ts - time.time(),
                    snap.up_bid, snap.up_ask, snap.down_bid, snap.down_ask, chainlink, 0.0, cl_recv)
                self.state.book_snapshots.append(snap)
                self.state.last_countdown_sec = cd
                log_sample(self.state.start_ts, cd, side, majority_ask, chainlink, ptb)
            else:
                chainlink, _, cl_recv = snapshot_chainlink(self.state)
                side = self._last_side or side_from_chainlink(chainlink, ptb)
                self.state.buffer.append_partial(
                    int(time.time() * 1000), self.state.market_end_ts - time.time(), chainlink, cl_recv)
                self.state.book_snapshots.append(empty_book_snapshot())
                self.state.last_countdown_sec = cd
                log_sample_partial(self.state.start_ts, cd, side, chainlink, ptb)
            time.sleep(0.05)


class RoundRunner(threading.Thread):
    def __init__(self, asset: str, interval: str, out_dir: Path, start_ts: int):
        super().__init__(daemon=True, name=f"round-{start_ts}")
        self.asset = asset
        self.interval = interval
        self.out_dir = out_dir
        self.start_ts = start_ts
        self._state: RoundState | None = None

    def request_stop(self) -> None:
        if self._state:
            self._state.stop.set()
            self._state.chainlink_done.set()

    def run(self) -> None:
        try:
            self._run_round()
        except Exception:
            log.exception("round %s failed", self.start_ts)

    def _run_round(self) -> None:
        market = wait_for_market(self.asset, self.interval, self.start_ts)
        if time.time() >= market["market_start_ts"]:
            log.info("round %s skipped (already started), next round %s", self.start_ts, market["market_end_ts"])
            return
        fee_rate = fetch_fee_rate(market["condition_id"])
        state = RoundState(
            self.start_ts, market["market_start_ts"], market["market_end_ts"],
            market["up_token_id"], market["down_token_id"], fee_rate)
        self._state = state
        feed = ChainlinkFeed.get()
        feed.register(state)
        cb = ClobThread(state)
        cb.start()
        ptb_logged = False
        next_gamma_poll = 0.0
        try:
            while time.time() < state.market_start_ts:
                time.sleep(0.05)
            lag = time.time() - state.market_start_ts
            log.info("round %s sampling started (lag=%.2fs)", self.start_ts, lag)
            sampler = SamplerThread(state)
            sampler.start()
            while time.time() < state.market_end_ts:
                now = time.time()
                if now >= next_gamma_poll:
                    next_gamma_poll = now + GAMMA_POLL_SEC
                    _try_gamma_ptb(self.asset, self.interval, self.start_ts, state)
                if not ptb_logged and state.ptb_chainlink is not None:
                    ptb_logged = True
                    log.info("round %s ptb_chainlink=%.2f", self.start_ts, round(state.ptb_chainlink, 2))
                time.sleep(0.1)
            state.stop.set()
            sampler.join(timeout=5)
            state.ensure_final_chainlink()
            state.ensure_ptb_chainlink()
            if len(state.buffer) == 0:
                raise Exception(f"no seconds collected for round {self.start_ts}")
            deadline = state.market_end_ts + OUTCOME_WAIT_SEC
            poll_gamma_outcome(self.asset, self.interval, self.start_ts, state, deadline)
            warnings: list[str] = []
            if not state.gamma_outcome:
                warnings.append("outcome from chainlink provisional, not gamma")
            if state.ptb_gamma is None:
                warnings.append("ptb_gamma missing at write")
            ptb_cl, final_cl = state.require_chainlink_prices()
            if state.gamma_outcome:
                computed = outcome_from_prices(final_cl, ptb_cl)
                if computed != state.gamma_outcome:
                    warnings.append(f"outcome mismatch gamma={state.gamma_outcome} computed={computed}")
            log.info("round %s final_chainlink=%.2f ptb_chainlink=%.2f outcome=%s",
                self.start_ts, final_cl, ptb_cl, state.gamma_outcome or "computed")
            state.chainlink_done.set()
            enrich_gains(state.buffer, state.book_snapshots, state.fee_rate)
            ticks = state.buffer.to_numpy()
            header = build_round_header(state.market_start_ts, state.market_end_ts, state.fee_rate, ticks, state)
            bin_path = round_bin_path(self.out_dir, self.asset, self.interval, self.start_ts)
            write_round(str(bin_path), header, ticks, state.book_snapshots)
            write_round_txt(str(bin_path), warnings)
            GammaPatchWorker.get().enqueue(
                self.asset, self.interval, self.start_ts, str(bin_path), state.market_end_ts)
            errs = verify_round(str(bin_path))
            for e in errs:
                log.error("round %s verify: %s", self.start_ts, e)
            log.info("round %s done %s seconds outcome=%s file=%s", self.start_ts, len(ticks),
                "Up" if header["outcome"] == 1 else "Down", bin_path.name)
        finally:
            state.stop.set()
            state.chainlink_done.set()
            feed.unregister(state)
            cb.join(timeout=3)
