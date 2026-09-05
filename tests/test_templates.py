#!/usr/bin/env python3
"""Templates are deterministic, clean, and honour the frozen contracts.

A template is the one place this migration writes bytes that are not the
frozen release's. Each one has to be reproducible, free of RepFlow work-item
state, and accepted by the frozen code that reads it.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT, frozen_bytes, upstream_available

from workflow_manager.release import find_release, sha256

sys.path.insert(0, str(REPO_ROOT / "tools"))
import migrate  # noqa: E402


def _load_payload_module(release, name):
    """Import a module out of the payload, the way an installed target would.

    `workflow_state` imports `workflow_fingerprint` by bare name, exactly as it
    does when run from an installed `scripts/`, so the payload's script
    directory goes on `sys.path` first.
    """
    scripts = release.root / "payload" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestTemplateGenerationIsDeterministic(unittest.TestCase):
    def setUp(self):
        if not upstream_available():
            self.skipTest("frozen upstream repository not available")
        self.commit = migrate.json.loads(
            (REPO_ROOT / "migration" / "classification.json").read_text()
        )["upstream"]["commit"]
        self.upstream = migrate.DEFAULT_UPSTREAM

    def test_two_generations_produce_identical_bytes(self):
        first = migrate.build_templates(self.upstream, self.commit)
        second = migrate.build_templates(self.upstream, self.commit)
        self.assertEqual(
            {k: v["bytes"] for k, v in first.items()},
            {k: v["bytes"] for k, v in second.items()},
        )

    def test_generated_bytes_match_what_is_committed(self):
        release = find_release(REPO_ROOT)
        generated = migrate.build_templates(self.upstream, self.commit)
        committed = {t["target_path"]: release.read(t["location"]) for t in release.templates()}
        self.assertEqual({k: v["bytes"] for k, v in generated.items()}, committed)

    def test_a_full_re_extraction_is_byte_stable(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = migrate.migrate(self.upstream, Path(a))
            second = migrate.migrate(self.upstream, Path(b))
            self.assertEqual(first, second)
            self.assertEqual(migrate._tree_digest(Path(a)), migrate._tree_digest(Path(b)))


class TestStateTemplateHonoursTheFrozenContract(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.ws = _load_payload_module(self.release, "workflow_state")
        self.state_bytes = self.release.read(
            "templates/docs/ai-workflow/WORKFLOW_STATE.json"
        )

    def test_template_is_the_migrated_modules_own_canonical_serialization(self):
        """The generator reimplements `_serialize_state` so it need not import
        what it is generating. This proves the two agree."""
        parsed = json.loads(self.state_bytes)
        self.assertEqual(self.state_bytes, self.ws._serialize_state(parsed))

    def test_template_passes_the_frozen_state_validator(self):
        self.ws.validate_state(json.loads(self.state_bytes))

    def test_template_carries_no_work_item_and_no_active_pointer(self):
        parsed = json.loads(self.state_bytes)
        self.assertEqual(parsed["work_items"], {})
        self.assertIsNone(parsed["active_work_item_id"])
        self.assertEqual(parsed["schema_version"], self.ws.SCHEMA_VERSION)

    def test_template_carries_no_repflow_commit_shas(self):
        text = self.state_bytes.decode()
        self.assertEqual(re.findall(r"\b[0-9a-f]{40}\b", text), [])


class TestConfigTemplateHonoursTheFrozenContract(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.ws = _load_payload_module(self.release, "workflow_state")
        self.config_bytes = self.release.read(
            "templates/docs/ai-workflow/WORKFLOW_CONFIG.json"
        )

    def test_template_passes_the_frozen_config_validator(self):
        self.ws.validate_config(json.loads(self.config_bytes))

    def test_template_is_byte_identical_to_the_frozen_config(self):
        """Declared as an identity transformation in the manifest, so it has to
        actually be one."""
        if not upstream_available():
            self.skipTest("frozen upstream repository not available")
        self.assertEqual(
            self.config_bytes, frozen_bytes("docs/ai-workflow/WORKFLOW_CONFIG.json"),
        )

    def test_manifest_records_the_identity_derivation(self):
        record = next(
            t for t in self.release.templates()
            if t["target_path"] == "docs/ai-workflow/WORKFLOW_CONFIG.json"
        )
        self.assertTrue(record["derivation"].startswith("identity:"), record["derivation"])


class TestActiveMilestoneTemplateIsClean(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.text = self.release.read("templates/docs/ACTIVE_MILESTONE.md").decode()

    def test_it_is_the_path_the_frozen_code_contracts_on(self):
        ws = _load_payload_module(self.release, "workflow_state")
        self.assertEqual(ws.FUNCTIONAL_CHECKLIST_PATH, "docs/ACTIVE_MILESTONE.md")

    def test_it_carries_no_repflow_narrative(self):
        for marker in ("RepFlow", "Milestone 8", "futsal", "Room", "Gradle", "Android",
                       "Status note (2026-", "workflow-v2-1-core"):
            self.assertNotIn(marker, self.text, marker)

    def test_it_states_no_active_work(self):
        self.assertIn("None.", self.text)
        self.assertEqual(re.findall(r"\b[0-9a-f]{40}\b", self.text), [])


class TestClaudeMdTemplateIsClean(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.text = self.release.read("templates/CLAUDE.md").decode()

    def test_it_carries_no_repflow_product_guidance(self):
        for marker in ("RepFlow", "Room", "Hilt", "Compose", "Gradle", "Android",
                       "offline-first", "docs/adr/", "DOMAIN_GLOSSARY"):
            self.assertNotIn(marker, self.text, marker)

    def test_it_never_names_the_retired_command(self):
        """`workflow_integration_test.py`'s LIVE_DOCS lint reads CLAUDE.md; a
        template that never mentions the retired command satisfies it without
        asserting anything untrue."""
        self.assertNotIn("accept-scoped-remediation", self.text)
        self.assertNotIn("scoped_remediation", self.text)

    def test_it_marks_where_the_managed_section_ends(self):
        self.assertIn("<!-- workflow-manager:end -->", self.text)

    def test_it_does_not_hardcode_a_gate_count(self):
        """The frozen CLAUDE.md contract: point at MILESTONE_WORKFLOW.md's own
        'Hard gates summary' rather than restating a number that goes stale as
        the workflow evolves."""
        self.assertIn("Hard gates summary", self.text)
        gate_sentences = [
            line for line in self.text.splitlines()
            if "gate" in line.lower() and re.search(r"\b\d+\b", line)
        ]
        self.assertEqual(gate_sentences, [], "a gate count is written into the template")


class TestGitignoreFragment(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.text = self.release.read("templates/.gitignore.workflow-fragment").decode()

    def test_it_ignores_the_runtime_workspace(self):
        """`.ai-review/` holds bundles, locks and the worktree identity. The
        frozen suite's own scratch repositories ignore it too."""
        self.assertIn(".ai-review/", self.text.splitlines())

    def test_it_carries_no_android_or_gradle_entries(self):
        for marker in ("gradle", "local.properties", ".kotlin", "*.jks", ".idea"):
            self.assertNotIn(marker, self.text)

    def test_it_is_a_fragment_not_a_replacement(self):
        record = next(
            t for t in self.release.templates()
            if t["target_path"] == ".gitignore.workflow-fragment"
        )
        self.assertIn("merged", record["derivation"])


