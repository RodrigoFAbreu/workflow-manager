# Active Milestone

## Milestone

`gate-preflight` -- implementation in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `2be4b4b`, branch `milestone/gate-preflight`): roadmap row 25 (#150, #125). A `fix:` pull request title (releases a Manager patch; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_GATE_PREFLIGHT_PLAN.md`.

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
| `unserved` (key and read-back loop) removed from the script's report | `test_the_real_script_reports_what_the_cache_serves` |

One mutation outside the plan's table survives: the script's read-back loop removed while the `unserved: []` key stays. A cache that primes but does not serve cannot be built hermetically against the real script, so the loop is covered by the fake-report case and by review only.

### Self-review

- `nested_in_checked_run` let `OverflowError` out for a marker too large for a pid (`WM_GATE_PREFLIGHT=99999999999999999999`): the run stopped with `run_all: error[OverflowError]` instead of being checked, as a malformed marker must be. It is now caught with the other malformed values, and `test_a_missing_dead_or_malformed_marker_is_checked` covers that value (red on the unfixed code in a scratch clone: `error[OverflowError]`; green after).
- The full gate at `0d39624` exited 1: `TestTestTreeHygiene.test_every_lock_reaching_call_in_this_module_is_rooted_at_a_scratch_checkout` named `cli.main` (through `main_in_process`) and `acquire_run_lock` as not rooted at a scratch checkout, because `TestGatePreflight` kept its scratch in `self.scratch`, a form the scan does not follow. Each test now binds `scratch = scratch_checkout(...)` itself and the patched run is the top-level `refused_in_process(scratch_root, ...)`; the assertions are unchanged. The scan reports nothing, and both classes pass.
- The mutation table above, rerun against the restructured tests (scratch clone of `0d39624` plus the new test file, `test_parallel_runner.TestGatePreflight` run directly; the candidate passes 12 of 12): every mutation fails the case named, as before. The moved check (placed after `prime` for every mode) also fails the scope case. One more mutation, `OverflowError` no longer caught, fails `test_a_missing_dead_or_malformed_marker_is_checked`.
- No other finding: the check runs before priming for the three unit-starting modes only, measures the directory `make_run_dir` uses in each, creates nothing, and the read-back is shared by `tools/release/package.py` and `tools/release/release.py`, which already turn `PrimingError` into their own refusal.

## Next action

Self-review, the full `python3 tests/run_all.py`, then the implementation-review bundle.
