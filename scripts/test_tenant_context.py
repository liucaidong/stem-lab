#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.tenant_context import TenantContextError, verify_tenant_assertion

KEY = b"reference-only-test-key-material-32-bytes-minimum!!"


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def token(**overrides) -> str:
    claims = {
        "v": 1, "tenant_id": "tenant-a", "sub": "principal-1",
        "aud": "stemlab-worker", "action": "job.complete",
        "resource_id": "job-1", "iat": 1000, "exp": 1060,
        "nonce": "nonce-123",
    }
    claims.update(overrides)
    encoded = b64(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(KEY, encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + b64(signature)


class TenantContextTests(unittest.TestCase):
    def verify(self, value=None, **kwargs):
        return verify_tenant_assertion(
            value or token(), key=KEY, audience="stemlab-worker",
            action="job.complete", resource_id="job-1", now=1030, **kwargs
        )

    def test_valid_assertion_returns_bound_tenant_and_principal(self):
        result = self.verify()
        self.assertEqual((result.tenant_id, result.subject), ("tenant-a", "principal-1"))

    def test_signature_tampering_is_rejected(self):
        value = token()
        payload, signature = value.split(".")
        changed = ("A" if signature[0] != "A" else "B") + signature[1:]
        with self.assertRaises(TenantContextError):
            self.verify(payload + "." + changed)

    def test_tenant_claim_tampering_without_resigning_is_rejected(self):
        value = token()
        payload, signature = value.split(".")
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        changed_raw = raw.replace(b"tenant-a", b"tenant-b")
        changed_payload = b64(changed_raw)
        with self.assertRaises(TenantContextError):
            self.verify(changed_payload + "." + signature)

    def test_expired_and_future_assertions_are_rejected(self):
        with self.assertRaises(TenantContextError):
            self.verify(token(exp=1030))
        with self.assertRaises(TenantContextError):
            self.verify(token(iat=1031, exp=1060))

    def test_wrong_audience_action_and_resource_are_rejected(self):
        for value in (token(aud="other"), token(action="job.claim"),
                      token(resource_id="job-2")):
            with self.subTest(value=value), self.assertRaises(TenantContextError):
                self.verify(value)

    def test_overlong_lifetime_and_unknown_claims_are_rejected(self):
        with self.assertRaises(TenantContextError):
            self.verify(token(exp=1300))
        with self.assertRaises(TenantContextError):
            self.verify(token(extra="not-allowed"))

    def test_malformed_and_weak_key_are_rejected(self):
        with self.assertRaises(TenantContextError):
            self.verify("not-a-token")
        with self.assertRaises(TenantContextError):
            verify_tenant_assertion(token(), key=b"short", audience="stemlab-worker",
                                    action="job.complete", resource_id="job-1", now=1030)


if __name__ == "__main__":
    unittest.main(verbosity=2)
