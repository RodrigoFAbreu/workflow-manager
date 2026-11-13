# Active Milestone

## Milestone

`retention-pins-and-title` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `72b8e56`, branch `milestone/retention-pins-and-title`): roadmap row 42 (#208, #211). A `test:` pull request title; no release follows. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_PINS_AND_TITLE_PLAN.md`.

Three tests pin wording that could drift (the `UNDO_WARNING` literal, the first per-item call of the cannot-start case, the help's exit-1 qualifier), and `docs/retention.md` has a title and `For:` line that cover the report, the policy, the alert and the cleanup. The #208.4 decision (`retention-run-mapping.json` stays: a historical requirement record) is recorded at acceptance.

## Checkpoints

| id | status | evidence |
| --- | --- | --- |
| CP1 | complete | the three pins, the page header and roadmap row 42; M1 to M3 each fail only their own test in a scratch copy; `tools/check_docs.py` exits 0; `src tools .claude scripts .workflow-manager tests/parallel` byte-identical to the base; `--select` of `test_retention_run.py`, `test_retention_cleanup.py`, `test_retention_status.py`, `test_docs.py`: 230 tests, `verdict: exit 0` |
