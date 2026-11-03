# R03.52.7.3.11.4 — Final Source Audit Report

**Status:** SOURCE INVENTORY VERIFIED / SEMANTIC AUDIT INCOMPLETE / IMPLEMENTATION BLOCKED  
**Audit baseline:** PR #20 HEAD `a9394870164bba5971ffa82b15c83d7e9b9cfc47`  
**PR under audit:** #21 HEAD `c0504a5f92a36d8a04dddfaef34b5f395561ff31`  
**As of:** 2026-11-03 (UTC+8)

## 1. Executive result

The repository inventory is complete and reproducible. The required line-by-line semantic audit of all 81 Worker/Authorization scoped paths is **not complete**. The audit therefore does not claim G0 PASS.

The source evidence already establishes multiple critical blockers. No v2alpha2 Business Handler, durable v2alpha2 Nonce Ledger, SELECT-only Receipt Reconcile helper, or complete v2alpha2 business Unit-of-Work is present. The current helper tests do not prove the required production transaction or least-privilege boundary.

**Conclusion: NOT READY FOR IMPLEMENTATION.** Product Code Freeze remains ACTIVE. No production code, production UOW, COMMIT fault injection, or merge is authorized by this report.

## 2. Repository inventory evidence

Recursive Git Tree at PR #20 HEAD returned 266 entries with `truncated=false`. The Worker/Authorization inventory is 81 paths: 16 contract assets, 7 Runtime assets, 19 scripts, 3 SQL assets, and 35 architecture documents. The inventory document is `18-pr-source-inventory.md`.

PR #21 changed-file inventory contains 34 Markdown files under this pre-implementation directory only. No PR #13 reference implementation path is changed by PR #21.

## 3. Semantic review coverage

| Area | Inventory | Reviewed evidence | Completion |
|---|---:|---|---|
| Contracts | 16 | v2alpha1/v2alpha2 assertion schemas, Store Protocol, Retry Policy, DLQ plan, digest/envelope fixtures | PARTIAL |
| Runtime | 7 | request_digest_v2alpha2.py, dlq_replay.py, retry_policy.py, worker_runtime.py, store_protocol.py; lifecycle/pool/context reviewed for boundary | PARTIAL |
| Scripts | 19 | digest, Receipt, Retry, DLQ, Store, Worker Runtime/Pool, tenant verifier/RLS, legacy resource authorization and ingestion-worker suites | PARTIAL |
| SQL | 3 | request-digest-v2alpha2.sql, request-receipt-v2alpha2.sql, legacy ingestion Worker SQL | PARTIAL |
| Architecture | 35 | R03.20, R03.52.4, R03.52.5, R03.52.6 trust/store docs, R03.52.7.2, R03.52.7.3.5, R03.52.7.3.11/.11.1 and PR #20 audit | PARTIAL |

The above rows identify inspected sources; they do not imply every line of every listed file has been reviewed. Remaining paths require an explicit per-file reviewer record with source SHA, symbol/line range, observed behavior, risk, action and verification evidence.

## 4. Confirmed findings

