# Workflow Manager: The Bounded-Read Tests Identify What They Count (Revision 3)

`work_item_id: discovery-test-cleanup` -- `governing_workflow_version: "2.2"`

**Deliverable:** the descriptor probe and its positive control in
`tests/test_discovery.py` decide "this host can list sockets" by the probe's
own wording and decide from what the first existing directory lists, and
identify the socket pair's own links instead of counting new ones; four lines
of dead setup go (roadmap row 31,
issue #131, items 1 to 3).

**Work item type:** `process`. **Base commit:** `fd423fa`
(`fd423fa4bf8e53d4e8e2af13986e5152b6de489d`, tip of `main`, Manager 1.14.8;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/discovery-test-cleanup`. **Scope source:** `docs/ROADMAP.md` row 31
(added by this item, Current now, Done at acceptance). Test code only: no
`src/` change, no printed text. The one behaviour of a test that changes: on a
host whose descriptor directory exists but lists no links, the control now
skips with the probe's reason instead of failing (section 2). The pull-request title is
a `test:` change and **releases nothing**; check it with
`python3 tools/release/release.py check-title "test: ..."`. One mechanism: the
bounded-read tests identify what they count. Two checkpoints, one file, one
review surface.

## 1. Each item checked against main (`fd423fa`)

| Item of #131 | Still open on main? | Evidence | Action |
| --- | --- | --- | --- |
| 1. control decides with a literal `/proc/self/fd`, own skip wording | Yes | `test_the_helper_sees_a_socket_it_just_opened` tests `os.path.isdir("/proc/self/fd")` and skips with `"/proc/self/fd is absent on ..."`; the probe `_require_socket_links` reads `_FD_DIRECTORIES` and words its skip as "descriptor directories (...) do not expose socket links on ...; the leak check would compare empty with empty" | decide with `_FD_DIRECTORIES`, skip with the probe's one wording (shared function) |
| 2. count "two new links" in a before/after difference | Yes | the control asserts `len(_socket_links() - before) == 2` and `_socket_links() - before == set()`; the probe asserts `len(shown) < 2` over the same difference | look for the pair's own `socket:[<inode>]` links (`os.fstat` of each end), in the control and in the probe, which share the count and the defect |
| 3. dead setup | Yes | `raw.recv_into = lambda buf, *a: 0` and `raw.fileno = lambda: 3` at lines 1469-1470 (`test_the_real_socket_outlives_close_while_a_reader_is_open`) and 1488-1489 (`test_a_second_reader_keeps_the_fake_socket_open`); removed in a scratch copy, those two tests and the probe class pass | delete the four lines; the `recv_into` at line 1517 is exercised and stays |
| 4. "once" with a boolean close | **No, already fixed** | `Counting._FakeSock.close` appends to `closes` and the test asserts `closes == [1]` (lines 1485 and 1497) | none; the roadmap row says so |

Out of scope, stays as it is: `src/`, every other test file, the leak checks'
set comparison `assertLessEqual(_socket_links(), self.sockets_before)` (a set
of links, not a count), and the `Last checked with:` stamps.

## 2. Decisions

* **One wording.** A function `_blind_reason(directories=None)` returns the
  probe's skip text; the probe raises `SkipTest(_blind_reason(directories))`
  and the control skips with `_blind_reason()`.
* **Capability is what the listed directory shows, not that it exists**
  (LPR1-001). `/dev/fd` exists on hosts where its entries are not symbolic
  links (macOS), and the probe skips there; a control that tested only
  `os.path.isdir` would run and fail where the probe skips, and the
  `fd423fa` control skipped there, so that would be a regression. A function
  `_lists_links(directories=None)` takes the first existing directory of
  `_FD_DIRECTORIES` (the rule `_socket_links` uses), opens a socket pair and
  returns whether `os.path.islink(<directory>/<fd of one end>)`; no existing
  directory returns false. It does not go through `_socket_links`, so the
  control stays a real positive control: it is not "skip whenever the probe
  skips". It reads the module's tuple at call time, so a patched or mutated
  tuple moves the probe and the control together.
* **Identify, not count.** `_own_links(pair)` returns
  `{f"socket:[{os.fstat(end.fileno()).st_ino}]" for end in pair}`. The probe
  skips unless `_own_links(pair) <= _socket_links(directories)`, taken in one
  listing while the pair is open. The control asserts the pair's own links
  are listed while the ends are open and none is listed once both are closed.
  A descriptor another thread opens or closes between two listings changes
  neither.
* **The bystander really is one** (LPR1-002). The control opens a second,
  unrelated pair *after* its first listing and keeps it open through the last
  (closed by `addCleanup`), so a before/after difference would see four new
  links and then two left over: counting fails, identifying does not. The
  probe has its own case: `test_the_probe_names_the_pairs_own_links_not_new_ones`
  patches `_socket_links` with a listing that grows by two unrelated links per
  call; identifying skips (the pair's inodes are not among them), counting
  would see two new links and not skip. M9 and M10 are the failure-only proof
  for each.
* **The "probe skipped" failure stays.** On a host whose directory lists
  links, the control still fails if the probe skips, as it does now.
* **No other change** to the probe's return value (`_socket_links(directories)`
  after the pair is closed), its callers or the leak checks.

## 3. Tests (`tests/test_discovery.py`)

`_FD_DIRECTORIES`, `_socket_links` stay. After them:

```python
def _blind_reason(directories=None) -> str:
    return (f"descriptor directories {tuple(directories or _FD_DIRECTORIES)} do not expose "
            f"socket links on {sys.platform}; the leak check would compare empty with empty")


def _own_links(pair) -> set[str]:
    return {f"socket:[{os.fstat(end.fileno()).st_ino}]" for end in pair}


def _lists_links(directories=None) -> bool:
    """Whether the first existing descriptor directory shows an open socket's
    descriptor as a symbolic link (not merely exists)."""
    for directory in directories or _FD_DIRECTORIES:
        if os.path.isdir(directory):
            end, other = socket.socketpair()
            try:
                return os.path.islink(os.path.join(directory, str(end.fileno())))
            finally:
                end.close()
                other.close()
    return False


def _require_socket_links(directories=None) -> set[str]:
    """... (docstring: the probe opens a pair and skips unless the pair's own
    links are listed)"""
    pair = socket.socketpair()
    try:
        shown = _own_links(pair) <= _socket_links(directories)
    finally:
        for end in pair:
            end.close()
    if not shown:
        raise unittest.SkipTest(_blind_reason(directories))
    return _socket_links(directories)
```

`TestTheDescriptorProbe`:

```python
    def test_the_helper_sees_a_socket_it_just_opened(self):
        if not _lists_links():
            self.skipTest(_blind_reason())
        before = _socket_links()
        pair = socket.socketpair()
        bystander = socket.socketpair()
        self.addCleanup(lambda: [end.close() for end in bystander])
        try:
            own = _own_links(pair)
            self.assertEqual(len(own), 2)
            self.assertTrue(before.isdisjoint(own))
            self.assertLessEqual(own, _socket_links())
        finally:
            for end in pair:
                end.close()
        self.assertEqual(own & _socket_links(), set())
        try:
            _require_socket_links()
        except unittest.SkipTest as skipped:
            self.fail(f"the probe skipped on a host that lists descriptors: {skipped}")

    def test_the_probe_names_the_pairs_own_links_not_new_ones(self):
        calls = []

        def growing(directories=None):
            calls.append(directories)
            return {f"socket:[unrelated-{k}]" for k in range(2 * len(calls))}

        with mock.patch.object(sys.modules[__name__], "_socket_links", growing):
            with self.assertRaises(unittest.SkipTest):
                _require_socket_links()

    def test_the_control_skips_exactly_where_the_probe_does(self):
        module = sys.modules[__name__]
        for label, build in (("a missing path", lambda directory: None),
                             ("regular files", lambda directory: (directory / "3").write_text("x"))):
            with self.subTest(label):
                path = self.standin(build)
                if label == "a missing path":
                    path = os.path.join(path, "absent")
                with mock.patch.object(module, "_FD_DIRECTORIES", (path,)):
                    with self.assertRaises(unittest.SkipTest) as probe:
                        _require_socket_links()
                    result = unittest.TextTestRunner(stream=io.StringIO()).run(
                        TestTheDescriptorProbe("test_the_helper_sees_a_socket_it_just_opened"))
                self.assertEqual((result.testsRun, len(result.skipped)), (1, 1))
                self.assertEqual((result.failures, result.errors), ([], []))
                self.assertEqual(result.skipped[0][1], str(probe.exception))
                self.assertIn(path, str(probe.exception))
```

The existing `test_a_directory_that_cannot_expose_links_is_a_skip_with_its_reason`
and `test_both_leak_checking_classes_skip_when_sockets_cannot_be_listed` stay
unedited and must stay green (they pin the probe's reason and the two leak
classes' skip). In `TestTheBoundedPieces` the two lines
`raw.recv_into = lambda buf, *a: 0` and `raw.fileno = lambda: 3` go from
`test_the_real_socket_outlives_close_while_a_reader_is_open` and from
`test_a_second_reader_keeps_the_fake_socket_open`; no assertion changes.
`TestTheDescriptorProbe` then has 6 tests.

**Failure-only mutations.** Each is a `sed` on a copy of the candidate in a
scratch directory made with `git archive` (never this repository; the scratch
is not a repository, so only `$S/t.py` runs, section 5, apply there),
passes on the real code, and starts from a fresh copy (`command rm -rf
$S/mut; command cp -rf $S/cand $S/mut`). Run in a scratch built from the code
above, each failed as listed:

| # | Mutation | Must fail |
| --- | --- | --- |
| M1 | control decides with the literal again: `s\|if not _lists_links():\|if not os.path.isdir("/proc/self/fd"):\|` | `test_the_control_skips_exactly_where_the_probe_does`, both cases (the control runs and fails instead of skipping) |
| M2 | control words its own skip: `s\|self.skipTest(_blind_reason())\|self.skipTest("no descriptor directory")\|` | the same test, both cases (reason differs) |
| M3 | the control decides by existence only: `s\|return os.path.islink(os.path.join(directory, str(end.fileno())))\|return True\|` | the same test, the `regular files` case only (LPR1-001) |
| M4 | a control that leaves one end open: `/def test_the_helper_sees/,/self.assertEqual(own &/ s/for end in pair:/for end in pair[:1]:/` | `test_the_helper_sees_a_socket_it_just_opened` |
| M5 | the links are not the pair's: `s\|st_ino}\]\|st_ino + 1}]\|` in `_own_links` | `test_the_helper_sees_a_socket_it_just_opened` |
| M6 | the probe never skips: `s\|^    if not shown:\|    if False:\|` | `test_a_directory_that_cannot_expose_links_is_a_skip_with_its_reason` (three subtests); selected alone it keeps the run offline. Run on all of `$P` it also fails the two leak classes' skip test, the coupling test and the growing-listing test, and takes about 13 s (the leak classes then run for real on loopback) |
| M7 | a bounded read leaks one extra socket link (in `src/workflow_manager/source.py`: `s\|^        self._sock.close()$\|        _LEAKED.append(self._sock)\|` and a `_LEAKED = []` line at the end of the module) | among the failures, the leak checks of `TestAnExpiredReadLeavesNothingBehind` and `TestAProxyConnectReplyIsBounded`, and some `TestTheBoundedPieces` tests (for example `test_the_real_socket_outlives_close_while_a_reader_is_open`); needs loopback sockets |
| M8 | the directory list is blind: `s\|^_FD_DIRECTORIES = .*\|_FD_DIRECTORIES = ("/nonexistent-fd",)\|`, and again with a directory of one regular file in place of the path | not a failure, a comparison, for each: on `fd423fa`'s test file the control **fails**; on the change it **skips** with the probe's reason |
| M9 | the probe counts again: `-e 's\|^    pair = socket.socketpair()$\|    _before = _socket_links(directories)\n    pair = socket.socketpair()\|' -e 's\|shown = _own_links(pair) <= _socket_links(directories)\|shown = len(_socket_links(directories) - _before) >= 2\|'` (the four-space anchor matches only the probe) | `test_the_probe_names_the_pairs_own_links_not_new_ones` |
| M10 | the control counts again: `s\|self.assertLessEqual(own, _socket_links())\|self.assertEqual(len(_socket_links() - before), 2)\|` | `test_the_helper_sees_a_socket_it_just_opened` (the bystander makes four new links) |

Evidence at implementation: the 6 tests of `TestTheDescriptorProbe` and the
two edited `TestTheBoundedPieces` tests green on the real code; M1 to M7, M9
and M10 each failing what is named; M8 run on both files for both variants
and recorded, all through the offline `run` of section 5 (scratch empty lock,
empty release cache: eight passing candidate tests, and a mutation counts only
when it fails by the named assertion, never by an import error); `python3 tests/run_all.py --select test_discovery.py` in a
clone (never in a `git archive` scratch, which has no repository for
`run_all`); then the full gate `python3 tests/run_all.py`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The probe and its control identify what they count; the dead setup goes | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the probe and its control identify what they count; the dead setup goes

**Files:** `tests/test_discovery.py`.

Sections 2 and 3, all in this one file: `_blind_reason`, `_own_links` and
`_lists_links` after `_socket_links`; the probe rewritten as above (docstring
too); the control rewritten and the growing-listing and coupling tests added;
four lines deleted in `TestTheBoundedPieces`. `src/` is not edited (mutation M7 touches only the
scratch copy).
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 31 of `docs/ROADMAP.md` is added by this plan as Current and is Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: a `test:` title releases nothing. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 5. Functional review

Flows 1 to 9 run offline with `python3 -I -B` only, outside the repository, in
a scratch directory: no network, no `gh`, no installs, no primed release cache,
no TCP sockets (they use `socketpair`, which is local, and flow 8 selects the one
probe test for M6 so no leak class runs). Flow 10 needs the full environment
(a primed release cache or a mirror, and loopback sockets) and is last; it runs
in a shell with none of the variables below set.

Setup: `S=$(mktemp -d "$HOME/.cache/dtc-fr.XXXXXX")`; `mkdir -p $S/base
$S/cand $S/tmp $S/cache`; `git archive fd423fa4bf8e53d4e8e2af13986e5152b6de489d src tests |
tar -x -C $S/base`; `git archive HEAD src tests | tar -x -C $S/cand` (HEAD is
the candidate). Importing `test_discovery` imports `tests/support.py`, which
at import resolves the frozen suite counts of every release in the lock from
the release cache's manifests and raises `LockError` on an empty cache, so no
test would run (and a mutation would "fail" by import error, which is no
evidence). The setup therefore selects a scratch lock with no releases:
`printf '{"schema_version": 1, "releases": {}}' > $S/lock.json`. Every flow
1 to 9 run goes through

```sh
run() { env -u WORKFLOW_MANAGER_RELEASE_SOURCE TMPDIR=$S/tmp \
  WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache \
  WORKFLOW_MANAGER_TESTED_RELEASES=$S/lock.json python3 -I -B $S/t.py "$@"; }
