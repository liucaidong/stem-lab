# R03.52.7.3.11.4 — Security and Tenant Isolation Gate

**Status:** SECURITY GATE BLOCKED / REFERENCE EVIDENCE ONLY  
**Baseline:** PR #20 HEAD `a9394870164bba5971ffa82b15c83d7e9b9cfc47`

## 1. Threat and control matrix

| Threat | Preconditions / path | Existing protection and evidence | Residual gap | Required acceptance test |
|---|---|---|---|---|
| Cross-tenant Receipt access | Runtime supplies another tenant's operation/Receipt ID | Receipt rows contain tenant_id; unique keys include tenant; no v2alpha2 RLS in Receipt SQL | No policy prevents direct cross-tenant SELECT/UPDATE; helper trusts caller identity | Runtime non-owner/NOBYPASSRLS reads/updates other tenant: denied; no existence leak |
| Exact Nonce replay | Same signed Assertion submitted after committed use | Legacy PR #13 nonce ledger exists; R03.52.7.3.5 defines one-transaction use | v2alpha2 verifier does not write a durable nonce ledger | Same token after commit always ASSERTION_REPLAYED before Receipt lookup |
| Idempotency collision | Same tenant/action/key but different digest | Receipt unique key and digest conflict in helper | Helper tests use invalid changed-operation_id/same-literal-digest fixture; helper does not validate full identity | Fresh nonce same envelope returns same outcome; changed digest/action/resource/operation conflicts |
| Digest substitution | Signed digest paired with different mutation arguments | SQL recomputes digest from Claim + supplied operation_arguments | No Handler proves supplied args are the exact SQL mutation values | Per-action substitution test: digest args differ from mutation params -> rollback |
| Resource substitution | Claim resource ID differs from persisted Job/Session/Outbox/DLQ | Schema and digest codec enforce some action/resource relationships; legacy verifier checks resource binding | No common v2alpha2 dispatcher/Handler; full persisted relationship binding absent | Wrong tenant/job/session/action/resource/epoch across all actions denied |
| Unauthorized DLQ Replay | Caller constructs ReplayAuthorizationDecision/ReplayPlan | Preflight validates matching actor/tenant/source/action/policy and limits | Dataclasses are caller-constructible; source row/counters not DB-locked; no production authorizer | Forged authorization object and stale source count denied; replay row locked and rechecked |
| Receipt privilege escalation | Direct function/table calls under Runtime role | Receipt functions use SECURITY INVOKER; fixed search_path=pg_catalog | No explicit PUBLIC revoke/exact grants/RLS/catalog tests; privileged test connection | pg_proc ACL/owner/prosecdef/search_path, role membership, direct table writes and function calls tested |
| Outbox event forgery | Runtime inserts arbitrary event/payload or external relay publishes uncommitted event | Legacy fixture has event-scoped dispatcher and RLS; architecture requires Outbox | No v2alpha2 Handler/Relay binding or consumer inbox integration | Event must derive from typed mutation; no publish before commit; duplicate event_id dedup |
| Retry policy manipulation | Worker injects classifier or constructs FailureDecision | Registry validates policy shape, unknown code fails closed | WorkerRuntime callback arbitrary; policy_version absent; attempt budget not bound | Inject hostile callback/forged FailureDecision; handler must ignore/reject; policy version pinned |
| Concurrent state transition | Competing Complete/Fail/Renew/Retry or stale epoch | Legacy PostgreSQL fixture has row locks and fencing tests | v2alpha2 action lock graph and transaction not implemented | Multi-connection same Job, stale epoch, concurrent action and deadlock tests |
| Transaction ambiguity exploitation | Client retries old Assertion after lost COMMIT response | Store error taxonomy has TRANSACTION_OUTCOME_UNKNOWN; R03.52.7.3.5 specifies fresh nonce reconciliation | No v2alpha2 read-only Reconcile or complete Receipt UOW | COMMIT response loss + fresh nonce Reconcile; no duplicate mutation |
| Oversized input / numeric overflow | Oversized raw Claim/Envelope/args or out-of-range iat/exp | SQL Claim parser caps 16 KiB; typed encoder has nesting/array/object/int64 bounds | Python raw parser and total args/canonical bytes unbounded; schema/SQL timestamp mismatch | Per-surface max/max+1, deep nesting, 2^53 and bigint boundary tests |
| SQL exception leakage | Cast, uniqueness, RLS or helper errors bubble to caller | Some stable StoreError taxonomy and explicit helper messages | v2alpha2 SQL uses raw RAISE exceptions; no uniform translation boundary | Assert stable public code/safe_message; raw SQL/driver details never returned |
| Unauthorized direct table access | Runtime bypasses helper and reads/writes Receipt/Nonce/issuer keys | Legacy role matrix separates runtime/verifier/dispatcher/replay identities | v2alpha2 Receipt SQL defines no roles, grants, RLS or catalog contract | Non-owner runtime direct SELECT/INSERT/UPDATE/DELETE denied except exact approved columns/rows |
| Cross-version replay/downgrade | Same assertion or action routed through legacy and v2alpha2 paths | Version discriminator exists in v2alpha2 schema; legacy tests separate | No common fail-closed dispatcher or cross-version nonce domain | Version confusion, downgrade, same nonce cross-version and unknown version tests |

