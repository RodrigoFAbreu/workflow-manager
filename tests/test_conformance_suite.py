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

`231`/`240`/`250` name the three releases (`2.3.1`, `2.4.0`, `2.5.0`);
`2.3.1`'s own run stays exactly as it always was -- CP6 adds the `2.4.0` run
beside it, never in place of it, and `implementation-review-two-stage`
(`workflow-2.5.0`) adds `2.5.0` the same way beside both.

Below the version-parameterized matrix, three more checks cover the
authored releases specifically -- `TestAuthoredReleaseOverlayDelta` (I2 --
every recorded overlay diff really reproduces from base + diff alone),
`TestAuthoredReleaseCiTemplateSuiteNames` (each shipped CI template names
exactly the suite set this matrix itself verifies), and
`TestOverlayStateWriterClosure` (the `WFO-STATE-SERIALIZATION`
closure-verifier gap: widening its scan to every present overlay's own
`.claude/commands/`/`scripts/` writer surface) -- CP6 introduced these
once, but every authored release added since (`2.5.0`) parametrizes all
three over its own overlay rather than adding a second hand-written copy,
so "once" now means "once per check, iterated over every authored release
present," not "never per-version."

Slow (~2 minutes per release): the acceptance matrix drives real `git` and
the real `prepare-ai-review.sh` across 146 rows, twice per release.

The matrix classes' frozen-suite results come from `tests/frozen_runs.py`:
run here in `setUpClass`, one repository, every suite in order (direct mode,
whenever `WM_FROZEN_RECORDS` is unset), or merged from independently run
chunk records against a merge context (merged mode, set up by the parallel
executor). The assertions read the same per-suite fields either way.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from support import (
    CI_SUITES,
    REPO_ROOT,
    expected_portability_exceptions,
)

from frozen_runs import open_matrix_run
from workflow_manager.release import find_release


def _ran(result) -> int:
    if result.ran is None:
        raise AssertionError(f"no unittest summary in output:\n{result.output[-2000:]}")
    return result.ran


class _SuiteRun:
    """One build of a disposable repository, with every frozen suite's result
    -- run once in that repository (direct mode), or merged from chunk
    records (merged mode; `tests/frozen_runs.py`). `results` maps each suite
    to a `frozen_runs.MergedResult` either way."""

    results: dict = {}
    root: Path | None = None
    workflow_version: str | None = None
    _run = None

    @classmethod
    def build(cls, fixture: str, workflow_version: str):
        cls.workflow_version = workflow_version
        cls._run = open_matrix_run(workflow_version, fixture)
        cls.root = cls._run.root
        cls.results = cls._run.results

    @classmethod
    def teardown(cls):
        if cls._run is not None:
            cls._run.cleanup()
            cls._run = None


