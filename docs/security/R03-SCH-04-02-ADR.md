# ADR R03-SCH-04.2 — Durable CI Scheduling and Dependabot Separation

- Status: **PROPOSED — awaiting explicit approval**
- Date: 2026-11-04
- Decision owner: repository owner
- Scope: CI task orchestration and Dependabot update scheduling only

## Context

The current custom workflow has one global concurrency group with `queue: single`. GitHub documents that this allows one pending run and replaces the existing pending run when another run is queued. Recent repository evidence shows three Dependabot PR validation runs cancelled before jobs were created. The artifact marker used by the 300-second admission gate expires after one day and is not a durable task queue.

GitHub now supports `queue: max` with up to 100 pending runs, but overflow still cancels runs and queue order is based on when a run begins waiting rather than event dispatch time; GitHub does not guarantee ordering by dispatch time.

Sources:
- [GitHub Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [GitHub Actions larger concurrency queues (2026-05-07)](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/)

## Decision proposed

Adopt a layered model:

1. **Authoritative durable queue:** external queue service with transactional task persistence, idempotency, lease/fencing, retry, dead-letter, and reconciliation.
2. **GitHub Actions execution backstop:** use native `queue: max` for bounded buffering, not as the source of truth.
3. **Dependabot arrival shaping:** stagger ecosystem schedules, cap open version-update PRs per ecosystem, retain minor/patch groups, and isolate major upgrades for review.
4. **Exact-task idempotency:** deduplicate only exact logical duplicates. Distinct PRs and distinct head SHAs remain separate tasks.
5. **300-second policy:** retain the current 300-second interval as a minimum inter-start delay during initial migration. Tasks wait with an `eligible_at` timestamp; they are not rejected.
6. **Required check:** preserve the exact `CI result` context and complete validation suite. Prove worker-run check association against the unchanged Ruleset before cutover.
7. **Ruleset:** no Ruleset or branch-protection mutation is authorized.

## Alternatives considered

### A. GitHub concurrency only

Rejected as the sole scheduler. `queue: max` is materially safer than `queue: single`, but it is bounded at 100 pending runs and does not provide an application-owned task ledger, retry/replay, or strict dispatch-time FIFO.

### B. Dependabot-only shaping

Rejected as the sole solution. It lowers the arrival rate but does not guarantee execution of already-created PR validation tasks and does not govern all human PRs or main pushes.

### C. Artifact-backed custom scheduler

Rejected as authoritative state. The current marker is expiring metadata and has no atomic claim, task queue, durable acknowledgement, or recovery path.

### D. External durable queue

Recommended. It is the only compared approach that can provide durable enqueue/claim/ack/replay and an auditable priority queue across PR, main, Dependabot, and manual tasks. It adds external infrastructure, GitHub App credentials, and operational ownership.

### E. Deduplication/coalescing

Required as an adjunct, not a scheduler. Exact duplicate deliveries can be idempotent; distinct PRs or head SHAs cannot be collapsed. Supersession must be explicit and persisted.

## Consequences

Positive:
- Pending validation tasks are not silently replaced.
- Queue state survives artifact expiry and workflow cancellation.
- Priority, fairness, retry, and recovery become explicit.
- Dependabot burst rate can be reduced independently of PR validation correctness.
- Every task can be linked to an exact SHA and workflow run.

Negative:
- Requires a durable database/queue, webhook receiver, GitHub App, monitoring, backups, and incident response.
- Requires proof that dispatched worker runs publish the exact required `CI result` check accepted by the current Ruleset.
- Adds API permission and secret-management obligations.
- The 300-second interval constrains throughput until separately approved.

## Security constraints

- No Administration write permission.
- No Rulesets write permission.
- No branch-protection write permission.
- No Contents write permission unless a separately justified worker design requires it; current proposal does not.
- Actions write is limited to dispatch/inspect operations.
- Pull requests and checks read permissions are limited to scheduler reconciliation.
- Untrusted PR code executes only in GitHub-hosted worker jobs, never in the scheduler service.
- Webhook signature, replay, repository allowlist, token rotation, and audit logging are mandatory.

## Rollout and rollback

Rollout must be dual-observed before cutover:
1. Build and test durable ingress/queue without dispatch authority.
2. Shadow-classify events and compare against GitHub PR/run state.
3. Prove task idempotency, lease fencing, retry, and reconciliation.
4. Prove required-check association on an isolated PR with unchanged Ruleset.
5. Enable worker dispatch for a controlled subset.
6. Verify no duplicate or missing required checks.
7. Only then disable the old admission decision path.

Rollback:
- Stop new external dispatches.
- Preserve queue records and run linkage.
- Restore the prior PR-triggered worker path only after confirming no task is in an ambiguous dispatch state.
- Never delete queued tasks as part of rollback.
- Keep the 300-second cooldown unchanged.
- Do not change Ruleset or required check context.

## Approval required

This ADR is **not approved**. Explicit repository-owner approval is required before:
- provisioning an external scheduler or queue;
- creating/installing a GitHub App or expanding permissions;
- changing workflow triggers/concurrency;
- replacing the current admission mechanism;
- modifying Dependabot scheduling;
- any Ruleset change (which remains separately unauthorized).
