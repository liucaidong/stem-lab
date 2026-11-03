# R03-SCH-04.4 — Scheduler Implementation Plan (Approval-Gated)

## 1. Status

**Plan only — implementation is NOT authorized.**

The architecture ADR in SCH.04.2 remains PROPOSED. This plan assumes the recommended hybrid:
- durable external task queue as authoritative state;
- GitHub Actions `queue: max` as bounded execution backstop;
- Dependabot arrival shaping;
- exact-task idempotency;
- 300-second inter-start interval retained as a delay, not a rejection.

No code, workflow, Dependabot configuration, App permission, Ruleset, or infrastructure was changed while producing this plan.

## 2. Design constraints and GitHub API facts

1. GitHub's workflow dispatch endpoint requires GitHub App repository permission `Actions: write`; its `ref` parameter is a branch or tag.
2. GitHub's workflow-run rerun endpoint requires `Actions: write`.
3. GitHub documents that reruns use the same `GITHUB_SHA` and `GITHUB_REF` as the original event. This is preferable for recovering a cancelled PR workflow because it preserves the original event context and commit identity.
4. Reruns are available for up to 30 days and are limited to 50 attempts per workflow run.
5. Checks API read requires `Checks: read`; creating/updating a check run requires a GitHub App with `Checks: write`.

