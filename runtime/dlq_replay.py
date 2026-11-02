"""R03.52.5 DLQ replay authorization preflight reference.

This module creates an auditable replay plan only. A production Store must
re-authorize and atomically lock/update the source DLQ row, create the new Job,
increment replay_count, and persist the immutable audit record in one transaction.
"""
from __future__ import annotations
from dataclasses import dataclass


REPLAY_ACTION = "worker.dlq.replay"


@dataclass(frozen=True)
class ReplayAuthorizationDecision:
    actor_id: str
    tenant_id: str
    job_id: str
    action: str
    allowed: bool
    policy_version: str


@dataclass(frozen=True)
class ReplayPlan:
    tenant_id: str
    source_job_id: str
    new_job_id: str
    request_id: str
    actor_id: str
    reason: str
    replay_number: int
    authorization_policy_version: str


def prepare_dlq_replay(
    *,
    tenant_id: str,
    source_job_id: str,
    source_status: str,
    replay_count: int,
    replay_limit: int,
    request_id: str,
    new_job_id: str,
    actor_id: str,
    reason: str,
    authorization: ReplayAuthorizationDecision,
) -> ReplayPlan:
    if source_status != "dead_lettered":
        raise ValueError("only dead-lettered jobs may be replayed")
    if replay_count < 0 or replay_limit < 1:
        raise ValueError("invalid replay counter or limit")
    if replay_count >= replay_limit:
        raise ValueError("DLQ replay limit exhausted")
    if not request_id or len(request_id) > 128:
        raise ValueError("request_id must be 1..128 characters")
    if not new_job_id or len(new_job_id) > 128 or new_job_id == source_job_id:
        raise ValueError("replay must use a distinct new Job ID")
    if not actor_id or len(actor_id) > 128:
        raise ValueError("actor_id must be 1..128 characters")
    if not reason or len(reason.strip()) < 8 or len(reason) > 512:
        raise ValueError("replay reason must be 8..512 characters")
    if authorization.allowed is not True:
        raise PermissionError("DLQ replay authorization denied")
    if authorization.action != REPLAY_ACTION:
        raise PermissionError("authorization action mismatch")
    if authorization.actor_id != actor_id:
        raise PermissionError("authorization actor mismatch")
    if authorization.tenant_id != tenant_id or authorization.job_id != source_job_id:
        raise PermissionError("authorization resource scope mismatch")
    if not authorization.policy_version or len(authorization.policy_version) > 128:
        raise PermissionError("authorization policy version is required and bounded")
    return ReplayPlan(
        tenant_id=tenant_id,
        source_job_id=source_job_id,
        new_job_id=new_job_id,
        request_id=request_id,
        actor_id=actor_id,
        reason=reason.strip(),
        replay_number=replay_count + 1,
        authorization_policy_version=authorization.policy_version,
    )
