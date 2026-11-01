# Active Milestone

## Milestone

`retention-view-steps` -- in implementation (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `e20cfd3`, branch `milestone/retention-view-steps`): roadmap row 24 (#116, items 3 and 4, and the three wording defects of item 5). A `fix:` pull request title (releases Manager 1.14.4; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_VIEW_STEPS_PLAN.md`.

`status --retention` and `doctor --retention` say the right thing: the next step by cause (all `rate_limited`: wait and run again), a linked `scripts/` directory refused like a linked script, the interrupted-removals list cut at five ids with a count, a header that no longer claims a forge query per finished item when there is none, `nothing to archive` with its reason when a finished item has tracked review files, and `1 archive`. Every other output and every exit code stay byte-identical. Item 4's test of every cause (LIR-001), the rest of item 5, item 6 and #147 stay open.

### CP1: the five changes, their tests and the page -- complete

- `retention.py`: `STEP_RATE_LIMITED` and the choice in `_query_failed_note`; the parent check in `_script_is_regular`; `_listed` for the interrupted removals; the zero-finished header; the reason in `next_step`; `_count` for the store line.
- `tests/test_retention_status.py` and `docs/retention.md` (commit `080a6ce`).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 24 is Current and is Done at acceptance.

### Mutation results (scratch clone of `080a6ce`, `test_retention_status` run directly: the candidate passes 69 of 69)

Each mutation exits 1 and fails the case the plan names (extra failures listed):

| Mutation | Failed |
| --- | --- |
| `STEP_FORGE` for every code | `test_the_step_follows_the_failure_code` (the `rate_limited` subtests) |
| `STEP_RATE_LIMITED` when any code is `rate_limited` | `test_the_step_follows_the_failure_code` (the mixed subtests) |
| `_script_is_regular` without the parent check | `test_a_linked_scripts_directory_is_a_missing_script` |
| `', '.join(removing)` | `test_interrupted_removals_are_limited_to_five` (the 6- and 7-id subtests) |
| the limit `5` changed to `4` | `test_interrupted_removals_are_limited_to_five`, plus `test_read_errors_are_listed_with_a_cap_of_five` |
| the limit `5` changed to `6` | `test_interrupted_removals_are_limited_to_five`, plus `test_read_errors_are_listed_with_a_cap_of_five` |
| the old fixed header for zero | `test_the_header_for_zero_finished_items` |
| the `kept_recent`-empty text also for a non-empty `kept_recent` | `test_the_header_for_zero_finished_items` |
| the zero header chosen before the INCOMPLETE header | `test_the_header_for_zero_finished_items` (the incomplete subtests) |
| the bare `nothing to archive` | `test_the_reason_for_nothing_to_archive`, plus `test_items_the_script_would_refuse_get_no_command` |
| the reason also for a folder-absent item | `test_items_the_script_would_refuse_get_no_command` (the archive-present, folder-absent, `tracked_files` 1 subtest) |
| `archives` always plural | `test_the_store_line_counts_the_noun`, plus two older store-line cases |
| the docs row not changed | `test_every_cause_the_code_can_build_is_on_the_page` |

The scratch clone is outside the repository, which was never mutated.

## Next action

The self-review, the full gate (`python3 tests/run_all.py`) and the implementation bundle, then the local implementation review.
