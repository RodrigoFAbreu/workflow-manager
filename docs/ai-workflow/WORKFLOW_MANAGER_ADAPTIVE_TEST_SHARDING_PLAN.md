# Workflow Manager: Adaptive, Duration-Balanced Test Sharding (Revision 7)

`work_item_id: workflow-manager-adaptive-test-sharding` -- `governing_workflow_version: "2.2"`

**Deliverable:** a deterministic test inventory, planner, parallel executor,
result aggregator and dynamic CI pipeline for **this repository's own**
verification suite (`tests/`), cutting full-verification wall-clock time
without removing, skipping or weakening a single test.
**Governing workflow version:** `2.2` (the config default at creation).
**Work item type:** `process` (repository tooling; no Workflow release, no
product code).
**Base commit:** `db4c7af59653de54c8f71c15a4f00cd3caa72707` (tip of `main`:
`2.6.0` accepted, installed Workflow `2.5.1`, protocol `2.2` active).
**Scope source:** the user's milestone brief of 2026-09-26 (this milestone is
not a `docs/ROADMAP.md` section; roadmap section 1.9 -- Controller
integration and the Orchestration Protocol -- stays NEXT and is explicitly
excluded here).

**Measured baseline (section 3.1):** full serial verification takes
**2162 s (36.0 min)** locally; 96.5 % of it is 105 frozen-suite
invocations made from 15 host classes.

## 1. Goal

