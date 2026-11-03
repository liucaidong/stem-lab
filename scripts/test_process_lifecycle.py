#!/usr/bin/env python3
"""R03.52.3 OS signal shutdown bridge tests."""
from __future__ import annotations
import signal
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.process_lifecycle import SignalShutdownBridge


class FakePool:
    def __init__(self):
        self.shutdown_calls = 0
        self.shutdown_event = threading.Event()

    def request_shutdown(self):
        self.shutdown_calls += 1
        self.shutdown_event.set()


class SignalShutdownBridgeTests(unittest.TestCase):
    def test_signal_handler_only_requests_shutdown_via_monitor(self):
        pool = FakePool()
        installed = {}
        previous = {signal.SIGINT: object(), signal.SIGTERM: object()}
        def fake_signal(signum, handler):
            installed[signum] = handler
        with patch("runtime.process_lifecycle.signal.getsignal",
                   side_effect=lambda sig: previous[sig]), \
             patch("runtime.process_lifecycle.signal.signal", side_effect=fake_signal):
            with SignalShutdownBridge(pool, monitor_interval_seconds=0.005):
                handler_int = installed[signal.SIGINT]
                handler_term = installed[signal.SIGTERM]
                self.assertIs(handler_int, handler_term)
                handler_term(signal.SIGTERM, None)
                self.assertTrue(pool.shutdown_event.wait(1))
            self.assertEqual(pool.shutdown_calls, 1)

    def test_context_restores_previous_signal_handlers(self):
        pool = FakePool()
        installed = {}
        previous = {signal.SIGINT: object(), signal.SIGTERM: object()}
        def fake_signal(signum, handler):
            installed[signum] = handler
        with patch("runtime.process_lifecycle.signal.getsignal",
                   side_effect=lambda sig: previous[sig]), \
             patch("runtime.process_lifecycle.signal.signal", side_effect=fake_signal):
            with SignalShutdownBridge(pool):
                self.assertTrue(callable(installed[signal.SIGINT]))
            self.assertIs(installed[signal.SIGINT], previous[signal.SIGINT])
            self.assertIs(installed[signal.SIGTERM], previous[signal.SIGTERM])

    def test_installation_from_non_main_thread_is_rejected(self):
        errors = []
        pool = FakePool()
        def install():
            try:
                with SignalShutdownBridge(pool):
                    pass
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=install)
        thread.start()
        thread.join(1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)

    def test_empty_signal_set_and_invalid_monitor_interval_rejected(self):
        with self.assertRaises(ValueError):
            SignalShutdownBridge(FakePool(), handled_signals=())
        with self.assertRaises(ValueError):
            SignalShutdownBridge(FakePool(), monitor_interval_seconds=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
