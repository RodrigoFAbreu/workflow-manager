# Active Milestone

## Milestone

**In progress.** `unattended-retention-run` (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `73a5a72`, branch `milestone/unattended-retention-run`): step A2 of issue #254. `workflow-manager retention-cleanup TARGET --unattended` runs the archive-and-remove cleanup without the per-plan `--confirm` sentence, under the authority of the unattended adoption sentence (A1), with the Manager-side `keep_recent`, one audit line per action and per refusal outside the repository, and a `--json` document. Prune is not part of this item (A3).

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_RETENTION_RUN_PLAN.md`.

Pull request title: `feat: run the retention cleanup unattended under the adopted unattended policy, with an audit file`.

### Checkpoints

- CP1 -- the unattended authority check and the `keep_recent` selection: **complete**. `retention_cleanup.unattended_refusal` is the pure check of authority rows d to f (no `unattended` key, the adoption without the unattended sentence, `unattended.cleanup` false), asked of `PolicyState.unattended` only; `preflight` gains the keyword `unattended=False` and calls it at step 2b, right after the policy is known adopted with a cleanup mode and before anything starts a process. `select` now keeps back the newest `keep_recent - report.keep_recent` entries of `report["finished"]` (taken before the review-folder filter, never planned, not listed as skipped, still counted in the measured numbers) whenever the state authorises unattended cleanup, so the preview, the confirmed run and the unattended run share one plan and one digest rule. `Plan` gains `kept`, `keep_recent` and `engine_keep`; `preview_lines` prints the `keep:` line only when items are kept. Tests: `tests/test_retention_unattended_run.py`.
- CP2 -- the audit writer: **complete**. New module `retention_unattended.py`: `audit_path`/`state_base` (`$XDG_STATE_HOME` when absolute, else `~/.local/state`), `open_audit` (location refused inside the repository or the archive store by real path; missing parents and the `workflow-manager/` directory created `0700`; file `O_WRONLY|O_APPEND|O_NOFOLLOW`, created `0600` then `fchmod`; existing file or directory must be the user's and not group- or world-writable; `stat` seam; `AuditRefusal` with a cause and one step) and `Audit.line` (the eleven fields, one `os.write` per line, a failed or short write raises the distinct `AuditWriteError`; `clock`, `run_id` and `write` seams). Nothing calls it yet. Tests: `TestAuditWriter` in `tests/test_retention_unattended_run.py`.
- CP3 -- the unattended run and its JSON document: **complete**. `retention-cleanup TARGET --unattended [--json]`: `argument_refusal` (rows a and b, before anything is read), then the managed check and installation-record read, then `retention_unattended.run_command`: the audit is opened (refusal on failure), the preflight runs with `unattended=True` (every `Refusal` writes one `preflight` line, a failed write adds the audit cause to stderr), the plan is selected, an empty plan prints `nothing to do` (no line) or `nothing eligible` (one `plan` line), otherwise the `plan`/`started` line is written before the first action and `retention_run.run` runs with the new `unattended` (per-item re-read also requires the adoption to still authorise unattended cleanup) and `observer` parameters (one audit line per step; an observer failure after a succeeded step stops the run before the next call, exit 1, closing line says the step had succeeded). `--json` prints one `retention_cleanup_run` document on stdout, progress on stderr, nothing on stdout for a refusal. Tests: `tests/test_retention_unattended_run.py`.
- CP4 -- the status text, the docs and the ROADMAP row: pending.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended_run.py --select test_retention_unattended.py --select test_retention_run.py --select test_retention_cleanup.py --select test_retention_policy.py`, 276 tests, `verdict: exit 0`. Mutations M3 (row d dropped), M6 (authority check removed from the preflight), M7 (`keep_recent` ignored) and M8 (`keep_recent` instead of `keep_recent - 3`) each fail the named tests of `test_retention_unattended_run.py`; the unmutated tree is green.
- CP2: `python3 tests/run_all.py --select test_retention_unattended_run.py`, 49 tests, `verdict: exit 0`. Mutations (no `O_APPEND`, no `fchmod`, short write accepted) each fail the named tests; the unmutated tree is green.
- CP3: `python3 tests/run_all.py --select test_retention_unattended_run.py`, 80 tests, `verdict: exit 0`; `--select test_retention_run.py --select test_retention_cleanup.py --select test_retention_unattended.py --select test_retention_policy.py --select test_retention_status.py`, 338 tests, `verdict: exit 0`. Mutations M16 (no start line), M17 (observer failure ignored) and M18 (re-read without the authority condition) each fail the named tests; the unmutated tree is green.

## Next action

CP4 -- the status text, the docs and the ROADMAP row. Run `/milestone-implement unattended-retention-run` again (one checkpoint per invocation).
