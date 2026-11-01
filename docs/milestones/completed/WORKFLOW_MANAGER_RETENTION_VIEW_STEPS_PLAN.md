# Workflow Manager: What the Retention View Tells the Operator Is Right (Revision 3)

`work_item_id: retention-view-steps` -- `governing_workflow_version: "2.2"`

**Deliverable:** `status --retention` and `doctor --retention` choose the
forge next step by the failure code, refuse a linked `scripts/` directory like
a linked script, limit the interrupted-removals list, and fix three texts
(header for zero finished items, a reason for `nothing to archive`, `1 archive`)
(roadmap row 24, issue #116 items 3 and 4 and the wording defects of item 5,
follow-ups of rows 17 and 23).

**Work item type:** `process`. **Base commit:** `e20cfd3`
(`e20cfd3353bc3f09b088cf985db66fceaa4617e0`, tip of `main`, Manager 1.14.3;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/retention-view-steps`. **Scope source:** `docs/ROADMAP.md` row 24
(added by this item, Current now, Done at acceptance). A `src/` change in the
Manager: the pull request title is `fix: ...`, a patch (**Manager 1.14.4**,
checked with `python3 tools/release/release.py check-title`). One mechanism:
what `retention.py` says and refuses. Two checkpoints. One review surface: the
fetch and render functions of one module and the tests that pin them.

## 1. Each item checked against main (`e20cfd3`)

| Item | Still present on main? | Evidence |
| --- | --- | --- |
| (a) forge step for `rate_limited` | Yes | `_query_failed_note` returns `STEP_FORGE` whatever the code |
| (b) linked `scripts/` directory | Yes | with `scripts` a link to a directory holding the script, `_script_is_regular` answers `True` (run on main) |
| (c) interrupted-removals list | Yes | `render` joins every id with `', '.join(removing)` |
| (d1) header for zero finished | Yes | the header is one fixed string |
| (d2) `nothing to archive` without a reason | Yes | `next_step` returns the bare text for every blocked case |
| (d3) `1 archives` | Yes | five assertions in four existing tests pin `1 archives` (section 4 names them) |

None is already fixed. Out of scope, stays open: item 4 LIR-001 (a test builds
two causes; a test-only item), the rest of item 5 (the fixture description,
the `chmod 000` root case), item 6 (checklist notes), everything in #147, and
any change to the Workflow engine.

## 2. Decisions

* **The step follows the code.** `_query_failed_note` takes the code of every
  failed entry (the part after `query_failed:`). If **every** code is exactly
  `rate_limited` the step is the new `STEP_RATE_LIMITED`: `wait for the
  forge's rate limit to reset, then run the command again`. For any other
  code, and for a mix of codes, the step is `STEP_FORGE`, byte for byte as
  today. The cause text (`the forge could not be queried (CODE, N items)`,
  with the first code) is unchanged. The engine installed here (Workflow
  2.25.5) emits `forge_unavailable` for a missing or unauthenticated `gh` and
  has no separate authentication code and no `rate_limited` code yet, so the
  login step remains the step of every code but `rate_limited`; the Manager
  reads the code as an opaque string and needs no engine change.
* **A linked `scripts/` directory is a missing script.** `_script_is_regular`
  also answers `False` when the script's parent directory is a link. The
  refusal is the existing `no_script_note`: same cause, same step
  (`workflow-manager update TARGET`), and the script is never started.
* **Interrupted removals use `_listed`.** Five or fewer ids print as before
  (`a, b, c`); more print the first five, then `and N more`. `none` and the
  not-reported line are unchanged.
* **The header for zero finished items.** The engine puts the first
  `KEEP_RECENT` (3) merged items in `kept_recent` and only the rest in
  `finished`, so `totals.finished` 0 does not mean no merged item was found.
  The new header replaces **only the complete-report header**; the INCOMPLETE
  header still wins and is unchanged. For a complete report with
  `totals.finished` 0: `kept_recent` empty gives `retention (read-only; the
  Workflow script found no finished work item):`; `kept_recent` of N items
  gives `retention (read-only; the Workflow script found no finished work item
  beyond the N most recent):`. For one or more finished items the header is
  unchanged. Both new texts stay true beside the `kept as the most recent: N`
  line.
* **`nothing to archive` gets a reason only when one is known.** When no
  command applies and at least one finished item has a review folder present
  with tracked files (the script archives and removes untracked folders only),
  the step is `nothing to archive: N finished work item(s) with tracked review
  files; the script archives and removes only untracked folders`, exactly
  `1 finished work item has` / `N finished work items have` (see section 3).
  Every other blocked case (folder absent, unreadable archive, a leftover
  removal) keeps the bare `nothing to archive`.
* **The store line counts correctly.** `1 archive`, `0 archives`, `2 archives`:
  one helper picks the noun. `prunable` is an adjective and unchanged.
* **Docs.** `docs/retention.md` changes where its text is now different: the
  forge row of the table, the `next` bullet and a sentence on the zero header
  and on the interrupted-removals limit. No internal milestone id is named.

## 3. Exact texts

| Place | Before | After |
| --- | --- | --- |
| forge step, every code `rate_limited` | `install gh and run `gh auth login`, then run the command again` | `wait for the forge's rate limit to reset, then run the command again` |
| forge step, any other code or a mix | same | same (unchanged) |
| header, complete, `totals.finished` 0, `kept_recent` empty | `retention (read-only; the Workflow script made one forge query per finished item):` | `retention (read-only; the Workflow script found no finished work item):` |
| header, complete, `totals.finished` 0, 3 in `kept_recent` | same | `retention (read-only; the Workflow script found no finished work item beyond the 3 most recent):` |
| header, incomplete (any `totals.finished`) | `retention: INCOMPLETE (read-only); ...` | same (unchanged) |
| step, 1 item with tracked files | `nothing to archive` | `nothing to archive: 1 finished work item has tracked review files; the script archives and removes only untracked folders` |
| step, 2 items | `nothing to archive` | `nothing to archive: 2 finished work items have tracked review files; the script archives and removes only untracked folders` |
| store line, 1 | `archive store: 1 archives, 0 prunable (older than 30 days)` | `archive store: 1 archive, 0 prunable (older than 30 days)` |
| interrupted removals, 7 ids | `interrupted removals: a1, a2, a3, a4, a5, a6, a7` | `interrupted removals: a1, a2, a3, a4, a5 and 2 more` |
| interrupted removals, 5 ids | five ids joined | unchanged |

## 4. Tests (`tests/test_retention_status.py`)

All through the `Scratch` stub engine (the stub prints a JSON file): no `gh`,
no network. Each end-to-end case runs `status --retention` **and** `doctor
--retention` through `both()` (same exit code as without `--retention`, no
traceback). Every failure path checks the tree is unchanged
(`tree_hash`, no `__pycache__`) and the stub's marker file for whether the
script started.

* **Step by code.** All entries `rate_limited` (one and three) give the note
  with exactly `STEP_RATE_LIMITED`; `gh_missing`, `forge_unavailable` and a mix
  of `rate_limited` and `gh_missing` give the literal old step text; the cause
  is unchanged. `STEP_FORGE`'s literal value is pinned so a rewording fails.
* **Linked directory.** `scripts` a link to a directory holding the stub: the
  `no_script_note` cause and step for both commands, marker file absent (the
  script never ran), tree unchanged. The existing linked-file case stays.
* **Interrupted removals.** 0, 1, 5, 6 and 7 ids: the exact lines of section 3
  (`none`, the single id, five ids, `and 1 more`, `and 2 more`).
* **Header.** Complete report, zero finished: `kept_recent` empty gives the
  exact first new line; `kept_recent` of 1 and of 3 give `beyond the 1 most
  recent` / `beyond the 3 most recent`; one finished: the exact old line.
  Incomplete report with zero finished (once through `complete` false, once
  through a `query_failed:` entry): the first line is the unchanged INCOMPLETE
  header and neither new text appears. The `query_failed:` case keeps
  `report()`'s three `kept_recent` items: with `kept_recent` empty and only
  failed entries `_query_failed_note` replaces the report with the forge note,
  and no header prints.
* **Reason.** `step()` over one and two tracked-file items gives the two exact
  texts; the other blocked cases (folder absent, unreadable archive, the
  leftover removal, archived with tracked files but folder absent) keep the
  bare text; a report that also has an archivable item prints the command, not
  the reason. The two cases of the existing refused-items test that now carry a
  reason are edited to the new text.
* **Store line.** Exact lines for 0, 1 and 2 archives. The five existing
  assertions that pin `1 archives` are edited to `1 archive`, in four tests of
  `tests/test_retention_status.py`:
  `test_a_complete_report_prints_the_section_before_the_last_next_line` (line
  239), `test_an_unrelated_archive_never_reads_as_one_of_zero` (321),
  `test_store_figures_and_coverage_move_independently` (340 and 344) and
  `test_the_real_script_counts_an_unrelated_archive_in_the_store_only` (357).
* **Docs.** `TestDocs` also requires `STEP_RATE_LIMITED` and the reason text on
  the page.
* **Unchanged.** Every test of `retention.py` other than the four named above
  and the refused-items and `STEP_FORGE` cases named in this section stays
  unedited and green.

**Failure-only mutations** (a scratch clone, never the repository; each
passes on the real code and must fail as stated):

| Mutation | Must fail |
| --- | --- |
| `STEP_FORGE` for every code (old behaviour) | the `rate_limited` case |
| `STEP_RATE_LIMITED` when **any** code is `rate_limited` | the mixed case |
| `_script_is_regular` without the parent check | the linked-directory case |
| `', '.join(removing)` (old line) | the 6- and 7-id cases |
| the limit `5` changed to `4` or `6` | the 5- and 6-id cases |
| the old fixed header for zero | the zero-header cases (`kept_recent` empty and non-empty) |
| the `kept_recent`-empty text also for non-empty `kept_recent` | the `beyond the N most recent` cases |
| the zero header chosen before the INCOMPLETE header | the incomplete-report zero-finished cases |
| the bare `nothing to archive` | both reason cases |
| the reason also for a folder-absent item | the last case of `test_items_the_script_would_refuse_get_no_command` (archive present, folder absent, `tracked_files` 1); the plain `folder absent` case (`tracked_files` 0) does not catch it |
| `archives` always plural | the 1-archive cases |
| the docs row not changed | the `TestDocs` case |

Evidence at implementation: `python3 tests/run_all.py --select
test_retention_status.py` green and each mutation failing the case named, then
the full gate `python3 tests/run_all.py`.

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The five changes, their tests and the page | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the five changes, their tests and the page

**Files:** `src/workflow_manager/retention.py`, `tests/test_retention_status.py`,
`docs/retention.md`.

Section 2 and section 4. `tests/test_retention_status.py` is the one existing
test file that pins changed text (`1 archives`, the bare `nothing to archive`
cases, the `STEP_FORGE` table check); no other test pins it. `docs/retention.md`
changes only the lines section 2 names.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 24 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: the `fix:` title releases Manager 1.14.4. Both
files stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 6. Functional review

Flows 1 to 8 run offline with `python3 -I` only, outside the repository, in a
small scratch, with **no** Workflow release cache, no `gh` and no network.
Flow 9 is the one exception: the runner primes the release cache before any
selection (`tests/parallel/cli.py`, `priming.prime`), so it needs a primed
cache or the network, and it runs in a clone made with `git clone --no-hardlinks
"$PWD" $S/clone` and checked out at the candidate (`git -C $S/clone checkout
<candidate head>`). No flow bootstraps a release: the target is built by hand and the section is
rendered by calling `retention.section` from the base and the candidate.
Setup: `S=$TMPDIR/fr; mkdir -p $S/t/scripts`; `git archive e20cfd3 src | tar
-x -C $S/base` (after `mkdir $S/base $S/cand`); `git archive HEAD src tests/fixtures
| tar -x -C $S/cand`. Stub `$S/t/scripts/workflow_retention.py`: `import
os,sys;sys.stdout.write(open(os.environ["R"]).read())`. Renderer `$S/run.py`:
`import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]+"/src");from
workflow_manager import retention as r;print("\n".join(r.section(Path(sys.argv[2]),sys.argv[3])))`.
Report maker `$S/mk.py`: loads `$S/cand/tests/fixtures/retention_report.json`,
sets `complete` true and `read_errors` `[]`, `removing` `[]`, runs the
statements in `argv[1]` with the report bound to `r` (`exec(sys.argv[1],
{"r": r})`), and prints JSON. A `not_finished` entry needs both keys, e.g.
`{"work_item_id":"w1","reason":"query_failed:rate_limited"}`. Run a flow as `R=$S/r.json
python3 -I $S/run.py $S/<base|cand> $S/t 2.22.0` for both trees and compare
(`diff`). The exit codes of the commands are covered by flow 9.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | report with `finished` and `kept_recent` `[]`, `totals.finished` 0, `totals.finished_folder_bytes` 0, and `not_finished` one entry: `r["not_finished"]=[{"work_item_id":"w1","reason":"query_failed:rate_limited"}]` | candidate: the note, step `wait for the forge's rate limit to reset, then run the command again`; base: the `gh auth login` step |
| 2 | the same with `r["not_finished"]=[{"work_item_id":"w1","reason":"query_failed:gh_missing"}]`; then `r["not_finished"]=[{"work_item_id":"w1","reason":"query_failed:rate_limited"},{"work_item_id":"w2","reason":"query_failed:gh_missing"}]` | candidate and base print byte-identical notes with the `gh auth login` step |
| 3 | on a second target, so `$S/t` stays intact for flows 4 to 8: `mkdir $S/t2; ln -s $S/t/scripts $S/t2/scripts`; valid report; render with `$S/t2` in place of `$S/t` | candidate: `retention: not available: the repository has no scripts/workflow_retention.py ...` and `workflow-manager update` step; base prints the section |
| 4 | valid report with `removing` set to 7 ids `a1`..`a7`; then 5 ids; then 6 | candidate: `a1, a2, a3, a4, a5 and 2 more`; five ids joined; `... and 1 more`; base joins all |
| 5 | complete report with `finished` `[]`, `totals.finished` 0, `finished_folder_bytes` 0; first with `kept_recent` `[]`, then with the fixture's 3 `kept_recent` items; then with `complete` false (keeping the 3 `kept_recent` items) | candidate headers `retention (read-only; the Workflow script found no finished work item):`, `... found no finished work item beyond the 3 most recent):`, and the unchanged INCOMPLETE header; base: the `one forge query per finished item` header for the first two |
| 6 | valid report whose one finished item has `review_folder.present` true and `tracked_files` 2 and no archive | candidate step `nothing to archive: 1 finished work item has tracked review files; ...`; base `nothing to archive` |
| 7 | valid report with `totals.archives` 1; then 0; then 2 | candidate `1 archive,`, `0 archives,`, `2 archives,`; base `1 archives,` for the first |
| 8 | the valid report with the finished item's `tracked_files` set to 0 (an archivable item) and `totals.archives` 2 | candidate and base byte-identical, `diff` empty, and no `retention: not available` line |
| 9 | in the clone, `python3 tests/run_all.py --select test_retention_status.py` (the one flow that needs a primed release cache or the network) | exit 0 |

## 7. Risks

* A repository whose engine one day reports a code spelled differently from
  `rate_limited` keeps the login step: the safe, existing behaviour.
* The zero header is a text change for every repository with no finished item,
  by design; its counts and every other line are untouched.

## 8. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
