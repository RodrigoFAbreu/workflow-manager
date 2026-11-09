# Workflow Manager: Re-derive the CI Timing Model so the Six Shards Balance (Revision 4)

`work_item_id: timings-rebalance` -- `governing_workflow_version: "2.2"`

**Deliverable:** `tests/parallel/timings.json` re-derived from real
one-class-per-chunk CI runs, two pins that keep the committed model from
going stale or lopsided unnoticed, and the refresh procedure written where it
is used (roadmap row 34, issue #181, second mechanism).

**Work item type:** `process`. **Base commit:** `3917010`
(`3917010d11dbfdaf958908ffa45d4347fece2877`, tip of `main`, Manager 1.14.8;
Workflow 2.29.1 installed, automatic gates). **Branch:**
`milestone/timings-rebalance`. **Scope source:** the owner's order of
2026-11-09 and the comments of #181 (the first mechanism, a per-chunk bytecode
cache, was withdrawn: A -13 %, B about -8 % of CPU). Owner constraints:
`ci_max_shards` stays 6, no conformance-job sharding, no new jobs or runners,
and what a pull request tests does not change. The pull-request title is a
`test:` change and **releases nothing**; check it with
`python3 tools/release/release.py check-title "test: ..."`. One mechanism: the
planner's cost model is re-derived from measurement. Two checkpoints, four
deliverable files, nothing under `src/`.

## 1. Investigation (done at `3917010`, before any design)

**What the planner predicts.** `python3 tests/run_all.py --plan-only --profile
ci` on `main`: 6 shards, 410 phase-A chunks (303 host, 107 frozen), 2363 units
(2056 frozen), every shard load 1993.8 s (spread 1.000), predicted shard wall
at 4 workers 498-499 s. LPT balances any model perfectly, so the predicted
spread says nothing about the model's error.

**What CI took.** The last three full runs that used this plan (same 410
chunk ids, same assignment): `gh run view --json jobs`.

| run | shard job seconds, shards 0 to 5 | max/min |
| --- | --- | --- |
| 42434510363 (push) | 630, 742, 972, 1029, 817, 615 | 1.67 |
| 42447145326 (pull request) | 1008, 630, 1000, 828, 771, 682 | 1.60 |
| 42448347885 (push) | 706, 851, 697, 802, 807, 716 | 1.22 |

**Where the error is** (the `results-shard-*` artifacts of the same three
runs, per-chunk start/end):

* Actual chunk time sums to 17,762 / 19,116 / 18,621 s against the plan's
  11,963 s (1.48 to 1.60x). Per chunk, estimate and the three-run mean
  correlate at 0.91, but the acceptance-matrix chunks are priced at about
  112 s and ran 255 to 326 s.
* **386 of the 2363 units have no measured CI time** (the earlier count): 329
  take the median of their group (all 79 classes of each of the four 2.29.1
  fixtures, added since the 2026-10-11 measurement), 53 take the 30 s default (host
  classes of `test_discovery`, `test_release_metadata`, `test_retention_status`,
  `test_tested_releases`), 4 take the local profile scaled. The committed CI
  numbers are from run 38140982424 (2026-10-11, Workflow 2.9.1 classes).
* A chunk repeats within a median 12 % (coefficient of variation, 117 chunks
  over 20 s, three runs): the error is mostly systematic, not noise.
* The per-shard three-run mean of actual chunk time is 3058, 2892, 3479,
  3351, 3111, 2608 s: slowest/mean **1.128**, slowest/smallest 1.334. A
  perfect model would shorten the slowest shard by at most 1 - 1/1.128 = 11 %
  (about 1.6 to 1.9 minutes of the 851 to 1029 s shard jobs). A leave-one-run-out
  re-pack of the real chunk times shows 9 to 17 %, which is inflated: it
  moves one run's slow-runner time to other shards. Use 11 % as the ceiling.
