# Workflow Manager: The Retention Report, Alert And Docs Say Exactly What The Code Does (Revision 4)

`work_item_id: retention-pins-and-wording-2` -- `governing_workflow_version: "2.2"`

**Deliverable:** one released-output fix (an incomplete retention report is shown as
incomplete, never as a forge failure), one shared refusal helper, and the tests
and docs that pin the retention wording. Roadmap row 48 (added by this item,
Current now, Done at acceptance) is this item. It closes the open points of
#160 (1, 2), #222 (1 to 3), #225 (1 to 4) and #216 (1); the archived-plan points
of #216 are KEEP (section 1).

**Work item type:** `process`. **Base commit:** `a2431446dac2d2741f89da08a001e52b91083f3a`
(tip of `main`; Manager 1.20.2, Workflow 2.29.6 installed, automatic gates).
**Branch:** `milestone/retention-pins-and-wording-2`. **Release:** a patch.
The pull request title is `fix: an incomplete retention report is never shown as a forge failure, and the retention pins and wording match the code`,
to be checked with `python3 tools/release/release.py check-title` (release impact
patch, Manager 1.20.3): one output of a released command changes, in one edge
case (section 2.1). Everything else is tests and docs and releases nothing by
itself. **Size:** two checkpoints, one mechanism (*the retention text and the
tests agree with the code*), about 200 lines of plan: no split. CP1 is the code
and its output, CP2 the tests and docs.

## 1. Investigation (done at the base commit)

| Point | Class | Evidence |
| --- | --- | --- |
| #160.1 the zero-header sentence has one exception | TRUE-FIX-NEEDED (code) | `src/workflow_manager/retention.py:293-303`: `_query_failed_note` reads no `complete`; the script sets `complete` to `not errors` (`scripts/workflow_retention.py:549`), so `complete: false` with read errors, nothing finished or kept, at least one `query_failed` item and none answered by the forge (`no_pull_request`, `pr_not_merged:*`) prints the forge note and hides the read errors; other entries (`open_phase`, `invalid_id`, `family_open`, `no_anchor`) do not stop it. `docs/retention.md:46` says an incomplete report keeps its first line |
| #160.2 two limit sentences pinned by no test | TRUE-FIX-NEEDED | `docs/retention.md:82` ("from 0 to 2**63 - 1", the `invalid_id` clause); `tests/test_retention_status.py` `TestDocs` (`:1157`) holds neither; `retention.INT_MAX` (`:32`) and `:206` carry the number |
| #222.1 age step without the unreadable-archive exception | TRUE-FIX-NEEDED (docs) | `docs/retention.md:174`; `retention_alert._age_step` (`:189-202`) passes over an old item whose archive is unreadable; `tests/test_retention_alert.py:337-348` pins it (case b: the cleanup plans `old-a` first, the step names `old-b`) |
| #222.2 only a prefix pinned | TRUE-FIX-NEEDED | `tests/test_retention_alert.py:306-309` asserts `startswith("  next: this Workflow release has no \`archive\` command; ")` |
| #222.3 `1 items` | KEEP | `retention_alert._shown` (`:219-223`) is the one source of the age line; `docs/retention.md:171` documents the line as `finished older than N days: K items` (and `at least K items`), `tests/test_retention_alert.py:901` pins `1 items`. A singular form changes the documented shape of a working path; the issue itself leaves it to a later UX item |
| #225.1 dead `record.write_text("{")` | TRUE-FIX-NEEDED | `tests/test_retention_alert_json.py:406` runs against `self.outside`, which is unmanaged, so the corrupt record is never read |
| #225.2 duplicated refusal block | TRUE-FIX-NEEDED | `src/workflow_manager/cli.py:895-900` (`_doctor_json`) and `:924-930` (`cmd_doctor`): `error: could not resolve the target release: ...`, `advice.next_step`, `next:`, return 2 |
| #225.3 deprecation line filtered out | TRUE-FIX-NEEDED | `tests/test_retention_alert_json.py:400` drops every `workflow-manager:` line, so the `--manager-root` case never asserts `cli.MANAGER_ROOT_DEPRECATION` |
| #225.4 archive count moves 0 to 1 | TRUE-FIX-NEEDED | `tests/test_retention_alert_json.py:248-253`: the first report has no archive, the second has one |
| #216.1 old link text | TRUE-FIX-NEEDED | `docs/README.md:15`, `docs/update.md:53`, `docs/verify.md:40`, `docs/exit-codes.md:11` and `:30` (the issue says `:28`) read `[Retention report](retention.md...)`; the page's title is `Retention: the report, the policy, the alert and the cleanup` |
| #216, archived plan and declaration points | KEEP | files bound by an approval and archived under `docs/milestones/completed/`; editing them re-opens a closed item and changes nothing a user reads |