class _ConformanceFixtureAssertions:
    """Shared assertions for `TestConformanceFixture*`, parameterized per
    release by `WORKFLOW_VERSION`. Deliberately a plain mixin, never itself a
    `unittest.TestCase`: subclassing `TestCase` here would let the test
    loader discover and run this shared body on its own, with no
    `WORKFLOW_VERSION` to build a fixture from."""

    WORKFLOW_VERSION: str

    @classmethod
    def setUpClass(cls):
        cls.Run.build("conformance", workflow_version=cls.WORKFLOW_VERSION)

    @classmethod
    def tearDownClass(cls):
        cls.Run.teardown()

    def test_every_frozen_suite_passes(self):
        failed = {
            suite: result.output
            for suite, result in self.Run.results.items() if result.returncode != 0
        }
        self.assertEqual(sorted(failed), [], "\n\n".join(failed.values())[-4000:])

    def test_every_suite_runs_the_frozen_number_of_tests(self):
        counts = {
            suite: _ran(result)
            for suite, result in self.Run.results.items()
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


class TestConformanceFixture250(_ConformanceFixtureAssertions, unittest.TestCase):
    """workflow-2.5.0's own CP11 obligation, mirroring `TestConformance
    Fixture240` exactly: the same frozen suite, run a third time against
    `distribution/workflow/2.5.0/`'s own authored payload, in addition to
    (never instead of) `TestConformanceFixture231`/`TestConformanceFixture240`
    above."""

    WORKFLOW_VERSION = "2.5.0"

    class Run(_SuiteRun):
        pass


class TestConformanceFixture251(_ConformanceFixtureAssertions, unittest.TestCase):
    """workflow-2.5.1's own CP2 obligation
    (`D-Checkpoint-Id-Anchor-Grammar-Widening`), mirroring
    `TestConformanceFixture250` exactly: the same frozen suite, run a
    fourth time against `distribution/workflow/2.5.1/`'s own authored
    payload, in addition to (never instead of) `TestConformanceFixture231`/
    `TestConformanceFixture240`/`TestConformanceFixture250` above."""

    WORKFLOW_VERSION = "2.5.1"

    class Run(_SuiteRun):
        pass


class TestConformanceFixture260(_ConformanceFixtureAssertions, unittest.TestCase):
    """workflow-2.6.0's own CP7 obligation
    (workflow-review-artifact-and-concurrency-hardening), mirroring
    `TestConformanceFixture251` exactly: the same frozen suite, run a fifth
    time against `distribution/workflow/2.6.0/`'s own authored payload, in
    addition to (never instead of) the earlier releases' classes above."""

    WORKFLOW_VERSION = "2.6.0"

    class Run(_SuiteRun):
        pass


class _BootstrappedTargetAssertions:
    """Shared assertions for `TestBootstrappedTarget*` -- mirrors
    `_ConformanceFixtureAssertions`'s own mixin shape and reasoning."""

    WORKFLOW_VERSION: str

    @classmethod
    def setUpClass(cls):
        cls.Run.build("target", workflow_version=cls.WORKFLOW_VERSION)

    @classmethod
    def tearDownClass(cls):
        cls.Run.teardown()

    def test_failures_are_exactly_the_documented_portability_exceptions(self):
        expected = expected_portability_exceptions(self.WORKFLOW_VERSION)
        actual = {}
        for suite, result in self.Run.results.items():
            names = set(result.failing)
            if names:
                actual[suite] = names
        self.assertEqual(actual, expected)

    def test_every_suite_still_runs_the_frozen_number_of_tests(self):
        """A target must not lose tests -- only fail the documented ones."""
        counts = {
            suite: _ran(result)
            for suite, result in self.Run.results.items()
        }
        self.assertEqual(counts, dict(CI_SUITES[self.WORKFLOW_VERSION]))

    def test_suites_with_no_exception_pass_outright(self):
        expected = expected_portability_exceptions(self.WORKFLOW_VERSION)
        for suite, result in self.Run.results.items():
            if suite in expected:
                continue
            self.assertEqual(result.returncode, 0,
                             f"{suite} failed:\n{result.output[-3000:]}")

    def test_the_target_carries_no_upstream_host_document(self):
        text = (self.Run.root / "docs/ACTIVE_MILESTONE.md").read_text()
        self.assertNotIn("RepFlow", text)
        self.assertNotIn("Status note (2026-08-04)", text)

    def test_every_documented_exception_actually_fires(self):
        """The exception list is not allowed to accumulate stale entries: each
        one must be a test that really does fail in a clean target."""
        expected = expected_portability_exceptions(self.WORKFLOW_VERSION)
        for suite, tests in expected.items():
            observed = set(self.Run.results[suite].failing)
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


class TestBootstrappedTarget250(_BootstrappedTargetAssertions, unittest.TestCase):
    """workflow-2.5.0's own CP11 obligation, mirroring `TestBootstrappedTarget240`
    exactly: the same clean-target run, a third time, against `2.5.0`'s own
    authored payload."""

    WORKFLOW_VERSION = "2.5.0"

    class Run(_SuiteRun):
        pass


class TestBootstrappedTarget251(_BootstrappedTargetAssertions, unittest.TestCase):
    """workflow-2.5.1's own CP2 obligation
    (`D-Checkpoint-Id-Anchor-Grammar-Widening`), mirroring
    `TestBootstrappedTarget250` exactly: the same clean-target run, a
    fourth time, against `2.5.1`'s own authored payload."""

    WORKFLOW_VERSION = "2.5.1"

    class Run(_SuiteRun):
        pass


class TestBootstrappedTarget260(_BootstrappedTargetAssertions, unittest.TestCase):
    """workflow-2.6.0's own CP7 obligation
    (workflow-review-artifact-and-concurrency-hardening), mirroring
    `TestBootstrappedTarget251` exactly: the same clean-target run, a fifth
    time, against `2.6.0`'s own authored payload."""

    WORKFLOW_VERSION = "2.6.0"

    class Run(_SuiteRun):
        pass


def _overlay_payload_roots() -> list[tuple[str, Path]]:
    """`(version, payload_root)` for every authored overlay present under
    `migration/overlays/` -- today `2.4.0`, `2.5.0`, `2.5.1`, and `2.6.0`, but never
    hardcoded to any of them: a further authored release adds its own
    overlay directory and is picked up here without touching this file
    (mirrors D-Authored-Release-4's own "for every authored release
    present" phrasing, CP6's registry row)."""
    overlays_dir = REPO_ROOT / "migration" / "overlays"
    roots = []
    if overlays_dir.is_dir():
        for entry in sorted(overlays_dir.iterdir()):
            payload = entry / "payload"
            if payload.is_dir():
                roots.append((entry.name, payload))
    return roots


def _authored_release_versions() -> list[str]:
    """Version strings for every authored release present *and already
    built* -- the version half of `_overlay_payload_roots()`'s own pairs,
    filtered down to those with a `distribution/workflow/<version>/
    manifest.json` on disk, reused wherever a test needs the version list
    without the payload path.

    round-3 I1: every consumer of this list (`test_every_overlay_delta_
    reproduces_from_base_and_overlay_bytes`, `test_no_missing_file_no_
    digest_mismatch_no_stray_file` via `find_release`, `test_ci_template_
    names_exactly_its_own_suite_set` via `CI_SUITES[version]`, and
    `test_build_release_check_reproduces_every_authored_release`) reads
    *built*-release artifacts, never the overlay alone. The previous
    overlay-only key made this list disagree with what those four guards
    can actually read for the entire span of an authored release's own
    milestone between the checkpoint that authors its overlay and the
    checkpoint that builds its release (ten checkpoints wide in the
    `2.5.0` milestone itself) -- surfacing as a raw `FileNotFoundError`/
    `KeyError` with nothing connecting it to "overlay authored, release
    not yet built" rather than a clean, explanatory result. Keying on the
    built side instead means an overlay-without-a-built-release is simply
    absent from this list until `tools/build_release.py` runs -- exactly
    the state `test_at_least_one_authored_release_is_built` below still
    guards against going silently empty."""
    return [
        version
        for version, _payload in _overlay_payload_roots()
        if (REPO_ROOT / "distribution/workflow" / version / "manifest.json").is_file()
    ]


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

    def test_an_overlay_without_a_built_release_is_silently_excluded(self):
        # round-3 I1's own regression pin: an overlay directory present with
        # no corresponding built release must be excluded from
        # `_authored_release_versions()`, never raise. Demonstrated live
        # against the real tree during this fix (a scratch
        # `migration/overlays/9.9.9-scratch-demo/payload/` with no
        # `distribution/workflow/9.9.9-scratch-demo/` was silently dropped
        # from the list and the whole class stayed green); this pins the
        # same behavior permanently via a temporary `REPO_ROOT`.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            (tmp_root / "migration" / "overlays" / "9.9.9-unbuilt" / "payload").mkdir(parents=True)
            (tmp_root / "migration" / "overlays" / "2.4.0" / "payload").mkdir(parents=True)
            (tmp_root / "distribution" / "workflow" / "2.4.0").mkdir(parents=True)
            (tmp_root / "distribution" / "workflow" / "2.4.0" / "manifest.json").write_text("{}")
            with unittest.mock.patch(f"{__name__}.REPO_ROOT", tmp_root):
                self.assertEqual(_authored_release_versions(), ["2.4.0"])

    def test_at_least_one_authored_release_is_built(self):
        # round-3 I1's own anti-vacuity twin: `_authored_release_versions()`
        # is now keyed on the *built* side (a `distribution/workflow/
        # <version>/manifest.json` on disk), separately from
        # `test_at_least_one_authored_overlay_is_present`'s overlay-side
        # precondition below -- an overlay authored but not yet built would
        # otherwise silently empty this list and make every test in this
        # class vacuously pass over zero versions.
        self.assertGreater(len(_authored_release_versions()), 0)

    def test_every_overlay_delta_reproduces_from_base_and_overlay_bytes(self):
        # I1: parametrized over every authored release present
        # (`_authored_release_versions()`), not hardcoded to `2.4.0` --
        # `2.5.0` is a second authored release, built on `2.4.0` (itself
        # authored), and this is the guard that would have caught B1 (a
        # stale `overlay_delta` copied forward from the base release's own
        # manifest for a file `2.5.0` does not replace).
        for version in _authored_release_versions():
            with self.subTest(version=version):
                overlay_manifest_path = REPO_ROOT / "distribution/workflow" / version / "manifest.json"
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
                        REPO_ROOT / "distribution/workflow" / version / artifact["location"]
                    ).read_bytes()

                    delta = artifact["overlay_delta"]
                    self.assertEqual(delta["base_sha256"], base_artifact["sha256"], rel_path)
                    recomputed = self.build_release.unified_diff_sha256(base_bytes, overlay_bytes, rel_path)
                    self.assertEqual(delta["diff_sha256"], recomputed, rel_path)

    def test_provenance_declares_authored_origin(self):
        # round-3 O1: parametrized over every authored release present
        # (`_authored_release_versions()`), not hardcoded to `2.4.0` alone
        # -- `2.5.0`'s own `provenance` (the field distinguishing "authored,
        # on an authored base" from a fresh upstream extraction) was
        # previously asserted by nothing. Each version's expected
        # `base_release` comes from its own `classification.json`'s
        # `base_workflow_version` -- an independent source, never the
        # manifest's own self-reported value.
        for version in _authored_release_versions():
            with self.subTest(version=version):
                overlay_manifest = json.loads(
                    (REPO_ROOT / "distribution/workflow" / version / "manifest.json").read_text()
                )
                classification = json.loads(
                    (REPO_ROOT / "migration/overlays" / version / "classification.json").read_text()
                )
                self.assertEqual(
                    overlay_manifest["provenance"],
                    {
                        "origin": "authored",
                        "base_release": classification["base_workflow_version"],
                        "overlay_commit": overlay_manifest["provenance"]["overlay_commit"],
                    },
                )

    def test_build_release_check_reproduces_every_authored_release(self):
        """Missing-tests item 1: `tools/migrate.py --check` is asserted
        twice elsewhere (`test_payload_bytes.py`, `test_amendment_update_
        path.py`), guarding `2.3.1`'s reproducibility from the suite --
        `2.4.0`'s own `tools/build_release.py --check` reproducibility had
        no equivalent, even though `CLAUDE.md`'s "Adding an authored
        Workflow release" step 2 and `docs/MIGRATION.md`'s evidence table
        both make it normative. `--check` builds into a throwaway temporary
        root and only diffs against what is committed -- it writes nothing
        under the real `distribution/`. I1: parametrized over every
        authored release present (`_authored_release_versions()`) rather
        than a second hardcoded version string, so `2.5.0` (built on the
        authored `2.4.0`, not a fresh upstream tag) gets the same
        reproducibility proof from `tests/run_all.py` itself, not only from
        a hand-run command recorded in `TEST_RESULTS.md`."""
        for version in _authored_release_versions():
            with self.subTest(version=version):
                proc = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "tools" / "build_release.py"),
                     "--overlay", str(REPO_ROOT / "migration" / "overlays" / version), "--check"],
                    cwd=str(REPO_ROOT), capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestBuildReleaseCollisionGuards(unittest.TestCase):
    """IMPL-O1/Missing-tests item 4: `tools/build_release.py`'s
    `target_path` collision guards, exercised against small synthetic
    base+overlay fixtures built fresh per test -- never against the real
    `2.3.1`/`2.4.0` releases, which carry no such collision (latent, not
    live, in both bases)."""

    @classmethod
    def setUpClass(cls):
        tools_dir = REPO_ROOT / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import build_release
        cls.build_release = build_release

    def _write_base_release(self, base_root: Path, *, artifacts=(), templates=()):
        """`artifacts`/`templates`: iterables of `(target_path, location, data)`."""
        artifact_records = []
        for target_path, location, data in artifacts:
            path = base_root / location
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            artifact_records.append({
                "target_path": target_path, "location": location,
                "category": "host-evidence" if location.startswith("fixtures/") else "distribution",
                "sha256": self.build_release.sha256(data), "size": len(data), "executable": False,
            })
        template_records = []
        for target_path, location, data in templates:
            path = base_root / location
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            template_records.append({
                "target_path": target_path, "location": location,
                "sha256": self.build_release.sha256(data), "size": len(data), "executable": False,
            })
        manifest = {
            "schema_version": 1,
            "workflow_version": "9.9.9",
            "upstream": {"origin": "test"},
            "provenance": {"origin": "upstream"},
            "categories": {"distribution": "test", "host-evidence": "test"},
            "artifacts": artifact_records,
            "templates": template_records,
        }
        (base_root / "manifest.json").write_text(json.dumps(manifest))

    def _write_overlay(self, overlay_dir: Path, *, rel_path: str, expected_kind: str, data: bytes):
        classification = {
            "schema_version": 1,
            "workflow_version": "10.0.0",
            "base_workflow_version": "9.9.9",
            "categories": {"distribution": "test"},
            "rules": [
                {
                    "pattern": f"^{re.escape(rel_path)}$", "category": "distribution",
                    "rationale": "test", "expected_kind": expected_kind,
                },
            ],
        }
        overlay_dir.mkdir(parents=True, exist_ok=True)
        (overlay_dir / "classification.json").write_text(json.dumps(classification))
        payload_path = overlay_dir / "payload" / rel_path
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(data)

    def test_overlay_payload_colliding_with_a_base_template_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_dist_root = root / "base_dist"
            base_root = base_dist_root / "workflow" / "9.9.9"
            self._write_base_release(
                base_root,
                templates=[("collide.txt", "templates/collide.txt", b"base template bytes")],
            )
            overlay_dir = root / "overlay"
            self._write_overlay(
                overlay_dir, rel_path="collide.txt", expected_kind="added", data=b"overlay bytes",
            )
            out_dist_root = root / "out_dist"
            with self.assertRaises(self.build_release.BuildReleaseError) as ctx:
                self.build_release.build("9.9.9", overlay_dir, base_dist_root, out_dist_root)
            self.assertIn("base template", str(ctx.exception))

    def test_overlay_payload_colliding_with_a_non_payload_base_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_dist_root = root / "base_dist"
            base_root = base_dist_root / "workflow" / "9.9.9"
            self._write_base_release(
                base_root,
                artifacts=[("collide.md", "fixtures/collide.md", b"base fixture bytes")],
            )
            overlay_dir = root / "overlay"
            self._write_overlay(
                overlay_dir, rel_path="collide.md", expected_kind="added", data=b"overlay bytes",
            )
            out_dist_root = root / "out_dist"
            with self.assertRaises(self.build_release.BuildReleaseError) as ctx:
                self.build_release.build("9.9.9", overlay_dir, base_dist_root, out_dist_root)
            self.assertIn("non-payload base artifact", str(ctx.exception))


