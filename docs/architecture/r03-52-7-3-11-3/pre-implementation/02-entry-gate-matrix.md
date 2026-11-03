# R03.52.7.3.11.3 — G0–G15 Entry Gate Matrix

**Version:** 0.1.0  
**Status:** ALL GATES PROVISIONAL; G15 BLOCKED  
**As-of:** 2026-11-03

## 1. Gate acceptance rule

G0–G14 must each be explicitly ACCEPTED with source/document evidence, applicable test evidence, unresolved issue review and named decision authority before G15 may be ACCEPTED. A gate is not accepted merely because a related helper or isolated test passes. OPEN, BLOCKED or security-/compatibility-/atomicity-relevant DEFERRED items block G15.

## 2. Gate register

| Gate | Required deliverable | Current evidence | Current state | Minimum acceptance criteria |
|---|---|---|---|---|
| G0 | GitHub/source/decision baseline + Gap Register | PR #13–#20 search, PR #20 HEAD/files/run #439, source inventory; additional DEC/freeze verification pending | IN_PROGRESS | All PR states/heads/files/CI and decision/freeze records verified; PR #13 immutability proven |
| G1 | Assertion / Digest Contract | PR #15 Python/SQL codec, schema, vectors; PR #17 strict parser; PR #18 verifier | OPEN | Exact payload/signature/digest bytes and all boundary rules approved; cross-language vectors pass |
| G2 | Version Compatibility Contract | Legacy v2alpha1 path and v2alpha2 candidate discriminator documented | OPEN | Explicit fail-closed dispatch; no downgrade/cross-version replay; old behavior regression tests |
| G3 | Trusted Signer / Key Trust Boundary | Disposable issuer key lookup and Ed25519 verifier | OPEN | Trusted issuer provenance, key lifecycle, revocation, role access and failure mapping accepted |
| G4 | Action-Specific Typed Binding | PR #20 binding proposal for nine action names | OPEN | Every field sourced once from verified Claim or typed operation args; digest and mutation use same values |
| G5 | Receipt / Idempotency | PR #19 helper + two-connection arbitration/rollback tests | OPEN | Identity-consistent replay, conflict semantics, pending visibility and business UOW integration proven |
| G6 | Nonce / Cross-Version Replay | Legacy nonce ledger reference only | OPEN | v2alpha2 durable uniqueness, consumption/rollback/retention and cross-version matrix accepted |
| G7 | Atomic Unit-of-Work | No integrated v2alpha2 complete write set | OPEN | Job/Session/Receipt/Nonce/Transition/Outbox/(DLQ) atomicity proven at outer transaction boundary |
| G8 | Lock Ordering / Concurrency | Candidate Job path order in PR #20 audit; no all-action graph | OPEN | Lock graph acyclic or justified; concurrent races and retry behavior tested |
| G9 | SQL Permissions / RLS | Legacy role/policy inventory; v2alpha2 grants not accepted | OPEN | Least privilege, function ownership, PUBLIC revocation, RLS and catalog assertions pass |
| G10 | Failure / Persisted-State Contract | Failure categories listed in task; no full state snapshots | OPEN | Every failure class maps to exact allowed/forbidden persisted changes |
| G11 | PostgreSQL Test Strategy | Existing CI + independent helper harnesses | OPEN | Reusable fixture, multi-connection, outer tx, snapshot, catalog and RLS test plan approved |
| G12 | Complete Vertical Slice Design | Action argument candidate fields in PR #20 audit | OPEN | Sequence/state diagrams, mutation inventory, locks, errors, persisted-state and file plan complete |
| G13 | Remaining Action Designs | Candidate action list exists | OPEN | Fail/Retry/Renew/Dead Letter/Receipt reconcile/Outbox Dispatch/Ack each has explicit delta contract |
| G14 | Architecture/Security Cross-Audit | PR #20 source audit exists | OPEN | Independent review closes contradictions, risks and deferred decisions without weakening constraints |
| G15 | Code Implementation Entry Gate | This matrix | BLOCKED | G0–G14 all ACCEPTED; no critical OPEN/BLOCKED/DEFERRED item; explicit approval recorded |

## 3. G0 detailed status

| G0 subcheck | Result | Evidence / limitation |
|---|---|---|
| PR #13–#20 existence and open/draft status | PASS | PR object metadata checked individually; all eight OPEN, DRAFT=true, merged=false |
| PR #13–#20 exact head/base chain | PASS | Exact PR-object head SHA, head branch, base branch and base SHA fetched for all eight; PR #13 → #14 → #15 → #16 → #17 → #18 → #19 → #20 stacked chain confirmed |
| PR #20 HEAD | PASS | `a9394870164bba5971ffa82b15c83d7e9b9cfc47` fetched |
| PR #20 changed files | PASS | One documentation file only |
| PR #20 CI | PASS | Workflow run #439 / ID `41578429173` completed success |
| PR #13 reference unchanged | PASS for PR #21 diff | PR #21 changed-file list contains only new Markdown audit documents; no PR #13 reference implementation path is modified |
| DEC-03 / DEC-14 / R535-OD3 current authoritative records | PARTIAL | R03.20 decision register and PR #15/#20 bodies confirm DEC-03/DEC-14 OPEN and R535-OD3 OPEN/PROPOSED; named approval/sign-off evidence still needs inventory |
| Product Code Freeze | PARTIAL | README and R03.52.7.3.11 docs record ACTIVE; exact governing freeze artifact still needs identification |
| Existing SQL/test/worker docs inventory | PARTIAL | Key PR #13/#15/#18/#19 assets fetched; complete repository-wide inventory remains |
| v1alpha1/v2alpha1 compatibility baseline | PARTIAL | Legacy verifier and nonce source inspected; full behavior matrix remains |

G0 remains IN_PROGRESS until all subchecks are closed.

## 4. Gate evidence rules

Each gate record must link to:
1. Exact repository path and commit/blob SHA.
2. Relevant test name, environment and result.
3. CI run ID and commit SHA where applicable.
4. Any assumptions and what the evidence does not prove.
5. Decision record and approving owner for normative protocol/security choices.

## 5. Prohibited gate shortcuts

- Do not accept G1 because Python and PostgreSQL helpers pass independently if cross-language and actual mutation binding is unproven.
- Do not accept G5 because Receipt helper concurrency passes without integrated Job/Nonce/Transition/Outbox state snapshots.
- Do not accept G7 because a handler function returns successfully; prove the outer caller transaction boundary.
- Do not accept G9 based only on RLS tests run as table owner or superuser.
- Do not run formal G10 fault injection as R03.52.7.3.11.4 before prerequisite gates pass.
- Do not change gate definitions or acceptance criteria to convert a blocked gate to accepted.

## 6. Change history

- 2026-11-03: Initial gate matrix created from user-supplied task and PR #20 source audit evidence.
