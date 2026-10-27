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
  SIGTERM, then SIGKILL once the leader has exited or after two seconds, and only then
  is the leader reaped), validates the
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
- Deviation from the plan's file list: the page-specific documentation checks (the
  cause-and-step table built from `retention.py`, the index and exit-code rows, the
  coverage-versus-store wording) are in `tests/test_retention_status.py`'s `TestDocs`,
  not in `tests/test_docs.py`; `tests/test_docs.py` is unchanged and its `check_tree`
  run applies the header, internal-id and command-parse rules to the registered page.

### Self-review

- Fixed: a script that exits on SIGTERM while a child of its own ignores it. The child
  was never sent SIGKILL (the leader's reap ended the stop sequence), so it outlived the
  call and held the output pipes: the call blocked until that child exited. The group now
  always gets SIGKILL after the grace, and the leader is reaped only after that (an
  unreaped leader keeps the group id from being reused). The new test
  (`test_a_child_that_ignores_sigterm_is_killed_and_does_not_hold_the_call`) runs the call
  in a scratch child subreaper, so the adopted child never reaches the runner's orphan
  check; at the CP2 head it times out (the call waited the child's full 60 seconds).
- `docs/retention.md`: the case-6 row also names exit 2 without the refusal lines.

### CP2: bookkeeping -- complete

Row 17 of `docs/ROADMAP.md` is Current (set when the plan started); it becomes Done at
acceptance. This file records the milestone. No version is edited.

## Current checkpoint

None: every checkpoint is complete; in self-review.

## Next action

The local implementation review of the bundle this command prepares.
