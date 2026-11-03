# Remaining Worker Action Pre-Implementation Designs

**Version:** 0.1.0  
**Status:** DESIGN PROPOSAL / NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gate:** G13 OPEN

## 1. Common template

All remaining actions reuse only the proven mechanisms from the Complete slice:
- strict raw assertion parsing and exact-byte signature verification;
- fail-closed version dispatch;
- verified Claim identity and action/resource closed mapping;
- one typed binding for digest and mutation;
- persisted tenant/owner/epoch/resource revalidation;
- Receipt/Nonce semantics where the action contract requires them;
- transaction ownership, typed error propagation and persisted-state proof;
- role/RLS and catalog assertions.

No generic abstraction is approved until the Complete slice demonstrates it is necessary.

## 2. worker.job.fail

**Resource:** `job / job_id`  
**Candidate digest args:** `error_code`, `retryable`, `retry_delay_micros`, `safe_message`.

Candidate preconditions:
- exact tenant/job/session;
- owner and epoch match;
- Job remains running and lease is valid under DB clock;
- attempt count and retry policy version are read from persisted state;
- error_code is from a closed error catalog;
- retryable, delay and safe_message are derived by the trusted versioned Retry Policy Registry, not caller-authoritative inputs;
- the exact policy result and version are bound to the digest and the SQL mutation through one typed binding.

Candidate outcomes:
- retryable failure schedules a retry and releases/updates lease under the accepted policy;
- non-retryable or exhausted failure moves to terminal failed/dead-letter path only as explicitly defined;
- append one Transition and one Outbox event for the actual state transition;
- insert DLQ only if the terminal reason/policy requires it.

Open: whether Fail and Retry are one atomic action or separate commands; which trusted component evaluates/pins the Retry Policy Registry; how `retry_delay_micros` maps to persisted scheduling; global/per-code delay bounds; whether a terminal failed state always creates a DLQ row.

## 3. worker.job.retry

**Resource:** `job / job_id`  
**Candidate digest args:** `delay_seconds`, `error_code`.

Candidate preconditions:
- exact owner/epoch/lease fence;
- Job is in a retry-eligible state;
- maximum attempts not exceeded;
- delay within accepted bounds;
- retry policy and error_code agree;
- delay is derived from the same pinned trusted policy and persisted attempt budget, not accepted as an arbitrary caller override.

Candidate writes:
- set retry/queued state according to accepted lifecycle;
- set `available_at` using database clock, not client clock;
- clear/advance lease fields as defined;
- update attempt count exactly once;
- append Transition and Outbox event;
- Receipt and Nonce in same transaction if required by action policy.

Open: whether attempt_count increments at retry scheduling or next claim; exact delay unit and rounding; retry event payload/version; policy version pinning and Fail/Retry policy-decision consistency.

## 4. worker.job.renew

**Resource:** `job / job_id`  
**Candidate digest args:** `lease_seconds`.

Candidate preconditions:
- owner/epoch match;
- Job is running and lease has not expired, unless explicit grace policy exists;
- lease_seconds within bounded range;
- database clock determines new expiry.

Candidate writes:
- update lease expiry only under exact owner/epoch/status fence;
- do not change owner or epoch;
- no Session mutation;
- Transition/Outbox emission is unresolved and must not be added by default;
- Receipt/Nonce semantics must be explicit because repeated renewal changes lease state.

Open: renewal idempotency if the same request is retried after the first commit; whether a same-request Receipt returns original expiry rather than extending lease again; lease boundary semantics at exact expiry.

## 5. worker.job.dead_letter

**Resource:** `job / job_id`  
**Candidate digest args:** `error_code`, `terminal_reason`.

Candidate preconditions:
- exact owner/epoch and current Job state;
- terminal reason is from a closed enum;
- retry exhaustion/non-retryable predicate is re-evaluated against persisted state;
- DLQ insertion is unique for the relevant Job/epoch/terminal operation.

Candidate writes:
- Job transitions to dead_lettered;
- clear lease/owner under terminal-state policy;
- insert immutable DLQ item;
- append Transition and Outbox;
- Receipt/Nonce in same transaction.

Open: DLQ identity strategy, immutable source snapshot fields, whether a repeated terminal assertion returns existing DLQ identity, and how later replay links a new Job to the source DLQ item.

