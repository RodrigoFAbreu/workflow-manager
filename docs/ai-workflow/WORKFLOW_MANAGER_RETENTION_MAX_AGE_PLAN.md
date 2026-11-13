# Workflow Manager: An Age Threshold For Finished Work Items (Revision 4)

`work_item_id: retention-max-age` -- `governing_workflow_version: "2.2"`

**Deliverable:** one new optional policy key, `thresholds.finished_max_age_days`
(integer, 1 to 3650). Finished work items with a review folder, beyond the 3 most
recent, whose last transition is older than N days count toward the retention
alert (a new line, like the other thresholds) and are planned by
`retention-cleanup` (modes `cleanup` and `both`), oldest first, within the
existing limit of 5 per run. The owner can say "finished work older than N days
is clutter" in the policy file. Roadmap row 43 (added by this item, Current now,
Done at acceptance) is this item (issue #215; owner decision 2026-11-13, option
C). **Work item type:** `process`. **Base commit:** `8ff4f43`
(`8ff4f435d8890d906dd167eac711434eaf751f03`, tip of `main`; Manager 1.18.1,
Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/retention-max-age`. **Release:** a new policy key is a new feature:
the pull request title is `feat: add an age threshold to the retention policy`
(`python3 tools/release/release.py check-title` says `feat, release impact
minor`: Manager 1.19.0, `docs/RELEASING.md`); the release-history row goes in a
`docs:` pull request afterwards. **Size:** two checkpoints, one mechanism
(*an age rule over the report's own `last_transition`*); the release is the
pull request title, not a checkpoint. The plan is far under 350 lines: no split.
No Workflow engine change: the report JSON already carries the data. The
product code outside `retention_policy.py`, `retention_alert.py` and
`retention_cleanup.py` stays byte-identical.

## 1. Investigation (done at `8ff4f43`)

| Point | Finding | Consequence |
| --- | --- | --- |
| The report has the age data | `scripts/workflow_retention.py` writes `generated_at` (`_iso(now)`, `%Y-%m-%dT%H:%M:%SZ`, UTC) and, per item, `last_transition` (the state file's string, or `null` when absent or not a string: `last or None`). The Manager's `retention._validate` checks neither field, so a report with a missing or odd one is accepted today | the age is computable from the existing JSON; no engine change; the Manager parses the two fields itself and treats anything unusable as "age not known" (section 2.2). `_validate` stays unchanged, so no existing report is newly refused |
| The 3-newest floor is the report's | `_assemble` puts `merged[:KEEP_RECENT]` (3, newest `last_transition` first) in `kept_recent` and only `merged[KEEP_RECENT:]` in `finished` | `finished` never holds the 3 newest. The age rule additionally drops any id of `kept_recent` it meets in `finished`, so the floor holds even for a report that lists one in both (a test pins it) |
| Report order | `finished` is newest first; an item with no `last_transition` sorts last in it (key `""`), so it comes **first** in the oldest-first order `retention_cleanup.select` walks | the age rule must take only items known to be old, or an unknown-age item at the front would be planned (section 2.3) |
| The policy file is closed and strict | `retention_policy.policy_errors` refuses an unknown key and an unknown threshold (`unknown threshold 'finished_max_age_days'`); `load` then returns state `invalid`, mode `off` | an **older Manager refuses a file carrying the new key and falls back to `off`**: it neither alerts nor cleans. `docs/retention.md` says so. A newer Manager reads every older file unchanged |
| `schema_version` | the loader requires exactly the integer 1 | **it stays 1.** The key is optional and additive; a file without it means exactly what it meant. A bump would give an older Manager the same outcome (refused, `off`) with a less specific message, and would force the new Manager to accept two versions and decide which keys each allows. The closed-key rule needs no bump: it already refuses safely |
| Thresholds in the alert | `retention_alert.evaluate` walks `retention_policy.THRESHOLDS` in order; `_measured` returns the report's number; reached is `value >= limit`; an incomplete report gives lower bounds (at or above is reached, below is `unknown`, never within); `render` prints `N of M thresholds reached` and one line per non-within result | the new key joins `THRESHOLDS` and the same walk; its measured number is a count of old items and it is reached at 1 or more |
| Thresholds in the plan | `retention_cleanup.select` keeps only `LOWERED` keys, takes eligible items oldest first while a lowered threshold is reached, at most `CAP = 5`; `plan_digest` hashes the repository, the policy digest and the `[id, action]` pairs | the new key joins `LOWERED`; the digest needs no change: the policy digest already moves when the key is added, removed or changed, and the items move with the age |
| The confirming sentence | `retention_policy.sentence` names the first 12 characters of the policy digest; `retention_cleanup.sentence` those of the plan digest; `cmd_retention_cleanup` selects again and refuses a sentence that names another plan | a changed policy needs a new adoption (new digest, as today). The plan digest hashes only the repository, the policy digest and the ordered `[id, action]` pairs, so a changed age invalidates a confirmation **only when it changes the selected items or their actions** (an item that crosses the age and is then selected, or one that stops being selected); a later `generated_at`, or an item that crosses the age and is not selected (for example a sixth old item beyond the cap of five, which turns `settled` into `cap`), leaves the digest and an accepted sentence unchanged (existing behaviour, said in the docs exactly so) |
| `last_transition` shape | `YYYY-MM-DDTHH:MM:SSZ`, UTC, as every state writer stamps it (`WORKFLOW_STATE.json`); the fixture `tests/fixtures/retention_report.json` carries it, with `generated_at` `2026-10-27T00:00:00Z` | parsed with the exact pattern of `retention_policy._is_timestamp` (fullmatch plus `strptime`); no time zone is guessed |
| Files that stay | `src/workflow_manager/cli.py` prints thresholds only through `retention_policy.describe`; `docs/exit-codes.md` and `docs/verify.md` name no threshold list | no change to either; `describe` gains the new key by walking `THRESHOLDS` |

## 2. Design

### 2.1 The policy key

`retention_policy.THRESHOLDS` gains `"finished_max_age_days": (3650, "finished
age limit")`, placed after `finished_folder_mib`; `_UNITS` gains `" days"`.
`policy_errors` already validates every `THRESHOLDS` key (integer, not a bool,
1 to the maximum), so the range 1 to 3650 and the refusals need no new code.
`describe` prints `finished age limit 30 days`. `SCHEMA_VERSION` stays 1. A
policy without the key digests, validates, describes and previews exactly as it
does at the base (a pinned literal digest, section 3).

### 2.2 What "older than N days" means (pinned)

An item is **old** when `generated_at - last_transition > N * 86400` seconds:
strictly greater, so an item exactly N days old is not old, and one second more
is. "Now" is the **report's own `generated_at`**, not the Manager's clock: the
alert, the plan and the confirmed run each judge the one report they hold, a
test needs no clock, and the Manager's clock never disagrees with the report.
Both values must match `[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z`
and name a date that exists. **Age not known** (never old, never planned by the age rule): `last_transition`
absent, `null`, not a string, or not that form; and, when `generated_at` itself
is unusable, every item. A `last_transition` later than `generated_at` (a clock
that ran ahead) is not unknown, it is simply not old. Only entries with a review folder present, not listed in
`kept_recent`, are examined.

`retention_alert.aged(report, days) -> (old, unknown)` is the one pure helper,
used by the alert and the plan: `old` is the list of entry ids (report order),
`unknown` the number of examined entries whose age is not known.

### 2.3 The alert

`_measured` for the new key returns `len(old)`; the limit for the comparison is
1 (reached at one old item or more), while `Result.limit` keeps the policy's N
for printing. `Result` gains `unknown_age: int = 0`. Incomplete reports follow
the existing rule (lower bound: reached still reached, zero old is `unknown`).
The line, in the `render` order of `THRESHOLDS`:

```text
  finished older than 30 days: 4 items: reached
  finished older than 30 days: at least 4 items: reached   (incomplete report)
  finished older than 30 days: 4 items, 2 more with no usable last transition (not counted): reached
  finished older than 30 days: not known (the report is incomplete)
```

`render`, `_shown` and the preview's `_measured`/`_names` special-case the key: its
label in every line is `finished older than N days` (never the `describe` label
`finished age limit`, and never the `{label}: {value}, limit {limit}` shape), its
value reads `K items` (`at least K items` for a lower bound), and the alert's
`N of M thresholds reached` counts it as one threshold. The `next:` step is the one of `finished_items` (`retention.next_step`). Nothing
is printed for a within result, as for every threshold; the unknown-age note
appears only on a printed line. `Result`s of the other keys, and the whole block
when the key is absent, are byte-identical.

### 2.4 The cleanup plan

`LOWERED` gains the key, and the cleanup's own reached test for it is the alert's:
**reached means at least one old item is not yet planned**, never `old count >= N`
(`_limit`, `_reached` and the preview's `left` special-case the key; `N` is a
duration, not a count). `Plan.before` and `after` carry it only when the policy
sets it (its value: the old items not yet planned); `Plan` gains
`unknown_age: int = 0`. The loop of `select` stays as it is when the key is
absent. With the key set it walks the eligible items oldest first and takes an
item when **a count or size threshold is reached** (the existing rule, so an
unknown-age item may still be planned by it, as today) **or the item is old**;
a young or unknown-age item is passed over, not taken, when only the age rule is
reached. It stops at `CAP = 5`, or when nothing is reached and no old item
remains. The age counts of `before`/`after` are old items that were not planned.
An old item that is ineligible (Git tracks files under its folder, or its id is
not the engine's) is `skipped` with the existing reason and keeps the age
threshold reached, so the outcome is `exhausted`, as for the other thresholds.
`CAPPED` (`run it again`) is said only when more can still be planned: the cap
was hit and at least one **eligible** item remains that is old, or that the
count or size rule would still take; an old item that is only ineligible keeps
the threshold reached but never makes the outcome `cap` (5 old eligible, 1 old
tracked, 3 young: first run takes 5 and ends `exhausted`). The `kept_recent`
exclusion is the age rule's own, inside `aged`: it does not filter `candidates`,
so `before["finished_items"]` and the count and size rules' plans are
byte-identical to the base for every report, including one that lists an id in
both `kept_recent` and `finished`.

Preview text, only with the key set: `thresholds reached:` names it as
`finished older than 30 days 4`; `after this run:` as `finished older than 30
days 0`; `nothing to do` as `finished older than 30 days 0`; and, when
`unknown_age > 0`, one line `  age not known: K finished items with no usable
last transition are never planned by the age rule`. The plan digest is the
existing function; a changed policy, or an age change that alters which items are selected or their
actions, changes it; another `generated_at` alone, or an item that becomes old
without being selected, does not.

### 2.5 The page

`docs/retention.md` (stamp unchanged: it names the installed versions, which do
not move here): the key joins the table (`finished_max_age_days`, integer, 1 to
3650: finished items with a review folder, beyond the most recent ones, whose
last transition is more than N days before the report's own time; one that has no
usable last transition never counts); a paragraph says the file is closed, so
**an older Manager refuses a file with this key and treats the mode as `off`**,
that `schema_version` stays 1, and that adding the key changes the digest, so the
policy is adopted again; the alert section gains the new line and drops "four", and two sentences that
are true only for counts are amended for the age key: "A number **at or above**
its limit is reached" (the age key is reached at one old item; `N` is a
duration) and "until every threshold the policy sets is below its limit" in the
cleanup section;
the two sentences that say "the four thresholds" (line 158 at `8ff4f43`) and "only the two thresholds that archiving and removing can lower take part" (line 191) are edited in place, not added beside; the cleanup section says the age rule joins the two lowered thresholds, takes
only items known to be old, never the 3 most recent, at most 5 per run, and that
an item crossing the age between the preview and the confirmed run invalidates the
sentence only when it changes the selected items or their actions (the digest
hashes those and the policy, not the time), in which case the preview is run
again.

## 3. Failure-only mutations and tests

Scratch copies under `$TMPDIR` (`command cp -rf`, `command rm -f`), never the
repository. The unmutated copy passes every test of the touched files. Each
mutation is **confined to one behaviour** and the table states the **complete**
set of tests of the touched files that fails with it, existing tests included
(`test_retention_policy`, `test_retention_alert`, `test_retention_cleanup`,
`test_retention_status`). The sets are claims the implementer **measures**: every
mutation is applied in a scratch copy and the measured set recorded in the
implementation summary; a difference is repaired by changing the test or this
table through a plan amendment, never by weakening the claim. Design rules that
make the sets hold: only A1 and C8 test the second-exact boundary; only A2, A5
and C3 use an item with no usable last transition; only C5 uses a day count
above 30 (every other cleanup test uses 10 or 30 days); only A4 lists an entry
without a review folder (so the cleanup tests and A1 to A3, A5, A6 have none);
only A3 and C2 list an id in both `kept_recent` and `finished`; only C4 (second
scenario), C6 and C7 have an old ineligible item (one tracked item old enough, so
the age key stays reached after selection); only C4 has more than 5 old
eligible items; only A1 and C8 use a `generated_at` that is not midnight (A1:
`2026-10-27T13:45:10Z`), every other test uses midnight, so flooring it to
midnight changes nothing for them; only T3 reads `describe` (or the policy status
output) of a policy that sets the key; the whole verdict line of the preview is
asserted only by C4 and C7 (the other cleanup tests assert plan fields, the
`age not known` line, or the sentence); C5's three plans differ in their items
(an item 30.5 days old), so their digests differ whatever the policy digest;
no existing test sets the new key.

| # | Test (file) | What it pins | Mutation (in the copy) | Fails (complete) |
| --- | --- | --- | --- | --- |
| T1 | `test_the_age_key_is_valid_from_one_to_3650` (policy) | 1 and 3650 accepted; 0, 3651, `True`, `1.5`, `"30"` refused; `schema_version` 2 refused | maximum 3650 to 3651 | T1 |
| T2 | `test_the_digest_of_a_policy_without_the_key_is_unchanged` (policy) | literal digest of the documented example policy at the base; the same policy with the key has another policy digest and another adoption sentence, and the key's value changes it too | `canonical` drops `thresholds.finished_max_age_days` | T2 |
| T3 | `test_cleanup_mode_may_set_only_the_age_key` (policy) | valid; `describe` reads `finished age limit 30 days`; absent key leaves `describe` as at the base | `" days"` removed from `_UNITS` | T3 |
| A1 | `test_age_is_strictly_greater_than_n_days_of_the_reports_own_time` (alert) | exactly N x 86400 s is not old; one second more is; N from the policy | `>` to `>=` in `aged` | A1, C8 |
| A2 | `test_an_item_with_no_usable_last_transition_is_never_old` (alert) | missing key, `null`, an integer, `2026-10-01`, `2026-10-01T00:00:00+00:00`, month 13, a lone date, a future moment: none old; the first six counted `unknown`, the future one not; an unusable `generated_at` makes every item unknown | in `aged`, an unparsable `last_transition` is counted old (and still unknown) | A2, A5, C3 |
| A3 | `test_the_three_newest_are_never_counted` (alert) | an id in `kept_recent` listed again in `finished` is not counted; old ones beyond are | the `kept_recent` exclusion removed from `aged` | A3, C2 |
| A4 | `test_an_item_without_a_review_folder_is_not_counted` (alert) | `present: false` not counted, not unknown | the folder test removed from `aged` | A4 |
| A5 | `test_the_age_line_and_its_variants` (alert) | the four lines of section 2.3 (label `finished older than N days`, never `finished age limit`), `N of M thresholds reached`, the `next:` step, a within result prints nothing | the unknown-age note dropped from `render` | A5 |
| A6 | `test_an_incomplete_report_gives_a_lower_bound_for_the_age` (alert) | `at least`, and `unknown` for zero old | in `evaluate`, the age key's result treats an incomplete report as complete | A5, A6 |
| C1 | `test_the_age_rule_alone_plans_only_old_items_oldest_first` (cleanup) | young items not planned; order oldest first; actions as for the other rules | the age test dropped from the loop of `select` (every eligible item taken once the age is reached) | C1, C3, C5, C6, C7, C8 |
| C2 | `test_the_age_rule_never_plans_the_three_newest` (cleanup) | a report whose `kept_recent` holds three very old items and whose `finished` lists one of them again: none planned; the count rule's plan for the same report equals the base's | as A3 | A3, C2 |
| C3 | `test_the_age_rule_never_plans_an_item_whose_age_is_unknown` (cleanup) | an unknown-age item at the front of the oldest-first order is passed over; the old ones behind it are planned; the preview prints the `age not known` line with the count; with a count threshold also reached the existing rule may still plan it (documented) | in `select`'s loop the age test is "not young" instead of "old" | C3 |
| C4 | `test_the_age_rule_never_exceeds_five_per_run` (cleanup) | 8 old items: 5 planned, outcome `cap`, the `run it again` verdict; the confirmed run issues calls for those 5 only; and 5 old eligible, 1 old tracked, 3 young: 5 planned, outcome `exhausted`, no `run it again` | the age rule ignores `CAP` in the loop | C4 |
| C5 | `test_the_age_value_changes_the_plan` (cleanup) | the same report and mode, the key at 10, 30 and 31 days: the item lists differ where the ages differ, and so do the plan digests | the day count passed to `aged` by `select` is `min(N, 30)` | C5 |
| C6 | `test_age_and_count_rules_together` (cleanup) | count reached plus age: the count rule plans the front item, the age rule continues past young items; an old item with tracked files is skipped with the existing reason and the outcome is `exhausted` | the skip of an ineligible item is dropped for the age rule (it is planned) | C4, C6, C7 |
| C7 | `test_the_preview_with_an_age_only_policy` (cleanup) | `cli.main` with an adopted age-only `cleanup` policy in the existing scratch repository, whose report has old eligible items (at most 5), one old item with tracked files and young items: exit 0, the lines of section 2.4 including the whole `exhausted` verdict (`finished older than N days still reached; no further item is eligible (skipped: ...); running it again will not help`), `tree_hash` equal before and after (nothing written), no script verb but `report` | the age key's `left` in `preview_lines` is always empty (the verdict never says it is still reached) | C4, C7 |
| C8 | `test_a_sentence_for_an_older_plan_is_refused_after_an_item_ages` (cleanup) | the preview's sentence, then a report whose `generated_at` is one second later and adds an old item that the plan now selects (so the `[id, action]` pairs change): `--confirm` refused, exit 2, nothing written | `aged` floors `generated_at` to midnight | A1, C8 |

A mutation to `LOWERED` (the key removed) is not in the table because its set is
every age plan test that expects an age plan and nothing existing: C1 and C3 to
C8 (C2 passes: it expects nothing planned, and its count-rule comparison does not
touch the key); it is checked once, in flow 9, with that set.

The absent-key golden (an in-repository test per touched module is the existing
suite; the before/after proof is flow 5): a scratch driver renders, at the base
tree and at the candidate tree, `describe`, `block`, `retention_alert.render`
and `retention_cleanup.preview_lines` for three policies without the key (items
and MiB; archives and prunable; all four) over three reports (the fixture, the
fixture incomplete, an empty `finished`); the two outputs are byte-identical.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The policy key and the alert line | - | 2 | 1 |
| CP2 | The cleanup plan and the page | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the policy key and the alert line

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/retention_alert.py`, `tests/test_retention_policy.py`, `tests/test_retention_alert.py`.

First add row 43 after row 42 of docs/ROADMAP.md in the style of the rows above
it (Current; Done at acceptance), then sections 2.1 to 2.3, tests T1 to T3 and A1
to A6, and their mutations. `python3 tests/run_all.py --select
test_retention_policy.py --select test_retention_alert.py --select
test_retention_status.py` (run `python3 tests/run_all.py --list` first if the
release cache may lack a version). docs/ROADMAP.md and docs/ACTIVE_MILESTONE.md
are excluded at both stages, not deliverables. The helper `aged` lands here, so
CP2 only calls it.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the cleanup plan and the page

**Files:** `src/workflow_manager/retention_cleanup.py`, `tests/test_retention_cleanup.py`, `docs/retention.md`.

Section 2.4 and 2.5, tests C1 to C8 and their mutations, the absent-key golden
(flow 5), `python3 tools/check_docs.py`, then `python3 tests/run_all.py
--select test_retention_cleanup.py --select test_retention_run.py --select
test_retention_status.py --select test_docs.py`, and `git diff --exit-code
8ff4f435d8890d906dd167eac711434eaf751f03 -- tools .claude scripts
.workflow-manager tests/parallel src/workflow_manager/cli.py
src/workflow_manager/retention.py src/workflow_manager/retention_run.py`
(no output). The full `python3 tests/run_all.py` runs at the implementation
review and at acceptance, never while a file is being written. After the
acceptance and merge, the `docs:` release-history row (1.19.0) is a separate
pull request. Comments on #215 record what was done; it closes at acceptance;
the Controller-owned JSON alert output stays a separate later item (it will read
`aged`'s counts).
<!-- /CP2 -->

## 5. The declaration

`docs/ai-workflow/registry/retention-max-age-artifacts.json` must classify every
file path a checkpoint's `Files` paragraph or this section names, at both stages, and protect every deliverable. The seven
deliverables (`src/workflow_manager/retention_policy.py`,
`src/workflow_manager/retention_alert.py`,
`src/workflow_manager/retention_cleanup.py`, `tests/test_retention_policy.py`,
`tests/test_retention_alert.py`, `tests/test_retention_cleanup.py`,
`docs/retention.md`) are excluded at the plan stage and protected at the
implementation stage. Paths named only as evidence or as byte-identical
comparisons (`src/workflow_manager/cli.py`, `src/workflow_manager/retention.py`,
`src/workflow_manager/retention_run.py`, `tools/check_docs.py`,
`tests/parallel/resources.json`, `tests/test_retention_status.py`,
`tests/test_retention_run.py`, `tests/test_docs.py`, `tests/fixtures/retention_report.json`,
`scripts/workflow_retention.py`, `docs/exit-codes.md`, `docs/verify.md`,
`docs/RELEASING.md`) get "named in the plan, not a deliverable" entries at both
stages, protected at the implementation stage where they must stay
byte-identical. `docs/ROADMAP.md` and `docs/ACTIVE_MILESTONE.md` stay excluded at
both, and are not declared as deliverables. `tests/parallel/resources.json` is
not edited. `tests/run_all.py` and `tools/release/release.py` are named only as
commands that are run, never read or compared as files, so they need no entry;
the coverage check examines the checkpoints' `Files` paragraphs only. SELF_REVIEWING_PLAN edits the generated template before the first
publish and checks every path above at both stages.

## 6. Functional review

Offline greps and diffs in a checkout of the candidate; `BASE` is
`8ff4f435d8890d906dd167eac711434eaf751f03`. Exit codes are read with `; echo $?`,
not through a pipe; greps exclude `docs/ai-workflow` and `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only the three source files, the three test files, `docs/retention.md` and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py src/workflow_manager/retention.py src/workflow_manager/retention_run.py docs/exit-codes.md docs/verify.md README.md docs/README.md; echo $?` | no output, `0` |
| 3 | `grep -n 'finished_max_age_days' src/workflow_manager/retention_policy.py` and `grep -n '^SCHEMA_VERSION' src/workflow_manager/retention_policy.py` | the entry with maximum 3650 and `SCHEMA_VERSION = 1` |
| 4 | `grep -n -e 'older Manager' -e 'finished_max_age_days' docs/retention.md` | the table row and the sentence that an older Manager refuses the file and falls back to `off`, with `schema_version` staying 1 |
| 5 | extract the base `src` with `git archive BASE src \| tar -x -C $TMPDIR/base`, run the scratch driver of section 3 once with `PYTHONPATH=$TMPDIR/base/src` and once with the candidate's `src`, `diff` the two outputs | no difference (existing outputs byte-identical when the key is absent) |
| 6 | the same driver with a policy that sets the key, candidate only | the alert line, `thresholds reached`, `after this run` and `age not known` lines of sections 2.3 and 2.4; a young and an unknown-age item are never in the plan; at most 5 items |
| 7 | `grep -n -E '^. 43 ' docs/ROADMAP.md` and `grep -c -E '^. 44 ' docs/ROADMAP.md` | row 43 present, last cell `Current`; `0` |
| 8 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 9 | in a scratch copy apply the mutations of T1, A1, A5, C3 and C5 of section 3, and the `LOWERED` one, with `sed`, then `python3 tests/run_all.py --select` the retention test files | each fails exactly the complete set the table states for it (T1: T1; A1: A1 and C8; A5: A5; C3: C3; C5: C5), existing tests included; the unmutated checkout passes; and with the key removed from `LOWERED`, exactly C1 and C3 to C8 fail |
| 10 | `python3 tools/release/release.py check-title "feat: add an age threshold to the retention policy"; echo $?` | `valid title: feat, release impact minor`, `0` |

## 7. Risks

* The report's `generated_at` is the script's own clock; a skewed machine
  clock shifts every age equally and never makes an unknown item old.
* An older Manager refuses a policy carrying the key and runs in `off`: stated
  on the page; nothing is cleaned or sent by it in the meantime.
* The age rule can plan several items for one adopted policy as time passes;
  every plan is still shown first, still needs its own sentence, and still
  stops at 5 per run and at the 3-newest floor.

## 8. Open decisions

* **Revision 2 (local plan review round 1, PLR1-001 to -006, all accepted):**
  the mutation table states each mutation's complete failure set (the old C5
  and T2/T3/C7/A2 rows were checked against `8ff4f43`'s tests and did not
  hold); the age key's reached test is "one old item" in the cleanup too; `cap`
  counts only eligible work; the `kept_recent` exclusion lives in `aged`; the
  two count-only sentences of `docs/retention.md` are amended; the age line's
  label is special-cased.
* **Revision 3 (local plan review round 2, PLR2-001 to -003, all accepted):**
  every row of the mutation table was re-derived by walking each named test's
  scenario through the mutated `select`/`aged`/`preview_lines`: C1, C6, C7 and the
  `LOWERED` note gained the tests they also fail (A6 gained A5, which asserts the
  incomplete-report lines); the design rules now fix what keeps each set exact
  (A1's `generated_at` off midnight, only A4 without a review folder, who may read
  `describe`, who asserts the whole verdict line); flow 9 checks the `LOWERED`
  set.
* **Revision 4 (manual external plan review round 1, I1, I2 and the Optional
  finding, all accepted):** C7's scenario now includes an old tracked item so the
  preview ends `exhausted` and uses `left`, the fixture restriction allows an old
  ineligible item in C7 too, and the failure sets of C6 and C7 follow (C6's
  mutation also fails C7; C7's stays C4, C7); the digest claim is narrowed to age
  changes that alter the selected items or actions (verified against
  `plan_digest`, which hashes no time); section 5's coverage claim is narrowed to
  the checkpoints' `Files` paragraphs and the evidence paths listed.
* **Decided here, for the owner to veto:** "older than N days" is elapsed
  seconds strictly greater than N x 86400 against the report's `generated_at`
  (not floor-of-days, which would call 5.5 days "not older than 5"); `schema_version`
  stays 1; an unknown age is never old.
