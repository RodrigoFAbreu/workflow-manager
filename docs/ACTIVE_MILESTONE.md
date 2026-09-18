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

**CP1-CP13 complete** (`implementation-review-two-stage`, 13 checkpoints
total -- every registry checkpoint is now `COMPLETE`). `complete_checkpoint`
therefore moved `phase` from `IMPLEMENTING` to
`SELF_REVIEWING_IMPLEMENTATION` in the same write that completed CP13. The
full-milestone self-review has now run (below); the implementation-review
bundle is generated from its result.

### `SELF_REVIEWING_IMPLEMENTATION` -- full-milestone self-review

Reviewed the complete `38114204..HEAD` diff (128 files). Four findings, one
important, three minor; all four fixed, nothing left open. The authored
surface was read directly (`migration/overlays/2.5.0/payload/`,
`migration/`, `tests/`, this repository's own docs), never only the
generated `distribution/workflow/2.5.0/` copies.

1. **Important -- the shipped ledger key diverged from the approved plan.**
   `implementation_review_stages`' local-stage key was implemented (CP2/CP3)
   as `LOCAL_IMPLEMENTATION_REVIEW`, but the approved plan's own "Durable
   stage ledger" block (revision 41, §2.1) declares it
   `LOCAL_MODEL_IMPLEMENTATION_REVIEW`, and so do the release's own
   normative documents: `WORKFLOW_V2_PLAN.md`'s `D-Implementation-Review-Stages`
   (both the ledger-shape declaration and the
   `technical_approval_gate_reachable` widening), `MILESTONE_WORKFLOW.md`,
   and `REVIEW_PROTOCOL.md`. The plan never uses the short form for
   anything but the *phase* name `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`.
   The result was two names for one stage: every normative document
   described a persisted key the code never wrote, and
   `review-implementation.md` carried a parenthetical
   ("recorded under the ledger's own canonical key, ...") whose only job was
   to reconcile them. It is also an asymmetry the rest of the protocol does
   not have -- on the plan side `LOCAL_MODEL_PLAN_REVIEW` is both the ledger
   key and the `Reviewer role:` string, and on the implementation side
   `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` is both, with
   `validate_manual_implementation_review_preconditions` comparing the role
   against the constant directly. **Fixed** by renaming the constant --
   identifier and value alike -- to `LOCAL_MODEL_IMPLEMENTATION_REVIEW`
   across the overlay payload (`workflow_state.py`, `workflow_state_test.py`,
   `review-implementation.md`, `record-manual-implementation-review.md`,
   `approve-review.md`, `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`), plus this
   repository's own `tests/test_implementation_review_two_stage_disposable_repo.py`
   and this item's requirements ledger; the reconciling parenthetical is
   replaced by a statement that the two are deliberately one name, and the
   constant's own comment block records the rule. Every normative document's
   existing text is now correct as written -- none needed editing. Safe as a
   pure rename: `"2.2"` is not activated anywhere, no repository has ever
   installed `2.5.0`, and no live `WORKFLOW_STATE.json` in any repository
   holds an `implementation_review_stages` ledger, so nothing persisted
   migrates. The frozen suite's own `_GOLDEN_COMMAND_FILE_SHA256` roster
   (overlay `workflow_integration_test.py`) caught the two roster command
   files the rename touched, `approve-review.md` and
   `review-implementation.md`; both recorded hashes are updated in place with
   a comment stating why, exactly as every prior intentional command-file
   change in that table does. The two other command files the rename touched
   (`record-manual-implementation-review.md`,
   `WORKFLOW_V2_1_OPERATOR_REFERENCE.md` is not a command) are not roster
   members -- that roster is the frozen upstream list, and neither `2.4.0`
   nor `2.5.0` extends it.
2. **Minor** -- `mark_missing_units_current` (overlay `workflow_state.py`,
   CP6) computed a local `newline` that nothing used. The inserted marker
   block is already correct for both cases the dead expression was testing
   for, since its own leading `"\n"` terminates the heading line; replaced
   with a comment saying so.
3. **Minor** -- `find_governing_version_occurrences` (same file, CP6) opened
   with a function-local `import os as _os` although the module already
   imports `os` at the top. Removed.
4. **Minor** -- `tests/test_conformance_suite.py`'s `_overlay_payload_roots`
   docstring still read "today just `2.4.0`" after CP11 added the `2.5.0`
   overlay directory the same function now discovers.

`distribution/workflow/2.5.0/` is regenerated from the amended overlay
(`python3 tools/build_release.py --overlay migration/overlays/2.5.0`), so
`manifest.json`'s `provenance.overlay_commit` moves to this rebuild's own
build-time HEAD. Counts are unchanged: 63 artifacts, 6 templates,
`overlay_replaced` 25, `overlay_added` 2.

**One process observation, recorded and not retroactively rewritten.**
`/milestone-implement` step 1e names the requirements ledger
(`docs/ai-workflow/requirements/implementation-review-two-stage-ledger.md`,
`WF4b`) as the narrative record for a *process* work item, which this is.
CP1-CP4 appended there; CP5-CP13 appended their per-checkpoint record to
this file instead. No narrative was lost -- this document carries all nine
in full -- so the ledger gains one section pointing at them rather than a
duplicate copy that could drift from what was reviewed.

CP13 delivered the full regression and the downgrade posture:

- **`CLAUDE.md`'s "Downgrade posture" paragraph** (plan-stage excluded,
  implementation-stage protected -- both as exact paths) gains `2.5.0`'s own
  vocabulary beside `2.4.0`'s `NEEDS_REVALIDATION`/`SUPERSEDED`: a
  `work_items[...]` entry that has ever held `governing_workflow_version:
  "2.2"`, either of the two new persisted phases
  (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
  `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`), or an
  `implementation_review_stages` ledger, plus the activation-trailer
  direction: `2.5.0`'s version-aware event model reports a
  `Workflow-Rollback: 2.2` repository *activated* (its resolved destination
  is `"2.1"`, not `"1"`), while every pre-`2.5.0`, version-blind
  `is_activated` answers *not activated* on that same unchangeable history
  -- a silent wrong answer, not a refusal, which is why the paragraph names
  it. (`2.5.0`'s own fail-closed miss rule -- an unresolvable
  `Workflow-Rollback` value reports activated -- is stated there too, so the
  posture and `§2.2`'s rule agree without restating the mechanism.)
- **The four previously-deferred defects' final disposition**, written into
  each defect's own `docs/defects/*.md` record and matching `§8` exactly:
  `v2.3.1-001` fixed (CP9), `v2.3.1-003` fixed (CP9), `v2.4.0-001`'s
  implementation-stage symmetry widened (CP9, still not retroactively
  repaired), `v2.4.0-002` reconsidered and still deferred in full (CP10),
  including the optional `IMPL10-O1` mitigation, per `§9`'s resolved
  decision 3. Never into this plan document itself: `§8` already carries the
  disposition in full, and `IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md` is this
  item's own `plan_stage.protected_paths` entry, which no checkpoint writes
  (revision 36, `LOCAL_MODEL_PLAN_REVIEW` round 36, finding B1). These four
  writes are deliberately non-review-bound mirrors of `§8`'s
  already-reviewed text -- `docs/defects/` is `excluded_prefixes` at *both*
  stages, confirmed against this item's own
  `implementation-review-two-stage-artifacts.json` -- so `§8` stays the one
  normative, already-approved disposition and these records are its copy.

  **One of the four is deliberately not staged.**
  `docs/defects/v2.3.1-003-plan-approval-requires-precommitted-state-file.md`
  has been an *untracked* working-tree file since before this milestone
  began -- `§7` names it by path as "prior work this milestone must not
  touch," and CP1-CP12 each left it untracked while committing around it
  (`.ai-review/runtime/WORKTREE_IDENTITY.json`'s own
  `expected_dirty_paths_by_work_item` entry for this item records it as
  expected residue, which is how the dirty-resume rule tolerated it at every
  checkpoint). Its `2.5.0` disposition section is written, and it stays in
  the working tree exactly where it has always been. Adding a file that
  predates the milestone to Git history is not something `CP13`'s registry
  row asks for -- it asks for the disposition to be recorded in the record,
  which it now is -- and it is the one irreversible direction here, so it is
  left for the user to decide. `docs/defects/v2.4.0-003-amendment-diff-
  anchored-at-head-is-always-empty.md` (this milestone's own
  `LOCAL_MODEL_PLAN_REVIEW` round 35 write-up, not one of the four) is
  untracked for the same reason and is likewise untouched.

**Two failures the full regression surfaced, both resolved here** -- one a
genuine shipped defect, one working-tree pollution.
No checkpoint in this milestone recorded a full `tests/run_all.py` run --
every recorded verification was `--fast` or narrower, by design, with the
full-regression obligation assigned to this checkpoint. Run here for the
first time, it failed with two failures in `test_conformance_suite.py`
(`test_bootstrap_e2e.py` and CP12's own disposable-repo suite were green):

- `TestOverlayStateWriterClosure.test_every_overlay_writer_surface_file_declares_state_writer`
  failed on `2.5.0:.claude/commands/review-implementation.md` -- "missing or
  contradictory state_writer declaration (found [])". CP11 had reclassified
  that command's frontmatter from `state_writer: false` to `state_writer:
  conditional -- false for "1"/"2.1" ...; true for a "2.2" item at
  AWAITING_LOCAL_IMPLEMENTATION_REVIEW`. **`conditional` is not in the
  declaration vocabulary.** `discover_state_writers`' closed set is exactly
  `true`/`false`/`"publisher"` (item 357, `WORKFLOW_V2_PLAN.md`'s own
  D-Completion-Obligations text), and a value outside it parses to nothing
  and **fails closed** -- so every `2.5.0` repository's own
  `WFO-STATE-SERIALIZATION` conformance would have returned `FAIL`/
  `UNRESOLVABLE`, and `complete_work_item` with it. Fixed to `state_writer:
  true`, the only admissible member for this file: it really can write
  `WORKFLOW_STATE.json` (so it must be inventoried as a writer, and the
  writer check that a declared writer names `state_transaction`/`state_lock`
  passes), and `false` would be doubly wrong, since the non-writer check
  forbids a declared non-writer from calling `state_transaction(` at all.
  The branch-dependence is not lost -- it is stated in the command's own
  `description:` frontmatter, in a new "Why the frontmatter declares
  `state_writer: true`" paragraph in its body, and in the operator
  reference's `/prepare-review` entry, none of which the machine-read value
  was ever the right place for. Widening the vocabulary instead was rejected
  as an architecture change to a frozen mechanism that would also require
  editing this repository's own *installed* `scripts/workflow_state.py`,
  which is what `tests/test_conformance_suite.py` imports the parser from.
  Sites: the overlay's `review-implementation.md`,
  `workflow_integration_test.py` (the `state_writer: conditional` assertion,
  its `_GOLDEN_COMMAND_FILE_SHA256` entry, and
  `test_the_state_writer_false_claim_matches_the_frontmatter`'s docstring --
  that test's own assertions were already correct and are unchanged), and
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`'s `/prepare-review` entry.
  `distribution/workflow/2.5.0/` rebuilt; `--check` reproduces byte-for-byte.
- `TestAuthoredReleaseOverlayDelta.test_build_release_check_reproduces_2_4_0`
  failed with `extra: payload/scripts/__pycache__/*.pyc`. Not a code defect:
  stale bytecode caches left in `distribution/workflow/2.4.0/payload/scripts/`,
  `distribution/workflow/2.5.0/payload/scripts/` and
  `migration/overlays/2.5.0/payload/scripts/` by earlier checkpoints' own
  verification runs -- CP12's recorded `cd distribution/workflow/2.5.0/
  payload/scripts && python3 workflow_state_test.py` and CP5/CP9/CP12's
  `PYTHONPATH=migration/overlays/2.5.0/payload/scripts` invocations are the
  direct causes. They are gitignored, so they never entered history, but
  `tools/build_release.py --check` walks the filesystem rather than the
  index and counts them as stray files. Removed.
  `tools/build_release.py` itself is deliberately **not** changed to ignore
  them: it is this item's `implementation_stage.protected_paths` entry that
  the plan explicitly declines to modify ("would require unauthorized
  build_release.py changes"). Worth knowing for the next release: any ad hoc
  `python3` run pointed at a payload `scripts/` directory re-creates them and
  re-breaks `--check` until they are cleared.

Verification for CP13 (this checkpoint's own narrowest relevant check *is*
the full regression -- that is its deliverable):
```
python3 tests/run_all.py                                                  # before the two fixes
python3 tools/build_release.py --overlay migration/overlays/2.5.0
python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check
cd tests && python3 -m unittest -v \
  test_conformance_suite.TestAuthoredReleaseOverlayDelta \
  test_conformance_suite.TestOverlayStateWriterClosure \
  test_conformance_suite.TestAuthoredReleaseIsSelfConsistent \
  test_conformance_suite.TestAuthoredReleaseCiTemplateSuiteNames \
  test_conformance_suite.TestPortabilityExceptions250RequiredEmptyEntry
python3 tests/run_all.py                                                  # after
```
Result: the first full run failed with exactly the two failures above --
`test_conformance_suite.py` `FAILED (failures=2)` after 646.8s over 40
tests, with `test_bootstrap_e2e.py` (319.5s) and
`test_implementation_review_two_stage_disposable_repo.py` (11.2s) green.
After both fixes: the release build succeeds and `--check` confirms
byte-for-byte reproduction; the five narrow conformance classes are 11/11
green; and the **full `python3 tests/run_all.py` is green, 11/11 suites,
exit 0** (`test_conformance_suite.py` 639.5s, `test_bootstrap_e2e.py`
319.3s, the disposable-repo suite 11.2s, the eight fast suites ~8s), with no
`__pycache__` re-created under any release tree by the run itself and
`--check` still clean afterwards. This is the first end-to-end green full
regression of the milestone.

CP12 delivered disposable-repository functional validation, in
`tests/test_implementation_review_two_stage_disposable_repo.py` (new;
declared under this item's own `plan_stage.excluded_prefixes['tests/']`/
`implementation_stage.protected_prefixes['tests/']`) plus one execution
evidence file, `docs/ai-workflow/dry-run/cp12-implementation-review-two-
stage-disposable-repo-evidence.md` (plan/implementation-stage excluded, per
`docs/ai-workflow/`'s existing classification):

- **Activation, no repository-internal shortcut** (`LOCAL_MODEL_PLAN_REVIEW`
  round 10, optional finding 1) -- `TestActivationProcedureOnComposedRelease`
  bootstraps a disposable repo directly (`workflow_manager.install.bootstrap`)
  on the real, composed `distribution/workflow/2.5.0/` release and performs
  `IMPLEMENTATION_REVIEW_WORKFLOW.md`'s documented `WORKFLOW_CONFIG.json`
  hand edit verbatim (both fields, one commit, `Workflow-Activation: 2.2`
  trailer) -- never `build_activated_config` (checked separately). Also
  covers the post-activation `ConfigMissingAfterActivationError` hard stop,
  a fail-closed unresolvable `Workflow-Rollback` value, and rollback to
  `"2.1"` (never bare `"1"`).
- **Update-path compatibility** -- `TestUpdatePathLeavesLiveV21ItemUnaffected`
  bootstraps on `2.4.0`, writes a live `"2.1"` item mid-
  `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`, updates to `2.5.0`, and proves
  the state/config are byte-identical afterward and the item is never
  retroactively upgraded even once the repository separately activates
  `"2.2"`.
- **The full two-stage implementation-review protocol**, against a
  disposable repository carrying the real, composed `"2.2"`-aware tooling
  (reusing `workflow_acceptance_matrix_test.py`'s own proven `Scratch`/
  `Item` harness via a minimal `Item22` extension, pointed at
  `distribution/workflow/2.5.0/payload/scripts/`): the plan-stage two-stage
  traversal (`LOCAL_MODEL_PLAN_REVIEW`\`round 5, finding B1's plan-side
  fix, proven end to end); the checkpoint loop through
  `enter_self_reviewing_implementation`/`record_bundle_generation(stage=
  "implementation")`, asserting the **committed** phase at the durability
  commit is `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` (round 6, finding B1's
  second "Missing tests" item); the positive path (local `APPROVE` ->
  manual `APPROVE` -> `/approve-review implementation`); every negative path
  the registry names (local/manual `REVISE`/`BLOCK`, wrong-phase and
  wrong-version refusals, stale `review_content_id`, duplicate manual
  ingestion, advisory-only `bundle_id` mismatch); `/recover-implementation-
  provenance` from each of the three phases a `"2.2"` item can occupy
  between a generation-record commit and technical approval (B1(a)/B2); and
  the `"2.2"` functional-review bounded-fix scenario routing back through
  both implementation-review stages before `/approve-review implementation`
  is reachable again (I2).
- **CP7's generic declaration-coverage helper**, exercised directly against
  this file's own synthetic `"2.2"` item (no second hand-written copy).
- **CP9's four backlog fixes against fresh disposable-repo scenarios**:
  three (mode-100644 fallback, the portable host-note skip, the required
  empty `2.5.0` portability-exceptions entry) are already covered by
  `tests/test_bootstrap_e2e.py`'s own `TestBootstrappedRepositorySatisfiesThe
  FrozenSuite250`, which runs the complete frozen suite against a
  bootstrapped-on-2.5.0 repository; the fourth (the widened
  implementation-stage `.workflow-manager/` exclusion) gets its own new,
  disposable-repo-level proof here.

**A defect this validation found and fixed** (in scope: authored,
unreleased `2.5.0` content, not frozen Workflow semantics -- mirrors CP9's/
CP11's own precedent of a later checkpoint correcting an earlier
checkpoint's gap its own required validation sweep discovers, within the
same protected `migration/` tree): driving the real local-approve-then-
manual-approve-then-`/approve-review implementation` sequence end to end
for the first time (CP3/CP4's own hermetic tests each start from a
hand-built dict-state fixture *after* the ledger write, never one that
carries it through to the following commit) showed that **every `"2.2"`
item's very first technical-approval commit failed outright** --
`MalformedTechnicalApprovalCommitError` -- because `TECHNICAL_APPROVAL_
COMMIT_FIELDS` had not been widened the way its sibling `ORDINARY_
BUNDLE_GENERATION_RECORD_FIELDS`/`RECOVERED_BUNDLE_GENERATION_RECORD_
FIELDS` already were, to admit a `"2.2"` item's uncommitted `implementation_
review_stages` ledger residue (neither `/review-implementation`'s
local-approve write nor `/record-manual-implementation-review`'s
manual-approve write creates its own durability commit; both ride into
whatever commit comes next -- for the ordinary positive path, always
`/approve-review implementation`'s own). This was the mainline path, not an
edge case. Fixed in `migration/overlays/2.5.0/payload/scripts/
workflow_state.py` (`TECHNICAL_APPROVAL_COMMIT_FIELDS` widened, mirroring
the generation-record sets' own identical widening) and
`workflow_state_test.py` (`TestTechnicalApprovalCommitAdmitsImplementation
ReviewStagesResidue`, two tests); `distribution/workflow/2.5.0/` rebuilt
(`python3 tools/build_release.py --overlay migration/overlays/2.5.0`) and
reproduces byte-for-byte (`--check`). `tests/support.py`'s
`CI_SUITES["2.5.0"]["workflow_state_test.py"]` updated `819` -> `821` to
match the two new tests; `tests/run_all.py`'s `SLOW_SUITES` gained this
checkpoint's own new suite.

Verification for CP12 (narrower than the full suite -- CP13 owns the full-
regression obligation):
```
cd tests && python3 test_implementation_review_two_stage_disposable_repo.py -v
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts python3 -m unittest \
  workflow_state_test.TestValidateTechnicalApprovalCommit \
  workflow_state_test.TestTechnicalApprovalCommitAdmitsImplementationReviewStagesResidue -v
python3 tools/build_release.py --overlay migration/overlays/2.5.0
python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check
cd distribution/workflow/2.5.0/payload/scripts && python3 workflow_state_test.py
```
Result: the new disposable-repo suite is 28/28 green (~11s); the two
narrow `workflow_state_test.py` classes are 5/5 green; the release build
succeeds and `--check` confirms byte-for-byte reproduction; the composed
release's own full `workflow_state_test.py` run is 821/821 outright with
only the same 2 pre-existing `TestCanonicalStateSerialization`
dry-run-path-relative errors this invocation shape is already known to
produce outside a real repository root (819 tests, same 2 errors, confirmed
via `git stash` against the pre-fix tree). Full detail and the complete
`-v` transcript: `docs/ai-workflow/dry-run/cp12-implementation-review-two-
stage-disposable-repo-evidence.md`.

CP11 delivered release authoring: `migration/overlays/2.5.0/classification.json`
(25 rules -- 23 `replaced`, 2 `added`) plus the overlay's own payload tree.
`python3 tools/build_release.py --overlay migration/overlays/2.5.0` composes
`distribution/workflow/2.5.0/` from the `2.4.0` base plus the overlay
(63 artifacts, 6 templates, `by_category` `{conformance: 24, distribution:
37, host-evidence: 2}`, `overlay_replaced: 25` -- 23 from this overlay's own
rules plus 2 already-`overlay_delta`-bearing base-2.4.0 artifacts copied
forward unchanged -- `overlay_added: 2`); `--check` confirms
`distribution/workflow/2.5.0/` reproduces byte-for-byte from that same base
plus overlay. `tests/support.py` gains the `2.5.0` `CI_SUITES` entry (its
counts pinned to what the composed overlay payload actually produces).
`migration/portability_exceptions.json`'s required, empty
`by_version["2.5.0"]` entry was already written by CP9 -- confirmed present
and untouched here, correcting revision 3's framing that CP11 itself writes
it.

The release-authoring sweep (`LOCAL_MODEL_PLAN_REVIEW` round 8, finding I2)
found and fixed every payload document CP1-CP10's own widenings left
stale, beyond the two gaps CP9 already flagged as its own out-of-scope
find (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW` missing from the operator
reference's persisted-phase table; `review-plan.md`'s/
`record-manual-plan-review.md`'s `_require_v2_1_plan_review` golden text
still reading the pre-widening `!= "2.1"` literal) -- both now fixed, in
`migration/overlays/2.5.0/payload/`:
- `.claude/commands/apply-functional-review.md`: the `"2.2"` child-item
  driver sequence now names `/review-implementation`'s authoritative role
  and the new `/record-manual-implementation-review` step explicitly,
  rather than describing `/review-implementation` as uniformly optional.
- `.claude/commands/review-plan.md`: prose rewrap only, no content change,
  keeping the paragraph's line-wrap consistent after CP1/CP2's own
  `TWO_STAGE_PLAN_REVIEW_VERSIONS` widening.
- `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`: `/review-implementation`'s
  `state_writer` reclassified `false` -> `conditional` (true only for a
  `"2.2"` item at `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`); the "Enter `X`
  state"/full-sequence-diagram sections widened for the two new `"2.2"`
  implementation-review commands and phases; the command count corrected
  16 -> 17.
- `scripts/workflow_integration_test.py`: golden hashes updated for every
  payload command CP1-CP10 actually changed; the `_require_v2_1_plan_review`
  golden-text assertions and the persisted-phase-table/writer-census/
  state-writer-false/command-count tests all restated to match the fixes
  above, closing both of CP9's flagged gaps.
- `scripts/workflow_state_test.py`: `TestImplementationReviewTwoStageDeclarationCoverage`
  and `DeclarationSymmetryHelperTest`'s two real-corpus methods removed --
  both were self-referential to this exact repository at a hardcoded
  commit SHA and could never pass once installed into any other target
  repository via the general release payload (CP12's disposable-repository
  validation exercises the same generic helper against a synthetic work
  item instead).
- `scripts/workflow_state_completion_obligations_test.py` (new overlay
  copy): `TestNeverPersistedPhaseVocabulary`'s AST-derivation helper
  widened with a third shape -- `work_item["phase"] = some_resolver(...)`,
  resolved by walking the called function's own `return` statements --
  so `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` (reachable only through
  `record_bundle_generation`'s call to `bundle_generation_target_phase`)
  and `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` both count as
  persisted, widening `PERSISTED` from thirteen to fifteen phases.
- `tests/test_conformance_suite.py`/`tests/test_bootstrap_e2e.py` (this
  repository's own suites, not the overlay payload): `TestConformanceFixture250`,
  `TestBootstrappedTarget250`, and `TestBootstrappedRepositorySatisfiesTheFrozenSuite250`
  added, mirroring their `240` siblings exactly, running the frozen suite
  and a real bootstrap-and-update cycle against `2.5.0` for the first time.

Verification for CP11 (build/check plus the new `2.5.0` test classes --
narrower than the full suite, since CP13 owns the full-regression
obligation):
```
python3 tools/build_release.py --overlay migration/overlays/2.5.0
python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check
PYTHONPATH=tests python3 -m unittest \
  tests.test_conformance_suite.TestConformanceFixture250 \
  tests.test_conformance_suite.TestBootstrappedTarget250 \
  tests.test_bootstrap_e2e.TestBootstrappedRepositorySatisfiesTheFrozenSuite250 -v
python3 tests/run_all.py --fast
```
Result: build succeeds, `--check` confirms byte-for-byte reproduction; all
new `2.5.0` test classes pass outright (`TestConformanceFixture250`: 4/4;
`TestBootstrappedTarget250`: 5/5; `TestBootstrappedRepositorySatisfiesTheFrozenSuite250`:
6/6, ~112s, a real bootstrap-and-CI-suite-and-update cycle against the
composed `2.5.0` release); `tests/run_all.py --fast` is green (8/8 suites).

CP10 delivered the post-v2.3.1 backlog's `v2.4.0-002` reconsideration
(`§2.7` point 4, `§8`, `§9` point 3) -- a written disposition alone, no
code change and no edit to the plan document itself (`IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md`
is this work item's own `plan_stage.protected_paths` entry; its
`review_content_id` is fixed as of the current `plan_approval`, so nothing
this checkpoint does may touch it). The reconsideration's full text
already lives in the approved plan, produced during planning and settled
at `MANUAL_EXTERNAL_PLAN_REVIEW` round 1's required acceptance criterion
4 (plan revision 15, carried unchanged through revision 41's approval this
milestone is executing against): both full structural fixes for
`docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`
(a `claims_dir`-rooted lock; a repo-global phase witness) remain declined,
as concurrency-correctness engineering this milestone's own
review-tooling mission does not undertake; the cheap `IMPL10-O1` partial
mitigation (a second `resolve_claim(...)` re-check immediately before
`request_plan_amendment`'s own supersede) is declined too, deferred
together with both structural fixes, for the same reason the defect
record itself already gave when it first declined this exact option
(round 10, under review pressure, in the same round the residual was
found) -- narrowing one race window without establishing the documented
cross-worktree guarantee adds surface to a critical section in a
review-focused milestone without closing the defect. All four
previously-deferred defects (`§8`) now carry a settled disposition; CP13
copies this one's disposition, verbatim in substance, into the defect's
own `docs/defects/v2.4.0-002-*.md` record (the other three copies land at
CP13 too -- `docs/defects/*.md` is excluded, not protected, at both
plan and implementation stage, so those four writes are deliberately
non-review-bound mirrors of `§8`'s own already-reviewed text, never a
second place its content could diverge from what was reviewed).

Verification for CP10 (no code change; the narrowest relevant check is
confirming the repository's own baseline suite is unaffected):
```
python3 tests/run_all.py --fast
```
Result: unaffected by this checkpoint (no file `run_all.py --fast`
exercises changed). `git status` after this checkpoint's own narrative
update shows only `docs/ai-workflow/WORKFLOW_STATE.json` (checkpoint
bookkeeping) and `docs/ACTIVE_MILESTONE.md` (this section) touched --
`IMPLEMENTATION_REVIEW_TWO_STAGE_PLAN.md` untouched, confirmed by `git
diff --stat` against `HEAD` before committing.

CP9 delivered the post-v2.3.1 backlog's tractable fixes (`§2.7`), in
`migration/overlays/2.5.0/payload/`:

- `scripts/workflow_state.py`: `v2.3.1-003` fixed --
  `pin_plan_approval_state_blob` now falls back to file mode `100644`
  (`_FALLBACK_STATE_BLOB_MODE`) when `_blob_mode_and_sha_at_commit` finds no
  `HEAD` entry for `state_path`, instead of raising
  `PlanApprovalStateBlobUnavailableError` unconditionally -- the first of
  the defect record's own two stated portable forms, adopted verbatim. The
  exception class is retained (documented, no longer raised by this
  function) rather than deleted, since nothing else in this module's
  public contract depends on its removal. `v2.4.0-001` widened further --
  `_implementation_stage_default`'s `excluded_prefixes` now also excludes
  `.workflow-manager/`, symmetric with the plan-stage default the `2.4.0`
  fix already widened (this item's own CP2 had to hand-add the identical
  exclusion to its own declarations file for the same reason). Forward-only:
  no existing work item's already-generated declarations file is edited by
  either change.
- `scripts/workflow_integration_test.py` (new overlay file -- the first
  checkpoint to give this base-2.4.0 payload file its own overlay copy):
  `v2.3.1-001` fixed -- `test_the_historical_status_note_carries_a_dated_correction`
  now looks for the host status note with `next((...), None)` and calls
  `self.skipTest(...)` when it is absent, instead of `next(...)` raising
  `StopIteration`. Verified live: running this exact test, unmodified,
  against this very repository's own `docs/ACTIVE_MILESTONE.md` (which has
  never carried RepFlow's dated note) raises `StopIteration` today: the
  fix resolves a defect this repository is *currently* exposed to, not
  only a hypothetical one. A repository that does carry a malformed note
  (present but not immediately followed by a `**Correction (2026-08-26)**`
  paragraph) still fails exactly as before -- confirmed against a
  synthetic scratch repo. `test_pin_raises_when_state_path_absent_at_head`
  is replaced by `test_pin_defaults_to_mode_100644_when_state_path_absent_at_head`,
  proving the new fallback: the pin succeeds, stages mode `100644`, and the
  staged content matches exactly.
- `migration/portability_exceptions.json`: gains the required, empty
  `by_version["2.5.0"]` entry (`tests/support.py`'s
  `expected_portability_exceptions` subscripts `by_version[workflow_version]`
  unguarded, so an absent key is a `KeyError`, not a pass). `2.3.1`'s and
  `2.4.0`'s own entries for this same test are untouched -- both releases'
  payloads still carry the unfixed test, and `2.3.1` is frozen.
- `tests/test_conformance_suite.py` (this repository's own suite, not the
  overlay payload): `TestPortabilityExceptions250RequiredEmptyEntry`
  proves `expected_portability_exceptions("2.5.0")` resolves to `{}` and
  that `expected_portability_exceptions("2.3.1")`/`("2.4.0")` are
  byte-unchanged by this checkpoint.
- `scripts/workflow_state_test.py`:
  `GeneratedDeclarationsWorkflowManagerImplementationStageWideningTest`
  (three tests) proves `generate_artifacts_declarations`'s
  implementation-stage default classifies
  `.workflow-manager/installation.json` `excluded` for both work-item
  types, and that the widened prefix is symmetric with the plan-stage
  default.

**Known, out-of-scope pre-existing gap surfaced by introducing
`workflow_integration_test.py` into the overlay for the first time**: run
directly against this repository's own live `docs/ai-workflow/*`
(governed by this repository's currently-installed release, not `2.5.0`)
with the *overlay's* `workflow_state.py` imported as `ws`, two unrelated
tests fail --
`TestOperatorReferenceMatchesReality.test_the_persisted_phase_table_is_exactly_the_writer_census`
and `.test_the_v1_plan_approval_gate_is_not_described_as_a_phase`. Checked
directly against the overlay's own paired `docs/ai-workflow/
WORKFLOW_V2_1_OPERATOR_REFERENCE.md`: the second is a genuine, pre-existing
staleness from CP1/CP2's own already-approved widening of
`_require_v2_1_plan_review` (no longer contains the literal `!= "2.1"`
the assertion looks for); the first reflects `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`
missing from the reference's "Persisted phases" table. Neither is caused by
CP9's own four fixes, both predate this checkpoint, and both are outside
`D-Post-v2.3.1-Backlog`'s stated scope -- left for CP11's own "every
payload document the sweep requires changing" step (or CP13's full
regression) to catch and correct once the composed `2.5.0` distribution
actually exists to run this suite against meaningfully. This checkpoint's
own narrowest checks (below) verify only the four backlog fixes
themselves, per its own registry scope.

Verification run for CP9 (narrowest relevant check, not the full suite --
`workflow_integration_test.py`'s full suite cannot be meaningfully run
against the overlay until `distribution/workflow/2.5.0/` is composed at
CP11, for the reason above):
```
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts \
  python3 -m unittest \
  workflow_state_test.GeneratedDeclarationsWorkflowManagerImplementationStageWideningTest \
  workflow_integration_test.TestPlanApprovalStateBlobPinAndMaterialize.test_pin_defaults_to_mode_100644_when_state_path_absent_at_head \
  workflow_integration_test.TestRetiredScopedRemediationLeavesNoLiveSurface.test_the_historical_status_note_carries_a_dated_correction \
  -v
python3 -m unittest test_conformance_suite.TestPortabilityExceptions250RequiredEmptyEntry -v   # run from tests/
```
Result: 6 passed, 1 skipped (the host-note test, correctly, against this
repository's own history-free `docs/ACTIVE_MILESTONE.md`), 0 failed. A full
`workflow_state_test` run under the same `PYTHONPATH` trick (822 tests, up
from CP8's 819) shows only the same 3 pre-existing errors that trick itself
is known to produce outside the composed release tree
(`TestGlobalLockOrderItem372h.setUpClass` and
`TestCanonicalStateSerialization`'s two dry-run-path-relative tests),
unaffected by this checkpoint's changes. `python3 tests/run_all.py --fast`
is green (8/8 suites).

CP8 delivered `D-Review-Finding-Taxonomy-and-Circuit-Breaker` (`§2.6`), in
`migration/overlays/2.5.0/payload/`:

- `docs/ai-workflow/REVIEW_PROTOCOL.md`: a new "Finding taxonomy and
  circuit breaker" subsection under the existing "Feedback protocol"
  section, additive only. An advisory, never parser-enforced,
  `[substantive]`/`[apparatus]` tag on every Blocking/Important
  `REVIEW_FEEDBACK.md` finding — a missing, malformed, or ambiguous tag
  is never rejected and defaults, conservatively, to `[substantive]` for
  every purpose (I5), so no live work item's existing feedback shape
  breaks on update and silence can never manufacture an apparatus-only
  streak. The existing resolve-or-reject-with-evidence rule is
  unchanged regardless of tag or its absence. A bounded, advisory
  circuit-breaker signal — fixed at 2, not left open (I6), since neither
  `record_local_plan_review`'s/`record_manual_plan_review`'s `REVISE`
  branch (nor their implementation-stage mirrors') writes any durable
  finding-classification-bearing ledger entry, so a reviewer can never
  observe more than one prior round beyond its own — stated in the
  reviewer's own next report after two consecutive apparatus-only
  `REVISE` rounds for the **same local-model** review stage
  (`LOCAL_MODEL_PLAN_REVIEW` or `LOCAL_MODEL_IMPLEMENTATION_REVIEW`,
  distinguished by `REVIEW_FEEDBACK.md`'s own `Reviewer role:` line).
  Never phase-gating, no new `WORKFLOW_STATE.json` field, no
  governing-version bump. Explicitly scoped away from two consecutive
  manual-external rounds: the single-prior-visibility mechanism the
  signal relies on does not hold there (a fresh required local pass
  always overwrites the shared `REVIEW_FEEDBACK.md` path before the next
  manual reviewer ever sees the prior one), so the added text states no
  corresponding recoverability claim for that case — manual-external
  convergence stays operator judgment, as it already is today.
- `scripts/workflow_state_test.py`: `FindingTaxonomyCircuitBreakerTest`
  (six tests: the signal fires after two consecutive apparatus-only
  rounds for each local-model stage independently; never fires across
  differing stages, for manual-external rounds, when only one round is
  apparatus-only, or when a missing tag could otherwise have
  masqueraded as apparatus; and the resolve-or-reject rule's own prose
  is unaffected by tag or its absence) and
  `ReviewProtocolManualExternalCircuitBreakerScopeTest` (two tests:
  `REVIEW_PROTOCOL.md`'s own text states no manual-external
  recoverability claim, and no sentence mentioning manual-external
  rounds makes an affirmative circuit-breaker claim). Both classes use
  test-only reference logic (`circuit_breaker_fires`, `_finding_tag`,
  etc.) modeling exactly the algorithm the new prose describes — never
  imported by `workflow_state.py` or any review command, matching the
  "advisory, never machine-enforced" framing; the declarations file
  needs no update (`migration/` is already a plan-stage excluded prefix
  and an implementation-stage protected prefix, per CP1/CP6/CP7).

Verification run for CP8 (narrowest relevant check, not the full suite):
```
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts \
  python3 -m unittest workflow_state_test.FindingTaxonomyCircuitBreakerTest \
  workflow_state_test.ReviewProtocolManualExternalCircuitBreakerScopeTest -v
```
Result: 8/8 passed. A full `workflow_state_test` run under the same
`PYTHONPATH` trick (819 tests, up from CP7's 811) shows only the same 3
pre-existing errors that trick itself is known to produce outside the
composed release tree (`TestGlobalLockOrderItem372h.setUpClass` and
`TestCanonicalStateSerialization`'s two dry-run-path-relative tests),
unaffected by this checkpoint's changes.

CP7 delivered `D-Canonical-Review-Data` (`§2.5`):

- `migration/overlays/2.5.0/payload/scripts/workflow_state_test.py`: one
  generic, parametric declaration-coverage helper --
  `find_declaration_symmetry_gaps` (the plan-stage/implementation-stage
  declaration-symmetry check, both directions, `narrowing_exceptions`
  included) and `assert_declaration_coverage` (the full per-work-item
  check: every `implementation_stage.protected_paths`/`protected_prefixes`
  entry classifies `protected`, plus both symmetry directions) --
  replacing the bespoke, hand-authored pattern this item's own CP2 and
  `plan-amendment-mechanism` each separately hand-derived from their own
  registry/declarations data. Both existing bespoke tests are left as-is
  (out of this milestone's scope to retrofit an already-approved work
  item's own test file); a future work item's plan calls the shared
  helper instead. The module docstring records
  `workflow_state_completion_obligations_test.py`'s own
  `surface_census`/`verifier_census` mechanism as this helper's own
  precedent (already mechanically discovered, never a second defect),
  per the plan's explicit instruction not to re-flag it.
- `DeclarationSymmetryHelperTest`: the seventeen required fixtures
  (revision 41's own list) pinning every documented case -- direction
  (a) failure; direction (b) failure with no coverage at all, with
  partial coverage and no exception, and against this item's own live
  pre-CP7 declarations file (pinned to CP7's own start commit,
  `2af606ac8b30a3db24d77e9f2429eebf6a212aaf`); `narrowing_exceptions`
  malformed in every documented way (empty value, undeclared listed
  path, listed path not contained, omits a contained exact child, omits
  a contained prefix child, a live-regression addition of each shape
  without updating the exception, and a key that is not itself a real
  plan-stage entry); the passing cases (the declared
  `.workflow-manager/` exception, a plan-stage entry fully covered
  without needing an exception, and a narrowing exception naming a
  contained prefix rather than an exact path); and the real-corpus
  check that this item's own post-CP7 declarations file passes both
  directions complete, plus `assert_declaration_coverage` itself
  against this same live work item.
- `docs/ai-workflow/registry/implementation-review-two-stage-artifacts.json`:
  CP7's own one write outside `migration/` (P-exc via
  `plan_stage.excluded_prefixes['docs/ai-workflow/registry/']`, I-prot as
  an `implementation_stage.protected_paths` exact entry -- the
  declarations file's own self-protection): added
  `plan_stage.narrowing_exceptions['.workflow-manager/'] =
  ['.workflow-manager/installation.json']`, restating as data what
  revision 36 stated only in prose. Recomputing
  `compute_review_content_id_plan_stage`'s own projection
  (`sorted(protected_paths)`/`sorted(excluded_paths)`/
  `sorted(excluded_prefixes)`) before and after this edit confirms it is
  byte-for-byte unchanged -- the new key sits outside that projection, so
  this edit does not breach §2.7/REQ-12's forward-only rule and does not
  stale the existing `plan_approval`.

Verification run for CP7 (narrowest relevant check, not the full suite):
```
PYTHONPATH=migration/overlays/2.5.0/payload/scripts:scripts \
  python3 -m unittest workflow_state_test.DeclarationSymmetryHelperTest -v
```
Result: 17/17 passed. A full `workflow_state_test` run under the same
`PYTHONPATH` trick (811 tests, up from CP6's 794) shows only the same 3
pre-existing errors that trick itself is known to produce outside the
composed release tree (`TestGlobalLockOrderItem372h.setUpClass` and
`TestCanonicalStateSerialization`'s two dry-run-path-relative tests),
unaffected by this checkpoint's changes.

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

External implementation review (round 10) approved with no further
findings; `/approve-review implementation` recorded `technical_approval` as
`CURRENT`. The work item is now at `AWAITING_FUNCTIONAL_REVIEW`, a hard
gate. This item is `"2.1"`-governed, so its own review lifecycle used the
existing single-stage implementation-review gate throughout -- the
two-stage protocol this milestone authors is `"2.2"`-only and applies to no
work item that exists today; that protocol is exercised instead by the
manual checklist below, against disposable repositories.

Next: manual functional testing per the checklist below. Findings go to
`.ai-review/feedback/FUNCTIONAL_REVIEW.md`; `/apply-functional-review`
classifies and routes them. Once testing is clean and every checkpoint in
`docs/ai-workflow/registry/implementation-review-two-stage-registry.json`
is `COMPLETE` (all 13 are), `/accept-milestone` is the only acceptance
command.

## Functional review checklist

All testing below happens against **disposable, throwaway repositories**
only — never `~/Workspace/repflow-android` (frozen, read-only; read it via
`git show <tag>:<path>` if needed) and never this repository's own live
`docs/ai-workflow/WORKFLOW_STATE.json` work items. The feature under test —
a new `governing_workflow_version: "2.2"` mirroring the two-stage
plan-review protocol onto the implementation-review gate — is inert for
every work item that exists anywhere today, so it can only be exercised
inside a disposable repo that explicitly activates it.

### Setup

1. Confirm both releases still reproduce:
   ```
   python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check
   python3 tools/migrate.py --check --upstream ~/Workspace/repflow-android
   ```
2. Create a scratch directory outside this repo, e.g. `/tmp/wf-impl-review-check/`.
3. Create and bootstrap the first disposable target repo directly on the new
   release (`--release-version` precedes the subcommand). The target must
   already be a Git repository with a baseline commit before any command
   that resolves `base_commit` (e.g. `git rev-parse HEAD`) can succeed:
   ```
   mkdir -p /tmp/wf-impl-review-check/repo-a
   git -C /tmp/wf-impl-review-check/repo-a init -q -b main
   git -C /tmp/wf-impl-review-check/repo-a config user.email "check@example.invalid"
   git -C /tmp/wf-impl-review-check/repo-a config user.name "Functional Check"
   git -C /tmp/wf-impl-review-check/repo-a config commit.gpgsign false
   PYTHONPATH=src python3 -m workflow_manager --release-version 2.5.0 bootstrap /tmp/wf-impl-review-check/repo-a
   git -C /tmp/wf-impl-review-check/repo-a add -A
   git -C /tmp/wf-impl-review-check/repo-a commit -q -m "baseline: bootstrap workflow 2.5.0"
   ```
4. Create and bootstrap a second disposable target repo on the *old*
   release, to exercise the update path in Flow 5:
   ```
   mkdir -p /tmp/wf-impl-review-check/repo-b
   git -C /tmp/wf-impl-review-check/repo-b init -q -b main
   git -C /tmp/wf-impl-review-check/repo-b config user.email "check@example.invalid"
   git -C /tmp/wf-impl-review-check/repo-b config user.name "Functional Check"
   git -C /tmp/wf-impl-review-check/repo-b config commit.gpgsign false
   PYTHONPATH=src python3 -m workflow_manager --release-version 2.4.0 bootstrap /tmp/wf-impl-review-check/repo-b
   git -C /tmp/wf-impl-review-check/repo-b add -A
   git -C /tmp/wf-impl-review-check/repo-b commit -q -m "baseline: bootstrap workflow 2.4.0"
   ```

### Test data

No product/feature content is needed — the mechanism under test is the
Workflow lifecycle itself. Each flow drives a synthetic `process`-type work
item (e.g. `impl-review-check-1`) through checkpoints, using
`src/workflow_manager/fixture.py`'s
`drive_synthetic_work_item_through_checkpoints` (fastest, scripted) or the
repo's own installed slash commands directly (closer to a real operator's
experience — prefer this for at least one flow). A `"2.2"` item can only be
created after repo-a activates `"2.2"` (Flow 1) — there is no legal path
for an existing `"1"`/`"2.1"` item to become `"2.2"` retroactively.

### Flow 1 — activate "2.2" in repo-a, following the documented procedure verbatim

1. Confirm a fresh `2.5.0` bootstrap is *not* `"2.2"`-enabled:
   `docs/ai-workflow/WORKFLOW_CONFIG.json`'s `default_workflow_version` is
   still `"2.1"`.
2. Follow `docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md`'s
   "Activating `2.2`" section by hand (never `build_activated_config`): edit
   `default_workflow_version` to `"2.2"` **and** append `"2.2"` to
   `supported_versions` in the same commit, carrying a
   `Workflow-Activation: 2.2` trailer.
3. **Expected:** `workflow_state.is_activated()` reports true afterward; a
   work item created from this point on defaults to `"2.2"`; no
   already-existing work item's `governing_workflow_version` is touched
   (there are none yet in repo-a).

### Flow 1a — activation guardrails (negative path)

1. **Partial edit:** repeat Flow 1's edit but change only
   `default_workflow_version` (leave `supported_versions` unchanged), commit
   with the same trailer. **Expected:** `validate_config` refuses the
   partial edit by name.
2. **Missing config after activation:** with `"2.2"` genuinely activated
   (Flow 1), delete or corrupt `WORKFLOW_CONFIG.json` and attempt any
   command that calls `load_config`. **Expected:** raises
   `ConfigMissingAfterActivationError` naming the resolved destination
   version (`"2.2"`) — never a silent fallback to `default_config()`.
3. **Rollback:** commit `Workflow-Rollback: 2.2`, reverting
   `default_workflow_version` to `"2.1"`. **Expected:** `is_activated()`
   still reports true (destination `"2.1"`, not `"1"`) — matches `"2.1"`'s
   own binary behavior at that same boundary, closing the previously-silent
   second boundary a `"2.2"` rollback opens.
4. **Malformed rollback trailer:** repeat with a blank or unrecognized
   `Workflow-Rollback` trailer value (e.g. `Workflow-Rollback: 2.9`).
   **Expected:** resolves fail-closed as activated — never a silent
   fall-through to not-activated, never an uncaught `KeyError`.
5. Re-activate `"2.2"` in repo-a (undo this sub-flow's rollback) before
   continuing to Flow 2 — the remaining flows need a live
   `"2.2"`-activated repo-a.

### Flow 2 — a "2.2" item's plan stage is unaffected

1. In repo-a, create a synthetic `"2.2"` work item (`impl-review-check-1`)
   and drive its plan through `/milestone-plan` → `/review-plan` (local) →
   `/record-manual-plan-review` (manual) → `/approve-review plan`.
2. **Expected:** `AWAITING_LOCAL_PLAN_REVIEW` →
   `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` → `AWAITING_PLAN_APPROVAL`,
   identical in shape to a `"2.1"` item's plan stage — this milestone widens
   `TWO_STAGE_PLAN_REVIEW_VERSIONS` to include `"2.2"` but changes no
   plan-stage behavior itself.

### Flow 3 — the new two-stage implementation-review flow, positive path

1. Drive `impl-review-check-1` through its checkpoints with
   `/milestone-implement` to `SELF_REVIEWING_IMPLEMENTATION`, then let
   bundle generation run.
2. **Expected:** the item lands at `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` —
   not the legacy single-stage `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` a
   `"1"`/`"2.1"` item would reach here.
3. Run `/review-implementation` (a fresh session is recommended, mirroring
   the plan side's local stage) and APPROVE. **Expected:** a local
   `implementation_review_stages` ledger entry is recorded; phase
   transitions to `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`.
4. Upload the bundle to a manual reviewer (or simulate one), paste the
   verdict into `REVIEW_FEEDBACK.md`, run
   `/record-manual-implementation-review`, and APPROVE. **Expected:** phase
   transitions to the terminal `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` —
   the same hard gate a `"1"`/`"2.1"` item reaches, now reached through two
   recorded stages instead of one.
5. Run `/approve-review implementation` (user-only). **Expected:**
   `technical_approval` becomes `CURRENT`; phase advances past the gate
   (e.g. to `AWAITING_FUNCTIONAL_REVIEW`).
6. Confirm no bundle regeneration happened between steps 3 and 4 — the same
   `bundle_id` is carried through the local-approve → manual-external
   hand-off, mirroring the plan side's own rule.

### Flow 3a — implementation-review negative paths

Exercise each of these as its own throwaway attempt against a `"2.2"` item
mid-flow (reuse `impl-review-check-1` at the relevant phase, or a second
synthetic item where a path would otherwise consume Flow 3's own progress):

1. **Local REVISE:** REVISE at the local stage. **Expected:** phase goes
   directly to `APPLYING_REVIEW_FEEDBACK` (no `enter_applying_review_feedback`
   call for `"2.2"`); `/apply-implementation-review` then returns the item
   to `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` via the same post-fix
   bundle-generation resolver, never a second writer.
2. **Local BLOCK:** BLOCK at the local stage. **Expected:** no-op — phase
   and ledger unchanged, requiring human intervention rather than an
   automatic transition.
3. **Manual REVISE:** REVISE at the manual stage. **Expected:** loops back
   to the *local* stage (`AWAITING_LOCAL_IMPLEMENTATION_REVIEW`), never
   straight back to manual — confirm this explicitly, since it is easy to
   assume a manual REVISE re-runs only the manual pass.
4. **Manual BLOCK:** BLOCK at the manual stage. **Expected:** no-op, same as
   local BLOCK.
5. **Wrong-phase, manual before local:** attempt
   `/record-manual-implementation-review` while the item is still at
   `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` (local stage not yet approved).
   **Expected:** refused by name, naming the actual phase.
6. **Wrong-phase, local from the wrong phase:** attempt
   `/review-implementation`'s `"2.2"` branch against an item not at
   `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`. **Expected:** refused by name.
7. **Ledger check for a `"2.1"` item:** confirm the widened
   `technical_approval_gate_reachable` ledger check is inert for a
   `"1"`/`"2.1"` item — its existing single-stage advisory behavior must be
   byte-unchanged.
8. **Stale `review_content_id`:** after local APPROVE, change the reviewed
   content (e.g. touch a protected file) before running
   `/record-manual-implementation-review`. **Expected:** manual ingestion
   hard-refuses with a staleness error, never silently ingesting feedback
   against superseded content.
9. **Duplicate manual ingestion:** run `/record-manual-implementation-review`
   twice against the same feedback file/verdict. **Expected:** the second
   run is refused as a duplicate.
10. **Bundle-id mismatch, manual stage:** manually edit the feedback file's
    recorded `bundle_id` before a `/record-manual-implementation-review` run
    so it no longer matches the current bundle. **Expected:** this is
    advisory-only — a warning, never a hard block.

### Flow 3b — `/recover-implementation-provenance` from each of the three "2.2" phases

1. After a legitimate excluded-only commit lands past the current
   `Workflow-Bundle-Generation-Record` commit, run
   `/recover-implementation-provenance` once with the item at each of:
   `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
   `AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, and the terminal
   `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`.
2. **Expected:** recovery succeeds from all three phases (the command's own
   phase guard and the recovered-role committed-phase membership test are
   the identical three-phase set); `HEAD == T` holds afterward in each
   case; a fourth attempt where the content genuinely changed (not just
   excluded-only) is correctly refused as not-applicable/stale rather than
   "recovered."

### Flow 4 — a "2.2" functional bounded fix re-enters both implementation-review stages

1. Take `impl-review-check-1` (or a fresh `"2.2"` item) all the way to
   `AWAITING_FUNCTIONAL_REVIEW`, then simulate a functional-review bounded
   fix (`/apply-functional-review`'s bounded branch,
   `technical_approval.status == "STALE"`).
2. **Expected:** resolves to `AWAITING_LOCAL_IMPLEMENTATION_REVIEW` — a
   `"2.2"` item must re-clear *both* implementation-review stages before
   `/approve-review implementation` is reachable again; it never routes
   straight to the terminal phase.

### Flow 5 — update path leaves a live "2.1" item unaffected

1. In repo-b (bootstrapped on `2.4.0` above), drive a synthetic `"2.1"` work
   item to mid-`AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW`.
2. Run
   `PYTHONPATH=src python3 -m workflow_manager --release-version 2.5.0 update /tmp/wf-impl-review-check/repo-b`.
3. **Expected:** the existing item's phase, ledgers, and
   `governing_workflow_version` (`"2.1"`) are untouched; `"2.2"` is not
   available in repo-b until it separately activates it (Flow 1's
   procedure) — updating alone never grants it.

### Flow 6 — post-v2.3.1 backlog fixes (CP9)

1. **v2.3.1-003:** in a fresh disposable repo with no pre-committed
   `WORKFLOW_STATE.json` blob at `HEAD`, run a first-ever
   `/approve-review plan`. **Expected:** succeeds, defaulting the staged
   blob's mode to `100644` instead of refusing outright.
2. **`.workflow-manager/` implementation-stage symmetry (v2.4.0-001
   widening):** confirm `generate_artifacts_declarations`'
   implementation-stage default `excluded_prefixes` now includes
   `.workflow-manager/`, symmetric with the plan-stage default. This is
   forward-only — no existing work item's own already-generated
   declarations file changes.
3. **Portability exceptions:** confirm
   `migration/portability_exceptions.json`'s `by_version["2.5.0"]` entry
   exists and is empty, and that `2.3.1`'s/`2.4.0`'s own entries are
   untouched.

### Flow 7 — review-material-lifecycle marker (CP1/CP6), spot check

1. In
   `migration/overlays/2.5.0/payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`,
   confirm CP1's carried `2.5.0`-scoped disposition-record subsection is
   preceded by the exact marker
   `<!-- review-material-lifecycle: HISTORICAL -->`, and that a current
   design section (e.g. `D-Implementation-Review-Stages`) carries
   `<!-- review-material-lifecycle: CURRENT -->` or no marker at all
   (fail-closed default, also `CURRENT`).
2. This lint's own classification/marker-presence/governing-version-sweep
   behavior is exercised by the automated suite (`tests/run_all.py`,
   already confirmed green — see step 1 of `/prepare-functional-review`);
   this spot check is a human sanity read of the actual document, not a
   re-run of that suite.

### Flow 8 — authored-release production

1. `python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check`
   must reproduce `distribution/workflow/2.5.0/` exactly from base `2.4.0`
   plus the overlay.
2. `python3 tools/migrate.py --check --upstream ~/Workspace/repflow-android`
   must still show `2.3.1` byte-identical to the frozen tag — confirm this
   milestone did not alter it.

### Known limitations / out of scope

- `docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`
  (cross-worktree amendment/claim race) is explicitly reconsidered by this
  milestone (`CP10`) and still deferred in full, including the optional
  `IMPL10-O1` mitigation — do not re-raise it as a new finding here.
- `"2.2"` has no legal retroactive-adoption path: an existing `"1"`/`"2.1"`
  work item, in this repository or any other (e.g.
  `~/Workspace/workflow-controller`'s `workflow-controller-generation-1`),
  cannot become `"2.2"`. Do not attempt or expect this.
- Two `docs/defects/*.md` files are currently untracked in this
  repository's own working tree (unrelated in-progress bookkeeping,
  predating and outside this command's own scope) — do not test against or
  modify them here.
- Downgrading a repository that has ever activated `"2.2"` or held any of
  its vocabulary (the two new phases, an `implementation_review_stages`
  ledger) back to an older release is unsupported, per this repository's
  own `CLAUDE.md` — do not attempt it as part of this review.
