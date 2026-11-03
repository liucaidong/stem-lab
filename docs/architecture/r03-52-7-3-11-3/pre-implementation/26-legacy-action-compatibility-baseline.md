# Legacy Worker Action Behavior and Compatibility Baseline

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / COMPATIBILITY BASELINE INCOMPLETE  
**As-of:** 2026-11-03  
**Gates:** G0/G2/G4 OPEN

## 1. Purpose

This document records the legacy v1alpha1/v2alpha1 behavior that v2alpha2 integration must not silently change. The source is the PR #13 PostgreSQL resource authorization reference and its test harness, fetched from the PR #20 stacked branch.

This is a test fixture/reference implementation, not a production Store Adapter. It is nevertheless the current compatibility baseline.

## 2. Assertion families

- Worker Claim Assignment v1alpha1 is used by claim_next_v1 and is distinct from Resource Assertion v2alpha1.
- Worker Resource Assertion v2alpha1 is used by verify_v2/authorize_v2 for resource-scoped operations.
- v2alpha2 adds explicit contract_version, idempotency_key and request_digest and must not be silently accepted by legacy verifier paths.

## 3. Legacy call-path inventory

| Action/path | Legacy entry point | Current auth model | Durable behavior | Compatibility constraint |
|---|---|---|---|---|
| Claim assignment | claim_next_v1(token, lease_seconds) | Separate v1alpha1 Claim Assignment verifier; trusted assignment and allowed job types; nonce/assignment/worker binding | Select eligible Job with SKIP LOCKED; owner/lease/attempt/epoch updates | Keep Claim Assignment v1alpha1 distinct; do not infer resource scope from caller |
| Renew | renew_v2(token, lease_seconds) | SECURITY DEFINER function calls authorize_v2 | Extend lease using database clock under Job owner/epoch/state fence | Preserve legacy argument units/range and false/null behavior unless separately versioned |
| Complete | Multiple direct RLS-protected statements, no dedicated complete_v2 function | authorize_v2 plus transaction-local assertion context and RLS policies | Job completion, Session revision/result update, Receipt, Transition and Outbox through separate statements | Do not treat this multi-statement legacy path as an atomic v2alpha2 Handler |
| Fail | fail_v2(token) | SECURITY DEFINER function calls authorize_v2 | Job failure state plus Transition/Outbox | Legacy signature has no error/retry arguments although v2alpha2 digest contract does |
| Retry | retry_v2(token, delay_seconds, error_code) | SECURITY DEFINER function calls authorize_v2 | Requeue/scheduling fields plus Transition/Outbox | Preserve seconds unit and existing retry behavior; v2alpha2 uses separate retry/fail contracts |
| Dead Letter | dead_letter_v2(token, error_code, terminal_reason) | SECURITY DEFINER function calls authorize_v2 | Job terminal state, DLQ row, Transition and Outbox | Preserve terminal predicates, DLQ identity and audit behavior |
| Receipt Reconcile | RLS-protected Receipt SELECT | verify_v2/authorize_v2 checks receipt action/resource and persisted Receipt identity | Read existing Receipt by tenant/operation identity | Read-only semantics must remain distinct from mutating actions |
| Outbox Dispatch | dispatch_outbox_v2(token, lease_seconds) | Separate SECURITY DEFINER dispatcher path; exact audience/action/resource; enabled dispatcher principal | Claim event, set dispatch owner/epoch/lease/attempt count | Preserve dispatcher identity, lease fencing and at-least-once semantics |
| Outbox Ack | ack_outbox_v2(token) | Separate SECURITY DEFINER dispatcher path; exact event/owner/epoch/lease | Mark exact event dispatched/acknowledged | Stale dispatch epoch/owner must remain fenced |
| DLQ Replay | replay_dlq_v2(token) | Separate replay principal/grant, source DLQ scope and replay limit | Create a distinct new Job; retain original DLQ evidence; append Outbox | Separate action/resource capability; not silently folded into Dead Letter |

## 4. Legacy security and error boundaries

Observed in PR #13 fixture:
- verify_v2 parses and validates the resource assertion and action/resource mapping.
- authorize_v2 checks audience, transaction-local resource context, persisted Job/Session relationship and owner/epoch/lease where applicable, then inserts a nonce-ledger row keyed by (issuer, kid, nonce) and binds it to transaction/token.
- renew/fail/retry/dead_letter and Outbox dispatch/ack are SECURITY DEFINER functions owned by the verifier role, with PUBLIC EXECUTE revoked and explicit Runtime/Dispatcher grants.
- the shared verifier owner has broad internal RLS policies and grants; PR #14/11.1 records the resulting blast-radius risk.
- several legacy functions catch OTHERS and return NULL/false. A local PL/pgSQL exception block does not prove the caller's entire outer transaction is uncommittable.
- Complete is multiple RLS-protected Runtime statements; it is not a single mandatory all-write-set entry point.
- Runtime has explicit SELECT/INSERT privileges for selected Receipt/Transition/Outbox paths in the disposable fixture, constrained by RLS.

These behaviors are not automatically appropriate for v2alpha2. They are the baseline to preserve for legacy callers until an approved migration changes them.

## 5. Legacy Nonce semantics

The legacy ledger uses primary key (issuer, kid, nonce). authorize_v2 inserts a nonce row and associates it with the current transaction and token. Multiple RLS statements within the same transaction can be authorized by the transaction-bound record; a new transaction cannot reuse the committed nonce.

The upstream R03.52.7.3.5 contract states:
- same token may authorize multiple SQL statements in one UOW;
- the nonce is consumed once at transaction level;
- client retry uses a fresh assertion nonce but the same business idempotency key/digest;
- business idempotency is separate from assertion replay protection.

Any v2alpha2 nonce design must preserve these legacy semantics and explicitly prove cross-version replay handling.

## 6. Compatibility acceptance tests

- Claim Assignment v1alpha1 remains accepted only by claim_next_v1.
- Resource Assertion v2alpha1 remains accepted by legacy resource handlers with unchanged required fields and behavior.
- v2alpha2-only fields are rejected by legacy v2alpha1 verifier.
- v1alpha1/v2alpha1 tokens are rejected by v2alpha2 entry points; no fallback.
- Legacy action argument units/signatures remain unchanged (notably Retry delay seconds and Fail's no-argument legacy signature).
- Existing owner/epoch/DB-clock lease fences remain unchanged.
- Existing transaction-bound nonce behavior remains unchanged.
- Existing Receipt reconciliation read scope remains unchanged.
- Existing Outbox dispatcher audience, principal, epoch and stale-ack behavior remain unchanged.
- Existing DLQ replay creates a new Job and retains source evidence.
- PR #13 test harness remains unmodified and continues to pass.

## 7. Migration strategy constraint

Do not replace legacy handlers in place during the pre-implementation closure. The first v2alpha2 vertical slice should use a distinct explicit entry point and verifier dispatch. A later migration can route callers to v2alpha2 only after compatibility, rollout and rollback policy are approved.

## 8. Gate conclusion

G0/G2/G4 remain OPEN. This document captures a source-derived baseline but does not yet prove every legacy error, transaction and edge-case behavior. A complete regression matrix must run unchanged before any versioned migration.

## Change history

- 2026-11-03: Initial legacy Worker action behavior inventory.
