# STEM Lab — CI Admission and Batched Change Policy

**Status:** Mandatory engineering policy  
**Scope:** All GitHub Actions workflows and all changes to this repository

## 1. Objective

Prevent repeated branch updates from repeatedly consuming the repository's full
contract-validation workflow. A successful CI admission starts a repository-wide
600-second cooldown. During that cooldown, subsequent workflow runs are rejected
before any contract, PostgreSQL, integration, security, or benchmark job starts.

## 2. Workflow topology

- Exactly one event-triggered root workflow is permitted.
- The root workflow is `.github/workflows/contract-validation.yml`.
- Any future child workflow must use `workflow_call` only; it must not independently
  subscribe to `push`, `pull_request`, `workflow_run`, `schedule`, or other events.
- Every root workflow run uses the repository-wide concurrency group
  `stem-lab-global-ci`, with `cancel-in-progress: false` and a single replaceable
  pending run.
- Every validation job must depend on `ci-admission` and must be conditional on
  `needs.ci-admission.outputs.admitted == 'true'`.

## 3. 600-second admission protocol

1. GitHub creates a workflow run record for an eligible event.
2. Workflow-level concurrency serializes admission decisions across this repository.
3. The admission job reads the current run's `created_at` and the latest
   `stem-lab-ci-admission` artifact metadata using the read-only `actions: read`
   token permission.
4. If fewer than 600 seconds separate the current event from the latest marker's
   creation time, the run is rejected. No marker is written and no validation job
   starts.
5. If at least 600 seconds have elapsed, the gate writes a marker file and uploads
   the repository-visible artifact `stem-lab-ci-admission`.
6. Validation jobs can start only after the admission job, including marker upload,
   succeeds.
7. If the GitHub API, timestamp parsing, or marker upload fails, the gate fails
   closed and all validation jobs remain blocked.

The artifact is deliberately used instead of Actions cache: pull-request caches are
branch/ref scoped and are not a reliable repository-wide lock across different PRs.
The artifact marker is repository-visible across PR branches. Its creation time is
slightly later than admission, so the effective interval is conservative and never
shorter than 600 seconds.

## 4. GitHub platform boundary

GitHub creates the workflow run record when an eligible event is received, before
workflow YAML can execute. Therefore this in-repository gate guarantees that no
second heavy CI workload starts within 600 seconds; it does not guarantee that the
GitHub Actions run record itself is absent. Preventing even run-record creation
requires an external webhook/GitHub App admission controller that dispatches CI
only after acquiring a durable repository-wide lock.

## 5. Change batching protocol

During an engineering task:

- Make source, SQL, test, and documentation changes locally or as unreferenced Git
  objects; do not repeatedly update remote branch refs.
- Run targeted tests, the full local validation suite, static checks, and diff review
  before creating the final commit.
- Prepare one coherent commit containing the complete task result.
- Update the remote task branch once and open/update its PR once.
- Do not push intermediate fixes. If CI rejects a run during cooldown, finish all
  fixes locally and dispatch or push one final validation request after cooldown.

## 6. Policy regression checks

`scripts/validate_ci_workflow_policy.py` enforces the single-root topology, global
concurrency group, gate dependency, and marker persistence. `scripts/test_ci_admission.py`
checks the 599/600/601-second boundaries and timestamp handling.
