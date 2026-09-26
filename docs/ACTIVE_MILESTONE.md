# Active Milestone

## Milestone

`workflow-review-artifact-and-concurrency-hardening`
(`governing_workflow_version: "2.2"`, plan approved at revision 8): Workflow
`2.6.0` — review-artifact, publication and concurrency hardening.
Full plan: `docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`.

## Goal

Close the Workflow correctness defects and gaps that `docs/ROADMAP.md`
section 1 groups under review artifacts, review publication, approval commit
integrity, legacy active-work-item compatibility, amendment artifacts and
cross-worktree concurrency, as one bounded hardening release. Deliverable: a
new authored Workflow release, `2.6.0`, built as `distribution/workflow/2.5.1/`
(base, unchanged, byte-for-byte immutable) plus `migration/overlays/2.6.0/`,
per this repository's `CLAUDE.md` "Adding an authored Workflow release"
process. See the plan's section 2 for non-goals.

## Current checkpoint

**CP9 complete** (9 of 9 checkpoints). Every registry checkpoint is
complete and technically approved. Next: the functional review (see
"Functional review checklist" below).

### CP1 — Release-derived exact-path classification of the legacy installation record

Implements the plan's section 5.2, `D-Tooling-Ambient-Classification` (the
legacy-item half of `v2.4.0-001`; requirement `REQ-3`). Delivered in
`migration/overlays/2.6.0/` (this milestone's first overlay files, each a
full replacement starting from the `2.5.1` base copy):

- `payload/scripts/workflow_fingerprint.py`: new
  `TOOLING_AMBIENT_EXCLUDED_PATHS = frozenset({".workflow-manager/installation.json"})`.
  `classify_path` and `classify_path_implementation_stage` consult it only
  after every declared classification has failed, immediately before the
  `UnclassifiedPathError` raise. No other line of the module changed.
- `payload/scripts/workflow_fingerprint_test.py`: new
  `TestToolingAmbientExcludedPaths` (8 tests) — fallback classification at
  both stages with a `2.5.1` control arm (constant patched empty), explicit
  protected declaration still wins, siblings
  (`installation.json.tmp`, `other.json`, `.workflow-manager/`, bare and
  nested look-alikes) still raise, full-projection invariance with and
  without the fallback, and digest invariance: with the record unchanged
  every digest is identical; after an uncommitted and then a committed
  record change every digest (plan worktree/commit, implementation
  worktree/commit) that raised under `2.5.1` now equals its pre-change
  recorded value.
- `payload/scripts/workflow_state_test.py`: new
  `TestImplementingEntryReachableAfterInstallationRecordUpdate` — a
  2.3.1-shaped item stays `implementing_entry_reachable` after a committed
  installation-record change; the control arm raises `UnclassifiedPathError`.
- `payload/docs/ai-workflow/REVIEW_PROTOCOL.md`: the classification
  paragraph under "Computing `review_content_id`".
- `payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`: new section
  `D-Tooling-Ambient-Classification` carrying section 5.2's justification.
- `classification.json`: `base_workflow_version: "2.5.1"`, one `replaced`
  rule per touched file. Later checkpoints add their own rules.

Every test/doc change is additive; no pre-existing test was modified.

**Verified state.** Run inside a temporary tree composed from
`distribution/workflow/2.5.1/payload/` overlaid with
`migration/overlays/2.6.0/payload/` (tests resolve sibling files relative to
their own directory, so a bare `PYTHONPATH` split fails on
`prepare-ai-review.sh`):

- `python3 -m unittest workflow_fingerprint_test workflow_fingerprint_generalization_test`:
  305 tests, OK.
- `workflow_state_test`'s new class plus `TestImplementingEntryReachableSecondItem`,
  the `ReviewMaterialLifecycle*`, `GoverningVersionEnumerationSweepTest` and
  `ApplyingReviewFeedbackVersionClaimSweepTest` classes (the new
  `WORKFLOW_V2_PLAN.md` section is swept by them): 51 tests, OK.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP2 — Working-tree-anchored `AMENDMENT_DIFF.patch`

Implements the plan's section 5.5, the `D-Plan-Amendment-5` revision
(`v2.4.0-003`; requirement `REQ-8`). Delivered in `migration/overlays/2.6.0/`:

- `payload/scripts/prepare-ai-review.sh` (first overlay replacement): the
  `AMENDMENT_DIFF.patch` block drops `..HEAD` and writes
  `git diff --no-renames <amendment_base_commit> -- <pathspec>`, anchored at
  the working tree. The pathspec is the sorted union of the
  `plan_stage.protected_paths` declared at `amendment_base_commit` (empty
  when the declaration is absent there), the ones declared now, and
  `<id>-artifacts.json` itself. A leading `#` preamble names
  `work_item_id`, `amendment_id`, `amendment_base_commit`, `plan_revision`
  and `review_content_id`. The block moved to just after `--write-manifest`
  (still after the pin, before the archive), so the preamble carries the
  manifest's own `review_content_id`. Nothing else in the script changed;
  the archive line item 341 guards is untouched.
  **`--no-renames` is an implementation finding, not in the plan text:**
  section 5.5 says Git's rename detection is not relied on, but `git diff`
  applies it by default (`diff.renames`), and the rename test failed
  without the flag — the patch showed `rename from/to`, not
  `deleted file` + `new file`.
- `payload/scripts/workflow_fingerprint_generalization_test.py`: new
  `TestPrepareAiReviewShAmendmentDiffWorkingTreeAnchor` (13 tests), driving
  the real script in scratch repositories. It covers every case CP2 names:
  - an uncommitted plan edit is present, with a `..HEAD` control arm that
    is empty;
  - an untracked new protected file appears as `new file`, and is
    untracked again afterwards (no lingering intent-to-add);
  - a dropped-and-deleted path appears as `deleted file`;
  - a rename appears as `deleted file` + `new file` and passes
    `git apply --check`;
  - a dropped-but-kept path appears as its content diff when changed, and
    only in the declaration hunk when unchanged;
  - with the declaration absent at the base, the patch equals the
    current-only form;
  - non-protected edits are absent;
  - the archive member is byte-identical to the on-disk patch;
  - `bundle_id` is identical with and without the patch (on disk and in
    the archive's `current/`);
  - the file is removed after resolution;
  - the preamble fields equal the manifest's and the state's;
  - `git apply --check` accepts the patch at `amendment_base_commit`.
- `payload/.claude/commands/request-plan-amendment.md` step 4,
  `payload/docs/ai-workflow/REVIEW_PROTOCOL.md` "Bundle structure", and
  `payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md` `D-Plan-Amendment-5` (new
  "Working-tree anchor" paragraph): restated to the working-tree anchor.
  The command keeps the mention-only generator wording that
  `workflow_integration_test.py`'s census pins.
- `classification.json`: three new `replaced` rules (`prepare-ai-review.sh`,
  the generalization test, `request-plan-amendment.md`); the existing
  `REVIEW_PROTOCOL.md`/`WORKFLOW_V2_PLAN.md` rules' rationales now cover
  CP2's delta too.

Every test change is additive; no pre-existing test was modified.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay (committed there as one scratch commit):

- `python3 -m unittest workflow_fingerprint_generalization_test`: 92 tests, OK
  (the new class alone: 13, OK).
- `python3 -m unittest workflow_integration_test`: 260 tests, 3 errors.
  Every error is in `TestRetiredScopedRemediationLeavesNoLiveSurface`, which
  reads the repository-level `docs/ACTIVE_MILESTONE.md`. The payload tree
  has none. The pure `2.5.1` payload has the identical failure set.
- `python3 -m unittest workflow_state_test` (its doc sweeps read the edited
  `WORKFLOW_V2_PLAN.md`): 854 tests, 2 errors. Both are
  `TestCanonicalStateSerialization` live-state tests with no live
  `WORKFLOW_STATE.json` in the payload tree. The pure `2.5.1` payload has the
  identical 2 errors.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP3 — Per-work-item feedback layout

Implements the plan's section 5.1, `D-Feedback-Layout` (requirements
`REQ-1`, `REQ-2`). Delivered in `migration/overlays/2.6.0/`.

