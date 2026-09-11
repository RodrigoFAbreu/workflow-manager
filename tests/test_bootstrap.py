#!/usr/bin/env python3
"""Bootstrapper unit behaviour, against disposable repositories only.

Nothing here touches a real consumer. Every test builds an empty Git
repository in a temporary directory, installs into it, and inspects the
result.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

import workflow_manager.install as install_module
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
    available_versions,
    find_release,
    sha256,
)

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
        self.release = find_release(REPO_ROOT, "2.3.1")
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
        elif change_ci and record["target_path"] in RELEASE_TEMPLATES:
            data = data + b"\n# runs the 2.3.2 suites\n"
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

    A `distribution/` that was damaged, half checked out, or edited must not be
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
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", "2.3.2")
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
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", "2.3.2",
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
                self.assertEqual(Installation.read(target).workflow_version, "2.3.1",
                                 "the record must not claim a release that is half applied")

                updated, _ = update(target, nxt, now="2027-01-02T00:00:00Z")
                self.assertEqual(updated.workflow_version, "2.3.2")
                self.assertEqual(drift(target, nxt), [])
                self.assertEqual(verify(target, nxt), [])
                self.assertEqual(state.read_text(), self.LIVE_STATE)

    def test_a_genuine_local_edit_still_blocks_a_resumed_update(self):
        """Resumability must not become a way to lose an edit."""
        bootstrap(self.target, self.release, now=FIXED_NOW)
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", "2.3.2")
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

    def test_an_unreadable_record_says_how_to_recover(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        installation_path(self.target).write_text("{ truncated")
        with self.assertRaises(CorruptInstallationError) as caught:
            Installation.read(self.target)
        self.assertIn(".workflow-manager", str(caught.exception))
        self.assertIn("bootstrap", str(caught.exception))

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
        nxt = synthesize_next_release(self.release, Path(self._tmp.name) / "r2", "2.3.2",
                                      change_ci=True)
        _, changes = update(self.target, nxt, now=FIXED_NOW)
        self.assertIn(f"updated {self.CI}", changes)
        self.assertIn("2.3.2 suites", (self.target / self.CI).read_text())
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


class TestReleaseResolution(BootstrapCase):
    """What `bootstrap`, `update`, `status` and `verify` mean by "the release"
    once `distribution/` holds more than one."""

    def setUp(self):
        super().setUp()
        self.manager_root = Path(self._tmp.name) / "manager"
        base = self.manager_root / "distribution" / "workflow"
        base.mkdir(parents=True)
        (base / "2.3.1").symlink_to(self.release.root)
        synthesize_next_release(self.release, base / "2.3.2", "2.3.2")

    def _cli(self, *args):
        """The CLI in-process, with its report captured rather than printed."""
        import io

        from workflow_manager.cli import main

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--manager-root", str(self.manager_root), *args])
        self.cli_output = out.getvalue() + err.getvalue()
        return code

    def test_available_versions_are_ordered_oldest_first(self):
        self.assertEqual(available_versions(self.manager_root), ["2.3.1", "2.3.2"])

    def test_an_unpinned_release_means_the_newest(self):
        self.assertEqual(find_release(self.manager_root).version, "2.3.2")
        self.assertEqual(find_release(self.manager_root, "2.3.1").version, "2.3.1")

    def test_bootstrap_installs_the_newest_and_update_moves_to_it(self):
        self.assertEqual(self._cli("bootstrap", str(self.target)), 0)
        self.assertEqual(Installation.read(self.target).workflow_version, "2.3.2")

    def test_reports_are_measured_against_the_release_the_target_records(self):
        """A target pinned to an older release must not start looking broken
        because a newer one landed in `distribution/`."""
        self.assertEqual(self._cli("--release-version", "2.3.1", "bootstrap", str(self.target)), 0)
        self.assertEqual(self._cli("status", str(self.target)), 0)
        self.assertEqual(self._cli("verify", str(self.target)), 0)

    def test_a_damaged_target_is_never_reported_as_clean(self):
        self.assertEqual(self._cli("--release-version", "2.3.1", "bootstrap", str(self.target)), 0)
        (self.target / "scripts/workflow_state.py").write_text("# clobbered\n")
        self.assertEqual(self._cli("status", str(self.target)), 1)
        self.assertEqual(self._cli("verify", str(self.target)), 1)

    def test_a_target_recording_a_release_that_is_absent_is_an_error(self):
        bootstrap(self.target, self.release, now=FIXED_NOW)
        record = Installation.read(self.target)
        record.workflow_version = "9.9.9"
        record.write(self.target)
        self.assertEqual(self._cli("status", str(self.target)), 2)


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

    `tools/migrate.py` reads the upstream tag; nothing else may. Grepping the
    distribution proves the *content* is clean (see `test_payload_bytes.py`);
    this proves the *code path* is, by running it where the upstream checkout's
    default location cannot exist.
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
        env = {
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "PATH": "/usr/bin:/bin",
            "HOME": str(elsewhere),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
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
