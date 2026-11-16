# Active Milestone

## Milestone

**Complete.** `test-hygiene-3` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `26d6850`, branch `milestone/test-hygiene-3`): roadmap row 49 (added at CP2, Done at acceptance).

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

## Acceptance

Accepted by policy (`/satisfy-gate acceptance`, policy digest `bae758b4f4ce`): all eleven functional flows passed at the approved content, and PR #246's checks are green at its head `6e8b5ae`. Roadmap row 49 is Done; the Optional findings are dispositioned in `docs/milestones/completed/test-hygiene-3-findings.md`.

## Next action

No milestone is ready in `docs/ROADMAP.md` (row 49 was the last). Merge PR #246: a `test:` change, no release. Then `/milestone-plan` for the next item.
