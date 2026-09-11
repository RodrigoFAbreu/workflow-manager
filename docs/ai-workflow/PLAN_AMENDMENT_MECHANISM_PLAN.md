# Plan-Amendment Mechanism (Revision 34)

`work_item_id: plan-amendment-mechanism` -- `governing_workflow_version: "2.1"`

## 1. Why this work item exists

Frozen Workflow v2.3.1 has no documented transition out of `IMPLEMENTING` or
`SELF_REVIEWING_IMPLEMENTATION` back into plan revision/review
(`docs/ai-workflow/MILESTONE_WORKFLOW.md`'s state reference has no such
edge). A sibling repository, `workflow-controller`
(`workflow-controller-generation-1`, phase `SELF_REVIEWING_IMPLEMENTATION`,
checkpoint `CP9`), hit this for real: its approved CP3/CP4 architecture has
no zero-work-item decision path, its REQ-T18 disposable-repo scenario needs
one, and the fix is an amendment to its already-approved plan that the
frozen lifecycle has no legal path to apply. That repository is out of
scope for this work item -- it is read-only context, cited only for the
blocker shape, never touched from this session.

This plan designs, and schedules the delivery of, a first-class mechanism
for amending an approved plan after implementation has begun, plus the
successor-release mechanics needed to ship it, plus the update-path
validation needed to deploy it into an existing v2.3.1-managed repository
without touching a real one until disposable-repository rehearsal has
passed. It does **not** edit `distribution/` in place, does not touch
`~/Workspace/workflow-controller`, and does not use `USER_OVERRIDE`,
undocumented manual transitions, or any weakening of an existing approval
binding.

## 2. Design decisions

### D-Plan-Amendment-1: the new phase and its entry gate

One new persisted phase, `AMENDING_PLAN`, added to `KNOWN_PHASES` in the
successor's `workflow_state.py` (additive -- v2.3.1's own thirteen
persisted phases are unchanged and unremoved). It is entered by exactly one
new command, `/request-plan-amendment [work-item-id]`, and left by the
very next `/milestone-plan` invocation -- reusing that command's existing
step 3/`[2.1]` machinery unchanged. `AMENDING_PLAN` is real and persisted
(unlike the four vocabulary states), because the mechanism must survive an
interruption between the request and the first post-request
`/milestone-plan` call.

