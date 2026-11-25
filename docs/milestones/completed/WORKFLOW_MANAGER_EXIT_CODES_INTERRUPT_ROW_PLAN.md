# Workflow Manager: The Exit-Codes Table Names An Interrupt Before The Prune's First Call (Revision 1)

`work_item_id: exit-codes-interrupt-row` -- `governing_workflow_version: "2.2"`

Pull request title: `docs: say in the exit codes that an unattended prune interrupt before its first call exits 2`

**Deliverable:** row 2 of the `retention-cleanup` table in `docs/exit-codes.md`
says that an unattended prune interrupted before its first `prune --apply`
exits 2, like its other stops before any change, and that an interrupt after
one exits 1; a test pins the clause. Follow-up of #276 (the Optional finding
LPR1-003 of the plan review of the previous prune-interrupt item, #264 point 3).
**Docs and one test pin only: no `src/` change and no release.**
`python3 tools/release/release.py check-title` on the title above reads "valid
title: docs, release impact none".

**Work item type:** `process`. **Base commit:**
`a19f6a215fda91ba55b2dc5e785b509d05079cb3` (tip of `main`; Workflow 2.29.14 is
this repository's own installation, automatic gates, default "2.2").
**Branch:** `milestone/exit-codes-interrupt-row`, bound by the Controller.
**Manager only**: nothing under `.claude/`, `scripts/`, `.workflow-manager/` or
the managed documents of `docs/ai-workflow/` is edited.
**ROADMAP:** no row is added or changed; this is a cleanup item and needs none.
Nothing in this item runs `retention-cleanup --unattended` or any archive,
remove or prune command against a real repository; it reads code and edits a
page and a test.

## 1. Verification on current main

Issue #276 (open, no comments) is **TRUE-FIX-NEEDED**. At the base, row 2 of
the `retention-cleanup` rows of `docs/exit-codes.md` (line 34) reads: "An
unattended prune that stops before any call of the run was attempted (its
refusal, or a dry run that does not match the plan) exits 2 too." It names no
interrupt.

What the code does:

* `src/workflow_manager/retention_unattended.py:443-446`: when the prune phase
  stopped and the cleanup phase did not, `ran = bool(result is not None and
  result.calls) or prune_result.apply_attempted` and `exit_code = 1 if ran else
  2`. So a prune stop exits 2 exactly when the cleanup made no per-item call
  and no `prune --apply` was attempted.
* `src/workflow_manager/retention_prune.py` (`run_phase`) turns a
  `KeyboardInterrupt` in each operation listed below into a stop (`STOPPED`).
  It does not guard every operation of the phase: the archive selection
  (`select`, line 354) runs outside the handlers, and an interrupt there
  escapes; this plan documents only the guarded ones. The
  interrupts that land **before** `result.apply_attempted = True` (line 397),
  which is set just before the first `--apply` call:
  1. while the policy is re-read before the report: `policy_interrupted(None)`
     (lines 332-335);
  2. while the fresh report is fetched (lines 338-342);
  3. while the `started` audit line is written (lines 361-366);
  4. while the policy is re-read before the dry run (lines 374-378);
  5. during the engine's dry run (lines 380-386);
  6. while the policy is re-read before the **first** apply: the loop's
     `holds()` (lines 391-395) runs before line 397.
  Each of these stops with `apply_attempted` false, so in a run whose cleanup
  made no call the run exits 2.
* An interrupt after line 397 exits 1: during an apply call (lines 399-405),
  while an `ok` line is written (lines 406-414), and while the policy is
  re-read before the second or a later item (`apply_attempted` is already
  true). The same holds when the cleanup phase made a call: the prune stop then
  exits 1 whatever its cause.
* The cleanup phase's own interrupt before its first call already exits 2 and
  is already named in the row ("the run was interrupted, while item 1's policy
  was read").
* The report and dry-run interrupts the issue calls "just as unlisted" are
  items 2 and 5 above. A stop that is not an interrupt (the policy changed,
  the report unavailable or incomplete, the `started` line not writable) also
  exits 2 on the same rule; the issue's scope is the interrupt, and the row's
  "its refusal" is left as it is.

Where the row is pinned: no test asserts the clause "An unattended prune that
stops before any call" (grep of `tests/` for it and for "does not match the
plan" finds nothing). Row 2 as a whole is pinned only in its cleanup half:
`tests/test_retention_run.py:826` holds "or the run stopped before that first
call" for `exit-codes.md`, and `tests/test_retention_unattended.py`
`TestPage.test_the_page_says_what_a_stop_and_the_cap_print` (line 672) pins the
two `stopped` lines in row 1. So the prune clause is **not pinned**; this item
adds a pin for the new wording only, in `TestPage` of
`tests/test_retention_unattended.py`, where the prune's page wording is pinned.
No existing pin is edited, and none of their needles is touched by the new
wording.

## 2. Decisions

* **The wording** (row 2, in the page's own style, one sentence replacing the
  one quoted above; the rest of the row is unchanged):
  "An unattended prune that stops before any per-item call or `prune --apply`
  was attempted exits 2 too: its refusal, a dry run that does not match the
  plan, or an interrupt that lands before the first `prune --apply` (while the
  policy or the fresh report is read, while its `started` audit line is
  written, or during the engine's dry run); an interrupt after a `prune
  --apply` was attempted exits 1." The phrase "before any call of the run was
  attempted" is made exact (it counted the dry run as a call, which does not
  change anything and does not decide the exit code), in the words row 1 uses.
* **Row 1 is not changed** (it already says a prune stops with exit 1 "after
  the cleanup's first call or after a `prune --apply`"), nor
  `docs/retention.md` (its line 438 says the prune's stop exits 1 when a call
  was attempted, else 2, in terms that already cover an interrupt).
* **The stamp stays.** `docs/exit-codes.md` keeps its `Last checked with:
  Workflow Manager 1.18.1, Workflow 2.29.3` stamp: one row is re-checked
  against the code, not the page, and a stamp moves only because the whole page
  was re-checked. No other page is touched.
* **The pin** (one new test, `test_the_exit_codes_row_names_an_interrupt_before_the_first_prune_apply`,
  in `TestPage`): on the whitespace-squashed text of `docs/exit-codes.md`, it
  asserts the four halves of the sentence: "An unattended prune that stops
  before any per-item call or `prune --apply` was attempted exits 2 too", "or an
  interrupt that lands before the first `prune --apply` (while the policy or the
  fresh report is read, while its `started` audit line is written, or during the
  engine's dry run)", "an interrupt after a `prune --apply` was attempted exits
  1" and that the stale "before any call of the run was attempted" is absent.
* **No internal id** is named on the page (no milestone id, no issue number).
* **Stop rule:** if the code turned out to exit differently from section 1 for
  any listed interrupt, the item stops and records a finding instead of
  writing the clause.

## 3. Tests and failure-only mutations

The pin is the only test change; it fails against the base wording and passes
against the new one. Failure-only mutations (scratch copy of the page under
`$TMPDIR` only, never the repository; each passes the unmutated control and
fails as stated):

| Mutation | Must fail |
| --- | --- |
| `docs/exit-codes.md` reverted to the base wording of the sentence | the new pin (the base text lacks every half) |
| the parenthesis dropped from the clause (interrupt named, no where) | the new pin |
| "exits 1" of the after-apply half changed to "exits 2" | the new pin |

Existing pins stay green: `--select` of `test_retention_unattended.py`,
`test_retention_run.py`, `test_retention_cleanup.py`, `test_docs.py` and
`test_operator_ux_docs.py` (the page checker), then the full gate once.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The interrupt clause in row 2 and its pin | - | 1 | 1 |

<!-- CP1 -->
### CP1 -- the interrupt clause in row 2 and its pin

**Files:** `docs/exit-codes.md`, `tests/test_retention_unattended.py`.

The sentence of section 2 in row 2 and its `TestPage` pin. Verification:
`python3 tests/run_all.py --select test_retention_unattended.py`, the same for
`test_retention_run.py`, `test_retention_cleanup.py`, `test_docs.py` and
`test_operator_ux_docs.py`, the mutations of section 3, then the full gate `python3 tests/run_all.py` once.
<!-- /CP1 -->

## 5. Functional review

Flows are offline greps and diffs, listed in the checklist the Controller
prepares: the diff touches only the two declared files (`git diff --stat`), the
page's stamp is unchanged, the new sentence reads as specified and the base
sentence is gone, rows 1 and the other pages are untouched
(`git diff --exit-code <base> -- docs/retention.md docs/ROADMAP.md src/`), and
the pin fails against the base page.

## 6. Risks and open decisions

* The sentence promises exit 2 for an interrupt only in a run whose cleanup made
  no call; the clause says "before any per-item call or `prune --apply` was
  attempted", which carries that condition.
* No row of `docs/TECHNICAL_DECISIONS.md` is touched. No open decision is
  finalised here.
