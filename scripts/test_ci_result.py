#!/usr/bin/env python3
"""Tests for truthful, fail-closed aggregation of the final CI result."""
import unittest

from ci_result import final_ci_decision


class FinalCiDecisionTests(unittest.TestCase):
    def test_passes_only_when_every_required_job_succeeds(self):
        passed, message = final_ci_decision(
            "success",
            "true",
            {"validate-contracts": "success", "tenant-ed25519-verifier": "success"},
        )
        self.assertTrue(passed)
        self.assertIn("CI PASSED", message)

    def test_non_admitted_run_is_blocked_and_non_successful(self):
        passed, message = final_ci_decision(
            "success",
            "false",
            {"validate-contracts": "skipped", "tenant-ed25519-verifier": "skipped"},
        )
        self.assertFalse(passed)
        self.assertIn("CI BLOCKED", message)

    def test_admission_job_failure_blocks_validation(self):
        passed, message = final_ci_decision("failure", "", {})
        self.assertFalse(passed)
        self.assertIn("CI BLOCKED", message)

    def test_missing_admission_output_fails_closed(self):
        passed, message = final_ci_decision(
            "success", "", {"validate-contracts": "success", "tenant-ed25519-verifier": "success"}
        )
        self.assertFalse(passed)
        self.assertIn("missing or invalid", message)

    def test_validation_failure_fails(self):
        passed, message = final_ci_decision(
            "success",
            "true",
            {"validate-contracts": "failure", "tenant-ed25519-verifier": "success"},
        )
        self.assertFalse(passed)
        self.assertIn("CI FAILED", message)

    def test_validation_skipped_after_admission_is_not_a_pass(self):
        passed, message = final_ci_decision(
            "success",
            "true",
            {"validate-contracts": "success", "tenant-ed25519-verifier": "skipped"},
        )
        self.assertFalse(passed)
        self.assertIn("tenant-ed25519-verifier=skipped", message)

    def test_cancelled_validation_is_not_a_pass(self):
        passed, message = final_ci_decision(
            "success",
            "true",
            {"validate-contracts": "success", "tenant-ed25519-verifier": "cancelled"},
        )
        self.assertFalse(passed)
        self.assertIn("cancelled", message)

    def test_missing_validation_result_fails_closed(self):
        passed, message = final_ci_decision("success", "true", {"validate-contracts": "success"})
        self.assertFalse(passed)
        self.assertIn("missing validation job", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
