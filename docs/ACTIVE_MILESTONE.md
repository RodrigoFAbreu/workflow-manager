# Active Milestone

## Milestone

**In progress.** `implementation-review-two-stage` (`governing_workflow_version:
"2.1"`, plan approved at revision 33): Workflow `2.5.0` — implementation
review, review scalability, and post-v2.3.1 remediation. Full plan:
`docs/ai-workflow/IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md`.

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

**CP1 complete** (`implementation-review-two-stage`, 13 checkpoints total).
Next: **CP2** (`workflow_state.py` plumbing in the overlay — `KNOWN_PHASES`
additions, generalized activation helpers, `TWO_STAGE_PLAN_REVIEW_VERSIONS`).

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

Verification run for CP1 (narrowest relevant check, not the full suite —
`migration/overlays/2.5.0/classification.json` does not exist yet, so
`tools/build_release.py --check` is not runnable until CP11):
```
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts \
  python3 -m unittest workflow_state_test.ReviewMaterialLifecycleMarkerTest -v
```
Result: 6/6 passed.

## Current blockers

None.

## Active plan

`docs/ai-workflow/IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md` (revision 33,
plan approval `CURRENT`, both `LOCAL_MODEL_PLAN_REVIEW` and
`MANUAL_EXTERNAL_PLAN_REVIEW` recorded `APPROVE`).

## Next action

Continue `/milestone-implement` to implement CP2, one checkpoint per
invocation (`workflow-2.1` resumable single-checkpoint session model).

## Functional review checklist

Not yet applicable — the milestone is still in `IMPLEMENTING`. A
disposable-repository functional-validation checklist is CP12's own
deliverable (bootstrap on `2.5.0`, activate `"2.2"` by hand per
`IMPLEMENTATION_REVIEW_WORKFLOW.md`, drive the full two-stage
implementation-review flow end-to-end including a `"2.2"`
functional-review bounded-fix scenario).
