# Workflow Manager: Interrupt During the Unattended Prune's Audit Writes (Revision 1)

`work_item_id: unattended-prune-interrupt` -- `governing_workflow_version: "2.2"`

Pull request title: `fix: stop the unattended prune cleanly on an interrupt during its audit writes`

**Deliverable:** an interrupt (Ctrl-C, or SIGINT from the lane heartbeat) that
lands while the prune phase of `retention-cleanup --unattended` writes its
`started` audit line, or its `ok` audit line after a successful apply, stops the
phase with `interrupted` like every other interrupt of the phase, instead of
escaping unhandled. One mechanism: the two audit writes the phase's
`KeyboardInterrupt` handling does not yet cover. **A Manager patch release**
(the title is `fix:`; `python3 tools/release/release.py check-title` reads
"valid title: fix, release impact patch").

**Work item type:** `process`. **Base commit:**
`a9dda8980619aafcdee5d3fbff6f7fd07a74552b` (tip of `main`; Workflow 2.29.3 is
this repository's own installation, automatic gates, default "2.2").
**Branch:** `milestone/unattended-prune-interrupt`, bound by the Controller.
**Scope source:** point 3 of issue #264 only (points 1 and 2 were taken by the
retention-followup-pins item; the issue has no comments) and the work-item
prompt. **Manager only**: nothing under `.claude/`, `scripts/`,
`.workflow-manager/` or the managed documents of `docs/ai-workflow/` is edited.
**ROADMAP:** no row is added or changed; this cleanup item needs none. Nothing
in this item runs `retention-cleanup --unattended` or any archive, remove or
prune command against a real repository: the tests drive scratch repositories
and a fake script only.

## 1. Verification on current main

#264 point 3 is **TRUE-FIX-NEEDED**, both spots, in
`src/workflow_manager/retention_prune.py` (`run_phase`):

1. The `started` write, lines 361 to 368: `note("prune", None, "started",
   first=True)` (line 362) sits in `try ... except Exception` only. A
   `KeyboardInterrupt` is not an `Exception`, so it escapes `run_phase`. No
   engine call had been made yet, but the run neither stops with `interrupted`
   nor records it. Every other interrupt of the phase is handled: the policy
   re-reads (lines 334, 373, 390), the report and dry run (lines 340, 382) and
   the apply call (line 401).
2. The `ok` write after a successful apply, lines 404 to 417:
   `entry["result"] = "done"` (404), then `observer("prune", item_id, "ok",
   ...)` (405 to 406) in `try ... except Exception` only (407). An interrupt
   here escapes with the archive **already deleted**: the run neither records
   nor says so, and the result keeps `done` for an entry whose stop is never
   reported.

The model to follow is the cleanup loop in `src/workflow_manager/retention_run.py`
(`run_items`, lines 280 to 358): its `_observe` call after each step is inside
the same `try` as the engine call, so an interrupt during the audit write lands
in `except (_Stop, KeyboardInterrupt)` (line 300), which prints `stopped at
{step}: interrupted` (line 314), stops the run, and writes one observer line
with result `interrupted`, the step, the item id and `engine_code` `None`
(lines 346 to 352). The prune phase has the same line shape in its own
handlers: `note("prune", item_id, "interrupted", None, interrupted_line)` then
`stop("prune", item_id, f"{item_id}: {interrupted_line}")` (lines 401 to 403).
The `ok`-write failure of the prune phase already says "the apply had
succeeded; no further call was made" (lines 410 to 415); the new wording
reuses those clauses.

## 2. Decisions

* **The `started` write:** a new `except KeyboardInterrupt:` clause, placed
  before `except Exception` on the existing `try`, writes the `interrupted`
  line and stops, exactly as the dry-run handler does:
  `note("prune", None, "interrupted", None, interrupted_line)` and
  `return stop("prune", None, interrupted_line)`. No engine call has been
  made; the stop text is the plain `interrupted`, so the run prints
  `retention prune: stopped after 0 of N archives; interrupted`. The phase
  outcome is `stopped` and the exit code is the one of the existing
  interrupted stops, with no change to either.
* **The `ok` write:** a new `except KeyboardInterrupt:` clause on the existing
  `try` around `observer(... "ok" ...)`, before `except Exception`. The text is
  `interrupted; the apply had succeeded (the archive is deleted); no further
  call was made`. It writes one audit line `note("prune", item_id,
  "interrupted", None, text)` (the line shape of the per-item handler: step
  `prune`, the item id, result `interrupted`, no engine code) and returns
  `stop("prune", item_id, f"{item_id}: {text}")`. The entry keeps `done`
  (the archive IS deleted), so the stop line's "N of M archives" counts it,
  and `apply_attempted` stays true. The audit line for the `ok` itself is lost
  (the write was interrupted); the `interrupted` line is the record, and says
  so.
