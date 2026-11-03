# PR #13–#20 Changed-File and Source Inventory

**Version:** 0.1.0  
**Status:** SOURCE PATH INVENTORY VERIFIED / G0 OPEN  
**As-of:** 2026-11-03

## 1. PR metadata result

GitHub PR search for `repo:liucaidong/stem-lab is:pr is:open is:draft` returned PR #13–#20. A corresponding closed-PR search did not return those PRs. PR #21 is also OPEN / DRAFT.

PR #20 head was independently fetched: `a9394870164bba5971ffa82b15c83d7e9b9cfc47`. PR #20 changed-file list contains one audit document. PR #20 Run #439 / ID `41578429173` is SUCCESS.

Exact PR-object metadata was fetched individually for PR #13–#20. All eight are OPEN / DRAFT and merged=false. Their head branch, HEAD SHA and latest observed CI mapping are recorded below; the PR base chain is contiguous from #13 through #20.

## 1.1 Exact PR HEAD and CI mapping

| PR | Head branch | HEAD SHA | Latest observed run | Result |
|---|---|---|---|---|
| #13 | `r03-52-7-3-6-resource-auth-debug2` | `c38f22d72a54934dbca80759db1dd85b3903163c` | #416 / `41496714183` | SUCCESS |
| #14 | `r03-52-7-3-11-auth-boundary-review` | `cda9a05ea0ea06b4435fb05b5d3815e0913dd3ef` | #420 / `41499382868` | SUCCESS |
| #15 | `r03-52-7-3-11-3-request-digest-v2alpha2` | `f5484b719e38a3c7145af26cf8470aab282058bb` | #429 / `41503109841` | FAILURE (historical; PostgreSQL digest syntax/conformance failure) |
| #16 | `r03-52-7-3-11-3-remediation-gate` | `f3e90cd85a21744f2e99ba4c82bd05c4e57083d0` | #430 / `41503709136` | SUCCESS (corrected SQL) |
| #17 | `r03-52-7-3-11-3-raw-claim-parser` | `2be9941b93b8dcf82d219c3cee660fe51d963ce4` | #431 / `41571959572` | SUCCESS |
| #18 | `r03-52-7-3-11-3-v2alpha2-db-verifier` | `1a8de570698a271a489f1dc7b0e60efb2c1966ab` | #437 / `41577147243` | SUCCESS |
| #19 | `r03-52-7-3-11-3-receipt-arbitration` | `8fb7dc5edc5954cd8b5ffc50bcce6833310550f6` | #438 / `41577279984` | SUCCESS |
| #20 | `r03-52-7-3-11-3-handler-integration-audit` | `a9394870164bba5971ffa82b15c83d7e9b9cfc47` | #439 / `41578429173` | SUCCESS |

The verified stack is #13 → #14 → #15 → #16 → #17 → #18 → #19 → #20 → PR #21. Changed-file lists were fetched for every PR; the eight lists contain 40 file entries in total (paths overlap across stacked PRs). PR #21's current audit branch is tracked separately in `21-pr-head-and-ci-evidence-matrix.md`.

## 2. Changed-file inventory

### PR #13 — Original reference implementation (11 files)

- `.github/workflows/contract-validation.yml`
- `contracts/examples/worker-claim-assignment.v1alpha1.valid.json`
- `contracts/examples/worker-resource-assertion.v2alpha1.valid.json`
- `contracts/worker-claim-assignment.schema.v1alpha1.json`
- `contracts/worker-job-lease.schema.v2alpha1.json`
- `contracts/worker-resource-assertion.schema.v2alpha1.json`
- `docs/architecture/R03.52.7.3.10-resource-authorization-security-evidence-and-acceptance-review.md`
- `docs/architecture/R03.52.7.3.6.1-job-rooted-assertion-and-lease-contract.md`
- `docs/architecture/R03.52.7.3.6.2-3.6.8-postgresql-resource-authorization-reference.md`
- `scripts/test_postgres_resource_scoped_authorization.py`
- `scripts/test_resource_assertion_contract.py`

