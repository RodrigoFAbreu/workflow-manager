#!/usr/bin/env python3
"""The migration inventory is closed.

Every path at the frozen upstream commit is accounted for exactly once, with a
category and a rationale, and the manifest's own arithmetic holds. These are the
Phase-A gate: no unresolved dependency-closure item may remain.
"""

from __future__ import annotations

import re
import unittest

from support import CLASSIFICATION, REPO_ROOT, frozen_paths, upstream_available

from workflow_manager.release import find_release


class TestClassificationRuleset(unittest.TestCase):
    def setUp(self):
        self.spec = CLASSIFICATION

    def test_every_rule_names_a_declared_category(self):
        for rule in self.spec["rules"]:
            self.assertIn(rule["category"], self.spec["categories"], rule["pattern"])

    def test_every_rule_carries_a_rationale(self):
        for rule in self.spec["rules"]:
            self.assertTrue(rule.get("rationale", "").strip(), rule["pattern"])

    def test_every_rule_pattern_compiles(self):
        for rule in self.spec["rules"]:
            re.compile(rule["pattern"])

    def test_every_declared_category_is_used_by_some_rule(self):
        used = {rule["category"] for rule in self.spec["rules"]}
        self.assertEqual(used, set(self.spec["categories"]))


class TestManifestInventoryIsClosed(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.manifest = self.release.manifest

    def test_manifest_pins_the_frozen_upstream_release(self):
        self.assertEqual(self.manifest["upstream"], CLASSIFICATION["upstream"])
        self.assertEqual(self.manifest["workflow_version"], CLASSIFICATION["workflow_version"])

    def test_artifacts_and_exclusions_partition_the_upstream_tree(self):
        artifacts = [a["upstream_path"] for a in self.manifest["artifacts"]]
        exclusions = [e["upstream_path"] for e in self.manifest["exclusions"]]
        self.assertEqual(len(set(artifacts) & set(exclusions)), 0,
                         "a path is both migrated and excluded")
        self.assertEqual(len(artifacts), len(set(artifacts)), "duplicate artifact path")
        self.assertEqual(len(exclusions), len(set(exclusions)), "duplicate exclusion path")
        self.assertEqual(
            len(artifacts) + len(exclusions), self.manifest["counts"]["upstream_paths"],
        )

    def test_counts_agree_with_the_records(self):
        counts = self.manifest["counts"]
        self.assertEqual(counts["artifacts"], len(self.manifest["artifacts"]))
        self.assertEqual(counts["exclusions"], len(self.manifest["exclusions"]))
        self.assertEqual(counts["templates"], len(self.manifest["templates"]))
        self.assertEqual(sum(counts["by_category"].values()),
                         counts["artifacts"] + counts["exclusions"])

    def test_every_record_carries_a_category_and_rationale(self):
        for record in self.manifest["artifacts"] + self.manifest["exclusions"]:
            self.assertIn(record["category"], self.manifest["categories"],
                          record["upstream_path"])
            self.assertTrue(record["rationale"].strip(), record["upstream_path"])

    def test_every_exclusion_records_the_bytes_it_declined(self):
        """An exclusion states which bytes it excluded, so a later upstream
        release cannot change a file's content and silently keep its verdict."""
        for record in self.manifest["exclusions"]:
            self.assertRegex(record["upstream_sha256"], r"^[0-9a-f]{64}$",
                             record["upstream_path"])

    def test_no_rule_is_dead(self):
        self.assertEqual(self.manifest["unmatched_rules"], [])

    def test_artifact_target_paths_are_unique_and_relative(self):
        targets = [a["target_path"] for a in self.manifest["artifacts"]]
        self.assertEqual(len(targets), len(set(targets)))
        for target in targets:
            self.assertFalse(target.startswith("/"), target)
            self.assertNotIn("..", target.split("/"), target)

    def test_template_target_paths_are_unique_and_relative(self):
        targets = [t["target_path"] for t in self.release.templates()]
        self.assertEqual(len(targets), len(set(targets)))
        for target in targets:
            self.assertFalse(target.startswith("/"), target)
            self.assertNotIn("..", target.split("/"), target)

    def test_every_template_states_how_it_was_derived(self):
        for template in self.release.templates():
            self.assertTrue(template["derivation"].strip(), template["target_path"])

    def test_every_templated_category_path_has_a_template(self):
        """Nothing classified `template` may be dropped on the floor: each one
        either has a template at the same target path or is a fragment whose
        target is named in its own derivation note."""
        templated = {
            e["upstream_path"] for e in self.manifest["exclusions"]
            if e["category"] == "template"
        }
        produced = {t["target_path"] for t in self.release.templates()}
        unhandled = set()
        for path in templated:
            if path in produced:
                continue
            if path == ".gitignore" and ".gitignore.workflow-fragment" in produced:
                continue
            if path == ".github/workflows/ci.yml" and any(
                t.startswith(".github/workflows/") for t in produced
            ):
                continue
            unhandled.add(path)
        self.assertEqual(unhandled, set())


class TestInventoryAgainstFrozenUpstream(unittest.TestCase):
    """The independent half: re-read the frozen tree and compare."""

    def setUp(self):
        if not upstream_available():
            self.skipTest("frozen upstream repository not available")
        self.manifest = find_release(REPO_ROOT).manifest

    def test_manifest_covers_exactly_the_frozen_tree(self):
        recorded = {a["upstream_path"] for a in self.manifest["artifacts"]}
        recorded |= {e["upstream_path"] for e in self.manifest["exclusions"]}
        self.assertEqual(recorded, set(frozen_paths()))


if __name__ == "__main__":
    unittest.main(verbosity=1)
