# Active Milestone

## Milestone

`runner-hardening` -- complete (accepted by policy; `governing_workflow_version: "2.2"`, `process`, plan revision 1, implementation revision 1, base `f0ea500`, branch `milestone/runner-hardening`): roadmap row 16. A `test:` pull request title (tests and docs only; nothing is released). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RUNNER_HARDENING_PLAN.md`.

Two changes to the test runner (`tests/parallel/executor.py`):

- **SIGINT when ignored.** A run started with `SIGINT` ignored (a `&` job of a non-interactive shell) is interrupted by `SIGINT` like one started with it at its default: exit 2, `InterruptedRunError`, the chunks killed, the write barrier restored. One handler serves `SIGTERM` and `SIGINT`.
- **Post-report cleanup.** Removing the run's temporary directory after the printed verdict is a warning on stderr (`warning: could not remove the run directory ...; the verdict is unchanged`), never the exit code. A printed `verdict: exit 0` stays exit 0.

Not in this milestone: anything that judges a test, the barrier, the lock or the leak check; anything under `src/`; the third follow-up of the row (an interrupt in the fork-to-exec window), dropped with its evidence in the plan, section 4.

Automated verification: the full gate (`python3 tests/run_all.py`) exited 0 at head `b78d19b` (2305 of 2305 units, 15231 tests, orphan check on). No file under `src/`, `tools/` or `tests/` has changed since that head.

### CP1: SIGINT handler, post-report cleanup warning, tests and architecture note -- complete

- `tests/parallel/executor.py`: `_install_signal_handlers` and `_restore_signal_handlers` (both signals, the previous handlers, including `SIG_IGN`); `remove_run_dir` in `local_run`.
- `tests/test_parallel_runner.py`: `TestSigintWhenIgnored`, `TestPostReportCleanupFailure`, and a unit test of the install and restore pair.
- `docs/ARCHITECTURE.md`, "Verification execution": two sentences (the barrier restore with `SIGINT` ignored; the cleanup warning).

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md`: row 16 marked In progress, then Done at acceptance (by policy).
## Functional review

Flows F1 to F4 from the checklist passed on the candidate (`14eaa15`), and the extras X1 and X2 reproduce the two original defects on the base `f0ea500`, all as expected (independent executor, `claude-sonnet-5-5`, round 1). The milestone was accepted by policy; the Optional findings are dispositioned in `docs/ai-workflow/registry/runner-hardening-dispositions.json` (1 fixed, 6 follow-ups on RodrigoFAbreu/workflow-manager#119, 2 dropped) and recorded in `docs/milestones/completed/runner-hardening-findings.md`.

## Next action

Roadmap row 16 is Done. The pull request (#120, a `test:` title, nothing released) merges after the acceptance commit. Next incomplete row: 17 (report the finished-work archive state on managed repos, #90), then `/milestone-plan`.
