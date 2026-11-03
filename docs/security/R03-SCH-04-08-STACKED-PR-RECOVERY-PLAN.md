# R03-SCH-04.8 — Stacked PR #13–#24 Recovery and Dependency Plan

**Status:** READ-ONLY AUDIT / RECOVERY NOT AUTHORIZED  
**Snapshot date:** 2026-11-04  
**Repository:** `liucaidong/stem-lab`  
**Protected base:** `main` at `8e749b55899d3626e39a31e1e438e3db682f5219`  
**SCH.04 branch / PR:** `security/r03-sch-04-01-event-task-audit`, PR #33  
**PR #33 head:** `d2b67664d81a8988a73c96eeaed48817fc5c8a01` (Draft / OPEN / unmerged)

## 1. Executive finding

PR #13–#24 form one stacked dependency chain, not twelve independent PRs. The parent/base relationship is consistent from #14 through #23, but two endpoints have drifted:

1. PR #13 was created against an older `main` SHA (`b33b9cb...`); current `main` is `8e749b5...`. GitHub reports the PR as `BEHIND`; comparison of current main to its head is `diverged`, 100 commits ahead and 11 behind.
2. PR #24 records base SHA `abbbe979...`, but its base branch (PR #23 head branch) currently points to `3b09e865...`. The current-parent comparison is 5 commits ahead and 1 behind.

A more serious integration conflict exists in PR #23: its workflow restores `queue: single` and a 600-second Artifact Marker cooldown. PR #24 inherits that workflow. This directly conflicts with the SCH.04 target on PR #33 (`queue: max`, no marker/cooldown). Do not merge or bulk-recover #23/#24 as they stand.

No PR #13–#24 was modified, rebased, retargeted, dispatched, rerun, cancelled, closed or merged during this audit.

## 2. Live dependency graph and SHA alignment

The chain is:

```text
main
  └─ PR #13
      └─ PR #14
          └─ PR #15
              └─ PR #16
                  └─ PR #17
                      └─ PR #18
                          └─ PR #19
                              └─ PR #20
                                  └─ PR #21
                                      └─ PR #22
                                          └─ PR #23
                                              └─ PR #24
```

| PR | Parent | Head SHA | Recorded base SHA | Live parent SHA | Commits / files | Current GitHub merge state |
|---:|---|---|---|---|---:|---|
| #13 | `main` | `c38f22d72a54934dbca80759db1dd85b3903163c` | `b33b9cb1d7e77b2123ff06533d31218f04d95b50` | `8e749b55899d3626e39a31e1e438e3db682f5219` | 100 / 11 | MERGEABLE / BEHIND |
| #14 | #13 | `cda9a05ea0ea06b4435fb05b5d3815e0913dd3ef` | `c38f22d72a54934dbca80759db1dd85b3903163c` | same | 4 / 2 | MERGEABLE / CLEAN |
| #15 | #14 | `f5484b719e38a3c7145af26cf8470aab282058bb` | `cda9a05ea0ea06b4435fb05b5d3815e0913dd3ef` | same | 10 / 18 | MERGEABLE / UNSTABLE |
| #16 | #15 | `f3e90cd85a21744f2e99ba4c82bd05c4e57083d0` | `f5484b719e38a3c7145af26cf8470aab282058bb` | same | 1 / 1 | MERGEABLE / CLEAN |
| #17 | #16 | `2be9941b93b8dcf82d219c3cee660fe51d963ce4` | `f3e90cd85a21744f2e99ba4c82bd05c4e57083d0` | same | 2 / 2 | MERGEABLE / CLEAN |
| #18 | #17 | `1a8de570698a271a489f1dc7b0e60efb2c1966ab` | `2be9941b93b8dcf82d219c3cee660fe51d963ce4` | same | 7 / 2 | MERGEABLE / CLEAN |
| #19 | #18 | `8fb7dc5edc5954cd8b5ffc50bcce6833310550f6` | `1a8de570698a271a489f1dc7b0e60efb2c1966ab` | same | 4 / 3 | MERGEABLE / CLEAN |
| #20 | #19 | `a9394870164bba5971ffa82b15c83d7e9b9cfc47` | `8fb7dc5edc5954cd8b5ffc50bcce6833310550f6` | same | 1 / 1 | MERGEABLE / CLEAN |
| #21 | #20 | `1d5b3ee76d314424d25676e48d62e5a8e154f66b` | `a9394870164bba5971ffa82b15c83d7e9b9cfc47` | same | 54 / 43 | MERGEABLE / CLEAN |
| #22 | #21 | `cc8a99c71794e9832525e14ff6509846c625c01a` | `1d5b3ee76d314424d25676e48d62e5a8e154f66b` | same | 1 / 22 | MERGEABLE / CLEAN |
| #23 | #22 | `3b09e865cd80253aa81e45f9f2f4b3c5fe4cb5c3` | `cc8a99c71794e9832525e14ff6509846c625c01a` | same | 10 / 30 | MERGEABLE / CLEAN |
| #24 | #23 | `3d6093764c8318bf4e4ba9eb50e74b7801b3ce6c` | `abbbe979bf273922574efa7f569cc522f1dcbce3` | `3b09e865cd80253aa81e45f9f2f4b3c5fe4cb5c3` | 5 / 2 | MERGEABLE / CLEAN |

All twelve PRs were OPEN / DRAFT at the inspected snapshot. PR #13–#24 remain `RECOVERY_REQUIRED` in the SCH.04 reconciler because their current heads lack a successful exact-head aggregate `CI result`. PR #13 targets protected `main`; PR #14–#24 target stacked feature branches and are not directly covered by Ruleset #26463757, but their CI gaps remain visible to repository reconciliation.