class TestAuthoredReleaseIsSelfConsistent(unittest.TestCase):
    """Missing-tests item 2: CP4 pinned every `find_release(REPO_ROOT)` in
    `test_payload_bytes.py`, `test_migration_inventory.py`, `test_templates.py`
    and `test_no_live_state_imported.py` to `"2.3.1"`, so the "no missing
    file, no digest mismatch, no stray file" self-consistency check
    (`Release.verify()`) covered only `2.3.1` -- `TestAuthoredReleaseOverlayDelta`
    above covers the 11 replaced payload files' own `overlay_delta`
    reproduction, but nothing gave `2.4.0` the same whole-release digest
    guard `2.3.1` already has."""

    def test_no_missing_file_no_digest_mismatch_no_stray_file(self):
        # I1: parametrized over every authored release present, mirroring
        # TestAuthoredReleaseOverlayDelta above -- mechanical given
        # `_authored_release_versions()` already exists for that purpose.
        for version in _authored_release_versions():
            with self.subTest(version=version):
                release = find_release(REPO_ROOT, version)
                self.assertEqual(release.verify(), [])


class TestAuthoredReleaseCiTemplateSuiteNames(unittest.TestCase):
    """CP6's own explicit obligation: each regenerated authored-release CI
    template must name exactly that release's own `CI_SUITES[version]` suite
    set, so the template a real consumer's CI would run never silently
    drifts from what this repository's own conformance matrix actually
    verifies. I1: parametrized over every authored release present, not
    hardcoded to `2.4.0`."""

    def test_ci_template_names_exactly_its_own_suite_set(self):
        for version in _authored_release_versions():
            with self.subTest(version=version):
                template_path = (
                    REPO_ROOT / "distribution/workflow" / version / "templates/.github/workflows"
                    "/workflow-conformance.yml"
                )
                text = template_path.read_text()
                named = set(re.findall(r"run:\s*python3\s+(\S+_test\.py)", text))
                self.assertEqual(named, set(CI_SUITES[version]))