**Pre-edit evidence (section 6.2's downgrade paragraph depends on it).**
Run against `distribution/workflow/2.5.1/payload/scripts/` before any edit:
`2.5.1`'s `validate_state` has **no** work-item key allowlist —
`_validate_work_item` checks `work_item_id`, type, kind, phase, checkpoint
statuses, the review-stage ledgers, the block pins and the approval
records only. A state whose every entry carries `feedback_layout:
"scoped"`, and one carrying `feedback_layout: "bogus"`, both validate
cleanly: the key is **ignored, not rejected**. The committed-field sets
(`ORDINARY_`/`RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS`,
`TECHNICAL_APPROVAL_COMMIT_FIELDS`) are *field-diff* allowlists; a key
written once at creation and never changed never appears in a later
commit's field diff, so none of them sees it either. Consequence for
CP7's downgrade paragraph: a downgraded repository does not fail — it
silently resolves scoped items' feedback by the legacy rule.

- `payload/scripts/workflow_fingerprint.py`:
  - `resolve_feedback_layout` (`scoped` / `legacy-scoped` / `legacy-flat`)
    reads the item's entry from the worktree's `WORKFLOW_STATE.json`;
    `resolve_feedback_dir` (signature unchanged) is built on it. A
    `"scoped"` item resolves `.ai-review/<id>/feedback` with no existence
    gate. An entry without the field, no entry, or no state file keeps the
    unchanged rule. A symlinked, non-JSON or non-object state file refuses
    (`FeedbackLayoutUndecidableError`), as does any other field value,
    `null` and non-strings included (`UnknownFeedbackLayoutError`).
  - `ensure_feedback_dir` creates the resolved directory;
    `mark_functional_review_consumed` now calls it.
  - `resolve_feedback_path_contract` and the
    `--resolve-feedback-path <id>` CLI (one JSON object, same function).
  - `assert_feedback_not_owned_by_other_work_item(..., state=None)`: with
    `state`, a foreign owner at a terminal phase is non-blocking for a
    legacy writer only; a non-terminal or state-absent owner, or any
    foreign file under a scoped writer, still refuses.
    `FEEDBACK_OWNER_TERMINAL_PHASES` is pinned equal to
    `workflow_state.TERMINAL_PHASES` (the module cannot import
    `workflow_state`).
  - `assert_manual_feedback_names_work_item` /
    `ManualFeedbackForeignWorkItemError`.
- `payload/scripts/workflow_state.py` (first overlay replacement): the
  stamp in `route_work_item`'s fresh-id branch and
  `create_remediation_child_work_item`; `_validate_work_item` refuses an
  unknown value. Nothing else changed.
- Tests: new `TestFeedbackLayout` (16) in `workflow_fingerprint_test.py`
  and `TestFeedbackLayoutStamp` (6) in `workflow_state_test.py`, covering
  every CP3 test bullet. An unhashable layout value (`["scoped"]`) first
  surfaced a raw `TypeError` from the membership test; both checks now
  type-check first (INV-3). Re-pointed pins, none deleted:
  `TestBundleLayoutResolver`, `TestFunctionalReviewConsumedMarker` and
  `TestReviewImplementationWritebackCrossWorkItemIsolation` now state their
  legacy scope (their fixtures have no state file); the acceptance-matrix
  `feedback_dir()` helper asserts the scoped layout and creates the
  directory through `ensure_feedback_dir`.
- Normative docs: `REVIEW_PROTOCOL.md` gains the "Feedback directory"
  subsection (the one normative definition, including the CLI contract for
  Controller); `MILESTONE_WORKFLOW.md`'s eight hard-coded flat paths become
  `<feedback_dir>` plus one definition; notes in
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, `PLAN_REVIEW_WORKFLOW.md` and
  `IMPLEMENTATION_REVIEW_WORKFLOW.md`; a new `WORKFLOW_V2_PLAN.md` section
  `D-Feedback-Layout`.
- Commands: `apply-functional-review`, `apply-implementation-review`,
  `apply-plan-review`, `approve-review`, `milestone-plan`,
  `prepare-functional-review`, `record-manual-plan-review`,
  `record-manual-implementation-review`, `review-functional`,
  `review-implementation` and `review-plan` now define `<feedback_dir>` by
  `feedback_layout` and print the exact resolved path wherever the operator
  must paste or find feedback. The three review writers pass `state=` to
  the ownership guard and call `ensure_feedback_dir` before writing;
  `/prepare-functional-review` calls it before reporting; both
  `/record-manual-*-review` commands run
  `assert_manual_feedback_names_work_item` before any state write.
- `classification.json`: new `replaced` rules for every newly overlaid
  file; the existing rules' rationales now cover CP3's delta too.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay (committed there as one scratch commit):

- `python3 -m unittest workflow_fingerprint_test workflow_fingerprint_generalization_test workflow_acceptance_matrix_test`:
  480 tests, OK (18 skipped).
- `python3 -m unittest workflow_state_test`: 860 tests, 2 errors — the same
  two `TestCanonicalStateSerialization` live-state errors as CP2 (no live
  `WORKFLOW_STATE.json` in the payload tree).
- `python3 -m unittest workflow_integration_test`: 260 tests, 3 errors — the
  same three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors as CP2.
- `workflow_state_demo_test`, `workflow_fingerprint_demo_test`,
  `workflow_test_harness_test`, `workflow_state_completion_obligations_test`:
  187 tests, 13 failures + 27 errors, a failure set identical, test for
  test, to the pure `2.5.1` payload's (these read real repository history).
- `workflow_fingerprint.py --resolve-feedback-path` smoke run: one JSON
  object, `legacy-flat` with no state file.
- Every overlay payload file is matched by a `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP4 — Bundle-bound plan-review publication

Implements the plan's section 5.3, `D-Plan-Review-Bundle-Binding` (revises
`D-Plan-Revision-Publication`; requirement `REQ-4`). Delivered in
`migration/overlays/2.6.0/`. `"1"`-governed behavior is unchanged
throughout.

**Mechanical enumeration (section 5.3 item 1), recorded before the edits:**

- *`workflow_state.py` predicates reading a plan-stage phase:*
  - `validate_local_plan_review_preconditions` (`== AWAITING_LOCAL_PLAN_REVIEW`)
    and `validate_manual_plan_review_preconditions`
    (`== AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`) are unaffected: only
    stronger, because the bind is now the sole writer of the first.
  - `record_local_plan_review`/`record_manual_plan_review` gain the
    `CONSUMED` write on `REVISE`.
  - `request_plan_amendment` (`_AMENDMENT_REQUEST_ALLOWED_PHASES`) gains
    the `CONSUMED` write.
  - `apply_plan_approval` has no phase precondition; `/approve-review plan`
    step 2's reader now gates it.
  - `BUNDLE_GENERATION_LEGAL_SOURCE_PHASES`/`CHECKPOINT_START_LEGAL_PHASES`
    contain no plan-stage phase: unaffected.
  - No predicate treated `AMENDING_PLAN` as "not yet under review"; the
    generator has no phase check (the bind decides).
- *Commands reading the post-publication phase:* `/review-plan`,
  `/record-manual-plan-review`, `/approve-review plan` step 2 (now the
  readers), `/milestone-plan` and `/apply-plan-review` (new entry),
  `/apply-functional-review` (remediation child), `/request-plan-amendment`
  (next step). `/milestone-implement` checks `IMPLEMENTING` only:
  unaffected.
- *Writers attempted at a ready phase and their decided behavior:*
  - `route_work_item` and `publish_plan_revision` refuse with
    `PlanReviewInProgressError`.
  - The generator is a wrapper-only regeneration that binds nothing.
  - `bind_plan_review_bundle` is idempotent at local review and refuses
    with `PlanReviewAlreadyReadyError` elsewhere.
  - `withdraw_plan_review` is the exit.
- *`route_work_item` resume callers:* only `/milestone-plan` step 1, reached
  at `PLANNING`/`REVISING_PLAN`/`AMENDING_PLAN` after the entry's
  withdrawal. The remediation child's re-declaration runs at `PLANNING`.
- *Protected edits before the publish, per command:*
  - `/milestone-plan`: steps 3-5 edit, and the publish sits at the new
    step-5 publication point.
  - `/apply-plan-review`: steps 3-5 edit, and the publish is in step 5
    after the regeneration, re-embed and staging. Its later steps write
    only `plan-inputs/`.
- *Exits between publish and bind:* only the generator-failure exits (each
  reporting the explicit-id re-run, row 9) and a bind refusal (same
  report). `apply-plan-review.md` step 6 is `"1"`-only, and 7'.2's second
  generation is removed.

**Delivered:**

- `payload/scripts/workflow_state.py`:
  - The publication split:
    - mirror-only `publish_plan_revision` with a required
      `review_content_id` and the `PUBLISHED` record;
    - the plan-stage allow-list on it and on `route_work_item`'s resume
      branch.
  - The `plan_review_binding` record (`CONSUMED`/`PUBLISHED`/`BOUND`) and
    its `validate_state` INV-3 check.
  - `CONSUMED` writes in both `REVISE` writers and
    `request_plan_amendment`, plus `ensure_plan_review_binding_marker`
    (the INV-7 legacy marker).
  - `bind_plan_review_bundle` and `withdraw_plan_review`.
  - `verify_plan_review_bundle`, with the cause-named
    `PlanReviewBundleUnverifiedError`/`ReviewedContentDriftError`.
  - `plan_review_publication_status` (the total table) and its read-only
    `--plan-review-publication-status` CLI.
  - The readers `assert_plan_review_bundle_bound`/
    `validate_local_plan_review_preconditions_bound`.
  - `assert_plan_review_entry_phase`, `assert_plan_review_withdrawal_allowed`
    and `assert_apply_plan_review_feedback`.
  - 15 named errors.
  - `transition_to_awaiting_local_plan_review` is retired: it always
    raises `PlanReviewWriterRetiredError`.
- `payload/scripts/workflow_fingerprint.py` and `prepare-ai-review.sh`:
  - Plan-stage-only staging generation: the plan stage builds in
    `current.staging-<token>/current/` with `.pin.staging-<token>/`, and
    the archive and `AMENDMENT_DIFF.patch` are staged too.
  - Author inputs come from `plan-inputs/`
    (`resolve_plan_review_inputs_dir`, `seed_plan_review_inputs`).
  - `finalize_staged_plan_bundle_generation`:
    - on success it promotes everything and clears `REJECTED`;
    - on failure it discards the staging area, with no withdrawal and no
      marker.
    - This is the deliberate `WFR-67` revision.
  - Implementation/post-fix keep the in-place path; its checks were
    factored unchanged into `_closing_bundle_generation_check`.
  - **Implementation detail, not in the plan text:** the staging area
    holds its bundle in a `current/` child so that item 341's archive
    guard (the positional argument is the bare literal `current`) holds
    unchanged.
- Commands and normative docs:
  - `milestone-plan`: the entry (row 1, withdrawal, marker, status), step 3
    without its publish, the step-5 publication point, and step 6's bind.
  - `apply-plan-review`: the entry, step 1's `REVISE`-only rule, step 5's
    publish on every round, step 6 as `"1"`-only, and step 7' as
    verify-plus-bind.
  - `review-plan`, `record-manual-plan-review`, `approve-review` (step 2),
    `apply-functional-review` and `request-plan-amendment`.
  - `REVIEW_PROTOCOL.md` (`<plan_inputs_dir>`, staging, the `WFR-67`
    revision stated as deliberate), `WORKFLOW_V2_PLAN.md` (revised
    `D-Plan-Revision-Publication`, new `D-Plan-Review-Bundle-Binding`),
    `MILESTONE_WORKFLOW.md`, `PLAN_REVIEW_WORKFLOW.md` and the operator
    reference.
  - `/milestone-plan`'s publication point is a `[2.1]` bullet closing
    step 5 rather than a new numbered step, because a golden test
    hash-pins steps 1-5 with the `[2.1]` bullets stripped.
- Tests:
  - New unit classes in `workflow_state_test.py` (37 tests).
  - `TestPrepareAiReviewShPlanStageStaging` in
    `workflow_fingerprint_generalization_test.py` (8).
  - 13 real-repository scenario classes in
    `workflow_acceptance_matrix_test.py` (85), covering every CP4 test
    bullet.
- **Pre-existing tests re-pointed, none deleted:**
  - Publish phase-flip pins, the retired transition, `route_work_item`
    resume fixtures (moved to a plan-stage phase), and both phase-writer
    censuses.
  - The acceptance driver now follows 2.6.0's command order: stage,
    publish the fresh id, `plan-inputs/`, generate, verify and bind.
    Every plan document gains checkpoint anchors.
  - Rows B13, B14 and F4 re-planned mid-implementation through 2.5.1's
    in-place re-publish, which 2.6.0 deliberately refuses. They now go
    through `/request-plan-amendment`. B14 reaches the B8 wedge via an
    amendment from `SELF_REVIEWING_IMPLEMENTATION`, since no plan
    re-entry exists from `AWAITING_FUNCTIONAL_REVIEW`.
  - The six restated command files' golden hashes are re-recorded.
- **Recorded edge, for review:** at a ready phase, deleting the plan
  document, registry or mapping refuses at the readers and the status
  function with the named `InvalidPlanStageMetadataPathError`, not row 4a.
  The plan's own section 5.3 item 6 limits `F = ⊥` to
  `AbsentProtectedPathError`/`PlanRevisionMismatchError`, "any other
  failure refuses (INV-3)". The withdrawal exit still works (pinned by
  `test_deleted_metadata_path_is_a_named_refusal_and_withdrawal_still_exits`).
- `classification.json`: CP4 rationales on every touched rule. The test
  rules state that pre-existing tests were re-pointed.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay:

- `workflow_fingerprint_test` + `workflow_fingerprint_generalization_test`:
  342 tests, OK.
- `workflow_acceptance_matrix_test`: 231 tests, OK (18 skipped).
- `workflow_state_test`: 897 tests, 2 errors. These are the same two
  `TestCanonicalStateSerialization` live-state errors as CP2/CP3.
- `workflow_integration_test`: 260 tests, 3 errors. These are the same
  three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors.
- Demo/harness/obligations suites: 40 failing, identical test for test to
  the pure `2.5.1` payload.
- Every overlay payload file is matched by a `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP5 — Plan-approval commit closure and committed-truth verification

Implements the plan's section 5.4, `D-Plan-Approval-Closure` (items 1-6;
item 7 declined as planned). Delivered in `migration/overlays/2.6.0/`.

