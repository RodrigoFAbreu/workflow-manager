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

**CP1 complete** (1 of 9 checkpoints). Next: CP2 (no dependencies) — the
working-tree-anchored `AMENDMENT_DIFF.patch`.

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

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`
(revision 8), registry
`docs/ai-workflow/registry/workflow-review-artifact-and-concurrency-hardening-registry.json`.

## Next action

Invoke `/milestone-implement workflow-review-artifact-and-concurrency-hardening`
to implement CP2.
