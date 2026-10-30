# Active Milestone

## Milestone

`cache-miss-message` -- in implementation (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `e162738`, branch `milestone/cache-miss-message`): roadmap row 21 (#128, items 3 to 5). A `test:` pull request title (releases nothing). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_CACHE_MISS_MESSAGE_PLAN.md`.

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

## Next action

Self-review, the full gate, then the implementation review bundle.
