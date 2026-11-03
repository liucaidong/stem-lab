# R03-SCH-04.2 — CI Scheduling Architecture

## 1. Decision status and scope

**Approved direction: native-first scheduling; global 300-second cooldown removed.**
This document supersedes the earlier external-scheduler recommendation.

The repository owner approved:
- removing the repository-wide 300-second inter-start cooldown;
- not building an external Scheduler, durable external queue, webhook service, or dedicated GitHub App for this problem;
- retaining GitHub Actions as the CI execution and scheduling control plane;
- retaining admission safety, truthful aggregate results, Dependabot arrival shaping, and reconciliation;
- keeping Ruleset #26463757 and its required check `CI result` unchanged.

This is an architecture decision, not authorization to edit production workflow or Dependabot files. Implementation remains gated by the revised plan and verification.

Audit baseline:
- Main SHA: `8e749b55899d3626e39a31e1e438e3db682f5219`
- Required Ruleset check: `CI result`, strict status checks.
- Current custom workflow: `contract-validation.yml`.
- Current concurrency: `stem-lab-global-ci`, `cancel-in-progress: false`, `queue: single`.
- Previous 300-second admission marker: to be removed after migration; it is not a scheduler.
- Recent Dependabot burst: PR #29–#32; three cancelled runs and one policy failure.

## 2. Target architecture

```text
GitHub events
  ├─ pull_request (opened / synchronize / reopened / ready_for_review)
  ├─ push (main)
  ├─ workflow_dispatch (authorized manual recovery)
  └─ Dependabot-created PRs
          |
          v
GitHub Actions native concurrency
  group: stem-lab-global-ci
  cancel-in-progress: false
  queue: max
          |
          v
CI admission / policy validation
          |
          +--> validate-contracts
          |
          +--> tenant-ed25519-verifier
          |
          v
CI result (required check; truthful aggregate)
          ^
          |
Lightweight reconciliation / operator recovery
  - inspect open PR head SHAs
  - inspect workflow runs and required check state
  - rerun or dispatch missing validation using an approved path
```

The exact event-to-check association must be preserved. The existing PR-triggered workflow remains the owner of the required `CI result` context unless an isolated test proves an alternative is equivalent. No external App-created check is introduced.

## 3. GitHub native concurrency facts

GitHub documents:
- `queue: single` allows one pending run; a newer pending run replaces the existing pending run.
- `queue: max` allows up to 100 pending runs in a concurrency group.
- When the queue is full, additional runs can be cancelled.
- Ordering is based on when a run starts waiting, not guaranteed event-dispatch FIFO.
- `queue: max` is not an unlimited or durable application queue.

Sources:
- [GitHub Actions concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [GitHub changelog: larger concurrency queues, 2026-05-07](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/)

**Decision:** use `queue: max` for the custom required-validation workflow, with explicit overflow detection and reconciliation. It is a bounded native queue, not a guarantee that every historical event SHA will execute.

## 4. Why the external scheduler is rejected for this scope

An external durable queue could preserve every event as a durable task, but it would introduce:
- an independently hosted service and database;
- GitHub App creation, installation, token lifecycle, and webhook security;
- lease/fencing, retry, dead-letter, replay, and reconciliation implementations;
- a second control plane and operational burden;
- a difficult required-check identity/association proof.

The actual requirement is to prevent a PR's current head from being left without a successful required validation. The repository can first meet that requirement with GitHub's bounded native queue plus an auditable reconciliation process. Preserving every intermediate superseded commit is not a merge-gate requirement; the latest open PR head is.

If future evidence shows that every event/SHA must be durably executed, or that the native queue/reconciliation design cannot meet the agreed service level, reopen the ADR and evaluate an external scheduler separately. Do not build it pre-emptively.

## 5. Dependabot arrival shaping

Dependabot is a separate GitHub-managed control plane. The custom workflow's concurrency group does not serialize every Dependabot internal/dynamic workflow.

Adopt these proposed configuration changes:
- stagger the four ecosystem update windows across separate UTC weekdays;
- set `open-pull-requests-limit: 1` per ecosystem entry;
- retain minor/patch grouping;
- keep major upgrades individually visible;
- do not configure Dependabot cooldown as a substitute for CI scheduling;
- keep security updates independently actionable and do not delay them with version-update policy.

This limits arrival bursts; it does not replace validation or reconciliation.

Sources:
- [Optimizing Dependabot PR creation](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/optimizing-pr-creation-version-updates)
- [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)

## 6. Admission and required-check invariants

1. No cooldown, sleep-based throttle, or artifact-marker delay remains in the target path.
2. Every admitted run executes the complete required validation suite.
3. Admission failure, skipped validation, cancellation, timeout, missing job result, or policy failure must never be translated to success.
4. The aggregate job remains named exactly `CI result`.
5. The aggregate job must run with `if: always()` and fail closed unless admission and every required job conclude success.
6. `cancel-in-progress: false` remains mandatory for the required validation group.
7. Queue overflow or cancellation is an operational exception requiring reconciliation; it is not success.
8. Distinct open PR head SHAs are not deduplicated against one another.
9. A newer head SHA may make an older PR head obsolete for merge-gate purposes, but the latest open head must receive complete validation.
10. Main push validation must remain covered.

## 7. Reconciliation model

A lightweight scheduled/manual reconciliation workflow or operator procedure must inspect:
- all open PRs and their current head SHAs;
- main's current SHA;
- workflow runs associated with those exact SHAs;
- the exact `CI result` check and its conclusion/integration;
- queued, in-progress, cancelled, failed, and missing runs.

For every open PR current head and current main SHA:
- if a complete successful `CI result` exists, record covered;
- if a run is queued/in progress, do not create a duplicate;
- if the run is cancelled/failed/missing or lacks the required check, initiate an approved recovery;
- after recovery, verify the exact SHA and required-check context;
- never infer success from a missing run, skipped jobs, or a cancelled run.

Recovery preference:
1. rerun the original PR-triggered workflow run when GitHub supports rerunning that run and it preserves SHA/ref;
2. otherwise test a workflow_dispatch/PR-head recovery path in isolation and prove check association;
3. if neither produces the exact required check, retain/re-trigger the PR workflow through a safe repository-supported method. Do not create a parallel check or weaken Ruleset.

Reconciliation should be low-frequency and bounded (for example, every 10–15 minutes plus manual dispatch); it must not create an unbounded run storm. Exact cadence and recovery rate limits are implementation details to validate.

## 8. Options decision

| Option | Outcome |
|---|---|
| Native `queue: max` + reconciliation | **Adopt** |
| Dependabot schedule staggering and per-ecosystem PR cap | **Adopt** |
| Exact current-head coverage and duplicate-run avoidance | **Adopt** |
| Artifact marker as a global cooldown/queue | **Remove** |
| External durable scheduler and database | **Reject for current scope; revisit only with evidence** |
| Dedicated GitHub App | **Not needed for current design** |
| Ruleset or branch-protection change | **Not authorized / not required** |

## 9. Rollback and re-entry criteria

Rollback to the previous workflow behavior only through a reviewed PR and only if the new native queue path causes a demonstrated regression. Do not reintroduce the 300-second cooldown by default.

Reopen external-scheduler architecture only if measured evidence demonstrates one or more:
- native queue overflow occurs despite arrival shaping and bounded reconciliation;
- current PR heads repeatedly remain without a required check beyond the agreed recovery SLA;
- an auditable requirement emerges to execute every historical event SHA;
- GitHub native controls cannot provide reliable current-head coverage.

Any such redesign requires a new ADR and explicit approval.
