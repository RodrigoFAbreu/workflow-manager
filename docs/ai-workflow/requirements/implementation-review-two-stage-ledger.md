# `implementation-review-two-stage` Requirements Ledger

Mutable, human-readable execution record for the `implementation-review-
two-stage` work item. Physically separate from the immutable, machine-
readable `implementation-review-two-stage-mapping.json` in this same
directory (D4b): the mapping file is the approved requirement↔checkpoint
binding and is plan-stage protected (editing it changes
`review_content_id`); this ledger is never a fingerprint input — it
resolves under `docs/ai-workflow/requirements/` in both this item's
plan-stage `excluded_prefixes` and its implementation-stage
`excluded_prefixes`. Editing this file never stales a plan approval or a
technical approval and never requires a fresh review round.

Each checkpoint appends one section here as it completes: implementation
evidence, verification results, review findings, and (where applicable)
functional-verification outcome. This is a log, not a status source —
`WORKFLOW_STATE.json`'s `checkpoints[id]` remains the sole record of
checkpoint status (D-Registry); nothing here is re-derived from or
overrides it.

**Ledger initialization (WF4b)**: this file did not exist before `CP2` —
`CP1` did not create it. Initialized here, per `D3`'s "a living document
WF4b initializes and implementation sessions append to," with a brief
retroactive `CP1` summary (from that checkpoint's own commit message and
diff, not re-derived implementation detail) so this ledger's own record
stays continuous from the work item's first checkpoint.

## `CP1` — Design decisions (retroactive summary)

