# Workflow Manager: Operator UX, Messages That Say What To Do Next (Revision 14)

`work_item_id: workflow-manager-operator-ux` -- `governing_workflow_version: "2.2"`

**Deliverable:** a Manager release (1.8.0, from a `feat:` pull-request title)
in which the tool, not the documentation, tells an operator what to do next.
Every user-facing error, refusal, warning and note of the Manager CLI names
its cause and one concrete next step (a command, a flag, or a page), using
the real program name (`workflow-manager`) and the real options. Where an
operator used to read `WORKFLOW_STATE.json` to learn what is in flight,
`status` now says so (decision D-3).

**Work item type:** `process` (Manager tooling; no Workflow release).
**Base commit:** `218155dd7ba6e1b59edb91c93da299cfeeb7e870` (tip of `main`;
Workflow 2.9.1 installed here with automatic gates, no `GATE_POLICY.json`).
**Branch:** `milestone/workflow-manager-operator-ux`. The milestone reaches
`main` through one pull request, opened and merged by the user. Its title is
`feat: ...`, which releases Manager 1.8.0.
**Scope source:** `docs/ROADMAP.md` item 7, "Operator UX"; the user's approval
of 2026-10-10. Size target: the size of Update ergonomics or smaller.

## 1. Goal and fixed inputs

1. **Inventory first** (section 2): every user-facing message of `bootstrap`,
   `update` (with `--dry-run` and `--force`), `verify`, `status`, `uninstall`,
   `releases`, `package verify`/`build`, `doctor`, and the argument, source,
   cache and priming paths they share, each with its code location, what the
   operator can do today, and the gap. Cited from the code at the base commit,
   and the CLI was run on throwaway repositories to read the real output.
2. **Fix the gaps** (section 3). A message keeps its cause line; a `next:` line
   names the one thing to do. The example from the brief:
   `error: release 2.9.1 is not published: this Manager has no pin for it ...
   --release-dir` now also says that a newer Manager pins a published release
   and where to learn how to upgrade the Manager.
3. **Two parked follow-ups from Update ergonomics:** `doctor --help` says
   "Exit 0: nothing found" although exit 0 also covers a notes-only report
   (row A4), and the `not-verified` note's parenthetical omits the
   integrity-failure cause, although `_installed_resolves` catches
   `ReleaseIntegrityError` too (row F-n).
4. **Stay in the Manager's role.** The Manager installs and checks the
   Workflow. It reads `WORKFLOW_STATE.json` and writes nothing of the
   Workflow's: no state file, no `.ai-review/`, no approval. It prints no
   "next Workflow step" (that is the Workflow's and the Controller's). D-3
   limits what it surfaces to facts the Manager already reads for `doctor`.
5. **Exit codes stay stable** (`docs/exit-codes.md` is the contract). Messages
   change; codes do not. The only codes that move are the four that D-5,
   D-14 and D-15 argue for: (a) a crash after a half-written install (a directory, or a
   regular file standing where a directory goes: T13, T18, T19), a traceback's
   exit 1 becoming a refusal's exit 2; (b) a record that cannot be read
   because a directory stands at `.workflow-manager/installation.json` (T20),
   which takes T8's cause and so T8's exit 2; (c) `status` of a
   **managed** repository, which exits 0 today for a clean repository and exits
   **1** after this milestone whenever it cannot prove that its writes stay
   outside the target and its `.git` directory: Git cannot run or answer, or
   the release cache, its lock or a temporary directory lies inside either
   (C5, 3.5a, D-14); `status` of an **unmanaged** target keeps today's
   behavior and exit 0, with or without release options (3.5a); and (d)
   `doctor` of a `--release-dir` whose manifest crashes today with an
   uncaught exception (an unhashable `workflow_version`, a `location` that is
   not text: R17), a traceback's exit 1 becoming the exit 2 that `doctor`
   already gives every other unusable release (3.3a, D-15). A manifest shape
   that **succeeds** today at any command keeps succeeding with the same exit
   (D-16). Every other exit code of every command is unchanged.
6. **Hermetic tests.** Subprocess tests use `support.cli_env()` (which carries
   `HERMETIC_GIT_ENV`, so no host Git config leaks in: a system git-lfs filter
   broke CI once and not the local gate). Repositories come from
   `fixture.init_git_repo`; the release cache is the shared one or a
   temporary one; the network is never used (a missing release is a
   `--release-source` pointed at an empty or tampered directory). A
   check that Git cannot run uses an empty `PATH`, so it fails closed.
7. **Out of scope:** any Workflow release, any change to a pin, the
   Controller, a new command, a second state reader, and any write to a
   target repository beyond what the commands already do.

### 1.1 What "done" means

- Every row of section 2 marked "gap" is fixed as section 3 says, or is listed
  in section 3.6 with the reason it stays.
- One test asserts each changed message: the cause text and the next step
  (the command, flag or page) are in the real output, the commands in `next:`
  lines parse under `build_parser()`, and the exit code is the old one.
- `--help` of the program, `doctor`, `bootstrap`, `update`, `verify`,
  `status`, `uninstall`, `releases` and `package` is asserted.
- `docs/common-problems.md` and `docs/exit-codes.md` quote the new messages
  exactly (a test compares them with real output); every other page that
  quoted a changed message is updated.
- `python3 tests/run_all.py` is green; `tools/check_docs.py` is clean.

### 1.2 Requirements

