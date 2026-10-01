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
import json
import re
import unittest

import support
from support import CI_SUITES, REPO_ROOT, expected_portability_exceptions

from workflow_manager.release import STATE_TEMPLATES, sha256

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
        self.release = support.release("2.3.1")
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


class TestMigrationEvidenceCountsMatchCiSuites(unittest.TestCase):
    """IMPL2-R2 missing-test 2: `docs/MIGRATION.md`'s `2.4.0` evidence-table
    test counts must never drift from `tests/support.py`'s own
    `CI_SUITES["2.4.0"]` -- the machine-read total `tests/run_all.py`
    itself asserts. `CI_SUITES` cannot drift silently (the conformance/
    bootstrap suites assert against it directly); the prose evidence table
    that quotes it can, and did, for one whole commit -- this pins the two
    together so a future test addition that forgets to update the table is
    a failing test, not a silent contradiction between two tracked files."""

    _FIXTURE_ROW_RE = re.compile(
        r"Frozen suite against the conformance fixture \| 7/7 suites, (\d+) tests"
    )
    _BOOTSTRAPPED_ROW_RE = re.compile(
        r"Frozen suite in a bootstrapped repository \| (\d+) of (\d+),"
    )
    _ADDITIONAL_WORKFLOW_STATE_TEST_RE = re.compile(
        r"plus (\d+) additional `workflow_state_test\.py` cases"
    )

    def _migration_text(self) -> str:
        return (REPO_ROOT / "docs" / "MIGRATION.md").read_text()

    def test_2_4_0_fixture_total_matches_ci_suites(self):
        match = self._FIXTURE_ROW_RE.search(self._migration_text())
        self.assertIsNotNone(match, "2.4.0 conformance-fixture evidence row not found")
        recorded_total = int(match.group(1))
        actual_total = sum(CI_SUITES["2.4.0"].values())
        self.assertEqual(recorded_total, actual_total)

    def test_2_4_0_bootstrapped_row_matches_ci_suites_minus_documented_exceptions(self):
        match = self._BOOTSTRAPPED_ROW_RE.search(self._migration_text())
        self.assertIsNotNone(match, "2.4.0 bootstrapped-repository evidence row not found")
        recorded_pass, recorded_total = int(match.group(1)), int(match.group(2))
        actual_total = sum(CI_SUITES["2.4.0"].values())
        exception_count = sum(
            len(tests) for tests in expected_portability_exceptions("2.4.0").values()
        )
        self.assertEqual(recorded_total, actual_total)
        self.assertEqual(recorded_pass, actual_total - exception_count)

    def test_2_4_0_additional_workflow_state_test_count_matches_ci_suites(self):
        """IMPL3-O3: the fixture-row evidence text also claims "plus N
        additional `workflow_state_test.py` cases" on top of `2.3.1`'s own
        count -- correct at every round so far but, unlike the two counts
        above, previously unpinned to `CI_SUITES` itself."""
        match = self._ADDITIONAL_WORKFLOW_STATE_TEST_RE.search(self._migration_text())
        self.assertIsNotNone(
            match, "2.4.0 'additional workflow_state_test.py cases' evidence text not found"
        )
        recorded_additional = int(match.group(1))
        actual_additional = (
            CI_SUITES["2.4.0"]["workflow_state_test.py"]
            - CI_SUITES["2.3.1"]["workflow_state_test.py"]
        )
        self.assertEqual(recorded_additional, actual_additional)


