#!/usr/bin/env python3
"""Internal references resolve from the canonical distribution alone.

The frozen suite passing is strong behavioural evidence, but it is indirect:
it proves the paths *the tests exercise* resolve. These tests read the
distribution's own text and check that every repository path it names is
either shipped, generated at bootstrap, or created by the Workflow at run
time -- so a reference to something that only ever existed in RepFlow is
caught by name rather than by a test that happens not to touch it.
"""

from __future__ import annotations

import ast
import re
import unittest

from support import REPO_ROOT

from workflow_manager.release import STATE_TEMPLATES, find_release, sha256

#: Paths the Workflow creates at run time. Absent from a fresh install by
#: design -- `.ai-review/` is git-ignored, and per-work-item declarations are
#: named after whatever work item a repository creates.
RUNTIME_CREATED = (
    ".ai-review/",
    "docs/ai-workflow/registry/",
    "docs/ai-workflow/requirements/",
    "docs/ai-workflow/checkpoint-claims/",
    "docs/ai-workflow/identity-gap-authorizations/",
    "docs/ai-workflow/archive/",
    "docs/ai-workflow/dry-run/",
)

#: Paths frozen v2.3.1 names that belong to the *host* repository, not the
#: Workflow. A managed repository supplies its own; the distribution neither
#: ships nor requires them. Each is a `PLAN_STAGE_EXCLUDED_PATHS` entry or a
#: product path in `IMPLEMENTATION_STAGE_DELIVERABLE_PREFIXES` upstream.
HOST_SUPPLIED = (
    "docs/ROADMAP.md",
    "docs/TECHNICAL_DECISIONS.md",
    "docs/PROJECT_BRIEF.md",
    "docs/DOMAIN_GLOSSARY.md",
    "docs/UX_FLOWS.md",
    "docs/milestones/",
    "docs/adr/",
    "docs/agent-context/",
    "docs/improvements/",
    "AGENTS.md",
    "README.md",
    "app/",
    "gradle/",
    "gradlew",
    "config/",
    ".github/",
    ".editorconfig",
    "build.gradle.kts",
    "settings.gradle.kts",
    "gradle.properties",
    "local.properties",
)

#: A backticked reference to a real file, not an identifier or a prose
#: fragment: it must sit under a directory the Workflow owns and end in a
#: file extension the Workflow ships.
PATH_RE = re.compile(
    r"`((?:docs/ai-workflow|scripts|\.claude/commands)/[A-Za-z0-9_./\-]+"
    r"\.(?:md|json|py|sh|svg))`"
)

#: The operator-facing contract documents. An agent follows these literally, so
#: a path they name has to exist.
CONTRACT_DOCS = (
    "docs/ai-workflow/MILESTONE_WORKFLOW.md",
    "docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md",
    "docs/ai-workflow/REVIEW_PROTOCOL.md",
    "docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md",
)

#: Design, audit and history documents. These argue about hypothetical
#: repositories -- `scripts/rogue.bash`, `docs/adr/0004-new.md`, a scratch
#: file that only ever existed inside one dry run -- so resolving their
#: example paths would be checking prose, not a contract.
NARRATIVE_DOCS_EXCLUDED_FROM_RESOLUTION = tuple(
    sorted({
        "docs/ai-workflow/WORKFLOW_V2_PLAN.md",
        "docs/ai-workflow/WORKFLOW_V2_AUDIT.md",
        "docs/ai-workflow/WORKFLOW_V2_3_PLAN.md",
        "docs/ai-workflow/WORKFLOW_V2_3_FOLLOWUPS.md",
        "docs/ai-workflow/WORKFLOW_V2_3_FOLLOWUPS_PLAN.md",
    })
)


