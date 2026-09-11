#!/usr/bin/env python3
"""The frozen v2.3.1 suite, run against what this repository produces --
and, since `workflow-2.4.0` (D-Authored-Release-2, CP6), the same matrix run
a second time against this repository's own first *authored* release.

This is the equivalence evidence for the migration (`2.3.1`) and for the
authored release (`2.4.0`) alike. For each `WORKFLOW_VERSION`, two runs, both
against disposable repositories built only from `distribution/`:

`TestConformanceFixture*`
    The frozen suite against the conformance fixture -- payload plus the
    `host-evidence` documents the suite lints. Every suite must be green and
    every test count must equal `CI_SUITES[WORKFLOW_VERSION]`, so a silently
    skipped or vanished test fails here rather than passing quietly.

`TestBootstrappedTarget*`
    The same suite against a clean target with no upstream history at all.
    The failure set must be *exactly* `migration/portability_exceptions.json`'s
    own `by_version[WORKFLOW_VERSION]` exceptions -- not a subset, not a
    superset.

`231`/`240` name the two releases (`2.3.1`, `2.4.0`); `2.3.1`'s own run stays
exactly as it always was -- CP6 adds the `2.4.0` run beside it, never in
place of it.

Below the version-parameterized matrix, three more checks CP6 adds once,
never per-version, since they are about the authored release specifically:
`TestAuthoredReleaseOverlayDelta` (I2 -- every recorded overlay diff really
reproduces from base + diff alone), `TestAuthoredReleaseCiTemplateSuiteNames`
(the shipped CI template names exactly the suite set this matrix itself
verifies), and `TestOverlayStateWriterClosure` (the `WFO-STATE-SERIALIZATION`
closure-verifier gap: widening its scan to every present overlay's own
`.claude/commands/`/`scripts/` writer surface).

Slow (~2 minutes per release): the acceptance matrix drives real `git` and
the real `prepare-ai-review.sh` across 146 rows, twice per release.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from support import (
    CI_SUITES,
    REPO_ROOT,
    expected_portability_exceptions,
    failing_tests,
    run_suite,
)

from workflow_manager.fixture import build_conformance_repo, build_target_repo
from workflow_manager.release import find_release

RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)


def _ran(output: str) -> int:
    match = RAN_RE.search(output)
    if match is None:
        raise AssertionError(f"no unittest summary in output:\n{output[-2000:]}")
    return int(match.group(1))


class _SuiteRun:
    """One build of a disposable repository, with every frozen suite run once."""

    results: dict = {}
    root: Path | None = None
    workflow_version: str | None = None
    _tmp = None

    @classmethod
    def build(cls, builder, workflow_version: str):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.workflow_version = workflow_version
        cls.root = builder(find_release(REPO_ROOT, workflow_version), Path(cls._tmp.name) / "repo")
        cls.results = {suite: run_suite(cls.root, suite) for suite in CI_SUITES[workflow_version]}

    @classmethod
    def teardown(cls):
        if cls._tmp is not None:
            cls._tmp.cleanup()
            cls._tmp = None


class _ConformanceFixtureAssertions:
    """Shared assertions for `TestConformanceFixture*`, parameterized per
    release by `WORKFLOW_VERSION`. Deliberately a plain mixin, never itself a
    `unittest.TestCase`: subclassing `TestCase` here would let the test
    loader discover and run this shared body on its own, with no
    `WORKFLOW_VERSION` to build a fixture from."""

    WORKFLOW_VERSION: str

    @classmethod
    def setUpClass(cls):
        cls.Run.build(build_conformance_repo, workflow_version=cls.WORKFLOW_VERSION)

    @classmethod
    def tearDownClass(cls):
        cls.Run.teardown()

    def test_every_frozen_suite_passes(self):
        failed = {
            suite: proc.stdout + proc.stderr
            for suite, proc in self.Run.results.items() if proc.returncode != 0
        }
        self.assertEqual(sorted(failed), [], "\n\n".join(failed.values())[-4000:])

    def test_every_suite_runs_the_frozen_number_of_tests(self):
        counts = {
            suite: _ran(proc.stdout + proc.stderr)
            for suite, proc in self.Run.results.items()
        }
        self.assertEqual(counts, dict(CI_SUITES[self.WORKFLOW_VERSION]))

    def test_the_fixture_holds_no_upstream_build_system(self):
        for name in ("build.gradle.kts", "settings.gradle.kts", "gradlew", "app"):
            self.assertFalse((self.Run.root / name).exists(), name)

    def test_the_fixture_state_file_is_the_clean_template(self):
        state = json.loads(
            (self.Run.root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text()
        )
        self.assertEqual(state["work_items"], {})


class TestConformanceFixture231(_ConformanceFixtureAssertions, unittest.TestCase):
    """Frozen suite, frozen host context, frozen `2.3.1` payload: unchanged
    by CP6 -- everything still green."""

    WORKFLOW_VERSION = "2.3.1"

    class Run(_SuiteRun):
        pass


class TestConformanceFixture240(_ConformanceFixtureAssertions, unittest.TestCase):
    """CP6's own explicit obligation: the same frozen suite, run a second
    time against `distribution/workflow/2.4.0/`'s own authored payload, in
    addition to (never instead of) `TestConformanceFixture231` above."""

    WORKFLOW_VERSION = "2.4.0"

    class Run(_SuiteRun):
        pass


class _BootstrappedTargetAssertions:
    """Shared assertions for `TestBootstrappedTarget*` -- mirrors
    `_ConformanceFixtureAssertions`'s own mixin shape and reasoning."""

    WORKFLOW_VERSION: str

    @classmethod
    def setUpClass(cls):
        cls.Run.build(build_target_repo, workflow_version=cls.WORKFLOW_VERSION)

    @classmethod
    def tearDownClass(cls):
        cls.Run.teardown()

    def test_failures_are_exactly_the_documented_portability_exceptions(self):
        expected = expected_portability_exceptions(self.WORKFLOW_VERSION)
        actual = {}
        for suite, proc in self.Run.results.items():
            names = failing_tests(proc.stdout + proc.stderr)
            if names:
                actual[suite] = names
        self.assertEqual(actual, expected)

    def test_every_suite_still_runs_the_frozen_number_of_tests(self):
        """A target must not lose tests -- only fail the documented ones."""
        counts = {
            suite: _ran(proc.stdout + proc.stderr)
            for suite, proc in self.Run.results.items()
        }
        self.assertEqual(counts, dict(CI_SUITES[self.WORKFLOW_VERSION]))

    def test_suites_with_no_exception_pass_outright(self):
        expected = expected_portability_exceptions(self.WORKFLOW_VERSION)
        for suite, proc in self.Run.results.items():
            if suite in expected:
                continue
            self.assertEqual(proc.returncode, 0,
                             f"{suite} failed:\n{(proc.stdout + proc.stderr)[-3000:]}")

    def test_the_target_carries_no_upstream_host_document(self):
        text = (self.Run.root / "docs/ACTIVE_MILESTONE.md").read_text()
        self.assertNotIn("RepFlow", text)
        self.assertNotIn("Status note (2026-08-04)", text)

    def test_every_documented_exception_actually_fires(self):
        """The exception list is not allowed to accumulate stale entries: each
        one must be a test that really does fail in a clean target."""
        expected = expected_portability_exceptions(self.WORKFLOW_VERSION)
        for suite, tests in expected.items():
            proc = self.Run.results[suite]
            observed = failing_tests(proc.stdout + proc.stderr)
            self.assertEqual(tests & observed, tests, f"{suite}: stale exception entry")


