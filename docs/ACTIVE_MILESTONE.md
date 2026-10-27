# Active Milestone

## Milestone

`runner-hardening` -- implementation complete and technically approved by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 1, implementation revision 1, base `f0ea500`, branch `milestone/runner-hardening`): roadmap row 16. A `test:` pull request title (tests and docs only; nothing is released). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RUNNER_HARDENING_PLAN.md`.

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

- `docs/ROADMAP.md`: row 16 marked In progress. It becomes Done at acceptance.

## Current checkpoint

None: CP1 and CP2 are complete. The item is at `AWAITING_FUNCTIONAL_REVIEW`.

## Functional review checklist

Scope: the runner's handling of `SIGINT` and of a failed cleanup after the report. A `test:` change: the verdict, the barrier, the lock and the leak check are unchanged.

### Setup (offline; the sandbox limits apply)

Work only in a scratch checkout. Never run the gate or any flow in the product clone: a run makes `src/` and `tools/` read-only and writes `.git/wm-verify/barrier.json` while it runs.

```bash
OUT=$(mktemp -d)                       # the output folder; everything below stays in it
export HOME=$OUT/home XDG_CACHE_HOME=$OUT/cache XDG_CONFIG_HOME=$OUT/config TMPDIR=$OUT/tmp
mkdir -p "$HOME" "$XDG_CACHE_HOME/workflow-manager" "$XDG_CONFIG_HOME" "$TMPDIR"
cp -a ~/.cache/workflow-manager/releases "$XDG_CACHE_HOME/workflow-manager/"   # the primed release cache
git clone -q --branch milestone/runner-hardening /home/rodrigo/Workspace/workflow-manager "$OUT/checkout"
cd "$OUT/checkout"
git diff --stat b78d19b HEAD -- src tools tests   # must print nothing
find src tools -printf '%m %p\n' | sort > "$OUT/modes-before.txt"
```

- The release cache is primed before every run and the sandbox has no network. Without the copied cache (or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror) the run stops at priming with exit 2 (`PrimingError`). That is an environment limit, not a defect.
- No flow needs `gh`, `claude`, `codex`, `ssh`, a network or a forge. A frozen unit that reaches the sandbox's `gh` stand-in is `environment`, not a product `defect`.
- Nothing is pushed or committed by any flow.

### Test data

None. The runner builds its own scratch checkouts and fixtures.

### Flows

**F1. `SIGINT` to a run started with it ignored (the first defect).** In `$OUT/checkout`:

```bash
PYTHONUNBUFFERED=1 sh -c 'trap "" INT; exec python3 tests/run_all.py --select test_parallel_runner.py' \
  > "$OUT/f1.out" 2> "$OUT/f1.err" &
RUN=$!
until ls -d "$TMPDIR"/wm-run-* >/dev/null 2>&1; do sleep 1; done
sleep 15                               # let the chunks start
ps --ppid "$RUN" -o pid,args           # expect at least one child (the chunk)
kill -INT "$RUN"; wait "$RUN"; echo "exit $?"
```

Expected: exit `2`. `$OUT/f1.err` names `InterruptedRunError` (the run was interrupted). `diff <(find src tools -printf '%m %p\n' | sort) "$OUT/modes-before.txt"` prints nothing. `.git/wm-verify/barrier.json` does not exist. No process still has `$TMPDIR` in its command line: `ps -eo pid,args | grep -F "$TMPDIR" | grep -v grep` prints nothing. Before the change, the same run finished with exit 0 once its chunk was released.

If `ps --ppid` shows no child, the signal arrived before any chunk started: that proves less, so repeat with a longer sleep.

**F2. `SIGTERM` control.** Same as F1 with `kill -TERM "$RUN"` instead of `kill -INT`. Expected: exit `2`, the same four checks. `SIGTERM` already behaved this way before the change.

**F3. Ordinary run, no signal (control).**

```bash
python3 tests/run_all.py --select test_docs.py > "$OUT/f3.out" 2> "$OUT/f3.err"; echo "exit $?"
```

Expected: exit `0`; the last line of `$OUT/f3.out` is `verdict: exit 0`; `$OUT/f3.err` has no `warning:` line; `ls -d "$TMPDIR"/wm-run-*` finds nothing (the run's own directory is removed as before).

**F4. A failed removal of the run directory after the report (the second defect).** The real `OSError` needs root or a mount, so the failure is injected in-process: the same `cli.main` as the real run, with `shutil.rmtree` raising only for a directory whose own name starts with `wm-run-` (a chunk's private `TMPDIR` is nested under the run directory and has a different name, so the chunks are untouched).

```bash
cat > "$OUT/inject.py" <<'EOF'
import pathlib, runpy, shutil, sys
real = shutil.rmtree
def rmtree(path, *args, **kwargs):
    if pathlib.Path(str(path)).name.startswith("wm-run-"):
        raise OSError(16, "injected: device or resource busy")
    return real(path, *args, **kwargs)
