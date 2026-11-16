# Active Milestone

## Milestone

`retention-pins-and-wording-2` -- implementation review (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `a243144`, branch `milestone/retention-pins-and-wording-2`): roadmap row 48

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

### Self-review and the full gate

- The full milestone diff matches the plan's file list and sections; no blocking or important finding, no code change.
- The plan's section 2.1 golden, not run at CP1, ran in a scratch directory outside the repository: base `src` (`a243144`) against the candidate (`9aa1513`) for the retention section, the alert text, the alert JSON and the cleanup preflight over 41 reports, the three refusal shapes and two adopted policies. 28 of 313 outputs differ, all for the four incomplete reports with no finished or kept item and only `query_failed` items (with or without `open_phase`, with or without read errors), each as the plan's table says; every other output is identical.
- Plan section 6 flows 1 to 7 and 9 give the expected results; the title check reads `valid title: fix, release impact patch`.
- Full gate: `evidence: full selection, local, 8 worker(s), head 9aa1513587073556fd8c27432fd022cd35219810, 2438/2438 units, 16481 tests, selection_digest 9957d343edee4613b59b75a4d916afa09d860b8240978644a6c90b09637c9ef4, tests_digest f7d7202276056f763121f95f0268abf00b36174f3aaae9a496a27706be5e40b0, tree_digest 984aa66960ddfc45c12976d89490168dab155b9617ef7408d3b488a8cc8fd3a9`, `verdict: exit 0`; the only orphans are the declared `orphan_sources`.

## Next action

The local implementation review of the bundle `/milestone-implement` generated (implementation revision 1).