`/request-plan-amendment`'s entry condition is `phase in {"IMPLEMENTING",
"SELF_REVIEWING_IMPLEMENTATION"}` -- the two phases the task requires at
minimum, and deliberately the *only* two this release supports. A later
phase (`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` onward) is out of scope:
`technical_approval` and functional-review evidence introduce additional
disposition questions (a reviewed bundle, a tested checklist) this release
does not need to solve for the Controller's blocker shape, and scoping
narrower keeps the mechanism small. A future release may widen the phase
set; this one refuses outside it, naming the actual phase.

Two further preconditions, both refusals rather than silent handling:

- **No checkpoint may be `IN_PROGRESS`, and no checkpoint claim may be
  outstanding (widened, revision 5, I1-new).** Reconciliation
  (D-Plan-Amendment-4 below) is defined only over `COMPLETE` checkpoints.
  An in-flight checkpoint must be finished (ordinary `/milestone-implement`)
  or the worktree's own claim released through the existing claim mechanism
  before an amendment can be requested. This is a scope-narrowing choice,
  not a new mechanism: it removes an entire class of "what does
  reconciliation mean for half-done work" question from this release.
  Widened from "no checkpoint may be `IN_PROGRESS`" alone because that
  wording did not require what its own remedy sentence already presumes:
  `resolve_checkpoint_ownership` (`workflow_state.py:5204-5334`, the
  function `/milestone-implement` step 1c calls to decide whether a
  selected checkpoint actually resumes) treats "a self-owned claim
  outstanding, with nothing locally `IN_PROGRESS`" as a third, distinct
  case from "uncontended" and from "locally `IN_PROGRESS`" -- exactly the
  `CONTINUE_CLAIM` crash window between publishing a claim and writing
  local state (`:5290-5302`) that the original wording's "no checkpoint may
  be `IN_PROGRESS`" precondition alone does not exclude. Requiring "no
  checkpoint `IN_PROGRESS`" closes the local half of that gap; requiring
  "no outstanding claim" closes the shared-claim half, so the precondition
  now excludes the case D-Plan-Amendment-7's own I4-new paragraph below
  documents as reachable and refusing.
- **No open plan-approval or approval journal.** Mirrors
  `/approve-review`'s existing "already-open approval journal" refusal --
  an amendment must never race an in-flight approval commit.
- **The current `plan_approval`'s own approval commit must actually be
  discoverable and an ancestor of `HEAD` (new, revision 11, I-R11-1;
  corrected, revision 12, B-R12-1, to call and name only the two checks
  this precondition actually needs)** -- `/request-plan-amendment` calls
  `discover_plan_approval_commit(repo_root, work_item_id,
  plan_approval["approved_review_content_id"], base_commit, head="HEAD")`
  directly and, when the result is not `None`, `_is_ancestor(repo_root,
  approval_commit, head)` directly -- the identical pair
  `implementing_entry_reachable` (`workflow_state.py:1591-1612`) itself
  evaluates at `:1606-1611`, called here on its own terms rather than
  through that function. **Why this precondition is needed, corrected from
  a false premise (I-R11-1)**: an earlier revision of D-Plan-Amendment-3
  justified skipping this check by claiming `plan_approval.status ==
  "CURRENT"` alone already "proves this exact commit exists and is an
  ancestor of `HEAD`" -- false, verified directly against the code.
  `apply_plan_approval` (`workflow_state.py:9638-9650`) is the sole writer
  of `plan_approval`, and it always builds the record through
  `build_approval_record`, which hardcodes `"status": "CURRENT"`
  (`:9480`); no writer anywhere ever assigns `plan_approval["status"]` any
  other value (`STALE`/`SUPERSEDED` are read-only in every live record
  today, per O-R9-4 below), so `status == "CURRENT"` is true of *every*
  live `plan_approval` record unconditionally and proves nothing about
  commit reachability specifically. Nor is reachability a precondition of
  the *phase* `/request-plan-amendment` requires (`IMPLEMENTING`/
  `SELF_REVIEWING_IMPLEMENTATION`): nothing gates `phase` on approval
  reachability, and `implementing_entry_reachable` is a command-time
  predicate `/milestone-implement` step 1a evaluates, never one
  `/request-plan-amendment` itself passed through. So on any history where
  the approval commit is not discoverable in `base_commit..HEAD` (a
  rebase, a force-rewrite, a shallow clone, or a `base_commit` that moved)
  -- none of D-Plan-Amendment-1's other preconditions exclude this --
  `/request-plan-amendment` would otherwise write
  `pre_amendment_approval_commit: null` (D-Plan-Amendment-3 below) into an
  `amendment_history` entry that is immutable from the moment it is
  appended, in the same transaction that sets `plan_approval.status =
  "SUPERSEDED"` -- wedging the item at `AWAITING_PLAN_APPROVAL`
  permanently the same way section 7's accepted, Git-level
  unreproducible-snapshot case is wedged, except self-inflicted by this
  command's own invocation rather than by an external Git accident.

  **Deliberately not `implementing_entry_reachable(repo_root, work_item,
  base_commit)` itself, and deliberately not `approval_is_current`
  (corrected, revision 12, B-R12-1, choosing fix (a) of the two the
  finding offered)**: `implementing_entry_reachable` is a four-exit
  composite, not a two-check one -- `plan_approval is None or
  plan_approval.get("status") != "CURRENT"` (`:1604`), the
  discovery-plus-ancestry pair this precondition calls directly above
  (`:1606-1611`), and, on its own last line (`:1612`), a full call into
  `approval_is_current(repo_root, work_item, stage="plan",
  base_commit=base_commit, head=head)`, which recomputes the plan-stage
  `review_content_id` fresh
  (`approval_review_content_id` -> `fingerprint.compute_review_content_id_plan_stage_at_commit_for_work_item`,
  `workflow_fingerprint.py:1534-1547`) and returns `False` on any mismatch
  with `plan_approval["approved_review_content_id"]`. That third exit is
  exactly what this precondition must *not* ask, because it has nothing to
  do with commit reachability: a committed edit to `plan_path`/
  `registry_path`/`mapping_path` since the approval, or a widened
  `<work_item_id>-artifacts.json` (D-Plan-Amendment-5's own sanctioned
  in-band remedy, below), each moves that digest, and calling the
  composite would make `/request-plan-amendment` refuse by the
  reachability error's own name for a plan the author simply edited in
  preparation for the amendment they are about to request -- the most
  natural operator sequence there is, and D-Plan-Amendment-4's own I3-new
  paragraph below already documents that exact edit as expected, not
  exceptional. The amendment is about to replace this approval anyway, so
  requiring its digest to still be current is not what this gate is for.
  This also reconciles cleanly with D-Plan-Amendment-5's I1-new remedy
  (widening the artifacts declaration mid-amendment): that remedy moves
  the plan-stage digest too, and it now has no bearing on this
  precondition at all, for the same reason.

  **The predicate's non-boolean failure modes, given a stated disposition
  (B-R12-1)**: calling only the two-check pair directly means
  `approval_is_current`'s own digest-recomputation failure surface --
  `UnclassifiedPathError` (from `compute_review_content_id_plan_stage_at_commit`'s
  classification pass) and `resolve_plan_stage_metadata`'s own error
  family (`MissingWorkItemArtifactsDeclarationError`,
  `StaleArtifactsDeclarationError`, `PlanStageMetadataNotProtectedError`)
  -- is never reached by this precondition at all; it belongs to
  `approval_is_current`, which this precondition does not call. The one
  raise that remains reachable here is `discover_plan_approval_commit`'s
  own: `-> discover_approval_commits -> _discover_trailer_commits`
  (`workflow_state.py:1457-1464`, `:1440-1454`, `:1309-1397` respectively;
  reordered and split, revision 15, O-R15-3, to match the three functions'
  own word order and to stop combining two of them into one span) raises
  `AmbiguousApprovalTrailerError` on a duplicated, unresolvable
  `Workflow-Plan-Approval` trailer for this work item. This precondition
  does not catch it -- the same disposition every existing caller of this
  function already gives it (`/milestone-implement` step 1a, via
  `implementing_entry_reachable`, lets the identical error propagate
  uncaught rather than converting it to a different name) -- so a work
  item in that state fails this precondition with
  `AmbiguousApprovalTrailerError`'s own name and recovery hint
  (`_ambiguous_trailer_recovery_hint`), never with
  `AmendmentApprovalCommitUnreachableError`.

  **The `plan_approval` missing entirely, or already `SUPERSEDED`, case --
  excluded by construction, not re-tested by this precondition (B-R12-1's
  third scenario; corrected, revision 13, B-R13-1, which names all three
  writers of the two accepted phases rather than a false single-writer
  claim)**: this precondition never re-tests `plan_approval.status`. It
  does not need to, but the reason is longer than "the only writer" --
  three functions write these two phases, not one. `apply_plan_approval`
  (`workflow_state.py:9638-9650`) sets `phase = "IMPLEMENTING"`
  unconditionally (`:9647`) and, in the same transaction, a freshly
  built, hardcoded-`CURRENT` `plan_approval` record (`build_approval_record`,
  `:9480`). `complete_checkpoint` (`:3183-3256`) and
  `enter_self_reviewing_implementation` (`:3259-3331`) both set
  `phase = "SELF_REVIEWING_IMPLEMENTATION"` (`:3255`, `:3328`), and
  **neither writes `plan_approval` at all**: `complete_checkpoint` carries
  no source-phase guard whatsoever -- its all-complete branch fires on
  registry completeness alone (`:3253-3255`), so nothing in that
  function's own contract constrains which phase it transitions *from* --
  and `enter_self_reviewing_implementation` guards only that its own
  source phase is `IMPLEMENTING` (`:3311`), a fact about that function,
  not about `apply_plan_approval`. The repository's own census agrees:
  `workflow_state_test.py`'s `EXPECTED_WRITERS` states
  `"IMPLEMENTING": {"apply_plan_approval"}` and
  `"SELF_REVIEWING_IMPLEMENTATION": {"complete_checkpoint",
  "enter_self_reviewing_implementation"}` directly (`:10205-10208`), as
  does `WORKFLOW_V2_1_OPERATOR_REFERENCE.md:637-638` (`:637` is the
  `IMPLEMENTING` row, `:638` the `SELF_REVIEWING_IMPLEMENTATION` row).

  The exclusion instead rests on two independent facts, together
  sufficient: first, every path into `IMPLEMENTING` passes through
  `apply_plan_approval`, which always pairs that write with a
  hardcoded-`CURRENT` record -- so `plan_approval` is present and
  `CURRENT` the instant `phase` becomes `IMPLEMENTING`. Second, no writer
  anywhere ever demotes `plan_approval["status"]` away from `CURRENT`
  while the item remains in `IMPLEMENTING` or
  `SELF_REVIEWING_IMPLEMENTATION`: neither
  `SELF_REVIEWING_IMPLEMENTATION` writer touches `plan_approval` (above),
  and the only writer that will ever assign a non-`CURRENT` status is
  `/request-plan-amendment` itself (D-Plan-Amendment-3, below), which
  sets `plan_approval.status = "SUPERSEDED"` in the very same transaction
  that moves `phase` to `AMENDING_PLAN` -- out of the two accepted
  phases, atomically, so no observer of `{"IMPLEMENTING",
  "SELF_REVIEWING_IMPLEMENTATION"}` can ever see the demotion.
  (Re-verified: `grep -n 'plan_approval\["status"\]' workflow_state.py`
  finds exactly this one assignment site once written; today, before it
  exists, the grep is empty, and the module's other `["status"] =`
  writes are `complete_checkpoint`'s own `entry["status"] = "COMPLETE"`
  (`:3248`, a checkpoint-registry entry, not `plan_approval`) and
  `mark_technical_approval_stale`'s unrelated `technical_approval` field,
  `:9694` -- neither is a `plan_approval` write.

  **Third fact, closing the gap the "no source-phase guard" sentence
  above opens (new, revision 14, I-R14-3)**: the first two facts alone do
  not reach an item that enters `SELF_REVIEWING_IMPLEMENTATION` from some
  phase other than `IMPLEMENTING` -- which is exactly what
  `complete_checkpoint` carrying no source-phase guard leaves open in
  principle. What closes it in practice is that `complete_checkpoint` has
  exactly two production callers, and both are already gated:
  `.claude/commands/milestone-implement.md`'s step 1f (`:169`) is reached
  only past step 1a's own entry validation (`:60`), which calls
  `workflow_state.implementing_entry_reachable(...)` and stops the whole
  command when it returns `False` -- and `implementing_entry_reachable`
  itself (`workflow_state.py:1604`) returns `False` the instant
  `plan_approval is None or plan_approval.get("status") != "CURRENT"`,
  before any checkpoint work begins; `.claude/commands/bootstrap-workflow-v2.md`'s
  own call (`:224`) is hardcoded to `workflow-v2-1-core`, a fixed item
  this release does not touch. So no production path reaches
  `complete_checkpoint` for a work item whose `plan_approval` is absent or
  non-`CURRENT` -- the guard the function itself lacks lives in its
  caller, not inside it.

  So whenever the phase precondition passes,
  `plan_approval` is guaranteed present and `CURRENT` -- not because one
  function owns both phases, but because entry into `IMPLEMENTING` always
  installs a `CURRENT` record, no writer before the next
  phase-precondition check can turn it into anything else, and the one
  function that writes `SELF_REVIEWING_IMPLEMENTATION` without touching
  `plan_approval` at all is reachable in production only from an item that
  already passed that same `CURRENT` check on its way into `IMPLEMENTING`.
  `None`/`SUPERSEDED` cannot coexist with `phase in {"IMPLEMENTING",
  "SELF_REVIEWING_IMPLEMENTATION"}` in any state this module's own
  writers can produce, so a defensive re-check of `plan_approval.status`
  here would be dead code, not a second precondition -- the phase check
  already owns this case completely.

  **Residual risk, named rather than argued away (B-R13-1)**: the
  argument above is a closure property of this module's own writers --
  `state_transaction`'s own production callers -- not a schema invariant
  of the JSON file itself. A hand-edited or externally produced
  `WORKFLOW_STATE.json` could set `phase: "IMPLEMENTING"` with
  `plan_approval` absent or `SUPERSEDED` directly, bypassing every writer
  this argument reasons about, and nothing before this precondition would
  catch it. That is not a gap specific to this precondition:
  `validate_state`, the one function that could catch such a mismatch,
  has no production caller anywhere in this repository (`:11246-11258`,
  its own documented limitation) and does not check phase/`plan_approval`
  consistency even as a write-time backstop today (`_validate_work_item`,
  `:11185-11237`, checks `phase in KNOWN_PHASES` and each approval
  record's own shape, never the pair together). Every other phase-gated
  precondition in this module already accepts the same trust boundary --
  a hand-edited state file can violate any of them -- so this
  precondition is not made weaker by accepting it too; closing it would
  mean adding both a new cross-field `validate_state` check and a
  production call site for that function, a change to this module's
  validation posture generally, not a fix scoped to
  `/request-plan-amendment`. Out of scope for this release: the
  defensive check stays out, and the argument above is the one that
  holds against the code today.

  **Fix, restated precisely to name only what it checks**:
  `/request-plan-amendment` refuses with
  `AmendmentApprovalCommitUnreachableError`, naming the work item and its
  `base_commit`, exactly when `discover_plan_approval_commit(...)` returns
  `None` or its result is not an ancestor of `HEAD` -- *before* writing
  anything, never after `plan_approval.status` has already been set to
  `SUPERSEDED`. Section 4's scenario 31 (below) asserts this refusal fires
  on a genuinely unreachable commit and, separately, that a *digest-only*
  mismatch -- the approval commit itself still perfectly reachable -- does
  **not** trigger this precondition at all, so the amendment proceeds,
  exactly as D-Plan-Amendment-4's own I3-new paragraph requires.

### D-Plan-Amendment-2: authority, distinct from `USER_OVERRIDE`

`/request-plan-amendment` carries the same mechanism-independent user-only
guard `/approve-review` and `/accept-milestone` already use:
`disable-model-invocation: true`, plus a literal, specificity-checked
confirmation in the same turn naming the exact `work_item_id` and the
literal word `amendment`, plus a required, non-empty free-text `reason`
(recorded verbatim, evidence-first, matching this workflow's existing
culture of never accepting an unexplained deviation). It never reads,
writes, or compares against the literal string `USER_OVERRIDE` -- that
sentinel stays reserved for `/approve-review`'s existing approval-basis
fallback and is not reused, generalized, or aliased here. Claude cannot
invoke this command, exactly as Claude cannot invoke `/approve-review` or
`/accept-milestone` today.

### D-Plan-Amendment-3: retiring the current approval

`/request-plan-amendment` (the sole writer of this transition) does, in one
`state_transaction`:

1. Sets `plan_approval.status` to a new value, `SUPERSEDED` -- additive to
   the existing `{CURRENT, STALE}` vocabulary, and deliberately distinct
   from `STALE`. `STALE` already means "the same reviewed plan document
   changed under us, by accident or a later `REVISE`"; `SUPERSEDED` means
   "an explicit, authorized amendment retired this approval on purpose."
   Conflating the two would make `plan_approval.status` unable to
   distinguish an accidental staleness bug from a deliberate act, which
   every downstream reader (`/accept-milestone`'s registry-coverage check,
   the "Repairing an artifact declaration" procedure) currently assumes it
   can.

   **The true reason stated precisely, not merely a live disambiguation
   (new, revision 9, O-R9-4)**: `plan_approval.status` in fact never
   reaches `STALE` for a live record -- `apply_plan_approval` is the sole
   writer of the field and always writes `CURRENT`
   (`workflow_state.py:9638`), `mark_technical_approval_stale`
   (`:9676-9697`) writes only `technical_approval.status` and is
   implementation-stage only, and `approval_is_current`'s own docstring
   states it "only ever detects fresh staleness, it never clears a status
   a caller previously set" (`:1569-1570`; corrected, revision 10,
   O-R10-3) -- it is a pure read, and writes nothing. So no live `plan_approval` value is actually being
   disambiguated from `STALE` today; adding `SUPERSEDED` is safer than the
   paragraph above implies, not riskier, because every downstream reader
   already tests `!= "CURRENT"` rather than branching on `STALE`
   specifically. The rationale for keeping the two values distinct still
   holds -- it rests on what a *future* reader could legitimately want to
   distinguish (accidental staleness versus deliberate supersession),
   not on a live ambiguity this design would otherwise resolve
   incorrectly.

   **Disambiguated from a same-named, unrelated vocabulary (I-R32-1)**:
   `workflow_state.py` already contains a `SUPERSEDED` token today, in
   `_RECONCILIATION_STATUS_TOKENS` (`:7397`) -- the closed status
   vocabulary of `workflow-v2-1-core`'s own requirements-ledger
   reconciliation table, read at `_resolve_reconciliation_owner` (`:7471`)
   and roughly a dozen other `*_reconciliation_*` helpers, all over
   `row["status"]` parsed out of a Markdown ledger document, with its own
   `ReconciliationTableParseError`. This is a different value in a
   different dict read by different functions: `validate_approval_record`
   (`:9558`, `record.get("status") not in APPROVAL_STATUSES`) tests
   `plan_approval` records only and never touches a reconciliation-table
   row, so the two never collide at any call site -- the collision is only
   in what a reader running a bare `grep SUPERSEDED scripts/workflow_state.py`
   might assume is one vocabulary. It is not, and CP2's own compatibility
   audit (section 5's CP2 row) must target `APPROVAL_STATUSES`'s real
   validation site directly rather than that raw grep, and must not treat
   `_RECONCILIATION_STATUS_TOKENS`'s reconciliation-table vocabulary as a
   hit -- the same disambiguation `D-Authored-Release-5`'s `CI_SUITES`
   paragraph already makes for that constant's own same-named collision.
2. Appends one entry to a new, append-only `amendment_history` list on the
   work item (`[]` default, so an old v2.3.1-shaped item without the key
   reads as "no amendments yet"): `{amendment_id (0-based index as a
   string), requested_at, requested_from_phase, reason,
   superseded_plan_revision, superseded_plan_approval (a deep copy of the
   record just superseded), checkpoints_snapshot (a deep copy of the live
   `checkpoints` map at request time), pre_amendment_approval_commit (a
   single git commit SHA, below), resolved_at_plan_revision (`null`)}`.

   **Bounded, content-addressed reference model, redesigned this revision
   (EXT-R6-I1, manual external round 6)**: revision 6 stored two additional
   fields here -- `pre_amendment_registry` (the full, parsed JSON content
   of `registry_path` at request time) and `pre_amendment_plan_text` (the
   full byte content of `plan_path` at request time) -- pinned inline and
   never removed. That is withdrawn: `amendment_history` is never trimmed
   (point 2's own "nothing is deleted" rule, below), so those two fields
   alone made `WORKFLOW_STATE.json` grow, unboundedly, by the cumulative
   byte size of every historical approved plan/registry pair the work item
   was ever amended past -- for the motivating Controller plan, itself
   large, a real and not theoretical cost, on a file this workflow
   repeatedly reads, canonical-serializes, hashes, and pins whole into
   every approval journal and commit (`open_plan_approval_journal`,
   `state_transaction`'s own canonical-serialize step). Neither field is
   needed to reproduce those exact bytes: `plan_path`/`registry_path` are
   both entries of this item's own `plan_stage.protected_paths` (verified
   directly against
   `docs/ai-workflow/registry/plan-amendment-mechanism-artifacts.json`,
   which lists exactly `plan_path`, `registry_path`, `mapping_path` there
   -- and, more strongly than a sample of one (new, revision 9, O-R9-2),
   structurally guaranteed for every `"2.1"` work item alike:
   `resolve_plan_stage_metadata` (`workflow_fingerprint.py:996-1003`)
   raises `PlanStageMetadataNotProtectedError` for any work item whose
   `plan_path`/`registry_path`/`mapping_path` is not a member of its own
   resolved plan-stage protected set, and `:1004-1008` additionally
   requires the three to be pairwise distinct -- so this is provably
   total over every work item this mechanism can ever apply to, including
   `workflow-controller`'s own plan, not merely demonstrated on this
   item's own artifacts declaration), so `superseded_plan_approval`'s own
   `review_content_manifest` --
   already retained in this same entry, by this point's own first
   sentence, as roughly a hundred bytes of metadata per protected path
   (corrected, revision 12, O-R12-6, an order of magnitude: a
   `{"path", "exists", "mode", "blob"}` entry carries a path string, a
   40-hex blob SHA, a mode string and a boolean, not "ten bytes" -- "ten"
   there had migrated from `build_approval_record`'s ten metadata *keys*,
   correctly stated below ("`record` ... is exactly ten metadata keys",
   citing `workflow_state.py:9466-9492`) and reconfirmed directly
   (`build_approval_record`, `:9466-9492`); the claim this supports, that
   the cost is bounded by protected-path count and never by a document's
   own byte size, is unaffected)
   (`{"path", "exists", "mode", "blob"}`, `build_approval_record`'s own
   shape) -- already pins the exact Git blob SHA of `plan_path`'s and
   `registry_path`'s content at the moment the superseded approval was
   made, for free, with no new field of its own. What was genuinely
   missing was a way to *retrieve* those bytes later without re-reading
   the (by-then-overwritten) live files: that is
   `pre_amendment_approval_commit`, a single git commit SHA -- the
   plan-approval commit that produced `superseded_plan_approval`,
   discovered once, at request time, via
   `discover_plan_approval_commit(repo_root, work_item_id,
   superseded_plan_approval["approved_review_content_id"], base_commit,
   head="HEAD")` (an existing function, unchanged; reachable and
   non-`None` **by precondition, not by construction (corrected, revision
   11, I-R11-1; citation corrected, revision 12, B-R12-1, to name the
   precondition's own two direct calls rather than the composite)** --
   `plan_approval.status == "CURRENT"` alone proves
   nothing here, since it is true of every live `plan_approval` record
   unconditionally (`build_approval_record` hardcodes it, and no writer
   ever sets any other value); the actual guarantee is
   D-Plan-Amendment-1's own third precondition above, which calls
   `discover_plan_approval_commit(...) is not None` and
   `_is_ancestor(...)` directly (the identical pair
   `implementing_entry_reachable` evaluates at `workflow_state.py:1606-1611`,
   called here on its own terms, never through that four-exit composite --
   B-R12-1) and refuses before
   this step ever runs if either fails -- so by the time this call
   executes, reachability has already been checked, not merely inferred
   from a status field that cannot carry that fact). Every other field this
   point already lists (`superseded_plan_approval`, `checkpoints_snapshot`,
   the metadata scalars) is bounded by construction -- proportional to the
   protected-path count or the checkpoint count, never to a document's own
   byte size -- and stays inline exactly as before; only the two unbounded
   fields are replaced, by one bounded string.

   **Loading the bytes, and only when reconciliation actually needs them**:
   a new function, `load_pre_amendment_snapshot(repo_root, work_item_id,
   plan_path, registry_path, entry) -> tuple[str, dict]`, given one
   `amendment_history` entry, reads the pinned `blob` SHA for `plan_path`
   and for `registry_path` out of
   `entry["superseded_plan_approval"]["review_content_manifest"]` (a
   lookup by `path`, never a re-derivation of the manifest), retrieves each
   blob's bytes via `git cat-file -p <blob>` (a direct, content-addressed
   object read -- independent of any tree/commit walk, and correct
   regardless of whether `plan_path`/`registry_path` were ever renamed,
   since the manifest already pins the path they had at request time), and
   cross-checks each retrieved blob is reachable from
   `entry["pre_amendment_approval_commit"]` via `git ls-tree
   <pre_amendment_approval_commit> -- <path>` reporting the identical SHA
   (defense against a corrupted or force-rewritten ref pointing somewhere
   the manifest's own blob no longer lives) before decoding: the registry
   bytes are parsed as JSON to produce `pre_registry`; the plan bytes are
   decoded as UTF-8 to produce `pre_plan_text`. **If the blob cannot be
   retrieved, or the cross-check's `git ls-tree` disagrees, this raises a
   new, named `AmendmentPreSnapshotUnreproducibleError`, naming the path
   and the blob SHA it could not reproduce, rather than silently
   substituting empty content or crashing on an unhandled `git`
   failure.** This function performs Git subprocess I/O, so -- exactly
   like the `post_registry`/`post_plan_text` read this same subsection
   already places at `.claude/commands/approve-review.md` step 4c, never
   inside `workflow_state.py`'s own mutators -- it is called from that same
   impure step 4c, immediately alongside the existing
   `post_registry`/`post_plan_text` read, never from inside
   `apply_plan_approval` itself (D-Plan-Amendment-4 restates the call site
   precisely). This is what "load and verify those bytes only when
   reconciliation actually needs them" means concretely: the bytes exist,
   transiently, in process memory for the duration of one
   `/approve-review plan` invocation, and never again touch
   `WORKFLOW_STATE.json`.

   Nothing is deleted from `amendment_history` -- the bounded reference
   (`pre_amendment_approval_commit`, plus the blob SHAs already inside
   `superseded_plan_approval`) exists permanently, exactly as the inline
   snapshots used to, so a later reconciliation step (D-Plan-Amendment-4)
   still has a pre-amendment reference independent of the live
   (already-overwritten) registry/plan files, and a human auditing the item
   later can still reconstruct exactly what was approved and completed
   before the amendment -- now via `git show
   <pre_amendment_approval_commit>:<plan_path>` (or `git cat-file -p
   <blob>`) instead of reading a field directly, the same
   git-is-the-archive discipline `REVIEW_PROTOCOL.md`'s "recomputation is
   the authority" contract already asks of every other piece of reviewed
   content in this workflow. `resolved_at_plan_revision` starting `null`
   and being written exactly once, by reconciliation itself, is the
   explicit open-amendment marker D-Plan-Amendment-4 depends on: it
   replaces every "is the last entry's `superseded_plan_revision` the plan
   revision immediately prior" test this design originally used, none of
   which survive a `REVISE` verdict during the amendment's own plan review
   -- and a `REVISE` is the normal case in the two-stage protocol, not an
   edge case (B4).

   **`amendment_history`'s writer discipline, stated precisely** (revision
   3, I5 -- round 2 correctly found revision 2's stated invariant
   ("append-only") and the mechanism just described (reconciliation
   mutates the last entry's `resolved_at_plan_revision`) contradicting
   each other): the list is **append-only in its entries** --
   `/request-plan-amendment` is the sole writer of *new* entries, exactly
   as stated above, and no entry is ever removed or reordered -- **with
   exactly one write-once field per entry**, `resolved_at_plan_revision`,
   whose sole writer is reconciliation (D-Plan-Amendment-4) and which
   transitions `null` -> a concrete plan-revision integer exactly once,
   never back to `null` and never overwritten a second time. Every other
   field of an already-appended entry (`requested_at`,
   `superseded_plan_approval`, `checkpoints_snapshot`,
   `pre_amendment_approval_commit`, etc.) is immutable
   from the moment `/request-plan-amendment` appends it. This is the same
   single-sanctioned-writer discipline `publish_plan_revision` already
   enforces for `plan_revision` (`D-Plan-Revision-Publication`, `WFR-65`),
   applied to one field of one list entry instead of one top-level key:
   reconciliation (folded into `apply_plan_approval`'s own computation,
   D-Plan-Amendment-4 below) asserts
   `amendment_history[-1]["resolved_at_plan_revision"] is None` as its own
   first act and raises a new, named `AmendmentAlreadyResolvedError`
   rather than silently overwriting an already-resolved entry if the
   assertion fails -- the same "wrong state, refuse and name it"
   discipline D-Plan-Amendment-6 already applies to a re-run
   `/request-plan-amendment`.
3. Sets `amendment_base_commit` to the current `HEAD` -- immutable once
   set for this amendment round, the amendment-lane analog of the
   work item's own immutable `base_commit` (D-Plan-Amendment-5 discusses
   why this is scoped to bundle legibility only, not to any hashed field).
4. Writes `phase = "AMENDING_PLAN"`.

Nothing here touches the `checkpoints` map, the registry, or the mapping --
reconciliation is deferred to the *next* plan approval (D-Plan-Amendment-4),
never performed on a request that might still be rejected at review.
`MILESTONE_WORKFLOW.md`'s new `AMENDING_PLAN` section states explicitly
that completion accounting is provisional while an item sits in this
phase -- the live `checkpoints` map still reads all-`COMPLETE` under a
plan that is being rewritten, and only the next reconciliation resolves it
(O1); no new state is needed to say so.

### D-Plan-Amendment-4: re-entering plan revision/review, and reconciling checkpoints

No new plan-review machinery. `AMENDING_PLAN` is a valid resume phase for
`/milestone-plan`'s existing dual-mode branch (step 0), exactly like any
other non-terminal existing entry -- the command's own id-resolution logic
already resumes an existing `work_items[id]` entry by lookup, not by phase
allowlist. Step 3's `[2.1]` `publish_plan_revision` call is unchanged and
already does the right thing: it bumps `plan_revision`, recomputes
`review_content_id`, and writes `AWAITING_LOCAL_PLAN_REVIEW` for a `"2.1"`
item (or `AWAITING_EXTERNAL_PLAN_REVIEW` for a `"1"` item) -- regardless of
whether this is the item's first plan or its fourth amendment. The entire
two-stage local-then-manual-external review protocol
(`/review-plan`/`/record-manual-plan-review`/`/apply-plan-review`) and the
approval gate (`/approve-review plan`) run completely unmodified for an
amended plan. This is what makes the mechanism small: everything below
`AMENDING_PLAN` in the state machine is code that already exists and is
already correct.

**Checkpoint reconciliation** happens exactly once per amendment, **folded
into `apply_plan_approval`'s own computation itself, not as a new,
separately-guarded step** (corrected, revision 3, B3 -- revision 2's
placement was mechanically impossible: `PLAN_APPROVAL_DESTRUCTIVE_STEPS`
(`workflow_state.py:2217-2224`) is a `frozenset` of guard-lease step-name
strings consumed by `plan_approval_step_class`
(`workflow_state.py:2266-2271`), not a set of mutator functions, so
"`apply_plan_approval` is added to" it is not an operation that exists to
perform; and `.claude/commands/approve-review.md` step 4c states
normatively that "no `docs/ai-workflow/WORKFLOW_STATE.json` working-tree
write happens here or anywhere below" inside the plan-approval-commit
sequence -- the transaction's post-approval bytes are computed exactly
once, before that sequence begins, and pinned into the journal, never
re-derived -- so a reconciliation write placed inside that sequence would
be self-defeating: step 6.2's `plan_approval_state_matches_pre_transaction`
compare-and-swap (`workflow_state.py:3070`) would observe the
just-performed reconciliation write as "the state changed since the
journal captured it" and roll back every single amendment approval via
step 6b, deterministically).

The real insertion point is **before** step 4c's journal open, inside the
pure computation step 4c already performs there:
`open_plan_approval_journal` (`workflow_state.py:1891-1983`; corrected,
revision 10, O-R10-4) calls
`apply_plan_approval(pre_state, work_item_id, record, approval_now)`
*once*, to compute `expected_post_state`, and pins the result's bytes into
`journal["expected_post_state_b64"]`/`_sha256` before any Git staging.
`apply_plan_approval` (`workflow_state.py:9638`) is extended so that, when
the work item it operates on has an open amendment (`amendment_history`
non-empty and its last entry's `resolved_at_plan_revision` still `null`,
the same marker D-Plan-Amendment-3 defines), it also runs
`reconcile_checkpoints_after_amendment` as part of that same pure
computation and folds its outcome -- the rewritten `checkpoints` map, and
`amendment_history[-1]["resolved_at_plan_revision"] = plan_revision` --
into the state it returns, alongside `apply_plan_approval`'s real,
unchanged write set (`plan_approval`, `phase` set to `"IMPLEMENTING"`,
`state_revision`, `last_transition` -- `workflow_state.py:9646-9649`;
corrected, revision 10, I-R10-1). `plan_revision` is never one of them:
it stays `publish_plan_revision`'s alone
(`D-Plan-Revision-Publication`, `WFR-65`), and this fold must not become
a second writer of it. Naming `phase` here also makes explicit what was
previously unstated: a post-amendment `/approve-review plan` lands the
item at `IMPLEMENTING`, with the reconciled `checkpoints` map, in the
same pinned `expected_post_state` blob.

**The actual mechanism by which `post_registry`/`post_plan_text` reach the
computation, named and verified this revision (corrected, B2-new)**:
revision 3's claim that `record` already carries the post-amendment
registry/plan-text content is false, verified directly against the code --
`apply_plan_approval(state, work_item_id, record, now)`
(`workflow_state.py:9638-9650`) receives nothing but those four arguments;
`record` (`build_approval_record`, `:9466-9492`) is exactly ten metadata
keys, none of them file content, and its `review_content_manifest` field is
a flat list of `{"path", "exists", "mode", "blob"}` entries -- path plus
*blob hash*, not bytes, so nothing in `record` can be diffed for a
per-checkpoint content change. `apply_plan_approval` must stay a pure
`state -> state` mutator -- the same property this codebase already treats
as a deliberate design invariant of its mutators (`record_bundle_
generation`'s own docstring: "a read-only Git-inspecting query this
function itself deliberately stays free of") -- so the fix is not to let it
read `repo_root`-relative paths itself, but to widen what it is handed.

`apply_plan_approval`'s signature gains four new, optional, keyword-only
parameters: `post_registry: dict | None = None`,
`post_plan_text: str | None = None`, and, symmetrically -- widened this
revision (EXT-R6-I1) now that the pre-amendment values are no longer
stored inline (D-Plan-Amendment-3 above) -- `pre_registry: dict | None =
None` and `pre_plan_text: str | None = None`. For a work item with no open
amendment (the ordinary, non-amendment case -- every existing call site,
since this mechanism does not exist in the frozen v2.3.1 semantics those
tests exercise), all four stay `None` and are never consulted; the
function's behavior for that case is byte-for-byte unchanged, so no
existing call site needs to change. For a work item with an open amendment
(`amendment_history` non-empty, last entry's `resolved_at_plan_revision`
still `None`), all four must be non-`None` -- a `None` value here is an
internal-caller bug, not a data condition it silently tolerates, so it
raises a new, named `AmendmentReconciliationInputsMissingError` naming
which of the four is absent, rather than reading anything itself or
silently skipping reconciliation (amendment-prefixed, I-R32-1, to match
the rest of this design's new error family and to stay clear of the
module's pre-existing, unrelated `ReconciliationTableParseError`).

The read that produces `post_registry`/`post_plan_text` happens exactly
once, at exactly one call site: `.claude/commands/approve-review.md` step
4c, immediately before it calls `open_plan_approval_journal` -- the same
step that already reads `docs/ai-workflow/WORKFLOW_STATE.json`'s own
working-tree bytes fresh to build `pre_state`, so this is one more
instance of a read that step already performs, not a new kind of read.
`pre_registry`/`pre_plan_text` are read at that identical call site, in the
identical statement -- `load_pre_amendment_snapshot` (D-Plan-Amendment-3
above), not a re-read of the live `registry_path`/`plan_path`, which by
this point in `AMENDING_PLAN`'s lifecycle already hold the *post*-amendment
content.

**The actual expression step 4c uses, named and verified against
`.claude/commands/approve-review.md` as it really reads (corrected,
revision 5, B1-new)**: revision 4's claim that step 4c "already holds,
from step 1's `resolve_plan_stage_metadata` call, this work item's own
`plan_path`/`registry_path` (`PlanStageMetadata.plan_path`/`.registry_path`)
-- not re-derived" is false, verified directly against the command file.
Step 1 (`:69-174`; corrected, revision 15, O-R15-2 -- step 1 actually runs
through `:174`, step 2 opens at `:175`) calls `parse_review_feedback_binding_fields`,
`approval_gate_reachable`/`plan_approval_gate_reachable`,
`record_technical_review_block_pin`,
`implementation_provenance_interval_reachable` -- no
`resolve_plan_stage_metadata` call anywhere, and `resolve_plan_stage_metadata`
is not even a `workflow_state` symbol (it lives in
`workflow_fingerprint.py:914`). Step 4a's own resolution,
`plan = workflow_fingerprint.resolve_plan_stage_approval_commit_paths(...)`
(`:243`), calls `resolve_plan_stage_metadata` *internally* to build its
four-member path tuple (`workflow_fingerprint.py:1087`), but does not
expose that result to its caller: `PlanApprovalCommitPlan`'s only public
surface is `plan.paths` (an opaque 4-tuple, ordered only by that
function's own docstring), `plan.artifacts_declaration_path` and
`plan.artifacts_declaration_sha256` -- no `plan_path`/`registry_path`
attribute at all. Neither step 1 nor step 4a hands 4c a
`PlanStageMetadata`.

The honest mechanism: step 4c makes its own fresh call, `metadata =
workflow_fingerprint.resolve_plan_stage_metadata(repo_root, work_item_id)`,
immediately before the read below, and reads `metadata.plan_path`/
`metadata.registry_path` (`PlanStageMetadata`'s own named fields) --
one additional, cheap, idempotent resolver call inside step 4c, not a
value inherited from an earlier step. CP3's scope (section 5) includes
authoring this call at step 4c, alongside the `post_registry`/
`post_plan_text` read it feeds.

When this work item has an open amendment, step 4c reads
`plan_path`'s current working-tree bytes as `post_plan_text` and
`registry_path`'s current working-tree bytes, parsed as JSON, as
`post_registry` -- the exact bytes the two-stage review just approved.

**What actually binds this read to reviewed content (corrected,
revision 5, B1-new)**: revision 4's staging-based argument ("these files
are not `git add`-staged until step 5, which runs after the journal is
already open, so nothing between this read and journal-open can change
what it sees") does not support its own conclusion -- staging state has
no bearing on working-tree mutability. The real binding is step 2's fresh
`review_content_id` recomputation over the working tree: `plan_path`/
`registry_path` are both plan-stage protected paths, so any change to
either between the reviewed bundle and step 2 refuses the command outright
through the ordinary protected-path check every plan-stage command already
performs -- this is what establishes the bytes step 2 saw are the reviewed
ones, not anything about `git add`. That leaves one narrow window this
mechanism does not close: between step 2's recomputation and step 4c's own
read, a change landing there is **not** re-checked before the journal pins
the reconciliation outcome into `expected_post_state`. It is not
undetected forever -- step 6a's post-commit `verify_post_approval_manifest_match`
recomputes the committed projection and refuses (stop and report; the
approval commit already exists and is never silently amended away) if the
committed bytes do not match what was reviewed -- but for reconciliation
specifically, a same-window change is caught only *after* the approval
commit lands, not before the journal opens, which is a materially
different disposition from "nothing can change what it sees." **Decision:
this narrow window is accepted as-is** -- it spans only the handful of
synchronous steps between 2 and 4c within one command invocation, with no
user input pending in between, and closing it would mean adding a second
`review_content_id` assertion inside 4c, a new check this revision does
not introduce; the existing step-6a post-commit verification already gives
reconciliation the same protection every other plan-stage protected-path
change already relies on, just confirmed slightly later (after the commit,
rather than before the journal opens) than for the ordinary case.
`open_plan_approval_journal`'s own signature gains the identical four
optional keyword-only parameters, forwarded verbatim into its one internal
call, `apply_plan_approval(pre_state, work_item_id, record, approval_now,
pre_registry=pre_registry, pre_plan_text=pre_plan_text,
post_registry=post_registry, post_plan_text=post_plan_text)`
(`workflow_state.py:1931`) -- `open_plan_approval_journal` performs no read
of its own to obtain these four values; it is a pure pass-through for them,
exactly as it already is for `record`/`base_commit`/every other
caller-supplied argument.

This keeps the purity boundary exactly where the codebase already draws
it: the impure read lives in the command procedure
(`.claude/commands/approve-review.md`, which already performs impure reads
at steps 1, 2, and 4c's own `pre_state` read), never inside
`workflow_state.py`'s own mutators. `apply_plan_approval` remains a pure
function of its arguments; `open_plan_approval_journal` remains a thin,
journal-writing orchestrator whose own pre-existing impurity (reading Git
identity/HEAD) is unrelated to and unwidened by this change.

**Every call site this signature change touches, enumerated** --
`apply_plan_approval`: `workflow_integration_test.py:149,4247,4461,5329,
5448,5602`, `workflow_state_test.py:2818`; `open_plan_approval_journal`:
`workflow_acceptance_matrix_test.py:436,2569,2636`,
`workflow_integration_test.py:4204,5320`, plus
`.claude/commands/approve-review.md` step 4c itself, the sole production
caller. None of the existing test call sites require a code change: every
one calls for a work item with no open amendment, so the four new
keyword-only parameters simply default to `None` and are never consulted --
the change is purely additive (new keyword-only parameters, no existing
positional parameter repositioned), never a breaking one. CP2's own test
file adds the amendment-path call sites (see section 4, "Update-path
validation," scenario 25 -- the scenario that proves this expression
B1-new settled).

With the actual mechanism named, the purity, replay and compare-and-swap
arguments follow from it directly, not from the false premise revision 3
rested them on: `apply_plan_approval` needs no separate freshness check
and no new guarded step, because its only inputs are `pre_state` (which
already carries `amendment_history[-1]`'s bounded pre-amendment reference
-- `pre_amendment_approval_commit` plus the blob SHAs already inside
`superseded_plan_approval.review_content_manifest`, EXT-R6-I1's redesign
above), `record`, and now the four caller-supplied, already-fixed content
values (`pre_registry`/`pre_plan_text`/`post_registry`/`post_plan_text`) --
none of them re-read or re-derived after journal-open. The single pinned
`expected_post_state` blob already contains both the ordinary approval
mutation and the reconciliation outcome, so the existing journal/commit/
rollback machinery carries them together with **no new step, no new entry
in `PLAN_APPROVAL_DESTRUCTIVE_STEPS`, and no change to
`.claude/commands/approve-review.md`'s numbered sequence at all** -- CP2
extends `apply_plan_approval`'s own body and `open_plan_approval_journal`'s
signature; CP3's command-file work adds step 4c's four-value read described
above, still no new numbered step. A post-amendment approval therefore
passes step 6.2's
compare-and-swap exactly as an ordinary approval does: that check only
asks whether `WORKFLOW_STATE.json`'s live bytes still match
`pre_procedure_state_sha256` (i.e., no *other* writer raced this
transaction) -- a question entirely orthogonal to reconciliation, which
consults only the bounded pre-amendment reference inside `pre_state`
itself and the `pre_registry`/`pre_plan_text`/`post_registry`/`post_plan_text`
values step 4c read (the first pair via `load_pre_amendment_snapshot`, the
second via the working-tree read above) and passed in once, before the
journal was opened, never anything written after. A crash
between journal-open and commit resumes through the existing
journal/rollback path unchanged, with no new recovery logic required,
since reconciliation is now inside the one thing that path already
protects.

Gated on an **explicit open-amendment marker**, never on revision
arithmetic (B4): `amendment_history` non-empty and its last entry's
`resolved_at_plan_revision` still `null` (D-Plan-Amendment-3). Revision
arithmetic -- "`superseded_plan_revision` is the plan revision immediately
prior to the one just approved" -- silently stops matching after any
`REVISE` verdict at either plan-review stage, because `/apply-plan-review`
step 5 bumps `plan_revision` again on both its governing-version branches
(`publish_plan_revision`'s own docstring names this as a call site: plan
revision 1 -> amendment request (`superseded_plan_revision` 1) ->
`/milestone-plan` -> revision 2 -> `REVISE` -> `/apply-plan-review` ->
revision 3; at approval of revision 3 the old test compares 1 against 2
and is false). A `REVISE` is the normal case in the two-stage protocol --
this very review round is one -- so a predicate that only survives zero
`REVISE` rounds is not viable. The open marker survives any number of
`REVISE` rounds within the same amendment, because nothing writes
`resolved_at_plan_revision` until reconciliation itself runs at the
approval that finally lands, and it gives "never twice for the same
amendment" directly (the next approval finds no open entry) without a
second condition.

Reconciliation's pre-amendment inputs, redesigned this revision
(EXT-R6-I1) to close over a bounded reference instead of an inline
snapshot: step 4c reads them via one call,
`load_pre_amendment_snapshot(repo_root, work_item_id, plan_path,
registry_path, amendment_history[-1])` (D-Plan-Amendment-3 above), which
resolves `amendment_history[-1]`'s pinned `pre_amendment_approval_commit`
and the blob SHAs already inside its own
`superseded_plan_approval.review_content_manifest` into the exact
pre-amendment `plan_path`/`registry_path` bytes -- never a re-read of the
live `registry_path`/`plan_path`, which `/milestone-plan` step 3 has
already overwritten with the *post*-amendment content by the time this
runs, and never a stored copy inside `WORKFLOW_STATE.json` either. The
resulting `pre_registry`/`pre_plan_text` values are passed into
`apply_plan_approval` as two more caller-supplied, keyword-only arguments,
exactly parallel to `post_registry`/`post_plan_text` (B2-new, above) --
read exactly once by step 4c and passed in as plain arguments, never
re-read or re-derived by `apply_plan_approval` itself. All four inputs are
therefore fixed, by construction, at the single moment
`open_plan_approval_journal` computes `expected_post_state` and pins it
into the journal, before any Git staging and before this transaction's
first durable mutation. This is what makes the result deterministic and
replay-safe: reconciliation runs **exactly once** per approval attempt --
at journal-open time, computed fresh from those four fixed inputs -- and a
resumed/retried approval never recomputes it a second time against
possibly-different bytes; it replays the pinned `expected_post_state_b64`
blob from the journal instead, exactly like every other part of that
state, regardless of any commit landing between the retries
(D-Plan-Amendment-6 restates this same guarantee from the crash-recovery
side, and states explicitly that a retry re-loads rather than
re-snapshots). If `load_pre_amendment_snapshot` cannot reproduce the
pinned bytes, it raises `AmendmentPreSnapshotUnreproducibleError`
(D-Plan-Amendment-3 above) and step 4c refuses before
`open_plan_approval_journal` is ever called -- nothing is pinned, nothing
is staged, and the approval attempt can be retried once the underlying Git
condition (never expected in ordinary operation, since the blob is
reachable from `pre_amendment_approval_commit`'s own tree, permanently,
from the moment that commit was made) is resolved. **Stated honestly
(corrected this revision, I-R8-1)**: "retried once ... resolved" presumes
the condition *is* resolvable. If it is not -- history rewritten, a
shallow clone, or object corruption -- there is no in-band recovery at
all, for exactly the reason section 7's own no-abandonment stance
(I3-new) already gives: the `amendment_history` entry pinning this
reference is immutable, a second `/request-plan-amendment` refuses, and
`plan_approval.status == "SUPERSEDED"` keeps `implementing_entry_reachable`
refusing re-entry regardless of how many further plan revisions run. See
section 7's new exclusion bullet for the accepted disposition.

A new function, `reconcile_checkpoints_after_amendment(pre_registry,
post_registry, pre_plan_text, post_plan_text, checkpoints)`, computes, per
checkpoint id, one of three outcomes -- never a free-text operator claim.
(`pre_registry`/`pre_plan_text` are exactly the values
`load_pre_amendment_snapshot` returns, per the bounded-reference redesign
above -- this function's own signature and body are unchanged by that
redesign, since it already treated both as plain arguments, never as
`amendment_history` dict lookups of its own.)

- **id present in both, identical registry row** (same `name`/
  `depends_on`/`complexity`/`session_target`) **and identical checkpoint
  content** -- untouched. A `COMPLETE` checkpoint stays `COMPLETE`; its
  commits and provenance trailers are unchanged. "Identical checkpoint
  content" is a mechanical, per-checkpoint content hash, not the registry
  row alone (B6): every plan document written or amended under this
  mechanism marks each checkpoint's own design-decision prose with paired
  anchor comments, `<!-- CP<n> -->` immediately before and `<!-- /CP<n> -->`
  immediately after each block of prose that describes it -- a checkpoint
  may have any number of such disjoint, non-contiguous pairs (the plan's
  own many-to-many mapping of checkpoints to design-decision subsections,
  section 5's own parenthetical, already needs this: CP2 and CP3 both draw
  on D-Plan-Amendment-3/4/5, CP4 on D-Authored-Release-2/3/4, so a single
  contiguous span could not represent either); the content hash for a
  checkpoint id is computed over the concatenation, in document order, of
  every paired span with that id.

  **A note on where `pre_amendment_plan_text` comes from, for everything
  below (EXT-R6-I1's redesign, D-Plan-Amendment-3 above)**: every
  reference to `pre_amendment_plan_text` (and `pre_amendment_registry`) in
  this subsection and in section 4's scenarios is the string
  `load_pre_amendment_snapshot` returns, loaded on demand from
  `amendment_history[-1]`'s bounded reference -- never a stored
  `amendment_history` field of that name. The anchor grammar, its
  validation policy, and `reconcile_checkpoints_after_amendment`'s own
  logic below operate identically regardless of where that string came
  from, so none of it changes as a result of that redesign; only the
  provenance of the two strings does.

  **Anchor coverage and validation, redesigned this revision (B4-new)**:
  revision 2's "span to the next anchor or end of document" rule is
  withdrawn -- it made the *last* checkpoint's span silently absorb every
  trailing section (5-8, including this document's own self-review notes,
  which every amendment rewrites by definition), was undefined for a
  pre-amendment plan with zero anchors at all (this document's own state
  before this revision, and `workflow-controller`'s plan -- section 1's
  entire motivating case), and had no validator, so one forgotten or
  misspelled anchor silently reproduced the exact bug it exists to fix.
  Replaced by an explicit close marker per span (above) plus two
  independent, fail-closed rules:
  - **Zero anchors anywhere in `pre_amendment_plan_text`** (the whole
    document predates this mechanism, or predates any amendment through
    it) is the sanctioned legacy case, not a refusal: reconciliation
    cannot prove any checkpoint's content unchanged, so it never tries --
    every id present in both registries is conservatively treated as
    **checkpoint content changed** (the second outcome below), the same
    fail-closed direction "no information" must take, and never as
    "unchanged." This is what makes the mechanism usable for
    `workflow-controller`'s own real amendment, and for this document's
    own first amendment through it, without pretending a proof exists
    where none does.

    **The cost, stated explicitly (new, revision 4, I3-new)**: combined
    with the dependency-closure pass, this default is total for the
    motivating case -- `workflow-controller` at `SELF_REVIEWING_
    IMPLEMENTATION` with CP1-CP9 all `COMPLETE` would come out of its
    *first* amendment with all nine flipped to `NEEDS_REVALIDATION`, every
    one re-run through `/milestone-implement`. This is what makes the
    default *safe*; it is also, honestly, maximally expensive for the one
    case section 1 exists to serve, and an operator meets it on the very
    first real use. The natural mitigation -- add anchors to `plan_path`
    before requesting the amendment, so the pinned pre-text already
    carries them -- is **not available in-band** for a plan that predates
    this convention: `plan_path` is a plan-stage protected path, so editing
    it while at `IMPLEMENTING` stales `plan_approval`, and
    `implementing_entry_reachable`/`approval_is_current` then refuse, and
    the only mechanism that can legally reopen plan revision from
    `IMPLEMENTING` in the first place is `/request-plan-amendment` itself
    -- the very request that pins `pre_amendment_plan_text` zero-anchored.
    There is no sanctioned way to retrofit anchors onto an already-approved,
    already-`IMPLEMENTING` plan before its first amendment through this
    mechanism. **Decision: full revalidation is accepted as the deliberate,
    one-time price of a pre-existing plan's first amendment.** Every
    amendment *after* that first one benefits from fine-grained
    reconciliation, because `/milestone-plan`'s post-amendment plan review
    round is exactly where CP1/CP2's own paired-anchor convention gets
    adopted going forward (below) -- the pinned pre-text of the *second*
    amendment is the *first* amendment's own post-text, which by
    construction already carries anchors. This document's own future
    amendments, and every other `"2.1"` work item's plan document created
    once this mechanism ships, pay this cost zero times, since their very
    first plan revision already carries anchors from the start.
  - **Grammar, made total this revision (B5-new/I5-new)**: for a given
    checkpoint id, its anchors in a text are well-formed if every
    `<!-- CP<n> -->` is followed, before any other `<!-- CP<n> -->` or
    `<!-- /CP<n> -->` tag and before end of document, by exactly one
    matching `<!-- /CP<n> -->` -- a closed, non-nesting, per-id
    balanced-tag grammar with no undefined case: an open tag with no
    matching close anywhere before end of document (revision 3's gap --
    undefined for an unterminated final anchor) is malformed; a
    `<!-- /CP<n> -->` with no preceding matching open (revision 3's
    second gap -- the orphan close tag) is malformed; a `<!-- CP<n> -->`
    nested inside another open span for the same id is malformed
    (overlapping). Any number of disjoint, non-overlapping, well-formed
    pairs for the same id remains legal and is never malformed (revision 3
    wrongly listed "duplicated" alongside "overlapping" as a malformed
    trigger -- corrected: only overlapping/unmatched tags are malformed;
    multiple well-formed pairs for one id are the ordinary many-span case
    this section's own parenthetical above already requires).
  - **Post side: validated, and a refusal here is always actionable.**
    For `post_plan_text` (the plan document actually being approved,
    which by definition postdates this mechanism shipping, and which the
    author can always still edit and resubmit before approval), every
    checkpoint id present in `post_registry` must have at least one
    well-formed pair in `post_plan_text`, per the grammar above. A
    missing id is a refusal (`AmendmentAnchorCoverageError`); a malformed
    tag touching a present id is a refusal (`AmendmentAnchorMalformedError`)
    -- both raised by `apply_plan_approval` before it computes any
    outcome, never a silent partial reconciliation. This is what catches
    a forgotten or misspelled anchor on the approved side, where the old
    design's gap would have reintroduced B6.2 invisibly: a materially
    redefined checkpoint with no anchor pair now refuses the approval
    outright instead of silently comparing empty-to-empty as unchanged.

    **Where this refusal fires, and its cost, stated explicitly (new,
    revision 5, I2-new)**: this check runs inside `apply_plan_approval`,
    i.e. inside `open_plan_approval_journal`, i.e. at `/approve-review
    plan` step 4c -- after *both* `AWAITING_LOCAL_PLAN_REVIEW` and
    `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` have already completed for this
    amended plan. Recovery requires editing `plan_path` (a plan-stage
    protected path), which stales `review_content_id` and refuses the next
    `/approve-review plan` attempt at step 2; the real recovery is
    `/milestone-plan` (or `/apply-plan-review`) -> a new `plan_revision` ->
    a fresh two-stage local-then-manual-external review round -> approve.
    One full review round is spent per forgotten or misspelled anchor.
    This lands hardest on exactly the case section 1 exists to serve:
    under the zero-anchor legacy default above, `workflow-controller`'s
    *first* amended plan must carry a well-formed pair for all nine
    registry ids -- including the eight the amendment itself does not
    touch -- or the approval refuses, discovered only after the external
    reviewer has already reviewed it. This is not unrecoverable (`/milestone-plan`
    is legal from `AWAITING_PLAN_APPROVAL` -- `route_work_item`,
    `workflow_state.py:6700`, and `publish_plan_revision`,
    `:6771`, both refuse only a *terminal* phase -- so it is not the
    round-3 wedge again), but it is a real, avoidable cost this plan did
    not previously name.

    **Decision: the cost is accepted as-is, and the check's placement is
    not moved.** Moving the coverage/malformedness check earlier -- into
    plan-stage bundle generation, ahead of `AWAITING_LOCAL_PLAN_REVIEW`,
    the way `assert_stage_completeness`/`assert_test_results_consistent_with_plan_review_request`
    already gate a `"2.1"` item's bundle generation -- was considered and
    rejected for this release: the anchor grammar and its asymmetric
    pre-side-conservative/post-side-refusing validation are, per this
    round's own independent review, now structurally sound as designed,
    after three consecutive rounds of point-fixes to this exact mechanism
    each broke an adjacent invariant of it (O-R31-1: the prior citation to
    "section 8's revision-4 note" no longer resolves -- section 8 carries
    no per-revision transcript any more -- and is dropped rather than
    restated, since the claim it supported is independently established
    by this section's own three-round point-fix history above).
    Relocating the post-side check's call site would mean re-validating
    the same grammar a second time, against the same registry/plan-text
    pair, from a second call site with its own error-reporting contract --
    a second surface for the same three-round failure pattern to recur on,
    for a cost (one review round, on the anchor-typo path only, not on the
    ordinary path) this release judges acceptable rather than worth that
    risk. This release adds no new command, no automatic pre-review
    self-check, and no change to bundle generation to reduce the cost; a
    future release may revisit the placement once the anchor mechanism has
    proven itself stable in real use across more than one amendment round.
  - **Pre side: never a refusal, always conservative (corrected this
    revision, B5-new)** -- `pre_amendment_plan_text` is pinned, immutable
    bytes captured by `/request-plan-amendment` at request time
    (D-Plan-Amendment-3); nothing can ever edit it, and
    `/request-plan-amendment` refuses a second request against the same
    work item (`WrongPhaseForAmendmentRequestError`), so a refusal
    against it would be permanent and unrecoverable in-band -- exactly
    the unrecoverable wedge B5-new identified in revision 3's symmetric
    treatment of both sides (every `/approve-review plan` attempt raising
    the same error inside `open_plan_approval_journal`, forever, with no
    way to append a corrective second amendment request). A registry
    checkpoint id in `pre_registry` that lacks a well-formed pair in
    `pre_amendment_plan_text` -- whether because the id has *zero* pairs
    (the whole-document zero-anchor case, already sanctioned as legacy
    above) or a *malformed* one (a partially anchored plan, the case
    between zero and total coverage that revision 3 left as a hard
    refusal) -- is never a refusal: it is conservatively treated as
    **checkpoint content changed**, the identical fail-closed direction
    the zero-anchor rule above already established for "no information."
    `AmendmentAnchorCoverageError`/`AmendmentAnchorMalformedError` are
    therefore raised only for `post_plan_text`, never for
    `pre_amendment_plan_text` -- reserved for the side where a refusal is
    always actionable, never for the side that is pinned and can never be
    resubmitted. This closes the "partially anchored
    `pre_amendment_plan_text`" failure mode entirely, by construction:
    every possible shape of `pre_amendment_plan_text` -- zero anchors,
    total coverage, partial coverage, or malformed tags for some ids --
    now produces a defined, non-refusing outcome (a well-formed pair
    present means compare by content hash; anything else means
    conservatively treated as changed), so this is a total function over
    the pre-side's own possible shapes rather than another case-by-case
    patch: no future round of this mechanism can find a fourth pre-side
    shape that wedges the item the way the zero-anchor (round 2) and
    partial-coverage (round 3) cases each did in turn.

  This document's own future amendments (and any other `"2.1"` work item's
  plan document, once this mechanism ships) adopt the paired-anchor
  convention; CP1/CP2 implement the anchor-hash comparison and its
  validator.
- **id present in both, registry row changed, OR checkpoint content
  changed** -- if it was `COMPLETE`, its status is rewritten to a new
  value, `NEEDS_REVALIDATION` (added to `CHECKPOINT_STATUSES`, additive to
  the existing `{IN_PROGRESS, COMPLETE}` pair). `select_next_checkpoint`'s
  existing "not yet complete" test already treats any non-`COMPLETE`
  status as selectable once dependencies are satisfied, so this single
  vocabulary addition is sufficient -- no change to the selection
  algorithm itself. `/milestone-implement` re-runs its narrow check for
  that checkpoint before it can become `COMPLETE` again, through its
  ordinary, unmodified checkpoint-implementation path.

  **The re-run's second commit permanently breaks trailer-based
  discovery for that id, bounded and accepted as-is (new, revision 9,
  I-R9-1)**: `/milestone-implement`'s completion step writes a
  `Workflow-Checkpoint: <id>` + `Workflow-Work-Item: <work_item_id>`
  commit unconditionally for every checkpoint it completes
  (`.claude/commands/milestone-implement.md:183-186`), so a
  `NEEDS_REVALIDATION` checkpoint re-run through the ordinary path above
  produces a **second** commit carrying the identical trailer pair, both
  inside `discover_checkpoint_commits`' own `base_commit..head` search
  window for the life of the work item (D-Plan-Amendment-5's B5 keeps
  `base_commit` unchanged by an amendment). `discover_checkpoint_commits`
  (`workflow_state.py:1416-1437`, via `_discover_trailer_commits`,
  `:1371-1396`, its resolution loop specifically -- narrower than the
  `:1309-1397` full-function span section 2 above cites, deliberately, per
  O-R16-1) requires exactly one first-parent-ancestor candidate whose
  own committed `WORKFLOW_STATE.json` claims the id `COMPLETE`
  (`_checkpoint_commit_claims_complete`, `:1400-1413`); both the original
  and the re-run commit satisfy that predicate, so the search finds two
  verified survivors and raises `AmbiguousCheckpointTrailerError`,
  permanently -- `Workflow-Supersedes` is honoured only inside
  `discover_bundle_generation_record_commits`, never for the
  `Workflow-Checkpoint` family, and `_ambiguous_trailer_recovery_hint`
  says so explicitly (`:1301-1306`). Under the zero-anchor legacy default
  above, `workflow-controller`'s first amendment flips all nine
  `COMPLETE` checkpoints and re-runs all nine, so this is nine
  permanently ambiguous ids after one amendment for the motivating case.

  **Reachability bound, checked directly against the live call graph**:
  this is not operator-visible in the successor release as designed.
  `discover_checkpoint_commits` has no caller anywhere in
  `.claude/commands/` -- every mention (`milestone-implement.md:188`,
  `:192`, `bootstrap-workflow-v2.md:220`; corrected, revision 10,
  O-R10-2) is prose describing the trailer shape, never a call -- and its
  own `verify_checkpoint_completions` (`:1489-1503`) likewise has no
  production caller; `validate_state` does not call it, and
  `/accept-milestone` resolves completion through
  `resolve_own_registry_completion_status`/`committed_checkpoint_status`
  (`:6843-6881`, `:4265-4282` respectively -- **split into two spans,
  revision 16, O-R16-2**: through revision 15 both functions shared the
  single span `:4265-4282`, which is exactly `committed_checkpoint_status`
  alone; `resolve_own_registry_completion_status` is over two thousand
  lines away), which read `HEAD`'s own committed state directly and are
  unaffected by trailer ambiguity. `resolve_checkpoint_ownership`, the
  function that actually decides a `NEEDS_REVALIDATION` checkpoint's
  re-run (D-Plan-Amendment-7's audit paragraph below), never calls
  `discover_checkpoint_commits` either.

  **Decision: accepted as-is for this release, not designed around.**
  This mechanism makes a stated Workflow invariant
  ("`discover_checkpoint_commits` requires exactly one match per
  checkpoint id") false, permanently, for every repository that amends a
  plan with a previously `COMPLETE` checkpoint -- a real, durable cost --
  but it is inert today: nothing this release ships calls
  `discover_checkpoint_commits` or `verify_checkpoint_completions` on the
  re-run path, so no operator meets this ambiguity through any command
  this plan's own scope adds or touches. CP2's compatibility-audit
  deliverable (D-Plan-Amendment-7) is scoped to `APPROVAL_STATUSES`/
  `CHECKPOINT_STATUSES` *readers*; trailer-provenance discovery is
  neither, and this release does not extend that audit to it, design a
  `Workflow-Supersedes` extension for the `Workflow-Checkpoint` family, or
  give `_checkpoint_commit_claims_complete` a newest-candidate tie-break --
  each is a real design decision with its own frozen-semantics cost that a
  future release can take up once trailer-based checkpoint discovery
  actually gains a caller. No section-4 scenario is added for this finding
  on that basis, the same disposition already given to I2-new/I3-new/
  I-R8-1 for an accepted, stated-rather-than-silently-resolved risk.
- **id removed from the amended registry** -- dropped from the live
  `checkpoints` map (its history already lives in the amendment's own
  `checkpoints_snapshot`, recorded at request time, and permanently in git
  history via its commit trailers -- nothing is destroyed, only excluded
  from live completion accounting).

**Dependency-closure propagation** (B6.3): after the per-checkpoint
outcomes above are computed, reconciliation performs one forward pass over
the post-amendment registry's own order (already a valid topological
order, D-Selection rule 3): for each checkpoint whose resulting status is
`COMPLETE`, if any of its `depends_on` entries is not itself `COMPLETE` in
the resulting map (i.e., `NEEDS_REVALIDATION`, or absent because it was
just removed), that checkpoint is also rewritten to `NEEDS_REVALIDATION`.
A single forward pass suffices -- no fixed-point loop needed, since every
dependency of a checkpoint precedes it in that order. Without this pass,
`select_next_checkpoint` rule 2 only ever skips a checkpoint whose *own*
status is `COMPLETE`, so a `COMPLETE` checkpoint dependent on one just
flipped to `NEEDS_REVALIDATION` would stay `COMPLETE` and never be
reselected, and `/accept-milestone`'s coverage check would treat the item
as terminal on top of an invalidated dependency (B6.3).

A brand-new checkpoint id is simply absent from `checkpoints` and is picked
up by `select_next_checkpoint` exactly as any new checkpoint always is --
no special case needed. If `current_checkpoint_id` or
`last_completed_checkpoint_id` names a checkpoint the amendment removed,
reconciliation also nulls that field -- one line, removing a
dangling-reference class entirely (O3); this is safe unconditionally
regardless of O2's restriction, since a removed id can never legitimately
still be the item's own in-progress or last-completed checkpoint by the
time reconciliation runs.

Reconciliation's outcome (retained / needs-revalidation / dropped, by id,
including which flips came from the dependency-closure pass) is included
in `/approve-review plan`'s own output, so "it ran and legitimately did
nothing" is visibly distinct from "it never ran."

### D-Plan-Amendment-5: identity, bundles, and protected-path bindings across the amendment

- **Plan-stage `review_content_id`**: unchanged mechanism, computed against
  the new `plan_revision` exactly as today -- no new digest algorithm.
- **Plan-stage bundle base commit stays the item's own immutable
  `base_commit`, unconditionally, for every consumer** (B5). This design
  originally proposed overriding `resolve_plan_stage_metadata`'s base
  resolution with `amendment_base_commit` for an open amendment ("changes
  only which commit `prepare-ai-review.sh` diffs from, not how the digest
  is computed") -- that conclusion is false: `base_commit` is a **hashed
  field of the plan-stage projection**
  (`workflow_fingerprint.py:1461-1472`/`:1503-1512`), fed in by
  `compute_review_content_id_plan_stage_for_work_item`
  (`:1515-1531`), so changing what the resolver returns changes the
  digest. Worse, the digest's base has a second, independent source that
  bypasses the resolver entirely: `approval_is_current`,
  `implementing_entry_reachable` and `verify_post_approval_manifest_match`
  all take `base_commit` as an explicit caller argument
  (`workflow_state.py:1513-1637`), and `/milestone-implement` step 1a
  passes the work item's own immutable `base_commit`, never the
  resolver's output. Overriding only the resolver's half would compute
  the approval's digest at `amendment_base_commit` while
  `implementing_entry_reachable` recomputes at the original `base_commit`
  -- they could never match, `approval_is_current` would return `False`
  forever, and the item could never legally re-enter `IMPLEMENTING` after
  an amendment: the mechanism would fail at exactly the step it exists to
  enable (B5).

  Making the amendment-aware base the *single* source for every consumer
  instead was considered and rejected: it would mean also threading
  `amendment_base_commit` through `discover_plan_approval_commit`'s and
  `discover_approval_commits`' trailer search (both already take
  `base_commit` as a plain argument with no resolver call of their own),
  and it would **narrow** `assert_all_changed_paths_classified_worktree`'s
  fail-closed classification window on every amendment round for no
  safety benefit -- that check exists to catch an unclassified path
  anywhere in `base_commit..worktree`, and moving the base forward
  mid-amendment silently shrinks the window it watches. It would also make
  a historical approval's digest depend on mutable `amendment_history`
  content, contradicting `REVIEW_PROTOCOL.md`'s "recomputation is the
  authority" contract. So: **no consumer changes at all.** `base_commit`
  means exactly what it means today, for every stage, with or without an
  open amendment.

  **Consequence for the first post-implementation plan-stage digest,
  stated explicitly (I1-new, round 5)**: because the window above is
  deliberately not narrowed, the first plan-stage `review_content_id`
  computed after `/request-plan-amendment` -- the first `/milestone-plan`
  call following the request -- classifies the *entire*
  `base_commit..worktree` interval against this item's own **plan-stage**
  protected/excluded sets. `compute_review_content_id_plan_stage_for_work_item`
  (`workflow_fingerprint.py:1515`) resolves those sets and calls
  `compute_review_content_id_plan_stage`, whose first act (`:1455-1457`) is
  `assert_all_changed_paths_classified_worktree(repo_root, base_full,
  protected, excluded_paths, excluded_prefixes)` -- before any manifest is
  computed. For an item amended after several checkpoints have already
  landed -- `workflow-controller`'s own motivating case,
  `SELF_REVIEWING_IMPLEMENTATION` with CP1-CP9 complete -- that interval is
  every path all nine checkpoints touched, and each one must already be
  covered by this item's own **plan-stage** excluded sets, never its
  implementation-stage ones, which this call never consults. A single path
  outside every plan-stage entry (a new top-level directory, a new `docs/`
  subtree an implementation checkpoint created) fails this call closed with
  `UnclassifiedPathError`, naming that path, on the mechanism's very first
  command on its own motivating case. This is recoverable, and the remedy
  already exists in this repository rather than needing to be invented
  here: widen the item's plan-stage declaration through the
  "Protected-path / artifacts-declaration bindings" bullet later in this
  section, which names `REVIEW_PROTOCOL.md`'s existing "Repairing an
  artifact declaration after an approval" procedure (the `plan_stage`
  half) as the sanctioned amendment-time route -- the declaration file
  (`docs/ai-workflow/registry/<work_item_id>-artifacts.json`) sits under
  the excluded `docs/ai-workflow/registry/` prefix itself, so widening it
  at `AMENDING_PLAN` is a legal edit that stales nothing further.

  **The same window is not amendment-specific, stated explicitly (round
  27, B-R27-1)**: the paragraph above frames the classification window as
  something that first bites "the first plan-stage `review_content_id`
  computed after `/request-plan-amendment`", but `assert_all_changed_paths_classified_commit`'s
  caller is `approval_is_current(..., stage="plan", ...)`
  (`workflow_state.py:1562-1588`), which `implementing_entry_reachable`
  (`:1591-1612`) calls on **every** `/milestone-implement` invocation, not
  only the first (`.claude/commands/milestone-implement.md` step 1a's own
  words), against exactly this item's own `base_commit..HEAD`. So the
  window bites the ordinary, no-amendment-ever-requested `IMPLEMENTING`
  lane the moment any checkpoint's own commit introduces a path family
  outside this item's own plan-stage declaration -- no `/request-plan-amendment`
  need occur at all, and no `AMENDING_PLAN` re-approval is available to
  recover mid-implementation the way it is at `AMENDING_PLAN` itself. This
  is exactly the failure round 27's `B-R27-1` finding located: this
  item's own `plan-amendment-mechanism-artifacts.json` did not classify
  `docs/defects/`, `migration/`, `tools/`, `tests/`, `src/workflow_manager/`
  or `distribution/workflow/2.4.0/` -- path families CP1/CP4/CP5/CP6/CP7/CP8/CP9
  themselves write -- so `implementing_entry_reachable` would have raised
  `UnclassifiedPathError` from CP2's own step 1a onward, before any
  amendment was ever requested. The declaration is corrected as part of
  this round (section 5's nine checkpoint rows are now each covered; see
  `plan-amendment-mechanism-artifacts.json`'s `plan_stage.excluded_prefixes`/
  `excluded_paths`). **The coupling, stated once so it is not lost again**:
  a checkpoint row that names a new path family owes this item's own
  artifacts declaration the matching plan-stage (and, one stage later,
  implementation-stage) entry, in the same plan revision that adds the
  row -- not deferred to the first `/milestone-implement` step 1a that
  trips over the gap, and not conflated with the `AMENDING_PLAN`-only
  remedy the paragraph above describes, which presumes an approval to
  re-run and does not exist for this item's own ordinary lane.

  **The coupling, extended (round 28, B-R28-1/I-R28-1)**: naming the
  matching entry at both stages is not enough on its own if a plan-stage
  justification asserts an unchecked *reason* for deferring review to the
  implementation stage that `implementation_stage`'s own sets do not
  actually bear out. Round 27's own fix widened `plan_stage` correctly,
  but its `tools/` justification string asserted the family was "reviewed
  one stage later at
  `implementation_stage.protected_prefixes`/`protected_paths`" while, in
  the same breath, recording that `tools/migrate.py` was `excluded`
  there, and concluded "nothing here escapes review" from that pair --
  false, since `tools/migrate.py` is itself a named CP4 deliverable and
  `excluded` there meant it in fact escaped `technical_approval`'s
  binding at that stage (**I-R29-2**: the defect is not two labels
  disagreeing -- the string's own two halves already agreed with each
  other on the classification, `excluded`; what was false was the
  "nothing escapes review" conclusion drawn from that agreement).
  `CLAUDE.md`'s round-27 defect (**I-R28-1**) was a different one: its
  plan-stage justification asserted nothing about the implementation
  stage at all, citing instead a stale `WF4a-ii` gate-count rationale,
  while `CLAUDE.md` is itself a named CP9 deliverable. The rule is
  therefore: **a file a checkpoint row names as a deliverable is
  `protected` at the implementation stage; a file it names only as
  incidentally touched or explicitly left unmodified is `excluded`
  there; and the plan-stage entry's justification must not assert the
  other stage's classification without checking it against
  `implementation_stage`'s own sets directly.** **Extended (round 29,
  I-R29-1)**: a named deliverable may instead be deliberately excluded
  from `implementation_stage`'s binding as a third, explicit category --
  stated as such, with its reason, and recorded in section 7 as an
  accepted cost -- never left to read as an omission;
  `docs/defects/v2.3.1-002-no-plan-amendment-edge.md` (CP1) is this
  release's one instance, below. `tools/migrate.py` and `CLAUDE.md` are
  both corrected to `implementation_stage.protected_paths` this round
  (`plan-amendment-mechanism-artifacts.json`), verified directly against
  that file's own text rather than cited to a round record. **Extended again (round
  30, required acceptance criterion 4, I-R30-1)**: the rule above is not
  self-checking -- its own deliverable set must be *derived* from section
  5's own rows (walking each row's named file list), not re-typed by hand
  each round, and every member of that derived set must be checked at
  **both** its `implementation_stage` classification (`protected`, or the
  explicit third category above) *and* that its `plan_stage`
  justification does not itself assert the file is outside this work
  item's declared scope or otherwise contradict that classification.
  `README.md` (CP9) is the instance that motivated this: its
  `implementation_stage.protected_paths` entry was corrected at round 28
  (I-R28-1's own pass, which enumerated "all six now resolve `protected`"),
  but that pass checked only the classification, so
  it never read the `plan_stage` justification string, which still
  gave a contradicting, product-scope-shaped reason until corrected this
  round (`plan-amendment-mechanism-artifacts.json:22`).

  **What is, and is not, mechanically checked (corrected this revision)**:
  a prior revision of this paragraph credited a new script,
  `tests/verify_amendment_test_census.py`, with closing this rule's
  cross-stage half by construction. That script was authored outside
  `REVISING_PLAN`'s legal artifact set, did not in fact implement the
  check it was credited with (its derived population was the unrelated
  test-suite-reader census, never consulted by its own classification
  sweep), and has been removed rather than repaired or completed --
  building it during a plan revision was itself the defect (round 31,
  I-R31-2/I-R31-3). What *is* mechanically checked, today, without any new
  tool: `assert_all_changed_paths_classified_worktree`
  (`scripts/workflow_fingerprint.py`) already fails closed,
  `UnclassifiedPathError`, on any changed or untracked path this item's
  `plan_stage` declaration does not name, every time a plan-stage bundle
  is generated; the implementation-stage counterpart
  (`classify_path_implementation_stage`, walked by
  `compute_review_content_manifest_implementation_stage_worktree`) fails
  closed the same way at implementation-stage bundle generation. Both are
  existing, already-running Workflow machinery -- no part of this
  revision changes either. What neither one checks, and what therefore
  stays a rule a reviewer re-applies by hand each round exactly as rounds
  28-30 did: that a name classified `excluded` at one stage does not
  contradict `protected` (or the explicit third category above) at the
  other. That cross-stage comparison is reviewed against
  `plan-amendment-mechanism-artifacts.json`'s own text at every plan
  review round; it is not, and this revision does not claim it is,
  closed by construction.

  The genuinely new piece of plumbing is purely presentational instead.
  The motivating problem -- diffing the amended plan against a
  `base_commit` that is by now many checkpoints behind `HEAD` buries the
  plan-stage edit inside the whole implementation diff, for a human
  reading `DIFF.patch` -- is real, but it is a legibility problem, not an
  identity problem. `scripts/prepare-ai-review.sh`, when generating a
  plan-stage bundle for a work item whose `amendment_history`'s last entry
  is open (`resolved_at_plan_revision` still `null`, B4), additionally
  writes `AMENDMENT_DIFF.patch` -- `git diff <amendment_base_commit>..HEAD`
  restricted to the plan-stage protected paths, for reviewer convenience
  only.

  **Placement, corrected this revision (B5-new)**: revision 2 wrote it to
  `<bundle_dir>/AMENDMENT_DIFF.patch` and claimed it was "never hashed" --
  false against the actual code: `compute_bundle_id`
  (`workflow_fingerprint.py`) hashes **every** file under `bundle_dir` via
  `bundle_dir.rglob("*")`, keyed by relative path, with only `MANIFEST.md`
  itself normalized out (`REQUIRED_BUNDLE_FILES = frozenset({"MANIFEST.md"})`);
  every other file, `AMENDMENT_DIFF.patch` included, both participates in
  `bundle_id` and is scanned by `_reject_foreign_bundle_id_field`. Worse,
  the file's very *presence* tracked mutable work-item state
  (`amendment_history[-1].resolved_at_plan_revision is None`), so
  regenerating the identical plan-stage bundle before versus after
  reconciliation produced two different `bundle_id`s at one, unchanged
  `review_content_id` -- exactly the "a historical approval's digest
  depends on mutable `amendment_history` content" property this same
  subsection's `base_commit` paragraph, two pages above, already rejected
  as contradicting `REVIEW_PROTOCOL.md`'s "recomputation is the authority"
  contract.

  Fixed by moving the file **outside `bundle_dir` entirely**, to
  `.ai-review/<work_item_id>/AMENDMENT_DIFF.patch` -- a sibling of
  `current/` (`resolve_bundle_dir`'s own scoped root,
  `workflow_fingerprint.py:1887-1937`, corrected from `:1887-1938`,
  revision 12, O-R12-3 -- `:1938` is blank), not a descendant of it. Nothing
  that computes `bundle_id` or `review_content_id` ever walks that parent
  directory (`compute_bundle_id` takes `bundle_dir` itself as its root and
  globs only beneath it), so the file is now genuinely outside both hashed
  identities, exactly as `REVIEW_REQUEST.md`'s identity contract already
  states -- "never hashed" is true because the file is not inside the
  thing that gets hashed, not merely asserted. Its presence is still a
  function of the same open-amendment marker (unconditional, not
  regenerated per round beyond that), which is fine precisely because
  nothing downstream of it treats that presence as identity-bearing: a
  reviewer who opens the wrong (stale, or absent) copy sees a worse
  presentational diff, never a wrong verdict about what was reviewed --
  `DIFF.patch`/`review_content_id`, both still computed and hashed exactly
  as before, remain the actual reviewed identity. `prepare-ai-review.sh`
  regenerates it unconditionally on every plan-stage generation for a work
  item with an open amendment (deleting a stale copy when the amendment
  closes), so a bundle regeneration mid-round never leaves a stale
  `AMENDMENT_DIFF.patch` sitting next to a fresh `current/`.

  **The layout-discriminator interaction, stated rather than left implicit
  (new, revision 4, I1-new)**: "nothing that computes `bundle_id` or
  `review_content_id` ever walks that parent directory" is true but not
  the whole question -- `resolve_rejected_marker_path`
  (`workflow_fingerprint.py:2112-2135`, corrected from `:2112-2122`,
  revision 12, O-R12-2 -- that span was the `def` line plus the first
  third of the docstring and contained no call at all; the function's
  single `return` statement, the actual call, is at `:2135`) calls
  `resolve_bundle_dir` with no
  `stage`, which takes the compatibility branch keyed on
  `(repo_root / ".ai-review" / work_item_id).is_dir()` -- the *root*
  directory's mere existence, not `bundle_id`/`review_content_id` at all.
  Creating `.ai-review/<work_item_id>/AMENDMENT_DIFF.patch` necessarily
  creates that root directory, which moves a flat-layout item's `REJECTED`
  marker path from `.ai-review/REJECTED` to
  `.ai-review/<work_item_id>/REJECTED`. Moving the file under
  `<feedback_dir>` instead, as round 2's B5 suggested, does not avoid
  this: `resolve_feedback_dir`'s own scoped path,
  `.ai-review/<work_item_id>/feedback`, is itself a subdirectory of the
  same root `resolve_rejected_marker_path` gates on, so writing there
  creates the identical root directory and trips the identical gate --
  that alternative was checked directly against the code and rejected as
  not actually a fix, not merely left unconsidered. The interaction is
  real but inert in practice: `AMENDMENT_DIFF.patch` is only ever written
  during a plan-stage bundle generation, and the plan stage is scoped by
  construction (`resolve_bundle_dir(..., stage="plan")` always answers
  `.ai-review/<work_item_id>/current`, unconditionally) -- so the same
  generation run that would ever write `AMENDMENT_DIFF.patch` has already
  created `.ai-review/<work_item_id>/` itself, independent of whether that
  file exists, the moment it writes `current/`. `AMENDMENT_DIFF.patch`'s
  own presence therefore causes no *incremental* flip of
  `resolve_rejected_marker_path`'s answer in any reachable call sequence --
  it always arrives after the plan-stage bundle that already performed the
  identical flip. This holds for both `"1"` and `"2.1"` items alike, since
  `stage="plan"` scoping is unconditional on governing version.

  **Reaching the manual external reviewer, stated explicitly (new,
  revision 4, I2-new)**: `scripts/prepare-ai-review.sh`'s own archive step
  (`tar -czf "$ARCHIVE_TMP" -C "$ROOT_DIR" current`) tars only `current/`;
  `AMENDMENT_DIFF.patch`, a sibling of `current/` by this same paragraph's
  own fix, is not a member of that archive and so never reaches the
  `MANUAL_EXTERNAL_PLAN_REVIEW` stage, which works exclusively from
  `review-bundle.tar.gz`. Decision: the archive step is widened to also
  include `AMENDMENT_DIFF.patch`, conditionally, when present --
  `tar -czf "$ARCHIVE_TMP" -C "$ROOT_DIR" current $(cd "$ROOT_DIR" &&
  [ -f AMENDMENT_DIFF.patch ] && echo AMENDMENT_DIFF.patch)` (CP3's own
  scope, alongside the file's generation) -- rather than leaving it a
  local-reviewer-only convenience. This is safe and does not reopen
  B5-new: the tarball is a sibling of `current/` on disk, built by a
  separate, unhashed step, so bundling `AMENDMENT_DIFF.patch` into it
  changes nothing about what `compute_bundle_id`/`review_content_id`
  measure -- both still see only `bundle_dir`'s own contents, exactly as
  the fix above establishes. Both reviewers -- local, via the filesystem,
  and manual-external, via the archive -- now see the identical
  reviewer-convenience diff.

  **Marked unmistakably non-authoritative in the reviewer-facing text
  itself (new, revision 7, EXT-R6-O1)**: being outside
  `bundle_dir`/`bundle_id`/`review_content_id` by construction is a true
  fact about the archive's mechanics, but nothing previously told a
  reviewer that fact in the one place they actually read --
  `REVIEW_REQUEST.md`, right next to the `Reviewed bundle ID`-anchoring
  `review_content_id: <hex>` line itself. Fixed cheaply, with no new
  mechanism: the author appends one fixed line to every plan-stage
  `REVIEW_REQUEST.md` `scripts/prepare-ai-review.sh` generates,
  unconditionally, never gated on whether this generation's own work item
  currently has an open amendment -- "`AMENDMENT_DIFF.patch` (if present
  in this archive) is reviewer convenience only: it sits outside
  `bundle_dir`/`bundle_id`/`review_content_id` and is not covered by the
  Reviewed bundle ID above." -- so a reviewer opening `REVIEW_REQUEST.md`
  cannot mistake the patch for bundle-identity-covered evidence, regardless
  of whether they ever inspect the archive's own directory layout.

  **Made unconditional rather than gated on the open-amendment condition,
  corrected this revision (new, revision 9, O-R9-3)**: revision 7 gated
  this line's own presence on the same open-amendment condition that
  gates `AMENDMENT_DIFF.patch`'s generation -- exactly the shape of mutable
  work-item-state-tracking-via-file-presence this same subsection's
  B5-new fix, sixty lines above, rejects in terms for `AMENDMENT_DIFF.patch`
  itself (`amendment_history[-1].resolved_at_plan_revision is None`
  tracked via a file's presence inside `bundle_dir`). In practice this was
  benign -- `REVIEW_REQUEST.md` is left untouched once it already exists
  (`REVIEW_PROTOCOL.md:38-41`), so regenerating after reconciliation
  closes the amendment leaves the file, and therefore `bundle_id`, exactly
  as a first generation with the amendment already open left them -- but
  the plan stated the no-mutable-tracking invariant absolutely and then
  introduced an instance of its own shape without noticing. The line's own
  "(if present in this archive)" hedge already makes the sentence true for
  a bundle with no amendment and no `AMENDMENT_DIFF.patch`, so making the
  line's own generation unconditional removes the coupling for free,
  rather than merely documenting it as a noted exception.
  CP3 owns this alongside its existing
  `REVIEW_REQUEST.md`/`AMENDMENT_DIFF.patch`-generation scope (section 5);
  no validator enforces the line's presence -- it is author-written prose
  like every other `REVIEW_REQUEST.md` field, not a schema-checked one,
  matching this file's existing discipline throughout
  (`REVIEW_PROTOCOL.md`'s author-written-files list).
- **Implementation-stage `technical_approval`/`reviewed_implementation_head`**:
  untouched by a request or by an unapproved amendment in progress -- they
  keep describing whatever they described before, and remain valid for
  every checkpoint reconciliation leaves `COMPLETE`. They next move only
  when `/milestone-implement` reaches a fresh `SELF_REVIEWING_IMPLEMENTATION`
  after the amendment, through the existing, unmodified bundle-generation
  path.
- **Protected-path / artifacts-declaration bindings**: an amendment is
  simply a new, named, sanctioned *reason* to walk the existing "Repairing
  an artifact declaration after an approval" procedure
  (`docs/ai-workflow/REVIEW_PROTOCOL.md`) -- widening or narrowing a
  classification set mid-amendment is already a reviewed, digested fact
  under that procedure, and nothing here relaxes it. No new rule is added;
  the existing one already covers "intentionally changing scope," not only
  "found a mistake."
- **Approval commits and ancestry**: the amendment produces no commit of
  its own at request time (`/request-plan-amendment` is a state-only
  write, like `/review-plan`'s ledger write, not a Git-history event). The
  next approval commit `/approve-review plan` creates is an ordinary plan-
  approval commit, a normal descendant of `HEAD` at approval time --
  `discover_approval_commits`' existing first-parent trailer search finds
  it exactly as it finds any plan-approval commit, with no amendment-aware
  special case needed.

### D-Plan-Amendment-6: crash recovery, interruption, idempotence

No new locking primitive. `/request-plan-amendment` writes through the
existing `state_transaction`/`state_lock` (`fcntl.flock`, single atomic
publish) exactly like every other state writer -- its mutation either
lands completely or not at all. An interruption before the write leaves the
item exactly where it was (still `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION`,
safe to retry the request). An interruption after the write leaves the item
at `AMENDING_PLAN`, a real persisted phase `/milestone-plan`'s existing
resume logic already picks up by id -- no new resume path. Re-running
`/request-plan-amendment` against an item already at `AMENDING_PLAN` (or
any later phase) refuses with a new, named error
(`WrongPhaseForAmendmentRequestError`, naming the actual phase) rather than
double-appending to `amendment_history` -- the same "wrong phase, refuse
and name it" discipline every existing command already uses.

**Reconciliation's own crash-recovery story, corrected this revision to
match D-Plan-Amendment-4 (B1-leftover)**: reconciliation is **not** added
to `PLAN_APPROVAL_DESTRUCTIVE_STEPS` (`workflow_state.py:2217-2224`) --
that set is a `frozenset` of guard-lease step-*name strings* consumed by
`plan_approval_step_class` (`:2266-2271`), not a set of mutator functions,
so "`apply_plan_approval` is added to it" was never an operation that
exists to perform, and it gets no separate `state_transaction` of its own.
Reconciliation needs no locking or transaction machinery beyond what the
rest of plan approval already has, because it is folded into
`apply_plan_approval`'s own pure computation (D-Plan-Amendment-4), which
`open_plan_approval_journal` invokes exactly once, before any Git staging
and before this transaction's first durable mutation -- the crash-recovery
boundary is therefore identical to the rest of the plan-approval
transaction's, not a second one: a crash before journal-open leaves
nothing pinned (safe to retry, reconciliation has not run); a crash after
journal-open but before commit resumes through the journal's existing
`expected_post_state_b64`-replay path, which already carries the
reconciliation outcome folded in, so "both land or neither does" holds by
construction, with no new recovery logic (I3 -- naming the boundary rather
than asserting a separate one). It is computed **exactly once**, at
journal-open time, from `pre_registry`/`pre_plan_text` -- loaded fresh by
step 4c via `load_pre_amendment_snapshot` from `amendment_history[-1]`'s
bounded reference (`pre_amendment_approval_commit` plus the blob SHAs
already inside `superseded_plan_approval`, EXT-R6-I1's redesign,
D-Plan-Amendment-3 above) -- and the
`post_registry`/`post_plan_text` values step 4c reads and passes in at
that same moment (B2-new, D-Plan-Amendment-4) -- so a resumed/retried
approval **never recomputes** reconciliation a second time; it **replays**
the pinned journal blob instead, exactly like every other part of
`expected_post_state` -- and, because the inputs were fixed once at
journal-open rather than re-read live on each retry, this holds even if an
unrelated commit lands between the retries. A retry that does re-invoke
step 4c before the journal is found already open re-loads the identical
bytes from the same immutable, content-addressed blobs `pre_amendment_approval_commit`
already pins -- reusing the same pre-amendment references rather than
capturing a new snapshot of anything -- and fails closed with
`AmendmentPreSnapshotUnreproducibleError` rather than silently computing
against different bytes if that load cannot reproduce them (B6).

### D-Plan-Amendment-7: compatibility with existing v2.3.1-managed repositories

Every change is additive:

- **`AMENDING_PLAN`'s own compatibility audit, stated as CP6's own
  acceptance obligation rather than hand-enumerated here (restructured
  this revision -- this bullet was the recurring source of the
  review-apparatus churn a circuit breaker flagged at round 30, wrong or
  incomplete in at least eleven prior rounds)**: `AMENDING_PLAN` is
  additive to `KNOWN_PHASES`, and no existing phase is renamed, removed,
  or reinterpreted. `KNOWN_PHASES` (and the two other closed vocabularies
  below) are mirrored, hardcoded, inside the payload's own shipped test
  suites (`workflow_state_test.py`,
  `workflow_state_completion_obligations_test.py`,
  `workflow_integration_test.py` -- the same `distribution`-category
  artifacts this repository both dogfoods at `scripts/` and ships inside
  `distribution/workflow/<version>/payload/`), so every payload-suite test
  function that reads a file this release's checkpoints edit needs a
  disposition: does the edit disturb its assertion, or not.

  This plan does not build a tool to derive or run that disposition now,
  and does not predict it by hand either (a prior revision tried both in
  turn -- a hand-typed census, then a script authored mid-`REVISING_PLAN`
  that neither derived the right population nor was ever invoked by its
  own classification check, round 31, I-R31-2/I-R31-3 -- and both were the
  churn this bullet's own heading names). Instead: **CP6's own
  definition-of-done requires it to produce and pass this disposition, as
  part of CP6's deliverable, during `IMPLEMENTING`** -- every
  payload-suite test function whose read set intersects a path this
  release's checkpoints touch must be identified and actually run against
  the finished overlay diff, reported green or an already-documented red
  in `migration/portability_exceptions.json`, before CP6 can complete.
  This is legitimate as a plan-stage statement of an obligation still to
  be discharged in `IMPLEMENTING`: it does not require the check to exist
  or to have been run yet, and it authors no new script, test file, or
  generator as part of this plan revision. Whether CP6 discharges it by
  reading the three suites directly or by some mechanism it builds inside
  its own legal `IMPLEMENTING`-phase scope is CP6's own implementation
  choice, not something this plan revision needs to settle.

  The authoring decisions this compatibility question actually turned on
  are declared once, in section 5's CP2/CP3 rows, not repeated here:
  `/request-plan-amendment <child-id>` is reachable from
  `apply-functional-review.md`'s broad-remediation branch;
  `/request-plan-amendment.md` carries the standard "Enter the
  `AMENDING_PLAN` state" preamble every other phase-writing command opens
  with; it names `scripts/prepare-ai-review.sh` in a state-only,
  generator-mention-only capacity (never `_GENERATION_DRIVING_COMMANDS`);
  and `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`'s "whole plan lane persists
  exactly three phases" claim gains a scoping sentence excluding this
  re-entry phase. `/request-plan-amendment` is also a censused state
  writer under this repository's own `STATE_WRITER_SURFACE_PREFIXES`
  convention and declares `state_writer: true`; it is deliberately left
  off `REVIEW_SUBJECT_ROSTER` (it is not the subject of any review bundle
  or verdict, the same precedent `recover-implementation-provenance.md`
  already sets), a decision CP2/CP3 record explicitly rather than leaving
  the omission unaddressed.
- **`CHECKPOINT_STATUSES`'s own compatibility audit, given the same terms
  as `APPROVAL_STATUSES`'s (new, revision 4, I4-new)**: `NEEDS_REVALIDATION`
  is additive to `{IN_PROGRESS, COMPLETE}`, but `CHECKPOINT_STATUSES` has
  more readers than `APPROVAL_STATUSES`, and several are load-bearing --
  `_checkpoint_status_at_commit` (`workflow_state.py:3636-3640`, whose
  membership test decides decidable vs `undecidable` and which
  D-Plan-Amendment-7's own downgrade paragraph below relies on for its
  analysis -- the two paragraphs cross-reference for that reason),
  `_validate_work_item`'s checkpoint validation (`:11202-11203`, called
  from `validate_state` (`:11240`) at `:11298`) and `validate_state`'s own
  dependency invariant (`:11447-11453`: every `COMPLETE` checkpoint's
  `depends_on` entries must themselves be `COMPLETE`, else
  `CheckpointDependencyNotCompleteError` -- the exact invariant
  D-Plan-Amendment-4's dependency-closure pass exists to preserve, stated
  here as the correctness obligation that pass discharges, not merely as
  selection-algorithm ergonomics; corrected, revision 10, O-R10-1 -- the
  invariant lives in `validate_state`'s own registry-driven block, not
  `_validate_work_item`'s), `complete_checkpoint`'s all-complete
  transition (`:3254`), `select_next_checkpoint` (`:3093-3162`; corrected,
  revision 11, O-R11-2), and
  roughly ten other `== "COMPLETE"` comparisons.

  **`resolve_checkpoint_ownership`, added to the audit (new, revision 5,
  I1-new)**: `workflow_state.py:5204-5334` -- the function
  `/milestone-implement` step 1c calls, and therefore the function that
  decides what actually happens when a `NEEDS_REVALIDATION` checkpoint is
  attempted -- was missing from the enumeration above, verified directly
  against its code. Its behavior for a third status is two-branched, both
  now stated explicitly rather than left to the audit to discover:
  **uncontended** (no claim, nothing locally `IN_PROGRESS`, `:5235-5240`)
  returns `FRESH` for the selected id -- a `NEEDS_REVALIDATION` checkpoint
  re-runs cleanly, and this is the mechanism's central success path, the
  one every reconciliation outcome above exists to feed; **a self-owned
  claim outstanding with nothing locally `IN_PROGRESS`** (`:5287-5331`;
  corrected, revision 11, O-R11-4)
  falls to `raise CheckpointOwnershipStateMismatchError(...)` when
  `local_status` is a concrete, non-`COMPLETE` status -- post-amendment,
  that is `NEEDS_REVALIDATION`, reachable only when reconciliation itself
  flips an existing `COMPLETE` entry -- the raise itself is `:5327-5331`
  (corrected this revision, O-R9-1: revision 8's own O-R8-4 fix attached
  the right substance to the wrong span, `:5304-5330`, a truncated copy of
  the raise plus the `local_status == "COMPLETE"` branch that precedes
  it); neither the
  `CONTINUE_CLAIM` crash window (`local_status is None`, `:5290-5302`) nor
  the automatic-release `COMPLETE` branch immediately above it
  (`:5304-5325`) reaches this raise, and D-Plan-Amendment-1's widened
  precondition already excludes both at request time (correcting the
  attribution here, O-R8-4; the design itself is unchanged). Also stated
  explicitly: `checkpoint_origination_provable`/`identity_reference_admits`
  are **not** on this re-run path at all -- `checkpoint_origination_provable`
  is called only from `adopt_claim`, which `resolve_checkpoint_ownership`
  reaches only via the `local_in_progress is not None and claim is None`
  branch (`:5256-5271`), never via the uncontended `FRESH` path a
  `NEEDS_REVALIDATION` checkpoint actually takes. So a `NEEDS_REVALIDATION`
  checkpoint is a `FRESH` start, not a blocked re-origination -- the single
  most load-bearing "this design works at all" fact in the whole
  reconciliation story, now stated rather than left implicit. CP2's
  compatibility-audit deliverable is therefore extended to
  `CHECKPOINT_STATUSES` readers on the same terms as `APPROVAL_STATUSES`'s: the complete call-site list is
  the audit's own produced output, not pre-announced here -- every site
  read so far treats a third value in the safe direction (a non-`COMPLETE`
  status is either already selectable or already excluded from the
  all-complete/dependency-satisfied checks), which is the audit's likely
  conclusion, not a substitute for actually running it.
- `amendment_history` (default `[]`) and `amendment_base_commit` (default
  `null`) are new, optional work-item fields, read with `.get(...,
  default)` everywhere the successor's code touches them -- a
  `WORKFLOW_STATE.json` produced by v2.3.1, which contains neither key,
  is valid input and behaves exactly as before until the *first* amendment
  is requested against it.
- `docs/ai-workflow/WORKFLOW_STATE.json`'s own `schema_version` (currently
  `1`) is not bumped: nothing about the additive shape requires readers to
  distinguish "old" from "new" state files structurally, only key-by-key.
- **Downgrade posture, stated explicitly (new, revision 3, I4-leftover)**:
  downgrading a repository from the successor release back to `2.3.1` is
  **unsupported**, and the consequence is stronger than a validator
  rejection. `_checkpoint_status_at_commit`
  (`workflow_state.py:3564-3640`) maps any status value outside
  `CHECKPOINT_STATUSES` to `"undecidable"`; a downgraded repository's
  installed `workflow_state.py` no longer contains `NEEDS_REVALIDATION`
  in its own `CHECKPOINT_STATUSES`, so any *already-committed*
  `WORKFLOW_STATE.json` state written while a checkpoint held that status
  reads as undecidable, permanently, at the commit that wrote it (git
  history does not change on downgrade).
  `checkpoint_origination_provable` (`workflow_state.py:3643-3706`;
  corrected, revision 11, O-R11-3) raises
  `CheckpointOriginationUnprovableError` the moment its scan reaches such a
  commit, wedging checkpoint resume for that id with no in-band escape
  short of the explicit, evidence-bound
  `authorize_identity_reference_gap` operation. The same applies to
  `plan_approval.status == "SUPERSEDED"` reaching a downgraded
  `validate_approval_record`, which rejects a status outside its own
  closed `APPROVAL_STATUSES` set outright. So: a repository that has ever
  requested an amendment, or has any committed checkpoint that ever held
  `NEEDS_REVALIDATION` or plan approval that ever held `SUPERSEDED`, must
  not run `workflow_manager update --release-version 2.3.1` (or any
  future downgrade path) against itself again -- CP4/CP9 document this as
  an explicit operator-facing warning, and CP9's downgrade section states
  the specific failure mode above rather than leaving it to be discovered.
  No code change is required to *enforce* the restriction in this
  release (there is no downgrade command to gate); stating the posture is
  the deliverable.
- A v2.3.1-managed repository is completely unaffected until it runs
  `workflow_manager update` to the successor release -- before that, its
  installed `scripts/workflow_state.py` has no knowledge of any of this,
  exactly as the hard rule (`distribution/` and any installed v2.3.1 copy
  are never edited in place) requires.
- `/request-plan-amendment` is itself a censused state writer under this
  repository's own `STATE_WRITER_SURFACE_PREFIXES = (".claude/commands/",
  "scripts/")` convention (`workflow_state.py:7114`) -- both as a command
  file and through the new `workflow_state.py` functions it calls, each of
  which needs the mandatory `state_writer:` declaration
  (`_STATE_WRITER_DECLARATION_RE`, `:7116`, which admits exactly
  `true|false|"publisher"`) and **declares it `true`** (**stated
  explicitly, revision 16, O-R16-4**: through revision 15 this bullet
  said only that the declaration was needed, not its value, while this
  audit's own `_declared_state_writer_false`'s-own-census place above
  (**relabelled from the ordinal "tenth place", revision 18, I-R18-1**,
  same reason) already depended on the value being
  `true` specifically, crediting this bullet as the place that decided
  it; this is that decision, made here for the first time) and must be
  passed over by the `WFO-STATE-SERIALIZATION` closure verifier
  (**corrected, revision 19, O-R19-1**: through revision 18 this read
  "must pass over by," garbled) along with the rest of the
  new writers this release adds. CP2 (the `workflow_state.py` additions)
  and CP3 (the command file) both own this explicitly (I1) -- see their
  expanded scope in section 5.

  **The second, separate command-file census, deliberately left alone
  (new, revision 11, O-R11-5)**: `.claude/commands/` also has a second
  hand-maintained roster distinct from the `state_writer:` one above --
  `REVIEW_SUBJECT_ROSTER` (`workflow_state.py:7310-7325`) and its own
  `review-subject:` declaration -- and no test derives that roster from
  disk the way `test_the_operator_reference_command_count_matches_reality`
  derives the command count, so a new command left off it fails nothing.
  `/request-plan-amendment` is deliberately left off `REVIEW_SUBJECT_ROSTER`:
  it is not the subject of any review bundle or verdict the way
  `/approve-review`/`/review-plan`/`/review-implementation` etc. are --
  it is a user-authority command that writes state directly, the same
  shape `recover-implementation-provenance.md` is already precedent for
  being deliberately left off this same roster
  (`workflow_state.py:7280-7291`, corrected from `:7285-7292`, revision 12,
  O-R12-4 -- the prior span began mid-sentence at `:7285` ("`stage:` field
  over a bundle directory it did not itself generate"), omitting `:7280-7284`
  where the file is actually named, and ran on to `:7292`'s bare comment
  line). CP2/CP3 record this decision explicitly
  rather than leaving the omission unaddressed, alongside the
  `state_writer:` census obligation above.
- This repository's own installed Workflow copy (its `scripts/`, per
  `CLAUDE.md`) is **not** updated to the successor release as part of this
  work item -- disposable-repository validation only (section 4). Stated
  explicitly rather than left ambiguous (O4).

### D-Plan-Amendment-8: routing against the frozen-semantics hard rule

`CLAUDE.md`'s hard rule -- "Never modify frozen Workflow semantics. If
migration surfaces a genuine upstream defect, write it up under
`docs/defects/` and stop there. Repairing it is a Workflow release's job,
not this repository's." -- was written for the *migration* half of this
repository's job (extracting an existing upstream tag byte-for-byte), and
its existing precedent, `docs/defects/v2.3.1-001-host-history-coupled-tests.md`,
matches that exactly: documented, not repaired, because repairing frozen
`2.3.1` in place is out of bounds here.

This work item is different in kind, not merely a bigger instance of the
same thing. Frozen `2.3.1` genuinely has no transition out of
`IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` back into plan revision
(section 1), which by the hard rule's own test is "a genuine upstream
defect" -- but this plan does not stop at documenting it. It has this
repository *author the fix*, as a second, authored Workflow release
(section 3), precisely because `repflow-android` at any tag has no such
release to extract and there is no other upstream source the fix could
come from. That is a deliberate, reasoned departure from "repairing it is
a Workflow release's job, not this repository's" -- read literally, this
repository is not supposed to author a Workflow release at all. The
departure is justified (this repository already needs
`tools/build_release.py`-shaped tooling the moment any authored release
exists, per D-Authored-Release-1's own reasoning for why `tools/migrate.py`
cannot produce one), but it must be stated as a departure, not left as an
implicit tension (I4).

CP1 accordingly opens `docs/defects/v2.3.1-002-no-plan-amendment-edge.md`,
in the same shape as `v2.3.1-001`, documenting the missing
`IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` -> plan-revision edge as a
genuine frozen-`2.3.1` defect, and explicitly recording this work item's
disposition as "documented **and** an authored-fix shipped as a second
release" -- distinct from `v2.3.1-001`'s "documented, not repaired" -- with
the reasoning above, so the deviation from the existing precedent's
posture is visible at the defect record itself, not only in this plan.

## 3. Successor-release mechanics

### D-Authored-Release-1: why `tools/migrate.py` cannot produce this release

`tools/migrate.py` extracts a frozen upstream tag byte-for-byte
(`git show <commit>:<path>`); it has no notion of content that does not
exist upstream. The plan-amendment mechanism does not exist in
`repflow-android` at any tag -- it originates in this repository. Adding it
by hand-editing `distribution/workflow/2.3.1/` would violate "`distribution/`
is generated, not edited" and would silently break the frozen release's own
byte-identity guarantee (`tools/migrate.py --check`). A second, **authored**
release-production path is required, alongside the existing
upstream-extraction path, not instead of it.

### D-Authored-Release-2: the overlay convention

- `migration/overlays/<successor-version>/payload/` -- hand-authored files
  at their target-relative paths (mirroring
  `distribution/workflow/<version>/payload/`'s own layout): the new file
  `.claude/commands/request-plan-amendment.md`, and full replacements of
  every v2.3.1 payload file this release changes. **Widened, revision 24,
  I-R24-3**: named explicitly rather than left to the catch-all
  clause alone, the replaced set is `scripts/workflow_state.py` (the new
  functions and constants), `scripts/prepare-ai-review.sh` (the
  `AMENDMENT_DIFF.patch` generation), `.claude/commands/approve-review.md`
  (step 4c's reconciliation read),
  `.claude/commands/apply-functional-review.md` (the broad-remediation
  branch), `docs/ai-workflow/MILESTONE_WORKFLOW.md`,
  `docs/ai-workflow/REVIEW_PROTOCOL.md` and
  `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md` (the updated sections),
  `docs/ai-workflow/WORKFLOW_V2_PLAN.md` (**added, revision 25, I-R25-1**:
  CP1's own new `### D-Plan-Amendment-1..8` design-decision section,
  appended under the document's existing `### D-<name>` convention --
  section 5's CP1 row now names it explicitly, closing the gap I-R25-1
  found in CP1's previously-unenumerated payload row), and the
  three payload test suites' own updates, `scripts/workflow_state_test.py`,
  `scripts/workflow_integration_test.py` and
  `scripts/workflow_state_completion_obligations_test.py` -- eleven paths,
  which together with the new `request-plan-amendment.md` file above are
  the same twelve-path set the content-reading family's own restated
  subject (above) and section 5's CP1/CP2/CP3 rows use, so scenario 17's
  "agree in extension" claim holds by construction rather than by
  expanding this bullet's own catch-all clause. **Corrected, revision 22,
  I-R22-2**: this list no longer names `workflow_fingerprint.py` -- section
  5's CP4 note (below) already records that B5's fix eliminated the need
  for any `workflow_fingerprint.py` change at all (its one remaining piece
  of new plumbing, `AMENDMENT_DIFF.patch` generation, is a
  `prepare-ai-review.sh` change and lives in CP3 instead); the mention here
  was leftover text from before that fix landed, and this revision resolves
  the two statements in the one direction section 5's own CP4 note already
  took.
