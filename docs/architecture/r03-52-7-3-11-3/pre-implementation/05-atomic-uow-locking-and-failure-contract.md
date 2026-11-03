# Atomic Unit-of-Work and Locking Design

**Version:** 0.1.0  
**Status:** DESIGN PROPOSAL / NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gates:** G7 OPEN; G8 OPEN; G10 OPEN

## 1. Design objective

For every mutating v2alpha2 action, the durable business result must be all-or-nothing at the caller-owned database transaction boundary. A successful committed action must not exist without its required Receipt, Nonce, Transition, Outbox and optional DLQ records. A failed operation must not leave a partial durable write set.

This document defines candidate invariants and the proof obligations. It does not implement a production UOW or select a production Store/Driver/Pool.

## 2. Candidate write-set inventory

| Action family | Resource writes | Receipt | Nonce | Transition | Outbox | DLQ |
|---|---|---|---|---|---|---|
| Job Complete | Job terminal status; Session revision/result binding (if required by accepted model) | Reserve + finalize | Consume | Append | Append completion event | No |
| Job Fail | Job failure/retry scheduling fields | Reserve + finalize | Consume | Append | Append failure event | Conditional terminal path |
| Job Retry | Job retry state, available_at, lease/owner/attempt fields | Reserve + finalize | Consume | Append | Append retry-scheduled event | No |
| Job Renew | Job lease expiry under owner/epoch fence | Reserve + finalize or explicitly accepted no-receipt policy | Consume | Only if contract requires lease event | Only if contract requires event | No |
| Job Dead Letter | Job terminal state and lease release | Reserve + finalize | Consume | Append | Append terminal event | Insert DLQ item |
| Receipt Reconcile | Receipt lookup / immutable outcome read; any repair write must be separately specified | Read/reconcile | Fresh reconciliation assertion nonce is expected to be consumed in the read transaction; exact read/nonce transaction rule requires approval | No by default | No | No |
| Outbox Dispatch | Outbox dispatch lease/owner/epoch/attempt state | Action receipt only if accepted; otherwise separate dispatch dedup contract | Consume | No Job transition by default | Mutate dispatch state | No |
| Outbox Ack | Outbox acknowledged/dispatched state under dispatch owner/epoch fence | Action receipt only if accepted; otherwise separate ack dedup contract | Consume | No Job transition by default | Update exact event | No |

The exact Job Complete Session mutation and whether Renew/Outbox operations require Receipts or Transitions are unresolved until the authoritative business model and source inventory are reconciled. The table is not a migration specification.

## 3. Transaction boundary

### 3.1 Candidate one-transaction model

One externally visible business operation owns one database transaction:

1. Parse raw assertion and validate request structure outside the transaction where safe.
2. Verify signature, issuer/key validity and version dispatch. These steps may be computationally performed before resource locks, but no durable nonce/Receipt mutation may commit separately.
3. Begin caller-owned transaction.
4. Revalidate any mutable trust/key/revocation state whose freshness is required by the threat model.
5. Lock and validate exact persisted resources and fencing state.
6. Arbitrate Receipt and consume Nonce according to the accepted lock/uniqueness contract.
7. Apply business mutation using the same typed binding used for digest verification.
8. Append Transition, Outbox and optional DLQ rows.
9. Finalize Receipt with the immutable operation outcome.
10. Return to the caller without committing on its behalf.
11. Caller commits once; any error aborts the entire transaction.

The exact placement of Receipt and Nonce relative to Job/Session locks is OPEN until the lock graph and contention behavior are proven. This list is not yet the normative lock order.

### 3.2 Work allowed outside the transaction

- Raw byte parsing, duplicate-key checks and structural schema validation.
- Signature cryptographic verification, provided key-state freshness and revocation race semantics are addressed.
- Pure typed argument construction and digest calculation.
- Network delivery to a broker after commit, using Outbox.
- Logging/metrics that do not claim a durable business outcome.

### 3.3 Work prohibited outside the transaction

- Durable Receipt reservation/finalization.
- Durable Nonce consumption.
- Job/Session mutation.
- Transition/Outbox/DLQ insertion.
- Any external side effect that could be observed as successful before the durable operation commits.

## 4. Error propagation contract

The legacy reference fixture contains operation functions that catch broad exceptions and return NULL/false. A return value alone does not force the outer transaction to roll back earlier caller statements.

Candidate v2alpha2 rule:
- Validation, authorization, fencing, uniqueness, mutation and write-set failures propagate as typed database errors.
- The top-level action entry must not swallow an error and return a success-shaped or ambiguous false/null result while leaving the transaction committable.
- If an API needs a structured failure response, the caller must roll back the transaction before translating the error into a response.
- A terminal business failure that should be persisted as an outcome is not the same as an infrastructure/atomicity failure. Its transaction and Receipt semantics must be explicit.
- Deadlock and serialization failures are retryable only after confirmed rollback; retry preserves the immutable business Request Envelope/idempotency identity but uses a fresh assertion nonce, iat/exp and signature.
- Never automatically retry a non-idempotent external side effect inside the database transaction.

