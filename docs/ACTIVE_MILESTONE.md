# Active Milestone

## Milestone

`timings-rebalance` -- in implementation (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `3917010`, branch `milestone/timings-rebalance`): roadmap row 34 (#181, second mechanism). A `test:` pull request title (releases nothing).

The CI timing model is re-derived so the six shards balance. `tests/parallel/timings.json`'s `ci` profile was folded from three one-class-per-chunk CI dispatches (runs 42551845166, 42553923351, 42556118176, branch `ci/timings-measurement`) into an emptied profile; two pins in `TestTheRealCheckoutPlans` keep the committed model measured (at most a tenth of the units unmeasured) and even (predicted shard walls within 10 %); `timings.update`'s docstring and `docs/ARCHITECTURE.md` say how to refresh. No planner change, no `src/` change, `ci_max_shards` stays 6. The real CI effect is measured after the merge (H4) and is not claimed here.

### CP1: the refreshed model and its pins -- complete

- Commit `5c88ede`: `tests/parallel/timings.json`, `tests/test_parallel_runner.py`, `tests/parallel/timings.py`, `docs/ARCHITECTURE.md`.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 34 (Current; Done at acceptance); this record.

### Acceptance rules for the data (plan section 4), on a clean clone of `5c88ede`

| Rule | Result |
| --- | --- |
| G1 | The three dispatches exited 0. Each `meas-<n>` holds 2359 phase-A records (one per selected non-matrix unit) and a `results-aggregate` run directory (the four matrix host classes). |
| G2 | 2363 units, 4 defaulted, all `other_profile` (the plan allows up to 10, each named with its cause): the four phase-B matrix host classes (`test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite`, `test_conformance_suite.py::TestBootstrappedTarget`, `test_conformance_suite.py::TestConformanceFixture`, `test_update_path.py::TestUpdatedRepositorySatisfiesTheFrozenSuite`). Cause: the aggregate job writes no `timings.jsonl` and the fold reads only `*.jsonl` and `*.record.json`, not the host `records/*.json` the `results-aggregate` artifact holds, so downloading it does not fold them. They run in the aggregate job's phase B, so their estimate never enters a shard's packing. `orphaned` empty, no warnings. Predicted shard walls at 4 workers 836 s on every shard, max/min 1.0001 (limit 1.02). |
| G3 | Against the three real runs of section 1, 410 chunks re-priced: correlation 0.970 (base 0.911, control re-run 0.911); slowest/mean after an LPT re-pack 1.044 (limit 1.10; base 1.091). The model's total now sits at 0.89 of the measured chunk time (base 1.49). This is a model check at the old chunk granularity, not a prediction of the new wall. |
| G4 | Against `3917010:tests/parallel/timings.json`: the `local` profile, `ci_job_setup_seconds` and the `local` group overheads are equal. |

### Failure-only mutations (plan section 5)

Each on a fresh copy of the clone of `5c88ede`, T1 `test_the_committed_ci_timings_measure_almost_every_unit`, T2 `test_the_committed_ci_model_packs_the_shards_evenly`, run from `tests/` with `python3 -B -m unittest`. The unmutated copy passes both.

| # | Mutation | T1 | T2 |
| --- | --- | --- | --- |
| M1 | the base `timings.json` (stale model) | fails: 386 of 2363 units unmeasured | passes |
| M2 | one class set to 20000 s | passes | fails: walls `[20001, 1006, 1006, 1006, 1006, 1006]` |
| M3 | every `frozen:updated/` entry of `ci` dropped | fails: 518 of 2363 units unmeasured | passes |

### Self-review

The diff against `3917010` was read against the plan: the data file was written by `parallel.timings` (never by hand), the two tests share one helper, the docstring sentence and the Architecture paragraph match the plan's text; nothing under `src/` or `tools/`. Self-review finding, fixed: the Architecture paragraph as the plan worded it said that downloading `results-*` folds the aggregate job's matrix classes and that the planner then lists no unit under `timing defaulted`; neither is true (see G2), so a refresher following it could never pass its final check. The paragraph now says the matrix host classes stay under `timing defaulted` with the `other_profile` estimate and why, and it still names every item plan flow 5 looks for. This rewords the plan's quoted paragraph; plan flow 7's "candidate: 0 defaulted" over-claims for the same reason (4, all phase B), and the functional checklist will say so. Not run yet: the gate (`python3 tests/run_all.py`) and the narrow `--select` runs at the implementation-review step.
