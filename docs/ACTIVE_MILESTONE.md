# Active Milestone

## Milestone

`age-alert-next-step` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `61e5b51`, branch `milestone/age-alert-next-step`): roadmap row 44 (#218). A `fix:` pull request title (`fix: the age alert's next step names an old finished item`, Manager 1.19.1); the release-history row follows in a `docs:` pull request.

When the age threshold is reached, the retention alert's `next:` step names the finished item `retention-cleanup` would plan first for the age rule (the oldest old item, beyond the 3 most recent, that the script can act on), not the first archivable item in report order. The count and size steps and `retention.next_step` are unchanged.

### CP1: the age step, the shared id rule, the example and the tests -- complete

- `retention_alert._age_step` walks the old items oldest first, keeps the plannable ids, and returns the first one-entry `retention.next_step` that names a command (so tracked, unreadable-archive and interrupted-removal items are passed over); with none left it returns the accurate `nothing to archive` text, never a young item.
- `plannable_id` (with `_ID` and `RESERVED_IDS`) moved from `retention_cleanup` to `retention_alert`; `retention_cleanup._eligible` calls it.
- `docs/retention.md`: the alert example is a complete report (no `not known` line); the `next:` bullet says what the age step names.
- Tests: `TestAgeStep` (N1 to N5, N8), `TestAgeStepEndToEnd` (N7), the page test (N6), and the adjusted `test_the_age_line_and_its_variants`.
- Narrow check: `python3 tests/run_all.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py --select test_docs.py` -- 45/45 units, 262 tests, `verdict: exit 0`; `tools/check_docs.py` clean; the byte-identical `git diff --exit-code` against the base is empty.