- `migration/overlays/<successor-version>/classification.json` -- same
  ruleset shape and category vocabulary `migration/classification.json`
  already defines (first-match-wins rules, `distribution`/`conformance`/
  etc.), scoped to only the overlay's own delta files.
- A new tool, `tools/build_release.py` (kept separate from
  `tools/migrate.py`, whose docstring and contract stay "frozen upstream ->
  distribution/" and are not touched): takes a base release version (e.g.
  `2.3.1`) and an overlay directory, verifies the base release against its
  own manifest, applies the overlay (new files added, existing files
  replaced byte-for-byte), and writes
  `distribution/workflow/<successor-version>/` with a freshly computed
  `manifest.json`. For any file the overlay *replaces* (as opposed to
  adds), it also records an additive per-artifact `overlay_delta` field --
  `{"base_sha256": "<the 2.3.1 payload file's own hash>", "diff_sha256":
  "<sha256 of a unified diff between the base file and the overlay
  file>"}` -- so a full-file replacement (e.g. the 601 KB
  `workflow_state.py`) carries a
  provenance record of *what changed*, not only what it changed to (I2).
  `tools/build_release.py` refuses to build if it cannot compute
  `overlay_delta` against the base file the overlay's own
  `classification.json` names. CP6's conformance extension adds a test
  asserting every replaced file's `overlay_delta.diff_sha256` reproduces
  from `base_release payload + the recorded diff` exactly -- byte-level
  provenance for the authored half of a release, matching the discipline
  `tools/migrate.py`'s own `manifest.json` already gives the upstream half
  (I2).
