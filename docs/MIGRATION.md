# Workflow v2.3.1 migration record

This is the Phase-A record: what was extracted from the frozen upstream
release, what was not, and how that is proven. It is written to be read
without any conversation context.

## The frozen source

| | |
|---|---|
| Repository | `repflow-android` (local clone) |
| Tag | `workflow-v2.3.1` |
| Commit | `1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6` |
| Paths at that commit | 479 |

The upstream repository is read-only for this project. Every read goes
through `git show <commit>:<path>` against the object store — never through
the upstream working tree, which carries an unrelated in-flight redesign
branch. `tools/migrate.py` re-checks that the tag still resolves to the
pinned commit before it reads anything.

## How the closure was derived

Not from an inventory handed over in advance. The dependency closure was
derived mechanically from the frozen source and then confirmed by
experiment:

1. **Static trace.** Imports, `sys.path` manipulation, `Path(__file__)`
   arithmetic, and every repository-path string literal across
   `scripts/*.py`, `scripts/prepare-ai-review.sh` and `.claude/commands/*.md`.
2. **Baseline.** A read-only clone at the frozen commit, with all nine
   upstream suites run to completion. All nine are green — 1440 tests in the
   seven CI-gated suites, plus the two history-coupled demo suites.
3. **Ablation.** A candidate closure was built into a disposable Git
   repository, then files and directories were removed group by group and the
   suites re-run. A path is in the closure if and only if removing it turns a
   suite red.

The ablation is what makes the closure trustworthy: a file is retained
because its absence breaks something, not because it looked related.

### What the ablation found

Required (removing them breaks a suite):

| Path | Broken by its absence |
|---|---|
| `scripts/` (all 13 files) | everything |
| `.claude/commands/*.md` | `workflow_integration_test` command census and hashes |
| `docs/ai-workflow/WORKFLOW_V2_PLAN.md` | `workflow_integration_test`, `workflow_state_test` |
| `docs/ai-workflow/MILESTONE_WORKFLOW.md` | `workflow_integration_test`, `workflow_state_completion_obligations_test` |
| `docs/ai-workflow/REVIEW_PROTOCOL.md` | `workflow_integration_test` |
| `docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md` | `workflow_integration_test` |
| `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md` | `workflow_integration_test` |
| `docs/ai-workflow/diagrams/workflow-v2-1-lifecycle.drawio.svg` | `workflow_integration_test` (parses the embedded drawio model) |
| `docs/ai-workflow/requirements/workflow-v2-1-core-mapping.json` | `workflow_integration_test` (WFR table lint) |
| `docs/ai-workflow/dry-run/verify_372h_*.py` (2 files) | `workflow_state_test` loads and executes them |
| `docs/ai-workflow/WORKFLOW_STATE.json` | `workflow_state_test` canonical-serialization guards |
| `CLAUDE.md` | `workflow_integration_test` `LIVE_DOCS` lint |
| `docs/ACTIVE_MILESTONE.md` | `workflow_integration_test` retirement lints |

Not required (probed removable): `AGENTS.md`, `.github/`, `.gitignore`,
`docs/ai-workflow/audit/`, `docs/ai-workflow/registry/`, the non-`verify_`
half of `docs/ai-workflow/dry-run/`, and the four `WORKFLOW_V2_{AUDIT,3_*}.md`
documents.

Some not-required files are still migrated, as `conformance`: they are the
Workflow's own design and audit history, and dropping them would leave the
distribution unable to explain itself. That is a deliberate choice, recorded
per file in the manifest, not an accident.

Two structural constraints came out of the trace and are load-bearing:

- `docs/ai-workflow/dry-run/verify_372h_lock_primitive_predicate.py` resolves
  the repository root as `Path(__file__).resolve().parents[3]`, and its
  sibling resolves the plan document as `parent.parent / "WORKFLOW_V2_PLAN.md"`.
  **Their directory depth is part of the contract**; they cannot be relocated.
- `workflow_state.py` imports `workflow_fingerprint` by bare name, so the two
  must stay in the same directory.

## Classification

