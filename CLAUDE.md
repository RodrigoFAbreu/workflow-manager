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

Distribution and bootstrap tooling for the reusable AI development Workflow.
It is *not* RepFlow, and no RepFlow product work belongs here.

## Hard rules

- **`~/Workspace/repflow-android` is read-only.** Read it through
  `git show <commit>:<path>` against the frozen tag `workflow-v2.3.1`
  (`1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6`). Never write to it, never
  create a worktree in it, never rely on its working tree — it carries an
  unrelated in-flight branch.
- **Each `distribution/workflow/<version>/` is generated, not edited.**
  `2.3.1` is byte-identical to the frozen upstream release; a later authored
  release is byte-identical to its own recorded base-plus-overlay
  composition. Change `migration/classification.json` or `tools/migrate.py`
  and re-run `python3 tools/migrate.py`.
- **Never modify frozen Workflow semantics.** If migration surfaces a genuine
  upstream defect, write it up under `docs/defects/` and stop there. Repairing
  it is a Workflow release's job, not this repository's.
- **Never migrate live work-item state.** Active `WORKFLOW_STATE` entries,
  `.ai-review/`, approvals, registries and mappings for someone else's work
  items are not defaults. Targets get clean templates.

## Before changing anything

```bash
python3 tests/run_all.py                          # the gate: full selection, in parallel (~7min)
python3 tests/run_all.py --select test_x.py       # run what you touched -- never a gate
python3 tests/run_all.py --jobs 1                 # serial reference (~40min) -- exceptional evidence only
```

Run what you touched with `--select`; gates run `python3 tests/run_all.py`.
Every Workflow gate here (checkpoint, implementation review, acceptance)
runs the full selection. The one reduced selection that is a gate is CI's
pull-request profile (`--newest-release-only`, chosen by
`tools/ci/choose_profile.py`), and only as the required `aggregate` check;
a newest-release run is never full-suite evidence. It is a stopgap M2
removes: see `docs/ARCHITECTURE.md`'s "One reduced selection is a gate, in
one place" and "Stopgap test profile". A new top-level path or test module
needs its own rule in `tools/ci/pr_profile_paths.json`, or the suite fails.
A full-suite serial or single-shard run (`--jobs 1`, `--shards 1`, CI
`shards=1`) is exceptional evidence, not a confidence rerun. Run one only
when the approved plan or an acceptance criterion requires it, or to debug
a serial/sharded discrepancy. If an equivalent run already exists, reuse and
cite it: same `selection_digest`/`tests_digest`, its own `verdict:` the one
the gate needs, and no change since its `head` to code, tests or the runner
(for CI evidence, the verify workflow too). Docs and workflow-state commits
don't count as changes. See `docs/ARCHITECTURE.md`'s "Verification execution"
for the equivalence and staleness rules and what to record.
`--fast` survives one release as a deprecated alias for a targeted
`--select` of eight modules -- targeted selection, not a verification gate.
A run makes `distribution/`, `migration/`, `src/` and `tools/` read-only
until it ends; see `docs/ARCHITECTURE.md`'s "Verification execution".
A run fails (exit 2, `OrphanProcessError`) when a test leaves an orphaned
process behind. A test that orphans on purpose is declared, with a reason,
in `tests/parallel/resources.json`'s `orphan_sources`; see
`docs/ARCHITECTURE.md`'s "Orphaned processes".

`tools/migrate.py --check` proves each upstream-derived
`distribution/workflow/<version>/` (today, `2.3.1`) still reproduces from a
fresh extraction; it does not by itself prove no unrelated file exists
directly under `distribution/` outside every release directory. An authored
release (today, `2.4.0`, `2.5.0`, `2.5.1`, and `2.6.0`) is proved
reproducible separately, by `python3 tools/build_release.py --overlay
migration/overlays/<version> --check`, from its own base release plus its
own overlay -- `migrate.py --check` does not cover it.

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

- The migration record and its evidence: `docs/MIGRATION.md`
- The distribution/state boundary: `docs/ARCHITECTURE.md`
- How the Manager is released, and the settings commands: `docs/RELEASING.md`
- Classification ruleset: `migration/classification.json`
- Frozen tests a clean target cannot pass, with reasons:
  `migration/portability_exceptions.json`

## Adding an upstream Workflow release

Use this when the new release is a fresh upstream tag (frozen content this
repository only extracts, never authors) -- `2.3.1` is the instance.

1. Add the new tag/commit to `migration/classification.json` (or a second
   classification file if the tree shape changed).
2. Run `python3 tools/migrate.py`, then `python3 tests/run_all.py`.
3. The conformance suite must be green against the fixture, and the clean
   target's failure set must equal the documented exceptions — no more, no
   fewer.

## Adding an authored Workflow release

Use this instead when the new release's content originates in this
repository -- a base release plus a hand-written overlay, never a new
upstream tag -- `2.4.0` (the plan-amendment mechanism) is the first instance.
See `docs/ARCHITECTURE.md`'s "Authored releases" and `docs/MIGRATION.md`'s
`2.4.0` record for the full mechanics and evidence.

1. Author `migration/overlays/<version>/payload/` (new files, plus full
   replacements of every base-release payload file the release changes) and
   `migration/overlays/<version>/classification.json` (the same ruleset shape
   as `migration/classification.json`, scoped to the overlay's own delta
   files).
2. Run `python3 tools/build_release.py --overlay migration/overlays/<version>`,
   then `python3 tools/build_release.py --overlay migration/overlays/<version>
   --check` — the committed `distribution/workflow/<version>/` must reproduce
   exactly from the base release plus the overlay alone, and every replaced
   file's recorded `overlay_delta` must reproduce from the base payload plus
   the recorded diff.
3. Add the new version to `tests/support.py`'s per-release `CI_SUITES` and,
   if it needs one, `migration/portability_exceptions.json`'s `by_version`,
   then run `python3 tests/run_all.py`. The conformance suite must be green
   against the fixture, the clean target's failure set must equal the
   documented exceptions, and any obligation the release's own checkpoints
   declare (a compatibility audit against the finished overlay diff, for
   instance) must actually be discharged, not merely inferred from suite
   totals.

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
against `distribution/workflow/2.5.0/payload/scripts/workflow_state.py`'s
own `validate_post_anchor_coverage`) — wedging the item with no in-band
exit; the error's own suggested repair, "rename it via another
`/milestone-plan` round", is exactly the renaming `2.5.1` exists to avoid.
Never run `workflow_manager update --release-version <older than 2.5.1>`
against a repository that has ever requested a plan amendment (entered
`AMENDING_PLAN`) for a work item whose registry carries a letter-suffixed
checkpoint id.

`2.6.0` adds its own downgrade constraints on top of (not instead of) the
paragraphs above. It adds no new phase, governing version or
checkpoint status. The difference is that `≤2.5.1` fails **silently**
rather than wedging: CP3 and CP6 ran it mechanically against
`distribution/workflow/2.5.1/payload/scripts/` and found that `2.5.1`'s
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
