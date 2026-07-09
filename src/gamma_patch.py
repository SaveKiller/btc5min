import logging
import math
import threading
import time

from src.binary_format import patch_final_gamma, patch_ptb_gamma, read_round, txt_path_for_bin
from src.convert import read_txt_warnings, write_round_txt
from src.market import fetch_market_by_slug
from src.setup import GAMMA_PATCH_WAIT_SEC, GAMMA_POLL_SEC

log = logging.getLogger("gamma_patch")


class GammaPatchWorker:
    _instance: "GammaPatchWorker | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "GammaPatchWorker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._queue: list[dict] = []
        self._queue_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="gamma-patch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def enqueue(self, asset: str, interval: str, start_ts: int, bin_path: str, market_end_ts: int) -> None:
        with self._queue_lock:
            for job in self._queue:
                if job["bin_path"] == bin_path:
                    return
            self._queue.append({
                "asset": asset, "interval": interval, "start_ts": start_ts,
                "bin_path": bin_path, "market_end_ts": market_end_ts,
            })

    def _run(self) -> None:
        while not self._stop.is_set():
            job = None
            with self._queue_lock:
                if self._queue:
                    job = self._queue[0]
            if job is None:
                time.sleep(0.5)
                continue
            if self._process(job):
                with self._queue_lock:
                    if self._queue and self._queue[0] is job:
                        self._queue.pop(0)
            else:
                time.sleep(GAMMA_POLL_SEC)

    def _process(self, job: dict) -> bool:
        deadline = job["market_end_ts"] + GAMMA_PATCH_WAIT_SEC
        if time.time() >= deadline:
            log.warning("round %s gamma patch timeout", job["start_ts"])
            return True
        try:
            header, _, _ = read_round(job["bin_path"])
        except Exception as e:
            log.warning("round %s patch read failed: %s", job["start_ts"], e)
            return True
        need_final = math.isnan(header["final_gamma"])
        need_ptb = math.isnan(header["ptb_gamma"])
        if not need_final and not need_ptb:
            return True
        try:
            m = fetch_market_by_slug(job["asset"], job["interval"], job["start_ts"])
        except Exception as e:
            log.warning("round %s gamma patch poll: %s", job["start_ts"], e)
            return False
        patched = False
        if need_ptb and m["price_to_beat"] is not None:
            patch_ptb_gamma(job["bin_path"], round(m["price_to_beat"], 2))
            log.info("round %s ptb_gamma patched %.2f", job["start_ts"], m["price_to_beat"])
            patched = True
        if need_final and m["final_chainlink"] is not None:
            patch_final_gamma(job["bin_path"], round(m["final_chainlink"], 2))
            log.info("round %s final_gamma patched %.2f", job["start_ts"], m["final_chainlink"])
            patched = True
        if patched:
            txt = str(txt_path_for_bin(job["bin_path"]))
            write_round_txt(job["bin_path"], read_txt_warnings(txt))
        if not need_final or m["final_chainlink"] is not None:
            if not need_ptb or m["price_to_beat"] is not None:
                return True
        return False
