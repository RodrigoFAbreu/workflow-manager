# Active Milestone

## Milestone

**In progress.** `test-hygiene-3` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `26d6850`, branch `milestone/test-hygiene-3`): roadmap row 49 (added at CP2, Current now, Done at acceptance).

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
