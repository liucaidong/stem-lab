# R03.SCH.03 — P2 Supply-Chain Hardening Implementation Status

Date: 2026-11-03

## Baseline
Based on P1 PR #27 head `c9e5d2bfaf4b7a3c41e485366dba4e474e175051`, not main. P2 branch: `security/r03-sch-03-p2`. P1 remains open, Draft, and unmerged. No repository settings, branch protection, required checks, or Actions settings were changed.

## Implemented in this branch
- Workflow-level `permissions: {}` removes inherited token permissions.
- `ci-admission` receives only `actions: read` and `contents: read`.
- `validate-contracts`, `tenant-ed25519-verifier`, and `ci-result` receive only `contents: read`.
- Admission marker retention is one day; benchmark smoke artifact retention is seven days.
- Static policy validator enforces exact job token scopes and both retention values.
- Negative policy tests reject write scopes, missing read scopes, and missing/overlong retention.
- Dependabot weekly updates configured for GitHub Actions, pip, and the Dockerfile directory; two open PRs maximum per ecosystem; minor/patch updates grouped; no auto-merge.

## Deferred — evidence required

### P2.1 Python hash-locked installs
A real `uv pip compile --generate-hashes` attempt failed because this environment cannot resolve PyPI DNS (`https://pypi.org/simple/cbor2/`). No hashes were fabricated. Generate a complete lock for all validator and verifier dependencies, including `psycopg[binary,pool]==3.3.6` and `asyncpg==0.32.0`, covering CI-selected artifacts. Verify with `pip install --require-hashes`; only then remove inline installs.

### P2.2 Node benchmark lock
The benchmark currently installs `pg@8.16.3` with npm and disables lockfile creation. npm registry access is unavailable here, so a valid integrity lock and `npm ci` verification cannot be produced. Do not hand-author integrity hashes. Isolate the benchmark dependency in a dedicated package directory, commit package.json/package-lock.json, and switch to `npm ci` when registry access is available.

### P2.3 APT snapshot
Docker Hub identifies the pinned linux/amd64 image digest as `postgres:17.11-trixie`. This is useful suite evidence, but not a replacement for inspecting the exact image's `/etc/os-release`, APT sources, and package metadata. No Docker/Podman runtime or registry access is available in this environment. Therefore no snapshot timestamp or package versions were guessed. Complete by inspecting the exact image, resolving the full package closure against a Debian Trixie snapshot, and documenting controlled refresh cadence.

## Invariants retained
- `pull_request`, `push` to `main`, and `workflow_dispatch`.
- Global `stem-lab-global-ci` concurrency, no cancellation, single queue.
- 600-second fail-closed admission gate and admission marker upload before validation.
- Both validation jobs remain aggregated by required `CI result`.
- CI Deferred remains non-successful; all existing validation steps remain.
- Checkout credentials remain non-persistent.
- No direct push to main, branch-protection bypass, or GitHub Settings mutation.

## Verification
This report does not claim P2 completion. Branch validation is required for the implemented permission/retention changes. P2.1–P2.3 remain open blockers.
