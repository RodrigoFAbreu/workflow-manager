# Active Milestone

## Milestone

`retention-run` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `662e6c2`, branch `milestone/retention-run`): roadmap row 39 (#90, #198, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

Fourth slice of the owner's retention track: `workflow-manager retention-cleanup TARGET --confirm "Run the retention cleanup DIGEST12."` archives and then removes the finished work items the preview lists, through the Workflow's own script, only when the sentence is the one bound to the plan's digest. Prune is never run. The follow-ups of #198 ride along as the closing checkpoint.

### CP1: the confirmed run -- complete

- Files: `src/workflow_manager/retention_run.py` (new: `run`, `Result`, `argv_for`, the three closed argv forms, the report lines, the stop rule), `src/workflow_manager/retention_cleanup.py` (`sentence`, `confirmation_holds`, the preview's closing `next:` and by-hand lines), `src/workflow_manager/retention.py` (the public `launch_script` and `ScriptTimeout`; `_run` calls it with `report --json --repo-root ROOT`, behaviour and the 300 seconds unchanged), `src/workflow_manager/cli.py` (`--confirm`, the help, the dispatch), `tests/test_retention_run.py` (new), `tests/test_retention_cleanup.py` (the pinned preview block and help test), `docs/retention.md`, `docs/exit-codes.md`. Row 39 of `docs/ROADMAP.md` is the plan's first step and is not a deliverable.
- Behaviour: the same preflight and plan as the preview; with `--confirm` the sentence must name the fresh plan's digest (whitespace collapsed, case ignored, every match the same 12 characters) or the command refuses with exit 2 before any `archive` or `remove`. Per item, in order: `archive ID --apply` (not for `remove only`), the dry run of `remove ID` as the verification, `remove ID --apply`. The adopted policy is read before each item; the first failure of any step stops the run and the report lists what was done, what stopped and what was not attempted. After a step-3 timeout, interrupt or unreadable output the report never says "untouched" and names the user-only `remove ID --apply`. Exit 0 done, 1 stopped after an engine call started, 2 refused. Nothing is committed.
- Deviations from the plan: none in the file list. `run(target, plan, emit=None)` takes the policy digest from the plan (`plan.policy_digest`) instead of a separate argument. `TestEndToEnd` drives the real release script through the `run=`/`resolve=` seams by patching `retention.launch_script` with a launcher that runs the script in a `python3 -I -B -c` driver, with a scratch `HOME` (the engine's store is named after the origin repository, `example`).
- Evidence: `--select` of `test_retention_run.py` (38 tests, the end-to-end case ran: `zstd` is on `PATH`), `test_retention_cleanup.py` (56), `test_operator_ux.py` (130) and `test_docs.py` (44) each `verdict: exit 0`; `python3 tools/check_docs.py` exit 0.
- Failure-only mutations (fresh copy each, the named test run alone from `tests/`): the unmutated copy passes; M1 to M22, M28, M29 and M31 to M33 each fail (M18 by the interrupt killing the test process).

### CP2: the #198 fold-in -- complete

- Files: `src/workflow_manager/compatibility.py` (public `git_env(extra_config=(), drop_config_parameters=False)`; `run_git` calls it with the defaults, so its environment is unchanged), `retention.py` (`release_key`, `shown`), `retention_alert.py` (`incomplete`; the local of `evaluate` renamed `lower_bound` so it no longer shadows it), `retention_cleanup.py` (`_git` uses `git_env(config, drop_config_parameters=True)`; the `_filter_overrides` docstring re-wrapped; an INVALID refusal's cause ends with the first problem), `retention_policy.py` (`WORDS`, `shown`), `tests/test_compatibility.py` (`TestGitEnv`), `tests/test_retention_cleanup.py` (`TestNoPrivateCrossUse`, `test_an_invalid_policy_names_its_problem`, the two fixed tests), `tests/test_retention_status.py` (the renamed helper's calls).
- Deviations: `retention_alert._shown` (a different helper, over a `Result`) stays private: no sibling uses it. `test_steps_one_to_six_start_no_script` now asserts all three refusals (step 2, step 4 on a dirty tree, step 6 on a clean tree with a modified script): with the plan's wording alone step 6 was never reached.
- Evidence: `--select` of `test_retention_cleanup.py`, `test_retention_run.py`, `test_retention_alert.py`, `test_retention_status.py`, `test_retention_policy.py`, `test_compatibility.py` and `test_read_only.py` `verdict: exit 0`. Mutations M23 to M27 and M30 (fresh copy each): the unmutated copy passes, each fails its named test (M26 only after the test was strengthened). The first full gate was stopped by the 30-minute background limit (`InterruptedRunError`, no test failure); the second ran 2401/2401 units, `verdict: exit 1`, one failure: my new INVALID test compared the upper-case state name, fixed (the state is `invalid`) and `--select test_retention_cleanup.py` is `verdict: exit 0` (58 tests). The full gate has not been re-run since that test-only fix; step 3 runs it again.

### Self-review and the full gate

- The full diff `662e6c2..ccbbff2` was reviewed for correctness, layer boundaries, missing tests and maintainability. Two findings, both fixed in `7089495`:
  - A Ctrl-C while the run re-read the policy before an item left the step unset: the item line said `stopped at None: interrupted` and the closing line claimed the item "was archived and verified". The policy check is now the item's first step (`retention_run.POLICY`). An interrupt there reports `stopped before any call for this item: interrupted`, says the item was not touched and does not say "the policy changed". The new regression `TestStop.test_an_interrupt_while_reading_the_policy_claims_nothing` fails on `ccbbff2`'s runner (fresh copy, the test alone) and passes after.
  - Two texts said this Manager release never cleans up, which the confirmed run makes false. The `status`/`doctor --retention` policy block said "it sends nothing and cleans nothing", and the `adopt-retention-policy` help said "it archives, removes, prunes and sends nothing". The block now says "it sends nothing, and cleans up only when retention-cleanup runs with --confirm" (`docs/retention.md` and the two `test_retention_policy.py` pins follow). The help now says adopting archives, removes, prunes and sends nothing, and that only `retention-cleanup` with `--confirm` cleans up.
- Considered and not changed: an `OSError` starting the first script call ends with exit 1, not 2, because the call is recorded before it is launched. The preflight has just run the same interpreter for `report`, so this cannot happen in practice. A Ctrl-C in the microseconds between a call returning and the next step being set reports the earlier step, which is conservative except at `archive`.
- Evidence: `--select` of `test_retention_run.py`, `test_retention_cleanup.py`, `test_retention_policy.py`, `test_operator_ux.py` and `test_docs.py` `verdict: exit 0` (351 tests); `python3 tools/check_docs.py` exit 0. Full gate `python3 tests/run_all.py` on `7089495`: `evidence: full selection, local, 8 worker(s), head 7089495b8cec6dd4bbba0bd075008f6d3a49333c, 2401/2401 units, 16196 tests, selection_digest ccbabdbc870008ea096daa97fe4214af8553f8fdbae6caa43492571bfffcef61, tests_digest 6043f2ec6e82b3bcd2ca8e5cccea847b85ec7613d1a81c5e78565daab63e42ad`, `verdict: exit 0`.

### Automated verification before functional review

- Full gate `python3 tests/run_all.py` on `0c0e4b6` (the current head; the last code change is `3ae605a`, after the earlier full run on `7089495`): `evidence: full selection, local, 8 worker(s), head 0c0e4b6641a5f7afe34b4001dfe1ff8358d7d082, 2401/2401 units, 16197 tests, selection_digest ccbabdbc870008ea096daa97fe4214af8553f8fdbae6caa43492571bfffcef61, tests_digest 63d96a6203359872063af0aa67aa65768f05cf2552a17f6aeba388b35918342f, tree_digest a4261a9e513de3184ea568ae2bba63d0d897cd500d17106efc521fd5036b9798`, `verdict: exit 0`.

## Functional review checklist

Scope: `retention-run` (`feat:`, CP1 and CP2, both complete): `workflow-manager retention-cleanup TARGET --confirm "Run the retention cleanup DIGEST12."` archives, verifies and removes the finished work items the preview lists, through the target's own `scripts/workflow_retention.py`. Prune is never run. Nothing is committed by the run.

### Setup

- Flows 1 to 8 run offline, in a scratch clone, and write nothing into the product clone. Start with:

  ```bash
  S=$(mktemp -d "${TMPDIR:-$HOME}/rr-fr.XXXXXX")
  git clone --no-hardlinks /home/rodrigo/Workspace/workflow-manager "$S/cand"
  git -C "$S/cand" remote remove origin
  export PYTHONPATH="$S/cand/src"
  ```

- Flow 9 needs the full environment: `gh` signed in, and a throwaway GitHub origin. Run it last, in a scratch managed repository under `$S`.
- Required tools on `PATH`: `git`, `python3`. `zstd` is needed for the end-to-end test (`TestEndToEnd`); without it that one case skips with a named reason, which must be recorded.

### Test data

- No data to seed for flows 1 to 8: they read the clone's code, docs and tests.
- Flow 9 seeds a state file of finished work items, their review folders, and a committed adopted retention policy with mode `cleanup` or `both`, in the scratch repository.

### Flows

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd "$S/cand" && git diff --stat 662e6c2d95eed185b93aa5a0e38330ab05f3bacb HEAD -- src tools tests docs .github scripts .claude` | only the files the checkpoints declare (including `retention_policy.py`) and the expected bookkeeping under `docs/` |
| 2 | `python3 -m workflow_manager retention-cleanup --help` | names `--confirm`, the sentence, archive then verify then remove, the stop rule, exit 0, 1 and 2, and that prune is never run; exit 0 |
| 3 | `grep -n 'prune' "$S/cand/src/workflow_manager/retention_run.py"` | only text that says prune is never run; no argv form carries it |
| 4 | the cross-module private-name scan (command below the table) | no output (exit 1) |
| 5 | `grep -n 'git_env\|def release_key\|def incomplete' "$S"/cand/src/workflow_manager/*.py`; `awk 'length > 100' "$S/cand/src/workflow_manager/retention_cleanup.py"` | the three public names present; no output from the `awk` |
| 6 | `python3 "$S/cand/tools/check_docs.py"` | exit 0 |
| 7 | `cd "$S/cand/tests" && python3 -B -m unittest test_retention_run.TestNeverPrune test_retention_run.TestNoRemovalWithoutVerification` | `OK` |
| 8 | in scratch copies of the clone, apply mutations M1, M3, M5, M8 and M12 (plan section 4, each with `sed`) and run the named test of each | each mutated copy FAILS its named test; the unmutated clone passes |
| 9 | (full environment, user only) `python3 tests/run_all.py --select test_retention_run.py`, then `--select` of `test_retention_cleanup.py`, `test_retention_alert.py`, `test_compatibility.py`, `test_read_only.py`, `test_operator_ux.py`, `test_docs.py`. Then in the scratch managed repository, with `export GH_CONFIG_DIR=$HOME/.config/gh HOME=$S/home` (in that order, so `gh` keeps its keyring): run `workflow-manager retention-cleanup TARGET` (the preview), then `--confirm` with its sentence | each `--select` run `verdict: exit 0`, no `OrphanProcessError`; the run archives and removes the planned items; `git status` of the scratch repository unchanged; a second run reports nothing to do |

Flow 4 command (run from `$S/cand`):

```bash
cd "$S/cand/src/workflow_manager" && grep -nE '(compatibility|retention|retention_alert|retention_policy|retention_run|retention_cleanup)\._|from \.[a-z_]+ import _' retention.py retention_alert.py retention_cleanup.py retention_policy.py retention_run.py
```

### Known limitations and out of scope

- Prune is never run and never part of cleanup.
- The sentence proves the plan was shown, not who asked. It is a formality for any job that reads it back from the preview.
- An archive store on another file system than `.ai-review` is refused with `cross_device` on every run (the default store is under `HOME`).
- Flows 1 to 8 do not touch GitHub, `gh`, `claude`, `codex` or `ssh`: they run offline against the code. Only flow 9 exercises a real forge.
- A killed Manager during removal leaves `.removing/ID`; the next preflight refuses it, and the user finishes it by hand.
- No version is edited, and nothing is pushed or committed by the run.
- Pull request title (for the later release, not part of this review): `feat: archive and remove finished work items under an adopted retention policy with retention-cleanup --confirm`.