* On top of that, the same chunks on the same shard took 1.6x longer in one
  run (shard 0: 2462, 2756, 3957 s). That is runner-speed variance; no packing
  removes it.

**The planner is not at fault.** LPT is exact on its input; the largest
chunk (326 s) is well below a shard's wall, so the sum-based packing is not
the limit; the fallbacks (group median, default) are the cause of the
mispriced chunks. No change under `tests/parallel/planner.py` is supported by
the evidence.

**How a fold behaves** (checked in a scratch clone): `timings.update` counts a
unit's stored estimate as the oldest samples of the median. Folding one real
run into the committed file changed 246 units and averaged each with its old
value (`TestContainmentFailsClosed` 13.3 s -> 40.1 s, samples 1 -> 2). A
refresh of numbers that are stale by many releases must therefore fold into a
profile emptied first (the Oct 2026 refresh did, by replacing the file), and
use several runs so one runner's speed does not set a class's number.

**Decision.** A refresh is worth doing, modestly: the ceiling is about 11 % of
the slowest shard (not the 17-19 minute wall as a whole), likely less
after runner variance, at the cost of three CI runs and one data file, with no
code under `src/`, nothing to invalidate and no change to what a PR proves. It
is also the repair of a model that has rotted (16 % of units unpriced). It is
abandoned, with the evidence recorded, if the offline checks of section 4
do not show the new model better than the old.

