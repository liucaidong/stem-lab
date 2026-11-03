# R03-SCH-04.3 — Dependabot Governance Audit and Target Policy

## 1. Status and scope

Audit only. No Dependabot configuration, PR, workflow, dependency lock, Ruleset, or run was modified or retriggered.

Baseline:
- Main SHA: `8e749b55899d3626e39a31e1e438e3db682f5219`
- Dependabot config: `.github/dependabot.yml`
- Ecosystems: GitHub Actions, pip, Docker, npm.
- PR burst: #29–#32, four PRs created in approximately two minutes.
- Recent Dependabot dynamic runs: eight in approximately five seconds; all successful.
- Custom CI global concurrency and 300-second admission do not govern GitHub-managed dynamic runs.

## 2. Current configuration audit

| Ecosystem | Directory | Schedule | Open PR limit | Grouping |
|---|---|---|---:|---|
| github-actions | `/` | weekly; no explicit day/time/timezone | 2 | minor + patch |
| pip | `/` | weekly; no explicit day/time/timezone | 2 | minor + patch |
| docker | `/scripts/docker` | weekly; no explicit day/time/timezone | 2 | minor + patch |
| npm | `/scripts/benchmarks/store-driver-node` | weekly; no explicit day/time/timezone | 2 | minor + patch |

Findings:
1. The PR limit is per update configuration/ecosystem, not a repository-wide global cap. The four entries can permit up to eight open version-update PRs at once; GitHub security-update PRs have separate behavior and must not be assumed covered by this version-update cap.
2. Minor and patch updates are grouped. Major updates remain separate PRs, which is appropriate for review but can arrive in the same update window.
3. No explicit schedule day/time/timezone is set, so the repository does not control ecosystem staggering.
4. No explicit version-update cooldown is set.
5. The configuration does not define a separate PostgreSQL major-version policy or a global cross-ecosystem arrival budget.
6. Dependabot dynamic runs are a separate GitHub-managed control plane and are not serialized by the custom workflow's concurrency group.

