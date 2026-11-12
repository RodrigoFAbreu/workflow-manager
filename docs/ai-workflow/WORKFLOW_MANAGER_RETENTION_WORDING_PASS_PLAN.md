# Workflow Manager: What the Retention Commands Say Is Exact (Revision 2)

`work_item_id: retention-wording-pass` -- `governing_workflow_version: "2.2"`

**Deliverable:** the report text of the retention commands says exactly what is
known, and a test pins each corrected text: the stop report of a confirmed
retention run after an archive-step stop, the exit-code wording, and the preview's
`next:` line (roadmap row 40; #201, #195, #192, #198). The run's behaviour does
not change.

**Work item type:** `process`. **Base commit:** `ec2f368`
(`ec2f368b33cb6f5e52c8670b63458d73ea1fc0bf`, tip of `main`, Manager 1.18.0;
Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/retention-wording-pass`. **Scope source:** the owner's sweep order of
2026-11-12. Two checkpoints. A `fix:` Manager patch release (1.18.1) follows the
merge, because the text of a released command changes.

**Size rule.** One mechanism: what the retention commands tell the operator is
exact and pinned. The safety-adjacent report accuracy is CP1 alone; everything
else is CP2. The plan stays under 350 lines, so no split.

## 1. Investigation (done at `ec2f368`)

Each candidate item checked on current `main`; the evidence is the line read.

| Item | Class | Evidence |
| --- | --- | --- |
| #201.1 `was not archived` for any parsed engine refusal | TRUE-FIX-NEEDED | `retention_run.py:204` sets `settled` for any `stop.engine`; `_closing` `:142-149` prints `was not archived`; the engine's `warning: the undo could not remove` is never read (`_engine_refusal` `:66-72` reads `error:` and `next step:` only) |
| #201.1 `already_archived` | TRUE-FIX-NEEDED | same path: an `already_archived` refusal reads `was not archived`, though an archive exists |
| #201.2 exit 1 is `after an engine call started` | TRUE-FIX-NEEDED | `exit-codes.md:31`, `retention.md:231`, `retention_run.py:48-49` say so; `result.started = bool(result.calls)` (`:238`) counts only `archive`/`verify`/`remove` calls, never the preflight's `report`; a policy change before item 1 exits 2 (`:239`) with no test and no doc line |
| #201.2 preview prints the literal `TARGET` | TRUE-FIX-NEEDED | `retention_cleanup.py:424`; the refusal quotes the real target (`cli.py:998`, `shlex.quote`); `preview_lines(plan)` has no target; pinned by `EXAMPLE` (`tests/test_retention_cleanup.py:191`) and `docs/retention.md:202` |
| #201.3 step 2 (verify) shape cases | TRUE-FIX-NEEDED | `test_step_three_requires_the_same_shape_as_the_others` (`tests/test_retention_run.py:259`) covers `remove --apply` only |
| #201.3 per-case restore in `test_every_preflight_refusal_with_a_sentence` | TRUE-FIX-NEEDED | `:501-509`: the restore runs after `self.refuse(...)` inside the `subTest`, so a failing case skips it and the next cases cascade |
| #201.3 record the fix-round gate run | KEEP | evidence of the finished item `retention-run`; nothing to change here |
| #195.1a `none can be pruned` when incomplete | ALREADY-FIXED | `retention_alert.py:140` (`no prunable archive was observed (the report is incomplete)`), pinned `tests/test_retention_alert.py:600-602` |
| #195.1b null installed version reads as a network cause | ALREADY-FIXED | `cli.py:849-850` returns `SCRIPT_NO_RELEASE`; `retention_alert.py:193-197` and `retention_cleanup.py:234-236` give the cause `the installation record names no release` with an `update --release-version` step; pinned `tests/test_retention_alert.py:616-632` |
| #195.2 test strength | ALREADY-FIXED | `:466-477` compares the whole `--retention` section; `:752-816` assert `REFUSAL`, the real script's own cause; `:624-637` is the real, unpatched `_installed_script_state` case, with `tree_hash` unchanged |
| #195.3 a `:60` seconds case | ALREADY-FIXED | `tests/test_retention_policy.py:667` |
| #192.1 help text and `invalid` step | ALREADY-FIXED | `cli.py:1198-1199` lists the link and non-regular-file refusals (pinned `tests/test_retention_policy.py:647-648`); `retention_policy.py:404,460` name `adopt-retention-policy TARGET ... to preview it` |
| #192.2 `adopted_at` by shape only | ALREADY-FIXED | `retention_policy.py:203-211` parses with `strptime`; `tests/test_retention_policy.py:662-672` |
| #198 items 2 and 3 | KEEP | not in this item's list; item 1 is fixed (`retention_cleanup.py:89`) and its preview `TARGET` half is #201.2 above |

**What the engine does** (`scripts/workflow_retention.py`, the installed copy):
`_apply` (`:1164-1262`) packs into `.ID.partial`, links it to `ID.tar.zst`
(`placed`), appends the index line, and on any failure calls `_undo` (`:1264-1296`),
which restores the index, drops `ID.tar.zst` when it was placed, removes the
partial and the directories it created, and, when any of that fails, writes
`warning: the undo could not remove: ...` to stderr, then the refusal is
printed. So after a refusal **with** that warning an archive (and its index line)
may still exist. `already_archived` is raised only before `placed` is set
(`:971-973`, before the link: the archive and, or, its index line are found
present; `:1220`: another run placed it first), so it always means an archive exists
that this run did not create, and the undo has nothing of the archive to touch.
Neither case can reach `remove`: a stop at the archive step ends the run.

## 2. Design

### 2.1 The report after an archive-step stop (CP1)

`_closing` keeps its shape (`head + fact + tail`); only `fact` changes, from one
of four causes. The item line (`stopped at archive (CAUSE): message`), the engine's
next step, every other closing line, the result's `error:` and `next:`, the exit
code and the calls issued are unchanged.

| The archive step stopped because | fact (before the tail `and its folder is untouched (...)`) |
| --- | --- |
| the engine refused `already_archived` (with or without the undo warning: it concerns only the temporary and the directories) | `this run did not create an archive for ID (one already exists)` |
| the engine refused with another cause and printed `warning: the undo could not remove` | `ID may or may not be archived (the engine's undo could not remove everything it created; the next preview shows which)` |
| the engine refused with another cause, no warning; or the script could not be started | `ID was not archived` (unchanged) |
| a timeout, an interrupt, unreadable or unexpected output, an unparsed exit | `ID may or may not be archived (the next preview shows which)` (unchanged) |

Code: `_engine_refusal` stays as is; a new `_undo_unsettled(stderr: bytes) -> bool`
is true when any stderr line starts with the constant `UNDO_WARNING` (`warning: the undo could not remove`);
`_Stop` gains `unsettled: bool = False`, set in `_call` for a parsed refusal;
`run` passes the closing the cause code and the flag instead of the one boolean
`settled`, and `_closing` takes an `archive_state` (`NOT_ARCHIVED`, `UNSETTLED`,
`FOREIGN`). The precedence is `already_archived` first, then the warning.

### 2.2 The exit codes (CP2)

The criterion is the code's: `result.started = bool(result.calls)`
(`retention_run.py:238`), and `_call` appends to `calls` *before* it launches the
script (`:104`). Exit 1: the run stopped after its first per-item call (`archive
--apply`, the verification, or `remove --apply`) was attempted, even if the script
could not be started (`ran=False`: exit 1 with no engine process run). The
preflight's `report` is not one. A `remove only` first item stopped at its
verification is therefore exit 1. Exit 2: refused, or stopped before that first
call (the policy changed, or the run was interrupted, while item 1's policy was
read); nothing written. "The verification" and `remove` keep the names the docs
and the help already use (`remove ID --json`, the dry run; `remove ID --apply`).
Reworded in
`retention_run.py` (the `Result` docstring), `cli.py` (the help),
`docs/retention.md` (the exit-status bullet and the closing paragraph) and
`docs/exit-codes.md` (rows 1 and 2 of `retention-cleanup`). The behaviour is not
touched; `TestReport.test_exit_codes` pins each boundary: exit 2 for a policy
changed before item 1 (no call but the report, nothing written); exit 2 for an
interrupt while item 1's policy is read (`calls` empty); exit 1 for a stop at the
first `archive` call; exit 1 for a script that cannot be started at item 1's
`archive` (`ran=False`); and exit 1 for a remove-only first item stopped at its
verification (the dry run, not `remove --apply`).

### 2.3 The preview's `next:` line (CP2)

`preview_lines(plan, target)` takes the target and prints
`workflow-manager retention-cleanup <shlex.quote(str(target))> --confirm "..."`,
as the refusal does (`cli.py:998`, the target as the operator typed it). The one
caller, `cmd_retention_cleanup` (`cli.py:992`), passes `args.target`; the
`nothing to do` lines are unchanged. `docs/retention.md`'s example block shows a
concrete path (`/srv/repo`) and says the line names the target.

### 2.4 Test hygiene (CP2)

The step-2 shape cases (`work_item_id`, `kind`, `mode`; a dry run with `matches`
false) join the shape test, renamed `test_a_step_must_return_its_own_shape`, for
`verify`; `test_every_preflight_refusal_with_a_sentence` restores in `try/finally`.

### 2.5 Not in this item

Any new behaviour; a repair of an archive left by an unsettled undo; the
notification sender; `keep_recent`, `ttl`; the Workflow engine; CI; #198 items 2
and 3; recording the earlier item's gate run (#201.3, KEEP).

## 3. What pins the old text, and the golden

Changed user-visible text and every pin of it, to be updated in the same
checkpoint as the text:

| Text | Pinned by |
| --- | --- |
| `... was not archived` for an `already_archived` refusal | no test (the case is new); `tests/test_retention_run.py:344,355` pin the unchanged `place_failed` and no-start cases and stay as they are |
| `exit 1 ... after an engine call started` | `docs/retention.md:231`, `docs/exit-codes.md:31`, `retention_run.py:48-49`, the `cli.py` help (`:1221-1223`); no test reads them, so CP2 adds `TestDocsSayExitCodes` |
| the help's `1: the run` | `tests/test_retention_cleanup.py:842` (`test_the_help_names_the_preview_the_run_the_floor_and_prune`) pins that substring; CP2 rewords that help, so it keeps the substring `1: the run` (the reworded sentence continues after it) and the test is extended with the new criterion |
| the literal `TARGET` in `next:` | `tests/test_retention_cleanup.py:191` (`EXAMPLE`, used at `:234` and `:708`), the other `preview_lines(plan)` callers in that file (`:103-167`), `docs/retention.md:202`. `:708` compares the CLI's whole stdout with `EXAMPLE` and is not a `preview_lines` caller: `EXAMPLE` becomes a template with a `{target}` field, formatted with `shlex.quote(str(self.repo))` at `:708` and with the example's target in `TestExample` |

**Golden.** Before any edit, a scratch driver under `$TMPDIR` (outside the
repository) runs the existing harness over these scenarios and writes each stdout,
stderr and exit code to `golden-before/`: a clean run, a stop at verify, a stop at
remove (refusal, timeout), a remove-only run, a `place_failed` stop, a timeout
stop at archive, a policy change after item 1, the preview and a nothing-to-do
preview. The same driver writes `golden-after/` once both checkpoints are done.
`diff -r` must show only: the `next:` line of the preview, and the closing line of
the new `already_archived` and undo-warning scenarios (which have no before).

## 4. Failure-only mutations

Fresh copy each (`command cp -f` into `$TMPDIR`); the unmutated copy passes the
named test; the mutated copy fails it.

| # | Mutation | Failing test |
| --- | --- | --- |
| M1 | `_undo_unsettled` always false | `test_an_unsettled_undo_may_or_may_not_be_archived` |
| M2 | the `already_archived` branch removed (reads `was not archived`) | `test_already_archived_says_this_run_did_not_create_one` |
| M3 | the warning takes precedence over `already_archived` | `test_already_archived_wins_over_an_undo_warning` |
| M4 | the warning is read from stdout, not stderr | M1's test |
| M5 | a stop after an archive-step engine refusal continues to `verify` | `test_an_archive_step_stop_never_reaches_remove` |
| M6 | the policy-before-item-1 stop exits 1 | `test_exit_codes` (the policy case) |
| M6b | `result.started` true regardless of `calls` (an interrupt at item 1's policy exits 1) | `test_exit_codes` (the interrupt case) |
| M6c | `_call` appends to `calls` only after a successful launch (a script that cannot be started exits 2) | `test_exit_codes` (the cannot-start case) |
| M7 | `preview_lines` prints `TARGET` | `TestExample.test_the_exact_block` |
| M8 | the target printed unquoted | `test_the_preview_quotes_the_target` |
| M9 | `_expected` ignores `mode` for verify | `test_a_step_must_return_its_own_shape` (verify arm) |
| M10 | the docs sentence reverted in a scratch copy of `docs/` | `TestDocsSayExitCodes` |
| M11 | the `dirty tree` case's cause text changed to a wrong one in the test | one subTest failure only, the later cases still run (`failures=1`) |

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Report accuracy after an archive-step stop | - | 2 | 1 |
| CP2 | Exit-code wording, the preview's real target, test hygiene | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- report accuracy after an archive-step stop

**Files:** `src/workflow_manager/retention_run.py`, `tests/test_retention_run.py`, `docs/retention.md`.

Section 2.1. Tests in `tests/test_retention_run.py` (the stub scenario's `stderr`
carries the warning line; each asserts the closing line, the calls issued and
that no `verify` or `remove` followed):
`test_an_unsettled_undo_may_or_may_not_be_archived` (a refusal with the warning),
`test_already_archived_says_this_run_did_not_create_one` (an `already_archived`
refusal), `test_already_archived_wins_over_an_undo_warning` (both), and
`test_an_archive_step_stop_never_reaches_remove` (all three: calls are
`archive --apply:item-00` only, the folders and `tree_hash` of the repository
are unchanged). The existing `place_failed` and no-start assertions stay as they
are: the golden for the unchanged text. `docs/retention.md` (the paragraph after
the run example) states the four cases. Then M1 to M5, `python3 tools/check_docs.py`,
`python3 tests/run_all.py --select test_retention_run.py`, `--select
test_docs.py`.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- exit-code wording, the preview's real target, test hygiene

**Files:** `src/workflow_manager/retention_cleanup.py`, `src/workflow_manager/retention_run.py`, `src/workflow_manager/cli.py`, `tests/test_retention_cleanup.py`, `tests/test_retention_run.py`, `docs/retention.md`, `docs/exit-codes.md`.

Sections 2.2 to 2.4. `retention_cleanup.preview_lines(plan, target)`;
`TestExample` and the other `preview_lines` callers pass a target;
`test_the_preview_quotes_the_target` (a target with a space) and
`TestDocsSayExitCodes` (the new wording is in `docs/retention.md` and
`docs/exit-codes.md`, and the old `after an engine call started` is nowhere) are
new; `EXAMPLE` becomes a template with a `{target}` field (formatted with
`shlex.quote(str(self.repo))` at `tests/test_retention_cleanup.py:708`, with the
example's target in `TestExample`); the help keeps the substring `1: the run`
pinned at `:842`; `test_exit_codes` gains the policy-before-item-1, the
interrupt-at-item-1's-policy, the cannot-start-at-archive and the remove-only
(stopped at the verification) cases;
the step-2 shape test and the `try/finally`. Then M6, M6b, M6c and M7 to M11, the golden diff
(section 3), `python3 tools/check_docs.py`, the `--select` runs of
`test_retention_run.py`, `test_retention_cleanup.py`, `test_operator_ux.py` and
`test_docs.py`, then the full gate `python3 tests/run_all.py`. No version is
edited. The pull request title is `fix: say exactly what a retention cleanup stop
left behind and name the target in the preview` (checked with `python3
tools/release/release.py check-title`: fix, patch). After the release the
orchestrator's `docs:` pull request adds the 1.18.1 row to the release history;
comments on #201, #195, #192 and #198 record what was fixed and what was already
fixed (item list of section 1); #201 and #195 and #192 close when nothing is left
open in them. Row 40 of docs/ROADMAP.md (Current; Done at acceptance) is added
in the first step; it and docs/ACTIVE_MILESTONE.md are excluded at both stages,
not deliverables.
<!-- /CP2 -->

## 6. Functional review

All flows are offline, in a clone `S/cand` (`S=$(mktemp -d "$TMPDIR/rw-fr.XXXXXX")`,
`git clone --no-hardlinks <product clone> $S/cand`, `git -C $S/cand remote remove
origin`, `export PYTHONPATH=$S/cand/src`) and write nothing into the product
clone. The last flow needs the full environment and runs last.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat ec2f368b33cb6f5e52c8670b63458d73ea1fc0bf HEAD -- src tools tests docs .github scripts .claude` | only the files the checkpoints declare, and the expected bookkeeping under `docs/` |
| 2 | `grep -n 'did not create an archive\|undo could not remove\|may or may not be archived' $S/cand/src/workflow_manager/retention_run.py` | the three facts of section 2.1 and the warning prefix |
| 3 | `grep -rn 'after an engine call started' $S/cand/src $S/cand/docs/retention.md $S/cand/docs/exit-codes.md` | no output (exit 1) |
| 4 | `grep -n 'def preview_lines\|shlex.quote' $S/cand/src/workflow_manager/retention_cleanup.py`; `grep -n 'TARGET --confirm' $S/cand/src/workflow_manager/retention_cleanup.py` | `preview_lines(plan, target)` quoting the target; no literal `TARGET --confirm` |
| 5 | `grep -n 'test_an_unsettled_undo\|test_already_archived\|test_an_archive_step_stop_never\|test_the_preview_quotes\|TestDocsSayExitCodes\|test_a_step_must_return_its_own_shape' $S/cand/tests/test_retention_run.py $S/cand/tests/test_retention_cleanup.py` | each of the six names present |
| 6 | in scratch copies of the clone apply M1, M2, M6, M7 and M9 with `sed` and run the named test of each from `tests/` | each FAILED, the unmutated clone OK |
| 7 | `python3 $S/cand/tools/check_docs.py` | exit 0 |
| 8 | (full environment, last) `python3 tests/run_all.py --select test_retention_run.py`, then `test_retention_cleanup.py`, `test_operator_ux.py`, `test_docs.py` | `verdict: exit 0` each, no `OrphanProcessError` |

## 7. Risks

* The undo warning is read from free text on stderr. The engine writes it as one
  literal prefix (`:1296`); if a later release rewords it, the report falls back
  to the old `was not archived`, which the integration test of a real archive
  cannot catch. The wording is the only thing at stake: no folder is removed after
  an archive-step stop either way. The prefix is one named constant with a test.
* `preview_lines` gains a required argument: its only caller is `cli.py`, and a
  caller that forgets it fails at once rather than printing `TARGET`.
* The exit-code docs describe, they do not change, the exit codes.
* The engine's undo-warning prefix is written once and identically in every
  release from the 2.25.5 floor to 2.29.3 (`scripts/workflow_retention.py:1296`,
  and `already_archived` is raised before `placed` is set), and it is the target's
  own installed script, not this repository's, that runs; the constant is pinned
  against that fact.

## 8. Open decisions (owner), each with a default

* **O1** `already_archived` plus the undo warning reads as `already_archived`
  (an archive exists regardless). Default: as planned.
* **O2** the undo warning is not a new exit code or a new refusal: exit 1, as
  every archive-step stop. Default: as planned.
