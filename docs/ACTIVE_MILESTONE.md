# Active Milestone

## Milestone

**Complete.** `exit-codes-interrupt-row` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, implementation revision 1, base `a19f6a2`, branch `milestone/exit-codes-interrupt-row`): row 2 of the `retention-cleanup` table in `docs/exit-codes.md` says that an unattended prune interrupted before its first `prune --apply` exits 2, and one interrupted after a `prune --apply` was attempted exits 1. A test pins the clause. A follow-up of #276 (the Optional finding LPR1-003 of the previous item's plan review). Docs and one test pin only: no `src/` change and no release.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_EXIT_CODES_INTERRUPT_ROW_PLAN.md`.

Pull request title: `docs: say in the exit codes that an unattended prune interrupt before its first call exits 2`.

### Checkpoints

- CP1 -- the interrupt clause in row 2 and its pin: **complete** (`de862da`). Only `docs/exit-codes.md` (line 34, row 2) and `tests/test_retention_unattended.py` (`TestPage.test_the_exit_codes_row_names_an_interrupt_before_the_first_prune_apply`) changed.

### Verification state at `4be2b8e`

- Targeted selection `python3 tests/run_all.py --select test_retention_unattended.py`: exit 0, 63 tests.
- Full gate `python3 tests/run_all.py`: exit 0, 2491 of 2491 units, 16800 tests, `tree_digest` `677b68cd9772f0a2452e694b2ab510e244351456bcfc3f8d7b304ab1d786578f`.
- The pin fails against the base page (scratch copy, 4 failures) and passes on the candidate.

### Acceptance

Accepted by policy (`/satisfy-gate acceptance`): all seven functional flows passed at the approved content, the pull request's checks are green and the technical approval is current. The four Optional findings have recorded dispositions (two dropped with a reason, two follow-up: #286) (`docs/milestones/completed/exit-codes-interrupt-row-findings.md`). This closes the follow-up of #276.

## Next action

Plan the next item from `docs/ROADMAP.md` with `/milestone-plan`.