**Delivered:**

- `payload/scripts/workflow_fingerprint.py`:
  - `resolve_plan_stage_approval_commit_paths` returns every declared
    `plan_stage.protected_paths` entry (plan, registry and mapping first),
    `WORKFLOW_STATE.json`, the unchanged conditional artifacts-declaration
    member, and the removals: protected under `HEAD`'s committed
    declaration, tracked at `HEAD`, and absent from both the current
    declaration and the worktree. A first approval has none.
  - `PlanApprovalCommitPlan` gains `protected_paths` and `removal_paths`,
    both defaulted, so hand-built plans still construct.
  - `read_plan_stage_manifest_base_commit` and
    `read_plan_stage_manifest_protected_paths`.
  - `compute_review_content_id_plan_stage_at_commit` is documented as
    accepting any tree-ish. No code change was needed: every Git read it
    makes already accepts a bare tree.
- `payload/scripts/workflow_state.py`:
  - `resolve_fresh_plan_approval_members` (step 4a, read-only). It runs:
    - the empty-index precondition, whose refusal now names the
      staged-`git mv` remedy;
    - the member set;
    - per-member freshness against the bound bundle. A protected member
      is compared with its `files/` capture, otherwise with its blob at
      the bundle's `MANIFEST.md` `base_commit`, otherwise it refuses. A
      removal member must be neither captured nor declared.
    - Every failure is `ReviewedContentDriftError`. A stale
      declaration's `StaleArtifactsDeclarationError` is chained under it.
  - `assert_plan_approval_member_set_unchanged`: step 5's re-resolution
    inside the guarded window.
  - `prove_plan_approval_index_closure` (step 6.3a): `git write-tree`,
    then the identity at that tree. Every removal must be absent.
  - `verify_plan_approval_commit`: the one post-commit verification. It
    derives the work item from the committed state and runs the two-sided
    path-set check (`assert_committed_plan_approval_closure` for the
    closure side).
  - `classify_post_commit_verification_failure`: the amend gate.
  - `verify_post_approval_manifest_match` gains
    `MissingApprovalRecordError` at both stages and an optional explicit
    `expected_review_content_id`.
  - `stage_plan_approval_commit_paths` stages an absent member as a
    deletion.
  - The journal gains an optional `removal_paths`. A `2.5.1` journal
    reads as `[]`.
  - 5 named errors.
- `approve-review.md`: steps 4a, 4c, 5, the new 6.3a, 6a/6a1, 6b's range
  and 6d, plus the implementation-stage verifier bullet.
  `milestone-plan.md`: the member-set sentence in step 3.
  `WORKFLOW_V2_PLAN.md`: new `D-Plan-Approval-Closure` section.
- Tests:
  - `Item.approve_plan` in the acceptance matrix is now a
    **command-shaped driver**. It follows the command's real data flow
    through steps 2-6d: the bound-bundle check, the fresh member set, the
    in-window re-resolution, the proof, `verify_plan_approval_commit`, the
    amend gate and the rollback. A resumable `complete_plan_approval`
    covers the rest. There is no hand-built post-state. All 231
    pre-existing rows pass through it unchanged.
  - 4 new scenario classes (31 tests) cover every CP5 test bullet. The
    amend-gate rows use real one-shot `pre-commit` hooks.
  - `TestPlanApprovalClosureUnits` (11 unit tests).
- **Pre-existing tests re-pointed, none deleted:** three integration tests
  pinned `2.5.1`'s fixed four/five-member set on a fixture whose
  declaration protects two further documents. The `approve-review.md` and
  `milestone-plan.md` golden hashes are re-recorded.
- **Implementation details, not in the plan text, for review:**
  - **An extra path is not amended.** An extra path in the approval
    commit (`CommittedPathSetMismatchError`) classifies
    `RECORD_OR_INPUT`: stop, no amend. The amend re-stages members and
    cannot remove a path, so an amend there could never succeed. This
    matches the frozen bootstrap design's "recovery corrects content,
    never membership". The closure side's content failures get their own
    `CommittedProtectedContentMismatchError`, which classifies
    `TREE_CONTENT`.
  - **Revision errors stop.** A hook that corrupts the plan document's
    `(Revision N)` title makes the committed-tree recompute raise a
    revision error. That classifies `RECORD_OR_INPUT` (stop), the
    conservative reading of INV-5.
  - **Step 6d's closing check is narrowed** to a clean index and clean
    members. A de-protected path left in the worktree legitimately
    survives the approval.
  - **6a1 re-stages the journal's members,** never a fresh resolution,
    because `HEAD` is by then the approval commit.
  - **The CP6 precondition is not built yet.** 6a1's
    `assert_amendment_resolution_held` precondition is named in the
    command as CP6's addition.

**Verified state.** Run in a temporary Git repository composed from the
`2.5.1` payload plus this overlay:

- `workflow_acceptance_matrix_test`: 262 tests, OK (18 skipped). That is
  the 231 pre-existing rows, now driven through the command-shaped
  driver, plus the 31 new ones.
- `workflow_state_test`: 908 tests, 2 errors. These are the same two
  `TestCanonicalStateSerialization` live-state errors as CP2-CP4.
- `workflow_integration_test`: 260 tests, 3 errors. These are the same
  three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors.
- `workflow_fingerprint_test` + `workflow_fingerprint_generalization_test`:
  342 tests, OK.
- Demo/harness/obligations suites: 40 failing, identical test for test to
  the pure `2.5.1` payload.
