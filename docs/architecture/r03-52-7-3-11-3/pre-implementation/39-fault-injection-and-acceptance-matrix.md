# R03.52.7.3.11.4 — Fault-Injection and Acceptance Matrix

**Status:** TEST PLAN / NOT EXECUTED / FORMAL COMMIT INJECTION BLOCKED  
**CI baseline:** PR #21 HEAD `c0504a5f92a36d8a04dddfaef34b5f395561ff31`, Run #488

## 1. Existing test evidence and limits

- Python Request Digest tests cover ASCII/Unicode golden vectors, key ordering, duplicate JSON keys, int64 typed values, float rejection and action/resource shape.
- PostgreSQL digest tests cover strict raw Claim duplicate keys, ASCII/Unicode digest vectors, tampered args, raw Ed25519 payload verification and signature rejection. The test extracts function bodies from the SQL asset and does not execute the complete malformed file as one asset.
- Receipt tests cover helper-level same-key arbitration, digest conflict, operation uniqueness, terminal finalization, two-connection first-use race and outer rollback. They do not test Reconcile, no-create, least-privilege roles, full business state snapshots or valid fresh-nonce reissue.
- Legacy PR #13 and R03.51 ingestion Worker tests cover reference-path nonce/RLS/fencing/rollback/concurrency. They are not v2alpha2 Handler/UOW tests.
- Retry tests cover Registry calculation and validation, not authoritative WorkerRuntime integration or policy-version pinning.
- DLQ tests cover caller-constructed preflight plans, not trusted production authorization or database atomic replay.
- Run #488 succeeds for current workflow jobs; it does not run a complete v2alpha2 Handler/UOW suite.

## 2. Acceptance matrix

