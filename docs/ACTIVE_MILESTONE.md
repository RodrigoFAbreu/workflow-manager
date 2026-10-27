# Active Milestone

## Milestone

`chunk-gh-telemetry` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan
revision 2, base `184682b`, branch `milestone/chunk-gh-telemetry`): roadmap row 18. A
`test:` pull request title (tests and docs only; nothing is released). Plan:
`docs/ai-workflow/WORKFLOW_MANAGER_CHUNK_GH_TELEMETRY_PLAN.md`.

### CP1: quiet gh telemetry in the chunk environment -- complete

- `tests/parallel/isolation.py`: `chunk_env` sets `GH_TELEMETRY=false` and `DO_NOT_TRACK=1`
  with the other fixed settings, before `extra`, so an inherited value never wins and an
  explicit caller value may override.
- `tests/test_orphan_processes.py`: `TestChunkEnvGhTelemetry` (six tests, a stub `gh` that
  writes a marker instead of starting a process; five fail at `184682b`, the control that
  proves the stub detects the difference passes there by design).
- `tests/test_parallel_runner.py`: `test_the_chunk_environment_and_session` runs the real
  chunk process under hostile outer values and asserts the quiet ones.
- Checks: `--select test_orphan_processes.py` and `--select test_parallel_runner.py` green.

### CP2: architecture note and bookkeeping -- complete

- `docs/ARCHITECTURE.md`, "Verification execution": one bullet next to the Git discovery
  ceiling bullet says a chunk runs with `gh` telemetry off, why (the orphan check), and that
  an orphan exception is not the remedy.
- Checks: `--select test_docs.py` green.

## Functional review checklist

This item changes test infrastructure only: no product behaviour, no `src/`, no frozen
suite, no orphan exception. The check is that a test chunk runs with `gh` telemetry off,
whatever the outer environment holds, and that the tests prove it.

### Setup

- The clone at the checklist's evidence commit (`milestone/chunk-gh-telemetry`), Python 3
  and Git on `PATH`. Run from the clone root.
- Flows 1 to 4 need no network and no real `gh`: they use the test suite's stub `gh`
  and private chunk directories. The first run on a machine needs the network, or a
  `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror, to prime the release cache (`CLAUDE.md`).
- Use `--select` only. The full selection (`python3 tests/run_all.py`) is the acceptance
  gate, not a functional step.
- Flow 5 works in a scratch copy under `$TMPDIR`, never in the clone.
- Flow 6 needs a real `gh` and is manual only.

### Test data

None. Each test builds its own scratch directory, stub `gh` and environment.

### Flows and expected results

1. **Chunk environment, unit level.** Run
   `python3 tests/run_all.py --select 'test_orphan_processes.py::TestChunkEnvGhTelemetry'`.
   Expected: exit 0, 6 tests OK. This covers both variables set (`GH_TELEMETRY=false`,
   `DO_NOT_TRACK=1`), an inherited `true`/`0` overridden, an explicit caller value still
   winning, every other variable unchanged, and the stub `gh` staying quiet under the
   chunk environment (with its control sending when telemetry is not disabled).
2. **Chunk environment, real chunk process, hostile outer shell.** Run
   `GH_TELEMETRY=true DO_NOT_TRACK=0 python3 tests/run_all.py --select
   'test_parallel_runner.py::TestRunChunk::test_the_chunk_environment_and_session'`.
   Expected: exit 0. The chunk records `GH_TELEMETRY=false` and `DO_NOT_TRACK=1`.
3. **Architecture note.** Run `python3 tests/run_all.py --select test_docs.py`. Expected:
   exit 0. Read `docs/ARCHITECTURE.md`, "Verification execution", the bullet "A chunk runs
   with `gh` telemetry off": it states the variables, the reason (the orphan check), and
   that an orphan exception is not the remedy.
4. **Touched selections together.** Run `python3 tests/run_all.py --select
   test_orphan_processes.py --select test_parallel_runner.py --select test_docs.py`.
   Expected: exit 0, 358 tests. (At `dd7d5e7` this passed with 358 tests.)
5. **Regression proof (scratch copy).** `git clone` the clone into `$TMPDIR`. In that copy
   only, remove the two `GH_TELEMETRY` and `DO_NOT_TRACK` assignments from
   `isolation.chunk_env`, then run flow 1. Expected: the telemetry tests fail, except the
   control `test_the_stub_gh_sends_without_it`, which passes by design.
6. **Real `gh` (manual; the sandbox's `gh` is a stand-in and cannot run it).** With `gh`
   2.102.x on `PATH` and network sockets blocked (for example `unshare -rn`), a control run
   without the two variables leaves a detached `gh send-telemetry` process. A run with
   `GH_TELEMETRY=false DO_NOT_TRACK=1` leaves none.

### Known limitations and out of scope

- The CI symptom (`OrphanProcessError` on `gh send-telemetry`) is intermittent and does not
  reproduce locally, so flows 1 to 5 prove the mechanism, not the CI symptom. Acceptance
  needs a green CI run of the pull request, and that cannot be done from here.
- Full-selection evidence at the acceptance head is required; flows 1 to 4 are targeted
  runs and do not replace it.
- Unchanged by design: `orphan_sources`, anything under `src/`, the frozen Workflow
  suites, and every version. The `test:` pull request title releases nothing.
