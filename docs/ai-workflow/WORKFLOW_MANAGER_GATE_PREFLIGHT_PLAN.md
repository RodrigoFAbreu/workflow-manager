# Workflow Manager: A Gate Run That Cannot Succeed Stops at Its Start (Revision 3)

`work_item_id: gate-preflight` -- `governing_workflow_version: "2.2"`

**Deliverable:** a preflight at the start of `tests/run_all.py`, before any
unit starts: (1) every tested version is read back from the release cache
after priming, and one the cache does not serve is a `PrimingError` naming the
version; (2) a run that starts units checks the free space of the filesystem
its run directory is created on (`--results` when given, else the effective
`TMPDIR`) against a named minimum and refuses with the path and the numbers
(roadmap row 25, issues #150 and #125).

**Work item type:** `process`. **Base commit:** `2be4b4b`
(`2be4b4bc6d00f0ea56d5234941c3c22279ef4f63`, tip of `main`; Workflow 2.25.5
installed, automatic gates). **Branch:** `milestone/gate-preflight`. **Scope
source:** `docs/ROADMAP.md` row 25 (added by this item, Current now, Done at
acceptance). The pull request title is `fix: ...`, a **patch** release (checked
with `python3 tools/release/release.py check-title`). One mechanism: *a gate
run that cannot succeed stops at its start with a refusal that names the
cause*. Two checkpoints. One review surface: the runner's start-up in
`tests/parallel/priming.py` and `tests/parallel/cli.py`, and the tests that
pin it. Sizing: well under 350 lines, one surface; no split needed.

## 1. Each item checked against main (`2be4b4b`)

| Item | Still present on main? | Evidence |
| --- | --- | --- |
| #125 the error names only the missing counts | No, already fixed | row 19 and row 21: `support._lock_conformance` names the release, the cache directory and `python3 tests/run_all.py --list`; pinned by `TestUnfilledCacheNamesTheRelease` |
| #125 a unit imports `support` before priming ends | No such path | see section 2 |
| #125 the fault itself | Not reproduced | see section 2 |
| #150 (1) every tested version cached, else `PrimingError` | Partly | `priming.prime` fails when `ensure` fails, but nothing checks that the cache then serves each manifest, the read `support` makes |
| #150 (2) free space under `TMPDIR` | Yes | nothing in `tests/` reads free space; the run directory is `tempfile.mkdtemp(prefix="wm-run-")` (`executor.py`) under the effective `TMPDIR` |

Out of scope, stays open: any Workflow change, any change to the matrix, the
shards or the pinned releases, #147, #145, #131, #119, #116 and #100
follow-ups.

## 2. #125: why the first run faulted, and what is done about it

**Ordering is correct.** `cli._main` takes the run lock, recovers a barrier,
then calls `priming.prime` and exports the cache; only then does `_dispatch`
discover or run anything. `tests/support.py` is imported only inside
subprocesses (`inventory._discover_frozen_in_process` and the units), never in
the runner process, and `cli.py` imports `matrix` (which imports `support`)
nowhere at module level. So no unit can import `support` before priming ends.

**Not reproduced after a real attempt (2026-11-02, base `2be4b4b`).** A cold
cache directory and a `file://`-style mirror directory built from the warm
cache (27 locked releases, none cached): `python3 tests/run_all.py --list`
primed all of them, and `--select test_parallel_runner.py::TestFrozenInventory
--select test_parallel_runner.py::TestCiAggregateRefusals` (two of the three
faulting modules) passed against that fresh cache (14 s, exit 0). The
2026-10-28 fault stays unexplained; the one state that could produce it is
"`ensure` succeeded and the cache still did not serve the manifest to a
later reader".

**So the failure is made to name its cause at the start, not in a unit.**
After priming, `priming.prime` reads back, for every tested version, what
`support` reads: `ReleaseCache.cached_manifest(version)`. A version for which
it returns nothing is a `PrimingError` (exit 2, before any unit starts):

`release V was primed into the cache C from S but the cache does not serve its manifest: when no other run is using the cache, remove C/V and run again`

(`V` the version, `C` the cache directory, `S` the source). One next step:
removing the entry makes the next `ensure` fetch it again; the condition is
there because `ReleaseCache` takes a per-version `<version>.lock` for its
writers and another checkout's run can share the same user cache. Priming
itself is not reordered.

## 3. #150 (2): the free-space minimum

`MIN_FREE_RUN_BYTES = 4 * 1024**3` (4 GiB), a named constant in
`tests/parallel/priming.py`, with its evidence in the comment above it.

**Evidence** (measured 2026-11-02, base `2be4b4b`, this machine: 16 CPUs, 8
local workers, TMPDIR a private directory, `du -sk` of it sampled once per
second while `python3 tests/run_all.py` ran the full selection, 2328 units,
15523 tests, wall 865 s, exit 0): the peak was **1,989,292 KiB (1.9 GiB)**.
That is the run directory, every chunk's private `TMPDIR` (emptied after each
chunk, and placed under the run directory by `isolation`, `run_dir / "tmp" /
name`), and the mirror and private-cache copies the tests build under it. In
that measurement the run directory was the default `mkdtemp` one, so the whole
peak was under `TMPDIR`; with `--results` the same bytes are written under
`--results` instead (see "Where it applies"). The
`resources.json` and timings data record no disk use, so this measurement is
the evidence. The minimum is 2.1 times the peak: room for a second sample
missed between two seconds, more workers on a bigger machine, and the Workflow
releases that will be locked later. It is a stated threshold of a run that
would otherwise fail, not a promise of exact use.

