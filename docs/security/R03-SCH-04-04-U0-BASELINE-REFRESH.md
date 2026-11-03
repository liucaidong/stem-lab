# R03-SCH-04.4 — U0 Baseline Refresh

- Date: 2026-11-04
- Repository: `liucaidong/stem-lab`
- Main SHA: `8e749b55899d3626e39a31e1e438e3db682f5219`
- Result: read-only baseline refresh complete.

## Controls

| Control | Observed state |
|---|---|
| Default branch | `main` |
| Ruleset | ID `26463757`, active |
| Required check | `CI result`, integration ID `15368`, strict |
| Workflow | `.github/workflows/contract-validation.yml` |
| Concurrency | `stem-lab-global-ci`, `cancel-in-progress: false`, `queue: single` |
| Admission | `scripts/ci_admission.py`, 300-second artifact marker |
| Dependabot | Four ecosystems, weekly, limit 2 each, no explicit UTC day/time |

## Open Dependabot PR snapshot

All four PRs were open against main SHA `8e749b55899d3626e39a31e1e438e3db682f5219`.

| PR | Head SHA | Historical run | Observed result |
|---:|---|---:|---|
| #29 PostgreSQL 18.4 | `0da65df7e40832d1bd9116febda35c8f3e2a7803` | `41722065653` | Cancelled; no Check Runs returned |
| #30 node-postgres 8.23.1 | `b49b165d8b7a73679a297b5264ddbf16013d8f0d` | `41722127811` | Cancelled; no Check Runs returned |
| #31 setup-python 7.1.0 | `2f18c7f3ca8c5d108cd472d753db97dc80b3d2e1` | `41722331190` | Cancelled; no Check Runs returned |
| #32 upload-artifact 7.0.2 | `06c7c7508ed525dc81d0bb2d65294a0a169310c4` | `41722344375` | `ci-admission` failed; validations skipped; `CI result` failed |

The exact cause of the three cancellations is not proven by job/check data. Queue replacement is consistent with the observed pattern but is not asserted as proven.

## Main validation snapshot

For main SHA `8e749b55899d3626e39a31e1e438e3db682f5219`, both required validation jobs and `CI result` succeeded. Eight Dependabot dynamic workflow runs were also observed in the same short burst; those are separate from the custom workflow concurrency group.

## Implementation implications

1. Remove the 300-second artifact-marker mechanism across workflow, admission script, tests, and policy validator.
2. Change the custom workflow to `queue: max`, preserving group and `cancel-in-progress: false`.
3. Preserve exact `CI result` context and fail-closed aggregation.
4. Stagger Dependabot schedules and cap each ecosystem at one open version PR.
5. Keep PR #29–#32 unmerged until complete CI and compatibility review.
6. Keep Ruleset #26463757 unchanged.

U0 was read-only; this evidence record does not itself modify main, Ruleset, branch protection, or Dependabot PRs.
