# Active Milestone

## Milestone

`preflight-leftovers` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `f0f9095`, branch `milestone/preflight-leftovers`): roadmap row 33 (#151, items 1 and 4). A `test:` pull request title (releases nothing; one documentation sentence rides along).

The gate preflight's test and note say the whole truth. `test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` also asserts the next step the refusal names (`remove <cache>/0.0.1`). The Priming bullet of `docs/ARCHITECTURE.md` says `--results` moves the run directory only: frozen discovery still creates its release snapshot (`support.release()`) under the ambient `TMPDIR`, a filesystem the check does not then measure. No behaviour, printed text or exit code changes; no `src/` change; no Workflow change. Items 2 and 3 of the issue stay as they are.

### CP1: the pinned next step and the residual sentence -- complete

- Commit `800c152`: `tests/test_parallel_runner.py`, `docs/ARCHITECTURE.md`.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 33 (Current; Done at acceptance); this record.

### Failure-only mutations

Plan section 4, each on a fresh `git clone` of `800c152` (scratch copy), run as `python3 -B -m unittest test_parallel_runner.TestGatePreflight.test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` from `tests/`. The unmutated candidate passes (0.18 s).

| # | Mutation (`tests/parallel/priming.py`) | Candidate test | Base test file (`f0f9095`) |
| --- | --- | --- | --- |
| M1 | `remove {cache}/{version}` reworded to `delete ...` | fails: `remove <cache>/0.0.1` not found in the message | passes (the gap item 1 closes) |
| M2 | the step loses the version (`remove {cache}`) | fails at the same assertion | passes |

### Self-review

The diff against `f0f9095` was read against the plan: `tests/test_parallel_runner.py` (one assertion), `docs/ARCHITECTURE.md` (one sentence, no work-item id), plus the bookkeeping files; nothing under `src/` or `tools/`.
