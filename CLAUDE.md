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

`tools/migrate.py --check` proves each `distribution/workflow/<version>/` is
still exactly what a fresh extraction (or, for an authored release, its
recorded base-plus-overlay composition) produces; it does not by itself
prove no unrelated file exists directly under `distribution/` outside every
release directory.

## Where things are

- The migration record and its evidence: `docs/MIGRATION.md`
- The distribution/state boundary: `docs/ARCHITECTURE.md`
- Classification ruleset: `migration/classification.json`
- Frozen tests a clean target cannot pass, with reasons:
  `migration/portability_exceptions.json`

## Adding a Workflow release

1. Add the new tag/commit to `migration/classification.json` (or a second
   classification file if the tree shape changed).
2. Run `python3 tools/migrate.py`, then `python3 tests/run_all.py`.
3. The conformance suite must be green against the fixture, and the clean
   target's failure set must equal the documented exceptions — no more, no
   fewer.
