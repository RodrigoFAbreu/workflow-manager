# Active Milestone

## Milestone

`retention-max-age` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `8ff4f43`, branch `milestone/retention-max-age`): roadmap row 43 (#215). A `feat:` pull request title (`feat: add an age threshold to the retention policy`, Manager 1.19.0); the release-history row follows in a `docs:` pull request.

One new optional policy key, `thresholds.finished_max_age_days` (integer, 1 to 3650): finished work items with a review folder, beyond the 3 most recent, whose last transition is more than N days before the report's own `generated_at` count toward the retention alert and are planned by `retention-cleanup`, oldest first, at most 5 per run. An item with no usable last transition is never old.

### CP1: the policy key and the alert line -- complete (`66ba841`)

- `retention_policy.THRESHOLDS` gains the key (maximum 3650, unit ` days`); `schema_version` stays 1. `retention_alert.aged(report, days)` is the one helper; `evaluate`, `_shown` and `render` special-case the key (label `finished older than N days`, reached at one old item).
- Tests: T1 to T3 (policy), A1 to A6 (alert). Roadmap row 43 added.

### CP2: the cleanup plan and the page -- complete (`d64d6c3`)

- `retention_cleanup.select` plans the age rule: `LOWERED` gains the key (reached at one old item not yet planned), the loop takes an item when a count or size threshold is reached or the item is old, `Plan.unknown_age`, the `age not known` line and the age wording in the preview. `docs/retention.md` documents the key, the older-Manager refusal, the alert line and the cleanup rule.
- Also: `retention_alert._moment` no longer calls `retention_policy._is_timestamp` (a private cross-use `TestNoPrivateCrossUse` forbids); it carries its own pattern.
- Tests: C1 to C8 (cleanup). The absent-key golden (flow 5) is identical except the `Result` repr's new `unknown_age` field.

### Self-review -- complete (`3c2e096`)

- Every mutation of plan section 3 measured in a scratch clone: three rows first differed from the table (A2, C1, `LOWERED`), each repaired by changing a test (C7 without an unknown-age item, the nothing-to-do case folded into C3, C2 reads the key with a default, C5 and C8 walk a young item first); after the repair all 18 measured sets equal the table.
- `docs/retention.md`: the alert example lists the age line where `render` prints it (before archives); the cleanup's "below its limit" sentence says what that means for the age threshold.
- Absent-key golden (flow 5): `describe`, `block`, `render` and `preview_lines` for three key-less policies over three reports are byte-identical at the base and the candidate (88 lines).
- Known limitation for the reviewers (the plan pins it): the age line's `next:` step is `retention.next_step`, which names the newest archivable item, possibly a young one.
- Full gate at `3c2e096`: `python3 tests/run_all.py`, 2410/2410 units, 16273 tests, `verdict: exit 0`.

**Next action:** the implementation bundle (revision 1) at `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`.
