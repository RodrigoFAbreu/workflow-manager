# Active Milestone

## Milestone

`retention-status` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan
revision 7, base `3019c95`, branch `milestone/retention-status`): roadmap row 17,
issue #90. A `feat:` pull request title (`src/` changes; a Manager minor follows the
merge). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_STATUS_PLAN.md`.

### CP1: the opt-in retention section -- complete

- `src/workflow_manager/retention.py`: runs the repository's installed
  `scripts/workflow_retention.py report --json` in a subprocess (`python3 -I -B`, resolved
  absolute path, own session, 300-second timeout; on timeout the process group gets
  SIGTERM, then SIGKILL after two seconds, and the leader is reaped), validates the
  report's fields, and renders the section or one `retention: not available` note.
- `cli.py`: `--retention` on `status` and `doctor`; no other behaviour changes, and the
  option never changes an exit code.
- Docs: `docs/retention.md` (registered in `tools/check_docs.py`), `docs/exit-codes.md`,
  `docs/verify.md`, `docs/update.md`, `docs/README.md`.
- Tests: `tests/test_retention_status.py`, `tests/retention_recipe.py` (the real script
  driven through its `run`/`resolve` seams), `tests/fixtures/retention_report.json` (a
  report captured from the real 2.22.0 script).
- Deviation from the plan's text: the timeout ends the group with SIGTERM before SIGKILL
  (two seconds of grace). A bare SIGKILL re-parents the script's children to the runner's
  subreaper, which the orphan check counts even though they are dead; with SIGTERM first
  a script reaps its own children and the check stays clean.

### CP2: bookkeeping -- pending

Row 17 of `docs/ROADMAP.md` is Current; it becomes Done at acceptance. No version is
edited.

## Current checkpoint

CP2.

## Next action

`/milestone-implement retention-status` for CP2, then the full gate and the implementation
review bundle.
