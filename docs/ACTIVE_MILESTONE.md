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
