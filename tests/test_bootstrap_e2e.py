#!/usr/bin/env python3
"""End to end: a repository the real bootstrapper produced.

`test_conformance_suite.py` runs the frozen suite against a fixture assembled
directly from the release. This suite runs it against a repository produced by
`install.bootstrap` -- the code a real consumer would run -- and then puts that
repository through an update cycle with live work-item state in it.

Slow (~2 minutes per release): `TestBootstrappedRepositorySatisfiesTheFrozen
Suite231`/`240` (CP6) each drive the frozen acceptance matrix once, against a
repository bootstrapped from `2.3.1` and from `2.4.0` respectively.

The matrix classes' frozen-suite results come from `tests/frozen_runs.py`:
run here in `setUpClass`, one repository, every suite in order (direct mode,
whenever `WM_FROZEN_RECORDS` is unset), or merged from independently run
chunk records against a merge context (merged mode, set up by the parallel
executor). The assertions read the same per-suite fields either way.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import CI_SUITES, REPO_ROOT, expected_portability_exceptions

from frozen_runs import FIXED_NOW, open_matrix_run
from frozen_runs import empty_repo as _empty_repo
from workflow_manager.install import bootstrap, update, verify
from workflow_manager.installation import Installation
from workflow_manager.release import find_release, sha256


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True).stdout


class _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions:
    """Shared assertions for `TestBootstrappedRepositorySatisfiesTheFrozen
    Suite*`, parameterized per release by `WORKFLOW_VERSION` -- mirrors
    `test_conformance_suite.py`'s own mixin shape and reasoning (a plain
    mixin, never itself a `unittest.TestCase`, so the shared body is never
    discovered and run on its own with no `WORKFLOW_VERSION` to bootstrap)."""

    WORKFLOW_VERSION: str

    @classmethod
    def setUpClass(cls):
        # `frozen_runs.build_bootstrapped_repo` is the bootstrap-and-commit
        # this class always did; `results` maps each suite to a
        # `frozen_runs.MergedResult`, run here (direct mode) or merged from
        # chunk records (merged mode), and the post-run residue and drift
        # travel with each suite's result.
        cls.matrix_run = open_matrix_run(cls.WORKFLOW_VERSION, "bootstrapped")
        cls.release = cls.matrix_run.release
        cls.target = cls.matrix_run.root
        cls.results = cls.matrix_run.results

    @classmethod
    def tearDownClass(cls):
        cls.matrix_run.cleanup()

    def test_failures_are_exactly_the_documented_exceptions(self):
        actual = {}
        for suite, result in self.results.items():
            names = set(result.failing)
            if names:
                actual[suite] = names
        self.assertEqual(actual, expected_portability_exceptions(self.WORKFLOW_VERSION))

    def test_every_suite_runs_the_frozen_number_of_tests(self):
        counts = {}
        for suite, result in self.results.items():
            self.assertIsNotNone(result.ran, f"{suite} produced no summary")
            counts[suite] = result.ran
        self.assertEqual(counts, dict(CI_SUITES[self.WORKFLOW_VERSION]))

    def test_the_acceptance_matrix_passes_outright(self):
        """The strongest single row: every documented lifecycle behaviour,
        driven through the real `prepare-ai-review.sh`, for a process and a
        product work item, inside a bootstrapped repository."""
        result = self.results["workflow_acceptance_matrix_test.py"]
        self.assertEqual(result.returncode, 0, result.output[-3000:])

    def test_the_real_generation_script_runs_in_the_bootstrapped_repository(self):
        """A smoke test at the shell boundary: the installed script is
        executable, finds its own repository root, and refuses cleanly rather
        than crashing when asked for a stage it cannot serve."""
        proc = subprocess.run(
            ["./scripts/prepare-ai-review.sh"], cwd=str(self.target),
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Usage", proc.stdout + proc.stderr)

    def test_the_installation_verifies_clean_after_the_suite_ran(self):
        """The suites write scratch repositories in `/tmp`, never into the
        repository under test. `drift` is measured after every suite
        invocation (one per suite in direct mode, one per chunk in merged
        mode) and unioned."""
        self.assertEqual(self.matrix_run.drift, [])

    def test_the_suite_left_the_repository_git_clean(self):
        # `git status --porcelain` lines, measured and unioned like `drift`.
        untracked = self.matrix_run.residue
        ignorable = [
            line for line in untracked
            if "__pycache__" not in line and not line.endswith(".pyc")
        ]
        self.assertEqual(ignorable, [])

    def test_the_target_is_still_git_clean_after_this_class_ran(self):
        # The pre-sharding check read the target's live status after every
        # method sorted before it, so it also saw what the generation script
        # run above leaves behind. The suites' residue is measured separately
        # now (above); this keeps the class's own methods covered. Named to
        # sort after both.
        ignorable = [
            line for line in _git(self.target, "status", "--porcelain").splitlines()
            if "__pycache__" not in line and not line.endswith(".pyc")
        ]
        self.assertEqual(ignorable, [])


class TestBootstrappedRepositorySatisfiesTheFrozenSuite231(
    _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions, unittest.TestCase,
):
    """The gate: what the bootstrapper produces behaves like frozen v2.3.1.
    Unchanged by CP6."""

    WORKFLOW_VERSION = "2.3.1"


class TestBootstrappedRepositorySatisfiesTheFrozenSuite240(
    _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions, unittest.TestCase,
):
    """CP6's own explicit obligation: the same bootstrapped-repository gate,
    a second time, against `2.4.0`'s own authored release -- `bootstrap()`
    against an authored (not merely upstream-extracted) manifest is itself
    part of what this proves (D-Authored-Release-5)."""

    WORKFLOW_VERSION = "2.4.0"


class TestBootstrappedRepositorySatisfiesTheFrozenSuite250(
    _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions, unittest.TestCase,
):
    """workflow-2.5.0's own CP11 obligation, mirroring `TestBootstrappedRepository
    SatisfiesTheFrozenSuite240` exactly: the same bootstrapped-repository
    gate, a third time, against `2.5.0`'s own authored release."""

    WORKFLOW_VERSION = "2.5.0"


class TestBootstrappedRepositorySatisfiesTheFrozenSuite251(
    _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions, unittest.TestCase,
):
    """workflow-2.5.1's own CP2 obligation
    (`D-Checkpoint-Id-Anchor-Grammar-Widening`), mirroring `TestBootstrappedRepository
    SatisfiesTheFrozenSuite250` exactly: the same bootstrapped-repository
    gate, a fourth time, against `2.5.1`'s own authored release."""

    WORKFLOW_VERSION = "2.5.1"


class TestBootstrappedRepositorySatisfiesTheFrozenSuite260(
    _BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions, unittest.TestCase,
):
    """workflow-2.6.0's own CP7 obligation
    (workflow-review-artifact-and-concurrency-hardening), mirroring
    `TestBootstrappedRepositorySatisfiesTheFrozenSuite251` exactly: the same
    bootstrapped-repository gate, a fifth time, against `2.6.0`'s own
    authored release."""

    WORKFLOW_VERSION = "2.6.0"


class TestUpdatePreservesLiveWorkItemState(unittest.TestCase):
    """An update must not cost a repository its work."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.release = find_release(REPO_ROOT, "2.3.1")
        cls.target = _empty_repo(Path(cls._tmp.name) / "consumer")
        bootstrap(cls.target, cls.release, now=FIXED_NOW)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.state_path = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"

    def _write_live_state(self) -> str:
        """A work item written through the *installed* module, so the bytes are
        whatever frozen v2.3.1 would really produce."""
        scripts = str(self.target / "scripts")
        script = (
            "import sys, json\n"
            f"sys.path.insert(0, {scripts!r})\n"
            "import workflow_state as ws\n"
            "from pathlib import Path\n"
            f"root = Path({str(self.target)!r})\n"
            "def mutate(state):\n"
            "    state['active_work_item_id'] = 'my-item'\n"
            "    state['work_items']['my-item'] = {\n"
            "        'work_item_type': 'process', 'work_item_kind': 'process',\n"
            "        'work_item_id': 'my-item', 'parent_work_item_id': None,\n"
            "        'plan_path': 'docs/ai-workflow/my-item-plan.md',\n"
            "        'registry_path': None, 'mapping_path': None,\n"
            "        'governing_workflow_version': '2.1', 'phase': 'PLANNING',\n"
            "    }\n"
            "    return state\n"
            "ws.state_transaction(root, mutate)\n"
        )
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest(f"installed workflow_state rejected the fixture: {proc.stderr[-800:]}")
        return self.state_path.read_text()

    def test_live_state_written_by_the_installed_module_survives_an_update(self):
        before = self._write_live_state()
        self.assertIn("my-item", before)
        update(self.target, self.release, now="2027-01-01T00:00:00Z")
        self.assertEqual(self.state_path.read_text(), before)

    def test_the_runtime_workspace_survives_an_update(self):
        runtime = self.target / ".ai-review" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        marker = runtime / "WORKTREE_IDENTITY.json"
        marker.write_text('{"mine": true}\n')
        update(self.target, self.release, now="2027-01-01T00:00:00Z")
        self.assertEqual(marker.read_text(), '{"mine": true}\n')

    def test_an_update_restores_canonical_tooling_bytes(self):
        path = self.target / "scripts/workflow_fingerprint.py"
        path.write_text("# damaged\n")
        updated, changes = update(self.target, self.release, force=True,
                                  now="2027-01-01T00:00:00Z")
        artifact = next(a for a in self.release.payload_artifacts(updated.profile)
                        if a.target_path == "scripts/workflow_fingerprint.py")
        self.assertEqual(sha256(path.read_bytes()), artifact.sha256)
        self.assertIn("updated scripts/workflow_fingerprint.py", changes)

    def test_the_repository_verifies_clean_afterwards(self):
        self.assertEqual(verify(self.target, self.release), [])
        record = Installation.read(self.target)
        self.assertEqual(record.installed_at, FIXED_NOW)
        self.assertEqual(record.workflow_version, self.release.version)

    def test_state_still_parses_after_everything(self):
        json.loads(self.state_path.read_text())


class TestCliDrivesTheSameOperations(unittest.TestCase):
    """The documented entry point works, not just the library behind it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = _empty_repo(Path(self._tmp.name) / "cli-target")

    def _cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "workflow_manager", *args],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin",
                 "HOME": str(Path.home())},
        )

    def test_status_bootstrap_verify_uninstall_round_trip(self):
        before = self._cli("status", str(self.target))
        self.assertIn("not a managed repository", before.stdout)

        # `find_release`'s own documented contract: an unpinned `bootstrap`
        # means "the current release" -- the newest one present, not a
        # literal pinned to whatever was newest when this test was written
        # (CP6, D-Authored-Release-4: adding `distribution/workflow/2.4.0/`
        # is exactly the kind of "just add a directory" change this
        # defaulting exists to absorb without a test edit here -- so this
        # asserts against the same live default the CLI itself resolves,
        # not a second, drifting copy of it).
        default_version = find_release(REPO_ROOT).version
        created = self._cli("bootstrap", str(self.target))
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn(f"bootstrapped workflow {default_version}", created.stdout)

        checked = self._cli("verify", str(self.target))
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

        again = self._cli("bootstrap", str(self.target))
        self.assertEqual(again.returncode, 2)
        self.assertIn("already managed", again.stderr)

        removed = self._cli("uninstall", str(self.target))
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse((self.target / "scripts/workflow_state.py").exists())

    def test_verify_reports_a_nonzero_exit_on_drift(self):
        self._cli("bootstrap", str(self.target))
        path = self.target / "scripts/workflow_state.py"
        path.write_text("# edited\n")
        checked = self._cli("verify", str(self.target))
        self.assertEqual(checked.returncode, 1)
        self.assertIn("modified: scripts/workflow_state.py", checked.stdout)

    def test_update_refuses_drift_and_says_how_to_proceed(self):
        self._cli("bootstrap", str(self.target))
        path = self.target / "scripts/workflow_state.py"
        path.write_text("# edited\n")
        blocked = self._cli("update", str(self.target))
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("--force", blocked.stderr)
        forced = self._cli("update", str(self.target), "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
