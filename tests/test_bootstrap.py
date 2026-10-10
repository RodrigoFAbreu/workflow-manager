#!/usr/bin/env python3
"""Bootstrapper unit behaviour, against disposable repositories only.

Nothing here touches a real consumer. Every test builds an empty Git
repository in a temporary directory, installs into it, and inspects the
result.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from support import NEWEST_RELEASE, REPO_ROOT, cli_env

import workflow_manager.cli as cli_module
import workflow_manager.install as install_module
import workflow_manager.package as package_module
from workflow_manager import source as release_source
from workflow_manager.fixture import init_git_repo
from workflow_manager.install import (
    AlreadyManagedError,
    CollisionError,
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
from workflow_manager.installation import (
    CorruptInstallationError,
    Installation,
    installation_path,
    is_managed,
)
from workflow_manager.release import (
    RELEASE_TEMPLATES,
    Release,
    ReleaseIntegrityError,
    sha256,
)

FIXED_NOW = "2026-01-01T00:00:00Z"
#: A synthetic release above every pinned one (plan 7.2), so the "next"
#: release is never lower than the installed one.
NEXT_RELEASE = support.next_version(NEWEST_RELEASE)


def empty_repo(root: Path) -> Path:
    init_git_repo(root)
    return root


class BootstrapCase(unittest.TestCase):
    def setUp(self):
        self.release = support.release(NEWEST_RELEASE)
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
        self.assertEqual(result.workflow_version, NEWEST_RELEASE)

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
        """The frozen releases resolve the repository root from these files as
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
        installed = {a.target_path for a in self.release.installable("full")}
        self.assertEqual(set(self.installation.managed), installed)
        self.assertEqual(
            set(self.installation.generated),
            {"docs/ai-workflow/WORKFLOW_STATE.json",
             "docs/ai-workflow/WORKFLOW_CONFIG.json",
             "docs/ACTIVE_MILESTONE.md"},
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

    def test_losing_the_workflow_ignore_entries_is_reported(self):
        """Without them a repository starts tracking `.ai-review/` -- the
        Workflow's live runtime workspace -- and nothing would have said so."""
        (self.target / ".gitignore").write_text("build/\n")
        found = drift(self.target, self.release)
        self.assertEqual([(d.path, d.kind) for d in found], [(".gitignore", "modified")])
        self.assertIn(".ai-review/", found[0].detail)

    def test_keeping_them_among_the_repositorys_own_entries_is_not_drift(self):
        path = self.target / ".gitignore"
        path.write_text("build/\n" + path.read_text() + "\n*.log\n")
        self.assertEqual(drift(self.target, self.release), [])

    def test_deleting_the_managed_claude_section_is_reported(self):
        (self.target / "CLAUDE.md").write_text("# just my rules\n")
        self.assertIn(("CLAUDE.md", "modified"),
                      [(d.path, d.kind) for d in drift(self.target, self.release)])

    def test_removing_claude_md_entirely_is_reported(self):
        (self.target / "CLAUDE.md").unlink()
        self.assertIn(("CLAUDE.md", "missing"),
                      [(d.path, d.kind) for d in drift(self.target, self.release)])

    def test_the_repositorys_own_guidance_below_the_marker_is_not_drift(self):
        path = self.target / "CLAUDE.md"
        path.write_text(path.read_text() + "\n# House rules\n\nMine.\n")
        self.assertEqual(drift(self.target, self.release), [])

    def test_a_repository_that_brought_its_own_claude_md_has_no_drift(self):
        """The managed section is prepended above the repository's file rather
        than replacing it, and that shape must read as clean."""
        other = empty_repo(Path(self._tmp.name) / "own-claude")
        (other / "CLAUDE.md").write_text("# Their repo\n\nTheir rules.\n")
        bootstrap(other, self.release, now=FIXED_NOW)
        self.assertEqual(drift(other, self.release), [])
        self.assertIn("Their rules.", (other / "CLAUDE.md").read_text())

    def test_an_update_repairs_both_merged_files(self):
        (self.target / ".gitignore").write_text("build/\n")
        (self.target / "CLAUDE.md").write_text("# just my rules\n")
        update(self.target, self.release, now=FIXED_NOW)
        self.assertEqual(drift(self.target, self.release), [])
        self.assertIn("just my rules", (self.target / "CLAUDE.md").read_text())

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

    def test_uninstall_removes_only_files_it_installed(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        path = self.target / ".claude/commands/approve-review.md"
        path.unlink()
        path.mkdir()
        (path / "mine.txt").write_text("mine\n")
        removed = uninstall(self.target)
        self.assertNotIn(".claude/commands/approve-review.md", removed)
        self.assertTrue((path / "mine.txt").exists())

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

    def test_a_pre_provenance_record_still_loads_and_defaults_to_upstream(self):
        """D-Authored-Release-2's `Installation` schema posture: `provenance`
        is additive, `SCHEMA_VERSION` is not bumped for it, and a `2.3.1`-era
        record written before this field existed -- no `provenance` key at
        all -- must still load, reporting the only origin that could have
        produced it (section 4 scenario 16)."""
        pre_provenance_record = {
            "schema_version": 1, "workflow_version": "2.3.1", "profile": "full",
            "upstream": {"tag": "t"}, "installed_at": FIXED_NOW, "updated_at": FIXED_NOW,
            "managed": {}, "generated": {}, "merged": {},
        }
        loaded = Installation.from_dict(pre_provenance_record)
        self.assertEqual(loaded.provenance, {"origin": "upstream"})
        self.assertEqual(loaded.to_dict()["provenance"], {"origin": "upstream"})

def synthesize_next_release(source: Release, dest: Path, version: str,
                            change_ci: bool = False) -> Release:
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
            data = data + f"\n<!-- v{version} note -->\n".encode()
            record["sha256"] = sha256(data)
            record["size"] = len(data)
        out = dest / record["location"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        out.chmod(0o755 if record["executable"] else 0o644)
        artifacts.append(record)

    added_data = f"# added in {version}\n".encode()
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
            data = f"# Active Milestone\n\nNone. ({version} wording.)\n".encode()
            record["sha256"] = sha256(data)
            record["size"] = len(data)
        elif change_ci and record["target_path"] in RELEASE_TEMPLATES:
            data = data + f"\n# runs the {version} suites\n".encode()
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
            self.release, Path(self._tmp.name) / f"release-{NEXT_RELEASE}", NEXT_RELEASE,
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
        self.assertEqual(updated.workflow_version, NEXT_RELEASE)
        self.assertEqual(Installation.read(self.target).workflow_version, NEXT_RELEASE)

    def test_added_changed_and_dropped_files_are_all_handled(self):
        _, changes = update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertIn(f"removed {self.DROPPED}", changes)
        self.assertIn(f"updated {self.CHANGED}", changes)
        self.assertIn(f"added {self.ADDED}", changes)
        self.assertFalse((self.target / self.DROPPED).exists())
        self.assertTrue((self.target / self.ADDED).exists())
        self.assertIn(f"v{NEXT_RELEASE} note", (self.target / self.CHANGED).read_text())

    def test_repository_local_state_is_untouched(self):
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertEqual(self.state.read_text(), self.live_state)
        self.assertEqual(self.checklist.read_text(), "# my milestone\n\nMy checklist.\n")
        self.assertEqual(
            (self.target / ".ai-review/runtime/WORKTREE_IDENTITY.json").read_text(),
            '{"live": true}\n',
        )

    def test_a_changed_template_does_not_rewrite_existing_state(self):
        """The next release ships a different `ACTIVE_MILESTONE.md` default. A repository
        that already has one keeps its own."""
        update(self.target, self.next_release, now="2027-01-01T00:00:00Z")
        self.assertNotIn(f"{NEXT_RELEASE} wording", self.checklist.read_text())

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



# ---------------------------------------------------------------------------
# Regressions
# ---------------------------------------------------------------------------


def damaged_copy(release: Release, dest: Path, location: str) -> Release:
    """A release whose bytes on disk no longer match its own manifest."""
    shutil.copytree(release.root, dest)
    path = dest / location
    path.write_bytes(path.read_bytes() + b"\n# tampered\n")
    return Release(dest)


class TestReleaseContentIsCheckedBeforeItIsInstalled(BootstrapCase):
    """Installing is where a release asserts its identity to a repository.

    A release directory that was damaged, half copied, or edited must not be
    able to hand a target non-canonical bytes under a canonical version label.
    """

    def test_bootstrap_refuses_a_release_whose_payload_was_tampered_with(self):
        damaged = damaged_copy(self.release, Path(self._tmp.name) / "damaged",
                               "payload/scripts/workflow_state.py")
        with self.assertRaises(ReleaseIntegrityError) as caught:
            bootstrap(self.target, damaged, now=FIXED_NOW)
        self.assertIn("payload/scripts/workflow_state.py", str(caught.exception))
        self.assertFalse(is_managed(self.target))

    def test_bootstrap_refuses_a_release_whose_template_was_tampered_with(self):
        damaged = damaged_copy(self.release, Path(self._tmp.name) / "damaged-t",
                               "templates/docs/ai-workflow/WORKFLOW_STATE.json")
        with self.assertRaises(ReleaseIntegrityError):
            bootstrap(self.target, damaged, now=FIXED_NOW)

    def test_update_refuses_a_damaged_release_too(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        damaged = damaged_copy(self.release, Path(self._tmp.name) / "damaged-u",
                               "payload/scripts/workflow_fingerprint.py")
        with self.assertRaises(ReleaseIntegrityError):
            update(self.target, damaged, force=True, now=FIXED_NOW)
        self.assertEqual(drift(self.target, self.release), [])

    def test_the_damaged_file_never_reaches_the_target(self):
        damaged = damaged_copy(self.release, Path(self._tmp.name) / "damaged-2",
                               "payload/scripts/workflow_state.py")
        with self.assertRaises(ReleaseIntegrityError):
            bootstrap(self.target, damaged, now=FIXED_NOW)
        landed = self.target / "scripts/workflow_state.py"
        self.assertTrue(not landed.exists() or b"tampered" not in landed.read_bytes())


class TestBootstrapDoesNotClobberTheRepositorysOwnFiles(BootstrapCase):
    """`.claude/commands/` and `scripts/` are ordinary names. A repository that
    already keeps files there must be told, not quietly overwritten."""

    OWN = ".claude/commands/review-plan.md"
    MINE = "# my own review-plan command\n"

    def _write_own(self) -> Path:
        path = self.target / self.OWN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.MINE)
        return path

    def test_a_colliding_file_stops_the_bootstrap(self):
        path = self._write_own()
        with self.assertRaises(CollisionError) as caught:
            bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertEqual([c.path for c in caught.exception.collisions], [self.OWN])
        self.assertEqual(path.read_text(), self.MINE)
        self.assertFalse(is_managed(self.target))

    def test_force_overwrites_it(self):
        path = self._write_own()
        bootstrap(self.target, self.release, force=True, now=FIXED_NOW)
        self.assertNotEqual(path.read_text(), self.MINE)
        self.assertEqual(drift(self.target, self.release), [])

    def test_a_directory_in_the_way_is_reported_not_crashed_on(self):
        (self.target / self.OWN).mkdir(parents=True)
        with self.assertRaises(CollisionError) as caught:
            bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertIn("directory", str(caught.exception))

    def test_a_directory_where_a_state_template_goes_is_reported_too(self):
        """State templates are never overwritten, but they still have to be
        files -- a directory there would fail half-way through the install."""
        (self.target / "docs/ACTIVE_MILESTONE.md").mkdir(parents=True)
        with self.assertRaises(CollisionError) as caught:
            bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertEqual([c.path for c in caught.exception.collisions],
                         ["docs/ACTIVE_MILESTONE.md"])
        self.assertFalse(is_managed(self.target))

    def test_force_does_not_paper_over_a_directory_in_a_state_path(self):
        (self.target / "docs/ACTIVE_MILESTONE.md").mkdir(parents=True)
        with self.assertRaises(CollisionError):
            bootstrap(self.target, self.release, force=True, now=FIXED_NOW)

    def test_a_directory_at_a_merged_path_is_reported(self):
        (self.target / "CLAUDE.md").mkdir()
        with self.assertRaises(CollisionError) as caught:
            bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertEqual([c.path for c in caught.exception.collisions], ["CLAUDE.md"])

    def test_an_update_reports_a_directory_where_it_must_write(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        (self.target / ".gitignore").unlink()
        (self.target / ".gitignore").mkdir()
        with self.assertRaises(CollisionError) as caught:
            update(self.target, self.release, force=True, now=FIXED_NOW)
        self.assertEqual([c.path for c in caught.exception.collisions], [".gitignore"])

    def test_a_file_that_already_holds_the_release_bytes_is_not_a_collision(self):
        """This is what makes an interrupted bootstrap re-runnable."""
        artifact = next(a for a in self.release.installable("full")
                        if a.target_path == self.OWN)
        path = self.target / self.OWN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.release.read(artifact.location))
        bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertEqual(drift(self.target, self.release), [])

    def test_the_cli_refuses_and_then_honours_force(self):
        """The flag is one line of wiring, which is exactly where a typo would
        sit unnoticed behind a library-level test."""
        import io

        from workflow_manager.cli import main

        path = self._write_own()

        def cli(*args):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--manager-root", str(REPO_ROOT), *args])
            return code, out.getvalue() + err.getvalue()

        code, output = cli("bootstrap", str(self.target))
        self.assertEqual(code, 2)
        self.assertIn(self.OWN, output)
        self.assertIn("--force", output)
        self.assertEqual(path.read_text(), self.MINE)
        self.assertFalse(is_managed(self.target))

        self.assertEqual(cli("bootstrap", str(self.target), "--force")[0], 0)
        self.assertEqual(cli("verify", str(self.target))[0], 0)

    def test_an_update_that_adds_a_file_the_repository_owns_stops_too(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", NEXT_RELEASE)
        mine = self.target / "docs/ai-workflow/WHATS_NEW.md"
        mine.write_text("# mine\n")
        with self.assertRaises(CollisionError):
            update(self.target, nxt, now=FIXED_NOW)
        self.assertEqual(mine.read_text(), "# mine\n")


class TestInterruptedOperationsAreRerunnable(BootstrapCase):
    """Neither operation is atomic. Both are idempotent, which is the contract
    `docs/ARCHITECTURE.md` states: run the same command again."""

    @staticmethod
    @contextlib.contextmanager
    def _interrupted_at(nth: int):
        """Make `_write` raise on its `nth` call, for the block's duration."""
        real = install_module._write
        calls = {"n": 0}

        def failing(path, data, executable=False):
            calls["n"] += 1
            if calls["n"] == nth:
                raise KeyboardInterrupt("simulated interruption")
            return real(path, data, executable)

        install_module._write = failing
        try:
            yield calls
        finally:
            install_module._write = real

    def _write_count(self) -> int:
        """How many files a bootstrap of a fresh repository writes."""
        counted = empty_repo(Path(self._tmp.name) / "counted")
        with self._interrupted_at(0) as calls:
            bootstrap(counted, self.release, now=FIXED_NOW)
        return calls["n"]

    def test_bootstrap_interrupted_at_any_write_converges_when_re_run(self):
        """Every write, not a sample of them: the contract is that the command
        can be re-run from wherever it stopped, and 'wherever' is all of them."""
        for nth in range(1, self._write_count() + 1):
            with self.subTest(interrupted_at=nth):
                target = empty_repo(Path(self._tmp.name) / f"boot-{nth}")
                with self._interrupted_at(nth) as calls:
                    with self.assertRaises(KeyboardInterrupt):
                        bootstrap(target, self.release, now=FIXED_NOW)
                self.assertFalse(is_managed(target), "a half-install must not look managed")
                installation = bootstrap(target, self.release, now=FIXED_NOW)
                self.assertEqual(drift(target, self.release), [])
                self.assertEqual(verify(target, self.release), [])
                self.assertTrue(calls["n"] >= nth)
                self.assertEqual(
                    {rec["source"] for rec in installation.generated.values()}, {"template"},
                    "state the interrupted run wrote is the template, not the repository's",
                )

    LIVE_STATE = '{"schema_version": 1, "active_work_item_id": "wi", "work_items": {"wi": {}}}\n'

    def _managed_repo_with_live_state(self, name: str) -> Path:
        target = empty_repo(Path(self._tmp.name) / name)
        bootstrap(target, self.release, now=FIXED_NOW)
        (target / "docs/ai-workflow/WORKFLOW_STATE.json").write_text(self.LIVE_STATE)
        return target

    def test_an_interrupted_update_resumes_at_any_write_on_a_plain_re_run(self):
        """The half-applied files are the new release's own bytes. Calling them
        local edits would leave `--force` -- which discards edits -- as the only
        way forward."""
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", NEXT_RELEASE,
                                      change_ci=True)
        counted = self._managed_repo_with_live_state("update-count")
        with self._interrupted_at(0) as calls:
            update(counted, nxt, now=FIXED_NOW)
        total = calls["n"]
        self.assertGreater(total, 1, "an update that writes nothing proves nothing")

        for nth in range(1, total + 1):
            with self.subTest(interrupted_at=nth):
                target = self._managed_repo_with_live_state(f"update-{nth}")
                state = target / "docs/ai-workflow/WORKFLOW_STATE.json"
                with self._interrupted_at(nth):
                    with self.assertRaises(KeyboardInterrupt):
                        update(target, nxt, now="2027-01-01T00:00:00Z")
                self.assertEqual(Installation.read(target).workflow_version, NEWEST_RELEASE,
                                 "the record must not claim a release that is half applied")

                updated, _ = update(target, nxt, now="2027-01-02T00:00:00Z")
                self.assertEqual(updated.workflow_version, NEXT_RELEASE)
                self.assertEqual(drift(target, nxt), [])
                self.assertEqual(verify(target, nxt), [])
                self.assertEqual(state.read_text(), self.LIVE_STATE)

    def test_a_genuine_local_edit_still_blocks_a_resumed_update(self):
        """Resumability must not become a way to lose an edit."""
        bootstrap(self.target, self.release, now=FIXED_NOW)
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", NEXT_RELEASE)
        path = self.target / "scripts/workflow_state.py"
        path.write_text(path.read_text() + "\n# mine\n")
        with self.assertRaises(DriftError):
            update(self.target, nxt, now=FIXED_NOW)
        self.assertIn("# mine", path.read_text())


class TestTheInstallationRecordSurvivesInterruption(BootstrapCase):
    def test_the_record_is_replaced_by_rename_not_written_in_place(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        update(self.target, self.release, now=FIXED_NOW)
        strays = list((self.target / ".workflow-manager").glob("*.tmp"))
        self.assertEqual(strays, [])

    def test_an_unreadable_record_names_its_path_and_cause(self):
        """The step to take is the CLI's `next:` line (`test_operator_ux.py`);
        the exception states the cause alone."""
        bootstrap(self.target, self.release, now=FIXED_NOW)
        installation_path(self.target).write_text("{ truncated")
        with self.assertRaises(CorruptInstallationError) as caught:
            Installation.read(self.target)
        self.assertIn(str(installation_path(self.target)), str(caught.exception))
        self.assertIn("is unreadable (", str(caught.exception))
        self.assertNotIn("Delete", str(caught.exception))

    def test_every_command_reports_a_damaged_record_including_bootstrap(self):
        """`bootstrap` used to answer "already managed; use update()" -- advice
        that cannot work, since `update` reads the same broken record."""
        bootstrap(self.target, self.release, now=FIXED_NOW)
        installation_path(self.target).write_text("{ truncated")
        for operation in (
            lambda: bootstrap(self.target, self.release, now=FIXED_NOW),
            lambda: update(self.target, self.release, now=FIXED_NOW),
            lambda: verify(self.target, self.release),
            lambda: status(self.target, self.release),
            lambda: uninstall(self.target),
        ):
            with self.assertRaises(CorruptInstallationError):
                operation()

    def test_the_documented_recovery_actually_recovers(self):
        """Delete the record, re-run bootstrap: the payload is already the
        release's own bytes, so nothing collides and nothing is rewritten."""
        bootstrap(self.target, self.release, now=FIXED_NOW)
        state = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        mine = '{"schema_version": 1, "active_work_item_id": "wi", "work_items": {"wi": {}}}\n'
        state.write_text(mine)
        installation_path(self.target).write_text("{ truncated")

        shutil.rmtree(self.target / ".workflow-manager")
        bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertEqual(verify(self.target, self.release), [])
        self.assertEqual(state.read_text(), mine, "recovery must not cost the repository its work")


class TestTheConformanceCiIsReleaseOwned(BootstrapCase):
    """It runs a particular release's suites and nothing writes to it at run
    time, so it belongs to the release, not to the repository."""

    CI = ".github/workflows/workflow-conformance.yml"

    def test_it_is_declared_as_a_release_template(self):
        self.assertIn(self.CI, RELEASE_TEMPLATES)

    def test_every_template_the_release_ships_has_a_declared_disposition(self):
        """A future release that adds a template must be given an owner. Without
        this, an unknown one would simply never be installed, silently."""
        from workflow_manager.release import MERGED_TEMPLATES, STATE_TEMPLATES

        declared = set(STATE_TEMPLATES) | set(RELEASE_TEMPLATES) | set(MERGED_TEMPLATES)
        shipped = {t["target_path"] for t in self.release.templates()}
        self.assertEqual(shipped, declared)

    def test_a_full_install_records_it_as_managed_not_generated(self):
        installation = bootstrap(self.target, self.release, now=FIXED_NOW)
        self.assertIn(self.CI, installation.managed)
        self.assertNotIn(self.CI, installation.generated)

    def test_editing_it_is_reported_as_drift(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        path = self.target / self.CI
        path.write_text(path.read_text() + "\n# local\n")
        self.assertIn((self.CI, "modified"), [(d.path, d.kind) for d in drift(self.target, self.release)])

    def test_a_new_release_updates_it(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", NEXT_RELEASE,
                                      change_ci=True)
        _, changes = update(self.target, nxt, now=FIXED_NOW)
        self.assertIn(f"updated {self.CI}", changes)
        self.assertIn(f"{NEXT_RELEASE} suites", (self.target / self.CI).read_text())
        self.assertEqual(drift(self.target, nxt), [])

    def test_the_runtime_profile_does_not_install_it(self):
        """Under `runtime` the documents several suites lint are absent, so the
        suites are red by design. Shipping the CI that runs them would hand a
        repository a red pipeline on its first push."""
        runtime = bootstrap(self.target, self.release, profile="runtime", now=FIXED_NOW)
        self.assertNotIn(self.CI, runtime.managed)
        self.assertFalse((self.target / self.CI).exists())

    def test_narrowing_the_profile_removes_it_and_widening_restores_it(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        update(self.target, self.release, profile="runtime", now=FIXED_NOW)
        self.assertFalse((self.target / self.CI).exists())
        update(self.target, self.release, profile="full", now=FIXED_NOW)
        self.assertTrue((self.target / self.CI).exists())
        self.assertEqual(drift(self.target, self.release), [])


class _PackagedReleases(BootstrapCase):
    """Synthetic published releases, served from a local source directory
    (plan 5.5, CP3): `7.0.0` and `7.0.1` are packaged and pinned in a pin file
    of this class's own. Every CLI call names this class's source and its own
    per-test cache, and the real pin file is never consulted."""

    PINNED = ("7.0.0", "7.0.1")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._class_tmp = tempfile.TemporaryDirectory()
        root = Path(cls._class_tmp.name)
        base = support.release(NEWEST_RELEASE)
        cls.source_dir = root / "source"
        releases = {}
        for version in cls.PINNED:
            tree = synthesize_next_release(base, root / "trees" / version, version)
            built = package_module.build_package(tree.root, cls.source_dir / version)
            releases[version] = {"archive": built.archive.name,
                                 "sha256": package_module.file_sha256(built.archive),
                                 "manifest_sha256": package_module.file_sha256(built.manifest)}
        cls.trees = root / "trees"
        cls.pins_path = root / "published_releases.json"
        cls.pins_path.write_text(json.dumps({"schema_version": 1,
                                             "repository": "example/workflow",
                                             "releases": releases}))

    @classmethod
    def tearDownClass(cls):
        cls._class_tmp.cleanup()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.cache = Path(self._tmp.name) / "cache"
        patcher = mock.patch.object(release_source, "PINS_PATH", self.pins_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cli(self, *args, source_dir=None):
        """The CLI in-process, with its report captured rather than printed."""
        out, err = io.StringIO(), io.StringIO()
        argv = ["--release-source", str(source_dir or self.source_dir),
                "--release-cache", str(self.cache), *args]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_module.main(argv)
        self.cli_stdout, self.cli_stderr = out.getvalue(), err.getvalue()
        self.cli_output = self.cli_stdout + self.cli_stderr
        return code


class TestReleaseResolution(_PackagedReleases):
    """What `bootstrap`, `update`, `status` and `verify` mean by "the release":
    the pins through the cache, and `--release-dir`."""

    def test_bootstrap_installs_the_newest_pinned_and_records_its_package(self):
        self.assertEqual(self._cli("bootstrap", str(self.target)), 0, self.cli_output)
        record = Installation.read(self.target)
        self.assertEqual(record.workflow_version, "7.0.1")
        pins = release_source.load_pins(self.pins_path)
        self.assertEqual(record.source, pins.source_record("7.0.1"))
        self.assertEqual(record.source["kind"], "package")

    def test_install_bytes_equal_those_of_the_release_itself(self):
        """INV-4: a package-backed install writes what a direct install of the
        same release writes; only the record's `source` is new."""
        self.assertEqual(self._cli("bootstrap", str(self.target)), 0, self.cli_output)
        direct = empty_repo(Path(self._tmp.name) / "direct")
        bootstrap(direct, Release(self.trees / "7.0.1"))
        ours, theirs = Installation.read(self.target), Installation.read(direct)
        self.assertEqual(ours.managed, theirs.managed)
        self.assertEqual(ours.generated, theirs.generated)
        self.assertEqual(ours.merged, theirs.merged)
        self.assertIsNone(theirs.source)

    def test_a_cache_hit_needs_no_source(self):
        self.assertEqual(self._cli("--release-version", "7.0.0", "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        gone = Path(self._tmp.name) / "no-source"
        self.assertEqual(self._cli("verify", str(self.target), source_dir=gone), 0,
                         self.cli_output)
        self.assertIn("installation matches workflow 7.0.0", self.cli_stdout)

    def test_a_broken_cache_entry_is_discarded_and_refetched(self):
        self.assertEqual(self._cli("--release-version", "7.0.0", "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        manifest = self.cache / "7.0.0" / "tree" / "manifest.json"
        manifest.write_text(manifest.read_text() + " ")
        self.assertEqual(self._cli("verify", str(self.target)), 0, self.cli_output)
        self.assertIn("discarding cache entry", self.cli_stderr)
        self.assertEqual(self._cli("verify", str(self.target)), 0, self.cli_output)
        self.assertNotIn("discarding", self.cli_stderr)

    def test_an_unreachable_package_is_unavailable_and_exits_1(self):
        gone = Path(self._tmp.name) / "no-source"
        self.assertEqual(self._cli("bootstrap", str(self.target), source_dir=gone), 1)
        self.assertIn("cannot fetch", self.cli_stderr)
        self.assertFalse(is_managed(self.target))

    def test_update_moves_to_the_newest_pinned(self):
        self.assertEqual(self._cli("--release-version", "7.0.0", "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        self.assertEqual(self._cli("update", str(self.target)), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")

    def test_reports_are_measured_against_the_release_the_target_records(self):
        """A target on an older release must not start looking broken because
        a newer one was published."""
        self.assertEqual(self._cli("--release-version", "7.0.0", "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        self.assertEqual(self._cli("status", str(self.target)), 0, self.cli_output)
        self.assertIn("workflow 7.0.0", self.cli_stdout)
        self.assertIn("source: package workflow-7.0.0.tar.gz from example/workflow",
                      self.cli_stdout)
        self.assertEqual(self._cli("verify", str(self.target)), 0, self.cli_output)

    def test_a_damaged_target_is_never_reported_as_clean(self):
        self.assertEqual(self._cli("bootstrap", str(self.target)), 0, self.cli_output)
        (self.target / "scripts/workflow_state.py").write_text("# clobbered\n")
        self.assertEqual(self._cli("status", str(self.target)), 1)
        self.assertEqual(self._cli("verify", str(self.target)), 1)

    def test_a_target_recording_an_unpublished_release_needs_release_dir(self):
        """5.5: status prints what the record says, then names the remedy."""
        bootstrap(self.target, self.release, now=FIXED_NOW)
        record = Installation.read(self.target)
        record.workflow_version = "9.9.9"
        record.source = None
        record.write(self.target)
        self.assertEqual(self._cli("status", str(self.target)), 1)
        self.assertIn("workflow 9.9.9 (full profile)", self.cli_stdout)
        self.assertIn("source: not recorded", self.cli_stdout)
        self.assertIn(f"installed at {FIXED_NOW}", self.cli_stdout)
        self.assertIn("release 9.9.9 is not published", self.cli_stderr)
        self.assertIn("--release-dir", self.cli_stderr)
        self.assertEqual(self._cli("verify", str(self.target)), 1)
        self.assertIn("--release-dir", self.cli_stderr)

    def test_release_dir_installs_an_unpublished_release_as_local(self):
        local = synthesize_next_release(self.release, Path(self._tmp.name) / "dev", "8.0.0")
        self.assertEqual(self._cli("--release-dir", str(local.root), "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        record = Installation.read(self.target)
        self.assertEqual((record.workflow_version, record.source), ("8.0.0", {"kind": "local"}))
        self.assertEqual(self._cli("--release-dir", str(local.root), "status",
                                   str(self.target)), 0, self.cli_output)
        self.assertIn("source: (local, unpublished)", self.cli_stdout)
        # Without it, an unpublished release cannot be verified.
        self.assertEqual(self._cli("verify", str(self.target)), 1)

    def test_release_dir_holding_a_pinned_version_is_recorded_as_its_package(self):
        self.assertEqual(self._cli("--release-dir", str(self.trees / "7.0.0"), "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        pins = release_source.load_pins(self.pins_path)
        self.assertEqual(Installation.read(self.target).source, pins.source_record("7.0.0"))
        self.assertIn("using a local copy of published release 7.0.0", self.cli_stderr)

    def test_release_dir_holding_an_altered_pinned_version_is_refused(self):
        altered = Path(self._tmp.name) / "altered"
        shutil.copytree(self.trees / "7.0.0", altered)
        _alter_consistently(altered)
        self.assertEqual(self._cli("--release-dir", str(altered), "bootstrap",
                                   str(self.target)), 1)
        self.assertIn("claims published release 7.0.0", self.cli_stderr)
        self.assertFalse(is_managed(self.target))

    def test_release_dir_of_another_version_is_refused(self):
        self.assertEqual(self._cli("--release-dir", str(self.trees / "7.0.0"),
                                   "--release-version", "7.0.1", "bootstrap",
                                   str(self.target)), 1)
        self.assertIn("not the requested 7.0.1", self.cli_stderr)

    def test_an_unpinned_version_without_release_dir_is_not_published(self):
        """CP6: with the checkout fallback gone, an unpinned version installs
        only from a local directory."""
        self.assertEqual(self._cli("--release-version", "7.1.0", "bootstrap",
                                   str(self.target)), 1)
        self.assertIn("release 7.1.0 is not published", self.cli_stderr)
        self.assertIn("--release-dir", self.cli_stderr)
        self.assertFalse(is_managed(self.target))

    def test_without_pins_there_is_no_default_release(self):
        empty = Path(self._tmp.name) / "no-pins.json"
        empty.write_text('{"schema_version": 1, "repository": "example/workflow", '
                         '"releases": {}}')
        with mock.patch.object(release_source, "PINS_PATH", empty):
            self.assertEqual(self._cli("bootstrap", str(self.target)), 1)
        self.assertIn("no Workflow release is published", self.cli_stderr)
        self.assertFalse(is_managed(self.target))

    def test_releases_lists_the_pins(self):
        self.assertEqual(self._cli("releases"), 0, self.cli_output)
        lines = self.cli_stdout.splitlines()
        self.assertEqual([line.split()[0] for line in lines], ["7.0.0", "7.0.1"])
        self.assertIn("[not cached]", lines[0])
        self._cli("--release-version", "7.0.0", "bootstrap", str(self.target))
        self._cli("releases")
        self.assertIn("[cached]", self.cli_stdout.splitlines()[0])

    def test_the_cache_named_by_release_cache_is_the_one_filled(self):
        self._cli("bootstrap", str(self.target))
        self.assertTrue((self.cache / "7.0.1" / "complete").is_file())


class TestManagerRootAlias(_PackagedReleases):
    """The deprecated `--manager-root` alias (5.5), on a temporary checkout
    this class lays out itself in the alias's old release-directory layout."""

    def setUp(self):
        super().setUp()
        self.alias = Path(self._tmp.name) / "old-checkout"
        self.alias_releases = self.alias / "distribution" / "workflow"

    def test_an_unpinned_checkout_release_is_used_as_a_release_dir(self):
        synthesize_next_release(self.release, self.alias_releases / "6.0.0", "6.0.0")
        self.assertEqual(self._cli("--manager-root", str(self.alias), "--release-version",
                                   "6.0.0", "bootstrap", str(self.target)), 0, self.cli_output)
        self.assertIn("--manager-root is deprecated", self.cli_stderr)
        record = Installation.read(self.target)
        self.assertEqual((record.workflow_version, record.source), ("6.0.0", {"kind": "local"}))

    def test_an_altered_pinned_checkout_release_is_refused(self):
        altered = self.alias_releases / "7.0.0"
        shutil.copytree(self.trees / "7.0.0", altered)
        _alter_consistently(altered)
        self.assertEqual(Release(altered).verify(), [])
        self.assertEqual(self._cli("--manager-root", str(self.alias), "--release-version",
                                   "7.0.0", "bootstrap", str(self.target)), 1)
        self.assertIn("claims published release 7.0.0", self.cli_stderr)
        self.assertFalse(is_managed(self.target))
        self.assertEqual(sorted(p.name for p in self.target.iterdir()), [".git"])

    def test_a_checkout_without_the_version_falls_through_to_the_pins(self):
        self.alias.mkdir()
        self.assertEqual(self._cli("--manager-root", str(self.alias), "bootstrap",
                                   str(self.target)), 0, self.cli_output)
        self.assertIn("--manager-root is deprecated", self.cli_stderr)
        self.assertEqual(Installation.read(self.target).source["kind"], "package")

    def test_releases_adds_the_checkout_versions(self):
        synthesize_next_release(self.release, self.alias_releases / "6.0.0", "6.0.0")
        self.assertEqual(self._cli("--manager-root", str(self.alias), "releases"), 0)
        self.assertEqual([line.split()[0] for line in self.cli_stdout.splitlines()],
                         ["7.0.0", "7.0.1", "6.0.0"])
        self.assertIn("6.0.0  (--manager-root, unpublished)", self.cli_stdout)


def _alter_consistently(tree: Path) -> None:
    """Change one payload file and record its new digest in the manifest, so
    `Release.verify()` passes but the manifest no longer hashes to its pin."""
    manifest_path = tree / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = manifest["artifacts"][0]
    path = tree / record["location"]
    data = path.read_bytes() + b"\n# altered\n"
    path.write_bytes(data)
    record["sha256"], record["size"] = sha256(data), len(data)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


class TestSourceRecord(unittest.TestCase):
    """5.5: the record's `source` is additive and optional."""

    PRE_M2 = {
        "schema_version": 1, "workflow_version": "2.6.0", "profile": "full",
        "upstream": {"tag": "t"}, "provenance": {"origin": "authored"},
        "installed_at": FIXED_NOW, "updated_at": FIXED_NOW,
        "managed": {"a": {"sha256": "x", "executable": False}}, "generated": {}, "merged": {},
    }

    def test_a_record_without_source_round_trips_unchanged(self):
        before = (json.dumps(self.PRE_M2, indent=2, ensure_ascii=False) + "\n").encode()
        loaded = Installation.from_dict(json.loads(before))
        self.assertIsNone(loaded.source)
        self.assertEqual(loaded.serialize(), before)

    def test_a_record_with_source_round_trips(self):
        for record in ({"kind": "local"},
                       {"kind": "package", "repository": "example/workflow",
                        "archive": "workflow-2.6.0.tar.gz", "sha256": "0" * 64}):
            with self.subTest(kind=record["kind"]):
                data = dict(self.PRE_M2, source=record)
                loaded = Installation.from_dict(data)
                self.assertEqual(loaded.source, record)
                again = Installation.from_dict(json.loads(loaded.serialize()))
                self.assertEqual(again.serialize(), loaded.serialize())
                self.assertEqual(loaded.to_dict()["schema_version"], 1)

    def test_a_malformed_source_is_a_corrupt_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            path = installation_path(target)
            path.parent.mkdir()
            path.write_text(json.dumps(dict(self.PRE_M2, source="package")))
            with self.assertRaises(CorruptInstallationError):
                Installation.read(target)


class TestStatusNeverClaimsCleanWithoutLooking(BootstrapCase):
    def test_an_unverified_installation_does_not_say_clean(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        result = status(self.target)
        self.assertTrue(result.managed)
        self.assertFalse(result.verified)
        self.assertNotIn("clean", str(result))
        self.assertIn("not verified", str(result))

    def test_a_verified_clean_installation_says_clean(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        result = status(self.target, self.release)
        self.assertTrue(result.verified)
        self.assertIn("clean", str(result))


class TestNoRuntimeDependencyOnTheUpstreamRepository(BootstrapCase):
    """The bootstrapper must work on a machine that has never held RepFlow.

    No Manager code path may read the upstream repository. This proves it by
    running the code where the upstream checkout's default location cannot
    exist.
    """

    MANAGER_SOURCES = sorted((REPO_ROOT / "src" / "workflow_manager").glob("*.py"))

    def test_no_manager_module_names_the_upstream_checkout(self):
        for path in self.MANAGER_SOURCES:
            text = path.read_text()
            self.assertNotIn("repflow", text.lower(), path.name)
            self.assertNotIn(str(Path.home()), text, path.name)

    def test_a_full_lifecycle_runs_with_home_pointed_somewhere_empty(self):
        """`~/Workspace/repflow-android` is where the upstream clone lives. With
        `HOME` moved, that path does not exist -- so anything that reached for
        it would fail here rather than silently succeed on this machine."""
        elsewhere = Path(self._tmp.name) / "empty-home"
        elsewhere.mkdir()
        self.assertFalse((elsewhere / "Workspace" / "repflow-android").exists())
        env = cli_env(HOME=str(elsewhere), PYTHONDONTWRITEBYTECODE="1")
        for argv in (
            ["bootstrap", str(self.target)],
            ["verify", str(self.target)],
            ["status", str(self.target)],
            ["update", str(self.target)],
            ["verify", str(self.target)],
            ["uninstall", str(self.target)],
        ):
            with self.subTest(command=argv[0]):
                proc = subprocess.run(
                    [sys.executable, "-m", "workflow_manager", *argv],
                    cwd=str(REPO_ROOT), capture_output=True, text=True, env=env,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
