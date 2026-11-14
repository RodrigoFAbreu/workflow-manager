# Workflow Manager: The Age Alert's Next Step Names An Old Item (Revision 4)

`work_item_id: age-alert-next-step` -- `governing_workflow_version: "2.2"`

**Deliverable:** when the retention alert's age threshold is reached, the alert's
`next:` step names the finished item the cleanup's age rule would plan first
(the oldest item older than N days, beyond the 3 most recent, that the cleanup
may plan), instead of the first archivable item in report order, which can be a
young or kept-recent one; and the alert example of `docs/retention.md` is a
complete report that matches what `retention_alert.render` prints. Issue #218
(follow-ups of the age threshold, Manager 1.19.0). Roadmap row 44 (added by this
item, Current now, Done at acceptance). **Work item type:** `process`. **Base
commit:** `61e5b51` (`61e5b51051864f3ce242f09ce1105b3b8365c273`, tip of `main`;
Manager 1.19.0, Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/age-alert-next-step`. **Release:** the text a released command prints
changes: the pull request title is `fix: the age alert's next step names an old
finished item` (`python3 tools/release/release.py check-title` says `fix, release
impact patch`: Manager 1.19.1, `docs/RELEASING.md`); the release-history row goes
in a `docs:` pull request afterwards. **Size:** one checkpoint, one mechanism
(*which item the age line's step names*); the release is the pull request title,
not a checkpoint. The plan is far under 300 lines: no split. Out of scope: the
JSON alert output (#220), any engine-script change, `prune`, a new write path.
The alert is read-only and stays so.

## 1. Investigation (done at `61e5b51`)

| Point | Class | Evidence | Consequence |
| --- | --- | --- | --- |
| 1. The age line's step can name a young or kept-recent item | TRUE-FIX-NEEDED | `retention_alert.py:181-183` sends `finished_items`, `finished_folder_mib` and the age key alike to `retention.next_step`; `retention.py:385-398` takes the first finished entry in report order (newest first, as `retention_cleanup.py:315` says) that is archivable, with no age filter. With one old item at the end of the report and a young one first, the step names the young one. | the age key gets its own step, built from the same rule the cleanup plan uses |
| 2. The cleanup plan's first item for the age rule | KEEP (the reference) | `retention_cleanup.py:311-357`: candidates oldest first, `_eligible` (valid id, no tracked file, `:301-308`), a young or unknown-age item passed over by the age rule alone (`:349-350`), `kept_recent` excluded in `aged` (`retention_alert.py:75-94`), cap 5 (`:28`). Its first item is the oldest eligible old item; its action is `remove only` when an archive is present, else `archive then remove`. | the hint names that item and that action; floor and cap unchanged |
| 3. `retention.next_step` stays byte-identical | KEEP | `retention.py:385` also serves `retention --retention` (`retention.py:481`) and the count and size lines. | not edited; the age step calls it with a one-entry view of the report, so the command text and the release gating (`archive`/`remove` need 2.21.0/2.22.0) stay the function's |
| 4. Count and size rules' steps | KEEP | `_step` branch for `finished_items` and `finished_folder_mib`. | byte-identical for every policy without the age key (golden, flow 5) |
| 5. The alert example of `docs/retention.md` | TRUE-FIX-NEEDED | `docs/retention.md:165-169` prints `finished items: 12, limit 10: reached` and `finished older than 30 days: 4 items ...` next to `archives: at least 5, limit 20: not known (the report is incomplete)`; `retention_alert._shown` (`:193-198`) prefixes `at least ` whenever the report is incomplete, so an incomplete report prints `at least 12` and `at least 4 items`. | make the example a complete report (drop the archives line; the header `3 of 5 thresholds reached` stays right, two of the five are within and not listed); the bullet about incomplete reports already shows `at least` |
| 6. Existing refusals and no-write proofs | KEEP | the alert never writes and never changes an exit code (`alert_lines`' one boundary); the existing `tree_hash` proofs of `test_retention_alert.py` stay and a new end-to-end test adds its own. | no new write path |

## 2. Design

### 2.1 The age step

`retention_alert._step` sends `AGE_KEY` to a new `_age_step(report, days, version,
target)`; the other two item keys keep `retention.next_step(report, version,
target)` unchanged.

`_age_step`: `old, _ = aged(report, days)` (the report-order ids of old items,
the 3 newest excluded). `candidates` are the entries of `report["finished"]`
walked in reverse (oldest first) whose id is in `old` and is accepted by
`plannable_id`. **The rule:** return the step of the first candidate for which
`retention.next_step({**report, "finished": [that entry]}, version, target)`
names a command: `archive` for an item without an archive, `remove` for one with a
readable archive, the update step for a release without the command. This one
actionability check is the whole eligibility test, and it **covers tracked
entries**: a one-entry call for an entry with a tracked review file always returns
the `nothing to archive: ... have tracked review files` text (`retention.py:393`,
`:401`, `:408` all require `tracked_files == 0`), which names no command, so a
tracked entry is skipped by it and the rule has no separate tracked filter (the
cleanup's `_eligible` also refuses a tracked folder, so the two agree). An entry
the script cannot act on is skipped the same way: an unreadable archive
(`archive.readable` false, present or not), a review folder that is not present,
or an id in the report's `removing` whose folder is present with an archive. The
cleanup would plan the first and the last of these (its candidates require the folder present, and its `_eligible` looks at neither readability nor `removing`; a folder that is not present is never old, since the alert examines only present folders, so it is never a candidate of either side), so the
step and the cleanup's first item may differ there, and only there: the cleanup
refuses an incomplete report and one with `removing`, so on a complete report with
no `removing` the one real divergence is `readable=False`; the step then names the
next old item the script can act on, and the page says the preview is not a
promise. If no candidate yields a command, return
`retention.next_step({**report, "finished": <the candidates, oldest first>},
version, target)`, which yields the accurate `nothing to archive: ... have tracked
review files` text when a candidate is tracked, or the bare `nothing to archive`
when none is (every candidate is unreadable or in `removing`), and never names a
young item. An old entry with a rejected id is not a candidate (the walk and the
fallback both skip it), so it is never named even though the engine does not
normally produce one.

The helper `plannable_id(identifier)` and its pattern move from
`retention_cleanup.py` (`_ID`, `RESERVED_IDS`) to `retention_alert.py`, public;
`retention_cleanup._eligible` calls it, so the alert and the cleanup can never
disagree on which id is plannable. No other behaviour of the cleanup changes.

When the count or size rule is also reached, its own step is printed as before
and the age step is added after it, unless they name the same command (`render`
already de-duplicates equal steps): the line may now carry two steps joined with
`; `.

### 2.2 The page

`docs/retention.md`, "The retention alert": the example is a complete report (the
archives line is removed, nothing else in it changes); the bullet that describes
the `next:` step gains: for the age threshold the step names the oldest finished
work item older than N days that `retention-cleanup` would plan first (never one of
the 3 most recent, never a young one); the finished-items and folders rules name
the first archivable item in the report's order, as before. The page's "Last
checked" stamp is not moved by this item.

## 3. Failure-only mutations and tests

All in `tests/test_retention_alert.py` (the helpers `aged_entry`, `age_state`,
`rs.report`, `rs.finished` exist). Scratch copies under `$TMPDIR` (`command cp
-rf`, `command rm -f`), never the repository. The unmutated copy passes every test
of the touched files. Each mutation is confined to one behaviour; the table
states the set of tests that fails with it, existing tests included. The sets are
claims the implementer **measures** in a scratch copy and records in the
implementation summary; a difference is repaired by changing the test or this
table (through an amendment), never by weakening a claim.

Existing tests that pin the old text and change: `test_the_age_line_and_its_variants`
(`tests/test_retention_alert.py:207-232`) builds its expected step with
`retention.next_step(rs.report(*old), ...)`, which names the newest old item; it
now names the oldest (the step is built from `_age_step`'s rule, written out with
the literal id in the test). The block in `docs/retention.md` that the new N6
pins is the only doc text that changes besides the new sentence. No other test
or doc pins the age line's `next:` step: `grep -rn 'finished older' tests docs`
also matches `tests/test_retention_cleanup.py:803/811/866/871` (the cleanup's own
lines, not the alert's step), `docs/ACTIVE_MILESTONE.md`, the plan documents and
`docs/milestones/completed/*` (history), none of which asserts the step.

| Test | Scenario | Mutation | Fails (to measure) |
| --- | --- | --- | --- |
| N1 young first | report order `young, old-a, old-b`, age only, `old-b` the oldest | M1: `_step` sends `AGE_KEY` back to `retention.next_step` | N1, N2, N4, N5, N7, N8, `test_the_age_line_and_its_variants` |
| N2 equals the cleanup | for six reports (oldest old has an archive: `remove`; oldest old is tracked; a kept-recent item is old; an unknown-age item is the oldest; the oldest old item has a rejected id (`runtime` or `Bad_ID`) and the next old one is clean; release below 2.21.0) the id and verb named equal `retention_cleanup.select(state, report).items[0]`'s id and action, and the step text is the command for it; the release-below-2.21.0 scenario names no id or verb, so it asserts instead the update step text and `items[0]`'s action | M2: `_age_step` walks the old items newest first | N1, N2, `test_the_age_line_and_its_variants` |
| N3 tracked first | oldest old item tracked, next old item untracked, exactly two old items: the second is named. A regression test for the actionability check's coverage of tracked entries; it has no mutation of its own (the tracked filter does not exist apart from the actionability check) and fails under M8 | none of its own | none alone; fails under M8 |
| N4 mixed rules | `finished_items` and the age key both reached, exactly one old item, with a young archivable item before it in report order so the count step (`retention.next_step(report)`, the first archivable entry) names a different item from the age step: the step is the count step, then the age step, joined by `; `; and a second report where the one old item is the first archivable entry, so both name the same item: one step | M4: the age result replaces the count result's step | N4 |
| N5 none eligible | exactly one old item, tracked, and a young untracked item present: `nothing to archive: 1 finished work item has tracked review files...`, no command | M5: the fallback passes the whole report | N5, N8 |
| N6 the page | `docs/retention.md` alert block: no `not known` line and `finished items: 12, limit 10`; the age bullet sentence present | M6: restore the old example | N6 |
| N7 end to end | an adopted `notify` policy with the age key, the stub script from `test_retention_status`, `cli verify`, a report with a young first item and exactly one old item: the printed `next:` names that old item; `tree_hash` of the target is equal before and after, and so is the repository's own tree | M1 (the same mutation as N1's) | listed in N1's row |
| N8 not actionable | complete report, no young item first except in (c), age only: (a) oldest old `present=False, readable=False`, next old clean: the next old item's `archive`; (b) oldest old `present=True, readable=False`, next old clean: the next old item's step; (c) the only old item unreadable, a young clean item first: bare `nothing to archive`, never the young item; (d) oldest old in `removing` with its folder and a readable archive present, next old clean: the next old item's step. Each case also asserts `retention_cleanup.select(...).items[0]` is the oldest old item for (a) and (b), pinning where the two differ | M8: `_age_step` returns the one-entry step of the first candidate without checking it names a command | N2 (tracked scenario), N3, N8 |
| N9 rejected id | the sixth scenario of N2 (a rejected id ahead of a clean old item) | M9: `_age_step` drops the `plannable_id` filter | N2 (rejected-id scenario) |

The `Fails` cell of a row is the set of tests its mutation fails, not only the
row's own test; N7's mutation is M1, so N7 appears in M1's set only; N3 has no
mutation and N9 is the rejected-id scenario of N2, listed for M9 (the tests are N1
to N8 and the adjusted existing one; N9 is a scenario, not a ninth test).

Design rules that keep the sets exact: every N2 report and N1 put a young
unarchived untracked item first, N4 a young archivable item before its one old
item (so its joined case needs the count step to differ from the age step, which
M1 breaks), N5 a young untracked item beside its one tracked old item, and N7 and (c) of N8 a young item first. Every test that has an archivable young (non-old) item ahead of its old items fails M1, because M1's step is `retention.next_step(report)` over the whole report and its first loop takes that item: those are N1, N2, N4, N5, N7, N8 (c) and the adjusted existing test, and the set above lists exactly them. N3 has no young item and no other archivable non-old item ahead of its two old items, so M1 passes it. N1 and the
oldest-has-an-archive scenario of N2 have two or more old items (so M2 fails
them), while N3, N4, N7 and each of N8's cases have exactly two, one, one and two
(one in (c)) old items (so M2 passes them), as do N5 (one) and the rejected-id
scenario (two); only N3 and the tracked scenario of N2 have a tracked old item with
an untracked old one behind it, and only N5 has every old item tracked; only N8 has
an old item that is not actionable but is not tracked; only the rejected-id scenario
has an old item with a rejected id. The reports use midnight `generated_at` as the
existing age tests do; N2 reads the plan through `retention_cleanup.select` with an
age-only policy at mode `both`.

Absent-key golden: `describe`, `block`, `render`, the `retention` report section
and `preview_lines` for key-less policies over the same three reports are
byte-identical between `61e5b51` and the candidate (the count and size steps, the
`retention --retention` section and the cleanup preview are untouched).

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The age step, the shared id rule, the example and the tests | - | 2 | 1 |

<!-- CP1 -->
### CP1 -- the age step, the shared id rule, the example and the tests

**Files:** `src/workflow_manager/retention_alert.py`, `src/workflow_manager/retention_cleanup.py`, `tests/test_retention_alert.py`, `docs/retention.md`.

Row 44 of docs/ROADMAP.md is already added (at planning, `Current`; Done at
acceptance): do not add it again. Then sections 2.1 and 2.2, tests N1 to N8 (N2 with its six scenarios) and
the adjusted existing one, their mutations, and the golden. `python3
tests/run_all.py --select test_retention_alert.py --select
test_retention_cleanup.py --select test_retention_status.py --select
test_docs.py` (run `python3 tests/run_all.py --list` first if the release cache
may lack a version), `python3 tools/check_docs.py`, and `git diff --exit-code
61e5b51051864f3ce242f09ce1105b3b8365c273 -- tools .claude scripts
.workflow-manager tests/parallel src/workflow_manager/cli.py
src/workflow_manager/retention.py src/workflow_manager/retention_run.py
src/workflow_manager/retention_policy.py` (no output). docs/ROADMAP.md and
docs/ACTIVE_MILESTONE.md are excluded at both stages, not deliverables. The full
`python3 tests/run_all.py` runs at the implementation review and at acceptance,
never while a file is being written. Comments on #218 record what was done; it
closes at acceptance; #220 stays a separate later item.
<!-- /CP1 -->

## 5. The declaration

`docs/ai-workflow/registry/age-alert-next-step-artifacts.json` must classify every
file path the checkpoint's `Files` paragraph names, at both stages, and protect
every deliverable. The four deliverables (`src/workflow_manager/retention_alert.py`,
`src/workflow_manager/retention_cleanup.py`, `tests/test_retention_alert.py`,
`docs/retention.md`) are excluded at the plan stage and protected at the
implementation stage. Paths named only as byte-identical comparisons or evidence
(`src/workflow_manager/retention.py`, `src/workflow_manager/retention_policy.py`,
`src/workflow_manager/retention_run.py`, `src/workflow_manager/cli.py`,
`tests/test_retention_status.py`, `tests/test_retention_cleanup.py`,
`tests/test_docs.py`, `tools/check_docs.py`, `tests/parallel/resources.json`) get
"named in the plan, not a deliverable" entries at both stages, protected at the
implementation stage where they must stay byte-identical, except
`tests/test_retention_cleanup.py`, `tests/test_retention_status.py` and
`tests/test_docs.py`, which are run only and are excluded at both stages.
`docs/ROADMAP.md` and `docs/ACTIVE_MILESTONE.md` stay excluded at both stages and
are not declared as deliverables. `tests/parallel/resources.json` is not edited.
SELF_REVIEWING_PLAN edits the generated template before the first publish and
checks every path above at both stages.

## 6. Functional review

Offline greps and diffs in a checkout of the candidate; `BASE` is
`61e5b51051864f3ce242f09ce1105b3b8365c273`. Exit codes are read with `; echo $?`,
not through a pipe; greps exclude `docs/ai-workflow` and `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only `retention_alert.py`, `retention_cleanup.py`, `test_retention_alert.py`, `docs/retention.md` and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py src/workflow_manager/retention.py src/workflow_manager/retention_run.py src/workflow_manager/retention_policy.py docs/exit-codes.md docs/verify.md README.md docs/README.md; echo $?` | no output, `0` |
| 3 | `grep -n 'Last checked with' docs/retention.md` | the stamp still reads `Workflow Manager 1.18.1, Workflow 2.29.3` (not moved by this item) |
| 4 | `grep -n -e 'not known (the report is incomplete)' -e 'finished items: 12' docs/retention.md` | the example no longer shows `not known`; the `finished items: 12, limit 10: reached` line stays in a complete report |
| 5 | extract the base `src` with `git archive BASE src \| tar -x -C $TMPDIR/base`, run the scratch driver (a function `driver(state_dir)` the implementer writes into the implementation summary, printing `describe`, `block`, `render` and `preview_lines` for the three reports of the golden, plus the age-key run) once with `PYTHONPATH=$TMPDIR/base/src` and once with the candidate's `src`, `diff` the two outputs | no difference for key-less policies; with the age key, only the `next:` line differs, by the age step (it can gain a second step joined with `; ` when the count or size rule is also reached, which is not a regression), and that step names the oldest old item the script can act on |
| 6 | `grep -n -E '^\| 44 ' docs/ROADMAP.md` and `grep -c -E '^\| 45 ' docs/ROADMAP.md` | row 44 present, last cell `Current`; `0` |
| 7 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 8 | in a scratch copy apply the mutations M1, M4, M5, M8 and M9 of section 3, then `python3 tests/run_all.py --select` the touched test files | each fails the set the table states; the unmutated checkout passes |
| 9 | `python3 tools/release/release.py check-title "fix: the age alert's next step names an old finished item"; echo $?` | `valid title: fix, release impact patch`, `0` |

## 7. Risks

* The age step and the count step can name two different commands on one `next:`
  line when both rules are reached; each is a user-only command with a dry run,
  and the page says so.
* The preview is not a promise (`docs/retention.md`): the engine judges each item
  again; the hint names the cleanup's first item at the time of the report.
* Moving `_ID`/`RESERVED_IDS` is a refactor of two names; the existing id tests of
  `test_retention_cleanup.py` (`REASON_ID`) cover it unchanged.

## 8. Open decisions

* **Decided here, for the owner to veto:** the age step names the cleanup's first
  item (oldest first), not the oldest-first archivable item of the report; when
  several rules are reached each keeps its own step; the page stamp is not moved
  (a re-check of the page is a separate docs item).
