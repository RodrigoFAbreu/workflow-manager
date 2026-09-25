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

**CP7 complete** (7 of 9 checkpoints). Next: CP8 (depends on CP7) —
disposable-repository and linked-worktree acceptance suite, including
update from installed `2.5.1`.

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

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`
(revision 8), registry
`docs/ai-workflow/registry/workflow-review-artifact-and-concurrency-hardening-registry.json`.

## Next action

Invoke `/milestone-implement workflow-review-artifact-and-concurrency-hardening`
to implement CP8.
