# Active Milestone

## Milestone

**In progress.** `test-hygiene-3` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `26d6850`, branch `milestone/test-hygiene-3`): roadmap row 49 (added at CP2)

The existing discovery, release-metadata, parallel-runner and update-report tests assert what they claim: ten points of #162, #164, #166 and #239. A `test:` change, no release.

### CP1: the descriptor probe and the runner test cleanup -- complete

- `tests/test_discovery.py`: `_lists_links()` takes no parameter and asks what the probe asks (the first existing directory of `_FD_DIRECTORIES` lists the pair's own links); the control test gains a 256 `pipe:[1]` links stand-in; new `test_the_first_existing_directory_decides_what_is_listed`; the second `socketpair()` of the helper test moves inside the `try`.
- `tests/test_parallel_runner.py`: the sigterm/sigint test's `finally` ends the chunk groups through `_end_group` before the stop file, kills a still-running executor, and asserts every group ended; `pgid` is `None` after the success-path death check.
- Verified: `--select test_discovery.py --select test_parallel_runner.py` verdict exit 0 (379 tests); M4 and M5 each fail `TestTheDescriptorProbe` in a scratch copy outside the repository; `src tools .claude scripts .workflow-manager tests/parallel` byte-identical to the checkpoint start.
