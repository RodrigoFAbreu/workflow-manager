#!/usr/bin/env python3
"""The frozen v2.3.1 suite, run against what this repository produces.

This is the equivalence evidence for the migration. Two runs, both against
disposable repositories built only from `distribution/`:

`TestConformanceFixture`
    The frozen suite against the conformance fixture -- payload plus the
    `host-evidence` documents the suite lints. Every suite must be green and
    every test count must equal the frozen upstream baseline, so a silently
    skipped or vanished test fails here rather than passing quietly.

`TestBootstrappedTarget`
    The same suite against a clean target with no upstream history at all.
    The failure set must be *exactly* the documented portability exceptions --
    not a subset, not a superset.

Slow (~2 minutes): the acceptance matrix drives real `git` and the real
`prepare-ai-review.sh` across 146 rows.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from support import CI_SUITES, PORTABILITY_EXCEPTIONS, REPO_ROOT, failing_tests, run_suite

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
    _tmp = None

    @classmethod
    def build(cls, builder):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = builder(find_release(REPO_ROOT), Path(cls._tmp.name) / "repo")
        cls.results = {suite: run_suite(cls.root, suite) for suite in CI_SUITES}

    @classmethod
    def teardown(cls):
        if cls._tmp is not None:
            cls._tmp.cleanup()
            cls._tmp = None


class TestConformanceFixture(unittest.TestCase):
    """Frozen suite, frozen host context: everything green."""

    class Run(_SuiteRun):
        pass

    @classmethod
    def setUpClass(cls):
        cls.Run.build(build_conformance_repo)

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
        self.assertEqual(counts, dict(CI_SUITES))

    def test_the_fixture_holds_no_upstream_build_system(self):
        for name in ("build.gradle.kts", "settings.gradle.kts", "gradlew", "app"):
            self.assertFalse((self.Run.root / name).exists(), name)

    def test_the_fixture_state_file_is_the_clean_template(self):
        import json
        state = json.loads(
            (self.Run.root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text()
        )
        self.assertEqual(state["work_items"], {})


class TestBootstrappedTarget(unittest.TestCase):
    """Frozen suite, clean target: green except the documented exceptions."""

    class Run(_SuiteRun):
        pass

    @classmethod
    def setUpClass(cls):
        cls.Run.build(build_target_repo)

    @classmethod
    def tearDownClass(cls):
        cls.Run.teardown()

    def _expected_failures(self) -> dict[str, set[str]]:
        expected: dict[str, set[str]] = {}
        for record in PORTABILITY_EXCEPTIONS["exceptions"]:
            expected.setdefault(record["suite"], set()).add(record["test"])
        return expected

    def test_failures_are_exactly_the_documented_portability_exceptions(self):
        expected = self._expected_failures()
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
        self.assertEqual(counts, dict(CI_SUITES))

    def test_suites_with_no_exception_pass_outright(self):
        expected = self._expected_failures()
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
        expected = self._expected_failures()
        for suite, tests in expected.items():
            proc = self.Run.results[suite]
            observed = failing_tests(proc.stdout + proc.stderr)
            self.assertEqual(tests & observed, tests, f"{suite}: stale exception entry")


if __name__ == "__main__":
    unittest.main(verbosity=2)
