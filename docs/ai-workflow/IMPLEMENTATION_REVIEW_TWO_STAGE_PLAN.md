# Workflow 2.5.0: Implementation Review, Review Scalability, and Post-v2.3.1 Remediation (Revision 33)

`work_item_id: implementation-review-two-stage` -- `governing_workflow_version: "2.1"`

**Scope correction at revision 3 (user-directed, not a review finding).** This
plan's `work_item_id` and `plan_path` are retained unchanged from revisions 1
and 2 -- renaming either is a mechanical, unrequested change to
fingerprinting/bundle machinery keyed by `work_item_id`, and no reviewer
finding or user instruction asked for it. What changes at revision 3 is the
milestone's own scope: revision 2 (and its title, "Implementation-Review
Two-Stage Protocol") was written from an accidentally narrower reading of
Workflow `2.5.0`'s objective. The user has now supplied the authoritative
tree:

```
Workflow 2.5.0
├─ implementation-review improvements
│  └─ local + manual external review bound to the same implementation identity
│
├─ review scalability / convergence improvements
│  ├─ normative current state separated from immutable history
│  ├─ canonical/generated review data
│  ├─ less duplicated self-audit bookkeeping
│  └─ convergence/circuit-breaker improvements
│
└─ remaining post-v2.3.1 correctness/ergonomics work
   → release
   → upgrade Controller
```

This work item is the vehicle for all three branches (it already carried
"Deliverable release: Workflow `2.5.0`" at the top of revisions 1 and 2, even
though its own body only ever designed the first branch). Revision 3 adds
design decisions and checkpoints for the second and third branches (§2.4-§2.7,
new checkpoints in §3) alongside the first branch's own local-review fixes
(§2.1's B1(a)/B1(b) resolution below). The two roadmap leaves "→ release" and
"→ upgrade Controller" are named for context only: "→ release" is this
milestone's own CP-numbered release-authoring checkpoint (cutting
`distribution/workflow/2.5.0/`, already in scope); "→ upgrade Controller" is
explicitly **not** in scope -- the Controller (`~/Workspace/repflow-android`'s
eventual successor tooling) is named in the roadmap only as a future consumer
of this release, never as work this milestone performs. **§2.2's "Reconciled
explicitly against the Controller rollout" paragraph, added at revision 15
(`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I1), states the concrete
consequence of that boundary for `~/Workspace/workflow-controller`'s own
already-existing, `"2.1"`-governed work item once that repository updates
to `2.5.0`.** Per the user's own
constraints, this remains Workflow tooling/process scope: no RepFlow product
work, no Controller development, and no broad human-documentation/changelog
redesign beyond what the review-scalability branch's own outcomes require.

**Deliverable release:** Workflow `2.5.0`
**Governing workflow version:** `2.1` (this work item's own governing
version — unchanged; the capability it builds is gated behind a *new*
`governing_workflow_version: "2.2"` for future work items, see below)
**Base commit:** `38114204a4eca46930b0a6fb7e7a1cc4d4810798` (the
`plan-amendment-mechanism` milestone's own completion commit)
**Deliverable:** a new authored Workflow release, `2.5.0`, built as
`distribution/workflow/2.4.0/` (base, unchanged) plus
`migration/overlays/2.5.0/` (this milestone's overlay), per this
repository's `CLAUDE.md` "Adding an authored Workflow release" process.

## 1. Goal

Frozen Workflow's implementation-review gate is a single stage:
`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`. The optional local reviewer
command added by `workflow-v2-3-followups` (`/review-implementation`) can
already *write* the authoritative `REVIEW_FEEDBACK.md` for that stage once
its own guards pass — meaning a single Claude-only pass, with no human or
external model ever involved, is today sufficient by itself to reach
`/approve-review implementation`'s `EXTERNAL_APPROVE` basis. This is
exactly the gap round 11 of the plan-review protocol closed for the *plan*
stage (`D-Plan-Review-Stages`, `docs/ai-workflow/WORKFLOW_V2_PLAN.md`):
"a plan cannot reach `AWAITING_PLAN_APPROVAL` on the strength of a single
reviewer having seen the current content." The implementation stage never
received the equivalent hardening.

This milestone mirrors that already-shipped, already-proven two-stage
local-then-manual-external design onto the implementation-review gate
(§2.1-§2.3), and — **widened at revision 3** to the roadmap's other two
branches — makes bounded, concrete improvements to review scalability and
convergence (§2.4-§2.6) and reconsiders this repository's own remaining
post-v2.3.1 correctness/ergonomics backlog (§2.7). None of the three
branches is a license for a broader redesign: §2.4-§2.6 stay inside review
apparatus/process/tooling (never a general human-documentation or
changelog redesign), and §2.7 fixes what is tractable within this
milestone's own overlay mechanics rather than reopening closed,
heavily-reviewed concurrency engineering.

**Revision-3 scope correction, superseding revision 2's blanket
exclusion**: revision 2 (and revision 1 before it) placed the four deferred
defects this repository already carries
(`docs/defects/v2.3.1-001-host-history-coupled-tests.md`,
`docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`,
`docs/defects/v2.4.0-001-workflow-manager-installation-record-unclassified-at-plan-stage.md`,
`docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`)
entirely out of scope, and old §8 stated that exclusion as a standing
confirmation every reviewer round should re-check stayed true. That
exclusion was written from the same accidentally-narrow milestone reading
§1 above now corrects, per the user's explicit instruction not to preserve
it merely because an earlier revision wrote it down. §2.7 below reconsiders
each of the four against 2.5.0's own "remaining post-v2.3.1
correctness/ergonomics work" branch; §8 is rewritten from a confirmation of
non-engagement into this milestone's actual, checkpoint-assigned
disposition of each one. (Revision 2, `LOCAL_MODEL_PLAN_REVIEW` round 1,
finding I3, remains correctly folded into that disposition: revision 1
undercounted this repository's own `docs/defects/` log by one — `v2.3.1-001`
is also "documented, not repaired," not merely the three records revision 1
named.)

## 2. Design decisions

### 2.1 D-Implementation-Review-Stages — two-stage local-then-manual-external implementation review

Directly mirrors `docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s
`D-Plan-Review-Stages`, substituting the implementation-stage identity
(`workflow_state.approval_review_content_id(..., stage="implementation",
...)`) for the plan-stage one throughout. **Scoped entirely to a new
`governing_workflow_version: "2.2"`** — see §2.2 for why a version bump is
needed here (unlike `D-Plan-Amendment-*`, which needed none) and why it is
a new value rather than a retroactive change to `"2.1"`. A `"1"`/`"2.1"`
item's implementation-review flow is **byte-for-byte unchanged**: this
section describes capability future `"2.2"`-governed work items get, not a
retroactive requirement on this one (this work item is itself `"2.1"`,
exactly as `plan-amendment-mechanism` was when it built `2.4.0`'s own new
capability for others).

**Two new phases, inserted between `APPLYING_REVIEW_FEEDBACK`/
`SELF_REVIEWING_IMPLEMENTATION` and the existing terminal
`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`** (added to `KNOWN_PHASES`):

- **`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`**
  - **Entry**: for a `"2.2"` item only — `SELF_REVIEWING_IMPLEMENTATION`'s
    exit (first round, `record_bundle_generation(stage="implementation")`)
    or `APPLYING_REVIEW_FEEDBACK`'s (or, for a `"2.2"` item's
    functional-review bounded fix, `AWAITING_FUNCTIONAL_REVIEW`'s)
    post-fix exit (later rounds, `record_bundle_generation(stage="post-fix")`).
    **Corrected at revision 4 (`LOCAL_MODEL_PLAN_REVIEW` round 3, finding
    I1)**: both entries are the same generation-record-commit mechanism,
    resolved through `bundle_generation_target_phase(stage,
    governing_workflow_version)` (§2.1's B1(a) resolution below); there is
    no separate `transition_to_awaiting_local_implementation_review`
    writer — `record_bundle_generation`'s own resolver is the sole writer
    for both entries, since it already covers the post-fix exit and a
    second writer performing the identical transition would either race it
    or duplicate it for no covered path. A `"1"`/`"2.1"` item never enters
    this phase; both exits target `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`
    directly, unchanged.
  - **Allowed actions**: run `/review-implementation` (full contract
    below).
  - **Artifacts**: `REVIEW_FEEDBACK.md` (role:
    `LOCAL_MODEL_IMPLEMENTATION_REVIEW`); for an `APPROVE` verdict only, a
    new `implementation_review_stages` ledger entry.
  - **Exit, verdict-specific**:
    - `APPROVE`: records the completed `LOCAL_MODEL_IMPLEMENTATION_REVIEW`
      stage (`bundle_id`, `verdict: APPROVE`, round, `completed_at`)
      against the current implementation-stage `review_content_id`;
      transitions to `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`.
    - `REVISE`: no ledger entry; transitions directly to
      `APPLYING_REVIEW_FEEDBACK` (mirroring `record_local_plan_review`'s
      `REVISE` branch, which writes `REVISING_PLAN` directly — the
      implementation-side editing state's name is `APPLYING_REVIEW_FEEDBACK`,
      not `REVISING_PLAN`, but the same "the review command itself performs
      the phase write" mechanism applies).
    - `BLOCK`: no ledger write, no transition — stays at
      `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`.
  - **Stop for user/reviewer?** Yes — same "stop, do not auto-continue"
    pattern the plan-side stage uses.

- **`AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`**
  - **Entry**: the ledger records a `LOCAL_MODEL_IMPLEMENTATION_REVIEW`
    stage completed with `verdict: APPROVE` against the *current*
    implementation-stage `review_content_id`.
  - **Allowed actions**: the user uploads the bundle to a manual external
    reviewer and pastes its feedback into `REVIEW_FEEDBACK.md` (role:
    `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`); runs
    `/record-manual-implementation-review` (new command, full contract
    below) to ingest it.
  - **Artifacts**: `REVIEW_FEEDBACK.md` (role:
    `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`); for an `APPROVE` verdict
    only, the ledger's second stage entry.
  - **Exit, verdict-specific**:
    - `APPROVE`: records the completed `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`
      stage (including the feedback's own `bundle_id` verbatim) against the
      current `review_content_id`; transitions to
      `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` — **the existing phase
      name, reused as the terminal "ready for approval" phase**, exactly
      as `AWAITING_PLAN_APPROVAL` kept its own pre-existing name across
      `D-Plan-Review-Stages`. See §2.3 for why this reuse is the right
      call rather than a fresh name.
    - `REVISE`: no ledger write; transitions directly to
      `APPLYING_REVIEW_FEEDBACK`.
    - `BLOCK`: no ledger write, no transition — stays at
      `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`.
  - **Stop for user/reviewer?** Yes — hard gate, identical in kind to
    today's single `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`.

**Verdict/state transition table** (mirrors
`D-Plan-Review-Stages`'s table exactly, substituted for the implementation
stage):

| Current state | Verdict | Writer | Next state/action | Validation preconditions |
|---|---|---|---|---|
| `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` | `APPROVE` | `/review-implementation` | record local stage → `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` | item is `"2.2"`; `phase == AWAITING_LOCAL_IMPLEMENTATION_REVIEW`; recomputed `bundle_id`/`review_content_id` match `MANIFEST.md`/`REVIEW_REQUEST.md` |
| `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` | `REVISE` | `/review-implementation` | write `REVIEW_FEEDBACK.md`, no ledger write → `APPLYING_REVIEW_FEEDBACK` | same as above |
| `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` | `BLOCK` | `/review-implementation` | no ledger write, no transition | same as above; explicit user resolution required |
| `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` | `APPROVE` | `/record-manual-implementation-review` | record manual stage → `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` | item is `"2.2"`; `phase == AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`; a current local `APPROVE` recorded for the same `review_content_id`; feedback role is `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`; `review_content_id` match is **hard**; `bundle_id` match is **advisory only**; no duplicate ingestion |
| `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` | `REVISE` | `/record-manual-implementation-review` | no ledger write → `APPLYING_REVIEW_FEEDBACK` | same as above |
| `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` | `BLOCK` | `/record-manual-implementation-review` | no ledger write, no transition | same as above; explicit user resolution required |

**Durable stage ledger** — new per-work-item field:
`implementation_review_stages: {review_content_id,
LOCAL_MODEL_IMPLEMENTATION_REVIEW: {bundle_id, verdict, round,
completed_at} | null, MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW: {bundle_id,
verdict, round, completed_at} | null}`. Same current-content-gate
semantics as `plan_review_stages`: valid only while `review_content_id`
equals the freshly recomputed current implementation-stage value; any
protected implementation-stage content change clears both stages by
construction (recomputation, never an explicit clear step).

**`technical_approval_gate_reachable`, widened**: for a `"2.2"` item, its
entry condition gains exactly the ledger check
`plan_approval_gate_reachable` already applies for `"2.1"` plan items —
both `LOCAL_MODEL_IMPLEMENTATION_REVIEW` and
`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` must be recorded `APPROVE` against
the current implementation-stage `review_content_id`. A `"1"`/`"2.1"`
item's condition is exactly today's shared rule, unchanged.

**`/apply-implementation-review`'s exit, revised for `"2.2"` only**: the
`"1"`/`"2.1"` branch (today's behavior, including this work item's own
implementation-review rounds — this work item is `"2.1"`) is byte-for-byte
untouched: its step 0 still calls `enter_applying_review_feedback`
(refusing outside `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`), and step 7
still stays effectively at `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` after
regenerating the post-fix bundle. For a `"2.2"` item: no
`enter_applying_review_feedback` call is made at all — the command finds
`phase` already at `APPLYING_REVIEW_FEEDBACK`, written directly by
`/review-implementation`'s or `/record-manual-implementation-review`'s own
`REVISE` verdict (exactly the mechanism `/apply-plan-review` already uses;
`/apply-plan-review` itself has no "enter `REVISING_PLAN`" call for the
same reason). Step 7's post-fix regeneration
(`record_bundle_generation(stage="post-fix")`) reaches
`AWAITING_LOCAL_IMPLEMENTATION_REVIEW` through that function's own
version-dependent `bundle_generation_target_phase` resolver (§2.1's
B1(a) resolution below) instead of staying at
`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`. No path re-enters
manual-external review without a fresh local pass first — identical in
kind to the plan side's own rule.

**Corrected at revision 4 (`LOCAL_MODEL_PLAN_REVIEW` round 3, finding
I1)**: revision 3 additionally proposed a new
`transition_to_awaiting_local_implementation_review` writer for this same
transition, "mirroring `transition_to_awaiting_local_plan_review`." The
mirror does not hold here: the plan side needs its own dedicated writer
because `/apply-plan-review`'s post-fix regeneration has no
generation-record commit at all to piggyback on (divergence 4, below), so
something has to write the phase directly. The implementation side's
post-fix regeneration *is* `record_bundle_generation(stage="post-fix")`,
which already performs the transition via the resolver — a second writer
for the identical transition covers no path the first does not already
cover, and risks becoming a second, silently-inconsistent place the target
phase is computed. `transition_to_awaiting_local_implementation_review` is
therefore dropped from this design entirely; `record_bundle_generation`'s
own resolver is the sole writer for both of `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`'s
entries (§2.1's phase description above, corrected the same way).

**Also corrected at revision 4 (finding I2)**: `record_bundle_generation`'s
`"post-fix"` legal source phases are `{APPLYING_REVIEW_FEEDBACK,
AWAITING_FUNCTIONAL_REVIEW}` — the second is `/apply-functional-review`'s
own bounded-fix branch (entered only when `technical_approval.status ==
"STALE"`), not a path this section's revision-3 text discussed. For a
`"2.2"` item, that branch's own post-fix regeneration resolves to
`AWAITING_LOCAL_IMPLEMENTATION_REVIEW` through the identical resolver, with
no special case — this is a deliberate consequence of this design's own
rule, not an oversight: **a `"2.2"` item's functional-review bounded fix
re-enters both implementation-review stages (local, then manual-external)
before `/approve-review implementation` is reachable again**, exactly the
same "no path re-enters manual-external review without a fresh local pass
first" guarantee stated above, applied to the one entry point that is not
itself part of the implementation-review REVISE loop. `.claude/commands/milestone-implement.md`
(the command that performs `record_bundle_generation(stage="implementation")`,
the first-round generation this section is centrally about),
`.claude/commands/apply-functional-review.md` (whose bounded-fix branch
performs the `"post-fix"` call this paragraph describes), and
`.claude/commands/recover-implementation-provenance.md` (whose own stated
phase guard names the literal `bundle_generation_target_phase` and the
recovered-role legal-source-phase set replace) are added to CP4's
command-update list accordingly — all three state the literal or the guard
this section's B1(a) resolution changes, and none was previously in any
checkpoint's scope. CP12's disposable-repository validation gains a
`"2.2"` functional-bounded-fix scenario exercising this exact path
end-to-end.

**`/review-implementation`, dual-mode**: its existing `"1"`/`"2.1"`
behavior (phase guard `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`, advisory
only, writes `REVIEW_FEEDBACK.md`, never `WORKFLOW_STATE.json`, never
advances phase) stays byte-for-byte unchanged. For a `"2.2"` item, it
becomes the authoritative `LOCAL_MODEL_IMPLEMENTATION_REVIEW` stage writer
(phase guard `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`; write set exactly
`/review-plan`'s own, substituted for the implementation stage).

**`/record-manual-implementation-review`** (new command): mirrors
`/record-manual-plan-review` exactly, substituted for the implementation
stage — mechanical, model-independent, not a user-authority gate, never
edits source/plan/registry/mapping/bundle content.

**`/approve-review implementation`**: gains the restated
`implementation_review_stages` invariant check, mirroring its existing
`plan_review_stages` check for the plan branch — a restated invariant, not
a second ingestion path, since entry to `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`
for a `"2.2"` item already required it.

**Exception/helper reuse vs. new names** (an implementation-checkpoint
judgment call, recorded here so CP2/CP3 do not re-litigate it): reuse the
already stage-agnostic primitives verbatim —
`WrongReviewerRoleError`, `StaleReviewContentIdError`,
`check_manual_stage_bundle_id_advisory` (its logic has no plan-specific
content at all) — and introduce implementation-stage-named siblings only
for the primitives whose plan-side name is literally plan-specific
(`WrongPhaseForPlanReviewStageError`, `PlanReviewStagesInvalidForVersionError`,
`WrongGoverningVersionForPlanReviewStageError`,
`MissingLocalApprovalForManualStageError`,
`DuplicateManualStageIngestionError`, `UnknownPlanReviewVerdictError`,
`AmbiguousPlanReviewStageKeyError`).

**Provenance-interval interaction — resolved (revision 2, `LOCAL_MODEL_PLAN_REVIEW`
round 1, finding B3).** The mirror is not exact at one point the plan-review
side has no analogue for: `/approve-review implementation` step 1 requires
`workflow_state.implementation_provenance_interval_reachable(...)`, which
holds only when live `HEAD` is **exactly** the discovered current
`Workflow-Bundle-Generation-Record: <work_item_id>/<implementation_revision>`
commit `T` — never merely a descendant of it
(`verify_implementation_provenance_interval`'s `HeadPastBundleGenerationRecordError`).
`plan_approval_gate_reachable` imposes nothing of the kind; it is purely
ledger-plus-content. Inserting two new state-writing transitions between
bundle generation and approval
(`record_local_implementation_review` → `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`,
then `record_manual_implementation_review` → `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`)
therefore raises a question the plan-side mirror does not: does `HEAD`
advance past `T` by the time `/approve-review implementation` runs?

Three options were weighed: (a) leave both transitions uncommitted — the
choice below; (b) widen `verify_implementation_provenance_interval` for
`"2.2"` to tolerate the two new review-stage commits after `T` — rejected,
since that invariant is heavily audited specifically to keep `HEAD == T`
from being relaxed (the "WF8b finding disposition (revision 27 → 28)"
reasoning exists for exactly this reason), and this milestone's own
narrow-scope instruction (§1) argues against touching it; (c) re-establish
`T` after the manual stage by regenerating the bundle — rejected outright,
since it contradicts §2.3/REQ-4's "no bundle regeneration between the two
stages" in the same breath it would need to satisfy it.

**This plan adopts (a)**, and the reasoning that neither review-stage
writer needs to create a commit is unchanged and re-verified: it is the
exact pattern `record_local_plan_review`/`record_manual_plan_review`
already use today, already shipped and reviewed. Neither plan-side
review-stage writer creates a git commit — each is a plain
`state_transaction` write to the working tree's
`docs/ai-workflow/WORKFLOW_STATE.json`, which `plan_approval_gate_reachable`
can read uncommitted because it never inspects `HEAD` at all.
`record_local_implementation_review` and `record_manual_implementation_review`
mirror that exactly: both write only via `state_transaction`, neither
creates a commit, and `implementation_review_stages` is (like
`plan_review_stages`) itself listed in
`implementation-review-two-stage-artifacts.json`'s implementation-stage
`excluded_paths` (`docs/ai-workflow/WORKFLOW_STATE.json`), so its bytes
never enter `review_content_id` either.

**Retracted at revision 3 (`LOCAL_MODEL_PLAN_REVIEW` round 2, finding
B1).** Revision 2 concluded from the paragraph above that "`T` — the bundle
generation commit — never moves during either new review stage... and
`verify_implementation_provenance_interval` itself needs no change for
`"2.2"` at all." That conclusion does not follow: it is true that neither
review-stage writer *moves* `T` (nothing commits between generation and
approval), but round 2 found the argument answers only "does anything
move `HEAD` past `T`?" and never asks the independent question
"does `T` *itself* remain a legally-generated commit for a `"2.2"` item at
all?" It does not, in two ways, both fixed below rather than merely
retracted.

**B1(a) — the generation-record commit's own required target phase is
version-dependent, and was hard-coded.** `record_bundle_generation`
(`scripts/workflow_state.py:10806`) unconditionally writes
`work_item["phase"] = "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW"` for both
its `"implementation"` (first-round) and `"post-fix"` (post-REVISE) call
shapes, and `validate_bundle_generation_record_commit` independently
requires the committed `phase` to equal that exact literal for both the
`"ordinary"` role (`:11120`) and the `"recovered"` role (`:11137`). For a
`"2.2"` item, `SELF_REVIEWING_IMPLEMENTATION`'s exit (first round) and
`APPLYING_REVIEW_FEEDBACK`'s post-fix exit (later rounds) must instead land
at `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` — the durability commit's entire
documented purpose is fresh-session resumption, and resuming a `"2.2"` item
mid-flight must resume it at the local-review gate, not at a phase meaning
"reviews are already done."

**Fix, assigned to CP3**: generalize the target phase into a single
function of `(stage, governing_workflow_version)`, e.g.
`bundle_generation_target_phase(stage, governing_workflow_version)` (name
open to CP3's own judgment), returning `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`
for `"1"`/`"2.1"` (both `stage` values — byte-identical to today) and
`AWAITING_LOCAL_IMPLEMENTATION_REVIEW` for `"2.2"` (both `stage` values).
`record_bundle_generation` calls it instead of writing the literal at
`:10806`; `validate_bundle_generation_record_commit` calls the identical
function — reading `governing_workflow_version` from the commit's own
committed `work_items[work_item_id]` dict, which is safe because that read
is anchored to the commit itself: it resolves the value that was in force
*at that commit*, regardless of any later change to the live entry, so
nothing about the field never changing is needed for the read to be
correct — instead of the literal at both `:11120` and `:11137`. **Restated
at revision 17 (`LOCAL_MODEL_PLAN_REVIEW` round 16, finding I1): revision
3's own wording here — "which is safe because `governing_workflow_version`
is fixed at work-item creation and never changes over a work item's
lifetime (`D-Self-Governance`)" — was the same false premise §2.2's
corrected "Future-work-item-only" paragraph above already retracts** (see
there for the enumeration of `governing_workflow_version`'s five write
sites, one of them, `promote_legacy_work_item`, an in-place mutation of an
already-existing item's field). The correction costs nothing here: `"1"`
and `"2.1"` resolve to the identical target phase, so
`promote_legacy_work_item`'s own `"1"` → `"2.1"` transition can never change
this resolver's answer even for the one work item it applies to. A
`"1"`/`"2.1"` item's commits are produced and validated identically to
today, since the function returns the same literal either way; no existing
generation-record commit, past or future, changes shape.

`RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES` (`:10867`,
today `BUNDLE_GENERATION_LEGAL_SOURCE_PHASES | {"AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW"}`)
gains `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` and
`AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` as additional legal parent
phases, so a `"2.2"` item's `/recover-implementation-provenance` remains
reachable while it sits in either new phase — otherwise, per round 2's
finding, that command (the one in-band escape from a stale
`generation_head`) would be phase-guarded unreachable precisely for the
items that spend the most wall time between generation and approval. This
widening is additive and safe unconditionally, the same argument the two
field-set constants above rely on (added at revision 5,
`LOCAL_MODEL_PLAN_REVIEW` round 4, optional finding 2):
`RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES` is a module-level
`frozenset`, and a `"1"`/`"2.1"` item can never hold either new
`"2.2"`-only phase, so the widened parent set is inert for it — only a
`"2.2"` item can ever match the added members.

The recovery command's own phase guard
(`verify_implementation_provenance_recovery`, `:11573`, and
`apply_implementation_provenance_recovery`, `:11654`) is widened the same
way: legal source phase is
`bundle_generation_target_phase("post-fix", governing_workflow_version)`
**or** one of the two new `"2.2"` phases **or, corrected at revision 5
(`LOCAL_MODEL_PLAN_REVIEW` round 4, finding B1), the terminal phase itself,
`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`** — rather than the single
hard-coded `"AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW"` literal. Revision
4's guard admitted only the two new phases, one phase narrower than
`RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES`'s own additive
widening just above (which already retains the terminal phase, since it is
additive rather than replacing). That under-widening matters because a
`"2.2"` item spends real wall time sitting at the terminal phase itself —
it is §2.2's own `"2.2"` "ready for approval" phase, and per
`.claude/commands/approve-review.md:153-157` it is *the one phase* from
which `record_bundle_generation`'s own legal source phases are unreachable
without first re-entering a remediation cycle, which is exactly the
scenario `/recover-implementation-provenance` exists to rescue. Omitting it
from the command guard reintroduced, one phase later, precisely the
unreachability round 2's own finding first identified and revision 3 set
out to prevent. CP12's negative-path list (renumbered from revision 2's
"CP7" at revision 3's checkpoint renumbering, corrected here since the
reference was never updated) gains `/recover-implementation-provenance`
from each of the **three** phases a `"2.2"` item can occupy between `T`
and approval — the two new phases plus the terminal phase (round 2's
"Missing tests" item 3, corrected at revision 5 to the full set).

**`IllegalImplementationProvenanceRecoverySourcePhaseError`'s own docstring
also needs updating (added at revision 6, `LOCAL_MODEL_PLAN_REVIEW` round 5,
optional finding 3).** Its current text (`scripts/workflow_state.py:11526-11535`)
states the terminal phase is "the only phase `/recover-implementation-provenance`
(WF8c (b)) may run from" because `SELF_REVIEWING_IMPLEMENTATION`/
`APPLYING_REVIEW_FEEDBACK` "already have their own same-content path through
`record_bundle_generation`'s `outcome=\"same_content\"`". For `"2.2"` neither
new phase (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
`AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`) has such a path — neither
is in `BUNDLE_GENERATION_LEGAL_SOURCE_PHASES_BY_STAGE` — which is precisely
why the guard above had to widen to admit them directly. CP3 updates this
docstring alongside the guard so it states the rule this design actually
implements rather than the rule that was true only while `"2.1"` was the
newest version.

**B2 — the recovered role's committed-phase clause is a single-valued
equality, but `"2.2"` legally admits recovery from either of two source
phases, and recovery never changes `phase`. Found at revision 3
(`LOCAL_MODEL_PLAN_REVIEW` round 3, finding B2).**
`apply_implementation_provenance_recovery`'s own contract (`:11629-11633`)
is that recovery never changes `phase`'s *value* — the recovered-role
commit's own committed `phase` is therefore whichever of
`RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES`'s members the
work item actually sat at when recovery ran. For `"1"`/`"2.1"` that is
still exactly one value (`bundle_generation_target_phase("post-fix",
governing_workflow_version)`, unchanged), so `validate_bundle_generation_record_commit`'s
recovered-role clause (`:11137`) correctly keeps single-valued equality
there. For `"2.2"` it is not one value: the widening two paragraphs above
makes recovery legally reachable both from
`AWAITING_LOCAL_IMPLEMENTATION_REVIEW` (where the committed phase equals
`bundle_generation_target_phase`'s own resolved value) **and** from
`AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` (where the committed
phase is a value the single-valued resolver never returns), so an equality
check against the resolver's own output alone rejects the second case
outright.

**Fix, assigned to CP3** (widened at revision 5, `LOCAL_MODEL_PLAN_REVIEW`
round 4, finding B1, to the correct set size): replace the recovered-role
committed-phase clause's single-valued equality with a membership test
against a small governing-version-dependent set,
`bundle_generation_recovered_role_legal_committed_phases(governing_workflow_version)`
— `{bundle_generation_target_phase("post-fix", governing_workflow_version)}`
for `"1"`/`"2.1"` (identical to today's single-value check, since that set
has exactly one member), and, for `"2.2"`, all **three** phases a `"2.2"`
item can legally occupy between `T` and approval —
`{AWAITING_LOCAL_IMPLEMENTATION_REVIEW, AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW,
AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW}` — since recovery does not
transition and all three are legal parent phases for recovery (the
terminal phase per the command-guard correction two paragraphs above).
Revision 4's set stopped at the first two phases, the identical
under-widening as the command guard's, one set over. This is the same
membership shape `RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES`
already uses for the *parent*-phase check just above; the committed-phase
check needs the identical membership discipline because, for the recovered
role alone, "the phase this commit records" and "the phase recovery was
invoked from" are the same value by the role's own no-transition contract.
The ordinary role keeps its existing single-valued equality unchanged —
only the recovered role's committed-phase clause changes, since only the
recovered role's whole point is that it performs no transition at all.

**The resulting invariant, stated explicitly so a future round does not
find a fourth set out of step (discharges round-4 finding B1's own
acceptance criterion 1):** for the recovered role, three sets govern
reachability, and the role's own no-transition contract forces two of them
to be equal while the third is a strict superset. The recovery command's
own invocation guard and `bundle_generation_recovered_role_legal_committed_phases(governing_workflow_version)`
**must be the identical set** — the phase recovery was invoked from is, by
construction, the phase the resulting commit records — and both **must be
a subset of** `RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES` (the
parent-phase check), which is additive and therefore always at least as
large as the other two.

**Stated exactly, not merely as it happens to hold today (added at revision
6, `LOCAL_MODEL_PLAN_REVIEW` round 5, optional finding 2).** The
committed-phase set is read by *two* producers, not one:
`/recover-implementation-provenance`'s own commit (committed phase = the
invocation phase, hence the guard's set) and
`record_bundle_generation(outcome="same_content")` (committed phase =
`bundle_generation_target_phase(stage, governing_workflow_version)`, which
is not an invocation phase of the recovery command at all). The two
coincide only because `bundle_generation_target_phase`'s `"2.2"` value,
`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`, happens to be a member of the
three-phase guard set — and, for `"1"`/`"2.1"`, because both producers
collapse to the same single literal. The exactly-true form is: the
committed-phase set must be the command guard's set **union** the
resolver's own target value for that version. Stating it that way
forecloses a future narrowing that would satisfy the "identical set"
statement above while breaking `record_bundle_generation`'s own
same-content republication path. For `"2.2"`, all three now correctly hold the
identical three-phase set at the command-guard/committed-phase layer, each
a subset of the larger, additively-widened parent set. `"1"`/`"2.1"`
behavior stays byte-identical throughout — the resolver returns the same
single literal either way, so every set collapses to today's one-member
form for those governing versions. With this fix, CP12's negative-path
list's "`/recover-implementation-provenance` from each of the three
phases" (above) is actually satisfiable by
`validate_bundle_generation_record_commit` for the terminal phase too,
which it is not under revision 4's two-phase committed-phase set.

**B1(b) — the next round's generation-record commit must tolerate a stale
`implementation_review_stages` ledger residue.** Trace the `"2.2"`
REVISE loop: round 1 generates and commits `T_1` (no
`implementation_review_stages` key yet). `/review-implementation`'s local
`APPROVE` writes the ledger — uncommitted, by design (§2.1 above).
`/record-manual-implementation-review`'s manual `REVISE` sets
`APPLYING_REVIEW_FEEDBACK` — also uncommitted; the stale local-`APPROVE`
ledger entry is left in place, exactly as `transition_to_awaiting_local_plan_review`'s
own docstring already establishes for the plan side ("the stale
`plan_review_stages` ledger, if any, is left as-is, never explicitly
cleared") — this milestone does not diverge from that convention.
`/apply-implementation-review` step 7 then regenerates and commits `T_2`
via `record_bundle_generation(stage="post-fix", outcome="same_content")`
— the ordinary REVISE loop's own same-content republication path, no
recovery command involved. **Corrected at revision 4 (`LOCAL_MODEL_PLAN_REVIEW`
round 3, finding B1).** Revision 3's trace treated `T_2` as an
`"ordinary"`-role commit and checked its field diff only against
`ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS`. That is not the commit shape
`record_bundle_generation`'s own `outcome="same_content"` branch produces:
its docstring (`:10764-10772`) and the comment immediately above
`ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS`'s own definition both establish
that the `"same_content"` outcome is `record_bundle_generation`'s
implementation of the **recovered/superseded role** (`WF8c` (c)) — the
same `Workflow-Supersedes`-trailer, three-trailer commit shape
`/recover-implementation-provenance`'s own dedicated commit uses, produced
here without that command ever running. `T_2` is therefore validated
against `RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS` (`:10863`, today
`{phase, state_revision, last_transition}`), not
`ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS` — a second, independent
constant. `T_2`'s own field diff is `{phase, state_revision,
last_transition, implementation_review_stages}` (`phase` changes because
`bundle_generation_target_phase` resolves a genuine transition out of
`APPLYING_REVIEW_FEEDBACK`; the residual `implementation_review_stages`
key — set in the working tree, absent from `T_1`'s own committed state —
is necessarily part of the diff too); that is not a subset of
`RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS` as it stands today, so `T_2`
still fails `MalformedBundleGenerationRecordCommitError` and the work item
is still wedged — widening only `ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS`,
as revision 3 did, fixes a different, non-existent failure mode and leaves
this one, the one the trace actually describes, unresolved.
`/recover-implementation-provenance`'s own dedicated recovery commit
carries the identical exposure for the same reason (both are the
recovered role): running it from `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`
right after a local `APPROVE` has written the ledger uncommitted produces
the same `{implementation_review_stages, state_revision, last_transition}`-inclusive
field diff, checked against the same constant.

**Fix, assigned to CP3**: widen **both** `ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS`
and `RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS` (neither a `"2.2"`-scoped
variant) to add `implementation_review_stages`. This is safe
unconditionally for both constants, not merely for `"2.2"`, by the same
argument: the field is `"2.2"`-only vocabulary that no `"1"`/`"2.1"` item's
`state_transaction` mutator ever writes, so for those items the key is
always absent both before and after every commit and can never appear in
either role's field diff regardless of what the allowed set contains —
widening both constants changes nothing observable for any existing item,
and needs no new per-version plumbing beyond the literal sets. No writer
in this design additionally resets the stale ledger to `null` — resetting
would still leave the field changing in the very same commit (from its
stale value to `null`), so it would not avoid needing this widening, and
adding a reset besides would be a real, stated divergence from the
plan-side writer's own "left as-is" convention for no corresponding
benefit. CP3's registry entry names both constants and states this
reasoning so a future reviewer does not re-propose the reset as if it were
a cheaper alternative, and does not mistake "the ordinary constant is
widened" for "the fix is complete."

**CP3 gains five tests for this** (round 2's "Missing tests," carried
forward, plus round 3's and round 4's own "Missing tests" additions,
renumbered at revision 6, `LOCAL_MODEL_PLAN_REVIEW` round 5, optional
finding 4, so the lead count matches the list rather than requiring a
trailing "a fifth test" sentence): (1) a test building a `"2.2"` item's
round-2 generation-record commit — the recovered-role, `outcome="same_content"`
shape described above — with a stale `implementation_review_stages`
ledger residue in the working-tree state, asserting
`validate_bundle_generation_record_commit` accepts it; (2) the symmetric
test for `/recover-implementation-provenance`'s own dedicated recovery
commit built the same way, since both are the recovered role and both
carry the identical exposure (B1); (3) the existing provenance-interval
test (§3/§6, CP3) extended to also assert (i) `T`'s own committed `phase`
for a `"2.2"` item and that `validate_bundle_generation_record_commit`
accepts it, and (ii) the REVISE-loop round specifically, where `T` is
created *after* an uncommitted ledger write; (4) a recovered-role
committed-phase test (B2; widened at revision 5, `LOCAL_MODEL_PLAN_REVIEW`
round 4, finding B1) asserting `validate_bundle_generation_record_commit`
accepts a recovery commit from **each** of the **three** phases a `"2.2"`
item can occupy between `T` and approval (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
`AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, and the terminal
`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`) and that
`verify_implementation_provenance_interval` then still resolves; and (5) a
negative test (added at revision 5, finding B1's own "Missing tests" item)
proving the widened `"2.2"` sets change no `"1"`/`"2.1"` refusal.

With all three fixes in place (B1(a)'s target-phase resolver, B1(b)'s
widening of both field-set constants, and B2's recovered-role
committed-phase membership test), `HEAD == T` is unaffected by a
local-`APPROVE` + manual-`APPROVE` ledger-write sequence, and `T` itself
is a legally generated and legally validated commit for a `"2.2"` item at
every round, in both the ordinary and recovered roles and from every legal
recovery source phase — `verify_implementation_provenance_interval`'s own
`HEAD == T` invariant is still never widened or relaxed (round 1's and
round 2's own reasoning for rejecting options (b)/(c) above stands
untouched); what changes is only that the commit's *own* required shape
(target phase, allowed field diff, and — for the recovered role — the set
of committed phases a recovery commit may legally carry) is now a correct
function of `governing_workflow_version` rather than a `"1"`/`"2.1"`-only
literal or single-valued check silently reused for `"2.2"`. CP12's
end-to-end scenario exercises the fixed behavior functionally (local
`APPROVE` → manual `APPROVE` → `/approve-review implementation` succeeding
on the first attempt, across a REVISE loop as well as the direct-approve
path, and `/recover-implementation-provenance` succeeding from each new
phase).

**Where the two-stage mirror genuinely diverges, consolidated (discharges
round 1's "Architecture and maintainability" ask, carried as round 2's
optional finding 1; resolves `AC6`).** `D-Implementation-Review-Stages`
above states "mirrors `D-Plan-Review-Stages` function-for-function where the
analogy holds exactly" — the analogy does not hold exactly everywhere, and
every place it does not is a direct consequence of one fact: **the
implementation stage's identity and provenance are both commit-anchored,
while the plan stage's are worktree-measured and gate-checked purely in
memory.** Four known divergences, all traced to that one fact:

1. **The provenance/`HEAD == T` anchor** (this subsection, above): the plan
   stage has no analogue of `verify_implementation_provenance_interval` at
   all, because `plan_approval_gate_reachable` never reads `HEAD`.
2. **No implementation-side pre-promoted terminal phase**: the plan side's
   terminal phase, `AWAITING_PLAN_APPROVAL`, already existed in
   `KNOWN_PHASES`'s vocabulary before `D-Plan-Review-Stages` promoted it to
   a persisted value (§2.2's own correction, finding I1). The
   implementation side's candidate analogue,
   `AWAITING_TECHNICAL_APPROVAL`, is available for the same promotion
   (§2.2's three-option reframing) but nothing in this design requires
   taking it — §2.2 recommends reusing
   `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`'s existing name instead, which
   has no plan-side equivalent decision point at all, since the plan side
   never had a pre-existing "reviews are done" phase name to reuse or not.
3. **Identity computation is anchored differently.**
   `compute_review_content_id_implementation_stage_at_commit` measures a
   specific commit's tree; the plan stage's own projection
   (`compute_review_content_id_plan_stage`/`_at_commit`) is worktree-measured
   when driven from a live session and only optionally pinned to a commit.
   `REVIEW_PROTOCOL.md`'s own "Computing `review_content_id`" section
   carries two explicit cautions about getting this anchor wrong for
   exactly this reason.
4. **The generation-record commit's own required shape is version-dependent
   in a way the plan side has no analogue for** (B1(a)/B1(b)/B2 above): the
   plan side has no generation-record commit at all — its ledger is
   committed by `/approve-review plan`'s own journal-backed transaction,
   long after both review stages complete, so no ledger residue can ever
   sit uncommitted across a plan-side structural commit the way
   `implementation_review_stages` could across the implementation side's
   generation-record commit. This divergence has two independent field-set
   constants (ordinary and recovered role) and two independent
   committed-phase clauses (single-valued for the ordinary role,
   membership-valued for the recovered role) precisely because the
   implementation side alone has both an ordinary and a recovered commit
   role at all — every fix to one role's shape has to be checked against
   the other's separately, which is exactly what B1(a)/B1(b)/B2 each did in
   turn. The three phase-level sets this divergence produces are the
   parent-phase set (`RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES`),
   the recovery command's own invocation guard, and the recovered role's
   committed-phase set (`bundle_generation_recovered_role_legal_committed_phases`)
   — this subsection's B2 fix binds the latter two into one set (exactly,
   their union with the ordinary resolver's target value, per the note
   below), itself a subset of the first; a future `"2.2"`-adjacent change to
   any one of the three must be checked against the other two, not made in
   isolation (added at revision 6, `LOCAL_MODEL_PLAN_REVIEW` round 5,
   optional finding 1).

Stating this once, here, is more durable than the previous arrangement
(revisions 1-2), where each divergence was patched locally where a reviewer
happened to find it, with no single place recording that they share one
root cause. CP1's overlay design text carries this consolidated
subsection's substance into `WORKFLOW_V2_PLAN.md`, since it is the fact a
future maintainer extending either stage most needs to see before assuming
the mirror is exact. **Corrected at revision 20 (`LOCAL_MODEL_PLAN_REVIEW`
round 19, finding I4): "verbatim" is dropped.** The subsection as written
above carries four inline disposition parentheticals in its own normative
text — the "(discharges round 1's … ask, carried as round 2's optional
finding 1; resolves `AC6`)" lead-in, "(§2.2's own correction, finding I1)"
at divergence 2, "(added at revision 6, `LOCAL_MODEL_PLAN_REVIEW` round 5,
optional finding 1)" at divergence 4, and this paragraph's own "(revisions
1-2)" reference — which is exactly the inline "revision N corrected finding
X" narrative point 1 above forbids in a document CP6's lint checks, and
carrying it verbatim would reproduce that defect inside
`D-Implementation-Review-Stages`'s own extent (§2.4 point 3's I4
correction). CP1 instead carries the subsection's substantive content — the
four divergences and their shared commit-anchored-versus-worktree-measured
root cause — in full, with each of the four provenance references above
restated, in substance, as an entry in a single, named `2.5.0`-scoped
disposition section CP1 adds to `WORKFLOW_V2_PLAN.md` (e.g. a
`#### 2.5.0 disposition record` subsection, explicitly classified
`HISTORICAL` under `D-Review-Material-Lifecycle`, point 2 above) rather
than inline in the carried subsection's own normative prose. **Corrected at
revision 21** (`LOCAL_MODEL_PLAN_REVIEW` round 20, finding I3: "the
document's own disposition section" was not a determinate destination —
`WORKFLOW_V2_PLAN.md` already carries 89 pre-existing disposition-shaped
headings (corrected from "83" at revision 22, `LOCAL_MODEL_PLAN_REVIEW`
round 21, optional finding O1 — 83 is only the `##`-level subset), so
nothing obliged CP1 to land its four restated provenance entries in any
particular one of them.) CP1 must name and create this exact
new section, explicitly marked `HISTORICAL`, as its own deliverable, rather
than appending to any pre-existing disposition heading. **CP1 additionally
fixes the marker's own concrete representation — its exact syntax and
delimiters — as part of this same deliverable (added at revision 29,
`LOCAL_MODEL_PLAN_REVIEW` round 28, finding B1, resolution 1: this
`HISTORICAL` marker must be written before CP6 exists to choose a
representation for it, since CP6 runs after CP1 in the registry's own
checkpoint order, so the representation cannot remain a CP6-time decision;
§2.4 point 3 and §6 state the same reassignment and what stays CP6's — the
lint that runs the parser, and every guarantee CP6 must prove; the parser
itself is CP1's own `parse_marker`, imported by CP6 rather than re-derived
(narrowed at revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2,
from "the parser that reads the representation, the lint that runs it, and
every guarantee CP6 must prove")).** **A single canonical representation
source — never one written instance alone — is the specification (revised
at revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I2,
replacing revision 30's "CP1's own single written instance of this
representation is itself the specification", added at revision 30,
`LOCAL_MODEL_PLAN_REVIEW` round 29, finding I1); §2.4 point 3's
separability bullet states the canonical `render_marker`/`parse_marker`
contract in full and names the fixture that pins CP6's conformance to it —
the representation-conformance fixture below, not a second, hand-written
grammar description.** No
fixture is added
for this specific carry: the change is to CP1's own deliverable text, and
the section's explicit `HISTORICAL` classification (never a heading-text
match) is what makes it, and only it, provenance surface rather than
current design content under CP6's lint (missing test 4's "none if the
carry is reworded" branch, `LOCAL_MODEL_PLAN_REVIEW` round 19).

### 2.2 D-Implementation-Review-Version-Activation — introducing `governing_workflow_version: "2.2"`

**Why a new version is needed at all** (unlike `AMENDING_PLAN`, which
needed none): `AMENDING_PLAN` is a wholly new, additive, opt-in entry
point that changes no existing phase's transition semantics for any
existing governing version. This milestone's design *does* change
existing transition semantics — `SELF_REVIEWING_IMPLEMENTATION`'s and
`APPLYING_REVIEW_FEEDBACK`'s exit targets, and `/review-implementation`'s
contract from advisory to authoritative — exactly the same class of
change that made `D-Plan-Review-Stages` itself require a new governing
version (`"2.1"`) rather than silently altering `"1"`'s behavior. A
governing version, once fixed at a work item's creation, must never change
meaning retroactively (`D-Self-Governance`); introducing this capability
under the existing `"2.1"` would silently change the contract for any
`"2.1"` item already resolved to enter `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`
under the old, single-stage meaning — including, in principle, a `"2.1"`
item created by a different repository that has already updated to
whatever release ships this capability. `"2.2"` avoids that.

**Why the terminal phase name is reused rather than a fresh one added**
(§2.1's `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` `APPROVE` exit):
**Corrected at revision 2 (`LOCAL_MODEL_PLAN_REVIEW` round 1, finding I1)** —
revision 1 claimed `AWAITING_PLAN_APPROVAL` "already existed, under that
exact name, as a `'1'`-era state distinct from `AWAITING_EXTERNAL_PLAN_REVIEW`".
That is factually wrong: the frozen release's own vocabulary
(`distribution/workflow/2.3.1/payload/scripts/workflow_state.py`'s
`KNOWN_PHASES`) lists `AWAITING_PLAN_APPROVAL` under the comment
`# v2.1-only additions (D-States, D-Plan-Review-Stages)`, alongside
`AWAITING_LOCAL_PLAN_REVIEW`, `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` and
`AWAITING_TECHNICAL_APPROVAL` — it is not a `"1"`-era persisted state; in
v1 it was only a gate *name* (`MILESTONE_WORKFLOW.md`'s hard-gate list),
and `D-Plan-Review-Stages` is what promoted it to a persisted phase value,
exactly the same promotion this milestone's own design performs on the
implementation side.

Which means the implementation side has the exact analogue available:
`AWAITING_TECHNICAL_APPROVAL`, already in `KNOWN_PHASES`, already the
vocabulary-only name for the technical-approval gate. Three options are
therefore live, not two: (a) introduce a genuinely new persisted
terminal-phase name distinct from both reserved vocabulary names and from
the "awaiting review" meaning; (b) keep `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`'s
name, letting `"2.2"`'s entry condition to it (widened, §2.1) carry the
"reviews are actually done" meaning, exactly mirroring how
`AWAITING_PLAN_APPROVAL`'s *entry condition* — not its name — grew the
extra ledger check for `"2.1"`; (c) promote the existing
`AWAITING_TECHNICAL_APPROVAL` vocabulary name to the persisted `"2.2"`
terminal phase — a distinct, unambiguous name with **zero new vocabulary**,
restoring rather than perpetuating plan/implementation naming symmetry.
**This plan still recommends (b)**, on the narrower ground that remains
true even after the correction — it changes no read site's shape and
requires no new phase-name plumbing anywhere `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`
is already referenced — but (c) is now recorded as a fully live
alternative, not a hypothetical one, since it costs nothing in new
vocabulary either. **Resolved at revision 15** (§9,
`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, required acceptance criterion 4):
**adopts (b)**, for the reasons already stated; (a) and (c) remain
recorded (§9) as considered alternatives, not silently dropped.

**Activation mechanism**: `WORKFLOW_CONFIG.json`'s
`default_workflow_version` gains `"2.2"` as its new value, and
`supported_versions` gains `"2.2"` as a new member, via generalized
`build_activated_config`/`build_rolled_back_config` helpers (**corrected
at revision 2, `LOCAL_MODEL_PLAN_REVIEW` round 1, finding I2**: the
rollback helper's actual name is `build_rolled_back_config`, not
`build_rollback_config` — `scripts/workflow_state.py:6637`) accepting a
target version parameter, reused rather than duplicated. Both helpers'
one-time-boundary guards need redesigning around a target version, not
merely parameterizing: today `build_activated_config` raises
`AlreadyActivatedError` when the config is already at `"2.1"` ("activation
is a sole, one-time boundary, not an idempotent setter") and
`build_rolled_back_config` raises `NotActivatedError` unless the config
*is* at `"2.1"` — CP1/CP2 generalize both checks to compare against the
target version parameter rather than the literal `"2.1"`. Neither helper
today writes `supported_versions` at all — each returns
`{**config, "default_workflow_version": ...}`, leaving every other field,
`supported_versions` included, untouched; nothing in the repository
currently writes `supported_versions` (it is only read: validated at
config-load time and checked again at work-item creation against a
governing version). CP1/CP2 must therefore also extend whichever helper
performs activation to append the target version to `supported_versions`,
not merely swap `default_workflow_version` — a genuinely new piece of
behavior, not a reuse of the existing `{**config, ...}` shape unchanged.

**Activation entry point, decided (resolves `LOCAL_MODEL_PLAN_REVIEW` round
10, finding I2): the hand edit is the supported path in `2.5.0`; the
generalized helpers stay library/design surface with no caller.**
`build_activated_config`/`build_rolled_back_config` are generalized above
because they are the executable specification CP2's own unit tests pin the
target-version transform against, and because a future `workflow_manager`
verb that automates the edit, if one is ever added, has a ready-made,
already-tested entry point to call rather than a redesign — not because
this milestone wires one in. The documented procedure in the new
`IMPLEMENTATION_REVIEW_WORKFLOW.md` operator guide (**Reachability**,
below) is the hand `WORKFLOW_CONFIG.json` edit directly, never a call
through these helpers, and states so explicitly. Consequently
`AlreadyActivatedError`/`NotActivatedError` — real guards on the helpers
themselves, exercised by CP2's own unit tests — do not constrain the
supported path at all: nothing stops an operator from hand-editing
`default_workflow_version` back and forth outside the helpers' one-time-
boundary check, and `WF-Activate`'s own "activation is a deliberate,
trailered boundary" is, for `"2.2"`, operator discipline plus the
trailer/ancestry-search machinery above, not code enforcement. The
**Template question** paragraph below is read consistently with this: it
declines the pre-enabled template because bypassing `D-Self-Governance`'s
boundary would require unauthorized `build_release.py` changes, not because
the boundary is otherwise code-enforced.

**Rollback's own destination is the version activation superseded, never a
fixed literal (resolves `LOCAL_MODEL_PLAN_REVIEW` round 7, finding I2).**
`build_rolled_back_config` is exactly two literals today: the guard
`config.get("default_workflow_version") != "2.1"` and the return value
`{**config, "default_workflow_version": "1"}` (`scripts/workflow_state.py:6645`
and `:6651`). Generalizing only the guard, as the paragraph above already
says, and leaving `:6651`'s `"1"` untouched would make a `Workflow-Rollback:
2.2` pass its own guard and then set `default_workflow_version` to `"1"` —
undoing both the `"1"`→`"2.1"` and `"2.1"`→`"2.2"` activations when the
operator asked to undo only the second, after which every new work item and
every remediation child (`create_remediation_child_work_item` reads
`config["default_workflow_version"]`) is silently born `"1"` instead of
`"2.1"`. **Fix, assigned to CP1/CP2 alongside the guard generalization
already described**: the generalized `build_rolled_back_config` takes the
target version's own predecessor as its rollback destination (`"2.2"` rolls
back to `"2.1"`, mirroring the guard's own target-version parameter) rather
than a hard-coded literal, and both helpers' docstrings and trailer examples
stop naming `2.1` as the only boundary. **Derivation mechanism, stated
explicitly (corrected at revision 9, `LOCAL_MODEL_PLAN_REVIEW` round 8,
optional finding 1): the predecessor comes from an explicit predecessor
mapping (or an equivalent caller-supplied parameter), never from comparing
version strings** — this section's own reasoning below already rejects
ordering comparison for these values (`"2.10" < "2.2"` lexicographically),
so "predecessor" cannot mean a computed ordering here; `"2.2"`'s entry in
that mapping is `"2.1"`, a declared table value, not a derived one, and
`"2.1"`'s entry is `"1"`, the literal `:6651` returns today, declared
rather than derived for the same reason. Rollback does **not** remove the
target version from `supported_versions` — cheaper to state than to build,
since `validate_governing_version` (`:6701`) is only ever called with
`config["default_workflow_version"]` itself (never with an independently
requested version), so a stale `supported_versions` member grants nothing
today; this asymmetry (activation appends, rollback does not remove) is
recorded here as the reason it is acceptable now, not left silent the way
round 7 found it.

**Activation event model, decided version-aware rather than binary
(resolves `LOCAL_MODEL_PLAN_REVIEW` round 10, finding I1).** `is_activated`'s
sole caller, `load_config` (`scripts/workflow_state.py:6692`), treats
"activated" as a binary fact today: `find_latest_activation_event`
(`:6600-6613`) returns whichever of `Workflow-Activation`/`Workflow-Rollback`
landed most recently, by trailer *key* alone, never reading the trailer's
own *value* — so `is_activated` is `False` after **any** rollback,
including a `Workflow-Rollback: 2.2` commit whose destination is `"2.1"`,
not `"1"`. Left as designed above, that silently disarms
`ConfigMissingAfterActivationError`'s hard stop for a repository that is
still `"2.1"`-configured, degrading a subsequent missing/corrupt config to
`default_config()` and, through `route_work_item`/
`create_remediation_child_work_item`, born-`"1"` for every work item and
remediation child created in that window — the exact silent downgrade
`OPUS-R6-015` added the hard stop to prevent (`ConfigMissingAfterActivationError`'s
own docstring), reached by the one route that fix does not cover. **Fix,
assigned to CP2 alongside the guard/destination generalization already
described above**: `find_latest_activation_event`/`is_activated` become
version-aware. Each event's own *destination* version is read from the
trailer's value — an activation trailer's value directly, a rollback
trailer's value resolved through this section's own explicit predecessor
mapping (the same one `build_rolled_back_config`'s destination now uses) —
and `is_activated` reports `True` whenever that destination is not `"1"`.
This reproduces today's binary behavior exactly at the one boundary it
already covers (`Workflow-Rollback: 2.1`'s destination is `"1"`, so still
not activated) and additionally reports `True` after `Workflow-Rollback:
2.2` (destination `"2.1"`), which is the correct answer: the repository is
still `"2.1"`-configured and the hard stop must stay armed. `load_config`'s
raise message and `ConfigMissingAfterActivationError`'s own docstring, both
of which hard-code "Workflow v2.1" today (`:6693-6696`, `:727-730`), are
generalized off that literal to name the version actually in force rather
than always naming `"2.1"`. **Message source, stated explicitly (taken as
`LOCAL_MODEL_PLAN_REVIEW` round 12's optional finding 1, since
`is_activated` keeps its boolean signature and nothing else in
`load_config`'s call graph carries a version string):** the message names
the resolved destination version when `find_latest_activation_event`
resolves one, and the unresolved trailer's own value verbatim in the miss
case the "Rollback-trailer-value miss" paragraph below makes reachable —
never a table subscript in the message path itself. **Plumbing, stated
explicitly (taken as `LOCAL_MODEL_PLAN_REVIEW` round 13's optional finding
3):** `find_latest_activation_event`'s own return widens from `(kind,
commit)` to also carry the resolved destination (or the unresolved
trailer's raw value in the miss case), and `load_config` reads the message
source from that widened return rather than re-deriving it — `is_activated`
itself keeps its boolean signature unchanged, per this section's own
round-11 decision above. Both sites are added to CP2's own site list.
**Taken as `LOCAL_MODEL_PLAN_REVIEW` round 11's optional finding 1**:
`AlreadyActivatedError`'s and `NotActivatedError`'s own docstrings
(`scripts/workflow_state.py:733-736`, `:739-743`) hard-code `"2.1"` as
their only boundary in the same exception-class block as
`ConfigMissingAfterActivationError`, so CP2's site list gains these two
docstrings as well, generalized off the target-version parameter alongside
the guards themselves (`:794-801`, above) — even though, per the activation
entry point decided above, neither guard fires on the supported hand-edit
path, so the correction is for accuracy against a hand-built config rather
than for any behavior an operator observes.
One sentence in the new `IMPLEMENTATION_REVIEW_WORKFLOW.md` operator guide
records the consequence for the first consumer to activate `"2.2"`: after
this commit, a missing or corrupt config is a hard stop rather than a
silent fallback — already true for `"2.1"`, but newly true, as an explicit
side effect, for this repository's own configuration at the moment it
activates.

**Rollback-trailer-value miss, decided fail-closed (resolves
`LOCAL_MODEL_PLAN_REVIEW` round 11, finding I1; domain corrected at
revision 13, round 12, finding I1).** The predecessor mapping above is
total only over the versions this section itself declares into it —
today's declared domain is `"2.1"` → `"1"` and `"2.2"` → `"2.1"`, both
already named above (the guard/destination generalization paragraph's own
`"2.1"` boundary and the derivation paragraph's `"2.2"` entry), not the
single `"2.2"` → `"2.1"` entry revision 12 mistakenly claimed as sole. A
`Workflow-Rollback: 2.1` trailer is therefore a *found* destination of
`"1"` (not activated, byte-unchanged from today), never the miss branch;
only a value outside that two-entry domain (a bare/empty value, an ordinary
typo, or a genuinely unrecognized version) reaches the miss rule below.
`is_activated`/`find_latest_activation_event`'s own input domain is not
similarly closed —
it is whatever value a `Workflow-Rollback` trailer carries anywhere in
first-parent ancestry (`_commit_trailers`, `:1416-1431`, returns plain
`dict[str, str]` from `git interpret-trailers --parse`, `""` included), and
under the hand-edit-plus-hand-written-trailer path this section just made
the supported one for `"2.2"`, nothing validates that value before it is
committed. Three reachable misses: a bare `Workflow-Rollback:` trailer with
no value; an ordinary hand-edit typo (`Workflow-Rollback: 2.2.0`); and a
future release's own version, read by an older `2.5.0`-era `is_activated`.
**An unresolvable rollback-trailer value resolves as activated** — fail
closed, the hard stop stays armed, never a silent fall-through to
not-activated and never an uncaught `KeyError` propagating out of
`load_config`. Concretely: the predecessor mapping stays a plain table (no
`.get(value, default)` widening its own domain), and the miss is caught by
an explicit branch checked before the table lookup, so a mapping-miss and a
found-but-`"1"` destination are never conflated. The activation direction
needs no equivalent rule — an activation trailer's value is used directly,
and any value other than `"1"` already answers `True` — so this asymmetry
is inherent to what the two trailer kinds mean, not an oversight the fix
leaves standing. Nor is §2.2's own "equivalent caller-supplied parameter"
alternative (above, the predecessor mapping's derivation paragraph)
available here: that escape hatch presumes a caller that already knows the
version it targets, and `find_latest_activation_event`/`is_activated` take
no target parameter at all (`scripts/workflow_state.py:6600`, `:6615` —
signature `(repo_root, head="HEAD")`), so there is no caller-supplied value
for this consumer to use instead. The `IMPLEMENTATION_REVIEW_WORKFLOW.md`
operator guide's missing-config-consequence sentence above gains one more
clause for this: the trailer's value is now semantically load-bearing and
must be written as exactly the activated version string, since after this
change a mistyped or blank rollback trailer no longer merely fails to
document the boundary but changes which config states are treated as
activated. Both `find_latest_activation_event` and `is_activated` are
already CP2's sites for the version-aware rewrite above; this miss rule is
one more thing CP2 implements at those same two sites, not a new site, and
§6 gains the corresponding test case below.

**Scope of the activation ceremony itself — resolved at revision 15**
(§9, `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, required acceptance criterion
4): the original `"1"`→`"2.1"`
`WF-Activate` ceremony (dry-run synthetic work item, activation/rollback
commit trailers, missing-config ancestry search) was built to *establish*
that whole pattern from scratch, self-hosted, with no fallback if it was
wrong. That infrastructure now exists and is proven. This plan's default
recommendation is a lighter activation for `"2.1"`→`"2.2"` — a direct,
reviewed config-default commit carrying the same `Workflow-Activation:
2.2`/`Workflow-Rollback: 2.2` trailer discipline and the same
missing-config ancestry-search behavior (both cheap to keep, since they
already exist as generalizable helpers), but **without** re-running a full
multi-session synthetic dry-run scenario — CP12's disposable-repo
validation (real repos, real end-to-end flows) already re-proves the new
capability directly, which is a stronger check than a synthetic dry-run
inside this very repository would add on top. This recommendation is now
adopted (above): the full-ceremony repeat remains recorded (§9) as a
considered, declined alternative.
(**Corrected at revision 5, `LOCAL_MODEL_PLAN_REVIEW` round 4, finding
I1** — this cross-reference said "CP7" from revision 3 through revision 4
without being updated to CP12, revision 3's own checkpoint renumbering
notwithstanding; CP7 is now review-scalability branch 2 and carries no
disposable-repo validation at all.)

**Reachability: how a repository managed by `2.5.0`, other than this one,
ever gets a `governing_workflow_version: "2.2"` work item at all, stated
explicitly (resolves `LOCAL_MODEL_PLAN_REVIEW` round 9, finding I1).**
Nothing above routes a work item to `"2.2"` by itself — everything this
section designs only makes `"2.2"` a legal, buildable target once a
repository has separately chosen it. Verified directly against
`scripts/workflow_state.py`: `route_work_item`'s fresh-id branch and the
remediation-child creator both pass `config["default_workflow_version"]`
straight through to `default_work_item`, with no parameter, flag, or
command argument anywhere that lets an operator request a version instead.
`"2.2"` therefore becomes reachable only by editing a repository's own
`WORKFLOW_CONFIG.json` by hand — **both** `default_workflow_version` and
`supported_versions`, since `validate_config` refuses a default absent
from `supported_versions` — and that file is a state template
`src/workflow_manager/release.py`'s `STATE_TEMPLATES` never rewrites for
an already-managed repository (`tests/test_bootstrap.py` pins it
`generated`, written once). This is the same shape `"2.1"` itself needed,
with one asymmetry `"2.1"` never had: `"2.1"` already shipped as
`2.4.0`'s own template default, so a fresh install created `"2.1"` items
with zero operator action; `2.5.0`'s own template stays at `"2.1"` (the
template question immediately below), so `"2.2"` is the first version
every consuming repository must activate deliberately, by the same
two-field edit plus `Workflow-Activation: 2.2`/`Workflow-Rollback: 2.2`
trailer discipline this section already generalizes above — stated here as
the *procedure* an operator follows, not only as the precondition §5
already states. **The procedure itself is written down**, as its own
dedicated section, in the new `IMPLEMENTATION_REVIEW_WORKFLOW.md` operator
guide CP1 authors (§5's second bullet is amended to cross-reference it):
the exact two `WORKFLOW_CONFIG.json` fields that must change together, the
commit trailer, and that `validate_config` refuses an edit to only one of
the two fields.

**Future-work-item-only, decided (resolves `MANUAL_EXTERNAL_PLAN_REVIEW`
round 1, finding I1). Premise corrected at revision 16 (`LOCAL_MODEL_PLAN_REVIEW`
round 15, finding I1): revision 15's own wording here —
"`governing_workflow_version` is fixed at a work item's creation and never
changes over its lifetime… and `route_work_item`/`create_remediation_child_work_item`
— the only two writers of the field… set it once, at creation, never
again" — was false as stated.** Enumerating every write of the field in
`scripts/workflow_state.py` finds five sites, not two:
`route_work_item` and `create_remediation_child_work_item` (both creation-time,
as stated), `import_legacy_work_item` (also creation-time, for the dormant
`LEGACY_READY` entry), and `promote_legacy_work_item`, which mutates an
**already-existing** work item's `governing_workflow_version` from `"1"` to
`"2.1"` **in place**, on legacy adoption — the same fact this section's own
round-6 bullet below already states and assigns CP3 to correct in the
function's own docstring. The honest claim is narrower than immutability:
no promotion path from `"1"`/`"2.1"` to `"2.2"` exists today, and this
milestone deliberately does not add one or generalize the one existing
in-place precedent to reach it — the round-6 bullet below already supplies
the reason (an adopted item sits at `AWAITING_FUNCTIONAL_REVIEW`, past both
implementation-review stages, so promoting it further to `"2.2"` would buy
nothing and would in fact wedge it against `technical_approval_gate_reachable`'s
new `"2.2"` check). Everything above establishes how a repository makes
`"2.2"` a legal target at all; it says nothing about whether an
already-existing `"1"`/`"2.1"` work item can ever become `"2.2"` after the
fact. It cannot, and this milestone adds no mechanism that would let it.
**This plan adopts contract (2) of the two the plan-review gate posed**:
`"2.2"` is available only to a work item created after its own repository
has activated it; no promotion path is added for an existing `"2.1"` item.
§5's own migration bullet is corrected below to state this without the
ambiguity the reviewed round found, and without the false premise round 15
found: activating `default_workflow_version` changes which version *a
subsequently created* work item or remediation child receives — never an
already-existing item's own already-fixed `governing_workflow_version`, at
any point, before or after activation, except through
`promote_legacy_work_item`'s own pre-existing `"1"` → `"2.1"` legacy-adoption
transition, which this milestone leaves exactly as is and does not extend.

**Reconciled explicitly against the Controller rollout (same finding).**
§1's own roadmap tree names "→ upgrade Controller" as this milestone's
declared future consumer, out of scope here; the concrete instance is
`~/Workspace/workflow-controller`'s own work item
`workflow-controller-generation-1`, already `"2.1"`-governed and, as of
this plan's own prior revision, mid-implementation
(`SELF_REVIEWING_IMPLEMENTATION`, `CP9` — `docs/ACTIVE_MILESTONE.md`'s own
prior-milestone record of it, read for context only, per that document's
own standing instruction never to touch or drive that repository from
this one). Under the contract just adopted, updating `workflow-controller`
to `2.5.0` and resuming that work item does **not**, by itself or after
that repository separately activates `"2.2"`, change
`workflow-controller-generation-1`'s own governing version: it stays
`"2.1"` for the rest of its lifetime and keeps the single-stage
implementation-review flow this milestone's own `"1"`/`"2.1"` branch
leaves byte-for-byte unchanged (§2.1). Only a *new* work item created in
that repository after it activates `"2.2"` would ever get the two-stage
flow. This is stated here as the operator's own informed, deliberate
acceptance of that consequence, not as an oversight left implicit: a
live-item promotion mechanism remains available for a future release to
design, scoped and reviewed on its own — exactly the posture CP10's own
reconsideration of `v2.4.0-002` (§2.7/§8/§9) already takes toward its own
deferred structural fixes.

**Template question, decided rather than left to CP11 to discover
(resolves round 9, finding I1's own recommendation).** `2.5.0`'s own
`templates/docs/ai-workflow/WORKFLOW_CONFIG.json` stays at `"2.1"`,
byte-unchanged from `2.4.0`'s: a fresh `2.5.0` bootstrap is **not**
`"2.2"`-enabled, and activation remains the per-repository operator act
described immediately above. Shipping the template pre-enabled instead is
declined for this milestone, and is not merely a style preference: it is
not expressible today without a further, unauthorized tooling change —
`tools/build_release.py` refuses any overlay payload path whose
`target_path` collides with a base template's `target_path`, and copies
every base template forward unchanged, so adopting it would require
`build_release.py` gaining overlay-template support no checkpoint in this
plan scopes, purely to bypass a boundary `D-Self-Governance` deliberately
draws ("activation is a deliberate, trailered boundary"). A future release
touching `build_release.py` for its own reason is free to revisit this as
its own scoped change; this milestone does not.

**Inheritance rule, stated explicitly and in its general form (resolves
`LOCAL_MODEL_PLAN_REVIEW` round 5, finding B1, and round 6, finding B1).**
Everything above activates `"2.2"` for the *implementation* side by adding
the two-stage implementation-review stages. Beyond that one addition,
**a `"2.2"` item is a `"2.1"` item: every `"2.1"`-gated behavior applies to
`"2.2"` unchanged, at every gate and in every command and workflow
document, except the implementation-review stages this milestone adds.**
The rule is general — it is not scoped to plan-review, and stating it that
way once (round 5's own framing below, "on the plan side… every
`"2.1"`-gated **plan-review** behavior applies to `"2.2"` unchanged") is
what let round 6's B1 find three further surfaces that framing never
reached: `/milestone-implement.md`'s own step 0 branch set,
`MILESTONE_WORKFLOW.md`'s plan-review state text, and four more command
documents' two-version enumerations — all fixed below, alongside the four
plan-review code gates round 5 already found.

§2.2's own argument above is entirely about what `"2.2"` does *not*
change; it never states what a `"2.2"` item *inherits*, and the code
answers that question today by four separate exact-equality
`governing_workflow_version == "2.1"` (or `!= "2.1"`) comparisons that
gate `D-Plan-Review-Stages`'s two-stage plan-review protocol — each of
which excludes `"2.2"` by construction, the same hard-coded-enumeration
class §2.1's B1(a)/B2 already fixed once on the implementation-phase side,
found here, unfixed, on the plan-version side. Left as-is, the first
`"2.2"` work item cannot be planned at all (the very first
`/milestone-plan` step crashes), and if that crash alone were patched, the
item would instead reach `AWAITING_PLAN_APPROVAL` on a single reviewer
pass — the exact single-reviewer gap `D-Plan-Review-Stages` exists to
close, making `"2.2"` strictly *weaker* than `"2.1"` at the plan gate
while strictly *stronger* than it at the implementation gate this very
milestone adds.

**Fix, assigned to CP2**: a single named membership constant,
`TWO_STAGE_PLAN_REVIEW_VERSIONS = {"2.1", "2.2"}`, replacing the
equality/inequality literal at each of the four sites below, so a future
`"2.6.0"` widens one thing rather than four:

- `publish_plan_revision` (`scripts/workflow_state.py:7457-7465`): routes
  `"2.2"` to `AWAITING_LOCAL_PLAN_REVIEW`, the same target `"2.1"` gets,
  instead of raising `UnsupportedGoverningVersionError`.
- `plan_approval_gate_reachable` (`:10078`): requires the
  `plan_review_stages` ledger's two-stage `APPROVE` check for `"2.2"` too,
  instead of returning `True` unconditionally — today's `"1"`-equivalent
  bypass, which for `"2.2"` would silently skip the plan-review-stage
  ledger requirement entirely.
- `_require_v2_1_plan_review` (`:11753`): accepts `"2.2"` — so
  `/review-plan`, `/record-manual-plan-review`, `record_local_plan_review`
  and `record_manual_plan_review` all work for a `"2.2"` item — instead of
  raising `WrongGoverningVersionForPlanReviewStageError`.
- `_validate_plan_review_stages` (`:12160`): treats a non-null
  `plan_review_stages` ledger as valid state for `"2.2"`, instead of
  raising `PlanReviewStagesInvalidForVersionError`.

`"1"` behavior stays byte-identical at all four sites (never a member of
`TWO_STAGE_PLAN_REVIEW_VERSIONS`), and so does `"2.1"` behavior (already a
member, and a membership test returns the same answer for it that the
equality test did). The plan-stage command-contract documents carry the
identical two-version (`"1"`/`"2.1"`) enumeration and need the matching
widening, assigned to CP4 below: `/milestone-plan.md` (`:59-67`),
`/apply-plan-review.md` (`:41`, `:135`), `/approve-review.md` (`:62-64`,
`:97`), `/review-plan.md` (`:39`), `/record-manual-plan-review.md`
(`:46`), and `/request-plan-amendment.md` (`:21-25`, whose own "downstream
`/milestone-plan` re-entry" sentence names `/milestone-plan`'s two-branch
set). CP2 also gains a parametrized unit test over `("1", "2.1", "2.2")`
pinning each of the four sites' answer per version — including that `"1"`'s
and `"2.1"`'s answers are byte-unchanged — and CP12's disposable-repo
scenario states explicitly that the synthetic `"2.2"` item's own *plan*
stage runs the full two-stage plan-review protocol
(`AWAITING_LOCAL_PLAN_REVIEW` → `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` →
`AWAITING_PLAN_APPROVAL`) before any implementation-review stage is
reached, which doubles as the end-to-end proof that `/milestone-plan` no
longer crashes on a `"2.2"` item's first step (§3, §6, §4's new REQ-15).

**Reasoning recorded beside `TWO_STAGE_PLAN_REVIEW_VERSIONS` itself, so a
future release does not relitigate the shape (round 6's optional finding
3).** An explicit membership set, not a monotonic "at least `"2.1"`"
comparison, is deliberate: governing versions are opt-in *contracts*, not
a capability ladder (`validate_governing_version` tests membership in
`supported_versions`, never ordering, and a version's meaning is fixed at
creation); a monotonic test would silently enrol a future version that
*replaces* the two-stage plan-review protocol rather than inheriting it,
making that design's opt-out invisible instead of a one-line set edit; and
the values are strings for which the obvious ordering comparison is wrong
anyway (`"2.10" < "2.2"` lexicographically). Hand-widening one named set
per release that actually inherits the protocol is the feature, not the
cost.

**Three further surfaces, found at round 6 (resolves
`LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1).** The four-site code fix
and the six-document command-contract widening above are exhaustive for
the *plan-review* protocol specifically, but the general rule above
reaches further, and round 6 found three surfaces the plan-review-scoped
framing missed entirely:

- **(a) `/milestone-implement.md` step 0's own branch set.** Step 0
  (`:17-38`) defines exactly two governing-version branches, `"1"` and
  `"2.1"`; a `"2.2"` item matches neither. Under the `"1"` branch's
  explicit no-state-write text, neither of `SELF_REVIEWING_IMPLEMENTATION`'s
  two writers (`complete_checkpoint`, `enter_self_reviewing_implementation`)
  ever runs, so step 4's `record_bundle_generation(stage="implementation")`
  call (already CP4's own documentation item, reached regardless of branch
  since it is gated on a `WORKFLOW_STATE.json` entry existing, not on
  governing version) raises `IllegalBundleGenerationSourcePhaseError` —
  `BUNDLE_GENERATION_LEGAL_SOURCE_PHASES_BY_STAGE["implementation"]` is
  exactly `{"SELF_REVIEWING_IMPLEMENTATION"}`. **Fix, assigned to CP4, as
  an item distinct from the `record_bundle_generation` documentation item
  already there**: step 0's branch set states that a `"2.2"` item takes
  the `"2.1"` branch — `[2.1 step 1]`'s resumable sequence and step 2's
  `enter_self_reviewing_implementation` write included — so
  `SELF_REVIEWING_IMPLEMENTATION` is reachable and
  `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` (`record_bundle_generation`'s own
  version-dependent resolver, already CP3's sole writer for that phase) is
  reachable in turn.
- **(b) `MILESTONE_WORKFLOW.md`'s plan-review text.**
  `AWAITING_LOCAL_PLAN_REVIEW`/`AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`'s own
  headings, entry/exit prose, and verdict/transition table (today's
  `:165`, `:170`, `:195`, `:224`, `:228`, `:231`, `:242`, `:576`, `:584`)
  all read `governing_workflow_version: "2.1"` as the exhaustive
  membership test, most consequentially `AWAITING_PLAN_APPROVAL`'s own
  entry condition (`:249-256`): "For a `governing_workflow_version: "2.1"`
  work item… a single reviewed round is necessary but no longer
  sufficient," closing "A `"1"` item's entry condition is exactly
  `REVISING_PLAN`'s exit condition, unchanged" — which for a `"2.2"` item
  reads as the no-ledger-requirement case, precisely the opposite of
  `plan_approval_gate_reachable`'s widened `"2.2"` behavior. **Fix,
  assigned to CP1** (which already owns `MILESTONE_WORKFLOW.md` updates
  for this overlay): every one of these sites states the `"2.1"`/`"2.2"`
  membership (`TWO_STAGE_PLAN_REVIEW_VERSIONS`) explicitly rather than the
  bare `"2.1"` literal, with `AWAITING_PLAN_APPROVAL`'s entry condition the
  priority since it ships the silent bypass.
- **(c) Four more command-document two-version enumerations, no behavior
  change, same class**: `/accept-milestone.md:43-49` ("Both `"1"` and
  `"2.1"` items run steps 1-8 identically"), `/review-functional.md:61-64`
  ("reachable for a `governing_workflow_version` of `"1"` or `"2.1"`
  alike"), `/prepare-functional-review.md:47-51` ("`governing_workflow_version`
  has transitioned `"1"` → `"2.1"`"), and `/apply-functional-review.md:227-231`'s
  remediation-child sentence ("enters review at `AWAITING_LOCAL_PLAN_REVIEW`
  when its `governing_workflow_version` is `"2.1"`… and at
  `AWAITING_EXTERNAL_PLAN_REVIEW` when it is `"1"`"). The last is directly
  coupled to B1: `create_remediation_child_work_item` fixes a remediation
  child's governing version from `config["default_workflow_version"]`, so
  once `"2.2"` is activated as the repository default, every remediation
  child is born `"2.2"`, and `publish_plan_revision`'s widened routing
  already sends it correctly to `AWAITING_LOCAL_PLAN_REVIEW` — the
  sentence describing that routing must say so for the common case, not
  only for `"2.1"`. **Fix, assigned to CP4** alongside the six plan-stage
  documents it already widens: each of these four sentences is restated to
  include `"2.2"` (the first three as version-independent for `"1"`,
  `"2.1"`, or `"2.2"` alike; the fourth's remediation-child sentence to
  route a `"2.2"` child identically to a `"2.1"` child).

**Four further surfaces, found at round 7 by running the sweep above by
hand over the actual `2.4.0` payload (resolves `LOCAL_MODEL_PLAN_REVIEW`
round 7, finding B1(b)-(e)).** The three-surface sweep round 6 found and
the four-site/six-document plan-review-command widening above are still
correct as far as they reach; round 7 found four further sites the round-6-
derived list did not cover, all instances of the same general inheritance
rule applied to documents nobody had yet cited:

- **(d) `docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`, unassigned entirely.**
  Byte-identical to `distribution/workflow/2.4.0/payload/docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`,
  so it ships. Three sites, all wrong for `"2.2"` after this section's own
  widening: `:1`, the document title, "# Two-Stage Plan-Review Protocol
  (`governing_workflow_version: "2.1"` only)"; `:14-19`, "Scoped entirely to
  `"2.1"` work items… `/review-plan` and `/record-manual-plan-review` both
  refuse cleanly if invoked against a `"1"` item" (the second half is
  correct post-widening and stays; the first half is the same statement
  `MILESTONE_WORKFLOW.md:170` makes, which CP1 already widens); `:66`,
  "`/apply-plan-review`: unchanged mechanism, `"2.1"`-only revised exit" —
  the operator-facing copy of the exact docstring optional finding 2 above
  corrects in code. **Fix, assigned to CP1** (the same class and the same
  overlay as `MILESTONE_WORKFLOW.md`, which CP1 already owns): widen all
  three sites to `"2.1"`/`"2.2"` alike, `"1"` behavior unchanged.
- **(e) `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, assigned under a scope that
  does not reach it.** Byte-identical to the payload copy. Two sites are
  outside any reading of CP4's existing "phase and command tables" item:
  `:21-24`'s own operator-reference definition of the governing-version
  space in prose ("**Two governing versions** exist per work item, fixed at
  creation: `"1"` … and `"2.1"` …") and `:229`/`:246`'s documented
  precondition of `/review-plan`/`/record-manual-plan-review`
  ("`"2.1"` only", beside a correct "**Refuses**: a `"1"` item" line each).
  **Fix, assigned to CP4**, as items distinct from its existing "phase and
  command tables" item: restate `:21-24` to name three governing versions
  (`"1"`, `"2.1"`, `"2.2"`) and correct `:229`/`:246`'s "`"2.1"` only" to
  the `"2.1"`/`"2.2"` membership.
- **(f) Two `MILESTONE_WORKFLOW.md` sites outside CP1's own cited scope.**
  CP1's registry entry scopes its plan-review-text widening to the
  `AWAITING_LOCAL_PLAN_REVIEW`/`AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`
  headings, entry/exit prose and verdict/transition table, and
  `AWAITING_PLAN_APPROVAL`'s own entry condition; two sites fall outside all
  four. `:52` (`AMENDING_PLAN`'s own scope sentence): "Applies to
  `governing_workflow_version: "1"` and `"2.1"` work items alike; only the
  downstream two-stage-vs-single-stage plan review that follows it still
  branches on governing version, unchanged" — the state-machine twin of
  `/request-plan-amendment.md:21-25`, which CP4 already widens; the command
  document gets fixed and the normative state definition it points at does
  not, until now. `:121` (`SELF_REVIEWING_PLAN`): "`/milestone-plan` …
  writes `AWAITING_LOCAL_PLAN_REVIEW` (`"2.1"`) or
  `AWAITING_EXTERNAL_PLAN_REVIEW` (`"1"`) directly, through
  `publish_plan_revision`" — the prose form of the exact routing table CP2
  already widens in code. **Fix, assigned to CP1**, as items distinct from
  its existing plan-review-state item: both sites restate the `"2.1"`
  membership as `"2.1"`/`"2.2"` alike, `"1"` behavior unchanged.
- **(g) The two plan-review commands' frontmatter `description:` lines.**
  `.claude/commands/review-plan.md:2` and
  `.claude/commands/record-manual-plan-review.md:2` both end "… of the
  two-stage plan-review protocol (`"2.1"` work items only)", byte-identical
  to the payload copies. CP4 already widens `:39`/`:46` (the in-body
  guards) for these two files, not `:2` — the frontmatter `description` is
  the operator- and model-visible one-liner in the command list, so it is
  the first thing a `"2.2"` operator reads, and today it says the command is
  not for them. **Fix, assigned to CP4**, one line each: drop the
  parenthetical's `"2.1"`-only framing so the description reads as
  version-independent (the in-body guard already states the precise
  membership).

**Registry propagation** (round 5's criterion 2, repeated for round 6's own
three surfaces and round 7's own four): CP4's registry entry now names (a),
(c), (e) and (g) explicitly; CP1's registry entry now names (b), (d) and (f)
explicitly, since CP1's prior scope ("state reference and hard-gates
summary") did not by itself reach the plan-review states or
`PLAN_REVIEW_WORKFLOW.md`. **Corrected at revision 9 (`LOCAL_MODEL_PLAN_REVIEW`
round 8, finding I2): CP11's registry entry itself is widened to say "every
payload document the sweep requires changing"**, matching §4's REQ-15's own
general wording verbatim rather than only echoing CP1's/CP4's named
widenings — revision 8's registry entry said "every payload document CP1's
or CP4's own round-6/round-7 plan-review inheritance widening requires
changing", which both misquoted this paragraph's own general phrasing and,
more consequentially, left CP6's own catch-all fixes (below) outside the
recorded scope even though they land in exactly the same overlay directory
for exactly the same reason. The general wording already covers today's
named-byte-identical documents — `MILESTONE_WORKFLOW.md`,
`/milestone-implement.md`, `/accept-milestone.md`, `/review-functional.md`,
`/prepare-functional-review.md`, `/apply-functional-review.md`,
`PLAN_REVIEW_WORKFLOW.md`, `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`,
`review-plan.md` and `record-manual-plan-review.md` — and now also CP6's own
straggler fixes, without naming either set, since a named list is exactly
the pattern round 7 found short a fourth time (below). §4's
REQ-15 is restated to match the general rule rather than only the
plan-review-command-contract form, and gains CP1 to its checkpoint list
(for (b), (d) and (f)).

**Mechanical sweep, the documentation-layer counterpart of CP2's own
parametrized code test (resolves round 6's "Missing tests" item, assigned
to CP6; predicate and allowlist corrected at revision 8,
`LOCAL_MODEL_PLAN_REVIEW` round 7, finding B1(a)).** Four rounds running —
round 3 (phase sets), round 5 (four version gates), round 6 (three document
surfaces), round 7 (four more sites, found by running this very sweep by
hand) — a hand-enumerated list has been the right rule applied to a short
surface, and round 7 additionally found that the rule *as specified* would
not have caught most of its own sites: measured over
`distribution/workflow/2.4.0/payload/`, the dominant textual form is not the
two-element `{"1", "2.1"}` enumeration but a bare single-version scoping
assertion (`"2.1" only`, "Scoped entirely to `"2.1"`", "`"2.1"`-only", "on a
`"2.1"` item") that never mentions `"1"` at all — six of round 6's own nine
cited sites are this form, not the enumeration form.

CP6, already authoring `D-Review-Material-Lifecycle`'s own mechanical lint
over milestone-authored documents, additionally authors a lint over the
built release payload's own `.claude/commands/*.md` and
`docs/ai-workflow/*.md`, asserting that **no document presents a `"2.1"`
(or `{"1", "2.1"}`) governing-version reference as exhaustive of the
protocol's own applicability**. The lint's detection rule covers both
textual forms:

1. the `{"1", "2.1"}`-exhaustive-enumeration form (round 3/5/6's own
   pattern), and
2. the bare `"2.1"`-scoped-assertion form round 7 found dominant — any
   assertion that the two-stage plan-review protocol, or a command that
   implements it, is scoped to, only for, or exclusive to `"2.1"`, with or
   without `"1"` named beside it.

**Predicate scope, corrected at revision 9 (`LOCAL_MODEL_PLAN_REVIEW` round
8, finding I1): a negated or version-independence assertion is not an
occurrence of either form above at all — this narrows what the two forms
themselves match, it is not a third allowlist entry.** Neither form 1 nor
form 2 is meant to match prose that asserts the *opposite* of what the lint
flags: a sentence saying the mechanism is **not** scoped to, or is not
exclusive to, `"2.1"` (e.g. "this is not a `"2.1"`-only mechanism", "applies
uniformly") never claims exhaustiveness in the first place, so it was never
inside either form's own definition to begin with, and needs no separate
excuse. `docs/ai-workflow/MILESTONE_WORKFLOW.md:424` ("entry (either
governing version — this is not a `"2.1"`-only mechanism)") and
`.claude/commands/apply-functional-review.md:34` ("`D-Functional-
Remediation` applies uniformly, it is not a `"2.1"`-only mechanism") are
both this shape: correct as written, and neither is to be reworded by CP6's
catch-all below or added to the allowlist.

**Allowlist granularity, stated explicitly (round 7 also found the prior
"small, reasoned allowlist" description under-specified): the allowlist
operates at occurrence granularity within a document, not whole-document
grant, with exactly two exemption shapes** (the predicate-scope narrowing
above is not a third shape — it means the occurrence is never flagged at
all, so it needs no allowlist entry). First, an occurrence inside a
section explicitly classified `HISTORICAL` (`D-Review-Material-
Lifecycle`'s own convention, §2.4; **terminology corrected at revision 21**
from a heading-matched "disposition section" to the explicit classification
the architectural correction there introduces) is exempt, since that prose
is by definition about a past state of the design, not a current claim. Second,
a whole-document exemption applies to the **three** closed design/history
documents the lint's own stated scope (`docs/ai-workflow/*.md` in the built
payload) would otherwise reach and that legitimately narrate past releases
throughout: `WORKFLOW_V2_3_PLAN.md`, `WORKFLOW_V2_3_FOLLOWUPS_PLAN.md`, and
`WORKFLOW_V2_AUDIT.md` — each named explicitly in the allowlist, not
matched by a pattern, so a future closed document requires its own
deliberate addition rather than silently qualifying. **Narrowed at revision
16 (`LOCAL_MODEL_PLAN_REVIEW` round 15, finding B1) from the four documents
revision 15's own paragraph here still named — including `WORKFLOW_V2_PLAN.md`
— down to these three**: `WORKFLOW_V2_PLAN.md` is not a closed document;
§2.4 itself classifies it as the single *active* design-of-record, still
growing with every authored release's own CP1-style design checkpoint (this
milestone's own CP1 among them), so a whole-document grant would suppress
the sweep inside the very current/normative sections REQ-15 requires it to
cover, not only inside genuinely historical prose. This is the identical
narrowing revision 15 itself already made to CP6's registry entry and to
§6's sweep test entry (both of which already state three, not four) —
finding I2's own first half, from `MANUAL_EXTERNAL_PLAN_REVIEW` round 1 —
but revision 15's edit pass missed this paragraph, the allowlist's actual
design-of-record statement. `WORKFLOW_V2_PLAN.md`'s own occurrences are
therefore exempt only occurrence-by-occurrence, inside its own
sections explicitly classified `HISTORICAL` under `D-Review-Material-
Lifecycle`, identically to every other non-exempt document, never by the
file's name alone. No other
document, and no other occurrence, is exempt (the predicate-scope narrowing
above aside, which excludes an occurrence from matching in the first place
rather than allowlisting a match): the two exemption shapes above are
exhaustive of the allowlist. **Taken at revision 17 (`LOCAL_MODEL_PLAN_REVIEW`
round 16, optional finding O1):** a document's whole-document exemption is
conditional on no checkpoint in this milestone's own registry writing to it
— true and cheap for the current three: no checkpoint targets
`WORKFLOW_V2_3_PLAN.md`, `WORKFLOW_V2_3_FOLLOWUPS_PLAN.md`, or
`WORKFLOW_V2_AUDIT.md`, and `WORKFLOW_V2_PLAN.md` was the only allowlist
member any checkpoint ever targeted, exactly why it was dropped above — so
the next occurrence of this class is self-evident from the registry rather
than a sixth discovery.

**A second gap the allowlist as stated (through revision 8) did not reach,
closed at revision 9 (finding I1's second half):
`WORKFLOW_V2_1_OPERATOR_REFERENCE.md`'s own `## Known discrepancies`
section (`:841`) carries stale bare-`"2.1"` claims once `"2.2"` exists.**
**Citation, corrected at revision 10 (`LOCAL_MODEL_PLAN_REVIEW` round 9,
optional finding 3): `:882` and `:892` are item 4's and item 5's own
opening lines — round 8's own numbering convention, each item's first
line — not the lines the quoted sentences themselves sit on.** Item 4's
"a child created under this repository's own `default_workflow_version:
"2.1"` enters at `AWAITING_LOCAL_PLAN_REVIEW`" is at `:886-888`; item 5's
"a state a `"2.1"` item never occupies" is at `:894`. Both are stale
bare-`"2.1"` claims once `"2.2"` exists, and neither negates a `"2.1"`-only
claim, so the predicate-scope narrowing above does not reach them either.
`## Known discrepancies` catalogues live cross-document defects as current
claims, which is **not** material a document owner would explicitly
classify `HISTORICAL` under `D-Review-Material-Lifecycle` (**terminology
corrected at revision 21** to explicit classification; the distinction
itself, unchanged: a `HISTORICAL`-classified disposition section "names,
per revision and finding id, what was found, what changed, and why" about
*this* document's own history, while `## Known discrepancies` names live
discrepancies in *other* documents, not this document's revision history —
current, normative content, correctly left unclassified), so neither of the
allowlist's two shapes reaches it. **`## Known
discrepancies` is explicitly in the lint's scope**, and the fix is CP6's
own catch-all below, as items distinct from CP4's own named
`WORKFLOW_V2_1_OPERATOR_REFERENCE.md` items (`:21-24`'s overview,
`:229`/`:246`, and "phase and command tables"). **Extent, corrected at
revision 10, round 9, optional finding 1: the section's stale occurrences
are not limited to items 4 and 5.** Two further occurrences in the same
section are just as stale, of the identical bare-`"2.1"` shape: item 1's
"`workflow_state.py`: `"2.1"` → `AWAITING_LOCAL_PLAN_REVIEW`, `"1"` →
`AWAITING_EXTERNAL_PLAN_REVIEW`" (`:853-854`), an exhaustive `{"1", "2.1"}`
enumeration CP2's own widening of `publish_plan_revision` falsifies, and
item 3's "fields the `"2.1"` plan commands require" (`:866`), which the
`"2.2"` plan commands require identically. Both are inside CP6's catch-all
by construction, so no obligation is lost — CP6 fixes every stale
occurrence the section contains, not only items 4 and 5, and each restates
the `"2.1"`/`"2.2"` membership, `"1"` wording unchanged throughout.

**Which checkpoint widens a site the lint flags that CP1/CP4's own named
lists (below, and in their own registry entries) did not already cover:**
CP6 does, at lint-authoring time. The registry's own checkpoint list
already sequences CP6 after CP1 and CP4 (CP1 → CP2 → CP3 → CP4 → CP5 → CP6
in listed order, and CP6's `depends_on: [CP1]` permits running it any time
after CP1), so by the time CP6 authors and runs the lint, CP1's and CP4's
own named fixes (B1(b)-(e) below) already exist on disk; CP6 fixes,
in place, any further site its own lint output flags beyond those named
fixes, rather than either leaving the lint red or duplicating a fix CP1/CP4
already made. **Inside a pre-existing disposition section of
`WORKFLOW_V2_PLAN.md`, this catch-all's remedy is a `HISTORICAL` marker,
never a reword (added at revision 23, `LOCAL_MODEL_PLAN_REVIEW` round 22,
usability finding: rewording closed historical prose to satisfy this sweep
is exactly the harm `D-Review-Material-Lifecycle` exists to prevent, and
the enumerated carve-out above cannot be exact by construction, per finding
I3); the catch-all rewords a flagged site only when it is current,
normative material, never when it sits inside a section that is, or by this
same act becomes, explicitly classified `HISTORICAL`.** This is the
artifact that makes a fifth round on this class
unnecessary rather than merely unlikely, since it no longer depends on the
predicate matching the form a future site happens to use.

**CP12's own disposable-repo scenario additionally states explicitly the
step *between* its plan-stage traversal and its implementation-review-stage
traversal (resolves round 6's second "Missing tests" item)**: driving
`/milestone-implement`'s own checkpoint loop from `SELF_REVIEWING_IMPLEMENTATION`
(`[2.1 step 1]`'s resumable sequence and step 2's
`enter_self_reviewing_implementation` write, per (a) above) through to its
own `record_bundle_generation(stage="implementation")` call, asserting the
committed phase at `T` is `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` — so
`IllegalBundleGenerationSourcePhaseError` cannot first be discovered as a
live wedge at CP12 itself.

**Two optional findings taken from round 6, both cheap, both closing a
question this review history shows is easy to get wrong:**

- **`promote_legacy_work_item`'s docstring justification (corrected at
  revision 11, `LOCAL_MODEL_PLAN_REVIEW` round 10, finding I3: the function
  is `promote_legacy_work_item`, not `adopt_legacy_work_item` — a name that
  does not exist in this repository — the same class as revision 2's own
  I2, `build_rollback_config` → `build_rolled_back_config`)**
  (`scripts/workflow_state.py:12097-12101`) states the `"1"` → `"2.1"`
  promotion is "legal only because… the repository default is already
  `"2.1"`" — true only until `"2.2"` is activated as the default.**
  Behaviourally this is benign: adoption lands the item at
  `AWAITING_FUNCTIONAL_REVIEW`, past both implementation-review stages, so
  promoting a grandfathered v1 item all the way to `"2.2"` would buy
  nothing and would in fact wedge it (a `LEGACY_V1`-approved item at
  `"2.2"` whose functional bounded fix then routes into
  `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` with no
  `implementation_review_stages` ledger and no local reviewer pass would
  stall at `technical_approval_gate_reachable`'s new `"2.2"` check). Fix,
  assigned to CP3 alongside its own docstring corrections: legacy adoption
  deliberately promotes to `"2.1"`, never the current default, because the
  adopted item is already past both implementation-review stages — stated
  as one clause here and corrected in the docstring itself.
  `/prepare-functional-review.md:47-51` is the same fact's command-contract
  copy, already covered by (c) above.
- **`transition_to_awaiting_local_plan_review`'s own docstring
  (`scripts/workflow_state.py:11941`) calls itself "`/apply-plan-review`'s
  `"2.1"`-only revised exit step"** — the same docstring-staleness class as
  round 5's optional finding 3, one function over, in the same file CP2 is
  already editing to introduce `TWO_STAGE_PLAN_REVIEW_VERSIONS`. Fix,
  assigned to CP2: the docstring states the exit step is `"2.1"`/`"2.2"`
  alike, not `"2.1"`-only.

**One optional finding taken from round 7, one declined with repository
evidence:**

- **Declined: `scripts/workflow_fingerprint.py:1081`'s docstring, on the
  same class round 6's optionals 1-2 fixed elsewhere.** The finding's own
  premise — that CP9 already opens this module "for the `v2.3.1-003` mode
  fallback" — does not hold: `v2.3.1-003`'s fix is entirely in
  `pin_plan_approval_state_blob`, `scripts/workflow_state.py:3107` (verified
  directly against `docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`
  and the function's own location); no checkpoint in this plan, at any
  revision, opens `scripts/workflow_fingerprint.py` at all (`grep -c
  workflow_fingerprint` over revision 7's own registry/plan text returns
  zero hits outside the self-hosting note's byte-identity check). Taking
  the finding as stated would mean opening a new file surface in some
  checkpoint's declared scope for one docstring correction with zero
  behavioral effect — the finding's own text agrees "the function is
  version-independent in fact, so nothing behaves wrongly either way".
  Declined for this milestone; a future release touching this module for
  its own reason is free to take it then at no greater cost.
- **The next unknown governing version fails immediately and
  self-describingly, rather than three steps later.** Round 6 proposed, and
  explicitly declined to require, a one-line "any other governing version:
  refuse, naming it" default in each dual-mode command's own step 0.
  Adopted at round 7, now that a second inheriting version (`"2.2"`) exists
  and a further one (`"2.6.0"`, per this section's own
  `TWO_STAGE_PLAN_REVIEW_VERSIONS` reasoning) is anticipated: fix, assigned
  to CP4, alongside its own dual-mode command updates — every dual-mode
  command's step 0 branch set (`/apply-plan-review`, `/milestone-implement`,
  and this milestone's own new `/apply-implementation-review`,
  `/review-implementation` and `/record-manual-implementation-review`) gains
  an explicit "any other `governing_workflow_version`: refuse, naming it"
  final branch, so an item at a version none of the named branches match
  fails at step 0 rather than at whichever write happens to raise first.

**This work item's own governing version is unaffected**: it is created
under today's default, `"2.1"` (confirmed:
`docs/ai-workflow/WORKFLOW_CONFIG.json`'s `default_workflow_version` is
`"2.1"` at routing time), builds `"2.2"` for *future* work items, and does
not activate `"2.2"` as the repository default until CP1's design and
CP2–CP5's implementation are complete and reviewed (mirroring exactly how
`plan-amendment-mechanism`, itself `"2.1"`, built and shipped `2.4.0`
without needing `AMENDING_PLAN` for its own execution).

**Self-hosting note, recorded for the reviewer, not a blocker. Corrected
at revision 2 (`LOCAL_MODEL_PLAN_REVIEW` round 1, finding B2)** — revision
1 claimed this repository's own live installation was still pinned to
`2.3.1` and that `plan-amendment-mechanism`'s `2.4.0` had never been
installed here. That was false: the working tree's
`.workflow-manager/installation.json` already records `workflow_version:
"2.4.0"` (`updated_at: "2026-09-13T00:19:42Z"`, roughly half an hour
before revision 1's own bundle was generated) — the update is genuinely
installed, only **uncommitted** (`HEAD` still shows `2.3.1`). Verified
directly: `scripts/workflow_state.py`, `scripts/prepare-ai-review.sh` and
`scripts/workflow_fingerprint.py` in the working tree are byte-identical
to `distribution/workflow/2.4.0/payload/`, confirming the generator that
produced this item's own `implementation-review-two-stage-artifacts.json`
was already `2.4.0`, not `2.3.1`.

Two follow-on corrections this revision adopts:

- `.workflow-manager/` in this item's own plan-stage declaration was
  **not** added by hand — the installed `2.4.0` generator
  (`scripts/workflow_state.py`'s `generate_artifacts_declarations`)
  supplies `plan_stage_excluded_prefixes['.workflow-manager/']`
  automatically (its own `v2.4.0-001` fix). Diffing this item's own
  declarations file against a fresh `generate_artifacts_declarations`
  call shows exactly one hand-added key:
  `plan_stage.excluded_prefixes['docs/defects/']`. §7's bullets below are
  corrected to say so.
- The `2.4.0` fix widened only `plan_stage_excluded_prefixes` — it never
  touched the implementation-stage template. That is exactly what left
  `implementation_stage` unclassified for this item's own real deliverable
  footprint (finding B1, fixed at this same revision in
  `implementation-review-two-stage-artifacts.json`), which means this item
  genuinely *is* exposed to `v2.4.0-001`, at the implementation stage — the
  opposite of what revision 1's §8 claimed. §8 below adopts the defect's
  own preferred mitigation #1 explicitly: do not commit
  `.workflow-manager/installation.json` while this work item is mid-flight
  (add it to a local, uncommitted `.git/info/exclude` rather than staging
  it in any checkpoint commit); mitigation #2 (an item "whose declarations
  file predates this fix" and whose repository "already committed" the
  file inside a live interval) does not apply here, since this item's
  declarations file was generated *by* the fix, not before it.

Authoring `migration/overlays/2.5.0/` against the (unmodified)
`distribution/workflow/2.4.0/` base is independent of any of this — the
overlay tooling operates on the base tree already committed on disk, not
on whatever release this repository happens to have installed for its own
use — and this work item's own `governing_workflow_version: "2.1"`
capability (`AWAITING_LOCAL_PLAN_REVIEW`/`AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`)
is already present in the currently-installed `scripts/workflow_state.py`,
so nothing about this milestone's own plan-stage execution is blocked by
the self-update. Whether and when to *commit* that already-installed
`2.4.0` self-update (as its own reviewed change, separate from this
milestone, or reverted) is an operator decision this plan does not make on
its own authority (`CLAUDE.md`'s "Don't touch unrelated working-tree
changes") — it should be settled one way or the other before CP2 begins,
so that CP2's own checkpoint commit does not sweep in ~5,700 lines of
unrelated, already-reviewed-elsewhere content. Self-updating this
repository's own installed copy is, independent of that housekeeping,
still explicitly out of this milestone's scope (narrow-scope instruction).

### 2.3 Convergence and token-efficiency scope for the two-stage implementation-review mechanism (narrow)

Interpreting the user's "reduce review-apparatus churn / improve review
convergence and token efficiency" instruction narrowly, as three concrete,
already-implied-by-the-mirror properties plus one measurable addition —
not a broader redesign:

1. **No bundle regeneration between the local-approve and
   manual-external stages** — the same bundle, `bundle_id`, and
   `review_content_id` the local stage approved is what the user uploads;
   nothing regenerates in between (mirrors the plan side, which already
   has this property structurally). Stated explicitly and tested (CP5),
   since it is easy to accidentally regress by adding a bundle-refresh
   step where none belongs.
2. **A single reviewer pass can no longer, by itself, exhaust a
   manual-external review round on an issue the local pass would have
   caught for free** — this is the entire point of the split (§1), stated
   here as the measurable convergence claim: fewer manual-external rounds
   spent on locally-catchable defects.
3. **`/review-implementation`'s independent-verification bar, for `"2.2"`
   items, must be at least as rigorous as today's combined
   `SELF_REVIEWING_IMPLEMENTATION` self-review plus the existing advisory
   pass** — since it now gates real state, not just advisory feedback, its
   own contract must not be weaker than what already exists today (CP4/CP5).
4. **One disposable-repo fixture (CP5/CP12) plants a realistic defect and
   demonstrates the local stage catches it without ever reaching the
   manual-external stage** — concrete evidence the split does what §1
   claims, not just a structural argument. (**Corrected at revision 5,
   `LOCAL_MODEL_PLAN_REVIEW` round 4, finding I1** — same stale "CP7"
   cross-reference as above; CP5 genuinely carries this fixture scenario,
   CP12 is the disposable-repo checkpoint.)

Explicitly **not** in scope for §2.1-§2.3: compacting `REVIEW_PROTOCOL.md`/
`MILESTONE_WORKFLOW.md` prose, restructuring the bundle file format, or
any other broader documentation/readability change. §2.4-§2.7 below are the
milestone's own, separately-scoped answer to the user's broader
review-scalability and post-v2.3.1 instruction (added at revision 3); they
do not reopen this exclusion.

### 2.4 D-Review-Material-Lifecycle — separating current normative review material from closed/immutable history

**Added at revision 3**, per the user's roadmap correction's "review
scalability / convergence improvements" branch, first bullet.

**Concrete evidence the problem is real, not hypothetical, gathered from
this repository directly rather than assumed:**

- `docs/ai-workflow/WORKFLOW_V2_PLAN.md` is 35,008 lines. It is the single
  design-of-record document for every `"1"`/`"2.1"` design decision this
  repository has ever made, spanning `workflow-v2-1-core`'s own original
  salvage/repair effort through `plan-amendment-mechanism`'s `2.4.0` work,
  and it grows with every future authored release's own CP1-style overlay
  design-doc checkpoint (this milestone's own CP1 is about to add to it
  again).
- `docs/ai-workflow/audit/WORKFLOW_DEFECT_LEDGER.md` (3,241 lines),
  `WORKFLOW_REPAIR_PLAN.md` (809 lines), `WORKFLOW_SYSTEM_AUDIT.md` (1,205
  lines) and `WORKFLOW_ACCEPTANCE_MATRIX.md` (384 lines) are, by their own
  content, a closed record: every ledger entry in
  `WORKFLOW_DEFECT_LEDGER.md`'s summary table is `FIXED`, `ACCEPTED`,
  `SUPERSEDED` or `CLOSED` — none is open — for a salvage effort
  (`workflow-v2-1-core`'s own bootstrap) that finished before either work
  item this repository's own `WORKFLOW_STATE.json` has ever tracked
  (`plan-amendment-mechanism`, `implementation-review-two-stage`) began.
  `docs/ai-workflow/archive/` and `docs/milestones/` — both named as
  destinations in this and other work items' own generic
  `*-artifacts.json` templates — do not exist in this repository at all
  (verified: neither path resolves). Nothing here is currently misfiled by
  any existing rule's own standard — every other work item's plan/
  implementation classification already excludes the whole
  `docs/ai-workflow/` prefix by default (verified against this item's own
  `implementation-review-two-stage-artifacts.json`), so this closed
  material is not today being re-hashed into any other work item's
  `review_content_id`.
- The concrete, currently-live churn source is narrower and closer to
  home: **within a single work item's own plan document, revision-over-
  revision corrective narrative accumulates inline in the same sections
  that state current, normative design**, rather than in any
  separately-labelled history. This very document is the direct example:
  revision 2 carried "Corrected at revision 2, finding X" prose inline
  inside §2.1, §2.2, §7 and §8's *normative* text, and revision 3 (this
  revision) has just added more of the same in the same places (the B1(a)/
  B1(b) resolution and the I1/I2 corrections above). Every future reviewer
  of the *current* design must first separate "what is true now" from
  "what used to be claimed and was corrected" by reading the same
  interleaved prose, and a correction's own justification remains
  permanently load-bearing text even once the plan reaches
  `AWAITING_PLAN_APPROVAL` and stops changing.

**Decision: no physical move of existing repository content this
milestone.** Nothing above requires relocating `WORKFLOW_V2_PLAN.md` or
`docs/ai-workflow/audit/*.md` to achieve semantic separation, and no
prior repository analysis in this design supports a specific
active/completed/archive folder scheme for them — forcing one now would be
exactly the kind of physical-layout redesign the user asked not to force
absent that support. This milestone therefore leaves `WORKFLOW_V2_PLAN.md`
and `docs/ai-workflow/audit/*.md` at their current paths, undisturbed, and
performs no `workflow_manager update` path-migration mechanism (there is
nothing to migrate). This is a deliberate scope boundary, not an oversight:
a future release remains free to introduce a physical
current/closed-history split if a later milestone's own repository
analysis supports one, using whatever safe, fail-closed, idempotent,
reusable migration mechanism that milestone designs.

**What this milestone does add — a lightweight, mechanically-checkable
convention for review documents going forward, piloted on this plan's own
§7/§8 (revision 4 correction, `LOCAL_MODEL_PLAN_REVIEW` round 3, optional
finding 1; enumeration widened to include §2.4 at revision 24,
`LOCAL_MODEL_PLAN_REVIEW` round 23, optional finding O3: §2.4's own points 2
and 3 have carried the same inline disposition narrative since revision 21
and gained more at revisions 22 and 23, so the enumeration was incomplete
for the third consecutive round):** §2.1/§2.2/§2.4's own normative text
still carries inline
"Corrected at revision N, finding X" justification load-bearing for the
current design (round 3's own honest admission, restated below rather than
retracted, since retracting it would itself violate point 1 by pretending
the disposition history was never inline there) — the pilot is therefore
true of §7/§8 only, not of every normative section. The convention binds
going forward to CP1/CP6's own overlay-authored documents
(`WORKFLOW_V2_PLAN.md`, `IMPLEMENTATION_REVIEW_WORKFLOW.md`) — concretely,
to the *new* material those documents gain from this milestone onward, and
to any pre-existing section CP6 explicitly marks under point 3's carve-out
below, never to `WORKFLOW_V2_PLAN.md`'s pre-existing, unmarked content
wholesale (point 3's own subject-scope statement below states this once,
for every guarantee) — not
retroactively to this plan's own §2.1/§2.2, which stops changing once this
plan reaches `AWAITING_PLAN_APPROVAL` and is not itself one of the
documents CP6's lint checks (**scope stated explicitly at revision 23**,
`LOCAL_MODEL_PLAN_REVIEW` round 22, finding I1: revision 22 named the whole
document here while stating "new sections" at §6 and evaluating pre-existing
content at guarantee (v) below — three incompatible readings of the same
convention, one of which made guarantee (vi) unsatisfiable):

1. **Normative text states only the current design.** A plan or design
   document's substantive sections (e.g. `WORKFLOW_V2_PLAN.md`'s
   `D-*`-numbered decisions, this plan's own §2.1-§2.7) describe the
   design as it stands today, without embedding "revision N corrected
   finding X" narrative inline as load-bearing justification for why the
   current text is correct — the current text should stand on its own
   evidence.
2. **A disposition record, explicitly classified `HISTORICAL`, carries the
   provenance.** Each such document keeps (or gains) one or more
   clearly-labelled disposition sections — this plan's own §7
   (`SELF_REVIEWING_PLAN` notes) already plays this role informally, one
   section per review round — that name, per revision and finding id, what
   was found, what changed, and why, so the history remains available
   without being repeatedly re-treated as current semantic review surface.
   **Corrected at revision 21** (`LOCAL_MODEL_PLAN_REVIEW` round 20, finding
   I3: revision 19-20's "one clearly-marked section" was false for
   `WORKFLOW_V2_PLAN.md`, which already carries 89 per-round disposition
   headings, not one — corrected from "83" at revision 22,
   `LOCAL_MODEL_PLAN_REVIEW` round 21, optional finding O1: 83 is only the
   `##`-level subset of the `^#+ .*[Dd]isposition` match set; 89 is the
   full count the "many, not one" argument actually needs, since round 21's
   own finding I5 established that at least one of the 6 `###`-level
   matches is itself a genuine disposition-section heading, not an
   incidental one): a document may carry several disposition sections;
   what the convention requires is that provenance narrative live only in
   sections explicitly classified `HISTORICAL` under point 3 below, never
   that there be exactly one such section. Where a checkpoint's own
   deliverable needs a single, determinate destination for new provenance
   entries (CP1's carried subsection below is the concrete case), that
   checkpoint names the specific disposition section it adds to or creates,
   explicitly classified `HISTORICAL`, rather than relying on any document
   having a unique pre-existing one. CP6 formalizes the classification
   itself as an explicit, named convention (`D-Review-Material-Lifecycle`)
   in the overlay's `WORKFLOW_V2_PLAN.md`, rather than leaving it as this
   plan's own ad hoc §7/§8 practice.
3. **A mechanical check, not merely a style guideline — stated at revision
   21 as explicit lifecycle classification, replacing the heading/prose
   inference design of revisions 15-20.** (User-directed architectural
   correction, applying together with `LOCAL_MODEL_PLAN_REVIEW` round 20's
   own convergence recommendation, which independently reached the same
   conclusion from the review side. Full history of revisions 15-20's
   heading/prose-inference approach, and why six consecutive local-model
   rounds each found the next way it failed to converge, is retained as
   history at §7's revision-21 disposition entry — this point states only
   the current design.)

   Lifecycle status — whether a unit of review material is current,
   normative design content or a closed, provenance-only historical
   record — is a **semantic** property of that content, decided by its
   author. It is not a syntactic property inferable from a heading's
   wording, a heading's level, a section's position in the document, or any
   other incidental structural or textual feature. CP6 accordingly defines
   `D-Review-Material-Lifecycle` around **explicit classification**, not
   inference. **Standing invariant, stated once here as the test future
   prose in this section must pass (added at revision 28, optional finding
   O3/architecture note; user-directed architectural correction): no
   statement in this convention derives a marker's presence, value, or
   scope from authorship, novelty, or a cross-corpus comparison; every such
   statement instead names a region of a named tree (a document, a
   registry-established section, or a unit the marker itself identifies).**
   Rounds 24-27 each found a different violation of this invariant —
   authorship-scoped presence ("this milestone's own authored/marked
   units"), novelty-scoped presence ("present in the overlay and absent
   from the base"), a presence obligation misapplied to the wrong
   guarantee's domain, and, most recently, authorship used to derive a
   marker's *value* ("`CURRENT` markers on new material CP1 authored") and
   authorship used to bound the presence obligation's own *extent* ("the
   sections CP1's own registry entry adds") — retired in turn below and at
   guarantee (vii) above; this sentence exists so the next one is caught at
   plan-review time rather than needing an eighth round to name it:

   - **Two explicit states.** Every unit of review material this
     convention applies to (a document, a section, or a finer grain CP6's
     implementation chooses) is classified either `CURRENT` — current,
     normative, review-visible design material — or `HISTORICAL` — a
     closed, provenance-only record of a past decision or review round,
     retained for reference but no longer active review surface. This
     classification is stated by an explicit marker the author writes.
     Nothing about a heading's text, level, or position is itself evidence
     of either state.
   - **Fail-closed default.** A unit with no explicit marker, or with a
     marker the mechanical check cannot unambiguously parse, is `CURRENT`.
     Classification can therefore only *narrow* what a reviewer sees (by an
     explicit, deliberate `HISTORICAL` marking); it can never silently
     *widen* what a reviewer does not see. This is the convention's central
     safety property: an implementation under which ambiguous or
     unclassified material ever reads as `HISTORICAL` fails the guarantee,
     full stop, not an acceptable edge case to be refined later.
   - **`CURRENT` -> `HISTORICAL` is an intentional transition of
     *material*, never a side effect of any edit (corrected at revision 22,
     `LOCAL_MODEL_PLAN_REVIEW` round 21, finding I3: stating the invariant
     over *units* left the unsafe merge direction open — see the disposition
     entry below).** No edit that does not itself change an explicit
     marker's value may move any material from `CURRENT` to `HISTORICAL` —
     whether by changing the marker on the unit that material already
     belongs to, or by changing *which* unit that material belongs to at
     all (for example, merging a `CURRENT` region into an adjacent
     `HISTORICAL`-marked unit by deleting or demoting the heading between
     them, with no marker edit anywhere in the diff). Unit boundaries are
     themselves part of what the marker governs, not a free variable outside
     the guarantee's reach. Editing a heading's wording or restructuring
     prose, without moving any material across a unit boundary and without
     changing a marker, never changes that material's classification. The
     only way material becomes `HISTORICAL` is a deliberate marker edit (on
     its own unit, or an edit that redraws a boundary and writes the marker
     in the same diff). A `HISTORICAL` unit may still be corrected in place
     as historical record-keeping, per point 4 below, without that
     correction itself re-promoting its material to `CURRENT` —
     re-promotion is likewise only ever an explicit, intentional marker
     edit, never incidental to any other change.
   - **Classification authority is separable from the prose being
     classified.** The mechanical check must be able to determine a unit's
     classification without parsing or pattern-matching the normative prose
     itself — the marker is machine-checkable on its own terms, independent
     of what the surrounding text says. This plan does not prescribe the
     marker's concrete representation (a delimited metadata block, a
     structured comment, or any other mechanism written directly into the
     tree the guarantees below read — **narrowed from "...a structured
     comment, a sidecar declaration, or any other mechanism" at revision 30**,
     `LOCAL_MODEL_PLAN_REVIEW` round 29, optional finding O1: a sidecar
     declaration is by construction not "in the tree" the structural note
     below and rows (v)/(vii)/Carve-out/Corpus regression of the table below
     each read, nor "of that tree" as guarantee (v)'s own verdict is now
     stated; CP1's required marker instance already lives inside
     `WORKFLOW_V2_PLAN.md` itself, as part of the disposition-record
     subsection §2.1 requires there, never beside it, so a sidecar was never
     actually a live choice once §2.1 fixed where CP1 writes that marker).
     **The representation, and its exact syntax and delimiters, are fixed by
     CP1, as part of CP1's own deliverable, no later than CP1 writes the
     first marker any checkpoint writes — the disposition-record
     subsection's own `HISTORICAL` marker (§2.1) — since that marker cannot
     be written in a representation that does not yet exist, and CP6 runs
     after CP1 in the registry's own checkpoint order (corrected at revision
     29, `LOCAL_MODEL_PLAN_REVIEW` round 28, finding B1, resolution 1: CP6
     cannot be the one to choose a representation that CP1's own required
     deliverable already depends on). The lint that runs the parser, and
     every guarantee below, remain CP6 implementation decisions, exactly as
     before — only the choice of the representation itself, and (per this
     point's own revision-32 paragraph below) the parser that reads it,
     move one checkpoint earlier (narrowed at revision 33,
     `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2, from "The parser that
     reads that fixed representation, the lint that runs it, and every
     guarantee below remain CP6 implementation decisions, exactly as
     before").**
     **A single canonical representation source — never one written
     instance alone — is the specification (revised at revision 32,
     `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I2, replacing revision
     30's "CP1's own single written instance of this representation is
     itself the specification").** One concrete `HISTORICAL` instance fixes
     its own literal bytes, but it does not by itself determine which part
     of those bytes is the state-valued slot, nor the complete accepted form
     of the representation's second state, `CURRENT` — an instance is a data
     point a grammar could be inferred from, not the grammar itself, and
     two different inferences ("same representation" means exact bytes;
     "same representation" means a template with a substitutable state
     slot) are equally consistent with one instance alone. CP1 therefore
     fixes the representation, as part of the same deliverable revision 29
     already assigns it and no later than the first marker any checkpoint
     writes, as one canonical, machine-readable render/parse definition —
     not a written marker instance alone, and not a second, hand-maintained
     prose grammar either (a `render_marker(state)` / `parse_marker(text) ->
     state | None` function pair, or an equivalent single machine-readable
     definition, is the concrete shape; the exact function names and module
     remain a CP1 implementation choice, exactly as the syntax and
     delimiters already were). That definition's own state parameter/return
     type is restricted to exactly the two-member domain `{CURRENT,
     HISTORICAL}` — the "Two explicit states" contract this point already
     states informally now has one determinate, machine-checkable location,
     rather than being inferable only from whichever one instance CP1
     happens to write. CP1 writes its own required `HISTORICAL` marker
     (§2.1's disposition-record subsection) by calling this same
     `render_marker`, rather than hand-typing the marker's bytes
     independently of it, so CP1's own instance is a *product* of the
     canonical definition, never a second, competing source of truth for
     it — CP1 is still not required to record the syntax in any further
     hand-written artifact beyond this one machine-readable definition.
     CP6 imports and reuses the identical `render_marker`/`parse_marker`
     pair for every marker it writes (§6's marking pass) and for its own
     lint's parsing — never a second, independently-derived regex or
     grammar tolerating a form the canonical pair does not itself produce
     or accept. Binding both CP1's write and CP6's write/read to one shared
     definition is what "same representation" means: exact bytes for a
     fixed state argument, since the render function is deterministic, and
     the shared template/state-slot structure for "conforms to the
     representation" generally — both readings are now properties of the
     one function pair rather than competing interpretations of one
     example. The representation-conformance fixture below (CP6) is widened
     accordingly (resolves `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding
     I2's own required test): it exercises the canonical pair directly —
     `parse_marker` accepts `render_marker("HISTORICAL")`'s own output as
     `HISTORICAL`, accepts `render_marker("CURRENT")`'s own output as an
     *explicit* `CURRENT` marker (distinct from the fail-closed default a
     missing marker also classifies `CURRENT` — the already-marked-nested-
     unit and marker-presence fixtures below cover that distinction), and
     rejects representative malformed/out-of-contract forms (a mutated
     delimiter, a third state value, truncated or duplicated marker text)
     back to the `CURRENT` fail-closed default. CP1's own written instance
     and every marker CP6's marking pass writes are required to equal
     `render_marker`'s own output bytes for their respective state — a
     mechanical equality check, not a second grammar comparison — so drift
     between what CP1 wrote and what CP6 later writes is a fixture failure
     rather than an assumption, which is what then lets the real-corpus
     marker-presence run (§6) — already required for guarantee (vii) —
     catch a CP6 writer that has drifted onto a second, tolerated form.**
   - **"Review-visible surface" names the check's own `CURRENT`/
     `HISTORICAL` partition, nothing else (added at revision 22,
     `LOCAL_MODEL_PLAN_REVIEW` round 21, finding I4: the term was used in
     four places below without ever being defined, and without naming what,
     if anything, it excludes material from).** The check computes, for
     each unit, which side of that partition it falls on, and reports it —
     "review-visible" means the `CURRENT` side, "excluded from
     review-visible surface" means the `HISTORICAL` side. The term names no
     other exclusion: not from `review_content_id`'s own computation, not
     from `<bundle_dir>/PLAN.md` or the bundle's `files/`, not from a human
     reviewer's actual reading list — none of those is a consumer of this
     classification, and this milestone adds none. A marker edit therefore
     never stales a plan or technical approval by itself, consistent with
     §5's "Review-scalability branches (CP6-CP8) change no runtime
     state-machine behavior" bullet below; it only moves material between
     the two reported sides of the check's own partition.
   - **The convention's subject scope — stated once, here, for every
     guarantee below (added at revision 23, `LOCAL_MODEL_PLAN_REVIEW` round
     22, finding I1: revision 22 stated three incompatible scopes for the
     same convention — the whole document at this section's own binding
     sentence above, "new sections" at §6, and pre-existing content
     evaluated at guarantee (v) below — leaving guarantee (vi) unsatisfiable
     under the first reading, since 22 of `WORKFLOW_V2_PLAN.md`'s 25
     pre-existing `### D-*` current-design sections already carry the
     narrative guarantee (vi) forbids).** Three different things need a
     scope, and they are not the same scope:
     - **What guarantee (vi) governs** (the narrative-content prohibition):
       only units this milestone itself authors or explicitly marks —
       `IMPLEMENTATION_REVIEW_WORKFLOW.md` in full, `WORKFLOW_V2_PLAN.md`'s
       new sections (CP1's own carried subsection among them), and any
       pre-existing `WORKFLOW_V2_PLAN.md` section CP6 deliberately marks
       under the carve-out below. **The mechanical basis for that
       membership, stated once here (added at revision 24,
       `LOCAL_MODEL_PLAN_REVIEW` round 23, finding I1: revision 23 stated
       this scope as a fact about authorship — "units this milestone itself
       authors or explicitly marks" — which is not a property the check can
       read; composed with guarantees (ii)/(iii) and the separability
       guarantee, the scope fixture and the narrative-location fixture ended
       up describing the same unmarked input while demanding opposite
       verdicts, with no marker, heading feature or prose difference between
       them to justify it):** a unit is within guarantee (vi)'s reach
       exactly when it carries an explicit `CURRENT` marker; a unit that
       classifies `CURRENT` only by point 2's fail-closed default — because
       it carries no marker at all — is outside guarantee (vi)'s reach. This
       is a property of the marker alone, so it costs nothing against
       guarantee (ii) (still no dependence on heading wording, level or
       position), guarantee (iii) (an unmarked unit still classifies
       `CURRENT`; it is merely outside guarantee (vi)'s reach, never
       reclassified) or the separability guarantee (the check still reads
       only the marker, never the prose): this milestone's own
       authored/marked units carry explicit markers by guarantee (vii)'s own
       presence obligation below together with CP1's own marker-writing
       obligation (§2.1) and CP6's own marking pass (§6) — never by point 1's
       normative-text convention, which is not one of the guarantees CP6
       must prove and has no fixture pinning it (**repointed at revision 29**,
       `LOCAL_MODEL_PLAN_REVIEW` round 28, finding I2: the sub-bullet below
       has called this citation "prior" since revision 25 without the
       citation itself ever being repointed — the last unretired instance of
       the authorship-derived-presence class the standing invariant above
       exists to catch) — and `WORKFLOW_V2_PLAN.md`'s pre-existing sections
       carry none, until CP6 deliberately marks one under the carve-out
       below. Guarantee
       (vi) is **not** asserted over `WORKFLOW_V2_PLAN.md`'s pre-existing,
       unmarked sections; an unmarked pre-existing section carrying the
       forbidden narrative is not a fixture failure — it is `CURRENT` only
       by the fail-closed default, and therefore outside guarantee (vi)'s
       reach by the basis just stated — proved by the scope fixture below.
       This is what §6's "new sections" phrasing and this section's own
       "binds going forward" sentence above both mean, restated here to
       agree.
     - **What the corpus regression asserts** (below): a narrower, different
       property over the *whole* existing corpus — that introducing the
       check reclassifies no unmarked pre-existing unit `HISTORICAL`
       (guarantee (v)'s own classification partition) — never guarantee
       (vi). The regression run proves the check is safe to introduce; it
       does not extend guarantee (vi)'s reach.
     - **What obligates a unit to carry a marker at all** (added at revision
       25, `LOCAL_MODEL_PLAN_REVIEW` round 24, finding I1: guarantee (vi)'s
       reach above is a property of the marker once written — it does not by
       itself say which units must write one, and the scope statement's
       prior appeal to "this milestone's own authored/marked units carry
       explicit markers by the first bullet above" cited point 1's
       normative-text convention, which is not one of the guarantees CP6
       must prove, has no fixture pinning it, and is itself scoped by
       authorship — exactly the kind of fact the check cannot read that this
       section exists to eliminate). A distinct, mechanically-evaluable
       obligation, separate from guarantee (vi)'s reach above and from
       guarantee (iii)'s classification default, over exactly two subjects:
       - **`IMPLEMENTATION_REVIEW_WORKFLOW.md`** — a document this milestone
         authors in full (CP1's registry entry): the subject is the whole
         document. Every unit of review material in it must carry an
         explicit marker; a missing marker anywhere in it is a lint failure.
       - **`WORKFLOW_V2_PLAN.md`** — scoped to an **enumerable** set, not a
         diffed one (**resolution 1, corrected at revision 26**,
         `LOCAL_MODEL_PLAN_REVIEW` round 25, finding I3: a cross-corpus
         "present in the overlay and absent from the base" predicate cannot
         decide unit identity for exactly the unmarked units this obligation
         is about — unit boundaries are themselves part of what the marker
         governs, not a free variable outside the guarantee's reach, per the
         transition bullet above, so neither corpus's units carry a marker
         that could establish "the same unit in both corpora"; the
         revision-25 fixture this predicate required — the same unit,
         unmarked, present in both fixtures, must pass — was therefore not
         constructible from anything this plan named): the subject is
         every top-level design section **any checkpoint's own registry
         entry** adds to the overlay's `WORKFLOW_V2_PLAN.md` — today CP1's
         `D-Implementation-Review-Stages` and
         `D-Implementation-Review-Version-Activation`, and CP6's own
         `D-Review-Material-Lifecycle` (§2.4 itself) — each in full
         (**widened from "the top-level design sections CP1's own registry
         entry adds" to "any checkpoint's own registry entry", at revision
         28, user-directed architectural correction applying together with
         `LOCAL_MODEL_PLAN_REVIEW` round 27's finding I2: scoping by which
         checkpoint happens to have authored a section left the one section
         that defines this convention — CP6's own — outside the obligation
         it defines; a registry entry remains the enumeration mechanism
         either way, so the "enumerable, not diffed" property this
         resolution establishes is unchanged**). Every unit of review
         material inside those sections must carry an explicit marker of
         **either value**; a missing marker anywhere inside them is a lint
         failure. Each checkpoint's own registry entry is what establishes
         that its section exists at all, so no cross-corpus matching is
         needed to decide it is "a unit" or "the same unit" — presence
         inside one of the named sections is a property readable directly
         off the one tree the obligation now names, never a comparison
         against a second one. A nested unit inside one of these sections —
         the `2.5.0`-scoped disposition-record subsection CP1 creates under
         `D-Implementation-Review-Stages` (§2.1) is the concrete case this
         milestone's own corpus contains — is not a separately enumerated
         member of this scope: it is reached once, as part of its
         container's "in full" reach, and its own explicit marker (whatever
         value the author gave it) independently discharges the obligation
         for it, exactly as guarantee (vii) states (**resolution to round
         27's finding B1/I1 at revision 28**: naming the disposition record
         as a third, separately-enumerated peer of the two `D-*` sections
         was both descriptively wrong — it is nested inside the first, not a
         peer — and the proximate cause of B1's direct marker-value
         conflict; dropping the separate enumeration removes both defects at
         once, without needing a carve-out or an exception clause, because
         presence is satisfied per-unit regardless of nesting). Which
         finer-grained units exist inside each in-scope section, beyond the
         section itself and any nested unit the author has already given an
         explicit marker of its own, is CP6 implementation's own mechanical
         decision, proved by the fixtures and real-corpus regression below,
         never enumerated in this plan's prose.

       This obligation is orthogonal to guarantee (iii): an in-scope unit
       with no marker still classifies `CURRENT` under (iii)'s fail-closed
       default — classification is unaffected — and independently fails
       this obligation (guarantee (vii) below), because it is in scope for
       the obligation and carries no marker. Which value — `CURRENT` or
       `HISTORICAL` — a marked unit's marker carries is never decided by
       this obligation: it is decided by the unit's own author, subject to
       guarantee (iii)'s fail-closed default and guarantee (vi)'s
       `CURRENT`-material content rule, never by this obligation inferring a
       value from who wrote the unit, whether it is new, or which named
       section or milestone it belongs to (**stated explicitly at revision
       28**, user-directed architectural correction: this presence/value
       separation is what closes the recurring authorship/novelty-derived
       defect class rounds 24-27 each found a new instance of). The two
       verdicts — classification and presence — are computed and reported
       separately, one classification-shaped, one presence-shaped, so
       proving either never disturbs the other's fixtures — in particular,
       the ambiguous fixture's own `CURRENT` classification verdict for
       unmarked material is untouched.

     Nothing above reopens the redesign: all three are properties of the
     explicit-classification mechanism already specified, stated together
     in one place instead of once per guarantee.
   - **Guarantees the mechanical check must prove**, whatever
     representation CP1 has fixed (**corrected at revision 29**,
     `LOCAL_MODEL_PLAN_REVIEW` round 28, finding B1, resolution 1: the
     representation is now fixed by CP1, not chosen by CP6 — see the
     separability bullet above):
     (i) every document this convention names is fully classified into
     `CURRENT`/`HISTORICAL` by the check's own predicate, with no third
     outcome besides the fail-closed default;
     (ii) the verdict never depends on heading wording, heading level, or
     any other incidental textual/structural feature — only on the
     explicit marker;
     (iii) a unit with no marker, or an unparseable/ambiguous one, is
     `CURRENT`;
     (iv) a `CURRENT` -> `HISTORICAL` transition of material is visible in
     the diff that performs it (the marker changes, whether on the unit
     material already belongs to or on a redrawn boundary per the
     transition bullet above), and no other diff shape produces that
     transition;
     (v) running the check against
     `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
     — the tree CP1 and CP6 both author directly, on disk at CP6 time — **as
     it stands the moment before CP6's own marking pass** (**anchor restated
     at revision 29**, `LOCAL_MODEL_PLAN_REVIEW` round 28, finding I1:
     "before CP6 adds any marker to it" mischaracterized the state it named
     — CP1's own required deliverable (§2.1) already writes an explicit
     `HISTORICAL` marker into this exact tree, at CP1 time, before CP6 runs
     at all, so CP6 does not add the tree's first marker, CP1 does) (**corpus
     named explicitly at revision 26**, `LOCAL_MODEL_PLAN_REVIEW` round 25,
     optional finding O2: "existing, already-committed content today" named
     no tree that exists today; **restated as the pre-marking half of a
     two-state read at revision 27**, `LOCAL_MODEL_PLAN_REVIEW` round 26,
     finding I3: revision 26's own parenthetical here said the regression
     proving this guarantee does not itself use this pre-marking state, and
     the clause it sat inside then named exactly this state for what the
     table below labelled "the same tree as (v)" — CP6 reads this one tree
     twice, not once: pre-marking, here, for this guarantee's own verdict;
     post-marking — after CP6 has made its carve-out-bound markings — for
     the corpus regression and the carve-out-bound fixture below, both
     restated accordingly at the table and at §6's lifecycle-lint bullet;
     "CP6's single run over this overlay-payload tree" below means never a
     *second* run against the built `distribution/workflow/2.5.0/` payload,
     never "once, in total, across both this guarantee and the regression"),
     classifies **every unit of that tree carrying no explicit marker of its
     own** `CURRENT` under the fail-closed default (**narrowed from "that
     content" — the whole tree — at revision 29**, finding I1: at that same
     moment the tree already carries CP1's own disposition-record
     subsection, explicitly marked `HISTORICAL` by CP1's own deliverable —
     §2.1 — which correctly classifies `HISTORICAL`, not `CURRENT`, and is
     therefore outside this guarantee's own verdict, never a counterexample
     to it; the already-marked-nested-unit fixture's own premise — "an
     in-scope unit already carrying an explicit `HISTORICAL` marker written
     by an earlier checkpoint" — describes exactly this same unit at this
     same moment, and now agrees with this guarantee's own wording instead
     of contradicting it. **This narrowed form is pinned by the
     pre-marking-partition fixture below, not by this real corpus alone
     (corrected at revision 30, `LOCAL_MODEL_PLAN_REVIEW` round 29, finding
     B1, resolution 2: revision 29's own claim that this narrowed assertion
     was itself the required regression named no run this plan requires to
     be green — the real-corpus state the claim depended on, this tree as it
     stands before CP6's own marking pass, stops existing in the worktree
     the moment CP6 completes, so a future edit that re-widens this
     guarantee back to `CURRENT` over the whole tree would break no check
     the real corpus alone could still run against; missing test 1 of round
     29's finding B1, below, is the fixture that closes this).** The
     real-corpus observation itself remains true, once, at CP6
     implementation time: an implementation that widens the assertion back
     to `CURRENT` over the whole tree, CP1's marked subsection included,
     fails against this exact real corpus, since that subsection's own
     explicit marker classifies it `HISTORICAL` — but it is the
     pre-marking-partition fixture below, constructed to survive CP6's own
     marking pass, that pins the narrowed form against a future re-widening,
     never this one-shot real-corpus reading), so no
     pre-existing, unmarked unit needs an
     explicit marker **for the lifecycle check
     itself to be valid** — a distinct fact from the sweep's own separate,
     deliberate marking obligation (§6), bounded by the sweep's own flagged
     output rather than enumerated, under which CP6 marks
     specific pre-existing sections `HISTORICAL` as part of its own required
     deliverable **(corrected at revision 23, `LOCAL_MODEL_PLAN_REVIEW`
     round 22, finding I2: this guarantee's own "never required to
     retroactively annotate the existing document" wording and §6's marking
     obligation stated opposite facts about the same document; the
     convention stays additive and opt-in per document for every document
     other than `WORKFLOW_V2_PLAN.md`, whose sweep-flagged sections CP6
     marks by that separate obligation, bounded per this guarantee's own
     partition carve-out below)** **(corrected again at revision 24,
     `LOCAL_MODEL_PLAN_REVIEW` round 23, finding I3: "enumerated" — both
     occurrences — is dropped for the flagged-output wording criterion 3
     already applies at every other site; the retired "9-or-so sections"
     count is dropped here as the obligation's own extent, since §6's sweep
     bullet already retains it labelled as a proxy-measured scale
     indication; and the cross-reference is repointed from guarantee (vi)'s
     carve-out — which this guarantee's own regression never asserts — to
     this guarantee's own partition carve-out, matching the subject-scope
     statement above)**;
     (vi), asserted only within the subject scope stated above, a unit
     classified `CURRENT` never carries the inline
     provenance/disposition narrative point 1 forbids — a "revision N
     corrected finding X"-shaped justification for why the current text is
     correct — and an occurrence of that narrative inside `CURRENT` material
     fails the check **(added at revision 22, `LOCAL_MODEL_PLAN_REVIEW`
     round 21, finding I1: without this guarantee, points 1-2's own
     substance was enforced by nothing, and CP1's carry sentence's appeal to
     "CP6's lint" making its provenance record provenance-only, not current
     design content, had nothing behind it)**. Guarantee (vi) has no
     `HISTORICAL`-side counterpart: a `HISTORICAL` unit's own content is
     exactly what point 2 expects such narrative to consist of, and the
     check imposes no content requirement on it beyond its classification.
     **Like the marker's representation — fixed by CP1 per the
     separability bullet above (§2.4 point 3) — this is an implementation
     decision rather than this plan's prose; unlike it, this one stays
     CP6's (repointed at revision 30, `LOCAL_MODEL_PLAN_REVIEW` round 29,
     finding I2: revision 29 moved the marker's representation to CP1
     without repointing this sentence's own analogy, so it kept asserting
     the attribution round 28's finding B1/criterion 1 had just retired —
     the fifth mirror of that attribution, one round 28's own four-site
     enumeration did not list).** The concrete textual shape
     the check treats as this narrative is CP6 implementation's own
     decision, proved by the narrative-location fixture below, not
     specified in this plan's prose;
     (vii), a new guarantee (added at revision 25, `LOCAL_MODEL_PLAN_REVIEW`
     round 24, finding I1; **narrowed to marker-presence only at revision
     28, user-directed architectural correction, applying together with
     `LOCAL_MODEL_PLAN_REVIEW` round 27's finding B1 and its own required
     acceptance criteria 1/2/4/5, which independently converged on the same
     defect from the review side: revisions 25-27 each derived this
     guarantee's scope or the marking pass's marker *value* from an
     authorship or novelty property — "new material CP1 authored", "the
     sections CP1's own registry entry adds" — rather than from a
     mechanically-readable property of the corpus, which is exactly the
     defect §2.4 point 3 itself exists to eliminate; this correction retires
     that entire derivation, not only its round-27 instance**): a **pure
     presence** obligation, nothing more — every unit within the
     marker-presence scope stated above (the whole of
     `IMPLEMENTATION_REVIEW_WORKFLOW.md`; every top-level design section
     this milestone's own registry entries add to `WORKFLOW_V2_PLAN.md`,
     whichever checkpoint's registry entry adds it — CP1's and CP6's own
     alike, each in full, established the same enumerable-by-registry-entry
     way as before, never by a cross-corpus diff — **widened from "CP1's own
     registry entry adds" to "whichever checkpoint's registry entry adds
     it" at revision 28, finding I2: the prior wording put CP6's own
     `D-Review-Material-Lifecycle` section, the section that defines this
     convention, outside the obligation it defines**) carries an explicit
     marker of **either value**; a unit within that scope carrying none is
     a lint failure, reported independently of guarantee (iii)'s own
     classification verdict for the same unit, which is unaffected by this
     guarantee. This guarantee asserts presence alone and never a required
     *value*: which value — `CURRENT` or `HISTORICAL` — a given unit's
     marker must carry is decided entirely by guarantee (iii)'s
     classification/partition contract above (explicit marker, author's own
     choice, fail-closed default), never by this guarantee, and never by
     who authored the unit, whether its content is new, which named section
     it sits under, or which milestone added it. A nested unit inside an
     in-scope section may legitimately carry an explicit marker that
     differs from its container's — the disposition-record subsection
     CP1 creates under `D-Implementation-Review-Stages` (§2.1), classified
     `HISTORICAL`, nested inside a section otherwise classified `CURRENT`,
     is the concrete case this milestone's own corpus already contains —
     and that nested unit's own explicit marker independently discharges
     this guarantee for it; nesting inside a differently-marked container
     never re-triggers the obligation or implies a conflicting value.
     Exactly which finer-grained units the marker-presence check enumerates
     inside each in-scope section, and what marks a freshly-authored unit
     that carries no marker yet, are CP6 implementation's own mechanical
     decisions, proved by the fixtures and the real-corpus regression below
     (§6), never enumerated in this plan's prose.

   - **Subject/mechanism/timing table (added at revision 26**,
     `LOCAL_MODEL_PLAN_REVIEW` round 25, required criterion 1, finding I1:
     required criterion 4 asked, for each of guarantees (i)-(vii), the
     carve-out and the corpus regression, what CP6 reads to evaluate it and
     when it can read it; revision 25's own §7 entry claimed this was
     already discharged by prose, which round 25 found true for only two of
     the nine cells — see that entry's own correction above; **rows (i),
     (ii), (iii) and "Corpus regression" corrected at revision 27**,
     `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I1/I3: revision 26's row
     (i) named guarantee (vii)'s own narrower marker-presence domain instead
     of the classification predicate's real one, contradicting guarantee
     (v)'s whole-corpus verdict, the scope fixture and the carve-out row of
     this same table; the "Corpus regression" row named the same
     pre-marking state as row (v), contradicting the regression's own
     post-marking carve-out). Every cell
     names a tree CP6 reads directly (never a comparison requiring identity
     across two trees, per I3's resolution above) and a point in the
     checkpoint order at which that tree exists:

     | Subject | What CP6 reads | When readable |
     | --- | --- | --- |
     | (i) full classification | every unit of `IMPLEMENTATION_REVIEW_WORKFLOW.md` and of `WORKFLOW_V2_PLAN.md` in full, pre-existing sections included — the classification predicate's own domain, every document the convention names, wider than guarantee (vi)'s marker-scoped reach (row (vi) below) and guarantee (vii)'s marker-presence scope (row (vii) below) | CP6 time — `IMPLEMENTATION_REVIEW_WORKFLOW.md` is authored whole by CP1; `WORKFLOW_V2_PLAN.md`'s pre-existing content already exists, and CP1 and CP6 each add their own new top-level design sections to it, per their registry entries |
     | (ii) verdict independent of heading | the marker alone, on the same units as (i) | CP6 time |
     | (iii) fail-closed default | the marker alone, on the same units as (i) | CP6 time |
     | (iv) transition visible in diff | two versions of the same unit's marker, across a diff, whether on the unit material already belongs to or on a redrawn unit boundary with no marker edit (per the transition bullet above) | CP6 time (fixture-only; no corpus) |
     | (v) pre-existing corpus stays `CURRENT` | `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s units carrying no explicit marker of their own, as it stands the moment before CP6's own marking pass — CP1's own already-`HISTORICAL`-marked disposition subsection is present in this same tree at this same moment and is outside this row's own verdict (**corrected at revision 29**, finding I1) | CP6 time — the file CP1 and CP6 both author directly |
     | (vi) narrative excluded from `CURRENT` material | the marker plus the prose of a unit already classified `CURRENT`, scoped to a unit carrying an explicit `CURRENT` marker | CP6 time |
     | (vii) marker presence | `IMPLEMENTATION_REVIEW_WORKFLOW.md` in full; every top-level design section this milestone's own registry entries add to `WORKFLOW_V2_PLAN.md`, CP1's and CP6's own alike (**widened at revision 28**, finding I2) | fixtures: CP6 time, independent of corpus timing; the real-corpus run: CP6 time, but only **after** CP6's own marking pass — pre-marking, the real corpus fails this guarantee by construction, since none of its in-scope units yet carries a marker (**two-state cell added at revision 28**, finding I3) |
     | Carve-out (which pre-existing sections CP6 may mark `HISTORICAL`) | the governing-version sweep's own flagged output, computed against `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md` | CP6 implementation time, after the sweep runs against that tree |
     | Corpus regression | `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`, the same tree as (v) but read a second time, after CP6 has made its carve-out-bound markings (post-marking, never row (v)'s own pre-marking read) | CP6 time; the built `distribution/workflow/2.5.0/` payload is never read a second time for this (§6, revision 25, finding I2, resolution 1) |

     The classification predicate's own domain — rows (i)-(iv) — is every
     unit of both documents the convention names, in full (**restated as a
     domain claim, not a "reads" claim, at revision 28**, optional finding
     O1: row (iv) is fixture-only and reads no corpus, so what rows (i)-(iv)
     share is the predicate's *domain*, never a claim about what CP6 reads
     to evaluate row (iv) specifically); that domain is distinct from, and
     wider than, guarantee (vi)'s marker-scoped reach (row (vi)) and
     guarantee (vii)'s marker-presence scope (row (vii)), which each cover a
     narrower, explicitly-named subset of the same corpus. Every row
     names a tree that exists at CP6 time, since CP1 and CP6
     between them author every tree this table cites directly — none of
     these guarantees waits on a later checkpoint's own output.

     **What a predecessor checkpoint has already written (added at revision
     29, optional but recommended structural note, `LOCAL_MODEL_PLAN_REVIEW`
     round 28's architecture-and-maintainability discussion): by the time
     any row above is first evaluated, CP1 has already written exactly one
     marker into the tree rows (v), (vii), Carve-out and Corpus regression
     each read — its own disposition-record subsection's explicit
     `HISTORICAL` marker (§2.1), in the representation CP1 itself fixes (the
     separability bullet above).** No row's own verdict is stated relative
     to a tree CP1 has not yet touched; each row that reads this tree reads
     it exactly as CP1 leaves it, never as a hypothetically marker-free
     base. Naming this once here is what makes an ordering precondition
     between CP1's and CP6's deliverables — B1's and I1's shape — visible at
     the one place this table already collects subject/mechanism/timing,
     rather than only recoverable by reading CP1's and CP6's own entries
     against each other by hand.
   - **CP6 must prove the mechanism it builds**, not merely assert it, with
     fixtures covering at minimum — every fixture in this list blocking
     CP6's own completion, stated once here rather than per-fixture
     (**added at revision 31**, `LOCAL_MODEL_PLAN_REVIEW` round 30, optional
     finding O2: criterion 5 asked the pre-marking-partition fixture to say
     which direction it falls in, and the same underspecification was true
     of every fixture in the enumerated set except the two the real-corpus
     marker-presence run and its own bullet already state explicitly) —: a
     positive case (explicitly-marked
     `CURRENT` material the check keeps review-visible), a negative case
     (explicitly-marked `HISTORICAL` material the check excludes from
     review-visible surface), an ambiguous case (unmarked or
     malformed-marker material the check fails closed to `CURRENT`), a
     two-version transition case (guarantee (iv), **added at revision 23**,
     `LOCAL_MODEL_PLAN_REVIEW` round 22, finding I4, restating round 21's
     own outstanding missing test 1: run the check over two fixture
     versions of the same document — one edit that changes no marker,
     spanning a heading reword and a prose restructure, and one edit that
     changes only a marker — and assert the first leaves every unit's
     reported classification unchanged while the second alone performs the
     `CURRENT` -> `HISTORICAL` transition), a
     boundary-redrawing case (guarantee (iv), added at revision 22, finding
     I3: merging a `CURRENT` region into an adjacent `HISTORICAL`-marked
     unit by deleting or demoting the heading between them, with no marker
     edit, must not report that material `HISTORICAL`), a
     narrative-location case (guarantee (vi), added at revision 22, finding
     I1: the forbidden narrative inside `CURRENT` material fails the check
     because that material carries an explicit `CURRENT` marker; the
     identical narrative inside `HISTORICAL` material passes), a scope
     case (guarantee (vi), **added at revision 23, discriminator restated at
     revision 24**, finding I1: a corpus-shaped fixture whose unmarked
     pre-existing section carries the forbidden narrative must pass, since
     that section is `CURRENT` only by the fail-closed default — carrying no
     explicit marker at all — and is therefore outside guarantee (vi)'s
     reach by the mechanical basis above, never merely because it is
     pre-existing as such), and a
     carve-out-bound case (**added at revision 23**, finding I3, restating
     round 21's own outstanding missing test 4: a pre-existing
     disposition-titled section containing only occurrences the
     governing-version sweep does not flag must not be marked `HISTORICAL`
     by CP6's own deliverable, and the corpus regression below must fail if
     it is), and a
     marker-presence fixture (**added at revision 25, restated as
     one-corpus-shaped at revision 26**, `LOCAL_MODEL_PLAN_REVIEW` round 25,
     finding I3, and I3's own required fixture): an in-scope unit
     (by the marker-presence scope stated above) carrying no marker must
     fail guarantee (vii), while the ambiguous fixture's own `CURRENT`
     classification verdict (guarantee (iii)) for the same unmarked input is
     unaffected — the two checks are independent; for `WORKFLOW_V2_PLAN.md`
     the fixture is now one-corpus-shaped, since the scope is every
     checkpoint-added top-level section rather than a cross-corpus diff
     (**restated for the widened scope at revision 28**, finding I2): a
     fixture unit inside one of the in-scope sections, unmarked, must fail;
     a fixture unit elsewhere in the same fixture document, unmarked, must
     pass (outside the scope) — no second corpus or cross-corpus identity
     comparison is needed (I3's own resolution above) — and an
     already-marked-nested-unit fixture (**added at revision 28**, required
     test 1 of round 27's finding B1: an in-scope unit already carrying an
     explicit `HISTORICAL` marker written by an earlier checkpoint, nested
     inside another in-scope unit CP6's own marking pass also covers, must
     survive that marking pass unchanged — CP6 must not overwrite it, this
     guarantee must report it satisfied by presence alone, and guarantee
     (vi) must not fail on its provenance narrative, since it is
     `HISTORICAL`, not `CURRENT` — the concrete fixture shape mirrors CP1's
     own carried disposition-record subsection nested under
     `D-Implementation-Review-Stages`), and a
     representation-conformance fixture (**added at revision 29**, required
     test 1 of round 28's finding B1: CP1's own disposition-record
     subsection, in the fixture, carries its `HISTORICAL` marker written in
     exactly the representation CP1 fixes — the separability bullet above —
     and CP6's own parser, built against that same fixed representation,
     recognizes it as an explicit marker rather than defaulting it to
     `CURRENT`; **widened at revision 31**, `LOCAL_MODEL_PLAN_REVIEW` round
     30, finding I1, resolution 1: the same fixture additionally asserts the
     exclusivity direction — a mutated copy of the fixture's marker, written
     in a form outside CP1's fixed representation, must *not* be recognized
     as an explicit marker and must instead fall to the `CURRENT` fail-closed
     default; without this fixture, the already-marked-nested-unit fixture
     above proves only the skip rule over inputs it generates itself, and
     nothing mechanically connects it to CP1's real deliverable; **widened
     again at revision 33**, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding I1
     (revision 32 itself applied this widening only at the separability
     bullet above and CP6's registry entry, not here — §7's own
     revision-32 entry is corrected below to say so): the fixture is
     widened to exercise the canonical `render_marker`/`parse_marker` pair
     directly rather than only CP1's one written instance, matching the
     separability bullet's own revision-32 text — `parse_marker` accepts
     `render_marker("HISTORICAL")`'s own output as `HISTORICAL`, accepts
     `render_marker("CURRENT")`'s own output as an explicit `CURRENT`
     marker distinct from the fail-closed default a missing marker also
     classifies `CURRENT`, and rejects representative malformed/
     out-of-contract forms — a mutated delimiter, a third state value,
     truncated or duplicated marker text — back to the `CURRENT`
     fail-closed default; CP1's own written instance and every marker
     CP6's marking pass writes are additionally required to equal
     `render_marker`'s own output bytes for their respective state, a
     mechanical equality check rather than a second grammar comparison;
     and (`LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2's own missing-test
     note) the fixture additionally asserts that CP6's own lint reaches its
     `CURRENT`/`HISTORICAL`/malformed classification verdicts by calling
     this same `parse_marker`, so a lint whose own grammar tolerates a form
     outside the canonical pair cannot pass with the fixture green), and a
     pre-marking-partition fixture (**added at revision 30**,
     `LOCAL_MODEL_PLAN_REVIEW` round 29, finding B1, resolution 2, missing
     test 1: a corpus-shaped fixture document containing one unit already
     carrying an explicit `HISTORICAL` marker — mirroring CP1's own
     disposition-record subsection — alongside units carrying no marker at
     all; the check run against it must classify the marked unit
     `HISTORICAL` and every unmarked unit `CURRENT` (guarantee (v)'s
     narrowed form), and a mutated copy of the same fixture asserting every
     unit classifies `CURRENT`, the marked one included, must fail (the
     widened form guarantee (v) forbids); being a fixture rather than a
     one-shot real-corpus read, it survives CP6's own marking pass and so
     remains available to catch a future edit that re-widens guarantee (v),
     which the real-corpus read below cannot, since that read's own
     pre-marking moment stops existing in the worktree once CP6 completes)
     — plus a
     real-corpus run of the finished marker-presence check itself, over
     every one of guarantee (vii)'s actual subjects —
     `IMPLEMENTATION_REVIEW_WORKFLOW.md` in full and every top-level
     `WORKFLOW_V2_PLAN.md` section any checkpoint's registry entry adds,
     `D-Review-Material-Lifecycle` itself included (**widened at revision
     28**, required test 2 of finding I2: the same widening that brought
     CP6's own section inside guarantee (vii)'s scope brings it inside this
     real-corpus run too, with no separate mechanism needed), once CP6 has
     written the markers CP6's own registry entry and §6's lifecycle-lint
     bullet assign it — as part of CP6's own completion
     requirement (**added at revision 27**, `LOCAL_MODEL_PLAN_REVIEW` round
     26, finding I2's own required test: guarantee (vii) was proved by
     fixtures alone, and the classification-partition regression below makes
     no claim about it), distinct from the guarantee (v) classification
     partition regression below — plus that guarantee (v) partition
     regression run of the finished check against
     `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s
     own, real existing corpus, run **after** CP6 has made its
     carve-out-bound markings (post-marking — distinct from guarantee (v)'s
     own pre-marking read of the same tree; **the two states named
     explicitly at revision 27**, `LOCAL_MODEL_PLAN_REVIEW` round 26,
     finding I3: this regression must observe CP6's own markings to have
     anything to check the carve-out-bound fixture above against) (**corpus
     and timing corrected at revision
     24**, `LOCAL_MODEL_PLAN_REVIEW` round 23, finding I2: revision 23 named
     the built `distribution/workflow/2.5.0/` payload, which CP11 depends on
     CP6 to build and which therefore does not exist while CP6's own
     blocking fixture would need to run against it; CP1 and CP6 both author
     this exact overlay file directly (their own registry entries), so it
     exists on disk when CP6 runs — **the second run dropped, revision 25**,
     `LOCAL_MODEL_PLAN_REVIEW` round 24, finding I2, resolution 1: CP6's own
     read of this overlay-payload tree is never repeated a second time
     against the *built* `distribution/workflow/2.5.0/` payload — "single
     run" names that omission, restated at revision 27 to mean exactly that,
     never "one read of this tree in total" (the pre- and post-marking reads
     are two reads of the same tree, not two runs against two trees);
     `build_release.py --check`'s own byte-identity proof (CP11) is what
     transfers this same result to the built `distribution/workflow/2.5.0/`
     payload once that tree exists, since `--check` reproduces the overlay's
     full-replacement file verbatim by construction — nothing else asserts
     this corpus a second time, and CP11/CP13 carry no obligation of their
     own toward it), proving that
     introducing
     the check reclassifies none of that corpus's existing material as
     `HISTORICAL` except where CP6 has deliberately and visibly marked a
     pre-existing section `HISTORICAL` as part of this checkpoint's own
     deliverable **(the basis stated precisely at revision 22,
     `LOCAL_MODEL_PLAN_REVIEW` round 21, finding I2: the governing-version
     enumeration sweep's own pre-existing disposition-section exemptions,
     §6 below, are the concrete case this milestone needs)** — this
     regression asserts guarantee (v)'s classification partition only,
     never guarantee (vi) (per the subject-scope statement above). **The
     carve-out's bound, corrected at revision 23** (`LOCAL_MODEL_PLAN_REVIEW`
     round 22, finding I3: revision 22 bounded the carve-out by a
     hand-measured "9 sections / 24 occurrences" proxy count, of which at
     least two of the 24 counted occurrences — `:3392`, `:3838` — are not
     occurrences of either of the sweep's own two detection forms at all):
     the sections CP6 may mark `HISTORICAL` under this carve-out are exactly
     those the governing-version sweep (§6 below) itself flags when CP6
     runs it against that same overlay-payload tree (**tree named
     explicitly at revision 24**, finding I2, for the reason just stated) —
     never a hand-measured
     proxy list. The "9 sections / 24 occurrences" figure is retained only
     as a proxy-measured indication of scale, not as the set CP6 marks; the
     carve-out-bound fixture above pins this direction. An unmarked
     pre-existing unit still
     classifies `CURRENT` under the fail-closed default, and any
     reclassification not traceable to such a deliberate marker addition is
     a fixture failure that blocks CP6's own completion, not an acceptable
     side effect to note and move past.

   This states the design at the semantic/invariant level a plan can
   specify durably — what `CURRENT`/`HISTORICAL` mean, the safe default,
   the allowed transition, and the guarantees CP6 must prove — while
   preserving this section's original 2.5 objective of separating current
   normative review material from closed, immutable historical record.
   The marker's exact representation — its concrete syntax and delimiters —
   is CP1's own implementation decision, fixed no later than CP1 time
   (**corrected at revision 29**, `LOCAL_MODEL_PLAN_REVIEW` round 28,
   finding B1, resolution 1); heading traversal and the lint built against
   the parser remain deliberately left to CP6's own implementation, verified
   there by the fixtures and corpus regression above, not specified in this
   plan's prose — the parser itself is CP1's own `parse_marker`, imported by
   CP6 rather than a second, independently-derived grammar (narrowed at
   revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2, from "the
   parser that reads that fixed representation, heading traversal, and
   parser grammar remain deliberately left to CP6's own implementation").

   §6's lifecycle-lint bullet and CP6's registry entry state this same
   design.
4. **A disposition bullet found wrong is corrected in place, with the
   superseded wording quoted and the correcting round named (resolves
   `LOCAL_MODEL_PLAN_REVIEW` round 7, optional finding 3).** §7's own
   revision-6 bullet, corrected at revision 7, is the worked example: it
   quotes the wrong original wording verbatim, attributes it, and names the
   round and finding that corrected it, rather than superseding it with a
   new bullet that leaves a reader to discover on their own that an earlier
   one was false. This convention is itself part of `D-Review-Material-
   Lifecycle` and binds the disposition sections point 2 above describes.

This plan's own §7/§8, rewritten at revision 3 below, are the worked
example: §8 is now this milestone's actual defect-disposition record (§2.7)
rather than a standing "we didn't touch these" confirmation, and both
sections are written as disposition history, not as design decisions in
their own right.

### 2.5 D-Canonical-Review-Data — preferring generated review data over duplicated hand-maintained bookkeeping

**Added at revision 3**, per the roadmap correction's "canonical/generated
review data" and "less duplicated self-audit bookkeeping" bullets.

**A genuine, already-duplicated instance, found by direct comparison
rather than assumed:** the "declaration-coverage" unit test this plan's own
CP2 adds (asserting every checkpoint-declared deliverable path a work
item's own `<work_item_id>-artifacts.json` names classifies `protected`,
never `UnclassifiedPathError`/`excluded`) is not this milestone's own
invention — revision 2's own §7 records that
`plan-amendment-mechanism-artifacts.json` diagnosed and fixed the identical
defect class for itself first, and this item's own CP2 re-derives a
bespoke, hand-authored copy of the same test shape, by hand, from this
item's own registry and declarations data. Two work items in a row have now
each hand-authored their own version of the same check from their own
data — exactly the "duplicated hand-maintained... proof tables" the user's
instruction names, even though the check itself is fully mechanical (its
inputs — the registry's own checkpoint list and the declarations file's own
path sets — already exist as data; only the test wiring is duplicated).

**Fix, assigned to CP7**: extract one generic, parametric helper, authored
in the overlay like every other code change this milestone makes (exact
home left to CP7's own judgment — the overlay's own
`scripts/workflow_state_test.py` shared test support, or a new small
overlay module, whichever this repository's existing test-layout
convention favors) that takes a `work_item_id`, reads its own
`<work_item_id>-artifacts.json` and registry, and asserts every
checkpoint-declared deliverable path classifies `protected` at the relevant
stage. `plan-amendment-mechanism` and `implementation-review-two-stage`'s
own existing bespoke tests are left as-is (rewriting another, already-approved
work item's own test file is out of this milestone's scope, and this item's
own CP2 test predates CP7 in the checkpoint order), but every future work
item's plan need only call the shared helper rather than re-author the
check, and this milestone's own CP12 (disposable-repository validation,
§3) exercises the generic helper directly rather than hand-writing another
copy for its own synthetic work item.

**A positive counter-example worth recording, not "fixed" — the census
mechanism already gets this right.** §6's existing text mentions
"`workflow_integration_test.py`/`workflow_state_completion_obligations_test.py`
census updates" as a per-milestone checklist item; reading the actual
mechanism (`scripts/workflow_state_completion_obligations_test.py`'s
`surface_census`/`verifier_census`) shows these are already **mechanically
discovered**, not hand-maintained lists — the "census" is *computed* from
the real module surface each run, not typed out by a plan author. This is
the model CP7's declaration-coverage helper follows, not a second problem
to fix; recorded here so a future reviewer does not mistake "census" for
another instance of the same defect class.

**Explicitly not attempted**: rewriting `docs/ai-workflow/audit/
WORKFLOW_DEFECT_LEDGER.md`'s own already-closed historical entries into a
generated form. That ledger's rows are a closed record of a finished
salvage effort (§2.4); regenerating history is not what "canonical/
generated" means for material that will never be regenerated again.

**Not a `WORKFLOW_V2_PLAN.md` design-of-record section (added at revision
29, optional finding O1, `LOCAL_MODEL_PLAN_REVIEW` round 28): this decision
is deliberately not one of `WORKFLOW_V2_PLAN.md`'s `D-*` sections — its
deliverable (CP7's generic declaration-coverage helper) is a test helper,
never a document section, so it has no design-of-record destination to
reach and none is missing.**

### 2.6 D-Review-Finding-Taxonomy-and-Circuit-Breaker — substantive vs. review-apparatus findings, bounded convergence

**Added at revision 3**, per the roadmap correction's "convergence/
circuit-breaker improvements" bullet and its explicit condition that this
not weaken substantive correctness review.

**The distinction, motivated by this very review round.** Round 2 of this
plan's own `LOCAL_MODEL_PLAN_REVIEW` raised two Important findings: I1 (a
stale justification string in `implementation-review-two-stage-artifacts.json`
republished a retracted premise) and I2 (a design-text bullet reasoned about
the wrong installed-vs-overlay path). Both are real, both required a
`REVISE` round to fix, and neither indicates the underlying design
(`D-Implementation-Review-Stages`, `D-Implementation-Review-Version-Activation`)
is wrong — they are defects in the review apparatus's own supporting
prose/declarations, not in the thing being reviewed. B1(a)/B1(b), by
contrast, are substantive: an actual invariant (`HEAD == T`, the
generation-record commit's own required shape) was wrong. `REVIEW_PROTOCOL.md`
today has no vocabulary for this distinction — every Blocking/Important
finding is procedurally identical regardless of which kind it is, so a
round consisting entirely of apparatus-only findings consumes exactly as
much convergence "budget" as a round that found a real defect.

**Fix, assigned to CP8**, authored into the overlay's own
`migration/overlays/2.5.0/payload/docs/ai-workflow/REVIEW_PROTOCOL.md`
(mirroring every other CP1/CP4-style overlay document edit this plan
makes), additive to that file's existing `REVIEW_FEEDBACK.md` structure
("Feedback protocol" section), not a new lifecycle phase or
governing-version bump:

1. **An advisory per-finding tag, not a parser-enforced one. Corrected at
   revision 4 (`LOCAL_MODEL_PLAN_REVIEW` round 3, finding I5)**: revision 3
   called this tag "required" and, in §6, specified a parser-level test
   "asserting every Blocking/Important finding carries a
   `[substantive]`/`[apparatus]` tag (malformed or missing tags
   rejected...)". That contradicts this very section's own §5 claim that
   CP6-CP8 "change no runtime state-machine behavior for any existing work
   item" and need no governing-version bump: `WFR-03`'s binding-field
   strictness (`parse_review_feedback_binding_fields`/
   `assert_feedback_matches_bundle`) governs a small, fixed set of identity
   fields checked before any write and applies uniformly to every
   governing version already; extending that same rejection behavior to a
   brand-new free-text finding tag would break the very next review round
   of every live `"1"`/`"2.1"` work item, in every repository, the moment
   it updates to `2.5.0` — no external reviewer's existing feedback carries
   these tags, so a parser that rejects untagged findings rejects
   feedback that was valid the round before. That is exactly the class of
   behavior change `D-Implementation-Review-Version-Activation` (§2.2)
   itself says requires a new governing version, which this addition
   deliberately does not carry. The tag is therefore recommended prose on
   every Blocking/Important finding — `[substantive]` (a defect in the
   design or implementation being reviewed) or `[apparatus]` (a defect
   confined to bundle metadata, declarations-file prose, a stale table
   embed, or similar supporting material that does not itself indicate the
   reviewed content is wrong) — never rejected for being malformed,
   ambiguous, or absent. An untagged or ambiguously-tagged Blocking/Important
   finding is instead treated, conservatively, as `[substantive]` for
   purposes of the circuit-breaker signal below, so an omitted tag can
   never manufacture an apparatus-only streak by silence. Optional findings
   are unaffected either way — the distinction matters only where
   `REVIEW_PROTOCOL.md` already requires resolution or explicit rejection.
2. **No weakening of resolution requirements.** `REVIEW_PROTOCOL.md`'s
   existing rule — "every blocking and important finding must end up
   either resolved, or explicitly rejected... with repository evidence" —
   is unchanged for both tags, and unchanged for an untagged finding too.
   `[apparatus]` never means "may be ignored"; it means only "does not by
   itself cast doubt on the substantive design."
3. **A bounded, advisory circuit-breaker signal**, surfaced in the
   reviewer's own report rather than gating `phase`: when a bounded number
   of consecutive `REVISE` rounds for the same **local-model** review
   stage (`LOCAL_MODEL_PLAN_REVIEW` or `LOCAL_MODEL_IMPLEMENTATION_REVIEW`
   — narrowed at revision 15, `MANUAL_EXTERNAL_PLAN_REVIEW` round 1,
   finding I3; see the scoping correction below) — checkable because
   `REVIEW_FEEDBACK.md` itself states its own `Reviewer role:` line
   (`LOCAL_MODEL_PLAN_REVIEW`, `MANUAL_EXTERNAL_PLAN_REVIEW`, or either
   implementation-stage equivalent), so a reviewer distinguishes "the same
   stage" by that line rather than by `<feedback_dir>/REVIEW_FEEDBACK.md`'s
   own path, which `resolve_feedback_dir` deliberately leaves stage-agnostic
   and shared by both stage protocols (added at revision 5,
   `LOCAL_MODEL_PLAN_REVIEW` round 4, optional finding 3) — have carried
   **no** `[substantive]` Blocking/Important finding (every one was `[apparatus]`,
   an untagged finding counting as `[substantive]` per point 1), the
   reviewer's own next report states this explicitly (e.g. "N consecutive
   apparatus-only rounds") as a visible diminishing-returns signal an
   operator can act on — requesting a lighter confirmation pass, or
   accepting the standing substantive verdict — rather than treating every
   apparatus fix as resetting the convergence clock to zero. This is
   deliberately advisory prose in the reviewer's report, not a new
   `WORKFLOW_STATE.json` field or phase-machinery gate: it changes no
   existing item's behavior on update (no governing-version bump needed)
   and never itself approves anything — `/approve-review` and its
   `EXTERNAL_APPROVE`/local-plus-manual-ledger bases are completely
   unaffected. **The bound is fixed at 2, resolved rather than left open
   (revision 4, `LOCAL_MODEL_PLAN_REVIEW` round 3, finding I6; §9's
   circuit-breaker round-bound paragraph is settled by this correction, not
   left for the plan-review gate)**: nothing durable records a `REVISE` round today —
   `record_local_plan_review`'s `REVISE` branch writes no ledger entry at
   all, the `APPROVE` branch's ledger entry carries no finding detail, and
   `<feedback_dir>/REVIEW_FEEDBACK.md` is a single path each round
   overwrites (this very plan's own revision-3 feedback overwrote
   revision-2's) — so a reviewer can observe at most one prior round
   beyond its own, which is exactly enough data for a bound of 2 and no
   more. A bound of 3 or higher is unimplementable from this data without a
   durable per-round record this addition deliberately does not add (the
   `"no new WORKFLOW_STATE.json field"` claim two paragraphs below would
   otherwise be false); a future release wanting a higher bound must first
   add such a record and state it explicitly, rather than this plan
   gesturing at an option the mechanism as designed cannot implement.

**Scope of the signal, corrected to what the artifact lifecycle can
actually support (resolves `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding
I3).** Point 3's own "checkable because `REVIEW_FEEDBACK.md` itself states
its own `Reviewer role:` line" reasoning holds only where the *same*
reviewing agent reads the immediately-prior
`<feedback_dir>/REVIEW_FEEDBACK.md` before overwriting it with its own —
true for two consecutive `LOCAL_MODEL_PLAN_REVIEW`/
`LOCAL_MODEL_IMPLEMENTATION_REVIEW` rounds, since `/review-plan`/
`/review-implementation` run before the file is replaced. It does not
hold across two consecutive manual-external rounds: a manual `REVISE` is
consumed by `/apply-*-review`, and before another manual-external round
can occur, a fresh local pass must run first (§2.1's "no path re-enters
manual-external review without a fresh local pass") and that pass
overwrites the same stage-agnostic path with its own `REVIEW_FEEDBACK.md`
before the next manual reviewer ever sees the prior one. Neither
`record_local_plan_review`'s/`record_manual_plan_review`'s (nor this
milestone's own implementation-stage mirrors') `REVISE` branch writes any
durable, finding-classification-bearing ledger entry, and the review
bundle itself never includes `feedback/`. By the next manual-external
round, no durable, reviewable record proves the preceding manual-external
round was apparatus-only — the two-round signal is therefore **not**
uniformly available for that reviewer role, as revision 14's own closing
paragraph incorrectly claimed.

**Fix: the signal is scoped to the local-model review loops only.** The
advisory circuit-breaker text is stated, and CP8 authors it, as a property
of two consecutive `LOCAL_MODEL_PLAN_REVIEW` (or two consecutive
`LOCAL_MODEL_IMPLEMENTATION_REVIEW`) rounds specifically — the automated,
token/convergence-costly loop this addition's own motivating example
(round 2's I1/I2, both local-model findings) actually came from.
`REVIEW_PROTOCOL.md`'s own addition states explicitly that it makes **no**
corresponding claim for two consecutive manual-external rounds: recovering
that signal would need a minimal durable per-round history this addition
deliberately does not add (the same "no new `WORKFLOW_STATE.json` field"
reasoning above), and this milestone does not build one — manual-external
convergence stays operator judgment, as it already is today. CP8's own
test coverage is corrected to match (§6): it proves the signal fires after
two consecutive local apparatus-only rounds for each stage, and proves
(rather than assumes) that `REVIEW_PROTOCOL.md`'s own text makes no
manual-external recoverability claim a reader could act on.

**Applies to both review-stage protocols this repository has, at the
local-model loop only** (plan-stage, already shipped, and this milestone's
own new implementation-stage two-stage protocol, §2.1) — `REVIEW_PROTOCOL.md`'s
"Feedback protocol" section governs `REVIEW_FEEDBACK.md`'s shape for both,
so CP8's addition is written once, there, rather than duplicated per
stage.

### 2.7 Remaining post-v2.3.1 correctness/ergonomics backlog — reconsidered per-defect disposition

**Added at revision 3**, per the roadmap correction's third branch and its
explicit instruction to reconsider the four already-documented deferred
defects rather than blanket-excluding them again. Old §8 ("Confirmation
this milestone leaves the four deferred defects alone") is superseded by
the rewritten §8 below, which states each defect's actual disposition. This
section states the fix design; §8 is the confirmation record; CP9/CP10
(§3) carry the implementation.

**Why any of these are tractable here at all, despite `CLAUDE.md`'s "never
modify frozen Workflow semantics" rule**: that rule binds
`distribution/workflow/2.3.1/`, the byte-identical frozen extraction, which
this milestone does not touch. `2.5.0` is an *authored* release — base
`2.4.0` plus this milestone's overlay — and `2.4.0` itself already
demonstrates that an authored release's overlay may carry a genuine
behavioral fix to `scripts/workflow_state.py` (the `.workflow-manager/`
plan-stage exclusion, `v2.4.0-001`'s own forward fix). A fix scoped to the
overlay's own copy, landing in `2.5.0` and applying only to repositories
that update to it, is squarely inside that same precedent — it is not an
edit to any frozen distribution directory.

**Not a `WORKFLOW_V2_PLAN.md` design-of-record section (added at revision
29, optional finding O1, `LOCAL_MODEL_PLAN_REVIEW` round 28): this
section's own heading ("Remaining post-v2.3.1 correctness/ergonomics
backlog") deliberately does not carry the `D-Post-v2.3.1-Backlog` name CP9's
and CP10's own registry entries cite it by — this disposition record is this
decision's design-of-record destination, and `WORKFLOW_V2_PLAN.md` gains no
section for it.**

1. **`v2.3.1-003` (first-ever plan approval needs a pre-committed
   `WORKFLOW_STATE.json`) — fixed.** The first of the defect record's own
   two stated portable forms is adopted (**corrected at revision 4,
   `LOCAL_MODEL_PLAN_REVIEW` round 3, optional finding 2** — "the record's
   own stated portable form," singular, is imprecise: the record offers
   two): `pin_plan_approval_state_blob` defaults to file mode `100644`
   (matching every other tracked path this Workflow ever commits) when
   `_blob_mode_and_sha_at_commit` returns `None`, instead of raising
   `PlanApprovalStateBlobUnavailableError` unconditionally. `100644` is not
   a guess: it is the mode every other path this workflow commits already
   uses, per the defect record's own observation. The record's alternative
   — generalizing `/approve-review`'s `workflow-v2-1-core`-only bootstrap
   diversion in step 4a — is not taken; this milestone's narrower fix is
   sufficient and does not touch that command's own step 4a logic.
   Assigned to CP9.
2. **`v2.3.1-001` (a conformance test asserts on host-repository history)
   — fixed.** The defect record's own stated portable form is adopted
   verbatim: `test_the_historical_status_note_carries_a_dated_correction`
   is changed from `next(...)` (raising `StopIteration` when the host note
   is absent) to `next((...), None)` plus `self.skipTest(...)` when the
   result is `None`. A repository that does carry the dated host note (the
   frozen conformance fixture) is unaffected; a bootstrapped target with no
   such note now skips cleanly instead of failing. **Corrected at revision
   4 (`LOCAL_MODEL_PLAN_REVIEW` round 3, finding I4)**:
   `migration/portability_exceptions.json`'s existing `2.3.1`/`2.4.0`
   `by_version` entries for this test are **not** removed — both releases'
   own payloads still carry the unfixed test (verified: the `next(...)`
   form is present in both `distribution/workflow/2.3.1/payload/scripts/workflow_integration_test.py`
   and `distribution/workflow/2.4.0/payload/…`), and `2.3.1` is frozen, so
   a clean-target run against either would gain an undocumented failure if
   its entry were removed. `2.5.0` instead **gains** its own, required
   `by_version["2.5.0"]` entry with an **empty** `exceptions` list —
   required, not conditional on whether "this release's own suite needs
   one," since `tests/support.py:134` reads
   `PORTABILITY_EXCEPTIONS["by_version"][workflow_version]["exceptions"]`
   as an unguarded subscript: an absent `"2.5.0"` key is a `KeyError` at
   test-collection time, not a pass. Assigned to CP9.
3. **`v2.4.0-001` (a pre-existing work item's plan-stage classification does
   not know about `.workflow-manager/installation.json`) — generator
   symmetry widened, not retroactively repaired.** The `2.4.0` fix widened
   only `generate_artifacts_declarations`'s **plan-stage** default
   `excluded_prefixes`. This item's own revision-2 fix (finding B1) had to
   hand-add the identical exclusion to its own **implementation-stage**
   declarations by hand, for the same reason the defect record already
   gives for the plan stage: `.workflow-manager/installation.json` is
   `workflow_manager`'s own tooling invention, absent from both frozen
   upstream vocabulary and, until now, the generator's own implementation-
   stage template. CP9 widens `generate_artifacts_declarations`'s
   **implementation-stage** default `excluded_prefixes` the same way the
   plan-stage default already was, so a future work item's own first-ever
   implementation-stage declarations file is not exposed to the identical
   gap this item had to hand-fix for itself. Exactly as `v2.4.0-001`'s own
   record states for its plan-stage fix, this is forward-only: no existing
   work item's already-generated declarations file is edited by this
   change (editing one after the fact would itself stale a standing
   approval, the same reasoning the record already gives). **Release
   operator guidance, added to close round 2's optional finding 2**: CP9's
   registry entry and CP11's (release-authoring) own migration notes state
   this widening as guidance for *any* repository updating to `2.5.0`, not
   only this repository's own mitigation — a repository with a live
   `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` work item whose
   declarations file predates this fix remains exposed exactly as
   `v2.4.0-001` already documents (mitigation #1, do not commit
   `.workflow-manager/installation.json` mid-flight; mitigation #2, hand-widen
   that one item's own declarations file) until that item's own next plan
   revision regenerates its declarations under the `2.5.0` generator.
4. **`v2.4.0-002` (cross-worktree amendment/claim race) — reconsidered,
   still deferred, for updated reasons stated explicitly rather than by
   omission.** This is a live concurrency-correctness invariant that has
   already gone through eleven external review rounds to reach its current,
   carefully-proved (and carefully-narrowed) shape; closing it requires
   either a `claims_dir`-rooted lock (reopening the `item 372(h)` primitive
   census and raw-edge derivation) or a repo-global phase witness (a wholly
   new kind of durable object) — both explicitly declined already, under
   review pressure, for being real, separate concurrency engineering rather
   than review-tooling work. This milestone's own mission is
   implementation-review process and review-scalability tooling, not
   concurrency-correctness engineering, and taking on either structural fix
   here would be exactly the kind of scope creep §1's narrow-scope
   discipline argues against. **Reconsidered outcome**: continue deferring
   the two structural fixes, unchanged. The cheaper, previously-declined
   third option (`IMPL10-O1`: a second `resolve_claim(...)` re-check
   immediately before `request_plan_amendment`'s own supersede, narrowing
   reason 1's exposure window at no new primitive and no `item 372(h)` edge)
   was recorded as a live, optional, cheap partial mitigation this
   milestone *could* adopt without reopening the census — but adopting even
   that was left as an explicit open decision (§9) pending the plan-review
   gate's own judgment, since it is still a change to the mechanism's own
   critical section and this milestone's own reviewers, not this plan
   unilaterally, should weigh whether "cheap" is cheap enough to take up
   mid-milestone. **Resolved at revision 15** (`MANUAL_EXTERNAL_PLAN_REVIEW`
   round 1, required acceptance criterion 4): **declined** — `IMPL10-O1` is
   deferred together with both full structural fixes, for the same reason
   the defect record itself already gave when it first declined this exact
   option (round 10, under review pressure, in the same round the residual
   was found): narrowing one race window without establishing the
   documented cross-worktree guarantee adds surface to a critical section
   in a review-focused milestone without closing the defect, and dedicated
   future concurrency-correctness work remains the right owner for all
   three options. No checkpoint in §3 performs any of the three; CP10 (§3)
   is scoped to producing this reconsidered, explicit disposition alone.

## 3. Checkpoints

Generated via `workflow_state.generate_registry`/`write_registry_and_mapping`
into `docs/ai-workflow/registry/implementation-review-two-stage-registry.json`.
This table is `workflow_state.render_registry_markdown`'s own output,
embedded verbatim — never hand-edited.

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Design decisions: author D-Implementation-Review-Stages (two new phases AWAITING_LOCAL_IMPLEMENTATION_REVIEW / AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW, the implementation_review_stages ledger, the full verdict/state transition table, /review-implementation's new authoritative "2.2" branch, the new /record-manual-implementation-review contract, /apply-implementation-review's new "2.2" branch, and technical_approval_gate_reachable's widened entry condition) plus D-Implementation-Review-Version-Activation (generalizing WF-Activate's build_activated_config/build_rolled_back_config to a target-version parameter, reused for the 2.1 -> 2.2 bump) into migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md; update MILESTONE_WORKFLOW.md's state reference and hard-gates summary and REVIEW_PROTOCOL.md / a new IMPLEMENTATION_REVIEW_WORKFLOW.md operator guide in the same overlay; resolve this plan's own surfaced open decisions (terminal-phase naming reuse, activation-ceremony scope) explicitly in the design text, not silently; carry into the overlay's own WORKFLOW_V2_PLAN.md design text this plan's actual resolution of the implementation-stage provenance-interval question -- the version-dependent bundle_generation_target_phase(stage, governing_workflow_version) resolver (replacing record_bundle_generation's and validate_bundle_generation_record_commit's single hard-coded target-phase literal in both the ordinary-role and recovered-role checks), both widened field-set constants (ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS and RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS, each gaining implementation_review_stages), RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES' additive widening to the two new "2.2" phases (already retaining the terminal AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW phase), the recovery command's own phase guard's widening to all three phases a "2.2" item can occupy between T and approval (the two new phases plus the terminal phase), and bundle_generation_recovered_role_legal_committed_phases(governing_workflow_version)'s membership test over that identical three-phase set replacing the recovered role's prior single-valued committed-phase equality -- stated as one invariant, the command guard and the committed-phase set are the same set and both are a subset of the additively-widened parent set -- so that HEAD == T remains a legally-generated, legally-validated invariant for a "2.2" item in both commit roles at every round; carry the consolidated "where the two-stage mirror genuinely diverges" subsection (the four divergences, all traced to the implementation stage's commit-anchored identity/provenance versus the plan stage's worktree-measured one, including the two-commit-role divergence B1/B2 add) into WORKFLOW_V2_PLAN.md, carrying its substantive content in full with its four inline disposition parentheticals restated as entries in a single, named `2.5.0`-scoped disposition section CP1 adds to WORKFLOW_V2_PLAN.md (e.g. a `#### 2.5.0 disposition record` subsection, explicitly classified HISTORICAL under D-Review-Material-Lifecycle) rather than inline (corrected at revision 20, `LOCAL_MODEL_PLAN_REVIEW` round 19, finding I4: "verbatim" is dropped, since carrying the subsection's four inline "revision N corrected finding X" parentheticals verbatim would reproduce, inside this checkpoint's own D-Implementation-Review-Stages extent, exactly the inline-disposition-narrative shape D-Review-Material-Lifecycle's own point 1 forbids; further corrected at revision 21, `LOCAL_MODEL_PLAN_REVIEW` round 20, finding I3: "the document's own disposition section" was not a determinate destination -- WORKFLOW_V2_PLAN.md already carries 89 pre-existing disposition-shaped headings (corrected from "83" at revision 22, `LOCAL_MODEL_PLAN_REVIEW` round 21, optional finding O1 -- 83 is only the ##-level subset), so CP1 must name and create this exact new section, explicitly marked HISTORICAL, as its own deliverable, rather than appending to any pre-existing disposition heading), additionally fixing the marker's own concrete representation -- its exact syntax and delimiters -- as part of this same deliverable (added at revision 29, `LOCAL_MODEL_PLAN_REVIEW` round 28, finding B1, resolution 1: this HISTORICAL marker must be written before CP6 exists to choose a representation for it, since CP6 runs after CP1, so the representation cannot remain a CP6-time decision; D-Review-Material-Lifecycle states the same reassignment and what stays CP6's -- the lint that runs the parser, and every guarantee CP6 must prove (narrowed at revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2, from "the parser that reads the representation, the lint that runs it, and every guarantee CP6 must prove")); CP1 fixes the representation as one canonical `render_marker`/`parse_marker` machine-readable definition, imported by CP6 rather than re-derived, never a second parsing grammar (revised at revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I2, from "CP1's own single written instance of this representation is itself the specification"), restricted to exactly the two-member state domain {CURRENT, HISTORICAL}, with no second, hand-written prose grammar restating its syntax; CP1 writes its own required HISTORICAL marker by calling this same render_marker rather than hand-typing it independently, so CP1's own instance is a product of the canonical definition, never a second, competing source of truth for it; CP6 imports and reuses the identical render_marker/parse_marker pair for every marker it writes and for its own lint's parsing, never a second, independently-derived regex or grammar tolerating a form the canonical pair does not itself produce or accept -- both directions (CP1's instance recognized as an explicit HISTORICAL marker; a form outside the canonical pair's own output falling to the CURRENT fail-closed default) pinned by the representation-conformance fixture D-Review-Material-Lifecycle names, per this plan's own §2.1; plan-review inheritance widening (resolves `LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1(b)): MILESTONE_WORKFLOW.md's AWAITING_LOCAL_PLAN_REVIEW/AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW headings, entry/exit prose and verdict/transition table, and AWAITING_PLAN_APPROVAL's own entry condition, restate the "2.1" membership test as TWO_STAGE_PLAN_REVIEW_VERSIONS ("2.1" or "2.2") rather than the bare "2.1" literal, with AWAITING_PLAN_APPROVAL's entry condition the priority since it ships the round-6 B1 silent bypass; round-7 plan-review inheritance widening, resolves `LOCAL_MODEL_PLAN_REVIEW` round 7, finding B1(b)/(d)/(f): docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md's title (:1), its "Scoped entirely to `"2.1"`" opening (:14-19, the `"1"`-item sentence stays unchanged) and its /apply-plan-review bullet (:66) restated to `"2.1"`/`"2.2"` alike; MILESTONE_WORKFLOW.md's AMENDING_PLAN scope sentence (:52) and SELF_REVIEWING_PLAN's publish_plan_revision routing sentence (:121), both outside CP1's own plan-review-state item, restated the same way; "2.2" rollback destination, resolves round 7 finding I2: the overlay's WORKFLOW_V2_PLAN.md design text for build_rolled_back_config states the rollback destination as the version activation superseded ("2.2" rolls back to "2.1"), never a fixed literal, correcting scripts/workflow_state.py:6651's current "1" return value, and records in one sentence why rollback need not remove the target version from supported_versions today -- the new IMPLEMENTATION_REVIEW_WORKFLOW.md operator guide additionally documents, as its own dedicated section, the "2.2" activation procedure a repository other than this one follows to reach it (resolves `LOCAL_MODEL_PLAN_REVIEW` round 9, finding I1): the WORKFLOW_CONFIG.json two-field edit (default_workflow_version and supported_versions together), the Workflow-Activation: 2.2 / Workflow-Rollback: 2.2 trailer discipline, and that validate_config refuses an edit to only one of the two fields; 2.5.0's own shipped templates/docs/ai-workflow/WORKFLOW_CONFIG.json stays at "2.1", unchanged from 2.4.0's, so a fresh 2.5.0 install is not "2.2"-enabled without that explicit act (finding I1's own template question, decided); CP1's registry entry additionally states, verbatim rather than only in §2.2's design text (resolves `LOCAL_MODEL_PLAN_REVIEW` round 11, finding I2), both of revision 11's operator-guide obligations: the documented procedure is the hand WORKFLOW_CONFIG.json edit directly, and states explicitly that it is never a call through build_activated_config/build_rolled_back_config; and one sentence records that, after the "2.2" activation commit, a missing or corrupt config is a hard stop rather than a silent fallback -- together with the trailer-value caution round 11's own finding I1 assigns to that same sentence, that the trailer's value must be written as exactly the activated version string, since it is now semantically load-bearing for is_activated's own rollback-trailer-value miss rule; the same operator guide additionally states, in its own dedicated paragraph, that "2.2" is available only to a work item created after a repository activates it -- there is no legal path for an already-existing "1"/"2.1" work item, in this repository or any other, to become "2.2" retroactively, and this milestone adds none (resolves `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I1) -- naming `~/Workspace/workflow-controller`'s own `workflow-controller-generation-1` work item as the concrete instance an operator updating that repository to 2.5.0 must not mistake for automatically upgraded; every addition this checkpoint makes to the overlay's WORKFLOW_V2_PLAN.md lands inside the two new D-* sections above and the carried disposition subsection above -- stated explicitly (added at revision 27, `LOCAL_MODEL_PLAN_REVIEW` round 26, optional finding O3), so that D-Implementation-Review-Stages, D-Implementation-Review-Version-Activation and the carried disposition subsection are exhaustive of what CP1 adds to that document: the version-dependent bundle_generation_target_phase resolver and its widened field-set constants land inside D-Implementation-Review-Stages, and build_rolled_back_config's own rollback-destination design text -- though build_rolled_back_config itself is WF-Activate's pre-existing helper -- lands inside D-Implementation-Review-Version-Activation as that section's own statement of the helper's generalized behavior, never as a standalone edit to a pre-existing section outside either D-* section | - | 4 | 2 |
| CP2 | workflow_state.py plumbing in the overlay: KNOWN_PHASES additions, the generalized activation helpers for a "2.2" target -- including build_rolled_back_config's own rollback destination targeting the version activation superseded ("2.2" -> "2.1") rather than a fixed "1" literal (resolves `LOCAL_MODEL_PLAN_REVIEW` round 7, finding I2, scripts/workflow_state.py:6651) -- the activation/rollback event model widened to be version-aware (resolves `LOCAL_MODEL_PLAN_REVIEW` round 10, finding I1): find_latest_activation_event/is_activated read each trailer's own destination version -- an activation trailer's value directly, a rollback trailer's value resolved through the same explicit predecessor mapping generalizing build_rolled_back_config above -- and is_activated reports true whenever that destination is not "1", so a Workflow-Rollback: 2.2 commit (destination "2.1") still reports activated and a Workflow-Rollback: 2.1 commit (destination "1") still reports not activated, matching "2.1"'s existing binary behavior exactly at that boundary while closing the second, previously-silent boundary a "2.2" rollback opens; load_config's raise message (scripts/workflow_state.py:6693-6696) and ConfigMissingAfterActivationError's own docstring (:727-730) generalized off the hard-coded "Workflow v2.1" text to name the resolved destination version when one exists, and the unresolved trailer's own value verbatim in the miss case (taken as `LOCAL_MODEL_PLAN_REVIEW` round 13's optional finding 2(a)) -- never a version name that, in the miss case, by construction does not exist; a unit test proving is_activated is true after a Workflow-Activation: 2.2 commit, that load_config raises ConfigMissingAfterActivationError (never default_config()) when the config is missing at that point, and that after a Workflow-Rollback: 2.2 commit is_activated is still true with load_config's missing-config behavior unchanged -- governing-version validation updates, new implementation-review-stage exception classes (reusing the already stage-agnostic WrongReviewerRoleError / StaleReviewContentIdError / check_manual_stage_bundle_id_advisory rather than duplicating them), and implementation_review_stages ledger normalize/read helpers mirroring normalize_plan_review_stages; unit tests for this pure plumbing; a declaration-coverage unit test asserting every CP1-CP13 deliverable path this item's own implementation-review-two-stage-artifacts.json declares classifies protected (never UnclassifiedPathError, never excluded) and that compute_review_content_id_implementation_stage no longer raises for this item; **plan-review-version inheritance widening (resolves `LOCAL_MODEL_PLAN_REVIEW` round 5, finding B1)**: a single named membership constant, `TWO_STAGE_PLAN_REVIEW_VERSIONS = {"2.1", "2.2"}`, replacing the exact `governing_workflow_version == "2.1"`/`!= "2.1"` literal at `publish_plan_revision` (`:7457-7465`, routes "2.2" to AWAITING_LOCAL_PLAN_REVIEW), `plan_approval_gate_reachable` (`:10078`), `_require_v2_1_plan_review` (`:11753`) and `_validate_plan_review_stages` (`:12160`); a parametrized unit test over ("1", "2.1", "2.2") pinning each site's answer per version, including that "1" and "2.1" are byte-unchanged; transition_to_awaiting_local_plan_review's own docstring (`:11941`) corrected from "`/apply-plan-review`'s `"2.1"`-only revised exit step" to state the exit step is `"2.1"`/`"2.2"` alike (resolves `LOCAL_MODEL_PLAN_REVIEW` round 6, optional finding 2); the version-aware event model's rollback-trailer-value miss additionally resolves fail-closed -- the predecessor mapping's declared domain is "2.1" -> "1" and "2.2" -> "2.1" (domain stated explicitly, resolves `LOCAL_MODEL_PLAN_REVIEW` round 12, finding I1), so a Workflow-Rollback: 2.1 trailer is a found destination of "1" (not activated, unchanged) and only a value outside that domain (a bare/empty value, a typo, or an unrecognized future version) reaches the miss branch: an unresolvable Workflow-Rollback trailer value reports activated, never a silent fall-through to not-activated and never an uncaught KeyError out of load_config (resolves `LOCAL_MODEL_PLAN_REVIEW` round 11, finding I1) -- and CP2's site list for the "2.1"-literal generalization additionally includes AlreadyActivatedError's and NotActivatedError's own docstrings (:733-736, :739-743), taken as round 11's optional finding 1; the unit test proving the version-aware event model additionally proves the miss rule (a bare/empty rollback-trailer value and an unknown version such as "2.9"), per round 11's own required test; a regression test proving that activating "2.2" (via the generalized helper or the supported hand edit to WORKFLOW_CONFIG.json.default_workflow_version) changes only default_work_item's own output for a *subsequently* created work item or remediation child, and mutates no already-existing work_items[...] entry's governing_workflow_version in WORKFLOW_STATE.json (resolves `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I1's own required test) | CP1 | 3 | 1 |
| CP3 | workflow_state.py review-stage writers and gate widening: record_local_implementation_review, record_manual_implementation_review, validate_local_implementation_review_preconditions, validate_manual_implementation_review_preconditions, technical_approval_gate_reachable widened with a "2.2"-only ledger check mirroring plan_approval_gate_reachable (no separate transition_to_awaiting_local_implementation_review writer -- record_bundle_generation's own version-dependent resolver is the sole writer for both entries into AWAITING_LOCAL_IMPLEMENTATION_REVIEW, first-round and post-fix alike, resolves I1); enter_applying_review_feedback left byte-unchanged for "1"/"2.1" and not called at all for "2.2" (the review-stage REVISE writers set APPLYING_REVIEW_FEEDBACK directly, mirroring the plan side); a version-dependent bundle_generation_target_phase(stage, governing_workflow_version) resolver replacing record_bundle_generation's and validate_bundle_generation_record_commit's hard-coded AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW literal in both the ordinary-role and recovered-role checks; RECOVERED_BUNDLE_GENERATION_RECORD_LEGAL_SOURCE_PHASES additively widened to the two new "2.2" phases, still retaining the terminal AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW phase (resolves B1(a)); separately, the recovery command's own phase guard widened to all three phases a "2.2" item can occupy between T and approval -- the two new phases plus the terminal phase, since that terminal phase is the one phase from which record_bundle_generation's own legal source phases are otherwise unreachable without re-entering a remediation cycle (resolves B1(a) and round-4 finding B1); the recovered role's committed-phase clause replaced by a membership test, bundle_generation_recovered_role_legal_committed_phases(governing_workflow_version) -- the resolver's own single value for "1"/"2.1", the identical three-phase set for "2.2", since recovery never changes phase -- while the ordinary role keeps single-valued equality (resolves B2 and round-4 finding B1); the resulting invariant stated explicitly: for the recovered role, the command guard and the committed-phase set are the same set, and both are a subset of the additively-widened parent-phase set; both ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS and RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS widened to include implementation_review_stages, since record_bundle_generation(outcome="same_content") -- the ordinary REVISE loop's own same-content republication, no recovery command involved -- produces a recovered-role (Workflow-Supersedes-trailer) commit exactly like /recover-implementation-provenance's own commit, so both field-set constants gate a "2.2" item's stale ledger residue (resolves B1(b) completely, correcting revision 3's widening of only the ordinary constant); unit tests mirroring the plan-review-stage suite's coverage shape (APPROVE/REVISE/BLOCK write sets, staleness, duplicate ingestion, missing-local-approval); a unit test proving implementation_provenance_interval_reachable/verify_implementation_provenance_interval's HEAD == T requirement is unaffected by a local-APPROVE + manual-APPROVE implementation_review_stages ledger-write sequence for a "2.2" item, extended to assert T's own committed phase and the REVISE-loop round where T is created after an uncommitted ledger write; a recovered-role field-diff test (both the record_bundle_generation(outcome="same_content") shape and /recover-implementation-provenance's own commit), a recovered-role committed-phase test (recovery from each of the three phases a "2.2" item can occupy between T and approval) pinning B1(b), B2's and round-4 finding B1's fixes, and a negative test that the widened "2.2" sets change no "1"/"2.1" recovery refusal; a "post-fix"-from-AWAITING_FUNCTIONAL_REVIEW unit test for a "2.2" item pinning the resolver's target phase (resolves I2's unit-level pin); the governing_workflow_version-absent rule (absent means the "1"/"2.1" literal, never a raise) stated and tested for both resolvers; promote_legacy_work_item's own docstring justification (corrected at revision 11, `LOCAL_MODEL_PLAN_REVIEW` round 10, finding I3) (`:12097-12101`) corrected to state that legacy adoption deliberately promotes to `"2.1"`, never the current default, because the adopted item is already past both implementation-review stages (resolves `LOCAL_MODEL_PLAN_REVIEW` round 6, optional finding 1); a new regression test (added at revision 16, `LOCAL_MODEL_PLAN_REVIEW` round 15, missing test 2) proving `promote_legacy_work_item` still promotes a legacy item to the literal `"2.1"`, never `config["default_workflow_version"]`, once a repository has separately activated `"2.2"` as its own default -- pinning that the adoption destination is the literal named in the corrected docstring above, not the current default | CP2 | 5 | 3 |
| CP4 | Command updates in the overlay: /review-implementation.md gains a "2.2" authoritative branch (phase guard AWAITING_LOCAL_IMPLEMENTATION_REVIEW, ledger write plus phase transition on APPROVE/REVISE; its existing "1"/"2.1" advisory branch stays byte-unchanged); new /record-manual-implementation-review.md mirroring /record-manual-plan-review.md; /apply-implementation-review.md gains a "2.2" branch (no enter_applying_review_feedback call; step 7's post-fix regeneration reaches AWAITING_LOCAL_IMPLEMENTATION_REVIEW via record_bundle_generation's own version-dependent resolver, not a second writer, resolves I1); its own existing "1"/"2.1" step-0 dual-mode enumeration stays byte-unchanged, correctly, mirroring the note already stated for /review-implementation.md's own advisory branch above (resolves `LOCAL_MODEL_PLAN_REVIEW` round 8, optional finding 3); /approve-review.md's implementation branch gains the restated implementation_review_stages ledger-check invariant mirroring its existing plan_review_stages check, and corrects step 0's stale claim that the "2.1" plan-ledger branch is inert only because this repository's own work item is fixed at "1" (untrue: this repository now has two "2.1" work items); /milestone-implement.md's step performing record_bundle_generation(stage="implementation") documented against the version-dependent target phase; /apply-functional-review.md's bounded-fix branch (technical_approval.status == "STALE", entered from AWAITING_FUNCTIONAL_REVIEW) documented as resolving, for a "2.2" item, to AWAITING_LOCAL_IMPLEMENTATION_REVIEW via the same post-fix resolver -- a "2.2" functional bounded fix re-enters both implementation-review stages before /approve-review implementation is reachable again (resolves I2); /recover-implementation-provenance.md's own stated phase guard updated to name all three phases a "2.2" item can occupy between T and approval (the two new phases plus the terminal AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW phase) and the recovered-role committed-phase membership test explicitly, and to state that the command guard and committed-phase set are identical (resolves round-4 finding B1); WORKFLOW_V2_1_OPERATOR_REFERENCE.md's phase and command tables updated; the plan-stage command-contract documents' own two-version ("1"/"2.1") enumerations widen to include "2.2" alongside "2.1" (resolves `LOCAL_MODEL_PLAN_REVIEW` round 5, finding B1): /milestone-plan.md (`:59-67`), /apply-plan-review.md (`:41`, `:135`), /approve-review.md (`:62-64`, `:97`), /review-plan.md (`:39`), /record-manual-plan-review.md (`:46`), and /request-plan-amendment.md (`:21-25`, whose own "downstream /milestone-plan re-entry" sentence names /milestone-plan's two-branch set); plan-review inheritance widening, round 6 (resolves `LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1(a)/(c)): /milestone-implement.md's step 0 branch set states a "2.2" item takes the "2.1" branch, as an item distinct from this checkpoint's own record_bundle_generation(stage="implementation") documentation item above; /accept-milestone.md:43-49, /review-functional.md:61-64 and /prepare-functional-review.md:47-51 restate their version-independence sentences to include "2.2" alongside "1"/"2.1"; /apply-functional-review.md:227-231's remediation-child sentence states that a "2.2" child enters review at AWAITING_LOCAL_PLAN_REVIEW identically to a "2.1" child; round-7 plan-review inheritance widening (resolves `LOCAL_MODEL_PLAN_REVIEW` round 7, finding B1(e)/(g)), as items distinct from this checkpoint's existing "phase and command tables" item: WORKFLOW_V2_1_OPERATOR_REFERENCE.md's own governing-version overview (:21-24, "Two governing versions" restated as three) and its AWAITING_LOCAL_PLAN_REVIEW/AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW precondition lines (:229, :246, "`"2.1"` only" restated as the `"2.1"`/`"2.2"` membership); /review-plan.md:2 and /record-manual-plan-review.md:2's own frontmatter description: lines, dropping the "(`"2.1"` work items only)" framing to match their own in-body guards (:39, :46) this checkpoint already widens; round-7 optional finding 2: every dual-mode command's step 0 branch set (/apply-plan-review, /milestone-implement, /apply-implementation-review, /review-implementation, /record-manual-implementation-review) gains an explicit "any other governing_workflow_version: refuse, naming it" final branch | CP3 | 4 | 2 |
| CP5 | Convergence / token-efficiency measures, narrowly scoped: state explicitly, and test, that no bundle regeneration occurs between the local-approve and manual-external stages (the same bundle_id carried through, mirroring the plan side's rule); tighten /review-implementation's "2.2" independent-verification bar to be at least as rigorous as today's combined self-review plus advisory pass; a disposable-repo fixture scenario demonstrating a planted defect is caught by the local stage without consuming a manual-external round | CP4 | 3 | 1 |
| CP6 | Review-scalability, branch 1 (added revision 3): author D-Review-Material-Lifecycle into the overlay's WORKFLOW_V2_PLAN.md -- the normative-vs-historical-disposition convention (current design text stays free of inline revision-correction narrative; one or more disposition sections, each explicitly classified HISTORICAL, carry provenance instead), explicitly deciding no physical move of existing docs/ai-workflow/ content this milestone (no repository-analysis support for a specific folder scheme, per D-Review-Material-Lifecycle's own reasoning); **revised at revision 21** (user-directed architectural correction, applying together with `LOCAL_MODEL_PLAN_REVIEW` round 20's own convergence recommendation, which independently reached the same conclusion -- full history of revisions 15-20's heading/prose-inference design, superseded by this revision, is retained at the plan's own §7 revision-21 disposition entry): CP6's mechanical lint moves from inferring lifecycle status out of heading text/level/position to explicit lifecycle classification -- classification, where present, is always by explicit marker the author writes, never inferred from prose or heading structure (narrowed at revision 26, `LOCAL_MODEL_PLAN_REVIEW` round 25, finding I2, from "every unit... carries an explicit marker": that wider, authorship-scoped subject was unevaluable and stood beside the marker-presence obligation below asserting a different, narrower, evaluable subject; the marker-presence obligation below is now the sole statement of which units must carry a marker); a unit with no marker, or an unparseable/ambiguous one, is classified CURRENT (fail-closed default: classification can only narrow what a reviewer sees, never silently widen what a reviewer does not see); CURRENT -> HISTORICAL is only ever an explicit, intentional marker edit affecting material -- never a side effect of any other edit, including an edit that redraws which unit material belongs to without itself changing a marker (restated over material rather than units at revision 22, `LOCAL_MODEL_PLAN_REVIEW` round 21, finding I3, closing the merge-direction gap: folding a CURRENT region into an adjacent HISTORICAL-marked unit by deleting or demoting the heading between them, with no marker edit, must not report that material HISTORICAL); a unit classified CURRENT never carries the inline "revision N corrected finding X"-shaped provenance narrative D-Review-Material-Lifecycle point 1 forbids, with no corresponding requirement on HISTORICAL material (added at revision 22, `LOCAL_MODEL_PLAN_REVIEW` round 21, finding I1: without this, points 1-2's own substance was enforced by nothing, and CP1's carry sentence's appeal to "CP6's lint" had nothing behind it); the marker is machine-checkable independently of the prose it classifies, with its concrete representation -- one canonical `render_marker`/`parse_marker` machine-readable definition, restricted to exactly the two-member state domain {CURRENT, HISTORICAL}, never a written instance alone and never a second hand-maintained prose grammar (revised at revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I2) -- fixed by CP1, as part of CP1's own deliverable, no later than CP1 time (reassigned at revision 29, `LOCAL_MODEL_PLAN_REVIEW` round 28, finding B1, resolution 1); the lint built against the parser, and the concrete textual shape treated as forbidden narrative above, remain left to this checkpoint's own implementation -- the parser itself is CP1's own `parse_marker`, imported by CP6 rather than re-derived (narrowed at revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2, from "the parser that reads it, the parsing grammar, and the concrete textual shape treated as forbidden narrative above remain left to this checkpoint's own implementation"); a separate, mechanically-evaluable marker-presence obligation (added at revision 25, `LOCAL_MODEL_PLAN_REVIEW` round 24, finding I1; narrowed to a pure presence obligation, and widened, at revision 28, user-directed architectural correction applying together with round 27's findings B1/I1/I2) requires every unit within a marker-presence scope -- the whole of IMPLEMENTATION_REVIEW_WORKFLOW.md; every top-level WORKFLOW_V2_PLAN.md design section any checkpoint's own registry entry adds -- today D-Implementation-Review-Stages and D-Implementation-Review-Version-Activation (CP1) and D-Review-Material-Lifecycle itself (CP6) -- (widened from "CP1's own registry entry adds" at revision 28, finding I2: the prior wording excluded CP6's own defining section from the obligation it defines) -- each in full, with a nested unit such as CP1's carried 2.5.0-scoped disposition-record subsection reached once, through its container's "in full" reach, never as a separately enumerated peer (corrected at revision 28, finding I1: naming it a third, nested member of a scope whose other two members already contained it was both wrong and the proximate cause of finding B1) -- to carry an explicit marker of either value; a unit within that scope carrying none is a lint failure, reported independently of and never disturbing the fail-closed classification default above, which still classifies that same unit CURRENT unaffected; this obligation never derives which value a unit's marker must hold from who authored the unit, whether it is new, or which named section it sits under -- that is guarantee (iii)'s classification default and the unit author's own explicit choice alone (stated explicitly at revision 28); CP6 writes the markers this obligation requires that are still missing, as part of this checkpoint's own deliverable (added at revision 27, `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I2; scoped to unmarked units only, at revision 28, round 27 finding B1: CP1 authors both D-* subjects and no checkpoint before this one was ever assigned to write the markers this obligation then requires on them -- but CP1's own carried disposition-record subsection already carries an explicit HISTORICAL marker by CP1's own deliverable, so revision 27's blanket "every unit ... CURRENT" instruction collided with it directly): using the same canonical render_marker/parse_marker definition CP1 has already fixed (reassigned at revision 29, finding B1, resolution 1: CP6 no longer chooses the representation, since CP1's own marker must exist in it before CP6 runs at all; the definition is canonical rather than a written instance alone as of revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I2), CP6 marks CURRENT every unit, within the scope stated above, that does not already carry an explicit marker of its own; CP6 never overwrites or reclassifies an already-marked unit, whatever its value -- CP1's disposition-record subsection's own HISTORICAL marker discharges this obligation for that unit and is left untouched; this marking pass is distinct from -- and never bounded by -- the sweep-flagged carve-out below, and it reasons only about which in-scope units already carry an explicit marker, never about which units are "new material CP1 authored" versus pre-existing; CP6 proves the mechanism, not merely asserts it, with fixtures covering -- every fixture in this list blocking CP6's own completion, stated once here rather than per-fixture (added at revision 31, round 30 optional finding O2) -- a positive case (explicit CURRENT material stays review-visible), a negative case (explicit HISTORICAL material is excluded from review-visible surface), an ambiguous case (unmarked or malformed-marker material fails closed to CURRENT), a two-version transition case (added at revision 23, finding I4, restating round 21's own outstanding missing test 1: a non-marker edit -- heading reword, prose restructure -- leaves every unit's reported classification unchanged across two fixture versions; a marker-only edit alone performs the CURRENT -> HISTORICAL transition), a boundary-redrawing case (added at revision 22, finding I3: merging a CURRENT region into an adjacent HISTORICAL-marked unit by deleting or demoting the heading between them, with no marker edit, must not report that material HISTORICAL), a narrative-location case (added at revision 22, finding I1: the forbidden narrative inside CURRENT material fails the lint; the identical narrative inside HISTORICAL material passes), a scope case (added at revision 23, discriminator restated at revision 24, finding I1: an unmarked pre-existing section carrying the forbidden narrative must pass, since it is CURRENT only by the fail-closed default -- carrying no explicit marker -- and is therefore outside guarantee (vi)'s reach, whose mechanical basis is that guarantee (vi) applies only to a unit carrying an explicit CURRENT marker), a carve-out-bound case (added at revision 23, finding I3, restating round 21's own outstanding missing test 4: a pre-existing disposition-titled section containing only occurrences the governing-version sweep below does not flag must not be marked HISTORICAL by CP6's own deliverable, and the corpus regression below must fail if it is), a marker-presence fixture (added at revision 25, finding I1: an in-scope unit carrying no marker must fail the marker-presence obligation above, unaffected by and never disturbing the ambiguous fixture's own CURRENT classification verdict for the same unmarked input; one-corpus-shaped for WORKFLOW_V2_PLAN.md (restated at revision 26, finding I3, and for the widened scope at revision 28, finding I2: a fixture unit inside one of the in-scope sections, unmarked, must fail; a fixture unit elsewhere in the same fixture document, unmarked, must pass), mirroring §2.4 point 3's own statement of the same fixture); an already-marked-nested-unit fixture (added at revision 28, round 27 finding B1, required test 1: an in-scope unit already carrying an explicit HISTORICAL marker, nested inside another in-scope unit, must survive CP6's own marking pass unchanged -- not overwritten, reported satisfied for the marker-presence obligation by presence alone, and not failing the narrative-content guarantee); a representation-conformance fixture (added at revision 29, round 28 finding B1, required test 1: CP1's own disposition-record subsection, in the fixture, carries its HISTORICAL marker written in exactly the representation CP1 fixes, and CP6's own parser, built against that same fixed representation, recognizes it as an explicit marker rather than defaulting it to CURRENT; widened at revision 31, round 30 finding I1, resolution 1, to additionally assert the exclusivity direction: a mutated copy of the fixture's marker, written in a form outside CP1's fixed representation, must not be recognized as an explicit marker and must instead fall to the CURRENT fail-closed default; widened again at revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I2's own required test, to exercise the canonical render_marker/parse_marker pair directly rather than only CP1's one written instance: parse_marker accepts render_marker("HISTORICAL")'s own output as HISTORICAL, accepts render_marker("CURRENT")'s own output as an explicit CURRENT marker distinct from the fail-closed default a missing marker also classifies CURRENT, and rejects representative malformed/out-of-contract forms -- a mutated delimiter, a third state value, truncated or duplicated marker text -- back to the CURRENT fail-closed default; CP1's own written instance and every marker CP6's marking pass writes are additionally required to equal render_marker's own output bytes for their respective state, a mechanical equality check rather than a second grammar comparison; and asserting that CP6's own lint reaches its CURRENT/HISTORICAL/malformed classification verdicts by calling this same parse_marker, so a lint whose own grammar tolerates a form outside the canonical pair cannot pass with the fixture green (added at revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2's own missing-test note)); a pre-marking-partition fixture (added at revision 30, `LOCAL_MODEL_PLAN_REVIEW` round 29, finding B1, resolution 2, missing test 1: a corpus-shaped fixture document containing one unit already carrying an explicit HISTORICAL marker -- mirroring CP1's own disposition-record subsection -- alongside units carrying no marker at all; the check run against it must classify the marked unit HISTORICAL and every unmarked unit CURRENT, and a mutated copy asserting every unit classifies CURRENT, the marked one included, must fail; being a fixture rather than a one-shot real-corpus read, it survives CP6's own marking pass and so remains available to catch a future edit that re-widens guarantee (v), which the real-corpus read below cannot, since that read's own pre-marking moment stops existing in the worktree once CP6 completes); a real-corpus run of the finished marker-presence check itself, over every one of that obligation's actual subjects -- IMPLEMENTATION_REVIEW_WORKFLOW.md in full and every top-level WORKFLOW_V2_PLAN.md section any checkpoint's registry entry adds, D-Review-Material-Lifecycle itself included (widened at revision 28, required test 2 of finding I2) -- as part of CP6's own completion requirement, once CP6 has written the markers this checkpoint assigns itself above (added at revision 27, `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I2's own required test, distinct from the guarantee (v) classification-partition regression below); and that guarantee (v) partition regression run of the finished lint against migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md's own, real existing corpus, run after CP6 has made its carve-out-bound markings (post-marking, distinct from guarantee (v)'s own pre-marking read of that same tree at §2.4 point 3 and §6 -- the two states named explicitly at revision 27, `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I3) (corpus and timing corrected at revision 24, finding I2: revision 23 named the built distribution/workflow/2.5.0/ payload, which CP11 builds only after CP6 and so does not exist while this checkpoint's own blocking fixture would need to run against it; CP1 and CP6 both author this overlay file directly, so it exists when CP6 runs; CP6's own read of this overlay-payload tree is never repeated a second time against the built distribution/workflow/2.5.0/ payload -- "single run" names that omission, restated at revision 27 to mean exactly that (revision 25, finding I2, resolution 1), transferred to the built distribution/workflow/2.5.0/ payload by build_release.py --check's own byte-identity proof (CP11) rather than asserted there a second time) proving the lint's introduction reclassifies none of that corpus's existing content as HISTORICAL except where CP6 has deliberately and visibly marked a pre-existing section HISTORICAL as part of this checkpoint's own deliverable (carve-out restated to match D-Review-Material-Lifecycle's own regression-run carve-out at revision 22, finding I2), asserting the classification partition only, never the narrative-content guarantee -- any reclassification not traceable to such a deliberate marker addition is a fixture failure blocking this checkpoint's own completion; the carve-out's own bound is corrected at revision 23 (finding I3: bounded by the sweep's own flagged output computed at CP6 implementation time against that same overlay-payload tree -- tree named explicitly at revision 24, finding I2 -- never the hand-measured "9 sections / 24 occurrences" proxy retained below only as a scale indication, since at least two of the 24 proxy-counted occurrences are not occurrences of either of the sweep's own two detection forms); CP6's own D-Review-Material-Lifecycle section and CP1's carried subsection are covered by the same positive/negative fixture pair as any other unit, with no special-cased predicate for the document's own required provenance content; a mechanical governing-version enumeration sweep (resolves `LOCAL_MODEL_PLAN_REVIEW` round 6's "Missing tests" item; predicate and allowlist corrected at revision 8, round 7, finding B1(a)): a lint over the built release payload's own .claude/commands/*.md and docs/ai-workflow/*.md asserting that no document presents a "2.1" governing-version reference as exhaustive of the two-stage plan-review protocol's own applicability, in either of two textual forms -- the {"1", "2.1"}-exhaustive-enumeration form, or the bare "2.1"-scoped-assertion form (`"2.1"` only, "Scoped entirely to `"2.1"`", etc.) that never mentions "1" at all, which round 7 found to be the dominant, previously-undetected form; an allowlist at occurrence granularity, not whole-document grant, exempting only an occurrence inside a section explicitly classified HISTORICAL -- including, at revision 22 (`LOCAL_MODEL_PLAN_REVIEW` round 21, finding I2), any pre-existing disposition-titled section of WORKFLOW_V2_PLAN.md that the sweep itself flags (approximately 9 sections / 24 occurrences by a hand-measured proxy against the 2.4.0 payload -- payload named explicitly at revision 24, finding O2 -- corrected at revision 23, finding I3: the exact set is the sweep's own flagged output computed at CP6 implementation time against migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md -- tree named explicitly at revision 24, finding I2, since the built distribution/workflow/2.5.0/ tree does not exist until CP11 builds it -- never this proxy, since at least two of the 24 proxy-counted occurrences are not occurrences of either of the sweep's own two detection forms): CP6 marks each such sweep-flagged section HISTORICAL as a deliberate, diff-visible act of this checkpoint's own deliverable, never a silent or automatic reclassification, and never a section the sweep's own output does not flag -- plus a whole-document exemption for the three named genuinely-closed history documents (WORKFLOW_V2_3_PLAN.md, WORKFLOW_V2_3_FOLLOWUPS_PLAN.md, WORKFLOW_V2_AUDIT.md) -- narrowed at revision 15 (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I2) to drop WORKFLOW_V2_PLAN.md from the whole-document list: unlike those three, §2.4 itself classifies WORKFLOW_V2_PLAN.md as the single active design-of-record, still growing with every authored release's own CP1-style design checkpoint (this milestone's own CP1 among them), so a whole-document grant would suppress the sweep inside the very current/normative sections REQ-15 requires it to cover, not only inside genuinely historical prose; WORKFLOW_V2_PLAN.md's own occurrences are therefore exempt only occurrence-by-occurrence, inside sections explicitly classified HISTORICAL, identically to every other non-exempt document, never by the file's name alone; a negated or version-independence assertion (e.g. "this is not a "2.1"-only mechanism") is not an occurrence of either detection form at all, not a third allowlist entry (resolves `LOCAL_MODEL_PLAN_REVIEW` round 8, finding I1); the sweep's own allowlist-pin negative fixture: a WORKFLOW_V2_PLAN.md-shaped document carrying a stale "2.1"-only claim inside a new current design section not classified HISTORICAL, which must fail even though the file's own historical sections stay exempt, doubling as the executable check on the three-document whole-document allowlist just narrowed above; MILESTONE_WORKFLOW.md:424 and apply-functional-review.md:34 are this shape and stay unreworded; WORKFLOW_V2_1_OPERATOR_REFERENCE.md's own "## Known discrepancies" section is explicitly in the lint's scope, not a section classified HISTORICAL, so CP6's catch-all fixes every stale bare-"2.1" occurrence the section contains -- not only :882/:892, but also :853-854 and :866; at least one further positive fixture (a document whose only occurrence is a negated/version-independence assertion) accompanies the existing per-form fixtures; CP6, running after CP1 and CP4 in the registry's own listed checkpoint order, additionally widens in place any further site its own lint flags beyond CP1's and CP4's own named fixes above, rather than leaving the lint red or duplicating either's work; inside a pre-existing disposition section of WORKFLOW_V2_PLAN.md, this catch-all's remedy is a HISTORICAL marker, never a reword (added at revision 23, usability finding), since a reword of closed historical prose is exactly the harm D-Review-Material-Lifecycle exists to prevent, and the enumerated carve-out above cannot be exact by construction (finding I3). | CP1 | 3 | 1 |
| CP7 | Review-scalability, branch 2 (added revision 3): extract one generic, parametric declaration-coverage helper (overlay's own scripts/workflow_state_test.py shared test support or a new small overlay module) generalizing the bespoke per-work-item declaration-coverage test pattern this item's own CP2 and plan-amendment-mechanism each hand-authored separately (D-Canonical-Review-Data); document the already-mechanically-discovered surface_census/verifier_census mechanism in workflow_state_completion_obligations_test.py as the precedent model, not a second defect; this item's own CP2 test and plan-amendment-mechanism's own existing test are left as-is (out of scope to retrofit an already-approved item's test file) | CP2 | 3 | 1 |
| CP8 | Review-scalability, branch 3 (added revision 3): author D-Review-Finding-Taxonomy-and-Circuit-Breaker into the overlay's REVIEW_PROTOCOL.md -- an advisory (not parser-enforced -- malformed or missing tags are never rejected, and default to [substantive] for circuit-breaker purposes, resolves I5) [substantive]/[apparatus] tag on every Blocking/Important REVIEW_FEEDBACK.md finding, with REVIEW_PROTOCOL.md's existing resolve-or-reject-with-evidence rule unchanged regardless of tag; plus an advisory (never phase-gating, no governing-version bump) circuit-breaker signal a reviewer's report states after 2 consecutive apparatus-only REVISE rounds for the same stage -- fixed at 2, the mechanism's own ceiling given REVIEW_FEEDBACK.md's single-round visibility, not an open decision (resolves I6); **scoped explicitly to two consecutive same-stage LOCAL_MODEL_PLAN_REVIEW (or LOCAL_MODEL_IMPLEMENTATION_REVIEW) REVISE rounds only -- corrected at revision 15 (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I3)** -- the single-prior-`REVIEW_FEEDBACK.md`-visibility mechanism the signal relies on holds for two consecutive local-model rounds (the same reviewing command reads the immediately-prior file before overwriting it) but not for two consecutive manual-external rounds, since a fresh required local pass (§2.1) overwrites that same stage-agnostic path before the next manual reviewer ever sees the prior one, and no durable, finding-classification-bearing ledger entry survives a REVISE round to recover it; `REVIEW_PROTOCOL.md`'s own added text states explicitly that it makes no corresponding claim for consecutive manual-external rounds, which remain operator judgment as they already are today; a test proves the signal fires after two consecutive local apparatus-only rounds for each stage, and a second test proves `REVIEW_PROTOCOL.md`'s own text makes no manual-external recoverability claim | CP1 | 3 | 1 |
| CP9 | Post-v2.3.1 backlog, tractable fixes (added revision 3, D-Post-v2.3.1-Backlog): in the overlay, fix v2.3.1-003 (pin_plan_approval_state_blob defaults to mode 100644 when no HEAD blob exists, instead of refusing unconditionally -- the first of the defect record's own two stated portable forms); fix v2.3.1-001 (test_the_historical_status_note_carries_a_dated_correction skips cleanly when no host status note is present, instead of raising StopIteration); migration/portability_exceptions.json gains a required, empty by_version["2.5.0"] entry (tests/support.py's expected_portability_exceptions subscripts by_version[workflow_version] unguarded, so an absent key is a KeyError, not a pass) -- 2.3.1's and 2.4.0's own by_version entries for this test are untouched, since both releases' payloads still carry the unfixed test and 2.3.1 is frozen (corrects revision 3's "entry is removed" framing, finding I4); widen v2.4.0-001 further (generate_artifacts_declarations' implementation-stage default excluded_prefixes gains .workflow-manager/, symmetric with the plan-stage default the 2.4.0 fix already widened) -- forward-only, no existing work item's own already-generated declarations file is edited; regression tests for all four; CP11's release-authoring migration notes state the v2.4.0-001 widening as guidance for any updating repository, not only this one's own mitigation (resolves round 2's optional finding 2) | CP2 | 4 | 2 |
| CP10 | Post-v2.3.1 backlog, v2.4.0-002 reconsideration (added revision 3, D-Post-v2.3.1-Backlog): produce this milestone's explicit, written reconsideration of v2.4.0-002 (cross-worktree amendment/claim race) -- continue deferring both full structural fixes (a claims_dir-rooted lock; a repo-global phase witness), recorded with updated reasoning tied to this milestone's own review-tooling mission rather than by omission; record the cheap IMPL10-O1 partial mitigation (a second resolve_claim re-check immediately before request_plan_amendment's own supersede) as a live optional adoption, -- **resolved at revision 15** (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, required acceptance criterion 4): **declined**, deferred together with both full structural fixes, for the same reason the defect record itself already gave when it first declined this exact option (round 10, under review pressure, in the same round the residual was found); this checkpoint's deliverable is the written disposition alone, no code change | CP1 | 2 | 1 |
| CP11 | Release-authoring: migration/overlays/2.5.0/classification.json plus payload (new files, full replacements of every base-release payload file this release changes, per CLAUDE.md's authored-release process); python3 tools/build_release.py --overlay migration/overlays/2.5.0 and --check reproducing distribution/workflow/2.5.0/ from the 2.4.0 base plus the overlay; tests/support.py's per-release CI_SUITES entry for 2.5.0; migration/portability_exceptions.json's required by_version["2.5.0"] entry (empty exceptions list; not conditional -- tests/support.py's unguarded by_version[workflow_version] subscript means an absent key fails closed as a KeyError, not a pass), leaving 2.3.1's and 2.4.0's own entries untouched (corrects revision 3's "if this release's own suite needs one" framing, finding I4); every payload document the sweep requires changing (resolves `LOCAL_MODEL_PLAN_REVIEW` round 8, finding I2 -- widened from "every payload document CP1's or CP4's own round-6/round-7 plan-review inheritance widening requires changing" so the recorded scope also covers CP6's own catch-all fixes) becomes one more full-replacement overlay payload file in migration/overlays/2.5.0/payload/, each with its own reproducible overlay_delta (resolves `LOCAL_MODEL_PLAN_REVIEW` round 7, finding B1's required acceptance criterion 6/point 3: stated generally rather than by name, since a named list is exactly the pattern round 7 found short a fourth time) | CP1, CP2, CP3, CP4, CP5, CP6, CP7, CP8, CP9, CP10 | 5 | 2 |
| CP12 | Disposable-repository functional validation: bootstrap a disposable repo directly on 2.5.0, drive the "2.2" activation by following CP1's documented IMPLEMENTATION_REVIEW_WORKFLOW.md procedure verbatim, with no repository-internal shortcut (resolves `LOCAL_MODEL_PLAN_REVIEW` round 10, optional finding 1), run a synthetic work item through the full two-stage implementation-review flow end to end (local APPROVE -> manual APPROVE -> /approve-review implementation) and the negative paths (local REVISE looping back through APPLYING_REVIEW_FEEDBACK, local BLOCK, manual REVISE loop, manual BLOCK, wrong-phase / wrong-version refusals, stale review_content_id, duplicate manual ingestion, advisory-only bundle_id mismatch, /recover-implementation-provenance from each of the three phases a "2.2" item can occupy between T and approval (the two new phases plus the terminal phase), resolving B1(a)'s recovery-path clause, B2's committed-phase membership test, and round-4 finding B1's widening of both to the terminal phase); a "2.2" functional-review bounded-fix scenario (post-fix regeneration from AWAITING_FUNCTIONAL_REVIEW routing through both implementation-review stages again before /approve-review implementation is reachable, resolves I2); update-path validation that a pre-existing repository managed under 2.4.0 with a live "2.1" work item mid-AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW is unaffected by an update to 2.5.0 until it explicitly activates "2.2"; exercise CP7's generic declaration-coverage helper against the synthetic work item directly rather than hand-writing another bespoke copy; exercise CP9's four backlog fixes (mode-100644 fallback, the portable host-note skip, the required empty 2.5.0 portability-exceptions entry, and the widened implementation-stage .workflow-manager/ exclusion) against fresh disposable-repo scenarios; the synthetic "2.2" item's own plan stage first runs the full two-stage plan-review protocol end to end (AWAITING_LOCAL_PLAN_REVIEW -> AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW -> AWAITING_PLAN_APPROVAL, resolves `LOCAL_MODEL_PLAN_REVIEW` round 5, finding B1) before any implementation-review stage is reached, proving B1's plan-side fix end to end and exercising /milestone-plan's own first planning step past what would otherwise crash for an unwidened "2.2" item; between this scenario's plan-stage traversal and its own two-stage implementation-review flow, the synthetic "2.2" item's disposable repo additionally drives /milestone-implement's checkpoint loop from SELF_REVIEWING_IMPLEMENTATION through step 2's enter_self_reviewing_implementation write to its own record_bundle_generation(stage="implementation") call, asserting the committed phase at T is AWAITING_LOCAL_IMPLEMENTATION_REVIEW (resolves `LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1's own second "Missing tests" item) | CP11 | 5 | 3 |
| CP13 | Full regression (python3 tests/run_all.py) and downgrade-posture documentation: extend this repository's own CLAUDE.md downgrade-posture paragraph to name 2.5.0's new vocabulary (AWAITING_LOCAL_IMPLEMENTATION_REVIEW, AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW, implementation_review_stages, governing_workflow_version "2.2") among the values an older release's workflow_state.py cannot read back; record this milestone's actual disposition of the four previously-deferred defects per section 8 (three fixed -- v2.3.1-001, v2.3.1-003, v2.4.0-001's implementation-stage symmetry widening -- one, v2.4.0-002, explicitly reconsidered and still deferred in full, including the optional IMPL10-O1 mitigation, per section 9's resolved decision 3) | CP12 | 2 | 1 |

## 4. Requirements traceability

Generated via `workflow_state.generate_mapping` into
`docs/ai-workflow/requirements/implementation-review-two-stage-mapping.json`,
validated for bidirectional registry↔mapping coverage at generation time.

| Requirement | Description | Checkpoints |
|---|---|---|
| REQ-1 | A two-stage local-then-manual-external implementation-review protocol exists, gated behind a new governing_workflow_version ("2.2"), with zero change to "1"/"2.1" review/lifecycle behavior in the protocol and version-gated inheritance surface this milestone adds, CP9's own enumerated forward-only fixes at REQ-12 excepted (narrowed at revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I1) | CP1, CP2, CP3, CP4 |
| REQ-2 | Both stages bind to the same implementation-stage review_content_id; ledger validity is by recomputation; staleness/advisory handling matches the plan side's rules exactly | CP2, CP3, CP4 |
| REQ-3 | /approve-review implementation can never reach EXTERNAL_APPROVE on the strength of a single reviewer pass for a "2.2" item | CP3, CP4 |
| REQ-4 | No bundle regeneration is required between the local-approve and manual-external stages | CP4, CP5 |
| REQ-5 | Review-apparatus churn is reduced: a narrowly-scoped, demonstrated improvement in review convergence / token efficiency | CP5 |
| REQ-6 | The authored 2.5.0 release reproduces byte-identically from the 2.4.0 base plus overlay; 2.3.1 and 2.4.0 remain untouched | CP11 |
| REQ-7 | Disposable-repository functional validation covers the positive path, every negative path, and update-path compatibility | CP12 |
| REQ-8 | Full regression suite is green and downgrade posture is documented for the new vocabulary | CP13 |
| REQ-9 | Review/design material carries an explicit CURRENT or HISTORICAL lifecycle classification -- never inferred from incidental prose wording, heading names, or document structure; unclassified or ambiguous material fails closed as CURRENT (the convention's own definitional statement of classification's two states and its safe default, mirroring §2.4 point 3's "Two explicit states" and "Fail-closed default" bullets -- the definitional form criterion 2 of `LOCAL_MODEL_PLAN_REVIEW` round 25's REVISE feedback left standing; which units must carry a marker at all is the separate, narrower obligation stated below, not this clause -- narrowed at revision 27, `LOCAL_MODEL_PLAN_REVIEW` round 26, optional finding O2); CURRENT -> HISTORICAL is only an intentional, explicit transition of material, never a side effect of an unrelated edit or of redrawing which unit material belongs to (revision 22, finding I3); within the milestone's own authored/marked material -- a unit carrying an explicit CURRENT marker, never a unit CURRENT only by the fail-closed default -- never WORKFLOW_V2_PLAN.md's pre-existing unmarked sections wholesale (scope stated explicitly at revision 23, finding I1; mechanical basis stated at revision 24, finding I1); a separate, mechanically-evaluable presence-only obligation (narrowed at revision 28, user-directed architectural correction applying together with round 27's finding B1: presence and value are independent -- this obligation never derives which value a unit's marker must hold from authorship, novelty, or which named section the unit sits under) requires every unit within a marker-presence scope -- the whole of IMPLEMENTATION_REVIEW_WORKFLOW.md; every top-level WORKFLOW_V2_PLAN.md design section any checkpoint's own registry entry adds, D-Review-Material-Lifecycle itself included (widened from "CP1's own registry entry adds" at revision 28, finding I2) -- each in full, with a nested unit reached once through its container's "in full" reach, never as a separately enumerated peer (revision 28, finding I1) -- to carry an explicit marker of either value, a missing marker there being a lint failure reported independently of and never disturbing the fail-closed classification default (revision 25, finding I1; subject corrected from a cross-corpus diff predicate to this enumerable set at revision 26, finding I3; widened and narrowed to presence-only at revision 28, findings B1/I1/I2); CP6 writes the markers this obligation requires that are still missing, as part of its own deliverable, never overwriting or reclassifying a unit that already carries an explicit marker of its own (added at revision 27, finding I2; scoped to unmarked units only at revision 28, finding B1) -- CURRENT-classified material additionally carries none of the inline provenance narrative excluded from disposition sections, checked over material the marker has already classified CURRENT, independently of the prose the marker classifies (revision 22, finding I1; clause corrected at revision 23, finding O2: "checked independently of the classification marker itself" had the dependency direction backwards -- the content check depends on the marker's own classification, never the reverse) -- enforced by a mechanical check for milestone-authored documents, proved with positive/negative/ambiguous/two-version-transition/boundary-redrawing/narrative-location/scope/carve-out-bound/marker-presence/already-marked-nested-unit/representation-conformance/pre-marking-partition fixtures (the last nine added at revisions 22-25, 28, 29 and 30, findings I4/I3/I1/I1/I3/I1/B1/B1/B1 (corrected at revision 31, round 30 optional finding O1, from "the last eight added at revisions 23-25, 28, 29 and 30, findings I4/I3/I1/I3/I1/B1/B1/B1", which opened with I4 -- two-version-transition's own finding, the ninth-from-last fixture -- while claiming to name only the last eight, and omitted one I1) -- the last, pre-marking-partition, durably pins guarantee (v)'s narrowed form past CP6's own marking pass, resolving round 29's finding B1) plus a real-corpus run of the finished marker-presence check itself, over every one of that obligation's actual subjects, once CP6 has written the markers it assigns itself (added at revision 27, finding I2's own required test; widened to cover D-Review-Material-Lifecycle itself at revision 28, finding I2's own required test 2) -- distinct from a regression run against migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md's own, real existing corpus -- the tree that exists when CP6 runs, corrected from the built distribution/workflow/2.5.0/ payload at revision 24, finding I2, since CP11 builds that tree only after CP6; this single run is the whole assertion for the classification partition, run **after** CP6 has made its carve-out-bound markings (post-marking, distinct from guarantee (v)'s own pre-marking read of that same tree -- the two states named explicitly at revision 27, restated here at revision 28, finding I3), transferred to the built distribution/workflow/2.5.0/ payload by build_release.py --check's own byte-identity proof (CP11) rather than asserted there a second time (revision 25, finding I2, resolution 1) -- asserting only the classification partition -- reclassifying none of it HISTORICAL except where CP6 deliberately and visibly marks a pre-existing section, itself bound by the sweep's own flagged output computed at CP6 implementation time against that same overlay-payload tree (revision 22, finding I2; carve-out's bound corrected at revision 23, finding I3; tree named at revision 24, finding I2) -- with no physical move of existing repository content required or forced | CP1, CP6 |
| REQ-10 | A generic, reusable declaration-coverage helper exists in place of the duplicated, hand-authored per-work-item test pattern; the already-canonical census mechanism is documented as the precedent, not re-implemented | CP7 |
| REQ-11 | Every Blocking/Important review finding carries an advisory substantive/apparatus tag (never parser-rejected; an untagged finding counts as substantive) without weakening REVIEW_PROTOCOL.md's existing resolve-or-reject-with-evidence rule; a fixed, advisory, non-phase-gating circuit-breaker signal (bound: 2 consecutive apparatus-only rounds) is available for both the plan-stage and implementation-stage two-stage review protocols, scoped to two consecutive same-stage local-model review rounds; manual-external convergence is explicitly left to operator judgment, with no durable recoverability claim made for it (resolves MANUAL_EXTERNAL_PLAN_REVIEW round 1, finding I3) | CP8 |
| REQ-12 | v2.3.1-001, v2.3.1-003, and v2.4.0-001's implementation-stage classification symmetry are fixed forward-only in the 2.5.0 overlay, with no existing work item's own already-generated declarations file or already-committed history edited | CP9 |
| REQ-13 | v2.4.0-002 is explicitly reconsidered with reasoning tied to this milestone's own scope; both full structural fixes and the cheap IMPL10-O1 partial mitigation are all resolved deferred (resolved MANUAL_EXTERNAL_PLAN_REVIEW round 1, required acceptance criterion 4) | CP10 |
| REQ-14 | A "2.2" item's generation-record commits, in both the ordinary and recovered roles, are legally produced and legally validated at every round, including after an uncommitted implementation_review_stages ledger write and from every legal recovery source phase | CP3, CP12 |
| REQ-15 | A "2.2" item inherits every "2.1"-gated behavior unchanged except the implementation-review stages this milestone adds -- across every code gate, command-contract document, and workflow document that behavior reaches; CP6's governing-version enumeration sweep is this requirement's own acceptance evidence, since a hand-enumerated surface list is exactly the pattern this requirement states generally instead of repeating; "1"/"2.1" review/lifecycle and version-gated behavior is byte-identical everywhere this milestone's own inheritance/enumeration surface reaches, CP9's own enumerated forward-only fixes at REQ-12 excepted (narrowed at revision 32, `MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I1) | CP1, CP2, CP4, CP6, CP12 |
| REQ-16 | A repository other than this one has a documented, operator-followable procedure to activate governing_workflow_version "2.2" as its own default -- the WORKFLOW_CONFIG.json two-field edit (default_workflow_version and supported_versions together) and the Workflow-Activation/Workflow-Rollback trailer discipline; a fresh 2.5.0 install is not "2.2"-enabled without that explicit act; the same procedure states explicitly that "2.2" is available only to a work item created after activation, never a promotion for an already-existing "1"/"2.1" work item (resolves MANUAL_EXTERNAL_PLAN_REVIEW round 1, finding I1) | CP1, CP2, CP12 |

**Why a new requirement rather than stretching REQ-1 (added at revision 6,
`LOCAL_MODEL_PLAN_REVIEW` round 5, required acceptance criterion 3).**
REQ-1's own current wording — "a two-stage local-then-manual-external
*implementation*-review protocol exists … with zero change to `"1"`/`"2.1"`
review/lifecycle behavior in the protocol and version-gated inheritance
surface this milestone adds" (quoted at revision 6 in its original,
since-narrowed unqualified form — "… with zero change to `"1"`/`"2.1"`
behavior" — updated here at revision 33, `LOCAL_MODEL_PLAN_REVIEW` round
32, optional finding O1, to REQ-1's revision-32-narrowed wording) — names
the implementation-review protocol specifically; it says
nothing about the *plan*-review gates a `"2.2"` item must also pass through
before it can ever reach implementation. B1 (§2.2) is a defect on that
distinct, un-examined surface, not an implementation-review gap, so
stretching REQ-1's wording to cover it would blur two requirements that
`generate_mapping`'s own bidirectional coverage check is designed to keep
separately traceable to their own checkpoints. REQ-15 states it as its own
requirement instead, owned by CP2 (the widening itself), CP4 (the
command-contract updates, including `/milestone-implement.md`'s own step 0
branch set), CP12 (the end-to-end plan-stage traversal), and, widened at
revision 7 (`LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1), CP1
(`MILESTONE_WORKFLOW.md`'s plan-review text) and CP6 (the mechanical
governing-version enumeration sweep). **Corrected at revision 8
(`LOCAL_MODEL_PLAN_REVIEW` round 7, finding I1)** — revision 7's own version
of this paragraph named `/milestone-implement.md`'s step 0 branch set under
CP1 here, while §2.2 and CP4's own registry entry both (correctly) assigned
that same fix to CP4, so three places disagreed about which checkpoint owns
one edit to one file. CP4 is the fix's one owner (§2.2's own overlay/command
scope: CP1 authors design and workflow documents, CP4 edits `.claude/commands/`
payload documents, and `/milestone-implement.md` is a command document); the
sentence above is corrected to name it there and nowhere else. REQ-15's
description is also restated generally at this revision (resolves B1's
required acceptance criterion 6), naming CP6's sweep as its acceptance
evidence rather than enumerating surfaces by name — the same restatement
this section's own §2.2 discussion gives for the reasoning. The general
form of the inheritance rule (§2.2) still fits inside REQ-15's own scope
rather than a sixteenth requirement, since REQ-15's subject — what a
`"2.2"` item inherits from `"2.1"` outside the implementation-review
protocol REQ-1 covers — is exactly what round 6's and round 7's own B1
findings keep finding under-widened; a new requirement would only restate
REQ-15 with a wider checkpoint list, which is what widening REQ-15 itself
already does.

**Why REQ-16, and why it is not REQ-15 either (added at revision 10,
`LOCAL_MODEL_PLAN_REVIEW` round 9, required acceptance criterion 3).**
REQ-15's own subject is what a `"2.2"` item inherits *once it exists* —
every `"2.1"`-gated behavior applying unchanged. REQ-16's subject is a
question no requirement previously named at all: how a `"2.2"` item comes
to exist in a repository other than this one in the first place, since
`route_work_item` and the remediation-child creator never choose a version
themselves (§2.2's "Reachability" paragraph). Folding this into REQ-15
would make REQ-15 responsible for two independent claims — inheritance and
reachability — that `generate_mapping`'s own bidirectional coverage check
is designed to keep separately traceable, exactly the reasoning that
already separates REQ-15 from REQ-1 above; REQ-16 is owned by CP1 (the
`IMPLEMENTATION_REVIEW_WORKFLOW.md` operator guide that states the
procedure) and CP12 (the disposable-repo scenario that already drives the
`"2.2"` activation, now also this requirement's acceptance evidence for the
procedure actually working end to end). **Widened at revision 16
(`LOCAL_MODEL_PLAN_REVIEW` round 15, optional finding O1) to also name CP2**:
revision 15's own addition to REQ-16 — that the documented procedure states
"2.2" is available only to a work item created after activation, never a
promotion for an existing item — is actually proved by CP2's own new
future-work-item-only regression test (§6), not by CP1 or CP12 alone;
REQ-16's `checkpoint_ids` are corrected to include CP2 so that clause is
traceable to the test that discharges it.

## 5. Migration/compatibility considerations

- `distribution/workflow/2.3.1/` and `distribution/workflow/2.4.0/` are
  never edited — `2.5.0` is base `2.4.0` plus this milestone's overlay,
  per `tools/build_release.py`'s existing authored-release mechanics
  (already proven by `2.4.0` itself).
- No existing `"1"`/`"2.1"` work item, in this repository or any other
  `workflow_manager`-managed repository, **ever** changes its `"1"`/`"2.1"`
  review/lifecycle behavior — the two-stage local-then-manual-external
  review protocol and version-gated inheritance this milestone adds — on
  update to `2.5.0` — not on update itself, and not afterward, including
  after that repository's own
  `WORKFLOW_CONFIG.json.default_workflow_version` is separately activated
  to `"2.2"` (CP12 proves this directly). **Narrowed at revision 32**
  (`MANUAL_EXTERNAL_PLAN_REVIEW` round 2, finding I1): revision 31's own
  version of this claim was global and unqualified — "ever changes
  behavior," with no carve-out — which directly contradicted the very next
  two bullets below, both of which are *this same section's own* deliberate
  exceptions: CP9's forward-only fixes (`v2.3.1-003`'s first-ever
  plan-approval fallback, `v2.3.1-001`'s host-history conformance behavior,
  and `v2.4.0-001`'s default classification for a newly-generated
  implementation-stage declarations file) do change behavior for a future
  event under a `"1"`/`"2.1"`-governed repository or work item, and are
  intentionally shipped release-wide rather than gated to `"2.2"`. The
  claim above is therefore scoped to exactly the surface this milestone's
  own two-stage-review/version-gated design adds (REQ-1, REQ-15); it says
  nothing about, and does not contradict, CP9's own forward-only fixes,
  which remain governed entirely by the forward-only/no-history-rewrite
  bullet immediately below and by REQ-12. No already-recorded history, and
  no already-generated declarations file, is retroactively rewritten by
  either surface — that stronger guarantee is unchanged and is restated,
  not weakened, by this narrowing. **Corrected at revision 15**
  (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I1): revision 14's own
  "unless and until… activated" phrasing read as though activation itself
  changes an already-existing item's behavior once it happens, which is
  false. **Further corrected at revision 16 (`LOCAL_MODEL_PLAN_REVIEW`
  round 15, finding I1)**: revision 15's own replacement claim —
  "`governing_workflow_version` is fixed at a work item's creation and
  never changes over its lifetime" — was itself false, since
  `promote_legacy_work_item` mutates an already-existing item's
  `governing_workflow_version` in place on legacy adoption (§2.2's
  "Future-work-item-only" paragraph, corrected the same round). The narrower,
  accurate claim: this milestone adds no promotion path from `"1"`/`"2.1"`
  to `"2.2"` for an already-existing work item, and does not generalize
  `promote_legacy_work_item`'s own `"1"` → `"2.1"` transition to reach it.
  Activation only changes which governing version a *subsequently
  created* work item or remediation child receives; it is never a
  retroactive act on anything that already exists. **The activation
  procedure itself — not only this precondition — is documented** (resolves
  `LOCAL_MODEL_PLAN_REVIEW` round 9, finding I1): §2.2's own "Reachability"
  paragraph states the mechanism, and CP1's new
  `IMPLEMENTATION_REVIEW_WORKFLOW.md` operator guide carries it as the
  document an operator actually consults. `2.5.0`'s own shipped template
  stays at `"2.1"` (§2.2's "Template question"), so a fresh `2.5.0`
  install is not `"2.2"`-enabled either.
- Downgrade posture (CP13): once a repository has activated `"2.2"` and
  committed any work item whose `implementation_review_stages` ledger, or
  whose `phase`, has ever held one of this milestone's new values,
  downgrading to a release whose `workflow_state.py` predates `"2.2"` is
  unsupported, by the same reasoning `2.4.0`'s own downgrade-posture
  paragraph already states for `NEEDS_REVALIDATION`/`SUPERSEDED`.
  **Cross-reference added at revision 13, `LOCAL_MODEL_PLAN_REVIEW` round
  12, optional finding 3**: this bullet's own direction also covers the
  activation-trailer case §2.2's "Rollback-trailer-value miss" paragraph
  reasons about — a `Workflow-Rollback` (or `Workflow-Activation`) trailer
  naming a version a downgraded, older `is_activated` predates (a later
  release's own future version string, e.g. `"2.3"`) is exactly that
  paragraph's miss case, resolved fail-closed as activated with the hard
  stop armed, never a silent fall-through — so this posture and that rule
  agree without restating the mechanism here.
- **`validate_bundle_generation_record_commit`'s `governing_workflow_version`
  read: the missing-key rule, stated explicitly (added at revision 4,
  `LOCAL_MODEL_PLAN_REVIEW` round 3, Migration and data-integrity
  concerns).** B1(a)'s resolver design has this function read
  `governing_workflow_version` from the commit's own committed
  `work_items[work_item_id]` dict. **Tightened at revision 5,
  `LOCAL_MODEL_PLAN_REVIEW` round 4, optional finding 1** (revision 4's
  version of this paragraph cited a second case that cannot arise at this
  read site, which would have made CP3's own test of the rule vacuous if
  built on it): that key can be genuinely absent in exactly one real case
  at this read site — a `"1"`-era entry that never carried the field at
  all (every read site in `workflow_state.py` uses `work_item.get(...)`,
  so absence is tolerated by construction). A second case that might
  appear to apply — `_read_json_at_commit_or_empty` returning `{}` for a
  commit whose side predates `WORKFLOW_STATE.json` — does not arise here:
  this resolver reads the field from the commit's own committed dict
  (`after`, `:11105`), and `validate_bundle_generation_record_commit` has
  already refused, before this read, unless `changed_paths ==
  {"docs/ai-workflow/WORKFLOW_STATE.json"}` (`:11082`), so the file
  necessarily exists on the commit's own side and `{}` is unreachable at
  this read site — that case belongs to a parent-side `WORKFLOW_STATE.json`
  read elsewhere, not to this one. **The rule is: absent means the
  `"1"`/`"2.1"` literal** —
  `bundle_generation_target_phase`'s and
  `bundle_generation_recovered_role_legal_committed_phases`'s own
  `"1"`/`"2.1"` branch, unconditionally, never a raise and never a `"2.2"`
  interpretation. Without stating this, every already-committed
  generation-record commit in this or any other repository's own history —
  none of which carries `governing_workflow_version` inside the commit's
  own tree, since the field does not exist before this milestone — becomes
  unvalidatable the moment `2.5.0`'s resolver-based check replaces today's
  single literal. CP3 states and tests this rule (a commit predating the
  field validates identically to a `"1"`/`"2.1"` commit that carries it).
  This is independent of, and does not narrow, `CP13`'s downgrade-posture
  paragraph immediately above, which is about the reverse direction
  (reading `2.2`-era vocabulary under an older release), not this one.
- **Review-scalability branches (CP6-CP8, added revision 3) change no
  runtime state-machine behavior for any existing work item.** CP6's
  documentation convention and lint, CP7's generic test helper, and CP8's
  `[substantive]`/`[apparatus]` finding tag plus advisory circuit-breaker
  signal are all either process/documentation or reviewer-report-facing —
  none writes a new `WORKFLOW_STATE.json` field, none gates a phase
  transition, and none requires a `governing_workflow_version` beyond
  `"2.2"` (already required for §2.1-§2.3). A `"1"`/`"2.1"` work item is
  unaffected by all three.
- **Post-v2.3.1 backlog fixes (CP9, added revision 3) are forward-only and
  release-wide operator guidance, not a retroactive repair.** `v2.3.1-003`'s
  and `v2.3.1-001`'s fixes change behavior only for events that have not
  yet happened (a future first-ever plan approval; a future conformance run
  against a target repository) — no already-recorded history is
  reinterpreted, and (**corrected at revision 4, finding I4**)
  `migration/portability_exceptions.json`'s own `2.3.1`/`2.4.0` `by_version`
  entries are untouched by this change; only a new, required, empty
  `by_version["2.5.0"]` entry is added. `v2.4.0-001`'s implementation-stage
  symmetry widening
  changes `generate_artifacts_declarations`' own defaults for a work item
  whose declarations file does not yet exist; exactly as the defect
  record's own plan-stage precedent already establishes, no existing work
  item's already-generated `<work_item_id>-artifacts.json` is edited by
  this change. **Discharges round 2's optional finding 2**: CP11's
  release-authoring migration notes and CP9's own registry entry state this
  widening as guidance for *any* repository updating to `2.5.0` — a
  repository with a live `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION`
  work item whose declarations file predates the fix remains exposed to
  `v2.4.0-001` exactly as documented (its own two mitigations apply)
  until that item's own next plan revision regenerates its declarations
  under the `2.5.0` generator — this is named explicitly as release-wide
  guidance now, not left implicit in this repository's own self-hosting
  note the way revision 2 left it.
- **`v2.4.0-002` (CP10) is unaffected either way.** §9's decision 3 is now
  resolved to decline `IMPL10-O1` (revision 15,
  `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, required acceptance criterion 4);
  no existing work item's behavior changes regardless, since the
  mitigation, had it been adopted, would only have narrowed an
  already-existing race window within one already-documented,
  already-scoped-to-one-worktree-root guarantee — it would not have widened
  or newly promised anything.

## 6. Tests

- Unit tests for every new pure function (CP2/CP3), mirroring the
  existing `plan_review_stages` test suite's coverage shape one-for-one.
- **A parametrized `"2.2"`-plan-inheritance test (CP2, added at revision 6,
  `LOCAL_MODEL_PLAN_REVIEW` round 5, finding B1)**: for each of
  `publish_plan_revision`, `plan_approval_gate_reachable`,
  `_require_v2_1_plan_review` and `_validate_plan_review_stages`, asserts
  that a `"2.2"`-governed work item gets the *same* answer a `"2.1"` one
  does — `publish_plan_revision` routes to `AWAITING_LOCAL_PLAN_REVIEW`
  (not a raise); `plan_approval_gate_reachable` returns `False` with no
  ledger and `True` only with both stages `APPROVE` against the current
  `review_content_id`; `validate_local_plan_review_preconditions` passes;
  `_validate_plan_review_stages` accepts a well-formed ledger — plus, in
  the same test, that a `"1"` item's answer at all four sites is
  byte-unchanged. Parametrized over `("1", "2.1", "2.2")` so a future
  `"2.6.0"` widening this milestone did not anticipate is pinned by the
  same test rather than needing a new one.
- **An activation/rollback event-model unit test (CP2, added at revision
  11, `LOCAL_MODEL_PLAN_REVIEW` round 10, finding I1's required test;
  extended at revision 12, round 11, finding I1's required test)**: proves
  `is_activated` is `True` after a `Workflow-Activation: 2.2` commit; that
  `load_config` raises `ConfigMissingAfterActivationError` — never returns
  `default_config()` — when the config is missing or corrupt at that point;
  that after a subsequent `Workflow-Rollback: 2.2` commit (config now
  `"2.1"`) `is_activated` is still `True` and `load_config`'s missing-config
  behavior is unchanged; and, for the mapping-miss case (revision 12), that
  after a `Workflow-Rollback` trailer whose value the predecessor mapping
  does not contain — a bare/empty value and an unknown version such as
  `"2.9"` are the two cheap inputs — `is_activated` still reports `True`
  (fail-closed) and `load_config` with a missing config at that point still
  raises `ConfigMissingAfterActivationError` rather than returning
  `default_config()` or propagating a `KeyError`, pinning the version-aware
  event model decided at §2.2 rather than the binary one, and its
  rollback-trailer-value miss rule in particular.
  **Extended again at revision 13, `LOCAL_MODEL_PLAN_REVIEW` round 12,
  finding I1's required test ("Missing tests")**: the same test additionally
  pins the *declared-entry* side of the table alongside the miss side above,
  so the two are provably not conflated — after a `Workflow-Activation: 2.1`
  commit followed by a `Workflow-Rollback: 2.1` commit, `is_activated` is
  `False` and `load_config` with a missing config returns `default_config()`
  (not `ConfigMissingAfterActivationError`), the same assertion
  `scripts/workflow_state_test.py:129-134` already makes today, stated here
  as a regression pin so a wrong domain resolution is caught by this test
  rather than only by that older one breaking. The test states explicitly
  that `"2.1"` is a declared predecessor-mapping entry (destination `"1"`),
  not a miss input, so this half and the bare/empty/`"2.9"` miss half above
  cannot silently drift back together.
  **Citation corrected as `LOCAL_MODEL_PLAN_REVIEW` round 11's optional
  finding 2**: `scripts/workflow_state_test.py:191-216` (this plan's own
  round-10 citation) is `TestActivationRollbackTransforms` — five pure-dict
  assertions over `build_activated_config`/`build_rolled_back_config` with
  no repository, no commits and no trailers, not the shape this test needs.
  The existing shape this extends is `:129-141`
  (`test_rollback_after_activation_restores_pre_activation_behavior`,
  `test_latest_event_wins_not_first`) and `TestWFActivateFourCombinations`
  (`:155-187`), which already owns "all four combinations of (config
  present/absent) x (activation trailer present/absent)" and is the natural
  home for a fifth trailer-value axis.
- **A future-work-item-only regression test (CP2, added at revision 15,
  `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I1's required test)**:
  proves that activating `"2.2"` (via the generalized helper, or the
  supported hand edit to `WORKFLOW_CONFIG.json.default_workflow_version`)
  changes only `default_work_item`'s own output for a *subsequently*
  created work item or remediation child, and mutates no already-existing
  `work_items[...]` entry's `governing_workflow_version` in
  `WORKFLOW_STATE.json` — a fixture with an existing `"2.1"` work item
  present before the activation commit, asserting that entry's
  `governing_workflow_version` is byte-unchanged after it.
- **A declaration-coverage unit test (CP2, added at revision 2, finding B1
  and its own "Missing tests" item)**: asserts every checkpoint-declared
  implementation-stage deliverable path this item's own
  `implementation-review-two-stage-artifacts.json` names classifies
  `protected` — never `UnclassifiedPathError`, never `excluded` — and that
  `compute_review_content_id_implementation_stage` no longer raises. Added
  under CP2 so it runs before CP11 needs a working implementation-stage
  classification to generate the release.
- **A provenance-interval unit test (CP3, added at revision 2, finding B3
  and its own "Missing tests" item; extended at revision 3, finding B1)**:
  proves `implementation_provenance_interval_reachable`/
  `verify_implementation_provenance_interval`'s `HEAD == T` requirement is
  unaffected by a local-`APPROVE` + manual-`APPROVE`
  `implementation_review_stages` ledger-write sequence for a `"2.2"` item
  (§2.1's provenance-interval resolution); **now additionally asserts**
  (i) `T`'s own committed `phase` for a `"2.2"` item and that
  `validate_bundle_generation_record_commit` accepts it, resolving to the
  version-dependent target phase per B1(a), and (ii) the REVISE-loop round
  specifically, where `T` is created *after* an uncommitted
  `implementation_review_stages` ledger write. CP12's end-to-end scenario
  covers the same property functionally; this is the unit-level pin, since
  it is the invariant most likely to be silently broken by a future edit.
- **A recovered-role generation-record-commit field-diff test (CP3, added
  at revision 3 as finding B1(b)'s own "Missing tests" item; corrected at
  revision 4, finding B1, to test the actually-affected role)**: builds a
  `"2.2"` item's round-2 generation-record commit — the
  `record_bundle_generation(outcome="same_content")` shape, which §2.1's
  B1 correction establishes is the **recovered** role (`Workflow-Supersedes`
  trailer), not the ordinary role — with a stale `implementation_review_stages`
  ledger residue present in the working-tree state at commit time, and
  asserts `validate_bundle_generation_record_commit` accepts it against the
  widened `RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS`. Under the plan as it
  stood before this correction (which widened only the ordinary
  constant), this exact test still fails — which is the point of adding it
  before CP11.
- **A symmetric recovered-role field-diff test for
  `/recover-implementation-provenance`'s own dedicated commit (CP3, added
  at revision 4, finding B1)**: the identical construction, built via the
  recovery command's own commit path rather than
  `record_bundle_generation`, proving both of B1's two paths into the
  recovered role are covered, not only the ordinary-REVISE-loop one.
- **A recovered-role committed-phase test (CP3, added at revision 4,
  finding B2; widened at revision 5, `LOCAL_MODEL_PLAN_REVIEW` round 4,
  finding B1)**: builds a recovery commit from **each** of the **three**
  phases a `"2.2"` item can occupy between `T` and approval
  (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
  `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, and
  `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`, the terminal phase) and
  asserts `validate_bundle_generation_record_commit` accepts all three
  against the membership test replacing the recovered role's prior
  single-valued equality, and that `verify_implementation_provenance_interval`
  then still resolves. Under the plan as it stood before this widening
  (which stopped at the first two phases), the terminal-phase case of this
  exact test fails — which is the point of adding it before CP11. CP12's
  "from each of the three phases" functional scenario (below) is the
  end-to-end counterpart; this is the unit-level pin.
- **A negative recovery-refusal test (CP3, added at revision 5,
  `LOCAL_MODEL_PLAN_REVIEW` round 4, finding B1's own "Missing tests"
  item)**: proves that widening `"2.2"`'s three sets changes no `"1"`/`"2.1"`
  refusal — `/recover-implementation-provenance` invoked from a phase
  outside `bundle_generation_target_phase("post-fix", governing_workflow_version)`
  still refuses for a `"1"`/`"2.1"` item exactly where it refuses today, and
  `validate_bundle_generation_record_commit` still rejects a `"1"`/`"2.1"`
  recovered-role commit whose committed phase is anything other than that
  single resolved value. Cheap, and it pins the "inert for existing items"
  claim restated above for a third set.
- `workflow_integration_test.py`/`workflow_state_completion_obligations_test.py`
  census updates for the two new phases and their writers (CP2–CP4).
- **CP12's negative-path list additionally exercises
  `/recover-implementation-provenance` from each of the three phases a
  `"2.2"` item can occupy between `T` and approval** (round 2's "Missing
  tests" item 3, resolves B1(a)'s recovery-path clause and, per B2's and
  revision 5's finding-B1 fix, actually passes for all three, including
  the terminal phase) — the recovery command's own widened phase guard and
  committed-phase membership test (§2.1) are otherwise untested at the
  functional layer.
- **A `"post-fix"`-from-`AWAITING_FUNCTIONAL_REVIEW` unit test for a
  `"2.2"` item (CP3, added at revision 4, finding I2)**: pins
  `bundle_generation_target_phase`'s resolution for that source phase to
  `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`, the same value the
  `APPLYING_REVIEW_FEEDBACK` source phase resolves to. **CP12 gains the
  corresponding functional scenario**: a `"2.2"` item's functional-review
  bounded fix (`technical_approval.status == "STALE"`) re-entering the
  local-then-manual-external implementation-review sequence before
  `/approve-review implementation` is reachable again — today's CP12 list
  covers implementation-review `REVISE` loops only, not this entry point.
- **CP6's mechanical lint — explicit lifecycle classification, replacing
  the heading/prose-inference design of revisions 15-20 (revision 21, user-
  directed architectural correction applying together with
  `LOCAL_MODEL_PLAN_REVIEW` round 20's own convergence recommendation; full
  history of revisions 15-20's heading/prose-inference approach retained at
  §7's revision-21 disposition entry).** The lint's classification predicate
  (the first three bullets below) runs over every document
  `D-Review-Material-Lifecycle` names, **in full** — this milestone's own
  overlay-authored `IMPLEMENTATION_REVIEW_WORKFLOW.md` and
  `WORKFLOW_V2_PLAN.md`, pre-existing sections included, per §2.4 point 3's
  own subject/mechanism/timing table (**scope corrected at revision 27**,
  `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I1: revision 23's own
  cross-reference scoped "every document `D-Review-Material-Lifecycle`
  names" here to this milestone's authored/marked material only — correct
  for the narrative-content bullet below, which restates that narrower
  scope explicitly where it applies, but wrong as a blanket framing for
  every bullet that follows, since the fail-closed-default bullet then
  read as scoped away from exactly the pre-existing corpus guarantee (v)
  says it covers). The narrower "this milestone's authored/marked material,
  never `WORKFLOW_V2_PLAN.md`'s pre-existing unmarked sections wholesale"
  scope named below belongs only to the narrative-content assertion; the
  lint asserts:
  - **classification, where present, is always by explicit marker, never by
    inference (narrowed from "every unit... carries an explicit
    classification" at revision 26**, `LOCAL_MODEL_PLAN_REVIEW` round 25,
    finding I2: the wider "every unit the convention applies to carries an
    explicit classification" is an authorship-scoped, unevaluable subject —
    the same shape round 24's own finding I1 removed from guarantee (vi)'s
    scope statement — and it stood beside guarantee (vii) below asserting a
    narrower, evaluable marker-presence obligation over a different subject,
    leaving an implementer two inconsistent readings of what the lint
    requires; guarantee (vii) below is now the lint's sole statement of
    *which* units are obliged to carry a marker, and this bullet states only
    the *manner* of classification): a unit's classification, wherever
    stated, never depends on
    a heading's wording, level, or position — only on an explicit marker;
  - a unit with no explicit marker, or an unparseable/ambiguous one, is
    classified `CURRENT` (fail-closed default) — the lint must never let
    ambiguous material read as `HISTORICAL`;
  - only an explicit, intentional marker edit moves *material* `CURRENT` ->
    `HISTORICAL`; no other edit shape (heading rewording, restructuring, or
    redrawing which unit material belongs to) changes that material's
    classification (**restated over material rather than units at revision
    22, `LOCAL_MODEL_PLAN_REVIEW` round 21, finding I3**: stating it over
    units left open the merge direction — folding a `CURRENT` region into
    an adjacent `HISTORICAL`-marked unit by deleting or demoting the
    heading between them, with no marker edit anywhere in the diff);
  - within the subject scope §2.4 point 3 states — **a unit is within this
    scope exactly when it carries an explicit `CURRENT` marker; a unit
    `CURRENT` only by the fail-closed default (no marker at all) is outside
    it (mechanical basis stated first at revision 29, optional finding O2,
    `LOCAL_MODEL_PLAN_REVIEW` round 28: restated ahead of the
    authorship-shaped framing that follows, mirroring §2.4 point 3's own
    revision-29 repoint of its analogous appeal, finding I2, so both
    documents state one consistent, marker-based basis for the same scope
    before naming the authorship-shaped framing it happens to coincide
    with)** — this milestone's own authored/marked material, never
    `WORKFLOW_V2_PLAN.md`'s pre-existing unmarked sections wholesale
    (**scope stated explicitly at revision 23**, finding I1), a unit
    classified `CURRENT` never carries the inline "revision N corrected
    finding X"-shaped provenance narrative point 1 of §2.4 point 3 forbids;
    an occurrence of that narrative inside `CURRENT` material fails the
    lint, with no corresponding requirement on `HISTORICAL` material
    (**added at revision 22, round 21, finding I1**: without this
    assertion, the lint could not fail on the one thing points 1-2 actually
    require, and §2.1's carry sentence's appeal to "CP6's lint" had nothing
    behind it) (mechanical basis originally stated at revision 24,
    `LOCAL_MODEL_PLAN_REVIEW` round 23, finding I1, mirroring §2.4 point 3's
    own statement);
  - **guarantee (vii), a new, separate obligation (added at revision 25**,
    `LOCAL_MODEL_PLAN_REVIEW` round 24, finding I1, mirroring §2.4 point 3's
    own statement) **— the lint's sole statement of which units must carry a
    marker at all (narrowed from the first bullet above at revision 26,
    finding I2), and, since revision 28, a pure presence obligation that
    never derives a marker's *value* (user-directed architectural
    correction, applying together with `LOCAL_MODEL_PLAN_REVIEW` round 27's
    finding B1)**: every unit within the marker-presence scope — the whole
    of `IMPLEMENTATION_REVIEW_WORKFLOW.md`; every top-level design section
    any checkpoint's own registry entry adds to `WORKFLOW_V2_PLAN.md` —
    today `D-Implementation-Review-Stages` and
    `D-Implementation-Review-Version-Activation` (CP1) and
    `D-Review-Material-Lifecycle` itself (CP6) (**widened from "CP1's own
    registry entry" to "any checkpoint's own registry entry" at revision
    28**, finding I2: the prior wording put CP6's own defining section
    outside the obligation it defines) — each in full, **with a nested unit
    such as CP1's carried `2.5.0`-scoped disposition-record subsection (§2.1)
    reached once, through its container's "in full" reach, never as a
    separately enumerated peer (corrected at revision 28, finding I1: the
    prior three-item enumeration named that subsection as a third, nested
    member of a scope whose other two members already contained it)** —
    carries an explicit marker of **either value**; a unit within that scope
    carrying none is a lint failure, reported independently of the
    fail-closed classification default above, which still classifies that
    same unit `CURRENT` unaffected. This obligation asserts presence alone:
    it never requires, implies, or derives which value a unit's marker must
    hold — that is guarantee (iii)'s classification default and the unit
    author's own explicit choice, never a function of who authored the
    unit, whether it is new, or which named section it sits under;
  - **CP6 writes the markers guarantee (vii) requires that are still
    missing, as part of this checkpoint's own deliverable (added at
    revision 27**, `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I2; **scoped
    to units not already carrying an explicit marker, and stripped of its
    novelty-derived value rule, at revision 28**, user-directed
    architectural correction applying together with round 27's finding B1:
    CP1 authors `IMPLEMENTATION_REVIEW_WORKFLOW.md` in full and the two
    named `WORKFLOW_V2_PLAN.md` `D-*` sections, and no checkpoint before
    this one was ever assigned to write the markers the lint then requires
    on them, so a freshly-built lint failed closed on its own author's own
    material with nothing in the plan producing the state it checks for —
    but CP1's own carried disposition-record subsection already carries an
    explicit `HISTORICAL` marker by CP1's own deliverable (§2.1), and
    revision 27's blanket "every unit ... `CURRENT`" instruction collided
    with it directly): using the representation CP1 has already fixed
    (**reassigned at revision 29**, `LOCAL_MODEL_PLAN_REVIEW` round 28,
    finding B1, resolution 1: CP6 no longer chooses the representation —
    §2.4 point 3's separability bullet — since CP1's own marker must exist
    in it before CP6 runs at all), CP6
    marks `CURRENT` every unit, within the scope stated above, that does
    not already carry an explicit marker of its own; CP6 never overwrites or
    reclassifies a unit that already carries an explicit marker, whatever
    that marker's value — CP1's disposition-record subsection's own
    `HISTORICAL` marker discharges guarantee (vii) for that unit and is left
    untouched, exactly as any other already-marked unit would be. This
    marking pass is distinct from — and never bounded by — the
    sweep-flagged carve-out below, and it never reasons about which units
    are "new material CP1 authored" versus pre-existing: it reasons only
    about which in-scope units already carry an explicit marker;
  - the classification is machine-checkable independently of the normative
    prose it classifies (§2.4 point 3's "classification authority is
    separable from the prose" guarantee).
  - The marker's concrete representation — its exact syntax and delimiters —
    is fixed by CP1, as part of CP1's own deliverable, no later than CP1
    time (**reassigned at revision 29**, finding B1, resolution 1); the
    lint built against the parser, and the concrete textual shape treated as
    forbidden narrative above, remain CP6 implementation's own decisions,
    not specified here (§2.4 point 3) — the parser itself is CP1's own
    `parse_marker`, imported by CP6 rather than re-derived (narrowed at
    revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2, from "the
    parser that reads it, the lint grammar built against it, and the
    concrete textual shape treated as forbidden narrative above remain CP6
    implementation's own decisions").
  **CP6 must prove the mechanism with fixtures, not merely assert it**: at
  minimum, one positive fixture (explicit `CURRENT` material stays
  review-visible), one negative fixture (explicit `HISTORICAL` material is
  excluded from review-visible surface), one ambiguous fixture (unmarked or
  malformed-marker material fails closed to `CURRENT`), one two-version
  transition fixture (**added at revision 23**, finding I4, restating round
  21's own outstanding missing test 1: a non-marker edit — heading reword,
  prose restructure — leaves every unit's reported classification unchanged
  across the two versions; a marker-only edit alone performs the `CURRENT`
  -> `HISTORICAL` transition), one
  boundary-redrawing fixture (**added at revision 22, finding I3**: merging
  a `CURRENT` region into an adjacent `HISTORICAL`-marked unit by deleting
  or demoting the heading between them, with no marker edit, must not
  report that material `HISTORICAL`), one narrative-location fixture
  (**added at revision 22, finding I1**: the forbidden narrative inside
  `CURRENT` material fails the lint because that material carries an
  explicit `CURRENT` marker; the identical narrative inside
  `HISTORICAL` material passes), one scope fixture (**added at revision
  23, discriminator restated at revision 24**, finding I1: a corpus-shaped
  fixture whose unmarked pre-existing
  section carries the forbidden narrative must pass the lint, since that
  section is `CURRENT` only by the fail-closed default — carrying no
  explicit marker — and is therefore outside guarantee (vi)'s reach), one
  carve-out-bound fixture (**added at revision 23**, finding
  I3, restating round 21's own outstanding missing test 4: a pre-existing
  disposition-titled section containing only occurrences the
  governing-version sweep below does not flag must not be marked
  `HISTORICAL` by CP6's own deliverable, and the corpus regression below
  must fail if it is), one
  marker-presence fixture (**added at revision 25, restated as
  one-corpus-shaped at revision 26**, `LOCAL_MODEL_PLAN_REVIEW` round 25,
  finding I3: an in-scope unit carrying no marker must fail
  guarantee (vii), unaffected by and never disturbing the ambiguous
  fixture's own `CURRENT` classification verdict for the same unmarked
  input; one-corpus-shaped for `WORKFLOW_V2_PLAN.md` — a fixture unit inside
  one of the in-scope sections, unmarked, must fail; a fixture unit
  elsewhere in the same fixture document, unmarked, must pass — per §2.4
  point 3's own statement of the same fixture, **restated for the widened
  scope at revision 28**, finding I2); an already-marked-nested-unit
  fixture (**added at revision 28**, round 27's finding B1, required test
  1: an in-scope unit already carrying an explicit `HISTORICAL` marker,
  nested inside another in-scope unit, must survive CP6's own marking pass
  unchanged — not overwritten, reported satisfied for guarantee (vii) by
  presence alone, and not failing guarantee (vi) — per §2.4 point 3's own
  statement of the same fixture); a representation-conformance fixture
  (**added at revision 29**, round 28's finding B1, required test 1: CP1's
  own disposition-record subsection, in the fixture, carries its
  `HISTORICAL` marker written in exactly the representation CP1 fixes
  (§2.4 point 3's separability bullet), and CP6's own parser, built against
  that same fixed representation, recognizes it as an explicit marker
  rather than defaulting it to `CURRENT`; **widened at revision 31**, round
  30's finding I1, resolution 1: the same fixture additionally asserts the
  exclusivity direction — a mutated copy of the fixture's marker, written in
  a form outside CP1's fixed representation, must not be recognized as an
  explicit marker and must instead fall to the `CURRENT` fail-closed default
  — per §2.4 point 3's own statement of the same fixture; **widened again at
  revision 33**, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding I1 (revision 32
  itself applied this widening only at §2.4 point 3's separability bullet
  and CP6's registry entry, not here — §7's own revision-32 entry is
  corrected below to say so): the fixture is widened to exercise the
  canonical `render_marker`/`parse_marker` pair directly rather than only
  CP1's one written instance — `parse_marker` accepts
  `render_marker("HISTORICAL")`'s own output as `HISTORICAL`, accepts
  `render_marker("CURRENT")`'s own output as an explicit `CURRENT` marker
  distinct from the fail-closed default a missing marker also classifies
  `CURRENT`, and rejects representative malformed/out-of-contract forms — a
  mutated delimiter, a third state value, truncated or duplicated marker
  text — back to the `CURRENT` fail-closed default; CP1's own written
  instance and every marker CP6's marking pass writes are additionally
  required to equal `render_marker`'s own output bytes for their respective
  state, a mechanical equality check rather than a second grammar
  comparison; and (`LOCAL_MODEL_PLAN_REVIEW` round 32, finding B2's own
  missing-test note) the fixture additionally asserts that CP6's own lint
  reaches its `CURRENT`/`HISTORICAL`/malformed classification verdicts by
  calling this same `parse_marker`, so a lint whose own grammar tolerates a
  form outside the canonical pair cannot pass with the fixture green); a
  pre-marking-partition fixture (**added at
  revision 30**, `LOCAL_MODEL_PLAN_REVIEW` round 29, finding B1, resolution
  2, missing test 1: a corpus-shaped fixture document containing one unit
  already carrying an explicit `HISTORICAL` marker — mirroring CP1's own
  disposition-record subsection — alongside units carrying no marker at
  all; the check run against it must classify the marked unit `HISTORICAL`
  and every unmarked unit `CURRENT`, and a mutated copy asserting every
  unit classifies `CURRENT`, the marked one included, must fail; being a
  fixture rather than a one-shot real-corpus read, it survives CP6's own
  marking pass and remains available to catch a future edit that
  re-widens guarantee (v), which the real-corpus read below cannot, since
  that read's own pre-marking moment stops existing in the worktree once
  CP6 completes — per §2.4 point 3's own statement of the same fixture); a
  real-corpus run of the
  finished marker-presence check over every one of guarantee (vii)'s actual
  subjects (**added at revision 27**, `LOCAL_MODEL_PLAN_REVIEW` round 26,
  finding I2's own required test: guarantee (vii) was proved by fixtures
  alone, and the one real-corpus run this checkpoint already specified
  asserts guarantee (v)'s classification partition only, never guarantee
  (vii) — this run must be green as part of CP6's own completion, over
  `IMPLEMENTATION_REVIEW_WORKFLOW.md` in full and every top-level
  `WORKFLOW_V2_PLAN.md` section any checkpoint's registry entry adds,
  `D-Review-Material-Lifecycle` itself included (**widened at revision 28**,
  required test 2 of finding I2), once CP6 has written the markers the
  bullet above assigns it); and a regression run of the finished lint
  against `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s
  own, real existing corpus, run **after** CP6 has made its carve-out-bound
  markings (post-marking — distinct from guarantee (v)'s own pre-marking
  read of the same tree above; **the two states named explicitly at
  revision 27**, `LOCAL_MODEL_PLAN_REVIEW` round 26, finding I3: this
  regression must observe CP6's own markings to have anything to check the
  carve-out-bound fixture below against, so it cannot be the same read as
  guarantee (v)'s pre-marking one) (**corpus and timing corrected at revision
  24**, `LOCAL_MODEL_PLAN_REVIEW` round 23, finding I2: revision 23 named
  the built `distribution/workflow/2.5.0/` payload, which does not exist
  until CP11 -- which depends on CP6 -- builds it; CP1 and CP6 both author
  this overlay file directly, so it exists when CP6 runs -- **the second
  run dropped, revision 25**, `LOCAL_MODEL_PLAN_REVIEW` round 24, finding
  I2, resolution 1: CP6's own read of this overlay-payload tree is never
  repeated a second time against the *built* `distribution/workflow/2.5.0/`
  payload — "single run" names that omission, restated at revision 27 to
  mean exactly that, never "one read of this tree in total" (the pre- and
  post-marking reads above are two reads of the same tree, not two runs
  against two trees); `build_release.py --check`'s own byte-identity proof
  (CP11) transfers this same result to the built `distribution/workflow/2.5.0/`
  payload once that tree exists, since `--check` reproduces the overlay's
  full-replacement file verbatim by construction, so nothing asserts this
  corpus a second time and neither CP11 nor CP13 carries an obligation of
  its own toward it)
  proving that introducing the lint reclassifies none of that corpus's
  existing content as `HISTORICAL` except where CP6 has deliberately and
  visibly marked a pre-existing section `HISTORICAL` as part of this
  checkpoint's own deliverable — the governing-version enumeration sweep's
  own pre-existing disposition-section exemptions, below, are the concrete
  case this milestone needs, and this regression asserts that
  classification partition only, never guarantee (vi) (per §2.4 point 3's
  subject-scope statement). **The carve-out's bound, corrected at revision
  23** (finding I3: revision 22 bounded the carve-out by a hand-measured "9
  sections / 24 occurrences" proxy count, of which at least two of the 24
  counted occurrences are not occurrences of either of the sweep's own two
  detection forms): the sections CP6 may mark `HISTORICAL` under this
  carve-out are exactly those the sweep itself flags when CP6 runs it
  against that same overlay-payload tree (**tree named explicitly at
  revision 24**, finding I2) — never a hand-measured proxy list;
  the "9 sections / 24 occurrences" figure is retained only as a
  proxy-measured indication of scale.
  An unmarked pre-existing unit still classifies `CURRENT` under the
  fail-closed default, and any reclassification not traceable to such a
  deliberate marker addition is a fixture failure that blocks CP6's own
  completion. CP6's own `D-Review-Material-Lifecycle` section and CP1's
  carried subsection (§2.1) are each covered by the same positive/negative
  fixture pair as any other unit — no special-cased predicate for the
  document's own required provenance content, since classification (not
  extent-membership) is what the lint reads.
- **CP7's generic declaration-coverage helper** gains its own unit test
  (parametrized over at least two work-item ids, including a synthetic one
  CP12 constructs) proving it reproduces the same pass/fail verdict CP2's
  own bespoke test already gives for this item.
- **CP8's finding-taxonomy tests (corrected at revision 4, findings I5/I6
  — the tag is advisory, never rejected, and the bound is fixed at 2, not
  section-9-resolved)**: a test proving an untagged or ambiguously-tagged
  Blocking/Important finding is accepted (never rejected) and is treated
  as `[substantive]` for circuit-breaker purposes; a test proving
  `REVIEW_PROTOCOL.md`'s resolve-or-reject rule is unchanged regardless of
  tag or its absence; a circuit-breaker-signal test proving the advisory
  message appears only after 2 consecutive apparatus-only `REVISE` rounds
  for the same **local-model** review stage, and never suppresses or
  auto-resolves a `[substantive]` finding (nor is triggered by one
  masquerading as `[apparatus]` via a missing tag). **Added at revision 15**
  (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I3): a test proving the
  signal fires after two consecutive `LOCAL_MODEL_PLAN_REVIEW` (and,
  separately, two consecutive `LOCAL_MODEL_IMPLEMENTATION_REVIEW`)
  apparatus-only rounds; and a test proving `REVIEW_PROTOCOL.md`'s own
  added text states no corresponding recoverability claim for two
  consecutive manual-external rounds (i.e. asserting the text does not
  contain an unscoped or manual-external circuit-breaker claim), so the
  scoping correction is pinned as prose evidence rather than left
  unverified.
- **CP9's four backlog-fix regression tests**: `pin_plan_approval_state_blob`
  defaulting to mode `100644` when no HEAD blob exists;
  `test_the_historical_status_note_carries_a_dated_correction` skipping
  cleanly (not raising `StopIteration`) against a repository with no host
  status note, and failing exactly as before against one that has a
  malformed note; `generate_artifacts_declarations`'s implementation-stage
  default classifying `.workflow-manager/installation.json` `excluded`
  for a freshly-generated declarations file; **added at revision 4, finding
  I4**, a `tests/` assertion that `expected_portability_exceptions("2.5.0")`
  resolves to an empty list and that `expected_portability_exceptions("2.3.1")`/
  `expected_portability_exceptions("2.4.0")` are byte-unchanged by CP9 — the
  mistake I4 describes (treating `2.5.0`'s entry as optional, or removing
  `2.3.1`'s/`2.4.0`'s) is exactly the kind a green `run_all.py` on this
  repository alone would not catch until the disposable-repo/bootstrap
  matrix ran.
- `python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check`
  (CP11).
- `python3 tools/migrate.py --check --upstream ~/Workspace/repflow-android`
  (CP11/CP13, confirms `2.3.1` untouched).
- Disposable-repository functional flows, positive and negative (CP12) —
  full detail authored as this work item's functional-review checklist at
  `AWAITING_FUNCTIONAL_REVIEW`, following `plan-amendment-mechanism`'s own
  checklist shape in `docs/ACTIVE_MILESTONE.md` as a template.
- **CP12's plan-stage traversal (added at revision 6, `LOCAL_MODEL_PLAN_REVIEW`
  round 5, finding B1's own "Missing tests" item)**: the disposable-repo
  scenario's synthetic `"2.2"` item runs the full two-stage plan-review
  protocol — `AWAITING_LOCAL_PLAN_REVIEW` → `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`
  → `AWAITING_PLAN_APPROVAL` — before any implementation-review stage is
  reached, exercising `/milestone-plan`'s own first planning step for a
  `"2.2"` item, which is otherwise the first place B1's crash would surface.
  This makes CP12 the end-to-end proof of B1's fix at no extra fixture cost.
- **A mechanical governing-version enumeration sweep (CP6, added at
  revision 7, `LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1's own "Missing
  tests" item; predicate, allowlist and fixtures corrected at revision 8,
  round 7, finding B1(a) and its own "Missing tests" item)**: a lint over
  the built release payload's own `.claude/commands/*.md` and
  `docs/ai-workflow/*.md` asserting that no document presents a `"2.1"`
  governing-version reference as exhaustive of the two-stage plan-review
  protocol's own applicability — in either the `{"1", "2.1"}`-exhaustive-
  enumeration form or the bare `"2.1"`-scoped-assertion form (round 7's own
  finding: the dominant, previously-undetected form) — allowing only an
  occurrence inside a section explicitly classified `HISTORICAL` under
  `D-Review-Material-Lifecycle` (**corrected at revision 21**,
  `LOCAL_MODEL_PLAN_REVIEW` round 20's architectural correction: the
  allowlist boundary is the section's explicit classification, never a
  disposition-heading text match) — **including, at revision 22
  (`LOCAL_MODEL_PLAN_REVIEW` round 21, finding I2), any pre-existing
  disposition-titled section of `WORKFLOW_V2_PLAN.md` that the sweep itself
  flags (approximately 9 sections / 24 occurrences by a hand-measured proxy
  against the `2.4.0` payload — **payload named explicitly at revision 24**,
  `LOCAL_MODEL_PLAN_REVIEW` round 23, finding O2: "the real payload" no
  longer names a determinate file once the lifecycle regression's own
  corpus, above, is named separately — **corrected at revision 23**,
  `LOCAL_MODEL_PLAN_REVIEW` round 22, finding I3: the exact set is the
  sweep's own flagged output, computed at CP6 implementation time against
  `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
  (**tree named explicitly at revision 24**, finding I2, since the built
  `distribution/workflow/2.5.0/` tree this sweep otherwise runs against
  does not exist until CP11 builds it), never
  this hand-measured proxy — at least two of the 24 proxy-counted
  occurrences, `:3392` and `:3838`, are not occurrences of either of the
  sweep's own two detection forms at all): CP6 marks each such
  sweep-flagged section
  `HISTORICAL` as a deliberate, diff-visible act of this checkpoint's own
  deliverable, per §2.4 point 3's and §6's own regression-run carve-out
  above, never a silent or automatic reclassification, never a basis
  the sweep grants by heading text alone, and never a section the sweep's
  own output does not flag (the carve-out-bound fixture above pins this
  direction)** — plus a whole-document
  exemption for the three named
  genuinely-closed history documents (§2.2 states which; **narrowed at
  revision 15, `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I2, from four
  to three: `WORKFLOW_V2_PLAN.md` is dropped from the whole-document
  allowlist, since it is the active design-of-record and stays exempt only
  occurrence-by-occurrence, like every other non-exempt document**). The documentation-
  layer counterpart of the parametrized `("1", "2.1", "2.2")` code test
  above, so a future document making either kind of exhaustive-`"2.1"`
  claim fails the suite instead of waiting for the next review round to
  notice by hand. **Per-form fixtures, added at revision 8**: at least two
  negative fixtures (one document presenting `{"1", "2.1"}` as exhaustive,
  one presenting a bare `"2.1"`-only scoping assertion with no `"1"`
  anywhere) and one positive fixture per allowlist category (a closed
  historical plan document; a section explicitly classified `HISTORICAL`),
  so the lint's
  own test suite cannot pass by only ever exercising the enumeration form —
  exactly the way round 7's own finding recurred inside a lint that had
  only ever been specified against that one form. **One further positive
  fixture, added at revision 9 (`LOCAL_MODEL_PLAN_REVIEW` round 8, finding
  I1)**: a document whose only occurrence is a negated / version-
  independence assertion (mirroring `MILESTONE_WORKFLOW.md:424`'s own
  phrasing) must pass the lint without an allowlist entry, pinning the
  predicate-scope narrowing above as a property of the two detection forms
  themselves. **One further negative fixture, moved here from §6's
  lifecycle-lint bullet above at revision 17 (`LOCAL_MODEL_PLAN_REVIEW`
  round 16, finding I3)**: a `WORKFLOW_V2_PLAN.md`-shaped document with a
  stale `"2.1"`-only claim in a *new* current design section not classified
  `HISTORICAL` (must fail, even though the file's own historical sections
  stay exempt) — this sweep's own executable check on §2.2's three-document
  whole-document allowlist (stated at revision 16, `LOCAL_MODEL_PLAN_REVIEW`
  round 15, missing test 1): it fails specifically because
  `WORKFLOW_V2_PLAN.md` is no longer whole-document-exempt, so a future
  revision cannot silently re-widen the allowlist to include it again
  without this fixture turning green in error. This fixture was
  misattributed to the lifecycle lint through revision 16, which cannot
  fail it — a stale governing-version claim is not a revision/finding-
  disposition marker, and this document's own markers stay inside sections
  explicitly classified `HISTORICAL`, so both of that lint's rules pass it
  either way (**terminology corrected at revision 21** to explicit
  classification per the architectural correction above; the sweep's own
  predicate and allowlist are unchanged in substance).
  **Runs against the built
  release, not this repository's own working tree, added at revision 8**:
  CP11 builds `distribution/workflow/2.5.0/`; the assertion that matters to
  a *target* repository is over the payload it installs, so this lint runs
  against that built payload as part of `tests/run_all.py`'s per-release
  suite (`tests/support.py`'s `CI_SUITES` entry CP11 adds for `2.5.0`), not
  only against `migration/overlays/2.5.0/payload/` in isolation. **CP6's own
  use of the sweep runs against the overlay tree, not the built release
  (clarified at revision 24, `LOCAL_MODEL_PLAN_REVIEW` round 23, finding I2;
  framing simplified at revision 25, `LOCAL_MODEL_PLAN_REVIEW` round 24,
  finding I2, resolution 1):** computing the flagged set that bounds CP6's
  own lifecycle carve-out, above, runs against
  `migration/overlays/2.5.0/payload/` alone -- the tree that exists while
  CP6 runs. The paragraph above's own CI-gating run of this same sweep
  against the fully built `distribution/workflow/2.5.0/` release is the
  separate, already-established obligation CP11's `CI_SUITES` entry and
  CP13's `tests/run_all.py` carry for the sweep itself, per this paragraph's
  own revision-8 statement -- it is not a second run of anything CP6
  asserts, and this paragraph makes no claim about the lifecycle lint's own
  corpus regression, whose timing is resolved instead at §2.4 point 3's and
  §6's lifecycle-lint bullet's own guarantee (v) discussion above (revision
  25, finding I2, resolution 1: dropping the "asserted a second time"
  framing this paragraph previously shared with that discussion).
- **CP12's `/milestone-implement` traversal, named explicitly (added at
  revision 7, `LOCAL_MODEL_PLAN_REVIEW` round 6, finding B1's own second
  "Missing tests" item)**: between CP12's plan-stage traversal above and
  its own two-stage implementation-review flow, the synthetic `"2.2"`
  item's disposable repo actually drives `/milestone-implement`'s
  checkpoint loop from `SELF_REVIEWING_IMPLEMENTATION` through step 2's
  `enter_self_reviewing_implementation` write to its own
  `record_bundle_generation(stage="implementation")` call, asserting the
  committed phase at `T` is `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`. Without
  this step named and asserted, `IllegalBundleGenerationSourcePhaseError`
  could first be discovered as a live wedge at CP12 itself rather than
  being pinned as a passing scenario.
- `python3 tests/run_all.py` (fast and full) green at CP13, with `2.3.1`'s
  and `2.4.0`'s own `migration/portability_exceptions.json` `by_version`
  entries byte-unchanged (**corrected at revision 4, finding I4** — revision
  3 called this a "shrink" of the exception set; it is not, since neither
  existing entry is removed) and a new, required `by_version["2.5.0"]`
  entry (empty `exceptions` list) added for the newly authored release —
  the one membership change this revision makes on purpose: `v2.3.1-001`'s
  fix means `2.5.0` never needs an exception for this test, but `2.3.1`'s
  and `2.4.0`'s own already-frozen or already-shipped payloads still do,
  and `tests/support.py:134`'s unguarded `by_version[workflow_version]`
  subscript means an absent `2.5.0` key would fail closed as a `KeyError`,
  not a pass.

## 7. Self-review notes (`SELF_REVIEWING_PLAN`)

**Standing note (added at revision 26**, `LOCAL_MODEL_PLAN_REVIEW` round 25,
optional finding O1, closing the series its own required-criterion-5 fix
predicted rather than merely fixing this entry's instance again: revisions
23, 24 and 25 each omitted §4's REQ-9 row from their own "only text that
changes" enumeration below, each caught and corrected one round later by the
next round's O1**): a change to a requirement's mapping description always
implies §4's own row for that requirement, since §4's row is required to
stay byte-identical to the regenerated mapping's description; every revision
entry below that touches a mapping description states so once, in its own
enumeration, without this note needing to be repeated per entry.

- **Artifacts-declaration gap caught and fixed at generation time.
  Corrected at revision 2 (`LOCAL_MODEL_PLAN_REVIEW` round 1, finding
  B2)**: this work item's own
  `docs/ai-workflow/registry/implementation-review-two-stage-artifacts.json`
  was generated by this repository's already-installed (uncommitted)
  `2.4.0` release of `scripts/workflow_state.py` — revision 1 mistakenly
  attributed generation to the still-`2.3.1` `HEAD`. Diffing this item's
  declarations file against a fresh `generate_artifacts_declarations` call
  shows exactly one hand-added key beyond the `2.4.0` generator's own
  defaults: `plan_stage.excluded_prefixes['docs/defects/']`.
  `.workflow-manager/` was **not** hand-added — the `2.4.0` generator
  already supplies `plan_stage_excluded_prefixes['.workflow-manager/']`
  automatically, per its own `v2.4.0-001` fix.
- **Second declaration gap caught the same way**: `docs/defects/` (this
  repository's own defect-record log) does not exist in the inherited
  `workflow-v2-1-core` template at all and was likewise unclassified;
  worse, an unrelated untracked defect record already sits in the working
  tree
  (`docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`,
  prior work this milestone must not touch per this repository's own
  `CLAUDE.md`), which made this item's own plan-stage `review_content_id`
  unclassifiable at generation time until `docs/defects/` was excluded by
  hand.
- **Third gap, at the implementation stage, caught only at revision 2
  (`LOCAL_MODEL_PLAN_REVIEW` round 1, finding B1)**: unlike the plan-stage
  fixes above (made before revision 1's own bundle), this item's
  `implementation_stage` classification was left at the bare generated
  template (`protected_prefixes` only `.claude/commands/`/`scripts/`,
  `protected_paths` only the declarations file itself) — the exact defect
  `plan-amendment-mechanism-artifacts.json` already diagnosed and fixed
  for itself (a self-hosted release-authoring item's real deliverable
  lives under `migration/overlays/<version>/`, not the installed
  `.claude/commands/`/`scripts/` copy). Reproduced directly:
  `compute_review_content_id_implementation_stage` raised
  `UnclassifiedPathError` on `.workflow-manager/installation.json` before
  a single line of implementation existed, and every one of this item's
  then-eight checkpoints' (CP1-CP8, as numbered at revision 2; CP6/CP7/CP8
  are today's CP11/CP12/CP13 after revision 3's renumbering, §3) own named
  deliverable paths (the `migration/overlays/2.5.0/` tree,
  `distribution/workflow/2.5.0/`, `tests/`, `tools/build_release.py`,
  `CLAUDE.md`) was either unclassified or, for `CLAUDE.md`, wrongly
  `excluded` even though revision 2's own CP8 (today's CP13) names it as a
  deliverable. Fixed at revision
  2, using `plan-amendment-mechanism-artifacts.json` as the worked
  precedent: `implementation_stage.protected_prefixes` now covers
  `migration/`, `distribution/workflow/2.5.0/` and `tests/`;
  `protected_paths` adds `tools/build_release.py` and `CLAUDE.md`;
  `.claude/commands/`/`scripts/` move to `excluded_prefixes` (the
  installed copy, not this item's own deliverable);
  `.workflow-manager/installation.json` and `docs/defects/` join
  `excluded_paths`/`excluded_prefixes` for the same reasons B2 gives at
  the plan stage. Verified: `compute_review_content_id_implementation_stage`
  now succeeds, and every revision-2-era CP1-CP8 deliverable path
  classifies `protected`.
  This is an `implementation_stage`-only edit, so it leaves the plan-stage
  `review_content_id` unchanged (`docs/ai-workflow/REVIEW_PROTOCOL.md`'s
  "Repairing an artifact declaration after an approval" table) — verified
  directly, not merely asserted.
- **Corrected at revision 3 (`LOCAL_MODEL_PLAN_REVIEW` round 2, finding
  I2).** Revision 2 stated that CP1's new `IMPLEMENTATION_REVIEW_WORKFLOW.md`
  operator guide "classifies `excluded` at the implementation stage (via the
  `docs/ai-workflow/` prefix), never bound by technical approval." That is
  true only of an *installed* `docs/ai-workflow/` copy, which this milestone
  never writes. CP1's own registry entry places the guide "in the same
  overlay" — i.e. at
  `migration/overlays/2.5.0/payload/docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md`
  — which classifies **protected**, via `implementation_stage.protected_prefixes['migration/']`
  (verified directly: `classify_path_implementation_stage` returns
  `"protected"` for that exact path against this item's own declarations
  file). Round 1's optional finding 4 made the same conflation and revision
  2 inherited it unchecked rather than re-verifying it. The correct
  statement, matching CP1's/CP4's/CP11's own overlay-authoring design
  throughout this plan: every document this milestone's overlay adds or
  edits under `migration/overlays/2.5.0/payload/docs/ai-workflow/` —
  `WORKFLOW_V2_PLAN.md`'s new design-decision sections, `MILESTONE_WORKFLOW.md`,
  `REVIEW_PROTOCOL.md`, the new `IMPLEMENTATION_REVIEW_WORKFLOW.md` guide,
  and `WORKFLOW_V2_1_OPERATOR_REFERENCE.md` — classifies `protected` via the
  `migration/` prefix, and is therefore bound by this work item's own
  `technical_approval`, exactly like every other overlay-payload file this
  milestone's checkpoints (CP2-CP5, CP6-CP10, CP11) touch. It is only the
  *installed*, already-committed
  `docs/ai-workflow/` copy at repository top level — the one a later
  `workflow_manager update` will eventually replace — that the blanket
  `docs/ai-workflow/` exclusion in both `plan_stage` and
  `implementation_stage` correctly keeps out of this item's own review
  surface (another item's or the tooling's own bookkeeping, per that
  exclusion's stated reasoning). `PLAN_REVIEW_WORKFLOW.md`'s own
  plan-stage exclusion (`excluded_paths`, not a prefix) is a genuinely
  different case: it names one specific already-existing *installed* file
  directly, excluded from this item's own plan-stage review surface for the
  same reason the blanket `docs/ai-workflow/` prefix exclusion exists.
  **Corrected further at revision 8 (`LOCAL_MODEL_PLAN_REVIEW` round 7,
  finding B1(b)) — this bullet previously went on to say
  `PLAN_REVIEW_WORKFLOW.md` "is unaffected by this correction… not an
  overlay path this milestone authors." That was true only until this
  round's own B1(d) above assigned `PLAN_REVIEW_WORKFLOW.md`'s `"2.2"`
  widening to CP1: once CP1 edits
  `migration/overlays/2.5.0/payload/docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`,
  it too is one more overlay-payload path this milestone authors, exactly
  like `MILESTONE_WORKFLOW.md` above, and is bound by this item's own
  `technical_approval` on that basis. What stays genuinely unaffected is
  only the plan-stage exclusion itself: the *installed* root copy this
  item's own declarations file excludes is a different file from the
  overlay copy CP1 edits, so the exclusion's reasoning still holds
  independent of this correction.**
- **Missing requirements / migration risk**: none identified beyond
  what §5 already states — this is a purely additive capability, and its
  own governing-version gating is the mechanism that keeps migration risk
  at zero for every existing work item.
- **Usability gap**: an operator who has only ever driven the single-stage
  implementation-review flow will need the same "upload to ChatGPT, paste
  back" muscle memory the plan-review protocol already taught them — no
  new interaction shape, so no new operator documentation burden beyond
  CP1's own operator-guide update.
- **Unnecessary complexity check**: considered generalizing
  `record_local_plan_review`/`record_manual_plan_review` into
  stage-parametric functions shared by both plan and implementation
  reviews, rather than writing parallel implementation-stage functions.
  Rejected for this milestone: the plan-side functions are already
  shipped, tested, and referenced by name throughout
  `docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s `D-Plan-Review-Stages` and its
  own test suite; retrofitting them to be stage-generic is a real,
  separate refactor with its own risk, and is exactly the kind of
  broader-redesign scope the user asked to keep out of this milestone.
  Recorded here so a reviewer does not need to re-raise it as a missing
  finding — CP1 states the same call under §2.1's "Exception/helper reuse
  vs. new names."
- **Missing tests check**: §6 covers unit/integration/release/functional
  layers; CP5's planted-defect fixture is the one net-new test class
  revision 2 added beyond what mirroring `D-Plan-Review-Stages`'s own test
  suite shape already implies; revision 3 adds CP3's two B1(a)/B1(b) tests,
  CP12's recovery-command negative path, and CP6/CP7/CP8/CP9's own new
  test classes for the review-scalability and backlog branches (§6);
  revision 4 adds CP3's recovered-role field-diff and committed-phase
  tests (B1/B2), CP3's `"post-fix"`-from-`AWAITING_FUNCTIONAL_REVIEW` unit
  test and CP12's matching functional scenario (I2), and CP9's
  `by_version["2.5.0"]`-resolution test (I4); revision 5 widens CP3's
  recovered-role committed-phase test and CP12's matching functional
  scenario to the third, terminal phase and adds CP3's negative
  `"1"`/`"2.1"`-recovery-refusal test (round-4 finding B1).
- **Revision 3's own B1(a)/B1(b) resolution (`LOCAL_MODEL_PLAN_REVIEW`
  round 2, finding B1) is recorded in full in §2.1** (the provenance-interval
  subsection), not repeated here — it retracts revision 2's "needs no
  change for `"2.2"` at all" claim and assigns both fixes to CP3. This
  bullet exists only as the same kind of pointer §7's other bullets already
  give for revision-2-era corrections, per `D-Review-Material-Lifecycle`'s
  own convention (§2.4) of stating a correction once, at its own site, and
  cross-referencing it from the disposition log rather than restating it.
- **Revision 4's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 3) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: B1 (revision 3's field-set widening covered only the
  ordinary role; the actually-affected commit shape is the recovered role,
  §2.1) and B2 (the recovered role's committed-phase clause needed a
  membership test, not single-valued equality, §2.1) together retract and
  fix revision 3's own B1(b) fix; I1 (no separate
  `transition_to_awaiting_local_implementation_review` writer, §2.1) and I2
  (the `AWAITING_FUNCTIONAL_REVIEW` post-fix source phase and CP4's
  command-list gap, §2.1) are both resolved where §2.1 states them; I3's
  `build_rolled_back_config` typo and the retracted provenance sentence are
  fixed in CP1's own registry entry (§3); I4 (`2.5.0`'s required, empty
  `portability_exceptions.json` entry, not a shrink of `2.3.1`'s/`2.4.0`'s)
  is fixed at §2.7 points 1-2, §6, and CP9/CP11's registry entries; I5 (the
  finding tag is advisory, never parser-rejected) and I6 (the
  circuit-breaker bound is fixed at 2, not left open) are both resolved in
  §2.6 and §9; the governing-version-absent rule for
  `validate_bundle_generation_record_commit` (Migration and data-integrity
  concerns) is stated in §5; optional findings 1-3 are addressed at §2.4,
  §2.7 point 1, and §4's new REQ-14 respectively.
- **Revision 5's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 4) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: B1 (the recovery command's own phase guard and
  `bundle_generation_recovered_role_legal_committed_phases`'s `"2.2"` set
  both omitted the terminal phase, `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`
  — the one phase from which `/recover-implementation-provenance` is the
  only in-band escape — both widened to the full three-phase set, and the
  resulting three-set invariant stated explicitly, §2.1) is fixed where
  §2.1 states it, with CP3/CP4/CP12's registry entries and §6's test list
  updated to match; I1 (two stale `"CP7"` disposable-repo cross-references,
  meaning CP12, at §2.2 and §2.3) is fixed at both sites; I2 (the
  `AMENDMENT_DIFF.patch` disclosure line `REVIEW_PROTOCOL.md` requires
  unconditionally at the plan stage was missing from `REVIEW_REQUEST.md`)
  is a bundle-content fix, restated in this round's own `REVIEW_REQUEST.md`;
  optional findings 1-4 are addressed at §5, §2.1, §2.6 point 3, and §9's
  closing paragraph respectively.
- **Revision 6's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 5) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: B1 (four exact-equality `governing_workflow_version == "2.1"`
  gates on the *plan* side — `publish_plan_revision`,
  `plan_approval_gate_reachable`, `_require_v2_1_plan_review` and
  `_validate_plan_review_stages` — inherited nothing for `"2.2"`; fixed by
  stating the inheritance rule and widening all four to a
  `TWO_STAGE_PLAN_REVIEW_VERSIONS` membership test, §2.2) is fixed where
  §2.2 states it, with CP2/CP4/CP12's registry entries, §4's new REQ-15 and
  §6's two new test entries updated to match; optional findings 1-4 are
  addressed at §2.1's divergence-4 subsection, §2.1's recovered-role
  invariant note, **§2.1's own prose** (the
  `IllegalImplementationProvenanceRecoverySourcePhaseError` docstring
  update, assigned there to CP3 — corrected at revision 7, `LOCAL_MODEL_PLAN_REVIEW`
  round 6, finding I1: this bullet originally said "CP3's registry entry,"
  which was never true; CP3's registry entry names no such docstring, only
  §2.1's prose does), and §2.1's B1(b) test-count paragraph respectively.
- **Revision 7's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 6) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: B1 (the inheritance rule was stated and applied only to the
  plan-review surface — four code gates and six command documents — leaving
  three further surfaces unwidened: `/milestone-implement.md`'s own step 0
  branch set, `MILESTONE_WORKFLOW.md`'s plan-review state text, and four
  more command documents' two-version enumerations; fixed by restating the
  rule in its general, unscoped form and widening all three surfaces, §2.2)
  is fixed where §2.2 states it, with CP1's and CP4's registry entries,
  CP11's registry entry (the resulting overlay full-replacement-payload
  obligation), §4's widened REQ-15, and §6's two new test entries (CP6's
  mechanical sweep, CP12's named `/milestone-implement` traversal) updated
  to match; I1 (the revision-6 disposition bullet immediately above
  misstated Optional 3's landing site as "CP3's registry entry" instead of
  "§2.1's prose") is fixed by correcting that bullet's own wording in
  place, and by the matching correction in this round's `REVIEW_REQUEST.md`;
  optional findings 1-3 are addressed at §2.2 (the `promote_legacy_work_item`
  docstring-justification clause, corrected in the docstring itself under
  CP3; the `transition_to_awaiting_local_plan_review` docstring correction
  under CP2; and the `TWO_STAGE_PLAN_REVIEW_VERSIONS` shape reasoning
  recorded beside the constant) respectively. Everything round 6's own
  required acceptance criterion 6 named as settled — the `"2.2"` gating
  decision and §2.2's core argument, §2.1's phase/ledger/verdict design,
  the retraction and revisions 3/4's B1(a)/B1(b)/B2 framing, revision 5's
  three-set resolution and its I1/I2 fixes, §2.4-§2.7's scope and factual
  bases, §8's per-defect dispositions, §6's test list beyond this round's
  two additions, §9.1/§9.2/§9.3 (still open, on which this round takes no
  position), B1's own four-site code fix and `TWO_STAGE_PLAN_REVIEW_VERSIONS`'s
  shape, the four-site list's exhaustiveness for the plan-review protocol,
  REQ-15's existence and separateness from REQ-1, CP2/CP4/CP12's registry
  propagation of round 5's B1, §6's two round-6-era test entries, and all
  four of round 5's optional findings as taken — stays settled; this
  revision revisits none of it.
- **Revision 8's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 7) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: B1 (the round-6 inheritance-rule sweep was hand-enumerated
  again and came up four sites short — `PLAN_REVIEW_WORKFLOW.md` entirely,
  two `WORKFLOW_V2_1_OPERATOR_REFERENCE.md` sites outside CP4's cited scope,
  two `MILESTONE_WORKFLOW.md` sites outside CP1's cited scope, and two
  command frontmatter lines — and, more consequentially, CP6's own lint
  predicate could not have caught most of them, since it tested only the
  `{"1", "2.1"}`-enumeration form and not the bare `"2.1"`-scoped-assertion
  form the majority of real sites use) is fixed where §2.2 states it, with
  CP1's, CP4's, CP6's and CP11's registry entries, §4's restated REQ-15, and
  §6's corrected CP6 test entry updated to match; I1 (`/milestone-implement.md`'s
  step 0 branch set was assigned to both CP1 and CP4 at once — §2.2 and
  CP4's own registry entry correctly to CP4, CP1's own registry entry and
  §4's REQ-15 discussion incorrectly repeating it) is fixed by removing the
  duplicate from CP1's registry entry and §4's discussion, leaving CP4 as
  the fix's one owner; I2 (`build_rolled_back_config`'s generalization
  described only the guard, not the rollback destination, which as
  literally described would target the fixed `"1"` literal rather than the
  version activation superseded) is fixed at §2.2's activation-mechanism
  paragraph, with CP1's and CP2's registry entries updated to match.
  Optional findings 1-3 are addressed at §2.2 (the
  `workflow_fingerprint.py:1081` docstring correction declined with
  repository evidence — the finding's own premise that CP9 already opens
  this module does not hold, verified directly; the "any other governing
  version: refuse, naming it" default in every dual-mode command's step 0,
  assigned to CP4) and §2.4 (the in-place-
  correction convention itself named as part of `D-Review-Material-
  Lifecycle`) respectively. Everything round 7's own required acceptance
  criterion 8 named as settled — the `"2.2"` gating decision and §2.2's core
  argument; §2.1's phase/ledger/verdict design; the retraction and
  revisions 3/4's B1(a)/B1(b)/B2 framing; revision 5's three-set resolution
  and its I1/I2 fixes; §2.4-§2.7's scope and factual bases; §8's per-defect
  dispositions; §6's test list beyond this round's own additions;
  §9.1/§9.2/§9.3 (still open, on which this round takes no position); B1's
  four-site code fix and `TWO_STAGE_PLAN_REVIEW_VERSIONS`'s shape; the
  four-site list's exhaustiveness for the plan-review protocol *in code*;
  REQ-15's existence and separateness from REQ-1; and round 5's four
  optional findings as taken — stays settled, plus everything round 7
  itself verified correct: §2.2's general inheritance rule as worded;
  revision 7's own (a)/(b)/(c) widenings and every citation in them; CP6's
  sweep as the right *kind* of artifact; CP12's `/milestone-implement`
  traversal and its committed-phase assertion at `T`; round 6's I1 fix and
  the in-place-errata convention it used; and all three of round 6's
  optional findings as taken. This revision revisits none of it.
- **Attribution, corrected at revision 10 (`LOCAL_MODEL_PLAN_REVIEW` round
  9, optional finding 2): the paragraph below misattributes round 7's own
  eight required acceptance criteria to round 8 — round 8 stated five (as
  that same paragraph correctly says two sentences earlier); it was round
  7 that stated eight, and reproducing those eight against the repository
  is what round 8 did.**
- **Revision 9's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 8) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: I1 (the occurrence-granularity allowlist's two exemption
  shapes had no home for an occurrence that is correct as written — a
  negated or version-independence assertion — and CP6's catch-all's own
  "exhaustive" allowlist sentence forbade the implementer's only other move,
  adding an allowlist entry; separately, two genuinely-stale
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md` `## Known discrepancies` sites
  reached neither allowlist shape) is fixed at §2.2 by narrowing the two
  detection forms themselves to exclude a negated/version-independence
  assertion (not a third allowlist entry — `MILESTONE_WORKFLOW.md:424` and
  `apply-functional-review.md:34` confirmed correct as written and not
  reworded) and by naming `## Known discrepancies` explicitly in the lint's
  scope with `:882`/`:892` assigned to CP6's catch-all, with CP6's registry
  entry and §6's CP6 test entry (one further positive fixture) updated to
  match; I2 (§2.2 quoted CP11's registry entry as saying "every payload
  document the sweep requires changing" when the registry actually said
  "every payload document CP1's or CP4's own round-6/round-7 plan-review
  inheritance widening requires changing" — narrower, and silently
  excluding CP6's own catch-all fixes from the recorded overlay obligation)
  is fixed by widening CP11's registry entry to the wording §2.2 already
  quoted, so both agree and the recorded scope now covers CP6's fixes too.
  Optional findings 1-3 are addressed at §2.2 (the `build_rolled_back_config`
  rollback-destination paragraph, stating the predecessor comes from an
  explicit mapping or caller-supplied parameter, never version-string
  comparison; CP6's registry entry, which now states the fixture
  obligation alongside the predicate and allowlist it already stated) and
  at CP4's registry entry (`/apply-implementation-review.md`'s own existing
  `"1"`/`"2.1"` step-0 dual-mode enumeration stated as staying
  byte-unchanged, mirroring the note CP4's entry already carries for
  `/review-implementation.md`'s advisory branch) respectively. Everything
  round 8's own required acceptance criterion 5 named as settled —
  revision 8's own (d)/(e)/(f)/(g) assignments and every citation in them;
  the lint's two-form predicate; the occurrence-granularity allowlist's own
  *granularity* decision; CP6 as the checkpoint that fixes sites beyond
  CP1's/CP4's named lists, and the registry array-order reasoning that makes
  it sound; the removal of the `/milestone-implement.md` duplicate, leaving
  CP4 as sole owner; the rollback-destination fix in substance; the decline
  of round 7's optional finding on `workflow_fingerprint.py:1081`; §2.4's
  in-place-correction convention; §4's generally restated REQ-15; and §6's
  two new test statements — stays settled, plus everything round 8 itself
  verified correct (§2.2; `LOCAL_MODEL_PLAN_REVIEW` round 7's own eight
  required acceptance criteria, all independently reproduced against the
  repository; the sweep re-run by hand finding no unassigned site beyond
  I1's own two; the four allowlisted documents confirmed the right four
  **(superseded at revision 15, `MANUAL_EXTERNAL_PLAN_REVIEW` round 1,
  finding I2, and again at revision 17, `LOCAL_MODEL_PLAN_REVIEW` round 16,
  finding I2: narrowed to three, `WORKFLOW_V2_PLAN.md` dropped — see §2.2 —
  so this entry no longer names a settled fact and is not to be
  re-litigated as though it still did)**).
  This revision revisits none of it.
- **Revision 10's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 9) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: I1 (nothing gave any repository other than this one a way
  to reach `governing_workflow_version: "2.2"`, so the milestone's
  headline capability shipped dormant everywhere except CP12's disposable
  test repo — no requirement and no checkpoint deliverable covered
  reachability) is fixed by §2.2's new "Reachability" and "Template
  question" paragraphs (the two-field `WORKFLOW_CONFIG.json` edit and
  trailer discipline, documented as its own section in CP1's new
  `IMPLEMENTATION_REVIEW_WORKFLOW.md`; the template deliberately staying
  at `"2.1"`, with the pre-enabled alternative declined and its own reason
  recorded), §5's second bullet cross-referencing both, §4's new REQ-16
  (mapped to CP1 and CP12, which already exercises the activation), and
  CP1's registry entry widened to state the operator-guide obligation
  explicitly. Optional findings 1-3 are addressed at §2.2's "Known
  discrepancies" paragraph (optional 3's citation precision — `:882` and
  `:892` are item 4's and item 5's own opening lines, not the lines the
  quoted sentences themselves sit on; optional 1's extent correction — the
  section's stale occurrences are not limited to those two items, and
  CP6's registry entry is widened to match) and at this section's own
  attribution-correction bullet immediately above (optional 2). Everything
  round 8's own required acceptance criterion 5 named as settled —
  revision 9's predicate-scope narrowing and its two named instances; `##
  Known discrepancies` as in-scope and as CP6's catch-all's work (only the
  sentence's *extent* was at issue, now corrected); CP11's widened
  registry wording and §2.2's agreement with it; the rollback-predecessor
  derivation mechanism; CP6's further positive fixture; the four-site code
  gate list's exhaustiveness; the four allowlisted documents **(superseded
  at revision 15, `MANUAL_EXTERNAL_PLAN_REVIEW` round 1, finding I2, and
  again at revision 17, `LOCAL_MODEL_PLAN_REVIEW` round 16, finding I2:
  narrowed to three, `WORKFLOW_V2_PLAN.md` dropped — see §2.2 — so this
  entry no longer names a settled fact and is not to be re-litigated as
  though it still did)**; and CP6's
  registry-array ordering after CP4 — stays settled, plus everything round
  9 itself verified correct (revision 9's five required acceptance
  criteria, all independently reproduced against the repository; the
  recurring inheritance-rule class confirmed closed a second time by an
  independent hand sweep over the `2.4.0` payload; both challenge areas —
  whether `## Known discrepancies` is the only in-scope catalogue, and
  whether version reachability and version inheritance are genuinely
  distinct questions — resolved affirmatively). This revision revisits
  none of it.
- **Revision 11's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 10) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: I1 (the binary activation/rollback event model silently
  disarms `ConfigMissingAfterActivationError`'s hard stop for a repository
  that rolls `"2.2"` back to `"2.1"`, since `find_latest_activation_event`
  reads only the trailer's key, never its value) is fixed at §2.2's new
  "Activation event model" paragraph — `is_activated` becomes version-aware
  via the same predecessor mapping `build_rolled_back_config` already uses,
  `load_config`'s raise message and `ConfigMissingAfterActivationError`'s
  docstring are generalized off the hard-coded `"2.1"` literal, both sites
  are added to CP2's registry entry, and a CP2 unit test is added at §6;
  I2 (§2.2 documented the `"2.2"` activation as a hand edit while also
  committing CP1/CP2 to generalizing helpers nothing calls, leaving the
  `supported_versions`-append behavior and both one-time-boundary guards
  without a caller or a documented path to one) is fixed at §2.2's new
  "Activation entry point" paragraph, deciding option (b): the hand edit is
  the supported path in `2.5.0`, the helpers stay library/design surface
  with no caller, generalizing them remains in CP1/CP2's scope as the
  executable specification CP2's own tests pin and as a ready-made entry
  point for a future automation verb, and `AlreadyActivatedError`/
  `NotActivatedError` therefore do not constrain the supported path; I3
  (`adopt_legacy_work_item`, named at §2.2, §7, and CP3's registry entry,
  does not exist — the function is `promote_legacy_work_item`) is fixed by
  correcting the name at all three sites, the identical class as revision
  2's own I2. Optional findings 1-2 are both taken: optional 1 at CP12's
  registry entry, binding its activation step to CP1's documented
  procedure followed verbatim, with no repository-internal shortcut;
  optional 2 by restoring the missing separator in this section's own
  round-8-disposition bullet immediately above (`"(§2.2 `LOCAL_MODEL_PLAN_REVIEW`"`
  → `"(§2.2; `LOCAL_MODEL_PLAN_REVIEW`"`), a punctuation fix carrying no new
  claim. Everything round 10's own required acceptance criterion 5 named as
  settled — revision 10's Reachability and Template-question paragraphs in
  substance (only the event model and who performs the edit were at
  issue); REQ-16's existence, wording and separateness from REQ-15; the
  `## Known discrepancies` widened fix and its extent; §2.2's
  citation-precision correction; §7's attribution correction in substance;
  the four-site code gate list, extended to the write sites; **the four
  allowlisted documents (superseded at revision 15, `MANUAL_EXTERNAL_PLAN_REVIEW`
  round 1, finding I2, and again at revision 16, `LOCAL_MODEL_PLAN_REVIEW`
  round 15, finding B1: narrowed to three, `WORKFLOW_V2_PLAN.md` dropped —
  see §2.2 — so this entry no longer names a settled fact and is not to be
  re-litigated as though it still did)**; the template decision and its
  `build_release.py` reason; and the legacy-promotion reasoning at §2.2
  (only its function name was wrong) — stays settled, plus everything
  round 10 itself verified
  correct (revision 10's five required acceptance criteria, all
  independently reproduced against the repository; the recurring
  inheritance-rule class confirmed closed a third time, `distribution/workflow/2.4.0/`
  being generated content and byte-unchanged in this working tree; the
  `## Known discrepancies` widened fix confirmed extent-complete, all ten
  `"2.1"` occurrences in the section accounted for; bundle hygiene; and
  plan-stage classification completeness). This revision revisits none of
  it.
- **Revision 12's own corrections (`LOCAL_MODEL_PLAN_REVIEW` round 11) are
  recorded in full at their own sites, not repeated here**, per the same
  convention: I1 (the version-aware event model revision 11 adopted
  introduces a lookup into a partial predecessor table, on an input domain
  — arbitrary committed `Workflow-Rollback` trailer values — that is no
  longer caller-controlled, and the plan did not say what happens on a
  miss) is fixed at §2.2's new "Rollback-trailer-value miss" paragraph: an
  unresolvable rollback destination resolves as activated (fail closed),
  the mapping stays a plain table with the miss caught by an explicit
  branch before the lookup, the activation direction is confirmed to need
  no equivalent rule, the "equivalent caller-supplied parameter"
  alternative is confirmed unavailable to `is_activated` (no target
  parameter at all), and the operator guide's missing-config sentence
  gains one clause on the trailer value now being load-bearing; the miss
  rule is added to CP2's own scope (both sites unchanged) and §6 gains the
  corresponding test case. I2 (revision 11 assigned two new
  `IMPLEMENTATION_REVIEW_WORKFLOW.md` obligations to CP1 in §2.2's
  "Activation entry point" and "Activation event model" paragraphs — that
  the hand edit is the supported path and states so explicitly, and the
  one-sentence missing-config consequence — and propagated neither into
  CP1's registry entry) is fixed by widening CP1's registry entry (§3's
  table re-rendered from it) to state both obligations verbatim, plus the
  rollback-trailer-value caution I1's own fix adds to that same operator
  guide sentence, all three now named at CP1's own site rather than only in
  §2.2's reasoning text; REQ-16's wording is untouched, per the finding's
  own instruction. Optional findings 1-2 are both taken: optional 1 widens
  CP2's site list to `AlreadyActivatedError`'s and `NotActivatedError`'s own
  docstrings (`:733-736`, `:739-743`), recorded at §2.2's generalization
  paragraph; optional 2 corrects §6's own citation from
  `scripts/workflow_state_test.py:191-216`
  (`TestActivationRollbackTransforms`, a pure-dict class with no repository
  or trailers) to `:129-141` and `TestWFActivateFourCombinations`
  (`:155-187`), the shape that already owns the four-combination
  trailer-presence axis this test extends with a fifth, trailer-*value*
  axis. **Attribution corrected at revision 13, `LOCAL_MODEL_PLAN_REVIEW`
  round 12, optional finding 2**: the following enumeration is round 11's
  own required acceptance criterion 4's list (round 11 had four criteria,
  not five, and this is that criterion's "do not treat any of this as
  grounds to revisit" list verbatim), not round 10's criterion 5 — a
  different, revision-10-era list correctly attributed one bullet above at
  `:2862`. Everything round 11's own required acceptance criterion 4 named
  as settled — revision 11's version-aware event-model decision, its two
  named boundaries, and its `load_config`/`ConfigMissingAfterActivationError`
  generalization; the I2 entry-point decision in full, option (b) and all
  four of its stated consequences; the `promote_legacy_work_item` rename at
  all three sites; CP12's procedure-binding clause; §7's punctuation fix;
  the `CI_SUITES`/`portability_exceptions` release-authoring scope;
  `default_config()`'s `:6663` being correctly untouched; challenge area 6
  answered against the alternative; and the registry/mapping delta's
  confinement to three checkpoint descriptions — stays settled, plus
  everything round 11 itself verified correct (revision 11's five required
  acceptance criteria, all independently reproduced against the repository;
  the recurring inheritance-rule class confirmed closed a fourth time,
  `distribution/workflow/2.4.0/` still generated content and
  byte-unchanged, and the overlay's own activation-region copy still
  line-for-line identical; the mechanical `scripts/*.py` sweep re-run
  finding exactly the two sites optional finding 1 names and nothing else
  unaccounted for; bundle hygiene; and plan-stage classification
  completeness against all 70 changed paths). This revision revisits none
  of it — neither finding is a position on any of §9's three open
  decisions, which stay textually unchanged and open.
- **Revision 13's own correction (`LOCAL_MODEL_PLAN_REVIEW` round 12) is
  recorded in full at its own site, not repeated here**, per the same
  convention: I1 (revision 12's new "Rollback-trailer-value miss" paragraph
  claimed the predecessor mapping's declared domain was the single entry
  `"2.2"` → `"2.1"`, which — read together with the same paragraph's own
  "found-but-`"1"` destination" clause two sentences later, which
  presupposes the opposite domain — made `Workflow-Rollback: 2.1` a
  *miss* and therefore *activated* under the fail-closed rule, inverting
  the one rollback behavior §5, REQ-15, CP2's own registry entry, and
  `scripts/workflow_state_test.py:129-134`,
  `test_rollback_after_activation_restores_pre_activation_behavior`, all
  pin as byte-unchanged) is fixed at §2.2's "Rollback-trailer-value miss"
  paragraph: the declared domain now states both entries, `"2.1"` → `"1"`
  and `"2.2"` → `"2.1"`, so a `Workflow-Rollback: 2.1` trailer is a found
  destination of `"1"`, never the miss branch, and only a value outside
  that two-entry domain reaches the fail-closed rule; the fail-closed
  decision itself, its branch-before-lookup shape, its
  activation-direction asymmetry, and its caller-supplied-parameter
  reasoning are all unchanged and correct, per this round's own required
  acceptance criterion 3. CP2's registry entry gains the matching
  one-clause correction (§3's table re-rendered from it) and §6's CP2 test
  entry gains the declared-entry regression pin round 12's own "Missing
  tests" item names, alongside the miss-side assertion it already carried.
  Optional findings 1-3 are all taken, per round 12's own required
  acceptance criterion 2: optional 1 states the raise message's source
  explicitly (the resolved destination version when one exists, the
  unresolved trailer's own value otherwise) at §2.2's generalization
  paragraph; optional 2 corrects this section's own revision-12 disposition
  bullet's misattribution (the enumeration is round 11's own required
  acceptance criterion 4's list, not round 10's criterion 5) at its own
  site immediately above; optional 3 adds a one-clause cross-reference from
  §5's downgrade-posture bullet to §2.2's miss rule, for the
  future-version-trailer direction round 11's own I1 point 2 first framed
  as a downgrade-posture question. Everything round 11's own required
  acceptance criterion 4 named as settled, and everything this section's
  own revision-12 bullet additionally settled, stays settled — I1 corrects
  one factual clause inside an already-correct decision; it does not
  reopen the decision itself. **Corrected at revision 14,
  `LOCAL_MODEL_PLAN_REVIEW` round 13, optional finding 4**: "Neither
  finding" undercounted round 12's own return of one Important and three
  Optional findings (four in total), carried over verbatim from this
  section's own revision-12-era wording where "Neither" correctly meant
  round 11's I1/I2 pair. None of round 12's four findings is a position on
  any of §9's three open decisions, which stay textually unchanged and
  open.
- **Revision 14 applies `LOCAL_MODEL_PLAN_REVIEW` round 13's `REVISE`
  feedback (one Important finding, no Blocking one, five Optional
  findings) against revision 13 (reviewed `bundle_id:
  66fd957767a9e94f671a1fbfa2a923bfce500918d2b26ad4d5369d6ab17ae918`).**
  **Required acceptance criterion 1, I1**: §2.6 point 3's bolded
  parenthetical (previously `:1856-1857`) claimed "§9's decision 3 is
  settled by this correction, not left for the plan-review gate" — wrong,
  since §9's decision 3 is `v2.4.0-002`'s `IMPL10-O1` mitigation, which
  stays open and un-recommended, exactly as §9 itself already stated. The
  correction the parenthetical was describing is §9's own
  "Circuit-breaker round bound" paragraph (§9, recorded as revision 3's
  *fourth* open decision, carrying no number since revision 4 resolved
  it) — the parenthetical now names that paragraph directly instead of a
  decision number, per the finding's own required fix. Nothing else in
  §2.6 changed: the bound of 2, its unimplementable-above-2 reasoning, the
  advisory tag, and the "no new `WORKFLOW_STATE.json` field" claim stay
  exactly as before, and §9's three open decisions (terminal-phase naming,
  `"2.2"` activation-ceremony scope, `v2.4.0-002`'s `IMPL10-O1` mitigation)
  stay textually unchanged and open — this round takes no position on any
  of them. **Optional findings 1, 3 and 4, and finding 2(a), are taken;
  finding 2(b) is declined:** optional 1 adds the `"2.1"` → `"1"` declared
  entry as its own citation clause at §2.2's derivation paragraph,
  alongside the already-correct `"2.2"` → `"2.1"` entry; optional 2(a)
  corrects CP2's registry entry so the raise-message clause matches §2.2
  `:900-908`'s actual split (the resolved destination version when one
  exists, the unresolved trailer's own value verbatim in the miss case)
  rather than unconditionally "whichever version's activation is in
  force"; **optional 2(b) is declined**: §6's CP2 test entry already
  states the declared-entry regression pin as CP2's own deliverable (added
  at revision 13, `LOCAL_MODEL_PLAN_REVIEW` round 12's required test, "An
  activation/rollback event-model unit test (CP2 ...)"), so restating that
  test clause a second time in CP2's registry `name` field would duplicate
  rather than complete the record — round 12's own required acceptance
  criterion 1 deliberately allocated the domain clause to the registry and
  the test to §6, and this round changes nothing about that split; optional
  3 states the plumbing source explicitly at §2.2's generalization
  paragraph (`find_latest_activation_event`'s own return widens to carry
  the resolved destination or the unresolved trailer's raw value,
  `load_config` reads the message source from that widened return,
  `is_activated` keeps its boolean signature unchanged); optional 4
  corrects this section's own revision-13 disposition bullet immediately
  above ("Neither finding" → "None of round 12's four findings"). Optional
  finding 5 is bundle evidence only (`TEST_RESULTS.md`'s own phrasing), not
  a plan-content finding, and is addressed at this round's own bundle
  regeneration rather than in this document. This revision reopens nothing
  round 12's own required acceptance criterion 3 named as settled, and
  everything this round's own "Verified correct — do not re-litigate" list
  independently reproduced against the repository stays settled; §9's
  three open decisions remain exactly as stated, for the manual external
  reviewer to confirm or override.
- **Revision 15 applies `MANUAL_EXTERNAL_PLAN_REVIEW` round 1's `REVISE`
  feedback (three Important findings, one Optional finding) against
  revision 14 (reviewed `bundle_id:
  94864727d9dd45937b9e5c61dea71a7942f9eadeb4ac7e0cbbe032caa4ea17c1`).**
  This is the first `MANUAL_EXTERNAL_PLAN_REVIEW` round this plan has
  received; every finding below is therefore new, not a correction of a
  prior manual-external disposition. **I1 (rollout contract for existing
  `"2.1"` work items)**: resolved by adopting contract (2) of the two the
  finding posed — `"2.2"` is future-work-item-only, with no promotion path
  for an already-existing item — stated as a new "Future-work-item-only"
  paragraph and a "Reconciled explicitly against the Controller rollout"
  paragraph in §2.2 (naming `~/Workspace/workflow-controller`'s own
  `workflow-controller-generation-1` work item as the concrete instance),
  §5's misleading "unless and until… activated" wording corrected to state
  plainly that activation is never retroactive, CP1's registry entry gains
  the matching operator-guide obligation, and CP2 gains a regression test
  proving activation mutates no already-existing work item's
  `governing_workflow_version` (§6). **I2 (CP6's whole-document exemption
  swallowing `WORKFLOW_V2_PLAN.md`'s own current sections)**: resolved by
  narrowing CP6's whole-document allowlist from four documents to three,
  dropping `WORKFLOW_V2_PLAN.md` (the active design-of-record per §2.4) so
  its own occurrences are exempt only inside its own disposition
  section(s), and by strengthening CP6's lint to fail on a
  revision/finding-disposition marker found outside a document's
  disposition section, not merely to check that a disposition heading
  exists somewhere in the file — both the CP6 registry entry and §6's CP6
  test entries gain the corresponding two new negative fixtures. **I3
  (circuit-breaker signal not recoverable across manual-external rounds)**:
  resolved by scoping §2.6's advisory two-round signal explicitly to two
  consecutive same-stage local-model rounds (`LOCAL_MODEL_PLAN_REVIEW` or
  `LOCAL_MODEL_IMPLEMENTATION_REVIEW`) — the one case where the
  single-prior-file-visibility mechanism actually holds — and stating
  explicitly that manual-external convergence remains operator judgment,
  with no recoverability claim made for it; CP8's registry entry, REQ-11,
  and §6's CP8 test entry are all corrected to match. **O1 (missing
  `v2.3.1-001` defect record in the bundle's `CONTEXT_FILES.txt`)**:
  the bundle's own `CONTEXT_FILES.txt` now lists
  `docs/defects/v2.3.1-001-host-history-coupled-tests.md` alongside the
  other three defect records, for provenance symmetry. **Required
  acceptance criterion 4 (§9's three open decisions)**: all three are now
  resolved — (b) for terminal-phase naming, the lightweight ceremony for
  activation scope, and decline for `IMPL10-O1` — recorded in place in §9,
  §2.2, §2.7 point 4 and §8, per `D-Review-Material-Lifecycle`'s point 4
  convention rather than silently dropped. **Required acceptance criterion
  5**: the plan/registry/mapping are regenerated at `plan_revision: 15` and
  a fresh local plan review is run against the new `review_content_id`
  before returning to manual-external review, per this finding's own
  instruction.
- **Revision 16 applies `LOCAL_MODEL_PLAN_REVIEW` round 15's `REVISE`
  feedback (one Blocking finding, two Important findings, one Optional
  finding) against revision 15 (reviewed `bundle_id:
  39ff360e43648d209672b481e4e53222ac901eacf225d5baef375262d6fa4c12`).**
  **B1 (§2.2's allowlist paragraph still granted `WORKFLOW_V2_PLAN.md` the
  whole-document exemption round 1's I2 required removed)**: resolved by
  restating §2.2's "Allowlist granularity" paragraph to the three-document
  whole-document list, with `WORKFLOW_V2_PLAN.md` exempt only
  occurrence-by-occurrence, recording the narrowing in place per §2.4
  point 4; and by correcting the round-10 (`LOCAL_MODEL_PLAN_REVIEW` round
  10 / revision-11) settled-list entry above so it no longer asserts "the
  four allowlisted documents" as a currently-settled fact. **I1 (revision
  15's future-work-item-only justification rested on a false "only two
  writers"/immutability premise, contradicted two pages later by its own
  round-6 bullet)**: resolved by narrowing §2.2's "Future-work-item-only"
  paragraph and §5's second bullet to what actually holds — no promotion
  path from `"1"`/`"2.1"` to `"2.2"` exists or is added by this milestone —
  and naming `promote_legacy_work_item`'s `"1"` → `"2.1"` legacy-adoption
  transition as the one existing in-place exception this milestone
  deliberately does not generalize, cross-referenced to the round-6 bullet
  that already gives the reason. **I2 (the lint-strengthening half of round
  1's I2 was stated correctly only at §6's CP6 test entry, not at §2.4
  point 3 or at CP6's own registry entry)**: resolved by restating §2.4
  point 3 to carry the strengthened marker check explicitly, and by naming
  the lifecycle lint explicitly at the point in CP6's registry entry where
  the strengthening clause sits, so it no longer reads as modifying the
  sweep clause it follows. **O1 (REQ-16's revision-15 clause was not
  traceable to the test that proves it)**: taken — REQ-16's `checkpoint_ids`
  gain `CP2`, matching CP2's own new future-work-item-only regression test
  that is the clause's actual acceptance evidence, in both this plan's §4
  table and the generated mapping. **Missing tests**: for B1, §6's CP6
  mechanical-lint fixture entry now states explicitly that its
  `WORKFLOW_V2_PLAN.md`-shaped negative fixture doubles as the executable
  check on §2.2's narrowed three-document allowlist; for I1, CP3's registry
  entry gains a regression test pinning that `promote_legacy_work_item`
  still promotes to the literal `"2.1"`, never the repository's current
  `default_workflow_version`, once that default has been separately
  activated to `"2.2"`; for I2, no new test was needed beyond §6's existing
  two fixtures; they now have the correct design-decision text to point to.
  **Required acceptance criterion 5**: the plan/registry/mapping are
  regenerated at `plan_revision: 16` and a fresh local plan review is run
  against the new `review_content_id` before returning to manual-external
  review, per this finding's own instruction.
- **Revision 17 applies `LOCAL_MODEL_PLAN_REVIEW` round 16's `REVISE`
  feedback (two Important findings, one Optional finding) against revision
  16 (reviewed `bundle_id:
  6796c3a1ee638169a41beae9f256c6d4d510b55ab666abc65b33660538993ec1`).**
  **I1 (§2.1's B1(a) resolver paragraph still stated the retired
  field-immutability premise, as its own load-bearing safety argument, at a
  third site round 15's and round 16's own I1 sweeps had not reached)**:
  resolved by restating the paragraph's safety argument to the read's
  actual anchor — reading `governing_workflow_version` from the commit's
  own committed dict resolves the value in force at that commit regardless
  of any later change to the live entry — with the retired premise quoted,
  attributed, and cross-referenced to §2.2's corrected "Future-work-item-only"
  paragraph, per §2.4 point 4. **I2 (two of §7's three "stays settled"
  entries asserting "the four allowlisted documents" were left uncorrected
  when only the one round 15 cited by line was fixed)**: resolved by
  annotating the revision-9 and revision-10 disposition bullets' own
  settled-list entries (immediately above) the same way the revision-11
  bullet's entry already was, so no §7 entry now asserts the four-document
  allowlist as a currently settled or currently verified fact. **I3 (the
  allowlist-pin fixture that discharges round 15's missing test 1 was filed
  under the lifecycle lint, which cannot fail it, and was absent from the
  sweep's own fixture list)**: resolved by moving the `WORKFLOW_V2_PLAN.md`-shaped
  negative fixture, with its allowlist-pin sentence, from §6's lifecycle-lint
  bullet into §6's governing-version sweep bullet's own fixture list, leaving
  the lifecycle bullet's "fixtures pin this" sentence to the one fixture that
  actually exercises the marker check; CP6's registry entry receives the
  matching move. **O1 (round 15's whole-document-allowlist invariant was
  neither adopted nor recorded as declined)**: taken — §2.2's "Allowlist
  granularity" paragraph gains one sentence conditioning whole-document
  exemption on no checkpoint writing to the document, independently
  reconfirmed true and cheap for the current three-document set. **Missing
  tests**: none of the three findings need one — I1 corrects a stated
  reason with no behavioral component; I2 is §7 disposition prose, not a
  checkable artifact; I3's fixture already exists in the plan's own test
  inventory and the correction is only to state it at the fixture's actual
  site of record. **Required acceptance criterion 5**: the plan/registry/mapping
  are regenerated at `plan_revision: 17` and a fresh local plan review is
  run against the new `review_content_id` before returning to
  manual-external review, per this finding's own instruction.
- **Revision 18 applies `LOCAL_MODEL_PLAN_REVIEW` round 17's `REVISE`
  feedback (one Important finding, one Optional finding) against revision
  17 (reviewed `bundle_id:
  3903e62042f9b85eb4a90bf399684b91bc48c157e1ba565612d60b88e83702d0`).**
  **I1 (§2.4 point 3's marker-check granularity was unresolved against the
  one existing corpus in its scope — its subject named "new sections," its
  predicate named "a document's own disposition section," and its declared
  minimum pattern set was drawn from this plan's own vocabulary rather than
  from the policed document's, so the check was either vacuous or, under
  the "at minimum" clause's own invitation to widen, contradicted its own
  "changes no existing document's validity" guarantee)**: resolved by
  stating explicitly, at §2.4 point 3 (the design-decision site of record),
  at §6's lifecycle-lint bullet, and at CP6's registry entry, that for
  `WORKFLOW_V2_PLAN.md` the check runs only over that document's own
  new/current sections — the specific `D-*`-numbered decision headings CP1
  adds — never over its pre-existing content, which sits structurally
  outside the check's own input rather than merely exempt from it; and that
  the marker pattern set is drawn from the vocabulary this milestone's own
  new prose actually uses, not from the excluded legacy region's.
  (**Corrected at revision 20, `LOCAL_MODEL_PLAN_REVIEW` round 19, finding
  I5(c): this bullet previously read "(this plan's own §7, 18/12/6
  occurrences of the three forms)" here — the same retired figure §2.4
  point 3 had already dropped at revision 19 without correcting this
  cross-reference. This plan does not state a self-referential occurrence
  count, at this revision or any future one, per §2.4 point 3's own
  revision-20 correction (finding I5(b)).**) A matching negative
  fixture (a `WORKFLOW_V2_PLAN.md`-shaped document carrying a
  legacy-vocabulary disposition paragraph outside its own new-section
  boundary, which the lint must pass) is added at all three sites. **O1
  (`route_work_item`'s own docstring, `scripts/workflow_state.py:7338-7342`,
  still states the retired field-immutability premise as a flat, unscoped
  claim)**: declined for this pass, recorded here rather than taken as a
  registry-entry edit. (**Corrected at revision 19,** `LOCAL_MODEL_PLAN_REVIEW`
  round 18, finding O1: this decline previously gave a second reason —
  "this command authors plan text only (`/apply-plan-review` performs no
  product-code change)" — that declines an option round 17's O1 never
  offered; round 17 named "adding the site to CP3's registry entry" as the
  take-it path, and a registry entry is plan text, exactly what
  `/apply-plan-review` authors. The docstring edit itself would be CP3's own
  implementation work, not this command's, which is the point that reason
  presumably meant; it is dropped here rather than restated, since the
  decline's real basis is the one below.) The sentence is defensible read
  strictly against `route_work_item`'s own resume branch, which genuinely
  never writes `governing_workflow_version`; CP3 already carries the
  sibling `promote_legacy_work_item` docstring correction (§3, CP3's
  registry entry), and a future revision remains free to fold this second
  site into that same checkpoint's scope if a reviewer weighs the reader-facing
  ambiguity O1 describes as worth taking up before implementation begins.
  **Missing tests**: for I1, the corpus-vocabulary fixture named above,
  added at all three sites (§2.4 point 3's own description, §6's
  lifecycle-lint bullet, and CP6's registry entry); for O1, none — no
  behavioral or code change was made. **Required acceptance criterion 5**:
  the plan/registry/mapping are regenerated at `plan_revision: 18` (CP6's
  registry entry is the only checkpoint text that changes; no
  `checkpoint_ids` list, requirement wording, or ledger field changes) and a
  fresh local plan review is run against the new `review_content_id` before
  returning to manual-external review, per this finding's own instruction.
- **Revision 19 applies `LOCAL_MODEL_PLAN_REVIEW` round 18's `REVISE`
  feedback (four Important findings, one Optional finding) against revision
  18 (reviewed `bundle_id:
  26631dd9f8b02ae04c87e3e7492c58de7feb76486ca2edc52dddd78219558818`).** No
  Blocking findings; no design decision reviewed in rounds 1-17 was
  reopened, and every finding asked for a specification correction, a
  fixture strengthening, or a measurement fix. **I1 (extending revision
  18's single "new/current sections only" extent to the heading-presence
  half made that half unsatisfiable for `WORKFLOW_V2_PLAN.md`: its
  disposition headings are `##`-level, while the `D-*` decision
  headings the extent runs from are `###`-level, so a `###`-delimited
  extent can never contain a `##`-level heading — **corrected at revision
  20, `LOCAL_MODEL_PLAN_REVIEW` round 19, finding I5(a): this bullet
  previously read "its 89 disposition headings are all `##`-level", which
  is false; 83 of the 89 `^#+ .*[Dd]isposition` regex matches are
  `##`-level, the other 6 are `###`-level headings that merely contain the
  word "disposition," which does not change the practical fact this finding
  needed** (further corrected at revision 22, `LOCAL_MODEL_PLAN_REVIEW`
  round 21, finding I5: the just-quoted "merely contain the word
  'disposition'" characterization of the 6 `###`-level matches is itself
  false — at least one of them, `:4171`
  (`` ### `OPUS-R25-*` external review disposition (revision 16 → 17,
  `Status: REVISE`) ``), is a genuine `###`-level disposition-section
  heading, not an incidental textual match. This does not change the
  practical fact revision 19's finding needed (a `###`-delimited extent
  cannot contain a `##`-level heading regardless of which `###` matches are
  genuine), which is why the error survived two rounds uncorrected until
  round 21 executed the finished specification against the real payload
  bytes rather than re-reading the prose)**)**: resolved by scoping the
  two halves differently — heading-presence stays document-scoped,
  marker-check stays extent-scoped — stated at §2.4 point 3, §6's
  lifecycle-lint bullet and CP6's registry entry. **I2 (the extent input
  was defined by checkpoint authorship, uncomputable from a lint over the
  built payload, and under-inclusive — CP6's own
  `D-Review-Material-Lifecycle` section was outside its own convention's
  lint)**: resolved by replacing it with an explicit, document-declared
  list of three heading strings (CP1's two plus CP6's own), stating where
  CP1's non-`D-*` "two-stage mirror genuinely diverges" subsection falls
  (nested under `D-Implementation-Review-Stages`, inside that heading's own
  extent), dropping the "named explicitly at CP1's registry entry" claim
  (CP1's registry entry describes the decisions in prose; §2.4 point 3 is
  the declared list's actual site of record), and correcting CP6's registry
  entry's "this checkpoint (CP1)" attribution to name CP1's two headings and
  CP6's own separately. **I3 (the corpus-vocabulary fixture could not fail
  on the boundary it was added to pin: none of the three declared marker
  forms occurs in the real document at all, so the fixture passed under
  both the extent-scoped resolution and an unimplemented whole-document
  reading alike)**: resolved by adding a literal declared-set marker to the
  fixture's out-of-extent legacy paragraph, so the same marker inside a new
  section fails and outside every new-section extent passes — a pass/fail
  pair that is test-bearing rather than incidental — stated at §6's
  lifecycle-lint bullet and CP6's registry entry. **I4 (both corpus
  measurements revision 18 added were misattributed: "this plan's own §7
  uses the three forms 18, 12 and 6 times respectively" were round 17's own
  whole-document line counts, not §7's — only "Corrected at revision"
  occurs in §7 at all, 3 times; and "lines 5-25" understated the excluded
  legacy region, actually the payload's entire pre-first-heading narrative,
  `:2`-`:3062`)**: resolved by dropping the §7 count claim (keeping the
  three forms, acknowledging this plan's own usage is predominantly
  inline-in-normative-text per point 1 above) and restating the legacy
  region as `:2`-`:3062` with counts that match that region (8/15/17/8,
  unchanged numerically from revision 18's mislabeled "lines 5-25" count,
  since none of the four forms recurs past `:3062`), at §2.4 point 3, §6's
  lifecycle-lint bullet and CP6's registry entry; `TEST_RESULTS.md` no
  longer restates the retired figures as independently confirmed. **O1
  (§7's own revision-18 O1 decline gave a first reason that declined an
  option round 17 did not offer)**: corrected in place, above, quoting the
  superseded wording and naming this round as the correcting one, per this
  convention's own point 4. **Missing tests**: for I1, the document-scoped
  heading-presence fixture (a document whose only disposition heading sits
  outside every new-section extent must still pass that half); for I2, the
  CP6-authored-section marker fixture (a declared-set marker inside
  `D-Review-Material-Lifecycle` must fail); for I3, the strengthened
  corpus-vocabulary fixture's own pass/fail pair, above; for I4 and O1,
  none — both are text corrections, no behavioral or code change is made.
  **Required acceptance criteria 1-6**: applied at §2.4 point 3, §6's
  lifecycle-lint bullet and CP6's registry entry as described above; the
  plan/registry/mapping are regenerated at `plan_revision: 19` (CP6's
  registry entry is the only checkpoint text that changes; no
  `checkpoint_ids` list, requirement wording, or ledger field changes) and a
  fresh local plan review is run against the new `review_content_id` before
  returning to manual-external review, per criterion 6's own instruction.
- **Revision 20 applies `LOCAL_MODEL_PLAN_REVIEW` round 19's `REVISE`
  feedback (four Important findings, one Optional finding) against revision
  19 (reviewed `bundle_id:
  afde8a953d4ae6394f06869ca2ee1f98722bacb3b7d7c21fc9a92b66739b225a`).** No
  Blocking findings; no design decision reviewed in rounds 1-18 was
  reopened. Round 19 independently verified round 18's four Important
  findings, its Optional finding, and all six required acceptance criteria
  as applied before looking for anything new, and found the remaining
  defect by executing the finished specification against the two documents
  it runs on, as a lint author would. **I1 (revision 19 added
  `D-Review-Material-Lifecycle` to the marker check's own declared input,
  and a fixture requiring a declared-set marker inside that section to
  fail — but that section is the one place the payload declares the
  pattern set at all, so a correct, honest declaration of the three
  literals necessarily contains them, and CP6's own convention-declaring
  section would fail the lint it authors)**: resolved by moving the pattern
  set's own declaration into a payload-local block inside
  `D-Review-Material-Lifecycle`'s extent and exempting an occurrence inside
  that block's own recitation from the marker check, at occurrence
  granularity, mirroring §6's own disposition-section exemption — stated at
  §2.4 point 3, §6's lifecycle-lint bullet and CP6's registry entry. **I2
  (revision 19's "checked whole for both halves" makes the marker check
  cover `IMPLEMENTATION_REVIEW_WORKFLOW.md`'s own required disposition
  section, forbidding exactly the markers point 2 requires there; two
  predicates — "no marker outside a disposition section" and "no marker
  inside a new section's extent" — collapsed inconsistently once the extent
  became the whole document)**: resolved by adding a second occurrence
  carve-out, identical in kind to I1's, exempting the document's own
  disposition section from the marker check regardless of whether the
  extent is a `D-*` section or the whole document — one predicate that
  survives both cases, stated at the same three sites. **I3 (the declared
  heading list's stated site of record, §2.4 point 3, is this repository's
  own plan text, not part of the `2.5.0` payload the lint reads, so an
  implementer must hardcode it and no rule obliges a future release to keep
  it current as `WORKFLOW_V2_PLAN.md` grows)**: resolved by moving the list
  into the same payload-local declaration block I1 introduces, with the
  lint itself asserting set-equality between the block's list and the
  document's actual `D-*` headings — a `D-*` section absent from the block,
  or a block entry naming a heading absent from the document, both fail —
  so the growth rule is enforced mechanically rather than left as an
  unstated obligation, stated at the same three sites. **I4 (§2.4's "holds
  for any future widening" guarantee is established only for the marker
  check's excluded pre-existing region, but is stated unrestrictedly, and
  CP1's own carried subsection — inside `D-Implementation-Review-Stages`'s
  extent per revision 19's own ruling — carries four inline disposition
  parentheticals in its own normative text, which point 1 forbids and which
  a plausible future widening of the pattern set would catch)**: resolved
  by dropping "verbatim" from §2.1's carry sentence — CP1 now carries the
  subsection's substantive content in full, with its four disposition
  parentheticals restated as entries in `WORKFLOW_V2_PLAN.md`'s own
  disposition section instead of inline — and by scoping §2.4's guarantee
  to the region the premise actually supports (the excluded pre-existing
  content, the declaration block's own recitation, and every named
  document's own disposition section), stated at §2.1's carry sentence and
  §2.4 point 3. **I5 (three measurement/record errors)**: (a) "89
  disposition headings are all `##`-level" is false — 83 of the 89
  `^#+ .*[Dd]isposition` matches are `##`-level, 6 are incidental `###`
  matches (e.g. `:4171`) — corrected at §2.4 point 3, §6's lifecycle-lint
  bullet, CP6's registry entry, this section's own revision-19 bullet
  above, and restated correctly in `TEST_RESULTS.md`. **Corrected further
  at revision 22** (`LOCAL_MODEL_PLAN_REVIEW` round 21, finding I5): the
  "6 are incidental `###` matches (e.g. `:4171`)" clause just quoted is
  itself false — `:4171` (`` ### `OPUS-R25-*` external review disposition
  (revision 16 → 17, `Status: REVISE`) ``) is a genuine `###`-level
  disposition-section heading, not an incidental match, exactly as this
  section's own revision-19 bullet above (also corrected at revision 22)
  now states. The corrected fact remains what motivates I3's resolution
  below and point 2's correction: 89 disposition-shaped headings exist
  across two heading levels, and no single heading pattern — "incidental"
  or otherwise — identifies "the" disposition section among them; (b) the
  self-referential
  §7/whole-document occurrence counts revision 19 added were already stale
  at the revision that stated them (the plan counts itself, so every
  revision that states a count falsifies it in the same edit) — resolved by
  dropping the count claim entirely rather than replacing it with a new
  count, at §2.4 point 3; (c) §7's own revision-18 bullet still asserted the
  retired "18/12/6" figure — corrected in place above, quoting the
  superseded wording and naming this round. **O1 (criterion 3 asked for the
  corpus-vocabulary fixture's pass/fail pair at all three sites; §2.4 point
  3 carries only a cross-reference to §6)**: declined, at the author's
  discretion per this finding's own Optional grading — §2.4 point 3 now
  states explicitly that §6 is this decision's fixture site of record and
  that §2.4 does not restate the pass/fail pair, so the cross-reference is
  not read as drift. **Missing tests**: for I1, the declaration-block
  occurrence fixture (added at §6, CP6's registry entry); for I2, the
  wholly-new-document disposition-section fixture (added at §6, CP6's
  registry entry); for I3, the heading-list equality fixture, both
  directions (added at §6, CP6's registry entry); for I4, none — the change
  is to CP1's own deliverable text, and I3's list-equality fixture plus the
  existing in-extent negative fixture already cover the lint side; for I5
  and O1, none — both are prose/measurement corrections. **Required
  acceptance criteria 1-7**: applied at §2.1's carry sentence, §2.4 point 3,
  §6's lifecycle-lint bullet, CP6's registry entry, and §7 as described
  above; the plan/registry/mapping are regenerated at `plan_revision: 20`
  (CP6's registry entry gains the declaration-block/carve-out/growth-rule
  correction and three new fixtures; CP1's registry entry gains the
  dropped-"verbatim" correction; no `checkpoint_ids` list, requirement
  wording, or ledger field changes) and a fresh local plan review is run
  against the new `review_content_id` before returning to manual-external
  review, per criterion 7's own instruction.
- **Revision 21 applies `LOCAL_MODEL_PLAN_REVIEW` round 20's `REVISE`
  feedback (four Important findings, one Optional finding) against
  revision 20 (reviewed `bundle_id:
  3bdfb574060f0cd1fe8aad937928b306b61648d52ed56ab9bdc290d31544572b`)
  together with a user-directed architectural correction, applied in the
  same revision.** No Blocking findings. Round 20 independently verified
  round 19's four Important findings, its Optional finding, and all seven
  of its required acceptance criteria as applied before looking for
  anything new (all confirmed applied), then found the next way the
  heading/prose-inference predicate failed to converge by measuring it
  against the actual bytes of the payload document it runs over. Round 20's
  own text named the pattern directly: §2.4 point 3 had been rewritten in
  six consecutive rounds (15-20), each round finding the next defect by
  reading the same paragraph against a slightly larger part of reality, and
  recommended stating only the invariants at the plan level and moving the
  concrete predicates, delimiters and extents into CP6's own implementation
  — convergence pass 7's own diagnosis (§2.6, unaffected by this revision).
  **The user's own architectural correction, delivered independently and
  scoped narrowly to this same design element (§2.4 point 3,
  `D-Review-Material-Lifecycle`, CP6's registry entry, and their direct
  dependents — CP1's carried subsection and REQ-9), reaches the identical
  conclusion by a different route**: lifecycle status is a semantic
  property an author decides, not a syntactic property inferable from
  headings or prose, so no further refinement of the heading/prose
  predicate could ever converge. Applied together, since round 20's own
  convergence recommendation and the user's correction are the same fix
  stated twice, from two independent directions.

  **I1 (the heading-list equality check fails immediately on
  `WORKFLOW_V2_PLAN.md`'s 25 pre-existing `###`-level `D-*` headings: as
  written, CP6 either ships red or pulls the entire pre-existing document
  into the marker check's own input)**, **I2 (the pattern set has a
  location inside one document only, leaving
  `IMPLEMENTATION_REVIEW_WORKFLOW.md`'s own marker check without any
  declared vocabulary)**, **I3 ("the document's own disposition section" is
  not identifiable in `WORKFLOW_V2_PLAN.md`, which carries 89 candidates —
  corrected from "83" at revision 22, `LOCAL_MODEL_PLAN_REVIEW` round 21,
  optional finding O1 — not one)**, and **I4 (both carve-outs are bounded only by
  "recognizable"/"recognizably-delimited," so each is an unbounded
  exemption)**: none of the four is patched in place. All four were defects
  in the heading/prose-inference mechanism's own predicates — a baseline
  for the equality check, a vocabulary source for the second document, a
  determinate disposition destination, a computed boundary for each
  carve-out. Revision 21 removes that mechanism entirely rather than
  extending it a seventh time, replacing it with explicit `CURRENT`/
  `HISTORICAL` lifecycle classification (§2.4 point 3, rewritten; §6's
  lifecycle-lint bullet, rewritten; CP6's registry entry, rewritten). Under
  explicit classification, each finding's underlying question is answered
  structurally rather than by a sharper predicate: I1's baseline problem
  does not arise, since the fail-closed default classifies all of
  `WORKFLOW_V2_PLAN.md`'s pre-existing content (25 pre-existing `D-*`
  sections included) `CURRENT` without needing a declared baseline set to
  measure growth against; I2's missing-vocabulary problem does not arise,
  since classification is per-unit and explicit, not read out of a
  document-level declared pattern set at all; I3 is resolved directly, not
  structurally — §2.1's carry sentence and CP1's registry entry now name
  the single, new, explicitly-`HISTORICAL`-classified disposition section
  CP1 must create, rather than relying on a heading-text match to find "the"
  disposition section among 89 (corrected from "83" at revision 22,
  `LOCAL_MODEL_PLAN_REVIEW` round 21, optional finding O1); I4's
  unbounded-exemption problem does not
  arise, since there is no carve-out to bound in the first place — a unit
  is either explicitly `CURRENT` or explicitly `HISTORICAL`, with no
  extent-and-exemption geometry for prose to be smuggled through. §2.4
  point 2 is also corrected in the same revision (round 20's own required
  correction, independent of I1-I4): "one clearly-marked section" is
  replaced with "one or more disposition sections, each explicitly
  classified `HISTORICAL`," since `WORKFLOW_V2_PLAN.md` provably carries
  many, not one.
  **O1 (the corrected heading figure reproduces, but its accompanying
  "incidental" characterization does not, since `:4171` is a genuine
  `###`-level disposition-section heading)**: moot. O1's finding concerned
  prose this revision deletes outright — the heading-count paragraph and
  its "incidental" characterization were part of the heading/prose-
  inference mechanism §2.4 point 3 no longer states at all, so there is
  nothing left to correct at the five sites O1 named; the underlying fact
  O1 surfaced (that `WORKFLOW_V2_PLAN.md` has disposition-shaped sections
  at both `##` and `###` levels, so no single heading pattern identifies
  "the" disposition section) is exactly what motivates I3's fix above and
  what point 2's correction states directly.
  **Corrected at revision 22** (`LOCAL_MODEL_PLAN_REVIEW` round 21, finding
  I5): "moot" was wrong. The refuted "incidental" characterization does not
  live only in the five normative sites this revision's own I1-I4 deleted —
  it also stands, uncorrected, at two further §7 sites this revision does
  not touch: this section's own revision-19 bullet's nested I5(a)
  correction, and this section's own revision-20 I5(a) restatement
  immediately above. §2.4 point 4 requires a disposition bullet found wrong
  to be corrected in place, not left standing because the surrounding
  design element it once supported was superseded for an unrelated reason;
  both sites are corrected in place above (this revision), quoting their
  own superseded wording and naming round 20 (which established the fact,
  reading `:4171` against the real payload) and round 21 (which found the
  two sites still asserting the refuted "incidental" reading and corrected
  them, per this same finding I5).
  **Missing tests**: the five fixtures round 20 required for I1/I2/I4 (a
  corrected fixture 3 plus a new pass case; one fixture for I2; two for I4)
  pinned predicates that no longer exist, so none is added in that form;
  in their place, CP6's registry entry and §6 now require the positive/
  negative/ambiguous fixture triple plus the corpus-regression run stated
  above, which is the fixture obligation the new design actually needs
  proved. For I3, no fixture is added — the fix is to CP1's own deliverable
  text (which disposition section it creates), mirroring how revision 20
  disposed of I4's identically-shaped carry-text fix.
  **Required acceptance criteria 1-8**: criteria 1 (I1's re-scoping), 2
  (I2's vocabulary source), 4 (I4's carve-out boundaries) and 5 (I1's
  fixture correction) are superseded, not applied in their literal form —
  each asked for the heading/prose-inference mechanism to be repaired, and
  this revision replaces that mechanism instead, per the user's own
  architectural correction and round 20's own convergence recommendation
  (criterion 7) read together. Criterion 3 (I3's determinate destination)
  is applied directly, at §2.1's carry sentence and CP1's registry entry.
  Criterion 6 (O1, optional) is moot, per O1's disposition above. Criterion
  7 (the convergence recommendation itself: state invariants at the plan
  level, move predicates/delimiters/extents into CP6's implementation,
  fixtures as the binding contract) is accepted and is, in substance, this
  entire revision. Criterion 8 (regenerate at the next `plan_revision`,
  regenerate the bundle, run a fresh local plan review before returning to
  manual-external review) is carried out below: the plan/registry/mapping
  are regenerated at `plan_revision: 21` (still 13 checkpoints, no
  `checkpoint_ids` list change; CP1's and CP6's registry entries and
  REQ-9's mapping description are the only text that changes) and a fresh
  local plan review is run against the new `review_content_id` before
  returning to manual-external review.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet, CP6's registry
  entry, §2.1's carry sentence, CP1's registry entry, and REQ-9 — the stuck
  design element the user's correction named and its direct dependents. The
  governing-version enumeration sweep (a separate CP6 check) is touched only
  to restate its allowlist boundary in the new classification's terms
  (an occurrence inside a section classified `HISTORICAL`, not inside a
  heading-matched "disposition section"), with its own predicate and
  allowlist otherwise unchanged. **Corrected at revision 22**
  (`LOCAL_MODEL_PLAN_REVIEW` round 21, finding I2): "otherwise unchanged"
  was false in effect, not merely in wording. Under heading-match,
  `WORKFLOW_V2_PLAN.md`'s 9 pre-existing disposition-titled sections
  carrying 24 quoted `"2.1"` occurrences sat inside the allowlist
  automatically, by heading text alone; under explicit classification they
  are exempt only if CP6 deliberately marks those sections `HISTORICAL` —
  new deliverable work the sweep's predicate did not previously require,
  not a consequence of "restating its allowlist boundary" in different
  words. §2.4 point 3's own regression-run carve-out and §6's/CP6's
  registry entry's matching correction (below) now state this basis
  explicitly: CP6 marks the specific pre-existing disposition-titled
  sections the sweep needs exempted as `HISTORICAL`, as a deliberate,
  diff-visible act of this checkpoint's own deliverable, per the same
  guarantee (v) carve-out that already permitted it — revision 21's own
  §2.4 point 3 and §6/CP6's registry entry disagreed about whether that
  carve-out existed at all, which this round's finding I2 resolves in
  favor of the carve-out (below). This sentence is retained, corrected, as
  the disposition-of-record for the sweep's own scope question, rather
  than superseded by a fresh bullet, per point 4.
  No other design decision — the two-stage
  review protocol (§2.1-§2.3), activation/reachability (§2.2), the
  finding-taxonomy circuit-breaker (§2.6), or the post-v2.3.1 backlog
  (§2.7, CP9-CP10) — is reopened.

- **Revision 22 applies `LOCAL_MODEL_PLAN_REVIEW` round 21's `REVISE`
  feedback (four Important findings, one Optional finding) against revision
  21 (reviewed `bundle_id:
  00b5c82744301a1e62df6cea657700360a3475f03cd75d9308c664f8485e18f6`).** No
  Blocking findings; no design decision reviewed in rounds 1-20 was
  reopened. Round 21 independently verified round 20's four Important
  findings, its Optional finding, and all eight of its required acceptance
  criteria as applied before looking for anything new (all confirmed
  applied — including that revision 21's redesign genuinely replaced the
  heading/prose-inference mechanism rather than patching it), then found
  the next four defects by executing revision 21's own explicit
  classification design against its own stated guarantees and against the
  real payload, exactly as round 20 diagnosed the prior mechanism's own
  predicates. The reviewer's own framing: the redesign itself is not
  reopened, and none of the four findings asks for a predicate, a
  delimiter, an extent, or a parser — each is a missing guarantee (I1), a
  contradiction between two statements of the same guarantee (I2), an
  invariant stated over the wrong subject (I3), or an undefined term (I4).

  **I1 (as specified, CP6's lint was vacuously satisfiable against points
  1-2's own substance: the five guarantees (i)-(v) are all classification
  well-formedness, and none is a condition a document can fail by writing
  provenance narrative in `CURRENT` design text, yet §2.1:752-753/:770-775
  justified CP1's carry precisely on the ground that such narrative would
  fail "CP6's lint")**: resolved by adding guarantee (vi) — a unit
  classified `CURRENT` never carries the inline "revision N corrected
  finding X"-shaped narrative point 1 forbids, checked and proved with a
  new narrative-location fixture — at §2.4 point 3's guarantee list, with
  the matching fixture requirement, and restated at §6's lifecycle-lint
  bullet and CP6's registry entry. Resolved at the invariant level: the
  concrete textual shape the check treats as forbidden narrative remains
  CP6 implementation's own decision, exactly as the marker's own
  representation already was, proved by the fixture rather than specified
  in this plan's prose — so this fix does not reintroduce the
  heading/prose-*inference* mechanism revision 21 removed (classification
  itself stays wholly explicit and marker-driven; guarantee (vi) is a
  narrower, bounded content check over material *already* classified
  `CURRENT` by that explicit marker, structurally distinct from inferring
  the classification itself from prose).
  **I2 (§2.4 point 3's own regression-run carve-out — "except where CP6 has
  deliberately marked it so" — contradicted §6's and CP6's registry entry's
  stricter "since none of it carries an explicit marker yet, the fail-closed
  default must classify all of it `CURRENT`" wording, with no carve-out; the
  governing-version enumeration sweep's own allowlist basis for 9
  pre-existing disposition-titled sections carrying 24 quoted `"2.1"`
  occurrences depends on which of the two governs, and §7's own revision-21
  "otherwise unchanged" claim assumed the answer without stating it)**:
  resolved in favor of the carve-out already present at §2.4 point 3 —
  CP6 marks the specific pre-existing disposition-titled sections the sweep
  needs exempted as `HISTORICAL`, as a deliberate, diff-visible act of this
  checkpoint's own deliverable, never a silent or automatic reclassification
  — restated identically at §2.4 point 3's fixture-requirement paragraph,
  §6's lifecycle-lint bullet, and CP6's registry entry, and the revision-21
  "Scope discipline" paragraph above is corrected in place per point 4 to
  state this explicitly rather than assert "otherwise unchanged" without
  support.
  **I3 (the invariants were stated over *units*, while the property that
  matters — the fail-closed safety guarantee — is over *material*; the
  merge direction, redrawing a unit boundary so `CURRENT` material joins an
  adjacent `HISTORICAL`-marked unit with no marker edit anywhere in the
  diff, was left open by "a unit's classification" phrasing)**: resolved by
  restating the transition bullet and guarantee (iv) over material rather
  than units — no edit that does not itself change a marker may move any
  material from `CURRENT` to `HISTORICAL`, whether by changing a marker's
  value or by changing which unit that material belongs to — with unit
  boundaries themselves stated as part of what the marker governs, at §2.4
  point 3's transition bullet and guarantee list, plus a new
  boundary-redrawing fixture requirement, restated at §6 and CP6's registry
  entry. The representation of units and markers stays CP6's, unchanged.
  **I4 ("review-visible surface" occurred four times across §2.4 point 3
  and §6/CP6's registry entry with no definition and no stated consumer,
  leaving both required fixtures without a determinate assertion — in
  particular leaving open whether the term meant an exclusion from
  `review_content_id`, a real identity/migration consequence §5's own
  "Review-scalability branches... change no runtime state-machine
  behavior" bullet does not state)**: resolved
  by defining the term once, at §2.4 point 3, immediately before the
  guarantee list — it names only the check's own computed `CURRENT`/
  `HISTORICAL` partition, excluding nothing from `review_content_id`,
  `<bundle_dir>/PLAN.md`, the bundle's `files/`, or a reviewer's actual
  reading list, since this milestone adds no such consumer — and the
  positive/negative fixtures already required are restated against that
  definition, unchanged in substance.
  **I5 (round 20's own "incidental"/"merely contain the word 'disposition'"
  characterization of the 6 `###`-level matches — refuted by `:4171`'s own
  content, a genuine `###`-level disposition-section heading — survived
  uncorrected at two §7 sites even after revision 21 correctly disposed of
  O1 as "moot"; §2.4 point 4 requires a refuted disposition bullet corrected
  in place, not left standing because its surrounding design element was
  superseded for an unrelated reason)**: both sites — this section's own
  revision-19 bullet's nested I5(a) correction, and this section's own
  revision-20 I5(a) restatement — are corrected in place above, quoting
  their own superseded wording and naming round 20 (which established the
  fact) and round 21 (which found the two sites still asserting it and
  corrected them). Revision 21's own O1 disposition ("moot") is likewise
  corrected in place above, per the same finding.
  **O1 (the "83" figure used at five sites — §2.1:766, §2.4 point 2, and
  this section's own revision-21 bullet at two sites, plus CP1's registry
  entry — is the `##`-level-only subset of the 89 total
  `^#+ .*[Dd]isposition` matches; since I5's evidence shows at least one of
  the 6 `###`-level matches is itself genuine, 89 is the count every one of
  those sites is actually using ("many, not one"); separately,
  `TEST_RESULTS.md`'s own `^##.*[Dd]isposition` returns 89, not the 83 it
  claims, since `^##` also matches `###`)**: accepted — every "83" site
  above is corrected to "89", each noting the correction and its own round
  21/finding-O1 provenance; `TEST_RESULTS.md`'s regex/number pairing is
  restated correctly below, since it is a bundle file regenerated with this
  revision.
  **Missing tests**: for I1, the narrative-location fixture (added at §2.4
  point 3, §6, CP6's registry entry); for I2, none beyond the fixtures
  already required — the fix restates an existing carve-out consistently
  rather than adding a new mechanism; for I3, the boundary-redrawing
  fixture (added at the same three sites); for I4, none — the fix defines a
  term against fixtures already required; for I5 and O1, none — both are
  prose/measurement corrections, no behavioral or code change is made.
  **Required acceptance criteria 1-8**: applied at §2.4 point 3 (criteria 1
  I1, 3 I3, 4 I4), §6's lifecycle-lint bullet and CP6's registry entry
  (criteria 1-4 restated identically), §7's revision-21 "Scope discipline"
  paragraph (criterion 2, I2, corrected in place), §7's revision-19 and
  revision-20 bullets and revision-21's own O1 disposition (criterion 5,
  I5, corrected in place), and five "83" sites (criterion 7, O1, corrected
  to "89"); the plan/registry/mapping are regenerated at `plan_revision: 22`
  (still 13 checkpoints, no `checkpoint_ids` list change; CP1's and CP6's
  registry entries and REQ-9's mapping description are the only text that
  changes) and a fresh local plan review is run against the new
  `review_content_id` before returning to manual-external review, per
  criterion 8's own instruction.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet, CP6's registry
  entry, this section's own revision-19/-20/-21 bullets (in-place
  corrections only, per point 4), §2.1:766, and CP1's registry entry — the
  same stuck design element and its direct dependents, plus the two
  measurement corrections (I5, O1) point 4 requires be made where the
  refuted text stands. No other design decision is reopened.

- **Revision 23 applies `LOCAL_MODEL_PLAN_REVIEW` round 22's `REVISE`
  feedback (three Important findings, two Optional findings, one Usability
  concern) against revision 22 (reviewed `bundle_id:
  fd3bba2a5a644733b99d9a3d4b7d0370c61fdca7dd0eda81b50bc1bdda4ebd52`).** No
  Blocking findings; no design decision reviewed in rounds 1-21 was
  reopened. Round 22 independently verified round 21's four Important
  findings, its Optional finding, and all eight of its required acceptance
  criteria as applied before looking for anything new (all confirmed
  applied), then found the next three defects by measuring revision 22's
  own explicit-classification design, guarantee by guarantee, against the
  real 35,008-line `WORKFLOW_V2_PLAN.md` corpus. The reviewer's own framing:
  the redesign is not reopened, and none of the three findings asks for a
  regex, a delimiter, an extent, or a parser grammar — all three trace to
  one omission, that revision 22 added guarantees, a carve-out and a
  fixture to the design without ever stating the check's *subject scope*
  over the pre-existing corpus in one place, so each guarantee's corpus
  consequence had to be worked out per-guarantee, inconsistently.

  **I1 (the check's subject scope over pre-existing `WORKFLOW_V2_PLAN.md`
  content was stated three incompatible ways — the whole document at §2.4's
  own binding sentence, "new sections" at §6, and pre-existing content
  evaluated at guarantee (v) — under the first of which guarantee (vi) is
  unsatisfiable: 22 of the corpus's 25 pre-existing `### D-*` current-design
  sections already carry the narrative guarantee (vi) forbids, 15 of them in
  the heading itself)**: resolved by stating the convention's subject scope
  once, immediately before the guarantee list at §2.4 point 3 — guarantee
  (vi) is asserted only over units this milestone authors or explicitly
  marks, never over `WORKFLOW_V2_PLAN.md`'s pre-existing unmarked sections;
  the corpus regression asserts a different, narrower property (guarantee
  (v)'s own classification partition), never guarantee (vi) — and restating
  §2.4's binding sentence and §6's "new sections" phrasing to agree on this
  same scope. A new scope fixture (an unmarked pre-existing section
  carrying the forbidden narrative must pass) proves the boundary. Resolved
  at the invariant level: the guarantee's own textual shape (still CP6's)
  is untouched; only its subject is now stated.
  **I2 (guarantee (v)'s own "this milestone is never required to
  retroactively annotate the existing document for it to remain valid"
  and §6's sweep-driven "CP6 marks each one HISTORICAL as a deliberate...
  act of this checkpoint's own deliverable" stated opposite facts about the
  same document, with the "for it to remain valid" qualifier silently
  narrowing the first sentence's claim to the lifecycle check's own
  validity)**: resolved by restating guarantee (v) so its scope is explicit
  — no pre-existing unit needs a marker for the lifecycle check itself to
  be valid, which is a distinct fact from the sweep's own separate,
  deliberate, enumerated marking obligation on `WORKFLOW_V2_PLAN.md` — and
  by correcting the "additive and opt-in per document" parenthetical, which
  is no longer true of this one document (it stays additive/opt-in for
  every other document this milestone touches).
  **I3 (the carve-out's bound was a hand-measured proxy — "9 pre-existing
  disposition-titled sections carrying a quoted `"2.1"`-only occurrence, 24
  occurrences total" — rather than the sweep's own two detection forms; at
  least two of the 24 counted occurrences, `:3392` and `:3838`, are field-
  value references and transition statements, not occurrences of either
  form)**: resolved by rebinding the carve-out to the sweep's own flagged
  output, computed at CP6 implementation time, at §2.4 point 3's fixture
  paragraph, §6's lifecycle-lint and sweep bullets, and CP6's registry
  entry alike; the 9-section/24-occurrence figure is retained everywhere
  only as a proxy-measured indication of scale, never as the set CP6 marks.
  A new carve-out-bound fixture (a pre-existing disposition-titled section
  containing only sweep-unflagged occurrences must not be marked
  `HISTORICAL`, and the corpus regression must fail if it is) proves the
  direction round 20's own finding I4 already rejected an author-bounded
  exemption for.
  **O1 (the "9 sections/24 occurrences" figure is extent-rule-dependent —
  9/24 under next-heading-of-any-level, 10/26 under next-heading-of-
  same-or-higher-level — and the lifecycle corpus regression's own subject,
  "the real, existing `docs/ai-workflow/WORKFLOW_V2_PLAN.md`", is
  ambiguous between the tracked working-tree file and the built release
  payload, which differ in line count today only because of this plan's own
  uncommitted self-hosting update)**: the extent-rule half is moot under
  I3's resolution, since the carve-out no longer names a fixed count at
  all; the corpus half is resolved by naming the lifecycle regression's
  corpus explicitly as the built `distribution/workflow/2.5.0/` payload's
  own `WORKFLOW_V2_PLAN.md`, the same corpus the governing-version sweep
  already runs against and for the same reason, at §2.4 point 3, §6's
  lifecycle-lint bullet, CP6's registry entry, and REQ-9's mapping
  description.
  **O2 (REQ-9's mapping row stated the narrative-content check as "checked
  independently of the classification marker itself", the opposite
  dependency direction from §2.4 point 3's own guarantee (vi), which is
  defined over material *already* classified `CURRENT` by that marker)**:
  corrected to "checked over material the marker has already classified
  `CURRENT`, independently of the prose the marker classifies", in both the
  mapping and §4's row.
  **Usability (CP6's catch-all — "fixes, in place, any further site its own
  lint output flags... rather than leaving the lint red" — had no stated
  remedy shape for a site inside a pre-existing disposition section the
  enumerated carve-out missed, which O1's extent measurement shows is a
  live possibility and I3 shows the enumeration cannot be exact by
  construction; its default remedy, a reword, is exactly the harm
  `D-Review-Material-Lifecycle` exists to prevent)**: resolved by one
  sentence at §2.1's catch-all paragraph and at CP6's registry entry's own
  catch-all clause — inside a pre-existing disposition section, the
  catch-all's remedy is a `HISTORICAL` marker, never a reword; reword only
  current material.
  **Missing tests**: for I1, the scope fixture (added at §2.4 point 3, §6,
  CP6's registry entry); for I2, none beyond the fixtures already required
  — the fix restates guarantee (v)'s own scope, adding no new mechanism;
  for I3, the carve-out-bound fixture (added at the same three sites, and
  round 21's own outstanding missing test 4 is thereby discharged); round
  21's own outstanding missing test 1 (the two-version transition fixture
  for guarantee (iv)) is also added at the same three sites, since I4's
  round-21 acceptance criterion 6 remained open for it through revision 22;
  for O1 and O2, none — both are prose/measurement corrections, no
  behavioral or code change is made; for the usability finding, none — the
  fix restates the catch-all's own remedy in prose.
  **Required acceptance criteria 1-8**: applied at §2.4 point 3 (criteria 1
  I1, 2 I2, 3 I3), §6's lifecycle-lint bullet and CP6's registry entry
  (criteria 1-4 restated identically), §2.4 point 3 and §6's sweep bullet
  (criterion 5, O1, corpus named explicitly), REQ-9's mapping row (criterion
  6, O2, corrected), §2.1's catch-all paragraph and CP6's registry entry
  (criterion 7, usability, corrected); the plan/registry/mapping are
  regenerated at `plan_revision: 23` (still 13 checkpoints, no
  `checkpoint_ids` list change; §2.4 point 3, §6's lifecycle-lint and sweep
  bullets, CP6's registry entry, and REQ-9's mapping description are the
  only text that changes, plus this section's own new entry — **this
  enumeration itself corrected at revision 24**, `LOCAL_MODEL_PLAN_REVIEW`
  round 23, optional finding O1: it omitted §2.1's catch-all paragraph and
  §4's REQ-9 row, both of which this same entry's criterion-7 sentence
  above and "Scope discipline" paragraph below already list as touched)
  and a fresh
  local plan review is run against the new `review_content_id` before
  returning to manual-external review, per criterion 8's own instruction.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet and sweep
  bullet, §2.1's catch-all paragraph, CP6's registry entry, and REQ-9's
  mapping row/§4's row — the same stuck design element and its direct
  dependents. No other design decision — the two-stage review protocol
  (§2.1-§2.3), activation/reachability (§2.2), the finding-taxonomy
  circuit-breaker (§2.6), or the post-v2.3.1 backlog (§2.7, CP9-CP10) — is
  reopened.

- **Revision 24 applies `LOCAL_MODEL_PLAN_REVIEW` round 23's `REVISE`
  feedback (three Important findings, three Optional findings) against
  revision 23 (reviewed `bundle_id:
  56df2145864dcc7bc161c3c20ff626bdb6d30007cbfc703ed22ddbeacf1eefff`).** No
  Blocking findings; no design decision reviewed in rounds 1-22 was
  reopened. Round 23 independently verified round 22's three Important
  findings, its two Optional findings, all eight of its required acceptance
  criteria and its usability finding as applied before looking for anything
  new (all confirmed applied), then found two findings one level down from
  round 22's own: revision 23 stated guarantee (vi)'s subject scope and the
  carve-out's bound correctly in substance, but as facts about the world
  (who authored a unit; what a built release contains) rather than as facts
  the check can read at the moment it runs, plus one apparatus defect left
  standing at the one site criterion 3 did not reach.

  **I1 (guarantee (vi)'s subject scope was defined by authorship — "units
  this milestone itself authors or explicitly marks" — which the check
  cannot read; composed with guarantees (ii)/(iii) and the separability
  guarantee, the scope fixture and the narrative-location fixture described
  the same unmarked input while demanding opposite verdicts)**: resolved by
  stating the scope's mechanical basis once, beside the subject-scope
  statement at §2.4 point 3: guarantee (vi) applies to a unit exactly when
  it carries an explicit `CURRENT` marker; a unit `CURRENT` only by the
  fail-closed default (no marker at all) is outside its reach. This is a
  property of the marker alone, so it costs nothing against guarantees
  (ii)/(iii) or separability, and both fixtures now cite the same
  discriminator instead of an authorship fact the check cannot evaluate.
  Restated identically at §6's lifecycle-lint bullet and mirrored at CP6's
  registry entry.
  **I2 (the corpus regression's subject and the carve-out's bound were both
  rebound, at revision 23, to the built `distribution/workflow/2.5.0/`
  payload — a tree CP11 builds only after CP6, and therefore does not exist
  while CP6's own blocking fixture and carve-out computation would need to
  run against it)**: resolved by separating the two runs explicitly. CP6's
  own corpus regression and its own computation of the sweep's flagged set
  run against
  `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
  directly — a file CP1 and CP6 both author, so it exists when CP6 runs.
  The assertion over the fully built `distribution/workflow/2.5.0/` payload
  is CP11's own `--check` obligation and CP13's `tests/run_all.py`
  per-release-suite obligation instead — the same corpus, asserted a second
  time once it exists, never a different one, since `build_release.py
  --check` reproduces the overlay's full-replacement file verbatim by
  construction. Applied at §2.4 point 3, §6's lifecycle-lint and sweep
  bullets, CP6's registry entry, and REQ-9's mapping description.
  **I3 (guarantee (v)'s own clause was the fourth site of round 22's own
  criterion 3 and was left uncorrected: it still called the marking
  obligation "enumerated" twice, still stated the retired "9-or-so
  sections" count as the obligation's own extent, and pointed the carve-out
  cross-reference at guarantee (vi) rather than at this guarantee's own
  partition carve-out — the same guarantee-conflation shape as round 22's
  own O2, one revision later)**: resolved by correcting all three defects
  in that one clause: "enumerated" is dropped for the flagged-output
  wording criterion 3 already applies elsewhere, the count is dropped as
  the obligation's own extent (retained only, labelled, at §6's sweep
  bullet), and the cross-reference is repointed at guarantee (v)'s own
  partition carve-out.
  **O1 (§7's own revision-23 "only text that changes" enumeration omitted
  §2.1's catch-all paragraph and §4's REQ-9 row, contradicting its own
  criterion-7 sentence one line above and its own "Scope discipline"
  paragraph one line below, both of which already listed both)**: resolved
  by completing that enumeration in place, quoting the omission and naming
  this round's finding, per `D-Review-Material-Lifecycle` point 4's own
  disposition-correction convention.
  **O2 ("the real payload" in §6's sweep bullet and CP6's registry entry no
  longer named a determinate file once the lifecycle corpus regression's
  own subject, two paragraphs up, was renamed to a different tree)**:
  resolved by naming it explicitly as the `2.4.0` payload the 9/24 figure
  was actually measured against, at both sites.
  **O3 (§2.4's own pilot carve-out enumeration — itself located at §2.4,
  point 3's own binding sentence — still named §2.1/§2.2 only, for the third
  consecutive round, though §2.4's own points 2 and 3 have carried the same
  inline disposition narrative since revision 21)**: resolved by adding §2.4
  to that enumeration. **Location corrected at revision 25**,
  `LOCAL_MODEL_PLAN_REVIEW` round 24, optional finding O2: this entry, and
  `REVIEW_REQUEST.md`'s own disposition list, both wrote "§2.4's own pilot
  carve-out enumeration at §2.2", but the enumeration is at §2.4 itself
  (`:1820`, inside §2.4's own `:1749`-`:2178` span); "pilot" occurs nowhere
  in §2.2. The edit the sentence describes was correct and at the right
  place; only the location label was wrong.
  **Missing tests**: none for any finding this round — I1 and I2 both
  correct a stated scope/bound to be mechanically evaluable without
  changing which fixtures are required (the scope, narrative-location and
  carve-out-bound fixtures already required at revision 23 remain the
  complete required set, now with well-defined, non-contradictory
  discriminators); I3, O1, O2 and O3 are prose corrections with no
  behavioral component.
  **Required acceptance criteria 1-6**: applied at §2.4 point 3 (criteria 1
  I1, 2 I2, 3 I3), §6's lifecycle-lint and sweep bullets and CP6's registry
  entry (criteria 1-3 restated identically), REQ-9's mapping description
  (criterion 2), §7's own revision-23 entry (criterion 4, O1), §6's sweep
  bullet and CP6's registry entry (criterion 5, O2), and §2.4's pilot
  carve-out enumeration (criterion 6, O3); the plan/registry/mapping are
  regenerated at `plan_revision: 24` (still 13 checkpoints, no
  `checkpoint_ids` list change; §2.4 point 3, §6's lifecycle-lint and sweep
  bullets, CP6's registry entry, REQ-9's mapping description, §7's
  revision-23 entry, §2.4's pilot carve-out enumeration, and §4's REQ-9 row
  are the only
  text that changes, plus this section's own new entry — **corrected at
  revision 25**, `LOCAL_MODEL_PLAN_REVIEW` round 24, optional finding O1:
  this enumeration, like round 23's own before it, omitted "§4's REQ-9 row"
  even though this same entry's criterion-7 sentence above and "Scope
  discipline" paragraph below both already list it) and a fresh local
  plan review is run against the new `review_content_id` before returning
  to manual-external review, per the reviewer's own required criterion 8.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet and sweep
  bullet, CP6's registry entry, REQ-9's mapping row/§4's row, §7's own
  revision-23 disposition entry, and §2.4's pilot carve-out enumeration —
  the same stuck design element, its direct dependents, and this section's
  own bookkeeping. No other design decision — the two-stage review protocol
  (§2.1-§2.3), activation/reachability (§2.2), the finding-taxonomy
  circuit-breaker (§2.6), or the post-v2.3.1 backlog (§2.7, CP9-CP10) — is
  reopened.

- **Revision 25 applies `LOCAL_MODEL_PLAN_REVIEW` round 24's `REVISE`
  feedback (two Important findings, two Optional findings) against revision
  24 (reviewed `bundle_id:
  ee87261fc8eb9eac589abdf6d24a454b1360026a43557976c7d47bfa8931f2aa`).** No
  Blocking findings; no design decision reviewed in rounds 1-23 was
  reopened. Round 24 independently verified round 23's six required
  acceptance criteria and its usability finding as applied before looking
  for anything new (all confirmed applied), then found two findings one
  level down from round 23's own: revision 24 stated guarantee (vi)'s
  mechanical scope correctly, but left unstated *what obligates a unit to
  carry a marker in the first place*, and separated the corpus regression's
  timing correctly while leaving its own reassignment of a "second"
  built-payload assertion to CP11/CP13 unimplemented at both checkpoints
  and in REQ-9's own `checkpoint_ids`.

  **I1 (guarantee (vi)'s reach is a property of the marker once written; it
  does not itself say which units must write one, and revision 24's own
  citation for that — "this milestone's own authored/marked units carry
  explicit markers by the first bullet above" — pointed at point 1's
  authoring convention, which is not one of the guarantees CP6 must prove,
  has no fixture pinning it, and is itself scoped by authorship, the exact
  kind of fact the check cannot read this section exists to eliminate)**:
  resolved by adding a new, separate, mechanically-evaluable marker-presence
  obligation — guarantee (vii) — orthogonal to guarantee (iii)'s
  classification default: the whole of `IMPLEMENTATION_REVIEW_WORKFLOW.md`
  (a document this milestone authors in full — subject is the whole
  document); and, for `WORKFLOW_V2_PLAN.md`, a unit present in
  `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
  and absent from
  `distribution/workflow/2.4.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
  (both trees on disk at CP6 time, the first by CP1's/CP6's own registry
  entries, the second already committed today at 35,008 lines). A unit in
  either scope carrying no marker is a lint failure, reported independently
  of and never disturbing guarantee (iii)'s own `CURRENT` classification
  verdict for the same unit. A new marker-presence fixture proves it,
  two-corpus-shaped for `WORKFLOW_V2_PLAN.md`, without disturbing the
  ambiguous fixture's own verdict. Applied at §2.4 point 3 (new sub-bullet
  and guarantee (vii)), §6's lifecycle-lint bullet, CP6's registry entry,
  and REQ-9's mapping description.
  **I2 (the built-payload assertion revision 24 reassigned to CP11 and CP13
  was carried by neither checkpoint's registry entry, by neither of §6's
  CP11/CP13 bullets, nor by REQ-9's `checkpoint_ids`, and the one concrete
  mechanism named for CP11, `build_release.py --check`, asserts
  byte-reproduction, not lifecycle classification)**: resolved by **resolution
  1**, the smaller of the two the reviewer offered and the one the plan's
  own justification sentence already argued: the "asserted a second time"
  framing and CP11's/CP13's attribution are dropped; CP6's single run over
  `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md` is
  the whole assertion, and `build_release.py --check`'s own byte-identity
  proof (CP11) is what transfers that same result to the built
  `distribution/workflow/2.5.0/` payload once it exists, since `--check`
  reproduces the overlay's full-replacement file verbatim by construction —
  nothing else asserts this corpus a second time, and neither CP11 nor CP13
  carries an obligation of its own toward it. Applied at all four prose
  sites the required criteria name: §2.4 point 3's guarantee (v) paragraph,
  §6's lifecycle-lint bullet, §6's sweep bullet (whose own "two distinct
  runs" framing is corrected to state plainly that CP6's carve-out
  computation uses the overlay tree and that the sweep's own, separately
  pre-existing CI-gating obligation — real, and unaffected by this finding
  — is unrelated to the lifecycle lint's corpus regression), and REQ-9's
  mapping description. REQ-9's `checkpoint_ids` needed no change under this
  resolution, since it never named CP11 or CP13 to begin with.
  **O1 (§7's own revision-24 "only text that changes" enumeration, like
  round 23's own before it, omitted "§4's REQ-9 row", contradicting this
  same entry's criterion-7 sentence and its own "Scope discipline"
  paragraph, both of which already listed it)**: resolved by completing that
  enumeration in place, quoting the omission and naming this round's
  finding, per `D-Review-Material-Lifecycle` point 4's own
  disposition-correction convention.
  **O2 (§7's revision-24 entry's own O3 bullet, and `REVIEW_REQUEST.md`'s
  matching disposition line, both located the pilot carve-out enumeration
  "at §2.2", where it does not exist — the enumeration is at §2.4 itself,
  `:1820`, inside §2.4's own `:1749`-`:2178` span; "pilot" occurs nowhere in
  §2.2)**: resolved by correcting both location labels to §2.4; the edits
  themselves were correct and at the right place.
  **Missing tests**: none beyond I1's own required marker-presence fixture,
  already counted above; I2, O1 and O2 are prose corrections (I2 deletes a
  claim rather than adding a mechanism) with no further behavioral
  component.
  **Required acceptance criteria 1-6**: applied at §2.4 point 3 (criteria 1
  and 2, I1), §6's lifecycle-lint bullet and CP6's registry entry (criteria
  1 and 2 restated identically), §2.4 point 3, §6's lifecycle-lint and sweep
  bullets and REQ-9's mapping description (criterion 3, I2, resolution 1),
  §7's own revision-24 entry (criteria 5 and 6, O1/O2); criterion 4 (the
  subject/mechanism/timing table) is discharged by this entry's own I1/I2
  paragraphs above stating, for guarantee (vii) and the corpus regression
  alike, what CP6 reads and when it can read it, rather than by a separate
  block, since both cells the reviewer's own three preceding rounds found
  empty are now filled at the same sites every other guarantee in §2.4
  point 3 already states its own subject/mechanism/timing at. **This
  discharge claim is false, corrected at revision 26** (`LOCAL_MODEL_PLAN_REVIEW`
  round 25, finding I1): criterion 4 named nine cells (guarantees (i)-(vi),
  the carve-out, and the corpus regression — subject, mechanism and timing
  each), of which the I1/I2 paragraphs above fill only two (guarantee (vii),
  the corpus regression); guarantees (i), (v) and (vii)'s own first subject
  are each missing a tree or a timing at the site that states the
  obligation, and guarantees (ii), (iii), (vi) and the carve-out state no
  timing anywhere — see revision 26's own entry below, which produces the
  table criterion 4 actually required. The
  plan/registry/mapping are regenerated at `plan_revision: 25` (still 13
  checkpoints, no `checkpoint_ids` list change, still 16 requirements;
  §2.4 point 3, §6's lifecycle-lint and sweep bullets, CP6's registry entry,
  REQ-9's mapping description **(and therefore §4's own REQ-9 row, per this
  section's standing note above — corrected at revision 26,
  `LOCAL_MODEL_PLAN_REVIEW` round 25, optional finding O1: this enumeration,
  like round 23's and round 24's own before it, omitted "§4's REQ-9 row")**,
  and §7's revision-24 entry are the only text
  that changes, plus this section's own new entry) and a fresh local plan
  review is run against the new `review_content_id` before returning to
  manual-external review, per the reviewer's own required criterion 8 (also
  restated as `LOCAL_MODEL_PLAN_REVIEW` round 24's own missing-tests item
  3/required criterion 7 in earlier rounds' numbering).
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet and sweep
  bullet, CP6's registry entry, REQ-9's mapping row/§4's row, and §7's own
  revision-24 disposition entry — the same stuck design element, its direct
  dependents, and this section's own bookkeeping. No other design decision —
  the two-stage review protocol (§2.1-§2.3), activation/reachability
  (§2.2), the finding-taxonomy circuit-breaker (§2.6), or the post-v2.3.1
  backlog (§2.7, CP9-CP10) — is reopened.

- **Revision 26 applies `LOCAL_MODEL_PLAN_REVIEW` round 25's `REVISE`
  feedback (three Important findings, two Optional findings) against
  revision 25 (reviewed `bundle_id:
  ac900b45b4b9121f3981b6ebd9ac4ee685861578db777e2e4600f4e52efec6a1`).** No
  Blocking findings; no design decision reviewed in rounds 1-24 was
  reopened. Round 25 independently verified round 24's seven required
  acceptance criteria as applied before looking for anything new (all
  confirmed applied), then found that revision 25's own claim to have
  discharged required criterion 4 by prose was false, that the wide first
  lint assertion round 24 left standing alongside the new guarantee (vii)
  was still unevaluable, and that guarantee (vii)'s own `WORKFLOW_V2_PLAN.md`
  subject — new this revision — had no stated basis for cross-corpus unit
  identity.

  **I1 (required criterion 4 asked for a subject/mechanism/timing table;
  revision 25's own §7 entry claimed this was discharged by its own I1/I2
  prose instead, which filled only two of the nine named cells, and whose
  premise — that every other guarantee already states its own
  subject/timing at §2.4 point 3 — was false for at least four of the
  remaining seven)**: resolved by producing the table, at §2.4 point 3,
  immediately after guarantee (vii) — the location required criterion 1
  named as one of two acceptable sites. Every guarantee, the carve-out and
  the corpus regression each get a row naming the tree CP6 reads and when
  it is readable; every row names a tree CP1 and/or CP6 authors directly,
  so nothing in the table waits on a later checkpoint. Revision 25's own §7
  entry is corrected in place, quoting the false discharge claim and naming
  this finding, per `D-Review-Material-Lifecycle` point 4's own
  disposition-correction convention.
  **I2 (§6's first lint assertion and CP6's registry entry's mirrored
  clause both still asserted, verbatim from revision 24, that "every unit
  the convention applies to" carries an explicit marker — an
  authorship-scoped, unevaluable subject standing beside guarantee (vii)'s
  new, narrower, evaluable marker-presence obligation, leaving two
  inconsistent statements of what the lint requires, with the wider one
  read first)**: resolved by narrowing that first assertion, at both sites,
  to state only the *manner* of classification — explicit marker, never
  inference from heading text, level or position — and no longer the
  *presence* obligation. Guarantee (vii) is now the lint's sole statement of
  which units must carry a marker at all. §2.4 point 3's own "Two explicit
  states" definitional bullet is unchanged, since it states the
  convention's definition rather than a listed lint assertion (the reviewer's
  own required criterion 2 names this bullet as the one exception).
  **I3 (guarantee (vii)'s `WORKFLOW_V2_PLAN.md` subject — "present in the
  overlay and absent from the base" — had no stated basis for deciding unit
  identity across the two corpora; unit boundaries are themselves
  marker-governed, per point 3's own transition bullet, so neither corpus's
  units carry a marker that could establish "the same unit in both
  corpora", and the required two-corpus fixture was therefore not
  constructible)**: resolved by **resolution 1**, the cheapest of the three
  the reviewer offered: `WORKFLOW_V2_PLAN.md`'s half of guarantee (vii) is
  rescoped to the overlay's own new top-level design sections that CP1's
  registry entry already names and creates — `D-Implementation-Review-Stages`,
  `D-Implementation-Review-Version-Activation`, and the carried
  `2.5.0`-scoped disposition-record subsection — each in full, rather than a
  diffed set. CP1's own registry entry is what establishes that each
  section exists at all, so no cross-corpus identity rule is needed: a unit
  is in scope exactly when it sits inside one of the three named sections,
  a property readable off the one tree the obligation now names. The
  required fixture is correspondingly restated as one-corpus-shaped: a
  fixture unit inside one of the three sections, unmarked, must fail; a
  fixture unit elsewhere in the same fixture document, unmarked, must pass.
  Applied at §2.4 point 3 (the obligation's own subject bullet, guarantee
  (vii)'s statement, and the marker-presence fixture), §6's lifecycle-lint
  bullet (guarantee (vii) bullet and its own fixture), and CP6's registry
  entry (the marker-presence obligation and its fixture).
  **O1 (§7's own revision-25 "only text that changes" enumeration, like
  round 23's and round 24's own before it, omitted "§4's REQ-9 row",
  contradicting this same entry's own criterion-7 sentence and "Scope
  discipline" paragraph, both of which already listed it)**: resolved by
  completing that enumeration in place, quoting the omission and naming
  this round's finding, per `D-Review-Material-Lifecycle` point 4's own
  disposition-correction convention, and by adding a standing note at the
  top of §7 stating once that a change to a requirement's mapping
  description always implies §4's own row, so this omission cannot recur
  silently at the next entry (the reviewer's own suggested remedy).
  **O2 (guarantee (v)'s own corpus clause still described a corpus state —
  "`WORKFLOW_V2_PLAN.md`'s own existing, already-committed content today" —
  that the regression proving it does not use, and that does not exist:
  the regression runs against the `2.5.0` overlay payload, which `migration/overlays/`
  does not yet contain)**: resolved by naming the overlay payload tree
  explicitly in guarantee (v)'s own clause, the same tree the regression two
  paragraphs below already runs against, at §2.4 point 3.
  **Missing tests**: none beyond I3's own required fixture restatement,
  already counted above; I1 adds a table, not a fixture; I2 narrows a prose
  assertion, adding no new mechanism; O1 and O2 are prose corrections with
  no behavioral component.
  **Required acceptance criteria 1-7**: applied at §2.4 point 3 (criteria 1
  I1, 2 I2, 3 I3, 4 I3's fixture), §6's lifecycle-lint bullet and CP6's
  registry entry (criteria 2 and 3 restated identically), §7's own
  revision-25 entry (criteria 5 and 6, O1/O2); the plan/registry/mapping are
  regenerated at `plan_revision: 26` (still 13 checkpoints, no
  `checkpoint_ids` list change, still 16 requirements; §2.4 point 3, §6's
  lifecycle-lint bullet, CP6's registry entry, REQ-9's mapping description
  (and therefore §4's own REQ-9 row, per §7's own standing note above), and
  §7's revision-25 entry are the only text that changes, plus this
  section's own new entry) and a fresh local plan review is run against the
  new `review_content_id` before returning to manual-external review, per
  the reviewer's own required criterion 7.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet, CP6's registry
  entry, REQ-9's mapping row/§4's row, §7's own standing note and its
  revision-25 disposition entry — the same stuck design element, its direct
  dependents, and this section's own bookkeeping. No other design decision —
  the two-stage review protocol (§2.1-§2.3), activation/reachability
  (§2.2), the finding-taxonomy circuit-breaker (§2.6), or the post-v2.3.1
  backlog (§2.7, CP9-CP10) — is reopened.

- **Revision 27 applies `LOCAL_MODEL_PLAN_REVIEW` round 26's `REVISE`
  feedback (three Important findings, three Optional findings) against
  revision 26 (reviewed `bundle_id:
  4a0655e8b48d8e9feefe3e807e22efd5a7b459cff64ae9fe3d75bf78602b05b3`).** No
  Blocking findings; no design decision reviewed in rounds 1-25 was
  reopened. Round 26 independently re-verified round 25's seven required
  acceptance criteria as applied before looking for anything new (all
  confirmed applied), then found that the revision-26 subject/mechanism/
  timing table the reviewer's own round 25 required contradicted, in three
  of its own rows and in the corpus-regression row, guarantees the same
  table was supposed to summarize, and that guarantee (vii)'s two subjects
  arrive with no checkpoint ever assigned to write the markers the lint
  then requires on them.

  **I1 (the table's rows (i)-(iii) named guarantee (vii)'s own narrower
  marker-presence domain as the classification predicate's domain,
  contradicting guarantee (v)'s whole-corpus fail-closed verdict, the scope
  fixture and the carve-out row of the same table; §6's own opening scope
  sentence had the same shape, scoping the fail-closed default — never its
  own subject — to the same narrower domain)**: resolved by correcting row
  (i) to name the classification predicate's real domain — every unit of
  both documents the convention names, `WORKFLOW_V2_PLAN.md`'s pre-existing
  sections included — with rows (ii) and (iii) inheriting the corrected
  domain by their own existing "same units as (i)" cross-reference, and by
  adding one sentence after the table distinguishing that domain from
  guarantee (vi)'s marker-scoped reach and guarantee (vii)'s marker-presence
  scope. §6's opening sentence is corrected in the same revision to state
  that its narrower scope belongs only to the narrative-content assertion,
  never to the fail-closed default or the other lint assertions stated
  alongside it.
  **I2 (guarantee (vii) obliges `IMPLEMENTATION_REVIEW_WORKFLOW.md` and
  `WORKFLOW_V2_PLAN.md`'s three enumerated sections to carry explicit
  markers; CP1 authors both subjects; the only marker-writing acts the plan
  assigned any checkpoint were CP1's own disposition subsection and CP6's
  sweep-flagged carve-out marking, neither of which covers guarantee (vii)'s
  subjects)** — **this premise was itself false, corrected at revision 28**
  (round 27's own required acceptance criterion 2): CP1's disposition-subsection
  marking *is* one of guarantee (vii)'s three then-named subjects (§2.4
  point 3's own enumeration at the time), so it already covered one of the
  three; the actual, narrower gap was only over the two `D-*` sections
  themselves. Revision 27's fix, below, missed this and directed CP6 to
  overwrite CP1's disposition subsection's own `HISTORICAL` marker with
  `CURRENT` — this is round 26's own finding I2 resolution, restated here
  as this entry's fix sentence at the time: "CP6, having chosen the
  marker's own representation, writes the markers guarantee (vii) requires
  into `IMPLEMENTATION_REVIEW_WORKFLOW.md` and the three enumerated
  sections as part of its own deliverable, distinct from — and never
  bounded by — the sweep-flagged carve-out, since these are `CURRENT`
  markers on new material CP1 authored, never `HISTORICAL`
  reclassifications of pre-existing material." **Superseded at revision 29**
  (`LOCAL_MODEL_PLAN_REVIEW` round 28, finding I3: this entry had presented
  the sentence above as if it were round 27's own finding B1's resolution,
  when it is instead the very blanket instruction B1 condemned — producing
  round 27's own finding B1, not resolving it; the sentence survived in the
  assertive voice, the one remaining site of the "`CURRENT` markers on new
  material CP1 authored" derivation the revision-28 standing invariant
  above exists to retire; and the "Applied at §2.4 point 3's own
  lint-assertion bullet, §6's lifecycle-lint bullet and CP6's registry
  entry" claim this entry carried was false, since none of those three
  sites has carried this sentence since revision 28 (**"the claim below"
  retargeted to "the claim this entry carried" at revision 30**,
  `LOCAL_MODEL_PLAN_REVIEW` round 29, optional finding O3: revision 29's
  own edit dropped the "Applied at …" claim this parenthetical refers to,
  leaving nothing below for "below" to name)): round 27's own finding B1,
  below,
  states the actual resolution — CP6's marking pass writes `CURRENT` only
  on units that do not already carry an explicit marker of their own,
  regardless of value, so CP1's own `HISTORICAL` marker on its disposition
  subsection discharges guarantee (vii) for that unit without CP6 ever
  touching it. The three sites named above no longer carry the superseded
  sentence quoted here; see revision 28's own entry below for what they
  carry instead. **I2's own required
  test**: a real-corpus run of the finished marker-presence check over both
  of guarantee (vii)'s actual subjects is added to CP6's own completion
  requirement, at the same three sites, distinct from the guarantee (v)
  partition regression.
  **I3 (guarantee (v)'s own revision-26 parenthetical said the corpus
  regression proving this guarantee does not itself use the pre-marking
  state, then the clause it sat inside named exactly that state for a run
  the plan elsewhere called "CP6's single run"; the table copied the
  contradiction, naming the same tree and state for row (v) and the
  "Corpus regression" row alike)**: resolved by stating explicitly that CP6
  reads this one tree twice — pre-marking, for guarantee (v)'s own verdict,
  and post-marking, after CP6 has made its carve-out-bound markings, for the
  corpus regression and the carve-out-bound fixture, which must observe
  CP6's own markings to have anything to check the fixture against — and
  that "CP6's single run over this overlay-payload tree" means never a
  *second* run against the built `distribution/workflow/2.5.0/` payload,
  never "once, in total, across both this guarantee and the regression".
  Applied at guarantee (v), at the table's rows (v) and "Corpus regression",
  and at §6's lifecycle-lint bullet and CP6's registry entry, which restate
  the same two-state read.
  **O1 (table row (iv)'s mechanism cell stated only the marker-edit shape,
  omitting the boundary-redrawing shape guarantee (iv)'s own text and the
  boundary-redrawing fixture both include)**: resolved by extending the
  cell to name a redrawn unit boundary with no marker edit, alongside the
  marker-edit-across-a-diff shape already there.
  **O2 (REQ-9's description, and therefore §4's byte-identical row, still
  opened with the wide presence-shaped clause criterion 2 of round 25's
  feedback removed from §6 and CP6's registry entry, the requirement an
  implementer traces REQ-9 through being the one site the narrowing never
  reached)**: resolved by stating explicitly that the opening clause is the
  convention's own definitional statement of classification's two states
  and safe default — the definitional form criterion 2 already exempted,
  mirroring §2.4 point 3's own "Two explicit states" and "Fail-closed
  default" bullets — and that which units must carry a marker at all is the
  separate, narrower obligation stated later in the same description, never
  this opening clause.
  **O3 (CP1's registry entry names two `WORKFLOW_V2_PLAN.md` additions —
  the version-dependent `bundle_generation_target_phase` resolver and
  `build_rolled_back_config`'s own rollback-destination design text —
  without stating which of the two new `D-*` sections either lands in,
  leaving the three-section enumeration's exhaustiveness argued rather than
  checkable)**: resolved by adding one clause to CP1's registry entry
  naming both destinations explicitly — the resolver and its field-set
  constants inside `D-Implementation-Review-Stages`, and
  `build_rolled_back_config`'s own generalized-behavior design text inside
  `D-Implementation-Review-Version-Activation` — so the enumerable scope's
  exhaustiveness is a property an implementer can check directly against
  CP1's own deliverable, not one that has to be inferred.
  **Missing tests**: none beyond I2's own required test, already counted
  above; I1, I3 and O3 are prose/table corrections pinned by fixtures and
  regressions this plan already specifies; O1 and O2 are prose corrections
  with no behavioral component.
  **Required acceptance criteria 1-8**: applied at §2.4 point 3 (criteria 1
  I1, 2/3 I2, 4 I3, 5 O1, 6 O2), §6's lifecycle-lint bullet and CP6's
  registry entry (criteria 1-4 restated identically), CP1's registry entry
  (criterion 7, O3), and REQ-9's mapping description and therefore §4's own
  row (criterion 6, per §7's own standing note); the plan/registry/mapping
  are regenerated at `plan_revision: 27` (still 13 checkpoints, no
  `checkpoint_ids` list change, still 16 requirements; §2.4 point 3, §6's
  lifecycle-lint bullet, CP1's registry entry, CP6's registry entry, REQ-9's
  mapping description (and therefore §4's own REQ-9 row, per §7's own
  standing note above), and this section's own new entry are the only text
  that changes) and a fresh local plan review is run against the new
  `review_content_id` before returning to manual-external review, per the
  reviewer's own required criterion 8.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet, CP1's registry
  entry, CP6's registry entry, REQ-9's mapping row/§4's row, and this
  section's own new entry — the same stuck design element, its direct
  dependents, and this section's own bookkeeping. No other design decision —
  the two-stage review protocol (§2.1-§2.3), activation/reachability
  (§2.2), the finding-taxonomy circuit-breaker (§2.6), or the post-v2.3.1
  backlog (§2.7, CP9-CP10) — is reopened.
- **Revision 28 applies a user-directed architectural correction to
  guarantee (vii) together with `LOCAL_MODEL_PLAN_REVIEW` round 27's
  `REVISE` feedback (one Blocking finding, three Important findings, three
  Optional findings) against revision 27 (reviewed `bundle_id:
  9b899443a8844fcffcf2e4bf42b6364231b3a2b032f1a26da71a963f94241339`), the
  two applied together because the correction supersedes the
  authorship/novelty-derived approach round 27's own findings were
  critiquing.**

  **The correction, narrowly scoped to guarantee (vii)**: rounds 24-27 each
  found a defect of the same shape — a quantified statement deriving a
  marker's presence, scope, or value from an authorship or novelty property
  (who wrote a unit, whether it is new, which named section or milestone it
  belongs to) rather than from a mechanically-readable property of the
  corpus, which is exactly what §2.4 point 3 itself exists to eliminate.
  Revision 27's own fix reintroduced the same defect with the polarity
  reversed — "these are `CURRENT` markers on new material CP1 authored" —
  and directed CP6 to overwrite CP1's already-`HISTORICAL` disposition
  subsection, which round 27's own finding B1 caught directly. Rather than
  patch that single instance again, guarantee (vii) is narrowed to a pure
  presence obligation: it asserts only that an in-scope unit carries an
  explicit marker, never which value that marker holds, and its scope is
  widened from "the top-level design sections CP1's own registry entry
  adds" to "every top-level design section any checkpoint's own registry
  entry adds" (still enumerable by registry entry, never by cross-corpus
  diff), with a nested unit — CP1's carried disposition-record subsection
  the concrete case — reached once, through its container's "in full"
  reach, never re-enumerated as a separate, differently-valued peer. A
  standing invariant is stated once in §2.4 point 3 (added, optional finding
  O3/architecture note) as the mechanical test future prose in this section
  must pass: no statement in this convention derives a marker's presence,
  value, or scope from authorship, novelty, or a cross-corpus comparison.

  **B1 (revision 27's marking instruction directed CP6 to mark CP1's
  carried disposition-record subsection `CURRENT`, which §2.1, §2.4 point 2
  and CP1's own registry entry each require `HISTORICAL`, so guarantee
  (vii)'s two checkpoints were assigned opposite markers on the same unit
  and CP6's own deliverable would fail guarantee (vi))**: resolved by the
  correction above (round 27's own resolution 1, generalized): CP6's
  marking pass writes `CURRENT` only on units that do not already carry an
  explicit marker of their own, never overwriting an already-marked unit
  regardless of value; guarantee (vii) is stated explicitly as satisfied by
  an explicit marker of either value, so CP1's required `HISTORICAL` marker
  on its disposition subsection discharges the obligation for that unit
  without CP6 ever touching it. **B1's premise** (§7's own revision-27 I2
  entry incorrectly claimed neither existing marker-writing obligation
  covered guarantee (vii)'s subjects, when CP1's disposition-subsection
  marking already covered one of the three): corrected in place at that
  entry above. **B1's test**: an already-marked-nested-unit fixture is added
  to CP6's own completion requirement, at the same three sites as CP6's
  other fixtures (§2.4 point 3, §6, CP6's registry entry) — a unit already
  carrying an explicit `HISTORICAL` marker, nested inside another in-scope
  unit, must survive CP6's marking pass unchanged, be reported satisfied by
  presence alone, and not fail guarantee (vi).
  **I1 ("three enumerated new top-level design sections" was false for the
  third member — CP1's disposition subsection is nested inside
  `D-Implementation-Review-Stages`, not a top-level peer, so "each in full"
  made the scope self-overlapping)**: resolved by the correction's own
  drop of the separate three-item enumeration: the scope is now stated as
  every top-level section a registry entry adds, with a nested unit reached
  once through its container, never as an additional enumerated member —
  applied at guarantee (vii), §2.4 point 3, §6's lifecycle-lint bullet,
  CP6's registry entry and REQ-9/§4.
  **I2 (CP6's own `D-Review-Material-Lifecycle` section, new material this
  milestone adds to `WORKFLOW_V2_PLAN.md`, was outside guarantee (vii)'s
  scope because the scope was defined by "sections CP1's own registry entry
  adds" rather than by document region)**: resolved by widening the scope
  to "every top-level section any checkpoint's own registry entry adds" —
  the first of the correction's own two changes, applied at guarantee
  (vii), §2.4 point 3, §6's lifecycle-lint bullet, CP6's registry entry and
  REQ-9/§4. **I2's own required test 2**: the real-corpus marker-presence
  run is widened to cover `D-Review-Material-Lifecycle` itself, at the same
  sites as B1's test.
  **I3 (row (vii) was not given the table's own required two-state "When
  readable" treatment rows (v) and "Corpus regression" already carry, since
  with CP6 writing the markers itself the real-corpus run can only be
  evaluated post-marking)**: resolved by giving row (vii)'s cell the same
  two-state treatment — fixtures at CP6 time, independent of corpus timing;
  the real-corpus run at CP6 time but only after CP6's own marking pass.
  **O1 (the post-table summarizing sentence said rows (i)-(iv) "read" every
  unit of both documents, which row (iv)'s own fixture-only cell denies)**:
  resolved by restating it as a domain claim — the predicate's domain is
  every unit of both documents — rather than a "reads" claim.
  **O2 (REQ-9's description carried neither of revision 27's two new
  obligations — CP6 writing the markers, and the real-corpus
  marker-presence run — and still said "this single run is the whole
  assertion" without the two-state read added everywhere else)**: resolved
  by regenerating REQ-9's description (and therefore §4's byte-identical
  row) to state both obligations and the classification-partition
  regression's own post-marking timing explicitly.
  **O3 (the coupling of CP6 both choosing the marker's representation and
  writing the first markers was not itself the problem; the problem was the
  blanket quantifier over a scope containing a unit of the opposite class)**:
  confirmed by this revision's own resolution, which keeps CP6's assignment
  and fixes the quantifier rather than moving the marking obligation
  elsewhere.
  **Missing tests**: B1's own already-marked-nested-unit regression and
  I2's own widened real-corpus-run regression, both above; no other new
  tests — I1, I3, O1 and O2 are prose/table/description corrections pinned
  by fixtures and regressions this plan already specifies.
  **Required acceptance criteria 1-9**: applied at guarantee (vii), §2.4
  point 3 (including the standing invariant, criterion 9), §6's
  lifecycle-lint bullet, CP6's registry entry (criteria 1-6 restated
  identically), §7's own revision-27 entry (criterion 2), and REQ-9's
  mapping description and therefore §4's own row (criterion 8, per §7's own
  standing note); the plan/registry/mapping are regenerated at
  `plan_revision: 28` (still 13 checkpoints, no `checkpoint_ids` list
  change, still 16 requirements; guarantee (vii), §2.4 point 3, §6's
  lifecycle-lint bullet, CP6's registry entry, REQ-9's mapping description
  (and therefore §4's own REQ-9 row), and this section's own new entry are
  the only text that changes) and a fresh local plan review is run against
  the new `review_content_id` before returning to manual-external review,
  per required criterion 10.
  **Scope discipline.** This revision touches only guarantee (vii), §2.4
  point 3, `D-Review-Material-Lifecycle`, §6's lifecycle-lint bullet, CP6's
  registry entry, §7's own revision-27 entry (the false-premise correction
  only), REQ-9's mapping row/§4's row, and this section's own new entry —
  the same stuck design element, its direct dependents, and this section's
  own bookkeeping. No other design decision — the two-stage review protocol
  (§2.1-§2.3), activation/reachability (§2.2), the finding-taxonomy
  circuit-breaker (§2.6), or the post-v2.3.1 backlog (§2.7, CP9-CP10) — is
  reopened.
- **Revision 29 applies `LOCAL_MODEL_PLAN_REVIEW` round 28's `REVISE`
  feedback (one Blocking finding, three Important findings, two Optional
  findings, one structural note) against revision 28 (reviewed `bundle_id:
  1da9ad6b33816f2799579b3a926fb120ffedcca4c26856761ac2a20dd1d19467`).**

  **B1 (revision 28's resolution of round 27's B1 requires CP1 to write an
  explicit `HISTORICAL` marker in a representation the plan assigned CP6 to
  choose, and CP6 runs after CP1 in the registry's own checkpoint order, so
  the precondition the whole never-overwrite rule rests on could not be
  satisfied as the plan stood)**: resolved by taking resolution 1 of the
  three the reviewer offered — the marker-representation decision moves to
  CP1, fixed no later than CP1 writes its own required `HISTORICAL` marker
  (§2.1), while the lint, the parser and every guarantee stay with CP6.
  Applied at §2.1 (CP1's own deliverable), §2.4 point 3 (the separability
  bullet, the guarantees preamble, and the closing paragraph), §6 (the
  marking-pass bullet and the representation bullet), and CP1's and CP6's
  registry entries, which restate the same reassignment identically. No
  checkpoint reordering is needed: CP6 already depends on CP1 in the
  registry's own listed order, so fixing the representation at CP1 time
  narrows when the decision is made without adding a new dependency. **B1's
  test**: a representation-conformance fixture is added to CP6's own
  completion requirement, at the same three sites as CP6's other fixtures
  (§2.4 point 3's fixture bullet, §6's fixture list, CP6's registry entry,
  and REQ-9's own fixture enumeration) — CP1's own disposition-record
  subsection's `HISTORICAL` marker, written in the representation CP1
  fixes, must be recognized by CP6's own parser as an explicit marker
  rather than defaulted to `CURRENT`.
  **I1 (guarantee (v)'s subject and its "the moment before CP6 adds any
  marker to it" anchor are both falsified by CP1's own required
  deliverable, since CP1 writes the tree's first marker, not CP6)**:
  resolved by narrowing guarantee (v)'s own verdict to the tree's units
  carrying no explicit marker of their own, and restating the anchor as
  "the moment before CP6's own marking pass" — applied at guarantee (v)
  itself and the table's row (v); §6 and CP6's registry entry are
  unaffected in substance since both cross-reference guarantee (v) at §2.4
  point 3 rather than restating its text. CP1's own disposition-record
  subsection, already `HISTORICAL`-marked at that same moment, is now
  stated as outside this guarantee's own verdict rather than a silent
  counterexample to it, agreeing with the already-marked-nested-unit
  fixture's own premise instead of contradicting it. **I1's test**: "the
  narrowed assertion is itself the required regression, stated explicitly
  in guarantee (v)'s own text — an implementation that widens it back to
  `CURRENT` over the whole tree, CP1's marked subsection included, fails
  against the real corpus, since that subsection's own marker classifies it
  `HISTORICAL` — so a future edit cannot silently re-widen it." **Superseded
  at revision 30** (`LOCAL_MODEL_PLAN_REVIEW` round 29, finding B1: this
  claim named no run this plan requires to be green — the real-corpus state
  it depended on stops existing in the worktree once CP6 completes, so it
  pins nothing past CP6's own implementation time; revision 30's own entry
  below states the actual resolution — a durable pre-marking-partition
  fixture, not this real-corpus observation, pins guarantee (v)'s narrowed
  form).
  **I2 (the round-24 finding-I1 appeal to "this milestone's own
  authored/marked units carry explicit markers by the first bullet above"
  was still live at §2.4 point 3, the last unretired instance of the
  authorship-derived-presence class the revision-28 standing invariant
  declares closed)**: resolved by repointing the citation to guarantee
  (vii)'s own presence obligation, CP1's own marker-writing obligation
  (§2.1) and CP6's marking pass, dropping the appeal to point 1's
  normative-text convention entirely — applied at §2.4 point 3 only; the
  sibling sub-bullet that already calls the retired appeal "prior" needed
  no change, since it already describes that appeal as history.
  **I3 (§7's own revision-27 entry read as if round 27's B1 was "resolved
  by resolution 1" by the very blanket instruction B1 condemned, and its
  "Applied at …" claim named three sites that no longer carried that
  instruction)**: resolved in place, per `D-Review-Material-Lifecycle`
  point 4's own disposition-correction convention — the fix sentence is
  re-quoted as superseded wording, attributed to round 26's own finding I2,
  and marked superseded by round 27's own finding B1 (whose actual
  resolution is recorded at revision 28's own entry above); the false
  "Applied at …" claim is dropped. Applied at §7's own revision-27 entry
  only.
  **O1 (two of this milestone's own `D-`named design decisions —
  `D-Canonical-Review-Data` and `D-Post-v2.3.1-Backlog` — have no
  design-of-record destination in `WORKFLOW_V2_PLAN.md`)**: resolved by
  adding one sentence to each of §2.5 and §2.7 stating this is deliberate,
  not a scope gap.
  **O2 (§6's own scope-statement bullet named the authorship-shaped scope
  ahead of its marker-based mechanical basis, the same order I2 above
  repoints in §2.4 point 3)**: resolved by restating the bullet's
  mechanical basis first, mirroring the repoint above, so both documents
  state one consistent basis for the same scope. Applied at §6 only.
  **Structural note (optional but recommended, required acceptance
  criterion 9)**: one sentence is added after the subject/mechanism/timing
  table stating what CP1 has already written to the overlay tree — its own
  `HISTORICAL`-marked disposition-record subsection, in the representation
  CP1 itself fixes — before any row in the table is first evaluated, so an
  ordering precondition of B1's or I1's shape cannot be written again
  without the table contradicting it. Applied at §2.4 point 3 only.
  **Missing tests**: B1's own representation-conformance fixture and I1's
  own narrowed-assertion regression, both above; no other new tests — I2,
  I3, O1 and O2 are prose/citation corrections with no behavioral
  component.
  **Required acceptance criteria 1-9**: applied at §2.1 (criterion 1's
  representation reassignment), §2.4 point 3 (criteria 1, 2, 3, 5, 9 — the
  separability bullet, the guarantees preamble, guarantee (v) and its table
  row, the repointed appeal, and the new structural note), §6 (criteria 1
  and 8 restated identically, criterion 8's mirrored repoint), CP1's
  registry entry and CP6's registry entry (criteria 1 and 2 restated
  identically), §7's own revision-27 entry (criterion 6), REQ-9's fixture
  enumeration (criterion 2), and §2.5/§2.7 (criterion 7); the
  plan/registry/mapping are regenerated at `plan_revision: 29` (still 13
  checkpoints, no `checkpoint_ids` list change, still 16 requirements; §2.1,
  §2.4 point 3, §6, CP1's registry entry, CP6's registry entry, REQ-9's
  mapping description (and therefore §4's own row, per §7's own standing
  note above), §2.5, §2.7, §7's own revision-27 entry, and this section's
  own new entry are the only text that changes) and a fresh local plan
  review is run against the new `review_content_id` before returning to
  manual-external review, per required criterion 10.
  **Scope discipline.** This revision touches only §2.1, §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6, CP1's registry entry, CP6's registry
  entry, REQ-9's mapping row/§4's row, §2.5, §2.7, §7's own revision-27
  entry (the superseded-wording correction only), and this section's own
  new entry — the same stuck design element, its direct dependents, and
  this section's own bookkeeping. No other design decision — the two-stage
  review protocol (§2.2-§2.3, and §2.1 apart from CP1's own new
  representation clause), the finding-taxonomy circuit-breaker (§2.6), or
  the post-v2.3.1 backlog (§2.7's own defect dispositions, CP9-CP10) — is
  reopened.
- **Revision 30 applies `LOCAL_MODEL_PLAN_REVIEW` round 29's `REVISE`
  feedback (one Blocking finding, two Important findings, three Optional
  findings) against revision 29 (reviewed `bundle_id:
  e26a5f709cd46262c57e3554f32f2aaa25f4ed0be3a41797d8c15ea71120469a`).**

  **B1 (revision 29's "this narrowed assertion is itself the required
  regression" named no run this plan requires to be green, and the
  real-corpus state the claim depended on — the tree as it stands before
  CP6's own marking pass — stops existing in the worktree once CP6
  completes, so a future edit that re-widens guarantee (v) would break no
  check the real corpus alone could still run against)**: resolved by
  taking resolution 2 of the three the reviewer offered — a durable
  pre-marking-partition fixture, rather than the one-shot real-corpus
  observation, is what pins guarantee (v)'s narrowed form. Applied at
  guarantee (v) itself, §2.4 point 3's fixture bullet, §6's fixture list,
  and CP6's registry entry, each adding the same fixture description; the
  real-corpus observation is retained, restated as confirmatory rather than
  as the regression itself. **B1's test**: the pre-marking-partition
  fixture, at the same three sites as CP6's other fixtures plus REQ-9's own
  fixture enumeration — a corpus-shaped fixture document containing one
  already-`HISTORICAL`-marked unit alongside unmarked units, asserting the
  narrowed verdict passes and the widened "every unit classifies `CURRENT`"
  form fails, surviving CP6's own marking pass since it is a fixture rather
  than a real-corpus read.
  **I1 (the representation is now CP1's decision, but no artifact is named
  in which CP1 records it, so CP6's obligation to use "the representation
  CP1 has already fixed" has no checkable referent)**: resolved by taking
  the second of the two branches the reviewer offered — CP1's own single
  written marker instance is declared to be the specification itself, not a
  syntax CP1 must additionally restate in some other named artifact; naming
  a second, hand-written record of a fact CP1 also writes literally would
  create a second statement of the same fact with nothing keeping the two
  in sync, the same "not a determinate destination" shape revision 21's own
  finding I3 already retired once, one level up. Applied at §2.1 (CP1's own
  deliverable) and §2.4 point 3 (the separability bullet), each stating the
  same declaration and naming the representation-conformance fixture as
  what pins CP6's conformance to it. **I1's test**: "none — the
  single-instance branch declines the general-grammar test the reviewer's
  first branch would have required, since there is no second, more general
  specification for a variant marker to conform to or diverge from; the
  existing representation-conformance fixture is the whole of what proves
  the coupling." **Superseded at revision 31** (`LOCAL_MODEL_PLAN_REVIEW`
  round 30, finding I1: this bullet's own declination reasoned about a
  general-grammar test that does not exist, while the declaration it
  declined a test for — conjunct B, that CP6's own writer stays inside
  CP1's exact representation — is a same-bytes claim with CP1's own
  instance as a determinate referent, not a general-grammar claim with none;
  the representation-conformance fixture, as it stood, exercised recognition
  only, never that writer-exclusivity direction. Resolved by widening the
  same fixture, at all four sites, to also assert exclusivity — see §2.4
  point 3's separability and fixture bullets, §6's fixture list and CP6's
  registry entry, revision 31).
  **I2 (guarantee (vi)'s closing sentence still attributed the marker's own
  representation to CP6, eighty lines after the separability bullet
  reassigned it to CP1)**: resolved by repointing the sentence to state the
  representation is CP1's, fixed per the separability bullet, while the
  narrative's own textual shape stays CP6's. Applied at guarantee (vi)
  only.
  **O1 (the structural note asserts an in-tree marker while the
  separability bullet still offered CP1 a sidecar representation that would
  not be in the tree at all)**: resolved by dropping the sidecar option
  from the list of mechanisms the separability bullet offers — CP1's
  required marker instance already lives inside `WORKFLOW_V2_PLAN.md`
  itself (§2.1), never beside it, so a sidecar was never actually a live
  choice once §2.1 fixed where CP1 writes that marker. Applied at §2.4
  point 3's separability bullet only.
  **O2 (REQ-9 still traces to CP6 alone, now that CP1 owns part of REQ-9's
  mechanism)**: resolved by adding `CP1` to REQ-9's `checkpoint_ids`.
  Applied at the mapping and §4's own row.
  **O3 (§7's own revision-27 entry pointed at a claim it deleted — "the
  claim below" naming an "Applied at …" claim revision 29 had already
  dropped)**: resolved in place, retargeting "the claim below" to "the
  claim this entry carried". Applied at §7's own revision-27 entry only.
  **Missing tests**: B1's own pre-marking-partition fixture, above; I1's
  test is declined with the reason stated above, per the reviewer's own
  second branch; no other new tests — I2, O1, O2 and O3 are prose/citation/
  traceability corrections with no behavioral component.
  **Required acceptance criteria 1-10**: applied at guarantee (v) and §7's
  own revision-29 entry (criterion 1, resolution 2 named), the
  pre-marking-partition fixture at §2.4 point 3's fixture bullet, §6's
  fixture list, CP6's registry entry and REQ-9's fixture enumeration
  (criterion 2), §2.1 and §2.4 point 3 (criterion 3, the single-instance
  declaration), the stated declination above (criterion 4), guarantee (vi)
  (criterion 5), §2.4 point 3's separability bullet (criterion 6), REQ-9's
  `checkpoint_ids` and §4's row (criterion 7), §7's own revision-27 entry
  (criterion 8); criterion 9 (an optional guarantee -> fixture/run table) is
  declined — composing it accurately means re-deriving each guarantee's
  proof set from the fixtures and runs §2.4 point 3 and §6 already
  enumerate in full, and a second, hand-maintained index of the same facts
  risks exactly the drift this round's own B1 and I1 findings were about,
  for a document that already states each guarantee's witness inline where
  the guarantee itself is stated; the enumerated fixtures/runs list remains
  the sole proof-side source. The plan/registry/mapping are regenerated at
  `plan_revision: 30` (still 13 checkpoints, `checkpoint_ids` list widened
  only for REQ-9 — CP1 added — still 16 requirements; guarantee (v),
  guarantee (vi), §2.1, §2.4 point 3, §6, CP1's registry entry, CP6's
  registry entry, REQ-9's mapping description and `checkpoint_ids` (and
  therefore §4's own row), §7's own revision-27 and revision-29 entries, and
  this section's own new entry are the only text that changes) and a fresh
  local plan review is run against the new `review_content_id` before
  returning to manual-external review, per required criterion 10.
  **Scope discipline.** This revision touches only guarantee (v), guarantee
  (vi), §2.1, §2.4 point 3, `D-Review-Material-Lifecycle`, §6, CP1's
  registry entry, CP6's registry entry, REQ-9's mapping row/§4's row, §7's
  own revision-27 entry (the dangling-reference correction only), §7's own
  revision-29 entry (the superseded-wording correction to its own I1's-test
  bullet only), and this section's own new entry — the same stuck design
  element, its direct dependents, and this section's own bookkeeping. No
  other design decision
  — the two-stage review protocol (§2.2-§2.3), the finding-taxonomy
  circuit-breaker (§2.6), or the post-v2.3.1 backlog (§2.7, CP9-CP10) — is
  reopened.
- **Revision 31 applies `LOCAL_MODEL_PLAN_REVIEW` round 30's `REVISE`
  feedback (no Blocking finding, one Important finding, two Optional
  findings) against revision 30 (reviewed `bundle_id:
  837ed0bfb17161234f169403c601d2a78926b313338a063da518adc536491fe4`).**

  **I1 (the separability bullet's conformance definition has two conjuncts
  — recognizing CP1's own written instance, and every marker CP6 itself
  writes reusing that exact syntax — but the representation-conformance
  fixture named as "the sole thing that need pin it" exercises only the
  first; nothing in CP6's enumerated proof set asserts the second, and the
  stated justification for declining a test wrongly treated conjunct B as a
  general-grammar claim with no determinate referent, when CP1's own
  instance is exactly that referent)**: resolved by taking resolution 1 of
  the three the reviewer offered — widening the existing
  representation-conformance fixture, rather than adding a new fixture, to
  additionally assert the exclusivity direction: a marker not in CP1's
  representation is not recognized as an explicit marker and falls to the
  `CURRENT` fail-closed default. Applied at §2.4 point 3's separability
  bullet and CP1's registry entry, both dropping "is what pins this, and is
  the sole thing that need pin it, since there is no second, more general
  specification for a variant input to conform to or diverge from" in favor
  of stating the fixture now pins both conjuncts. **I1's test**: the
  representation-conformance fixture, widened at the same four sites as
  CP6's other fixtures (§2.4 point 3's fixture bullet, §6's fixture list,
  CP6's registry entry, REQ-9's own fixture enumeration is unchanged in
  substance since it already names the fixture, not its assertions) with a
  mutated-marker case asserting the exclusivity direction; nothing further
  is needed for conjunct B's enforcement, since the real-corpus
  marker-presence run already required for guarantee (vii) now catches a
  divergent writer once the parser's exclusivity is itself asserted.
  **O1 (REQ-9's fixture-provenance citation opened with `I4` —
  two-version-transition's own finding, the ninth-from-last fixture — while
  claiming to name only "the last eight", and omitted one `I1`)**: resolved
  by correcting the count, revision range and label sequence to "the last
  nine added at revisions 22-25, 28, 29 and 30, findings
  I4/I3/I1/I1/I3/I1/B1/B1/B1". Applied at the mapping's REQ-9 description
  and §4's own row only.
  **O2 (the pre-marking-partition fixture — and the fixture list as a
  whole — never states whether it is part of CP6's own completion
  requirement)**: resolved by adding one clause to §2.4 point 3's fixture
  bullet, stating once that every fixture in the enumerated list blocks
  CP6's own completion, settling the same question for all twelve fixtures
  at once rather than per-fixture. Applied at §2.4 point 3's fixture bullet
  and CP6's registry entry only.
  **Missing tests**: I1's own exclusivity assertion on the
  representation-conformance fixture, above; no other new tests — O1 and O2
  are citation/wording corrections with no behavioral component.
  **Required acceptance criteria 1-6**: applied at §2.4 point 3's
  separability bullet and CP1's registry entry (criterion 1), the widened
  representation-conformance fixture at §2.4 point 3's fixture bullet, §6's
  fixture list and CP6's registry entry (criterion 2), this entry itself and
  the revision-30 entry's own I1's-test bullet marked superseded above
  (criterion 3), REQ-9's mapping description and §4's own row (criterion
  4), §2.4 point 3's fixture bullet and CP6's registry entry (criterion 5);
  criterion 6 (the attribution-discipline suggestion in place of criterion
  9's declined guarantee -> witness table) is declined for the same reason
  revision 30 declined the table itself — a second, hand-maintained
  discipline statement would duplicate what §2.4 point 3 and §6 already do
  at each site this round and the two before it touched, and duplication is
  exactly what this round's own finding was about; the discipline is
  followed here (each new claim quotes what it supersedes) without a
  separate rule stating it. The plan/registry/mapping are regenerated at
  `plan_revision: 31` (still 13 checkpoints, no `checkpoint_ids` list
  change, still 16 requirements; §2.4 point 3, §6, CP1's registry entry,
  CP6's registry entry, REQ-9's mapping description (and therefore §4's own
  row), §7's own revision-30 entry, and this section's own new entry are the
  only text that changes) and a fresh local plan review is run against the
  new `review_content_id` before returning to manual-external review, per
  required criterion 7.
  **Scope discipline.** This revision touches only §2.4 point 3,
  `D-Review-Material-Lifecycle`, §6, CP1's registry entry, CP6's registry
  entry, REQ-9's mapping row/§4's row, §7's own revision-30 entry (the
  superseded-wording correction to its own I1's-test bullet only), and this
  section's own new entry — the same stuck design element, its direct
  dependents, and this section's own bookkeeping. No other design decision
  — the two-stage review protocol (§2.2-§2.3), the finding-taxonomy
  circuit-breaker (§2.6), or the post-v2.3.1 backlog (§2.7, CP9-CP10) — is
  reopened.
- **Revision 32 applies `MANUAL_EXTERNAL_PLAN_REVIEW` round 2's `REVISE`
  feedback (no Blocking finding, two Important findings, one Optional
  finding) against revision 31 (reviewed `bundle_id:
  32f5632bf8d7e6925e743f9a39301f6ba3d5a179c6ddcab721d46c0fbdbb9c89`).**

  **I1 (the compatibility contract promised global, unqualified zero
  change to `"1"`/`"2.1"` behavior on update to `2.5.0` — REQ-1, REQ-15
  and §5's opening bullet — while §5 and REQ-12 simultaneously ship CP9 as
  release-wide forward-only fixes that do change future behavior for a
  `"1"`/`"2.1"`-governed repository or work item: `v2.3.1-003`'s
  first-ever plan-approval fallback, `v2.3.1-001`'s host-history
  conformance behavior, and `v2.4.0-001`'s default classification for a
  newly-generated implementation-stage declarations file)**: resolved by
  narrowing every occurrence of the zero-change/byte-identical claim to
  the surface it is actually meant to cover — the two-stage
  local-then-manual-external review protocol and version-gated
  inheritance this milestone adds — and explicitly excepting CP9's own
  enumerated forward-only fixes (owned by REQ-12) from that narrower
  claim, everywhere the broader claim previously appeared unqualified.
  The stronger, unweakened guarantee — that no already-recorded history
  and no already-generated declarations file is ever retroactively
  rewritten by either surface — is restated, not narrowed. Applied at
  REQ-1's and REQ-15's mapping descriptions (and therefore §4's own two
  rows) and §5's opening bullet. No architecture change: CP9's own
  already-planned regressions remain the positive evidence for the
  intentional forward changes, and the existing `"1"`/`"2.1"` regression
  coverage continues to prove the new `"2.2"` review machinery changes
  nothing else.

  **I2 (CP1's single written `HISTORICAL` marker instance was stated to be
  itself the complete representation specification, but one instance
  fixes only its own literal bytes — it does not by itself determine
  which part of those bytes is the state-valued slot, or the complete
  accepted form of the representation's second state, `CURRENT`; the
  widened representation-conformance fixture proved recognition and
  exclusivity of that one instance, not what the canonical two-state
  representation actually is)**: resolved by replacing the single-instance
  claim with a single canonical, machine-readable `render_marker(state)` /
  `parse_marker(text) -> state | None` definition (or an equivalent single
  pair) whose own state parameter/return type is restricted to exactly the
  two-member domain `{CURRENT, HISTORICAL}` — never a second, hand-written
  prose grammar. CP1 writes its own required `HISTORICAL` marker by
  calling this same `render_marker`, so CP1's own instance is a *product*
  of the canonical definition rather than a second, competing source of
  truth for it; CP6 imports and reuses the identical pair for every marker
  it writes and for its own lint's parsing. Applied at §2.4 point 3's
  separability bullet and CP1's and CP6's registry entries. **I2's test**:
  the representation-conformance fixture (§2.4 point 3's separability
  bullet and CP6's registry entry — corrected here at revision 33,
  `LOCAL_MODEL_PLAN_REVIEW` round 32, finding I1, from "§2.4 point 3's
  fixture bullet, §6's fixture list, CP6's registry entry": at revision 32
  the widening below was applied only at the separability bullet and CP6's
  registry entry; §2.4 point 3's own fixture bullet and §6's fixture list
  were not actually reached until revision 33) is widened to exercise the
  canonical pair directly — accepting `render_marker("HISTORICAL")`'s own
  output as `HISTORICAL`, accepting `render_marker("CURRENT")`'s own
  output as an *explicit* `CURRENT` marker (distinct from the fail-closed
  default a missing marker also classifies `CURRENT`), and rejecting
  representative malformed/out-of-contract forms (a mutated delimiter, a
  third state value, truncated or duplicated marker text) back to the
  `CURRENT` fail-closed default — plus a mechanical equality check that
  CP1's own written instance and every marker CP6's marking pass writes
  equal `render_marker`'s own output bytes for their respective state.

  **O1 (the `CURRENT`/`HISTORICAL` classification is semantic only and
  does not itself reduce bundle/context size; CP6 should not be credited
  with direct token/context reduction)**: no plan correction required —
  §2.4's own point 2 already states this limitation explicitly ("does not
  change `review_content_id`, `PLAN.md`, bundle `files/`, or a reviewer's
  actual reading list"), and REQ-9/CP6 make no contrary claim anywhere in
  this plan. Left as-is.

  **Missing tests**: I2's own widened representation-conformance fixture,
  above; I1 requires no new test, since CP9's own already-planned
  regressions and the existing `"1"`/`"2.1"` regression coverage already
  discharge it once the compatibility wording is narrowed correctly.
  **Required acceptance criteria 1-6**: criteria 1-2 applied at REQ-1's and
  REQ-15's mapping descriptions and §5's opening bullet; criteria 3-4
  applied at §2.4 point 3's separability bullet and CP1's and CP6's
  registry entries; criterion 5 applied at §2.4 point 3's separability
  bullet and CP6's registry entry (corrected here at revision 33,
  `LOCAL_MODEL_PLAN_REVIEW` round 32, finding I1, from "§2.4 point 3's
  fixture bullet, §6's fixture list and CP6's registry entry"; §2.4 point
  3's fixture bullet and §6's fixture list are widened only at revision
  33, below); criterion 6 (regenerate
  plan/registry/mapping and obtain a fresh local plan review before
  returning to manual-external review) is this entry's own closing
  action, below. The plan/registry/mapping are regenerated at
  `plan_revision: 32` (still 13 checkpoints, no `checkpoint_ids` list
  change, still 16 requirements; the title's revision marker, §5's opening
  bullet, §2.4 point 3, REQ-1's and REQ-15's mapping descriptions (and
  therefore §4's own two rows), CP1's and CP6's registry entries, and this
  section's own new entry are the only text that changes) and a fresh
  local plan review is run against the new `review_content_id` before
  returning to manual-external review, per required criterion 6, per
  `/apply-plan-review`'s own two-stage-review revised exit step (identical
  for `"2.1"` and `"2.2"` alike, this work item's own governing version
  being `"2.1"`).
  **Scope discipline.** This revision touches only §5's opening bullet,
  REQ-1's and REQ-15's mapping rows/§4's own rows, §2.4 point 3,
  `D-Review-Material-Lifecycle`, CP1's registry entry, CP6's registry
  entry, and this section's own new entry — never §6, corrected here at
  revision 33, `LOCAL_MODEL_PLAN_REVIEW` round 32, finding I1, from a
  sentence that wrongly named §6 among the sections this revision touches
  (revision 32 touched no text inside §6 at all) — the same two findings'
  direct dependents, and this section's own bookkeeping. No other design
  decision — the two-stage review protocol (§2.2-§2.3), the
  finding-taxonomy circuit-breaker (§2.6), or the post-v2.3.1 backlog
  (§2.7, CP9-CP10) — is reopened.
- **Revision 33 applies `LOCAL_MODEL_PLAN_REVIEW` round 32's `REVISE`
  feedback (two Blocking findings, one Important finding, one Optional
  finding) against revision 32 (reviewed `bundle_id:
  2e14c92d9c70102e4170bfcc4ab40c4105c01516f123b9587f1965477c4d7855`).**

  **B1 (§2.1 still stated the retired "CP1's single written instance of
  this representation is itself the specification" claim as live
  normative text, and asserted §2.4 point 3's separability bullet "states
  the same" when that bullet now states the opposite)**: resolved by
  replacing §2.1's stale claim with the same revision-32 canonical-source
  statement §2.4 point 3's separability bullet already carries, and
  correcting the cross-reference to describe what that bullet actually
  states now (the full `render_marker`/`parse_marker` contract, not a
  restatement of the single-instance claim). Applied at §2.1 only.

  **B2 (the parser and its grammar were still assigned to CP6 at five
  sites — §2.1, §2.4 point 3's own closing-paragraph sentence and its
  separate closing paragraph, §6's lifecycle-lint bullet, and CP6's
  registry entry — defeating criterion 4's single-source binding revision
  32 itself states)**: resolved by narrowing all five sites to what
  actually remains CP6's — the lint that runs the parser (unit
  segmentation and heading traversal, the marker-presence scope
  enumeration, the forbidden-narrative textual shape, reporting) and every
  guarantee CP6 must prove — and naming marker parsing itself as CP1's own
  `parse_marker`, imported by CP6 rather than re-derived, at each site.
  CP1's registry entry carried the identical stale phrase, unenumerated by
  this finding but the same defect, and is narrowed identically here so
  the two registry entries do not disagree. **B2's own missing-test
  note**: the representation-conformance fixture (§2.4 point 3's fixture
  bullet, §6's fixture list, CP6's registry entry) additionally asserts
  that CP6's own lint reaches its `CURRENT`/`HISTORICAL`/malformed
  classification verdicts by calling this same `parse_marker`, so a lint
  whose own grammar tolerates a form outside the canonical pair cannot
  pass with the fixture green.

  **I1 (criterion 5's fixture widening was absent from two of the three
  sites §7's revision-32 entry claimed it was applied at — §2.4 point 3's
  fixture bullet and §6's fixture list — and that entry itself misnamed
  the separability bullet as the "fixture bullet")**: resolved by applying
  revision 32's own canonical-pair widening (matching CP6's registry
  entry, which already carried it) at both §2.4 point 3's fixture bullet
  and §6's fixture list, and by correcting §7's revision-32 entry (the
  I2's-test parenthetical, the required-acceptance-criteria-5 sentence,
  and the scope-discipline sentence, all three above) to name only the
  sites revision 32 itself actually touched, with the superseded wording
  quoted in place, per this plan's own §2.4 point 4 disposition-correction
  convention.

  **O1 (§4's "why a new requirement" paragraph quoted REQ-1's
  pre-narrowing, revision-6 wording)**: resolved by updating the quotation
  to REQ-1's current, revision-32-narrowed wording, with the original
  quoted form retained and dated in place.

  **Missing tests**: none beyond B2's own missing-test note and I1's
  fixture widening, above — both required tests this revision applies, not
  new fixture families.

  **Required acceptance criteria 1-7**: criterion 1 applied at §2.1
  (replacing the stale specification claim and correcting its
  cross-reference); criterion 2 applied at §2.1, §2.4 point 3's own
  closing-paragraph sentence and its separate closing paragraph, §6's
  lifecycle-lint bullet, and CP6's registry entry — plus CP1's registry
  entry, carrying the identical stale phrase though unenumerated by this
  finding; criterion 3 applied at §2.4 point 3's fixture bullet and §6's
  fixture list; criterion 4 applied at §2.4 point 3's fixture bullet, §6's
  fixture list and CP6's registry entry; criterion 5 applied at §7's
  revision-32 entry, at the three sentences named above; criterion 6
  (optional, §4's REQ-1 quotation) applied; criterion 7 (regenerate
  plan/registry/mapping and obtain a fresh local plan review before
  returning to manual-external review) is this entry's own closing action,
  below. The plan/registry/mapping are regenerated at `plan_revision: 33`
  (still 13 checkpoints, no `checkpoint_ids` list change, still 16
  requirements; §2.1, §2.4 point 3, §4, §6, CP1's registry entry, CP6's
  registry entry, §7's own revision-32 entry, and this section's own new
  entry are the only text that changes) and a fresh local plan review is
  run against the new `review_content_id` before returning to
  manual-external review, per required criterion 7, per
  `/apply-plan-review`'s own two-stage-review revised exit step.
  **Scope discipline.** This revision touches only §2.1, §2.4 point 3, §4,
  §6, CP1's registry entry, CP6's registry entry, and §7's own revision-32
  entry (the wording corrections named above only) — the same one round's
  findings' direct dependents, and this section's own bookkeeping. No
  other design decision — the two-stage review protocol (§2.2-§2.3), the
  finding-taxonomy circuit-breaker (§2.6), or the post-v2.3.1 backlog
  (§2.7, CP9-CP10) — is reopened.

## 8. Disposition of the four previously-deferred defects (§2.7)

(Superseded at revision 3: the old title — "Confirmation this milestone
leaves the four deferred defects alone" — described revision 1/2's
now-corrected blanket exclusion, §1. Revision 2, `LOCAL_MODEL_PLAN_REVIEW`
round 1, finding I3, remains correctly folded in below: this repository's
own `docs/defects/` log holds five records, of which `v2.3.1-002` is the
one already *fixed* (by `2.4.0`) and the four below were, until this
revision, all deferred.)

- **`docs/defects/v2.3.1-001-host-history-coupled-tests.md` — fixed
  (CP9).** The defect record's own portable form is adopted: the
  conformance test skips cleanly when no host status note is present,
  instead of raising `StopIteration`. The frozen conformance fixture
  (which does carry the dated host note) is unaffected. **Corrected at
  revision 4 (finding I4)**: `2.3.1`'s and `2.4.0`'s own
  `migration/portability_exceptions.json` entries for this test are
  untouched — both releases' payloads still carry the unfixed test; only
  `2.5.0` gains its own required, empty `by_version["2.5.0"]` entry (§2.7
  point 2, §6).
- **`docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`
  — fixed (CP9).** The defect record's own portable form is adopted:
  `pin_plan_approval_state_blob` defaults to mode `100644` when no `HEAD`
  blob exists, instead of refusing unconditionally. This repository's own
  first-ever plan approval already recovered by a different route
  (`plan-amendment-mechanism` committed `WORKFLOW_STATE.json` before this
  milestone began) and is unaffected either way; the fix is for every
  *other* repository's own genuinely-first plan approval, which no longer
  hits this refusal after updating to `2.5.0`.
- **`docs/defects/v2.4.0-001-workflow-manager-installation-record-unclassified-at-plan-stage.md`
  — implementation-stage symmetry widened (CP9), still not retroactively
  repaired.** Revision 2 (finding B2) already corrected revision 1's false
  claim that this item was "not itself a fresh victim," and hand-fixed this
  item's own implementation-stage declarations file (§7's finding B1) as
  the record's own "before the stage's approval" cheap case permits.
  Revision 3 goes one step further and reconsiders the underlying
  generator gap itself, per the roadmap correction's instruction: `2.4.0`'s
  own fix widened only `generate_artifacts_declarations`'s **plan-stage**
  default `excluded_prefixes`, leaving the identical gap in its
  **implementation-stage** default template — exactly what this item had
  to hand-fix for itself. CP9 widens the implementation-stage default the
  same way, forward-only: no existing work item's already-generated
  declarations file is edited (editing one after the fact would itself
  stale a standing approval, the same reasoning the record already gives
  for the plan-stage case). The defect's own retroactive non-repair
  reasoning therefore still holds for every already-existing work item;
  what changes is that a *future* work item's first-ever implementation-stage
  declarations file is generated already-correct, the same guarantee
  `2.4.0` already gave the plan stage.
- **`docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`
  — reconsidered, still deferred in full (CP10), for stated reasons rather
  than by omission.** §2.7 point 4 gives the full reasoning: both full
  structural fixes (a `claims_dir`-rooted lock; a repo-global phase
  witness) remain out of scope, as concurrency-correctness engineering
  this milestone's own review-tooling mission does not undertake, and as
  scope creep the user's own narrow-scope instruction argues against. The
  cheap `IMPL10-O1` partial mitigation was recorded as a live, optional
  adoption pending §9's own decision; **resolved at revision 15**
  (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, required acceptance criterion
  4): declined, deferred together with the two structural fixes. All four
  defects now carry a settled disposition.

## 9. Open decisions surfaced for review — resolved at revision 15

(`docs/TECHNICAL_DECISIONS.md` does not exist in this repository, so
`/milestone-plan` step 5's check is vacuous by inspection; the three
decisions below were surfaced here instead, in the same spirit. Corrected at
revision 4: this parenthetical said "two" from revision 1 through revision
3 without being updated as decisions were added and, at this revision,
resolved — another instance of the same stale-cross-reference class §2.4
and finding I3 both name. **All three are now resolved** by
`MANUAL_EXTERNAL_PLAN_REVIEW` round 1's required acceptance criterion 4;
each is kept below, rather than deleted, as this milestone's own
disposition record for it, per `D-Review-Material-Lifecycle`'s point 4
convention (§2.4): the option originally recommended, the alternatives
considered, and the resolution, so a future reader sees what was decided
and why rather than only the outcome.)

1. **Terminal-phase naming** (§2.2, re-framed at revision 2 per finding I1
   to carry all three live options, not two) — **resolved: (b)**, reuse
   `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` as the `"2.2"` terminal
   "ready for approval" phase, this plan's own recommendation throughout,
   on the grounds already stated in §2.2: it avoids a new phase-name read
   site anywhere `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` is already
   referenced. (a) introducing a genuinely new, distinct persisted name,
   and (c) promoting the existing vocabulary-only `AWAITING_TECHNICAL_APPROVAL`
   name to the persisted terminal phase — zero new vocabulary, and (unlike
   revision 1's framing) not a weaker alternative to (b) on vocabulary
   grounds, since `AWAITING_PLAN_APPROVAL` — the state (b)'s analogy rests
   on — is itself a `"2.1"`-era promotion of a previously vocabulary-only
   name, exactly what (c) would do here — both remain recorded as
   considered, live alternatives a future release is free to prefer, not
   as options this milestone silently discarded.
2. **`"2.2"` activation-ceremony scope** (§2.2) — **resolved:** the
   lightweight, direct config-default commit with activation/rollback
   trailers, this plan's own recommendation, on the grounds already stated
   in §2.2 that the original `WF-Activate` ceremony's rigor was there to
   *establish* the pattern, not something every subsequent version bump
   must re-earn, and that CP12's real disposable-repository end-to-end
   validation is a stronger check than repeating the original multi-session
   synthetic dry-run ceremony would add on top. The full-ceremony repeat
   remains recorded as considered and declined.
3. **`v2.4.0-002`'s cheap partial mitigation** (§2.7 point 4, §8) —
   **resolved: declined.** `IMPL10-O1` (a second `resolve_claim(...)`
   re-check immediately before `request_plan_amendment`'s own supersede,
   narrowing reason 1's exposure window at no new primitive and no
   `item 372(h)` edge) is deferred together with both full structural
   fixes, for a future release that takes up `v2.4.0-002` as its own
   dedicated concurrency-correctness work — for the same reason the defect
   record itself already gave when it first declined this exact option
   (round 10, under review pressure, in the same round the residual was
   found): narrowing one race window without establishing the documented
   cross-worktree guarantee adds surface to a critical section in a
   review-focused milestone without closing the defect. This is the one
   decision of the three this plan itself took no default position on
   before the plan-review gate weighed in ("the plan-review gate should
   decide fresh rather than infer a recommendation from silence," revision
   14's own framing) — the gate has now done so, above.

**Circuit-breaker round bound — resolved, no longer an open decision
(revision 4, `LOCAL_MODEL_PLAN_REVIEW` round 3, findings I5/I6).** Revision
3 carried this as a fourth open decision, recommending 2 but inviting a
reviewer to prefer "3 or more." Round 3 found that recommendation
unimplementable above 2 from the data this milestone's own §2.6 design
deliberately leaves available (no durable per-round record — see §2.6
point 3's own restated reasoning), so there is no live 3-or-more
alternative to surface for a reviewer to choose between; §2.6 above now
states 2 as the bound directly, settled together with I5's tag-enforcement
correction rather than left open beside it, per round 3's own "§9.3's
bound should be settled together with I5/I6 rather than before them."

Decisions 1-2 were implementation-detail-level with a stated recommendation,
not product-behavior forks; decision 3 was new at revision 3 and carried a
deliberate non-recommendation. All three were surfaced here so the
plan-review gate could confirm or override them before CP1/CP10 lock them
into the overlay's own design document; the plan-review gate has now done
so (above), and CP1/CP10 lock in exactly the resolutions stated. (**Corrected
at revision 5, `LOCAL_MODEL_PLAN_REVIEW` round 4, optional finding 4** —
"Both" undercounted the three decisions above, the same stale-count class
this section's own opening parenthetical was corrected for at revision 4.)
