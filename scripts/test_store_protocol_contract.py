#!/usr/bin/env python3
"""R03.52.7.2 Store / Unit-of-Work contract validation."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from runtime.store_protocol import (
    ClaimRequest,
    ClaimedJobRecord,
    CompleteJobCommand,
    FailJobCommand,
    JobLease,
    StoreAccessContext,
    StoreError,
    StoreErrorCode,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "worker-store-protocol.schema.v1alpha1.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
LEASE = {
    "tenant_id": "tenant-a",
    "job_id": "job-1",
    "owner": "worker-1",
    "epoch": 7,
    "expires_at": "2026-11-02T13:00:00Z",
}


class StoreProtocolSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Draft202012Validator.check_schema(SCHEMA)
        cls.request_validator = Draft202012Validator(SCHEMA)
        cls.response_validator = Draft202012Validator(SCHEMA["$defs"]["StoreResponse"])
        cls.error_validator = Draft202012Validator(SCHEMA["$defs"]["StoreError"])

    def access(self):
        return {"assertion": "opaque.signed.assertion", "audience": "stemlab-store"}

    def valid_request(self, command):
        return {
            "schema_version": "1alpha1",
            "access_context": self.access(),
            "command": command,
        }

    def test_valid_claim_request(self):
        request = self.valid_request({
            "operation": "claim",
            "worker_id": "worker-1",
            "supported_job_types": ["package.validate", "package.index"],
            "lease_seconds": 30,
            "max_items": 1,
        })
        self.request_validator.validate(request)

    def test_valid_renew_complete_and_fail_requests(self):
        commands = [
            {
                "operation": "renew",
                "lease": LEASE,
                "lease_seconds": 30,
            },
            {
                "operation": "complete",
                "lease": LEASE,
                "expected_session_revision": 4,
                "result_ref": "object://results/job-1",
                "idempotency_key": "complete-job-1-7",
                "request_digest": "sha256:" + "a" * 64,
            },
            {
                "operation": "fail",
                "lease": LEASE,
                "error_code": "PACKAGE_VALIDATION_FAILED",
                "safe_message": "Package validation failed",
                "retryable": False,
                "retry_delay_seconds": 0,
                "idempotency_key": "fail-job-1-7",
            },
        ]
        for command in commands:
            with self.subTest(operation=command["operation"]):
                self.request_validator.validate(self.valid_request(command))

    def test_request_rejects_untrusted_top_level_tenant_selector(self):
        request = self.valid_request({
            "operation": "claim",
            "worker_id": "worker-1",
            "supported_job_types": ["package.validate"],
            "lease_seconds": 30,
            "max_items": 1,
        })
        request["tenant_id"] = "tenant-b"
        with self.assertRaises(Exception):
            self.request_validator.validate(request)

    def test_request_rejects_batch_claim_in_v1alpha1(self):
        request = self.valid_request({
            "operation": "claim",
            "worker_id": "worker-1",
            "supported_job_types": ["package.validate"],
            "lease_seconds": 30,
            "max_items": 10,
        })
        with self.assertRaises(Exception):
            self.request_validator.validate(request)

    def test_response_and_unknown_commit_outcome_error(self):
        response = {
            "schema_version": "1alpha1",
            "outcome": "APPLIED",
            "result": None,
        }
        self.response_validator.validate(response)
        error = {
            "schema_version": "1alpha1",
            "error_code": "TRANSACTION_OUTCOME_UNKNOWN",
            "safe_message": "Commit result is unknown; reconcile by idempotency key",
            "retryable": False,
            "outcome_known": False,
        }
        self.error_validator.validate(error)
        error["outcome_known"] = True
        with self.assertRaises(Exception):
            self.error_validator.validate(error)


class StoreProtocolValueTests(unittest.TestCase):
    def test_access_context_is_opaque_and_has_no_tenant_field(self):
        ctx = StoreAccessContext("signed.assertion", "stemlab-store")
        self.assertFalse(hasattr(ctx, "tenant_id"))
        with self.assertRaises(ValueError):
            StoreAccessContext("", "stemlab-store")

    def test_claim_request_rejects_duplicate_types_and_batch_claim(self):
        with self.assertRaises(ValueError):
            ClaimRequest("worker-1", ("validate", "validate"), 30)
        with self.assertRaises(ValueError):
            ClaimRequest("worker-1", ("validate",), 30, max_items=2)

    def test_lease_requires_aware_expiry_and_positive_epoch(self):
        with self.assertRaises(ValueError):
            JobLease("tenant-a", "job-1", "worker-1", 0, datetime.now(timezone.utc))
        with self.assertRaises(ValueError):
            JobLease("tenant-a", "job-1", "worker-1", 1, datetime.now())

    def test_claimed_payload_tenant_must_match_persisted_lease_tenant(self):
        lease = JobLease(
            "tenant-a", "job-1", "worker-1", 7,
            datetime.now(timezone.utc),
        )
        with self.assertRaises(ValueError):
            ClaimedJobRecord(lease, "package.validate", {"tenant_id": "tenant-b"}, 1)

    def test_complete_command_requires_stable_digest(self):
        lease = JobLease(
            "tenant-a", "job-1", "worker-1", 7,
            datetime.now(timezone.utc),
        )
        with self.assertRaises(ValueError):
            CompleteJobCommand(
                lease, 3, "object://result", "complete-1", "sha256:bad"
            )

    def test_failure_command_rejects_unbounded_or_unstable_error(self):
        lease = JobLease(
            "tenant-a", "job-1", "worker-1", 7,
            datetime.now(timezone.utc),
        )
        with self.assertRaises(ValueError):
            FailJobCommand(lease, "raw exception", "safe", True, 1, "fail-1")
        with self.assertRaises(ValueError):
            FailJobCommand(lease, "FAILED", "x" * 513, True, 1, "fail-1")

    def test_unknown_transaction_outcome_is_explicit(self):
        error = StoreError(
            StoreErrorCode.TRANSACTION_OUTCOME_UNKNOWN,
            "Commit result is unknown",
            retryable=False,
            outcome_known=False,
        )
        self.assertFalse(error.outcome_known)
        with self.assertRaises(ValueError):
            StoreError(
                StoreErrorCode.TRANSACTION_OUTCOME_UNKNOWN,
                "Incorrect known outcome",
                outcome_known=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
