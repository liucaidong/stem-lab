#!/usr/bin/env python3
"""Offline tests for exact-SHA, read-only CI reconciliation."""
import unittest
from ci_reconcile import ACTIVE, RECOVERY, SUCCESS, Target, classify_target, run_id_from_details_url

SHA = "a" * 40
TARGET = Target("pull_request", "example", 7, SHA)

def run(run_id=123, status="completed", conclusion="success"):
    return {"id": run_id, "head_sha": SHA, "path": ".github/workflows/contract-validation.yml",
            "status": status, "conclusion": conclusion, "run_attempt": 1, "created_at": "2026-11-04T00:00:00Z"}

def check(run_id=123, conclusion="success", app_id=15368, name="CI result"):
    return {"name": name, "app": {"id": app_id}, "status": "completed", "conclusion": conclusion,
            "details_url": f"https://github.com/example/repo/actions/runs/{run_id}/job/999"}

class ReconciliationClassificationTests(unittest.TestCase):
    def test_exact_sha_required_check_and_workflow_success_is_covered(self):
        self.assertEqual(classify_target(TARGET, [run()], [check()]).state, SUCCESS)
    def test_active_run_prevents_duplicate_recovery(self):
        self.assertEqual(classify_target(TARGET, [run(status="in_progress", conclusion=None)], []).state, ACTIVE)
    def test_cancelled_run_requires_recovery(self):
        self.assertEqual(classify_target(TARGET, [run(conclusion="cancelled")], []).state, RECOVERY)
    def test_workflow_success_without_aggregate_check_is_not_covered(self):
        self.assertEqual(classify_target(TARGET, [run()], [check(name="validate-contracts")]).state, RECOVERY)
    def test_wrong_required_check_app_is_not_covered(self):
        self.assertEqual(classify_target(TARGET, [run()], [check(app_id=1)]).state, RECOVERY)
    def test_check_from_different_run_is_not_covered(self):
        self.assertEqual(classify_target(TARGET, [run(run_id=123)], [check(run_id=456)]).state, RECOVERY)
    def test_different_sha_run_is_not_covered(self):
        other = dict(run())
        other["head_sha"] = "b" * 40
        self.assertEqual(classify_target(TARGET, [other], [check()]).state, RECOVERY)
    def test_no_run_is_recovery_required(self):
        self.assertEqual(classify_target(TARGET, [], []).state, RECOVERY)
    def test_details_url_parser(self):
        self.assertEqual(run_id_from_details_url("https://github.com/o/r/actions/runs/123/job/456"), 123)
        self.assertIsNone(run_id_from_details_url("https://example.invalid/no-run-id"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
