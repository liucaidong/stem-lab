# CI Supply Chain Hardening Plan — R03.SCH.02 P1

## Scope

This change closes the P1 findings from the read-only R03.SCH.01 audit. It is intentionally limited to immutable GitHub Actions references, Node.js 24-compatible action releases, PostgreSQL image digest pinning, and pgsodium release-asset integrity verification.

## Remediation decisions

| Surface | Locked input | Verification basis |
|---|---|---|
| actions/checkout | v7.0.1 — `3d3c42e5aac5ba805825da76410c181273ba90b1` | GitHub release tag resolves to this commit; commit signature verified; action metadata declares `node24` |
| actions/setup-python | v7.0.0 — `5fda3b95a4ea91299a34e894583c3862153e4b97` | GitHub release tag resolves to this commit; commit signature verified; action metadata declares `node24` |
| actions/setup-node | v6.0.0 — `2028fbc5c25fe9cf00d9f06a71cc4710d4507903` | GitHub release tag resolves to this commit; commit signature verified; action metadata declares `node24` |
| actions/upload-artifact | v6.0.0 — `b7c566a772e6b6bfb58ed0dc250532a479d7789f` | GitHub release tag resolves to this commit; commit signature verified; action metadata declares `node24` |
| PostgreSQL service and Docker base | `postgres:17.11@sha256:0b81cec82228160abfa753aeaad0609b709eb26eeb950f2e404ad2326e1cc370` | Docker Hub manifest digest for the linux/amd64 PostgreSQL 17.11 image |
| pgsodium archive | GitHub release asset v3.1.11, SHA-256 `c8fef093d6d3afe859b03abcf7f598e9fce4298f7bfff283434bc300cba203ab` | GitHub Releases API asset digest; same SHA-256 is published by the SourceForge mirror page |

## Compatibility

The four pinned Actions use the Node.js 24 Action runtime. GitHub's Node.js 24 action releases require Actions Runner v2.327.1 or newer. The workflow uses GitHub-hosted `ubuntu-latest` runners; the first PR run is the runtime compatibility acceptance test. The application-level Node.js setup inputs (22 and 24) are unchanged.

The PostgreSQL digest is the linux/amd64 platform manifest. This is consistent with the current GitHub-hosted `ubuntu-latest` runner architecture. If the workflow later moves to ARM runners, the image pin must be deliberately replaced with a verified multi-platform index digest or architecture-specific selection.

## CI invariants preserved

- `pull_request`, `push` to `main`, and `workflow_dispatch` triggers remain unchanged.
- The global concurrency group, `cancel-in-progress: false`, and `queue: single` remain unchanged.
- The 600-second admission gate and fail-closed behavior remain unchanged.
- The admission marker is still persisted only after admission.
- All validation jobs remain required; `CI result` remains the aggregate status.
- No tests, validation steps, jobs, or required outcomes are removed or weakened.
- No GitHub repository settings, branch protection, secrets, or Actions permissions are changed.

## Explicitly deferred

Python hash-locking, npm lockfile creation, apt snapshot pinning, and per-job permission redesign remain separate P2 work. They are not mixed into this P1 patch.
