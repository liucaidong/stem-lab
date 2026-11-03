# R03.52.7.3.11.3 — Gap Register and Dependency Matrix

**Version:** 0.1.0  
**Status:** OPEN / SOURCE-DERIVED  
**As-of:** 2026-11-03  
**Decision owner:** Architecture + Security; protocol owner for canonicalization semantics.

## 1. Executive gap statement

The repository currently has independently tested v2alpha2 primitives, not a business-operation integration. The next safe activity is to close contracts and establish a disposable integration test design. It is not safe to begin production-shaped business Handler implementation while the following gaps remain unresolved.

## 2. Gap Register

| ID | Area | Source-backed finding | Required closure evidence | Severity | State |
|---|---|---|---|---|---|
| GAP-01 | Version dispatch | No shared action entry point selects exactly one legacy or v2alpha2 verifier | Fail-closed dispatch state machine + compatibility tests | Critical | OPEN |
| GAP-02 | Digest/mutation binding | Digest verifier accepts an operation-argument object separately; no call-site proof it is the same typed values used in SQL mutation | Handler contract derives digest and SQL from one typed local binding; tamper tests | Critical | OPEN |
| GAP-03 | Trusted signer | SQL verifier resolves an issuer key in disposable fixture; production issuer provenance, signer service, rotation/revocation and key custody are not accepted | Trust-boundary design, interfaces, threat model and key lifecycle tests | Critical | OPEN |
| GAP-04 | Action contracts | Digest helper has an action map, but there is no integrated typed Handler binding matrix for all actions | Per-action claim/resource/argument/lock/write/error/replay contract | Critical | OPEN |
| GAP-05 | Receipt integration | Receipt helper is independent of Job, Session, Nonce, Transition and Outbox | Same-transaction integration and full persisted-state snapshots | Critical | OPEN |
| GAP-06 | Receipt fixture identity | PR #20 audit records a replay fixture changing operation_id while holding a literal digest constant, although operation_id participates in the envelope | Same signed envelope replay fixture + changed-identity negative tests | High | OPEN |
| GAP-07 | v2alpha2 Nonce Ledger | Legacy nonce ledger is transaction-bound but no v2alpha2 durable ledger or cross-version coordination is integrated | Explicit uniqueness domain, consumption timing, retention and cross-version tests | Critical | OPEN |
| GAP-08 | Atomic UOW | No v2alpha2 complete Job/Session/Receipt/Nonce/Transition/Outbox write set | One transaction contract + outer rollback and persisted-state proof | Critical | OPEN |
| GAP-09 | Lock ordering | Candidate order exists in PR #20 audit, but no all-action lock graph or proof against cycles | Per-action lock graph and adversarial multi-connection tests | Critical | OPEN |
| GAP-10 | Database privileges | v2alpha2 helper privilege/RLS model is not accepted as production boundary; legacy fixture concentrates broad verifier authority | Role/ownership/EXECUTE/RLS/catalog matrix and negative tests | Critical | OPEN |
| GAP-11 | Failure semantics | Helper rollback tests do not define every business operation's durable state after each failure | Failure-to-table mutation matrix and state snapshot schema | Critical | OPEN |
| GAP-12 | Test architecture | Existing CI runs independent helper harnesses; no integrated Handler/UOW test is present | Reusable fixture design + test proof-boundary matrix + CI wiring plan | High | OPEN |
| GAP-13 | Complete vertical slice | Complete is not a single mandatory v2alpha2 complete-write-set entry path | End-to-end sequence, mutation inventory, state and security acceptance | Critical | OPEN |
| GAP-14 | Remaining actions | Fail/Retry/Renew/Dead Letter/Receipt reconcile/Outbox Dispatch/Ack lack v2alpha2 integrated designs | Action-by-action contracts and concurrency differences | High | OPEN |
| GAP-15 | Canonicalization approval | R535-OD3 and canonicalization ADR remain OPEN/PROPOSED | Formal approval of exact bytes, field set, limits and vectors | Critical | OPEN |
| GAP-16 | Production architecture | DEC-03 and DEC-14 remain OPEN; no production adapter/driver/pool/provider is selected | Separate approved decisions; not a prerequisite to disposable contract design unless directly required | Deferred | OPEN |
| GAP-17 | Code-freeze authority | Product Code Freeze ACTIVE; P3.17 OUT OF SCOPE | Explicit authorized freeze decision after all prerequisites | Critical | BLOCKED |
| GAP-18 | Claim validation parity | JSON Schema caps and SQL manual verifier checks differ; Python codec is not a full Claim validator; iat/exp lack explicit schema upper bounds but SQL casts to bigint, so overflow may escape as a raw DB error | Normative Claim field/range table, safe numeric bounds, normalized overflow errors and Schema/Python/SQL parity tests | Critical | OPEN |
| GAP-19 | Canonicalization size boundary | ADR says uint32; Python `_u32` and SQL int4send both effectively cap positive lengths at 2^31−1; operation_arguments has no total size cap | Align normative ADR with implementation range or implement full uint32 consistently; set maximum canonical bytes and per-field UTF-8 limits | High | OPEN |
| GAP-20 | Action argument bounds | result_ref/safe_message lack business-level bounds; error_code is 64 chars in v2alpha2 codec vs 128 in Retry Policy/Store; safe_message is 512 in Registry/Store but unbounded in v2alpha2; retryable/delay cross-field rules undefined | Per-action byte/range/policy constraints, shared error/message bounds and typed SQL parameter binding | High | OPEN |
| GAP-21 | Re-issued assertion semantics | Upstream contract distinguishes exact token replay from fresh-nonce retry with same business envelope/digest | Receipt/Nonce tests for exact replay, reissue, deadlock retry and ambiguous commit | Critical | OPEN |
| GAP-22 | Receipt store split / read-only reconciliation | Legacy receipts and request_receipts_v2alpha2 are separate; no v2alpha2 read-only lookup helper exists; reserve is insert-first and can create a pending Receipt if reused for reconcile | Version-correct SELECT-only lookup by target operation identity, no-create invariant, terminal/pending semantics and cross-version idempotency decision | Critical | OPEN |
| GAP-23 | Receipt helper security/outcome | Helper trusts caller identity/digest, finalization is receipt_id-only; functions default SECURITY INVOKER so Runtime needs direct Receipt table privileges; no explicit PUBLIC EXECUTE revoke/exact grants; outcome schema/size and RLS/grants are absent | Explicit INVOKER+minimal grants/RLS or capability-scoped DEFINER decision, exact identity comparison, outcome schema and catalog tests | Critical | OPEN |
| GAP-24 | Legacy action compatibility | Claim Assignment v1alpha1 and Resource Assertion v2alpha1 have distinct entry points and action semantics | Full unchanged legacy regression matrix and explicit v2alpha2-only dispatch | High | OPEN |
| GAP-25 | SQL asset integrity | Digest SQL file has six function declarations but nine function terminators; test extractor ignores trailing orphan bodies | Clean SQL asset and parse/run complete file in disposable PostgreSQL | High | OPEN |
| GAP-26 | Retry delay unit contract | Legacy Store uses retry_delay_seconds; v2alpha2 Fail digest uses retry_delay_micros | Canonical internal unit, checked conversion and policy bounds | High | OPEN |
| GAP-27 | Receipt fixture reissue coverage | PR #19 helper tests change operation_id while reusing literal digest; no fresh-nonce same-business-envelope test | Correct fixtures with recomputed digests and fresh assertion nonce semantics | High | OPEN |
| GAP-28 | Retry-policy authority | Fail/Retry digest args contain retryable/delay/safe_message values; WorkerRuntime accepts an injected classifier and does not enforce RetryPolicyRegistry use; FailureDecision/Store Fail carry no policy_version | Approved trusted evaluator, pinned policy version, persisted attempt inputs and digest-to-mutation binding | Critical | OPEN |
| GAP-29 | Retry-policy global bounds | Registry schema/runtime has no absolute maximum; legacy Store Fail and v2alpha2 Retry cap at 86,400 seconds, while v2alpha2 Fail accepts int64 microseconds | One approved global/per-code upper bound enforced consistently across Registry, Store, digest codec and SQL; boundary tests | High | OPEN |
| GAP-30 | Retry delay conversion | Registry uses float seconds, v2alpha2 Fail uses integer microseconds, v2alpha2 Retry uses integer seconds, legacy Store uses float seconds | Canonical unit, exact conversion/rounding/overflow rule and shared vectors | High | OPEN |
| GAP-31 | Input size budgets | SQL strict Claim parser caps raw payload at 16 KiB; Python strict JSON parser has no explicit input cap; operation_arguments are passed separately and have no total canonical-byte cap | Define transport, Claim, Request Envelope and operation_arguments byte budgets; enforce them before parsing/encoding/hashing | High | OPEN |
| GAP-32 | DLQ replay action binding | v2alpha2 digest map defines `worker.dlq.replay` with empty args, but R03.52.5 ReplayPlan requires stable request_id, reason, actor/policy audit provenance and distinct new_job_id; only preflight exists | Define field provenance and typed digest binding; derive actor/source state under trusted Claim/DB lock, generate new_job_id server-side, atomically create Job/increment replay_count/audit; fail closed until accepted | Critical | OPEN |

