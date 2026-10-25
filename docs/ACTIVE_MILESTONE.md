# Active Milestone

## Milestone

`operator-polish` -- complete (accepted by policy; `governing_workflow_version: "2.2"`, `process`, plan
revision 1, base `5c06591`, branch `milestone/operator-polish`): roadmap row 14,
issue #84. A `fix:` pull request title (`src/` changes). Plan:
`docs/ai-workflow/WORKFLOW_MANAGER_OPERATOR_POLISH_PLAN.md`.

### CP1: the four fixes -- complete

- `source.py`: the null-record cause in `not_a_version`; `_log_once` carries the
  `using release` log in `ReleaseCache.resolve`, so one invocation prints a
  discovery note once.
- `cli.py`: `main` clears the once-record on entry; `cmd_status` re-raises a typed
  not-a-version refusal before printing the record.
- Docs: `docs/exit-codes.md` and `docs/update.md` list the refusal with its exit codes.
- Tests: `tests/test_discovery.py`, `tests/test_operator_ux.py`,
  `tests/test_operator_ux_docs.py`, `tests/test_docs.py`. Commit `193f5c8`.

### CP2: bookkeeping -- complete

- Row 14 of `docs/ROADMAP.md` is marked Current (`dc1052b`); it becomes Done at
  acceptance. This file records the milestone. No version is edited.
- The nightly `package` job's cache key (item 5) ships in its own `ci:` pull request.

### Self-review and the full gate

- The first full gate at `0ac15aa` failed one test:
  `test_operator_ux_readonly.TestPrintedCommandsParse.test_i3_verify_without_release_dir_after_a_scalar_install_asks_for_one`
  (subtest `version=None`) asserted the old `the installation record names` text
  for a null record, a second assertion the plan did not list. Its null case now
  expects CP1's cause (`76c63b3`); `123` and `""` keep the `names` wording.
- Red-first, in a clone at `0ac15aa` with `src/`, `docs/exit-codes.md` and
  `docs/update.md` restored to `5c06591`: 8 of the new or changed tests fail (the
  null record, typed `status`, the per-invocation reset, the `installed is the
  target` case for `doctor` and `update --dry-run`, both null-record subtests in
  `test_operator_ux`, the `docs/update.md` bullet) and both new exit-code rows of
  `test_operator_ux_docs` fail. Three discovery-note subtests (`pinned target`,
  `two discovered releases`, `pinned installed`) are green there: they guard the
  sole and distinct notes that must stay (EPR-001).
- Full gate `python3 tests/run_all.py` at `76c63b3`: exit 0, 2279/2279 units,
  14919 tests.

## Functional review

Five flows from the checklist and five from an independent executor passed at
`35a2cad`; the seven Optional findings are dispositioned (2 fixed, 5 dropped,
follow-ups on RodrigoFAbreu/workflow-manager#108). Record:
`docs/milestones/completed/operator-polish-findings.md`.

## Current checkpoint

None: the milestone is complete. Pull request #109 awaits its merge; the Manager
release follows the merge.

## Next action

`/milestone-plan` for the next incomplete roadmap row: row 15 (`_http_read`
releases its worker thread and socket at the deadline, #50), Later, low priority.
Issue #84 item 5 (the nightly cache key) ships in its own `ci:` pull request.
