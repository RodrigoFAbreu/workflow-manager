# Active Milestone

## Milestone

`update-dry-run-match` -- implementation complete, awaiting review (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `76783c9`, branch `milestone/update-dry-run-match`): roadmap row 28 (#145, item 4). A `fix:` pull request title (releases a patch).

`update --dry-run` and the real `update` decide the same way on a record whose `workflow_version` is null: with `--release-version` or `--release-dir` both are accepted (the dry run previews, its header says `from a record with no workflow_version`, not `workflow None`); a run that must choose the release is refused by both with the same cause and step. A record damaged in another way, `doctor`, every other message and every exit code are unchanged. No Workflow change.

### CP1: the dry run's record check, its header, the tests and the docs -- complete

- `src/workflow_manager/cli.py` (the record check in `cmd_dry_run` runs only for a non-null record; `_print_dry_run` words a null record), a comment in `src/workflow_manager/advice.py`, `tests/test_operator_ux.py` (the agreement test, the header test, one row removed from the test that pinned the divergence), `docs/update.md`, `docs/common-problems.md` (commit `74d55a5`).

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 28 is **Current** (done at acceptance); this record.

### Failure-only mutations (each restores one old behaviour, then `python3 tests/run_all.py --select test_operator_ux.py`, restored afterwards)

| Mutation | Fails |
| --- | --- |
| (a) unconditional `_refuse_unparseable_record(installed)` in `cmd_dry_run` | `test_update_and_dry_run_decide_the_same_way_on_a_null_record`, the three accepted rows |
| (b) `_print_dry_run` back to `workflow {plan.current.workflow_version}` | `test_the_dry_run_header_names_a_null_record_in_words` and the agreement test's accepted rows |
| (c) the record check skipped on any explicit run, not only a null record | `test_the_record_is_the_cause_for_each_command_and_its_own_step` |
| (d) `floor=None` in `cmd_dry_run`'s `_choose_and_resolve` call | `test_update_and_dry_run_decide_the_same_way_on_a_null_record` (the refused row) and `test_a_null_record_is_refused_with_one_step_by_update_dry_run_and_doctor` |

Unmutated: `python3 tests/run_all.py --select test_operator_ux.py` green (130 tests, head `74d55a5`).
