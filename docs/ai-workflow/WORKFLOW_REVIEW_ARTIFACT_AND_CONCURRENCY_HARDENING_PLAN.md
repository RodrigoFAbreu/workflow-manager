# Workflow 2.6.0: Review-Artifact, Publication and Concurrency Hardening (Revision 8)

`work_item_id: workflow-review-artifact-and-concurrency-hardening` -- `governing_workflow_version: "2.2"`

**Deliverable release:** Workflow `2.6.0`
**Governing workflow version:** `2.2` (the config default at creation: two-stage plan review, two-stage implementation review)
**Base commit:** `b2060bf462ec120c5ca4d284a3670b248c5828e8` (tip of `main`: `2.5.1` installed, protocol `2.2` activated, `docs/ROADMAP.md` and the open defect records committed)
**Deliverable:** a new authored Workflow release, `2.6.0`, built as
`distribution/workflow/2.5.1/` (base, **unchanged, byte-for-byte immutable**)
plus `migration/overlays/2.6.0/` (this milestone's own overlay), following
this repository's `CLAUDE.md` "Adding an authored Workflow release" process.
`docs/ROADMAP.md` section 1 is the scope source.

## 1. Goal

Close the Workflow correctness defects and gaps that `docs/ROADMAP.md`
section 1 groups under review artifacts, review publication, approval commit
integrity, legacy active-work-item compatibility, amendment artifacts and
cross-worktree concurrency. Do it as one bounded hardening release. Every
fix is justified by a defect or gap reproduced against the installed `2.5.1`
(section 3). Every fix preserves the Workflow's existing semantics except
where those semantics are the defect.

The release must:

1. Give each new work item its own current review-feedback surface
   (`.ai-review/<work-item-id>/feedback/REVIEW_FEEDBACK.md`), resolved by one
   authoritative resolver. Active legacy items keep working on the shared
   path.
2. Let an active work item whose artifact declarations predate the
   `.workflow-manager/` fix survive a committed `workflow_manager update`
   without an `UnclassifiedPathError`, without rewriting its approved
   declarations, and without moving any existing review identity.
3. Never let durable state advertise a plan revision as review-ready before
   a bundle bound to that revision exists. Make interrupted generation
   recoverable and idempotent.
4. Make the plan-approval commit contain every protected path the approved
   identity covers, proven before the commit exists.
5. Make post-commit approval verification and recovery derive truth from
   the committed transaction, never from pre-commit memory. This removes the
   observed `TypeError` and the false-mismatch path to a second commit.
6. Make checkpoint claims and plan-amendment claims mutually exclusive
   across linked worktrees. Close both causes of `v2.4.0-002`. Make the
   *resolution* of each amendment repository-unique too: at most one
   materially distinct resolution of an amendment sequence can become
   repository-valid (revision 7, `MPR-R1-I1`).
7. Make `AMENDMENT_DIFF.patch` show the amendment actually under review
   (`v2.4.0-003`).
8. Keep `v2.3.1-001`/`-002`/`-003` regression-protected.
9. Prove all of the above in disposable repositories and linked worktrees,
   including an update from the installed `2.5.1` baseline.

## 2. Non-goals

- **Not a Workflow redesign or operator-UX milestone.** No new review
  stages, no new phases, no new governing workflow version (section 6.3), no
  error-message sweep beyond the refusals this release introduces.
- **No persistent per-stage or per-round feedback trees.**
  `.ai-review/<id>/feedback/REVIEW_FEEDBACK.md` stays the single, current,
  ephemeral handoff surface. Durable review history stays in
  `WORKFLOW_STATE.json` ledgers, bundles and Git (`docs/ROADMAP.md` 1.1).
- **No `workflow-controller` change.** This repository never writes
  `~/Workspace/workflow-controller`. It ships the Workflow-side contract
  (section 5.1's resolver CLI) that Controller should consume instead of its
  own copy (`controller/evidence.py:170-194`). Adopting that contract is
  Controller's own milestone. No Controller branch, Draft-PR or release
  policy is designed here. Section 5.6 records only which identity facts the
  new repository-global witness keeps available for a future
  branch/base/worktree record.
- **No `workflow_manager update` tooling guard.** An update-time preflight
  that warns about active legacy items belongs to `docs/ROADMAP.md`
  milestone 5. So does the separate hazard found during investigation: an
  update rewrites a `process` item's *protected* `scripts/`/
  `.claude/commands/` mid-implementation (section 3.2). This release
  documents that hazard in the `v2.4.0-001` defect record and does not fix
  it.
- **No broad `.workflow-manager/` ignore** and no retroactive edit of any
  existing `<id>-artifacts.json`.
- **No change to any frozen release.** `distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/`
  stay byte-identical. The only new release tree is
  `distribution/workflow/2.6.0/`.
- **No change to the permanently-`"1"`-governed bootstrap path.**
  `/bootstrap-workflow-v2`'s own `publish_plan_revision` call for
  `workflow-v2-1-core` keeps its current phase behavior. Section 5.3 applies
  to `"2.1"`/`"2.2"`-governed items, the only ones `/milestone-plan` and
  `/apply-plan-review` publish for.
- **No RepFlow work.** Disposable RepFlow validation is `docs/ROADMAP.md`
  milestone 2.
- **No `USER_OVERRIDE` anywhere.**

## 3. Investigation findings

Every item below was investigated against the installed `2.5.1` code at
the repository root (`scripts/`, `.claude/commands/`, `docs/ai-workflow/`,
byte-identical to `distribution/workflow/2.5.1/payload/`). Reproductions
ran in disposable repositories outside this repository. Line references
are to `2.5.1`.

Every roadmap item turned out to be live. **No item is fully closed**, so
none converts to regression-only scope. The only regression-only items are
the three already-closed `v2.3.1-*` records (section 3.8).

| # | Item | Classification | Reproduced |
| --- | --- | --- | --- |
| 1 | Shared feedback path | current defect | yes: `FeedbackOwnedByOtherWorkItemError` for a new item; also hit by this repository at this milestone's creation (section 9) |
| 2 | Legacy `.workflow-manager/installation.json` | legacy migration gap (forward-fixed for new declarations) | yes: `UnclassifiedPathError` on 2.3.1-shaped and 2.4.0-shaped items after a committed update |
| 3 | `/apply-plan-review` publication ordering | current defect | yes, two variants |
| 4 | Plan-approval commit closure | current defect | yes: new, edited and renamed companion |
| 5 | Post-commit approval `TypeError` | current defect | yes: same traceback as the real Controller session, plus a worse false-mismatch variant |
| 6 | Cross-worktree amendment/claim (`v2.4.0-002`) | current defect (open) | yes: deterministic and end-to-end |
| 7 | `AMENDMENT_DIFF.patch` (`v2.4.0-003`) | current defect (open) | yes: 0 bytes vs 294 bytes |
| 8 | `v2.3.1-001/-002/-003` | already fixed; regression-only | existing tests pass |

### 3.1 Shared review feedback

- **The resolver.** `workflow_fingerprint.resolve_feedback_dir`
  (`scripts/workflow_fingerprint.py:1940-1949`) returns
  `.ai-review/<id>/feedback` only when that directory already exists, and
  otherwise the flat `.ai-review/feedback`.
- **Nothing ever creates the scoped directory.** No script, shell step or
  command does. `review-implementation.md:281-283` calls creating it by hand
  "not an endorsed remedy". So in practice every item uses the flat path.
- **The ownership guard.**
  `assert_feedback_not_owned_by_other_work_item` (`:2891-2920`) refuses when
  the existing flat file's `Work item:` names another item. It never
  consults state, so a `MILESTONE_COMPLETE` owner blocks exactly like a live
  one. It is invoked in prose at `/review-plan` step 8 and at both
  `/review-implementation` writers.
- **Reproduced, and hit here.** When this milestone was created, this
  repository's `.ai-review/feedback/REVIEW_FEEDBACK.md` belonged to the
  completed `workflow-2-5-1-checkpoint-id-compatibility`. A read-only call
  for any new id raised
  `FeedbackOwnedByOtherWorkItemError ... belongs to work item 'workflow-2-5-1-checkpoint-id-compatibility'`.
  Section 9 records how that precondition was discharged for this
  milestone's own review.
- **Durable review facts store no feedback path or content hash.**
  - `plan_review_stages`/`implementation_review_stages` hold
    `{review_content_id, <STAGE>: {bundle_id, verdict, round, completed_at}}`.
  - `technical_review_block_pins` is keyed by `bundle_id`.
  - Consequence: changing resolution for an item can never corrupt a
    recorded verdict. It can only orphan an *unconsumed* file, so legacy
    items must keep their resolution (section 5.1).
- **The consumed marker is shared across items.**
  `FUNCTIONAL_REVIEW.consumed` resolves through the same function, so it is
  shared across items today.
- **`/record-manual-*-review` never checks `Work item:`.** A stale foreign
  file is caught only by the `review_content_id` mismatch.
- **Controller reimplements the resolver.**
  `~/Workspace/workflow-controller/controller/evidence.py:170-194` copies
  scoped-else-flat and uses it at about 15 call sites. After this release it
  would look in the wrong place for new items unless it consumes the
  Workflow contract.

### 3.2 Legacy `.workflow-manager/installation.json`

- **Only two classification choke points.**
  - Plan stage: `classify_path` (`workflow_fingerprint.py:1305`).
  - Implementation stage: `classify_path_implementation_stage` (`:1660`).
  - Every gate reaches one of them, including
    `approval_review_content_id` -> `approval_is_current` ->
    `implementing_entry_reachable`, `any_protected_path_changed_since`, and
    the provenance-interval check (`workflow_state.py:11829`).
- **What the digest hashes.** Both stage projections (`:1461-1472`,
  `:1795-1806`) hash the declared *key strings* of the classification sets
  plus protected content. They never hash excluded content, and never a
  classifier-internal fallback.
- **Reproduced.** Bootstrap `2.3.1`, drive a synthetic item to
  `IMPLEMENTING`, update to `2.5.1`, and commit. The only non-payload changed
  path is `.workflow-manager/installation.json`. Then:
  - `implementing_entry_reachable` raises `UnclassifiedPathError`, as do
    both plan-stage digests and the implementation digest at `HEAD`.
  - A 2.4.0-shaped item raises at the implementation stage only.
- **The fix, tested as a patch.** An in-process patch that treats exactly
  that path as excluded, only where the classifier would otherwise raise,
  made every raising computation return. The plan-stage digests at `HEAD`
  and in the worktree **equal the stored `plan_approval`** (`dd54f5…b6b`).
  The product item's implementation digest **equals its pre-update value**.
  Every digest that was computable before is byte-identical, patched or
  not.
- **A separate hazard found along the way (out of scope, documented).** For
  a `process` item, the same update rewrote 21 *protected*
  `scripts/`/`.claude/commands/` paths. That moves the implementation digest
  on its own, independent of the classification fix. It is recorded, not
  fixed (section 2).
- **What `update()` writes.**
  - `src/workflow_manager/install.py:421-512` writes no other
    `.workflow-manager/*` file except the transient `installation.json.tmp`.
  - Every other path `update()` writes is already classified by legacy
    declarations.

### 3.3 `/apply-plan-review` publication ordering

- **The ordering.** `apply-plan-review.md` step 5 and `milestone-plan.md`
  step 3 call `publish_plan_revision` (`workflow_state.py:7755-7808`)
  *before* generation. That function sets both the `plan_revision` mirror
  and `phase = AWAITING_LOCAL_PLAN_REVIEW`.
- **Why the ordering exists, and what is actually wrong.**
  `D-Plan-Revision-Publication`/`WFR-65` requires the mirror to equal the
  registry before generation. `validate_state` and `prepare-ai-review.sh:94-112`
  both enforce this. So the *revision* must advance first. The defect is
  that the *phase* flip is coupled to it.
- **Nothing durable records plan-bundle identity.**
  - `current_bundle_id` exists in `default_work_item` (`:7639`) and has no
    writer.
  - `validate_local_plan_review_preconditions` (`:12368`) checks only
    version and phase.
- **Variant 1: withdrawn bundle.** With a stale `TEST_RESULTS.md`, the
  generator exits 1 and withdraws the bundle. State says
  `plan_revision: 2 / AWAITING_LOCAL_PLAN_REVIEW` with no bundle, and every
  coded check passes.
- **Variant 2: mixed bundle, worse.** With a stale `REVIEW_REQUEST.md`,
  `--write-manifest` fails (`workflow_fingerprint.py:3346`) *before*
  finalize.
  - Nothing is withdrawn and no marker is written.
  - `current/PLAN.md` says revision 2, while `MANIFEST.md` still says
    `plan_revision: 1` with a now-inconsistent `bundle_id`.
  - The archive is the complete revision-1 bundle.
  - Again every coded check passes.
- **Retry works but is undiscoverable.** A republish is a true no-op, but
  nothing durable says a retry is needed.

### 3.4 Plan-approval commit closure

- **A fixed member set.** `resolve_plan_stage_approval_commit_paths`
  (`workflow_fingerprint.py:1041`, `base_paths` `:1088`) returns
  `plan_path`, `registry_path`, `mapping_path`, `WORKFLOW_STATE.json`, plus
  a conditional `<id>-artifacts.json`. It never consults the declared
  `plan_stage.protected_paths`.
- **The identity covers more than that set.** It covers every declared
  protected path, snapshotted from the worktree (`_snapshot_worktree`
  `:1358`).
- **Omissions are invisible to the checks.** `assert_committed_path_set_matches`
  is a subset check, and `stage_plan_approval_commit_paths`
  (`workflow_state.py:2041`) never checks for omitted protected paths.
- **Reproduced, with a declared-protected `docs/ai-workflow/WI_COMPANION.md`:**
  - new, intent-to-add: `AbsentProtectedPathError` after the commit;
  - tracked and edited: `PostApprovalManifestMismatchError` after the
    commit;
  - renamed with a plain `mv`: `UnclassifiedPathError` at the commit.
- **Recovery cannot help.** Each failure appears only *after* the commit
  exists. Step 6a then routes into 6a1 amend recovery, which re-stages the
  same insufficient set and stops.

### 3.5 Post-commit bookkeeping `TypeError`

- **The real traceback.** It comes from a `workflow-controller` session:
  - `outcome COMMITTED`, then
  - `verify_post_approval_manifest_match` ->
    `workflow_state.py:2011 expected = record["approved_review_content_id"]`
    -> `TypeError: 'NoneType' object is not subscriptable`.
- **Root cause.** The journal design deliberately leaves the worktree's
  `WORKFLOW_STATE.json` pre-approval until step 6c materialize. But
  `approve-review.md:545-546` passes the command's own pre-commit
  `work_item` to the step-6a verifier.
- **First approval** (`plan_approval: None`): reproduces the `TypeError`
  exactly.
- **Prior `STALE`/`SUPERSEDED` approval** (post-fix re-approval, amendment
  re-approval): no `TypeError`. Instead a **false**
  `PostApprovalManifestMismatchError` against the *old* id. Step 6a routes
  any verification failure into 6a1 `git commit --amend`. That is the only
  path in the design that can replace an approval commit, and here it is
  triggered by a verifier-input error, not a tree defect.
- **Re-entry** after the crash hits the same failure.
- **Why the tests missed it.** The existing tests
  (`workflow_integration_test.py:5743`, `:4075`) hand-build a post-state
  dict, so they never exercise the command's real data flow.

### 3.6 Cross-worktree amendment/checkpoint (`v2.4.0-002`)

- **Both causes in the defect record are still present in 2.5.1:**
  - the per-worktree `WORKFLOW_STATE.lock` (`STATE_LOCK_PATH` `:1381`,
    acquired by `state_lock` `:1409`);
  - `claim_checkpoint` (`:4915`) reading only *this worktree's* state.
- **Reproduced end to end.** Worktree A committed `AMENDING_PLAN`. Worktree
  B then published `CP2` and moved it to `IN_PROGRESS`. A still saw
  `AMENDING_PLAN`, and `apply_plan_approval` (`:10779`) never consults
  claims.
- **Two further paths publish a claim without the phase gate:**
  - `take_over_claim` of an *absent* claim (user literal required);
  - `adopt_claim`.
- **The tests currently pin the open boundary.**
  `TestCrossWorktreeAmendmentClaimResidualXModelR9B1`
  (`workflow_state_test.py:11618`) passes today.
- **The item 372(h) census.** It is
  `docs/ai-workflow/dry-run/verify_372h_*.py`, enforced by
  `TestGlobalLockOrderItem372h` (`:9001`), and declares 8 primitives and 11
  edges. Its acyclicity rule is "blocking sources ∩ blocking targets = ∅".
- **Dead owners.** None of the existing primitives use liveness heuristics.
  `flock`s die with their holder, and claim removal is evidence-bound and
  literal-gated.

### 3.7 `AMENDMENT_DIFF.patch` (`v2.4.0-003`)

- **Where it is generated.** `scripts/prepare-ai-review.sh:470-471` (the
  `subprocess.run` call and its `git diff` argument list) diffs
  `amendment_base_commit..HEAD`, restricted to the *current*
  `sorted(metadata.protected_paths)`. The amended plan is uncommitted until
  approval, so the patch is always empty.
- **Reproduced through the real generator.** The shipped form gives
  0 bytes, packed into the archive. The working-tree form gives 294 bytes of
  the actual edit.
- **Untracked protected files are already visible to a working-tree diff.**
  The generator's own `git add -N` (`:138-141`) runs before the block, and
  its EXIT trap restores the index.
- **Not part of identity.** The file is hashed into neither `bundle_id` nor
  `review_content_id`.
- **No test runs this block today.**

### 3.8 Closed defects: regression-only

- **`v2.3.1-001`:**
  - `workflow_integration_test.py` ~6250
    (`test_the_historical_status_note_carries_a_dated_correction`, which
    skips without a host note);
  - `tests/test_conformance_suite.py:810`;
  - `migration/portability_exceptions.json` (2.5.x empty).
- **`v2.3.1-002`:**
  - `TestRequestPlanAmendment` (`:10808`),
    `TestReconcileCheckpointsAfterAmendment` (`:10692`),
    `TestAmendmentClaimRaceRealProcesses` (`:11404`),
    `TestApplyPlanApprovalAmendmentBranch` (`:11779`);
  - `tests/test_amendment_update_path.py`.
- **`v2.3.1-003`:**
  `TestPlanApprovalStateBlobPinAndMaterialize.test_pin_defaults_to_mode_100644_when_state_path_absent_at_head`
  (`workflow_integration_test.py:5331`).
- **Carry-forward.** Unchanged payload files carry forward byte-for-byte
  (`tools/build_release.py` ~`:340-351`). Replaced test files start from the
  `2.5.1` copy, and a deletion would show in `overlay_delta`.
- **Interaction with this release.** CP5 touches the first-approval path
  that `v2.3.1-003` protects (a first approval with no state at `HEAD` is
  exactly section 3.5's `TypeError` case). So CP5/CP8 must re-prove
  `v2.3.1-003` through the new verifier, not only through the unchanged
  unit test.

## 4. Invariants and recovery semantics (normative)

These come first. Sections 5 and 7 implement them and must never weaken
them.

- **INV-1: One durable truth per fact.** Review readiness, approval,
  amendment ownership and feedback location are each decided from exactly
  one durable source. That source is committed state, the Git tree, the
  journal, or the repository-global witness (for amendment ownership
  only). Every other artifact is a derived view checked against it.
- **INV-2: Publish only durable truths.** A phase that tells a reviewer or
  Controller "act now" is written only after every artifact that phase
  presupposes exists and verifies against durable identity:
  - `AWAITING_LOCAL_PLAN_REVIEW` presupposes a finalized bundle bound to
    `(work_item_id, plan_revision, review_content_id)`;
  - `COMMITTED` approval presupposes the reviewed tree.
- **INV-3: Fail closed on ambiguity.** Unreadable, torn, symlinked,
  unknown-valued or mutually inconsistent identity or state yields a named
  refusal, never a guess and never a raw `TypeError`/`KeyError`.
- **INV-4: Idempotent, convergent recovery.** Re-running any interrupted
  operation from any intermediate point reaches the same final durable
  result. It never advances a revision twice, never creates a second
  approval commit, and never publishes a second witness sequence for the
  same amendment.
- **INV-5: Exactly-once approval commit.** At most one commit carries
  `Workflow-Plan-Approval: <rcid>` for a work item's approval round.
  `git commit --amend` is reachable only for a proven tree-content defect
  of the commit this invocation just created, never for a record, input or
  verifier error.
- **INV-6: Repository-wide claims need repository-wide primitives.** A
  mutual exclusion between lifecycle claims that different linked worktrees
  can make is enforced by:
  - a primitive rooted at `git rev-parse --git-common-dir`; and
  - a repository-global witness readable from every worktree.

  A worktree whose local committed state is stale relative to the witness
  is refused, never trusted.
- **INV-7: Legacy compatibility is explicit.** Every rule that treats a
  pre-`2.6.0` work item differently is keyed on a durable fact recorded at
  that item's creation, or on a release-derived exact-path constant. It is
  never keyed on file shape, file existence alone, or the governing version
  (a protocol version, not a release). No legacy item's committed state or
  declarations are rewritten by the upgrade.
- **INV-8: Identity stability.** No change in this release moves any
  `review_content_id` or `bundle_id` that `2.5.1` could compute. A
  computation that used to raise may now return, and must then equal the
  value the approval recorded.
- **INV-9: Frozen releases are immutable.** `git diff <base_commit> --
  distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/` is empty at every
  checkpoint.
- **INV-10: One resolution per amendment sequence** (revision 7,
  `MPR-R1-I1`). Request identity and resolution identity are different
  facts, recorded separately. At most one resolution of amendment seq N
  (its approved `review_content_id`, `resolved_at_plan_revision` and
  `reconciliation_outcome`) is repository-valid. It is reserved
  repository-globally before any approval commit for it exists. Once
  recorded, it is never overwritten or reinterpreted. A worktree whose
  committed state carries a different resolution of the same seq is
  refused, never collapsed into the recorded one.

Recovery semantics per operation are stated with each design in section 5
(sections 5.3, 5.4, 5.6) and tested per section 8.

## 5. Design decisions

### 5.1 `D-Feedback-Layout` (CP3)

- **Durable stamp.** A new work-item field, `feedback_layout: "scoped"`.
  - It is written only at creation: by `route_work_item`'s fresh-id branch
    (`workflow_state.py:7651`) and `create_remediation_child_work_item`
    (`:10216`).
  - It is never written on resume, never changed, never back-filled.
  - Absent means legacy. Any other value refuses with
    `UnknownFeedbackLayoutError` (INV-3).
- **One authoritative resolver.** `workflow_fingerprint.resolve_feedback_dir(repo_root, work_item_id)`
  keeps its signature, so every existing call site and every command's
  `<feedback_dir>` prose stays valid. It reads the item's entry from the
  worktree's `docs/ai-workflow/WORKFLOW_STATE.json`:
  - **`"scoped"`**: returns `.ai-review/<id>/feedback`
    **unconditionally** (by construction, no existence gate).
  - **Entry present without the field, no entry at all, or no state file**
    (a pre-activation repository or a `"1"`-governed item, which carries no
    state entry by construction): the unchanged legacy rule, scoped if
    `.ai-review/<id>/feedback/` exists, else flat. So an active legacy item
    keeps finding its unconsumed flat file.
  - **State file present but unparseable**: refuses (INV-3), never falls
    back.
- **Directory creation.** `ensure_feedback_dir(repo_root, work_item_id)`
  creates the resolved directory. Every writer calls it: the three review
  writers, the functional-review consumed marker, and
  `/prepare-functional-review`. `/record-manual-*-review` and the
  gate-reporting steps print the exact resolved path the operator must paste
  into.
- **Machine-readable contract for external consumers.**
  `python3 scripts/workflow_fingerprint.py --resolve-feedback-path <work-item-id>`
  prints one JSON object:
  `{"work_item_id", "layout": "scoped"|"legacy-scoped"|"legacy-flat", "feedback_dir", "review_feedback_path", "functional_review_path"}`.
  - It uses the same function, with no second implementation.
  - It is documented in `REVIEW_PROTOCOL.md` "Bundle location" as the
    supported way for Controller or any other tool to locate feedback.
- **Ownership guards stay, with a bounded relaxation.**
  - For a scoped item the path is private, so a foreign legacy file is
    never consulted. This satisfies "completed legacy feedback never blocks
    a new work item" by construction.
  - For a **legacy** item resolving flat,
    `assert_feedback_not_owned_by_other_work_item` gains an optional
    `state` argument. An existing file whose `Work item:` names an entry at
    a **terminal** phase in current durable state is non-blocking: the
    overwrite is allowed, since terminal state proves no consumer remains.
  - A non-terminal owner, or an owner absent from state, still refuses.
  - The file is never reinterpreted as the new item's: the new writer
    replaces it whole, with its own binding fields.
- **Manual-record binding.** `/record-manual-plan-review` and
  `/record-manual-implementation-review` additionally refuse a pasted file
  whose `Work item:` is present and names a different item. A file without
  that field keeps today's behavior: the hard `review_content_id` check
  still binds it.
- **Coordinated updates required.**
  - `REVIEW_PROTOCOL.md` "Bundle location".
  - `MILESTONE_WORKFLOW.md`, which hard-codes the flat path at 155, 161,
    439, 447, 511, 554, 708 and 746-747; replace those with `<feedback_dir>`
    plus one normative definition.
  - `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, `PLAN_REVIEW_WORKFLOW.md`,
    `IMPLEMENTATION_REVIEW_WORKFLOW.md`, and every command listed in the
    investigation.
  - A new `WORKFLOW_V2_PLAN.md` design section, `D-Feedback-Layout`.
- **Rejected alternatives.**
  - Keying on the file's `Work item:` line: a hand-pasted manual verdict may
    omit it, and it decides ownership, not location.
  - Keying on `governing_workflow_version`: `"2.2"` items already exist
    under `2.5.x`.
  - Moving legacy items: this would orphan an unconsumed file mid-round.

### 5.2 `D-Tooling-Ambient-Classification` (CP1)

- **The constant.** `workflow_fingerprint.TOOLING_AMBIENT_EXCLUDED_PATHS = frozenset({".workflow-manager/installation.json"})`.
  It is an exact path, not a prefix.
- **Where it applies.** It is consulted by `classify_path` and
  `classify_path_implementation_stage` **only after every declared
  classification has failed, immediately before the `UnclassifiedPathError`
  raise**. Consequences:
  - It never overrides a declared protected or excluded entry.
  - It never enters the hashed classification sets.
  - It persists nothing.
  - It applies to every governing version, because classification is not
    version-dispatched.
- **How it is authorized and recorded.** It is **release-derived**. The
  constant is part of the reviewed `2.6.0` payload, approved through this
  milestone's plan and technical gates, and documented in
  `REVIEW_PROTOCOL.md` and the new `WORKFLOW_V2_PLAN.md` design section. No
  per-item metadata or operator action is involved.
- **Why this is trustworthy for approval identity (INV-8).** Declared
  classification decides first, and the set of paths that raise only
  shrinks. So every digest `2.5.1` could compute is unchanged. Every digest
  that raised only because of this path now equals the recorded approval,
  as section 3.2 reproduced.
- **What stays fail-closed.** `.workflow-manager/installation.json.tmp`,
  any other `.workflow-manager/*` path, and every other unclassified path
  still raise.
- **This is the first overlay replacement of `workflow_fingerprint.py`.**
  The plan-stage `classify_path` was described as frozen after its own
  round-10 review. What stays frozen is the *declared-classification*
  semantics, and this change leaves them untouched: it adds one terminal
  fallback for a single tooling-owned path. That path never existed in any
  Workflow payload or in the upstream repository the frozen semantics were
  written for. The plan states this justification in the design section and
  the overlay's classification rule.
- **Rejected alternatives.**
  - A per-item operator-authorized compatibility record: new persisted
    vocabulary, new downgrade constraint, another gate, no identity benefit.
  - Hand-editing legacy declarations: stales approvals.
  - Catch-and-rename the error: unblocks nothing.

### 5.3 `D-Plan-Review-Bundle-Binding` (CP4; revises `D-Plan-Revision-Publication`)

The design separates "the revision exists" from "the revision is
review-ready".

1. **Mirror-only publication.** `publish_plan_revision` (for
   `TWO_STAGE_PLAN_REVIEW_VERSIONS` items) writes `plan_revision`,
   `state_revision` and `last_transition` and **leaves `phase` unchanged**.
   The phase stays at whatever it was: `PLANNING`, `REVISING_PLAN` or
   `AMENDING_PLAN`. It also writes the `PUBLISHED` record (item 2).
   - WFR-65's "mirror before generation" invariant is kept exactly.
   - The function stays idempotent: the same revision and the same
     published `review_content_id` is a no-op.
   - **Only at a non-ready plan-stage phase: an allow-list, not a
     deny-list** (revision 4, `LPR-R3-001`; revision 5, `LPR-R4-002`).
     For a `TWO_STAGE_PLAN_REVIEW_VERSIONS` item, `publish_plan_revision`
     and `route_work_item`'s resume-branch revision advance
     (`workflow_state.py:7742`) run only at `PLANNING`, `REVISING_PLAN` or
     `AMENDING_PLAN`. Every other non-terminal phase refuses before any
     write, with one of two errors:
     - at a ready phase (`AWAITING_LOCAL_PLAN_REVIEW`,
       `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, `AWAITING_PLAN_APPROVAL`),
       `PlanReviewInProgressError`, naming the sanctioned exit, item 7's
       withdrawal (`/milestone-plan <id>`);
     - at any other phase (`IMPLEMENTING`, `SELF_REVIEWING_IMPLEMENTATION`,
       every implementation-review phase, `AWAITING_FUNCTIONAL_REVIEW`,
       and anything else outside the two sets), the new
       `PlanReviewPhaseNotPlanStageError`, naming the phase. When the
       phase is in `_AMENDMENT_REQUEST_ALLOWED_PHASES`
       (`IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION`,
       `workflow_state.py:10943`), the message names
       `/request-plan-amendment <id>` as the route back to planning;
       otherwise it names none, because `2.5.1` sanctions no plan re-entry
       from that phase.

     `2.5.1`'s `publish_plan_revision` flipped any non-terminal phase to
     `AWAITING_LOCAL_PLAN_REVIEW` (`:7790-7807`), so `/milestone-plan <id>`
     at `IMPLEMENTING` silently re-entered plan review without an
     amendment. `2.6.0` refuses that. The amendment mechanism
     (`2.4.0`) is the sanctioned route, and it lands on `AMENDING_PLAN`,
     which is on the allow-list.

     So no single call can leave a ready phase with a record other than
     `BOUND`: the only writers that run at a ready phase are `bind` (item
     3, which writes `BOUND` or refuses) and withdrawal (item 7, which
     leaves the ready phase in the same write). `"1"`-governed behavior of
     both functions is unchanged (section 2). That includes
     `/bootstrap-workflow-v2`'s step-1 call for the permanently
     `"1"`-governed `workflow-v2-1-core` at `IMPLEMENTING`.

     **The resume-branch callers** (revision 5, `LPR-R4-002`). Today the
     only command that calls `route_work_item` is `/milestone-plan` step 1
     (`grep -n "route_work_item(" .claude/commands/*.md`). Its
     remediation-child re-declaration is the same call, and it runs at
     `PLANNING`, because `create_remediation_child_work_item`
     (`workflow_state.py:10216`) creates the child at
     `default_work_item`'s `PLANNING` phase. So the allow-list refuses no
     sanctioned caller. CP4's mechanical enumeration re-derives this list
     from the payload rather than trusting this paragraph.
   - CP4 first enumerates, mechanically, every predicate in
     `workflow_state.py` and every command that reads the post-publication
     phase, including anything that treats `AMENDING_PLAN` as "not yet
     under review". Each one is adapted, or shown unaffected, in CP4's own
     evidence. The enumeration also lists every writer that can be
     attempted **at** a ready phase, and its decided behavior there:
     `route_work_item`, `publish_plan_revision`, the generator, `bind` and
     `withdraw_plan_review`.
2. **The durable discriminator: `plan_review_binding`** (revision 2,
   `LPR-R1-001`; revision 3, `LPR-R2-001`). A mirror equal to the
   registry, a non-ready phase and a bundle that verifies on disk is also
   the ordinary shape at the *start* of every round: a fresh local or
   manual `REVISE`, a fresh `AMENDING_PLAN`, or a round that does not
   advance the revision. Before the author edits anything, the reviewed
   bundle still verifies. So verification alone cannot decide whether
   binding is legitimate. Nor can "the content differs from what was
   reviewed": a session that dies partway through its edits differs too.
   "The edits are complete" is therefore its own durable fact. A new
   work-item field records all three facts:

   `plan_review_binding: {"status": "CONSUMED"|"PUBLISHED"|"BOUND", "at", "consumed", "published", "bound"}`

   - `consumed` is `{"review_content_id", "plan_revision", "legacy"}` or
     `null`: the content most recently taken out of review.
   - `published` is `{"review_content_id", "plan_revision"}` or `null`:
     the content the author last declared complete.
   - `bound` is `{"review_content_id", "bundle_id", "plan_revision"}` or
     `null`: the bundle last bound.

   The writers, by status (plus the legacy marker below):
   - **`CONSUMED`** is written by every transition that takes reviewed
     content out of review for editing, using **that transition's own
     inputs**, never a prior record:
     - `record_local_plan_review(verdict="REVISE")` and
       `record_manual_plan_review(verdict="REVISE")`: their own
       `review_content_id` argument and the current mirror;
     - `request_plan_amendment`: `plan_approval.approved_review_content_id`
       (the content being amended) and the current mirror;
     - `withdraw_plan_review` (item 7): the `BOUND` record's own `bound`
       fields.

     It sets `consumed` and clears `published` and `bound`. So the record
     is correct even for an item that entered review under `2.5.1` and
     was never bound.
   - **`PUBLISHED`** is written by `publish_plan_revision`, for
     `TWO_STAGE_PLAN_REVIEW_VERSIONS` items only. That function gains a
     keyword argument, `review_content_id`: the fresh plan-stage id,
     computed through `REVIEW_PROTOCOL.md`'s canonical entry point inside
     the same `state_transaction`'s mutator, after the registry
     regeneration and the table re-embed. It sets `published` and
     carries `consumed` forward unchanged.
     - **Staging precedes publish** (revision 4, `LPR-R3-003`). Computing
       `F` goes through `resolve_plan_stage_metadata`, which requires the
       plan, registry and mapping paths to be in the Git index
       (`_validate_plan_stage_metadata_path`'s tracked-path check). In
       `2.5.1`, `/milestone-plan` step 3 calls `publish_plan_revision`
       *before* its intent-to-add staging step (`milestone-plan.md:208-213`,
       then `:214-245`), which was harmless only because publish read no
       files. So the intent-to-add staging step moves ahead of the publish
       call, both in `/milestone-plan` (whose publish now sits at the
       publication point after step 5, below, with the staging step
       re-applied there) and in `/apply-plan-review` step 5's
       first-creation clause. Otherwise every brand-new work
       item's first publish would raise `InvalidPlanStageMetadataPathError`,
       which is outside the `⊥` set.
     - This call **is** the "edits declared complete" act. So
       `/apply-plan-review` step 5 now calls it on **every** round,
       whether or not the round advances the revision. The function is
       already idempotent on an unchanged revision.
     - **Every command publishes after its last protected edit**
       (revision 5, `LPR-R4-001`). A publish is only a true "edits
       complete" act when no later step of the same command can edit a
       plan-stage protected path. `2.5.1`'s `/milestone-plan` breaks that
       rule. It publishes inside step 3 (`milestone-plan.md:208-213`),
       then step 4 (`SELF_REVIEWING_PLAN`) says "Revise the plan in
       place" (`:246-249`). Step 4 must also confirm that the inherited
       `plan_stage` exclusion sets fit (`:175-177`), and those sets are
       hashed into the plan-stage id (`:191-196`). Step 5 may add flags to
       the plan. So `2.6.0` moves `/milestone-plan`'s publication out of
       step 3 into a new **publication point**, after step 5 and
       immediately before step 6 writes the author inputs and generates.
       In order, it:
       1. re-runs `generate_registry`/`generate_mapping`/
          `write_registry_and_mapping` at the round's `plan_revision`
          (the value step 1's `route_work_item` set). This is a
          byte-identical no-op when steps 4-5 changed no checkpoint or
          requirement, and it is required when they did;
       2. re-embeds `render_registry_markdown(registry)` into the plan
          document, unconditionally (the `I22` rule `/apply-plan-review`
          step 5 already follows);
       3. re-applies the intent-to-add staging step. It is idempotent, and
          it covers any plan-stage file that step 4 created;
       4. calls `publish_plan_revision(..., review_content_id=F)`, with `F`
          computed after items 1-3.

       Step 3 keeps its first registry, mapping, `<id>-artifacts.json`
       and table write, and its intent-to-add step, so self-review reads a
       complete, index-visible plan. What leaves step 3 is only the
       publish call. `WFR-65`'s ordering (mirror published before any
       bundle is generated) holds, because step 6's generation follows the
       publication point. `LPR-R3-003`'s ordering (intent-to-add before
       publish) holds too, and is now stronger: the staging step runs both
       in step 3 and again inside the publication point.

       `/milestone-plan` binds in step 6, straight after the generator
       succeeds, through the same `verify_plan_review_bundle` plus
       `bind_plan_review_bundle` call `/apply-plan-review` step 7' makes.
       Step 7's `assert_bundle_not_rejected` and its hand-off report then
       follow.

       `/apply-plan-review` already satisfies the rule. Its edits happen in
       steps 3-4, and step 5 regenerates, re-embeds and publishes. After
       the publish, step 5 writes only the `plan-inputs/` author files,
       which are not protected (item 5). Step 7' edits nothing and
       generates nothing (item 3 below: `2.5.1`'s step 7'.2 regeneration
       is removed for `2.x`). CP4's
       mechanical enumeration records this per command: every step that
       can edit a plan-stage protected path, and the publish call's
       position after all of them.
     - **No command exits between its publish and its bind** (revision 6,
       `LPR-R5-001`). This is the mirror of the rule above. Under `2.5.1`
       the publish itself wrote the ready phase, so any step after it
       could stop the command with the item already review-ready. Under
       `2.6.0` the publish is mirror-only and the bind is the only
       review-ready writer (item 3). So a command that stops after the
       publish and before the bind leaves the item at a non-ready phase
       with a `PUBLISHED` record (row 9). That is recoverable, but
       nothing announces it. `2.5.1`'s `/apply-plan-review` step 6 is
       such an exit: for a `"2.1"`/`"2.2"` item, "steps 1-6 execute
       identically" (`apply-plan-review.md:41-42`), and step 6
       (`:140-142`) stops the command on `BLOCK` or on a "major
       structural changes" judgment, before step 7' runs. `2.6.0`
       therefore changes step 6 as follows:
       1. **Step 6 does not apply to `TWO_STAGE_PLAN_REVIEW_VERSIONS`
          items.** For them, step 7' always runs after step 5, so every
          successful round ends bound at `AWAITING_LOCAL_PLAN_REVIEW`.
          This is the reviewer's first option. It matches step 7''s own
          rule, which never self-declares plan readiness "regardless of how
          large or small a 'structural change' judgment would call the
          edit". It also matches 7''s "sole path back" clause: every `2.x`
          round already returns to a fresh local review, so the
          structural-change judgment has nothing left to decide. The
          other option, binding inside step 6 before stopping, was
          rejected. It would give the same bind two call sites in one
          command for no behavioral difference. Step 6 keeps its `2.5.1`
          text for `"1"`-governed items (section 2).
       2. **A `2.x` `BLOCK` is never applied by `/apply-plan-review`.** A
          plan-stage `BLOCK` writes no transition. The item stays at its
          ready phase (`MILESTONE_WORKFLOW.md:246`, `:249`), where
          `/apply-plan-review`'s entry lands on rows 2-4d and never
          reaches step 1. The feedback can still meet the command at a
          non-ready phase: the shared feedback file is overwritten by a
          later verdict on the same content, and both the row-10 binding
          and the rows 9/11 durable check match on content alone. So for a
          `TWO_STAGE_PLAN_REVIEW_VERSIONS` item, step 1 accepts only
          `Status: REVISE`. That is the same condition the legacy-marker
          check already applies (item 6). `BLOCK` or `APPROVE` refuses
          before any write with `FeedbackStatusNotApplicableError`. The
          message names the ready-phase routes for a `BLOCK`: after the
          user resolves it, re-review the unchanged content (row 2), or
          edit and withdraw with `/milestone-plan <id>` (row 4a, item 7).
          Step 6's restated text says the same thing.
       3. **Every remaining exit between the publish and the bind reports
          the exact next command.** The only such exits are a generator
          failure, in `/apply-plan-review` step 5 or `/milestone-plan`
          step 6, and a crash. Each leaves row 9. The failure report names
          a re-run of the same command with the explicit id, whose entry
          resumes at row 9 (regenerate, then bind). It never names a
          review command, because `/review-plan` refuses at a non-ready
          phase.

          That list is exact only because `2.6.0` also **removes
          `/apply-plan-review` step 7'.2 for `2.x` items** (revision 7,
          `MPR-R1-O1`). `2.5.1`'s 7'.2 re-runs
          `./scripts/prepare-ai-review.sh ... plan <id>` a second time,
          after step 5 already generated the round's bundle, and has no
          failure report of its own. Kept, it would be a third generator
          failure exit between the publish and the bind, and an
          unreported one. The reviewer's first option is taken: **step 5
          is the round's single generation**, and step 7' becomes exactly
          (1) the recomputation note (unchanged 7'.1 text), (2)
          `verify_plan_review_bundle` plus `bind_plan_review_bundle`
          (item 3), and (3) the `AWAITING_LOCAL_PLAN_REVIEW` report and
          stop. Retaining 7'.2 with its own failure report was rejected:
          a second generation of unchanged content can only change
          `bundle_id` (a wrapper-only regeneration, advisory under item
          4), so it buys nothing and adds an exit. If step 5's bundle no
          longer verifies at step 7' (a crash or an operator edit between
          them), the bind refuses by cause (item 3). The item stays at
          row 9, or row 11 after an edit, and the refusal report names
          the same explicit-id re-run. `"1"`-governed step 7 is unchanged.

       CP4's enumeration records both properties per command: the publish
       after every protected edit, and no exit between the publish and
       the bind other than the reporting exits in item 3 above.
     - Re-publishing in the same round, after further edits, replaces
       `published`.
     - It refuses early with `ConsumedPlanReviewContentError` when the
       fresh id equals `consumed.review_content_id`, or, for a legacy
       marker, when `plan_revision` is not greater than
       `consumed.plan_revision`. `bind` repeats both checks (item 3).
       This early refusal only saves a wasted generation.
   - **`BOUND`** is written only by `bind_plan_review_bundle` (item 3).
   - A work item created under `2.6.0` starts in `PLANNING` with no
     record, and its first publish writes `PUBLISHED` with
     `consumed: null`.
   - **Legacy items (INV-7).** An item with no record in `REVISING_PLAN`
     or `AMENDING_PLAN` is a `2.5.1` item mid-round, and nothing durable
     says which content it already reviewed. It fails closed. The entry
     step of `/apply-plan-review` or `/milestone-plan` (item 6) writes, in
     its first `state_transaction`, a legacy marker:
     `{"status": "CONSUMED", "consumed": {"review_content_id": null, "plan_revision": <current mirror>, "legacy": true}, "published": null, "bound": null, "at": <now>}`.
     Until that marker exists, `publish_plan_revision` and `bind` both
     refuse with `LegacyPlanReviewBindingUnknownError`, naming that
     remedy.
     - **Legacy `AMENDING_PLAN` items use the amendment's own record**
       (revision 4, `LPR-R3-006`). A `2.5.1` amendment durably recorded,
       at request time, which content it took out of approval:
       `amendment_history[-1].superseded_plan_approval.approved_review_content_id`
       and `amendment_history[-1].superseded_plan_revision`
       (`workflow_state.py:11108-11118`). When the item's last
       `amendment_history` entry is unresolved and that id is non-null, the
       entry step writes a non-legacy `CONSUMED` record from those two
       fields (`"legacy": false`) instead of the null-id marker. That is
       exactly what `2.6.0`'s own `request_plan_amendment` would have
       written, it is an INV-7 fact recorded at request time, and it needs
       no forced second revision advance when `2.5.1`'s `/milestone-plan`
       step 1 already advanced the mirror before the update. Only when
       that id is absent does the null-id marker apply.
   - **Keyed on `review_content_id`, not `bundle_id`.** A wrapper-only
     regeneration legitimately changes `bundle_id` with unchanged content
     (`check_manual_stage_bundle_id_advisory`). Keying the refusal on
     `bundle_id` would let such a regeneration re-enter review with
     content that was already rejected.
   - `current_bundle_id` keeps being written by `bind` alongside the
     record. It is a reader-facing pointer, compared advisorily only
     (item 4). The record is the discriminator.
3. **The sole writer of the review-ready phase.**
   `bind_plan_review_bundle(state, work_item_id, *, binding, now)` is a pure
   mutator run inside `state_transaction`. Its `binding` input comes from
   the read-only verifier `verify_plan_review_bundle(repo_root, work_item_id)`,
   which returns a binding only when all of these hold:
   - `.ai-review/<id>/current/MANIFEST.md` is present;
   - the bundle is not rejected;
   - the manifest's `plan_revision` equals the state mirror;
   - the manifest's `review_content_id` equals a fresh recomputation;
   - the recomputed `bundle_id` of `current/` equals the manifest's and the
     archive's.

   Its refusals are named by cause (revision 4, `LPR-R3-001`/`-002`), so
   that every reader can print the matching remedy:
   - **`ReviewedContentDriftError`**: the bundle is internally consistent
     (the manifest, `current/` and the archive agree) but the fresh
     recomputation differs from the manifest's `review_content_id`. The
     worktree's protected content has drifted from what the bundle
     captured. This is the same error section 5.4 item 2 raises, so a
     drift is reported the same way at every gate;
   - **`PlanReviewBundleUnverifiedError`**: anything else (no bundle, a
     rejected bundle, a stale-revision manifest, a `current/`/manifest/
     archive disagreement).

   **Bind legitimacy lives entirely inside the mutator**, never in a
   caller's reading of the status (item 6). Against the freshly re-read
   state, `bind_plan_review_bundle` succeeds only when every one of these
   holds:
   - the phase is `PLANNING`, `REVISING_PLAN` or `AMENDING_PLAN`;
   - the record's status is `PUBLISHED`, and the binding's
     `review_content_id` and `plan_revision` equal `published`'s.
     Otherwise it refuses with `PlanReviewNotPublishedError`, so content
     the author never declared complete cannot bind;
   - the binding's `review_content_id` differs from a non-null
     `consumed.review_content_id`, and, for a legacy marker, its
     `plan_revision` is greater than the marker's. Otherwise it refuses
     with `ConsumedPlanReviewContentError`. A legacy mid-round item must
     therefore advance its revision once, which needs an edit. That is
     the fail-closed direction: "not bindable without an edit plus
     regeneration".

   On success it sets `phase = AWAITING_LOCAL_PLAN_REVIEW`, writes
   `current_bundle_id`, and writes the `BOUND` record with `bound` filled
   in and `consumed`/`published` carried forward.
   - **Idempotent.** A record already `BOUND` with the same
     `bound.review_content_id`, at `AWAITING_LOCAL_PLAN_REVIEW`, is a
     no-op, even when the binding's `bundle_id` differs (a wrapper-only
     regeneration, reported as advisory).
   - **Never regresses a phase** (revision 3, `LPR-R2-002`). Called at
     any other ready phase, it refuses with `PlanReviewAlreadyReadyError`
     and writes nothing. It can never move a manual-stage or
     approval-stage item back to local review.

   `transition_to_awaiting_local_plan_review` (`workflow_state.py:12547`)
   is retired as a free-standing writer. `apply-plan-review.md` step 7'
   becomes the bind call, and its 7'.2 regeneration is removed, so step 5
   is the round's only generation (item 2, revision 7, `MPR-R1-O1`). For
   `TWO_STAGE_PLAN_REVIEW_VERSIONS` items, step 6 no longer applies, so
   step 7' is always reached (item 2, revision 6, `LPR-R5-001`).
4. **Readers enforce the binding, keyed on `review_content_id`**
   (revision 3, `LPR-R2-002`).
   - `assert_plan_review_bundle_bound(repo_root, work_item_id)` re-runs
     the verifier. So `current/` is present, not rejected, at the mirror,
     internally consistent, and its manifest's `review_content_id` equals
     a fresh recomputation. It then requires a `BOUND` record whose
     `bound.review_content_id` equals that id.
   - It does **not** require `bundle_id == current_bundle_id`. A mismatch
     returns an advisory warning, reported the way
     `check_manual_stage_bundle_id_advisory` reports one today. A
     wrapper-only regeneration after the bind therefore never blocks the
     manual stage or approval. `2.5.1` documents that behavior and it is
     kept exactly (`workflow_state.py:12485-12501`,
     `record-manual-plan-review.md:86-91`, `PLAN_REVIEW_WORKFLOW.md:82-84`).
   - It is called by `validate_local_plan_review_preconditions` (through a
     repo-aware wrapper), `/review-plan`, `/record-manual-plan-review` and
     `/approve-review plan` step 2.
   - **Every refusal names its remedy** (revision 4, `LPR-R3-001`), per
     item 6's rows 4a-4d: restore the bound bytes from
     `current/files/<path>`, regenerate, or withdraw with
     `/milestone-plan <id>` (item 7). That includes an unreadable fresh
     id (`F = ⊥`, revision 5, `LPR-R4-003`), which the readers report as
     row 4a or 4c, never as a bare `PlanRevisionMismatchError` or
     `AbsentProtectedPathError`.
   - **Legacy ready items (INV-7).** An item that entered
     `AWAITING_LOCAL_PLAN_REVIEW`, `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`
     or `AWAITING_PLAN_APPROVAL` under `2.5.1` has no record and a null
     `current_bundle_id`. It is accepted when the on-disk bundle verifies.
     Nothing is back-filled, and its phase is never touched. Revision 2's
     back-fill is dropped because nothing needs it: the item's next
     `REVISE` writes a real `CONSUMED` record from its own inputs, and its
     next bind happens from a non-ready phase.
5. **A recoverable generator.** `prepare-ai-review.sh` assembles into
   `.ai-review/<id>/current.staging-<token>/` plus a temporary archive, and
   renames both into place only after `finalize_bundle_generation`
   succeeds.
   - Any failure from `--derive-plan-stage-document` onward removes the
     staging directory and leaves the previous `current/` intact (see the
     revised `WFR-67` semantics below). That
     previous bundle is harmless: it carries either an older revision or
     the `CONSUMED` content, never the `PUBLISHED` content. Either way
     `bind` refuses it.
   - The plan-stage pin moves with the bundle (revision 2, `LPR-R1-002`).
     `capture_plan_stage_pin` writes to a sibling
     `.ai-review/<id>/.pin.staging-<token>/`, which is renamed onto `.pin`
     in the same finalization step that renames `current/`, and removed on
     any failure. A failed generation therefore leaves the previous
     `current/` *and* the pin that produced it intact. The pin stays a
     sibling of `current/`, never inside it, so `compute_bundle_id` and
     INV-8 are untouched. The approval freshness check (section 5.4 item 2)
     does not depend on the pin at all.
   - This removes section 3.3's variant-2 mixed bundle.
   - The pair of renames is not atomic, so INV-2 rests on the bind
     verifier, not on the renames. A crash between them leaves a
     `current/` whose manifest, directory and archive disagree. The
     verifier refuses it with `PlanReviewBundleUnverifiedError` (row 4b or
     4c), and the named remedy is to regenerate. Leftover
     `current.staging-*`/`.pin.staging-*` directories are read by nothing
     and are removed by the next generation.
   - **Author-written inputs never touch `current/`** (revision 4,
     `LPR-R3-002`). Today the author writes `REVIEW_REQUEST.md`,
     `TEST_RESULTS.md` and `CONTEXT_FILES.txt` into `<bundle_dir>` before
     running the generator, which only stubs missing ones
     (`prepare-ai-review.sh:364-373`). Under staging, the plan stage reads
     them from a separate author-input directory,
     `.ai-review/<id>/plan-inputs/`, resolved by one new function,
     `workflow_fingerprint.resolve_plan_review_inputs_dir(repo_root, work_item_id)`.
     The generator copies each of the four author files
     (`REVIEW_REQUEST.md`, `TEST_RESULTS.md`, `CONTEXT_FILES.txt`,
     `IMPLEMENTATION_SUMMARY.md`) byte-for-byte into the staging directory.
     A file missing from `plan-inputs/` is seeded from `current/<file>` if
     that exists (read-only; the migration path for an author who has not
     yet moved), else stubbed empty as today. Every closing check,
     including `assert_review_request_states_review_content_id` and
     `assert_test_results_consistent_with_plan_review_request`, reads the
     staging copy. `plan-inputs/` is a sibling of `current/`, and the copy
     is byte-exact, so `bundle_id` is computed over exactly the bytes it
     would have been in place (INV-8). `/milestone-plan` step 6's and
     `/apply-plan-review` step 5's "write/refresh
     `<bundle_dir>/<file>`" prose becomes `<plan_inputs_dir>/<file>`,
     and `REVIEW_PROTOCOL.md` "Bundle location" defines `<plan_inputs_dir>`.
     So in the real command order (refresh the inputs, then generate),
     nothing writes `current/` until the final rename.
   - **Revised `WFR-67` semantics under staging** (revision 4,
     `LPR-R3-002`; a deliberate revision, recorded as such in the
     `D-Plan-Review-Bundle-Binding` text). `WFR-67` says "a failed
     closing binding assertion must leave no review-ready artifact". Under
     plan-stage staging, a failed generation's artifacts exist only in the
     staging directory, the staging pin and the temporary archive.
     `finalize_bundle_generation`'s failure path removes those three and
     **does not** call `withdraw_bundle` on `current/`, and **writes no
     `REJECTED` marker**. So the failed generation leaves no review-ready
     artifact of its own, as `WFR-67` requires. The previous `current/` is
     left in place: it is review-ready only for its own content, and only
     if it is still the `BOUND` one, which the readers check by
     `review_content_id` (item 4). A `REJECTED` marker written by `2.5.1`,
     or by an implementation-stage withdrawal, keeps its existing meaning:
     `assert_bundle_not_rejected` still refuses while it exists, and a
     successful generation still clears it (`workflow_fingerprint.py:2482`).
     A staging failure therefore never makes the readers refuse a
     still-bound previous bundle.
   - **Stage scope: plan stage only.** The implementation and post-fix
     stages keep `2.5.1`'s in-place generation, in-place author files and
     `withdraw_bundle` failure path, byte-for-byte. Nothing binds an
     implementation bundle, so staging buys them nothing, and leaving them
     alone keeps their flat-layout compatibility untouched. The script
     branches on `STAGE`, as it already does for the stub list.
6. **Resume rule** (revision 3, `LPR-R2-001`: one total decision table).
   `plan_review_publication_status(repo_root, state, work_item_id)` is
   read-only. It evaluates the table below top to bottom, and the first
   matching row wins. Its inputs are the durable facts (the phase, the
   registry's revision `R`, the mirror `M` and the record), plus the fresh
   plan-stage id `F`.
   - `F` is computed only in rows that need it. If computing `F` raises
     `AbsentProtectedPathError` or `PlanRevisionMismatchError`, `F` is
     read as `⊥`. Those errors mean a plan-stage file is absent, or the
     document's `(Revision N)` marker disagrees with the registry. Any
     other failure refuses (INV-3).
     - In a non-ready phase, `F = ⊥` means an edit in progress (row 11).
     - **At a ready phase, `F = ⊥` means drift, not a refusal** (revision
       5, `LPR-R4-003`). An author starting a re-plan by bumping the
       title, or deleting or renaming a declared protected file, has moved
       the worktree away from the reviewed content just as a byte edit
       does. So `F = ⊥` with a `BOUND` record is row 4a
       (`CONTENT_DRIFTED`), and `F = ⊥` with no record is row 4c
       (`LEGACY_UNVERIFIED`, because the verifier's own recomputation
       fails the same way). Both rows name an in-band exit. The readers
       (item 4) catch the same two errors from the verifier's
       recomputation and re-raise them as `ReviewedContentDriftError` or
       `PlanReviewBundleUnverifiedError` respectively, with the row's
       remedy text, chaining the original error. They never surface the
       bare error.
   - The status only routes. Legitimacy is decided by item 3's mutator,
     so a routing error can at worst send a run to a refusal. It can
     never bind consumed or unpublished content.

   | # | Phase | Record | Other facts | Status | Resume action |
   | --- | --- | --- | --- | --- | --- |
   | 1 | not a plan-stage phase (neither ready nor non-ready; terminal phases are already refused at entry) | any | - | `NOT_PLAN_STAGE`; both commands refuse at entry with `PlanReviewPhaseNotPlanStageError`, before any write (revision 5, `LPR-R4-002`) | none in-band from this phase; the message names `/request-plan-amendment <id>` when the phase allows an amendment (item 1) |
   | 2 | ready | `BOUND` | the bundle verifies, and `bound.review_content_id == F` | `BOUND` | nothing to do; report and stop (a `bundle_id` differing from `current_bundle_id` is reported as advisory) |
   | 3 | ready | none (a `2.5.1` item) | the bundle verifies | `BOUND` | as row 2; nothing is written |
   | 4a | ready | `BOUND` | `F` differs from `bound.review_content_id`, or `F = ⊥` (the worktree content drifted: a byte edit, a bumped `(Revision N)` title, or a deleted or renamed protected path) | `CONTENT_DRIFTED`; readers refuse with `ReviewedContentDriftError` | restore the bound bytes from `current/files/<path>` (row 2 again), or withdraw with `/milestone-plan <id>` (item 7) and take the normal path |
   | 4b | ready | `BOUND` | `F == bound.review_content_id`, but the bundle does not verify (a crash mid-rename, or a wrapper-only regeneration that failed after its renames began) | `BUNDLE_UNVERIFIED`; readers refuse with `PlanReviewBundleUnverifiedError` | regenerate (the content is unchanged, so row 2 then matches; the new `bundle_id` is advisory), or withdraw |
   | 4c | ready | none (a `2.5.1` item) | the bundle does not verify (section 3.3's variant 1 or 2 under `2.5.1`), including because `F = ⊥` | `LEGACY_UNVERIFIED`; readers refuse with `PlanReviewBundleUnverifiedError` | regenerate, then row 3 re-evaluates; or withdraw |
   | 4d | ready | `CONSUMED` or `PUBLISHED` (unreachable under `2.6.0` by item 1's ready-phase refusal; only a hand edit produces it) | - | refuses with `PlanReviewBindingInconsistentError` (INV-3) | withdraw with `/milestone-plan <id>`, which writes the fail-closed legacy marker (item 7) |
   | 5 | `REVISING_PLAN` or `AMENDING_PLAN` | none | - | `LEGACY_UNMARKED` | the entry `state_transaction` writes the legacy marker (or, for an open amendment with a recorded `approved_review_content_id`, the non-legacy `CONSUMED` record from item 2), then re-evaluates (row 10 or 11) |
   | 6 | non-ready | `BOUND` | - | refuses with `PlanReviewBindingInconsistentError`: every exit from a ready phase back to a non-ready one writes `CONSUMED` | - |
   | 7 | non-ready | any other | the registry does not exist yet (`PLANNING` before `/milestone-plan` step 3) | `NEEDS_EDIT` | the normal path |
   | 8 | non-ready | any other | `M < R` | `NEEDS_REVISION` | the edits were complete when the registry was regenerated; re-run the command's own publication step at `R` (`/apply-plan-review` step 5, or `/milestone-plan`'s publication point; the registry/mapping regeneration and the table re-embed are byte-identical no-ops if already done), then publish |
   | 9 | non-ready | `PUBLISHED` | `M == R == published.plan_revision` and `F == published.review_content_id` | `PUBLISHED_UNBOUND` | regenerate if no bundle verifies for `F`, then bind; never re-advance the revision |
   | 10 | non-ready | `CONSUMED`, not legacy | `M == R == consumed.plan_revision` and `F == consumed.review_content_id` | `NEEDS_EDIT` | the normal path, including `/apply-plan-review` step 1's full feedback binding against the on-disk bundle, which is still the reviewed one |
   | 11 | non-ready | anything else: every legacy marker, `M > R`, `F = ⊥`, or `F` differing from the record's latest id | - | `EDIT_IN_PROGRESS` | the normal path; `/apply-plan-review` step 1 uses the durable feedback check below, since the on-disk bundle may already have been regenerated |

   "Ready" means `AWAITING_LOCAL_PLAN_REVIEW`,
   `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` or `AWAITING_PLAN_APPROVAL`.
   "Non-ready" means `PLANNING`, `REVISING_PLAN` or `AMENDING_PLAN`.

   **Ready rows by command** (revision 4, `LPR-R3-001`). The "Resume
   action" column above is what `/apply-plan-review` and the readers do.
   `/milestone-plan <id>` entering an item at **any** ready row (2, 3 or
   4a-4d) instead performs item 7's withdrawal in its entry
   `state_transaction`, reports which phase and record it left, and then
   re-evaluates, landing on a non-ready row. This preserves `2.5.1`'s
   "re-planning a ready item returns it to local review" behavior, now
   through a transition that writes `CONSUMED` rather than a bare phase
   flip.
   - **The withdrawal never computes `F`** (revision 5, `LPR-R4-003`).
     At a ready phase, `/milestone-plan`'s entry decides "withdraw" from
     the phase alone. It does not call the status function first, and it
     does not need to know which ready row applies. Item 7 reads only the
     phase, the record and `amendment_history`. So an unreadable fresh id
     (a bumped title, a deleted protected path) can never block the
     named exit. The status function is evaluated only after the
     withdrawal, at the non-ready phase, where `F = ⊥` is row 11.
   - **Only with an explicit id** (revision 5, `LPR-R4-006`). The
     withdrawal makes the bound content permanently unbindable
     (`CONSUMED`) and discards both recorded stages, even at row 2, where
     nothing was edited. `2.5.1`'s flip left an unchanged re-run
     re-reviewable. So a `/milestone-plan` run with **no work-item-id
     argument** that resolves to an item at a ready phase refuses before
     any write (`PlanReviewWithdrawalNeedsExplicitIdError`). That covers
     both the no-argument form and the one-argument base-SHA form
     (`/milestone-plan <base-sha>`, `milestone-plan.md:21-25`), since
     neither names the target (revision 6, `LPR-R5-004`). Only a form
     whose argument is a `work_items` key withdraws: the one-argument
     `<id>` form, or the two-argument `<id> <base-sha>` form. The refusal reports the
     current row and what a withdrawal would discard, and names
     `/milestone-plan <id>` as the deliberate form. A named-id run reports
     the same consequences in its withdrawal report.
   - **Not during an open plan-approval journal** (revision 5,
     `LPR-R4-004`). Before the withdrawal, the entry calls
     `read_plan_approval_journal` (`workflow_state.py:2393`). If it
     returns a journal whose `work_item_id` is this item, the command
     refuses before any write (`PlanApprovalInProgressError`), naming
     `/approve-review plan <id>`'s own resume and takeover path. If the
     journal is unreadable (`PlanApprovalJournalUnavailableError`), the
     command refuses too: an undecidable journal is never read as "no
     transaction in progress", which is that function's own contract. The
     check lives in the command's entry, like the other entry checks.
     `withdraw_plan_review` stays a pure mutator.

   **"Edits complete" is never inferred.** Only rows 8 and 9 skip ahead
   of the normal path. Each rests on a fact the command writes only after
   the edits are complete:
   - row 8 on the registry regeneration in `/apply-plan-review` step 5;
   - row 9 on the `PUBLISHED` record.

   A mirror advance is deliberately not such a fact.
   `/milestone-plan` step 1's `route_work_item` advances the mirror
   before any edit (`workflow_state.py:7742`), so an amendment mid-edit
   has `M > R` and lands on row 11.

   **The durable feedback check** (rows 9 and 11; revision 3,
   `LPR-R2-007`). This applies to `/apply-plan-review` only. It replaces
   step 1's binding against the on-disk bundle: the feedback's
   `review_content_id` must equal `consumed.review_content_id`. For a
   legacy marker, which has a null id, the check is exactly (revision 4,
   `LPR-R3-006`): `parse_review_feedback_binding_fields` returns
   `work_item` equal to the target id and `status` equal to `REVISE`.
   There is no revision comparison, because that parser has no revision
   field (`workflow_fingerprint.py:2842-2857`) and `REVIEW_PROTOCOL.md`
   requires only the three binding fields. `/milestone-plan`,
   entering an `AMENDING_PLAN` item, has no feedback file and runs no
   feedback check in any row. There, `request_plan_amendment`'s own
   `CONSUMED` record is the binding.

   **When it is consulted.** It is called exactly once, at command entry:
   `/apply-plan-review` step 0 and `/milestone-plan`'s entry, after the
   target work item and governing version resolve and before step 1.
   At `/milestone-plan`'s entry, a ready-phase item is withdrawn first
   (see "Ready rows by command" above), and the status is evaluated
   after the withdrawal. Row 1's phase check runs before either, so a
   non-plan-stage item is refused before anything is written, including
   `route_work_item`'s mirror advance in step 1.
   That call's `state_transaction` also writes the legacy marker from
   item 2 when row 5 matches. A read-only CLI entry point exposes the same
   status to Controller.
7. **Withdrawal from review** (revision 4, `LPR-R3-001`).
   `withdraw_plan_review(state, work_item_id, now)` is a pure mutator run
   inside `state_transaction`. It is the one sanctioned way for a
   `TWO_STAGE_PLAN_REVIEW_VERSIONS` item to leave a ready phase for
   editing without a `REVISE` verdict, and `/milestone-plan`'s entry is
   its only command caller (item 6, "Ready rows by command"). It reads
   only the phase, the `plan_review_binding` record and
   `amendment_history`. It computes no fresh id and reads no plan-stage
   file, so no worktree state can make it raise (revision 5,
   `LPR-R4-003`). In one write it:
   - moves the phase to the matching non-ready phase: `AMENDING_PLAN` if
     the item's last `amendment_history` entry is unresolved (the same test
     `apply_plan_approval` uses, `workflow_state.py:10854`), else
     `REVISING_PLAN`. No new phase vocabulary is added;
   - writes `CONSUMED` from the `BOUND` record's own `bound`
     `review_content_id`/`plan_revision` (`"legacy": false`). Any other
     record, or none (a `2.5.1` ready item, or row 4d), gets the
     fail-closed legacy marker at the current mirror instead, so the next
     bind needs one revision advance;
   - leaves `plan_review_stages` untouched. A later bind of different
     content already reads both stages as absent through
     `plan_approval_gate_reachable`'s recomputation rule, exactly as after
     a `2.5.1` re-publish.

   It refuses at a non-ready phase (`PlanReviewNotReadyError`, writing
   nothing), so re-running `/milestone-plan` after a crash that followed
   the withdrawal simply finds the non-ready row. It never touches the
   bundle, the pin or `plan-inputs/`. The typo-at-local-review case is
   covered either way: restoring the bound bytes from
   `current/files/<path>` needs no state change at all (row 4a back to
   row 2), and `/milestone-plan <id>` is the in-band exit when the edit
   is meant to stay.

**Recovery semantics:**

| Crash point | Status | Next run |
| --- | --- | --- |
| fresh `REVISE` or `AMENDING_PLAN`, nothing edited yet | `NEEDS_EDIT` (row 10), or `EDIT_IN_PROGRESS` (row 11) for an amendment whose `/milestone-plan` step 1 already advanced the mirror | the normal path; `publish_plan_revision` and `bind` both refuse the unchanged content |
| mid-edit, in a bumping or a non-bumping `/apply-plan-review` round | `EDIT_IN_PROGRESS` (row 11) | the normal path; nothing binds |
| mid-edit, in an amendment or a first round under `/milestone-plan` | `EDIT_IN_PROGRESS` (row 11), or `NEEDS_EDIT` (row 7) before the registry exists | the normal path; nothing binds |
| `/apply-plan-review` step 5, after the registry regeneration, before publish | `NEEDS_REVISION` (row 8) | re-run step 5 at `R`, then publish |
| after publish, then further edits | `EDIT_IN_PROGRESS` (row 11: `F` differs from `published`) | the normal path; step 5 publishes again |
| after publish, before or during generation | `PUBLISHED_UNBOUND` (row 9) | regenerate, then bind |
| after generation, before bind, bumping or not | `PUBLISHED_UNBOUND`, with a bundle verifying for `F` | bind only |
| legacy item mid-round at update | `LEGACY_UNMARKED` (row 5), then `EDIT_IN_PROGRESS` once the marker exists | the normal path; the first publish and bind need one revision advance |
| after bind, including a later wrapper-only regeneration at any ready phase | `BOUND` (row 2) | nothing to do; the `bundle_id` mismatch is advisory |
| at a ready phase, the author edits a protected file (with or without regenerating) | `CONTENT_DRIFTED` (row 4a); `publish_plan_revision` and `bind` refuse, and no record changes | restore from `current/files/`, or `/milestone-plan <id>` withdraws and takes the normal path |
| a wrapper-only regeneration at a ready phase crashes between its renames | `BUNDLE_UNVERIFIED` (row 4b) | regenerate; row 2 again |
| a `2.5.1` ready item whose bundle was withdrawn or mixed before the update | `LEGACY_UNVERIFIED` (row 4c) | regenerate; row 3 again |
| `/milestone-plan <id>` re-run at any ready phase | withdrawal (item 7), then `NEEDS_EDIT` (row 10) or `EDIT_IN_PROGRESS` (row 11) | the normal path; the withdrawn content is `CONSUMED` and cannot re-bind |
| crash after the withdrawal, before any edit | non-ready row 10 or 11 | re-running `/milestone-plan` finds the non-ready row; withdrawal is not repeated |
| `/milestone-plan` step 4 or 5 edits the plan document or `<id>-artifacts.json` (revision 5, `LPR-R4-001`) | not yet published: the publish call sits after step 5 | the publication point regenerates the registry, re-embeds the table, re-stages and publishes the post-self-review `F`; step 6 generates and binds it |
| crash after the publication point, during self-review re-runs or generation | `PUBLISHED_UNBOUND` (row 9), or `EDIT_IN_PROGRESS` (row 11) if the content changed after the publish | row 9: regenerate, then bind; row 11: the normal path re-runs self-review and the publication point |
| at a ready phase, the author bumps the `(Revision N)` title or deletes a protected path (revision 5, `LPR-R4-003`) | `CONTENT_DRIFTED` (row 4a) with `F = ⊥`, or `LEGACY_UNVERIFIED` (row 4c) with no record; readers name both remedies | revert, or `/milestone-plan <id>` withdraws without computing `F`, then row 11 |
| a `2.x` `/apply-plan-review` round with "major structural changes" (revision 6, `LPR-R5-001`) | step 6 does not apply to `2.x`, so step 7' binds: `BOUND` (row 2) at `AWAITING_LOCAL_PLAN_REVIEW` | `/review-plan` |
| `/apply-plan-review` step 5's or `/milestone-plan` step 6's generator fails after the publish (revision 6, `LPR-R5-001`) | `PUBLISHED_UNBOUND` (row 9); the failure report names a re-run of the same command with the explicit id | the re-run regenerates, then binds |
| `2.x` feedback whose `Status:` is `BLOCK` or `APPROVE` meets `/apply-plan-review` at a non-ready phase (revision 6, `LPR-R5-001`) | refused at step 1 (`FeedbackStatusNotApplicableError`) before any write | a `BLOCK` is resolved at its ready phase: re-review (row 2), or edit plus `/milestone-plan <id>` |
| `/milestone-plan <id>` or `/apply-plan-review` at `IMPLEMENTING`, an implementation-review phase or `AWAITING_FUNCTIONAL_REVIEW` (revision 5, `LPR-R4-002`) | `NOT_PLAN_STAGE` (row 1) | refused at entry with nothing written; `/request-plan-amendment <id>` where the phase allows it |

In no row can a reviewer see a ready phase without a matching bundle. In
no row can already-reviewed or unpublished content enter review, and no
row advances the revision twice. No row is a sink: every ready-phase row
names an in-band exit, whose withdrawal needs no fresh id; no single call
leaves a ready phase holding a record other than `BOUND`; and no call
writes anything at a phase outside the plan-stage allow-list (row 1).

### 5.4 `D-Plan-Approval-Closure` (CP5)

1. **Commit members.** The approval commit's members are:
   - every declared `plan_stage.protected_paths` entry from the worktree
     declaration the approved identity was computed from;
   - `WORKFLOW_STATE.json`;
   - `<id>-artifacts.json`, under today's conditional rule;
   - **removals**: every path protected under `HEAD`'s committed
     declaration and tracked at `HEAD` that is absent from both the current
     declaration and the worktree, staged as a deletion.

   A rename is therefore a removal plus an addition. A path still present in
   the worktree that the current declaration no longer protects is not a
   member; the existing classification gates govern it.

   **First approval** (revision 2, `LPR-R1-009`): when `<id>-artifacts.json`
   is absent at `HEAD`, there is no committed declaration, so the removal
   set is empty by definition. The same holds for any path untracked at
   `HEAD`.
2. **Freshness before mutation, per member kind** (revision 2,
   `LPR-R1-002`; revision 3, `LPR-R2-002`). This runs after step 2's
   `assert_plan_review_bundle_bound` has proved that `current/` verifies
   for the `BOUND` record's `review_content_id`. A wrapper-only
   regeneration since the bind may have given `current/` a new
   `bundle_id`, but its protected captures are then the same content,
   because the generator's pin/worktree byte-identity check ties them to
   that id. The check reads that bundle, never `.ai-review/<id>/.pin`,
   which is a generation-time artifact:
   - **Protected members** (the declared `plan_stage.protected_paths`;
     revision 6, `LPR-R5-002`). The check is keyed on the bound bundle's
     own `base_commit`, the one its `MANIFEST.md` records. For each
     member, the expected bytes are:
     - the bound bundle's captured copy, `<bundle_dir>/files/<path>`,
       when that capture exists;
     - otherwise, the member's blob at `base_commit`, when the path exists
       there;
     - otherwise nothing, and the member refuses.

     The worktree bytes must equal the expected bytes. Why `base_commit`
     and not `HEAD`: `base_commit` is the generator's own capture
     condition. `files/` holds exactly the paths that differ between
     `base_commit` and the worktree (`git diff --name-status -z
     "$BASE_SHA"`, `prepare-ai-review.sh:497-510`). Untracked paths are
     included, because the generator marks them intent-to-add first
     (`:134-141`). The pin refresh never adds an entry
     (`workflow_fingerprint.py:2259-2267`). So at generation time, every
     protected member either was captured or was byte-equal to its
     `base_commit` blob. The rule therefore compares every member against
     what the reviewer actually saw, with no ungated hole. That includes a
     member that is unchanged since `base_commit` and so never captured
     (for example, a pre-existing design input the declaration protects,
     like `workflow-v2-1-core-artifacts.json`'s
     `docs/TECHNICAL_DECISIONS.md`). It is compared against its
     `base_commit` blob and approves.

     Gating on `HEAD` instead was rejected. A member can differ from
     `HEAD` and still equal its `base_commit` blob: a commit after
     `base_commit` touched the path, and the worktree reverted it. Such a
     member has no capture, so a `HEAD`-gated rule would need a second
     comparison source anyway, and `base_commit` is that source. A member
     that equals both `HEAD` and `base_commit` passes trivially under
     either key. The final "nothing expected" case can only mean drift. A
     path absent at `base_commit` that existed in the worktree at
     generation was captured, so a missing capture there means the path
     appeared after generation.

     This rule is **adapted from**, not identical to, the fifth-member
     rule (`resolve_plan_stage_approval_commit_paths`,
     `workflow_fingerprint.py:1097-1107`). That rule has a gate: it
     compares against the capture only when `<id>-artifacts.json` differs
     from `HEAD` ("unchanged since HEAD, no fifth member", `:1098`), and
     it refuses a missing capture only behind that gate. Here the gate is
     replaced by the base-commit fallback above, because a protected
     member, unlike the fifth member, is always a commit member (item 1).
     Adding a capture for every protected path in the generator instead
     was rejected, because it would move `bundle_id` for such bundles and
     break INV-8.
   - **`<id>-artifacts.json`**: the existing fifth-member rule, unchanged.
   - **`WORKFLOW_STATE.json`**: not compared. It changes by design, is
     excluded from the plan-stage identity, and its committed blob is
     already pinned and verified by the existing journal mechanism
     (`verify_committed_plan_approval_state_blob`).
   - **Removal members**: they have no bytes. Worktree absence is part
     of item 1's definition, so it is not a separate check here (revision
     5, `LPR-R4-005`). The check is that the path is absent from both the
     bound bundle's `files/` and its manifest's declared protected set. A
     reviewer who saw the file cannot have its deletion committed without
     a regeneration. The membership computation itself runs immediately
     before staging, inside the same journal step, so the worktree-absence
     condition is evaluated once, against the tree that is staged.
     A path that the current declaration no longer protects but that is
     present in the worktree, including one deleted and then re-created,
     is not a member (item 1). No deletion is staged for it, `HEAD`'s
     committed copy is left as it is, and the reviewed declaration, which
     no longer protects it, keeps it out of the plan-stage identity. That
     is the intended outcome, not a gap: the reviewer reviewed the
     declaration change, and the classification gates govern the path
     from then on.

   Any failure refuses **before any mutation** with
   `ReviewedContentDriftError`, naming the path and the member kind.
   Section 3.3's failed-regeneration case is covered by construction: a
   failed staging generation leaves the bound `current/` in place,
   byte-identical, because the author's inputs live in `plan-inputs/`
   (section 5.3 item 5). So worktree edits made after it are compared
   against what the reviewer actually saw.

   **Which check fires first** (revision 4, `LPR-R3-002`). An edit to a
   declared protected path moves the fresh plan-stage id, so step 2's
   `assert_plan_review_bundle_bound` already refuses it, with the same
   `ReviewedContentDriftError` (section 5.3 item 3, row 4a). The
   per-member check here is then reached only for what that id does not
   hash: a removal member still captured by the bound bundle (revision 5,
   `LPR-R4-005`) and the `<id>-artifacts.json` bytes outside its
   declared key sets. For
   protected members it stays as defense in depth (captured or
   `base_commit` bytes alike, revision 6, `LPR-R5-002`). Either way the error
   name is the same and no mutation has happened. The existing empty-index precondition remains, and its
   refusal message names the staged-`git mv` remedy.
3. **Pre-commit closure proof.** After staging, the approval runs
   `git write-tree` and recomputes the plan-stage `review_content_id`
   against that tree. This needs `compute_review_content_id_plan_stage_at_commit`
   generalized to a tree-ish. The result must equal the journal's
   `expected_review_content_id`. A mismatch takes the existing
   `NOT_COMMITTED` rollback, so no commit exists to amend.
4. **Committed-truth verification (the section 3.5 fix).**
   `verify_plan_approval_commit(repo_root, journal, commit)` runs, in order:
   - `verify_committed_plan_approval_state_blob`;
   - derives the work item **from the committed `WORKFLOW_STATE.json` at
     `commit`**;
   - requires its `plan_approval.approved_review_content_id` to equal
     `journal["expected_review_content_id"]`;
   - recomputes the identity at `commit` and requires equality;
   - runs a **two-sided** path-set check: every protected path that differs
     from the parent is in the commit, and nothing outside the member set
     is;
   - checks the artifacts blob.

   Both the in-session step 6a and every resumed or takeover step 6a use
   this one function.
5. **A named error instead of `TypeError`.** `verify_post_approval_manifest_match`
   takes an explicit `expected_review_content_id` and raises
   `MissingApprovalRecordError` on a `None` record. The implementation-stage
   caller gets the same named-error guard, since it shares the helper. The
   implementation-stage transaction is not otherwise changed.
6. **Amend gating.** Step 6a1's amend becomes reachable only through
   `classify_post_commit_verification_failure(...) == TREE_CONTENT`: a
   committed blob differing from the staged and pinned bytes, for example
   after a hook rewrite. Every record, input or verifier error stops with
   `HEAD` unchanged (INV-5). On an item with an open amendment, 6a1 also
   passes CP6's `assert_amendment_resolution_held` before it re-stages
   (section 5.6, revision 8, `LPR-R7-001`). The amend keeps its one-shot
   rule (`WF8c` 348(jj)).
7. **Declined.** Forward-completing a `COMMITTED` outcome without the
   takeover gate after the owner process died. The existing takeover gate is
   left exactly as is, and changing it is outside this defect's scope.

**Recovery semantics:** re-entry at any `progress` step converges through
`verify_plan_approval_commit` plus materialize/close. Discovery by trailer
plus first parent is unchanged. The number of approval-trailer commits is
provably 1 (tested).

### 5.5 `D-Plan-Amendment-5` revision (CP2)

- **The anchor.** `prepare-ai-review.sh` writes `AMENDMENT_DIFF.patch` as
  `git diff <amendment_base_commit> -- <pathspec>`, anchored at the working
  tree. The generator's own intent-to-add covers new untracked protected
  files.
- **The pathspec** (revision 2, `LPR-R1-003`; revision 3, `LPR-R2-004`)
  is the sorted union of:
  - the `plan_stage.protected_paths` declared in `<id>-artifacts.json` **at
    `amendment_base_commit`** (read with `git show`; empty if the file is
    absent there);
  - the ones declared now; and
  - `<id>-artifacts.json` itself. The declaration is not a plan-stage
    protected path (the manifest's protected set is the plan, the registry
    and the mapping), so without this member a declaration edit would not
    appear at all.

  This answers the reviewer's actual question: what changed in the
  protected design set since the amendment base. A path that is still
  declared protected cannot be deleted: `capture_plan_stage_pin` raises
  `AbsentProtectedPathError` before this block runs. So the only reachable
  deletion is a path **dropped from the declaration** and removed from the
  worktree. It is in the base-side half of the union, and appears as
  `deleted file`. A rename is that same deletion plus a newly declared
  path appearing as `new file`. Git's rename detection is not relied on,
  and the patch applies either way. A path dropped from the declaration
  but still present in the worktree appears as its content diff only if
  it changed since `amendment_base_commit`. Either way, the
  `<id>-artifacts.json` hunk shows it leaving the protected set, so a
  reviewer who reads only the patch still sees every declaration change.
- **Provenance preamble.** A leading comment block names `work_item_id`,
  the amendment sequence, `amendment_base_commit`, `plan_revision` and the
  bundle's `review_content_id`. `git apply` ignores text before the first
  `diff --git`, so the patch stays applicable.
- **Consistency with the reviewed bytes.** The patch is written after the
  pin snapshot. The generator's existing pin/worktree byte-identity check
  covers every currently declared path, so for those paths the diff
  describes exactly the bytes the bundle's `review_content_id` hashes.
  Base-only paths (the deletion half of the union) are outside the current
  identity by definition. They are shown so that the protected set's
  shrinkage is visible, never hashed. `<id>-artifacts.json`'s bytes are
  outside both identities too; only its declared key sets are hashed,
  so showing it changes no identity.
- **Still convenience-only.** It sits outside `current/` and is hashed into
  neither `bundle_id` nor `review_content_id`.
- **Documentation.** `REVIEW_PROTOCOL.md` "Bundle structure",
  `request-plan-amendment.md` step 4 and `WORKFLOW_V2_PLAN.md`
  `D-Plan-Amendment-5` are restated to the working-tree anchor. The
  generator-mention census wording that `workflow_integration_test.py`
  pins is kept.

### 5.6 `D-Repo-Global-Lifecycle` (CP6; closes `v2.4.0-002`)

**Lifecycle lock (new primitive 9).**
- **Path.** `<git-common-dir>/ai-workflow/checkpoint-claims/<token>.lifecycle.lock`,
  a per-work-item `flock` that is never unlinked. It has the same shape as
  `guard_mutation_lock`.
- **Pure source.** It is acquired only while holding no other primitive. A
  process-local held-set asserts this.
- **Acquired by:**
  - `claim_checkpoint`, as (9) → (2) `state_lock` → witness check → local
    phase check → `_claim_or_refuse`;
  - the new `request_plan_amendment_transaction` entry point, which wraps
    `state_transaction(request_plan_amendment)`;
  - `adopt_claim`, and `take_over_claim` of an absent claim, both before
    (6)/(5);
  - `advance_amendment_witness`;
  - the new `reserve_amendment_resolution` and
    `release_amendment_resolution` (revision 7, `MPR-R1-I1`; "Resolution
    side" below).
  - the new `assert_amendment_resolution_held` (revision 8, `LPR-R7-001`),
    at 6a1 amend recovery only.
- **No bypass.** The pure `request_plan_amendment` mutator asserts that (9)
  is held. On an item with an open amendment, `open_plan_approval_journal`
  records no reservation of its own. The step-5 staging entry takes an
  explicit mode and asserts the evidence that mode requires (revision 8,
  `LPR-R7-001`, narrowing revision 7's single assertion):
  - **`first_commit`** (the in-session 4c → 4d → 5 path, the only path that
    can create an approval commit): a `RESOLVING` witness whose reservation
    `reserve_amendment_resolution` wrote at 4d for this journal's current
    `owner_token`;
  - **`amend_recovery`** (6a1's re-staging, reached only after 6a
    classified `COMMITTED`, so a commit for this journal already exists
    and no new resolution can be created): a passing
    `assert_amendment_resolution_held` for this journal, made at 6a1's
    entry.

**Amendment witness (the repository-global lifecycle record).**
- **Path.** `<same dir>/<token>.amendment.json`, written with tempfile plus
  `os.replace`, so it is not a new `os.link` primitive under the census
  predicate.
- **Fields:** `schema_version`, `work_item_id`, `amendment_seq`
  (`len(amendment_history)`), `status`
  (`OPEN`|`RESOLVING`|`RESOLVED`|`NONE`), `amendment_base_commit`,
  `requester_worktree_root`, `requester_worktree_git_dir`,
  `requester_branch`, `state_revision`, `requested_at`,
  `request_projection_sha256`, `resolved_at_plan_revision`,
  `resolved_commit`, `resolution_projection_sha256` (`RESOLVED` only;
  revision 7), `resolution_reservation` (`RESOLVING` only; revision 7),
  and, for `OPEN` and `RESOLVING`, `previous` (the fields of the witness
  it replaced, used by the orphan rollbacks). `requester_branch` is
  `null` when the requester's `HEAD` was detached.
- **The resolution reservation** (revision 7, `MPR-R1-I1`) is an object:
  `journal_owner_token` (the plan-approval journal's `owner_token` at
  reservation time), `resolver_worktree_root`, `resolver_worktree_git_dir`,
  `resolver_branch` (`null` if detached), `pre_procedure_head` (the
  journal's), `approved_review_content_id` (the journal's
  `expected_review_content_id`), `resolution_projection_sha256` (see
  below, computed from the journal's `expected_post_state`), and
  `reserved_at`.
- **The request projection** (revision 4, `LPR-R3-005`). One function,
  `amendment_request_projection_sha256(entry)`, defines it: the SHA-256 of
  the canonical JSON (`sort_keys=True`, `separators=(",", ":")`,
  `ensure_ascii=False`, UTF-8) of the `amendment_history` entry with the
  three resolution-time keys `resolved_at_plan_revision`,
  `reconciliation_outcome` and `resolved_review_content_id` (revision 7)
  removed. That leaves exactly the request-time
  fields `request_plan_amendment` writes (`workflow_state.py:11108-11118`):
  `amendment_id`, `requested_at`, `requested_from_phase`, `reason`,
  `superseded_plan_revision`, `superseded_plan_approval`,
  `checkpoints_snapshot` and `pre_amendment_approval_commit`.
  `request_plan_amendment_transaction` computes the new entry inside its
  mutator, then writes the `OPEN` witness carrying that digest, then
  publishes the state. A `RESOLVED` witness carries the digest forward;
  `NONE` has `null`. Bootstrap step 3 and the lagging-worktree comparison
  both use this one function, so every "same entry?" question in 5.6 is
  answered by one computation over stored data.
- **The resolution projection** (revision 7, `MPR-R1-I1`). The request
  projection deliberately cannot tell two resolutions of the same request
  apart, so resolution identity is a second, separate digest.
  `amendment_resolution_projection_sha256(entry)` is the SHA-256 of the
  same canonical JSON of the object `{"request_projection_sha256": <the
  entry's request projection>, "resolved_at_plan_revision": ...,
  "reconciliation_outcome": ..., "resolved_review_content_id": ...}`,
  with an absent key taken as `null`. It is defined only for a resolved
  entry (`resolved_at_plan_revision` non-null); every caller checks that
  first.
  - **`resolved_review_content_id`** is new resolution-time vocabulary on
    an `amendment_history` entry. `2.6.0`'s `apply_plan_approval` writes
    it next to `resolved_at_plan_revision`, equal to the approval
    record's `approved_review_content_id`. So two resolutions of the same
    request that approved different amended plans differ even when their
    revision and `reconciliation_outcome` agree. `reconciliation_outcome`
    is the `{checkpoint id: outcome}` map `reconcile_checkpoints_after_amendment`
    returns, and it determines the resulting checkpoint validity, so the
    digest covers that too. Because the journal's `expected_post_state` is
    computed by the same `apply_plan_approval`
    (`workflow_state.py:2275` onward), the reservation's digest is
    computable before any commit exists. It equals the committed entry's
    digest by construction.
  - **Legacy entries** resolved by `2.5.1` have no
    `resolved_review_content_id`. The key is `null` in their digest,
    everywhere. Two copies of the same legacy resolution (one approval
    commit, merged or cherry-picked) are byte-identical entries, so their
    digests agree. A `2.5.1` resolution and a `2.6.0` resolution of the
    same seq always differ (`null` versus an id), which is correct,
    because they are two approvals. The one blind spot is two
    independent `2.5.1` resolutions of the same seq with equal revision
    and equal outcome. Upgrade bootstrap adds a trailer-derived check for
    exactly that case (bootstrap step 3). Only a legacy resolution landed
    without its `Workflow-Plan-Approval:` trailer (for example, squashed)
    stays compared on revision and outcome alone. That is stated in the
    residual below.
- **Lifecycle.** It is advanced, never deleted. The orphan rollback
  below rewrites it to its `previous` content. A torn, symlinked or unknown-schema witness refuses, like a claim.
- **A gate, not an authority.** It can only cause refusals; committed Git
  state remains authoritative.

**Predicates, evaluated under (9).** "`HEAD` shows seq N resolved" always
means that the item's entry in the **`HEAD`-committed**
`WORKFLOW_STATE.json` of the worktree evaluating the predicate has
`len(amendment_history) >= N` and `amendment_history[N-1].resolved_at_plan_revision`
non-null. Working-tree state is never used for this test; it is committed
truth only (revision 2, `LPR-R1-004`).

All three sides (claim, amendment and, since revision 7, resolution) run
the mixed-release lag probe (below) first, then evaluate
the witness in this **fixed order**, before anything else. The order is identical for every side, so self-heal always runs
before an `OPEN` or `RESOLVING` refusal:

1. **Witness `OPEN` or `RESOLVING` at seq N, and a committed resolution
   of seq N is visible.** "Visible" means the evaluating worktree's
   `HEAD` shows seq N resolved, or, for `RESOLVING` only, the resolver
   worktree's `HEAD` or the tip of `refs/heads/<resolver_branch>` does.
   In that case the approval already landed, and only the witness
   advance was lost. Compute that entry's
   `amendment_resolution_projection_sha256` (revision 7):
   - `RESOLVING`, and the digest equals the reservation's: advance the
     witness to `RESOLVED` with that digest (the `advance_amendment_witness`
     write, done inline under the (9) already held), then continue at
     step 3;
   - `RESOLVING`, and the digest differs: refuse with
     `AmendmentResolutionConflictError`, naming both digests and the
     worktree or branch holding the unreserved resolution. The witness is
     unchanged. **Exception** (revision 8, `LPR-R7-001`): when the only
     differing resolution visible is on the resolver's own `HEAD` or
     `resolver_branch` tip, and the resolver worktree still has an open
     plan-approval journal whose `owner_token` or `previous_owner_tokens`
     contains `journal_owner_token`, this is the reserving transaction's
     own commit awaiting 6a1 amend recovery (a hook rewrote the committed
     `WORKFLOW_STATE.json` blob). Refuse with
     `AmendmentResolutionReservedError` instead, naming the open
     transaction. The witness is unchanged in both cases, and neither is
     ever an advance;
   - `OPEN` (no reservation exists; under `2.6.0` only a lagging `2.5.1`
     resolver can produce this, see the residual): advance to `RESOLVED`
     binding that entry's digest, then continue at step 3. The first
     resolution a (9) holder observes is bound. Any different one is
     refused from then on by step 3.
2. **Witness `OPEN` at seq N otherwise**: apply the provable-orphan
   rollback test (crash table below). If it proves an orphan, roll back
   to the witness's own `previous` object and re-enter this list.
   Otherwise:
   - claim side: refuse with `AmendmentInFlightError`, naming the
     requesting worktree, branch and sequence. This closes cause 2
     regardless of the claimer's local phase;
   - amendment side: refuse, since concurrent amendments would fork
     `amendment_history`;
   - resolution side (revision 7): continue to its own checks below.
     `OPEN` is the one state a resolution may reserve from.
2a. **Witness `RESOLVING` at seq N otherwise** (revision 7,
   `MPR-R1-I1`): apply the provable-orphan *reservation* test (crash
   table below). If it proves an orphan, roll back to the witness's own
   `previous` object (the `OPEN` witness it replaced) and re-enter this
   list. Otherwise:
   - claim side: `AmendmentInFlightError`, as in step 2. The amendment is
     still unresolved;
   - amendment side: refuse, as in step 2;
   - resolution side: if the evaluating worktree's own open plan-approval
     journal for this item has an `owner_token` or `previous_owner_tokens`
     entry equal to the reservation's `journal_owner_token`, this is the
     reserving transaction itself. Continue to its own checks, where
     reservation is an idempotent no-op. No command path reaches this
     branch (revision 8, `LPR-R7-001`: 4d runs only in the invocation that
     opened the journal at 4c, whose `RESOLVING` witness it has not yet
     written). It exists so the function is idempotent when called
     directly, and CP6 test 21 calls it that way. Otherwise
     refuse with `AmendmentResolutionReservedError`, naming the resolver
     worktree, its branch, the reserved `approved_review_content_id` and
     `reserved_at`. **No second worktree can begin an approval commit for
     the same seq.**
3. **Witness `RESOLVED` at seq N**: the evaluating worktree's `HEAD` must
   show seq N resolved. Otherwise refuse with `StaleLifecycleStateError`
   ("merge the resolved amendment first"). This is the same test on every
   side; for the amendment side it replaces revision 1's ambiguous
   "local history length N". On the resolution side it means a second
   worktree cannot approve seq N at all once it is resolved elsewhere,
   whether or not its amended plan is the same one. It merges the
   recorded resolution instead. **Revision 7:** when `HEAD` does show seq
   N resolved, its entry's `amendment_resolution_projection_sha256` must
   also equal the witness's `resolution_projection_sha256`. Otherwise
   refuse with `AmendmentResolutionConflictError`, naming both digests.
   No literal is offered: this is a real second resolution, not a crash.
   The remedy is to discard the divergent approval on that branch and
   merge the recorded one. An identical resolution (the same approval,
   merged or cherry-picked) has the same digest and passes, however many
   worktrees show it.
4. **Witness `NONE`** (revision 4, `LPR-R3-007`): no amendment has ever
   been recorded. Continue to the side's own checks. On the amendment
   side, the `OPEN` witness it then publishes has `amendment_seq: 1` and
   `previous` equal to this `NONE` witness.
5. **Witness absent**: the upgrade-bootstrap derivation below, which ends
   by writing a witness or a `NONE` sentinel (or, while a worktree lags,
   an in-memory "no amendment" result that is treated as step 4), then
   re-enters this list at the matching step.

Then each side's own checks run:

- **Claim side** (`claim_checkpoint`, `adopt_claim`, absent-claim
  `take_over_claim`): the existing local phase check, then
  `_claim_or_refuse`.
- **Amendment side:**
  - the existing `resolve_claim` quiescence read, now serialized with every
    claim publication by (9). This closes cause 1;
  - only after every validation passes does it publish the `OPEN` witness
    (seq = current `HEAD`-and-working-tree history length + 1), then the
    state, both inside (9).
- **Resolution side** (`/approve-review plan` on an item with an open
  amendment; revision 7, `MPR-R1-I1`, replacing revision 6's
  "approval side", which advanced the witness only after the commit and so
  never serialized the resolution itself).
  - `open_plan_approval_journal`'s amendment branch refuses if any live
    claim exists for the item (defense in depth, unchanged).
  - **Reserve before any commit.** A new `/approve-review plan` step 4d,
    right after 4c opens the journal and before step 5 stages anything,
    calls `reserve_amendment_resolution(repo_root, work_item_id,
    journal)`. It holds (9) and nothing else, outside every
    `plan_approval_guarded_mutation` window, and runs the lag probe and
    the predicate list as the resolution side. Its own checks then
    require all of these:
    - the working-tree state's last `amendment_history` entry is seq N,
      unresolved, and its request projection equals the witness's
      `request_projection_sha256`. Any other witness (`NONE`, a different
      seq, or a different digest) refuses with `StaleLifecycleStateError`,
      naming both;
    - the journal's `expected_post_state` resolves that same entry N.
      Its `amendment_resolution_projection_sha256` is the digest being
      reserved.

    On `OPEN` it writes `RESOLVING` with the reservation object, and with
    `previous` equal to the `OPEN` witness. On `RESOLVING` whose
    reservation is this journal's own (predicate step 2a), and whose
    digest and `approved_review_content_id` equal this journal's, it is a
    no-op. The same token with a different digest cannot happen, because
    the journal's expected post-state is pinned at open. It refuses as
    INV-3 if it does. A refused reservation happens before any staging,
    so step 6b's existing `NOT_COMMITTED` rollback applies unchanged. It
    closes the journal and writes nothing else.
  - **4d is the only reservation point** (revision 8, `LPR-R7-001`,
    replacing revision 7's "every entry into step 5 or step 6
    re-reserves", which described a resume flow `/approve-review` does not
    have). `approve-review.md` step 4b is unchanged (section 5.4 item 7):
    with a journal open, a fresh invocation reports and stops, and a
    takeover resumes at 6a, skipping 4c-6. So a taken-over transaction
    never reaches 4d or first-commit staging. It reaches only 6a, and from
    there 6a1, 6b or 6c. A crash between 4c and 4d is therefore recovered
    by 4b stop, takeover, 6a `NOT_COMMITTED` (`HEAD` is still
    `pre_procedure_head`, because nothing was staged), 6b rollback, and a
    release that is a no-op (the witness is still `OPEN`, and it carries no
    reservation of this journal's). No reservation is needed and no commit
    exists. The user then re-runs `/approve-review plan`, which opens a
    fresh journal and reserves at 4d. If another worktree reserved in the
    meantime, that fresh run refuses at 4d with
    `AmendmentResolutionReservedError` and takes 6b, still before any
    commit.
  - **6a1 amend recovery holds the resolution; it does not reserve**
    (revision 8, `LPR-R7-001`). 6a1 is the one re-entry into step 5 after
    a journal is open. It is reached in session or after a takeover, only
    when 6a classified `COMMITTED` and `classify_post_commit_verification_failure`
    returned `TREE_CONTENT` (section 5.4 item 6). A commit for this journal
    already exists, so 6a1 must not create or re-bind a resolution. At
    6a1's entry, before the `step-7b-amend-stage` guarded window, it
    calls `assert_amendment_resolution_held(repo_root, work_item_id,
    journal)`. That takes (9) alone, outside every guarded window, and
    **does not run the predicate list and never writes the witness**.
    Its digest source is the journal's pinned `expected_post_state` entry
    N (`amendment_resolution_projection_sha256` of it), never the digest
    `HEAD` shows, because `HEAD`'s committed `WORKFLOW_STATE.json` blob may
    itself be the tree-content defect 6a1 exists to repair. It accepts
    exactly two witnesses:
    - `RESOLVING` at seq N whose reservation's `journal_owner_token` is
      this journal's `owner_token` or one of its `previous_owner_tokens`,
      and whose `resolution_projection_sha256` and
      `approved_review_content_id` equal the pinned values (the ordinary
      case, in session or after a takeover);
    - `RESOLVED` at seq N whose `resolution_projection_sha256` equals the
      pinned digest. Another worktree's (9) holder self-healed it through
      predicate step 1 from the pre-amend commit, which is possible only
      when the defect was in some other member, so the committed state
      blob was already correct.

    Anything else (`OPEN`, `NONE`, another seq, a foreign reservation, a
    different digest) cannot arise while this journal is open, since the
    reservation serialized every other resolver and the orphan tests read
    this open journal as live. It raises `AmendmentResolutionHeldError`
    (INV-3). 6a1 then stops and reports under its existing "stop and
    report" rule: no amend, `HEAD` and the journal left as found. On
    success, 6a1's staging runs in `amend_recovery` mode ("No bypass"
    above), then `git commit --amend` and the re-verification run as
    today. Only the post-6c advance below binds `RESOLVED`, and it
    evaluates the amended `HEAD`. The hook-rewrote-`WORKFLOW_STATE.json`
    variant therefore repairs normally. While the defective commit is on
    `HEAD`, other (9) holders refuse under predicate step 1's in-flight
    exception, and never bind the defective digest.
  - **Advance after materialize.** A new step between 6c (materialize)
    and 6d (close the journal) calls `advance_amendment_witness`. Under
    (9), holding nothing else, it runs the predicate list, whose step 1
    advances `RESOLVING` to `RESOLVED` when this worktree's `HEAD` entry N
    carries the reserved digest. It is idempotent: `RESOLVED` with the
    same digest is a no-op. The journal is closed only after it
    succeeds. So an open journal always outlives its reservation's
    `RESOLVING` state, and the reservation orphan test below can use
    journal presence as its liveness evidence. If this step is lost,
    predicate step 1 self-heals it on the next (9) holder in any
    worktree, from that worktree's `HEAD` or from the resolver's.
    **`resolved_commit` is a label** (revision 8, `LPR-R7-001`). No
    predicate, orphan test or bootstrap step reads it. Every comparison is
    by `resolution_projection_sha256`. It can name a commit that 6a1's
    `--amend` later made unreachable, when another holder advanced the
    witness from the pre-amend commit. So the owner's advance is called as
    `advance_amendment_witness(repo_root, work_item_id, journal=journal,
    commit=<the verified commit>)`. On a `RESOLVED` witness with an equal
    digest and a different `resolved_commit`, it rewrites that one field to
    the verified commit and changes nothing else. This refresh happens only
    in the owner's call, which carries the journal. Every other (9)
    holder's advance leaves `resolved_commit` as it is.
  - **Release after rollback.** After step 6b's rollback succeeds (the
    journal is already closed by `rollback_plan_approval_transaction`), a
    new call `release_amendment_resolution(repo_root, work_item_id,
    journal_tokens)` runs under (9), holding nothing else.
    `journal_tokens` is the journal's `owner_token` plus every
    `previous_owner_tokens` entry, **captured before** 6b calls
    `rollback_plan_approval_transaction`, since that call closes the
    journal (its step 5) and the list is gone afterwards (revision 8,
    `LPR-R7-001`; revision 7 passed the current token alone, so a
    reservation made before a takeover was never matched). It rewrites a
    `RESOLVING` witness whose reservation's `journal_owner_token` is in
    that set back to its `previous` (`OPEN`), only if the resolver's
    `HEAD` and `resolver_branch` tip both lack a resolution of seq N.
    Otherwise it is a no-op. So a takeover followed by a `NOT_COMMITTED`
    rollback restores `OPEN` in band, with no orphan test and no literal,
    on a detached `HEAD` too. A crash between the rollback and the release
    leaves exactly the provable orphan the crash table rolls back.
  - **Every `/approve-review plan` entry, and the lifecycle call it
    makes** (revision 8, `LPR-R7-001`, the reviewer's architecture note).
    Enumerated from `approve-review.md` as installed. CP6 pins each row
    against the `2.6.0` command text:

    | Entry | How reached | Lifecycle call on an open-amendment item |
    | --- | --- | --- |
    | 4b | fresh invocation, journal open | none; reports and stops |
    | 4c | fresh invocation, no journal | none; opens the journal |
    | 4d | directly after 4c, same invocation only | `reserve_amendment_resolution` (`OPEN` → `RESOLVING`) |
    | 5, 6.x | directly after 4d, same invocation only | staging in `first_commit` mode, asserting the 4d reservation |
    | 6a | in session after 6.x, or after a 4b takeover | none; classifies |
    | 6a1 | 6a `COMMITTED` plus `TREE_CONTENT`, in session or taken over | `assert_amendment_resolution_held`, then staging in `amend_recovery` mode |
    | 6b | 6a `NOT_COMMITTED`, or a failure in 5 through 6.3 | capture `journal_tokens`, roll back, then `release_amendment_resolution` |
    | 6c → advance → 6d | 6a (or 6a1) verified `COMMITTED` | `advance_amendment_witness(..., journal=, commit=)`, then close the journal |
    | 6a `AMBIGUOUS` | any | none; stops |

    Nothing else in the command touches the witness. On an item with no
    open amendment, every row's lifecycle call is skipped, and the command
    is `2.5.1`'s plus section 5.4.
  - The multi-invocation journal never holds (9). The reservation is the
    `RESOLVING` witness itself, a durable record rather than a held
    `flock`. Reserve, advance and release are each one short (9)
    acquisition within a single process invocation, and so is 6a1's held
    check.
  - **No new lock-order edge.** Reserve, advance, release and 6a1's held
    check hold (9) alone. They read the working-tree state (atomically
    replaced, so read without (2)), the committed states, the journal (a
    plain file read) and the witness, and they write only the witness (the
    held check writes nothing). The census target
    values below are therefore unchanged.

**Crash recovery, with no liveness heuristics** (consistent with the
existing primitives):

| Crash point | Outcome |
| --- | --- |
| Witness `OPEN`, state never published or discarded (**provable orphan**) | The next (9) holder rolls it back automatically only when **every** one of these holds (revision 4, `LPR-R3-004`): (a) `requester_branch` is non-null, and the requester worktree is registered, readable, and its `HEAD` is still the symbolic ref `refs/heads/<requester_branch>`; (b) that worktree's working-tree state and its `HEAD`-committed state both lack seq N; (c) the tip of `refs/heads/<requester_branch>`, read directly from the common ref store, lacks seq N in its committed state (this also covers a branch that moved without the worktree); (d) no registered worktree's working-tree or `HEAD`-committed state holds an entry N whose `amendment_request_projection_sha256` equals the witness's `request_projection_sha256`. If (c) or (d) finds seq N, the amendment is live and the holder refuses plainly (`AmendmentInFlightError`, naming the branch or worktree that holds it); no literal is offered. In every other case where the test cannot be completed (the requester worktree gone, unreadable, detached, or switched to another branch), it refuses and offers the evidence-bound literal `clear amendment witness <wi> <sha256-of-witness-bytes>`, the `take_over_claim` pattern. A branch switch in the requester worktree therefore never rolls back a committed amendment's witness. |
| Journal open (4c), crash before the reservation (4d) (revision 7; corrected in revision 8, `LPR-R7-001`) | The witness is still `OPEN`, and nothing is staged. The next invocation stops at 4b. After the takeover literal, it resumes at 6a, which returns `NOT_COMMITTED`, and 6b rolls back. The release is a no-op, because no reservation carries this journal's tokens. No reservation is needed and no commit exists. A fresh `/approve-review plan` then reserves at 4d, or refuses there with `AmendmentResolutionReservedError` if another worktree reserved first. |
| Journal open, reservation `RESOLVING`, crash before the commit (revision 8, `LPR-R7-001`) | 4b stop, takeover, 6a `NOT_COMMITTED`, 6b. The release matches the reservation's token in the `journal_tokens` captured before the rollback (it is now in `previous_owner_tokens`), and restores `OPEN` in band. No orphan test or literal is involved, on a detached `HEAD` too. |
| Commit exists, `TREE_CONTENT` defect, crash before or during 6a1 (revision 8, `LPR-R7-001`) | The journal stays open, so the reservation stays live and no orphan test fires. After a takeover, 6a re-classifies `COMMITTED`, and 6a1's held check accepts the reservation through `previous_owner_tokens` (or a `RESOLVED` witness with the pinned digest). Other (9) holders that see the defective state blob on the resolver's `HEAD` refuse under predicate step 1's in-flight exception, and bind nothing. |
| Witness `RESOLVING`, the approval not committed (revision 7) | While the resolver's journal is open, the reservation is live. Other resolvers refuse (step 2a), and the owner resumes, takes over or rolls back. A **provable orphan reservation** is rolled back to `previous` (`OPEN`) automatically only when **every** one of these holds: (a) `resolver_branch` is non-null, and the resolver worktree is registered, readable, and its `HEAD` is still the symbolic ref `refs/heads/<resolver_branch>`; (b) that worktree has no open plan-approval journal whose `owner_token` or `previous_owner_tokens` contains `journal_owner_token`. The journal is read at its worktree-local path, and an unreadable journal fails the test; (c) neither that worktree's `HEAD`-committed state nor the tip of `refs/heads/<resolver_branch>` shows seq N resolved; (d) no registered worktree's `HEAD`-committed state shows seq N resolved. If (c) or (d) finds a resolution, predicate step 1 applies instead: advance on an equal digest, `AmendmentResolutionConflictError` on a different one. When the test cannot be completed (the resolver worktree gone, unreadable, detached, or switched to another branch), it refuses and offers the evidence-bound literal `clear amendment resolution <wi> <sha256-of-witness-bytes>`, which rewrites the witness to its `previous`. Because the journal is closed only after the advance (6d) or by a completed rollback (6b), (b) cannot misread a live transaction as dead. |
| Approval committed, witness still `RESOLVING` (revision 7) | Self-heals through predicate step 1 on any side, in any worktree, from the evaluating `HEAD`, the resolver's `HEAD` or the `resolver_branch` tip, when the committed digest equals the reservation's. The owner's own resumed run does the same at its advance step. |
| Rollback done (6b), crash before the release (revision 7) | A provable orphan reservation (no journal, no resolution anywhere). The next (9) holder rolls it back to `OPEN`. |
| Approval committed, witness still `OPEN` | Reachable under `2.6.0` only through a lagging `2.5.1` resolver, which never reserves (see the residual). Self-heals through predicate step 1, on any side, in any worktree whose `HEAD` has the approval, and binds that resolution's digest. A worktree whose `HEAD` does not have it yet correctly refuses under step 2 until it merges. |
| Holder of (9) killed | The kernel releases the `flock`. |

**Upgrade bootstrap (INV-7), deterministic derivation.** A repository
updated from `2.5.1` may already have an open amendment with no witness.
When the witness file is absent, the (9) holder runs one scan:

1. **Inputs.** It enumerates every registered worktree
   (`git worktree list --porcelain`). For each, it reads the item's entry
   from the `HEAD`-committed `WORKFLOW_STATE.json` and, when readable, from
   the working-tree one. An unreadable or torn state file refuses
   (INV-3). A prunable or missing worktree is skipped and named in the
   refusal text if the result is `OPEN`.
2. **Sequence.** `S` is the maximum `len(amendment_history)` over every
   scanned state, working-tree or `HEAD`. If `S == 0`, the scan writes a
   **`NONE` sentinel**: a witness with `status: "NONE"` and
   `amendment_seq: 0`. It then re-enters the predicate list, which now
   matches step 4 ("no amendment"). The first amendment request replaces the
   sentinel with `OPEN` at seq 1. **Exception** (revision 3,
   `LPR-R2-003`): while the lag probe reports any lagging worktree, the
   sentinel is never written. The scan's "no amendment" result is used in
   memory for this acquisition only, and the scan runs again on the next
   (9) holder.
3. **Fork check, before any status decision** (revision 3, `LPR-R2-005`).
   Collect entry `S` from every scanned state that holds one. Compare
   their request-time projections by `amendment_request_projection_sha256`
   (revision 4, `LPR-R3-005`): every field except
   `resolved_at_plan_revision` and `reconciliation_outcome`, the two
   fields `apply_plan_approval` adds at resolution
   (`workflow_state.py:10907-10915`). Across the states where entry `S` is
   still unresolved, also compare `amendment_base_commit`. On any
   disagreement the scan writes **nothing** and refuses with
   `AmendmentBootstrapConflictError`, naming every worktree and value.
   The operator resolves it by finishing or discarding the divergent
   amendment. An evidence-bound literal is not offered here: the
   disagreement is a real fork of `amendment_history`, not a crash.
   Running this check first means a `2.5.1` fork is never misreported as
   a stale worktree, whose remedy ("merge the resolved amendment") would
   be wrong for it.

   **Resolution fork check** (revision 7, `MPR-R1-I1`). Request
   agreement is not resolution agreement, so the scan also compares
   resolutions, before any status decision and writing nothing on
   failure. It covers **every seq `k` from 1 to `S`** held by two or more
   scanned states, not only `S`. A divergence at an older seq matters
   just as much, since its reconciliation shaped the checkpoints every
   later seq inherits:
   - the request projections of entry `k` must agree (the check above,
     generalized from `S` to every shared `k`);
   - across the `HEAD`-committed states where entry `k` is resolved,
     `amendment_resolution_projection_sha256` must agree;
   - for a legacy-resolved entry `k` (no `resolved_review_content_id`)
     held resolved by two or more `HEAD`s, each `HEAD` also derives the
     set of `Workflow-Plan-Approval:` trailer values over the commits
     reachable from it whose committed state shows entry `k` resolved
     while every parent's committed state shows it unresolved or absent
     (the commits that performed the resolution). Two non-empty,
     disjoint sets mean two different approved plans, even with equal
     revision and outcome. An empty set (no trailer, for example after a
     squash) adds no evidence, and that pair is compared on the digest
     alone (the residual below);
   - a working-tree state showing entry `k` resolved while its own
     `HEAD`-committed state does not is a plan approval in flight at
     update time, the unsupported posture in section 6.1's table. It
     refuses rather than being guessed at.

   Any disagreement refuses with `AmendmentBootstrapConflictError`, naming
   every worktree, `k`, and the differing digests or trailer values. **It
   never chooses one resolution deterministically.** The operator
   resolves it by discarding the divergent approval on all but one
   branch. States that agree, including one resolution visible in many
   worktrees, pass.
4. **Status.** The entries now agree, request and resolution alike. If
   **any** scanned `HEAD`-committed
   state shows seq `S` resolved, the scan writes `RESOLVED` at `S`, with
   `resolution_projection_sha256` equal to the agreed resolution digest
   (revision 7), and `resolved_commit` equal to that worktree's `HEAD`.
   The lexicographically smallest worktree path wins if several do, which
   only picks a commit label now, because every candidate carries the
   same resolution. A stale worktree that
   still shows the same entry `S` unresolved then refuses under predicate
   step 3 (`StaleLifecycleStateError`), never as an orphan `OPEN`. This
   covers a stale linked worktree whose `HEAD` predates a resolution that
   has since landed on another branch.
5. Otherwise the scan writes `OPEN` at `S`:
   - **Requester**: the worktree whose *working-tree* state holds the
     unresolved entry `S`. If several do, the one whose `HEAD` also holds
     it wins, and then the lexicographically smallest path. If only
     `HEAD`-committed states hold it, the smallest such path.
   - **`amendment_base_commit`**: the requester's value, which step 3
     proved all holders agree on.
   - **`request_projection_sha256`**: the agreed digest from step 3. A
     `RESOLVED` witness written by bootstrap step 4 carries it too.
6. **Cost.** Once no worktree lags, the scan runs at most once per item.
   After it, a witness (`OPEN`, `RESOLVED` or `NONE`) always exists, so
   later (9) holders read one witness file plus the lag probe. An orphan
   `OPEN` rollback rewrites the witness to its own recorded `previous`
   object (the `RESOLVED` or `NONE` witness it replaced), never to
   "absent". So a rollback cannot re-trigger the scan. The amendment side
   runs the bootstrap before it publishes, so an `OPEN` witness always has
   a non-null `previous`.

- **The status vocabulary.** `status` is `OPEN`|`RESOLVING`|`RESOLVED`|`NONE`
  (`RESOLVING` since revision 7). Any other value refuses, like a torn
  witness, and so does a `RESOLVING` witness without a well-formed
  `resolution_reservation` or a `RESOLVED` witness without a
  `resolution_projection_sha256`.
**Mixed-release worktrees** (revision 3, `LPR-R2-003`). The installed
Workflow is committed per branch: `scripts/`, `.claude/commands/` and
`WORKFLOW_STATE.json` land on the branch where `workflow_manager update`
is committed. A linked worktree whose branch has not merged that update
keeps running `2.5.1` scripts. Those never take (9), never read the
witness, and claim and amend exactly as `v2.4.0-002` describes. Nothing
a `2.6.0` process does can stop a `2.5.1` process. So **the mutual
exclusion is guaranteed only once every registered worktree's branch has
merged the `2.6.0` update.** Before that, `2.6.0` detects what it can and
refuses; it never trusts a lagging worktree:
- **The lag probe.** Every (9) holder, before the predicate list,
  enumerates the registered worktrees (`git worktree list --porcelain`)
  and reads each one's `HEAD`-committed
  `.workflow-manager/installation.json`. A worktree **lags** when that
  record's `workflow_version` is below `2.6.0`, or when the record is
  absent, unreadable or unparseable. The unknown cases count as lagging
  because that direction only costs extra scanning. A prunable or missing
  worktree cannot be probed. It is skipped and falls under the residual
  below.
  - **Version comparison** (revision 4, `LPR-R3-007`): numeric, never by
    string, so `2.10.0` is above `2.6.0`. The payload cannot import
    `src/workflow_manager/release.py`, so a payload-local helper
    reproduces `release._version_key`'s ordering (numeric parts compare as
    integers). CP6 pins the two against each other on a table of versions.
    A version it cannot order counts as lagging.
  - **`bare` entries** (revision 4, `LPR-R3-007`): an entry that
    `git worktree list --porcelain` marks `bare` has no working tree and
    no checked-out state, so no Workflow process can run in it. It is
    skipped by the probe and by every scan, and it is not lagging.
    Branches that exist only as refs remain the residual below.
- **While any worktree lags:**
  - the `NONE` sentinel is never written (bootstrap step 2), so a
    lagging worktree can never be hidden behind it;
  - on every acquisition, each lagging worktree's working-tree and
    `HEAD`-committed state for the item are read. An unresolved
    amendment entry there that the witness does not record refuses with
    `LaggingWorktreeAmendmentError`, naming the worktree, its branch and
    its installed version. "Does not record" is defined over stored data
    only (revision 4, `LPR-R3-005`): the lagging entry's seq is greater
    than the witness's `amendment_seq`; or it equals it and either its
    `amendment_request_projection_sha256` differs from the witness's
    `request_projection_sha256`, or the lagging state's
    `amendment_base_commit` differs from the witness's. A `NONE` witness,
    or none at all, records no seq, so any unresolved lagging entry is
    unrecorded. The witness is not changed, since a
    `2.5.1` amendment has no witness to own it. The remedy is to finish
    or discard that amendment in its worktree, or to merge the update
    there.
  - **Lagging resolutions** (revision 7, `MPR-R1-I1`). On the same read,
    a lagging worktree's `HEAD`-committed state that shows the witness's
    seq resolved, with a resolution digest different from the witness's
    (`RESOLVED`) or the reservation's (`RESOLVING`), refuses with
    `AmendmentResolutionConflictError`, naming the worktree, branch and
    installed version. The witness is not changed.
- **A lagging worktree alone is not a refusal.** A worktree on an
  unrelated old branch is ordinary, and refusing every claim while one
  exists would wedge the upgrade itself.
- **Once no worktree lags,** the probe costs one `git worktree list` plus
  one blob read per worktree, and no other worktree's state file is read.
  A worktree added later on an un-updated branch lags from its first
  probe, so no cached result can hide it.

- **Residual** (an unsupported upgrade posture, stated in section 6.2):
  - a `2.5.1` process in a lagging worktree can still claim while a
    `2.6.0` amendment is `OPEN`. The approval side's live-claim refusal
    (above) catches that claim if it is still live at approval, since
    claims already live under the common git dir;
  - a `2.5.1` process can still request an amendment without taking (9).
    The lag scan detects it on the next (9) acquisition, but cannot close
    the race window before that read;
  - an amendment requested under `2.5.1` on a branch checked out in *no*
    worktree, or only in a prunable one, is not discoverable;
  - (revision 7) a `2.5.1` process can approve (resolve) an `OPEN`
    amendment without reserving it. Nothing stops that race. The first
    such resolution a `2.6.0` (9) holder observes is bound by predicate
    step 1. Any different resolution of the same seq is then refused
    wherever it becomes visible (predicate step 3 and the lagging
    resolution check), so it is detected, never collapsed;
  - (revision 7) two independent `2.5.1` resolutions of the same seq,
    with equal revision and equal `reconciliation_outcome`, at least one
    landed without its `Workflow-Plan-Approval:` trailer, compare equal at
    bootstrap. Their checkpoint outcomes are identical by construction.
    Only the approved plan text can differ, and no committed fact records
    it.

**Lock-order census.**
- Primitive (9) and its edges are added: (9)→(2), (9)→(8), (9)→(6), (9)→(5)
  and the witness read/write sites.
- Updated: `DECLARED_PRIMITIVES`, `DIRECT_WITH_PRIMITIVE`,
  `BLOCKING_TARGETS`, `CODE_DERIVABLE`, the `WORKFLOW_V2_PLAN.md` edge table,
  its anchors and "eleven-edge" wording, and every hard-coded count.
- **The known target values** (revision 2), so that CP6 replaces the
  hard-coded counts with stated numbers, not re-derived ones:
  - primitives: 8 → **9**;
  - edges: 11 → **15**;
  - blocking/non-blocking split: 6/5 → **8/7**. The two new blocking
    edges are (9)→(2) and (9)→(6), since `BLOCKING_TARGETS` holds the
    `fcntl.flock` primitives. The two new non-blocking edges are (9)→(8)
    and (9)→(5).
  - `"9"` joins `BLOCKING_TARGETS` because it is itself an `fcntl.flock`
    primitive. No edge targets it, so the blocking *target* set stays
    `{2, 3, 6}` and the blocking *source* set becomes `{1, 5, 8, 9}`.
- A mutation regression proves removal of the (9) edge evidence is
  detected.
- (9) is a pure source, so the "blocking sources ∩ blocking targets = ∅"
  rule still holds unchanged (`{1, 5, 8, 9} ∩ {2, 3, 6} = ∅`). (9) is still a single digit, so the parser's
  `^\((\d)\)` regex needs no change.

**Documentation.**
- `WORKFLOW_V2_PLAN.md`: the (2)→(8) row and paragraph,
  `D-Plan-Amendment-1`'s narrowed bullet (now repository-wide), and a new
  `D-Repo-Global-Lifecycle` section.
- The `IllegalCheckpointStartPhaseError` and `claim_checkpoint`
  docstrings and messages.
- `request-plan-amendment.md` steps 1-2 (the new entry point),
  `milestone-implement.md` step 1d (new refusals and the remedy), and
  `approve-review.md`'s new steps (revision 7, corrected in revision 8):
  4d (reserve, in the invocation that opened the journal only), the
  step-5 staging mode (`first_commit` or `amend_recovery`), 6a1's held
  check, the advance between 6c and 6d (with the journal and commit),
  and the release after 6b (with the `journal_tokens` captured before
  the rollback), each with its refusals and remedies. Step 4b's takeover
  flow is unchanged and says so.
- `apply_plan_approval`'s docstring and its new `resolved_review_content_id`
  write, and `validate_state`/`amendment_history` entry validation
  admitting that key (revision 7). CP6 establishes mechanically whether
  `2.5.1`'s validators reject the key or ignore it, the same question CP3
  answers for `feedback_layout`.

**Forward compatibility.** The witness records worktree, branch and base
identity. That keeps a later Workflow release free to record or enforce
repository-global branch/base/worktree identity, for example
Controller-driven multi-worktree work, by extending this record rather than
adding a second one. This release adds no such policy.

## 6. Compatibility, migration and downgrade

### 6.1 Legacy active work items after updating from `2.5.1`

| Item state at update | Behavior under `2.6.0` |
| --- | --- |
| Any pre-`2.6.0` item | no `feedback_layout` stamp, so the legacy resolver; unconsumed flat feedback is still found; a terminal foreign owner no longer blocks it |
| Declarations lacking `.workflow-manager/` | CP1's fallback classifies the installation record; digests unchanged or now equal to the recorded approval |
| `AWAITING_LOCAL_PLAN_REVIEW`/`AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`/`AWAITING_PLAN_APPROVAL` with null `current_bundle_id` and no `plan_review_binding` | the readers accept it when the on-disk bundle verifies (section 5.3 item 4); nothing is back-filled and the phase is never changed; a later `REVISE` writes a real `CONSUMED` record from its own inputs |
| `REVISING_PLAN` mid-apply, no `plan_review_binding` | fails closed: the command-entry status call writes the legacy `CONSUMED` marker at the current mirror (section 5.3 item 2); `publish_plan_revision` and `bind` refuse until the revision advances once, which requires an edit plus regeneration |
| `AMENDING_PLAN`, no `plan_review_binding` | the command-entry status call writes a non-legacy `CONSUMED` record from the open amendment entry's own `superseded_plan_approval.approved_review_content_id` and `superseded_plan_revision` (revision 4, `LPR-R3-006`), so no forced extra revision advance; only if that id is absent does it fall back to the row above. The witness is established by the deterministic worktree scan on the first (9) holder (section 5.6) |
| Any ready phase, whose content the author then edits or re-plans | readers refuse by cause with a named remedy (section 5.3 item 6, rows 4a-4c); `/milestone-plan <id>` withdraws it to `REVISING_PLAN`/`AMENDING_PLAN` (section 5.3 item 7), writing the fail-closed legacy marker because a `2.5.1` ready item has no `BOUND` record |
| `IMPLEMENTING`, an implementation-review phase or `AWAITING_FUNCTIONAL_REVIEW`, re-planned with `/milestone-plan <id>` | `2.5.1` re-entered plan review silently (`publish_plan_revision`'s flip, `workflow_state.py:7790-7807`); `2.6.0` refuses at command entry with `PlanReviewPhaseNotPlanStageError` and writes nothing, not even the mirror advance. The route from `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` is `/request-plan-amendment <id>` (revision 5, `LPR-R4-002`) |
| Mid plan-approval transaction | out-of-scope posture: finish or abandon the approval under `2.5.1` before updating (documented) |
| A linked worktree whose branch has not merged the update | it keeps running `2.5.1`; `2.6.0` (9) holders probe it on every acquisition, never write the `NONE` sentinel while it lags, and refuse on an unresolved amendment in it that the witness does not record (section 5.6, "Mixed-release worktrees"); mutual exclusion holds only once it merges the update |

No update rewrites any committed state, declaration or ledger (INV-7).

### 6.2 Downgrade posture (CP7 adds a `2.6.0` paragraph to `CLAUDE.md`)

Downgrading to `<2.6.0` is unsupported for a repository that has:

- created any work item under `2.6.0`, since `feedback_layout` is new
  persisted vocabulary. CP3 must establish mechanically whether `2.5.1`'s
  validators reject the key or silently ignore it. Either way, older
  commands resolve scoped items' feedback to the flat path, silently.
- bound a plan bundle under `2.6.0`'s phase semantics.
- relied on `.ai-review/<id>/plan-inputs/` for a plan-stage round. Older
  generators read the author files from `current/` only, so they would
  stub them empty or reuse the previous round's copies there, and fail
  their own closing checks. That is a loud
  failure, not a silent one, but it is still unsupported.
- ever written an amendment witness (including a `NONE` sentinel). Older
  releases ignore it, which silently reopens `v2.4.0-002` rather than
  wedging. A `RESOLVING` reservation (revision 7) is ignored the same
  way, so an older release can resolve a reserved amendment a second
  time.
- ever resolved an amendment under `2.6.0` (revision 7). The resolved
  entry carries `resolved_review_content_id`, new persisted vocabulary.
  CP6's mechanical answer decides whether `2.5.1` rejects the key or
  ignores it.
- ever written a `plan_review_binding` record. It is new persisted
  vocabulary, like `feedback_layout`, and CP3's mechanical answer about
  unknown work-item keys decides whether `2.5.1` rejects or ignores it.
  Ignoring it silently re-admits already-reviewed content to review.

**Mixed-release worktrees are an unsupported posture too** (revision 3,
`LPR-R2-003`). Until every registered worktree's branch has merged the
`2.6.0` update, `2.5.1` processes in the lagging worktrees neither take
(9) nor read the witness. So `v2.4.0-002`'s mutual exclusion is
guaranteed only after that merge. `2.6.0` narrows the window (the lag
probe and the lagging-worktree scan in section 5.6) but cannot close it.
The same qualification appears in section 5.6's residual, in CP7's
`CLAUDE.md` paragraph and in the `v2.4.0-002` disposition.

The residual upgrade posture from section 5.6 is stated there too.

### 6.3 No new governing workflow version

Every fix is version-independent code: classification, resolver, lock,
witness, publication and approval transaction. It applies to `"2.1"` and
`"2.2"` items alike, and CP1's fallback applies to `"1"` items too.
Introducing `"2.3"` would add activation-trailer, rollback-predecessor and
dispatch surface for no behavioral difference.

## 7. Checkpoint registry

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Release-derived exact-path classification of the legacy .workflow-manager/installation.json record | - | 2 | 1 |
| CP2 | Anchor AMENDMENT_DIFF.patch at the working tree and restate its documentation | - | 1 | 1 |
| CP3 | Per-work-item feedback layout: one authoritative resolver, scoped-by-construction for new items, explicit legacy rule | CP1 | 3 | 1 |
| CP4 | Bundle-bound plan-review publication: split revision mirror from review-ready phase, recoverable generation | CP2, CP3 | 4 | 1 |
| CP5 | Plan-approval commit closure over the declared protected set and committed-truth post-commit verification | CP4 | 4 | 1 |
| CP6 | Repository-global lifecycle lock and amendment witness closing v2.4.0-002 | CP5 | 5 | 2 |
| CP7 | Compose the 2.6.0 release; release docs, defect dispositions and downgrade posture | CP6 | 3 | 1 |
| CP8 | Disposable-repository and linked-worktree acceptance suite, including update from installed 2.5.1 | CP7 | 4 | 1 |
| CP9 | Full regression, release parity and closed-defect regression verification | CP8 | 1 | 1 |

**Why this order.**
- CP1 and CP2 are small and independent.
- CP3 follows CP1 because both replace `workflow_fingerprint.py`, and serial
  edits keep each overlay delta reviewable.
- CP4 needs CP2 (both edit `prepare-ai-review.sh`) and CP3 (both edit
  `apply-plan-review.md` and `review-plan.md`).
- CP5 needs CP4's bound bundle for its `/approve-review plan` step-2 check
  and pin freshness.
- CP6 needs CP5's approval-side changes, since the resolution
  reservation, the witness advance and the release are all
  `/approve-review plan` steps (revision 7).

**Common rules for every implementation checkpoint.**
- All code, test and normative-doc changes go into
  `migration/overlays/2.6.0/payload/` only. Each changed file is a full
  replacement starting from the `2.5.1` base copy.
- The live installed `scripts/`, `.claude/commands/` and `docs/ai-workflow/`
  trees at this repository's root are not edited.
- Each checkpoint runs its narrowest check with `PYTHONPATH` pointing at the
  overlay `scripts/` plus the `2.5.1` base `scripts/` for files not yet
  overlaid, the precedent the `2.5.1` milestone set. It also records
  `git diff <base_commit> -- distribution/workflow/2.5.1/` as empty (INV-9).

<!-- CP1 -->
**CP1 -- Release-derived exact-path classification of the legacy
installation record.**

Implement section 5.2 in `migration/overlays/2.6.0/payload/scripts/workflow_fingerprint.py`.
Also create `migration/overlays/2.6.0/classification.json` with
`base_workflow_version: "2.5.1"` and a `replaced` rule per touched file.
Later checkpoints add their own rules.

Tests, in the overlay `workflow_fingerprint_test.py` (new class
`TestToolingAmbientExcludedPaths`):
- A legacy-shaped plan-stage and implementation-stage declaration with no
  `.workflow-manager/`: the path classifies `excluded` through the
  fallback.
- A declaration that protects `.workflow-manager/installation.json`
  explicitly still classifies it protected.
- Siblings still raise: `.workflow-manager/installation.json.tmp`,
  `.workflow-manager/other.json` and `.workflow-manager/`.
- Hashed-set invariance: the projection's classification sets are identical
  with and without the fallback.
- Digest invariance: for a scratch repository where the path is unchanged,
  and one where it changed, every digest `2.5.1` computes is byte-identical;
  the previously raising digest equals a pre-change recorded value.
- A `workflow_state_test.py` case: `implementing_entry_reachable` is `True`
  for a 2.3.1-shaped item after a committed installation-record change.

Normative docs: the `REVIEW_PROTOCOL.md` classification paragraph, plus a
`WORKFLOW_V2_PLAN.md` section `D-Tooling-Ambient-Classification` carrying
section 5.2's justification.

Narrowest check: the new classes plus the existing
`workflow_fingerprint_test.py` and `workflow_fingerprint_generalization_test.py`
run in full, green.
<!-- /CP1 -->

<!-- CP2 -->
**CP2 -- Working-tree-anchored `AMENDMENT_DIFF.patch`.**

Implement section 5.5 in `migration/overlays/2.6.0/payload/scripts/prepare-ai-review.sh`
(drop `..HEAD`, widen the pathspec to the base-plus-current union, add the
provenance preamble, write after the pin), plus the three documentation
sites.

Tests, through the **real script** in a scratch repository, following
`workflow_fingerprint_generalization_test.py`'s
`TestPrepareAiReviewShPlanStageRequiredArgument` fixture pattern:
- an uncommitted edited plan gives a non-empty patch containing the edit;
- a new untracked protected file appears as `new file`, and the index is
  restored afterwards (no lingering intent-to-add);
- a protected path dropped from the declaration and deleted from the
  worktree appears as `deleted file` (the base-side half of the union);
- a rename (old path dropped from the declaration, new path declared)
  appears as `deleted file` plus `new file`;
- a path dropped from the declaration but kept in the worktree, and
  changed since `amendment_base_commit`, appears as its content diff;
- the same path **unchanged** since `amendment_base_commit` produces no
  hunk of its own, and the `<id>-artifacts.json` hunk shows it leaving
  the declaration (revision 3, `LPR-R2-004`);
- `<id>-artifacts.json` absent at `amendment_base_commit`: the base-side
  half is empty and the patch equals the current-only form;
- an edit to a non-protected path is absent;
- the archive member is byte-identical to the on-disk patch;
- `bundle_id` is identical with and without the patch;
- after resolution the file is removed;
- the preamble fields equal the manifest's;
- `git apply --check` accepts the patch against `amendment_base_commit`.
<!-- /CP2 -->

<!-- CP3 -->
**CP3 -- Per-work-item feedback layout.**

Implement section 5.1:
- the resolver, `ensure_feedback_dir` and the CLI in `workflow_fingerprint.py`;
- the `feedback_layout` stamp in `route_work_item` and
  `create_remediation_child_work_item`, plus `validate_state` acceptance of
  the field (INV-3 for unknown values), in `workflow_state.py`;
- the relaxed guard, and the manual-record `Work item:` check;
- every command and normative document listed in section 5.1.

Before editing, record in this checkpoint's evidence whether `2.5.1`'s
`validate_state` and committed-field sets reject an unknown work-item key.
Section 6.2's downgrade paragraph depends on that answer.

Tests:
- A new item is stamped `"scoped"` and resolves scoped with no directory
  present; `ensure_feedback_dir` creates it.
- A remediation child is stamped `"scoped"`.
- Resume never stamps.
- Legacy entry, no entry and no state file each give the unchanged rule.
- A corrupt state file refuses.
- An unknown layout value refuses.
- Two scoped items never collide.
- A completed legacy item's flat file never affects a scoped item.
- The legacy terminal-owner relaxation allows the write; a non-terminal or
  unknown owner still refuses.
- The consumed marker is per item for scoped items.
- The CLI JSON output matches the function for all three layouts.
- The manual-record foreign-`Work item:` refusal.

Update the pinned tests listed in the investigation:
- `TestBundleLayoutResolver` and the consumed-marker tests;
- `TestReviewImplementationWritebackCrossWorkItemIsolation`, whose "creates
  no scoped dir" assertion now applies to legacy items only;
- the acceptance-matrix `feedback_dir()` helper;
- the `workflow_integration_test.py` prose pins.

Every pin is re-pointed deliberately, never deleted.
<!-- /CP3 -->

<!-- CP4 -->
**CP4 -- Bundle-bound plan-review publication.**

Implement section 5.3 items 1-7 in:
- `workflow_state.py` (publication split and its plan-stage phase
  allow-list, `route_work_item`'s matching allow-list on its resume-branch
  revision advance, `PlanReviewPhaseNotPlanStageError`,
  `PlanReviewWithdrawalNeedsExplicitIdError`, `PlanApprovalInProgressError`,
  `bind_plan_review_bundle`,
  `withdraw_plan_review`, verifier and its cause-named refusals, reader
  assertion, `plan_review_publication_status` and its CLI entry point);
- `workflow_fingerprint.py` and `prepare-ai-review.sh` (plan-stage-only
  staging-directory generation, `resolve_plan_review_inputs_dir` and the
  `plan-inputs/` copy, and the revised `WFR-67` failure path, with the
  implementation and post-fix stages byte-for-byte unchanged);
- `milestone-plan.md`:
  - its entry: the row-1 refusal before any write; the ready-phase
    withdrawal, which never computes `F`, needs an explicit id, and
    refuses during an open plan-approval journal for the item
    (`LPR-R4-002`/`-003`/`-004`/`-006`);
  - step 3: keeps the registry, mapping, `<id>-artifacts.json` and table
    write and the intent-to-add staging step, and **loses** its
    `publish_plan_revision` call;
  - a new publication point between steps 5 and 6: registry and mapping
    regeneration, the unconditional table re-embed, the staging step
    again, then `publish_plan_revision` (`LPR-R4-001`, section 5.3 item
    2);
  - step 6: `<plan_inputs_dir>` prose, and the bind straight after the
    generator succeeds; its heading, "Enter
    `AWAITING_EXTERNAL_PLAN_REVIEW`", is restated so that for `2.x` the
    phase is written by the bind, not the publish (revision 6,
    `LPR-R5-003`); and a generator-failure report that names the explicit-id
    re-run (row 9, `LPR-R5-001`);
- `apply-plan-review.md` steps 0 (the row-1 refusal), 1 (and, for
  `TWO_STAGE_PLAN_REVIEW_VERSIONS` items, the `Status: REVISE`-only
  acceptance with `FeedbackStatusNotApplicableError`), 5 (the
  intent-to-add reordering in its first-creation clause,
  `<plan_inputs_dir>` prose, and the generator-failure report naming the
  explicit-id re-run), 6 (restated as `"1"`-only; for `2.x` a `BLOCK` is
  resolved at the ready phase, section 5.3 item 2, revision 6,
  `LPR-R5-001`) and 7' (the bind, with 7'.2's second generation removed
  for `2.x`, section 5.3 item 2, revision 7, `MPR-R1-O1`), `REVIEW_PROTOCOL.md` "Bundle
  location" (`<plan_inputs_dir>`) and the `WFR-67` text,
  `review-plan.md`, `record-manual-plan-review.md`,
  `approve-review.md` step 2, and `apply-functional-review.md` (~244-253,
  where a remediation child "enters review at `AWAITING_LOCAL_PLAN_REVIEW`"
  through `publish_plan_revision`'s version branch; revision 2,
  `LPR-R1-006`);
- `publish_plan_revision`'s own docstring ("Sets ... `phase` to ..." and
  its exhaustive call-site list) and its new `review_content_id` keyword
  and `PUBLISHED` write, plus the `CONSUMED` writes in
  `record_local_plan_review`, `record_manual_plan_review` and
  `request_plan_amendment`, and `validate_state` acceptance of the new
  record (INV-3 for unknown `status` values and malformed sub-objects);
- `apply-plan-review.md` step 5's "whenever ... advances the plan's own
  revision counter" condition, which now governs only the registry
  regeneration: the `publish_plan_revision` call runs on every round
  (section 5.3 item 2);
- the revised `D-Plan-Revision-Publication` and the new
  `D-Plan-Review-Bundle-Binding` text in `WORKFLOW_V2_PLAN.md`,
  `MILESTONE_WORKFLOW.md` (including its `SELF_REVIEWING_PLAN` section,
  `:130-133`, which says `/milestone-plan` writes
  `AWAITING_LOCAL_PLAN_REVIEW` "directly, through
  `publish_plan_revision`"; under `2.6.0` the bind writes it, revision 6,
  `LPR-R5-003`; the new withdrawal edge from each
  ready phase back to `REVISING_PLAN`/`AMENDING_PLAN`, and its `BLOCK`
  rows, now at `:246` and `:249`, which say only "explicit user
  resolution required": under `2.6.0` a plan-stage `BLOCK` is resolved by
  re-review of unchanged content (row 2) or by an edit plus withdrawal
  (row 4a), `LPR-R4-006`),
  `PLAN_REVIEW_WORKFLOW.md` and the operator reference. The
  `D-Plan-Review-Bundle-Binding` text states the `WFR-67` revision as a
  deliberate revision of that requirement (`LPR-R3-002`).

First, record the mechanical enumeration from section 5.3 item 1. It
also records, per command (revision 5, `LPR-R4-001`), every step that can
edit a plan-stage protected path (the plan document, the registry, the
mapping, or `<id>-artifacts.json`'s `plan_stage` sets), and shows the
`publish_plan_revision` call after all of them. Per command it also
records every step that can end the command after the publish and before
the bind (revision 6, `LPR-R5-001`). It shows that the only ones left are
the generator-failure exits, each reporting the explicit-id re-run, and
that `apply-plan-review.md` step 6 is unreachable for
`TWO_STAGE_PLAN_REVIEW_VERSIONS` items. It also lists every caller of
`route_work_item`'s resume branch and the phase each reaches it at
(`LPR-R4-002`).

Tests:
- `publish_plan_revision` leaves the phase unchanged, for each of
  `PLANNING`, `REVISING_PLAN` and `AMENDING_PLAN`, and writes `PUBLISHED`
  with the fresh id. A same-round re-publish after further edits replaces
  `published`. It refuses consumed content early.
- `bind` refuses each of: no bundle, rejected bundle, stale-revision
  manifest, stale `review_content_id`, mixed bundle (section 3.3 variant 2),
  and a mismatched archive.
- `bind` refuses with `PlanReviewNotPublishedError` when the record is
  not `PUBLISHED`, or the binding is not the published content.
- Both section 3.3 variants reproduced against the new code end in a
  non-ready phase.
- Retry after failure: no second revision bump, then a successful bind.
- A crash between generation and bind resumes with bind only, both in a
  bumping round and in a non-bumping one.
- **Consumed content never re-binds** (revision 2, `LPR-R1-001`). Each case
  asserts that publish and `bind` refuse (`ConsumedPlanReviewContentError`)
  before an edit plus regeneration, and succeed after one:
  - a fresh local `REVISE` entry, with the reviewed bundle still on disk;
  - a fresh manual `REVISE` entry;
  - a fresh `AMENDING_PLAN` entry, with the approved bundle still on disk;
  - a non-bumping round (mirror unchanged): refused before the edit, and
    bound after the edit plus regeneration without a revision bump;
  - a wrapper-only regeneration of consumed content (new `bundle_id`,
    same `review_content_id`) is still refused.
- **A mid-edit crash never binds** (revision 3, `LPR-R2-001`). Each case
  crashes after a partial edit to the plan document, with the content
  already differing from the `CONSUMED` record. The entry status is
  `EDIT_IN_PROGRESS`, the command takes the normal path, and a direct
  `bind` against the on-disk bundle refuses:
  - a bumping `/apply-plan-review` round;
  - a non-bumping `/apply-plan-review` round;
  - an amendment under `/milestone-plan`, where step 1 already advanced
    the mirror (`M > R`);
  - a bumping round whose document `(Revision N)` marker was already
    bumped ahead of the registry (`PlanRevisionMismatchError`, read as
    `F = ⊥`);
  - a publish followed by further edits (`F` differs from `published`).
- The legacy `null`-`current_bundle_id` item in `REVISING_PLAN`, and in
  `AMENDING_PLAN` with no `approved_review_content_id` in its open
  amendment entry: publish and `bind` refuse with
  `LegacyPlanReviewBindingUnknownError` before the entry marker exists;
  the entry step writes the marker; publish and `bind` refuse at the
  marker's revision and succeed only after one advance.
- **The status function is total** (revision 3, `LPR-R2-001`). One test
  per row of section 5.3 item 6's table, each driven from the command
  entry, including:
  - a first-round `PLANNING` item with no record and no registry
    (`NEEDS_EDIT`, row 7);
  - a `PLANNING` item with a registry and no record (`EDIT_IN_PROGRESS`);
  - `NEEDS_REVISION` resuming at step 5 without regenerating anything
    that differs;
  - the durable feedback check under `PUBLISHED_UNBOUND` and
    `EDIT_IN_PROGRESS`, with a mismatching feedback file refusing;
  - `/milestone-plan` on an `AMENDING_PLAN` item performing no feedback
    check (`LPR-R2-007`);
  - every refusal row (4a, 4b, 4c, 4d and 6), each asserting the named
    error and that its message names the row's remedy.
- **Wrapper-only regeneration after bind stays non-blocking** (revision 3,
  `LPR-R2-002`):
  - at `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, `/record-manual-plan-review`
    still ingests, with the advisory warning naming both `bundle_id`s;
  - at `AWAITING_PLAN_APPROVAL`, `/approve-review plan` step 2 still
    proceeds, and section 5.4 item 2's freshness check passes against the
    regenerated `files/`;
  - `bind` at either phase refuses with `PlanReviewAlreadyReadyError`
    and leaves the phase unchanged.
- **Legacy ready items** (revision 3, `LPR-R2-002`): a `2.5.1` item at
  `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` with no record is accepted by
  the readers; nothing writes a record or changes its phase.
- **A failed staging generation, driven in the real command order**
  (revision 2, `LPR-R1-002`; revision 3 merged the duplicate bullet,
  `LPR-R2-006`; revision 4, `LPR-R3-002`): refresh `plan-inputs/`'s
  `REVIEW_REQUEST.md` and `TEST_RESULTS.md` as `/apply-plan-review` step 5
  does, then force a failure (a stale `TEST_RESULTS.md`, and separately a
  stale `REVIEW_REQUEST.md`, section 3.3's two variants). In each case:
  - the previous `current/`, its archive and `.pin` are byte-identical;
  - no `REJECTED` marker is written, and `withdraw_bundle` is not called
    on `current/`;
  - no staging directory survives;
  - for a previously bound item, the readers still accept the previous
    bundle.

  A pre-existing `REJECTED` marker still refuses the readers and is
  cleared by the next successful generation. An implementation-stage
  generation failure still withdraws exactly as in `2.5.1` (stage scope).
- `plan-inputs/` seeding: with no `plan-inputs/` file and a `current/`
  copy present, the staging copy equals the `current/` copy, and
  `current/` is unchanged; with neither, the stub is empty. `bundle_id`
  equals the value an in-place `2.5.1` generation of the same bytes gives.
- **Ready-phase writers** (revision 4, `LPR-R3-001`). No case ends in a
  wedge, and after every call the phase is ready only with a `BOUND`
  record:
  - `/milestone-plan <id>` re-run at each of `AWAITING_LOCAL_PLAN_REVIEW`,
    `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` and `AWAITING_PLAN_APPROVAL`
    withdraws to `REVISING_PLAN` (and to `AMENDING_PLAN` for an item with
    an open amendment), writes `CONSUMED` from `bound`, and then re-binds
    new content through the normal path; the withdrawn content is refused;
  - an edit plus regeneration at `AWAITING_LOCAL_PLAN_REVIEW` before any
    verdict: `/review-plan` refuses with `ReviewedContentDriftError`
    naming both remedies; restoring from `current/files/` returns to row
    2, and `/milestone-plan <id>` is the in-band exit when the edit is
    kept;
  - `publish_plan_revision` and `route_work_item`'s revision advance at
    each ready phase refuse with `PlanReviewInProgressError` and write
    nothing;
  - a legacy ready item whose bundle was withdrawn under `2.5.1` (row 4c)
    recovers by regeneration to row 3, and the readers accept it;
  - `withdraw_plan_review` at a non-ready phase refuses and writes
    nothing; a crash after it is resumed by re-running `/milestone-plan`.
- **Self-review edits bind** (revision 5, `LPR-R4-001`), each driven in
  the real `/milestone-plan` step order (steps 1-6), with no manual
  re-publish:
  - a first round whose step-4 self-review edits the plan document binds;
  - a first round whose step-4 self-review edits `<id>-artifacts.json`'s
    `plan_stage` sets binds, and the bound id reflects the edited sets;
  - a first round whose self-review adds a checkpoint: the publication
    point regenerates the registry and re-embeds the table, and the bound
    plan's table equals `render_registry_markdown` of the bound registry;
  - an amendment round through `/milestone-plan` with a self-review edit
    binds;
  - a pinning test: publishing at `2.5.1`'s step-3 position and then
    editing in step 4 makes the bind refuse with
    `PlanReviewNotPublishedError`, showing why the order matters.
- **Plan-stage phase allow-list** (revision 5, `LPR-R4-002`). At
  `IMPLEMENTING` and at `AWAITING_FUNCTIONAL_REVIEW`:
  - `/milestone-plan <id>` and `/apply-plan-review <id>` refuse with
    `PlanReviewPhaseNotPlanStageError`, and `WORKFLOW_STATE.json` is
    byte-identical afterwards (no mirror advance);
  - `publish_plan_revision` and `route_work_item`'s resume branch refuse
    the same way and write nothing;
  - the `IMPLEMENTING` message names `/request-plan-amendment <id>`, and
    the `AWAITING_FUNCTIONAL_REVIEW` message does not;
  - a remediation child's re-declaration at `PLANNING` still succeeds;
  - `"1"`-governed `/bootstrap-workflow-v2`'s `publish_plan_revision` at
    `IMPLEMENTING` is unchanged.
- **Unreadable fresh id at a ready phase** (revision 5, `LPR-R4-003`), at
  `AWAITING_LOCAL_PLAN_REVIEW` with a `BOUND` record, once with a bumped
  `(Revision N)` title and once with a deleted protected path:
  - the status function returns `CONTENT_DRIFTED` (row 4a);
  - `/review-plan`, `/record-manual-plan-review` and `/approve-review
    plan` refuse with `ReviewedContentDriftError` and the row-4a remedy
    text (revert, or withdraw), never the bare error;
  - `/milestone-plan <id>` withdraws, writing `CONSUMED` from `bound`,
    and lands on row 11;
  - the same two cases with no record (a `2.5.1` ready item) give row 4c
    and withdraw the same way.
- **Withdrawal guards** (revision 5, `LPR-R4-004`/`-006`):
  - `/milestone-plan` with no work-item-id argument, resolving to an item
    at each ready phase, refuses with
    `PlanReviewWithdrawalNeedsExplicitIdError` and writes nothing. This is
    tested once for the no-argument form and once for the one-argument
    base-SHA form, `/milestone-plan <base-sha>` (revision 6,
    `LPR-R5-004`). `/milestone-plan <id>` and `/milestone-plan <id>
    <base-sha>` withdraw and report that both stages were discarded and
    the content consumed;
  - with an open plan-approval journal for the item, `/milestone-plan
    <id>` at `AWAITING_PLAN_APPROVAL` refuses with
    `PlanApprovalInProgressError` and writes nothing; with a corrupt
    journal it refuses with `PlanApprovalJournalUnavailableError`; with a
    journal for a different item it withdraws.
- **First round with untracked plan files** (revision 4, `LPR-R3-003`):
  a fresh work item's first `/milestone-plan` round, starting with its
  four plan-stage files untracked, publishes (at the publication point),
  generates and binds, and publishing *before* the intent-to-add step
  refuses with
  `InvalidPlanStageMetadataPathError` (pinning why the order matters).
- **Legacy `AMENDING_PLAN` marker source** (revision 4, `LPR-R3-006`): a
  `2.5.1` item in `AMENDING_PLAN` whose mirror `2.5.1`'s `/milestone-plan`
  step 1 already advanced gets a non-legacy `CONSUMED` record from its
  open amendment entry, and binds after its edit with no extra revision
  advance; the amended-away content is refused.
- **Legacy-marker feedback check** (revision 4, `LPR-R3-006`): for a
  legacy `REVISING_PLAN` item with the null-id marker, `/apply-plan-review`
  accepts feedback whose `Work item:` is the target and whose `Status:` is
  `REVISE`, and refuses a foreign `Work item:` or a non-`REVISE` status.
- **No exit between publish and bind** (revision 6, `LPR-R5-001`):
  - a `2.2` `/apply-plan-review` round, driven in the real step order,
    whose applied findings the author judges "major structural changes"
    ends at `AWAITING_LOCAL_PLAN_REVIEW` with a `BOUND` record for the
    published content. Step 6 is shown unreachable for
    `TWO_STAGE_PLAN_REVIEW_VERSIONS` items, and `/review-plan` then
    accepts the bundle;
  - the same round for a `"1"`-governed item still takes `2.5.1`'s step
    6 unchanged;
  - `/apply-plan-review` on a `2.2` item at `REVISING_PLAN` whose feedback
    file carries `Status: BLOCK`, and separately `Status: APPROVE`,
    refuses at step 1 with `FeedbackStatusNotApplicableError`.
    `WORKFLOW_STATE.json` is byte-identical afterwards, and the `BLOCK`
    message names the re-review and withdrawal routes;
  - a forced generator failure after the publish, in `/apply-plan-review`
    step 5 and in `/milestone-plan` step 6: the item is at row 9, the
    report names the explicit-id re-run of the same command, and that
    re-run binds with no second revision advance;
  - **Single generation per round** (revision 7, `MPR-R1-O1`): a `2.2`
    `/apply-plan-review` round driven in the real step order invokes
    `prepare-ai-review.sh` exactly once (instrumented), at step 5. Step
    7' binds that generation's bundle without regenerating. If `current/`
    is made unverifiable between step 5 and step 7', the bind refuses by
    cause, the item stays at row 9, and the report names the explicit-id
    re-run. CP4's per-command enumeration lists step 7' with no generator
    call.
- `/review-plan`, `/record-manual-plan-review` and `/approve-review plan`
  refuse an unbound bundle.
- `"1"`-governed `publish_plan_revision` behavior is byte-for-byte
  unchanged (section 2).
<!-- /CP4 -->

<!-- CP5 -->
**CP5 -- Plan-approval commit closure and committed-truth verification.**

Implement section 5.4 items 1-6 in `workflow_fingerprint.py`,
`workflow_state.py` and `approve-review.md` (steps 4a/5 "four-or-five
members" wording, 6a/6a1, 6d), plus the `WORKFLOW_V2_PLAN.md` section
`D-Plan-Approval-Closure`.

Tests, all driven through a **command-shaped driver** that uses the
command's real data flow: pre-commit `work_item` from steps 1-2, never a
hand-built post-state.
- The previously observed new-file case: an intent-to-add companion, as the
  regression.
- A fully untracked new companion.
- A tracked, edited companion.
- A companion dropped from the declaration.
- A rename, both via `mv` and via `git mv` (the latter refusing with the
  named remedy).
- A companion edited after bundle generation refuses before any mutation,
  with `HEAD` unchanged.
- **Failed regeneration, then approve** (revision 2, `LPR-R1-002`;
  revision 4, `LPR-R3-002`): after a bound bundle, in the real command
  order, refresh `plan-inputs/`, edit a protected member and force a
  staging-generation failure. `current/` is byte-identical to before.
  `/approve-review plan` refuses at step 2 with `ReviewedContentDriftError`
  (section 5.4 item 2, "Which check fires first"), before any mutation.
  `HEAD`, the index and state are unchanged. One further case leaves the
  fresh id unchanged, so step 2 passes and the per-member check refuses
  with the same error: a byte edit to `<id>-artifacts.json` that leaves
  its declared key sets unchanged. (The other such case, a removal member
  still captured by the bound bundle, has its own bullet below. Revision
  6, `LPR-R5-005`.)
- **A de-protected path re-created in the worktree is not a removal
  member** (revision 5, `LPR-R4-005`, replacing revision 4's
  contradictory "refused" case): a path protected at `HEAD`, dropped from
  the current declaration and deleted, then re-created under an excluded
  classification. The approval stages no deletion for it, `HEAD`'s
  committed copy survives in the approval commit's tree, the write-tree
  proof and the two-sided path-set check pass, and the approval
  succeeds. The same path left deleted is staged as a deletion.
- **Protected members keyed on `base_commit`** (revision 6, `LPR-R5-002`,
  replacing revision 5's unconditional "no capture refuses"):
  - a declared protected companion that is present, tracked and unchanged
    since `base_commit`, so it has no `files/` capture, approves. It is
    compared against its `base_commit` blob, and no deletion or content
    change is staged for it;
  - a protected member that differs from `base_commit` in the worktree
    but has no `files/` capture in the bound bundle (it was edited after
    generation) refuses with `ReviewedContentDriftError`, before any
    mutation. This is the restated "no capture refuses" case;
  - a protected member with no capture whose worktree bytes differ from
    `HEAD` but equal its `base_commit` blob (a post-base commit touched
    it and the worktree reverted it) approves;
  - a protected member absent at `base_commit`, with no capture, that
    appeared in the worktree after generation refuses. In the command,
    step 2's id check already refuses this case, so it is driven directly
    against the per-member check as a defense-in-depth pin.
- A removal member whose path is still in the bound bundle's captured set
  refuses with `ReviewedContentDriftError`.
- A first approval (no `<id>-artifacts.json` at `HEAD`) has an empty
  removal set (revision 2, `LPR-R1-009`).
- The write-tree proof failing becomes a `NOT_COMMITTED` rollback, not an
  amend.
- **First approval with no `WORKFLOW_STATE.json` at `HEAD`**. This is
  `v2.3.1-003` together with the section 3.5 `TypeError` case: it must
  commit once and verify.
- A prior `STALE` approval and a prior `SUPERSEDED` approval (amendment)
  verify, with no false mismatch.
- A crash after commit resumes, both in session and via takeover.
- A crash after materialize, before close (the NOOP path).
- A record or input error never invokes amend: `HEAD` SHA is unchanged and
  the count of approval-trailer commits is 1.
- A `None` record raises `MissingApprovalRecordError`.
- The implementation-stage helper's named-error guard.
<!-- /CP5 -->

<!-- CP6 -->
**CP6 -- Repository-global lifecycle lock and amendment witness.**

Implement section 5.6 in:
- `workflow_state.py`;
- both `docs/ai-workflow/dry-run/verify_372h_*.py` scripts;
- `WORKFLOW_V2_PLAN.md`;
- `request-plan-amendment.md`, `milestone-implement.md` and
  `approve-review.md` (including the resolution steps: 4d, the step-5
  staging mode, 6a1's held check, the 6c/6d advance and the post-6b
  release, per section 5.6's entry table, revision 8).

Invert `TestCrossWorktreeAmendmentClaimResidualXModelR9B1`. Its tests
become the refusal assertions below, renamed to state the closed property.
Keep the within-worktree tests, adapted to the new entry point.

Adversarial tests, using real linked worktrees (`ScratchRepo.worktree`) and
real processes where stated:
1. Amendment first: B's claim is refused (`AmendmentInFlightError`) while
   B's local state still says `IMPLEMENTING`. Nothing is published.
2. Claim first: A's amendment is refused, naming the foreign claim.
3. Real-process race, with the amender paused after `resolve_claim` and the
   claimer started. Exactly one succeeds, and B blocks on (9).
4. Real-process race in the reverse order.
5. Stale B after resolution: refused with `StaleLifecycleStateError` until
   B merges, then allowed.
6. Two worktrees request amendments concurrently: exactly one succeeds.
7. `SIGKILL` between witness publish and state publish gives a provable
   orphan and an automatic rollback. With the requester worktree removed,
   the literal is required, and a wrong digest refuses.
7a. **Branch switch never rolls back a live amendment** (revision 4,
    `LPR-R3-004`): worktree A requests an amendment and commits it on
    `requester_branch` (`request-plan-amendment.md` step 3), then checks
    out another branch. A claim from worktree B refuses with
    `AmendmentInFlightError` naming the branch that holds seq N, offers no
    literal, and the witness bytes are unchanged. Variants: A's branch is
    checked out in a third worktree instead (condition (d)), and A is
    left on a detached `HEAD` (the literal is offered, and there is still
    no automatic rollback).
8. `SIGKILL` after the approval commit, before the witness advance
   (the witness is `RESOLVING`), then self-heals: in the resolver's own
   resumed run, and separately from a claim in another worktree that
   reads the resolver's `HEAD` or the `resolver_branch` tip.
9. `SIGKILL` of a (9) holder: the next contender proceeds.
10. A symlinked, torn or unknown-schema witness refuses.
11. Absent-claim `take_over_claim` and `adopt_claim` refuse while the
    witness is `OPEN`.
12. A direct `state_transaction(request_plan_amendment)` without (9)
    refuses.
13. Upgrade bootstrap: an `AMENDING_PLAN` item with no witness in another
    worktree is discovered by the scan and refused.
13a. **Self-heal ordering** (revision 2, `LPR-R1-004`): the witness is
    `OPEN` at seq N and the evaluating worktree's `HEAD` shows N resolved.
    Both a claim and an amendment request advance the witness to
    `RESOLVED` and proceed, and neither raises `AmendmentInFlightError`.
    A worktree whose `HEAD` lacks the resolution still refuses.
13b. **Stale-worktree bootstrap**: a `2.5.1` amendment resolved on the main
    worktree, plus a stale linked worktree whose `HEAD` still shows it
    unresolved. The scan writes `RESOLVED`, not `OPEN`. The stale
    worktree's claim refuses with `StaleLifecycleStateError`, and no
    orphan wedge occurs.
13c. **Bootstrap conflict**: two worktrees holding unresolved entry `S` with
    different `amendment_base_commit` values. The scan writes nothing and
    refuses with `AmendmentBootstrapConflictError`, naming both. A second
    case (revision 3, `LPR-R2-005`): one worktree's `HEAD` shows entry `S`
    resolved, and another holds a *different* unresolved entry `S`. The
    scan refuses with `AmendmentBootstrapConflictError`, not
    `StaleLifecycleStateError`, and writes nothing.
13d. **Sentinel**: an item that never amended, with no lagging worktree,
    gets a `NONE` witness after the first claim. A second claim reads no
    other worktree's state file (asserted by instrumentation; the lag
    probe's `git worktree list` and installation-record reads are
    expected). The first amendment request replaces
    the sentinel with `OPEN` at seq 1, and an orphan rollback restores
    `NONE`, not "absent".
13e. **Amendment-side `HEAD` test**: a worktree whose working tree shows
    seq N resolved but whose `HEAD` does not is refused under a `RESOLVED`
    witness.
13f. **Lagging worktree and the sentinel** (revision 3, `LPR-R2-003`): a
    linked worktree whose `HEAD`-committed installation record says
    `2.5.1`. For an item that never amended, the first claim writes no
    `NONE` sentinel, and the second claim scans again. After that
    worktree merges the update, the next claim writes `NONE`. A worktree
    whose `HEAD` has no installation record is treated as lagging.
13g. **Lagging worktree amendment** (revision 3, `LPR-R2-003`): the witness
    is `RESOLVED` at seq 1, or absent. The lagging worktree's working-tree
    state holds an unresolved entry 2, written by `2.5.1`'s own
    `request_plan_amendment`. A claim from an updated worktree refuses
    with `LaggingWorktreeAmendmentError`, naming the worktree, branch and
    version, and the witness is unchanged. A lagging worktree with no
    unresolved amendment does not block the claim. **Same-seq fork**
    (revision 4, `LPR-R3-005`): the witness is `OPEN` at seq 2 from an
    updated worktree, and the lagging worktree holds a *different*
    unresolved entry 2 (a different `amendment_request_projection_sha256`).
    The claim refuses with `LaggingWorktreeAmendmentError`. A lagging
    worktree holding the *same* entry 2 (equal digest and
    `amendment_base_commit`) does not trigger that refusal; the claim
    refuses only as step 2's ordinary `AmendmentInFlightError`.
13h. **Predicate totality and probe details** (revision 4, `LPR-R3-007`):
    a `NONE` witness lets a claim through and lets an amendment publish
    `OPEN` at seq 1 with `previous` equal to the `NONE` witness; a `bare`
    entry in `git worktree list --porcelain` is neither probed nor
    lagging; the payload-local version helper orders `2.10.0` above
    `2.6.0` and agrees with `release._version_key` on a pinned table, and
    an unorderable version counts as lagging.
13i. **One projection function** (revision 4, `LPR-R3-005`):
    `amendment_request_projection_sha256` ignores exactly
    `resolved_at_plan_revision`, `reconciliation_outcome` and
    `resolved_review_content_id` (revision 7), so an entry's
    digest is identical before and after `apply_plan_approval` resolves
    it; the `OPEN` witness's digest equals the digest of the entry the
    same transaction published.
14. The item 372(h) census rediscovers primitive (9) and its edges, with
    the stated counts (9 primitives, 15 edges, 8/7 split); the mutation
    regression removing (9)→(8) evidence is detected; disjointness holds.
15. No deadlock: every existing guard/claim/journal test passes, including
    `TestRealProcessConcurrentTakeover` and `TestGlobalLockOrderItem372h`.
16. The same-worktree behavior of `TestAmendmentClaimRaceRealProcesses`
    still holds.

**One resolution per amendment sequence** (revision 7, `MPR-R1-I1`,
INV-10), with real linked worktrees A and B whose branches both carry
the same unresolved entry N (witness `OPEN` at N):
17. **Divergent concurrent resolution.** A and B each edit a different
    amended plan, so the post-amendment registries and reconciliation
    outcomes differ. Each is reviewed and reaches `/approve-review plan`,
    with real processes and B paused after its journal opens. Exactly one
    reservation succeeds. The other refuses at step 4d with
    `AmendmentResolutionReservedError`, naming the resolver worktree,
    branch and reserved `approved_review_content_id`. It takes the 6b
    rollback. Exactly one approval-trailer commit exists repository-wide,
    and the witness ends `RESOLVED` with the winner's digest. Run in both
    orders.
18. **Second resolution after `RESOLVED`.** A's resolution is `RESOLVED`.
    B then attempts approval of a *different* amended plan, and
    separately of the *identical* one. Both refuse at step 4d with
    `StaleLifecycleStateError` ("merge the resolved amendment first")
    before any staging or commit. B's `HEAD`, its index and the witness
    bytes are unchanged. After B merges A's resolution, B's claim is
    admitted. The identical-plan refusal is intended, not a missing
    idempotence (revision 8, `LPR-R7-002`): predicate step 3 refuses
    because B's `HEAD` lacks the resolution, "whether or not its amended
    plan is the same one" (section 5.6). An identical approval is a second
    approval commit, so B merges A's instead. The test's docstring cites
    that sentence.
19. **Resolution conflict is never collapsed.** A committed divergent
    resolution is planted on B's branch (a `2.5.1`-style unreserved
    approval, produced by the installed `2.5.1` scripts in a lagging
    worktree for the end-to-end variant, CP8 scenario 7). Under a
    `RESOLVED` witness, B's claim refuses with
    `AmendmentResolutionConflictError` naming both digests. Under a
    `RESOLVING` witness, predicate step 1 refuses the same way and does
    not advance. The witness bytes are unchanged in both cases.
20. **Upgrade bootstrap resolution fork.** No witness exists. Two `HEAD`s
    hold entry N with equal request projections but different resolution
    data, in three variants: different `reconciliation_outcome`;
    different `resolved_at_plan_revision`; and equal revision and outcome
    with disjoint `Workflow-Plan-Approval:` trailer sets on the resolving
    commits. Each refuses with `AmendmentBootstrapConflictError`, naming
    both worktrees and values, and writes no witness. A fourth variant
    places the divergence at seq `k < S`, with agreeing entries at `S`,
    and refuses the same way. A worktree whose working tree shows N
    resolved while its `HEAD` does not refuses too.
21. **Identical resolution is admissible and idempotent.** The same
    approval commit is merged into B, and separately cherry-picked. Every
    worktree's claim is admitted under `RESOLVED`. Bootstrap over the
    same shape writes `RESOLVED` with that digest. Re-running
    `advance_amendment_witness` and `reserve_amendment_resolution`
    (the latter called directly on its own journal's token, before
    commit, since no command path re-enters 4d) are byte-level no-ops on
    the witness.
22. **Reservation crash recovery**, each driven through
    `approve-review.md`'s real 4b/6a/6b flow (revision 8, `LPR-R7-001`).
    (a) `SIGKILL` between 4c and 4d. The next invocation stops at 4b.
    After the takeover literal it goes straight to 6a (`NOT_COMMITTED`)
    and 6b. The witness bytes are unchanged throughout (still `OPEN`),
    and `reserve_amendment_resolution` is never called (instrumented). A
    fresh invocation then reserves at 4d. In a variant, B reserves in the
    window, and the fresh invocation refuses at 4d with
    `AmendmentResolutionReservedError` and takes 6b, with no commit.
    (b) A `SIGKILL`ed resolver with its journal still
    open keeps its reservation live: B's approval refuses, and nothing
    rolls it back automatically. (c) Crash after the 6b rollback, before
    the release: the next (9) holder proves the orphan and restores
    `OPEN`, after which B can reserve. (d) With the resolver worktree
    removed, or on a detached `HEAD`, the literal
    `clear amendment resolution <wi> <sha256>` is required, and a wrong
    digest refuses. (e) After a takeover of A's journal, the reservation
    stays live against B through `previous_owner_tokens` (predicate step
    2a and orphan test (b)), and the taken-over run never reaches 4d.
23. **No flock across turns.** Instrumentation asserts that (9) is never
    held when `/approve-review plan` returns control between steps, or
    inside any `plan_approval_guarded_mutation` window, and that the
    held-set assertion rejects taking (9) there.
24. **`resolved_review_content_id`.** `apply_plan_approval`'s amendment
    branch writes it equal to the record's `approved_review_content_id`.
    `validate_state` admits it. The journal's `expected_post_state`
    digest equals the committed entry's digest. The `2.5.1` validator's
    behavior on the key is recorded (rejects or ignores), as CP3 records
    it for `feedback_layout`.

**Recovery paths after the journal opens** (revision 8, `LPR-R7-001`),
each on an open-amendment approval with a `pre-commit` hook fixture that
produces a `TREE_CONTENT` defect:
25. **6a1 amend recovery holds the resolution.** A hook rewrites a
    non-state member. Four variants: in session, and after a takeover,
    each with the witness still `RESOLVING`, and with it already advanced
    to `RESOLVED` by another worktree's claim evaluating the resolver's
    pre-amend `HEAD` (predicate step 1). Each completes with exactly one
    approval-trailer commit repository-wide (the amended one) and a
    `RESOLVED` witness carrying the reserved digest. In the pre-advanced
    variant, the owner's advance rewrites `resolved_commit` to the
    amended SHA, and no other witness byte changes. The held check
    writes no witness bytes.
26. **The hook rewrites `WORKFLOW_STATE.json`.** The committed entry N
    has a digest different from the reservation's. Before 6a1, a claim in
    worktree B that reads the resolver's `HEAD` refuses with
    `AmendmentResolutionReservedError` (predicate step 1's in-flight
    exception, not `AmendmentResolutionConflictError`), and the witness
    bytes are unchanged. 6a1's held check passes on the journal's pinned
    digest, the amend repairs the blob, and the post-6c advance binds
    `RESOLVED` with the reserved digest. There is exactly one
    approval-trailer commit.
27. **The held check refuses a witness it cannot hold.** With the
    witness planted as `OPEN`, `NONE`, another seq, a foreign token's
    `RESOLVING`, or a `RESOLVED` with a different digest, 6a1 raises
    `AmendmentResolutionHeldError` before its first guarded window.
    `HEAD`, the index, the journal and the witness bytes are unchanged,
    and no amend is attempted. The step-5 staging entry, called in
    `first_commit` mode without a 4d reservation, or in `amend_recovery`
    mode without a passing held check, refuses the same way.
28. **Takeover, then a `NOT_COMMITTED` rollback, releases in band.** A
    reserves at 4d, is `SIGKILL`ed before its commit, and its journal is
    taken over (the reservation's token is now only in
    `previous_owner_tokens`). 6a returns `NOT_COMMITTED` and 6b rolls
    back. The release, given the `journal_tokens` captured before the
    rollback, restores `OPEN`, on an attached branch and on a detached
    `HEAD` alike. No orphan test runs, and no literal is requested. B
    can then reserve. A regression variant that passes only the current
    token leaves `RESOLVING` behind and is detected.
29. **The entry table is the command.** A text test over the `2.6.0`
    `approve-review.md` asserts each row of section 5.6's entry table:
    4d follows 4c and is named nowhere else, 4b still skips 4c-6 after a
    takeover, 6a1 names the held check and the `amend_recovery` mode, 6b
    captures the tokens before calling `rollback_plan_approval_transaction`,
    and the advance precedes 6d.
<!-- /CP6 -->

<!-- CP7 -->
**CP7 -- Compose the 2.6.0 release.**

1. Complete `migration/overlays/2.6.0/classification.json`.
2. Run `python3 tools/build_release.py --overlay migration/overlays/2.6.0`,
   then `--check`.
3. Add `tests/support.py` `CI_SUITES["2.6.0"]`, derived from the overlay
   suites' real counts.
4. Add the empty `migration/portability_exceptions.json` `by_version["2.6.0"]`
   entry, unless a genuine exception arises, which must then be justified.
5. Add the per-release classes: `TestConformanceFixture260` and
   `TestBootstrappedTarget260` (`tests/test_conformance_suite.py`),
   `TestBootstrappedRepositorySatisfiesTheFrozenSuite260`
   (`tests/test_bootstrap_e2e.py`), and the README pin
   (`tests/test_internal_references.py`).
6. Update `README.md`'s Status row and build commands, `docs/MIGRATION.md`'s
   `2.6.0` record, and `CLAUDE.md`'s 2.6.0 downgrade-posture paragraph
   (section 6.2). That paragraph also states the mixed-release posture:
   mutual exclusion is guaranteed only once every registered worktree's
   branch has merged the `2.6.0` update (revision 3, `LPR-R2-003`).
7. Record a `2.6.0` disposition in each of `docs/defects/v2.4.0-001`, `-002`
   and `-003`: closed, citing the tests. The `-001` record also documents
   the out-of-scope process-item update hazard (section 3.2). The `-002`
   disposition is **closed, qualified**: closed for every repository whose
   registered worktrees have all merged the `2.6.0` update, with section
   5.6's residual stated verbatim (revision 3, `LPR-R2-003`).

Derive the README values from this checkpoint's own full, non-`--fast`
`tests/run_all.py` run. `git diff <base_commit> -- distribution/workflow/2.5.1/`
must be empty.
<!-- /CP7 -->

<!-- CP8 -->
**CP8 -- Disposable-repository and linked-worktree acceptance.**

New `tests/test_workflow_2_6_0_hardening_disposable_repo.py`. It uses
`src/workflow_manager` bootstrap/update and `fixture.build_target_repo`/`drive_synthetic_work_item_through_checkpoints`,
drives the *installed* scripts in subprocesses, and has one class per
scenario:

1. Fresh `2.6.0` work item: scoped feedback, with two concurrent items not
   colliding, and CLI output matching.
2. Bootstrap `2.5.1`: item A completes and leaves flat feedback. Update to
   `2.6.0`. New item B's local plan-review write succeeds at its scoped
   path, and A's file is untouched.
3. An active legacy item in manual plan review with an unconsumed flat file
   is updated to `2.6.0`. The record and apply steps find the flat file and
   the item proceeds.
4. Bootstrap `2.3.1` and `2.4.0` items without a local exclude, commit the
   update to `2.6.0`, then check:
   - `implementing_entry_reachable` holds;
   - plan and implementation digests equal their recorded or pre-update
     values (product item);
   - a genuinely novel path still raises.
5. Plan-review remediation with both forced generation-failure variants:
   non-ready phase, then retry, then bound, with a single revision bump.
6. Plan approval with a brand-new protected companion file: the commit
   contains it, the recomputed identity is equal, and there is exactly one
   approval commit. Include a crash-after-commit resume.
7. Cross-worktree amendment/checkpoint contention across two linked
   worktrees of the disposable repository: both orders plus the stale-state
   case. Plus a mixed-release case (revision 3, `LPR-R2-003`): a third
   linked worktree on a branch that has not merged the `2.6.0` update
   requests an amendment with its own installed `2.5.1` scripts. A claim
   from an updated worktree then refuses with
   `LaggingWorktreeAmendmentError`, and no `NONE` sentinel is written
   while that worktree lags. Plus the resolution cases (revision 7,
   `MPR-R1-I1`): two updated worktrees carrying the same open amendment
   each drive `/approve-review plan` on a different amended plan through
   the installed scripts. Exactly one approval commit lands, the other
   refuses with `AmendmentResolutionReservedError` (or
   `StaleLifecycleStateError` once `RESOLVED`), and the witness records
   the winner's digest. A lagging worktree's unreserved `2.5.1`
   resolution of the same seq with a different plan is then refused with
   `AmendmentResolutionConflictError`.
8. A non-empty `AMENDMENT_DIFF.patch` during an open amendment, with the
   archive member identical.
9. Update `2.5.1` to `2.6.0` with items at `AWAITING_LOCAL_PLAN_REVIEW`,
   `IMPLEMENTING` and `AMENDING_PLAN`:
   - committed state bytes are unchanged by the update;
   - each proceeds through its next gate;
   - the `AMENDING_PLAN` item's witness is established by the scan;
   - a fourth item, `REVISING_PLAN` mid-apply with no
     `plan_review_binding`, gets the legacy marker at entry, refuses bind at
     that revision, and binds after one advance (section 6.1).

Plus a closed-defect census class, which asserts that the named regression
tests for `v2.3.1-001`/`-002`/`-003` (section 3.8) exist in
`distribution/workflow/2.6.0/payload/` and pass there.

If a scenario exposes a payload defect, fix it in the overlay, re-run CP7's
build/`--check` and re-derive CI counts. Record that explicitly.

**Tooling scope** (revision 2, `LPR-R1-005`). Scenarios 3, 5, 7 and 9 need
drivers that `src/workflow_manager/fixture.py` does not have today (it only
drives an item through checkpoints). New drivers go in the test module or a
`tests/` helper first. If extending `fixture.py` is the cleaner design, it
is allowed. The work item's artifacts declaration classifies
`src/workflow_manager/`, `tools/` and `pyproject.toml` as plan-stage
excluded, and `src/workflow_manager/`/`tools/` as implementation-stage
protected (`pyproject.toml` excluded), exactly as
`plan-amendment-mechanism-artifacts.json` does after its own
`UnclassifiedPathError` wedge (`B-R27-1`, `O-R28-1`). Any `src/` change is
then reviewed at the implementation stage, and never wedges identity
computation.
<!-- /CP8 -->

<!-- CP9 -->
**CP9 -- Full regression and parity (verification-only).**
- `python3 tests/run_all.py --fast`, then the full `python3 tests/run_all.py`,
  must be green.
- The clean-target failure set must equal `by_version["2.6.0"]` exactly.
- `tools/build_release.py --overlay migration/overlays/2.6.0 --check` must
  pass.
- `git diff <base_commit> -- distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/`
  must be empty.
- Read back README's `2.6.0` row against this run.

This checkpoint writes no artifact. A disagreement is a defect for the
owning checkpoint to fix.
<!-- /CP9 -->

## 8. Requirements traceability

| id | requirement (abridged; full text in the mapping file) | checkpoints |
| --- | --- | --- |
| REQ-1 | New items use `.ai-review/<id>/feedback/` by construction; no cross-item blocking | CP3, CP8 |
| REQ-2 | One authoritative resolver plus CLI contract; legacy rule explicit; completed legacy feedback never blocks or is reinterpreted | CP3, CP8 |
| REQ-3 | Legacy installation-record classification: release-derived, exact-path, fallback-only, identity-neutral, otherwise fail-closed | CP1, CP8 |
| REQ-4 | Review-ready only with a bound bundle; recoverable, idempotent generation | CP4, CP8 |
| REQ-5 | Approval commit closure over the declared protected set, proven pre-commit; post-commit identity equal | CP5, CP8 |
| REQ-6 | Post-commit verification from committed truth; named errors; no second or amended commit on input errors | CP5, CP8 |
| REQ-7 | Cross-worktree mutual exclusion: repo-global lock plus witness, stale state refused, at most one repository-valid resolution per amendment sequence, reserved before any approval commit and never collapsed at bootstrap (revision 7, `MPR-R1-I1`), crash recovery, census updated; guaranteed once every registered worktree has merged the `2.6.0` update, with lagging worktrees detected and refused on an unrecorded amendment before that (revision 4, `LPR-R3-008`) | CP6, CP8 |
| REQ-8 | `AMENDMENT_DIFF.patch` reflects the uncommitted amendment under review; convenience-only | CP2, CP8 |
| REQ-9 | `v2.3.1-001/-002/-003` stay regression-protected | CP8, CP9 |
| REQ-10 | `2.6.0` composed from the immutable `2.5.1` base plus overlay; docs, defect records and downgrade posture updated | CP7, CP9 |
| REQ-11 | Update from installed `2.5.1` preserves active legacy items through their next gate | CP8 |

## 9. This milestone's own review logistics

This work item was created under the installed `2.5.1`, so it has no
`feedback_layout` stamp and resolves feedback through the **legacy flat
path** for its whole life, even after `2.6.0` is later installed here
(INV-7).

**Historical evidence, now discharged** (revision 2, `LPR-R1-007`). At
creation, the completed `workflow-2-5-1-checkpoint-id-compatibility`'s
consumed `APPROVE` verdict sat at `.ai-review/feedback/REVIEW_FEEDBACK.md`.
`/review-plan` step 8's ownership guard would have refused this item's
first local plan-review write (section 3.1). The endorsed `2.5.1`
recovery (`review-implementation.md:284-300`) is to remove that file by
hand, since its owner is `MILESTONE_COMPLETE`. This plan left that to the
operator. The operator removed it before the round-1 local plan review,
so that review's write did not hit the guard. The flat path now holds
this item's own round-1 `REVISE` feedback. That sequence is itself the
live evidence for section 3.1: a manual deletion was the only way
forward.

**Consequence for this item's later rounds.** The flat file now belongs to
this item, which is non-terminal, so it will block every *other* work item's
flat-path write until this item completes, or until `2.6.0` is installed
here and the other item is created scoped. No other work item is active in
this repository.

## 10. `SELF_REVIEWING_PLAN`

- **Scope discipline.** Each design maps to one roadmap item and one
  reproduced defect. Several things were considered and deliberately left
  out:
  - an update-time preflight (roadmap 5);
  - a fix for the process-item update rewrite hazard (documented only);
  - lock-free forward completion of a dead owner's `COMMITTED` approval
    (section 5.4 item 7);
  - a generalized multi-work-item lifecycle lease (roadmap 7/9);
  - persisting feedback history.

  No speculative hardening is included.
- **Is anything already closed?** No. Every item reproduced on `2.5.1`
  (section 3), so none converts to regression-only. The `v2.3.1-*` items
  are regression-only and are handled that way (CP8 census, CP5
  `v2.3.1-003` re-proof).
- **Migration risk.**
  - New persisted vocabulary: the `feedback_layout` field, the
    `plan_review_binding` record, the witness files (including the `NONE`
    sentinel and, since revision 7, the `RESOLVING` reservation), the
    `resolved_review_content_id` key on resolved `amendment_history`
    entries (revision 7), and the written `current_bundle_id`. Each is additive, and
    each is covered by section 6.2's downgrade paragraph.
  - The phase-semantics change (a mirror-only publish) is the riskiest edit
    for legacy items mid-plan-review. Section 6.1 plus CP8 scenario 9 cover
    it. Revision 4 closes its one sink: every ready-phase row now has an
    in-band exit, through the withdrawal transition (section 5.3 item 7),
    which reuses the existing non-ready phases. Revision 5 closes three
    more of the same class: the publish call moves after
    `/milestone-plan`'s self-review; publish and the mirror advance run
    only on a plan-stage phase allow-list; and the withdrawal needs no
    fresh id. Revision 6 closes the mirror-image gap, an exit after the
    publish and before the bind (`/apply-plan-review` step 6 for `2.x`).
    It also removes an approval wedge for protected paths that are
    unchanged since `base_commit` (section 5.4 item 2). Revision 7 closes
    the last remaining exit of that class, `/apply-plan-review` step
    7'.2's second generation (`MPR-R1-O1`).
  - A `2.5.1`-era habit changes on update (revision 5, `LPR-R4-002`):
    `/milestone-plan <id>` on an item at `IMPLEMENTING` used to re-enter
    plan review silently, with no amendment. `2.6.0` refuses it before
    writing anything and names `/request-plan-amendment <id>`. Section
    6.1 records this for operators.
  - The plan-stage author-input move to `plan-inputs/` changes where
    operators write `REVIEW_REQUEST.md`/`TEST_RESULTS.md`. The read-only
    seeding from `current/` keeps an operator who has not moved working,
    and the implementation stages are untouched.
  - CP6's worktree scan and lag probe are the only new cross-worktree
    *reads*. Once no worktree lags, the scan runs at most once per item
    (section 5.6's sentinel), and the probe reads one committed blob per
    worktree. Other worktrees' state files are read on every acquisition
    only while a worktree lags. Their results only ever cause refusals.
- **Concurrency correctness.** The new lock is a pure source. So the
  existing census rule (no blocking chaining) proves no new cycle without
  switching to a full topological check. The witness uses `os.replace`, not
  `os.link`, deliberately staying outside the `os.link` primitive predicate.
  A reviewer should challenge whether any path can take (9) while holding
  (1)/(5)/(6)/(8). CP6 test 14 is the mechanical answer.
- **Resolution is part of the lifecycle** (revision 7, `MPR-R1-I1`).
  Revision 6 serialized an amendment's request and its claims, but let
  two worktrees resolve the same seq independently. The witness then
  compared only the request projection, so bootstrap could collapse two
  different resolutions into one `RESOLVED`. Three shapes were weighed:
  - Single-resolution ownership by the requester branch. Rejected: it
    forbids the ordinary flow of finishing an amendment on another
    worktree or branch, and it needs an ownership-transfer mechanism.
    Revision 7 needs neither.
  - Resolution identity in the witness alone. Rejected on its own: it
    detects a second resolution only after its approval commit exists,
    which INV-5's "exactly once" spirit forbids for the repository-global
    case.
  - **Chosen:** a `RESOLVING` reservation under (9), bound to the
    journal's pinned expected post-state, taken once before first-commit
    staging (revision 8 drops "re-taken on every resume": the command has
    no such resume). It is combined with a separate resolution
    digest recorded in `RESOLVED` and compared at every predicate, at
    bootstrap and in the lagging scan. The reservation prevents the race
    among `2.6.0` processes, and the digest detects everything the
    reservation cannot see (lagging `2.5.1` resolvers, pre-upgrade
    history). The journal is never held under (9), and no lock-order
    edge is added.
- **The reservation follows the command's real recovery graph**
  (revision 8, `LPR-R7-001`). Revision 7 specified the reservation's
  recovery against an idealized "resume re-enters step 5" model.
  `approve-review.md`'s real graph is 4b stop → takeover → 6a, then 6a1,
  6b or 6c. Two alternatives were weighed for the one real re-entry into
  step 5 (6a1):
  - Let 6a1 re-run `reserve_amendment_resolution`. Rejected: the
    reservation runs the predicate list, whose step 1 would advance or
    conflict on `HEAD`'s entry. That is exactly the blob 6a1 may be
    repairing, and a `RESOLVED` witness has no reservation to match.
  - Change 4b so that a takeover resumes at 4d. Rejected: section 5.4
    item 7 keeps the takeover gate unchanged, and a crash before 4d has
    nothing staged, so rollback plus a fresh run costs one re-invocation
    and no new state.
  - **Chosen:** a separate, read-only held check at 6a1 against the
    journal's pinned digest, an explicit staging mode, and a release that
    matches every token the journal ever had. Section 5.6's entry table
    enumerates every command entry with its lifecycle call, and CP6 test
    29 pins it against the command text, so the design and the command
    cannot drift apart again unnoticed.
- **Unnecessary complexity.** For item 6, two designs were weighed:
  - Scanning all worktrees' state *instead of* a witness. Rejected as the
    primary mechanism: it cannot see an amendment on a branch checked out
    in no worktree, and it records no ownership identity. It is kept only
    as the upgrade bootstrap.
  - A witness without a lock. Rejected, because it leaves cause 1 open.

  For item 3, a new "bundle pending" phase was rejected in favor of keeping
  the existing non-ready phases, which adds no persisted phase vocabulary.
- **Missing tests.** Every item has adversarial interruption,
  stale-state, linked-worktree or legacy-active-item coverage in its own
  checkpoint (sections 7 and 8). CP8 re-proves each item end to end through
  installed scripts.
- **Checkpoint size.** CP6 is the largest (`session_target: 2`). Splitting
  lock and witness was rejected, because the defect record itself says
  landing either alone is a partial fix that must not ship.

## 11. `docs/TECHNICAL_DECISIONS.md` cross-check

This repository has no `docs/TECHNICAL_DECISIONS.md` (checked at the base
commit). No open decision row exists to be silently finalized. The one
decision this plan takes that a reviewer may want to own explicitly is the
release number **`2.6.0`** (not `2.5.2`). It introduces new persisted
vocabulary and a new downgrade constraint, which this repository's
precedent (`2.4.0`, `2.5.0`) treats as a minor bump. Neither
`release._version_key` nor any test assumes otherwise.

## 12. Review-round dispositions

### Round 1 (`LOCAL_MODEL_PLAN_REVIEW`, `REVISE`) -> Revision 2

| Finding | Disposition | Where |
| --- | --- | --- |
| `LPR-R1-001` (blocking) | **Accepted.** Validated: `record_local_plan_review`/`record_manual_plan_review(verdict="REVISE")` write no ledger (`workflow_state.py:12383-12427`, `:12504-12546`), so no durable fact distinguished consumed content. Fixed with the `plan_review_binding` record keyed on `review_content_id`, the bind-internal `ConsumedPlanReviewContentError`, the legacy marker, a fourth status `NEEDS_EDIT` consulted at command entry, and the reconciled recovery table. | 5.3 items 2-6, 6.1, 6.2, CP4, CP8 scenario 9 |
| `LPR-R1-002` | **Accepted.** Validated: `capture_plan_stage_pin` rewrites `.ai-review/<id>/.pin` on every generation (`workflow_fingerprint.py:2208-2239`, called at `:3779`); the fifth member compares against `<bundle_dir>/files/<path>` (`:1099-1107`). Freshness now reads the bound bundle's `files/` copies, per member kind; the pin is also staged and renamed with `current/`. | 5.3 item 5, 5.4 item 2, CP4, CP5 |
| `LPR-R1-003` | **Accepted.** Validated: `capture_plan_stage_pin` raises `AbsentProtectedPathError` for a declared-but-absent path (`:2230-2232`). Pathspec widened to the base-plus-current union; deletion and rename are stated and tested only in their reachable form. | 5.5, CP2 |
| `LPR-R1-004` | **Accepted.** Fixed predicate order (self-heal first), `HEAD`-only resolution test on both sides, deterministic bootstrap derivation (max seq, any-`HEAD`-resolved gives `RESOLVED`, requester rule, conflict refusal), and a `NONE` sentinel so that the scan runs at most once. Census target counts are stated. | 5.6, CP6 13a-13e, 14 |
| `LPR-R1-005` | **Accepted** (the declaration option). Validated: the artifacts declaration names none of `src/`, `tools/` or `pyproject.toml`, while `plan-amendment-mechanism-artifacts.json` does. The declaration is extended to match the precedent. | `<id>-artifacts.json`, CP8 |
| `LPR-R1-006` | **Accepted.** `apply-functional-review.md` (~244-253) and `publish_plan_revision`'s docstring are added to CP4's list. | CP4 |
| `LPR-R1-007` | **Accepted.** Section 9 is restated as discharged historical evidence; section 3.1 and the section 3 table are put in the past tense. | 3, 3.1, 9 |
| `LPR-R1-008` | **Partially accepted.** `state_lock` is at `:1409`, now cited; `:1381` is kept for `STATE_LOCK_PATH`, which is what that reference named. **Rejected half:** the `AMENDMENT_DIFF` `git diff` is at `prepare-ai-review.sh:470-471` as the plan said: `:470` opens `subprocess.run(` and `:471` is `["git", "diff", f"{base_commit}..HEAD", ...]` (checked with `grep -n HEAD scripts/prepare-ai-review.sh`). `:~463-466` is the state-read preamble (`history = ...`, `is_open = ...`). Section 3.7 now names both lines explicitly. | 3.6, 3.7 |
| `LPR-R1-009` | **Accepted.** The removal set is empty by definition when `<id>-artifacts.json` (or the path) is absent at `HEAD`. | 5.4 item 1, CP5 |

The architecture note ("bind legitimacy local to one function") is adopted
in 5.3 item 3. No checkpoint was added, removed or renamed, so the
registry's checkpoint set and the mapping's requirements are unchanged.
Only `plan_revision` advances.

### Round 2 (`LOCAL_MODEL_PLAN_REVIEW`, `REVISE`) -> Revision 3

| Finding | Disposition | Where |
| --- | --- | --- |
| `LPR-R2-001` (blocking) | **Accepted.** Validated: `apply-plan-review.md` step 3 edits `plan_path` before step 5 regenerates the registry and publishes, so a mid-edit crash left the mirror, the registry and the `CONSUMED` revision equal while the fresh id differed, which revision 2 classified as `PUBLISHED_UNBOUND`. The reviewer's first option is taken: `publish_plan_revision` writes a durable `PUBLISHED` record carrying the fresh id, and is called on every round. The second option (every round bumps, and the mirror advance is the fact) is **rejected with evidence**: `/milestone-plan` step 1's `route_work_item` advances the mirror before any edit (`workflow_state.py:7742`), so a mirror advance cannot mean "edits complete" for an amendment. `bind` now also requires `PUBLISHED` content. The status is a single, total decision table, including a new `EDIT_IN_PROGRESS` value and rows for no record, no registry and non-plan phases. The recovery table is corrected, and CP4 tests are added. | 5.3 items 1-3 and 6, recovery table, CP4 |
| `LPR-R2-002` | **Accepted.** Validated: `check_manual_stage_bundle_id_advisory` (`workflow_state.py:12485-12501`), `record-manual-plan-review.md:86-91` and `PLAN_REVIEW_WORKFLOW.md:82-84` make a wrapper-only regeneration advisory at the manual stage. The readers are now keyed on `review_content_id`, and the `bundle_id` vs `current_bundle_id` comparison is advisory. `bind` never changes a ready phase (`PlanReviewAlreadyReadyError`). The legacy back-fill is dropped: nothing needs it, because the next `REVISE` writes `CONSUMED` from its own inputs. CP4 tests are added. | 5.3 items 3-4, 5.4 item 2, 6.1, CP4 |
| `LPR-R2-003` | **Accepted.** Validated: the installed release is recorded per branch in the committed `.workflow-manager/installation.json` (`"workflow_version": "2.5.1"` here), and `scripts/` and `.claude/commands/` are committed alongside it. The mixed-release posture is stated in 5.6, 6.1, 6.2, CP7's `CLAUDE.md` paragraph and the `v2.4.0-002` disposition, which becomes "closed, qualified". Decision: a lag probe on every (9) acquisition. While any worktree lags, the `NONE` sentinel is never written, and the lagging worktrees' states are scanned, refusing on an unrecorded unresolved amendment (`LaggingWorktreeAmendmentError`). A lagging worktree alone does not refuse a claim. Pinned by CP6 13f/13g and CP8 scenario 7. | 5.6, 6.1, 6.2, 10, CP6, CP7, CP8 |
| `LPR-R2-004` (optional) | **Accepted, both halves.** `<id>-artifacts.json` joins the `AMENDMENT_DIFF.patch` pathspec, and the per-path claim is restated as "when changed". | 5.5, CP2 |
| `LPR-R2-005` (optional) | **Accepted.** The fork check (bootstrap step 3) now runs before the status decision. It compares the request-time projection of entry `S`, which excludes the two resolution fields `apply_plan_approval` adds (`workflow_state.py:10907-10915`). | 5.6, CP6 13c |
| `LPR-R2-006` (optional) | **Accepted.** The duplicate CP4 bullets are merged, and the status bullet now covers every row of the revised table. | CP4 |
| `LPR-R2-007` (optional) | **Accepted.** The durable feedback check is `/apply-plan-review`-only. `/milestone-plan` on an `AMENDING_PLAN` item runs none. | 5.3 item 6, CP4 |

The architecture note is adopted: the status is now one decision table
over the durable facts plus the fresh id. Bind legitimacy stays inside
the mutator, and is strengthened by the `PUBLISHED` requirement. No
checkpoint was added, removed or renamed, so the registry's checkpoint
set and the mapping's requirements are unchanged. Only `plan_revision`
advances, to 3.

### Round 3 (`LOCAL_MODEL_PLAN_REVIEW`, `REVISE`) -> Revision 4

| Finding | Disposition | Where |
| --- | --- | --- |
| `LPR-R3-001` (blocking) | **Accepted.** Validated: `/milestone-plan` refuses only a terminal target (`milestone-plan.md:79`); `route_work_item`'s resume branch advances the mirror for any non-terminal entry (`workflow_state.py:7742`); `publish_plan_revision` flips a `"2.1"`/`"2.2"` item to `AWAITING_LOCAL_PLAN_REVIEW` from any non-terminal phase (`:7790-7807`); and `validate_local_plan_review_preconditions` checks only version and phase (`:12368`). So revision 3 left ready phases as a sink. The reviewer's second option is taken, because it keeps `2.5.1`'s "re-plan returns to local review" semantics: a new `withdraw_plan_review` transition (ready to `REVISING_PLAN`, or `AMENDING_PLAN` for an open amendment, writing `CONSUMED` from `bound`), called only at `/milestone-plan`'s entry. `publish_plan_revision` and `route_work_item`'s revision advance now refuse at a ready phase (`PlanReviewInProgressError`), so no single call leaves a non-`BOUND` record at a ready phase. Row 4 is split into 4a-4d, each with a named remedy (restore from `current/files/`, regenerate, or withdraw); the verifier's refusals are named by cause. The recovery table, 6.1 and CP4 tests are extended. | 5.3 items 1-4, 6, 7; recovery table; 6.1; 10; CP4 |
| `LPR-R3-002` | **Accepted.** Validated: the author writes the wrapper files into `<bundle_dir>` before generating (`apply-plan-review.md` step 5; `milestone-plan.md:265-275`), the generator only stubs missing ones (`prepare-ai-review.sh:364-373`), and `finalize_bundle_generation`'s failure path calls `withdraw_bundle` (`workflow_fingerprint.py:2388-2410`). Decisions: plan-stage author inputs move to `.ai-review/<id>/plan-inputs/` and are copied into the staging directory (seeded read-only from `current/` for an unmoved author); a plan-stage staging failure removes only its own staging artifacts, calls no `withdraw_bundle` on `current/` and writes no `REJECTED` marker, recorded as a deliberate `WFR-67` revision; staging is plan-stage only. Evidence that the marker question matters less than feared: a *completed* `withdraw_bundle` already removes its own marker (docstring at `:2388-2410`), so only a partial withdrawal leaves one. CP4's byte-identity test now drives the real command order; CP5's expected error is aligned by making the step-2 reader raise the same `ReviewedContentDriftError`. | 5.3 items 3 and 5, 5.4 item 2, 6.2, 10, CP4, CP5 |
| `LPR-R3-003` | **Accepted.** Validated: `/milestone-plan` step 3 publishes at `milestone-plan.md:208-213`, before the intent-to-add step at `:214-245`, and `resolve_plan_stage_metadata` requires index-visible paths. The staging step moves ahead of the publish call in both commands, and a CP4 test pins the order. | 5.3 item 2, CP4 |
| `LPR-R3-004` | **Accepted.** Validated: `request-plan-amendment.md` step 3 commits `AMENDING_PLAN` on the requester's branch, so a later branch switch hides it from the revision-3 test. The provable-orphan test now also requires the requester's `HEAD` to still be on `requester_branch`, that branch's tip to lack seq N, and no registered worktree to hold an entry N with the witness's projection digest. If the amendment is found anywhere, the holder refuses with no literal; if the test cannot complete, only the evidence-bound literal is offered. | 5.6 crash table, CP6 7a |
| `LPR-R3-005` | **Accepted** (the digest option). Validated: an `amendment_history` entry holds `amendment_id`, `requested_at`, `requested_from_phase`, `reason`, `superseded_plan_revision`, `superseded_plan_approval`, `checkpoints_snapshot` and `pre_amendment_approval_commit` (`workflow_state.py:11108-11118`), and the revision-3 witness stored only `requested_at` of them. The witness gains `request_projection_sha256`, computed by one function that bootstrap step 3 and the lagging comparison both use; "does not record" is restated over stored fields only. | 5.6, CP6 13g and 13i |
| `LPR-R3-006` (optional) | **Accepted, both halves.** The legacy-marker feedback check is restated as `work_item` equal to the target and `status == REVISE`; the revision half is dropped, since `parse_review_feedback_binding_fields` has no revision field (`workflow_fingerprint.py:2842-2857`). A legacy `AMENDING_PLAN` item takes its `CONSUMED` record from its open amendment entry's `superseded_plan_approval.approved_review_content_id`/`superseded_plan_revision`, avoiding the forced second advance. | 5.3 items 2 and 6, 6.1, CP4 |
| `LPR-R3-007` (optional) | **Accepted.** An explicit predicate step for a `NONE` witness; `bare` worktree entries are skipped and not lagging; versions compare numerically through a payload-local helper pinned against `release._version_key` (`src/workflow_manager/release.py:216`), which the payload cannot import. | 5.6, CP6 13h |
| `LPR-R3-008` (optional) | **Accepted.** REQ-7's text, in section 8 and in the mapping file, is qualified: guaranteed once every registered worktree has merged the `2.6.0` update. | 8, mapping |

The architecture notes are adopted: CP4's mechanical enumeration now lists
every writer that can be attempted at a ready phase, and the `WFR-67`
revision is stated as such. No checkpoint was added, removed or renamed,
so the registry's checkpoint set is unchanged. The mapping keeps its 11
requirements, with REQ-7's description qualified. `plan_revision`
advances to 4.

### Round 4 (`LOCAL_MODEL_PLAN_REVIEW`, `REVISE`) -> Revision 5

| Finding | Disposition | Where |
| --- | --- | --- |
| `LPR-R4-001` (blocking) | **Accepted.** Validated: `milestone-plan.md` step 3 calls `publish_plan_revision` "in the same operation" as the registry write (`:208-213`); step 4 then says "Revise the plan in place" (`:246-249`) and must confirm the inherited `plan_stage` exclusion sets (`:175-177`), which the plan-stage id hashes (`:191-196`); step 6 generates. So under revision 4 any self-review edit made the bind refuse. The reviewer's first option is taken: `/milestone-plan`'s publish leaves step 3 for a new publication point between steps 5 and 6. That point re-runs the registry and mapping regeneration (a byte-identical no-op unless self-review changed checkpoints or requirements), re-embeds the table unconditionally, re-applies the intent-to-add step, then publishes. Step 3 keeps its first registry, mapping, declaration and table write and its staging step, so self-review reads a complete plan. `WFR-65` and `LPR-R3-003` orderings are kept. `/milestone-plan`'s bind is now stated (step 6, straight after generation). `/apply-plan-review` was checked and already publishes after its last protected edit. CP4's enumeration records this per command, and five CP4 tests cover it, including a pinning test for the old order. | 5.3 item 2, recovery table, 10, CP4 |
| `LPR-R4-002` | **Accepted.** Validated: `milestone-plan.md:79-80` refuses only a terminal target; `route_work_item`'s resume branch advances the mirror for any non-terminal entry (`workflow_state.py:7742`); `publish_plan_revision` flips any non-terminal `"2.1"`/`"2.2"` phase to `AWAITING_LOCAL_PLAN_REVIEW` (`:7790-7807`). Publish and the resume-branch advance now run only on the allow-list `PLANNING`/`REVISING_PLAN`/`AMENDING_PLAN`. Ready phases keep `PlanReviewInProgressError`, and every other phase refuses with the new `PlanReviewPhaseNotPlanStageError`, which names `/request-plan-amendment <id>` exactly when the phase is in `_AMENDMENT_REQUEST_ALLOWED_PHASES` (`:10943`). Row 1 is an explicit, write-free refusal at both command entries, evaluated before `route_work_item`. Caller check: `route_work_item(` appears in only `/milestone-plan` step 1 among the commands, and a remediation child is created at `PLANNING` (`create_remediation_child_work_item`, `:10216`), so no sanctioned caller is refused. `"1"` behavior and `/bootstrap-workflow-v2` are unchanged. | 5.3 items 1 and 6, recovery table, 6.1, 10, CP4 |
| `LPR-R4-003` | **Accepted.** Validated: `load_plan_revision` raises `PlanRevisionMismatchError` on a title/registry disagreement (`workflow_fingerprint.py:749-756`), and revision 4 read `F = ⊥` only at a non-ready phase. At a ready phase, `F = ⊥` now maps to row 4a with a `BOUND` record and row 4c with none. The readers re-raise the two errors as `ReviewedContentDriftError`/`PlanReviewBundleUnverifiedError` with the row's remedy. `/milestone-plan`'s withdrawal decides from the phase alone, and `withdraw_plan_review` reads only the phase, the record and `amendment_history`, so no worktree state can block it. CP4 tests cover a bumped title and a deleted protected path, with and without a record. | 5.3 items 4, 6 and 7, recovery table, CP4 |
| `LPR-R4-004` (optional) | **Accepted.** Validated: `apply_plan_approval` has no phase check (`workflow_state.py:10779` onward), and `read_plan_approval_journal` (`:2393`) returns the open journal, whose required fields include `work_item_id` (`:2383-2389`). `/milestone-plan`'s entry refuses the withdrawal with `PlanApprovalInProgressError` while a journal for this item is open, and on an unreadable journal, following that function's own fail-closed contract. The check is in the command entry; `withdraw_plan_review` stays pure. | 5.3 item 6, CP4 |
| `LPR-R4-005` (optional) | **Accepted** (the restate option). Validated: item 1 defines a removal member as absent from both the current declaration and the worktree, so revision 4's CP5 case "re-created in the worktree ... refused by the per-member check" named a non-member. The alternative (removal candidates independent of worktree presence, refusing any present one) is **rejected**: it would refuse a legitimate, reviewed de-protection that keeps the file, which item 1 deliberately leaves to the classification gates. Item 2's vacuous worktree check is dropped. The removal check is now only "not captured by the bound bundle", and membership is computed immediately before staging. The CP5 case is restated: a re-created de-protected path is not a member, no deletion is staged, and the approval succeeds. | 5.4 items 1-2, CP5 |
| `LPR-R4-006` (optional) | **Accepted.** Validated: under `2.5.1`, `publish_plan_revision`'s flip left `plan_review_stages` keyed on an unchanged `review_content_id`, so an unchanged re-run stayed re-reviewable; revision 4's withdrawal consumes the content. Withdrawal now needs an explicit id: a no-argument `/milestone-plan` that resolves to a ready item refuses with `PlanReviewWithdrawalNeedsExplicitIdError`, reporting what a withdrawal would discard. A named-id run reports the same consequences. The `MILESTONE_WORKFLOW.md` `BLOCK` rows (`:246`, `:249`) join CP4's doc updates. | 5.3 item 6, CP4 |

The architecture notes are adopted. CP4's enumeration now lists, per
command, every step that can edit a plan-stage protected path, and shows
the publish after all of them. The phase guards on publish and the
resume-branch advance are an allow-list. No checkpoint was added, removed
or renamed, so the registry's checkpoint set and the mapping's 11
requirements are unchanged. `plan_revision` advances to 5.

### Round 5 (`LOCAL_MODEL_PLAN_REVIEW`, `REVISE`) -> Revision 6

| Finding | Disposition | Where |
| --- | --- | --- |
| `LPR-R5-001` | **Accepted** (the reviewer's first option). Validated: for `"2.1"`/`"2.2"`, "steps 1-6 execute identically" (`apply-plan-review.md:41-42`), and step 6 (`:140-142`) stops on `BLOCK` or on a "major structural changes" judgment before step 7' runs. Under revision 5, 7' is the bind, so step 6 stranded the item at row 9, unannounced. Step 6 is now `"1"`-only, so 7' always runs for `TWO_STAGE_PLAN_REVIEW_VERSIONS` items. That matches 7''s own "regardless of how large or small a 'structural change' judgment" rule. Binding inside step 6 was rejected: it would put a second call site for the same bind in one command. The `BLOCK` clause is restated for `2.x`. A `BLOCK` leaves the item at its ready phase (`MILESTONE_WORKFLOW.md:246`, `:249`), so it is resolved there, by re-review (row 2) or by an edit plus `/milestone-plan <id>`. Step 1 accepts only `Status: REVISE` for `2.x` (`FeedbackStatusNotApplicableError`), the same condition the legacy-marker check already applies. The rule "no exit between publish and bind" is added next to "publish after the last edit". The only remaining exits are the generator failures, and each report names the explicit-id re-run. CP4's command list gains step 6 and the failure reports, its enumeration covers exits per command, and four tests are added. | 5.3 items 2, 3 and 6; recovery table; 10; CP4 |
| `LPR-R5-002` | **Accepted**, keyed on `base_commit`. Validated: `files/` holds only paths in `git diff --name-status -z "$BASE_SHA"` (`prepare-ai-review.sh:497-510`); the pin refresh never adds an entry (`workflow_fingerprint.py:2259-2267`); and the fifth-member precedent is gated on "differs from `HEAD`" (`:1097-1099`). The `workflow-v2-1-core-artifacts.json` precedent protects pre-existing `docs/TECHNICAL_DECISIONS.md`. Expected bytes are now the capture if one exists, else the `base_commit` blob, else a refusal. `base_commit` was chosen over `HEAD` because it is the generator's own capture condition, which makes the check total. Untracked paths are captured because the generator marks them intent-to-add first (`prepare-ai-review.sh:134-141`). A `HEAD` key would still need a source for a member that differs from `HEAD` but equals its `base_commit` blob. "Exactly the rule the fifth member follows" is corrected to "adapted from", and it now quotes the precedent's gate. CP5 gains the unchanged-companion approval and the restated no-capture refusal, plus two edge cases. | 5.4 item 2, 10, CP5 |
| `LPR-R5-003` (optional) | **Accepted.** Validated: `MILESTONE_WORKFLOW.md:130-133` and the `milestone-plan.md` step 6 heading (`:253`). Both are named in CP4's doc and command lists. | CP4 |
| `LPR-R5-004` (optional) | **Accepted.** Validated: `milestone-plan.md:21-25` has a one-argument base-SHA form that does not name the target. The guard is now keyed on "no work-item-id argument". The CP4 test covers both non-naming forms. | 5.3 item 6, CP4 |
| `LPR-R5-005` (optional) | **Accepted.** "Two further cases" becomes "One further case", with a cross-reference to the removal-member bullet. | CP5 |

The architecture notes are adopted. CP4's enumeration now records both
properties per command: the publish after every protected edit, and no
exit between the publish and the bind other than the reporting
generator-failure exits. The precedent in section 5.4 item 2 is quoted
with its gate and labelled as adapted. No checkpoint was added, removed
or renamed, so the registry's checkpoint set and the mapping's 11
requirements are unchanged. `plan_revision` advances to 6.

### Round 6 (`MANUAL_EXTERNAL_PLAN_REVIEW` round 1, `REVISE`) -> Revision 7

Feedback bound to bundle `1b485b7f…3891`, `review_content_id`
`8e5ca86a…0816`, plan revision 6. The local stage had approved the same
content (round 6). Finding ids are prefixed `MPR-R1-`.

| Finding | Disposition | Where |
| --- | --- | --- |
| `MPR-R1-I1` (important) | **Accepted.** Validated: `apply_plan_approval` resolves the open entry from the worktree's own state alone, setting `resolved_at_plan_revision` and `reconciliation_outcome` and rewriting `checkpoints`/`current_checkpoint_id` (`workflow_state.py:10846-10915`). No lock or witness is consulted. Revision 6's approval side took (9) only after the commit (section 5.6), and `amendment_request_projection_sha256` removes exactly the two resolution fields. So two worktrees could each commit a different resolution of seq N, and bootstrap step 4 would choose one deterministically. Fix: new INV-10. A `RESOLVING` witness state, reserved under (9) by `reserve_amendment_resolution` at a new `/approve-review plan` step 4d, after the journal opens and before staging, bound to the journal's pinned expected post-state, and re-reserved on every resume or takeover. A separate `amendment_resolution_projection_sha256`, over the new `resolved_review_content_id` plus revision and outcome, is recorded in `RESOLVED` and compared at predicate steps 1 and 3 (`AmendmentResolutionConflictError`), in the lagging scan, and at bootstrap for every shared seq, with a trailer-derived check for legacy entries (`AmendmentBootstrapConflictError`, writing nothing). The provable-orphan reservation test uses journal presence as liveness evidence, since the journal closes only after the advance or a completed rollback. The literal `clear amendment resolution` covers the undecidable cases. No flock is held across invocations, and no census edge is added. The residuals for lagging `2.5.1` resolvers and trailer-less legacy resolutions are stated. The design alternatives are in section 10. | 1, 4 (INV-10), 5.6, 6.2, 7 (CP6 tests 8, 13i, 17-24; CP8 scenario 7), 8 (REQ-7), 10, mapping |
| `MPR-R1-O1` (optional) | **Accepted** (the reviewer's first option). Validated: installed `apply-plan-review.md` step 7'.2 re-runs `./scripts/prepare-ai-review.sh <base-sha> plan <work_item_id>` after step 5 already generated, and has no failure report of its own. For `2.x`, 7'.2 is removed. Step 5 is the round's single generation, and 7' is the recomputation note, the verify-plus-bind, and the report. Keeping 7'.2 with its own failure report was rejected: a regeneration of unchanged content can change only `bundle_id`, which is advisory. A CP4 test pins one generator call per round. | 5.3 items 2-3, CP4 |

The architecture note ("request identity and resolution identity are
different facts") is adopted as INV-10, with two separate digests. No
checkpoint was added, removed or renamed, so the registry's checkpoint
set is unchanged. The mapping keeps its 11 requirements, with REQ-7's
description extended. `plan_revision` advances to 7.

### Round 7 (`LOCAL_MODEL_PLAN_REVIEW`, `REVISE`) -> Revision 8

Feedback bound to bundle `7580b00f…83bc5`, `review_content_id`
`97c5c891…f9d`, plan revision 7. The reviewer closed `MPR-R1-O1` and
closed `MPR-R1-I1` for the forward path.

| Finding | Disposition | Where |
| --- | --- | --- |
| `LPR-R7-001` (important) | **Accepted in full, (a)-(d).** Validated against the installed command and code: `approve-review.md` step 4b (`:321-359`) stops when a journal is open, and after a takeover resumes at 6a, "skipping straight past steps 4c-6". 6a1 (`:556-570`) is the one re-entry into step 5, re-running the staging and pin and then `git commit --amend`, with no second amend (`WF8c` 348(jj)). `take_over_plan_approval_transaction` appends the old token to `previous_owner_tokens` (`workflow_state.py:3156`). `rollback_plan_approval_transaction` closes the journal at its own step 5 (`:2513` onward). So revision 7's "re-reserve on every entry into step 5 or 6", its 4c/4d crash row and test 22(a)/(e) described an unreachable path. At 6a1, the step-5 assertion failed on a `RESOLVED` witness, and predicate step 1 conflicted on a hook-rewritten state blob. The release also missed a pre-takeover token. Fix: (a) 4d is the only reservation point; a crash before 4d recovers by 4b → takeover → 6a `NOT_COMMITTED` → 6b; the crash rows and test 22 are rewritten to that flow. (b) A new read-only `assert_amendment_resolution_held` at 6a1 accepts own-token `RESOLVING` (current or previous token) or `RESOLVED` with the journal's pinned digest, and never reads `HEAD`'s digest. Step-5 staging takes an explicit `first_commit`/`amend_recovery` mode. Predicate step 1 refuses a differing digest on the resolver's own `HEAD` with an open journal as `AmendmentResolutionReservedError` (in flight), never as a bind. `resolved_commit` is documented as a label, and the owner's advance refreshes it. (c) The release takes the `journal_tokens` captured before the rollback. (d) CP6 tests 25-28 are added, plus test 29 pinning the new per-entry table against the command text (the reviewer's architecture note). | 5.4 item 6, 5.6 ("Acquired by", "No bypass", predicate steps 1 and 2a, "Resolution side", entry table, crash table), 7 (CP6 command list, tests 21, 22, 25-29), 10 |
| `LPR-R7-002` (optional) | **Accepted.** Test 18 now states that the identical-plan refusal is intended, citing predicate step 3's "whether or not its amended plan is the same one", so an implementer does not turn it into an idempotent pass. | 7 (CP6 test 18) |

No checkpoint was added, removed or renamed, and no requirement changed,
so the registry and mapping are regenerated at `plan_revision` 8 with the
same content. No new persisted vocabulary is added: the held check writes
nothing, and the `resolved_commit` refresh rewrites an existing field.
Section 6.2 is therefore unchanged. `plan_revision` advances to 8.
