# Workflow Manager Roadmap

> For: anyone following where the Workflow Manager is going. Last checked with: Workflow Manager 1.7.0, Workflow 2.12.0.

The full text of earlier versions is in this file's git history; the last long version is [here](https://github.com/RodrigoFAbreu/workflow-manager/blob/de95195/docs/ROADMAP.md).

## How to read this roadmap

- Read **What's next** for the order of work, **Done** for what already shipped, and **Later** for open items that have no slot yet.
- Status words: **Done** (merged and released), **In progress** (a milestone is under way), **Next** (the item to start now), **Later** (wanted, not scheduled), **Waiting on ...** (blocked until the named thing exists).
- This file covers the Workflow Manager (the installer and updater) and the order of work across this repository and the `workflow` repository. M1, M2 and M3 are this file's milestone names.
- The Workflow's own plans and defects are in [the Workflow roadmap](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md). The Controller's are in [the Controller roadmap](https://github.com/RodrigoFAbreu/workflow-controller/blob/main/docs/ROADMAP.md). They are linked, not copied.
- Controller releases are installed into the shared Controller only between milestones, when no lane is running one.

## What's next

Items 1 to 4 and item 7 (Operator UX) are done. Item 8 (the release-agnostic Manager) is done. Items 5 and 6 wait on the Controller.

The end goal is a loop where the Controller takes the next roadmap item, plans, implements, reviews, tests, merges and releases it, then starts the next one. The order below is the owner's agreed order across this lane.

| Order | Item | What it gives you | Status or what it waits on |
|---|---|---|---|
| 1 | Documentation clean-up | Readable install, update and verify guides | Done (PR #16) |
| 2 | This roadmap clean-up | A roadmap you can read | Done |
| 3 | Small Workflow fix release | The `v2.6.0-003` fix, the latest governing version as the default for new work items, and `/retire-legacy-work-item`; then its pin here | Done (Workflow 2.9.0, pinned in Manager 1.5.0, PR #19) |
| 4 | Update ergonomics | `workflow-manager doctor`, `update --dry-run` and a compatibility report; safer upgrades for every repository | Done (PR #22, Manager 1.6.0) |
| 5 | Controller C10 (gate policy and automatic acceptance) | The Controller can use Workflow 2.8's gate policy | Waiting on the Controller; tracked in [the Controller repository](https://github.com/RodrigoFAbreu/workflow-controller/blob/main/docs/ROADMAP.md) |
| 6 | **M3**: this repository and `workflow` driven by the Controller's loop | Roadmap items worked, merged and released with no hand-driving | Waiting on the Controller's kanban runner (C11) |
| 7 | Operator UX | Error messages that name the cause and the next command, and `status` showing the work in flight | Done (accepted by policy 2026-10-10; Manager 1.8.0 releases when its pull request merges) |
| 8 | Release-agnostic Manager | A Workflow release installs without a Manager pin pull request or a Manager release | Done (accepted by policy 2026-10-17; Manager release follows the merge) |
| 9 | Host tests isolated from a stray ancestor `.git` (#66) | A green change no longer looks red when another process leaves a `.git` in the shared `/tmp` | Done (accepted by policy; a `test:` change, no release) |
| 10 | Follow-ups to the host-test Git isolation (#74) | The three small test-helper fixes the reviews of row 9 deferred | Done (accepted by policy; a test change, no release) |
| 11 | Host-test Git isolation: the last two follow-ups (#74) | The helper documents its valid-repository boundary, and empty ceiling markers are tested at every position | Next |

### 7. Operator UX (Done)

The documentation clean-up delivered most of this: install, update and verify guides, a common-problems page, and a documentation index. What remains is in the tool, not the docs, and this item delivers it: every error, refusal, warning and note names its cause and one concrete next step (a command, a flag or a page), using the real program name and options; recovery instructions appear in the output; and `status` shows the work in flight, so an operator does not need to read the state JSON. Exit codes stay as `docs/exit-codes.md` documents them. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_OPERATOR_UX_PLAN.md`. A `feat:` title, so it releases Manager 1.8.0.

### 8. Release-agnostic Manager (Done)

Every Workflow release forces a Manager pin pull request and a Manager release that adds nothing but the pin. This item removes that: the Manager discovers published Workflow releases and verifies each by its published `SHA256SUMS` and manifest digest, instead of only the digests pinned in `src/workflow_manager/published_releases.json`. Existing pins stay, are never changed, and stay authoritative for the releases they name. A release's manifest may carry the data the Manager hard-codes today (downgrade boundary, new-work-only fixes, gate-default change, frozen suite counts, portability exceptions, `min_manager_version`); an older Manager refuses a release that needs a newer one, and releases up to 2.12.0 keep the built-in data. Manager CI stays deterministic: a lock file names the Workflow releases it tests, and the nightly tests the newest published one. The Workflow-side change (writing those manifest fields) is a separate milestone in the `workflow` repository; its contract is [`release-metadata.md`](release-metadata.md). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RELEASE_AGNOSTIC_PLAN.md`. A `feat:` title, so it releases a Manager minor.

### 9. Host tests isolated from a stray ancestor `.git`

Two `tests/test_read_only.py` tests expect a plain scratch directory to be "no repository", but the runner puts scratch under `/tmp/wm-run-*/tmp/`, so a stray `/tmp/.git` left by another process makes Git discover it and the full gate fails with nothing wrong in the change under test (#66; seen on 2026-10-18 and 2026-10-19). Isolate Git discovery for the tests (for example `GIT_CEILING_DIRECTORIES` at the scratch root, in the runner or in those tests), with a regression test that plants a `.git` above the scratch root. Test and runner code only: no Manager behaviour change, so no Manager release (`test:`).

### 10. Follow-ups to the host-test Git isolation

Three Optional review findings from row 9 (#74), test code only: keep the empty-entry markers of an inherited `GIT_CEILING_DIRECTORIES` (`tests/parallel/isolation.py` `ceiling_with`, `tests/support.py` `no_repository_above`); make `no_repository_above` count `root/.git` for a target at or below `root`; give the `TestAncestorRepositoryIsolation` subprocess a timeout. No Manager behaviour change, so no Manager release (`test:`).

### 11. Host-test Git isolation: the last two follow-ups

What #74 still lists after row 10, test code only: `tests/support.py` `no_repository_above` documents that a *valid* repository at `root` is hidden by the Git ceiling for a target below it (the helper then refuses, where the unbounded product would protect it: fails closed), and advises a fixture that needs such a repository to pass a `root` above it; and the empty-ceiling-marker tests in `tests/test_orphan_processes.py` and `tests/test_read_only.py` cover leading (`:/mnt/a`), trailing (`/mnt/a:`) and repeated (`/mnt/a:::/mnt/b`) markers, not only an internal one. No Manager behaviour change, so no Manager release (`test:`).

## Done

Newest first.

- **Release-agnostic Manager** (2026-10-17, accepted by policy; the Manager release follows the pull request's merge, #38). A Workflow release published after a Manager release installs without a Manager pin pull request or a Manager release: the Manager discovers published releases and verifies each by its published `SHA256SUMS` and manifest digest; a release's manifest may carry the per-release compatibility data and `min_manager_version`; releases up to 2.12.0 keep their pins and built-in data; CI tests the releases a lock file names, and the nightly the newest published one. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RELEASE_AGNOSTIC_PLAN.md`.
- **Workflow 2.12.0 pinned** (2026-10-16). Published by the `workflow` repository (W8, workflow#28): from round 2 a plan or implementation review is given the changes since the last reviewed bundle in a gitignored `CHANGES_SINCE_REVIEW.md`, and a verdict is checked for shape before it becomes state. It writes no new key or value; Orchestration Protocol 1.4.
- **Workflow 2.11.0 pinned** (2026-10-13). Published by the `workflow` repository (W7, workflow#23): a plan revision's checkpoint anchors are checked when the revision is published, bound or turned into a plan-review bundle, instead of first at plan approval. It writes nothing new; Orchestration Protocol stays 1.3.
- **Workflow 2.10.0 pinned** (2026-10-12). Published by the `workflow` repository (W5, workflow#24): creating a new work item is refused while `default_workflow_version` is `"2.1"`; Orchestration Protocol 1.3; the managed CI workflow runs its suites in parallel and cancels a superseded pull-request run. `workflow-manager doctor` and `update --dry-run` warn about a `"2.1"` default whatever release is installed.
- **Workflow 2.9.2 pinned** (2026-10-11). A fix release built and published by the `workflow` repository (workflow#19 and #20): `/apply-functional-review`'s bounded branch commits the stale technical-approval write alone, then the fix, then the narrative and checklist, and the generation record last; the `Workflow-*` trailers are the final paragraph alone.
- **Operator UX** (2026-10-10, accepted by policy; Manager v1.8.0 releases when its pull request merges). Every error, refusal, warning and note of the Manager CLI names its cause and one concrete next step, and `status` shows the work in flight. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_OPERATOR_UX_PLAN.md`.
- **Workflow 2.9.1 pinned, Manager v1.7.0** (2026-10-10). A fix release built and published by the `workflow` repository (W4, workflow#13): a review stage's `REVISE` write is committed alone, so the post-fix round that follows it is no longer refused, and `APPROVE` writes stay uncommitted for the approval commit. Installed here the same day, so this repository runs its own milestones on 2.9.1.
- **Update ergonomics** (2026-10-09, PR #22, Manager v1.6.0). `workflow-manager doctor` and `update --dry-run` read a repository and report what an update would do and which Workflow guarantees it would cross, without writing it. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UPDATE_ERGONOMICS_PLAN.md`.
- **Small Workflow fix release** (2026-10-08, Workflow 2.9.0; pinned in Manager v1.5.0, PR #19). Built and published by the `workflow` repository. It fixes `v2.6.0-003`, makes the latest governing version the default for new work items, and adds `/retire-legacy-work-item`.
- **Documentation clean-up** (2026-10-04, PR #16). Readable user documentation with install, update and verify guides, a troubleshooting page and a documentation index.
- **Workflow 2.9.0 installed here** (2026-10-08, PR #21). Replaced by 2.9.1 above.
- **Workflow 2.8.0 pinned, Manager v1.4.0** (PR #14), and **2.8.0 installed here** (PR #15). Replaced by 2.9.0 above.
- **Workflow 2.7.0 pinned, Manager v1.3.0** (PR #13).
- **The `workflow` repository and its releases** (W0 to W2). Set up for development with CI and releases; it published Workflow 2.7.0 (Orchestration Protocol, first packaged release) and 2.8.0 (declarative gate policy, a red pull request reopening its work item). They are tracked in the Workflow roadmap, not here.
- **M2, packaged distribution** (2026-10-01, PR #11, Manager v1.2.0). Workflow moved to its own repository and is released as checksummed, immutable packages (2.3.1 to 2.6.0 published as a record). The Manager downloads, verifies and installs them, and caches them for offline use. `distribution/` and the stopgap test profile were removed. Record and evidence: `docs/MIGRATION.md`.
- **M1b, test cleanup** (2026-09-30, PR #10). Throwaway test repositories turn off Git's automatic maintenance, and a leak check fails a run that leaves orphaned processes. This stopped about 1,000 stray `git` processes per full run.
- **M1, trunk model** (2026-09-29, PR #4, Manager v1.1.0). Protected `main`, one short-lived branch per milestone, squash merges, and the release version derived from the pull-request title (a Conventional Commit). The Git tag is the only version authority. See `docs/RELEASING.md`.
- **Adaptive test sharding** (2026-09-28, PR #1). The full test run takes about 7 minutes locally instead of 36, and about 7 to 10 minutes in CI at 16 shards (2026-10-11: CI now plans 6 shards, each on all runner CPUs; see `docs/ARCHITECTURE.md`). Design: `docs/ARCHITECTURE.md`, "Verification execution".
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

### Review follow-ups: release-agnostic Manager (item 8)

These are the Optional review findings deferred at acceptance (the owner's rule of 2026-10-16). Each one is an issue labelled [`review-follow-up`](https://github.com/RodrigoFAbreu/workflow-manager/issues?q=is%3Aissue+label%3Areview-follow-up), and a later clean-up milestone works them off:

- #39: Floor edges outside bare update: --pinned-only with an installed discovered release, and doctor at the floor
- #40: Floor refusal: add a REASON for the --pinned-only case
- #41: doctor's "Latest available" on an explicit --release-version run can hide a newer discovered release
- #42: A malformed version such as v2.12.0 gets "not published" advice instead of "name a release as X.Y.Z"
- #43: Specify partial manager-block objects (conformance: {} and missing nested fields)
- #44: Revisit refusing the whole release for a manager block of the wrong shape
- #45: Pre-screen the pin binding from the manifest asset before fetching the archive
- #46: Refuse duplicate filenames in SHA256SUMS
- #47: ReleaseFloorError's docstring does not name the none-at-floor kind
- #48: CLI test: a traversal version through an installation record stays inside the cache
- #49: CLI test: doctor exits 0 on an up-to-date post-2.12.0 installation with an unreadable source
- #50: _http_read abandons its worker thread and socket when the deadline expires
- #51: Overlapping frozen orphan keys in tests/parallel/resources.json silently overwrite each other
- #52: The nightly saves a new cache entry on every run

## Principles

1. **Published releases are immutable.** Fixes ship as a new release, in the `workflow` repository.
2. **Work items keep the version that governs them.** Installing a newer Workflow never silently rewrites an existing item.
3. **Fail closed, recover cleanly.** Unknown or stale state stops progress with a clear recovery step.
4. **Never migrate live work-item state.** Targets get clean templates.
5. **One home for each fact.** Do not add files that restate what state, ledgers, bundles or Git already record; derive views on demand.
6. **Say what changes before changing it.** Dry runs and reports come before writes.
7. **Try it on a disposable copy first**, before a long-lived repository.