## 5. Candidate lock discipline

The lock order must be derived from the resource graph, not copied mechanically from the Job Complete path.

Candidate lock classes:
- T: tenant/authorization scope or tenant root row, if a persisted row lock is required;
- J: Job;
- S: Session;
- R: Receipt;
- N: Nonce unique key;
- O: Outbox event;
- D: DLQ item;
- A: assignment/dispatcher/replay grant rows.

For each action, document all lock acquisitions and unique-index arbitration points. All multi-resource actions must follow a consistent total order among shared lock classes or prove no wait-for cycle can arise. Unique-key conflicts are lock edges even when no explicit SELECT FOR UPDATE appears in source.

### Required contention cases

- Same Job, different operation IDs, same owner/epoch.
- Same Job, same Receipt identity, same digest.
- Same Job, same Receipt identity, different digest.
- Different Jobs, same tenant/action/idempotency key.
- Same tenant, same operation ID, different idempotency key.
- Job Complete racing Job Renew/Fail/Retry/Dead Letter.
- Session revision update racing two Job Complete requests.
- Outbox Dispatch racing Outbox Ack and lease expiry/reclaim.
- Receipt Reconcile racing a pending or finalizing operation.
- DLQ insertion racing terminal Job transition or replay authorization.
- Same Nonce racing across two independent connections and versions.

## 6. Deadlock and serialization policy

- Deadlocks (SQLSTATE 40P01) and serialization failures (40001) are transaction-level failures; retry only the entire operation after confirmed rollback and with a fresh assertion nonce.
- Use bounded retry with jitter at the application transaction coordinator; the retry count/backoff policy remains a deferred operational decision.
- Do not reduce isolation level to make a race disappear.
- Unique constraints remain authoritative concurrency arbiters.
- On a deadlock/serialization retry, preserve the same immutable business Request Envelope (operation_id, idempotency_key, request_digest and exact typed arguments) but issue a fresh assertion with a fresh nonce, iat/exp and signature after the prior transaction is confirmed rolled back. Never reuse a committed nonce. For ambiguous commit, reconcile first; do not assume rollback.
- A fresh assertion with a consumed nonce is not a valid retry merely because the client reused an idempotency key.
- Capture the database error class and transaction attempt in telemetry without exposing assertion secrets.

## 7. Failure-state snapshot contract

A snapshot is taken before the operation and after rollback/commit from an independent connection. It records:
- Job row and version/status/owner/epoch/lease/attempt fields;
- Session revision and result reference;
- Receipt rows including identity, digest, status and outcome;
- Nonce rows including issuer/kid/nonce/version/operation/digest/transaction binding;
- Transition rows;
- Outbox rows including event identity, event type, payload digest and dispatch fencing state;
- DLQ rows and replay counters;
- relevant key/authorization rows if they are part of the tested race.

For each injected failure, compare primary keys and row contents, not only row counts. Include a transaction ID and operation ID correlation.

## 8. Failure matrix (candidate)

| Failure point | Required durable result |
|---|---|
| Parse/signature/version/auth failure before transaction | No business table changes |
| Resource missing / tenant mismatch / owner or epoch mismatch | No Receipt, Nonce or business writes committed |
| Session revision conflict | No partial Job/Receipt/Nonce/Transition/Outbox changes |
| Receipt same-key/same-digest business retry under a fresh assertion nonce | Consume the fresh nonce and return stored terminal result; no second business mutation |
| Receipt same-key/different-digest | Conflict; no business write |
| Operation ID conflict | Conflict; no business write |
| Exact old assertion/nonce replay | Reject as `ASSERTION_REPLAYED`; Receipt lookup cannot override committed nonce collision |
| Job mutation failure | Entire write set absent after rollback |
| Transition insert failure | Job/Receipt/Nonce/Outbox/DLQ changes absent after rollback |
| Outbox insert failure | Job/Receipt/Nonce/Transition/DLQ changes absent after rollback |
| DLQ insert failure | Job/Receipt/Nonce/Transition/Outbox changes absent after rollback |
| Receipt finalization failure | All business writes absent after rollback |
| Deadlock / serialization failure | Entire attempt rolled back; bounded full-transaction retry only |
| Outer caller rollback | All durable rows from the action absent |
| Commit outcome ambiguous | Issue a fresh reconciliation assertion/nonce, reconcile by stable business operation identity and digest; never reuse the old nonce or blindly repeat mutation |

The final matrix must specify whether a business rejection is represented as a committed terminal Receipt or a rolled-back operation. The current helper code does not decide that.

## 9. Non-goals

- No production UOW implementation.
- No production adapter, pool or isolation-level selection.
- No broker delivery in the database transaction.
- No formal R03.52.7.3.11.4 COMMIT fault injection in this phase.
- No change to legacy handler semantics.

## 10. Gate conclusion

G7, G8 and G10 remain OPEN. This document establishes candidate invariants and proof obligations only. The lock graph, per-action write set and persisted-state acceptance contract require further source reconciliation and independent review.

## Change history

- 2026-11-03: Initial candidate UOW and locking design.
