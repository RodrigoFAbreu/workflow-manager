#!/usr/bin/env python3
"""CP12 (`implementation-review-two-stage`, `workflow-2.5.0`): disposable-
repository functional validation for `governing_workflow_version: "2.2"`
(`D-Implementation-Review-Stages`/`D-Implementation-Review-Version-Activation`).

Every scenario here runs against a real, disposable Git repository carrying
a real copy of `workflow-2.5.0`'s own composed tooling -- never a private
reimplementation of the two-stage implementation-review protocol. Two
different fixture shapes are used, matching what each scenario actually
needs to prove:

- `TestActivationProcedureOnComposedRelease`/`TestUpdatePathLeavesLiveItem
  Unaffected` drive the **real installer** (`workflow_manager.install.
  bootstrap`/`update`) against `find_release(REPO_ROOT, "2.5.0"/"2.4.0")`,
  proving the documented `"2.2"` activation procedure
  (`docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md`, "Activating
  `\"2.2\"`") end to end with **no repository-internal shortcut** (resolves
  `LOCAL_MODEL_PLAN_REVIEW` round 10, optional finding 1), and that an
  update to `2.5.0` never retroactively touches a live `"2.1"` item or a
  repository's own un-activated config.
- Every other class below reuses `workflow_acceptance_matrix_test.py`'s own
  proven `Scratch`/`Item` disposable-repo harness (already the vehicle for
  this repository's `"1"`/`"2.1"` acceptance matrix), pointed at
  `distribution/workflow/2.5.0/payload/scripts/` so the tooling each
  `Scratch` actually copies is the real, composed, `"2.2"`-aware release --
  never this repository's own top-level `scripts/` copy, which stays
  `"2.1"`-only. `Item22` (below) is the minimal `"2.2"` extension that
  harness needs: everything else in `Item` already reads
  `governing_workflow_version` from live state rather than hard-coding a
  version, so it drives a `"2.2"` item unmodified.

`assert_declaration_coverage`/`find_declaration_symmetry_gaps` (`D-Canonical
-Review-Data`, CP7) are imported from the composed release's own
`workflow_state_test.py` and exercised directly against this file's own
synthetic work item, rather than a second hand-authored copy of that check.

Slow: this suite bootstraps/bootstraps-then-updates whole disposable
repositories and drives full multi-stage lifecycles inside several more. Run
directly:

    python3 tests/test_implementation_review_two_stage_disposable_repo.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "src"))
from workflow_manager.install import bootstrap, update
from workflow_manager.release import find_release

FIXED_NOW = "2026-01-01T00:00:00Z"

RELEASE_250_SCRIPTS = REPO_ROOT / "distribution" / "workflow" / "2.5.0" / "payload" / "scripts"
if not (RELEASE_250_SCRIPTS / "workflow_state.py").is_file():
    raise RuntimeError(f"composed 2.5.0 release not found at {RELEASE_250_SCRIPTS}")

# Prepended (never appended): every module below must resolve to the
# composed, "2.2"-aware release copy, not this repository's own top-level
# scripts/ (still "2.1"-only) or any other same-named module already on
# sys.path.
sys.path.insert(0, str(RELEASE_250_SCRIPTS))
import workflow_state as ws  # noqa: E402  (the composed 2.5.0 copy, see above)
import workflow_fingerprint as fingerprint  # noqa: E402
import workflow_acceptance_matrix_test as base_matrix  # noqa: E402
import workflow_state_test as wst  # noqa: E402  (assert_declaration_coverage lives here)


def _empty_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "cp12@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CP12"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    return root


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True).stdout


# ===========================================================================
# A. The documented "2.2" activation procedure, driven verbatim against a
#    repository bootstrapped directly on the composed 2.5.0 release --
#    resolves LOCAL_MODEL_PLAN_REVIEW round 10, optional finding 1.
# ===========================================================================


class TestActivationProcedureOnComposedRelease(unittest.TestCase):
    """`docs/ai-workflow/IMPLEMENTATION_REVIEW_WORKFLOW.md`'s "Activating
    `\"2.2\"`" section, followed exactly as documented: a direct
    `WORKFLOW_CONFIG.json` hand edit (both fields, one commit) carrying a
    `Workflow-Activation: 2.2` trailer -- never a call through
    `build_activated_config` (that helper is deliberately not this
    procedure's own implementation; a separate, narrow check below proves
    it separately, on its own terms, never substituted for the real one)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.release = find_release(REPO_ROOT, "2.5.0")
        self.target = _empty_repo(Path(self._tmp.name) / "consumer")
        self.installation = bootstrap(self.target, self.release, now=FIXED_NOW)
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "bootstrap workflow 2.5.0")
        self.config_path = self.target / "docs/ai-workflow/WORKFLOW_CONFIG.json"

    def _config(self) -> dict:
        return json.loads(self.config_path.read_text())

    def test_fresh_install_is_not_22_enabled(self):
        config = self._config()
        self.assertEqual(config["default_workflow_version"], "2.1")
        self.assertNotIn("2.2", config["supported_versions"])

    def test_documented_hand_edit_activates_22(self):
        config = self._config()
        # Step 1: both fields, in the same commit -- never one alone.
        config["default_workflow_version"] = "2.2"
        config["supported_versions"] = config["supported_versions"] + ["2.2"]
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")
        _git(self.target, "add", "docs/ai-workflow/WORKFLOW_CONFIG.json")
        # Step 2: the Workflow-Activation: 2.2 trailer.
        subprocess.run(
            ["git", "-C", str(self.target), "commit", "-q", "-m",
             "chore: activate governing_workflow_version 2.2\n\n"
             "Workflow-Activation: 2.2\n"],
            check=True,
        )
        activated = self._config()
        self.assertEqual(activated["default_workflow_version"], "2.2")
        self.assertIn("2.2", activated["supported_versions"])
        # Loading it back through the production loader agrees.
        loaded = ws.load_config(self.target)
        self.assertEqual(loaded, activated)
        self.assertTrue(ws.is_activated(self.target))

    def test_config_missing_after_activation_is_a_hard_stop(self):
        self.test_documented_hand_edit_activates_22()
        self.config_path.unlink()
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "oops: accidentally delete the config")
        with self.assertRaises(ws.ConfigMissingAfterActivationError) as ctx:
            ws.load_config(self.target)
        self.assertIn("2.2", str(ctx.exception))

    def test_a_typo_d_rollback_trailer_value_resolves_activated_fail_closed(self):
        self.test_documented_hand_edit_activates_22()
        config = self._config()
        config["default_workflow_version"] = "2.1"
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")
        _git(self.target, "add", "docs/ai-workflow/WORKFLOW_CONFIG.json")
        subprocess.run(
            ["git", "-C", str(self.target), "commit", "-q", "-m",
             "chore: rollback, but the trailer value is a typo\n\n"
             "Workflow-Rollback: 2.2.0\n"],
            check=True,
        )
        # An unresolvable rollback trailer value resolves as activated,
        # fail-closed -- documented explicitly ("Rolling back").
        self.assertTrue(ws.is_activated(self.target))

    def test_documented_rollback_reverts_to_21_not_to_1(self):
        self.test_documented_hand_edit_activates_22()
        config = self._config()
        config["default_workflow_version"] = "2.1"
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")
        _git(self.target, "add", "docs/ai-workflow/WORKFLOW_CONFIG.json")
        subprocess.run(
            ["git", "-C", str(self.target), "commit", "-q", "-m",
             "chore: roll back governing_workflow_version 2.2\n\n"
             "Workflow-Rollback: 2.2\n"],
            check=True,
        )
        self.assertEqual(self._config()["default_workflow_version"], "2.1")
        # Still "2.1"-activated (never bare "1"): ConfigMissingAfterActivationError
        # stays armed.
        self.assertTrue(ws.is_activated(self.target))

    def test_build_activated_config_helper_matches_the_documented_edit(self):
        """The generalized helper (`D-Implementation-Review-Version-
        Activation`) is never itself the documented procedure -- checked
        separately here, on its own terms, so the two are never conflated."""
        config = self._config()
        built = ws.build_activated_config(config, target_version="2.2")
        self.assertEqual(built["default_workflow_version"], "2.2")
        self.assertIn("2.2", built["supported_versions"])
        with self.assertRaises(ws.AlreadyActivatedError):
            ws.build_activated_config(built, target_version="2.2")
        rolled_back = ws.build_rolled_back_config(built, target_version="2.2")
        self.assertEqual(rolled_back["default_workflow_version"], "2.1")


