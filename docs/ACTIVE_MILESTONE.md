# Active Milestone

## Milestone

**In progress.** `implementation-review-two-stage` (`governing_workflow_version:
"2.1"`, plan approved at revision 41, superseding the revision-33 approval
CP1 originally executed against via amendment 0): Workflow `2.5.0` —
implementation review, review scalability, and post-v2.3.1 remediation.
Full plan: `docs/ai-workflow/IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md`.

## Goal

Mirror the already-shipped two-stage local-then-manual-external plan-review
design (`D-Plan-Review-Stages`) onto the implementation-review gate, gated
behind a new `governing_workflow_version: "2.2"` so no existing `"1"`/`"2.1"`
work item's behavior changes; make bounded improvements to review
scalability/convergence (normative-vs-historical review material,
canonical/generated review data, a bounded finding-taxonomy circuit
breaker); and reconsider this repository's own remaining post-v2.3.1
correctness/ergonomics backlog. Deliverable: a new authored Workflow
release, `2.5.0` (`distribution/workflow/2.4.0/` base plus
`migration/overlays/2.5.0/`), per this repository's `CLAUDE.md` "Adding an
authored Workflow release" process. Scope is deliberately bounded to
Workflow tooling/process — no RepFlow product work, no Controller
development.

## Current checkpoint

**CP1-CP6 complete** (`implementation-review-two-stage`, 13 checkpoints
total). Next: **CP7** (review-scalability branch 2, depends on CP2).

CP6 delivered `D-Review-Material-Lifecycle` (`§2.4`), in
`migration/overlays/2.5.0/payload/`:

- `docs/ai-workflow/WORKFLOW_V2_PLAN.md`: the new `### D-Review-Material-Lifecycle`
  top-level design section (unit/nesting definition, fail-closed default,
  the marker-edit-only-route-to-HISTORICAL invariant, the narrative-content
  guarantee's scope, the two-subject marker-presence obligation, the
  marking pass, and the governing-version enumeration sweep). CP6's own
  marking pass wrote an explicit `<!-- review-material-lifecycle: CURRENT
  -->` marker onto `D-Implementation-Review-Stages`,
  `D-Implementation-Review-Version-Activation`, and this section itself —
  the three in-scope top-level sections that had none of their own; CP1's
  already-marked `2.5.0 disposition record` subsection was left untouched.
  Two pre-existing, genuinely-closed disposition sections the
  governing-version sweep itself flagged — `## Round 11 finding
  disposition (revision 10)` and `## Checkpoint registry` — were marked
  `HISTORICAL` as a deliberate, diff-visible act (never a reword of
  otherwise-untouched historical prose).
- `docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md`: one top-of-file
  `CURRENT` marker (its own marker-presence subject is the whole document).
- `scripts/workflow_state.py`: `parse_markdown_units`/`document_level_unit`
  (heading-delimited unit parsing, with nesting — a nested unit's own
  explicit marker is never folded into its container's search, which is
  what keeps a merge-by-heading-demotion from silently promoting material
  to `HISTORICAL`), `unit_state` (classification via the first non-blank
  line of a unit's own text, reusing CP1's `render_marker`/`parse_marker`
  exclusively), `check_marker_presence_whole_document`/
  `check_marker_presence_plan_sections` (the marker-presence obligation),
  `find_forbidden_narrative`/`check_narrative_content` (the
  narrative-content guarantee, scoped to explicit-`CURRENT` units only),
  `mark_missing_units_current` (the marking pass), and
  `find_governing_version_occurrences`/`sweep_governing_version_enumeration`
  (the governing-version enumeration sweep: both detection forms, a
  plan-review-context requirement, negation-cue exclusion, and the
  occurrence-granular/whole-document allowlist).
- `scripts/workflow_state_test.py`: `ReviewMaterialLifecycleClassificationTest`,
  `ReviewMaterialLifecycleMarkerPresenceTest`,
  `ReviewMaterialLifecycleMarkingPassTest`,
  `ReviewMaterialLifecyclePreMarkingPartitionFixtureTest`,
  `ReviewMaterialLifecycleRealCorpusTest`, and
  `GoverningVersionEnumerationSweepTest` (32 new tests, all passing) —
  positive/negative/ambiguous/malformed-marker, two-version-transition,
  boundary-redrawing, narrative-location, scope, already-marked-nested-unit,
  marker-presence, a pre-marking classification-partition fixture, a
  real-corpus run of both the marker-presence obligation and the
  narrative-content guarantee over their actual subjects, and the sweep's
  own two detection forms, negation/widened-form exclusions, occurrence
  allowlist, whole-document allowlist, and a real-corpus run.

