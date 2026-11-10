# Active Milestone

## Milestone

`retention-cleanup` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `bb5a016`, branch `milestone/retention-cleanup`): roadmap row 38 (#90, #195, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

Third slice of the owner's retention track, first half: a new explicit command `retention-cleanup TARGET` that, for a policy adopted with mode `cleanup` or `both`, checks the preconditions of an unattended cleanup and previews which finished items it would archive and remove. It writes nothing and runs no engine verb but the report. The four follow-ups of #195 ride along.

### CP1: the #195 follow-ups: alert wording, the no-release cause, test strength -- complete

- Files: `src/workflow_manager/retention_alert.py` (`SCRIPT_NO_RELEASE`, its cause and step; the incomplete-store wording of `_step`), `src/workflow_manager/cli.py` (`_installed_script_state` returns `SCRIPT_NO_RELEASE` for a record with no release), `tests/test_retention_alert.py` (new `TestFollowUps`; the doctor section test compares the whole section; the two `TestScriptState` cases assert the real script's refusal), `tests/test_retention_policy.py` (the `:60` seconds case), `docs/retention.md`.
- The no-release cause is defensive: `doctor` refuses a null record first (`could not resolve the target release`), and a test pins that refusal.
- Evidence: `--select` of `test_retention_alert.py` (58 tests), `test_retention_policy.py` (77) and `test_retention_status.py` (78) each `verdict: exit 0`.
- Failure-only mutations (fresh copy each, the named tests run alone from `tests/`): the unmutated copy passes; M1 to M6 each fail (M5 with the raise placed after the script check and before the fetch, the only place the real script's refusal is observable).