# ===========================================================================
# B. Update-path compatibility: a pre-existing repository managed under
#    2.4.0, with a live "2.1" work item mid-AWAITING_EXTERNAL_IMPLEMENTATION_
#    REVIEW, is unaffected by an update to 2.5.0 until "2.2" is explicitly
#    activated.
# ===========================================================================


class TestUpdatePathLeavesLiveV21ItemUnaffected(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.release_240 = find_release(REPO_ROOT, "2.4.0")
        self.release_250 = find_release(REPO_ROOT, "2.5.0")
        self.target = _empty_repo(Path(self._tmp.name) / "consumer")
        bootstrap(self.target, self.release_240, now=FIXED_NOW)
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "bootstrap workflow 2.4.0")
        self.state_path = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        self.config_path = self.target / "docs/ai-workflow/WORKFLOW_CONFIG.json"

    def _write_live_v21_item_mid_review(self) -> str:
        """Writes a live `"2.1"` item at
        `AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW` through the *installed*
        2.4.0 module, in a subprocess, so the bytes are whatever frozen
        2.4.0 would really produce (mirrors `test_bootstrap_e2e.py`'s own
        `_write_live_state`)."""
        scripts = str(self.target / "scripts")
        script = (
            "import sys, json\n"
            f"sys.path.insert(0, {scripts!r})\n"
            "import workflow_state as ws\n"
            "from pathlib import Path\n"
            f"root = Path({str(self.target)!r})\n"
            "def mutate(state):\n"
            "    state['active_work_item_id'] = 'legacy-item'\n"
            "    state['work_items']['legacy-item'] = {\n"
            "        'work_item_type': 'process', 'work_item_kind': 'process',\n"
            "        'work_item_id': 'legacy-item', 'parent_work_item_id': None,\n"
            "        'plan_path': 'docs/ai-workflow/legacy-item-plan.md',\n"
            "        'registry_path': None, 'mapping_path': None,\n"
            "        'governing_workflow_version': '2.1',\n"
            "        'phase': 'AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW',\n"
            "    }\n"
            "    return state\n"
            "ws.state_transaction(root, mutate)\n"
        )
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest(f"installed 2.4.0 workflow_state rejected the fixture: {proc.stderr[-800:]}")
        return self.state_path.read_text()

    def test_update_to_250_does_not_touch_the_live_21_item(self):
        before_state = self._write_live_v21_item_mid_review()
        before_config = self.config_path.read_text()
        update(self.target, self.release_250, now="2027-01-01T00:00:00Z")
        self.assertEqual(self.state_path.read_text(), before_state)
        entry = json.loads(self.state_path.read_text())["work_items"]["legacy-item"]
        self.assertEqual(entry["governing_workflow_version"], "2.1")
        self.assertEqual(entry["phase"], "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")
        # Config is untouched by the update itself: still "2.1"-default,
        # "2.2" not yet a supported version.
        self.assertEqual(self.config_path.read_text(), before_config)
        config = json.loads(before_config)
        self.assertEqual(config["default_workflow_version"], "2.1")
        self.assertNotIn("2.2", config["supported_versions"])

    def test_22_becomes_available_only_after_the_repository_explicitly_activates_it(self):
        self._write_live_v21_item_mid_review()
        update(self.target, self.release_250, now="2027-01-01T00:00:00Z")
        config = json.loads(self.config_path.read_text())
        config["default_workflow_version"] = "2.2"
        config["supported_versions"] = config["supported_versions"] + ["2.2"]
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")
        _git(self.target, "add", "docs/ai-workflow/WORKFLOW_CONFIG.json")
        subprocess.run(
            ["git", "-C", str(self.target), "commit", "-q", "-m",
             "chore: activate governing_workflow_version 2.2\n\n"
             "Workflow-Activation: 2.2\n"],
            check=True,
        )
        # The pre-existing "2.1" item is not retroactively upgraded merely
        # because the repository has now activated "2.2" for *future* items.
        entry = json.loads(self.state_path.read_text())["work_items"]["legacy-item"]
        self.assertEqual(entry["governing_workflow_version"], "2.1")


