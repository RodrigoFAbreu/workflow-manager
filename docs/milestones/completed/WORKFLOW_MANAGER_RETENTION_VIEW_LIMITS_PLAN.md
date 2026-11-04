# Workflow Manager: What the Retention View Says About Its Limits and Causes Is Exact, Documented and Tested (Revision 3)

`work_item_id: retention-view-limits` -- `governing_workflow_version: "2.2"`

**Deliverable:** the retention view (`status --retention`, `doctor --retention`)
counts the value it echoes in one stated way, its page says what the
`read_errors[].path` limit is and what the view prints above it and that the
zero-finished header belongs to a complete report, and its tests compare the
complete refusal and build every cause the view can return from the
code (roadmap row 29, issue
#147 items 1 to 3, issue #116 item 4's test of every cause and item 5's
leftovers, and the leftover in #116's last comment).

**Work item type:** `process`. **Base commit:** `4a98c25`
(`4a98c25b54ddcca9c63d204cfe0cc340b3e9f373`, tip of `main`, Manager 1.14.7;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/retention-view-limits`. **Scope source:** `docs/ROADMAP.md` row 29
(added by this item, Current now, Done at acceptance). One line of text in
`src/workflow_manager/retention.py` changes what is printed, so the pull
request title is `fix: ...`, a patch (**Manager 1.14.8**, checked with
`python3 tools/release/release.py check-title`). One mechanism: what the
retention view says about its limits and causes is exact, documented and
tested. Two checkpoints. One review surface: `retention.py`, its page and the
one test file that pins both.

## 1. Each item checked against main (`4a98c25`)

| Item | Still wrong on main? | Evidence | Action |
| --- | --- | --- | --- |
| (a) #147-1, `assertIn(name, got)` | Yes | `tests/test_retention_status.py` line 774; `"finished[].work_item_id"` is a substring of `"not_finished[].work_item_id contains ..."` | compare the complete refusal |
| (b) #147-3, echo count | Yes | `_shown` counts `len(repr(value))`: a 5000-character `kind` prints `(5002 characters)`, a 10**400 `schema_version` prints `(401 characters)` | count the value itself, one rule |
| (c) #147-2, `PATH_LIMIT` | Yes, by owner decision documented only | `retention.py` line 33 comment says Linux `PATH_MAX`; the page says nothing of the limits | page text; **no code change** |
| (d) #116-4, LIR-001 | Yes | `test_every_cause_the_code_can_build_is_on_the_page` builds two causes (`not_managed_note`, `no_script_note`); the other four it names are literals, and `fetch` builds seven more (the script's own refusal, exit status 2 without a refusal, any other exit status, output not UTF-8, output not one JSON object, kind, schema_version), two of which (UTF-8, JSON) are on the page in no form; 13 in all | build all thirteen causes the view can return from the code, add the two the page lacks and make its rows match the code's texts |
| (e-i) #116-5, fixture description | **Already right** | `tests/retention_recipe.py` line 73 says four merged items, three kept, the oldest finished, one open item, a tracked file, a symlinked `.removing`; the recipe run by hand yields 3 `kept_recent`, 1 `finished`, 1 `not_finished`. The wrong text ("one kept item") was in an accepted plan, not in a file the repository still pins | drop |
| (e-ii) #116-5, `chmod 000` as root | **Does not exist** | no `chmod` in the recipe or in `tests/test_retention_status.py`; the recipe's read error is a symlinked `.removing` (`symlink: not followed`), which does not depend on the user. Run by hand as euid 0 (`unshare -rm`): the same read error, 3 kept, 1 finished | drop |
| (f) #116 last comment, zero-header sentence | Yes | `docs/retention.md` line 46 says "With no finished work item, the first line reads ..." for any report; an incomplete report keeps the INCOMPLETE header | say it is a complete report |

Out of scope, stays as it is: #116 item 6 (checklist notes of an accepted
milestone); #147 beyond items 1 to 3 (there is nothing beyond them); any
Workflow (engine) change; any other message or exit code; the page's
`Last checked with:` stamp (a later docs item moves the stamps).

## 2. Decisions

* **One counting rule for the echoed value.** `_shown` keeps showing the
  `repr` cut to 40 characters, and keeps the same cut-off (a value whose
  `repr` is at most 40 characters is shown whole, byte for byte as today).
  Only the number after `...` changes: it is the length of the value itself,
  `len(value)` for a string (the two quotes the display adds are not
  counted, and an escape such as `\x1b` counts as the one character it is),
  and the length of the printed form for any other value (a number counts the
  characters it is written with, a sign included; a list or object counts its
  printed form, never its elements). The same rule serves
  `kind` and `schema_version`. Visible change: a string `kind` over the cut
  reports its characters without the quotes (`(5000 characters)` for 5000
  `x`, was `(5002 characters)`). A number is counted as before.
* **The path limit is documented, not changed** (owner decision). The page
  says the limit is 4096 characters, Linux's `PATH_MAX`, but not a strict
  bound for `read_errors[].path`, because the engine builds that path as a
  string; and that a valid report with a longer path is printed as the
  malformed-report fallback naming `read_errors[].path`, never cut, with the
  step to run the script directly. The comment next to `PATH_LIMIT` is not
  edited. A test pins what the page promises.
* **The page lists the limits it checks.** The same paragraph names every
  limit (control characters, 0 to 2**63 - 1, 256, 4096, 8192) so the 4096 is
  not a lone figure, and says what the cut value shows.
* **The zero-header sentence names its case.** "In a complete report with no
  finished work item ..." and a second sentence: an incomplete report keeps
  `retention: INCOMPLETE` as its first line whatever the count. This is what
  the code does today (pinned by the existing incomplete-report cases of
  `test_retention_status.py`).
* **Causes are built by running the code.** The view can return thirteen
  causes (twelve from `fetch` and its helpers, one from `cli.py`'s call of
  `not_managed_note`): the repository not managed, no script, Python cannot start, the
  timeout, the script's own refusal, exit status 2 without a refusal, any
  other exit status, output not UTF-8, output not one JSON object (two sites,
  one text), kind, schema_version, a malformed report, and the forge could not
  be queried. The test builds each by calling `fetch` with `_run` returning a
  chosen `(status, stdout, stderr)` (or `Popen` forced to raise or time out)
  and `_query_failed_note` with a failed-only report. One more site is out of
  the count: `section()` (`retention.py` line 471) builds `the script's report
  is malformed: {type(exc).__name__}` when `render` raises; its lead is the
  malformed report's, shared with the `_validate` cause, so a reword of that
  site alone is not what the thirteen leads guard, and it is not built here.
  Each is built with a
  sentinel in its variable part; the fixed pieces around the sentinel must be
  on the page. No process is started: `Popen` is patched for the duration of
  the call, `_stop_group` is a no-op.

## 3. Exact texts

| Place | Before | After |
| --- | --- | --- |
| `kind` of 5000 `x` | `the script's report has kind 'xxxx...39 x... (5002 characters), not 'retention-report'` | `... (5000 characters), not 'retention-report'` |
| `kind` of 50 `\x1b` | `... (202 characters)` | `... (50 characters)` |
| `schema_version` 10**400 | `... (401 characters); this workflow-manager reads 1` | same (unchanged) |
| any value whose `repr` is at most 40 characters | shown whole | same (unchanged) |
| page, zero header | "With no finished work item, the first line reads ..." | "In a complete report with no finished work item, the first line reads ...; an incomplete report keeps the `retention: INCOMPLETE` first line whatever the count." |
| page, limits | none | a subsection "Limits on the report" (section 4) |
| page, causes table | one row for a malformed report or a bad exit status; one for kind and schema_version; `the Python running workflow-manager cannot start` without a colon | one row per cause in the code's words (section 4): the malformed row split into `FIELD AND PROBLEM`, `exited with status N` and `exited with status 2 without a refusal`, the new UTF-8 and JSON rows, the kind row and the schema_version row apart, and the `cannot start: ERROR` row (with its colon) |

Every other output of the view and every exit code stay byte-identical.

## 4. The page (`docs/retention.md`)

Under "If it is not available", after the table, a subsection **Limits on the
report**: the Manager checks a report before it prints any of it; a string has
no control character; a number lies from 0 to 2**63 - 1; a work-item id or a
reason has at most 256 characters (an id the script files as `invalid_id` is
never printed and is only checked for valid text); `repository`,
`archive_dir` and each `read_errors[].path` have at most 4096; each
`read_errors[].error` at most 8192; a report that breaks a limit is the
two-line fallback, exit status unchanged. A paragraph on the path: 4096 is
`PATH_MAX`, not a strict bound for that field; a valid report with a longer
path prints `retention: not available: the script's report is malformed:
read_errors[].path is longer than 4096 characters`, with the step to run
`python3 -I scripts/workflow_retention.py report`, which shows the whole
report; the Manager does not raise the limit. A paragraph on the echo: the
fallback for a kind or schema_version it does not read shows the value cut at
40 characters then `... (N characters)`, N being the length of the value
itself, a string without the quotes the display adds, a number the characters
it is written with. The causes table of the page ("If it is not available") has one row per
cause above, in the code's own words with the variable part in capitals (the
`cannot start` row gains the colon the code prints: `the Python running
workflow-manager cannot start: ERROR`): the
current row for a malformed report or a bad exit status is split into `the
script's report is malformed: FIELD AND PROBLEM`, `the script exited with
status N (FIRST LINE OF ITS ERROR OUTPUT)`, `the script exited with status 2
without a refusal (...)`, and the two new rows `the script's output is not UTF-8
text` and `the script's output is not one JSON object` (all with the step to run
the script directly); the kind and schema_version row names `the script's
report has kind VALUE, not 'retention-report'` and `the script's report has
schema_version VALUE; this workflow-manager reads 1`. The echo paragraph says a
list or object counts its printed form. No internal milestone id is named.

## 5. Tests (`tests/test_retention_status.py`)

All through the stub engine (a stub script prints a JSON file) or direct calls
of `retention` functions: no `gh`, no network, no process left behind. Each
end-to-end case runs `status --retention` **and** `doctor --retention`, checks
the exit code equals the one without `--retention`, no traceback, the tree
unchanged (`tree_hash`, no `__pycache__`).

* **(a) Complete refusal.** In the every-field test, `assertIn(name, got)` and
  `assertIn("contains a control character", got)` become one
  `assertEqual(got, f"{name} contains a control character")`.
* **(b) Counting.** The two pins of the end-to-end test (`kind`, `5002` to
  `5000`) and the unit pin `_shown("y" * 39)` (`41` to `39`) are edited. New
  test `test_the_echo_count_is_the_values_own_length`: `_shown` of `"y" * 39`,
  `"y" * 5000` and `"\x1b" * 50` end `(39 characters)`, `(5000 characters)`
  and `(50 characters)`; `_shown(["x"] * 50)` ends `(250 characters)` (its printed
  form, not 50 elements); of `10 ** 400` and `-(10 ** 400)` end `(401 ...)` and
  `(402 ...)`; **the same rule** is proven by `_shown("1" * 100)` and
  `_shown(int("1" * 100))` both ending `(100 characters)`; a value of 40 or
  fewer printed characters is returned whole.
* **(c) The documented fallback.** New test
  `test_a_read_error_path_over_the_limit_is_the_documented_fallback`, both
  commands: a valid incomplete report whose `read_errors[].path` is 4097
  characters gives one note whose cause is `the script's report is malformed:
  read_errors[].path is longer than 4096 characters` and whose step is
  `STEP_RUN_DIRECTLY`, the path is not printed, the tree is unchanged; a path
  of 4096 prints in full and is not a note. `TestDocs` also requires on the page
  the refusal text **built from the code** (`retention._validate` over the
  fixture report with a `read_errors[].path` of `retention.PATH_LIMIT + 1`,
  the text of the `_Invalid` it raises), `PATH_MAX`, the figures 256, 4096 and
  8192, and the sentence on the counted length.
* **(d) Every cause from the code.**
  `test_every_cause_the_code_can_build_is_on_the_page` (the name is now true)
  builds all thirteen causes by running the code (section 2), each with a
  sentinel in its variable part (the `OSError` text, the stderr line, exit
  status 77, the kind or schema_version value, the missing key, the forge
  code and count). The cause is split on its sentinels; every piece that has a
  letter must be on the page (whitespace normalised). The script's own refusal
  has no fixed text: the test checks it is `CODE: message` from stderr and its
  step the script's `next step`. The UTF-8 and JSON causes are built, and the
  JSON cause from both its sites (invalid text and a non-object) with equal
  text. The thirteen cause leads must be distinct (a guard against two causes
  collapsing into one). The steps loop is unchanged.
* **(f) The zero-header sentence.** `TestDocs` requires the page to hold
  "In a complete report with no finished work item" and "an incomplete report
  keeps the `retention: INCOMPLETE` first line whatever the count".
* **Unchanged.** Every other test of the view stays unedited and green;
  `tests/retention_recipe.py` is not edited (items e-i and e-ii are dropped).

**Failure-only mutations** (a scratch clone, never this repository; each
passes on the real code and must fail as stated):

| Mutation | Must fail |
| --- | --- |
| the `finished` loop of `_validate` names `not_finished[]` for its id | the every-field test (the old `assertIn` would have passed) |
| `_shown` counts `len(text)` again | the end-to-end `kind` case, the `y * 39` pin, the new counting test |
| `_shown` counts the cut text, `len(text[:SHOWN_LIMIT])` | the counting test (every count would read 40) and the end-to-end `kind` case |
| `PATH_LIMIT` 8192 | the new fallback test and the `TestDocs` assertion on the refusal built from the code (the page says 4096) |
| `_shown` counts `len(value)` for anything with a length | the list case of the counting test |
| the cause `cannot start` reworded in `retention.py` | the causes test (the old literal would have passed) |
| the UTF-8, the JSON, the any-other-exit-status, the exit-2-without-a-refusal, the kind or the schema_version cause reworded in `retention.py` (one run each) | the causes test |
| `no_script_note` reworded in `retention.py` | the causes test |
| `not_managed_note` reworded in `retention.py` | the causes test |
| the timeout cause reworded in `retention.py` | the causes test |
| the malformed-report cause reworded in `retention.py` | the causes test |
| the forge cause reworded in `retention.py` | the causes test |
| the page's zero-header sentence restored to the old text | `TestDocs` |
| the page's limits subsection removed | `TestDocs` |

Evidence at implementation: `python3 tests/run_all.py --select
test_retention_status.py` green and each mutation failing the case named, then
the full gate `python3 tests/run_all.py`.

## 6. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The count, the page and the tests | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the count, the page and the tests

**Files:** `src/workflow_manager/retention.py`, `tests/test_retention_status.py`,
`docs/retention.md`.

Sections 2 to 5. `src/workflow_manager/retention.py` changes only the count in
`_shown` (and its docstring). `tests/test_retention_status.py` is the one
existing test file that pins changed text (the `5002` and `41` pins) and the
one that holds items (a) and (d); no other test pins it. `docs/retention.md`
changes in the zero-header sentence, the causes table (the rows of section 4)
and the new subsection.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 29 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: the `fix:` title releases Manager 1.14.8. Both
files stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 7. Functional review

Flows 1 to 8 run offline with `python3 -I` only, outside the repository, in a
small scratch, with no network, no `gh`, no installs, no sockets and **no**
Workflow release cache; none bootstraps a release. Flow 9 is the one flow that
needs the full environment (the runner primes the release cache before any
selection) and runs in a clone made with `git clone --no-hardlinks "$PWD"
$S/clone`, checked out at the candidate.

Setup: `S=$(mktemp -d "$HOME/.cache/rvl-fr.XXXXXX"); mkdir -p $S/base $S/cand
$S/t/scripts` (deleted when the flows finish);
`git archive 4a98c25b54ddcca9c63d204cfe0cc340b3e9f373 src docs | tar -x -C $S/base`;
`git archive HEAD src tests/fixtures docs | tar -x -C $S/cand` (HEAD is the
candidate). Stub `$S/t/scripts/workflow_retention.py`: `import os,sys;
sys.stdout.write(open(os.environ["R"]).read())`. Renderer `$S/run.py`:
`import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]+"/src");
from workflow_manager import retention as r;print("\n".join(r.section(Path(
sys.argv[2]),sys.argv[3])))`. Report maker `$S/mk.py`: loads
`$S/cand/tests/fixtures/retention_report.json`, sets `complete` true,
`read_errors` `[]` and `removing` `[]`, runs `exec(sys.argv[1],{"r":rep})`
against the loaded report bound to `r`, and prints JSON to `$S/r.json`. Run
every flow for both trees: `R=$S/r.json python3 -I $S/run.py $S/<base|cand>
$S/t 2.25.5`, and compare with `diff`.

Snippet `$S/causes.py` (flow 8; argument: the tree to read; it starts no process):

```python
import sys,re,subprocess;from pathlib import Path;from unittest import mock
sys.path.insert(0,sys.argv[1]+"/src")
from workflow_manager import retention as r
page=" ".join(Path(sys.argv[1]+"/docs/retention.md").read_text().split())
class Slow:
    pid=0
    def communicate(self,timeout=None): raise subprocess.TimeoutExpired("x",1)
T=Path("/t"); OK=b'{"kind":"retention-report","schema_version":1}'
def go(patch):
    with mock.patch.object(r,"_script_is_regular",return_value=True), mock.patch.object(r,"_stop_group"):
        ctx=[mock.patch.object(*k,**v) for k,v in patch.items()]
        for c in ctx: c.start()
        try: return r.fetch(T).refusal.cause
        finally:
            for c in ctx: c.stop()
def run(res): return go({(r,"_run"):{"return_value":res}})
def pop(**kw): return go({(r.subprocess,"Popen"):kw})
failed={"not_finished":[{"work_item_id":"w","reason":"query_failed:VAR"}],"finished":[],"kept_recent":[]}
cases=[(r.not_managed_note(T).cause,[]),(r.no_script_note(T).cause,[]),
 (pop(side_effect=OSError("VAR")),["VAR"]),(pop(return_value=Slow()),[]),
 (run((2,b"",b"VAR")),["VAR"]),(run((77,b"",b"VAR")),["77","VAR"]),
 (run((0,b"\xff",b"")),[]),(run((0,b"[]",b"")),[]),
 (run((0,b'{"kind":"VAR"}',b"")),["'VAR'"]),
 (run((0,b'{"kind":"retention-report","schema_version":"VAR"}',b"")),["'VAR'"]),
 (run((0,OK,b"")),["complete is missing"]),(r._query_failed_note(failed).cause,["VAR","1"])]
for cause,var in cases:
    pieces=[p.strip() for p in re.split("|".join(map(re.escape,var)),cause)] if var else [cause]
    print(all(p in page for p in pieces if re.search("[A-Za-z]",p)),"|",cause)
```

(The thirteenth cause, the script's own refusal, has no fixed text; the unit
test checks its shape.)

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | report with `r["kind"]="x"*5000` | candidate: `... (5000 characters), not 'retention-report'`; base: `(5002 characters)`; the rest of the line identical |
| 2 | `r["kind"]="\x1b"*50` | candidate `(50 characters)`, base `(202 characters)`; no raw ESC byte in either output |
| 3 | `r["schema_version"]=10**400`, then `r["kind"]="x"*38` | first: `(401 characters)` in both, `diff` empty; second: `kind` shown whole in both, no `characters)` marker, `diff` empty |
| 4 | complete report with `r["complete"]=False`, `r["read_errors"]=[{"path":"a"*4097,"error":"e"}]`; then the path `"a"*4096` | first: both trees print `retention: not available: the script's report is malformed: read_errors[].path is longer than 4096 characters` and the `next:` line equal to `STEP_RUN_DIRECTLY` (the backticks are printed: ``run `python3 -I scripts/workflow_retention.py report` in the repository``), `diff` empty, the long path absent; second: both print the section under the `retention: INCOMPLETE` header, with the 4096-character path in its `could not read:` line, `diff` empty |
| 5 | report with `finished[0]["work_item_id"]="a\nb"`; then `r["not_finished"]=[{"work_item_id":"a\nb","reason":"no_pull_request"}]` | both trees: `finished[].work_item_id contains a control character` for the first and `not_finished[].work_item_id contains a control character` for the second, `diff` empty |
| 6 | read `$S/cand/docs/retention.md` | it holds the two new cause rows, "In a complete report with no finished work item", "an incomplete report keeps the `retention: INCOMPLETE` first line whatever the count", `PATH_MAX`, the exact refusal text of flow 4 and the `(N characters)` explanation; the base page holds none of them |
| 7 | complete zero-finished report (`finished` `[]`, `totals.finished` 0, `finished_folder_bytes` 0); then the same with `complete` false | candidate and base: first line `retention (read-only; the Workflow script found no finished work item beyond the 3 most recent):` for the first, `retention: INCOMPLETE (read-only); the numbers below are lower bounds` for the second, `diff` empty (the page sentence describes exactly this) |
| 8 | `python3 -I $S/causes.py $S/cand`, then the same with `$S/base` | candidate: twelve lines, each `True | CAUSE`; base: `False` on at least the UTF-8 and the JSON causes (the page lacks them), so the check is not blind; no process started |
| 9 | (needs the full environment: network or a primed release cache) in the clone, `python3 tests/run_all.py --select test_retention_status.py` | exit 0 |

## 8. Risks

* The count change is visible only for a string over the cut; a value whose
  `repr` is at most 40 characters and every number are byte-identical.
* The causes test patches `subprocess.Popen` (the shared `subprocess` module's
  attribute) for the duration of each call and restores it; the fake process
  starts nothing.
* The page documents a limit the owner chose to keep; if a real report ever
  hits it, the fallback is the existing, safe behaviour.

## 9. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
