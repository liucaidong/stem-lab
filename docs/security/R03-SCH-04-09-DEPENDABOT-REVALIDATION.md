# R03-SCH-04.9 — Dependabot PR #29–#32 Revalidation

**Status:** READ-ONLY DISPOSITION / NO PR MUTATIONS  
**Snapshot date:** 2026-11-04  
**Repository:** `liucaidong/stem-lab`  
**Current `main`:** `8e749b55899d3626e39a31e1e438e3db682f5219`  
**SCH.04 target:** PR #33 head `d2b67664d81a8988a73c96eeaed48817fc5c8a01` (Draft / OPEN / unmerged)

## 1. Summary

| PR | Head SHA | Change | Latest CI evidence | Disposition |
|---:|---|---|---|---|
| #29 | `0da65df7e40832d1bd9116febda35c8f3e2a7803` | PostgreSQL base image 17.11 → 18.4 | Run `41722065653` cancelled; no exact-head success | BLOCKED |
| #30 | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` | node-postgres `pg` 8.16.3 → 8.23.1 | Run `41722127811` cancelled; no exact-head success | HOLD / deterministic policy fixture mismatch |
| #31 | `2f18c7f3ca8c5d108cd472d753db97dc80b3d2e1` | `actions/setup-python` 7.0.0 → 7.1.0 | Run `41722331190` cancelled; no exact-head success | HOLD / upstream pin verified, CI outstanding |
| #32 | `06c7c7508ed525dc81d0bb2d65294a0a169310c4` | `actions/upload-artifact` 6.0.0 → 7.0.2 | Run `41722344375` failed; `CI result` failed | DO NOT MERGE AS-IS |

All four PRs remain OPEN and target `main`. None was modified, rerun, dispatched, cancelled, closed or merged by this revalidation.

## 2. PR #29 — PostgreSQL major-version mismatch

The only PR diff changes the Dockerfile base image from PostgreSQL `17.11` to `18.4`. The same Dockerfile still:

- downloads and installs `postgresql-server-dev-17=17.11-1.pgdg13+2`;
- installs `libpq-dev=18.6-1.pgdg13+2`;
- verifies the PostgreSQL 17 development package checksum;
- builds and installs pgsodium using `/usr/lib/postgresql/17/bin/pg_config`.

This creates a PostgreSQL 18 runtime image with PostgreSQL 17 server headers and PGXS/`pg_config` paths. It is not a coherent major-version upgrade. Keep BLOCKED until the runtime image, server development package, libpq, `pg_config`, PGXS path, extension compatibility and complete PostgreSQL 18 test strategy are aligned. This is not authorization for a production database migration.

## 3. PR #30 — node-postgres dependency update

The package manifest and lockfile consistently update `pg` from `8.16.3` to `8.23.1`, with corresponding transitive dependency updates and an integrity digest. However, the current main-branch static policy still requires:

- `package.json` dependency `pg == 8.16.3`;
- lockfile `node_modules/pg.version == 8.16.3`.

Those exact checks are in `scripts/validate_ci_workflow_policy.py` (current main lines 167–173). PR #30 changes only the manifest and lockfile, so it does not update the policy fixture. A complete validation run would fail deterministically until the approved exact-version fixture and lockfile policy are updated together. Review the transitive compatibility surface and run the Store driver smoke benchmark before merge consideration.

## 4. PR #31 — setup-python action pin

The PR changes both `actions/setup-python` references to:

`6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`

The upstream Git reference `actions/setup-python` tag `v7.1.0` resolves to this exact commit. Its `action.yml` declares `runs.using: node24`, consistent with the current GitHub runner Node 24 transition. The immutable pin itself is verified; the current PR head still lacks a completed successful CI run and exact-head `CI result`. Keep HOLD until the branch is current and the full required validation succeeds.

## 5. PR #32 — upload-artifact pin and obsolete admission marker

The PR changes both `actions/upload-artifact` references to:

`cf430e030ddbb5b0abf93d22962f4752f3646cd9`

The upstream `actions/upload-artifact` tag `v7.0.2` resolves to this exact commit, and its `action.yml` declares `runs.using: node24`. The action pin itself is valid.

However, the PR retains the `stem-lab-ci-admission` Artifact Marker upload. Its current-main policy fixture explicitly requires the previous upload-artifact SHA `b7c566a...` for that marker, so Run `41722344375` failed in `ci-admission` with `ci-admission must upload the marker artifact only after admission`. More importantly, the SCH.04 target architecture has removed the marker/cooldown mechanism entirely. Do not update the fixture simply to bless the new marker SHA; that would preserve the obsolete scheduler and conflict with PR #33.

Reassess legitimate benchmark artifact upload separately. Any remaining artifact use must be independently justified, SHA-pinned and retained with bounded retention; it must not be used as global admission or queue state.

## 6. Required next steps

1. Keep PR #29 blocked until the PostgreSQL major-version build/runtime chain is coherent.
2. Update PR #30's exact dependency policy fixture and validate the full benchmark path before considering merge.
3. For PR #31, retain the verified v7.1.0 immutable SHA and obtain a complete current-head CI result.
4. For PR #32, remove Artifact Marker admission behavior; retain only legitimate artifact use, then align policy/tests with the SCH.04 native queue design.
5. Revalidate all four current heads immediately before any write or merge decision. A cancelled run is not success.
6. Do not merge any PR #29–#32 until exact-head CI and compatibility review both pass.

## 7. Explicit non-actions

No PR #29–#32 branch was modified, rerun, dispatched, cancelled, closed or merged. No Ruleset, `main`, or required check was changed.
