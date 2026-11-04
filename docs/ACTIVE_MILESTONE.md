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

## Functional review checklist

Checked against implementation revision 3 (reviewed head `6e74814`; later commits change only `WORKFLOW_STATE.json`). The one change in the code is the count in the echoed `kind` and `schema_version` (flows 4 and 5). Flows 1 to 3 check that everything else prints as before; flow 6 checks that the page says what the code prints.

### Setup

- Run the branch's source from the repository root, never the installed `workflow-manager` (pipx 1.13.x has none of this change): `PYTHONPATH=src python3 -B -m workflow_manager ...`. `-B` keeps Python from writing bytecode into the clone.
- Scratch, on disk and not in `/tmp`: `S=$(mktemp -d "$HOME/.cache/rvl-fr.XXXXXX")`. Everything below is created under `$S`, nothing in the clone. Delete it when the flows finish: `rm -rf "$S"`.
- Stand-in `gh` (flow 3 only): `mkdir -p "$S/bin" "$S/gh-log"`; write `$S/bin/gh` as a shell script that appends `$(date -u +%FT%TZ) gh $*` to `$S/gh-log/gh.log`, prints `gh: refused by the functional sandbox (no network)` to stderr and exits 4; `chmod +x` it. Run flow 3 with `PATH="$S/bin:/usr/bin:/bin"`: this machine also has a real `/usr/bin/gh`, which must not be reached.
- Workflow release: the scratch repositories name Workflow 2.25.5. The Manager resolves that release from its cache or from GitHub. If it cannot be resolved (no cache, no network), the status run stops before the retention section: record that flow as **blocked**, not failed.
- Scratch managed repository, for flows 2 to 5: `R="$S/<name>"`; `git init -q "$R"`; `git -C "$R" remote add origin https://github.com/octo/example.git`; copy `scripts/workflow_retention.py` and `scripts/workflow_forge.py` from the clone's `scripts/` into `"$R/scripts/"`; create `"$R/docs/ai-workflow/WORKFLOW_STATE.json"` with the test data below; then record it as managed, run from the clone root:

  ```
  PYTHONPATH=src python3 -B -c "from pathlib import Path; from workflow_manager.installation import Installation as I; I(workflow_version='2.25.5', profile='full', upstream={'repository': 'RodrigoFAbreu/workflow', 'release': '2.25.5'}).write(Path('$R'))"
  ```

  In such a repository the status lines outside the retention block (`unexpected: scripts/...`, `source: not recorded`, `work in flight: unknown`, and the `next:` line about moving a script away) are expected. Ignore them.

### Test data

- **Open item only** (flows 2, 4, 5): `{"schema_version": 1, "active_work_item_id": null, "work_items": {"open-item": {"phase": "IMPLEMENTING", "work_item_type": "process", "governing_workflow_version": "2.2"}}}`.
- **Four finished items** (flow 3): the open item above plus `item-1` to `item-4`, each `{"phase": "MILESTONE_COMPLETE", "work_item_type": "process", "governing_workflow_version": "2.2", "reviewed_implementation_head": <40 hex digits>, "last_transition": "2026-10-0<n>T00:00:00Z"}` (the shape `tests/retention_recipe.py` writes).
- **Echo stubs** (flows 4 and 5): replace the copied `scripts/workflow_retention.py` in the repository with a one-line-per-variable script that prints a single JSON object `{"kind": kind, "schema_version": sv}`, with:
  - 4a: `kind = "x" * 5000`, `sv = 1`;
  - 4b: `kind = "\x1b" * 50`, `sv = 1`;
  - 5: `kind = "retention-report"`, `sv = 10 ** 400`.

  Restore the real script from the clone before flow 2 is run again.

### Flows

1. **Unmanaged repository.** `git init -q "$S/plain"`, then `PYTHONPATH=src python3 -B -m workflow_manager status --retention "$S/plain"`.
   Expected: the first line is `not a managed repository (no .workflow-manager/installation.json)`; then `retention: not available: the repository is not managed by workflow-manager` and `  next: workflow-manager bootstrap <path>`; the status `next:` line follows. The output equals the same command without `--retention` plus those two lines, and the exit status is the same.

