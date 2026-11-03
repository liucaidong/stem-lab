# R03-SCH-04.3 — PR #29 PostgreSQL 18 Upgrade Audit

## 1. Decision

<badge>BLOCKED — DO NOT MERGE</badge>

PR #29 must remain open and unmerged until its build recipe, test matrix, static policy, and target version are corrected and a complete CI run passes on the exact PR head SHA.

This is a major PostgreSQL version transition, not a routine image refresh.

## 2. PR identity and CI evidence

| Field | Observed |
|---|---|
| PR | #29 |
| Title | `build(deps): bump postgres from 17.11 to 18.4 in /scripts/docker` |
| State | open |
| Head SHA | `0da65df7e40832d1bd9116febda35c8f3e2a7803` |
| Base SHA | `8e749b55899d3626e39a31e1e438e3db682f5219` |
| Changed files | 1 |
| Run ID | `41722065653` |
| Run conclusion | cancelled |
| Jobs returned | 0 |
| Head check-runs | 0 |
| Combined status | pending |
| Mergeable state | blocked |

Cancelled is not success. No target-version integration test has passed on this PR head.

## 3. Exact PR diff

The only changed line is the Dockerfile base image:

```diff
-FROM postgres:17.11@sha256:0b81cec82228160abfa753aeaad0609b709eb26eeb950f2e404ad2326e1cc370
+FROM postgres:18.4@sha256:a02db8cac496f15b094798a38254f14d6e00741f709360e5e00bb6668ea31636
```

No other build input, PGDG package, `pg_config` path, workflow service image, test matrix, or policy fixture is changed.

## 4. Critical build incompatibility

The current main Dockerfile and PR #29 Dockerfile still contain all of the following PostgreSQL 17-specific inputs:

- `PGDG_SERVER_DEV_VERSION=17.11-1.pgdg13+2`
- `postgresql-server-dev-17`
- package filename `postgresql-server-dev-17_...`
- `/usr/lib/postgresql/17/bin/pg_config`
- `make PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config`
- installation into PostgreSQL 17's PGXS directories.

The PR changes only the base runtime image to PostgreSQL 18.4. Therefore the extension is still compiled and installed for PostgreSQL 17, while the image's server is PostgreSQL 18.4. The PostgreSQL 18 server will not load a PostgreSQL 17 extension binary/control installation from the PG17-specific paths. The tenant verifier test calls `CREATE EXTENSION pgsodium`; this image is not a coherent PG18 pgsodium build.

This is a static, deterministic version-alignment defect; it does not require executing the PR to identify it.

Required alignment if the intended test image is PG18:
- PG18 server development package and exact package version;
- PG18 package filename and SHA-256;
- PG18 `pg_config` path;
- PG18 PGXS installation directories;
- Dockerfile naming and build-step labels;
- policy validator and negative tests;
- exact image digest for the selected supported PG18 patch;
- target-version integration test.

## 5. pgsodium upstream compatibility evidence

The extension version remains `pgsodium 3.1.11`; its release asset SHA-256 remains unchanged:

`c8fef093d6d3afe859b03abcf7f598e9fce4298f7bfff283434bc300cba203ab`

The upstream pgsodium v3.1.11 README states that pgsodium 3.0+ requires PostgreSQL 14 or later. More specifically, the upstream v3.1.11 `test.sh` default test matrix includes PostgreSQL `14.19 15.14 16.10 17.6 18.0`.

