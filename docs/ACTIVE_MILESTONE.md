# Active Milestone

## Milestone

`age-alert-next-step` -- self-reviewed, awaiting the implementation review (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `61e5b51`, branch `milestone/age-alert-next-step`): roadmap row 44 (#218). A `fix:` pull request title (`fix: the age alert's next step names an old finished item`, Manager 1.19.1); the release-history row follows in a `docs:` pull request.

When the age threshold is reached, the retention alert's `next:` step names the finished item `retention-cleanup` would plan first for the age rule (the oldest old item, beyond the 3 most recent, that the script can act on), not the first archivable item in report order. The count and size steps and `retention.next_step` are unchanged.

### CP1: the age step, the shared id rule, the example and the tests -- complete (`91ef442`)

- `retention_alert._age_step` walks the old items oldest first, keeps the plannable ids, and returns the first one-entry `retention.next_step` that names a command (so tracked, unreadable-archive and interrupted-removal items are passed over); with none left it returns the accurate `nothing to archive` text, never a young item.
- `plannable_id` (with `_ID` and `RESERVED_IDS`) moved from `retention_cleanup` to `retention_alert`; `retention_cleanup._eligible` calls it.
- `docs/retention.md`: the alert example is a complete report (no `not known` line); the `next:` bullet says what the age step names.
- Tests: `TestAgeStep` (N1 to N5, N8), `TestAgeStepEndToEnd` (N7), the page test (N6), and the adjusted `test_the_age_line_and_its_variants`.
- Narrow check: `python3 tests/run_all.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py --select test_docs.py` -- 45/45 units, 262 tests, `verdict: exit 0`; `tools/check_docs.py` clean; the byte-identical `git diff --exit-code` against the base is empty.

### Self-review -- complete (no defect found)

- Every mutation of plan section 3 (M1, M2, M4, M5, M6, M8, M9) measured in a scratch clone outside the repository with `python3 tests/run_all.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py --select test_docs.py`; each failing set, read from the unit logs (the runner's summary drops subtests), equals the table: M1 fails N1, N2 (archived, tracked, kept-recent, unknown-age, `runtime`, `Bad_ID`), N4, N5, N7, N8 and `test_the_age_line_and_its_variants`; M2 fails N1, N2 (archived) and the adjusted test; M4 fails N4; M5 fails N5 and N8; M6 fails N6; M8 fails N2 (tracked), N3 and N8 ((b), (d)); M9 fails N2 (`runtime`, `Bad_ID`). The unmutated clone passes (45/45 units, 262 tests). No test or table row needed a change.
- Absent-key golden: `describe`, `block`, `render`, the `retention` section and `preview_lines` for three key-less policies over three reports (mixed, incomplete, empty) at releases 2.25.0 and 2.20.0 are byte-identical between `61e5b51` and the candidate (228 lines).
- Full gate at `91ef442`: `python3 tests/run_all.py`, 2413/2413 units, 16282 tests, `verdict: exit 0`.