## 2. Receipt helper privilege facts

`sql/request-receipt-v2alpha2.sql` defines two ordinary PL/pgSQL functions with no SECURITY DEFINER clause, so default execution is SECURITY INVOKER. The SQL asset contains no explicit PUBLIC EXECUTE revocation, exact EXECUTE grants, RLS statements or role creation. PostgreSQL default function ACL normally includes PUBLIC EXECUTE, but effective invocation also depends on schema USAGE and default privileges; actual catalog state must be tested, not inferred from source alone.

The Receipt test opens its configured DSN with autocommit and does not SET ROLE to a least-privileged Runtime login. It proves helper behavior under that fixture connection, not the production privilege boundary.

## 3. Recommended security design (not approved)

- Keep the Runtime login NOLOGIN? The login principal should be a non-owner, NOSUPERUSER, NOCREATEROLE, NOBYPASSRLS and NOINHERIT role; it must not be a member of verifier/helper owner roles.
- Prefer SECURITY INVOKER plus exact minimum table/column privileges and forced RLS where this does not expose broad direct access.
- If a privileged function is unavoidable, use a capability-specific NOLOGIN owner (not the shared legacy verifier owner), fixed search_path, schema-qualified references, no dynamic SQL, exact tenant/action/resource/digest validation, REVOKE PUBLIC, and exact EXECUTE grants.
- Runtime must not read issuer private keys, write nonce rows outside the authorization boundary, or directly mutate protected business rows outside the approved UOW.
- Verify function owner, prosecdef, proconfig/search_path, ACL, role memberships, schema USAGE/CREATE, table ACL, RLS enabled/forced and policy definitions through PostgreSQL catalogs.
- Do not weaken RLS or grant broad table privileges to make tests pass.

## 4. Required catalog and negative tests

1. Query pg_proc/pg_namespace/pg_roles/pg_auth_members and has_function_privilege/has_table_privilege for every v2alpha2 function and relation.
2. Assert no unexpected PUBLIC EXECUTE, schema CREATE, table ownership, BYPASSRLS, superuser, role inheritance or SET ROLE path.
3. Assert direct Receipt/Nonce/issuer-key access denied to Runtime unless explicitly required and narrowly scoped.
4. Assert wrong tenant/action/resource/digest cannot reserve or finalize a Receipt.
5. Assert Receipt Reconcile has SELECT only and cannot INSERT/UPDATE/DELETE.
6. Assert helper search_path and object-shadowing resistance.
7. Run under a real non-superuser login with NOBYPASSRLS, not merely SET ROLE from a privileged session.
8. Prove rollback, nonce uniqueness, cross-tenant denial and pool context reset.

## 5. Gate conclusion

G9 is **BLOCKED**. No v2alpha2 least-privilege or tenant-isolation acceptance is established by Run #488. Formal Security/Database approval and negative catalog tests remain mandatory.
