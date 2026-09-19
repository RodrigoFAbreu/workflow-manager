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

**CP3 complete** (3 of 3 checkpoints -- all checkpoints complete; the
milestone is now ready for `SELF_REVIEWING_IMPLEMENTATION`).

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
  11 suites green, ~1300s total): total tests `1681`
  (`sum(CI_SUITES["2.5.1"].values())`), new cases `12`
  (`workflow_state_test.py`'s `853 - 841`, `workflow_integration_test.py`
  unchanged), `1681 of 1681` passing (zero portability exceptions). Wrote
  the `## Status` table's `2.5.1` row and the matching
  `tools/build_release.py --overlay migration/overlays/2.5.1`/`--check`
  command pair in the rebuild-commands section.

Narrowest relevant check: build + `--check` (byte-for-byte reproduction
confirmed); `TestBootstrappedRepositorySatisfiesTheFrozenSuite251` (6/6) and
`TestReadmeStatusTableMatchesCiSuites` (4/4) run directly; the two
discretionary `...251` conformance-fixture classes (9/9) run directly; the
full, non-`--fast` `tests/run_all.py` run all 11 suites depend on: green,
exit code 0.

CP3 delivered (verification-only checkpoint -- no implementation artifact
was written or re-pinned):

- `python3 tests/run_all.py --fast`: all 8 fast suites green.
- `python3 tests/run_all.py` (full, non-`--fast`): all 11 suites green, exit
  code 0 -- `test_conformance_suite.py` (874.6s) and `test_bootstrap_e2e.py`
  (433.4s, which runs `TestBootstrappedRepositorySatisfiesTheFrozenSuite251`)
  both passed outright, confirming the clean-target failure set equals the
  documented `2.5.1` exceptions (empty) -- no more, no fewer.
- `git diff ce0f221b39467a8dd8417c9ea8818a14ada1bed8 -- distribution/workflow/2.5.0/`:
  empty, both before and after the full regression run -- `2.5.0`'s own
  byte content is provably unchanged by this milestone.
- `python3 tools/build_release.py --overlay migration/overlays/2.5.1 --check`:
  re-run against the final tree -- `distribution/workflow/2.5.1/` reproduces
  exactly from the `2.5.0` base plus the `2.5.1` overlay alone.
- Read-back verification of `README.md`'s `2.5.1` Status row (CP2's own
  deliverable; not re-written or re-pinned here): `7/7 suites, 1681 tests`
  matches `CI_SUITES["2.5.1"]` exactly (7 suites, `sum(...) == 1681`); the
  `1681 of 1681` bootstrapped-repository figure matches
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite251`'s own pass total,
  confirmed by this checkpoint's own independent full regression run above
  (its `test_failures_are_exactly_the_documented_exceptions` and
  `test_every_suite_runs_the_frozen_number_of_tests` both passed, so every
  one of the 1681 `2.5.1`-suite tests run inside the bootstrapped repository
  passed). No disagreement found; nothing to hand back to CP2.

Narrowest relevant check for CP3: the checkpoint's own deliverable *is* the
full regression above, run directly; `git diff` and `build_release --check`
run directly; README read-back checked by inspection against the same run's
own results.

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_2_5_1_CHECKPOINT_ID_COMPATIBILITY_PLAN.md`
(revision 5, plan approval `CURRENT`, both `LOCAL_MODEL_PLAN_REVIEW` (round
5) and `MANUAL_EXTERNAL_PLAN_REVIEW` (round 1) recorded `APPROVE`).

## Next action

External implementation review approved with no further findings;
`/approve-review implementation` recorded `technical_approval` as `CURRENT`
(`implementation_revision: 2`). The work item is now at
`AWAITING_FUNCTIONAL_REVIEW`, a hard gate.

Next: manual functional testing per the checklist below. Findings go to
`.ai-review/feedback/FUNCTIONAL_REVIEW.md`; `/apply-functional-review`
classifies and routes each one (its bounded branch for a same-scope fix,
its broad branch for new or wider scope). Once testing is clean,
`/accept-milestone` is the only acceptance command, and it requires every
checkpoint in
`docs/ai-workflow/registry/workflow-2-5-1-checkpoint-id-compatibility-registry.json`
to be `COMPLETE` (all 3 — CP1/CP2/CP3 — already are).

## Functional review checklist

