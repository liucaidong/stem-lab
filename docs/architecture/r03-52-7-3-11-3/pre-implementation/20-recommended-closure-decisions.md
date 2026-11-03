# Recommended Closure Decisions for G1–G13

**Version:** 0.1.0  
**Status:** RECOMMENDATIONS ONLY / NOT ACCEPTED  
**As-of:** 2026-11-03  
**Decision authority:** Project owner + Architecture + Security + Database

## 1. Purpose

This document recommends a coherent resolution for the open protocol/transaction/security choices. It does not accept those decisions, change protected project decisions, or authorize implementation. Each recommendation must be explicitly reviewed and approved before it becomes normative.

## 2. Recommended decisions

### REC-01 — Canonical Request Digest

**Recommendation:** retain the existing typed binary encoding candidate, not JSON text canonicalization/JCS, for v2alpha2.

Rationale:
- PostgreSQL can independently reproduce explicit type tags, length prefixes and UTF-8 bytes without relying on jsonb textual serialization.
- The candidate supports the current narrow action types and integer-only numeric model.
- Existing Python/PostgreSQL golden vectors provide a useful conformance baseline.

Conditions before acceptance:
- remove all orphan function-body fragments from the SQL asset;
- enforce one normative Claim/Envelope field limit table across Schema/Python/SQL;
- enforce maximum safe integer for Claim epoch/iat/exp consistently;
- align the ADR's uint32 length declaration with the current Python `_u32` and PostgreSQL `int4send` positive ceiling (2^31−1), or implement full uint32 consistently;
- define total Claim, Request Envelope and separately supplied operation_arguments byte budgets before accepting the codec as normative;
- add C0/C1, supplementary Unicode, unpaired surrogate, exponent/decimal, -0, nested limits and null negative vectors;
- verify the full SQL asset, not extracted function fragments;
- obtain formal R535-OD3 Architecture/Security approval.

### REC-02 — No Unicode normalization

**Recommendation:** keep exact Unicode scalar sequences as UTF-8; do not apply NFC/NFD or trimming at the digest layer.

Rationale: automatic normalization can silently change identifiers and make the signed operation differ from the caller's raw value. Trusted normalization may resolve business defaults before signing, but it must be deterministic and explicit.

Acceptance: test that NFC and NFD strings produce different canonical bytes/digests; reject invalid scalar sequences and controls per one shared rule.

### REC-03 — Version dispatch

**Recommendation:** dispatch by assertion family using exact discriminator + exact field set:
- Claim Assignment v1alpha1 -> existing Claim verifier only;
- Resource Assertion v2alpha1 (no contract_version, legacy field set) -> legacy resource verifier only;
- Resource Assertion v2alpha2 (contract_version="2alpha2" + idempotency_key + request_digest) -> v2alpha2 verifier only;
- anything mixed, unknown or ambiguous -> reject.

Never fallback after the selected verifier fails. Keep old verifier semantics unchanged during migration. A shared dispatcher should be a thin classifier; it must not normalize legacy claims into a new semantic form.

### REC-04 — Trusted Signer and key registry

**Recommendation:** keep the Ed25519 private key exclusively in a trusted signer service or isolated signing process; PostgreSQL stores public verification keys only. Runtime worker processes do not receive signing private keys and do not submit arbitrary caller-supplied digest for the signer to attest.

Key registry candidate:
- issuer identity is enrolled by a trusted administrative process;
- (issuer, kid) is the logical lookup identity;
- a kid is never reused for different key material;
- rotation publishes a new kid and permits a bounded overlap;
- revocation is explicit and auditable;
- public key validity is bounded by not_before/not_after and revoked_at;
- ordinary Runtime cannot modify or administer key records;
- verification failures collapse into stable non-secret error classes.

Deployment choice (pgsodium vs dedicated gateway) remains under DEC-14 and must not be selected here.

### REC-05 — Action typed binding

**Recommendation:** each handler receives only raw assertion plus action-specific typed arguments. It creates one immutable internal binding from the verified Claim and arguments. The digest projection and SQL mutation projection are derived from that same object.

Never accept separate tenant_id, job_id, session_id, owner, epoch, resource_id or operation_id mutation arguments from the caller after verification. Derive identity from Claim and recheck persisted relationships in the transaction.

### REC-06 — Receipt identity

**Recommendation:** preserve both unique constraints:
- (tenant_id, action, idempotency_key);
- (tenant_id, operation_id).

Store the digest, resource type/id, terminal outcome and immutable result reference. On same idempotency key:
- same digest and same immutable identity under a fresh assertion nonce -> consume the fresh nonce and return stored Receipt/outcome, no business mutation;
- different digest -> IDEMPOTENCY_CONFLICT;
- any inconsistent stored operation/resource identity -> reject as invariant violation even if helper input digest matches.

A new idempotency key is a new signed envelope and therefore a newly computed digest. Never reuse a literal digest after changing operation_id or idempotency_key.

### REC-07 — Nonce uniqueness across versions

**Recommendation:** preserve the legacy unique key scope (issuer, kid, nonce) as the cross-version uniqueness domain. Add version/operation/digest metadata without changing legacy validation semantics, or introduce a common unique registry that both legacy and v2alpha2 paths must consult atomically.

Do not use separate per-version unique namespaces unless a formal threat model proves cross-version replay impossible. Nonce consumption occurs in the same transaction as Receipt arbitration and the business write set. Reusing the exact signed assertion after its nonce committed is rejected as `ASSERTION_REPLAYED`; Receipt lookup must not override the nonce collision. A client retry preserves the immutable business Request Envelope and digest but uses a fresh assertion nonce/signature; Receipt arbitration may then return the existing terminal outcome without a second business mutation.

