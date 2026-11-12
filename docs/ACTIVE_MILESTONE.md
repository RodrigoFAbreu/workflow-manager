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

### CP2: the #198 fold-in -- not started

Public names (`git_env`, `release_key`, `incomplete`, `shown`, `WORDS`), the two test fixes, the INVALID-policy problem; then M23 to M27 and M30 and the full gate.