No point is ALREADY-FIXED. Output texts that change: one report predicate, in section 2.1. Tests
and docs that pin the old output: none for the edge case (it is unpinned); two
fixtures build a partial report without `complete`
(`tests/test_retention_status.py:1204` and `:1298`) and get `"complete": True`.

## 2. Design

### 2.1 The note reads `complete` (CP1)

`_query_failed_note` returns `None` when `report["complete"]` is false, so the
report is returned and rendered, and the page's sentence at `docs/retention.md:46`
becomes exact with no change to it. Why the code and not the page: with read
errors the report names what could not be read, which the forge note hides; the
forge note stays for a complete report, where it is the only fact.

The note's predicate today (`retention.py:293-303`): at least one `not_finished`
entry is `query_failed:*`, none is `no_pull_request` or `pr_not_merged:*`, and
`finished` and `kept_recent` are empty. Entries of any other reason
(`open_phase`, `invalid_id`, `family_open`, `no_anchor`) may be present: they do
not stop the note. The guard adds one condition, `complete` is true, so the
affected set is every **incomplete** report that meets that predicate, with or
without such other entries.

| Report | Before | After |
| --- | --- | --- |
| complete, predicate met (only `query_failed`, or `query_failed` plus `open_phase`/`invalid_id`/`family_open`/`no_anchor`) | forge note | forge note (byte-identical) |
| `complete: false`, predicate met, only `query_failed` | forge note | the report: first line `retention: INCOMPLETE ...`, read errors listed, the forge items under `not checked against the forge` |
| `complete: false`, predicate met, `query_failed` plus an ordinary `open_phase` entry (or another of the four) | forge note | the same report as the row above: `retention.render` (`retention.py:431-482`) lists read errors and `query_failed` items only, so the other entry is not listed (its id appears on no line), as in every report today |
| any report that does not meet the predicate | unchanged | unchanged |

`retention.fetch` is the report source of four commands, so for the affected set
four outputs move, and no other. Only invocations the parser accepts are listed:
`status --retention` has no `--json` (`cli.py:1219-1225` rejects it, exit 2), and
`doctor --retention --json` prints the alert document, never a report.

| Invocation | Before | After |
| --- | --- | --- |
| `status --retention`, `doctor --retention` (text) | the forge note | the report, first line `retention: INCOMPLETE ...` |
| `doctor --retention --json` (the alert document, `cli.py:879-904`) | the forge cause, no report fields | the incomplete-report document: `report_complete: false`, the threshold results and the snapshot present, with no threshold reached the cause is the incomplete one (`retention_alert_json._build`, `:117-124`), otherwise the evaluated document with its alerts, no cause and `report_complete: false` (an `archives`/`prunable_archives` threshold reads `totals`, which an incomplete report still has); the shape is not touched |
| `verify` (the alert as text, `cli.py:966-971`; `retention_alert.assess`, `retention_alert.py:302-305`) | the forge cause | with no threshold reached, the incomplete-report case the page documents (`docs/retention.md:175`); otherwise the reached line (`at least`) |
| `retention-cleanup` (`retention_cleanup.py:244-251`) | refused at step 7: `the forge could not be queried (CODE, N items)` and the forge step | refused at step 8: `retention cleanup: the retention report is incomplete (the numbers are lower bounds)` and `retention.STEP_INCOMPLETE`; nothing written |