Make `python3 tests/run_all.py` -- the one command every gate in this
repository (`CLAUDE.md` "Before changing anything", "Adding an upstream
Workflow release" step 2, "Adding an authored Workflow release" step 3,
every checkpoint's full-regression row) already names -- run the **same,
complete** set of tests it runs today, in a fraction of the wall-clock time,
by changing only *how* the tests are scheduled and executed:

1. an authoritative, deterministic inventory of every test the full
   selection requires, independent of any timing data;
2. a planner that splits a selection into an adaptively sized number of
   duration-balanced shards, proving on every plan that the shards partition
   the selection exactly;
3. decomposition of the few oversized units (the frozen-suite matrix
   classes) into independently executable, independently isolated chunks
   whose merged results feed the **unchanged** assertions;
4. an isolation model that makes concurrent execution safe, with the
   non-overlappable tests identified from evidence and serialized
   auditably, and one run per checkout at a time;
5. one local executor and one dynamic CI pipeline driven by the same plan;
6. one aggregated verdict with the existing exit-code contract, failing test
   names, logs and a copy-pasteable single-unit reproduction command;
7. a measured pre-change baseline and measured post-change results, locally
   and in CI, against a ~5-minute CI target -- with any remaining serial
   floor documented quantitatively rather than closed by weakening
   coverage.

## 2. Non-goals

- **No verification tiers.** No FAST/STANDARD/FULL (or equivalent) modes.
  Every gate runs the full selection. Targeted selection (`--select`) is a
  debugging convenience, never a gate. The pre-existing `--fast` flag is
  handled by decision `D-Fast-Flag` (section 5.12), which is flagged for
  the user rather than silently decided.
- **No coverage reduction.** No test is removed, skipped, sampled,
  deduplicated or made conditional on timing history. The frozen suites'
  pinned test counts (`tests/support.py`'s `CI_SUITES`) and the exact
  portability-exception equality stay asserted, over the merged results.
- **No Workflow change.** No file under `distribution/`, `migration/`,
  `scripts/`, `.claude/commands/` or `docs/ai-workflow/` (other than this
  item's own plan/registry/mapping/artifacts files and the workflow's own
  bookkeeping) changes. No frozen or authored Workflow release is rebuilt.
  The frozen suites are executed byte-for-byte as shipped; only *which
  classes* one invocation runs changes, through `unittest.main()`'s own
  documented argv (section 5.5).
- **No product-semantic change to make tests parallelizable.** Where a test
  cannot safely overlap another, it is serialized (section 5.8), never
  rewritten to test something weaker.
- **Timing data is never Workflow normative state.** It lives under
  `tests/parallel/`, is read by nothing under `scripts/` or
  `distribution/`, and never decides whether a test runs.
- **Not in scope:** the Controller <-> Workflow 2.6 integration and the
  public Orchestration Protocol (`docs/ROADMAP.md` 1.9); any change to the
  managed `.github/workflows/workflow-conformance.yml` (it is a
  `workflow_manager`-managed file, section 5.10); speculative fixture
  caching (section 5.14 makes it an evidence-gated, report-only
  evaluation).

## 3. Investigation findings (measured at the base commit)

All local measurements: this workstation, 16 logical CPUs, 30 GiB RAM,
Python 3.14.7, Git 2.55.0, 1-minute load average 2-4 from unrelated
processes throughout, base commit `db4c7af`, clean tree. The profiling
scripts are throwaway (session scratch, not committed); CP5 re-creates the
capability properly as `--profile` output of the executor, and CP7
re-measures everything from the committed tooling.

### 3.1 Authoritative serial baseline (P-0)

`python3 tests/run_all.py` (full), 2026-09-26 17:07:43Z -> 17:43:45Z,
exit 0: **2162 s wall (36.0 min)**.

| module | seconds | share |
| --- | ---: | ---: |
| `test_conformance_suite.py` | 1421.0 | 65.7 % |
| `test_bootstrap_e2e.py` | 693.4 | 32.1 % |
| `test_workflow_2_6_0_hardening_disposable_repo.py` | 27.9 | 1.3 % |
| `test_implementation_review_two_stage_disposable_repo.py` | 11.6 | 0.5 % |
| the other eight modules together | 8.6 | 0.4 % |

The brief's figures (conformance ~1360 s, bootstrap E2E ~682 s, ~34 min)
and `docs/ACTIVE_MILESTONE.md`'s CP9 record (1336.6 s / 666.9 s) agree
within 5 %; the suite has grown slightly since.

### 3.2 Where the time goes: the frozen-suite matrix

A second, instrumented serial pass (every `support.run_suite` call timed;
per-class wall including `setUpClass`) reproduced the baseline within
1.6 % and shows:

- **105 frozen-suite invocations take 2087 s -- 96.5 % of all serial
  time.** They are made from inside `setUpClass` of exactly 15 host
  classes (5 releases x {`TestConformanceFixture*`,
  `TestBootstrappedTarget*`, `TestBootstrappedRepositorySatisfiesTheFrozenSuite*`}),
  each running all seven `CI_SUITES` suites serially in one repository.
  Every other host class together takes ~75 s.
- Per matrix host class: `2.6.0` classes 245-249 s each; `2.3.1`-`2.5.1`
  classes 104-117 s each. As indivisible units, **the three `2.6.0`
  classes (~249 s) would bound wall time** no matter how many shards ran.
- By frozen suite, across all 105 invocations:
  `workflow_acceptance_matrix_test.py` 1471 s (70 %),
  `workflow_state_test.py` 387 s, `workflow_fingerprint_generalization_test.py`
  102 s, `workflow_state_completion_obligations_test.py` 64 s, the other
  three 64 s together.
- Inside the frozen suites (one `2.6.0` conformance fixture, per class):
  the acceptance matrix is 49 classes summing to 180 s, largest class
  `RepoGlobalLifecycleAcrossWorktrees` 22.2 s, median 2.9 s;
  `workflow_state_test.py` is 149 classes summing to 41 s, largest
  `TestGlobalLockOrderItem372h` **22.5 s** (one test of it 14.8 s). No
  frozen class anywhere exceeds 22.5 s locally. The `2.3.1` suites have
  the same shape at about half the size (largest class 12.3 s).
- Frozen classes per release (all seven suites): 223 / 233 / 265 / 266 /
  311 for `2.3.1` / `2.4.0` / `2.5.0` / `2.5.1` / `2.6.0`; x 3 fixture
  kinds = **3894 frozen-class atomic units**, plus 79 non-matrix host
  classes (349 host tests across 94 classes in total).
- **Fixture build cost is negligible:** `build_conformance_repo` /
  `build_target_repo` take 0.06-0.11 s; per-invocation interpreter and
  suite-import overhead is ~0.1-0.3 s (e.g. the 19-test harness suite runs
  in 0.1 s wall). Splitting a frozen suite across fresh repositories costs
  well under 1 s per chunk.

### 3.3 Parallel-safety audit

**Contention experiment.** Frozen-suite chains run concurrently in
separately built fixtures (same instrumented runner):

| concurrency | wall | slowdown of the `2.6.0` chain vs serial 247 s | outcomes |
| --- | ---: | ---: | --- |
| 5 (`conformance`, all releases) | 256 s | 1.04x | all green |
| 10 (`conformance` + `target`, all releases) | 301 s | 1.22x (`workflow_state_test.py` 1.57x, acceptance matrix 1.15x) | exactly the two documented `2.3.1`/`2.4.0` portability exceptions, nothing else |

The 10-way run did 1871 s of serial work in 301 s. The race tests in
`workflow_state_test.py` (15 s deadlines) passed at 10-way concurrency;
they are the most load-sensitive code measured (section 5.7).

**Shared-state audit** (all 12 host modules, all `2.6.0` frozen suites,
`src/workflow_manager/`):

| hazard | finding |
| --- | --- |
| writes to the real repository tree | **one**: `test_amendment_update_path.py::TestMigrateDoesNotDeleteASiblingAuthoredRelease.test_a_fresh_regeneration_leaves_authored_siblings_untouched` runs `tools/migrate.py` without `--check`, which `shutil.rmtree`s the real `distribution/workflow/2.3.1/` and rebuilds it, then restores via `git checkout`/`git clean`. A concurrent reader already collided with it once (`docs/ACTIVE_MILESTONE.md`, CP9 process note: `test_disposable_repo_fixtures.py` "briefly saw no `2.3.1/manifest.json`"). `build_release.py --check` and `migrate.py --check` build into temporary roots only. |
| readers of the real tree | nearly every unit reads `distribution/` via `find_release`; several read `migration/`, `tools/`, `README.md`, `docs/` -- safe except against the writer above |
| disposable repositories and worktrees | always under `tempfile.mkdtemp`/`TemporaryDirectory` (collision-free); linked worktrees are created as siblings inside those directories |
| Workflow locks and witnesses | repository-local (`.ai-review/runtime/`, git common dir) of each disposable repository |
| Git configuration | frozen runs pin `GIT_CONFIG_GLOBAL`/`SYSTEM` to `/dev/null`; host tests set identity per repository and only read global config |
| fixed paths, ports, daemons | none (no fixed `/tmp` names, no sockets, no servers) |
| bytecode | `support` sets `sys.dont_write_bytecode`, but gitignored `__pycache__` directories exist today (`git status --ignored`, round 3, O2) under `distribution/workflow/{2.4.0,2.5.0,2.5.1,2.6.0}/payload/scripts/`, `migration/overlays/{2.5.0,2.5.1,2.6.0}/payload/scripts/`, `src/workflow_manager/`, `tests/`, `tools/` and `scripts/`. One known writer: `TestCliDrivesTheSameOperations._cli` (`tests/test_bootstrap_e2e.py:258-263`) and `tests/test_amendment_update_path.py:510-514` replace `env` wholesale, without `PYTHONDONTWRITEBYTECODE`, so their `python3 -m workflow_manager` writes `src/workflow_manager/__pycache__/` |
| upstream clone | `tests/support.py` and `tools/migrate.py` read `~/Workspace/repflow-android` (public) read-only via `git show`/`ls-tree`; `migrate.py` ignores `WORKFLOW_MANAGER_UPSTREAM` |

### 3.4 Can the oversized units be subdivided? Yes, at frozen-class granularity

- No frozen suite in any release defines `setUpModule`, `tearDownModule` or
  `load_tests`, and every `__main__` block is a bare `unittest.main()`
  (`verbosity=1`/`2` in two), so `python3 <suite>.py ClassA ClassB`
  runs exactly those classes as `__main__` through the same code path.
- The host matrix assertions decompose: per-suite `Ran N` counts sum,
  failure sets union, return codes max, and the `bootstrapped` residue and
  drift checks can run per chunk (section 5.5).
- Splitting *host* classes is not needed: every non-matrix host class is
  under 6 s.

### 3.5 What is achievable

- **Local.** Total work ~2160 s; floor at frozen-class granularity
  22.5 s; measured contention ~1.2x at 10-way. With 8 workers the
  predicted makespan is ~2160 x 1.2 / 8 = **~5.4 min (~6.7x faster)**;
  with 16 workers perhaps ~3.5-4 min if contention stays near 1.5x. CP7
  measures both.
- **CI.** The only CI data point today is the managed job on
  `RodrigoFAbreu/workflow-manager` (private; standard 2-vCPU runner),
  run `36210177714`: the installed `2.5.1` suites take ~319 s there,
  against ~116 s for the same chain locally -- **~2.75x slower per
  suite** (one sample; CP6 re-measures). That factor mixes two effects
  that cannot be separated from one run: the runner's speed, and the
  interpreter version (5.10 pins `actions/setup-python` 3.12; every local
  number here is Python 3.14.7). CP6's `--shards 1` reference run is on
  the same 3.12 as the sharded runs, so the CI speed-up it measures is
  version-consistent. Projected CI total work is
  therefore ~5900 s (~100 runner-minutes). The CI critical path (~62 s
  for the largest frozen class) is not the limit; parallelism is:
  16 shards -> ~370 s compute per shard, ~6.5-7 min end to end; ~24
  shards -> ~250 s, **~5 min**. Job setup in that run took ~3 s.
- **Cost, not coverage, sets the CI number.** Billed minutes are roughly
  total work plus per-job rounding (~100-120 min per full run at 16-24
  shards), almost independent of the shard count. That makes
  `ci_max_shards` a cost-free latency choice *per run*, but the run
  frequency a real budget question (`D-CI-Cost`, section 5.13).
- **Fixture reuse is not worth doing.** Build cost is <0.11 s per chunk
  (3.2), so `D-Fixture-Reuse` (5.14) is closed by this evidence unless
  CP7's `bootstrapped` measurement contradicts it.

## 4. Invariants (normative for every checkpoint)

- **INV-1 Exact partition.** For every plan: the multiset union of all
  shards' atomic units equals the selection's atomic-unit set; every
  pairwise shard intersection is empty; no atomic unit appears twice or is
  missing. Checked by the planner on every plan (refuse to emit otherwise),
  re-checked by every shard before it runs (against the plan digest), and
  re-checked by the aggregator against the results actually received.
- **INV-2 Timing-independent selection.** The selection (which atomic
  units, hence which tests, must run) is a pure function of
  `(repository tree, --select arguments)`. Timing history, shard count,
  environment profile and bounds never appear in its inputs. A property
  test runs the selector under empty, corrupt, stale, adversarial and
  real timing files and asserts byte-identical selections.
- **INV-3 Determinism.** Given the same tree, selection, timing file,
  profile and bounds, the plan JSON is byte-identical (canonical JSON,
  sorted keys, explicit tie-breaks on unit id). No wall clock, randomness,
  hash-seed, `os.listdir` order or process id enters a plan.
- **INV-4 Unchanged assertions.** Every existing assertion in `tests/`
  still executes, over the same observable facts. Where section 5.5 moves
  frozen-suite *execution* out of a host class, the host class's
  assertions run unchanged over the merged records. The merge itself
  refuses a *structurally* incomplete or duplicated record set (a planned
  chunk with no record, overlapping or missing classes, a foreign digest),
  but never judges test outcomes: a chunk that ran fewer tests than
  enumerated, errored in `setUpClass`, or crashed at import flows into the
  merged view and fails the unchanged host assertion that would fail today
  (section 5.5). One existing assertion reads `run_all.py`'s *source*
  rather than a run's outcome:
  `tests/test_workflow_2_6_0_hardening_disposable_repo.py:1425-1426`
  (`test_the_repository_level_guards_are_still_registered`, v2.3.1-002).
  CP5 replaces it with one declared, reviewed assertion change over the
  same fact, the one exception to "unchanged" (5.12).
- **INV-5 Frozen bytes.** Frozen and authored Workflow suites run from a
  disposable repository built by the existing `workflow_manager.fixture` /
  `install.bootstrap` code, invoked as `python3 <suite>.py [Class ...]` from
  that repository's `scripts/` with `support.run_suite`'s existing
  environment. No frozen file is patched, wrapped, or imported in-process
  by the executor.
- **INV-6 Serial reference.** `--jobs 1` of any selection executes
  exactly the same plan units (phase A chunks, then phase B matrix host
  classes in *merged* mode), one at a time, in the same isolation, and
  must reach the same verdict and the same per-suite counts as the
  parallel run. It is the equivalence oracle for the parallel run, not a
  separate mode of coverage. The oracle for *today's* behaviour is direct
  mode (section 5.5): the unchanged module entry points, which never go
  through the planner. CP2 proves direct == merged; CP5 proves
  `--jobs 1` == `--jobs auto` and re-checks both against direct mode.
  **Applies from CP5 (round 5, O3).** Before CP5 there is no merged-mode
  executor, run lock or barrier. CP1's interim `--jobs 1 [--select ...]`
  path runs the selected host classes one at a time in **direct mode**,
  including the matrix host classes, with no lock and no barrier. It is
  a developer convenience and the narrow check that section 8's common
  rules name for CP1-CP4. It is not the serial reference. INV-6 and 5.9's
  lock and guard table bind every `run_all.py` mode from CP5 onward.
- **INV-7 Fail closed.** A missing shard result, a plan-digest mismatch, a
  record from a different tree, a unit the executor had to kill (timeout)
  or whose runner process died without writing its record, or a detected
  undeclared write to the repository tree is a failed run (exit 2 for
  infrastructure faults, section 5.11), never a pass. A frozen suite that
  itself crashes, errors or loses tests is **not** an infrastructure
  fault: its record exists and carries that outcome, and the unchanged
  host assertion fails (exit 1), exactly as today.
- **INV-8 No shared mutable state between concurrent units** except
  through a declared resource (section 5.8), and no two `run_all.py`
  invocations ever execute in the same checkout at once (the checkout
  run lock, 5.9). Section 5.9 states exactly
  which undeclared writes to the real repository tree are caught, by
  which mechanism, and which are not: persistent changes are detected
  after the run; transient create/delete/rename inside the guarded trees
  is refused as it happens; a transient in-place overwrite that is
  restored before the run ends is caught only by CP4's static lint.

## 5. Design decisions

### 5.1 `D-Inventory`: atomic units and deterministic discovery

Two kinds of **atomic unit**, each with a stable textual id:

| kind | id form | granularity | why this granularity |
| --- | --- | --- | --- |
| host class | `host:<module>.py::<Class>` | one `unittest.TestCase` class in `tests/test_*.py` | classes share `setUpClass` fixtures (`_SuiteRun`, `TestUpdatePreservesLiveWorkItemState`, `_RealReleaseCase`); splitting a class would run its fixture twice and change what the class proves. Never split. |
| frozen class | `frozen:<version>/<fixture>/<suite>.py::<Class>` | one class of one frozen/authored suite, in one fixture kind, for one release | the only units big enough to need splitting (section 3); the frozen suites have no `setUpModule`/`load_tests` and every `__main__` block is a bare `unittest.main()` (section 3.4), so a class is the finest boundary the suites themselves already respect |

`<fixture>` is one of `conformance` (`build_conformance_repo`), `target`
(`build_target_repo`) and `bootstrapped` (`install.bootstrap` into an empty
repository, `test_bootstrap_e2e.py`'s path) -- the three disposable
repository shapes the 15 matrix host classes already build.

**Discovery** (`tests/parallel/inventory.py`):
- Host classes: for each `tests/test_*.py` in sorted byte order, import
  the module in a discovery subprocess (cwd `<repo_root>/tests/`, with
  that directory as `sys.path[0]`, `PYTHONDONTWRITEBYTECODE=1`) and walk `unittest.defaultTestLoader.loadTestsFromModule` -- the same
  loader `unittest.main()` uses today, so discovery sees exactly the
  tests a direct run sees. Output: `{class_id: [test_id, ...]}`, sorted.
- Frozen classes: for each matrix host class (identified by the
  declarative `FROZEN_MATRIX` table, section 5.5), for each
  `CI_SUITES[version]` suite, load the suite module **from the release's
  own `distribution/workflow/<version>/payload/scripts/`** in a discovery
  subprocess and list its classes and test ids. The payload bytes are the
  exact bytes every fixture copies (`_place_payload`), and discovery
  asserts the per-suite test total equals `CI_SUITES[version][suite]` --
  so a discovery that disagrees with the pinned counts is an inventory
  error before anything runs. `FROZEN_MATRIX` and `CI_SUITES` are read
  **inside that same discovery subprocess**, from
  `<repo_root>/tests/parallel/matrix.py` and the `<repo_root>/tests/support.py`
  it imports. The executor process never imports `parallel.matrix` or
  `support` for data (round 4, O1). So an in-process
  `cli.main(argv, repo_root=scratch)` sees the scratch checkout's matrix
  and release, never the importing process's real ones. Discovery **imports and never runs**: it
  executes a frozen suite's module-level code (imports and definitions,
  as any `import` does) and calls `loadTestsFromModule`, which constructs
  `TestCase` instances without calling any test, fixture or
  `setUpClass`. It runs with `PYTHONDONTWRITEBYTECODE=1` and
  `sys.dont_write_bytecode`, so it adds nothing to the stray
  `__pycache__` noted in 3.3, and it runs inside the executor's
  before/after integrity window (5.9 step 1 snapshots first), so a
  discovery that wrote to `distribution/` would fail the run.
- The inventory file is canonical JSON with a `tree_digest` (see 5.6),
  written to the run directory for inspection; it is recomputed on every
  run, never cached (a per-run directory could never hit a cache, and
  P-5 bounds discovery + planning at 20 s), and never committed.

**Selection grammar** (`--select`, repeatable, union of matches; no
`--select` = the full selection):

| spec | selects |
| --- | --- |
| `test_bootstrap.py` | every host class in the module (and, for a matrix module, its frozen classes) |
| `test_bootstrap.py::TestUpdate` | one host class |
| `test_bootstrap.py::TestUpdate::test_x` | one host test (run inside its class's unit; the class fixture still runs once) |
| `frozen:2.6.0/conformance/workflow_state_test.py` | one frozen suite in one fixture |
| `frozen:2.6.0/conformance/workflow_state_test.py::TestFoo` | one frozen class |

Selecting a matrix host class implies all of its frozen classes (its
assertions need them). Selecting only frozen classes runs them without the
host assertions and says so in the report ("partial frozen selection:
host matrix assertions not evaluated") -- a debugging aid, never a gate.
An unknown spec is a usage error, never an empty selection.

### 5.2 `D-Timing-History`: format and lifecycle

**Committed estimates** -- `tests/parallel/timings.json`:

```json
{
  "schema_version": 1,
  "profiles": {
    "local": {"units": {"<unit id>": {"seconds": 12.4, "samples": 5}}, "source": "..."},
    "ci":    {"units": {"<unit id>": {"seconds": 23.9, "samples": 3}}, "source": "..."}
  },
  "group_overhead_seconds": {"local": {"conformance": 0.0, "target": 0.0, "bootstrapped": 0.0},
                             "ci":    {"conformance": 0.0, "target": 0.0, "bootstrapped": 0.0}},
  "ci_job_setup_seconds": {"plan": 0.0, "shard": 0.0, "aggregate": 0.0}
}
```

- `seconds` is the **median** of the most recent `samples` (at most 5)
  observed durations, rounded to 0.1 s -- median, not mean, so one slow run
  on a loaded machine does not skew the plan.
- `group_overhead_seconds` is the measured fixed cost of one frozen
  execution group (repository build + interpreter start + suite import),
  paid once per chunk (section 5.4). `ci_job_setup_seconds` is the
  measured per-job setup of each CI job kind (5.4 step 5); CP6 seeds it
  and CP7 refreshes it.
- Canonical JSON (sorted keys, 2-space indent, trailing newline) so a
  refresh produces a reviewable diff.

**Observed history (never committed)** -- every run appends one JSON line
per executed unit (`unit`, `profile`, `seconds`, `outcome`, `tree_digest`,
`utc`) to `$XDG_CACHE_HOME/workflow-manager/test-timings.jsonl` (default
`~/.cache/...`) locally, and to a results artifact in CI.

**Lifecycle.**
- *Refresh* is explicit: `python3 tests/run_all.py --update-timings
  [--from <results dir or jsonl> ...] --profile local|ci` folds passing
  observations into `timings.json`. Nothing rewrites the committed file
  implicitly; CI never commits.
- *New unit* (no estimate in the active profile): estimate = the other
  profile's value x the profile ratio (median ratio over units present in
  both), else the median of known units of the same group (same module, or
  same `version/fixture/suite`), else `default_unit_seconds` from
  `tests/parallel/config.json`. The report lists every defaulted unit.
- *Stale entry* (unit no longer in the inventory): ignored, listed as
  `orphaned` in the report; `--update-timings` drops it.
- *Drift*: a unit whose observed duration is outside `[0.5x, 2x]` of its
  estimate is listed as `drifted` in the report (advisory; never a
  failure, never a selection change).
- Corrupt/unreadable timing file: warning, every estimate falls back to
  defaults, the run proceeds with the full selection (INV-2 test covers it).
- Timing never leaves `tests/parallel/` and the user cache; no Workflow
  module reads it.

### 5.3 `D-Shard-Count`: adaptive shard count

```
T      = sum(estimate(chunk) for chunk in chunks)          # includes group overheads
C      = max(estimate(chunk))                               # critical-path floor
n_raw  = ceil(T / target_shard_seconds)
n      = clamp(n_raw, min_shards, max_shards(profile))
n      = min(n, number_of_chunks)                           # never an empty shard
```

- `max_shards(local) = min(local_max_shards, os.cpu_count())`;
  `max_shards(ci) = min(ci_max_shards, ci_account_concurrent_job_limit - 1)`
  (5.13). `--shards N` overrides (still clamped
  to `[1, number_of_chunks]`), `--jobs N` overrides the local worker count
  (section 5.9).
- The report prints `T`, `C`, `n`, the predicted makespan
  (`max shard load`) and, when `C > target_shard_seconds`, the critical-
  path warning naming the unit that bounds wall time.
- Initial `tests/parallel/config.json` values are the brief's
  (`target_shard_seconds: 240`, `min_shards: 2`, `local_max_shards: 8`,
  `ci_max_shards: 16`, `default_unit_seconds: 30`,
  `default_group_overhead_seconds: 0.5`,
  `split_threshold_ratio: 0.5`), plus `ci_account_concurrent_job_limit:
  20` (the Free-plan value, the conservative default until the user
  records the real one, 5.13); CP7 tunes them from measurements and
  records the evidence (section 7); section 3.5 already predicts that
  `ci_max_shards` near 24 is what reaches ~5 min in CI, so CP7 measures
  16 and 24 and the user chooses (`D-CI-Cost`).

### 5.4 `D-Balance`: chunking and duration-balanced assignment

1. **Group.** Atomic units are grouped into *execution groups*: a host
   class is its own group; frozen classes group by
   `(version, fixture, suite)` -- the classes that must share one
   disposable repository and one `python3 <suite>.py` invocation to be
   run efficiently.
2. **Chunk.** A group whose estimate (sum of its classes + its group
   overhead) is at most `split_threshold_ratio x target_shard_seconds` is
   one chunk. A larger frozen group is split into
   `k = ceil(group_estimate / (split_threshold_ratio x target_shard_seconds))`
   chunks by LPT over its classes (below), each chunk paying the group
   overhead once. Host classes are never split.
3. **Assign.** Longest-processing-time-first: sort chunks by
   `(-estimate, chunk_id)`, place each on the shard with the smallest
   `(load, shard_index)`. LPT is within 4/3 of the optimal makespan and is
   deterministic with these tie-breaks.
4. **Resource-aware placement.** Chunks holding an exclusive resource
   (section 5.8) are assigned to shards like any other and are always
   placed **first** in their shard's chunk order. The planner learns which
   units are exclusive only through CP1's `resources.load(repo_root)`
   (5.8), never by naming a unit itself (round 5, I1). The executor, not the
   planner, serializes them, by phase ordering rather than by lock
   contention (5.8): locally every exclusive chunk runs in pre-phase A0,
   alone, before the worker pool starts; in CI each shard is its own
   checkout, so its exclusive chunks simply run first.
5. **Phase B placement and the predicted makespan (round 3, O3).** The 15
   phase-B units (matrix host classes in merged mode, 5.5) are planned
   like any other units: they have timing estimates, and LPT assigns them
   over the same `n` workers in a separate phase-B assignment. Locally,
   the pool runs them after phase A drains. In CI, the `aggregate` job
   runs them over a pool of `os.cpu_count()` workers. The **local**
   predicted makespan is `sum(exclusive chunk estimates) + max shard
   load over the remaining phase-A chunks + max worker load over phase
   B`. The **CI** predicted wall is `plan job + max shard job + aggregate
   job`, where each job is its measured setup (`timings.json`'s
   `ci_job_setup_seconds`: checkout, Python, downloads, and for `plan`
   and `shard` the upstream fetch) plus its compute, and the aggregate
   compute is the phase-B makespan at the runner's worker count. The
   report prints each term, and P-5 compares against these totals.
   Phase B's cost is not yet measured in isolation. Each unit builds one
   fixture (0.06-0.11 s for `conformance`/`target`, 3.2; `bootstrapped`
   is unmeasured, 5.14) and runs a few sub-second assertions. Until CP5
   records it, it is estimated by 5.2's new-unit rule.
6. **Plan output** (`plan.json`): schema version, `tree_digest`,
   selection digest, profile, bounds, `n`, per-shard ordered chunk lists,
   the phase-B assignment, predicted loads and the predicted makespan
   terms, and a `plan_digest` over all of it. The plan is emitted only
   after INV-1 is verified.

   **The chunk-descriptor contract (round 5, I1).** Each entry of a
   shard's chunk list is a `ChunkDescriptor` from CP1's
   `tests/parallel/plan_schema.py`: `id`, `shard_index`, `units` (sorted
   atomic-unit ids), `estimate` (seconds), and `resources` (sorted names
   from `resources.json`; empty for a shared chunk). `plan_schema` also
   provides `ChunkDescriptor.to_json`/`from_json` and
   `shard_chunks(plan) -> list[list[ChunkDescriptor]]`, the one reader of
   a plan's chunk lists. The planner (CP3) writes chunks only through
   `to_json`. `isolation.phase_a_order` and `check_exclusive_windows`
   (CP4) read them only through `shard_chunks`, and nothing else in a
   plan. Because both sides depend on CP1's type rather than on each
   other, CP3 and CP4 stay independent and first meet at CP5 on a
   contract each has already tested against.

Chunking depends on timing; **coverage does not**: whatever the chunking,
the chunk set covers the group's classes exactly once (INV-1), and the
merge (5.5) re-proves it from what actually ran.

### 5.5 `D-Frozen-Matrix-Decomposition`: oversized-suite handling

The 15 matrix host classes (`TestConformanceFixture{231,240,250,251,260}`,
`TestBootstrappedTarget{...}` in `test_conformance_suite.py`;
`TestBootstrappedRepositorySatisfiesTheFrozenSuite{...}` in
`test_bootstrap_e2e.py`) each build one repository and then run all seven
frozen suites **serially inside `setUpClass`**. Section 3.2 shows their frozen-suite runs are
96.5 % of total serial time and that the acceptance matrix
alone is the largest single item. They are the oversized units.

**Mechanism.**
- New `tests/frozen_runs.py` (shared helper, used by both host modules):
  - `FrozenChunk(version, fixture, suite, classes)`;
  - `execute(chunk) -> FrozenRecord`: build a **fresh** repository with the
    fixture's existing builder, run `python3 <suite>.py <Class> ...` via
    `support.run_suite` (extended with an optional `classes` argument
    appended to argv -- `unittest.main()` resolves bare names against
    `__main__`, so the frozen file runs as `__main__` exactly as today),
    then record: `returncode`, `ran` (from the same `RAN_RE`), `failing`
    (from the same `support.failing_tests`), the chunk's enumerated test
    ids, the output tail, and -- for `bootstrapped` -- the post-run
    `git status --porcelain` residue and `install.drift(...)` result the
    host assertions check today; plus provenance (`tree_digest`, release
    manifest sha256, plan digest, chunk id).
    If the fixture builder itself raises, `execute` still writes a record
    (round 2, O4): `build_error` (the traceback), `returncode` 1, `ran`
    `None`, no `failing` entries. Today such an exception in a matrix
    `setUpClass` is a test error (exit 1); a build-error record keeps
    it one -- it is structurally complete, so the merge accepts it, and
    the unchanged count/pass assertions fail on `ran is None` and the
    non-zero `returncode` (exit 1), with the traceback in `output`. Only
    a chunk *process* that dies without writing any record is a missing
    record (exit 2).
  - `merge(records, context) -> {suite: MergedResult}`, where `context`
    is a `MergeContext` (below) for one `(version, fixture)`: checks
    **structural completeness only**, and refuses (raises
    `FrozenMergeError`, exit 2) unless, per suite: the set of record chunk
    ids equals the context's planned chunk ids for that suite, each
    exactly once; each record's class set equals its planned chunk's
    class set; the planned chunks' class sets are pairwise disjoint and
    their union equals the context's discovered class set for the suite;
    every record carries the context's `tree_digest` and `plan_digest`
    and the release digest `merge` reads from the release's own manifest;
    and every record was written by a chunk process that exited on its own
    (not killed by the executor's timeout). Every expected value comes
    from `context`, never from the records being checked (round 7, I1). It **never** compares test
    counts or outcomes. `MergedResult` exposes `returncode` (max), `ran`
    (sum, or `None` if any chunk's output has no `Ran N` summary),
    `failing` (union), `output` (chunk tails concatenated, labelled), and
    for `bootstrapped` the union of residues and drifts. A chunk whose
    frozen class errored in `setUpClass` (unittest counts one `ERROR`,
    none of the class's tests), or whose suite crashed on import (no
    summary at all), therefore yields a smaller `ran` or `None` plus a
    non-zero `returncode`: the unchanged
    `test_every_suite_runs_the_frozen_number_of_tests` /
    `test_every_frozen_suite_passes` assertions fail on it exactly as they
    do today (exit 1). The per-chunk difference between `ran` and the
    chunk's enumerated count is printed in the report as attribution
    (which chunk lost which tests), never as a refusal.
  - **Provenance is an argument, not a lookup (round 4, I1).** `execute`
    stamps, and `merge` compares against, the `tree_digest` and plan
    digest its caller passes. It reads the release digest from the
    release's own manifest. CP5's executor passes the real plan's values.
    CP2's tests pass synthetic strings, and CP2's evidence passes
    `tree.tree_digest(repo_root)` (CP1, 5.6) plus the digest of the fixed
    chunking below. So `frozen_runs` is complete and testable at CP2
    without the planner (CP3) or the executor (CP5).
  - **The merge context, and how phase B receives it (round 7, I1).**
    `MergeContext` (CP2, `tests/frozen_runs.py`, with canonical
    `to_json`/`from_json`) carries, for one `(version, fixture)`:
    `tree_digest`, `plan_digest`, and per suite the planned chunks
    (`{chunk_id: sorted class names}`) and the discovered class set. It
    is the one authoritative source of every expected value `merge`
    checks. It is built by whoever owns the plan, never read out of a
    records directory:
    - *CP5's executor* builds it after `planner.load_plan` has verified
      the plan's `plan_digest` and `tree_digest` (T-PLN-8): the planned
      chunks from `plan_schema.shard_chunks(plan)` (frozen units only,
      grouped by `(version, fixture, suite)`), the discovered class sets
      from this run's inventory, and both digests from the verified plan.
      It writes one file per `(version, fixture)` under
      `<run>/merge-context/` -- a directory separate from the records
      directory -- and passes that directory to every phase-B unit as
      `WM_FROZEN_CONTEXT`, next to `WM_FROZEN_RECORDS`. In CI the
      `aggregate` job does the same from the downloaded `plan.json`, so
      shard artifacts supply records only, never the context.
    - *CP2's evidence driver* builds it directly from its fixed chunking,
      the frozen inventory's class sets, `tree.tree_digest(repo_root)` and
      the fixed chunking's digest, writes it the same way, and sets the
      same two variables.
    - *Merged-mode `setUpClass`* refuses (`FrozenMergeError`) if
      `WM_FROZEN_RECORDS` is set and `WM_FROZEN_CONTEXT` is not, or if its
      `(version, fixture)` has no context file; it never derives a
      context from the records. It also recomputes
      `tree.tree_digest(repo_root)` and refuses a context whose
      `tree_digest` differs, so a context file from another checkout
      is refused too.
    T-MRG-7 is the negative test: a complete, internally consistent record
    set for one plan and tree, merged against a separately supplied
    context for a different plan, tree or chunk partition, is refused.
  - **CP2's evidence driver.** `python3 tests/frozen_runs.py --evidence
    {merged,one-class,residue}` runs E-MRG-1, -2 and -3 (6.2) serially.
    It executes each chunk with `execute`, then runs the matrix host
    classes through `unittest` with `WM_FROZEN_RECORDS` pointing at the
    records and `WM_FROZEN_CONTEXT` at the contexts it built from that
    chunking (above). `merged` uses a **fixed chunking**: each suite's classes, in
    sorted order, split into two chunks at the midpoint (a one-class
    suite is one chunk). That exercises multi-chunk merges without the
    planner. The planner's own chunking is proved equivalent in CP5
    (6.5).
- **Host classes, two modes, one set of assertions.**
  - *Direct mode* (the default whenever `WM_FROZEN_RECORDS` is unset,
    i.e. every unchanged entry point: `python3
    tests/test_conformance_suite.py TestConformanceFixture260`, `python3
    -m unittest ...`; never used by the executor, including `--jobs 1`,
    which always runs merged mode -- INV-6): `setUpClass` executes one
    full-suite chunk per suite in the one repository, in `CI_SUITES`
    order -- today's exact behaviour -- and wraps each result as a
    `FrozenRecord`. There is no plan and no foreign record in direct
    mode (each record is produced in-process), so it takes no context:
    `MergedResult.from_single(record)` computes the per-suite view with
    the same field computation `merge` applies to one chunk.
  - *Merged mode* (`WM_FROZEN_RECORDS=<dir>` and
    `WM_FROZEN_CONTEXT=<dir>` set by the executor):
    `setUpClass` builds its own repository (the non-suite assertions --
    "no upstream build system", "state file is the clean template", "no
    upstream host document", "generation script refuses cleanly" -- read
    the repository, and these builds are sub-second), loads the context
    and the records for its `(version, fixture)`, merges them, and
    exposes the same per-suite view.
  - The assertions are rewritten once to read `MergedResult` fields
    (`ran`, `failing`, `returncode`, `output`, residue, drift) instead of
    re-parsing a `CompletedProcess`; in direct mode those fields are
    computed by the very same `RAN_RE`/`failing_tests` calls as today, so
    each assertion's predicate is unchanged. CP2 proves this with a
    both-modes equivalence test and mutation tests (section 6).
- **Two execution phases.** Phase A runs every host-class chunk that is
  not a matrix host class, and every frozen chunk. Phase B runs the 15
  matrix host classes in merged mode (seconds each) after all phase-A
  records exist -- locally after the worker pool drains, in CI in the
  aggregate job. A matrix host class is therefore an atomic unit of
  phase B; its frozen classes are atomic units of phase A.

**What changes, stated plainly (`D-Frozen-Run-Fresh-Repo`, flagged for
review).** Today one repository sees all seven suites in sequence, and
inside each suite every class in file order; under decomposition each
chunk gets its own freshly built repository and runs a subset of one
suite's classes. The upstream CI template runs the suites as sequential
steps of one job (`.github/workflows/workflow-conformance.yml`), so a
sequential single-repository run is closer to it.

*What is kept:* every suite still runs in a repository built by the same
builder from the same release bytes; the `bootstrapped` post-run residue
and drift checks now run after *every* chunk (strictly more attribution
than one check at the end).

*Also different, and benign (round 2, O1):* merged-mode chunks run with
`PYTHONDONTWRITEBYTECODE=1` (5.7), while direct mode -- `support.run_suite`
as it is today (`tests/support.py:69-78`, which sets no bytecode variable)
-- lets each frozen suite write `scripts/__pycache__/` into its fixture
repository. The frozen code executed is the same source either way;
only whether CPython caches its compiled form differs. Neither the
`bootstrapped` residue check (`git status --porcelain`, which does not
list ignored files) nor any frozen assertion observes it today.

*What is lost* is detection of any interaction in which a later suite
(or a later class of the same suite) behaves differently **only because
of state an earlier one left behind** -- in the repository *or in its git
dir*. At the base commit that state is barely asserted today: only the
`bootstrapped` fixture checks `git status --porcelain` and `drift` after
the chain (`tests/test_bootstrap_e2e.py:104-110`); the `conformance` and
`target` host classes (`tests/test_conformance_suite.py:77-139`,
`:202-253`) assert nothing about residue between suites, and `git
status` sees none of: new commits or `HEAD` movement, refs, branches and
tags, stashes, `.git/config` (frozen suites run `git config`), registered
worktrees, hooks, or the `2.6.0` git-common-dir artifacts (checkpoint
claims, identity-gap authorizations, amendment witnesses). So the lost
property is "any state suite N (or class K) leaves in the repository or
its git dir that suite N+1 (or class K+1) observes", not merely ignored
residue.

*How CP2 measures it.* For every release x fixture x suite, in today's
sequential order, CP2 takes a **full-state snapshot** of the repository
before and after the suite runs and records the diff:
- worktree: `git status --porcelain=v1 -z --ignored --untracked-files=all`
  plus a sha256 of every listed path's content (so ignored and
  untracked files are in, not just tracked changes);
- git dir (the common dir): `git rev-parse HEAD`, `git symbolic-ref -q
  HEAD`, `git for-each-ref` (all refs, including `refs/stash`), `git
  config --local --list`, `git worktree list --porcelain`, and a sha256
  listing of every file under the common dir except `objects/`
  (content-addressed; unreferenced objects are unobservable through
  refs), `index` (covered by status) and `logs/` (reflogs move with the
  refs already captured) -- which covers `hooks/`, `info/` and every
  Workflow artifact kept there.
The snapshot helper lives in `tests/frozen_runs.py` so the same function
serves CP2's measurement and any later canary. The measurement is
deliberately conservative: it reports *any* delta, not just deltas a
later suite provably observes.

*Pre-classified deltas (round 2, O1).* Two kinds of delta are
foreseeable now and are classified before CP2 runs, so the rule below
does not fire on them:
- **bytecode caches** -- `__pycache__/` directories and `*.pyc` files
  that direct mode writes (above). A later suite that finds them loads
  the same code (CPython revalidates a `.pyc` against its source's mtime
  and size), so they are not an observable interaction;
- **`flock` target files** -- files the frozen Workflow code opens only
  to hold an `fcntl.flock` on (`.ai-review/runtime/WORKFLOW_STATE.lock`
  and the git-common-dir lifecycle lock). CP2 records, for each, the
  frozen source line that opens it; a lock held by a process that has
  exited carries no state. A file at such a path whose *content* the
  frozen code reads (a witness, a claim, a reservation) is **not** in
  this class.
Every other delta -- a commit, a moved ref, a config key, a registered
worktree, a hook, a Workflow witness, claim or authorization, any other
new or changed file -- is unclassified.

*Decision rule.* If every suite's delta is empty or pre-classified in
every fixture, the fresh-repository model loses nothing observable and
CP2 records that as the evidence, listing the pre-classified deltas it
saw. If any unclassified delta exists, CP2 stops and surfaces the
exact deltas before CP5, and the reviewer/user chooses between accepting
the gap (with those deltas written into this section) and adding a
`sequential-canary` unit: one `2.6.0` full sequential chain per fixture
in one repository (today's direct-mode behaviour), bounded by section
3's per-release chain time. Class-order interactions *within* a suite
are covered separately by CP2's one-class-per-chunk run (section 6
"Merge"), which gives every frozen class its own repository and must
reach the same outcome as the whole-suite run.

### 5.6 `D-Tree-Identity`: provenance of plans and records

`tree_digest` = sha256 over `git rev-parse HEAD` plus the byte content of
every tracked-and-modified and untracked-unignored path (`git status
--porcelain=v1 -z --untracked-files=all`, sorted), so a dirty working tree
has its own identity. A plan, a record and a merge all carry it; a shard
refuses a plan whose `tree_digest` differs from its checkout; the merge
refuses a record from another tree. CI uses the same function (clean
checkout: digest of HEAD alone). `tree_digest(repo_root)` and the
repository snapshot/compare function of 5.9 steps 1 and 6 live in
`tests/parallel/tree.py`, owned by **CP1** (round 4, I1). Every later
checkpoint that needs them depends on CP1: the planner writes the digest
into `plan.json` (CP3), T-INV-7 uses the snapshot (CP2), and the integrity
guard uses both (CP4).

**The tool's own outputs can never enter it.** Every file the tooling
writes -- the run directory (inventory, `plan.json`, merge contexts,
records, logs, per-chunk `TMPDIR`), `--out`/`--plan`/`--results` paths,
the timing cache, and the checkout state directory -- lives **outside
the working tree**. The one exception is `--update-timings`, which
deliberately rewrites the committed `tests/parallel/timings.json`
(5.2); it executes no tests, takes no snapshot, and never runs inside
another mode's run (round 7, O1). Everything else is placed as follows:
- local run directory: `tempfile.mkdtemp(prefix="wm-run-")` under the
  system temp dir, or `--results DIR` if given; printed in the report
  and kept after a failed run for inspection;
- CI: `$RUNNER_TEMP/plan.json` and `$RUNNER_TEMP/out/` (5.10);
- timing history: `$XDG_CACHE_HOME/workflow-manager/` (5.2);
- checkout state (the run lock and the barrier marker, 5.9):
  `<git dir>/wm-verify/`, where `<git dir>` is `git rev-parse
  --absolute-git-dir` -- the *per-worktree* git directory (`.git/` for
  the main worktree, `.git/worktrees/<name>/` for a linked one), so two
  linked worktrees never share it, and `git status` never lists it.
Every path-taking flag resolves its argument and refuses (usage error,
exit 2) a path inside the repository root, so no operator choice can put
an output where the digest reads. No `.gitignore` change is needed or
made. `tree_digest` is also computed only once, before anything is
written, and the post-run check (5.9) re-computes it from the same
function, so the tool's own writes are outside both computations by
construction; section 6 "CI" asserts that the digest a CI shard
computes, with `plan.json` and results placed where 5.10 puts them,
equals the plan job's.

### 5.7 `D-Isolation`: per-unit execution environment

Every chunk runs in its **own process** (`python3 -m parallel.unit ...`
for host chunks, cwd `tests/`, the same interpreter; frozen chunks
through `frozen_runs.execute`), in a new session (`start_new_session`) so
a timeout kills the whole process group. Per chunk:

| resource | isolation | evidence it suffices |
| --- | --- | --- |
| disposable repositories, worktrees | already per-test/per-class `tempfile` directories (`mkdtemp`/`TemporaryDirectory` -- collision-free by construction); linked worktrees are created as siblings inside those directories (`add_worktree`) | section 3.3 audit |
| `TMPDIR` | a private `<run>/tmp/<chunk>/` (the run directory is outside the checkout, 5.6), so leaked scratch is attributable and removed after the chunk; subprocesses that replace `env` wholesale (`TestCliDrivesTheSameOperations`, frozen `env={"PATH": ...}` calls) fall back to `/tmp`, which is still collision-free (`mkdtemp`) -- `TMPDIR` is for attribution and cleanup, not the safety argument | section 3.3 |
| Git configuration | unchanged from today: frozen runs already get `GIT_CONFIG_GLOBAL=/dev/null`/`GIT_CONFIG_SYSTEM=/dev/null` (`support.run_suite`), host tests set identity per repository; global config is read-only, so concurrency adds no hazard | section 3.3 |
| Workflow locks (`WORKFLOW_STATE.lock`, lifecycle lock, amendment witness) | all live inside each disposable repository's `.ai-review/runtime/` or git common dir, never global | section 3.3 grep |
| env vars | executor passes today's environment minus `PYTHONPATH`/`FORCE_COLOR`, plus `PYTHONDONTWRITEBYTECODE=1`, `PYTHON_COLORS=0`, `TMPDIR`; `WM_FROZEN_RECORDS` and `WM_FROZEN_CONTEXT` only in phase B (5.5) | |
| install/bootstrap destinations | every `bootstrap`/`update` target is inside a per-test temp directory; the only writes to the real repository tree are declared resources (5.8) | section 3.3 |
| ports / servers / daemons | none exist in any suite (grep in section 3.3) | |
| bytecode | `PYTHONDONTWRITEBYTECODE=1` for every chunk, and `sys.dont_write_bytecode = True` as the first statement of `run_all.py`, before it imports anything, so the executor's own imports write nothing either (the ignored `__pycache__` directories listed in 3.3 show something writes into the guarded trees today; they are gitignored, but concurrent writers are removed rather than argued safe). A subprocess that replaces `env` wholesale (3.3: the two `python3 -m workflow_manager` helpers) does not inherit the variable; its `.pyc` write into `src/workflow_manager/__pycache__/` fails under the write barrier, which CPython ignores silently, so it leaves no file. That is why every mode that executes units applies the barrier, CI included (5.9 "Guards per mode"). This differs from direct mode's frozen runs; 5.5 states why that is benign | |

**Load-sensitive frozen tests.** `workflow_state_test.py` contains
cross-process race tests with 15 s deadlines and `hold_seconds` sleeps
(`wf-race-worker`, `wf-amend-race`, `wf-lifecycle-holder`). They are not a
shared-state hazard but can flake under CPU oversubscription. Mitigation:
the local worker cap never exceeds `os.cpu_count()`, and CP7's acceptance
requires repeated green parallel runs at the maximum worker count
(section 7). A flake is a finding to investigate, never a retry.

### 5.8 `D-Resources`: declared non-overlappable tests

`tests/parallel/resources.json` declares every resource and every unit
that needs one exclusively. The file and its loader,
`tests/parallel/resources.py` (`load(repo_root, host_unit_ids) ->
Resources`, reading `<repo_root>/tests/parallel/resources.json` and
validating exclusive units against the host unit ids its caller passes
-- the host inventory it already discovered -- so the loader never runs
discovery itself), are **CP1's** (round 5, I1). Every reader goes
through that loader: the planner's placement (5.4 step 4, CP3),
`isolation`'s A0 ordering and barrier lifting, and the static lint (both
CP4).

**Each resource names the guarded trees it covers, machine-readably
(round 7, I3).** `resources.py` also owns `GUARDED_TREES =
("distribution/", "migration/", "src/", "tools/")`, the one list of
trees the write barrier covers (5.9); `isolation` imports it rather than
restating it. A resource is `{"paths": [...], "description": "..."}`,
and each entry of `paths` must be exactly one member of `GUARDED_TREES`
-- the barrier locks and lifts whole trees, so no sub-path form exists.
`ResourcesFileError` is raised on: a wrong `schema_version`; a resource
that is not an object with exactly those two keys; an empty `paths`
list; a `paths` entry that is not a string, is absolute, contains a
`..` component, or is not a member of `GUARDED_TREES`; a tree listed
twice within one resource, or claimed by two resources (so each guarded
tree maps to at most one resource, and lifting is never ambiguous); an
empty `description`; an exclusive entry naming an undeclared resource,
with an empty `resources` list, or with an empty `reason`; and an
exclusive unit id absent from `host_unit_ids`. During A0 the executor
lifts the barrier for exactly the union of the `paths` of the running
exclusive unit's resources (5.9), and nothing infers a tree from a
resource's name or description.

```json
{
  "schema_version": 1,
  "resources": {
    "repo:distribution": {
      "paths": ["distribution/"],
      "description": "the real repository's distribution/ tree; every unit reads it (find_release, build_release --check, migrate.py --check)"
    }
  },
  "exclusive": {
    "host:test_amendment_update_path.py::TestMigrateDoesNotDeleteASiblingAuthoredRelease": {
      "resources": ["repo:distribution"],
      "reason": "test_a_fresh_regeneration_leaves_authored_siblings_untouched runs tools/migrate.py without --check, which shutil.rmtree()s and rebuilds the real distribution/workflow/2.3.1/ before restoring it via git; a concurrent reader saw no 2.3.1/manifest.json (docs/ACTIVE_MILESTONE.md CP9 process note)"
    }
  }
}
```

- Every unit implicitly *reads* every declared resource; a unit listed
  under `exclusive` is the only thing running while it runs.
  **Serialization is by phase ordering, not by lock contention** (round
  2, I1): locally, every exclusive chunk runs in pre-phase **A0** --
  one at a time, with no other chunk process alive -- and the phase-A
  worker pool starts only after A0 has finished. No per-resource
  `LOCK_SH`/`LOCK_EX` is taken, so an exclusive unit can never starve
  behind a stream of shared acquisitions (`fcntl.flock` has no writer
  preference), and its wait is zero by construction. The cost is A0's
  duration added once to the local makespan; the one declared unit is a
  non-matrix host class, and every such class measured under 6 s (3.4).
  CP5's phase-A evidence measures it and the report prints it.
- Cross-*run* exclusion is the checkout run lock (5.9): no second
  `run_all.py` can start in the same checkout while a run is live, so
  A0's exclusive window cannot overlap another run's readers either --
  the collision the CP9 process note actually records (two concurrent
  `run_all.py` invocations, `--fast` and the full run).
- Every chunk's start and end time, and A0's window, are logged in the
  result records and summarised in the report (auditable
  serialization); the aggregator re-checks from those timestamps that no
  exclusive chunk's window overlapped any other chunk's.
- In CI each shard is its own checkout on its own runner, so cross-shard
  contention cannot occur; within a shard, its exclusive chunks run
  first (5.4), before the rest of the shard, under the same rule.
- Section 3.3's audit table is the evidence that this is the only
  exclusive unit today. 5.9 states what keeps it honest mechanically, and
  where that stops.

### 5.9 `D-Local-Executor` and the repository-integrity guard

`python3 tests/run_all.py [--jobs N] [--select ...]`:

- (pre-lock) parse arguments, resolve every path flag and refuse one
  inside the repository root, and check each `--select` spec's syntax
  (5.1's five forms). These steps read nothing but `argv` and `git
  rev-parse --show-toplevel`/`--absolute-git-dir`, and write nothing, so
  their refusals (argparse usage errors, `PathInsideRepositoryError`,
  `SelectSyntaxError`) happen before, and never touch, the lock;
0. acquire the **checkout run lock** and, only then, recover any barrier
   a dead run left behind (below);
1. snapshot the repository tree (`tree_digest` inputs, plus the path and
   content-hash list of every ignored file under `distribution/`,
   `migration/`, `src/`, `tools/`, `tests/`, **`__pycache__` included**
   -- round 2, O2: the executor and every chunk run with bytecode
   writing off (5.7), so any new `__pycache__` there is a real write) --
   *before* discovery, so discovery's own imports are inside the window;
2. discover -> select -> plan (profile `local`, bounds from
   `config.json`, `n = --jobs` or adaptive), into the run directory
   outside the checkout (5.6);
3. apply the **write barrier** below; it stays applied through step 5;
4. phase A: pre-phase A0 runs the exclusive chunks (5.8), alone and one
   at a time; then one worker per shard runs its shard's remaining
   chunks in plan order, with per-chunk timeout (`max(600, 5 x
   estimate)`, hard cap 3600 s) and a per-chunk log file;
5. phase B: matrix host classes in merged mode;
6. restore the barrier; re-snapshot and compare with step 1. Any
   difference fails the run (exit 2) and names the chunks whose
   execution windows overlapped the run;
7. append observed timings to the user cache; print the report (5.11);
   release the run lock.

**Checkout run lock (round 2, B1).** Every `run_all.py` mode (a local
run, `--list`, `--plan-only`, `--run-shard`, `--aggregate`,
`--update-timings`, `--restore-barrier`, and `--fast` however
`D-Fast-Flag` resolves), from CP5 onward (INV-6), first takes `fcntl.flock(LOCK_EX | LOCK_NB)` on
`<git dir>/wm-verify/run.lock` (5.6: per worktree, outside the working
tree). If it is held, the invocation refuses at once with exit 2 and
prints the holder recorded in the lock file (executor pid, start time,
and the process-group ids of its live chunks); it never waits and never
touches the barrier. Every refusal after the pre-lock step (an unknown
name in a `--select` spec, a plan or tree digest mismatch, a missing
shard result) therefore happens under the lock. Consequences:
- two runs in one checkout can never overlap, so a reader of one can
  never see the other's A0 window, and no run's step-1 snapshot can land
  inside another run's exclusive window;
- linked worktrees each have their own git dir, hence their own lock
  and marker; they run concurrently and never see each other's barrier
  (each barrier covers only its own worktree's directories);
- the lock file descriptor is passed to every chunk process
  (`pass_fds`), so the lock stays held until **the last chunk process**
  has exited, not merely the executor. If the executor is SIGKILLed
  while chunks are still running, the checkout stays locked until those
  orphans exit; the refusal message names their process groups (`kill
  -- -<pgid>`). A chunk's own `subprocess` children do **not** inherit
  the fd (their default is `close_fds=True`), so the lock does not cover
  them (round 4, O3). They are covered by process-group handling
  instead. Every chunk waits on its children today. A timeout kills the
  chunk's whole process group (5.7). And once a chunk process has exited,
  for any reason, `isolation.run_chunk` sends `SIGKILL` to that chunk's
  process group before it returns, so no descendant outlives its chunk
  (T-ISO-1).
- The lock covers `run_all.py` only. Unchanged direct entry points
  (`python3 tests/<module>.py`, `python3 -m unittest ...`) take no
  lock; running one alongside a live `run_all.py` in the same checkout
  is outside this guarantee, as it is today. The barrier still refuses
  such a process's structural writes to the guarded trees.

**Guards per mode (round 3, O2).** Every mode takes the lock (step 0).
The other guards depend on what the mode runs. This table, like INV-6,
binds from CP5. CP1-CP4's interim direct-mode path takes none of these
guards (INV-6, round 5 O3):

| mode | snapshot (steps 1, 6) | write barrier (steps 3-5) | why |
| --- | --- | --- | --- |
| local run (any `--jobs`, `--fast`) | yes | yes | executes units |
| `--run-shard` (CI) | yes | yes | executes units in a fresh checkout |
| `--aggregate` (CI) | yes | yes | executes phase B |
| `--list`, `--plan-only` | yes | no | runs discovery only (import, never run, bytecode off, 5.1) |
| `--update-timings`, `--restore-barrier` | no | no | execute no units. `--update-timings` writes exactly one working-tree file, the committed `tests/parallel/timings.json` (5.2), which is its purpose and the one exception to 5.6's outside-the-tree rule; `--restore-barrier` changes only directory modes (round 7, O1) |

In CI the barrier matters for more than safety. A fresh checkout has no
ignored files, so an ignored file created by any unit shows up in the
step-6 comparison. The foreseeable case is the two `python3 -m
workflow_manager` helpers (3.3) writing `src/workflow_manager/__pycache__/`.
Under the barrier that write fails with `EACCES`, which CPython ignores,
so no file appears and the run stays green. Without the barrier, the run
would exit 2 on a false integrity failure. T-CI-5 covers it.

**Tests and the lock (round 3, I1).** `tests/test_parallel_runner.py` runs
as a chunk of `python3 tests/run_all.py`, so the real checkout's lock is
held (by fd inheritance) the whole time it runs. A test that opened that
lock again would get `RunLockHeldError`, so it would either fail under
`run_all.py` while passing when the module runs directly, or pass for the
wrong reason when it expects exit 2. Three rules close this:
- **Nothing in `tests/parallel/` reads a module-level repository root.**
  `run_all.py` is a thin shim:
  `sys.exit(parallel.cli.main(sys.argv[1:], repo_root=<derived from
  __file__>))`. The inventory, lock, snapshot, barrier, planner and
  executor all take `repo_root` as an argument. No flag or environment
  variable can point a gate run at another checkout.
- **Every test that goes through the lock runs against a scratch
  checkout, never the real one.** The shared helper
  `scratch_checkout(...)` in `tests/test_parallel_runner.py` does the
  following:
  - `git init`s a `tempfile` directory, so it has its own per-worktree
    git dir and hence its own lock;
  - copies verbatim (round 4, O1): `tests/run_all.py`,
    `tests/parallel/` except `matrix.py` and `resources.json` (both
    replaced below), `tests/frozen_runs.py`, `tests/support.py` (which
    `frozen_runs` imports for `run_suite`/`failing_tests`), and all of
    `src/workflow_manager/` (the fixture builders and `find_release`,
    `src/workflow_manager/release.py:239`, which the frozen-chunk cases
    run for real);
  - writes a synthetic release `distribution/workflow/0.0.1/`. Its
    payload `scripts/` holds a tiny frozen suite: two classes, plus a
    variant with one failing test. It also holds the state templates the
    fixture builders place. The helper then generates `manifest.json`
    from the files it just wrote. That includes every field `Release`
    reads (`workflow_version`, `upstream`, `artifacts` with each file's
    `sha256`/`size`/`executable`/`category`, and `templates`), so the
    digests match by construction;
  - writes `migration/classification.json` and
    `migration/portability_exceptions.json` in the shape `support` reads
    at import (`tests/support.py:18-21`), with a `by_version` entry for
    `0.0.1` only, and an empty `tools/` directory (a guarded tree);
  - writes synthetic `tests/test_*.py` host modules, including one
    matrix-style host class for `(0.0.1, conformance)` with the same
    direct/merged `setUpClass` split as the real 15;
  - replaces the data-only `tests/parallel/matrix.py` with one whose
    `FROZEN_MATRIX` names only that class and whose `CI_SUITES` is a
    literal for `0.0.1`, not a view of `support`'s. 5.1 reads it from the
    scratch root in the discovery subprocess, so the real table is never
    consulted;
  - writes a synthetic `tests/parallel/resources.json` in place of the
    real one (round 7, I2). The real declaration's exclusive unit
    (`TestMigrateDoesNotDeleteASiblingAuthoredRelease`) is not in the
    scratch host inventory, so copying it would make the scratch
    checkout fail its own loader. The default synthetic declaration has
    one resource, `repo:distribution` with `paths: ["distribution/"]`
    (the tree the synthetic release lives in), and one exclusive unit,
    `host:test_scratch_exclusive.py::TestScratchExclusiveWriter`, a
    synthetic host module the helper also writes. A test that needs a
    different declaration (none, or several exclusive units) passes it
    through the helper's `resources=` argument, and the helper refuses
    one that fails `resources.load` against the scratch's own host
    inventory, so every scratch checkout is valid by construction;
  - commits.

  CP4 builds the parts its function-level tests need, and CP5 completes
  the rest (section 8). The helper refuses a root that resolves to, or has the same `git
  rev-parse --absolute-git-dir` as, the real `REPO_ROOT`. In-process
  tests call `cli.main(argv, repo_root=scratch)`. Subprocess tests run
  `python3 <scratch>/tests/run_all.py`.
  Only the pre-lock refusals may be tested against the real checkout,
  because they never reach the lock. T-INV-5 tests the pure selector
  in-process; its CLI form is T-EXE-6(c). Every CLI or subprocess test
  (T-EXE-1..5, T-EXE-8..11, T-CI-2/-3/-5) uses a scratch checkout. The
  CP4 function-level tests that take the lock or apply the barrier
  (T-ISO-5/-7/-8/-11/-12/-13/-14) call the `isolation` functions with
  `repo_root` set to a scratch checkout, or to a linked worktree of one
  made by the helper `scratch_worktree(scratch)`, never the real one
  (round 4, I1).
- **Accepted root forms, mechanically checked (round 5, O1).** T-EXE-7's
  AST scan of `tests/test_parallel_runner.py` accepts exactly these as
  the `repo_root` of a lock-reaching call (`cli.main`,
  `isolation.acquire_run_lock`, `apply_barrier`, `restore_barrier`,
  `recover_barrier`) or as the path of a subprocess naming `run_all.py`:
  - a name bound to a `scratch_checkout(...)` result;
  - a name bound to `scratch_worktree(<accepted>)` (T-ISO-13, T-EXE-11(c));
  - `<accepted> / <literal parts>` (for example `scratch / "tests" /
    "run_all.py"`);
  - a parameter named `scratch_root` of a module-level function in the
    same module, when every call site of that function in the module,
    including `multiprocessing` `Process(target=fn, args=(...))`, passes
    an accepted value at that position.

  Helper-process code (T-ISO-8, T-ISO-11 and T-EXE-6(a)'s lock holders)
  must be a module-level function of `tests/test_parallel_runner.py`,
  started through `multiprocessing.get_context("spawn").Process`. It is
  never a `python3 -c` string. So the scan reads it like any other code,
  and the scan fails on any string constant that names one of the
  lock-reaching functions. The only exceptions are the pre-lock refusal
  tests, listed by name in the scan.
- **Refusals are distinguishable.** Every exit-2 refusal prints
  `run_all: error[<ErrorName>]: ...` as its first stderr line. Every
  refusal test asserts that tag, in-process the exception type, as well
  as the exit code, so a test aimed at `PlanDigestMismatchError` fails if
  it gets `RunLockHeldError` (T-EXE-6).

**What the guard catches, stated truthfully.** The known writer
(`TestMigrateDoesNotDeleteASiblingAuthoredRelease`) restores the tree
before it exits, and so would any undeclared writer built the same way;
the step 1/6 comparison sees **persistent** changes only and would miss
exactly the transient rmtree-then-restore that caused the CP9 collision
(3.3). So the guard has three layers, each with a stated scope:

| layer | catches | misses |
| --- | --- | --- |
| **write barrier** (steps 3-5) | any *transient or persistent* create, delete or rename inside the guarded trees -- by any process, including subprocesses and `install.update`-style helpers pointed at `REPO_ROOT` | in-place overwrite of an existing file's content (the file mode is untouched); writes by a process running as root |
| **before/after snapshot** (steps 1, 6) | any *persistent* change, including in-place overwrites and ignored files | a transient in-place overwrite restored before the run ends |
| **static lint** (CP4) | writer patterns in `tests/*.py` source, including the in-place overwrites the other two miss | writers it cannot see syntactically (dynamic paths, writes inside helper code outside `tests/`) |

*Write barrier.* For steps 3-5 the executor removes write permission
(`chmod u-w`, never touching file modes) from every **directory** under
`distribution/`, `migration/`, `src/` and `tools/` (the trees the audit
found read by nearly every unit and written by the one declared unit;
`tests/` is excluded because Python and the tooling never need to write
there during a run -- the run directory is outside the checkout and
bytecode is off). A create/delete/rename there then fails at once with
`PermissionError`/`EACCES` in the writing test, which surfaces as a
named test failure (exit 1) instead of a silent collision in some other
unit. The four trees are `resources.GUARDED_TREES` (5.8). During A0 the
executor lifts the barrier for exactly the union of the `paths` declared
by the running exclusive unit's resources (5.8; round 7, I3), and
re-applies it before the next chunk starts; nothing else is running in
that window (5.8).

*Barrier state and recovery (round 2, B1).* Directory modes are not
tracked by git, so the barrier never shows in `git status`. Before the
first `chmod` the executor writes `<git dir>/wm-verify/barrier.json`
(the original mode of every guarded directory, the executor pid and
start time; written to a temporary name, `fsync`ed, then renamed), and
it deletes the marker only after the last restore. It restores in a
`finally` and on `SIGINT`/`SIGTERM`. Recovery after a kill is tied to
the lock, never to the marker's mere existence: a start finds and acts
on a marker **only after step 0 has acquired the run lock**, which it
can do only when every process of the marker's run has exited (the lock
is held until the last one does). So a start can never lift a live
run's barrier, and a run never records another run's `u-w` modes as
originals: it records originals only after recovery, while holding the
lock that excludes every other run. As a safety net, if a guarded
directory already lacks `u+w` when no marker exists, the executor warns,
names it, and restores it to the recorded mode at the end like any
other. `python3 tests/run_all.py --restore-barrier` performs just step 0's
recovery and exits (0 when nothing was left, refusing with exit 2 while
a run is live); the barrier-apply log line prints that command, so a
checkout left `u-w` after a SIGKILL with no later run is recoverable by
name rather than through an opaque `EACCES` from `git checkout`.
The same log line also warns the developer (round 3, usability). While
the run is live, the guarded trees are read-only to them too. Saving a
new file, or an editor's atomic-rename save, under `src/`, `tools/`,
`migration/` or `distribution/` fails with `EACCES`. So does a `git
checkout`/`switch`/`stash`/`pull` that touches those trees, and a branch
switch can be left half-applied. CP5's "Verification execution" section
in `docs/ARCHITECTURE.md` states the same.
Running as root disables the barrier's effect; the executor detects
`os.geteuid() == 0` and refuses unless `--allow-root` is given, which
the report then flags.

*The barrier propagates into copies (round 2, I2).* `shutil.copytree`
calls `copystat` on every directory it creates, so a copy of a guarded
tree made during the barrier arrives with `u-w` directories.
`tests/test_bootstrap.py:613-618`'s `damaged_copy` does exactly this
with the real `distribution/workflow/2.3.1/`. Its four callers
(`tests/test_bootstrap.py:629-651`) only overwrite an existing file in
the copy (file modes are untouched, so that works) and keep the copy in
a `TemporaryDirectory`, whose `cleanup` resets permissions on
`PermissionError`, so they pass. What this means:
- **Limitation, stated:** a test that copies a guarded tree during a run
  and then creates, deletes or renames inside the copy fails with
  `EACCES`. That is a false failure caused by the barrier, not a
  detected writer. No test does this at the base commit (the audit
  above). A future test that needs to must restore `u+w` on its own
  copy, and the "Verification execution" section CP5 adds to
  `docs/ARCHITECTURE.md` says so.
- **Handled in cleanup:** the executor's per-chunk `TMPDIR` cleanup
  first walks the tree and adds `u+rwx` to every directory, then
  removes it, so an `mkdtemp` copy cleaned with plain `shutil.rmtree`,
  or not cleaned at all, never leaves undeletable residue. Residue is
  still reported against its chunk (T-ISO-3) before it is removed.
- **Tested:** T-ISO-12.

*Static lint (CP4) and its declared completeness.* It is a heuristic
over `tests/*.py` source, not a proof. It flags, unless the enclosing
unit is declared in `resources.json`: a subprocess argv that names
`tools/migrate.py` or `tools/build_release.py` without `--check`; any
call to `install.bootstrap`/`install.update`/a `tools` entry point whose
destination argument is `REPO_ROOT` or an expression derived from it;
any `shutil.rmtree`/`os.remove`/`unlink`/`write_text`/`write_bytes`/
`open(..., "w"|"a"|"x")` whose path expression is rooted at `REPO_ROOT`;
and any `shutil.copy*`/`rename`/`replace` whose **destination**
argument (the second positional argument, or `dst=`) is rooted at
`REPO_ROOT` (round 2, O3: a copy *from* the real tree, such as
`damaged_copy`'s `copytree(release.root, dest)`, is a read and is not
flagged). It cannot see a write made by a
helper script or library function outside `tests/` given an innocuous
path, nor a path assembled dynamically. Those are left to the write
barrier (structural writes) and the snapshot (persistent writes); the
one residual gap -- an undeclared *transient in-place overwrite* by code
the lint cannot see -- is stated in section 11 as a residual risk, not
claimed covered.

`--jobs 1` is the serial reference (INV-6). Direct module execution
(`python3 tests/test_bootstrap.py`, `python3 -m unittest ...`) keeps
working unchanged for any module, including the matrix modules in direct
mode.

### 5.10 `D-CI`: dynamic matrix from the plan

A **new** workflow `.github/workflows/workflow-manager-verify.yml`
(this repository's own verification; the existing
`workflow-conformance.yml` is `workflow_manager`-managed -- recorded in
`.workflow-manager/installation.json` -- and stays untouched so
`workflow_manager verify` does not report drift):

- `plan` job: checkout; `actions/setup-python` 3.12; fetch the public
  upstream `RodrigoFAbreu/repflow-android` at the frozen commit
  `1f954fbb...` into `$HOME/Workspace/repflow-android` (the path
  `tools/migrate.py`'s `DEFAULT_UPSTREAM` and `tests/support.py`'s
  `UPSTREAM` default to, so no test is skipped for lack of it);
  `python3 tests/run_all.py --plan-only --profile ci --out
  "$RUNNER_TEMP/plan.json"`; write `shards=[0..n-1]` to
  `$GITHUB_OUTPUT`; upload `plan.json`. (Python 3.12 here versus 3.14.7
  locally is part of the 3.5 speed factor; `timings.json`'s separate
  `ci` profile absorbs it.)
- `shard` job: `strategy.matrix.shard: ${{ fromJSON(needs.plan.outputs.shards) }}`,
  `fail-fast: false`; same setup; download `plan.json` into
  `$RUNNER_TEMP`; `python3 tests/run_all.py --run-shard
  ${{ matrix.shard }} --plan "$RUNNER_TEMP/plan.json" --results
  "$RUNNER_TEMP/out/"`; upload that `out/` (records, logs, timings) with
  `if: always()`. Nothing is written into the checkout, so the shard's
  `tree_digest` equals the plan job's (5.6).
- `aggregate` job: `needs: [plan, shard]`, `if: always()`; checkout
  and `actions/setup-python` 3.12, as in the other jobs; no upstream
  fetch, because phase B's matrix host classes never call
  `upstream_available` (round 3, O2). Download plan
  and every shard's results into `$RUNNER_TEMP`; `python3
  tests/run_all.py --aggregate "$RUNNER_TEMP/out/" --plan
  "$RUNNER_TEMP/plan.json"` verifies the plan, builds the merge contexts
  from it (5.5; never from the downloaded records), runs phase B and the
  completeness checks, writes the
  report to `$GITHUB_STEP_SUMMARY`, and its exit code is the verdict.
  **`aggregate` is the one required status check** (matrix job names are
  dynamic; a missing/cancelled shard makes `aggregate` fail by INV-7).
- `--run-shard` and `--aggregate` apply the lock, the snapshot and the
  write barrier exactly as a local run does ("Guards per mode", 5.9).
- Triggers: `pull_request` and `push` to `main` (the existing workflow's
  triggers), plus `workflow_dispatch`; a `concurrency` group per ref with
  `cancel-in-progress` for PRs. Billing implication in `D-CI-Cost`
  (section 5.13).

There is no hand-written shard allocation anywhere: the matrix is the
plan's shard list.

### 5.11 `D-Aggregation`: verdict, report and exit codes

- Exit `0`: every planned atomic unit reported, every test passed (skips
  are reported with reasons, exactly as unittest reports them today).
- Exit `1`: at least one test failed or errored (today's only failure
  code -- automation keyed on non-zero keeps working).
- Exit `2`: infrastructure fault -- incomplete or duplicated results,
  plan/tree digest mismatch, structural merge refusal (5.5), a chunk the
  executor killed on timeout or whose runner died without writing its
  record, repository-integrity violation (5.9 snapshot), another run
  holding the checkout run lock (5.9), a refused root run, usage error
  (argparse's own default code, kept). A fixture build failure is a
  record with a non-zero outcome (5.5), hence exit 1, as today. A frozen suite that crashes,
  errors in `setUpClass` or loses tests is a *test* failure (exit 1),
  never reclassified to 2 (INV-7). When a run has both, exit 2 wins
  (the run as a whole is not trustworthy), and the report still lists
  every test failure it did observe.
- Report: first the existing per-module lines
  (`ok  test_x.py   123.4s  Ran N tests ... OK` -- same columns; seconds
  are summed chunk time, with wall time printed separately), then for each
  failure: the unit id, failing test names, the log path (locally) or
  artifact name (CI), the last 6000 characters of output (today's limit),
  and a one-line reproduction command:
  `python3 tests/run_all.py --jobs 1 --select '<unit id>'` for a host
  unit. For a frozen chunk the command has one `--select` per class of
  the chunk, plus `--whole-groups` (round 3, O4): `python3
  tests/run_all.py --jobs 1 --whole-groups --select '<frozen class id>'
  --select ...`. The classes of one chunk form one execution group, and
  `--whole-groups` (a debugging flag that never changes the selection)
  stops the planner splitting a group. So the command rebuilds the same
  fixture and runs exactly that chunk's classes in one invocation. No
  chunk-id grammar is added, since a chunk id is only meaningful relative
  to one plan. Then the shard summary (`n`, predicted vs actual loads, A0's
  window, defaulted/orphaned/drifted timing entries).
- Machine-readable `results.json` (per-unit outcome, duration, test ids,
  failing ids) for CI and `--update-timings`.

### 5.12 `D-Fast-Flag` and compatibility with existing commands (flagged for the user)

- `python3 tests/run_all.py` (no flags) remains the full verification and
  the gate command every document names. Its exit contract is kept
  (5.11). Its default becomes parallel (`--jobs auto`).
- Direct module runs (`python3 tests/<module>.py`, `python3 -m unittest
  <module>.<Class>`) are unchanged.
- **`--fast` is the one conflict with the brief.** It exists today and is
  named in `CLAUDE.md` and `README.md`; it is a coverage tier (it skips
  four suites). Proposed: keep it for one release of this tooling as a
  **deprecated alias** for `--select` of its eight modules, printing
  "targeted selection -- not a verification gate", and remove the tier
  wording from `CLAUDE.md`/`README.md` in favour of "run what you touched
  with `--select`; gates run `python3 tests/run_all.py`". The alternative
  is to delete it outright. This plan does not decide silently: the plan
  reviewer/user chooses; the default above is what CP5 implements unless
  told otherwise.
- **An existing assertion depends on this decision (round 3, I2).**
  `tests/test_workflow_2_6_0_hardening_disposable_repo.py:1425-1426`
  (`test_the_repository_level_guards_are_still_registered`) asserts that
  the literal `"test_amendment_update_path.py"` appears in
  `run_all.py`'s source. Its purpose (v2.3.1-002, and the comment at
  `tests/test_amendment_update_path.py:444-450`) is that the disposable
  update-path suite runs on every fast run. After CP5, `run_all.py` is a
  thin shim (5.9), so the literal leaves it under **either** outcome. The
  assertion would then fail, or pass vacuously if a leftover string kept
  it alive. CP5 therefore replaces it under either outcome, as a
  declared, reviewed assertion change (section 8), with an assertion over
  the same fact that no longer depends on source text:
  - *both outcomes:* the full selection's inventory
    (`parallel.inventory.discover(REPO_ROOT)`, host part) contains every
    host class of `test_amendment_update_path.py`. Every gate runs the
    full selection, so this is the "runs on every gate run" guarantee.
    Under "no tiers" it is the meaningful one;
  - *deprecated-alias outcome only:* in addition, the `--fast` alias's
    resolved selection (`parallel.cli.FAST_ALIAS_SELECTION`, resolved
    through the same selector) contains those classes too, so the
    alias still runs the suite for as long as the alias exists;
  - *deletion outcome:* the second clause is dropped along with `--fast`.

  **Comments, under either outcome (round 4, O2).** Two comments go stale
  whichever way `D-Fast-Flag` resolves, because `FAST_SUITES` leaves
  `run_all.py` under both. They are
  `tests/test_amendment_update_path.py:444-450` ("This suite is in
  `run_all.py`'s `FAST_SUITES`, so it runs on `python3 tests/run_all.py
  --fast`") and
  `tests/test_workflow_2_6_0_hardening_disposable_repo.py:1423-1424`
  ("still runs on every fast run"). CP5 rewrites both unconditionally,
  as comment-only edits:
  - *alias outcome:* "this suite is in the full inventory, so every gate
    run executes it, and in `parallel.cli.FAST_ALIAS_SELECTION`, so the
    deprecated `--fast` alias runs it too";
  - *deletion outcome:* "this suite is in the full inventory, so every
    gate run executes it".

  The v2.3.1-001 half of the same test (the `portability_exceptions.json`
  and `TestBootstrappedTarget260` checks) is unchanged.

### 5.13 `D-CI-Cost` (flagged for the user)

`RodrigoFAbreu/workflow-manager` is a **private** repository, so GitHub
Actions minutes are billed per job, rounded up per job. Today no CI job
runs `tests/` at all (the only workflow is the managed frozen-suite job,
~5.5 min). The new pipeline costs roughly `n x (shard wall + ~1 min
setup)` + plan + aggregate per run; section 3.5 estimates it. The trigger
policy in 5.10 is the proposal; the user may prefer `workflow_dispatch` +
`push: main` only, or a smaller `ci_max_shards`. This changes cost, never
coverage.

**Concurrent-job limit (round 3, O5).** GitHub caps concurrently running
hosted jobs per account (20 on the Free plan, more on paid plans). Jobs
over the cap queue, and that adds latency the design cannot remove. The
`plan` and `aggregate` jobs never overlap the shards. The managed
`workflow-conformance.yml` job fires on the same triggers and can.
So `ci_max_shards` is capped at `account_concurrent_job_limit - 1`.
`D-CI-Cost` records the account's plan and limit, which the user
supplies, since the plan tier cannot be read from the repository. It is
stored in `tests/parallel/config.json` as
`ci_account_concurrent_job_limit`, and the planner clamps
`max_shards(ci)` by it (T-PLN-4). On a Free plan the cap is 19, so the
24-shard point of section 3.5 cannot be reached. P-3 then measures at
the cap instead (section 7).

### 5.14 `D-Fixture-Reuse` (second-order; closed by evidence unless CP7 contradicts it)

Section 3.2 measured repository build cost at 0.06-0.11 s per
`conformance`/`target` fixture against a critical path of ~22 s, so a
template-and-copy scheme (build each `(version, fixture)` repository once,
clone per chunk) cannot buy a measurable improvement and would add a
shared artifact to reason about. It is **not** implemented. CP7 measures
the `bootstrapped` fixture's build cost (not yet measured in isolation)
and the per-chunk group overhead from real plans; only if that overhead
exceeds 10 % of the measured critical path does CP7 raise it as a finding
for a follow-up milestone -- never implemented here.

## 6. Equivalence, determinism and fault-injection tests

All new automated tests live in `tests/test_parallel_runner.py` (fast,
synthetic, run by every selection) unless marked **[evidence]**: an
evidence run is too slow for the suite itself, is executed by the named
checkpoint with the committed tooling, and its command, output summary
and verdict are recorded in the checkpoint's ledger entry. Every
refusal test asserts the named error type and exit code, not just
"non-zero".

**Ownership (round 4, I1).** Each test id and evidence item belongs to
the first checkpoint whose registered `depends_on` (section 8) provides
everything it runs. Tests of a CP2, CP3 or CP4 module call that module's
functions directly. Anything that needs the executor, the CLI's modes,
the aggregator or an exit code from `run_all.py` belongs to CP5 (6.5),
which depends on all three. Where a behaviour has both a function-level
form and an executor-level form, each form has its own id in its own
checkpoint.

### 6.1 "Inventory and selection" (CP1; frozen parts CP2; T-INV-6 CP3; T-INV-8 CP1)

| id | checkpoint | test |
| --- | --- | --- |
| T-INV-1 | CP1 (host); CP2 extends it to the frozen inventory | Discovery run twice (and once with `PYTHONHASHSEED` varied, once from a copy of the tree listed in reverse `os.listdir` order via a patched listing) yields byte-identical inventory JSON. |
| T-INV-2 | CP1 (host); CP2 (frozen) | The host inventory equals, as a set of test ids, what `unittest.defaultTestLoader.discover`/`loadTestsFromModule` returns for every `tests/test_*.py`; the frozen inventory's per-suite totals equal `CI_SUITES[version][suite]` for every release (CP2). |
| T-INV-3 | CP2 | Discovery refuses (`InventoryCountError`, in-process) a synthetic suite whose discovered total differs from its pinned count. The test builds its own minimal layout in a temporary directory (round 5, O4): a release payload `distribution/workflow/0.0.1/payload/scripts/` holding one tiny suite, and a literal `tests/parallel/matrix.py` whose `CI_SUITES` pins a wrong count. It calls frozen discovery with `repo_root` set to that directory. It needs no fixture builder, manifest or `scratch_checkout` part, so it depends on nothing past CP1/CP2. The CLI's exit-2 form is T-EXE-6(c). |
| T-INV-4 | CP1 (the three host forms, union of repeated specs); CP2 (the two frozen forms, a matrix host class pulling in all of its frozen classes, the "partial frozen selection" flag) | Grammar: each of the five spec forms of 5.1 selects exactly the expected unit ids; union of repeated `--select`; selecting a matrix host class pulls in all of its frozen classes; a frozen-only selection is flagged "partial frozen selection". |
| T-INV-5 | CP1 (module, class, test); CP2 (version, fixture, suite) | Unknown module, class, test, version, fixture or suite in a spec is a usage error (`UnknownSelectorError` from the selector, in-process), never an empty selection. The CLI's exit-2 form is T-EXE-6(c). |
| T-INV-6 | CP3 (needs 5.2's timing file format and loader) | INV-2 property: the selector's output is byte-identical under no timing file, an empty one, corrupt JSON, a wrong `schema_version`, a file listing only orphaned units, a file with adversarial values (0, negative, NaN, 1e12 seconds) and the real file. |
| T-INV-7 | CP2 (frozen discovery; the snapshot function is CP1's `tree.py`) | Discovery leaves the tree byte-identical, including ignored files under `distribution/` (no new `__pycache__`), using the 5.9 snapshot function (O4). |
| T-INV-8 | CP1 (round 5, I1; resource paths round 7, I3) | Shared contracts. `resources.load(REPO_ROOT, <host inventory unit ids>)` loads the committed `resources.json`; its one exclusive unit is in the host inventory, and `repo:distribution`'s `paths` is `["distribution/"]`. `ResourcesFileError` is raised for a synthetic file (loaded against a synthetic unit-id list) with a wrong `schema_version`, an exclusive entry naming an undeclared resource or with an empty `resources` list, an empty `reason`, and an exclusive unit id absent from the passed ids; and, per 5.8's resource-path rules, for a resource given as a bare string (the revision-6 form), an empty `paths`, a non-string entry, an absolute path, a `..` component, a path outside `GUARDED_TREES` (`tests/`, `distribution/workflow/`, `docs/`), a tree listed twice in one resource, one tree claimed by two resources, and an empty `description`. A valid synthetic file declaring two resources over different trees loads, and `Resources` reports each exclusive unit's tree union. `plan_schema.ChunkDescriptor` round-trips through `to_json`/`from_json` canonically. `shard_chunks` returns each shard's descriptors in stored order and refuses a chunk missing any of the five fields. |

### 6.2 "Merge" (CP2)

Fast mutation tests over synthetic `FrozenRecord`s:

| id | test |
| --- | --- |
| T-MRG-1 | A complete, disjoint record set merges; `ran` sums, `failing` unions, `returncode` is the max, outputs are labelled per chunk. |
| T-MRG-2 | Structural refusals (`FrozenMergeError`): a planned chunk with no record; two records for one chunk; overlapping class sets; a class of the suite in no chunk; a class not in the suite; a record whose class set differs from its planned chunk's; a foreign `tree_digest`, release digest or plan digest (the expected values are synthetic strings in the `MergeContext` passed to `merge`, 5.5); a record flagged as killed on timeout. |
| T-MRG-7 (round 7, I1) | Independent provenance. A complete, internally self-consistent record set (every record carries the same plan digest `P1` and tree digest `T1`, one record per chunk of partition `X`) is refused (`FrozenMergeError`) when merged against a separately supplied context that differs in exactly one of: `plan_digest` (`P2`), `tree_digest` (`T2`), or chunk partition (same classes split as `Y`, so the chunk ids differ). Against the matching context it merges. At host-class level, merged-mode `setUpClass` refuses when `WM_FROZEN_RECORDS` is set but `WM_FROZEN_CONTEXT` is not, when its `(version, fixture)` has no context file, and when the context's `tree_digest` differs from `tree.tree_digest(repo_root)`. `MergeContext` round-trips through `to_json`/`from_json` canonically. |
| T-MRG-3 (I4) | A chunk whose frozen class errors in `setUpClass` (synthetic record: `Ran` excludes that class's tests, one `ERROR`, rc 1) merges **without** refusal; the unchanged `test_every_suite_runs_the_frozen_number_of_tests` and `test_every_frozen_suite_passes` bodies, run against it in merged mode, fail as test failures, not a merge refusal. The executor-level verdict (exit 1, not 2) is T-EXE-1, CP5. |
| T-MRG-4 (I4) | Same for a chunk whose suite crashes on import (no `Ran` line): `ran` is `None`, the count assertion fails with today's "no unittest summary" message, as a test failure. The exit-1 verdict is T-EXE-1, CP5. |
| T-MRG-5 | Every host assertion of the 15 matrix classes, fed a mutated merged view (one extra failing test; one missing test; a stale portability exception; non-empty `bootstrapped` residue; non-empty drift), fails in merged mode exactly as it fails in direct mode fed the equivalent single `CompletedProcess` -- predicate equality, checked per assertion. |
| T-MRG-6 (O4) | A chunk whose fixture builder raises yields a build-error record (`returncode` 1, `ran` `None`, traceback in `output`); the merge accepts it; the unchanged count/pass assertions fail in merged mode as test failures -- today's class for a `setUpClass` builder exception. The exit-1 verdict, and exit 2 for a chunk process killed before writing any record, are T-EXE-1, CP5. |

**[evidence]** run by CP2 through `python3 tests/frozen_runs.py
--evidence` (5.5), all green:
- **E-MRG-1 direct == merged**, for every release x fixture: the 15
  matrix classes in direct mode (today's behaviour) and in merged mode
  over the fixed two-chunk chunking of 5.5 reach identical per-suite
  `ran`, `failing` sets and pass/fail per assertion. The same comparison
  over the planner's default chunking is E-EXE-1's, in CP5 (round 4,
  I1).
- **E-MRG-2 one class per chunk**, for every release x fixture: every
  frozen class in its own fresh repository; merged per-suite results
  equal E-MRG-1's (covers class-order dependence inside a suite).
- **E-MRG-3 full-state residue**, for every release x fixture x suite:
  the 5.5 full-state snapshot diff, in sequential order; the table of
  deltas (expected: all empty) is the `D-Frozen-Run-Fresh-Repo`
  evidence.

### 6.3 "Planner" (CP3)

| id | test |
| --- | --- |
| T-PLN-1 | INV-1 property over randomized (seeded, recorded seed) inventories, timing files and bounds: the multiset union of shard units equals the selection, pairwise intersections are empty. |
| T-PLN-2 | The planner refuses to emit a plan when a (monkeypatched) assignment drops or duplicates a unit. |
| T-PLN-3 | INV-3: the same inputs give byte-identical `plan.json`, across `PYTHONHASHSEED` values and input orderings; tie-breaks on unit id are exercised by equal estimates. |
| T-PLN-4 | 5.3 arithmetic: `n` equals `clamp(ceil(T/target), min, max)`, never more than the chunk count, `--shards` override clamped; `max_shards(ci)` never exceeds `ci_account_concurrent_job_limit - 1`; the critical-path warning appears iff `C > target_shard_seconds`. |
| T-PLN-5 | 5.4 chunking: a group under the split threshold is one chunk; a larger group splits into exactly `k` chunks covering its classes once; host classes never split; with the planner's `whole_groups=True` option (what CP5's `--whole-groups` flag passes) no group splits and the selection is byte-identical; phase-B units get their own assignment, and the predicted makespan equals the sum of 5.4 step 5's terms. |
| T-PLN-6 | LPT: on fixed hand-computed cases the assignment equals the expected one; on randomized cases the makespan is within 4/3 of a brute-force optimum (small n). |
| T-PLN-7 | 5.2 lifecycle: new-unit estimate falls back in the stated order; orphaned and drifted units are reported, never selected or dropped; `timings.update(...)` (what CP5's `--update-timings` calls) keeps the median of the last 5 and serializes canonically; a corrupt file degrades to defaults with a warning. |
| T-PLN-9 (round 5, I1; round 7, I2) | 5.4 step 4, planner-level. The test builds a mutually valid pair in a temporary directory: a minimal synthetic host inventory (a unit-id list, passed to the planner as its inventory input) and a `tests/parallel/resources.json` whose resource has `paths: ["distribution/"]` and whose one exclusive unit is in that inventory; it loads through CP1's `resources.load(tmp, <those ids>)` without error before the planner runs. With that declaration of a synthetic exclusive unit whose estimate is smaller than every other chunk in its shard, the planner puts that unit's chunk **first** in its shard's chunk list, whatever shard LPT assigns it to (varied by estimates). Its descriptor's `resources` names the declared resources, and every shared chunk's `resources` is empty. The written `plan.json` parses through `plan_schema.shard_chunks` with those values. The result is byte-identical across repeats (INV-3). With no exclusive unit declared, the chunk order equals plain LPT. |
| T-PLN-8 | Plan provenance, function-level: `planner.load_plan(path, repo_root)` raises `PlanDigestMismatchError` for a plan whose recorded `plan_digest` does not match its content, and `TreeDigestMismatchError` for one whose `tree_digest` differs from `tree.tree_digest(repo_root)` (CP1) of a temporary git repository. `--run-shard`'s exit-2 refusal is T-EXE-8, CP5. |

### 6.4 "Isolation and integrity" (CP4) -- fault injection, function-level

Every test here calls `tests/parallel/isolation.py` (and CP1's `tree.py`)
directly. None needs the executor, the worker pool, a plan, the CLI or
the aggregator. The executor-level forms, with `run_all.py` exit codes,
are in 6.5 (T-EXE-8..11). A test that takes the run lock or applies the
barrier passes `repo_root` as a `scratch_checkout` or a
`scratch_worktree` of one (5.9), which this checkpoint adds to
`tests/test_parallel_runner.py`. Synthetic plans are built from CP1's
`plan_schema.ChunkDescriptor`, and resources come from CP1's
`resources.load` (round 5, I1).

| id | test |
| --- | --- |
| T-ISO-1 | Timeout: `isolation.run_chunk` on a synthetic chunk that sleeps past its timeout kills its whole process group (a grandchild it spawned is gone too) and returns the `timed_out` outcome, classified as an infrastructure fault. A chunk that exits normally while a grandchild still runs also leaves no survivor: `run_chunk` kills the group on exit (5.9, round 4 O3). |
| T-ISO-2 | Runner crash: `run_chunk` on a chunk process that exits via `os._exit` before writing its record returns the `missing_record` outcome, classified as an infrastructure fault. |
| T-ISO-3 | Orphan `TMPDIR`: files a chunk leaves in its private `TMPDIR` are reported against that chunk and removed. |
| T-ISO-4 (I1) | Serialization, function-level, over synthetic plans built from CP1's `plan_schema.ChunkDescriptor` (not from the planner, round 5 I1): `isolation.phase_a_order(plan)` puts every exclusive chunk into A0, in plan order, ahead of every shared chunk, whatever the exclusive chunk's shard index (varied), including for 1 exclusive unit among 16 shards x 50 shared units; with one shard (the CI case) the exclusive chunk is first. `isolation.check_exclusive_windows(windows)` accepts overlapping shared windows and refuses (`ExclusiveOverlapError`) an exclusive window that overlaps any other, on synthetic timestamps. |
| T-ISO-5 (I2) | **Transient structural writer**: with `apply_barrier` on a scratch checkout's guarded trees, an undeclared synthetic unit run through `run_chunk` that `rmtree`s and restores a directory under a guarded tree fails with `PermissionError` (a named test failure in its record); run with the barrier lifted for its declared resource, as A0 does, it passes. |
| T-ISO-6 (I2) | **Transient in-place overwrite**: an undeclared unit that overwrites and restores an existing file's bytes is **not** caught by the barrier or the snapshot -- asserted, so the documented residual gap stays documented -- and **is** flagged by the static lint when written with a `REPO_ROOT`-rooted path. |
| T-ISO-7 | Persistent writer, function-level: a unit run through `run_chunk` that leaves an ignored file under a guarded tree of a scratch checkout makes `tree.compare(before, after)` report that path, and `isolation.attribute_integrity_diff` names the chunks whose windows overlapped. |
| T-ISO-8 (B1) | Barrier recovery acts only on a dead owner, function-level, in a scratch checkout: a helper process takes `acquire_run_lock`, applies the barrier, spawns a child with the lock fd (`pass_fds`) and is then SIGKILLed with the child still alive. `acquire_run_lock` then raises `RunLockHeldError` naming the child's process group, and every guarded directory stays `u-w`. Once the child exits, `acquire_run_lock` succeeds and `recover_barrier` restores the recorded modes and deletes the marker. `recover_barrier` with no marker is a no-op. `apply_barrier` refuses `RootRefusedError` when `os.geteuid()` (patched) is 0 unless `allow_root=True`. |
| T-ISO-9 | Lint: flags each pattern of 5.9's list in a synthetic module; does not flag a copy whose *source* is `REPO_ROOT`-rooted (`damaged_copy`'s shape); is clean on today's `tests/` apart from the one declared unit. |
| T-ISO-11 (B1) | One lock per checkout, function-level: two processes call `acquire_run_lock` on one scratch checkout. The second raises `RunLockHeldError` at once, never waits, and changes no directory mode; the first's barrier stays applied while the second tries; after the first releases and restores, every mode equals its pre-run mode and no marker remains. |
| T-ISO-12 (I2) | Barrier propagation into copies: under the barrier, `copytree` of a guarded scratch tree into the chunk's `TMPDIR` yields `u-w` directories (asserted, as the documented behaviour); creating a file inside the copy raises `PermissionError` (asserted); overwriting an existing file in the copy succeeds; the `TMPDIR` cleanup then removes the copy completely, with no residue and no error. |
| T-ISO-13 (B1) | Linked worktrees, function-level: in two linked worktrees of one scratch repository, `acquire_run_lock` and `apply_barrier` succeed concurrently; each uses its own `<git dir>/wm-verify/` lock and marker, and neither's barrier or `recover_barrier` touches the other worktree's directories. |
| T-ISO-14 (round 7, I2/I3) | Scratch declarations are valid, and lifting follows `paths`. A default `scratch_checkout`'s synthetic `resources.json` loads through `resources.load(scratch, <the scratch's discovered host unit ids>)`, and its exclusive unit is in that inventory; `scratch_checkout(resources=...)` refuses a declaration whose exclusive unit is not in the scratch inventory. With the barrier applied, lifting for an exclusive unit whose resource declares `paths: ["distribution/"]` restores `u+w` on the directories under `distribution/` only; `migration/`, `src/` and `tools/` stay `u-w`. |

T-ISO-10 (round 2, I1: bounded exclusive wait under a running pool) is
now executor-level and has moved to T-EXE-10 (CP5); its ordering
property stays here in T-ISO-4. There is no CP4 **[evidence]** run: the
real phase A under the write barrier needs the executor and the planner,
so that evidence is CP5's (E-EXE-2, round 4, I1).

### 6.5 "Executor" (CP5)

| id | test |
| --- | --- |
| T-EXE-1 | Exit-code contract on synthetic selections: all pass -> 0; one failing host test -> 1; one frozen chunk with a failing test -> 1; a frozen chunk whose class errors in `setUpClass`, whose suite crashes on import, or whose fixture builder raises -> 1, not 2 (the executor-level verdicts of T-MRG-3/-4/-6); missing record (a chunk killed before writing one) -> 2; digest mismatch -> 2; failure plus infra fault -> 2 with the failure still listed. |
| T-EXE-2 | Report: per-module lines keep today's columns; each failure names the unit, failing tests, log path and a reproduction command; running that command reproduces the same failing set. This includes a failing **multi-class** frozen chunk from a split group: the command has one `--select` per class plus `--whole-groups`, and it runs exactly those classes in one invocation (5.11). |
| T-EXE-3 | `--jobs 1` and `--jobs 4` over a synthetic selection execute identical unit-id sets with identical verdicts; three `--shuffle-seed` values permute execution order but not the verdict. |
| T-EXE-4 | Every path flag (`--out`, `--plan`, `--results`) refuses a path inside the repository root (exit 2). |
| T-EXE-5 | `--fast` behaves per the resolved `D-Fast-Flag`; `python3 tests/<module>.py` and `python3 -m unittest <module>.<Class>` still work unchanged. |
| T-EXE-6 (I1) | Refusal discrimination, in a scratch checkout. (a) With the lock held by a helper process, an invocation aimed at a plan-digest mismatch gets `RunLockHeldError`. The shared refusal assertion used by T-EXE-8/T-CI-3, pointed at that output with `PlanDigestMismatchError` expected, fails. (b) With the lock held, an argparse usage error, an in-repo path flag and a `--select` syntax error are each still reported as themselves (pre-lock ordering, 5.9). (c) With the lock free, each targeted refusal reports its own tag. |
| T-EXE-7 (I1) | Test-tree hygiene. `scratch_checkout` refuses the real `REPO_ROOT` and any root sharing its absolute git dir, and a checkout it returns satisfies `find_release(scratch, "0.0.1")` and `build_conformance_repo` (5.9, round 4 O1). An AST scan of `tests/test_parallel_runner.py` finds no lock-reaching call (`cli.main`, `isolation.acquire_run_lock`, `apply_barrier`, `restore_barrier`, `recover_barrier`) and no subprocess naming `run_all.py` whose repository root is outside 5.9's accepted root forms (round 5, O1): a `scratch_checkout` result, a `scratch_worktree` of one, a literal path under either, or a `scratch_root` parameter that every call site, `multiprocessing` targets included, binds to one of these. It also finds no string constant naming a lock-reaching function. Mutations of the scan's own input (a lock call on `REPO_ROOT`, an unbound `scratch_root` call site, a `-c` string holding `acquire_run_lock`) each make it fail. The scan's only exceptions are the pre-lock refusal tests, listed by name. |
| T-EXE-8 (round 4, I1; was T-PLN-8's CLI half) | In a scratch checkout, `--run-shard` refuses a plan whose `tree_digest` or `plan_digest` does not match, exit 2, tagged `TreeDigestMismatchError`/`PlanDigestMismatchError`. |
| T-EXE-9 (round 4, I1; was the executor halves of T-ISO-1/-2/-7) | In a scratch checkout, a local run whose selection contains a chunk that sleeps past its timeout, one that exits via `os._exit` before writing its record, and (separately) one that leaves an ignored file under a guarded tree each exits 2 and names the chunk; the persistent-writer run fails at step 6 and names the chunks whose windows overlapped. |
| T-EXE-10 (round 4, I1; was T-ISO-10, plus T-ISO-4's aggregator re-check) | Bounded exclusive wait under continuous shared load, through the executor: a plan of 1 exclusive unit plus 16 workers x 50 back-to-back synthetic shared units. The exclusive unit starts before every shared unit and its wait is 0, whatever its shard index (varied); in a single shard (the CI case) it runs first; A0's window is logged. The aggregator re-checks the recorded windows and exits 2 on a record set doctored so that an exclusive window overlaps another. |
| T-EXE-11 (round 4, I1; was the CLI halves of T-ISO-8/-11/-13) | In scratch checkouts: (a) after a SIGKILL of the executor mid-run with a chunk still alive, a new start and `--restore-barrier` both exit 2 naming the live process group and leave every guarded directory `u-w`; once the chunk exits, the next start restores the recorded modes before anything else and deletes the marker; `--restore-barrier` with nothing to restore exits 0; a run as (patched) root without `--allow-root` exits 2. (b) Two concurrent executors in one checkout: the second exits 2 at step 0, before any snapshot, discovery or `chmod`, repeated for every mode (`--list`, `--plan-only`, `--restore-barrier`, a second local run); while the first runs its guarded directories stay `u-w`; afterwards every mode equals its pre-run mode and no marker remains. (c) Two linked worktrees run executors concurrently; both run, and neither's barrier or recovery touches the other worktree. |

**[evidence]** run by CP5:
- **E-EXE-1** full selection with `--jobs 1` and `--jobs auto`, plus
  three `--shuffle-seed` runs: identical executed-id sets, per-suite
  counts and verdicts, and both equal to the direct-mode full run CP2
  recorded (O1). This is E-MRG-1's direct == merged comparison over the
  planner's default chunking (round 4, I1).
- **E-EXE-2** (moved from CP4, round 4, I1) the full phase A of the real
  selection under the write barrier, `--jobs 1` and `--jobs 8`, green --
  proving no legitimate unit other than the declared one writes to a
  guarded tree. Each run also records A0's measured duration, that the
  run directory's `tmp/` is empty after cleanup, and every chunk's
  reported `TMPDIR` residue (expected: none).
- **E-EXE-3** (round 3, I1) `tests/test_parallel_runner.py` green when
  run directly (`python3 tests/test_parallel_runner.py`) and as a chunk
  of the E-EXE-1 full runs, that is, with the real checkout's run lock
  held. The rewritten
  `test_the_repository_level_guards_are_still_registered` is green in
  both too, and a mutation (removing `test_amendment_update_path.py`
  from the inventory input) makes it fail.

### 6.6 "CI" (CP6)

| id | test |
| --- | --- |
| T-CI-1 | Structural checks of `workflow-manager-verify.yml`: the matrix is `fromJSON(needs.plan.outputs.shards)` (no literal shard list); `fail-fast: false`; `aggregate` has `needs: [plan, shard]` and `if: always()`; every tool output path is under `$RUNNER_TEMP`; the upstream fetch pins commit `1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6`. |
| T-CI-2 (I3) | In a scratch clone: compute the plan job's `tree_digest`; place `plan.json` and a results directory exactly where the workflow puts them (a stand-in `RUNNER_TEMP`), then compute the shard's digest: equal. The same with the outputs deliberately placed inside the clone is refused by the path check. |
| T-CI-3 | `aggregate` fails (exit 2) when one shard's results are missing, and when a shard's results come from a different plan digest; and, with the merge context built from `plan.json` (5.5), when a shard supplies a complete, self-consistent record set for a different frozen chunk partition (round 7, I1). |
| T-CI-4 | The managed `.github/workflows/workflow-conformance.yml` still matches its installation-record digest (`workflow_manager verify` reports no drift). |
| T-CI-5 (O2) | In a scratch clone with no ignored files (a fresh CI checkout): `--run-shard` of a synthetic unit that runs a subprocess with `env` replaced wholesale (no `PYTHONDONTWRITEBYTECODE`) importing a module from `src/`. The unit is green, no `__pycache__` appears under `src/`, and the step-6 comparison passes. The same unit with the barrier forcibly disabled leaves the `.pyc`, and the comparison fails with exit 2, which shows the barrier is what keeps it green. `--aggregate` applies the same guards. |

**[evidence]** CP6: one real run on a pushed branch (user push) at the
default `ci_max_shards`, plus the `--shards 1` reference run. The shard
that runs `TestCliDrivesTheSameOperations` must be green with no
integrity failure (O2). Also recorded: the per-job setup times that seed
`ci_job_setup_seconds`, and the account's concurrent-job limit
(`D-CI-Cost`).

## 7. Performance acceptance

All local measurements on the section 3 workstation, from a clean tree
at the implementation head, load noted; median of the stated number of
runs. CI measurements on the real pipeline; wall is from the `plan`
job's start to the `aggregate` job's end. Every run's command, wall
time, verdict and per-shard loads are recorded in CP7's ledger entry
and summarised in `docs/ARCHITECTURE.md`.

| id | measure | runs | acceptance threshold |
| --- | --- | ---: | --- |
| P-0 | Serial baseline: today's `python3 tests/run_all.py` (recorded in 3.1: 2162 s); CI counterpart: the `--shards 1` CI run from CP6 | 1 each | reference only |
| P-1 | Local full selection, default `--jobs auto` (8 workers) | 3 | all green; median wall **<= 420 s** (prediction 3.5: ~324 s); also measured at `--jobs 16`, reported, no threshold |
| P-2 | Local `--jobs 1` serial reference | 1 | green; per-suite counts and verdict identical to P-1; wall **<= 1.10 x P-0** (fresh repository per chunk must not cost more than 10 %) |
| P-3 | CI full selection at `ci_max_shards` 16 and 24, or at `ci_account_concurrent_job_limit - 1` in place of 24 if that is lower (5.13) | 2 each | all green; median wall at the higher shard count **<= 5.5 min** (the ~5-minute target plus 10 %); 16 shards recorded for `D-CI-Cost`, no threshold; if unreachable, the remainder is documented quantitatively: critical-path chunk, per-job setup, plan and aggregate time, per-shard compute -- never closed by weakening coverage |
| P-4 | Stability: local full selection at `--jobs $(nproc)` (16) | 10 consecutive | **10 / 10 green**, zero retries; any failure is a blocking finding investigated to root cause (5.7) |
| P-5 | Planner quality and overhead, from P-1 and P-3 runs | all of them | predicted vs actual makespan within **+/-25 %**, with the prediction including A0, phase B and (CI) per-job setup and the aggregate job (5.4 step 5); max/mean shard load **<= 1.15**; discovery + planning **<= 20 s** locally; write-barrier setup/teardown **<= 5 s**; billed CI runner-minutes per full run recorded for `D-CI-Cost` |

`D-Fixture-Reuse` (5.14) is closed out from P-1's per-chunk group
overhead and a measured `bootstrapped` build cost. `config.json` and
both `timings.json` profiles are refreshed from these runs before the
final P-1 repetition, so the committed values are the ones measured.

## 8. Checkpoint registry

<!-- generated by workflow_state.render_registry_markdown(registry); never hand-edited -->
| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Deterministic inventory, selection grammar, tree identity, shared resource and plan-chunk contracts, and per-unit host execution | - | 3 | 1 |
| CP2 | Frozen-matrix decomposition: frozen chunks, fail-closed merge, unchanged host assertions in direct and merged modes | CP1 | 5 | 2 |
| CP3 | Timing history, adaptive shard count and duration-balanced chunking/assignment planner | CP1 | 3 | 1 |
| CP4 | Isolation, declared exclusive units and repository-integrity guard | CP1 | 3 | 1 |
| CP5 | Local parallel executor, aggregation/reporting, exit codes and run_all.py compatibility | CP2, CP3, CP4 | 4 | 1 |
| CP6 | Dynamic CI pipeline generated from the plan, with aggregate as the required check | CP5 | 3 | 1 |
| CP7 | Performance acceptance, tuning, committed timing seed, stress runs and full regression | CP6 | 2 | 1 |

**Why this order.** CP1's inventory, unit ids and tree identity
(`tree.py`: `tree_digest` and the snapshot/compare function, 5.6) are the
vocabulary every other checkpoint uses. So are the two contracts CP3 and
CP4 both consume (round 5, I1): the declared resources (`resources.json`
and its loader, 5.8) and the plan's chunk descriptor (`plan_schema.py`,
5.4 step 6). The planner writes that contract and `isolation` reads it,
so neither needs the other. CP2 (the riskiest: it touches the
two assertion modules that carry the conformance evidence), CP3 (pure
planning functions) and CP4 (isolation mechanics) each need only CP1, and
each is proved at function level by its own tests and evidence (round 4,
I1): CP2's merge takes provenance as an argument and its evidence uses a
fixed chunking; CP3's plan verification is a function; CP4's tests drive
`isolation` functions against scratch checkouts. CP5 is the first point
where they compose into a parallel run, so every executor-, CLI- or
exit-code-level test (T-EXE-1..11) and every evidence item that needs a
real run through the executor (E-EXE-1..3) is CP5's. CP6 needs CP5's
`--plan-only`/`--run-shard`/`--aggregate`. CP7 measures the finished
system. Section 6 names the owning checkpoint of every test id.

**Common rules for every checkpoint.**
- Changes are confined to `tests/` (new `tests/parallel/` package, new
  `tests/frozen_runs.py`, new `tests/test_parallel_runner.py`, edits to
  `tests/run_all.py`, `tests/support.py`, `tests/test_conformance_suite.py`,
  `tests/test_bootstrap_e2e.py`, and in CP5 only (round 3, I2) one
  declared assertion change in
  `tests/test_workflow_2_6_0_hardening_disposable_repo.py` plus, under
  either `D-Fast-Flag` outcome (round 4, O2), comment-only edits to
  `tests/test_workflow_2_6_0_hardening_disposable_repo.py:1423-1424` and
  `tests/test_amendment_update_path.py:444-450`), the new
  `.github/workflows/workflow-manager-verify.yml` (CP6), and documentation
  (`README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`; CP5/CP7).
- Never touched: `distribution/`, `migration/`, `scripts/`,
  `.claude/commands/`, `src/workflow_manager/`, `tools/`, the managed
  `.github/workflows/workflow-conformance.yml`. Each checkpoint records
  `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
  as empty (INV-5 evidence).
- Stdlib only (the repository's existing rule for `tests/`).
- Each checkpoint's narrowest check runs its own new tests plus
  `python3 tests/run_all.py --jobs 1 --select <touched modules>`; CP2, CP5
  and CP7 run the full selection. Before CP5 that command is CP1's
  interim direct-mode path, with no lock or barrier. It is not INV-6's
  serial reference (INV-6, round 5 O3).

<!-- CP1 -->
**CP1 -- Deterministic inventory, selection grammar, tree identity and
per-unit host execution** (REQ-1, REQ-6).
- `tests/parallel/__init__.py`, `tests/parallel/inventory.py`
  (section 5.1 host discovery; frozen discovery lands in CP2),
  `tests/parallel/tree.py` (5.6: `tree_digest(repo_root)` and the
  repository snapshot/compare function 5.9 steps 1 and 6 use; round 4,
  I1),
  `tests/parallel/unit.py` (runs one host chunk -- a class, or selected
  methods of it -- in its own process via `unittest`, writes a result
  record: ids run, outcomes, skips with reasons, failing ids, duration,
  output tail).
- The two contracts CP3 and CP4 share (round 5, I1):
  `tests/parallel/resources.json` (5.8, with the one exclusive unit and
  its reason, and each resource's guarded-tree `paths`; round 7, I3) plus
  its loader `tests/parallel/resources.py` (`load(repo_root,
  host_unit_ids)`, the resource-path validation and `GUARDED_TREES`), and
  `tests/parallel/plan_schema.py` (`ChunkDescriptor`, `shard_chunks`;
  5.4 step 6).
- `run_all.py` gains `--list` and `--select` and a serial `--jobs 1`
  path over host units. That path is interim direct mode, with no lock
  or barrier, and not INV-6's serial reference (round 5, O3). The default
  path still runs today's modules (parallel default arrives in CP5).
- Tests: section 6.1 T-INV-1, -2, -4 and -5, host parts, and T-INV-8
  (the shared contracts); `tree.py`'s
  own unit tests (a dirty tree has its own digest; an untracked file
  changes it; an ignored file does not; the snapshot sees an ignored
  file under a guarded tree).

<!-- CP2 -->
**CP2 -- Frozen-matrix decomposition** (REQ-1, REQ-5, REQ-10).
- `tests/support.py`: `run_suite(..., classes=())` appends class names to
  argv; nothing else in it changes.
- `tests/frozen_runs.py` (section 5.5): `FrozenChunk`, `execute`,
  `FrozenRecord`, `MergeContext`, `merge`, `MergedResult.from_single`,
  `FrozenMergeError` (the merge's expected values come only from the
  context, and merged mode reads it from `WM_FROZEN_CONTEXT`; round 7,
  I1); the declarative
  `FROZEN_MATRIX` table naming the 15 host classes with their
  `(version, fixture)` lives in the data-only `tests/parallel/matrix.py`,
  next to the `CI_SUITES` view the inventory reads (imported from
  `support`, the single source), so a scratch checkout can replace it
  (5.9 "Tests and the lock"); frozen discovery added to `inventory.py`.
- `tests/test_conformance_suite.py`, `tests/test_bootstrap_e2e.py`: the
  15 matrix classes' `setUpClass` gains the direct/merged split and the
  assertions read `MergedResult` fields. No assertion is removed, and no
  expected value (`CI_SUITES`, `expected_portability_exceptions`, residue,
  drift) changes.
- `tests/frozen_runs.py` also carries the full-state snapshot helper
  (5.5) used by E-MRG-3, and the `--evidence` driver of 5.5.
- Tests: section 6.1 T-INV-1, -2, -4 and -5, frozen parts, plus T-INV-3
  and -7; section 6.2 T-MRG-1..7 (merge-level; their exit-code verdicts
  are T-EXE-1, CP5); evidence E-MRG-1 (direct == merged over the fixed
  two-chunk chunking), E-MRG-2 (one class per chunk) and E-MRG-3 (full
  repository and git-dir state delta per suite, per fixture, per
  release), all recorded in the ledger. If
  E-MRG-3 finds any unclassified delta (5.5's pre-classified bytecode
  caches and `flock` targets excepted, each listed), stop and surface
  the exact deltas for the `D-Frozen-Run-Fresh-Repo` decision (5.5) before CP5.
- Full selection green in direct mode (`python3 tests/run_all.py` as
  today).

<!-- CP3 -->
**CP3 -- Timing history and planner** (REQ-2, REQ-3, REQ-4).
- `tests/parallel/timings.py` (5.2), `tests/parallel/planner.py` (5.3,
  5.4, INV-1..3; canonical `plan.json` + `plan_digest`),
  `tests/parallel/config.json` (initial bounds), and a seeded
  `tests/parallel/timings.json` whose `local` profile comes from this
  plan's section 3 profiling data, regenerated by the committed tooling
  (CP7 refreshes both profiles).
- The planner reads exclusive units only through CP1's
  `resources.load` and writes chunks only through CP1's
  `plan_schema.ChunkDescriptor` (5.4 steps 4 and 6; round 5, I1).
- Tests: section 6.3 T-PLN-1..9 (T-PLN-8 at function level, 6.3; T-PLN-9
  is the planner-level test of 5.4 step 4) and section 6.1 T-INV-6
  (INV-2 over the timing file this checkpoint defines).

<!-- CP4 -->
**CP4 -- Isolation, declared exclusive units and integrity guard** (REQ-6).
- `tests/parallel/isolation.py`, all taking `repo_root`, reading
  resources through CP1's `resources.load` and plans through CP1's
  `plan_schema.shard_chunks` (round 5, I1; `resources.json` itself is
  CP1's):
  `run_chunk` (per-chunk environment and `TMPDIR` with the
  permission-resetting cleanup, `start_new_session`, process-group kill
  on timeout and on exit, outcome classification; 5.7, 5.9),
  `phase_a_order` and `check_exclusive_windows` (the A0 ordering and
  window check, 5.8), `acquire_run_lock` (the checkout run lock under
  the per-worktree git dir), `apply_barrier`/`restore_barrier`/
  `recover_barrier` (the write barrier, its marker, lock-gated crash
  recovery and the root refusal) and `attribute_integrity_diff` (5.9).
  The CLI flags that expose them (`--restore-barrier`, `--allow-root`)
  are CP5's. The snapshot/compare and `tree_digest` are CP1's `tree.py`.
- The `scratch_checkout` helper of 5.9 in `tests/test_parallel_runner.py`,
  in the form CP4's tests need: its own git dir, a copy of
  `tests/parallel/` with the synthetic `resources.json` of 5.9 in place of
  the real one (and the `resources=` argument), synthetic host modules
  including `test_scratch_exclusive.py`, and the four guarded trees,
  and the refusal of the real root; plus `scratch_worktree(scratch)` for
  T-ISO-13, and the module-level helper-process functions that 5.9's
  accepted root forms require (round 5, O1). CP5 adds the parts only a CLI run
  over frozen chunks needs (`tests/run_all.py`, `tests/frozen_runs.py`,
  `tests/support.py`, `src/workflow_manager/`, the synthetic release,
  `migration/` files and `matrix.py`), since `frozen_runs.py` is CP2's.
- The static lint test, with exactly the pattern list and the declared
  limits of 5.9, taking its declared units from CP1's `resources.load`.
- Tests: section 6.4 T-ISO-1..9 and T-ISO-11..14, function-level (T-ISO-10
  is now T-EXE-10, CP5). No evidence run: the real-selection phase-A
  evidence needs the executor and moved to CP5 (E-EXE-2; round 4, I1).

<!-- CP5 -->
**CP5 -- Local parallel executor, aggregation and compatibility**
(REQ-2, REQ-7, REQ-10).
- `tests/parallel/executor.py` (5.9: phases A/B, workers, run lock,
  integrity guard with the per-mode guard set, history append; the
  phase-B `MergeContext` files built from the verified plan and passed
  as `WM_FROZEN_CONTEXT`, 5.5, round 7, I1),
  `tests/parallel/report.py` (5.11), `tests/parallel/cli.py` (the
  `repo_root`-parameterized `main`, pre-lock validation and the
  `error[<ErrorName>]` refusal tag, 5.9), and `run_all.py` reduced to the
  shim calling it. CLI: `--jobs`, `--select`, `--list`, `--plan-only`,
  `--run-shard`, `--aggregate`, `--results`, `--profile`,
  `--update-timings`, `--restore-barrier`, `--allow-root`,
  `--shuffle-seed` and `--whole-groups` (debug), and `--fast` per
  `D-Fast-Flag`. Default becomes `--jobs auto`.
- `tests/test_workflow_2_6_0_hardening_disposable_repo.py`: the one
  declared assertion change of 5.12 (round 3, I2). Under either
  `D-Fast-Flag` outcome it also gets the comment-only edits of 5.12 to
  its own `:1423-1424` and to `tests/test_amendment_update_path.py:444-450`
  (round 4, O2).
- Documentation: `README.md` and `CLAUDE.md` "Before changing anything"
  (new timings, no tier wording), `docs/ARCHITECTURE.md` (a short
  "Verification execution" section: inventory, plan, phases, resources,
  timing data is not Workflow state, the guarded trees being read-only
  to the developer during a run and `--restore-barrier`, and the
  copy-propagation limitation of 5.9).
- Tests: section 6.5 T-EXE-1..11, including the executor-level forms
  moved out of CP2, CP3 and CP4 (the exit-code verdicts of T-MRG-3/-4/-6
  in T-EXE-1; T-EXE-8..11; round 4, I1); evidence (6.5): E-EXE-1, full
  selection `--jobs 1` vs `--jobs auto` vs three `--shuffle-seed` runs,
  identical executed-id sets, per-suite counts and verdicts, all equal
  to CP2's direct-mode full run (E-MRG-1 over the planner's chunking);
  E-EXE-2, full phase A under the write barrier at `--jobs 1` and
  `--jobs 8`, green, with A0's duration and zero `TMPDIR` residue
  recorded; E-EXE-3, `tests/test_parallel_runner.py` and the rewritten
  v2.3.1-002 assertion green both directly and under the held run
  lock.

<!-- CP6 -->
**CP6 -- Dynamic CI** (REQ-8).
- `.github/workflows/workflow-manager-verify.yml` (5.10), triggers per
  `D-CI-Cost`'s resolution.
- Tests: section 6.6 T-CI-1..5 (structure, `$RUNNER_TEMP` paths and the
  shard/plan `tree_digest` equality, aggregate refusals, managed
  `workflow-conformance.yml` still matching its installation-record
  digest, the shard/aggregate guard set in a fresh checkout).
- Evidence: one real run on a branch. This repository forbids Claude from
  pushing, so the checkpoint stops with the branch ready and asks the user
  to push it; the run URL, per-job timings and the `--shards 1` CI
  reference run (P-0's CI counterpart) are recorded when the user
  provides them.

<!-- CP7 -->
**CP7 -- Performance acceptance and regression** (REQ-3, REQ-4, REQ-9,
REQ-10).
- P-0 (CI counterpart) and P-1..P-5 with the thresholds and run counts
  of section 7, `config.json` tuned, `timings.json` refreshed for
  both profiles via `--update-timings` from CP6/CP7 results,
  `D-Fixture-Reuse` measurement closed out, measured results appended to
  this plan's ledger and `docs/ARCHITECTURE.md`.
- Final: full selection green locally (parallel and `--jobs 1`) and in CI;
  `tools/migrate.py --check` and every authored release's
  `build_release.py --check` still pass (they run inside the suite);
  INV-5 diff empty.

## 9. Requirements traceability

| id | requirement (abridged; full text in the mapping file) | checkpoints |
| --- | --- | --- |
| REQ-1 | Deterministic inventory; targeted selection kept; full selection is the only gate | CP1, CP2 |
| REQ-2 | Exact partition, verified at plan, shard and aggregation time | CP3, CP5 |
| REQ-3 | Timing history format/lifecycle; timing never selects tests | CP3, CP7 |
| REQ-4 | Adaptive shard count, LPT balancing, oversized-group chunking, tuned bounds | CP3, CP7 |
| REQ-5 | Frozen-matrix decomposition with fail-closed merge into unchanged assertions | CP2 |
| REQ-6 | Isolation, declared serialization, integrity guard | CP1, CP4, CP5 |
| REQ-7 | Local executor, one report, reproduction commands, exit-code contract | CP5 |
| REQ-8 | CI matrix generated from the plan; required aggregate check | CP6 |
| REQ-9 | Pre/post measurements against the ~5-minute CI target, floor documented | CP7 |
| REQ-10 | No tiers, no coverage change, Workflow bytes untouched | CP2, CP5, CP7 |

## 10. This milestone's own review logistics

- Governing version `2.2`: two-stage plan review (local, then manual
  external) and two-stage implementation review.
- The installed Workflow here is `2.5.1`, which has no `feedback_layout`
  stamp, so this item resolves feedback by the `2.5.1` rule
  (scoped-else-flat). No other work item is active.
- `docs/ai-workflow/registry/workflow-manager-adaptive-test-sharding-artifacts.json`
  is generated from the `process` template and then adjusted in
  `SELF_REVIEWING_PLAN` (section 11) to this item's own footprint:
  `tests/`, the new CI workflow file, `README.md`, `CLAUDE.md` and
  `docs/ARCHITECTURE.md` are this item's implementation deliverables and
  are protected at the implementation stage. `distribution/`,
  `migration/`, `src/`, `tools/` and `scripts/` are excluded at the plan
  stage (they are not design content, so an unrelated edit never stales
  the plan approval) and **protected** at the implementation stage, so an
  accidental edit there is part of the reviewed content and shows up as a
  defect of this item rather than passing silently. The managed
  `.github/workflows/workflow-conformance.yml` is also protected by exact
  path at the implementation stage (it must not change -- 5.10), winning
  over the inherited `.github/` exclusion exactly as the new
  `workflow-manager-verify.yml` does. Every `plan_stage` reason string
  in the artifacts file describes this item (revision 2; the revision-1
  strings were carried over from another milestone's declarations).
- CP6's CI evidence needs a user push (section 8, CP6).

## 11. `SELF_REVIEWING_PLAN`

- **Coverage.** Every host test still runs: 79 non-matrix host classes as
  their own units; the 15 matrix host classes in phase B with every
  assertion intact; every frozen class of every suite, release and
  fixture exactly once in phase A (3894 units), with the merge refusing
  anything else. The pinned counts and exact exception equality remain
  the proof, now over merged data. Nothing is sampled or skipped, and
  timing cannot remove a unit (INV-2).
- **The one semantic trade-off** is `D-Frozen-Run-Fresh-Repo`: suites
  stop sharing one repository in sequence. It is stated in 5.5, measured
  in CP2, and left to the reviewer if the measurement finds any
  unclassified repository or git-dir state delta (5.5).
- **Tiers.** None are added. `--fast` predates this milestone; the plan
  names the conflict (`D-Fast-Flag`) instead of silently keeping or
  deleting it.
- **Complexity check.** The two-phase design exists only because 96.5 %
  of the time sits in 15 `setUpClass` blocks. Stated honestly: *locally*
  with 8 workers the undecomposed floor (~249 s, one `2.6.0` matrix
  class) is already below the predicted 8-worker makespan (~324 s), so CP2
  buys little there. It is needed for CI, where that same class is
  ~685 s (2.75x) -- more than twice the 5-minute target on its own --
  and for local runs above ~10 workers. Without CP2 the CI target is
  unreachable at any shard count. The rest is deliberately plain: static LPT, not a
  dynamic work-stealing scheduler (same plan locally and in CI, easier to
  reproduce); one lock type; no fixture caching (3.5 shows it is not
  needed); no new dependencies.
- **Risk: load-sensitive race tests** in frozen `workflow_state_test.py`.
  Measured green at 10-way; worker count capped at CPU count; P-4 stress
  runs; a flake is a blocking finding, never retried.
- **Risk: CI speed estimate** rests on one CI run (2.75x). CP6 measures
  it; `ci_max_shards` is then a latency/cost choice for the user.
- **Risk: an undeclared writer added later.** Covered in three layers
  with stated scope (5.9): the write barrier refuses any transient or
  persistent create/delete/rename inside `distribution/`, `migration/`,
  `src/`, `tools/`, by any process; the before/after snapshot catches
  any persistent change; CP4's lint catches syntactically visible writer
  patterns in `tests/`. **Residual, not covered:** a transient in-place
  overwrite of an existing file, restored before the run ends, by code
  the lint cannot see (a helper outside `tests/`, or a dynamic path).
  T-ISO-6 asserts that gap so it cannot silently be claimed closed.
- **Risk: concurrent runs and crashed runs in one checkout** (round 2,
  B1) -- the collision the CP9 note actually records. One run per
  checkout, enforced by a lock under the per-worktree git dir and held
  until the run's last chunk process exits (a chunk's own descendants
  are covered by process-group kill, 5.9); barrier recovery happens only
  under that lock, so it can never act on a live run's barrier, and
  `--restore-barrier` recovers a checkout left `u-w` by a SIGKILL.
  **Residual, not covered:** the unchanged direct entry points take no
  lock, so a direct module run alongside a live `run_all.py` is outside
  the guarantee (the barrier still refuses its structural writes).
- **Risk: the run lock collides with the runner's own tests** (round 3,
  I1). `test_parallel_runner.py` runs inside a locked run, so every test
  that reaches the lock uses a scratch checkout with its own git dir.
  Pre-lock refusals are ordered before the lock. Every refusal is tagged
  and asserted by name. T-EXE-6/-7 and CP5's direct-and-under-lock
  evidence hold it.
- **Risk: an assertion over `run_all.py`'s source** (round 3, I2).
  v2.3.1-002's literal check cannot survive CP5's shim under either
  `D-Fast-Flag` outcome. It is replaced once, as a declared change, by an
  inventory assertion over the same fact (5.12).
- **Risk: the barrier breaks a legitimate test** (round 2, I2). It
  propagates into `copytree` copies of guarded trees; no test at the
  base commit modifies such a copy structurally, the limitation is
  documented, and cleanup handles the residue (T-ISO-12).
- **Migration.** None: no Workflow state, release or installed file
  changes. The new CI workflow is additive; the managed one is untouched
  so `workflow_manager verify` stays clean.
- **Scope.** Controller integration and the Orchestration Protocol are
  untouched; nothing here writes `~/Workspace/repflow-android` (CI clones
  it read-only at the frozen commit).
- **Artifact declarations.** Checked against section 8's file list at both
  stages (section 10); see the generated
  `workflow-manager-adaptive-test-sharding-artifacts.json`.

## 12. Open decisions and `docs/TECHNICAL_DECISIONS.md` cross-check

This repository has no `docs/TECHNICAL_DECISIONS.md`, so there are no
recorded "Open decision" rows this plan could finalize. The plan's own
decisions that need the user rather than the reviewer:

| decision | proposal | alternative |
| --- | --- | --- |
| `D-Fast-Flag` (5.12) | keep `--fast` for now as a deprecated alias for a targeted `--select`, and remove tier wording from the docs; v2.3.1-002's source-text assertion becomes "full inventory and the alias's selection contain `test_amendment_update_path.py`'s classes" | delete `--fast` outright; the same assertion keeps only its full-inventory clause |
| `D-CI-Cost` (5.13) | `pull_request` + `push: main` + `workflow_dispatch`, PR runs cancel-in-progress, `ci_max_shards` 16 (~6.5-7 min); the user states the account's plan and concurrent-job limit, which caps shards at limit - 1 | 24 shards (~5 min, same billed minutes; needs a limit of at least 25); or fewer triggers to save minutes |
| `D-Frozen-Run-Fresh-Repo` (5.5) | fresh repository per chunk; CP2 measures the full repository and git-dir state delta of every suite (E-MRG-3) and stops on any unclassified delta | add a sequential `2.6.0` canary unit (~250 s locally, becomes the critical path) |

The manual external plan reviewer (round 7) recommends the proposal
column for all three: `--fast` only as a deprecated alias, never a
verification tier; full PR + push-to-`main` verification at the highest
shard count the account's concurrency and cost allow; a fresh repository
per frozen chunk, with the canary only if CP2 finds an unclassified
interaction. That is a recommendation, not a resolution: each decision
still needs the user's explicit answer before its consuming checkpoint
(`D-Frozen-Run-Fresh-Repo` before CP5, only if E-MRG-3 fires;
`D-Fast-Flag` at CP5; `D-CI-Cost`, including the account's concurrent-job
limit, at CP6).

## 13. Review rounds

### Round 1 -- `LOCAL_MODEL_PLAN_REVIEW`, `REVISE` (bundle `47e5cd10...`, `review_content_id` `867453f8...`)

Every finding was checked against the repository before being applied;
all were accepted. None was rejected.

| finding | verified against | disposition |
| --- | --- | --- |
| B1 sections 6 and 7 missing | revision 1 went from 5.14 straight to section 8 | Accepted: section 6 (6.1-6.6, every named test group, test ids, evidence runs) and section 7 (P-0..P-5, thresholds, run counts) added; every checkpoint now cites test ids. |
| I1 lost property understated | `tests/test_bootstrap_e2e.py:104-110` is the only residue check; `tests/test_conformance_suite.py:77-139`, `:202-253` have none; `git status` cannot see git-dir state | Accepted: 5.5 restates the lost property over repository **and** git-dir state; CP2's E-MRG-3 measures a full-state delta per suite/fixture/release; the canary decision keys on it; E-MRG-2 (one class per chunk) covers within-suite class order. |
| I2 guard misses transient writes | the known writer restores the tree via `git checkout`/`git clean` before exiting | Accepted, both halves: a write barrier (directory `u-w` on the guarded trees, lifted only under an exclusive lock) now refuses transient structural writes by any process; the remaining gap (transient in-place overwrite) is stated in 5.9, INV-8 and section 11 and asserted by T-ISO-6; the lint's pattern list and limits are spelled out. |
| I3 `tree_digest` perturbed by own artifacts | `.gitignore` covers neither `plan.json` nor `out/`; revision 1 never located `<run>/` | Accepted: every output lives outside the checkout (system temp run dir, `$RUNNER_TEMP` in CI, XDG cache); path flags refuse in-repo paths; no `.gitignore` edit; T-CI-2 asserts plan/shard digest equality. |
| I4 merge conflates failures with infra faults | unittest reports a failed `setUpClass` as one error and does not count the class's tests | Accepted: the merge checks structure only; counts/outcomes flow into the unchanged assertions (exit 1); T-MRG-3/-4 added; 5.11 states exit precedence. |
| I5 artifact reasons from another milestone | `.github/workflows/ci.yml` does not exist here; `WF1a`/`WF4a-ii`/`WF5` strings | Accepted: every `plan_stage` reason in the artifacts file rewritten for this item; the stale `ci.yml` entry removed; section 10 now matches the file (implementation-stage *protection* of `distribution/`, `migration/`, `src/`, `tools/`). |
| O1 `--jobs 1` mode ambiguous | 5.5's "or `--jobs 1`'s host-only execution" clause | Accepted: `--jobs 1` is always merged mode (INV-6); direct mode is the unchanged entry points only; CP5 compares against CP2's direct run too. |
| O2 managed CI file unprotected | implementation-stage `.github/` exclusion | Accepted: `.github/workflows/workflow-conformance.yml` protected by exact path at the implementation stage. |
| O3 3.12 vs 3.14.7 | 5.10 pins 3.12 | Accepted: stated in 3.5 and 5.10. |
| O4 discovery side effects | 5.1 | Accepted: 5.1 states import-only, no test execution, bytecode off, inside the integrity window; T-INV-7. |

### Round 2 -- `LOCAL_MODEL_PLAN_REVIEW`, `REVISE` (bundle `577627db...`, `review_content_id` `79205685...`)

Every finding was checked against the repository before being applied;
all were accepted. None was rejected.

| finding | verified against | disposition |
| --- | --- | --- |
| B1 no cross-run exclusion; barrier recovery can lift or clobber a live run's barrier | `git show db4c7af:docs/ACTIVE_MILESTONE.md` lines 957-961: the recorded collision was a `--fast` run overlapping a full run, two `run_all.py` invocations; revision 2's locks lived in a fresh per-run `mkdtemp`, and recovery keyed on a marker's existence under a shared XDG path | Accepted, all four parts: (1) the run lock and barrier marker live under `<git dir>/wm-verify/`, the per-worktree git dir (5.6); (2) one exclusive, non-waiting run lock per checkout for every `run_all.py` mode, held until the run's last process exits (5.9 step 0); (3) recovery only after acquiring that lock, so only for a dead owner, and originals recorded only after recovery; (4) T-ISO-8 (live orphan blocks recovery), T-ISO-11 (two executors in one checkout, every mode), T-ISO-13 (linked worktrees). Usability note: `--restore-barrier` added and printed in the barrier-apply log line. |
| I1 exclusive `LOCK_EX` can starve behind `LOCK_SH` | `fcntl.flock` has no writer preference | Accepted, first option: exclusive chunks run in pre-phase A0, alone, before the pool starts (first in their shard in CI); per-resource `flock` removed; predicted makespan includes A0 (5.4, 5.8); T-ISO-4 reworded, T-ISO-10 bounds the wait under 16 x 50 shared units. |
| I2 barrier leaks into `copytree` copies | `tests/test_bootstrap.py:613-618` `damaged_copy` copies the real `2.3.1/`; its callers at `:629-651` only overwrite existing files inside `TemporaryDirectory` | Accepted: stated as a limitation in 5.9 and section 11; `TMPDIR` cleanup resets directory permissions before removal; T-ISO-12; CP4 evidence records zero residue. No other `copytree`/`copystat` exists in `tests/`, `src/` or `tools/`. |
| O1 E-MRG-3 will fire on foreseeable deltas | `tests/support.py:69-78` sets no bytecode variable | Accepted: bytecode caches and `flock` target files pre-classified in 5.5 (content-bearing witnesses excluded from the class); the bytecode difference stated in 5.5 and 5.7. |
| O2 snapshot's `__pycache__` exclusion contradicts T-INV-7 | 5.9 step 1 | Accepted: the snapshot now includes `__pycache__`; `run_all.py` sets `sys.dont_write_bytecode` before any import so the executor itself writes none. |
| O3 lint copy pattern flags `damaged_copy` | `copytree(release.root, dest)` | Accepted: copy/rename patterns match the destination argument only; T-ISO-9 asserts the source-rooted copy is not flagged. |
| O4 fixture-build failure changes exit class | today an exception in a matrix `setUpClass` is a test error (exit 1) | Accepted: a build-error record keeps it exit 1 (5.5, 5.11); T-MRG-6. |
| O5 stale implementation-stage reasons for `.claude/commands/`, `scripts/` | the artifacts file's `implementation_stage.protected_prefixes` | Accepted: both reasons now read "must not change; protected so any change is reviewed". |
| O6 inventory cache can never hit | per-run `mkdtemp` | Accepted: cache dropped; the inventory is recomputed every run (5.1). |

Registry regenerated at `plan_revision` 3 with checkpoints unchanged
(table re-embedded); mapping REQ-6 description updated for B1/I1/I2.

### Round 3 -- `LOCAL_MODEL_PLAN_REVIEW`, `REVISE` (bundle `7793211f...`, `review_content_id` `2b411fa2...`)

Every finding was checked against the repository before being applied;
all were accepted. None was rejected.

| finding | verified against | disposition |
| --- | --- | --- |
| I1 the run lock collides with the runner's own CLI tests | revision 3's 5.9 passes the lock fd to every chunk; `test_parallel_runner.py` is a chunk; only T-ISO-5/-11/-13 and T-CI-2 named a scratch checkout; `run_all.py` derived the root from `__file__` with no seam | Accepted, both options combined: pre-lock ordering for argparse, path-flag and `--select` syntax refusals; everything in `tests/parallel/` takes `repo_root`, with `run_all.py` a shim and no override flag; every lock-reaching test uses `scratch_checkout` (own git dir, synthetic `matrix.py`); tagged refusals; T-EXE-6/-7; CP5 evidence that the module is green directly and under the held lock (5.9, 6.5). |
| I2 a source-text assertion over `run_all.py` | `tests/test_workflow_2_6_0_hardening_disposable_repo.py:1425-1426`; `tests/test_amendment_update_path.py:445-449` | Accepted: named in INV-4 and 5.12; the literal leaves `run_all.py` under either `D-Fast-Flag` outcome, so the assertion is replaced in CP5 by an inventory assertion (plus an alias clause under the alias outcome); both files added to section 8's edit list; mutation-checked in CP5 evidence. |
| O1 stale "resource locks" naming | registry CP4 `name`; section 8 CP4 heading | Accepted: renamed to "declared exclusive units"; registry regenerated. |
| O2 CI guard set unspecified; `__pycache__` understated | `tests/test_bootstrap_e2e.py:258-263` and `tests/test_amendment_update_path.py:510-514` replace `env` without `PYTHONDONTWRITEBYTECODE`; `git status --ignored` lists `__pycache__` under `distribution/workflow/{2.4.0,2.5.0,2.5.1,2.6.0}`, `migration/overlays/{2.5.0,2.5.1,2.6.0}`, `src/workflow_manager/`, `tests/`, `tools/`, `scripts/` | Accepted: 5.9 "Guards per mode" table (barrier and snapshot in `--run-shard`/`--aggregate` too) and the CI `.pyc` case stated; 3.3 and 5.7 corrected; aggregate job's checkout and Python 3.12 setup stated (5.10); T-CI-5 and CP6 evidence. |
| O3 phase B missing from the prediction | 5.4 step 4 | Accepted: 5.4 step 5 plans phase B on the same pool and adds it, plus CI per-job setup (`ci_job_setup_seconds`) and the aggregate job, to the prediction P-5 compares; T-PLN-5. |
| O4 reproduction command cannot name a chunk | 5.1's grammar has no chunk form | Accepted: one `--select` per class plus a debug-only `--whole-groups` that stops a group splitting; T-EXE-2 covers a multi-class chunk; T-PLN-5 shows `--whole-groups` leaves the selection unchanged. |
| O5 account concurrent-job limit | GitHub caps concurrent hosted jobs per account | Accepted: `ci_account_concurrent_job_limit` (default 20) caps `max_shards(ci)` at limit - 1; `D-CI-Cost` asks the user for the plan tier; P-3 measures at the cap if it is below 24; T-PLN-4. |
| Usability: guarded trees read-only to the developer | 5.9 barrier | Accepted: printed in the barrier-apply log line and stated in CP5's `docs/ARCHITECTURE.md` section. |

Registry regenerated at `plan_revision` 4 (CP4 renamed, dependencies
unchanged; table re-embedded).

### Round 4 -- `LOCAL_MODEL_PLAN_REVIEW`, `REVISE` (bundle `63fbe77e...`, `review_content_id` `a7872abd...`)

Every finding was checked against the repository before being applied;
all were accepted. None was rejected.

| finding | verified against | disposition |
| --- | --- | --- |
| I1 CP2/CP3/CP4 own tests and evidence that need later checkpoints | revision 4's registry (`depends_on: ["CP1"]` for CP2, CP3 and CP4); section 8's CP4 bullet (T-ISO-1..13 and phase-A evidence) against CP5's `executor.py`/`cli.py`/`report.py`; T-PLN-8 against CP5's `--run-shard`; `tree_digest` in CP4's `isolation.py` but needed by CP3's `plan.json`; E-MRG-1 over CP3's chunking | Accepted, option (a); `depends_on` unchanged. `tree_digest` and the snapshot/compare function moved to CP1's new `tests/parallel/tree.py` (5.6). CP4 now owns only function-level tests (6.4 rewritten), and T-ISO-10 plus the executor halves of T-ISO-1/-2/-4/-7/-8/-11/-13 moved to CP5 as T-EXE-9..11. T-PLN-8 is now function-level (`planner.load_plan`), and its `--run-shard` form is T-EXE-8. E-MRG-1 uses an explicit fixed two-chunk chunking at CP2 through a `frozen_runs.py --evidence` driver, with provenance passed in as an argument (5.5). Its planner-chunking form is E-EXE-1. CP4's phase-A evidence is now E-EXE-2. The same audit found five more mis-owned items, fixed the same way: T-INV-4/-5's frozen clauses (CP2); T-INV-6's timing file (CP3); T-INV-7's snapshot (now CP1's); T-MRG-3/-4/-6's exit-code verdicts (T-EXE-1); T-PLN-5/-7 naming CP5 flags (now the planner/timings functions). Also fixed: section 3's "CP1 ... `--profile`" and 5.8's "CP4 measures" A0, both CP5. Section 6 now names the owning checkpoint of every id, and "Why this order" states the rule. |
| O1 `scratch_checkout` wiring | `tests/support.py:15-21` (imports `migration/*.json`, puts `src/` on `sys.path`); `src/workflow_manager/release.py:81-93`, `:239` | Accepted: 5.1 reads `FROZEN_MATRIX`/`CI_SUITES` only in the discovery subprocess rooted at `repo_root`. 5.9's helper copies `support.py` and `src/workflow_manager/` verbatim, generates the synthetic release's `manifest.json` from the files it writes, writes both `migration/` files for `0.0.1`, and replaces `matrix.py` with a literal `CI_SUITES`. T-EXE-7 asserts that `find_release` and `build_conformance_repo` accept the result. |
| O2 stale comments under both outcomes | `tests/test_amendment_update_path.py:444-450`; `tests/test_workflow_2_6_0_hardening_disposable_repo.py:1423-1424` | Accepted: 5.12 and section 8 make both comment edits unconditional, with wording per outcome. |
| O3 `pass_fds` overstated | `subprocess` defaults to `close_fds=True` for grandchildren | Accepted: 5.9 now says the lock is held until "the last chunk process" has exited. Descendants are covered by process-group handling, and `run_chunk` also kills a chunk's group when the chunk exits (T-ISO-1). |

Registry regenerated at `plan_revision` 5 (CP1 renamed to include tree
identity; dependencies unchanged; table re-embedded). Mapping: REQ-6 now
also names CP5, which owns the executor-level isolation tests.

### Round 5 -- `LOCAL_MODEL_PLAN_REVIEW`, `REVISE` (bundle `27a41998...`, `review_content_id` `301fc832...`)

Every finding was checked against the repository before being applied;
all were accepted. None was rejected.

| finding | verified against | disposition |
| --- | --- | --- |
| I1 the planner needs CP4's `resources.json`, and CP4's `phase_a_order` reads CP3's plan schema, with no dependency either way | revision 5's 5.4 steps 4 and 6 (the planner places exclusive chunks and writes their `resources`); section 8 CP4 ("`tests/parallel/resources.json` (5.8) with the one exclusive unit"); registry `depends_on` `["CP1"]` for both CP3 and CP4; T-PLN-1..8 never mention exclusive placement | Accepted, option (a); `depends_on` unchanged. `resources.json` and its loader `resources.py` (5.8) and the new `plan_schema.py` with `ChunkDescriptor`/`shard_chunks` (5.4 step 6) are now CP1's. The planner writes chunks only through `to_json`, and `isolation` and the lint read only through the CP1 loader and `shard_chunks`. New T-INV-8 (CP1) tests both contracts. New T-PLN-9 (CP3) is the planner-level test of 5.4 step 4. T-ISO-4 builds its plans from `ChunkDescriptor`. "Why this order" names the shared contracts. CP1 now also carries REQ-6 (sections 8 and 9, mapping). |
| O1 T-EXE-7's AST scan narrower than the roots 5.9 allows | 5.9 "Tests and the lock" (scratch checkout or scratch repository); T-ISO-13's linked worktrees; T-ISO-8/-11's helper processes | Accepted: 5.9 lists the accepted root forms (a `scratch_checkout` result, `scratch_worktree` of one, a literal path under either, a `scratch_root` parameter that every call site binds to one of these, `multiprocessing` targets included). Helper-process code must be module-level functions started through `multiprocessing` spawn, never `-c` strings, and the scan fails on a string naming a lock-reaching function. T-EXE-7 adds mutation checks of the scan. CP4 adds `scratch_worktree` and the helper functions. |
| O2 leftover "last process" wording; REQ-6 traceability | section 11 "Risk: concurrent runs"; the mapping's REQ-6 description; section 9's REQ-6 row (CP4 only) | Accepted: section 11 and the mapping now say "last chunk process", with descendants covered by process-group kill. Section 9 and the mapping list REQ-6 against CP1, CP4 and CP5, CP1 because of I1's move. |
| O3 CP1-CP4's interim `--jobs 1` contradicts INV-6 and "every mode takes the lock" | INV-6 ("always runs merged mode"); 5.9 "Every mode takes the lock"; section 8's common narrow check `--jobs 1 --select` | Accepted: INV-6, 5.9's lock paragraph and its guard table now bind from CP5. The CP1-CP4 `--jobs 1` path is stated as interim direct mode, with no lock or barrier, and not the serial reference (INV-6, section 8 common rules, CP1). |
| O4 T-INV-3 appears to need CP4/CP5's `scratch_checkout` parts | 5.1 frozen discovery reads `<repo_root>/tests/parallel/matrix.py` and the release payload; section 8 CP4 assigns the synthetic release and literal `matrix.py` to CP5 | Accepted: T-INV-3 builds its own minimal layout (a payload `scripts/` with one suite and a literal `matrix.py` pinning a wrong count). It needs no fixture builder, manifest or `scratch_checkout`. |

Registry regenerated at `plan_revision` 6 (CP1 renamed to include the
shared resource and plan-chunk contracts; dependencies unchanged; table
re-embedded). Mapping: REQ-6 now names CP1, CP4 and CP5, and its
description says "last chunk process".

### Round 6 -- `LOCAL_MODEL_PLAN_REVIEW`, `APPROVE` (bundle `4f758048...`, `review_content_id` `84260a52...`)

Approved with no blocking or important findings; revision 6 went to
manual external review unchanged.

### Round 7 -- `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, `REVISE` (bundle `4f758048...`, `review_content_id` `84260a52...`)

Every finding was checked against the repository before being applied;
all were accepted. None was rejected. The reviewer found no reason to
change the architecture, checkpoint graph, performance targets or the
no-coverage-reduction requirement, and none of them changed.

| finding | verified against | disposition |
| --- | --- | --- |
| I1 phase-B merge provenance has no independent source | revision 6's 5.5: `merge(records, version, fixture)` takes no expected chunk set, class set, tree digest or plan digest; merged mode receives only `WM_FROZEN_RECORDS`; CP2's evidence path the same | Accepted: `MergeContext` (CP2) carries the planned chunks, discovered class sets, `tree_digest` and `plan_digest` for one `(version, fixture)`, and `merge(records, context)` takes every expected value from it. CP5's executor (and the CI `aggregate` job) builds it from the verified plan and inventory, writes it under `<run>/merge-context/`, separate from the records, and passes it as `WM_FROZEN_CONTEXT`. CP2's evidence driver builds it from its fixed chunking. Merged mode refuses a missing context and a context whose `tree_digest` differs from the checkout's, and never derives one from records. Direct mode uses `MergedResult.from_single` (no plan exists). New T-MRG-7; T-MRG-2 and T-CI-3 extended; 5.6, 5.7, 5.10 and section 8 CP2/CP5 updated. |
| I2 `scratch_checkout` copies a `resources.json` its own loader rejects | revision 6's 5.9 copies `tests/parallel/` verbatim; 5.8's committed exclusive unit `host:test_amendment_update_path.py::TestMigrateDoesNotDeleteASiblingAuthoredRelease` is not in the synthetic host inventory, and the loader rejects an exclusive unit absent from the inventory | Accepted: the helper replaces `resources.json` with a synthetic declaration (`repo:distribution` over `distribution/`, exclusive unit `host:test_scratch_exclusive.py::TestScratchExclusiveWriter`, a synthetic module it writes), takes a `resources=` override, and refuses one that does not load against the scratch inventory. The loader now takes the caller's host unit ids (`load(repo_root, host_unit_ids)`), so T-PLN-9 builds a minimal inventory and declaration that are mutually valid. New T-ISO-14 (CP4); section 8 CP4 updated. |
| I3 resources do not say which guarded trees they cover | revision 6's 5.8 schema maps `repo:distribution` to a prose string; 5.9 lifts "the trees the running exclusive unit's resource names" | Accepted, the preferred shape: each resource is `{"paths": [...], "description": ...}`, each path exactly one member of CP1's `resources.GUARDED_TREES` (which `isolation` imports). The loader rejects the bare-string form, empty or non-string paths, absolute paths, `..`, paths outside the allowlist, a tree repeated in one resource or claimed by two, and an empty description. A0 lifts exactly the union of the running unit's resources' `paths`. T-INV-8 extended with every invalid case; T-ISO-14 checks lifting follows `paths`; section 8 CP1 updated. |
| O1 `--update-timings` contradicts "no working-tree writes" | 5.2 (`--update-timings` rewrites the committed `tests/parallel/timings.json`) against 5.6 ("every file the tooling writes ... lives outside the working tree") and 5.9's guard table ("touch no working-tree path") | Accepted: 5.6 names `--update-timings` as the one deliberate exception; the guard-table reason now says both modes execute no units, and states what each writes. |

The three user decisions of section 12 are unchanged and still open;
the reviewer's recommendation on them is recorded there. Registry
regenerated at `plan_revision` 7 with checkpoints unchanged (table
re-embedded). Mapping: REQ-5 and REQ-6 descriptions name the merge
context and the resources' declared guarded trees.