- Every overlay payload file is matched by a `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP6 — Repository-global lifecycle lock and amendment witness

Implements the plan's section 5.6, `D-Repo-Global-Lifecycle` (closes
`v2.4.0-002`; INV-6, INV-10). Delivered in `migration/overlays/2.6.0/`.

**Pre-edit evidence (section 6.2's downgrade paragraph depends on it).** Run
against `distribution/workflow/2.5.1/payload/scripts/` before any edit:
`2.5.1`'s `validate_state` has no `amendment_history` entry-key check, so a
state whose resolved entry carries `resolved_review_content_id` (a hex
string, or even an integer) validates cleanly. The key is **ignored, not
rejected**, the same finding CP3 recorded for `feedback_layout`.

**Delivered:**

- `payload/scripts/workflow_state.py`:
  - **Primitive (9)**, `lifecycle_lock`: a per-work-item `flock` at
    `<git-common-dir>/ai-workflow/checkpoint-claims/<token>.lifecycle.lock`,
    never unlinked. It is a pure source. A process-local held-set
    (`_held_primitives`), which every existing `flock` and lease now
    registers in, must be empty when it is taken
    (`LifecycleLockOrderError`).
  - **The amendment witness**, `<token>.amendment.json`
    (`OPEN`/`RESOLVING`/`RESOLVED`/`NONE`), written by tempfile plus
    `os.replace`. A torn, symlinked or unknown-shaped witness refuses
    (`AmendmentWitnessUnavailableError`).
  - `amendment_request_projection_sha256` and
    `amendment_resolution_projection_sha256`.
  - The lag probe, with `workflow_release_version_key` ordering versions
    numerically and treating an unorderable version as lagging.
  - The upgrade bootstrap (the request and resolution fork checks, the
    legacy trailer comparison, and no `NONE` sentinel while a worktree
    lags), the two orphan tests with their evidence-bound clear literals,
    and the predicate list (`_evaluate_lifecycle`).
  - `claim_checkpoint` runs (9) → (2) → witness check → phase check →
    publish. `adopt_claim` and an absent-claim `take_over_claim` take (9)
    before (6)/(5); the takeover's guarded window moved, unchanged, into
    `_take_over_claim_window`.
  - `request_plan_amendment` refuses without (9)
    (`LifecycleLockNotHeldError`). `request_plan_amendment_transaction` is
    the one entry point, and it publishes the `OPEN` witness before the
    state.
  - The resolution side: `reserve_amendment_resolution` (4d),
    `assert_amendment_resolution_held` (6a1), `advance_amendment_witness`
    (6c1), `release_amendment_resolution` (after 6b), and
    `stage_plan_approval_members` with `first_commit`/`amend_recovery`
    modes.
  - `apply_plan_approval` records `resolved_review_content_id`.
    `open_plan_approval_journal` refuses an amendment-resolving transaction
    while a claim is live.
  - 11 named errors under `LifecycleRefusalError`.
- `payload/docs/ai-workflow/dry-run/verify_372h_*.py`: primitive 9, the five
  (9) edges as code-derivable, the stated totals (16 edges, 9/7) replacing
  the hard-coded 11 and 6/5, the re-anchored `(6)→(8)` mutation, and a new
  regression that removes both `(9)→(8)` evidence paths.
- Commands:
  - `approve-review.md`: the entry table under 4b, the new 4d, step 5's
    `first_commit` staging, 6a1's held check and `amend_recovery` staging,
    6b's token capture and release, and the new 6c1 advance before 6d.
  - `request-plan-amendment.md`: steps 1-2 (the closed race, the new entry
    point, every refusal and its remedy).
  - `milestone-implement.md` (new to the overlay): step 1d's lifecycle
    refusals and remedies, and step 1c's routing to them.
- `WORKFLOW_V2_PLAN.md`: the edge table, the primitive list, the totals,
  the blocking list, the acyclicity argument, the `(2)→(8)` paragraph,
  `D-Plan-Amendment-1`'s bullet (now repository-wide), and a new
  `D-Repo-Global-Lifecycle` section.
- Tests, with every CP6 test bullet 1-29 covered:
  - `workflow_state_test.py` (51 new tests):
    - `TestCrossWorktreeAmendmentClaimResidualXModelR9B1` is inverted
      into `TestCrossWorktreeAmendmentClaimRaceIsClosed` (tests 1-4,
      including real-process races in both orders);
    - `TestAmendmentClaimRaceRealProcesses` keeps the same-worktree races
      (test 16);
    - new classes for tests 5-13i and 19-28 at the unit level, with real
      linked worktrees, `SIGKILL`ed workers and real plan-approval
      journals.
  - `workflow_acceptance_matrix_test.py`: the command-shaped driver gains
    4d, the staging modes, 6a1's held check, 6b's capture-then-release and
    the 6c1 advance, with hook seams. The new
    `RepoGlobalLifecycleAcrossWorktrees` (18 rows) drives
    `/approve-review plan` in worker processes that pause or `SIGKILL` at a
    named step (tests 8, 17, 18, 22, 23, 25, 26, 27, 28).
  - `workflow_integration_test.py`: `TestApproveReviewLifecycleEntryTable`
    (test 29).
- **Pre-existing tests changed, none deleted:**
  - four tests that acquired a lease to stand in for a live holder now
    release it at the end, because the held-set correctly carried it into
    every later test in the process;
  - `TestRequestPlanAmendment` calls the pure mutator holding (9);
  - the golden hashes of `approve-review.md` and `milestone-implement.md`
    are re-recorded.
- **Deviation from the plan text, for review.** The census finds
  **sixteen** edges, not the fifteen section 5.6 states, with a **9/7**
  split, not 8/7. The extra edge is `(9)→(3)`: an absent-claim
  `take_over_claim` must hold (9) across its publication, and that
  publication's guarded (5) window already establishes this worktree's
  identity (the existing `(5)→(3)` edge). Avoiding the edge would mean
  writing the identity before the takeover's re-verification, which
  breaks its "refuse, having mutated nothing" contract. The edge is
  blocking but acyclic: the blocking sources `{1, 5, 8, 9}` and targets
  `{2, 3, 6}` stay disjoint. The script, the plan table and
  `WORKFLOW_V2_PLAN.md` all state 16 and 9/7.
- **Implementation details, not in the plan text, for review:**
  - The witness is always written with every field; a field a status does
    not use is `null`.
  - A bootstrap-written `OPEN` at seq S has a `previous` derived from the
    requester's entry S-1 (a `RESOLVED` witness), or `NONE` when S is 1,
    so a rollback never returns to "absent".
  - A rollback always writes `previous`, even a `NONE` the bootstrap
    left unwritten because a worktree lagged (bootstrap step 6: "never to
    absent"). The lagging checks run on every acquisition anyway.
  - An unreadable state file in any worktree makes the `OPEN` orphan test
    undecidable, so the literal is offered and can clear the witness.
  - The `amend_recovery` evidence is the proof object
    `assert_amendment_resolution_held` returns, passed to the staging
    entry. The held check takes (9), and the staging runs inside a guarded
    window, where (9) cannot be taken.
  - An owner's `advance_amendment_witness` with a journal raises
    `AmendmentResolutionHeldError` if the witness does not end `RESOLVED`
    with the pinned digest, and 6c1 then stops without closing the journal.
  - `milestone-implement.md` step 1d now states that `claim_checkpoint`
    returns the claim record (the token is its `owner_token` field). This
    session tripped on the old wording while claiming CP6: it recovered
    through the documented `CONTINUE_CLAIM` path, and the claim, the state
    write and the token are correct.

**Independent review of the implementation against section 5.6**
(a read-only review agent, before commit). Four defects were confirmed:
- **Fixed:** an unreadable state file made the `OPEN` orphan test refuse
  with no literal, and the literal itself could not clear it;
- **Fixed:** the impossible reservation case raised
  `AmendmentResolutionConflictError`, whose remedy is wrong; it is now
  `AmendmentWitnessUnavailableError` (INV-3);
- **Fixed:** a rollback could delete the witness;
- **Not fixed, a plan-level gap -- needs a decision in review:** an
  amendment written by a lagging `2.5.1` worktree becomes invisible once
  that worktree merges the `2.6.0` update. That merge is the remedy
  `LaggingWorktreeAmendmentError` names, but once the worktree stops
  lagging, section 5.6 reads no other worktree's state under a `NONE` or
  `RESOLVED` witness, and CP6 test 13d asserts exactly that. So a claim or
  an amendment request from another worktree is then admitted while that
  amendment is open. Closing this needs the plan to choose between
  (a) always scanning other worktrees' states (dropping test 13d's cost
  property), (b) re-bootstrapping (adopting the amendment as `OPEN`) when
  a worktree first stops lagging, or (c) narrowing the remedy to "finish or
  discard it before merging the update". The implementation follows the
  plan's text. The only change: that worktree's own request and
  reservation now refuse naming the unrecorded amendment, instead of the
  wrong "merge the resolved amendment first" (regression test
  `test_an_updated_worktree_names_its_own_unrecorded_amendment`).

The reviewer also noted, without calling it a defect: with no witness,
the lag checks run before the bootstrap, as test 13g requires. So a lagging
worktree's stale unresolved entry blocks every lifecycle operation for the
item until it updates, whereas the same state under an existing witness
passes. The outcome depends on order, and the plan could settle it
explicitly.

**Verified state.** Run in a temporary Git repository composed from the
`2.5.1` payload plus this overlay:

- `workflow_state_test`: 959 tests, 2 errors (1 skipped: the pin against
  the real `release._version_key` runs only where `workflow_manager` is
  importable; run separately with `PYTHONPATH=src`, it passes). The 2
  errors are the same two `TestCanonicalStateSerialization` live-state
  errors as CP2-CP5.
- `workflow_acceptance_matrix_test`: 280 tests, OK (18 skipped). That is
  the 262 CP5 rows, all through the extended driver, plus the 18 new ones.
- `workflow_integration_test`: 267 tests, 3 errors. These are the same
  three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors.
- `workflow_fingerprint_test` + `workflow_fingerprint_generalization_test`:
  342 tests, OK.
- Demo/harness/obligations suites: 40 failing, identical test for test to
  the pure `2.5.1` payload.
- Both `verify_372h_*.py` scripts pass standalone: 9 primitives, 12
  code-derivable plus 4 orchestrated edges, 9/7, acyclic, and every
  regression including the new `(9)→(8)` one.
- Every overlay payload file (29) is matched by exactly one
  `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP7 — Compose the `2.6.0` release

Implements the plan's CP7 and section 6.2 (requirement `REQ-10`).

- `migration/overlays/2.6.0/classification.json` was already complete: each
  of the 29 overlay payload files is matched by exactly one rule, so
  nothing changed there.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0`
  composed `distribution/workflow/2.6.0/`: 63 artifacts (39
  `distribution`, 22 `conformance`, 2 `host-evidence`), 6 templates, 29
  `overlay_replaced`, 0 `overlay_added`, `overlay_commit` `736e170`
  (CP6). The `--check` run reproduces it byte for byte.
- `tests/support.py` `CI_SUITES["2.6.0"]`, counted from the composed
  payload's own suites. Five suites differ from `2.5.1`: fingerprint 242,
  state 959, integration 267, acceptance matrix 280 and generalization
  100. Harness (19) and obligations (106) are unchanged.
  Total 1973, or 292 more than `2.5.1`'s 1681. The same loader count
  reproduces the pinned `2.5.1` values.
- `migration/portability_exceptions.json` gets the empty
  `by_version["2.6.0"]`. No genuine exception arose.
- Per-release classes: `TestConformanceFixture260` and
  `TestBootstrappedTarget260` (`tests/test_conformance_suite.py`),
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite260`
  (`tests/test_bootstrap_e2e.py`), and
  `TestReadmeStatusTableMatchesCiSuites.test_2_6_0_row_matches_ci_suites`
  (`tests/test_internal_references.py`). Because five suites move, its "new
  cases" is the whole-release delta against `2.5.1`, not `2.5.1`'s
  two-suite sum.
- `README.md`: `2.6.0` Status row and rebuild commands. `docs/MIGRATION.md`:
  new "Workflow v2.6.0 — an authored release" record with its own downgrade
  posture. `CLAUDE.md`: the authored-release list, plus the `2.6.0`
  downgrade paragraph. That paragraph cites CP3's and CP6's mechanical
  finding (ignored, not rejected, so the failure is silent), lists section
  6.2's five conditions, and states the mixed-release posture.
- `docs/defects/v2.4.0-001`, `-002` and `-003` each get a status-line
  update and a "`2.6.0` disposition" section citing their tests. `-001`:
  closed, plus the out-of-scope process-item update hazard (section 3.2).
  `-002`: closed, qualified, with section 5.6's residual quoted verbatim.
  `-003`: closed (repair form 1).