### PR #14 — Authorization boundary / Store benchmark (2 files)

- `docs/architecture/R03.52.7.3.11-production-authorization-boundary-review-and-full-store-workload-benchmark.md`
- `docs/architecture/R03.52.7.3.11.1-verifier-function-ownership-grant-and-rls-inventory.md`

### PR #15 — Request Digest v2alpha2 (18 files)

- `.github/workflows/contract-validation.yml`
- `contracts/examples/worker-request-digest.v2alpha2.golden.json`
- `contracts/examples/worker-request-digest.v2alpha2.unicode.golden.json`
- `contracts/examples/worker-request-envelope.v2alpha2.valid.json`
- `contracts/examples/worker-resource-assertion.v2alpha2.invalid.json`
- `contracts/examples/worker-resource-assertion.v2alpha2.valid.json`
- `contracts/worker-resource-assertion.schema.v2alpha2.json`
- `docs/architecture/R03.52.7.3.11.3.1-request-digest-contract-gap-audit.md`
- `docs/architecture/R03.52.7.3.11.3.10-request-digest-threat-model-and-residual-risk-register.md`
- `docs/architecture/R03.52.7.3.11.3.12-request-digest-evidence-and-acceptance-status.md`
- `docs/architecture/R03.52.7.3.11.3.2-request-envelope-operation-binding-and-idempotency.md`
- `docs/architecture/R03.52.7.3.11.3.3-canonicalization-adr-candidate.md`
- `docs/architecture/R03.52.7.3.11.3.5-trusted-normalization-and-signer-integration.md`
- `docs/architecture/R03.52.7.3.11.3.6-postgresql-independent-digest-verification-design.md`
- `runtime/request_digest_v2alpha2.py`
- `scripts/test_postgres_request_digest_v2alpha2.py`
- `scripts/test_request_digest_v2alpha2.py`
- `sql/request-digest-v2alpha2.sql`

### PR #16 — PostgreSQL digest conformance correction (1 file)

- `sql/request-digest-v2alpha2.sql`

### PR #17 — Strict raw Claim JSON parsing (2 files)

- `scripts/test_postgres_request_digest_v2alpha2.py`
- `sql/request-digest-v2alpha2.sql`

### PR #18 — PostgreSQL v2alpha2 assertion verifier (2 files)

- `scripts/test_postgres_request_digest_v2alpha2.py`
- `sql/request-digest-v2alpha2.sql`

### PR #19 — Receipt arbitration (3 files)

- `.github/workflows/contract-validation.yml`
- `scripts/test_postgres_request_receipt_v2alpha2.py`
- `sql/request-receipt-v2alpha2.sql`

### PR #20 — Business Handler integration source audit (1 file)

- `docs/architecture/R03.52.7.3.11.3.13-business-handler-integration-source-audit.md`

## 3. Repository-wide source path inventory at PR #20 HEAD

The Git tree at PR #20 HEAD `a9394870164bba5971ffa82b15c83d7e9b9cfc47` was fetched recursively. GitHub returned 266 paths with `truncated=false`.

| Repository area | Total paths | Worker/authorization-relevant paths |
|---|---:|---:|
| `contracts/` | 81 | 16 |
| `runtime/` | 8 | 7 |
| `scripts/` | 43 | 19 |
| `sql/` | 4 (includes one directory) | 4 (3 SQL files + directory) |
| `docs/architecture/` | 94 | 35 |
| Other repository roots | 36 | Not classified in this Worker audit |
| **Total** | **266** | **81 scoped paths** |

### Worker/authorization contract assets (16)

Eight schema/policy files:
- `contracts/dlq-replay-plan.schema.v1alpha1.json`
- `contracts/worker-claim-assignment.schema.v1alpha1.json`
- `contracts/worker-job-lease.schema.v2alpha1.json`
- `contracts/worker-resource-assertion.schema.v2alpha1.json`
- `contracts/worker-resource-assertion.schema.v2alpha2.json`
- `contracts/worker-retry-policy.schema.v1alpha1.json`
- `contracts/worker-retry-policy.v1alpha1.json`
- `contracts/worker-store-protocol.schema.v1alpha1.json`

