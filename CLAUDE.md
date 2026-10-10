# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

## Semi-autonomous workflow gates

Work follows the state machine in `docs/ai-workflow/MILESTONE_WORKFLOW.md`.
Claude works autonomously between gates but must stop and wait at every hard
gate that document names -- see its "Hard gates summary" for the current
count and list, which changes as the workflow evolves; do not hardcode a
count here.

Use the commands in `.claude/commands/` to drive each state. Do not skip a
gate because the diff looks small.

## Workflow documents

- Milestone state machine: `docs/ai-workflow/MILESTONE_WORKFLOW.md`
- Two-stage plan review: `docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`
- Bundle mechanics and feedback format: `docs/ai-workflow/REVIEW_PROTOCOL.md`
- Phase/command reference: `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`
- Current work-item state: `docs/ai-workflow/WORKFLOW_STATE.json` (ground
  truth -- never inferred from plan text)
- Active work item narrative: `docs/ACTIVE_MILESTONE.md`

## Git restrictions

- Commits are normally prohibited. Only commit when a workflow command
  explicitly authorizes it after verification gates pass.
- Never push, merge, rebase, force-push, or open a pull request.
- Don't touch unrelated working-tree changes.

<!--
Sections above this marker are managed by workflow-manager and are replaced
on update. Add repository-specific guidance below it; it is never touched.
-->

<!-- workflow-manager:end -->

# CLAUDE.md

Guidance for Claude Code in the **workflow-manager** repository.

## What this repository is

Installer, bootstrap and update tooling for the reusable AI development
Workflow. Workflow releases are authored, built and published as packages in
the `workflow` repository (`RodrigoFAbreu/workflow`); this repository pins
them by digest and installs them. It is *not* RepFlow, and no RepFlow
product work belongs here.

## Hard rules

- **`~/Workspace/repflow-android` is read-only.** `2.3.1`'s origin: if
  history ever needs it, read it through `git show <commit>:<path>` against
  the frozen tag `workflow-v2.3.1`
  (`1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6`). Never write to it, never
  create a worktree in it, never rely on its working tree — it carries an
  unrelated in-flight branch.
