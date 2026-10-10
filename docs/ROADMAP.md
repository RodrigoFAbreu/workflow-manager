# Workflow Manager Roadmap

> For: anyone following where the Workflow Manager is going. Last checked with: Workflow Manager 1.7.0, Workflow 2.9.1.

The full text of earlier versions is in this file's git history; the last long version is [here](https://github.com/RodrigoFAbreu/workflow-manager/blob/de95195/docs/ROADMAP.md).

## How to read this roadmap

- Read **What's next** for the order of work, **Done** for what already shipped, and **Later** for open items that have no slot yet.
- Status words: **Done** (merged and released), **Next** (the item to start now), **Later** (wanted, not scheduled), **Waiting on ...** (blocked until the named thing exists).
- This file covers the Workflow Manager (the installer and updater) and the order of work across this repository and the `workflow` repository. M1, M2 and M3 are this file's milestone names.
- The Workflow's own plans and defects are in [the Workflow roadmap](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md). The Controller's are in [the Controller roadmap](https://github.com/RodrigoFAbreu/workflow-controller/blob/main/docs/ROADMAP.md). They are linked, not copied.
- Controller releases are installed into the shared Controller only between milestones, when no lane is running one.

## What's next

Nothing is Next right now. Items 1 to 4 are done. Items 5 and 6 wait on the Controller, and item 7 is Later. The next step is the Controller's, not this repository's.

The end goal is a loop where the Controller takes the next roadmap item, plans, implements, reviews, tests, merges and releases it, then starts the next one. The order below is the owner's agreed order across this lane.

| Order | Item | What it gives you | Status or what it waits on |
|---|---|---|---|
| 1 | Documentation clean-up | Readable install, update and verify guides | Done (PR #16) |
| 2 | This roadmap clean-up | A roadmap you can read | Done |
| 3 | Small Workflow fix release | The `v2.6.0-003` fix, the latest governing version as the default for new work items, and `/retire-legacy-work-item`; then its pin here | Done (Workflow 2.9.0, pinned in Manager 1.5.0, PR #19) |
| 4 | Update ergonomics | `workflow-manager doctor`, `update --dry-run` and a compatibility report; safer upgrades for every repository | Done (PR #22, Manager 1.6.0) |
| 5 | Controller C10 (gate policy and automatic acceptance) | The Controller can use Workflow 2.8's gate policy | Waiting on the Controller; tracked in [the Controller repository](https://github.com/RodrigoFAbreu/workflow-controller/blob/main/docs/ROADMAP.md) |
| 6 | **M3**: this repository and `workflow` driven by the Controller's loop | Roadmap items worked, merged and released with no hand-driving | Waiting on the Controller's kanban runner (C11) |
| 7 | Operator UX | Clearer errors and recovery steps | Later (deferred); see below |

### 7. Operator UX (Later, deferred)

The documentation clean-up delivered most of this: install, update and verify guides, a common-problems page, and a documentation index. What remains is in the tool, not the docs: error messages that say what to do next, recovery instructions in output, and fewer cases where an operator has to read state JSON. Update ergonomics delivered part of it. The rest has no slot yet.

## Done

Newest first.

- **Workflow 2.9.1 pinned, Manager v1.7.0** (2026-10-10). A fix release built and published by the `workflow` repository (W4, workflow#13): a review stage's `REVISE` write is committed alone, so the post-fix round that follows it is no longer refused, and `APPROVE` writes stay uncommitted for the approval commit.
- **Update ergonomics** (2026-10-09, PR #22, Manager v1.6.0). `workflow-manager doctor` and `update --dry-run` read a repository and report what an update would do and which Workflow guarantees it would cross, without writing it. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UPDATE_ERGONOMICS_PLAN.md`.
- **Small Workflow fix release** (2026-10-08, Workflow 2.9.0; pinned in Manager v1.5.0, PR #19). Built and published by the `workflow` repository. It fixes `v2.6.0-003`, makes the latest governing version the default for new work items, and adds `/retire-legacy-work-item`.
- **Documentation clean-up** (2026-10-04, PR #16). Readable user documentation with install, update and verify guides, a troubleshooting page and a documentation index.
- **Workflow 2.9.0 installed here** (2026-10-08, PR #21), so this repository runs its own milestones on 2.9.0.
- **Workflow 2.8.0 pinned, Manager v1.4.0** (PR #14), and **2.8.0 installed here** (PR #15). Replaced by 2.9.0 above.
- **Workflow 2.7.0 pinned, Manager v1.3.0** (PR #13).
- **The `workflow` repository and its releases** (W0 to W2). Set up for development with CI and releases; it published Workflow 2.7.0 (Orchestration Protocol, first packaged release) and 2.8.0 (declarative gate policy, a red pull request reopening its work item). They are tracked in the Workflow roadmap, not here.
- **M2, packaged distribution** (2026-10-01, PR #11, Manager v1.2.0). Workflow moved to its own repository and is released as checksummed, immutable packages (2.3.1 to 2.6.0 published as a record). The Manager downloads, verifies and installs them, and caches them for offline use. `distribution/` and the stopgap test profile were removed. Record and evidence: `docs/MIGRATION.md`.
- **M1b, test cleanup** (2026-09-30, PR #10). Throwaway test repositories turn off Git's automatic maintenance, and a leak check fails a run that leaves orphaned processes. This stopped about 1,000 stray `git` processes per full run.
- **M1, trunk model** (2026-09-29, PR #4, Manager v1.1.0). Protected `main`, one short-lived branch per milestone, squash merges, and the release version derived from the pull-request title (a Conventional Commit). The Git tag is the only version authority. See `docs/RELEASING.md`.
- **Adaptive test sharding** (2026-09-28, PR #1). The full test run takes about 7 minutes locally instead of 36, and about 7 to 10 minutes in CI at 16 shards. Design: `docs/ARCHITECTURE.md`, "Verification execution".
- **RepFlow upgrade.** RepFlow's own lane did it. RepFlow is on Workflow 2.9.0 since 2026-10-08 (repflow-android PR #8, merge 7b33182), adopted through Manager 1.5.0, and its legacy milestone-8 is retired. It keeps its adopted gate policy, unchanged, which keeps every gate human. Using the Controller is the owner's decision for RepFlow. Done for this roadmap.
- **Old sections that moved or were replaced** (review artifacts, review-data simplification, multi-worktree, long-term evolution, release quality): now in the Workflow roadmap or replaced by M2.

## Later (open items)

Not scheduled. Each is small unless noted.

- **Controller repository policy for this repository.** What: a Controller policy file with milestone branches enabled and the release section disabled (this repository releases through `.github/workflows/release.yml`). Why: lets the Controller drive this repository, and it must reach `main` before the milestone that first uses it starts. Direction: validate it with the Controller's `inspect`. Belongs with M3.
- **Retire the `--manager-root` alias.** It is kept as a deprecated alias of the old layout (`src/workflow_manager/cli.py`). Remove it in a later breaking release (`feat!:`).
- **Test runner hardening.** Three small follow-ups from the sharding and cleanup milestones:
  - the runner has no interrupt handler of its own, so a run started with `&` from a non-interactive shell ignores SIGINT and one runner test times out;
  - a cleanup failure after the report can turn a printed exit 0 into exit 2;
  - an interrupt inside the fork-to-exec window of a spawned process is not covered.
- **A 5-minute CI target.** It needs about 24 shards; the account's cap is 20 parallel jobs. Revisit if the cap changes or the test set shrinks.

## Principles

1. **Published releases are immutable.** Fixes ship as a new release, in the `workflow` repository.
2. **Work items keep the version that governs them.** Installing a newer Workflow never silently rewrites an existing item.
3. **Fail closed, recover cleanly.** Unknown or stale state stops progress with a clear recovery step.
4. **Never migrate live work-item state.** Targets get clean templates.
5. **One home for each fact.** Do not add files that restate what state, ledgers, bundles or Git already record; derive views on demand.
6. **Say what changes before changing it.** Dry runs and reports come before writes.
7. **Try it on a disposable copy first**, before a long-lived repository.
