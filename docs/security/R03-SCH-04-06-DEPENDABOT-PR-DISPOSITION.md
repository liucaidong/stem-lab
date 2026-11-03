# R03-SCH-04.6 — Dependabot PR #29–#32 Disposition

## Status and scope

This is a read-only disposition record for the four Dependabot pull requests observed during the SCH.04 audit. As of the audit refresh on 2026-11-04, all four remain open, unmerged, and their PR heads have not been modified by this work. No merge, rebase, comment, label, or branch update was performed on them.

| PR | Proposed update | Current head SHA | Disposition |
|---|---|---|---|
| [#29](https://github.com/liucaidong/stem-lab/pull/29) | Docker PostgreSQL 17.11 → 18.4 | `0da65df7e40832d1bd9116febda35c8f3e2a7803` | BLOCKED — inconsistent PostgreSQL major-version build/runtime paths |
| [#30](https://github.com/liucaidong/stem-lab/pull/30) | Node `pg` 8.16.3 → 8.23.1 | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` | HOLD — plausible update, but full validation and exact-version policy alignment are outstanding |
| [#31](https://github.com/liucaidong/stem-lab/pull/31) | `actions/setup-python` 7.0.0 → 7.1.0 | `2f18c7f3ca8c5d108cd472d753db97dc80b3d2e1` | HOLD — cancelled validation is not evidence of success |
| [#32](https://github.com/liucaidong/stem-lab/pull/32) | `actions/upload-artifact` 6.0.0 → 7.0.2 | `06c7c7508ed525dc81d0bb2d65294a0a169310c4` | DO NOT MERGE AS-IS — old artifact-marker implementation conflicts with SCH.04 removal |

## Findings

### PR #29 — PostgreSQL major version

The PR changes the Docker image from PostgreSQL 17.11 to 18.4, but the repository's Docker build still installs PostgreSQL 17 development packages and references PostgreSQL 17 `pg_config` / PGXS paths. This creates a mixed-major build/runtime environment. The PR is blocked until the image, development headers, `pg_config`, PGXS path, and extension build/test strategy are made consistently PostgreSQL 18. This audit does not authorize a production database migration.

### PR #30 — Node pg

The package manifest and lockfile consistently move `pg` from 8.16.3 to 8.23.1 and the lockfile integrity is present. However, the complete required CI validation has not been established for this PR head, and the repository's static dependency-policy fixture still pins the old version. Review the upstream compatibility/change surface, update the exact-version fixture only as part of a reviewed dependency change, and obtain a complete successful required check before merge consideration.

### PR #31 — setup-python action

This PR updates the immutable action reference for `actions/setup-python` from 7.0.0 to 7.1.0. The previously observed validation was cancelled; cancellation is not success. Verify the exact upstream immutable SHA and major-version compatibility, then obtain a complete successful required check for the current PR head.

### PR #32 — upload-artifact action

This PR updates the immutable action reference for `actions/upload-artifact` to 7.0.2, but its workflow changes retain artifact-marker admission behavior that SCH.04 removes in favor of native queueing. It also encountered the old static action-SHA policy fixture. Do not merge this PR as-is. Re-evaluate the action reference and any remaining legitimate artifact usage against the current SCH.04 workflow; do not restore the removed marker scheduler.

## Merge gate

- All four PRs remain open and unmerged.
- No PR #29–#32 head was changed by this audit.
- A cancelled, missing, or incomplete run is not a passing check.
- Reassess current head SHA and exact required `CI result` status immediately before any future decision.
- No automatic merge is authorized by this disposition.