- **A published Workflow release is immutable, and so is its pin.** This
  repository never builds, edits or re-publishes a Workflow release. A pin in
  `src/workflow_manager/published_releases.json` is added only for a release
  the `workflow` repository has published, with its digests checked against
  the published assets (`docs/RELEASING.md`, "Workflow packages: adding a
  pin"), and an existing pin is never changed. `distribution/`, `migration/`,
  `tools/migrate.py` and `tools/build_release.py` are gone since M2; read
  them at `ec38979` if history needs them.
- **Never modify frozen Workflow semantics.** If testing a release surfaces a
  genuine defect, write it up under `docs/defects/` and stop there. Repairing
  it is a Workflow release's job, in the `workflow` repository, not this
  repository's.
- **Never migrate live work-item state.** Active `WORKFLOW_STATE` entries,
  `.ai-review/`, approvals, registries and mappings for someone else's work
  items are not defaults. Targets get clean templates.

## Before changing anything

```bash
python3 tests/run_all.py                          # the gate: full selection, in parallel (~5min)
python3 tests/run_all.py --select test_x.py       # run what you touched -- never a gate
python3 tests/run_all.py --jobs 1                 # serial reference (slow) -- exceptional evidence only
```

Run what you touched with `--select`; gates run `python3 tests/run_all.py`.
Every Workflow gate here (checkpoint, implementation review, acceptance)
and every CI run (pull request, `main` push, nightly) runs the same full
selection: the host tests plus the newest pinned release's frozen suites in
four fixtures. Every run first primes the release cache with every pinned
version and then runs offline; a version it cannot cache is `PrimingError`
(exit 2). The first run on a machine needs the network, or a
`WORKFLOW_MANAGER_RELEASE_SOURCE` mirror.
A full-suite serial or single-shard run (`--jobs 1`, `--shards 1`, CI
`shards=1`) is exceptional evidence, not a confidence rerun. Run one only
when the approved plan or an acceptance criterion requires it, or to debug
a serial/sharded discrepancy. If an equivalent run already exists, reuse and
cite it: same `selection_digest`/`tests_digest`, its own `verdict:` the one
the gate needs, and no change since its `head` to code, tests or the runner
(for CI evidence, the verify workflow too). Docs and workflow-state commits
don't count as changes. See `docs/ARCHITECTURE.md`'s "Verification execution"
for the equivalence and staleness rules and what to record.
A run makes `src/` and `tools/` read-only until it ends; see
`docs/ARCHITECTURE.md`'s "Verification execution".
A run fails (exit 2, `OrphanProcessError`) when a test leaves an orphaned
process behind. A test that orphans on purpose is declared, with a reason,
in `tests/parallel/resources.json`'s `orphan_sources`; see
`docs/ARCHITECTURE.md`'s "Orphaned processes".

## Branches, pull requests and releases

- **Trunk model.** `main` is protected by a ruleset
  (`.github/repository/ruleset-main.json`) and changes only through pull
  requests, merged by squash. One short-lived branch per milestone
  (`milestone/<work-item-id>`).
- **The pull-request title is the release.** It must be a Conventional
  Commit (`feat: ...`, `fix(cli): ...`, `feat!: ...`), checked by the
  required `Conventional Commit title` check, and it becomes the squash
  commit's subject. `feat` releases a minor, `fix`/`perf`/`refactor`/
  `build`/`revert` a patch, `!` a major; `docs`/`chore`/`ci`/`test`/`style`
  release nothing. Check one with `python3 tools/release/release.py
  check-title "<title>"`.
- **Never edit a version.** The Git tag `vX.Y.Z` is the only version
  authority; `pyproject.toml`'s `0.0.0.dev0` is a placeholder a test pins.
  The release workflow computes, builds, tags and publishes the Manager
  package after `main`'s full run is green. It never creates a Workflow
  release.
- **Settings are data.** `.github/repository/` holds the merge settings and
  the ruleset; the repository owner applies them with the `gh api` commands
  in `docs/RELEASING.md`. Pushing, opening or merging a pull request and
  changing settings stay the user's (see "Git restrictions" above).
- **Squash merges are safe for the installed Workflow**: no reader resolves
  a SHA a completed item records (`docs/ARCHITECTURE.md`, "Squash merges
  and the installed Workflow"). Re-check that before installing a Workflow
  release that adds a history reader.

## Where things are

- The release/state boundary (packages, pins, source, cache):
  `docs/ARCHITECTURE.md`
- How the Manager is released, how a Workflow release is pinned, the
  settings commands and M2's cutover (K1-K5): `docs/RELEASING.md`
- The migration and packaging record and its evidence: `docs/MIGRATION.md`
- The pins: `src/workflow_manager/published_releases.json`
- Frozen suite counts per pinned version: `tests/support.py`'s `CI_SUITES`
- Frozen tests a clean target cannot pass, with reasons:
  `tests/portability_exceptions.json`

## Adding a Workflow release

A Workflow release is authored, built and published in the `workflow`
repository, never here. This repository adds its pin in one `feat:` pull
request (`docs/RELEASING.md`, "Workflow packages: adding a pin"):

1. Download the published assets and check them (`sha256sum -c
   SHA256SUMS`, `workflow-manager package verify <archive> --sha256 <digest>`).
2. Add the pin (`archive`, `sha256`, `manifest_sha256`) to
   `src/workflow_manager/published_releases.json`.
3. Add the version's frozen suite counts to `tests/support.py`'s
   `CI_SUITES` and its entry, possibly empty, to
   `tests/portability_exceptions.json`'s `by_version`, extend the three
   release tables in `src/workflow_manager/compatibility.py`
   (`DOWNGRADE_BOUNDARIES`, `NEW_WORK_ONLY`, `GATE_DEFAULT_CHANGES`; a test
   fails until you do), then run `python3 tests/run_all.py`. The matrix moves to the new release and the `updated`
   fixture updates the previous one to it. The conformance suite must be
   green against the fixture, and the clean target's failure set must equal
   the documented exceptions — no more, no fewer.

The first five releases pinned (`2.3.1` to `2.6.0`) were extracted (`2.3.1`)
or authored as a base plus an overlay (`2.4.0` to `2.6.0`) in this repository
before M2; `2.7.0` and later are built and published by the `workflow`
repository;
`docs/MIGRATION.md` records each, and `docs/ARCHITECTURE.md`'s "Authored
releases (history)" the mechanism. The downgrade posture below still governs
every one of them.

**Downgrade posture.** Once a repository has run `workflow_manager update` to
an authored release that introduces vocabulary an older release's
`workflow_state.py` does not have (`2.4.0`'s `NEEDS_REVALIDATION` checkpoint
status and `SUPERSEDED` plan-approval status, for instance), downgrading it
back to that older release is **unsupported** — not merely unproven, actively
broken: any already-committed `WORKFLOW_STATE.json` state that ever recorded
one of those values reads back as permanently `"undecidable"` under the older
release's own narrower vocabulary (git history does not change on downgrade),
and checkpoint resume for that work item wedges with no in-band escape short
of an explicit, evidence-bound override
(`authorize_identity_reference_gap`). Never run `workflow_manager update
--release-version <older>` against a repository that has ever requested a
plan amendment, or has any checkpoint that ever held `NEEDS_REVALIDATION`, or
a plan approval that ever held `SUPERSEDED`.

`2.5.0` adds its own vocabulary to that same list, and the posture is
identical — same reasoning, one release later. Never run `workflow_manager
update --release-version <older than 2.5.0>` against a repository that has
activated `"2.2"` (`WORKFLOW_CONFIG.json`'s `default_workflow_version`, plus
the `Workflow-Activation: 2.2` trailer) or that has committed any work item
which has ever held one of:

- `governing_workflow_version: "2.2"` on a `work_items[...]` entry — the
  field every `"2.2"`-only branch dispatches on, so an older release reads
  the item as an unknown governing version;
- `phase: "AWAITING_LOCAL_IMPLEMENTATION_REVIEW"` or
  `phase: "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW"` — the two
  persisted phases `2.5.0` adds, absent from an older release's
  `KNOWN_PHASES`;
- an `implementation_review_stages` ledger on a `work_items[...]` entry —
  `2.5.0`'s implementation-stage counterpart of `plan_review_stages`, which
  an older release's validators neither normalize nor admit into their
  committed-field sets.

The activation trailer itself reads back differently too, and this one is
silent. `2.5.0`'s activation-event model is version-aware: it resolves an
activation trailer's value directly and a rollback trailer's own
destination version (`Workflow-Rollback: 2.2` → `"2.1"`); an activation
event reports *activated* unconditionally, for every trailer value
including `"1"`, while a rollback event reports *activated* whenever its
resolved destination is not `"1"` — so a repository that activated `"2.2"`
and then rolled it back is still, correctly, an activated `"2.1"`
repository. Every pre-`2.5.0` `is_activated` is
version-blind: it reads any rollback event as a return to `"1"` and answers
*not activated* on that same, unchangeable history. A downgrade therefore
re-answers the activation question wrongly, with no error to notice.
(`2.5.0` itself fails closed in the one case it cannot resolve — a
`Workflow-Rollback` trailer whose value falls outside its declared
predecessor mapping reports *activated*, never a silent fall-through to
not-activated.)

`2.5.1` adds its own downgrade constraint on top of (not instead of) the
two paragraphs above, and it is narrower than either — no new persisted
phase, status or ledger key, only a persisted *registry-content shape*
that only `2.5.1` accepts. `2.5.1` widens the plan-amendment
anchor-compatible checkpoint-id grammar from `CP<digits>` to
`CP<digits>[A-Z]?`, so `request_plan_amendment`'s shape precondition now
admits a letter-suffixed id (`CP4B`, `CP6B`, ...) that `≤2.5.0` refuses
outright — only `2.5.1` can move a work item carrying such an id into
`AMENDING_PLAN`. If that repository is then downgraded to
`≤2.5.0`, the item's only exit from `AMENDING_PLAN` (`/approve-review
plan` → `apply_plan_approval` → `validate_post_anchor_coverage`) calls
into the older release's own narrower grammar, which still raises
`AmendmentCheckpointIdShapeError` for that same id (reproduced directly
against the published `2.5.0` package's
`payload/scripts/workflow_state.py`'s own `validate_post_anchor_coverage`) — wedging the item with no in-band
exit; the error's own suggested repair, "rename it via another
`/milestone-plan` round", is exactly the renaming `2.5.1` exists to avoid.
Never run `workflow_manager update --release-version <older than 2.5.1>`
against a repository that has ever requested a plan amendment (entered
`AMENDING_PLAN`) for a work item whose registry carries a letter-suffixed
checkpoint id.

`2.6.0` adds its own downgrade constraints on top of (not instead of) the
paragraphs above. It adds no new phase, governing version or
checkpoint status. The difference is that `≤2.5.1` fails **silently**
rather than wedging: CP3 and CP6 ran it mechanically against the published
`2.5.1` package's `payload/scripts/` and found that `2.5.1`'s
`validate_state` has no work-item or `amendment_history` key allowlist. So
every new persisted key below is *ignored, not rejected*, and a downgraded
repository keeps running with none of `2.6.0`'s guarantees and no error to
notice. Never run `workflow_manager update --release-version <older than
2.6.0>` against a repository that has:

- created any work item under `2.6.0`. Its `feedback_layout: "scoped"`
  stamp is ignored, so older commands resolve that item's feedback by the
  legacy scoped-else-flat rule;
- ever written a `plan_review_binding` record (bound a plan bundle under
  `2.6.0`'s phase semantics). Ignoring it silently re-admits
  already-reviewed content to review;
- relied on `.ai-review/<id>/plan-inputs/` for a plan-stage round. Older
  generators read author files from `current/` only, so they stub them or
  reuse the previous round's copies and fail their own closing checks.
  This one is loud, but still unsupported;
- ever written an amendment witness under the common git dir
  (`<token>.amendment.json`, including a `NONE` sentinel or a `RESOLVING`
  reservation). Older releases ignore it, which silently reopens
  `v2.4.0-002` and lets an older release resolve a reserved amendment a
  second time;
- ever resolved an amendment under `2.6.0`. The resolved entry's
  `resolved_review_content_id` is ignored the same way.

**Mixed-release worktrees are unsupported too.** `v2.4.0-002`'s
cross-worktree mutual exclusion is guaranteed only once every registered
worktree's branch has merged the `2.6.0` update. Until then, `2.5.1`
processes in the lagging worktrees neither take the repository-global
lifecycle lock nor read the amendment witness. `2.6.0` narrows the window
(a lag probe on every acquisition, no `NONE` sentinel while any worktree
lags, and a scan of lagging worktrees' states that refuses on an
unrecorded unresolved amendment) but cannot close it. The residual is
stated verbatim in
`docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`'s
`2.6.0` disposition. After updating to `2.6.0`, merge the update into every
branch checked out in a linked worktree before driving checkpoints or
amendments from more than one of them.

`2.7.0` adds one persisted work-item key, `consumed_plan_review_content_ids`
(`v2.6.0-001`'s durable consumed history), migrated at read time. `2.6.0`'s
`validate_state` accepts state that carries it (checked in W1's functional
review) but ignores it, so a downgrade fails **silently**: the guarantee that
consumed plan content never re-binds shrinks back to `2.6.0`'s most recent
consumption, with no error to notice. Never run `workflow_manager update
--release-version <older than 2.7.0>` against a repository that has driven
any work item under `2.7.0`, or that an orchestrator drives through the
Orchestration Protocol, which `2.6.0` does not have.

`2.8.0` changes the default rather than only adding vocabulary: with no
committed `GATE_POLICY.json`, its gates are satisfied automatically by their
evidence (human approval is off by default; `{"schema_version": 1,
"human_approval": true}` restores the `2.7.0` gates). Updating a repository
to `2.8.0` therefore changes how it is driven; decide its policy before the
update, not after. Downgrading is constrained by what `2.7.0` reads (`2.8.0`'s
published `ORCHESTRATION_PROTOCOL.md`, "Downgrade"): `2.7.0` refuses a state
that carries the approval basis `POLICY_SATISFIED`, loudly, but accepts the
other keys `2.8.0` adds (`gate_evidence`, `reopenings`,
`acceptance_satisfaction`, the ledger audit keys, `gate_policy_adoption`,
`gate_policy_floor`) **silently, without acting on them**. Because the
automatic default writes those in ordinary operation, never run
`workflow_manager update --release-version <older than 2.8.0>` against a
repository that has written any of them: any automatic satisfaction, ingested
pull-request fact or functional evidence, reopening, policy adoption or
recorded floor.

`2.9.0` adds no new persisted key, phase or status: every state it writes is
one `2.8.0` already reads as legal (its published plan, `D-Downgrade`). What a
downgrade loses is behavior. `/retire-legacy-work-item` closes a dormant legacy
item as `MILESTONE_COMPLETE`, and only `2.9.0` keeps it closed: `2.8.0` and
earlier have no retired-item guard, so a red pull-request fact reported for a
retired item can reopen it (row 38d, `/apply-pr-review`) to
`AWAITING_FUNCTIONAL_REVIEW`, silently. A downgraded repository also meets
`v2.6.0-003` again for a new governing-`1` implementation entry, and loses
`/resume-implementation`. The `"2.2"` default reaches only new installations;
an update or downgrade never touches an existing `WORKFLOW_CONFIG.json`. Never
run `workflow_manager update --release-version <older than 2.9.0>` against a
repository that has retired a legacy work item, unless no pull-request fact is
ever reported for that item again.

`2.9.1` is a fix release (workflow#13) and adds no persisted key, phase, status
or commit shape: it writes nothing `2.9.0` would refuse, so `2.9.0` reads every
state and history it produces. What a downgrade loses is the fix: `2.9.0`'s
review commands leave a `REVISE` write uncommitted, so the post-fix
generation-record commit is refused (`OPUS-R101-001`) unless the state file is
committed alone by hand before the first fix commit. A downgrade to `2.9.0` is
supported on those terms.