| Id | Requirement |
|---|---|
| REQ-1 | The inventory (section 2) is complete and cited, and every gap in it is fixed or kept for a stated reason (3.6) |
| REQ-2 | Each changed message names its cause and one concrete next step, using the real program name and options; every printed command parses |
| REQ-3 | The two parked follow-ups are folded in: `doctor --help`'s exit-0 wording and the `not-verified` note's parenthetical |
| REQ-4 | The Manager surfaces what is in flight instead of requiring a read of the state JSON, read-only, with no new command and no write to any Workflow state |
| REQ-5 | Every exit code is stable (`docs/exit-codes.md`), except the moves D-5, D-14 and D-15 argue for: T13, T18, T19 and T20 (each a traceback's 1 becoming 2), `status` of a managed repository exiting 1 where it cannot prove its writes stay outside the repository (C5; Git unavailable included), and `doctor` exiting 2 for a manifest that crashes it today (R17); a manifest shape that succeeds today keeps its exit (D-16) |
| REQ-6 | Tests are hermetic, assert each changed message (cause and next step) and the help text |
| REQ-7 | `docs/common-problems.md`, `docs/exit-codes.md` and every page quoting a changed message match the new output exactly |
| REQ-8 | `docs/ROADMAP.md` carries item 7 as the current Next item (Done at acceptance), and `docs/ACTIVE_MILESTONE.md` describes the milestone |

## 2. Inventory of what the operator sees today

Columns: message as printed (`...` marks a variable part); where
(`file:function`, from the base commit); exit; what the operator can do
today; the gap. `X` is the target path as typed. Rows marked **OK** were read
and need no change; they are here so the inventory is complete.

### 2.1 Arguments and help (`src/workflow_manager/cli.py`)

| ID | Message | Where | Exit | Next step today | Gap |
|---|---|---|---|---|---|
| A1 | `usage: workflow_manager [-h] ...` and `workflow_manager: error: unrecognized arguments: --release-dir /x` (a global option written after the command) | `cli.py:build_parser` (`prog="workflow_manager"`) | 2 | Nothing in the output; `docs/exit-codes.md` says to put global options first | The program is named `workflow_manager` (the module), not `workflow-manager`; no hint that `--release-version`, `--release-source`, `--release-cache` and `--release-dir` go before the command |
| A2 | `workflow_manager bootstrap: error: the following arguments are required: target`; `invalid choice: 'bogus' (choose from ...)` | argparse via `build_parser` | 2 | The message names the missing argument and the choices | Only the program name (A1) |
| A3 | `workflow-manager: --manager-root is deprecated and will be removed in a later release. ... use --release-dir <dir>` | `cli.py:MANAGER_ROOT_DEPRECATION`, `main` | continues | Names the replacement option | **OK** |
| A4 | `doctor --help`: "Exit 0: nothing found; 1: warnings; 2: could not check." | `cli.py:build_parser` (`doctor`) | n/a | n/a | Wrong: exit 0 also covers a notes-only report (`Report.doctor_exit_code`: only `blocked` and `warning` give 1). Parked follow-up |
| A5 | `--help` of `bootstrap`, `update`, `verify`, `status`, `uninstall`, `releases`, `package`: no description (`sub.add_parser(name)` with no `help=`); `--release-version` has no help text | `cli.py:build_parser` | n/a | n/a | An operator reading `--help` cannot learn what each command does, that `--release-version` goes before the command, or which exit codes to expect |

### 2.2 The target repository and the installation record

| ID | Message | Where | Exit | Next step today | Gap |
|---|---|---|---|---|---|
| T1 | `error: no directory at X` | `install.py:bootstrap` (`InstallError`) | 2 | None printed | No next step |
| T2 | `error: X is not a Git repository` | `install.py:bootstrap` | 2 | None printed (`docs/install.md` says `git init`) | No next step; a sub-directory of a repository fails too (only `X/.git` counts) and the message does not say so |
| T3 | `error: X is already managed; use update() to move it to another release` | `install.py:bootstrap` (`AlreadyManagedError`) | 2 | `update()` is a Python function, not a command | Wrong next step: no `workflow-manager update X` |
| T4 | `error: X is not a managed repository; use bootstrap() first` | `install.py:plan_update` (`NotManagedError`); `cli.py:cmd_dry_run` | 2 | `bootstrap()` is a Python function | Wrong next step |
| T5 | `error: X is not a managed repository; nothing to verify` / `nothing to check` | `cli.py:cmd_verify`, `cmd_doctor` | 2 | None printed | No next step |
| T6 | `error: X is not a managed repository (no .workflow-manager/installation.json)` | `installation.py:Installation.read` (`FileNotFoundError`), reached by `uninstall` | 2 | None printed | No next step; says nothing about where to look |
| T7 | `not a managed repository` (stdout) | `install.py:Status.__str__`, `cli.py:cmd_status` | 0 | None printed | No next step. The exit stays 0 (contract) |
| T8 | `error: the installation record at P is unreadable (E). Delete .workflow-manager/ and re-run bootstrap to reinstall; repository-local state is not stored there and is not affected.` | `installation.py:Installation.read` (`CorruptInstallationError`; a record that is not UTF-8 raises a bare `UnicodeDecodeError` today, a `ValueError` that `main` prints as `error: 'utf-8' codec can't decode byte ...` with exit 2 and no path, and it joins this row) | 2 | Prose only | The next step has no command and no path; it names no release, and a bootstrap after the deletion installs the *newest* release, so a repository that was on an older one meets collisions it did not cause (and `--force` would upgrade it silently) |
| T9 | `error: unsupported installation schema_version N; this workflow-manager understands 1` | `installation.py:Installation.from_dict` (a bare `ValueError`, not wrapped, so `read` does not call it a corrupt record; any value other than 1 prints it: `None`, `"1"`, `0`, `2`) | 2 | None | No next step. Only an integer above `SCHEMA_VERSION` means a newer Manager; any other value is a damaged record (the T8 cause) |
| T10 | `error: unknown install profile 'x'` | `install.py:bootstrap`, `plan_update` | 2 (`InstallError`) | None | `--profile` has `choices`, so `bootstrap` cannot reach it, **but `update` and `update --dry-run` can**: `plan_update` takes the profile from the installation record when `--profile` is not given (`install.py:plan_update`: `profile = profile or current.profile`), and a record that parses but holds `"profile": "bogus"` (damaged, or written by a newer Manager that has another profile) reproduces it. No next step (Round 5 I-6) |
| T11 | `refusing to update: these release files were modified locally and would be overwritten:` + list, then `re-run with --force to discard those local edits` | `install.py:plan_update` (`DriftError`), `cli.py:main` | 2 | Names the flag, not the command, and not how to keep or see the edit | Partial: no command, no `--dry-run`/`git diff` pointer, drops `--release-version` if the operator used it |
| T12 | `refusing to bootstrap: the repository already has its own file at these release paths:` / `refusing to update: this release needs paths the repository is using for something else:` + list, then `re-run with --force to replace those files with the release's` | `install.py:bootstrap`, `plan_update` (`CollisionError`), `cli.py:main` | 2 | `--force` named for every case | **Wrong for a directory in the way**: `_blocked_paths` entries (`occupied: a directory is in the way`) survive `--force`, so the advice cannot work. No command |
| T13 | `IsADirectoryError` traceback with `--force` when a directory stands where a release file goes (reproduced: `.claude/commands/milestone-plan.md/`) | `install.py:bootstrap` and `plan_update` skip `_collisions` when `force` | 1 | None; the install is half written | A crash instead of a refusal (D-5) |
| T18 | `NotADirectoryError` traceback when a regular file stands where a release *directory* goes (reproduced at the base: `git init a && touch a/.claude && python3 -m workflow_manager bootstrap a`, no `--force` needed) | `install.py:_write` (`mkdir(parents=True)`); `_collisions` and `_blocked_paths` test only the leaf (`path.exists()` is False when an ancestor is a file) | 1 | None; release paths sort by name, so an ancestor such as `scripts` that is a file fails after the `.claude/...` files are written | A crash with a half-written install, with or without `--force` (D-5) |
| T14 | Any other `OSError` while installing (permission denied, disk full) ends as a traceback | `cli.py:main` has no `OSError` handler beyond `FileNotFoundError` | 1 | None | A traceback, with no cause named and no step; for `bootstrap`/`update` a re-run does not always finish the job (a disk-full write can leave a truncated file, which the re-run reports as modified or in the way). The handler sits in `cli.main`, so it also catches an `OSError` from the read-only commands (`verify`/`status` hitting `PermissionError` in `drift`'s `path.read_bytes()`), `uninstall` and `package`, for which "a partial write" and `--force` are false (D-6) |
| T15 | `verify`/`status` problem lines: `N problem(s)` then `modified: P`, `missing: P`, `unexpected: P (present but not recorded as installed)`, `not-executable: P`, `modified: .gitignore (workflow entries removed: ...)`, `modified: CLAUDE.md (the managed section differs from the release's)`, `release: ...`, `version: installed A, release B` | `install.py:drift`, `verify`; `cli.py:cmd_verify`, `cmd_status` | 1 | None printed (the pages say `git checkout -- <file>` or `update --force`) | No next step, and the right one depends on the line |
| T16 | `status` of a managed repository: `workflow V (full profile) -- clean` and `source:` lines | `cli.py:cmd_status`, `install.py:Status.__str__` | 0/1 | Reading `WORKFLOW_STATE.json` to see what is in flight | Nothing about work in flight (D-3) |
| T19 | `FileExistsError` traceback when a regular file stands at `.workflow-manager` (reproduced at the base: `git init a && touch a/.workflow-manager && python3 -m workflow_manager bootstrap a`) | `installation.py:Installation.write` (`path.parent.mkdir(parents=True, exist_ok=True)`); `is_managed` tests only `.workflow-manager/installation.json`, so it is False; the record is written by `installation.write`, not `_write`, and is in neither `incoming` nor `_other_written_paths` | 1 | None; every release file, state template and merge is already written, the record is not | A crash with a fully written, unrecorded install (D-5) |
| T20 | `IsADirectoryError` traceback when a directory stands at `.workflow-manager/installation.json` | `installation.py:is_managed` (`exists()` is True), then `Installation.read`'s `read_text`, which `read` does not wrap (only `IsADirectoryError` is wrapped under the plan; a `PermissionError` is T14 and keeps exit 1) | 1 | None | Every command reaches it; it is a record that cannot be read, the T8 cause (D-5) |
| T17 | Success lines: `bootstrapped workflow V ...`, `updated X to workflow V`, `(no change)`, `removed N managed files ...` | `cli.py:cmd_bootstrap`, `cmd_update`, `cmd_uninstall` | 0 | The pages say verify, then review and commit | No next step in the output (D-7) |

### 2.3 Releases, sources, the cache and packages

| ID | Message | Where | Exit | Next step today | Gap |
|---|---|---|---|---|---|
| R1 | `error: no Workflow release is published: this Manager pins none. Install an unpackaged release with --release-dir <dir>.` | `cli.py:_default_version` (`ReleaseNotPublishedError`) | 1 | Names `--release-dir` | Not a command (the option goes before the command); no pointer to upgrade the Manager |
| R2 | `error: release V is not published: this Manager has no pin for it (pinned: ...). An unpublished release installs only from a local directory, with --release-dir.` | `source.py:ReleaseCache._pin` (`ReleaseNotPublishedError`) | 1 | Names `--release-dir` only | The brief's example: does not say a published release needs a newer Manager, nor how to upgrade it |
| R3 | `error: cannot fetch URL-or-PATH: REASON` | `source.py:ReleaseSource.fetch` (`ReleaseUnavailableError`) | 1 | None printed (pages: connect once, or a mirror) | No next step; differs for a URL source (network) and a directory source (missing `<version>/`) |
| R4 | `refusing release source 'S': use https://, file://, or http:// to a loopback host`; `release source 'S' has no {version} field` | `source.py:_check_url`, `ReleaseSource.__init__` | 1 | The first names the allowed schemes; the second names the missing field | Second: does not show the form (`.../{version}/`) or where the value came from. First: **OK** |
| R5 | `refusing redirect from A to B: it drops https`; `URL is larger than N bytes` | `source.py:_RedirectHandler.redirect_request`, `_copy_capped` | 1 | None | No next step |
| R6 | `cannot use the release cache C: REASON (choose another with --release-cache or $WORKFLOW_MANAGER_RELEASE_CACHE)`; `cannot discard the cache entry E (WHY): REASON. Remove it by hand, or choose another cache ...` | `source.py:ReleaseCache._locked`, `_discard` | 1 | Names the option and the variable | **OK** |
| R7 | `cannot store release V in the cache C: REASON` | `source.py:ReleaseCache._fetch` | 1 | None | No next step (disk space, permissions, or another cache) |
| R8 | `release V's archive does not match its pin: downloaded D, SHA256SUMS lists S, the pin records P` and the manifest-asset and carried-manifest variants | `source.py:ReleaseCache._fetch` (`ReleaseIntegrityError`) | 1 | None printed (pages: retry once; if it persists, do not install and report it) | No next step in the output; "report it in the Manager repository" is impossible because the repository has Issues turned off (D-9) |
| R9 | `release V's cache entry changed while it was being copied, twice: ...` | `source.py:ReleaseCache.resolve` | 1 | None | No next step (another process is writing the cache) |
| R10 | `the pin file P is malformed: ...` | `source.py:load_pins` (`ReleaseIntegrityError`) | 1 | None | No next step: the Manager's own pin file is damaged, so the Manager needs reinstalling |
| R11 | `D is not a release: ...`; `D holds release A, not the requested B`; `D claims published release V, but its manifest.json has digest A and the pin records B`; `release V at D fails verification: ...`; `cannot snapshot the release at D: ...`; `unsafe manifest location L`; `L is a link` | `source.py:local_release`, `_copy_snapshot` (`ReleaseIntegrityError`) | 1 | None | No next step for a `--release-dir` operator (use an unmodified copy, or drop the option to use the published package) |
| R12 | `release V is damaged: L has digest A, its manifest records B. Refetch it, or rebuild the release directory, before installing.` | `release.py:Release.read_verified` | 1 | Prose: "Refetch it" without how | The command and the cache path are missing |
| R13 | `A has digest D, not S` (`package verify --sha256`); `A is not a readable package: ...`; `A is empty`, `carries no manifest.json`, `unsafe path`, `does not match its manifest entry`, ... | `cli.py:cmd_package`, `package.py:extract_package`, `_extract_into` (`ReleaseIntegrityError`) | 1 | None printed (the pages: download again and check `SHA256SUMS`) | No next step |
| R14 | `P is not a release: no manifest at P/manifest.json`; `release V at D fails verification: ...` | `package.py:build_package` | 1 | None | No next step (`package build` takes a directory holding `manifest.json`) |
| R17 | A manifest that parses as JSON but has the wrong shape. **Crashes today** (a traceback, exit 1): a `null`, list, or `artifacts`/`templates`-less manifest, and a numeric or `null` artifact `location`, in `package build` (`package.py:build_package` catches `FileNotFoundError`, `KeyError` and `ValueError` only); a numeric or `null` `location` (`source.py:_copy_snapshot`, `location.split`) and an **unhashable** `workflow_version`, a list or object (`source.py:local_release`, `pins.get(version)`, before `_copy_snapshot` runs), in every `--release-dir` command. **Succeeds today:** a scalar `workflow_version` (`null`, a number, a boolean, `""`) for `package build` (exit 0 in every case), `bootstrap` and `update` (exit 0, the value written to the record), and `update --dry-run` (exit 0 for `null` and `""`; exit 2, `not a release version`, for a number or boolean). The full per-command table is 3.3a | `package.py:build_package`, `source.py:local_release`, `_copy_snapshot` | 1 (an uncaught exception's exit), except where the table of 3.3a records another | None; a traceback | A crash where R11/R14 assume a classified `ReleaseIntegrityError`; the `OSError` handler of D-6 catches none of them (Round 5 I-6, Round 7 R2-I-4) |
| R15 | `workflow-manager: no Workflow release is published` (stderr, `releases`) | `cli.py:cmd_releases` | 0 | None | Cannot occur with shipped pins; **OK** |
| R16 | `workflow-manager: discarding cache entry E: WHY`; `using a local copy of published release V from D` | `source.py:_log` | n/a | Informational | **OK**: they report an action taken, not a failure |

### 2.4 Read-only commands (`doctor`, `update --dry-run`)

| ID | Message | Where | Exit | Next step today | Gap |
|---|---|---|---|---|---|
| C1 | `error: could not resolve the target release: CAUSE` | `cli.py:cmd_doctor` | 2 | The cause (R1-R14) with whatever next step it has | Inherits R-rows; no next step of its own |
| C2 | `the release cache C lies inside H: ... choose another with --release-cache or $WORKFLOW_MANAGER_RELEASE_CACHE`; `the release cache entry L resolves to R, inside H: the repository is never written by this command`; `the release cache entry E holds a link (K); remove the entry or choose another cache with --release-cache`; `a temporary directory named in the environment (D) lies inside H; unset it or point it outside the repository` | `compatibility.py:plan_destinations` (`ContainmentError`) | 2 | The first, third and fourth name a fix | The second names none |
| C3 | `could not check containment: git rev-parse FLAG failed in X`; `... printed P, which is not a directory`; `no temporary directory outside the target` | `compatibility.py:protected_set`, `plan_destinations` | 2 | None | No next step (Git not runnable; no writable temporary directory) |
| C5 | `status` writes inside the target: it resolves its release through `_release_for_target` and `_resolve` with no validated destinations (`cli.py:cmd_status`, unlike `doctor` and `update --dry-run`, which call `_readonly_destinations` first), so the cache resolver creates directories and a lock file (`source.py:ReleaseCache._locked`; reproduced: `.git/status-cache/2.9.1.lock` created before an error against an empty local source), and a `TMPDIR` inside the target is used for the snapshot | `cli.py:cmd_status`, `source.py:ReleaseCache._locked` | 0/1 | None | Breaks the no-write claim; the command must be contained like `doctor` (Round 5 I-2). Containment runs `git rev-parse --absolute-git-dir` (`compatibility.py:protected_set`), so a clean `status` of a **managed** repository that exits 0 today with no Git on `PATH`, or with `--release-cache` inside `.git`, exits 1 after the change: the argued move (c) of section 1 item 5 (Round 6 I-3). An **unmanaged** target is outside the move: its `status` prints T7 and exits 0 today, with no Git needed and with or without release options, and keeps doing so (3.5a, Round 7 O-1) |
| C4 | `update --dry-run` refusal after the report (T11, T12) | `cli.py:cmd_dry_run` | 2 | As T11, T12 | As T11, T12 |

### 2.5 Report findings (`compatibility.py:build_findings` and `_item_findings`)

Findings print under `Findings --`; the `Recovery` section prints commands.

| ID | Finding | Where | Next step today | Gap |
|---|---|---|---|---|
| F-a | `blocked refused-drift` | `build_findings` | `Save the edits, then run the update with --force to discard them.`, plus a Recovery command | **OK** |
| F-b | `blocked refused-collision` | `build_findings` | The raw refusal only | No next step; a directory in the way needs a different one (T12) |
| F-c | `warning incomplete-inspection` (state or config unreadable, state missing from a managed repository, bad `schema_version`, declarations missing or unreadable, Git could not be run, partial clone, unknown phase) | `build_findings`, `_item_findings`, `read_repository` | `This report is not a clean bill of health.` | Names no fix per reason. A Workflow data file (state, config, `ACTIVE_MILESTONE.md`, a work item's declarations) that is missing, unreadable or malformed is the dangerous one: `update` recreates **every** missing state template from a blank one in one run (`install.py:plan_update`), `git restore` discards what is not committed, and a file that exists is left untouched by `update`, so no printed write repairs it safely. Under P1 (3.4) the Manager prints no write at all for these files |
| F-d | `warning v2.4.0-001` (the update rewrites paths the item protects) | `_item_findings` | `Finish or park the item first, or update before it starts.` | "Park" is undefined; no pointer to the page that explains the choice |
| F-e | `warning unclassified-paths` | `_item_findings` | `the item's declarations need review or amendment` | No pointer to the procedure (the installed `REVIEW_PROTOCOL.md`, "Repairing an artifact declaration after an approval") |
| F-f | `warning v2.4.0-001-old` | `_item_findings` | States the fact | No next step: choose a target of 2.6.0 or later |
| F-g | `warning legacy-active` | `build_findings`, `_retirement_advice` | The slash command, or why it is not offered | **OK** |
| F-h | `warning gates-change` | `build_findings` | Commit `GATE_POLICY.json` with the exact JSON before updating | **OK** |
| F-i | `warning downgrade` | `build_findings` | `A downgrade is unsupported.` and the posture lines | No next step: what to run instead |
| F-j | `warning worktrees`, `warning dirty-tree` | `build_findings` | Merge into every worktree; commit or set aside edits | **OK** |
| F-k | `note new-work-only` | `build_findings` | Informational | **OK** |
| F-n | `note not-verified`: "...(offline, or the release is not pinned), the comparison `workflow-manager verify` makes." | `build_findings` | Reassures; no next step | The parenthetical omits the integrity-failure cause (`_installed_resolves` also catches `ReleaseIntegrityError`); no command that shows the actual cause. Parked follow-up |

## 3. Design

### 3.1 Output convention (D-1, D-2)

- Stderr for an error: the existing cause line(s), then exactly one line
  `next: <step>`. A cause prints with the prefix `error: ` where it has it
  today; the drift and collision refusals (`DriftError`, `CollisionError`) print
  without it today (`cli.py:main`) and keep printing without it: their
  first words, which `docs/common-problems.md` and the docs-versus-output test
  quote, do not change, and the `next:` line replaces the old
  `re-run with --force ...` line. A step names a command in backticks,
  a flag, or a page. Success output on stdout may end with one `next:` line
  (D-7). Exit codes are not touched by the printing.
- Commands in a `next:` line are built from an argv list and rendered with
  `compatibility.render_command` (`shlex`), using the real program name
  `workflow-manager`, with the global options (`--release-version`,
  `--release-source`, `--release-cache`, `--release-dir`) before the command.
  **Quoting is not enough** (Round 5 I-5): `bootstrap -- -repo` parses, but
  rebuilding it as `bootstrap -repo` exits 2 under `build_parser()`. The
  builder (`compatibility.manager_command`, extended, with `git_command`
  already placing `-C X` first) puts every subcommand flag **before** the
  positional target and, when the positional starts with `-`, an
  end-of-options `--` immediately before it, so the printed line is
  `workflow-manager bootstrap -- -repo`. The same rule covers the one printed
  command whose positional is the target, `git init`: `git init -repo` fails
  with `unknown switch`, `git init -- -repo` works (Round 6 O-1). The
  `git -C X ...` forms need nothing, because `-C` takes the next word as its
  value. Every printed inspection `git` command is prefixed with `env GIT_NO_LAZY_FETCH=1`
  (Round 13 R4-I-1; Round 14 L13-O-1): the argv is `env GIT_NO_LAZY_FETCH=1 git -C X ...`, which is
  both an executable argv and a valid shell line. `compatibility.git_command(target, *args,
  inspection=True)` builds it (the default for the log/show/rev-parse readers); the unprefixed
  `restore`, `clean`, `status` and `init` lines are built with `inspection=False`. The
  command-parse test and the `printed_commands` extractor of `tests/test_doctor_cli.py` are
  extended to recognise a leading `env GIT_NO_LAZY_FETCH=1 git` (family Git, argv run as
  printed), and a test fails if a printed inspection command lacks the prefix or if the
  extractor skips a prefixed line. A test executes them.
  Update ergonomics' rule for printed commands is kept and extended: a test
  extracts every backticked `workflow-manager ...` command from every `next:`
  line of every case below and parses it under `build_parser()`.
- Pages are full URLs (`DOCS_BASE`, the repository's `main` branch), because
  an installed wheel has no `docs/` folder. A test resolves each URL's page
  and anchor with `tools/check_docs.py`'s slug rule against the working tree.
- Placeholders in a `next:` line are upper-case words (`DIR`, `MIRROR`), never
  `<angle brackets>`, so a pasted command still parses.

### 3.2 Where the next step is computed

- New module `src/workflow_manager/advice.py`: `DOCS_BASE`, `PROGRAM`,
  `page(name, anchor)`, and `next_step(error, context) -> str | None`, a table
  keyed by exception class (and, where one class has several causes, a
  `kind` attribute) returning the text. `context` is a small frozen
  dataclass, `advice.Context`, built by `cli.main` and the report commands,
  carrying the facts neither the exception nor `args` holds: `args` (the
  command, target and global options as typed), `installed_version` (read
  best-effort from the target's record, `None` when the target has no
  readable record), `cache_dir` (the release cache folder the run resolved,
  `None` when it did not get that far) and, for `verify`/`status`, the
  `Drift` list (each `Drift` carries its `kind`, its `path` and a `detail`;
  the deleted-state case is `missing` with detail `repository-local state was
  deleted`, `install.py:drift`), `release_dir_version` (the version of the
  release directory the run resolved, `None` when it used none: the input of
  the option-precedence rule, 3.3) and `missing_templates` (the state
  templates of `release.STATE_TEMPLATES`, `WORKFLOW_STATE.json`,
  `WORKFLOW_CONFIG.json` and `ACTIVE_MILESTONE.md`, that are absent from the
  target's working tree: a plain `exists()` check per path, the very set
  `update` would recreate from blank templates, `install.py:plan_update`) and
  `data_findings` (the full findings list of `build_findings`, `()` for a target that holds no
  Workflow data; Round 14 L13-I-2, see the predicate and its evaluation order below).
  **The withholding rule has one home, one definition and one predicate**
  (Round 8 L8-I-1, Round 9 L9-I-1, Round 11 R3-I-2). *The target holds
  Workflow data* means, by plain `lexists()` checks and no Git probe: a path
  exists at `.workflow-manager` (a record, a directory at it, a directory at
  `installation.json` or a file at `.workflow-manager`, readable or not) **or**
  at least one state template exists; `is_managed` is not the predicate.
  `advice.writes_withheld(findings, missing_templates, holds_data)` is **true
  when the target holds Workflow data and either `missing_templates` is
  non-empty or `findings` holds any `incomplete-inspection` finding other
  than the record-derived ones** (Round 12 L11-I-2; Round 14 L13-I-1: `read_repository` adds the
  fixed problem text `compatibility.NOT_MANAGED_PROBLEM`, "the repository is
  not managed (no installation record)", for **every** unmanaged target,
  `compatibility.py:396`. It describes the installation record, which is not a
  Workflow data file, so neither `data_findings` nor the predicate counts the
  finding that carries exactly that text; counting it would withhold the
  `bootstrap` of every unmanaged target and make the predicate equal to
  *holds data*. **The same reason excludes the installation-record finding**
  (Round 14 L13-I-1): `read_repository` turns a `CorruptInstallationError` or a
  `ValueError` from `Installation.read` into `facts.installation_error`
  (`compatibility.py:381-399`) and `build_findings` adds
  `Finding(WARNING, "incomplete-inspection", "the installation record could not
  be read", ...)` (`compatibility.py:1117-1119`), for every T8, T9
  (non-integer value) and T20 case even when all Workflow data is intact;
  counting it would make `writes_withheld` true for each of them, T8's
  `bootstrap` unreachable and its "While `advice.writes_withheld` is true"
  conditional never false. **One named constant, one rule:**
  `compatibility.PREDICATE_EXCLUDED = (NOT_MANAGED_PROBLEM,
  RECORD_UNREADABLE_TITLE)`, defined next to `NOT_MANAGED_PROBLEM`, where
  `RECORD_UNREADABLE_TITLE` is the fixed title "the installation record could
  not be read". The predicate drops a finding whose title is
  `RECORD_UNREADABLE_TITLE`, and drops the `facts.problems` lines equal to
  `NOT_MANAGED_PROBLEM` from the aggregate "the inspection could not be
  completed" finding, which then counts only if another line remains. A test
  asserts the constant's contents by value, so a later `incomplete-inspection`
  producer added to `build_findings` widens the predicate (it counts by default)
  and a new exclusion is a deliberate edit of that constant and its test.)
  **The one stated outcome for an unmanaged target that holds
  Workflow data with nothing missing and nothing malformed** (after
  `uninstall`, after T8's deletion once the data is intact): the predicate is
  false, so T1, T2, T4, T5, T7 and T12 to T19 print `bootstrap X`, and
  `install.bootstrap` keeps every state template that exists
  (`install.py:371`, "never clobbered"), so running it leaves every data byte
  intact (test (j)). The same holds for a **managed** target with a damaged
  record (T8, T9, T20) and every template intact: the predicate is false, so
  T8's `bootstrap --release-version V` is printed after the deletion step. Because it holds data written by an earlier install, the
  line carries T8's caveat: ``a bootstrap with no --release-version installs
  the newest release over state an older release wrote: to stay on the release
  the repository was on, run `workflow-manager --release-version V bootstrap
  X` with V that release (`env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks --no-pager log
  --oneline --no-show-signature -- docs/ai-workflow/WORKFLOW_STATE.json`
  lists the history)``. Nothing else about the outcome varies: 3.2, T15, D-12
  and the tests all use it. The predicate is also **the only place a row's
  text can learn that a write is withheld**: `advice.writes_withheld` and
  `NOT_MANAGED_PROBLEM` live in `compatibility` (re-exported by `advice`), so
  `recovery_steps` (which `advice` does not import and which already lives in
  `compatibility`) and `advice` call the same function with no import cycle
  (Round 12 L11-O-2). It is
  computed from the **findings list itself**, never from a subset of its
  sources (`facts.problems` alone missed the declaration failures that
  `compatibility.py` adds directly to `findings`, R3-I-2). The findings
  list covers every Workflow-data reason: state, config or
  `ACTIVE_MILESTONE.md` missing, unreadable or malformed, an unknown or newer
  `schema_version`, a work item's declarations missing, unreadable or
  malformed, and any other incomplete inspection (Git could not be run, a
  partial clone, an unknown phase: stricter than the data files strictly need,
  and deliberate). The same function serves the three consumers, so they
  cannot disagree: (1) **exception advice** (`advice.manager_command`, which
  refuses to render an `update` or `bootstrap` while it is true and returns the
  workflow-data step instead), (2) **finding details** (F-b's `--force`
  command, F-c, T15) and (3) **the Recovery section**, which withholds **every
  command that writes Workflow data or the tree** under it: the `update` step,
  the `update --force` step, any `bootstrap`, and the whole-tree undo
  (`git restore --source=HEAD --staged --worktree -- .`, with its `clean -n`),
  and, while it is true, it prints no `git status` either (the rule is stated
  in 3.4, Round 13 R4-I-2; Round 14 L13-O-2).
  **One input for all three** (Round 13 R4-O-1): the predicate receives the
  **same findings list** from every consumer, the full list `build_findings`
  returns, Git-derived `incomplete-inspection` findings (a partial clone, Git
  that cannot run) included. For (1) `cli` therefore passes that list (through
  `compatibility.data_findings(target)`, which returns it whole and still
  never raises: a failure to compute it counts as an `incomplete-inspection`
  finding, so the predicate fails closed), and finding details and Recovery
  pass the very list they render from. Exception advice no longer receives a
  file-only subset, so with intact templates and a promisor configuration the
  predicate is true for all three consumers or false for all three. Test (j)
  renders exception advice, finding details and Recovery for that fixture and
  asserts they agree.
  **Evaluation order** (Round 14 L13-I-2). `read_repository` always runs the
  hermetic internal Git reader (`_read_git`: `rev-parse`, `worktree list`, the
  partial-clone `config` probes, `status --porcelain`), so the full list costs
  Git. `holds_data` is therefore computed **first**, by the `lexists()` checks
  alone; the full list, and its Git, is computed **only when `holds_data` is
  true** (lazily, in `cli` and in each report path). A target that holds no
  Workflow data gets `data_findings=()`, a false predicate and no Git at all.
  When Git cannot run, `_read_git` adds an `incomplete-inspection` finding, so
  for a target that holds data the predicate fails closed (`bootstrap` is
  withheld): stricter than the data files strictly need, and deliberate (above).
  Every "no Git" statement of this plan is therefore narrowed to "no Git when
  the target holds no Workflow data" (3.5, 3.5a, section 4, CP2). `missing_templates` is computed for **every** target,
  managed or not and whether or not a record is readable (an `exists()` check
  needs no record), and `bootstrap` is covered as well as `update`. A row
  therefore cannot print such a command by omission. A fresh repository (no
  record, no template) holds no Workflow data, so the predicate is false and it
  keeps its `bootstrap` (T1, T2, T4, T5, T7, a first install). **Accepted
  residual:** a repository with no record and *every* state template missing is
  indistinguishable from a fresh one without Git and keeps its `bootstrap`;
  T8's text already tells the operator to bring the Workflow data back before
  any bootstrap.
  There is **no Git probe** anywhere in the advice (Round 7 P1, D-12): the
  table never classifies a path by what Git holds and never reads the
  filesystem itself; `cli` and `compatibility.read_repository` compute
  `missing_templates` and `data_findings` and pass them in. The helpers `advice` calls
  (`manager_command`, `render_command`, `git_command`) live in
  `compatibility`, which `install.py`, `installation.py`, `source.py` and
  `release.py` do **not** import, so no import cycle appears; `writes_withheld`
  and `NOT_MANAGED_PROBLEM` live there too, `advice` re-exports them, and
  `recovery_steps` calls `compatibility.writes_withheld` directly (Round 12
  L11-O-2: `advice` imports `compatibility`, never the reverse).
  **Every way a `next:` or Recovery text tells the operator to run or re-run a
  write goes through the predicate** (Round 12 L11-I-3, the principle applied
  to prose, not only to rendered commands). Two renderers carry it:
  `compatibility.manager_command` for an `update` or `bootstrap` (without
  `--dry-run`) takes a required keyword `withheld` and returns `None` when it
  is true, which the caller renders as the workflow-data step; and
  `compatibility.rerun_phrase(withheld, command_is_write)` renders every
  "run the same command again" / "run the command again" / "then run ... again"
  phrase of the tables below (T1, T2, T12, T13, T14, T18, T19, R3, R8, R9, R12,
  C3 and Recovery's "re-run with the same command"). For a read-only command,
  `uninstall` or a false predicate it returns the phrase unchanged; for
  `bootstrap` or `update` (not `--dry-run`) while the predicate is true it
  returns ``do not run it again until the Workflow data named above is back in
  place (PAGE)`` and the row's own `--force` and "move your files away" tails are
  dropped with it. A row cannot keep a re-run instruction by phrasing it as
  prose: a test (j) renders every row under a predicate-true context and fails
  on any `update` or `bootstrap` command, on "again" next to a write command,
  and on `--force`. `cli.main`
  prints `error: ...` then `next: ...` for the errors it already catches.
- The raise sites keep the cause. Four small, mechanical additions give the
  table what it needs: `install.TargetNotFoundError` and
  `install.NotAGitRepositoryError` (subclasses of `InstallError`, so every
  existing `except` still catches them); `installation.UnsupportedInstallationSchemaError`
  (a `ValueError` subclass, so `main` and `read_repository` still catch it);
  and a `kind` keyword on `ReleaseIntegrityError`, `ReleaseUnavailableError`
  and `ContainmentError`, defaulted so every untouched raise site compiles.
- Wrong words are fixed in place (T3, T4: `update()` and `bootstrap()` become
  the cause "is already managed (workflow V is installed)" and "is not a
  managed repository (no .workflow-manager/installation.json)"); the advice
  that was embedded in a cause (T8, R2, R12) moves to `next:`.

### 3.3 The fixes, row by row

Final text, as the tests assert it. `X` is the target as typed; `V` is the
`--release-version` the operator gave, kept in every printed command that
needs it. A command written without `V` is for a case where the option is
not set. **Global options are carried by a command-specific rule** (Round 5 I-4),
not blindly. `--release-source` and `--release-cache` are always carried
(they say where releases come from, not which one). `--release-version` is
what the row says: the row's own `V` for a repair, the operator's value
elsewhere. `--release-dir D` is carried **only when `context.release_dir_version`
equals the version the printed command uses**: otherwise `update` would fail
with `D holds release A, not the requested B`. When it is dropped, the
`next:` line says so (`--release-dir D holds A, so it is left out; the
installed release V comes from the cache or --release-source`), **except when
the installation record's source is `local`** (an unpublished release
installed from a directory, so V is in neither the cache nor a source): no
command is printed then, and the line says that a release directory holding V
is needed (`a release directory holding V is needed: run the command again
with --release-dir DIR`), because the printed `update` would fail with R2
(Round 6 O-4). A1 (a
misplaced option) prints **no command at all** (Round 11 R3-I-1): the parser
error handler runs before any context exists, so a corrected argv rendered
there would bypass the withholding predicate (3.2) and could recreate a
missing template. It prints a usage **pattern** with placeholders, which is not
runnable, so the predicate has nothing to guard there. The rows below show `--release-version V` only where it is the point of the row;
the others are written with `...` for the carried options.

| Row | Cause (stderr `error:` line) | `next:` line |
|---|---|---|
| A1 | `argparse` usage with `prog="workflow-manager"` | When an unrecognised argument is one of the four global options: ``next: global options go before the command, as in the pattern `workflow-manager [--release-version VERSION] update TARGET`; see PAGE#global-options`` where the pattern names the option(s) the operator misplaced (in their argparse order), the operator's own command word, and upper-case placeholders for the rest. It echoes **no value the operator typed** other than the option names and the command word, so it is not an executable command (a placeholder is not a version or a path) and carries no `update` or `bootstrap` that could be pasted. It is printed after the argparse error; exit 2. PAGE is `exit-codes.md` (its global-options sentence; CP1 gives the sentence its own anchor) |
| A4 | n/a | `doctor --help`: "Exit 0: no blocked or warning finding (notes alone still exit 0); 1: a blocked or warning finding, an incomplete inspection included; 2: could not check." |
| A5 | n/a | Each subcommand gets a `help=` line and a `description` that names what it reads and writes and its exit codes; `--release-version` help: "the Workflow release to use; goes before the command"; the program epilog points to the exit-codes page |
| T1 | `no directory at X` | ``create the repository first with `git init X`, then run `workflow-manager bootstrap X` again `` (`git init -- X` when X starts with `-`, 3.1) |
| T2 | `X is not a Git repository` | ``run `git init X` (or give the repository's top directory, the one holding .git), then run `workflow-manager bootstrap X` again `` (`git init -- X` when X starts with `-`, 3.1) |
| T3 | `X is already managed (workflow V is installed)` | ``to move it to another release run `workflow-manager update X`; `workflow-manager doctor X` shows what that would do first ``. **While `advice.writes_withheld` is true (3.2; Round 8 L8-I-1, Round 11 R3-I-2) the `update` command is withheld** (the command renderer's rule, 3.2): the `next:` line is the workflow-data step, then ``workflow-manager doctor X shows what an update would do`` |
| T4, T5 | `X is not a managed repository (no .workflow-manager/installation.json)` | ``to install the Workflow there run `workflow-manager bootstrap X` `` |
| T6 | same cause (`uninstall`) | ``there is nothing to uninstall; check the path, or run `workflow-manager status X` to see whether the Manager manages it `` |
| T7 | stdout: `not a managed repository (no .workflow-manager/installation.json)` | stdout: ``next: run `workflow-manager bootstrap X` to install the Workflow``; exit 0 |
| T8, T20 | `the installation record at P is unreadable (E)`; `Installation.read` also wraps two causes of a damaged record it does not catch today: `IsADirectoryError` (T20, E `P is a directory`) and `UnicodeDecodeError` (a record that is not UTF-8, E its own text, which names the path now that the T8 wording does). Both are raised as `CorruptInstallationError` and take T8's step. **No other `OSError` from `read_text` is wrapped** (a `PermissionError` on an intact record is T14: exit 1, the read-only or write text of the command, and no step that deletes the record) | ``delete X/.workflow-manager, then run `workflow-manager --release-version V bootstrap X`, with V the release the repository was on (the two vetted history readers of 3.4 P1, Round 12 L11-I-1: `env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks --no-pager log --oneline --no-show-signature -- .workflow-manager/installation.json` lists the revisions and `env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks --no-pager show --no-textconv REV:.workflow-manager/installation.json` shows its `workflow_version`; never `log -p`, which runs a configured textconv driver); a bootstrap with no version installs the newest release. Repository-local state is not stored there and is not affected. If bootstrap lists files in the way, they are files you edited or files of a different release than V; keep a copy of any edit, then add --force ``. **While `advice.writes_withheld` is true (3.2; Round 8 L8-I-1, Round 11 R3-I-2) the `bootstrap` command is withheld** (`install.bootstrap` writes every state template that does not exist, `install.py:368`): the step is only ``delete X/.workflow-manager``, followed by the workflow-data step, and the line ``No bootstrap command is offered until the Workflow data named above is back in place (PAGE)``. `missing_templates` is a plain `exists()` check, so it is computed for T8, T9 and T20 even though the record is unreadable. **The unreadable-record finding itself does not count toward the predicate** (Round 14 L13-I-1, `compatibility.PREDICATE_EXCLUDED`, 3.2): a damaged record with every template intact and no other incomplete inspection leaves the predicate **false**, and the `bootstrap --release-version V` step above is printed; the deletion step leaves every data byte intact. The withheld branch applies only when a template is missing or another `incomplete-inspection` finding is present, and then the line names the Workflow data (the missing template or the other finding), never nothing |
| T9 (an integer above 1) | `the installation record at P was written by a newer Manager (schema_version N; this one understands 1)` | ``upgrade the Manager: PAGE#update-the-manager `` |
| T9 (any other value) | the T8 cause: `the installation record at P is unreadable (unsupported schema_version N)` (raised as `CorruptInstallationError`) | as T8 |
| T10 (`update`, `update --dry-run`) | `unknown install profile 'x'` (raised as the new `UnknownProfileError(InstallError)`, exit 2 unchanged; `plan_update` raises it when the profile came from the record, i.e. `args.profile` is `None`) | ``the installation record names a profile this Manager does not know: if a newer Manager wrote it, upgrade the Manager (PAGE#update-the-manager); otherwise the record is damaged, so take T8's step: the text of the T8 `next:` line, verbatim (it names the release the repository was on, and it withholds `bootstrap` while a state template is missing) `` |
| T11 | the existing `refusing to update: ...` list | ``keep a copy of any file a `modified:` line above names, then run `workflow-manager update X --force` to replace those files with the release's; `workflow-manager update X --dry-run` previews it first `` (no `git diff` is printed: plain `git diff` runs the clean filter of a selected tracked path, Round 12 L11-I-1, and no flag disables it; the `modified:` lines already name the files). While `advice.writes_withheld` is true the `--force` command is withheld, as for every `update` |
| T12 (files) | the existing `refusing to ...` list (all lines `the repository has its own file here`) | ``move your own files away and run the same command again, or add --force to replace them with the release's: `workflow-manager bootstrap X --force` `` (`update` for an update). **While `advice.writes_withheld` is true** (Round 12 L11-I-3) both the prose re-run and the `--force` command are withheld, whichever the command: the line is the workflow-data step and ``do not run it again until the Workflow data named above is back in place (PAGE)`` (`rerun_phrase`, 3.2) |
| T12 (directory), T18, T19 | the list, with `occupied: a directory is in the way` (T18, T19: `occupied: P is a file, not a directory` for the ancestor; T19's P is `.workflow-manager`). **A mixed list** (file collisions together with any directory line, or any ancestor-file line) takes this directory text, because `--force` cannot clear the directory line and a printed `--force` would fail again | ``move or remove that directory, or that file where a directory goes (--force cannot replace either), then run `workflow-manager bootstrap X` again `` (`update` for an update) |
| T13, T18, T19 | as T12 (directory), now raised with `--force` too and for any ancestor of a written path below the target that exists and is not a directory (D-5). The scanned paths include the installation record, `.workflow-manager/installation.json`, and its `.tmp` sibling (`installation.write` writes the record through a temporary file), each through its ancestors, and the record itself also as a leaf, in `bootstrap` and `update`, with or without `--force`. At the two record paths only a **directory**, or a non-directory ancestor, is refused: a regular file at `installation.json.tmp` is the harmless leftover of an interrupted write (`installation.write` overwrites it), so it is not a collision and blocks nothing | as T12 (directory); exit 2 |
| T14 | `error: REASON` (the `OSError`'s own text); the `next:` line is chosen by `advice.writes_repository(args)`, true only for `bootstrap` and for `update` without `--dry-run` (a read-only flag added to a write command later joins the read-only text by changing that one helper) | **`bootstrap`, `update` (not `--dry-run`), while `advice.writes_withheld` is false:** ``fix the cause named above, then run the same command again; if it then lists a file as modified or in the way that you did not edit, it is a partial write from this run, and adding --force replaces it (PAGE#an-install-stopped-part-way)``. **The same commands while it is true** (Round 12 L11-I-3: a re-run recreates every missing state template from a blank one, so a customised template deleted from the worktree is blanked): ``fix the cause named above``, then the workflow-data step, then ``do not run it again until the Workflow data named above is back in place (PAGE)``; no "again" and no `--force`. **`uninstall`:** ``fix the cause named above, then run the same command again (it removes only what is left)``. **Every read-only command (`verify`, `status`, `doctor`, `releases`, `package`, and `update --dry-run`, which writes nothing):** ``fix the cause named above (often a permission), then run the same command again; this command writes nothing in the repository``. None of the last two mentions `--force` or a partial write. PAGE is `common-problems.md` (a user page); exit 1 (D-6) |
| T15 | the existing problem lines | By the first of these rules, `V` being the installed version from `context.installed_version` (or the operator's own `--release-version` when it equals it). **A `missing:` line for a Workflow data file** (a state template of `release.STATE_TEMPLATES`: `WORKFLOW_STATE.json`, `WORKFLOW_CONFIG.json`, `ACTIVE_MILESTONE.md`; Round 7 P1) takes the **workflow-data step** of 3.4 and no other text: history readers that show where a good copy is (the two of 3.4 P1: `env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks log ... -- PATH` and `env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks show ... REV:PATH`; no `git status`), the page that explains the manual repair, and the sentence that this Manager prints no command that writes the file and that `update` is not a repair for it. The Manager does not ask Git whether a copy exists and prints no `restore`, no `checkout` and no `update` for it (an index entry, a staged deletion, an unborn `HEAD` and a broken ref all get the same text; the operator reads the inspection output and decides). **An `update` or `bootstrap` command is never printed while `advice.writes_withheld` is true** (3.2: the target holds Workflow data, "a path at `.workflow-manager` or at least one state template present", and a state template is missing **or** the findings list holds any `incomplete-inspection` finding, declaration failures included): one `update` or `bootstrap` recreates every missing state template from a blank one (`install.bootstrap` does so whether or not the target was managed before, and `uninstall` and T8's own `delete X/.workflow-manager` both leave a target with data and no record). The rule is **structural** (Round 8 L8-I-1): it lives in the one renderer that turns a Manager command into text (`advice.manager_command`, 3.2), not in row text, so a row cannot opt out. It covers every `update` command of this row (the `version:` and general branches included), T3, T8, T9, T10, T11, T12 (`update`), F-b and any later row, and each prints the workflow-data step instead of its command. T1, T2, T4, T5 and T7 keep their `bootstrap` command **whenever the predicate is false**, by 3.2's single definition (Round 12 L11-I-2): a fresh repository (no path at `.workflow-manager`, no state template: a first install), **and** an unmanaged target that holds data with nothing missing and nothing malformed (after `uninstall`, or after T8's deletion once the data is intact), where the line carries the release-version caveat of 3.2 and running it leaves every data byte intact. An unmanaged target for which the predicate is **true** (it holds data and a state template is missing or a data finding is incomplete) gets the workflow-data step for the problem named, and no `bootstrap`; so do T12 (bootstrap, files: `bootstrap X --force`), T12-directory, T13, T18 and T19 (`bootstrap X again`) under the same condition. The not-managed finding and the installation-record finding (T8, T9, T20) do not count toward the predicate (3.2, `PREDICATE_EXCLUDED`). An `unexpected:` line, ``move PATH away or delete it if it is not yours; `update` refuses to run over it unless it already holds the release's bytes, or you add --force (--force cannot replace a directory)``; a `release:` line, ``the release package failed its own check, so the comparison is unreliable: run the command again (a cache entry that fails its pin is discarded and downloaded afresh)``; a `version:` line, ``you compared with a release other than the installed one: leave out --release-version and --release-dir to compare with workflow V, or run `workflow-manager --release-version R update X` to move the repository``; otherwise, ``to put the release's files back run `workflow-manager --release-version V update X` (add --force if a line says "modified: PATH" for a release file: that replaces your edit, so keep a copy first; no `git diff` is printed, L11-I-1); `workflow-manager --release-version V update X --dry-run` previews it``. A command never omits `--release-version V`: without it `update` resolves the newest pin and moves the repository, which is not a repair. |
| T16 | `status` prints a work-in-flight block (3.4) | stdout: ``next: `workflow-manager doctor X` reports what an update would meet`` (printed whenever `status` prints the block, which is every managed repository, including `work in flight: none` and `could not be read`; on a release error `cmd_status` re-raises after `_print_record`, and the block is printed before it, so the operator still sees it) |
| T17 | n/a | stdout, after a successful `bootstrap` or `update`: ``next: run `workflow-manager verify X`, then review and commit what changed (`git -C X status`)`` |
| R1 | `no Workflow release is published: this Manager pins none` | ``upgrade the Manager (PAGE#update-the-manager), or install an unpackaged release directory: `workflow-manager --release-dir DIR bootstrap X` `` |
| R2 | `release V is not published: this Manager has no pin for it (pinned: ...)` | ``a published release needs a newer Manager that pins it: upgrade the Manager (PAGE#update-the-manager), then run the command again. An unpublished release directory installs with `workflow-manager --release-dir DIR bootstrap X` `` (the command is the one the operator ran, with `--release-dir DIR` added) |
| R3 (URL source) | the existing `cannot fetch URL: REASON` | ``connect to the network and run the same command again, or point the Manager at a mirror that holds V/ (a directory, or a URL with {version}): `workflow-manager --release-source MIRROR ...` `` |
| R3 (directory source) | same | ``the source directory D has no V/ with SHA256SUMS, the archive and the manifest asset: fix --release-source (or $WORKFLOW_MANAGER_RELEASE_SOURCE), or leave it unset to download `` |
| R4 | `release source 'S' has no {version} field` | ``write the source as a directory, or as a URL with {version} in it, for example https://host/releases/v{version}/ `` |
| R5 | the existing redirect and size messages | ``the source answered with something that is not a Workflow package or a safe redirect; check --release-source, or leave it unset to use the published releases `` |
| R7 | `cannot store release V in the cache C: REASON` | ``free space or fix permissions on C, or choose another cache: `workflow-manager --release-cache DIR ...` `` |
| R8 | the existing digest-mismatch cause | ``run the same command again (it downloads afresh). If the digests differ again, install nothing from this download and report it to the Manager's maintainer with this message `` (D-9) |
| R9 | the existing cause | ``another process is writing the release cache C; wait for it to finish and run the command again `` |
| R10 | the existing cause | ``the Manager's own pin file is damaged; reinstall the Manager: PAGE#update-the-manager `` |
| R11 | the existing causes | ``use an unmodified copy of the release directory, or leave --release-dir out so the Manager uses the published, checksummed package `` |
| R12 | `release V is damaged: L has digest A, its manifest records B` | with a release directory: as R11; from the cache: ``run the command again; this row is defensive (a cache entry that fails its pin is discarded and fetched again automatically), so if it persists, report it as R8 does`` |
| R13 | the existing causes | ``download the archive again and compare it with SHA256SUMS: `sha256sum -c SHA256SUMS` `` |
| R14 | the existing causes | ``give a Workflow release directory, the one holding manifest.json: `workflow-manager package build DIR --out OUT` `` |
| R17 | `manifest.json at D is malformed: REASON` (the shape problem, e.g. `workflow_version is a list, not text`, `a location that is not text`, `the manifest is null`), raised as `ReleaseIntegrityError(kind="manifest-shape")` at the sites of 3.3a, **only where the command crashes today**; exit **1** for every command, the traceback's own exit, except `doctor`, which exits **2** like every other unusable release it meets (D-15). A scalar `workflow_version` that succeeds today is not rejected (D-16) | as R11 for `--release-dir`; as R14 for `package build` |
| C1 | `could not resolve the target release: CAUSE` | the `next:` of CAUSE, then (exit 2 unchanged) |
| C2 (resolves inside) | the existing cause | ``choose another cache: `workflow-manager --release-cache DIR doctor X` `` |
| C5 | `status` of a **managed** repository is contained like `doctor` (3.5a); an unmanaged target is not (T7 and exit 0 unchanged). A `ContainmentError` from it prints the C2/C3 cause after the record and block and ends **exit 1** (the contract row `status` already has for "no usable release"), never 0. This is an **argued move** of `status`'s exit code (section 1 item 5 (c), D-14): a clean repository whose destinations cannot be proven outside the target, Git unavailable included, exits 0 at the base and 1 after | as C2/C3: choose another cache or temporary directory outside the repository (`workflow-manager --release-cache DIR status X`) |
| C3 | the existing causes | Git: ``make sure Git runs here (`env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks rev-parse --git-dir`), then run the command again``; no temporary directory: ``set TMPDIR to a writable directory outside the repository and run the command again `` |

### 3.4 Report findings (`compatibility.py`)

All keep their ids and severities; none adds a refusal; `doctor`'s exit code
rule is untouched.

- **F-b** appends to the detail the T12 step, and carries the
  ``workflow-manager update X --force`` command (not when any line is a
  directory or an ancestor file: the directory text wins, as in T12).
- **F-c** appends a per-reason step to each `facts.problems` line, by the
  first matching rule. **One principle, one policy** (Round 7, P1;
  `advice.workflow_data_step`) serves T15, F-c and the Recovery section, so
  the three never disagree.
  **P1: the Manager never prints a command that overwrites, restores over or
  recreates Workflow data.** For a state file, a config file,
  `ACTIVE_MILESTONE.md` or a work item's declarations file (artifacts,
  registry, mapping) that is **missing, unreadable or malformed**, the step is
  exactly three things, and the operator decides:
  1. *Copy it aside*, when the file exists: ``save a copy first: `cp -p -- 'X/PATH' 'X/PATH.bak'` ``
     (the path quoted exactly as `shlex` renders it; the destination is the first of
     `PATH.bak`, `PATH.bak.1`, `PATH.bak.2`, ... that does not exist when the
     line is printed, so an earlier copy is never overwritten, chosen by the
     caller and passed to `advice`). Printed for a file that exists and is
     malformed, not JSON, not a JSON object or has no readable schema; for one
     that exists but cannot be read by permission the copy cannot be made, so the
     step says to check its permissions and owner (`ls -ld -- 'X/PATH'`) instead and prints no `chmod`;
     for a missing file there is nothing to copy and the step is omitted.
  2. *History readers that show where a good copy is* (Round 11 R3-I-3).
     Exactly two forms, each built by `compatibility.git_command` with the
     global option first: ``env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks --no-pager log
     --oneline --no-show-signature -- PATH`` and ``env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks
     --no-pager show --no-textconv HEAD:PATH`` (`REV:PATH` for any other
     revision `log` lists). **`git status` is not printed** in any Workflow-data
     step: it refreshes the index (a write under `.git`) and runs the clean
     filters of any selected path, so it is neither read-only nor free of
     configured executables (reproduced by the reviewer: `.git/index` rewritten
     after a timestamp change, and a clean filter run that wrote a marker inside
     `.git`). The two forms read history only: `log` over a path reads commits
     and never the index or a filter; `show` of a blob prints stored bytes
     (no smudge or clean filter; `--no-textconv` keeps a configured textconv
     helper out); `--no-optional-locks` forbids the optional index refresh and
     `--no-pager`/`--no-show-signature` keep a configured pager and signature
     program out. **The `GIT_NO_LAZY_FETCH=1` prefix** (Round 13 R4-I-1) is the
     same protection the Manager's own reader sets
     (`compatibility.py:161`): in a partial clone a `show` of an absent
     promised object otherwise fetches it and writes pack files under
     `.git/objects/pack` (reproduced by the reviewer); with the prefix the
     read fails (exit 128) and changes nothing. Every printed inspection
     command carries it together with `--no-optional-locks`. The **executed test is the arbiter**, not the flag list
     (section 4, (g)): if a case in it leaves a byte under `.git` changed or
     runs a marker helper, the printed form is extended until it does not, and
     the extension is recorded here.
  3. *The page that explains the manual repair*:
     ``PAGE#repair-workflow-data-by-hand`` (`common-problems.md`), which says in
     prose what restoring a file from Git, or copying a template out of the
     release package, involves, that `update` recreates **every** missing
     state template from a blank one in one run, and that the operator, not
     the Manager, decides which copy is the good one.
  The step also states, as a sentence and not as a command, that this
  Manager prints no command that writes the file and that `update` is not
  a repair for it. It **never** prints `git restore`, `git checkout --`,
  `git stash`, `update` or `bootstrap` for these files, whatever Git holds
  (an index entry, a staged deletion, an unborn `HEAD` and a broken ref all get
  the same text), so there is no per-path classification, no Git probe and no
  unreadable-declaration branch (Round 7 R2-I-1 to R2-I-3 end here).
  Other reasons, by the first matching rule:
  - a `schema_version` the report does not understand: upgrade the Manager;
  - declarations missing, unreadable or malformed: the P1 step above for
    that declarations path; a legacy item has none, so finish or retire it
    (`/retire-legacy-work-item ID`) before the update;
  - Git could not be run, a partial clone, a clean/process filter, or
    a Git read failed: ``make sure `env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks rev-parse
    --git-dir` works here, or review the named parts by hand``; anything else: ``fix what is named and run
    `workflow-manager doctor X` again``.
  - **The Recovery section** (`compatibility.py:recovery_steps`) obeys the same
    principle through the same predicate (Round 11 R3-I-2): when
    `advice.writes_withheld(findings, missing_templates, holds_data)` is true
    (3.2: any `incomplete-inspection` finding, whatever feeds it, or a missing
    template), **every command that writes Workflow data or the tree is
    withheld**, not only `update`: the "An update that stopped half way is
    re-run with the same command" step and its `update` command, the
    `update --force` step for a refused drift, any `bootstrap`, and the
    whole-tree undo `git restore --source=HEAD --staged --worktree -- .` with
    its `git clean -n`. The reason: a clean-looking tree can hide Workflow-data
    edits (an assume-unchanged state file reports `dirty=False` while holding
    uncommitted edits, and a clean repository can hold committed malformed
    state), and the restore would discard or overwrite them. In their place the
    section prints the line ``No command that writes the repository is
    offered: the Workflow data problem named above needs your decision first
    (PAGE)``. **Slash commands** (Round 12 L11-O-1): `recovery_steps` appends
    every `FAMILY_SLASH` command of a finding (F-c's and F-g's
    `/retire-legacy-work-item ID`). These are **not withheld** under the
    predicate, and the exemption is stated, not implied: a slash command runs
    the installed Workflow's own validated writer in an agent session, which
    recreates no blank template and replaces no file with the release's, so it
    is not the write the predicate guards. Their wording must not presuppose an
    update (F-c: "before the update"; F-g's detail says "before any update",
    since the predicate-true Recovery section has none). The forbidden list of
    test (i) stays `update`, `update --force`, `bootstrap`, `git restore`,
    `git clean`; test (j) asserts the slash command is **present** for a
    `LEGACY_READY` item together with a predicate-true problem. **While the predicate is true the section prints no `git status`**
    (Round 13 R4-I-2), and no other command outside the two vetted history
    readers of P1: the baseline "Before the update" `git status --short` line
    is replaced by the sentence ``review the working tree by hand: this
    Manager offers no command for it while the Workflow data named above is
    incomplete``. `git status` refreshes the index and runs a selected clean
    filter (the reviewer wrote a marker inside `.git` this way while the
    Manager had skipped its own status call, `compatibility.py:570`). When the
    predicate is false the section is the baseline's, `git status --short`
    included (a review line the operator runs knowingly, not claimed
    read-only). There is no exception while the predicate is true.
- **F-d** replaces "park" by what it means and points to the page: ``finish
  the item (it reaches its final phase), or run the update before the item
  starts implementing; PAGE#check-before-you-update``.
- **F-e** points to the installed `docs/ai-workflow/REVIEW_PROTOCOL.md`,
  "Repairing an artifact declaration after an approval".
- **F-f** ends: ``check a target of 2.6.0 or later: `workflow-manager
  --release-version 2.6.0 doctor X` ``.
- **F-i** ends: ``to check the update to the newest release instead, leave
  --release-version out: `workflow-manager doctor X` ``.
- **F-n** becomes: "...cannot compare the installation with the installed
  release's published package (offline, the release is not pinned, or its
  package failed verification), the comparison `workflow-manager verify`
  makes. `workflow-manager verify X` prints the actual cause." (This also
  closes the parked follow-up.)

### 3.5 The state-JSON question (D-3)

`status X` of a managed repository gains one block, read from the same
entry validation `doctor` uses for its Work items table. A new
`compatibility.read_work_items(target)` returns `WorkInFlight(state_read,
items, problems)`; it reads the state through `_read_state`'s checks and a
refactored `_item_core(wid, entry, problems)` that `_read_items` also calls
(the shared per-entry validation, **without** loading declarations or
registries, which `status` does not need), so the **reader** runs no Git and
`status`'s block stays fast and independent of host Git config. (The command
as a whole runs Git for a **managed** target in the destination check of
3.5a, `git rev-parse --absolute-git-dir`, and, only when a `next:` line is
rendered through the predicate for a target that holds Workflow data, in the
hermetic reader of 3.2's evaluation order, Round 14 L13-I-2.):

```
workflow 2.9.1 (full profile) — clean
  source: package workflow-2.9.1.tar.gz from ... (sha256 ...)
  work in flight: 1 active work item
    workflow-manager-operator-ux  PLANNING  process  governing 2.2  (active)
  next: `workflow-manager doctor X` reports what an update would meet
```

- **Fail closed on partial inspection** (Round 5 I-3). `work in flight:
  none` is printed only when the state was read, its `schema_version` is the
  one the reader understands, `problems` is **empty**, and no entry is
  non-terminal. The reused reader skips an entry with an unknown governing
  version, no phase, or a non-object value, and keeps going; so the block
  never infers "none" from an empty item list. By case, all with `status`'s
  exit code unchanged:
  - *state file missing* (managed repository): `work in flight: unknown (WORKFLOW_STATE.json is missing; workflow-manager doctor X says what to do)`;
  - *unreadable, not JSON, not an object, or an unknown `schema_version`
    (older or newer)*: `work in flight: could not be read (workflow-manager doctor X says why)`;
  - *state read, but `problems` is not empty* (an unknown governing version
    such as `"2.3"`, a malformed entry, an unknown phase): the readable
    non-terminal items are listed, then `inspection incomplete: N problem(s)
    (FIRST PROBLEM); workflow-manager doctor X lists them`, N being the length
    of `problems` (Round 6 O-3: an item in an unknown *phase* was read and is
    listed, but still counts as a problem, so the line says "problem(s)", not
    "could not be read"); a repository whose only
    implementing item has governing `"2.3"` therefore prints
    `incomplete`, never `none`. An item in an unknown *phase* is listed (it
    is treated as non-terminal, as `doctor` does) with `(unknown phase)`.
  - supported governing versions are exactly `GOVERNING_VERSIONS` (`"1"`,
    `"2.1"`, `"2.2"`); anything else is the third case.
- Only non-terminal items are listed, in the table's own columns (id, phase,
  type, governing version), capped at ten with "and N more".
- It never prints a Workflow command or a "next Workflow step", never opens
  `.ai-review/`, and writes nothing. The block never changes `status`'s exit
  code, also when the read fails; the one exit-code move of `status` is the
  containment refusal of 3.5a.
- The same facts remain in `doctor`'s Work items table; nothing else is
  added there.

#### 3.5a `status` writes nothing in the target (Round 5 I-2)

The block's "no write" holds for the **whole command** of a **managed**
target, not only the reader. For a managed target `cmd_status` calls
`_readonly_destinations(args, installed)` (as `doctor` and
`update --dry-run` do) **before** any resolver call and passes the result
to `_resolve`, so `plan_destinations` validates the release cache, its lock
leaf, every `TMPDIR`-style candidate and the snapshot parent against the
target **and its `.git` directory**, following symlinks (C2). Permitted writes
are those **outside** the target: the cache entry and lock under the cache
root, the snapshot under a validated temporary directory. A destination
inside the target or its Git directory is a `ContainmentError`, which
`cmd_status` catches next to `RELEASE_ERRORS`: it prints the record and the
block (as for a release error), then the C2/C3 cause and its `next:` line,
and returns **1**, the exit `status` already has for "no usable release"
(`docs/exit-codes.md`), so `status` never exits 0 after refusing a destination.
**Containment applies only to a managed target** (Round 7 O-1). The guard is
`is_managed(args.target)`, evaluated first, as `cmd_status` evaluates it today (`_release_for_target`
checks `args.release_version` before `is_managed`, `cli.py:254-257`; this
design keeps that order for it and puts `is_managed` first only in `status`'s containment). An **unmanaged** target keeps today's path
unchanged: no destination check and, **when the target holds no Workflow
data**, no Git (a target that holds data runs the hermetic reader for T7's
predicate-gated `bootstrap` line, 3.2's evaluation order, Round 14 L13-I-2), T7's `not a managed repository`,
exit 0, whether or not release options are given. Without
`--release-version` nothing is resolved at all (`_release_for_target` returns
`None`). With an explicit `--release-version`, today's code resolves that
release through the cache before it prints T7, and that resolution keeps its
base behavior (exit 0 when it succeeds, a release error's exit 1 when it does
not). Containing that explicit-option resolution would move an exit that no
requirement asks to move (D-14), so it is listed in 3.6 as a known remaining
gap, not changed here.
**This does move an exit code for a managed target, and the plan says so**
(Round 6 I-3, option (i)): at the base, `status` of a clean managed repository exits **0** with no Git on
`PATH` (`env -i PATH=/nonexistent python3 -m workflow_manager status r`: `clean`,
exit 0; `doctor` refuses with `could not check containment`) and with
`--release-cache r/.git/mycache` (`clean`, exit 0; `doctor` exits 2). Both
become C3's/C2's cause with exit **1**. The alternative (ii), skipping the
comparison on a refusal, is not free either: `cmd_status` already returns 1
whenever `verified` is false, so it would exit 1 as well and drop the cause. The
move is argued, not hidden: `status` promises it writes nothing, and a
command that cannot prove that must not report `clean`. It is listed in
section 1 item 5 (c), REQ-5 (plan and mapping), D-14, `docs/exit-codes.md`
(section 5) and `docs/ACTIVE_MILESTONE.md`, and tested by value (section 4).
The block and the record are read-only and run first. The read-only audit (`test_read_only.py`) is extended to whole
`status` runs, including refusal paths, comparing the target **and**
`.git` byte for byte before and after.

#### 3.3a Malformed release manifests (Round 5 I-6, Round 7 R2-I-4)

R11/R14 assume a damaged release is a classified `ReleaseIntegrityError`.
Some wrong *shapes* escape as uncaught exceptions, and others are accepted
today. **The rule (P2): classify only what crashes; keep accepting what
succeeds.** A shape that succeeds today at any command is not made a
rejection by this milestone (a message milestone does not tighten what a
release may contain; D-16). Every crash becomes a `ReleaseIntegrityError(
kind="manifest-shape")` at its own site, not in the D-6 `OSError` handler.
The checks run in this order, so a shape is validated before anything
indexes with it:

1. **`source.local_release`**, after the existing requested-version comparison
   (so the `holds release ..., not the requested ...` cells below keep their
   text) and **before `pins.get(version)`**: an unhashable `workflow_version` (a
   list or an object) raises the shape error. A scalar (`null`, a number, a
   boolean, `""`) passes through exactly as today (`pins.get` answers
   `None`, the release is unpublished, and the commands behave as the table
   below records).
2. **`source._copy_snapshot`**: each `artifacts`/`templates` record is
   checked before `location.split`: a mapping whose `location` is text.
3. **`package.build_package`** catches `TypeError` and `AttributeError`
   around `Release(...)` and `release.verify()`, and checks the records that
   `_manifest_records` and `_read_checked` index (a mapping with a text
   `location`) before the first index, raising the same kind. It does **not**
   look at `workflow_version`'s type: `package build` accepts every scalar
   version today (exit 0) and keeps doing so (D-16).

**Baseline exits, recorded from the unchanged code at `218155d`** (each command
run against a fresh managed repository and a `--release-dir` copy of a real
release whose manifest was edited and whose version is unpublished, with no
`--release-version` unless a row says so; Round 8 O-1; `tb` =
the command ends in a traceback today). The table is the contract of the
sweep test, which asserts every cell **by value**. **Fixture condition**
(Round 11 R3-O-1): the sweep runs every cell against the **clean committed**
fixture of `tests/frozen_runs.py` (`build_bootstrapped_repo`: bootstrap, then
commit), not a dirty tree; a dirty tree gives `doctor` the `dirty-tree` warning and so exit 1 where
the report completes, so a dirty fixture would bake that unrelated warning into
the by-value cells. The two `doctor` cells for a `null` or `""`
`workflow_version` are 1 only because a bootstrap that is not committed leaves
the tree dirty, and reproduce as 0 on the clean committed fixture. The
sweep asserts the clean values, and asserts the dirty-tree 1 once for those
two cells so both outcomes are recorded; neither introduces a new exit:

| Manifest | `package build` | `bootstrap` | `update` | `update --dry-run` | `verify` | `status` | `doctor` |
|---|---|---|---|---|---|---|---|
| `workflow_version` a list or object | 0 | 1 tb | 1 tb | 1 tb | 1 (`holds release [], not the requested ...`) | 1 (same) | 1 tb |
| `workflow_version` `null` or `""` | 0 | 0 | 0 | 0 | 1 (`holds release`) | 1 | 1 on a dirty tree, **0 on a clean committed fixture** |
| `workflow_version` a number or boolean | 0 | 0 | 0 | 2 (`not a release version`) | 1 (`holds release`) | 1 | 2 (`not a release version`) |
| manifest `null` or a list | 1 tb | 1 | 1 | 1 | 1 | 1 | 2 |
| `artifacts` `null` or an object; a record that is not a mapping; `templates` missing | 1 tb | 1 | 1 | 1 | 1 | 1 | 2 |
| `upstream` missing | 1 | 1 | 1 | 1 | 1 | 1 | 2 |
| an artifact `location` a number or `null` | 1 tb | 1 tb | 1 tb | 1 tb | 1 | 1 | 1 tb |
| the same `location` rows, with `--release-version` equal to the manifest's own version (an unpublished one; the requested-version comparison then passes and `_copy_snapshot` runs) | n/a | 1 tb | 1 tb | 1 tb | 1 tb | 1 tb | 1 tb |

**After this milestone**, every `tb` cell has no traceback and a
non-empty `error:`/`next:` pair, and every cell keeps its value **except one
column**: `doctor` on a list/object version and on a numeric/`null` location
(the two `doctor` cells that are `1 tb` today) exits **2**, the exit `doctor`
already gives every other unusable release in the same table (D-15). Every
`0` cell stays `0` and every other cell keeps its exit. The `1 (holds
release ...)` cells of `verify`/`status` are the existing, classified
installed-record comparison and do not change; scalar versions are not
rejected anywhere they succeed. Because a scalar `workflow_version` can
install and be written into the record (`bootstrap`, `update`), the sweep
also asserts that the install it performs is the same as today (the record's
`workflow_version` equals the manifest's value) and that no step this
milestone adds reads it as text. A tightening (reject a non-text version in
`bootstrap`, `update` and `package build`, which moves `0` cells to `1`)
is a separate decision, argued and left open in D-16.

### 3.6 Rows that stay as they are

A3, A2 (apart from the program name), R4 (first form), R6, R15, R16,
F-a, F-g, F-h, F-j, F-k: already name their cause and a concrete step,
are unreachable from the CLI (T10 is not: Round 5 I-6 found its `update` path and fixed it), or report an action rather than a failure.
R12 and T15's `release:` line are close to unreachable: every release reaches
the installer as a private snapshot already checked by `_snapshot_problems`,
and `_ensure_locked` discards and refetches a cache entry that fails its pin.
They get the defensive text above, with no cache-deletion step.
`fixture.py`'s `ValueError` and `RuntimeError` messages are test-fixture
builders, not operator-facing, and are not touched.
**Known remaining gap, not changed** (Round 7 O-1): `status` of an
**unmanaged** target given an explicit `--release-version` still resolves that
release through the cache before printing T7, as at the base, and so can write
a `--release-cache` placed inside the target or `.git` (reproduced at the
base: `--release-version 2.9.1 --release-cache r/.git/c status r` exits 0 and
creates `r/.git/c`). Containing it would move a base exit 0 for no requirement
of this milestone; it is recorded for a later milestone and tested as
unchanged (section 4).

## 4. Tests

New: `tests/test_operator_ux.py`, subprocess tests through the entry point
(`python3 -m workflow_manager`, `support.cli_env()`), plus unit tests of
`advice.next_step`. Existing tests whose assertions quote a changed message
change in the same checkpoint (`test_bootstrap.py`'s corrupt-record test now
asserts the CLI output; the others keep working because every cause line
keeps its first words).

- **One assertion per changed message** (section 3.3): the cause text, the
  next step's key part (the command, flag or page), and the old exit code.
  Table-driven: each row builds its repository or release source in a
  temporary directory (`fixture.init_git_repo`, `build_bootstrapped_repo`,
  an empty or tampered `--release-source` directory, an empty `PATH` for
  "Git cannot run", no usable temporary directory for C3, below).
- **Every printed command parses.** A helper extracts each backticked
  `workflow-manager ...` command from the `next:` lines and `Recovery` of the
  cases above and parses it under `cli.build_parser()`; placeholders are
  upper-case words. A `next:` line with a `workflow_manager` (underscore)
  program name fails.
- **Pages resolve.** Each URL in a `next:` line maps to a file and anchor in
  the working tree (`tools/check_docs.py`'s slug rule), including the new
  `update.md#update-the-manager`.
- **Help text.** The program's, `doctor`'s (exit 0 covers notes; the old
  "nothing found" is gone), and every subcommand's `--help` are asserted;
  `--release-version`'s help says it goes before the command.
- **T13** is reproduced with a directory at a release path under `--force`,
  for `bootstrap` and for `update`: exit 2, a `CollisionError`, and **no file
  of the release written** (the tree is byte-identical before and after).
- **T18** is reproduced with a regular file at an ancestor of a release path
  (`.claude`, and `scripts`, which sorts after `.claude/...`), for `bootstrap`
  and `update`, with and without `--force`: exit 2, a `CollisionError`, and a
  byte-identical tree. **T19:** `.workflow-manager` as a regular file, for
  `bootstrap` only (for `update` it is T4, not managed, because `is_managed`
  needs `installation.json`), with and without `--force`: exit 2, a
  `CollisionError`, and a byte-identical tree. For `update`, a **directory**
  at `.workflow-manager/installation.json.tmp` (where `tmp.write_bytes` would
  fail after every file is written): the same refusal, byte-identical. A
  leftover **regular file** at `installation.json.tmp` blocks neither
  `bootstrap` nor `update`. **T20:** a directory at `.workflow-manager/installation.json`:
  every command prints T8's text, exit **2** (the argued move of D-5), no traceback. **Other unreadable records:** a record of the bytes `\xff\xfe` prints T8's text with exit 2 and names the path (no code moves); a record with mode 000 gives exit 1, no traceback and no "delete" or `bootstrap` in the `next:` line, for `status` (the read-only T14 text) and for `update` (the write text).
- **T14** uses a read-only parent directory: exit 1, a message instead of a
  traceback, and the same command succeeds after the permission is restored.
  A second case simulates `ENOSPC` mid-write (a patched `_write` that leaves a
  truncated release file): the message is the traceback-free one, and the
  re-run prints the modified/in-the-way list the T14 text describes (it needs
  `--force`). **A read-only command:** `verify` with an unreadable managed
  file (mode 000): exit 1, no traceback, and no `--force` and no "partial
  write" in the `next:` line; the same for `update --dry-run` with an
  unreadable managed file (`drift` raises `PermissionError` at the base), and
  for `uninstall` (its own text).
- **T12 mixed:** one refusal listing a file collision and a directory in the
  way: the directory text, with no `--force` in the `next:` line.
- **Workflow-data advice, executed** (Round 5 I-1, replaced by P1 in Round 7;
  every case runs each printed command and asserts its **effect**, and that
  every byte of repository data the case started with is still there). The
  advice has no Git probe, so there is no per-path classification to test; the
  cases cover what the operator is told, for every state and config file,
  `ACTIVE_MILESTONE.md` and declarations file, through `verify`, `status`,
  `doctor` and the Recovery section:
  (a) **missing, committed** (clean index): the output has the workflow-data
  step (the two history readers of 3.4 P1 and the page) and none of `restore`,
  `checkout`, `stash`, `status`, `update`, `bootstrap`; running each printed command
  exits 0 and changes nothing (the whole tree and `.git`, hashed before and
  after); `git show HEAD:PATH` prints the committed bytes.
  (b) **missing, staged deletion** (`git rm`), **modified-staged-then-deleted**
  (`echo staged-work > S; git add S; rm S`), **staged but never committed then
  deleted**, **unborn `HEAD`** (a bootstrapped, uncommitted repository), a
  **repository with commits whose `HEAD` and index lack the path**, a
  **broken `HEAD`** (the branch ref names a nonexistent object, with the
  recoverable state on another ref: Round 7 R2-I-3), and a **repository Git
  refuses** (a stub `run_git` returning 128, and an empty `PATH`): the text is
  the same in every one, no command in it writes, and `git log --oneline --
  PATH` / `git show OTHERREF:PATH` forms (run by the test) still reach the data the
  case kept on another ref.
  (c) **mixed missing templates** (Round 7 R2-I-1): state, config and
  `ACTIVE_MILESTONE.md` missing together in every combination of "never
  tracked", "in the index" and "only on another ref", with a payload file also
  modified: `verify` and `status` print no `update` command at all (the
  `modified:` repair line included), `update --force`'s T11/T12 text and
  F-b print the workflow-data step instead of their command, and `doctor`'s
  Recovery section withholds every writing command with the stated line; the test then runs
  `update` anyway and asserts it **would** recreate all three (the
  reproducer), to show why it is withheld. A repository with **no** template
  missing still gets the ordinary `update` command, asserted by value.
  (d) **existing malformed or non-JSON** state, config and declarations files
  (R2-I-2), each with **uncommitted** contents, with committed contents
  edited, and with a **staged** edit: the step prints the `cp -p -- 'X/PATH'
  'X/PATH.bak'` command; the test runs it and asserts the copy's bytes and
  mode equal the original's; no output contains `restore`, `checkout`,
  `update` or `bootstrap`; running `update` afterwards (the test's own call,
  to prove the claim) leaves the file's bytes unchanged. When `PATH.bak`
  already exists with other bytes, the printed destination is
  `PATH.bak.1`, and the earlier copy's bytes survive running the command.
  (e) **unreadable** (mode 000) state and declarations files: the step says
  to check permissions and prints `ls -ld`, no `chmod`, no `cp`, and no
  `restore`; a path with spaces, quotes and a leading hyphen in the target is
  printed quoted and the printed `cp`/`git` commands, run as written, have the
  stated effect.
  (f) every printed command of (a) to (e) that is a `workflow-manager`
  command parses under `build_parser()`; every `git` command **of a
  Workflow-data step** is exactly one of the two history readers of 3.4 P1
  (asserted against the two printed forms, not a list of subcommand names:
  an allow-list of names does not establish read-only behaviour, R3-I-3), with
  `cp -p`/`ls -ld` the only other commands, and a test fails if any `next:` or Recovery
  text built from these rules contains `restore`, `checkout --`, `stash`,
  `reset`, `rm` or an `update` command while a Workflow data file is missing,
  unreadable or malformed. **The check runs over every `next:` and Recovery
  text of every case in this section, not only the rows above** (Round 8
  L8-I-1): with one state template missing, no `update` or `bootstrap` command
  is printed for a managed target. The variants are T3 (a customised
  `WORKFLOW_CONFIG.json` committed, then deleted from the worktree: the
  printed text is executed as written and must not recreate it), T8, T9, T10
  and T20 (a damaged record together with a missing template), T11, T12, T15
  and F-b. T1, T2, T4, T5 and T7 are asserted, by value, to keep their
  `bootstrap` command **when no state template exists and no path exists at
  `.workflow-manager`** (a fresh repository). Two reproducers cover targets
  that hold data and have no record (Round 9 L9-I-1), each asserting that no
  `bootstrap` or `update` is printed and that running the printed text as
  written leaves the missing file absent: (1) T8's deletion: bootstrap at
  2.9.1, commit a customised `WORKFLOW_CONFIG.json`, `rm -rf
  X/.workflow-manager X/docs/ai-workflow/WORKFLOW_CONFIG.json` (state present),
  then `status`, `verify` and `update`; (2) `uninstall`, then a missing state
  template, then `status`. A third case is T19 (a regular file at
  `.workflow-manager`) with one template missing and another present: no
  `bootstrap`.
- **Round 11 cases, executed** (R3-I-1 to R3-I-3; each runs the printed text
  as written and hashes the whole tree and `.git` before and after):
  (g) **printed inspection is read-only.** A repository with **stale index
  stat data** (a tracked file's timestamp changed with `touch`, the index not
  refreshed), a **selected clean filter** (`.gitattributes` `filter=marker`
  with a `filter.marker.clean` script that writes a marker file inside
  `.git`), and marker helpers for a textconv driver, `core.pager`,
  `core.fsmonitor` and `log.showSignature` with a `gpg.program`, all set in the
  repository's own config (the hermetic environment keeps the host's out).
  The repository's config also selects a **textconv driver on `*.json`**
  (`diff.tc.textconv` with a marker helper, `*.json diff=tc`; Round 12
  L11-I-1). **Scope, stated** (Round 13 R4-O-2): (g) runs **every printed
  INSPECTION command** of the plan, each with its `GIT_NO_LAZY_FETCH=1` and
  `--no-optional-locks` prefix, and asserts `.git` byte-identical for all of
  them. Outside it, by name: the deliberate `git init` advice of T1/T2 (a
  write by design), the whole-tree undo's `git restore ...` and `git clean -n
  -d` (writes, withheld under the predicate), and the two review lines not
  claimed read-only: T17's `git -C X status` and Recovery's baseline `git
  status --short`, the latter printed **only while the predicate is false**
  (Round 13 R4-I-2: under a true predicate Recovery prints no `git status`,
  which (g) asserts with a selected clean filter and a stored-marker check,
  and (j) asserts by value). **Partial clone** (Round 13 R4-I-1): a clone
  whose origin is a local-filesystem promisor, the managed target missing
  `WORKFLOW_STATE.json` from the object store; the printed `show` of that
  absent promised object is executed: exit 128, no fetch, `.git` unchanged
  (the same command without the prefix creates pack files, shown on a copy as
  the reproducer). That includes T8's two
  version-inspection readers for `.workflow-manager/installation.json` (a
  record with `*.json diff=tc` selected). No `git diff` is printed anywhere
  (T11, T15 dropped it: no flag disables a clean filter), and a test fails if
  any `next:` or Recovery text contains `git -C X diff` or `log -p`.
  Every printed inspection command of (a) to (e) and T8, for the state, config,
  `ACTIVE_MILESTONE.md`, declarations and record files, is run: `.git` is
  **byte-identical** afterwards (including `index`), no marker exists, and
  `git log`/`show` output is the history's. The test also runs plain `git
  status` on a copy of the same repository to show the marker **would** appear
  (the reproducer, which is why `status` is not printed).
  (h) **A1 prints no executable command.** A committed, customised
  `WORKFLOW_CONFIG.json` deleted from the worktree, then `update X
  --release-version V` (and each of the four global options misplaced after
  `bootstrap`, `update`, `verify`, `status`, `doctor`): exit 2, the argparse
  error, and a `next:` line holding the pattern of A1 and **no** `update` or
  `bootstrap` command carrying the operator's target or version (the test
  extracts the backticked text, asserts it contains only placeholders, and that
  the program's `build_parser()` does not accept it as a command with a real
  target). Nothing in the tree or `.git` changes, the config stays absent, and
  the output is identical with the config present (the pattern does not depend
  on the repository).
  (i) **Recovery withholds every writing command.** Each case is run through
  `doctor` and the report's Recovery section, asserting that none of
  `update`, `update --force`, `bootstrap`, `git restore`, `git clean` appears
  and that the stated line does: (1) **malformed declarations with empty
  `facts.problems`** and no missing template (the reviewer's reproducer: only
  the finding that `compatibility.py` adds directly to `findings` carries the
  reason); (2) a **clean repository with committed malformed state**
  (`dirty` is False); (3) **committed malformed state with malformed
  uncommitted edits hidden by `git update-index --assume-unchanged`**
  (`dirty` is False; the test first runs the baseline's `git restore ... -- .`
  on a copy to show it would discard the edits, then asserts on the original
  that the printed text does not contain it and that every byte of the state
  file survives); (4) an unknown and a newer `schema_version`; (5) a missing
  `ACTIVE_MILESTONE.md` with every other file intact; (6) unreadable (mode
  000) state; (7) a refused drift together with each of (1) to (6) (the `update
  --force` step is withheld too). A repository with **no** such problem keeps
  the baseline section by value (the `update`, the undo when `dirty` is False,
  the `--force` step for a drift): the predicate is asserted both ways, and
  the exception advice, finding details and Recovery are asserted to agree on
  each case (one predicate, one answer).
  (j) **Prose re-runs, the unmanaged-with-data outcome, and slash commands**
  (Round 12 L11-I-2, L11-I-3, L11-O-1; each runs the printed text as written
  and hashes the tree and `.git`). (1) **Unmanaged with data, nothing
  missing:** `bootstrap`, `uninstall`, every template intact, then `status`,
  `verify`, `update` (T7, T4, T5): `bootstrap X` is printed with the release-
  version caveat of 3.2, and running it leaves every data byte intact. (2)
  **Unmanaged with data and a template missing:** T8's deletion with
  `WORKFLOW_CONFIG.json` removed: the workflow-data step, no `bootstrap`. (3)
  **T14:** a patched `_write` raising `OSError` for `bootstrap` and for
  `update`, one customised template missing from the worktree: neither output
  contains "run the same command again", "again" next to the command, or
  `--force`; the predicate-false twin keeps the baseline text. (4) **T12
  (files)** the same, with a file in the way and a missing template. (5)
  **Every row, rendered under a predicate-true context:** no `update` or
  `bootstrap` command, no `--force`, no "again" next to a write command (the
  rows of `uninstall` and the read-only commands are exempt and asserted
  unchanged). (6) **A `LEGACY_READY` legacy item together with a predicate-true
  problem:** Recovery withholds every writing command and keeps the
  `/retire-legacy-work-item ID` line. (7) **A damaged record with every
  template intact** (Round 14 L13-I-1): a bootstrapped repository whose
  `.workflow-manager/installation.json` is overwritten with `{bad` (T8), is
  replaced by a directory (T20) and holds a non-integer `schema_version` (T9),
  with `WORKFLOW_STATE.json`, `WORKFLOW_CONFIG.json` and `ACTIVE_MILESTONE.md`
  present: `writes_withheld` is **false**, T8's step is `delete
  X/.workflow-manager` followed by `workflow-manager --release-version V
  bootstrap X`, the line "No bootstrap command is offered ..." is absent, and
  running both printed steps leaves every data byte intact (tree hash). The
  twin with one template also missing keeps the withheld branch, and that line
  names the missing template. (8) **`PREDICATE_EXCLUDED` by value:** a test
  asserts `compatibility.PREDICATE_EXCLUDED` equals exactly `(NOT_MANAGED_PROBLEM,
  RECORD_UNREADABLE_TITLE)`, and that a synthetic `incomplete-inspection`
  finding with any other title makes the predicate true on a target that holds
  data, so a new producer widens the predicate and an exclusion is a deliberate
  edit. (9) **Evaluation order** (Round 14 L13-I-2): an unmanaged target with
  no data and a recording stub of `compatibility.run_git`: zero Git calls and
  `bootstrap` printed; an unmanaged target **with** data and an empty `PATH`:
  `bootstrap` withheld (Git cannot run, the predicate fails closed) and the
  workflow-data step printed. (10) **Printed prefixed commands:** `printed_commands`
  returns every `env GIT_NO_LAZY_FETCH=1 git ...` line as a Git-family argv, none
  is skipped, and each runs as printed (Round 14 L13-O-1).
- **A local-source installed release** (Round 6 O-4): a repository installed
  from a release directory not in the pins (`source` is `local`) with a
  modified payload file and a `--release-dir` of another version: no command is
  printed, and the line says that a release directory holding V is needed.
- **Global options, executed** (Round 5 I-4): the reproducer: a repository
  installed at 2.6.0, a modified payload file (so the ordinary repair line
  prints; the state templates all exist), and `verify --release-version 2.9.1
  --release-dir <2.9.1 tree>`: the printed repair **drops** `--release-dir`
  (its version differs), carries `--release-version 2.6.0`, parses **and
  succeeds when run**; with `--release-dir <2.6.0 tree>` the directory is
  carried and the command succeeds; `--release-source` and `--release-cache`
  are carried in both.
- **Leading-hyphen paths, executed** (Round 5 I-5): targets named `-repo`
  (bootstrap, update, verify, status, doctor): every printed command, run as
  written from the directory holding the target, **has the effect it names**
  (Round 6 O-1: not "contains `--`", which is wrong for `git -C X ...`, where
  `-C` takes the next word as its value); `workflow-manager` commands have
  their flags before the positional and `--` before it, and `git init` has `--`
  before its path. This includes `bootstrap -- -repo` for a missing `-repo`:
  the printed `git init -- -repo` runs, then the printed bootstrap succeeds.
- **Malformed manifests** (3.3a, Round 5 I-6, Round 7 R2-I-4): validation of the
  version's shape precedes the pin lookup, and the sweep runs the table of
  3.3a: every row of the baseline table, for each of `package build`,
  `bootstrap`, `update`, `update --dry-run`, `verify`, `status` and `doctor`,
  each against a **fresh** managed repository (one command mutating the
  record, as `update` with a scalar version does, would change the next
  command's baseline). **Each cell's exit is asserted by value**: the
  unchanged cells equal the base, the `tb` cells have no `Traceback`, a
  non-empty `error:`/`next:` pair and the table's exit, and the two `doctor`
  cells of D-15 are 2. The values of the base were recorded by running the
  unchanged code (3.3a) and are kept in the test as data; a cell that succeeds
  today (a scalar version) is asserted to still succeed with the same exit and
  the same record content. An installation record
  with `"profile": "bogus"` for `update` and `update --dry-run` (exit 2, the
  T10 step, no traceback). A final **no-traceback sweep** runs every
  inventory case that is reachable from the CLI and asserts `Traceback` is
  in none of the stderr outputs.
- **T8/T15 versions:** on a repository installed at an older pinned release
  the printed `update` (T15) command carries `--release-version <that
  release>`, asserted by value; T8 fires only when the record cannot be read,
  so `installed_version` is `None` and its `bootstrap` carries the placeholder
  `V` with the two vetted history readers of 3.4 P1 for the record (never `log -p`), asserted as that text; a deleted
  `WORKFLOW_STATE.json` prints the workflow-data step (inspection commands and the page; no `restore`, no `update`); a
  schema value of `None`, `"1"`, `0` prints the T8 text, `2` the newer-Manager
  text.
- **C3** has no environment variable naming a temporary directory (a *named*
  candidate inside the target is C2's fourth message, raised before the
  fallback). Its case makes every candidate unusable: the working directory is
  inside the target and the fixed candidates are redirected through a test
  seam on `compatibility._TEMP_FIXED`.
- **`status`'s block:** no state, a terminal-only state, one active item, more
  than ten, an unreadable state file, **governing `"1"`, `"2.1"` and `"2.2"`
  items, an unknown governing version (`"2.3"`) on an implementing item,
  an unknown phase, a malformed entry, and an unknown or newer
  `schema_version`**: the unknown ones print `incomplete` or `could not be
  read`, **never** `none` (Round 5 I-3); exit codes equal `status`'s old
  ones. **The state reader** (`read_work_items`) runs with a `PATH` that has
  no Git and starts no Git subprocess (asserted by a `PATH` without Git, on the
  reader alone). A complete `status` run is **not** Git-free: its destination
  check of a managed target runs `git rev-parse --absolute-git-dir`, its only
  Git call **unless a `next:` line goes through the predicate**, which for a
  target that holds Workflow data adds the hermetic reader's calls (Round 5
  O-1, Round 6 I-3, Round 7 P1, Round 14 L13-I-2). The
  `incomplete` count (`N problem(s)`, Round 6 O-3) is asserted by value, an
  unknown-phase item counting once.
- **`status`'s exit-code move, by value** (Round 6 I-3): the reproducers of
  3.5a on a **clean** bootstrapped repository. (1) `status` with an empty `PATH`
  (no Git): exit **1**, `could not check containment` and C3's `next:`, the
  block and the record printed first. (2) `status --release-cache X/.git/mycache`:
  exit **1**, C2's cause, and nothing created under `.git`. (3) The same two
  runs with `doctor`: exit 2 (unchanged). (4) `status` of the same repository
  with a usable cache and Git: exit **0** (unchanged). Each exit is asserted
  against the base's value (0) or the newly listed exception (1), and the
  exception is quoted in `docs/exit-codes.md`. **Unmanaged targets** (Round 7
  O-1; the containment guard is `is_managed`): an unmanaged repository **that holds no Workflow data**, and a
  directory that is not a repository, with (5) an empty `PATH` (no Git): T7 and
  exit **0**, as at the base; (6) `--release-version 2.9.1` and a cache outside
  the target, and (7) the same with `--release-cache` inside the target and
  inside `.git` (the base behavior, exit 0, is asserted and the known gap of
  3.6 is quoted in the test as such), and `--release-dir` alone: exit 0 in each;
  (8) `--release-version 9.9.9` (unpublished): exit 1 with R2's text, as at the
  base. No destination check and no Git run in any of them **while the target holds no
  Workflow data** (an empty `PATH` and a recording stub of `compatibility.run_git`
  both assert it). (9) **Unmanaged target that holds data** (Round 14 L13-I-2):
  with a usable `PATH` it prints T7 with `bootstrap X` and the caveat when the
  predicate is false; with an **empty `PATH`** (Git cannot run) `_read_git`'s
  incomplete-inspection finding makes the predicate true, `bootstrap` is
  withheld and the workflow-data step is printed, exit 0 as at the base. (10)
  The same unmanaged-with-data target never starts Git when `holds_data` is
  false: a recording stub of `run_git` on a target with no path at
  `.workflow-manager` and no template asserts zero calls.
- **`status` writes nothing** (Round 5 I-2): whole runs, including the refusal
  paths, with a cache, a lock path and a `TMPDIR` placed inside the target, inside
  `.git`, and behind a **symlink** into either: each is refused (exit 1, the
  C2/C3 cause and `next:`), and a hash of the target **and** `.git` is the
  same before and after; the reproducer (an empty local `--release-source`)
  leaves no `.git/status-cache`; a cache **outside** the target is still used
  and written.
- **Report findings:** the `not-verified` detail names the integrity cause
  and `workflow-manager verify X`; each F-c row's step is in the report; the
  `blocked`/`warning` severities and `doctor_exit_code` are unchanged
  (the existing report tests pass untouched).
- **Docs match output** (CP5): `tests/test_operator_ux_docs.py` takes the
  quoted message of each `common-problems.md` row that quotes a Manager
  message, checks it is a substring of the real output of the case that
  raises it, and checks the row's fix names the real `next:` command; it
  checks every message `exit-codes.md` quotes the same way.
- The frozen suites, the read-only audit (`test_read_only.py`) and the
  update-planning parity tests run unchanged and must stay green; `status`
  and the error paths write nothing, so the read-only audit is extended with
  whole `status` runs, refusal paths included (3.5a).

## 5. Documentation

- `docs/common-problems.md`: every row rewritten to the new message and its
  `next:` step; new rows for the new messages (directory in the way,
  `OSError`, newer-Manager record, `status`'s work-in-flight block); and a new
  section, `## An install stopped part way` (the anchor T14 links), which
  CP1 creates so it exists from the first checkpoint that prints a link to it;
  a second new section, `## Repair workflow data by hand` (the anchor P1's
  workflow-data step links, 3.4), which says in prose how an operator restores
  a missing Workflow data file from Git or copies a template out of the
  release package, that `update` recreates every missing state template from a
  blank one, and that the operator decides which copy is the good one (CP1
  creates it too); the
  "report it in the Manager repository" wording replaced (D-9).
- `docs/exit-codes.md`: the `doctor` row says notes alone exit 0; the bootstrap
  and update rows add the directory-in-the-way refusal; the traceback sentence
  is replaced by the exit-1 `OSError` message; a line records T20 (a directory at
  the installation record is now exit 2, T8's cause, not a traceback's 1) next to
  T13, T18 and T19 (the refusal replacing a crash after a partial install);
  `status` mentions its block, and a line records the `status` move (exit 1,
not 0, for a **managed** repository where Git cannot run or the release cache,
its lock or a temporary directory lies inside the repository or `.git`: C5,
D-14; an unmanaged target still exits 0) and the `doctor` move (exit 2, not a
traceback's 1, for a `--release-dir` manifest that crashes it today: R17, D-15)
next to T13, T18, T19 and T20.
- `docs/update.md`: step 2 becomes its own section, `## Update the Manager`,
  which messages link to (CP1 creates the heading; CP5 completes the prose); the "If it fails" list quotes the new text.
- `docs/install.md`, `docs/verify.md`, `README.md`, `docs/README.md`:
  every quoted message updated (`already managed`, the `1 problem(s)` lines
  and their next step, `status`'s block); headers move to Manager 1.8.0.
- `docs/ARCHITECTURE.md`: one short section, "Operator messages", naming
  `advice.py`, the `error:`/`next:` convention, and that exit codes are the
  contract.
- `docs/ROADMAP.md`: item 7 becomes the current Next item now, and Done at
  acceptance. `docs/ACTIVE_MILESTONE.md` describes this milestone.
- Page rules (`tools/check_docs.py`): user pages carry the header and none of
  the internal identifiers; quoted commands parse.

## 6. Checkpoints

<!-- registry:begin -->
| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | advice.py next-step machinery, the program name, help text for every command and option (doctor exit wording included), the global-option hint for argument errors, and the three page anchors every later `next:` links (`update.md#update-the-manager`, `common-problems.md#an-install-stopped-part-way`, `common-problems.md#repair-workflow-data-by-hand`) | - | 3 | 1 |
| CP2 | Target, record and refusal messages: not-managed, not-a-repository, already-managed, record errors (an unknown profile included), drift and collision refusals, the --force directory refusal, the OSError message, the verify/status next lines with the workflow-data step (P1: no printed write for Workflow data, update and bootstrap withheld, prose re-runs included, while the target holds Workflow data and a state template is missing or any inspection is incomplete) and the command-specific option rule, success next lines | CP1 | 4 | 1 |
| CP3 | Release, source, cache, integrity, package (malformed manifest shapes included) and containment messages, with the kind values on the three error classes and doctor pass-through | CP1 | 4 | 1 |
| CP4 | Report findings next steps and the workflow-data step (Recovery section included), the reworded not-verified note, and the status work-in-flight block (fail closed on partial inspection) with status's destination containment | CP1, CP2 | 3 | 1 |
| CP5 | Documentation (common-problems, exit-codes, update, install, verify, README, ARCHITECTURE), the docs-versus-output test, ROADMAP and the full gate | CP2, CP3, CP4 | 3 | 1 |
<!-- registry:end -->

Notes on the table: CP1 builds the machinery and the argument surface
alone, so the others only add table rows. CP2 (the target and the record) and
CP3 (releases, sources, cache, packages, containment) are independent of each
other after CP1. CP4 touches the report and `status`. CP5 is documentation,
the docs-versus-output test, and the full gate.

<!-- CP1 -->
**CP1 -- The next-step machinery and the argument surface** (REQ-2, REQ-3,
REQ-5, REQ-6).
- `src/workflow_manager/advice.py` (`PROGRAM`, `DOCS_BASE`, `page`,
  `next_step`, `writes_withheld`, the `kind`-keyed table, a first set of
  entries for the argument errors, A1's pattern: no command); `cli.py`: `prog="workflow-manager"`, a parser whose
  `error()` appends A1's `next:`, `help=` and descriptions for every
  subcommand and option (A4, A5), `main()` printing `error:` then `next:`.
- `docs/exit-codes.md`: the global-options sentence gets its own anchor
  (`#global-options`) that A1 links.
- `docs/update.md`: the `## Update the Manager` heading (step 2 moved under
  it, text unchanged); `docs/common-problems.md`: the `## An install stopped
  part way` section and the `## Repair workflow data by hand` section (a first
  paragraph each; CP5 completes them). All three exist
  before any checkpoint prints a link to them, so the page-resolution test
  holds checkpoint by checkpoint.
- Tests: `tests/test_operator_ux.py` helpers (command extraction and
  parsing, page resolution, the table-driven runner) and the A-rows.
<!-- /CP1 -->

<!-- CP2 -->
**CP2 -- Target, record and refusal messages** (REQ-1, REQ-2, REQ-5, REQ-6).
- T1 to T15, T17 to T20 (T10: `UnknownProfileError`, the record's profile; T15: `advice.workflow_data_step`, `advice.writes_withheld` and `Context.missing_templates`/`data_findings` (the full list, computed lazily and only when the target holds Workflow data, 3.2's evaluation order)/`release_dir_version`, the option-precedence rule, the `--` rendering of 3.1, `git init --`): the new exception subclasses, the corrected
  causes, the `next:` rows, the `--force` directory and ancestor-file
  refusal (D-5; the scan covers every ancestor of a written path below the
  target, and the installation record `.workflow-manager/installation.json`
  and its `.tmp` sibling), `Installation.read` wrapping `IsADirectoryError` (T20) and
  `UnicodeDecodeError` as `CorruptInstallationError` and nothing else (every other `OSError` goes to the D-6 handler), the `OSError` handler keyed on the
  command (D-6), `advice.Context`, `verify`/`status` next lines, success `next:`
  lines.
- Tests: one per row; the executed recovery, option-precedence and leading-hyphen cases of section 4; T13, T14 (including the read-only and `uninstall`
  cases), T18, T19, T20, the mixed T12, the mode-000 and non-UTF-8 records (Round 4 I-1, O-1) and the version/state cases of section 4; the existing
  corrupt-record test moved to the CLI; update-versus-dry-run parity keeps
  comparing the change lines only.
<!-- /CP2 -->

<!-- CP3 -->
**CP3 -- Release, source, cache, package and containment messages**
(REQ-1, REQ-2, REQ-5, REQ-6).
- R1 to R14, R17, C1 to C3 (inventory C-rows 2.4): the `kind` values on the
  three error classes and their raise sites, the manifest-shape handling of
  3.3a, the table rows, the doctor `could not resolve` pass-through.
- Tests: one per row, using an empty, a tampered and a missing `--release-source`
  directory, a damaged copy of a release directory, a tampered pin file
  (`source.PINS_PATH` redirected), `TMPDIR` inside the repository, and the
  malformed-manifest sweep.
<!-- /CP3 -->

<!-- CP4 -->
**CP4 -- Report findings and the work-in-flight block** (REQ-1, REQ-3,
REQ-4, REQ-5, REQ-6).
- `compatibility.py`: the F rows of section 3.4 (the P1 workflow-data step,
  `data_findings`, and the Recovery section's withheld writing commands
  through `advice.writes_withheld`), `read_work_items` and
  `_item_core`, `read_repository` computing `missing_templates` and the backup
  destination (no Git probe), the reworded
  `not-verified` note (it now takes the repository path); `cli.py`: `status`'s
  block and its destination containment (3.5a, C5), including the exit-1 move
  where Git cannot run.
- Tests: section 4's report and `status` items, including the fail-closed
  block cases and the whole-run no-write audit; the read-only audit extended.
<!-- /CP4 -->

<!-- CP5 -->
**CP5 -- Documentation, the docs-versus-output test, and the gate**
(REQ-7, REQ-8, REQ-5).
- Section 5's pages; `tests/test_operator_ux_docs.py`; ROADMAP item 7 marked
  Done at acceptance (it is made the current Next item at planning).
- `python3 tests/run_all.py` (full gate) and `tools/check_docs.py`.
<!-- /CP5 -->

## 7. Open decisions

`docs/TECHNICAL_DECISIONS.md` does not exist at the base commit, so no
"Open decision" row is touched or silently finalized. Decided here, for the
reviewer to challenge. Each has a recommendation.

- **D-1. Where the next step lives.** *Recommend:* a table in `advice.py`
  keyed by exception class (and `kind`), printed by `main()`; the raise
  sites keep only the cause. *Alternative:* embed the next step in every
  message at its raise site. Rejected: the right step depends on the
  invocation (the command, the target, the global options), which the raise
  site does not have, and embedding is how `update()` and `bootstrap()`
  reached the wrong text.
- **D-2. Format.** *Recommend:* `error: <cause>` then one `next: <step>` line,
  lower case, backticked commands, URLs for pages. *Alternative:* a single
  sentence. Rejected: a script or a person can find the `next:` line, and a
  test can parse the commands in it.
- **D-3. What replaces reading state JSON.** *Recommend:* `status` prints the
  active work items (id, phase, type, governing version), from the reader
  `doctor` already uses, and points to `doctor`; nothing else. *Alternatives:*
  (b) point to `doctor` only, with no `status` change (smallest, but the
  everyday question "is anything running here?" still sends people to the
  JSON); (c) a new `work-items` command (rejected: a second Workflow command
  line, and a growing surface). The recommendation adds no command, no field
  and no write; the block's reader runs no Git and the block cannot change
  `status`'s exit code (the containment of D-14 can, and is argued there).
- **D-4. Pages as URLs.** *Recommend:* `DOCS_BASE` (the repository's `main`
  branch) plus a test that every linked page and anchor exists in the tree.
  *Alternative:* relative `docs/...` paths, rejected because a wheel ships no
  `docs/`. Risk: a page moved later breaks the link; the test catches it
  before release, and a moved page already needs `docs/README.md` updated.
- **D-5. A directory in the way under `--force`.** Today
  `bootstrap --force` and `update --force` crash with `IsADirectoryError`
  (exit 1) after writing some files, because `force` skips the collision
  scan that also finds directories. *Recommend:* scan for directories in the
  way, and for any ancestor of a written path, below the target, that exists
  and is not a directory (T18, reported as `occupied`), even with `--force`,
  with the installation record `.workflow-manager/installation.json` and its
  `.tmp` sibling among the scanned paths (T19: the record is written by
  `installation.write`, not `_write`, so it is in neither `incoming` nor
  `_other_written_paths` and must be named),
  for `bootstrap` and `update`, and refuse before writing (a `CollisionError`,
  exit 2), which is the same refusal `_blocked_paths` already gives for the state
  and merge targets. This is where exit codes move, each a traceback's 1 becoming 2: for T13, T18 and T19 (a refusal before any write, replacing a crash after a partial install), and for T20. T20 is not a half-written install: a directory at `installation.json` is a record that cannot be read, which is T8's cause (only `IsADirectoryError` and `UnicodeDecodeError` are wrapped; an unreadable-by-permission record stays T14's exit 1), and T8 already exits 2, so the same cause gets the same code for every command (`status`, `verify`, `doctor`, `uninstall`, `bootstrap`; today each is a traceback with exit 1). No other code moves under D-5. `docs/exit-codes.md` (section 5) records both moves and already tells people to report tracebacks.
  *Alternative:* leave it (rejected: the half-written install is the
  worst outcome the tool can produce). T18 reproduces without `--force`, so
  the scan is not a `--force` special case.
- **D-6. Other `OSError`s.** *Recommend:* print `error: <reason>` and a `next:`
  line, and keep **exit 1**, the code the traceback has today. *Alternative:*
  exit 2 (rejected here: the brief says codes stay stable, and this is not a
  refusal). The `next:` text does not promise a plain re-run (a truncated file from a disk-full write needs `--force`) and is keyed on `advice.writes_repository(args)`: `--force` and "a partial write" appear only for `bootstrap` and `update` without `--dry-run`, the commands that write release files (`update --dry-run` writes nothing and takes the read-only text); a read-only command and `uninstall` get their own text (3.3, T14). The handler comes after the existing `FileNotFoundError` one (an
  `OSError` subclass that already exits 2), so no existing exit code moves.
- **D-7. A `next:` line on success.** *Recommend:* yes for `bootstrap` and
  `update` (verify, review, commit: today only the pages say it), none for
  other commands. The dry-run prints none (its Recovery section already
  does). The parity test compares change lines, which are unchanged.
  *Alternative:* none (rejected: it is the cheapest way to meet "the tool
  tells the operator").
- **D-8. Upgrading the Manager.** *Recommend:* messages link to a new
  `docs/update.md#update-the-manager` section (today step 2 of Steps), which
  holds the download, checksum and `pipx` commands. *Alternative:* print the
  six-line recipe in the message (rejected: it would duplicate the page), or a
  `workflow-manager self-update` command (rejected: the Manager would become a
  package manager, and it has no signed channel of its own to update from).
- **D-9. Where an integrity failure is reported.** The Manager repository has
  GitHub Issues turned off, so "report it in the Manager repository" (today's
  `docs/common-problems.md`) cannot be done. *Recommend:* say "report it to
  the Manager's maintainer, with this message" and name no URL; the owner may
  turn Issues on later, and then one string changes.
- **D-10. The program name in usage text.** *Recommend:* `workflow-manager`
  (the installed command) for `python3 -m workflow_manager` too. Existing
  tests that match `workflow_manager:` in argparse output: none found at the
  base commit.
- **D-12. The Manager never prints a write for Workflow data (P1).**
  *Recommend:* one principle for T15, F-c and Recovery
  (`advice.workflow_data_step`): for a missing, unreadable or malformed state
  file, config file, `ACTIVE_MILESTONE.md` or declarations file the Manager
  prints (1) a copy-aside command when the file exists (`cp -p -- PATH
  PATH.bak`, the first free `.bak` name, the path quoted), (2) read-only
  history readers that show where a good copy is (the two forms of 3.4 P1:
  `env GIT_NO_LAZY_FETCH=1 git -C X --no-optional-locks ... log` and `... show --no-textconv`; never
  `git status`, which refreshes the index and runs clean filters) and (3) the page that explains the
  manual repair, and **never** `git restore`, `git checkout --`, `update` or
  `bootstrap`; `update` and `bootstrap` (and the Recovery section's whole-tree
  undo) are also withheld for every other Workflow-data problem or incomplete
  inspection while the target holds Workflow data, by the one predicate
  `compatibility.writes_withheld` (re-exported by `advice`; 3.2, computed from
  the findings list; unmanaged targets included, the not-managed finding and the
  installation-record finding not counted (`compatibility.PREDICATE_EXCLUDED`):
  an unmanaged target with intact data, and a damaged record with intact data,
  keep a caveated `bootstrap`, L11-I-2, L13-I-1; the full list, and its Git, is
  computed only when the target holds Workflow data, L13-I-2; prose re-runs go through it too, L11-I-3), because one `update` or `bootstrap` recreates every
  missing template and a restore discards edits Git cannot see
  (R2-I-1, L9-I-1, R3-I-2).
  The operator decides. This replaces Round 6's `git_copy` classification
  (`ls-files`, `rev-parse`, `ls-tree` probes and the `"index"`, `"head"`,
  `"none"`, `"unknown"` answers): a classification can be wrong in a case
  nobody listed (a broken ref read as an unborn `HEAD`, R2-I-3; a template
  recreated alongside the one being repaired, R2-I-1; an uncommitted edit under
  a restore, R2-I-2), whereas a rule that prints no write cannot lose data. It
  needs no probe, so the probe machinery is dropped from the design and the
  tests. *Alternatives:* keep the probes and add a "complete write set" check
  (rejected: it is still a classification whose every miss destroys or blanks
  data, and the review found three misses in two rounds); print `restore` only
  after a backup (rejected: it still overwrites, and the operator may not want
  that copy). *Cost:* the operator runs two or three read-only commands instead
  of one pasted repair; the page makes them cheap.
- **D-13. Printed command construction.** *Recommend:* a command-specific
  option rule (`--release-dir` is carried only when its version matches the
  command's) and `--` before a positional that starts with `-`. *Alternative:*
  carry every global option (rejected: it makes the installed-release repair
  fail, I-4) and rely on quoting (rejected: it does not make `-repo` parse, I-5).
- **D-14. `status` of a managed repository is contained like `doctor`.** *Recommend:* validate the
  destinations first, refuse with exit 1 (the existing release-error exit) if
  one is inside the target or `.git` **or if containment cannot be checked**
  (Git cannot run or answer). This is an **exit-code move for `status`**, from
  0 to 1, for a clean **managed** repository in those two situations (reproduced at the
  base; Round 6 I-3), argued as section 1 item 5 (c) and 3.5a say: a command
  that promises to write nothing must not report `clean` when it cannot prove
  it. An **unmanaged** target is outside the guard and keeps today's behavior
  and exit 0, with or without release options (Round 7 O-1; tested). *Alternatives:*
  resolve with the default destinations (rejected: it
  creates `.git/status-cache/*.lock`, reproduced); skip the comparison on a
  refusal and exit as an unverified status does (rejected: it also exits 1,
  because `cmd_status` returns 1 when `verified` is false, and loses the
  cause); contain the unmanaged explicit-option resolution too (rejected here:
  it moves a base exit 0 for no requirement; listed in 3.6 as a known gap).
- **D-15. `doctor` exits 2 for a manifest that crashes it today.** At the base
  `doctor --release-dir` on an unhashable `workflow_version` or a non-text
  `location` ends in a traceback with exit 1, which the contract reads as
  "warnings" (`docs/exit-codes.md`), while every other unusable release (a
  `null` manifest, `artifacts` of the wrong type, a missing `upstream`, a
  non-text `workflow_version` the release check rejects) already gives `doctor`
  exit 2, "could not check". *Recommend:* classify the crash like its
  siblings, so `doctor` exits **2** (recorded in section 1 item 5 (d), REQ-5,
  3.3a, `docs/exit-codes.md` and `docs/ACTIVE_MILESTONE.md`, asserted by value
  in the sweep). *Alternative:* keep exit 1 with a `cmd_doctor`-only
  special case for this one kind (rejected: it would make the same kind of
  failure exit differently in one command than in the others, and a script that
  reads 1 as "findings, read the report" would be misled by a message that
  has no report; but it is **not unsafe**, so the reviewer may choose it, and
  the plan then drops move (d)). Every other command keeps its exit in the
  table.
- **D-16. Accepted manifest shapes stay accepted.** A scalar `workflow_version`
  (`null`, a number, a boolean, `""`) succeeds today in `package build`,
  `bootstrap` and `update` (exit 0, the value reaching the installation
  record). *Recommend:* keep accepting it; this milestone classifies crashes
  and does not tighten acceptance, so no exit-0 cell of 3.3a becomes 1.
  *Alternative:* reject a non-text version at the one place that reads it
  (`Release`), moving those `0` cells to `1`: rejected here because it changes
  what a release may contain, which no requirement of this milestone asks and
  which the release-manifest schema (the Workflow's) owns, but it is safe, and
  it is left to the user as a later decision.
- **D-11. Version.** A `feat:` title releases Manager 1.8.0; the change is
  user-visible (new output, new `status` block).

## 7.1 Round 1 review disposition

Sections 7.1 to 7.6 record each round as it was accepted. Where a later round
replaced a mechanism, 7.7 says so; in particular Round 7 replaces Round 6's
`git_copy` probes (I-1, I-2) by P1.

All five Important and all seven Optional findings were validated against the
code at `218155d` and accepted; none was rejected.

- **I-1, I-2 (T15):** the printed `update` carries `--release-version V`; a
  deleted generated file prints `git restore`, never `update`; `unexpected:`
  lines get their own step (3.3, T15; `cmd_update` resolves the newest pin
  when no version is given, `cli.py:_release`).
- **I-3 (T18):** new inventory row and test; D-5 widened to ancestors, with
  or without `--force` (`_collisions`/`_blocked_paths` test the leaf only).
- **I-4 (T14):** the claim is narrowed to what holds; a truncated-file test.
- **I-5 (T8):** bootstrap is given the release the repository was on.
- **O-1:** T9 splits by the schema value. **O-2:** C3 setup corrected, CP4
  says "the F rows". **O-3:** drift and collision refusals keep printing
  without `error: ` (3.1). **O-4:** A1 echoes the operator's argv (replaced in Round 11: A1 prints a pattern, no command, 7.10).
  **O-5:** R12 and T15's `release:` are defensive (3.6). **O-6:** T16's
  condition stated (3.3). **O-7:** T14 links a user page.
- **Architecture concern:** `advice.Context` (3.2).

## 7.2 Round 2 review disposition

Both Important findings and all six Optional findings were validated against
the code at `218155d` and accepted; none was rejected.

- **I-1 (T14):** the `OSError` handler sits in `cli.main`, so it catches
  every command's error; the text is now keyed on `context.args.command`
  (3.3, T14), with a read-only test. **I-2 (T19, T20):** reproduced at the
  base (`FileExistsError` after a fully written install); D-5's scan names
  the installation record, its `.tmp` sibling and their ancestors;
  a directory at `installation.json` is wrapped as the T8 cause.
- **O-1:** CP1 creates the two anchors. **O-2:** T15 and F-c fall back to
  `update` when Git has no copy. **O-3:** `unexpected:` reworded. **O-4:**
  a mixed T12 list takes the directory text, with a test. **O-5:** every
  global option is carried into printed commands (3.3). **O-6:** the 3.5
  example prints the em dash.

## 7.3 Round 3 review disposition

Both Important findings and all five Optional findings were validated against
the code at `218155d` and accepted; none was rejected.

- **I-1 (T14, `update --dry-run`):** `cmd_update` returns `cmd_dry_run(args)`
  when `args.dry_run`, so `args.command == "update"`; the selector is now
  `advice.writes_repository(args)` and the dry run takes the read-only text
  (3.3, T14; D-6), with a test. **I-2 (T20):** option (a): section 1 item 5,
  REQ-5, D-5 and `exit-codes.md` name the move and argue it (same cause as T8,
  which exits 2).
- **O-1:** T8 is asserted as the placeholder `V` form; by-value stays for
  T15. **O-2:** the T19 `update` case is a directory at
  `installation.json.tmp`. **O-3:** only a directory at the record paths is
  refused; a regular `.tmp` file is a harmless leftover. **O-4:**
  `Context.git_has_copy`, computed by `cli` only for a generated `missing:`
  line, failing closed to `git restore`. **O-5:** "leave out
  --release-version and --release-dir".

## 7.4 Round 4 review disposition

The Important finding and the Optional finding were validated against the code
at `218155d` (`Installation.read` catches `JSONDecodeError`, `KeyError` and
`TypeError` only, so a `PermissionError` is a traceback with exit 1 and
`UnicodeDecodeError` a bare `ValueError` with exit 2) and accepted; none was
rejected.

- **I-1 (T20):** `read` wraps `IsADirectoryError` only, not every `OSError`;
  a `PermissionError` keeps exit 1 and takes T14's text, so no `next:` line
  tells the operator to delete an intact record and the only exit-code moves
  are T13, T18, T19 and T20 (3.3, T8/T20 row; CP2; D-5), with a mode-000 test
  for `status` and `update` (section 4).
- **O-1 (T8):** `UnicodeDecodeError` joins `read`'s wrapped causes and takes
  T8's text, exit 2 unchanged (section 2, T8 row; 3.3), with a test.

## 7.5 Round 5 review disposition

All six Important findings and both Optional findings were validated against
the code at `218155d` (and each reproduction read from the cited lines) and
accepted; none was rejected.

- **I-1 (state recovery):** missing and existing-but-unusable files are split;
  restore uses `--source=HEAD --staged --worktree`; `update` only for a
  confirmed no-copy file, pinned to the installed release; no write command
  for a malformed existing file or when Git cannot answer; the Recovery
  section follows the same policy (3.3 T15, 3.4 F-c, D-12), with executed tests.
- **I-2 (`status` writes):** whole-command containment, permitted external
  cache writes distinguished from target and `.git` writes, exit 1 kept (3.5a,
  C5, D-14), with a symlink and whole-run audit.
- **I-3 (partial inspection):** `none` only for a complete, problem-free
  read; unknown schema, governing version, phase and malformed entries print
  `incomplete` or `could not be read` (3.5).
- **I-4 (global options):** a command-specific rule; `--release-dir` is carried
  only when its version matches; the reproducer is an executed test (3.3, D-13).
- **I-5 (`-repo`):** subcommand flags before the positional, `--` before a
  hyphen-leading path; executed test (3.1, D-13).
- **I-6 (inventory):** T10 (`update` inherits the record's profile) and R17
  (malformed manifest shapes) added; fixed at the raise sites with the same
  exit codes, and a no-traceback sweep (3.3, 3.3a).
- **O-1:** the no-Git assertion is scoped to the state reader. **O-2:**
  `docs/ACTIVE_MILESTONE.md` is refreshed to revision 6.

## 7.6 Round 6 review disposition

All three Important findings and all four Optional findings were validated
against the code at `218155d` and accepted; none was rejected. I-3's two
reproducers were checked against the base (`env -i PATH=/nonexistent python3 -m
workflow_manager status r` and `--release-cache r/.git/mycache status r`: both
`clean`, exit 0; `cmd_status` returns 0 when `verified` and no problems).

- **I-1 (index before `HEAD`):** `git_copy` checks the index first; `"index"`
  prints plain `git restore -- PATH`, `"head"` only when the index has no entry
  (3.2, T15, F-c, D-12), with executed case (b′) (section 4).
- **I-2 (`none` versus `unknown`):** three probes decided by output
  (`ls-files -z`, `rev-parse --verify --quiet HEAD^{commit}`, `ls-tree -z
  --name-only HEAD`), any other exit `"unknown"`, one helper
  `compatibility.git_copy` (3.2); unborn-`HEAD` and Git-refuses cases (section 4).
- **I-3 (`status` exit code):** option (i): the move is listed, argued and
  tested; section 1 item 5 (c), REQ-5 (plan and mapping), the C5 rows, 3.5,
  3.5a, D-3, D-14, `exit-codes.md` and `docs/ACTIVE_MILESTONE.md` name the same
  set, and the statements that `status` runs no Git are narrowed to its
  reader.
- **O-1:** `git init -- X`; the assertion is "run as written, has its effect".
  **O-2:** one helper called by `cli` and `read_repository`. **O-3:** the count
  line says `N problem(s)`. **O-4:** a `local` source keeps no command.

## 7.7 Round 7 review disposition (external plan review, round 2)

Verdict: REVISE on revision 7; four Important findings (R2-I-1 to R2-I-4) and
one Optional (O-1), none Blocking. Round 1's I-2 to I-5 were resolved and are
unchanged. Each finding was reproduced or read against the code at `218155d`
and accepted; none was rejected. The reviewer's three recovery findings
(R2-I-1, R2-I-2, R2-I-3) have one root: the design classified a path by what
Git holds and printed a write for some classes. Patching each miss (a
complete-write-set check, a backup condition, a better unborn-`HEAD` test)
would leave the classification, so the revision applies one principle and
removes the classification.

- **P1 (R2-I-1, R2-I-2, R2-I-3):** for missing, unreadable or malformed
  Workflow state, config, `ACTIVE_MILESTONE.md` or declarations files the
  Manager never prints a command that overwrites, restores over or recreates
  them (no `git restore`, no `git checkout --`, no `update` as a repair). It
  prints a copy-aside step when the file exists, read-only inspection that
  shows where a good copy is, and the page that explains the manual repair
  (3.4, T15, D-12). The `git_copy` helper, its three probes and `Context.git_copy`
  are removed from the design and the tests; the unreadable-declaration branch
  is gone (an unreadable file gets the same step, with a permissions pointer
  and no copy). **R2-I-1:** `update` is also withheld for every other problem
  while any state template is missing (`Context.missing_templates`, a
  filesystem check), because one `update` recreates all of them
  (`install.py:plan_update`); the Recovery section follows with no exception.
  **R2-I-2:** an existing malformed declarations file is copied aside before
  anything and never restored over. **R2-I-3:** no probe can mistake a broken
  `HEAD` for an unborn one, because no step depends on the answer. Tests
  execute the printed commands for every missing/staged/unborn/broken-ref/
  malformed/unreadable case, a mixed missing-templates case and a `.bak`
  that already exists (section 4).
- **P2 (R2-I-4):** the version's shape is validated before the pin lookup
  (`source.local_release`, 3.3a). The exit of every manifest case was recorded
  from the unchanged code, per command (the table of 3.3a, which the sweep
  asserts by value). The rule: classify only what crashes, keep accepting
  what succeeds. A scalar `workflow_version` succeeds today in `package build`,
  `bootstrap`, `update` and `update --dry-run` and keeps succeeding (D-16:
  tightening is left open, with the argument). The one exit that moves is
  `doctor` on the two shapes that crash it today, 1 to 2 (D-15, an explicit
  open decision with the alternative that keeps 1 and is not unsafe).
  The Round 5 sweep's blanket "exit 1" assertion is replaced by the table.
- **O-1:** containment applies only to managed targets (3.5a, D-14); an
  unmanaged `status` keeps today's behavior and exit 0, with or without
  `--release-version`, `--release-cache` or `--release-dir`; a remaining base gap
  (an unmanaged `status --release-version` resolves into a cache that may be
  inside the target) is recorded in 3.6 and the unchanged behavior is tested
  (section 4: cases 5 to 8).
- **Checkpoints and mapping:** the three registry names that mention the
  recovery policy and the page anchors are updated (CP1: a third anchor,
  `common-problems.md#repair-workflow-data-by-hand`; CP2 and CP4: the P1
  step); REQ-5 names the four exit moves. No checkpoint is added, removed or
  re-ordered.

## 7.8 Round 8 review disposition (local plan review, round 8)

Verdict: REVISE on revision 8; one Important finding (L8-I-1) and two
Optional (O-1, O-2), none Blocking. All accepted; each checked against the
code at `218155d`.

- **L8-I-1:** confirmed. `install.bootstrap` writes every state template that
  does not exist (`install.py:368`, the `release.state_templates()` loop), and
  `update` does the same, so T3's `update X` and T8/T10's `bootstrap X` could
  blank a template Git holds a customised copy of. The rule is now structural:
  `advice.manager_command` withholds `update` and `bootstrap` for a managed
  target while `context.missing_templates` is non-empty (3.2, T15, T3, T8),
  and `missing_templates` is computed without a readable record. Test (f) runs
  over every `next:` and Recovery text, with missing-template variants of T3
  (executed as printed), T8 to T10, T20, T11, T12, T15 and F-b. T1, T2, T4, T5
  and T7 were stated out of scope there (an unmanaged target has no Workflow
  data); Round 9 L9-I-1 shows that statement false and replaces it (7.9).
- **O-1:** confirmed by running the sweep: with no `--release-version`, `verify`
  and `status` on a `location` row exit 1 without a traceback (the
  requested-version comparison precedes `_copy_snapshot`). The two cells are
  corrected to `1`, and a variant row with the manifest's own version records
  the crash path (`1 tb` in all six commands). `doctor` stays `1 tb` in both.
- **O-2:** both sentences corrected (D-5; 3.5a).
- **Missing tests:** the three listed are in section 4 (f) and the sweep row.

Everything else in revision 8 is unchanged. No checkpoint is added, removed or
re-ordered.

## 7.9 Round 9 review disposition (local plan review, round 9)

Verdict: REVISE on revision 9; one Important finding (L9-I-1) and one
Optional (O-1), none Blocking. Both accepted; checked against the code at
`218155d`.

- **L9-I-1:** confirmed. `install.bootstrap` writes every state template that
  does not exist (`install.py:368`, the `release.state_templates()` loop), and
  skips only a template that is present (`path.exists()`); it does not look at
  whether the target had a record. A target holds Workflow data with no record
  after T8's own `delete X/.workflow-manager` and after `uninstall`
  (`install.py:685`, "Repository-local state stays"), so T7/T5/T4's printed
  `bootstrap X` could blank a customised template Git holds. The guard is
  rekeyed from "has a `.workflow-manager` record" to "holds Workflow data": a
  path at `.workflow-manager` (any type) or at least one state template
  present, both plain `lexists()` checks with no Git probe. `missing_templates`
  is computed for unmanaged targets too. A fresh repository keeps its
  `bootstrap`. The all-templates-missing, no-record repository stays
  indistinguishable from a fresh one and is the stated residual (3.2); T8's
  text already says to restore the data first. 3.2, T15, D-12 and test (f) are
  updated, including the two reproducers and the T19 case.
- **O-1:** accepted. One definition ("the target holds Workflow data", 3.2) is
  used by 3.2, T15 and D-12; `is_managed` is not the predicate. D-12 now names
  `bootstrap` as well as `update`.
- **Missing tests:** the four listed are in section 4 (f): T8's deletion
  followed by `status`/`verify`/`update`, `uninstall` followed by a missing
  template, T19 with one template missing and another present, and a fresh
  repository keeping `bootstrap` by value.

Everything else in revision 9 is unchanged. No checkpoint is added, removed or
re-ordered.

## 7.10 Round 10 review disposition (external plan review, round 3)

Verdict: REVISE on revision 10; three Important findings (R3-I-1 to R3-I-3) and
one Optional (R3-O-1), none Blocking. Each was reproduced or read against the
code at `218155d` (`compatibility.py:137` renders plain Git; `:147` and `:570`
hold the Manager's own protective flags; `:1003` and `:1076` add declaration
failures straight to `findings`; `:1237` prints the whole-tree
`git restore`) and accepted; none was rejected. The three share one root, as
Round 7's did: the principle (the Manager prints nothing that can write or lose
Workflow data) was applied to a subset of the places that print commands. The
revision tightens the principle, not the case list.

- **R3-I-1 (A1):** the parser error handler prints no executable command: a
  usage **pattern** with placeholders and the docs page (3.3 A1). A pattern
  is not runnable, so the missing-template guard has nothing to guard there and
  no exemption weakens P1. Test (h) executes the reviewer's reproducer (a
  customised config deleted from the worktree).
- **R3-I-2 (Recovery):** one predicate, `advice.writes_withheld`, computed from
  the **findings list itself** (any `incomplete-inspection` finding, whatever
  feeds it, or a missing template, while the target holds Workflow data),
  serves exception advice, finding details and Recovery alike (3.2). Recovery
  withholds **every** command that writes Workflow data or the tree: `update`,
  `update --force`, `bootstrap` and the whole-tree `git restore ... -- .` undo
  (3.4). Test (i): malformed declarations with empty `facts.problems`;
  committed malformed state; committed malformed state with assume-unchanged
  edits (the baseline restore is shown to discard them); unknown and newer
  schema; missing `ACTIVE_MILESTONE.md`; unreadable state; drift together with
  each; and the predicate asserted both ways.
- **R3-I-3 (inspection commands):** `git status` is dropped from every
  Workflow-data step. The two printed forms are `git -C X --no-optional-locks
  --no-pager log --oneline --no-show-signature -- PATH` and `git -C X
  --no-optional-locks --no-pager show --no-textconv REV:PATH` (3.4 P1). Test
  (g) runs each against a repository with stale index stat data, a selected
  clean filter and marker helpers for textconv, pager, fsmonitor and signature
  programs: `.git` byte-identical, no marker. The test, not the flag list, is
  the arbiter. Not touched, and stated so: T17's `git -C X status` and the
  Recovery section's baseline "Before the update" `git status --short` are
  review lines the operator runs knowingly; they are not Workflow-data steps and
  are not described as read-only.
- **R3-O-1 (manifest sweep):** the sweep's fixture condition is stated (the
  clean committed fixture of `tests/frozen_runs.py`) and both outcomes are
  recorded for the two `doctor` cells (3.3a).

Everything else in revision 10 is unchanged. No checkpoint is added, removed or
re-ordered.

## 7.11 Round 11 review disposition (local plan review, round 11)

Verdict: REVISE on revision 11; three Important findings (L11-I-1 to L11-I-3)
and three Optional (L11-O-1 to L11-O-3), none Blocking. Each was read against
the plan and the code at `218155d` and accepted; none was rejected. They share
one root: the principle was enforced where a command is *rendered* and not
where the plan prints *prose* re-run instructions or Git commands built outside
those renderers.

- **L11-I-1 (printed Git outside Workflow-data steps):** T8 prints the two
  vetted history readers for the record (`log --oneline`, then `show
  --no-textconv REV:PATH`); `log -p`, which runs a textconv driver, is gone.
  T11 and T15 drop `git -C X diff` (plain `git diff` runs a selected clean
  filter and no flag disables it; the report's `modified:` lines already name
  the files). Test (g) is scoped by name: every printed `git` command except
  the three review lines **not claimed read-only**: T17's `git -C X status`,
  Recovery's `git status --short`, and the whole-tree undo's `git restore` and
  `git clean -n -d` (all four are operator-run review or undo lines, not
  Workflow-data steps). Textconv on `*.json` joins its hostile configuration
  and T8 joins its cases.
- **L11-I-2 (one predicate for an unmanaged target with data):** 3.2's single
  definition stands. `compatibility.NOT_MANAGED_PROBLEM` (the text at
  `compatibility.py:396`) is **excluded** from `data_findings` and from the
  predicate, because the installation record is not Workflow data. The one
  outcome: `uninstall` with every template intact, then `status`, prints
  `bootstrap X` with the release-version caveat, and running it leaves every
  data byte intact (`install.py:371` keeps existing templates). T15's
  sentence and D-12 are corrected to match; test (j)(1) and (2) assert both
  sides by value.
- **L11-I-3 (prose re-runs):** the predicate is an input to every re-run
  phrase, through `compatibility.rerun_phrase` and the required `withheld`
  keyword of `manager_command` (3.2). T14's write text and T12's prose are
  keyed on it; under the predicate they print the workflow-data step and
  "do not run it again until the Workflow data named above is back in place".
  The same renderer covers T1, T2, T13, T18, T19, R3, R8, R9, R12, C3 and
  Recovery. Test (j)(3) to (5).
- **L11-O-1 (slash commands):** exempt, and said so (3.4): the Workflow's own
  validated writer recreates no blank template. Their wording no longer
  presupposes an update. Test (j)(6).
- **L11-O-2 (one home):** `writes_withheld` and `NOT_MANAGED_PROBLEM` live in
  `compatibility` and `advice` re-exports them; `recovery_steps` and `advice`
  call the same function; no import cycle.
- **L11-O-3 (apparatus):** CP2's registry name and table row now state the
  current predicate (any incomplete inspection, not only a missing template).

Everything else in revision 11 is unchanged. No checkpoint is added, removed or
re-ordered.

## 7.12 Round 12 external review disposition (external plan review, round 4)

Verdict: REVISE on revision 12; two Important findings (R4-I-1, R4-I-2) and
two Optional (R4-O-1, R4-O-2), none Blocking. Each reproduction was read
against `compatibility.py` and accepted; none was rejected.

- **R4-I-1 (lazy fetch):** every printed inspection `git` command is prefixed
  with `GIT_NO_LAZY_FETCH=1` (env-assignment form, rendered by
  `compatibility.git_command` and parsed exactly by the parse test), in
  addition to `--no-optional-locks` (3.1, 3.4 P1; T8, T15, C3 and the
  rev-parse line). Test (g) gains the executed partial-clone case: absent
  promised object, no fetch, `.git` unchanged.
- **R4-I-2 (Recovery `git status`):** while the predicate is true Recovery
  prints no `git status` and no command outside the vetted log/show readers;
  it says to review the tree by hand. The exemption is removed from test (g)
  for that case; (g) and (j) assert the absence with a selected clean filter.
- **R4-O-1 (one findings list):** exception advice, finding details and
  Recovery receive the same findings list as the predicate input, Git-derived
  incomplete inspection included (3.2). Test (j) compares the three on an
  intact-template promisor fixture.
- **R4-O-2 (scope of (g)):** (g) covers every printed inspection command; the
  deliberate `git init` of T1/T2, the whole-tree undo and the two review
  lines (the baseline `git status --short` only while the predicate is false)
  are outside it, by name.

Everything else in revision 12 is unchanged. No checkpoint is added, removed
or re-ordered.

## 7.13 Round 13 local review disposition (local plan review, round 13)

Verdict: REVISE on revision 13; two Important findings (L13-I-1, L13-I-2) and
two Optional (L13-O-1, L13-O-2), none Blocking. Both Important findings were
checked against `compatibility.py` at `218155d` and accepted; none was rejected.

- **L13-I-1 (record finding counted):** `compatibility.py:381-399` and
  `1117-1119` make the installation-record finding exist for every T8, T9 and
  T20 case, so the full list made the predicate true for each and T8's
  `bootstrap` unreachable. The finding is excluded by the same rule as
  `NOT_MANAGED_PROBLEM`, through one named constant
  `compatibility.PREDICATE_EXCLUDED` (3.2, T8, T15, D-12), tested by value.
  Test (j)(7) adds the predicate-false T8 case and its executed twin.
- **L13-I-2 (Git in the full list):** `holds_data` is computed first by
  `lexists()`; the full list and its Git only when it is true (3.2, evaluation
  order). The "no Git" and "only Git call" statements (3.5, 3.5a, section 4,
  CP2) are narrowed to a target that holds no Workflow data; the Context
  definition of `data_findings` is corrected. Tests (j)(9) and the `status`
  cases (9) and (10) assert both halves, including the empty-`PATH` fail-closed
  case.
- **L13-O-1 (prefix representation):** the argv is `env GIT_NO_LAZY_FETCH=1 git
  -C X ...`, built by `git_command(..., inspection=True)`; the unprefixed lines
  use `inspection=False`. `printed_commands` and the parse test recognise the
  form ((j)(10)).
- **L13-O-2 (cross-reference):** 3.2's consumer (3) now states the no-`git
  status` rule and points to 3.4.
- **Architecture concern (silent widening):** answered by the named constant and
  its by-value test ((j)(8)).

Everything else in revision 13 is unchanged: R4-I-1, R4-I-2 and R4-O-2 stand,
and exits, pins, published releases and frozen Workflow semantics are
untouched. No checkpoint is added, removed or re-ordered.

## 8. Risks

- **A changed cause breaks a script that parses it.** Mitigation: every cause
  line keeps its first words; only the wrong ones (T3, T4) and the embedded
  advice (T8, R2, R12) change, and the exit codes do not.
- **A `next:` command that does not parse or does the wrong thing.**
  Mitigation: the parse test over every case, the page-resolution test, and
  the docs-versus-output test.
- **`status` reading state makes a fast command slower or fragile, or
  reports "none" falsely.** Mitigation: a state-only reader, no Git, a
  failure printed as one line, and `none` only for a complete read (3.5).
- **A recovery step makes things worse.** Mitigation: P1 (D-12): the Manager
  prints no command that writes Workflow data, whatever Git holds, so there is
  nothing to misclassify; executed tests assert that the printed commands are
  read-only or a non-clobbering copy, and that the bytes of every affected
  file survive (section 4). The cost is that the operator reads inspection
  output and decides.
- **Existing tests quote `status` output.** `test_bootstrap_e2e.py` compares
  `status` output before and after an operation; the new block is derived from
  the unchanged state file, so it is identical on both sides.
- **Scope growth.** The inventory has about fifty rows. The rows share a
  handful of texts; the checkpoints are table rows plus tests, and nothing here
  touches the update algorithm except D-5.
