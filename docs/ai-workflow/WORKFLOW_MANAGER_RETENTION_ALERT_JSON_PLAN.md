# Workflow Manager: A Machine-Readable Retention Alert For The Controller (Revision 3)

`work_item_id: retention-alert-json` -- `governing_workflow_version: "2.2"`

**Deliverable:** `workflow-manager doctor --retention TARGET --json`: one JSON
document on stdout, the read-only machine form of the retention alert, in a
documented, byte-stable shape the Controller can consume (a stable `alert_key`
per repository, rule and state; an explicit not-evaluated case; the current facts
the Controller compares to observe archived and deleted changes, with their causes
stated as uncertain). Issue #220.
Roadmap row 45 (added by this item, Current now, Done at acceptance). **Work item
type:** `process`. **Base commit:** `84e6e3f` (`84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74`,
tip of `main`; Manager 1.19.1, Workflow 2.29.3 installed, automatic gates).
**Branch:** `milestone/retention-alert-json`. **Release:** a new output form of a
released command: the pull request title is `feat: a machine-readable retention
alert, doctor --retention --json` (`python3 tools/release/release.py check-title`
says `feat, release impact minor`: Manager 1.20.0, `docs/RELEASING.md`); the
release-history row goes in a `docs:` pull request afterwards. **Size:** two
checkpoints (the release is the pull request title, not a checkpoint), one
mechanism (*the alert as one JSON document*): CP1 code and tests, CP2 the pages
and the pins on them. Estimated 150 lines of source, 300 of tests, 120 of docs:
under the ~350-line plan limit, no split. Out of scope: the notification sender
and any scheduling (Controller lane), the engine script, `prune`, the cleanup, a
new write path, a record of past cleanup runs.

## 1. Investigation (done at `84e6e3f`)

| Point | Class | Evidence | Consequence |
| --- | --- | --- | --- |
| 1. What the report shows per finished item | KEEP (the input) | `retention._validate` (`retention.py:240-279`): per `finished[]` entry `work_item_id`, `review_folder{present, tracked_files, bytes}`, `archive{present, readable}`; plus `kept_recent`, `removing`, `totals{finished, finished_folder_bytes, archives, prunable}`, `ttl_days`, `generated_at` and per-entry `last_transition` (the age rule). No archive size, no archive age, no event or run history. | the JSON is built from these fields only |
| 2. Is `archived` derivable from the report alone? | TRUE: NOT PROVABLE | an entry with `archive.present` and no review folder reads "archived and removed", but an item archived by hand last year, one archived by `retention-cleanup` yesterday and one archived at the start of this repository's life read identically; the report carries no timestamp for an archive. A transition is a difference between two observations, and there is one. Nor is the set stable under unrelated changes: `finished` is the entries outside the three most recent (`workflow_retention.py:457-463`), so a new completion moves an item into `finished`, and an item whose family opens drops out, with every archive unchanged. | never emit `archived` as a `state`; report the current set (`snapshot.archived_and_removed`) as an observed fact, not as evidence of a transition |
| 3. Is `deleted` derivable? | TRUE: NOT PROVABLE | a deleted review folder with its archive pruned leaves an entry with neither (`archive.present` false, folder not present): identical to an item that never had a review folder. `totals.archives` is the store's count and falls when `prune` runs, but a lowered count says nothing about which item left, and an id leaving `archived_and_removed` can equally be an item that stopped being eligible (its family opened) with its archive intact. | never emit `deleted`; the Controller sees an id leave `archived_and_removed`, or `archive_store` fall, between two observations, and treats each as an observed change of uncertain cause |
| 4. A record of the last cleanup run | REJECTED | `retention_run.py` writes nothing durable by design (no write path is added: out of scope), the Manager is stateless (`docs/retention.md`), and a Manager-kept history would be a second source of truth that a hand-run `archive`/`prune` bypasses. | the Controller keeps the previous snapshot; the Manager reports current counts only |
| 5. The alert's gate and its not-evaluated causes | KEEP (reuse) | `retention_alert.alert_lines` (`retention_alert.py:269-296`; `render` starts at 231): policy read locally first, nothing started unless `alerting(state)`; script state, `fetch` refusal, one exception boundary; `render` turns "no rule reached and some unknown" into the incomplete not-evaluated line. | the JSON shares one assessment with the text (section 2.8) so the two can never disagree; the text stays byte-identical (golden) |
| 6. `doctor` exit codes | KEEP | `cmd_doctor` (`cli.py:862-892`): refusals before any evaluation exit 2 (not managed, unparseable record, cache or temporary directory inside the repository); the findings exit 1; the alert never changes a code. | `--json` keeps every pre-evaluation refusal and its message; once the document is printed the exit is 0 (section 2.7) |
| 7. The three rules and two more | KEEP | `retention_policy.THRESHOLDS` has five keys: `finished_items`, `finished_folder_mib`, `archives`, `prunable_archives`, `finished_max_age_days`. The text alert evaluates all five. | the JSON lists every threshold the policy sets, so it is never weaker than the text; the Controller filters by `rule` |

