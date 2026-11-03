# R03-SCH-04.6 — Dependabot PR #29–#32 Disposition and Repository PR Matrix

## 1. Scope and current state

This is a read-only disposition record. The live GitHub snapshot on 2026-11-04 shows 17 open PRs: #13–#24 and #29–#33. PR #25–#28 are already closed and merged; they are not current reconciliation targets.

- Current main SHA: `8e749b55899d3626e39a31e1e438e3db682f5219`
- SCH.04 branch: `security/r03-sch-04-01-event-task-audit`
- PR #33 current head: `d2b67664d81a8988a73c96eeaed48817fc5c8a01`
- PR #33 latest exact-head CI Run `41739088474` completed successfully, including `CI result` from Actions App `15368`.
- PR #33 remains Draft / OPEN / unmerged.
- No PR #29–#32 head was modified, rerun, dispatched, cancelled, closed, or merged by this audit.
- No Ruleset, branch protection, or required check was changed.

## 2. Dependabot PR #29–#32 disposition

| PR | Proposed update | Current head SHA | Latest run | CI result | Disposition |
|---|---|---|---:|---|---|
| [#29](https://github.com/liucaidong/stem-lab/pull/29) | PostgreSQL 17.11 → 18.4 | `0da65df7e40832d1bd9116febda35c8f3e2a7803` | 41722065653 cancelled | absent | BLOCKED |
| [#30](https://github.com/liucaidong/stem-lab/pull/30) | Node `pg` 8.16.3 → 8.23.1 | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` | 41722127811 cancelled | absent | HOLD |
| [#31](https://github.com/liucaidong/stem-lab/pull/31) | `actions/setup-python` 7.0.0 → 7.1.0 | `2f18c7f3ca8c5d108cd472d753db97dc80b3d2e1` | 41722331190 cancelled | absent | HOLD |
| [#32](https://github.com/liucaidong/stem-lab/pull/32) | `actions/upload-artifact` 6.0.0 → 7.0.2 | `06c7c7508ed525dc81d0bb2d65294a0a169310c4` | 41722344375 failure | failure | DO NOT MERGE AS-IS |

### PR #29 — PostgreSQL major version

The PR changes the Docker image from PostgreSQL 17.11 to 18.4, but the repository's Docker build still installs PostgreSQL 17 development packages and references PostgreSQL 17 `pg_config` / PGXS paths. This creates a mixed-major build/runtime environment. The PR remains blocked until the image, development headers, `pg_config`, PGXS path, and extension build/test strategy are made consistently PostgreSQL 18. This audit does not authorize a production database migration.

The latest validation run is cancelled and there is no successful exact-head `CI result` check. Cancellation is not success.

### PR #30 — Node pg

The package manifest and lockfile consistently move `pg` from 8.16.3 to 8.23.1 and the lockfile integrity is present. However, complete required CI validation has not been established for this PR head, and the repository's static dependency-policy fixture still pins the old version. Review the upstream compatibility/change surface, update the exact-version fixture only as part of a reviewed dependency change, and obtain a complete successful required check before merge consideration.

The latest validation run is cancelled and there is no successful exact-head `CI result` check.

### PR #31 — setup-python action

This PR updates the immutable action reference for `actions/setup-python` from 7.0.0 to 7.1.0. The latest validation run is cancelled; cancellation is not success. Verify the exact upstream immutable SHA and major-version compatibility, then obtain a complete successful required check for the current PR head.

### PR #32 — upload-artifact action

This PR updates the immutable action reference for `actions/upload-artifact` to 7.0.2, but its workflow changes retain artifact-marker admission behavior that SCH.04 removes in favor of native queueing. It also encountered the old static action-SHA policy fixture. The latest workflow run and aggregate `CI result` both failed. Do not merge this PR as-is. Re-evaluate the action reference and any remaining legitimate artifact usage against the current SCH.04 workflow; do not restore the removed marker scheduler.

## 3. PR #13–#32 classification and disposition matrix

This matrix includes the missing PR #13. The four already merged PRs #25–#28 are included for completeness but are not part of the 17-open-PR reconciliation.

| PR | Current state | Base branch | Current head SHA | Latest CI workflow | Exact CI result | Disposition |
|---|---|---|---|---|---|---|
| #13 | OPEN / Draft | main | `c38f22d72a54934dbca80759db1dd85b3903163c` | success | absent | RECOVERY_REQUIRED; main Ruleset applies |
| #14 | OPEN / Draft | r03-52-7-3-6-resource-auth-debug2 | `cda9a05ea0ea06b4435fb05b5d3815e0913dd3ef` | success | absent | RECOVERY_REQUIRED; Ruleset #26463757 does not apply directly |
| #15 | OPEN / Draft | r03-52-7-3-11-auth-boundary-review | `f5484b719e38a3c7145af26cf8470aab282058bb` | failure | absent | RECOVERY_REQUIRED |
| #16 | OPEN / Draft | r03-52-7-3-11-3-request-digest-v2alpha2 | `f3e90cd85a21744f2e99ba4c82bd05c4e57083d0` | success | absent | RECOVERY_REQUIRED |
| #17 | OPEN / Draft | r03-52-7-3-11-3-remediation-gate | `2be9941b93b8dcf82d219c3cee660fe51d963ce4` | success | absent | RECOVERY_REQUIRED |
| #18 | OPEN / Draft | r03-52-7-3-11-3-raw-claim-parser | `1a8de570698a271a489f1dc7b0e60efb2c1966ab` | success | absent | RECOVERY_REQUIRED |
| #19 | OPEN / Draft | r03-52-7-3-11-3-v2alpha2-db-verifier | `8fb7dc5edc5954cd8b5ffc50bcce6833310550f6` | success | absent | RECOVERY_REQUIRED |
| #20 | OPEN / Draft | r03-52-7-3-11-3-receipt-arbitration | `a9394870164bba5971ffa82b15c83d7e9b9cfc47` | success | absent | RECOVERY_REQUIRED |
| #21 | OPEN / Draft | r03-52-7-3-11-3-handler-integration-audit | `1d5b3ee76d314424d25676e48d62e5a8e154f66b` | success | absent | RECOVERY_REQUIRED |
| #22 | OPEN / Draft | r03-52-7-3-11-3-preimplementation-closure | `cc8a99c71794e9832525e14ff6509846c625c01a` | success | absent | RECOVERY_REQUIRED |
| #23 | OPEN / Draft | r03-52-7-3-11-5-protocol-security-hardening | `3b09e865cd80253aa81e45f9f2f4b3c5fe4cb5c3` | success | absent | RECOVERY_REQUIRED |
| #24 | OPEN / Draft | r03-52-7-3-11-6-atomic-business-handler-uow | `3d6093764c8318bf4e4ba9eb50e74b7801b3ce6c` | success | absent | RECOVERY_REQUIRED |
| #25 | CLOSED / Merged | main | `5f94ccef6c500d29e4ff7cf4dd8f1af1c347314f` | historical | historical | MERGED; excluded from current open-PR audit |
| #26 | CLOSED / Merged | main | `226582a5cbe3ace9840bddafe2d6dfbf2ffe159f` | historical | historical | MERGED; excluded from current open-PR audit |
| #27 | CLOSED / Merged | main | `c9e5d2bfaf4b7a3c41e485366dba4e474e175051` | historical | historical | MERGED; excluded from current open-PR audit |
| #28 | CLOSED / Merged | main | `18bc4676e8a8d4d7c8e925788e12ec6d0201791c` | historical | historical | MERGED; excluded from current open-PR audit |
| #29 | OPEN | main | `0da65df7e40832d1bd9116febda35c8f3e2a7803` | cancelled | absent | BLOCKED |
| #30 | OPEN | main | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` | cancelled | absent | HOLD |
| #31 | OPEN | main | `2f18c7f3ca8c5d108cd472d753db97dc80b3d2e1` | cancelled | absent | HOLD |
| #32 | OPEN | main | `06c7c7508ed525dc81d0bb2d65294a0a169310c4` | failure | failure | DO NOT MERGE AS-IS |

PR #33 is the active SCH.04 implementation PR and is tracked separately in the reconciliation record. Its exact current-head `CI result` succeeded.

## 4. Required-check interpretation

- The Ruleset requires `CI result` from integration `15368` on the protected `main` branch.
- PR #13 and PR #29–#33 target main; the Ruleset applies.
- PR #14–#24 target other branches. Their missing aggregate checks are reported as CI coverage gaps by U5, not as a direct Ruleset violation.
- A successful legacy workflow run or successful individual job is not a substitute for the exact aggregate check.
- PR #13 was omitted from the earlier classification expression and is now explicitly included.
- PR #25–#28 are confirmed closed and merged; they are not open PR targets.

## 5. Merge gate

- PR #29–#32 remain open and unmerged.
- No PR #29–#32 head was changed by this audit.
- A cancelled, missing, or incomplete run is not a passing check.
- Reassess current head SHA, base branch, compatibility findings, and exact required check immediately before any future decision.
- No automatic merge or recovery is authorized by this disposition.

## 6. Recovery authorization boundary

This document records a possible future sequence only:
1. Revalidate the current head/base SHA and run status for the selected PR.
2. Review compatibility independently from CI status.
3. For stacked PRs #13–#24, proceed in base-to-leaf dependency order; do not dispatch a bulk wave.
4. Determine whether rerunning an older workflow can produce the current aggregate `CI result`; reruns may reuse the original workflow definition.
5. If a new event is required, prepare a bounded one-PR-at-a-time trigger plan and verify the exact SHA/run/check association after each action.
6. Obtain separate explicit authorization before any rerun, dispatch, push, PR mutation, cancellation, or merge.

No such recovery action was performed.
