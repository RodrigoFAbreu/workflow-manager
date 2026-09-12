# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

## Semi-autonomous workflow gates

Work follows the state machine in `docs/ai-workflow/MILESTONE_WORKFLOW.md`.
Claude works autonomously between gates but must stop and wait at every hard
gate that document names -- see its "Hard gates summary" for the current
count and list, which changes as the workflow evolves; do not hardcode a
count here.

Use the commands in `.claude/commands/` to drive each state. Do not skip a
gate because the diff looks small.

## Workflow documents

- Milestone state machine: `docs/ai-workflow/MILESTONE_WORKFLOW.md`
- Two-stage plan review: `docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`
- Bundle mechanics and feedback format: `docs/ai-workflow/REVIEW_PROTOCOL.md`
- Phase/command reference: `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`
- Current work-item state: `docs/ai-workflow/WORKFLOW_STATE.json` (ground
  truth -- never inferred from plan text)
- Active work item narrative: `docs/ACTIVE_MILESTONE.md`

## Git restrictions

- Commits are normally prohibited. Only commit when a workflow command
  explicitly authorizes it after verification gates pass.
- Never push, merge, rebase, force-push, or open a pull request.
- Don't touch unrelated working-tree changes.

<!--
Sections above this marker are managed by workflow-manager and are replaced
on update. Add repository-specific guidance below it; it is never touched.
-->

<!-- workflow-manager:end -->

# CLAUDE.md

Guidance for Claude Code in the **workflow-manager** repository.

## What this repository is

Distribution and bootstrap tooling for the reusable AI development Workflow.
It is *not* RepFlow, and no RepFlow product work belongs here.

## Hard rules

- **`~/Workspace/repflow-android` is read-only.** Read it through
  `git show <commit>:<path>` against the frozen tag `workflow-v2.3.1`
  (`1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6`). Never write to it, never
  create a worktree in it, never rely on its working tree — it carries an
  unrelated in-flight branch.
- **Each `distribution/workflow/<version>/` is generated, not edited.**
  `2.3.1` is byte-identical to the frozen upstream release; a later authored
  release is byte-identical to its own recorded base-plus-overlay
  composition. Change `migration/classification.json` or `tools/migrate.py`
  and re-run `python3 tools/migrate.py`.
- **Never modify frozen Workflow semantics.** If migration surfaces a genuine
  upstream defect, write it up under `docs/defects/` and stop there. Repairing
  it is a Workflow release's job, not this repository's.
- **Never migrate live work-item state.** Active `WORKFLOW_STATE` entries,
  `.ai-review/`, approvals, registries and mappings for someone else's work
  items are not defaults. Targets get clean templates.

## Before changing anything

```bash
python3 tests/run_all.py --fast     # ~10s, covers inventory/bytes/templates/bootstrap
python3 tests/run_all.py            # ~7min, adds the frozen conformance matrix
```

`tools/migrate.py --check` proves each upstream-derived
`distribution/workflow/<version>/` (today, `2.3.1`) still reproduces from a
fresh extraction; it does not by itself prove no unrelated file exists
directly under `distribution/` outside every release directory. An authored
release (today, `2.4.0`) is proved reproducible separately, by
`python3 tools/build_release.py --overlay migration/overlays/<version>
--check`, from the base release plus its overlay -- `migrate.py --check`
does not cover it.

## Where things are

- The migration record and its evidence: `docs/MIGRATION.md`
- The distribution/state boundary: `docs/ARCHITECTURE.md`
- Classification ruleset: `migration/classification.json`
- Frozen tests a clean target cannot pass, with reasons:
  `migration/portability_exceptions.json`

## Adding an upstream Workflow release

Use this when the new release is a fresh upstream tag (frozen content this
repository only extracts, never authors) -- `2.3.1` is the instance.

1. Add the new tag/commit to `migration/classification.json` (or a second
   classification file if the tree shape changed).
2. Run `python3 tools/migrate.py`, then `python3 tests/run_all.py`.
3. The conformance suite must be green against the fixture, and the clean
   target's failure set must equal the documented exceptions — no more, no
   fewer.

## Adding an authored Workflow release

Use this instead when the new release's content originates in this
repository -- a base release plus a hand-written overlay, never a new
upstream tag -- `2.4.0` (the plan-amendment mechanism) is the first instance.
See `docs/ARCHITECTURE.md`'s "Authored releases" and `docs/MIGRATION.md`'s
`2.4.0` record for the full mechanics and evidence.

1. Author `migration/overlays/<version>/payload/` (new files, plus full
   replacements of every base-release payload file the release changes) and
   `migration/overlays/<version>/classification.json` (the same ruleset shape
   as `migration/classification.json`, scoped to the overlay's own delta
   files).
2. Run `python3 tools/build_release.py --overlay migration/overlays/<version>`,
   then `python3 tools/build_release.py --overlay migration/overlays/<version>
   --check` — the committed `distribution/workflow/<version>/` must reproduce
   exactly from the base release plus the overlay alone, and every replaced
   file's recorded `overlay_delta` must reproduce from the base payload plus
   the recorded diff.
3. Add the new version to `tests/support.py`'s per-release `CI_SUITES` and,
   if it needs one, `migration/portability_exceptions.json`'s `by_version`,
   then run `python3 tests/run_all.py`. The conformance suite must be green
   against the fixture, the clean target's failure set must equal the
   documented exceptions, and any obligation the release's own checkpoints
   declare (a compatibility audit against the finished overlay diff, for
   instance) must actually be discharged, not merely inferred from suite
   totals.

**Downgrade posture.** Once a repository has run `workflow_manager update` to
an authored release that introduces vocabulary an older release's
`workflow_state.py` does not have (`2.4.0`'s `NEEDS_REVALIDATION` checkpoint
status and `SUPERSEDED` plan-approval status, for instance), downgrading it
back to that older release is **unsupported** — not merely unproven, actively
broken: any already-committed `WORKFLOW_STATE.json` state that ever recorded
one of those values reads back as permanently `"undecidable"` under the older
release's own narrower vocabulary (git history does not change on downgrade),
and checkpoint resume for that work item wedges with no in-band escape short
of an explicit, evidence-bound override
(`authorize_identity_reference_gap`). Never run `workflow_manager update
--release-version <older>` against a repository that has ever requested a
plan amendment, or has any checkpoint that ever held `NEEDS_REVALIDATION`, or
a plan approval that ever held `SUPERSEDED`.