## 2. Design

### 2.1 The document

`retention_alert_json.document(target, version, script_state, outcome=None)`
returns a dict and `render(doc)` returns `json.dumps(doc, indent=2) + "\n"`
(`ensure_ascii` default, insertion order fixed by construction, never sorted
dynamically): the same inputs give the same bytes.

```text
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "/abs/resolved/path",
  "policy": {"state": "adopted", "mode": "notify", "digest": "<64 hex>"},
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [ { "rule": "finished_items", "threshold": 10, "threshold_unit": "items",
      "current_value": 12, "value_unit": "items", "lower_bound": false,
      "unknown_age": null, "reached": true, "state": "reached",
      "alert_key": "retention:/abs/resolved/path:finished_items:reached:12",
      "next": "in the repository, run ..." } ],
  "snapshot": { "finished": 14, "with_review_folder": 12, "archived_and_removed": ["a", "b"],
      "finished_folder_bytes": 641728512, "archive_store": 3, "prunable_archives": 0,
      "interrupted_removals": [] }
}
```

`kind` is `retention_alert` (underscore: the existing page test forbids the hyphenated spelling on a page). Every key is always present (a value is `null` when it does not apply), so a
consumer never tests for a missing key.

### 2.2 `evaluation`: the three answers, and never a false all-clear

| `evaluation` | When | `alerts` | `snapshot` | `not_evaluated` |
| --- | --- | --- | --- | --- |
| `not_applicable` | the policy is absent, `file-missing`, `invalid`, `not-adopted`, `record-invalid`, `changed`, or adopted with mode `off` or `cleanup`: the text alert prints nothing and starts nothing; so does the JSON | `[]` | `null` | `null` |
| `not_evaluated` | the text alert's `retention alert: not evaluated: CAUSE` cases: no release in the record, installed release cannot be checked, script not the release's, script missing or refusing, report malformed or timed out, any exception, or an incomplete report with no rule reached | `[]`, except the incomplete case (below) | `null`, except the incomplete case | `{"cause": "...", "next": "..."}`: the text's cause and step, verbatim |
| `evaluated` | the report was had and at least one rule is reached, or every rule is clear | one per threshold the policy sets, in `THRESHOLDS` order | the current facts | `null` |

An incomplete report with no rule reached is `not_evaluated` with the incomplete
cause (as the text), and still carries `alerts` (every state `unknown`) and the
`snapshot`, whose numbers are lower bounds, because the report exists. `policy`
is always present: `state` is the policy state's name, `mode` the mode in force
(`off` unless adopted), `digest` the 64-hex digest for an adopted policy else
`null`. `report_complete` is `null` when no report was had, else the report's
completeness as `retention_alert.incomplete` judges it (inverted). `evaluated`
with `reached` false everywhere is a true all-clear; `not_applicable` and
`not_evaluated` are never one.

