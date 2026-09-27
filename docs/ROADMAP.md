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

# 0. Current Baseline

## Workflow 2.3.1

**Status:** Frozen historical baseline.

Important properties:

- original reusable Workflow baseline;
- preserved byte-for-byte;
- no in-place semantic repairs.

Known defects discovered against 2.3.1 have either been fixed in later authored releases or retained only as historical records.

### Closed defect: v2.3.1-001 — host-history-coupled conformance test

**Disposition:** Fixed in Workflow 2.5.0.

The affected integration test previously assumed target repositories carried RepFlow-specific historical prose in `docs/ACTIVE_MILESTONE.md`.

Workflow 2.5.0 made the check portable by skipping the host-specific assertion when the historical note is absent.

No new implementation work is planned for this defect.

### Closed defect: v2.3.1-002 — no legal plan-amendment edge

**Disposition:** Fixed in Workflow 2.4.0.

Workflow 2.3.1 had no supported transition from implementation back into plan revision/review when the approved plan itself needed to change.

Workflow 2.4.0 introduced:

- `AMENDING_PLAN`;
- `/request-plan-amendment`;
- amendment reconciliation;
- approval supersession/re-approval semantics;
- checkpoint/amendment quiescence within one worktree.

No new implementation work is planned for the missing-edge defect itself.

### Closed defect: v2.3.1-003 — first plan approval requires precommitted `WORKFLOW_STATE.json`

**Disposition:** Fixed in Workflow 2.5.0.

The plan-approval transaction previously required `WORKFLOW_STATE.json` to already exist at `HEAD` so it could reuse the tracked file mode.

Workflow 2.5.0 now falls back to mode `100644` when no previous tracked state blob exists.

The fix is regression-tested and should remain preserved.

---

## Workflow 2.4.0

**Status:** Complete authored release.

Primary feature:

- first-class approved-plan amendment during implementation.

Delivered:

- `AMENDING_PLAN`;
- `/request-plan-amendment`;
- approval supersession and reconciliation;
- amendment-specific review behavior;
- same-worktree amendment/checkpoint quiescence.

Known follow-up defects remain and are tracked below.

---

## Workflow 2.5.0

**Status:** Complete authored release.

Primary feature:

- two-stage implementation review:
  - local model implementation review;
  - manual external implementation review;
- both bound to the same implementation identity.

Additional improvements:

- review scalability/convergence improvements;
- separation of current normative review state from immutable history;
- generated/canonical review data where practical;
- reduced duplicated self-audit bookkeeping;
- multiple portability/correctness fixes inherited from earlier defect records.

Important fixes carried here:

- v2.3.1-001 host-history portability;
- v2.3.1-003 first plan-approval state-blob mode fallback;
- implementation-stage `.workflow-manager/` classification for newly generated artifact declarations.

---

## Workflow 2.5.1

**Status:** Current installed baseline for this repository.

Primary purpose:

- compatibility/correctness follow-up for checkpoint identifiers and surrounding Workflow machinery.

This is the base release the 2.6.0 hardening overlay was built from. This repository intentionally remains installed on 2.5.1 until the post-2.6 Controller integration step (1.9) moves consumers to the released 2.6.x.

---

## Workflow 2.6.0

**Status:** Complete authored release — accepted as milestone `workflow-review-artifact-and-concurrency-hardening` (section 1).

Delivered:

- per-work-item/scoped review feedback storage (new work items stamped `feedback_layout: "scoped"`);
- legacy `.workflow-manager/installation.json` compatibility handling for active legacy work items (release-derived, exact-path terminal fallback; no declarations rewritten);
- plan-review publication/binding hardening (`/apply-plan-review` ordering and recovery, `plan_review_binding`, `.ai-review/<id>/plan-inputs/`);
- approval commit closure for newly introduced protected paths;
- cross-worktree amendment/checkpoint coordination (repository-global lifecycle lock plus amendment witness under the common git dir);
- correct, non-empty `AMENDMENT_DIFF.patch` anchored at the working tree;
- regression preservation for v2.3.1-001, v2.3.1-002 and v2.3.1-003.

Documented residuals / follow-ups left by the accepted implementation:

