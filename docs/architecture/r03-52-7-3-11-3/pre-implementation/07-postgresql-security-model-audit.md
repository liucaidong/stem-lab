# PostgreSQL Permission, RLS and Function Trust-Boundary Audit

**Version:** 0.1.0  
**Status:** SOURCE AUDIT / TARGET MODEL NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gate:** G9 OPEN

## 1. Existing legacy reference fixture facts

The R03.52.7.3.11.1 inventory records 11 SECURITY DEFINER functions in the disposable PR #13 reference fixture. All 11 are owned by one NOLOGIN verifier role, use fixed search_path, and revoke PUBLIC EXECUTE. Ten functions have direct application-principal EXECUTE grants; one helper is private. The same owner has broad internal RLS policies across protected relations.

The inventory explicitly identifies the residual risk: the shared verifier owner means each SECURITY DEFINER function inherits the same table privileges and broad internal RLS reach. This does not prove an exploitable flaw in the current fixed functions; it does increase blast radius if a function is incorrect or added without review.

The R03.52.7.3.11 architecture review recommends investigating capability-specific NOLOGIN helper roles and separately proving any trusted transaction context. It rejects BYPASSRLS/table ownership as a shortcut and rejects caller-controlled GUCs as trusted authorization context. These recommendations are not approved production role decisions.

## 2. v2alpha2 helper privilege facts

The disposable v2alpha2 SQL assets define functions and tables but do not, in the inspected files, establish an accepted production role/ownership/EXECUTE/RLS model. The digest PostgreSQL harness connects using its database test connection, creates the schema/functions and executes helper calls. The Receipt harness likewise creates the schema and calls the functions without proving execution as a least-privileged Runtime principal.

No evidence from these helper tests establishes:
- PUBLIC EXECUTE has been revoked from every helper function; the inspected v2alpha2 SQL assets contain no explicit PUBLIC revoke or exact EXECUTE grants, and default function ACLs normally include PUBLIC EXECUTE (effective callability also depends on schema USAGE/default privileges);
- Runtime cannot directly read issuer keys or mutate Receipt/Nonce/Transition/Outbox tables;
- helper ownership and search_path are safe under all object-shadowing conditions;
- RLS is enabled and forced on every protected relation;
- the Runtime login cannot SET ROLE into a more privileged helper role;
- SECURITY DEFINER is necessary or safe for the v2alpha2 path.

The current v2alpha2 verifier functions are not declared SECURITY DEFINER in the inspected SQL; do not change that posture without a threat model and explicit review. The Receipt helper functions are also ordinary PL/pgSQL functions with no `SECURITY DEFINER` clause, so they execute as SECURITY INVOKER by default. Their tests use privileged fixture connections and do not prove that Runtime can invoke them without direct Receipt table privileges.

## 3. Role taxonomy to evaluate (not an approved selection)

| Principal class | Purpose | Minimum candidate authority | Explicit restrictions |
|---|---|---|---|
| Migration/Admin | DDL, ownership, grants, schema changes | Controlled schema/table/function changes during migration | Not used by application runtime; credentials isolated |
| Runtime login | Invoke permitted business action entry points | EXECUTE on approved entry functions; minimum read access strictly required by invoker design | No table owner, superuser, BYPASSRLS, helper-role membership or broad direct writes |
| Verification helper | Read issuer/key metadata and verify assertions | Only key/crypto operations required by verifier | NOLOGIN, NOSUPERUSER, NOBYPASSRLS, NOINHERIT; no unrelated mutation |
| Job mutation helper | Fenced Job/Session/Transition/Receipt/Outbox writes for approved Job actions | Exact tables/columns and rows required for Job action | No Claim/Dispatcher/Replay authority by default |
| Outbox helper | Exact event dispatch/ack and lease fencing | Outbox event-scoped read/update; nonce/delivery identity as accepted | No Job terminal mutation or DLQ replay |
| DLQ helper | Exact DLQ replay grant and fresh Job creation | DLQ grant/read/update and required new Job/event writes | No general Runtime/Outbox mutation |
| RLS predicate helper | Evaluate transaction-bound authorization evidence | Read-only access to minimum authorization ledger | No general verifier authority |

This taxonomy is a design exploration derived from prior architecture documents. It is not permission to create or assign these roles yet. The exact split must be justified by the action call graph and database execution model.

## 4. Required catalog security invariants

For every protected schema/table/function, CI should inspect PostgreSQL catalogs and assert:

- Protected tables have RLS enabled and forced where required.
- No unexpected table owner, superuser or BYPASSRLS principal can be assumed by Runtime.
- Runtime has no membership path to migration/admin/helper roles.
- Function owner, language, SECURITY INVOKER/DEFINER flag, volatility, parallel-safety, search_path and identity arguments match a reviewed manifest.
- PUBLIC EXECUTE is revoked unless a documented public entry is explicitly approved.
- EXECUTE grants are explicit and action-specific.
- Schema CREATE is absent for runtime principals after setup.
- Direct table writes are denied where writes must go through an action entry point.
- Column-level grants cannot mutate tenant, owner, epoch, status, lease, operation identity or other fencing fields outside the approved path.
- RLS policies do not trust caller-set custom GUCs, caller-writable temp tables or application-supplied tenant IDs as proof of authorization.
- SECURITY DEFINER routines use a fixed safe search_path and schema-qualified references; dynamic SQL is prohibited unless separately reviewed and safely parameterized.
- Function replacement/ownership changes are migration-only and catalog-audited.

## 5. Negative security tests

- Runtime SELECT issuer key/private key material: denied; only public verification material may be exposed where intended.
- Runtime direct INSERT/UPDATE/DELETE Receipt, Nonce, Transition, Outbox, DLQ and Job fencing columns: denied unless explicitly granted by the accepted design.
- Runtime SET ROLE to helper/migration/admin: denied.
- Runtime CREATE/REPLACE function or policy in protected schema: denied.
- PUBLIC execute on private helpers: denied.
- Search_path shadowing/temp object attacks: no altered function behavior.
- Cross-tenant and cross-session read/write attempts: denied under non-owner runtime.
- Cross-action confused-deputy calls: a permission for one action cannot invoke another action's mutation.
- Revoked/expired/unknown key: fail closed.
- Direct SQL bypass of Handler: cannot create a state combination that violates required Receipt/Nonce/Transition/Outbox invariants.
- Role inheritance and default privileges: catalog assertions detect accidental authority expansion.

## 6. SECURITY DEFINER decision rule

Do not introduce SECURITY DEFINER simply to bypass RLS or simplify a Handler. If a SECURITY DEFINER boundary is proposed:
1. Identify the exact capability and why SECURITY INVOKER cannot safely perform it.
2. Threat-model the owner role, call graph, search_path, object qualification and nested helpers.
3. Grant only the minimum table/column privileges.
4. Keep owner NOLOGIN/NOSUPERUSER/NOBYPASSRLS/NOINHERIT and non-owner of protected tables.
5. Revoke PUBLIC EXECUTE and grant only exact signatures to exact principals.
6. Add catalog and confused-deputy negative tests.
7. Obtain explicit Architecture and Security acceptance.

No such approval is granted by this document.

## 7. Gate conclusion

G9 remains OPEN. Existing PR #13 role/RLS evidence is useful reference material; v2alpha2 helper tests do not prove an accepted database permission boundary. Do not widen Runtime privileges or change security mode to get integration tests passing.

## Change history

- 2026-11-03: Initial database permission and RLS audit.
