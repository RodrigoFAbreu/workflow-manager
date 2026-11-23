# Active Milestone

## Milestone

**In progress.** `unattended-prune-interrupt` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `a9dda89`, branch `milestone/unattended-prune-interrupt`): an interrupt that lands while the unattended prune writes its `started` or `ok` audit line stops the phase with `interrupted` instead of escaping (#264 point 3). A Manager patch release (`fix:`).

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_PRUNE_INTERRUPT_PLAN.md`.

Pull request title: `fix: stop the unattended prune cleanly on an interrupt during its audit writes`.

### Checkpoints

- CP1 -- the two interrupt handlers and their tests: **complete**. `run_phase` handles `KeyboardInterrupt` on the `started` write and on the `ok` write; two tests in `TestAuditFailures` pin the stop, the audit line and the text. The three code mutations (either clause deleted, "the apply had succeeded" dropped) fail them.
- CP2 -- the Audit lines clause and its pin: **complete**. `docs/retention.md`'s Audit lines paragraph says an `interrupted` line is also written when the run is interrupted while the `started` line or an archive's `ok` line is written (the archive is already deleted for the latter); a `TestPage` pin holds both halves and fails against the base wording.

## Next action

Run `/milestone-implement unattended-prune-interrupt` again: every checkpoint is complete, so it enters `SELF_REVIEWING_IMPLEMENTATION`.
