# Active Milestone

## Milestone

`retention-pins-and-title` -- implementation review (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `72b8e56`, branch `milestone/retention-pins-and-title`): roadmap row 42 (#208, #211). A `test:` pull request title; no release follows. Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_PINS_AND_TITLE_PLAN.md`.

Three tests pin wording that could drift (the `UNDO_WARNING` literal, the first per-item call of the cannot-start case, the help's exit-1 qualifier), and `docs/retention.md` has a title and `For:` line that cover the report, the policy, the alert and the cleanup. The #208.4 decision (`retention-run-mapping.json` stays: a historical requirement record) is recorded at acceptance.

## Checkpoints

| id | status | evidence |
| --- | --- | --- |
| CP1 | complete | the three pins, the page header and roadmap row 42; M1 to M3 each fail only their own test in a scratch copy; `tools/check_docs.py` exits 0; `src tools .claude scripts .workflow-manager tests/parallel` byte-identical to the base; `--select` of `test_retention_run.py`, `test_retention_cleanup.py`, `test_retention_status.py`, `test_docs.py`: 230 tests, `verdict: exit 0` |

## Self-review -- complete

- The full diff `72b8e56..f357c7a` was reviewed against the plan. One finding, fixed in `f357c7a`: the plan's flow 6 greps `UNDO_WARNING ==`, and the pin was written as `assertEqual(rr.UNDO_WARNING, ...)`, so the grep found nothing; the pin now reads `assertTrue(rr.UNDO_WARNING == "...", rr.UNDO_WARNING)` (the value is the failure message). M1 re-run in a scratch copy: only that test fails, its message showing the reworded constant.
- The plan's offline flows 1 to 7 at `f357c7a`: only the two test files, `docs/retention.md` and `docs/ROADMAP.md` changed; `src tools .claude scripts .workflow-manager tests/parallel`, the unchecked pages and `retention-run-mapping.json` byte-identical to the base (exit 0); the new title and `For:` line, no `# Retention report`; no `retention.md#retention-report` link; `tools/check_docs.py` exits 0; the three pins found by their greps; row 42 Current, no row 43.
- Full gate `python3 tests/run_all.py` on `f357c7a`: 2406/2406 units, 16255 tests, selection_digest `0f5c56bd...`, tests_digest `8ef85434...`, tree_digest `0b1ff19c...`, `verdict: exit 0`.