class TestMigrationEvidenceManifestFieldsMatchShippedManifest(unittest.TestCase):
    """IMPL11-B1 missing test: `docs/MIGRATION.md`'s `2.4.0` evidence table
    quotes `distribution/workflow/2.4.0/manifest.json` verbatim in three
    places -- the Provenance row's full `provenance` JSON, the Manifest
    row's artifact/template counts, and the Overlay row's replaced/added
    counts. `TestMigrationEvidenceCountsMatchCiSuites` above pins the
    *test*-count rows to `tests/support.py`; nothing pinned these
    manifest-quoting rows, and the Provenance row's `overlay_commit` drifted
    for a full round undetected (round 10's shipped manifest carried
    `64c62ec0...`; the table still named round 9's `350a039d...`, caught
    only by an external reviewer's sweep, `IMPL11-B1`). This pins all three
    rows to the manifest they claim to quote, so the next `overlay_commit`
    move -- or any manifest count drift -- fails a test instead of needing
    one."""

    _PROVENANCE_ROW_RE = re.compile(
        r"Provenance \| `distribution/workflow/2\.4\.0/manifest\.json`'s "
        r"`provenance`: `(\{.*?\})`"
    )
    _MANIFEST_ROW_RE = re.compile(
        r"2\.4\.0[\s\S]*?Manifest \| (\d+) artifacts \(\d+ `distribution`, \d+ `conformance`, "
        r"\d+ `host-evidence`\), (\d+) templates"
    )
    _OVERLAY_ROW_RE = re.compile(
        r"Overlay \| `migration/overlays/2\.4\.0/` . (\d+) payload files "
        r"replaced, (\d+) added"
    )

    def _migration_text(self) -> str:
        return (REPO_ROOT / "docs" / "MIGRATION.md").read_text()

    def _manifest(self) -> dict:
        return json.loads(support.release("2.4.0").read("manifest.json"))

    def test_provenance_row_matches_shipped_manifest(self):
        match = self._PROVENANCE_ROW_RE.search(self._migration_text())
        self.assertIsNotNone(match, "2.4.0 Provenance row not found")
        recorded = json.loads(match.group(1))
        self.assertEqual(recorded, self._manifest()["provenance"])

    def test_manifest_row_counts_match_shipped_manifest(self):
        match = self._MANIFEST_ROW_RE.search(self._migration_text())
        self.assertIsNotNone(match, "2.4.0 Manifest row not found")
        recorded_artifacts, recorded_templates = int(match.group(1)), int(match.group(2))
        counts = self._manifest()["counts"]
        self.assertEqual(recorded_artifacts, counts["artifacts"])
        self.assertEqual(recorded_templates, counts["templates"])

    def test_overlay_row_counts_match_shipped_manifest(self):
        match = self._OVERLAY_ROW_RE.search(self._migration_text())
        self.assertIsNotNone(match, "2.4.0 Overlay row not found")
        recorded_replaced, recorded_added = int(match.group(1)), int(match.group(2))
        counts = self._manifest()["counts"]
        self.assertEqual(recorded_replaced, counts["overlay_replaced"])
        self.assertEqual(recorded_added, counts["overlay_added"])


