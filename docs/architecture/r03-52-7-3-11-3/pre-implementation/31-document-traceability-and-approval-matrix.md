# Pre-Implementation Document Traceability and Approval Matrix

**Version:** 0.1.0  
**Status:** GOVERNANCE REGISTER / OPEN  
**As-of:** 2026-11-03  
**Implementation authorization:** NO — all documents are pre-implementation audit/design only.

## 1. Status and approval rules

- **SOURCE-VERIFIED:** a source fact was fetched and checked; design decisions may still be open.
- **PROPOSED:** candidate contract/design, not accepted.
- **OPEN:** required decision, evidence or test is incomplete.
- **IN_PROGRESS:** partial evidence exists; closure conditions remain.
- **BLOCKED:** downstream gate cannot pass.
- **ACCEPTED:** only when a named authority explicitly approves the exact scope and evidence.

No document in this PR grants business Handler implementation permission. G15 remains BLOCKED. All numbered audit artifacts are pre-implementation evidence/design only; none is an implementation approval.

## 2. Document traceability matrix

| File | Status | Gate(s) | Evidence basis | Dependencies | Decision owner | Acceptance criteria | Implementation allowed |
|---|---|---|---|---|---|---|---|
| 00-baseline-and-scope.md | SOURCE-VERIFIED BASELINE | G0 | PR metadata, PR #20 HEAD, CI #439, source inventory | GitHub current state | Architecture governance | Current PR states/heads/files/CI and constraints independently verified | NO |
| 01-gap-register-and-dependencies.md | OPEN | G0–G15 | PR #20 audit and fetched source assets | All source inventories | Architecture + Security | Every gap has owner, evidence, dependency and closure proof | NO |
| 02-entry-gate-matrix.md | IN_PROGRESS | G0–G15 | Source and CI evidence available at creation | All G0–G14 artifacts | Architecture + Security | G0–G14 ACCEPTED before G15 | NO |
| 03-protocol-digest-source-audit.md | OPEN | G1 | PR #15 schema/Python/SQL, PR #17 parser, PR #18 verifier | R535-OD3, golden vectors, typed binding | Protocol + Security | Exact cross-language bytes/fields/limits and mutation binding accepted | NO |
| 04-receipt-and-nonce-contract-audit.md | OPEN | G5/G6 | PR #19 Receipt helper/test and PR #13 nonce ledger | G1/G2/G4 | Protocol + Database + Security | Receipt/Nonce replay, transaction and cross-version semantics tested | NO |
| 05-atomic-uow-locking-and-failure-contract.md | PROPOSED | G7/G8/G10 | PR #20 candidate sequence and R03.52.7.3.5 transaction principles | G4–G6, action write sets | Database + Architecture | One outer transaction, lock graph, rollback and error propagation proven | NO |
| 06-action-handler-binding-matrix.md | PROPOSED | G4/G12/G13 | PR #15 action map, PR #20 audit and R03.52.5 DLQ preflight | G1–G3 | Protocol + action owner + Security | Eight in-scope actions have typed bindings; `worker.dlq.replay` is explicitly fail-closed until its empty digest args and replay plan fields are reconciled | NO |
| 07-postgresql-security-model-audit.md | OPEN | G9 | PR #13 role fixture, PR #14/11.1 inventory and v2alpha2 Receipt SECURITY INVOKER audit | Action call graph, R535-OD5 | Security + Database | Least-privilege role/ownership/EXECUTE/RLS/catalog tests pass; Receipt helper invoker/definer choice is explicit | NO |
| 08-postgresql-test-strategy.md | PROPOSED | G11 | Existing workflow, PostgreSQL helper tests and R03.52.5 preflight | G1–G10/G13 | Test + Database | Reusable fixtures, Handler/UOW, DLQ replay atomicity, security and proof boundaries accepted | NO |
| 09-worker-job-complete-vertical-slice.md | PROPOSED | G12 | PR #13 Complete path, PR #15 digest fields, PR #20 audit, R03.52.7.3.5 | G1–G11 | Architecture + Worker + Security | Sequence, state, writes, locks, errors and full UOW tests accepted | NO |
| 10-remaining-action-designs.md | PROPOSED | G13 | PR #13 handler signatures, PR #15 action map and R03.52.5 preflight | Complete slice and G1–G11 | Architecture + Worker | Each action delta accepted; DLQ replay remains separately deferred and fail-closed until typed fields/provenance and atomic UOW are approved | NO |
| 11-decision-and-deferred-register.md | OPEN | G0/G14/G13 | R03.20, R03.52.7.3.5, R03.52.5 and PR #14/#15 records | Named decision owners | Project owner + Architecture + Security + Worker | DEC-03/14/16/19/30, R535 and Product Code Freeze states/owners/approvals are authoritative; DEC-16/30 remain open and DEC-19 target-only | NO |
| 12-risk-register.md | OPEN | G14 | Source audits and design gap analysis | All gates | Risk owners per row | Critical/high risks closed or explicitly accepted by owner | NO |
| 13-cross-document-consistency-audit.md | OPEN | G14 | Documents 00–12 and PR #20 audit | All normative contracts | Independent Architecture + Security | No unresolved contradiction across accepted contracts | NO |
| 14-version-dispatch-and-trusted-signer-audit.md | OPEN | G2/G3 | v1alpha1/v2alpha1/v2alpha2 schemas, PR #15 signer design and unsupported-action audit | G1, key trust decision | Protocol + Security | One fail-closed verifier path; unsupported digest-map actions (including DLQ replay) reject before writes; trusted key lifecycle accepted | NO |
| 15-interim-gate-status-report.md | BLOCKED | G0–G15 | Snapshot of GitHub/CI/source evidence at authoring | All gates | Architecture governance | Current G0–G14 evidence refreshed and all mandatory gates accepted | NO |
| 16-failure-semantics-persisted-state-contract.md | PROPOSED | G10 | User-specified failure classes and UOW candidate | G7/G8 and action write sets | Database + Test + Security | Every failure has exact before/after snapshot acceptance | NO |
| 17-lock-dependency-graph.md | PROPOSED | G8 | PR #20 candidate sequence; R03.20 Run #208/#210/#212 deadlock evidence | All action SQL and FK/index edges | Database | Acyclic lock order proven under multi-connection tests | NO |
| 18-pr-source-inventory.md | IN_PROGRESS | G0 | PR #13–#20 changed-file inventory and fetched source | Exact PR-object head mapping | Architecture governance | Per-PR current head, files, CI and governance artifacts verified | NO |
| 19-protocol-semantic-conflict-register.md | OPEN | G1/G4/G5/G6 | PR #15 envelope/action/Receipt semantics and PR #19 helper | Protocol owner decision | Protocol + Security | Conflicts resolved in normative contract and vectors | NO |
| 20-recommended-closure-decisions.md | PROPOSED | G1–G10 | Source audits and security/transaction principles | Named decision approval | Project owner + Architecture + Security + Database | Each recommendation explicitly accepted/rejected/deferred | NO |
| 21-pr-head-and-ci-evidence-matrix.md | IN_PROGRESS | G0 | GitHub branch refs and workflow runs | PR-object head mapping | Architecture governance | Current PR heads map to exact branch refs and CI evidence | NO |
| 22-receipt-fixture-correction-spec.md | PROPOSED | G5/G11 | PR #19 test fixture and Request Envelope fields | G1/G5/G6 | Test + Protocol | Corrected fixtures use recomputed digest and fresh nonce semantics | NO |
| 23-claim-validation-parity-matrix.md | OPEN | G1 | JSON Schema vs SQL verifier vs Python codec | Normative field/limit table | Protocol + Security | All Claim fields/limits/errors have exact parity | NO |
| 24-action-argument-bounds-audit.md | OPEN | G1/G4 | Python and SQL action argument validators | Retry policy/error taxonomy/artifact model | Worker + Protocol | Every action arg has closed type, range, size and cross-field rules | NO |
| 25-reissued-assertion-nonce-reconciliation.md | OPEN | G5/G6/G10 | R03.52.7.3.5 Section 8 and PR #19 helper | Receipt/Nonce normative contract | Security + Protocol + Database | Exact replay, reissue and ambiguous-commit paths tested | NO |
| 26-legacy-action-compatibility-baseline.md | OPEN | G0/G2/G4 | PR #13 legacy PostgreSQL fixture | Complete regression suite | Worker + Security | Legacy behavior remains unchanged and regression tests pass | NO |
| 27-canonicalization-boundary-audit.md | OPEN | G1 | PR #15 canonicalization ADR, Python codec, SQL codec | R535-OD3 | Protocol + Database | Byte limits, typed args and SQL/Python vectors approved | NO |
| 28-receipt-storage-and-reconciliation-gap.md | OPEN | G5/G6/G9 | Legacy/v2alpha2 Receipt split; insert-first reserve helper and missing read-only lookup | Receipt reconcile contract | Protocol + Database + Security | Dedicated version-correct SELECT-only lookup; no-create/no-finalize invariant and cross-version idempotency proven | NO |
| 29-receipt-helper-contract-security-gaps.md | OPEN | G5/G7/G9/G10 | PR #19 Receipt SQL; default SECURITY INVOKER and privileged test connection | Least-privilege and UOW design | Database + Security | Reserve/finalize identity, outcome bounds, invoker grants/RLS or capability-scoped definer boundary are enforced | NO |
| 30-legacy-postgresql-role-grant-matrix.md | SOURCE-VERIFIED LEGACY FIXTURE | G9 | PR #13 role/grant/RLS source | v2alpha2 role design | Security + Database | Legacy baseline preserved; v2alpha2 target least-privilege tests pass | NO |
| 31-document-traceability-and-approval-matrix.md | GOVERNANCE REGISTER / OPEN | G0–G15 | This PR's complete audit inventory | All numbered documents and approval records | Architecture governance | Every artifact has traceable owner, evidence, dependencies and explicit non-authorization status | NO |
| 32-test-matrix-detail.md | PROPOSED | G11/G13 | Existing helper CI, action test gaps and R03.52.5 replay preflight | Integrated fixture design | Test + Database | Unit/PG/concurrency/security/rollback matrices pass, including PG-11 DLQ replay atomicity and SEC-17 unsupported-action fail-closed behavior | NO |
| 33-retry-policy-authority-and-delay-unit-audit.md | SOURCE-VERIFIED GAP / NOT ACCEPTED | G1/G4/G13 | R03.52.4 Retry Policy Registry, v2alpha2 action codec/SQL and legacy Store protocol | Trusted policy authority, policy version and delay-unit decision | Worker + Protocol + Security + Database | Trusted source, pinned policy version, bounds and exact conversion accepted and tested | NO |