All testing below happens against **disposable, throwaway repositories**
only — never `~/Workspace/repflow-android` (frozen, read-only; read it via
`git show <tag>:<path>` if needed) and never `~/Workspace/workflow-controller`
(the out-of-scope, real-world repository that motivated this milestone; it
must not be touched or read during this review, even though it is the
concrete reason the fix exists). This repository's own root
`scripts/workflow_state.py` deliberately stays on the unwidened `2.5.0`
grammar — this milestone does not self-upgrade this repository — so every
flow below drives a disposable target repository bootstrapped onto the new
`2.5.1` release, never this repository's own live work items.

### Setup

1. Run the fast regression suite from this repository's own root (a few
   seconds, all green): `python3 tests/run_all.py --fast`. This exercises
   this release's own new test classes at the fast-suite level before any
   manual driving begins.
2. Confirm the new release still reproduces and the `2.5.0` base is
   untouched:
   ```
   python3 tools/build_release.py --overlay migration/overlays/2.5.1 --check
   git diff ce0f221b39467a8dd8417c9ea8818a14ada1bed8 -- distribution/workflow/2.5.0/
   ```
   The second command must print nothing.
3. Create a scratch directory outside this repo, e.g. `/tmp/wf-251-check/`.
4. Bootstrap a disposable target repo directly on `2.5.1`:
   ```
   mkdir -p /tmp/wf-251-check/repo-a
   git -C /tmp/wf-251-check/repo-a init -q -b main
   git -C /tmp/wf-251-check/repo-a config user.email "check@example.invalid"
   git -C /tmp/wf-251-check/repo-a config user.name "Functional Check"
   git -C /tmp/wf-251-check/repo-a config commit.gpgsign false
   PYTHONPATH=src python3 -m workflow_manager --release-version 2.5.1 bootstrap /tmp/wf-251-check/repo-a
   git -C /tmp/wf-251-check/repo-a add -A
   git -C /tmp/wf-251-check/repo-a commit -q -m "baseline: bootstrap workflow 2.5.1"
   ```
5. Bootstrap a second disposable target repo on `2.5.0`, to exercise the
   update path in Flow 6:
   ```
   mkdir -p /tmp/wf-251-check/repo-b
   git -C /tmp/wf-251-check/repo-b init -q -b main
   git -C /tmp/wf-251-check/repo-b config user.email "check@example.invalid"
   git -C /tmp/wf-251-check/repo-b config user.name "Functional Check"
   git -C /tmp/wf-251-check/repo-b config commit.gpgsign false
   PYTHONPATH=src python3 -m workflow_manager --release-version 2.5.0 bootstrap /tmp/wf-251-check/repo-b
   git -C /tmp/wf-251-check/repo-b add -A
   git -C /tmp/wf-251-check/repo-b commit -q -m "baseline: bootstrap workflow 2.5.0"
   ```

### Test data

No product/feature content is needed — the mechanism under test is the
plan-amendment anchor-compatibility grammar itself. Each flow drives a
synthetic `"2.1"`-governed `process`-type work item (e.g.
`cp251-check-1`) through checkpoints inside a disposable repo, using
`src/workflow_manager/fixture.py`'s
`drive_synthetic_work_item_through_checkpoints` with a custom
`checkpoint_ids` tuple that reproduces the user-supplied legacy example set
(`CP1 CP2 CP3 CP4 CP4B CP5 CP6 CP6B CP7 CP8 CP9`) — the exact
inserted-checkpoint lettering convention `workflow-controller-generation-1`
actually carries — or, for at least one flow, the repo's own installed
`/request-plan-amendment` slash command directly against a hand-edited plan
document, closer to a real operator's experience.

### Flow 1 — legacy letter-suffixed ids are accepted, end to end

1. In `repo-a`, drive `cp251-check-1` to `IMPLEMENTING` with
   `checkpoint_ids=("CP1","CP2","CP3","CP4","CP4B","CP5","CP6","CP6B","CP7","CP8","CP9")`
   and `complete_checkpoint_ids` a prefix leaving at least one checkpoint
   open (e.g. every id through `CP8`).