- `manifest.json` gains one additive top-level field, `provenance`,
  **alongside** the existing `upstream` key -- never replacing it (B3).
  `Release.__init__` reads `self.manifest["upstream"]` unconditionally
  (`release.py:89`), and `cli.py:83`, `install.py:352,472` and
  `installation.py:72` all read or persist `release.upstream` downstream;
  a manifest that dropped `upstream` would `KeyError` before any command
  (`bootstrap`, `update`, `status`, `verify`, `releases`) did anything. An
  authored release's `manifest.json` therefore keeps an `upstream` key
  whose value is the **base release's own** upstream triple (the `2.3.1`
  manifest's `{repository, tag, commit}`, copied forward unchanged by
  `tools/build_release.py`) -- an authored release is still, transitively,
  provenanced from that upstream tag, so this is not a fiction, only an
  incomplete one on its own. `provenance` is the field that actually
  distinguishes origin: `{"origin": "upstream"}` for every
  existing/future extracted release (`release.py`'s manifest reader
  defaults a missing `provenance` to `{"origin": "upstream"}` for backward
  compatibility with `2.3.1`'s own manifest, which predates this field),
  or `{"origin": "authored", "base_release": "2.3.1", "overlay_commit":
  "<this repository's own commit at build time>"}` for an authored one.
  `Release.__init__` gains `self.provenance = self.manifest.get(
  "provenance", {"origin": "upstream"})`, additive alongside
  `self.upstream`; `cli.cmd_releases` prints `release.provenance["origin"]`
  next to the existing upstream tag/commit line, so `workflow_manager
  releases` distinguishes an authored release from an extracted one at a
  glance; `install.py:352,472` and `installation.py:72` persist
  `release.provenance` into the installed target's own installation
  record alongside the existing `release.upstream` (additive there too,
  `.get(..., default)` read everywhere an older installation record
  without it is read), so `workflow_manager status` on an already-
  bootstrapped target can report which kind of release it was bootstrapped
  from. Every existing `release.upstream` reader keeps working unmodified
  for an authored release, reading the base release's own provenance
  exactly as it would for `2.3.1` directly (B3). This work is assigned to
  CP4 (redefined in place for this revision, section 5), alongside B1/B2's
  fixes -- it concerns `src/workflow_manager/`'s and `tools/migrate.py`'s
  own behavior in the presence of a second release, not the
  overlay/successor release's own payload content (CP2/CP3/CP5/CP6's
  scope).

  **`Installation`'s own `SCHEMA_VERSION` posture, stated explicitly (new,
  revision 3, I3-new)**: `Installation` (`installation.py:36,51-99`) is a
  second, independent schema from `WORKFLOW_STATE.json`'s, with its own
  `SCHEMA_VERSION = 1` and a `from_dict` that refuses on exact inequality
  (`data.get("schema_version") != SCHEMA_VERSION`) -- a floor check would
  admit an unknown-future record; this one refuses anything that is not
  exactly the version it understands, correctly, but that means a bump
  breaks every already-bootstrapped `2.3.1` target's own record outright.
  `provenance` is additive and every reader of it already defaults a
  missing key (`.get(..., default)`, above), so nothing about its shape
  requires a reader to distinguish "old" from "new" records structurally
  -- exactly the same reasoning D-Plan-Amendment-7 applies to
  `WORKFLOW_STATE.json`'s own `schema_version`, applied to this second
  schema. **`SCHEMA_VERSION` is therefore not bumped.** `provenance` takes
  a fixed position in `to_dict()`'s own documented fixed key order
  (`installation.py:66-76`) -- immediately after `upstream` and before
  `installed_at`, mirroring `manifest.json`'s own `provenance`-alongside-
  `upstream` placement (above) -- and `from_dict` reads it via
  `data.get("provenance", {"origin": "upstream"})`, the same default
  `Release.provenance` uses, so a pre-existing `2.3.1`-era installation
  record with no `provenance` key at all remains readable, unmodified,
  reporting `{"origin": "upstream"}` exactly as a freshly-bootstrapped
  `2.3.1` record would. CP4 owns this alongside the manifest-side
  `provenance` field; CP8's disposable-repository scenario 1 (normal
  `2.3.1` -> successor `update`) exercises the round-trip, and section 4's
  scenario 16 below adds an explicit `Installation.from_dict` unit test
  against a `2.3.1`-era record with no `provenance` key.
