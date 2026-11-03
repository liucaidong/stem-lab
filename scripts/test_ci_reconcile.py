#!/usr/bin/env python3
"""Offline tests for exact-SHA, all-open-PR, read-only CI reconciliation."""
import unittest
from typing import get_type_hints

from ci_reconcile import (
    ACTIVE, RECOVERY, SUCCESS, GitHubReadOnly, ReconcileError, Target,
    check_started_in_latest_attempt, classify_target, discover_targets,
    run_id_from_details_url,
)

SHA = "a" * 40
TARGET = Target("pull_request", "example", 7, SHA, "main", "b" * 40)


def run(
    run_id=123, status="completed", conclusion="success",
    created_at="2026-11-04T00:00:00Z", attempt=1,
    run_started_at="2026-11-04T00:00:00Z",
):
    return {
        "id": run_id, "head_sha": SHA,
        "path": ".github/workflows/contract-validation.yml",
        "status": status, "conclusion": conclusion,
        "run_attempt": attempt, "created_at": created_at,
        "run_started_at": run_started_at,
    }


def check(
    run_id=123, conclusion="success", app_id=15368,
    name="CI result", started_at="2026-11-04T00:00:00Z",
):
    return {
        "name": name, "app": {"id": app_id}, "status": "completed",
        "conclusion": conclusion,
        "details_url": f"https://github.com/example/repo/actions/runs/{run_id}/job/999",
        "head_sha": SHA, "started_at": started_at,
    }


class FakeDiscoveryAPI:
    def get(self, path, query=None):
        return {"name": "main", "commit": {"sha": "c" * 40}}

    def list_all(self, path, key, query=None):
        self.query = query
        return [
            {
                "number": 7, "title": "PR on main",
                "head": {"sha": "a" * 40},
                "base": {"ref": "main", "sha": "c" * 40},
            },
            {
                "number": 8, "title": "PR on stacked branch",
                "head": {"sha": "d" * 40},
                "base": {"ref": "feature/parent", "sha": "e" * 40},
            },
        ]


class PagedAPI(GitHubReadOnly):
    def __init__(self, pages):
        super().__init__(None)
        self.pages = pages

    def get(self, path, query=None):
        return self.pages[query["page"]]


