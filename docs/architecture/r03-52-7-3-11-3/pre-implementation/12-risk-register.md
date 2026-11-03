# Pre-Implementation Risk Register

**Version:** 0.1.0  
**Status:** OPEN  
**As-of:** 2026-11-03

| Risk ID | Risk | Impact | Likelihood | Current controls/evidence | Required mitigation | Owner | State |
|---|---|---|---|---|---|---|---|
| RISK-01 | Digest arguments can diverge from actual SQL mutation parameters | Signed request may authorize different data than persisted | High | Independent digest helper only; PR #20 audit explicitly records missing binding | Single typed binding; substitution tests for every action | Protocol + Security | OPEN |
| RISK-02 | Legacy and v2alpha2 verifier paths lack common explicit dispatch | Downgrade or cross-version authorization ambiguity | High | Separate legacy verify_v2/authorize_v2 and v2alpha2 verifier functions | Fail-closed version dispatch and compatibility matrix | Security | OPEN |
| RISK-03 | v2alpha2 has no integrated durable Nonce Ledger | Assertion replay across handlers/versions | High | Legacy nonce ledger only; v2alpha2 helper path does not consume it | Shared uniqueness policy, same-tx consumption, cross-version tests | Security + Database | OPEN |
| RISK-04 | Receipt fixture changes operation_id while holding digest constant | Tests overstate replay correctness; identity/digest tuple is inconsistent | High | PR #19 helper tests and PR #20 audit | Correct fixtures and add negative identity mismatch tests | Test + Protocol | OPEN |
| RISK-05 | Receipt is not atomic with Job/Session/Nonce/Transition/Outbox | Partial durable state or duplicate effects | Critical | Receipt-only concurrency and rollback helper tests | Integrated UOW with full state snapshots and outer rollback | Database + Runtime | OPEN |
| RISK-06 | Lock ordering across Job/Session/Receipt/Nonce/Outbox/DLQ is unproven | Deadlock, starvation, duplicate or partial outcome | High | Candidate Job-path sequence only | Full lock dependency graph and multi-connection stress tests | Database | OPEN |
| RISK-07 | Legacy SECURITY DEFINER owner has broad internal RLS reach | Confused deputy or high blast radius on future helper changes | High | PR #14/11.1 inventory: shared verifier owner and broad policies | Capability-role threat model, exact grants and catalog tests | Security + Database | OPEN |
| RISK-08 | v2alpha2 helper privileges are not accepted/tested under least-privileged roles; Receipt helpers are SECURITY INVOKER by default with no explicit PUBLIC EXECUTE revoke/exact grants in the SQL asset | Runtime may need broad direct table grants or helper invocation may fail; PUBLIC EXECUTE/direct table access may bypass intended boundary | High | Current helper tests execute under privileged fixture connection; Receipt reserve/finalize require underlying table privileges | Explicit INVOKER+minimal grants/RLS or capability-scoped DEFINER decision; Runtime role negative tests and catalog assertions | Security + Database | OPEN |
| RISK-09 | SQL digest asset contains orphan duplicate function fragments | Standalone execution may fail; test extraction can hide malformed trailing content | High | Blob SHA and full source structure inspected; six CREATE FUNCTION declarations vs nine terminators | Remove orphan fragments and add full-file SQL parse test | Database + Test | OPEN |
| RISK-10 | Schema/SQL/Python Claim boundary limits differ; iat/exp have no explicit schema upper bound but SQL casts to bigint | Cross-language acceptance drift, raw cast errors and inconsistent verifier outcomes | High | Claim parity audit shows unbounded schema timestamp fields and bigint casts without normalized overflow mapping | Single field/range contract, explicit safe numeric bounds and stable overflow error classes with negative golden vectors | Protocol + Database | OPEN |
| RISK-11 | Pending Receipt recovery semantics are undefined | Permanently pending or unsafe recovery after ambiguous failure | Medium/High | Helper returns pending state; no recovery policy | Define pending visibility, ownership/timeout and reconciliation | Architecture | OPEN |
| RISK-12 | Error handlers return false/NULL in legacy paths | Caller may commit earlier statements after hidden local failure | High | Legacy functions contain broad exception handlers | v2alpha2 typed errors and outer rollback proof | Database | OPEN |
| RISK-13 | Action map includes DLQ Replay outside requested eight-action scope | Unclear contract ownership and incomplete acceptance | Medium | Python/SQL digest action maps include worker.dlq.replay | Explicitly defer or formally include separate design | Architecture | OPEN |
| RISK-14 | Outbox delivery semantics may be confused with exactly-once effects | Duplicate or out-of-order external side effects | High | Prior architecture states at-least-once delivery and consumer dedup requirement | Event ID dedup, inbox, ordering and lease fencing tests | Messaging | OPEN |
| RISK-15 | Product freeze and production decisions lack a single signed authoritative artifact in this audit | Accidental scope/authority drift | Medium | README and architecture docs repeat ACTIVE/OPEN status | Locate authoritative decision records and record owner/sign-off | Architecture governance | OPEN |
| RISK-16 | Retryability, delay and safe_message are signed action values without an accepted trusted policy source/version/bounds | Incorrect retry scheduling, policy bypass or non-deterministic replay | High | R03.52.4 Registry exists as a reference; WorkerRuntime accepts an injected classifier; FailureDecision/Store Fail carry no policy_version; delay ceilings differ across layers | Enforce trusted registry evaluation, pin policy version, derive outputs from persisted attempt budget, unify delay bounds and bind exact result to digest/mutation | Worker + Protocol + Security | OPEN |
| RISK-17 | Request Envelope/operation_arguments and Python strict JSON input lack a complete total size budget | Memory/CPU exhaustion and inconsistent ingress behavior | High | SQL Claim parser caps raw Claim at 16 KiB; separate operation_arguments has no total cap; Python parser has no explicit cap | Define and enforce transport/Claim/envelope/argument limits and maximum canonical bytes | Protocol + Runtime + Security | OPEN |
| RISK-18 | `worker.dlq.replay` is accepted by the digest action map with empty args while the replay plan requires unbound reason/request identity and no production UOW exists | Replay reason/identity tampering, duplicate Job creation or incomplete audit trail | High | R03.52.5 preflight is plan-only; v2alpha2 action tuple is empty; production transaction/auth issuer absent | Fail closed until typed arguments/provenance, trusted authorization and atomic source-DLQ/new-Job/audit transaction are accepted | Worker + Security + Database | OPEN |
| RISK-19 | v2alpha2 Receipt Reconcile has no read-only lookup helper; the only reserve helper inserts a pending Receipt when no row exists | Reconciliation can mutate Receipt state or fabricate a pending record instead of reporting missing | High | PR #19 SQL exposes insert-first reserve/finalize only; no SELECT-only operation_id lookup | Add a read-only, version-correct lookup; enforce no-create/no-finalize behavior and persisted-state tests | Protocol + Database + Security | OPEN |

## Highest-priority blockers

1. RISK-01 through RISK-06: protocol/compatibility/atomicity blockers.
2. RISK-07 through RISK-10: database privilege and cross-language contract blockers.
3. RISK-11 through RISK-19: operational semantics, retry-policy authority, DLQ replay binding, Receipt reconciliation, input-size and governance blockers.

## Risk acceptance rule

No Critical or High risk affecting signature binding, replay protection, tenant isolation, atomicity, authorization or compatibility may be accepted by merely documenting a workaround. Any residual risk acceptance requires an explicit named decision owner, impact rationale, compensating control, expiry/review date and test evidence.

## Change history

- 2026-11-03: Initial pre-implementation risk register.