`docs/retention.md:285-286` (refusal order: 7 the report can be had, 8 the report
is complete) stays exact: the report can now be had, and step 8 refuses it.

**Golden (CP1 evidence, not a test):** the supported invocations, enumerated
and run on base `src` (`git archive`) and on the candidate: `status --retention`
and `doctor --retention` (text lines compared), `doctor --retention --json` (the
alert document: its fields compared separately from the text lines), `verify`
(the alert text) and the `retention-cleanup` preview. The corpus: complete or
not, with or without finished and kept items, with no, some or all items
`query_failed`, `query_failed` mixed with an `open_phase` entry (complete and
incomplete), and the three refusal shapes. The complete mixed report is
byte-identical in every invocation; the incomplete mixed report is paired with
it and moves exactly as the table says. Only an incomplete report meeting the
predicate differs, and the golden names each invocation whose output moves and
checks its before and after against the table (for `retention-cleanup` the
step 7 to step 8 change, with the tree hash unchanged). The refusal-helper
output (section 2.2) is compared byte for byte over the same corpus.

### 2.2 One refusal helper (CP1)

`cli._refuse_release_resolution(args, error) -> int` prints the
`error: could not resolve the target release: ...` line, the `next:` line when
`advice.next_step` has a step, and returns 2; `cmd_doctor` and `_doctor_json` call
it. No output changes; X1 (`test_X1_refusals_before_any_document`) already pins
equal stderr of the two paths (it stays green when the helper changes, because
both paths call it), and the text path's own tests pin the bytes.

### 2.3 Tests and docs (CP2)

| Point | Change |
| --- | --- |
| #160.2 | `TestDocs`: the page holds `from 0 to 2**63 - 1` and `retention.INT_MAX == 2**63 - 1`; the page holds the `invalid_id` clause and a report with an `invalid_id` entry of invalid text is refused while one of valid text is not (the code behaviour the sentence states) |
| #160.1 (cleanup) | `tests/test_retention_cleanup.py`, `TestPreflight`: one case for the report of section 2.1 (`complete: false`, nothing finished or kept, `query_failed` items, with and without an `open_phase` entry): refused at step 8 with `ra.CAUSE_INCOMPLETE` and `retention.STEP_INCOMPLETE`, nothing written (`refusal_writes_nothing`); `test_an_incomplete_report` (`:682-690`) uses `many()`, which has finished items, and never meets this report |
| #160.1 | one sentence in "If the report is incomplete": an incomplete report is shown as incomplete even when every forge query failed, and the forge cause below is for a complete report; `TestDocs` pins the sentence and the first-line sentence of `:46` |
| #222.1 | `:174` gains: except an old item whose archive cannot be read, which the cleanup plans first and the step passes over to the next old item (or `nothing to archive`); `TestAgeStep` pins the clause |
| #222.2 | the release-below-2.21.0 scenario compares the whole line `  next: this Workflow release has no \`archive\` command; workflow-manager update /scratch/repo`, not a prefix |
| #225.1 | the last case of the release-option test runs against `self.repo` with the corrupt record (the refusal is first); the `self.outside` case stays |
| #225.3 | the `--manager-root` case asserts two lines: `cli.MANAGER_ROOT_DEPRECATION` and the error line; the other options keep one line |
| #225.4 | the first report sets `totals.archives` to 1, so the archive is in both and the item enters `archived_and_removed` through eligibility alone |
| #216.1 | the five links read `[Retention: the report, the policy, the alert and the cleanup](retention.md...)`; `TestDocs` checks that every link to `retention.md` in the four pages has the page title as its text |

