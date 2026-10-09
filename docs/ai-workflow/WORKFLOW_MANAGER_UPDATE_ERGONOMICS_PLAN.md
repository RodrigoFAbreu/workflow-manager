# Workflow Manager: Update Ergonomics, `doctor`, `update --dry-run` and the Compatibility Report (Revision 6)

`work_item_id: workflow-manager-update-ergonomics` -- `governing_workflow_version: "2.2"`

**Deliverable:** a Manager release (1.6.0, from a `feat:` pull-request title)
in which an operator can see, before an update runs and without changing
anything, what a repository's installation looks like, what the update would
change and leave alone, which work in flight it could disturb, and how to
recover. Three pieces, one code path:

1. `workflow-manager doctor <repo>`: a read-only report on a repository.
2. `workflow-manager update --dry-run <repo>`: what the real update would
   change and leave alone, computed by the same function the real update
   applies.
3. A compatibility report, printed by both: the installed release, each active
   work item and the version that governs it, the latest available pinned
   release, migration hazards, fixes that apply only to new work, and recovery
   instructions.

**Work item type:** `process` (Manager tooling; no Workflow release).
**Base commit:** `bb54c76d201600605ee7a58cc355b8fdfe8436af` (tip of `main`;
Workflow 2.9.0 installed here with automatic gates, no `GATE_POLICY.json`).
**Branch:** `milestone/workflow-manager-update-ergonomics`. The milestone
reaches `main` through one pull request, opened and merged by the user. Its
title is `feat: ...` (a new command), which releases Manager 1.6.0.
**Scope source:** `docs/ROADMAP.md` "What's next" item 4 and its section 4;
the user's order of 2026-10-04, confirmed 2026-10-08.

## 1. Goal

### 1.1 Fixed inputs

1. `doctor` and `update --dry-run` **never write the target repository**:
   not its working tree, not its Git index, not its actual Git directory, not
   its common Git directory, not `.ai-review/`, not `.workflow-manager/`. The
   guarantee is about the target and is stated once, as three principles
   that section 3.6 specifies in full:
   - **P1.** Writes are allowed only to the Manager's own release cache and a
     freshly allocated temporary snapshot directory (resolving a pinned
     release is a verified download into the cache, then a copy,
     `source.py`'s `_copy_snapshot`, removed on exit; exactly what `update` and
     `verify` already do), and only when each is **outside** the target.
   - **P2.** Every destination is decided by **path arithmetic alone, before
     any filesystem write** (`os.path.realpath` over the options and the
     environment, never a call that creates a file), and the snapshot is then
     created with an explicit `dir=` on the validated directory.
   - **P3.** A command refuses (exit 2, a named message) only when a
     destination is **inside** the target or inside either Git directory. A
     target that merely lies inside the temporary directory (`/tmp/<repo>`) is
     fine: the fresh allocation is outside its tree.
   Both commands say so in `--help` ("writes the release cache and a
   temporary snapshot outside the repository, never the repository").
2. **The dry run shares the real update's code path.** `update` becomes
   "compute an `UpdatePlan`, then apply it"; `--dry-run` computes the same
   plan and prints it. There is no second implementation of "what would
   change" to drift from the first.
3. **Three versions stay distinct, and are labelled as such everywhere:**
   *installed release* (the Workflow release the repository's installation
   record names, e.g. `2.8.0`), *governing version* (the protocol version
   fixed on a work item at creation: `1`, `2.1` or `2.2`; **not** a release
   number), and *latest available release* (the newest pin in this Manager).
   A fourth, the *target release* of a particular update (`--release-version`,
   else the latest), appears only where it differs from latest.
4. **Commands print exactly as they execute.** Every command the report
   prints is built from an argv list and rendered with `shlex.join`, tagged
   with its family, and each family is validated against its own contract:
   *Manager* commands are re-parsed through the real `build_parser()` and
   must yield the intended namespace; *Git* commands are executed (or, for
   the destructive ones, their `-n` preview and the exact restore argv) in a
   disposable repository whose path contains spaces and shell
   metacharacters, and must behave as described; *slash* commands
   (`/retire-legacy-work-item <id>`) are checked against the installed
   release's published command file (`.claude/commands/<name>.md` exists in
   the target release's artifacts and its argument contract names the
   argument printed). A printed command with no family is a test failure.
   In particular the global
   `--release-version` option goes before the subcommand (`update ...
   --release-version` does not parse), and the program is named
   `workflow-manager`, not `workflow_manager`.
5. Frozen Workflow semantics, pins and Workflow releases are untouched. The
   report reads the Workflow's state file as data; it imports nothing from
   the installed `scripts/` and never takes `.ai-review/runtime/*.lock`.

### 1.2 What "done" means

- On a disposable repository, `doctor` and `update --dry-run` leave every
  byte of the working tree and of `.git/` (index included) identical, also
  when the repository is made read-only first.
- For every fixture the existing tests already build (clean update, locally
  modified file, collision, missing state, merged-file change, dropped file,
  profile change, interrupted update), `update --dry-run` reports exactly the
  change list, or exactly the refusal, the real `update` then produces.
- The three scenarios the user named produce their hazards: a `process` work
  item in `IMPLEMENTING` or later (`v2.4.0-001`), an active legacy work item,
  and a downgrade past each `CLAUDE.md` posture boundary.
- Byte, path and mode preservation is demonstrated for the target work tree
  and for the actual and common Git directories (linked worktrees included),
  **and the absence of transient target writes by the Manager process** (a
  file created and deleted within a run leaves no final trace, so an audit of
  write-capable events, with relative and `dir_fd` paths resolved, is recorded
  too, 3.6; the Git subprocesses' absence of writes rests on the hermetic
  contract P4 and the final-state snapshots, which the audit cannot observe),
  and real-update/dry-run parity, refusal parity and interruption convergence
  through the module-global `_write` are retained.
- The compatibility tables' meaning (not only their pin coverage) is verified
  against the published 2.9.0 behaviour. The existing checkpoint path
  classifications are preserved, and the frozen suites run unchanged.
- `python3 tests/run_all.py` is green; the docs check (`tools/check_docs.py`)
  accepts the new commands in `docs/update.md`.

## 2. Non-goals and invariants

- **N1.** No change to what `update`, `bootstrap`, `verify`, `status` or
  `uninstall` do or print, except that `update` gains `--dry-run`. The
  existing update tests pass unmodified, apart from the one `test_docs.py`
  header bump section 5 allows; they are the refactor's oracle.
- **N2.** No new refusal. The report warns; only the existing drift and
  collision refusals stop an update, and the dry run reproduces them rather
  than adding its own. (A downgrade stays allowed, as today; the report says
  it is unsupported.) The one addition is the dry-run-only containment guard
  of 3.6, which protects the target from the dry run's own cache and snapshot
  writes; it never changes what the real `update` does.
