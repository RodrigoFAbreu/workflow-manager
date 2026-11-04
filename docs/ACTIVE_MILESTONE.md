# Active Milestone

## Milestone

`retention-view-limits` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `4a98c25`, branch `milestone/retention-view-limits`): roadmap row 29 (#147 items 1 to 3; #116 item 4's test of every cause, item 5's leftovers and the leftover of its last comment). A `fix:` pull request title (releases Manager 1.14.8).

What the retention view (`status --retention`, `doctor --retention`) says about its limits and causes is exact, documented and tested: the value it echoes in a refusal is counted by its own length (`(5000 characters)` for a 5000-character `kind`, where `(5002 characters)` was printed), its page states the limits on the report (the 4096-character limit on `read_errors[].path` is not a strict bound by `PATH_MAX`, and what the view prints above it) and that the zero-finished header belongs to a complete report, and its tests compare the complete refusal and build every cause the view can return (thirteen) from the code. Every other message and exit code is unchanged; no Workflow change.

### CP1: the count, the page and the tests -- complete

- `src/workflow_manager/retention.py` (`_shown` counts the value's own length), `tests/test_retention_status.py` (the complete-refusal comparison, the counting test, the read-error-path fallback test, the causes built from the code, the page test), `docs/retention.md` (the limits subsection, the zero-header sentence, the causes table) (commit `8acd5ee`).

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 29 is Current (Done at acceptance); this record.

### Failure-only mutations

Section 5 of the plan, run in a scratch clone at self-review on `d049409`, one `python3 tests/run_all.py --select test_retention_status.py` each: the unmutated clone exit 0; all 20 mutations exit 1, each failing the test the plan names (the 19 of the plan, with the causes one run each, and one more for the distinct-leads guard: `the UTF-8 cause made the JSON cause's text`, failing `test_the_causes_built_from_the_code_are_what_they_say`). The bundle's `TEST_RESULTS.md` has the table.

### Self-review

Commit `d049409`: the zero-header text is the plan's one sentence (the test no longer rewrites the page to match it), the causes table follows the code's refusal order, the distinct-causes guard compares the thirteen leads rather than the whole texts, the read-error-path test compares the complete refusal line and checks the tree at both sizes, a redundant literal is gone, and the roadmap row counts a number by the characters it is written with.

## Next action


All checkpoints are implemented; the milestone is in self-review and then implementation review.
