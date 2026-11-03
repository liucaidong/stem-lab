# R03.52.7.3.11.4 — Decision Closure Matrix

**Status:** RECOMMENDATIONS RECORDED / NO NEW DECISION APPROVED  
**As of:** 2026-11-03

## 1. Existing decision status

| ID | Existing state | Scope | Effect |
|---|---|---|---|
| DEC-03 | OPEN | Production Worker runtime/protocol | Do not select production runtime; reference harness may remain explicitly non-production |
| DEC-04 | ACCEPTED at architecture-principle level | Language-neutral Store Protocol + explicit UOW | Does not select adapter, driver, pool or migration tooling |
| DEC-14 | OPEN | Production deployment/provider/topology | No production provider/topology selection |
| DEC-16 | OPEN | DLQ Replay new Job ID strategy | Replay cannot be enabled |
| DEC-19 | ACCEPTED target architecture only | Tenant trust-boundary target | Production issuer/verifier/grants/operations remain unverified |
| DEC-30 | OPEN | Event relay/replay side-effect policy | No replay event policy inferred |
| R535-OD3 | OPEN / PROPOSED | Request digest/canonicalization | G1 blocked |
| R535-OD5 | OPEN | Verifier/helper privilege boundary | G9 blocked |
| Product Code Freeze | ACTIVE; signed authority record not located | Product/business implementation freeze | No production Business Handler implementation |

## 2. Recommended decisions requiring approval

| ID | Question | Recommendation | Rationale / compatibility | Approver role | Blocks implementation |
|---|---|---|---|---|---|
| ADR-PRE-01 | Version routing | Explicit discriminator selects exactly one verifier; unknown/unsupported action fails closed; no generic fallback | Prevents downgrade; legacy paths remain unchanged | Architecture + Security | YES |
| ADR-PRE-02 | Digest/mutation source | One immutable typed action binding supplies both digest and SQL mutation parameters | Removes parameter substitution | Protocol + Security + Worker | YES |
| ADR-PRE-03 | Nonce versus Receipt order | Consume/check nonce before Receipt success arbitration | Exact old token replay must never become Receipt success; fresh nonce business retry remains supported | Protocol + Security + Database | YES |
| ADR-PRE-04 | Receipt Reconcile | Separate SELECT-only lookup; typed missing/pending/terminal/inconsistent; no-create/no-finalize | Reserve is insert-first; Reconcile must not create pending rows | Protocol + Database + Security | YES |
| ADR-PRE-05 | Reconcile nonce outcome | Commit fresh Reconcile nonce with typed read outcomes; roll it back on auth/infrastructure/transaction failure | Makes read request single-use without mutating target business state | Security + Protocol | YES |
| ADR-PRE-06 | Atomic write set | One caller-owned outer transaction for nonce, Receipt, Job/Session, Transition and Outbox writes | Prevents partial durable state | Architecture + Database | YES |
| ADR-PRE-07 | Lock order | Nonce unique arbitration → Receipt arbitration → action-specific Job/Session/DLQ/Outbox locks → append-only Transition/Outbox → Receipt finalize; prove each action path | Honors replay semantics; lock graph still needs proof | Database + Worker | YES |
| ADR-PRE-08 | COMMIT ambiguity | Discard uncertain connection; fresh Assertion/nonce for Reconcile; same operation identity/key/digest; retry only through unique-key arbitration | Prevents duplicate mutation and false rollback assumption | Database + Runtime + Security | YES |
| ADR-PRE-09 | Retry authority | Registry is the only policy source; policy_version is pinned and included in typed signed binding; attempt_count/max_attempts come from persisted Job | Signature alone does not make caller-selected delay trustworthy | Worker + Protocol + Security | YES |
| ADR-PRE-10 | Retry units | Integer microseconds canonical for v2alpha2 Fail and Retry; legacy seconds converted only at adapter boundary using Decimal and explicit ROUND_HALF_EVEN; proposed ceiling 86,400 seconds | Aligns current Store/Retry ceiling and removes float drift; requires policy owner approval | Worker + Protocol | YES |
| ADR-PRE-11 | Retry fields | error_code 1..128, safe_message 1..512; retryable/delay cross-field rules; policy version and persisted attempt budget validated | Aligns Registry/Store compatibility; v2alpha2 vectors must be versioned | Worker + Protocol | YES |
| ADR-PRE-12 | Claim numeric bounds | epoch/iat/exp safe integer domain 0..2^53-1 (epoch/exp minimum 1); SQL checks numeric bounds before casts; stable overflow error | Matches JSON Schema and avoids raw bigint overflow | Protocol + Database | YES |
| ADR-PRE-13 | Canonical bytes/input budgets | Keep 4-byte big-endian length prefix with accepted positive length <=2^31-1; proposed Claim 16 KiB, arguments 256 KiB, total canonical bytes 1 MiB | Practical DoS boundary; validate product payload assumptions | Protocol + Security | YES |
| ADR-PRE-14 | SQL privileges | Prefer invoker + exact minimal grants/RLS; if direct grants cannot be constrained, use a dedicated capability-specific NOLOGIN definer owner with fixed search_path and exact grants; never shared broad verifier owner | Least privilege without broad Runtime table access | Security + Database | YES |
| ADR-PRE-15 | DLQ Replay scope | Exclude from initial v2alpha2 Handler slice and reject before writes; revisit only after trusted actor/policy/reason/request/new-ID binding and atomic replay UOW | DEC-16/DEC-30 remain OPEN; current digest args are empty | Project Owner + Worker + Security | YES for Replay; NO for other actions if formally excluded |
| ADR-PRE-16 | Outbox side effects | Insert Outbox in business transaction; relay only after commit; delivery at-least-once; consumer inbox/event_id dedup | External broker I/O cannot be atomic with PostgreSQL | Architecture + Messaging | YES |
| ADR-PRE-17 | Product Code Freeze | Keep ACTIVE until all mandatory gates and named approvals pass; then explicit owner authorization for bounded implementation scope | CI/document completion is not release authority | Project Owner | YES |

## 3. Decisions that may remain deferred without selecting production technology

DEC-03 and DEC-14 may remain OPEN if the next increment is explicitly limited to a disposable, non-production reference implementation and does not select production Worker runtime, Store adapter, driver, pool, provider or deployment topology. They cannot be represented as accepted production choices.

DEC-16 and DEC-30 may remain OPEN only if DLQ Replay is formally excluded and fails closed. DEC-19 remains target-only until production signer/key custody and database verification are approved.

## 4. Required approvals

No named approval record was found for R535-OD3, R535-OD5, DEC-03, DEC-14, DEC-16, DEC-30, production DEC-19 verification, or Product Code Freeze release. PR #21 has no submitted Review or inline review thread at the inspected snapshot.

The recommendations above are not approvals. Each normative decision needs a named owner, explicit ACCEPTED/REJECTED/DEFERRED status, date, scope, and linked acceptance tests.

## 5. Gate conclusion

G1/G2/G3/G4/G5/G6/G7/G8/G9/G10/G11/G12/G13/G14 remain BLOCKED until applicable decisions are approved and evidence passes. No OPEN decision is closed by this matrix.
