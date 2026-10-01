# Workflow Manager Roadmap

## Purpose

This roadmap captures the planned evolution of `workflow-manager` and the Workflow distribution after the current 2.5.x baseline.

The roadmap prioritizes correctness, migration safety, review-artifact integrity, and concurrency semantics before broader ergonomics or new Workflow features.

The guiding rule is additive evolution:

- frozen releases remain immutable;
- fixes ship through a new Workflow release;
- existing active work items are not silently rewritten;
- migration behavior must remain explicit, reviewable, and fail-closed.

---

## At a glance

**Where things stand (2026-10-01).**
- **The Workflow is its own product now.** M2 published releases 2.3.1 to 2.6.0 as immutable,
  checksummed packages in `RodrigoFAbreu/workflow`, and the Manager (v1.2.0) installs from them.
  The Workflow's roadmap (W0-W2 and the Workflow sections that were here) lives in that
  repository's `docs/ROADMAP.md` (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md). This roadmap keeps the Manager's items and
  the cross-repository order.
- This repository and the Workflow Controller both run Workflow 2.6.0.
- The Controller admits 2.5.1 and 2.6.0 since its release 1.3.0, which completes the integration
  half of 1.9.
- Adaptive test sharding is on `main`.

**Where this is heading: a kanban loop.** The Workflow Controller takes the next open roadmap
item, plans it, implements it, reviews it, tests it, merges it and releases it, then starts the
next one, until the roadmap is empty. In the end no human gate is left:
- approvals pass on local plus automated cross-model review evidence;
- acceptance passes when the automated functional review finds nothing;
- pull requests merge themselves on green required checks.

This repository's part is to:
- work the same trunk-based way the Controller does;
- ship Workflow as downloadable packages;
- deliver the protocol and the gate policy the Controller needs.

**Two lanes run in parallel**, one milestone at a time in each: the Workflow Controller, and this
repository together with the new `workflow` repository. They meet where the Controller consumes
Workflow 2.7 (W1) and 2.8 (W2).

**Manager and Workflow lane, in order:**

