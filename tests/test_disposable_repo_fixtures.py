#!/usr/bin/env python3
"""CP7 (`plan-amendment-mechanism`): disposable-repository fixtures for
`IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION`.

`workflow_manager.fixture.drive_synthetic_work_item_through_checkpoints`
scripts the *installed* `workflow_state`/`workflow_fingerprint` modules --
the same technique `test_bootstrap_e2e.py`'s own `_write_live_state` already
uses for a single `PLANNING`-phase item -- to land a `build_target_repo`
fixture in `IMPLEMENTING` (a proper checkpoint prefix complete) or
`SELF_REVIEWING_IMPLEMENTATION` (every checkpoint complete), with a real,
reachable plan-approval commit and one real checkpoint commit per
completed checkpoint.

This suite proves the fixture itself is trustworthy -- not the update-path
scenarios CP8 builds on top of it (`docs/ai-workflow/PLAN_AMENDMENT_
MECHANISM_PLAN.md` section 4, scenarios 2/3 and beyond)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

from workflow_manager.fixture import build_target_repo, drive_synthetic_work_item_through_checkpoints
from workflow_manager.release import find_release


class _DisposableRepoFixtureTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.release = find_release(REPO_ROOT, "2.3.1")
        self.root = build_target_repo(self.release, Path(self._tmp.name) / "repo")

    def _entry(self, work_item_id: str) -> dict:
        state = json.loads((self.root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())
        return state["work_items"][work_item_id]

    def _import_installed(self, name: str):
        scripts_dir = str(self.root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        sys.modules.pop(name, None)
        return __import__(name)


class TestDriveToImplementing(_DisposableRepoFixtureTestCase):
    def test_lands_in_implementing_with_a_proper_checkpoint_prefix_complete(self):
        result = drive_synthetic_work_item_through_checkpoints(
            self.root, work_item_id="fixture-implementing",
            checkpoint_ids=("CP1", "CP2", "CP3"), complete_checkpoint_ids=("CP1", "CP2"),
        )
        self.assertEqual(result["phase"], "IMPLEMENTING")
        entry = self._entry("fixture-implementing")
        self.assertEqual(entry["phase"], "IMPLEMENTING")
        self.assertEqual(entry["checkpoints"]["CP1"]["status"], "COMPLETE")
        self.assertEqual(entry["checkpoints"]["CP2"]["status"], "COMPLETE")
        self.assertNotIn("CP3", entry["checkpoints"])
        self.assertEqual(entry["plan_approval"]["status"], "CURRENT")

    def test_implementing_entry_reachable_holds_for_the_fixture(self):
        result = drive_synthetic_work_item_through_checkpoints(
            self.root, work_item_id="fixture-reachable",
            checkpoint_ids=("CP1", "CP2"), complete_checkpoint_ids=("CP1",),
        )
        ws = self._import_installed("workflow_state")
        entry = self._entry("fixture-reachable")
        self.assertTrue(
            ws.implementing_entry_reachable(self.root, entry, result["base_commit"]),
        )

    def test_the_plan_approval_commit_is_discoverable_by_its_trailer(self):
        result = drive_synthetic_work_item_through_checkpoints(
            self.root, work_item_id="fixture-discoverable",
            checkpoint_ids=("CP1", "CP2"), complete_checkpoint_ids=("CP1",),
        )
        ws = self._import_installed("workflow_state")
        entry = self._entry("fixture-discoverable")
        discovered = ws.discover_plan_approval_commit(
            self.root, "fixture-discoverable",
            entry["plan_approval"]["approved_review_content_id"], result["base_commit"],
        )
        self.assertEqual(discovered, result["approval_commit"])

    def test_a_non_prefix_complete_set_is_refused(self):
        with self.assertRaises(ValueError):
            drive_synthetic_work_item_through_checkpoints(
                self.root, work_item_id="fixture-bad-prefix",
                checkpoint_ids=("CP1", "CP2", "CP3"), complete_checkpoint_ids=("CP2",),
            )


class TestDriveToSelfReviewingImplementation(_DisposableRepoFixtureTestCase):
    def test_lands_in_self_reviewing_implementation_with_every_checkpoint_complete(self):
        result = drive_synthetic_work_item_through_checkpoints(
            self.root, work_item_id="fixture-self-reviewing",
            checkpoint_ids=("CP1", "CP2"), complete_checkpoint_ids=("CP1", "CP2"),
        )
        self.assertEqual(result["phase"], "SELF_REVIEWING_IMPLEMENTATION")
        entry = self._entry("fixture-self-reviewing")
        self.assertEqual(entry["phase"], "SELF_REVIEWING_IMPLEMENTATION")
        for cid in ("CP1", "CP2"):
            self.assertEqual(entry["checkpoints"][cid]["status"], "COMPLETE")

    def test_each_completed_checkpoint_has_its_own_discoverable_commit(self):
        result = drive_synthetic_work_item_through_checkpoints(
            self.root, work_item_id="fixture-checkpoint-commits",
            checkpoint_ids=("CP1", "CP2"), complete_checkpoint_ids=("CP1", "CP2"),
        )
        ws = self._import_installed("workflow_state")
        discovered = ws.discover_checkpoint_commits(
            self.root, "fixture-checkpoint-commits", result["base_commit"],
        )
        self.assertEqual(set(discovered), {"CP1", "CP2"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
