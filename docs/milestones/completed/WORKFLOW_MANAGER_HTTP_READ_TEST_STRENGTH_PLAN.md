# Workflow Manager: Make the Bounded Discovery Read's Tests Check What They Claim (Revision 1)

`work_item_id: http-read-test-strength` -- `governing_workflow_version: "2.2"`

**Deliverable:** two test-strength gaps of the bounded discovery read
(`http-read-deadline`, roadmap row 15) are closed in `tests/test_discovery.py`:
the descriptor-leak assertions no longer pass silently where the platform
cannot show socket descriptors, and a case now fails when
`_Bounded._decref_socketios` stops counting readers.

**Work item type:** `process`. **Base commit:** `19b2ffc` (tip of `main`;
Workflow 2.25.0 installed, automatic gates). **Branch:**
`milestone/http-read-test-strength`. **Scope source:** `docs/ROADMAP.md` row 20
(items 1 and 2 of issue #128). Tests only: nothing under `src/` changes, so the
pull request title is `test: ...`, which releases nothing (checked with
`python3 tools/release/release.py check-title`).
**Not in this milestone:** items 3 to 5 of #128 (message wording and the
priming test's tree, a different mechanism and the next item), and any `src/`
change. One mechanism, two checkpoints (the sizing rule's limits).

## 1. The two gaps

1. **A check that checks nothing.** `_socket_links()` returns an empty set when
   neither `/proc/self/fd` nor `/dev/fd` exists, and also when a directory
   exists but its entries do not read as `socket:` links. The two classes that
   assert "no descriptor left" (`TestAnExpiredReadLeavesNothingBehind`,
   `TestAProxyConnectReplyIsBounded`) then compare empty with empty and pass,
   on a platform where the plan says they check.
2. **An untested line.** `_Bounded._decref_socketios` calls `close()`, not
   `_real_close()`, so that it counts readers as `socket.socket` does. With
   `_real_close()` there, a first reader's close shuts the socket under a second
   reader still open. The one existing reader case
   (`test_the_real_socket_outlives_close_while_a_reader_is_open`) has a single
   reader, which behaves the same on both lines; the mutation leaves all 30
   cases of the three new classes of row 15 green.

## 2. Decisions

* **Skip, with a reason, rather than fail.** A platform whose descriptor
  directory cannot show sockets (no `/proc/self/fd` or `/dev/fd`, or entries
  that are not `socket:` links) is a limit of the platform, not a defect of the
  code under test, so failing there would fail the gate for something no change
  can fix. The assertions skip, visibly: the runner reports `OK (skipped=N)`.
  Where `/proc/self/fd` exists (every Linux host and CI) nothing skips, and the
  positive control of section 3 fails if the helper stops seeing sockets, so a
  helper that silently went blind cannot turn the skip into cover. The positive
  control decides "this host has `/proc/self/fd`" with `os.path.isdir`,
  independently of the probe, and it skips only when that test says the
  directory is absent: a `unittest.SkipTest` raised by `_require_socket_links()`
  on a host that has the directory is caught and turned into a failure
  (`self.fail(...)`), never left to propagate, because the runner reports a
  propagated `SkipTest` as a skip and exits 0 (`tests/parallel/unit.py`
  `addSkip`, `report.py` `OK (skipped=N)`). The same rule holds for every case
  meant to fail under a mutation: none lets a `SkipTest` escape.
* **The probe is a socket the test opens.** "No socket is open" and "cannot
  show sockets" both list as empty, so the listing alone cannot tell them
  apart. `_require_socket_links()` opens a `socket.socketpair()`, lists, and
  raises `unittest.SkipTest` unless the two new links appear; it closes the pair
  before returning. Both classes call it in `setUp` for their baseline, before
  any `addCleanup`, so a skip registers nothing to check. The leak assertions
  keep calling `_socket_links()`.
* **A seam, in the test file only.** `_socket_links` and `_require_socket_links`
  take `directories=None` (meaning the module's `_FD_DIRECTORIES`, read at call
  time, `("/proc/self/fd", "/dev/fd")`), so a test hands them a stand-in
  directory or patches the module's tuple. Nothing under `src/` changes, and no
  other test file or `tests/parallel/resources.json` is touched.
* **The reader case needs no wait.** Closing is synchronous; the case uses a
  fake socket and a socket pair, no thread, no sleep.

## 3. Tests

All in `tests/test_discovery.py`. Hermetic: stand-in directories under a
temporary directory, a loopback-free `socket.socketpair()`, and the existing
fake socket. Deterministic: no clock, no sleep, no thread. No process or
thread is left behind (the pairs and directories close in `addCleanup`), and
nothing is added to `tests/parallel/resources.json`.

**Gap 1, new class `TestTheDescriptorProbe`:**

* **Links are read.** A stand-in directory holding symlinks to `socket:[1]`,
  `socket:[2]` and `pipe:[3]`: `_socket_links` returns exactly the two socket
  names. Only `_socket_links` is called, so no `SkipTest` can arise.
* **A stand-in that cannot expose links is a skip, with its reason.** Three
  stand-ins, as sub-tests: a directory of regular files (`readlink` fails), a
  directory of symlinks to non-socket targets, and a path that does not exist.
  `_require_socket_links` raises `unittest.SkipTest` for each, and the message
  names the directory and `sys.platform`. The case asserts the skip with
  `assertRaises(unittest.SkipTest)` and checks the message; it never lets the
  exception propagate, so a probe that stops raising fails the case instead of
  the case reading as a skip.
* **A positive control.** Where `os.path.isdir("/proc/self/fd")`: a socket pair
  just opened shows two new links, they are gone after it closes, and
  `_require_socket_links()` returns; a `SkipTest` from it is caught and fails
  the case (section 2). Where the directory is absent, the case skips with the
  same reason (visible). It does not skip on this repository's Linux hosts.
* **The two classes honour the probe.** With the module's `_FD_DIRECTORIES`
  patched to a stand-in that cannot expose links, loading both leak-checking
  classes and running them in a private `TextTestRunner` gives only skips: every
  case skipped, none run or failed. The tuple is patched on the module the
  runner loaded, `sys.modules[__name__]` (the runner imports the file as
  `test_discovery` through `importlib.import_module`, so the module the classes
  are loaded from is the one named by `__name__`), and the private runner gets an `io.StringIO` stream, so its inner skips and
  output never mix with the outer run's report. Under mutations 2 and 5 of the table below this
  case really runs the loopback classes inside a test, threads included; that
  is acceptable in a scratch copy, and a slower or noisier mutation run is that,
  not a regression.

**Gap 2, two cases in `TestTheBoundedPieces`:**

* **Two readers, one fake socket.** `makefile` twice, `wrapper.close()`, then the
  first reader's `close()`: the real socket is still open; the second reader's
  `close()` closes it, once.
* **Two readers, one real socket.** A `socket.socketpair()`; the peer sends
  `ab`; two readers over the wrapper; `wrapper.close()`; the first reader
  closes; the second still reads exactly `ab` with `read(2)`, never a `read()` to
  EOF, which would block until the peer closes and, with a clock that never
  advances, wait out the whole `Deadline`; after it closes the real socket's
  `fileno()` is `-1`. The peer closes in `addCleanup`, so a slip fails fast and
  leaves nothing open.

**Failure-only mutations** (each applied to a scratch copy, never to the
repository, and recorded with its result at implementation):

| Mutation | Must fail | Passes on the real code |
| --- | --- | --- |
| `_decref_socketios` calls `_real_close()` instead of `close()` | both gap 2 cases (the existing 30 stay green, which is the gap) | yes |
| `_require_socket_links` never raises | the stand-in skip case, and the integration case | yes |
| `_require_socket_links` always raises `SkipTest` | the positive control (a failure, not a skip) | yes |
| `_socket_links` returns an empty set always | the links-are-read case and the positive control | yes |
| a class's `setUp` takes its baseline with `_socket_links()`, not the probe | the integration case | yes |

Evidence at implementation: the new cases pass on the candidate; each mutation
above fails the cases named; at the base commit the gap 2 cases pass (they
test code that exists) and the helper cases do not exist, so the mutation table
is the base-fail demonstration; `python3 tests/run_all.py --select
test_discovery.py` green; the full gate `python3 tests/run_all.py` green.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The probe, the reader cases and their mutations | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the probe, the reader cases and their mutations

**Files:** `tests/test_discovery.py`.

Section 2 and section 3. `_FD_DIRECTORIES`, `_socket_links(directories=None)` and
`_require_socket_links(directories=None)` next to the existing helper; the two
classes' `setUp` call the probe for their baseline; the new class
`TestTheDescriptorProbe`; the two reader cases in `TestTheBoundedPieces`.

`src/workflow_manager/source.py` appears only in functional-review flow F2, as a
scratch-copy mutation; it is deliberately unclassified by the artifact
declaration and unchanged, so a stray edit to it fails closed.

Evidence: section 3's. Nothing is written into the repository while a run is in
progress.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 20 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance, and `docs/ACTIVE_MILESTONE.md` records the milestone and the
mutation results. No version is edited: a `test:` title releases nothing.

Both files stay excluded at both stages, as in every item: the acceptance step
writes them, so they are bookkeeping, not a reviewed deliverable.
`tests/test_discovery.py` is implementation-protected.
<!-- /CP2 -->

## 5. Functional review

Every flow runs offline in a scratch checkout of the branch, outside the
repository, loopback only, no network and no install. The command form is
`python3 tests/run_all.py --select test_discovery.py` (`docs/RELEASING.md`,
`tests/run_all.py --select`), run in the scratch checkout.

| id | do | expect |
| --- | --- | --- |
| F1 | On the candidate, `python3 tests/run_all.py --select test_discovery.py::TestTheDescriptorProbe --select test_discovery.py::TestTheBoundedPieces` | exit 0; the new cases pass and nothing is reported skipped on this Linux host |
| F2 | In a scratch copy, change `_decref_socketios` in `src/workflow_manager/source.py` to call `self._real_close()` where it calls `self.close()`, then run the F1 command | exit 1; the two reader cases fail and no other case does |
| F3 | In a scratch copy, point `_FD_DIRECTORIES` in `tests/test_discovery.py` at a directory of regular files, then run `--select test_discovery.py::TestAnExpiredReadLeavesNothingBehind --select test_discovery.py::TestAProxyConnectReplyIsBounded` | exit 0 and the report reads `OK (skipped=N)`: a visible skip, not a silent pass |
| F4 | In a scratch copy, make `_socket_links` return an empty set, then run the F1 command | exit 1; the links-are-read case and the positive control fail |
| F5 | In a scratch copy, make `_require_socket_links` always raise `unittest.SkipTest`, then run the F1 command | exit 1; the positive control fails (not skips) |

## 6. Risks

* A skip is weaker than a check. It is confined to platforms that cannot show
  sockets, and the positive control fails on any host with `/proc/self/fd` if
  the helper goes blind, so Linux hosts and CI cannot skip unnoticed.
* The probe opens a socket pair per `setUp`; the cost is two descriptors, closed
  before the baseline is taken.
* The integration case runs the leak-checking classes inside another test; with
  the patched tuple each case skips in `setUp` before it opens anything, so it
  starts no server or thread.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
