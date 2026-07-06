import json
import logging
import math
import threading
import time
from pathlib import Path

from src.binary_format import round_filename, write_round
from src.clob_api import enrich_gains, fetch_fee_rate, majority_side
from src.convert import write_round_txt
from src.feed_chainlink import ChainlinkFeed
from src.feed_clob import ClobThread, snapshot_books
from src.market import wait_for_market
from src.round_state import RoundState
from src.sample_log import log_sample
from src.settlement import build_round_header
from src.verify import verify_round

log = logging.getLogger("round")
FINAL_WAIT_SEC = 30.0
_DBG_LOG = Path(__file__).resolve().parent.parent / "debug-9c51e0.log"


def _dbg(location: str, message: str, data: dict, hypothesis_id: str = "P1") -> None:
    # #region agent log
    with open(_DBG_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "sessionId": "9c51e0", "hypothesisId": hypothesis_id, "location": location,
            "message": message, "data": data, "timestamp": int(time.time() * 1000),
        }, default=str) + "\n")
    # #endregion


def countdown_sec(market_end_ts: int) -> int | None:
    secs = market_end_ts - time.time()
    if secs <= 0: return None
    cd = int(math.floor(secs + 0.5))
    if cd < 1 or cd > 300: return None
    return cd


class SamplerThread(threading.Thread):
    def __init__(self, state: RoundState):
        super().__init__(daemon=True, name=f"sampler-{state.start_ts}")
        self.state = state
        self._first_logged = False

    def run(self) -> None:
        while not self.state.stop.is_set() and time.time() < self.state.market_end_ts:
            cd = countdown_sec(self.state.market_end_ts)
            if cd is None or cd == self.state.last_countdown_sec:
                time.sleep(0.05)
                continue
            if not self.state.books_ready():
                # #region agent log
                if cd <= 30 and cd % 10 == 0:
                    _dbg("round_runner.SamplerThread", "books not ready", {
                        "start_ts": self.state.start_ts, "cd": cd,
                    }, hypothesis_id="P2")
                # #endregion
                time.sleep(0.05)
                continue
            if not self.state.chainlink_ready():
                time.sleep(0.05)
                continue
            snap, chainlink, ptb = snapshot_books(self.state)
            side = majority_side(snap.up_bid, snap.up_ask, snap.down_bid, snap.down_ask)
            majority_ask = snap.up_ask if side == "Up" else snap.down_ask
            self.state.buffer.append(
                int(time.time() * 1000), self.state.market_end_ts - time.time(),
                snap.up_bid, snap.up_ask, snap.down_bid, snap.down_ask, chainlink, 0.0)
            self.state.book_snapshots.append(snap)
            self.state.last_countdown_sec = cd
            log_sample(self.state.start_ts, cd, side, majority_ask, chainlink, ptb)
            if not self._first_logged:
                self._first_logged = True
                # #region agent log
                _dbg("round_runner.SamplerThread", "first sample", {
                    "start_ts": self.state.start_ts,
                    "cd": cd,
                    "secs_to_expiry": self.state.market_end_ts - time.time(),
                    "lag_after_start": time.time() - self.state.market_start_ts,
                    "ptb_ready": ptb is not None,
                })
                # #endregion
            time.sleep(0.05)


class RoundRunner(threading.Thread):
    def __init__(self, asset: str, interval: str, out_dir: Path, start_ts: int):
        super().__init__(daemon=True, name=f"round-{start_ts}")
        self.asset = asset
        self.interval = interval
        self.out_dir = out_dir
        self.start_ts = start_ts
        self.price_to_beat: float | None = None
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
        try:
            while time.time() < state.market_start_ts:
                time.sleep(0.05)
            lag = time.time() - state.market_start_ts
            log.info("round %s sampling started (lag=%.2fs)", self.start_ts, lag)
            # #region agent log
            _dbg("round_runner._run_round", "sampler start", {
                "start_ts": self.start_ts, "lag_after_start": lag,
            })
            # #endregion
            sampler = SamplerThread(state)
            sampler.start()
            while time.time() < state.market_end_ts:
                if not ptb_logged and state.price_to_beat is not None:
                    self.price_to_beat = round(state.price_to_beat, 2)
                    ptb_logged = True
                    lag_ptb = (state._ptb_ts_ms - state._ptb_start_ms) / 1000.0
                    log.info("round %s price_to_beat=%.2f (lag=%.2fs)", self.start_ts, self.price_to_beat, lag_ptb)
                    # #region agent log
                    _dbg("round_runner._run_round", "ptb captured", {
                        "start_ts": self.start_ts, "ptb": self.price_to_beat,
                        "lag_ptb_sec": lag_ptb, "sampler_ticks": len(state.buffer),
                    })
                    # #endregion
                time.sleep(0.1)
            state.stop.set()
            sampler.join(timeout=5)
            if state.price_to_beat is None:
                raise Exception(f"chainlink price_to_beat not captured for round {self.start_ts}")
            if self.price_to_beat is None:
                self.price_to_beat = round(state.price_to_beat, 2)
            if len(state.buffer) == 0:
                raise Exception(f"no seconds collected for round {self.start_ts}")
            deadline = time.time() + FINAL_WAIT_SEC
            while time.time() < deadline:
                with state.lock:
                    if state._final_source == "oracle":
                        break
                time.sleep(0.05)
            if state.final_chainlink is None:
                raise Exception(f"chainlink final not captured for round {self.start_ts}")
            lag_final = (state._final_ts_ms - state._final_end_ms) / 1000.0
            final_chainlink = round(state.final_chainlink, 2)
            if state._final_source == "oracle":
                log.info("round %s final_chainlink=%.2f (oracle lag=%.2fs)", self.start_ts, final_chainlink, lag_final)
            else:
                log.info("round %s final_chainlink=%.2f (recv fallback, oracle_lag=%.2fs)",
                    self.start_ts, final_chainlink, lag_final)
            state.chainlink_done.set()
            enrich_gains(state.buffer, state.book_snapshots, state.fee_rate)
            ticks = state.buffer.to_numpy()
            header = build_round_header(
                self.price_to_beat, final_chainlink, state.market_start_ts, state.market_end_ts)
            path = self.out_dir / round_filename(self.asset, self.interval, self.start_ts)
            write_round(str(path), header, ticks)
            write_round_txt(str(path))
            errs = verify_round(str(path))
            for e in errs:
                log.error("round %s verify: %s", self.start_ts, e)
            log.info("round %s done %s seconds outcome=%s file=%s", self.start_ts, len(ticks),
                "Up" if header["outcome"] == 1 else "Down", path.name)
        finally:
            state.stop.set()
            state.chainlink_done.set()
            feed.unregister(state)
            cb.join(timeout=3)
