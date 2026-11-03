# Pre-Implementation Test Matrices and Proof Boundaries

**Version:** 0.1.0  
**Status:** TEST PLAN / NOT EXECUTED AS INTEGRATED SUITE  
**As-of:** 2026-11-03  
**Gate:** G11 OPEN

## 1. Unit Test Matrix

| ID | Test | Expected assertion | Proves | Does not prove |
|---|---|---|---|---|
| UT-01 | Strict JSON parser | Reject invalid UTF-8, duplicate keys at all depths, malformed JSON, unknown fields | Raw parser behavior | Signature or DB behavior |
| UT-02 | Typed codec primitives | Exact tags/lengths/order for null/bool/int64/string/array/object | Python canonical bytes | PostgreSQL parity |
| UT-03 | Golden vectors | Python digest equals published expected bytes/hash | Deterministic reference codec | Handler mutation binding |
| UT-04 | Action schema | Exact argument fields/types/ranges/null/extra rejection | Action argument validation | Persisted state |
| UT-05 | Claim schema | Every Claim field/limit and version discriminator | Schema validator | SQL verifier parity unless cross-run |
| UT-06 | Version classifier | One exact verifier family selected; no fallback | Pure dispatch rules | Actual operation entry wiring |
| UT-07 | Error mapping | Stable codes for each parse/claim/action conflict | Error translation | Outer transaction rollback |
| UT-08 | Retry policy binding | Trusted policy version, persisted attempt budget, retryable/delay/safe_message derivation and checked seconds↔microseconds conversion | Policy evaluation and action binding | Production policy approval or Handler transaction correctness |

## 2. PostgreSQL Integration Test Matrix

| ID | Test | Required setup | Expected assertion | Proves | Does not prove |
|---|---|---|---|---|---|
| PG-01 | Strict raw Claim parse | PostgreSQL 17, disposable schema | Duplicate keys rejected before jsonb | SQL parser | Production deployment safety |
| PG-02 | Ed25519 raw-payload verify | pgsodium, ephemeral signer/key fixture | Signature verifies exact decoded payload bytes | Database crypto verifier | Trusted key custody |
| PG-03 | Digest conformance | Python and SQL implementations | Exact golden bytes/hash match | Cross-language codec parity for tested vectors | Action mutation uses same values |
| PG-04 | Digest tampering | Signed Claim + changed argument JSON | Mismatch rejected | Helper detects changed arguments | Handler passes real SQL params |
| PG-05 | Receipt helper | Disposable Receipt table | Unique key, replay, conflict, finalization | Receipt helper semantics | Job/Nonce/Outbox atomicity |
| PG-06 | Nonce ledger | Shared nonce key and transaction fixture | Single use, rollback and cross-version behavior | Nonce primitive | All action handlers consume it |
| PG-07 | Complete Handler | Runtime role, signed Claim, Job/Session/Receipt/Nonce | One end-to-end Complete transaction | Actual Handler binding/UOW | Other actions |
| PG-08 | Catalog security | Runtime/Verifier/Dispatcher/Replay roles | Ownership, RLS, EXECUTE, membership, direct writes | Tested privilege boundary | Production credentials/provider |
| PG-09 | Receipt Reconcile | Legacy and v2alpha2 Receipt stores | Version-correct read and outcome verification | Correct reconciliation path | Business repair capability |

## 3. Concurrency Test Matrix

| ID | Race | Expected result | Required evidence |
|---|---|---|---|
| CC-01 | Two fresh assertions, same business envelope/key/digest, different nonces | One mutation and one Receipt; both fresh valid nonces are consumed/committed; both return the same stored outcome | Independent connections, barrier, nonce/Receipt/Job snapshots |
| CC-02 | Same key, different digest under fresh assertions | One winner; loser IDEMPOTENCY_CONFLICT; accepted loser assertion nonce is consumed atomically with the conflict result only if that business-rejection policy is approved | Unique-key wait observation and nonce snapshot |
| CC-03 | Same operation_id, different idempotency key | OPERATION_ID_CONFLICT | Unique index arbitration |
| CC-04 | Same nonce across two transactions/actions/versions | Exactly one nonce insert succeeds | Shared uniqueness domain |
| CC-05 | Complete vs Fail/Renew/Retry/Dead Letter | One valid state transition; stale competitor rejected | Job row locks + epoch/lease snapshots |
| CC-06 | Complete vs Complete with same Session revision | One revision increment only | Session FOR UPDATE/CAS |
| CC-07 | Outbox Dispatch vs Dispatch lease reclaim | One current dispatch epoch; stale worker fenced | Outbox owner/epoch/lease snapshots |
| CC-08 | Outbox Dispatch vs Ack | Ack only for exact active owner/epoch/event | Two-connection wait graph |
| CC-09 | Receipt Reconcile vs pending/finalizing action | No phantom success; pending/terminal semantics exact | Independent transaction snapshots |
| CC-10 | DLQ terminal transition vs replay | No duplicate terminal row or invalid replay | Job/DLQ lock order |
| CC-11 | Multi-row reverse acquisition order | No unhandled deadlock; whole transaction retry only | pg_locks/wait graph |
| CC-12 | Deadlock/serialization retry | Prior attempt rolled back; retry uses same business envelope and fresh nonce | SQLSTATE + exact before/after state |