## 6. worker.receipt.reconcile

**Resource:** `receipt / operation_id`  
**Candidate digest args:** empty object.

Candidate behavior:
- authenticate signed operation identity and tenant;
- lookup exact Receipt by tenant + operation_id and verify action/resource/digest;
- return stored outcome only if terminal and internally consistent;
- pending, missing, duplicate or inconsistent state must return a typed non-success result.

Open: whether reconcile is strictly read-only or has repair authority. If repair is permitted, define the exact source-of-truth for every table and an auditable repair transition. Do not infer business success from a Receipt alone if required Job/Transition/Outbox rows are absent. Reconcile must not rewrite a digest or silently manufacture a terminal outcome.

## 7. worker.outbox.dispatch

**Resource:** `outbox_event / event_id`  
**Candidate digest args:** `lease_seconds`.

Candidate preconditions:
- dedicated dispatcher principal and persisted dispatcher authorization;
- exact event/tenant identity;
- event eligible for dispatch;
- DB-clock lease and dispatch epoch fencing;
- bounded lease_seconds.

Candidate writes:
- claim exact event, set dispatch owner/epoch/lease and increment attempts;
- no Job mutation;
- durable dispatch claim commits before network delivery;
- external broker publish occurs after commit;
- at-least-once delivery is expected; consumer deduplication by event ID is required.

Open: ordering key, expired lease reclaim, retry backoff, poison-event handling and dispatch receipt/dedup strategy.

## 8. worker.outbox.ack

**Resource:** `outbox_event / event_id`  
**Candidate digest args:** empty object.

Candidate preconditions:
- exact dispatcher principal;
- event currently leased to that dispatcher;
- dispatch epoch matches;
- lease/fencing policy accepts acknowledgement.

Candidate writes:
- mark exact event dispatched/acknowledged or set immutable delivery marker;
- reject stale dispatcher and wrong event;
- duplicate ack semantics must be deterministic;
- no Job state transition by default.

Open: whether ack means broker accepted, consumer processed, or downstream business effect committed. These are different semantics and must not be conflated. If consumer processing is involved, an Inbox record is required at the consumer boundary.

## 9. Shared action differences

| Concern | Job Fail/Retry/Renew/Dead Letter | Receipt Reconcile | Outbox Dispatch/Ack |
|---|---|---|---|
| Primary lock | Job, sometimes Session | Receipt | Outbox event |
| Fencing | Job owner + epoch + lease | Operation/digest/tenant identity | Dispatcher owner + dispatch epoch + lease |
| Session lock | Only where business contract requires | No by default | No |
| Transition | State changes only | No by default | No Job transition |
| Outbox | Event for Job transition | No by default | The Outbox row itself |
| DLQ | Dead Letter and conditional Fail | No | Poison event policy separate |
| External I/O | None in DB tx | None | Publish only after dispatch claim commit |
| Replay | Receipt + nonce | Read existing outcome | Event delivery dedup + stale ack fencing |

## 10. Cross-action concurrency matrix

- Complete vs Fail: only one may win the current Job fence; loser has no partial write set.
- Complete vs Renew: stale epoch/lease/revision cannot overwrite terminal completion.
- Fail vs Retry: one operation identity and one state transition; no double attempt increment.
- Retry vs Dead Letter: attempt ceiling and terminal reason are checked under the same locked Job row.
- Dead Letter vs Replay: DLQ item becomes replayable only after terminal state and grant/limit checks.
- Receipt Reconcile vs in-flight action: pending/terminal visibility follows documented transaction semantics; no phantom success.
- Dispatch vs Ack: ack requires the exact active dispatch epoch/owner; stale dispatchers cannot ack reclaimed events.
- Dispatch vs lease reclaim: only one current dispatch lease wins; delivery remains at-least-once.
- Cross-version same nonce: no action path bypasses the shared anti-replay policy.

## 11. Gate conclusion

G13 remains OPEN. The action deltas and test concerns are inventoried, but exact state transitions, persisted fields, Receipt policy, Nonce semantics, lock graph and error contracts require authoritative domain/source reconciliation and approval.

## Change history

- 2026-11-03: Initial remaining-action design inventory.
