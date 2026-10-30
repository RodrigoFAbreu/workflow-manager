# Active Milestone

## Milestone

`release-cache-priming` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `1575e0d`, branch `milestone/release-cache-priming`): roadmap row 19 (#125). A `test:` pull request title (releases nothing). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RELEASE_CACHE_PRIMING_PLAN.md`.

When `tests/support.py` cannot read a lock-only release's manifest from the release cache and the lock entry carries no suite counts, its `LockError` now names the release, the cache directory, the missing manifest and `python3 tests/run_all.py --list`, which fills the cache. The original error text stays first.

Investigation result (issue #125): the fault of 2026-10-28 (three host modules faulted at import after `release_lock.py add 2.24.0`, then passed after a `--list`) **did not reproduce**. With an empty cache and a mirror, priming fills the cache and the same modules pass; priming and the units read the same cache with the same pins. The only deterministic fact is that, when the read misses, the message hid the cause. A race on a shared cache is a candidate, not a proven cause, and cannot be reproduced hermetically; so the item makes the error self-explaining and changes nothing else. Priming, the runner, `src/` and the contract are untouched.

Not in this milestone: the two test-strength items of the previous item (issue #128, the next item), a change to priming or to the runner, a change to `InfrastructureFaultError`'s report.

### CP1: the lock error, its tests and the architecture note -- complete

- `tests/support.py`: `_lock_conformance` reads the manifest once and raises the cache-aware `LockError` (`from None`) only when the manifest is absent; every other path is unchanged.
- `tests/test_tested_releases.py`: the new test class (cold import, original text first, other paths unchanged); `tests/test_release_workflows.py` is back to its base content.
- `docs/ARCHITECTURE.md`, "Priming": the one sentence.

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 19 is Current and becomes Done at acceptance. No version is edited.

### Self-review -- complete

- No blocking or important finding; no code change. One deviation from the plan's section 2, kept on purpose: the new message starts with the original `LockError` text and then names the cache, the manifest and the remedy, so an existing reader of the original text (`tests/test_release_workflows.py`) stays at its base content.
- Evidence: at the base `1575e0d` (its `tests/support.py`, the new test file) only the cold-import case fails; the three mutations of the plan's section 3 each fail the case named (hint dropped from the miss path: cold import; hint added to the present-manifest path: the hint-only case; the manifest not read, scoped to the synthetic release so the parent's own import survives: the hint-only case). `--select test_tested_releases.py --select test_docs.py` exited 0; the full gate (`python3 tests/run_all.py`) exited 0 at head `0c87cd2` (2321 of 2321 units, 15353 tests, orphan check on).