| # | Step | Repository | Section |
|---|---|---|---|
| M1 | Trunk model, plus the stopgap test profile until M2 (COMPLETE) | Workflow Manager | [10.1](#101-m1-trunk-model-and-the-stopgap-test-profile) |
| M1b | Test cleanup: throwaway test repositories leave no orphaned Git processes, and a leak check (COMPLETE) | Workflow Manager | [10.1b](#101b-m1b-test-cleanup-no-orphaned-git-processes) |
| M2 | Distribution rework: Workflow in its own repository, released as downloadable packages (COMPLETE) | Workflow Manager, `workflow` | [10.2](#102-m2-distribution-rework-packaged-workflow-releases) |
| W0 | The `workflow` repository set up for development: CI, the release workflow, branch protection, its own Workflow installation, and its roadmap | `workflow` | [workflow roadmap](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md) |
| W1 | Workflow 2.7, the first packaged release: Orchestration Protocol v1, and the `v2.6.0-001` and `v2.6.0-002` follow-ups | `workflow` | [workflow roadmap](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md) |
| W2 | Workflow 2.8: declarative gate policy, and a red or changes-requested pull request reopening the same work item | `workflow` | [workflow roadmap](https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md) |
| M3 | This repository and `workflow` driven by the Controller's loop | both | [10.3](#103-m3-driven-by-the-controllers-loop) |

**Controller releases are installed only between Manager milestones**, never during one. That
covers the Controller's own C1 release (1.4.0) and its zombie-process fix (a patch release). Until
the fix is installed, this lane runs the Controller one step per process (`--max-steps 1`); see
10.1b.

**The Controller lane** (its roadmap owns it):
1. squash merges and Conventional-Commit PR-title versions;
2. CI reliability;
3. settings file, cleanup and telemetry;
4. auto-merge and release wait;
5. SignalHub notifications;
6. automated lifecycle scenarios;
7. a Codex review seam;
8. a usage budget;
9. the Controller on the protocol (needs W1);
10. gate policy and automatic acceptance (needs W2);
11. the kanban runner.

**Deferred** because they do not unlock that operating model:
- RepFlow upgrade (2, 3): now the RepFlow lane's, straight to the latest Workflow release;
- review-data simplification (4, moved to the `workflow` roadmap);
- update ergonomics (5);
- multi-worktree maturity (7, moved to the `workflow` roadmap);
- operator UX (8).

Section 6 is replaced by M2.

The numbered sections below keep their historical numbers; this table is the current order.

---

# 0. Current Baseline

The Workflow release records (2.3.1 to 2.6.0) moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md), section 0. This repository's own baseline follows.

---

## Repository tooling: adaptive test sharding

**Status:** COMPLETE. Accepted as milestone `workflow-manager-adaptive-test-sharding`, a `process` work item scoped from the user's milestone brief rather than from a section of this roadmap. It changes no Workflow release. Its plan is `docs/ai-workflow/WORKFLOW_MANAGER_ADAPTIVE_TEST_SHARDING_PLAN.md`.

`python3 tests/run_all.py` still runs the complete test set, and every test it ran before. It is now faster:

- locally, about 6.5-7 min instead of 36 min serial;
- in CI, about 7-10 min at 16 shards through `.github/workflows/workflow-manager-verify.yml`. The single-shard reference takes 110.8 min.

It gets there through:

- a deterministic inventory;
- duration-balanced shards;
- isolated parallel chunks, protected by a write barrier and a run lock;
- a CI matrix generated from the plan.

`docs/ARCHITECTURE.md`'s "Verification execution" has the design. It also sets the policy that a serial or single-shard run is exceptional evidence, not a routine check.

Follow-ups left open by the accepted implementation:

- A per-commit CI concurrency group for `main`. Today's per-ref group can cancel an intermediate `main` run while it is still pending.
- Two optional hardening items:
  - A cleanup failure after the report can still turn a printed exit 0 into exit 2.
  - An interrupt inside `Popen`'s fork-to-exec window is not covered.
- The 5-minute CI target (P-3) needs about 24 shards, above the account's 20-job cap.

It is on `main` since 2026-09-28. The per-commit `main` concurrency group is folded into M1.

---

# 1. Review Artifact, Publication, and Concurrency Hardening (moved)

Moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md), sections 1 and 1.9, when the Workflow became its own product in M2 (2026-10-01).

---

# 1.9 Post-2.6 Controller integration and Workflow Orchestration Protocol foundation (moved)

Moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md), section 1.9: the source of W1 and W2.

---

# 2. RepFlow Upgrade Rehearsal

**Priority:** the RepFlow lane's, right after its current milestone (user decision, 2026-09-30).

RepFlow (`~/Workspace/repflow-android`) runs Workflow 2.3.1. The earlier plan was to validate a
migration on a disposable copy and then migrate RepFlow once, straight to Workflow 2.7 (W1).
**That plan is replaced:** once `repflow-redesign-visual-foundation` is accepted and merged on 2.3.1,
RepFlow upgrades straight to the **latest published Workflow release** (2.6.0 today). The RepFlow
lane rehearses it first on a throwaway clone:

- `workflow-manager bootstrap --force` from the published package (Manager v1.2.0 or later, which
  downloads and verifies it), then `verify`;
- `workflow-controller explain` and `inspect` on the clone;
- a check that `v2.4.0-001` (the installation record left unclassified at the plan stage) is
  fixed there;
- no unexpected protected-path drift, and no rewritten historical work-item bindings.

The upgrade is one-way: the downgrade constraints in `CLAUDE.md` ("Downgrade posture") apply, so a
repository on 2.6.0 never goes back.

---

# 3. Real RepFlow Upgrade

**Priority:** after the rehearsal passes; run by the RepFlow lane, never from this repository.

Move the actual RepFlow repository to the latest published release through supported
`workflow-manager update`/`bootstrap` semantics:

- resume product work under the current Workflow;
- avoid manual compatibility hacks;
- never rewrite historical work-item bindings, and preserve governing Workflow versions;
- fail closed on unresolved historical incompatibilities;
- RepFlow starts using the Workflow Controller only after its upgrade, and Controller releases are
  installed only between Manager milestones.

This repository's sessions still treat `~/Workspace/repflow-android` as read-only.

---

# 4. Review Data / History Simplification (moved)

Moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md), section 4, when the Workflow became its own product in M2 (2026-10-01).

---

# 5. Workflow Manager Update and Migration Ergonomics

**Priority:** Medium

Make update behavior easier to reason about for operators.

Potential improvements:

- stronger preflight before updating a repo with active work items;
- explicit compatibility report:
  - installed Workflow version;
  - active work items;
  - governing versions;
  - forward-only fixes that do not apply retroactively;
  - migration hazards;
- dry-run update;
- migration plan output;
- clearer recovery instructions;
- explicit distinction between:
  - installed release;
  - work-item governing release;
  - latest available release.

Potential command shape:

```text
workflow-manager doctor
workflow-manager update --dry-run
```

---

# 6. Distribution and Release Quality

**Status:** Replaced by M2 ([10.2](#102-m2-distribution-rework-packaged-workflow-releases)), which delivers these goals through packaged releases.

**Priority:** Medium (historical)

Improve release production and verification.

Goals:

- deterministic release build;
- authoritative version source;
- immutable distribution outputs;
- provenance for overlay-derived files;
- release checksum manifest;
- stronger release-delta reporting;
- CI proving:
  - frozen historical releases unchanged;
  - newly built release matches checked-in distribution;
  - migration overlays apply deterministically;
  - conformance suites pass for every supported release.

---

# 7. Multi-Worktree and Concurrency Model Maturity (moved)

Moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md), section 7, when the Workflow became its own product in M2 (2026-10-01).

---

# 8. Operator UX / Documentation

**Priority:** Ongoing

Improve:

- error messages;
- actionable recovery instructions;
- lifecycle diagrams;
- migration documentation;
- distinction between repairable operator state and genuine Workflow defects;
- exact commands that parse as printed;
- fewer situations requiring manual inspection of state JSON.

---

# 9. Longer-Term Workflow Evolution (moved)

Moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md), section 9, when the Workflow became its own product in M2 (2026-10-01).

---

# 10. Trunk-based delivery and packaged distribution

## 10.1 M1: trunk model and the stopgap test profile

