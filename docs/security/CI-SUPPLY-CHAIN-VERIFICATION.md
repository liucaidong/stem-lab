# CI Supply Chain Verification — R03.SCH.02 P1

## Static acceptance checks

- [x] All external `uses:` references in the root workflow are full 40-character commit SHAs.
- [x] All four action commits are signature-verified by GitHub.
- [x] All four action metadata files declare Node.js 24 runtime.
- [x] Every checkout step disables persisted Git credentials.
- [x] PostgreSQL service image is pinned to a SHA-256 manifest digest.
- [x] Custom PostgreSQL Dockerfile base image uses the same SHA-256 manifest digest.
- [x] pgsodium v3.1.11 release asset SHA-256 is declared and checked with `sha256sum -c -` before archive extraction.
- [x] Static workflow policy validator enforces the above controls.
- [x] Original workflow triggers, global concurrency, admission gate, validation jobs, and aggregate check remain present and unchanged.

## Runtime acceptance (must be observed on the PR)

- [ ] `ci-admission` executes and preserves the 600-second gate.
- [ ] `validate-contracts` executes and succeeds.
- [ ] `tenant-ed25519-verifier` executes, builds the digest-pinned image, verifies the pgsodium archive, and succeeds.
- [ ] `CI result` executes and succeeds.
- [ ] If a run is deferred by the cooldown, `CI result` fails as designed; this is not a passing acceptance run.

## Manual verification commands

```bash
python scripts/validate_ci_workflow_policy.py
python scripts/test_ci_admission.py
python scripts/test_ci_result.py
docker build --pull -f scripts/docker/pgsodium-postgres17.Dockerfile -t stemlab-postgres17-pgsodium:3.1.11 .
```

The Docker build must complete without a checksum mismatch. The PR CI is the authoritative integrated runtime verification. No claim of runtime acceptance is made until its four jobs report the required successful outcomes.