`migration/classification.json` holds an ordered, first-match-wins ruleset.
Every path at the frozen commit must match a rule; an unmatched path is a hard
error, so the inventory cannot silently drift when the source changes.

| Category | Count | Meaning |
|---|---|---|
| `distribution` | 34 | Canonical Workflow implementation. Installed into every managed repository. |
| `conformance` | 24 | Workflow-owned material the frozen suite reads. Installed under the `full` profile. |
| `host-evidence` | 2 | Upstream host documents the frozen suite asserts on. Fixture only, never installed. |
| `template` | 4 | Repository-local state. Never copied; a clean template is generated. |
| `historical` | 38 | Upstream evidence no test requires. Deliberately excluded. |
| `upstream-specific` | 377 | RepFlow application and build material. |
| **Total** | **479** | |

Every excluded path records the sha256 of the bytes it declined, so a later
upstream release cannot change a file's content and silently inherit its
verdict.

## Layout

```
distribution/workflow/2.3.1/
├── manifest.json   every one of the 479 upstream paths, exactly once
├── payload/        58 files, byte-identical, at target-relative paths
├── fixtures/       CLAUDE.md and docs/ACTIVE_MILESTONE.md, frozen
└── templates/      6 generated files: 3 seeding repository-local state,
                    2 merged into files the target may already own, and the
                    release-owned conformance CI workflow
```

Payload paths are target-relative, so installing is a copy with no path
rewriting. That is deliberate: the two `verify_372h_*.py` scripts and the
bare-name import above both depend on layout, and a rewriting installer would
be a place for those to break silently.

## Templates

| Target path | Derivation |
|---|---|
| `docs/ai-workflow/WORKFLOW_STATE.json` | generated — empty state in `_serialize_state`'s canonical form |
| `docs/ai-workflow/WORKFLOW_CONFIG.json` | identity — the frozen file is already repository-generic |
| `docs/ACTIVE_MILESTONE.md` | generated — clean scaffold; the frozen file is 1857 lines of RepFlow narrative |
| `CLAUDE.md` | generated — Workflow routing only, in a managed section |
| `.gitignore.workflow-fragment` | generated — merged into the target's own `.gitignore` |
| `.github/workflows/workflow-conformance.yml` | generated — the frozen CI's seven hermetic suite steps. Rendered here, but owned by the release once installed: see [ARCHITECTURE.md](ARCHITECTURE.md#what-the-installer-owns-and-what-it-does-not) |

The `WORKFLOW_STATE.json` template is proven against the migrated
`workflow_state` module itself: `tests/test_templates.py` asserts the
generated bytes equal `ws._serialize_state(json.loads(bytes))` and pass
`ws.validate_state`. The CI template's suite list is checked against the
frozen `ci.yml`'s own `python3 <suite>` steps rather than trusted.

## Evidence

`python3 tests/run_all.py`

| Suite | Proves |
|---|---|
| `test_migration_inventory.py` | The inventory is closed: 479 paths, each classified exactly once, every rule live, every record carrying a rationale. Re-reads the frozen tree independently. |
| `test_payload_bytes.py` | Every migrated file is byte-identical to `git show <commit>:<path>`; every recorded digest is the real one; a fresh re-extraction reproduces the committed tree; nothing functional reaches back into the upstream checkout. |
| `test_templates.py` | Template generation is deterministic across runs, and each template satisfies the frozen contract that reads it. |
| `test_no_live_state_imported.py` | No `.ai-review/` path, lock, journal, approval, or RepFlow product work item crossed the boundary. |
| `test_internal_references.py` | Every Workflow path the command files and operator contract documents name resolves from the distribution alone; the command inventory is the frozen fifteen; the frozen suite's own `_GOLDEN_COMMAND_FILE_SHA256` table matches the shipped command files; nothing imports outside the stdlib. |
| `test_conformance_suite.py` | The frozen suite against the conformance fixture: all seven green, **1440 tests, matching the upstream baseline count-for-count**. Against a clean target: the failure set is exactly the documented exception list. |
| `test_bootstrap.py` / `test_bootstrap_e2e.py` | The bootstrapper's own output runs the frozen suite to the same result, and survives an update round trip with live work-item state in place. |

