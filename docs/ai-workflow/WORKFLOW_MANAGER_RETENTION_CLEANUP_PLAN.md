# Workflow Manager: The Retention Cleanup Preview (Revision 3)

`work_item_id: retention-cleanup` -- `governing_workflow_version: "2.2"`

**Deliverable:** a new explicit command `workflow-manager retention-cleanup
TARGET` that, for a retention policy the owner adopted with mode `cleanup` or
`both`, checks every precondition of an unattended cleanup and **previews**
exactly which finished work items it would archive and remove, in which
order, under which plan digest. It writes nothing and runs no engine verb
but the report. The four follow-ups of #195 ride along (roadmap row 38; #90,
wf#84).

**Work item type:** `process`. **Base commit:** `bb5a016`
(`bb5a016b01c62e551eeb0adf255c36db28d86ca9`, tip of `main`, Manager 1.16.0;
Workflow 2.29.1 installed, automatic gates). **Branch:**
`milestone/retention-cleanup`. **Scope source:** the owner's decision of
2026-11-10 ("yes go ahead"): an automatic cleanup that acts only under an
adopted policy and only archives, then removes; prune stays user-only. Two
checkpoints. A Manager release (`feat`, minor) follows the merge.

**Why this is the preview and not the whole run (size rule).** The full
design (preflight, selection, preview, confirmation, a runner for two engine
verbs, stop semantics, report, docs, tests, four follow-ups) does not fit
one reviewable item: the confirmed run alone adds a launch path that deletes
files. This item plans and ships everything up to the line "nothing is
written": the loader and preflight, the selection, the preview, every
refusal. The confirmed run is the next row, with the design fixed in 2.7 so
it is not reopened. This item removes and archives nothing, in tests or in
use.

**Revision history.** Rev 1-2: the plan as approved. Rev 3 (amendment 0): the
work item id equals the new command name, so the docs check (`tools/check_docs.py`
rule 3, internal ids) flagged `retention-cleanup` in `docs/retention.md`. The
implementation fixed the check, a file the plan and the artifact declaration did
not name, so the gate refused it; rev 3 records the change (2.9, CP2, M35, flow
7) and classifies the path. No other design changed.

## 1. Investigation (done at `bb5a016`, before any design)

### 1.1 What the Workflow's engine does

`scripts/workflow_retention.py` (installed 2.29.1; `docs/RETENTION.md` in the
`workflow` repository) has four subcommands: `report`, `archive`, `remove`,
`prune`. Each takes `--json`, `--repo-root`, `--archive-root` (default
`~/.local/share/workflow-archive`); the writers take `--apply` and are dry
runs without it.

| Verb | Writes | Refuses (stderr `error: <code>: ...` and `next step: ...`, exit 2) | Guarantees |
| --- | --- | --- | --- |
| `archive ID --apply` | `<root>/<repo>/ID.tar.zst`, one `index.jsonl` line | for example `not_finished:*`, `kept_recent`, `already_archived`, `tracked_files`, `unreadable`, `review_folder_absent`, `zstd_missing`, `archive_busy` | packs the untracked folder, verifies the tarball, links it into place without overwriting, makes it durable; never touches the folder |
| `remove ID --apply` | moves the folder to `.removing/ID`, then deletes it | for example `not_archived`, `tracked_files`, `cross_device`, `leftover_conflict`, `archive_mismatch`, `archive_busy`, `unreadable` | compares every file's SHA-256 with the archive **before** any delete; a mismatch renames the folder back; `flock` on the archive directory |
| `prune ID... --apply` | unlinks archives past the time to live | for example `item_not_finished`, `archive_changed`, `removal_interrupted` | irreversible; never touches a review folder |

The codes in the table are examples, not a closed list (the engine has more, such as
`folder_changed`, `partial_present`, `not_in_report`, `path_unsafe`, `pack_failed`,
`verify_failed`, `restore_failed`); the stop rule of 2.7 is keyed to the exit
status, never to a code.

