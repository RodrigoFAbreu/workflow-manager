# Active Milestone

## Milestone

`runner-test-cleanup` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `c041050`, branch `milestone/runner-test-cleanup`): roadmap row 32 (#119, items 1 to 4). A `test:` pull request title (releases nothing).

The runner-hardening tests and notes say exactly what they check. The interrupt test's cleanup also ends the chunk's process group (`_end_group`, covered by `TestEndGroup`) before it writes the stop file, so a failing run no longer leaves the chunk to `WAIT_MODULE`'s 120-second deadline. `test_a_failing_run_keeps_its_directory_and_attempts_no_removal` asserts the directory the verdict line names exists and holds `results.json`. `remove_run_dir`'s docstring says the directory may be left behind. `docs/ARCHITECTURE.md` says the signal handler covers all three modes through `_install_signal_handlers`. No behaviour, printed text or exit code of the runner changes; no `src/` change; no Workflow change.

### CP1: the interrupt cleanup, the kept-directory assertion and the two wordings -- complete

- Commit `472d138`: `tests/test_parallel_runner.py`, `tests/parallel/executor.py` (docstring lines only), `docs/ARCHITECTURE.md`.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 32 is Done (accepted by policy); this record.

### Failure-only mutations

Plan section 5, run in a `git clone` of `472d138` (scratch copy; `T` is `test_sigint_interrupts_a_run_that_started_with_it_ignored`, `K` the kept-directory test, `E` is `TestEndGroup`). The unmutated candidate passes `E` (2 tests) and `T` (0.5 s).

| # | Mutation | Result |
| --- | --- | --- |
| M0 | no stop write in `_interrupt` | applied with M1, M2 or M3 only, so a left-over group is deterministic |
| M1 | `_end_group` never kills | `E` fails after 5 s; with M2 and M0, `T` fails with "outlived the cleanup" (45.5 s) and the group stays listed |
| M2 | the executor does not kill chunks on interrupt | base test file with M0: `T` fails at `assertTrue(_dead(pgid))` (30.5 s), group listed; candidate without M0: same assertion (30.5 s), nothing listed; candidate with M0: same, nothing listed |
| M3 | the cleanup call removed (with M2, M0) | `T` fails at the same assertion without "outlived the cleanup" (30.5 s), group listed |
| M4 | run directory removed before `if not keep:` | `K` fails at `Path(kept).is_dir()`; the base test file passes the same mutation (the defect item 2 closes) |

Every group a mutation left running was ended with `kill -9 -<pgid>`.

### Self-review

The diff against `c041050` was read against the plan: three files changed (`tests/test_parallel_runner.py`, `tests/parallel/executor.py` docstring only, `docs/ARCHITECTURE.md`, one sentence with no work-item id); nothing under `src/` or `tools/`.

## Functional review checklist

Scope: test code, one docstring and one sentence of `docs/ARCHITECTURE.md`. The runner's behaviour, printed text and exit codes do not change, and no `src/` or `tools/` file changes. The functional review checks that the tests and wording say what the plan says. Nothing here needs a forge, a network or a real `claude`, `codex` or `ssh`.

### Setup (every flow)

- **Run as a non-root user.** `run_all` and the CLI tests refuse to run as root (`RootRefusedError`: running as root disables the write barrier). Under `unshare -rn` (which maps you to root) `TestLockAndRecoveryThroughTheCli` and `TestPostReportCleanupFailure` fail during setup. That is a sandbox setup problem, not a finding.
- **Never write into the product clone.** Make a scratch directory `S` in the sandbox's writable scratch area (for example `S=$(mktemp -d "$HOME/.cache/rtc-fr.XXXXXX")`), then clone the branch head: `git clone --no-hardlinks <product clone> "$S/cand"`. Flows 1 to 5 read the clone; flows 6 to 10 run there or in copies made with `command cp -rf "$S/cand" "$S/mut"`. The clone's `origin` is the product clone; no flow fetches, pushes or calls `gh`, `claude`, `codex` or `ssh`.
- **Tools on `PATH`:** `git`, `python3`, `grep`, `sed`, `tr`, `cp`, `rm`, `ps`, `kill`, `mktemp`, `timeout`.
- **Timeouts:** an interrupt test passes in about 0.5 s; under mutation M2 it takes about 30 s; M1 with M2 about 45 s. Flow 10 takes several minutes. Allow at least 120 s per flow and 1500 s for flow 10.
- **Flow 10 needs a primed release cache** (every tested release cached under `~/.cache/workflow-manager/releases`, or `WORKFLOW_MANAGER_RELEASE_CACHE` pointing at a primed copy). With no cache and no network, priming fails with `PrimingError` (exit 2). That is an environment failure, not a finding.

### Test data

None is seeded. The data is the clone at the branch head and its ancestor `c041050`.

### Flows

Run each command as written, from the directory named. Record the exit code and the matching lines. Report pass or fail per flow.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd "$S/cand" && git diff --stat c041050c55d07ee7dd8f8a4c1eb0534e369b36a3 HEAD -- src tests tools docs/ARCHITECTURE.md` | exactly `tests/test_parallel_runner.py`, `tests/parallel/executor.py` and `docs/ARCHITECTURE.md`; nothing under `src/` or `tools/`. Then `git diff c041050c55d07ee7dd8f8a4c1eb0534e369b36a3 HEAD -- tests/parallel/executor.py \| grep '^[+-]' \| grep -v '^+++\|^---'`: only docstring lines (the `remove_run_dir` docstring) |
| 2 | `grep -n "def _end_group\|class TestEndGroup\|outlived the cleanup\|results kept in" "$S/cand/tests/test_parallel_runner.py"` | `_end_group` defined once, `TestEndGroup` defined once, the cleanup message once; the kept-directory assertion line (`results kept in` in its `partition`) |
| 3 | `grep -n "may be left behind" "$S/cand/tests/parallel/executor.py"`; `grep -c "stays where it is" "$S/cand/tests/parallel/executor.py"` | one match in the `remove_run_dir` docstring; count `0` |
| 4 | `tr '\n' ' ' < "$S/cand/docs/ARCHITECTURE.md" \| grep -o "all three modes (a local run, .\{0,160\}"` | one match (newlines are normalised, so line wrapping cannot hide it) naming a local run, `--run-shard`, `--aggregate` and `_install_signal_handlers` |
| 5 | `cd "$S/cand" && git diff c041050c55d07ee7dd8f8a4c1eb0534e369b36a3 HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|runner-test-cleanup'` | `0`: no added line names a milestone or a work-item id |
| 6 | `cd "$S/cand/tests" && python3 -B -m unittest test_parallel_runner.TestEndGroup`; then the unmutated `T` and `K`: `python3 -B -m unittest test_parallel_runner.TestLockAndRecoveryThroughTheCli.test_sigint_interrupts_a_run_that_started_with_it_ignored` and `python3 -B -m unittest test_parallel_runner.TestPostReportCleanupFailure.test_a_failing_run_keeps_its_directory_and_attempts_no_removal` | `TestEndGroup`: 2 tests, `OK`, exit 0. `T` and `K`: `OK`, under a second each |
| 7 | Make `"$S/mut1"`: in `_end_group`, `sed -i 's\|os.killpg(pgid, signal.SIGKILL)\|pass\|' "$S/mut1/tests/test_parallel_runner.py"`. Run `python3 -B -m unittest test_parallel_runner.TestEndGroup` from `"$S/mut1/tests"`. Then make `"$S/mut4"`: `sed -i '/^    if not keep:$/i\    __import__("shutil").rmtree(run_dir, ignore_errors=True)' "$S/mut4/tests/parallel/executor.py"`, and run `python3 -B -m unittest test_parallel_runner.TestPostReportCleanupFailure.test_a_failing_run_keeps_its_directory_and_attempts_no_removal` from `"$S/mut4/tests"` | Each `sed` changes exactly one line (`git -C "$S/mut1" diff --stat`, `git -C "$S/mut4" diff --stat`). `TestEndGroup`: exit 1, `test_a_live_group_is_ended` fails with `AssertionError: False is not true`, in about 5 s. `K`: exit 1 at `Path(kept).is_dir()` (`False is not true` followed by the kept path), in about 0.5 s |
| 8 | Make `"$S/mut2b"` from a `cp` of `"$S/cand"`: `git checkout -q c041050c55d07ee7dd8f8a4c1eb0534e369b36a3 -- tests/test_parallel_runner.py` (the base test file); in `_interrupt`, `sed -i '/^    def _interrupt(self, signum)/,/^    def /{s\|^\( *\)stop.write_text("")$\|\1pass\|}' tests/test_parallel_runner.py`; in the executor, `sed -i 's\|os.killpg(pgid, signal.SIGKILL)\|pass\|' tests/parallel/executor.py`. Run `T` from `"$S/mut2b/tests"`. Then `ps -eo pgid,args \| grep '[t]est_scratch_wait'` | exit 1 at `assertTrue(_dead(pgid))` after about 30 s, and the chunk's process group is **listed** (the `test_scratch_wait` process is still running). End that group with `kill -9 -<pgid>` before the next flow. Repeat on the candidate test file with only the executor `sed` applied (`"$S/mut2"`): same assertion; nothing listed |
| 9 | From `"$S/mut2"` (executor `sed` only), add the `_interrupt` `stop.write_text` `sed` and the `gone = []` `sed` (`sed -i 's\|gone = \[_end_group(group) for group in pgids\]\|gone = []\|' ...`), run `T`, then `ps` as in flow 8. Next, a fresh copy with the executor `sed`, the `_end_group` kill `sed` and the `_interrupt` `stop.write_text` `sed`, run `T`, then `ps` | First run: exit 1 at `assertTrue(_dead(pgid))` with no `outlived the cleanup` message, group listed. Second run: exit 1 at `assertTrue(_dead(pgid))` and also `outlived the cleanup` (chained on the first failure), group listed. End each group with `kill -9 -<pgid>` |
| 10 | `cd "$S/cand" && python3 tests/run_all.py --select test_parallel_runner.py` (output to a file) | exit 0; no `OrphanProcessError`. Any `tolerated orphans` lines name only the declared classes in `tests/parallel/resources.json`'s `orphan_sources`, and none names `TestEndGroup` |

Flows 1 to 5 write nothing. Flows 6 to 10 write only under `$S`. Before ending any flow, `ps -eo pgid,args | grep '[t]est_scratch_wait'` must show nothing; kill anything it lists (`kill -9 -<pgid>`).

### Known limitations and out of scope

- Flows 7 to 9 are mutation checks on scratch copies. They show that the tests catch each defect; they do not prove the fix on every machine. They are timing-based: a timing-only difference (a wait lengthened by load) is rerun once and reported, not counted as a fail.
- Flow 10 runs the runner's whole `test_parallel_runner.py` selection through `run_all`, which primes the release cache first. It is slow; a host with a busy `/tmp` can differ in timing, not in outcome.
- Out of scope: `src/`, every other test (including `test_sigterm_and_sigint_kill_the_chunk_restore_the_barrier_and_exit_2`), the runner's behaviour, `tests/parallel/resources.json`, the version (a `test:` title releases nothing).
- The `remove_run_dir` docstring and the `ARCHITECTURE.md` sentence are wording only; they are checked by reading, flows 3 to 5.
- If a flow fails, report the output. Do not fix anything in the product clone; the repair belongs in the item's own findings.
