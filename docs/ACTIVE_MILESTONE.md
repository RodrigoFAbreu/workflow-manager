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

## Current checkpoint

CP1 and CP2 are complete; the milestone is awaiting the full verification run and
the implementation review.

## Next action

Full gate `python3 tests/run_all.py`, then the implementation review bundle.
