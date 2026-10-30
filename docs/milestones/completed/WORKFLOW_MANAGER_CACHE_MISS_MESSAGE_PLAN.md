# Workflow Manager: One Remedy and an Exact Cause in the Cache-Miss Message, and a Test That Sees a Rewritten Lock (Revision 2)

`work_item_id: cache-miss-message` -- `governing_workflow_version: "2.2"`

**Deliverable:** the error `tests/support.py` raises when a lock-only release's
manifest cannot be read from the release cache (roadmap row 19, issue #125) names
one remedy, the right cause and the right cache; and the test that says the
failure writes nothing can now tell that a lock file was rewritten.

**Work item type:** `process`. **Base commit:** `e162738` (tip of `main`;
Workflow 2.25.0 installed, automatic gates). **Branch:**
`milestone/cache-miss-message`. **Scope source:** `docs/ROADMAP.md` row 21
(items 3 to 5 of issue #128). Tests only: nothing under `src/` changes, so the
pull request title is `test: ...`, which releases nothing (checked with
`python3 tools/release/release.py check-title`). One mechanism: the wording of
that one error and the tests that pin it. Two checkpoints.

## 1. The three points

1. **Two remedies.** `lock_conformance` raises "... carries the frozen suite
   counts (`tools/release_lock.py add` writes them)" and `support` appends
   "fill the cache first with `python3 tests/run_all.py --list`". When the
   cache is unfilled the first remedy is wrong: `add` is not what is missing.
2. **A test that cannot see a rewrite.** `tree()` in
   `tests/test_tested_releases.py` returns path names, so
   `test_the_failure_writes_nothing` passes if the failing import rewrites
   `tested_releases.json` in place.
3. **A cause stated too narrowly, a remedy stated too widely.** The message
   says the cache "does not hold the verified manifest", but
   `ReleaseCache.cached_manifest` also answers `None` for an entry with no
   `complete` marker and for manifest bytes that do not match the pin's digest.
   And `--list` fills the cache the failing process reads only if both use the
   same cache setting: a child started with `support.cli_env()` reads a private
   cache (`_lock_cache()`) that a separately run `--list` does not fill.

## 2. Decisions

* **Keep the original cause first, drop the parenthetical in the unfilled
  case.** `TestAssertFullPlan` (`tests/test_release_workflows.py`) pins the
  substring `neither its manifest nor its lock entry carries the frozen suite
  counts`. That substring stays the start of the message, so that test is not
  edited and is not declared: the item needs no second file for its sake.
  The text moves to a constant, `NO_SUITE_COUNTS`, in `tests/tested_releases.py`;
  `lock_conformance` keeps raising `"<v>: <NO_SUITE_COUNTS> (`tools/release_lock.py
  add` writes them)"` (right when the manifest is readable and lacks a block);
  `support` builds the cache-miss message itself from the same constant and
  does not append to the original, so the two remedies never meet.
* **The message, for a manifest the cache cannot serve:**
  `<v>: <NO_SUITE_COUNTS>; the release cache <root> holds no verified manifest
  (<asset>) of <v>: fill the cache first with `python3 tests/run_all.py --list`,
  using the same cache setting (`WORKFLOW_MANAGER_RELEASE_CACHE`, else
  `XDG_CACHE_HOME`/`HOME`, which `source.cache_root()` resolves in that order)
  as the failing process (every runner mode but `--restore-barrier` primes
  before any unit starts)`.
* **A snapshot compares contents, by digest.** `tree()` maps each path to the
  SHA-256 of its bytes (`None` for a directory, the link target for a symlink),
  so a rewrite with unchanged names changes it and the snapshot's memory does
  not grow with the bytes under the tree. A primed case's tree holds every
  version of the tested set (`priming.prime` resolves each: the 13 pins `2.3.1`
  to `2.12.0` plus the lock's, about 157 MB in about 1,050 files), so holding
  bytes would cost hundreds of MB per snapshot; digests are read file by file
  and dropped. Snapshotting only the lock and the version's own entry would be
  cheaper still but would not prove that nothing else was written.
* **No change to `docs/ARCHITECTURE.md`.** Its note says the error names the
  release, the cache directory and the `--list` command; it does not quote the
  message, and stays true.

## 3. Tests

All in `tests/test_tested_releases.py`, class `TestUnfilledCacheNamesTheRelease`
(a private cache and the hermetic mirror; no network, no thread, no process
left behind; nothing added to `tests/parallel/resources.json`).

* **The cold import** (changed): the message holds the release, the cache, the
  asset name, `holds no verified manifest`, the `--list` command and `using the
  same cache setting`; it does not hold `release_lock.py add` or `does not
  hold`; the original cause still precedes the cache.
* **An incomplete entry** (new): prime, remove the entry's `complete` marker,
  import `support`: the same message (the cache is named, `holds no verified
  manifest`, one remedy).
* **A manifest that does not match its digest** (new): prime, overwrite the
  cached `tree/` manifest with other bytes, import: the same message.
* **A filled cache stays unblamed** (changed): the message holds the
  `release_lock.py add` remedy, not the cache, not the `--list` command.
* **Each failure writes nothing** (changed, three cases): the snapshot of the
  whole temporary tree, content digests included, is equal before and after the
  failing import (cold, incomplete entry, digest mismatch); the cold case also
  asserts the cache directory was not created.
* **The snapshot sees a rewrite** (new): a file rewritten with other bytes and
  the same name makes two snapshots differ; so does a file added and another removed under a
  directory.

**Failure-only mutations** (applied to a scratch clone, never to the
repository; each passes on the real code, fails as stated):

| Mutation | Must fail |
| --- | --- |
| `support` appends to the original text again (`f"{exc}; ..."`) | cold import, incomplete entry, digest mismatch |
| the cache-miss message loses `using the same cache setting` | cold import, incomplete entry, digest mismatch |
| the cache-miss message says `does not hold the verified manifest` | cold import, incomplete entry, digest mismatch |
| the cache-miss branch also fires when the manifest is readable (the `if manifest is not None` re-raise removed) | filled cache stays unblamed |
| the cache-miss branch rewrites the lock file with the same names and other bytes (whitespace) | all three no-write cases |
| `tree()` returns names only again | the snapshot-sees-a-rewrite case (the no-write cases then pass, which is the gap) |

Evidence at implementation: the new cases pass on the candidate; each mutation
fails the cases named; `python3 tests/run_all.py --select
test_tested_releases.py` and `--select test_release_workflows.py` green (the
second to show the pinned substring still holds); the full gate
`python3 tests/run_all.py` green.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The message, the constant and the tests | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the message, the constant and the tests

**Files:** `tests/tested_releases.py`, `tests/support.py`, `tests/test_tested_releases.py`.

Section 2 and section 3. `NO_SUITE_COUNTS` and its use in `lock_conformance`;
`_lock_conformance` in `tests/support.py` builds the cache-miss message from
the constant; `tree()` and the cases of section 3 in the test file.

`tests/test_release_workflows.py` and `src/workflow_manager/source.py` are
deliberately not edited and not classified by the artifact declaration, so a
stray edit to either fails closed.

Evidence: section 3's. Nothing is written into the repository while a run is
in progress.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 21 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance, and `docs/ACTIVE_MILESTONE.md` records the milestone and the
mutation results. No version is edited: a `test:` title releases nothing.

Both files stay excluded at both stages, as in every item: the acceptance step
writes them. The three test paths of CP1 are implementation-protected.
<!-- /CP2 -->

## 5. Functional review

Every flow runs offline with python3 and git only, in a scratch clone of the
branch with a copied release cache (`WORKFLOW_MANAGER_RELEASE_CACHE` pointing
at the copy), outside the repository. Run `python3 tests/run_all.py --list`
first in the clone if the copied cache may lack a version.

| Flow | Do | Expect |
| --- | --- | --- |
| F1 | In the scratch clone, `python3 tests/run_all.py --select test_tested_releases.py --select test_release_workflows.py` | exit 0; the new and changed cases pass, nothing fails |
| F2 | In the scratch clone, change the cache-miss message in `tests/support.py` to append to `{exc}` again (restoring the `release_lock.py add` remedy), then `python3 tests/run_all.py --select test_tested_releases.py` | exit 1; the cold-import, incomplete-entry and digest-mismatch cases fail |
| F3 | In the scratch clone, make the cache-miss branch of `_lock_conformance` rewrite the file named by `WORKFLOW_MANAGER_TESTED_RELEASES` with the same text plus a trailing blank line, then run the F2 command | exit 1; the three no-write cases fail |
| F4 | In the scratch clone, make `tree()` return `{path.relative_to(self.tmp) for path in self.tmp.rglob("*")}` again, then run the F2 command | exit 1; the snapshot-sees-a-rewrite case fails |

## 6. Risks

* A reworded message could break a pinned substring elsewhere; the one known
  pin (`TestAssertFullPlan`) is kept by construction and run in CP1.
* The two new primed cases prime the cache from the mirror, as two existing
  cases do. `priming.prime` copies and extracts every version of the tested set,
  about 157 MB in about 1,050 files on the shared tmpfs per primed case, while
  the parallel runner has other units running; the cases add no cost beyond
  what the existing primed cases already pay, and each case's temporary tree is
  removed at its end.
* Hashing every file under a primed case's temporary tree reads those ~157 MB
  once per snapshot (two per case) but holds only the digests, a few dozen KB;
  the mirror lives outside the tree.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
