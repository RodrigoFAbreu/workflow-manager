# Active Milestone

## Milestone

`retention-view-steps` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `e20cfd3`, branch `milestone/retention-view-steps`): roadmap row 24 (#116, items 3 and 4, and the three wording defects of item 5). A `fix:` pull request title (releases Manager 1.14.4; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_VIEW_STEPS_PLAN.md`.

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

## Functional review checklist

The automated flows below run offline, in a sandbox with no network, no real `gh`, `claude`, `codex` or `ssh`, and no write inside the product clone. Flow 9 is the one flow that needs the network or a primed release cache; the user runs it outside the sandbox. The exact helper scripts are in section 6 of the plan (`docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_VIEW_STEPS_PLAN.md`); the notes under "Setup" correct them.

### Setup

- Tools: `python3` (always with `-I`), `git`, `tar`, `ln`, `diff`. Nothing else on `PATH`. No `gh` is needed: the stub script replaces the Workflow script, so no forge call happens.
- Scratch: set `S` yourself to a new, empty directory outside the product clone (`S=<dir>`). The plan's `$TMPDIR/fr` assumes `TMPDIR` is set, which a sandbox may not do.
- Build, reading the product clone only (`git archive` writes nothing into it):
  `mkdir -p $S/t/scripts $S/base $S/cand`, then `git archive e20cfd3 src | tar -x -C $S/base` and `git archive HEAD src tests/fixtures | tar -x -C $S/cand`.
- Stub `$S/t/scripts/workflow_retention.py` (one line): `import os,sys;sys.stdout.write(open(os.environ["R"]).read())`.
- Renderer `$S/run.py`, report maker `$S/mk.py` and the run form `R=<report.json> python3 -I $S/run.py $S/<base|cand> <target> 2.22.0` are as in the plan.
- The finished item's tracked-file count is `review_folder.tracked_files` (not a top-level key). Flows 6 and 8 set that key.
- Flow 2 starts from flow 1's report (`finished` and `kept_recent` empty, `totals.finished` 0, `totals.finished_folder_bytes` 0), not from the fixture: with the fixture's kept items the report is INCOMPLETE and the forge note is not reached.

### Test data

- `tests/fixtures/retention_report.json` from the candidate tree: one finished item (`item-1`, review folder present with 1 tracked file, no archive), three `kept_recent` items, `totals` finished 1, archives 0, complete.
- Each flow edits one copy of that fixture through `mk.py`; the fixture itself is never edited.

### Flows

Each row runs for `cand` and for `base` (the `e20cfd3` tree) with the same report and target. "Expect" is what was observed when this checklist was prepared.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | empty `finished` and `kept_recent`, `totals.finished` 0, folder bytes 0, `not_finished` = one `query_failed:rate_limited` entry | cand: `retention: not available: the forge could not be queried (rate_limited, 1 items)` and `next: wait for the forge's rate limit to reset, then run the command again`; base: the same cause with `next: install gh and run `gh auth login`, then run the command again` |
| 2 | flow 1's setup with `not_finished` = one `gh_missing` entry; then with `rate_limited` for w1 and `gh_missing` for w2 | cand and base byte-identical each time, with the `gh auth login` step (the mixed case reads `rate_limited, 2 items`) |
| 3 | `mkdir $S/t2; ln -s $S/t/scripts $S/t2/scripts`; valid report; render with `$S/t2` | cand: `retention: not available: the repository has no scripts/workflow_retention.py (the Workflow release that ships it is 2.20.0 or later)` and `next: workflow-manager update <t2>`; base prints the full section |
| 4 | valid report with `removing` = 7 ids `a1`..`a7`; then 5 ids; then 6 | cand: `interrupted removals: a1, a2, a3, a4, a5 and 2 more`; 5 ids joined as before; `... a5 and 1 more`; base joins every id |
| 5 | complete report, `finished` [], `totals.finished` 0, folder bytes 0; first with `kept_recent` [], then with the fixture's 3 `kept_recent` items; then the same with `complete` false | cand headers: `retention (read-only; the Workflow script found no finished work item):`, then `... found no finished work item beyond the 3 most recent):`; the INCOMPLETE case prints `retention: INCOMPLETE (read-only); the numbers below are lower bounds` in both trees. base prints `made one forge query per finished item` for the first two |
| 6 | the one finished item with `review_folder.present` true, `review_folder.tracked_files` 2, no archive | cand: `next: nothing to archive: 1 finished work item has tracked review files; the script archives and removes only untracked folders`; base: `next: nothing to archive` |
| 7 | `totals.archives` 1; then 0; then 2 | cand: `archive store: 1 archive,`, `0 archives,`, `2 archives,`; base: `1 archives,` for the first, the same for 0 and 2 |
| 8 | `review_folder.tracked_files` 0 (archivable) and `totals.archives` 2 | cand and base byte-identical; the next line is the `archive item-1 --apply` command; no `retention: not available` line |
| 9 | outside the sandbox, with network or a primed release cache: `git clone --no-hardlinks "$PWD" $S/clone`, `git -C $S/clone checkout <candidate head>`, then `python3 tests/run_all.py --select test_retention_status.py` in the clone | exit 0 |

### Known limitations

- The stub replaces the Workflow script, so the live `gh` path, the real script's report and its exit codes are not exercised offline. Exit codes are covered only by flow 9.
- The installed Workflow engine emits no `rate_limited` code yet (plan section 2), so the `rate_limited` step is reached only through the fixture and the stub.
- Out of scope and still open: item 4's test of every cause (LIR-001), the rest of item 5, item 6 (checklist notes), #147, and any change to the Workflow engine.
- Every other output and every exit code stay as they were; a difference in any of them is a finding.

### Evidence

The checklist is the content of this file at the evidence commit named in the handoff message (`Workflow-Functional-Checklist` trailer on `milestone/retention-view-steps`). Findings go to `.ai-review/retention-view-steps/feedback/FUNCTIONAL_REVIEW.md`.

## Next action

Functional review: run flows 1 to 8 (offline, in the sandbox) and flow 9 (with network), and report each result against the expectations above. Clean testing is followed by `/accept-milestone`, which needs every checkpoint `COMPLETE` (both are). Findings go to `FUNCTIONAL_REVIEW.md` and `/apply-functional-review` routes them.
