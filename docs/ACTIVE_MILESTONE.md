# Active Milestone

## Milestone

`version-message-wording` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `10213e0`, branch `milestone/version-message-wording`): roadmap row 26 (#145, items 1 and 2). A `fix:` pull request title (releases a Manager patch; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_VERSION_MESSAGE_WORDING_PLAN.md`.

A version taken from the installation record is named in words in the messages that quote it: a null reads as `no workflow_version recorded` (the `next:` line of `verify` and `status`, and the `status` header), an empty value as `''` (the `status` header and the `verify` `version:` line). Every other value, message and exit code is byte-identical. No Workflow change.

### CP1: the wording, its function and its tests -- complete

- `install.record_head` (used by `Status.__str__` and `cli._print_record`), the null branch of `advice._directory_step`, the quoted empty value in `install.verify`, and `TestNotAVersionRows.test_a_version_the_operator_did_not_type_is_named_in_words` (commit `c90589e`).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 26 is Current; the acceptance step marks it Done.

### Mutation results (scratch copy of `c90589e` outside the repository, `python3 tests/run_all.py --select test_operator_ux.py::TestNotAVersionRows`; the candidate passes)

Each mutation exits 1 and fails the case the plan names:

| Mutation | Failed |
| --- | --- |
| (a) `_directory_step` null branch removed | `test_a_version_the_operator_did_not_type_is_named_in_words` (null) |
| (b) `record_head` null branch removed | same case (null) |
| (c) `record_head` empty branch removed | same case (empty) |
| (d) `verify` without the quoting | same case (empty) |
| (e) `_print_record` back to its own f-string | same case (null and empty; `_print_record` only) |
| (f) `shlex.quote` of `_not_a_version`'s directory removed | existing `test_a_null_record_with_a_release_dir_names_one_step_without_it` (`null-manifest update --dry-run`, `null-manifest doctor`) |

No mutation survives. `python3 tests/run_all.py --select test_operator_ux.py` at `c90589e`: 128 tests, `verdict: exit 0`.

## Next action

Run the full gate (`python3 tests/run_all.py`) and prepare the implementation review bundle.