- `docs/MIGRATION.md` gains a short new section recording this second
  release's own provenance (what was authored, why, and against which base
  release), the same evidentiary discipline the existing Phase-A record
  already applies to the upstream extraction.
- `CLAUDE.md`'s "Adding a Workflow release" section gains a second,
  parallel procedure, "Adding an **authored** Workflow release," alongside
  the existing upstream-tag procedure -- both remain valid, chosen by
  whether the new release's content originates upstream or in this
  repository.

### D-Authored-Release-3: v2.3.1 stays frozen

`tools/build_release.py` only ever *reads* `distribution/workflow/2.3.1/`
(manifest-verified) and only ever *writes*
`distribution/workflow/<successor-version>/` -- a fresh, sibling directory.

`tools/migrate.py` itself needs a real, scoped fix before that claim holds
end to end (B1) -- verified false as this subsection originally stated
unconditionally: `tools/migrate.py:453-456` does `shutil.rmtree(REPO_ROOT
/ "distribution")` -- the **whole** committed tree, not
`distribution/workflow/2.3.1/` alone -- before every regeneration, and
`--check` compares a fresh extraction (`2.3.1` only) against
`_tree_digest(REPO_ROOT / "distribution")` (again the whole tree,
`tools/migrate.py:465-476`). So the ordinary `python3 tools/migrate.py`
regeneration `CLAUDE.md` instructs operators to run destroys
`distribution/workflow/<successor-version>/` outright, and `--check`
reports every one of that sibling's files `extra:` and exits 1 the moment
it exists -- CP6's stated verification method could not run as designed.
Both are made release-scoped instead, and the scope itself is derived from
`migration/classification.json`'s own `spec["workflow_version"]` -- the
exact field `migrate()` already reads at `tools/migrate.py:333` -- rather
than the literal `"2.3.1"` anywhere in `main()` (I1-new: both prescribed
scopings below named the literal in revision 2, defeating their own purpose
the moment a *third* release is ever added, since neither branch would
know to scope itself to the new version without an edit here):

- `main()` reads `spec = json.loads(CLASSIFICATION_PATH.read_text())` --
  the same file `migrate()` reads -- once, before either branch runs, and
  binds `version = spec["workflow_version"]`;
- the destructive step becomes `shutil.rmtree(REPO_ROOT / "distribution" /
  "workflow" / version)` -- an authored sibling directory is never touched
  by `tools/migrate.py`, regardless of what else is present under
  `distribution/workflow/`. The manifest write needs no separate scoping
  of its own (revision 2's parenthetical "(and the manifest write likewise
  scoped)" described nothing real, B1-new: `migrate()` already writes
  `manifest.json` inside `release_root = out_root / "workflow" / version`
  (`tools/migrate.py:337,416`), so once `out_root` stays `distribution/`
  unchanged, the manifest already lands under the correctly-scoped release
  directory with no code change);
- `--check`'s comparison is taken **at one common root on both sides**,
  corrected from revision 2's `_tree_digest(tmp)` against
  `_tree_digest(REPO_ROOT / "distribution" / "workflow" / version)` (B1-new:
  verified against the actual code and found unconditionally broken --
  `migrate(args.upstream, Path(tmp))` writes to `Path(tmp) / "workflow" /
  version`, so `_tree_digest(Path(tmp))`'s keys are `workflow/<version>/…`
  -- root-relative to `tmp`, not to the release directory -- while
  `_tree_digest(REPO_ROOT / "distribution" / "workflow" / version)`'s keys
  are `manifest.json`, `payload/…`, with no `workflow/<version>/` prefix at
  all; the two key sets are disjoint, so every path reports both
  `missing:` and `extra:` and `--check` exits 1 unconditionally, with or
  without an authored sibling present -- CP6's stated verification method
  could not execute as revision 2 specified it). The corrected comparison
  is `_tree_digest(Path(tmp) / "workflow" / version)` against
  `_tree_digest(REPO_ROOT / "distribution" / "workflow" / version)` --
  both sides rooted directly at the release directory itself, so an
  authored sibling is invisible to it in both directions -- it neither
  reports the sibling as `extra:` nor is capable of catching drift inside
  it (that is `tools/build_release.py`'s (CP5) and CP6's own job, via the
  overlay-delta verification above, I2). CP4 adds a digest-level unit test
  asserting both digests are computed at the same root (section 4's
  scenario 18 below) -- scenario 8's exit-status check alone cannot
  distinguish a same-root bug from a correct implementation, since a
  disjoint-key-set bug and a real drift bug both exit 1.

