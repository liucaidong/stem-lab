# R03-SCH.04.5 — Read-Only CI Reconciliation

## 1. Status and acceptance

**The initial U5 implementation passed CI on the prior branch head. This audit batch corrects all-open-PR discovery and fail-closed edge cases; its 24 offline tests and live read-only reconciliation passed locally. Post-push CI for the corrected head is a separate final gate. PR #33 remains Draft / OPEN and is not merged.**

- Working branch: `security/r03-sch-04-01-event-task-audit`
- Audited implementation head: `ae4557d914b1417693e6f9e9214aa9d734253d68`
- Main baseline at audit time: `8e749b55899d3626e39a31e1e438e3db682f5219`
- Latest workflow run: [41734325333](https://github.com/liucaidong/stem-lab/actions/runs/41734325333)
- Latest workflow attempt: 1; conclusion: success
- Ruleset: `26463757`, unchanged; required context `CI result`, integration `15368`, strict=true

## 2. Purpose and scope

The reconciler inspects:
1. the current configured base branch (main) as an independent target; and
2. **every open pull request in the repository, regardless of its target/base branch**.

Each pull request is preserved as a separate target, including its current head SHA, base branch, and base SHA. It then inspects the exact-SHA runs for `.github/workflows/contract-validation.yml` and the corresponding check runs.

The repository Ruleset `26463757` protects `refs/heads/main`. Therefore:
- PRs targeting main are subject to that Ruleset's required check.
- PRs targeting another branch are included in this repository-wide CI coverage audit, but this report does not claim that the main Ruleset applies to those PRs.

## 3. Command

```sh
GH_TOKEN="$(gh auth token)" python3 scripts/ci_reconcile.py --repo liucaidong/stem-lab --base main
```

The command is read-only. The implementation issues GitHub API GET requests only. It does not dispatch, rerun, cancel, merge, comment, label, update branches, or modify Rulesets/checks. A read-only token is preferred. If a caller supplies a token with broader scopes, this program still only performs GET requests.

Use `--json` for machine-readable output. Exit codes:
- `0`: every target is covered-success or active;
- `1`: at least one target needs recovery or is unknown;
- `2`: target discovery failed.

## 4. Classification

| State | Meaning |
|---|---|
| COVERED_SUCCESS | Latest run for the exact SHA and exact workflow path succeeded, and its same-run `CI result` check from Actions App 15368 succeeded for that SHA and latest attempt |
| ACTIVE | Latest matching workflow run is queued or in progress; do not duplicate it |
| RECOVERY_REQUIRED | No matching run exists, latest run failed/cancelled/timed out, or its exact required aggregate check is absent/unsuccessful |
| UNKNOWN | API, permission, malformed-response, pagination, or rate-limit failure prevents a safe conclusion |

Unknown is never treated as success. A workflow run's individual job successes cannot substitute for the aggregate required check.

## 5. Latest-run and latest-attempt authority

Only the latest relevant run for a target SHA and exact workflow path is authoritative. Ordering is deterministic by parsed `created_at`, then `run_attempt`, then run ID. Missing or invalid ordering timestamps fail closed.

A successful target requires all of the following:
- exact target head SHA;
- exact workflow path `.github/workflows/contract-validation.yml`;
- exact check name `CI result`;
- GitHub Actions integration App ID `15368`;
- completed successful check;
- check head SHA equals the target SHA;
- check `details_url` identifies the selected workflow run ID;
- check `started_at` is a timezone-aware valid timestamp at or after that attempt's `run_started_at`.

A rerun reuses its workflow run ID. The timestamp boundary prevents an earlier successful attempt from masking the latest attempt. Missing, malformed, or timezone-naive timestamps fail closed.

## 6. Implementation and code-quality review

Implementation: `scripts/ci_reconcile.py`.

Verified properties:
- `get()` return annotation supports both JSON object and array responses.
- Pagination reads all pages and has an explicit safety ceiling; malformed list entries and exhausted pagination fail closed rather than silently truncating.
- API/HTTP/network/timeout/JSON errors become explicit reconciliation errors.
- Every PR head and base SHA is validated as a full 40-character lowercase Git SHA.
- PR discovery does not filter by `base=main`; all open PRs are included.
- Workflow path and head SHA matching are exact.
- Required check name, App ID, head SHA, run ID, attempt time, status, and conclusion are all checked.
- No write-capable GitHub operation exists in the implementation.
- Base branch and base SHA are included in each finding.

## 7. Offline validation

Test file: `scripts/test_ci_reconcile.py`.

**24 offline tests passed** on the consolidated working head after the U5 correction.

Coverage includes:
- exact-SHA and exact-workflow matching;
- required check name and App ID;
- check/run association;
- older run and older attempt precedence;
- active-run deduplication;
- failed/cancelled/missing aggregate check behavior;
- missing, malformed, or timezone-naive timestamps;
- malformed details URL rejection;
- dict/list return annotation;
- inclusion of PRs targeting non-main branches;
- malformed pagination entries;
- exact-page-boundary pagination and safety-limit failure.

Command:
```sh
python3 -m unittest discover -s scripts -p 'test_ci_reconcile.py' -v
```

## 8. CI baseline evidence before this audit correction batch

Run [41734325333](https://github.com/liucaidong/stem-lab/actions/runs/41734325333), SHA `ae4557d914b1417693e6f9e9214aa9d734253d68`, attempt 1, completed successfully. This validates the pre-correction U5 baseline, not the uncommitted corrections described in this audit batch.

| Job / Check | Job ID | Result |
|---|---:|---|
| `ci-admission` | 126259461110 | success |
| `validate-contracts` | 126259537084 | success |
| `tenant-ed25519-verifier` | 126259536855 | success |
| `CI result` | 126260496887 | success |

Required check evidence:
- Name: `CI result`
- Head SHA: `ae4557d914b1417693e6f9e9214aa9d734253d68`
- Actions App ID: `15368`
- Started: `2026-11-03T22:53:20Z`
- Workflow `run_started_at`: `2026-11-03T22:51:03Z`
- Details URL: `https://github.com/liucaidong/stem-lab/actions/runs/41734325333/job/126260496887`

The check is bound to the exact latest run and began after that attempt started.

## 9. Repository-wide live reconciliation — 2026-11-04

The reconciler was executed against GitHub with the current main SHA and all 17 open PR heads. It returned exit code `1` because unresolved targets exist; this is the expected fail-closed result, not a script failure.

Summary: **COVERED_SUCCESS=2, ACTIVE=0, RECOVERY_REQUIRED=16, UNKNOWN=0** (18 targets: main + 17 open PRs).

| Target | Current head SHA | Base branch | Latest Run | Workflow | CI result | U5 state |
|---|---|---|---:|---|---|---|
| main | `8e749b55899d3626e39a31e1e438e3db682f5219` | main | 41721958066 | success | success | COVERED_SUCCESS |
| PR #13 | `c38f22d72a54934dbca80759db1dd85b3903163c` | main | 41496714183 | success | absent | RECOVERY_REQUIRED |
| PR #14 | `cda9a05ea0ea06b4435fb05b5d3815e0913dd3ef` | r03-52-7-3-6-resource-auth-debug2 | 41499382868 | success | absent | RECOVERY_REQUIRED |
| PR #15 | `f5484b719e38a3c7145af26cf8470aab282058bb` | r03-52-7-3-11-auth-boundary-review | 41503109841 | failure | absent | RECOVERY_REQUIRED |
| PR #16 | `f3e90cd85a21744f2e99ba4c82bd05c4e57083d0` | r03-52-7-3-11-3-request-digest-v2alpha2 | 41503709136 | success | absent | RECOVERY_REQUIRED |
| PR #17 | `2be9941b93b8dcf82d219c3cee660fe51d963ce4` | r03-52-7-3-11-3-remediation-gate | 41571959572 | success | absent | RECOVERY_REQUIRED |
| PR #18 | `1a8de570698a271a489f1dc7b0e60efb2c1966ab` | r03-52-7-3-11-3-raw-claim-parser | 41577147243 | success | absent | RECOVERY_REQUIRED |
| PR #19 | `8fb7dc5edc5954cd8b5ffc50bcce6833310550f6` | r03-52-7-3-11-3-v2alpha2-db-verifier | 41577279984 | success | absent | RECOVERY_REQUIRED |
| PR #20 | `a9394870164bba5971ffa82b15c83d7e9b9cfc47` | r03-52-7-3-11-3-receipt-arbitration | 41578429173 | success | absent | RECOVERY_REQUIRED |
| PR #21 | `1d5b3ee76d314424d25676e48d62e5a8e154f66b` | r03-52-7-3-11-3-handler-integration-audit | 41591092307 | success | absent | RECOVERY_REQUIRED |
| PR #22 | `cc8a99c71794e9832525e14ff6509846c625c01a` | r03-52-7-3-11-3-preimplementation-closure | 41593640211 | success | absent | RECOVERY_REQUIRED |
| PR #23 | `3b09e865cd80253aa81e45f9f2f4b3c5fe4cb5c3` | r03-52-7-3-11-5-protocol-security-hardening | 41631413641 | success | absent | RECOVERY_REQUIRED |
| PR #24 | `3d6093764c8318bf4e4ba9eb50e74b7801b3ce6c` | r03-52-7-3-11-6-atomic-business-handler-uow | 41607950079 | success | absent | RECOVERY_REQUIRED |
| PR #29 | `0da65df7e40832d1bd9116febda35c8f3e2a7803` | main | 41722065653 | cancelled | absent | RECOVERY_REQUIRED |
| PR #30 | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` | main | 41722127811 | cancelled | absent | RECOVERY_REQUIRED |
| PR #31 | `2f18c7f3ca8c5d108cd472d753db97dc80b3d2e1` | main | 41722331190 | cancelled | absent | RECOVERY_REQUIRED |
| PR #32 | `06c7c7508ed525dc81d0bb2d65294a0a169310c4` | main | 41722344375 | failure | failure | RECOVERY_REQUIRED |
| PR #33 | `ae4557d914b1417693e6f9e9214aa9d734253d68` | main | 41734325333 | success | success | COVERED_SUCCESS |

The `absent` entries mean no `CI result` check from App 15368 exists on that exact current head SHA. Legacy successful workflow jobs are not treated as substitutes.

## 10. Ruleset interpretation and unresolved targets

- PR #13 and PR #29–#33 target main; the main Ruleset applies to them.
- PR #14–#24 target stacked feature branches; they are included in CI coverage reporting but are not subject to main Ruleset #26463757 directly.
- PR #13 has a successful workflow run but no exact required aggregate check. It is not merge-ready under the current main Ruleset.
- PR #14 and #16–#24 have successful historical workflow runs but no exact current-head aggregate check. This is not proof of current required-check coverage.
- PR #15's latest workflow run failed.
- PR #29–#31's latest workflow runs were cancelled.
- PR #32's latest workflow run and aggregate check failed.
- PR #33 and main have exact successful aggregate checks.

## 11. Deferred recovery plan — not authorized

This section is an execution plan only. No historical PR recovery is authorized or performed in U5.

1. Re-read each target PR's current state, head SHA, base ref/SHA, and latest run immediately before any recovery.
2. Preserve the stacked dependency order for PR #13–#24; do not start a bulk rerun wave.
3. Prioritize the main-target PR #13 and Dependabot PRs #29–#32 for separate compatibility and required-check decisions.
4. For each candidate, determine whether a rerun of the historical workflow can actually produce the current `CI result` check. A rerun may reuse the original workflow definition; do not assume it loads a newer workflow revision.
5. If a fresh event is required, propose a bounded one-PR-at-a-time trigger plan, with exact SHA and resulting run/check association verified before proceeding.
6. Do not execute rerun, dispatch, push, branch update, cancel, merge, or PR metadata mutation without separate explicit authorization.
7. Keep PR #29–#32 unmerged until both compatibility review and exact-head CI acceptance are complete.

## 12. Safety and architecture boundaries

- All reconciliation requests are GET-only.
- No scheduled reconciliation workflow is added.
- No write-capable recovery is implemented.
- No Ruleset or required-check mutation is implemented.
- Native Actions concurrency remains `group: stem-lab-global-ci`, `cancel-in-progress: false`, `queue: max`.
- `queue: max` is bounded to 100 pending runs; it is not an infinite or durable queue and does not guarantee strict FIFO.
- Dependabot's dynamically generated workflows do not automatically inherit this custom workflow's concurrency settings; Dependabot arrival shaping remains separate.
- No artifact-marker cooldown/admission system is restored.

## 13. Final U5 disposition

The corrected U5 implementation and its 24 offline tests pass locally; the repository-wide audit is complete and has explicitly identified 16 recovery-required targets. The corrected head must pass its post-push required CI before this implementation batch is considered CI-accepted. This is **not** a claim that all open PRs have been recovered or are merge-ready. Recovery remains deferred and unauthorized.