**Where it applies.** `cli._main`, after the barrier is recovered and
**before `priming.prime`** (so a doomed run fetches nothing and writes
nothing), for the modes that start units: the local run, `--run-shard` and
`--aggregate`. `--list`, `--plan-only`, `--update-timings` and
`--restore-barrier` start no unit and are never refused for space. **The
path checked is the directory the run directory is created in**, because
`executor.make_run_dir(results)` creates it at `--results` when that is given
and with `tempfile.mkdtemp` (under `tempfile.gettempdir()`) only when it is
not, and every chunk's private `TMPDIR`, the mirror and the private caches live
under it: `--results` (its nearest existing ancestor, since it may not exist
yet, and the check creates nothing) for the local run with `--results` and for
`--run-shard` (where `--results` is required); `tempfile.gettempdir()` for a
local run without `--results` and for `--aggregate` (`make_run_dir(None)`). A
small `TMPDIR` with a large `--results` is therefore not refused, and a large
`TMPDIR` with a full `--results` is.

`priming.check_free_space(path, minimum=None, free=None, lever="TMPDIR")` raises
`TmpSpaceError`, a subclass of `PrimingError`, so it is in the same error
family and exits 2 through the existing `REFUSALS`. `free` is the injected
measurement (default `shutil.disk_usage(path).free`, `path` the nearest existing
ancestor); `minimum` defaults to the constant; `lever` is the option the
operator changes, `cli._main` passing `--results` when it is given and `TMPDIR`
otherwise. The refusal is exactly

`P has F bytes (G GiB) free, and a run needs at least M bytes (N GiB) there: set L to a directory with that much free space and run again`

with `P` the path checked (the `--results` path as given, or the effective
temp directory), `L` the lever, `F` and `M` the byte counts and `G`, `N` the
same in GiB to one decimal. Free equal to the minimum passes.

**Nested runs.** `tests/test_parallel_runner.py` starts about 30 runner
invocations of its own (`--run-shard`, `--aggregate` and local runs against
scratch checkouts), inside a unit of the outer run; `isolation.chunk_env` copies
`os.environ` into every chunk, and its `TMPDIR` and any `--results` are under the
outer run directory, on the outer run's filesystem. Checked again, each would
need the 4 GiB while the outer run is already using up to 1.9 GiB of it, which
raises the real requirement to about 4 GiB plus the peak and fails dozens of
existing tests deep inside units. So **only the outermost run checks**. While
`priming.exported` is active it sets `WM_GATE_PREFLIGHT=<pid of the outer
runner>` (a named constant, `GATE_PREFLIGHT_ENV`, restored on exit like the
cache variables); chunk subprocesses and in-process nested calls inherit it. A
run whose environment carries it with the pid of a live process skips the check;
a missing, malformed or dead-pid value is checked. It is internal: it is not an
option, it appears in no help text or page, it holds no number, and it cannot
lower the minimum, only skip a check an enclosing run has already done. The
hermetic refusal tests clear it so they still exercise the check.

## 4. Tests (`tests/test_parallel_runner.py`, a new class `TestGatePreflight`)

A new class in the existing file, after `TestScratchReleaseIsolation`: no new
test module, no change to `resources.json` or the timings. All hermetic: a
scratch checkout and its own source and cache (`scratch_checkout`), an
injected free-space number, a faked priming report, no network.

