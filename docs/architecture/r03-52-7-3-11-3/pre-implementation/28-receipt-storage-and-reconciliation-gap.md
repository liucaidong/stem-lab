# v2alpha2 Receipt Storage, Legacy Receipt Separation and Reconciliation Gap

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / INTEGRATION GAP  
**As-of:** 2026-11-03  
**Gates:** G4/G5/G6/G9 OPEN

## 1. Two Receipt stores are present

### Legacy reference Receipt
The PR #13 fixture defines a legacy receipts table with:
- primary key (tenant_id, operation_id);
- job_id and session_id;
- request_digest and outcome;
- composite foreign key to the tenant/job/session row.

The legacy worker.receipt.reconcile path validates a v2alpha1 resource assertion and reads this legacy table through RLS. Its resource_id is required to equal operation_id.

### v2alpha2 helper Receipt
PR #19 defines a separate table: request_receipts_v2alpha2:
- generated receipt_id primary key;
- tenant_id, action, idempotency_key, operation_id;
- request_digest, resource_type, resource_id;
- receipt_status, outcome and timestamps;
- unique (tenant_id, action, idempotency_key);
- unique (tenant_id, operation_id).

The PR #19 reserve/finalize functions operate only on request_receipts_v2alpha2. They do not read/write the legacy receipts table and are not called by legacy action handlers.

## 2. Integration consequence

The existence of a legacy Receipt reconcile path does not prove that v2alpha2 Receipts can be reconciled. The current v2alpha2 action map includes worker.receipt.reconcile, but there is no integrated Handler path shown that:
- authenticates a v2alpha2 reconciliation assertion;
- reads request_receipts_v2alpha2 by the intended target operation identity;
- verifies the stored action/resource/idempotency identity and digest;
- handles pending vs terminal Receipt state;
- returns the stored outcome without repeating business effects;
- consumes a fresh assertion nonce under the cross-version policy.

A v2alpha2 Receipt Reconcile implementation must not accidentally query the legacy receipts table and report “not found” for an existing v2alpha2 Receipt.

### Missing read-only lookup helper

The only v2alpha2 Receipt SQL helpers are `reserve_request_receipt_v2alpha2` and `finalize_request_receipt_v2alpha2`. The reserve helper is insert-first: when the supplied tenant/action/idempotency key has no row, it creates a new `pending` Receipt before returning. There is no dedicated SELECT-only lookup by tenant + target operation_id. Reusing `reserve` for `worker.receipt.reconcile` can therefore create a new pending Receipt when the target is missing, violating the proposed read-only reconciliation contract. A dedicated read-only lookup path (or a carefully scoped SELECT in the Handler) is required; Reconcile must never create/finalize a business Receipt.

## 3. Receipt metadata gaps

The v2alpha2 helper table does not store:
- assertion version;
- subject;
- owner/worker identity;
- epoch;
- session_id separately;
- issuer/kid or nonce references;
- original action's immutable result/event identifiers.

The request_digest binds some of these values indirectly only if they are part of the canonical Request Envelope. The current envelope excludes issuer, subject, owner, epoch, iat, exp and nonce. If the system needs to ensure a Receipt replay is restricted to the same actor/lease identity, the helper table currently has no persisted actor-binding columns.

This does not prove an authorization bypass by itself: the trusted signer and Handler may independently enforce actor scope. It does mean Receipt helper equality alone is not enough to establish actor continuity.

## 4. Cross-version idempotency question

Legacy receipts and request_receipts_v2alpha2 have separate unique indexes. Therefore the same tenant/operation_id or logical business intent can exist once in each table unless a shared cross-version registry or migration policy prevents it.

The system must decide:
- Is business idempotency scoped per assertion contract version, or does it survive migration from v2alpha1 to v2alpha2?
- Can a legacy operation be reissued as v2alpha2 with the same operation_id/idempotency key?
- Does the v2alpha2 Receipt need to query a legacy Receipt before allowing a new mutation?
- If versions have separate Receipt stores, how is cross-version duplicate business execution prevented?
- Is the same nonce uniqueness domain shared across versions even when Receipt stores are separate?

Do not silently merge legacy and v2alpha2 Receipt semantics or modify the PR #13 reference table in this closure PR.

## 5. Recommended v2alpha2 Receipt reconciliation contract (proposal)

- Keep legacy receipts and v2alpha2 request_receipts_v2alpha2 separate during the compatibility period.
- For v2alpha2, resource_type=receipt and resource_id identifies the target logical operation/Receipt.
- Claim.operation_id remains the stable business operation ID being reconciled, consistent with the current resource_id=operation_id candidate, unless the protocol owner approves a separate target-operation field.
- Reconciliation is read-only with respect to business Job/Session/Transition/Outbox state.
- The reconciliation assertion uses a fresh nonce; it does not consume the original mutation assertion nonce. Recommended outcome rule: a typed missing/pending/terminal reconciliation result is a committed read outcome and commits the fresh reconciliation nonce; an authorization/infrastructure/transaction failure aborts and rolls back the nonce with the outer transaction. This outcome/commit mapping must be approved and tested.
- The handler looks up the v2alpha2 Receipt by tenant + operation_id and verifies action, idempotency key, resource type/id and stored digest according to the approved contract.
- A terminal Receipt returns its stored outcome; pending/missing/inconsistent Receipt returns a typed non-success result and never fabricates success.
- Reconcile must not create a new business Receipt for the same operation_id, because the unique operation identity is already owned by the original mutation.
- Any repair capability is a separate action with its own explicit write-set and audit record.

This proposal still needs a precise rule for how the reconciliation assertion's own request_digest relates to the original mutation request_digest. The two digests must not be compared as if they represent the same action envelope.

## 6. Required tests

- Legacy v2alpha1 Receipt reconcile still reads only legacy receipts and remains unchanged.
- v2alpha2 reconcile reads only request_receipts_v2alpha2.
- v2alpha2 Receipt cannot be reported missing merely because the legacy table has no row.
- Matching operation_id with wrong tenant/action/resource/idempotency identity is denied.
- Matching operation_id but wrong stored digest returns conflict/invariant error.
- Pending Receipt is not reported as succeeded.
- Reconcile consumes a fresh nonce; replaying the same reconciliation nonce is rejected.
- Reconcile does not create a second Receipt or mutate Job/Session/Transition/Outbox.
- Cross-version same logical operation behavior is tested with separate and shared Receipt stores.
- Actor continuity is tested for subject/owner/epoch changes after terminal completion.

## 7. Gate conclusion

G5/G6/G9 remain OPEN. PR #19 provides a standalone v2alpha2 Receipt helper; legacy Receipt reconcile does not integrate it. The target Receipt store, reconciliation identity and cross-version idempotency scope must be accepted before Handler implementation.

## Change history

- 2026-11-03: Initial Receipt storage and reconciliation audit.
