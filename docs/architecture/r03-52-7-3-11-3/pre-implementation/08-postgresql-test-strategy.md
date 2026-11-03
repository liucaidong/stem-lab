# PostgreSQL Integration Test Architecture and Evidence Plan

**Version:** 0.1.0  
**Status:** TEST STRATEGY PROPOSAL / NOT ACCEPTED  
**As-of:** 2026-11-03  
**Gate:** G11 OPEN

## 1. Existing CI topology

The PR #20 branch workflow `.github/workflows/contract-validation.yml` defines two jobs:

### validate-contracts
- Ubuntu runner.
- PostgreSQL 17 service container.
- Python 3.13 with pinned contract-validation requirements.
- Runs the contract validator and multiple reference harnesses.
- Includes Python v2alpha2 typed digest/golden-vector tests.
- Includes PostgreSQL v2alpha2 Receipt arbitration/concurrency harness using the PostgreSQL service.

### tenant-ed25519-verifier
- Ubuntu runner.
- Python 3.13 and pinned Psycopg/asyncpg clients.
- Builds PostgreSQL 17.11 with pgsodium 3.1.11.
- Runs the Ed25519 verifier test, PostgreSQL v2alpha2 digest verifier harness, and legacy resource authorization/RLS/nonce harness.
- Runs a Store driver/pool smoke benchmark.

This is useful infrastructure for isolated conformance tests. It is not an integrated v2alpha2 Handler/UOW test suite.

## 2. Existing test assets and proof boundaries

| Test asset | Current purpose | What it can prove | What it does not prove |
|---|---|---|---|
| `scripts/test_request_digest_v2alpha2.py` | Python typed codec and golden vectors | Python canonical byte/digest behavior and action argument validation | PostgreSQL equivalence or Handler mutation binding |
| `scripts/test_postgres_request_digest_v2alpha2.py` | Disposable PostgreSQL digest/verifier conformance | PostgreSQL helper behavior against selected Python vectors; raw signature/duplicate-key/argument mismatch cases | Full SQL asset parse validity; action Handler integration; production roles |
| `scripts/test_postgres_request_receipt_v2alpha2.py` | Receipt helper tests | Unique-key arbitration, same/different digest outcomes, terminal finalization, two-connection first use and Receipt-only outer rollback | Identity-consistent replay today; integrated Job/Nonce/Transition/Outbox atomicity |
| `scripts/test_postgres_resource_scoped_authorization.py` | Legacy resource authorization reference | Existing legacy Claim/Job/Receipt/DLQ/Outbox paths, RLS, nonce, owner/epoch/lease fencing and concurrency | v2alpha2 dispatch/Receipt/Nonce/UOW integration |
| `scripts/test_postgres_tenant_assertion_verifier.py` | Earlier tenant verifier boundary | Reference tenant verifier and role/RLS behavior | v2alpha2 business actions |
| `scripts/test_postgres_tenant_ed25519_verifier.py` | Ed25519 verifier reference | Database-side Ed25519 behavior in disposable pgsodium fixture | Trusted production issuer/key custody or v2alpha2 Handler UOW |
| `scripts/test_store_protocol_contract.py` | Adapter-neutral Store/UOW contract | Protocol-level conformance assertions | Actual PostgreSQL action transactions |

## 3. Test harness reuse strategy

Reuse the existing disposable PostgreSQL harness patterns:
- unique schema suffix per run;
- explicit teardown in finally blocks;
- deterministic fixture issuer and generated ephemeral keypair;
- independent connections for concurrency;
- explicit database encoding and extension/version checks;
- role creation and catalog assertions where security is under test;
- outer transaction control by the test caller;
- before/after persisted-state snapshots from a separate connection.

Do not duplicate the large PR #13 fixture wholesale for every action. Extract only after contracts are stable:
1. common PostgreSQL service/connection lifecycle;
2. schema and role bootstrap;
3. signer/key fixtures;
4. claim/envelope builders with strict serialization;
5. multi-connection barrier helpers;
6. state snapshot readers;
7. catalog privilege assertions;
8. assertion helpers for exact row equality/absence.

The extraction itself must be tested against the existing PR #13 fixture and must not alter its reference semantics.

## 4. Required test layers

### Layer 1 — Pure contract tests
- JSON Schema validation and unknown/missing/null/type cases.
- Python typed encoding and strict JSON parser.
- Golden vector generation and independent verification.
- Action-specific argument validation.