Sources:
- [pgsodium v3.1.11 README](https://github.com/michelp/pgsodium/blob/v3.1.11/README.md)
- [pgsodium v3.1.11 test.sh](https://github.com/michelp/pgsodium/blob/v3.1.11/test.sh)
- [pgsodium v3.1.11 release and asset digest](https://github.com/michelp/pgsodium/releases/tag/v3.1.11)

This is positive upstream compatibility evidence for PostgreSQL 18.0. It does **not** validate this repository's PG18.4 Dockerfile, because the local build still targets PG17 headers and PGXS paths. The local Docker build and tenant verifier must be tested after the build inputs are aligned.

## 6. Target patch level

The official PostgreSQL versioning page observed during this audit lists:
- PostgreSQL 18 current minor: 18.6
- PostgreSQL 17 current minor: 17.11

PR #29 proposes 18.4, which is behind the currently listed PostgreSQL 18 patch release. The PR should not be merged as-is even if its build recipe is corrected; the target digest should be selected for the currently approved patch level after verification.

Source: [PostgreSQL versioning policy](https://www.postgresql.org/support/versioning/)

## 7. SQL migration and tenant verifier review

Repository source inspected:
- `sql/package-ingestion-worker/R03.51-ingestion-worker.sql`
- `scripts/test_postgres_tenant_ed25519_verifier.py`
- `scripts/test_postgres_tenant_assertion_verifier.py`
- `scripts/test_postgres_transaction_rls.py`

Observed:
- The R03.51 reference DDL uses ordinary relational constraints, JSONB, timestamps, indexes, RLS policies, and tenant-scoped keys.
- The Ed25519 verifier test calls `CREATE EXTENSION pgsodium`, generates Ed25519 keypairs, invokes `crypto_sign_verify_detached`, and exercises tenant RLS through a non-superuser runtime role.
- The tenant assertion verifier test exercises pgcrypto HMAC and RLS.
- The transaction/RLS test exercises RLS, role switching, transaction-local GUCs, composite foreign keys, Inbox/Outbox atomicity, and `FOR UPDATE SKIP LOCKED`.

No PostgreSQL-17-only SQL syntax was identified in the inspected reference DDL/test paths. This is not a complete migration compatibility certification: the PR does not run these tests against PostgreSQL 18.4, and the repository currently has only the listed R03.51 SQL reference file in that directory.

## 8. Workflow and static policy mismatch

The main workflow still declares the PostgreSQL service image as PostgreSQL 17.11. The static policy validator explicitly requires:
- the PostgreSQL service image to match 17.11 and its digest;
- the pgsodium Dockerfile base image to match 17.11;
- PGDG development packages to match the locked 17.11 recipe.

The current PR changes only the Dockerfile base image. If the cancelled run had reached the static policy step, the Dockerfile pin check would reject it. This is a predicted result from source inspection, not an observed run conclusion.

The workflow also labels the pgsodium image build as PostgreSQL 17.11. The PR does not update that label or introduce a PG17/PG18 test matrix.

## 9. Major-version migration distinction

PR #29 changes a CI Dockerfile; it does not itself demonstrate a production database data migration. No production data-volume migration is present in this PR.

If this change is intended to represent a production PostgreSQL major migration, PostgreSQL 18 documentation requires a planned dump/restore, `pg_upgrade`, or logical replication path. Replacing the container image tag alone is not a data migration.

Sources:
- [PostgreSQL 18 release notes — migration](https://www.postgresql.org/docs/18/release-18.html)
- [PostgreSQL 18 pg_upgrade](https://www.postgresql.org/docs/18/pgupgrade.html)

## 10. Required remediation and acceptance

1. Select and verify a current PostgreSQL 18 patch image digest.
2. Align all server development packages and `pg_config` paths to PG18.
3. Preserve the existing PostgreSQL 17 test path during transition or explicitly define the intended supported matrix.
4. Update workflow service/test matrix and Docker build labels.
5. Update static policy and its negative tests to accept the new approved version without weakening SHA/digest checks.
6. Build the image and prove `pgsodium` is installed into the PostgreSQL 18 extension directories.
7. Run the complete tenant Ed25519 verifier and RLS tests against the target PostgreSQL 18 image.
8. Verify pgsodium extension creation, crypto verification, RLS denial paths, and cleanup.
9. Record exact image digest, Docker build log, workflow Run ID, Job conclusions, and PR head SHA.
10. Require the complete `CI result` check to succeed before considering merge.

**Final PR #29 verdict: REJECT CURRENT PATCH / REQUEST CORRECTION. No merge authorization.**