- **CP6 test portability defect, found by this checkpoint's full run and
  fixed in the overlay.** Eight git calls in CP6's `workflow_state_test.py`
  tests (`TestRepoGlobalLifecycleClaimAndAmendment`,
  `TestAmendmentWitnessCrashRecovery`, `TestAmendmentWitnessUpgradeBootstrap`,
  `TestAmendmentBootstrapResolutionFork`) named the branch `main` literally.
  `ScratchRepo`'s `git init -q` names it from `init.defaultBranch`, and the
  conformance harness isolates git config (`GIT_CONFIG_GLOBAL=/dev/null`,
  `tests/support.py`), so it was `master` there. The result was 7 errors
  against both the fixture and the bootstrapped target. CP6's narrow checks
  had passed only under a global config that sets `main`. A new
  `_primary_branch(root)` helper (`git symbolic-ref --short HEAD`) replaces
  every literal. The test count is unchanged (959), no assertion changed,
  the shared base `ScratchRepo` fixture is untouched, and
  `distribution/workflow/2.6.0/` was rebuilt from the overlay. It is not a
  portability exception: the test was wrong, so `by_version["2.6.0"]`
  stays empty.

**Verified state.**

- `python3 tests/run_all.py` (full, non-`--fast`), after the CP6
  test-portability fix above: 11/11 files OK, including
  `test_conformance_suite.py` (1360.8s: `TestConformanceFixture260` and
  `TestBootstrappedTarget260` green, 1973 tests) and
  `test_bootstrap_e2e.py` (665.4s:
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite260`'s failure set
  equals the empty `by_version["2.6.0"]`). The README row's values
  (1973, +292, 1973 of 1973) come from this run. The run before the fix
  failed exactly as described above: 3 conformance failures and 1
  bootstrap-e2e failure, all caused by the branch-name literal.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check`:
  reproduces `distribution/workflow/2.6.0/` byte for byte.
- `python3 tools/migrate.py --check`: OK.
- INV-9: `git diff b2060bf -- distribution/workflow/2.5.1/` is empty.

### CP8 — Disposable-repository and linked-worktree acceptance

Implements the plan's CP8 (requirements `REQ-1` to `REQ-9` and `REQ-11`
end to end). New `tests/test_workflow_2_6_0_hardening_disposable_repo.py`,
registered in `tests/run_all.py`'s slow tier next to the `2.5.0`
disposable suite.

**How it drives the installed release.** Every test installs real
releases with `workflow_manager.install.bootstrap`/`update`. Every step
then runs in a subprocess whose `sys.path` starts with that checkout's own
installed `scripts/`, so a `2.5.1`→`2.6.0` update mid-test really switches
bytes, and a lagging linked worktree really runs `2.5.1`. The
command-shaped drivers are the installed release's own acceptance-matrix
harness (`Scratch`/`Item`, part of the `full` profile), pointed at the
installed repository. The module adds only:

- `Item` re-pointed at a chosen work-item id, so several items coexist;
- review feedback written the way `/review-plan` writes it, through the
  release's own guard and resolver;
- the command steps the harness does not wrap: `/record-manual-plan-review`
  steps 4-7, `/review-plan`'s `REVISE`, `/apply-plan-review`'s entry;
- for `2.5.1` checkouts, their own amendment request and resolution, which
  the `2.5.1` harness predates.

`src/workflow_manager/fixture.py`, `tools/` and `pyproject.toml` are
unchanged.

**One class per scenario** (18 tests):

1. Two concurrent fresh items write local plan-review feedback at
   `.ai-review/<id>/feedback/`, never the flat directory.
   `--resolve-feedback-path` prints exactly `resolve_feedback_path_contract`.
2. A `2.5.1` item runs to `MILESTONE_COMPLETE`, leaving flat feedback.
   After the update, a new item's local review lands at its scoped path,
   and A's file is byte-identical.
3. A `2.5.1` item waits at `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` with an
   unconsumed flat `REVISE`, and the update is committed.
   `/record-manual-plan-review` and `/apply-plan-review` both resolve the
   flat file. The item goes to `REVISING_PLAN` with a `CONSUMED` record,
   then back to `AWAITING_LOCAL_PLAN_REVIEW`, bound at revision 2.
4. `2.3.1` and `2.4.0` product items run without a local exclude, and the
   update is committed. `implementing_entry_reachable` holds, the plan
   digest equals the recorded approval, and the implementation digest
   equals its pre-update value. A novel committed path still raises
   `UnclassifiedPathError`. The control arm runs the base release's own
   bytes against the same history:
   - `2.3.1` wedges at both stages;
   - `2.4.0` wedges only at the implementation stage, because its
     generator already excluded `.workflow-manager/` at the plan stage.
5. Both section 3.3 variants, stale `TEST_RESULTS.md` and stale
   `REVIEW_REQUEST.md`, after the publish:
   - the item stays at `REVISING_PLAN`, row 9 (`PUBLISHED_UNBOUND`);
   - `current/` is byte-identical, with no `REJECTED` and no staging
     leftovers;
   - the reader refuses;
   - the re-run binds at revision 2, a single bump.
6. A brand-new, untracked protected companion:
   - the approval commit contains it;
   - the identity recomputed from that commit equals the approved one;
   - exactly one approval commit exists;
   - the worktree is clean.
   This holds in session, and after a crash right after the commit, when a
   new process takes the transaction over and completes it.
