#!/usr/bin/env python3
"""Bootstrapper unit behaviour, against disposable repositories only.

Nothing here touches a real consumer. Every test builds an empty Git
repository in a temporary directory, installs into it, and inspects the
result.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

from workflow_manager.install import (
    AlreadyManagedError,
    DriftError,
    NotManagedError,
    bootstrap,
    drift,
    merge_claude_md,
    merge_gitignore,
    status,
    uninstall,
    update,
    verify,
)
from workflow_manager.installation import Installation, is_managed
from workflow_manager.release import Release, find_release, sha256

FIXED_NOW = "2026-01-01T00:00:00Z"


def empty_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "T"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


class BootstrapCase(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = empty_repo(Path(self._tmp.name) / "target")


class TestRecognition(BootstrapCase):
    def test_a_fresh_repository_is_not_managed(self):
        self.assertFalse(is_managed(self.target))
        self.assertFalse(status(self.target).managed)

    def test_bootstrap_makes_it_recognizable(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertTrue(is_managed(self.target))
        result = status(self.target, self.release)
        self.assertTrue(result.managed)
        self.assertEqual(result.workflow_version, "2.3.1")

    def test_bootstrapping_twice_is_refused(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        with self.assertRaises(AlreadyManagedError):
            bootstrap(self.target, self.release, now=FIXED_NOW)

    def test_updating_an_unmanaged_repository_is_refused(self):
        with self.assertRaises(NotManagedError):
            update(self.target, self.release, now=FIXED_NOW)

    def test_bootstrap_requires_a_git_repository(self):
        plain = Path(self._tmp.name) / "plain"
        plain.mkdir()
        with self.assertRaises(Exception):
            bootstrap(plain, self.release, now=FIXED_NOW)


class TestInstalledLayout(BootstrapCase):
    def setUp(self):
        super().setUp()
        self.installation = bootstrap(self.target, self.release, now=FIXED_NOW)

    def test_every_payload_file_landed_at_its_target_path(self):
        for artifact in self.release.payload_artifacts("full"):
            path = self.target / artifact.target_path
            self.assertTrue(path.exists(), artifact.target_path)
            self.assertEqual(sha256(path.read_bytes()), artifact.sha256, artifact.target_path)

    def test_the_generation_script_is_executable(self):
        path = self.target / "scripts/prepare-ai-review.sh"
        self.assertTrue(path.stat().st_mode & 0o111)

    def test_the_layout_dependent_verifiers_kept_their_depth(self):
        """Frozen v2.3.1 resolves the repository root from these files as
        `parents[3]`. Installing them anywhere else breaks the suite."""
        for name in ("verify_372h_lock_primitive_predicate.py",
                     "verify_372h_raw_edge_derivation.py"):
            path = self.target / "docs/ai-workflow/dry-run" / name
            self.assertTrue(path.exists(), name)
            self.assertEqual(path.resolve().parents[3], self.target.resolve(), name)

    def test_the_two_modules_are_siblings(self):
        """`workflow_state` imports `workflow_fingerprint` by bare name."""
        scripts = self.target / "scripts"
        self.assertTrue((scripts / "workflow_state.py").exists())
        self.assertTrue((scripts / "workflow_fingerprint.py").exists())

    def test_no_host_evidence_fixture_was_installed(self):
        text = (self.target / "docs/ACTIVE_MILESTONE.md").read_text()
        self.assertNotIn("RepFlow", text)
        self.assertNotIn("Status note (2026-08-04)", text)

    def test_state_starts_empty(self):
        state = json.loads((self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())
        self.assertEqual(state["work_items"], {})
        self.assertIsNone(state["active_work_item_id"])

    def test_the_runtime_workspace_is_ignored(self):
        self.assertIn(".ai-review/", (self.target / ".gitignore").read_text().splitlines())

    def test_the_record_lists_everything_it_wrote(self):
        installed = {a.target_path for a in self.release.payload_artifacts("full")}
        self.assertEqual(set(self.installation.managed), installed)
        self.assertEqual(
            set(self.installation.generated),
            {"docs/ai-workflow/WORKFLOW_STATE.json",
             "docs/ai-workflow/WORKFLOW_CONFIG.json",
             "docs/ACTIVE_MILESTONE.md",
             ".github/workflows/workflow-conformance.yml"},
        )
        self.assertEqual(set(self.installation.merged), {".gitignore", "CLAUDE.md"})

    def test_a_fresh_installation_has_no_drift(self):
        self.assertEqual(drift(self.target, self.release), [])
        self.assertEqual(verify(self.target, self.release), [])

    def test_the_runtime_profile_installs_strictly_fewer_files(self):
        other = empty_repo(Path(self._tmp.name) / "runtime-target")
        runtime = bootstrap(other, self.release, profile="runtime", now=FIXED_NOW)
        self.assertLess(len(runtime.managed), len(self.installation.managed))
        self.assertTrue(set(runtime.managed) < set(self.installation.managed))


class TestBootstrapIsDeterministic(BootstrapCase):
    def test_two_bootstraps_produce_identical_trees_and_records(self):
        a = empty_repo(Path(self._tmp.name) / "a")
        b = empty_repo(Path(self._tmp.name) / "b")
        first = bootstrap(a, self.release, now=FIXED_NOW)
        second = bootstrap(b, self.release, now=FIXED_NOW)
        self.assertEqual(first.serialize(), second.serialize())

        def tree(root):
            return {
                p.relative_to(root).as_posix(): sha256(p.read_bytes())
                for p in sorted(root.rglob("*"))
                if p.is_file() and ".git/" not in p.relative_to(root).as_posix()
            }

        self.assertEqual(tree(a), tree(b))


class TestPreExistingRepositoryContentIsRespected(BootstrapCase):
    def test_an_existing_gitignore_is_appended_to_not_replaced(self):
        (self.target / ".gitignore").write_text("build/\n*.log\n")
        bootstrap(self.target, self.release, now=FIXED_NOW)
        lines = (self.target / ".gitignore").read_text().splitlines()
        self.assertIn("build/", lines)
        self.assertIn("*.log", lines)
        self.assertIn(".ai-review/", lines)

    def test_merging_gitignore_twice_adds_nothing(self):
        fragment = self.release.read("templates/.gitignore.workflow-fragment")
        (self.target / ".gitignore").write_bytes(fragment)
        merged, action = merge_gitignore(self.target, fragment)
        self.assertEqual(action, "unchanged")

    def test_an_existing_claude_md_is_preserved_below_the_managed_section(self):
        (self.target / "CLAUDE.md").write_text("# My repo\n\nHouse rules.\n")
        bootstrap(self.target, self.release, now=FIXED_NOW)
        text = (self.target / "CLAUDE.md").read_text()
        self.assertIn("House rules.", text)
        self.assertIn("Hard gates summary", text)
        self.assertLess(text.index("Hard gates summary"), text.index("House rules."))

    def test_a_second_merge_replaces_only_the_managed_section(self):
        managed = self.release.read("templates/CLAUDE.md")
        (self.target / "CLAUDE.md").write_bytes(managed + b"\n# Mine\n\nKeep me.\n")
        merged, action = merge_claude_md(self.target, managed)
        self.assertEqual(action, "replaced")
        self.assertIn("Keep me.", merged.decode())
        self.assertEqual(merged.decode().count("Hard gates summary"), 1)

    def test_an_existing_state_file_is_never_clobbered(self):
        path = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"schema_version": 1, "active_work_item_id": null,'
                        ' "work_items": {"mine": {}}}\n')
        before = path.read_bytes()
        installation = bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(
            installation.generated["docs/ai-workflow/WORKFLOW_STATE.json"]["source"],
            "pre-existing",
        )


class TestDriftDetection(BootstrapCase):
    def setUp(self):
        super().setUp()
        bootstrap(self.target, self.release, now=FIXED_NOW)

    def test_an_edited_managed_file_is_reported_as_modified(self):
        path = self.target / "scripts/workflow_state.py"
        path.write_text(path.read_text() + "\n# local edit\n")
        found = drift(self.target, self.release)
        self.assertEqual([(d.path, d.kind) for d in found],
                         [("scripts/workflow_state.py", "modified")])

    def test_a_deleted_managed_file_is_reported_as_missing(self):
        (self.target / ".claude/commands/approve-review.md").unlink()
        found = drift(self.target, self.release)
        self.assertIn((".claude/commands/approve-review.md", "missing"),
                      [(d.path, d.kind) for d in found])

    def test_a_lost_executable_bit_is_reported(self):
        path = self.target / "scripts/prepare-ai-review.sh"
        path.chmod(0o644)
        found = drift(self.target, self.release)
        self.assertIn(("scripts/prepare-ai-review.sh", "not-executable"),
                      [(d.path, d.kind) for d in found])

    def test_a_deleted_state_file_is_reported_but_not_as_modified(self):
        (self.target / "docs/ACTIVE_MILESTONE.md").unlink()
        found = drift(self.target, self.release)
        self.assertEqual([(d.path, d.kind) for d in found],
                         [("docs/ACTIVE_MILESTONE.md", "missing")])

    def test_editing_repository_local_state_is_not_drift(self):
        """A repository is supposed to write its own state. Doing so must not
        make its installation look damaged."""
        path = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        path.write_text('{"schema_version": 1, "active_work_item_id": "wi",'
                        ' "work_items": {"wi": {}}}\n')
        (self.target / "docs/ACTIVE_MILESTONE.md").write_text("# whatever\n")
        self.assertEqual(drift(self.target, self.release), [])

    def test_verify_reports_a_version_mismatch(self):
        record = Installation.read(self.target)
        record.workflow_version = "9.9.9"
        record.write(self.target)
        problems = verify(self.target, self.release)
        self.assertTrue(any("version:" in p for p in problems), problems)


class TestUpdate(BootstrapCase):
    def setUp(self):
        super().setUp()
        self.installation = bootstrap(self.target, self.release, now=FIXED_NOW)

    def test_updating_to_the_same_release_is_a_no_op(self):
        _, changes = update(self.target, self.release, now=FIXED_NOW)
        self.assertEqual(changes, [])
        self.assertEqual(drift(self.target, self.release), [])

    def test_update_refuses_to_discard_a_local_edit(self):
        path = self.target / "scripts/workflow_state.py"
        path.write_text(path.read_text() + "\n# local edit\n")
        with self.assertRaises(DriftError) as caught:
            update(self.target, self.release, now=FIXED_NOW)
        self.assertEqual([d.path for d in caught.exception.drifted],
                         ["scripts/workflow_state.py"])

    def test_forced_update_restores_the_canonical_bytes(self):
        path = self.target / "scripts/workflow_state.py"
        path.write_text("# clobbered\n")
        update(self.target, self.release, force=True, now=FIXED_NOW)
        artifact = next(a for a in self.release.payload_artifacts("full")
                        if a.target_path == "scripts/workflow_state.py")
        self.assertEqual(sha256(path.read_bytes()), artifact.sha256)

    def test_update_never_rewrites_repository_local_state(self):
        state = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        mine = ('{\n  "schema_version": 1,\n  "active_work_item_id": "mine",\n'
                '  "work_items": {\n    "mine": {}\n  }\n}\n')
        state.write_text(mine)
        checklist = self.target / "docs/ACTIVE_MILESTONE.md"
        checklist.write_text("# my milestone\n")
        update(self.target, self.release, now=FIXED_NOW)
        self.assertEqual(state.read_text(), mine)
        self.assertEqual(checklist.read_text(), "# my milestone\n")

    def test_update_recreates_a_state_file_that_was_deleted(self):
        (self.target / "docs/ACTIVE_MILESTONE.md").unlink()
        _, changes = update(self.target, self.release, now=FIXED_NOW)
        self.assertTrue((self.target / "docs/ACTIVE_MILESTONE.md").exists())
        self.assertIn("created missing state docs/ACTIVE_MILESTONE.md", changes)

    def test_narrowing_the_profile_removes_the_files_it_drops(self):
        full_only = (set(a.target_path for a in self.release.payload_artifacts("full"))
                     - set(a.target_path for a in self.release.payload_artifacts("runtime")))
        self.assertTrue(full_only)
        updated, changes = update(self.target, self.release, profile="runtime", now=FIXED_NOW)
        for rel in full_only:
            self.assertFalse((self.target / rel).exists(), rel)
            self.assertNotIn(rel, updated.managed)
        self.assertTrue(any(c.startswith("removed ") for c in changes))
        self.assertEqual(drift(self.target, self.release), [])

    def test_widening_the_profile_restores_them(self):
        update(self.target, self.release, profile="runtime", now=FIXED_NOW)
        updated, _ = update(self.target, self.release, profile="full", now=FIXED_NOW)
        for artifact in self.release.payload_artifacts("full"):
            self.assertTrue((self.target / artifact.target_path).exists(),
                            artifact.target_path)
        self.assertEqual(drift(self.target, self.release), [])

    def test_update_preserves_the_original_install_timestamp(self):
        updated, _ = update(self.target, self.release, now="2027-02-02T00:00:00Z")
        self.assertEqual(updated.installed_at, FIXED_NOW)
        self.assertEqual(updated.updated_at, "2027-02-02T00:00:00Z")

    def test_update_does_not_duplicate_the_claude_section(self):
        (self.target / "CLAUDE.md").write_text(
            (self.target / "CLAUDE.md").read_text() + "\n# Mine\n")
        update(self.target, self.release, now=FIXED_NOW)
        update(self.target, self.release, now=FIXED_NOW)
        text = (self.target / "CLAUDE.md").read_text()
        self.assertEqual(text.count("Hard gates summary"), 1)
        self.assertEqual(text.count("# Mine"), 1)


class TestUninstall(BootstrapCase):
    def test_uninstall_removes_tooling_and_keeps_state(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        state = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        state.write_text('{"schema_version": 1, "active_work_item_id": null,'
                         ' "work_items": {"kept": {}}}\n')
        uninstall(self.target)
        self.assertFalse(is_managed(self.target))
        self.assertFalse((self.target / "scripts/workflow_state.py").exists())
        self.assertIn("kept", state.read_text())

    def test_uninstall_leaves_no_empty_directories_behind(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        uninstall(self.target)
        self.assertFalse((self.target / ".claude" / "commands").exists())
        self.assertFalse((self.target / "scripts").exists())


class TestInstallationRecord(unittest.TestCase):
    def test_an_unknown_schema_version_is_refused(self):
        with self.assertRaises(ValueError):
            Installation.from_dict({"schema_version": 99, "workflow_version": "2.3.1",
                                    "profile": "full", "upstream": {}})

    def test_round_trip_is_lossless(self):
        original = Installation(
            workflow_version="2.3.1", profile="full", upstream={"tag": "t"},
            managed={"a": {"sha256": "x", "executable": False}},
            generated={"b": {"sha256": "y", "source": "template"}},
            merged={".gitignore": {"action": "created"}},
            installed_at=FIXED_NOW, updated_at=FIXED_NOW,
        )
        again = Installation.from_dict(json.loads(original.serialize()))
        self.assertEqual(again.serialize(), original.serialize())

def synthesize_next_release(source: Release, dest: Path, version: str) -> Release:
    """A second release, built from the real one by hand.

    Only one release exists so far, so the release-to-release update path would
    otherwise be untested. This fabricates a plausible next one: a payload file
    whose content changed, a payload file that was dropped, a payload file that
    is new, and a template whose default changed.
    """
    import json

    dest.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(source.manifest))
    manifest["workflow_version"] = version

    dropped = ".claude/commands/prepare-review.md"
    changed = "docs/ai-workflow/REVIEW_PROTOCOL.md"

    artifacts = []
    for record in manifest["artifacts"]:
        if record["target_path"] == dropped:
            continue
        data = source.read(record["location"])
        if record["target_path"] == changed:
            data = data + b"\n<!-- v2.3.2 note -->\n"
            record["sha256"] = sha256(data)
            record["size"] = len(data)
        out = dest / record["location"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        out.chmod(0o755 if record["executable"] else 0o644)
        artifacts.append(record)

    added_data = b"# added in 2.3.2\n"
    added = {
        "upstream_path": "docs/ai-workflow/WHATS_NEW.md",
        "target_path": "docs/ai-workflow/WHATS_NEW.md",
        "location": "payload/docs/ai-workflow/WHATS_NEW.md",
        "category": "distribution",
        "rule": "synthetic",
        "rationale": "synthetic fixture",
        "sha256": sha256(added_data),
        "size": len(added_data),
        "executable": False,
    }
    (dest / added["location"]).write_bytes(added_data)
    artifacts.append(added)
    manifest["artifacts"] = artifacts

    for record in manifest["templates"]:
        data = source.read(record["location"])
        if record["target_path"] == "docs/ACTIVE_MILESTONE.md":
            data = b"# Active Milestone\n\nNone. (2.3.2 wording.)\n"
            record["sha256"] = sha256(data)
            record["size"] = len(data)
        out = dest / record["location"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return Release(dest)


class TestReleaseToReleaseUpdate(BootstrapCase):
    """The path that matters most: moving between two Workflow releases."""

    DROPPED = ".claude/commands/prepare-review.md"
    CHANGED = "docs/ai-workflow/REVIEW_PROTOCOL.md"
    ADDED = "docs/ai-workflow/WHATS_NEW.md"

    def setUp(self):
        super().setUp()
        bootstrap(self.target, self.release, now=FIXED_NOW)
        self.next_release = synthesize_next_release(
            self.release, Path(self._tmp.name) / "release-2.3.2", "2.3.2",
        )
        # Repository-local work this update must not cost anyone.
        self.state = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        self.live_state = ('{\n  "schema_version": 1,\n'
                           '  "active_work_item_id": "live-item",\n'
                           '  "work_items": {\n    "live-item": {"phase": "IMPLEMENTING"}\n  }\n}\n')
        self.state.write_text(self.live_state)
        self.checklist = self.target / "docs/ACTIVE_MILESTONE.md"
        self.checklist.write_text("# my milestone\n\nMy checklist.\n")
        runtime = self.target / ".ai-review" / "runtime"
        runtime.mkdir(parents=True)
        (runtime / "WORKTREE_IDENTITY.json").write_text('{"live": true}\n')

    def test_the_update_moves_the_recorded_version(self):
        updated, _ = update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertEqual(updated.workflow_version, "2.3.2")
        self.assertEqual(Installation.read(self.target).workflow_version, "2.3.2")

    def test_added_changed_and_dropped_files_are_all_handled(self):
        _, changes = update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertIn(f"removed {self.DROPPED}", changes)
        self.assertIn(f"updated {self.CHANGED}", changes)
        self.assertIn(f"added {self.ADDED}", changes)
        self.assertFalse((self.target / self.DROPPED).exists())
        self.assertTrue((self.target / self.ADDED).exists())
        self.assertIn("v2.3.2 note", (self.target / self.CHANGED).read_text())

    def test_repository_local_state_is_untouched(self):
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertEqual(self.state.read_text(), self.live_state)
        self.assertEqual(self.checklist.read_text(), "# my milestone\n\nMy checklist.\n")
        self.assertEqual(
            (self.target / ".ai-review/runtime/WORKTREE_IDENTITY.json").read_text(),
            '{"live": true}\n',
        )

    def test_a_changed_template_does_not_rewrite_existing_state(self):
        """2.3.2 ships a different `ACTIVE_MILESTONE.md` default. A repository
        that already has one keeps its own."""
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertNotIn("2.3.2 wording", self.checklist.read_text())

    def test_the_updated_repository_verifies_against_the_new_release(self):
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertEqual(drift(self.target, self.next_release), [])
        self.assertEqual(verify(self.target, self.next_release), [])

    def test_it_no_longer_verifies_against_the_old_release(self):
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        problems = verify(self.target, self.release)
        self.assertTrue(any("version:" in p for p in problems), problems)

    def test_a_local_edit_still_blocks_the_upgrade(self):
        path = self.target / self.CHANGED
        path.write_text(path.read_text() + "\nlocal note\n")
        with self.assertRaises(DriftError):
            update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertIn("local note", path.read_text())

    def test_downgrading_back_restores_the_dropped_file(self):
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        update(self.target, self.release, now="2027-01-02T00:00:00Z")
        self.assertTrue((self.target / self.DROPPED).exists())
        self.assertFalse((self.target / self.ADDED).exists())
        self.assertEqual(drift(self.target, self.release), [])
        self.assertEqual(self.state.read_text(), self.live_state)

if __name__ == "__main__":
    unittest.main(verbosity=1)
