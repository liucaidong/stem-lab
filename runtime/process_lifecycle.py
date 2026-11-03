"""R03.52.3 OS signal to WorkerPool shutdown bridge.

Signal handlers only set an Event. A normal supervisor thread performs pool
shutdown; handlers do not block, join threads, access the Store, or mutate jobs.
"""
from __future__ import annotations
import signal
import threading
from types import FrameType
from typing import Iterable

from runtime.worker_pool import WorkerPool


class SignalShutdownBridge:
    def __init__(self, pool: WorkerPool,
                 handled_signals: Iterable[int] = (signal.SIGINT, signal.SIGTERM),
                 monitor_interval_seconds: float = 0.02) -> None:
        if monitor_interval_seconds <= 0:
            raise ValueError("monitor interval must be positive")
        self.pool = pool
        self.handled_signals = tuple(handled_signals)
        if not self.handled_signals:
            raise ValueError("at least one signal is required")
        self.monitor_interval_seconds = monitor_interval_seconds
        self._requested = threading.Event()
        self._monitor_stop = threading.Event()
        self._previous: dict[int, object] = {}
        self._monitor: threading.Thread | None = None
        self._handler = self._handle_signal

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        self._requested.set()

    def __enter__(self) -> "SignalShutdownBridge":
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("signal handlers must be installed from the main thread")
        for signum in self.handled_signals:
            self._previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handler)
        self._monitor = threading.Thread(
            target=self._monitor_loop,
            name="worker-signal-shutdown-bridge",
            daemon=True,
        )
        self._monitor.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._monitor_stop.set()
        if self._monitor is not None:
            self._monitor.join()
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)
        self._previous.clear()

    def _monitor_loop(self) -> None:
        while not self._monitor_stop.wait(self.monitor_interval_seconds):
            if self._requested.is_set():
                self.pool.request_shutdown()
                return


def run_with_signal_handling(pool: WorkerPool) -> None:
    """Run pool until signal or normal shutdown; restore previous handlers."""
    with SignalShutdownBridge(pool):
        pool.run()
