# CP12 execution evidence -- `implementation-review-two-stage`, workflow-2.5.0

Disposable-repository functional validation for `governing_workflow_version:
"2.2"` (`D-Implementation-Review-Stages`/`D-Implementation-Review-Version-
Activation`). This file is execution evidence only (`docs/ai-workflow/`:
plan-stage excluded, implementation-stage excluded) -- never a second,
review-bound copy of the checkpoint's own narrative, which lives in
`docs/ACTIVE_MILESTONE.md`.

Test module: `tests/test_implementation_review_two_stage_disposable_repo.py`.

## Full suite run

```
$ cd tests && python3 test_implementation_review_two_stage_disposable_repo.py -v
```

28/28 passed, 0 failed, 0 errors, ~11s. Full `-v` output:

```
test_a_typo_d_rollback_trailer_value_resolves_activated_fail_closed (__main__.TestActivationProcedureOnComposedRelease.test_a_typo_d_rollback_trailer_value_resolves_activated_fail_closed) ... ok
test_build_activated_config_helper_matches_the_documented_edit (__main__.TestActivationProcedureOnComposedRelease.test_build_activated_config_helper_matches_the_documented_edit)
The generalized helper (`D-Implementation-Review-Version- ... ok
test_config_missing_after_activation_is_a_hard_stop (__main__.TestActivationProcedureOnComposedRelease.test_config_missing_after_activation_is_a_hard_stop) ... ok
test_documented_hand_edit_activates_22 (__main__.TestActivationProcedureOnComposedRelease.test_documented_hand_edit_activates_22) ... ok
test_documented_rollback_reverts_to_21_not_to_1 (__main__.TestActivationProcedureOnComposedRelease.test_documented_rollback_reverts_to_21_not_to_1) ... ok
test_fresh_install_is_not_22_enabled (__main__.TestActivationProcedureOnComposedRelease.test_fresh_install_is_not_22_enabled) ... ok
test_a_live_workflow_manager_bookkeeping_write_never_blocks_a_checkpoint (__main__.TestCP9FixesAgainstADisposableRepoScenario.test_a_live_workflow_manager_bookkeeping_write_never_blocks_a_checkpoint) ... ok
test_workflow_manager_installation_record_is_excluded_at_implementation_stage (__main__.TestCP9FixesAgainstADisposableRepoScenario.test_workflow_manager_installation_record_is_excluded_at_implementation_stage) ... ok
test_find_declaration_symmetry_gaps_is_clean_for_the_generated_declarations (__main__.TestDeclarationCoverageHelperAgainstSyntheticItem.test_find_declaration_symmetry_gaps_is_clean_for_the_generated_declarations) ... ok
test_synthetic_item_declarations_are_symmetric_and_self_consistent (__main__.TestDeclarationCoverageHelperAgainstSyntheticItem.test_synthetic_item_declarations_are_symmetric_and_self_consistent) ... ok
test_bounded_fix_reopens_both_implementation_review_stages (__main__.TestFunctionalReviewBoundedFixRoutesThroughBothStagesAgain.test_bounded_fix_reopens_both_implementation_review_stages) ... ok
test_bundle_id_mismatch_at_the_manual_stage_is_advisory_only (__main__.TestNegativeImplementationReviewPaths.test_bundle_id_mismatch_at_the_manual_stage_is_advisory_only)
`check_manual_stage_bundle_id_advisory`: a wrapper-only bundle ... ok
test_duplicate_manual_ingestion_is_refused (__main__.TestNegativeImplementationReviewPaths.test_duplicate_manual_ingestion_is_refused)
`DuplicateManualImplementationStageIngestionError`: a second ... ok
test_local_block_is_a_true_no_op (__main__.TestNegativeImplementationReviewPaths.test_local_block_is_a_true_no_op) ... ok
test_local_review_from_the_wrong_phase_refuses (__main__.TestNegativeImplementationReviewPaths.test_local_review_from_the_wrong_phase_refuses) ... ok
test_local_revise_loops_back_through_applying_review_feedback (__main__.TestNegativeImplementationReviewPaths.test_local_revise_loops_back_through_applying_review_feedback) ... ok
test_manual_block_is_a_true_no_op (__main__.TestNegativeImplementationReviewPaths.test_manual_block_is_a_true_no_op) ... ok
test_manual_review_before_local_approve_refuses_wrong_phase (__main__.TestNegativeImplementationReviewPaths.test_manual_review_before_local_approve_refuses_wrong_phase) ... ok
test_manual_revise_loops_back_through_applying_review_feedback (__main__.TestNegativeImplementationReviewPaths.test_manual_revise_loops_back_through_applying_review_feedback) ... ok
test_stale_review_content_id_hard_blocks_manual_ingestion (__main__.TestNegativeImplementationReviewPaths.test_stale_review_content_id_hard_blocks_manual_ingestion)
A bundle regeneration between the local approval and the manual ... ok
test_two_stage_ledger_refuses_for_a_21_item (__main__.TestNegativeImplementationReviewPaths.test_two_stage_ledger_refuses_for_a_21_item)
`WrongGoverningVersionForImplementationReviewStageError`: the ... ok
test_local_approve_manual_approve_technical_approval (__main__.TestPositiveTwoStagePath.test_local_approve_manual_approve_technical_approval) ... ok
test_recovery_from_awaiting_local_implementation_review (__main__.TestRecoverImplementationProvenanceFromEachPhase.test_recovery_from_awaiting_local_implementation_review) ... ok
test_recovery_from_awaiting_manual_external_implementation_review (__main__.TestRecoverImplementationProvenanceFromEachPhase.test_recovery_from_awaiting_manual_external_implementation_review) ... ok
test_recovery_from_the_terminal_awaiting_external_implementation_review (__main__.TestRecoverImplementationProvenanceFromEachPhase.test_recovery_from_the_terminal_awaiting_external_implementation_review) ... ok
test_recovery_is_not_applicable_when_content_genuinely_changed (__main__.TestRecoverImplementationProvenanceFromEachPhase.test_recovery_is_not_applicable_when_content_genuinely_changed) ... ok
test_22_becomes_available_only_after_the_repository_explicitly_activates_it (__main__.TestUpdatePathLeavesLiveV21ItemUnaffected.test_22_becomes_available_only_after_the_repository_explicitly_activates_it) ... ok
test_update_to_250_does_not_touch_the_live_21_item (__main__.TestUpdatePathLeavesLiveV21ItemUnaffected.test_update_to_250_does_not_touch_the_live_21_item) ... ok

