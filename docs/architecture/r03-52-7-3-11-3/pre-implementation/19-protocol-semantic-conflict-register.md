# Protocol and Idempotency Semantic Conflict Register

**Version:** 0.1.0  
**Status:** OPEN / SOURCE-DERIVED  
**As-of:** 2026-11-03  
**Gates:** G1, G4, G5, G6 OPEN

## 1. Purpose

This register records inconsistencies or underspecified semantics across PR #15 candidate contracts, the v2alpha2 codec, Receipt helper and legacy Store contracts. These are not resolved by selecting whichever source is newest; the protocol owner must approve the normative rule.

## 2. Conflicts and required resolution

| ID | Source observation | Conflict / ambiguity | Required resolution |
|---|---|---|---|
| SEM-01 | Request Envelope includes `idempotency_key` and `operation_id` in the digest. PR #15 Receipt section says “different idempotency key + same digest” is a distinct operation identity and may execute. | With collision-resistant digest over both fields, changing idempotency_key necessarily changes canonical bytes and therefore digest (barring SHA-256 collision). Same digest with different key is not a normal valid case. | Change the semantic matrix to state that a new idempotency key is a new signed envelope and must have a newly computed digest and distinct operation_id. Treat a fixture that changes either identity field while holding digest constant as invalid. |
| SEM-02 | Legacy `FailJobCommand` in the Store protocol uses `retry_delay_seconds`; v2alpha2 digest action map uses `retry_delay_micros`. The `worker.job.retry` action uses `delay_seconds`. | Units differ across API/domain/digest/SQL layers. Silent conversion, rounding or overflow could cause the signed digest to describe a different persisted delay. | Define one canonical internal unit, explicit conversion functions and bounds. The value signed and hashed must be the exact typed value used to calculate the database scheduling timestamp. |
| SEM-03 | R03.52.7.3.5 distinguishes exact assertion replay (committed nonce reuse is rejected) from client retry (fresh nonce, same business idempotency key/digest); Receipt Reconcile also uses a fresh assertion. | Exact-token replay, re-issued business request and a new Receipt Reconcile command are three distinct paths; prior wording conflated them. | Exact old assertion returns `ASSERTION_REPLAYED`; a fresh assertion over the same business Request Envelope may resolve the existing Receipt; Receipt Reconcile is separately scoped and uses a fresh nonce. |
| SEM-04 | `worker.receipt.reconcile` action matrix says resource is `receipt` and resource_id equals operation_id; Claim also has operation_id, and Receipt primary key/unique key uses tenant + operation_id. | It is unclear whether the Claim operation_id identifies the reconciliation request or the Receipt being reconciled. If they are the same, a fresh reconciliation operation cannot have a distinct identity. | Split `target_receipt_operation_id` from the current reconciliation `operation_id` in typed args or define resource_id as the target operation ID. Update digest envelope, Claim and SQL contract explicitly. |
| SEM-05 | PR #15 says action argument schemas currently do not allow null; generic codec supports null. | Codec-level capability can be mistaken for action-level permission. | Normative action schemas must reject null for all current action arguments; test null for every field. Generic codec null support remains an unused primitive. |
| SEM-06 | PR #15 candidate canonicalization ADR defines limits: depth 32, arrays/objects up to 4096, signed int64, uint32 byte lengths; JSON Schema separately caps Claim integers at 2^53−1 and some strings. SQL verifier does not show all identical Claim bounds. | The protocol limits are distributed and not all enforced identically in Schema, Python and SQL. | Publish one normative field/limit table and enforce exact parity in all implementations, including Claim numeric safe-integer bounds. |
| SEM-07 | PR #15 signer design says trusted normalizer materializes defaults before digest; Store independently reconstructs arguments from actual SQL params. | Current source has no signer implementation or integrated Handler call site proving this contract. | G3/G4 require signer and handler call-graph evidence; no defaults may be injected in digest helper or mutation path after signing. |
| SEM-08 | SQL strict Claim parser caps raw payload at 16 KiB; Python strict JSON parser has no explicit input cap; separately supplied operation_arguments have no total canonical-byte cap. | Transport, Claim, Request Envelope and argument surfaces have no shared size-budget contract. | Define explicit per-surface and total canonical byte limits; enforce before parsing/encoding/hashing and test max/max+1 in Python and SQL. |
| SEM-09 | Retry Policy Registry/legacy Store uses error_code up to 128 chars and safe_message up to 512; v2alpha2 codec limits error_code to 64 and has no safe_message max; Registry delay has no global max while Store/Retry cap at 86,400 seconds and Fail uses int64 microseconds. | Policy authority, field bounds and delay range/unit are not aligned across runtime, Store and v2alpha2. | Approve one trusted policy/version, common error/message bounds, global delay maximum and checked unit conversion; bind exact values to digest and mutation. |