Exit status: 0 (a dry run printed, or the write is done), 2 (a coded
refusal), and any other status means the process died (a traceback was exit 1
in releases before 2.25.1 and 2.25.5). `--json` prints one object:
`result.archived` is `true` after an archive, `result.removed` is `true`
after a removal.

**What makes an item finished** (the engine decides, the Manager re-derives
nothing): phase `MILESTONE_COMPLETE` with parent and children complete, a
fresh forge query saying `merged`, and not one of the 3 most recent merged
items. Every `archive` and `remove` call rebuilds the whole report, so each
engine call costs one forge query per finished item (about 20 to 40 s for
25 items, 1.7).

**A partial failure leaves, by design, a state a re-run resolves**: after
`archive` and before `remove`, the archive exists and the folder is whole
(`archive` then refuses `already_archived`, `remove` goes ahead); a killed
`remove` leaves the folder, whole or smaller, in `.removing/ID`, which the
report lists in `removing` and `remove ID --apply` resumes (verifying against
the archive). A killed `archive` leaves `.ID.partial`, which the engine
cleans or refuses on. The engine writes no state, phase or trailer.

### 1.2 What is user-only today, and how it is enforced

`/archive-finished-item` and `/prune-archives` are commands of the Workflow
(`disable-model-invocation: true`, `state_writer: false`) that run the engine
and refuse unless the owner's own turn carries a literal sentence naming the
id (or the archives). **The script itself checks nothing**: `archive ID
--apply` runs for anyone who invokes it. The user-only property is the
command's own two controls (the flag and the sentence), so a Manager command
that drives the script needs its own, equivalent control: the owner's
adopted policy, a confirmation sentence bound to the plan (2.7), and never
the verbs `prune` or an archive deletion. A scheduled job may pass the
sentence because the owner adopted the policy; the sentence proves the plan
was shown, not who is asking.

### 1.3 Can the Manager drive it without reimplementing it? Yes

`retention.py` already runs `python3 -I -B scripts/workflow_retention.py
report --json --repo-root ROOT` in its own process group with a 300 s limit
and validates the output. The two writers have the same shape. The Manager
needs no engine logic: it chooses ids and verbs, and the engine selects,
verifies and writes. **This item runs only `report`** (through
`retention.fetch`, unchanged). It never imports the script and never reads an
archive.

### 1.4 What the target's Workflow release must carry

`archive` exists from 2.21.0, `remove` from 2.22.0 (and the report's
`removing` list). Before 2.25.1 the engine ended in a traceback when a stat
failed for a reason other than "not found", and before **2.25.5** when a
symlink in the folder could not be read, in the middle of a removal. An
unattended run must not meet a traceback after deleting part of a folder, so
**the minimum release is 2.25.5** (constant `CLEANUP_FROM`); an older one is
refused with `workflow-manager update TARGET`. The check reads the
installation record's `workflow_version`; a null or unparseable one is refused
at step 5 of the preflight (2.2), as `doctor` refuses it (2.5, follow-up 1b). The installed script must also be the
release's own (`retention_alert.script_state`): a modified script is never
started.

### 1.5 Failure modes, and where each is caught