- **N3.** No new persisted file, no schema change to `installation.json`
  (`SCHEMA_VERSION` stays 1), no second source of truth. Everything shown is
  derived on demand from the installation record, the pins, the state and
  config files, and Git (roadmap principle 5).
- **N4.** No migration of live work-item state (hard rule).
- **N5.** `src/workflow_manager/published_releases.json`, `distribution/` and
  frozen Workflow semantics are not touched.

## 3. Design

### 3.1 `UpdatePlan`: the shared path (`install.py`)

`update()` today interleaves deciding with writing. It is split, behaviour
preserved:

```python
@dataclass(frozen=True)
class UpdatePlan:
    target: Path; current: Installation; updated: Installation   # the record it would write
    profile: str
    changes: list[str]            # the lines `update` prints, in order
    removals: list[str]; writes: list[PlannedWrite]   # PlannedWrite(path, data, executable, mode_only)
    left_alone: list[LeftAlone]   # (path, reason)

def plan_update(target, release, profile=None, force=False, now=None) -> UpdatePlan
def apply_update(plan, release) -> Installation
def update(target, release, profile=None, force=False, now=None):   # unchanged signature
    plan = plan_update(...); return apply_update(plan), plan.changes
```

- `plan_update` is pure: it performs every read and every check the old
  `update` did before its first write (managed-file drift, collisions, blocked
  paths) and raises the same `DriftError`/`CollisionError`/`InstallError`/
  `NotManagedError` with the same messages. It computes `changes` from the
  same comparisons the old code made while writing (`before != data`,
  executable bit, removal, missing state template, the two merges).
- The merges get a pure half: `_plan_merges` returns the bytes each merge
  would write, its change lines, and the new `installation.merged` entries;
  `_apply_merges` (still used by `bootstrap`) becomes plan + write, so
  bootstrap and update keep one merge implementation.
- `apply_update` performs the writes in the old order (removals, artifacts,
  state templates, merges, record last), so the "re-runnable after an
  interruption" contract and `tests/test_bootstrap.py`'s interrupt-at-every-
  write test hold unchanged. That test interrupts by patching `install._write`
  and counting its calls (`tests/test_bootstrap.py:773-850`), so `apply_update`
  must keep calling `install._write` **through the module global** (never a
  captured reference or a new helper), once per file, in the same order; the
  test's existing `assertGreater(total, 1)` guard stays, so it cannot pass by
  seeing zero writes.
- `plan_update` reads `release.read_verified` for every artifact up front,
  which is stricter than today's interleaved reads: a corrupt cached artifact
  now refuses before any write rather than part-way. That is an improvement and
  still behaviour-preserving for the existing tests.
- `left_alone` records what the update deliberately keeps, for the dry run:
  existing generated state files (`WORKFLOW_STATE.json`, `WORKFLOW_CONFIG.json`,
  `ACTIVE_MILESTONE.md`, ...), managed files already identical to the
  release, the repository's own text in `CLAUDE.md` and `.gitignore`, and
  `.ai-review/`. Each entry has a reason string.
- `--force` reaches the plan exactly as it reaches the update. Parity is
  defined on **`plan.changes`**: the dry run prints each `changes` line with a
  `would ` prefix in place of the real run's past-tense verb (`updated x` ->
  `would update x`), and a test maps one to the other line for line. A forced
  dry run additionally prints **annotations**, which are not parity lines and
  which the real run does not print: `would overwrite <path> (local edits
  discarded)` for each locally modified managed file the force discards,
  and the `left alone:` block.

### 3.2 The repository reader (`compatibility.py`)

`read_repository(target) -> RepositoryFacts`, read-only, no Workflow imports:

