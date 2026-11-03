# ADR R03-SCH-04.2 — Native-First CI Scheduling

- Status: **Accepted direction; implementation pending**
- Decision date: 2026-11-04
- Scope: `liucaidong/stem-lab` custom required-validation workflow and Dependabot arrival shaping

## Context

The audit found that the current `queue: single` semantics can replace an older pending run with a newer pending run. The existing artifact marker implements a 300-second admission interval but is not a durable queue, atomic lock, or task ledger. Dependabot dynamic workflows also operate outside the custom workflow's concurrency group.

The earlier proposal introduced an external Scheduler, GitHub App, durable database, webhooks, task leases/fencing, retries, and dead-letter handling. That is technically capable but disproportionate to the immediate requirement: ensure every open PR's current head SHA and current main SHA obtain a truthful required CI result.

## Decision

1. Remove the global 300-second cooldown.
2. Use GitHub Actions native concurrency with:
   ```yaml
   concurrency:
     group: stem-lab-global-ci
     cancel-in-progress: false
     queue: max
   ```
3. Retain one global concurrency group for the required custom validation workflow.
4. Add bounded reconciliation of current open PR head SHAs and main SHA against workflow runs and the exact `CI result` check.
5. Avoid duplicate runs when a matching run is queued or in progress.
6. Recover cancelled, failed, timed-out, or missing-check targets through an approved exact-SHA recovery path.
7. Stagger Dependabot ecosystem schedules and reduce each ecosystem's open version PR limit to one; retain minor/patch grouping and individually review major updates.
8. Keep the exact required check `CI result` and Ruleset #26463757 unchanged.
9. Do not create an external Scheduler, database, webhook receiver, or GitHub App for this phase.

## Rationale

- Removing cooldown eliminates artificial delay and the need for delayed task eligibility.
- `queue: max` is materially safer than `queue: single` for bursts, while remaining native and low-maintenance.
- The queue is bounded (100 pending) and not strict dispatch FIFO, so reconciliation is mandatory.
- The merge gate needs current-head coverage, not execution of every obsolete intermediate commit.
- Dependabot arrival shaping reduces bursts but is not mistaken for a correctness guarantee.
- A small reconciliation mechanism addresses native queue overflow/missing checks without operating a second control plane.

## Consequences

Positive:
- No external service, database, GitHub App, or secret-management plane.
- No 300-second artificial delay.
- Fewer moving parts and lower operational cost.
- Current PR head coverage becomes an explicit auditable invariant.

Limitations:
- Native queue is bounded at 100 pending.
- Native ordering is not guaranteed by event dispatch time.
- Intermediate superseded PR SHAs are not guaranteed to execute.
- Reconciliation must be bounded, idempotent, and observable.
- GitHub-managed Dependabot dynamic runs are not serialized by this workflow's concurrency group.

## Guardrails

- `cancel-in-progress: false` remains mandatory.
- `CI result` fails closed on failed, cancelled, skipped, missing, or non-admitted dependencies.
- A missing check or API uncertainty is never success.
- Recovery must prove exact SHA and required-check integration identity.
- No Ruleset, branch protection, or required-check mutation.
- No workflow implementation until the revised plan and migration tests are approved.

## Rejected alternatives

- External durable Scheduler: rejected as disproportionate for current scope; reopen only with measured native queue/reconciliation failure or a new requirement to execute every event SHA.
- Artifact marker as queue: rejected; not durable or atomic.
- `queue: single`: rejected due pending replacement semantics.
- Dependabot staggering alone: rejected as a correctness mechanism.

## Re-entry criteria

Reopen this ADR if:
- queue overflow repeatedly leaves current PR heads without required checks;
- reconciliation cannot meet the agreed recovery SLA;
- a strict every-event-SHA execution requirement is introduced;
- GitHub native concurrency/recovery proves insufficient under measured workload.
