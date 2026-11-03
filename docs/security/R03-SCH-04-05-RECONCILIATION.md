# R03-SCH.04.5 — Read-Only CI Reconciliation

## Status
Implemented on the SCH.04 working branch. This phase is read-only and deliberately has no scheduled workflow.

## Purpose
The GitHub Actions queue is bounded to 100 pending runs and is not a durable event ledger. The reconciler checks authoritative current heads instead of preserving every superseded event.

## Command
    GH_TOKEN="$(gh auth token)" \
      python scripts/ci_reconcile.py --repo liucaidong/stem-lab --base main

The command requires read access to repository metadata, pull requests, Actions workflow runs, and commit check-runs. It accepts GH_TOKEN or GITHUB_TOKEN. Do not grant write scopes.

Use --json for machine-readable output. Exit codes:
- 0: every target is covered-success or active;
- 1: at least one target needs recovery or is unknown;
- 2: target discovery failed.

## Classification
| State | Meaning |
|---|---|
| COVERED_SUCCESS | Exact SHA has a successful CI result check from GitHub Actions integration 15368, tied to a successful run of the required workflow |
| ACTIVE | Exact SHA has a queued/in-progress run of the required workflow |
| RECOVERY_REQUIRED | No run, failed/cancelled run, or no matching successful aggregate check |
| UNKNOWN | API, permission, pagination, or rate-limit failure prevents a safe conclusion |

The report includes the current base branch SHA and every open PR targeting that base branch. Each PR remains a separate report target even if two PRs share a head SHA.

## Safety properties
- All GitHub API requests use GET.
- No dispatch, rerun, cancellation, merge, comment, label, branch, Ruleset, or check mutation is implemented.
- A successful run alone is insufficient: exact CI result context, expected GitHub Actions app ID, exact SHA, and same run ID must agree.
- A cancelled, skipped, missing, failed, stale-SHA, wrong-app, or unrelated check is never success.
- Active work is not duplicated.
- API failures classify the affected target as UNKNOWN; unknown is never treated as success.
- No scheduled workflow is added, so reconciliation itself creates no recurring CI traffic.

## Current observed baseline
PR #33 validation run 41729326068 is a verified example: exact head SHA fb31d718f38613ebb3ce7d1cb49aec60dbfd8d58, required check CI result, app ID 15368, conclusion success.

## Deferred recovery phase
This phase does not rerun or dispatch workflows. Recovery automation is deferred until the read-only report has been exercised against real open PRs and edge cases. Any later write-capable recovery requires a separate review, least-privilege Actions permission, bounded attempts, and exact-SHA verification.
