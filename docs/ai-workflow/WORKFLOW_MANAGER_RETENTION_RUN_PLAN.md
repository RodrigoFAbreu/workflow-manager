# Workflow Manager: The Confirmed Retention Cleanup Run (Revision 3)

`work_item_id: retention-run` -- `governing_workflow_version: "2.2"`

**Deliverable:** `workflow-manager retention-cleanup TARGET --confirm SENTENCE`
archives and then removes the finished work items the preview lists, through
the Workflow's own script, only when the sentence is the one bound to the
plan's digest. Prune is never run. The follow-ups of #198 ride along as a
closing checkpoint (roadmap row 39; #90, #198, wf#84).

**Work item type:** `process`. **Base commit:** `662e6c2`
(`662e6c2d95eed185b93aa5a0e38330ab05f3bacb`, tip of `main`, Manager 1.17.0;
Workflow 2.29.1 installed, automatic gates). **Branch:**
`milestone/retention-run`. **Scope source:** the owner's decision of
2026-11-10: cleanup and both modes may archive finished items and then remove
them, only after the engine verified the archive; prune stays user-only and is
never run; a literal confirmation sentence bound to the plan is the control.
Two checkpoints. A Manager release (`feat`, minor) follows the merge.

**Size rule.** This slice deletes data, so CP1 is one new module, one flag and
one runner function; the #198 clean-up is its own closing checkpoint and changes
no behaviour of the run. The plan stays under 450 lines, so no split.

## 1. Investigation (done at `662e6c2`, on the real script in a scratch repository)

I ran the release's own `scripts/workflow_retention.py` (a stub forge through its
`run=`/`resolve=` seams, a scratch `HOME`, merged items with review folders) and
read its code. It exits 0 or 2 only; a refusal is `error: CODE: message` and
`next step: ...` on stderr; `--json` prints one object.

| Step | On disk | In Git |
| --- | --- | --- |
| `archive ID --apply` | creates `<store>/<repo>/` (default `~/.local/share/workflow-archive/<repo>`, durable), packs into `.ID.partial`, checks every entry by reading the archive back and re-scanning the folder, hard-links it to `ID.tar.zst`, unlinks the partial, appends one line to `index.jsonl`; the review folder is untouched; no lock file (an `flock` on the store directory, released on exit); a failure undoes what the run created | nothing |
| `remove ID` (dry run) | nothing written; reads the archive and hashes the folder; refuses `not_archived` without the archive file **and** its index line, `archive_mismatch` when one entry differs | nothing |
| `remove ID --apply` | one atomic rename of the folder to `<store>/<repo>/.removing/ID`, a SHA-256 comparison of every file with the archive, then deletion entry by entry; on a mismatch it renames the folder back; an empty `.removing` directory stays | nothing |

**Where the folder is after each refusal** (checked against
`scripts/workflow_retention.py` at `662e6c2`; the Manager reads none of these, it
quotes the engine's message and `next step:` verbatim, 2.3):

| Refusal | Raised at | The review folder afterwards |
| --- | --- | --- |
| `cross_device` | the dry run (select step 10, folder in place) and again at the rename (`EXDEV`) | in `.ai-review`, nothing moved; **nothing progresses on a re-run** (see below) |
| `archive_busy`, `leftover_conflict`, a `place_failed` before the rename | steps 1 and 3 | in `.ai-review`, nothing moved or deleted |
| `place_failed` from an fsync after the rename | step 3 | whole in `.removing/ID`, rename done, not confirmed durable; `remove ID --apply` again |
| `folder_changed` or `archive_mismatch` while verifying | step 3 (and `archive_mismatch` step 2) | renamed back to `.ai-review` when the restore works; none deleted |
| `restore_failed` | step 3 | whole in `.removing/ID`, nothing deleted |
| `folder_changed` or `remove_failed` during the deletion | step 3 | partly deleted in `.removing/ID`, every deleted entry proven archived |
| `remove_failed` from the final fsync | step 3 | deleted, every entry proven archived |

**Git and the commit question.** The review folders are untracked (the engine
refuses `tracked_files`), no state file or trailer is touched, and `git status`
and HEAD are identical before and after. There is nothing to commit; the
Manager commits nothing and the report says so (O1).

**What verifies the archive.** `archive --apply` verifies its own tarball, and
`remove` (dry run or apply) compares the archive with the folder by content
before it deletes anything; `remove` refuses a folder with no verified archive.
There is no separate `verify` verb: the engine's own check available alone is the
dry run of `remove`, which writes nothing. The run uses it as the explicit
"verified" stage (O4).

**Why the Manager's precondition is still needed.** The engine protects the data
(archive first, content-verified), not the authority: it knows nothing of the
owner's policy, the confirmation, the release floor (before 2.25.5 it can end in a
traceback in the middle of a removal), a modified installed script, an
uncommitted policy or an interrupted removal. Those are the preflight of the
preview (reused unchanged). The Manager reimplements neither verb: it chooses ids
and verbs, runs the target's script in its own process group, and reads its exit
status and JSON.

