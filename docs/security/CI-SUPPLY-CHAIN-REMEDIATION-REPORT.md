# CI Supply Chain Remediation Report — R03.SCH.02 P1

## Baseline

- Repository: `liucaidong/stem-lab`
- Base branch: `main`
- Audited base commit: `e509041b96900dbd76a9c87dbb462edb56428fdf`
- Scope: P1 only

## Changes made

1. Replaced mutable major-version Action tags with full 40-character commit SHA references for checkout, setup-python, setup-node, and upload-artifact.
2. Selected verified Node.js 24-compatible releases and verified the referenced action metadata at each exact commit.
3. Set `persist-credentials: false` for every checkout step. The workflow's admission API call continues to use the explicitly scoped `GH_TOKEN`; no git-authenticated operation is needed.
4. Pinned both the PostgreSQL service container and the custom Dockerfile base image to the same PostgreSQL 17.11 linux/amd64 manifest digest.
5. Switched the pgsodium archive source to the upstream GitHub v3.1.11 release asset and added a SHA-256 verification step before extraction.
6. Extended `validate_ci_workflow_policy.py` to reject unpinned external Actions, unpinned PostgreSQL service/base images, and missing pgsodium checksum enforcement.

## Evidence

- Action commit signatures: GitHub API reported `verified=true`, `reason=valid` for all four pinned commits.
- Action runtime metadata: all four exact `action.yml` files declare `runs.using: node24`.
- pgsodium release: GitHub release `michelp/pgsodium v3.1.11`; release asset digest is `c8fef093d6d3afe859b03abcf7f598e9fce4298f7bfff283434bc300cba203ab`.
- PostgreSQL manifest: Docker Hub's `postgres:17.11` linux/amd64 manifest digest is `0b81cec82228160abfa753aeaad0609b709eb26eeb950f2e404ad2326e1cc370`.

## Status

The source changes are staged for review on a dedicated branch. Final acceptance is contingent on the PR's full CI run completing successfully. A cooldown rejection is not acceptance: the aggregate `CI result` must report success after all required validation jobs execute.

## Out of scope

No GitHub Settings changes, branch-protection changes, secret changes, force-push, direct push to `main`, or changes to CI triggers/admission policy were made.
