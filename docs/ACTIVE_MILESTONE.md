# Active Milestone

## Milestone

`gate-preflight` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 3, implementation revision 2, base `2be4b4b`, candidate code head `23c6214`, branch `milestone/gate-preflight`): roadmap row 25 (#150, #125). A `fix:` pull request title (releases a Manager patch; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_GATE_PREFLIGHT_PLAN.md`.

A gate run that cannot succeed stops at its start with a refusal that names the cause, before any unit starts: (1) after priming, every tested version is read back from the release cache, and one the cache does not serve is a `PrimingError` naming the version, the cache and one next step; (2) a run that starts units checks the free space of the filesystem its run directory is created on (`--results` when given, else the effective `TMPDIR`) against 4 GiB and refuses with the path and the numbers (`TmpSpaceError`, exit 2). A nested run under a live outer run does not check again. No Workflow change, no change to the matrix, the shards or the pins.

### CP1: the preflight, its tests and the page -- complete

- `tests/parallel/priming.py` (`MIN_FREE_RUN_BYTES`, `TmpSpaceError`, `check_free_space`, `nested_in_checked_run`, the read-back in the script and in `prime`, the marker in `exported`), `tests/parallel/cli.py` (`_check_run_space` before priming), `tests/test_parallel_runner.py` (`TestGatePreflight`, 12 cases) and `docs/ARCHITECTURE.md` (commit `d19c69b`).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 25 is Current; the acceptance step makes it Done.

### Mutation results (scratch clone of `d19c69b` outside the repository, `test_parallel_runner.TestGatePreflight` run directly: the candidate passes 12 of 12; `python3 tests/run_all.py --select test_parallel_runner.py::TestGatePreflight` exits 0)

Each mutation exits 1 and fails the case the plan names (extra failures listed):

| Mutation | Failed |
| --- | --- |
| the `check_free_space` call removed from `cli._main` | `test_a_refused_run_stops_before_it_writes_or_fetches_anything`, plus three more cases that expect the check |
| the call moved after `priming.prime` | `test_a_refused_run_stops_before_it_writes_or_fetches_anything` |
| the call also for `--list` and `--plan-only` | `test_modes_that_start_no_unit_are_not_refused_for_space` |
| always `tempfile.gettempdir()`, `--results` ignored | `test_results_not_tmpdir_is_the_directory_checked`, `test_the_path_checked_follows_the_run_directory` |
| a nested run checks again | `test_a_nested_run_under_a_live_marker_is_not_checked_again` |
| the marker honoured without the liveness test | `test_a_missing_dead_or_malformed_marker_is_checked` |
| `exported` no longer sets the marker | `test_exported_sets_and_restores_the_marker` |
| `free < minimum` to `free <= minimum` | `test_free_equal_to_the_minimum_passes` |
| `MIN_FREE_RUN_BYTES` changed | `test_the_minimum_is_pinned` |
| the `unserved` raise removed from `prime` | `test_a_version_the_cache_does_not_serve_is_a_priming_error` |
| `unserved` key removed from the script's report | `test_the_real_script_reports_what_the_cache_serves` |
| the script's read-back loop removed, `unserved: []` kept (LIR1-001) | `test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` |
| an `OSError` from the measurement escapes (LIR1 optional) | `test_an_unmeasurable_path_is_a_refusal_that_names_it` |

No mutation survives. The read-back loop is pinned by driving the real script against a scratch whose `ReleaseCache.cached_manifest` returns `None` (LIR1-001); a first version of this note said that case could not be built hermetically, which was wrong.

### Self-review

- `nested_in_checked_run` let `OverflowError` out for a marker too large for a pid (`WM_GATE_PREFLIGHT=99999999999999999999`): the run stopped with `run_all: error[OverflowError]` instead of being checked, as a malformed marker must be. It is now caught with the other malformed values, and `test_a_missing_dead_or_malformed_marker_is_checked` covers that value (red on the unfixed code in a scratch clone: `error[OverflowError]`; green after).
- The full gate at `0d39624` exited 1: `TestTestTreeHygiene.test_every_lock_reaching_call_in_this_module_is_rooted_at_a_scratch_checkout` named `cli.main` (through `main_in_process`) and `acquire_run_lock` as not rooted at a scratch checkout, because `TestGatePreflight` kept its scratch in `self.scratch`, a form the scan does not follow. Each test now binds `scratch = scratch_checkout(...)` itself and the patched run is the top-level `refused_in_process(scratch_root, ...)`; the assertions are unchanged. The scan reports nothing, and both classes pass.
- The mutation table above, rerun against the restructured tests (scratch clone of `0d39624` plus the new test file, `test_parallel_runner.TestGatePreflight` run directly; the candidate passes 12 of 12): every mutation fails the case named, as before. The moved check (placed after `prime` for every mode) also fails the scope case. One more mutation, `OverflowError` no longer caught, fails `test_a_missing_dead_or_malformed_marker_is_checked`.
- No other finding: the check runs before priming for the three unit-starting modes only, measures the directory `make_run_dir` uses in each, creates nothing, and the read-back is shared by `tools/release/package.py` and `tools/release/release.py`, which already turn `PrimingError` into their own refusal.

### Full gate

`python3 tests/run_all.py` at `80f8ead` (code head `23c6214`; `2eb537b` and `23c6214` are the last code changes, and `git diff 80f8ead HEAD` touches only `docs/ai-workflow/WORKFLOW_STATE.json`): full selection, 8 workers, 2329/2329 units, 15537 tests, `selection_digest e44f83c5...`, `tests_digest bdd149bc...`, orphan check on (9 tolerated, all declared), `verdict: exit 0`. This is the current evidence (`.ai-review/gate-preflight/current/TEST_RESULTS.md`, revision 2). It supersedes the run at `b8dd8a9` (15535 tests), which predates `2eb537b`. The first full run, at `0d39624`, exited 1 on the hygiene scan (see the self-review).

## Functional review checklist

Candidate: code head `23c6214` against base `2be4b4b`. Flows 1 to 7 run offline in the sandbox described under Setup; flow 8 does not.

### Setup

- Limits: no network; `gh`, `claude`, `codex` and `ssh` are stand-ins that refuse and log; `PATH` is the sandbox's `bin/` plus the system directories, which must include `python3` and `git`; the product clone is read-only. Every write goes under one scratch directory `$S` on a writable location.
- `S=$(mktemp -d "<writable location>/gp-fr.XXXXXX")`, then `mkdir -p $S/base $S/cand $S/cache`, `git archive 2be4b4b tests | tar -x -C $S/base`, `git archive 23c6214 tests | tar -x -C $S/cand`. `$S/cache` stays empty throughout.
- The harness `$S/h.py` (one line): `import sys;sys.path.insert(0,sys.argv[1]+"/tests");from parallel import priming;exec(sys.argv[2])`. Run every function flow from `cd $S`, never from the product clone, because flow 4 passes `Path(".")`.
- The CLI flows (6 and 7) run in a scratch clone: `git clone -q --no-hardlinks <product clone> $S/cli && git -C $S/cli checkout -q 23c6214`. They need a writable location with less than 4 GiB free, given as `$S/small`. The sandbox's small tmpfs will do; otherwise `unshare -rm` mounts a 16 MiB one (needs unprivileged user namespaces).

### Test data

None to seed. The inputs are the fixed paths and sizes written into each flow, and fake `subprocess.run` results in flows 4 and 5, so no release is fetched.

### Flows

Function flows, `python3 -I $S/h.py $S/<base|cand> '<code>'`. Run each against `base` and `cand`.

1. Refusal names the path, the numbers and `TMPDIR`:
   `'from pathlib import Path;priming.check_free_space(Path("/x/tmp"),minimum=1000,free=999)'`
   then the same with `,lever="--results"` before the closing `)`.
2. Boundary passes:
   `'from pathlib import Path;priming.check_free_space(Path("/x/tmp"),minimum=1000,free=1000);print("ok");priming.check_free_space(Path("/x/tmp"),minimum=1000,free=2000);print("ok")'`
3. Constants:
   `'print(priming.MIN_FREE_RUN_BYTES==4*1024**3, issubclass(priming.TmpSpaceError,priming.PrimingError))'`
4. A version the cache does not serve is refused. Run with `CACHE="$S/cache"` in the environment:
   `'import json,os,types;priming.subprocess.run=lambda *a,**k:types.SimpleNamespace(returncode=0,stderr="",stdout=json.dumps({"cache":os.environ["CACHE"],"source":"s","versions":["7.0.0"],"unserved":["7.0.0"]}));from pathlib import Path;print(priming.prime(Path(".")))'`
5. A served version passes, with the same fake and `"unserved":[]` in place of `["7.0.0"]`. Print the result, e.g. `;print(priming.prime(Path(".")))`.

CLI flows, run in `$S/cli`, after `cd $S/cli`:

6. A real run refuses before anything is primed, with `--results` as the lever:
   `mkdir -p $S/small && unshare -rm sh -c "mount -t tmpfs -o size=16m tmpfs $S/small && python3 tests/run_all.py --select test_parallel_runner.py::TestGatePreflight --results $S/small/res; echo EXIT=\$?; ls -A $S/small"`
7. The same with `TMPDIR` as the lever:
   `unshare -rm sh -c "mount -t tmpfs -o size=16m tmpfs $S/small && TMPDIR=$S/small python3 tests/run_all.py --select test_parallel_runner.py::TestGatePreflight; echo EXIT=\$?; ls -A $S/small"`

Flow 8 is not run in the sandbox: `python3 tests/run_all.py --select test_parallel_runner.py::TestGatePreflight` in a clone at `23c6214`, with network or a primed release cache. Expect exit 0 and all 12 cases passing. The full gate at `80f8ead` already covers this class.

### Expected results

- 1, candidate: `TmpSpaceError` text naming `/x/tmp`, `999` and `1000`, and `TMPDIR`. The second names `--results` and not `TMPDIR`. Base: `AttributeError` (no check).
- 2, candidate: `ok` twice, nothing raised. Base: `AttributeError`.
- 3, candidate: `True True`. Base: `AttributeError`.
- 4, candidate: `PrimingError` naming `7.0.0`, the cache directory and `s`, and telling the operator to remove `<cache>/7.0.0` and run again. Base: returns the report with no error. `$S/cache` is still empty.
- 5, candidate and base: return the report, no error. `$S/cache` is still empty.
- 6, exit 2. stderr is one line `run_all: error[TmpSpaceError]: <path>/res has ... bytes ... free, and a run needs at least 4294967296 bytes (4.0 GiB) there: set --results ...`. The `ls` after `EXIT=2` prints nothing. The product clone is unchanged.
- 7, exit 2. The same error, but the message says `set TMPDIR` and names `$S/small`. Nothing in `$S/small`.

### Known limitations and out of scope

- The check measures free space once, at the start of a run that starts units. It does not guard the release cache's filesystem (plan section 7), and it does not catch a run that fills the disk later.
- `--list` and `--plan-only` are not refused for space (by design). Both still prime, so they need network or a cache and are not sandbox flows.
- `WM_GATE_PREFLIGHT=<live pid>` skips the check, by design, for a nested run (plan section 7). No flow here sets it.
- The remediation in flow 4 (remove `<cache>/<version>` and run again) is safe only while no other run uses that cache. This is optional finding `F-aa6a070750c2` (LPR1-003), to be dispositioned at acceptance.
- No Workflow change, no change to the matrix, shards or pins.

## Next action

The user performs the functional review: run flows 1 to 7 at the checklist commit and place any findings at `.ai-review/gate-preflight/feedback/FUNCTIONAL_REVIEW.md`. Flow 8 is run by the user with network. Acceptance (`/accept-milestone`) follows only a clean functional review; both checkpoints (CP1, CP2) are already `COMPLETE`.
