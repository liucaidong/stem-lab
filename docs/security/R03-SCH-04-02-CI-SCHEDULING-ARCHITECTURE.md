# R03-SCH-04.2 — CI Scheduling Architecture

## 1. Decision context

This is an architecture proposal only. No workflow, Dependabot configuration, Ruleset, permission, or scheduler was changed.

Audit baseline:
- Main SHA: `8e749b55899d3626e39a31e1e438e3db682f5219`
- Required Ruleset check: `CI result`, strict status checks.
- Current custom workflow: `contract-validation.yml`.
- Current global concurrency: `stem-lab-global-ci`, `cancel-in-progress: false`, `queue: single`.
- Current cooldown: 300 seconds, implemented using an expiring artifact marker.
- Observed recent Dependabot burst: PR #29–#32; three cancelled runs, one policy failure.
- Eight separate Dependabot dynamic runs occurred outside the custom concurrency group.

## 2. GitHub-native concurrency facts (current documentation)

GitHub documents the following behavior:
- `queue: single` permits at most one pending run/job in a concurrency group. A newer queued run cancels and replaces the existing pending run.
- `queue: max` permits up to 100 pending runs/jobs. Once full, additional runs are cancelled.
- The concurrency queue is FIFO according to the time a run starts waiting in the group, not dispatch time; GitHub explicitly warns that ordering is not guaranteed because start times can vary.
- `queue: max` cannot be combined with `cancel-in-progress: true`.

