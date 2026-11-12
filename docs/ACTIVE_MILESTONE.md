# Active Milestone

## Milestone

`retention-wording-pass` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `ec2f368`, branch `milestone/retention-wording-pass`): roadmap row 40 (#201, #195, #192, #198). A `fix:` pull request title; a Manager patch release follows.

The report text of the retention commands says exactly what is known, and a test pins each corrected text. The run's behaviour does not change.

### CP1: report accuracy after an archive-step stop -- complete

- Files: `src/workflow_manager/retention_run.py` (`UNDO_WARNING`, `_undo_unsettled`, `_Stop.unsettled`, `_closing` takes an `archive_state`: `NOT_ARCHIVED`, `UNSETTLED`, `FOREIGN`), `tests/test_retention_run.py` (five new tests), `docs/retention.md` (the paragraph after the run example).
- Behaviour: `already_archived` reads `this run did not create an archive for ID (one already exists)` (it wins over the undo warning); another engine refusal with `warning: the undo could not remove` on stderr reads `ID may or may not be archived (the engine's undo could not remove everything it created; the next preview shows which)`; every other case reads as before.
- Evidence: `--select test_retention_run.py` (45 tests) and `test_docs.py` `verdict: exit 0`; `tools/check_docs.py` clean. Mutations M1 to M5: each fails its named test (M4 is covered by `test_the_undo_warning_is_read_from_stderr_only` and M1's test).

### CP2: exit-code wording, the preview's real target, test hygiene -- not started