- the installation record (`Installation.read`; a missing record is "not
  managed", a corrupt one is reported with the record's own remedy text);
- `docs/ai-workflow/WORKFLOW_CONFIG.json` (`default_workflow_version`),
  `docs/ai-workflow/GATE_POLICY.json` (present or absent);
- `docs/ai-workflow/WORKFLOW_STATE.json` as JSON: `active_work_item_id` and
  every `work_items` entry's `phase`, `governing_workflow_version`,
  `work_item_type`, `parent_work_item_id`. Inspection that cannot be
  completed is **never a silent success**: each of these yields an
  `incomplete-inspection` finding (severity `warning`, section 4) carrying the
  reason, and `doctor` then exits 1 at the least, never 0: a missing state
  file in a managed repository, malformed JSON, an unsupported
  `schema_version`, a governing version outside `1`/`2.1`/`2.2`, an item or
  field of the wrong shape, an unknown phase, and any failed Git call that a
  detector needed. Per N2 these are advisory for `update` and `--dry-run`
  (they print the finding and the update still proceeds; no new refusal);
- Git facts via `git -C <repo> ...`: whether the tree is clean, the list of
  worktrees, and whether any commit carries the `Workflow-Legacy-Retirement`
  trailer. A failing Git call yields "unknown" (and an `incomplete-inspection`
  finding when a detector needed it), never an exception. **Git runs
  hermetically** (`compatibility.run_git`, the only Git entry point of the
  read-only paths): `GIT_OPTIONAL_LOCKS=0` is necessary but not sufficient (a
  configured `core.fsmonitor` hook still runs under `git status` and may write
  inside `.git`, and a history read in a partial clone can lazily fetch
  objects). Every call therefore passes `-c core.fsmonitor=false -c
  core.untrackedCache=false -c gc.auto=0 -c maintenance.auto=false -c
  core.hooksPath=/dev/null`, sets `GIT_TERMINAL_PROMPT=0`,
  `GIT_OPTIONAL_LOCKS=0` and `GIT_NO_LAZY_FETCH=1`, passes `--no-optional-locks`,
  and uses only commands that do not write by contract (`rev-parse`,
  `config --get`, `worktree list --porcelain`, `status --porcelain
  --no-renames --untracked-files=normal`, `log --grep`).
  **Lazy fetch is prevented by construction, not by trusting a variable.**
  `GIT_NO_LAZY_FETCH` is honoured only by recent Git (older ones ignore it, and
  `docs/install.md` names no Git minimum), so the result must not depend on the
  installed Git honouring it. Before **any** read that can touch objects
  (`status`, `log`), `read_repository` detects a partial clone with
  `run_git config --get extensions.partialClone` and `config --get-regexp
  '^remote\..*\.(promisor|partialclonefilter)$'` (read from the common
  Git directory's configuration; both are config reads, which never fetch).
  `run_git` returns the exit status with the output (it does not collapse
  every nonzero exit to `None` as `cli._git` does), because both probes exit
  **1** when the key is absent (checked with a fresh `git init`): exit 1 with
  empty output means "not a partial clone" and is the normal case of every
  ordinary repository. If either probe prints a value (exit 0), **or the
  detection itself fails** (any exit other than 0 or 1, a timeout, an
  `OSError`), the object-touching reads are skipped (never attempted) and `read_repository` reports an
  `incomplete-inspection` finding naming the partial clone: the dirty-tree fact
  and the two trailer searches are "unknown" (so the restore line is withheld,
  3.5). The variable stays set as defence in depth only.

A work item is **active** when its phase is not `MILESTONE_COMPLETE`. It is
**legacy** when its governing version is `1` or its phase is `LEGACY_READY`.
**Implementing or later** is the set `IMPLEMENTING`,
`SELF_REVIEWING_IMPLEMENTATION`, `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`,
`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
`AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, `APPLYING_REVIEW_FEEDBACK`,
`AWAITING_TECHNICAL_APPROVAL`, `AWAITING_FUNCTIONAL_REVIEW`,
`FIXING_FUNCTIONAL_FINDINGS`, `AWAITING_USER_ACCEPTANCE` **and
`AMENDING_PLAN`**. `AMENDING_PLAN` is a *known* phase, so the unknown-phase
fallback below would not catch it, yet an item reaches it only from
implementation: it has completed checkpoints and implementation-stage content
(the protected `scripts/`/`.claude/commands/` and the rest of its declared
set), which an update rewrites exactly as at `IMPLEMENTING`. The set is
therefore "every known phase except the pre-implementation plan phases
(`PLANNING`, `SELF_REVIEWING_PLAN`, `AWAITING_EXTERNAL_PLAN_REVIEW`,
`REVISING_PLAN`, `AWAITING_LOCAL_PLAN_REVIEW`,
`AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, `AWAITING_PLAN_APPROVAL`) and the
non-active `MILESTONE_COMPLETE`/`LEGACY_READY`", and a test fails when a phase
in 2.9.0's `KNOWN_PHASES` is in none of three classes: the plan-phase list,
the implementing-or-later set, or the two named non-active exemptions
(`MILESTONE_COMPLETE`, terminal; `LEGACY_READY`, dormant). `LEGACY_READY`
is exempt from the implementing-or-later set only: it stays reportable under
the legacy definition above. An unrecognised phase is shown verbatim and treated
as implementing-or-later (the cautious side), so a future phase name cannot
silently hide a hazard.

**The item's own implementation-stage declarations.** For the `v2.4.0-001`
trigger the reader also reads `docs/ai-workflow/registry/<work_item_id>-artifacts.json`
(the Workflow's own authoritative lookup, `artifacts_path_for_work_item` in
`workflow_fingerprint.py`: pure templating from the work item id, independent
of `registry_path`, which may be null or nonstandard and is not consulted; the
id is validated against the Workflow's id grammar before templating and a
failing id is an `incomplete-inspection` finding; plain JSON, read as data
like the state file) and takes its `implementation_stage`
`protected_paths`, `protected_prefixes`, `excluded_paths`, `excluded_prefixes`.
A path the update writes or removes counts when it classifies `protected` in
the Workflow's own order (`classify_path_implementation_stage`): exact
protected path, then protected prefix, then excluded path, then excluded
prefix, so an exclusion never overrides an earlier protection. Only when the
declarations file is missing or unreadable does the reader fall back to the
heuristic "any path under `scripts/` or `.claude/commands/`", and the finding
says it fell back. This covers managed `docs/ai-workflow/*` paths an item
protects (`workflow-v2-1-core` moved `MILESTONE_WORKFLOW.md` and
`REVIEW_PROTOCOL.md` into its `implementation_stage.protected_paths`).

**The plan stage is classified too.** The Workflow also classifies every path
changed in `base_commit..HEAD` (and the worktree, untracked paths included) at
the **plan** stage, through `classify_path` over the item's `plan_stage`
declarations (`load_plan_stage_classification`): **exact** protected path,
excluded path, excluded prefix, the ambient installation-record exclusion, else
`UnclassifiedPathError`. The plan stage has **no protected prefixes** (the
published loader reads `protected_paths`, `excluded_paths` and
`excluded_prefixes` only, and `classify_path` takes no protected-prefix
argument), and no heuristic fallback; the reader mirrors that exactly and
ignores a stray `plan_stage.protected_prefixes` key. That check is reached
from `implementing_entry_reachable` -> `approval_is_current` ->
`approval_review_content_id` (`docs/defects/v2.4.0-001-...md`, "Affects"), so
it matters for plan-phase items (plan-bundle generation, `review_content_id`)
and for implementing-or-later items (`implementing_entry_reachable`,
`/request-plan-amendment`) alike. The reader therefore classifies
`plan.writes`/`plan.removals` for **every active item that has an artifacts
file**, plan phases included, **at both stages**, each in its own stage's
order. The two merges (`CLAUDE.md`, `.gitignore`) appear in `plan.writes` as
`PlannedWrite`s (3.1), so the detectors see them: a merge-only update is a
real trigger when an item protects `CLAUDE.md` (this item's own
`implementation_stage` does).

- **Protected at the plan stage.** A managed path in an item's
  `plan_stage.protected_paths` (exact paths only) that the update rewrites
  changes the plan-stage `review_content_id`: a plan-phase item's bound bundle
  then drifts (`ReviewedContentDriftError`), and an implementing-or-later
  item's `plan_approval` goes stale. This is reported under `v2.4.0-001` with
  the stage named (section 4). **Both work-item types**: the Workflow's plan
  metadata resolution accepts `process` and `product` items alike, and a product
  item loses a bound plan bundle or a current approval the same way, so the
  plan-stage branch (here and in the `unclassified-paths` finding) applies to
  every active item with an artifacts file. Only the implementation-stage
  `v2.4.0-001` branch stays `process`-only (the defect's own scope).
- **Unclassified at either stage.** A path matching neither a stage's
  declarations nor the ambient exclusion is reported under `unclassified-paths`
  with the stage it fails at: the implementation stage only for
  implementing-or-later items (implementation review would refuse), the plan
  stage for every active item with an artifacts file. The two stages can
  disagree for one path (a path the implementation stage classifies but the
  plan stage leaves unclassified, for instance `.claude/settings.json`), and
  each is reported on its own.
- **Missing declarations.** A missing artifacts file, or one without a
  `plan_stage` (or, for the implementation stage, `implementation_stage`) key,
  is an `incomplete-inspection` finding for that stage; only the
  `v2.4.0-001` implementation-stage trigger keeps its heuristic fallback.

The installation record `.workflow-manager/installation.json` is a legitimate
ambient exclusion and never reported. The ambient set is read from the
installed Workflow's published behaviour and pinned by a test against the
2.9.0 package (not copied from memory). Because `compatibility.py` must not
import the installed `scripts/` (1.1 item 5), its classifiers are a copy of
the Workflow's two; a test runs both over a table of paths against the 2.9.0
package's own `classify_path` and `classify_path_implementation_stage` and
compares, so the two copies cannot drift.

`compatibility.run_git` is the one Git helper of the read-only paths
(`read_repository`, the trailer searches, and the containment check's
`rev-parse --absolute-git-dir`/`--git-common-dir` calls, which run before the
check); it reuses `cli._git`'s timeout but returns `(returncode, stdout)` (or a
failure marker for a timeout or `OSError`), so a caller can tell exit 1 ("key
absent") from other failures; every other caller treats a nonzero exit as
"unknown", as before. It adds the hermetic flags above. No second helper
exists. Paths printed by `rev-parse` (`--absolute-git-dir`, `--git-common-dir`)
are made absolute against the target directory before any `realpath` (a bare
`realpath` would resolve a relative `.git` against the process cwd);
`--path-format=absolute` is not used, since it needs Git 2.31 and
`docs/install.md` names no minimum.

### 3.3 Findings and the report

`build_report(facts, plan_or_refusal, target_release, latest, ...) ->
Report`: a list of `Finding(severity, id, title, detail, commands)` plus the
three-version header and the work-item table. Severities: `blocked` (the real
update would be refused; the refusal text is quoted), `warning` (the update
proceeds and could disturb something; read before running), `note` (fixes
that apply only to new work, informational). The catalogue (section 4) is
data in one module; each finding's trigger is a small function over
`RepositoryFacts` and the `UpdatePlan`.

The release-specific knowledge the Manager must carry, because only the
Manager knows what it pinned, is three tables in `compatibility.py`, each
keyed by release version, each with a source note, and **every pinned
version must have an entry (possibly empty)**, enforced by a test the way
`CI_SUITES` is, so pinning a release forces someone to decide:

- `DOWNGRADE_BOUNDARIES`: per release that introduced downgrade-relevant
  vocabulary (2.4.0, 2.5.0, 2.5.1, 2.6.0, 2.7.0, 2.8.0, 2.9.0), its signals
  and the `CLAUDE.md` posture sentence. A signal is a detector over the
  state file (a key present anywhere under a work item, a phase value, a
  governing version, a registry checkpoint id shape), over Git (the
  `Workflow-Legacy-Retirement` trailer, the `Workflow-Activation: 2.2`
  trailer, an `*.amendment.json` witness in the common git directory), or a
  **path-present** detector over the working tree (2.6.0's
  `.ai-review/<id>/plan-inputs/` directory, which is neither a state key nor a
  Git fact). The two trailer searches are two `git log` calls (so a match is
  attributed to its trailer by construction; one call with two `--grep`s ORs
  them and cannot say which matched), each with one `--grep` and
  `-n 1 --format=%H`, scoped to `HEAD` only (`git log HEAD`, never `--all`: a
  trailer on an unmerged branch is not this checkout's history), with a
  line-anchored match, passed as argv elements with no shell
  (`--extended-regexp`, `--grep=^Workflow-Legacy-Retirement:` and
  `--grep=^Workflow-Activation: 2\.2[[:space:]]*$`, each pattern containing a
  single backslash; `shlex.join` quoting is for display only) so a
  message that merely quotes the trailer name mid-line does not count. This is
  a **conservative approximation**, not a trailer parse: `git log --grep`
  matches any body line, so a line that starts with the trailer text but sits
  outside the final trailer block still matches. The report therefore words
  the signal "a trailer-shaped line was found in HEAD's history", never "a
  trailer was verified", and over-reporting is the safe side; a test pins both
  the match and this limit. A boundary whose hazard cannot be detected (2.7.0's
  "driven through the Orchestration Protocol") is listed with the line "this
  boundary has a hazard the report cannot detect", never silently omitted, so
  coverage is not implied.
- `NEW_WORK_ONLY`: per release, the fixes and defaults that reach only new
  work items or new installations (2.9.0: the `"2.2"` default is for new
  installations and an update never edits `WORKFLOW_CONFIG.json`; the
  `v2.6.0-003` fix covers new governing-`1` implementation entries only;
  2.8.0: nothing (see the next table: gates are evaluated from the
  repository's effective policy and the item's governing version, so
  existing items are affected, not only new ones); 2.6.0: the `feedback_layout:
  "scoped"` stamp is written only on items created under it, and the
  `v2.4.0-001` repair reaches earlier items through the release, not their
  declarations files; 2.5.0: implementation review stages only for items
  governed `"2.2"`).
- `GATE_DEFAULT_CHANGES`: 2.8.0 (a repository with no `GATE_POLICY.json`
  moves from human gates to automatic ones; decide the policy before the
  update). It applies to **existing** work items as well as new ones, by
  governing version and gate, mirroring the published `gate_mode` table
  (`_ALWAYS_HUMAN`): `plan_approval` stays human for governing `1`;
  `technical_approval` stays human for `1` and `2.1`; `acceptance` is
  automatic for every governing version. The finding lists, per active item,
  which of its gates change and which stay human. A test checks the table's
  meaning against the 2.9.0 package's `gate_mode` for every governing version
  and gate, not only that every pin has an entry.

Because absence in the working tree is not proof for the "ever held"
signals, the downgrade finding always says which signals were found *in the
current state* and that Git history was not searched beyond the retirement
trailer and the amendment witness; it never says "safe".

### 3.4 Commands

`workflow-manager doctor <repo>` takes no option of its own. Like `update`,
it honours the global `--release-version V` (placed before the subcommand)
to name the target release the report is measured against; the default is the
latest pinned release. One rule, no second spelling.

`workflow-manager update <repo> --dry-run [--force] [--profile P]` with the
same global `--release-version` as today. Its output is `update`'s own line shape
so an operator reads the same list the real run prints:

```text
would update /path/repo from workflow 2.8.0 to workflow 2.9.0     (dry run: nothing written)
  would update scripts/workflow_state.py
  would add .claude/commands/retire-legacy-work-item.md
  ...
left alone:
  docs/ai-workflow/WORKFLOW_STATE.json   repository-local state
  ...
```

followed by the compatibility report for that update. Exit codes: `update
--dry-run` exits 0 when the update would proceed, 2 when it would be refused
(the same exit the real update gives, with the same refusal text on stderr
and the same `--force` hint); `doctor` exits 0 when it found no `blocked` or
`warning` finding (an `incomplete-inspection` is a `warning`, so an
inspection that could not finish is never exit 0 and its report says
"inspection incomplete" in its headline), 1 when it found one, 2 on an error (`not a managed
repository`, unreadable record, or the **target** release cannot be resolved:
offline with an empty cache, an unpinned `--release-version`), mirroring
`status`/`verify`. `main()` maps `RELEASE_ERRORS` to exit 1, so `doctor`
handles a target-resolution failure itself and returns 2 ("could not check"),
keeping exit 1 unambiguous ("warnings found"). An unresolvable *installed*
release is different: the report is still produced, with the `not-verified`
note, and the exit is decided by its other findings. `update --dry-run` with
an unresolvable target exits as the real `update` does.

Report shape (headings fixed, tested):

```text
Repository      /path/repo
Installed release   2.8.0  (profile full, installed 2026-..., source package workflow-2.8.0.tar.gz)
Latest available    2.9.0  (this Manager pins 2.3.1 ... 2.9.0)
Target of this check 2.9.0  (--release-version, else latest)

Work items (governing version is a protocol version, not a release)
  ID                          PHASE                 TYPE      GOVERNING
  ...
Config default for new work items: 2.2

Findings
  [warning] v2.4.0-001 ...
Fixes that apply only to new work
Recovery
```

### 3.5 Recovery instructions

Static text with the repository path and target filled in, every command
rendered through `render_command` (3.1 input 4). The core:

1. Before the update: `git -C <repo> status --short` is clean, or the edits
   are committed; update on a branch.
2. An update that stopped half way is re-run with the same command; it needs
   no `--force` (the shipped contract).
3. To undo an update that has not been committed: `git -C <repo> restore
   --source=HEAD --staged --worktree -- .`, then review untracked leftovers
   with `git -C <repo> clean -n -d` (printed as a preview, never the
   destructive form). Printed with its precondition on the same line: "this
   is an undo only if the tree was clean before the update; it discards ALL
   uncommitted changes, not only the update's". When `doctor` sees a dirty
   tree, **or cannot tell** (a failed `git status`), it prints step 1 alone
   and withholds the restore line. A committed
   update is undone by reverting its commit.
   **Not** `update --release-version <older>`: that is the unsupported
   downgrade.
4. Per-finding recovery where one applies (a locally modified file: save it,
   then `update ... --force`; a legacy item that was finished long ago:
   `/retire-legacy-work-item <id>` after the update, offered only for an item
   that is exactly `LEGACY_READY`, is not `active_work_item_id` (a dormant
   item is never active), has no unfinished children, and when the target is
   2.9.0 or later; otherwise the report says why it is not offered, matching
   the published writer's refusals).

### 3.6 Read-only enforcement

**The guarantee (P1)** is about the **target**: its working tree, its actual
Git directory and its common Git directory. `doctor` and `update --dry-run`
never write there. Writes to the Manager's own release cache and to one freshly
allocated temporary snapshot directory are allowed **only when they are outside
the target** and its two Git directories.

`doctor`/`--dry-run` call no function that writes to the target:
`plan_update`, `read_repository`, `build_report`. A static check (no import or
call of `apply_update`, `bootstrap`, `_write`) is only a tripwire; it cannot
establish the safety of the resolver and subprocess side effects, so those
have explicit contracts and behavioural tests.

**Destinations are decided by path arithmetic only (P2), before any write.**
`compatibility.plan_destinations(options, environ, target)` is a pure function:
it calls `os.path.realpath` (symlinks count) over strings and creates, opens and
probes nothing. It must **not** call `tempfile.gettempdir()` (its first call
selects a directory by creating, writing and deleting a probe file, which
with `TMPDIR=<repo>` would write inside the target before any refusal),
`tempfile.mkdtemp()` without `dir=`, or any other call that creates a file. It
returns the validated destinations or raises the named refusal (exit 2):

1. **The target's protected set**: the realpath of the work tree, of
   `git rev-parse --absolute-git-dir` and of `--git-common-dir` (these differ
   in a linked worktree; the `rev-parse` calls run through `run_git` and write
   nothing). It fails closed: if the target has a `.git` entry but the
   resolution fails, the command refuses ("could not check containment"), and
   never checks the work tree alone.
2. **Cache destinations**: the cache root (`--release-cache`, else the
   environment, `source.cache_root`'s own order), and every leaf the resolver
   would open under it for the target and installed versions: `<root>/<version>.lock`
   and the version directory `<root>/<version>`. Each leaf's `realpath` (so a
   leaf that is a symlink into the target resolves into it) is tested, not only
   the root's. A symlink found inside an existing version directory (walked,
   not followed) is refused as well.
3. **Temporary-directory candidates**, in `tempfile`'s documented order:
   `TMPDIR`, `TEMP`, `TMP` (each when set and non-empty), then `/tmp`,
   `/var/tmp`, `/usr/tmp`, then the current directory. An environment-named
   candidate that lies inside the target or a Git directory is a **refusal**
   (the default allocation would pick it). Of the rest, the first candidate that
   exists as a directory, is accessible (`os.access`, which probes nothing) and
   lies outside the protected set is **the snapshot parent**; if there is
   none, the command refuses ("no temporary directory outside the target").

**Only then** does anything write. `source._copy_snapshot` gains an optional
`dir=None` parameter (default: today's behaviour, so `update`, `verify` and
`bootstrap` are unchanged, N1), and the read-only paths pass the validated
snapshot parent through one named call chain, so no hop falls back to the
default `mkdtemp()`: `cli` (`doctor`/`update --dry-run`) calls
`compatibility.plan_destinations`, then passes `snapshot_parent` and
`read_only=True` to `release.py`'s resolver entry point, which hands both to
`ReleaseCache.resolve` (and `local_release`); `resolve` passes `read_only` to
`_locked` and `snapshot_parent` to `_copy_snapshot(dir=)`. The
`gettempdir`-patched-to-fail test (5) fails on any hop that misses it. The
snapshot is created with `tempfile.mkdtemp(prefix=..., dir=<snapshot
parent>)` and nothing else. The resolver, handed a `read_only`
flag that defaults to False, opens each lock leaf with
`os.open(path, O_RDWR | O_CREAT | O_APPEND | O_NOFOLLOW)`, so a leaf that is
or becomes a symlink fails (`ELOOP`) instead of redirecting the write; it
reports `cannot use the release cache` and writes nothing.

**Refusal is only for a destination inside the target (P3).** A target that
lies inside the temporary directory (`/tmp/<repo>`, which every existing test
fixture is) is accepted: the fresh snapshot directory is a sibling allocation
outside the target's tree. The reverse condition is not a refusal. Parity: for
a destination outside the target neither the dry run nor the real update
refuses for containment, and a `/tmp/<repo>` target gets the same changes or
refusal from both. A destination inside the target is refused by the dry run
(the command that promises not to write the target); the real `update`, whose
job is to write the target, is unchanged (N1/N2) and is not claimed to refuse.
The parity tests therefore cover destinations outside the target only.

- **Subprocess contract (P4):** Git only through `compatibility.run_git`
  (3.2), hermetic as specified, with partial clones detected and their
  object-touching reads skipped rather than attempted; no other subprocess.
- **Evidence:** a recorded snapshot of path, mode and bytes of the whole
  target work tree **and** of the actual Git directory **and** the common Git
  directory (distinct in a linked worktree; a `.git` file is not the
  metadata), taken before and after each command, plus a run against a
  `chmod -R a-w` copy; **and a transient-write audit of the Manager process**: each command runs
  in a fresh process with a `sys.addaudithook` that records every `open` and
  `os.open` event whose mode (for `open`) or flags (for `os.open`: any of
  `O_WRONLY|O_RDWR|O_CREAT|O_TRUNC|O_APPEND`) can write, and every
  `os.mkdir`, `os.rename`, `os.remove`, `os.rmdir`, `os.chmod`, `os.symlink`,
  `os.link`, `os.truncate`, `os.utime`, `os.chown` and `os.chflags` event
  (both ends of a rename, link or symlink), and the test asserts that none
  targets a path under the target or either Git directory (a final-state
  snapshot alone cannot see a probe file that was created and deleted, and
  does not see `utime` or ownership). **The hook resolves each event's path**:
  a relative path against the process cwd, and a path given with a `dir_fd`
  (as `shutil.rmtree` reports its removals on CPython 3.12+, with a bare entry
  name) against `os.readlink(f"/proc/self/fd/{dir_fd}")`; an event whose path
  it cannot resolve **fails the test** rather than passing. **Scope, stated
  plainly:** an audit hook sees only the Manager's own process. Writes by
  the Git subprocesses (`status`/`log`, an fsmonitor, an index refresh) are not
  observed by it, and a `chmod -R a-w` run does not catch them either, because
  Git tolerates a failed optional write; for them the guarantee rests on the
  hermetic contract above (flags, environment, commands that do not write by
  contract) and on the final-state snapshots. A per-call
  `GIT_TRACE2_EVENT` record of every `run_git` invocation is kept in the
  test, so the argv set is also asserted to be only the contracted commands.

## 4. Hazard catalogue

| id | severity | trigger | says |
| --- | --- | --- | --- |
| `refused-drift` | blocked | `plan_update` raises `DriftError` | quotes the refusal and the `--force` consequence |
| `refused-collision` | blocked | `CollisionError` | quotes it |
| `v2.4.0-001` | warning | an active item and `plan.writes`/`plan.removals` (merges included) intersect, **at the implementation stage** (a `process` item at implementing-or-later only, including `AMENDING_PLAN`), the item's declared implementation-stage protected paths and prefixes (heuristic `scripts/` + `.claude/commands/` only when its declarations file is missing, and the finding says so), **or at the plan stage** (every active item of **either type** with an artifacts file, plan phases included) its `plan_stage` protected **paths** (exact; the plan stage has no prefixes) (3.2); each path is shown with the stage it is protected at | names the item, phase, stage, the count and first paths; at the implementation stage the rewritten files enter the item's implementation diff and review content, and from `AWAITING_TECHNICAL_APPROVAL` on its technical approval goes stale; at the plan stage the plan-stage `review_content_id` changes: a bound plan bundle drifts (`ReviewedContentDriftError`) and an implementing item's `plan_approval` goes stale; finish or park the item first, or update before it starts |
| `v2.4.0-001-old` | warning | target < 2.6.0, and an active `process` item at implementing-or-later: committing `.workflow-manager/installation.json` then makes `implementing_entry_reachable` raise for declarations that predate the 2.4.0 fix | the repair reaches earlier items only through a release >= 2.6.0; update to it, or expect that refusal (rare; the `NEW_WORK_ONLY` data already carries the fact) |
| `legacy-active` | warning | any active legacy item (including dormant `LEGACY_READY`) | names it; the update does not retire or migrate it; `/retire-legacy-work-item` is offered only for an eligible dormant entry (3.5) and only when the target is 2.9.0 or later |
| `gates-change` | warning | installed < 2.8.0 <= target and no `GATE_POLICY.json` | gates become automatic for existing items too, per governing version and gate (3.3); the exact file to commit first, as the docs print it |
| `downgrade` | warning | target < installed | unsupported; lists each boundary crossed with the signals found in the current state, and the `CLAUDE.md` posture sentence |
| `worktrees` | warning | more than one Git worktree and installed < 2.6.0 <= target | merge the update into every linked worktree's branch before driving amendments from several |
| `dirty-tree` | warning | Git reports uncommitted changes | commit or set aside edits first so the update is the only diff |
| `new-work-only` | note | each `NEW_WORK_ONLY` entry for a release in (installed, target] | what does not reach existing work |
| `incomplete-inspection` | warning | any inspection that could not finish (3.2): missing/malformed/unsupported state, an artifacts file or stage key missing, unknown governing version or phase, item shape, failed Git call a detector needed | names what could not be read and why; the report is not a clean bill of health; advisory for `update` (N2) |
| `unclassified-paths` | warning | an active item whose declarations leave a path of `plan.writes`/`plan.removals` unclassified **at the plan stage** (every item with an artifacts file) or **at the implementation stage** (implementing-or-later only) (3.2), excluding the ambient installation-record exclusion; each path is shown with the stage it fails at | the Workflow would refuse with `UnclassifiedPathError` at that stage (plan-bundle generation, `implementing_entry_reachable`, or implementation review); the item's declarations need review or amendment |
| `not-verified` | note | the installed release could not be resolved (offline, unpinned) | drift was not checked; why |

## 5. Tests

New files, each a `unittest.TestCase` module under `tests/` (auto-discovered):

- `tests/test_update_plan.py` -- N1/parity: for each existing update
  scenario (built with `fixture.py`'s repositories), `plan_update` then
  `apply_update` equals `update`, `plan.changes` equals what `update`
  returned, and a refusal raises identically; `plan_update` writes nothing
  (tree snapshot); `--dry-run` through the CLI prints the lines the real
  `update` then prints (line for line on `plan.changes` with the `would `
  prefix; the forced-dry-run annotations checked separately); the existing
  `_write`-counting interrupt test still counts `apply_update`'s writes
  (`total > 1`).
- `tests/test_read_only.py` -- containment and hermeticity, one test per
  reproduced case:
  - **Temporary-directory discovery.** In a fresh process, `TMPDIR=<repo>` and
    `TMPDIR=<repo>/.git` (also `TEMP`/`TMP`, and via a symlink) are each
    refused before anything is written, and the audit hook (3.6) records **no
    create, write, rename or remove event** under the target, not merely an
    unchanged final tree; `tempfile.gettempdir` and `mkdtemp` without `dir=`
    are patched to fail the test if called by the read-only path.
  - **Cache leaf symlink.** An external cache whose `<version>.lock` is a
    symlink to `<repo>/new-file` (and another to `<repo>/.git/x`), and a
    version directory that is such a symlink: refused or failed with `ELOOP`
    before any write, and `new-file` never exists. A cache root inside the
    target, inside `.git`, inside a linked worktree's common Git directory, and
    via a symlink, through the option and the environment, is refused before
    any lock or directory exists.
  - **Partial clone.** A repository with `extensions.partialClone` and a
    promisor remote whose `uploadpack` is a script that records any
    invocation: no fetch helper runs, no `log`/`status` argv is attempted
    (recorded through `run_git`), the `incomplete-inspection` finding is
    present, and the result is identical when `run_git`'s environment omits
    `GIT_NO_LAZY_FETCH` (an older Git), proving the outcome does not depend
    on it. A detection failure behaves the same.
  - **Ordinary repository, partial-clone probes.** A fresh non-partial
    repository where both config probes exit 1: `status` and `log` **are** run
    (recorded through `run_git`), no `incomplete-inspection` is produced, and a
    clean tree gives `doctor` exit 0 (dirty-tree and both trailer findings
    reported when present). A probe whose exit is neither 0 nor 1, and one
    that times out (fake `git` earlier on `PATH`), skip the object reads and
    produce the finding.
  - **Audit-hook self-test.** A child process runs an audit hook identical to
    the one used on the commands and deliberately `shutil.rmtree`s a directory
    under a scratch target, creates and removes a symlink there, opens a file
    with `os.open(..., O_CREAT)` there, and `os.utime`s a file there, with
    relative paths and `dir_fd` events; the hook flags every one, and an
    event whose path it cannot resolve fails. This proves the observation sees
    what it claims to exclude.
  - **Relative `--git-common-dir`.** A linked worktree, and the main worktree
    run from another cwd, where `rev-parse` prints a relative path: it is
    resolved against the target and the containment check still refuses a
    cache root inside the common Git directory.
  - **`/tmp/<repo>` accepted.** A target under the ordinary system temporary
    directory: `doctor` and `--dry-run` proceed, the snapshot parent is a
    directory outside the target, and the dry run's changes or refusal equal
    the real update's.
  - A repository with a configured `core.fsmonitor` hook (the hook never
    runs) and a linked worktree, with path/mode/byte snapshots of the work
    tree, the actual Git directory and the common Git directory unchanged.
- `tests/test_compatibility.py` -- the reader and every finding: fixtures
  with hand-written state files (the reader takes plain JSON): a `process`
  item at `IMPLEMENTING` with a plan touching `scripts/`, the same at a plan
  phase (no finding), a governing-`1` item, `LEGACY_READY`, the retirement
  trailer and the `Workflow-Activation: 2.2` trailer (real commits in a
  throwaway repository), the `plan-inputs/` path-present detector, each
  downgrade boundary with and without its signal (and the undetectable 2.7.0
  line present), unknown phase, and each incomplete-inspection cause (malformed or missing
  state, unsupported `schema_version`, unknown governing version, invalid
  item shape, failed Git call) producing the finding and a nonzero `doctor`
  exit, yet leaving `update`/`--dry-run` unrefused; the canonical artifacts
  lookup with a null and a nonstandard `registry_path`; an update adding a
  command outside an item's declarations (`unclassified-paths`) and the
  installation record not reported; existing items of each governing version
  crossing 2.8.0 with the per-gate result matched to the 2.9.0 `gate_mode`;
  retirement advice withheld for a non-`LEGACY_READY`, active-pointer or
  unfinished-children item; a `process` item at
  `AMENDING_PLAN` yields `v2.4.0-001`; every phase in 2.9.0's `KNOWN_PHASES`
  is classified plan-phase, implementing-or-later, or one of the two named non-active exemptions (`MILESTONE_COMPLETE`, `LEGACY_READY`); an item whose artifacts
  file protects a managed `docs/ai-workflow/` path (found by the declared
  classification), one whose exclusion must not override an earlier
  protection, and one whose artifacts file is missing (heuristic fallback,
  stated in the finding); plan-stage classification at both stages: a plan-phase item with an unclassified added path, an implementing item whose plan stage leaves a path unclassified while its implementation stage classifies it, an item that plan-stage-protects a managed path (bound bundle or approval named), and an artifacts file without `plan_stage` yielding `incomplete-inspection`; a merge-only update (only `CLAUDE.md` changes) triggering `v2.4.0-001` for an item that protects `CLAUDE.md`; a commit quoting `Workflow-Legacy-Retirement` in its body without being a trailer not counting, and a trailer on a ref other than `HEAD` not counting; both classifier copies compared with the 2.9.0 package's over a table of paths, a stray `plan_stage.protected_prefixes` key leaving classification unchanged, a `product` item whose plan stage protects a managed path (named under `v2.4.0-001`) and no implementation-stage finding for it, and the activation grep's argv pinned (single backslash) with the body-line limit: a line starting with the trailer text outside the trailer block matches and is worded as approximate; containment with a linked worktree where `rev-parse` fails (refused, exit 2); the target < 2.6.0 `v2.4.0-001-old` warning; the
  three version labels never share a line; the tables cover every pinned
  version and name only pinned ones.
- `tests/test_doctor_cli.py` -- the CLI: exit codes (including `doctor` with
  the target release unresolvable -> exit 2, and with an unresolvable
  installed release -> report with `not-verified`, exit by its other
  findings), a dirty tree printing no restore line, headings, byte-snapshot
  and read-only-copy runs for `doctor` and `update --dry-run`, `--force`
  listing, a not-managed target, a corrupt record, an unresolvable release
  (`not-verified`), every printed command validated by family (Manager commands through
  `build_parser()` with the intended namespace, Git commands executed in a
  disposable repository whose path has spaces and shell metacharacters, slash
  commands against the release's command file), the restore line withheld
  when cleanliness is unknown, and the undo command run
  against a real updated throwaway repository restoring the pre-update tree.
- `tests/test_docs.py` is extended only by the header bump the docs change
  needs; `tools/check_docs.py` already parses documented commands.

`tests/test_bootstrap.py`, `tests/test_update_path.py` and the frozen matrix
run unchanged and are the refactor's regression net.

## 6. Documentation

`docs/update.md` gains a "Check before you update" step (`doctor`, then
`update --dry-run`) and the report's reading guide; `docs/troubleshooting.md`
gets "the report says blocked/warning" entries; `docs/README.md` indexes them;
`docs/ARCHITECTURE.md` gets a short "Update planning" section (the shared
path, the read-only guarantee, what the cache write is); `docs/RELEASING.md`'s
"adding a pin" list and `CLAUDE.md`'s "Adding a Workflow release" gain the
step "extend the three tables in `compatibility.py` (a test fails until you
do)"; `docs/ROADMAP.md` marks item 4 done at acceptance; the `cli.py`
docstring lists the new commands. Header "Last checked with" lines move to
Manager 1.6.0 where the pages are rewritten (`test_docs.py` pins the header).

## 7. Checkpoints

<!-- registry:begin -->
| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Split update into plan_update and apply_update (UpdatePlan, pure merge planning, left_alone), behaviour unchanged, with parity tests | - | 4 | 1 |
| CP2 | compatibility.py: read-only repository reader, the three release tables, findings catalogue, report rendering and command rendering, with unit tests | CP1 | 4 | 1 |
| CP3 | CLI: workflow-manager doctor and update --dry-run, exit codes, containment and hermetic Git, read-only and printed-commands-by-family tests | CP1, CP2 | 3 | 1 |
| CP4 | Documentation (update, troubleshooting, README index, ARCHITECTURE, RELEASING and CLAUDE.md pin step, cli docstring) and the docs check | CP3 | 2 | 1 |
| CP5 | End-to-end evidence on disposable repositories (process item at IMPLEMENTING, legacy item, downgrade, undo command) and the full gate | CP3, CP4 | 3 | 1 |
<!-- registry:end -->

Notes on the table: CP1 is the only change to existing behaviour and lands
first, alone, so its green full-suite run is a clean regression baseline for
the rest. CP2 has no CLI. CP3 wires the CLI. CP4 is docs and the
pin-maintenance step. CP5 is the end-to-end evidence on disposable
repositories with a real process item driven to `IMPLEMENTING`
(`fixture.drive_synthetic_work_item_through_checkpoints`).

## 8. Open decisions

`docs/TECHNICAL_DECISIONS.md` does not exist at the base commit, so no
"Open decision" row is touched or silently finalized. Decided here, for the
reviewer to challenge:

- **D-1.** The downgrade detectors read the current state file only (plus the
  two Git facts); they never walk history. Rationale: bounded and testable;
  the report says what it did not search. Alternative (a history walk of the
  state file) rejected as slow and still incomplete.
- **D-2.** The compatibility tables live in the Manager as code, not in the
  Workflow package. Rationale: pins are the Manager's fact and the Workflow's
  published packages are immutable, so they cannot gain a field; the cost is
  one table entry per pin, enforced by a test.
- **D-3.** `doctor` defaults its target to the latest pinned release (what
  `update` would install), so a bare `doctor` answers "what would an update
  do to this repository".
- **D-4.** Exit code 1 for `doctor` warnings is a new convention for the
  tool's advisory output; it follows `status`/`verify`.

## 9. Review dispositions (round 5, manual external review of revision 4)

All four Important findings and all four optional findings are accepted; none
is rejected.

- **I1** (`tempfile.gettempdir()` probes inside the target): accepted.
  `gettempdir()` is forbidden on the read-only path; candidates are decided by
  path arithmetic in `tempfile`'s documented order and the snapshot is created
  with an explicit `dir=` (3.6, 1.1 item 1). Test: forbidden `TMPDIR` with the
  audit hook (5).
- **I2** (cache leaf symlink): accepted. Each leaf the resolver opens is
  resolved and tested, and lock leaves are opened with `O_NOFOLLOW` under a
  `read_only` flag that leaves `update` unchanged (3.6). Test: leaf symlink
  into the target and `.git` (5).
- **I3** (lazy fetch depends on the installed Git): accepted. Partial clones
  are detected from configuration and the object-touching reads are skipped,
  never attempted; `GIT_NO_LAZY_FETCH` is defence in depth only (3.2). Test:
  partial clone, with and without the variable (5).
- **I4** (reverse containment): accepted. Only a destination inside the target
  is refused; a target under the temporary directory is accepted (1.1, 3.6).
  Test: `/tmp/<repo>` (5). The real `update` is left unchanged (N1/N2) and is
  not claimed to refuse an in-target destination; parity is defined for
  destinations outside the target, which is the case reviewers' fixtures use.
- **Optional 1** (plan-stage protected prefixes): accepted; removed, with a
  test that a stray key is ignored (3.2, 4, 5).
- **Optional 2** (product items): accepted; the plan-stage branch covers both
  item types, the implementation-stage branch stays `process`-only (3.2, 4).
- **Optional 3** (anchored grep): accepted; documented as a conservative
  approximation, argv escaping pinned (3.3).
- **Optional 4** (requirements mapping): accepted; REQ-1 and REQ-6 synchronized
  (mapping file).

## 10. Review dispositions (round 6, local review of revision 5)

Both Important findings, the three substantive optional findings and the two
apparatus findings are accepted; none is rejected. I checked the premises:
`cli._git` returns `None` on any nonzero exit (`src/workflow_manager/cli.py`),
and both config probes exit 1 on a fresh `git init`.

- **I1** (partial-clone detection fails on every ordinary repository):
  accepted. `run_git` returns the exit status; exit 1 means "key absent"; any
  other nonzero exit, timeout or `OSError` is a detection failure (3.2).
  Test: ordinary repository and failing probes (5).
- **I2** (transient-write audit): accepted. (a) relative and `dir_fd` paths
  are resolved and unresolvable events fail; (b) `os.open` flags are tested
  and `os.symlink`, `os.link`, `os.truncate`, `os.utime`, `os.chown`,
  `os.chflags` are added; (c) the scope is stated: the audit covers the
  Manager process, and Git's absence of writes rests on P4 plus the
  final-state snapshots, with a `GIT_TRACE2_EVENT` argv assertion (1.2, 3.6).
  Test: audit-hook self-test (5).
- **Optional: `dir=`/`read_only` threading**: accepted; the call chain is named
  (3.6).
- **Optional: relative `rev-parse` paths**: accepted; resolved against the
  target, without `--path-format=absolute` (3.2). Test: relative
  `--git-common-dir` (5).
- **Optional: trailer attribution**: accepted; two calls, one `--grep` each
  (3.3).
- **Optional: mapping REQ-4 and the artifacts file's `src/` reason**:
  accepted; both synchronized.

## 11. Risks

- The refactor could change update behaviour: contained by N1, the unchanged
  existing tests, and the parity tests; CP1 lands alone.
- A signal table that rots as releases are pinned: contained by the
  every-pinned-version test and the pin-checklist step.
- `git` calls reading a repository mid-operation: `GIT_OPTIONAL_LOCKS=0`,
  short timeouts, failures degrade to "unknown". Every Git call goes through
  `compatibility.run_git` (hermetic flags and environment of 3.2), not
  `GIT_OPTIONAL_LOCKS=0` alone.