## 4. Security Test Matrix

| ID | Attack | Expected result |
|---|---|---|
| SEC-01 | Cross-tenant Job/Session/Receipt/Outbox identifier | Deny; no row mutation |
| SEC-02 | Wrong subject/owner | Deny; no mutation |
| SEC-03 | Stale epoch or expired DB-clock lease | Deny; no mutation |
| SEC-04 | Claim action/resource mismatch | Deny before Receipt/Nonce writes |
| SEC-05 | Digest args differ from SQL mutation values | Deny before durable mutation |
| SEC-06 | Legacy token submitted to v2alpha2 entry | Reject; no fallback |
| SEC-07 | v2alpha2 token submitted to legacy entry | Reject |
| SEC-08 | PUBLIC EXECUTE on private helper | Catalog assertion fails |
| SEC-09 | Runtime direct write to protected table/fencing columns | Permission denied |
| SEC-10 | Runtime SET ROLE to privileged helper/admin | Permission denied |
| SEC-11 | search_path/temp object shadowing | No altered verifier/handler behavior |
| SEC-12 | Caller-controlled GUC spoofing | No authorization without signed transaction-bound evidence |
| SEC-13 | Revoked/expired/unknown key | Fail closed |
| SEC-14 | Duplicate JSON key / unknown field | Reject before jsonb digest path |
| SEC-15 | Outbox stale dispatcher ack | Reject by owner/epoch fence |
| SEC-16 | Exact old signed assertion replay after committed nonce | `ASSERTION_REPLAYED`; Receipt lookup cannot override the nonce collision |

## 5. Rollback Test Matrix

| ID | Failure point | Required after-state |
|---|---|---|
| RB-01 | Receipt reservation then outer rollback | No new Receipt |
| RB-02 | Nonce insertion then outer rollback | No new Nonce |
| RB-03 | Job mutation then Session failure | Job/Session/Receipt/Nonce unchanged |
| RB-04 | Job/Session mutation then Transition insert failure | Entire write set absent |
| RB-05 | Transition insert then Outbox insert failure | Entire write set absent |
| RB-06 | DLQ insert failure | Job terminal change and all companion rows absent |
| RB-07 | Receipt finalization failure | No committed pending Receipt or partial business state |
| RB-08 | Outer caller rollback after successful Handler return | All operation rows/mutations absent |
| RB-09 | Deadlock/serialization failure | Attempt fully rolled back; retry fresh nonce only |
| RB-10 | Ambiguous COMMIT | Exactly all-or-none state; reconcile by stable operation identity |

Formal commit-boundary failure injection is excluded from this phase. RB-10 is a contract to be tested in R03.52.7.3.11.4 only after G0–G14 acceptance.

## 6. Existing suite coverage

- PR #15: Python digest and PostgreSQL digest golden vectors; initial CI failure corrected by PR #16.
- PR #17: strict raw JSON duplicate-key parser conformance.
- PR #18: PostgreSQL Ed25519 verifier, raw payload signature, digest mismatch cases.
- PR #19: Receipt helper uniqueness, finalization, concurrent first use and Receipt-only rollback.
- PR #13: legacy resource authorization, RLS, nonce, lease fencing, Outbox/DLQ, concurrency and rollback reference suite.

Existing tests cover portions of UT/PG/SEC/CC for their isolated reference helpers. They do not cover UT-08 policy-to-Handler binding, PG-07, PG-09, CC-01/04/05/06/07/08/09/10 in the integrated v2alpha2 path, or the full RB matrix.

## 7. Gate conclusion

G11 remains OPEN. The test matrix is defined but the integrated test layers and persisted-state snapshots are not implemented. No test is claimed passed merely because a helper-level suite is green.

## Change history

- 2026-11-03: Initial detailed unit/PG/concurrency/security/rollback matrices.