Running the finished governing-version sweep against the overlay's own
`.claude/commands/*.md`/`docs/ai-workflow/*.md` (before any fix) flagged 10
occurrences beyond CP1's/CP4's own already-fixed sites — all bare
`"2.1"`-scoped or `{"1","2.1"}`-exhaustive claims about the two-stage
plan-review protocol's own applicability, now stale since
`TWO_STAGE_PLAN_REVIEW_VERSIONS = {"2.1", "2.2"}`. Two lived inside
genuinely-closed disposition sections (marked `HISTORICAL` per the
carve-out); the other eight were widened in place (`docs/ai-workflow/MILESTONE_WORKFLOW.md`
twice; `docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s `D-Plan-Review-Stages`/`D-Self-Governance`/`D3`
sections six times). The sweep is now clean over the real corpus (asserted
by `test_real_corpus_sweep_is_clean`).

A before/after classification-partition check (every `WORKFLOW_V2_PLAN.md`
unit, pre- vs. post-CP6, via `git show HEAD:...` against the CP6 start
commit) confirmed exactly the two deliberately-marked sections above
became `HISTORICAL` and no other pre-existing unmarked unit was
reclassified — guarantee (v) holds for this checkpoint's own real
introduction, not only the fixture.

Verification run for CP6 (narrowest relevant check, not the full suite):
```
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts \
  python3 -m unittest \
  workflow_state_test.ReviewMaterialLifecycleClassificationTest \
  workflow_state_test.ReviewMaterialLifecycleMarkerPresenceTest \
  workflow_state_test.ReviewMaterialLifecycleMarkingPassTest \
  workflow_state_test.ReviewMaterialLifecyclePreMarkingPartitionFixtureTest \
  workflow_state_test.ReviewMaterialLifecycleRealCorpusTest \
  workflow_state_test.GoverningVersionEnumerationSweepTest -v
```
Result: 32/32 passed. A full `workflow_state_test` run under the same
`PYTHONPATH` trick (794 tests, up from CP5's 762) shows only the same 3
pre-existing errors that trick itself is known to produce outside the
composed release tree (`TestGlobalLockOrderItem372h.setUpClass` and
`TestCanonicalStateSerialization`'s two dry-run-path-relative tests),
unaffected by this checkpoint's changes.

Amendment 0 (requested from `IMPLEMENTING` after CP1's original commit,
`20a808d`, to fix `implementation-review-two-stage-artifacts.json`'s
`plan_stage.excluded_prefixes` gap for `migration/`/`tests/`/`distribution/`)
downgraded every registry checkpoint, CP1 included, to
`NEEDS_REVALIDATION` as part of its reconciliation. Revalidating CP1 against
the amended, re-approved plan (revision 41): `git diff 20a808d..HEAD --
docs/ai-workflow/registry/implementation-review-two-stage-registry.json`
shows CP1's own registry entry is byte-for-byte unchanged by the amendment
and every subsequent plan-review round (only CP7's and CP13's entries
gained clarifying text); the amendment's actual delta is confined to
`implementation-review-two-stage-artifacts.json`'s declaration sets. CP1's
already-committed deliverable therefore required no rework — this
invocation re-ran CP1's own narrowest check (below, unchanged result) and
re-marks it `COMPLETE` under the new plan approval so the registry's own
per-checkpoint status again matches reality.

CP1 delivered, in `migration/overlays/2.5.0/payload/`:
- `docs/ai-workflow/WORKFLOW_V2_PLAN.md`: new `D-Implementation-Review-Stages`
  and `D-Implementation-Review-Version-Activation` design sections, plus a
  `#### 2.5.0 disposition record` subsection (marked `HISTORICAL` via the
  new canonical `review-material-lifecycle` marker) carrying the
  "where the two-stage mirror genuinely diverges" content.