* **The check.** `check_free_space(p, minimum=M, free=M - 1)` raises
  `TmpSpaceError` (a `PrimingError`) whose text has the path, both byte counts
  and `TMPDIR`; with `lever="--results"` the text names `--results` and not
  `TMPDIR`; `free=M` and `free=M + 1` return; the constant is pinned to
  `4 * 1024**3`.
* **The refusal at the start.** In-process `cli.main` against a scratch with
  `priming.MIN_FREE_RUN_BYTES` patched above any disk: exit 2, first stderr
  line `run_all: error[TmpSpaceError]: ...` naming the effective `TMPDIR`.
  **No-write proof:** the scratch checkout's tree digest is unchanged, the
  `TMPDIR` holds no `wm-run-*` directory, the scratch's private release cache
  was never created (priming did not run), `src/` and `tools/` are not
  read-only afterwards (no barrier), and the run lock is free.
* **Which directory.** A local run with `--results SCRATCH/res` (not yet
  existing, under an existing scratch directory) and `MIN_FREE_RUN_BYTES`
  patched above any disk: exit 2, the refusal names the `SCRATCH/res` path and
  `--results`, and `SCRATCH/res` was not created. With `--results` given and the
  patch absent but the injected free number for the `--results` side only
  (`check_free_space` stubbed to record its first argument), the path recorded
  is the `--results` one, not `tempfile.gettempdir()`; without `--results` it is
  `tempfile.gettempdir()`; for `--run-shard` and for `--aggregate` the paths
  follow the same rule.
* **Nested runs.** `priming.exported(cache)` sets `GATE_PREFLIGHT_ENV` to
  `str(os.getpid())` inside the block and restores the previous value after it.
  With the variable set to the test process's own pid and `MIN_FREE_RUN_BYTES`
  patched above any disk, a local run against a scratch is not refused for
  space (it exits as it would without the patch); with it unset, set to a dead
  pid (a reaped child's) or set to text, the same run is refused. A run
  started through the runner's real chunk environment (`isolation.chunk_env`
  from inside `priming.exported`) carries the variable. The refusal tests above
  clear it (`mock.patch.dict(os.environ)` with the key removed).
* **Scope.** With the same patch, `--list` and `--plan-only --out PATH` (outside
  the checkout) are not refused for space and exit 0 on the scratch.
* **The read-back.** `priming.prime` with `subprocess.run` faked to print a
  report whose `unserved` is `["0.0.1"]` raises `PrimingError` naming
  `0.0.1`, the cache and the source, and nothing is written. With `unserved`
  `[]` it returns the report. Against the scratch's real script,
  `priming.prime(scratch, env)` returns `unserved == []` and `versions ==
  ["0.0.1"]` (the key must be present, so the script cannot drop the read-back
  silently).
* **Unchanged.** `test_a_pin_that_cannot_be_primed_is_exit_2_naming_the_cache_and_the_source`
  and every other existing test stay unedited and green: no existing test pins
  a text this item changes (`PrimingError` for a version that cannot be primed
  is untouched).

**Failure-only mutations** (a scratch clone, never the repository; each passes
on the real code and must fail as stated):

| Mutation | Must fail |
| --- | --- |
| remove the `check_free_space` call from `cli._main` | the refusal-at-the-start case |
| the call moved after `priming.prime` | the refusal case (the private cache must not exist) |
| the call also for `--list` and `--plan-only` | the scope case |
| the check always measures `tempfile.gettempdir()`, ignoring `--results` | the which-directory case |
| a nested run checks again (the marker ignored) | the nested-run case |
| the marker honoured without the liveness test (a dead pid skips) | the nested-run case, dead-pid half |
| `exported` no longer sets the marker | the chunk-environment case |
| `free < minimum` changed to `free <= minimum` | the `free=M` case |
| `MIN_FREE_RUN_BYTES` changed | the pinned-constant case |
| the `unserved` raise removed from `prime` | the read-back refusal case |
| `unserved` removed from the script's report | the real-script case |

Evidence at implementation: `python3 tests/run_all.py --select
test_parallel_runner.py::TestGatePreflight` green, each mutation failing the
case named, then `python3 tests/run_all.py`.

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The preflight, its tests and the page | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the preflight, its tests and the page