### 2.3 `state`, and the archived and deleted transitions (decided, with evidence)

`state` is one of `reached`, `clear`, `unknown` (a lower bound below its limit:
the text's `not known`). **There is no `archived` and no `deleted` state**
(points 2 to 4): the report proves current facts, not transitions, so the
Manager never invents one, and the page does not present a difference between two
snapshots as one. `snapshot.archived_and_removed` is the sorted ids of the
`finished` entries whose archive is present and readable and whose review folder
is not present: a fact of this moment, and membership of `finished` itself moves
with no filesystem change (a newer completion pushes an item out of the three
most recent and into `finished`; an item whose family opens leaves it). The page
therefore tells a Controller that compares two **complete** documents
(`report_complete: true` on both; an incomplete one holds lower bounds and a
missing observation never establishes that anything left) to report:
an id **entering** `archived_and_removed` as "observed archived and without a
review folder", cause uncertain (archived and removed since the last look, or newly
eligible with an archive already there); an id **leaving** it, or a fall of
`archive_store`, as "no longer observed", cause uncertain (archive deleted or
moved, or no longer eligible, or its folder present again); an id leaving while
`archive_store` falls is stronger evidence of a pruned archive, still not proof.
`snapshot.finished_folder_bytes` and `with_review_folder` fall when folders are
removed, with the same caveat. `interrupted_removals` is the report's `removing`
list (`null` for a Workflow release that does not report it).

### 2.4 `alert_key`

