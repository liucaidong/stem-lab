# R03.SCH.03 — P2 Supply-Chain Hardening Implementation Status

Date: 2026-11-03

## Baseline and PR topology

- P1 PR #27 remains open, Draft, and unmerged.
- P2 branch: security/r03-sch-03-p2, stacked on P1 PR #27.
- P2 does not modify main or change branch protection, required checks, repository settings, or Actions settings.

## P2 workstreams

| Workstream | Status | Evidence |
|---|---|---|
| P2.1 Python hash lock | Implemented | 26 exact package versions; every package has SHA-256 hashes; clean Linux/amd64 CPython 3.13 pip install --require-hashes succeeded; pip check passed |
| P2.2 npm lock | Implemented | Isolated package manifest/lock; pg@8.16.3; npm ci succeeded; pg.Pool API smoke check passed |
| P2.3 APT snapshot | Implemented | Exact image inspected as Debian 13.7 Trixie; Debian snapshot timestamp and package versions pinned; PGDG .deb checksums verified; full Docker build and pgsodium 3.1.11 extension creation passed |
| P2.4 job permissions | Implemented | Workflow permissions empty; admission has actions/read + contents/read; other jobs have contents/read only |
| P2.5 artifact retention | Implemented | Admission marker: one day; benchmark artifact: seven days |
| P2.6 Dependabot | Implemented | Weekly GitHub Actions, pip, Docker, and npm updates; max two open PRs per ecosystem; minor/patch grouped; no auto-merge |

## Security policy enforcement

The static workflow policy validator now verifies:
- immutable full-SHA GitHub Action references;
- exact job-scoped GITHUB_TOKEN permissions and no inherited workflow-level permissions;
- bounded artifact retention;
- complete hash presence and --require-hashes use for both Python jobs;
- isolated npm lockfile integrity and npm ci use;
- fixed Debian Snapshot timestamp, exact APT package versions, and PGDG package SHA-256 pins;
- all four Dependabot ecosystems and bounded weekly update cadence.

Negative tests reject elevated token scopes, missing read scopes, unbounded retention, Python installs without hash enforcement, and mutable npm install commands.

## Invariants retained

- pull_request, push to main, and workflow_dispatch triggers.
- Global stem-lab-global-ci concurrency, no cancellation, single queue.
- 600-second fail-closed admission gate and marker upload before validation.
- Both validation jobs remain aggregated by the stable CI result check.
- CI Deferred remains non-successful; no validation jobs or checks were removed or weakened.
- Checkout credentials remain non-persistent.
- No direct push to main, branch-protection bypass, or GitHub Settings mutation.

## Verification record

Local verification completed on the connected macOS development host using clean Linux/amd64 containers where appropriate:
- Python lock: pip install --require-hashes and pip check passed.
- Node lock: npm ci, npm ls --depth=0, pg.Pool API smoke check, and the complete Node ESM benchmark smoke passed.
- Policy validator: passed.
- Negative policy tests: passed.
- Docker build: full linux/amd64 build passed using the exact PostgreSQL image digest, Debian Snapshot, and PGDG package checksum verification. The built image started PostgreSQL 17.11 and successfully created pgsodium 3.1.11.
- Database verifier: all 15 PostgreSQL tenant Ed25519 verifier tests passed against the built image.
- Store benchmark: full smoke profile passed for psycopg sync, psycopg async, asyncpg, and Node pg across concurrency 1/8/32. Local results are functional smoke evidence only, not production performance claims.
- CI admission and result unit tests: 7 admission tests and 8 aggregate-result tests passed.

P2 implementation is complete in the branch, pending the stacked PR's complete GitHub CI result. The PR remains Draft until that result is green.