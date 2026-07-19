"""Test worker process_task (in-process) e RoundBatchRunner cancel."""

from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

from dashv2.batch.runner import BatchCancelled, RoundBatchRunner
from dashv2.batch.worker import process_task
from dashv2.rounds import LoadedRound
from src.book import BookSnapshot

_STUB = """
def on_round_start(ctx): return []
def on_tick(ctx):
    if ctx.get("sec") == 200 and ctx.get("tradable"):
        return [{"cmd": "order.place", "side": "Up", "size_usd": 10.0}]
    return []
def on_round_end(ctx): return []
"""


def _book(up_ask=0.55, down_ask=0.45):
    return BookSnapshot(
        [(up_ask - 0.02, 1000)], [(up_ask, 1000)],
        [(down_ask - 0.02, 1000)], [(down_ask, 1000)],
        up_ask - 0.02, up_ask, down_ask - 0.02, down_ask,
    )


def _tick(sec: int, up_ask=0.55, down_ask=0.45) -> dict:
    up_bid, down_bid = up_ask - 0.02, down_ask - 0.02
    return {
        "sec": sec,
        "chainlink_btc": 90000.0,
        "chainlink_stale": False,
        "up_bid": up_bid, "up_ask": up_ask,
        "down_bid": down_bid, "down_ask": down_ask,
        "delta_usd": 10,
        "partial": False,
        "gap": False,
        "up_mid_c": int(round(((up_bid + up_ask) / 2) * 100)),
        "down_mid_c": int(round(((down_bid + down_ask) / 2) * 100)),
        "majority_side": "Up",
        "vol": {},
        "side_risk": {"Up": {"rq": None, "rs": None}, "Down": {"rq": None, "rs": None}},
        "dwin_a": None,
        "dwin_b_pct": None,
    }


def _synthetic_round() -> LoadedRound:
    mts = 1784469600  # 2026-07-19 14:00:00 UTC
    return LoadedRound(
        market_start_ts=mts,
        market_end_ts=mts + 300,
        fee_rate=0.02,
        ptb_chainlink=89990.0,
        outcome_code=1,
        outcome_name="Up",
        final_chainlink=90100.0,
        ticks_by_sec={200: _tick(200)},
        books_by_sec={200: _book()},
        all_secs=set(range(1, 301)),
    )


class TestProcessTask(unittest.TestCase):
    def test_strategy_in_process(self):
        loaded = _synthetic_round()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "strategy_stub.py"
            path.write_text(_STUB, encoding="utf-8")
            with patch("dashv2.batch.worker.load_bin", return_value=loaded) as mock_load:
                out = process_task({
                    "job": "strategy",
                    "market_start_ts": loaded.market_start_ts,
                    "bin_path": str(Path(td) / "fake.bin"),
                    "data_dir": td,
                    "stall_reconnect_sec": 15.0,
                    "module_path": str(path),
                    "strategy_id": "stub",
                    "size_up": 10.0,
                    "size_down": 10.0,
                    "hour_utc": 14,
                })
        mock_load.assert_called_once()
        self.assertEqual(mock_load.call_args[0][1], 15.0)
        self.assertTrue(out["ok"], out.get("error"))
        self.assertEqual(out["hour_utc"], 14)
        self.assertTrue(out["traded"])
        self.assertEqual(out["n_wins"], 1)
        self.assertGreater(out["pnl_usd"], 0.0)

    def test_process_task_uses_bin_path(self):
        """process_task passa task['bin_path'] a load_bin (niente RoundRepository)."""
        loaded = _synthetic_round()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "strategy_stub.py"
            path.write_text(_STUB, encoding="utf-8")
            bin_path = Path(td) / "btc5m_1784469600_0000.bin"
            with patch("dashv2.batch.worker.load_bin", return_value=loaded) as mock_load:
                out = process_task({
                    "job": "strategy",
                    "market_start_ts": loaded.market_start_ts,
                    "bin_path": str(bin_path),
                    "data_dir": td,
                    "stall_reconnect_sec": 15.0,
                    "module_path": str(path),
                    "strategy_id": "stub",
                    "size_up": 10.0,
                    "size_down": 10.0,
                    "hour_utc": 14,
                })
        mock_load.assert_called_once_with(bin_path, 15.0)
        self.assertTrue(out["ok"], out.get("error"))


