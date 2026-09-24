# Active Milestone

## Milestone

`workflow-review-artifact-and-concurrency-hardening`
(`governing_workflow_version: "2.2"`, plan approved at revision 8): Workflow
`2.6.0` — review-artifact, publication and concurrency hardening.
Full plan: `docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`.

## Goal

Close the Workflow correctness defects and gaps that `docs/ROADMAP.md`
section 1 groups under review artifacts, review publication, approval commit
integrity, legacy active-work-item compatibility, amendment artifacts and
cross-worktree concurrency, as one bounded hardening release. Deliverable: a
new authored Workflow release, `2.6.0`, built as `distribution/workflow/2.5.1/`
(base, unchanged, byte-for-byte immutable) plus `migration/overlays/2.6.0/`,
per this repository's `CLAUDE.md` "Adding an authored Workflow release"
process. See the plan's section 2 for non-goals.

## Current checkpoint

**CP2 complete** (2 of 9 checkpoints). Next: CP3 (depends on CP1) — the
per-work-item feedback layout.

### CP1 — Release-derived exact-path classification of the legacy installation record

Implements the plan's section 5.2, `D-Tooling-Ambient-Classification` (the
legacy-item half of `v2.4.0-001`; requirement `REQ-3`). Delivered in
`migration/overlays/2.6.0/` (this milestone's first overlay files, each a
full replacement starting from the `2.5.1` base copy):

- `payload/scripts/workflow_fingerprint.py`: new
  `TOOLING_AMBIENT_EXCLUDED_PATHS = frozenset({".workflow-manager/installation.json"})`.
  `classify_path` and `classify_path_implementation_stage` consult it only
  after every declared classification has failed, immediately before the
  `UnclassifiedPathError` raise. No other line of the module changed.
- `payload/scripts/workflow_fingerprint_test.py`: new
  `TestToolingAmbientExcludedPaths` (8 tests) — fallback classification at
  both stages with a `2.5.1` control arm (constant patched empty), explicit
  protected declaration still wins, siblings
  (`installation.json.tmp`, `other.json`, `.workflow-manager/`, bare and
  nested look-alikes) still raise, full-projection invariance with and
  without the fallback, and digest invariance: with the record unchanged
  every digest is identical; after an uncommitted and then a committed
  record change every digest (plan worktree/commit, implementation
  worktree/commit) that raised under `2.5.1` now equals its pre-change
  recorded value.
- `payload/scripts/workflow_state_test.py`: new
  `TestImplementingEntryReachableAfterInstallationRecordUpdate` — a
  2.3.1-shaped item stays `implementing_entry_reachable` after a committed
  installation-record change; the control arm raises `UnclassifiedPathError`.
- `payload/docs/ai-workflow/REVIEW_PROTOCOL.md`: the classification
  paragraph under "Computing `review_content_id`".
- `payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`: new section
  `D-Tooling-Ambient-Classification` carrying section 5.2's justification.
- `classification.json`: `base_workflow_version: "2.5.1"`, one `replaced`
  rule per touched file. Later checkpoints add their own rules.

Every test/doc change is additive; no pre-existing test was modified.

**Verified state.** Run inside a temporary tree composed from
`distribution/workflow/2.5.1/payload/` overlaid with
`migration/overlays/2.6.0/payload/` (tests resolve sibling files relative to
their own directory, so a bare `PYTHONPATH` split fails on
`prepare-ai-review.sh`):

- `python3 -m unittest workflow_fingerprint_test workflow_fingerprint_generalization_test`:
  305 tests, OK.
- `workflow_state_test`'s new class plus `TestImplementingEntryReachableSecondItem`,
  the `ReviewMaterialLifecycle*`, `GoverningVersionEnumerationSweepTest` and
  `ApplyingReviewFeedbackVersionClaimSweepTest` classes (the new
  `WORKFLOW_V2_PLAN.md` section is swept by them): 51 tests, OK.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP2 — Working-tree-anchored `AMENDMENT_DIFF.patch`

Implements the plan's section 5.5, the `D-Plan-Amendment-5` revision
(`v2.4.0-003`; requirement `REQ-8`). Delivered in `migration/overlays/2.6.0/`:

- `payload/scripts/prepare-ai-review.sh` (first overlay replacement): the
  `AMENDMENT_DIFF.patch` block drops `..HEAD` and writes
  `git diff --no-renames <amendment_base_commit> -- <pathspec>`, anchored at
  the working tree. The pathspec is the sorted union of the
  `plan_stage.protected_paths` declared at `amendment_base_commit` (empty
  when the declaration is absent there), the ones declared now, and
  `<id>-artifacts.json` itself. A leading `#` preamble names
  `work_item_id`, `amendment_id`, `amendment_base_commit`, `plan_revision`
  and `review_content_id`. The block moved to just after `--write-manifest`
  (still after the pin, before the archive), so the preamble carries the
  manifest's own `review_content_id`. Nothing else in the script changed;
  the archive line item 341 guards is untouched.
  **`--no-renames` is an implementation finding, not in the plan text:**
  section 5.5 says Git's rename detection is not relied on, but `git diff`
  applies it by default (`diff.renames`), and the rename test failed
  without the flag — the patch showed `rename from/to`, not
  `deleted file` + `new file`.
- `payload/scripts/workflow_fingerprint_generalization_test.py`: new
  `TestPrepareAiReviewShAmendmentDiffWorkingTreeAnchor` (13 tests), driving
  the real script in scratch repositories. It covers every case CP2 names:
  - an uncommitted plan edit is present, with a `..HEAD` control arm that
    is empty;
  - an untracked new protected file appears as `new file`, and is
    untracked again afterwards (no lingering intent-to-add);
  - a dropped-and-deleted path appears as `deleted file`;
  - a rename appears as `deleted file` + `new file` and passes
    `git apply --check`;
  - a dropped-but-kept path appears as its content diff when changed, and
    only in the declaration hunk when unchanged;
  - with the declaration absent at the base, the patch equals the
    current-only form;
  - non-protected edits are absent;
  - the archive member is byte-identical to the on-disk patch;
  - `bundle_id` is identical with and without the patch (on disk and in
    the archive's `current/`);
  - the file is removed after resolution;
  - the preamble fields equal the manifest's and the state's;
  - `git apply --check` accepts the patch at `amendment_base_commit`.
- `payload/.claude/commands/request-plan-amendment.md` step 4,
  `payload/docs/ai-workflow/REVIEW_PROTOCOL.md` "Bundle structure", and
  `payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md` `D-Plan-Amendment-5` (new
  "Working-tree anchor" paragraph): restated to the working-tree anchor.
  The command keeps the mention-only generator wording that
  `workflow_integration_test.py`'s census pins.
- `classification.json`: three new `replaced` rules (`prepare-ai-review.sh`,
  the generalization test, `request-plan-amendment.md`); the existing
  `REVIEW_PROTOCOL.md`/`WORKFLOW_V2_PLAN.md` rules' rationales now cover
  CP2's delta too.

Every test change is additive; no pre-existing test was modified.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay (committed there as one scratch commit):

- `python3 -m unittest workflow_fingerprint_generalization_test`: 92 tests, OK
  (the new class alone: 13, OK).
- `python3 -m unittest workflow_integration_test`: 260 tests, 3 errors.
  Every error is in `TestRetiredScopedRemediationLeavesNoLiveSurface`, which
  reads the repository-level `docs/ACTIVE_MILESTONE.md`. The payload tree
  has none. The pure `2.5.1` payload has the identical failure set.
- `python3 -m unittest workflow_state_test` (its doc sweeps read the edited
  `WORKFLOW_V2_PLAN.md`): 854 tests, 2 errors. Both are
  `TestCanonicalStateSerialization` live-state tests with no live
  `WORKFLOW_STATE.json` in the payload tree. The pure `2.5.1` payload has the
  identical 2 errors.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`
(revision 8), registry
`docs/ai-workflow/registry/workflow-review-artifact-and-concurrency-hardening-registry.json`.

## Next action

Invoke `/milestone-implement workflow-review-artifact-and-concurrency-hardening`
to implement CP3.
