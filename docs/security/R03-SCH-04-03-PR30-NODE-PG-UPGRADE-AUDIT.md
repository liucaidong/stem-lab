# R03-SCH-04.3 — PR #30 node-postgres Upgrade Audit

## 1. Decision

<badge>BLOCKED — DO NOT MERGE YET</badge>

PR #30 is a semver-minor dependency update and its lockfile has integrity hashes, but it has not completed CI. The static policy currently pins the old `pg@8.16.3` version and would reject the PR before heavy validation. The accumulated upstream delta is substantial enough to require focused compatibility tests.

## 2. PR identity and CI evidence

| Field | Observed |
|---|---|
| PR | #30 |
| Title | `build(deps): bump pg from 8.16.3 to 8.23.1 in the node-minor-patch group` |
| State | open |
| Head SHA | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` |
| Base SHA | `8e749b55899d3626e39a31e1e438e3db682f5219` |
| Changed files | 2 |
| Run ID | `41722127811` |
| Run conclusion | cancelled |
| Jobs returned | 0 |
| Head check-runs | 0 |
| Combined status | pending |
| Mergeable state | blocked |

Cancelled is not success. No full CI or Node benchmark result exists for this PR head.

## 3. Exact change summary

Files:
- `scripts/benchmarks/store-driver-node/package.json`
- `scripts/benchmarks/store-driver-node/package-lock.json`

Direct dependency:
- `pg`: 8.16.3 → 8.23.1

Transitive package versions in the new lock:
- `pg-cloudflare`: 1.4.1
- `pg-connection-string`: 2.14.1
- `pg-int8`: 1.0.1
- `pg-pool`: 3.14.0
- `pg-protocol`: 1.16.1
- `pg-types`: 2.2.0
- `pgpass`: 1.0.5
- plus the locked postgres-array/by tea/date/interval, split2 and xtend dependencies.

The package manifest and lock root agree on `pg@8.23.1`. The lockfile remains version 3. All resolved package entries with versions have an integrity digest. The top-level `pg` tarball resolves from `registry.npmjs.org`; several transitive entries retain `registry.npmmirror.com` URLs. Integrity hashes mitigate content substitution, but mixed registry hosts remain a reproducibility/availability consideration.

The workflow continues to use `npm ci --ignore-scripts --no-audit --no-fund` in the isolated benchmark package. This is the correct immutable install mode and should be preserved.

## 4. Upstream delta and compatibility

The upstream node-postgres compare from `pg@8.16.3` to `pg@8.23.1` reports 125 commits ahead. This is semver-minor, not semver-major, but it accumulates meaningful protocol, authentication, connection, pool, and parser changes.

Relevant upstream changelog items include:
- 8.17.0: correct error when database URL parsing fails;
- 8.18.0: `client.connect()` returns the client instance;
- 8.19.0: deprecates internal query queue and passes connection parameters to password callback;
- 8.20.0: adds `onConnect` callback to `pg.Pool`;
- 8.21.0: SASL SCRAM server-error handling, `scramMaxIterations`, transaction status API;
- 8.22.0: direct SSL negotiation support for PostgreSQL 17+;
- 8.23.0: query pipelining support.

Upstream compatibility documentation states node-postgres supports PostgreSQL 8.x through the latest version and currently supports Node 18, 20, 22, and 24. The repository workflow uses Node 24, so the declared runtime is within the upstream compatibility matrix.

Sources:
- [node-postgres compatibility](https://node-postgres.com/)
- [node-postgres upgrading guide](https://node-postgres.com/guides/upgrading)
- [node-postgres CHANGELOG](https://github.com/brianc/node-postgres/blob/master/CHANGELOG.md)
- [upstream pg@8.23.1 release commit](https://github.com/brianc/node-postgres/commit/0980cefebe0ae461da8883703be049fe13ca96cf)

## 5. Local benchmark call-path review

The Node benchmark imports `Pool` from the isolated package using `createRequire`, then:
1. constructs a pool with environment configuration, `max`, `min`, connection/idle timeouts, `maxLifetimeSeconds`, and `pipeline: false`;
2. runs warm-up operations;
3. acquires a client;
4. starts a transaction;
5. sets the runtime role;
6. sets the tenant assertion using `set_config`;
7. selects one tenant row;
8. commits and releases the client;
9. records latency and pool-acquire wait.

This exercises a useful end-to-end path through `pg`, `pg-pool`, protocol framing, transactions, role switching, RLS and connection reuse.

Coverage limitations:
- it is a benchmark smoke test, not the full upstream node-postgres test suite;
- it does not independently exercise all SCRAM/SASL error paths, TLS negotiation, native bindings, connection-string parser edge cases, or pipeline mode;
- `pipeline: false` means the new pipelining feature is not exercised;
- the PR's CI run was cancelled, so even the smoke test has not passed on this head SHA.

The change may be compatible, but source compatibility claims and upstream support matrices cannot substitute for the repository's own complete PR CI.

## 6. Static admission policy conflict

The main-branch `scripts/validate_ci_workflow_policy.py` currently requires:
- `package.json` dependency `pg` exactly equal to `8.16.3`;
- `package-lock.json` `node_modules/pg.version` exactly equal to `8.16.3`.

PR #30 changes both to 8.23.1. If the cancelled run reached the static policy test, it would fail the exact-version assertion before the benchmark validation jobs. This is a predicted failure from the inspected source, not an observed run conclusion.

The correct fix is not to weaken lockfile integrity checks. The policy must verify exact manifest/lock consistency and integrity digests while allowing a reviewed new exact version. A Dependabot PR must update the expected policy fixture or approved dependency manifest in the same PR.

## 7. Compatibility verdict

| Dimension | Result |
|---|---|
| Node runtime | Compatible by upstream stated support (Node 24) |
| PostgreSQL protocol/server compatibility | Upstream states support through latest PostgreSQL |
| Exact package/lock consistency | Pass |
| Integrity digests | Pass for all resolved package entries |
| Install mode | Pass; `npm ci --ignore-scripts` retained |
| Static policy compatibility | Fail — hard-coded 8.16.3 |
| Local benchmark compatibility | Not tested; run cancelled |
| Full CI | Not tested; run cancelled |
| Merge readiness | No |

## 8. Required remediation and acceptance

1. Update static policy to validate manifest/lock exact equality without hard-coding yesterday's `pg` version.
2. Preserve `lockfileVersion: 3`, exact versions, and all integrity digests.
3. Decide whether mixed npm registry hosts are acceptable; if not, regenerate lock using one approved registry while preserving integrity.
4. Run `npm ci --ignore-scripts` from a clean workspace.
5. Run the complete existing Node benchmark smoke path on the exact PR head SHA.
6. Add targeted tests for pool lifecycle/reuse, connection errors, SCRAM authentication failure handling, and transaction rollback.
7. Verify PostgreSQL 17.11 service compatibility; if PostgreSQL 18 is introduced separately, test against both versions.
8. Capture exact workflow Run ID, Job IDs, conclusions, artifact outputs, and PR head SHA.
9. Require the unchanged `CI result` check to succeed.

**Final PR #30 verdict: CONDITIONALLY PLAUSIBLE, NOT VALIDATED, DO NOT MERGE.**
