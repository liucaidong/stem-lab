# R03-SCH-04.4 — Native-First CI Scheduling Implementation Plan

## 1. Status and authorization

**Architecture direction accepted; U0–U4 implemented on the SCH.04 working branch. U5 read-only reconciliation is now being added. PR #33 remains unmerged.**

Approved direction:
- remove the global 300-second cooldown and artifact-marker admission delay;
- use GitHub Actions native `queue: max` for the custom required-validation workflow;
- retain `cancel-in-progress: false` and the global concurrency group;
- add bounded current-head reconciliation and recovery;
- shape Dependabot arrival rate;
- keep Ruleset #26463757 and required check `CI result` unchanged.

Not authorized by this plan:
- external Scheduler, durable external queue, webhook service, or dedicated GitHub App;
- Ruleset or branch-protection changes;
- bypassing required validation;
- automatic merge of PR #29–#32;
- changing dependency policy pins without a compatibility review.

Implementation is contained in PR #33 and has not changed production main; the current main SHA and Ruleset remain unchanged.

## 2. Target design

```text
GitHub PR / main push / Dependabot PR
             |
             v
contract-validation.yml
  concurrency:
    group: stem-lab-global-ci
    cancel-in-progress: false
    queue: max
             |
             v
ci-admission (policy / safety only; no cooldown)
       |                         |
       v                         v
validate-contracts      tenant-ed25519-verifier
       |                         |
       +------------+------------+
                    v
             CI result
       (exact required check; fail closed)

Scheduled/manual reconciler
  -> inspect open PR heads + main SHA
  -> inspect runs + CI result
  -> recover missing/cancelled/failed target safely
```

## 3. Implementation work units

### U0 — Freeze and refresh baseline
- Read current main SHA, workflow YAML, admission scripts/tests, Dependabot config, Ruleset, open PR #29–#32 and current head SHAs.
- Capture current required check context and integration identity.
- Confirm working branch contains the full SCH.04 document set.
- Confirm no unrelated branch or Ruleset mutation occurred.
- No production changes.

### U1 — Remove cooldown behavior safely
- Inspect `scripts/ci_admission.py`, `scripts/test_ci_admission.py`, `scripts/validate_ci_workflow_policy.py`, `scripts/test_ci_workflow_policy.py`, and all references to the 300-second interval / artifact marker.
- Define the admission job's remaining purpose: static policy and safe-run admission only.
- Remove artifact-listing logic, marker age calculation, 300-second comparisons, delayed/rejected state, and marker upload/download dependencies.
- Preserve fail-closed behavior for invalid workflow policy, unauthorized event context, or malformed inputs.
- Update tests so no test expects a 300-second delay or marker artifact.
- Add regression assertions that no cooldown/marker implementation remains in the active workflow path.
- Do not remove unrelated artifacts used by benchmark/test reporting.

### U2 — Native concurrency queue migration
- Change only the custom required-validation workflow's queue mode from `single` to `max`.
- Preserve `group: stem-lab-global-ci`.
- Preserve `cancel-in-progress: false`.
- Do not add another concurrency group for required validation.
- Add/update static policy tests to enforce this exact contract.
- Add explicit documentation/monitoring for the 100-pending bound and non-FIFO ordering.
- Do not assume this controls Dependabot's internal/dynamic workflows.

### U3 — Required-check correctness tests
- Preserve the job name `CI result` and exact status context.
- Preserve `if: always()` and dependencies on admission plus every required validation job.
- Test admission failure, missing output, skipped validation, failure, cancellation, timeout, and missing job result.
- Prove every non-success path makes `CI result` fail.
- Prove success is possible only when all required jobs succeed.
- Keep Ruleset #26463757 unchanged.

### U4 — Dependabot arrival shaping
- Update `.github/dependabot.yml` with explicit weekly UTC schedule windows staggered by ecosystem (GitHub Actions, pip, Docker, npm).
- Set `open-pull-requests-limit: 1` for each ecosystem entry.
- Retain minor/patch grouping.
- Keep major upgrades individually reviewable.
- Do not introduce a version-update cooldown as a replacement for the removed CI cooldown.
- Ensure security updates remain independently actionable.
- Validate YAML and Dependabot configuration semantics.
- Update static dependency-policy fixtures only in the same reviewed change as the corresponding legitimate dependency change; do not weaken digest/SHA/hash enforcement.

### U5 — Bounded reconciliation and recovery
- Initial phase is a manual read-only CLI; do not add a scheduled workflow until actual report volume and API cost justify it.
- Inspect all open PR current head SHAs and current main SHA.
- Inspect workflow runs and exact `CI result` checks for those SHAs.
- Classify each target as covered-success, active, recovery-required, or unknown.
- Never recover a target already active or already covered by exact-SHA success.
- Treat unknown/API errors as unknown, not success.
- Initial phase performs no rerun or dispatch. Add write-capable recovery only after read-only classification is validated and separately authorized.
- If a no-job cancelled run cannot be rerun, test the alternative recovery route in isolation before enabling it.
- Bound attempts, apply backoff, respect API rate limits, and emit an audit record with target SHA/run ID/attempt/reason/conclusion.
- Do not create an external App check. The GitHub Actions workflow remains the required-check producer.
- Keep reconciliation cadence low and configurable; initial candidate is every 15 minutes plus manual dispatch, subject to run-volume testing.

