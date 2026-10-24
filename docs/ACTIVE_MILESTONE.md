# Active Milestone

## Milestone

`explicit-latest-floor` -- complete (`governing_workflow_version: "2.2"`, `process`, plan
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

## Current checkpoint

**Milestone complete.** `explicit-latest-floor` reached `MILESTONE_COMPLETE`
through `/satisfy-gate acceptance` on 2026-10-24, by policy (the default gate
policy; no person's decision), and `active_work_item_id` is null.
- **Checkpoints:** CP1 is complete.
- **Functional evidence:** flows md1-f1 to md1-f5 passed at `397ed56` (run
  `manager-orchestrator:runs/md1-functional-r1`, an independent Claude executor).
- **Pull request:** #101, CI green at `113490a` (the Workflow's own `gh` query).
- **Findings:** six Optional findings dispositioned (four dropped, two follow-ups
  on #100); record in `docs/milestones/completed/explicit-latest-floor-findings.md`.

## Next action

Roadmap row 14, "Operator polish from the functional review (#84)", is next:
run `/milestone-plan`. The Manager release for row 13 follows the merge of
pull request #101.
