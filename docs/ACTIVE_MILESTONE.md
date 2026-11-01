# Active Milestone

## Milestone

`retention-view-hardening` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `e5fa61f`, branch `milestone/retention-view-hardening`): roadmap row 23 (#116, items 1 and 2). A `fix:` pull request title (releases Manager 1.14.3; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_VIEW_HARDENING_PLAN.md`.

`status --retention` and `doctor --retention` print nothing from the engine's JSON report until it has passed a stricter validation: no string with a control character (Unicode category Cc, U+2028, U+2029), every integer in 0 to 2**63 - 1, every string within a stated length, and the `kind` and `schema_version` refusals echo a cut, escaped value. Items 3 to 6 of #116 stay open.

### CP1: the validation and its tests -- complete

- `retention.py`: limits (`INT_MAX`, `PATH_LIMIT`, `ERROR_LIMIT`, `ID_LIMIT`, `SHOWN_LIMIT`), the integer range in `_need`, the control-character and length checks in `_printable`, `_shown` for the two echoes; an `invalid_id` entry's id is exempt (the Manager never prints it).
- `tests/test_retention_status.py`: `TestHardenedValidation` and the extended range case (commit `51086fb`).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 23 is Current and is Done at acceptance.

### Mutation results (scratch clone of `51086fb`, `test_retention_status` run directly: the candidate passes 61 of 61)

Each mutation exits 1 and fails the case the plan names (extra failures listed):

| Mutation | Failed |
| --- | --- |
| the control-character scan removed | the control-character case, the forged-line/escape end-to-end case, plus two `invalid_id` cases |
| only the U+2028/U+2029 clause removed | the control-character case (the separators are among its subtests) |
| `\x85` (C1) no longer refused | the control-character case |
| the length check removed | both length cases, plus the `invalid_id` case |
| the length limit off by one | both length cases |
| the lower bound removed | the integer-range cases |
| the upper bound removed | the integer-range cases, plus the `totals.finished` upper-bound case |
| the range applied to `bytes` only | the every-integer-field case, plus the upper-bound case |
| `removing` items skipped by the scan | the `removing` control-character and length cases |
| the `invalid_id` exemption removed | the `invalid_id` case |
| the exemption widened to every `not_finished` id | the `invalid_id` case, plus the control-character and length cases |
| `kind` echoed untruncated | the echo case |
| `schema_version` echoed untruncated | the echo case |
| `_shown` returns the raw string instead of `repr` | the echo case, plus `test_shown_keeps_a_short_value...` and `test_other_failures_are_case_six` |

The scratch clone is outside the repository, which was never mutated.

## Next action

Self-review the diff, run the full gate (`python3 tests/run_all.py`), then prepare the local implementation review bundle.