## 3. Specific blockers and superseding evidence

### 3.1 PR #13 — stale protected base

- PR #13 directly targets `main` and therefore the unchanged Ruleset #26463757 applies.
- Its recorded base is `b33b9cb...`; current `main` is `8e749b5...`.
- GitHub comparison reports current `main` versus PR #13 head as `diverged`, 100 commits ahead and 11 behind. The PR is `MERGEABLE / BEHIND`, not ready to merge under strict up-to-date checks.
- The branch's workflow changes only add resource-authorization tests. It still inherits the old `main` workflow's `queue: single` and 300-second Artifact Marker gate.
- Do not rebase or merge #13 until the target scheduling policy and the entire downstream stacked chain have an approved integration strategy.

### 3.2 PR #15 — historical Request Digest SQL failure

Run `41503109841` failed in `tenant-ed25519-verifier`. The PostgreSQL conformance test failed while creating `request_digest_v2alpha2`; the PL/pgSQL `IF resource_name <> CASE ... END THEN` expression caused a PostgreSQL syntax error. The Python and PostgreSQL resource-authorization tests passed before the digest test failed.

PR #22 subsequently supersedes this defect: its digest SQL asset was repaired, and its PostgreSQL test now executes the complete SQL asset as shipped instead of extracting individual function fragments. This is a later-chain fix; do not rerun the historical PR #15 head or treat its old failure as the final state of the entire chain.

### 3.3 PR #21 — pre-implementation gate remains a governance boundary

PR #21's own canonical gate artifacts record:
- Product Code Freeze: ACTIVE;
- G0–G14 BLOCKED and aggregate G15 BLOCKED;
- no production Business Handler or production UOW authorization;
- no formal COMMIT fault injection until predecessor gates and owner/security approvals pass.

PR #22 explicitly remains reference-level hardening and preserves the production boundary. PR #23's description also limits its implementation to a PostgreSQL reference harness, only `worker.job.complete` for `package.validate`, and says to keep the PR Draft/unmerged pending source audit, independent code/security review and owner/security approval. CI success is not production readiness.

### 3.4 PR #23 — hard conflict with SCH.04 scheduling policy

The PR #23 workflow patch introduces all of the following:

- `queue: single` instead of the approved `queue: max`;
- a repository-wide 600-second admission/cooldown gate;
- `COOLDOWN_SECONDS = 600`;
- the `stem-lab-ci-admission` Artifact Marker upload;
- mutable `actions/checkout@v4`, `actions/upload-artifact@v4` and `actions/setup-python@v5` references;
- `actions: read` permission to inspect the marker artifact.

The current `main` workflow still has the older 300-second marker and `queue: single`; the SCH.04 branch/PR #33 has `queue: max` and no marker. Therefore PR #23 is not mergeable as-is from a policy perspective, despite GitHub's `MERGEABLE / CLEAN` result. PR #24 inherits PR #23's workflow and the same conflict.

Do not solve this by merely changing `600` to `300`, updating artifact SHAs, or restoring the marker. The approved target is native GitHub concurrency with no cooldown/marker.

### 3.5 PR #24 — stale parent and design-only scope

- PR #24 is documentation-only; it has not implemented `worker.job.fail`.
- Its design selects Job-specific Transition and Job Outbox ledgers (Option A) to avoid inventing a Session revision for a Job-only failure.
- The design requires extending PR #23 Complete to append Job aggregate history, then implementing the Failure Handler with a complete rollback/concurrency/fault-injection suite.
- PR #24's recorded base `abbbe979...` is stale relative to the current PR #23 branch head `3b09e865...`; compare reports 5 commits ahead / 1 behind. Rebase #24 only after the parent is stabilized and approved.

## 4. Recovery ordering — plan only

No write operation is authorized by this plan. If and when a separate owner decision authorizes recovery, use this sequence:

1. Resolve the PR #33 / `main` scheduling-policy integration decision first. While PR #33 remains Draft and unmerged, `main` continues to use its old 300-second marker and `queue: single` policy.
2. Revalidate PR #13 against the then-current `main`; update its base only through an approved branch operation. Re-run only the current PR #13 head after the branch is stable.
3. Reconcile #14 against the exact new PR #13 head; then continue #15 → #16 → #17 → #18 → #19 → #20 → #21 → #22 → #23 one branch at a time. After each parent change, verify child base SHA equals the current parent head before touching the child.
4. Remove PR #23's obsolete marker/cooldown implementation and align its workflow with the approved native queue policy and immutable action pinning before any merge consideration.
5. Rebase PR #24 onto the final current PR #23 head; review its Job aggregate sequence/Transition/Outbox design as a separate design gate.
6. For every current head, require exact SHA, latest workflow attempt, same-run `CI result`, Actions App ID `15368`, and independent technical/security review. A green legacy job or historical run is insufficient.
7. Keep all PRs Draft/unmerged until the applicable owner/security/architecture approvals are recorded. Product Code Freeze remains ACTIVE unless explicitly lifted by the owner.

## 5. Explicit non-actions

- No PR #13–#24 was rebased, retargeted, pushed, rerun, dispatched, cancelled, closed or merged.
- No branch was deleted or recreated.
- No Ruleset, `main`, or required check was changed.
- No historical workflow run was replayed.
- No production deployment, migration, production key lifecycle or Product Code Freeze release is implied.

**Conclusion:** PR #13–#24 must be treated as one stacked recovery chain. The chain is not ready for recovery writes until the #13 base drift, PR #23 scheduling-policy regression, and #24 parent drift are resolved under explicit authorization.