## 3. Dependency Matrix

| Work item | Depends on | Must precede |
|---|---|---|
| Protocol/Claim contract | Existing PR #15–#18 source; R535-OD3 approval | Version dispatch; action binding; verifier integration |
| Trusted Signer boundary | Issuer/key provenance decision; threat model | Verifier call path and key access grants |
| Version dispatch | Claim discriminator; legacy behavior inventory | Every action entry point |
| Action-specific typed binding | Frozen action schema; exact SQL mutation inventory | Digest recomputation and Handler implementation |
| Receipt semantics | Operation identity + digest contract | Receipt reserve/replay/finalize integration |
| Nonce contract | Version compatibility + issuer/kid/tenant/subject scope | Durable nonce consumption |
| Atomic UOW | Receipt + Nonce + action mutation + event contracts | Complete/Fail/Retry/etc. implementation |
| Lock graph | All action resource dependencies and unique-key arbitration | Concurrency test implementation |
| SQL security model | Role inventory + function call graph + RLS policy inventory | Grant/revoke and handler function implementation |
| Failure-state contract | UOW write set + error propagation model | R03.52.7.3.11.4 fault injection |
| PostgreSQL test strategy | All contracts above + reusable fixture inventory | Integrated CI suite |
| Complete vertical slice | G1–G11 accepted | PR for business implementation |
| Remaining action designs | Complete slice template + action-specific differences | Subsequent handler increments |
| Claim validation parity | Strict parser + schema + SQL/Python field/limit table | G1 acceptance |
| Canonicalization size boundary | R535-OD3 candidate, action argument bounds and typed encoder parity | G1 acceptance |
| Raw input size budgets | SQL strict parser, Python JSON parser and separately supplied operation_arguments | G1/G4 acceptance |
| DLQ replay typed binding and atomicity | R03.52.5 preflight + v2alpha2 action map + source DLQ/Job transaction | G2/G13 acceptance |
| Retry delay unit resolution | Existing Retry Policy Registry + legacy Store contract + v2alpha2 action schema | G4/G13 acceptance |
| Retry-policy authority and version pinning | R03.52.4 policy registry + v2alpha2 Fail/Retry action map + persisted attempt budget | G4/G13 acceptance |
| Retry-policy numeric bounds and conversion | Registry schema/runtime + seconds/microseconds action contracts | G1/G4/G13 acceptance |
| Receipt re-issuance and Nonce | R03.52.7.3.5 replay contract + Receipt uniqueness + cross-version threat model | G5/G6 acceptance |
| Receipt Reconcile | Legacy/v2alpha2 Receipt store split + action/resource identity + target digest semantics | G5/G6/G9 acceptance |
| Receipt helper security | Role/ownership/RLS design + exact typed binding + outcome schema | G5/G7/G9 acceptance |
| Cross-version business idempotency | Legacy compatibility baseline + Nonce uniqueness + version dispatch | G2/G5/G6 acceptance |
| Cross-audit / entry gate | All prior artifacts + independent review | G15 decision |

