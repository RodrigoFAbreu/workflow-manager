# Active Milestone

## Milestone

`cache-miss-message` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `e162738`, branch `milestone/cache-miss-message`): roadmap row 21 (#128, items 3 to 5). A `test:` pull request title (releases nothing). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_CACHE_MISS_MESSAGE_PLAN.md`.

The cache-miss `LockError` raised in `_lock_conformance` (`tests/support.py`) names one remedy and the exact cause, and the no-write test's snapshot compares contents. Nothing under `src/` changes.

### CP1: the message, the constant and the tests -- complete

- `NO_SUITE_COUNTS` in `tests/tested_releases.py`; `support` builds the cache-miss message from it ("holds no verified manifest", `--list`, "using the same cache setting") and no longer appends to the original text, so `release_lock.py add` appears only when the manifest is readable.
- `tree()` in `tests/test_tested_releases.py` maps each path to its SHA-256; new cases for an incomplete entry, a digest mismatch and a snapshot that sees a rewrite.

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 21 is Current and is Done at acceptance. No version is edited.

### Mutation results (scratch clone of `1900364`, `python3 tests/run_all.py --select test_tested_releases.py`)

The candidate passes: 12 of 12 units, 53 tests, exit 0. Each mutation exits 1 and fails exactly the cases the plan names:

| Mutation | Failed |
| --- | --- |
| `support` appends `{exc}` to the original text again | cold import, incomplete entry, digest mismatch |
| the message loses `using the same cache setting` | cold import, incomplete entry, digest mismatch |
| the message says `does not hold the verified manifest` | cold import, incomplete entry, digest mismatch |
| the `if manifest is not None` re-raise is removed | `test_the_hint_is_for_the_unfilled_cache_only` |
| the cache-miss branch rewrites the lock file (trailing newline) | the three no-write cases |
| `tree()` returns names only | `test_the_snapshot_sees_a_rewrite` |

The scratch clone is deleted; the repository was never mutated.

## Functional review checklist

Scope: the message `_lock_conformance` raises when a lock-only release's manifest cannot be read from the release cache, and the no-write test's snapshot. Plan section 5 holds the flows F1 to F4; this checklist repeats them with the sandbox setup they need.

### Setup

- **Tools:** `python3` and `git` from the system directories (not a user venv or a pyenv shim). No network, `gh`, `claude`, `codex` or `ssh` is used by any flow below.
- **Scratch clone, outside the product clone:** `git clone <product clone> "$TMPDIR/cmm/wm"`, then `git -C "$TMPDIR/cmm/wm" checkout milestone/cache-miss-message`. The code under test is `1900364` (`tests/support.py`, `tests/tested_releases.py`, `tests/test_tested_releases.py`). Every edit below is made in that clone only, never in the product clone.
- **Release cache, copied:** `cp -a ~/.cache/workflow-manager/releases "$TMPDIR/cmm/releases"` and `export WORKFLOW_MANAGER_RELEASE_CACHE="$TMPDIR/cmm/releases"` (also `HOME` and `XDG_CACHE_HOME` into `$TMPDIR/cmm` if you run with a scratch `HOME`). Every run primes every tested version before its first unit: the copy must hold each one (the pins `2.3.1` to `2.12.0` and the lock's entries). A version it lacks needs the network and fails as `PrimingError` (exit 2). That is an environment fault, not a defect.
- **Test data:** none to seed. The tests build their own private caches and local mirrors and remove them at their end.

### Flows

| Flow | Do | Expect |
| --- | --- | --- |
| F1 | In the scratch clone: `python3 tests/run_all.py --select test_tested_releases.py --select test_release_workflows.py` | exit 0. Recorded reference: `test_tested_releases.py` 12 of 12 units, 53 tests; `test_release_workflows.py` 33 tests OK (the substring `TestAssertFullPlan` pins still hold). |
| F2 | In the scratch clone, change the cache-miss message in `tests/support.py` to append `{exc}` to the original text again, then `python3 tests/run_all.py --select test_tested_releases.py` | exit 1. The cold-import, incomplete-entry and digest-mismatch cases fail. Restore the file afterwards (or discard the clone). |
| F3 | In the scratch clone, make the cache-miss branch of `_lock_conformance` rewrite the file named by `WORKFLOW_MANAGER_TESTED_RELEASES` with the same text plus a trailing blank line, then run the F2 command | exit 1. The three no-write cases fail. |
| F4 | In the scratch clone, make `tree()` return `{path.relative_to(self.tmp) for path in self.tmp.rglob("*")}` again, then run the F2 command | exit 1. `test_the_snapshot_sees_a_rewrite` fails. |
| F5 | Read, do not run: `tests/support.py` (`_lock_conformance`, the cache-miss `LockError`) and `NO_SUITE_COUNTS` in `tests/tested_releases.py` | The cache-miss text names the release, the cache directory, the asset, `holds no verified manifest`, `tests/run_all.py --list` and `using the same cache setting`. It does not name `release_lock.py add`. The `release_lock.py add` remedy appears only in the `lock_conformance` text, which is for a readable manifest without a block. |

### Environment, not defects

- A `PrimingError` (exit 2) from a missing cache version, or an `OrphanCheckUnavailableError` (exit 2) on a host without the subreaper check, is the environment.
- A flow that reaches a stand-in (`gh`, `claude`, `codex`, `ssh`) is a bug in the flow, not the product: none of F1 to F5 should.
- A write refused on a link inside the clone is the sandbox limit (`environment`). The runner's run directories are outside the clone.

### Known limitations (out of scope)

- Nothing under `src/` changes, and no version is edited (a `test:` pull request, which releases nothing).
- The message's wording is pinned by substrings in the tests, not by its full text. F5 is the only check of the whole sentence.
- No flow reaches the network, so the priming of a missing version (the real cold start on a new machine) is not exercised here.
- The full gate ran at `062713e` (exit 0, 2322 of 2322 units, 15364 tests). Code is unchanged since `1900364`; only docs and state changed after it.

## Next action

Functional review (`/review-functional` when it is ready, then `/accept-milestone`). Findings go to `.ai-review/cache-miss-message/feedback/FUNCTIONAL_REVIEW.md`.
