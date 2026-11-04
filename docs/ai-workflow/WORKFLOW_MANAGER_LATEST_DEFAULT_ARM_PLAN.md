# Workflow Manager: The Latest-Available Line's Default-Version Arm Is Pinned and Its Docs Sentence Is True (Revision 2)

`work_item_id: latest-default-arm` -- `governing_workflow_version: "2.2"`

**Deliverable:** a test that fails when the `version == default` arm of the
explicit run's latest-available filter is deleted, and a sentence of
`docs/update.md` that no longer contradicts the sentences before it (roadmap
row 30, issue #100).

**Work item type:** `process`. **Base commit:** `d785aa8`
(`d785aa8c8af1e2725563a7fa4beeaed4c8f16804`, tip of `main`, Manager 1.14.8;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/latest-default-arm`. **Scope source:** `docs/ROADMAP.md` row 30
(added by this item, Current now, Done at acceptance). No printed text and no
behaviour changes: the pull request title is a `test:` change and **releases
nothing** (the docs sentence is part of it). Check it with
`python3 tools/release/release.py check-title "test: ..."`. One mechanism: the
default-version arm of the latest-available filter is pinned and its docs
sentence is true. Two checkpoints, one review surface: `_latest_filter`, the
one sentence about it and the one test module that already tests the explicit
run's latest.

## 1. Each item checked against main (`d785aa8`)

| Item | Still open on main? | Evidence | Action |
| --- | --- | --- | --- |
| (a) docs sentence | Yes | `docs/update.md` line 45: "a pin or the default version is always named", after the sentences that say a release whose minimum is not met, or whose cached `manager` block cannot be used, is left out | qualify it: it applies when neither this run nor the cache could read the release's `manager` block |
| (b) the `version == default` arm | Yes | `src/workflow_manager/cli.py` `_latest_filter`: `return None if version in pins or version == default else UNREADABLE`; no test module calls `_latest_filter` (`grep` over `tests/`), and deleting the arm leaves the explicit-run tests green because every one of them runs with pins | add unit tests with empty pins: a default whose block was not read is kept; one whose block was read (by the run, or from the cache) is judged like any other release |

Out of scope, stays as it is: any behaviour change of the filter; any other
page; the `Last checked with:` stamps.

## 2. Decisions

* **The arm in words.** For a release that is not built in and whose
  `manager` block this run did not read, a missing cached manifest keeps the
  release when it is a pin or the default version and drops it as `UNREADABLE`
  otherwise. The default is `_default_version`, which with no pin is an
  alias-checkout version; that is the only case in which the arm decides.
* **The docs sentence.** The bullet keeps its text up to "a damaged cached
  release that is not pinned (no readable minimum) is left out without a
  mention" and then says: "while a pin or the default version whose `manager` block
  neither this run nor the cache could read is kept (one whose block was read
  is judged like any other release)". The words "is always named" go.
  `_latest_filter` reads the run's block first (`metadata.blocks`, filled by
  `gather_metadata` from the listing or the target, with no cache entry
  needed) and only then the cache, so "no cached manifest" alone does not
  decide the case.
* **Unit tests, not end-to-end tests.** The explicit-run tests build a
  mirror whose releases are all pins; the default can be a non-pin only with
  an alias checkout. The tests call `cli._latest_filter` with injected
  arguments (a fake cache whose `cached_manifest` returns the manifest bytes
  the case names, or `None`; empty pins). It starts no process, touches no file and no network, so there is
  nothing to write and no no-write proof beyond that.

## 3. Tests (`tests/test_release_metadata.py`)

New class `TestTheLatestFilterKeepsTheDefault` (a plain `unittest.TestCase`,
next to `TestTheListedReleasesOfTheMetadata`), versions `7.0.x` (above the
built-in data):

```python
class TestTheLatestFilterKeepsTheDefault(unittest.TestCase):
    def needs(self, pins, default, blocks=None, cached=None):
        cache = SimpleNamespace(cached_manifest=lambda version: (cached or {}).get(version))
        metadata = comp.ReleaseMetadata(blocks=blocks or {})
        return cli_module._latest_filter(cache, metadata, pins, default)

    def test_the_default_version_with_no_pins_is_kept_without_a_manifest(self):
        needs = self.needs((), "7.0.9")
        self.assertIsNone(needs("7.0.9"))
        self.assertIs(needs("7.0.8"), comp.UNREADABLE)

    def test_a_pin_is_kept_without_a_manifest_and_a_release_that_is_neither_is_not(self):
        needs = self.needs(("7.0.1",), "7.0.9")
        self.assertIsNone(needs("7.0.1"))
        self.assertIsNone(needs("7.0.9"))
        self.assertIs(needs("7.0.8"), comp.UNREADABLE)

    def test_a_default_whose_minimum_the_run_read_and_not_met_is_dropped(self):
        blocks = {"7.0.9": ManagerBlock(min_manager_version="99.0.0")}
        with mock.patch.object(cli_module, "_installed_version", return_value="1.14.8"):
            needs = self.needs((), "7.0.9", blocks)
            self.assertEqual(needs("7.0.9"), "99.0.0")

    def test_a_default_whose_cached_block_is_read_is_judged_like_any_other_release(self):
        cached = {
            "7.0.9": b'{"manager": {"schema_version": 1, "min_manager_version": "99.0.0"}}',
            "7.0.8": b'{"manager": 5}',
            "7.0.7": b'{}',
        }
        with mock.patch.object(cli_module, "_installed_version", return_value="1.14.8"):
            for default, expected in (("7.0.9", "99.0.0"), ("7.0.8", comp.MALFORMED_BLOCK),
                                      ("7.0.7", None)):
                with self.subTest(default=default):
                    self.assertEqual(self.needs((), default, cached=cached)(default), expected)
```

`TestTheDocs` of the same module gains
`test_the_latest_available_bullet_qualifies_the_kept_pins`: it reads
`docs/update.md`, requires the sentence of section 2 (whitespace
normalised) and requires that "is always named" is absent. The rest of the
module and every other test stay unedited and green.

**Failure-only mutations** (a scratch clone, never this repository; each passes
on the real code and must fail as stated, one
`python3 tests/run_all.py --select test_release_metadata.py` each):

| Mutation | Must fail |
| --- | --- |
| delete `or version == default` from `_latest_filter` | `test_the_default_version_with_no_pins_is_kept_without_a_manifest` and the pin-and-default case of the second test |
| delete `version in pins or` (keep only the default arm) | `test_a_pin_is_kept_without_a_manifest_...` |
| make the default skip the run's block (`if version == default: return None` as the first line of `needs`, after the built-in check) | `test_a_default_whose_minimum_the_run_read_and_not_met_is_dropped` |
| make the default skip the cache's block (`if version == default: return None` immediately before `manifest = cache.cached_manifest(version)`) | `test_a_default_whose_cached_block_is_read_is_judged_like_any_other_release`, the `7.0.9` and `7.0.8` subtests (`7.0.7` stays green) |
| restore "is always named" in `docs/update.md` | `test_the_latest_available_bullet_qualifies_the_kept_pins` |

Evidence at implementation: the new tests (four) green on the real code, each
mutation failing the case named, `python3 tools/check_docs.py` and
`python3 tests/run_all.py --select test_docs.py` on the page change, then the
full gate `python3 tests/run_all.py`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The arm test and the true sentence | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the arm test and the true sentence

**Files:** `tests/test_release_metadata.py`, `docs/update.md`.

Sections 2 and 3. `tests/test_release_metadata.py` gains the new class (four tests) and the
docs test; it already imports `cli_module`, `comp`, `SimpleNamespace`, `mock`
and `ManagerBlock`. `docs/update.md` changes one sentence of the `Latest
available` bullet. `src/workflow_manager/cli.py` is not edited.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 30 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: a `test:` title releases nothing. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 5. Functional review

Flows 1 to 7 run offline with `python3 -I -B` only (`-I` alone does not stop bytecode being written), outside the repository, in a
small scratch, with no network, no `gh`, no installs, no sockets, no zlib-ng
and **no** Workflow release cache; none bootstraps a release and none needs
one. Flow 8 is the one flow that needs the full environment.

Setup: `S=$(mktemp -d "$HOME/.cache/lda-fr.XXXXXX"); mkdir -p $S/base
$S/cand $S/mut` (deleted when the flows finish);
`git archive d785aa8c8af1e2725563a7fa4beeaed4c8f16804 src docs | tar -x -C $S/base`;
`git archive HEAD src docs | tar -x -C $S/cand` (HEAD is the candidate).
Snippet `$S/f.py` (argument: the tree to read; it starts no process and, run with
`-I -B`, writes nothing):

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

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `grep -n "Latest available" $S/base/docs/update.md` and the same for `$S/cand`, then `diff` of the two bullets | base: "while a pin or the default version is always named"; candidate: "while a pin or the default version whose `manager` block neither this run nor the cache could read is kept (one whose block was read is judged like any other release)"; no other line of the page differs |
| 2 | `python3 -I -B $S/f.py $S/cand/`, line 1 | `['UNREADABLE', 'UNREADABLE', None]`: the default is kept, a release that is neither pin nor default is not |
| 3 | the same, line 2 | `[None, 'UNREADABLE', None]` |
| 4 | the same, line 3 | `['UNREADABLE', 'UNREADABLE', '99.0.0']`: a default whose minimum the run read and which is not met is dropped, not kept, with no cached manifest |
| 5 | the same, line 4 | `['UNREADABLE', 'UNREADABLE', '99.0.0']`: the same for a default whose minimum is read from the cache |
| 6 | `python3 -I -B $S/f.py $S/base/` and `diff` with the candidate's output | identical: the filter is the same, only the page and the tests changed |
| 7 | `cp -r $S/cand/src $S/mut/` (`$S/mut` exists from the setup), delete `or version == default` from `$S/mut/src/workflow_manager/cli.py`'s `_latest_filter` with `sed`, run `python3 -I -B $S/f.py $S/mut/` | line 1 now reads `['UNREADABLE', 'UNREADABLE', 'UNREADABLE']`: without the arm the default is dropped, which is what the new test catches; listing `$S` recursively before and after every flow shows no file written but the scratch copy and `$S/mut/src` |
| 8 | (needs the full environment: network or a primed release cache) in a clone made with `git clone --no-hardlinks "$PWD" $S/clone` at the candidate: `python3 tests/run_all.py --select test_release_metadata.py --select test_docs.py` | exit 0 |

## 6. Risks

* The tests patch `_installed_version` only in the cases that read a
  block, for the duration of the call; nothing else is patched.
* The docs test pins a sentence, so a later rewording of the bullet updates
  both; that is the point.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
