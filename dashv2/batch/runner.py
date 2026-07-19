"""Pool parallelo per job batch Stats (strategy / analyze)."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed

from dashv2.batch.worker import process_task


class BatchCancelled(Exception):
    """Job batch interrotto via cancel(); niente reduce su risultati parziali."""


class RoundBatchRunner:
    def __init__(self, workers: int):
        self.workers = workers
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self, tasks: list[dict], on_progress) -> list[dict]:
        """Esegue tasks in ProcessPool; on_progress(done, total, errors). Raise BatchCancelled se cancel."""
        # Non resettare _cancel qui: un cancel durante listing/prep deve restare valido.
        if self._cancel:
            raise BatchCancelled()
        total = len(tasks)
        results: list[dict] = []
        done = 0
        errors = 0
        executor = ProcessPoolExecutor(max_workers=self.workers)
        try:
            futs = [executor.submit(process_task, t) for t in tasks]
            for fut in as_completed(futs):
                if self._cancel:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise BatchCancelled()
                r = fut.result()
                results.append(r)
                done += 1
                if not r["ok"]:
                    errors += 1
                on_progress(done, total, errors)
            return results
        finally:
            if not self._cancel:
                executor.shutdown(wait=True)
