# v2alpha2 Receipt Helper Contract and Security Gap Audit

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / HELPER NOT PRODUCTION-ACCEPTED  
**As-of:** 2026-11-03  
**Gates:** G5/G7/G9/G10 OPEN

## 1. Verified helper structure

The PR #19 table request_receipts_v2alpha2 contains:
- receipt_id identity primary key;
- tenant_id, action, idempotency_key, operation_id;
- request_digest, resource_type, resource_id;
- receipt_status pending/succeeded/failed;
- JSONB outcome and created/updated timestamps;
- unique tenant/action/idempotency_key;
- unique tenant/operation_id;
- digest format check.

It has no foreign key to Job/Session, no session_id column, no actor/owner/epoch columns, no nonce reference, no retention policy and no RLS/grant statements in the helper SQL.

## 2. Reserve helper gaps

reserve_request_receipt_v2alpha2 accepts tenant/action/idempotency/resource/operation/digest as independent parameters. It validates non-empty strings and digest syntax, but does not itself:
- verify a signed Claim;
- verify the digest from a canonical Request Envelope;
- enforce the closed action/resource mapping;
- compare operation_id/resource_type/resource_id against a verified Claim;
- compare stored operation_id/resource_type/resource_id when same idempotency key and digest is found;
- validate tenant/resource relationships against Job/Session;
- enforce a maximum length for identity fields.

This is acceptable only as a narrow helper called by a trusted Handler with one already-validated typed binding. It is not a standalone authorization boundary.

## 3. Finalization helper gaps

finalize_request_receipt_v2alpha2 accepts only receipt_id, final_status and outcome. It:
- checks non-null receipt ID/status/outcome;
- permits succeeded/failed only;
- updates a pending row;
- allows exact repeat of the same terminal status/outcome;
- rejects a conflicting finalization.

It does not take tenant_id, operation_id, action, digest or actor identity as parameters, and it does not itself prove the caller owns the Receipt. If this helper were executable by a broad Runtime role, a caller able to guess/obtain another receipt_id could attempt to finalize it unless RLS/privileges or a trusted caller boundary prevents it.

The helper also does not define a closed outcome schema, maximum outcome size, sensitive-data policy or status/outcome table constraint. The table itself does not enforce:
- pending => outcome IS NULL;
- succeeded/failed => outcome IS NOT NULL;
- terminal outcome immutability against direct table writes.

## 4. Error and concurrency considerations

- Same idempotency key + same digest returns stored row, but identity equality beyond digest is not independently checked.
- Same key + different digest raises IDEMPOTENCY_CONFLICT.
- Operation unique violation maps to OPERATION_ID_CONFLICT through a broad unique_violation handler. If future unique constraints are added, unrelated violations may be misclassified.
- A serialization failure (40001) is raised when the conflict row is unexpectedly not found; caller must retry the entire transaction only after rollback.
- Finalization is serialized by SELECT FOR UPDATE on receipt_id.
- No timeout/lease/recovery semantics exist for a committed pending Receipt.
- No cleanup/archive policy exists.

## 5. Required production-shaped contract before implementation

1. Only a Handler may call reserve/finalize; Runtime cannot directly mutate Receipt rows.
2. The Handler passes one verified typed binding to both digest and Receipt helper.
3. Reserve conflict compares all immutable identity fields: tenant, action, idempotency key, operation ID, digest, resource type and resource ID.
4. Receipt outcome has a versioned closed schema, maximum size and sensitive-data allow-list.
5. Pending/terminal status and outcome constraints are enforced by database constraints as well as function logic.
6. Finalization is scoped by exact tenant/operation/digest or protected by a reviewed RLS/role boundary.
7. The helper is executed by a least-privileged identity; PUBLIC EXECUTE is revoked; exact grants and ownership are catalog-tested.
8. Direct table writes are denied except through the accepted action boundary.
9. Receipt is part of the same transaction as Nonce/Job/Session/Transition/Outbox/DLQ.
10. Reconciliation reads only the correct versioned Receipt store and returns stored terminal outcome without replaying effects.
11. Pending recovery, retention, cleanup and audit policy are explicit.
12. Every failure in reserve/finalize aborts the complete outer write set.

## 6. Gate conclusion

G5/G7/G9/G10 remain OPEN. PR #19 is a useful helper conformance prototype, not a production Receipt subsystem or a business idempotency boundary.

## Change history

- 2026-11-03: Initial Receipt helper contract/security gap audit.
