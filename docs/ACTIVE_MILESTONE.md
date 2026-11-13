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

## Functional review checklist

Review the committed checklist: the commit that carries the `Workflow-Functional-Checklist` trailer for this round (`/prepare-functional-review` reports its SHA and blob). Test a checkout of the candidate branch at that commit, with `BASE` = `72b8e56e4824b0fc73954fe943887afd5c45c8e0`. Exit codes are read with `; echo $?`, never through a pipe.

### Setup

- Tools: `git`, `grep`, `sed`, `python3`. No network, no `gh`, no `claude`, `codex` or `ssh` is needed for flows 1 to 7.
- No build or install step. Nothing is seeded. Flows 1 to 7 read the working tree and git history only.
- Flow 8 runs the test runner in a scratch copy under `$TMPDIR` (never inside the clone). Run `python3 tests/run_all.py --list` first; if the release cache lacks a version, the first run needs the network or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror. After priming, the run is offline.

### Test data

None. The Workflow state file, `.ai-review/` and any live work-item state are not to be edited or migrated.

### Flows

Classification: flows 1 to 7 are sandbox-runnable (offline, read-only); flow 8 needs the test runner and a primed release cache.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only `docs/ROADMAP.md`, `docs/retention.md`, `tests/test_retention_cleanup.py` and `tests/test_retention_run.py` change |
| 2 | `git diff --exit-code BASE -- src tools .claude scripts .workflow-manager tests/parallel README.md docs/README.md docs/glossary.md docs/exit-codes.md docs/verify.md docs/update.md docs/ai-workflow/requirements/retention-run-mapping.json; echo $?` | no output, `0` |
| 3 | `sed -n 1,3p docs/retention.md`, then `grep -c -e '^# Retention report' docs/retention.md; echo $?` | line 1 is `# Retention: the report, the policy, the alert and the cleanup`; the `For:` line names the report, the policy, the alert and the cleanup and ends `Last checked with: Workflow Manager 1.18.1, Workflow 2.29.3.`; count `0` |
| 4 | `grep -rn --exclude-dir=ai-workflow --exclude-dir=milestones --exclude=ACTIVE_MILESTONE.md 'retention.md#retention-report' docs README.md src tests tools; echo $?` | no output, `1`. The `--exclude=ACTIVE_MILESTONE.md` is needed: the plan's flow 4 without it matches the self-review sentence in this file and exits `0` |
| 5 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 6 | `grep -n 'UNDO_WARNING ==' tests/test_retention_run.py`; `grep -n 'attempted, \[("archive", "item-00")\]' tests/test_retention_run.py`; `grep -n 'even if its script could not be started' tests/test_retention_cleanup.py` | three hits: `UNDO_WARNING ==` at `tests/test_retention_run.py:378` (the literal pin); `attempted, [("archive", "item-00")]` at line 651 (the recorded attempt); the qualifier at `tests/test_retention_cleanup.py:859` |
| 7 | `grep -n -E '^. 42 ' docs/ROADMAP.md`; `grep -c -E '^. 43 ' docs/ROADMAP.md; echo $?` | row 42 present, last cell `Current`; count `0` |
| 8 | In a scratch copy of the candidate under `$TMPDIR`, apply each mutation with `sed` and run `python3 tests/run_all.py --select <file>`: M1 reword `UNDO_WARNING` in `src/workflow_manager/retention_run.py` (`could not remove` to `could not delete`) and run `test_retention_run.py`; M2 in the copy's `_call` in `retention_run.py`, make the `except OSError` branch first call `retention.launch_script` once with the remove argv inside `try`/`except OSError: pass`, then raise the same `_Stop`, and run `test_retention_run.py`; M3 delete `even if its script could not be started` from the copy's `cli.py` help and run `test_retention_cleanup.py` | each mutated run FAILS only its own test: M1 the new literal pin (`test_the_undo_warning_prefix_is_the_engines_own_text`); M2 `test_exit_codes` at the `attempted` assertion, named by its message (the first per-item call was attempted although the script never started), not an earlier assertion; M3 `test_the_help_names_the_preview_the_run_the_floor_and_prune`. The unmutated copy passes each. Delete the scratch copies afterwards |

### Known limitations and out of scope

- No test pins the page title (M4). Flow 3 is the only check, by decision.
- `docs/ai-workflow/requirements/retention-run-mapping.json` keeps the old exit-1 wording (#208.4, KEEP: a historical requirement record). Recorded at acceptance, not changed.
- `docs/README.md`, `docs/update.md`, `docs/verify.md` and `docs/exit-codes.md` still call the page `Retention report` in their link text. They stay byte-identical on purpose (flow 2). Optional finding `F-4c10eea99742`, dispositioned at acceptance.
- No source change, no release (a `test:` pull request title), no CI change.
- Plan-review optional findings are recorded in `WORKFLOW_STATE.json` and dispositioned at acceptance.