class TestBootstrappedTarget231(_BootstrappedTargetAssertions, unittest.TestCase):
    """Frozen suite, clean target, frozen `2.3.1` payload: unchanged by
    CP6 -- green except the one documented exception."""

    WORKFLOW_VERSION = "2.3.1"

    class Run(_SuiteRun):
        pass


class TestBootstrappedTarget240(_BootstrappedTargetAssertions, unittest.TestCase):
    """CP6's own explicit obligation: the same clean-target run, a second
    time, against `2.4.0`'s own authored payload."""

    WORKFLOW_VERSION = "2.4.0"

    class Run(_SuiteRun):
        pass


def _overlay_payload_roots() -> list[tuple[str, Path]]:
    """`(version, payload_root)` for every authored overlay present under
    `migration/overlays/` -- today just `2.4.0`, but never hardcoded to it:
    a future authored release adds its own overlay directory and is picked
    up here without touching this file (mirrors D-Authored-Release-4's own
    "for every authored release present" phrasing, CP6's registry row)."""
    overlays_dir = REPO_ROOT / "migration" / "overlays"
    roots = []
    if overlays_dir.is_dir():
        for entry in sorted(overlays_dir.iterdir()):
            payload = entry / "payload"
            if payload.is_dir():
                roots.append((entry.name, payload))
    return roots


