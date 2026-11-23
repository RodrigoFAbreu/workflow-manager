# Active Milestone

## Milestone

**In progress.** `retention-followup-pins` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `d2be4f8`, branch `milestone/retention-followup-pins`): tests and two docs sentences brought into line with the code (#257, #270, #264 points 1 and 2). Tests and docs only: no `src/` change, no release.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_FOLLOWUP_PINS_PLAN.md`.

Pull request title: `test: pin the retention follow-ups and say in the docs what the code prints`.

### Checkpoints

- CP1 -- the tests: a quoted verify command and the adopting helper's empty states: **complete**. The `not-verified` note is compared with `shlex.join`, a spaced target is pinned, and the adopting helper test covers a missing and an invalid policy file. Both mutations (`" ".join`, a guard that lets an empty policy through) fail the new tests.
- CP2 -- the docs say what the code prints, and their pins: **complete**. `docs/retention.md` says archives beyond the cap are left for a later run and what a prune stop prints; `docs/exit-codes.md` names both stop lines; `TestPage` and the zero-deleted stop test pin them. The four docs/code mutations fail the new tests; the full gate passed (16780 tests).