### U6 — PR #29–#32 disposition
- Keep all four PRs unmerged until their current head SHAs have complete successful required checks and independent compatibility review.
- PR #29: blocked pending coherent PostgreSQL 18 build/runtime/extension strategy; it currently mixes a PG18 base image with PG17 development/install paths.
- PR #30: plausible dependency update but unvalidated; fix exact-version policy fixture and run complete validation before merge consideration.
- PR #31: inspect current state and obtain a complete run; cancellation is not success.
- PR #32: update the action SHA policy fixture only after verifying the intended immutable upstream action SHA and action major compatibility; then rerun full CI.
- Reassess current PR state before any action; do not assume the historical snapshots remain current.

### U7 — Shadow validation, cutover, and rollback
- Implement all changes on the existing SCH.04 working branch.
- Run YAML/static policy/unit tests locally or in isolated test workflows first.
- Prepare one cohesive implementation PR; avoid repeated pushes that trigger unnecessary CI.
- Verify queue behavior with a controlled burst that stays below the 100-pending bound.
- Separately test overflow detection/reconciliation without creating a run storm.
- Verify PR check association, exact SHA, integration identity, and aggregate semantics.
- Do not merge until all required checks succeed on the exact PR head SHA.
- Rollback through one reviewed PR restoring the previous workflow/admission implementation if required; do not change Ruleset.

## 4. Candidate repository paths

| Path | Planned change |
|---|---|
| `.github/workflows/contract-validation.yml` | queue max; remove marker artifact steps; preserve required jobs |
| `scripts/ci_admission.py` | remove cooldown/marker scheduler behavior; retain policy admission |
| `scripts/test_ci_admission.py` | replace cooldown tests with admission invariants |
| `scripts/validate_ci_workflow_policy.py` | enforce native queue and no cooldown |
| `scripts/test_ci_workflow_policy.py` | regression tests for queue and required-check contract |
| `.github/dependabot.yml` | stagger schedules; PR limit 1/ecosystem |
| `scripts/ci_reconcile.py` (implemented read-only) | inspect current-head coverage and recovery decisions |
| `.github/workflows/ci-reconciliation.yml` (candidate) | scheduled/manual bounded reconciliation |
| `scripts/test_ci_reconcile.py` (implemented) | exact SHA, active-run dedupe, unknown state, recovery bounds |

The reconciler and offline tests are implemented in the SCH.04 working branch; no scheduled workflow has been added.

## 5. Security and permission boundary

- No new GitHub App.
- No new external credentials or database.
- Keep workflow token permissions least-privilege.
- Read-only reconciliation is preferred.
- If rerun capability requires write permission, use the narrowest supported GitHub Actions permission and only after explicit review.
- No Administration, Rulesets, branch-protection, Contents write, or Checks write permission.
- Never execute untrusted PR code in a privileged reconciliation context.
- Never expose `GITHUB_TOKEN`, installation tokens, or secrets in logs/artifacts.

## 6. Acceptance gates

Implementation is accepted only when all are true:
1. No global 300-second cooldown or artifact-marker admission logic remains.
2. Custom workflow concurrency uses the existing global group, `queue: max`, and `cancel-in-progress: false`.
3. `CI result` remains the exact required check and fails closed.
4. Every open PR current head and current main SHA has a successful exact-SHA required check, or is explicitly reported as unresolved.
5. Reconciliation avoids duplicate active/successful runs and handles overflow/cancellation without false success.
6. Dependabot schedules are staggered and each ecosystem's open PR limit is one.
7. Security updates remain actionable.
8. PR #29–#32 are not merged without complete CI and compatibility review.
9. Ruleset #26463757 is unchanged.
10. No external Scheduler/App/queue infrastructure has been introduced.

## 7. Execution order

1. U0 baseline freeze.
2. U1 admission/cooldown removal and tests.
3. U2 native queue migration and policy tests.
4. U3 required-check correctness.
5. U4 Dependabot governance.
6. U5 reconciliation implementation and fault tests.
7. U6 PR #29–#32 disposition.
8. U7 isolated burst, overflow, recovery, and final acceptance.
9. One cohesive implementation PR; no merge until complete CI success.

**Current state:** U0–U4 implemented in PR #33; exact-SHA required CI passed on head fb31d718f38613ebb3ce7d1cb49aec60dbfd8d58. U5 read-only CLI and offline tests are being added. No recovery writes, scheduled workflow, Ruleset changes, or main-branch changes are authorized.
