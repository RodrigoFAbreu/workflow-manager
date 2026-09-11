# `plan-amendment-mechanism` Requirements Ledger

Mutable, human-readable execution record for the `plan-amendment-mechanism`
work item. Physically separate from the immutable, machine-readable
`plan-amendment-mechanism-mapping.json` in this same directory (D4b): the
mapping file is the approved requirement↔checkpoint binding and is
plan-stage protected (editing it changes `review_content_id`); this ledger
is never a fingerprint input — it resolves under
`docs/ai-workflow/requirements/` in `PLAN_STAGE_EXCLUDED_PREFIXES` and in
this item's own plan-stage approval's `excluded_prefixes`. Editing this
file never stales a plan approval or a technical approval and never
requires a fresh review round.

Each checkpoint appends one section here as it completes: implementation
evidence, verification results, review findings, and (where applicable)
functional-verification outcome. This is a log, not a status source —
`WORKFLOW_STATE.json`'s `checkpoints[id]` remains the sole record of
checkpoint status (D-Registry); nothing here is re-derived from or
overrides it.

## `CP1` — Lock the amendment state-machine design into the successor's own normative design document

- **Implementation evidence**:
  - **Design-doc lock (D-Plan-Amendment-1..8, O-R30-2)**: created
    `migration/overlays/2.4.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`
    as a full-file copy of the frozen
    `distribution/workflow/2.3.1/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`,
    with one addition: a new `### D-Plan-Amendment-1` through
    `### D-Plan-Amendment-8` section block, inserted immediately after the
    existing `### D-Bundle-Manifest` section (the last `### D-<name>`
    section in the document's `## Decisions` area) and before
    `## Preserved ownership (unchanged, extended)`, under the document's
    existing `### D-<name>` heading convention (headings converted from
    `PLAN_AMENDMENT_MECHANISM_PLAN.md`'s own colon-separated
    `### D-Plan-Amendment-N: <title>` form to the target document's
    em-dash form, `### D-Plan-Amendment-N — <title>`; body prose carried
    over unchanged from the approved plan's own `## 2. Design decisions`
    section, lines 31–1843).
  - **Forbidden-pattern check (I-R25-1/I-R26-1)**: verified by grep that
    the added content introduces, anywhere in the file, no
    D-Plan-Review-Stages `/review-plan` transition-table row (a markdown
    table row with a state cell, a verdict cell, and a `/review-plan`
    command cell), no four-cell Requirements-traceability-table row keyed
    by a `WFR-nn` id, and no line beginning `85. `/`96. ` — the file has
    zero `^|` table rows and the only `AWAITING_LOCAL_PLAN_REVIEW`
    occurrences are inside ordinary prose, not table cells.
  - **Defect record (CLAUDE.md's "write it up under `docs/defects/` and
    stop there")**: opened
    `docs/defects/v2.3.1-002-no-plan-amendment-edge.md`, in the same shape
    as `v2.3.1-001`, documenting frozen v2.3.1's missing
    `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` → plan-revision edge,
    with disposition "documented **and** an authored-fix shipped as a
    second release" (distinct from `v2.3.1-001`'s "documented, not
    repaired"), per the plan's own closing paragraph under
    `D-Plan-Amendment-8`.
  - **Ledger initialization (WF4b)**: this file did not exist before this
    checkpoint; created here as the first checkpoint of `IMPLEMENTING`,
    per `D3`'s "a living document WF4b initializes and implementation
    sessions append to."
- **Verification**: `python3 -m unittest workflow_integration_test.TestReviewPlanWriteSetConsistencyLint workflow_integration_test.TestRequirementsMappingTableConformance` (6 tests, all green — these read the live, untouched `docs/ai-workflow/WORKFLOW_V2_PLAN.md`, unaffected by this checkpoint's overlay-only write, and confirm the checkpoint introduced no regression in the patterns it is required to avoid); `python3 -m unittest workflow_state_test` (616 tests, all green).
- **Review findings**: none yet — self-review pending at
  `SELF_REVIEWING_IMPLEMENTATION`.
- **Functional-verification outcome**: not applicable at this checkpoint.

## `CP2` — Author workflow_state.py additions in the overlay

- **Scope note**: this checkpoint's own registry row is scoped strictly
  to `scripts/workflow_state.py` (and its two payload-adjacent test
  files) inside `migration/overlays/2.4.0/payload/scripts/`. CP3
  (command files: `/request-plan-amendment.md`, `approve-review.md` step
  4c's own `post_registry`/`post_plan_text`/`pre_registry`/`pre_plan_text`
  read, `workflow_integration_test.py`, `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`,
  `REVIEW_PROTOCOL.md`, `MILESTONE_WORKFLOW.md`) is separate, later, scope
  -- not attempted here. The root, self-hosted `scripts/workflow_state.py`
  this repository's own commands run against is frozen v2.3.1 and is
  never edited; every change below lands only in the new
  `migration/overlays/2.4.0/payload/scripts/` copy (a full-file copy of
  the frozen v2.3.1 module plus this checkpoint's additions), per
  `CLAUDE.md`'s "distribution/ is generated, not edited" rule applied to
  its overlay analogue.
- **Implementation evidence**:
  - **Created the overlay payload directory**: copied
    `scripts/workflow_state.py`, `scripts/workflow_state_test.py`, and
    `scripts/workflow_state_completion_obligations_test.py` byte-for-byte
    into `migration/overlays/2.4.0/payload/scripts/` (verified identical
    to `distribution/workflow/2.3.1/payload/scripts/`'s own copies before
    editing), then edited only the three copies below.
  - **Vocabulary additions (D-Plan-Amendment-1/3/4)**: `KNOWN_PHASES`
    gains `"AMENDING_PLAN"`; `APPROVAL_STATUSES` gains `"SUPERSEDED"`
    (disambiguated in a code comment from `_RECONCILIATION_STATUS_TOKENS`'
    own same-named, unrelated token, I-R32-1); `CHECKPOINT_STATUSES` gains
    `"NEEDS_REVALIDATION"`. All three are additive frozenset extensions;
    `select_next_checkpoint`'s own "not yet `COMPLETE`" test already
    treats any non-`COMPLETE` status as selectable, so no change to the
    selection algorithm itself was needed (confirmed by inspection of
    `select_next_checkpoint`'s live body).
  - **New error family (amendment-prefixed, I-R32-1)**:
    `WrongPhaseForAmendmentRequestError`,
    `AmendmentApprovalCommitUnreachableError`,
    `AmendmentAlreadyResolvedError`,
    `AmendmentReconciliationInputsMissingError`,
    `AmendmentPreSnapshotUnreproducibleError`,
    `AmendmentAnchorCoverageError`, `AmendmentAnchorMalformedError`.
  - **`request_plan_amendment(state, work_item_id, reason, *, repo_root,
    now)`** (D-Plan-Amendment-1/2/3, `/request-plan-amendment`'s sole
    writer): refuses outside `phase in {"IMPLEMENTING",
    "SELF_REVIEWING_IMPLEMENTATION"}` (`WrongPhaseForAmendmentRequestError`,
    also what refuses a redundant second request once at
    `AMENDING_PLAN`); calls `discover_plan_approval_commit`/`_is_ancestor`
    directly (the identical pair `implementing_entry_reachable` itself
    evaluates, never through that four-exit composite) and raises
    `AmendmentApprovalCommitUnreachableError` *before* superseding
    anything when the approval commit is not discoverable or not an
    ancestor of `HEAD`; on success, appends one `amendment_history` entry
    (bounded, content-addressed reference model, EXT-R6-I1:
    `superseded_plan_approval` deep-copied, `checkpoints_snapshot`
    deep-copied, `pre_amendment_approval_commit` the single resolved
    commit SHA, `resolved_at_plan_revision: None`), sets
    `plan_approval.status = "SUPERSEDED"`, sets `amendment_base_commit` to
    current `HEAD`, and writes `work_item["phase"] = "AMENDING_PLAN"` as a
    direct string-literal subscript assignment (so the AST-derived phase
    census in `workflow_state_test.py` resolves it without a hardcoded
    compensation entry).
  - **`load_pre_amendment_snapshot(repo_root, work_item_id, plan_path,
    registry_path, entry)`** (D-Plan-Amendment-3): resolves the pinned
    `blob` SHAs for `plan_path`/`registry_path` out of
    `entry["superseded_plan_approval"]["review_content_manifest"]`,
    cross-checks each is still reachable from
    `entry["pre_amendment_approval_commit"]` via `git ls-tree` before
    trusting it, retrieves the bytes via `git cat-file -p`, and returns
    `(pre_plan_text, pre_registry)` (UTF-8 decode / JSON parse
    respectively). Raises `AmendmentPreSnapshotUnreproducibleError`,
    naming the path and blob, on any retrieval or cross-check failure
    (verified against a real tampered-blob fixture in a scratch repo --
    see Verification).
  - **Paired-anchor grammar (D-Plan-Amendment-4, B4-new/B5-new/I5-new)**:
    `parse_checkpoint_anchor_spans(text, *, strict)` parses
    `<!-- CPn -->`/`<!-- /CPn -->` pairs into
    `{"CPn": [(start, end), ...]}`; `strict=True` (used only for
    `post_plan_text`) raises `AmendmentAnchorMalformedError` on an
    unmatched open tag, an orphan close tag, or same-id nesting;
    `strict=False` (used only for `pre_amendment_plan_text`) instead
    silently omits a malformed id from the returned map, the fail-closed
    "no information" direction the pre side requires.
    `checkpoint_content_hash(text, checkpoint_id, *, strict)` sha256-hashes
    the concatenation, in document order, of every well-formed span for
    that id, returning `None` (never a refusal) when the id has zero
    well-formed spans -- the zero-anchor legacy default and the
    partial-coverage case both fall out of this one `None` return, with
    no separate special-casing. `validate_post_anchor_coverage(post_plan_text,
    post_registry)` requires every registry checkpoint id to have at
    least one well-formed pair, raising `AmendmentAnchorCoverageError`
    (missing id) or letting the strict parse's own
    `AmendmentAnchorMalformedError` propagate.
  - **`reconcile_checkpoints_after_amendment(pre_registry, post_registry,
    pre_plan_text, post_plan_text, checkpoints)`** (D-Plan-Amendment-4):
    per shared id, compares registry row fields (`name`/`depends_on`/
    `complexity`/`session_target`) and per-checkpoint content hash
    (pre-side non-strict/conservative -- `None` counts as "changed";
    post-side already validated strict) to classify each id `retained` /
    `needs_revalidation` / `dropped` / `new`; a `COMPLETE` checkpoint
    classified `needs_revalidation` is rewritten to status
    `"NEEDS_REVALIDATION"`; a removed id is dropped from the live
    `checkpoints` map. A single forward pass over the post-amendment
    registry's own (topologically valid) order then propagates dependency
    closure: any checkpoint left `COMPLETE` whose own `depends_on`
    includes a non-`COMPLETE`/absent id is also rewritten to
    `NEEDS_REVALIDATION` (B6.3) -- no fixed-point loop needed. Returns
    `{"checkpoints": ..., "outcome": {id: ...}, "dropped": [...]}`.
  - **`apply_plan_approval` widened** (D-Plan-Amendment-4, B2-new): four
    new, optional, keyword-only parameters,
    `pre_registry`/`pre_plan_text`/`post_registry`/`post_plan_text`,
    defaulting to `None`. For a work item with no open amendment
    (`amendment_history` empty, or its last entry already resolved), all
    four stay unconsulted and behavior is byte-for-byte unchanged --
    verified directly (see Verification) rather than merely asserted.
    For a work item with an open amendment (`amendment_history`
    non-empty, last entry's `resolved_at_plan_revision` still `None`): a
    `None` among the four raises `AmendmentReconciliationInputsMissingError`
    naming which; an already-resolved entry defensively raises
    `AmendmentAlreadyResolvedError` (unreachable in practice given the
    `has_open_amendment` guard, kept as the same "wrong state, refuse and
    name it" discipline the plan calls for); otherwise
    `validate_post_anchor_coverage` runs, then
    `reconcile_checkpoints_after_amendment`'s outcome is folded into the
    returned state (`checkpoints` rewritten; `current_checkpoint_id`/
    `last_completed_checkpoint_id` nulled if either named a dropped id;
    `amendment_history[-1]["resolved_at_plan_revision"]` set to the work
    item's own live `plan_revision`), alongside the function's unchanged
    `plan_approval`/`phase`/`state_revision`/`last_transition` writes.
    `plan_revision` itself is never written by this function.
  - **`open_plan_approval_journal` widened**: gained the identical four
    optional keyword-only parameters, forwarded verbatim into its one
    internal `apply_plan_approval` call -- no read of its own, no other
    change to the function.
  - **`REVIEW_SUBJECT_ROSTER` decision recorded** (compatibility-audit
    deliverable): a comment above the frozenset explains why
    `/request-plan-amendment.md` (CP3) is deliberately not added --
    it never reads `REVIEW_FEEDBACK.md`, recomputes/compares a
    `bundle_id`, or presents a bundle for review, so none of the
    roster's three semantic disjuncts apply.
  - **`workflow_state_test.py` (overlay copy)**: `EXPECTED_WRITERS` gains
    `"AMENDING_PLAN": {"request_plan_amendment"}`.
  - **`workflow_state_completion_obligations_test.py` (overlay copy)**:
    `TestNeverPersistedPhaseVocabulary.PERSISTED` gains `"AMENDING_PLAN"`.
  - **`_run_bytes` helper**: a binary-safe counterpart of `_run` (which
    uses `text=True` and would corrupt/misdecode arbitrary blob bytes),
    added for `load_pre_amendment_snapshot`'s `git cat-file -p` read.
- **Verification**:
  - `PYTHONPATH=migration/overlays/2.4.0/payload/scripts:scripts python3 -m unittest workflow_state_test` run against the **overlay's own** edited module: 614 tests, 611 green / 3 errors, all three `FileNotFoundError` against overlay-tree paths CP3+ has not yet placed (`docs/ai-workflow/WORKFLOW_STATE.json`, `docs/ai-workflow/dry-run/verify_372h_lock_primitive_predicate.py`) -- not a regression from this checkpoint's own edits, since the overlay tree is necessarily partial before CP3/CP6-CP9 land their own payload files. The two directly relevant census tests --
    `TestPersistedPhaseWriterCensus.test_the_persisted_phase_writers_are_exactly_these`
    and `test_every_write_site_resolves_to_a_named_phase` -- pass.
  - `PYTHONPATH=migration/overlays/2.4.0/payload/scripts:scripts python3 -m unittest workflow_state_completion_obligations_test`: 106 tests, 105 green / 1 error, the same class of pre-existing-doc `FileNotFoundError`
    (`docs/ai-workflow/MILESTONE_WORKFLOW.md`, a CP3 deliverable) in
    `TestNeverPersistedPhaseVocabulary.test_the_document_marks_every_one_of_them_and_no_other`.
    The directly relevant `test_exactly_four_known_phases_are_never_persisted`
    and `test_all_four_remain_in_the_validator_allowlist` pass.
  - Hand-rolled functional verification of every new function against
    both synthetic state fixtures and a real scratch Git repository
    (temporary, outside this repository): `parse_checkpoint_anchor_spans`/
    `checkpoint_content_hash` against well-formed, unterminated, orphan-close,
    and nested-open fixtures (all four malformed shapes correctly raise in
    `strict` mode and correctly degrade to `None`/omitted in non-strict
    mode); `reconcile_checkpoints_after_amendment` against a
    retained/row-changed/content-changed/dependency-closure/dropped/new
    fixture set (all six outcomes verified); `request_plan_amendment`
    against a real two-commit scratch repository (success path, wrong-phase
    refusal, and unreachable-approval-commit refusal, the last confirmed to
    leave `plan_approval.status` still `"CURRENT"`); `load_pre_amendment_snapshot`
    against the same scratch repository (successful retrieval, and a
    tampered-blob fixture correctly raising
    `AmendmentPreSnapshotUnreproducibleError`); `apply_plan_approval`'s
    amendment fold against a synthetic open-amendment fixture (missing-inputs
    refusal, already-resolved inertness, and the full fold producing the
    expected `checkpoints`/`amendment_history`/`phase` result).
  - Confirmed the root, self-hosted `scripts/workflow_state.py` (and its
    two sibling test files) remain byte-identical to
    `distribution/workflow/2.3.1/payload/scripts/`'s own copies --
    nothing in this checkpoint touched the frozen, self-hosted runtime
    this very command depends on.
- **Review findings**: none yet -- self-review pending at
  `SELF_REVIEWING_IMPLEMENTATION`.
- **Functional-verification outcome**: not applicable at this checkpoint.
