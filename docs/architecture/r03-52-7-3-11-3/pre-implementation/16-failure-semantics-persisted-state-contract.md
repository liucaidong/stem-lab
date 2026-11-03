# Failure Semantics and Persisted-State Acceptance Contract

**Version:** 0.1.0  
**Status:** ACCEPTANCE CONTRACT CANDIDATE / NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gates:** G10 OPEN; R03.52.7.3.11.4 BLOCKED

## 1. Purpose and hard boundary

This document defines expected durable database outcomes for failure classes before any formal COMMIT Fault Injection. It is a test contract candidate only.

**No formal R03.52.7.3.11.4 fault injection is authorized by this document.** Do not inject failures at PostgreSQL COMMIT or simulate ambiguous commit in the production-shaped workflow until G0–G14 are accepted.

## 2. State snapshot schema

A test snapshot must capture, before and after the operation, exact rows and relevant columns for:
- Job: tenant/job/session, status, owner, epoch, lease expiry, attempt count, available_at, error fields, result reference and revision if present.
- Session: tenant/session, revision, result binding and updated timestamp.
- Receipt: receipt ID, tenant/action/idempotency key, operation ID, request digest, resource type/id, status, outcome and timestamps.
- Nonce: issuer, kid, nonce, assertion version, tenant/subject, action/resource, operation ID, request digest and transaction binding.
- Transition: tenant/transition ID, job/session, operation ID, from/to state and event payload/version.
- Outbox: tenant/event ID, job/session, operation ID, event type, payload digest, dispatch state/owner/epoch/lease/attempts.
- DLQ: tenant/DLQ ID, source Job/session/epoch, terminal reason, error code, attempt count, replay count and immutable source payload.
- Relevant issuer/key registry row when testing key state/revocation races.

Compare primary-key sets and exact row values, not only counts. Read after-state through an independent connection after the transaction outcome is known.

## 3. Failure-to-persisted-state matrix

| Failure class | Expected response | Job / Session | Receipt | Nonce | Transition / Outbox / DLQ |
|---|---|---|---|---|---|
| Assertion Parsing Failure | Reject malformed UTF-8/JSON/duplicate/unknown fields | Unchanged | No new row | No new row | Unchanged |
| Signature Failure | Reject invalid Ed25519 signature | Unchanged | No new row | No new row | Unchanged |
| Version Dispatch Failure | Reject unknown/mixed/downgrade family; no fallback | Unchanged | No new row | No new row | Unchanged |
| Authorization Failure | Reject tenant/subject/action/resource mismatch | Unchanged | No new row | No new row | Unchanged |
| Resource Lock Failure | Return typed missing/lock/timeout/fence failure | Unchanged | No new row or rolled back | No new row or rolled back | Unchanged |
| Session Revision Conflict | Return revision conflict | Unchanged | No new row or rolled back | No new row or rolled back | Unchanged |
| Receipt Reservation — same key/same digest terminal | Return stored outcome; no mutation | Unchanged | Existing terminal row unchanged | No fresh nonce consumption for a replay path unless explicit contract requires a read-only audit record | Unchanged |
| Receipt Reservation — same key/different digest | IDEMPOTENCY_CONFLICT | Unchanged | Existing Receipt unchanged | No new nonce | Unchanged |
| Receipt Reservation — operation ID conflict | OPERATION_ID_CONFLICT | Unchanged | Existing Receipt unchanged | No new nonce | Unchanged |
| Nonce Replay | ASSERTION_REPLAYED or exact Receipt replay | Unchanged | Existing Receipt unchanged | Existing nonce row unchanged | Unchanged |
| Job Mutation Failure | UOW_ABORTED; outer transaction rolled back | Job/Session changes absent | New Receipt reservation absent or unchanged existing Receipt | New nonce absent | All inserts absent |
| Transition Insert Failure | UOW_ABORTED; outer transaction rolled back | Job/Session changes absent | New Receipt reservation/finalization absent | New nonce absent | Transition/Outbox/DLQ inserts absent |
| Outbox Insert Failure | UOW_ABORTED; outer transaction rolled back | Job/Session changes absent | New Receipt reservation/finalization absent | New nonce absent | Transition/Outbox/DLQ inserts absent |
| DLQ Insert Failure | UOW_ABORTED; outer transaction rolled back | Job terminal mutation absent | New Receipt absent | New nonce absent | Transition/Outbox/DLQ inserts absent |
| Receipt Finalization Failure | UOW_ABORTED; outer transaction rolled back | Job/Session changes absent | New pending Receipt absent after rollback | New nonce absent | Transition/Outbox/DLQ inserts absent |
| Commit Failure — definitive server abort | Transaction abort reported | All action changes absent | New Receipt absent | New nonce absent | All inserts absent |
| Commit Outcome Ambiguous (connection lost) | Client must reconcile by same operation identity; no blind fresh mutation | Either all action changes committed or none; never partial | Terminal Receipt exists iff whole transaction committed | Nonce exists iff whole transaction committed | Transition/Outbox/DLQ exist iff whole transaction committed |
| Deadlock (40P01) | Transaction abort; retry whole transaction only | No attempt writes committed | No attempt Receipt committed | No attempt nonce committed | No attempt inserts committed |
| Serialization Failure (40001) | Transaction abort; retry whole transaction only | No attempt writes committed | No attempt Receipt committed | No attempt nonce committed | No attempt inserts committed |
| Outer Transaction Rollback | Caller rolls back | All action changes absent | New Receipt absent | New nonce absent | All inserts absent |