* **No other behaviour changes.** `note` itself is untouched (it swallows only
  `Exception`; a second interrupt during the `interrupted` line is the
  operator's own and out of scope). The cleanup loop is untouched.
* **Docs:** `docs/retention.md`'s "Audit lines" paragraph (line 432) already
  describes the `interrupted` result of the prune ("one per archive with `ok`
  (deleted), `failed` ... or `interrupted`"), so one clause is added there: an
  `interrupted` line is also written when the run is interrupted while the
  `started` line or an archive's `ok` line is being written, and for the second
  case the archive is already deleted and the line says so. A pin in
  `TestPage` holds the clause. `docs/exit-codes.md` already says an interrupt
  is an exit 1 stop after a first call and is not changed.
* **Stop rule:** if the fix needs more than these two guarded spots, the item
  stops and records a finding instead.

## 3. Tests and failure-only mutations

CP1, in `tests/test_retention_unattended_prune.py`, class `TestAuditFailures`
(its observer seam, `failing`, raises `OSError` at the n-th observer call; the
new tests use an observer that raises `KeyboardInterrupt` at the n-th call and
otherwise records the line, like the neighbouring interrupt tests):

* **`started` interrupt** (call 1): the outcome is `stopped`, `result.stop` is
  `("prune", None)`, the phase's text is `retention prune: stopped after 0 of 3
  archives; interrupted` (read from the `said` lines), `self.verbs()` is `[]`
  and `apply_attempted` is false (no engine call made, so also
  `result.calls` is empty), the last recorded audit line is `("prune",
  "interrupted", None)`, every entry is `not-attempted` or `stopped` and none
  is `done`, and the repository tree is unchanged (`self.tree()`).
* **`ok` interrupt** (call 3: `started`, `a-oldest` ok, `b-mid` ok raises):
  the outcome is `stopped`, `result.stop` item id is `b-mid`, the error holds
  "interrupted" and "the apply had succeeded" and "the archive is deleted",
  `self.verbs()[-1]` is `prune b-mid --apply` and its length is 3 (no call
  for `c-new`), the entry results are `done, done, not-attempted`, the last
  audit line is `("prune", "interrupted", "b-mid")` with the same text, and
  the stop line reads `stopped after 2 of 3 archives`.

CP2, in `tests/test_retention_unattended.py`, `TestPage`: the page holds the
new clause (pinned on its two halves, `interrupted` while the `started` line
or an archive's `ok` line is written, and "already deleted").

**Failure-only mutations** (scratch copy under `$TMPDIR` only, never the
repository; each passes the unmutated control and fails as stated):

| Mutation | Must fail |
| --- | --- |
| delete the new `except KeyboardInterrupt:` clause of the `started` write | the `started` interrupt test (the interrupt escapes `run_phase`) |
| delete the new `except KeyboardInterrupt:` clause of the `ok` write | the `ok` interrupt test (the interrupt escapes `run_phase`) |
| the `ok` clause drops "the apply had succeeded" from its text | the `ok` interrupt test (text and audit line) |
| `docs/retention.md` reverted to the base wording of the Audit lines paragraph | the new `TestPage` test |

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The two interrupt handlers and their tests | - | 2 | 1 |
| CP2 | The Audit lines clause and its pin | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the two interrupt handlers and their tests

**Files:** `src/workflow_manager/retention_prune.py`, `tests/test_retention_unattended_prune.py`.

The two `except KeyboardInterrupt` clauses of section 2 and the two tests of
section 3 with their text and audit-line assertions. Verification:
`python3 tests/run_all.py --select test_retention_unattended_prune.py`, then
the first three mutations of section 3 on a scratch copy.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the Audit lines clause and its pin

**Files:** `docs/retention.md`, `tests/test_retention_unattended.py`.

The clause of section 2 and its `TestPage` pin. Verification: `--select` of
`test_retention_unattended.py`, `test_retention_unattended_prune.py`,
`test_docs.py` and `test_operator_ux_docs.py`, the last mutation of section 3,
then the full gate `python3 tests/run_all.py` once, at the last checkpoint.
<!-- /CP2 -->

## 5. Functional review

Flows are offline greps and diffs, listed in the checklist the Controller
prepares: the diff touches only the declared files (`git diff --stat`), the two
handlers read as specified, the docs clause reads as specified, the page stamps
are unchanged where not re-checked, and `git diff --exit-code` against the base
shows `docs/ROADMAP.md`, `docs/exit-codes.md` and every page not named here
untouched.

## 6. Risks and open decisions

* The `ok` interrupt happens after the archive is deleted, so the stop cannot
  undo anything; the item only makes the run say so and record it.
* A second interrupt while the `interrupted` line is written escapes `note`
  (it swallows only `Exception`); that is the operator's own and is the same
  in every other handler of the phase.
* No row of `docs/TECHNICAL_DECISIONS.md` is touched. No open decision is
  finalised here.
