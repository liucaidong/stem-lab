# R03-SCH-04.7 — Controlled Native Queue Validation

**Status: ACCEPTED WITH DOCUMENTED PLATFORM-BOUNDARY LIMITATION**  
**Date:** 2026-11-04 (UTC evidence timestamps below are 2026-11-03)  
**Repository:** `liucaidong/stem-lab`  
**Branch:** `security/r03-sch-04-01-event-task-audit`  
**Test SHA:** `3fdfc3a355031891ac1703869c68e6a2e2b5d2b4`

## 1. Objective and unchanged contract

Validate the configured GitHub Actions workflow-level concurrency contract without creating a large CI burst:

```yaml
concurrency:
  group: stem-lab-global-ci
  cancel-in-progress: false
  queue: max
```

The test did not modify the workflow, `main`, Ruleset `26463757`, or required check `CI result`. PR #33 remained Draft / OPEN / unmerged. No historical PR workflow was rerun, dispatched, cancelled, closed, or recovered.

## 2. Controlled below-limit burst

Three `workflow_dispatch` runs were triggered against the same branch and exact head SHA. The live Actions API showed one run in progress while the next two remained pending in the same workflow concurrency group.

| Run | Run ID | Observed queue state | Final result | CI result |
|---|---:|---|---|---|
| 1 | [41737913014](https://github.com/liucaidong/stem-lab/actions/runs/41737913014) | First run in progress; completed at 23:19:36Z | `completed / success` | `completed / success` |
| 2 | [41737946696](https://github.com/liucaidong/stem-lab/actions/runs/41737946696) | Pending from 23:17:22Z; jobs began at 23:19:39Z after Run 1 completed | `completed / success` | `completed / success` |
| 3 | [41737952333](https://github.com/liucaidong/stem-lab/actions/runs/41737952333) | Pending from 23:17:25Z; jobs began at 23:22:03Z after Run 2 completed | `completed / success` | `completed / success` |

All three workflow runs used head SHA `3fdfc3a355031891ac1703869c68e6a2e2b5d2b4`, attempt 1. All three aggregate checks were named exactly `CI result`, had conclusion `success`, used GitHub Actions App ID `15368`, and linked to their corresponding run IDs:

- Run `41737913014`: check job `126272829800`, started `23:19:31Z`.
- Run `41737946696`: check job `126273933947`, started `23:21:55Z`.
- Run `41737952333`: check job `126275154940`, started `23:24:38Z`.

Observed behavior: two pending runs were retained; neither was replaced or cancelled; the runs drained sequentially in the observed wait order. This is evidence for the tested three-run burst, not a claim of a strict event-dispatch FIFO guarantee.

## 3. Queue overflow contract and fault injection

GitHub documents `queue: max` as allowing up to 100 pending jobs or workflow runs per concurrency group. When the queue is full, additional runs are cancelled/rejected. See:

- [GitHub Actions concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub Changelog — larger concurrency queues, 2026-05-07](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/)

The repository's offline reconciliation fault test now models the overflow-relevant terminal state: an older exact-SHA successful run and successful check are followed by a newer cancelled run. The expected and asserted classification is `RECOVERY_REQUIRED`; the older success must not mask the latest cancellation. This protects against false success if GitHub cancels/rejects a run at queue capacity.

No live 101-run overflow test was performed. Reaching the actual limit would require intentionally filling the production concurrency group and submitting additional runs, which would create the CI storm this scheduling change is intended to avoid. The numeric limit is therefore grounded in GitHub's published platform contract; cancellation/reconciliation behavior is validated through offline fault injection, not a live saturation experiment.

## 4. Scope limitations

- The live burst proves retention and sequential draining for two pending runs, not acceptance of all 100 pending slots.
- Native queue ordering is not treated as strict FIFO by event-dispatch timestamp. Actual waiting/start times can differ.
- GitHub-managed Dependabot dynamic workflows are not assumed to inherit this custom workflow's concurrency group and are outside this burst test.
- This test does not authorize or perform recovery of the 16 historical `RECOVERY_REQUIRED` PR targets.

## 5. Acceptance evidence

- [x] Workflow concurrency policy remains `stem-lab-global-ci` / `cancel-in-progress: false` / `queue: max`.
- [x] Three-run controlled burst produced one active and two pending runs.
- [x] All three runs completed successfully and drained sequentially in observed wait order.
- [x] All three `CI result` checks succeeded for the exact same head SHA and Actions App ID `15368`.
- [x] Latest cancellation cannot be masked by an older successful run (offline fault-injection regression test).
- [x] No live overflow storm, historical PR recovery, Ruleset mutation, or `main` mutation was performed.
- [x] PR #33 remains Draft / OPEN / unmerged.

**Conclusion:** U7 is accepted for the bounded native queue contract with an explicit, evidence-based limitation: the live test validates below-limit queue retention and draining; the 100-pending saturation threshold is taken from GitHub's documented platform limit, while overflow cancellation is covered by offline fail-closed reconciliation tests.