class TestAuthoredReleaseMigrationRecordMatchesShippedEvidence(unittest.TestCase):
    """workflow-review-artifact-and-concurrency-hardening round-4 `I1`: the
    two classes above pin only the `2.4.0` record (their regexes hard-code
    `2\\.4\\.0`), so `docs/MIGRATION.md`'s `2.6.0` record drifted across
    three remediation rounds undetected -- `overlay_commit`, the fixture
    total, three per-suite deltas and the bootstrapped row -- the same
    `IMPL11-B1` shape one release later. This is the table-driven version:
    one entry per authored release whose record uses the `2.6.0` table
    shape, each checked -- scoped to its own `## Workflow v<version>`
    section -- against its shipped `manifest.json`, `CI_SUITES[<version>]`
    (and its base release's) and `expected_portability_exceptions`. Every
    rebuild moves `overlay_commit`, so the next round that forgets the
    record fails here rather than needing a reviewer."""

    #: Authored releases whose `docs/MIGRATION.md` record uses this table
    #: shape. `2.4.0`'s older prose shape is pinned by the two classes above.
    RELEASES = ("2.6.0",)

    def _section(self, version: str) -> str:
        text = (REPO_ROOT / "docs" / "MIGRATION.md").read_text()
        match = re.search(
            rf"^## Workflow v{re.escape(version)} — .*?(?=^## |\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"{version} section not found in docs/MIGRATION.md")
        return match.group(0)

    def _row(self, version: str, pattern: str) -> re.Match:
        match = re.search(pattern, self._section(version))
        self.assertIsNotNone(match, f"{version} row not found: {pattern}")
        return match

    def _manifest(self, version: str) -> dict:
        return json.loads(support.release(version).read("manifest.json"))

    def test_base_release_row_matches_shipped_manifest(self):
        for version in self.RELEASES:
            with self.subTest(version=version):
                match = self._row(version, r"\| Base release \| `([^`]+)`")
                self.assertEqual(
                    match.group(1), self._manifest(version)["provenance"]["base_release"]
                )

    def test_provenance_row_matches_shipped_manifest(self):
        for version in self.RELEASES:
            with self.subTest(version=version):
                match = self._row(
                    version,
                    rf"\| Provenance \| `distribution/workflow/{re.escape(version)}/"
                    r"manifest\.json`'s `provenance`: `(\{.*?\})`",
                )
                self.assertEqual(
                    json.loads(match.group(1)), self._manifest(version)["provenance"]
                )

    def test_overlay_row_counts_match_shipped_manifest(self):
        for version in self.RELEASES:
            with self.subTest(version=version):
                match = self._row(
                    version,
                    rf"\| Overlay \| `migration/overlays/{re.escape(version)}/` . "
                    r"(\d+) payload files replaced, (\d+) added",
                )
                counts = self._manifest(version)["counts"]
                self.assertEqual(int(match.group(1)), counts["overlay_replaced"])
                self.assertEqual(int(match.group(2)), counts["overlay_added"])

    def test_manifest_row_counts_match_shipped_manifest(self):
        for version in self.RELEASES:
            with self.subTest(version=version):
                match = self._row(
                    version,
                    r"\| Manifest \| (\d+) artifacts \((\d+) `distribution`, "
                    r"(\d+) `conformance`, (\d+) `host-evidence`\), (\d+) templates",
                )
                counts = self._manifest(version)["counts"]
                self.assertEqual(
                    [int(g) for g in match.groups()],
                    [
                        counts["artifacts"],
                        counts["by_category"]["distribution"],
                        counts["by_category"]["conformance"],
                        counts["by_category"]["host-evidence"],
                        counts["templates"],
                    ],
                )

    def test_fixture_row_matches_ci_suites(self):
        """Suite count, total, the "plus N new cases" delta over the base
        release, and every quoted per-suite `a→b` transition -- which must
        also name exactly the suites whose counts moved."""
        for version in self.RELEASES:
            with self.subTest(version=version):
                base = self._manifest(version)["provenance"]["base_release"]
                match = self._row(
                    version,
                    r"\| Frozen suite against the conformance fixture \| "
                    r"(\d+)/(\d+) suites, (\d+) tests — the same suite set as "
                    rf"`{re.escape(base)}`, plus (\d+) new cases \(([^)]*)\)",
                )
                suites, base_suites = CI_SUITES[version], CI_SUITES[base]
                self.assertEqual(int(match.group(1)), len(suites))
                self.assertEqual(int(match.group(2)), len(suites))
                self.assertEqual(int(match.group(3)), sum(suites.values()))
                self.assertEqual(
                    int(match.group(4)), sum(suites.values()) - sum(base_suites.values())
                )
                recorded = {
                    name: (int(old), int(new))
                    for name, old, new in re.findall(
                        r"`([\w.]+\.py)` (\d+)→(\d+)", match.group(5)
                    )
                }
                actual = {
                    name: (base_suites[name], count)
                    for name, count in suites.items()
                    if base_suites.get(name) != count
                }
                self.assertEqual(recorded, actual)

    def test_bootstrapped_row_matches_ci_suites_minus_documented_exceptions(self):
        for version in self.RELEASES:
            with self.subTest(version=version):
                match = self._row(
                    version,
                    r"\| Frozen suite in a bootstrapped repository \| (\d+) of (\d+)",
                )
                total = sum(CI_SUITES[version].values())
                exceptions = sum(
                    len(tests) for tests in expected_portability_exceptions(version).values()
                )
                self.assertEqual(int(match.group(2)), total)
                self.assertEqual(int(match.group(1)), total - exceptions)


class TestReadmeStatusTableMatchesCiSuites(unittest.TestCase):
    """IMPL12-B1 missing test: `README.md`'s Status table -- the
    repository's front page -- quotes the same derived `CI_SUITES` totals
    `docs/MIGRATION.md`'s evidence table does
    (`TestMigrationEvidenceCountsMatchCiSuites` above), but nothing pinned
    it to them. It drifted for eleven external-implementation-review rounds
    undetected (`IMPL12-B1`): `docs/MIGRATION.md`'s own `2.4.0` row moved in
    lockstep with every `CI_SUITES` change because a reviewer, and then a
    test, pinned it; `README.md`'s twin row was never swept. This closes
    the identical defect shape one document earlier, and extends it to the
    `2.3.1` row for the same reason."""

    _README_2_4_0_ROW_RE = re.compile(
        r"`2\.4\.0` \|.*?7/7 suites, (\d+) tests — same suite set as "
        r"`2\.3\.1`, plus (\d+) new cases \| (\d+) of (\d+)"
    )
    _README_2_3_1_ROW_RE = re.compile(
        r"`2\.3\.1` \|.*?7/7 suites, (\d+) tests — matching the upstream "
        r"baseline \| (\d+) of (\d+)"
    )
    _README_2_5_0_ROW_RE = re.compile(
        r"`2\.5\.0` \|.*?7/7 suites, (\d+) tests — same suite set as "
        r"`2\.4\.0`, plus (\d+) new cases \| (\d+) of (\d+)"
    )
    _README_2_5_1_ROW_RE = re.compile(
        r"`2\.5\.1` \|.*?7/7 suites, (\d+) tests — same suite set as "
        r"`2\.5\.0`, plus (\d+) new cases \| (\d+) of (\d+)"
    )
    _README_2_6_0_ROW_RE = re.compile(
        r"`2\.6\.0` \|.*?7/7 suites, (\d+) tests — same suite set as "
        r"`2\.5\.1`, plus (\d+) new cases \| (\d+) of (\d+)"
    )

    def _readme_text(self) -> str:
        return (REPO_ROOT / "README.md").read_text()

    def test_2_4_0_row_matches_ci_suites(self):
        match = self._README_2_4_0_ROW_RE.search(self._readme_text())
        self.assertIsNotNone(match, "README.md 2.4.0 Status row not found")
        recorded_total, recorded_new, recorded_pass, recorded_of = (
            int(match.group(1)), int(match.group(2)),
            int(match.group(3)), int(match.group(4)),
        )
        actual_total = sum(CI_SUITES["2.4.0"].values())
        actual_new = (
            CI_SUITES["2.4.0"]["workflow_state_test.py"]
            + CI_SUITES["2.4.0"].get("workflow_integration_test.py", 0)
            - CI_SUITES["2.3.1"]["workflow_state_test.py"]
            - CI_SUITES["2.3.1"].get("workflow_integration_test.py", 0)
        )
        exception_count = sum(
            len(tests) for tests in expected_portability_exceptions("2.4.0").values()
        )
        self.assertEqual(recorded_total, actual_total)
        self.assertEqual(recorded_new, actual_new)
        self.assertEqual(recorded_of, actual_total)
        self.assertEqual(recorded_pass, actual_total - exception_count)

    def test_2_3_1_row_matches_ci_suites(self):
        match = self._README_2_3_1_ROW_RE.search(self._readme_text())
        self.assertIsNotNone(match, "README.md 2.3.1 Status row not found")
        recorded_total, recorded_pass, recorded_of = (
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
        )
        actual_total = sum(CI_SUITES["2.3.1"].values())
        exception_count = sum(
            len(tests) for tests in expected_portability_exceptions("2.3.1").values()
        )
        self.assertEqual(recorded_total, actual_total)
        self.assertEqual(recorded_of, actual_total)
        self.assertEqual(recorded_pass, actual_total - exception_count)

    def test_2_5_0_row_matches_ci_suites(self):
        # round-3 I3's twin: the identical drift shape this class exists to
        # stop, one release later. `2.5.0`'s own base is `2.4.0` (not
        # `2.3.1`), so "new cases" is measured against `2.4.0`'s own totals.
        match = self._README_2_5_0_ROW_RE.search(self._readme_text())
        self.assertIsNotNone(match, "README.md 2.5.0 Status row not found")
        recorded_total, recorded_new, recorded_pass, recorded_of = (
            int(match.group(1)), int(match.group(2)),
            int(match.group(3)), int(match.group(4)),
        )
        actual_total = sum(CI_SUITES["2.5.0"].values())
        actual_new = (
            CI_SUITES["2.5.0"]["workflow_state_test.py"]
            + CI_SUITES["2.5.0"].get("workflow_integration_test.py", 0)
            - CI_SUITES["2.4.0"]["workflow_state_test.py"]
            - CI_SUITES["2.4.0"].get("workflow_integration_test.py", 0)
        )
        exception_count = sum(
            len(tests) for tests in expected_portability_exceptions("2.5.0").values()
        )
        self.assertEqual(recorded_total, actual_total)
        self.assertEqual(recorded_new, actual_new)
        self.assertEqual(recorded_of, actual_total)
        self.assertEqual(recorded_pass, actual_total - exception_count)

    def test_2_5_1_row_matches_ci_suites(self):
        # `2.5.1`'s own base is `2.5.0` (D-Checkpoint-Id-Anchor-Grammar-
        # Widening's narrow overlay), so "new cases" is measured against
        # `2.5.0`'s own totals -- the identical drift-prevention shape this
        # class exists to enforce, one release later.
        match = self._README_2_5_1_ROW_RE.search(self._readme_text())
        self.assertIsNotNone(match, "README.md 2.5.1 Status row not found")
        recorded_total, recorded_new, recorded_pass, recorded_of = (
            int(match.group(1)), int(match.group(2)),
            int(match.group(3)), int(match.group(4)),
        )
        actual_total = sum(CI_SUITES["2.5.1"].values())
        actual_new = (
            CI_SUITES["2.5.1"]["workflow_state_test.py"]
            + CI_SUITES["2.5.1"].get("workflow_integration_test.py", 0)
            - CI_SUITES["2.5.0"]["workflow_state_test.py"]
            - CI_SUITES["2.5.0"].get("workflow_integration_test.py", 0)
        )
        exception_count = sum(
            len(tests) for tests in expected_portability_exceptions("2.5.1").values()
        )
        self.assertEqual(recorded_total, actual_total)
        self.assertEqual(recorded_new, actual_new)
        self.assertEqual(recorded_of, actual_total)
        self.assertEqual(recorded_pass, actual_total - exception_count)

    def test_2_6_0_row_matches_ci_suites(self):
        # `2.6.0`'s own base is `2.5.1`, and unlike `2.5.1` its overlay
        # replaces five of the seven frozen suites, so "new cases" is the
        # whole-release delta against `2.5.1`'s own totals rather than a
        # two-suite sum -- the same drift-prevention shape, one release
        # later.
        match = self._README_2_6_0_ROW_RE.search(self._readme_text())
        self.assertIsNotNone(match, "README.md 2.6.0 Status row not found")
        recorded_total, recorded_new, recorded_pass, recorded_of = (
            int(match.group(1)), int(match.group(2)),
            int(match.group(3)), int(match.group(4)),
        )
        actual_total = sum(CI_SUITES["2.6.0"].values())
        actual_new = actual_total - sum(CI_SUITES["2.5.1"].values())
        exception_count = sum(
            len(tests) for tests in expected_portability_exceptions("2.6.0").values()
        )
        self.assertEqual(recorded_total, actual_total)
        self.assertEqual(recorded_new, actual_new)
        self.assertEqual(recorded_of, actual_total)
        self.assertEqual(recorded_pass, actual_total - exception_count)


_STDLIB = frozenset(
    getattr(__import__("sys"), "stdlib_module_names", ())
) or frozenset({
    "argparse", "ast", "base64", "contextlib", "copy", "dataclasses", "datetime",
    "errno", "fcntl", "hashlib", "html", "importlib", "inspect", "itertools",
    "json", "multiprocessing", "os", "pathlib", "re", "secrets", "shutil",
    "stat", "subprocess", "sys", "tarfile", "tempfile", "threading", "time",
    "types", "typing", "unittest", "uuid", "xml",
})



#: Test modules M2's CP6 deleted, with `distribution/` and `migration/`
#: (plan 10, CP6). No kept test names one (`TestNoTestNamesARetiredModule`).
RETIRED_MODULES = frozenset({
    "test_payload_bytes.py", "test_templates.py", "test_migration_inventory.py",
    "test_no_live_state_imported.py", "test_amendment_update_path.py",
    "test_implementation_review_two_stage_disposable_repo.py", "test_stopgap_profile.py",
    "test_authored_release_tools.py", "test_package_round_trip.py",
})
#: The deprecated runner alias's identifiers, which CP6 removed with it.
RETIRED_FAST_IDENTIFIERS = ("FAST_ALIAS_SELECTION", "FAST_NOTE", "args.fast", "--fast")

#: `(module, top-level class or assignment, lifetime)`: the only places a
#: scanned module may name the layout. A stale entry fails the test.
LAYOUT_EXEMPTIONS = (
    # The deprecated `--manager-root` alias reads a checkout's old layout; its
    # tests build that layout themselves.
    ("test_bootstrap.py", "TestManagerRootAlias", "while the alias exists"),
    # Regexes over `docs/MIGRATION.md`'s historical text, not lookups.
    ("test_internal_references.py", "TestMigrationEvidenceManifestFieldsMatchShippedManifest",
     "permanent"),
    ("test_internal_references.py", "TestAuthoredReleaseMigrationRecordMatchesShippedEvidence",
     "permanent"),
)

LAYOUT_API = ("find_release", "available_versions", "release_root")
#: Built, not written, so this module's own text never names the layout.
LAYOUT_TEXT = "/".join(["distribution"] + ["workflow"])
LAYOUT_COMPONENTS = re.compile(r"""["']distribution["']\s*[/,]\s*["']workflow["']""")


def _scanned_test_files() -> list[Path]:
    """Every `tests/**/*.py`, the infrastructure included."""
    return [path for path in sorted((REPO_ROOT / "tests").rglob("*.py"))
            if "__pycache__" not in path.parts]


def _layout_scopes(tree: ast.Module) -> dict[str, tuple[int, int]]:
    """`{scope name: (first line, last line)}` for every top-level class,
    top-level assignment, and `from <module> import ...` (as
    `import:<module>`)."""
    scopes = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            scopes[node.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    scopes[target.id] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.ImportFrom) and node.module:
            scopes[f"import:{node.module}"] = (node.lineno, node.end_lineno)
    return scopes


def layout_references(text: str) -> list[tuple[int, str]]:
    """`(line, what)` for every way `text` resolves a release through the
    checkout layout: importing the discovery API, or naming the release
    directory, as a path string or as path components, comments included."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if LAYOUT_TEXT in line or LAYOUT_COMPONENTS.search(line):
            found.append((number, "names the release-directory layout"))
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in LAYOUT_API:
                    found.append((node.lineno, f"imports {alias.name}"))
    return sorted(found)


class TestNoTestResolvesAReleaseThroughTheLayout(unittest.TestCase):
    """M2's CP5 (plan 10): every test obtains a release through the pins and
    the cache (`support.release`), never through the checkout's release
    directories.
    Scans every `tests/**/*.py`."""

    def scanned(self):
        return _scanned_test_files()

    def test_no_scanned_module_names_the_layout_outside_its_exemptions(self):
        exempt: dict[str, list[str]] = {}
        for module, scope, _lifetime in LAYOUT_EXEMPTIONS:
            exempt.setdefault(module, []).append(scope)
        violations = []
        for path in self.scanned():
            text = path.read_text(encoding="utf-8")
            scopes = _layout_scopes(ast.parse(text))
            spans = [scopes[s] for s in exempt.get(path.name, ()) if s in scopes]
            for line, what in layout_references(text):
                if not any(first <= line <= last for first, last in spans):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{line}: {what}")
        self.assertEqual(violations, [])

    def test_every_exemption_names_something_that_exists_and_still_needs_it(self):
        for module, scope, lifetime in LAYOUT_EXEMPTIONS:
            with self.subTest(module=module, scope=scope):
                self.assertIn(lifetime, ("while the alias exists", "permanent"))
                text = (REPO_ROOT / "tests" / module).read_text(encoding="utf-8")
                scopes = _layout_scopes(ast.parse(text))
                self.assertIn(scope, scopes, "stale exemption: nothing by that name")
                first, last = scopes[scope]
                self.assertTrue(any(first <= line <= last
                                    for line, _ in layout_references(text)),
                                "stale exemption: its scope no longer names the layout")

    def test_the_scan_catches_each_form(self):
        cases = {
            "from workflow_manager.release import find_release\n": "imports find_release",
            "from workflow_manager.release import (\n    Release,\n    release_root,\n)\n":
                "imports release_root",
            f"# see {LAYOUT_TEXT}/2.6.0\n": "names the release-directory layout",
            f"p = ROOT / {'distribution'!r} / {'workflow'!r}\n":
                "names the release-directory layout",
            f"p = os.path.join(ROOT, {'distribution'!r}, {'workflow'!r})\n":
                "names the release-directory layout",
        }
        for text, what in cases.items():
            with self.subTest(text=text):
                self.assertIn(what, [w for _, w in layout_references(text)])
        self.assertEqual(layout_references("support.release(NEWEST_RELEASE)\n"), [])

    def test_the_scan_covers_the_infrastructure(self):
        names = {path.relative_to(REPO_ROOT / "tests").as_posix() for path in self.scanned()}
        for required in ("support.py", "frozen_runs.py", "parallel/inventory.py",
                         "parallel/matrix.py", "test_parallel_runner.py"):
            self.assertIn(required, names)


#: `(module, scope)`: the only places a kept test may name a retired module or
#: an identifier of the retired runner alias. A scope is a top-level name, or
#: `Class.method` for a method. A stale entry fails the test.
RETIRED_NAME_EXEMPTIONS = (
    # The lists themselves.
    ("test_internal_references.py", "RETIRED_MODULES"),
    ("test_internal_references.py", "RETIRED_FAST_IDENTIFIERS"),
    # The runner test that the flag is now an unrecognized argument.
    ("test_parallel_runner.py", "TestDirectEntryPoints.test_the_retired_alias_is_refused"),
)


def _retired_name_scopes(tree: ast.Module) -> dict[str, tuple[int, int]]:
    """`_layout_scopes`, plus `Class.method` for every top-level class's methods."""
    scopes = _layout_scopes(tree)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scopes[f"{node.name}.{item.name}"] = (item.lineno, item.end_lineno)
    return scopes


def retired_name_references(text: str) -> list[tuple[int, str]]:
    """`(line, name)` for every retired module or retired alias identifier `text`
    names, in code or comments."""
    names = sorted(RETIRED_MODULES) + list(RETIRED_FAST_IDENTIFIERS)
    return [(number, name) for number, line in enumerate(text.splitlines(), 1)
            for name in names if name in line]


class TestNoTestNamesARetiredModule(unittest.TestCase):
    """M2's CP6 (plan 10): no kept `tests/**/*.py` names, in code or comments,
    a module CP6 deleted or an identifier of the runner alias it removed, so a
    missed reference fails here by name."""

    def test_no_kept_test_names_a_retired_module_or_identifier(self):
        exempt: dict[str, list[str]] = {}
        for module, scope in RETIRED_NAME_EXEMPTIONS:
            exempt.setdefault(module, []).append(scope)
        violations = []
        for path in _scanned_test_files():
            text = path.read_text(encoding="utf-8")
            scopes = _retired_name_scopes(ast.parse(text))
            spans = [scopes[s] for s in exempt.get(path.name, ()) if s in scopes]
            for line, name in retired_name_references(text):
                if not any(first <= line <= last for first, last in spans):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{line}: {name}")
        self.assertEqual(violations, [])

    def test_the_retired_modules_are_gone(self):
        for name in sorted(RETIRED_MODULES):
            with self.subTest(module=name):
                self.assertEqual(list((REPO_ROOT / "tests").rglob(name)), [])

    def test_every_exemption_names_something_that_still_needs_it(self):
        for module, scope in RETIRED_NAME_EXEMPTIONS:
            with self.subTest(module=module, scope=scope):
                text = (REPO_ROOT / "tests" / module).read_text(encoding="utf-8")
                scopes = _retired_name_scopes(ast.parse(text))
                self.assertIn(scope, scopes, "stale exemption: nothing by that name")
                first, last = scopes[scope]
                self.assertTrue(any(first <= line <= last
                                    for line, _ in retired_name_references(text)),
                                "stale exemption: its scope no longer names a retired name")

    def test_the_scan_catches_a_module_and_each_identifier(self):
        module = sorted(RETIRED_MODULES)[0]
        self.assertEqual(retired_name_references(f"# see {module}\n"), [(1, module)])
        for name in RETIRED_FAST_IDENTIFIERS:
            with self.subTest(name=name):
                self.assertIn(name, [n for _, n in retired_name_references(f"x = {name!r}\n")])
        self.assertEqual(retired_name_references("run_all.py --select test_bootstrap.py\n"), [])


class TestNoLiteralCliEnvironment(unittest.TestCase):
    """Plan 7.1: a test that starts a `workflow_manager` subprocess takes its
    environment from `support.cli_env`, which always names the primed release
    cache -- never a literal `env={...}`, which would drop it."""

    def test_no_workflow_manager_subprocess_gets_a_literal_env(self):
        offenders = []
        for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(text)):
                if not isinstance(node, ast.Call):
                    continue
                env = next((k.value for k in node.keywords if k.arg == "env"), None)
                if isinstance(env, ast.Dict) and \
                        "workflow_manager" in (ast.get_source_segment(text, node) or ""):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
