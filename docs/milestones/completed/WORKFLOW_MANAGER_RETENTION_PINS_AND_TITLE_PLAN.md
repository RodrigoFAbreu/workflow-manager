# Workflow Manager: Three Retention Test Pins And The Retention Page Title (Revision 1)

`work_item_id: retention-pins-and-title` -- `governing_workflow_version: "2.2"`

**Deliverable:** three test pins that make existing retention wording unable
to drift (the undo-warning constant, the first-per-item-call attempt of the
cannot-start case, the help's exit-1 qualifier), one decision on a historical
requirement record, and a page header for `docs/retention.md` that says what
the page covers. Roadmap row 42 (added by this item, Current now, Done at
acceptance) is this item (issues #208 and #211).

**Work item type:** `process`. **Base commit:** `72b8e56`
(`72b8e56e4824b0fc73954fe943887afd5c45c8e0`, tip of `main`; Manager 1.18.1,
Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/retention-pins-and-title`. **Release:** `test:` and `docs:` changes
release nothing (`docs/RELEASING.md`); the pull request title is `test: pin the
retention wording and widen the retention page title`, to be checked with
`python3 tools/release/release.py check-title` (release impact none). The
product code stays byte-identical: no change under `src/`, `tools/`, `.claude/`,
`scripts/`, `.workflow-manager/` or `tests/parallel/resources.json`. If a pin
cannot be written without touching `src/`, the item stops and says so. One
checkpoint, one mechanism (*existing wording is pinned, and the page header
says what the page says*), far under 300 lines: no split.

## 1. Investigation (done at `72b8e56`)

| Point | Class | Evidence |
| --- | --- | --- |
| #208.1 no test pins the literal of `UNDO_WARNING` | TRUE-FIX-NEEDED | `src/workflow_manager/retention_run.py:34` is `"warning: the undo could not remove"`; `tests/test_retention_run.py:378,394,402,410` build their stderr from `rr.UNDO_WARNING`, so rewording the constant keeps every test green while the target's own script (which prints the literal) is no longer recognised. No other file in `tests/` holds the literal |
| #208.2 the cannot-start case does not pin the first call | TRUE-FIX-NEEDED | `tests/test_retention_run.py:638-644` asserts exit 1 and the text `the script could not be started`. `_call` (`retention_run.py:119-129`) appends `(step, item_id)` to `calls` before `retention.launch_script` raises, and exit 1 is `bool(result.calls)`; nothing in the test shows which call was attempted. `self.keys()` reads the stub's marker, and the patched `launch_script` never starts the stub, so `keys()` is `[]` there by construction: the pin is the patched function's own record of the arguments it received, plus `self.keys() == []` (the script never ran) |
| #208.3 the help test lacks the qualifier | TRUE-FIX-NEEDED | `tests/test_retention_cleanup.py:853-858`'s word list has `after its first per-item call` and `or stopped before that first call` but not `even if its script could not be started`, which the help carries (`cli.py:1223`) and the page tests pin elsewhere |
| #208.4 `retention-run-mapping.json` reads `stopped after an engine call started` | KEEP | `docs/ai-workflow/requirements/retention-run-mapping.json`, requirement R3, is the requirement record of the finished item `retention-run` (last change `45c79bf`). The docs checker treats `docs/ai-workflow/` as records (`tools/check_docs.py:65`); no test reads the file (`grep -rn retention-run-mapping tests tools src` is empty) and `tests/test_retention_run.py:802,813` forbid the old phrase only in the user pages, `retention_run.py` and `cli.py`; the later record `retention-wording-pass-mapping.json` R3 carries the corrected wording. A requirement record says what was required then; rewriting it would falsify history. Nothing requires a change: KEEP, and this plan says so |
| #211 title and `For:` line cover only the report | TRUE-FIX-NEEDED | `docs/retention.md:1-3`: title `Retention report`, `For:` about counting folders; the page has `## Retention policy` (`:88`), `## The retention alert` (`:156`), `## Retention cleanup` (`:176`) |
| #211 anchors | no link breaks | the old title's anchor is `#retention-report`; `grep -rn 'retention.md#' docs README.md src tests` lists only `#retention-policy`, `#retention-cleanup`, `#the-confirmed-run`, `#the-retention-alert` (all headings that stay), and `docs/retention.md` links itself only to `#retention-cleanup`, `#the-confirmed-run`, `#the-retention-alert`. Links to the page without an anchor (`docs/README.md:15`, `docs/update.md:53`, `docs/verify.md:40`) keep working |
| #211 tests pinning the title or `For:` | none | `grep -rn 'Retention report' tests tools src` is empty; `tests/test_retention_status.py:1158-1175` pins registration and `check_docs.check_tree(...) == []`; the only grammar is `HEADER_RE` (`tools/check_docs.py:75`): `> For: <reader>. Last checked with: <versions>.` |

## 2. Design

### 2.1 The three pins (tests only)

* `TestDocsSayExitCodes`-style, in `tests/test_retention_run.py`: a test
  `test_the_undo_warning_prefix_is_the_engines_own_text` asserting
  `rr.UNDO_WARNING == "warning: the undo could not remove"` (the literal, once;
  the fixtures keep deriving from the constant, as the approved design says).
* The cannot-start case of `test_exit_codes`: `cannot_start` appends each
  non-report call's `args[:2]` to a list; after the run the test asserts
  `attempted == [("archive", "item-00")]` and `self.keys() == []`, with a
  message that says the first per-item call was attempted although the script
  never started.
* `tests/test_retention_cleanup.py`: `"even if its script could not be started"`
  joins the word list of `test_the_help_names_the_preview_the_run_the_floor_and_prune`.

### 2.2 The page header

`docs/retention.md` line 1 becomes `# Retention: the report, the policy, the
alert and the cleanup` (anchor `#retention-the-report-the-policy-the-alert-and-the-cleanup`,
which nothing links to and no heading of the page shares) and the `For:` line
reads: someone who wants to know which finished work items of a managed
repository keep review folders and which are archived, or who wants to adopt a
retention policy, read its alert, or preview and run the cleanup it allows;
`Last checked with: Workflow Manager 1.18.1, Workflow 2.29.3.` (the versions are
the installed ones, so the stamp stays true). The `Goal:` line and every other
line stay: it introduces the report's steps and is still true of them.

## 3. Failure-only mutations

Scratch copies under `$TMPDIR` (`command cp -rf` of the clone, `rm` with
`command rm -f`), never the repository. The unmutated copy passes the named
test; the mutated copy fails it, and fails nothing else of the touched files.

| # | Mutation | Failing test |
| --- | --- | --- |
| M1 | `UNDO_WARNING` reworded in the copy's `retention_run.py` (`could not delete`) | the new literal pin only; the derived-fixture tests still pass, which is the gap the pin closes |
| M2 | confined to the cannot-start path: in the copy's `_call` (`retention_run.py`), the `except OSError` branch first makes a second `retention.launch_script(Path(root), *argv_for(REMOVE, item_id, root), timeout=CALL_TIMEOUT_SECONDS)` call inside a `try`/`except OSError: pass`, then raises the same `_Stop`. `argv_for` is untouched, so the exact-argv pins and every scenario key still match; exit 1 and the text `the script could not be started` are unchanged | `test_exit_codes`, at the `attempted` assertion (named by its message), and no other test of the touched files: the cannot-start case is the only one where `launch_script` raises `OSError`, and its `attempted` is then `[("archive", "item-00"), ("remove", "item-00")]` instead of `[("archive", "item-00")]`. The earlier assertions of `test_exit_codes` (exit codes, keys, the `could not be started` text) still pass, so the mutation proves the pin and nothing else |
| M3 | the qualifier deleted from the copy's `cli.py` help | `test_the_help_names_the_preview_the_run_the_floor_and_prune` |
| M4 | the copy's `docs/retention.md` title restored to `# Retention report` | flow 3 below (a grep), not a test: no test pins the title, by decision (out of scope) |

## 4. Checkpoint

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The three pins and the page header | - | 1 | 1 |

<!-- CP1 -->
### CP1 -- the three pins and the page header

**Files:** `tests/test_retention_run.py`, `tests/test_retention_cleanup.py`, `docs/retention.md`.

First add row 42 after row 41 of docs/ROADMAP.md in the style of the rows above
it (Current; Done at acceptance), and the `KEEP` decision of #208.4 goes into
the acceptance dispositions, not into the mapping file. Then sections 2.1 and
2.2, then M1 to M3, `python3 tools/check_docs.py`, `python3 tests/run_all.py
--select test_retention_run.py --select test_retention_cleanup.py --select
test_retention_status.py --select test_docs.py` (run `python3 tests/run_all.py
--list` first if the release cache may lack a version), and
`git diff --exit-code 72b8e56e4824b0fc73954fe943887afd5c45c8e0 -- src tools .claude scripts .workflow-manager tests/parallel`
(no output). The full `python3 tests/run_all.py` runs at the implementation
review and at acceptance, never while a file is being written. docs/ROADMAP.md
and docs/ACTIVE_MILESTONE.md are excluded at both stages, not deliverables.
Comments on #208 and #211 record what was done and the KEEP; both close at
acceptance.
<!-- /CP1 -->

## 5. The declaration

`docs/ai-workflow/registry/retention-pins-and-title-artifacts.json` must
classify every path this plan names as a file to change or to compare at both
stages and protect every deliverable. Paths named only as read-only evidence or
as the unchanged-page list of flow 2 and the `--select` of CP1 (`docs/glossary.md`,
`docs/exit-codes.md`, `tests/test_docs.py`) are listed as excluded entries
("named in the plan, not a deliverable") at both stages; they stay byte-identical. SELF_REVIEWING_PLAN edits the generated template before the first
publish: the two test files and `docs/retention.md` are excluded at the plan
stage and protected at the implementation stage; `docs/ROADMAP.md` and
`docs/ACTIVE_MILESTONE.md` stay excluded at both; the source files and
`retention-run-mapping.json` named above are under prefixes the template already
excludes or are classified by an explicit entry if it leaves them open.

## 6. Functional review

Offline greps and diffs in a checkout of the candidate; `BASE` is
`72b8e56e4824b0fc73954fe943887afd5c45c8e0`. Exit codes are read with
`; echo $?`, not through a pipe.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only the two test files, `docs/retention.md` and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- src tools .claude scripts .workflow-manager tests/parallel README.md docs/README.md docs/glossary.md docs/exit-codes.md docs/verify.md docs/update.md docs/ai-workflow/requirements/retention-run-mapping.json; echo $?` | no output, `0` (the product code, the pages not re-checked and the KEEP record are byte-identical) |
| 3 | `sed -n 1,3p docs/retention.md`, then `grep -c -e '^# Retention report' docs/retention.md` | the new title and a `For:` line naming the report, the policy, the alert and the cleanup, ending `Last checked with: Workflow Manager 1.18.1, Workflow 2.29.3.`; `0` |
| 4 | `grep -rn --exclude-dir=ai-workflow --exclude-dir=milestones 'retention.md#retention-report' docs README.md src tests tools; echo $?` | no output, `1` |
| 5 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 6 | `grep -n 'UNDO_WARNING ==' tests/test_retention_run.py` and `grep -n 'attempted, \[("archive", "item-00")\]' tests/test_retention_run.py` (the assertion itself: the word `attempted` already occurs at the base in "not attempted" lines, so a bare grep would pass without the pin) and `grep -n 'even if its script could not be started' tests/test_retention_cleanup.py` | the literal pin, the recorded attempt assertion, the qualifier in the help word list |
| 7 | `grep -n -E '^. 42 ' docs/ROADMAP.md` and `grep -c -E '^. 43 ' docs/ROADMAP.md` | row 42 present, last cell `Current`; `0` |
| 8 | in a scratch copy apply M1, M2 and M3 with `sed`, then `python3 tests/run_all.py --select` the named file | each FAILED; for M2 the failure message names the `attempted` assertion (the first-per-item-call message of section 2.1), not an earlier assertion of `test_exit_codes`; the unmutated checkout passes |

## 7. Risks

* The attempt record is the patched function's, not the stub's: it pins that
  `_call` reached `launch_script` for `archive item-00`, which is the exit-1
  criterion; it does not pin the later steps, which `test_exit_codes`' other
  cases already do.
* A title with a colon makes a long anchor; nothing links to it.

## 8. Open decisions

* **For the owner, no blocker:** #208.4 is KEEP (a historical record); the
  `Goal:` line of the page keeps its report-only sentence (section 2.2).