Eight example fixtures:
- `contracts/examples/dlq-replay-plan.valid.json`
- `contracts/examples/worker-claim-assignment.v1alpha1.valid.json`
- `contracts/examples/worker-request-digest.v2alpha2.golden.json`
- `contracts/examples/worker-request-digest.v2alpha2.unicode.golden.json`
- `contracts/examples/worker-request-envelope.v2alpha2.valid.json`
- `contracts/examples/worker-resource-assertion.v2alpha1.valid.json`
- `contracts/examples/worker-resource-assertion.v2alpha2.invalid.json`
- `contracts/examples/worker-resource-assertion.v2alpha2.valid.json`

### Runtime implementation assets (7)

- `runtime/dlq_replay.py`
- `runtime/request_digest_v2alpha2.py`
- `runtime/retry_policy.py`
- `runtime/store_protocol.py`
- `runtime/tenant_context.py`
- `runtime/worker_pool.py`
- `runtime/worker_runtime.py`

### Worker/authorization test and validation assets (19)

- `scripts/benchmark_store_driver_pool.mjs`
- `scripts/benchmark_store_driver_pool.py`
- `scripts/test_dlq_replay.py`
- `scripts/test_package_ingestion_worker_postgres.py`
- `scripts/test_postgres_request_digest_v2alpha2.py`
- `scripts/test_postgres_request_receipt_v2alpha2.py`
- `scripts/test_postgres_resource_scoped_authorization.py`
- `scripts/test_postgres_tenant_assertion_verifier.py`
- `scripts/test_postgres_tenant_ed25519_verifier.py`
- `scripts/test_request_digest_v2alpha2.py`
- `scripts/test_resource_assertion_contract.py`
- `scripts/test_store_protocol_contract.py`
- `scripts/test_tenant_context.py`
- `scripts/test_tenant_rls_trust_boundary_postgres.py`
- `scripts/test_worker_pool.py`
- `scripts/test_worker_retry_policy.py`
- `scripts/test_worker_runtime.py`
- `scripts/validate_dlq_replay.py`
- `scripts/validate_worker_retry_policy.py`

### SQL implementation assets

- `sql/package-ingestion-worker/R03.51-ingestion-worker.sql`
- `sql/request-digest-v2alpha2.sql`
- `sql/request-receipt-v2alpha2.sql`

### Worker/authorization architecture documents (35)