class ReferenceCase(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self.shipped = {a.target_path for a in self.release.payload_artifacts("full")}
        self.generated = {t["target_path"] for t in self.release.templates()}
        self.generated |= set(STATE_TEMPLATES)

    def resolves(self, ref: str) -> bool:
        if ref in self.shipped or ref in self.generated:
            return True
        if any(ref == p or ref.startswith(p) for p in RUNTIME_CREATED + HOST_SUPPLIED):
            return True
        # A directory reference resolves if anything ships beneath it.
        if ref.endswith("/") and any(s.startswith(ref) for s in self.shipped):
            return True
        return False


class TestCommandFilesResolve(ReferenceCase):
    def test_every_workflow_path_a_command_names_resolves(self):
        """A command file is executed step by step by an agent. Every Workflow
        file it names must be one the installer actually put there."""
        unresolved = {}
        checked = 0
        for artifact in self.release.payload_artifacts("full"):
            if not artifact.target_path.startswith(".claude/commands/"):
                continue
            text = self.release.read(artifact.location).decode()
            references = set(PATH_RE.findall(text))
            checked += len(references)
            bad = sorted({r for r in references if not self.resolves(r)})
            if bad:
                unresolved[artifact.target_path] = bad
        self.assertEqual(unresolved, {})
        self.assertGreater(checked, 20, "too few references found -- the regex stopped matching")

    def test_every_command_names_only_shipped_scripts(self):
        """A command that shells out to a script we did not ship would fail at
        the first invocation in a target repository."""
        missing = {}
        for artifact in self.release.payload_artifacts("full"):
            if not artifact.target_path.startswith(".claude/commands/"):
                continue
            text = self.release.read(artifact.location).decode()
            for script in re.findall(r"\bscripts/[A-Za-z0-9_.\-]+\.(?:py|sh)\b", text):
                if script not in self.shipped:
                    missing.setdefault(artifact.target_path, set()).add(script)
        self.assertEqual(missing, {})


class TestWorkflowDocsResolve(ReferenceCase):
    def test_every_workflow_path_the_contract_docs_name_resolves(self):
        unresolved = {}
        per_doc = {}
        for rel in CONTRACT_DOCS:
            artifact = next(a for a in self.release.payload_artifacts("full")
                            if a.target_path == rel)
            references = set(PATH_RE.findall(self.release.read(artifact.location).decode()))
            per_doc[rel] = len(references)
            bad = sorted({r for r in references if not self.resolves(r)})
            if bad:
                unresolved[rel] = bad
        self.assertEqual(unresolved, {})
        # Non-vacuousness: every contract document contributed references, so a
        # regex that stopped matching fails here rather than passing silently.
        self.assertEqual([rel for rel, n in per_doc.items() if n == 0], [])

    def test_the_narrative_docs_are_shipped_even_though_they_are_not_resolved(self):
        """Excluding them from resolution is a statement about their genre, not
        permission to drop them: the frozen suite lints all five."""
        for rel in NARRATIVE_DOCS_EXCLUDED_FROM_RESOLUTION:
            self.assertIn(rel, self.shipped, rel)

    def test_the_narrative_exclusion_covers_only_narrative_documents(self):
        """No contract document may quietly join the excluded list."""
        self.assertEqual(
            set(CONTRACT_DOCS) & set(NARRATIVE_DOCS_EXCLUDED_FROM_RESOLUTION), set(),
        )


class TestPythonModulesResolve(ReferenceCase):
    def test_the_scripts_import_only_each_other_and_the_stdlib(self):
        """No third-party dependency may have crept in: frozen v2.3.1 is
        stdlib-only, and a target repository installs no packages."""
        shipped_modules = {
            a.target_path.split("/")[-1][:-3]
            for a in self.release.payload_artifacts("full")
            if a.target_path.startswith("scripts/") and a.target_path.endswith(".py")
        }
        third_party = set()
        for artifact in self.release.payload_artifacts("full"):
            if not (artifact.target_path.startswith("scripts/")
                    and artifact.target_path.endswith(".py")):
                continue
            tree = ast.parse(self.release.read(artifact.location).decode())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in shipped_modules:
                        continue
                    if name in ("__future__",) or name in _STDLIB:
                        continue
                    third_party.add(f"{artifact.target_path}: {name}")
        self.assertEqual(sorted(third_party), [])

    def test_the_two_layout_dependent_verifiers_are_shipped_at_their_required_depth(self):
        for name in ("verify_372h_lock_primitive_predicate.py",
                     "verify_372h_raw_edge_derivation.py"):
            rel = f"docs/ai-workflow/dry-run/{name}"
            self.assertIn(rel, self.shipped)
            self.assertEqual(len(rel.split("/")) - 1, 3,
                             f"{name} resolves the repository root as parents[3]")

    def test_the_plan_document_the_verifiers_parse_is_shipped(self):
        """`verify_372h_raw_edge_derivation.py` resolves its plan as
        `parent.parent / 'WORKFLOW_V2_PLAN.md'`."""
        self.assertIn("docs/ai-workflow/WORKFLOW_V2_PLAN.md", self.shipped)


class TestCommandInventoryAndGoldenHashes(ReferenceCase):
    """The command corpus is exactly the frozen one, and the frozen suite's own
    golden hashes still describe the files we shipped."""

    def _command_names(self):
        return sorted(
            p.split("/")[-1] for p in self.shipped if p.startswith(".claude/commands/")
        )

    def test_the_command_inventory_is_the_frozen_fifteen(self):
        self.assertEqual(self._command_names(), [
            "accept-milestone.md",
            "apply-functional-review.md",
            "apply-implementation-review.md",
            "apply-plan-review.md",
            "approve-review.md",
            "bootstrap-workflow-v2.md",
            "milestone-implement.md",
            "milestone-plan.md",
            "prepare-functional-review.md",
            "prepare-review.md",
            "record-manual-plan-review.md",
            "recover-implementation-provenance.md",
            "review-functional.md",
            "review-implementation.md",
            "review-plan.md",
        ])

    def test_the_retired_command_is_absent(self):
        """`workflow_integration_test.py` asserts this file does not exist."""
        self.assertNotIn(".claude/commands/accept-scoped-remediation.md", self.shipped)

    def test_the_frozen_golden_hashes_match_the_migrated_command_files(self):
        """`_GOLDEN_COMMAND_FILE_SHA256` in the migrated integration test is a
        drift guard over the command corpus. Reading it here proves the payload
        the installer ships is the corpus those hashes were computed over --
        directly, not by running the suite."""
        source = self.release.read(
            "payload/scripts/workflow_integration_test.py"
        ).decode()
        tree = ast.parse(source)
        golden = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_GOLDEN_COMMAND_FILE_SHA256"
                for t in node.targets
            ):
                golden = ast.literal_eval(node.value)
        self.assertIsNotNone(golden, "_GOLDEN_COMMAND_FILE_SHA256 not found in the payload")
        self.assertTrue(golden, "the golden hash table is empty -- assertion would be vacuous")
        for filename, expected in golden.items():
            rel = f".claude/commands/{filename}"
            self.assertIn(rel, self.shipped, filename)
            artifact = next(a for a in self.release.payload_artifacts("full")
                            if a.target_path == rel)
            self.assertEqual(sha256(self.release.read(artifact.location)), expected, filename)


_STDLIB = frozenset(
    getattr(__import__("sys"), "stdlib_module_names", ())
) or frozenset({
    "argparse", "ast", "base64", "contextlib", "copy", "dataclasses", "datetime",
    "errno", "fcntl", "hashlib", "html", "importlib", "inspect", "itertools",
    "json", "multiprocessing", "os", "pathlib", "re", "secrets", "shutil",
    "stat", "subprocess", "sys", "tarfile", "tempfile", "threading", "time",
    "types", "typing", "unittest", "uuid", "xml",
})


if __name__ == "__main__":
    unittest.main(verbosity=1)