### Equivalence result

| | Suites green | Tests |
|---|---|---|
| Upstream baseline at the frozen commit | 7/7 | 1440 |
| Conformance fixture from `distribution/` | 7/7 | 1440 |
| Clean bootstrapped target | 6/7 | 1439 of 1440 |

The single clean-target failure is
`TestRetiredScopedRemediationLeavesNoLiveSurface.test_the_historical_status_note_carries_a_dated_correction`,
which asserts on RepFlow's own dated milestone history. It is recorded in
`migration/portability_exceptions.json` and explained in
`docs/defects/v2.3.1-001-host-history-coupled-tests.md`. Frozen v2.3.1 bytes
were not modified to make it pass, and no false history was written into the
target template to satisfy it.

## What was deliberately not done

- No Workflow behaviour was refactored, renamed, or "improved".
- The RepFlow-specific literals baked into frozen v2.3.1 —
  `LEDGER_COVERAGE_WORK_ITEM_ID = "workflow-v2-1-core"`,
  `DEFAULT_REGISTRY_PATH`, and the `PLAN_STAGE_PROTECTED` /
  `PLAN_STAGE_EXCLUDED_*` path sets — were left exactly as they are. v2.3.1
  already retired them as live defaults (`resolve_plan_stage_metadata` derives
  everything per work item); they survive as named historical fixtures.
- The upstream repository was never written to. No tag, branch, worktree, or
  object was created there.

## Phase-A completion gate

The gate this migration was held to: *a mechanically checkable inventory
showing every Workflow-owned dependency from frozen v2.3.1 as migrated,
templated, deliberately excluded, or historical-only, with no unresolved
dependency-closure item.*

| Gate condition | Where it is checked |
|---|---|
| Every expected reusable artifact accounted for | `manifest.json`; `test_migration_inventory.py::test_artifacts_and_exclusions_partition_the_upstream_tree` |
| Every exclusion carries a classification and rationale | `test_migration_inventory.py::test_every_record_carries_a_category_and_rationale` |
| Migrated bytes match frozen v2.3.1 | `test_payload_bytes.py::test_every_migrated_file_is_byte_identical_to_the_frozen_commit` |
| Transformations deterministic and tested | `test_templates.py` (whole file) |
| Internal references resolve from the distribution | `test_internal_references.py` |
| The Workflow suite executes against the migrated distribution | `test_conformance_suite.py::TestConformanceFixture231` |
| Command inventory and golden hashes accounted for | `test_internal_references.py::TestCommandInventoryAndGoldenHashes` |
| No dependency reaches back into the RepFlow working tree | `test_payload_bytes.py::TestNoUpstreamReachback` |
| No active RepFlow runtime/work-item state imported | `test_no_live_state_imported.py` |
| A clean disposable target satisfies the Workflow's own tests | `test_conformance_suite.py::TestBootstrappedTarget231`, `test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite231` |
| No unresolved dependency-closure item | An unclassified path is a hard error in `tools/migrate.py`; `unmatched_rules` must be empty |

All green. The one clean-target failure is classified, explained, and asserted
to be the *only* one.

## Workflow v2.4.0 — an authored release