**Interrupted runs and re-runs.**

| Situation | What it looks like | What a re-run does |
| --- | --- | --- |
| archive done, remove not (the run stopped, or was killed) | archive file and index line exist, folder intact | the report lists the item with an archive: planned `remove only`; no archive call (a second `archive` is refused `already_archived`, so it is never issued) |
| remove half done | folder in `.removing/ID`, partly deleted | the preflight refuses (`removing` in the report) and names the user-only `remove ID --apply`, which resumes; the run never resumes it |
| archiver killed (SIGKILL) | `.ID.partial` left | the next `archive` refuses `partial_present` (a leftover, not a danger); the run stops at that item and says so |
| two runs at once | the engine's `flock` | the second stops with `archive_busy`; nothing is lost |
| store on another file system than `.ai-review` (`cross_device`) | step 1 archives, step 2 (the dry run) refuses; the folder stays | every re-run plans `remove only`, verifies, refuses again: no progress. The Manager never passes `--archive-root` (closed argv, 2.2), so the store is under `HOME`; the report quotes the engine's cause and next step and the page tells the user to remove by hand with `--archive-root`, or to run with a `HOME` on the repository's file system (a user who changes `HOME` for that keeps `gh` signed in with `GH_CONFIG_DIR` set to the real configuration directory first, and needs a Git identity if the run's repository setup commits; `docs/retention.md` says so) |
| `remove --apply` stopped by the Manager (timeout, Ctrl-C, unreadable output) | the engine has no signal handler: the folder may still be in `.ai-review`, or be in `.removing/ID` partly deleted | the item line never says "untouched" (2.3); if the folder is in `.removing`, the next preflight refuses (`removing`) until the user-only `remove ID --apply` finishes it; otherwise the next run plans `remove only` again |

## 2. Design

### 2.1 The command

`retention-cleanup TARGET` is unchanged without `--confirm`: the preview, exit 0.
`retention-cleanup TARGET --confirm SENTENCE` (the flag `adopt-retention-policy`
uses) runs the **same** `retention_cleanup.preflight` (steps 1 to 8, with its one read-only `report`, so every
existing refusal and its no-write guarantee are inherited), recomputes `select`
from the fresh report and its `plan_digest`, and acts only if the sentence
holds. The sentence is `Run the retention cleanup DIGEST12.` (the first 12
characters of the plan digest, the same width `adopt-retention-policy` uses). The
check is the adoption check's: whitespace collapsed, case ignored, other words
allowed, at least one match and every match the same 12 characters.
A sentence that names another plan (a plan changed since the preview, another
repository, another policy digest all move the digest), or none, or an empty
string, is a refusal before any `archive` or `remove` call (exit 2, `next:` names the
command that shows the current plan; the preflight's read-only `report` has run). A plan with no items runs nothing (exit 0, the
preview's text; the sentence is not consulted).

### 2.2 The run (`retention_run.py`, new)

`run(target, plan, confirm_policy_digest) -> Result` walks `plan.items` in the
preview's order (at most 5, the preview's cap, not a second one). For each item,
every step a call of the target's script through `retention.launch_script` (2.3):

1. unless the action is `remove only`: `archive ID --apply --json`; success is
   exit 0, `kind == "retention-archive"`, `work_item_id == ID` and
   `result.archived is True`;
2. verify: `remove ID --json` (the dry run); success is exit 0,
   `kind == "retention-remove"`, `mode == "dry-run"` and `verify.matches is True`;
3. `remove ID --apply --json`; success is exit 0, `kind == "retention-remove"`,
   `mode == "apply"`, `work_item_id == ID` and `result.removed is True`.

Before each item the adopted policy is read again (`retention_policy.load`); any
state but ADOPTED, or another digest, stops the run ("the policy changed").
The first failure of any step (exit not 0, a timeout, output that is not the
expected JSON, a failed step condition, the policy check, Ctrl-C) **stops the
run**: no further call and no further item. The argv is built in one place from a
closed list of three forms, each ending in `--repo-root ROOT` as `report` does
(the target never depends on the script's location default), and never carries `prune`, `--archive-root`,
`--ttl-days` or any user text; `ID` is the plan's, already matched by the
engine's pattern. A timeout is 600 seconds per call (O7), enforced as
`retention.fetch` does it (the group is ended and reaped).

### 2.3 The runner and the report

`retention._run` becomes the public `retention.launch_script(root, *args,
timeout)`; `_run` calls it with `report --json --repo-root ROOT`, behaviour and
the 300 seconds unchanged. The run prints as it goes (flushed), so a killed
Manager leaves a record of what was done:

```text
retention cleanup: running plan 9f8e7d6c5b4a (mode both, policy 1a2b3c4d5e6f), 3 items
  1. item-a: archived 41 MiB, verified, removed
  2. item-b: remove only, verified, removed
  3. item-c: stopped at verify (archive_mismatch): the review folder differs from its archive in 1 entry: REVIEW.md (differs)
     next step (the engine's): ...
retention cleanup: stopped after 2 of 3 items; item-c was archived and its folder is untouched; nothing was committed or needs committing
```

Each item line says what was done and what was not (archived, verified,
removed; or the step and the engine's `CODE` and `next step:` verbatim); items
after the stop are listed as `not attempted`. The last line says how many items
completed. A clean run ends `retention cleanup: done, N of N items archived and
removed; Git is unchanged (the review folders were untracked); prune was not run`.

**What a stop may claim.** The item line names the step as `archive` (step 1), `verify` (step 2, the dry run) or `remove` (step 3, `--apply`). Steps 1 and 2 never move the folder (`archive` leaves
it, the dry run writes nothing), so a stop there says "its folder is untouched"
(after a step-1 timeout or interrupt also that a `.ID.partial` may remain). After
a step-3 stop the Manager knows less. On an engine refusal the item line quotes the
engine's message and `next step:` verbatim (they say where the folder is, section
1) and the closing line says "archived and verified; where its folder is: see the
engine's message", never "untouched". After a timeout, an interrupt or output that
cannot be read, the closing line says the folder's state is unknown and may be
partly removed, and names the user-only `remove ID --apply` (the next run's
preflight refuses until it finishes, if the folder is in `.removing`).

**Exit status:** 0 the preview, nothing to do, or a run that finished every item;
2 a refusal before any `archive` or `remove` call (nothing written: no file, no
lock, no temporary; stderr `error:` and `next:`); 1 the run stopped after at least one
engine call started (stdout the report above; stderr `error:` and `next:` for the
stop). The cause of a stop is never swallowed into a success. Exit 1 is also what a
traceback and the CLI's generic file error end with; the report's closing
`retention cleanup: stopped ...` line is what tells a stop apart, and
`docs/exit-codes.md` says so.

### 2.4 The preview's last lines

The two closing lines of the preview change (the pinned block in the tests too):
the "does not apply the plan" sentence goes; `next:` names the command with the
sentence: `workflow-manager retention-cleanup TARGET --confirm "Run the retention
cleanup 9f8e7d6c5b4a."`; one more line names the by-hand route (the Workflow's
user-only `/archive-finished-item ID`, and for an item already archived
`python3 -I scripts/workflow_retention.py remove ID --apply` alone), which is
#198 item 3's `APPLY_STEP` half. A scheduled job passes the sentence it reads
from that line.

### 2.5 Safety by construction

| Property | How |
| --- | --- |
| nothing removed without a verified archive | step 2 must succeed before step 3 is issued; `remove --apply` verifies again |
| prune never | the closed argv list; a test records every argv of every scenario and asserts the verb set |
| every refusal before the first archive writes nothing | the Manager takes no lock and creates no file; the preflight and the report are read-only; per refusal the repository tree, the archive store and `TMPDIR` are compared before and after |
| first failure stops | the loop `return`s the result at the first non-success |
| not a second implementation | no tar, no zstd, no hashing, no `rm` in the Manager |

### 2.6 Documentation

`docs/retention.md` gets the run section (sentence, steps, stop rule, report,
exit status, re-runs, the default store and `HOME`, the `cross_device` case (with the `GH_CONFIG_DIR` and Git-identity note for a changed `HOME`), that
a job which scrapes the sentence from the preview makes the confirmation a
formality, nothing committed), the
preview's lines and example change, and the "later release cleans up" sentence is
updated. `docs/exit-codes.md` gets the exit 1 row and the exit 2 row's new cause.
The help and the pages name no internal id.

### 2.7 The #198 fold-in (CP2)

1. A public `compatibility.git_env(extra_config=(), drop_config_parameters=False)`
   returns the hermetic environment (`_GIT_ENVIRONMENT`, selectors dropped, the
   extra pairs appended, `GIT_CONFIG_PARAMETERS` dropped only when asked);
   `retention_cleanup._git` passes `drop_config_parameters=True` and
   `compatibility.run_git` calls it with the defaults, so `run_git`'s environment
   is byte-for-byte what it is today (`verify`, `status`, `doctor` keep honouring
   `GIT_CONFIG_PARAMETERS`; a test pins it). `retention._release_key` becomes
   `retention.release_key`, `retention_alert._incomplete` becomes
   `retention_alert.incomplete`, `retention._shown` becomes `retention.shown` and
   `retention_policy._WORDS` becomes `retention_policy.WORDS` (and `retention_policy`'s
   `from .retention import _shown`). The rule is scoped to what CP2 can deliver:
   **no retention module** (`retention`, `retention_alert`, `retention_cleanup`,
   `retention_policy`, `retention_run`) uses a sibling's underscore name, by
   attribute access or `from .x import _y`. Other modules' uses (`advice._options`,
   `advice._not_a_directory_tail`, `cache._local_pin`, `release._version_key`) are
   outside this item (2.8). The `_filter_overrides` docstring is re-wrapped.
2. Tests: the invalid and reserved id test asserts the skipped folders stay in
   `plan.before` for `runtime`, `archive` and an invalid id;
   `test_steps_one_to_six_start_no_script` restores the adoption record so the
   dirty-tree plus modified-script case really reaches steps 4 and 6.
3. An INVALID policy refusal names its first problem (the cause ends with it).

### 2.8 Not in this item

The private cross-module names outside the retention modules (`advice._options`,
`advice._not_a_directory_tail`, `cache._local_pin`, `release._version_key`), an
`--archive-root` option for the run (the `cross_device` case), the notification
sender, `ttl` and keep-recent policy fields, any change to the
Workflow's engine, prune, a `--json` output, resuming an interrupted removal.

## 3. Failure-only mutations

Each is applied with `sed` in a fresh scratch copy; the named test runs alone from
`tests/`, passes unmutated and fails mutated.

| id | mutation | test that fails |
| --- | --- | --- |
| M1 | a `prune` form added to the argv list | `TestNeverPrune` |
| M2 | step 2 (the dry run) skipped | `TestOrder.test_remove_apply_follows_a_verified_archive` |
| M3 | the check accepts any 12-hex sentence | `TestSentence.test_another_plans_sentence_is_refused` |
| M4 | the sentence compared to the policy digest | `TestSentence.test_the_plan_digest_binds_the_sentence` |
| M5 | the loop continues after a failure | `TestStop.test_the_first_failure_stops_before_any_further_call` |
| M6 | `archive` issued for a `remove only` item | `TestOrder.test_remove_only_issues_no_archive` |
| M7 | exit 0 accepted without `result.archived` true | `TestStop.test_an_exit_zero_that_says_not_archived_stops` |
| M8 | verification fails but removal still issued | `TestNoRemovalWithoutVerification` |
| M9 | the preflight skipped under `--confirm` | `TestRefusalsWriteNothing.test_every_preflight_refusal_with_a_sentence` |
| M10 | an empty `--confirm` treated as absent | `TestSentence.test_an_empty_sentence_is_a_refusal` |
| M11 | the policy re-check before each item removed | `TestStop.test_a_policy_changed_during_the_run_stops` |
| M12 | a timeout read as success | `TestStop.test_a_timeout_stops_and_leaves_no_process` |
| M13 | unparseable output read as success | `TestStop.test_output_that_is_not_json_stops` |
| M14 | exit 1 returned as 0 | `TestReport.test_exit_codes` |
| M15 | exit 2 returned for a started run | `TestReport.test_exit_codes` |
| M16 | not-attempted items omitted | `TestReport.test_a_stopped_run_says_what_was_done_and_not_done` |
| M17 | a file written before the sentence check | `TestRefusalsWriteNothing.test_a_wrong_sentence_writes_nothing` |
| M18 | Ctrl-C propagates unreported | `TestStop.test_an_interrupt_stops_and_reports` |
| M19 | an empty plan runs the engine | `TestSentence.test_an_empty_plan_runs_nothing` |
| M20 | the preview's `next:` loses the sentence | `TestExample.test_the_exact_block` (also `TestPreview.test_the_exact_block_through_the_cli_for_both_and_cleanup`) |
| M21 | `--apply` dropped from the archive call | `TestEndToEnd.test_the_real_engine_archives_verifies_and_removes` |
| M22 | the run issues removal before archive | `TestOrder.test_the_order_of_calls` |
| M23 | `retention_cleanup._git` no longer drops `GIT_CONFIG_PARAMETERS` | the existing `test_a_filter_inherited_through_git_config_parameters_never_runs` |
| M24 | a sibling underscore use re-added to a retention module | `TestNoPrivateCrossUse` |
| M25 | skipped folders dropped from `plan.before` | `TestSelect.test_an_id_the_engine_would_not_accept_is_skipped` |
| M26 | step 6 (script state) removed | `TestPreflight.test_steps_one_to_six_start_no_script` |
| M27 | an INVALID refusal without its problem | `TestPreflight.test_an_invalid_policy_names_its_problem` |
| M28 | a step-3 timeout reported with "untouched" | `TestStop.test_a_step_three_timeout_never_claims_the_folder_untouched` |
| M29 | a step-3 interrupt reported with "untouched" | `TestStop.test_a_step_three_interrupt_never_claims_the_folder_untouched` |
| M30 | `run_git` drops `GIT_CONFIG_PARAMETERS` | `TestGitEnv.test_run_git_environment_is_unchanged` |
| M31 | `cross_device` read as success or hidden | `TestStop.test_cross_device_stops_at_verification_and_names_the_cause` |
| M32 | step 3 accepts a report for another `work_item_id` | `TestStop.test_step_three_requires_the_same_shape_as_the_others` |
| M33 | an argv form without `--repo-root` | `TestNeverPrune` (the argv shape assertion) |

## 4. Tests

Hermetic: no network, no `gh`, no process left behind; only scratch repositories,
never this repository's work items (`tests/test_retention_run.py`, new, built on
`Base` of `tests/test_retention_cleanup.py`).