`CLAUDE.md`'s hard rule itself is amended alongside the procedure section
it already updates (D-Authored-Release-2's `docs/MIGRATION.md`/`CLAUDE.md`
bullet) -- "`distribution/` is generated, not edited. It is byte-identical
to the frozen release." becomes "Each `distribution/workflow/<version>/`
is generated, not edited. `2.3.1` is byte-identical to the frozen upstream
release; a later authored release is byte-identical to its own recorded
base-plus-overlay composition (I2)." -- so the repository's own stated
invariant stays true once a second, non-upstream release exists, instead
of becoming silently false the moment CP6 lands (B1). Release-scoped as
above, `tools/migrate.py --check`'s reproducibility proof for `2.3.1`
needs no further change and must still pass unmodified after this work
item lands (part of CP6's own verification) -- the corrected form of the
claim this subsection originally made.

**A second `CLAUDE.md` sentence needs the identical amendment, previously
missed (new, revision 5, I4-new)**: the hard-rule bullet above is not
`CLAUDE.md`'s only statement of this guarantee. Its "Before changing
anything" section separately states, verified directly against the current
file (`CLAUDE.md:73-74`), "`tools/migrate.py --check` proves `distribution/`
is still exactly what a fresh extraction produces" -- unqualified,
whole-tree phrasing that the release-scoping above (this subsection,
`shutil.rmtree`/`--check` rescoped to `distribution/workflow/<version>/`)
silently narrows without updating: once CP4 lands, `--check` proves only
that each individual `distribution/workflow/<version>/` matches its own
recorded composition, and a stray or hand-edited file directly under
`distribution/` (outside every release directory) becomes invisible to
both the destructive step and `--check` alike, where the unscoped
whole-tree form covered it. **Decision: the guarantee is genuinely
narrowed, and this repository's own stated rule is corrected to describe
the narrower, per-release scope precisely, rather than left to silently
stop matching CP4's own code (this is this repository's own operating
rule, not frozen `2.3.1` semantics, so amending it is this work item's own
deliverable, not a `docs/defects/` matter).** CP4's scope is therefore
extended to amend this sentence in the same pass as the hard-rule bullet:
"`tools/migrate.py --check` proves `distribution/` is still exactly what a
fresh extraction produces" becomes "`tools/migrate.py --check` proves each
`distribution/workflow/<version>/` is still exactly what a fresh
extraction (or, for an authored release, its recorded base-plus-overlay
composition) produces; it does not by itself prove no unrelated file
exists directly under `distribution/` outside every release directory."
No new whole-tree assertion is added to close that narrower residual gap
in this release -- the two release directories this work item ever
produces (`2.3.1`, `2.4.0`) are both covered end to end by their own
per-release `--check` runs plus CP6's conformance matrix, and a stray file
directly under `distribution/` (outside any `workflow/<version>/`
directory) is not a shape either `tools/migrate.py` or
`tools/build_release.py` has ever written in this repository's own
history -- stated as the accepted residual scope, not silently left
unstated the way it was before this correction.

### D-Authored-Release-4: existing workflow-manager suites stay pinned to `2.3.1`

`find_release(repo_root)` with no explicit version returns the newest
release present (`_version_key` orders `2.4.0` after `2.3.1`,
`release.py:212-219`; `find_release` itself is `:235-250`) -- exactly right
for `bootstrap`/`update`'s own
"current release" semantics, but wrong for every existing
workflow-manager conformance/inventory/byte-identity suite, each of which
pins to `2.3.1`'s own content today only because `2.3.1` happens to be the
only release that exists (B2). The moment `2.4.0` lands, `find_release`
called with `REPO_ROOT` and no version silently repoints every one of them
at authored content, and they fail for an unrelated reason (the
missing-`upstream`-shape assumption, byte-identity checked against the
wrong tag) instead of continuing to prove what they exist to prove --
`2.3.1`'s own byte-identity stops being tested at all, silently, exactly
when a second release makes provenance discipline matter most.

**The rule, stated rather than enumerated (corrected, revision 3,
I2-leftover)**: revision 2 named five files as if the list were exhaustive
and it was not -- verified against the actual repository, `find_release`
is also called with `REPO_ROOT` and no version at
`tests/test_migration_inventory.py:42,131`,
`tests/test_payload_bytes.py:27,66,121`,
`tests/test_bootstrap_e2e.py:59,124`,
`tests/test_no_live_state_imported.py:29,57,95`,
`tests/test_templates.py:63,78,106,134,153,185,207`,
`tests/test_conformance_suite.py:54`, `tests/test_internal_references.py:97`
and `tests/test_bootstrap.py:69` -- fifteen more call sites than revision
2 named, all with the same shape. Rather than maintain a second,
independently-drifting enumeration, CP4's obligation is stated as a rule:
**every `find_release` call whose first argument is `REPO_ROOT` (this
repository's own committed content, the only place `2.3.1`'s byte-identity
can be asserted) is pinned explicit -- `find_release(REPO_ROOT, "2.3.1")`
-- and CP4's own audit is a grep-verified, exhaustive pass over every
`find_release(REPO_ROOT` call site, not a pre-enumerated list that can go
stale the next time a suite adds one.**

**Exempted, by the same rule, not by exception (I2-leftover)**:
`tests/test_bootstrap.py:975-976` calls `find_release(self.manager_root)`
and `find_release(self.manager_root, "2.3.1")` against `self.manager_root`
-- a **synthetic, disposable test-fixture root** built with a fabricated
newer release (`2.3.2`) present, whose entire purpose (asserted at line
975: `find_release(self.manager_root).version == "2.3.2"`) is to prove the
newest-wins default *itself*, not to assert `2.3.1`'s byte-identity. Its
first argument is not `REPO_ROOT`, so the rule above never reaches it, and
pinning it (as revision 2's literal "pin the existing workflow-manager
suites' `find_release` calls to `2.3.1` explicitly" would, read literally)
would silently break the one test that exists to prove the default
behaviour `bootstrap`/`update` still rely on.

CP4 (redefined in place for this revision, section 5) applies the rule
above to every `REPO_ROOT`-rooted call site; CP6 adds the parallel
assertion set for the authored release (`2.4.0`'s own manifest shape, its
`provenance`/`overlay_delta` fields per I2/B3, `workflow_state.py`'s
successor content matching the overlay -- D-Authored-Release-5 below).
`bootstrap`/`update`'s own newest-wins default (`cli.py`'s existing
`--release-version` flag already lets an operator pin explicitly) is the
intended, unchanged behaviour once a second release exists -- this plan
does not change that default, only the workflow-manager test suites' own
use of the no-argument form against `REPO_ROOT` (B2).

**One named carve-out from "every `REPO_ROOT`-rooted call is pinned
explicit" (new, revision 4, B3-leftover)**: `tests/test_conformance_suite.py:54`
-- `cls.root = builder(find_release(REPO_ROOT), Path(cls._tmp.name) /
"repo")` inside `_SuiteRun.build` -- is the single line that decides which
release's payload `TestConformanceFixture`/`TestBootstrappedTarget` build
their disposable repository from, i.e. **what is under test**, as distinct
from `CI_SUITES`/`by_version` (D-Authored-Release-5 below), which decide
only what the assertions *compare against*. Pinning line 54 to a literal
`"2.3.1"`, as this rule would otherwise require, forecloses
D-Authored-Release-5's own CP6 obligation to run this exact class a
**second** time against `2.4.0`'s own payload -- CP4 and CP6 would then be
given contradictory instructions about the same statement. Line 54 is
therefore carved out of this rule by name, not folded into it: `_SuiteRun.build`
gains an explicit `workflow_version: str = "2.3.1"` parameter, and line 54
becomes `find_release(REPO_ROOT, workflow_version)` -- a parameter with a
`"2.3.1"` default (preserving CP4's own pinning intent for the run this
checkpoint owns) rather than a literal, so CP6's `2.4.0` run
(`cls.Run.build(build_conformance_repo, workflow_version="2.4.0")`, etc.)
is the same method, called with the other value, not a second copy of it.
`build` also stores `cls.workflow_version = workflow_version`, so the two
`CI_SUITES`-derived lines in the same file (`test_conformance_suite.py:90,139`,
currently `self.assertEqual(counts, dict(CI_SUITES))`) become
`dict(CI_SUITES[self.Run.workflow_version])`, reading the class's own
`workflow_version` -- see D-Authored-Release-5's per-release restructuring,
which already prescribes this shape for this file; this paragraph is what
makes `_SuiteRun.build` itself, the one line that was left out, consistent
with it.

### D-Authored-Release-5: conformance evidence for the authored release (new, revision 3, B2-leftover)

Revision 2's B2 fix (D-Authored-Release-4 above) is necessary but not
sufficient: pinning every `REPO_ROOT`-rooted workflow-manager suite to
`2.3.1` closes the only path by which the frozen conformance matrix could
ever run against `2.4.0`, and nothing in revision 2 reopened it. CP6's
"parallel authored-release assertion set" was manifest-shape and
`provenance`/`overlay_delta` byte-provenance assertions only -- none of
them execute a single line of the successor's own `workflow_state.py`,
even though the successor adds `AMENDING_PLAN` to `KNOWN_PHASES`, a third
member to `APPROVAL_STATUSES` and to `CHECKPOINT_STATUSES`, a new state
writer, and `reconcile_checkpoints_after_amendment` -- exactly the kind of
change the payload's own shipped test suites
(`distribution/workflow/2.3.1/payload/scripts/workflow_state_test.py` et
al., `distribution`-category artifacts -- **corrected, revision 16,
I-R16-2: not "24 `conformance`-category artifacts", the same
mislabel D-Plan-Amendment-7's own audit opening carried; see that
correction for the manifest evidence**) assert against, e.g.
`workflow_state_completion_obligations_test.py`'s
`test_exactly_four_known_phases_are_never_persisted` (asserts
`KNOWN_PHASES - persisted == NEVER_PERSISTED`) and
`workflow_integration_test.py`'s
`test_the_persisted_phase_table_is_exactly_the_writer_census` (asserts the
operator reference lists every `KNOWN_PHASES` member). Under revision 2,
nothing ever ran them against the release that changes what they assert
on.

**Decision: the authored release gets its own conformance run, not a
documented absence of one.** Two mechanical obstacles, both solved this
revision:

1. `CI_SUITES` in `tests/support.py:88-96` becomes **per-release**: a
   mapping keyed by `workflow_version`, `{"2.3.1": {<the current seven
   suite:count entries, unchanged>}, "2.4.0": {<the successor's own suite
   file names and their own exact test counts, computed once against the
   built `2.4.0` payload and committed alongside it>}}`.
   `test_every_suite_runs_the_frozen_number_of_tests` (and every other
   `CI_SUITES` reader in `tests/test_conformance_suite.py`) takes an
   explicit `workflow_version` and looks up `CI_SUITES[workflow_version]`,
   rather than reading the top-level mapping directly.
2. `migration/portability_exceptions.json` becomes per-release the same
   way: its top level gains a `by_version` mapping keyed by
   `workflow_version`, with `2.3.1`'s existing single-entry `exceptions`
   list moved under `by_version["2.3.1"]` unchanged, and `2.4.0` getting
   its own list (populated by whatever the successor's own new/changed
   payload tests need, if any -- possibly empty).
   `test_failures_are_exactly_the_documented_portability_exceptions` reads
   `by_version[workflow_version]` for the release under test, preserving
   the existing "not a subset, not a superset" equality contract per
   release rather than globally.

**Every reader of both constants, grep-verified rather than trusted from a
prior round's list (new, revision 4, B4-new)**: `tests/support.py`'s
`CI_SUITES`/`PORTABILITY_EXCEPTIONS` are imported by exactly two files --
`tests/test_conformance_suite.py` (`:29` the import; `:55`
`{suite: run_suite(cls.root, suite) for suite in CI_SUITES}` in
`_SuiteRun.build`; `:90`/`:139` `self.assertEqual(counts,
dict(CI_SUITES))` in `test_every_suite_runs_the_frozen_number_of_tests`/
`test_every_suite_still_runs_the_frozen_number_of_tests`; `:120` `for
record in PORTABILITY_EXCEPTIONS["exceptions"]` in `_expected_failures` --
all named individually rather than left to the general "already scoped
above" phrasing (round-4 O2, closed this revision), and by B3-leftover's
`_SuiteRun.build` fix) **and** `tests/test_bootstrap_e2e.py` (`:22`),
which revision 3 did not scope and which breaks in three places under the
restructuring as originally stated:
`:64` (`{suite: run_suite(cls.target, suite) for suite in CI_SUITES}`,
iterating what becomes a version-keyed mapping of mappings),
`:84` (`self.assertEqual(counts, dict(CI_SUITES))`, comparing against the
same), and `:48` (`for record in PORTABILITY_EXCEPTIONS["exceptions"]`,
`KeyError` the moment that list moves under `by_version`). Unlike
`_SuiteRun.build`, this file needs no parameterization -- both of its test
classes exist specifically to prove the real bootstrapper produces frozen
`2.3.1` behavior (`find_release(REPO_ROOT)` at `:59,124`, already pinned
to `"2.3.1"` explicitly by D-Authored-Release-4's own rule; there is no
`2.4.0` rehearsal analog for this file in this release's own scope) -- so
its three sites become fixed literal lookups: `:64`
`CI_SUITES["2.3.1"]`, `:84` `dict(CI_SUITES["2.3.1"])`, `:48`
`PORTABILITY_EXCEPTIONS["by_version"]["2.3.1"]["exceptions"]`. CP6's own
scope (redefined below) is stated as covering both files by name, not
"`tests/test_conformance_suite.py` and every other `CI_SUITES` reader,"
which is exactly the open-ended phrasing that let this file go unscoped
once already.

**Disambiguated from a same-named, unrelated constant (B4-new)**:
`tools/migrate.py:252` defines its own `CI_SUITES` -- a plain tuple of
suite filenames driving `render_ci_workflow` (`:263-269`), which produces
the CI template installed at
`templates/.github/workflows/workflow-conformance.yml` and is asserted
against the frozen upstream `ci.yml` by `tests/test_templates.py:214,225`
(`migrate.CI_SUITES`, always qualified by module, never imported bare --
so no name actually collides at any call site; the collision is only in
what a reader named "make `CI_SUITES` per-release" might assume). This
constant is **not** in scope for the per-release restructuring above: it
belongs to `tools/migrate.py`'s own upstream-extraction path (untouched by
this work item's `distribution/workflow/2.3.1/` output) and is a template
generator, not a test-comparison table. Its own successor-release
treatment is I6-new's own concern, addressed next.

**The authored release's own installed CI template (new, revision 4,
I6-new; ownership split corrected, revision 5, B2-new)**: if `2.4.0`'s
payload ships new or renamed test suites -- D-Authored-Release-5 already
assumes it might, since it budgets `2.4.0` its own `CI_SUITES["2.4.0"]`
counts -- nothing in revision 3 rendered a `2.4.0` template naming them;
`tools/build_release.py`'s overlay-apply step (D-Authored-Release-2, CP5)
copies forward any payload file the overlay does not explicitly replace,
and `templates/` was not named among the files a suite-count change
requires replacing.

