#!/usr/bin/env python3
"""The newest pinned release's frozen suites, run against what this
repository produces, and the per-release records they are checked against.

For `NEWEST_RELEASE` (the highest pinned version, `tests/support.py`), two
runs, both against disposable repositories built only from the release's
verified package:

`TestConformanceFixture`
    The frozen suites against the conformance fixture -- payload plus the
    `host-evidence` documents the suites lint. Every suite must be green and
    every test count must equal `CI_SUITES[NEWEST_RELEASE]`, so a silently
    skipped or vanished test fails here rather than passing quietly.

`TestBootstrappedTarget`
    The same suites against a clean target with no upstream history at all.
    The failure set must be *exactly* `tests/portability_exceptions.json`'s
    own `by_version[NEWEST_RELEASE]` exceptions -- not a subset, not a
    superset.

The classes carry no version in their names, so pinning a new release
retargets them with no edit (plan 7.1, `D-Tested-Releases`). Older pinned
releases are not run again: a published release is immutable, and its
`CI_SUITES` counts and portability exceptions stay as frozen records, which
`TestAuthoredReleaseCiTemplateSuiteNames` and
`TestPortabilityExceptions250RequiredEmptyEntry` below still check.

The matrix classes' frozen-suite results come from `tests/frozen_runs.py`:
run here in `setUpClass`, one repository, every suite in order (direct mode,
whenever `WM_FROZEN_RECORDS` is unset), or merged from independently run
chunk records against a merge context (merged mode, set up by the parallel
executor). The assertions read the same per-suite fields either way.
"""

from __future__ import annotations

import json
import re
import unittest

import support
from support import (
    CI_SUITES,
    NEWEST_RELEASE,
    PINNED_VERSIONS,
    expected_portability_exceptions,
)

from frozen_runs import open_matrix_run


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
    """Assertions for `TestConformanceFixture`, parameterized by
    `WORKFLOW_VERSION`. Deliberately a plain mixin, never itself a
    `unittest.TestCase`: subclassing `TestCase` here would let the test
    loader discover and run this body on its own, with no `WORKFLOW_VERSION`
    to build a fixture from."""

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

class TestConformanceFixture(_ConformanceFixtureAssertions, unittest.TestCase):
    """Frozen suites, frozen host context, the newest pinned payload:
    everything green."""

    WORKFLOW_VERSION = NEWEST_RELEASE

    class Run(_SuiteRun):
        pass


class _BootstrappedTargetAssertions:
    """Assertions for `TestBootstrappedTarget` -- mirrors
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

class TestBootstrappedTarget(_BootstrappedTargetAssertions, unittest.TestCase):
    """Frozen suites, clean target, the newest pinned payload: green except
    the documented exceptions."""

    WORKFLOW_VERSION = NEWEST_RELEASE

    class Run(_SuiteRun):
        pass


class TestAuthoredReleaseCiTemplateSuiteNames(unittest.TestCase):
    """CP6's own explicit obligation: each authored release's CI template
    must name exactly that release's own `CI_SUITES[version]` suite set, so
    the template a real consumer's CI would run never silently drifts from
    what the conformance matrix verifies. Covers every pinned version except
    `2.3.1` (the upstream extraction, which ships no such template), each
    read from its verified package, so a newly pinned release joins with no
    edit."""

    def test_ci_template_names_exactly_its_own_suite_set(self):
        versions = [v for v in PINNED_VERSIONS if v != "2.3.1"]
        self.assertGreater(len(versions), 0)
        for version in versions:
            with self.subTest(version=version):
                text = support.release(version).read(
                    "templates/.github/workflows/workflow-conformance.yml").decode()
                named = set(re.findall(r"run:\s*python3\s+(\S+_test\.py)", text))
                self.assertEqual(named, set(CI_SUITES[version]))


class TestPinnedVersionsCarryTheirRecords(unittest.TestCase):
    """Plan 7.1: the pinned versions, `CI_SUITES`'s keys and
    `tests/portability_exceptions.json`'s `by_version` keys are one set, so
    pinning a release forces its counts and its (possibly empty) exceptions
    entry, and no test can subscript a version the data lacks."""

    def test_pins_counts_and_exceptions_name_the_same_versions(self):
        pinned = set(PINNED_VERSIONS)
        self.assertEqual(set(CI_SUITES), pinned)
        self.assertEqual(set(support.PORTABILITY_EXCEPTIONS["by_version"]), pinned)

    def test_the_matrix_runs_the_newest_pin(self):
        self.assertEqual(NEWEST_RELEASE, PINNED_VERSIONS[-1])
        self.assertEqual(TestConformanceFixture.WORKFLOW_VERSION, NEWEST_RELEASE)
        self.assertEqual(TestBootstrappedTarget.WORKFLOW_VERSION, NEWEST_RELEASE)


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