7. Three tests:
   - *Fresh `2.6.0`, two worktrees.* Claim first, and the amendment refuses
     with `AmendmentCheckpointActiveError`, naming the claimant. Amendment
     first, and the claim refuses with `AmendmentInFlightError` while the
     claimant's own state says `IMPLEMENTING`, with nothing published. Once
     the amendment resolves, the unmerged worktree gets
     `StaleLifecycleStateError` ("merge the resolved amendment first") and
     is admitted after the merge.
   - *Mixed release.* A lagging worktree alone refuses nothing, and no
     `NONE` sentinel is written. Its `2.5.1` amendment request makes an
     updated claim refuse with `LaggingWorktreeAmendmentError` (evidence:
     worktree, branch, `2.5.1`, seq 1), still with no sentinel.
   - *Resolution.* `main` and `b` carry the same open amendment and approve
     different amended plans:
     - `main` dies right after 4d, so `b` refuses with
       `AmendmentResolutionReservedError`;
     - `main`'s takeover rolls back and releases, then `main` re-approves;
     - the witness is `RESOLVED` with `main`'s committed resolution digest;
     - `b` then refuses with `StaleLifecycleStateError`;
     - exactly two approval commits exist (round 1 plus one resolution).

     A lagging worktree carrying the same open seq resolves it unreserved
     with its `2.5.1` scripts and a different plan. The next `2.6.0` claim
     refuses with `AmendmentResolutionConflictError` (recorded = the
     winner's digest), and the witness stays unchanged.
8. During an open amendment, `AMENDMENT_DIFF.patch` is non-empty and shows
   the uncommitted amended plan. The archive member is byte-identical.
9. Four `2.5.1` items are caught by the update. Their committed state blob
   is unchanged by the update commit.
   - `IMPLEMENTING` completes `CP2`.
   - `AWAITING_LOCAL_PLAN_REVIEW` passes the bound-bundle reader with
     nothing back-filled, then records the local `APPROVE`.
   - `AMENDING_PLAN` has no witness before the first (9) holder. Its
     entry marker is the non-legacy `CONSUMED` record from the superseded
     approval. It resolves through `/approve-review plan`, and the witness
     ends `RESOLVED` at seq 1.
   - `REVISING_PLAN` mid-apply works as follows:
     - a publish before the entry refuses with
       `LegacyPlanReviewBindingUnknownError`;
     - the entry writes the legacy marker at revision 1;
     - a same-revision publish then refuses with
       `ConsumedPlanReviewContentError` and writes no state;
     - one advance binds at revision 2.

Plus `TestClosedDefectCensus`:

- the named `v2.3.1-001`/`-002`/`-003` tests (section 3.8) exist in the
  composed payload;
- they pass in an installed `2.6.0` repository: 44 tests, one skip, the
  host-note test, which skips by design without RepFlow's note;
- `by_version["2.6.0"]` is empty, `TestBootstrappedTarget260` exists, and
  `test_amendment_update_path.py` is still in the fast tier;
- `v2.3.1-003` is re-proved end to end: a first approval with no state file
  at `HEAD`, through `verify_plan_approval_commit`, commits the state as
  `100644`.

**Payload defects found: none.** No scenario exposed a payload defect, so
the overlay, `distribution/workflow/2.6.0/` and the CI counts are
untouched.

**Two expectations were corrected against the plan text.** Both times the
engine was right and the first draft of the test was wrong:

- **Scenario 9.** Section 6.1 names `LegacyPlanReviewBindingUnknownError`
  for the refusal *before* the marker exists. After the marker, the
  same-revision refusal is `ConsumedPlanReviewContentError`. The test now
  pins both.
- **Scenario 7.** A resolver that dies *after* its approval commit does not
  leave `AmendmentResolutionReservedError` for the other worktree: the
  committed resolution is visible, so predicate step 1 self-heals the
  witness to `RESOLVED`, and the other side gets `StaleLifecycleStateError`
  (CP6 test 8). So the test crashes the resolver after 4d instead.

**Observation, not fixed:** `fixture.drive_synthetic_work_item_through_checkpoints`
cannot drive a `2.6.0` target. Its publish passes no `review_content_id`,
which `2.6.0` requires for a two-stage item (`TypeError`). No test asks it
to; it is used only against `2.3.1`/`2.4.0`.

**Verified state.**

- `python3 tests/test_workflow_2_6_0_hardening_disposable_repo.py`:
  18 tests, OK (about 28s).
- `python3 tests/run_all.py --fast`: all green.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check`:
  reproduces `distribution/workflow/2.6.0/` byte for byte.
- INV-9: `git diff b2060bf -- distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/`
  is empty.
- The new test file and `tests/run_all.py` classify as
  implementation-stage protected (`tests/`) under this item's declaration.

### CP9 — Full regression, release parity and closed-defect regression verification

Implements the plan's CP9 (requirements `REQ-9` and `REQ-10`). This
checkpoint is verification-only and writes no artifact. No disagreement was
found, so no owning checkpoint needed a fix.

**Verified state** (all run in this checkpoint, from `HEAD` `813ac82`):

- `python3 tests/run_all.py --fast`: all 8 fast suites OK.
- `python3 tests/run_all.py` (full): all 12 suites OK, exit 0.
  `test_conformance_suite.py` took 1336.6s, `test_bootstrap_e2e.py` 666.9s,
  `test_implementation_review_two_stage_disposable_repo.py` 11.4s and
  `test_workflow_2_6_0_hardening_disposable_repo.py` 28.0s.
- Clean-target failure set: `TestBootstrappedTarget260` and
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite260` passed. Both
  assert that the failure set equals `by_version["2.6.0"]` exactly, and
  that set is empty. `TestConformanceFixture260` passed its per-suite count
  equality against `CI_SUITES["2.6.0"]`.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check`:
  `distribution/workflow/2.6.0/` matches a fresh build from base `2.5.1`
  plus the overlay.
- `python3 tools/migrate.py --check`: `distribution/workflow/2.3.1/` matches
  a fresh extraction of the frozen upstream release.
- INV-9: `git diff b2060bf -- distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/`
  is empty (0 lines).
- README's `2.6.0` row reads "7/7 suites, 1973 tests ... 1973 of 1973".
  That agrees with `CI_SUITES["2.6.0"]`
  (242 + 959 + 19 + 267 + 280 + 106 + 100 = 1973 across 7 suites) and with
  the empty `by_version["2.6.0"]`. The conformance run above asserts both.
- `v2.3.1-001/-002/-003` (`REQ-9`): still regression-protected by CP8's
  census tests, which passed in the full run.

**Process note.** The first `--fast` run overlapped the full run, which was
regenerating `distribution/`, so `test_disposable_repo_fixtures.py` briefly
saw no `2.3.1/manifest.json`. That was a harness collision, not a defect.
Run on its own afterwards, `--fast` passed, and the full run's own fast
tier passed too.

The unrelated working-tree changes to `.gitignore`,
`.workflow-manager/installation.json` and `docs/ROADMAP.md` were there
before this checkpoint. They were left untouched and not committed.

## Implementation review round 1 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `9b929aeb…93c6`, `review_content_id`
`b70c675f…b308`, `implementation_revision` 1. It had no Blocking findings
and five Important ones. Each was reproduced before any change, with a new
test that fails on the reviewed code. All five are fixed in the `2.6.0`
overlay, and the release was rebuilt.

- **Important 4 (CP2): non-UTF-8 protected content.** Fixed.
  `AMENDMENT_DIFF.patch` is now captured and written as bytes.
- **Important 5 (CP2): git-config sensitivity.** Fixed. Every option that
  shapes the patch is pinned on the command line: `--literal-pathspecs`,
  `--no-ext-diff`, `--no-textconv`, `--no-color`, `a/` `b/` prefixes,
  `--no-renames` and `--binary`. The new test regenerates under a hostile
  `GIT_CONFIG_GLOBAL` (`noprefix`, `mnemonicPrefix`, `renames = copies`,
  an external diff and `color = always`). The patch must be
  byte-identical and still pass `git apply --check`.
- **Important 1 (CP4): re-bound content reaching plan approval.**
  **Partially resolved.** The user dispositioned this on 2026-09-25.
  - Closed: the stale-approval shortcut. `apply_plan_approval` refuses a
    `TWO_STAGE_PLAN_REVIEW_VERSIONS` item at any phase other than
    `AWAITING_PLAN_APPROVAL` (`PlanApprovalPhaseError`, `799b80d`), and
    `approve-review.md` step 0 says so.
  - Still open: withdraw → detour → restore can re-bind the same
    `review_content_id` for a *fresh* review, and both stages must then
    approve it again. Section 5.3's "never re-binds" wording, and the
    recovery-table row that mirrors it, remain stronger than the
    implementation.
  - Why it stays open: enforcing that wording needs a design/schema change,
    such as a consumed-content history. Plan revision 8 pins `consumed` as a
    single slot. The change cannot be introduced while this item is at
    `APPLYING_REVIEW_FEEDBACK`, because `/request-plan-amendment` accepts
    only `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION`. The user directed
    that no consumed-history schema be invented in this round.
  - Mandatory follow-up: recorded as
    `docs/defects/v2.6.0-001-withdrawn-plan-content-can-rebind-after-a-detour.md`,
    which names both acceptable resolutions (enforce, or narrow normatively)
    and the regression test either one must satisfy.
- **Important 2 (CP6): unreadable committed state wedging the witness.**
  Fixed. An unreadable committed `WORKFLOW_STATE.json` in another worktree
  now makes the test undecidable. The refusal carries the evidence-bound
  literal, and the literal clears it. This covers every read that
  previously raised: `RESOLVING` step 1 (resolver `HEAD`, resolver branch
  tip), step 2a (`_resolution_visible_anywhere`, which now also returns
  the unreadable reasons), `clear_amendment_resolution`'s scan, and the
  `OPEN` orphan test's branch-tip and requester reads.
- **Important 3 (CP6): upgrade-topology wedge.** Fixed. While the witness
  is absent, a lagging worktree's unresolved entry counts as recorded if
  the bootstrap would record the same entry (same seq, request projection
  and `amendment_base_commit`) from a `2.6.0` worktree: any non-lagging
  one, or the evaluating one. Both reported topologies are tests now.
  An entry held only by lagging worktrees still refuses (plan test 13g,
  unchanged). A lagging worktree whose working tree already carries the
  update is told to commit it, not to merge it.

Optional findings:

- **Applied:**
  - 1: the archive includes `AMENDMENT_DIFF.patch` at the plan stage only.
  - 3: `--literal-pathspecs`.
  - 4: the gitignored-new-protected-file gap is documented in
    `prepare-ai-review.sh`.
  - 5: `--no-renames` on the empty-index and post-staging checks.
  - 7: the witness publish fsyncs its directory.
  - 8: `request_plan_amendment_transaction` rolls the `OPEN` witness back
    when the state publish raises. It does not roll back if the state
    already holds the entry or cannot be read.
  - 10: `apply-plan-review.md` step 5 notes the forced revision advance
    for a legacy-marked item.
  - 11: the overlay classification says 12 named errors.
  - 12: `docs/MIGRATION.md` now says `2.4.0` is recorded.
- **Not applied, with reasons:**
  - 2: a failure-injection test for `PlanStagePromotionError`, and the
    skipped `clear_rejected_marker_if_present` on a late cleanup failure.
    This needs a promotion-crash harness. The skipped marker clear fails
    safe: the next generation clears it.
  - 6: re-checking 6a1's re-staged members against
    `review_content_manifest`. The post-amend verification already
    refuses a drifted member. The cost is one wasted amend attempt, not a
    wrong commit.
  - 9: a `git stash` of committed-but-unapproved `AMENDING_PLAN` state.
    This is a residual to document through the amendment above, alongside
    section 5.6's other residuals.
  - 13: CP8 concurrency depth. REQ-7's concurrency evidence stays with
    CP6's real-process race tests, as the reviewer notes.

The counts move from 1973 to 1989 (+16): `workflow_state_test.py` from 959
to 972, and `workflow_fingerprint_generalization_test.py` from 100 to 103.
`tests/support.py` and `README.md` are updated to match.

## Implementation review round 2 (`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `2629fcaf…6f4e`, `review_content_id`
`11b4eac4…64bf`, `implementation_revision` 2.
`LOCAL_MODEL_IMPLEMENTATION_REVIEW` round 2 had approved the same content.
The reviewer accepted Important 1's partial disposition and found Important
2-5 resolved. There were no Blocking findings and one new Important one.

- **I1 (CP5): approval staging and closure were not literal- or
  byte-safe.** Fixed. Reproduced first against the reviewed code:
  - An absent `*.md` removal member made `git rm --cached -- '*.md'` unstage
    every tracked Markdown file, which is worse than the review described.
  - A present `*.md` member staged a worktree-edited `a.md`.
  - A non-ASCII member came back C-quoted from `--name-only`.

  Every case refused (`UnexpectedStagedPathSetError`,
  `CommittedPathSetMismatchError`).

  Now:
  - `stage_plan_approval_commit_paths` runs `git add`/`git rm --cached`
    under `--literal-pathspecs`.
  - The empty-index, post-staging and post-commit path-set checks read
    `-z` output through `_git_path_set`, which decodes with `os.fsdecode`.
  - The new `assert_staged_path_set_within` backs `/approve-review` step
    6.3, so the operator never compares quoted output by eye.
  - `_snapshot_commit` and the tracked-metadata checks use
    `--literal-pathspecs`, so a leading-`:` member is not read as pathspec
    magic.

  The same defect sat at two more boundaries a declared path crosses, and
  both are fixed too:
  - `prepare-ai-review.sh`'s untracked-file `git add -N` and its exit-trap
    `git reset`. The reset could also unstage unrelated staged files that
    matched a glob-named untracked file.
  - `/milestone-plan` step 3's intent-to-add instruction.

  `approve-review.md` steps 4a, 6.3 and 6d follow. New
  `PlanApprovalClosureLiteralPaths` (5 rows) drives the real
  `Item.approve_plan` with these members:
  - an ASCII control;
  - `docs/ai-workflow/*.md`;
  - `[DW]ECOY.md` and `:WI_MAGIC.md`;
  - `désign.md`;
  - an absent `*.md` removal member.

  Each row asserts the exact committed member set, and that a tracked,
  worktree-edited decoy the glob would match stays unstaged and
  uncommitted.
- **O1 applied.** `AMENDMENT_DIFF.patch` pins `-U3`, and its `git diff`
  runs with `GIT_DIFF_OPTS` removed. A mid-file edit under
  `diff.context=0` plus `GIT_DIFF_OPTS=--unified=0` stays byte-identical
  and `git apply --check`-clean. The new test fails without the fix.
- **O2 applied.** The current-only-form oracle pins the implementation's
  own diff options.
- **O4 applied.** The `v2.6.0-001` defect record now lists
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md` among the documents to reconcile.
- **O3 not applied.** Aligning `_bootstrap_derivable_entries` with the
  RESOLVED-witness asymmetric topology changes CP6's derivation rule, not a
  boundary. The current refusal fails closed and the documented remedy
  (merge the update into the lagging worktree) works. The reviewer rated
  it a later cleanup.
- **O5 not applied.** Each remaining bare `LifecycleStateUnreadableError`
  site needs its own remedy text and test. It fails closed today.

The counts move from 1989 to 1995 (+6):
- `workflow_acceptance_matrix_test.py`: 280 → 285.
- `workflow_fingerprint_generalization_test.py`: 103 → 104.

## Implementation review round 3 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `1cba8013…f9f34`, `review_content_id`
`3bb5e04c…dcda`, `implementation_revision` 3. It had no Blocking findings
and one Important finding, the residual of round 2's I1.

- **I1-residual: `load_pre_amendment_snapshot` read a declared path as
  a pathspec.** Fixed. Reproduced first: with both `x` and `:x` tracked,
  `git ls-tree HEAD -- ':x'` returns `x`'s blob, so an amended approval
  with a legal `:`-leading `plan_path` was refused
  (`AmendmentPreSnapshotUnreproducibleError`). For `:(glob)…` and `:!…`
  it was a Git error instead. The cross-check now runs `git
  --literal-pathspecs ls-tree`. There are two new regressions:
  - `AmendedApprovalLiteralMetadataPath` drives a real amended approval
    whose `plan_path` is `:proc-item-plan.md`, with a tracked decoy
    `proc-item-plan.md`.
  - `DeclaredPathGitReads` calls the function directly with `:plan.md`,
    `:(glob)*.md` and `:!plan.md`.

  Both fail with the fix reverted.
- **Re-sweep (acceptance criterion 2).** I checked every `git … --
  <path>` and `<rev>:<path>` call in `workflow_state.py`,
  `workflow_fingerprint.py` and `prepare-ai-review.sh`:
  - The rest of the plain `--` calls pass a fixed constant, not a declared
    path: the state path, the `scripts/` and `.claude/commands/` surface
    prefixes, or `.`.
  - `<rev>:<path>` reads are literal, because the path grammar rejects
    `.`/`..` components and a leading `/`.

  The sweep found one more defect in the same class:
  `verify_staged_blob_sha256` read `:<path>`, and Git parses `:0:x.md` as
  index stage 0 of `x.md`. A fifth member named `0:x.md` was therefore
  checked against the wrong blob. It now reads `:0:<path>`. The new
  `DeclaredPathGitReads` row fails with this fix reverted.
- **O1 applied, with a narrowed premise.**
  `workflow_fingerprint.literal_pathspec_env()` drops
  `GIT_GLOB_PATHSPECS`/`GIT_NOGLOB_PATHSPECS`/`GIT_ICASE_PATHSPECS` for
  every `--literal-pathspecs` call. `prepare-ai-review.sh` unsets them
  once, which also covers the Python it runs.

  The review said 2.5.1 worked under all three modes. That holds only for
  `GIT_NOGLOB_PATHSPECS`. `git ls-tree` rejects glob/icase magic outright
  ("pathspec magic not supported by this command"). 2.5.1's own plain
  `ls-tree -- <path>` reads (the identity-reference scan on
  `route_work_item`, and `_snapshot_commit`) therefore already failed
  under the other two. The lifecycle row pins the real regression
  (`GIT_NOGLOB_PATHSPECS`). A per-call-site row covers all three modes on
  the literal reads, and the generator row covers all three plus
  `GIT_DIFF_OPTS`. Full-lifecycle support for glob/icase modes would
  scrub every Git call. That is a pre-existing limitation outside this
  item.
- **O2 applied.** The dead journal term is removed. A new row commits
  tab, double-quote and backslash members exactly.
- **O3 applied.** The generalization oracle's `_git` scrubs
  `GIT_DIFF_OPTS` and the conflicting pathspec modes. The new row fails
  with the scrub reverted.
- **O4 applied.**
  - `approve-review.md` and `DirtyIndexBeforeStagingError` now recommend
    `git --literal-pathspecs restore --staged`.
  - `milestone-plan.md` step 5.3 and `apply-plan-review.md` now say `git
    --literal-pathspecs add -N`.
  - The empty-index check is credited to
    `assert_plan_approval_index_clean`.

  The matrix harness's own step-3 simulation (`Item.stage_plan_files`)
  was still a bare `git add -N`. It is now literal to match.

The counts move from 1995 to 2002 (+7):
- `workflow_acceptance_matrix_test.py`: 285 → 291.
- `workflow_fingerprint_generalization_test.py`: 104 → 105.

## Implementation review round 4 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `6855d548…a3e`, `review_content_id`
`4472240b…6ab`, `implementation_revision` 4. It had no Blocking findings
and one Important finding. The round-3 fixes were confirmed load-bearing
by mutation.

- **I1: `docs/MIGRATION.md`'s `2.6.0` record was stale and unpinned.**
  Fixed. Reproduced first: the record still quoted round 1's
  `overlay_commit` (`736e170`, "the CP6 commit"), 1973 fixture tests, the
  per-suite deltas `853→959`, `146→280` and `79→100`, and "1973 of 1973".
  The shipped manifest and `CI_SUITES["2.6.0"]` say `a886069`, 2002
  (+321), `853→972`, `146→291`, `79→105` and "2002 of 2002". The two
  existing pin classes hard-code `2.4.0`, so nothing caught this.
  - The record now matches, and the provenance sentence no longer claims
    the CP6 commit.
  - New `TestAuthoredReleaseMigrationRecordMatchesShippedEvidence` in
    `tests/test_internal_references.py`. It is table-driven by release
    and scoped to each release's own `## Workflow v<version>` section. It
    pins the Base release, Provenance JSON, Overlay counts, Manifest
    counts (per category), the fixture total, the "plus N new cases"
    delta, every quoted per-suite `a→b` (and that exactly the moved
    suites are quoted), and the bootstrapped row. It checks them against
    the manifest, `CI_SUITES` and `expected_portability_exceptions`.
    Against the stale text it failed three tests: provenance, fixture and
    bootstrapped.
  - The pin then did its job within this round. Each O1/O2 rebuild moved
    `overlay_commit` (to `cc12398`, then `201c82d`), and the provenance
    test failed until the record was updated in the same commit.
- **O1 applied.** The `git mv` row of `PlanApprovalClosureMembers` now
  runs the remedy exactly as printed: `git --literal-pathspecs restore
  --staged`.
- **O2 applied.** `approve-review.md`'s remedy text says the three
  pathspec-mode variables must be unset, because Git refuses
  `--literal-pathspecs` combined with any of them.
  `TestGoldenCommandFileHashes`' recorded hash for that file is
  re-recorded (`644b1cd6…` → `65d60c81…`), in a separate commit.

The suite counts are unchanged at 2002. `test_internal_references.py`
gains six tests.

## Functional review checklist

Technical approval: commit `7175de8` (implementation revision 5, basis
`EXTERNAL_APPROVE`). You are testing the composed `distribution/workflow/2.6.0/`
release as an operator would use it: installed into a throwaway repository.
Put findings in `.ai-review/feedback/FUNCTIONAL_REVIEW.md`.

**Setup.** From this checkout:

```bash
export M=~/Workspace/workflow-manager PYTHONPATH=~/Workspace/workflow-manager/src
export T=$(mktemp -d)        # every flow below works under $T
```

No feature flags. The only test data is the throwaway repositories and work
items each flow creates.

**All seven flows are required**, in order. Flows 4-6 build on each other:
flow 4 creates work item `<A>`, flow 5 leaves `<A>` in `AMENDING_PLAN`,
and flow 6 uses a second item `<B>`. Replace `<A>`/`<B>` with the ids
`/milestone-plan` reports.

Flows 1-3, flow 4.3's direct-writer refusal and flow 7 were dry-run while
this checklist was prepared. The rest of flows 4-6 state the documented
`2.6.0` contract.

1. **Release is present and reproducible.**
   - `python3 -m workflow_manager --manager-root $M releases` lists `2.6.0
     ... [authored]`.
   - `python3 $M/tools/build_release.py --overlay $M/migration/overlays/2.6.0 --check`
     exits 0.
   - Expected: both succeed; nothing under `$M` changes (`git -C $M status`).
2. **Fresh install.**
   ```bash
   git init -q $T/a && git -C $T/a commit -q --allow-empty -m init
   python3 -m workflow_manager --manager-root $M bootstrap $T/a
   python3 -m workflow_manager --manager-root $M status $T/a
   python3 -m workflow_manager --manager-root $M verify $T/a
   cd $T/a && git add -A && git commit -qm "install 2.6.0"
   python3 scripts/workflow_fingerprint.py --resolve-feedback-path demo-item
   ```
   - Expected: `bootstrapped workflow 2.6.0 (full)`, 62 managed files;
     `status` says `clean`; `verify` says `installation matches workflow
     2.6.0`.
   - Expected: the last command prints one JSON object with `"layout":
     "legacy-flat"` and `.ai-review/feedback/...` paths. There is no state
     entry for `demo-item`, so the legacy rule applies.
3. **Update from `2.5.1`; the installation record no longer wedges
   classification** (`v2.4.0-001`, CP1).
   ```bash
   git init -q $T/b && cd $T/b && git commit -q --allow-empty -m init
   python3 -m workflow_manager --manager-root $M --release-version 2.5.1 bootstrap .
   git add -A && git commit -qm "install 2.5.1"
   python3 -m workflow_manager --manager-root $M update . && git add -A && git commit -qm "update 2.6.0"
   python3 -m workflow_manager --manager-root $M verify .
   python3 -c "import sys; sys.path.insert(0,'scripts'); import workflow_fingerprint as wf
   print(wf.classify_path('.workflow-manager/installation.json', frozenset(), {}, {}))
   print(wf.classify_path_implementation_stage('.workflow-manager/installation.json', {}, {}, {}, {}))
   wf.classify_path('.workflow-manager/other.json', frozenset(), {}, {})"
   ```
   - Expected: `updated . to workflow 2.6.0`; `verify` matches `2.6.0`.
   - Expected: `excluded` twice, then `UnclassifiedPathError` for
     `other.json`. The fallback covers exactly one path, not the directory.
4. **Work item `<A>`: plan review through approval, driven by Claude Code
   in `$T/a`** (CP3, CP4, CP5). Open a Claude Code session in `$T/a`.
   1. **Declare a new protected companion before the bundle exists.** Run
      `/milestone-plan` for a tiny item (for example, "add a `hello.txt`
      file") and note its id `<A>`. Create `docs/<A>-notes.md` with any
      text, and do **not** `git add` it. Before the plan bundle is
      generated, make sure `docs/ai-workflow/registry/<A>-artifacts.json`
      lists `docs/<A>-notes.md` in `plan_stage.protected_paths`. Ask Claude
      to add it while it writes the declaration, or edit the file yourself
      before it generates. If you add it after the bundle is generated, you
      have edited reviewed content, and that needs a new review round.
   2. **Bound, scoped.** Once `/milestone-plan` reports the item at
      `AWAITING_LOCAL_PLAN_REVIEW`:
      - `python3 scripts/workflow_state.py --plan-review-publication-status <A>`
        prints one JSON object whose `status` is exactly `"BOUND"`.
      - `python3 scripts/workflow_fingerprint.py --resolve-feedback-path <A>`
        prints `"layout": "scoped"` and `.ai-review/<A>/feedback/...` paths.
   3. **Required refusal: plan review is in progress.** At that same
      `AWAITING_LOCAL_PLAN_REVIEW` phase, run both checks below. Neither may
      write anything: `git status --porcelain` and the `status` in step 2
      are unchanged afterwards.
      - The in-place writer refuses. This calls the same writer
        `/milestone-plan` and `/apply-plan-review` use to publish a plan
        revision, and discards the result:
        ```bash
        python3 -c "import sys,json; sys.path.insert(0,'scripts'); import workflow_state as ws
        s=json.load(open('docs/ai-workflow/WORKFLOW_STATE.json')); w=s['work_items']['<A>']
        ws.publish_plan_revision(s,'<A>',w['plan_revision']+1,'2026-01-01T00:00:00Z',review_content_id='0'*64)"
        ```
        Expected: `PlanReviewInProgressError`, naming `<A>`, the phase and
        `/milestone-plan <A>` as the withdrawal exit.
      - `/milestone-plan` with **no argument** refuses with
        `PlanReviewWithdrawalNeedsExplicitIdError`, before any write.
      - Do **not** run `/milestone-plan <A>` with the id here. At a ready
        phase, that form is the sanctioned withdrawal, not a refusal. It
        discards both review stages and would force a new round.
   4. **Scoped feedback.** `/review-plan <A>` writes
      `.ai-review/<A>/feedback/REVIEW_FEEDBACK.md`. Nothing new appears
      under `.ai-review/feedback/`.
   5. **Optional `REVISE` round.** If you give a `REVISE`, `/apply-plan-review
      <A>` reaches the next round with a single `plan_revision` bump.
      `.ai-review/<A>/current/` is replaced only when generation succeeds:
      no `.ai-review/<A>/current.staging-*` directory remains, and there is
      no `REJECTED` marker.
   6. **Required refusal: another item's manual feedback.** Once `<A>` is at
      `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, write
      `.ai-review/<A>/feedback/REVIEW_FEEDBACK.md` with
      `Reviewer role: MANUAL_EXTERNAL_PLAN_REVIEW`, `Status: APPROVE` and
      `Work item: some-other-item`, then run `/record-manual-plan-review <A>`.
      Expected: `ManualFeedbackForeignWorkItemError`, naming both
      `some-other-item` and `<A>`. The phase is still
      `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, and
      `docs/ai-workflow/WORKFLOW_STATE.json` is unchanged. Then paste a
      genuine manual verdict naming `<A>` and re-run the command to continue.
      `/record-manual-implementation-review` makes the same check
      (`assert_manual_feedback_names_work_item`); this flow exercises it
      through the plan-stage command only.
   7. **Approval closes over the companion.** `/approve-review plan <A>`
      creates exactly one approval commit.
      - `git show --stat HEAD` lists `docs/<A>-notes.md`, the file that was
        untracked until now.
      - `git ls-tree HEAD docs/<A>-notes.md` shows it in the committed tree.
      - `git status --porcelain` is empty, apart from anything you created
        outside the item's declared paths.
      - `<A>` is now at `IMPLEMENTING`.
5. **Open amendment on `<A>` shows the uncommitted plan** (CP2). Start from
   flow 4's end state: `<A>` at `IMPLEMENTING`. Do not run
   `/milestone-implement`. An amendment is only accepted from
   `IMPLEMENTING` or `SELF_REVIEWING_IMPLEMENTATION`.
   1. Run `/request-plan-amendment <A>`. `<A>` moves to `AMENDING_PLAN`.
   2. Edit `<A>`'s plan document, and do not commit the edit.
   3. Run `/milestone-plan <A>` while `<A>` is in `AMENDING_PLAN`. It
      generates the amended plan bundle.
   4. Expected: `.ai-review/<A>/current/AMENDMENT_DIFF.patch` is non-empty
      and contains your uncommitted edit. Its leading `#` preamble names
      `work_item_id`, `amendment_id`, `amendment_base_commit`,
      `plan_revision` and `review_content_id`.
   5. The patch applies at `amendment_base_commit`. Copy that value from the
      preamble:
      ```bash
      git worktree add --detach $T/check <amendment_base_commit>
      git -C $T/check apply --check $T/a/.ai-review/<A>/current/AMENDMENT_DIFF.patch && echo applies
      git worktree remove $T/check
      ```
   6. Leave `<A>` here, in `AMENDING_PLAN`. Flow 6 does not use it.
6. **Two linked worktrees cannot race an amendment on `<B>`** (CP6,
   `v2.4.0-002`). A second item is needed because flow 5 deliberately left
   `<A>` in `AMENDING_PLAN`, with its amendment already open. A checkpoint
   claim is illegal there, and so is a second amendment request. Keep this
   setup order so that the merge in step 3 really brings `<B>` into the
   linked worktree:
   1. In `$T/a`, on `main`, create the linked worktree **before `<B>`
      exists**: `git worktree add $T/a-wt -b wt`.
   2. Still in `$T/a` on `main`, plan and approve a second tiny item `<B>`
      the way flow 4 does. Steps 4.1 and 4.3-4.6 can be skipped for `<B>`.
      `<B>` must end at `IMPLEMENTING`, with `git status --porcelain`
      clean.
   3. Bring `<B>` into the worktree: `git -C $T/a-wt merge --ff-only main`.
      Confirm that `$T/a-wt` sees `<B>` at `IMPLEMENTING`:
      ```bash
      python3 -c "import json; print(json.load(open('$T/a-wt/docs/ai-workflow/WORKFLOW_STATE.json'))['work_items']['<B>']['phase'])"
      ```
   4. The claim is taken and released with the same functions
      `/milestone-implement` calls at steps 1d and 1f, so no checkpoint has
      to be implemented. Run each of these from `$T/a-wt`. `<CP>` is
      `<B>`'s first checkpoint id, for example `CP1`.
      ```bash
      # CLAIM
      python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import workflow_state as ws
      print(ws.claim_checkpoint(Path.cwd(), '<B>', '<CP>', now='2026-09-26T00:00:00Z')['checkpoint_id'])"
      # RELEASE
      python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import workflow_state as ws
      ws.release_checkpoint(Path.cwd(), '<B>', '<CP>', owner_token=ws.resolve_claim(Path.cwd(), '<B>')['owner_token'], now='2026-09-26T00:00:00Z')"
      # SHOW
      python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import workflow_state as ws
      print(ws.resolve_claim(Path.cwd(), '<B>'))"
      ```
   5. **Order 1, the claim first.**
      - CLAIM in `$T/a-wt` prints `<CP>`.
      - In `$T/a`, `/request-plan-amendment <B>` refuses with
        `AmendmentCheckpointActiveError`, naming `$T/a-wt` as the
        claimant. `<B>` stays at `IMPLEMENTING` in `$T/a`.
      - RELEASE in `$T/a-wt`, then SHOW prints `None`.
   6. **Order 2, the amendment first.**
      - In `$T/a`, `/request-plan-amendment <B>` succeeds, and `<B>` moves
        to `AMENDING_PLAN` in `$T/a`.
      - CLAIM in `$T/a-wt` refuses with `AmendmentInFlightError`, even
        though `$T/a-wt`'s own state still says `IMPLEMENTING` (check it
        with step 3's command).
      - SHOW prints `None`: no claim was published.
7. **Required: the automated disposable-repository suite.** This is part of
   the functional acceptance evidence, not an optional extra. It drives the
   cases a manual pass can't reach safely: in-flight `2.5.1` items at four
   phases being updated, an in-flight flat-feedback item, forced
   plan-bundle generation failures, mixed-release worktrees, and a crash
   followed by a takeover in a new process.
   ```bash
   python3 $M/tests/test_workflow_2_6_0_hardening_disposable_repo.py -v
   ```
   Expected: `Ran 18 tests`, then `OK` (about 30s). Record the final lines
   in your functional-review notes.

**Known limitations and out of scope.**
- Mixed-release worktrees remain unsupported. A `2.5.1` worktree that has
  not merged the update neither takes the lifecycle lock nor reads the
  witness; `2.6.0` only narrows that window. This is the residual quoted
  in `v2.4.0-002`'s `2.6.0` disposition, and the mandatory follow-up
  `v2.6.0-001`.
- Downgrading below `2.6.0` fails silently, not loudly. See `CLAUDE.md`'s
  `2.6.0` downgrade paragraph. Don't treat that as a finding.
- `fixture.drive_synthetic_work_item_through_checkpoints` cannot drive a
  `2.6.0` target (CP8 observation). Nothing uses it that way.
- **Known issue, non-gating:** `scripts/workflow_state.py
  --plan-review-publication-status <unknown-id>` exits 1 with a raw
  `KeyError` traceback, not a named refusal. It was observed while this
  checklist was prepared, and this checklist-only change deliberately
  leaves it unfixed. No required flow passes an unknown id. Record it as a
  finding only if you judge it matters, or if it blocks a required flow.
- This repository's own unrelated working-tree edits (`.gitignore`,
  `.workflow-manager/installation.json`, `docs/ROADMAP.md`) are not part
  of this milestone.

## Current blockers

None. Important 1's residual is dispositioned as a mandatory follow-up
(`v2.6.0-001`), not as a blocker for this round.

## Active plan

`docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`
(revision 8), registry
`docs/ai-workflow/registry/workflow-review-artifact-and-concurrency-hardening-registry.json`.

## Next action

Both implementation-review stages approved revision 5, and the technical
approval is committed (`7175de8`). The item is at
`AWAITING_FUNCTIONAL_REVIEW`. Next is the manual functional review using
the checklist above. Findings go to `.ai-review/feedback/FUNCTIONAL_REVIEW.md`.
