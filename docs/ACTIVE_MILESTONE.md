# Active Milestone

## Milestone

`timings-rebalance` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `3917010`, branch `milestone/timings-rebalance`): roadmap row 34 (#181, second mechanism). A `test:` pull request title (releases nothing).

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

The diff against `3917010` was read against the plan: the data file was written by `parallel.timings` (never by hand), the two tests share one helper, the docstring sentence matches the plan's text and the Architecture paragraph deliberately deviates from it (below); nothing under `src/` or `tools/`. Self-review finding, fixed: the Architecture paragraph as the plan worded it said that downloading `results-*` folds the aggregate job's matrix classes and that the planner then lists no unit under `timing defaulted`; neither is true (see G2), so a refresher following it could never pass its final check. The paragraph now says the matrix host classes stay under `timing defaulted` with the `other_profile` estimate and why, and it still names every item plan flow 5 looks for. This rewords the plan's quoted paragraph; plan flow 7's "candidate: 0 defaulted" over-claims for the same reason (4, all phase B), and the functional checklist will say so. The full gate (`python3 tests/run_all.py`) passed at `1106a83` (exit 0, recorded in `TEST_RESULTS.md`). Implementation review round 1 (manual external, TR-EXT-001) found the `ci` profile's provenance over-claiming "every host class" and the `results-aggregate` artifact as a source; the provenance was rewritten through `parallel.timings.update(..., source=...)` with no observations, so no value or sample count moved, and now names the four unmeasured phase-B matrix host classes.

## Functional review checklist

Checklist for `timings-rebalance` (plan section 7, flows 1 to 10). Written against head `1fe04d4`, implementation revision 2, technical approval `CURRENT`. The automated gate (`python3 tests/run_all.py`, full selection, 2363/2363 units, 15952 tests, `selection_digest` ad23e64e…, `tree_digest` ae040024…) exited 0 on that head.

### Setup

Work in a scratch clone of the committed branch. Run as a non-root user. Write nothing into the product clone.

```
S=$(mktemp -d "$HOME/.cache/tr-fr.XXXXXX")
git clone --no-hardlinks /home/rodrigo/Workspace/workflow-manager "$S/cand"
cd "$S/cand"
```

Flows 1 to 6 run offline with `git`, `python3` and standard tools only (no `gh`, no network, no installs). Flows 7 to 10 need the primed release cache (`~/.cache/workflow-manager/releases`, or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror). Flows 7 to 10 are user-run.

Set `WORKFLOW_MANAGER_RELEASE_SOURCE=$HOME/.cache/workflow-manager/releases` for flows 7 to 10 when the network is unavailable. GitHub returned HTTP 504 for `v2.12.0` during two gate runs; the mirror let the same gate exit 0.

### Test data

Nothing to seed. The flows read committed files only, except flow 7, which uses the scratch planner script `~/.cache/tr-impl/predict.py` (not committed; it reads the clone it is given). The G3 scoring script `~/.cache/tr-impl/g3.py` is not a flow here.

### Flows

Flows 1 to 6 are offline; the Controller's functional tester may run them in its sandbox.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat 3917010d11dbfdaf958908ffa45d4347fece2877 HEAD -- src tools tests docs/ARCHITECTURE.md .github` | exactly `docs/ARCHITECTURE.md`, `tests/parallel/timings.json`, `tests/parallel/timings.py` and `tests/test_parallel_runner.py`; nothing under `src/`, `tools/` or `.github/`; `tests/parallel/config.json` is unchanged |
| 2 | `grep -n 'def test_the_committed_ci_timings_measure_almost_every_unit\|def test_the_committed_ci_model_packs_the_shards_evenly' tests/test_parallel_runner.py` | two matches, both inside `class TestTheRealCheckoutPlans` |
| 3 | `python3 -I ~/.cache/tr-fr-scripts/flow3.py "$S/cand" 3917010d11dbfdaf958908ffa45d4347fece2877` | `profiles.local`, `ci_job_setup_seconds` and `group_overhead_seconds.local` equal the base; `profiles.ci.source` names the three run ids, `median`, `6 shards` and `emptied`; last line `FLOW 3 PASS` (exit 0) |
| 4 | `grep -c '"frozen:[0-9]' tests/parallel/timings.json` | `0` |
| 5 | `grep -n 'oldest samples' tests/parallel/timings.py`; `tr '\n' ' ' < docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'A fold counts a unit.\{0,800\}'` | the docstring line names the emptied profile; the paragraph names `profiles.ci.units`, the three dispatches, `target_shard_seconds`, `results-*` and `timing defaulted` |
| 6 | `git diff 3917010d11dbfdaf958908ffa45d4347fece2877 HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|timings-rebalance'`; `python3 tools/check_docs.py` | `0`; `check_docs.py` exits 0 |
| 7 | `python3 -I ~/.cache/tr-impl/predict.py "$S/cand"`; the same on a clone of `3917010` | candidate: 2363 units, **4 defaulted** (all `other_profile`, the four phase-B matrix host classes), `orphaned []`, `warnings []`, shard-wall max/min at most 1.02 (observed 1.0001). Base: 386 defaulted |
| 8 | Mutations in fresh copies of `$S/cand` (`cp -rf "$S/cand" "$S/mutN"`), then from `tests/`: `python3 -B -m unittest test_parallel_runner.TestTheRealCheckoutPlans.<name>` for T1 `test_the_committed_ci_timings_measure_almost_every_unit` and T2 `test_the_committed_ci_model_packs_the_shards_evenly` | see the mutation table below |
| 9 | `cd "$S/cand/tests" && python3 -B -m unittest test_parallel_runner.TestTheRealCheckoutPlans` | exit 0 |
| 10 | `cd "$S/cand" && python3 tests/run_all.py --select test_parallel_runner.py`, then `--select test_docs.py` | exit 0 each; no `OrphanProcessError` |

Flow 7 correction: the plan text says "candidate: 0 defaulted". The plan's own G2 rule allows up to 10 defaulted units, each named with its cause. The four units are named above and are the phase-B matrix host classes, so the correct expected value is 4, not 0. The self-review already recorded this over-claim.

Flow 8 mutations (apply in a fresh copy of `$S/cand`, then run T1 and T2):

| # | Mutation (in the copy) | T1 | T2 |
| --- | --- | --- | --- |
| M1 | `git -C "$S/cand" show 3917010d11dbfdaf958908ffa45d4347fece2877:tests/parallel/timings.json > tests/parallel/timings.json` | fails: 386 of 2363 units unmeasured | passes |
| M2 | `python3 -I -c` edit: set `profiles.ci.units['frozen:conformance/workflow_state_test.py::TestGlobalLockOrderItem372h']['seconds']` to `20000` | passes | fails |
| M3 | `python3 -I -c` edit: delete every `ci` unit key that starts with `frozen:updated/` (514 keys) | fails: 518 of 2363 units unmeasured | passes |

The unmutated copy passes both T1 and T2.

### Known limitations and out of scope

- The real CI effect is not measured or claimed here. The post-merge measurement (H4) is outside this item's acceptance.
- The four phase-B matrix host classes keep their `other_profile` estimate by design. They appear under `timing defaulted`, as flow 7 and the Architecture paragraph say.
- G1 and G3 rest on the three CI runs (42551845166, 42553923351, 42556118176) and their artifacts. Those artifacts are not in this repository. The independent review could not replay the raw CI artifacts and relied on the submitted evidence. G3 is a model check at the old chunk granularity, not a prediction of the new wall. The H3b control artifacts expire after 90 days.
- Flows 7 and 8 depend on scratch tools outside the repository. Flow 8's numbers depend on the release cache.
- `test_operator_ux_report.py::TestStatusContainment::test_an_unmanaged_target_with_a_cache_inside_git_is_the_known_gap` fetches a release from GitHub because its cache path is empty. It is unchanged since `3917010`, outside this item's scope, and passes when the release comes from a mirror. Without network or a mirror the full gate fails on that one test.

### Reporting findings

Put findings in `.ai-review/timings-rebalance/feedback/FUNCTIONAL_REVIEW.md`. `/apply-functional-review` routes each one: a bounded fix stays in this item, and anything wider becomes a remediation child.

### After testing

Once testing is clean, `/accept-milestone` is the only acceptance command. Both checkpoints (CP1, CP2) are `COMPLETE`, so the registry is terminal. Roadmap row 34 is marked Done at acceptance.
