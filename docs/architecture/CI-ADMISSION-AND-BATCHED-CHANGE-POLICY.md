# STEM Lab — CI Scheduling and Batched Change Policy

**Status:** Mandatory engineering policy  
**Scope:** All GitHub Actions workflows and all changes to this repository
**Scheduling model:** GitHub Actions native repository-wide concurrency queue

## 1. Objective

Serialize the repository's contract-validation workload without cancelling an
in-progress validation run or repeatedly replacing a pending run. Preserve normal
automatic pull-request and `main`-branch triggers while batching engineering changes
so avoidable workflow runs are minimized.

This policy describes the active queue-based architecture. The former 600-second
cooldown and Artifact Marker admission design is retired and must not be reintroduced
implicitly.

## 2. Workflow topology and automatic triggers

- Exactly one event-triggered root workflow is permitted:
  `.github/workflows/contract-validation.yml`.
- The root workflow retains automatic `pull_request` triggers for `opened`,
  `synchronize`, `reopened`, and `ready_for_review`, subject to its declared path
  filters.
- The root workflow retains automatic `push` validation for `main`, subject to its
  declared path filters, and supports explicit `workflow_dispatch`.
- Any future child workflow must use `workflow_call` only. It must not independently
  subscribe to `push`, `pull_request`, `workflow_run`, `schedule`, or other events.
- Do not add a second event-triggered workflow for the same repository validation
  workload.

## 3. Repository-wide native concurrency queue

The root workflow must declare:

```yaml
concurrency:
  group: stem-lab-global-ci
  cancel-in-progress: false
  queue: max
```

Operational semantics:

1. Matching GitHub events still create workflow run records.
2. All runs in the shared concurrency group are serialized: one run owns the group
   while later eligible runs wait in the native queue.
3. `cancel-in-progress: false` protects the active run from cancellation when another
   matching event arrives.
4. `queue: max` permits a queue of pending runs instead of the former single,
   replaceable pending-run behavior, subject to GitHub's platform limits.
5. Automatic triggers are preserved. This policy does not reject events, prevent
   workflow-run record creation, impose a 10-minute interval, or promise that a
   pending run will be discarded as a duplicate.

`scripts/ci_admission.py` is intentionally a pass-through admission-output step. It
writes `admitted=true`; actual serialization is provided by GitHub Actions native
concurrency. It is not a distributed lock, cooldown, deduplication service, or
pre-trigger admission controller.

If the project later requires rejecting an event before GitHub creates a workflow
run, that is a separate architecture requiring an external webhook/GitHub App
controller and a durable repository-wide lock. It is not implemented by this
workflow and must not be claimed as a current capability.

## 4. Required validation and aggregate result

- Every heavy validation job must depend on `ci-admission` and run only when
  `needs.ci-admission.outputs.admitted == 'true'`.
- The always-running `CI result` job aggregates admission and all required validation
  jobs. It succeeds only when admission succeeded and every required validation job
  completed successfully.
- A failed, cancelled, or unexpectedly skipped required validation job must not be
  reported as a successful aggregate result.
- `CI result` is the stable required status-check context for `main`. Changes to
  branch protection or repository rulesets require a separate, explicit governance
  decision; workflow changes must not bypass required checks.

## 5. Batched change protocol

For each engineering work unit:

- Perform source, SQL, test, documentation, and static-policy changes in local
  worktrees before updating remote branch refs.
- Run targeted regression tests, the applicable full local suite, static validators,
  `git diff --check`, and a final diff review before committing.
- Prefer one coherent commit and one coordinated push after the work unit is ready.
  Do not push intermediate fixes merely to observe CI.
- For stacked PRs, update branches in dependency order and push the reviewed refs in
  one controlled multi-ref operation where practical. Updating both a PR head and
  its base can generate more than one `pull_request` synchronization run for the
  same head SHA; native concurrency serializes these runs but does not deduplicate
  them.
- Do not cancel active or queued runs simply because a newer run exists. Reconcile
  each PR against its latest head SHA, workflow run ID, attempt, and same-run
  `CI result` before deciding whether its required check is covered.
- Do not use workflow dispatch or reruns as a substitute for fixing the latest head.

## 6. Audit and regression requirements

The following checks are part of the root workflow's policy validation:

- `scripts/validate_ci_workflow_policy.py` validates the single-root topology,
  repository-wide concurrency group, queue mode, admission dependencies, and
  aggregate result wiring.
- `scripts/test_ci_workflow_policy.py` exercises positive and negative workflow
  policy cases.
- `scripts/test_ci_admission.py` verifies the pass-through admission contract.
- `scripts/test_ci_result.py` verifies truthful aggregate status behavior.
- `scripts/test_ci_reconcile.py` verifies exact-SHA/run/attempt reconciliation and
  fail-closed handling of incomplete or ambiguous run data.

The read-only U5 reconciliation is the operational evidence source for current
coverage. It must not mutate PR state, cancel runs, dispatch workflows, or weaken
branch protection.

## 7. Explicitly retired behavior and boundaries

The following are not part of the active architecture:

- 600-second or 300-second workflow cooldown gates;
- `stem-lab-ci-admission` Artifact Marker artifacts or marker files;
- a single replaceable pending run as the repository-wide scheduling mechanism;
- claims that the workflow rejects an event before GitHub creates its run record.

Do not restore any of these mechanisms without a separately reviewed architecture
decision, updated regression tests, and explicit owner approval.