### REC-08 — Atomic Unit-of-Work

**Recommendation:** all durable state for one mutating action belongs to one caller-owned transaction:
Job/Session/Receipt/Nonce/Transition/Outbox/DLQ as applicable. The action helper never commits. Any infrastructure/write-set failure propagates and aborts the entire transaction. The caller owns commit/rollback.

Broker publish is outside the database transaction. Outbox dispatch claim is committed before external publish; transport is at-least-once and consumer effect is idempotent.

### REC-09 — Receipt Reconcile identity

**Recommendation:** separate the current reconcile operation identity from the target Receipt identity:
- Claim.operation_id = this reconciliation command's operation ID;
- Claim.resource_type = receipt;
- Claim.resource_id = target Receipt's operation ID;
- action arguments may include a typed target_operation_id only if resource_id cannot fully express it.

Reconcile should be read-only by default. Any repair capability is a distinct action/contract with its own authorization and write-set rules.

### REC-10 — Lock order

**Recommendation:** evaluate the candidate total rank:
Job -> Session -> Receipt -> Nonce -> DLQ -> Transition -> Outbox.
Receipt Reconcile remains Receipt-only; Outbox Dispatch/Ack must not lock Job/Session; DLQ Replay must not acquire DLQ before a source Job lock if it needs both.

Acceptance requires SQL/FK/unique-index/trigger edge inventory and deterministic multi-connection wait-for tests.

### REC-11 — SQL execution security

**Recommendation:** keep v2alpha2 helpers SECURITY INVOKER unless a specific capability proves a need for SECURITY DEFINER. Any definer function must have a dedicated NOLOGIN least-privilege owner, fixed search_path, schema-qualified references, PUBLIC EXECUTE revoked, exact EXECUTE grants and catalog/negative tests.

Do not widen Runtime direct table grants or weaken RLS to simplify Handler integration. Explore capability-specific roles in a disposable experiment first; R535-OD5 remains open.

### REC-12 — Business rejection versus infrastructure abort

**Recommendation:** define three separate outcomes:
1. same business Request Envelope re-issued with a fresh assertion nonce and a matching terminal Receipt -> return stored outcome, no business mutation; exact old signed assertion replay is `ASSERTION_REPLAYED`;
2. valid but business-rejected request -> explicit policy whether a terminal failed Receipt/Nonce commits, with no partial Job/Transition/Outbox effects;
3. infrastructure/write-set failure -> full transaction rollback, no partial durable outcome.

Do not let a broad exception handler return false/null after partial writes. The transaction coordinator must treat typed errors as rollback-required.

### REC-13 — Retry Policy authority, version and units

**Recommendation:** treat the R03.52.4 Retry Policy Registry as the source of retryability, safe message and delay decisions. Resolve the policy from a trusted, version-pinned registry using the locked persisted Job attempt_count/maximum_attempts and stable error_code. Do not treat worker/caller-supplied retryable, safe_message or delay as authoritative merely because those values are signed.

The exact policy version (or immutable policy digest) and the derived values must be bound through the same typed action binding used for Digest and SQL mutation. Define a global/per-code maximum, a canonical internal delay unit, checked conversions and explicit rounding/overflow behavior. Fail and Retry must not compute contradictory scheduling decisions. The existing registry's float-seconds fields and sample policy do not constitute an approved production maximum or conversion rule.

This is a recommendation only. Worker, Protocol, Security and Database owners must approve the authority, policy pinning, bounds and conversion before G1/G4/G13 acceptance.

### REC-14 — Keep DLQ replay fail-closed until action binding and UOW are accepted

The v2alpha2 digest action map currently recognizes `worker.dlq.replay` with an empty argument tuple, while the R03.52.5 preflight plan contains a stable request_id, human reason, actor, replay number, policy version and distinct new Job ID. The preflight is not a production authorization issuer or database transaction.

**Recommendation:** do not dispatch this action to a v2alpha2 business Handler yet. Fail closed before Receipt/Nonce/business writes. Before enabling it, approve which fields are caller-signed versus trusted/server-derived; map the stable request identity to the idempotency contract; bind the human reason or source it from a trusted workflow; derive actor from verified Claim subject; derive replay count/number under a locked DLQ row; generate new_job_id through the approved server ID strategy; and persist trusted authorization policy version. The production UOW must lock source Job/DLQ, revalidate authorization/limit, reserve idempotency, create the new Job, increment replay_count and append immutable audit record atomically.

This remains outside the current eight-action Handler slice and is not authorized by presence in the digest action registry.

## 3. Decisions intentionally not made

- Production Store Adapter, database driver, connection pool, PostgreSQL provider or deployment topology.
- Production cryptographic extension/provider selection.
- Production key custody/HSM/KMS vendor.
- Broker provider, consumer inbox deployment or exactly-once claims.
- Production retention/archival period.
- Product Code Freeze release or P3.17 authorization.

These remain governed by DEC-03/DEC-14 and other project approvals.

## 4. Acceptance process

For each REC item:
1. review exact source evidence and threat model;
2. record ACCEPTED/REJECTED/DEFERRED with named owner and date;
3. update canonical contract and dependent test vectors;
4. update Gate matrix;
5. do not implement until the affected gate is accepted.

## 5. Gate conclusion

This is a recommended decision package, not an accepted architecture. G1–G10 remain OPEN until explicit approvals and test evidence are recorded.

## Change history

- 2026-11-03: Initial recommended closure decisions.
