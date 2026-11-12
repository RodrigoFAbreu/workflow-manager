# Active Milestone

## Milestone

`retention-wording-pass` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `ec2f368`, branch `milestone/retention-wording-pass`): roadmap row 40 (#201, #195, #192, #198). A `fix:` pull request title; a Manager patch release follows.

The report text of the retention commands says exactly what is known, and a test pins each corrected text. The run's behaviour does not change.

### CP1: report accuracy after an archive-step stop -- complete

- Files: `src/workflow_manager/retention_run.py` (`UNDO_WARNING`, `_undo_unsettled`, `_Stop.unsettled`, `_closing` takes an `archive_state`: `NOT_ARCHIVED`, `UNSETTLED`, `FOREIGN`), `tests/test_retention_run.py` (five new tests), `docs/retention.md` (the paragraph after the run example).
- Behaviour: `already_archived` reads `this run did not create an archive for ID (one already exists)` (it wins over the undo warning); another engine refusal with `warning: the undo could not remove` on stderr reads `ID may or may not be archived (the engine's undo could not remove everything it created; the next preview shows which)`; every other case reads as before.
- Evidence: `--select test_retention_run.py` (45 tests) and `test_docs.py` `verdict: exit 0`; `tools/check_docs.py` clean. Mutations M1 to M5: each fails its named test (M4 is covered by `test_the_undo_warning_is_read_from_stderr_only` and M1's test).

### CP2: exit-code wording, the preview's real target, test hygiene -- complete

- Files: `retention_cleanup.py` (`preview_lines(plan, target)` prints the quoted target in `next:`), `retention_run.py` (`Result` docstring), `cli.py` (help; passes `args.target`), `tests/test_retention_cleanup.py` (`EXAMPLE` template with `{target}`, `test_the_preview_quotes_the_target`, help pins), `tests/test_retention_run.py` (`test_exit_codes` gains the policy-before-item-1, interrupt-at-item-1, cannot-start and remove-only-verify cases; `test_a_step_must_return_its_own_shape`; `try/finally` in the refusal test; `TestDocsSayExitCodes`), `docs/retention.md`, `docs/exit-codes.md`.
- Behaviour: exit 1 = stopped after the first per-item call was attempted; exit 2 = refused or stopped before it. No behaviour change.
- Evidence: `--select` of `test_retention_run.py` (47), `test_retention_cleanup.py` (59), `test_operator_ux.py` (130), `test_docs.py` (44) all `verdict: exit 0`; `tools/check_docs.py` clean; full gate `python3 tests/run_all.py` 2406/2406 units, 16253 tests, `verdict: exit 0`. Mutations M7, M8, calls-after-launch (M6c-like) and M10 each fail their named test; M6, M6b, M9, M11 and the golden before/after diff were not run.