class TestAuthoredReleaseOverlayCommitIsReachable(unittest.TestCase):
    """Missing-tests item carried from rounds 8 and 9
    (`implementation-review-two-stage`): each authored release's own
    `manifest.json` records `provenance.overlay_commit` -- the last
    overlay-tree commit `build_release.py` composed from -- but nothing
    checks it actually is one. `build_release.py --check` cannot catch a
    dangling value here by construction (round 8/9's `B2`/round 10's `O1`
    both found and fixed a real instance of exactly this): it feeds the
    *recorded* `overlay_commit` back in as `now_commit`, so the
    reproducibility check is never `HEAD`-sensitive and passes green
    against a broken manifest. One line closes the gap: `git merge-base
    --is-ancestor <recorded> HEAD` must exit zero."""

    def test_overlay_commit_is_an_ancestor_of_head(self):
        for version in _authored_release_versions():
            with self.subTest(version=version):
                manifest = json.loads(
                    (REPO_ROOT / "distribution/workflow" / version / "manifest.json").read_text()
                )
                overlay_commit = manifest["provenance"]["overlay_commit"]
                result = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", overlay_commit, "HEAD"],
                    cwd=REPO_ROOT,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"{version}: recorded overlay_commit {overlay_commit!r} is not an "
                    f"ancestor of HEAD",
                )


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