## 4. Current evidence versus inference

### Verified facts
- PR #18 and #19 CI runs #437/#438 were recorded SUCCESS in the PR #20 audit.
- PR #20 run #439 is SUCCESS.
- The v2alpha2 verifier and Receipt helper have independent PostgreSQL test harnesses.
- Existing legacy action paths use `verify_v2` / `authorize_v2`; PR #20 audit reports no calls from these paths to the v2alpha2 verifier or Receipt functions.
- Existing legacy nonce ledger has a primary key `(issuer, kid, nonce)` and binds rows to transaction/token context in the reference fixture.
- The workflow invokes the helper suites but does not contain an end-to-end v2alpha2 Handler/UOW test.
- v2alpha2 uses a separate request_receipts_v2alpha2 table; legacy receipt reconciliation reads the PR #13 receipts table.
- The v2alpha2 Receipt finalization helper takes receipt_id only; the helper SQL does not define an accepted RLS/role/outcome-schema boundary.
- The SQL digest asset contains orphan repeated function-body fragments after the active verifier definition; the current harness extracts declared function bodies and does not parse the trailing content.
- Claim Schema string/numeric limits are not all mirrored by the SQL verifier; the Python codec validates Request Envelopes/action arguments, not the complete Claim.
- PR #19 Receipt fixtures vary operation_id while reusing a literal digest; R03.52.7.3.5 distinguishes exact assertion replay from fresh-nonce retry of the same business envelope.
- The legacy Store Fail signature has no action arguments, while v2alpha2 Fail digest arguments include error_code/retryable/retry_delay_micros/safe_message; legacy Retry uses seconds.

### Design implications (not yet accepted decisions)
- A v2alpha2 Handler should construct digest arguments from the same typed local variables passed to mutation statements.
- A failed business operation should not permit a caller to commit a partial durable write set.
- Outbox broker I/O should remain outside the database transaction; durable event intent belongs inside it.
- Receipt reconciliation and Outbox-only operations likely require distinct lock paths from Job mutation operations.

## 5. Immediate closure order

1. G0: finish source inventory, exact PR/branch/CI/decision baseline and freeze evidence.
2. G1–G3: close protocol/digest semantics, version compatibility and signer trust boundary.
3. G4–G6: close action binding, Receipt and Nonce semantics.
4. G7–G10: close UOW, lock ordering, database privileges and failure state contracts.
5. G11–G13: close test architecture and action designs.
6. G14: independent architecture/security consistency review.
7. G15: accept only if every mandatory predecessor is ACCEPTED.

No step in this sequence authorizes production implementation by itself.