GitHub supports weekly schedule day/time/timezone, open PR limits, update groups, and version-update cooldowns. Cooldowns affect version updates; they do not delay security updates. References:
- [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
- [Optimizing Dependabot PR creation](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/optimizing-pr-creation-version-updates)
- [Controlling dependencies updated](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependencies/controlling-dependencies-updated)

## 3. Target policy proposal

This is a policy proposal, not an edit to `.github/dependabot.yml`.

### 3.1 Cadence and arrival shaping

| Ecosystem | Proposed window (UTC) | Open version PR limit | Policy |
|---|---|---:|---|
| github-actions | Monday 02:00 | 1 | Minor/patch grouped; major individual |
| pip | Tuesday 02:00 | 1 | Minor/patch grouped; lock regeneration required |
| docker | Wednesday 02:00 | 1 | PostgreSQL major updates individually reviewed |
| npm | Thursday 02:00 | 1 | Minor/patch grouped; major individual |

Rationale:
- Stagger discovery across four separate days.
- Reduce per-ecosystem concurrent PRs from two to one.
- Keep security updates available; do not globally suppress them to control CI load.
- A weekly schedule is a discovery cadence, not a substitute for the durable CI queue.

Times are proposed operating windows. The repository owner must approve the timezone and operating window before implementation.

### 3.2 Version risk policy

| Ecosystem / dependency class | Patch | Minor | Major |
|---|---|---|---|
| GitHub Actions | Group; pin full SHA; full CI | Group; pin full SHA; full CI | Individual PR; verify upstream release/tag and action SHA; policy tests must accept approved immutable SHA |
| pip | Update direct + compiled hash lock atomically | Update direct + compiled hash lock atomically | Individual PR; dependency/API review and complete Python CI |
| Docker / PostgreSQL | Digest-only patch update; full container tests | Individual review if server/runtime changes | Individual upgrade dossier; PG compatibility, extension build, SQL, migration and rollback audit |
| npm / node-postgres | Group; lockfile integrity required | Group; API/pool/protocol review and smoke + targeted tests | Individual PR; breaking-change review and full benchmark/contract tests |

### 3.3 Proposed version-update cooldowns

Subject to owner approval:
- patch: 3 days;
- minor: 7 days;
- major: 30 days.

The purpose is to avoid immediate adoption of a newly published version before ecosystem metadata and downstream reports stabilize. Security updates must not be delayed by this version-update cooldown. If the project requires a shorter security remediation SLA, that is a separate control.

### 3.4 PostgreSQL major update policy

A PostgreSQL major update is not an ordinary Docker digest bump. Require:
1. Explicit target major and current supported patch release.
2. Official PostgreSQL release/migration note review.
3. All extension versions and build artifacts verified for the target major.
4. Extension binaries compiled with the target major's `pg_config` and server headers.
5. Test matrix covering the current supported major and target major during transition.
6. SQL migration and tenant verifier tests on the target major.
7. Backup/restore or `pg_upgrade` plan if production data is actually migrated.
8. Performance and operational regression evidence.
9. Rollback plan and exact immutable image digest.
10. Complete successful CI on the PR head SHA.

PostgreSQL 18 documentation states that a major migration requires dump/restore, `pg_upgrade`, or logical replication; changing a container tag alone does not migrate a persistent data directory:
- [PostgreSQL 18 release notes — migration to version 18](https://www.postgresql.org/docs/18/release-18.html)
- [PostgreSQL 18 pg_upgrade](https://www.postgresql.org/docs/18/pgupgrade.html)

### 3.5 Static policy / Dependabot compatibility

Current static policy contains exact package-version expectations:
- Dockerfile base image and PGDG development package are pinned to PostgreSQL 17.11.
- Node benchmark requires `pg==8.16.3`.
- Workflow policy tests pin the old upload-artifact action SHA.

This makes legitimate Dependabot updates fail admission until the policy and its expected lock data are changed in the same reviewed update. A valid immutable SHA or new exact package version must not be treated as an untrusted change merely because it differs from yesterday's approved value.

Target approach:
- separate structural policy (full 40-character action SHA, digest format, hash presence, lock integrity, installation flags) from approved-version policy;
- keep an explicit reviewed pin manifest or derive expected exact versions from committed lock inputs;
- require a PR to update dependency input, checksum/digest, and policy fixture together;
- run negative tests for tag refs, shortened SHA, missing integrity, mismatched direct/lock version, and changed artifact retention;
- ensure Dependabot-generated PRs can pass after full review without bypassing static checks.

The Python validator currently verifies that every direct dependency package name appears in the hash lock, but the inspected implementation does not compare the direct requirement's exact version with the corresponding locked version. This should be tightened so that a direct requirement bump cannot leave a stale lock silently accepted.

## 4. Cross-ecosystem concurrency control

The target Dependabot policy reduces simultaneous arrivals but does not create a global cap. A single ecosystem limit of one still permits one PR from each ecosystem, and security updates may arrive outside the normal version-update schedule.

Therefore:
- Dependabot configuration is an arrival-rate control only.
- The durable scheduler proposed in SCH.04.2 remains the authoritative task queue.
- Dynamic Dependabot runs are monitored separately from PR validation runs.
- No automatic merge is enabled.
- No PR is mergeable solely because Dependabot opened it or its dynamic update job succeeded.

## 5. Current PR and run observations

| PR | Ecosystem | Change | Run ID | Result | Governance consequence |
|---|---|---|---:|---|---|
| #29 | Docker | PostgreSQL 17.11 → 18.4 | 41722065653 | cancelled | Major upgrade; blocked pending complete compatibility and CI audit |
| #30 | npm | pg 8.16.3 → 8.23.1 | 41722127811 | cancelled | Minor semver update but large upstream delta; blocked pending complete CI |
| #31 | github-actions | setup-python 7.0.0 → 7.1.0 | 41722331190 | cancelled | No completed validation evidence |
| #32 | github-actions | upload-artifact 6.0.0 → 7.0.2 | 41722344375 | failure | Static policy fixture rejected new immutable SHA |

All four PRs were open at audit time. #29, #30 and #31 runs returned zero jobs; #32 failed in `ci-admission` before heavy validation. None is approved for merge.

## 6. Acceptance criteria for Dependabot governance

- [ ] Four ecosystems have explicit, staggered schedule windows.
- [ ] Per-ecosystem open version PR limit is one, unless an exception is approved.
- [ ] Minor/patch grouping remains enabled.
- [ ] Major updates remain individually reviewable.
- [ ] Security updates are not blocked by version-update cooldowns.
- [ ] PostgreSQL major upgrades require a dedicated compatibility dossier.
- [ ] Python direct requirements and generated hash lock are version-consistent.
- [ ] Node lockfile uses exact versions and integrity hashes for all resolved packages.
- [ ] Docker image digests and extension build inputs are immutable and aligned to the same PostgreSQL major.
- [ ] Static policy tests validate immutable structure without freezing old dependency versions.
- [ ] No automatic merge for unverified updates.
- [ ] All PR validation results are tied to exact head SHA and successful run ID.

**Stage result: audit and policy proposal complete; no configuration changes authorized.**