- `v2.4.0-002` is closed **qualified**: mixed-release worktrees remain unsupported until every registered worktree's branch has merged the 2.6.0 update (see the defect record's 2.6.0 disposition and `CLAUDE.md`);
- `v2.4.0-001`'s separate `workflow_manager update`-rewrites-protected-paths hazard for an active `process` work item is out of scope and belongs to milestone 5;
- `v2.6.0-001` (withdrawn plan-stage content can re-bind after a detour) is open — partially mitigated in 2.6.0, mandatory follow-up for a later Workflow release.

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

This milestone does not change the order below: 1.9 stays NEXT.

---

# 1. Review Artifact, Publication, and Concurrency Hardening

**Status:** COMPLETE — accepted as Workflow 2.6.0 (milestone `workflow-review-artifact-and-concurrency-hardening`, commit `136c417`).

The subsections below are retained as the milestone's scope record; see "Workflow 2.6.0" above and the Defect Disposition Summary for outcomes.

**Priority:** Immediate / High (delivered)

Suggested milestone:

`workflow-review-artifact-and-concurrency-hardening`

This milestone groups the remaining Workflow correctness and operator-friction defects around:

- review feedback ownership;
- review publication correctness;
- approval commit integrity;
- active-work-item migration compatibility;
- amendment artifacts;
- cross-worktree concurrency.

It should be a bounded Workflow hardening release, not a general redesign.

---

## 1.1 Per-work-item review feedback storage

### Problem

Review feedback currently converges through the shared path:

```text
.ai-review/feedback/REVIEW_FEEDBACK.md
```

Ownership guards correctly prevent one work item from overwriting feedback owned by another, but this creates recurring operational friction:

- a completed work item's stale feedback file blocks a new work item;
- the next review worker exits after doing all review work but before persisting its verdict;
- operators must manually copy/delete the stale file before retrying.

This has now interrupted multiple real Controller milestones.

### Required direction

Move review feedback to work-item-scoped storage.

Preferred minimal shape:

```text
.ai-review/<work-item-id>/feedback/REVIEW_FEEDBACK.md
```

This file is the current, ephemeral feedback surface for its work item. It preserves the existing feedback document format and lifecycle semantics.

Durable review history stays where it already lives: Workflow state, review ledgers, bundles, and Git.

### Non-goal: per-stage / per-round feedback files

Do not introduce persistent per-stage or per-round feedback storage such as:

```text
.ai-review/<work-item-id>/feedback/plan-local/round-1.md
.ai-review/<work-item-id>/feedback/implementation-local/round-2.md
```

It would improve filesystem-level history, but at the cost of:

- more review-artifact noise and agent context overhead;
- more cleanup and migration rules;
- a higher risk of stale artifacts being mistaken for current state;
- duplicating history the canonical mechanisms already preserve.

### Required semantics

- new work items use scoped feedback storage;
- unrelated work items cannot block one another through a shared feedback file;
- active legacy work items using the shared path remain supported;
- completed legacy feedback must never block a new work item;
- do not silently reinterpret a legacy feedback file as belonging to a different work item;
- review/apply/manual-record commands resolve feedback through one authoritative helper;
- Controller should consume the Workflow-resolved feedback location instead of hard-coding the old shared path;
- cleanup/ownership rules must remain fail-closed.

### Affected areas

At minimum:

- `/review-plan`;
- `/apply-plan-review`;
- `/review-implementation`;
- `/apply-implementation-review`;
- manual external plan-review recording;
- manual external implementation-review recording;
- feedback ownership helpers;
- review admissibility/reconciliation;
- tests and migration compatibility.

---

## 1.2 Legacy active-work-item compatibility for `.workflow-manager/installation.json`

**Status:** Closed in 2.6.0 (`v2.4.0-001` 2.6.0 disposition).

### Current state

The forward-looking classification problem is already mostly fixed:

- Workflow 2.4.0 added `.workflow-manager/` to newly generated plan-stage exclusions;
- Workflow 2.5.0 added the same behavior to newly generated implementation-stage exclusions.

Therefore newly created work items are generated correctly.

### Remaining problem

Existing work items whose artifact declarations were generated before those fixes remain exposed.

A Workflow Manager update can commit:

