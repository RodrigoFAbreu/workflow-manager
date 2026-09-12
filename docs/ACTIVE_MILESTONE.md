# Active Milestone

## Milestone

**Approved-plan amendment: a first-class Workflow mechanism for safely
amending an already-approved plan after implementation has begun.**

Frozen Workflow v2.3.1 (`docs/ai-workflow/MILESTONE_WORKFLOW.md`) has no
documented transition from `IMPLEMENTING` or `SELF_REVIEWING_IMPLEMENTATION`
back into plan revision/review. A sibling repository
(`workflow-controller`, work item `workflow-controller-generation-1`,
phase `SELF_REVIEWING_IMPLEMENTATION`, checkpoint `CP9`) hit this gap for
real: its approved CP3/CP4 architecture has no zero-work-item decision path,
which its REQ-T18 disposable-repo scenario needs, and the fix is an
approved-plan amendment the frozen lifecycle has no legal path to apply.
That repository is out of scope here and must not be touched or read from a
live session — this milestone is planning a Workflow-manager-side capability,
not fixing the Controller.

## Goal

Design and land, in this repository's own successor Workflow release (never
by editing the frozen v2.3.1 `distribution/` in place), the smallest robust
mechanism for amending an approved plan mid-implementation, plus what is
needed to deliver and deploy it:

1. **The amendment mechanism itself** (a new first-class state-machine
   capability, additive to v2.3.1's existing states/transitions):
   - which post-plan-approval phases may request one (at minimum
     `IMPLEMENTING` and `SELF_REVIEWING_IMPLEMENTATION`);
   - what explicit operator/user authority is required to request one (no
     `USER_OVERRIDE`, no undocumented manual transitions);
   - how the current plan approval becomes stale/superseded/retired safely;
   - how the work item legally re-enters plan revision/review;
   - how fresh local/manual plan review (the `"2.1"` two-stage protocol) is
     performed for the amended plan;
   - how a new plan approval becomes the implementation basis;
   - the disposition of already-completed checkpoints and commits
     (retained / invalidated / selectively revalidated), and how
     implementation safely resumes afterward;
   - how `review_content_id`, bundle identity, approval commits, ancestry,
     and protected-path bindings are handled across the amendment, without
     weakening any existing approval binding;
   - crash recovery, interruption recovery, and idempotence throughout;
   - compatibility with repositories already managed by v2.3.1, and whether
     any state schema/version migration is required.
2. **Successor-release mechanics**: the authoring path inside this
   repository (`migration/classification.json`, `tools/migrate.py`, and
   this repo's existing release conventions) that produces the successor
   Workflow release carrying the amendment, keeping v2.3.1 byte-identical
   and frozen, plus the regeneration/release validation this repo's
   `CLAUDE.md` "Before changing anything" / "Adding a Workflow release"
   sections already require.
3. **Workflow Manager update-path validation**, on disposable repositories
   only, before any real managed repository (including the paused
   Controller repo, later, out of scope here) is touched: a normal
   v2.3.1-managed repo, one in `IMPLEMENTING`, and one in
   `SELF_REVIEWING_IMPLEMENTATION` (matching the Controller's blocker
   shape) — each updated to the successor release with pre-existing
   approvals/state/bindings verified to survive or transform exactly per
   the new contract, then exercising the new amendment mechanism, fresh
   plan re-review/re-approval, and safe resumption of implementation.

Scope is deliberately narrow: this covers only safe mid-implementation
approved-plan amendment, the successor-release mechanics to deliver it, and
the update-path validation to deploy it. It explicitly excludes the larger
review-history/context-scalability redesign, and it must never touch
`~/Workspace/workflow-controller`.

## Current checkpoint

None.

## Current blockers

None.

## Active plan

None. `/milestone-plan` records the plan document path on the work item's
`WORKFLOW_STATE.json` entry when a work item is created.

## Functional review checklist

All testing below happens against **disposable, throwaway repositories**
only — never `~/Workspace/repflow-android` (frozen, read-only; read it via
`git show <tag>:<path>` if needed) and never `~/Workspace/workflow-controller`
(the out-of-scope repository that motivated this milestone; it must not be
touched or read during this review, even though it is the real-world reason
this mechanism exists).

### Setup

1. From this repository's root, confirm both releases still reproduce:
   ```
   python3 tools/migrate.py --check --upstream ~/Workspace/repflow-android
   python3 tools/build_release.py --overlay migration/overlays/2.4.0 --check
   ```
2. Create a scratch directory outside this repo, e.g. `/tmp/wf-amend-check/`.
3. Create and bootstrap the first disposable target repo directly on the new
   release. `--release-version` is a top-level `workflow_manager` argument —
   it must precede the subcommand, not follow it. The target must already be
   a Git repository *before* bootstrap runs, and needs a baseline commit
   afterward: `drive_synthetic_work_item_through_checkpoints` (and every
   command that resolves a `base_commit`) reads `git rev-parse HEAD`, which
   fails outright on a repository with no commits at all.
   ```
   mkdir -p /tmp/wf-amend-check/repo-a
   git -C /tmp/wf-amend-check/repo-a init -q -b main
   git -C /tmp/wf-amend-check/repo-a config user.email "check@example.invalid"
   git -C /tmp/wf-amend-check/repo-a config user.name "Functional Check"
   git -C /tmp/wf-amend-check/repo-a config commit.gpgsign false
   PYTHONPATH=src python3 -m workflow_manager --release-version 2.4.0 bootstrap /tmp/wf-amend-check/repo-a
   git -C /tmp/wf-amend-check/repo-a add -A
   git -C /tmp/wf-amend-check/repo-a commit -q -m "baseline: bootstrap workflow 2.4.0"
   ```
4. Create and bootstrap the second disposable target repo the same way, on
   the *old* release, to exercise the update path in Flow 7:
   ```
   mkdir -p /tmp/wf-amend-check/repo-b
   git -C /tmp/wf-amend-check/repo-b init -q -b main
   git -C /tmp/wf-amend-check/repo-b config user.email "check@example.invalid"
   git -C /tmp/wf-amend-check/repo-b config user.name "Functional Check"
   git -C /tmp/wf-amend-check/repo-b config commit.gpgsign false
   PYTHONPATH=src python3 -m workflow_manager --release-version 2.3.1 bootstrap /tmp/wf-amend-check/repo-b
   git -C /tmp/wf-amend-check/repo-b add -A
   git -C /tmp/wf-amend-check/repo-b commit -q -m "baseline: bootstrap workflow 2.3.1"
   ```

### Test data

No product/feature content is needed — the mechanism under test is the
Workflow lifecycle itself. Each flow below drives a synthetic `process`-type
work item (e.g. `amendment-check-1`) through checkpoints inside a disposable
repo, using either `src/workflow_manager/fixture.py`'s
`drive_synthetic_work_item_through_checkpoints` (fastest, scripted) or the
repo's own installed slash commands directly (closer to a real operator's
experience — prefer this for at least one flow).

### Flow 1 — request an amendment while `IMPLEMENTING`

1. In `repo-a`, drive a synthetic work item to `IMPLEMENTING` with one
   checkpoint remaining (e.g. `checkpoint_ids=("CP1","CP2","CP3")`,
   `complete_checkpoint_ids=("CP1","CP2")`).
2. Run `/request-plan-amendment <work-item-id>` (user-only; supply the
   confirmation text it asks for).
3. **Expected:** phase transitions to `AMENDING_PLAN`; the prior
   `plan_approval` becomes `SUPERSEDED`; CP1/CP2 remain `COMPLETE`; nothing
   about the checkpoint registry is silently discarded.

### Flow 2 — re-plan, re-review, re-approve, and reconcile checkpoints

1. In `repo-a`, from `AMENDING_PLAN`, run `/milestone-plan <work-item-id>`
   with a small plan change (e.g. drop CP2's requirement, add a new
   checkpoint `CP4`). Every checkpoint id in the amended registry (`CP1`,
   `CP3`, `CP4`) must have at least one well-formed
   `<!-- CP<n> -->` ... `<!-- /CP<n> -->` anchor pair wrapping its own
   section of the plan document — add these by hand if `/milestone-plan`
   doesn't; `/approve-review plan` refuses an amendment whose plan text is
   missing this coverage or misuses the anchor grammar (see Flow 2a).
2. Take the amended plan through local review (`/review-plan`) and manual
   review (`/record-manual-plan-review`), then
   `/approve-review plan <work-item-id>`.
3. **Expected:** `apply_plan_approval`'s amendment branch runs
   `reconcile_checkpoints_after_amendment`; CP1 (untouched) reports
   `retained`; a checkpoint whose own requirement changed reports
   `needs_revalidation`; a checkpoint only affected via dependency closure
   reports the distinct `needs_revalidation_dependency`; a dropped checkpoint
   reports `dropped`. The outcome is recorded on the work item's
   `amendment_history` entry and, per `D-Plan-Amendment-4`, is surfaced in
   `/approve-review plan`'s own output — confirm it actually appears there,
   not only in `WORKFLOW_STATE.json`.

### Flow 2a — amendment checkpoint-anchor and registry/checkpoint-id validation

Flow 2 above is this sub-flow's happy path: a valid, fully anchored amended
plan going through review and approval cleanly. Before (or after) completing
it for real, exercise each refusal below as its own throwaway
`/milestone-plan` + `/review-plan` + `/record-manual-plan-review` +
`/approve-review plan` attempt against the same `repo-a` `AMENDING_PLAN`
work item. Each attempt must fail, leaving `plan_approval` still
`SUPERSEDED` and no reconciliation outcome recorded, so Flow 2 still has a
clean amendment to resolve once these are done.

1. **Missing anchor:** author the same small change as Flow 2 (drop CP2, add
   `CP4`), but leave `CP4` with no `<!-- CP4 -->`/`<!-- /CP4 -->` pair
   anywhere in the plan document. Run the review/approval sequence.
   **Expected:** refused by name with `AmendmentAnchorCoverageError`, naming
   the uncovered checkpoint id, raised before any reconciliation outcome is
   computed.
2. **Malformed anchor:** repeat, this time giving one checkpoint id (e.g.
   `CP1`) an unmatched open tag (`<!-- CP1 -->` with no matching
   `<!-- /CP1 -->` before end of document) or an orphan `<!-- /CP1 -->` with
   no preceding open tag. **Expected:** refused by name with
   `AmendmentAnchorMalformedError`.
3. **Anchor-incompatible checkpoint id introduced by the amendment:** repeat
   once more, naming the new checkpoint `CP2b` (not `CP<digits>`) instead of
   `CP4`, regardless of anchors. **Expected:** refused by name with
   `AmendmentCheckpointIdShapeError` — distinct from the two cases above,
   since no anchor text could ever satisfy an id of this shape, and distinct
   from `/request-plan-amendment`'s own id-shape precondition in Flow 1
   (that one checks ids already in the *pre*-amendment registry; this one
   checks an id the amendment itself introduces).
4. **Malformed post-registry:** with the plan document otherwise validly
   anchored, edit `docs/ai-workflow/registry/<work-item-id>-registry.json`
   directly to remove its top-level `"checkpoints"` key entirely before
   running `/approve-review plan <work-item-id>`. **Expected:** refused by
   name with `AmendmentPostRegistryMalformedError`, never an unnamed
   `KeyError`.

### Flow 3 — resume implementation after reconciliation

1. Run `/milestone-implement <work-item-id>` repeatedly.
2. **Expected:** checkpoints reconciled as `retained` are skipped; anything
   `needs_revalidation`/`needs_revalidation_dependency`/new is
   (re)implemented; the item eventually reaches
   `SELF_REVIEWING_IMPLEMENTATION` again cleanly.

### Flow 4 — amendment during `SELF_REVIEWING_IMPLEMENTATION`

1. Drive a second synthetic work item straight to
   `SELF_REVIEWING_IMPLEMENTATION` (`complete_checkpoint_ids=checkpoint_ids`).
2. Run `/request-plan-amendment` again.
3. **Expected:** the same `AMENDING_PLAN` transition and reconciliation
   behavior as Flow 1/2, reachable from this phase too.

### Flow 5 — amendment vs. checkpoint-claim quiescence (same worktree)

1. In a fresh synthetic work item mid-`IMPLEMENTING`, acquire a checkpoint
   claim (`claim_checkpoint`) without completing it, then attempt
   `/request-plan-amendment` concurrently in the *same* worktree.
2. **Expected:** exactly one side wins — either the amendment refuses because
   a checkpoint is claimed/`IN_PROGRESS`, or the claim itself refuses once
   `AMENDING_PLAN` has landed. It must never be possible to end with
   `AMENDING_PLAN` *and* a live outstanding claim in the same worktree.
3. **Known limitation, not a regression to chase:** this guarantee is scoped
   to a single worktree root — see
   `docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`.
   Do not expect quiescence across two separate worktrees of the same repo.

### Flow 6 — authored-release production

1. `python3 tools/build_release.py --overlay migration/overlays/2.4.0 --check`
   must reproduce `distribution/workflow/2.4.0/` exactly from base `2.3.1`
   plus the overlay.
2. `python3 tools/migrate.py --check --upstream ~/Workspace/repflow-android`
   must show `2.3.1` byte-identical to the frozen tag — confirm this
   milestone did not alter it.

### Flow 7 — update path (disposable repos only)

1. In `repo-b` (bootstrapped on `2.3.1` above), drive one synthetic work item
   to `IMPLEMENTING` (one checkpoint left) and a second to
   `SELF_REVIEWING_IMPLEMENTATION`.
2. Run
   `PYTHONPATH=src python3 -m workflow_manager --release-version 2.4.0 update /tmp/wf-amend-check/repo-b`.
3. **Expected:** both work items' existing plan/technical approvals,
   `WORKFLOW_STATE.json` bindings, and checkpoint history survive the update
   untouched; `/request-plan-amendment` becomes available afterward for both.
4. Repeat against a plain `2.3.1` repo with no in-flight work item, confirming
   an ordinary update with nothing to preserve still succeeds cleanly.

### Known limitations / out of scope

- Cross-worktree amendment/claim races are a documented residual
  (`docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`),
  not a defect to re-open during this review.
- `docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`
  (bootstrap's first-ever plan approval requiring a pre-committed
  `WORKFLOW_STATE.json`) and
  `docs/defects/v2.4.0-001-workflow-manager-installation-record-unclassified-at-plan-stage.md`
  (`.workflow-manager/installation.json` unclassified for pre-existing items)
  are pre-existing/residual Workflow-Manager-side defects, out of this
  milestone's scope — do not treat them as new findings here.
- Four Optional documentation/test-apparatus items from the final
  implementation-review round (evidence-regex anchoring hardening on older
  pinning classes, a narrower "new cases" count derivation than the
  surrounding prose, stale "~7 min"/`--fast` suite-count description text, a
  `sleep(0.2)` test-synchronization primitive in one race regression) were
  explicitly accepted as non-gating polish, not defects — do not re-raise
  them as functional findings.
- `~/Workspace/workflow-controller` must never be touched or read during this
  testing.
- `AmendmentRegistryMissingIdError` (a pre-existing registry checkpoint entry
  with no `id` key at all) and `/request-plan-amendment`'s own id-shape
  precondition against the *pre*-amendment registry are both raised against
  registry shapes the synthetic fixture and `/milestone-plan` never produce
  in practice; they are exercised by the unit suite already. Flow 2a covers
  the anchor-grammar and post-registry/checkpoint-id refusals reachable
  through the ordinary amendment flow, deliberately without reproducing
  every registry-malformation unit test here.

<!--
This file is `workflow_state.FUNCTIONAL_CHECKLIST_PATH`. It is
repository-local state: workflow-manager generates it once at bootstrap and
never overwrites it on update.
-->
