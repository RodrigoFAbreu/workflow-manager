# Active Milestone

## Milestone

`http-read-test-strength` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `19b2ffc`, branch `milestone/http-read-test-strength`): roadmap row 20 (#128, items 1 and 2). A `test:` pull request title (releases nothing). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_HTTP_READ_TEST_STRENGTH_PLAN.md`.

Two test-strength gaps of the bounded discovery read (row 15) are closed in `tests/test_discovery.py`: the descriptor-leak assertions skip, with a reason that names the platform, where the process's descriptor directory cannot show socket links (instead of comparing empty with empty), and a case now fails when `_Bounded._decref_socketios` stops counting readers. Nothing under `src/` changes.

Not in this milestone: items 3 to 5 of #128 (message wording, the priming test's tree), and any `src/` change.

### CP1: the probe, the reader cases and their mutations -- complete

- `_FD_DIRECTORIES`, `_socket_links(directories=None)` and `_require_socket_links(directories=None)`: the probe opens a `socket.socketpair()` and raises `unittest.SkipTest` unless both new links show. Both leak-checking classes take their baseline from it in `setUp`.
- New class `TestTheDescriptorProbe` (links are read; three stand-ins that cannot expose links skip with their reason; a positive control; both classes honour the probe) and two reader cases in `TestTheBoundedPieces` (a fake socket and a real socket pair, two readers each).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 20 is Current and becomes Done at acceptance. No version is edited.

### Mutation results (scratch clone of `974a797`, `python3 tests/run_all.py --select test_discovery.py`)

The candidate passes: 19 of 19 units, 108 tests, exit 0, nothing skipped on this Linux host. Each mutation exits 1 and fails exactly the cases the plan names:

| Mutation | Failed |
| --- | --- |
| `_decref_socketios` calls `_real_close()` | `test_a_second_reader_keeps_the_fake_socket_open`, `test_a_second_reader_still_reads_after_the_first_closes` (the other cases stay green) |
| `_require_socket_links` never raises | the stand-in skip case (all three sub-tests) and `test_both_leak_checking_classes_skip_when_sockets_cannot_be_listed` |
| `_require_socket_links` always raises `SkipTest` | `test_the_helper_sees_a_socket_it_just_opened` (a failure, not a skip) |
| `_socket_links` always returns an empty set | `test_links_are_read` and `test_the_helper_sees_a_socket_it_just_opened` |
| a class's `setUp` takes its baseline with `_socket_links()` | `test_both_leak_checking_classes_skip_when_sockets_cannot_be_listed` |

The scratch clone is deleted; the repository was never mutated.

## Functional review checklist

Implementation revision 1. The manual functional review runs against the code at head `082e8b7`; `98badd3` is the branch tip and differs from it only in `docs/ai-workflow/WORKFLOW_STATE.json`.

**Verification already in hand (not rerun).** The full gate, `python3 tests/run_all.py`, exited 0 at `082e8b7`: 2322 of 2322 units, 15359 tests (`.ai-review/http-read-test-strength/current/TEST_RESULTS.md`). No file under `src/`, `tests/` or `tools/` has changed since.

### Setup

- Work in a scratch checkout of `milestone/http-read-test-strength`: a `git clone` into a new, empty directory outside this repository. Flows F2 to F5 edit files, so never run them in the repository itself. Nothing is installed; only `python3` and `git` are needed.
- Every `tests/run_all.py` run, `--select` included, first primes the release cache with every tested version, then runs offline. The first run on a machine needs the network or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror. On a machine whose cache is populated (`~/.cache/workflow-manager/releases`, about 470 MB), a scratch run needs no network if `XDG_CACHE_HOME` points at a copy of that cache.
- The F1 command, also used for each mutation run: `python3 tests/run_all.py --select test_discovery.py::TestTheDescriptorProbe --select test_discovery.py::TestTheBoundedPieces`.

### Test data

None. Each case builds its own temporary directories and socket pairs and removes them.

### Flows

| id | do | expect |
| --- | --- | --- |
| F1 | On the candidate, run the F1 command. | exit 0; `Ran 18 tests OK`; nothing reported skipped. |
| F2 | In a scratch copy, change `_decref_socketios` in `src/workflow_manager/source.py` to call `self._real_close()` where it calls `self.close()`, then run the F1 command. | exit 1; `test_a_second_reader_keeps_the_fake_socket_open` and `test_a_second_reader_still_reads_after_the_first_closes` fail; no other case fails. |
| F3 | In a scratch copy, point `_FD_DIRECTORIES` in `tests/test_discovery.py` at a directory of regular files, then run `--select test_discovery.py::TestAnExpiredReadLeavesNothingBehind --select test_discovery.py::TestAProxyConnectReplyIsBounded`. | exit 0; the report reads `OK (skipped=N)`: a visible skip, not a silent pass. |
| F4 | In a scratch copy, make `_socket_links` return an empty set, then run the F1 command. | exit 1; `test_links_are_read` and the positive control `test_the_helper_sees_a_socket_it_just_opened` fail. |
| F5 | In a scratch copy, make `_require_socket_links` always raise `unittest.SkipTest`, then run the F1 command. | exit 1; the positive control fails (a failure, not a skip). |

Record each flow's command, exit code and summary line, and the file and line you changed for F2 to F5.

### Sandbox notes (Controller functional tester)

- No flow calls `gh`, `claude`, `codex`, `ssh` or any forge, and none needs the network. F1 to F5 use only `python3` and `git` from the system directories.
- F1, F2, F4 and F5 use `socket.socketpair()` only (in-process Unix sockets), not TCP. The two classes F3 selects use loopback TCP, but with `_FD_DIRECTORIES` patched they skip in `setUp`, before any server or thread starts.
- The descriptor probe needs `/proc/self/fd` or `/dev/fd` to list `socket:` links. If a sandbox hides them, the probe skips with its reason, F1's "nothing skipped" does not hold, and that is an environment outcome, not a `defect`.
- Setup check (not a review result): F1 was run once in a scratch clone of `milestone/http-read-test-strength` with a copied release cache, inside a network namespace with no network (`unshare -rn`). It exited 0 with `Ran 18 tests OK` and nothing skipped. That namespace maps the user to root, so the run needed `run_all.py --allow-root`; a normal, non-root run does not.

### Known limitations and out of scope

- Items 3 to 5 of #128 (message wording and the priming test's tree) and any `src/` change are out of scope.
- The skip path is exercised only by F3's mutation on this Linux host. No non-Linux host is run.
- Mutations run only in scratch copies. The repository is never mutated.
- The implementation reviewer's sandbox could not rerun socket data transfer, so the real-socket reader case was assessed from code and supplied evidence. F1 is the run that exercises it on Linux.

## Next action

Manual functional review: run F1 to F5 above in a scratch checkout and write any findings to `.ai-review/http-read-test-strength/feedback/FUNCTIONAL_REVIEW.md`.

- Clean: `/accept-milestone` is the only acceptance command. It requires every checkpoint to be `COMPLETE`, and CP1 and CP2 are. No command records acceptance of a partial round.
- Findings: `/apply-functional-review` classifies each one. A same-scope fix takes its bounded branch; new or wider scope takes its broad branch, a `http-read-test-strength-remediation-<n>` child work item.
- Eight plan-stage optional findings are recorded in `WORKFLOW_STATE.json` without a disposition. Acceptance records one for each.
