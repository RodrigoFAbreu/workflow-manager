# Workflow Manager: The Unattended Retention Prune (Revision 5)

`work_item_id: unattended-retention-prune` -- `governing_workflow_version: "2.2"`

Pull request title: `feat: prune old archives in the unattended retention run under the adopted unattended policy`

**Deliverable:** step A3 of the three unattended-retention steps of issue #254:
`workflow-manager retention-cleanup TARGET --unattended`, after its
archive-and-remove phase (A2, Manager 1.22.0), also **prunes archives** when the
adopted unattended policy says `unattended.prune` is `true`. The run keeps every
safeguard of A2 (preflight, authority check, policy re-read once per
item before its engine calls, audit-first, the first failure stops the run, one audit line per action and
per refusal, progress to stderr under `--json`) and adds the bounds the owner
set: finished items only, archives older than `unattended.ttl_days`, only items
whose review folder is already gone, never an id under an interrupted removal, at
most `unattended.prune_max_per_run` per run, oldest first, an engine dry run that
must list exactly the planned set before anything is applied.

**Work item type:** `process`. **Base commit:** `7e0ab69ddfef482e15f7d771e97b4473d591d8b2`
(tip of `main`; Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/unattended-retention-prune`, bound by the Controller. **Scope source:**
issue #254 (the owner's request and the design comment of 2026-11-18, option A,
step A3) and the work-item prompt. Owner decisions (2026-11-18 and 2026-11-19):
prune is enabled from the first adoption; `ttl_days` 30 (floor 14), prune cap per
run 3, `keep_recent` 5. These are values the owner writes in the policy file (A1
validates them); this item enforces whatever the adopted file says. The title is
a `feat:` change: the Manager releases a minor
(`python3 tools/release/release.py check-title` reads `valid title: feat, release
impact minor`); the Controller waits for the release. **Manager only**: no
Workflow release is needed, no pin changes, nothing under `.claude/`, `scripts/`,
`.workflow-manager/` or the managed documents of `docs/ai-workflow/` is edited.
No scheduler and no notification is added: the lane heartbeat step comes later.
**ROADMAP:** row 52 (A3 of the three unattended retention items, #254) is added in
the style of rows 50 and 51 with status Current, and the last checkpoint marks it
Done in the item's own wording; the Controller runs acceptance itself and will not
edit the row. No planning, test or tool in this item runs `archive`, `remove` or
`prune` against a real repository: every test drives a fake engine in a scratch
repository.

## 1. Verification on current main (`7e0ab69`)

Each point of the work-item specification was checked against the code and the
installed engine (`scripts/workflow_retention.py`, the installed copy of the
release; the release source in the `workflow` repository is read-only and was not
needed).

* **(1) Selection inputs.** The report the preflight fetches
  (`retention.fetch`, `retention.py:310`) already carries `archives[]`, one entry
  per archive file with `name`, `work_item_id`, `modified`, `age_days`, `bytes`,
  `prunable` and `item` (`finished`, `recent`, `open` or `other`:
  `scripts/workflow_retention.py:499-546`), `finished[]` with each entry's
  `review_folder.present`, and `removing[]` (interrupted removals). The Manager's
  validator (`retention.py:_validate`) checks `finished`, `kept_recent`,
  `totals` and `removing`, **not** the fields of `archives[]`, so the new
  selection must read them defensively. **TRUE-FIX-NEEDED.**
* **(2) The engine's own ttl notion.** `age_days` is the whole days since the
  archive's modification time and `prunable` is `age_days > ttl_days`
  (`_archive_fact`, `:352-368`). The Manager's report call is `report --json`
  with the engine's default ttl of 30 (`retention._run`), so the report's
  `prunable` flag says nothing about the policy's `ttl_days`: the Manager
  selects with `age_days > unattended.ttl_days` itself and passes
  `--ttl-days N` to the engine explicitly, so the engine judges the same
  boundary again. **TRUE-FIX-NEEDED.**
* **(3) The engine's prune.** `prune ID... [--apply] [--json] [--ttl-days N]`
  (`prune_archives`, `:2067`) refuses by code: `not_in_report`,
  `removal_interrupted`, `not_prunable`, `item_not_finished` (class `open` or
  `recent`), `archive_changed`, `archive_busy`, `unreadable`, `prune_failed`. It
  unlinks one archive file each, checked immediately before, and never opens the
  index, an archive's contents, a review folder or the repository. **The engine
  does not look at the review folder**: an archive whose folder still exists is
  deletable, after which `archive` refuses `already_indexed` and `remove` refuses
  `not_archived` for that item for good (the hazard of the design comment).
  Preventing it is the Manager's selection, not the engine's. **TRUE-FIX-NEEDED.**
* **(4) A dry run exists.** Without `--apply` the same call returns
  `kind` `retention-prune`, `mode` `dry-run`, `ttl_days`, `archives[]` (the set it
  would delete, each with `work_item_id` and `item`) and
  `result.removed` `[]`. That is the dry-run equivalence input. No change needed in
  the engine.
* **(5) Safeguards of A2 that carry over unchanged.** Preflight
  (`retention_cleanup.preflight`), the authority rows a to f, the audit file and
  its refusals (`retention_unattended.open_audit`), the per-item policy re-read
  (`retention_run.run`, `retention_run.py:241-251`), the observer and the audit-stop. The re-read
  logic is inline in `run`; it is **extracted** into a function so the prune phase
  asks the same question (CP2).
* **(6) Manager only.** Every requirement is met with the engine's existing
  `report` and `prune` verbs; nothing needs a Workflow release, so there is no STOP
  finding.

## 2. Design

One mechanism: **the unattended run gains a last phase that deletes the archives
the policy has aged out, under bounds the Manager selects and the engine
re-checks.** Principle: the Manager proposes, the engine's dry run must agree
exactly, only then is anything deleted, and every step is audited before it acts.

### 2.1 Where it runs

`run_command` (`retention_unattended.py`) keeps A2's order for the cleanup phase
(argument checks, managed check, audit open, preflight, plan, start line, run).
After the cleanup phase ends **without a stop** (items done, nothing to do or
nothing eligible) and the state the preflight read has `unattended.prune` true,
the **prune phase** runs. If the cleanup phase stopped, the prune phase is not
attempted (the report says so). Prune is independent of the cleanup thresholds: a
daily run with nothing to clean still prunes what has aged out.

`unattended.cleanup` must still be true for the run to start at all (authority row
f is unchanged): a policy with `cleanup` false and `prune` true is refused as
today, and the docs say so. This keeps A2's refusal, its tests and its text
unchanged and means the prune authority is always "cleanup authority plus prune".
(Design choice for the reviewers: loosening row f would change a released refusal
for no requirement of this item.)

### 2.2 Selection (CP1)

`retention_prune.select(report, unattended)` is a pure function of the **fresh**
report and the adopted `unattended` object. The fresh report is one more
`retention.fetch(target)` after the cleanup phase (the preflight's report is stale
once items were archived and removed; the specification says "from the fresh
report"). It must be complete (an incomplete report stops the phase), and an id
under `removing` is excluded, never selected.

An archive is **selected** only when every condition holds:

| Condition | Source | Excluded as |
| --- | --- | --- |
| class `finished` | `archives[].item == "finished"`; `open`, `recent` and `other` never | (not listed) |
| older than the ttl | `age_days` is an integer (not a boolean) and `age_days > unattended.ttl_days`: the archive is selected only when strictly older, so an archive exactly `ttl_days` old waits one more day | (not listed) |
| the review folder is gone | the matching `finished[]` entry has `review_folder.present` false; **no matching entry fails closed** | `review-folder-present` |
| not under an interrupted removal | id not in `removing` | `removal-interrupted` |
| an id the engine accepts | `retention_alert.plannable_id` | `unacceptable-id` |
| a usable `modified` | a string (the order key) | `age-not-known` |

Selected archives are ordered **oldest first** by `(modified, id)` and cut at
`unattended.prune_max_per_run`. The ids that were old enough and finished but
excluded for one of the three listed reasons are returned as `skipped` with the
reason (they are shown in the text and the JSON, never selected). `keep_recent`
is **not** applied to prune: it protects review folders from removal, and an
archive of an item whose folder is gone is exactly what prune is for; the
engine's own class check already keeps `recent` items. The plan has a digest,
`sha256` of `{repository, policy digest, ttl_days, ids in order}`, printed and
returned like the cleanup plan's.

### 2.3 The prune calls and dry-run equivalence (CP2)

The phase issues exactly two argv forms, built by `retention_prune.argv_for`,
each ending `--repo-root ROOT`, carrying only ids the selection returned and the
integer ttl (no `--archive-root`, as in A2: the engine's default store):

* dry run: `prune ID1 ID2 ... --json --ttl-days N --repo-root ROOT`
* apply: `prune ID --apply --json --ttl-days N --repo-root ROOT`, **one id per
  call**.

Order: policy re-read, fresh report, selection, (non-empty) the `prune`/`started`
audit line, policy re-read, **dry run**, equivalence check, then per id: policy
re-read, apply. The rule is uniform: **the policy is re-read before every engine
call of the phase** (the report, the dry run and each apply), through the same
function as the cleanup phase plus one extra predicate the prune module supplies
(that `unattended.prune` is still true; `retention_run.py` never names prune, see
CP2). A change stops the phase with a `policy` line before that call.

**Equivalence.** The dry run's document must be `kind` `retention-prune`, `mode`
`dry-run`, with `ttl_days` equal to the ttl passed, `result.removed` equal to
`[]`, and `archives[]` listing **exactly** the planned ids (same set, no
duplicate, no other id), each with `item` `finished`. Any difference, an engine refusal (for example `not_prunable`, see below), a timeout, a non-zero exit or output that is not one JSON
object stops the run **before any `--apply`**, naming the difference. Apply is
checked as a success only when `kind` is `retention-prune`, `mode` `apply`,
`ttl_days` is the ttl and `result.removed` is exactly `[ID]`.

One apply per id (rather than one apply for the whole set) is the one place this
item refines the specification's `prune IDS --apply` wording, and the code forces
it: the engine reports a partial failure only inside the text of its refusal
(`removed: a; not removed: b`), the specification requires the policy re-read
"before each prune call" and "one audit line per prune action", and a per-id call
makes each of them a plain fact instead of a parse. The set the engine's dry run
verified is the set applied; no id is applied that the dry run did not list. The
equivalence is a **set** comparison: the engine sorts the ids it is given
(`prune_archives`, `workflow_retention.py:2074`, `sorted(set(ids))`), so the dry
run's `archives[]` comes back in id order, and the apply order (oldest first) is
the Manager's, fixed by the per-id calls. The engine's own checks run again inside each apply.

**What the engine does and does not detect across calls.** Every `prune`
invocation, dry run or apply, builds a **new** report of its own
(`prune_archives` -> `_prune_select` -> `build_report`,
`workflow_retention.py:1971`) and compares an archive's file only with *that*
report (`_seen_by_report`, step 9; `_check_unchanged` just before the unlink). So
`archive_changed` covers a change **within one invocation** (between the engine's
report and the unlink) and nothing between the Manager's report, the dry run and
an apply. Across calls: an archive whose modification time changed but which is
still older than the ttl is accepted by the dry run and applied (the equivalence
check compares ids, classes and fields of the document, not mtimes, and the
Manager holds no mtime to compare); an archive whose modification time moved
forward so that `age_days` is no longer above the ttl is refused by the dry run
or the apply as `not_prunable`, without any clock change. The Manager's guarantee
is therefore: **the Manager selected only `finished` archives, the engine's own
fresh report listed exactly the planned ids as prunable and `finished` at the dry
run (the equivalence check), and at each apply the engine re-checks that the
archive is still prunable and not `open` or `recent`**; it is not that the bytes
are the ones the Manager's report saw. The engine's apply-time class check is only
that (`item_not_finished`, step 8, `workflow_retention.py:1990-1994`, refuses
`open` and `recent`, not `other`): if a checkout removed the item from the
workflow state after the dry run, the archive's class becomes `other`, and the
engine accepts and deletes it, as does the Manager's apply-success check
(`result.removed` is exactly `[ID]`). That is accepted, not guarded: the window is
one call, the folder was already gone (the Manager checked `review-folder-present`
at selection) and the item no longer exists in the state, so the archive is not
the only copy of a live item's review. The planned cross-call tests do not assert
a `finished` class at apply. An archive rewritten between
calls that is still old is a benign case (the file is an archive of an item whose
folder is gone either way).

### 2.4 Audit, stops and exit codes (CP2, CP3)

`retention_unattended.STEPS` gains `prune` (the results vocabulary is unchanged).
Lines of the phase, all with `policy_digest` and the prune plan digest in
`plan_digest`:

| Event | `step` | `result` | `item_id` |
| --- | --- | --- | --- |
| the plan is non-empty, written before the first prune call (the proof the file is writable; an unwritable file stops the phase before any prune call) | `prune` | `started` | null |
| an apply succeeded | `prune` | `ok` | the id |
| an apply failed (engine refusal with its code, exit status, timeout, output not readable) | `prune` | `failed` | the id |
| an apply was interrupted | `prune` | `interrupted` | the id |
| the fresh report is unavailable or incomplete, or the dry run failed or differs | `prune` | `refused` | null |
| the policy changed (or stopped allowing prune) before a call | `policy` | `stopped` | the next id (null before the dry run) |
| an interrupt during a policy re-read | `policy` | `interrupted` | the next id (null before the dry run), as A2 writes it |
| an interrupt during the fresh report or the dry run (no apply is running) | `prune` | `interrupted` | null |

No line is written when nothing is selected (a daily heartbeat must not grow the
file by itself); the JSON says `nothing-to-prune`. The first failure stops the
phase; later ids are not attempted. After an apply succeeded but its audit line
could not be written the phase stops before the next call and says the step had
succeeded (A2's audit-stop, reused).

**Exit codes** keep their meaning: 0 every step done (or nothing to do or to
prune), 1 a stop after any `archive`, `remove` or `prune --apply` call of this run
was attempted (the cleanup phase's own rule, extended to the prune apply), 2 a
refusal or a stop before any such call was attempted. A prune stop after the
cleanup phase succeeded therefore exits 1 and leaves the archived-and-removed
items done and reported; the audit shows exactly what ran. A stop in the prune
phase of a run whose cleanup phase attempted nothing (nothing to clean) and whose
failure came before any `--apply` (the report, the dry run, the equivalence, the
policy) exits 2: nothing was written.

### 2.5 `--json` and text (CP3)

The document keeps A2's shape and **`schema_version` stays 1**: the only change is
one added key, `prune`, and nothing in the schema rules (A2's page, the audit
`schema_version` of the audit lines) forces a bump for an added field; the
document has no consumer yet (the heartbeat step comes later). `outcome` stays the
**cleanup phase's** outcome (`done`, `stopped`, `nothing-to-do`,
`nothing-eligible`) except that it is `stopped` when either phase stopped, and
`stopped` (the existing object) describes the first stop of either phase, `step`
being `prune` or `policy` for the prune phase. `prune`:

`enabled` (the adopted `unattended.prune`), `outcome` (`disabled`,
`not-attempted` (the cleanup phase stopped), `nothing-to-prune`, `done`,
`stopped`), `ttl_days`, `max_per_run` (both `null` when disabled), `plan_digest`
(`null` unless a plan exists), `ids` (planned, in order), `results` (per planned
id: `id`, `result` `done`, `stopped` or `not-attempted`, `engine_code`, `error`)
and `skipped` (`id`, `reason`). A refusal before a plan exists still prints
nothing on stdout. Progress lines go to stderr under `--json`, to stdout
otherwise, as in A2; the closing line of the cleanup phase no longer says "prune
was not run" when the prune phase follows (a `closing` text parameter of
`retention_run.run`, whose default is today's line and whose name and uses contain
no prune word; the confirmed run and an unattended run with `prune` false keep
their bytes).
The prune phase prints one line per planned archive and a closing line that says
a deleted archive cannot be undone and where the archive store is
(`~/.local/share/workflow-archive`, the engine's default store, which the Manager
does not back up); the final text line stays `  audit: PATH`.

**Text of a run whose cleanup phase has nothing to do** (today `_empty` prints the
preview lines and no `audit:` line; the new text is spelled out so CP3's goldens
have a target). With `prune` false the output is today's, byte for byte. With
`prune` true: the cleanup lines are today's (the preview lines for nothing-to-do;
the `nothing eligible` line, its audit line and its `audit:` line for
nothing-eligible), followed by the prune phase: nothing selected prints one line,
`retention prune: nothing to prune (ttl_days N, at most M per run)`, plus one
`skipped:` line per excluded archive, and nothing else (no prune audit line is
written, so no `audit:` line is added for nothing-to-do, and the nothing-eligible
run keeps its own); something pruned prints its per-archive lines, the
irreversibility closing line and the final `  audit: PATH`; a prune stop prints its
`retention prune: stopped ...` line, the final `  audit: PATH`, and `error:` and
`next:` on stderr. Under `--json` the same facts are the `prune` section, and a
nothing-to-do or nothing-eligible cleanup no longer returns before the phase
(`outcome` stays `nothing-to-do` or `nothing-eligible`, `prune.outcome` says what
the phase did).

### 2.6 Text and docs (CP4)

`retention_policy.NOT_ENFORCED` (A2's constant) becomes a function of the
`unattended` object, so `status`, `doctor`, the adopt preview and the
`retention-cleanup` preview agree. With `prune` true it says that
`retention-cleanup --unattended` archives and removes and then prunes, with the
exact limits (finished items only, a folder already gone, older than `ttl_days`,
at most `prune_max_per_run` per run, never one under an interrupted removal) and,
on its own line, that deleting an archive cannot be undone and where the archive
store lives; with `prune` false it says the cleanup part is enforced and that
`unattended.prune` is false, so no archive is pruned. `docs/retention.md` and `cli.py` replace every statement that
prune is not run unattended, each named here with its new wording (the stale text
is also in code and tests, which flow 6 and M23 search for):

1. `docs/retention.md` intro, the key table row, the enforcement paragraph ("`prune`
   is read and printed, and never run unattended yet" and its quoted line) and the
   "Prune is not yet unattended" paragraph: replaced as the text function above.
2. `docs/retention.md`, "What the one-time adoption authorises" ("It authorises
   nothing else: not prune, ..."): the sentence becomes "It authorises pruning too
   only when the file's `unattended.prune` is `true`, within its numbers; it
   authorises nothing else: not a file that changed after it was adopted (state
   `changed`, mode `off`), and not a file adopted with the ordinary sentence only."
3. `docs/retention.md`, "Retention cleanup" intro ("Prune is never part of cleanup:
   it stays user-only and is never run, and the unattended run does not run it
   either yet"): "The confirmed run never runs prune, and `workflow_retention.py
   prune` stays user-only; `--unattended` prunes only under the adopted
   `unattended.prune` (see [The unattended run](#the-unattended-run))."
4. `cli.py`, the `retention-cleanup` command description ("Prune is never run."): "Prune
   is never run by the confirmed run; with `--unattended` it runs only when the
   adopted policy's `unattended.prune` is true (see `--unattended`)." Its exit
   code 1 and 2 clauses also name a `prune --apply` call (1: stopped after the
   first per-item call or `prune --apply` was attempted; 2: before it).
5. `cli.py`, the `--unattended` help ("Prune is never run"): says that after the
   archive-and-remove phase a policy with `unattended.prune` true also prunes,
   with the limits, that this cannot be undone, and that the archive store is not
   backed up.

6. `docs/retention.md`, the status list's `archive store` line ("Neither is run by
   the Manager."): "Neither is run by `verify`, `doctor` or `status`; only
   `retention-cleanup --unattended` under an adopted `unattended.prune` runs a prune."
7. `docs/retention.md`, the alert's `next:` bullet ("The Manager never runs any of
   them."): "`verify`, `doctor` and `status` never run any of them; only
   `retention-cleanup --unattended` runs `archive`, `remove` and, under an adopted
   `unattended.prune`, `prune`."

CP3 (items 4 and 5, with the help pin in `tests/test_retention_cleanup.py`) and
CP4 (items 1 to 3, 6 and 7, with the page pin in the same file) carry them. The page also
documents the phase, the selection table, the dry-run
equivalence, the audit lines, the `--json` `prune` section and the exit-code
extension; `docs/exit-codes.md` carries the extension. The pages name no internal
id.

## 3. Failure-only mutations

Every test is run unmutated first, one `--select` per file
(`python3 tests/run_all.py --select test_retention_unattended_prune.py`, then
`--select test_retention_unattended_run.py`, `--select test_retention_unattended.py`,
`--select test_retention_run.py`, `--select test_retention_cleanup.py`,
`--select test_retention_policy.py`); then each mutation below on a scratch copy
outside the repository, checked with the selection of the file that holds the
named test. The expectation is "the named tests are among the failures"; the
unmutated tree exits 0.

| # | File and change | Must fail |
| --- | --- | --- |
| M1 | `retention_prune.py`: ignore the class (select `open`/`recent`/`other` archives too) | the class-filter test |
| M2 | `age_days >= ttl_days` instead of `>` | the ttl-boundary test (exactly `ttl_days` old is not selected; one more is) |
| M3 | ignore the review folder (select an archive whose folder is present) | the folder-present exclusion test, the wedge-hazard test, and the end-to-end no-apply proof |
| M4 | treat a missing `finished[]` entry as folder absent | the fail-closed test |
| M5 | ignore `removing` | the interrupted-removal exclusion test |
| M6 | no cap, or the cap applied before the order | the cap-and-order test |
| M7 | order by id instead of `(modified, id)` | the cap-and-order test (the oldest has the last name) |
| M8 | read the report's `prunable` flag instead of `age_days` and the policy ttl | the ttl test (a report whose default-ttl flag disagrees) |
| M9 | `argv_for` omits `--ttl-days` or adds `--archive-root` | the argv-pin test |
| M10 | skip the dry run (apply straight away) | the dry-run-first test (the first prune call must be the dry run) |
| M11 | dry-run set check ignores a missing or an extra id | the two equivalence-stop tests (nothing applied) |
| M12 | equivalence ignores `mode`, `ttl_days` or `result.removed` | the equivalence field tests |
| M13 | apply one call for the whole set | the one-id-per-call test |
| M14 | policy re-read skipped before the dry run or before an apply | the re-read-before-every-call tests (policy changed before the report, before the dry run, before the second apply) |
| M15 | re-read ignores `unattended.prune` | the prune-withdrawn stop test |
| M16 | no `started` line before the first prune call | the first-write-fails test (an injected write error on that line must issue no prune call) |
| M17 | ignore a failed audit write after an apply | the mid-phase audit failure test (no call after it) |
| M18 | write no line for a prune refusal or stop | the audit-line tests of each stop |
| M19 | prune after a stopped cleanup phase | the cleanup-stopped test (no prune call at all) |
| M20 | prune phase runs when `unattended.prune` is false | the prune-off test (no prune call, no prune line, text and JSON as before) |
| M21 | exit 2 for a stop after an apply was attempted, or 1 before any call | the exit-code tests |
| M22 | `retention_run.py`: the closing line says prune was not run when the prune phase follows, or loses it for the confirmed run | the closing-line tests and the confirmed run's golden |
| M23 | `retention_policy.py`, `cli.py` or `docs/retention.md`: restore the old not-enforced line, or any of the stale statements of 2.6 (items 2 to 4: "not prune,", "Prune is never run." in the command description, "never part of cleanup"), or drop the irreversibility or store text | the text goldens, the help and page tests of `tests/test_retention_cleanup.py` and `tests/test_retention_unattended.py` (each asserts the old statement absent) |
| M24 | `retention_run.py`: add `prune` to the cleanup argv forms, or a prune parameter or word that is not a never/no-form line | the existing never-prune tests of the confirmed run (`test_the_module_has_no_prune_verb`, unchanged, and the `argv_for` closed-forms test) |
| M25 | JSON document without the `prune` key, or `schema_version` changed | the document tests |
| M26 | `retention_prune.py`: skip the `plannable_id` check (select an unacceptable id) | the unacceptable-id test |
| M27 | `age_days` accepted when a boolean or a non-integer (drop the `bool`/`int` guard) | the non-integer and boolean `age_days` tests |
| M28 | a missing or non-string `modified` selected (treated as a sort key of `""` or the id) | the missing-`modified` test (never selected, `age-not-known`) |

Every refusal and stop has its own **no-write proof**: the repository's
`tree_hash` before and after is equal, no `prune --apply` call was issued unless
the test is about the apply that ran (the fake engine's call log, which also
proves the cleanup phase's calls are the confirmed run's), and the audit file
holds exactly the lines the table of 2.4 names.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The prune selection, its plan digest and its two argv forms | - | 2 | 1 |
| CP2 | The prune phase: policy re-read, dry-run equivalence, per-id apply, audit lines | CP1 | 3 | 1 |
| CP3 | The unattended command runs the phase; the JSON document, text and exit codes | CP2 | 3 | 1 |
| CP4 | The status text, the docs and the ROADMAP row | CP3 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the prune selection, its plan digest and its two argv forms

**Files:** `src/workflow_manager/retention_prune.py`, `tests/test_retention_unattended_prune.py`.

Section 2.2 as a new module: `select(report, unattended)` (pure, defensive reads
of `archives[]`), `PrunePlan` (ids in order, the entries, ttl, cap, `skipped`,
`capped`), `prune_digest` and `argv_for` (the two forms of 2.3, nothing else).
Nothing calls it yet. Tests (new file; report fixtures built from the shape of
`scripts/workflow_retention.py`'s `_assemble`, with `archives[]` entries carrying
`age_days`, `modified`, `item`): the class filter (`finished` selected;
`open`, `recent`, `other` never), the ttl boundary (`age_days` equal to
`ttl_days` not selected, one more selected, with a report whose own `prunable`
flag disagrees in both directions), the folder-present exclusion with
`review-folder-present`, a missing `finished[]` entry failing closed, an id under
`removing` excluded with its reason, an unacceptable id, a non-integer or boolean
`age_days` and a missing `modified` (never selected), the cap and the oldest-first
order (the oldest is not the first by name, and the cap cuts the newest), the
cap with `capped`, `skipped` listing only archives that were old and finished, a
policy-kept newest item with a gone folder and an old archive is selectable
(`keep_recent` does not apply to prune), an empty selection, `prune_digest`
stable and sensitive to each of repository, policy digest, ttl and the ids and
their order, `argv_for` pinned for both forms (ttl always present, one id for the
apply, never `--archive-root`, nothing else accepted), and that the module never
starts a process or reads a file (a pure function of its arguments).
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the prune phase: policy re-read, dry-run equivalence, per-id apply, audit lines

**Files:** `src/workflow_manager/retention_prune.py`, `src/workflow_manager/retention_run.py`, `src/workflow_manager/retention_unattended.py`, `tests/test_retention_unattended_prune.py`, `tests/test_retention_unattended_run.py`.

Sections 2.3 and 2.4. `retention_run.py` gains the extracted
`policy_holds(target, policy_digest, unattended=..., extra=None)` (`run`'s re-read
calls it; its behaviour is unchanged byte for byte; `extra` is an optional
predicate on the loaded policy state that `retention_prune.py` supplies to also
require `unattended.prune`) and the `closing` text parameter of 2.5. **The
existing `tests/test_retention_run.py::test_the_module_has_no_prune_verb`
(lines 494-499) is kept unchanged and is not an edited file**: every line of
`retention_run.py` containing "prune" must still match its pattern, so this file
gains no new prune word (the new names are `extra` and `closing`; the prune
words stay only in the three lines that exist, each already a never/no-form
line). `tests/test_retention_run.py` is therefore in no **Files:** paragraph and
no artifact declaration; the prune words, the `prune` argv and the extra
predicate live in `retention_prune.py`. `retention_prune.py` gains the phase: the fresh report, the
selection, the uniform re-read, the `started` line, the dry run, the equivalence
check, the per-id apply with the observer, and its result object (outcome, ids,
per-id results, the stop, whether an apply was attempted). `retention_unattended.py`
gains the `prune` step. That breaks one existing test, which CP2 therefore edits:
`tests/test_retention_unattended_run.py::test_an_unknown_step_or_result_is_a_bug`
calls `audit.line("prune", "ok")` and expects `ValueError`; it moves to a step that
is still unknown (`"unknown-step"`), keeps its `plan`/`done` result case, and a new
test there pins that `prune` with each of `started`, `ok`, `failed`, `interrupted`
and `refused` is accepted and written. Tests (fake engine: the verb-aware stub of
`test_retention_run`, extended in the new file with `prune` dry-run and apply
answers and a second report for calls after the first, in a scratch managed
repository; every test sets `XDG_STATE_HOME` to a scratch directory): the happy
path issues exactly one report, one dry run and one apply per id in order, with
the argv of 2.3; each safeguard has its own test with the no-write proof: the
policy changed or `unattended.prune` withdrawn before the report, before the dry
run and before the second apply (a `policy` line, no later call), a record swapped
for an ordinary-only adoption; the fresh report unavailable and incomplete; an id
under `removing` in the fresh report never applied; an old archive whose folder
is still present never applied, **and the wedge hazard test: a fixture where the
engine would delete it is proven by the call log to have no `prune` call naming
it**; the dry run listing one id too few, one too many, another class, the wrong
`mode`, the wrong `ttl_days`, a non-empty `result.removed`, an engine refusal
(`not_prunable`), a timeout and unreadable output (each stops before any apply
with one `refused` line); **engine-faithful cross-call tests** (the fake engine
recomputes `age_days`, `prunable` and the file's mtime from a scratch archive on
every `prune` call, as the real engine builds a new report per invocation): an
archive whose mtime changes after the Manager's report but stays older than the ttl
is accepted by the dry run and applied, and one whose mtime moves forward so it is
no longer older than the ttl makes the dry run (and, in a second test, the apply)
refuse `not_prunable` with one `refused`/`failed` line and no later call; the
`archive_changed` refusal is exercised only as an apply-time answer of the engine; an apply refusal (`archive_changed`), a non-zero exit,
a timeout, an interrupt and a wrong `result.removed` stop at that id with
`failed` or `interrupted` and the next ids not attempted; an interrupt during the policy re-read (a `policy`
`interrupted` line) and during the fresh report or the dry run (a `prune`
`interrupted` line with a null `item_id`), each with no later call; the `started` line
unwritable (no prune call), and a write failure after the second apply stops
before the third; the cap and the order reach the engine as selected; an empty
selection writes no line; after each stop the earlier applied ids stay reported.
<!-- /CP2 -->

<!-- CP3 -->
### CP3 -- the unattended command runs the phase; the JSON document, text and exit codes

**Files:** `src/workflow_manager/retention_unattended.py`, `src/workflow_manager/cli.py`, `tests/test_retention_unattended_prune.py`, `tests/test_retention_unattended_run.py`, `tests/test_retention_cleanup.py`.

Sections 2.1 and 2.5. `run_command` runs the phase after a cleanup phase that
did not stop (including the nothing-to-do and nothing-eligible outcomes, which no
longer return early when prune is enabled), builds the exit code of 2.4 and the
`prune` section of the document, prints the phase's lines (stdout, or stderr under
`--json`) before the final `audit:` line; `cli.py` replaces the command
description's "Prune is never run." and the `--unattended` help's "Prune is never
run" (2.6 items 4 and 5; A2's statements end), and
`tests/test_retention_cleanup.py:1031` moves its help pin ("Prune is never run")
to the new wording, with a needle that the old statements are gone. The empty-run
text of 2.5 is pinned by goldens here. Tests: with `prune`
false the text, the JSON (apart from the new `prune` key, `enabled` false and
`outcome` `disabled`), the audit and the calls equal A2's (the existing
`test_retention_unattended_run.py` goldens move only where they pin the old
"prune was not run" text or the document's key set (CP2 alone edits the
unknown-step test in that file), and one test pins that the
confirmed run's output is unchanged); with `prune` true: a run that cleans and
prunes (calls in order: cleanup's three per item, a report, the dry run, the
applies), a run with nothing to clean that still prunes, a run whose cleanup phase
stopped (no prune call, `prune.outcome` `not-attempted`, exit as A2's), each prune
stop through the command with its exit code (1 after an apply was attempted or the
cleanup attempted something, 2 when nothing had run), `cleanup` false with `prune`
true still refused as in A2 (row f), the authority refusals unchanged, the
`--json` document for done, stopped in the prune phase, nothing-to-prune,
disabled and not-attempted with nothing but the document on stdout and progress on
stderr, `schema_version` 1, the audit line counts in the document, the final text
line, and that the irreversibility and archive-store sentence is printed by a
run that deleted something.
<!-- /CP3 -->

<!-- CP4 -->
### CP4 -- the status text, the docs and the ROADMAP row

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `docs/retention.md`, `docs/exit-codes.md`, `tests/test_retention_unattended.py`, `tests/test_retention_policy.py`, `tests/test_retention_cleanup.py`.

Section 2.6: the text function in `retention_policy.py` (and its docstrings, which
say prune is not run unattended), the adopt help in `cli.py`, A1's and A2's
goldens in `tests/test_retention_unattended.py` (block, adopt preview and
cleanup preview in each state, with `prune` true and false; the no-key outputs
stay byte-identical) and its page needles, with the old statement asserted absent
from the code and the pages (M23), `tests/test_retention_policy.py` where it pins
the adopt help or the old line, `docs/retention.md` and `docs/exit-codes.md` as
2.6 says (items 1 to 3, 6 and 7), and the page pin of `tests/test_retention_cleanup.py:1042`
("Prune is never part of cleanup") moved to the new wording, with the stale
statements of 2.6 asserted absent from `docs/retention.md` (M23). A page test pins the needles (the limits, the irreversibility sentence,
the store path, the `prune` JSON section) and that the pages name no internal id.
Row 52 is added to docs/ROADMAP.md (status Current, in the style of rows 50 and
51; the "What's next" sentence is left as the neighbours leave it) and, as the
last act of this checkpoint, marked Done in the item's own wording;
docs/ROADMAP.md is implementation-excluded by design and is not a deliverable.
<!-- /CP4 -->

## 5. Functional review

Flows are offline greps and diffs in a clone `S/cand` of the branch head
(`S=$(mktemp -d "$HOME/.cache/up-fr.XXXXXX")`, `git clone --no-hardlinks <product
clone> $S/cand`); they write nothing into the product clone. Flow 9 needs the
full environment (the primed release cache `tests/run_all.py` needs). Every grep
excludes `docs/ACTIVE_MILESTONE.md`. `B` is
`7e0ab69ddfef482e15f7d771e97b4473d591d8b2`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --name-status B HEAD -- src tests tools .github .claude scripts .workflow-manager` | `src/workflow_manager/retention_prune.py` and `tests/test_retention_unattended_prune.py` added; `src/workflow_manager/retention_unattended.py`, `retention_run.py`, `retention_policy.py`, `cli.py`, `tests/test_retention_unattended_run.py`, `tests/test_retention_unattended.py`, `tests/test_retention_cleanup.py` and `tests/test_retention_policy.py` modified; `tests/test_retention_run.py` unchanged; nothing under `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/` |
| 2 | `cd $S/cand && git diff --name-status B HEAD -- docs` | `docs/retention.md`, `docs/exit-codes.md` and `docs/ROADMAP.md` modified, plus this item's own planning and bookkeeping files (plan, registry, artifacts, mapping added; `docs/ai-workflow/WORKFLOW_STATE.json` and `docs/ACTIVE_MILESTONE.md` modified); no other page |
| 3 | `cd $S/cand && git diff --exit-code B HEAD -- docs/verify.md docs/update.md docs/release-history.md README.md tests/parallel/resources.json src/workflow_manager/retention.py src/workflow_manager/retention_cleanup.py src/workflow_manager/retention_alert.py src/workflow_manager/retention_alert_json.py` | exit 0 (untouched) |
| 4 | `cd $S/cand && grep -n "older than .ttl_days\|prune_max_per_run\|cannot be undone\|workflow-archive" docs/retention.md` | the page names the ttl rule, the cap, that deleting an archive cannot be undone and where the archive store lives; `grep -n "prune" docs/exit-codes.md` shows the prune stop in the exit-code rows |
| 5 | `cd $S/cand && grep -rn "unattended-retention\|#254\|#259" docs/retention.md docs/exit-codes.md` | no match (the pages name no internal id) |
| 6 | `cd $S/cand && grep -rni "prune is not run unattended yet\|Prune is not yet unattended\|not prune,\|Prune is never run\.\|never part of cleanup\|does not run it either\|Neither is run by the Manager\|The Manager never runs any of them\|prune was not run" src docs/retention.md` | the search is case-insensitive; every needle but the last has no match anywhere (it still misses `retention_run.py:8` and the two-line `retention_cleanup.py:10-11`, which stay true and are untouched); `prune was not run` matches only the confirmed run's closing line and the unattended run's with `prune` false (`src/workflow_manager/retention_run.py`) and the page's description of those, never a line that says it of a run whose prune phase ran |
| 7 | `cd $S/cand && grep -n "^| 5[0-2] " docs/ROADMAP.md` | row 52 names #254 and A3 with status Done in the item's own wording; rows 50 and 51 are unchanged (`git diff B HEAD -- docs/ROADMAP.md` shows only added lines) |
| 8 | `cd $S/cand && XDG_STATE_HOME=$S/state PYTHONPATH=src python3 -m workflow_manager retention-cleanup "$S" --unattended --confirm x; echo $?; ls $S/state` | exit 2, stderr names that `--confirm` and `--unattended` cannot be combined, and `$S/state` does not exist (nothing written) |
| 9 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_retention_unattended_prune.py`, then one run each with `--select test_retention_unattended_run.py`, `--select test_retention_unattended.py`, `--select test_retention_run.py`, `--select test_retention_cleanup.py` and `--select test_retention_policy.py` | all six exit 0; with mutation M3 of section 3 applied in a scratch copy the first selection exits 1 with the folder-present and wedge-hazard tests among the failures |
| 10 | `python3 tools/release/release.py check-title "feat: prune old archives in the unattended retention run under the adopted unattended policy"` | `valid title: feat, release impact minor` |

## 6. Risks

* **Deleting an archive cannot be undone.** After a prune the item's only copy is
  gone: the review folder was removed by the cleanup phase (or earlier) and the
  archive was the proof of it. That is the owner's decision (2026-11-17, 2026-11-18,
  2026-11-19) and it is bounded: finished items only, a folder already gone, older
  than `ttl_days` (30 by the owner's setting, 14 at least), at most
  `prune_max_per_run` (3) per run, never an interrupted removal, the engine's
  dry run must agree exactly, and the engine re-checks every archive before its
  unlink. The archive store (`~/.local/share/workflow-archive`) is keyed by the
  repository's name only and the Manager does not back it up; moving it to a
  backed-up disk is the owner's decision (it must stay on the same file system as
  `.ai-review`) and is not part of this item.
* **The engine does not check the folder.** The wedge hazard is guarded by the
  Manager's selection and its tests only; an engine that changes `prune`'s
  selection or `report`'s fields would reach the dry-run equivalence check
  (`archives[]` and `item` are compared) but not the folder rule, which is read
  from `finished[].review_folder.present`. A report that lacks the entry fails
  closed.
* **A swapped adoption record keeps the policy digest.** The re-read before every
  call asks `state.unattended` and `unattended.prune` again (M14, M15); a swap
  between the re-read and the engine's own `lstat` is not detectable, a window of
  one call.
* **An archive that changes between the Manager's report and the dry run or an
  apply.** Each engine call builds its own report (2.3), so a changed modification
  time is **not** detected as such: if the archive is still older than the ttl the
  call accepts it and the phase applies it (benign, see 2.3); if the time moved
  forward so that it is no longer older than the ttl the engine refuses
  `not_prunable` (no clock change needed), the phase stops, writes a `refused` line
  and exits as 2.4 says, and the next daily run selects again. `archive_changed`
  arises only from a change inside one engine invocation, and `archive_busy` when
  another run holds the archive directory; both stop the phase the same way. A day
  boundary cannot cause a refusal: `age_days` only grows. Both outcomes have
  engine-faithful tests (CP2).
* **A review folder can reappear between the report and an apply** (for example a
  checkout of a branch that tracks it). The engine never looks at the folder and
  the Manager reads `review_folder.present` once, from the fresh report, so an
  archive of such an item would still be pruned and the item wedged
  (`already_indexed`/`not_archived`). The window is one run (seconds to minutes),
  needs a concurrent action on the repository during an unattended run, and is
  bounded by the cap; it is named, not closed, because closing it would need the
  folder re-checked before each apply, a later change that needs no schema change.
* **The cleanup phase's `keep_recent` does not protect archives.** An archive of a
  newest item whose folder is gone is old enough to prune; the engine keeps
  `recent` items only.

## 7. Open decisions

None for the owner. Design choices marked for the reviewers: one apply per id
(2.3, forced by partial-failure reporting, the per-call re-read and the per-action
audit line), `unattended.cleanup` still required (2.1, no change to a released
refusal), `keep_recent` not applied to prune (2.2), `schema_version` 1 with an
added `prune` key (2.5), no line for an empty selection (2.4, the heartbeat must
not grow the file), and the extraction of the re-read into `policy_holds` (CP2).
`docs/TECHNICAL_DECISIONS.md` does not exist in this repository.