2. By hand, add a well-formed `<!-- CP4B --> ... <!-- /CP4B -->` (and
   `CP6B`) anchor pair for each lettered checkpoint's own design prose to
   the plan document `repo-a` bootstrapped the work item against. This is
   always required, not conditional on the fixture driver's own behavior:
   `src/workflow_manager/fixture.py`'s
   `drive_synthetic_work_item_through_checkpoints` builds its plan text via
   `render_registry_markdown`, which never writes anchor comments.
   **Note:** because step 1 already drove the item to `IMPLEMENTING` —
   approving and committing the plan before this hand-edit exists —
   this anchor pair never enters the *pre*-amendment snapshot
   `load_pre_amendment_snapshot` reads later (it resolves pre-side
   plan/registry content from blobs pinned in
   `amendment_history[-1]["superseded_plan_approval"]["review_content_manifest"]`,
   cross-checked against `pre_amendment_approval_commit`, never from the
   working tree — `scripts/workflow_state.py`'s `load_pre_amendment_snapshot`
   function, ~line 1803). See step 6's expected result, which accounts for
   this.
3. Run `/request-plan-amendment cp251-check-1` (user-only; supply the exact
   confirmation text and a non-empty reason it asks for).
4. **Expected:** the command succeeds — no `AmendmentCheckpointIdShapeError`
   for `CP4B`/`CP6B` — and phase transitions to `AMENDING_PLAN`. **Prior
   Workflow `2.5.0` behavior would have refused this at this exact step**,
   naming `CP4B`/`CP6B`, before ever superseding `plan_approval`.
5. Take the amendment through `/milestone-plan` → `/review-plan` →
   `/record-manual-plan-review` → `/approve-review plan`, preserving every
   lettered id's own anchor pair unchanged in the amended plan text.
6. **Expected:** `apply_plan_approval`'s post-side check
   (`validate_post_anchor_coverage`) passes for every lettered id — no
   `AmendmentCheckpointIdShapeError` and no `AmendmentAnchorCoverageError`.
   Because the pre-amendment plan text committed in step 1 predates step
   2's hand-added anchors, `reconcile_checkpoints_after_amendment` reports
   every shared checkpoint id — lettered ones included — as
   `needs_revalidation`, not `retained`: the same conservative outcome an
   entirely un-anchored *numeric* plan gets under this same setup (this
   repository's own `tests/test_amendment_update_path.py`, ~lines 306-307,
   asserts exactly that for the legacy un-anchored shape). The point this
   step confirms is that lettered ids reconcile through the exact same
   mechanism as numeric ones, with the exact same outcome — never a
   special-cased rejection tied to the letter suffix itself.
7. Run `/milestone-implement` to resume; confirm the remaining checkpoints
   (lettered ones included, and any flipped to `needs_revalidation` by step
   6) implement and complete normally.

### Flow 2 — malformed shapes still fail closed

Using a second synthetic work item (or a fresh disposable repo bootstrapped
the same way), confirm each of these is **still refused** exactly as it was
before this milestone, naming the offending id:

1. A registry/plan carrying `CP4b` (lowercase letter) — refused.
2. A registry/plan carrying `CP4BC` (two-letter suffix) — refused.
3. A registry/plan carrying `CPB4` (letter before digits) — refused.
4. A registry/plan carrying `CP4B1` (letter then more digits) — refused.
5. A registry/plan carrying a non-`CP`-prefixed id, e.g. `WF4a-i` (this
   repository's own `workflow-v2-1-core` convention) — refused, unchanged.
6. A malformed id introduced only by the amendment itself, not present in
   the original registry/plan: drive a synthetic work item to
   `IMPLEMENTING` with an ordinary well-formed checkpoint set, run
   `/request-plan-amendment`, then write an amended registry/plan that adds
   a malformed id such as `CP4b` (absent from the pre-amendment set) and
   run `/approve-review plan`. This exercises `validate_post_anchor_
   coverage`'s post-side refusal for an id introduced by the amendment
   itself — the surface added by this milestone's own most recent fix
   (commit `b04de5e`, finding I2). — refused with
   `AmendmentCheckpointIdShapeError`; confirm it is specifically that error,
   not the unrelated `AmendmentAnchorCoverageError`.

**Expected:** every case above raises `AmendmentCheckpointIdShapeError`
(from `request_plan_amendment`'s early precondition, or from
`validate_post_anchor_coverage` if the malformed id is introduced only by
the amendment itself) — the widening must not have loosened any of these.

### Flow 3 — purely numeric ids are unaffected

1. Drive a third synthetic work item through the ordinary
   `CP1`/`CP2`/`CP3` shape used elsewhere in this repository's own history,
   through an amendment (`/request-plan-amendment` → re-plan → review →
   approve).
2. **Expected:** behaves identically to `2.5.0` — no observable difference
   in accept/refuse behavior, reconciliation outcomes, or anchor parsing
   for numeric-only ids.

### Flow 4 — anchor tag and id-shape grammar stay coupled

1. In a plan document, add a stray `<!-- CPabc -->` (a shape the grammar
   was never widened to admit) somewhere in prose unrelated to any
   checkpoint id.
2. **Expected:** it is not recognized as an anchor tag at all (safe,
   `_CHECKPOINT_ANCHOR_RE` simply does not match it) — confirms the
   widening did not also start accepting tag shapes it has no matching
   id-shape counterpart for.

### Flow 5 — documentation sync

Grep the bootstrapped `repo-a`'s installed copies of
`docs/ai-workflow/WORKFLOW_V2_PLAN.md` (`D-Plan-Amendment-4`),
`docs/ai-workflow/MILESTONE_WORKFLOW.md`,
`docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, and
`.claude/commands/request-plan-amendment.md`. **Expected:** every site that
describes the anchor-compatible checkpoint-id shape states
`CP<digits>[A-Z]?` (not the old `CP<digits>`), and no site illustrates it
with a concrete, letter-suffixed, anchor-shaped literal tag (e.g. an actual
`<!-- CP4B -->` used as a grammar example) — only the non-matching
`CPn`/`CP<n>` placeholder convention.

### Flow 6 — update path (disposable repos only)

1. In `repo-b` (bootstrapped on `2.5.0` above), drive one synthetic work
   item to `IMPLEMENTING` with a registry that already contains a lettered
   id such as `CP4B` (legal under `2.5.0` too — `D-Registry` never
   constrained checkpoint-id shape; only the amendment mechanism did).
2. Run
   `PYTHONPATH=src python3 -m workflow_manager --release-version 2.5.1 update /tmp/wf-251-check/repo-b`.
3. **Expected:** the existing work item's state, approvals, and checkpoint
   history survive the update untouched, and `/request-plan-amendment`
   against it now succeeds where it would have refused under the
   still-installed `2.5.0` grammar.

### Flow 7 — release-inventory sanity

1. `python3 tools/build_release.py --overlay migration/overlays/2.5.1 --check`
   (already run in Setup) must still pass.
2. `README.md`'s `## Status` table `2.5.1` row: confirm the suite count and
   total-tests figures it states match `tests/support.py`'s
   `CI_SUITES["2.5.1"]` (`sum(...) == 1681`) and the rebuild command pair
   listed alongside it actually reproduces the release.

### Known limitations / out of scope

- This repository's own root `scripts/workflow_state.py` intentionally
  stays on the unwidened `2.5.0` grammar — this milestone never
  self-upgrades this repository, only produces the `2.5.1` release for
  downstream targets to adopt.
- `~/Workspace/workflow-controller` (the real repository that motivated
  this fix) must never be touched or read during this testing — every flow
  above uses a disposable, synthetic work item instead.
- Widening beyond exactly one trailing uppercase letter (multi-letter,
  lowercase, letter-before-digit, letter-then-digit) is deliberately out of
  scope — Flow 2 exists to confirm those shapes still fail closed, not to
  request they be admitted.
- The downgrade hazard `CLAUDE.md`'s downgrade-posture paragraph documents
  (commit `1ebd758`) — a repository with a letter-suffixed-id work item in
  `AMENDING_PLAN`, downgraded to Workflow `≤2.5.0`, wedges with no in-band
  exit, since `2.5.0`'s `validate_post_anchor_coverage` raises
  `AmendmentCheckpointIdShapeError` for ids like `CP4B` — is out of scope
  for this manual pass. A full downgrade-and-wedge rehearsal is heavier
  than the flows above, and this is process-tooling functional review, not
  exhaustive regression; the hazard itself, and its lack of an in-band
  escape, is already documented at the `CLAUDE.md` downgrade-posture level,
  not a gap in this milestone's own forward-direction widening.
- `docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`
  and `docs/defects/v2.4.0-003-amendment-diff-anchored-at-head-is-always-empty.md`
  are prior, unrelated, already-untracked residue — do not re-raise them as
  findings against this milestone.