# ===========================================================================
# C. The two-stage implementation-review protocol itself, driven against a
#    disposable repository carrying the real, composed "2.2"-aware tooling
#    (`workflow_acceptance_matrix_test.py`'s own proven Scratch/Item
#    harness, reused rather than re-derived).
# ===========================================================================


class Item22(base_matrix.Item):
    """The minimal `"2.2"` extension of the base matrix's own `Item`:
    every other method already reads `governing_workflow_version` from live
    state rather than hard-coding a version, so it drives a `"2.2"` item
    unmodified (checked directly: `implement_checkpoint`, `generate_impl_
    bundle`, `recover_provenance`, `prepare_functional_review`, `mark_
    technical_approval_stale` all pass)."""

    def __init__(self, scratch, work_item_type, governing="2.2"):
        super().__init__(scratch, work_item_type, governing=governing)

    def seed(self, extra_files=None):
        """Identical to the base `seed()`, except `supported_versions`
        includes `"2.2"` from repository genesis. Activation *fidelity*
        (the documented procedure, followed with no shortcut) is proven
        exhaustively and separately, above -- this matrix's own scope,
        exactly like the base matrix's own `seed()` for `"2.1"`, is "a
        repository that has already activated this version behaves
        correctly," not "how it got there.\""""
        self.sim.write("docs/ai-workflow/WORKFLOW_CONFIG.json", json.dumps({
            "schema_version": 1,
            "default_workflow_version": self.governing,
            "supported_versions": ["1", "2.1", "2.2"],
        }, indent=2) + "\n")
        self.sim.write("docs/ai-workflow/WORKFLOW_STATE.json", json.dumps({
            "schema_version": 1, "active_work_item_id": None, "work_items": {},
        }, indent=2) + "\n")
        self.sim.write("docs/ACTIVE_MILESTONE.md", "# Active milestone\n\n(nothing yet)\n")
        self.sim.write("docs/ROADMAP.md", "# Roadmap\n")
        if self.wtype == "product":
            self.sim.write("app/src/main/kotlin/Existing.kt", "class Existing\n")
        for rel, content in (extra_files or {}).items():
            self.sim.write(rel, content)
        self.base_commit = self.sim.commit("base: repository before this work item")
        return self.base_commit

    # ---------------- two-stage implementation review ----------------

    def record_local_review(self, verdict="APPROVE", round=1,
                            review_content_id=None, bundle_id=None):
        review_content_id = review_content_id or self.impl_review_content_id(self.sim.head())[0]
        bundle_id = self.bundle_id() if bundle_id is None else bundle_id
        return self.tx(lambda state: ws.record_local_implementation_review(
            state, self.wid, verdict=verdict, bundle_id=bundle_id,
            review_content_id=review_content_id, round=round, now=self.now(),
        ))

    def record_manual_review(self, verdict="APPROVE", round=1, bundle_id=None,
                             current_review_content_id=None, feedback_role=None,
                             feedback_review_content_id=None):
        current_review_content_id = (
            current_review_content_id or self.impl_review_content_id(self.sim.head())[0]
        )
        bundle_id = self.bundle_id() if bundle_id is None else bundle_id
        feedback_role = feedback_role or ws.MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW
        feedback_review_content_id = (
            current_review_content_id if feedback_review_content_id is None
            else feedback_review_content_id
        )
        return self.tx(lambda state: ws.record_manual_implementation_review(
            state, self.wid, verdict=verdict, bundle_id=bundle_id, round=round,
            now=self.now(), current_review_content_id=current_review_content_id,
            feedback_role=feedback_role, feedback_review_content_id=feedback_review_content_id,
        ))

    def approve_implementation(self, user_confirmation=None, expect_basis="EXTERNAL_APPROVE"):
        """Base `approve_implementation`'s own shared gate check omits the
        `"2.2"`-specific `implementation_review_stages` kwargs (it has no
        `"2.2"` item to drive), so a `"2.2"` item's own real gate condition
        -- both ledger stages `APPROVE` against the *current*
        `review_content_id` -- is verified explicitly here first, calling
        the identical production function with the kwargs the real
        `/approve-review implementation` command passes for a `"2.2"`
        item, before delegating everything else (feedback/basis/commit/
        verify) to the already-proven base implementation unchanged."""
        entry = self.entry()
        if entry.get("governing_workflow_version") == "2.2":
            review_content_id, _ = self.impl_review_content_id(self.sim.head())
            if not ws.technical_approval_gate_reachable(
                latest_round_status="APPROVE", protected_path_dirty=False,
                head_matches_reviewed_implementation_head=True,
                governing_workflow_version="2.2",
                implementation_review_stages=entry.get("implementation_review_stages"),
                current_review_content_id=review_content_id,
            ):
                raise AssertionError(
                    "technical-approval gate not reachable: the '2.2' "
                    "implementation_review_stages ledger does not record both "
                    "stages APPROVE against the current review_content_id"
                )
        return super().approve_implementation(
            user_confirmation=user_confirmation, expect_basis=expect_basis,
        )