No stamp moves: each page changes in a sentence or a link and is not re-checked
as a whole (flow 3). No new option; `tests/parallel/resources.json` is untouched.

## 3. Failure-only mutations

Scratch clones under `$TMPDIR` (`command cp -rf`, `command rm -f`), never the
repository; the unmutated clone passes, the mutated one fails the named test.

| # | Mutation | Failing test |
| --- | --- | --- |
| M1 | the `complete` guard removed from `_query_failed_note` | the new incomplete-report tests (plain and mixed, CP1) and the new `retention-cleanup` cases |
| M2 | the guard made unconditional (`return None` for any report) | the existing forge-note tests for a complete report, and the new complete mixed counterpart |
| M3 | `_refuse_release_resolution` drops its `next:` line | `tests/test_operator_ux.py`'s `test_c1_doctor_prints_the_release_cause_and_its_step` (`:2117`) (X1 stays green: both paths call the helper; `tests/test_discovery.py:545` also pins it but is outside the `--select` list) |
| M4 | the page's `2**63 - 1` reworded to `2**31 - 1` | the limits pin |
| M5 | the `invalid_id` clause removed from the page | the clause pin |
| M6 | the unreadable-archive clause removed from `:174` | the age-step docs pin |
| M7 | `workflow-manager update` removed from the step's tail | the full-text comparison (the prefix test stays green: that is the gap) |
| M8 | one link text restored to `Retention report` | the link-text pin |

Each mutation of the code (M1 to M3) is a measured `--select` run, as are the
planned cleanup refusal and its no-write case, the unchanged complete-report
outputs and the unchanged helper output; each failure
path of M1 and M3 also has a no-write proof: `status` and `doctor` leave the tree
hash of the target unchanged (the existing no-write helpers).

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The note reads complete, one refusal helper | - | 2 | 1 |
| CP2 | The tests and the docs | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the note reads `complete`, one refusal helper

**Files:** `src/workflow_manager/retention.py`, `src/workflow_manager/cli.py`, `tests/test_retention_status.py`, `tests/test_retention_cleanup.py`.

First add row 48 after row 47 of docs/ROADMAP.md in the style of the rows above
it (Current; Done at acceptance). Then sections 2.1 and 2.2: the guard, the
two fixtures, one `retention-cleanup` case for the same report (section 2.3), tests for the incomplete report (through `fetch` and `render`:
the report comes back, first line `retention: INCOMPLETE`, the forge items
listed; the incomplete mixed report (`query_failed` plus `open_phase`) renders the same way (first line, the forge item listed, the `open_phase` id absent from every rendered line, so the test and `render` agree); and
its complete counterpart, like the complete report of only `query_failed` items, still gives the forge note, for
`rate_limited` and another code), the helper. Run M1 to M3, the golden of
section 2.1, `python3 tests/run_all.py --select test_retention_status.py --select
test_retention_alert.py --select test_retention_alert_json.py --select
test_retention_cleanup.py --select test_doctor_cli.py --select test_operator_ux.py` (run `python3 tests/run_all.py
--list` first if the release cache may lack a version). docs/ROADMAP.md and
docs/ACTIVE_MILESTONE.md are excluded at both stages, not deliverables.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the tests and the docs

**Files:** `tests/test_retention_status.py`, `tests/test_retention_alert.py`, `tests/test_retention_alert_json.py`, `docs/retention.md`, `docs/README.md`, `docs/update.md`, `docs/verify.md`, `docs/exit-codes.md`.

