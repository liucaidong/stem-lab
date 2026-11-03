# PR #13 Legacy PostgreSQL Role and Table-Grant Matrix

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / LEGACY FIXTURE ONLY  
**As-of:** 2026-11-03  
**Gate:** G9 OPEN

## 1. Role definitions observed

In scripts/test_postgres_resource_scoped_authorization.py:

| Role | Login | Key attributes | Membership / purpose |
|---|---|---|---|
| VERIFIER | NOLOGIN | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOBYPASSRLS | Owner of legacy SECURITY DEFINER verifier/action functions |
| RUNTIME | NOLOGIN | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOBYPASSRLS | Application runtime capability role |
| LOGIN | LOGIN | NOINHERIT, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS | Granted RUNTIME membership; test client assumes RUNTIME role |
| DISPATCHER | LOGIN | NOINHERIT, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS | Dedicated Outbox dispatch/ack principal |
| REPLAY | LOGIN | NOINHERIT, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS | Dedicated DLQ replay principal |

The fixture creates all roles and schemas with an administrative test connection. It grants VERIFIER USAGE/CREATE on the test schema during bootstrap, then revokes CREATE after function/policy setup.

## 2. Verifier grants and RLS

VERIFIER receives:
- SELECT on issuer_keys; USAGE on pgsodium schema and EXECUTE on the detached Ed25519 verify function;
- SELECT on sessions, jobs, receipts, dlq_items and dlq_replay_principals;
- INSERT on jobs, transitions, outbox and dlq_items;
- UPDATE on selected Job fields (status, lease expiry, owner, available_at, attempt_count, last_error_code, epoch);
- SELECT/INSERT on nonce_ledger;
- SELECT/UPDATE on selected Outbox dispatch fields;
- SELECT/INSERT/UPDATE on claim_nonce_ledger;
- SELECT on worker_assignments and outbox_dispatchers;
- selected RLS policies for verifier reads/writes on protected tables.

The fixture enables and FORCEs RLS on sessions, jobs, receipts, transitions, outbox, dlq_items, nonce_ledger, worker_assignments, claim_nonce_ledger, outbox_dispatchers and dlq_replay_principals.

The verifier policies are broad within the isolated fixture (for example USING(true) for the verifier role on selected tables). PR #14/11.1 records the resulting shared-owner blast-radius concern. This is not a production role recommendation.

## 3. Runtime grants

RUNTIME receives:
- EXECUTE on authorize_v2(text), claim_next_v1(text,integer), renew_v2(text,integer), fail_v2(text), retry_v2(text,integer,text), dead_letter_v2(text,text,text), and assertion_allows(...);
- SELECT on jobs and sessions;
- UPDATE(status) on jobs;
- SELECT/INSERT on legacy receipts and transitions;
- INSERT on selected Outbox columns (tenant/event/job/session/operation/event type/payload).

RUNTIME does not receive direct grants on nonce_ledger, dlq_items, issuer_keys or broad Job fencing columns in the inspected grant block. RLS further constrains the permitted direct statements through the transaction-local signed assertion and exact resource predicates.

This means the legacy Complete path is intentionally a multi-statement RLS path that permits Runtime to update Job status and insert selected Receipt/Transition/Outbox rows. It is not evidence that a v2alpha2 Runtime should receive those same direct grants.

## 4. Dispatcher and Replay grants

- DISPATCHER receives schema USAGE and EXECUTE only on dispatch_outbox_v2(token, lease_seconds) and ack_outbox_v2(token).
- REPLAY receives schema USAGE and EXECUTE only on replay_dlq_v2(token).
- Neither role is granted general Job/Receipt/Nonce/Transition/Outbox table writes in the inspected grant block.

## 5. Function ownership and execution

The legacy verifier/action functions are changed to owner VERIFIER, PUBLIC EXECUTE is revoked, and exact EXECUTE grants are issued to Runtime/Dispatcher/Replay roles. The verifier role is NOLOGIN and NOBYPASSRLS.

The source audit identifies broad internal RLS policies for the shared VERIFIER owner. A capability-specific role split is a candidate for future security review, not an accepted change.

## 6. v2alpha2 delta

The v2alpha2 digest and Receipt SQL files do not reproduce this role setup:
- no accepted Runtime/Verifier/Dispatcher/Replay role matrix;
- no explicit production grants/revokes;
- no RLS enable/force/policies for v2alpha2 Receipt/Nonce tables;
- no catalog assertions for owner, security mode, PUBLIC EXECUTE, role membership or direct-write denial;
- helper tests use privileged test connections and do not prove least-privilege invocation.

Therefore the legacy grants cannot be copied to v2alpha2 by default. The v2alpha2 handler boundary should be designed independently and least-privilege tested before implementation.

## 7. Gate conclusion

G9 remains OPEN. This matrix records the current legacy fixture authority. It is not an accepted production privilege model and does not authorize broad Runtime grants for the new v2alpha2 path.

## Change history

- 2026-11-03: Initial legacy PostgreSQL role/grant inventory.
