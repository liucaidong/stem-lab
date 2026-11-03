# R03-SCH-04.2 — CI Scheduling Contract

## 1. Status

**Approved target contract; implementation not yet performed.**

This contract supersedes the prior external-scheduler task-ledger contract. Scheduling is GitHub-native. There is no external queue, webhook ingress, task database, lease service, or 300-second delay.

## 2. Event and validation identity

A validation target is identified by:
- repository identity;
- event class (`pull_request`, `main_push`, or authorized `manual`);
- PR number where applicable;
- exact head SHA;
- base SHA where relevant;
- workflow/validation contract version.

A GitHub event delivery may be observed more than once. Recovery must avoid starting duplicate work when a run for the same target is already queued or running.

Different PR numbers or different current head SHAs are distinct validation targets. Never treat one PR's successful check as evidence for another PR or a different SHA.

For merge-gate coverage, the authoritative target is each open PR's current head SHA and the current main SHA. Superseded historical PR head SHAs need not be executed solely to preserve event history.

## 3. State model

The implementation may use GitHub run/check state rather than a separate persisted state machine. The following logical states are required:

```text
DISCOVERED
  -> QUEUED
  -> IN_PROGRESS
  -> SUCCEEDED

DISCOVERED / QUEUED / IN_PROGRESS
  -> FAILED | CANCELLED | TIMED_OUT

FAILED | CANCELLED | TIMED_OUT | MISSING_CHECK
  -> RECOVERY_PENDING
  -> QUEUED / IN_PROGRESS
  -> SUCCEEDED or terminal failure
```

Terminal success is valid only when all required jobs and the aggregate `CI result` succeed for the exact target SHA.

A cancelled run, a run with no jobs, a skipped validation job, or a missing check is never success.

## 4. Native concurrency contract

- Global group: `stem-lab-global-ci` for the custom required-validation workflow.
- `cancel-in-progress: false` is mandatory.
- Target queue mode: `queue: max`.
- The queue is bounded to 100 pending runs; overflow can cancel additional runs.
- Native ordering is not strict event-dispatch FIFO.
- No other concurrency group may be used to bypass serialization for required validation without explicit review.
- Dependabot internal/dynamic workflows are not assumed to be covered by this custom group.
- No cooldown interval, delayed eligibility timestamp, artifact marker, or sleep-based throttle is permitted in the target architecture.

## 5. Required check contract

The required check remains exactly `CI result`, produced by the GitHub Actions integration accepted by the unchanged Ruleset #26463757.

The aggregate result MUST:
- run with `if: always()`;
- depend on admission and all required validation jobs;
- fail if admission fails or does not explicitly admit;
- fail if any required job is failure, cancelled, skipped, timed out, or missing;
- succeed only when every required job succeeds;
- never convert a deferred, absent, or cancelled task into success.

No Ruleset change and no external App-created check is allowed in this phase.

## 6. Reconciliation contract

Reconciliation MUST cover:
- every open PR's current head SHA;
- current main SHA;
- the workflow run and exact required check associated with each target.

For each target, classify:
- `COVERED_SUCCESS`: exact SHA has successful required `CI result`;
- `ACTIVE`: exact SHA has a queued or in-progress authoritative run;
- `RECOVERY_REQUIRED`: run is cancelled/failed/timed out, or required check is missing/incomplete;
- `UNKNOWN`: API/permission/rate-limit state prevents a safe conclusion.

Rules:
1. `UNKNOWN` is never success.
2. Do not dispatch when a matching run is active.
3. Do not dispatch when exact-SHA `COVERED_SUCCESS` exists.
4. Recover only the current open PR head or current main SHA; do not replay obsolete PR heads by default.
5. Bound recovery attempts and apply backoff for API/rate-limit failures.
6. Record target SHA, run ID, run attempt, recovery reason, and final conclusion in logs/artifacts.
7. A recovery operation must preserve or prove the exact SHA and required-check association.
8. If exact association cannot be proven, stop and require operator intervention.

## 7. Dependabot governance contract

- Weekly update schedules are staggered by ecosystem and expressed in UTC.
- Each ecosystem entry has `open-pull-requests-limit: 1`.
- Minor/patch updates remain grouped.
- Major updates remain individually reviewable.
- Security updates remain actionable and are not blocked by version-update cooldown.
- Dependabot scheduling is arrival shaping only; it cannot replace CI validation.
- Static dependency policy fixtures must be updated consistently with legitimate dependency PRs, without weakening digest, immutable SHA, or hash-lock verification.

## 8. Failure and retry policy

Retry/recovery may be considered for:
- runner or infrastructure failure;
- workflow cancellation;
- transient GitHub API/network failure;
- missing required check after a run should have completed.

Do not automatically retry deterministic test/policy failures without a code or policy correction. Do not retry 401/403 permission failures in a loop. Respect GitHub rate limits and bound all retries.

## 9. Security and permissions

- Keep repository token permissions least-privilege.
- No GitHub App is required by the target architecture.
- No Actions write permission is added to a new service.
- No Administration, Rulesets, branch-protection, Contents write, or Checks write permission is added.
- Reconciliation should use the existing authorized GitHub connector/operator context or a narrowly scoped GitHub Actions token for read-only inspection and approved reruns.
- Untrusted PR code executes only in GitHub-hosted runner jobs.

## 10. Acceptance invariants

- No global 300-second cooldown remains.
- No artifact marker is treated as queue state.
- `queue: max` is configured on the required workflow.
- Current PR head and main SHA receive complete CI coverage.
- No cancelled, skipped, missing, or failed run is represented as success.
- Exact `CI result` name and integration remain unchanged.
- Overflow and recovery are observable and bounded.
- Dependabot arrival shaping is configured and validated.
- Ruleset #26463757 is unchanged.