```text
.workflow-manager/installation.json
```

inside an active work item's `base_commit..HEAD` interval.

The old work item's declarations do not know how to classify that path, so review/approval reachability can fail with an unclassified-path error.

This is especially relevant during migration of long-lived repositories such as RepFlow.

### Required outcome

Design a migration-safe compatibility mechanism for active legacy work items without silently rewriting their approved protected-path declarations.

The solution must answer:

- how known Workflow Manager-owned metadata is classified for a pre-existing work item;
- how compatibility is authorized and recorded;
- how plan approval identity remains trustworthy;
- whether compatibility is release-derived, migration-derived, or explicit per-work-item metadata;
- how to avoid broad rules such as "ignore everything under `.workflow-manager/`".

### Non-goal

Do not reopen the already-correct forward-generated declarations for new work items except where needed for consistency.

---

## 1.3 `/apply-plan-review` publication ordering and recovery

### Problem

A previously reproduced failure showed this sequence:

```text
revision N
  |
/apply-plan-review
  |
Workflow state advances to revision N+1 / AWAITING_LOCAL_PLAN_REVIEW
  |
new review bundle generation fails
```

The durable Workflow state then claims revision N+1 is review-ready while the current review bundle is still revision N.

Controller correctly fails closed on this stale-bundle mismatch, but Workflow itself should not publish contradictory durable state.

### Required outcome

Make the transition to a review-ready plan revision transactional or explicitly recoverable.

Preferred semantic shape:

```text
prepare revised plan state
generate + validate review artifacts
publish the review-ready durable state only after required artifacts exist
```

If full atomicity is impractical, introduce an explicit intermediate/recovery state where the Workflow never claims the new review round is ready before the matching bundle is durable.

### Requirements

- never advertise a review-ready revision before its matching required bundle exists and validates;
- deterministic recovery after process failure;
- safe retry;
- no duplicate revision advancement;
- review bundle identity and durable state remain bound;
- Controller stale-bundle gates remain valid defense-in-depth, not the primary repair mechanism.

---

## 1.4 Plan approval commit closure

### Problem

The reviewed plan-stage content can include a newly introduced protected file that the approval commit fails to include.

The failure shape is:

```text
reviewed:
A + B + C + D

approval commit:
A + B + C
```

where `D` is a valid newly introduced protected plan-stage file.

Post-approval verification then recomputes review identity from the approval commit tree and no longer sees the exact content that was approved.

### Required outcome

The approval commit closure must be derived from the complete declared protected plan-stage set, not only a fixed list of conventional artifacts.

### Requirements

- every protected plan-stage path contributing to the approved review identity is present in the approval commit tree;
- new protected companion/reference files work without special-case code;
- deleted/renamed protected paths are handled deterministically;
- approval commit verification proves exact reviewed-content closure;
- regression test reproduces the previously observed new-file case.

---

## 1.5 Cross-worktree amendment/checkpoint correctness

### Defect

`v2.4.0-002-amendment-claim-race-crosses-worktree-boundary`

