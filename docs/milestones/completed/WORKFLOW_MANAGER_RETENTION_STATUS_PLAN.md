# Workflow Manager: Report the Finished-Work Archive State, #90 (Revision 7)

`work_item_id: retention-status` -- `governing_workflow_version: "2.2"`

**Deliverable:** `workflow-manager status --retention TARGET` and
`workflow-manager doctor --retention TARGET` print one extra section that
reports a managed repository's finished work items, their untracked review
folders and their archives, by running the repository's own installed
`scripts/workflow_retention.py report --json` (read-only) and rendering what it
answers. Without `--retention` nothing changes: same output, same exit codes,
no subprocess.

**Work item type:** `process`. **Base commit:** `3019c95` (tip of `main`;
Workflow 2.22.0 installed, automatic gates). **Branch:**
`milestone/retention-status`. **Scope source:** `docs/ROADMAP.md` row 17
(issue #90) and the Workflow's retention page for the installed 2.22.0 script.
`src/` changes that add a feature, so the pull request title is `feat: ...` (a
Manager minor release, 1.14.0, follows the merge; checked with `python3
tools/release/release.py check-title`).

**Sizing (the owner's rule).** One mechanism: an opt-in section that calls one
installed script and renders its JSON. No exit-code change, no new state, no
release source or pin change, no Workflow release. Two checkpoints including
the bookkeeping one. The Manager never runs `archive`, `remove` or any other
command of the script, and never writes.

## 1. Decisions

**Opt-in, not cached.** The report makes one fresh forge query per finished
item (about 20 to 40 seconds for 25 items), and `status` and `doctor` must stay
fast. So the section appears only with `--retention` (an option of the command,
written after it like `--profile` or `--dry-run`, not a global option).
Caching was rejected: a cache is a write (a file somewhere, or a record in the
repository), needs an age rule and an invalidation story, and a stale answer
about "what can be archived" is worse than no answer. Default output, option
list of the other commands, and every exit code are unchanged; `--retention`
never changes an exit code either (the section is informational: a repository
whose retention report is not available still exits as it did without the
option).

**Where it prints.** `status`: after the work-in-flight block, before the final
`next:` line (which stays the last line). `doctor`: after the report. It is not
printed when the command refuses before its normal report (an unreadable
record, an unresolvable release): those paths are unchanged. For a repository
that is not managed, `status --retention` prints the not-available note below
(cause: not managed) and exits 0 as before.

**Calling the script.** `src/workflow_manager/retention.py` runs

    python3 -I -B TARGET/scripts/workflow_retention.py report --json --repo-root TARGET

with `sys.executable` as the interpreter (`python3` above stands for it).
TARGET is resolved once, to an absolute path from the directory the Manager was
started in (`Path.resolve()`, before anything else), and that one path is used
for the script path, for `--repo-root` and for `cwd`: the CLI keeps a relative
target as typed, and a relative script path or `--repo-root` would be read again
from the changed directory (`nested/repo` would become
`nested/repo/nested/repo/scripts/...`). `cwd` is the target, stdin closed, a new session (`start_new_session`) and a timeout of 300 seconds (a module
constant; tests patch it). On timeout the whole process group is killed and
reaped (the script's `gh` children included), so no process outlives the
call. `-B` is the Manager's own guarantee that the run writes no `__pycache__`
(`-I` implies `-E`, which ignores `PYTHONDONTWRITEBYTECODE`, so that variable is
not used). The script is never imported. The Manager passes no `--archive-root` and
no `--ttl-days`: the Workflow's defaults (`~/.local/share/workflow-archive`, 30
days) apply, and the report prints the archive directory and the TTL it used.

**Capability of the installed script.** The script's commands depend on the
Workflow release: `report` from 2.20.0, `archive` from 2.21.0, `remove` from
2.22.0 (the parsers of the cached 2.20.0 and 2.21.0 scripts have `{report}` and
`{report,archive}`). The Manager reads the record's `workflow_version` (the
version the target runs; it never probes the script) and offers a command only
when that release has it; a release newer than 2.22.0 is assumed to keep all
three. A version that is missing or not a release number offers none. When the
step the report calls for needs a command the installed release lacks, the step
is instead `workflow-manager update TARGET` ("this Workflow release has no
`archive` command; update it"), the one useful action; the counts are still
shown.

**Validation before rendering.** After the JSON object, `kind` and
`schema_version` checks, the fields the renderer reads are validated, each named
exactly as `scripts/workflow_retention.py` emits it (`_assemble`, `report`
at 2.20.0, 2.21.0 and 2.22.0), and the first failure is case 6 (naming the
field and the type seen), never a traceback or a default that could read as
clean: `complete` a boolean; `read_errors` a list of objects each with string
`path` and `error`; `repository` and `archive_dir` strings and `ttl_days` and
`keep_recent` ints; `finished`, `kept_recent` and `not_finished` lists; every
`finished` entry an object with a string `work_item_id`, `review_folder`
(`present` bool, `tracked_files` int, `bytes` int) and `archive` (`present` and
`readable` bool); every `kept_recent` entry an object with a string
`work_item_id`; every `not_finished` entry an object with strings
`work_item_id` and `reason`; `totals` an object with ints `finished`,
`finished_folder_bytes`, `archives` and `prunable` (the renderer's finished
count, folder size and prunable count; a `totals.finished` that differs from
`len(finished)` is case 6). `totals.archives` and `totals.prunable` count the
whole archive store (`len(archives)` and the prunable ones in
`scripts/workflow_retention.py` `_assemble`), including archives of items that
are `recent`, `open`, `other` or no longer in the state: they are store totals,
never finished-item coverage. The coverage "with an archive: A of N" is
derived from `finished`: A is the number of `finished` entries whose
`archive.present` and `archive.readable` are both true, and N is `totals.finished`;
the `finished` entries whose `archive.readable` is false are counted as
"unknown" and shown as `(U unknown)` when U > 0; `removing`, when
present, a list of strings. The kept count printed is `len(kept_recent)`.
Unknown extra keys (`archives[]`, `generated_at`) are ignored and preserved
nowhere (nothing is written). A script that exits 2 without the `error: CODE:
MESSAGE` and `next step:` lines is case 6 with the exit status and the first
stderr line as the cause, and its step is the case-4 step (run the script
directly). Stdout that is not valid UTF-8 is case 6. A valid report
accompanied by stderr warnings and exit 0 renders, and the warnings are
dropped.

**Stub shape is checked against the real script.** The hermetic stubs must not
invent a shape. `tests/test_retention_status.py` builds every stub report from
one base fixture, a report captured from the real 2.22.0 script (one finished
item with its folder present, one kept item, one `not_finished` item, one
`read_errors` entry and `removing` present), stored as
`tests/fixtures/retention_report.json`; the other cases are edits of that
fixture. A conformance test compares the fixture key-for-key and type-for-type
with a report the real script produces from the recipe below, and fails when
either side gains or loses a key. The validated-field list above is checked
against the fixture by the same test, so a renamed key fails the suite instead
of the product.

*Recipe (the second real-script case of section 2, in addition to the
no-finished case there; the fixture's contents are exactly what this run emits).*
The real `scripts/workflow_retention.py` and `scripts/workflow_forge.py` are
copied into a scratch managed repository (an `origin` remote of a GitHub URL,
no fetch; `HOME` a scratch directory so the default archive root does not read
the developer's machine). Its state holds four `MILESTONE_COMPLETE` items, each
with a distinct `reviewed_implementation_head` (40 hex) and a distinct
`last_transition`, so `KEEP_RECENT = 3` makes the three newest `kept_recent` and
the oldest the one `finished` item (`merged[KEEP_RECENT:]`), plus one open item
(`not_finished`, `open_phase`). The forge is not a stub `gh`: `resolve_gh` refuses
any `gh` under `TMPDIR`, `/tmp`, `/var/tmp`, `/dev/shm` or in a world-writable
directory, and the runner gives every chunk a private `TMPDIR`. The test instead
runs a test-only `python3 -I -B -c` subprocess with `cwd` the scratch repository
that puts the scratch `scripts/` first on `sys.path` and calls the real script's
`main(["report", "--json", "--repo-root", ROOT], run=RUN, resolve=RESOLVE)`
through the seams `main` already exposes (`scripts/workflow_retention.py`
`main`/`build_report`), with stdout captured. `RESOLVE` returns
`{"path": "/usr/bin/gh", "sha256": "0" * 64}` (never executed) and `RUN(argv,
timeout)` ignores the argv's `gh` path, reads the 40-hex commit from the
`--search` argument and returns the JSON text of a one-element list for it:
`{"number": N, "url": "https://github.com/OWNER/REPO/pull/N", "state":
"MERGED", "headRefOid": <that commit>}` (the other fixed fields absent, which
`_derive` accepts), so every anchor reads `state: "merged"`. The finished item
gets a review folder under `.ai-review/` with a tracked file. The `read_errors`
entry is made deterministically, not by `chmod 000` (readable for root, which
some CI containers run as): `<archive-dir>/.removing` is created as a symlink
(`_removing_ids` records `symlink: not followed`), which also gives the
`removing` key's list. If the entry could not be produced (the key empty), the
test skips rather than passes. The subprocess is the only place the real script
runs; the Manager's own `retention.py` is still exercised only through its
subprocess of the installed script, not through these seams.

**Refusal order, one cause and one next step each.** Checked in this order; the
first that applies is the only note printed. The note is two lines:
`retention: not available: CAUSE` then `  next: STEP` (two-space indent, so the
command's own `next:` line stays the only line that starts at column 0).

1. Not managed (`status` only): cause "the repository is not managed by
   workflow-manager"; step `workflow-manager bootstrap TARGET`.
2. No script (Workflow before 2.20.0, or the file is missing, a link or not a
   regular file): cause "the repository has no scripts/workflow_retention.py
   (the Workflow release that ships it is 2.20.0 or later)"; step
   `workflow-manager update TARGET`.
3. The interpreter cannot start (`sys.executable`, the Python running the
   Manager, is missing or not executable): cause the OS error; step "reinstall
   workflow-manager (`pipx reinstall workflow-manager`)".
4. Timeout: cause "the report did not finish within 300 seconds"; step "run
   `python3 -I scripts/workflow_retention.py report` in the repository" (the
   "run the script directly" step; case 6 reuses it).
5. The script refuses (exit 2): its stderr `error: CODE: MESSAGE` and
   `next step: STEP` lines are passed through as cause and step. This covers
   `repository_unknown` (no GitHub origin), `state_missing`, `state_invalid`,
   `path_unsafe`, `usage`.
6. Any other failure (another exit status, stdout that is not one JSON object,
   `kind` not `retention-report`, a `schema_version` other than 1): cause names
   what was seen; step "update workflow-manager to the newest release" for a
   schema or kind mismatch, otherwise the step of case 4.
7. The forge could not be asked for any candidate: the report is valid, at
   least one item was tried (N >= 1), every item tried is a `not_finished`
   entry with reason `query_failed:CODE`, and none is finished or kept. With
   mixed codes the first code in report order is named and the count is N.
   Cause "the forge could not be queried (CODE, N items)" (`gh` missing, not
   signed in, offline); step
   "install gh and run `gh auth login`, then run the command again".

**A partial report is never shown as clean.** When the report parsed but is
incomplete, the section opens with `retention: INCOMPLETE` and says why, and
its numbers are labelled lower bounds. Incomplete means `complete` is false (the
`read_errors` are listed, at most five paths, then a count) or at least one
`not_finished` entry has a reason starting `query_failed:` (some items could
not be checked against the forge: listed by id and code, at most five). The
step is "fix what is named, then run the command again".

**What a complete report shows.**

    retention (read-only; the Workflow script made one forge query per finished item):
      repository OWNER/NAME, archive directory DIR, time to live N days
      finished work items: N (review folders MiB), kept as the most recent: K
      with an archive: A of N (U unknown); archive store: S archives, P prunable (older than N days)
      interrupted removals: none | ID, ID
      next: THE WORKFLOW'S COMMAND

`A` and `U` come from `finished[].archive` only; `S` is `totals.archives` and
`P` is `totals.prunable`, both labelled as the archive store's, so a store with
one unrelated archive and no finished item prints "with an archive: 0 of 0;
archive store: 1 archives, 0 prunable", never "1 of 0". Sizes use binary units (KiB, MiB, GiB). The `removing` key is optional (absent
on 2.20.0 and 2.21.0): absent is shown as "not reported by this Workflow
release", never as none. Next commands are the Workflow's own, printed for the
user to run in the repository (only those the installed release has, see
"Capability"); the Manager never runs them: for the first
finished item whose `archive.present` is false and `archive.readable` is true,
whose `review_folder.present` is true and whose `review_folder.tracked_files`
is 0 (the only items `archive` accepts: it refuses `review_folder_absent` and
`tracked_files` otherwise), `python3 -I scripts/workflow_retention.py archive
ID --apply` (run it without `--apply` first for a dry run); for the first
finished item with `archive.present` true, `archive.readable` true,
`review_folder.present` true and `review_folder.tracked_files` 0, whose id is
not in `removing` (the only items `remove` accepts: it refuses `tracked_files`,
and `leftover_conflict` when the item has a leftover and its folder is back),
`python3 -I scripts/workflow_retention.py remove ID --apply`; for an
interrupted removal, an id in `removing` that is in `finished` with
`archive.present` and `archive.readable` true, `tracked_files` 0 and
`review_folder.present` false (the only state `remove` resumes), the same
`remove ID --apply`. Any other `removing` id is listed under "interrupted
removals" and gets no command: it is not in `finished`, its archive is absent or
unreadable, Git tracks files under its folder, or its folder is back; the
script's own refusal names the fix. An
archive with `readable` false is unknown, never "without an archive" and never
"with an archive": it qualifies for neither command. A finished item with
neither a review folder nor an archive (a fresh clone, or a folder deleted by
hand) qualifies for no command and is counted in "finished" only. Every printed
Workflow command meets each precondition of the script's command that the
report exposes (`review_folder.present`, `tracked_files`, `archive.present` and
`readable`, membership in `finished` and `removing`), so the script does not
refuse it on those. The report does not expose the archive index
(`already_indexed` after a hand prune), a `.partial` or non-regular file at the
archive path, `zstd` or the file systems (`cross_device`); the script refuses
those itself with its own next step, and the plan claims nothing about them. Prunable archives get no command: the
prune is a later Workflow row, and the section says so. With nothing to do the
step reads "nothing to archive". At most one next step is printed (the first
that applies, in the order archive, remove, interrupted removal), so the
operator has one thing to do.

**Why subprocess and not import.** The script's contract is its JSON and exit
status; the Manager is release-agnostic and the installed script is whatever
Workflow release the repository runs. `python3 -I` also keeps a stray
`json.py` or `sitecustomize` in the repository out of the interpreter.

## 2. Tests

All hermetic: a stub `scripts/workflow_retention.py` written into a scratch
managed repository (a copy of the pristine one the other CLI tests use), no
network, no `gh`. No test writes into this repository.

* `tests/test_retention_status.py`:
  * default off: `status` and `doctor` without `--retention` print no
    `retention` line and never start the script (the stub appends to a marker
    file outside the repository; it stays absent). "Unchanged" is proved inside
    one run, with no history outside the checkout (a depth-1 CI checkout has
    no `3019c95`, and a worktree would write into `.git`): stdout, stderr and
    exit code of both commands are byte-identical with the retention script
    present, absent, and replaced by a stub that would print a section; so the
    option off cannot depend on the script. The existing `status` and `doctor`
    suites (`test_operator_ux_report.py`, `test_doctor_cli.py`) stay green
    unchanged and carry the rest of the default-output guarantee. No golden
    file is added.
  * archive coverage versus store totals (EPR-005): for both commands, a report
    with no finished item and one unrelated archive in the store (`totals.archives`
    1, `totals.finished` 0) prints "with an archive: 0 of 0" and "archive store:
    1 archives"; a report whose `totals.archives` exceeds the finished items
    that have an archive (archives of `kept_recent` and `not_finished` items,
    one finished item without an archive, one with an unreadable archive) prints
    A from `finished[].archive` only, U for the unreadable one, and S and P from
    the totals; changing only `totals.archives` or `totals.prunable` in the
    fixture changes only the store figures, and changing only a `finished`
    entry's `archive` changes only A and U. One check uses the real script's
    output of the recipe below with an extra archive file for an unrelated id
    when the copied script is present.
  * on, complete report: the lines above for `status` (placed before the final
    `next:`) and `doctor`; exit codes unchanged for a clean and for a
    problem-carrying repository; the `removing` key present, empty and absent;
    next-step choice (archive, remove, interrupted removal, none); each printed
    Workflow command equals the form the Workflow documents; a finished item
    with its folder absent, one with tracked files and one with an unreadable
    archive each print no `archive` (and no `remove`) command; an archived
    finished item with tracked files, a `removing` id whose folder is present,
    and a `removing` id that is not in `finished` each print no `remove`.
  * capability: the installed record at 2.20.0 (an eligible unarchived item
    gets no `archive` command, only the update step), at 2.21.0 (an archived
    item gets no `remove`, only the update step) and at 2.22.0 (both offered);
    a missing or unparseable version offers none.
  * relative target: `status --retention` and `doctor --retention` with a
    relative target (`nested/repo`, run from its parent) and one whose path
    contains spaces, using a stub that records its `argv` and `cwd`: both are
    absolute and equal to the resolved target, the report renders, and the exit
    code equals the baseline.
  * malformed but valid-looking reports: `{"schema_version":1,"kind":"retention-report"}`
    alone, each required field missing and wrongly typed, a `finished` entry
    without `archive`, stdout that is not UTF-8, exit 2 without the refusal
    lines, and a valid report with stderr warnings (renders): each failure is
    one case-6 note, no traceback, the baseline exit code and no writes; an
    unknown extra key and an absent `removing` still render.
  * incomplete: `complete` false with `read_errors`; `query_failed` entries,
    some and all (all becomes the case 7 note, with mixed codes); no item
    queried (nothing at `MILESTONE_COMPLETE`) renders as a complete report with
    nothing finished, not as case 7; never worded as clean.
  * every not-available case in the refusal order (not managed, script absent,
    a link in place of the script, non-executable interpreter via a patched
    `sys.executable`, timeout, script refusal passed through with its code and
    step, exit 1, bad JSON, wrong kind, schema 2, all queries failed): exactly
    one cause and one `  next:` step, exit code equal to the baseline, no
    traceback, stdout and stderr free of `Traceback`.
  * timeout leaves no process: the stub spawns a sleeping child and sleeps;
    with the timeout patched to a fraction of a second the call returns, the
    child's pid is gone, and the orphan check of the runner stays clean.
  * no-write proof for the new path, once per failure path and once for the
    success path: a hash of the whole scratch tree (including `.git`) before
    and after is equal, and no `__pycache__` appears.
  * two real-script cases: (1) the repository's real `scripts/workflow_retention.py`
    and `scripts/workflow_forge.py` copied into a scratch managed repository
    with an `origin` remote of a GitHub URL (no fetch) and a state with no
    `MILESTONE_COMPLETE` item, so the real script runs with no forge query
    and the section renders the real JSON (empty `finished`, `kept_recent` and
    `read_errors`); `HOME` is set to a scratch directory so the default archive
    root does not read the developer's machine; (2) the conformance recipe of
    section 1 ("Stub shape is checked against the real script"): four merged
    items (three kept, one finished), one open item, a symlinked `.removing`,
    driven through the script's `run`/`resolve` seams in a test-only `-I -B`
    subprocess, never a stub `gh` in a temp directory. Both skip when the
    copied files are absent.
* `tests/test_docs.py`: `docs/retention.md` is in `USER_PAGES` and
  `COMMAND_PAGES` of `tools/check_docs.py` and passes its header, internal-id
  and command-parse rules (its `workflow-manager status --retention TARGET`
  and `doctor --retention TARGET` examples are parsed); the new page is in the documentation index and
  `docs/exit-codes.md` carries the new row; `docs/retention.md` has the
  cause-and-step table matching the refusal order (a test builds each cause
  from `retention.py` and finds its text on the page). The page also states that "with an archive" counts finished items
  and that the archive store's totals are separate (EPR-005).
* `tests/test_operator_ux_docs.py` stays green unchanged: the exit-code rows it
  checks are not edited, and the new row is added to the documentation test
  only.

## 3. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The opt-in retention section, its tests and docs | - | 3 | 1 |
| CP2 | Roadmap and active-milestone bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the opt-in retention section

**Files:** `src/workflow_manager/retention.py`, `src/workflow_manager/cli.py`, `tools/check_docs.py`, `tests/test_retention_status.py`, `tests/fixtures/retention_report.json`, `tests/test_docs.py`, `docs/retention.md`, `docs/exit-codes.md`, `docs/verify.md`, `docs/update.md`, `docs/README.md`.

`retention.py`: the subprocess call, the parse, the refusal order and the
renderer of section 1 (pure functions over a result, so the tests render
without a subprocess where they can). `cli.py`: the `--retention` option on
`status` and `doctor` and the two print points; nothing else in either command
changes. Docs: the new `docs/retention.md` (what the section shows, the cause
and step table, the Workflow commands the user runs, that the Manager never
runs them), a row in `docs/exit-codes.md` stating that the option never changes
an exit code, the distinction between finished-item archive coverage and the
archive store's totals, a paragraph in `docs/verify.md` (the `status` page) and in
`docs/update.md` (the `doctor` page), and the index entry in `docs/README.md`.
Wording follows the Operator UX rules already in `docs/`: the real program
name, one cause, one step, no internal ids on a user page; the new page opens with the
required `> For: ... Last checked with: ...` line and is linked from the index.
`tools/check_docs.py` gains `docs/retention.md` in `USER_PAGES` and
`COMMAND_PAGES`, so those rules are enforced on the page rather than claimed
(the file is classified: excluded at the plan stage, protected at the
implementation stage).

Evidence: the new tests fail first at `3019c95` (no option) and are green
after; `python3 tools/check_docs.py` is green with the page registered; `python3 tests/run_all.py --select test_retention_status.py`, `--select
test_docs.py`, `--select test_operator_ux.py`, `--select
test_operator_ux_docs.py`, `--select test_operator_ux_report.py` and `--select
test_doctor_cli.py` green; the full gate `python3 tests/run_all.py` green.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 17 of `docs/ROADMAP.md` is marked Current when the plan starts and Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone. No version is
edited: the `feat:` pull request title releases the minor.

Both files stay excluded at both stages, as in every item: the workflow's own
commands write them after technical approval, so they are bookkeeping, not a
reviewed deliverable. Every deliverable (CP1) is implementation-protected.
<!-- /CP2 -->

## 4. Functional review (for the checklist)

Workspaces: every flow except the last uses a **scratch managed repository**
(a copy of a bootstrapped repository under the run's scratch directory) with a
**stub** `scripts/workflow_retention.py` that prints a fixed JSON report or
exits as told, so no `gh` and no network are involved. Flows: default
`status`/`doctor` unchanged and fast; `--retention` with a complete report
(with and without `removing`); incomplete; each not-available cause; a hung
script (timeout patched down through a stub that sleeps) leaves no process; no
file changes in the scratch tree. The **one real-script flow** runs
`status --retention` and `doctor --retention` read-only against a scratch clone
of this repository (installed Workflow 2.22.0 script, real forge): never run
`archive` or `remove` there, and compare the scratch tree before and after.

## 5. Risks

* The report's wall time is the script's: 20 to 40 seconds for 25 items. The
  300-second timeout covers about ten times that; a repository with many more
  finished items hits case 4 and is told to run the script directly.
* A forge failure is not a script refusal: the script exits 0 and lists the
  items as `not_finished`. Case 7 and the incomplete rule exist so that this is
  never shown as "no finished items".
* The section is informational and never changes an exit code, so a script that
  gates on `status` or `doctor` cannot be broken by a retention failure.
* The artifact declaration's generated template classifies `src/` and `tests/`
  at both stages and leaves the new `docs/` pages and `scripts/` to be checked;
  self-review confirms every path of CP1 and CP2 is classified at both stages
  before the bundle is generated.

## 6. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
