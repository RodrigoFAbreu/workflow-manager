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

## `CP3` — Author command files

- **Implementation evidence**, each an overlay_delta-recorded full-file
  replacement/addition in `migration/overlays/2.4.0/payload/`:
  - **`.claude/commands/request-plan-amendment.md` (new)**: opens with the
    house "Enter the `AMENDING_PLAN` state of
    `docs/ai-workflow/MILESTONE_WORKFLOW.md`." preamble; resolves the
    target work item (step 0, refusing an item with no
    `WORKFLOW_STATE.json` entry at all); states the user-only guard
    (`disable-model-invocation: true` plus a literal confirmation naming
    the work item and the word `amendment`, plus a required non-empty
    `reason`) distinct from `USER_OVERRIDE`; states
    `D-Plan-Amendment-1`'s three preconditions -- phase, no
    `IN_PROGRESS`/claimed checkpoint (checked by this command itself, via
    `work_item["checkpoints"]`/`resolve_claim`, since
    `request_plan_amendment` does not check it), and no open plan-approval
    transaction (`plan_approval_takeover_evidence`); calls
    `workflow_state.request_plan_amendment` inside `state_transaction`;
    commits `WORKFLOW_STATE.json` alone with a single
    `Workflow-Work-Item:` trailer; its own "what happens next" prose names
    `scripts/prepare-ai-review.sh` under the `I-R14-2` phrasing constraint
    (no run/rerun-plus-backticked-invocation construction, so it never
    matches `_GENERATOR_RUN_RE`).
  - **`.claude/commands/approve-review.md`**: step 4c gains a new
    paragraph, before the `open_plan_approval_journal` call, that calls
    `workflow_fingerprint.resolve_plan_stage_metadata` fresh and reads
    `post_plan_text`/`post_registry` from the current working tree, and
    -- open amendment only -- `pre_plan_text`/`pre_registry` via
    `workflow_state.load_pre_amendment_snapshot`; forwards all four,
    verbatim, as new keyword arguments on the existing
    `open_plan_approval_journal` call. The numbered sequence itself is
    unchanged -- reconciliation adds no new guarded step.
  - **`.claude/commands/apply-functional-review.md`**: the broad-branch's
    sanctioned child sequence paragraph gains one new addendum paragraph
    (placed after it, not inside its own pinned wrapped text) naming
    `/request-plan-amendment <child-id>` -- a remediation child in
    `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` may request its own
    amendment on the same terms as its parent.
  - **`scripts/prepare-ai-review.sh`**: a new `AMENDMENT_DIFF.patch`
    generation step (plan stage only), written to
    `$ROOT_DIR/AMENDMENT_DIFF.patch` -- a sibling of `$BUNDLE_DIR`, never a
    descendant -- as `git diff <amendment_base_commit>..HEAD` restricted
    to the plan-stage protected paths, for a work item with an open
    amendment; deletes the file when none is open. The archive step widens
    to `tar -czf "$ARCHIVE_TMP" -C "$ROOT_DIR" current $(cd "$ROOT_DIR" &&
    [ -f AMENDMENT_DIFF.patch ] && echo AMENDMENT_DIFF.patch)`. Introduces
    no `assert_local_generation_matches` call and no
    `governing_workflow_version` awareness (confirmed by grep — the
    literal string does not appear in the file).
  - **`docs/ai-workflow/REVIEW_PROTOCOL.md`**: "Bundle structure" gains a
    paragraph describing `AMENDMENT_DIFF.patch` as a sibling of
    `<bundle_dir>`, never hashed; "Author-written files"' `REVIEW_REQUEST.md`
    bullet gains the fixed, unconditional, non-authoritative marker-line
    requirement (D-Plan-Amendment-5, EXT-R6-O1/O-R9-3). The two pinned
    sentences ("Must state `review_content_id: <hex>` as a plain labelled
    line", "`implementation_revision: <N>` matching the work item") are
    left byte-identical.
  - **`docs/ai-workflow/MILESTONE_WORKFLOW.md`**: a new `### AMENDING_PLAN
    (workflow-2.4.0, D-Plan-Amendment-1)` section, placed immediately
    after `### PLANNING` and before `### SELF_REVIEWING_PLAN` (so `##
    State reference`'s never-persisted summary paragraph stays inside the
    first-`### `-heading slice), carrying no *Vocabulary state — never
    persisted* marker (it is real and persisted); `### IMPLEMENTING` and
    `### SELF_REVIEWING_IMPLEMENTATION` each gain one clause on their own
    **Exit**/**Stop for user/reviewer?** bullets naming the re-entry edge.
  - **`docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`**: command
    count/roster updated to 16 (new `### /request-plan-amendment
    [work-item-id] — user-only` section); "Persisted phases" table gains
    the `AMENDING_PLAN` row (`request_plan_amendment`), and its own
    hand-maintained `expected` writer dict (in
    `workflow_integration_test.py`) gains the matching entry;
    "Declared/written" phase counts updated to eighteen/fourteen; "Enter
    the `X` state" table/literal updated ten-of-fifteen → eleven-of-sixteen
    and gains a `/request-plan-amendment` row; "Remediation children"
    section gains an addendum paragraph naming
    `/request-plan-amendment <child-id>`; the "whole plan lane persists
    exactly three phases" claim gains a scoping clarification
    (`I-R19-1`) distinguishing it from the new re-entry `AMENDING_PLAN`
    phase, without altering the pinned sentence itself.
  - **`scripts/workflow_integration_test.py`** (overlay copy): `_GOLDEN_COMMAND_FILE_SHA256`
    entries for `approve-review.md`/`apply-functional-review.md`
    recomputed against their edited bytes (with dated comments, no entry
    added for `request-plan-amendment.md` itself, matching the census's
    "thirteen of fifteen, not total" discipline); `_GENERATOR_MENTION_ONLY_COMMANDS`
    gains a `request-plan-amendment.md` entry with its own justification
    string (`I-R14-2`); `test_no_mention_only_command_instructs_its_own_generation`'s
    docstring reworded to a three-population reading (`I-R15-2`); the
    hardcoded `len(on_disk)` tripwire (two call sites) and its docstrings
    updated 15 → 16; the "Enter ..." preamble literal list and its
    docstring updated ten → eleven, gaining `request-plan-amendment`;
    `test_every_persisted_phase_row_names_its_real_writer`'s `expected`
    dict gains `"AMENDING_PLAN": ["request_plan_amendment"]`;
    `NON_SYMBOL_NAMES` gains the three `amendment_history`-entry/top-level
    state field names (`amendment_base_commit`, `amendment_history`,
    `pre_amendment_approval_commit`) that `test_every_code_symbol_the_reference_names_actually_exists`'s
    identifier scan would otherwise treat as unresolved code symbols.
  - **`docs/ai-workflow/requirements/plan-amendment-mechanism-ledger.md`**:
    this entry.
- **Verification**:
  - Constructed a disposable merged tree (`distribution/workflow/2.3.1/payload/`
    as the base, this checkpoint's overlay files layered on top, plus the
    `2.3.1` release's own `CLAUDE.md`/`docs/ACTIVE_MILESTONE.md` templates)
    to exercise the full, otherwise-partial overlay against
    `workflow_integration_test.py`'s complete corpus-derived checks --
    the overlay alone cannot run this suite meaningfully, since it holds
    only the files CP1-CP3 have touched, not a full sixteen-command
    payload. Outside the repository, discarded after verification; no
    output committed.
  - `python3 -m unittest workflow_integration_test` against that merged
    tree: 256 tests, 255 green / 1 error -- the one error is
    `test_the_historical_status_note_carries_a_dated_correction`, a
    `StopIteration` against the *template* `docs/ACTIVE_MILESTONE.md`
    (which carries no 2026-08-04 status note; only this self-hosted
    repository's own live copy does) -- not a regression from this
    checkpoint, and not reachable through any file this checkpoint's own
    scope touches.
  - Targeted, pre-fix-iteration runs of `TestGoldenCommandFileHashes`,
    `TestWorkItemTargetingContract`, `TestOperatorReferenceMatchesReality`,
    `TestRetiredScopedRemediationLeavesNoLiveSurface`,
    `TestGenerationCommandsNameTheCompleteAuthorInputSet`,
    `TestVersion21OnlyCommandsRefuseCleanlyForV1`,
    `TestBootstrapCommandStaticConformance`,
    `TestGoldenV1BehaviorAgainstPreV21BaseCommit`,
    `TestMatrixHelpersDoNotOutrunTheirCommands`,
    `TestAssertLocalGenerationMatchesCallSiteConformance`,
    `TestReviewPlanWriteSetConsistencyLint`,
    `TestRequirementsMappingTableConformance`,
    `TestLifecycleDiagramMatchesTheCode`, and
    `TestPlanApprovalCommitTrailerFinalParagraphConformance` (97 tests) —
    all green on the finished state.
  - `python3 -m unittest workflow_state_test workflow_state_completion_obligations_test`
    against the same merged tree: 722 tests, 720 green / 2 errors, both
    `FileNotFoundError` against the live, self-hosted-only
    `docs/ai-workflow/WORKFLOW_STATE.json` (not part of any release
    payload or template) — the same class of pre-existing environment gap
    CP2's own verification already documented for this merged-tree
    technique, not a regression.
  - `bash -n scripts/prepare-ai-review.sh` (syntax check) and a direct,
    isolated exercise of the new `AMENDMENT_DIFF.patch` python block
    against a real two-commit scratch Git repository (open-amendment case
    producing the expected restricted diff; closed/absent case exercised
    by inspection of the `unlink(missing_ok=True)` branch) — both
    confirmed the `set -e`-safety of the widened archive line's
    `$(... && echo ...)` construction when the file is absent.
  - Confirmed the root, self-hosted `.claude/commands/`,
    `scripts/prepare-ai-review.sh`, `scripts/workflow_integration_test.py`,
    and the three `docs/ai-workflow/*.md` files touched here remain
    byte-identical to `distribution/workflow/2.3.1/payload/`'s own
    copies — nothing in this checkpoint touched the frozen, self-hosted
    runtime this very command depends on.
- **Review findings**: none yet -- self-review pending at
  `SELF_REVIEWING_IMPLEMENTATION`.
- **Functional-verification outcome**: not applicable at this checkpoint.

## `CP4` — Fix workflow-manager's own release tooling and test suites for a second release

- **Implementation evidence**:
  - **`tools/migrate.py`'s destructive step and `--check` comparison, made
    release-scoped (D-Authored-Release-3, B1/I1-new)**: `main()` now reads
    `migration/classification.json`'s `workflow_version` once (the same
    field `migrate()` itself reads at `tools/migrate.py:333`) and derives
    `release_root = REPO_ROOT / "distribution" / "workflow" / version`.
    The ordinary regeneration path `shutil.rmtree`s only `release_root`,
    never the whole `distribution/` tree, so a later authored sibling
    (`distribution/workflow/2.4.0/`) survives an ordinary `2.3.1`
    re-extraction. `--check`'s comparison is now taken at one common root
    on both sides -- `_tree_digest(Path(tmp) / "workflow" / version)`
    against `_tree_digest(release_root)` -- replacing the previous
    disjoint-key-set comparison (`_tree_digest(Path(tmp))` against
    `_tree_digest(REPO_ROOT / "distribution")`) that reported every path
    both `missing:` and `extra:` unconditionally.
  - **`CLAUDE.md`'s two per-release statements (D-Authored-Release-3,
    I4-new)**: the hard-rule bullet now reads "Each
    `distribution/workflow/<version>/` is generated, not edited. `2.3.1`
    is byte-identical to the frozen upstream release; a later authored
    release is byte-identical to its own recorded base-plus-overlay
    composition."; the "Before changing anything" section's `--check`
    sentence now reads "`tools/migrate.py --check` proves each
    `distribution/workflow/<version>/` is still exactly what a fresh
    extraction (or, for an authored release, its recorded
    base-plus-overlay composition) produces; it does not by itself prove
    no unrelated file exists directly under `distribution/` outside every
    release directory." Neither sentence is asserted verbatim by any
    payload or workflow-manager test, so no test-side change was needed
    alongside it.
  - **Additive `provenance` (D-Authored-Release-2)**:
    `Release.__init__` (`src/workflow_manager/release.py`) gains
    `self.provenance = self.manifest.get("provenance", {"origin":
    "upstream"})`, alongside the existing `self.upstream` -- every
    extracted release's manifest predates this key and defaults exactly
    as `2.3.1`'s own would once `tools/build_release.py` (CP5) starts
    writing it for an authored one. `cli.cmd_releases`
    (`src/workflow_manager/cli.py`) prints `[{release.provenance
    ['origin']}]` alongside the existing upstream tag/commit line.
    `bootstrap`/`update` (`src/workflow_manager/install.py:349-355,
    469-480`) both pass `provenance=release.provenance` into the
    `Installation` they construct. `Installation`
    (`src/workflow_manager/installation.py`) gains a `provenance: dict`
    field (default `{"origin": "upstream"}`), placed immediately after
    `upstream` and before `installed_at` in the dataclass, in
    `to_dict()`'s fixed key order, and read in `from_dict` via
    `data.get("provenance", {"origin": "upstream"})` -- additive, so a
    pre-existing `2.3.1`-era record with no `provenance` key at all still
    loads. `SCHEMA_VERSION` is not bumped (D-Authored-Release-2's
    `Installation` schema-posture decision): the reader default already
    makes an old/new record shape-indistinguishable to every caller.
    Added `test_a_pre_provenance_record_still_loads_and_defaults_to_upstream`
    to `tests/test_bootstrap.py`'s `TestInstallationRecord` (section 4
    scenario 16) asserting exactly this round-trip.
  - **Every `REPO_ROOT`-rooted `find_release` call pinned to `"2.3.1"`
    explicitly (D-Authored-Release-4)**: a grep-verified, exhaustive pass
    over every `find_release(REPO_ROOT)` call site (no pre-enumerated
    list trusted) found and pinned all nineteen: `tests/test_bootstrap.py:69`,
    `tests/test_bootstrap_e2e.py:59,124`,
    `tests/test_internal_references.py:97`,
    `tests/test_migration_inventory.py:42,131`,
    `tests/test_no_live_state_imported.py:29,57,95`,
    `tests/test_payload_bytes.py:27,66,121`, and
    `tests/test_templates.py:63,78,106,134,153,185,207` -- each now reads
    `find_release(REPO_ROOT, "2.3.1")`. Exempted, by the same rule rather
    than by ad hoc carve-out: `tests/test_bootstrap.py:975-976`'s
    `find_release(self.manager_root)`/`find_release(self.manager_root,
    "2.3.1")` calls are not `REPO_ROOT`-rooted (a synthetic disposable
    fixture proving the newest-wins default itself) and were left
    untouched.
  - **`tests/test_conformance_suite.py:54`'s own carve-out
    (D-Authored-Release-4's named exception)**: `_SuiteRun.build` gained an
    explicit `workflow_version: str = "2.3.1"` parameter; its
    `find_release` call became `find_release(REPO_ROOT, workflow_version)`;
    `cls.workflow_version = workflow_version` is now stored on the class.
    This is the one `REPO_ROOT`-rooted call site this checkpoint does not
    pin to a bare literal, since it decides which release's payload is
    under test rather than only what the assertions compare against --
    CP6 calls the same method a second time with `workflow_version="2.4.0"`
    rather than duplicating it. `CI_SUITES`/`PORTABILITY_EXCEPTIONS`
    themselves stay the flat, non-per-release mappings they are today;
    restructuring them into `{"2.3.1": ..., "2.4.0": ...}` and adding the
    second, `2.4.0`-parameterized run is explicitly CP6's own row (section
    5), not this checkpoint's.
- **Verification**:
  - `python3 tools/migrate.py --check` — reports
    "`distribution/workflow/2.3.1/ matches a fresh extraction of the
    frozen upstream release`" and exits 0 (the release-scoped message and
    comparison, proving the common-root fix).
  - `python3 -m unittest test_bootstrap.TestInstallationRecord` (3 tests,
    all green, including the new pre-provenance-record case).
  - `python3 tests/run_all.py --fast` (`test_migration_inventory.py`,
    `test_payload_bytes.py`, `test_templates.py`,
    `test_no_live_state_imported.py`, `test_internal_references.py`,
    `test_bootstrap.py` — 216 tests total, all green): every pinned
    `find_release` call site and every `Installation`/`Release`
    provenance reader still resolves correctly.
  - `python3 -m unittest test_conformance_suite` (both `TestConformanceFixture`
    and `TestBootstrappedTarget`, ~199s): `TestConformanceFixture` fully
    green (proving `_SuiteRun.build`'s new `workflow_version` parameter
    still defaults to and exercises `2.3.1` exactly as before).
    `TestBootstrappedTarget` reproduces the same two pre-existing failures
    this repository already carries on `main` before this checkpoint
    (`test_failures_are_exactly_the_documented_portability_exceptions` and
    `test_every_documented_exception_actually_fires`, both against the
    same stale `TestRetiredScopedRemediationLeavesNoLiveSurface
    .test_the_historical_status_note_carries_a_dated_correction` entry) —
    confirmed via `git stash`/`git stash pop` that the identical failure,
    with the identical test name, reproduces unmodified on `main` at
    `HEAD` with none of this checkpoint's changes applied; not a
    regression from this checkpoint, and not reachable through any path
    this checkpoint's own scope touches, matching CP3's own prior note
    about this same stale exception.
- **Review findings**: none yet -- self-review pending at
  `SELF_REVIEWING_IMPLEMENTATION`.
- **Functional-verification outcome**: not applicable at this checkpoint.

## `CP5` — Release-authoring tooling

- **Implementation evidence**:
  - **`tools/build_release.py` (new, D-Authored-Release-1/2/3)**: a second,
    separate release-production tool, kept apart from `tools/migrate.py`
    (whose "frozen upstream tag -> `distribution/`" contract stays
    untouched -- no line of `tools/migrate.py` changed in this checkpoint).
    `build(base_version, overlay_dir, base_dist_root, out_dist_root, *,
    now_commit=None)`:
    1. loads the overlay's own `classification.json`, cross-checks its
       `base_workflow_version` against the requested base version;
    2. verifies the base release
       (`<base_dist_root>/workflow/<base_version>/`) against its own
       committed `manifest.json` (`_verify_base_release`: every
       artifact/template file present with the recorded sha256) --
       refuses to build on top of a base that fails this check;
    3. classifies every file under the overlay's own `payload/` tree
       through the overlay's rules (same first-match-wins shape
       `migration/classification.json` already uses), each rule declaring
       an `expected_kind` (`added`/`replaced`) that is cross-checked
       against the base release's own manifest by path -- a mismatch
       (e.g. a rule claiming `added` for a path the base already has)
       raises `BuildReleaseError` rather than guessing which is right,
       and a rule matching no payload file also raises;
    4. for every `replaced` file, records an additive `overlay_delta`
       field, `{"base_sha256": ..., "diff_sha256": ...}` -- `diff_sha256`
       is the sha256 of a unified diff between the base file and the
       overlay file (`unified_diff_sha256`), reproducible from `base
       payload + this recorded diff` alone (I2; CP6 owns the mirrored
       reproduction assertion);
    5. copies forward, byte-for-byte, every base artifact (`payload/` and
       `fixtures/` locations alike -- both live in
       `manifest["artifacts"]`, exactly as `tools/migrate.py` writes them)
       the overlay does not replace, and every base template unchanged;
    6. writes `<out_dist_root>/workflow/<successor-version>/manifest.json`
       with `upstream` copied forward from the base manifest unchanged
       (B3) and an additive `provenance: {"origin": "authored",
       "base_release": <base_version>, "overlay_commit": <HEAD at build
       time, or the caller-supplied `now_commit`>}` -- the producing half
       of the field CP4 already taught `Release.__init__`/`cli.py`/
       `install.py`/`installation.py` to read.
  - **`--check` reproducibility (a design correction found and fixed
    during this checkpoint's own manual verification, not part of any
    prior round's text)**: `base_dist_root` and `out_dist_root` are two
    separate parameters, not one shared `out_root` -- an ordinary build
    reads the base release and writes the successor under the same real
    `distribution/`, but `--check` must read the base from the real,
    committed `distribution/` while writing its trial rebuild into a
    throwaway temp root; collapsing them into one parameter (the first
    draft) made `--check` fail to find the base release at all. Separately,
    `overlay_commit` defaults to the live `git rev-parse HEAD` for an
    ordinary build, but `--check` reads the *previously recorded*
    `provenance.overlay_commit` back out of the already-committed manifest
    and pins the trial rebuild to that same value instead of re-deriving
    it from the current HEAD -- HEAD has necessarily moved forward by at
    least the commit that added the built tree itself by the time anyone
    runs `--check` again, so re-deriving it would make every `--check` run
    report a spurious `differs: manifest.json` forever. Verified directly
    (D-Authored-Release-3's own byte-identity discipline, exercised against
    this new tool rather than `tools/migrate.py`): built into a scratch
    `distribution/` under a real (throwaway) git repository, ran `--check`
    immediately (`rc=0`), made an unrelated commit to advance HEAD, ran
    `--check` again against the now-stale HEAD (`rc=0`, unchanged) --
    confirming the fix before relying on it.
  - **`migration/overlays/2.4.0/classification.json` (new, overlay
    classification ruleset, I-R16-2)**: twelve rules, one per overlay
    payload path (the eleven full-file replacements plus the one new
    `.claude/commands/request-plan-amendment.md`, CP1-CP3's own
    twelve-path set) -- every rule's `category` is `"distribution"`,
    matching exactly the category `migration/classification.json`'s own
    rules already assign each of the eleven replaced paths at `2.3.1`
    (verified by reading each path's base manifest record directly, not
    assumed), preserving install-profile membership across the
    replacement (`src/workflow_manager/release.py:29-32`'s
    `_PROFILE_CATEGORIES`: `distribution` installs under both `runtime`
    and `full`). Each rule also declares `expected_kind` (`"replaced"` for
    the eleven, `"added"` for the new command file), which `build()`
    cross-checks rather than trusts.
  - **The CI-workflow template: the deliberate no-op case
    (D-Authored-Release-5)**: `2.4.0`'s own payload test-suite *file set*
    is identical to `2.3.1`'s -- `workflow_state_test.py`,
    `workflow_integration_test.py` and
    `workflow_state_completion_obligations_test.py` gained content changes
    in CP2/CP3, but no suite file was added, removed, or renamed, and
    `workflow_fingerprint_test.py`/`workflow_test_harness_test.py`/
    `workflow_acceptance_matrix_test.py`/
    `workflow_fingerprint_generalization_test.py` are untouched. Per
    D-Authored-Release-5's own decision ("the overlay simply omits a
    `templates/` replacement and the base `2.3.1` template is copied
    forward unchanged"), the overlay carries no
    `templates/.github/workflows/workflow-conformance.yml` replacement,
    and `build()`'s template-copy-forward loop carries the base `2.3.1`
    template into `2.4.0` byte-for-byte, unchanged -- confirmed by the
    manual verification run below (`workflow_fingerprint.py`, an unrelated
    copied-forward payload file, and the template are both hash-identical
    to their base counterparts in the built tree).
- **Verification** (`tools/build_release.py` has no committed automated
  test yet -- that is CP6's own scope, "extend conformance suite with the
  parallel authored-release assertion set, overlay-delta verification";
  this checkpoint's own manual verification, run against scratch/temporary
  distribution roots so no real `distribution/workflow/2.4.0/` is written
  by this checkpoint -- CP6 alone regenerates it for real):
  - Built `migration/overlays/2.4.0` against a scratch copy of
    `distribution/workflow/2.3.1`: 61 artifacts (35 `distribution`, 24
    `conformance`, 2 `host-evidence` -- base's 60 plus the one new command
    file), 6 templates, `overlay_replaced: 11`, `overlay_added: 1`.
  - Every replaced file's `overlay_delta.diff_sha256` reproduces exactly
    from `unified_diff_sha256(base_bytes, overlay_bytes, path)` recomputed
    independently; every `overlay_delta.base_sha256` matches the base
    manifest's own recorded sha256 for that path.
  - A copied-forward, untouched file (`scripts/workflow_fingerprint.py`)
    is byte-identical between the base and the built successor tree.
  - Two consecutive builds with the same pinned `now_commit` produce a
    byte-and-mode-identical output tree (`_tree_digest` equality) --
    deterministic.
  - Error paths exercised directly: wrong `--base` raises
    `BuildReleaseError` naming the mismatch; a corrupted base payload file
    fails `_verify_base_release` and refuses to build; an overlay rule
    with a wrong `expected_kind` (claiming `added` for a path the base
    already has) raises naming the path; an overlay rule matching no
    payload file raises naming the unused pattern.
  - `python3 tools/migrate.py --check` -- still reports
    "`distribution/workflow/2.3.1/ matches a fresh extraction of the
    frozen upstream release`" and exits 0: this checkpoint's new tool and
    new overlay file touch nothing `tools/migrate.py` or
    `distribution/workflow/2.3.1/` own (D-Authored-Release-3).
  - `python3 tests/run_all.py --fast` -- all six suites green
    (`test_migration_inventory.py`, `test_payload_bytes.py`,
    `test_templates.py`, `test_no_live_state_imported.py`,
    `test_internal_references.py`, `test_bootstrap.py`).
  - `python3 -m py_compile tools/build_release.py` -- compiles clean.
- **Review findings**: none yet -- self-review pending at
  `SELF_REVIEWING_IMPLEMENTATION`.
- **Functional-verification outcome**: not applicable at this checkpoint.

## `CP6` — Regenerate `distribution/workflow/2.4.0/`; prove frozen `2.3.1`; make CI suites/exceptions per-release; extend the conformance suite; discharge D-Plan-Amendment-7's compatibility audit

- **Implementation evidence**:
  - **`distribution/workflow/2.4.0/` regenerated for real (D-Authored-Release-2/3)**:
    ran `python3 tools/build_release.py --overlay migration/overlays/2.4.0`
    against the committed `distribution/workflow/2.3.1/` base and the
    committed `migration/overlays/2.4.0/` overlay -- 61 artifacts (35
    `distribution`, 24 `conformance`, 2 `host-evidence`), 6 templates,
    `overlay_replaced: 11`, `overlay_added: 1`; `manifest.json`'s
    `provenance` is `{"origin": "authored", "base_release": "2.3.1",
    "overlay_commit": "5c0c32120e05435df0c7a169c9a71b628aa34917"}` (CP5's
    own commit -- the overlay's content as it actually stood when this
    build ran, not a later, unrelated HEAD).
  - **Frozen/reproducible, proven by `--check` (not merely asserted)**:
    `python3 tools/migrate.py --check` --
    "`distribution/workflow/2.3.1/ matches a fresh extraction of the frozen
    upstream release`", exit 0 -- `2.3.1` is untouched by this checkpoint.
    `python3 tools/build_release.py --overlay migration/overlays/2.4.0
    --check` -- "`distribution/workflow/2.4.0/ matches a fresh build from
    base 2.3.1 + overlay .../migration/overlays/2.4.0`", exit 0 -- the
    committed `2.4.0/` tree is byte-identical to what base + overlay alone
    reproduce.
  - **`tests/support.py`'s `CI_SUITES`/`PORTABILITY_EXCEPTIONS` made
    per-release**: `CI_SUITES` restructured from a flat `{suite: count}`
    map to `{"2.3.1": {...}, "2.4.0": {...}}` (both inner maps identical
    today -- `2.4.0`'s overlay changes payload-file *content*, never the
    suite *file set* or per-suite test *count*, confirmed by the run
    below); added `expected_portability_exceptions(workflow_version)`, the
    one place both `test_conformance_suite.py` and `test_bootstrap_e2e.py`
    derive their expected-failure set from a `by_version`-keyed
    `migration/portability_exceptions.json`.
  - **`migration/portability_exceptions.json` made per-release (`schema_version:
    2`)**: `by_version.2.3.1` carries the pre-existing single exception
    unchanged; `by_version.2.4.0` carries the same test
    (`workflow_integration_test.py`'s
    `TestRetiredScopedRemediationLeavesNoLiveSurface.test_the_historical_status_note_carries_a_dated_correction`),
    for the identical reason -- that suite file is copied forward into the
    `2.4.0` overlay payload unmodified (not one of CP2/CP3's eleven
    replaced files), and the overlay does not touch
    `docs/ACTIVE_MILESTONE.md`.
  - **`tests/test_conformance_suite.py` extended (parallel authored-release
    assertion set + three new checks)**: `_SuiteRun.build` now requires an
    explicit `workflow_version` (no silent default); `TestConformanceFixture231`/
    `TestConformanceFixture240` and `TestBootstrappedTarget231`/
    `TestBootstrappedTarget240` share their assertion bodies through
    `_ConformanceFixtureAssertions`/`_BootstrappedTargetAssertions` mixins
    (plain mixins, never themselves a `TestCase`, so the shared body is
    never discovered and run with no `WORKFLOW_VERSION` to build from),
    parameterized by `WORKFLOW_VERSION`; `231` stays exactly as it always
    was, `240` is CP6's own addition, run beside it, never in place of it.
    Three more checks, added once (not per-version, since they are about
    the authored release specifically): `TestAuthoredReleaseOverlayDelta`
    (I2 -- every recorded `overlay_delta` reproduces from base bytes +
    recorded diff alone, via `build_release.unified_diff_sha256`, and
    `provenance` is exactly the expected authored shape);
    `TestAuthoredReleaseCiTemplateSuiteNames` (the shipped `2.4.0` CI
    template names exactly `CI_SUITES["2.4.0"]`'s own suite set -- guards
    the D-Authored-Release-5 no-op decision against silent drift);
    `TestOverlayStateWriterClosure` (the `WFO-STATE-SERIALIZATION`
    closure-verifier gap: `workflow_state.discover_state_writers` only ever
    scans this repository's own `.claude/commands/`/`scripts/` trees at a
    Git commit, never `migration/overlays/<version>/payload/`, so a new
    state writer authored inside an overlay had no closure check at all;
    this widens the scan, reusing the frozen module's own
    `_parse_state_writer_declarations` against every present overlay's
    working-tree files, and positively confirms the widened scan actually
    covers `request-plan-amendment.md`/`workflow_state.py`, not merely that
    it runs).
  - **`tests/test_bootstrap_e2e.py` extended in parallel**:
    `TestBootstrappedRepositorySatisfiesTheFrozenSuite231`/`240` mirror the
    same mixin-parameterization shape; `TestCliDrivesTheSameOperations`'s
    hardcoded `"bootstrapped workflow 2.3.1"` assertion is replaced with a
    live `find_release(REPO_ROOT).version`-derived expectation, so adding
    `2.4.0` (now the newest release present) does not itself break a test
    that was only ever asserting "whatever `bootstrap` with no pin
    defaults to," per `find_release`'s own documented newest-wins contract.
  - **`migration/overlays/2.4.0/payload/scripts/prepare-ai-review.sh`
    correctness fix, found by this checkpoint's own run of the widened
    conformance matrix**: the archive line's process-substitution
    conditional member is now placed *before* the fixed `current`
    positional argument (`tar -czf "$ARCHIVE_TMP" -C "$ROOT_DIR"
    $(cd "$ROOT_DIR" && [ -f AMENDMENT_DIFF.patch ] && echo
    AMENDMENT_DIFF.patch) current`, not after it) -- item 341's frozen
    regression guard
    (`workflow_fingerprint_generalization_test.py`) requires the archive's
    positional directory argument to be the bare literal `"current"`, and
    with the conditional member trailing, an absent `AMENDMENT_DIFF.patch`
    made `current` the *first* positional argument by accident of shell
    word-splitting rather than by the literal the guard expects; reordering
    makes `current` always the fixed last positional argument regardless of
    whether the conditional member expands to anything, which is what the
    guard actually checks. Recorded as a fresh `overlay_delta` (this file
    is one of CP3's eleven replaced paths; the diff is against the same
    `2.3.1` base, unchanged from CP3's own delta base).
  - **D-Plan-Amendment-7's compatibility-audit acceptance obligation,
    discharged**: the obligation is to identify every payload-suite test
    function (`workflow_state_test.py`, `workflow_state_completion_obligations_test.py`,
    `workflow_integration_test.py`) whose read set intersects a path this
    release's checkpoints touch, run each against the finished overlay
    diff, and report every member green or an already-documented red.
    `TestConformanceFixture240`/`TestBootstrappedTarget240` run *every*
    test in all three files (not a hand-selected subset) against the
    finished `2.4.0` overlay diff inside a real conformance
    fixture/bootstrapped target, which is a superset of "every test whose
    read set intersects a touched path" -- discharged by construction
    rather than by a separate, narrower enumeration. Result: `256`/`616`/
    `106` tests each, all green except the one already-documented
    `by_version.2.4.0` exception above (a `docs/ACTIVE_MILESTONE.md`
    host-history read, not a Workflow-semantics regression). No new red.
  - **`docs/ai-workflow/requirements/plan-amendment-mechanism-ledger.md`**:
    this entry.
- **Verification**:
  - `python3 tools/migrate.py --check` -- `2.3.1` matches a fresh
    extraction, exit 0.
  - `python3 tools/build_release.py --overlay migration/overlays/2.4.0
    --check` -- `2.4.0` matches a fresh build from base `2.3.1` + the
    overlay, exit 0.
  - `python3 tests/run_all.py --fast` -- six suites, all green.
  - `python3 scripts/workflow_state_test.py` -- 616 tests, all green
    (narrow check, run first, against the live self-hosted module CP2's
    overlay copy mirrors).
  - `python3 tests/run_all.py` (full matrix, ~10m21s total): all eight
    suites green, including both slow suites --
    `test_conformance_suite.py` (410.0s: `TestConformanceFixture231/240`,
    `TestBootstrappedTarget231/240`, `TestAuthoredReleaseOverlayDelta`,
    `TestAuthoredReleaseCiTemplateSuiteNames`,
    `TestOverlayStateWriterClosure`, all green) and
    `test_bootstrap_e2e.py` (205.9s:
    `TestBootstrappedRepositorySatisfiesTheFrozenSuite231/240` and every
    other test in the file, all green). This is the run that proves
    `2.4.0`'s own conformance/bootstrap matrix passes end to end and that
    `2.3.1`'s own matrix is unaffected -- the strongest evidence this
    checkpoint offers, and the one this entry's "D-Plan-Amendment-7"
    paragraph above relies on directly.
- **Review findings**: self-review performed before commit (this
  checkpoint's own diff, `git diff HEAD` against CP5's commit, read in
  full): the two-line reordering fix to `prepare-ai-review.sh` was the one
  confirmed defect found and fixed (the archive-argument-order bug above);
  no other defect found. `docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`
  (an untracked file already present in the working tree before this
  checkpoint began, per `WORKTREE_IDENTITY.json`'s own recorded
  `expected_dirty_paths_by_work_item` snapshot) documents an unrelated
  defect found during this work item's own first `/approve-review plan`
  attempt; it is not part of this checkpoint's scope and is deliberately
  left uncommitted here, unchanged, per `CLAUDE.md`'s "don't touch
  unrelated working-tree changes."
- **Functional-verification outcome**: not applicable at this checkpoint.