| 34-final-source-audit-report.md | SOURCE AUDIT PARTIAL / BLOCKED | G0–G14 | 81-path inventory, source SHA/line evidence and GAP register | Remaining per-path semantic review | Architecture + Worker + Database + Security | All 81 paths reviewed line-by-line and findings closed/accepted | NO |
| 35-atomic-unit-of-work-formal-model.md | TARGET MODEL / NOT ACCEPTED | G2–G8/G10/G11 | R03.52.7.3.5, Store Protocol and v2alpha2 helper sources | Handler/Adapter, lock graph, Receipt/Nonce approval | Architecture + Database + Security | One outer transaction and failure/recovery behavior proven | NO |
| 36-cross-module-contract-consistency-matrix.md | SOURCE-VERIFIED DISCREPANCIES | G1–G10/G13 | Python, Store Protocol, SQL, schemas and fixtures | Normative contract decisions | Protocol + Worker + Database + Security | All field/type/range/unit/error/permission mismatches resolved | NO |
| 37-security-and-tenant-isolation-gate.md | SECURITY GATE BLOCKED | G9 | Receipt SQL, legacy role matrix, v2alpha2 verifier and threat model | Catalog/negative tests and privilege decision | Security + Database | Least-privilege Runtime and tenant isolation proven | NO |
| 38-decision-closure-matrix.md | RECOMMENDATIONS ONLY / NOT APPROVED | G1–G14 | DEC register, R535 records, Product Code Freeze and source audits | Named approvals for each normative decision | Project Owner + Architecture + Security + Database + Worker | All blocking decisions recorded ACCEPTED/REJECTED/DEFERRED by authority | NO |
| 39-fault-injection-and-acceptance-matrix.md | TEST PLAN / NOT EXECUTED | G7/G10/G11 | Existing helper/legacy tests and transaction target model | Integrated v2alpha2 Handler/UOW | Test + Database + Security | Required unit/PG/concurrency/catalog/crash/COMMIT tests pass | NO |
| 40-documentation-consistency-report.md | CONSISTENCY REVIEW PARTIAL | G0/G13/G14 | PR #21 docs 00–33, current PR/CI snapshot | Full link/ID scan and remaining source audit | Architecture governance | Cross-reference scan and approval traceability complete | NO |
| 41-implementation-entry-gate.md | BLOCKED | G0–G15 | Source audit, security, transaction, test and approval artifacts | All predecessor gates | Architecture + Security + Project Owner | G0–G14 PASS or approved N/A; G15 explicitly approved | NO |
| 42-final-pre-implementation-closure-report.md | NOT READY | G0–G15 | Current repository snapshot and docs 34–41 | Blocker closure and owner authorization | Project Owner + Architecture + Security + Database + Worker | All blockers closed, evidence verified and explicit entry approval | NO |

## 3. Approval record requirements

When a row is accepted, record:
- decision ID and exact scope;
- named approver(s) and date;
- exact document version/commit SHA;
- evidence and test run IDs;
- residual risks and review date;
- affected Gate(s) and dependency rows;
- explicit implementation permission (must remain NO until G15).

## 4. Current approval state

No G0–G14 gate is accepted by this PR. Existing architecture principles DEC-04 and DEC-19 remain accepted only within their previously recorded scope. DEC-03/DEC-14 remain OPEN; R535-OD3 remains proposed/unapproved; Product Code Freeze remains ACTIVE.

## 5. Gate conclusion

G15 remains BLOCKED. This matrix makes document ownership and evidence traceability explicit; it does not replace independent approval or test proof.

## Change history

- 2026-11-03: Initial pre-implementation document traceability matrix.
- 2026-11-03: Added governance/test/retry-policy audit traceability rows.
- 2026-11-03: Added final source audit, Atomic UoW, contract matrix, security gate, decision closure, test matrix, documentation consistency and final entry-gate artifacts (34–42).
