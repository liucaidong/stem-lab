#!/usr/bin/env python3
"""R03.52.4 Retry Policy Registry behavior tests."""
from __future__ import annotations
import json
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.retry_policy import RetryPolicy, RetryPolicyRegistry

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = json.loads((ROOT / "contracts/worker-retry-policy.v1alpha1.json").read_text())


class RetryPolicyTests(unittest.TestCase):
    def test_document_registry_loads_and_maps_known_codes(self):
        registry = RetryPolicyRegistry.from_document(DOCUMENT, random_value=lambda: 0.5)
        decision = registry.decide("DEPENDENCY_UNAVAILABLE", 1, 5)
        self.assertTrue(decision.retryable)
        self.assertEqual(decision.error_code, "DEPENDENCY_UNAVAILABLE")
        self.assertEqual(decision.retry_delay_seconds, 1.0)

    def test_full_jitter_exponential_ceiling_is_capped(self):
        registry = RetryPolicyRegistry.from_document(DOCUMENT, random_value=lambda: 1.0)
        first = registry.decide("RATE_LIMITED", 1, 10)
        third = registry.decide("RATE_LIMITED", 3, 10)
        ninth = registry.decide("RATE_LIMITED", 9, 10)
        self.assertEqual(first.retry_delay_seconds, 5.0)
        self.assertEqual(third.retry_delay_seconds, 20.0)
        self.assertEqual(ninth.retry_delay_seconds, 300.0)

    def test_non_retryable_and_attempt_exhaustion_fail_closed(self):
        registry = RetryPolicyRegistry.from_document(DOCUMENT, random_value=lambda: 0.4)
        permanent = registry.decide("INVALID_INPUT", 1, 5)
        exhausted = registry.decide("DEPENDENCY_UNAVAILABLE", 5, 5)
        self.assertFalse(permanent.retryable)
        self.assertFalse(exhausted.retryable)
        self.assertEqual(exhausted.retry_delay_seconds, 0)

    def test_unknown_code_maps_to_non_retryable_default_without_echo(self):
        registry = RetryPolicyRegistry.from_document(DOCUMENT)
        decision = registry.decide("SECRET_TOKEN_IN_EXCEPTION", 1, 5)
        self.assertFalse(decision.retryable)
        self.assertEqual(decision.error_code, "UNCLASSIFIED_ERROR")
        self.assertNotIn("SECRET_TOKEN", decision.safe_message)

    def test_invalid_attempts_and_random_source_rejected(self):
        registry = RetryPolicyRegistry.from_document(DOCUMENT, random_value=lambda: 1.1)
        with self.assertRaises(ValueError):
            registry.decide("DEPENDENCY_UNAVAILABLE", 0, 5)
        with self.assertRaises(ValueError):
            registry.decide("DEPENDENCY_UNAVAILABLE", 1, 0)
        with self.assertRaises(ValueError):
            registry.decide("DEPENDENCY_UNAVAILABLE", 1, 5)


    def test_document_loader_rejects_coerced_boolean_and_duplicate_codes(self):
        invalid_type = copy.deepcopy(DOCUMENT)
        invalid_type["policies"][0]["retryable"] = "false"
        with self.assertRaises(ValueError):
            RetryPolicyRegistry.from_document(invalid_type)
        duplicate = copy.deepcopy(DOCUMENT)
        duplicate["policies"].append(copy.deepcopy(duplicate["policies"][0]))
        with self.assertRaises(ValueError):
            RetryPolicyRegistry.from_document(duplicate)

    def test_registry_rejects_retryable_default_and_invalid_policy(self):
        with self.assertRaises(ValueError):
            RetryPolicyRegistry({}, RetryPolicy("DEFAULT", True, 1, 2, "safe"))
        with self.assertRaises(ValueError):
            RetryPolicy("BAD", False, 1, 0, "safe")
        with self.assertRaises(ValueError):
            RetryPolicy("BAD", True, 2, 1, "safe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