| Mode | Caught by | Result |
| --- | --- | --- |
| dirty working tree (tracked files changed) | preflight, `clean_tree` | refusal, nothing written |
| policy files not committed, or edited after the commit | preflight, `committed` | refusal |
| item with tracked files under `.ai-review/ID` | selection: skipped and named; the engine would refuse `tracked_files` | not planned |
| unreadable item or archive | the report is incomplete: preflight refuses | refusal |
| an interrupted removal (`removing` not empty) | preflight refuses; the owner finishes it with the user-only `remove` | refusal |
| crash between archive and remove | next run: the item has an archive and a folder, planned as `remove only` | the preview names it |
| a second run at the same time | engine `archive_busy` (next row's concern) | n/a here |

### 1.6 The 4096-byte limit

The Manager's validator caps `read_errors[].path` and `archive_dir` at 4096
characters (Linux `PATH_MAX`); a longer one makes the report `malformed` and
the preflight refuses with that cause, so no path is cut short or acted on.
The policy file is capped at 4096 bytes by the loader. Ids are at most 64
characters (the engine's pattern, which the Manager checks again, with `fullmatch`,
before it plans an item). The Manager passes no `--archive-root`, so it adds no path
of its own. No new limit is introduced.

### 1.7 Committed at HEAD, without writing

`git -C TARGET show HEAD:./PATH` prints the blob at HEAD and writes nothing;
comparing it byte for byte with the working file proves "committed and
unchanged". `git --no-optional-locks status --porcelain -z
--untracked-files=no` lists changes to tracked files without refreshing the
index (plain `git status` may rewrite `.git/index`; the no-write test makes
the index stale on purpose to catch that). Untracked review folders are
expected and ignored.

## 2. Design

### 2.1 The command

`workflow-manager retention-cleanup TARGET`: a new command. It is not a
side effect of `verify`, `doctor`, `update` or `status`, which stay
read-only and never import the module's behaviour (a cleanup policy changes
their output by nothing). It has no `--confirm` in this release. Exit 0: the
preview was printed or there is nothing to do; 2: refused, nothing was
written. It runs `report` once at most, and only after every cheap check
passed.

### 2.2 The preflight, in this order (first refusal wins)

`retention_cleanup.preflight(target, version, script_state) -> PolicyState`
raises `Refusal(cause, step)`; the CLI prints `error: CAUSE` and `next: STEP`
on stderr, exit 2.

1. The repository is managed (the CLI, as `adopt-retention-policy`).
2. The policy state is `adopted` and its mode is `cleanup` or `both`. Any
   other state is refused with the state's own cause and step. The cause is
   `retention policy: STATE (WORDS)` with `WORDS` from `retention_policy._WORDS`;
   the step is `retention_policy.step_for(state, target)`, extracted from `block`
   so the two never drift. `step_for` covers every state **except `ADOPTED`**
   (it raises `ValueError` there; the caller never asks) and, new, `ABSENT`,
   which `block` prints nothing for and `_WORDS` has no entry for. The `ABSENT`
   refusal, the commonest first contact, is exact:
   `error: retention cleanup: no retention policy is adopted (there is no
   .workflow-manager/retention-policy.json)` and `next: write
   .workflow-manager/retention-policy.json with mode "cleanup" or "both"
   (docs/retention.md shows the file), then run workflow-manager
   adopt-retention-policy TARGET`; the other states reuse `block`'s step
   verbatim. `block`'s own output stays byte-identical (the existing `block`
   tests pin it, and a new assertion compares `block`'s step line with
   `step_for` for every non-adopted, non-absent state). An `ADOPTED` policy
   whose mode is `off` or `notify` is refused with `error: retention cleanup:
   the adopted mode is MODE, which does not allow cleanup` and `next: set mode
   to "cleanup" or "both" in .workflow-manager/retention-policy.json, then run
   workflow-manager adopt-retention-policy TARGET`.
3. `committed`: both `.workflow-manager/retention-policy.json` and
   `retention-adoption.json` are at HEAD with the working file's exact bytes.
   An edited policy is already `CHANGED` at step 2 and an edited tracked file is
   dirty at step 4; the step's own role is a policy or record that was never
   committed, or committed with other bytes than the adopted ones (the test
   re-adopts the edited policy first, so step 3 and not step 2 is the first
   refusal).
4. `clean_tree`: no change to a tracked file.
5. The release: the record names a parseable release (a null or unparseable
   one is refused here, with the cause and step `doctor` gives for it, `not_a_version`)
   at or above `CLEANUP_FROM`.
6. The installed script is the release's own (`script_state()` is
   `SCRIPT_OK`); modified and unchecked have each their cause (`SCRIPT_NO_RELEASE`
   cannot occur after step 5; if it does, it is refused with its own cause).
7. `retention.fetch(target)`: a refusal is passed on with its own cause and
   step (script missing, malformed, forge, timeout).
8. The report is complete (`retention_alert._incomplete` false) and `removing`
   is empty.

Steps 1 to 6 start no process but `git`; the script starts at step 7.

### 2.3 The selection, pure: `select(state, report) -> Plan`

Only the two thresholds that archiving and removing can lower take part:
`finished_items` and `finished_folder_mib` (`LOWERED`). `archives` and
`prunable_archives` never trigger and never shape a plan (archiving raises
the first; the second is prune's, which is user-only).

* Candidates: the `finished[]` entries whose folder is present, **oldest
  first** (the report lists newest first; the order is the engine's own, read
  reversed, so no new field is trusted).
* Each has an action from the report alone: no archive, `archive then remove`;
  an archive present, `remove only` (an earlier run archived and stopped).
  An entry with `tracked_files > 0` or an id that fails the engine's pattern is
  **skipped** (the re-check is `fullmatch` of the engine's `^[a-z0-9][a-z0-9_-]{0,63}$`
  and not one of its `RESERVED_IDS`, `runtime` and `archive`; it is defensive, since
  `finished[]` ids already passed the engine's own filter, which uses `match` and so
  would accept a trailing newline) and named with the reason; it still counts toward the measured
  numbers.
* Reached: count of candidates at or above `finished_items`, or folder bytes
  at or above `finished_folder_mib * 2**20`. If none of the policy's two
  thresholds is reached the plan is empty ("nothing to do").
* Take candidates in order, subtracting each from the measured numbers, until
  every set threshold is below its limit or `CAP` (5 per run) is reached.
  One run never touches more than `CAP` items. The plan ends in exactly one of
  three outcomes: `settled` (every set threshold is below its limit);
  `cap` (not settled, `CAP` items taken and an eligible candidate is left,
  so a re-run plans more); `exhausted` (not settled, no eligible candidate is
  left: every other item is skipped, so a re-run plans the same items and
  does not help). `cap` wins only when a candidate remains.
  A threshold reached with no eligible candidate at all is `exhausted` with an
  empty plan: the preview is printed (`would clean 0 of N ...`), not "nothing
  to do", and exit is 0.

### 2.4 The plan digest and the preview

`digest = sha256` of the canonical JSON of `{repository, policy digest,
items: [[id, action], ...]}`, shown as its first 12 hex characters (the
policy's `DIGEST_SHOWN`). The next row's sentence binds to it. Output
(stdout, exit 0), exact:

```text
retention cleanup: preview (nothing was written; mode both, policy 1a2b3c4d5e6f, plan 9f8e7d6c5b4a)
  thresholds reached: finished items 12 (limit 10), finished folders 612 MiB (limit 500 MiB)
  would clean 3 of 12 finished items with a review folder, oldest first, at most 5 per run:
    1. item-a: 210 MiB, archive then remove
    2. item-b: 3 MiB, remove only (already archived)
    3. item-c: 40 MiB, archive then remove
  skipped: item-x: Git tracks files under its review folder (the engine archives untracked folders only)
  after this run: finished items 9, finished folders 359 MiB: below every limit
  this release does not apply the plan. Prune is never part of cleanup; the archive store is not touched.
  next: apply it with the user-only commands, one item at a time: `python3 -I scripts/workflow_retention.py archive ID --apply`, then `remove ID --apply`
```

The `after this run:` line is `after this run: finished items N, finished
folders M MiB: OUTCOME` (a threshold the policy does not set is left out), with
`OUTCOME`, one per plan outcome of 2.3, exact:

* `settled`: `below every limit`
* `cap`: `NAMES still reached; stopped at the cap of 5 per run; run it again`
* `exhausted`: `NAMES still reached; no further item is eligible (skipped: ID,
  ID); running it again will not help`, with `(skipped: ...)` left out when no
  item was skipped

`NAMES` is `finished items`, `finished folders`, or `finished items and
finished folders`, for the thresholds still at or above their limit.

Nothing to do: one line, `retention cleanup: nothing to do (finished items
4 of 10, finished folders 12 of 500 MiB)`. Sizes are rounded down to whole
MiB, as in the alert. A threshold the policy does not set is not printed.

### 2.5 The follow-ups of #195, in the files this item changes (CP1)

1. (a) `retention_alert._step`: when the report is incomplete and no archive
   is prunable, the text reads `no prunable archive was observed (the report
   is incomplete)` instead of `none can be pruned`, and still names raising
   `thresholds.archives`. (b) `cli._installed_script_state` returns the new
   `retention_alert.SCRIPT_NO_RELEASE` for a record without a release; the
   alert reads `not evaluated: the installation record names no release`
   with the step `workflow-manager --release-version X.Y.Z update TARGET`
   (`workflow-manager releases` lists them). `SCRIPT_UNCHECKED` stays for
   resolution errors. **This cause is defensive: no command reaches it.**
   `cmd_doctor` calls `_refuse_unparseable_record` first, so a null
   `workflow_version` ends in `error: could not resolve the target release`
   (`not_a_version`), exit 2, before `alert_lines`; `cmd_verify` never asks
   `_installed_script_state` and `_release_for_target` refuses the same record;
   `retention-cleanup` refuses it at preflight step 5. #195 1b assumed a
   doctor-visible path that does not exist; the cause is kept so a later caller
   that asks first is not told a wrong one, and it is tested by calling
   `_installed_script_state` directly.
2. Test strength in `tests/test_retention_alert.py`: the doctor section test
   compares the whole `--retention` section with and without the policy,
   minus the policy block; the two `TestScriptState` cases assert the real
   script's own refusal (`repository_unknown: git remote get-url origin
   failed: error: No such remote 'origin'`, the scratch repository has no
   origin); an unpatched direct call of `_installed_script_state` for a record with no
   release and for an unresolvable one asserts the two distinct causes and,
   with `tree_hash`, that nothing was written; next to it, `cli.main doctor` on
   the null record asserts the refusal it really gives (exit 2, `could not
   resolve the target release`), so the unreachable path is pinned as such.
3. `tests/test_retention_policy.py`: a `:60` seconds case in `TestFollowUps`.

### 2.6 Documentation (CP2)

`docs/retention.md` gets a section "Retention cleanup (preview)" (the
preconditions in order, the selection, the cap, the minimum release, the
preview, that it writes and removes nothing and that prune is never part of
it) and the policy block's last line keeps saying "cleans nothing". It names
no internal id. `docs/exit-codes.md` gets the two rows of the command. The
`retention-cleanup` help text names the same.

### 2.9 The docs check and the command name (rev 3)

Decision: Manager command names are not internal ids. `check_pages(root,
commands=())` subtracts `commands` from the work-item id set of rule 3, and
`check_tree` passes `tuple(cli.COMMANDS)`; the default `()` leaves rule 3 unchanged. Reason: a work item named after the command it builds would otherwise
make the user page naming the command fail the docs check. Diff scope: only
`check_pages` and `check_tree` in `tools/check_docs.py`; no rule, page list or
message changes. It is pinned by `TestCommandNameIsNotAnInternalId` (section 4).

### 2.7 Fixed for the next row (the confirmed run), not built here

`retention-cleanup TARGET --confirm "Run the retention cleanup <plan
digest>."`: the run recomputes the preflight and the plan from a fresh report
and refuses unless the sentence names that digest (a stale or other plan is
refused, nothing done). Per item, in plan order, `archive ID --apply --json`
then, only on exit 0 with `result.archived` true, `remove ID --apply --json`
(only `remove` for `remove only`); the argv is a closed list of two verbs and
never carries `prune`, `--archive-root` or `--ttl-days`. Any non-zero exit,
timeout or unparseable output stops the whole run, with a report of what was
done and not done; exit 1 for a run that stopped after starting, 2 for a
refusal before anything started. A re-run is safe because the engine is. The
Manager keeps no record of its own.

### 2.8 Not in this item

The confirmed run, the notification sender, `ttl`/`keep-recent` policy
fields, any change to the Workflow's engine, and prune.

## 3. Failure-only mutations

Each on a fresh copy, one at a time, the named tests run alone from `tests/`
(`python3 -B -m unittest`): the unmutated copy passes, each mutation fails.

| # | Mutation | Must fail |
| --- | --- | --- |
| M1 | `_step` always says `none can be pruned` | `TestFollowUps` incomplete store |
| M2 | `_installed_script_state` returns `SCRIPT_UNCHECKED` for a null version | no-release cause test (direct call, unpatched) |
| M3 | the no-release line uses the network-retry step | the same test, step assertion |
| M4 | `cmd_doctor` rewords the section's first line when the policy alerts | whole-section comparison |
| M5 | the alert boundary returns `not evaluated: KeyError` after the script check | real-script refusal cause |
| M6 | `_is_timestamp` replaces `:60` by `:59` before `strptime` | the `:60` case |
| M7 | `committed` only checks the path exists at HEAD | policy edited and re-adopted after the commit |
| M8 | `committed` skips the adoption record | record not committed |
| M9 | `clean_tree` counts untracked files | untracked review folder is accepted |
| M10 | `clean_tree` returns without checking | dirty tracked file refused |
| M11 | `clean_tree` runs plain `git status` | no-write proof with a stale index |
| M12 | the mode check accepts `notify` | mode matrix |
| M13 | the state check accepts `changed` | state matrix |
| M14 | `CLEANUP_FROM` is `(2, 25, 4)` | 2.25.4 refused, 2.25.5 accepted |
| M15 | `script_state` is not asked before the script runs | a modified script never started |
| M16 | `retention.fetch` runs before the cheap checks | a refused policy starts no script |
| M17 | an incomplete report is accepted | incomplete refusal |
| M18 | a non-empty `removing` is ignored | interrupted removal refusal |
| M19 | candidates are newest first | order |
| M20 | `CAP` is not applied | 7 candidates, 5 planned |
| M21 | an entry with tracked files is planned | skipped with its reason |
| M22 | a plan is made with no threshold reached | nothing to do |
| M23 | `archives` or `prunable_archives` triggers a plan | only those reached: nothing to do |
| M24 | every candidate is taken, ignoring the limits | only what is needed |
| M25 | the digest ignores the policy digest | digest moves with the policy |
| M26 | the digest ignores the action | digest moves with the action |
| M27 | a refusal writes a probe file in the target | every refusal writes nothing |
| M28 | the preview also runs `archive` (dry run) | the stub's argv set is exactly `report` |
| M29 | `cmd_verify` prints the preview for a cleanup policy | verify, doctor and status unchanged |
| M30 | `step_for(ABSENT)` is not defined (raises `KeyError`) | `ABSENT` row of the state matrix |
| M31 | `block`'s step differs from `step_for` for a state | `block` vs `step_for` equality |
| M32 | the `after this run:` line always says `run it again` | the `exhausted` cases |
| M33 | the outcome is `cap` when no candidate is left | the `exhausted` cases |
| M34 | the plan stops at the first item that brings one threshold below its limit | the `settled` rule of 2.4's example |
| M35 | `check_pages` does not subtract `commands` (remove `- set(commands)`) | `TestCommandNameIsNotAnInternalId` |

## 4. Tests

`tests/test_retention_cleanup.py` (new), hermetic: the stub script of
`test_retention_status` in a scratch managed repository whose policy and
record are adopted and **committed**, no network, nothing written into this
repository. Classes:

* `TestSelect` (pure, hand-made reports): order, cap, tracked skip, actions,
  nothing to do, only the two lowered thresholds, bytes at and one byte below
  the MiB limit, an unset threshold; one case per plan outcome with the exact
  `after this run:` line (`settled`; `cap`, 7 eligible candidates, 5 taken;
  `exhausted` because the remaining items are skipped for tracked files, naming
  them; `exhausted` with an empty plan), and the rule of 2.3 on the example of
  2.4 (12 finished items, one skipped: three are taken).
* `TestPlanDigest`: stable across runs, moves with an id, an action, the
  policy digest and the repository.
* `TestPreflight`: one scratch case per step of 2.2 (state matrix with the
  `ABSENT` row and its exact `error:`/`next:` lines of 2.2 step 2, mode
  matrix, the policy file untracked, edited and re-adopted (so step 3, not
  step 2, refuses), the record missing from HEAD, a
  dirty tracked file, untracked review folder accepted, version null, 2.25.4,
  2.25.5, modified script, incomplete report, interrupted removal, a report
  refusal passed through). Each refusal runs `cli.main` in-process with the
  script-state seam patched, asserts exit 2, the `error:` and `next:` lines,
  that `tree_hash` of the whole target (`.git` included, the index made stale
  first) is unchanged, and the stub's marker: steps 1 to 6 start no script.
* In `tests/test_retention_policy.py`: `step_for` equals `block`'s step line for
  every state but `ADOPTED` and `ABSENT`, and `block`'s whole output is unchanged
  for every state.
* `TestPreview`: the exact block of 2.4 for a hand-made report; mode `both`
  and `cleanup` both preview; the stub's argv set is exactly one `report`.
* `TestOtherCommandsUnchanged`: with a cleanup policy adopted, `verify`,
  `doctor`, `status` and `update --dry-run` print what they print without it and
  start no script.
* `TestRealRules`: nothing patched, a release of the cache that ships the
  script: the real `script_state` refuses a modified script for the command, and
  a record at 2.25.4 is refused before any script starts.
* `tests/test_operator_ux.py`: `retention-cleanup` joins `TARGET_COMMANDS`, so the
  generic help, exit-code and misplaced-global-option cases cover it.
* `TestCommandNameIsNotAnInternalId` (in `tests/test_retention_cleanup.py`): a
  scratch tree with one user page naming `item-two` (a work item) and the command
  word `item-one`; `check_pages` with `commands=("item-one",)` reports exactly one
  problem, naming `item-two`.
* `TestDocs`: the help text and `docs/retention.md` name the command, the
  minimum release and that prune is never part of it.

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The #195 follow-ups: alert wording, the no-release cause, test strength | - | 2 | 1 |
| CP2 | The cleanup preview: preflight, selection, preview, docs, tests | CP1 | 3 | 1 |

<!-- CP1 -->
### CP1 -- the #195 follow-ups

**Files:** `src/workflow_manager/retention_alert.py`, `src/workflow_manager/cli.py`, `tests/test_retention_alert.py`, `tests/test_retention_policy.py`, `docs/retention.md`.

Section 2.5. The alert's incomplete-store wording, `SCRIPT_NO_RELEASE` and its
cause and step, the three test changes, and the sentence in `docs/retention.md`
that says none can be pruned. Then mutations M1 to M6, `python3 tests/run_all.py
--select test_retention_alert.py`, `--select test_retention_policy.py` and
`--select test_retention_status.py`.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the cleanup preview

**Files:** `src/workflow_manager/retention_cleanup.py`, `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_cleanup.py`, `tests/test_retention_policy.py`, `tests/test_operator_ux.py`, `docs/retention.md`, `docs/exit-codes.md`, `tools/check_docs.py`.

Sections 2.1 to 2.4, 2.6, 2.9 and the tests of section 4. `retention_policy.py`
gains `step_for` (the `block` step, extracted, `block`'s output unchanged, and the
`ABSENT` step of 2.2);
`cli.py` the command, its help and the wiring of `_installed_script_state`;
`retention_cleanup.py` is new (`preflight`, `committed`, `clean_tree`, `select`,
`plan_digest`, `preview_lines`, `Refusal`); `tools/check_docs.py` gains the
command-name exemption of 2.9 (`check_pages` and `check_tree` only). Then
mutations M7 to M35, `python3 tools/check_docs.py` (exit 0), `--select test_retention_cleanup.py`, `--select
test_retention_policy.py`, `--select test_operator_ux.py`, `--select
test_docs.py`, then the full gate `python3 tests/run_all.py`. Row 38 of
docs/ROADMAP.md (Current; Done at acceptance) and docs/ACTIVE_MILESTONE.md
record the item and the mutation results; both are excluded at both stages,
not deliverables. No version is edited. The PR title is `feat: preview what
an adopted retention policy would clean up, before anything is cleaned`
(checked with `python3 tools/release/release.py check-title`: feat, minor).
After the release the orchestrator's `docs:` pull request adds the
release-history row and the `Last checked with:` stamps; a comment on #90
records the slice and that the confirmed run is the next row; #195 is closed.
<!-- /CP2 -->

## 6. Functional review

Flows 1 to 7 are offline and write nothing into the product clone, in a clone
`S/cand` (`S=$(mktemp -d "$TMPDIR/rc-fr.XXXXXX")`, `git clone --no-hardlinks
<product clone> $S/cand`, `git -C $S/cand remote remove origin`, `export
PYTHONPATH=$S/cand/src`). Flows 8 to 10 need the full environment and run last.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat bb5a016b01c62e551eeb0adf255c36db28d86ca9 HEAD -- src tools tests docs .github scripts .claude` | `retention_alert.py`, `retention_cleanup.py`, `retention_policy.py`, `cli.py`, `tests/test_retention_alert.py`, `tests/test_retention_cleanup.py`, `tests/test_retention_policy.py`, `tests/test_operator_ux.py`, `tools/check_docs.py`, `docs/retention.md`, `docs/exit-codes.md` and the expected bookkeeping under `docs/` only |
| 2 | `python3 -m workflow_manager retention-cleanup --help` | names the preview, the preconditions, the minimum release 2.25.5, that nothing is written and that prune is never part of it |
| 3 | `python3 -c` calling `retention_cleanup.select` on hand-made reports: 12 finished items with folders (limit 10), 7 candidates over a byte limit, a tracked-files entry, only `archives` reached | the oldest first; at most 5; the tracked one skipped with its reason; an empty plan for the last |
| 4 | `grep -n 'prune' $S/cand/src/workflow_manager/retention_cleanup.py` | only text that says prune is never run; no argv carries it |
| 5 | `grep -n 'none can be pruned\|no prunable archive was observed' $S/cand/src/workflow_manager/retention_alert.py $S/cand/docs/retention.md` | both wordings are present, the second for an incomplete report |
| 6 | `python3 $S/cand/tools/check_docs.py` | exit 0 |
| 7 | `grep -n 'set(commands)' $S/cand/tools/check_docs.py`; `cd $S/cand/tests && python3 -B -m unittest test_retention_cleanup.TestCommandNameIsNotAnInternalId`; then in a scratch copy of the clone `sed -i 's/ - set(commands)//' tools/check_docs.py` (the mutation of M35) and run the same test | the grep prints the exemption in `check_pages`; the test passes (OK); in the copy it fails (FAILED) |
| 8 | (full environment) in `$S/cand` apply M1 to M35 with `sed` in scratch copies and run the named tests; first the unmutated copy | the unmutated copy: OK; each mutation: FAILED |
| 9 | (full environment) `python3 tests/run_all.py --select test_retention_cleanup.py`, then `test_retention_alert.py`, `test_retention_policy.py`, `test_retention_status.py`, `test_operator_ux.py`, `test_docs.py` | exit 0 each, no `OrphanProcessError` |
| 10 | (full environment) a scratch managed repository from the newest tested release, a `cleanup` policy adopted and committed, the release's own script untouched and no origin: run `retention-cleanup`; then change a tracked file and run it again | the first: the script's own refusal (no origin), exit 2, nothing written; the second: the uncommitted-change refusal before the script starts, exit 2 |

## 7. Risks

* The preview runs the report, so it costs one forge query per finished item
  and needs `gh` signed in; it says so (1.1) and is bounded by 300 s.
* The selection trusts the report's order (newest first). It is the engine's
  own sort; a test pins it with hand-made reports, and the next row's engine
  calls re-check each item.
* A preview is not a promise: the engine judges again at apply (next row).
* The strict clean-tree rule may refuse an owner who works in the clone; the
  step says to commit or run it from a clean checkout.

## 8. Open decisions

* **O1** minimum Workflow release **2.25.5** (1.4): planned, since older
  engines can end in a traceback mid-removal.
* **O2** an interrupted removal refuses the plan instead of being resumed
  (1.5): planned, because "do not delete `.removing` as clutter" says it needs
  the owner.
* **O3** the cap of 5 items per run and the stop-when-settled rule (2.3), not
  a policy field.
* **O4** the split (this preview first, the confirmed run next): planned by
  the size rule.
