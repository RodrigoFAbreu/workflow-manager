# Active Milestone

## Milestone

`retention-alert` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `7810ff6`, branch `milestone/retention-alert`): roadmap row 37 (#90, #192, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

Second slice of the owner's retention track: for a retention policy adopted with mode `notify` or `both`, `verify` and `doctor` evaluate the four thresholds against the retention report and print a `retention alert:` block when one is reached (one `not evaluated` line when the report cannot be had). The alert never starts a script that is not the release's, never changes an exit code, and sends and cleans nothing. The four follow-ups of #192 ride along in CP2.

### CP1: the alert: evaluation, verify and doctor wiring, tests, docs -- complete

- Files: `src/workflow_manager/retention_alert.py` (new: `evaluate`, `script_state`, `alert_lines`), `src/workflow_manager/retention.py` (`PRUNE_FROM`, the prunable line, `section(..., outcome)`), `src/workflow_manager/cli.py` (wiring, help text, `_installed_script_state`), `tests/test_retention_alert.py` (53 tests, nine classes), `tests/test_retention_status.py` (`TestPruneLine`), `docs/retention.md`, `docs/verify.md`, `docs/exit-codes.md`.
- Deviations from the plan text: none of substance. `not-executable` is not a case of the real script (the release lists it as non-executable), so `TestScriptState` covers modified, missing, unlisted and the no-script release; the doctor `--release-version` case picks the newest tested release whose script digest differs from the newest's (2.25.5 today) and skips when none does. The in-process `cli.main` helper asserts the patched seam's `call_count` in `TestGate` and `TestOutput`.
- Evidence: `python3 tools/check_docs.py` exit 0; `--select` of `test_retention_alert.py` (53 tests), `test_retention_status.py` (78), `test_retention_policy.py` (71), `test_operator_ux.py` and `test_docs.py` each `verdict: exit 0`.
- Failure-only mutations (plan section 3), each on a fresh copy, the named tests run alone from `tests/`: the unmutated copy passes and every mutation fails: M1 to M18 (M15 in two parts: order and the unindented `next:`), M24 to M27 (M27 in two parts), M29 to M36 (M34 and M36 in two parts each). M37 is not mutated mechanically: the stub-based cases assert the seam's `call_count` instead. M19 to M23 and M28 belong to CP2.

### CP2: the #192 follow-ups, bookkeeping and the release -- not started
