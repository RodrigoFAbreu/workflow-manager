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

**CP2 complete** (3 checkpoints total). Next: **CP3** (full regression,
release-composition parity checks, and read-back verification of
`README.md`'s `2.5.1` Status row).

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

CP2 delivered:

- `migration/overlays/2.5.1/classification.json`
  (`base_workflow_version: "2.5.0"`), one `replaced` rule apiece for
  `scripts/workflow_state.py`, `scripts/workflow_state_test.py` (both
  already delivered by CP1), and the four normative documents below.
- Documentation sync, inside the overlay payload only (the live
  `docs/ai-workflow/`/`scripts/` trees at this repository's own root stay
  on the installed `2.5.0` content; only `migration/overlays/2.5.1/
  payload/` changed): `docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s
  `D-Plan-Amendment-4` section now states explicitly that its own `<n>`
  anchor placeholder denotes the widened `CP<digits>[A-Z]?` shape;
  `MILESTONE_WORKFLOW.md`'s two sites (the `/request-plan-amendment`
  entry-condition description and the post-anchor-coverage description
  under `AMENDING_PLAN`/plan-approval) and `WORKFLOW_V2_1_OPERATOR_
  REFERENCE.md`'s three sites (`/request-plan-amendment`'s own Expects/
  Next/Refuses entries) both widened from `CP<digits>` to
  `CP<digits>[A-Z]?`; `.claude/commands/request-plan-amendment.md`'s own
  documented shape precondition and anchor-tag format widened the same
  way. Every edited site keeps the non-matching-placeholder convention
  (`CPn`/`CP<n>`) — confirmed by grepping every edited file for a
  concrete, letter-suffixed, anchor-shaped tag (`<!-- CP[0-9]+[A-Z] -->`):
  zero matches.
- `python3 tools/build_release.py --overlay migration/overlays/2.5.1` then
  `--check`: composed `distribution/workflow/2.5.1/` (63 artifacts, 6
  templates, 6 `overlay_replaced`, 0 `overlay_added`) and confirmed
  byte-for-byte reproduction from the `2.5.0` base plus this overlay
  alone. `git diff <base_commit> -- distribution/workflow/2.5.0/` stays
  empty — the `2.5.0` base is untouched.
- `tests/support.py` gained `CI_SUITES["2.5.1"]` (only
  `workflow_state_test.py`'s count moves, `841` → `852`, `+11`; every
  other suite's count is byte-identical to `2.5.0`'s own row, since no
  other file changed). `migration/portability_exceptions.json` gained the
  required, empty `by_version["2.5.1"]` entry.
- `tests/test_bootstrap_e2e.py` gained
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite251` (required
  deliverable): 6/6 tests pass against a real `install.bootstrap`-produced
  `2.5.1` repository — this is the milestone's own bootstrapped-repository
  pass count.
- `tests/test_internal_references.py`'s `TestReadmeStatusTableMatchesCiSuites`
  gained the `2.5.1` pin (`_README_2_5_1_ROW_RE` +
  `test_2_5_1_row_matches_ci_suites`, required deliverable): 4/4 tests in
  that class pass, including the new one.
- **Discretionary `tests/test_conformance_suite.py` siblings (recorded
  explicitly, per the plan's own instruction, rather than silently matching
  or silently diverging from `2.5.0`'s own count)**: added
  `TestConformanceFixture251` and `TestBootstrappedTarget251`, mirroring
  `...250` exactly — both ran green (9/9 tests combined, ~219s, including
  the acceptance matrix twice). Declined `TestPortabilityExceptions251
  RequiredEmptyEntry`: `...250`'s own version of this class exists to
  narrate a specific, one-time fact (CP9's fix of `v2.3.1-001`, and that
  `2.3.1`'s/`2.4.0`'s own entries are byte-unchanged by that fix) that has
  no `2.5.1` analogue — `2.5.1` introduces no comparable fix and changes no
  earlier release's own exception entry, so a `2.5.1` sibling would only
  re-assert `expected_portability_exceptions("2.5.1") == {}`, already
  proven live by `TestBootstrappedTarget251`/`TestConformanceFixture251`'s
  own portability-exception assertions and by
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite251`'s
  `test_failures_are_exactly_the_documented_exceptions` above, with no
  narrative left to add.
- Derived `README.md`'s final `2.5.1` Status-row values from this
  checkpoint's own full, non-`--fast` `python3 tests/run_all.py` run (all
  11 suites green, ~1300s total): total tests `1680`
  (`sum(CI_SUITES["2.5.1"].values())`), new cases `11`
  (`workflow_state_test.py`'s `852 - 841`, `workflow_integration_test.py`
  unchanged), `1680 of 1680` passing (zero portability exceptions). Wrote
  the `## Status` table's `2.5.1` row and the matching
  `tools/build_release.py --overlay migration/overlays/2.5.1`/`--check`
  command pair in the rebuild-commands section.

Narrowest relevant check: build + `--check` (byte-for-byte reproduction
confirmed); `TestBootstrappedRepositorySatisfiesTheFrozenSuite251` (6/6) and
`TestReadmeStatusTableMatchesCiSuites` (4/4) run directly; the two
discretionary `...251` conformance-fixture classes (9/9) run directly; the
full, non-`--fast` `tests/run_all.py` run all 11 suites depend on: green,
exit code 0.

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_2_5_1_CHECKPOINT_ID_COMPATIBILITY_PLAN.md`
(revision 5, plan approval `CURRENT`, both `LOCAL_MODEL_PLAN_REVIEW` (round
5) and `MANUAL_EXTERNAL_PLAN_REVIEW` (round 1) recorded `APPROVE`).

## Next action

**CP3** — full regression (`python3 tests/run_all.py`, both `--fast` and
the full, non-`--fast` run) must be green, and the clean-target failure set
(`migration/portability_exceptions.json`) must equal the documented
exceptions for `2.5.1` (empty) — no more, no fewer; confirm
`distribution/workflow/2.5.0/`'s own byte content is provably unchanged by
this milestone (`git diff <base_commit> -- distribution/workflow/2.5.0/`
empty); re-run `tools/build_release.py --overlay migration/overlays/2.5.1
--check` once more against the final tree; and read back (never rewrite)
`README.md`'s `2.5.1` Status row, confirming its suite/test counts equal
`CI_SUITES["2.5.1"]` and its bootstrapped-repository count equals
`TestBootstrappedRepositorySatisfiesTheFrozenSuite251`'s own pass total,
both checked against this checkpoint's own independent full regression
run.

## Functional review checklist

Not yet applicable — the milestone is still in `IMPLEMENTING`. A functional
checklist is prepared once the implementation stage reaches
`AWAITING_FUNCTIONAL_REVIEW`.
