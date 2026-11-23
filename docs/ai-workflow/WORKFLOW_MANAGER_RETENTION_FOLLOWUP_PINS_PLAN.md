# Workflow Manager: Retention Follow-up Pins and Docs Sentences (Revision 1)

`work_item_id: retention-followup-pins` -- `governing_workflow_version: "2.2"`

Pull request title: `test: pin the retention follow-ups and say in the docs what the code prints`

**Deliverable:** make a few tests and two documentation sentences say exactly
what the code does. One mechanism: a statement (a test assertion or a docs
sentence) that is narrower or stronger than the code, brought into line with
the code. Tests and docs only: **no `src/` change and no release.**

**Work item type:** `process`. **Base commit:**
`d2be4f8aeb374c7ebe5a610d09a5e98edd5ce971` (tip of `main`; Workflow 2.29.3 is
this repository's own installation, automatic gates, default "2.2").
**Branch:** `milestone/retention-followup-pins`, bound by the Controller.
**Scope source:** issues #257, #270 and points 1 and 2 of #264 (none has a
comment) and the work-item prompt. The title is a `test:` change and its
release impact is none (`python3 tools/release/release.py check-title` reads
"valid title: test, release impact none"). **Manager only**: nothing under
`.claude/`, `scripts/`, `.workflow-manager/` or the managed documents of
`docs/ai-workflow/` is edited. **ROADMAP:** no row is added or changed; this
cleanup item needs none. Nothing in this item runs `retention-cleanup
--unattended` or any archive, remove or prune command: the tests drive scratch
repositories and a fake script only.

## 1. Verification of each point on current main

1. **#257 -- TRUE-FIX-NEEDED.** `tests/test_compatibility.py` line 1319
   asserts ``f"`workflow-manager verify {self.target}` makes that comparison"``
   with the raw target. The text under test is built at
   `src/workflow_manager/compatibility.py` line 1972
   (`manager_command("verify", ...).render()`), and the renderer
   `render_command` (line 153) is `shlex.join`, which quotes a path holding a
   space or another unsafe character. `self.target` is
   `<TemporaryDirectory>/target` (line 110), so the assertion holds only while
   `TMPDIR` has no such character; under one with a space it fails spuriously.
   Nothing in the suite exercises a quoted target here, so a renderer that
   stopped quoting would not be caught either.
2. **#270 -- TRUE-FIX-NEEDED.** `test_the_helper_with_adopting_changes_only_the_ordinary_head`
   (tests/test_retention_unattended.py line 414) ends with the `[]` check for a
   keyless file only: `self.put()` writes `GOOD`, which has no `unattended`
   key (lines 425 to 427). The code (`retention_policy.py` line 265) returns
   `[]` when `not state.policy` or the key is absent, and reads `adopting`
   only after that guard, so the behaviour is right and unpinned for a state
   with no policy file (`state.policy` is empty) and for an invalid file.
3. **#264 point 1 -- TRUE-FIX-NEEDED (docs).** `docs/retention.md` line 426
   says "Archives beyond the cap are counted as `capped`, not listed." In
   `retention_prune.py` `PrunePlan.capped` (line 54, set at line 115) is read
   by no output: not the text, not the `--json` document, not the audit file
   (a search of `src/` finds no other use). The true behaviour is that the
   plan keeps the oldest `prune_max_per_run` archives (`chosen[:cap]`), the
   rest are neither listed nor counted, and a later run selects them again
   when they are still eligible. The page's `capped` is also pinned as a
   needle (tests/test_retention_unattended.py line 639), which moves with the
   sentence.
