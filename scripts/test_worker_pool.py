#!/usr/bin/env python3
"""R03.52.2 bounded Worker pool supervisor tests."""
from __future__ import annotations
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.worker_pool import WorkerPool


class FakeRuntime:
    def __init__(self, worker_id, started=None, release=None, failure=None):
        self.worker_id = worker_id
        self.started = started or threading.Event()
        self.release = release or threading.Event()
        self.failure = failure
        self.shutdown_requested = threading.Event()

    def run_forever(self):
        self.started.set()
        self.release.wait(2)
        if self.failure:
            raise self.failure

    def request_shutdown(self):
        self.shutdown_requested.set()
        self.release.set()


class WorkerPoolTests(unittest.TestCase):
    def test_starts_exactly_configured_number_of_pollers_and_drains(self):
        started = [threading.Event() for _ in range(3)]
        runtimes = []
        def factory(slot):
            runtime = FakeRuntime(f"worker-{slot}", started[slot])
            runtimes.append(runtime)
            return runtime
        pool = WorkerPool(runtime_factory=factory, concurrency=3,
                          monitor_interval_seconds=0.01)
        thread = threading.Thread(target=pool.run)
        thread.start()
        self.assertTrue(all(event.wait(1) for event in started))
        pool.request_shutdown()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(runtimes), 3)
        self.assertTrue(all(runtime.shutdown_requested.is_set() for runtime in runtimes))

    def test_duplicate_worker_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            WorkerPool(runtime_factory=lambda _: FakeRuntime("same-worker"),
                       concurrency=2)

    def test_invalid_concurrency_and_monitor_interval_rejected(self):
        with self.assertRaises(ValueError):
            WorkerPool(runtime_factory=lambda i: FakeRuntime(str(i)), concurrency=0)
        with self.assertRaises(ValueError):
            WorkerPool(runtime_factory=lambda i: FakeRuntime(str(i)), concurrency=1,
                       monitor_interval_seconds=0)

    def test_shutdown_before_start_creates_no_threads(self):
        runtimes = []
        def factory(slot):
            runtime = FakeRuntime(str(slot))
            runtimes.append(runtime)
            return runtime
        pool = WorkerPool(runtime_factory=factory, concurrency=2)
        pool.request_shutdown()
        pool.run()
        self.assertTrue(all(runtime.shutdown_requested.is_set() for runtime in runtimes))

    def test_unexpected_poller_failure_stops_the_pool_and_propagates(self):
        started = [threading.Event(), threading.Event()]
        runtimes = []
        def factory(slot):
            runtime = FakeRuntime(f"worker-{slot}", started[slot],
                                  failure=RuntimeError("poller failure") if slot == 0 else None)
            runtimes.append(runtime)
            if slot == 0:
                runtime.release.set()
            return runtime
        pool = WorkerPool(runtime_factory=factory, concurrency=2,
                          monitor_interval_seconds=0.01)
        with self.assertRaisesRegex(RuntimeError, "poller failure"):
            pool.run()
        self.assertTrue(all(runtime.shutdown_requested.is_set() for runtime in runtimes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
