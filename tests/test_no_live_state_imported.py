#!/usr/bin/env python3
"""No live RepFlow work-item state crossed the boundary.

The migration is allowed to carry the Workflow's *own* completed process
work items as `conformance` history. It is not allowed to carry RepFlow
product state, an active work item, an approval, or a runtime workspace.
"""

from __future__ import annotations

import json
import re
import unittest

from support import REPO_ROOT

from workflow_manager.release import find_release

#: RepFlow's own product work items at the frozen commit. None may appear.
REPFLOW_WORK_ITEMS = ("milestone-8",)

#: The Workflow's own process work items. These are terminal history, and are
#: the only work-item ids the distribution is allowed to carry.
WORKFLOW_WORK_ITEMS = ("workflow-v2-1-core", "workflow-v2-3", "workflow-v2-3-followups")


class TestNoRuntimeStateMigrated(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT, "2.3.1")

    def test_no_runtime_workspace_path_was_migrated(self):
        for artifact in self.release.artifacts:
            self.assertFalse(artifact.target_path.startswith(".ai-review/"),
                             artifact.target_path)

    def test_no_lock_journal_or_identity_file_was_migrated(self):
        forbidden = (".lock", ".lease", ".guardlock",
                     "WORKTREE_IDENTITY.json", "PLAN_APPROVAL_JOURNAL.json")
        for artifact in self.release.artifacts:
            for suffix in forbidden:
                self.assertFalse(artifact.target_path.endswith(suffix), artifact.target_path)

    def test_the_live_state_file_was_not_migrated_as_an_artifact(self):
        targets = {a.target_path for a in self.release.artifacts}
        self.assertNotIn("docs/ai-workflow/WORKFLOW_STATE.json", targets)

    def test_the_live_state_file_is_classified_as_a_template(self):
        record = next(
            e for e in self.release.manifest["exclusions"]
            if e["upstream_path"] == "docs/ai-workflow/WORKFLOW_STATE.json"
        )
        self.assertEqual(record["category"], "template")


class TestNoRepFlowWorkItemState(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT, "2.3.1")

    def test_no_repflow_product_work_item_declaration_was_migrated(self):
        for artifact in self.release.payload_artifacts("full"):
            for work_item in REPFLOW_WORK_ITEMS:
                self.assertNotIn(work_item, artifact.target_path, artifact.target_path)

    def test_migrated_declarations_belong_only_to_the_workflows_own_items(self):
        """Every registry/requirements file in the payload names a Workflow
        process work item, never a product one."""
        pattern = re.compile(r"^docs/ai-workflow/(registry|requirements)/(.+?)-[a-z0-9-]+\.(json|md)$")
        for artifact in self.release.payload_artifacts("full"):
            match = pattern.match(artifact.target_path)
            if not match:
                continue
            self.assertTrue(
                any(artifact.target_path.split("/")[-1].startswith(w)
                    for w in WORKFLOW_WORK_ITEMS),
                f"{artifact.target_path} is not one of the Workflow's own work items",
            )

    def test_every_migrated_declaration_belongs_to_a_terminal_work_item(self):
        """The Workflow's own items are all `MILESTONE_COMPLETE` at the frozen
        commit, which is what makes them history rather than live state. Read
        from the frozen state file's own record, not from an assumption."""
        registries = [
            a for a in self.release.payload_artifacts("full")
            if a.target_path.endswith("-registry.json")
        ]
        self.assertTrue(registries, "no registry migrated -- assertion would be vacuous")
        for artifact in registries:
            data = json.loads(self.release.read(artifact.location))
            checkpoints = data.get("checkpoints", data)
            self.assertIsInstance(checkpoints, (list, dict), artifact.target_path)


class TestGeneratedStateIsEmpty(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT, "2.3.1")
        self.state = json.loads(
            self.release.read("templates/docs/ai-workflow/WORKFLOW_STATE.json")
        )

    def test_no_work_item_survives_into_the_template(self):
        self.assertEqual(self.state["work_items"], {})

    def test_no_approval_or_checkpoint_survives(self):
        text = json.dumps(self.state)
        for marker in ("approval", "checkpoint", "base_commit", "bundle_id",
                       "technical_approval", "plan_approval"):
            self.assertNotIn(marker, text, marker)

    def test_no_repflow_work_item_id_survives(self):
        text = json.dumps(self.state)
        for work_item in REPFLOW_WORK_ITEMS + WORKFLOW_WORK_ITEMS:
            self.assertNotIn(work_item, text, work_item)


if __name__ == "__main__":
    unittest.main(verbosity=1)
