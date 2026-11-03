# Action-Specific Typed Binding and Handler Contract Matrix

**Version:** 0.1.0  
**Status:** DESIGN PROPOSAL / NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gate:** G4 OPEN; G12/G13 OPEN

## 1. Binding invariants

For every action:
1. Claim-authenticated identity fields are read only from the verified Claim.
2. The handler validates action/resource type using a closed mapping before mutation.
3. Resource ID is bound to the exact persisted row selected and locked.
4. Tenant, Job, Session, Owner, Epoch and Subject are rechecked against persisted relationships inside the transaction.
5. Expected revision and idempotency identity are validated before state mutation.
6. One typed operation binding supplies both digest arguments and mutation parameters.
7. Every mutation is fenced by the verified owner/epoch/revision where applicable.
8. Receipt, Nonce and business writes follow the accepted single-transaction contract.
9. Error mapping is deterministic; no broad catch-and-return behavior may hide partial writes.
10. A client retry uses the same immutable business Request Envelope/digest under a fresh assertion nonce; Receipt may return the stored outcome without repeating side effects. Exact old signed assertion replay after committed nonce use is rejected as `ASSERTION_REPLAYED`.

## 2. Candidate action contract matrix

| Action | Resource | Digest arguments observed in PR #15/#20 | Persisted identity/fence to recheck | Candidate writes | Distinct acceptance concerns |
|---|---|---|---|---|---|
| `worker.job.complete` | `job / job_id` | `expected_session_revision`, `result_ref` | tenant, job_id, session_id, subject/owner, epoch, running status, DB-clock lease, Session revision | Job terminal state; Session revision/result binding if confirmed; Receipt; Nonce; Transition; Outbox | Session optimistic concurrency; result_ref validation; duplicate completion |
| `worker.job.fail` | `job / job_id` | `error_code`, `retryable`, `retry_delay_micros`, `safe_message` | same Job fence and state; retry policy/attempt ceiling | Job failure/retry fields; Receipt; Nonce; Transition; Outbox; conditional DLQ | Distinguish retryable failure from terminal failure; safe message persistence |
| `worker.job.retry` | `job / job_id` | `delay_seconds`, `error_code` | tenant/job/session/owner/epoch/status/lease and attempt ceiling | Job available_at/lease/attempt/error; Receipt; Nonce; Transition; Outbox | DB-clock scheduling; bounded delay; attempt ceiling |
| `worker.job.renew` | `job / job_id` | `lease_seconds` | owner, epoch, running status, current lease and DB clock | Job lease expiry; Receipt/Nonce according to accepted action policy; Transition/Outbox only if specified | Lease extension cap; stale worker fencing; no silent resurrection |
| `worker.job.dead_letter` | `job / job_id` | `error_code`, `terminal_reason` | owner/epoch/status/attempt ceiling and exact Job/DLQ relation | Job terminal state; DLQ item; Receipt; Nonce; Transition; Outbox | DLQ unique identity; terminal idempotency; replay counter unaffected |
| `worker.receipt.reconcile` | `receipt / operation_id` | empty object | tenant/action/operation_id and stored receipt identity/digest/resource | Receipt read; any repair/update must be explicitly specified; Nonce behavior separately decided | Must not invent success from missing/ambiguous receipt; pending recovery semantics |
| `worker.outbox.dispatch` | `outbox_event / event_id` | `lease_seconds` | exact tenant/event, dispatcher identity, dispatch epoch, state, DB-clock lease | Outbox dispatch owner/epoch/lease/attempt fields; Nonce; Receipt policy TBD | At-least-once delivery; broker I/O after commit; event ordering |
| `worker.outbox.ack` | `outbox_event / event_id` | empty object | exact tenant/event, dispatcher owner/epoch/lease and delivery state | Outbox acknowledged/dispatched fields; Nonce; Receipt policy TBD | Duplicate ack; stale dispatcher fencing; no ack for another event |

The v2alpha2 digest helper also maps `worker.dlq.replay` to `dlq_item`. This action is not in the eight-action scope above and remains separately deferred until an explicit scope decision.

## 3. Claim-to-row binding requirements

| Claim field | Required transaction check |
|---|---|
| `iss`, `kid` | Active trusted issuer/key record; key state and revocation freshness per G3 |
| `tenant_id` | Exact tenant scope of locked resource and all dependent rows |
| `sub` | Authenticated subject/worker identity; owner binding policy |
| `aud` | Exact worker-store audience accepted by this service |
| `action` | Closed action registry; must match invoked handler |
| `job_id` | Exact locked Job for Job actions; not accepted as a caller override |
| `session_id` | Job-to-Session relationship and tenant composite key |
| `owner` | Current persisted Job owner/worker principal |
| `epoch` | Current persisted fencing epoch; stale epoch rejects |
| `resource_type` | Closed mapping from action to resource type |
| `resource_id` | Exact resource row ID; for Job actions must equal job_id; for Receipt reconcile must equal operation_id |
| `operation_id` | Signed immutable operation identity; stable across retries of the same request |
| `idempotency_key` | Signed immutable idempotency scope; never client-substituted after verification |
| `request_digest` | Recomputed from the same typed binding used by the mutation |
| `nonce` | Unique replay token consumed in the same transaction under accepted cross-version policy |

