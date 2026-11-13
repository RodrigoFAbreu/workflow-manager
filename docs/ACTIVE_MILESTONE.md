# Active Milestone

## Milestone

`retention-max-age` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `8ff4f43`, branch `milestone/retention-max-age`): roadmap row 43 (#215). A `feat:` pull request title (`feat: add an age threshold to the retention policy`, Manager 1.19.0); the release-history row follows in a `docs:` pull request.

One new optional policy key, `thresholds.finished_max_age_days` (integer, 1 to 3650): finished work items with a review folder, beyond the 3 most recent, whose last transition is more than N days before the report's own `generated_at` count toward the retention alert and are planned by `retention-cleanup`, oldest first, at most 5 per run. An item with no usable last transition is never old.

### CP1: the policy key and the alert line -- complete (when committed)

- `retention_policy.THRESHOLDS` gains the key (maximum 3650, unit ` days`); `schema_version` stays 1. `retention_alert.aged(report, days)` is the one helper; `evaluate`, `_shown` and `render` special-case the key (label `finished older than N days`, reached at one old item).
- Tests: T1 to T3 (policy), A1 to A6 (alert). Roadmap row 43 added.

### CP2: the cleanup plan and the page -- not started

**Next action:** `/milestone-implement retention-max-age` for CP2.