Revision 4's fix named the template's source as "`tests/support.py`'s
`CI_SUITES["2.4.0"]` list" -- verified false against the checkpoint order:
CP5 (which authors the overlay, including this template) `depends_on`
`["CP2", "CP3", "CP4"]`, never `CP6`; `CI_SUITES["2.4.0"]` is the key CP6
itself creates (`D-Authored-Release-5`'s own per-release restructuring,
this checkpoint's row in section 5), and `CI_SUITES["2.4.0"]`'s *counts*
are specified as "computed once against the built `2.4.0` payload" --
a payload CP6 itself regenerates from the very overlay CP5 is authoring.
CP6 `depends_on` `["CP5"]`, so CP5 cannot read a mapping key CP6 has not
yet produced, and CP6's own build in turn consumes CP5's output --
the two checkpoints could not both be followed in the declared order.

**Decision: split the obligation by what each half actually needs.** The
template only ever needs suite *names*; only the mirrored assertion's
*counts* need the built payload -- the two live in one `{name: count}`
mapping today, but nothing requires authoring the template from that
mapping. The suite-name list itself is knowable at CP5's own authoring
time without consulting `CI_SUITES["2.4.0"]` at all: it is exactly the set
of payload test-suite files CP2/CP3 add or change inside
`migration/overlays/2.4.0/payload/scripts/` -- CP5's own upstream
dependencies, already complete by the time CP5 runs. So: when `2.4.0`'s
own suite-file set differs from `2.3.1`'s (added, removed, or renamed
files), the overlay
(`migration/overlays/2.4.0/payload/templates/.github/workflows/workflow-conformance.yml`)
includes a regenerated template, produced by the same
`render_ci_workflow`-shaped logic `tools/migrate.py` uses today but
authored **against an explicit suite-name list written directly into the
overlay's own authoring materials** (the payload test-file names CP2/CP3
already fixed, enumerated once as part of CP5's own scope) -- never
against `tests/support.py`'s `CI_SUITES["2.4.0"]`, which does not exist
yet at CP5's own point in the sequence (the two constants stay
disambiguated exactly as stated above -- this is a one-time authoring step
for the overlay, not a change to either existing constant or to
`tools/migrate.py` itself). CP5 owns the names; CP6 -- which runs after
CP5, once `2.4.0`'s built payload exists -- independently enumerates the
built payload's own suite files and owns the measured counts, which is
where `CI_SUITES["2.4.0"]` is actually populated (round-5 O1: stated
explicitly here, since "CP6 owns only the counts" read alone makes the
check below sound like a tautology -- it is not, precisely because CP6
measures the payload itself rather than reading CP5's list). CP6 adds the
mirrored assertion `test_templates.py:225`'s equality
(`self.assertEqual(set(migrate.CI_SUITES), frozen_suites)`, inside
`test_it_runs_exactly_the_frozen_ci_suites` -- the equality-shaped model,
not `test_every_named_suite_exists_in_the_payload`'s (`:212-215`)
membership-only `assertIn` loop; corrected, revision 11, O-R11-1: revision
5's own O1 moved the line number from `:213-215` to `:225` but carried the
old test name along with it) makes for
`2.3.1`, parameterized at `2.4.0`: the *installed template*'s suite-name
list is asserted equal to `CI_SUITES["2.4.0"]`'s own keys, once CP6 has
computed that mapping -- this is what actually proves CP5's hand-authored
name list and CP6's independently measured mapping agree, catching a typo
in CP5's list rather than assuming it away. `depends_on` needs no edge
changes to realize this
split: CP5 already depends on CP2/CP3/CP4 (where the payload's own suite
files are fixed), and CP6 already depends on CP5 (so the mirrored
assertion runs after the template it checks exists) -- the fix is which
constant CP5's own authoring step reads, not the dependency graph. If a
future authored release changes no suite names, the overlay simply omits a
`templates/` replacement and the base `2.3.1` template is copied forward
unchanged -- correct, and stated as the deliberate no-op case rather than
left ambiguous.

**CP6's explicit obligation**: after regenerating
`distribution/workflow/2.4.0/`, run the full frozen conformance matrix a
**second** time, parameterized at `2.4.0` -- `TestConformanceFixture`
against a fixture built from the `2.4.0` payload (green, exact counts per
`CI_SUITES["2.4.0"]`) and `TestBootstrappedTarget` against a clean target
bootstrapped at `2.4.0` (failure set exactly
`by_version["2.4.0"]`) -- in addition to, not instead of, the existing
`2.3.1` run, which CP4 already keeps green and unmodified. This is the run
`CLAUDE.md`'s existing "Adding a Workflow release" procedure already
requires ("must be green against the fixture, and the clean target's
failure set must equal the documented exceptions") for every release;
D-Authored-Release-2's parallel "Adding an **authored** Workflow release"
procedure now has the verification half it previously promised without
designing.

**The `WFO-STATE-SERIALIZATION` closure-verifier gap, also closed here**:
I1's own state-writer-census obligation
(`STATE_WRITER_SURFACE_PREFIXES = (".claude/commands/", "scripts/")`,
`workflow_state.py:7114`) only ever scans this repository's own
`.claude/commands/`/`scripts/` trees, never
`migration/overlays/2.4.0/payload/` -- so a new state writer authored
inside the overlay was previously checked only by "the successor's own
conformance run," which this plan never scheduled anywhere. CP6 widens the
closure verifier's scan to also cover
`migration/overlays/<version>/payload/` for every authored release present,
so the census runs against the overlay's own new writers inside this
repository's own conformance pass, rather than being deferred to a
conformance run that does not exist.

## 4. Update-path validation (disposable repositories only)

Every scenario below is built and exercised against a disposable Git
repository under a temp directory (the same `build_target_repo`-style
fixtures `tests/` already uses), never against a real managed repository,
and never against `~/Workspace/workflow-controller`.

1. **Normal v2.3.1-managed repository** (`PLANNING`, no open work item) --
   bootstrap at `2.3.1`, `update` to the successor release, assert every
   pre-existing file/record survives or transforms exactly per
   D-Plan-Amendment-7's additive contract.
2. **`IMPLEMENTING`** -- bootstrap, drive a synthetic work item through
   plan approval and partway through checkpoints (scripted via direct
   `workflow_state` calls, the same way `tests/` already drives fixtures
   through phases without a live Claude session), `update`, assert the
   in-flight `plan_approval`/`checkpoints`/claims survive untouched, then
   exercise `/request-plan-amendment` for the first time on an
   updated repository.
3. **`SELF_REVIEWING_IMPLEMENTATION`** -- same as (2), advanced one phase
   further (all checkpoints complete, pre-technical-approval) -- the exact
   shape of the Controller's real blocker. `update`, then
   `/request-plan-amendment`.

Each of (2) and (3) continues past the update into the full new sequence:
request amendment -> `/milestone-plan` (produces the amended plan) ->
two-stage local/manual plan review -> `/approve-review plan` (exercising
checkpoint reconciliation for real, with at least one retained, one
changed, and one added checkpoint in the synthetic amendment) ->
`/milestone-implement` resumes and reaches `SELF_REVIEWING_IMPLEMENTATION`
again cleanly. This is the disposable-repository rehearsal the real
Controller repository will need once this release exists -- exercised here
so that when it eventually happens, it is a known-good sequence, not a
first attempt.

The full-sequence rehearsal, in at least one of (2)/(3), also exercises
every scenario B4/B5/B6 identified as unproven:

4. **A `REVISE` verdict at either plan-review stage before the amended
   plan is approved** -- asserts reconciliation still fires exactly once
   at the eventual approval, and that the plan-stage base
   (`AMENDMENT_DIFF.patch`'s `amendment_base_commit`) stays stable across
   every round of the same amendment, driven by the open-amendment marker
   rather than revision arithmetic (B4).
5. **`implementing_entry_reachable` immediately after the amended plan's
   approval** -- asserts the item can actually re-enter `IMPLEMENTING`
   (`approval_is_current` returns `True` against the item's own unchanged
   `base_commit`), the single test that would have caught B5's
   consumer-source split.
6. **A reconciliation case with a dependent chain** -- CP*j* changed ->
   `NEEDS_REVALIDATION`, CP*k* `depends_on` CP*j*, CP*k* itself unchanged
   -- asserts CP*k* is also flipped to `NEEDS_REVALIDATION` by the
   dependency-closure pass (B6.3).
7. **A reconciliation case with a byte-identical registry row but changed
   checkpoint content** -- CP*m*'s registry row (`name`/`depends_on`/
   `complexity`/`session_target`) is untouched between the two pinned
   registries, but its `<!-- CP<m> -->`-anchored plan-document content
   differs -- asserts CP*m* is flipped to `NEEDS_REVALIDATION`, proving the
   discriminator sees a redefinition the registry row alone would miss
   (B6.2).
8. **`tools/migrate.py --check` with `distribution/workflow/2.4.0/`
   present** -- asserts it still passes for `2.3.1`, and that an ordinary
   `python3 tools/migrate.py` regeneration does not delete the sibling
   authored release (B1).
9. **The pinned workflow-manager suites, re-run with both releases
   present** -- asserts every `find_release(repo_root, "2.3.1")`-pinned
   assertion still exercises `2.3.1`'s own content unchanged, and the
   parallel authored-release assertion set exercises `2.4.0`'s own
   manifest/provenance/overlay-delta content (B2).
10. **`Release`/`cli`/`install` against the authored `2.4.0` manifest** --
    constructs a `Release` from it and runs `bootstrap`/`update`/`status`/
    `releases` against it, asserting no `KeyError` and that
    `release.provenance`/`release.upstream` both read correctly (B3).

Added this revision, closing round 2's Blocking/Important findings the
first ten scenarios did not yet exercise. Items 11-15 exercise
`reconcile_checkpoints_after_amendment`/`apply_plan_approval` directly
(unit-level, CP2's own test file, not necessarily a full disposable-repo
bootstrap); item 16 is a plain `Installation.from_dict` unit test (CP4);
item 17 is a `tests/test_conformance_suite.py`-level run, and item 18 a
`tools/migrate.py`-level unit test -- neither is a disposable-repository
scenario in this section's own narrower sense, but both are listed here
since they are the direct evidence CP6's/CP4's own obligations
(D-Authored-Release-5, D-Authored-Release-3) produce and every other
numbered item in this section lives beside them:

11. **A post-amendment `/approve-review plan`, asserting step 6.2's
    compare-and-swap actually passes** --
    `plan_approval_state_matches_pre_transaction(repo_root,
    journal["pre_procedure_state_sha256"])` returns `True` for an approval
    whose `apply_plan_approval` call folds in reconciliation, proving the
    corrected insertion point (reconciliation inside the journal's pinned
    `expected_post_state`, not a new guarded step) actually satisfies the
    existing compare-and-swap rather than being rolled back by it (B3-new).
12. **A reconciliation case whose `pre_amendment_plan_text` carries no
    `<!-- CP<n> -->` anchors at all** -- the exact shape of
    `workflow-controller`'s own plan and of this document before this
    mechanism ships -- asserts every checkpoint id present in both
    registries is conservatively flipped to `NEEDS_REVALIDATION` (never
    silently treated as unchanged), proving the fail-closed default for
    the legacy/no-anchor case (B4-new.1).
13. **A registry/plan-text anchor-coverage validation case** -- one
    registry checkpoint id with no anchor pair in the approved plan text,
    one with two *overlapping* pairs, and one with a stray close tag and
    no matching open (the orphan-close gap) -- asserts `apply_plan_approval`
    refuses (`AmendmentAnchorCoverageError` for the missing pair,
    `AmendmentAnchorMalformedError` for the overlapping and orphan-close
    cases) in every case rather than silently reconciling against an
    incomplete or ambiguous span. Two well-formed, disjoint pairs for the
    same id is asserted as legal, not malformed (I5-new corrected this:
    "duplicated" never belonged in the malformed trigger) (B4-new.2).
14. **A reconciliation case where the plan's trailing sections (5-8)
    change but no checkpoint's own anchored content does** -- asserts no
    checkpoint flips to `NEEDS_REVALIDATION`, proving the paired
    open/close anchor span excludes trailing document sections by
    construction rather than absorbing them as revision 2's
    span-to-next-anchor-or-EOF rule did (B4-new.3).
15. **A bundle-identity check across an amendment's open/closed state** --
    generate a plan-stage bundle while an amendment is open
    (`AMENDMENT_DIFF.patch` present at
    `.ai-review/<work_item_id>/AMENDMENT_DIFF.patch`), then again
    immediately after reconciliation closes it (the file absent) --
    asserts `bundle_id` is **identical** across the two generations
    whenever nothing under `bundle_dir` itself changed, proving
    `AMENDMENT_DIFF.patch`'s presence, being outside `bundle_dir`, is no
    longer a function of `bundle_id` at all (B5-new).
16. **`Installation.from_dict` round-trip against a `2.3.1`-era record with
    no `provenance` key** -- asserts the record still loads (no
    `SCHEMA_VERSION` bump breaks it) and reports
    `provenance == {"origin": "upstream"}` by default (I3-new).
17. **The full frozen conformance matrix run against `2.4.0`'s own
    payload** -- `TestConformanceFixture` green against a `2.4.0` fixture
    with `CI_SUITES["2.4.0"]`'s own counts, `TestBootstrappedTarget`'s
    failure set exactly `by_version["2.4.0"]`'s documented exceptions, and
    the `WFO-STATE-SERIALIZATION` closure verifier's widened scan covering
    `migration/overlays/2.4.0/payload/`'s own new writers (B2-leftover).
    **This scenario's own precondition is CP6's acceptance obligation, not
    a tool this plan revision ships (corrected this revision -- a prior
    revision credited a mid-`REVISING_PLAN` script that neither derived
    the right population nor was wired into its own check, round 31,
    I-R31-2/I-R31-3, and has been removed)**: D-Plan-Amendment-7's
    compatibility disposition -- every payload-suite test function whose
    read set intersects a path this release touches, identified and run
    green (or a red one already accepted in
    `migration/portability_exceptions.json`) -- must be produced and pass
    as part of CP6's own deliverable before this scenario's own
    conformance-matrix run is meaningful. This scenario exercises the
    result against the actual `2.4.0` overlay diff once CP6 has done so;
    it does not itself build or run the disposition.
18. **`tools/migrate.py`'s `_tree_digest` common-root scoping, at the
    digest level, not just `--check`'s exit status** -- a unit test
    asserting `_tree_digest(Path(tmp) / "workflow" / version)`'s and
    `_tree_digest(REPO_ROOT / "distribution" / "workflow" / version)`'s
    key sets are computed at the same root (both containing
    `manifest.json`/`payload/…` with no `workflow/<version>/` prefix on
    either side) -- distinct from scenario 8's black-box exit-status
    check, which a disjoint-key-set bug and a real drift bug both fail
    identically, so only a digest-level assertion actually distinguishes
    the two (B1-new).

Added this revision (4), closing round 3's Blocking/Important findings the
first eighteen scenarios did not yet exercise:

19. **A reconciliation case whose `pre_amendment_plan_text` is *partially*
    anchored** -- one registry checkpoint id with a well-formed pair, a
    second present in the same text with no pair at all -- the shape
    between scenario 12's zero anchors and scenario 13's malformed
    post-side text, and the one revision 3 left as an unrecoverable
    refusal. Asserts `apply_plan_approval` never raises
    `AmendmentAnchorCoverageError`/`AmendmentAnchorMalformedError` for
    `pre_amendment_plan_text` under any shape, and that the unanchored id
    is conservatively flipped to `NEEDS_REVALIDATION` while the anchored
    id is compared by content hash as usual (B5-new).
20. **`apply_plan_approval` actually receiving `post_registry`/
    `post_plan_text` by the named mechanism, and a resumed approval
    replaying rather than recomputing** -- asserts (a) calling
    `apply_plan_approval` for a work item with an open amendment and
    `post_registry`/`post_plan_text` both `None` raises
    `AmendmentReconciliationInputsMissingError`, naming which is absent; (b) a call
    with both supplied folds reconciliation into the returned state
    exactly as D-Plan-Amendment-4 describes; and (c) simulating a
    resumed/retried approval (a second `open_plan_approval_journal` call
    against the same pre-state and inputs) produces byte-identical
    `expected_post_state` to the first, and that the actual approval path
    (`/approve-review plan` step 6c) replays the journal's pinned blob
    rather than invoking `apply_plan_approval` a second time -- the test
    that distinguishes the corrected mechanism from revision 3's now-
    withdrawn false premise (B2-new).
21. **`tests/test_bootstrap_e2e.py`'s own three `CI_SUITES`/
    `PORTABILITY_EXCEPTIONS` sites, with both releases present** -- asserts
    `:64`/`:84`/`:48` (`CI_SUITES["2.3.1"]`,
    `PORTABILITY_EXCEPTIONS["by_version"]["2.3.1"]["exceptions"]`) still
    exercise `2.3.1`'s own bootstrapped behavior unchanged once `2.4.0`
    exists on disk alongside it -- the second reader of both restructured
    constants scenario 17 did not name (B4-new).
22. **An unterminated final anchor** -- a `<!-- CP<n> -->` open tag with no
    matching close and no subsequent open tag of any id before end of
    document, in `post_plan_text` -- asserts `apply_plan_approval` refuses
    with `AmendmentAnchorMalformedError` rather than treating the span as
    running to end of document (the trailing-absorption bug this
    mechanism exists to remove) or silently dropping it (I5-new).

Added this revision (5), closing round 4's Blocking/Important findings the
first twenty-two scenarios did not yet exercise:

23. **A `NEEDS_REVALIDATION` checkpoint's central success path, proven
    rather than assumed** -- for a checkpoint reconciliation flips from
    `COMPLETE` to `NEEDS_REVALIDATION`, asserts `resolve_checkpoint_ownership`
    returns `FRESH` for its id when selected again, that `claim_checkpoint`
    then succeeds, and that `checkpoint_origination_provable`/
    `identity_reference_admits` are never consulted anywhere on that path
    (I1-new -- the mechanism's central success path, previously unproven
    anywhere in this section).
24. **An outstanding self-owned claim surviving into an amendment
    approval** -- a checkpoint claimed by this worktree, with nothing
    locally `IN_PROGRESS` for it (the `CONTINUE_CLAIM` crash window), still
    outstanding when `/request-plan-amendment` is attempted -- asserts the
    widened D-Plan-Amendment-1 precondition refuses the request by name
    (rather than admitting it and surfacing a later
    `CheckpointOwnershipStateMismatchError` failure inside
    `/milestone-implement`), and that releasing the claim first is
    sufficient to make the request succeed (I1-new).
25. **`apply_plan_approval` receiving `plan_path`/`registry_path` bytes by
    the expression B1-new's fix names** -- asserts step 4c's own fresh
    `workflow_fingerprint.resolve_plan_stage_metadata(repo_root,
    work_item_id)` call is what supplies `post_plan_text`/`post_registry`'s
    source paths (not step 1, not step 4a's `plan.paths`), and that a
    change to `plan_path` landing between step 2's recomputation and step
    4c's own read is caught by step 6a's post-commit
    `verify_post_approval_manifest_match` when the approval otherwise
    proceeds (B1-new).
26. **CP5's overlay CI template and CP6's per-release `CI_SUITES` in one
    ordered scenario** -- builds the `2.4.0` overlay's CI-workflow template
    from CP5's own explicit suite-name list (no `CI_SUITES["2.4.0"]` read
    at that point), then runs CP6's build and mirrored assertion, asserting
    the installed template's suite names equal `CI_SUITES["2.4.0"]`'s own
    keys once CP6 has computed them -- proving the names/counts ownership
    split B2-new asks for is actually followable in the declared checkpoint
    order, not merely asserted (B2-new).

Added this revision (6), closing round 5's Important finding scenario 26
did not yet exercise:

27. **An amendment whose implementation surface exceeds its plan-stage
    declaration** -- drive a fixture through (2)/(3)'s
    `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` sequence with at least
    one completed checkpoint writing a path outside every entry in the
    item's own plan-stage protected/excluded sets (a new top-level
    directory), then call `/request-plan-amendment` followed by
    `/milestone-plan` -- asserts the first post-amendment plan-stage digest
    fails closed with `UnclassifiedPathError` naming that path
    (D-Plan-Amendment-5's stated consequence, I1-new), and that widening
    the item's `<work_item_id>-artifacts.json` plan-stage declaration
    through the existing artifact-declaration repair procedure and
    re-running `/milestone-plan` then succeeds.

Added this revision (7), closing round 6's (`MANUAL_EXTERNAL_PLAN_REVIEW`)
Blocking/Important findings the first twenty-seven scenarios did not yet
exercise (EXT-R6-B1/EXT-R6-I1; the required-tests list `REVIEW_FEEDBACK.md`
itself named for the chosen bounded-reference redesign):

28. **Repeated amendments against a realistically large plan do not cause
    unbounded inline `WORKFLOW_STATE.json` growth** -- construct a synthetic
    plan document/registry pair sized like the motivating Controller plan
    (megabyte-scale plan text, dozens of checkpoints), drive it through at
    least three successive amend-then-approve cycles, and assert
    `WORKFLOW_STATE.json`'s own on-disk byte size after the third approval
    is within a small, checkpoint-count-proportional bound of its size
    after the first -- never growing by anything close to a plan-document's
    own byte size per amendment -- proving `amendment_history`'s bounded
    reference model (`pre_amendment_approval_commit` plus the blob SHAs
    already inside `superseded_plan_approval`) actually bounds state growth
    rather than merely being designed to (EXT-R6-I1(a)).
29. **Reconciliation refuses cleanly when a pinned reference cannot
    reproduce the exact pre-amendment bytes** -- construct an
    `amendment_history` entry whose `pre_amendment_approval_commit` names a
    commit that does not (or no longer) contains the blob SHA pinned in its
    own `superseded_plan_approval.review_content_manifest` (simulating a
    corrupted or force-rewritten reference, never a reachable path in
    ordinary operation), and separately one whose blob SHA is simply
    unreachable -- asserts `load_pre_amendment_snapshot` raises
    `AmendmentPreSnapshotUnreproducibleError` naming the path and the blob
    SHA in both cases, and that step 4c refuses before
    `open_plan_approval_journal` is ever called (nothing pinned, nothing
    staged) rather than silently substituting empty or wrong content
    (EXT-R6-I1(b)).
30. **Crash/retry of plan approval reuses the same immutable pre-amendment
    references rather than re-snapshotting** -- simulate a crash between
    journal-open and commit for a post-amendment `/approve-review plan`
    invocation, then resume: asserts the resumed attempt replays the
    journal's pinned `expected_post_state_b64` rather than calling
    `load_pre_amendment_snapshot`/`apply_plan_approval` a second time; and,
    separately, simulate step 4c being invoked twice before either reaches
    `open_plan_approval_journal` (no journal open yet) and asserts both
    invocations of `load_pre_amendment_snapshot` return byte-identical
    `pre_registry`/`pre_plan_text`, sourced from the same immutable blob
    SHAs each time, proving retry safety holds whether or not a journal was
    already open (EXT-R6-I1(c), D-Plan-Amendment-6).

No new scenario is added for EXT-R6-B1: that finding is a review-context
closure and bundle-regeneration matter (`CONTEXT_FILES.txt`, below),
resolved without any implementation-test obligation, exactly as
`REVIEW_FEEDBACK.md` itself states ("No additional implementation tests
are required for EXT-R6-B1 itself").

Added this revision (11), closing round-11's (`LOCAL_MODEL_PLAN_REVIEW`)
Important finding the first thirty scenarios did not yet exercise
(I-R11-1):

31. **`/request-plan-amendment` refuses by name when its own plan-approval
    commit is not discoverable, before superseding anything -- and
    distinguishes that cause from a moved plan-stage digest, rather than
    proving only that some refusal fires (strengthened, revision 12,
    B-R12-1's own test criterion; originally added revision 11, I-R11-1)**.
    Revision 11's own fixture ("a `base_commit` advanced past it")
    triggered an unreachable approval commit and a moved plan-stage digest
    simultaneously, so it could not tell the two causes apart -- corrected
    into two separate constructions:
    - **(i) Approval commit genuinely unreachable, digest otherwise
      current**: construct a work item at `IMPLEMENTING` whose
      `plan_approval` is `CURRENT` and whose plan-stage digest still
      matches (no committed edit to any plan-stage protected path since
      the approval), but whose approval commit itself is not reachable in
      `base_commit..HEAD` (a simulated rebase/force-rewrite of the
      approval commit) -- asserts `/request-plan-amendment` refuses with
      `AmendmentApprovalCommitUnreachableError` naming the work item and
      `base_commit`, and that `plan_approval.status` is still `CURRENT`
      and `amendment_history` is still empty afterward -- i.e. that the
      refusal precedes the supersession rather than following it.
    - **(ii) Approval commit perfectly reachable, digest moved**:
      construct a work item at `IMPLEMENTING` whose approval commit is
      reachable and an ancestor of `HEAD` (this precondition's own two
      checks both pass), but whose plan-stage `review_content_id` has
      moved since the approval -- a committed edit to `plan_path` since
      the approval commit, and, separately, a widened
      `<work_item_id>-artifacts.json` (D-Plan-Amendment-5's own sanctioned
      in-band remedy) -- asserts `/request-plan-amendment` does **not**
      refuse on this precondition (it is not consulted at all, by design --
      B-R12-1): the request proceeds, `plan_approval.status` becomes
      `SUPERSEDED`, and `amendment_history` gains exactly one new entry.
      This is the case revision 11's own fixture could not isolate, and it
      is the behaviour D-Plan-Amendment-4's own I3-new paragraph depends
      on (editing the plan in preparation for the amendment being
      requested must not itself block the request).
    - **(iii) `plan_approval` missing or already `SUPERSEDED`**: construct
      a work item whose phase is not in `{"IMPLEMENTING",
      "SELF_REVIEWING_IMPLEMENTATION"}` (the only reachable way
      `plan_approval` can be absent or non-`CURRENT` while a request is
      attempted) -- asserts the phase precondition refuses with
      `WrongPhaseForAmendmentRequestError` naming the actual phase, never
      with `AmendmentApprovalCommitUnreachableError`, confirming this case
      is excluded by the phase precondition and never reaches the
      reachability check at all.

## 5. Checkpoints

Generated from `docs/ai-workflow/registry/plan-amendment-mechanism-registry.json`
via `workflow_state.render_registry_markdown` -- not hand-formatted, and not
itself hashed (only the JSON registry is a protected path).

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Lock the amendment state-machine design (D-Plan-Amendment-1..8) into the successor's own normative design document, migration/overlays/2.4.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md (a new ### D-Plan-Amendment-1..8 section appended under its existing ### D-<name> convention, naming D-Plan-Amendment-1..8; writes, anywhere in the document, no D-Plan-Review-Stages `/review-plan` transition-table row (state cell `AWAITING_LOCAL_PLAN_REVIEW`, verdict cell `APPROVE`/`REVISE`/`BLOCK`, command cell `/review-plan`), no four-cell Requirements-traceability-table row keyed by a `WFR-nn` id, and no line beginning `85. `/`96. ` -- the patterns TestReviewPlanWriteSetConsistencyLint's three functions and TestRequirementsMappingTableConformance's three functions (workflow_integration_test.py:3384/:3470) actually match, not merely the 'Missing tests' section and the Requirements traceability table by name, I-R25-1, tightened I-R26-1 -- so all six stay green); an overlay_delta-recorded full-file replacement in migration/overlays/2.4.0/payload/ alongside D-Authored-Release-2's other ten replaced paths (O-R30-2: named here at its overlay payload path, not the bare host-relative path, to remove the ambiguity a mechanical derivation of the deliverable set from this row would otherwise hit); open docs/defects/v2.3.1-002-no-plan-amendment-edge.md (not an overlay member -- this repository's own defect record, not distributed payload) | - | 3 | 1 |
| CP2 | Author workflow_state.py additions in the overlay: AMENDING_PLAN, /request-plan-amendment's writer (state_writer: declaration; assigns work_item["phase"] = "AMENDING_PLAN" as a direct string literal, never through a local name, so the AST-derived phase census resolves it without a third hardcoded compensation entry; its widened precondition refusing by name via AmendmentApprovalCommitUnreachableError when the plan-approval commit is not discoverable/an ancestor of HEAD, before superseding anything; records amendment_history's bounded pre_amendment_approval_commit reference, never inline plan/registry snapshots), SUPERSEDED/NEEDS_REVALIDATION, apply_plan_approval's pre_registry/pre_plan_text/post_registry/post_plan_text keyword-only parameters (AmendmentReconciliationInputsMissingError) and reconcile_checkpoints_after_amendment folded into its own computation (load_pre_amendment_snapshot's on-demand, content-addressed load of the pre-amendment registry/plan-text from the pinned approval commit and blob SHAs, AmendmentPreSnapshotUnreproducibleError, total per-id anchor grammar with asymmetric pre-side-conservative/post-side-refusing validation, write-once resolved_at_plan_revision enforcement, dependency-closure propagation), APPROVAL_STATUSES/CHECKPOINT_STATUSES/KNOWN_PHASES + validate_approval_record updates, full compatibility audit of all three vocabularies' own reader call sites -- targeted at APPROVAL_STATUSES's real validation site (validate_approval_record, workflow_state.py:9558) rather than a raw SUPERSEDED grep, since _RECONCILIATION_STATUS_TOKENS's own unrelated reconciliation-table vocabulary (D-Plan-Amendment-3) shares that token and is not a collision (including the payload's own workflow_state_completion_obligations_test.py PERSISTED frozenset and workflow_state_test.py EXPECTED_WRITERS census, both updated for AMENDING_PLAN/its writer as overlay_delta-recorded full-file replacements in migration/overlays/2.4.0/payload/, the way CP3's own row separately describes its own three payload/command files), and the REVIEW_SUBJECT_ROSTER decision (deliberately leaving /request-plan-amendment off it, recorded rather than left unaddressed); introduces no new fcntl.flock(LOCK_EX) call or releasable os.link site (I-R21-1: workflow_state_test.py's TestGlobalLockOrderItem372h closed-set censuses would otherwise go red; if a future revision ever does add one, verify_372h_lock_primitive_predicate.py's DECLARED_PRIMITIVES and WORKFLOW_V2_PLAN.md's own ten-edge table must move in the same overlay change) | CP1 | 5 | 3 |
| CP3 | Author command files (state_writer: declaration; /request-plan-amendment.md opens with the house "Enter the AMENDING_PLAN state of docs/ai-workflow/MILESTONE_WORKFLOW.md." preamble, the same convention every other phase-writing/gating command uses; approve-review.md's numbered sequence unchanged -- reconciliation adds no new guarded step; step 4c reads pre_registry/pre_plan_text via load_pre_amendment_snapshot and post_registry/post_plan_text via the working-tree read, and forwards all four to open_plan_approval_journal; /request-plan-amendment.md's own "what happens next" prose names scripts/prepare-ai-review.sh, explaining that AMENDMENT_DIFF.patch will appear in the next plan-stage bundle while this amendment stays open, I-R14-2, authored under an explicit phrasing constraint -- it names scripts/prepare-ai-review.sh without a run/rerun-plus-backticked-invocation construction, so its own invocation lines never match _GENERATOR_RUN_RE, I-R15-1), prepare-ai-review.sh's AMENDMENT_DIFF.patch generation outside bundle_dir, its inclusion in review-bundle.tar.gz, and REVIEW_REQUEST.md's fixed non-authoritative marker line for it, introducing neither assert_local_generation_matches nor governing_workflow_version awareness into prepare-ai-review.sh itself (I-R21-1: workflow_integration_test.py's TestAssertLocalGenerationMatchesCallSiteConformance and the governing_workflow_version half of test_bundle_scripts_are_deliberately_version_agnostic would otherwise go red), apply-functional-review.md's broad-remediation branch naming /request-plan-amendment <child-id> (a remediation child in IMPLEMENTING/SELF_REVIEWING_IMPLEMENTATION may request its own plan amendment, on the same terms as its parent), and distribution-doc updates in the overlay -- explicitly including the payload's own workflow_integration_test.py (its persisted-phase table check, its own hand-maintained phase-to-writer dict, its command-count/literal-string check, its argument-hint-heading check, its broad-remediation-branch/remediation-children-section completeness checks, its Enter-preamble ten-stem-to-eleven-stem literal/table check, its generator-mention census -- _GENERATOR_MENTION_ONLY_COMMANDS gains a third entry, request-plan-amendment.md, with its own justification string, I-R14-2; and test_no_mention_only_command_instructs_its_own_generation's two-population docstring updated to a three-population reading, I-R15-2 -- and, new at revision 18, B-R18-1, _GOLDEN_COMMAND_FILE_SHA256's approve-review.md and apply-functional-review.md entries, recomputed against the overlay's own edited command files; request-plan-amendment.md itself needs no entry, since the dict is thirteen of fifteen command files today and is not a total census) and, new at revision 19 (B-R19-1), test_the_broad_branch_states_the_real_child_entry_phase's own three-line pinned literal (workflow_integration_test.py:6227-6239) updated to match the reflowed broad-remediation-branch text once /request-plan-amendment <child-id> is inserted into the sanctioned child sequence) and WORKFLOW_V2_1_OPERATOR_REFERENCE.md itself (its Persisted phases table, its persisted-phase-writer table, its hand-maintained command-count pair updated to 16, its Remediation children section, its "Enter the `X` state" table and "Ten of the fifteen" sentence updated to eleven of sixteen, a new ### /request-plan-amendment section, and, new at revision 19 (I-R19-1), a small clarifying sentence scoping the "whole plan lane persists exactly three phases" claim to the pre-approval PLANNING->IMPLEMENTING sequence, distinct from the new re-entry AMENDING_PLAN phase) and docs/ai-workflow/REVIEW_PROTOCOL.md itself (its "Author-written files" list gaining AMENDMENT_DIFF.patch's own bullet -- a fixed non-authoritative marker line, D-Plan-Amendment-5 -- and its "Bundle structure" diagram gaining the same file; constrained, I-R22-2, to leave :199's "Must state `review_content_id: <hex>` as a plain labelled line" and :212's "`implementation_revision: <N>` matching the work item" sentences byte-identical, or to move test_the_ad_hoc_and_bootstrap_drivers_route_authoring_through_the_protocol's two pinned literals in the same overlay change) and docs/ai-workflow/MILESTONE_WORKFLOW.md itself (its state-machine listing gaining the AMENDING_PLAN state and its re-entry edges from IMPLEMENTING/SELF_REVIEWING_IMPLEMENTATION, I-R22-2, constrained, I-R23-1, to place the new ### AMENDING_PLAN section after ### PLANNING (so ## State reference's never-persisted summary paragraph stays inside the text.split("## State reference", 1)[1].split("### ", 1)[0] slice) and to carry no *Vocabulary state — never persisted* marker on that section, the same shape the REVIEW_PROTOCOL.md:199/:212 constraint already takes), each an overlay_delta-recorded full-file replacement in migration/overlays/2.4.0/payload/ | CP2 | 3 | 1 |
| CP4 | Fix workflow-manager's own release tooling and test suites for a second release: tools/migrate.py's spec-derived, release-scoped destructive step and common-root --check comparison, CLAUDE.md's distribution/ hard rule and its 'Before changing anything' --check sentence (both amended to the per-release scope), release.py/cli.py/install.py/installation.py's additive provenance handling (manifest and installation-record schema posture), pin every REPO_ROOT-rooted find_release call to 2.3.1 explicitly (exempting the synthetic-root defaulting test and test_conformance_suite.py:54's own workflow_version-parameterized _SuiteRun.build) | CP1 | 4 | 2 |
| CP5 | Release-authoring tooling: migration/overlays/2.4.0/ (including a regenerated CI-workflow template, authored against an explicit suite-name list fixed by CP2/CP3's own overlay payload files -- never against tests/support.py's CI_SUITES["2.4.0"], which CP6 alone creates -- when 2.4.0's own suite list differs from 2.3.1's), tools/build_release.py (base-verify, overlay-apply, overlay_delta recording), overlay classification ruleset, manifest.json's additive provenance field, and preserving each replaced payload file's existing 2.3.1 category in the overlay's own classification.json (I-R16-2: category determines the install profile, src/workflow_manager/release.py:29-32) | CP2, CP3, CP4 | 5 | 2 |
| CP6 | Regenerate distribution/workflow/2.4.0/; prove 2.3.1 byte-identical/frozen via the fixed migrate.py --check; make tests/support.py's CI_SUITES/portability_exceptions.json per-release across both test_conformance_suite.py and test_bootstrap_e2e.py and run the full frozen conformance matrix against 2.4.0's own payload via _SuiteRun.build's workflow_version parameter; widen the WFO-STATE-SERIALIZATION closure verifier to the overlay payload; extend conformance suite with the parallel authored-release assertion set, overlay-delta verification, and the 2.4.0 CI-template suite-name assertion; discharge D-Plan-Amendment-7's own compatibility-audit acceptance obligation -- identify every payload-suite test function (workflow_state_test.py, workflow_state_completion_obligations_test.py, workflow_integration_test.py) whose read set intersects a path this release's checkpoints touch, run each one against the finished overlay diff, and report every member green or an already-documented red in migration/portability_exceptions.json | CP5 | 5 | 3 |
| CP7 | Disposable-repository fixtures for IMPLEMENTING/SELF_REVIEWING_IMPLEMENTATION | CP6 | 3 | 1 |
| CP8 | Update-path validation: all three scenarios, including a REVISE round mid-amendment, post-amendment implementing_entry_reachable, reconciliation dependency-closure and registry-row-unchanged/prose-changed cases, and safe resumption | CP7 | 5 | 3 |
| CP9 | Documentation: ARCHITECTURE.md, MIGRATION.md, README.md, CLAUDE.md release procedures (including the stated downgrade posture) | CP8 | 2 | 1 |

(Full names, unabbreviated, live in the registry JSON and section 3/4 above;
this table mirrors the generator's own column set exactly. CP4's identity
is kept live and redefined across this revision -- from "workflow_fingerprint.py
additions" to "fix workflow-manager's own release tooling" -- rather than
retired and replaced by a new id: B5's fix eliminated the need for any
`workflow_fingerprint.py` change at all (its one remaining piece of new
plumbing, `AMENDMENT_DIFF.patch` generation, is a `prepare-ai-review.sh`
change and lives in CP3 instead), and B1/B2/B3 need a checkpoint that
CP2/CP3/CP5's existing scope does not fit.

**Citation corrected (I6-new)**: this is in-place redefinition of a
kept-live id, and it is legal -- but not, as revision 2 claimed, because
`D-Registry`'s checkpoint-id-reuse rule "sanctions" it.
`WORKFLOW_V2_PLAN.md`'s `D-Registry` section says the opposite: "Checkpoint
ids are permanently non-reusable within a work item... A rename is
therefore a **new** id and the retired one stays retired" -- a
prohibition on reuse, not a license for redefinition. The reason CP4's
redefinition is legal is the carve-out the same section states a few
paragraphs later: the invariant is scoped to ids observed in
`D-Checkpoint-Ownership`'s origination reference (durable history of a
checkpoint actually reaching `IN_PROGRESS`), and "a checkpoint id retired
before it was ever started carries no historical binding, and is
therefore outside this invariant." This work item's `checkpoints` map is
`{}` (`docs/ai-workflow/WORKFLOW_STATE.json`) -- CP4 has never been
started under either its revision-1 or revision-2 identity, so no
historical observation binds it, and the never-started carve-out is what
makes the redefinition legal, not a general sanction for redefining a
kept-live id that has been worked on.)

