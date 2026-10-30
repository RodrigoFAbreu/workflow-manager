# Workflow Manager: Name the Missing Release in the First Run After a Lock Add (Revision 1)

`work_item_id: release-cache-priming` -- `governing_workflow_version: "2.2"`

**Deliverable:** when `tests/support.py` cannot read a lock-only release's
manifest from the release cache and the lock entry carries no suite counts,
the error names the release, the cache directory and the command that fills
the cache (`python3 tests/run_all.py --list`), instead of saying only that the
counts are missing. The fault of issue #125 did not reproduce, so this item
makes it self-explaining and changes nothing else.

**Work item type:** `process`. **Base commit:** `1575e0d` (tip of `main`;
Workflow 2.25.0 installed, automatic gates). **Branch:**
`milestone/release-cache-priming`. **Scope source:** `docs/ROADMAP.md` row 19
(issue #125). Tests and docs only (`tests/`, `docs/ARCHITECTURE.md`): nothing
under `src/` changes, so the pull request title is `test: ...`, which releases
nothing (checked with `python3 tools/release/release.py check-title`).
**Not in this milestone:** the two test-strength items of the previous item
(issue #128, the next item), a change to priming or to the runner, a change to
`InfrastructureFaultError`'s report, and any `src/` change. One mechanism, two
checkpoints (the sizing rule's limits).

## 1. The problem and what the investigation showed

On 2026-10-28, after `python3 tools/release_lock.py add 2.24.0`, the first
`python3 tests/run_all.py` exited 2: three host modules each reported
`missing_record: no result record (runner exit 1)`, and their logs ended in
`LockError: 2.24.0: neither its manifest nor its lock entry carries the frozen
suite counts`, raised at import of `tests/support.py`. `support` builds
`CI_SUITES` for every lock entry through `_lock_conformance`
(`tests/support.py`), which asks `ReleaseCache.cached_manifest(version)`; a
lock entry written for a release whose manifest has a `conformance` block holds
no suite counts (`release_lock.py add` writes them only while the manifest has
no block), so a cache without that manifest leaves nothing to read. A rerun
after `python3 tests/run_all.py --list` passed.

Findings, each reproduced at `1575e0d` in a scratch cache under `$TMPDIR`:

1. **The import fault itself is deterministic.** `python3 -c "import support"`
   from `tests/`, with `WORKFLOW_MANAGER_RELEASE_CACHE` naming an empty
   directory, raises `LockError: 2.13.0: neither its manifest nor its lock
   entry carries ...` (the first suiteless entry of today's lock). Nothing in
   the message says the cause is an unfilled cache, or which cache.
2. **A child process with `cli_env()` reproduces it too.** `support.cli_env()`
   gives a child a private, empty cache while the lock is non-empty
   (`_lock_cache()`), so a child that imports `support` under that environment
   fails the same way. No unit does so today: the full gate passes.
3. **The documented contract holds.** A copy of the real cache (hard links)
   with `2.25.0` removed, and a directory mirror of every version's three
   assets as `WORKFLOW_MANAGER_RELEASE_SOURCE`: `python3 tests/run_all.py
   --select test_parallel_runner.py::TestFrozenInventory`, `--select
   test_parallel_runner.py::TestCiAggregateRefusals` and `--select
   test_workflow_2_6_0_hardening_disposable_repo.py::TestScenario4From231`
   each exit 0, and the run re-creates `2.25.0` in the cache before any unit
   starts. Priming (`tests/parallel/priming.py`) and the units read the same
   cache with the same pins, and the runner exports the primed directory to
   discovery and to every unit (`priming.exported`); `isolation.py` neither
   sets nor clears the cache variables.
4. **The incident's cache read is not otherwise explained.** `cached_manifest`
   takes no lock and returns `None` for any `OSError` or integrity miss
   (`src/workflow_manager/source.py`), and a concurrent writer of the same
   shared cache (`_fetch` discards a broken entry before renaming its
   successor) leaves a window in which an entry is absent. That is a candidate,
   not a proven cause, and no ordering of one run's own priming and units
   produces it. Reproducing it needs two processes racing on one cache, which
   no hermetic, deterministic test of this repository can promise.

So the contract needs no change and no fix to priming is justified: the only
thing proven is that, when the read does miss, the message hides the cause.

## 2. Decisions

**One mechanism: a cause-specific error in `support._lock_conformance`.** When
`cache.cached_manifest(version)` returns `None` **and**
`tested_releases.lock_conformance` raises `LockError` (the entry has no
counts), `_lock_conformance` raises a `LockError` of its own that says:

```
<version>: the release cache <cache directory> does not hold its verified
manifest (workflow-<version>.manifest.json) and the lock entry carries no
suite counts; fill the cache first with `python3 tests/run_all.py --list`
(every runner mode does, before any unit starts)
```

built from `tested_releases.PRIME_COMMAND` (already the repository's one
spelling of that command) and the cache root the read used. In every other case
the original `LockError` passes through unchanged: a manifest that is present
but has no `conformance` block, with no counts in the entry, keeps today's
message, because the cache is not the cause there.

**Why not a `PrimingError` from priming.** A check after `ensure` in the
priming subprocess would read the manifest the way `support` does. Priming and
units already read one cache with one set of pins (finding 3), so the check
could not fail in any state this repository can build deterministically, and a
check no test can fail is a guess, not a fix. If a real divergence is ever
caught with this item's message, that evidence is what a priming check needs.

**Why not change the report.** `InfrastructureFaultError`'s
`missing_record: no result record (runner exit 1)` hides the unit's log tail.
That is a second mechanism (the runner's reporting) and a different review
surface; it is not folded in. With this item the unit's own log, which the
runner already prints, carries the cause and the remedy.

**No contract change.** `CLAUDE.md` and `docs/ARCHITECTURE.md` already say
every run primes before it runs offline, and finding 3 shows it does.
`docs/ARCHITECTURE.md`'s "Priming" bullet gains one sentence stating what a
unit that imports `support` on an unfilled cache reports.

**`test:` and not `fix:`.** The change is in `tests/support.py` and its tests;
no shipped code (`src/`, `tools/`) changes, so the Manager has nothing to
release. The repository's own test helper is not the product.

## 3. Tests

The tests run in subprocesses of their own, and none reaches the runner's
primed cache. `_LockedRelease` (`tests/test_tested_releases.py`) gives each
case a private cache under its own temporary directory, a lock override naming
a synthetic release `7.0.2` that no pin names, and a mirror of symlinks; the
child's `PYTHONPATH` is the checkout's `src` and `tests`. So the runner under
which the gate runs them cannot fill, change or fool the cache a case reads,
and a case never writes into the repository.

`tests/test_tested_releases.py`, a new class `TestUnfilledCacheNamesTheRelease`
on `_LockedRelease`:

* **The cold import names the cause.** A lock entry with no suite counts and
  an empty private cache: a child that imports `support` exits non-zero, and
  its stderr contains `LockError`, the version, the private cache directory,
  `workflow-<version>.manifest.json` and `python3 tests/run_all.py --list`.
  Fails first at `1575e0d` (the old message names none of the last four).
* **That failure writes nothing.** The files and directories under the case's
  temporary directory (the lock, the mirror and the cache, which stays empty)
  are the same before and after the child ran, and the repository checkout is
  untouched (the case reads no path outside its temporary directory).
* **An entry with counts is unaffected.** A lock entry that carries suite
  counts imports with the private cache empty and again after `priming.prime`
  filled it from the mirror (the fallback to the entry's own counts, and the
  documented remedy, unchanged).
* **The hint is for the unfilled cache only (failure-only mutation).** The
  same entry without counts, with the cache filled: the synthetic manifest has
  no `conformance` block, so the child fails with today's message, which names
  the missing counts and does **not** contain the cache directory or the
  command. A message that always carried the hint, or an error raised without
  looking at the manifest, fails this case; a message without the cache
  directory fails the first.

Evidence at implementation: the first case fails at `1575e0d`; the four pass
after; and each of three mutations of `_lock_conformance` fails the case
named: the hint dropped from the miss path (first case), the hint added to the
present-manifest path (fourth), and the `LockError` raised without reading the
manifest (fourth). The rest of the lock-only machinery is not touched:
`python3 tests/run_all.py --select test_tested_releases.py` green.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The cause-specific lock error, its tests and the architecture note | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the lock error, its tests and the architecture note

**Files:** `tests/support.py`, `tests/test_tested_releases.py`, `docs/ARCHITECTURE.md`.

Section 2 and section 3. `_lock_conformance` in `tests/support.py`: read the
manifest once, call `tested_releases.lock_conformance`, and on a `LockError`
with `manifest is None` raise the error of section 2 (`from None`); every other
path unchanged. The new test class in `tests/test_tested_releases.py`.
`docs/ARCHITECTURE.md`, "Priming": the one sentence of section 2.

Evidence: the cold-import case fails first at `1575e0d` and the four cases
pass after; the three mutations of section 3 fail the cases named; `python3
tests/run_all.py --select test_tested_releases.py` and `--select
test_docs.py` green; the full gate `python3 tests/run_all.py` green. Nothing is
written into the repository while a run is in progress.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 19 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance, and `docs/ACTIVE_MILESTONE.md` records the milestone and the
investigation's result (not reproduced, and why). No version is edited: a
`test:` title releases nothing.

Both files stay excluded at both stages, as in every item: the acceptance step
writes them, so they are bookkeeping, not a reviewed deliverable.
`tests/support.py`, `tests/test_tested_releases.py` and
`docs/ARCHITECTURE.md` are implementation-protected.
<!-- /CP2 -->

## 5. Functional review

Every flow runs offline in a scratch checkout of the branch, outside the
repository, with a private empty cache:

* **F1, the base commit.** `cd <scratch of 1575e0d>/tests && WORKFLOW_MANAGER_RELEASE_CACHE=$(mktemp -d)
  python3 -B -c "import sys; sys.path.insert(0, '../src'); import support"`
  exits 1 with `LockError: 2.13.0: neither its manifest nor its lock entry
  carries the frozen suite counts`.
* **F2, the candidate.** The same command exits 1 and the message names
  `2.13.0`, the cache directory, `workflow-2.13.0.manifest.json` and
  `python3 tests/run_all.py --list`.
* **F3, the remedy.** With a directory mirror of the tested releases' assets
  (the form of `docs/RELEASING.md`, "Air-gapped or mirrored":
  `<dir>/<version>/` and `WORKFLOW_MANAGER_RELEASE_SOURCE=<dir>`) and the
  same empty cache, `python3 tests/run_all.py --list` exits 0 and the F2
  command then prints nothing and exits 0.

None depends on the network, on installing a package, or on the repository's
own cache.

## 6. Risks

* The incident's cause is unproven (section 1, finding 4). The item does not
  claim to remove the fault; it makes the next occurrence say what it is. If it
  recurs with a message naming a cache that priming just filled, that is the
  evidence for a priming or locking change, as its own item.
* The message could mislead where a cache holds the manifest but
  `cached_manifest` misses for an integrity reason (a corrupt entry): the
  remedy then still helps, because priming replaces a broken entry, and the
  wording says "does not hold its verified manifest".
* A lock entry that carries counts never reaches the message (it falls back to
  its own counts), so the common case is untouched.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
