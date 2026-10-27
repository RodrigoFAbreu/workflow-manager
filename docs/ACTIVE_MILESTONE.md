# Active Milestone

## Milestone

`retention-status` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan
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
- Fixed (found by the first full gate, at `7a6d4bf`): `tests/retention_recipe.py`'s
  `init_origin` ran a bare `git init`, which `test_orphan_processes.py`'s `TestRoutingCheck`
  refuses; it now calls `init_git_repo` (`src/workflow_manager/fixture.py`), so the
  scratch repository gets the throwaway Git configuration every host test repository has.

### CP2: bookkeeping -- complete

Row 17 of `docs/ROADMAP.md` is Current (set when the plan started); it becomes Done at
acceptance. This file records the milestone. No version is edited.

### Verification

- Full gate, first run at `7a6d4bf`: `python3 tests/run_all.py` -> exit 1, one failure
  (`test_orphan_processes.py::TestRoutingCheck`, the recipe's bare `git init`; fixed in
  `ef52005`).
- Full gate, second run at `ef52005`: `python3 tests/run_all.py` -> exit 0 (full
  selection, 8 workers, 2302/2302 units, 15212 tests, orphan check on; `selection_digest
  20d92751...`, `tests_digest dfc9a75f...`, `tree_digest 2cb5d9dc...`).
- `python3 tools/check_docs.py` -> exit 0.
- Red first: with `3019c95`'s `src/` under `ef52005`'s tree (a scratch copy outside the
  repository), `python3 -m unittest test_retention_status` fails to import
  `workflow_manager.retention`, and `status --retention` and `doctor --retention` exit 2
  (`unrecognized arguments: --retention`). The SIGTERM-ignoring-child test also fails
  against `7a6d4bf`'s parent (it times out).
- Full gate at the implementation head `93e945f` (after the `7c1d8f0` fix of LIR2-001):
  `python3 tests/run_all.py` -> exit 0 (full selection, 8 workers, 2302/2302 units, 15217
  tests, orphan check on; `selection_digest 20d92751...`, `tests_digest 9e5d051b...`,
  `tree_digest f8b20128...`).
- Implementation review round 3 (`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` and
  `LOCAL_MODEL_IMPLEMENTATION_REVIEW`): APPROVE, no blocking or important findings. One
  Optional finding is open: EIR-003 (see Known limitations).

## Current checkpoint

None: the milestone is complete (CP1 and CP2 complete, `MILESTONE_COMPLETE`).

## Functional review

Sixteen flows (flow-1 to flow-12, flow-x1a, flow-x1b, flow-x2, flow-x3) passed at
`5b7238b`, run by an independent executor; flow 12 used the real forge with read-only
`gh`. Acceptance was by policy from that evidence and the Workflow's own query of
PR #117. The 20 Optional findings are dispositioned in
`docs/milestones/completed/retention-status-findings.md`.

### Known limitations

- EIR-003 (Optional, open): the renderer accepts negative integers, so a report with
  `finished_folder_bytes: -1` renders as `-1 B`. This does not change any exit code and
  produces no traceback. It is recorded as an Optional finding for disposition at
  acceptance; it is not a functional blocker.
- The Manager never runs `archive`, `remove` or any other script command, and it never
  prunes: prunable archives get no command, and the section says so.
- The 300-second timeout covers about ten times the forge time for 25 finished items. A
  repository with many more finished items gets the case-4 note.
- The report does not expose the archive index, `.partial` files, `zstd` or file-system
  boundaries; the script refuses those itself with its own next step, and the section
  claims nothing about them.

## Next action

Roadmap row 17 is Done. The pull request (#117) merges, then the Manager minor release
follows. The next incomplete milestone in `docs/ROADMAP.md` is ready for `PLANNING`
(`/milestone-plan`).
