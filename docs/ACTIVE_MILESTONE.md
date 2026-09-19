# Active Milestone

## Milestone

**In progress.** `workflow-2-5-1-checkpoint-id-compatibility`
(`governing_workflow_version: "2.1"`, plan approved at revision 5): Workflow
`2.5.1` — widen the plan-amendment anchor-compatibility checkpoint-id
grammar to admit legacy, pre-`2.4.0` letter-suffixed ids (`CP4B`/`CP6B`).
Full plan: `docs/ai-workflow/WORKFLOW_2_5_1_CHECKPOINT_ID_COMPATIBILITY_PLAN.md`.

## Goal

`workflow-controller-generation-1`, a real downstream repository, was
successfully upgraded from Workflow `2.3.1` to `2.5.0` with its live work
item preserved. That live work item legitimately carries checkpoint ids such
as `CP4B` and `CP6B` — an inserted-checkpoint lettering convention that
predates Workflow `2.4.0`'s plan-amendment mechanism and that `D-Registry`'s
checkpoint-registry format has never forbidden. `/request-plan-amendment`
against that work item now fails, before any mutation, with
`AmendmentCheckpointIdShapeError`, because `2.4.0`'s plan-amendment
mechanism introduced a narrower, purely-numeric `CP<digits>` anchor grammar
and used it as a precondition on every checkpoint id a work item's registry
already contains, not merely on ids newly introduced by an amendment. This
milestone widens that one grammar — and only that one grammar — to
`CP<digits>` optionally followed by exactly one uppercase letter, so the
anchor mechanism accepts the checkpoint-id shapes real Workflow milestones
have actually used, while remaining exactly as strict as before for every
id shape it was never meant to admit. Deliverable: a new authored Workflow
release, `2.5.1`, built as `distribution/workflow/2.5.0/` (base, unchanged,
byte-for-byte immutable) plus `migration/overlays/2.5.1/` (this milestone's
own narrow overlay), per this repository's `CLAUDE.md` "Adding an authored
Workflow release" process. Not a `workflow-controller` change and no other
known defect is bundled — see the plan's §2 non-goals.

## Current checkpoint