- `docs/ai-workflow/MILESTONE_WORKFLOW.md`: the two new phases
  (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`/
  `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`), their transition
  table, widened `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`/
  `AWAITING_TECHNICAL_APPROVAL` entry conditions, the Hard gates summary's
  "2.2" refinement paragraph (count stays 6), and the
  `TWO_STAGE_PLAN_REVIEW_VERSIONS` restatement of the plan-review "2.1"
  literal (headings, transition table, `AWAITING_PLAN_APPROVAL` entry,
  `AMENDING_PLAN`/`SELF_REVIEWING_PLAN` scope sentences).
- `docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`: widened to `"2.1"`/`"2.2"`
  alike (title, scope paragraph, `/apply-plan-review` bullet).
- `docs/ai-workflow/REVIEW_PROTOCOL.md`: `/review-implementation`'s
  dual-mode behavior documented (advisory for `"1"`/`"2.1"`, authoritative
  for `"2.2"`).
- `docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md` (new): operator
  guide for the two-stage implementation-review flow and the `"2.2"`
  activation/rollback procedure (hand `WORKFLOW_CONFIG.json` edit only,
  never through `build_activated_config`/`build_rolled_back_config`;
  explicitly not retroactive — names `workflow-controller-generation-1` as
  the concrete instance that stays `"2.1"`).
- `scripts/workflow_state.py`: the canonical `render_marker`/`parse_marker`
  pair for the `review-material-lifecycle` marker (`{CURRENT, HISTORICAL}`),
  which `D-Review-Material-Lifecycle` (CP6) will import rather than
  re-derive.
- `scripts/workflow_state_test.py`: `ReviewMaterialLifecycleMarkerTest` (6
  tests, all passing) pinning `render_marker`/`parse_marker`'s exact
  output bytes, roundtrip, and fail-closed malformed-input handling.

CP2 delivered `scripts/workflow_state.py`/`workflow_state_test.py` plumbing
(`KNOWN_PHASES` additions, the version-aware activation/rollback event
model, `TWO_STAGE_PLAN_REVIEW_VERSIONS`, the `implementation_review_stages`
ledger helpers). CP3 delivered the review-stage writers and gate widening
(`record_local_implementation_review`, `record_manual_implementation_review`,
`technical_approval_gate_reachable`'s `"2.2"` ledger check,
`bundle_generation_target_phase`, the widened field-set constants, the
recovered-role committed-phase membership test). CP4 delivered the command
contracts (`"2.2"` branches across the dual-mode commands, the new
`/record-manual-implementation-review.md`, and
`WORKFLOW_V2_1_OPERATOR_REFERENCE.md`'s widening). See those checkpoints'
own commits (`61e04a8`, `0f06771`, `7d737fa`) for their full detail.

CP5 delivered the `§2.3` convergence/token-efficiency measures, in
`migration/overlays/2.5.0/payload/`:
- `.claude/commands/review-implementation.md`: tightened the `"2.2"`
  authoritative branch's A4 verification-bar text to state explicitly that
  it must be at least as rigorous as today's combined
  `SELF_REVIEWING_IMPLEMENTATION` self-review plus the pre-existing
  advisory `/review-implementation` pass — never a weaker substitute for
  either, since this pass now gates a real phase transition.
- `docs/ai-workflow/REVIEW_PROTOCOL.md`: a new "No bundle regeneration
  between the local and manual-external implementation-review stages"
  subsection stating `REQ-4` explicitly and naming the mechanical
  enforcement (`StaleReviewContentIdError` in
  `validate_manual_implementation_review_preconditions`) and its
  advisory-only `bundle_id` counterpart.
- `scripts/workflow_state_test.py`: the disposable-repo fixture scenario —
  `TestLocalStageCatchesPlantedDefectWithoutManualRound` (a planted defect
  caught by the local stage on round 1, routed straight to
  `APPLYING_REVIEW_FEEDBACK` without ever opening a manual-external round —
  `REQ-5`) and `TestNoBundleRegenerationBetweenImplementationReviewStages`
  (the ordinary carry-through succeeds unchanged; a simulated regeneration
  between the two stages is hard-blocked — `REQ-4`), both built against a
  real `ScratchRepo` Git history rather than isolated dict-state
  assertions alone.

Verification run for CP5 (narrowest relevant check, not the full suite —
`migration/overlays/2.5.0/classification.json` does not exist yet, so
`tools/build_release.py --check` is not runnable until CP11):
```
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts \
  python3 -m unittest \
  workflow_state_test.TestLocalStageCatchesPlantedDefectWithoutManualRound \
  workflow_state_test.TestNoBundleRegenerationBetweenImplementationReviewStages -v
```
Result: 3/3 passed. A full `workflow_state_test` run under the same
`PYTHONPATH` trick (762 tests) shows only the 3 pre-existing errors that
trick itself is known to produce outside the composed release tree
(`TestGlobalLockOrderItem372h.setUpClass` and
`TestCanonicalStateSerialization`'s two `dry-run`-path-relative tests,
unaffected by this checkpoint's changes — confirmed unchanged by running
the same command against the pre-CP5 tree via `git stash`).

## Current blockers

None.

## Active plan

`docs/ai-workflow/IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md` (revision 41,
plan approval `CURRENT`, both `LOCAL_MODEL_PLAN_REVIEW` (round 42) and
`MANUAL_EXTERNAL_PLAN_REVIEW` (round 1) recorded `APPROVE`).

## Next action

Continue `/milestone-implement` to implement CP7, one checkpoint per
invocation (`workflow-2.1` resumable single-checkpoint session model).

## Functional review checklist

Not yet applicable — the milestone is still in `IMPLEMENTING`. A
disposable-repository functional-validation checklist is CP12's own
deliverable (bootstrap on `2.5.0`, activate `"2.2"` by hand per
`IMPLEMENTATION_REVIEW_WORKFLOW.md`, drive the full two-stage
implementation-review flow end-to-end including a `"2.2"`
functional-review bounded-fix scenario).
