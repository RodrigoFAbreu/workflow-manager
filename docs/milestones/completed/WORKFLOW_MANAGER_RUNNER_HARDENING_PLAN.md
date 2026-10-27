# Workflow Manager: Test Runner Hardening (Revision 1)

`work_item_id: runner-hardening` -- `governing_workflow_version: "2.2"`

**Deliverable:** the test runner (a) handles `SIGINT` with a handler of its own,
so a run started with `SIGINT` ignored (a background job started with `&` from a
non-interactive shell) is still interrupted cleanly by it, and (b) reports a
failure of the cleanup that follows the printed report as a warning on stderr,
so a printed `verdict: exit 0` stays exit 0.

**Work item type:** `process`. **Base commit:** `f0ea500` (tip of `main`;
Workflow 2.22.0 installed, automatic gates). **Branch:**
`milestone/runner-hardening`. **Scope source:** `docs/ROADMAP.md` row 16. Tests
and docs only (`tests/`, `docs/ARCHITECTURE.md`): the pull request title is
`test: ...`, which releases nothing. **Not in this milestone:** any change to
what a test or the verdict judges, to the barrier, the lock or the leak check,
anything under `src/`, and the third follow-up of the row (section 4: dropped).
Two changes in one file and one test module, one review surface, two
checkpoints (the sizing rule's limit); nothing needed splitting.

## 1. The two defects, reproduced at `f0ea500`

Both were reproduced against a scratch checkout (the `WAIT_MODULE` pattern of
`tests/test_parallel_runner.py`), before any change.

**SIGINT ignored.** `executor._install_signal_handlers` installs a `SIGTERM`
handler only; `SIGINT` relies on Python's default handler, which the
interpreter installs at start-up only when `SIGINT` is not already ignored. A
run started with `SIGINT` ignored (`preexec` `SIG_IGN`, equal to `trap '' INT`
in a non-interactive shell before `exec`) keeps ignoring it: with the chunk
running, `SIGINT` to the executor left it alive and the run finished normally
(exit 0) once the chunk was released, instead of exit 2
(`InterruptedRunError`) with the barrier restored. The existing
`test_sigterm_and_sigint_kill_the_chunk_restore_the_barrier_and_exit_2` has
this shape when the whole test run itself was started that way: its
`communicate(timeout=60)` times out.

**Post-report cleanup.** `executor.local_run` prints the report (ending
`verdict: exit 0`) and then removes its temporary run directory
(`isolation.clean_tmpdir(run_dir)`). An `OSError` there (a busy mount, a
permission change under the directory) propagates to `cli.main`'s catch-all,
which prints `run_all: error[OSError]: ...` with a traceback and returns 2:
the report said exit 0, the process exits 2. Reproduced with a stub that raises
`OSError` for the `wm-run-*` directory only (in-process `cli.main`): stdout ends
`verdict: exit 0`, return value 2.

## 2. Decisions

**SIGINT: one handler, both signals.** `_install_signal_handlers` installs the
same handler for `SIGTERM` and `SIGINT` (raise `KeyboardInterrupt`, so every
`finally` runs: chunk kill, barrier restore, lock release) and returns both
previous handlers; `_restore_signal_handlers` puts both back, including a
previous `SIG_IGN`. For an interactive Ctrl-C the behaviour is the same as the
default handler's (`KeyboardInterrupt`), so a run interrupted by `SIGTERM` or
Ctrl-C still restores the write barrier, kills the chunks and exits 2.
Main thread only, as today. One consequence, accepted and tested: a chunk
no longer inherits an ignored `SIGINT` from the run (a handler is reset to the
default at `exec`); chunks are in their own session, so a terminal Ctrl-C never
reached them either way.

**Post-report cleanup: which failures are demoted.** Only the removal of the
run's own temporary directory, which happens after `emit_report` has printed
the verdict, in `local_run` (the only mode that removes a directory after the
report: `run_shard` and `aggregate` keep theirs). An `OSError` becomes
`warning: could not remove the run directory <path>: <reason>; the verdict is
unchanged` on stderr, the directory is left where it is, and the exit code is
the printed one. The helper sits beside `append_side_effect` (same contract,
same wording of the last clause). **Kept as they are** (they corrupt or
qualify the result, or happen before the report): the barrier restore (before
the report: an unrestored barrier is a hazard the user must see); the
integrity, window, leak and orphan faults, which the verdict itself reports; the
primed-cache stray-entry check in `cli._main` (`PrimingError`: a discipline
fault of the run, reported as today); and any non-`OSError` error, which is a
programming error, not cleanup noise.

## 3. Tests (all in `tests/test_parallel_runner.py`; the failing ones first)

Written and run first, recorded as failing at `f0ea500`, then green after the
change. Nothing writes into the repository: scratch checkouts under the test's
own temporary directory, and a unit test that saves and restores the process's
own signal table.

* `start_cli` gains `sigint_ignored=False`; true starts the run through
  `sh -c 'trap "" INT; exec "$@"'`, the exact shape of a `&` job.
* Class `TestSigintWhenIgnored` (`_CliCase`): a run started with `SIGINT`
  ignored and interrupted by `SIGINT` exits 2 with `InterruptedRunError`, the
  chunk's group is dead, the guarded modes equal the pre-run modes and no
  `barrier.json` remains. The same for `SIGTERM` as a control (passes at the
  base). A `finally` always releases the stop file and, if the run is still
  alive, kills and reaps it, so a failing test leaves no process behind.
* A unit test: with `SIGINT` set to `SIG_IGN`, `_install_signal_handlers()`
  makes `SIGINT` raise `KeyboardInterrupt` and `_restore_signal_handlers`
  returns it to `SIG_IGN`; same for a custom previous handler and for
  `SIGTERM`. A second case: off the main thread it installs nothing.
* Class `TestPostReportCleanupFailure`: `cli.main` in-process on a green
  scratch run with the temporary run directory's removal raising `OSError`
  (stub filtered on the `wm-run-` name, so the chunks' own cleanups are
  untouched): exit 0, stdout ends `verdict: exit 0`, stderr has the warning
  and the directory path, no `error[`; the control without the stub is exit 0
  with no warning. A failing run (exit 1) keeps its directory and attempts no
  removal. A pre-report fault stays exit 2: a barrier restore that raises
  still produces `error[...]` and exit 2 (the kept case).
* Existing tests untouched except the shared helper's new keyword.

**Not fooled by the runner under test.** The new tests exercise a scratch copy
of the tree (`scratch_checkout`), so the edited `tests/parallel/` is what runs
in the child. The fail-first evidence is taken before `executor.py` is edited.
While any `run_all` is in progress nothing is written to the repository; the
gate is run once, after the last edit.

## 4. The third follow-up: dropped, with the evidence

"An interrupt inside the fork-to-exec window of a spawned process" was tried.
A seam on `subprocess._fork_exec` that raises `KeyboardInterrupt` right after
the real fork returns does leak: `isolation.run_chunk`'s `Popen` raised before
`proc` was assigned, the `finally` found nothing to kill, and the wrapper's
group stayed alive. But it cannot be reproduced without that CPython-private
seam, and a real signal needs a main-thread chunk (the exclusive phase) in a
window of microseconds; the pool path has a different, larger race (the
interrupt kills only registered groups) that is its own mechanism. Fixing
either needs private `subprocess` internals or a signal-mask protocol with the
wrapper: a third mechanism with its own review surface. Dropped as the row
allows; the evidence stays here and the row's text records it. If a run is
ever lost to it, it is a new item.

## 5. Docs

`docs/ARCHITECTURE.md`, "Verification execution": the barrier paragraph says
the run restores the modes "including on `SIGINT` and `SIGTERM`"; it gains one
sentence that this holds when the run was started with `SIGINT` ignored (a `&`
job), and one that a failure to remove the run's temporary directory after the
report is a warning on stderr, never the exit code. No page names a milestone.

## 8. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | SIGINT handler, post-report cleanup warning, tests and architecture note | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- both changes, their tests and the architecture note

**Files:** `tests/parallel/executor.py`, `tests/test_parallel_runner.py`, `docs/ARCHITECTURE.md`.

Order: the section 3 tests first, recorded failing at `f0ea500`; then
`_install_signal_handlers`/`_restore_signal_handlers` and the post-report
cleanup helper in `local_run`; then the architecture sentences. Row 16 of
`docs/ROADMAP.md` is marked Current here (its "Later: when a run is next lost
to either" text replaced, the third follow-up recorded as dropped).

Evidence: the new tests fail first and are green after; `python3
tests/run_all.py --select test_parallel_runner.py` and `--select test_docs.py`
green; the scratch checks of section 1 re-run: `SIGINT` to a run started with
it ignored exits 2 and restores the barrier, the stubbed cleanup failure leaves
the printed exit 0 and a stderr warning; the full gate green, run last.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** docs/ROADMAP.md and docs/ACTIVE_MILESTONE.md, written by the acceptance step.

Row 16 Done at acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone.
Both stay excluded at both stages, as in every item. No version is edited: a
`test:` title releases nothing.
<!-- /CP2 -->

## 9. Risks

* An installed `SIGINT` handler changes what a chunk inherits (section 2);
  no test depends on an ignored `SIGINT` in a chunk, and the full gate shows it.
* The demoted cleanup leaves a `wm-run-*` directory behind on failure; the
  warning names it. It is outside the checkout and the orphan check.
* The real-process proof of the cleanup case uses a stub in-process; the
  functional review repeats it in a scratch checkout.

## 10. Open decisions

None: nothing here finalises a row of `docs/TECHNICAL_DECISIONS.md` (the file
does not exist in this repository).