class MatrixCase22(unittest.TestCase):
    """One disposable repository per test, torn down after -- mirrors
    `workflow_acceptance_matrix_test.py`'s own `MatrixCase` exactly."""

    work_item_type = "process"

    def setUp(self):
        self.scratch = base_matrix.Scratch()
        self.addCleanup(self.scratch.cleanup)
        self.item = Item22(self.scratch, self.work_item_type)
        self.item.seed()

    # --- reusable stage helpers, each stopping at a named lifecycle point ---

    def reach_plan_approved(self):
        item = self.item
        item.milestone_plan()
        self.assertEqual(item.entry()["phase"], "AWAITING_LOCAL_PLAN_REVIEW")
        item.generate_plan_bundle()
        item.write_feedback("APPROVE")
        item.record_plan_reviews()
        self.assertEqual(item.entry()["phase"], "AWAITING_PLAN_APPROVAL")
        commit = item.approve_plan()
        self.assertEqual(item.entry()["phase"], "IMPLEMENTING")
        return commit

    def reach_awaiting_local_implementation_review(self):
        self.reach_plan_approved()
        item = self.item
        item.implement_checkpoint("CP1", {item.deliverable: "// round 1\n"})
        self.assertEqual(item.entry()["phase"], "SELF_REVIEWING_IMPLEMENTATION")
        outcome, durability, proc = item.generate_impl_bundle(
            "implementation", expect_outcome="ordinary",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(item.entry()["phase"], "AWAITING_LOCAL_IMPLEMENTATION_REVIEW")
        self.assertEqual(item.entry()["implementation_revision"], 1)
        committed = json.loads(
            self.scratch.git("show", f"{durability}:docs/ai-workflow/WORKFLOW_STATE.json").stdout
        )
        self.assertEqual(
            committed["work_items"][item.wid]["phase"], "AWAITING_LOCAL_IMPLEMENTATION_REVIEW",
        )
        return durability

    def reach_awaiting_manual_review(self):
        durability = self.reach_awaiting_local_implementation_review()
        self.item.record_local_review("APPROVE")
        self.assertEqual(
            self.item.entry()["phase"], "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW",
        )
        return durability

    def reach_awaiting_external_implementation_review(self):
        self.reach_awaiting_manual_review()
        self.item.record_manual_review("APPROVE")
        self.assertEqual(self.item.entry()["phase"], "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")

    def reach_technical_approved(self):
        self.reach_awaiting_external_implementation_review()
        self.item.write_feedback("APPROVE")
        commit = self.item.approve_implementation()
        self.assertEqual(self.item.entry()["phase"], "AWAITING_FUNCTIONAL_REVIEW")
        return commit


# --------------------------- C1. Positive path -----------------------------


class TestPositiveTwoStagePath(MatrixCase22):
    def test_local_approve_manual_approve_technical_approval(self):
        self.reach_technical_approved()
        entry = self.item.entry()
        self.assertEqual(entry["technical_approval"]["status"], "CURRENT")
        stages = ws.normalize_implementation_review_stages(entry["implementation_review_stages"])
        self.assertEqual(stages[ws.LOCAL_MODEL_IMPLEMENTATION_REVIEW]["verdict"], "APPROVE")
        self.assertEqual(stages[ws.MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW]["verdict"], "APPROVE")


# --------------------------- C2. Negative paths -----------------------------


class TestNegativeImplementationReviewPaths(MatrixCase22):
    def test_local_revise_loops_back_through_applying_review_feedback(self):
        self.reach_awaiting_local_implementation_review()
        item = self.item
        item.record_local_review("REVISE")
        self.assertEqual(item.entry()["phase"], "APPLYING_REVIEW_FEEDBACK")
        self.assertNotEqual(item.entry()["phase"], "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW")
        self.scratch.write(item.deliverable, "// fixed round 1\n")
        self.scratch.commit(f"fix({item.wid}): address local finding",
                            {"Workflow-Work-Item": item.wid})
        outcome, durability, proc = item.generate_impl_bundle("post-fix", expect_outcome="ordinary")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(item.entry()["phase"], "AWAITING_LOCAL_IMPLEMENTATION_REVIEW")
        self.assertEqual(item.entry()["implementation_revision"], 2)

    def test_local_block_is_a_true_no_op(self):
        self.reach_awaiting_local_implementation_review()
        item = self.item
        before = item.entry()
        item.record_local_review("BLOCK")
        self.assertEqual(item.entry(), before)

    def test_manual_revise_loops_back_through_applying_review_feedback(self):
        self.reach_awaiting_manual_review()
        item = self.item
        item.record_manual_review("REVISE")
        self.assertEqual(item.entry()["phase"], "APPLYING_REVIEW_FEEDBACK")
        self.scratch.write(item.deliverable, "// fixed after manual finding\n")
        self.scratch.commit(f"fix({item.wid}): address manual finding",
                            {"Workflow-Work-Item": item.wid})
        outcome, durability, proc = item.generate_impl_bundle("post-fix", expect_outcome="ordinary")
        self.assertEqual(proc.returncode, 0)
        # A manual REVISE also lands back at the *local* stage: no path
        # re-enters manual review without a fresh local pass first.
        self.assertEqual(item.entry()["phase"], "AWAITING_LOCAL_IMPLEMENTATION_REVIEW")

    def test_manual_block_is_a_true_no_op(self):
        self.reach_awaiting_manual_review()
        item = self.item
        before = item.entry()
        item.record_manual_review("BLOCK")
        self.assertEqual(item.entry(), before)

    def test_manual_review_before_local_approve_refuses_wrong_phase(self):
        self.reach_awaiting_local_implementation_review()
        with self.assertRaises(ws.WrongPhaseForImplementationReviewStageError):
            self.item.record_manual_review("APPROVE")

    def test_local_review_from_the_wrong_phase_refuses(self):
        self.reach_plan_approved()
        with self.assertRaises(ws.WrongPhaseForImplementationReviewStageError):
            self.item.record_local_review("APPROVE")

    def test_two_stage_ledger_refuses_for_a_21_item(self):
        """`WrongGoverningVersionForImplementationReviewStageError`: the
        two-stage *implementation*-review ledger is `"2.2"`-only, unlike
        the plan-review ledger, which both `"2.1"`/`"2.2"` share."""
        scratch = base_matrix.Scratch()
        self.addCleanup(scratch.cleanup)
        item21 = base_matrix.Item(scratch, "process", governing="2.1")
        item21.seed()
        item21.milestone_plan()
        item21.generate_plan_bundle()
        item21.write_feedback("APPROVE")
        item21.record_plan_reviews()
        item21.approve_plan()
        item21.implement_checkpoint("CP1", {item21.deliverable: "// round 1\n"})
        item21.generate_impl_bundle("implementation", expect_outcome="ordinary")
        self.assertEqual(item21.entry()["phase"], "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")
        review_content_id, _ = fingerprint.compute_review_content_id_implementation_stage_at_commit(
            item21.root, item21.base_commit, scratch.head(), "process", item21.wid,
            *item21.impl_classification(),
        )
        with self.assertRaises(ws.WrongGoverningVersionForImplementationReviewStageError):
            ws.state_transaction(item21.root, lambda state: ws.record_local_implementation_review(
                state, item21.wid, verdict="APPROVE", bundle_id=item21.bundle_id(),
                review_content_id=review_content_id, round=1, now="t",
            ))

    def test_stale_review_content_id_hard_blocks_manual_ingestion(self):
        """A bundle regeneration between the local approval and the manual
        paste changes the live `review_content_id`; the manual stage's own
        recorded value (what the local stage actually approved) is now
        stale against it -- a hard block (`StaleReviewContentIdError`),
        unlike the advisory-only `bundle_id` check below."""
        self.reach_awaiting_manual_review()
        item = self.item
        stale_review_content_id = ws.normalize_implementation_review_stages(
            item.entry()["implementation_review_stages"],
        )["review_content_id"]
        self.scratch.write(item.deliverable, "// accidental regeneration\n")
        self.scratch.commit(f"chore({item.wid}): accidental bundle regeneration",
                            {"Workflow-Work-Item": item.wid})
        fresh_review_content_id, _ = item.impl_review_content_id(self.scratch.head())
        self.assertNotEqual(fresh_review_content_id, stale_review_content_id)
        with self.assertRaises(ws.StaleReviewContentIdError):
            item.record_manual_review(
                "APPROVE",
                current_review_content_id=fresh_review_content_id,
                feedback_review_content_id=stale_review_content_id,
            )
        self.assertEqual(
            item.entry()["phase"], "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW",
        )

    def test_duplicate_manual_ingestion_is_refused(self):
        """`DuplicateManualImplementationStageIngestionError`: a second
        manual ingestion against the same `review_content_id`, with the
        phase somehow still (or again) `AWAITING_MANUAL_EXTERNAL_
        IMPLEMENTATION_REVIEW`, is refused rather than silently re-recorded
        -- reconstructed here by resetting the durable phase back after a
        genuine manual approval, the only way to make the contended state
        (ledger already recorded, phase still pending) reachable at all."""
        self.reach_awaiting_manual_review()
        item = self.item
        item.record_manual_review("APPROVE")
        self.assertEqual(item.entry()["phase"], "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")
        item.tx(lambda state: {
            **state,
            "work_items": {
                **state["work_items"],
                item.wid: {
                    **state["work_items"][item.wid],
                    "phase": "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW",
                },
            },
        })
        with self.assertRaises(ws.DuplicateManualImplementationStageIngestionError):
            item.record_manual_review("APPROVE")

    def test_bundle_id_mismatch_at_the_manual_stage_is_advisory_only(self):
        """`check_manual_stage_bundle_id_advisory`: a wrapper-only bundle
        regeneration between upload and paste (new `bundle_id`, unchanged
        `review_content_id`) must not invalidate the manual stage."""
        self.reach_awaiting_manual_review()
        item = self.item
        current_bundle_id = item.bundle_id()
        warning = ws.check_manual_stage_bundle_id_advisory("a-different-bundle-id", current_bundle_id)
        self.assertIsNotNone(warning)
        self.assertIn("advisory only", warning)
        # And the state writer itself never blocks on it -- the ledger
        # records the reviewer's own bundle_id verbatim regardless.
        item.record_manual_review("APPROVE", bundle_id="a-different-bundle-id")
        self.assertEqual(item.entry()["phase"], "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")
        stages = ws.normalize_implementation_review_stages(item.entry()["implementation_review_stages"])
        self.assertEqual(stages[ws.MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW]["bundle_id"], "a-different-bundle-id")


# --------------------- C3. /recover-implementation-provenance ---------------


class TestRecoverImplementationProvenanceFromEachPhase(MatrixCase22):
    """B1(a)'s recovery-path clause and B2's committed-phase membership
    test, resolved at every one of the three phases a `"2.2"` item can
    occupy between a generation-record commit `T` and technical approval."""

    def _recover_and_assert_phase_unchanged(self, expected_phase):
        item = self.item
        self.scratch.write(item.excluded_note, "# ledger\n\nconcurrent excluded-only note.\n")
        self.scratch.commit(f"docs({item.wid}): concurrent excluded-only commit",
                            {"Workflow-Work-Item": item.wid})
        superseded, s2, proc = item.recover_provenance()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(item.entry()["phase"], expected_phase)
        self.assertEqual(
            ws.verify_implementation_provenance_interval(item.root, item.entry(), item.base_commit),
            s2,
        )

    def test_recovery_from_awaiting_local_implementation_review(self):
        self.reach_awaiting_local_implementation_review()
        self._recover_and_assert_phase_unchanged("AWAITING_LOCAL_IMPLEMENTATION_REVIEW")

    def test_recovery_from_awaiting_manual_external_implementation_review(self):
        self.reach_awaiting_manual_review()
        self._recover_and_assert_phase_unchanged("AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW")

    def test_recovery_from_the_terminal_awaiting_external_implementation_review(self):
        self.reach_awaiting_external_implementation_review()
        self._recover_and_assert_phase_unchanged("AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")

    def test_recovery_is_not_applicable_when_content_genuinely_changed(self):
        self.reach_awaiting_local_implementation_review()
        item = self.item
        self.scratch.write(item.deliverable, "// genuinely different content\n")
        self.scratch.commit(f"feat({item.wid}): a real content change",
                            {"Workflow-Work-Item": item.wid})
        with self.assertRaises(ws.ImplementationProvenanceRecoveryNotApplicableError):
            ws.verify_implementation_provenance_recovery(
                item.root, item.entry(), base_commit=item.base_commit, head=self.scratch.head(),
            )


# --------------- C4. "2.2" functional-review bounded-fix scenario ----------


class TestFunctionalReviewBoundedFixRoutesThroughBothStagesAgain(MatrixCase22):
    """Resolves I2: for a `"2.2"` item, `/apply-functional-review`'s
    bounded-fix branch regenerates to `AWAITING_LOCAL_IMPLEMENTATION_REVIEW`,
    never straight back to the terminal phase -- a fresh two-stage pass is
    required before `/approve-review implementation` is reachable again."""

    def test_bounded_fix_reopens_both_implementation_review_stages(self):
        self.reach_technical_approved()
        item = self.item
        item.prepare_functional_review()
        item.write_functional_findings("Finding 1: the label is wrong.\n")
        fingerprint.assert_functional_review_not_already_consumed(item.root, item.wid)

        item.mark_technical_approval_stale()
        self.assertEqual(item.entry()["technical_approval"]["status"], "STALE")
        self.scratch.write(item.deliverable, "// functional fix\n")
        self.scratch.commit(f"fix({item.wid}): functional finding 1",
                            {"Workflow-Work-Item": item.wid})
        outcome, durability, proc = item.generate_impl_bundle("post-fix", expect_outcome="ordinary")
        self.assertEqual(proc.returncode, 0)
        # Never straight back to the terminal phase.
        self.assertEqual(item.entry()["phase"], "AWAITING_LOCAL_IMPLEMENTATION_REVIEW")
        self.assertEqual(item.entry()["implementation_revision"], 2)
        fingerprint.mark_functional_review_consumed(item.root, item.wid)

        # /approve-review implementation is not reachable yet: a fresh
        # local-then-manual pass is required first.
        with self.assertRaises(ws.WrongPhaseForImplementationReviewStageError):
            item.record_manual_review("APPROVE")
        item.record_local_review("APPROVE")
        self.assertEqual(item.entry()["phase"], "AWAITING_MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW")
        item.record_manual_review("APPROVE")
        self.assertEqual(item.entry()["phase"], "AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")

        item.write_feedback("APPROVE")
        item.approve_implementation()
        self.assertEqual(item.entry()["technical_approval"]["status"], "CURRENT")
        self.assertEqual(item.entry()["phase"], "AWAITING_FUNCTIONAL_REVIEW")


# --------------- C5. CP7's generic declaration-coverage helper --------------


class TestDeclarationCoverageHelperAgainstSyntheticItem(MatrixCase22):
    """CP7's own `assert_declaration_coverage`/`find_declaration_symmetry_
    gaps` (`D-Canonical-Review-Data`), exercised directly against this
    file's own synthetic `"2.2"` work item rather than a second hand-written
    copy of the check."""

    def test_synthetic_item_declarations_are_symmetric_and_self_consistent(self):
        self.item.milestone_plan()
        wst.assert_declaration_coverage(self.item.wid, self.item.root)

    def test_find_declaration_symmetry_gaps_is_clean_for_the_generated_declarations(self):
        self.item.milestone_plan()
        declarations = json.loads((self.item.root / self.item.artifacts_path).read_text())
        direction_a, direction_b = wst.find_declaration_symmetry_gaps(
            declarations["plan_stage"], declarations["implementation_stage"],
        )
        self.assertEqual(direction_a, [])
        self.assertEqual(direction_b, [])


# --------------- C6. CP9's backlog fixes, against a live scenario -----------


class TestCP9FixesAgainstADisposableRepoScenario(MatrixCase22):
    """CP9's four backlog fixes (`docs/defects/v2.3.1-001`,
    `v2.3.1-003`, the `v2.5.0` `portability_exceptions.json` entry,
    `v2.4.0-001`'s implementation-stage symmetry widening) are each already
    proven hermetically by their own unit tests, and the *first three* are
    additionally proven against a real bootstrapped-on-2.5.0 disposable
    repository by `tests/test_bootstrap_e2e.py`'s own
    `TestBootstrappedRepositorySatisfiesTheFrozenSuite250` (it runs the
    complete frozen suite -- `workflow_state_test.py`, `workflow_integration
    _test.py` included -- against exactly that repository, and asserts zero
    undocumented failures). The fourth (the widened implementation-stage
    `.workflow-manager/` exclusion) is proven here specifically at the
    disposable-repo level: a live checkpoint commit in a repository whose
    own `.workflow-manager/installation.json` bootstrap bookkeeping sits
    right next to the synthetic item's own deliverable must not be blocked
    by it."""

    def test_workflow_manager_installation_record_is_excluded_at_implementation_stage(self):
        item = self.item
        item.milestone_plan()
        declarations = json.loads((item.root / item.artifacts_path).read_text())
        self.assertIn(
            ".workflow-manager/", declarations["implementation_stage"].get("excluded_prefixes", {}),
        )

    def test_a_live_workflow_manager_bookkeeping_write_never_blocks_a_checkpoint(self):
        self.reach_plan_approved()
        item = self.item
        # Stands in for workflow_manager's own installation-record write --
        # not this or any other work item's implementation-stage
        # deliverable, so it must never register as a dirty protected path.
        self.scratch.write(".workflow-manager/installation.json", json.dumps({
            "workflow_version": "2.5.0", "installed_at": FIXED_NOW,
        }) + "\n")
        self.scratch.commit("chore: workflow_manager installation bookkeeping (concurrent)")
        classification = item.impl_classification()
        self.assertFalse(ws.any_protected_path_dirty(item.root, *classification))
        item.implement_checkpoint("CP1", {item.deliverable: "// round 1\n"})
        self.assertEqual(item.entry()["phase"], "SELF_REVIEWING_IMPLEMENTATION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