`retention:{repo}:{rule}:{state}` and, for `reached` only, `:{bucket}`, where
`repo` is the resolved absolute path of the target (`Path(target).resolve()`,
the repository's identity here; the page says a moved repository is a new
identity) and `bucket` is the printed number: items for the count and age
rules, whole MiB rounded down for the folder rule (the text's rounding), archives
and prunable archives for theirs, with a `+` suffix when `lower_bound`. So one
event per key, and a new key (a repeat) exactly when the printed value changes (the printed
value includes the `+`: `:12` to `:12+` is a new key, and a byte change inside the
same MiB is not; the page and K1 say so). `clear` and `unknown` keys carry no value, so a rule that stays clear
never produces a new key. The key is an opaque identity string: the repository
path may contain `:`, and a consumer compares keys whole and never parses one
(the page says so).

### 2.5 The rules onto the fields

| `rule` | `threshold` / `threshold_unit` | `current_value` / `value_unit` | `reached` when | Text line it mirrors |
| --- | --- | --- | --- | --- |
| `finished_items` | the policy's number / `items` | finished entries with a review folder / `items` | value at or above the number | `finished items: N, limit L` |
| `finished_folder_mib` | MiB / `MiB` | `finished_folder_bytes` rounded down to MiB / `MiB` | at or above (compared in bytes, as the text) | `finished folders: N MiB` |
| `archives` | number / `archives` | `totals.archives` / `archives` | at or above | `archives: N` |
| `prunable_archives` | number / `archives` | `totals.prunable` / `archives` | at or above | `prunable archives: N` |
| `finished_max_age_days` | days / `days` | count of old items (`retention_alert.aged`) / `items` | one old item or more | `finished older than N days: K items` |

For the age rule `unknown_age` is the count of examined items with no usable age
(the text's `K more with no usable last transition (not counted)`); it is `null`
for every other rule. `lower_bound` is the text's `at least`. `next` is the text's
step for a reached rule (`retention_alert._step`), else `null`. On an incomplete
report the text's `next:` line also appends `retention.STEP_INCOMPLETE`; the
document does not carry that step. The page says a consumer reads
`report_complete: false` as "fix what the alerts name, then run again". `next` names the target as the caller typed it (the text's
`shlex.quote(str(target))`), so its bytes follow the spelling of the target;
`repo` and `alert_key` are the identity (the page says so). A rule the policy
does not set is absent from `alerts`.

### 2.6 One assessment, two renderings

`retention_alert.assess(target, script_state, outcome)` holds what `alert_lines`
decides today (the policy gate, the script check, the fetch, `evaluate`, one
exception boundary) and returns an `Assessment` (policy state, not-evaluated
`(cause, step)` or `None`, results, report). `alert_lines` becomes: assess; the
not-evaluated lines, or `[]` for an unalerting policy, or `render` inside its own
boundary (an exception there is the same `not evaluated: TypeName` line). The
text is byte-identical (golden). `retention_alert_json.document` is the second
renderer of the same assessment; its own boundary turns an exception into
`not_evaluated` with the type name and `retention.STEP_RUN_DIRECTLY`.

### 2.7 The command and its exit codes

`doctor` gains `--json` (valid only with `--retention`; without it the parser
refuses, exit 2). With it `cmd_doctor` reads the record and refuses as today (not
managed, unparseable record -- a `null` or non-version `workflow_version` exits 2
through `_refuse_unparseable_record`, empty stdout, `docs/exit-codes.md` row 24,
so the document's "no release" cause is reachable only through `document()` --, a
cache or temporary directory inside the repository: exit 2, message on stderr,
nothing on stdout; `main` prints `MANAGER_ROOT_DEPRECATION` to stderr before dispatch, so a
`--manager-root` run writes that line and then the one `error:` line), in this order: the
release-option refusal, then not managed, then the unparseable record, then the
cache or temporary directory check; then **skips the compatibility report** (it resolves the
target release, can need the network and is no part of the alert) and evaluates
and prints exactly the document on stdout: no other line.

**The release options under `--json`.** `--release-version`, `--release-dir` and
`--manager-root` choose a target release, and nothing under `--json` uses one, so
they are **refused**: exit 2, one `error:` line on stderr naming the option and
`--json`, nothing on stdout, before any evaluation (and before any cache or
discovery access). The document's bytes therefore cannot depend on them.
Read-only destinations are planned for the installed release only
(`plan_destinations(args, os.environ, args.target, [installed])` directly:
`_readonly_destinations` is not reused, since it resolves `_default_version`,
which can run discovery and need the network for a version never used).

**The script is started only after the gate.** Today `cmd_doctor` runs
`retention.fetch(args.target)` unconditionally for `--retention`. Under `--json`
that line is not used: the document passes `outcome=None` and the report is
fetched only inside `retention_alert.assess`, after the policy gate, so no
`not_applicable` policy (absent, `off`, `cleanup`, `changed`, ...) ever starts
the script through the real command (J5, mutation M10).

Exit **0 whenever the document is printed**, whatever it says; the `doctor`
findings exit 1 does not apply because no finding is computed (documented). Text
output without `--json` is byte-identical, the `--retention` section included. It
writes nothing in the repository (the existing `tree_hash` proofs, plus a new one).

## 3. Tests, failure-only mutations and goldens

New file `tests/test_retention_alert_json.py` (helpers of `test_retention_alert`
and `test_retention_status`: the stub script, `Base`, `rs.report`, `rs.finished`,
`aged_entry`). Scratch copies under `$TMPDIR` (`command cp -rf`, `command rm -f`),
never the repository. The unmutated copy passes every test of the touched files;
the sets below are claims the implementer **measures** in a scratch copy and
records in the implementation summary; a difference is repaired by changing the
test or this table (through an amendment), never by weakening a claim.

**Surfaces.** J1 to J5, J7 and J8, and every J6 cause except "no release", read
the **stdout of the real command** (`cli.main` on `doctor TARGET --retention
--json`, with the stub script), so they see everything the command prints and
whether it starts the script. The "no release" cause is tested through
`retention_alert_json.document()` only, because the command refuses a record
without a release at exit 2 before any document (section 2.7); X1 pins that
refusal. A further test (D0) asserts `document()` rendered equals the command's
stdout for J1.

Golden: one test holds the **complete expected document, byte for byte** (a
literal), for each of: J1 reached (all five rules set, count and size and age
reached with an unknown-age item, two within); J2 all clear; J3 an incomplete
report with one rule reached and one `unknown`; J4 an incomplete report, nothing
reached (`not_evaluated`, `alerts` all `unknown`, snapshot present); J5
`not_applicable` for each of absent policy, mode `off`, mode `cleanup`, a
`changed` policy (through the command, the script is never started: the stub's
marker file stays absent); J6 each not-evaluated cause (no script, refusing script, malformed
report, modified script, no release, unchecked release, a `script_state` or report
that makes `assess` raise (cause the type name, `next` `retention.STEP_RUN_DIRECTLY`),
and a raise inside `document()`'s own rendering boundary); J7 prior-and-current
pairs showing the observed facts (an id enters `archived_and_removed`; an id
leaves it and `archive_store` falls) and the negative cases that must not read as
proof: an item leaves the three most recent with its archive unchanged (enters the
set), an item becomes ineligible because its family opens (leaves it,
`archive_store` unchanged), and an incomplete observation (lower bounds; nothing
derived from a missing id). The page text and the test both name each as
cause-uncertain; J8 long ids and
`interrupted_removals` present, empty and `null`. Text golden: `verify` and `doctor`
(with and without `--retention`) for the same scenarios are byte-identical between
`84e6e3f` and the candidate (flow 5).

| Test | Scenario | Mutation | Fails (to measure) |
| --- | --- | --- | --- |
| J1 to J8 | the goldens above, each a whole-document literal | M1: a top-level key (`kind`) renamed, reordered or dropped | all of J1 to J8 (a mutation of an alert-entry key fails only the goldens with a non-empty `alerts`) |
| K1 key per state | `alert_key` for reached (with bucket and `+`), clear and unknown; the same value twice gives the same key, a changed value a new one, a clear rule one key whatever the value, the folder bucket is whole MiB | M2: the bucket dropped from a reached key; M3: a bucket added to a clear key | K1, J1, J3 (M2); K1, J2 (M3) |
| E1 not a false all-clear | every not-evaluated and not-applicable case has no alert entry with `reached: true` and `evaluation` not `evaluated`; no case with an unreadable report has `evaluation: evaluated` | M4: `evaluation` fixed to `evaluated` | E1, J4, J5, J6 |
| X1 exit codes | exit 0 for every document; exit 2, empty stdout, same stderr as the text command for not managed, an unparseable record, a `null` `workflow_version` record, a cache inside the repository; `--release-version X` (also a malformed one), `--release-dir DIR` and `--manager-root DIR` with `--json` exit 2 with the one `error:` line and empty stdout, and no cache or discovery access; `--json` without `--retention` exits 2; `doctor` text exit codes unchanged, including one fixture (a drifted managed file) where the text `doctor` exits 1 and `--json` exits 0; the `--manager-root` case asserts the deprecation line plus the one `error:` line, and one case has both a release option and an unmanaged target (the release-option refusal wins) | M5: exit code taken from the compatibility report (caught by the drifted fixture) | X1 |
| W1 no write | `tree_hash` of the target and of this repository equal before and after, for evaluated, not-evaluated and not-applicable; no second line on stdout | M6: a `print` of the text block after the document | W1, J1 to J5, J7, J8 and J6 (command-level causes), D0; not the function-level J6 "no release" case |
| S1 shared assessment | the cause and step of each text `not evaluated` line equal `not_evaluated.cause` and `.next` of the document for the same state, across every J6 case, including the two raise causes | M7: the document builds its own cause | S1, J6 |
| P1 gate before fetch | through the command, every `not_applicable` policy leaves the stub's marker file absent; an evaluated policy creates it once | M10: `cmd_doctor` fetches unconditionally under `--json` | P1, J5 |
| T1 text unchanged | the existing `test_retention_alert.py` (all of it) passes; the new golden compares to literals captured at the base | M8: `alert_lines` renders the not-evaluated line differently | the existing text tests, T1 |
| D1 pages | `docs/retention.md` and `docs/exit-codes.md` carry the shape (every key name of section 2.1, the three `evaluation` values, the three `state` values, the key rule (exactly when the printed value changes; opaque, never parsed), the `report_complete: false` reading, `next` as the target was typed and `repo`/`alert_key` as the identity, the observed-not-proven reading of `snapshot` changes with the uncertain causes of section 2.3, the refusal of the release options, the sentence that `archived` and `deleted` are not emitted and why, the exit rule) | M9: a key deleted from the page | D1 |

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The assessment, the JSON document, the flag, and the tests | - | 2 | 1 |
| CP2 | The pages, the roadmap pin and the page tests | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the assessment, the JSON document, the flag, and the tests

**Files:** `src/workflow_manager/retention_alert.py`, `src/workflow_manager/retention_alert_json.py`, `src/workflow_manager/cli.py`, `tests/test_retention_alert_json.py`.

Sections 2.1 to 2.7 and tests J1 to J8, D0, K1, E1, X1, W1, S1, P1, T1 with their
mutations. The new module is imported by `cli.py`; the `doctor` parser line gains
`--json` and a help sentence; the `doctor` description says the exit rule. The
text paths are not edited except `alert_lines` (section 2.6). `python3
tests/run_all.py --select test_retention_alert_json.py --select
test_retention_alert.py --select test_retention_status.py --select
test_retention_cleanup.py --select test_doctor_cli.py --select test_docs.py --select test_operator_ux_docs.py` (run `python3 tests/run_all.py
--list` first if the release cache may lack a version), then `git diff
--exit-code 84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74 -- tools .claude scripts
.workflow-manager tests/parallel src/workflow_manager/retention.py
src/workflow_manager/retention_policy.py src/workflow_manager/retention_cleanup.py
src/workflow_manager/retention_run.py` (no output). The full `python3
tests/run_all.py` runs at the implementation review and at acceptance, never
while a file is being written.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the pages, the roadmap pin and the page tests

**Files:** `docs/retention.md`, `docs/exit-codes.md`, `tests/test_retention_alert_json.py`.

Row 45 of docs/ROADMAP.md is already added (at planning, `Current`; Done at
acceptance): do not add it again. `docs/retention.md` gets a section
"The retention alert as JSON" after "The retention alert": the command, the
document with one complete example, the key table, the `evaluation` and `state`
tables, the `alert_key` rule, the transition decision (what each state means,
that `archived` and `deleted` are not emitted, how a Controller compares two complete
snapshots and reports each difference as an observed change of uncertain cause,
section 2.3), the not-evaluated causes, and the exit rule; the "Exit status"
section gains one sentence. `docs/exit-codes.md` gains one row for `doctor
--retention --json` (0 whenever the document is printed; 2 for the refusals
before it; the findings exit 1 is not computed). The pages' `Last checked with`
stamps are not moved. The page tests D1 join `tests/test_retention_alert_json.py`.
`python3 tools/check_docs.py` must pass. docs/ROADMAP.md and
docs/ACTIVE_MILESTONE.md are excluded at both stages, not deliverables. Comments
on #220 record what was done and the exact shape (the Controller lane is told by
the orchestrator); it closes at acceptance.
<!-- /CP2 -->

## 5. The declaration

`docs/ai-workflow/registry/retention-alert-json-artifacts.json` must classify
every file path the checkpoints' `Files` paragraphs name, at both stages, and
protect every deliverable. The deliverables (`src/workflow_manager/retention_alert.py`,
`src/workflow_manager/retention_alert_json.py`, `src/workflow_manager/cli.py`,
`tests/test_retention_alert_json.py`, `docs/retention.md`, `docs/exit-codes.md`)
are excluded at the plan stage and protected at the implementation stage. Paths
named only as byte-identical comparisons (`src/workflow_manager/retention.py`,
`src/workflow_manager/retention_policy.py`, `src/workflow_manager/retention_cleanup.py`,
`src/workflow_manager/retention_run.py`, `tools/check_docs.py`,
`tests/parallel/resources.json`, `scripts/workflow_retention.py`) get "named in
the plan, not a deliverable" entries at both stages, protected at the
implementation stage; the run-only tests (`tests/test_retention_alert.py`,
`tests/test_retention_status.py`, `tests/test_retention_cleanup.py`,
`tests/test_doctor_cli.py`, and `tests/test_docs.py` and
`tests/test_operator_ux_docs.py`, named in CP1's `--select` list) are excluded at
both stages, each with an entry in the declaration. `docs/ROADMAP.md` and
`docs/ACTIVE_MILESTONE.md` stay excluded at both stages and are not declared as
deliverables. `tests/parallel/resources.json` is not edited (it names test files, but the new
test file needs no entry there). SELF_REVIEWING_PLAN edits the generated template before the first
publish and checks every path above at both stages.

## 6. Functional review

Offline greps and diffs in a checkout of the candidate; `BASE` is
`84e6e3fb4edf7b01e0c4cbbb30f4f7b89935fb74`. Exit codes are read with `; echo $?`,
not through a pipe; greps exclude `docs/ai-workflow` and `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only `retention_alert.py`, `retention_alert_json.py`, `cli.py`, `test_retention_alert_json.py`, `docs/retention.md`, `docs/exit-codes.md` and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/retention.py src/workflow_manager/retention_policy.py src/workflow_manager/retention_cleanup.py src/workflow_manager/retention_run.py README.md docs/README.md docs/verify.md; echo $?` | no output, `0` |
| 3 | `grep -n 'Last checked with' docs/retention.md docs/exit-codes.md` | both stamps still read `Workflow Manager 1.18.1, Workflow 2.29.3` (not moved by this item) |
| 4 | `grep -n -e 'retention_alert' -e 'schema_version' -e 'alert_key' docs/retention.md` | the new section names `retention_alert` (the `kind`), `schema_version`, `alert_key` and the three `evaluation` values |
| 5 | extract the base `src` with `git archive BASE src \| tar -x -C $TMPDIR/base`, run the scratch driver the implementer writes into the implementation summary (the text of `verify` and `doctor` with and without `--retention`, in every J scenario, on a stub script) once with `PYTHONPATH=$TMPDIR/base/src` and once with the candidate's `src`, `diff` the two outputs | no difference |
| 6 | `grep -n -E '^\| 45 ' docs/ROADMAP.md` and `grep -c -E '^\| 46 ' docs/ROADMAP.md` | row 45 present, last cell `Current`; `0` |
| 7 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 8 | in a scratch copy apply M1, M2, M4, M6, M9 and M10 of section 3, then `python3 tests/run_all.py --select` the touched test files | each fails the set the table states; the unmutated checkout passes |
| 9 | `python3 tools/release/release.py check-title "feat: a machine-readable retention alert, doctor --retention --json"; echo $?` | `valid title: feat, release impact minor`, `0` |

## 7. Risks

* The Controller expects `archived` and `deleted` states (the issue's wording):
  the plan declines to emit them and says why on the page; a Controller
  observes changes between two snapshots, as observed changes of uncertain cause. A later Manager could add a state without a
  `schema_version` change only if the page says consumers must ignore unknown
  `state` values; the page says so.
* `--json` skips the compatibility report, so a Controller that wants the
  findings still runs `doctor` without the flag.
* The `alert_key` embeds the path: a moved repository is a new identity, once.

## 8. Open decisions

* **Decided here, for the owner to veto:** `state` has three values and the
  a Controller observes changes between two complete snapshots, and the Manager
  proves no archived or deleted transition (it stays stateless and records
  nothing); all five thresholds are
  listed, not only three; `--json` replaces the text output of `doctor` and skips
  the compatibility report; exit 0 whenever the document is printed.