| Finding | Source path → symbol/line | Observed behavior | Violated / unproven contract | Risk / required action |
|---|---|---|---|---|
| SA-01 | `runtime/request_digest_v2alpha2.py:59-71` → `parse_json_strict` | Strict duplicate-key parsing, but no explicit raw input byte budget | Claim/Envelope input budget parity | Add transport/Claim/Envelope limits before parsing; test max/max+1 |
| SA-02 | `runtime/request_digest_v2alpha2.py:73-104` → `validate_envelope`, `canonical_request_bytes` | Envelope/action validation exists; no total canonical-byte budget; `_u32` caps at 0x7fffffff | R535-OD3 and cross-language size contract remain unapproved | Set practical per-surface and total byte budgets; align ADR and Python/SQL |
| SA-03 | `sql/request-digest-v2alpha2.sql:6-379`, :380-572 | Six function declarations but nine `$fn$;` terminators; orphan duplicated verifier fragments begin around lines 380, 443 and 510 | Complete SQL asset integrity | Repair entire SQL file; execute the complete asset in PostgreSQL CI |
| SA-04 | `scripts/test_postgres_request_digest_v2alpha2.py:16,24-26` | Test splits on CREATE FUNCTION and executes each extracted body up to first terminator | Full-file SQL syntax not tested | Add full-file execution test; do not let extraction hide trailing fragments |
| SA-05 | `sql/request-receipt-v2alpha2.sql:27-107` | Reserve is INSERT-first; missing key creates pending Receipt; no SELECT-only operation lookup exists | Read-only Reconcile/no-create invariant | Implement separate SELECT-only lookup; never call reserve from Reconcile |
| SA-06 | `sql/request-receipt-v2alpha2.sql:109-163` | Finalize takes receipt_id/status/outcome only; outcome is arbitrary JSONB | Tenant/action/resource/digest binding and bounded outcome | Add exact identity binding, closed outcome schema and size constraints |
| SA-07 | `sql/request-receipt-v2alpha2.sql:27-163`; `scripts/test_postgres_request_receipt_v2alpha2.py:38-85` | Functions default SECURITY INVOKER; SQL has no explicit PUBLIC revoke/exact grants/RLS; tests use configured privileged connection and autocommit | Least-privilege Runtime proof | Select and approve privilege model; add catalog and negative-role tests |
| SA-08 | `runtime/worker_runtime.py:27,60-158`; `runtime/retry_policy.py:11-90` | FailureDecision is directly constructible; arbitrary classifier injected; Registry use not enforced; no policy_version | Retry Policy authority | Trusted evaluator, pinned version, persisted attempt budget and digest/mutation binding |
| SA-09 | `runtime/dlq_replay.py:15-83` | Replay authorization, source state/counters, reason and new ID are caller-supplied preflight values | Trusted actor/source/limit/ID provenance and atomic replay | Keep action fail-closed until trusted authorization and atomic replay UOW exist |
| SA-10 | `contracts/worker-resource-assertion.schema.v2alpha2.json`; SQL verifier in `sql/request-digest-v2alpha2.sql:285-379` | Schema caps epoch/iat/exp at 2^53-1; SQL checks integer form but casts iat/exp to bigint without matching explicit upper bound; Python codec is not a Claim validator | Schema/SQL/Python parity and stable overflow errors | Define exact numeric domain; range-check numeric before bigint cast; normalize errors |
| SA-11 | `runtime/store_protocol.py:152-210`; `runtime/worker_runtime.py:60-158` | Store Protocol is an interface; WorkerRuntime calls independent facade methods; no production Adapter/UOW integration | v2alpha2 transaction atomicity | Implement only after approved complete write-set contract and entry gate |
| SA-12 | `docs/architecture/R03.52.7.3.5-resource-scoped-assertion-contract-resolution.md:303-342` | Exact assertion replay is rejected; business retry uses fresh nonce and same envelope/key/digest | Must preserve distinction | Ensure Nonce check precedes any Receipt success arbitration |

## 5. Retry-policy cross-layer discrepancies

- Registry uses floating-point seconds; legacy Store Fail uses floating-point seconds; v2alpha2 Fail uses integer microseconds; v2alpha2 Retry uses integer seconds.
- Registry schema/runtime has no absolute global maximum.
- Existing legacy Store and v2alpha2 Retry cap at 86,400 seconds; v2alpha2 Fail has no matching policy ceiling in its action validator.
- Registry and Store allow error_code up to 128 characters; v2alpha2 digest codec/SQL pattern permits 64.
- Registry/Store safe_message is capped at 512 characters; v2alpha2 digest action validator has no matching bound.
- FailureDecision and FailJobCommand do not carry policy_version.

## 6. Receipt and Nonce fixture defect

The Receipt test reserves `operation-1`, then calls the same tenant/action/idempotency key with `operation-retry` while reusing the same literal digest (test lines 41-58). Since operation_id is part of the Request Envelope digest, this is not a valid same-business-request reissue vector. Correct tests must keep the entire business envelope and digest identical, reissue only the Assertion with a fresh nonce/signature, and separately prove exact old-token replay returns ASSERTION_REPLAYED before Receipt arbitration.

## 7. Legacy reference versus v2alpha2 implementation

PR #13 and the R03.51 ingestion-worker PostgreSQL harness contain independently tested legacy/reference paths for nonce, lease fencing, Job/Session/Receipt/Transition/Outbox, rollback and concurrency. Those are useful reference evidence only. PR #20 source audit confirms the legacy `verify_v2/authorize_v2` path does not call the v2alpha2 verifier, digest, or Receipt functions. Legacy success cannot be promoted into v2alpha2 integration evidence.

## 8. Remaining audit work

1. Complete line-by-line semantic review of all 81 scoped paths, recording immutable blob SHA and line ranges.
2. Review all 35 architecture documents and the canonical decision/freeze records for authority and scope.
3. Verify every action's exact call graph, mutation set, lock order, failure mapping and test coverage.
4. Reconcile all findings with the source and test changes in a single reviewed batch.
5. Obtain independent Architecture, Security, Database and Worker owner signoffs.

## 9. Gate conclusion

G0 is **BLOCKED**: path inventory is complete, but full semantic review and authoritative approval evidence are not. The critical findings above independently block implementation. This report does not claim source audit closure or authorize production code.
