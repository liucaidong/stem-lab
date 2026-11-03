# R03-SCH.04.5 — Read-Only CI Reconciliation

## Status

Implemented on the SCH.04 working branch; offline regression tests are part of required CI. This phase is a manual, read-only CLI and deliberately has no scheduled workflow.

## Purpose

GitHub Actions native `queue: max` is bounded to 100 pending runs. It is not a durable event ledger, and its ordering is not strict event-dispatch FIFO. The reconciler therefore inspects authoritative current heads rather than replaying every superseded event.

## Command

```sh
python scripts/ci_reconcile.py --repo liucaidong/stem-lab --base main
```

For a public repository, an unauthenticated read may work within GitHub's lower API rate limit. An optional `GH_TOKEN` or `GITHUB_TOKEN` can be supplied for read access to repository metadata, pull requests, Actions workflow runs, and commit check-runs. Use a read-only token; do not grant write scopes.

Use `--json` for machine-readable output. Exit codes:
- `0`: every target is covered-success or active;
- `1`: at least one target needs recovery or is unknown;
- `2`: target discovery failed.

## Classification

| State | Meaning |
|---|---|
| COVERED_SUCCESS | The latest run for the exact SHA and required workflow completed successfully, and its same-run `CI result` check from GitHub Actions integration 15368 also succeeded for that exact SHA |
| ACTIVE | The latest matching run for the exact SHA is queued or in progress |
| RECOVERY_REQUIRED | No matching run exists, the latest run failed/cancelled/timed out, or its exact required aggregate check is missing or unsuccessful |
| UNKNOWN | API, permission, pagination, or rate-limit failure prevents a safe conclusion |

The report includes the current base branch SHA and every open PR targeting that base branch. Each PR remains a separate report target even if two PRs share a head SHA.

## Latest-run authority rule

Only the latest relevant workflow run for a target SHA is authoritative. The selection is deterministic by `created_at`, then `run_attempt`, then run ID. An older successful run or check must never mask a newer failed, cancelled, or active run. A latest successful run is covered only when all of these agree:
- exact target SHA;
- exact workflow path `.github/workflows/contract-validation.yml`;
- exact check name `CI result`;
- GitHub Actions integration app ID `15368`;
- successful completed check;
- check head SHA equals the target SHA;
- check `details_url` resolves to the selected latest workflow run ID, and the check start time is at or after that run attempt's `run_started_at`. This is necessary because GitHub reruns reuse the workflow run ID.

## Safety properties

- All GitHub API requests use GET.
- No dispatch, rerun, cancellation, merge, comment, label, branch, Ruleset, or check mutation is implemented.
- Active work is not duplicated.
- API failures classify the affected target as UNKNOWN; unknown is never treated as success.
- No scheduled workflow is added, so reconciliation itself creates no recurring CI traffic.

## Validation

Offline tests cover exact-SHA checks, expected app identity, run/check association, active-run deduplication, missing/cancelled runs, older-run precedence, and the regression where an earlier successful attempt of the same rerun ID must not mask the latest attempt.

## Deferred recovery phase

This phase does not rerun or dispatch workflows. Any later write-capable recovery requires a separate review and explicit authorization, least-privilege Actions permission, bounded attempts, backoff, exact-SHA verification, and an auditable record.