## 4. Error taxonomy candidate

| Condition | Candidate stable code | Retry guidance |
|---|---|---|
| Malformed assertion / unknown version | `ASSERTION_INVALID` / `ASSERTION_VERSION_UNSUPPORTED` | Do not retry unchanged |
| Invalid signature / unknown or revoked key | `ASSERTION_UNTRUSTED` | Do not retry unchanged; key state may change |
| Digest/argument mismatch | `REQUEST_DIGEST_MISMATCH` | Do not retry; caller must re-sign correct operation |
| Action/resource mismatch | `ACTION_RESOURCE_MISMATCH` | Do not retry unchanged |
| Tenant/subject/owner mismatch | `RESOURCE_FORBIDDEN` | Do not retry unchanged |
| Stale epoch/lease | `FENCE_REJECTED` | Refresh work claim; do not replay stale assertion |
| Session revision conflict | `SESSION_REVISION_CONFLICT` | Reload/recompute; new signed operation |
| Same idempotency key, different digest | `IDEMPOTENCY_CONFLICT` | Do not retry unchanged |
| Operation ID collision | `OPERATION_ID_CONFLICT` | New operation identity only for a genuinely new operation |
| Nonce already consumed | `ASSERTION_REPLAYED` | Exact old assertion is rejected; a client retry must use a fresh nonce and may then resolve through Receipt without repeating business mutation |
| Deadlock / serialization failure | Database retryable transaction class | After confirmed rollback, retry whole transaction with the same immutable business Request Envelope/digest but a fresh assertion nonce, iat/exp and signature |
| Internal write-set failure | `UOW_ABORTED` | Roll back entire transaction; operator diagnostics |

This table is a candidate mapping. It must be reconciled with the repository's existing error catalog and transport contract before acceptance.

## 5. Action-specific open questions

### Complete
- Is Session revision increment and result_ref persisted in Session, Job, or both?
- Is the terminal Job state and Session revision update one atomic state transition?
- Is duplicate completion with same digest always replay, even after subsequent Session changes?

### Fail / Retry
- Does Fail itself choose retry scheduling or does it only record failure and delegate to Retry?
- Are retry_delay_micros and delay_seconds intentionally distinct units/contracts?
- What is the canonical mapping from error_code to retryability and attempt ceiling?

### Renew
- Does a lease renewal create a Receipt and consume a one-time assertion nonce?
- Is a Transition or Outbox event required for each renewal, or is it intentionally silent?
- How is renewal idempotency defined if repeated request arrives after the lease expiry time has advanced?

### Dead Letter
- Is the DLQ row identity derived from operation_id, Job+epoch, or a dedicated immutable ID?
- Is exactly one DLQ row permitted per terminal Job epoch?
- What are the immutable payload fields required for audit and replay?

### Receipt Reconcile
- Does reconcile only read and return the stored terminal result, or may it repair an incomplete state?
- If it may repair, which tables may be mutated and under what proof?
- What happens for a committed pending Receipt?

### Outbox Dispatch / Ack
- Does dispatch reserve a Receipt or use event-level delivery identity?
- Is dispatch at-least-once and how does the consumer inbox deduplicate by event ID?
- What is the event ordering key and does the database guarantee it?
- Is Ack a durable state transition or a deletion/retention marker?

## 6. Required test matrix

For each action, tests must include:
- valid claim and correct action/resource;
- wrong action, resource type, resource ID and tenant;
- wrong subject/owner/session/epoch;
- changed operation arguments after digest calculation;
- missing, null, extra and wrong-type arguments;
- same signed request replay;
- same idempotency key with different digest;
- operation ID conflict;
- nonce replay and cross-version replay;
- concurrent same-resource mutation;
- concurrent competing epoch/revision;
- each write-set failure with persisted-state snapshot;
- outer transaction rollback;
- least-privilege Runtime role execution and direct-table-write denial.

## 7. Gate conclusion

G4, G12 and G13 remain OPEN. This matrix is an implementation-preparation contract candidate; it does not authorize handler implementation and does not settle the open questions listed above.

## Change history

- 2026-11-03: Initial action binding matrix based on PR #15 digest schema and PR #20 source audit.
