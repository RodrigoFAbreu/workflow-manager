# Active Milestone

## Milestone

`retention-pins-and-wording-2` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `a243144`, branch `milestone/retention-pins-and-wording-2`): roadmap row 48

The retention report, alert and docs say exactly what the code does (#160, #222, #225, #216). An incomplete report whose forge queries all failed is shown as incomplete, one refusal helper replaces the duplicated block of `doctor`, and the retention wording and tests are pinned. A `fix:` change, Manager patch release 1.20.3.

### CP1: the note reads `complete`, one refusal helper -- complete

- `retention.py`: `_query_failed_note` returns `None` for an incomplete report, so `status`, `doctor`, `verify` and `retention-cleanup` show the incomplete report (cleanup refuses at step 8) instead of the forge note.
- `cli.py`: `_refuse_release_resolution(args, error)` replaces the two identical refusal blocks of `_doctor_json` and `cmd_doctor`; output unchanged.
- Tests: two fixtures get `"complete": True`; new incomplete, mixed-incomplete and complete-counterpart cases in `tests/test_retention_status.py`; a `TestPreflight` case in `tests/test_retention_cleanup.py` (refused at step 8, nothing written).
- Mutations M1 to M3 measured in scratch clones outside the repository: each fails the named tests. The golden of plan section 2.1 was not run as a separate script; the new tests cover the incomplete, mixed and complete reports. Narrow selection (`test_retention_status`, `_alert`, `_alert_json`, `_cleanup`, `test_doctor_cli`, `test_operator_ux`): verdict exit 0.
- `docs/ROADMAP.md`: row 48 added, Current.

### CP2: the tests and the docs -- complete

- `docs/retention.md`: one sentence in "If the report is incomplete" (an incomplete report is shown as incomplete even when every forge query failed; the forge cause is for a complete report), and the age-step bullet names the unreadable-archive exception (#160.1, #222.1).
- Links: the five `[Retention report](retention.md...)` links in `docs/README.md`, `update.md`, `verify.md` and `exit-codes.md` (two) read the page's title (#216.1).
- Tests: `TestDocs` pins the limits sentences (`2**63 - 1`, `INT_MAX`, the `invalid_id` clause and its code behaviour), the incomplete-report sentences and the link text; `TestAgeStep` pins the unreadable-archive clause; the release-below-2.21.0 scenario compares the whole line (#222.2); the release-option test's last case runs against `self.repo` with the corrupt record, and the `--manager-root` case asserts the deprecation line and the error line (#225.1, #225.3); the first report of the pushed-out test holds the archive (#225.4).
- KEEP: #222.3 (`1 items`) and the archived plan and declaration points of #216.
- Mutations M4 to M8 measured in a scratch copy outside the repository: each fails the named test. `python3 tools/check_docs.py` clean; `git diff` of `tools .claude scripts .workflow-manager tests/parallel` against the base is empty. Narrow selection (`test_retention_status`, `_alert`, `_alert_json`, `_cleanup`, `test_doctor_cli`, `test_operator_ux`, `test_docs`): verdict exit 0.

## Next action

`/milestone-implement retention-pins-and-wording-2` again: every checkpoint is complete, so it enters self-review, the full verification and the implementation review bundle.
