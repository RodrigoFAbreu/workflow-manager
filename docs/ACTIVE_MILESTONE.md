# Active Milestone

## Milestone

`discovery-test-cleanup` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `fd423fa`, branch `milestone/discovery-test-cleanup`): roadmap row 31 (#131, items 1 to 3). A `test:` pull request title (releases nothing).

The bounded-read tests of `tests/test_discovery.py` identify the sockets they count, by the descriptor probe's own rules. The positive control decides "this host can list sockets" from what the first existing descriptor directory of `_FD_DIRECTORIES` shows (`_lists_links`) and skips with the probe's one wording (`_blind_reason`). The probe and the control look for the socket pair's own links (`socket:[<inode>]` from `os.fstat` of each end, `_own_links`) instead of counting two new links in a before/after difference, so a descriptor another thread opens or closes between two listings disturbs neither. Four lines of dead setup (`recv_into`, `fileno` on the fake socket, in two tests) are deleted. Item 4 of the issue was already fixed on main. Test code only: no `src/` change, no printed text, no Workflow change.

### CP1: the probe and its control identify what they count -- complete

- `tests/test_discovery.py` only (commit `392ffe1`): `_blind_reason`, `_own_links`, `_lists_links`; the probe and the control rewritten; the growing-listing test and the coupling test added (`TestTheDescriptorProbe` has 6 tests); the four dead lines removed.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 31 is Current (Done at acceptance); this record.

### Failure-only mutations

Plan section 3, run in a scratch copy of `392ffe1` made with `git archive` (not a repository; the offline `run` of plan section 5: empty scratch lock, empty release cache, `python3 -I -B`). The unmutated copy passes the 6 probe tests; each mutation fails exactly what the plan names:

| # | Mutation | Result |
| --- | --- | --- |
| M1 | control decides with the literal `/proc/self/fd` | `test_the_control_skips_exactly_where_the_probe_does`, both cases |
| M2 | control words its own skip | the same test, both cases |
| M3 | control decides by existence only (`return True`) | the same test, `regular files` case only |
| M4 | control leaves one end open | `test_the_helper_sees_a_socket_it_just_opened` |
| M5 | `_own_links` names the wrong inodes | `test_the_helper_sees_a_socket_it_just_opened` |
| M6 | the probe never skips | `test_a_directory_that_cannot_expose_links_is_a_skip_with_its_reason` (three subtests), plus the leak classes' skip test, the coupling test and the growing-listing test (13 s on all of `TestTheDescriptorProbe`: the leak classes then run for real) |
| M7 | a bounded read leaks one socket (`src/workflow_manager/source.py`, scratch copy only) | the leak checks of `TestAnExpiredReadLeavesNothingBehind` and `TestAProxyConnectReplyIsBounded` fail, and `TestTheBoundedPieces` tests including `test_the_real_socket_outlives_close_while_a_reader_is_open` (22 tests of the three classes, needs loopback sockets; the unmutated three classes pass, 32 tests) |
| M8 | the directory list is blind (a missing path, and a directory of one regular file) | comparison: on `fd423fa`'s file the control **fails** in both variants; on the change it **skips** with the probe's reason in both |
| M9 | the probe counts again | `test_the_probe_names_the_pairs_own_links_not_new_ones` |
| M10 | the control counts again | `test_the_helper_sees_a_socket_it_just_opened` (the bystander makes four new links) |

### Self-review

The full diff against `fd423fa` was read against the plan: `tests/test_discovery.py` is the only code or test file that changed, the helpers, the probe, the control and the two new tests match plan section 3, the four dead lines are gone, and the `recv_into` that is exercised stays. M1 to M10 were run again on `9a0a5d2` through plan section 5's offline `run` (M7 and M8 as in the table above), each with the result listed, by a fresh session. No code finding. Two record corrections, in excluded files only: the M7 row above now names every class the plan names, and roadmap row 31 no longer says "no behaviour change" (the plan names the one test behaviour that changes) and says what the control decides from.

### Verification

`python3 tests/run_all.py` at `9a0a5d2` (full selection, 8 workers): `verdict: exit 0`, 2330/2330 units, 15552 tests, `selection_digest` `4c041765...`, `tests_digest` `348433d5...`.

No `src/`, `tests/` or `tools/` file changed after `9a0a5d2` (`git diff --stat 9a0a5d2 HEAD -- src tests tools` is empty; the later commits are docs and state), so this run is current and was not repeated for the functional gate.

## Functional review checklist

The change is test code only: `tests/test_discovery.py`, at `392ffe1`. The product does not change, so this review checks that the tests do what the plan says. Flows 1 to 9 run in the Controller's functional sandbox (no network, no `gh`, no `claude`/`codex`/`ssh`, no origin, no release cache, no loopback socket, `PATH` of the system directories only). Flow 10 does not: it needs a primed release cache and loopback sockets, so the user runs it in a normal shell. Flows 1 to 9 were run at HEAD on 2026-11-04 exactly as written below, under `env -i PATH=/usr/bin:/bin unshare -rn` (no network), and every expectation held. Flow 10 was not run for this checklist.

### Setup (flows 1 to 9)

Run from the root of the product clone. Nothing below writes inside it; `S` is a new scratch directory outside it (in the sandbox, its writable scratch area; a manual run uses `$HOME/.cache`).

```sh
REPO=$PWD
BASE=fd423fa4bf8e53d4e8e2af13986e5152b6de489d
S=$(mktemp -d "$HOME/.cache/dtc-fr.XXXXXX")
mkdir -p "$S/base" "$S/cand" "$S/tmp" "$S/cache"
printf '{"schema_version": 1, "releases": {}}' > "$S/lock.json"
git archive "$BASE" src tests | tar -x -C "$S/base"
git archive HEAD src tests | tar -x -C "$S/cand"
cat > "$S/t.py" <<'PY'
import sys, unittest
tree = sys.argv[1]
sys.path[:0] = [tree + "/src", tree + "/tests"]
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:], __import__("test_discovery"))
sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
PY
run() { env -u WORKFLOW_MANAGER_RELEASE_SOURCE TMPDIR="$S/tmp" WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" WORKFLOW_MANAGER_TESTED_RELEASES="$S/lock.json" python3 -I -B "$S/t.py" "$@"; }
mut() { command rm -rf "$S/mut"; command cp -rf "$S/cand" "$S/mut"; }   # a fresh copy per mutation
P=TestTheDescriptorProbe; B=TestTheBoundedPieces; T="$S/cand/tests/test_discovery.py"
```

`verbosity=2` prints each skip's reason, which flow 9 checks.

### Flows 1 to 9

**Flow 1: the change is one file.**
```sh
git -C "$REPO" diff --stat "$BASE" HEAD -- src tests tools
```
Expect: one file, `tests/test_discovery.py`; nothing under `src/` or `tools/`.

**Flow 2: the six definitions, once each.**
```sh
grep -c "def test_the_helper_sees_a_socket_it_just_opened\|def test_the_control_skips_exactly\|def test_the_probe_names\|def _blind_reason\|def _own_links\|def _lists_links" "$T"
```
Expect: `6`.

**Flow 3: the dead setup is gone; the exercised `recv_into` stays.**
```sh
grep -n "raw.fileno = lambda: 3" "$T"; grep -c 'raw.recv_into = lambda buf, \*a: 0' "$T"
```
Expect: the first prints nothing; the second prints `1`.

**Flow 4: the bounded-read tests of this change pass.**
```sh
run "$S/cand" $P $B.test_the_real_socket_outlives_close_while_a_reader_is_open $B.test_a_second_reader_keeps_the_fake_socket_open
```
Expect: `Ran 8 tests`, `OK`, exit 0.

**Flow 5: the control decides by the probe's rule, and words its skip from the probe (M1, M2).**
```sh
mut; sed -i 's|if not _lists_links():|if not os.path.isdir("/proc/self/fd"):|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
mut; sed -i 's|self.skipTest(_blind_reason())|self.skipTest("no descriptor directory")|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
```
Expect, each: exit 1; the only failing test is `test_the_control_skips_exactly_where_the_probe_does`, in both subtests (`a missing path`, `regular files`).

**Flow 6: the control does not decide by existence alone (M3).**
```sh
mut; sed -i 's|return os.path.islink(os.path.join(directory, str(end.fileno())))|return True|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
```
Expect: exit 1; that test fails in its `regular files` subtest only.

**Flow 7: the control and the helper see the pair's own two links (M4, M5, M10).**
```sh
mut; sed -i '/def test_the_helper_sees/,/self.assertEqual(own &/ s/for end in pair:/for end in pair[:1]:/' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
mut; sed -i 's|st_ino}\]|st_ino + 1}]|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
mut; sed -i 's|self.assertLessEqual(own, _socket_links())|self.assertEqual(len(_socket_links() - before), 2)|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
```
Expect, each: exit 1; only `test_the_helper_sees_a_socket_it_just_opened` fails.

**Flow 8: the probe names the pair's own links, and it skips where it cannot list them (M9, M6).**
```sh
mut; sed -i -e 's|^    pair = socket.socketpair()$|    _before = _socket_links(directories)\n    pair = socket.socketpair()|' -e 's|shown = _own_links(pair) <= _socket_links(directories)|shown = len(_socket_links(directories) - _before) >= 2|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P
mut; sed -i 's|^    if not shown:|    if False:|' "$S/mut/tests/test_discovery.py"; run "$S/mut" $P.test_a_directory_that_cannot_expose_links_is_a_skip_with_its_reason
```
Expect: M9, exit 1, only `test_the_probe_names_the_pairs_own_links_not_new_ones` fails. M6, exit 1, three subtests fail (`regular files`, `non-socket links`, `a missing path`). The M6 run selects one test on purpose: with the probe never skipping, the full class runs the leak classes on loopback.

**Flow 9: a blind directory list skips with the probe's reason (M8), on the base file and on the change.**
```sh
mkdir -p "$S/reg"; : > "$S/reg/3"
for tree in base cand; do
  for dir in /nonexistent-fd "$S/reg"; do
    command rm -rf "$S/mut"; command cp -rf "$S/$tree" "$S/mut"
    sed -i "s|^_FD_DIRECTORIES = .*|_FD_DIRECTORIES = (\"$dir\",)|" "$S/mut/tests/test_discovery.py"
    run "$S/mut" $P.test_the_helper_sees_a_socket_it_just_opened; echo "$tree $dir rc=$?"
  done
done
```
Expect: `base` (`fd423fa`'s file), both variants: exit 1, the control fails. `cand` (the change), both variants: `OK (skipped=1)`, exit 0, and the printed skip reason says `do not expose socket links`.

### After the flows

```sh
git -C "$REPO" status --porcelain | wc -l
find "$S/tmp" "$S/cache" -mindepth 1 | wc -l
```
Expect: `0` and `0`. The product clone is untouched; the sandbox wrote only under `$S`.

### Flow 10 (user, outside the sandbox)

Needs the full environment: the release cache primed (network on the first run, or a mirror via `WORKFLOW_MANAGER_RELEASE_SOURCE`) and loopback sockets. Run it in a shell with none of the variables above set.

```sh
git clone --no-hardlinks "$REPO" "$S/clone" && cd "$S/clone"
python3 tests/run_all.py --select test_discovery.py          # expect: verdict: exit 0
sed -i 's|^        self._sock.close()$|        _LEAKED.append(self._sock)|' src/workflow_manager/source.py
printf '\n_LEAKED = []\n' >> src/workflow_manager/source.py  # M7, in the clone only
python3 tests/run_all.py --select test_discovery.py          # expect: verdict: exit 1
```
Expect: the second run exits 1 with the two leak classes (`TestAnExpiredReadLeavesNothingBehind`, `TestAProxyConnectReplyIsBounded`) among the failures, and some `TestTheBoundedPieces` tests (for example `test_the_real_socket_outlives_close_while_a_reader_is_open`). The second run is meant to fail. It keeps its results directory (`results kept in .../wm-run-...`) under the shell's temporary directory, outside `$S`: remove that directory, then `rm -rf "$S"`.

### Test data

None to seed. Each flow builds its own stand-in directories and socket pairs under `$S/tmp` (`TMPDIR`). The release lock is empty and the release cache stays empty.

### Known limitations

- A pass shows the test file's checks behave as the plan says. It does not exercise the product's descriptor handling; the full gate does (`python3 tests/run_all.py`, exit 0 at `9a0a5d2`, see Verification).
- If the sandbox hides `/proc/self/fd`, the probe skips and the expectations above change (flow 4 reports skips). Report that as an environment limit, not a defect.
- Open optional findings in `WORKFLOW_STATE.json` (`optional_findings`), dispositioned at acceptance, none a flow failure: the name `test_the_control_skips_exactly_where_the_probe_does` claims more than it checks for a directory of non-socket links (the code stays); no case pins the first-existing-directory half of `_lists_links`; the `bystander` `socketpair()` (`tests/test_discovery.py:1279`) sits outside the first pair's `try/finally`, so the first pair's cleanup falls to finalisation if that allocation fails.
