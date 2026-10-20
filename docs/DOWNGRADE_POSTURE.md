# Downgrade posture (Workflow releases up to 2.12.0)

> For: anyone about to run `workflow-manager update --release-version <older>`, or changing
> `compatibility.py`'s downgrade boundaries. A release after 2.12.0 carries its own posture in its
> manifest's `manager` block (`docs/release-metadata.md`). Moved here from `CLAUDE.md`, whose
> resident rule points here.

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

`2.9.2` is a fix release (workflow#19, #20) and adds no persisted key, phase,
status or commit shape; the Orchestration Protocol stays `1.2`. It writes
nothing `2.9.1` would refuse, so `2.9.1` reads every state and history it
produces. What a downgrade loses is the fix, and the corrected command text:
with `2.9.1`, commit the stale `technical_approval` write alone before the
first fix edit, commit the checklist before the generation record, and keep
`Co-Authored-By:` out of the `Workflow-*` trailer paragraph, by hand. A
downgrade to `2.9.1` is supported on those terms.

`2.10.0` is a minor release (workflow#24) and adds no persisted key, phase,
status, value, configuration write or commit shape; the Orchestration Protocol
becomes `1.3`, additively (row `1b`, `plan_start_default_retired`, and the
advisory `default_workflow_version` verify check). It writes nothing `2.9.2`
would refuse, so `2.9.2` reads and drives every state and history it produces.
What a downgrade loses: `2.10.0` refuses to create a new work item while
`WORKFLOW_CONFIG.json` names `"2.1"` as the default, and `2.9.2` creates it
again, so a repository that wants to stay off `"2.1"` for new work keeps its
default at `"2.2"`; and `2.9.2`'s `workflow-conformance.yml`, which runs the
suites one after another and never cancels a run, comes back. A downgrade to
`2.9.2` is supported on those terms.

`2.11.0` is a minor release (workflow#23) and adds no persisted key, phase,
status, value, record, configuration write or commit shape; the Orchestration
Protocol stays `1.3`. It writes nothing `2.10.0` would refuse, so `2.10.0`
reads and drives every state and history it produces. What a downgrade loses
is the early anchor check: `2.11.0` refuses a plan revision without its
checkpoint anchors (`<!-- CPn -->`/`<!-- /CPn -->`) when it is published,
bound or turned into a plan-review bundle, and `2.10.0` again refuses an
amending plan without anchors first at plan approval, after both plan reviews,
and accepts a new plan without anchors, so its first amendment demotes every
completed checkpoint. Plans already written with anchors keep them, and
`2.10.0`'s reconciliation uses them. A downgrade to `2.10.0` is supported on
those terms.

`2.12.0` is a minor release (workflow#28) and adds no persisted key, phase,
status, value, configuration write or commit shape; the Orchestration Protocol
becomes `1.4`, additively (the `review_round` field of the `next-action`
snapshot). It adds one gitignored file, `.ai-review/<id>/CHANGES_SINCE_REVIEW.md`,
outside `bundle_id` and `review_content_id`, and one optional verdict header
line, `Review scope:`. It writes nothing `2.11.0` would refuse, so `2.11.0`
reads and drives every state and history it produces, and verifies an archive
that carries the file. What a downgrade loses: `2.11.0` ignores the header
line, neither regenerates nor deletes `CHANGES_SINCE_REVIEW.md` (delete it by
hand so a reviewer does not read a stale copy), no longer refuses a malformed
verdict by shape (a `REVISE` without a Blocking or Important finding, an
`APPROVE` listing a Blocking finding or declaring `Review scope: changes`),
and drops `review_round` (an orchestrator reading protocol `1.4` sees `1.3`
again). A downgrade to `2.11.0` is supported on those terms.
