# Active Milestone

## Milestone

`retention-cleanup` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `bb5a016`, branch `milestone/retention-cleanup`): roadmap row 38 (#90, #195, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

Third slice of the owner's retention track, first half: a new explicit command `retention-cleanup TARGET` that, for a policy adopted with mode `cleanup` or `both`, checks the preconditions of an unattended cleanup and previews which finished items it would archive and remove. It writes nothing and runs no engine verb but the report. The four follow-ups of #195 ride along.

### CP1: the #195 follow-ups: alert wording, the no-release cause, test strength -- complete

- Files: `src/workflow_manager/retention_alert.py` (`SCRIPT_NO_RELEASE`, its cause and step; the incomplete-store wording of `_step`), `src/workflow_manager/cli.py` (`_installed_script_state` returns `SCRIPT_NO_RELEASE` for a record with no release), `tests/test_retention_alert.py` (new `TestFollowUps`; the doctor section test compares the whole section; the two `TestScriptState` cases assert the real script's refusal), `tests/test_retention_policy.py` (the `:60` seconds case), `docs/retention.md`.
- The no-release cause is defensive: `doctor` refuses a null record first (`could not resolve the target release`), and a test pins that refusal.
- Evidence: `--select` of `test_retention_alert.py` (58 tests), `test_retention_policy.py` (77) and `test_retention_status.py` (78) each `verdict: exit 0`.
- Failure-only mutations (fresh copy each, the named tests run alone from `tests/`): the unmutated copy passes; M1 to M6 each fail (M5 with the raise placed after the script check and before the fetch, the only place the real script's refusal is observable).

### CP2: the cleanup preview -- complete

- Files: `src/workflow_manager/retention_cleanup.py` (new: `preflight`, `committed`, `clean_tree`, `select`, `plan_digest`, `preview_lines`, `Refusal`), `src/workflow_manager/retention_policy.py` (`step_for`, `block` unchanged in output), `src/workflow_manager/cli.py` (the `retention-cleanup` command and help), `tests/test_retention_cleanup.py` (new), `tests/test_retention_policy.py` (`TestStepFor`), `tests/test_operator_ux.py` (`TARGET_COMMANDS`), `docs/retention.md`, `docs/exit-codes.md`.
- Deviation from the plan's file list, one: `tools/check_docs.py` (+ one case in `tests/test_docs.py`). The command is named after its work item (`retention-cleanup`), so rule 3 flagged the command name on the user pages as an internal id; `check_pages` now takes the Manager's command names and does not count them as ids. Every other id is still flagged.
- Deviation from the declaration, one: the pin for the `check_docs` change (a Manager command is not an internal id, even when a work item has its name) lives in `tests/test_retention_cleanup.py` (`TestCommandNameIsNotAnInternalId`), because `tests/test_docs.py` is outside the artifact declaration; `tests/test_docs.py` is unchanged from `main`. Mutation: with `- set(commands)` removed the test fails.
- `preflight` returns `Cleared(state, report)` (the policy state and the complete report) instead of the plan's `PolicyState`, since `select` needs both.
- Evidence: `--select` of `test_retention_cleanup.py` (49 tests), `test_retention_policy.py` (80), `test_operator_ux.py` (130) and `test_docs.py` (46) each `verdict: exit 0`; `python3 tools/check_docs.py` exit 0.
- Failure-only mutations (fresh copy each, the named module run alone from `tests/`): the unmutated copy passes; M7 to M34 each fail (M9 after a test gained an untracked, non-ignored file; M23 fails by a `KeyError`).
- Full gate `python3 tests/run_all.py`: `verdict: exit 0`, 2390/2390 units, 14332+ tests (16144), head 44f46f3, selection_digest 961b6741...9f2, tests_digest f6dded27...c314.
