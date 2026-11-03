# R03.52.7.3.11.7 — v2alpha2 Worker Failure Handler & Atomic UoW Design

**Status:** REFERENCE DESIGN / IMPLEMENTATION NOT STARTED  
**Parent:** PR #23 — R03.52.7.3.11.6 Atomic Business Handler & UoW  
**Product Code Freeze:** ACTIVE  
**Production readiness:** NOT READY

## 1. Objective and scope

Add the first failure-path v2alpha2 business handler, `worker.job.fail`, using the existing Worker Store contract. This action is the Worker Runtime's single failure-reporting operation: it persists a retry decision or terminal dead-letter result from the trusted retry-policy decision.

The signed operation arguments are exactly:

- `error_code`
- `retryable`
- `retry_delay_micros`
- `retry_policy_version`
- `safe_message`

The Request Digest must be recomputed from the exact typed values used by the mutation. The Job's persisted `attempt_count` and `maximum_attempts` remain authoritative; the signed decision cannot extend the persisted attempt budget.

## 2. Failure decision matrix

| Signed decision | Persisted attempt budget | Required result | Job transition |
|---|---|---|---|
| `retryable=true` | `attempt_count < maximum_attempts` | Schedule retry at DB clock + signed delay | `running → retry` |
| `retryable=false` | Any valid current attempt | Create terminal DLQ item, reason `non_retryable` | `running → dead_lettered` |
| `retryable=true` | `attempt_count >= maximum_attempts` | Create terminal DLQ item, reason `max_attempts` | `running → dead_lettered` |

A non-retryable decision must carry `retry_delay_micros=0`. Retryable delay is an integer in `[0, 86,400,000,000]` microseconds. The DB clock, not the Worker clock, determines `available_at`.

The issuer-signed `retry_policy_version` records which policy produced the decision. The reference database can verify that the signed version and arguments were not changed; it cannot prove that the issuer applied the correct policy unless the production policy publication/trust chain is separately implemented.

## 3. Atomic transaction boundary

Use the same v2alpha2 lock order as PR #23:

1. Verify raw Claim, Ed25519 signature, issuer/key status, action/resource binding and Request Digest.
2. Overwrite transaction-local tenant context from the verified Claim.
3. Insert the Nonce Ledger row under `(tenant_id, issuer, nonce)`; exact nonce replay fails here.
4. Reserve/lock Receipt under `(tenant_id, action, idempotency_key)`; compare operation ID, resource identity and digest.
5. Lock the exact Job row `FOR UPDATE`; verify tenant, job, session, owner, epoch, `running` state and `lease_expires_at > clock_timestamp()`.
6. Read persisted attempt counters and derive the effective terminal/retry branch.
7. Update Job fields and clear owner/lease. If terminal, insert the DLQ item. Increment Job revision and append one Job Transition and one Job Outbox event.
8. Finalize the Receipt with the immutable typed outcome.
9. Return from the one PostgreSQL entry point; the caller commits the transaction.

The failure handler does not mutate Session state or revision. It must use the persisted Job→Session relationship and composite tenant/job/session foreign keys for child rows. It increments the locked Job revision and writes Job-specific history/outbox rows; it does not lock Session.

## 4.1 Blocking aggregate-sequence contract

The existing R03.50 reference schema makes `transitions.sequence` and `outbox.sequence` unique per `(tenant_id, session_id)`, with child rows tied to Session. The proposed failure Handler changes Job state but does not change Session status or revision. Therefore it cannot safely invent `session.revision + 1`, reuse an existing Session sequence, or write a no-op Session transition merely to satisfy the current schema.

The legacy R03.52.7.3.6 disposable authorization fixture uses a different Transition/Outbox shape (Job-rooted rows without the R03.50 Session revision sequence). It is not proof that the R03.50 production-facing schema supports Job lifecycle events.

**This is an implementation blocker.** Before coding the failure handler, select and document one aggregate event model:

- **Option A — Job-specific ledgers:** add append-only `job_transitions` and a Job-scoped Outbox table keyed by tenant/job/sequence; the relay consumes both Session and Job outboxes.
- **Option B — Aggregate-aware shared Outbox:** extend Outbox with explicit aggregate type/ID/sequence and tenant-aware FK/uniqueness rules, while retaining Session Transition for Session state changes and adding a Job Transition ledger.
- **Option C — Session lifecycle coupling:** define a real Session state/revision transition for a Job failure. Use only if the domain state machine explicitly requires Session status to change; do not invent a same-state transition to allocate a sequence.

**Reference implementation decision: select Option A for the next increment.** This preserves the existing R03.50 Session Transition/Outbox sequence contract and introduces a distinct Job aggregate event stream without pretending that a Job-only failure mutates Session state. This is a reference-schema decision only; production migration and relay approval remain under DEC-30.

Option A requires:
- Add `ingestion_jobs.revision` as a bounded monotonic Job aggregate revision, incremented under the locked Job row for each Job state transition.
- Add append-only `job_transitions`, unique by `(tenant_id, job_id, sequence)`, with composite tenant/job/session binding and immutable command/digest/actor fields.
- Add tenant-scoped `job_outbox`, unique by `(tenant_id, job_id, sequence)` and `(tenant_id, event_id)`, carrying the Job's Session ID as context. It is a transactional outbox only; no relay is included.
- Use the new Job revision as the sequence for both Job Transition and Job Outbox rows. Keep the existing R03.50 Session Transition/Outbox tables and Session revision unchanged for Job-only failures.
- Extend the PR #23 Complete handler to append a Job Transition/Job Outbox row for `running → succeeded` in addition to its existing Session transition/outbox writes. The Failure handler appends only Job aggregate rows.
- Apply ENABLE + FORCE RLS, composite FKs and runtime no-direct-table-access to both new tables.

