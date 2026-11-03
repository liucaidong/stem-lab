# PR #13–#20 Changed-File and Source Inventory

**Version:** 0.1.0  
**Status:** INVENTORY PARTIAL — G0 OPEN  
**As-of:** 2026-11-03

## 1. PR metadata result

GitHub PR search for `repo:liucaidong/stem-lab is:pr is:open is:draft` returned PR #13–#20. A corresponding closed-PR search did not return those PRs. PR #21 is also OPEN / DRAFT.

PR #20 head was independently fetched: `a9394870164bba5971ffa82b15c83d7e9b9cfc47`. PR #20 changed-file list contains one audit document. PR #20 Run #439 / ID `41578429173` is SUCCESS.

The current GitHub search wrapper does not expose the head SHA for each of PR #13–#19 in its normalized result. Do not invent those SHAs. Exact per-PR head SHA inventory remains a G0 subtask.

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

## 3. Source review coverage

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
- CI workflow steps for helper suites.

## 4. PR #13 immutability check

PR #21 changed-file inventory consists only of new Markdown documents under:
`docs/architecture/r03-52-7-3-11-3/pre-implementation/`.

No PR #13 reference implementation path is modified by PR #21. PR #13 itself remains OPEN / DRAFT and is not merged.

## 5. Remaining G0 work

- Obtain exact head SHA for PR #13–#19 and record per-PR CI run/commit mapping.
- Inspect current authoritative DEC-03/DEC-14/R535-OD3 records and record exact paths/versions/sign-off.
- Identify the authoritative Product Code Freeze artifact and owner; repeated README/architecture statements are supporting evidence but not a signed freeze decision.
- Complete repository-wide SQL/Worker Handler/document inventory and compare against all PR #13–#20 branches.
- Verify the new PR #21 latest head CI run after all current documentation commits.

## 6. Gate conclusion

G0 remains IN_PROGRESS. The changed-file inventory and key source assets are reviewed, but exact per-PR head SHA and authoritative governance artifact evidence remain incomplete.

## Change history

- 2026-11-03: Initial PR changed-file and source inventory.