2. **Zero finished work items (real script).** The open-item repository, `status --retention "$R"`.
   Expected retention block: `retention (read-only; the Workflow script found no finished work item):`, then `  repository octo/example, archive directory <your home>/.local/share/workflow-archive/example, time to live 30 days`, `  finished work items: 0 (review folders 0 B), kept as the most recent: 0`, `  with an archive: 0 of 0; archive store: 0 archives, 0 prunable (older than 30 days)`, `  interrupted removals: none`, `  next: nothing to archive`. No `gh` call is made.

3. **Forge refused (real script, stand-in gh).** The four-finished repository, `PATH="$S/bin:/usr/bin:/bin" PYTHONPATH=src python3 -B -m workflow_manager status --retention "$R"`.
   Expected: `retention: not available: the forge could not be queried (forge_unavailable, 4 items)` and `  next: install gh and run \`gh auth login\`, then run the command again`. `$S/gh-log/gh.log` holds four `gh pr list --repo octo/example` lines, one per finished-candidate item, and the stand-in refused each. Exit status as without `--retention`.

4. **Long echoed kind.** Stub 4a, then stub 4b, `status --retention "$R"` each.
   - 4a expected: `retention: not available: the script's report has kind 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx... (5000 characters), not 'retention-report'`, then `  next: update workflow-manager to the newest release`. The count is 5000, the length of the value; the line used to say `(5002 characters)`.
   - 4b expected: `... kind '\x1b\x1b\x1b\x1b\x1b\x1b\x1b\x1b\x1b\x1... (50 characters), not 'retention-report'`, the same next step. Before this change the count was 202.

5. **Long echoed schema_version.** Stub 5, `status --retention "$R"`.
   Expected: `retention: not available: the script's report has schema_version` followed by the first 40 printed characters (a `1` then 39 zeros), `... (401 characters); this workflow-manager reads 1`, then `  next: update workflow-manager to the newest release`. A number is counted as before.

6. **The page.** Read `docs/retention.md` in the clone; no run.
   - "Limits on the report" lists: no control characters, 0 to 2**63 - 1, 256, 4096 and 8192 characters, and valid text (the `invalid_id` parenthesis).
   - The path paragraph says 4096 is Linux's `PATH_MAX` and not a strict bound for `read_errors[].path`, quotes the fallback `retention: not available: the script's report is malformed: read_errors[].path is longer than 4096 characters`, and gives the step `python3 -I scripts/workflow_retention.py report` in the repository.
   - The echo paragraph says a value whose printed form is over 40 characters shows its first 40 printed characters, then `... (N characters)`, N being the length of the value itself (a string counts its characters without the quotes).
   - The zero-header paragraph says that in a complete report with no finished work item the first line reads as flow 2 shows, and that an incomplete report keeps `retention: INCOMPLETE` whatever the count.
   - The causes table has one row per cause. Each row's words match the printed text the code gives (for example `the script's report has kind VALUE, not 'retention-report'`, and the cannot-start row with its colon). Check the rows against the output of flows 1 to 5, and against the `not_managed_note`, `no_script_note` and `fetch` texts in `src/workflow_manager/retention.py`.

### Expected results

- Flows 1 to 3: no change from the base; the output and exit status are the ones that were there before. Flow 6: the page matches the code.
- Flows 4 and 5: only the counts differ from the base (5000 for 5002, 50 for 202, 401 unchanged).
- Every flow writes nothing in the clone (check `git status --short` before and after: no new entries).

### Known limitations and out of scope

- The path limit stays at 4096; the Manager does not raise it, and does not print a longer path. The comment next to `PATH_LIMIT` is not edited.
- Causes that flows 1 to 6 cannot reach offline (a timeout, Python that cannot start, output that is not UTF-8 or not one JSON object, an exit status other than 0 or 2, a report with a malformed field) are covered by `tests/test_retention_status.py`, not by these flows. A tester may run them; they are not required.
- Known exception to the zero-header sentence (follow-up, not this item): a report with `complete: false`, read errors, nothing finished or kept, and only `query_failed` items prints the forge note (`the forge could not be queried (...)`) instead of the `retention: INCOMPLETE` header.
- Any other message, the exit codes, the `Last checked with:` stamp of the page, and the Workflow itself are unchanged.
- Optional findings from the plan and implementation reviews are dispositioned at acceptance.

Findings go to `.ai-review/retention-view-limits/feedback/FUNCTIONAL_REVIEW.md` (the resolved feedback directory, printed when this checklist is prepared).

## Next action

Manual functional testing against the checklist above. The gate stays here until the user reports the result.
