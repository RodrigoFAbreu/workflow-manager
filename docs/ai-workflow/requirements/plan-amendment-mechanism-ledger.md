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