----------------------------------------------------------------------
Ran 28 tests in 11.294s

OK
```

## Coverage map (against the registry's own CP12 scope)

- **Activation, no repository-internal shortcut** (`LOCAL_MODEL_PLAN_REVIEW`
  round 10, optional finding 1): `TestActivationProcedureOnComposedRelease`
  bootstraps a disposable repo directly via `workflow_manager.install.
  bootstrap` against the real, composed `distribution/workflow/2.5.0/`
  release, proves a fresh install stays `"2.1"`-default, and performs
  `docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md`'s documented
  `WORKFLOW_CONFIG.json` hand edit (both fields, one commit,
  `Workflow-Activation: 2.2` trailer) verbatim -- never a call through
  `build_activated_config` (checked separately, on its own terms). Also
  covers the post-activation `ConfigMissingAfterActivationError` hard stop,
  a fail-closed unresolvable `Workflow-Rollback` trailer value, and a
  documented rollback to `"2.1"` (never bare `"1"`).
- **Update-path compatibility**: `TestUpdatePathLeavesLiveV21ItemUnaffected`
  bootstraps on `2.4.0`, writes a live `"2.1"` item mid-
  `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` through the *installed* module,
  updates to `2.5.0`, and proves both the state and the config are
  byte-identical afterward, and that the pre-existing item is never
  retroactively upgraded even after the repository separately activates
  `"2.2"` for future items.
- **Plan-stage two-stage traversal + `/milestone-implement` to
  `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`**: `MatrixCase22.reach_plan_
  approved`/`reach_awaiting_local_implementation_review`, driven by every
  test below, run the real `AWAITING_LOCAL_PLAN_REVIEW` ->
  `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` -> `AWAITING_PLAN_APPROVAL` ->
  `approve_plan()` sequence, then the real checkpoint loop
  (`implementing_entry_reachable` -> `select_next_checkpoint` ->
  `resolve_checkpoint_ownership` -> the guarded `IN_PROGRESS`/completion
  writes) through `enter_self_reviewing_implementation` and
  `record_bundle_generation(stage="implementation")`, asserting the
  **committed** phase at the durability commit `T` (read back via `git
  show T:docs/ai-workflow/WORKFLOW_STATE.json`, not merely the working-tree
  entry) is `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`.
- **Positive path**: `TestPositiveTwoStagePath` -- local `APPROVE` -> manual
  `APPROVE` -> `/approve-review implementation`.
- **Negative paths**: `TestNegativeImplementationReviewPaths` -- local
  `REVISE` looping back through `APPLYING_REVIEW_FEEDBACK`; local `BLOCK`
  (true no-op); manual `REVISE` loop (back to the *local* stage, never
  re-entering manual review directly); manual `BLOCK` (true no-op);
  wrong-phase refusals both directions; `"2.1"` item refusal
  (`WrongGoverningVersionForImplementationReviewStageError`); stale
  `review_content_id` hard block; duplicate manual ingestion; advisory-only
  `bundle_id` mismatch (`check_manual_stage_bundle_id_advisory`, and the
  state writer's own verbatim-recording behavior).
- **`/recover-implementation-provenance` from each of the three phases**:
  `TestRecoverImplementationProvenanceFromEachPhase` --
  `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
  `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, and the terminal
  `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`, plus the not-applicable case
  when content genuinely changed.
- **`"2.2"` functional-review bounded-fix scenario** (resolves I2):
  `TestFunctionalReviewBoundedFixRoutesThroughBothStagesAgain` -- post-fix
  regeneration from `AWAITING_FUNCTIONAL_REVIEW` lands at
  `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`, never straight back to the
  terminal phase, and `/approve-review implementation` is refused
  (`WrongPhaseForImplementationReviewStageError`) until a fresh
  local-then-manual pass completes.
- **CP7's generic declaration-coverage helper, exercised directly**:
  `TestDeclarationCoverageHelperAgainstSyntheticItem` calls
  `workflow_state_test.assert_declaration_coverage`/`find_declaration_
  symmetry_gaps` (imported from the composed release) against this file's
  own synthetic `"2.2"` work item -- no second hand-written copy.
- **CP9's four backlog fixes, against fresh disposable-repo scenarios**:
  the mode-100644 fallback, the portable host-note skip, and the required
  empty `2.5.0` portability-exceptions entry are already exercised against
  a real bootstrapped-on-2.5.0 disposable repository by
  `tests/test_bootstrap_e2e.py`'s own
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite250` (it runs the
  *complete* frozen suite there and asserts zero undocumented failures --
  re-run below). The fourth (the widened implementation-stage
  `.workflow-manager/` exclusion) is additionally proven here, at the
  disposable-repo level, by `TestCP9FixesAgainstADisposableRepoScenario`: a
  live checkpoint commit succeeds with `.workflow-manager/installation.json`
  bookkeeping sitting concurrently in the same repository.