**Files:** `tests/parallel/priming.py`, `tests/parallel/cli.py`,
`tests/test_parallel_runner.py`, `docs/ARCHITECTURE.md`.

Sections 2 to 4. `priming.py` gets the constant, `TmpSpaceError`,
`check_free_space` and the read-back (script and `prime`); `tools/release/package.py`
and `tools/release/release.py` also call `priming.prime` and gain the read-back
refusal, which only ever fires on a cache that would have failed later.
`cli.py` calls the check before priming, unless the nested-run marker names a
live process (with `--results` or the temp directory, as section 3 says);
`priming.exported` sets and restores the marker and lists the two new exit-2 causes in its
docstring, and its "Order:" paragraph (every mode but `--restore-barrier` then
primes) also says that the free-space check runs before priming, for the modes
that start units. `docs/ARCHITECTURE.md`'s "Verification execution" Priming bullet
changes (the read-back and the free-space refusal, in place of "naming the
cache directory and the source" alone); no other section changes. No test pins
the changed text. No internal milestone id is named on the page.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 25 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance (its text says the free space is checked under `--results` when
given, else the effective `TMPDIR`); `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: the `fix:` title releases a patch. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 6. Functional review

Every flow runs offline in a sandbox: no network, no `gh`, no installs, no
sockets, no zlib-ng, a small tmpfs, and **no Workflow release cache**. No flow
bootstraps a release; flows 1 to 5 call the new functions through `python3 -I`
with injected inputs, once against the base and once against the candidate.
Setup: `S=$TMPDIR/fr; mkdir -p $S/base $S/cand $S/cache`; `git archive 2be4b4b
tests | tar -x -C $S/base`; `git archive <candidate head> tests | tar -x -C
$S/cand`. `$S/cache` stays empty throughout. The harness `$S/h.py`:
`import sys;sys.path.insert(0,sys.argv[1]+"/tests");from parallel import
priming;exec(sys.argv[2])`, run as `python3 -I $S/h.py $S/<base|cand> "<code>"`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | code `from pathlib import Path;priming.check_free_space(Path("/x/tmp"),minimum=1000,free=999)`, then the same with `,lever="--results"` appended | candidate: `TmpSpaceError` text with `/x/tmp`, `999`, `1000` and `TMPDIR`; the second names `--results` and not `TMPDIR`; base: `AttributeError` (no check) |
| 2 | code `from pathlib import Path;priming.check_free_space(Path("/x/tmp"),minimum=1000,free=1000);print("ok")`, then the same code with `free=2000` | candidate: `ok` twice, nothing raised |
| 3 | code `print(priming.MIN_FREE_RUN_BYTES==4*1024**3, issubclass(priming.TmpSpaceError,priming.PrimingError))` | candidate: `True True`; base: `AttributeError` |
| 4 | code: `import types;priming.subprocess.run=lambda *a,**k:types.SimpleNamespace(returncode=0,stderr="",stdout='{"cache":"CACHE","source":"s","versions":["7.0.0"],"unserved":["7.0.0"]}')`, then `from pathlib import Path;priming.prime(Path("."))`, with `CACHE` the path of `$S/cache` | candidate: `PrimingError` naming `7.0.0`, the (empty) cache directory and `s`; base: returns the report, no error |
| 5 | the same fake with `"unserved":[]` | candidate and base: return the report, no error; `$S/cache` still empty |
| 6 | (needs the full environment) in a clone at the candidate head: `python3 tests/run_all.py --select test_parallel_runner.py::TestGatePreflight` | exit 0, every test of the class passes |

## 7. Risks

* A hand-set `WM_GATE_PREFLIGHT=<live pid>` skips the check for that run. It is
  undocumented, carries no value and exists only so a nested runner inside a
  gate chunk does not repeat the enclosing run's check; an operator who sets it
  bypasses a safety check on their own run.
* The 4 GiB minimum refuses a run on a tmpfs smaller than that. It is the
  point: such a run risks ENOSPC mid-way. The message names the path and
  the lever the run uses (`--results` or `TMPDIR`), the one lever.
* Priming writes into the release cache (`XDG_CACHE_HOME`/`HOME`, possibly
  another filesystem) before any unit starts; the check does not cover a full
  cache filesystem. That case already fails at its start as `PrimingError`, so
  it is out of scope here.
* The read-back adds one `cached_manifest` call per tested version to every
  priming (a local file read and a hash); `tools/release/package.py` and
  `tools/release/release.py` share it.

## 8. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