* **Stub script.** A target script that logs every argv and answers per
  `verb[--apply]:ID` from a scenario table (exit, stdout, stderr), so a test fixes
  "archive succeeds, verification fails" exactly.
* `TestSentence`: the exact sentence runs; another plan's, another repository's,
  another policy digest's, none, empty, wrong case-only differences (accepted),
  extra words (accepted) and two different digests (refused); an empty plan runs
  nothing; the sentence is not consulted before the preflight.
* `TestOrder`: the call list is exactly `archive`, `remove`, `remove --apply` per
  item in preview order; a `remove only` item has no archive call.
* `TestNoRemovalWithoutVerification`: archive exits 0 and says archived, the dry
  run refuses `archive_mismatch`: no `remove --apply` in the log; the report names
  the item as archived, unverified, folder untouched; exit 1.
* `TestStop`: a failure at each of the three steps of the first and of a later
  item stops the run, later items `not attempted`; exit nonzero with a bad shape
  of output, a timeout (patched to 1 second, the stub's `sleep` mode, no orphan),
  an interrupt, and a policy changed mid-run. At step 3 a timeout and an
  interrupt (the stub killed, optionally leaving `.removing/ID`): the report never
  says "untouched", it names `remove ID --apply`, and the next preflight refuses
  with its `removing` cause when the folder is there; step 3 refuses a report with
  another `work_item_id`, `kind` or `mode`; a `cross_device` refusal (exit 2 at the
  dry run, the engine's text) stops at step 2, the report quotes the engine's cause
  and next step, the folder is untouched, the exit is 1.
* `TestNeverPrune`: across every scenario above no argv contains `prune`,
  `--archive-root` or `--ttl-days`; the verbs are exactly `report`, `archive`,
  `remove`, and every argv of the three forms ends in `--repo-root ROOT`.
* `TestRefusalsWriteNothing`: for each preflight refusal (policy not adopted,
  mode, uncommitted file, dirty tree, old release, modified script, incomplete
  report, interrupted removal, missing script) run with a valid-looking sentence:
  exit 2, no engine write verb in the log, and the repository tree hash, the
  archive store (still absent) and a scratch `TMPDIR` listing equal before and
  after; the same for a wrong sentence.
* `TestReport`: the exact text of a clean, a stopped and a `remove only` run; exits 0, 1, 2.
* `TestEndToEnd` (one): the pristine install of the newest tested release
  (`build_bootstrapped_repo`, the release's own unmodified script), an `origin` on
  github.com, a state file of finished items, folders, a committed adopted policy,
  a scratch `HOME`; the forge through the script's own `run=`/`resolve=` seams
  (the recipe of `tests/retention_recipe.py`, a patched `retention.launch_script`
  launcher only; the script-state seam patched as `Base` does). Run with the sentence: the archives and index lines exist, the
  folders are gone, `git status` and HEAD are unchanged, a second run says
  nothing to do, and the report lists no removal. Skipped with a named reason when
  `zstd` is not on `PATH`; the acceptance evidence says whether it ran.
* `TestNoPrivateCrossUse` (CP2): an AST scan of the five retention modules finds
  no attribute access of a sibling module's underscore name and no `from .x import
  _y`. `TestGitEnv` (CP2, in `tests/test_compatibility.py`): `git_env` with an extra
  pair and with `drop_config_parameters`; `run_git`'s environment, with
  `GIT_CONFIG_PARAMETERS` exported, still carries it and equals the environment of
  `662e6c2` (captured through a patched `subprocess.run`).

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The confirmed run: sentence, runner, stop rule, report, docs, tests | - | 3 | 1 |
| CP2 | The #198 fold-in: public names, test fixes, the INVALID problem | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the confirmed run

**Files:** `src/workflow_manager/retention_run.py`, `src/workflow_manager/retention_cleanup.py`, `src/workflow_manager/retention.py`, `src/workflow_manager/cli.py`, `tests/test_retention_run.py`, `tests/test_retention_cleanup.py`, `docs/retention.md`, `docs/exit-codes.md`.

Sections 2.1 to 2.6 and the tests of section 4. `retention_run.py` is new
(`run`, `Result`, the closed argv, the report lines); `retention_cleanup.py` gains
`sentence`, `confirmation_holds` and the preview's closing lines;
`retention.py` gains `launch_script`; `cli.py` the `--confirm` flag, the help and the
dispatch. Then mutations M1 to M22 and M28, M29, M31 to M33, `python3 tools/check_docs.py` (exit 0),
`python3 tests/run_all.py --select test_retention_run.py`, `--select
test_retention_cleanup.py`, `--select test_operator_ux.py`, `--select
test_docs.py`. Row 39 of docs/ROADMAP.md (Current; Done at acceptance) is added in
the first step; it and docs/ACTIVE_MILESTONE.md are excluded at both stages, not
deliverables.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the #198 fold-in

**Files:** `src/workflow_manager/compatibility.py`, `src/workflow_manager/retention.py`, `src/workflow_manager/retention_alert.py`, `src/workflow_manager/retention_cleanup.py`, `src/workflow_manager/retention_policy.py`, `tests/test_retention_cleanup.py`, `tests/test_retention_run.py`, `tests/test_retention_status.py` (its calls of the renamed helper), `tests/test_compatibility.py` (the new tests of the public Git environment helper).

Section 2.7. Then mutations M23 to M27 and M30, the `--select` runs of CP1 plus
`test_compatibility.py`, `test_read_only.py` and `test_retention_alert.py`, then the
full gate `python3 tests/run_all.py`. No version is edited. The pull request title
is `feat: archive and remove finished work items under an adopted retention policy
with retention-cleanup --confirm` (checked with `python3 tools/release/release.py
check-title`: feat, minor). After the release the orchestrator's `docs:` pull
request adds the release-history row and the `Last checked with:` stamps; a
comment on #90 records the slice; #198 is closed.
<!-- /CP2 -->

## 6. Functional review

Flows 1 to 8 are offline and write nothing into the product clone, in a clone
`S/cand` (`S=$(mktemp -d "$TMPDIR/rr-fr.XXXXXX")`, `git clone --no-hardlinks
<product clone> $S/cand`, `git -C $S/cand remote remove origin`, `export
PYTHONPATH=$S/cand/src`). Flow 9 needs the full environment and runs last.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat 662e6c2d95eed185b93aa5a0e38330ab05f3bacb HEAD -- src tools tests docs .github scripts .claude` | only the files the checkpoints declare, `retention_policy.py` included, and the expected bookkeeping under `docs/` |
| 2 | `python3 -m workflow_manager retention-cleanup --help` | names `--confirm`, the sentence, archive then verify then remove, the stop rule, exit 0, 1 and 2, and that prune is never run |
| 3 | `grep -n 'prune' $S/cand/src/workflow_manager/retention_run.py` | only text that says prune is never run; no argv form carries it |
| 4 | `cd $S/cand/src/workflow_manager && grep -nE '(compatibility|retention|retention_alert|retention_policy|retention_run|retention_cleanup)\._|from \.[a-z_]+ import _' retention.py retention_alert.py retention_cleanup.py retention_policy.py retention_run.py` | no output (exit 1) |
| 5 | `grep -n 'git_env\|def release_key\|def incomplete' $S/cand/src/workflow_manager/*.py`; `awk 'length > 100' $S/cand/src/workflow_manager/retention_cleanup.py` | the three public names; no overlong docstring line |
| 6 | `python3 $S/cand/tools/check_docs.py` | exit 0 |
| 7 | `cd $S/cand/tests && python3 -B -m unittest test_retention_run.TestNeverPrune test_retention_run.TestNoRemovalWithoutVerification` | OK |
| 8 | in scratch copies of the clone apply M1, M3, M5, M8 and M12 with `sed` and run the named test of each | each FAILED, the unmutated clone OK |
| 9 | (full environment) `python3 tests/run_all.py --select test_retention_run.py`, then `test_retention_cleanup.py`, `test_retention_alert.py`, `test_compatibility.py`, `test_read_only.py`, `test_operator_ux.py`, `test_docs.py`; in a scratch managed repository with `gh` signed in and a throwaway origin, run the preview, then `--confirm` with its sentence; the repository and a scratch `HOME` (`export GH_CONFIG_DIR=$HOME/.config/gh HOME=$S/home`, set in that order so `gh` stays signed in through its real configuration directory and keyring; the scratch repository gets a local `user.name`/`user.email`, because a scratch `HOME` has no `~/.gitconfig`) are both under `$S`, so `.ai-review` and the archive store share a file system (otherwise the engine refuses `cross_device`, section 1) | `verdict: exit 0` each, no `OrphanProcessError`; the run archives and removes the planned items, `git status` unchanged |

## 7. Risks

* **Data loss is the risk of this slice.** The engine verifies by content before
  every deletion and refuses without an archive; the Manager adds a content
  check of its own as an explicit stage and stops at the first failure. No test
  touches this repository's work items.
* A killed Manager mid-`remove` leaves a leftover; the next preflight refuses and
  names the user-only `remove ID --apply`.
* The sentence proves the plan was shown, not who asked (the owner's choice).
* The run costs the report's forge queries plus up to three calls per item (600 s
  each at most). The default archive store is under `HOME`: a job with another
  `HOME` archives elsewhere, and `docs/retention.md` says so. A repository on
  another file system than `HOME` gets `cross_device` at step 2 on every run (the
  archive is made, the removal never is); the page names the by-hand route.
* A Manager stop at step 3 (timeout, Ctrl-C) can leave the folder partly deleted in
  `.removing/ID`; every deleted entry was proven archived, the report does not
  claim otherwise (2.3) and the next preflight refuses until the user finishes it.

## 8. Open decisions (owner), each with a default

* **O1** commit: the Manager commits nothing (nothing is tracked; the report says
  so). Default: as planned.
* **O2** sentence `Run the retention cleanup DIGEST12.`, 12 characters like the
  adoption sentence. Default: as planned (alternative: the full 64).
* **O3** exit 1 for a run that stopped after starting, 2 for a refusal before.
  Default: as planned.
* **O4** the dry run of `remove` as a separate verification (hashes twice).
  Default: keep.
* **O5** a `remove only` item with no index line stops the run (no repair);
  **O6** an interrupted removal is refused by the preflight, never resumed;
  **O7** 600 seconds per engine call. Defaults: as planned.
* **O9** an interrupt or timeout during step 3 kills the engine's process group
  (the engine resumes safely and every deleted entry was proven archived) rather
  than letting the in-flight call finish, bounded by the timeout. Default: kill, so
  Ctrl-C and the timeout stay prompt; the alternative is a bounded grace period.
* **O8** the end-to-end test skips, with a named reason, when `zstd` is missing.
  Default: skip and cite.