**Status:** COMPLETE. Accepted as milestone `workflow-manager-trunk-model`
on 2026-09-29, from `milestone/workflow-manager-trunk-model` (pull request
#4). The cutover (`docs/RELEASING.md`, "Cutover") is complete: `main` is
protected by the ruleset, merges are squash-only, pull request #4 merged as
`59158c6`, and the first tag-derived Manager release, `v1.1.0`, is
published. Design: `docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md`.

This repository works the way the Workflow Controller does:

- a protected `main`, changed only through pull requests, with required checks;
- one short-lived branch per milestone;
- squash merges, with the release version derived from the pull request title, as in SignalHub
  and the Controller:
  - the title must be a Conventional Commit (`feat: …`, `fix: …`, `feat!: …`), checked by a
    required check;
  - it becomes the squash commit's subject;
  - its type decides the bump (`feat` minor, `fix` patch, `!` major);
  - `docs`, `chore` and `ci` merge without a release;
  - the Git tag is the only version authority, and nobody edits a version file: the release
    computes the next version from the latest tag and the commit type, and sets the package's
    version at build time (decided 2026-09-29, as in the Controller's C1);
- auto-merge on green required checks;
- a Workflow Manager package release published from `main`;
- a per-commit CI concurrency group for `main`, so an intermediate `main` run is never cancelled
  (the sharding milestone's open follow-up).

M1 releases the Manager only. It creates no Workflow release.

**Stopgap test profile, until M2.** About 96% of today's roughly 25,000 tests re-run the frozen
suites of all five Workflow releases, in three fixtures each. A pull request runs the host tests and
the newest release only. `main` and a nightly run keep the full matrix. The stopgap comes with these
rules, which must be implemented together with it and not dropped:

1. A pull request that touches the installer, the fixture builder, the shared test infrastructure
   or `distribution/` runs the **full** matrix.
2. The Manager release waits for `main`'s full run, so a red `main` publishes nothing and is fixed
   forward.
3. One aggregate summary check is the required check, so the required checks stay stable whatever
   the shard count.
4. `docs/ARCHITECTURE.md`'s policy that a targeted run is never a gate is updated, as a reviewed
   decision.
5. A nightly failure is loud (a badge or a notification), and the next pull request runs the full
   matrix.
6. The second CI profile is removed when M2 lands.

**Follow-up, ready once a Controller release with its C1 ships (`OD-4`).**
Add a Controller repository policy for this repository: milestone branches
enabled, the release section disabled (this repository releases through
`.github/workflows/release.yml`), validated with that release's
`workflow-controller inspect`. It must reach `main` before the milestone
that first uses it starts, since adoption reads it at the branch point. M1
adds none: under Controller 1.3.0 a policy would name draft pull requests
with a non-Conventional title, end every squash merge in
`MERGED_REWRITTEN`, and require a `version_change`/`pyproject` release
model that M1 removes.

## 10.1b M1b: test cleanup, no orphaned Git processes

**Status:** COMPLETE. Accepted as milestone `workflow-manager-test-cleanup` on 2026-09-30, from
`milestone/workflow-manager-test-cleanup` (pull request #10, titled `test: throwaway test
repositories leave no orphaned Git processes`, which releases nothing). Design:
`docs/ai-workflow/WORKFLOW_MANAGER_TEST_CLEANUP_PLAN.md`. Follow-up, not fixed there: the runner has
no SIGINT handler of its own, so a run started with `&` from a non-interactive shell ignores SIGINT
and one runner test times out (observation O1, present at the base `7dabd2e`).

**Why.** Since Git 2.55, a commit can start detached background maintenance. The tests make
thousands of commits in throwaway repositories, so one full test run leaves about 1,000 orphaned
`git` processes. Workflow Controller 1.3.0 adopts those orphans (it is a Linux subreaper for its
workers) but only collects the ones it saw alive, so they stay as zombies until the Controller
exits. On 2026-09-29 they filled the per-user process limit and every Claude Code session on the
machine aborted. The Controller fix belongs to the Controller lane. This milestone stops the
orphans at the source, in this repository's tests.

- **Throwaway test repositories turn off Git's automatic maintenance.** The shared test setup
  (the fixture builder and the test infrastructure) sets `maintenance.auto=false` and `gc.auto=0`
  in every repository it creates. Setting them through the environment is not enough: tests start
  Git with their own clean environment. The tests also get a little faster.
- **A leak check.** A test run, or the CI job, fails when the suite leaves orphaned background
  processes behind, so the next tool that starts detaching processes shows up in CI, not as a
  crash.
- **Kept small.** The big test reduction (only the release in development plus the upgrade path)
  stays in M2.
- **Full matrix.** It changes the fixture builder and the test infrastructure, so M1's stopgap
  rule 1 runs its pull request on the full matrix.

**After it, between milestones:** install the Controller release that carries the zombie fix, and
drop `--max-steps 1` from this lane's Controller runs.

## 10.2 M2: distribution rework, packaged Workflow releases

**Status:** COMPLETE. Accepted as milestone `workflow-manager-packaged-distribution` on
2026-10-01, from `milestone/workflow-manager-packaged-distribution` (pull request #11, titled
`feat: Workflow releases are downloaded, verified packages`, which releases the Manager's
`v1.2.0`). Design: `docs/ai-workflow/WORKFLOW_MANAGER_PACKAGED_DISTRIBUTION_PLAN.md`; the record
and its evidence: `docs/MIGRATION.md`. The five releases `2.3.1` to `2.6.0` are published as
immutable packages in `RodrigoFAbreu/workflow`. Follow-ups, not done there: each new Workflow
release still needs a small Manager pull request that adds its pin (`OD-M2-2`), and
`--manager-root` survives one release as a deprecated alias.

- **Workflow moves to its own repository** (`workflow`). It holds only the release in development,
  with its own version and release stream: one product per repository.
- **A Workflow release is a package.** A versioned archive is published as a release asset with
  `SHA256SUMS` and a manifest, and it is immutable once published.
- **Every earlier release is published as a package too**, 2.3.1 through 2.6.0, as a record, even if
  nothing installs it. Each is checked byte for byte against today's `distribution/` tree before
  that tree is removed.
- **The Manager downloads, verifies and installs.** `bootstrap` and `update --release-version X`
  fetch the package and check it against the published checksums, and refuse on any mismatch.
  Downloaded packages are cached locally, so an offline machine or CI can still install a version
  it already has.
- **`distribution/` leaves this repository.** The Manager tests its own code, plus the release in
  development in its three fixtures, plus the upgrade path from the latest published release. Old
  releases are tested once, when they are built, and never again.
- **The stopgap test profile (10.1) is removed.** `docs/ARCHITECTURE.md`'s
  "Stopgap test profile" lists exactly the files that carry it (the
  `STOPGAP(M2)` marker), what to delete, and the gate-policy exception to
  drop with them.

M2 publishes the existing releases as packages; it creates no new Workflow version. The first new
one is W1, Workflow 2.7.

## 10.3 M3: driven by the Controller's loop

**Priority:** after the Controller's kanban runner.

This repository and `workflow` run the same loop the Controller runs on its own repository: the
next roadmap item, one run, merge, release, next.

---

# Suggested Execution Order

The current order is the table in [At a glance](#at-a-glance). The diagram below is the earlier order, kept as a record.

```text
0. Workflow 2.5.1 baseline                                      CURRENT INSTALLED BASELINE
   |
1. Review artifact/publication/concurrency hardening -> 2.6.0   COMPLETE
   |                       \
   |                        \ Controller trunk/PR/release milestone runs in parallel
   |                         \
1.9 Small Controller <-> released 2.6 integration               NEXT
   |
2. Workflow Orchestration Protocol foundation / decoupling
   |
3. Disposable RepFlow migration validation
   |
4. Real RepFlow Workflow migration
   |
5. Review-data/history simplification
   |
6. Workflow Manager migration/update ergonomics
   |
7. Distribution/release quality
   |
8. Broader multi-worktree concurrency maturity
   |
9. Operator UX/documentation
   |
10. Longer-term Workflow evolution
```

---

# Defect Disposition Summary (moved)

Moved to the `workflow` repository's roadmap (https://github.com/RodrigoFAbreu/workflow/blob/main/docs/ROADMAP.md): Workflow defects are that product's. The write-ups stay in this repository's `docs/defects/`.

---

# Roadmap Principles

1. **Frozen releases are immutable.**  
   Fixes ship as new authored releases.

2. **Work-item governance is durable.**  
   Installing a newer Workflow does not silently rewrite the semantics of an already-governed work item.

3. **Review identity must describe exactly what was reviewed.**  
   Approval commits, bundles, ledgers, and protected-path declarations must remain consistent.

4. **Publish only durable truths.**  
   Workflow must not claim a review-ready or approved state before the artifacts required by that state are valid and durable.

5. **Fail closed, but recover cleanly.**  
   Unknown classification, stale artifacts, and conflicting ownership should stop progress with actionable recovery rather than corrupt state.

6. **Repository-wide claims require repository-wide primitives.**  
   A worktree-local lock cannot establish a repository-wide concurrency guarantee.

7. **Legacy compatibility must be explicit.**  
   Forward-generated fixes are not automatically retroactive fixes for already-approved work items.

8. **Avoid duplicating review/history state.**  
   Each review fact has one canonical home; do not add persistent files that restate what state, ledgers, bundles, or Git already record.

9. **Prefer minimal canonical state and generated views.**  
   Derive projections on demand rather than maintaining more persistent bookkeeping.

10. **Dogfood migrations before touching real long-lived repositories.**  
    RepFlow disposable migration remains a required proving ground.