Sources:
- [GitHub Actions concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [GitHub changelog: larger concurrency queues, 2026-05-07](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/)

**Implication:** current `queue: single` is a direct task-retention risk. The PR #29–#31 cancellation pattern is consistent with pending-run replacement. Native `queue: max` materially improves bounded buffering, but is not an unlimited or durable queue: the 101st pending run can still be cancelled and ordering is not strict dispatch FIFO.

## 3. Options assessment

| Option | FIFO guarantee | Task-loss risk | Parallelism / isolation | Recovery / observability | Cost / complexity | Decision |
|---|---|---|---|---|---|---|
| A. Native concurrency only (`queue: max`) | Bounded queue; order not guaranteed by dispatch time | Medium: 100 pending cap; overflow cancellation; no durable task ledger | Simple single group serializes custom runs; separate groups can bypass global serialization | GitHub run history only; no durable enqueue/claim/replay semantics | Very low | Adopt as execution backstop, not as sole scheduler |
| B. Dependabot/custom CI layering | Not a CI queue | Medium-low for PR burst if schedules/PR limits are staggered; does not itself preserve every validation task | Separates dependency discovery from PR validation; dynamic Dependabot remains GitHub-managed | Dependabot config and PR history are visible; no global scheduler | Low | Adopt |
| C. Custom Actions admission/scheduler using artifacts | No | High: artifact TTL, non-atomic marker, one-page query, no queue ledger/replay | Same workflow group; dynamic workflows outside it | Weak; artifact metadata is not authoritative task state | Medium, deceptively fragile | Reject current design as scheduler; retain only as temporary throttle if needed |
| D. Independent durable queue + GitHub App worker | FIFO can be guaranteed within priority class by the queue store | Low if webhook ingestion is durable, idempotent, acknowledged only after persistence, and reconciled | Explicit global concurrency, priorities, leases, and worker limits | Strong task ledger, run linkage, retry and dead-letter records | High; external service and App operations | Recommended authoritative scheduler |
| E. Event deduplication and safe coalescing | Not a scheduler by itself | Reduces duplicate work; unsafe coalescing can lose distinct SHA validations | Exact duplicate tasks can collapse; different PR/head SHA remain distinct | Strong if every dedup/supersede decision is persisted | Low-medium | Required adjunct to D |

### A. Native concurrency

Set the custom validation worker to `queue: max` only after the scheduler contract and integration tests are approved. It provides a bounded GitHub-managed queue of up to 100 pending executions. It is an important safety net if the external dispatcher sends more than one request or if a task is delayed.

Do not treat it as:
- an unlimited queue;
- a durable task ledger;
- strict event-dispatch FIFO;
- a guarantee against overflow cancellation;
- a control over GitHub-managed Dependabot dynamic runs.

### B. Dependabot and custom CI layering

Dependabot version-update discovery is a separate control plane. Stagger the four ecosystem schedules, lower each ecosystem's open-PR limit, and keep minor/patch grouping. Major upgrades should remain individually visible and be subject to explicit compatibility review.

Dependabot supports custom weekly day/time/timezone schedules, open PR limits, groups, and version-update cooldowns. Its cooldown applies to version updates, not security updates; security updates must remain independently actionable.

Sources:
- [Optimizing Dependabot PR creation](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/optimizing-pr-creation-version-updates)
- [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)

Layering reduces the arrival burst but does not replace PR task persistence.

### C. Custom admission

The existing artifact marker is not suitable as the authoritative scheduler:
- it expires after one day;
- it is not a compare-and-set lock;
- it does not store queued tasks;
- it has no worker lease, acknowledgement, or retry record;
- it does not recover cancelled tasks;
- it fails closed but does not re-enqueue deferred work.

The 300-second policy can be preserved as a **minimum inter-start interval** in the scheduler. A task that arrives during the interval must transition to `READY_WAITING` with an `eligible_at` timestamp, not be rejected and forgotten. The current marker can be retained temporarily as telemetry or a secondary guard during migration, but must be removed as the source of truth after cutover.

### D. Recommended durable scheduler

Recommended logical components:

1. **Event ingress:** GitHub App webhook receiver for `pull_request`, `push`, and approved manual task events. Verify webhook signatures and repository identity.
2. **Durable task store:** transactional queue with unique task identity, priority, enqueue timestamp, exact SHA/ref, payload digest, attempt counter, and state history.
3. **Scheduler:** priority-aware FIFO with bounded aging; reserves a worker lease and enforces the 300-second minimum inter-start interval.
4. **Dispatcher:** invokes the GitHub Actions worker using an installation token with narrowly scoped permissions. It records the returned workflow/run identifier before acknowledging dispatch.
5. **Worker workflow:** runs the complete validation suite; no validation jobs are removed. It reports terminal outcome to the scheduler through a signed callback or authenticated API.
6. **Reconciler:** periodically compares durable tasks with GitHub workflow runs/checks and repairs missing dispatches or stale leases.
7. **Operator surface:** task lookup by PR, SHA, delivery ID, run ID, and state; explicit retry/cancel operations; dead-letter queue for exhausted transient failures.

The durable queue is authoritative. GitHub Actions is the execution substrate, not the queue database.

### Required-check compatibility gate

The existing Ruleset requires the exact check context `CI result` from the GitHub Actions integration. The worker design must preserve that context and must prove that a dispatched worker run on an exact PR head SHA produces the required check accepted by the unchanged Ruleset.

Before cutover, an isolated test PR must verify:
- the check is attached to the intended PR commit;
- the context remains exactly `CI result`;
- the integration identity is the one required by the Ruleset;
- there is no permanently pending check from an ingress-only workflow;
- failure, cancellation, and missing worker result cannot yield success.

If workflow_dispatch cannot satisfy those properties, retain the PR-triggered workflow as the required-check owner and have its lightweight admission job await a durable queue lease; do not weaken or rewrite the Ruleset to accommodate the scheduler.

### E. Deduplication and coalescing

Task identity should be deterministic and scoped to the validation target, for example:

```text
task_key = SHA256(
  repository_id || event_type || workflow_contract_version ||
  pull_request_number || head_sha || base_sha || ref
)
```

Webhook delivery ID is separately unique and stored for replay/audit. Exact duplicate deliveries for the same task key are idempotent. Distinct PR numbers or distinct head SHAs are distinct tasks and must not silently replace one another.

A task can be marked `SUPERSEDED` only when the system has durably recorded the replacement task and the supersession reason. A superseded/cancelled task is never reported as successful. The audit history is immutable.

## 4. Recommended priority policy

| Priority | Task class | Policy |
|---|---|---|
| P0 | Main branch push validation | Highest priority; never silently superseded |
| P1 | Human PR validation; Dependabot security update PR | High priority; all current head SHAs must receive complete validation |
| P2 | Dependabot major update PR | Normal-high; individually reviewed and fully validated |
| P3 | Dependabot minor/patch update PR | Normal; grouping and staggered schedule reduce volume |
| P4 | Manual non-urgent validation | Normal-low; operator can request an explicit priority within authorization limits |

Fairness:
- FIFO within each priority class using durable enqueue sequence.
- Aging promotes long-waiting tasks to prevent starvation.
- A running validation is non-preemptive by default.
- A newer task never cancels an older running task merely to save compute.
- Main priority affects the next available worker; it does not silently erase already-enqueued PR tasks.

## 5. Scheduling and throughput

The 300-second rule is retained as a global minimum interval between validation task starts during the initial migration. It becomes a scheduler delay, not a rejection decision.

The worker concurrency limit and the inter-start interval are separate controls:
- concurrency controls simultaneous active validation workers;
- cooldown controls minimum spacing between starts;
- Dependabot cadence controls update arrival rate;
- the durable queue absorbs temporary bursts.

Capacity planning must use observed median/p95 validation duration and burst rate. The current main validation took about 2m46s from run creation to completion, while the cooldown is 5m; initial throughput is therefore intentionally below one task per 5 minutes. This should be measured before any change to the 300-second value.

## 6. Security and permission boundary

Proposed GitHub App permissions, subject to endpoint-by-endpoint verification:
- Actions: read/write, only to dispatch and inspect worker runs.
- Contents: read, only if worker checkout requires it.
- Pull requests: read, for PR/head metadata.
- Checks: read, for reconciliation; write only if a check-run API is deliberately selected and its integration identity is accepted by the Ruleset.
- Metadata: read.

No Contents write, Administration write, Rulesets write, or branch-protection write permission is proposed. No Ruleset mutation is part of this architecture.

External queue security:
- webhook HMAC signature verification;
- replay protection via delivery ID;
- least-privilege installation token;
- secret rotation;
- tenant/repository allowlist;
- payload minimization;
- encrypted storage;
- immutable audit trail;
- bounded retries and dead-letter alerting;
- no untrusted PR code executed by the scheduler service.

## 7. Decision recommendation

**Recommend D + A + B + E: durable external queue as source of truth, GitHub `queue: max` as a bounded execution backstop, staggered Dependabot scheduling, and exact-task idempotency.**

Why:
- A alone cannot meet the no-loss requirement because the queue is capped at 100 and GitHub warns ordering is not guaranteed by dispatch time.
- B reduces burst volume but does not guarantee task execution.
- C's artifact marker cannot provide durable task state or atomic claims.
- D is the only compared option that can provide durable enqueue/claim/ack/replay and an auditable priority queue.
- E prevents duplicate work without collapsing distinct PR/SHA tasks.

Trade-off: D introduces an external service, database, GitHub App, operational monitoring, and secret management. If the owner rejects that cost, the fallback is a native-first `queue: max` + periodic PR/main reconciliation design, but it must be labelled **eventual current-head coverage**, not strict preservation of every event task.

## 8. Approval gates

This proposal does not authorize implementation. Before SCH.04.4:
1. Approve or reject the external durable scheduler.
2. Approve the GitHub App permission boundary.
3. Approve the priority/fairness policy.
4. Approve the required-check integration strategy after a non-production or isolated-branch proof.
5. Keep the 300-second inter-start interval unchanged until separately reviewed.
6. Keep Ruleset #26463757 unchanged.