- **Implementation evidence** (from commit `20a808d1`, `feat
  (implementation-review-two-stage): CP1 -- author
  D-Implementation-Review-Stages and D-Implementation-Review-Version-
  Activation`): authored `D-Implementation-Review-Stages` and
  `D-Implementation-Review-Version-Activation` into
  `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
  (a full-file copy of the `2.4.0` base plus this item's own design
  additions); added the consolidated "where the two-stage mirror
  genuinely diverges" disposition as a new, explicitly `HISTORICAL`-
  marked `2.5.0 disposition record` subsection; fixed the review-
  material-lifecycle marker's canonical `render_marker`/`parse_marker`
  representation in the overlay's own `scripts/workflow_state.py`;
  updated `MILESTONE_WORKFLOW.md`, `PLAN_REVIEW_WORKFLOW.md`, and
  `REVIEW_PROTOCOL.md` in the same overlay; added a new
  `IMPLEMENTATION_REVIEW_WORKFLOW.md` operator guide.
- **Verification**: this checkpoint's own commit records its verification
  separately (not reproduced here since this summary is retroactive); see
  `docs/ACTIVE_MILESTONE.md`'s history and the commit itself for detail.

## `CP2` — `workflow_state.py` plumbing in the overlay

- **Implementation evidence** (all in
  `migration/overlays/2.5.0/payload/scripts/workflow_state.py` unless
  noted):
  - **`KNOWN_PHASES` additions (D-Implementation-Review-Stages)**: added
    `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` and
    `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, both real and
    persisted — declared ahead of their own writers, which `CP3` adds
    (`bundle_generation_target_phase`'s version-dependent resolver);
    `TestPersistedPhaseWriterCensus`'s `DECLARED_BUT_UNWRITTEN` set is
    updated to include both, with the test renamed accordingly, until
    `CP3` moves them into `EXPECTED_WRITERS`.
  - **Generalized `WF-Activate` helpers (D-Implementation-Review-Version-
    Activation)**: `build_activated_config`/`build_rolled_back_config`
    gained a `target_version` parameter (default `"2.1"`, preserving the
    original call shape byte-for-byte), reused rather than duplicated for
    the `"2.1"` → `"2.2"` bump. Activation now appends `target_version` to
    `supported_versions` when absent (new behavior). The new
    `ACTIVATION_ROLLBACK_PREDECESSOR = {"2.1": "1", "2.2": "2.1"}` mapping
    replaces the prior hard-coded `"1"` rollback-destination literal:
    rollback now targets the version activation actually superseded,
    never a fixed literal and never a version-string ordering comparison.
  - **Version-aware activation/rollback event model**:
    `find_latest_activation_event` now returns `(kind,
    destination_version, commit)` — an activation trailer's value used
    directly, a rollback trailer's value resolved through
    `ACTIVATION_ROLLBACK_PREDECESSOR`. `is_activated` reports `True`
    whenever the resolved destination is not `"1"` (so `Workflow-
    Rollback: 2.2`, resolving to `"2.1"`, still reports activated).
    Rollback-trailer-value miss (a bare/empty value, a typo, or an
    unrecognized version such as `"2.9"`) resolves fail-closed as
    activated, via the shared `_activation_event_description` helper —
    never a silent fall-through and never an uncaught `KeyError`.
    `load_config`'s raise message and `ConfigMissingAfterActivationError`'s
    docstring generalize off the prior hard-coded `"Workflow v2.1"` text
    to name the resolved destination version, or the unresolved trailer's
    own raw value verbatim in the miss case.
  - **`TWO_STAGE_PLAN_REVIEW_VERSIONS = {"2.1", "2.2"}`** replaces the
    exact `governing_workflow_version == "2.1"` / `!= "2.1"` literal at
    `publish_plan_revision`, `plan_approval_gate_reachable`,
    `_require_v2_1_plan_review`, and `_validate_plan_review_stages` — a
    `"2.2"` item runs the identical two-stage plan-review protocol a
    `"2.1"` item does. `transition_to_awaiting_local_plan_review`'s
    docstring corrected from describing itself as `"2.1"`-only.
  - **`implementation_review_stages` ledger normalize/read plumbing**:
    `LOCAL_IMPLEMENTATION_REVIEW`/`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`
    canonical key constants; `_normalize_implementation_review_stage_key`/
    `normalize_implementation_review_stages`, mirroring
    `normalize_plan_review_stages`'s own collision-aware read contract
    (identity mapping today — no legacy alias has ever existed for this
    ledger); `_validate_implementation_review_stages`, mirroring
    `_validate_plan_review_stages`, hooked into `_validate_work_item`.
    New exception classes: `ImplementationReviewStagesInvalidForVersionError`,
    `ManualImplementationStageWithoutLocalStageError`,
    `AmbiguousImplementationReviewStageKeyError` — `WrongReviewerRoleError`/
    `StaleReviewContentIdError`/`check_manual_stage_bundle_id_advisory`
    are reused unchanged, already stage-agnostic. `CP3` owns this
    ledger's writers (`record_local_implementation_review`/
    `record_manual_implementation_review`) and their own preconditions.
  - **Unit tests** (`migration/overlays/2.5.0/payload/scripts/
    workflow_state_test.py`): `TestKnownPhases22Additions`,
    `TestActivationHelpersGeneralizedTargetVersion`,
    `TestVersionAwareActivationEventModel`,
    `TestTwoStagePlanReviewVersionsInheritance`,
    `TestImplementationReviewStagesLedgerPlumbing`,
    `TestActivatingDoesNotMutateExistingWorkItems` (regression: a fresh
    `route_work_item` call under a `"2.2"`-default config changes no
    already-existing work item's own `governing_workflow_version`),
    `TestImplementationReviewTwoStageDeclarationCoverage` (every CP1–CP13
    deliverable path this item's own
    `implementation-review-two-stage-artifacts.json` declares classifies
    `protected`, and `compute_review_content_id_implementation_stage`
    does not raise for this item against the real repository).
- **Verification**: `PYTHONPATH="migration/overlays/2.5.0/payload/scripts:scripts"
  python3 -m unittest workflow_state_test` — 721 tests, all green except
  three pre-existing environment-only errors (`TestCanonicalStateSerialization`'s
  two "live `WORKFLOW_STATE.json`" tests and `TestGlobalLockOrderItem372h`'s
  `setUpClass`), all three caused by running the overlay's own test file
  directly from its source tree rather than through an installed
  repository's real layout (they resolve paths via `Path(__file__).
  resolve().parent.parent`, which only lands on a real repository root
  when this file is installed at `scripts/workflow_state_test.py`) —
  confirmed pre-existing by running the identical command against `CP1`'s
  own committed state before this checkpoint's changes, unaffected by
  this checkpoint. `python3 tests/run_all.py --fast` — all green.