4. **#264 point 2 -- TRUE-FIX-NEEDED (docs).** `docs/retention.md` line 434
   says "(after a stop, `N of M archives were deleted before the stop`)" as
   if every stop prints it. The code prints, for every prune stop, `retention
   prune: stopped after N of M archives; CAUSE` (`retention_prune.py` line
   308), and the deleted-count line only when at least one archive was deleted
   (`retention_unattended.py` line 439, `elif prune_result.done:`, then
   `_irreversible(..., done=False)` at line 340: `retention prune: N of M
   archives were deleted before the stop; a deleted archive cannot be undone;
   the archive store is ...`). `docs/exit-codes.md` line 33 says the closing
   `retention cleanup: stopped` line says what was done and "that closing line
   is what tells a stop apart"; a prune stop's line is `retention prune:
   stopped ...` and the cleanup line exists only for a cleanup stop.
5. **#264 point 3 -- KEEP, not taken.** The `KeyboardInterrupt` handling in the
   prune apply (`retention_prune.py` near lines 352 and 394 to 398) is a
   `src/` change; this item changes no `src/`. It stays open as #264's
   remaining point and is not edited, closed or restated here. Record it so at
   acceptance.

If a pin turns out to show a real defect, the item stops and records a finding
instead of changing `src/`.

## 2. Decisions

* **#257: render the expected command the way the product does, and add a case
  that fails in every environment.** The expected text in the existing
  assertion becomes `shlex.join(["workflow-manager", "verify", str(self.target)])`
  (the test imports `shlex`; it does not call the product's own helper). A new
  test copies the managed fixture to a directory whose name holds a space (a
  second target next to the first, after the commit) and asserts the same
  sentence with the path quoted by `shlex.quote`; unlike the first assertion
  it does not depend on `TMPDIR`.
* **#270: add the two states** to the same test, after the keyless file: no
  policy file (the file removed again) and an invalid file (`self.put("not
  json")`); both give `[]` for `adopting=True` and for the default.
* **#264 point 1:** the sentence becomes "Archives beyond the cap are not
  listed and are left for a later run." The `capped` needle of `TestPage`
  becomes "left for a later run". `PrunePlan.capped` stays a field with its own
  unit tests; no output prints it and the page no longer says so.
* **#264 point 2:** the `Text.` paragraph says exactly what is printed: a stop
  prints `retention prune: stopped after N of M archives; ` and its cause and,
  only when at least one archive was deleted, `retention prune: N of M
  archives were deleted before the stop; ` followed by the same closing
  warning as the done line. The exit-codes row says that a stopped cleanup
  ends with a `retention cleanup: stopped after N of M items; ` line and that
  a stopped prune prints `retention prune: stopped after N of M archives; `
  and its cause; the sentence "that closing line is what tells a stop apart"
  becomes "the `stopped` line is what tells a stop apart".
* **The pages keep their header stamp** (Workflow Manager 1.18.1, Workflow
  2.29.3): this item changes wording, it does not re-check a page against a
  release.
* **Where the docs pins go.** `TestPage` in tests/test_retention_unattended.py
  already pins the page's sections by needle and reads `docs/exit-codes.md`
  (the neighbouring sentences are pinned), so the new docs pins join it; the
  code side of "the deleted count only when archives were deleted" is pinned
  in tests/test_retention_unattended_prune.py next to the existing stop test.

## 3. Tests and failure-only mutations

CP1:

* tests/test_compatibility.py: the shlex expectation and the spaced-target test
  of section 2.
* tests/test_retention_unattended.py: the two extra states in the adopting
  helper test.

CP2:

* tests/test_retention_unattended.py `TestPage` (new test): the page holds the
  new cap sentence and the exact stop sentences, does not hold "counted as
  `capped`" or the unconditional "(after a stop, `N of M archives were deleted
  before the stop`)"; `docs/exit-codes.md` holds the two stop lines and does
  not hold "closing line is what tells a stop apart"; the page's needle list
  swaps `capped` for the new wording.
* tests/test_retention_unattended_prune.py: a prune stop at the first archive
  prints `retention prune: stopped after 0 of 3 archives` and does not print
  "were deleted before the stop"; the existing stop test keeps the other half.

**Failure-only mutations** (scratch copy under `$TMPDIR` only, never the
repository; each passes the unmutated control and fails as stated):

| Mutation | Must fail |
| --- | --- |
| `render_command` in `compatibility.py` joins with a space instead of `shlex.join` | the spaced-target test (the existing assertion alone would pass under a plain `TMPDIR`) |
| `unattended_lines` reads `adopting` before the `not state.policy` guard and returns a head for a state with no file | the new states of the adopting helper test |
| `docs/retention.md` is reverted to "counted as `capped`", or to the unconditional "after a stop" parenthesis | the new `TestPage` test |
| `docs/exit-codes.md` is reverted to "closing `retention cleanup: stopped` line says what was done" | the new `TestPage` test |
| `retention_unattended.py` prints the deleted-count line for a stop with nothing deleted (`elif prune_result.done or True`) | the zero-deleted stop test |

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The tests: a quoted verify command and the adopting helper's empty states | - | 1 | 1 |
| CP2 | The docs say what the code prints, and their pins | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the tests: a quoted verify command and the adopting helper's empty states

**Files:** `tests/test_compatibility.py`, `tests/test_retention_unattended.py`.

The shlex expectation and the spaced-target test (#257), and the no-file and
invalid-file states in the adopting helper test (#270), as in sections 2 and 3.
Verification: `python3 tests/run_all.py --select test_compatibility.py`, then
`--select test_retention_unattended.py`, then the first two mutations of
section 3 on a scratch copy.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the docs say what the code prints, and their pins

**Files:** `docs/retention.md`, `docs/exit-codes.md`, `tests/test_retention_unattended.py`, `tests/test_retention_unattended_prune.py`.

The cap sentence and the stop text of `docs/retention.md`, the exit-1 row of
`docs/exit-codes.md`, the new `TestPage` test and the swapped needle, and the
zero-deleted stop test, as in sections 2 and 3. Verification: `--select` of
`test_retention_unattended.py`, `test_retention_unattended_prune.py`,
`test_docs.py` and `test_operator_ux_docs.py`, the last three mutations of
section 3, then the full gate `python3 tests/run_all.py` once, at the last
checkpoint.
<!-- /CP2 -->

## 5. Functional review

Flows are offline greps and diffs, listed in the checklist the Controller
prepares: the diff touches only the declared files (`git diff --stat`), the
two wording fixes read as specified, the page stamps are unchanged, and
`git diff --exit-code` against the base shows `src/`, `docs/ROADMAP.md` and
every page not named here untouched.

## 6. Risks and open decisions

* A docs pin that quotes a whole sentence breaks on a later reword; the pins
  quote the two printed line prefixes and the cap clause only, not the
  paragraph.
* The spaced-target test copies a fixture with its Git directory; it uses a
  scratch directory and removes it with the test's own cleanup.
* #264 point 3 (`KeyboardInterrupt` in the prune apply) is a `src/` change and
  is not taken here; #264 stays open for it.
* No row of `docs/TECHNICAL_DECISIONS.md` is touched. No open decision is
  finalised here.