### Layer 2 — PostgreSQL helper conformance
- Strict raw JSON parsing and duplicate key rejection.
- Ed25519 over exact raw payload bytes.
- Digest recomputation and tampered-argument rejection.
- Receipt unique-key arbitration and terminal replay.
- Catalog assertions for helper function identity/permissions.

### Layer 3 — Handler integration
- Explicit version dispatch and exactly-one-verifier call path.
- Claim-to-resource identity binding.
- Digest arguments and mutation values from the same typed binding.
- Receipt + Nonce + Job/Session + Transition + Outbox (+ DLQ) same transaction.
- Typed error propagation to outer transaction.
- Same-request replay does not repeat mutation.

### Layer 4 — Concurrency
- Multi-connection same-key/same-digest first request.
- Same key/different digest.
- Same operation ID/different key.
- Same nonce across actions/tenants/versions.
- Competing Job owner/epoch/lease updates.
- Competing Session revision changes.
- Outbox dispatch lease reclaim and stale ack.
- Deadlock/serialization classification and full-transaction retry.

### Layer 5 — Security
- Runtime role cannot bypass Handler or write protected rows directly.
- Cross-tenant/session/owner/epoch denial.
- PUBLIC EXECUTE, role inheritance, schema CREATE and search_path attacks.
- RLS forced/enabled and correct non-owner execution.
- Confused-deputy cross-action tests.
- Key rotation/revocation/unknown-key behavior.

### Layer 6 — Rollback and persisted-state
- Snapshot all involved tables before operation.
- Inject failure at each write boundary in a disposable harness only after prerequisite contracts accepted.
- Trigger outer caller rollback.
- Compare exact primary-key sets and row values after rollback.
- Distinguish committed business terminal failures from infrastructure aborts.

## 5. Golden Vector governance

Every vector must include:
- vector ID and version;
- exact UTF-8 Request Envelope JSON;
- canonical typed bytes (hex and/or Base64URL);
- digest algorithm and digest;
- operation action and argument schema;
- expected accept/reject result;
- generating implementation/version;
- independent verifier result.

Never hand-copy a digest while changing operation_id, resource_id, tenant, action or any other field included in the envelope. Test generators must recompute the digest from the full envelope.

## 6. Test evidence manifest

CI should publish a machine-readable summary per job:
- commit SHA;
- PostgreSQL server version and encoding;
- extension names/versions;
- Python and driver versions;
- test file and test case IDs;
- role used by each test;
- pass/fail counts;
- concurrency connection count;
- snapshot comparison outcome;
- whether the test is helper-level, Handler integration, concurrency, security or rollback.

A green job must not be summarized as broader proof than its executed test layer.

## 7. Immediate test gaps to close

1. Correct PR #19 Receipt replay fixtures so the same request retains the same operation_id and digest.
2. Add negative tests that pair a changed operation_id/resource identity with the original digest.
3. Add an assertion that the entire SQL file has no orphan function-body fragments; the current digest harness extracts function definitions up to the first terminator and does not parse trailing content.
4. Add explicit test invocation proof for all required v2alpha2 helper suites in CI.
5. Add a Handler integration test that verifies exact digest/mutation parameter binding.
6. Add a Nonce Ledger test across assertion versions and independent connections.
7. Add complete write-set snapshots and outer-transaction rollback.
8. Add catalog assertions for v2alpha2 helper grants/ownership/RLS.
9. Add an end-to-end `worker.job.complete` test before extending to the other actions.

## 8. What the current CI success means

PR #18/#19 helper-level CI success is valid evidence that the executed helper test cases passed in their disposable environments. It does not mean:
- the helpers are called by business action entry points;
- every action uses the v2alpha2 verifier;
- the digest is tied to actual mutation values;
- a durable v2alpha2 nonce is consumed;
- the full Job/Session/Receipt/Transition/Outbox/DLQ write set is atomic;
- least-privilege production grants are approved;
- a production database deployment is safe.

## 9. Gate conclusion

G11 remains OPEN. Existing PostgreSQL service and pgsodium CI jobs are reusable, but the integrated Handler/UOW, cross-version, catalog-security and full persisted-state rollback suites do not yet exist.

## Change history

- 2026-11-03: Initial PostgreSQL test strategy and proof-boundary inventory.
