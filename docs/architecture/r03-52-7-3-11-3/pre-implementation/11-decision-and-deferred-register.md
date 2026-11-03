# Architecture Decision and Deferred Decision Register

**Version:** 0.1.0  
**Status:** OPEN REGISTER / NO NEW DECISION ACCEPTED  
**As-of:** 2026-11-03

## 1. Decision governance

This register distinguishes:
- **ACCEPTED:** existing decision explicitly recorded as accepted, within its stated scope;
- **OPEN:** no final decision or approval recorded;
- **PROPOSED:** candidate design only;
- **DEFERRED:** intentionally excluded from this pre-implementation increment;
- **REJECTED:** explicitly prohibited by existing constraints.

A passing CI run does not accept a protocol, security or production architecture decision. Decision owner/sign-off must be recorded for each normative choice.

## 2. Existing decision status observed

| Decision | Current recorded state | Scope and evidence | Effect on this work |
|---|---|---|---|
| DEC-03 — Worker runtime/protocol | OPEN | R03.20 decision register; Python reference does not select production Worker runtime/protocol | Do not select production runtime or transport |
| DEC-04 — Production Store architecture | ACCEPTED at architecture-principle level | Language-neutral Store Protocol + explicit UOW; implementation, driver, pool and migration tooling remain open | Use as design constraint only; no adapter selection |
| DEC-14 — Deployment/provider | OPEN | R03.20 decision register; deployment topology/provider not selected | No production PostgreSQL topology/provider choice |
| DEC-19 — Tenant trust context | ACCEPTED target architecture only; production verification gates OPEN | R03.52.6 proposal and verification docs; decision owner names/sign-off not recorded in the proposal | Preserve target principles; do not infer production security acceptance |
| DEC-16 — DLQ replay Job ID strategy | OPEN | R03.52.5 requires a distinct new Job ID; ID generation strategy is explicitly injected/not selected | Do not allow caller-selected IDs or production replay until approved server-side ID strategy |
| DEC-30 — DLQ replay event/side-effect policy | OPEN | R03.52.5 lists event relay/replay side-effect policy as unresolved | Do not assume replay emits or suppresses events until contract is approved |
| R535-OD3 — Request digest/canonicalization | OPEN / PROPOSED | R03.52.7.3.11 document says exact canonicalization and signed Claim await approval | G1 blocked |
| R535-OD1 / OD4 / OD6 | OPEN in PR #14 recorded decision baseline | PR #14 body explicitly records OD1/OD3/OD4/OD5/OD6 as open; exact titles and current canonical register state still need source-path confirmation | Keep all related gates open until verified |
| R535-OD5 — Verifier helper-role boundary | OPEN | Prior authorization review requires capability-role experiment and catalog evidence | G9 blocked |
| Product Code Freeze | ACTIVE | Repeatedly recorded in README, R03.52.6 verification and R03.52.7.3.11 docs; no separate signed freeze decision artifact identified in current audit | No business code implementation or P3.17 |
| P3.17 | OUT OF SCOPE | Repeated project baseline constraint | Must not start |

DEC-03/DEC-14/R535-OD3 are explicitly protected by the task. This register does not attempt to change them.

## 3. Proposed decisions requiring explicit acceptance

