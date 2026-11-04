# Workflow Manager: The Runner-Hardening Tests and Notes Say Exactly What They Check (Revision 3)

`work_item_id: runner-test-cleanup` -- `governing_workflow_version: "2.2"`

**Deliverable:** the interrupt test kills and waits for its chunk's process
group when it fails; the kept-directory test asserts the directory; the
`remove_run_dir` docstring and one architecture sentence say what is true
(roadmap row 32, issue #119, items 1 to 4).

**Work item type:** `process`. **Base commit:** `c041050`
(`c041050c55d07ee7dd8f8a4c1eb0534e369b36a3`, tip of `main`, Manager 1.14.8;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/runner-test-cleanup`. **Scope source:** `docs/ROADMAP.md` row 32
(added by this item, Current now, Done at acceptance). Test code, one
docstring and one documentation sentence: no behaviour of the runner changes,
no `src/` change, no printed text. The pull-request title is a `test:` change
and **releases nothing** (the docstring and the sentence ride along); check it
with `python3 tools/release/release.py check-title "test: ..."`. One
mechanism: the runner-hardening tests and notes say exactly what they check.
Two checkpoints, three files, one review surface.

## 1. Each item checked against main (`c041050`)

| Item of #119 | Still open on main? | Evidence | Action |
| --- | --- | --- | --- |
| 1. the interrupt test's cleanup kills only the executor | Yes | `_interrupt` (`TestLockAndRecoveryThroughTheCli`, `tests/test_parallel_runner.py`) reads `pgid` from the lock and its `finally` writes the stop file, kills and reaps `proc`, nothing else. Measured in a scratch clone: with the executor's `Engine.interrupt` kill replaced by `pass`, the test fails at `assertTrue(_dead(pgid))` and the chunk group (reaper plus unit) is still running after the test returned | kill the known chunk group during failure cleanup and wait for its exit (section 2) |
| 2. the failing-run test does not assert the kept directory | Yes | `test_a_failing_run_keeps_its_directory_and_attempts_no_removal` asserts `attempted == []` and no warning. Measured: with `shutil.rmtree(run_dir)` inserted before `if not keep:` in `local_run`, the test still passes | assert the directory named by the verdict line exists (section 3) |
| 3. `remove_run_dir` says the directory "stays where it is" | Yes | `tests/parallel/executor.py`, the docstring; `isolation.clean_tmpdir` runs `shutil.rmtree` after listing the residue and can fail midway | say it may be left behind |
| 4. no sentence says the SIGINT handler covers all three modes | Yes | `docs/ARCHITECTURE.md` ("The guarded trees are read-only while a run is live") ends the handler sentence with "the run installs its own handler for both"; `local_run`, `run_shard` and `aggregate` each call `_install_signal_handlers()` | one sentence, section 4 |
| 5. the third original follow-up | Obsolete, stays dropped | the plan of the runner-hardening item records the evidence (an interrupt inside the fork-to-exec window leaks only when private CPython API is wrapped) | none |

Out of scope, stays as it is: `src/`, every other test (including
`test_sigterm_and_sigint_kill_the_chunk_restore_the_barrier_and_exit_2`, which
shares the shape but is not named by the issue), any behaviour of the runner,
`tests/parallel/resources.json`.

## 2. Item 1: the failure cleanup of `_interrupt`

After `_dead`, a module-level helper:

```python
def _end_group(pgid, timeout: float = 15.0) -> bool:
    """Failure cleanup: SIGKILL the process group `pgid` unless its leader has
    already exited, then wait until the leader has exited. True when it has
    (also when there is nothing to kill: `None`, or a group already gone)."""
    if pgid is None or _dead(pgid):
        return True
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return _wait_until(lambda: _dead(pgid), timeout)
```

It kills only a group whose leader is still alive, so on the passing path it
does nothing and cannot mask the test's own `assertTrue(_dead(pgid))` (which
stays after the signal, before the cleanup): the cleanup runs only for what
the assertions left alive. The cleanup runs **before** the stop file is
written: the stop file releases the chunk (`WAIT_MODULE` polls it every
0.05 s), so writing it first lets the group exit by itself while `_end_group`
waits and the kill is never exercised. The stop write still stays ahead of
the final assertion, but it is only a best effort: the case's teardown
(`_ScratchCase._cleanup`) removes the temporary directory, stop file
included, milliseconds later, so the chunk (polling every 0.05 s) sees the
file only if a poll lands in that window. When the helper could not end the
group, the group usually runs on to `WAIT_MODULE`'s 120-second deadline (issue
#119, item 1, says the same). Section 5's mutations therefore take the stop
write out (M0) wherever they expect a group to be left listed. `_interrupt` becomes one `try`/`finally`: its
assertions move inside the `try`, and the `finally` is

```python
        finally:
            pgids = {pgid, *_lock_holder(scratch).get("chunk_pgids", ())}
            gone = [_end_group(group) for group in pgids]
            stop.write_text("")
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
            self.assertTrue(all(gone), "the chunk's process group outlived the cleanup")
```

The lock still names the chunk when the executor died (the lock file stays,
as the killed-executor test relies on), so a failure before `pgid` is read
(the executor exits early) is covered too. The same file gets a small class
`TestEndGroup` (plain `unittest.TestCase`, hermetic): a live group
(`subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
start_new_session=True)`, killed by `addCleanup` and waited) is ended by
`_end_group(proc.pid, timeout=5)` and `_dead(proc.pid)` holds; `None` and a
group whose leader has been waited are both true without raising.

## 3. Item 2: the kept directory

In `test_a_failing_run_keeps_its_directory_and_attempts_no_removal`, after the
existing assertions:

```python
        kept = out.rstrip().splitlines()[-1].partition("results kept in ")[2]
        self.assertTrue(kept, out[-500:])
        self.assertTrue(Path(kept).name.startswith("wm-run-"), kept)
        self.assertTrue(Path(kept).is_dir(), kept)
        self.assertTrue((Path(kept) / "results.json").is_file(), kept)
```

The verdict line names the directory (`emit_report`: `verdict: exit 1;
results kept in <dir>`), so the test asserts the directory the run says it
kept. The test already leaves that directory under its own temporary path
(removed by the case's teardown); no new leftover.

## 4. Items 3 and 4: wording

`remove_run_dir`'s docstring (`tests/parallel/executor.py`) ends: "an
`OSError` becomes a warning, never an exit code, and the directory may be left
behind (`clean_tmpdir` can fail midway through `shutil.rmtree`)". In
`docs/ARCHITECTURE.md`, after "the run installs its own handler for both.":
"The same handler covers all three modes (a local run, `--run-shard` and
`--aggregate`): each installs it through the one shared
`_install_signal_handlers`." No milestone id appears in the page.

## 5. Failure-only mutations

Each is a `sed` on a fresh copy of the candidate (`command rm -rf $S/mut;
command cp -rf $S/cand $S/mut`; `cand` is a clone of the branch head). The
tests need the full environment (about 30 s for an interrupt run under M2,
hermetic: a scratch checkout and loopback-free subprocesses), run from `$S/mut/tests` as
`python3 -B -m unittest test_parallel_runner.<Class>.<test>`; `T=` the
`TestLockAndRecoveryThroughTheCli` test
`test_sigint_interrupts_a_run_that_started_with_it_ignored`, `K=` the
`TestPostReportCleanupFailure` test of item 2, `E=TestEndGroup`.

| # | Mutation | Must happen |
| --- | --- | --- |
| M0 | no stop write (applied together with M1, M2 or M3 wherever a group must be left listed, so that result is deterministic): in `test_parallel_runner.py`, `/^    def _interrupt(self, signum)/,/^    def /{s\|^\( *\)stop.write_text("")$\|\1pass\|}` (the one `_interrupt` body, on the base file and on the candidate) | none alone; it only removes the race described in section 2 |
| M1 | the helper never kills: in `_end_group`, `s\|os.killpg(pgid, signal.SIGKILL)\|pass\|` | `E` fails (its live-group test returns false after 5 s); with M2 and M0 also applied `T` fails with "outlived the cleanup" (chained on the `assertTrue(_dead(pgid))` failure), takes about 45 s (30 s for the executor's wait plus the helper's 15 s) and leaves the group listed (with M0 on every run; killed by the flow). Measured on the revised order of section 2: 45.5 s |
| M2 | the executor does not kill chunks on interrupt (the intended defect): in `tests/parallel/executor.py` `Engine.interrupt`, `s\|os.killpg(pgid, signal.SIGKILL)\|pass\|` | on the **base** test file (with M0, which makes the result deterministic: measured six of six runs, `TMPDIR` on disk and on tmpfs, the group listed each time), `T` fails at `assertTrue(_dead(pgid))` and the group is left running (`ps -eo pgid,args` shows `test_scratch_wait`); on the **candidate** (without M0), `T` fails at the same assertion and nothing is left running |
| M3 | the cleanup call is removed (with M2 and M0 applied): `s\|gone = \[_end_group(group) for group in pgids\]\|gone = []\|` | `T` fails at the same assertion, without "outlived the cleanup" (about 30 s), and the group is left listed. Measured on the revised order |
| M4 | the run directory is removed without `clean_tmpdir`: in `local_run`, `/^    if not keep:$/i\    __import__("shutil").rmtree(run_dir, ignore_errors=True)` | `K` fails at `Path(kept).is_dir()`; the base test file passes the same mutation (the defect item 2 closes) |

M2 on the candidate shows the test still fails on its intended defect first,
as it must, and that nothing is left behind; it is not by itself the proof
that the kill repairs the leak. M1 and M3 are that proof: with the executor's
kill gone, the group is left listed (with M0) when the helper does not kill
(M1) or is not called (M3), and is gone when both are present (M2, no M0). Without M0 "listed" is not certain
(a poll can see the stop file before teardown removes it); the flows below
therefore always apply M0 where they expect a listed group. Measured on the
revised order of section 2 (the unmutated `T` passes in 0.5 s). A group left running by a mutation
run is ended by `kill -9 -<pgid>` before the next flow.

## 6. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The interrupt cleanup, the kept-directory assertion and the two wordings | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the interrupt cleanup, the kept-directory assertion and the two wordings

**Files:** `tests/test_parallel_runner.py`, `tests/parallel/executor.py`,
`docs/ARCHITECTURE.md`.

Sections 2 to 4: `_end_group`, `TestEndGroup` and the reshaped `_interrupt`
in `tests/test_parallel_runner.py`; the four added assertions of the
kept-directory test; the docstring of `remove_run_dir` in
`tests/parallel/executor.py` (no code line there changes); the one sentence in
`docs/ARCHITECTURE.md`. M1 to M4 touch scratch copies only.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 32 of `docs/ROADMAP.md` is added by this plan as Current and is Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: a `test:` title releases nothing. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 7. Functional review

Flows 1 to 5 run offline (no network, no `gh`, no installs) in a scratch
directory `S=$(mktemp -d "$HOME/.cache/rtc-fr.XXXXXX")` and in this
repository's read-only `git` commands. Flows 6 to 10 are tagged "(needs the
full environment)": they run the repository's tests, which need the primed
release cache (or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror) that
`tests/run_all.py` needs, and nothing else once primed; flow 10 is last.
Setup: `git clone --no-hardlinks "$PWD" $S/cand` at the candidate head.
Mutations use `command cp`/`command rm`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat c041050c55d07ee7dd8f8a4c1eb0534e369b36a3 HEAD -- src tests tools docs/ARCHITECTURE.md` | exactly `tests/test_parallel_runner.py`, `tests/parallel/executor.py`, `docs/ARCHITECTURE.md`; nothing under `src/` or `tools/`; `git diff` of `tests/parallel/executor.py` shows only docstring lines |
| 2 | `grep -n "def _end_group\|class TestEndGroup\|outlived the cleanup\|results kept in" $S/cand/tests/test_parallel_runner.py` | the helper, the class and the cleanup message once each; the kept-directory assertion line |
| 3 | `grep -n "may be left behind" $S/cand/tests/parallel/executor.py`; `grep -c "stays where it is" $S/cand/tests/parallel/executor.py` | one match in the `remove_run_dir` docstring; count 0 |
| 4 | `tr '\n' ' ' < $S/cand/docs/ARCHITECTURE.md \| grep -o "all three modes (a local run, .\{0,160\}"` | one match (newlines are normalised, so page wrapping cannot hide it) naming a local run, `--run-shard`, `--aggregate` and `_install_signal_handlers` |
| 5 | `git diff c041050c55d07ee7dd8f8a4c1eb0534e369b36a3 HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|runner-test-cleanup'` | `0`: no added line names a milestone or a work-item id |
| 6 | (needs the full environment) in `$S/cand/tests`: `python3 -B -m unittest test_parallel_runner.TestEndGroup` | exit 0 |
| 7 | (needs the full environment) fresh copy, M1, `E`; fresh copy, M4, `K` | each exit 1 by the named assertion |
| 8 | (needs the full environment) fresh copy, M2 and M0, `T` on the base test file; fresh copy, M2 only, `T` on the candidate; after each, `ps -eo pgid,args \| grep '[t]est_scratch_wait'` | both exit 1 at `assertTrue(_dead(pgid))`; base: the group is listed on every run (end it with `kill -9 -<pgid>`); candidate: nothing listed |
| 9 | (needs the full environment) fresh copy, M2, M3 and M0, `T`; then M2, M1 and M0, `T`; `ps` as above | each exit 1 at `assertTrue(_dead(pgid))`; the second also with "outlived the cleanup" (chained on the first failure); each leaves the group listed (end it) |
| 10 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_parallel_runner.py` | exit 0, no `OrphanProcessError`; the report's `tolerated orphans (declared in resources.json's orphan_sources)` lines are the same as the base commit's (four chunks of the four declared classes, none from `TestEndGroup`; the base run prints the same four) |

Flows 1 to 5 write nothing. Flows 7 to 10 run the repository's own runner in
scratch checkouts under `$S`; nothing is written into this repository.

## 8. Risks

* The helper runs a `SIGKILL` on a group id; it first checks the leader is
  alive (`_dead` is false for a live process, true for a zombie or a gone
  one), so a reused id would need a full pid wrap within the test's own
  milliseconds.
* The interrupt tests take about 0.5 s each on the passing path, unchanged by
  the cleanup; the 30 s appears only under M2 (the executor's wait), as
  section 5 uses it.

## 9. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