```

which also keeps the cache empty (`$S/cache` stays empty) and puts the
fixtures' `TemporaryDirectory()` under `$S/tmp`. `-I` ignores `PYTHONPATH`, so
`$S/t.py` (argument 1: the tree; the rest: test ids) sets the path itself and
runs the named tests:

```python
import sys, unittest
tree = sys.argv[1]
sys.path[:0] = [tree + "/src", tree + "/tests"]
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:], __import__("test_discovery"))
sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
```

`P=TestTheDescriptorProbe`, `B=TestTheBoundedPieces`. A mutation starts from a
fresh copy, never from the previous mutation: `command rm -rf $S/mut; command
cp -rf $S/cand $S/mut`, then `sed -i` on `$S/mut/tests/test_discovery.py`
(`command` because `rm` and `cp` may be aliased to their interactive forms).

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat fd423fa4bf8e53d4e8e2af13986e5152b6de489d HEAD -- src tests tools` | exactly one file, `tests/test_discovery.py`; nothing under `src/` or `tools/` |
| 2 | `grep -n "def test_the_helper_sees_a_socket_it_just_opened\|def test_the_control_skips_exactly\|def test_the_probe_names\|def _blind_reason\|def _own_links\|def _lists_links" $S/cand/tests/test_discovery.py` | the six definitions, once each |
| 3 | `grep -n "raw.fileno = lambda: 3" $S/cand/tests/test_discovery.py` and `grep -c "raw.recv_into = lambda buf, \*a: 0" $S/cand/tests/test_discovery.py` | no match; the count is 1 (the exercised one) |
| 4 | `run $S/cand $P $B.test_the_real_socket_outlives_close_while_a_reader_is_open $B.test_a_second_reader_keeps_the_fake_socket_open` | exit 0, `Ran 8 tests`, `OK` |
| 5 | fresh copy, M1, `run $S/mut $P`; then fresh copy, M2, the same run | each exit 1; only `test_the_control_skips_exactly_where_the_probe_does` fails (both cases) |
| 6 | fresh copy, M3, the same run | exit 1; the same test fails, the `regular files` case only |
| 7 | fresh copy, M4; fresh copy, M5; fresh copy, M10; the same run for each | each exit 1; `test_the_helper_sees_a_socket_it_just_opened` fails (and nothing else) |
| 8 | fresh copy, M9, the same run; fresh copy, M6, `run $S/mut $P.test_a_directory_that_cannot_expose_links_is_a_skip_with_its_reason` | M9: exit 1, `test_the_probe_names_the_pairs_own_links_not_new_ones` fails; M6: exit 1, three subtests fail |
| 9 | M8, both variants, on `$S/base` and on `$S/cand`, `run <tree> $P.test_the_helper_sees_a_socket_it_just_opened` | base exits 1 each time (the control runs and fails); candidate exits 0 with the test skipped, its reason the probe's (`verbosity=2` prints it: `do not expose socket links`) |
| 10 | (needs the full environment) in a clone made with `git clone --no-hardlinks "$PWD" $S/clone` at the candidate: `python3 tests/run_all.py --select test_discovery.py`; then apply M7 in the clone and run it again | first run exit 0; second run exit 1, with the two leak classes among the failures |

Flows 1 to 9 write only under `$S` (`TMPDIR` is `$S/tmp`, which is empty again
after each flow, and `$S/cache` stays empty); listing `$S` recursively before
and after each flow shows only the scratch copies. Flow 10's second run exits 1
by design and keeps its results directory (`verdict: exit 1; results kept in
.../wm-run-...`) under the run's temporary directory, outside `$S`: that is
not a defect; remove it afterwards, then `command rm -rf $S`.

## 6. Risks

* A socket inode could in principle be reused between the pair's close and the
  second listing; the kernel numbers sockets upward, so this is not a
  practical flake, and the case asserts the pair has two distinct links first.
* The coupling test runs the control inside a private `TextTestRunner` with a
  `StringIO` stream (the runner imports the file as `test_discovery`, hence
  `sys.modules[__name__]`), as the existing integration test does.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
