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

## Functional review checklist

Code under test: `6a89e3f` (`tests/support.py`, `tests/test_tested_releases.py`, `docs/ARCHITECTURE.md`; nothing under `src/` changes). The automated gate above is current: nothing under `src/`, `tools/`, `tests/` or `docs/ARCHITECTURE.md` changed after `0c87cd2`.

### Setup (offline: no network, no GitHub, no `claude`, `codex` or `ssh`)

Write only under a scratch directory. Never run `git worktree`, or any write, in the product clone; clone it instead (a clone only reads its source):

```
SCR="$(mktemp -d)"; git clone -q <product clone> "$SCR/wm"
mkdir -p "$SCR/home" && export HOME="$SCR/home" TMPDIR="$SCR"
```

Build the mirror from the release cache (copies the three assets of each cached version; nothing is fetched):

```
MIRROR="$SCR/mirror"
for d in ~/.cache/workflow-manager/releases/*/; do
  v=$(basename "$d"); [ -f "$d/complete" ] || continue
  mkdir -p "$MIRROR/$v" && cp "$d/workflow-$v.tar.gz" "$d/workflow-$v.manifest.json" "$d/SHA256SUMS" "$MIRROR/$v/"
done
```

Check out the commit under test in the clone (`git -C "$SCR/wm" checkout -q <commit>`) and give each flow an empty release cache: `EMPTY="$(mktemp -d "$SCR/empty-XXXX")"`.

Test data: none. The lock (`tests/tested_releases.json`) supplies it: `2.13.0` is its first entry without suite counts.

### Flows

- **F1, the base (before the change).** Check out `1575e0d`, then `cd "$SCR/wm/tests" && WORKFLOW_MANAGER_RELEASE_CACHE="$EMPTY" python3 -B -c "import sys; sys.path.insert(0, '../src'); import support"`.
  Expected: exit 1; the last line is `tested_releases.LockError: 2.13.0: neither its manifest nor its lock entry carries the frozen suite counts (...)`. Nothing in it names the cache, the manifest or `--list`.
- **F2, the candidate.** Check out `6a89e3f` and run F1's command again with the same `$EMPTY`.
  Expected: exit 1; the message starts with the same text as F1, then names `2.13.0`, the cache directory `$EMPTY`, `workflow-2.13.0.manifest.json` and `python3 tests/run_all.py --list`.
- **F3, the remedy.** At `6a89e3f`, with `EMPTY2="$(mktemp -d "$SCR/empty-XXXX")"`: `cd "$SCR/wm" && WORKFLOW_MANAGER_RELEASE_SOURCE="$MIRROR" WORKFLOW_MANAGER_RELEASE_CACHE="$EMPTY2" python3 -B tests/run_all.py --list`.
  Expected: exit 0, and `$EMPTY2` is filled (about 70 entries: `ls "$EMPTY2" | wc -l`). Then F2's import command with `WORKFLOW_MANAGER_RELEASE_CACHE="$EMPTY2"` prints nothing and exits 0.

### Known limitations

- This does not reproduce or fix the 2026-10-28 fault (issue #125). The investigation above did not reproduce it; the change only makes a cache miss name its cause. Priming, the runner, `src/`, `InfrastructureFaultError`'s report and the contract are unchanged.
- F1-F3 cover the import path only. The unit cases and the mutations are automated evidence, not part of this checklist.
- F3 needs the mirror. Without it the remedy cannot run offline; that is a sandbox limit, not a product defect.
- Out of scope: the two test-strength items (issue #128, the next item).