class TestRoundBatchRunner(unittest.TestCase):
    def test_run_progress_and_results(self):
        runner = RoundBatchRunner(workers=1)
        tasks = [{"n": i} for i in range(3)]
        progress = []

        def on_progress(done, total, errors):
            progress.append((done, total, errors))

        futs = []
        for i in range(3):
            f = Future()
            f.set_result({"ok": True, "n": i})
            futs.append(f)

        mock_ex = MagicMock()
        mock_ex.submit.side_effect = futs

        with patch("dashv2.batch.runner.ProcessPoolExecutor", return_value=mock_ex), \
             patch("dashv2.batch.runner.as_completed", return_value=futs):
            out = runner.run(tasks, on_progress)

        self.assertEqual(len(out), 3)
        self.assertEqual(progress[-1], (3, 3, 0))
        mock_ex.shutdown.assert_called()

    def test_cancel_raises_without_partial(self):
        runner = RoundBatchRunner(workers=1)
        tasks = [{"n": i} for i in range(3)]

        f0 = Future()
        f0.set_result({"ok": True, "n": 0})
        f1 = Future()
        f1.set_result({"ok": True, "n": 1})
        futs = [f0, f1]

        mock_ex = MagicMock()
        mock_ex.submit.side_effect = [Future(), Future(), Future()]

        def on_progress(done, total, errors):
            runner.cancel()

        with patch("dashv2.batch.runner.ProcessPoolExecutor", return_value=mock_ex), \
             patch("dashv2.batch.runner.as_completed", return_value=futs):
            with self.assertRaises(BatchCancelled):
                runner.run(tasks, on_progress)

        mock_ex.shutdown.assert_called_with(wait=False, cancel_futures=True)

    def test_cancel_before_run_raises_without_pool(self):
        """Cancel durante listing/prep (prima di run) non deve essere azzerato."""
        runner = RoundBatchRunner(workers=1)
        runner.cancel()
        with patch("dashv2.batch.runner.ProcessPoolExecutor") as MockPool:
            with self.assertRaises(BatchCancelled):
                runner.run([{"n": 0}], lambda *a: None)
        MockPool.assert_not_called()


class TestStatsRequestCancel(unittest.TestCase):
    """Cancel ok se _stats_busy anche senza runner ancora assegnato."""

    def _bare_server(self):
        from dashv2.server import ServerBridge
        srv = ServerBridge.__new__(ServerBridge)
        srv._stats_busy = False
        srv._stats_cancel_requested = False
        srv._stats_runner = None
        return srv

    def test_cancel_no_job(self):
        srv = self._bare_server()
        self.assertEqual(srv._stats_request_cancel(), {"error": "no job running"})

    def test_cancel_busy_before_runner(self):
        srv = self._bare_server()
        srv._stats_busy = True
        self.assertEqual(srv._stats_request_cancel(), {"ok": True})
        self.assertTrue(srv._stats_cancel_requested)

    def test_cancel_busy_with_runner(self):
        srv = self._bare_server()
        srv._stats_busy = True
        runner = RoundBatchRunner(workers=1)
        srv._stats_runner = runner
        self.assertEqual(srv._stats_request_cancel(), {"ok": True})
        self.assertTrue(srv._stats_cancel_requested)
        self.assertTrue(runner._cancel)

    def test_prep_cancel_before_run_no_done(self):
        """Simula cancel post-listing: BatchCancelled, niente done con risultati."""
        from dashv2.server import ServerBridge
        srv = ServerBridge.__new__(ServerBridge)
        srv._stats_busy = True
        srv._stats_cancel_requested = False
        runner = RoundBatchRunner(workers=1)
        srv._stats_runner = runner
        emitted = []
        srv._emit_stats = lambda ev, payload: emitted.append((ev, payload))

        srv._stats_request_cancel()
        if srv._stats_cancel_requested:
            runner.cancel()
        with self.assertRaises(BatchCancelled):
            if runner._cancel:
                raise BatchCancelled()
            runner.run([{"n": 0}], lambda *a: None)

        self.assertFalse(any(ev == "stats.job.done" for ev, _ in emitted))


if __name__ == "__main__":
    unittest.main()
