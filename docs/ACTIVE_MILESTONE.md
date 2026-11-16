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

## Next action

`/milestone-implement retention-pins-and-wording-2` for CP2 (the tests and the docs).