class ReconciliationClassificationTests(unittest.TestCase):
    def test_exact_sha_required_check_and_workflow_success_is_covered(self):
        self.assertEqual(classify_target(TARGET, [run()], [check()]).state, SUCCESS)

    def test_active_run_prevents_duplicate_recovery(self):
        self.assertEqual(
            classify_target(TARGET, [run(status="in_progress", conclusion=None)], []).state,
            ACTIVE,
        )

    def test_cancelled_run_requires_recovery(self):
        self.assertEqual(classify_target(TARGET, [run(conclusion="cancelled")], []).state, RECOVERY)

    def test_queue_overflow_cancellation_cannot_be_masked_by_older_success(self):
        older_success = run(run_id=100, created_at="2026-11-03T23:00:00Z")
        latest_overflow_cancel = run(
            run_id=200, status="completed", conclusion="cancelled",
            created_at="2026-11-03T23:01:00Z",
        )
        older_check = check(run_id=100)
        self.assertEqual(
            classify_target(TARGET, [older_success, latest_overflow_cancel], [older_check]).state,
            RECOVERY,
        )

    def test_workflow_success_without_aggregate_check_is_not_covered(self):
        self.assertEqual(
            classify_target(TARGET, [run()], [check(name="validate-contracts")]).state,
            RECOVERY,
        )

    def test_wrong_required_check_app_is_not_covered(self):
        self.assertEqual(classify_target(TARGET, [run()], [check(app_id=1)]).state, RECOVERY)

    def test_check_from_different_run_is_not_covered(self):
        self.assertEqual(classify_target(TARGET, [run()], [check(run_id=456)]).state, RECOVERY)

    def test_different_sha_run_is_not_covered(self):
        other = dict(run())
        other["head_sha"] = "b" * 40
        self.assertEqual(classify_target(TARGET, [other], [check()]).state, RECOVERY)

    def test_no_run_is_recovery_required(self):
        self.assertEqual(classify_target(TARGET, [], []).state, RECOVERY)

    def test_older_success_cannot_mask_latest_failure(self):
        older = run(run_id=100, created_at="2026-11-03T23:00:00Z")
        latest = run(run_id=200, conclusion="failure", created_at="2026-11-04T00:00:00Z")
        self.assertEqual(classify_target(TARGET, [older, latest], [check(run_id=100)]).state, RECOVERY)

    def test_latest_success_requires_check_from_latest_run(self):
        older = run(run_id=100, created_at="2026-11-03T23:00:00Z")
        latest = run(run_id=200, created_at="2026-11-04T00:00:00Z")
        self.assertEqual(classify_target(TARGET, [older, latest], [check(run_id=100)]).state, RECOVERY)

    def test_latest_success_with_its_own_exact_sha_check_is_covered(self):
        older = run(run_id=100, created_at="2026-11-03T23:00:00Z")
        latest = run(run_id=200, created_at="2026-11-04T00:00:00Z")
        self.assertEqual(classify_target(TARGET, [older, latest], [check(run_id=200)]).state, SUCCESS)

    def test_latest_active_run_takes_precedence_over_older_success(self):
        older = run(run_id=100, created_at="2026-11-03T23:00:00Z")
        latest = run(
            run_id=200, status="in_progress", conclusion=None,
            created_at="2026-11-04T00:00:00Z",
        )
        self.assertEqual(classify_target(TARGET, [older, latest], [check(run_id=100)]).state, ACTIVE)

    def test_old_successful_attempt_cannot_mask_latest_successful_rerun(self):
        first = run(run_id=123, attempt=1, run_started_at="2026-11-04T00:00:00Z")
        latest = run(run_id=123, attempt=2, run_started_at="2026-11-04T00:10:00Z")
        old_attempt_check = check(run_id=123, started_at="2026-11-04T00:01:00Z")
        self.assertEqual(classify_target(TARGET, [first, latest], [old_attempt_check]).state, RECOVERY)

    def test_check_started_in_latest_attempt_is_covered(self):
        latest = run(run_id=123, attempt=2, run_started_at="2026-11-04T00:10:00Z")
        latest_attempt_check = check(run_id=123, started_at="2026-11-04T00:10:01Z")
        self.assertEqual(classify_target(TARGET, [latest], [latest_attempt_check]).state, SUCCESS)

    def test_missing_attempt_timestamps_are_not_accepted_as_success(self):
        latest = run()
        no_attempt_time = check()
        no_attempt_time.pop("started_at")
        self.assertEqual(classify_target(TARGET, [latest], [no_attempt_time]).state, RECOVERY)

    def test_naive_or_malformed_timestamp_fails_closed_without_type_error(self):
        latest = run(run_started_at="2026-11-04T00:00:00")
        check_with_offset = check(started_at="2026-11-04T00:00:01+00:00")
        self.assertFalse(check_started_in_latest_attempt(check_with_offset, latest))
        self.assertEqual(classify_target(TARGET, [latest], [check_with_offset]).state, RECOVERY)

    def test_invalid_created_at_fails_closed(self):
        self.assertEqual(
            classify_target(TARGET, [run(created_at="not-a-timestamp")], [check()]).state,
            RECOVERY,
        )

    def test_check_for_different_sha_is_not_covered(self):
        different = check()
        different["head_sha"] = "b" * 40
        self.assertEqual(classify_target(TARGET, [run()], [different]).state, RECOVERY)

    def test_details_url_parser_requires_canonical_github_url(self):
        self.assertEqual(
            run_id_from_details_url("https://github.com/o/r/actions/runs/123/job/456"),
            123,
        )
        self.assertIsNone(run_id_from_details_url("https://example.invalid/o/r/actions/runs/123/job/456"))
        self.assertIsNone(run_id_from_details_url("https://github.com/o/r/actions/runs/123"))

    def test_get_annotation_supports_object_and_array_responses(self):
        hints = get_type_hints(GitHubReadOnly.get)
        self.assertIn("list", str(hints["return"]))
        self.assertIn("dict", str(hints["return"]))


class DiscoveryAndPaginationTests(unittest.TestCase):
    def test_discovery_includes_open_prs_with_non_main_base(self):
        api = FakeDiscoveryAPI()
        targets = discover_targets(api, "owner", "repo", "main")
        self.assertEqual(len(targets), 3)
        self.assertEqual(api.query, {"state": "open", "sort": "updated", "direction": "desc"})
        stacked = next(target for target in targets if target.number == 8)
        self.assertEqual(stacked.base_ref, "feature/parent")
        self.assertEqual(stacked.base_sha, "e" * 40)

    def test_list_all_rejects_malformed_entries_instead_of_silently_dropping(self):
        api = PagedAPI({1: [{"id": 1}, "unexpected"]})
        with self.assertRaises(ReconcileError):
            api.list_all("/items", "items")

    def test_list_all_reads_the_empty_page_after_exactly_one_full_page(self):
        api = PagedAPI({1: [{"id": index} for index in range(100)], 2: []})
        self.assertEqual(len(api.list_all("/items", "items")), 100)

    def test_list_all_fails_closed_when_safety_limit_is_exhausted(self):
        page = [{"id": 1} for _ in range(100)]
        api = PagedAPI({index: page for index in range(1, 101)})
        with self.assertRaises(ReconcileError):
            api.list_all("/items", "items")


if __name__ == "__main__":
    unittest.main(verbosity=2)
