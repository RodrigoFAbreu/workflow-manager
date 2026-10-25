# Active Milestone

## Milestone

`operator-polish` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan
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

## Current checkpoint

CP1 and CP2 are complete, and so are the self-review and the full gate. The
milestone is awaiting the implementation review.

## Next action

The implementation review of the bundle.
