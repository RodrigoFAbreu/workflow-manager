# Active Milestone

## Milestone

**Functional review.** `test-hygiene-3` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `26d6850`, branch `milestone/test-hygiene-3`): roadmap row 49 (added at CP2, Current now, Done at acceptance).

The existing discovery, release-metadata, parallel-runner and update-report tests assert what they claim: ten points of #162, #164, #166 and #239. A `test:` change, no release.

### CP1: the descriptor probe and the runner test cleanup -- complete

- `tests/test_discovery.py`: `_lists_links()` takes no parameter and asks what the probe asks (the first existing directory of `_FD_DIRECTORIES` lists the pair's own links); the control test gains a 256 `pipe:[1]` links stand-in; new `test_the_first_existing_directory_decides_what_is_listed`; the second `socketpair()` of the helper test moves inside the `try`.
- `tests/test_parallel_runner.py`: the sigterm/sigint test's `finally` ends the chunk groups through `_end_group` before the stop file, kills a still-running executor, and asserts every group ended; `pgid` is `None` after the success-path death check.
- Verified: `--select test_discovery.py --select test_parallel_runner.py` verdict exit 0 (379 tests); M4 and M5 each fail `TestTheDescriptorProbe` in a scratch copy outside the repository; `src tools .claude scripts .workflow-manager tests/parallel` byte-identical to the checkpoint start.

### CP2: the latest filter, the update report note, the docs line and the roadmap row -- complete

- `tests/test_release_metadata.py`: the default case gains `7.0.6` with a `schema_version: 2` block (`NEWER_BLOCK`); new `test_a_pin_that_is_not_built_in_is_judged_like_any_other_release_when_its_block_is_read` (six pins, none built in); `TestTheDocs` pins the new `docs/update.md` sentence and that the old words are gone.
- `docs/update.md` line 45: "a pin or the default version with no trusted cached manifest is kept (one whose block was read is judged like any other release)"; the "Last checked with" stamp does not move.
- `tests/test_compatibility.py`: the no-installation arm asserts only that no ` verify ` command is printed; the redundant `assertIn("verify", ...)` is gone.
- `docs/ROADMAP.md`: row 49 (Current).
- Verified: `--select test_release_metadata.py --select test_compatibility.py --select test_docs.py` verdict exit 0 (237 tests); `python3 tools/check_docs.py` exit 0; M1 fails the default case `7.0.6` and M2 fails the pin cases `7.0.1` to `7.0.4` in a scratch copy outside the repository (M3 and M8b are flow 10 of the functional review); `src tools .claude scripts .workflow-manager tests/parallel` byte-identical to the base.

### Self-review and the full gate

- The full milestone diff matches the plan's file list and sections; no blocking or important finding, no change. The sigterm test's new `finally` reads `_lock_holder` as `_interrupt` does; on the success path the chunk's own `finally` has already removed its pgid under the held lock, so no reused group is signalled.
- Plan section 6 flows 1 to 9 and 11 give the expected results; the title check reads `valid title: test, release impact none`.
- Mutations in a scratch clone of `61262c4` outside the repository, each run with `python3 tests/run_all.py --select` of the file: M1 (`src/workflow_manager/cli.py:768`) fails the default case `7.0.6`; M2 (`cli.py:758`) the pin cases `7.0.1` to `7.0.4`; M2b (`cli.py:768`) `7.0.2` and `7.0.3`; M3 (`docs/update.md:45`) `TestTheDocs::test_the_latest_available_bullet_qualifies_the_kept_pins`; M4 (`tests/test_discovery.py:954`) the control, case "links to something other than a socket"; M5 (`test_discovery.py:954`) the first-directory test, case "a blind directory first hides a listing one"; M8b (`src/workflow_manager/compatibility.py:1969`) `test_an_unknown_record_gets_a_note_with_no_verify_command`. Without `makes that comparison` (`compatibility.py:1973`) `test_a_valid_record_keeps_the_verify_command_in_the_note` fails (#239.2).
- M6 (the bystander `socketpair()` raises, references held so refcounting cannot close them): the base order leaves the test's pair (descriptors 3 and 4) open, the new order closes both.
- M7 (`self.fail("injected")` in place of the signal, both subtests): the base `finally` ends with the chunk group alive and the runner reports one tolerated orphan chunk; the new `finally` ends with it dead (also before the stop file is written) and the declared `orphan_sources` entry is unused.
- Full gate: `evidence: full selection, local, 8 worker(s), head 61262c4e86931a27b07dcd9b3238f2b21f75662a, 2438/2438 units, 16483 tests, selection_digest 9957d343edee4613b59b75a4d916afa09d860b8240978644a6c90b09637c9ef4, tests_digest b27d2bb04042d0cd687849db2df7f132f0385bee75ed1f721beda46a2f5a98be, tree_digest 9b39dc9d271b26a45f6de53412f16a05579fb5db2e0483a46487b8e6d4f18412`, `verdict: exit 0`; the only orphans are the declared `orphan_sources`.

## Functional review checklist

Implementation revision 1; base `26d6850`; the candidate is the tip of `milestone/test-hygiene-3` (the checklist evidence commit, once made, is that tip). The automated gate was run at head `61262c4` (CP2); since then only `docs/` and `docs/ai-workflow/` state commits have landed (`ee27758`, `ab24b78`, `65a3ac2`), so the gate is current. Nothing under `src/`, `tools/`, `.claude/`, `scripts/`, `.workflow-manager/` or `tests/parallel/` has changed since the base.

The item is a test-only change: the four test files, one line of `docs/update.md` and roadmap row 49. There is no user-facing behaviour to exercise. Each flow below checks that the change is what the plan says and that the tests it names fail when the behaviour they name breaks.

### Setup

- A checkout of the candidate (repository root). Flows 1 to 9 and 11 run from it with `git`, `grep`, `sed` and `python3` only: no network, no GitHub, no install.
- Sandbox: flows 1 to 9 and 11 run offline and read-only. Flow 10 writes only to a scratch copy outside the clone and needs the release cache primed (`~/.cache/workflow-manager/releases`, or `XDG_CACHE_HOME`); in a sandbox, copy a primed cache in first, or set `WORKFLOW_MANAGER_RELEASE_SOURCE` to a mirror. Without a primed cache `run_all.py` exits 2 (`PrimingError`) before any test runs.
- Read each exit code with `; echo $?`, not through a pipe. `BASE` is `26d6850bb050a6d66b3afc7d9c22de7e06b12525`.

### Test data

None. The flows read the diff and run the test selections. Flow 10 applies the mutations of the plan's section 3 (below) to a scratch copy, one at a time.

### Flows

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | six files: `tests/test_compatibility.py`, `tests/test_discovery.py`, `tests/test_parallel_runner.py`, `tests/test_release_metadata.py`, `docs/update.md`, `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- src tools .claude scripts .workflow-manager tests/parallel README.md docs/README.md docs/retention.md docs/verify.md docs/exit-codes.md; echo $?` | no output, `0` |
| 3 | `git diff --numstat BASE -- docs/update.md` then `grep -c 'neither this run nor the cache could read' docs/update.md; echo $?` | `1	1	docs/update.md`; then `0` and `1` |
| 4 | `grep -n 'with no trusted cached manifest is kept' docs/update.md` and `grep -n 'Last checked with' docs/update.md` | one match, line 45; the stamp still reads `Workflow Manager 1.14.6, Workflow 2.25.5` |
| 5 | `grep -n 'def _lists_links' tests/test_discovery.py` then `grep -c 'islink' tests/test_discovery.py; echo $?` | `def _lists_links() -> bool:`; then `0` and `1` |
| 6 | `sed -n '/def test_sigterm_and_sigint_kill/,/def test_a_root_run_with_allow_root/p' tests/test_parallel_runner.py \| grep -c '_end_group'` | `1` |
| 7 | `grep -n 'assertIn("verify", found.detail)' tests/test_compatibility.py; echo $?` | no match, `1` |
| 8 | `grep -n -E '^\| 49 ' docs/ROADMAP.md` then `grep -c -E '^\| 50 ' docs/ROADMAP.md; echo $?` | row 49 present, its last cell `Current`; then `0` and `1` |
| 9 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 10 | In a scratch copy outside the clone, apply each mutation of plan section 3 on its own, then `python3 tests/run_all.py --select <file>` for the file the table names (`--select test_release_metadata.py`, `--select test_discovery.py`, `--select test_compatibility.py`). Apply to an unmutated copy first to confirm it passes. | Each mutation fails the test the table names; the unmutated copy passes. M1 `if version == default and exc.newer_manager: return None` in the `except` of `_latest_filter` (`src/workflow_manager/cli.py`, about line 768) fails the default case `7.0.6`. M2 `if version in pins: return None` after the built-in check (about line 758) fails the pin cases `7.0.1` to `7.0.4`. M2b (the same inside the `except`, about line 768) fails `7.0.2` and `7.0.3`. M3 reverts the sentence of `docs/update.md` line 45 fails `TestTheDocs`. M4 makes `_lists_links` test `os.path.islink` (`tests/test_discovery.py` line 954) fails the control case "links to something other than a socket". M5 `if matches: return True` in `_lists_links` fails "a blind directory first hides a listing one". M8b prints ` Run verify now.` for `installation = None` (`src/workflow_manager/compatibility.py` about line 1969) fails `test_an_unknown_record_gets_a_note_with_no_verify_command`. |
| 11 | `python3 tools/release/release.py check-title "test: the discovery, release-metadata, parallel-runner and update-report tests assert what they claim"; echo $?` | `valid title: test, release impact none`, then `0` |

Flows 6 and 7 show that the #166.1 and #239.2 text changed; they do not show that a test is stronger. The strength evidence for #164.3 (M6) and #166.1 (M7) is measured, not a test failure, and is recorded in the self-review above at `61262c4`; it is not repeated as a flow here.

### Known limitations

- The first-directory test depends on the host listing sockets: it skips with the control's reason where the host lists none (plan section 7). This host lists them.
- No `src/` change: a defect in the product is out of scope for this item. A finding that needs one is a Workflow or Manager defect to file, not a fix here.
- Retention commands, Workflow releases, CI and the release pins are out of scope.
- The optional plan-review finding on M7's expected outcome (`LPR1-O01`) is dispositioned at acceptance, not here.

## Next action

Functional review: run the flows above and place any findings at `.ai-review/test-hygiene-3/feedback/FUNCTIONAL_REVIEW.md`. Once testing is clean, `/accept-milestone` is the only acceptance command; both checkpoints (CP1, CP2) are `COMPLETE`. If testing finds a same-scope problem, `/apply-functional-review` takes its bounded branch; a new or wider problem goes to its broad branch.