class TestCiWorkflowTemplate(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.text = self.release.read(
            "templates/.github/workflows/workflow-conformance.yml"
        ).decode()

    def test_every_named_suite_exists_in_the_payload(self):
        installed = {a.target_path for a in self.release.payload_artifacts("full")}
        for suite in migrate.CI_SUITES:
            self.assertIn(f"scripts/{suite}", installed, suite)

    def test_it_runs_exactly_the_frozen_ci_suites(self):
        """The upstream `ci.yml` interleaves these steps with RepFlow's Gradle
        jobs. Lifting them out is a transformation, so it is checked against the
        frozen file rather than trusted."""
        if not upstream_available():
            self.skipTest("frozen upstream repository not available")
        upstream_ci = frozen_bytes(".github/workflows/ci.yml").decode()
        frozen_suites = set(re.findall(r"run: python3 (\S+\.py)", upstream_ci))
        self.assertEqual(set(migrate.CI_SUITES), frozen_suites)

    def test_it_excludes_the_history_coupled_demo_suites(self):
        for suite in ("workflow_state_demo_test.py", "workflow_fingerprint_demo_test.py"):
            self.assertNotIn(f"run: python3 {suite}", self.text, suite)

    def test_rendering_is_stable(self):
        self.assertEqual(migrate.render_ci_workflow().decode(), self.text)
        record = next(
            t for t in self.release.templates()
            if t["target_path"] == ".github/workflows/workflow-conformance.yml"
        )
        self.assertEqual(sha256(self.text.encode()), record["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
