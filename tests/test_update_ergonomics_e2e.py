#!/usr/bin/env python3
"""End-to-end evidence for `doctor` and `update --dry-run` on disposable repositories.

Each scenario is a real repository a consumer could have: a Workflow release
bootstrapped and committed, then a work item driven by the installed
`workflow_state` (`fixture.drive_synthetic_work_item_through_checkpoints`) or
a legacy state file. The commands run through `python -m workflow_manager`
and every one is checked against the byte-for-byte contents of the work tree
and `.git/`: the report is advisory and must leave the repository as it was,
and the undo command it prints must undo a real update.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support
from support import NEWEST_RELEASE, REPO_ROOT, cli_env

from frozen_runs import build_bootstrapped_repo
from workflow_manager.fixture import drive_synthetic_work_item_through_checkpoints

OLDEST = "2.3.1"
STATE = "docs/ai-workflow/WORKFLOW_STATE.json"
LEGACY_STATE = {"schema_version": 1, "active_work_item_id": None, "work_items": {
    "old-item": {"work_item_type": "product", "phase": "LEGACY_READY",
                 "governing_workflow_version": "1", "parent_work_item_id": None}}}


def run(*args):
    return subprocess.run([sys.executable, "-m", "workflow_manager", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=cli_env())


def git(repo: Path, *args: str):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True)


def snapshot(root: Path) -> dict:
    """Path -> (kind, mode, bytes or link text) for everything under `root`,
    `.git` included."""
    found = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            found[rel] = ("link", 0, os.readlink(path).encode())
        elif path.is_file():
            found[rel] = ("file", path.stat().st_mode & 0o7777, path.read_bytes())
        else:
            found[rel] = ("dir", path.stat().st_mode & 0o7777, b"")
    return found


def commit_all(repo: Path, message: str):
    git(repo, "add", "-A")
    if git(repo, "status", "--porcelain").stdout:
        git(repo, "commit", "-q", "-m", message)


def finding_ids(report: str) -> set[str]:
    return {line.split("]", 1)[1].split(":", 1)[0].strip()
            for line in report.splitlines() if line.startswith("  [")}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pristine = build_bootstrapped_repo(support.release(OLDEST),
                                               Path(cls._tmp.name) / "pristine")
        cls.with_item = Path(cls._tmp.name) / "with-item"
        shutil.copytree(cls.pristine, cls.with_item, symlinks=True)
        drive_synthetic_work_item_through_checkpoints(
            cls.with_item, work_item_id="proc-item", work_item_type="process",
            checkpoint_ids=("CP1", "CP2", "CP3"), complete_checkpoint_ids=("CP1",))
        commit_all(cls.with_item, "drive proc-item to IMPLEMENTING")
        cls.legacy = Path(cls._tmp.name) / "legacy"
        shutil.copytree(cls.pristine, cls.legacy, symlinks=True)
        (cls.legacy / STATE).write_text(json.dumps(LEGACY_STATE))
        commit_all(cls.legacy, "legacy item")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def copy_of(self, source: Path) -> Path:
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        repo = Path(work.name) / "repo"
        shutil.copytree(source, repo, symlinks=True)
        return repo

    def assertReadOnly(self, repo: Path, *argv: str):
        """Run `argv` against `repo` and prove it left every byte alone."""
        before = snapshot(repo)
        proc = run(*argv, str(repo))
        self.assertEqual(snapshot(repo), before)
        return proc


class TestProcessItemAtImplementing(Base):
    """The scenario `v2.4.0-001` exists for: an update would rewrite paths a
    `process` item in `IMPLEMENTING` protects."""

    def test_doctor_names_the_hazard_and_changes_nothing(self):
        repo = self.copy_of(self.with_item)
        proc = self.assertReadOnly(repo, "doctor")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("v2.4.0-001", finding_ids(proc.stdout))
        self.assertIn("proc-item (IMPLEMENTING)", proc.stdout)
        self.assertIn("gates-change", finding_ids(proc.stdout))
        self.assertRegex(proc.stdout, r"(?m)^  proc-item  IMPLEMENTING  process   2\.1")

    def test_the_dry_run_reports_the_hazard_and_matches_the_real_update(self):
        dry_repo, real_repo = self.copy_of(self.with_item), self.copy_of(self.with_item)
        before = snapshot(dry_repo)
        dry = run("update", str(dry_repo), "--dry-run")
        self.assertEqual(snapshot(dry_repo), before)
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("v2.4.0-001", finding_ids(dry.stdout))
        real = run("update", str(real_repo))
        self.assertEqual(real.returncode, 0, real.stderr)
        lines = dry.stdout.splitlines()
        would = lines[1:lines.index("left alone:")]
        done = [line for line in real.stdout.splitlines()[1:] if line.startswith("  ")]
        self.assertEqual(len(would), len(done))

    def test_the_item_survives_the_update_the_report_warned_about(self):
        repo = self.copy_of(self.with_item)
        before = json.loads((repo / STATE).read_text())["work_items"]["proc-item"]
        self.assertEqual(run("update", str(repo)).returncode, 0)
        after = json.loads((repo / STATE).read_text())["work_items"]["proc-item"]
        self.assertEqual(after, before)

    def test_the_printed_undo_restores_the_committed_tree(self):
        repo = self.copy_of(self.with_item)
        doctor = run("doctor", str(repo)).stdout
        restore = next(line.split() for line in doctor.splitlines()
                       if "restore --source=HEAD" in line)
        committed = git(repo, "rev-parse", "HEAD:").stdout
        self.assertEqual(run("update", str(repo)).returncode, 0)
        subprocess.run(restore, check=True, capture_output=True)
        self.assertEqual(git(repo, "diff", "HEAD", "--stat").stdout, "")
        self.assertEqual(git(repo, "rev-parse", "HEAD:").stdout, committed)
        self.assertTrue(all(line.startswith("??")
                            for line in git(repo, "status", "--porcelain").stdout.splitlines()))


class TestLegacyItem(Base):
    def test_a_dormant_legacy_item_is_offered_retirement(self):
        repo = self.copy_of(self.legacy)
        proc = self.assertReadOnly(repo, "doctor")
        self.assertIn("/retire-legacy-work-item old-item", proc.stdout)

    def test_the_dry_run_of_a_legacy_repository_writes_nothing(self):
        repo = self.copy_of(self.legacy)
        before = snapshot(repo)
        proc = run("update", str(repo), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(snapshot(repo), before)


class TestDowngrade(Base):
    def updated(self) -> Path:
        repo = self.copy_of(self.with_item)
        self.assertEqual(run("update", str(repo)).returncode, 0)
        commit_all(repo, "update")
        return repo

    def test_a_downgrade_is_reported_unsupported_and_still_not_refused(self):
        repo = self.updated()
        before = snapshot(repo)
        doctor = run("--release-version", OLDEST, "doctor", str(repo))
        dry = run("--release-version", OLDEST, "update", str(repo), "--dry-run")
        self.assertEqual(snapshot(repo), before)
        self.assertEqual(doctor.returncode, 1, doctor.stdout + doctor.stderr)
        self.assertIn("downgrade", finding_ids(doctor.stdout))
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("downgrade", finding_ids(dry.stdout))

    def test_each_pinned_older_target_reports_and_changes_nothing(self):
        repo = self.updated()
        before = snapshot(repo)
        for version in support.PINNED_VERSIONS[:-1]:
            with self.subTest(target=version):
                proc = run("--release-version", version, "doctor", str(repo))
                self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
                self.assertIn("downgrade", finding_ids(proc.stdout))
        self.assertEqual(snapshot(repo), before)

    def test_the_same_release_is_not_a_downgrade(self):
        repo = self.updated()
        proc = run("--release-version", NEWEST_RELEASE, "doctor", str(repo))
        self.assertNotIn("downgrade", finding_ids(proc.stdout))


if __name__ == "__main__":
    unittest.main()
