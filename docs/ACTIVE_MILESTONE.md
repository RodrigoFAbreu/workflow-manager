# Active Milestone

## Milestone

`retention-cleanup` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `bb5a016`, branch `milestone/retention-cleanup`): roadmap row 38 (#90, #195, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

Third slice of the owner's retention track, first half: a new explicit command `retention-cleanup TARGET` that, for a policy adopted with mode `cleanup` or `both`, checks the preconditions of an unattended cleanup and previews which finished items it would archive and remove. It writes nothing and runs no engine verb but the report. The four follow-ups of #195 ride along.

### CP1: the #195 follow-ups: alert wording, the no-release cause, test strength -- complete

- Files: `src/workflow_manager/retention_alert.py` (`SCRIPT_NO_RELEASE`, its cause and step; the incomplete-store wording of `_step`), `src/workflow_manager/cli.py` (`_installed_script_state` returns `SCRIPT_NO_RELEASE` for a record with no release), `tests/test_retention_alert.py` (new `TestFollowUps`; the doctor section test compares the whole section; the two `TestScriptState` cases assert the real script's refusal), `tests/test_retention_policy.py` (the `:60` seconds case), `docs/retention.md`.
- The no-release cause is defensive: `doctor` refuses a null record first (`could not resolve the target release`), and a test pins that refusal.
- Evidence: `--select` of `test_retention_alert.py` (58 tests), `test_retention_policy.py` (77) and `test_retention_status.py` (78) each `verdict: exit 0`.
- Failure-only mutations (fresh copy each, the named tests run alone from `tests/`): the unmutated copy passes; M1 to M6 each fail (M5 with the raise placed after the script check and before the fetch, the only place the real script's refusal is observable).

### CP2: the cleanup preview -- complete (revalidated against plan revision 3)

- Files: `src/workflow_manager/retention_cleanup.py` (new: `preflight`, `committed`, `clean_tree`, `select`, `plan_digest`, `preview_lines`, `Refusal`), `src/workflow_manager/retention_policy.py` (`step_for`, `block` unchanged in output), `src/workflow_manager/cli.py` (the `retention-cleanup` command and help), `tests/test_retention_cleanup.py` (new), `tests/test_retention_policy.py` (`TestStepFor`), `tests/test_operator_ux.py` (`TARGET_COMMANDS`), `docs/retention.md`, `docs/exit-codes.md`.
- Revision 3 (amendment 0) records the `tools/check_docs.py` change below (plan 2.9, M35) and classifies the path, so it is no longer a deviation; the code did not change for the revalidation. Revalidation evidence at head 3f34535: `--select` of `test_retention_cleanup.py` (50 tests) and `test_docs.py` (44) each `verdict: exit 0`; `python3 tools/check_docs.py` exit 0.
- Formerly a deviation from the plan's file list, one: `tools/check_docs.py`. The command is named after its work item (`retention-cleanup`), so rule 3 flagged the command name on the user pages as an internal id; `check_pages` now takes the Manager's command names and does not count them as ids. Every other id is still flagged.
- Deviation from the declaration, one: the pin for the `check_docs` change (a Manager command is not an internal id, even when a work item has its name) lives in `tests/test_retention_cleanup.py` (`TestCommandNameIsNotAnInternalId`), because `tests/test_docs.py` is outside the artifact declaration; `tests/test_docs.py` is unchanged from `main`. Mutation: with `- set(commands)` removed the test fails.
- `preflight` returns `Cleared(state, report)` (the policy state and the complete report) instead of the plan's `PolicyState`, since `select` needs both.
- Evidence: `--select` of `test_retention_cleanup.py` (49 tests), `test_retention_policy.py` (80), `test_operator_ux.py` (130) and `test_docs.py` (46) each `verdict: exit 0`; `python3 tools/check_docs.py` exit 0.
- Failure-only mutations (fresh copy each, the named module run alone from `tests/`): the unmutated copy passes; M7 to M34 each fail (M9 after a test gained an untracked, non-ignored file; M23 fails by a `KeyError`).
- Full gate `python3 tests/run_all.py` (before the amendment): `verdict: exit 0`, 2390/2390 units, head 44f46f3, superseded by the run below.

### Self-review and full verification -- complete

- Phase `SELF_REVIEWING_IMPLEMENTATION` (written by CP2's completion; the step-2 call was a no-op). The full milestone diff (`bb5a016..77c4f75`) was reviewed for correctness, layer boundaries, missing tests and maintainability: no blocking or important finding, no code change.
- Full gate `python3 tests/run_all.py`: `verdict: exit 0`, 2391/2391 units, 16144 tests, head 77c4f75, selection_digest 1c4c251e...a7, tests_digest 09b995c7...b4. The processes the log lists are the declared `orphan_sources`.

## Functional review checklist

Implementation revision 7 (local APPROVE, round 7). Current automated verification: `python3 tests/run_all.py` at head `9211a4b`, `verdict: exit 0`, 2391/2391 units, 16150 tests, selection_digest 1c4c251e...a7, tests_digest 3d8ff2f1...a7. It was rerun after the implementation-review fixes (the last full gate before them was 77c4f75). The only uncommitted change is a row-38 edit in `docs/ROADMAP.md`, which this review does not cover.

### Setup

Test in a scratch clone, so nothing is written into the product clone (`<product clone>` is this repository, branch `milestone/retention-cleanup`):

```
S=$(mktemp -d "$HOME/rc-fr.XXXXXX")
git clone --no-hardlinks <product clone> "$S/cand"
git -C "$S/cand" remote remove origin
export PYTHONPATH="$S/cand/src"
```

- Flows 1 to 7 are offline. They need Python 3 and git, and nothing else: no network, no `gh`, no GitHub, no `claude`, `codex` or `ssh`.
- Flows 8 to 10 need the full environment: network access (the first run primes the release cache), `gh` signed in, and a scratch managed repository from the newest tested release. Run them last, and only on a machine with that environment.
- Clean up with `rm -rf "$S"` when done.

### Test data

- Flow 3 uses hand-made reports, described in the flow. No real repository is needed.
- Flow 10 uses a scratch managed repository with a `cleanup` policy adopted and committed, the release's own script untouched, and no origin.

### Flows

| Flow | Do | Expect | Runs in the sandbox |
| --- | --- | --- | --- |
| 1 | `cd "$S/cand" && git diff --stat bb5a016b01c62e551eeb0adf255c36db28d86ca9 HEAD -- src tools tests docs .github scripts .claude` | `retention_alert.py`, `retention_cleanup.py`, `retention_policy.py`, `cli.py`, `tests/test_retention_alert.py`, `tests/test_retention_cleanup.py`, `tests/test_retention_policy.py`, `tests/test_operator_ux.py`, `tools/check_docs.py`, `docs/retention.md`, `docs/exit-codes.md`, and the expected bookkeeping under `docs/` only | yes |
| 2 | `python3 -m workflow_manager retention-cleanup --help` | names the preview, the preconditions, the minimum release 2.25.5, that nothing is written, and that prune is never part of it | yes |
| 3 | `python3 -c` calling `retention_cleanup.select` on hand-made reports: 12 finished items with folders (limit 10), 7 candidates over a byte limit, a tracked-files entry, and only `archives` reached | oldest first; at most 5; the tracked item is skipped with its reason; an empty plan for the last report | yes |
| 4 | `grep -n 'prune' "$S/cand/src/workflow_manager/retention_cleanup.py"` | only text that says prune is never run; no argv carries it | yes |
| 5 | `grep -n 'none can be pruned\|no prunable archive was observed' "$S/cand/src/workflow_manager/retention_alert.py" "$S/cand/docs/retention.md"` | both wordings are present; the second is for an incomplete report | yes |
| 6 | `python3 "$S/cand/tools/check_docs.py"` | exit 0 | yes |
| 7 | `grep -n 'set(commands)' "$S/cand/tools/check_docs.py"`; `cd "$S/cand/tests" && python3 -B -m unittest test_retention_cleanup.TestCommandNameIsNotAnInternalId`; then in a second scratch copy, `sed -i 's/ - set(commands)//' tools/check_docs.py` and run the same test there | the grep shows the exemption in `check_pages`; the test is OK on the clone and FAILED on the mutated copy | yes |
| 8 | (full environment) in scratch copies of `$S/cand`, apply each mutation M1 to M35 with `sed` and run its named test; the unmutated copy first | the unmutated copy is OK; each mutation is FAILED | no |
| 9 | (full environment) `python3 tests/run_all.py --select test_retention_cleanup.py`, then the same for `test_retention_alert.py`, `test_retention_policy.py`, `test_retention_status.py`, `test_operator_ux.py` and `test_docs.py` | `verdict: exit 0` each, with no `OrphanProcessError` | no |
| 10 | (full environment) in the scratch managed repository, run `workflow-manager retention-cleanup TARGET`; then change a tracked file and run it again | the first: the script's own refusal (no origin), exit 2, nothing written; the second: the uncommitted-change refusal before the script starts, exit 2 | no |

### Known limitations and out of scope

- The command writes nothing and runs no archive or remove. The confirmed run, which is the next roadmap row, is not in this item.
- Prune is user-only and is never run by the Manager.
- The preview runs the Workflow's report, so it needs `gh` signed in, and a forge query per finished item (bounded at 300 s).
- The clean-tree rule refuses a repository with uncommitted changes, including one the owner is working in. Commit, or run the command from a clean checkout.
- An interrupted removal refuses the plan rather than resuming it (plan open decision O2).
- The minimum Workflow release is 2.25.5 (plan open decision O1). The installed 2.29.1 satisfies it.
- The Manager release (a minor `feat` release) follows the merge and is not part of this review.