## 6. Requirements mapping (summary; full detail in the generated mapping file)

| Requirement | Covers | Checkpoints |
| --- | --- | --- |
| REQ-1 | Which phases may request amendment | CP1, CP2 |
| REQ-2 | Explicit authority, no `USER_OVERRIDE` | CP1, CP2, CP3 |
| REQ-3 | How the current approval becomes stale/superseded | CP1, CP2 |
| REQ-4 | Legal re-entry into plan revision/review | CP1, CP2 |
| REQ-5 | Fresh two-stage plan review of the amended plan | CP1, CP2 |
| REQ-6 | New approval becomes the implementation basis | CP1, CP2 |
| REQ-7 | Disposition of completed checkpoints/commits; safe resumption | CP1, CP2 |
| REQ-8 | `review_content_id`/bundle/approval-commit/ancestry/protected-path handling | CP1, CP3 |
| REQ-9 | Crash/interruption recovery, idempotence | CP2 |
| REQ-10 | Compatibility with v2.3.1-managed repos; schema migration need | CP2, CP4, CP6 |
| REQ-11 | Correct authored-release production path; v2.3.1 stays frozen | CP4, CP5, CP6 |
| REQ-12 | Regeneration/release validation per this repo's own conventions | CP6 |
| REQ-13 | Disposable-repo update-path validation (normal/IMPLEMENTING/SELF_REVIEWING_IMPLEMENTATION) | CP7, CP8 |
| REQ-14 | Exercise amendment + fresh review/approval + resumption post-update, pre-real-repo | CP8 |
| REQ-15 | Document the authored-release convention and the amendment operator flow | CP3, CP9 |

## 7. Explicitly out of scope

- The larger review-history/context-scalability redesign.
- Amendment requests from any phase other than `IMPLEMENTING`/
  `SELF_REVIEWING_IMPLEMENTATION` (e.g. after `technical_approval` or
  during functional review) -- a documented future extension, not solved
  here.
- Amending while a checkpoint is `IN_PROGRESS`, or while a checkpoint claim
  is outstanding with nothing locally `IN_PROGRESS` for it (D-Plan-
  Amendment-1's widened precondition, revision 5's I1-new) -- must be
  finished, or its claim released, first.
- Any change to `~/Workspace/workflow-controller`, and any application of
  this mechanism to a real managed repository -- disposable-repository
  validation only, in this work item.
- Any in-place edit to `distribution/workflow/2.3.1/`.
- **Abandoning an in-flight amendment once requested (new, revision 5,
  I3-new)**. `/request-plan-amendment` sets `plan_approval.status =
  SUPERSEDED` in one transaction (D-Plan-Amendment-3); from that moment
  `approval_is_current`/`implementing_entry_reachable` both read `status
  != "CURRENT"` (`workflow_state.py:1562-1612`, verified directly), so the
  only way back to `IMPLEMENTING` is a completed two-stage review plus
  `/approve-review plan` against a new, `CURRENT` approval -- there is no
  in-band `SUPERSEDED -> CURRENT` restoration, and inventing one here would
  mean either resurrecting a stale approval record (weakening an existing
  approval binding, explicitly out of bounds for this work item) or adding
  a second, narrower state-writer command whose own guard, journal
  interaction, and interruption story would need the same scrutiny this
  plan already gives `/request-plan-amendment` itself. An operator who
  requests an amendment and then decides against it -- a mistaken
  invocation, a blocker that turns out not to need a plan change, a
  `BLOCK` verdict at either amendment review stage -- pays the cost of a
  full amendment cycle to a no-op amended plan (identical in content to
  the pre-amendment plan) to get back to `IMPLEMENTING`, and on a
  pre-anchor plan's first amendment that also means the full-revalidation
  price D-Plan-Amendment-4's zero-anchor default already accepts, for an
  amendment that changed nothing. The resulting all-retained, no-op
  reconciliation outcome is already handled by unmodified machinery, not
  left to chance (new, revision 10, O-R10-5): `select_next_checkpoint`'s
  own docstring (`workflow_state.py:3115-3130`) names this exact case --
  `None` is the correct answer on the first selection after a plan
  re-approval on an item whose checkpoints are all already `COMPLETE`,
  where `apply_plan_approval` has legitimately just written
  `IMPLEMENTING` -- and `/milestone-implement`'s `NO_CHECKPOINT` branch
  (`.claude/commands/milestone-implement.md:88-99`, the call itself at
  `:219`) already routes that case into
  `enter_self_reviewing_implementation` rather than wedging the item.
  **This is the deliberate call for this
  release**, to keep the mechanism's own scope bounded to what the
  Controller's real blocker needs (section 1) rather than adding a second
  new command and a second new authority check on the strength of a
  hypothetical mis-invocation; a future release may add a narrow,
  user-only `/withdraw-plan-amendment`, valid only while
  `resolved_at_plan_revision` is still `null` and no plan revision has
  been published since the request, if abandonment turns out to be common
  enough in practice to justify it.
- **A permanently unreproducible pre-amendment Git snapshot (new,
  revision 8, I-R8-1)**. `AmendmentPreSnapshotUnreproducibleError`
  (D-Plan-Amendment-3/-4) is fail-closed by design, but its own text
  previously implied the underlying Git condition is always eventually
  retriable. It is not, given this section's own no-abandonment stance
  immediately above (I3-new): the `amendment_history` entry pinning
  `pre_amendment_approval_commit` is immutable from the moment
  `/request-plan-amendment` appends it, a second
  `/request-plan-amendment` against the same work item refuses
  (`WrongPhaseForAmendmentRequestError`), and `plan_approval.status ==
  "SUPERSEDED"` keeps `approval_is_current`/`implementing_entry_reachable`
  refusing re-entry to `IMPLEMENTING` (both test `!= "CURRENT"`,
  `workflow_state.py:1562-1612`) no matter how many further
  `/milestone-plan`/`/apply-plan-review` rounds run -- a new plan revision
  does not clear the open amendment marker, so every subsequent
  `/approve-review plan` refuses again at step 4c for the identical
  reason. So a work item whose pinned commit's tree genuinely stops
  reproducing the exact `plan_path`/`registry_path` blobs -- history
  rewritten, a shallow clone, or object corruption, never expected in
  ordinary operation since the blob is reachable from that commit's own
  tree from the moment it was made -- is wedged at `AWAITING_PLAN_APPROVAL`
  permanently: the identical unrecoverable-wedge shape D-Plan-Amendment-3's
  pre-side anchor-coverage treatment was built to close for a different
  pinned input, reopened here through this bounded Git reference instead.
  **Accepted as-is for this release, not given a narrow escape**: the
  reachability is bounded by the same ordinary Git object-retention
  guarantee the anchor-coverage case relies on, this work item's own
  validation is disposable-repository only (this section, above), and a
  future `/withdraw-plan-amendment` -- if abandonment turns out to be
  common enough to justify one -- would close this gap and the one above
  in the same stroke, so it is better deferred to that single future
  release than solved twice, narrowly, here.
- **The successor's lifecycle diagram is not regenerated by this release
  (new, revision 25, B-R25-2)**.
  `docs/ai-workflow/diagrams/workflow-v2-1-lifecycle.drawio.svg` is a
  `distribution`-category payload artifact
  (`distribution/workflow/2.3.1/manifest.json`) that draws every
  persisted phase as a box, and CP1's own registry row locks
  `AMENDING_PLAN`'s design into text -- `docs/ai-workflow/WORKFLOW_V2_PLAN.md`
  (I-R25-1, above) and `docs/ai-workflow/MILESTONE_WORKFLOW.md`'s state
  reference (CP3, section 5) -- never into this diagram. Seventeen
  payload-suite test functions read the diagram's embedded drawio model
  or its rendered SVG body directly (`workflow_integration_test.py`:
  `TestLifecycleDiagramMatchesTheModelItCarries` `:6718`, `:6729`,
  `:6737`, `:6747`; `TestLifecycleDiagramLayout` `:6776`, `:6785`,
  `:6802`, `:6817`, `:6838`; `TestLifecycleDiagramMatchesTheCode` `:6852`,
  `:6872`, `:6886`, `:6897`, `:6906`, `:6913`, `:6935`, `:6950`), and one
  of them --
  `test_edge_crossings_are_limited_to_the_documented_set`, which asserts
  the diagram's computed edge-crossing set equals the hardcoded
  `ALLOWED_CROSSINGS = {("e31", "e35"), ("e33", "e35")}`
  (`workflow_integration_test.py:6768`) -- would go red on *any* edit that
  adds the two inbound edges `AMENDING_PLAN` needs (from `IMPLEMENTING`
  and from `SELF_REVIEWING_IMPLEMENTATION`) and one outbound edge into
  the plan-review lane, with no checkpoint in this plan owning
  `ALLOWED_CROSSINGS`'s update. Regenerating the diagram correctly --
  new boxes and edges, `ALLOWED_CROSSINGS` recomputed, the
  model-and-rendered-body agreement the other geometric tests require --
  is real, biddable scope, but it is a diagram-authoring deliverable this
  plan has never actually assigned to a checkpoint (CP1's design-docs row
  is prose, not a drawing obligation; CP3's
  `MILESTONE_WORKFLOW.md`/`WORKFLOW_V2_1_OPERATOR_REFERENCE.md` updates
  are text, not a drawio edit), and the plan already carries one
  deliberate, stated usability gap in the *text* record of
  `amendment_history` (section 8) rather than inventing new drawing
  surface to close a second one here. **Decided for this release**: the
  diagram is left exactly as it is; all seventeen readers stay green for
  that reason alone -- nothing is drawn -- not because any of the
  seventeen assertions was individually re-verified against a changed
  diagram. The two of the seventeen that also fall inside the six-clause
  population (`test_every_command_the_diagram_names_exists`,
  `test_every_phase_the_diagram_draws_as_a_box_has_a_writer`, section 4
  scenario 17 above) are re-grounded on this same "nothing is drawn" fact
  rather than left to read as though `AMENDING_PLAN` were drawn and
  merely well-formed; the remaining fifteen stay outside this plan's
  content-reading family for the same reason the diagram is never added
  to D-Authored-Release-2's file list, above. This is an operator-facing
  choice, not only a testing one: an operator reading this release's
  design artifacts gets `AMENDING_PLAN` from `MILESTONE_WORKFLOW.md` and
  from the operator reference's Persisted-phases table, but not from the
  picture of the state machine -- a defensible choice, stated once, here,
  rather than a silent one. A future release that does add
  `AMENDING_PLAN` to the diagram must add the file to
  D-Authored-Release-2's replaced set, name the regeneration and the
  `ALLOWED_CROSSINGS` update as a CP1/CP3 deliverable, preserve the
  diagram's `distribution` category in that release's own overlay
  `classification.json` (I-R16-2), and disposition all seventeen readers
  red or green with a reason -- the same discipline this bullet gives the
  "not updated" branch, applied to the other one.

- **`docs/defects/v2.3.1-002-no-plan-amendment-edge.md` is a named CP1
  deliverable deliberately excluded from `technical_approval`'s binding
  (new, revision 29, I-R29-1)**. CP1's own registry row (section 5) names
  opening this file as one of its outputs, so by the rule this same
  section's D-Plan-Amendment-5 discussion states, a checkpoint's named
  deliverable is ordinarily `protected` at `implementation_stage`. This
  one is the deliberate exception: it is CLAUDE.md's own out-of-band
  defect record for human attention ("write it up under `docs/defects/`
  and stop there") -- not a design artifact this plan reviews, and not a
  byte-for-byte reviewed implementation deliverable in the sense
  `technical_approval` binds to. It is therefore `excluded` at both
  stages (O-R30-3), at both `docs/defects/` declaration entries
  (`plan-amendment-mechanism-artifacts.json`'s `plan_stage.excluded_prefixes`
  and `implementation_stage.excluded_prefixes` alike), which means a later
  edit to this specific file, after
  `technical_approval` is granted, does not stale that approval. This is
  a real, accepted cost -- an edit to CP1's own defect record after
  implementation review closes escapes that review -- accepted because
  the file's entire purpose is to carry a human-facing writeup that may
  legitimately be refined after the fact (CLAUDE.md's own "and stop
  there" already puts it outside this repository's normal review
  machinery), not because it is unreviewable in principle. The
  alternative (moving it to `implementation_stage.protected_paths`) was
  considered and rejected: nothing about the record's own purpose
  requires the destructive re-review overhead a protected path implies,
  and no requirement (section 6) depends on this file's post-approval
  immutability.

## 8. Self-review notes (`SELF_REVIEWING_PLAN`)

- **Missing requirements check**: re-read every "must determine at
  minimum" and "must also plan" bullet from the assigning brief against
  section 6's mapping; all are covered, none deferred silently (section 7
  lists every deliberate exclusion with a reason).
- **Migration risk**: the additive-only discipline in D-Plan-Amendment-7
  and D-Authored-Release-3 is the load-bearing risk control; CP6 and CP8
  are where it is actually proven (reproducibility of `2.3.1`, and survival
  of pre-existing state across `update`), not merely asserted here.
- **Usability gap flagged, not silently resolved**: this plan does not
  invent a UI for reviewing `amendment_history`; an operator reads it out
  of `WORKFLOW_STATE.json` directly, the same way every other ledger field
  in this workflow is read today. Acceptable for this release's scope;
  worth a follow-up if amendments become frequent.
- **Unnecessary complexity check**: considered and rejected a dedicated
  new plan-review lane parallel to the existing one (a second copy of
  `AWAITING_LOCAL_PLAN_REVIEW`/`AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`
  scoped to "amendment mode") -- rejected because the existing lane's
  behavior is already correct for an amendment once `plan_revision` has
  bumped; a parallel copy would only duplicate logic without adding
  safety.
- **Missing tests**: CP6's D-Plan-Amendment-7 compatibility-audit
  acceptance obligation (discharged and run during `IMPLEMENTING`, as
  part of CP6's own deliverable -- not by this plan revision, and not by
  a standalone script authored ahead of it), CP4's release-explicit suite
  pinning, CP6's per-release conformance run and overlay-delta/authored-release
  verification, and CP7/CP8's disposable-repository proofs -- including
  all thirty-one numbered scenarios in section 4 -- are the tests that
  matter most for this feature; CP9 adds no test, by design (it is
  documentation only). The scenario count is a current fact, not a
  derivation from review history: read section 4's own numbered list
  rather than this note if the count ever needs re-confirming.
- **`docs/TECHNICAL_DECISIONS.md` check**: **not applicable** -- this
  repository's `docs/` contains only `ACTIVE_MILESTONE.md`,
  `ARCHITECTURE.md`, `MIGRATION.md`, `ai-workflow/`, and `defects/`; no
  `TECHNICAL_DECISIONS.md` exists here to check.

**Closed review history -- what is and is not retained (corrected this
revision, B-R31-1).** This plan has been through thirty-four rounds of
`LOCAL_MODEL_PLAN_REVIEW` (plus one `MANUAL_EXTERNAL_PLAN_REVIEW` pass;
count current as of this revision, O-R34-1).
The full round-by-round record -- what each round found, what was applied
or rejected and why, and every citation checked in doing so -- is
intentionally not restated in this section, and revision 31 introduced a
false claim about why: it asserted that record "already lives durably" in
`.ai-review/feedback/REVIEW_FEEDBACK.md`'s "own history", in
`WORKFLOW_STATE.json`'s `plan_review_stages` ledger, and in a
`state_revision` "history". None of the three holds it. Checked directly,
not asserted: `.ai-review/` is `.gitignore`d (`git check-ignore -v
.ai-review/feedback/REVIEW_FEEDBACK.md`) and that one file is overwritten
by every `/review-plan` run, so it carries only the single most recent
round's feedback, never a history, and is not in Git history either.
`WORKFLOW_STATE.json` was untracked for the first thirty-three revisions of
this plan and became tracked at `208050b` (`git log --oneline
--diff-filter=A -- docs/ai-workflow/WORKFLOW_STATE.json`), so it carries Git
history only from that commit forward and still holds no retained record of
rounds 1-33 (fixed, I-R34-1: this paragraph previously claimed the file was
untracked outright, which `git ls-files --error-unmatch
docs/ai-workflow/WORKFLOW_STATE.json` now contradicts). `state_revision`
itself is still a bare current integer, not a log -- becoming tracked does
not change that the field holds only its present value, never a sequence of
past ones. `plan_review_stages`' own
`LOCAL_MODEL_PLAN_REVIEW` entry is a single dict, overwritten on the next
recorded verdict and not written at all for a `REVISE`
(`record_local_plan_review`, `workflow_state.py`), so it holds at most one
past round's outcome, never a ledger of them.

What actually persists, and is what this section relies on instead: this
plan document's own Git history (every prior revision's full text is a
`git show <commit>:docs/ai-workflow/PLAN_AMENDMENT_MECHANISM_PLAN.md`
away, for as long as this repository's history is kept); the single
current `.ai-review/feedback/REVIEW_FEEDBACK.md`, which carries the most
recently completed round's own findings and evidence in full; and
`WORKFLOW_STATE.json`'s current fields (`plan_revision`,
`plan_review_stages`), which name where the item stands now, not where it
has been. That is the same durability every other Workflow-governed plan
document already has -- nothing new is introduced here, and nothing about
it changed this revision.

A prior revision of this section carried the full per-round transcript
inline; removing it (revision 31) was the right call and stands --
durable state duplicated as hand-typed prose is exactly the shape that
produced round 30's own review-apparatus findings (a stale plan-stage
justification string, and a paragraph annotated rather than rewritten),
and it is where at least three recurring classes of review churn came
from across the thirty rounds. What revision 31 got wrong was the
justification for removing it, not the removal itself; this revision
corrects the justification and additionally removes
`tests/verify_amendment_test_census.py`, a script revision 31 introduced
as part of the same remediation outside `REVISING_PLAN`'s legal artifact
set and that did not implement the check it claimed to (round 31,
I-R31-2/I-R31-3 -- see D-Plan-Amendment-5 and D-Plan-Amendment-7 above).
Nothing about the design itself changed in either revision's removal:
`AMENDING_PLAN` phase semantics, `SUPERSEDED` approval status, amendment
request authority, plan-review re-entry mechanics, approval
supersession/re-approval semantics, the checkpoint reconciliation
algorithm, crash/recovery/idempotence guarantees, successor-release
generation mechanics, Workflow Manager update/migration behavior, the
v2.3.1 compatibility posture, and every implementation protected/excluded
path classification are exactly as designed in the decision sections
above and in `plan-amendment-mechanism-artifacts.json`'s actual
classifications -- only prose describing *how this plan itself has been
reviewed*, and a script that misdescribed part of that same review
apparatus, were removed.
