import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from src.market import INTERVAL_SECS, current_round_start_ts
from src.feed_chainlink import ChainlinkFeed
from src.gamma_patch import GammaPatchWorker
from src.round_runner import RoundRunner
from src.setup import PREP_AHEAD_SEC
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logging.getLogger("websocket").setLevel(logging.CRITICAL)
log = logging.getLogger("main")


def run_forever(asset: str, interval: str, out_dir: Path, spawned: dict[int, RoundRunner]) -> None:
    step = INTERVAL_SECS[interval]
    attempted: set[int] = set()
    while True:
        now = time.time()
        base = int(now) // step * step
        for start_ts in (base, base + step):
            if start_ts in attempted: continue
            if now < start_ts - PREP_AHEAD_SEC: continue
            if now >= start_ts + step: continue
            runner = RoundRunner(asset, interval, out_dir, start_ts)
            runner.start()
            spawned[start_ts] = runner
            attempted.add(start_ts)
            log.info("orchestrator spawn round %s", start_ts)
        for ts in list(spawned):
            if not spawned[ts].is_alive(): del spawned[ts]
        attempted = {ts for ts in attempted if now < ts + step + 60}
        time.sleep(0.5)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--asset", default="btc")
    p.add_argument("--interval", default="5m")
    p.add_argument("--out", default=None)
    p.add_argument("--once", action="store_true")
    p.add_argument("--start-ts", type=int)
    args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.out) if args.out else root / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    spawned: dict[int, RoundRunner] = {}

    def shutdown(signum, frame):
        for runner in spawned.values():
            runner.request_stop()
        GammaPatchWorker.get().stop()
        ChainlinkFeed.get().stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if args.interval not in INTERVAL_SECS:
        raise Exception(f"unsupported interval: {args.interval}")
    feed = ChainlinkFeed.get()
    feed.configure(args.asset)
    feed.start()
    GammaPatchWorker.get()
    log.info("collector start asset=%s interval=%s out=%s", args.asset, args.interval, out_dir)

    try:
        if args.once:
            start_ts = args.start_ts if args.start_ts is not None else current_round_start_ts(args.interval)
            runner = RoundRunner(args.asset, args.interval, out_dir, start_ts)
            spawned[start_ts] = runner
            runner.start()
            runner.join()
        else:
            run_forever(args.asset, args.interval, out_dir, spawned)
    except SystemExit:
        pass
    finally:
        GammaPatchWorker.get().stop()
        feed.stop()


if __name__ == "__main__":
    main()