| SEM-10 | v2alpha2 digest map declares `worker.dlq.replay` with empty operation_arguments; R03.52.5 ReplayPlan requires stable request_id, new_job_id, actor_id, reason, replay_number and authorization_policy_version. The preflight is plan-only and no production authorization issuer/UOW exists. | The digest does not bind caller-supplied reason/request_id; new Job ID and policy provenance are not mapped to a trusted source; action appears supported in codec but is not implemented. | Keep action fail-closed until G13 approves typed fields/provenance. Bind reason and stable request identity (or derive from trusted internal workflow); derive actor from Claim, replay_number/source state from locked DLQ, generate new_job_id server-side, persist trusted policy version, and atomically create Job/increment replay_count/audit. |
## 3. Normative Receipt identity rules (recommended, not approved)

- `operation_id` identifies one immutable signed operation and is unique within tenant scope.
- `idempotency_key` identifies the caller's retry scope within tenant + action.
- Both are part of the Request Envelope and digest.
- A re-issued assertion for the same business Request Envelope preserves operation_id, idempotency_key, action/resource and operation_arguments, and therefore preserves the request_digest; the assertion nonce/iat/exp/signature are fresh and are not part of that business digest.
- A changed operation ID or idempotency key is a different Request Envelope and must be re-signed with a recomputed digest.
- Same tenant/action/idempotency key + same digest, presented under a fresh assertion nonce, returns the stored Receipt/outcome and never repeats business effects; reuse of the previously committed assertion nonce is rejected.
- Same tenant/action/idempotency key + different digest returns IDEMPOTENCY_CONFLICT.
- Same tenant + operation_id under another idempotency key returns OPERATION_ID_CONFLICT.
- Different idempotency key + same digest should not be a generated valid vector because idempotency_key participates in the digest. A digest collision is not a semantic branch.

## 3.1 Normative assertion replay distinction (source-derived)

- A committed nonce cannot be reused in a new transaction; exact old signed assertion replay is rejected as `ASSERTION_REPLAYED`.
- A client retry uses the same immutable business Request Envelope and digest with a fresh nonce/iat/exp/signature; Receipt arbitration may return the existing terminal outcome without repeating business mutation.
- A Receipt Reconcile request is a distinct fresh assertion/authorization path; its target Receipt identity and digest relationship remain subject to the unresolved SEM-04 decision.

## 4. Normative retry-delay rule (recommended, not approved)

Prefer a canonical integer microsecond field in the signed v2alpha2 envelope if sub-second precision is required. Convert legacy seconds to microseconds exactly using checked integer multiplication. Reject values that overflow the accepted int64/range. Do not round floats. Database scheduling uses a timestamp derived from the exact signed microsecond value and database clock. If business policy only supports seconds, standardize on integer seconds in a separately versioned contract rather than silently converting.

## 5. Gate conclusion

These semantic conflicts block final G1/G4/G5/G6 acceptance. They must be resolved in the normative Protocol/Action/Receipt contracts and reflected in the Golden Vectors and integration tests.

## Change history

- 2026-11-03: Initial semantic conflict register.
