#!/usr/bin/env python3
"""R03.52.5 DLQ replay authorization preflight tests."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.dlq_replay import (
    REPLAY_ACTION, ReplayAuthorizationDecision, prepare_dlq_replay,
)


def auth(**overrides):
    values = dict(actor_id="operator-7", tenant_id="tenant-a",
                  job_id="job-original", action=REPLAY_ACTION,
                  allowed=True, policy_version="policy-v1")
    values.update(overrides)
    return ReplayAuthorizationDecision(**values)


def prepare(**overrides):
    values = dict(
        tenant_id="tenant-a", source_job_id="job-original",
        source_status="dead_lettered", replay_count=0, replay_limit=3,
        request_id="request-1", new_job_id="job-replay-1",
        actor_id="operator-7", reason="Retry after dependency recovery",
        authorization=auth(),
    )
    values.update(overrides)
    return prepare_dlq_replay(**values)


class DlqReplayTests(unittest.TestCase):
    def test_authorized_replay_creates_new_job_plan_and_audit_context(self):
        plan = prepare()
        self.assertEqual(plan.new_job_id, "job-replay-1")
        self.assertEqual(plan.source_job_id, "job-original")
        self.assertEqual(plan.replay_number, 1)
        self.assertEqual(plan.actor_id, "operator-7")
        self.assertEqual(plan.reason, "Retry after dependency recovery")
        self.assertEqual(plan.authorization_policy_version, "policy-v1")

    def test_only_dead_lettered_source_can_be_replayed(self):
        with self.assertRaises(ValueError):
            prepare(source_status="running")

    def test_replay_limit_is_enforced(self):
        with self.assertRaises(ValueError):
            prepare(replay_count=3, replay_limit=3)

    def test_denied_authorization_fails_closed(self):
        with self.assertRaises(PermissionError):
            prepare(authorization=auth(allowed=False))

    def test_action_actor_and_resource_scope_must_match(self):
        for decision in (
            auth(action="worker.job.cancel"),
            auth(actor_id="another-operator"),
            auth(tenant_id="tenant-b"),
            auth(job_id="other-job"),
        ):
            with self.subTest(decision=decision), self.assertRaises(PermissionError):
                prepare(authorization=decision)


    def test_authorization_allowed_must_be_boolean_true(self):
        with self.assertRaises(PermissionError):
            prepare(authorization=auth(allowed=1))

    def test_replay_requires_new_job_id_and_request_id(self):
        with self.assertRaises(ValueError):
            prepare(new_job_id="job-original")
        with self.assertRaises(ValueError):
            prepare(request_id="")

    def test_reason_and_authorization_policy_version_are_required(self):
        with self.assertRaises(ValueError):
            prepare(reason="bad")
        with self.assertRaises(PermissionError):
            prepare(authorization=auth(policy_version=""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