- `docs/architecture/R03.11-multitenant-security-and-threat-model.md`
- `docs/architecture/R03.31-package-digest-signature-provenance-adr-candidates.md`
- `docs/architecture/R03.32-runtime-event-consumer-outbox-replay-test-plan.md`
- `docs/architecture/R03.35-canonical-manifest-and-deterministic-package-digest.md`
- `docs/architecture/R03.38-event-consumer-inbox-outbox-and-replay-verification.md`
- `docs/architecture/R03.50-postgresql-ingestion-transaction-rls-and-outbox-integration.md`
- `docs/architecture/R03.51-ingestion-worker-lease-fencing-retry.md`
- `docs/architecture/R03.51-worker-job-state-machine.md`
- `docs/architecture/R03.51-worker-protocol-sequences.md`
- `docs/architecture/R03.52.1-worker-runtime-lifecycle-sequences.md`
- `docs/architecture/R03.52.1-worker-runtime-lifecycle-supervision.md`
- `docs/architecture/R03.52.1-worker-runtime-lifecycle-verification-report.md`
- `docs/architecture/R03.52.2-bounded-worker-poller-pool.md`
- `docs/architecture/R03.52.2-worker-pool-sequences.md`
- `docs/architecture/R03.52.2-worker-pool-verification-report.md`
- `docs/architecture/R03.52.4-worker-error-taxonomy-retry-policy.md`
- `docs/architecture/R03.52.4-worker-retry-policy-verification-report.md`
- `docs/architecture/R03.52.5-dlq-replay-authorization-audit.md`
- `docs/architecture/R03.52.5-dlq-replay-verification-report.md`
- `docs/architecture/R03.52.6.1-tenant-trust-boundary-threat-model.md`
- `docs/architecture/R03.52.6.2-tenant-isolation-architecture-options.md`
- `docs/architecture/R03.52.6.3-production-store-architecture.md`
- `docs/architecture/R03.52.7.1-database-tenant-assertion-verifier-spike.md`
- `docs/architecture/R03.52.7.2-store-protocol-unit-of-work-contract.md`
- `docs/architecture/R03.52.7.3.10-resource-authorization-security-evidence-and-acceptance-review.md`
- `docs/architecture/R03.52.7.3.11-production-authorization-boundary-review-and-full-store-workload-benchmark.md`
- `docs/architecture/R03.52.7.3.11.3.1-request-digest-contract-gap-audit.md`
- `docs/architecture/R03.52.7.3.11.3.10-request-digest-threat-model-and-residual-risk-register.md`
- `docs/architecture/R03.52.7.3.11.3.12-request-digest-evidence-and-acceptance-status.md`
- `docs/architecture/R03.52.7.3.11.3.6-postgresql-independent-digest-verification-design.md`
- `docs/architecture/R03.52.7.3.4-full-store-workload-benchmark-design.md`
- `docs/architecture/R03.52.7.3.5-resource-scoped-assertion-contract-resolution.md`
- `docs/architecture/R03.52.7.3.6.1-job-rooted-assertion-and-lease-contract.md`
- `docs/architecture/R03.52.7.3.6.2-3.6.8-postgresql-resource-authorization-reference.md`
- `docs/architecture/R03.7-runtime-state-command-worker-protocol.md`

This is a path inventory, not a claim that every one of the 81 scoped files received a line-by-line semantic review. Semantic review coverage is stated separately.

## 4. Source review coverage

Fetched and reviewed:
- v2alpha1 Claim Assignment and Resource Assertion schemas;
- v2alpha2 Resource Assertion schema;
- Python Request Digest implementation;
- PostgreSQL digest/verifier SQL;
- PostgreSQL digest test harness;
- PostgreSQL Receipt SQL and test harness;
- legacy PostgreSQL resource authorization harness;
- PR #14 authorization boundary and function/role/RLS inventories;
- PR #15 trusted normalization/signer design;
- CI workflow steps for helper suites;
- runtime/store_protocol.py, tenant_context.py, dlq_replay.py, worker_runtime.py, worker_pool.py and retry_policy.py;
- contracts/worker-store-protocol.schema.v1alpha1.json and the Worker Retry Policy schema/sample;
- scripts/test_worker_retry_policy.py, validate_worker_retry_policy.py and the Worker Runtime/Store/DLQ reference tests;
- R03.51-worker-job-state-machine.md, R03.52.4-worker-error-taxonomy-retry-policy.md and R03.52.5-dlq-replay-authorization-audit.md.

## 5. PR #13 immutability check

PR #21 changed-file inventory consists only of new Markdown documents under:
`docs/architecture/r03-52-7-3-11-3/pre-implementation/`.

No PR #13 reference implementation path is modified by PR #21. PR #13 itself remains OPEN / DRAFT and is not merged.

## 6. Remaining G0 work

- Inspect current authoritative DEC-03/DEC-14/R535-OD3 records and record exact paths/versions/sign-off.
- Identify the authoritative Product Code Freeze artifact and owner; repeated README/architecture statements are supporting evidence but not a signed freeze decision.
- Complete line-by-line semantic review of the 81 scoped source paths; recursive tree/path and PR changed-file inventories are complete, but not every file has been semantically reviewed.
- Verify the new PR #21 latest head CI run after all current documentation commits.

## 7. Gate conclusion

G0 remains IN_PROGRESS. The changed-file inventory and key source assets are reviewed, but exact per-PR head SHA and authoritative governance artifact evidence remain incomplete.

## Change history

- 2026-11-03: Initial PR changed-file and source inventory.