Section 2.3, then M4 to M8, `python3 tools/check_docs.py`, the same `--select`
list as CP1 plus `test_docs.py`, and
`git diff --exit-code a2431446dac2d2741f89da08a001e52b91083f3a -- tools .claude scripts .workflow-manager tests/parallel`
(no output). The full `python3 tests/run_all.py` runs at the implementation
review and at acceptance, never while a file is being written. Comments on
#160, #222, #225 and #216 record what was done and the KEEP decisions; they
close at acceptance (#222 and #216 with the KEEP noted).
<!-- /CP2 -->

## 5. The declaration

`docs/ai-workflow/registry/retention-pins-and-wording-2-artifacts.json` must
classify every path this plan names as a file to change or to compare at both
stages and protect every deliverable. SELF_REVIEWING_PLAN edits the generated
template before the first publish: the four source and test files of CP1, the
two test files and five pages of CP2 are excluded at the plan stage and
protected at the implementation stage; `.claude/`, `scripts/` and
`.workflow-manager/` are compared by diff only and fall under prefixes the
declaration lists; `tools/` and `tests/parallel/` are compared by diff only (flow 2,
CP2) and are listed nowhere, because nothing writes them; `docs/ROADMAP.md` and
`docs/ACTIVE_MILESTONE.md` stay excluded at both, not deliverables. No edit of
`tests/parallel/resources.json`.

## 6. Functional review

Offline greps and diffs in a checkout of the candidate; `BASE` is
`a2431446dac2d2741f89da08a001e52b91083f3a`. Exit codes are read with `; echo $?`.
Flows 8 and 10 run `tests/run_all.py`, which primes the release cache before
dispatch (`tests/parallel/cli.py:261`; `ReleaseCache.ensure` fetches a missing
entry from the configured source, GitHub by default): they are offline only with a
complete release cache or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md' ':!docs/milestones'` | only `src/workflow_manager/retention.py`, `src/workflow_manager/cli.py`, the four test files, the five declared pages and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- tools .claude scripts .workflow-manager tests/parallel README.md docs/glossary.md; echo $?` | no output, `0` (untouched pages and trees) |
| 3 | `git diff BASE -- docs/retention.md docs/README.md docs/update.md docs/verify.md docs/exit-codes.md \| grep -c '^[-+]> For:'` | `0` (no stamp moved: none of the five pages is re-checked as a whole) |
| 4 | `grep -rn --exclude-dir=ai-workflow --exclude-dir=milestones --exclude=ACTIVE_MILESTONE.md '\[Retention report\](retention' docs README.md; echo $?`, then `grep -rc --include='*.md' '\[Retention: the report, the policy, the alert and the cleanup\](retention.md' docs/README.md docs/update.md docs/verify.md docs/exit-codes.md` | no output, `1`; counts `1`, `1`, `1`, `2` |
| 5 | `git diff BASE -- src/workflow_manager/retention.py` | one added guard on `report["complete"]` in `_query_failed_note` and its docstring, nothing else |
| 6 | `grep -n 'complete' docs/retention.md \| sed -n 1,8p` and `grep -c 'cannot be read' docs/retention.md` | the added incomplete-report sentence beside `:46`'s sentence; the age-step clause present (count `1` or more) |
| 7 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 8 | `python3 tests/run_all.py --select test_retention_status.py --select test_retention_alert.py --select test_retention_alert_json.py --select test_retention_cleanup.py --select test_docs.py; echo $?` | `verdict: exit 0` |
| 9 | `grep -n -E '^\| 48 ' docs/ROADMAP.md` and `grep -c -E '^\| 49 ' docs/ROADMAP.md` | row 48 present, last cell `Current`; `0` |
| 10 | in a scratch copy apply M1, then M4, with `sed`, and run `--select` of the named file | each FAILED (M1: the incomplete-report tests; M4: the limits pin); the unmutated checkout passes |

## 7. Risks

* The status and doctor reports, the alert (and `verify`) and `retention-cleanup`
  move for the incomplete reports of section 2.1's predicate; the page already documents the
  incomplete cases, and no output of a complete report or of a report with
  finished items changes.
* The link-text pin reads the page's first heading; a later title change then
  needs five link edits, which is what the pin is for.

## 8. Open decisions

* **For the owner, no blocker:** #222.3 is KEEP (documented shape of the age
  line); the archived-plan points of #216 are KEEP (bound records).
