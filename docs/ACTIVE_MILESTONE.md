# Active Milestone

## Milestone

**Complete.** `unattended-adopt-wording` (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `87c9460`, branch `milestone/unattended-adopt-wording`): the three points of issue #259, one mechanism: what the adopt output and the documentation say about adopting again, and the tests that pin it. Accepted by policy (`policy:bae758b4f4ce`).

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_ADOPT_WORDING_PLAN.md` (archived copy in `docs/milestones/completed/`).

Pull request title: `fix: tell the adopt preview to adopt again with the unattended sentence instead of running itself`.

### Checkpoints

- CP1 -- the adopt preview says to adopt again, and the mixed-confirmation refusal is pinned in full: **complete**. `retention_policy.unattended_lines(state, target, *, adopting=False)`; `cmd_adopt_retention_policy` passes `adopting=True`; `status`, `doctor` and the cleanup preview keep the shared text.
- CP2 -- the docs say the owner adopts again, and the ROADMAP row: **complete**. `docs/retention.md` says "the owner adopts the policy again"; row 53 of `docs/ROADMAP.md` is Done.

### Findings

The four Optional findings (`F-c939785685a6`, `F-f5884c700870`, `F-9bcaf4ea730c`, `F-a04152085a98`) and their dispositions are in `docs/milestones/completed/unattended-adopt-wording-findings.md`.

## Next action

No roadmap item is ready: the remaining rows (5, 6) wait on the Controller (C10, C11). The Manager patch release follows the pull request merge, as its `fix:` title says.
