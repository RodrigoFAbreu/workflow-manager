# Workflow Manager: The Unattended Retention Cleanup Run and Its Audit File (Revision 5)

`work_item_id: unattended-retention-run` -- `governing_workflow_version: "2.2"`

Pull request title: `feat: run the retention cleanup unattended under the adopted unattended policy, with an audit file`

**Deliverable:** step A2 of the three unattended-retention steps of issue #254:
`workflow-manager retention-cleanup TARGET --unattended` runs the
archive-and-remove cleanup **without the per-plan `--confirm` sentence**, under
the authority the owner gave once with the unattended adoption sentence (A1,
Manager 1.21.0), keeps every safeguard of the confirmed run, adds the
Manager-side `keep_recent`, writes one audit line per action and per
refusal/stop outside the repository, and can print its result as one JSON
document. **Prune is not part of this item** (A3): no unattended run issues
`prune`, and the closed argv forms of the run stay three.

**Work item type:** `process`. **Base commit:** `73a5a7212b26238dd8a36a45c7a970c8518b3f52`
(tip of `main`; Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/unattended-retention-run`, bound by the Controller. **Scope source:**
issue #254 (the owner's request and the design comment of 2026-11-18, option A)
and the work-item prompt; #259 (A1's follow-ups) is **not** taken. The title is
a `feat:` change: the Manager releases a minor
(`python3 tools/release/release.py check-title` reads `valid title: feat,
release impact minor`); the Controller waits for the release. **Manager only**:
no Workflow release is needed, no pin changes, nothing under `.claude/`,
`scripts/`, `.workflow-manager/` or the managed documents of `docs/ai-workflow/`
is edited. No scheduler and no notification is added: the lane heartbeat step
comes later. **ROADMAP:** row 51 (A2 of the three unattended retention items,
#254) is added in the style of row 50 with status Current, and the last
checkpoint marks it Done in the item's own wording; the Controller runs
acceptance itself and will not edit the row.

## 1. Verification on current main (`73a5a72`)

Each point of the work-item specification was checked against the code.

* **(1) Authority.** `PolicyState.unattended` exists
  (`src/workflow_manager/retention_policy.py:96`, set by `_load` at `:450` only
  in the `adopted` state, for a file with the key and a record whose
  confirmation holds the unattended sentence). No consumer exists yet.
  `retention_cleanup.preflight` (`retention_cleanup.py:178`) refuses a policy
  that is not `adopted` (`_policy_refusal`, `:159`, one named cause per state:
  absent, invalid, not-adopted, record-invalid, changed) and a mode other than
  `cleanup`/`both` (`:189`). The two policy cross rules of A1
  (`retention_policy.py:222-224`) already make an `unattended` file carry mode
  `cleanup` or `both`; the check is repeated here because the authority must not
  depend on a rule of another module. **TRUE-FIX-NEEDED.**
* **(2) Preflight, selection, cap, tracked folders, re-read.** Already in code
  and kept untouched: both policy files at HEAD with the adopted bytes (`:196`),
  no tracked change (`:207`), release 2.25.5 or later (`:216`), the installed
  script is the release's own (`:230`), one report that is complete with no
  interrupted removal (`:243-258`); selection oldest-first with `CAP = 5`
  (`:28`, `select` `:309`); a folder holding tracked files is skipped
  (`_eligible`, `:299`); `retention_run.run` re-reads the policy before each
  item (`retention_run.py:206`) and stops the run on a change; the first failed
  step stops the run (`:227`). **Already satisfied; only the re-read needs one
  more condition** (the adoption must still authorise unattended: the policy's
  digest does not cover the adoption record, so a record swapped for an
  ordinary-only one keeps the digest, see 2.4).
* **(3) `keep_recent`.** Not in code. The engine's report already splits the
  newest `KEEP_RECENT = 3` merged items into `kept_recent` and lists the rest,
  newest first, in `finished` (`scripts/workflow_retention.py:514-518`; the
  Manager reads both through `retention.fetch`, which requires the integer
  `keep_recent`, `retention.py:249`). The policy's `unattended.keep_recent`
  (3 to 100000) counts those three too, so **the Manager's extra skip is
  `keep_recent - report.keep_recent` entries from the newest end of
  `finished`**. **TRUE-FIX-NEEDED.**
* **(4) Dry-run equivalence.** `plan_digest` (`:372`) hashes the repository,
  the policy digest and the ordered `[id, action]` pairs. If `keep_recent`
  changed the plan of the unattended run only, the preview would show a
  different plan from the one that runs, which is exactly what equivalence
  forbids. **Forced refinement (2.2):** `select` applies `keep_recent` whenever
  the state authorises unattended cleanup, for the preview, the confirmed run
  and the unattended run alike, so there is one plan and one digest rule.
* **(5) Audit.** Nothing in code writes outside the repository except the
  engine. The existing run emits only to stdout. **TRUE-FIX-NEEDED.**
* **(6) `--json`.** `retention_alert_json.py` is the Manager's one JSON
  document writer; the retention-cleanup command has none. **TRUE-FIX-NEEDED.**
* **(7) Text.** `retention_policy.NOT_ENFORCED` (`:237`) is printed by
  `unattended_lines` (`:241`) for `status`, `doctor`, the adopt preview and the
  `retention-cleanup` preview; A1's tests (`tests/test_retention_unattended.py`)
  and `docs/retention.md` pin it. **TRUE-FIX-NEEDED.**
* **Manager only.** Every requirement is met with the engine's existing
  `archive --apply`, `remove` (dry run) and `remove --apply` verbs and the
  `report` the preflight already runs; nothing needs a Workflow release, so
  there is no STOP finding.

## 2. Design

One mechanism: **the unattended run is the confirmed run with the per-plan
sentence replaced by the recorded, digest-bound adoption, and with a durable
record of what it did.** Principle: the run adds authority and evidence, never
new actions.

### 2.1 Authority (CP1, CP3)

`retention-cleanup TARGET --unattended` is refused, with a named cause and one
`next:` step, exit 2, **nothing written in the repository, no engine verb
issued**, unless the state the preflight read authorises it. The checks are, in
order (the existing preflight order is kept; the new check is step 2b, after the
policy is known adopted with a cleanup mode and before anything that starts a
process):

| Order | Condition | Cause (after `retention cleanup: `) |
| --- | --- | --- |
| a | `--confirm` given together with `--unattended` | `--confirm and --unattended cannot be combined (the per-plan sentence and the adopted unattended policy are two authorities)` |
| b | `--json` without `--unattended` | `--json is for the unattended run` |
| b2 | the target is not managed (`NotManagedError`, `cli.py:1027-1028`), or its installation record cannot be read (`Installation.read`, `cli.py:1029`: `CorruptInstallationError` or `UnsupportedInstallationSchemaError`, `installation.py:173-188`; neither is a `Refusal`); both are raised before any preflight, as in the existing command: exit 2, `cli.py:1355` (LPR4-002) | the existing cause, unchanged |
| c | policy not `adopted` (absent, invalid, not-adopted, record-invalid, changed) or mode not `cleanup`/`both` | the existing causes, unchanged |
| d | the file has no `unattended` key | `--unattended is not authorised: the adopted policy has no unattended key` |
| e | the key is there but `state.unattended` is `None` (adopted with the ordinary sentence only) | `--unattended is not authorised: the adoption does not hold the unattended sentence` |
| f | `state.unattended["cleanup"]` is false (prune only) | `--unattended is not authorised: unattended.cleanup is false` |

Only `PolicyState.unattended` is asked, never `policy["unattended"]`; an
invalid or changed policy and an older record are refused by row c with the
state they are in, so they authorise nothing. Rows a and b are argument checks
and row b2 is the managed check and the installation-record read: they run before the repository is read and
before the audit file is opened, so the audit directory holds nothing for them
(**LPR1-003**, **LPR4-002**: the not-managed refusal and an unreadable installation record write no `preflight` line, because the read runs before the audit file is opened). **Every
`retention_cleanup.Refusal` the unattended preflight raises, once the audit is
open, writes exactly one `preflight` line (EPR3-001)**: rows c to f and also
the existing refusals behind them (the adopted mode that does not allow
cleanup, a policy file not committed at HEAD, a changed tracked file, a failed
`git`, an installed release older than the cleanup floor or unreadable, a
modified, unchecked or release-less installed script, an unavailable or
incomplete report and an interrupted removal, `retention_cleanup.py:196-258`).
The argument refusals (rows a, b) and the row b2 refusals (not managed, installation
record unreadable) are the
only ones that write nothing and open no audit file. Rows d to f are checked before
anything that starts a process: no `report` and no `git` run for them
(**LPR1-001**; the existing `committed()` check at `retention_cleanup.py:196`
runs after them).
With `--unattended`, `--confirm` is **not** required.

### 2.2 Selection and `keep_recent` (CP1)

`select` takes the policy's `keep_recent` from the state: when
`state.unattended` is set and its `cleanup` is true, the newest
`max(0, keep_recent - report["keep_recent"])` entries of `report["finished"]`
(which is newest first) are **kept**: never planned, and not listed as skipped.
"The N newest finished items" means the N newest **entries of
`report["finished"]`**, taken before the `review_folder.present` filter: a kept
newest entry whose review folder is already removed still counts toward the keep
(**LPR1-008**; the code, the keep line, the page and a test say the same). They
still count in the measured numbers (the thresholds describe the
repository), so a threshold that only they hold up ends `no further item is
eligible`. Everything else in `select` is unchanged: oldest first, `CAP = 5`,
the skip for tracked files and unacceptable ids, the age rule.

Because `select` is the one planner, the preview (`retention-cleanup TARGET`),
the confirmed run and the unattended run show and execute **the same plan with
the same digest rule** (`plan_digest` is untouched; the policy digest it hashes
already covers `keep_recent`). The preview gains one line when items are kept:
`keep: the 5 newest finished items stay (the policy's unattended keep_recent; the
engine keeps 3, so 2 more here)`. A policy without an authorising adoption
prints exactly today's preview (a golden pins it). The unattended run prints,
and the JSON carries, the plan digest it executed.

### 2.3 The audit file (CP2)

One JSON object per line, appended to `retention-audit.jsonl` in
`$XDG_STATE_HOME/workflow-manager/` (a relative or empty `XDG_STATE_HOME` is
ignored, as the XDG rule says; default `~/.local/state/workflow-manager/`).

| Rule | Detail |
| --- | --- |
| Fields | `schema_version` 1, `time` (ISO UTC, `...Z`), `run_id` (32 hex), `repository` (resolved path), `policy_digest`, `plan_digest`, `item_id`, `step`, `engine_code`, `result`, `error`; each line has all eleven (`null` where none) |
| One line per | action: `step` is `archive`, `verify` or `remove`, `result` `ok`, `failed` or `interrupted`, `engine_code` the engine's `error: CODE:` code when it printed one, `error` the cleaned message; nothing eligible: `step` `plan`, `result` `nothing-eligible`; refusal or stop: `step` `preflight` (`result` `refused`, `plan_digest` null) or `policy` (`result` `stopped`, the re-read found the policy changed or no longer authorising) |
| Start line | **one line beyond the specification, forced by "never act unaudited"**: `step` `plan`, `result` `started`, written once when the plan is non-empty and before the first action. It is the proof the file is writable (a failure refuses the run before any action), it names the plan digest, and it leaves a trace if the Manager is killed during an action (the action's own line is written after it returns) |
| Location | outside the repository and outside the engine's archive store (`~/.local/share/workflow-archive`); a path that resolves inside either is refused, so the clean-tree check is untouched |
| Modes | missing parents of the state directory (`$XDG_STATE_HOME` or `~/.local/state`) are created `0700` too (the XDG default for a state base; **LPR1-007**), existing parents are not inspected; the `workflow-manager/` directory created `0700`, file created `0600` (`O_CREAT` with the mode, then `fchmod`, so the umask cannot widen them); an existing file must be a regular file owned by the user, not a link (`O_NOFOLLOW`) and not group- or world-writable; an existing directory must be owned by the user and not group- or world-writable |
| Append-only | opened `O_WRONLY` with `O_APPEND` only: never seeked, truncated or rewritten; each line is **one** `os.write` of the whole encoded line plus a newline, and a short write is a failure |
| Unwritable | opening or writing the start line fails: refuse before any action, exit 2, cause `the audit file cannot be written: ...`, no engine verb issued (an open failure and a first-write failure are two distinct refusals, each tested). A refusal whose own `preflight` line cannot be written still exits 2 with nothing run: the printed `error:` is the refusal's own cause, and one more stderr line `error: the audit file could not record this refusal: ...` names the audit cause (**LPR1-006**). A write failure after the start line stops the run (2.4). The write is the `Audit` class's injectable `write` seam (default `os.write`), so a test lets the open succeed and fails only the first write |

A line is at most about 1 KiB (the engine text is cut at the run's
`MESSAGE_LIMIT` of 400 characters), so one `write` is one atomic append.

### 2.4 The run and `--json` (CP3)

`retention_run.run` gains two keyword parameters with defaults that keep the
confirmed run byte-identical: `unattended` (the per-item policy re-read also
requires `state.unattended` set with `cleanup` true, so a swapped adoption
record, which the policy digest does not cover, stops the run) and `observer`
(called after each step with the step, the item, the result, the engine code and
the text). The unattended module supplies the observer that appends the audit
line and records the step for the JSON document.

* **Audit failure after an action.** The observer raises on a failed write; the
  run stops with its own closing line, which says the step **had succeeded**,
  that no further call was made and where the audit file is. Exit 1 (a per-item
  call was attempted). An audit failure while recording a failure only adds
  `audit_error` to the result; the run was stopping already.
* **Order in the command.** Argument checks (rows a, b); managed check and installation-record read (b2, both before the audit opens);
  the audit file is opened (refuse on failure); the preflight with
  `unattended=True` (any `Refusal` writes one `preflight` line, then
  exits 2); the plan; an empty plan (**LPR1-002**) never prints a `--confirm`
  next step: with no threshold reached (`plan.outcome is None`) it prints the
  preview's own `nothing to do` text, writes no line (a daily heartbeat must not
  grow the file by itself), JSON `outcome` `nothing-to-do`, exit 0; with a
  threshold reached and `items == ()` (`outcome` `EXHAUSTED`: every candidate
  tracked, unacceptable or held by `keep_recent`) it prints one line,
  `retention cleanup: nothing eligible (<the reached thresholds>; no item is
  eligible[, skipped: ...]; running it again will not help)`, writes one `plan`
  line with `result` `nothing-eligible` and the plan digest (evidence that the
  run saw a threshold it could not lower), JSON `outcome` `nothing-eligible`
  with `thresholds_reached`, exit 0 (the retention alert reports the threshold);
  else the start line, then the run.
* **Text.** The lines of the confirmed run, then one last line
  `  audit: PATH`.
* **`--json`.** One document on stdout and nothing else there; the run's
  progress lines go to **stderr** (flushed, `emit` set to stderr) so a killed
  Manager still leaves its record (**LPR1-005**); without `--json` they stay on
  stdout:
  `kind` `retention_cleanup_run`, `schema_version` 1, `repository`, `run_id`,
  `policy_digest`, `plan_digest` (full), `outcome` (`done`, `stopped`,
  `nothing-to-do` or `nothing-eligible`), `items` (id, action, `result` `done`/`stopped`/`not-attempted`,
  `steps` each with `step`, `result`, `engine_code`, `error`), `done`, `total`,
  `stopped` (`null`, or `step`, `item_id`, `engine_code`, `error`, `next_step`),
  `thresholds_reached` (the names, empty unless `nothing-eligible`), `exit_code`, `audit` (`path`, `lines_written`, `error`). Exit codes are the
  confirmed run's: 0 done or nothing to do, 1 stopped after a per-item call was
  attempted, 2 refused or stopped before the first call. As for `doctor --retention
  --json`, a refusal before a plan exists prints nothing on stdout (stderr has
  `error:` and `next:`, and the audit has its `preflight` line); a stop prints
  the document.

### 2.5 Text and docs (CP4)

`NOT_ENFORCED` becomes one line printed by every output that printed it:
`  enforced by retention-cleanup --unattended for the cleanup part (archive and
remove); prune is not run unattended yet`. `status`, `doctor`, the adopt preview
and the `retention-cleanup` preview use the helper unchanged, so they agree.

**Three more statements say "only `--confirm` cleans up" and would contradict
that line (LPR2-001).** Each is made conditional on the same authority, so no
output holds two opposite statements, and the no-key outputs keep today's bytes
(A1):

* **The adopted block's last line** (`retention_policy.block`,
  `retention_policy.py:619-622`). When `state.unattended` is set with `cleanup`
  true it ends `... it sends nothing, and cleans up only when retention-cleanup
  runs with --confirm or, under the adopted unattended policy, with --unattended`.
  In every other adopted state (no key, ordinary-only adoption, `cleanup` false)
  the line is today's, byte for byte (`... cleans up only when retention-cleanup
  runs with --confirm`), so those outputs are unchanged. The phrase `retention-cleanup runs with --confirm` already sits in one string literal on `73a5a72` (`retention_policy.py:622`; only `cleans up only when ` is in the literal before it), so the edit rejoins nothing: it keeps the phrase in one literal, and lays the code out so the no-authority line's literal **ends** with `--confirm` (as at `:622`) while the unattended line is a separate literal that continues `retention-cleanup runs with --confirm or, under the adopted unattended policy, with --unattended` (EPR3-002, LPR4-001).
* **The `adopt-retention-policy` help** (`cli.py:1261`): `and only
  retention-cleanup with --confirm cleans up (for cleanup and both)` becomes `and
  only retention-cleanup cleans up (for cleanup and both), with --confirm, or
  with --unattended when the file carries the unattended key and is adopted with
  the unattended sentence`. The sentence after it (`Only the repository's owner
  runs it with --confirm; an agent must not`) is unchanged: the adoption
  sentence is what the owner gives once.
* **`docs/retention.md`**: the intro sentence (`:90`, `only when its --confirm
  holds the sentence ... archives and removes`) gains `, or, under a policy
  adopted with the unattended sentence, when run with --unattended`; the block
  quoted at `:171` is the no-key block, still exact, and a second block shows
  the line for an unattended adoption (a single line in a code fence, as at `:171`; it contains the searched phrase but does not end with it).

`README.md:71` (`preview, or with --confirm run, the cleanup the policy allows`)
is **left as it is on purpose** (LPR2-003): it is a one-line summary that stays
true (`--confirm` still runs the cleanup), the page and `--help` carry the
unattended form, and the README is outside this item's declared files.
`docs/retention.md` documents the command, what the one-time adoption
authorises, the audit file, the refusals, `keep_recent` and that prune is not
yet unattended; `docs/exit-codes.md` and the command help gain the new flags.
The pages name no internal id (a test pins it).

## 3. Failure-only mutations

Every test is run unmutated first, one `--select` per file (`python3
tests/run_all.py --select test_retention_unattended_run.py --select
test_retention_unattended.py --select test_retention_run.py --select
test_retention_cleanup.py --select test_retention_policy.py`); then each mutation below on a scratch copy outside
the repository, checked with the selection of the file that holds the named
test. The expectation is "the named tests are among the failures"; the unmutated
tree exits 0.

| # | File and change | Must fail |
| --- | --- | --- |
| M1 | `cli.py`: accept `--confirm` with `--unattended` | the mix refusal test (and its no-write proof) |
| M2 | `cli.py`: accept `--json` without `--unattended` | the json-needs-unattended refusal test |
| M3 | `retention_cleanup.py`: authority row d dropped | the no-key refusal test |
| M4 | authority row e dropped (read `policy["unattended"]` instead of `state.unattended`) | the ordinary-adoption refusal test |
| M5 | authority row f dropped | the cleanup-false refusal test |
| M6 | `preflight`: check the authority after the report is fetched | the no-process proof of rows d to f (`script_calls()` empty, so no `report`, and the `retention_cleanup._git` seam never called) |
| M7 | `select`: `keep_recent` ignored | the keep test (newest not planned) |
| M8 | `select`: skip `keep_recent` entries instead of `keep_recent - 3` | the keep-boundary test (5 keeps 2 beyond the engine's 3) |
| M9 | `select`: apply `keep_recent` for the unattended run only | the dry-run equivalence test |
| M10 | `retention_unattended.py`: file created without `0600` (umask applied) | the audit modes test |
| M11 | directory created without `0700` | the audit modes test |
| M12 | open without `O_APPEND` (truncate) | the append-only test |
| M13 | write the line in two `write` calls | the single-write test |
| M14 | do not refuse an audit path inside the repository | the audit-location test |
| M15 | do not refuse a link, a group-writable file or a directory as the audit file | the audit-file-shape tests |
| M16 | do not write the start line before the first action | the first-write-fails test: the open succeeds, an injected `os.write` error (`ENOSPC`) fails the first write; without the start line that write is the one after the first action, so an engine verb is issued and the test fails |
| M17 | `retention_run.py`: ignore an observer failure | the mid-run audit failure test (no further call after it) |
| M18 | `retention_run.py`: re-read without the authority condition | the swapped-record stop test |
| M19 | `retention_run.py`: re-read ignores a changed digest | the policy re-read stop test |
| M20 | `retention_unattended.py`: write no line for a refusal or a stop | the refusal-line and stop-line tests |
| M25 | `retention_unattended.py`: write the `preflight` line only for rows c to f (suppress it for a later preflight `Refusal`, such as an uncommitted policy file or an interrupted removal) | the later-refusal audit tests (EPR3-001): each of those refusals must leave exactly one `preflight` line, so the mutation fails them |
| M21 | `retention_unattended.py`: JSON `plan_digest` truncated or `kind` changed | the document test and the equivalence test |
| M22 | `retention_policy.py`: restore the old not-enforced line | the text goldens and the page test |
| M24 | `retention_policy.py`: `block` keeps `cleans up only when retention-cleanup runs with --confirm` for a policy whose unattended cleanup is authorised, or changes it for one that is not | the unattended-block test and the unchanged no-key and ordinary-only block tests in `tests/test_retention_policy.py` (LPR2-001) |
| M23 | `retention_run.py`: issue `prune` or add an argv form | the existing never-prune tests |

Every refusal has its own **no-write proof**: the repository's `tree_hash` before
and after is equal, `keys()` (the engine calls but the report) is empty, and the
audit directory holds either nothing (rows a, b, b2 (including the unreadable installation record) and the audit refusals) or
exactly one `preflight` line (every refusal after the audit opens, rows c to f and the later preflight refusals, EPR3-001). **Rows d to f are stronger**
(**LPR1-001**): `keys()` ignores the `report` call, which is the only effect of
M6, so their proof is that `script_calls()` is empty (no `report`) and that the
`retention_cleanup._git` seam (patched to raise) was never reached either.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The unattended authority check and the keep_recent selection | - | 2 | 1 |
| CP2 | The audit writer | - | 2 | 1 |
| CP3 | The unattended run and its JSON document | CP1, CP2 | 3 | 1 |
| CP4 | The status text, the docs and the ROADMAP row | CP3 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the unattended authority check and the keep_recent selection

**Files:** `src/workflow_manager/retention_cleanup.py`, `tests/test_retention_unattended_run.py`.

Section 2.1 rows d, e and f as a function of the state (`unattended_refusal`)
called by `preflight` through a new keyword `unattended=False` right after step 2
(nothing else in the preflight moves) and section 2.2: `select` applies
`keep_recent`; `Plan` gains `kept`; `preview_lines` prints the keep line only
when items are kept. Tests (new file, reusing the scratch base of
`test_retention_run`): each authority refusal at the function and through the
preflight with the no-write proof and, for rows d to f, no script call at all and
no `git` process (M3 to M6; the proof patches `retention_cleanup._git`,
`retention_cleanup.py:78`, the one place the preflight starts `git`, to raise,
so a refusal that reached it fails the test, and no fake `PATH` is involved,
LPR2-004); the existing
refusals still win for an absent, invalid, not-adopted, record-invalid and
changed policy; `keep_recent` 3 keeps nothing beyond the engine, 5 keeps two
more, a larger keep than the finished list ends `no further item is eligible`,
the kept items are not listed as skipped, the age rule never plans a kept item;
a newest finished entry with no review folder still counts toward the keep
(LPR1-008);
`keep_recent` is not applied for a policy without an authorising adoption
(preview byte-identical to today's golden); dry-run equivalence: the preview's
plan digest equals the plan an unattended state selects, for the same report.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the audit writer

**Files:** `src/workflow_manager/retention_unattended.py`, `tests/test_retention_unattended_run.py`.

Section 2.3 as a small class in a new module: `audit_path` from the environment,
`open_audit` (the location, mode and shape rules, `AuditRefusal` with a cause and
one step), `Audit.line` (build the eleven fields, one `os.write`, a short write
is an error) with injectable `clock`, `run_id` and `write` seams for the tests. Nothing
calls it yet. Tests: the eleven fields and the schema version on every kind of
line; the ISO UTC time; the run id shape; the default path with `HOME` and the
`XDG_STATE_HOME` override (a relative value ignored); directory `0700` and file
`0600` under a `0o000` and a `0o077` umask; append-only (existing lines stay
byte for byte, two runs append, no seek or truncate: the open flags are pinned);
one `os.write` per line (a counting wrapper); refusals each with its own proof:
a path inside the repository, inside the archive store (its default pinned to the
engine script's own constant by reading `scripts/workflow_retention.py`), a link,
a directory in place of the file, a group-writable file, a file owned by another
user (simulated through the stat seam), an unwritable directory; missing parents of the state directory
created `0700`; a write error and a short write raise the audit error, and an
open failure and a first-write failure are different errors.
<!-- /CP2 -->

<!-- CP3 -->
### CP3 -- the unattended run and its JSON document

**Files:** `src/workflow_manager/retention_unattended.py`, `src/workflow_manager/retention_run.py`, `src/workflow_manager/cli.py`, `tests/test_retention_unattended_run.py`.

Section 2.4: the flags `--unattended` and `--json`, the argument checks, the
order in the command, `retention_run.run`'s `unattended` and `observer`
parameters and the audit-stop closing, the document builder. Tests (the fake
engine and report of `test_retention_run`; every test sets `XDG_STATE_HOME` to a
scratch directory, and one test pins that the audit path used is that one):
`--unattended` runs without `--confirm` and issues exactly the confirmed run's
calls in its order; the two argument refusals (M1, M2), the not-managed
refusal and a corrupt installation record (LPR4-002: exit 2, no engine call, no audit file created) before any read; each of rows c to f
through the command writes one `preflight` line, rows d to f with no script call
and `retention_cleanup._git` never reached; **each later preflight refusal**
(mode not allowing cleanup, policy file not committed, tracked change, failed
`git`, old release, unreadable release record, modified/unchecked/release-less
script, report unavailable, incomplete report, interrupted removal) runs through
the command unattended with the no-write proof (tree hash equal, no engine verb
but the report) and exactly one `preflight` line, and M25 must fail them (EPR3-001); a `preflight` line that cannot be written still exits 2
and prints the policy cause plus the audit cause (LPR1-006); an unwritable audit
directory refuses at the open, and, separately, an open that succeeds followed by
an injected `os.write` failure on the first write refuses before any engine verb
(M16); the audit has the start line, then one line per
action with the full plan digest, the same digest as the preview, the document
and `plan_digest(select(...))`; each failure (archive refusal with its engine
code, verify mismatch, remove timeout, interrupt) writes its `failed` or
`interrupted` line and stops with the confirmed run's closing text and exit
codes; the policy changed before item 2 and a record swapped for an ordinary-only
one stop with a `policy` line (M18, M19); a write failure after the second action
stops before the third call, says the step succeeded, exits 1 (M17); nothing to
do (no threshold reached) prints the preview's text, writes no line, exits 0; a
reached threshold with no eligible item, including one held only by
`keep_recent`, prints the `nothing eligible` line with no `--confirm` next step,
writes one `plan` line, exits 0 (LPR1-002); the `--json` document for
done, stopped, stopped before the first call, nothing-to-do and nothing-eligible,
with nothing but the document on stdout (the progress lines on stderr, LPR1-005),
and nothing on stdout for a refusal; the text output
equals the confirmed run's plus the `audit:` line; `prune` and any extra argv
form are still never issued (M23); the repository's tree is unchanged by a clean
run (the review folders are untracked).
<!-- /CP3 -->

<!-- CP4 -->
### CP4 -- the status text, the docs and the ROADMAP row

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `docs/retention.md`, `docs/exit-codes.md`, `tests/test_retention_unattended.py`, `tests/test_retention_policy.py`.

Section 2.5: the new text constant in `retention_policy.py`, the conditional
last line of `block` and the adopt help in `cli.py` (LPR2-001), and the module
docstring (nothing runs unattended becomes: only the cleanup part of
`retention-cleanup --unattended` does); A1's goldens in
`tests/test_retention_unattended.py` (block, adopt preview and cleanup preview in
each state, the no-key outputs still byte-identical) and its page needles move to
the new wording, with the old not-enforced line asserted absent from the code and
the pages (M22); `tests/test_retention_policy.py`'s two goldens of the block line
(`:536`, `:550`) stay as they are for the no-key adoption, and a new test there
pins the block of a policy adopted with the unattended sentence (the
`--unattended` wording, and no remaining `cleans up only when retention-cleanup
runs with --confirm` line in it), the unchanged block for an ordinary-only
adoption and for `cleanup` false (M24), and that the adopt help and the page
carry the unattended form (a page test pins the needle); `docs/retention.md` (the command, what the one-time adoption authorises,
the audit file with its fields, location and modes, the refusals, `keep_recent`
and the keep line, `--json`, that prune is not yet unattended, and the table row
that said not enforced yet; the sentences the existing exit-code tests pin stay
word for word) and `docs/exit-codes.md` (the `--unattended` and `--json` cases of
the three exit codes). Row 51 is added to docs/ROADMAP.md (status Current, in the
style of row 50; the "What's next" sentence is left as the neighbours leave it)
and, as the last act of this checkpoint, marked Done in the item's own wording;
docs/ROADMAP.md is implementation-excluded by design and is not a deliverable.
`docs/retention.md` also pins the nothing-eligible outcome (text, `plan` line, JSON
`outcome`, exit 0) and what "the N newest finished items" means. A page test pins the needles and that the pages name no internal id.
<!-- /CP4 -->

## 5. Functional review

Flows are offline greps and diffs in a clone `S/cand` of the branch head
(`S=$(mktemp -d "$HOME/.cache/ur-run-fr.XXXXXX")`, `git clone --no-hardlinks
<product clone> $S/cand`); they write nothing into the product clone. Flow 9
needs the full environment (the primed release cache `tests/run_all.py` needs).
Every grep excludes `docs/ACTIVE_MILESTONE.md`. `B` is
`73a5a7212b26238dd8a36a45c7a970c8518b3f52`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --name-status B HEAD -- src tests tools .github .claude scripts .workflow-manager` | `src/workflow_manager/retention_cleanup.py`, `retention_run.py`, `retention_policy.py` and `cli.py` modified, `src/workflow_manager/retention_unattended.py` and `tests/test_retention_unattended_run.py` added, `tests/test_retention_unattended.py` and `tests/test_retention_policy.py` modified; nothing under `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/` |
| 2 | `cd $S/cand && git diff --name-status B HEAD -- docs` | `docs/retention.md`, `docs/exit-codes.md` and `docs/ROADMAP.md` modified, plus this item's own planning and bookkeeping files (plan, registry, artifacts, mapping added; `docs/ai-workflow/WORKFLOW_STATE.json` and `docs/ACTIVE_MILESTONE.md` modified); no other page |
| 3 | `cd $S/cand && git diff --exit-code B HEAD -- docs/verify.md docs/update.md docs/release-history.md README.md tests/parallel/resources.json src/workflow_manager/retention_alert.py src/workflow_manager/retention_alert_json.py src/workflow_manager/retention.py` | exit 0 (untouched) |
| 4 | `cd $S/cand && grep -n "retention-cleanup TARGET --unattended\|retention-audit.jsonl\|keep_recent\|0600\|0700" docs/retention.md` | the page names the command, the audit file with its modes, and `keep_recent`; `grep -n "unattended" docs/exit-codes.md` shows the flag in the exit-code rows |
| 5 | `cd $S/cand && grep -rn "unattended-retention\|#254\|#259" docs/retention.md docs/exit-codes.md` | no match (the pages name no internal id) |
| 6 | `cd $S/cand && grep -rn "nothing runs unattended, and retention-cleanup" src docs/retention.md` | no match (the old not-enforced line is gone); `grep -rn "prune is not run unattended yet" src docs/retention.md` matches in the code and the page; `grep -nE 'retention-cleanup runs with --confirm("|$)' src/workflow_manager/retention_policy.py docs/retention.md` matches only the no-authority forms, i.e. those that **end** with the phrase (exactly once in the code, the literal in the conditional that keeps today's bytes, and exactly once in the page, the no-key block at `:171`); the unattended forms also contain the phrase but continue `or, under the adopted unattended policy, with --unattended`, so `grep -n "runs with --confirm or, under the adopted unattended policy" src/workflow_manager/retention_policy.py docs/retention.md` matches once in the code and once in the page, in the second block (EPR3-002, LPR4-001). The rendered bytes are proven by the unchanged no-key and ordinary-only block tests, not by the grep alone, and `grep -n "with --unattended" src/workflow_manager/retention_policy.py src/workflow_manager/cli.py docs/retention.md` matches the unattended block line, the adopt help and the page (LPR2-001) |
| 7 | `cd $S/cand && grep -n "^| 5[01] " docs/ROADMAP.md` | row 51 names #254 and A2 with status Done in the item's own wording; row 50 is unchanged (`git diff B HEAD -- docs/ROADMAP.md` shows only added lines) |
| 8 | `cd $S/cand && XDG_STATE_HOME=$S/state PYTHONPATH=src python3 -m workflow_manager retention-cleanup "$S" --unattended --confirm x; echo $?; ls $S/state` | exit 2, stderr names that `--confirm` and `--unattended` cannot be combined, and `$S/state` does not exist (nothing written); the same with `--json` alone gives exit 2 and an empty stdout |
| 9 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_retention_unattended_run.py`, then one run each with `--select test_retention_unattended.py`, `--select test_retention_run.py`, `--select test_retention_cleanup.py`, `--select test_retention_policy.py` and `--select test_retention_status.py` | all six exit 0; with mutation M16 of section 3 applied in a scratch copy the first selection exits 1 with the first-write-fails test among the failures |
| 10 | `python3 tools/release/release.py check-title "feat: run the retention cleanup unattended under the adopted unattended policy, with an audit file"` | `valid title: feat, release impact minor` |

## 6. Risks

* **The run deletes without a per-plan human step.** That is the owner's
  decision (2026-11-17) and is bounded: the engine keeps its 3 newest and
  deletes only what the archive proves by SHA-256; the Manager keeps
  `keep_recent`; at most 5 per run; the first failure stops; the authority is
  the one-time digest-bound sentence and any edit of the policy ends it.
* **A swapped adoption record keeps the policy digest.** Re-reading
  `state.unattended` before each item closes it (M18). A record changed between
  the last re-read and the call of the item is not detectable; the window is up to
  three engine calls (archive, verify and remove run for the item after the
  re-read, which happens once before each item).
* **`keep_recent` also changes the confirmed run's plan** once the policy is
  adopted with the unattended sentence. Intended (one plan, one digest rule);
  documented; the plan digest still changes with it, so a stale sentence is
  refused.
* **The audit file grows without bound.** One run writes at most 1 + 3 x 5 + 1
  lines; a daily run is under 20 lines a day. Rotation is not in this item and
  is not needed for years of runs.
* **A kill during `remove`.** The action's line is written after it returns, so
  a kill leaves the start line and the engine's own `.removing` evidence, which
  the next preflight refuses until finished by hand. The run's behaviour is
  unchanged by this item.
* **A shared audit file under concurrent runs.** `O_APPEND` single writes do not
  interleave; the engine's lock already makes the second run stop at `archive`.

## 7. Open decisions

None for the owner. Design choices marked for the reviewers: the single `plan`
start line beyond the specification (2.3, forced by "never act unaudited"),
`keep_recent` applying to every cleanup plan once an unattended adoption exists
(2.2, forced by dry-run equivalence), nothing on stdout for a `--json` refusal
(2.4, the `doctor --json` convention), and an audit file or directory that is
group- or world-writable being refused (2.3). `docs/TECHNICAL_DECISIONS.md` does
not exist in this repository.