| ID | Proposed decision | Rationale | Dependencies | Decision owner | State |
|---|---|---|---|---|---|
| ADR-PRE-01 | A v2alpha2 action entry must dispatch to exactly one verifier based on an explicit contract discriminator; no fallback | Prevent downgrade and ambiguous verifier paths | Claim schema, legacy behavior matrix | Architecture + Security | PROPOSED |
| ADR-PRE-02 | Digest arguments and mutation parameters derive from one immutable typed action binding | Eliminate digest/SQL argument substitution | G1, G4 | Protocol + Security + action owner | PROPOSED |
| ADR-PRE-03 | Receipt/Nonce/resource/event writes are one caller-owned transaction for mutating actions | Prevent partial business state | G5–G8, G10 | Architecture + Database | PROPOSED |
| ADR-PRE-04 | Errors that invalidate the write set abort the outer transaction; no broad catch-and-return | Avoid partial commit hidden behind false/null | G7, G10 | Database + Runtime | PROPOSED |
| ADR-PRE-05 | Broker publish occurs after durable Outbox dispatch claim commits | Preserve transactional boundary and at-least-once delivery semantics | Outbox consumer contract | Architecture + Messaging | PROPOSED |
| ADR-PRE-06 | Keep v2alpha2 verifier invoker-security by default; any SECURITY DEFINER requires a separate threat model and role design | Avoid privilege expansion by convenience | G9 | Security + Database | PROPOSED |
| ADR-PRE-07 | Nonce uniqueness must prevent cross-version replay without changing legacy semantics | Prevent replay downgrade | G2, G6 | Security + Protocol | PROPOSED |
| ADR-PRE-08 | Complete is the first v2alpha2 business vertical slice; no broad framework before evidence | Minimize speculative abstraction | G12 | Architecture | PROPOSED |
| ADR-PRE-09 | Keep `worker.dlq.replay` fail-closed until action args/provenance and source-DLQ/new-Job/audit UOW are accepted | Digest map currently has empty args; R03.52.5 preflight is plan-only | G2/G13 | Architecture + Worker + Security + Database | PROPOSED |

## 4. Deferred decisions

| ID | Deferred topic | Why deferred | Re-entry condition |
|---|---|---|---|
| DEFER-01 | Production Store adapter / driver / pool | DEC-03/DEC-14 and deployment evidence remain open; not needed to define disposable contract | Separate approved technology decision and controlled full-workload benchmark |
| DEFER-02 | Production PostgreSQL provider/topology | Deployment/provider decision not selected | DEC-14 approval and security/data residency review |
| DEFER-03 | Production key custody/HSM/KMS operations | No production issuer enrollment/custody architecture accepted | G3 threat model and operational key lifecycle decision |
| DEFER-04 | Capability-specific SECURITY DEFINER role split | Prior review recommends experiment but no accepted role topology | Disposable least-privilege experiment + catalog evidence + Security approval |
| DEFER-05 | DLQ Replay v2alpha2 handler | Digest helper recognizes `worker.dlq.replay` with empty args, but R03.52.5 requires reason/request identity, trusted actor/policy provenance and atomic source-DLQ/new-Job/audit writes; preflight is plan-only | Explicit scope decision, typed binding/provenance, trusted authorization and production UOW; reject action before writes until then |
| DEFER-06 | Broker implementation and consumer inbox | Outbox contract requires at-least-once and consumer dedup, but provider not selected | Messaging architecture decision and consumer integration tests |
| DEFER-07 | Production retention/archival/cleanup | Nonce/Receipt retention policies not accepted | Data lifecycle, audit and compliance review |
| DEFER-08 | Production deployment readiness | Explicitly outside current stage | All product/security/operational gates and explicit release approval |

## 5. Rejected shortcuts

- Lowering transaction isolation or deleting uniqueness constraints to eliminate contention.
- Weakening RLS or granting broad Runtime table privileges to make tests pass.
- Treating caller-controlled GUCs, tenant IDs or temp tables as trusted authorization context.
- Adding SECURITY DEFINER without a threat model, fixed search_path, least-privilege owner and catalog tests.
- Treating helper CI as Handler/UOW acceptance.
- Treating PostgreSQL conformance as production deployment approval.
- Modifying legacy v1alpha1/v2alpha1 behavior without compatibility approval.

## 6. Gate conclusion

G2, G3, G7, G9 and G14 remain blocked by OPEN decisions. No new architecture or security decision is accepted by this register.

## Change history

- 2026-11-03: Initial decision/deferred register.