Option B remains the future consolidation candidate if DEC-30 approves a shared aggregate-aware Outbox. Option C is rejected for this increment because a no-op or invented Session state transition would corrupt Session revision semantics.

The failure Handler cannot be marked READY until the Job revision, Job Transition and Job Outbox schema, FK/tenant isolation, event IDs and rollback/concurrency tests are implemented. The 11-point fault matrix must include Job sequence allocation races and rollback of Job event/Transition with the Job update.

## 4. Persisted writes

### Retry scheduled

- Job: `status='retry'`, `available_at=clock_timestamp()+delay`, error code/safe message/policy version stored, `lease_owner=NULL`, `lease_expires_at=NULL`.
- Job Transition: `running → retry`, keyed by operation ID and Job revision.
- Job Outbox: stable event ID, type `job.retry_scheduled`, sequence equal to the new Job revision.
- Receipt: `succeeded` with outcome `RETRY_SCHEDULED`, next availability and attempt counters.

### Dead-lettered

- Job: `status='dead_lettered'`, error code/safe message/policy version stored, `lease_owner=NULL`, `lease_expires_at=NULL`.
- DLQ: one row per tenant/job, exact terminal reason, error code, safe message, persisted attempt count and lease epoch.
- Job Transition: `running → dead_lettered`, keyed by operation ID and Job revision.
- Job Outbox: stable event ID, type `job.dead_lettered`, sequence equal to the new Job revision.
- Receipt: `succeeded` with outcome `DEAD_LETTERED`, terminal reason and DLQ identity.

A unique conflict or any failure in any write must abort the whole transaction, including Nonce and Receipt reservation. No false/null return may be interpreted as a successful commit.

## 5. Idempotency and concurrency

- Exact signed nonce replay: reject before Receipt arbitration.
- Same operation/idempotency/digest with a fresh nonce: return the stored terminal Receipt; do not mutate Job, DLQ, Transition or Outbox again.
- Same idempotency key with a different digest, operation ID or resource: `IDEMPOTENCY_CONFLICT`; no business write.
- Concurrent same-key requests: Receipt unique key is the serialization point; exactly one transaction may perform the state transition.
- Stale owner, epoch, status or expired lease: reject and roll back Nonce/Receipt reservation.
- Attempt exhaustion: derive terminal `max_attempts` from the locked Job row, never from caller-supplied counters.

## 6. Required PostgreSQL fault-injection matrix

1. Fail immediately after Nonce insertion.
2. Fail after Receipt reservation.
3. Fail after Job update.
4. Fail after DLQ insertion on the terminal branch.
5. Fail after Transition insertion.
6. Fail after Outbox insertion.
7. Fail during Receipt finalization.
8. Simulate a lost COMMIT acknowledgement after server commit; reconcile with a fresh assertion.
9. Race two fresh-nonce requests with the same Receipt identity.
10. Race a stale lease/epoch update against the failure handler.
11. Verify persisted snapshots for Job, Nonce, Receipt, DLQ, Transition and Outbox after every injected failure.

Each rollback test must compare persisted rows, not merely assert that an exception was raised.

## 7. Action scope decisions

- `worker.job.fail` is the Worker Runtime's retry-or-dead-letter decision path and matches `FailJobCommand` / `StoreOutcome.RETRY_SCHEDULED|DEAD_LETTERED`.
- `worker.job.retry` is not part of the current `WorkerStoreFacade` contract. Keep it non-executable until a separate operator/scheduler principal, source state, authorization policy and idempotency semantics are defined.
- `worker.job.dead_letter` is likewise not a second Worker failure route. If retained, it must be a separately authorized administrative operation; it must not bypass the persisted attempt/decision path.
- DLQ Replay remains excluded from v2alpha2 execution until trusted replay provenance and its atomic new-Job UoW are approved.
- Outbox dispatch/ack remain a separate dispatcher capability and lock graph.

No generic handler fallback is permitted for reserved actions.

## 8. Implementation prerequisites and non-goals

Before code:
- Confirm the exact Job/DLQ/Transition/Outbox schema columns and constraints against R03.51 reference DDL.
- Add a bounded persisted `retry_policy_version` field to Job if absent; no caller-supplied attempt count may enter the SQL API.
- Resolve the blocking Job-vs-Session Transition/Outbox aggregate sequence model in Section 4.1 before writing SQL.
- Ensure the trusted issuer binds `retry_policy_version`, retryability, delay and safe message into the signed assertion digest.
- Add a typed `FailJobCommand` adapter path using one connection and one transaction.
- Preserve the PR #23 runtime/function-owner privilege model and helper EXECUTE allowlist.

This increment does not implement Renew, explicit operator Retry/Dead-letter, Outbox Relay, consumer deduplication, DLQ Replay, production migration, production signer/key custody or operational policy rollout. Product Code Freeze remains ACTIVE.
