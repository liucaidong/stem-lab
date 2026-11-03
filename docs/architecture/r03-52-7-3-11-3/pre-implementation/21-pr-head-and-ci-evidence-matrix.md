# PR #13–#21 Head SHA and CI Evidence Matrix

**Version:** 0.1.0  
**Status:** G0 EVIDENCE UPDATE / PARTIAL  
**As-of:** 2026-11-03

## 1. Head SHA and CI mapping

The branch refs were fetched using the GitHub commit endpoint, and workflow runs were queried for each resulting SHA.

| PR | Head branch | Head SHA | Latest observed run | Result | Notes |
|---|---|---|---|---|---|
| #13 | r03-52-7-3-6-resource-auth-debug2 | c38f22d72a54934dbca80759db1dd85b3903163c | #416 / 41496714183 | SUCCESS | Original reference PR; remains OPEN/DRAFT |
| #14 | r03-52-7-3-11-auth-boundary-review | cda9a05ea0ea06b4435fb05b5d3815e0913dd3ef | #420 / 41499382868 | SUCCESS | Authorization boundary and Store benchmark design |
| #15 | r03-52-7-3-11-3-request-digest-v2alpha2 | f5484b719e38a3c7145af26cf8470aab282058bb | #429 / 41503109841 | FAILURE | tenant-ed25519-verifier failed at PostgreSQL independent Request Digest v2alpha2 vs Python golden vector; validate-contracts passed |
| #16 | r03-52-7-3-11-3-remediation-gate | f3e90cd85a21744f2e99ba4c82bd05c4e57083d0 | #430 / 41503709136 | SUCCESS | Corrected PostgreSQL action/resource CASE expression |
| #17 | r03-52-7-3-11-3-raw-claim-parser | 2be9941b93b8dcf82d219c3cee660fe51d963ce4 | #431 / 41571959572 | SUCCESS | Nested duplicate-key rejection before jsonb conversion |
| #18 | r03-52-7-3-11-3-v2alpha2-db-verifier | 1a8de570698a271a489f1dc7b0e60efb2c1966ab | #437 / 41577147243 | SUCCESS | PostgreSQL assertion verifier |
| #19 | r03-52-7-3-11-3-receipt-arbitration | 8fb7dc5edc5954cd8b5ffc50bcce6833310550f6 | #438 / 41577279984 | SUCCESS | Receipt arbitration helper |
| #20 | r03-52-7-3-11-3-handler-integration-audit | a9394870164bba5971ffa82b15c83d7e9b9cfc47 | #439 / 41578429173 | SUCCESS | Source audit only |

| #21 | r03-52-7-3-11-3-preimplementation-closure | f3cef4b5dafff2a9b1b8e19e739c95b2a7d33ee5 | #486 / 41586441727 | SUCCESS | Both jobs passed on exact pre-batch HEAD; 34 Markdown files at that snapshot; preceding Run #485 on da06f11 also passed |

## 2. Interpretation

- PR #15 had a real failing PostgreSQL digest conformance run. PR #16's corrected branch then passed. The failure is historical evidence and must not be erased from the audit trail.
- PR #17/#18/#19 successes establish only the exact helper/reference tests executed by their workflows.
- PR #19 success does not close the Receipt fixture identity defect found by source review; the tests can pass while using an invalid replay fixture.
- PR #20 success validates its source-audit documentation CI, not a business Handler integration.
- The current PR search independently returned PR #13–#20 as OPEN / DRAFT; the closed-PR search did not return them.

## 3. G0 remaining work

- Named approval/sign-off evidence for DEC-03, DEC-14 and R535-OD3 was not located in the inspected canonical decision artifacts; obtain the required owner approvals or record the formal approval route. Product Code Freeze is stated ACTIVE in README/R03.52 records, but a separate named/signed freeze-authority artifact was not located.
- Complete line-by-line semantic review of the 81 scoped paths identified by the recursive PR #20 repository tree; path inventory and PR changed-file lists are complete.
- Verify CI on the latest PR #21 head after all documentation-only additions.

## 4. Gate conclusion

This closes the PR #13–#21 head mapping for the pre-batch snapshot and records Run #486 on the exact PR #21 HEAD (both jobs SUCCESS). Later staged audit changes are not covered by Run #486 and will be validated by the single CI run after the next batched commit. G0 remains IN_PROGRESS until governance artifact/sign-off checks and scoped semantic review are complete.

## Change history

- 2026-11-03: Added per-branch head SHA and workflow evidence.
- 2026-11-03: Added PR #21 exact pre-batch HEAD and completed Run #485 evidence.