**CP1 complete** (3 checkpoints total). Next: **CP2** (author and compose
the `2.5.1` release; sync normative docs to the widened grammar; derive and
write `README.md`'s final `2.5.1` Status row).

CP1 delivered, in `migration/overlays/2.5.1/payload/scripts/` (this
milestone's own first-ever copy of both files, layered onto `2.5.0`'s own
overlay copy the same way `2.5.0`'s copy layered onto `2.4.0`'s):

- `workflow_state.py`: widened `_CHECKPOINT_ANCHOR_RE` and
  `_ANCHOR_COMPATIBLE_CHECKPOINT_ID_RE` from `CP<digits>` to `CP<digits>`
  optionally followed by exactly one uppercase letter (`CP\d+[A-Z]?`),
  changing the anchor **tag** grammar and the anchor **id-shape** grammar
  together so they never diverge. `parse_checkpoint_anchor_spans`'s own
  `"CP" + match.group(2)` reassembly line is unchanged — group 2 now simply
  captures `"4B"` for `CP4B` exactly as it already captured `"1"` for
  `CP1`. Updated every docstring/comment/exception message that spells out
  the old `'CP<digits>'` shape as prose:
  `AmendmentCheckpointIdShapeError`'s own docstring, the
  `_CHECKPOINT_ANCHOR_RE`/`_ANCHOR_COMPATIBLE_CHECKPOINT_ID_RE` block
  comment, `checkpoint_id_supports_anchor`'s docstring,
  `validate_post_anchor_coverage`'s docstring and its own
  `AmendmentCheckpointIdShapeError` message text, and
  `request_plan_amendment`'s docstring, inline comment, and its own
  `AmendmentCheckpointIdShapeError` message text — all now read
  `'CP<digits>[A-Z]?'` (or the equivalent prose) together, so no comment is
  ever momentarily stale.
- `workflow_state_test.py`: `TestCheckpointIdSupportsAnchor` gained a
  legacy-shaped-set case (the full user-supplied `CP1`..`CP9` plus
  `CP4B`/`CP6B` set, every id `True`) and four new malformed-shape
  fail-closed cases (`CP4b` lowercase, `CP4BC` two-letter, `CPB4`
  letter-before-digit, `CP4B1` letter-then-digit, each `False`) — the
  pre-existing `WF4a-i`/`"CP1\n"` pins are left untouched, re-asserted
  unchanged. `TestCheckpointAnchorSpans`/`TestCheckpointContentHash` each
  gained a `CP4B` case proving anchor recognition and content hashing work
  identically for a lettered id. `TestValidatePostAnchorCoverage` gained a
  full-legacy-set coverage-passes case. `TestRequestPlanAmendment` gained a
  case proving the full legacy set no longer raises
  `AmendmentCheckpointIdShapeError`, and a case proving the four new
  malformed shapes still do. A new `TestCheckpointIdAnchorTagShapeCoupling
  Invariant` class (`LOCAL_MODEL_PLAN_REVIEW` round 1, optional finding
  OPT-2) asserts, for an enumerated candidate corpus (the legacy set, every
  malformed case, plus `CP0`/`CP04A`/`CP12Z`/`CP999A`/`CP4-B`/`CP4_B`/
  `cp4`/`CPB`), that `checkpoint_id_supports_anchor` and a literal anchor
  tag built from the same id always agree.

Narrowest relevant check: `PYTHONPATH` pointing at the `2.5.1` overlay's
`scripts/` dir plus the unmodified `2.5.0` base `scripts/` dir
(`workflow_fingerprint.py` is not itself overlaid by this milestone, so it
must resolve from the base) — `python3 -m unittest
workflow_state_test.TestCheckpointIdSupportsAnchor
workflow_state_test.TestCheckpointAnchorSpans
workflow_state_test.TestValidatePostAnchorCoverage
workflow_state_test.TestRequestPlanAmendment
workflow_state_test.TestApplyPlanApprovalAmendmentBranch
workflow_state_test.TestCheckpointContentHash
workflow_state_test.TestCheckpointIdAnchorTagShapeCouplingInvariant -v`:
54/54 pass. A full `workflow_state_test.py` run under the same `PYTHONPATH`:
839/850 pass; the 11 failures are all structural path-resolution errors
from real-corpus/live-state tests that expect this file to live inside a
fully composed release tree (`docs/ai-workflow/...` under the same payload
root) — 3 of them
(`TestCanonicalStateSerialization`'s two live-state tests,
`TestGlobalLockOrderItem372h.setUpClass`) reproduce identically against
`2.5.0`'s own overlay copy run the same way, confirmed by a side-by-side
run; the other 8 fail only because CP2, not CP1, is the checkpoint that
populates `migration/overlays/2.5.1/payload/docs/`. None of the 11 touches
the anchor-grammar code this checkpoint changed.

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_2_5_1_CHECKPOINT_ID_COMPATIBILITY_PLAN.md`
(revision 5, plan approval `CURRENT`, both `LOCAL_MODEL_PLAN_REVIEW` (round
5) and `MANUAL_EXTERNAL_PLAN_REVIEW` (round 1) recorded `APPROVE`).

## Next action

**CP2** — author `migration/overlays/2.5.1/classification.json`
(`base_workflow_version: "2.5.0"`, one `replaced` rule apiece for
`scripts/workflow_state.py`, `scripts/workflow_state_test.py`, and each
normative document the plan's §4 names); apply §4's documentation-site
edits inside the overlay payload
(`docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s `D-Plan-Amendment-4` section,
`MILESTONE_WORKFLOW.md`, `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`,
`.claude/commands/request-plan-amendment.md`), preserving the
non-matching-placeholder (`CPn`/`CP<n>`) convention throughout; run `python3
tools/build_release.py --overlay migration/overlays/2.5.1` then `--check`
to compose and verify `distribution/workflow/2.5.1/`; add the `2.5.1`
`CI_SUITES` entry to `tests/support.py` and the required, empty
`by_version["2.5.1"]` entry to `migration/portability_exceptions.json`; add
`TestBootstrappedRepositorySatisfiesTheFrozenSuite251` and the
`TestReadmeStatusTableMatchesCiSuites` `2.5.1` pin; then derive and write
`README.md`'s final `2.5.1` Status-row values from that checkpoint's own
full, non-`--fast` `tests/run_all.py` run.

## Functional review checklist

Not yet applicable — the milestone is still in `IMPLEMENTING`. A functional
checklist is prepared once the implementation stage reaches
`AWAITING_FUNCTIONAL_REVIEW`.