| ID | Layer | Scenario | Required assertion | Maps to | Current state |
|---|---|---|---|---|---|
| UT-01 | Unit | Exact consumed Assertion replay | ASSERTION_REPLAYED; Receipt not queried for success | G2/G6, SA-12 | NOT IMPLEMENTED |
| UT-02 | Unit/Contract | Fresh nonce, same immutable Envelope/key/digest | Existing Receipt outcome; no second mutation | G2/G5/G6 | PARTIAL helper only |
| UT-03 | Unit | Same key, different digest | IDEMPOTENCY_CONFLICT; no mutation | G5 | PARTIAL helper only |
| UT-04 | Unit | Same operation_id, different key | OPERATION_ID_CONFLICT | G5 | PARTIAL helper only |
| UT-05 | Unit | Retry Policy callback forgery | Forged FailureDecision rejected; Registry/version authoritative | G4/G6 | NOT IMPLEMENTED |
| UT-06 | Unit | Retry delay conversion and bounds | Exact micros/seconds conversion; max/max+1 and rounding vectors | G1/G4 | NOT IMPLEMENTED |
| UT-07 | Unit | Claim numeric overflow | 2^53-1 accepted where valid; +1 rejected; bigint max+1 stable error | G1/G10 | NOT IMPLEMENTED |
| UT-08 | Unit | Claim/Envelope/args/canonical size | Each surface max accepted, max+1 rejected before expensive work | G1/G10 | NOT IMPLEMENTED |
| CT-01 | Contract | Python/SQL digest parity | Byte-for-byte canonical bytes and digest across all actions | G1/G4 | PARTIAL golden vectors |
| CT-02 | Contract | Unsupported action/version | Fail closed before any write; no generic handler fallback | G2 | NOT IMPLEMENTED |
| PG-01 | PostgreSQL | Complete v2alpha2 vertical slice | One transaction writes Job/Session/Nonce/Receipt/Transition/Outbox | G4/G5/G6/G7 | NOT IMPLEMENTED |
| PG-02 | PostgreSQL | Receipt Reconcile missing target | Typed missing; no Receipt/Job/Session/Transition/Outbox mutation | G5/G9 | NOT IMPLEMENTED |
| PG-03 | PostgreSQL | Receipt Reconcile pending/terminal/inconsistent | Typed result; SELECT only; target row unchanged | G5/G9 | NOT IMPLEMENTED |
| PG-04 | PostgreSQL | Receipt helper catalog security | owner, prosecdef, search_path, ACL, schema USAGE, RLS, role membership | G9 | NOT IMPLEMENTED |
| PG-05 | PostgreSQL | Cross-tenant Receipt read/write | Runtime cannot read/modify another tenant's Receipt | G9 | NOT IMPLEMENTED |
| CC-01 | Concurrency | Same idempotency key + same digest, fresh nonces | Exactly one mutation and one terminal Receipt | G5/G7/G8 | NOT IMPLEMENTED |
| CC-02 | Concurrency | Same key + different digest | One deterministic conflict; no second mutation | G5/G8 | PARTIAL helper arbitration |
| CC-03 | Concurrency | Same nonce submitted twice | Exactly one transaction consumes nonce; other gets ASSERTION_REPLAYED | G6/G8 | NOT IMPLEMENTED v2alpha2 |
| CC-04 | Concurrency | Concurrent Complete/Fail/Renew | Valid lock order, one allowed state transition | G7/G8 | NOT IMPLEMENTED v2alpha2 |
| FI-01 | Fault injection | Failure before BEGIN | No persisted changes | G10/G11 | NOT RUN |
| FI-02 | Fault injection | Disconnect before COMMIT reaches server | Transaction rolls back; fresh-nonce retry safe | G5/G7/G11 | NOT RUN |
| FI-03 | Fault injection | COMMIT succeeds, response dropped | One committed write set; Reconcile finds terminal Receipt | G5/G7/G11 | NOT RUN |
| FI-04 | Fault injection | COMMIT rejected definitively | Known abort; no partial writes | G7/G10/G11 | NOT RUN |
| FI-05 | Fault injection | COMMIT outcome delayed/unknown | Return TRANSACTION_OUTCOME_UNKNOWN; discard connection | G5/G11 | NOT RUN |
| FI-06 | Fault injection | Process crash before COMMIT | PostgreSQL rolls back entire write set | G7/G10/G11 | NOT RUN |
| FI-07 | Fault injection | Process crash after COMMIT | Durable Receipt/Nonce/Mutation/Outbox; fresh Reconcile | G5/G7/G11 | NOT RUN |
| FI-08 | Fault injection | Outbox insert fails | Job/Session/Receipt/Nonce/Transition all roll back | G7/G8/G11 | NOT RUN |
| SEC-01 | Security | Runtime direct Receipt table access | Denied unless explicitly approved exact privilege | G9 | NOT IMPLEMENTED |
| SEC-02 | Security | PUBLIC EXECUTE / role escalation / search_path | No unauthorized function or object shadowing path | G9 | NOT IMPLEMENTED |
| SEC-03 | Security | Forged DLQ Replay actor/policy/reason | Fail closed before writes | G7/G9 | Preflight only |
| SEC-04 | Security | Cross-version nonce reuse/downgrade | Denied; no legacy fallback | G2/G6/G9 | NOT IMPLEMENTED |
| REC-01 | Recovery | Receipt absent after unknown commit | Do not infer rollback solely from one missing read; same-key unique arbitration on retry | G5/G11 | NOT IMPLEMENTED |

## 3. Mandatory persisted-state snapshot

Every PostgreSQL integration/fault test must snapshot, before and after:
- Job state, owner, epoch, attempt_count, available_at and version;
- Session state/revision/result reference;
- Nonce ledger row and transaction binding;
- Receipt identity/status/digest/outcome;
- Transition count and immutable rows;
- Outbox count/state/event_id;
- DLQ source state/replay_count/new Job/audit record where applicable.

Tests must assert both allowed changes and forbidden changes. A handler return value alone is insufficient.

## 4. Formal COMMIT fault injection sequencing

Formal COMMIT fault injection is **not executed in this phase**. The current architecture record explicitly blocks it until mandatory predecessor gates pass. Execute FI-02 through FI-07 only after:
1. complete v2alpha2 Handler and UOW exist;
2. G1-G10 contracts and security are accepted;
3. real Receipt Reconcile and fresh-nonce flow exist;
4. test harness can capture complete persisted-state snapshots;
5. Architecture/Security/Database owners authorize the fault campaign.

## 5. Gate conclusion

G11 is **BLOCKED**. Existing helper and legacy tests are useful partial evidence; required v2alpha2 acceptance and fault injection have not passed.
