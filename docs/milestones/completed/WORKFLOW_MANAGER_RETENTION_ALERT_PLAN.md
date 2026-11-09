# Workflow Manager: The Retention Alert Evaluation (Revision 5)

`work_item_id: retention-alert` -- `governing_workflow_version: "2.2"`

**Deliverable:** `verify` and `doctor` evaluate the adopted retention
thresholds against the measured retention state and print a retention alert
when one is reached, only for a policy that is adopted with mode `notify` or
`both` (roadmap row 37; #90, wf#84; the four follow-ups of #192 ride along).
Nothing is sent, nothing is cleaned, no exit code changes.

**Work item type:** `process`. **Base commit:** `7810ff6`
(`7810ff66bd7b43b3b0ba60d7fa790cd630fd4732`, tip of `main`, Manager 1.15.0;
Workflow 2.29.0 installed, automatic gates). **Branch:**
`milestone/retention-alert`. **Scope source:** the owner's decisions on #90
(2026-11-03: modes `off | notify | cleanup | both`, "an alert for the owner to
act on") and the row 36 plan's section 2.6 item 1. One mechanism: evaluate the
adopted thresholds against the retention report and say so in `verify` and
`doctor`. Two checkpoints. This changes output for adopted users: a Manager
release follows (`feat`, minor; CP2 says why).

## 1. Investigation (done at `7810ff6`, before any design)

### 1.1 What the retention report carries, per threshold

`retention.fetch(target)` runs the installed script's `report --json` once and
returns a validated report or one `NotAvailable`. The numbers are in
`report["totals"]` (validated integers, 0 to 2**63 - 1):

| Threshold | Measured number | Unit | Reached when |
| --- | --- | --- | --- |
| `finished_items` | the number of `finished[]` entries whose `review_folder.present` is true (finished items beyond the `keep_recent` most recent that still have a review folder) | items | `>=` the limit |
| `finished_folder_mib` | `totals.finished_folder_bytes` | bytes; the limit is MiB, so compare with `limit * 2**20` | `>=` the limit |
| `archives` | `totals.archives` (every archive in the store) | archives | `>=` the limit |
| `prunable_archives` | `totals.prunable` (the script's `age > ttl_days`) | archives | `>=` the limit |

`totals.finished` is not the measured number (LPR1-001): the script counts
every finished item beyond `KEEP_RECENT` whatever its folder state, so an item
that was archived and whose folder was removed still counts, and the owner's
step (archive, then remove) could never lower it: a reached alert would never
clear. Counting the items that still have a review folder (`finished[].
review_folder.present`, a validated boolean) is the number the step lowers, and
it is the same population `finished_folder_bytes` already measures (a removed
folder reports 0 bytes). `docs/retention.md`'s table says "finished work items
with a review folder". An incomplete report is still a lower bound: a folder
the script could not read counts as absent, so the number can only be low.

"At or above" is the rule `docs/retention.md` already publishes for all four, so the limit itself is
reached; the comparison is integer arithmetic. A threshold the policy omits is
not checked.

An INCOMPLETE report (`complete` false, a `read_errors` entry, or a
`query_failed:` item) carries lower bounds (`docs/retention.md`, "If the report
is incomplete"). So a number at or above its limit is **reached** even then (a
lower bound that already reaches the limit is proof), and a number below it is
**unknown**, never within.

### 1.2 When the query is unavailable

`fetch` returns a `NotAvailable(cause, step)` for: no script (Workflow before
2.20.0, or a target that is not a Workflow repository), a script that refuses
(no `origin`, no state file), a timeout (300 s), a malformed report or schema,
every forge query failing. `verify` and `doctor` refuse an unmanaged target
first (exit 2), so that case never reaches the evaluation. Rule: an unavailable
query gives **no alert and one `not evaluated` line with the cause and step**,
only for an adopted `notify`/`both` policy; never an all-clear, never a reached
threshold.

### 1.3 How `verify` and `doctor` render today

* `verify` (`cmd_verify`): clean: one stdout line, exit 0; problems: `N
  problem(s)`, indented lines, one unindented `next:`, exit 1. It has no
  `--retention` option and never starts the script. A release note goes to
  stderr (`workflow-manager: note: ...`).
* `doctor` (`compatibility.render_report`): a `Findings` list whose entries are
  `[blocked]`, `[warning]` or `[note]`; a `blocked` or `warning` finding (an
  incomplete inspection included) is exit 1, notes alone exit 0
  (`doctor_exit_code`, `docs/exit-codes.md`). `doctor --retention` appends the
  retention section after the report.
* So the alert is **not** a doctor `[warning]` finding (that would exit 1). It
  is its own block, `retention alert:`, printed after the existing output (for
  `verify` with problems, before the final `next:`, so the one unindented
  `next:` stays last), to stdout like the `--retention` section; its step
  is an indented `  next:` line.

### 1.4 Exit codes: owner decision O2

Built: **the alert changes no exit code** and `verify` never fails because of
it. A threshold is a reminder, not a defect of the installation, and a `verify`
that exits 1 would break scripts that use `verify <repo> &&`. If the owner wants
`doctor` to exit 1 on a reached threshold, that is a new decision about its
contract (a `doctor_exit_code` input). Not planned.

### 1.5 A cost the owner should know: O1

`verify` today is a local file comparison. For an adopted `notify`/`both`
policy it now also runs the retention script: one forge query per finished
work item (about 20 to 40 seconds for 25 items, 300 s at worst) and it needs
`gh` signed in for a complete answer. A repository without an adopted
`notify`/`both` policy pays nothing: the policy is read first, locally, and the
script is never started. This plan builds it as asked and documents the cost;
a switch to skip the evaluation for one run is a possible later option, not
built here.

## 2. Design

### 2.1 The pure evaluation, `src/workflow_manager/retention_alert.py` (new)

```python
REACHED, WITHIN, UNKNOWN = "reached", "within", "unknown"

@dataclass(frozen=True)
class Result:
    key: str            # a retention_policy.THRESHOLDS key
    status: str         # REACHED, WITHIN or UNKNOWN
    value: int | None   # the measured number (bytes for finished_folder_mib), None without a report
    limit: int          # the policy's number (MiB for finished_folder_mib)
    lower_bound: bool   # the report was incomplete

def alerting(state) -> bool        # state.state == ADOPTED and state.mode in ("notify", "both")
def evaluate(state, report) -> list[Result]
```

`evaluate` is pure: no file, no process, no clock. It returns `[]` unless
`alerting(state)`; otherwise one `Result` per threshold the policy sets, in
`retention_policy.THRESHOLDS` order. With `report` `None` every result is
`UNKNOWN` with `value` `None`. With a report it applies 1.1. It reads
`finished[].review_folder.present` (for `finished_items`), the totals
`finished_folder_bytes`, `archives` and `prunable`, `complete`, `read_errors`
and `not_finished` only.

### 2.2 Gating, once

`alert_lines(target, version, script_state, outcome=None) -> list[str]` loads
the policy (`retention_policy.load`, local). If not `alerting` it returns `[]`
and starts nothing, **and never calls `script_state`** (LPR3-004), so every
other state (`absent` included) is byte-identical to 1.15.0 and pays no
snapshot and no `drift` walk. `script_state` is a zero-argument callable the
caller passes, which `alert_lines` calls only after the policy is alerting and
inside its one exception boundary (below). Otherwise, **the script is never
started by the alert when it is not the release's** (LPR1-003): `verify` is
the integrity check and must not execute a file it has just reported as
modified. The callable returns `SCRIPT_OK`, `SCRIPT_MODIFIED` or
`SCRIPT_UNCHECKED`, constants of `retention_alert`.

* **The one rule (LPR2-005, LPR3-001).** `retention_alert.script_state(target,
  release)` returns `SCRIPT_OK` only when all three hold: the release
  manifest's installable artifacts for the recorded profile list
  `scripts/workflow_retention.py`; the installation record lists it as
  managed; and `install.drift(target, release)` (the `Drift` objects, never the
  `install.verify` strings) reports nothing for that path. Any other case is
  `SCRIPT_MODIFIED`: `modified`, `missing`, `not-executable` and `unexpected`
  included, and the script missing from the record (an installation
  bootstrapped before 2.20.0 and never updated, or a record edited by hand)
  with a file in the tree, for which `drift` reports `unexpected` or nothing
  at all. One case stays outside the rule: a release whose manifest has no
  script **and** no such file in the tree (a Workflow before 2.20.0, or a
  target that is not a Workflow repository) is `SCRIPT_OK`, and `fetch` gives
  its existing "no script" `NotAvailable`: nothing runs. The same release
  with a file in the tree is `SCRIPT_MODIFIED`: an arbitrary file is never run.
* **`cmd_verify`** passes `lambda: retention_alert.script_state(args.target,
  release)` with its own release (`_release_for_target(args)`, the one it
  already compares against, `--release-version` included, as `verify` does
  today); `install.verify` and the alert share that release, and `drift` is
  walked a second time only for an alerting policy. **The alert is computed
  inside `with release:` (LPR4-001).** The release is a `SnapshotRelease` whose
  `close()` removes its directory, and `install.drift` reads release files
  (`_merged_drift` reads the `.gitignore` and `CLAUDE.md` templates), so a
  `script_state` run after the `with` exits would raise `FileNotFoundError` on
  every `verify` of a healthy installation. `cmd_verify` therefore calls
  `retention_alert.alert_lines(...)` right after `verify(...)` and
  `_note_release_needs(...)`, still inside the `with`, keeps the returned
  lines, and prints them afterwards where 2.5 places them (after the result
  lines, before the problems branch's `next:`). The release is held open for
  the duration of the report query (bounded by the 300 s timeout, 1.5), and
  only for an alerting policy; no other state reaches the call.
* **`cmd_doctor` (LPR2-001)** judges the **installed** release, never the update
  candidate: its `release` (`--release-version` names the candidate) is not
  used for this check. It resolves the installed release exactly as
  `_installed_resolves` does, read-only through the `destinations` it already
  built: `_cache(args, _pins()).resolve(installed, snapshot_parent=
  destinations.snapshot_parent, read_only=True)`, then `install.drift(target,
  that release)`, inside a zero-argument callable (`cli._installed_script_state`)
  that `cmd_doctor` passes as `script_state`. The callable runs `drift` inside
  the `with` of its own resolution (`with _cache(...).resolve(...) as
  installed_release:`), never after `close()` (LPR4-001): `cmd_doctor`'s own
  `with release:` has already exited by the time the alert is printed, which is
  why the callable resolves for itself, so a repository without an
  alerting policy resolves nothing a second time and an exception of the
  resolution stays inside the one boundary (LPR3-004). For an alerting policy
  the installed release is resolved once more than `_installed_resolves` did
  (a read-only cache hit): reusing that handle is not done because it has
  been closed by then, and the price is paid only by the repository that
  asked for the alert. `--release-dir` and `--manager-root` are not consulted
  (the same limit `_installed_resolves` documents), and nothing is resolved
  through the default temporary directory. When the installed release does not resolve
  (`RELEASE_ERRORS`, or a record that names no cache entry) the flag is
  `SCRIPT_UNCHECKED` and the alert prints `retention alert: not evaluated: the
  installed release cannot be checked` with `  next: run the command again
  with the network, or with WORKFLOW_MANAGER_RELEASE_SOURCE set to a mirror`.
* `SCRIPT_MODIFIED` prints `retention alert: not evaluated: the installed
  scripts/workflow_retention.py does not match the release` with `  next:
  workflow-manager update TARGET --force` (also for a script the record does
  not list or one that is `unexpected`). In both non-OK cases the alert starts
  nothing: no `fetch`, and an `outcome` passed in is ignored.
* Otherwise (`SCRIPT_OK`) it uses `outcome` when the caller already fetched,
  else `retention.fetch`, then `evaluate`, then renders (2.3).

**`doctor --retention` (LPR2-002).** Decided: the `--retention` *section* is
unchanged from 1.15.0 in every policy state: it always runs the script and
renders its report, exactly as `status --retention` does (untouched). The
alert alone refuses a modified script. `cmd_doctor` fetches once for the
section (`retention.section(target, version, outcome=...)`, the new optional
argument) and passes the same `outcome` to `alert_lines`, which uses it only
for `SCRIPT_OK`. So `doctor --retention` makes **one** script call in every
case, and `doctor` without `--retention` makes none when the script is not OK.
(This keeps "every other state is byte-identical to 1.15.0" true for the
section, and makes no claim about the section that `status --retention` would
then contradict.)

**The test seam (LPR3-002, LPR4-002).** A stub script cannot be the release's
script, so a stub-based test never reaches `SCRIPT_OK` through the real rule.
Two layers: `retention_alert.script_state` and `cli._installed_script_state`
are module-level functions the stub-based cases (`TestGate` notify/both,
`TestOutput`, `TestExitCodes`, `TestNextStep`, `TestNothingElse`, the
`doctor` positive cases, and `TestUnavailable` except the case named there)
replace with `unittest.mock.patch` to return `SCRIPT_OK`. A patch does not
reach a child process, and `Scratch.invoke` runs `python -m workflow_manager`
as one (`run`/`run_in`, `tests/test_operator_ux.py`), so **the stub-based cases
call `cli.main(argv)` in-process**: a helper of `tests/test_retention_alert.py`
(`Scratch` itself is untouched) runs `cli.main` with `os.environ` replaced by
`pinned_env(...)` (`unittest.mock.patch.dict(os.environ, env, clear=True)`),
`contextlib.redirect_stdout`/`redirect_stderr` capturing the streams, and the
exit code taken from the return value or a `SystemExit`, as
`tests/test_retention_policy.py` and `tests/test_read_only.py` already do.
The stub script is still started by `retention.fetch` as a child process, so the
marker-file proof is unaffected. Every stub-based case asserts that the patched
seam was consulted (the mock's `call_count` is 1 for an alerting state, 0
otherwise), so a seam that is never reached fails the case instead of being
rewritten into one. What the seam leaves untested is the rule itself, tested
separately and for real, **in subprocesses**, by `TestScriptState` (section 4)
against a release of the cache that ships the script (the newest tested
release, at least 2.20.0), in a scratch installation of it, where the script is
the release's, a modified one, an `unexpected` one, one the record does not
list, and a missing one, with nothing patched. A `doctor` positive case also
asserts that the evaluation was reached (the marker file records the call).

One boundary catches any exception of its own, `script_state` included, and
returns the `not evaluated`
form with the exception's class name, so the alert never changes an exit code
(`KeyboardInterrupt` is not caught). `status` is not touched.

### 2.3 What is printed

All lines are stdout, after the command's own output:

```
retention alert: 2 of 4 thresholds reached (mode notify, policy 1a2b3c4d5e6f)
  finished items: 12, limit 10: reached
  finished folders: 612 MiB, limit 500 MiB: reached
  archives: at least 5, limit 20: not known (the report is incomplete)
  next: in the repository, run `python3 -I scripts/workflow_retention.py archive ID --apply` (run it without `--apply` first for a dry run); ...
```

* At least one `REACHED`: the header and one line for each reached or unknown
  threshold (a `within` one is not listed), then `next:`. A lower-bound number
  reads `at least N`.
* At least one `REACHED` and the report incomplete (LPR1-004): the `next:` joins
  the reached causes' steps (2.4) with `retention.STEP_INCOMPLETE`, in that
  order, each once, with `; `; the unknown lines carry the lower-bound reading.
* None reached and at least one `UNKNOWN`, or no report: one line
  `retention alert: not evaluated: CAUSE` and `  next: STEP`. CAUSE is the
  fetch refusal's text, or `the retention report is incomplete (the numbers
  are lower bounds)` with the step `fix what is named, then run the command
  again` (`retention.STEP_INCOMPLETE`). Two causes were considered and
  rejected: silence (a false all-clear) and a doctor `[warning]` (an exit
  code). O3: this is the one line printed beyond "a threshold is reached".
* All thresholds `WITHIN`: nothing, byte for byte.

MiB is `bytes // 2**20` (floor, so a within value never prints as the limit).
Cause and step text come from `retention` (validated, control-free); nothing
else is echoed.

### 2.4 The next step, by cause

The commands are the user-only ones, named, never run:

* `finished_items` or `finished_folder_mib` reached: `retention.next_step(report,
  version, target)` (archive first, then remove, then resume an interrupted
  removal, with the update step when the Workflow release lacks the command).
  With an incomplete report the step is this one **joined with**
  `retention.STEP_INCOMPLETE` (2.3), never `STEP_INCOMPLETE` alone.
* `prunable_archives` reached: `in the repository, run `python3 -I
  scripts/workflow_retention.py report` to list the prunable archives, then
  `python3 -I scripts/workflow_retention.py prune ID --apply` for each` (the
  report's `archives` list is not validated by the Manager, so ids are not
  quoted here); a Workflow release before 2.24.0 gets the update step.
  `PRUNE_FROM = (2, 24, 0)` is a new constant in `retention.py` beside
  `ARCHIVE_FROM` and `REMOVE_FROM` (LPR1-002), so the capability is judged by the
  recorded release in one place.
* `archives` reached: the prune step above when `totals.prunable > 0`; else
  `no archive is past the time to live yet, so none can be pruned: raise
  thresholds.archives in the policy if the store is meant to be this large, then
  adopt it again` (adoption command named).

Steps of different causes join with `; `, each once.

### 2.5 Wiring, `cli.py`

`cmd_verify` and `cmd_doctor` print `retention_alert.alert_lines(target,
version, script_state, ...)`: in
`cmd_verify` after the result lines and before the problems branch's `next:`; in
`cmd_doctor` after the report and the `--retention` section. Their help text
gains one sentence (adopted `notify`/`both`: runs the retention report and
warns; never changes the exit code). The usage docstring is unchanged.

### 2.5a The prune text the section and the page still carry (LPR1-002)

`retention.render` prints `prunable archives get no command yet: the Workflow has
none for them` and `docs/retention.md` says the Workflow has no command to prune
them yet. Since Workflow 2.24.0 `prune` exists and the alert names it, so
`doctor --retention` would contradict itself. CP1 changes both: with
`PRUNE_FROM` met by the recorded release the section's line names the command itself (LPR3-003): `prunable archives:
python3 -I scripts/workflow_retention.py prune ID --apply removes one (run
`report` to list them)`. It does not point to "the next step": the section's
`next:` is `retention.next_step`, which names only `archive` and `remove` (or
`nothing to archive`), and stays as today, so the line is complete without it
(`status --retention`, which never prints the alert, and `doctor --retention`
without an alerting policy print the same line). Below
2.24.0 the line reads `prunable archives: this Workflow release has no prune
command: workflow-manager update` (LPR2-004: one line per side of `PRUNE_FROM`,
the old `get no command yet` wording is gone on both); the page paragraph says
the same by release. `tests/test_retention_status.py` pins both lines, one test
per side, for `status --retention` and `doctor --retention` (M32, M35).
Its other expectations move with it, and `retention.py` therefore also changes `render` and gains
`PRUNE_FROM` (CP1's Files list names it).

### 2.6 The four #192 follow-ups (same files)

1. Help text: the `adopt-retention-policy` exit-2 list also names ".workflow-manager
   is a link" and "the record path is not a regular file", as
   `docs/exit-codes.md` does.
2. The `invalid` state's step (`retention_policy.block`) and the refusal step of
   `usable_policy` name the command: `... then run workflow-manager
   adopt-retention-policy TARGET to preview it`.
3. `check_record` parses `adopted_at` with `datetime.strptime(v,
   "%Y-%m-%dT%H:%M:%SZ")` after the full match; an impossible date
   (`2026-99-99T99:99:99Z`, `2026-02-30T00:00:00Z`, hour 24) is a problem. A leap
   second (`:60`) is accepted by `strptime`; not chased.
4. `_write_atomically` opens the parent directory (`O_RDONLY | O_DIRECTORY`),
   `os.fsync`s it after `os.replace`, closes it; an `OSError` there is ignored
   (the record is already in place; a failed durability sync must not report a
   failed adoption). The temporary-file clean-up path is unchanged.

5. (LPR1-005) Two "only reads the policy" texts become true again:
   `retention_policy.block`'s `this Manager release only reads the policy: it
   sends nothing and cleans nothing` and the `adopt-retention-policy` help's
   `This release only reads the policy: it archives, removes, prunes and sends
   nothing` now say the Manager reads the policy and, for `notify`/`both`,
   evaluates its thresholds in `verify` and `doctor`; it still sends nothing,
   cleans nothing and decides nothing for the owner. Two more places carry the
   same claim (LPR2-003) and are reworded the same way: `cmd_adopt_retention_policy`'s
   success output (`cli.py:934`, `this Manager release only reads the policy:
   nothing is archived, removed, pruned or sent`) and the example block in
   `docs/retention.md` (line 140) that prints `block`'s line (it moves with
   `block`). `grep -rn "only reads" src docs/retention.md` finds none of the
   old claim afterwards (LPR3-005). Two matches elsewhere remain on purpose:
   `docs/ACTIVE_MILESTONE.md` (rewritten by this item's bookkeeping, not a
   deliverable) and
   `docs/milestones/completed/WORKFLOW_MANAGER_RETENTION_POLICY_FILE_PLAN.md`
   (a completed plan, historical and never edited).

### 2.7 Documentation

`docs/retention.md`: a section "The retention alert" (when it prints, the
example, the outcomes, 1.1, 1.5, 2.4, "never changes an exit code"); the table's
`finished_items` wording (1.1); the prune paragraph (2.5a); the policy
section's "This release only **reads** the policy ... A later release evaluates
the thresholds" becomes true (cleanup and the sender stay "a later release").
`docs/verify.md`: a paragraph on the alert and its cost. `docs/exit-codes.md`: a
row beside the `--retention` one. No page names a milestone id; the `Last
checked with:` stamps move in the `docs:` follow-up.

### 2.8 Not in this slice

The notification sender (the Controller lane's SignalHub interface: an owner
decision), the automatic cleanup run, the ttl and keep-recent fields, any change
to `archive`, `remove` or `prune`, `status` printing the alert, a skip switch.

## 3. Failure-only mutations

Each on a fresh copy, one at a time, the named test run alone from `tests/`
(`python3 -B -m unittest`): the unmutated copy passes, each mutation fails.

| # | Mutation | Must fail |
| --- | --- | --- |
| M1 | `>=` becomes `>` in the comparison | `TestEvaluate` at the limit is reached |
| M2 | the MiB limit is compared with `limit * 10**6` bytes, or the bytes are compared with the MiB limit | `TestEvaluate` folder at and one byte below the limit |
| M3 | an incomplete report below the limit is `WITHIN` | `TestEvaluate` incomplete below is unknown |
| M4 | an incomplete report at or above the limit is `UNKNOWN` | `TestEvaluate` incomplete at limit is reached |
| M5 | `alerting` accepts mode `cleanup` or `off` | `TestGate` mode matrix (no script call, no lines) |
| M6 | `alerting` accepts `changed`, `not-adopted`, `record-invalid`, `invalid` or `file-missing` | `TestGate` state matrix |
| M7 | a threshold the policy omits is evaluated | `TestEvaluate` omitted threshold |
| M8 | an unavailable query prints nothing, or an all-clear, or a reached line | `TestUnavailable` each cause prints one `not evaluated` line with cause and step |
| M9 | all thresholds within prints a line | `TestOutput` within prints nothing |
| M10 | the alert makes `verify` or `doctor` exit non-zero | `TestExitCodes` reached keeps 0 and 1 |
| M11 | the script is started when the policy is not alerting | `TestGate` marker file has no call |
| M12 | `doctor --retention` fetches twice | `TestOutput` one script call |
| M13 | `alert_lines` has no exception boundary | `TestUnavailable` an evaluation that raises prints `not evaluated` and keeps the exit code |
| M14 | the alert runs a second script command (`archive`, `remove`, `prune`) | `TestNothingElse` exactly one `report --json` call, tree unchanged |
| M15 | the alert prints before the problems, or its `next:` is unindented | `TestOutput` verify with problems keeps one unindented final `next:` |
| M16 | `archives` reached with nothing prunable names `prune` | `TestNextStep` by cause |
| M17 | the `prune` step is offered to a Workflow release before 2.24.0 | `TestNextStep` capability |
| M18 | a failed path writes (a not-evaluated verify or doctor changes the target) | `TestUnavailable` no-write proof per cause (`tree_hash`) |
| M19 | the help text drops the two refusals | `TestFollowUps` help assertion |
| M20 | the `invalid` step (either place) drops the command | `TestFollowUps` step wording |
| M21 | `strptime` is removed | `TestFollowUps` impossible dates |
| M22 | the directory fsync is removed | `TestFollowUps` directory fd is synced after the replace |
| M23 | a failing directory fsync raises | `TestFollowUps` failure there does not mask the write |
| M24 | `finished_items` reads `totals.finished` | `TestEvaluate` archived-and-removed items do not count |
| M25 | the section prints `no command yet` at a release with `PRUNE_FROM` met | `TestOutput` `doctor --retention` carries no contradictory line |
| M26 | the script is started although `verify` reported it modified | `TestUnavailable` modified script (no marker call) |
| M27 | an incomplete report with a reached threshold gets only `STEP_INCOMPLETE`, or only the threshold's step | `TestNextStep` joined step |
| M28 | the stale "only reads" wording stays in `block`, the help, the adoption output or the docs example | `TestFollowUps` wording, `TestDocs` |
| M29 | `cmd_doctor` checks the script against the update candidate (`_release_for_target` / its `release`) instead of the installed release | `TestScriptState` `doctor --release-version <other>` on an untouched installation still evaluates (nothing patched; LPR4-003) |
| M30 | `cmd_doctor` never passes `SCRIPT_MODIFIED`, or `doctor --retention` hands the section's outcome to the alert although the script is modified | `TestUnavailable` `doctor` (no marker call) and `doctor --retention` (one call) with a modified script |
| M31 | an unresolvable installed release is treated as `SCRIPT_OK`, or resolves through the default temporary directory | `TestUnavailable` the `installed release cannot be checked` line; no write outside the destinations |
| M32 | the prunable line is the same on both sides of `PRUNE_FROM` | `test_retention_status.py` one test per side |
| M33 | a script `unexpected` in `drift`, or one the installation record does not list, is `SCRIPT_OK` | `TestScriptState` unexpected and unlisted script (no marker call in `verify`, `doctor`) |
| M34 | `script_state` is called before `alerting` holds (every `doctor` and `verify` pays the snapshot and the `drift` walk), or outside the exception boundary | `TestGate` a counting `script_state` is not called for a non-alerting state; `TestUnavailable` a `script_state` that raises prints `not evaluated` and keeps the exit code |
| M35 | the section's prunable line at `PRUNE_FROM` points to "the next step" or omits the command | `test_retention_status.py` the line names `python3 -I scripts/workflow_retention.py prune ID --apply` in `status --retention` and `doctor --retention` |
| M36 | `verify` or the doctor callable computes the script state after the release is closed (LPR4-001) | `TestScriptState` the release's own untouched script through `verify` and `doctor`: moving the call out of `with release:` (or out of the callable's own `with`) makes the run print `not evaluated: FileNotFoundError` instead of the real script's line |
| M37 | a stub-based case runs the command in a child process, so the patched seam is never consulted and the real rule answers `SCRIPT_MODIFIED` (LPR4-002) | every stub-based case asserts the mock's `call_count`; a case that returns to a subprocess fails it |

## 4. Tests

New `tests/test_retention_alert.py`, reusing `Scratch`, `finished` and `report`
from `tests/test_retention_status.py` (hermetic: the stub script, no network;
the stub-based cases reach `SCRIPT_OK` through the patched seam of 2.2, and
`TestScriptState` tests the real rule).
The #192 cases are a class `TestFollowUps` in `tests/test_retention_policy.py`.

* **TestEvaluate** (pure, no process): finished items whose folders were
  archived and removed (`review_folder.present` false) do not count toward
  `finished_items`, while `totals.finished` stays high; each threshold at the limit, one below,
  one above; the folder at `limit * 2**20` and one byte under; an incomplete
  report below (unknown, `lower_bound`) and at or above (reached); a policy
  omitting a threshold; `None` report; a non-alerting state returns `[]`.
* **TestScriptState** (LPR3-001, LPR3-002; the newest tested release from the
  primed cache, a scratch installation of it, hermetic after priming): the
  release's own script is `SCRIPT_OK`; modified, missing, not executable,
  `unexpected` (the manifest has it, the record does not list it) and a script
  the record does not list are each `SCRIPT_MODIFIED`; a release whose manifest
  has no script is `SCRIPT_OK` with no file in the tree and `SCRIPT_MODIFIED`
  with one; each through `verify` and `doctor` with a marker stub: no call.
  These run in subprocesses with nothing patched (LPR4-002). Added (LPR4-001):
  the release's own, untouched script through `verify` and `doctor` **reaches
  the evaluation**: the output is the real script's own report or its own
  refusal line (the scratch repository has no forge), never `does not match`
  and never an exception class name (`FileNotFoundError`). Added (LPR4-003):
  `doctor --release-version <other release>` on the same untouched
  installation (the scratch cache holds a second release whose script differs)
  still evaluates by the real script's own line: M29 fails exactly when
  `doctor` judges against the candidate.
* **TestGate**: with the stub (seam patched to `SCRIPT_OK`), a counting
  `script_state` that a non-alerting state never calls (LPR3-004), the mode matrix (`off`, `cleanup`: no lines, the
  marker file records no call) and the state matrix (every non-adopted state);
  `notify` and `both` run the script once.
* **TestOutput**: the exact lines for one reached, several, a lower bound;
  within prints nothing and equals the run with no policy, byte for byte;
  `verify` clean and with problems (one unindented final `next:`); `doctor` and
  `doctor --retention` (one script call, and the marker proves a `doctor`
  positive case reached the evaluation), and with prunable archives reached no
  "no command" line next to the alert's `prune` step (2.5a).
* **TestUnavailable**: no script, a refusing script, malformed, timeout lowered,
  an evaluation that raises, a `script_state` that raises, and a `verify` whose installed
  `scripts/workflow_retention.py` is modified (the marker file records no
  call, the line says it does not match the release), the same for `doctor`
  (no call) and `doctor --retention` (exactly one call, the section's; the
  section output equals 1.15.0's), and an installed release that
  does not resolve (the line `not evaluated: the installed release cannot be
  checked`; nothing written outside the destinations): each one `not evaluated` line with cause and step,
  the exit code of the run without the policy, `tree_hash` of the target
  unchanged (the no-write proof of each failure path). The timeout case stubs `retention.fetch`
  to return the timeout refusal in-process (LPR1-006): the real 300 s path and
  its process-group clean-up stay covered by `test_retention_status.py`, and the
  stub's `sleep` mode, which starts a grandchild, is not used here, so no
  re-parented child can fail the gate with `OrphanProcessError`.
* **TestExitCodes**: a reached threshold with a clean installation (`verify` 0,
  `doctor` as without the policy) and a problem-carrying one (`verify` 1).
* **TestNextStep**: archive, remove, prune, the archives-without-prunable text,
  the update step by recorded Workflow release; an incomplete report with a
  reached threshold joins the threshold's step with `STEP_INCOMPLETE`.
* **TestNothingElse**: one `report --json` call; nothing outside the stub's
  marker changes; the alert never starts an `archive`, `remove` or `prune`.
* **TestFollowUps**: the four #192 cases; the help, `block`, adoption-output and docs-example wording assertions (LPR1-005, LPR2-003) pin the new text; the help assertion also pins
  `verify` and `doctor` naming the alert.
* **TestDocs**: the section and the exit-codes sentence exist; no page names a
  work item id. `test_operator_ux.py` is unchanged (no new command).
* `tests/test_retention_status.py`: the prunable line on each side of `PRUNE_FROM` (LPR2-004), and at or after it the line names `python3 -I scripts/workflow_retention.py prune ID --apply` in `status --retention` and in `doctor --retention` (LPR3-003).

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The alert: evaluation, verify and doctor wiring, tests, docs | - | 3 | 1 |
| CP2 | The #192 follow-ups, bookkeeping and the release | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the alert: evaluation, verify and doctor wiring, tests, docs

**Files:** `src/workflow_manager/retention_alert.py`, `src/workflow_manager/retention.py`, `src/workflow_manager/cli.py`, `tests/test_retention_alert.py`, `tests/test_retention_status.py`, `docs/retention.md`, `docs/verify.md`, `docs/exit-codes.md`.

Sections 2.1 to 2.5a, 2.7 and the tests of section 4 except `TestFollowUps`.
`retention.py` gives `section` an optional `outcome` argument (so `doctor
--retention` runs the script once; the section itself is not gated, 2.2), adds `PRUNE_FROM` and
rewords `render`'s prunable line (2.5a); `tests/test_retention_status.py`
follows. Then, in order: mutations M1 to M18, M24 to M27 and M29 to M37, `python3 tools/check_docs.py`, `python3
tests/run_all.py --select test_retention_alert.py`, `--select
test_retention_status.py`, `--select test_retention_policy.py`, `--select
test_operator_ux.py` and `--select test_docs.py`.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the #192 follow-ups, bookkeeping and the release

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_policy.py`.

Section 2.6 (items 1 to 5) and `TestFollowUps`, mutations M19 to M23 and M28, then the full gate
`python3 tests/run_all.py`. Row 37 of docs/ROADMAP.md (Current; Done at acceptance) and
docs/ACTIVE_MILESTONE.md record the item and the mutation results; both are
excluded at both stages, not deliverables. No version is edited. The PR title is `feat: warn in verify and doctor when an
adopted retention threshold is reached` (checked with `python3
tools/release/release.py check-title`: feat, minor). It is `feat`, not `fix`,
because an adopted `notify`/`both` policy now changes what `verify` and `doctor`
print and makes them query the forge; a repository without such a policy sees
byte-identical output. After the release, the orchestrator's follow-up `docs:`
pull request adds the release-history row and moves the `Last checked with:`
stamps of the three pages; a comment on #90 records the slice and the remaining
rows; #192 is closed by this item.
<!-- /CP2 -->

## 6. Functional review

Flows 1 to 7 are offline and write nothing into the product clone, in a clone
`S/cand` (`S=$(mktemp -d "$TMPDIR/ra-fr.XXXXXX")`, `git clone --no-hardlinks
<product clone> $S/cand`, `git -C $S/cand remote remove origin`,
`export PYTHONPATH=$S/cand/src`). Flows 8 to 10 need the full environment (a
release cache) and run last.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat 7810ff66bd7b43b3b0ba60d7fa790cd630fd4732 HEAD -- src tools tests docs .github scripts .claude` | `src/workflow_manager/retention_alert.py`, `retention.py`, `retention_policy.py`, `cli.py`, `tests/test_retention_alert.py`, `tests/test_retention_policy.py`, `tests/test_retention_status.py`, `docs/retention.md`, `docs/verify.md`, `docs/exit-codes.md`, and the expected bookkeeping under `docs`: the bookkeeping under `docs` (roadmap, active milestone, state, the plan's registry, mapping, artifacts and dispositions files, findings record, checklist); nothing in `scripts/`, `.claude/`, `.github/`, `tools/` or `tests/parallel/` |
| 2 | `grep -n '^class Test' $S/cand/tests/test_retention_alert.py` | `TestEvaluate`, `TestScriptState`, `TestGate`, `TestOutput`, `TestUnavailable`, `TestExitCodes`, `TestNextStep`, `TestNothingElse`, `TestDocs`; `TestFollowUps` is in `tests/test_retention_policy.py` |
| 3 | `grep -n 'retention alert' $S/cand/docs/retention.md $S/cand/docs/verify.md $S/cand/docs/exit-codes.md`; `grep -n 'retention-alert' $S/cand/docs/retention.md $S/cand/docs/verify.md $S/cand/docs/exit-codes.md` | the first matches in all three pages; the second matches nothing |
| 4 | `python3 -m workflow_manager adopt-retention-policy --help`, `verify --help`, `doctor --help` | the first names the link and the non-regular-file refusals; the other two name the alert and say it never changes the exit code |
| 5 | `python3 -c` calling `retention_alert.evaluate`: an adopted `notify` state with hand-made reports (10 `finished[]` entries with a present folder, limit 10; 9; 10 entries of which 2 have no folder; 524288000 and 524287999 folder bytes, limit 500; an incomplete report with 9), then an adopted `cleanup` state and a `changed` state | reached; within; within; reached and within; unknown; an empty list each for the last two |
| 6 | `python3 -c` with `retention_policy.check_record` on a record whose `adopted_at` is `2026-99-99T99:99:99Z`, then `2026-02-30T00:00:00Z`; and `retention_policy.block` of an `invalid` state | a problem for each date; the step names `workflow-manager adopt-retention-policy` |
| 7 | `python3 $S/cand/tools/check_docs.py` | exit 0 |
| 8 | (full environment) in `$S/cand` apply M1 to M37 with `sed` in scratch copies and run the named tests; first the unmutated copy | the unmutated copy: OK; each mutation: FAILED |
| 9 | (full environment) `python3 tests/run_all.py --select test_retention_alert.py`, then `test_retention_policy.py`, `test_retention_status.py`, `test_operator_ux.py`, `test_docs.py` | exit 0 each, no `OrphanProcessError` |
| 10 | (full environment) a scratch managed repository installed from a release that ships the script (the newest tested one, at least 2.20.0) with an adopted `notify` policy (limit 1), the script untouched: `workflow-manager verify` and `doctor`; then replace `scripts/workflow_retention.py` with a stub that writes a marker file and reports 2 finished items, and run both again; then delete the stub | untouched: the script's own answer (the alert block, or one `not evaluated` line carrying the script's own refusal, as the scratch repository has no forge), exit as without the policy; with the stub: one `not evaluated` line saying the script does not match the release, `next: workflow-manager update TARGET --force`, no marker file, exit as without the policy (`verify` still reports `modified`); stub removed: the `missing` problem and the same line |

## 7. Risks

* A forge query on every `verify` and `doctor` of an adopted `notify`/`both`
  repository (1.5, O1): documented, bounded by the 300 s timeout.
* The report's `archives` list is not validated by the Manager, so the prune
  step names a placeholder id; validating it is a later change.
* The alert is not a `[warning]` finding; the page says so.
* `finished_items` counts folders still present, not `totals.finished` (1.1): a
  policy limit means "this many finished items still hold a review folder".

## 8. Open decisions

* **O1** the cost in 1.5: built as asked (the evaluation runs in `verify` and
  `doctor`); a skip switch is a follow-up if the owner wants one.
* **O2** an exit code for a reached threshold: planned without (1.4).
* **O3** the `not evaluated` line (2.3): planned, because "say why" needs it.
* The notification target (the sender) stays the owner's, with the Controller
  lane.