## A defect this validation found and fixed

Driving the real local-approve-then-manual-approve-then-`/approve-review
implementation` sequence (never exercised end to end before this
checkpoint -- CP3/CP4's own hermetic tests each construct a hand-built
dict-state fixture that starts *after* the ledger write, never one that
carries it through to the following commit) surfaced a genuine defect:
`TECHNICAL_APPROVAL_COMMIT_FIELDS` had not been widened the way its sibling
`ORDINARY_BUNDLE_GENERATION_RECORD_FIELDS`/`RECOVERED_BUNDLE_GENERATION_
RECORD_FIELDS` already were, to admit a `"2.2"` item's uncommitted
`implementation_review_stages` ledger residue (neither `/review-
implementation`'s local-approve write nor `/record-manual-implementation-
review`'s manual-approve write creates its own durability commit -- both
ride into whatever commit comes next, which for a `"2.2"` item's *ordinary,
first-round positive path* is always `/approve-review implementation`'s own
technical-approval commit). Before the fix, every `"2.2"` item's very first
technical-approval commit failed `MalformedTechnicalApprovalCommitError`
outright -- the mainline path, not an edge case.

Fixed in `migration/overlays/2.5.0/payload/scripts/workflow_state.py`
(`TECHNICAL_APPROVAL_COMMIT_FIELDS` widened with `implementation_review_
stages`, mirroring the generation-record sets' own identical widening and
reasoning) and `workflow_state_test.py`
(`TestTechnicalApprovalCommitAdmitsImplementationReviewStagesResidue`, two
tests). `distribution/workflow/2.5.0/` was rebuilt
(`python3 tools/build_release.py --overlay migration/overlays/2.5.0`) and
reproduces byte-for-byte from the base release plus the overlay
(`--check`). This is authored, unreleased `2.5.0` content, not frozen
Workflow semantics -- squarely this milestone's own fix to make, mirroring
CP9's/CP11's own precedent of a later checkpoint correcting an earlier
checkpoint's gap discovered by its own required validation sweep, within
the same protected `migration/` tree.

## Narrowest relevant checks run for the fix itself

```
$ PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts python3 -m unittest \
  workflow_state_test.TestValidateTechnicalApprovalCommit \
  workflow_state_test.TestTechnicalApprovalCommitAdmitsImplementationReviewStagesResidue -v
```
5/5 passed.

```
$ python3 tools/build_release.py --overlay migration/overlays/2.5.0
$ python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check
```
Build succeeds; `--check` confirms byte-for-byte reproduction.

```
$ cd distribution/workflow/2.5.0/payload/scripts && python3 workflow_state_test.py
```
Pre-fix (confirmed via `git stash`): 819 tests, 2 errors. Post-fix: 821
tests (exactly the two new tests above), 2 errors -- the identical,
pre-existing `TestCanonicalStateSerialization` dry-run-path-relative errors
this exact invocation shape (run outside a real repository root) is already
known to produce, unaffected by this checkpoint's own change.

`tests/support.py`'s `CI_SUITES["2.5.0"]["workflow_state_test.py"]` updated
819 -> 821 to match.
