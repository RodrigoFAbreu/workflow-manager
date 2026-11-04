# Active Milestone

## Milestone

`latest-default-arm` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `d785aa8`, branch `milestone/latest-default-arm`): roadmap row 30 (#100). A `test:` pull request title (releases nothing).

The default-version arm of the filter that keeps a release this Manager cannot use out of the explicit run's latest (`_latest_filter`) is pinned by tests, and the `Latest available` bullet of `docs/update.md` no longer says a pin or the default version is "always named": the keep applies to a release whose `manager` block neither the run nor the cache could read. No behaviour, printed text or exit code changes; no Workflow change.

### CP1: the arm test and the true sentence -- complete

- `tests/test_release_metadata.py` (`TestTheLatestFilterKeepsTheDefault`, four tests, and the docs test), `docs/update.md` (the one sentence) (commit `3fff782`).

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 30 is Current (Done at acceptance); this record.

### Failure-only mutations

Plan section 3, run in a scratch clone at `3fff782` and again at self-review on `ae06bf1`, one `python3 tests/run_all.py --select test_release_metadata.py` each: the unmutated clone exit 0; all five mutations exit 1, each failing the test the plan names (delete `or version == default`: the default-with-no-pins test and the pin test; delete `version in pins or`: the pin test; the default skips the run's block: the unmet-minimum test, and the cached-block test too, since that early return skips both block sources; the default skips the cache's block: the cached-block test, subtests `7.0.9` and `7.0.8`; the qualification removed from `docs/update.md`: the docs test). The bundle's `TEST_RESULTS.md` has the table.

### Self-review

The diff against `d785aa8` was read against plan sections 2 and 3: no finding, no code change. `src/workflow_manager/cli.py` is not edited; no user page still says "is always named".

## Next action

Local implementation review of the bundle.
