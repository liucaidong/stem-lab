"""R03.52.2 bounded in-process Worker poller pool.

Durable scheduling remains the responsibility of the Store claim transaction;
this module does not implement a distributed scheduler or tenant fairness.
"""
from __future__ import annotations
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Callable, Sequence
from runtime.worker_runtime import WorkerRuntime


class WorkerPool:
    def __init__(self, *, runtime_factory: Callable[[int], WorkerRuntime],
                 concurrency: int, monitor_interval_seconds: float = 0.05) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least one")
        if monitor_interval_seconds <= 0:
            raise ValueError("monitor interval must be positive")
        self.concurrency = concurrency
        self.monitor_interval_seconds = monitor_interval_seconds
        self._shutdown = Event()
        self._runtimes: list[WorkerRuntime] = [
            runtime_factory(slot) for slot in range(concurrency)
        ]
        worker_ids = [runtime.worker_id for runtime in self._runtimes]
        if len(set(worker_ids)) != len(worker_ids):
            raise ValueError("runtime_factory must provide a unique worker_id per slot")

    def request_shutdown(self) -> None:
        self._shutdown.set()
        for runtime in self._runtimes:
            runtime.request_shutdown()

    def run(self) -> None:
        if self._shutdown.is_set():
            return
        with ThreadPoolExecutor(max_workers=self.concurrency,
                                thread_name_prefix="stemlab-worker") as executor:
            futures: Sequence[Future[None]] = [
                executor.submit(runtime.run_forever) for runtime in self._runtimes
            ]
            try:
                while not self._shutdown.wait(self.monitor_interval_seconds):
                    for future in futures:
                        if future.done():
                            error = future.exception()
                            self.request_shutdown()
                            if error is not None:
                                raise error
                            raise RuntimeError("worker poller exited before shutdown")
            finally:
                self.request_shutdown()
                for future in futures:
                    future.result()
