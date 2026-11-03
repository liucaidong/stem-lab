# R03.52.7.3.11.6 — Atomic Business Handler and Unit-of-Work Reference

## Scope

This increment introduces the first executable v2alpha2 business slice: package-validation Job completion. It is a PostgreSQL reference implementation and conformance harness, not a production deployment migration.

## Transaction boundary

The SECURITY DEFINER entry point verifies the signed assertion and Request Digest, overwrites the caller-controlled tenant GUC with the verified tenant, consumes the nonce, arbitrates the Receipt, locks Job then Session, validates the lease fence and expected revision, updates Job and Session, inserts Transition and Outbox records, finalizes the Receipt, and returns one outcome. The database statement runs inside one PostgreSQL transaction; any failure rolls back every write.

Global lock order:

1. Nonce unique key
2. Receipt idempotency key
3. Job row
4. Session row

Exact nonce reuse fails before Receipt arbitration. A fresh nonce with the same operation/idempotency/digest returns a pending or terminal Receipt without repeating the business mutation.

## Read-only reconciliation

The reconciliation entry point verifies a fresh signed assertion and consumes its nonce, then performs a SELECT-only lookup of the target Receipt by tenant and operation ID. It returns one of missing, pending, terminal, or inconsistent. It does not create/update a Receipt or touch Job, Session, Transition or Outbox state.

The reconciliation assertion uses action worker.receipt.reconcile, resource type receipt, and resource ID equal to the original operation ID. The operation ID and idempotency key bind the target Receipt.

## Tenant isolation and privilege model

- Receipt and Nonce Ledger tables use ENABLE + FORCE ROW LEVEL SECURITY. Nonce uniqueness is tenant + issuer + nonce (not key ID), and assertion expiry is persisted for safe retention; purge only after expiry plus the configured clock-skew/operational grace period.
- The handler/reconciliation functions are SECURITY DEFINER and must be owned by a dedicated NOLOGIN, NOSUPERUSER, NOBYPASSRLS role.
- The runtime role receives EXECUTE only on the two entry points; it receives no direct table or sequence privileges.
- The function owner has only the required table DML/SELECT privileges and remains subject to FORCE RLS.
- The verified tenant claim overwrites any caller-supplied app.tenant_id before protected table access.

## Fault-injection acceptance

The PostgreSQL conformance harness tests:
- signed Job completion across Nonce, Receipt, Job, Session, Transition and Outbox in one UOW;
- exact nonce replay rejection and fresh-nonce duplicate Receipt behavior;
- tenant GUC spoofing resistance and runtime direct-table privilege denial;
- pending, missing and terminal reconciliation outcomes;
- an Outbox-trigger failure after earlier writes, proving full transaction rollback;
- concurrent fresh-nonce requests with the same Receipt identity, proving one mutation and one terminal duplicate;
- runtime-role catalog inspection proving helper functions are not executable by the runtime role;
- a simulated lost COMMIT acknowledgement after server commit, followed by fresh-nonce reconciliation to the terminal Receipt.

## Explicit limitations

Only worker.job.complete for package.validate is implemented. Job retry, fail, renew, dead-letter, Outbox relay/consumer deduplication, DLQ Replay, cancellation, and other action handlers remain out of scope. The SQL assumes the R03.51 session/job/transition/outbox reference schema. Production migration ownership, key lifecycle, operational retention, monitoring, deployment grants and owner/security approval remain separate gates.