Everything above is the Phase-A record for `2.3.1` specifically, and does not
apply to `2.4.0`. `2.4.0` is not extracted from an upstream tag; it is
authored in this repository, to ship the plan-amendment mechanism
(`docs/ai-workflow/PLAN_AMENDMENT_MECHANISM_PLAN.md`'s `AMENDING_PLAN` phase
and `/request-plan-amendment`) on top of the frozen `2.3.1` base: a base
release plus a hand-written overlay, composed by `tools/build_release.py`
(mechanism in [`ARCHITECTURE.md`'s "Authored releases"](ARCHITECTURE.md#authored-releases)).

| | |
|---|---|
| Base release | `2.3.1`, verified against its own manifest before the overlay is applied |
| Overlay | `migration/overlays/2.4.0/` — 11 payload files replaced, 1 added (`.claude/commands/request-plan-amendment.md`) |
| Provenance | `distribution/workflow/2.4.0/manifest.json`'s `provenance`: `{"origin": "authored", "base_release": "2.3.1", "overlay_commit": "531a76137c4a58ca538633b5cea8c193a727d9c5"}` (the build-time `HEAD`, re-recorded by the round-4 `APPLYING_REVIEW_FEEDBACK` rebuild that carried the XMODEL-R4-B1/IMPL4-O1/O2/O3 fixes into the overlay) |
| Manifest | 61 artifacts (35 `distribution`, 24 `conformance`, 2 `host-evidence`), 6 templates |
| Byte-level provenance | Every overlay-replaced file records an `overlay_delta` (the base file's own sha256 plus the sha256 of a unified diff against it). `tools/build_release.py --overlay migration/overlays/2.4.0 --check` reproduces the committed `distribution/workflow/2.4.0/` from the base release and the overlay alone; `TestAuthoredReleaseOverlayDelta` reproduces every `overlay_delta` from the base payload plus its recorded diff |
| Frozen suite against the conformance fixture | 7/7 suites, 1492 tests — the same suite set as `2.3.1`, plus 51 additional `workflow_state_test.py` cases covering the new `AMENDING_PLAN` reconciliation code (including IMPL2-R1's checkpoint-id-shape precondition, IMPL2-O2's named `post_registry` refusal, IMPL3-R1/O1/O2's narrowed plan-approval-coverage read and two residual named refusals, round 4's `AmendmentCheckpointActiveError`/`IllegalCheckpointStartPhaseError` claim-race guards, IMPL4-O1's named `post_registry` missing-`id` refusal, IMPL4-O3's anchor-shape trailing-newline fix, and round 6's `reconciliation_outcome` direct-vs-closure-derived token distinction, `IMPL6-B1`), plus 1 additional `workflow_integration_test.py` case (`IMPL6-B1`'s own static-conformance pin that `approve-review.md` step 7 reports it) |
| Frozen suite in a bootstrapped repository | 1491 of 1492, the same single documented exception as `2.3.1`'s own baseline (`docs/defects/v2.3.1-001-host-history-coupled-tests.md`) — the overlay replaces `workflow_integration_test.py`, but that replacement does not touch this specific test or `docs/ACTIVE_MILESTONE.md`, so the identical RepFlow-history assertion fails for the identical reason |
| Compatibility audit (D-Plan-Amendment-7) | Every test in `workflow_state_test.py`, `workflow_state_completion_obligations_test.py` and `workflow_integration_test.py` whose read set intersects a path this release touches was run directly against the finished overlay diff and reported green or the one already-documented exception above — not merely inferred from the totals above |

Both releases stay independently verifiable and independently frozen:
`tools/migrate.py --check` still proves `2.3.1` byte-identical to the
upstream tag; `tools/build_release.py --overlay migration/overlays/2.4.0
--check` proves `2.4.0` byte-identical to its own recorded
base-plus-overlay composition; and `python3 tests/run_all.py` runs the full
frozen matrix against both releases independently
(`migration/portability_exceptions.json`'s `by_version` keys each release's
own exception set separately, never assumed to carry over from the other).

### Downgrade posture

Downgrading a repository that has ever run `2.4.0` back to `2.3.1` is
**unsupported**. `2.3.1`'s `workflow_state.py` has no `NEEDS_REVALIDATION`
(a `CHECKPOINT_STATUSES` member `2.4.0` introduces) and no `SUPERSEDED` plan-
approval status; a downgraded repository's already-committed
`WORKFLOW_STATE.json` reads any commit that ever recorded either value as
permanently `"undecidable"` under `2.3.1`'s own narrower vocabulary (git
history does not change on downgrade), and checkpoint resume for that work
item wedges with no in-band escape short of the explicit,
evidence-bound `authorize_identity_reference_gap` operation. A repository
that has ever requested a plan amendment, or has any checkpoint that ever
held `NEEDS_REVALIDATION`, or a plan approval that ever held `SUPERSEDED`,
must not run `workflow_manager update --release-version 2.3.1` against
itself again. `CLAUDE.md`'s "Adding an authored Workflow release" states the
same warning as an operator instruction.
