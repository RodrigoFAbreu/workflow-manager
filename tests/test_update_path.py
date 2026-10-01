#!/usr/bin/env python3
"""The update path the pins define: `UPGRADE_FROM` bootstrapped, then updated
to `NEWEST_RELEASE` (plan 7.1 and 7.2, `D-Tested-Releases`).

`TestUpdatedRepositorySatisfiesTheFrozenSuite` is the frozen matrix's fourth
fixture, `updated`: the newest release's frozen suites run in a repository
that reached that release through the real `update` rather than a fresh
bootstrap, with the same expected failure set as `bootstrapped` and the same
post-run checks (a clean `git status`, no drift). The host classes below it
drive the same update through the CLI and check what it leaves behind.

Nothing here names a version: it follows the pins, so pinning a new release
retargets it (`2.6.0` -> `2.7.0`, say) with no edit.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support
from support import NEWEST_RELEASE, PINNED_VERSIONS, REPO_ROOT, UPGRADE_FROM, cli_env

from frozen_runs import empty_repo
from test_bootstrap_e2e import _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions
from workflow_manager import source
from workflow_manager.installation import Installation
from workflow_manager.release import sha256


class TestUpdatedRepositorySatisfiesTheFrozenSuite(
    _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions, unittest.TestCase,
):
    """The gate for updating: `UPGRADE_FROM` bootstrapped and committed, then
    updated to the newest pinned release and committed, behaves like that
    frozen release. A newest suite that fails only here is an upstream
    defect, never a portability exception (plan 7.1)."""

    WORKFLOW_VERSION = NEWEST_RELEASE
    FIXTURE = "updated"


class TestTheRealPinsDefineAnUpdatePath(unittest.TestCase):
    """The `updated` fixture drops out of the matrix when only one release
    is pinned; the real repository must never be in that state silently."""

    def test_upgrade_from_is_the_release_below_the_newest(self):
        self.assertIsNotNone(UPGRADE_FROM)
        self.assertEqual(PINNED_VERSIONS[-2:], [UPGRADE_FROM, NEWEST_RELEASE])

    def test_the_matrix_carries_the_updated_class(self):
        from parallel import matrix

        self.assertIn(
            "host:test_update_path.py::TestUpdatedRepositorySatisfiesTheFrozenSuite",
            matrix.FROZEN_MATRIX)
        self.assertEqual(set(matrix.FROZEN_MATRIX.values()),
                         {(NEWEST_RELEASE, f) for f in matrix.FIXTURES})


class TestCliUpdateToTheNewestRelease(unittest.TestCase):
    """`bootstrap --release-version UPGRADE_FROM`, then a bare `update`,
    through the documented entry point."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.target = empty_repo(Path(cls._tmp.name) / "consumer")
        cls.bootstrapped = cls._cli("--release-version", UPGRADE_FROM, "bootstrap",
                                    str(cls.target))
        cls.before = Installation.read(cls.target) if cls.bootstrapped.returncode == 0 else None
        cls.updated = cls._cli("update", str(cls.target))
        cls.release = support.release(NEWEST_RELEASE)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @staticmethod
    def _cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "workflow_manager", *args],
            cwd=str(REPO_ROOT), capture_output=True, text=True, env=cli_env(),
        )

    def test_the_bootstrap_and_the_update_succeed(self):
        self.assertEqual(self.bootstrapped.returncode, 0, self.bootstrapped.stderr)
        self.assertEqual(self.before.workflow_version, UPGRADE_FROM)
        self.assertEqual(self.updated.returncode, 0, self.updated.stderr)
        self.assertIn(f"updated {self.target} to workflow {NEWEST_RELEASE}",
                      self.updated.stdout)

    def test_the_record_names_the_newest_release_and_its_package(self):
        record = Installation.read(self.target)
        self.assertEqual(record.workflow_version, NEWEST_RELEASE)
        self.assertEqual(record.source, source.load_pins().source_record(NEWEST_RELEASE))
        self.assertEqual(record.installed_at, self.before.installed_at)

    def test_every_managed_file_holds_the_newest_release_bytes(self):
        record = Installation.read(self.target)
        artifacts = self.release.installable(record.profile)
        self.assertTrue(artifacts)
        for artifact in artifacts:
            with self.subTest(path=artifact.target_path):
                path = self.target / artifact.target_path
                self.assertEqual(sha256(path.read_bytes()), artifact.sha256)

    def test_the_updated_repository_verifies(self):
        checked = self._cli("verify", str(self.target))
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