**Not measured:** the CI wall after the refresh (needs the merged file; it is
outside this item's acceptance, see H4); why a runner is 1.6x
slower on some runs; the local profile (equally stale, not the CI goal, left
untouched); whether three measurement runs are enough (chosen from the 12 %
chunk variation, not from a power calculation).

## 2. Design

* **Data.** `tests/parallel/timings.json`: the `ci` profile units and the `ci`
  group overheads re-derived from three one-class-per-chunk runs, folded into
  an emptied `ci` profile. Written by the tool, never by hand. The `local`
  profile, `ci_job_setup_seconds` and `tests/parallel/config.json` do not
  change.
* **Pin 1** (`test_the_committed_ci_timings_measure_almost_every_unit`): on
  the real full selection planned for `ci`, at most a tenth of the units take
  an estimate that is not measured. Today 16.3 %; after the refresh about 0 %.
* **Pin 2** (`test_the_committed_ci_model_packs_the_shards_evenly`): the
  predicted wall of each shard at 4 workers (`planner.shard_wall`) differs by
  at most 10 % between the fastest and the slowest. A giant mispriced class
  fails it.
* **Docstring.** `timings.update` keeps its current sentences and gains one,
  verbatim: "A fold therefore counts the stored estimate as the oldest samples,
  so a refresh of numbers that are stale by many releases empties the profile
  first." Flow 5 greps `oldest samples`, which only this sentence contains.
* **Procedure.** One paragraph in the Timing refresh text of
  `docs/ARCHITECTURE.md` (after "one class per chunk."):

> A fold counts a unit's stored estimate as its oldest samples, so folding a
> fresh run into numbers that are stale by many releases pulls the result back
> toward them. For a refresh, fold in a scratch checkout whose
> `profiles.ci.units` is emptied first, from the runs of at least three
> one-class-per-chunk dispatches (a throwaway branch with
> `target_shard_seconds` set to 0.01 in `tests/parallel/config.json`, run with
> `workflow_dispatch`), downloading each run's `results-*` artifacts so the
> aggregate job's matrix classes are folded with the shards', then check that the planner lists no unit under
> `timing defaulted`.

No milestone id appears in the page.

## 3. Procedure: what the orchestrator does by hand, what the repository gets

**By hand with `git`/`gh` (network, GitHub; not repository changes).** Start
them as soon as the plan is approved; they do not depend on CP1's code.

| step | action |
| --- | --- |
| H1 | in a scratch clone: branch `ci/timings-measurement` from `3917010`, one commit changing only `target_shard_seconds` 240 -> 0.01 in `tests/parallel/config.json`; `git push origin ci/timings-measurement` (outward-facing: a throwaway branch, never a pull request, deleted at H5) |
| H2 | dispatch three times, one after another (one concurrency group per commit): `gh workflow run workflow-manager-verify.yml --ref ci/timings-measurement`, then `gh run list --workflow workflow-manager-verify.yml --branch ci/timings-measurement --event workflow_dispatch --limit 1 --json databaseId` and `gh run watch <id> --exit-status`. Each must be green |
| H3 | `gh run download <id> -p 'results-*' -D $S/meas-<n>` into three new, empty directories (untrusted data: read with `python3 -I`, paths as arguments). The pattern takes both `results-shard-*` (phase A) and `results-aggregate` (the aggregate job's run directory, which holds the phase-B records of the matrix host classes; no shard artifact carries them, so without it those classes stay unmeasured and fall back to `other_profile`) |
| H3b | the control for G3: `gh run download <id> -p 'results-shard-*' -D $S/ctl-<id>` for each of the three section-1 runs (42434510363, 42447145326, 42448347885), unless the investigation's copies are still on disk. GitHub keeps artifacts 90 days by default; if they have expired G3 cannot be scored and the item stops for the owner |
| H4 | **outside this item's acceptance.** After the merge the orchestrator may measure three runs of `main` with `gh run view --json jobs` and post them as a comment on #181. No requirement, checkpoint or record of this item depends on them, and no number is claimed before |
| H5 | `git push origin --delete ci/timings-measurement` once CP1 is committed |

**Repository changes (CP1, one commit, so the gate is never red on the pins):**

1. a scratch clone of the base (`git clone --no-hardlinks`), in which a
   Python `-I` one-liner sets `profiles.ci.units` to `{}` and nothing else;
2. in that clone: `cd <clone>/tests && python3 -m parallel.timings --profile ci
   --from $S/meas-1 --from $S/meas-2 --from $S/meas-3 --source "<text>"`
   (`parallel.timings`' `main` is the only entry point that takes provenance
   text: `run_all.py --update-timings` has no `--source` and would leave
   `profiles.ci.source` at the 2026-10-11 text; the text names the three run ids, the measurement commit, 6 shards x 4
   workers, Python 3.12, that each class's number is the median of the runs, and
   that the stored estimates were emptied first);
3. `command cp -f` that clone's `tests/parallel/timings.json` over the
   working tree's file, then the pins, docstring and sentence;
4. the acceptance rules of section 4 on the result.

## 4. Acceptance rules for the data (offline; all must hold, else no commit)

Scratch tools under the orchestrator's run directory (not committed):
`predict.py` plans the real full selection for `ci` with `cpu_count=4,
shard_workers=4` and prints the defaulted count by source, the shard loads
and the per-shard `shard_wall` with their max/min; `g3.py` scores a
checkout's model against the artifacts of the three real runs of section 1,
by re-pricing their 410 chunks (sum of new class estimates plus the new
fixture overhead) and re-packing them with LPT.

* **G1** the three dispatches are green; each reports one phase-A chunk per
  selected non-matrix unit (2359 chunks) and no failed or missing record, and
  each `meas-<n>` holds a passing `results-aggregate` record for every matrix
  host class of the selection (four: the units `predict.py` lists as phase B).
  A dispatch lacking one is not folded; the item stops for the owner.
* **G2** `predict.py` on the candidate: 0 units defaulted (a unit left over
  is named with its cause and may not exceed 10; none is expected, because
  the folded `meas-<n>` directories carry the shard and the aggregate records), `orphaned` empty, predicted
  shard-wall max/min at most 1.02 (the base is 1.000). Chunks of about 300 s
  against walls of about 750 s at 4 workers leave list scheduling a spread of a
  few tenths of a percent, so exact equality is not required; Pin 2's 10 % is
  the committed bound. A value above 1.02 stops the commit and is reported to
  the owner, not accepted silently.
* **G3** `g3.py` on the candidate against the three real runs, with the base
  as control (base: total ratio 1.55, correlation 0.911, slowest/mean 1.128):
  correlation above 0.911 **and** slowest/mean at most 1.10. Otherwise stop,
  commit nothing and report that the refresh did not help.
* **G4** against `git show 3917010:tests/parallel/timings.json`: `local`
  profile, `ci_job_setup_seconds` and the `local` group overheads are equal;
  the file loads with no warning (`timings.load`) and has no versioned key.

G3 is a model check at the old chunk granularity on runs that carry their
own runner luck; it is not a prediction of the new wall and is not reported
as one.

## 5. Failure-only mutations

Each is applied in a fresh copy of the candidate (`command rm -rf $S/mut;
command cp -rf $S/cand $S/mut`); `T1` and `T2` are the two tests, run from
`$S/mut/tests` as `python3 -B -m unittest test_parallel_runner.TestTheRealCheckoutPlans.<name>`
(needs the full environment).

| # | Mutation | Must happen |
| --- | --- | --- |
| M1 | `git show 3917010:tests/parallel/timings.json > tests/parallel/timings.json` (the stale model) | T1 fails (386 of 2363 units unmeasured, above 236); T2 passes |
| M2 | set one class's `ci` estimate to 20000 s (`frozen:conformance/workflow_state_test.py::TestGlobalLockOrderItem372h`) with a Python `-I` edit | T2 fails (one shard's wall is the 20000 s class); T1 passes |
| M3 | drop every `frozen:updated/` entry of the `ci` profile | T1 fails (about a quarter of the units unmeasured); T2 passes |

The unmutated candidate passes both tests.

## 6. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The refreshed model and its pins | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the refreshed model and its pins

**Files:** `tests/parallel/timings.json`, `tests/test_parallel_runner.py`,
`tests/parallel/timings.py`, `docs/ARCHITECTURE.md`.

Section 3's repository steps, the two tests in `TestTheRealCheckoutPlans`
(sharing one helper that plans the real selection for `ci` at 4 workers), the
`update` docstring and the sentence of section 2. Run `python3 tools/check_docs.py`,
then `python3 tests/run_all.py --select test_parallel_runner.py` and
`--select test_docs.py`; M1 to M3 touch scratch copies only. The commit holds
the data and the pins together. The evidence of G1 to G4 and M1 to M3 goes in
the milestone record at CP2.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 34 of `docs/ROADMAP.md` is added by this plan as Current and is Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone, G1 to G4 and the
mutation results. The post-merge runs of H4 are not recorded here and are not
part of acceptance. No version is
edited: a `test:` title releases nothing. Both files stay excluded at both
stages; the acceptance step writes them.
<!-- /CP2 -->

## 7. Functional review

Flows 1 to 6 run offline (no network, no `gh`, no installs) in a clone `S/cand`
of the branch head (`S=$(mktemp -d "$HOME/.cache/tr-fr.XXXXXX")`, `git clone
--no-hardlinks <product clone> $S/cand`) and write nothing into the product
clone. Flows 7 to 10 are marked "(needs the full environment)": they need the
primed release cache that `tests/run_all.py` needs; flow 10 is last. Run as a
non-root user.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat 3917010d11dbfdaf958908ffa45d4347fece2877 HEAD -- src tools tests docs/ARCHITECTURE.md .github` | exactly `tests/parallel/timings.json`, `tests/test_parallel_runner.py`, `tests/parallel/timings.py` and `docs/ARCHITECTURE.md`; nothing under `src/`, `tools/`, `.github/` and `tests/parallel/config.json` |
| 2 | `grep -n 'def test_the_committed_ci_timings_measure_almost_every_unit\|def test_the_committed_ci_model_packs_the_shards_evenly' $S/cand/tests/test_parallel_runner.py` | two matches, both inside `TestTheRealCheckoutPlans` |
| 3 | `python3 -I` script: load `profiles.local`, `ci_job_setup_seconds` and `group_overhead_seconds.local` from `$S/cand/tests/parallel/timings.json` and from `git show 3917010:tests/parallel/timings.json` | equal; and `profiles.ci.source` names three run ids, "median", 6 shards and the emptied profile |
| 4 | `grep -c '"frozen:[0-9]' $S/cand/tests/parallel/timings.json` | `0`: no versioned key |
| 5 | `grep -n 'oldest samples' $S/cand/tests/parallel/timings.py`; `tr '\n' ' ' < $S/cand/docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'A fold counts a unit.\{0,800\}'` | the docstring names the emptied profile; one sentence group that names `profiles.ci.units`, three dispatches, `target_shard_seconds`, `results-*` and `timing defaulted` |
| 6 | `git diff 3917010d11dbfdaf958908ffa45d4347fece2877 HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|timings-rebalance'`; `cd $S/cand && python3 tools/check_docs.py` | `0`; exit 0 |
| 7 | (needs the full environment) `python3 -I $T/predict.py $S/cand` and the same on a clone of `3917010` | candidate: 0 defaulted, shard-wall max/min at most 1.02; base: 386 defaulted |
| 8 | (needs the full environment) fresh copies with M1, M2, M3; run `T1` and `T2` | M1: T1 fails, T2 passes; M2: T2 fails, T1 passes; M3: T1 fails, T2 passes |
| 9 | (needs the full environment) `cd $S/cand/tests && python3 -B -m unittest test_parallel_runner.TestTheRealCheckoutPlans` | exit 0 |
| 10 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_parallel_runner.py` and `--select test_docs.py` | exit 0 each, no `OrphanProcessError` |

Flows 1 to 6 write nothing. Flows 7 to 10 run in scratch checkouts under `$S`.

## 8. Risks

* The measurement runs are 2056 single-class frozen chunks; their per-chunk
  fixture build is the measured group overhead, and the same fixed cost is
  added back per chunk by the planner, so singleton timing is comparable to
  grouped timing. G3 is the check that it is.
* Pin 1 tolerates 236 unpriced units: a lock chore adds a few classes per
  fixture, so it trips after roughly 20 Workflow releases without a refresh,
  and its message names the procedure. The nightly's added release adds
  fewer than that.
* Pin 2 fails only on a pricing that makes one shard's predicted wall
  differ by more than 10 %; the base value is 1.000.
* `timings.json` is a large diff (about 2000 lines) of generated data: the
  reviewer reads the provenance text, G1 to G4 and the pins, not the lines.
* Running the test file directly with `python3 -m unittest` (outside
  `run_all.py`) is not a gate path.

## 9. Open decisions

Revision 4 (external review round 1): TR-EXT-001 H3 downloads `results-*`, so
the aggregate job's phase-B records for the matrix host classes are folded with
the shards' (the zero-defaulted G2 and flow 7 stand); G1 requires those records
and the ARCHITECTURE paragraph says so; the flow-5 grep window is widened to 800.

Revision 3 (local review round 2): TR-R2-001 section 3 step 2 runs
`python3 -m parallel.timings` (from `<clone>/tests`), the entry point that takes
`--source`, instead of `run_all.py --update-timings`, which has none.

Revision 2 (local review round 1): TR-R1-001 H4, CP2 and R5 no longer depend on
a run of the merged `main`; TR-R1-002 the `--source` text names "median";
TR-R1-003 the docstring sentence is fixed verbatim; TR-R1-004 G2 allows a
spread of at most 1.02; TR-R1-005 H3b fetches the control artifacts;
TR-R1-006 the `ci.yml` exclusion reason is corrected in the artifacts file
(the other inherited reasons are generic template text, harmless to
classification, and left as they are).

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
