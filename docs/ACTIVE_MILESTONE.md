# Active Milestone

## Milestone

`retention-wording-pass` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `ec2f368`, branch `milestone/retention-wording-pass`): roadmap row 40 (#201, #195, #192, #198). A `fix:` pull request title; a Manager patch release follows.

The report text of the retention commands says exactly what is known, and a test pins each corrected text. The run's behaviour does not change.

### CP1: report accuracy after an archive-step stop -- complete

- Files: `src/workflow_manager/retention_run.py` (`UNDO_WARNING`, `_undo_unsettled`, `_Stop.unsettled`, `_closing` takes an `archive_state`: `NOT_ARCHIVED`, `UNSETTLED`, `FOREIGN`), `tests/test_retention_run.py` (five new tests), `docs/retention.md` (the paragraph after the run example).
- Behaviour: `already_archived` reads `this run did not create an archive for ID (one already exists)` (it wins over the undo warning); another engine refusal with `warning: the undo could not remove` on stderr reads `ID may or may not be archived (the engine's undo could not remove everything it created; the next preview shows which)`; every other case reads as before.
- Evidence: `--select test_retention_run.py` (45 tests) and `test_docs.py` `verdict: exit 0`; `tools/check_docs.py` clean. Mutations M1 to M5: each fails its named test (M4 is covered by `test_the_undo_warning_is_read_from_stderr_only` and M1's test).

### CP2: exit-code wording, the preview's real target, test hygiene -- complete

- Files: `retention_cleanup.py` (`preview_lines(plan, target)` prints the quoted target in `next:`), `retention_run.py` (`Result` docstring), `cli.py` (help; passes `args.target`), `tests/test_retention_cleanup.py` (`EXAMPLE` template with `{target}`, `test_the_preview_quotes_the_target`, help pins), `tests/test_retention_run.py` (`test_exit_codes` gains the policy-before-item-1, interrupt-at-item-1, cannot-start and remove-only-verify cases; `test_a_step_must_return_its_own_shape`; `try/finally` in the refusal test; `TestDocsSayExitCodes`), `docs/retention.md`, `docs/exit-codes.md`.
- Behaviour: exit 1 = stopped after the first per-item call was attempted; exit 2 = refused or stopped before it. No behaviour change.
- Evidence: `--select` of `test_retention_run.py` (47), `test_retention_cleanup.py` (59), `test_operator_ux.py` (130), `test_docs.py` (44) all `verdict: exit 0`; `tools/check_docs.py` clean; full gate `python3 tests/run_all.py` 2406/2406 units, 16253 tests, `verdict: exit 0`. Mutations M7, M8, calls-after-launch (M6c-like) and M10 each fail their named test; M6, M6b, M9, M11 and the golden before/after diff were not run.

### Self-review -- complete

- The full diff `ec2f368..6e75b8d` was reviewed. One finding, fixed in `a1d7639`: a CP2 help-string line in `cli.py` ran to 126 characters; it is rewrapped and the joined help text is byte-identical.
- The plan's evidence CP2 left unrun: mutations M6 (`changed` subtest fails), M6b (`changed` and `interrupt` fail), M9 (the verify arm's `mode` case fails) and M11 (only `dirty tree` fails, `failures=1`, later cases still run), each against an unmutated scratch clone that passes. Golden before (`ec2f368`) / after (`a1d7639`), ten shared scenarios: `diff -r` shows only the preview's `next:` line (`TARGET` -> the quoted target) plus the two new scenarios (`already_archived`, the undo warning), which have no before.
- Full gate `python3 tests/run_all.py` on `a1d7639`: 2406/2406 units, 16253 tests, selection_digest `0f5c56bd...`, tests_digest `daa15450...`, `verdict: exit 0`.

### Functional review checklist

Implementation revision 3, code head `28d8c18`. Automated verification re-run on `28d8c18` (the tree changed after `a1d7639`, through `73382e4` and `430f31f`): `python3 tests/run_all.py` `verdict: exit 0`, 2406/2406 units, 16254 tests, selection_digest `0f5c56bd...`, tests_digest `2e4c4796...`, tree_digest `19dd58c6...`.

**Setup.** Work in a scratch clone, never the product clone. Clone it at this branch (the checklist commit's HEAD) and run the Manager from the clone's source:

```
S="$HOME/.cache/wm-functional/retention-wording-pass"
git clone -q --branch milestone/retention-wording-pass <product-clone-path> "$S/clone"
cd "$S/clone"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src"
```

Flows 4 to 6 use a managed scratch repository, a copy of a repository bootstrapped at Workflow 2.25.5 or later, with an adopted `cleanup` policy committed (`workflow-manager adopt-retention-policy`), with a path that contains a space (for example `"$HOME/scratch repo"`) so the quoting is exercised, and with at least one finished work item that has an untracked review folder. Each run needs `gh` signed in, because the retention report makes one forge query per finished work item.

Flows 1 to 3 run offline, with no `gh`, `claude`, `codex` or `ssh`, and write nothing: they are the sandbox-runnable flows.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `python3 -m workflow_manager retention-cleanup --help` | Exit 0. The exit paragraph reads: 1 is "the run stopped after its first per-item call (archive, the verification or remove) was attempted, even if its script could not be started", and 2 is "refused, or stopped before that first call (the policy changed or the run was interrupted while item 1's policy was read)". The text says nothing about "an engine call started". |
| 2 | `grep -rn --exclude=ACTIVE_MILESTONE.md 'after an engine call started' docs/*.md src` | No output (exit 1). The old criterion is gone from the user-facing docs and the source. (This checklist is excluded because it quotes the phrase; `tests/test_retention_run.py` quotes it only inside two `assertNotIn` guards that keep it out; `docs/ai-workflow/requirements/retention-run-mapping.json` still carries it; see limitations.) |
| 3 | Read `docs/exit-codes.md`, the `retention-cleanup` rows 1 and 2, and `docs/retention.md`: the "Exit status" bullet of the confirmed run and its closing sentence | Each says the same criterion as flow 1: the first per-item call was attempted (exit 1), or the run stopped before it (exit 2). The `docs/retention.md` preview example shows `next: workflow-manager retention-cleanup /srv/repo --confirm ...`: the real target as typed, not `TARGET`. |
| 4 | Full environment. `python3 -m workflow_manager retention-cleanup "$HOME/scratch repo"` | Exit 0. The `next:` line names the target quoted for a shell, `'…/scratch repo'`, with the sentence `Run the retention cleanup DIGEST12.`; the literal `TARGET` does not appear. Nothing is written: `git status --short` shows the same untracked review folder, and `.ai-review/` is unchanged. |
| 5 | Full environment. `python3 -m workflow_manager retention-cleanup "$HOME/scratch repo" --confirm "Run the retention cleanup 000000000000."` | Exit 2. stderr: `error: retention cleanup: --confirm does not hold the sentence for the current plan ...` and `next: run workflow-manager retention-cleanup '…/scratch repo' to see the current plan and its sentence` (the target quoted). Nothing is archived or removed: the review folder is still there. |
| 6 | Full environment. Run flow 4's `next:` sentence exactly: `python3 -m workflow_manager retention-cleanup "$HOME/scratch repo" --confirm "Run the retention cleanup DIGEST12."` | Exit 0. The closing line reads `retention cleanup: done, N of N items archived and removed; Git is unchanged (the review folders were untracked); prune was not run`. `git rev-parse HEAD` is unchanged. The run's behaviour is the same as before this milestone. |

**Limitations and out of scope.**

- The two stop-report texts that CP1 added (`this run did not create an archive for ID (one already exists)` after `already_archived`, and `ID may or may not be archived (the engine's undo could not remove everything it created; ...)` after the undo warning) cannot be produced by hand: they need an engine race or a failing undo. They are pinned by the five new tests in `tests/test_retention_run.py` and were mutation-checked. The functional review does not need to reproduce them.
- `docs/ai-workflow/requirements/retention-run-mapping.json` still reads "1 stopped after an engine call started". It is the requirement record of the finished item `retention-run`, not user-facing text, and it is not edited here. Record a disposition at acceptance.
- No behaviour changes; the Manager patch release follows the merge and is not part of this review.