Sources:
- [Create workflow dispatch event](https://docs.github.com/en/rest/actions/workflows)
- [Re-run workflow run](https://docs.github.com/en/rest/actions/workflow-runs)
- [Re-running workflows and jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [Checks API permissions](https://docs.github.com/en/rest/checks/runs)

**Required-check rule:** do not use the GitHub Checks API to create a parallel `CI result` check under the external scheduler App. The current Ruleset is configured for the GitHub Actions integration. Prefer GitHub Actions to remain the producer of the required `CI result` context. Any alternate check producer requires a separate Ruleset integration review and is outside this plan.

## 3. Proposed GitHub App boundary

Candidate installation scope: only `liucaidong/stem-lab`.

| Permission / event | Proposed level | Purpose |
|---|---|---|
| Actions | Read + Write | Inspect workflow runs/jobs; rerun cancelled runs; dispatch worker only if integration proof requires it |
| Pull requests | Read | Read PR number, head/base SHA, branch, open/closed state |
| Checks | Read | Inspect `CI result` and other check conclusions |
| Contents | Read | Read workflow/ref metadata if required |
| Metadata | Read | Repository identity |
| Webhook: pull_request | Subscribe | Capture opened/synchronize/reopened/ready_for_review/closed |
| Webhook: push | Subscribe | Capture main branch pushes |
| Webhook: workflow_run | Subscribe | Correlate task records with run IDs and conclusions |

Explicitly excluded:
- Administration: none;
- Rulesets / branch protection: no write;
- Contents: no write;
- Checks: no write;
- Actions write is limited to run rerun/dispatch operations.

The GitHub App must verify webhook signatures, enforce a repository allowlist, persist the delivery ID, and reject replayed deliveries idempotently.

## 4. Component plan

| Component | Candidate path / location | Responsibility | Dependencies |
|---|---|---|---|
| Scheduler service | Separate private deployment repository/service (name not created) | Webhook receiver, queue API, scheduler, reconciler, audit API | GitHub App, durable database/queue, secret manager |
| Task schema | Scheduler service `db/migrations/001_ci_task_ledger.sql` | Tasks, deliveries, attempts, leases, outbox, audit events | Transactional database |
| Event normalizer | Scheduler service `src/events/normalize.py` | Normalize PR/push/manual payloads and exact SHA | Webhook signature verification |
| Task identity | Scheduler service `src/tasks/identity.py` | Stable task key and duplicate detection | Canonical JSON / SHA-256 |
| Queue repository | Scheduler service `src/tasks/repository.py` | Atomic enqueue, claim, lease, ack, retry, dead-letter | DB transaction and row locks |
| Priority scheduler | Scheduler service `src/scheduler/dispatch.py` | P0–P4 priority, FIFO per class, aging, 300-second eligibility | Queue repository |
| GitHub client | Scheduler service `src/github/actions.py` | Inspect runs, rerun cancelled runs, optional dispatch fallback | App installation token |
| Reconciler | Scheduler service `src/reconcile/workflow_runs.py` | Find orphaned, cancelled, missing, or stale run/task linkage | Actions:read/write, Checks:read |
| Worker workflow | `.github/workflows/contract-validation.yml` (evolve in place) | Preserve complete validation and `CI result` | Scheduler client / approved dispatch model |
| Admission client | `scripts/ci_scheduler_client.py` | Request/heartbeat/complete scheduler lease | Scheduler API, short-lived signed token |
| Task identity tests | `scripts/test_ci_task_identity.py` | Duplicate delivery and distinct SHA invariants | Pure unit tests |
| State-machine tests | `scripts/test_ci_scheduler_state_machine.py` | Allowed transitions, terminal-state immutability | Pure unit tests |
| API fault tests | `scripts/test_ci_scheduler_api_faults.py` | 429/5xx/timeout/403/retry-after | Fake GitHub client |
| Concurrency tests | `scripts/test_ci_scheduler_concurrency.py` | Atomic claims, leases, fencing tokens | Transactional test DB |
| Fault-injection suite | `scripts/test_ci_scheduler_fault_injection.py` | Runner loss, cancellation, rerun, artifact loss, crash recovery | Test DB + fake Actions adapter |
| Policy validator | `scripts/validate_ci_scheduler_policy.py` | Assert no bypass, permissions, required jobs and concurrency policy | Workflow YAML parser |

The service repository/path is a proposal only. Do not create it until the external scheduler decision and hosting provider are approved.

## 5. Required-check integration — critical proof gate

The current required check is `CI result`, Ruleset ID `26463757`, with strict checks enabled.

Preferred recovery path for an existing run:
1. Capture the PR/push event and persist the task.
2. Correlate the event with the GitHub Actions run ID.
3. If the original run is cancelled before jobs or is otherwise retryable, call the workflow-run rerun endpoint.
4. GitHub reruns the original event using the same SHA and ref.
5. Observe the new run attempt and require all original validation jobs plus `CI result` to succeed.

This preserves the original PR event context better than dispatching a new workflow against a moving branch.

Before relying on it, a controlled test MUST prove that GitHub accepts a rerun of a workflow run cancelled before any job was created (as observed for PR #29–#31). The test must confirm:
- same original SHA and ref;
- a new run attempt is created;
- the PR receives the required `CI result` check;
- the check's integration identity remains GitHub Actions;
- no duplicate check is left pending;
- a failed/cancelled rerun remains non-success.

Fallback if the no-job rerun is not supported:
- test a worker dispatch against a PR head branch;
- verify the run's `head_sha` and check association match the exact intended PR head;
- if not, retain the original PR-triggered workflow as the required-check owner and use it as the scheduler-controlled worker.
- Do not create a check through the external App; that would use a different integration identity and is not accepted by this plan.

## 6. Migration work units

### U0 — Baseline freeze and evidence capture
- Record current main SHA, PR heads, Ruleset, workflow IDs, and current required-check context.
- Save exact current YAML and static policy fixtures.
- No changes to main or Ruleset.

### U1 — Durable task store and schema
- Implement task envelope, delivery ledger, attempts, lease/fencing token, scheduler outbox, terminal audit.
- Enforce unique task key and unique delivery ID.
- Add transactional claim and immutable transition log.
- Verify restart and concurrent-writer behavior.

### U2 — Webhook ingress in shadow mode
- Subscribe to PR, push, and workflow_run events.
- Verify HMAC signatures.
- Persist all supported events before returning 2xx.
- No Actions rerun/dispatch authority in this unit.
- Compare task ledger to actual GitHub events and current open PR heads.
- Prove idempotent duplicate delivery handling.

### U3 — GitHub Actions adapter and recovery
- Implement Actions run lookup, run attempt inspection, rerun, and dispatch fallback.
- Use Actions:read/write only after explicit App permission approval.
- Test cancelled-before-job rerun.
- Verify same SHA/ref and required check identity.
- Add rate-limit handling and bounded retry.

### U4 — Scheduler and 300-second throttle
- Implement priority classes, FIFO per class, aging, and worker limit.
- Preserve 300 seconds as `eligible_at` delay.
- Never mark a task complete when deferred.
- Add lease expiry, fencing token, retry and dead-letter behavior.
- Ensure active validation is non-preemptive by default.

### U5 — Workflow integration
- Keep `validate-contracts` and `tenant-ed25519-verifier` unchanged in coverage and semantics.
- Preserve job names and exact aggregate context `CI result`.
- Replace artifact-marker decision as the authoritative queue state only after shadow parity.
- Set native custom workflow queue to `max` only after the overflow/reconciliation test.
- No simultaneous old and new admission decisions.
- Do not change Ruleset.

### U6 — Dependabot governance rollout
- Stagger weekly schedule windows.
- Reduce each ecosystem's open version-update PR limit to one.
- Retain minor/patch groups.
- Keep major updates individually visible.
- Ensure security updates are not delayed by version-update cooldown.
- Fix exact-version static policy fixtures without weakening immutable SHA/digest/hash checks.
- Ensure Python direct requirements and generated hash lock versions agree.

### U7 — Reconciliation and operations
- Periodically compare durable task state, workflow runs, check runs, and open PR head SHAs.
- Detect orphaned task, orphaned run, missing required check, stale lease, cancelled run, exhausted retry, and queue overflow.
- Provide operator commands/API for inspect, retry, cancel, and dead-letter replay.
- Alert on oldest task age and missing required check.

## 7. File/interface contract

### Scheduler API (proposed)

| Method | Path | Purpose |
|---|---|---|
| POST | `/webhooks/github` | Receive signed GitHub webhook |
| POST | `/v1/tasks` | Create an operator-authorized manual task |
| GET | `/v1/tasks/{task_id}` | Read task state and attempts |
| POST | `/v1/tasks/{task_id}/retry` | Explicit retry |
| POST | `/v1/tasks/{task_id}/cancel` | Authorized cancellation |
| POST | `/internal/tasks/claim` | Atomic worker claim |
| POST | `/internal/tasks/{task_id}/heartbeat` | Renew current lease |
| POST | `/internal/tasks/{task_id}/complete` | Record terminal worker result |
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Dependency readiness |
| GET | `/metrics` | Queue/worker/API metrics |

### Database tables (proposed)

- `ci_tasks`
- `ci_task_deliveries`
- `ci_task_attempts`
- `ci_task_leases`
- `ci_task_events` (append-only)
- `ci_scheduler_outbox`
- `ci_task_dead_letters`

The scheduler database is a separate control-plane store. Do not reuse the STEM product tenant database or any tenant-scoped application schema.

## 8. API rate-limit and retry plan

- Respect `Retry-After`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`.
- Use conditional requests and ETags where available.
- Batch run/check lookups and cache PR metadata.
- Treat 429 and transient 5xx/network errors as retryable.
- Treat 401/403 permission failures as configuration incidents, not retry storms.
- Treat 404 as ambiguous until repository/run lifecycle is reconciled; never infer task success.
- Use bounded exponential backoff with jitter.
- Every API attempt records method, endpoint class, status, request ID, latency, and retry decision without logging tokens or secrets.

## 9. No-double-execution and no-pending-check migration

1. Build the new service in shadow mode; it does not dispatch.
2. Compare its normalized task list against actual PR/push events and Actions runs.
3. Complete all state-machine and API adapter tests using a test repository or isolated branch.
4. Prepare one migration PR that changes workflow integration and policy fixtures together.
5. During the cutover window, pause scheduler dispatch; do not merge a half-migrated state.
6. Enable the new authoritative scheduler only after the worker path is deployed and the old admission decision is disabled in the same controlled rollout.
7. Reconcile every open PR head and current main SHA after cutover.
8. Verify one and only one authoritative `CI result` outcome per task/attempt.
9. Keep a watchdog for any required check that remains pending beyond the agreed SLA.
10. Do not merge the migration PR until all required checks pass on its exact head SHA.

## 10. Rollback plan

- Disable external dispatch/rerun actions first.
- Preserve all durable tasks and audit events.
- Stop claiming new tasks; allow active validation jobs to finish.
- Restore the previous workflow trigger/admission path in a single reviewed rollback PR if necessary.
- Do not delete queue rows or task attempts.
- Reconcile ambiguous dispatches against Actions run IDs before retrying.
- Keep the 300-second policy unchanged.
- Do not change Ruleset #26463757.
- Verify the exact `CI result` context is again produced by the original workflow before declaring rollback complete.

## 11. Implementation acceptance gate

Implementation may begin only after explicit approval of:
- external durable queue architecture and hosting/provider;
- GitHub App creation/installation and permission list;
- scheduler database and backup/retention design;
- priority/fairness policy;
- required-check rerun/dispatch integration proof;
- migration/cutover/rollback plan.

No approval is inferred from the request to continue the audit. No GitHub App, infrastructure, workflow, Dependabot configuration, or Ruleset has been changed in SCH.04.4.
