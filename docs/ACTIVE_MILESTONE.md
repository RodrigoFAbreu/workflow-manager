# Active Milestone

## Milestone

`explicit-latest-floor` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan
revision 2, base `0d6ee1f`, branch `milestone/explicit-latest-floor`): roadmap
row 13, issue #85. A `fix:` pull request title (`src/` changes). Plan:
`docs/ai-workflow/WORKFLOW_MANAGER_EXPLICIT_LATEST_FLOOR_PLAN.md`.

### CP1: filter the explicit run's latest by `min_manager_version` -- complete

- `compatibility.explicit_latest(known, metadata, needs, upgrade_page)` drops
  candidates `needs` rejects (a minimum not met, `NEWER_BLOCK`, `MALFORMED_BLOCK`,
  or `UNREADABLE`) and names the newest dropped one with the "upgrade the
  Manager" step; `ReleaseMetadata.read_listed` backs `newest_read`.
- `cli._latest_filter` builds `needs`: built-in data ignored, else the block the
  run read, else the cache's trusted manifest; a pin or the default version is
  never dropped for an unreadable minimum, a damaged non-pinned cached entry is.
- Docs: `update.md` "Latest available" bullet.
- Tests (`tests/test_release_metadata.py`): the `explicit_latest` unit test, four
  CLI tests in `TestMinManagerVersion` (minimum, unusable block, no block,
  damaged entry) and the no-listing suffix assertion. The four new CLI/unit tests
  fail at `0d6ee1f` and pass after; the suffix assertion pins existing behaviour.

Verification: `--select` test_release_metadata, test_discovery, test_docs green.
