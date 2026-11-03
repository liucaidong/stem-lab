# R03.SCH.03 — P2 Dependency and Build-Input Locks

Date: 2026-11-03

## Python: full hash-locked dependency closure

Direct requirements are maintained in requirements-contract-validation.txt. The generated requirements-contract-validation.lock.txt contains 26 exact package versions and SHA-256 hashes for every selected package artifact.

Generation command (target matches the GitHub Actions runner):

    uv pip compile --generate-hashes --python-version 3.13 --python-platform x86_64-unknown-linux-gnu requirements-contract-validation.txt -o requirements-contract-validation.lock.txt

The direct dependency set includes jsonschema==4.26.0, PyYAML==6.0.3, openapi-spec-validator==0.9.0, rfc8785==0.1.4, cbor2==6.1.5, psycopg[binary,pool]==3.3.6, and asyncpg==0.32.0.

Both Python CI jobs use:

    python -m pip install --require-hashes -r requirements-contract-validation.lock.txt

Verification: installed the lock in a clean python:3.13-slim linux/amd64 container using pip hash-checking mode; installation succeeded and pip check reported no broken requirements.

## Node: isolated benchmark package and integrity lock

The Store driver benchmark has its own package directory: scripts/benchmarks/store-driver-node/.

- package.json pins pg to exactly 8.16.3.
- package-lock.json uses npm lockfileVersion 3 and integrity metadata.
- CI uses npm ci --ignore-scripts --no-audit --no-fund from that directory.
- The .mjs benchmark script uses createRequire from the isolated package manifest, so Node ESM resolves pg without NODE_PATH or repository-level symlinks.

Verification: npm ci installed 14 packages; npm ls --depth=0 showed only pg@8.16.3; the pg.Pool API smoke check passed.

## Debian APT: immutable snapshot plus explicit package pins

The exact pinned base image was pulled and inspected:
- Image: postgres:17.11@sha256:0b81cec82228160abfa753aeaad0609b709eb26eeb950f2e404ad2326e1cc370
- Platform: linux/amd64
- OS: Debian GNU/Linux 13.7 (trixie)

Debian and Debian Security sources are fixed to snapshot timestamp 20261027T000000Z. APT's Check-Valid-Until check is disabled only because historical snapshots are intentionally immutable; repository signatures remain verified using the Debian archive keyring.

Explicit Debian package pins:

| Package | Version |
|---|---|
| build-essential | 12.12 |
| ca-certificates | 20250419+deb13u1 |
| clang-19 | 1:19.1.7-3+b1 |
| curl | 8.14.1-2+deb13u7 |
| llvm-19-dev | 1:19.1.7-3+b1 |
| pkg-config | 1.8.1-4 |
| unzip | 6.0-29+deb13u1 |

### PGDG compatibility exception

The pinned PostgreSQL base image already contains PGDG libpq5 18.6-1.pgdg13+2. Installing Debian's postgresql-server-dev-17 17.11-0+deb13u1 would require downgrading that runtime library to 17.11. That package combination was rejected.

Instead, the Docker build obtains these exact PGDG packages and verifies their archive SHA-256 before installation:

| Package | Version | SHA-256 |
|---|---|---|
| postgresql-server-dev-17 | 17.11-1.pgdg13+2 | a802fd5ec363597ea39b342451803797ef972c684cc2f6a5ffbfab786a75b9f1 |
| libpq-dev | 18.6-1.pgdg13+2 | b2add61e7fe0e9328140de456a85c96737b517f9cf62b44fd88e86aa2b765f29 |

The PGDG source remains signed and package versions are fixed; the exact downloaded package bytes are checksum-verified. All other APT package resolution is anchored to the Debian snapshot.

## Source archive integrity

- libsodium 1.0.22 SHA-256: adbdd8f16149e81ac6078a03aca6fc03b592b89ef7b5ed83841c086191be3349
- pgsodium 3.1.11 SHA-256: c8fef093d6d3afe859b03abcf7f598e9fce4298f7bfff283434bc300cba203ab

Both checks occur before extraction/build.

## Refresh procedure

1. Review upstream security support and release status; do not automatically roll back to an older snapshot.
2. Select a new Debian and Debian Security snapshot timestamp together.
3. Resolve all exact package versions against that timestamp and verify the full Docker build.
4. For PGDG, review the new package versions, download the exact .deb artifacts, and update their SHA-256 values only after independently verifying the bytes.
5. Regenerate the Python lock from the direct requirements and the exact CI target platform; verify with pip install --require-hashes and pip check.
6. Regenerate the npm lock with npm, then verify with npm ci and the benchmark API smoke check.
7. Update this record and the CI policy tests in the same reviewed change. Dependabot suggestions do not bypass this controlled process.