**Status:** Closed, qualified, in 2.6.0 — closed for every repository whose registered worktrees have all merged the 2.6.0 update; mixed-release worktrees remain unsupported (residual stated in the defect record's 2.6.0 disposition).

### Problem

The existing amendment/checkpoint serialization works only inside one worktree root.

Two linked worktrees can still independently decide:

- worktree A: plan amendment may begin;
- worktree B: checkpoint claim may begin.

The defect has two independent causes:

1. the current state lock is worktree-local, so the two processes do not serialize on the same lock;
2. Workflow phase lives in each worktree's own tracked `WORKFLOW_STATE.json`, so one worktree cannot authoritatively observe another worktree's newly committed `AMENDING_PLAN` phase merely by taking a shared lock.

### Required outcome

Establish a repository-wide guarantee, not only a same-worktree guarantee.

A complete repair must address both:

- repository-global serialization/ownership;
- repository-global visibility/witness of the conflicting lifecycle condition.

### Likely design work

Potential ingredients include:

- a `git_common_dir` / claims-rooted mutation lock;
- a repository-global amendment witness/lease;
- explicit lock ordering with existing claim/guard/journal primitives;
- durable crash recovery;
- stale witness detection;
- clear ownership rules.

### Required tests

- amendment begins first -> checkpoint claim cannot start from another worktree;
- checkpoint claim begins first -> amendment cannot begin from another worktree;
- real-process cross-worktree racing case;
- deterministic non-concurrent stale-phase case;
- crash while holding amendment ownership;
- crash while holding checkpoint ownership;
- no deadlock with existing guard/claim/journal locks;
- same-worktree behavior remains correct.

### Important constraint

Do not land only a partial fix that closes the shared-lock problem but leaves foreign-worktree phase visibility stale.

The defect is closed only when both causes are addressed.

---

## 1.6 `AMENDMENT_DIFF.patch` correctness

### Defect

`v2.4.0-003-amendment-diff-anchored-at-head-is-always-empty`

**Status:** Closed in 2.6.0 (repair form 1, working-tree anchor).

### Problem

During plan review of an open amendment, the generated convenience artifact currently behaves like:

```bash
git diff "${amendment_base_commit}..HEAD" -- <plan-stage protected paths>
```

The amended plan-stage files are still uncommitted during review, so `HEAD` does not contain them.

The result is an empty `AMENDMENT_DIFF.patch` even though the working tree contains real amendment changes.

### Preferred repair

Generate the amendment diff against the working tree:

```bash
git diff "${amendment_base_commit}" -- <plan-stage protected paths>
```

This matches how plan-stage review identity already reasons about uncommitted reviewed content.

### Requirements

- local and manual external reviewers see the same meaningful amendment diff;
- documentation accurately describes the chosen anchor;
- artifact remains convenience-only unless intentionally promoted into identity semantics;
- existing review identity/bundle identity rules remain unchanged unless explicitly redesigned;
- regression test proves a real uncommitted amendment generates a non-empty diff.

---

## 1.7 Preserve previously closed defect fixes

The milestone must explicitly regression-test that nearby changes do not reopen:

### v2.3.1-001

Host-history-specific integration test remains portable.

### v2.3.1-002

First-class plan amendment edge remains intact.

### v2.3.1-003

First-ever plan approval still succeeds when `WORKFLOW_STATE.json` has no prior `HEAD` entry.

These are not implementation scope; they are protected regressions.

---

## 1.8 Functional / migration acceptance

The milestone should include disposable-repository exercises covering:

1. fresh work item using scoped feedback;
2. completed old work item's feedback cannot block a new item;
3. active legacy work item still resolves its existing feedback correctly;
4. Workflow Manager update during a legacy active work item;
5. plan-review remediation with intentional bundle-generation failure/recovery;
6. plan approval with a brand-new protected file;
7. cross-worktree amendment/checkpoint contention;
8. non-empty amendment diff during an open amendment;
9. update from Workflow 2.5.1 to the new release without corrupting active state.

---

# 1.9 Post-2.6 Controller integration and Workflow Orchestration Protocol foundation

**Priority:** NEXT — the 2.6 hardening release has been accepted as Workflow 2.6.0.

The 2.6 hardening milestone (now complete) and the Controller trunk/branch/PR/release milestone run independently in parallel.

After both complete, perform a small integration milestone first:

- upgrade the Controller repository from Workflow 2.5.1 to the released 2.6.x;
- verify the actual released contract rather than planning against unreleased details;
- replace the Controller's copied feedback-path resolver with Workflow's authoritative resolver/query;
- update/re-measure Controller expectations that still name Workflow internal state writers;
- validate 2.5.1 -> 2.6.x migration and current Controller lifecycle behavior.

After that compatibility step, introduce a stable Workflow-facing orchestration protocol so later Workflow releases normally do not require Controller lifecycle-code changes.

## Public orchestration protocol

The protocol should be a versioned public contract, separate from both:

- Workflow release version (`2.6.0`, `2.7.0`, ...);
- the work item's governing Workflow version (`2.1`, `2.2`, ...).

Initial operations:

1. `describe`
   - Workflow release;
   - orchestration protocol version;
   - supported governing versions;
   - capabilities.

2. `verify`
   - repository/installation/state health;
   - protocol readiness.

3. `next-action`
   - normalized state snapshot;
   - semantic action id and arguments;
   - disposition:
     - `automatic`;
     - `validation`;
     - `human_gate`;
     - `external_gate`;
     - `blocked`;
     - `complete`;
   - generic worker requirements;
   - state revision / state identity.

4. `reconcile`
   - Workflow-authoritative classification of the durable result of an action;
   - must recognize same-phase progress such as one checkpoint completing while phase remains `IMPLEMENTING`;
   - returns progress/result class and new state identity.

5. `record-external-result`
   - ingest typed external/manual evidence without requiring Controller to know Workflow-owned storage paths.

6. `resolve-artifact`
   - narrow semantic artifact resolver when another component genuinely needs a path.

Optional convenience:

- `inspect` for CLI/UI/debugging.

## Protocol design constraints

- public semantic action ids, not internal Python helper/function names;
- Workflow may return a rendered command invocation, but command text is not the protocol identity;
- artifact locations remain Workflow-owned;
- Controller should not copy feedback/bundle/path selection rules;
- state revision/identity must make stale decisions detectable;
- unknown protocol major fails closed;
- broad stable protocol error codes may accompany precise Workflow-native exceptions;
- exact Workflow releases may be recorded as tested/validated combinations, but should not remain the fundamental compatibility mechanism.

Target compatibility:

```text
Workflow 2.6.x ─┐
Workflow 2.7.x ─┤
Workflow 2.9.x ─┤── Orchestration Protocol v1 ── Controller
Workflow 3.x   ─┘
```

## Gate and validation policy must be declarative

Workflow must own the meaning of lifecycle gates rather than assuming today's user-gate layout forever.

Future supported policies may include:

- plan approval automatically satisfied by current local + independent cross-model review evidence;
- implementation technical acceptance automatically satisfied by current review evidence;
- functional validation satisfied automatically by configured integration/E2E/migration evidence;
- human functional acceptance only where repository/risk policy requires it;
- PR review/merge as the final external/human acceptance boundary.

The protocol must therefore distinguish:

- automation-safe action;
- automated validation;
- human gate;
- external gate;
- blocked/refused state;
- completion.

Removing a human gate must not require Controller lifecycle-code changes if the public protocol contract remains compatible.

## Post-validation reopening and PR-review defects

"Validation passed" is not irreversible milestone completion.

The Workflow model should support an external gate result such as PR `CHANGES_REQUESTED` reopening the same work item into remediation.

Required semantic shape:

```text
technical review
  -> functional validation
  -> PR ready
  -> external PR review
       -> approved/merged
       -> or changes requested -> remediation -> re-review/re-validation -> PR ready
```

Evidence/readiness must be bound to exact implementation / PR-head identity.

When the Controller's forge adapter reports facts such as:

- PR head SHA changed;
- PR review requested changes;
- checks changed;
- PR reopened/closed/merged;

Workflow decides:

- which evidence became stale;
- whether technical review must repeat;
- whether full or targeted functional validation is required;
- what the next legal action is.

The Controller must not encode those invalidation rules itself.

## Functional validation evolution

For repositories where manual functional testing is weak or repetitive, Workflow should support strong automated functional evidence.

Examples:

- Workflow / Workflow Manager:
  - disposable-repository scenarios;
  - migration suites;
  - integration/conformance suites;
  - real lifecycle E2E exercises.

- RepFlow:
  - Room migration tests;
  - Compose/UI tests;
  - emulator/device E2E flows;
  - backup/restore and navigation/session flows.

Repository policy may still require human product/visual acceptance even when automated evidence passes.

The long-term principle is:

> stop for a human only when policy says available automation/evidence is insufficient for the next decision.

---

# 2. RepFlow Migration Validation

**Priority:** Immediately after the post-2.6 Controller integration and Orchestration Protocol foundation (1.9)

Once the hardening release is complete, repeat the real migration scenario against a disposable RepFlow copy.

This is the primary acceptance target for the hardening work.

## Required validation

- preserve the existing active work item;
- update/bootstrap through `workflow-manager`;
- ensure `.workflow-manager/installation.json` does not break the active item;
- run plan review/remediation;
- verify scoped feedback does not collide with previous work items;
- verify review publication cannot leave state ahead of artifacts;
- exercise amendment behavior if relevant;
- confirm no unexpected protected-path drift;
- verify Controller can operate the migrated Workflow cleanly.

Only after this succeeds should the real RepFlow repository be migrated.

---

# 3. Real RepFlow Workflow Migration

**Priority:** After disposable validation passes

Move the actual RepFlow Android repository to the current Workflow release.

Goals:

- resume product/redesign work under the hardened Workflow;
- avoid manual compatibility hacks;
- validate a long-lived repository with historical work items and reviews;
- use RepFlow as a continuing integration target for Workflow Manager.

Constraints:

- do not rewrite historical work-item bindings;
- preserve governing Workflow versions;
- migrate through supported update/bootstrap semantics;
- fail closed on unresolved historical incompatibilities.

---

# 4. Review Data / History Simplification

**Priority:** Medium

Continue the convergence/scalability work begun in Workflow 2.5.0.

Potential areas:

- clearer separation of normative current review state from immutable history;
- fewer duplicated review facts across state, ledgers, bundles, and feedback;
- generated projections instead of manually synchronized copies;
- better historical indexing;
- compact long-running work-item state;
- easier audit without increasing author/reviewer bookkeeping.

Principle:

> One authoritative fact, multiple generated views.

Review storage stays intentionally minimal: one current feedback file per work item (milestone 1.1), with history held in the existing canonical mechanisms. Add persistent review files only when a concrete requirement cannot be met by state, ledgers, bundles, Git, or a generated view.

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

**Priority:** Medium

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

# 7. Multi-Worktree and Concurrency Model Maturity

**Priority:** Later / Ongoing

After the specific amendment/checkpoint race is fixed, review the broader concurrency model systematically.

Areas:

- repository-global vs worktree-local primitives;
- claim ownership;
- guard ownership;
- plan-amendment ownership;
- journal transactions;
- lock ordering;
- crash recovery;
- stale lease detection;
- multiple unrelated work items in linked worktrees.

Goal:

Document which invariants are:

- repository-wide;
- work-item-wide;
- worktree-local;
- process-local.

Then mechanically test those scopes.

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

# 9. Longer-Term Workflow Evolution

Potential future work:

- stronger transactional publication primitives;
- generalized repository-global lifecycle leases;
- reduced review convergence cost;
- better review-history compaction;
- versioned Workflow Orchestration Protocol for Controller integration;
- declarative gate/validation policy;
- semantic external-result ingestion and post-validation reopening;
- compatibility contracts for Controller/Workflow Manager integrations;
- deprecation policy for very old governing Workflow releases;
- migration tooling for retiring historical compatibility branches.

---

# Suggested Execution Order

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

# Defect Disposition Summary

| Defect                                                                       | Status                                        | Roadmap disposition        |
| ---------------------------------------------------------------------------- | --------------------------------------------- | -------------------------- |
| `v2.3.1-001-host-history-coupled-tests`                                      | Fixed in 2.5.0                                | Regression protection only |
| `v2.3.1-002-no-plan-amendment-edge`                                          | Fixed in 2.4.0                                | Regression protection only |
| `v2.3.1-003-plan-approval-requires-precommitted-state-file`                  | Fixed in 2.5.0                                | Regression protection only |
| `v2.4.0-001-workflow-manager-installation-record-unclassified-at-plan-stage` | Closed in 2.6.0 (legacy active-item gap)      | Regression protection; separate update-rewrites-protected-paths hazard -> milestone 5 |
| `v2.4.0-002-amendment-claim-race-crosses-worktree-boundary`                  | Closed, qualified, in 2.6.0                   | Mixed-release worktrees unsupported (documented residual) |
| `v2.4.0-003-amendment-diff-anchored-at-head-is-always-empty`                 | Closed in 2.6.0                               | Regression protection only |
| `v2.6.0-001-withdrawn-plan-content-can-rebind-after-a-detour`                | Open; partially mitigated in 2.6.0            | Mandatory follow-up in a later Workflow release |

Additional hardening items delivered in milestone 1 (Workflow 2.6.0):

- shared review-feedback ownership/contention;
- `/apply-plan-review` publication ordering/recovery;
- plan approval commit closure for newly introduced protected files.

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