def _load_release_module(version: str, name: str):
    """Load `name` (e.g. `"workflow_state"`) out of the *built*
    `distribution/workflow/<version>/payload/scripts/` tree under a
    version-qualified module name, never the bare name -- so a caller in
    this same process can hold this release's copy of a module alongside
    this repository's own `scripts/` copy (already cached under the bare
    name by `TestOverlayStateWriterClosure.setUpClass` above) without one
    shadowing the other. Always re-execs from source; never trusts
    whatever a previous bare `import` may have already cached."""
    scripts = REPO_ROOT / "distribution" / "workflow" / version / "payload" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    qualified = f"_release_{version.replace('.', '_')}_{name}"
    spec = importlib.util.spec_from_file_location(qualified, scripts / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


class TestReleaseMetadataVersionClaimCorpus250(unittest.TestCase):
    """Round 10's `B1`: the corpus widening round 9 asked for
    (`test_real_corpus_sweep_is_clean` in both
    `GoverningVersionEnumerationSweepTest` and
    `ApplyingReviewFeedbackVersionClaimSweepTest`,
    `migration/overlays/2.5.0/payload/scripts/workflow_state_test.py`,
    introduced by `29aaf24`) resolved `version_root` to `payload_root.parent`
    -- correct only while the payload sits inside
    `distribution/workflow/2.5.0/` or `migration/overlays/2.5.0/`, and
    pointing *outside the repository* once the payload is installed, which
    is the only context any automated run (`tests/support.py`'s
    `run_suite`) actually uses. The widened corpus was therefore empty in
    every real run and the guard never fired. That widening is reverted in
    both copies of `workflow_state_test.py` (a payload test must never read
    above `payload_root`); this class re-homes the guard here instead,
    where `distribution/workflow/2.5.0/manifest.json` and
    `migration/overlays/2.5.0/classification.json` are real, resolvable,
    repository-side paths, and proves the corpus is genuinely non-empty
    before trusting either sweep's `[]` result (this repository's own
    `test_at_least_one_authored_overlay_is_present` pattern, applied here).

    The sweep functions themselves (`sweep_governing_version_enumeration`,
    `sweep_applying_review_feedback_version_claims`) exist only in
    `2.5.0`'s own payload copy of `workflow_state.py`, not in this
    repository's own `scripts/` (still `2.4.0`), so this class loads that
    built copy directly by path rather than importing the repository's own
    module -- and is itself named for the one release it applies to, like
    `TestPortabilityExceptions250RequiredEmptyEntry` above."""

    @classmethod
    def setUpClass(cls):
        cls.ws = _load_release_module("2.5.0", "workflow_state")
        cls.manifest_path = REPO_ROOT / "distribution" / "workflow" / "2.5.0" / "manifest.json"
        cls.classification_path = REPO_ROOT / "migration" / "overlays" / "2.5.0" / "classification.json"

    def _corpus(self) -> dict[str, str]:
        return {
            str(cls_path): cls_path.read_text()
            for cls_path in (self.manifest_path, self.classification_path)
            if cls_path.is_file()
        }

    def test_corpus_is_not_empty(self):
        # Precondition: both real files must actually contribute, or the
        # sweeps below would pass vacuously over an empty corpus -- exactly
        # `B1`'s own failure mode, guarded against rather than repeated.
        texts = self._corpus()
        self.assertIn(str(self.manifest_path), texts)
        self.assertIn(str(self.classification_path), texts)

    def test_manifest_and_classification_have_no_governing_version_enumeration(self):
        findings = self.ws.sweep_governing_version_enumeration(self._corpus())
        self.assertEqual(findings, [], [repr(f) for f in findings])

    def test_manifest_and_classification_have_no_applying_review_feedback_version_claims(self):
        findings = self.ws.sweep_applying_review_feedback_version_claims(self._corpus())
        self.assertEqual(findings, [], [repr(f) for f in findings])


class TestNoPayloadTestReadsAbovePayloadRoot(unittest.TestCase):
    """Missing-tests item from round 10's `B1`: a payload test must never
    resolve a path above its own `payload_root` -- once installed,
    `payload_root` **is** the target repository root, and a second
    `.parent` hop off it lands outside the repository entirely (exactly
    `B1`'s own failure mode, reverted above). One static, repository-wide
    lint over every overlay's own `payload/scripts/*_test.py`: none may
    reference `payload_root.parent`, the shape that climb takes."""

    def test_no_payload_test_climbs_above_payload_root(self):
        offenders = []
        for version, payload_root in _overlay_payload_roots():
            scripts_dir = payload_root / "scripts"
            if not scripts_dir.is_dir():
                continue
            for path in sorted(scripts_dir.glob("*_test.py")):
                if "payload_root.parent" in path.read_text():
                    offenders.append(f"{version}:{path.name}")
        self.assertEqual(offenders, [], offenders)


class TestPortabilityExceptions250RequiredEmptyEntry(unittest.TestCase):
    """`workflow-2.5.0` CP9 (`v2.3.1-001`'s own fix, revision 4 finding I4):
    `tests/support.py`'s `expected_portability_exceptions` subscripts
    `PORTABILITY_EXCEPTIONS["by_version"][workflow_version]["exceptions"]`
    unguarded, so an absent `"2.5.0"` key would be a `KeyError` at
    test-collection time for any future `2.5.0`-specific matrix, not a
    clean pass. `2.5.0`'s own `by_version` entry is therefore required, not
    conditional on whether this release's own suite happens to need one --
    and it is empty, since `2.5.0`'s own overlay fixes the one test
    (`v2.3.1-001`) that `2.3.1`'s and `2.4.0`'s entries exist for, while
    those two releases' own entries are left untouched: both releases' own
    payloads still carry the unfixed test (`2.3.1` is frozen; `2.4.0`'s own
    overlay never touched this specific test), so removing either would
    give a clean-target run against either release an undocumented
    failure."""

    def test_2_5_0_has_a_required_empty_entry(self):
        self.assertEqual(expected_portability_exceptions("2.5.0"), {})

    def test_2_3_1_entry_is_byte_unchanged_by_cp9(self):
        self.assertEqual(
            expected_portability_exceptions("2.3.1"),
            {
                "workflow_integration_test.py": {
                    "TestRetiredScopedRemediationLeavesNoLiveSurface."
                    "test_the_historical_status_note_carries_a_dated_correction",
                },
            },
        )

    def test_2_4_0_entry_is_byte_unchanged_by_cp9(self):
        self.assertEqual(
            expected_portability_exceptions("2.4.0"),
            {
                "workflow_integration_test.py": {
                    "TestRetiredScopedRemediationLeavesNoLiveSurface."
                    "test_the_historical_status_note_carries_a_dated_correction",
                },
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
