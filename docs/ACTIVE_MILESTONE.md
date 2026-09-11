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

Empty. `/prepare-functional-review` writes the numbered checklist for the
active work item into this section; `/apply-functional-review` and
`/accept-milestone` read it back from here.

<!--
This file is `workflow_state.FUNCTIONAL_CHECKLIST_PATH`. It is
repository-local state: workflow-manager generates it once at bootstrap and
never overwrites it on update.
-->