class TestAuthoredReleaseOverlayDelta(unittest.TestCase):
    """D-Authored-Release-2's I2, and `tools/build_release.py`'s own
    `unified_diff_sha256` docstring ("CP6's own conformance extension
    asserts exactly that reproduction"): every `overlay_delta` recorded in
    an authored release's manifest must be reproducible from
    `base payload bytes + this recorded diff` alone -- never trusted as an
    opaque hash on the manifest's own say-so."""

    @classmethod
    def setUpClass(cls):
        tools_dir = REPO_ROOT / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import build_release
        cls.build_release = build_release

    def test_every_overlay_delta_reproduces_from_base_and_overlay_bytes(self):
        overlay_manifest_path = REPO_ROOT / "distribution/workflow/2.4.0/manifest.json"
        overlay_manifest = json.loads(overlay_manifest_path.read_text())
        base_version = overlay_manifest["provenance"]["base_release"]
        base_manifest = json.loads(
            (REPO_ROOT / "distribution/workflow" / base_version / "manifest.json").read_text()
        )
        base_by_path = {a["target_path"]: a for a in base_manifest["artifacts"]}

        replaced = [a for a in overlay_manifest["artifacts"] if "overlay_delta" in a]
        self.assertGreater(len(replaced), 0, "expected at least one overlay-replaced artifact")

        for artifact in replaced:
            rel_path = artifact["target_path"]
            base_artifact = base_by_path[rel_path]
            base_bytes = (
                REPO_ROOT / "distribution/workflow" / base_version / base_artifact["location"]
            ).read_bytes()
            overlay_bytes = (
                REPO_ROOT / "distribution/workflow/2.4.0" / artifact["location"]
            ).read_bytes()

            delta = artifact["overlay_delta"]
            self.assertEqual(delta["base_sha256"], base_artifact["sha256"], rel_path)
            recomputed = self.build_release.unified_diff_sha256(base_bytes, overlay_bytes, rel_path)
            self.assertEqual(delta["diff_sha256"], recomputed, rel_path)

    def test_provenance_declares_authored_origin(self):
        overlay_manifest = json.loads(
            (REPO_ROOT / "distribution/workflow/2.4.0/manifest.json").read_text()
        )
        self.assertEqual(
            overlay_manifest["provenance"],
            {
                "origin": "authored",
                "base_release": "2.3.1",
                "overlay_commit": overlay_manifest["provenance"]["overlay_commit"],
            },
        )


class TestAuthoredReleaseCiTemplateSuiteNames(unittest.TestCase):
    """CP6's own explicit obligation: the regenerated `2.4.0` CI template
    must name exactly `CI_SUITES["2.4.0"]`'s own suite set, so the template
    a real consumer's CI would run never silently drifts from what this
    repository's own conformance matrix actually verifies."""

    def test_ci_template_names_exactly_the_240_suite_set(self):
        template_path = (
            REPO_ROOT / "distribution/workflow/2.4.0/templates/.github/workflows"
            "/workflow-conformance.yml"
        )
        text = template_path.read_text()
        named = set(re.findall(r"run:\s*python3\s+(\S+_test\.py)", text))
        self.assertEqual(named, set(CI_SUITES["2.4.0"]))


class TestOverlayStateWriterClosure(unittest.TestCase):
    """The `WFO-STATE-SERIALIZATION` closure-verifier gap (CP6's registry
    row): `scripts/workflow_state.py`'s own `discover_state_writers` only
    ever scans this repository's own `.claude/commands/`/`scripts/` trees
    (`STATE_WRITER_SURFACE_PREFIXES`) at a Git commit -- never
    `migration/overlays/<version>/payload/` -- so a new state writer
    authored inside an overlay was previously checked only by "the
    successor's own conformance run," which nothing schedules. This widens
    the scan to every present overlay's own writer surface, reusing the
    frozen module's own declaration regex/parser (imported, never
    reimplemented) against the overlay's own working-tree files."""

    @classmethod
    def setUpClass(cls):
        scripts_dir = REPO_ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import workflow_state
        cls.ws = workflow_state
        cls.overlay_roots = _overlay_payload_roots()

    def _surface_files(self, payload_root: Path) -> list[Path]:
        files: list[Path] = []
        for prefix in self.ws.STATE_WRITER_SURFACE_PREFIXES:
            base = payload_root / prefix
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts:
                    # Untracked bytecode cache -- never part of the real
                    # `git ls-tree`-derived surface `discover_state_writers`
                    # scans, but a filesystem `rglob` over a live working
                    # tree can see one left behind by an earlier ad hoc
                    # `python3 <payload file>` invocation.
                    continue
                if prefix == "scripts/" and path.name.endswith("_test.py"):
                    continue
                files.append(path)
        return files

    def test_at_least_one_authored_overlay_is_present(self):
        # A precondition, not the finding: if this ever goes empty (no
        # overlay directories at all), every other test in this class
        # would vacuously "pass" over zero files -- fail loudly instead.
        self.assertGreater(len(self.overlay_roots), 0)

    def test_every_overlay_writer_surface_file_declares_state_writer(self):
        for version, payload_root in self.overlay_roots:
            files = self._surface_files(payload_root)
            self.assertGreater(len(files), 0, version)
            for path in files:
                declared = self.ws._parse_state_writer_declarations(path.read_text())
                distinct = set(declared)
                self.assertEqual(
                    len(distinct), 1,
                    f"{version}:{path.relative_to(payload_root)}: missing or contradictory "
                    f"state_writer declaration (found {declared!r})",
                )

    def test_the_widened_scan_actually_covers_the_240_new_writers(self):
        """Not vacuous: the new command/module files CP2/CP3 authored are
        really among the scanned surface, so this closure genuinely covers
        the release's own new writers rather than only re-confirming the
        base payload's unchanged ones."""
        payload_root = dict(self.overlay_roots)["2.4.0"]
        files = {p.relative_to(payload_root).as_posix() for p in self._surface_files(payload_root)}
        self.assertIn(".claude/commands/request-plan-amendment.md", files)
        self.assertIn("scripts/workflow_state.py", files)


if __name__ == "__main__":
    unittest.main(verbosity=2)
