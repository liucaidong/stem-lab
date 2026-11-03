#!/usr/bin/env python3
"""R03.52 Worker Runtime lifecycle and supervision reference tests."""
from __future__ import annotations
import threading
import time
import unittest
import sys
import copy
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.worker_runtime import ClaimedJob, WorkerRuntime
from runtime.retry_policy import RetryPolicyRegistry


class FakeStore:
    def __init__(self, job=None, renew_result=True):
        self.job = job
        self.renew_result = renew_result
        self.claim_calls = 0
        self.renew_calls = 0
        self.complete_calls = []
        self.fail_calls = []

    def claim(self, worker_id, lease_seconds):
        self.claim_calls += 1
        return self.job

    def renew(self, job, lease_seconds):
        self.renew_calls += 1
        return self.renew_result

    def complete(self, job, result):
        self.complete_calls.append((job.lease_epoch, result))
        return True

    def fail(self, job, decision):
        self.fail_calls.append((job.lease_epoch, decision))
        return True


def sample_job():
    return ClaimedJob("tenant-a", "job-1", "validate", {"x": 1},
                      "worker-a", 7, 1, 5)


def classify(exc):
    return "HANDLER_ERROR"


def policy_registry():
    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "contracts/worker-retry-policy.v1alpha1.json").read_text())
    document = copy.deepcopy(document)
    document["policies"].append({
        "error_code": "HANDLER_ERROR", "retryable": True,
        "base_delay_micros": 3000000, "max_delay_micros": 3000000,
        "safe_message": "Handler failed safely"
    })
    return RetryPolicyRegistry.from_document(document, random_value=lambda: 1.0)


class WorkerRuntimeTests(unittest.TestCase):
    def runtime(self, store, handlers, **kwargs):
        return WorkerRuntime(worker_id="worker-a", store=store, handlers=handlers,
                             classify_error_code=classify, retry_policy=policy_registry(), lease_seconds=0.12,
                             heartbeat_interval_seconds=0.02,
                             poll_interval_seconds=0, **kwargs)

    def test_claimed_job_rejects_unsafe_epoch_and_attempt_budget(self):
        with self.assertRaises(ValueError):
            ClaimedJob("tenant-a", "job-1", "validate", {}, "worker-a", 2**53, 1, 5)
        with self.assertRaises(ValueError):
            ClaimedJob("tenant-a", "job-1", "validate", {}, "worker-a", 7, 1, 101)

    def test_runtime_rejects_non_registry_retry_authority(self):
        class UntrustedPolicy:
            def decide(self, error_code, attempt_count, maximum_attempts):
                raise AssertionError("must not be invoked")
        with self.assertRaises(TypeError):
            WorkerRuntime(worker_id="w", store=FakeStore(), handlers={},
                          classify_error_code=classify, retry_policy=UntrustedPolicy())

    def test_idle_does_not_run_handler(self):
        store = FakeStore()
        runtime = self.runtime(store, {"validate": lambda *_: self.fail("unexpected")})
        self.assertEqual(runtime.run_once(), "idle")
        self.assertEqual(store.claim_calls, 1)

    def test_success_completes_with_claimed_epoch(self):
        store = FakeStore(sample_job())
        runtime = self.runtime(store, {"validate": lambda job, ctx: {"ok": True}})
        self.assertEqual(runtime.run_once(), "succeeded")
        self.assertEqual(store.complete_calls, [(7, {"ok": True})])
        self.assertEqual(store.fail_calls, [])

    def test_handler_exception_uses_classifier_and_failure_transition(self):
        store = FakeStore(sample_job())
        def handler(job, context):
            raise ValueError("private payload must not be persisted")
        runtime = self.runtime(store, {"validate": handler})
        self.assertEqual(runtime.run_once(), "retry_or_dlq")
        self.assertEqual(store.fail_calls[0][1].error_code, "HANDLER_ERROR")
        self.assertEqual(store.fail_calls[0][1].retry_delay_micros, 3000000)
        self.assertEqual(store.fail_calls[0][1].policy_version, "2026-11-03.1")
        self.assertNotIn("private payload", store.fail_calls[0][1].safe_message)

    def test_heartbeat_loss_prevents_completion_and_failure(self):
        store = FakeStore(sample_job(), renew_result=False)
        entered = threading.Event()
        release = threading.Event()
        def handler(job, context):
            entered.set()
            release.wait(1)
            return {"ok": True}
        runtime = self.runtime(store, {"validate": handler})
        result = []
        thread = threading.Thread(target=lambda: result.append(runtime.run_once()))
        thread.start()
        self.assertTrue(entered.wait(1))
        deadline = time.monotonic() + 1
        while store.renew_calls == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        release.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["lease_lost"])
        self.assertEqual(store.complete_calls, [])
        self.assertEqual(store.fail_calls, [])

    def test_shutdown_stops_future_claims(self):
        store = FakeStore(sample_job())
        runtime = self.runtime(store, {"validate": lambda *_: {"ok": True}})
        runtime.request_shutdown()
        self.assertEqual(runtime.run_once(), "shutdown")
        self.assertEqual(store.claim_calls, 0)

    def test_shutdown_drains_active_handler_without_new_claim(self):
        store = FakeStore(sample_job())
        entered = threading.Event()
        release = threading.Event()
        observed_shutdown = []
        def handler(job, context):
            entered.set()
            release.wait(1)
            observed_shutdown.append(context.shutdown_requested.is_set())
            return {"drained": True}
        runtime = self.runtime(store, {"validate": handler})
        result = []
        thread = threading.Thread(target=lambda: result.append(runtime.run_once()))
        thread.start()
        self.assertTrue(entered.wait(1))
        runtime.request_shutdown()
        release.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["succeeded"])
        self.assertEqual(observed_shutdown, [True])
        self.assertEqual(store.complete_calls, [(7, {"drained": True})])

    def test_heartbeat_exception_is_treated_as_lease_loss(self):
        class BrokenHeartbeatStore(FakeStore):
            def renew(self, job, lease_seconds):
                self.renew_calls += 1
                raise TimeoutError("store unavailable")
        store = BrokenHeartbeatStore(sample_job())
        entered = threading.Event()
        release = threading.Event()
        def handler(job, context):
            entered.set()
            release.wait(1)
            return {"ok": True}
        runtime = self.runtime(store, {"validate": handler})
        result = []
        thread = threading.Thread(target=lambda: result.append(runtime.run_once()))
        thread.start()
        self.assertTrue(entered.wait(1))
        deadline = time.monotonic() + 1
        while store.renew_calls == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        release.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["lease_lost"])
        self.assertEqual(store.complete_calls, [])
        self.assertEqual(store.fail_calls, [])

    def test_missing_handler_fails_closed(self):
        store = FakeStore(sample_job())
        runtime = self.runtime(store, {})
        self.assertEqual(runtime.run_once(), "failed")
        self.assertEqual(store.fail_calls[0][1].error_code, "HANDLER_NOT_REGISTERED")

    def test_invalid_heartbeat_interval_rejected(self):
        with self.assertRaises(ValueError):
            WorkerRuntime(worker_id="w", store=FakeStore(), handlers={},
                          classify_error_code=classify, retry_policy=policy_registry(), lease_seconds=5,
                          heartbeat_interval_seconds=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