shutil.rmtree = rmtree
sys.argv = ["tests/run_all.py", "--select", "test_docs.py"]
runpy.run_path("tests/run_all.py", run_name="__main__")
EOF
python3 "$OUT/inject.py" > "$OUT/f4.out" 2> "$OUT/f4.err"; echo "exit $?"
```

Expected: exit `0`. The last line of `$OUT/f4.out` is `verdict: exit 0`. `$OUT/f4.err` has one line `warning: could not remove the run directory <path>: injected: device or resource busy; the verdict is unchanged`, naming a `wm-run-*` directory, and no `error[` line and no traceback. `ls -d "$TMPDIR"/wm-run-*` shows that directory still there. Before the change, the same run printed `verdict: exit 0`, then `run_all: error[OSError]` with a traceback, and exited 2.

If `$OUT/f4.err` has no warning line, the injection did not reach the process that removes the directory. That is an environment fault in the flow, not a product defect; the in-process test in the suite is the evidence for this case.

### Expected results at a glance

| Flow | Expected exit | Expected evidence |
| --- | --- | --- |
| F1 `SIGINT`, ignored at start | 2 | `InterruptedRunError`; modes unchanged; no `barrier.json`; no child left |
| F2 `SIGTERM` control | 2 | as F1 |
| F3 ordinary run | 0 | `verdict: exit 0`; no warning; no `wm-run-*` left |
| F4 removal fails after the report | 0 | `verdict: exit 0`; one stderr warning naming the kept directory; no `error[` |

### Known limitations (not defects of this milestone)

- A removal that fails partway can leave the run directory partly removed (`shutil.rmtree` may stop midway). The warning names the path; the directory is never retried.
- The `SIGINT` handler is shared by `--run-shard` and `--aggregate`, and the new handling reaches them. Only the unit test covers them, not a flow. The post-report warning applies to the local run only, by design.
- A failing run (exit 1) keeps its directory. The suite covers this; no flow here produces a failing run.
- A chunk no longer inherits an ignored `SIGINT` from the run. Chunks are in their own session, so a terminal Ctrl-C never reached them either way.
- The fork-to-exec interrupt window is out of scope (dropped, plan section 4).
- Review-stage Optional findings (for example, the chunk-group kill on the failing-test path, a test-only cleanup) are dispositioned at acceptance, not here.

### Next steps

1. Run F1 to F4 and record each exit code and the evidence line in the functional review file below.
2. Findings go to `.ai-review/runner-hardening/feedback/FUNCTIONAL_REVIEW.md`. `/apply-functional-review` routes each one: a bounded fix in this item, or a `runner-hardening-remediation-<n>` child item for wider scope.
3. Once testing is clean, `/accept-milestone` is the only acceptance command. It needs every checkpoint `COMPLETE` (CP1 and CP2 are). There is no command that records acceptance of a partial round.
