# Active Milestone

## Milestone

`runner-test-cleanup` -- implemented, awaiting implementation review (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `c041050`, branch `milestone/runner-test-cleanup`): roadmap row 32 (#119, items 1 to 4). A `test:` pull request title (releases nothing).

The runner-hardening tests and notes say exactly what they check. The interrupt test's cleanup also ends the chunk's process group (`_end_group`, covered by `TestEndGroup`) before it writes the stop file, so a failing run no longer leaves the chunk to `WAIT_MODULE`'s 120-second deadline. `test_a_failing_run_keeps_its_directory_and_attempts_no_removal` asserts the directory the verdict line names exists and holds `results.json`. `remove_run_dir`'s docstring says the directory may be left behind. `docs/ARCHITECTURE.md` says the signal handler covers all three modes through `_install_signal_handlers`. No behaviour, printed text or exit code of the runner changes; no `src/` change; no Workflow change.

### CP1: the interrupt cleanup, the kept-directory assertion and the two wordings -- complete

- Commit `472d138`: `tests/test_parallel_runner.py`, `tests/parallel/executor.py` (docstring lines only), `docs/ARCHITECTURE.md`.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 32 (Current; Done at acceptance); this record.

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
