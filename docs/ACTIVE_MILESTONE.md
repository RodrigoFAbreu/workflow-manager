# Active Milestone

## Milestone

`latest-default-arm` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `d785aa8`, branch `milestone/latest-default-arm`): roadmap row 30 (#100). A `test:` pull request title (releases nothing).

The default-version arm of the filter that keeps a release this Manager cannot use out of the explicit run's latest (`_latest_filter`) is pinned by tests, and the `Latest available` bullet of `docs/update.md` no longer says a pin or the default version is "always named": the keep applies to a release whose `manager` block neither the run nor the cache could read. No behaviour, printed text or exit code changes; no Workflow change.

### CP1: the arm test and the true sentence -- complete

- `tests/test_release_metadata.py` (`TestTheLatestFilterKeepsTheDefault`, four tests, and the docs test), `docs/update.md` (the one sentence) (commit `3fff782`).

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 30 is Done (accepted by policy); this record.

### Failure-only mutations

Plan section 3, run in a scratch clone at `3fff782` and again at self-review on `ae06bf1`, one `python3 tests/run_all.py --select test_release_metadata.py` each: the unmutated clone exit 0; all five mutations exit 1, each failing the test the plan names (delete `or version == default`: the default-with-no-pins test and the pin test; delete `version in pins or`: the pin test; the default skips the run's block: the unmet-minimum test, and the cached-block test too, since that early return skips both block sources; the default skips the cache's block: the cached-block test, subtests `7.0.9` and `7.0.8`; the qualification removed from `docs/update.md`: the docs test). The bundle's `TEST_RESULTS.md` has the table.

### Self-review

The diff against `d785aa8` was read against plan sections 2 and 3: no finding, no code change. `src/workflow_manager/cli.py` is not edited; no user page still says "is always named".

## Functional review checklist

Plan section 5 is the source. Flows 1 to 7 run offline in a scratch directory,
with `python3 -I -B` only: no network, no `gh`, no release cache, no sockets, no
install. Flow 8 is the one flow that needs the full environment and is run by
the user, not in the offline sandbox.

**Automated verification (current):** the full gate `python3 tests/run_all.py`
at `ae06bf1` exited 0 (2330/2330 units, 15550 tests; `TEST_RESULTS.md` in the
bundle). Nothing under `src/`, `tests/` or `tools/` has changed since, so the
run stays equivalent.

### Setup

- The candidate is the branch tip reported in the functional-review step. It
  is not the product clone; the flows only read it through `git archive`.
- Scratch, outside the product clone (the path below is an example; any
  writable scratch directory will do):
  `S=$(mktemp -d "$HOME/.cache/lda-fr.XXXXXX"); mkdir -p $S/base $S/cand $S/mut`
- `git archive d785aa8c8af1e2725563a7fa4beeaed4c8f16804 src docs | tar -x -C $S/base`
- `git archive HEAD src docs | tar -x -C $S/cand`
- Write this snippet to `$S/f.py` with a heredoc. It starts no process and,
  run with `-I -B`, writes nothing. Its argument is the tree to read.

```python
import sys
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0, sys.argv[1] + "/src")
import workflow_manager.cli as cli
import workflow_manager.compatibility as comp
from workflow_manager.release import ManagerBlock
CACHED = {"7.0.9": b'{"manager": {"schema_version": 1, "min_manager_version": "99.0.0"}}'}
def run(pins, default, blocks=None, cached=None):
    cache = SimpleNamespace(cached_manifest=lambda version: (cached or {}).get(version))
    f = cli._latest_filter(cache, comp.ReleaseMetadata(blocks=blocks or {}), pins, default)
    with mock.patch.object(cli, "_installed_version", return_value="1.14.8"):
        return ["UNREADABLE" if f(v) is comp.UNREADABLE else f(v) for v in ("7.0.1", "7.0.8", "7.0.9")]
print("no pins, default 7.0.9:", run((), "7.0.9"))
print("pin 7.0.1, default 7.0.9:", run(("7.0.1",), "7.0.9"))
print("incompatible default read by the run:", run((), "7.0.9", {"7.0.9": ManagerBlock(min_manager_version="99.0.0")}))
print("incompatible default read from the cache:", run((), "7.0.9", None, CACHED))
```

### Test data

None. The flows use the snippet's in-memory fake cache; no release files are
needed.

### Flows

| # | Steps | Expected result |
| --- | --- | --- |
| 1 | `grep -n "Latest available" $S/base/docs/update.md` and the same for `$S/cand/docs/update.md`; then `diff $S/base/docs/update.md $S/cand/docs/update.md` | Base: "while a pin or the default version is always named". Candidate: "while a pin or the default version whose `manager` block neither this run nor the cache could read is kept (one whose block was read is judged like any other release)". The diff touches that one line only. |
| 2 | `python3 -I -B $S/f.py $S/cand/`, line 1 | `['UNREADABLE', 'UNREADABLE', None]`: the default is kept; a release that is neither a pin nor the default is not. |
| 3 | The same command, line 2 | `[None, 'UNREADABLE', None]`: a pin is kept; the other releases are not. |
| 4 | The same command, line 3 | `['UNREADABLE', 'UNREADABLE', '99.0.0']`: a default whose minimum the run read and that is not met is dropped, not kept, with no cached manifest. |
| 5 | The same command, line 4 | `['UNREADABLE', 'UNREADABLE', '99.0.0']`: the same for a default whose minimum is read from the cache. |
| 6 | `python3 -I -B $S/f.py $S/base/` and `python3 -I -B $S/f.py $S/cand/`; `diff` the two outputs | Identical. The filter is unchanged; only the page and the tests changed. |
| 7 | `cp -r $S/cand/src $S/mut/`; `sed -i 's/ or version == default//' $S/mut/src/workflow_manager/cli.py`; `python3 -I -B $S/f.py $S/mut/`, line 1 | `['UNREADABLE', 'UNREADABLE', 'UNREADABLE']`: without the arm the default is dropped, which the new unit test catches. |
| 8 | User environment only. In a clone made with `git clone --no-hardlinks "$PWD" $S/clone` at the candidate, run `python3 tests/run_all.py --select test_release_metadata.py --select test_docs.py` (needs network or a primed release cache) | Exit 0. |

After the flows, `find $S -name __pycache__` prints nothing, and the product
clone has no new or changed file. Remove `$S` when done.

### Known limits (out of scope)

- No end-to-end flow through `workflow-manager update` for the default arm: the
  explicit-run tests use pins, and a non-pin default needs an alias checkout, so
  the arm is verified at unit level only.
- No change to the filter, to any other page, to printed text, to exit codes,
  or to the `Last checked with:` stamps.

### Reporting

Findings go to the path the functional-review step prints, not a fixed flat
path. Report each flow number with the observed output.

## Next action

No incomplete milestone is left in `docs/ROADMAP.md` (row 30 was the last), and the repository declares no backlog. Pull request #163 (`test:`, releases nothing) is ready to merge; then `/milestone-plan` for the next item once one is added.
