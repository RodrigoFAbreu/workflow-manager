# Active Milestone

## Milestone

**In progress.** `unattended-retention-run` (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `73a5a72`, branch `milestone/unattended-retention-run`): step A2 of issue #254. `workflow-manager retention-cleanup TARGET --unattended` runs the archive-and-remove cleanup without the per-plan `--confirm` sentence, under the authority of the unattended adoption sentence (A1), with the Manager-side `keep_recent`, one audit line per action and per refusal outside the repository, and a `--json` document. Prune is not part of this item (A3).

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_RETENTION_RUN_PLAN.md`.

Pull request title: `feat: run the retention cleanup unattended under the adopted unattended policy, with an audit file`.

### Checkpoints

- CP1 -- the unattended authority check and the `keep_recent` selection: **complete**. `retention_cleanup.unattended_refusal` is the pure check of authority rows d to f (no `unattended` key, the adoption without the unattended sentence, `unattended.cleanup` false), asked of `PolicyState.unattended` only; `preflight` gains the keyword `unattended=False` and calls it at step 2b, right after the policy is known adopted with a cleanup mode and before anything starts a process. `select` now keeps back the newest `keep_recent - report.keep_recent` entries of `report["finished"]` (taken before the review-folder filter, never planned, not listed as skipped, still counted in the measured numbers) whenever the state authorises unattended cleanup, so the preview, the confirmed run and the unattended run share one plan and one digest rule. `Plan` gains `kept`, `keep_recent` and `engine_keep`; `preview_lines` prints the `keep:` line only when items are kept. Tests: `tests/test_retention_unattended_run.py`.
- CP2 -- the audit writer: pending.
- CP3 -- the unattended run and its JSON document: pending.
- CP4 -- the status text, the docs and the ROADMAP row: pending.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended_run.py --select test_retention_unattended.py --select test_retention_run.py --select test_retention_cleanup.py --select test_retention_policy.py`, 276 tests, `verdict: exit 0`. Mutations M3 (row d dropped), M6 (authority check removed from the preflight), M7 (`keep_recent` ignored) and M8 (`keep_recent` instead of `keep_recent - 3`) each fail the named tests of `test_retention_unattended_run.py`; the unmutated tree is green.

## Next action

CP2 -- the audit writer. Run `/milestone-implement unattended-retention-run` again (one checkpoint per invocation).