The same-request terminal Receipt replay is a no-op with respect to business mutation. It must not re-run Job or Session state transitions.

## 4. Commit ambiguity semantics

A transport failure after sending COMMIT is not proof of rollback. The client must not:
- assume the transaction failed;
- issue a fresh operation ID for the same logical request;
- reuse a consumed nonce in a new mutation path;
- blindly execute the business mutation again.

Instead, the caller retries/reconciles with the same signed operation identity and idempotency key. The service returns the stored terminal outcome if the transaction committed; if it did not commit, the retry follows the accepted nonce/retry policy and executes at most once.

The exact recovery rule depends on the final Receipt/Nonce model and must be proven before COMMIT fault injection.

## 5. Required snapshot assertions

For each failure case:
1. Snapshot all listed tables before execution.
2. Execute one operation with a unique operation ID and controlled failure point.
3. Ensure the caller transaction is committed or rolled back exactly as the case requires.
4. Wait for the database response/connection state to settle.
5. Query from a separate connection.
6. Compare exact rows and relevant values.
7. Verify no out-of-scope tenant/resource row changed.
8. Verify no external broker call occurred before commit.
9. Verify a retry with the same operation identity returns the correct outcome without duplicate effects.

## 6. Business rejection versus infrastructure failure

Do not conflate:
- **Business rejection:** a valid request that cannot transition state (for example stale epoch or Session revision conflict). The API may return a stable rejection; whether a failed Receipt is committed is an explicit action contract decision.
- **Idempotent replay:** an exact same signed request whose Receipt already has a terminal outcome; return stored outcome without mutation.
- **Infrastructure/write-set failure:** database/constraint/serialization/insert/finalization failure; abort the whole transaction.
- **Ambiguous commit:** client does not know the outcome; reconcile by immutable operation identity.

A failed Receipt must not be used to conceal a partial Job/Outbox write set.

## 7. Tests that must not run in this phase

The following are reserved for R03.52.7.3.11.4 after G0–G14 acceptance:
- process termination during COMMIT;
- socket close after sending COMMIT;
- proxy dropping COMMIT response;
- server crash/restart at commit boundary;
- broken pooled connection during transaction completion;
- formal database crash/recovery and WAL durability experiments.

Current phase may write test specifications and static assertions only.

## 8. Gate conclusion

G10 remains OPEN. This contract defines expected durable outcomes, but no complete integrated Handler/UOW state snapshot suite exists. R03.52.7.3.11.4 remains BLOCKED.

## Change history

- 2026-11-03: Initial failure/persisted-state acceptance contract candidate.
