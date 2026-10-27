# Active Milestone

## Milestone

`chunk-gh-telemetry` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan
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

## Current checkpoint

None: the milestone is complete (CP1 and CP2 complete, `MILESTONE_COMPLETE`).

## Functional review

Seven flows (flow-1 to flow-6 and flow-x1) passed at `3232e7e`, run by an independent
executor; flow 6 used the real `gh` 2.102.1 under blocked network sockets. Acceptance was
by policy from that evidence and the Workflow's own query of PR #118. The 5 Optional
findings are dispositioned in `docs/milestones/completed/chunk-gh-telemetry-findings.md`.

### Known limitations

- The CI symptom (`OrphanProcessError` on `gh send-telemetry`) is intermittent and does not
  reproduce locally, so the flows prove the mechanism, not the CI symptom.
- Unchanged by design: `orphan_sources`, anything under `src/`, the frozen Workflow
  suites, and every version. The `test:` pull request title releases nothing.
