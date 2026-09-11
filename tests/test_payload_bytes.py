#!/usr/bin/env python3
"""Migrated bytes are the frozen bytes.

Two independent checks, deliberately not sharing a source of truth:

1. Self-contained: every file in the release matches its manifest digest, and
   the release contains nothing the manifest does not record.
2. Adversarial: every payload and fixture file is byte-identical to
   `git show <frozen commit>:<path>` read straight from the upstream object
   store -- and a fresh re-extraction produces the committed tree exactly.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from support import REPO_ROOT, frozen_bytes, upstream_available

from workflow_manager.release import find_release, sha256


class TestReleaseIsSelfConsistent(unittest.TestCase):
    def setUp(self):
        self.release = find_release(REPO_ROOT, "2.3.1")

    def test_no_missing_file_no_digest_mismatch_no_stray_file(self):
        self.assertEqual(self.release.verify(), [])

    def test_recorded_sizes_match_the_files(self):
        for artifact in self.release.artifacts:
            self.assertEqual(
                len(self.release.read(artifact.location)), artifact.size, artifact.location,
            )

    def test_the_review_generation_script_is_executable(self):
        script = next(
            a for a in self.release.artifacts
            if a.target_path == "scripts/prepare-ai-review.sh"
        )
        self.assertTrue(script.executable)
        self.assertTrue(
            (self.release.root / script.location).stat().st_mode & 0o111,
            "prepare-ai-review.sh lost its executable bit in the payload",
        )

    def test_payload_and_fixture_trees_hold_only_recorded_artifacts(self):
        for subtree in ("payload", "fixtures"):
            root = self.release.root / subtree
            if not root.exists():
                continue
            on_disk = {
                p.relative_to(self.release.root).as_posix()
                for p in root.rglob("*") if p.is_file()
            }
            recorded = {a.location for a in self.release.artifacts}
            self.assertEqual(on_disk - recorded, set(), f"unrecorded files under {subtree}/")


class TestPayloadMatchesFrozenUpstream(unittest.TestCase):
    def setUp(self):
        if not upstream_available():
            self.skipTest("frozen upstream repository not available")
        self.release = find_release(REPO_ROOT, "2.3.1")

    def test_every_migrated_file_is_byte_identical_to_the_frozen_commit(self):
        mismatched = []
        for artifact in self.release.artifacts:
            frozen = frozen_bytes(artifact.target_path)
            if self.release.read(artifact.location) != frozen:
                mismatched.append(artifact.target_path)
        self.assertEqual(mismatched, [])

    def test_manifest_digests_are_the_frozen_digests(self):
        for artifact in self.release.artifacts:
            self.assertEqual(sha256(frozen_bytes(artifact.target_path)), artifact.sha256,
                             artifact.target_path)

    def test_excluded_digests_are_the_frozen_digests(self):
        """An exclusion's recorded digest must be the real one, so the
        inventory cannot drift from what it claims to have looked at."""
        for record in self.release.manifest["exclusions"]:
            self.assertEqual(
                sha256(frozen_bytes(record["upstream_path"])), record["upstream_sha256"],
                record["upstream_path"],
            )

    def test_a_fresh_extraction_reproduces_the_committed_distribution(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "migrate.py"), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestNoUpstreamReachback(unittest.TestCase):
    """Nothing in the distribution reaches back into the RepFlow working tree.

    The risk being tested is a *functional* one: a script, manifest or config
    in the distribution that resolves a path into the upstream checkout at
    run time. Frozen design prose that quotes an absolute path inside a worked
    example is not that, so those occurrences are pinned by exact location and
    count instead of being waved through -- a new one fails this suite.
    """

    #: Executable and machine-read file types. A reachback here would be live.
    FUNCTIONAL_SUFFIXES = (".py", ".sh", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini")

    #: Frozen documentation prose that quotes the upstream path, with the exact
    #: number of *lines* doing so at v2.3.1. Both are illustrative example paths
    #: in WORKFLOW_V2_PLAN.md's worktree-identity worked example.
    PINNED_PROSE = {
        "payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md": 2,
    }

    NEEDLES = ("repflow-android", str(Path.home()))

    def setUp(self):
        self.release = find_release(REPO_ROOT, "2.3.1")

    def _scan(self):
        """`{relative path: number of lines naming the upstream}` over the whole
        release except the manifest, whose provenance record names it on purpose."""
        found = {}
        for path in sorted(self.release.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.release.root).as_posix()
            if rel == "manifest.json":
                continue
            text = path.read_bytes().decode("utf-8", "replace")
            hits = sum(
                1 for line in text.splitlines()
                if any(needle in line for needle in self.NEEDLES)
            )
            if hits:
                found[rel] = hits
        return found

    def test_no_functional_file_names_the_upstream_working_tree(self):
        offenders = [
            rel for rel in self._scan()
            if rel.endswith(self.FUNCTIONAL_SUFFIXES)
        ]
        self.assertEqual(offenders, [], "a script or config resolves into the upstream checkout")

    def test_documentation_occurrences_are_exactly_the_pinned_ones(self):
        self.assertEqual(self._scan(), self.PINNED_PROSE)

    def test_the_manifest_names_the_upstream_only_as_provenance(self):
        upstream = self.release.manifest["upstream"]
        self.assertEqual(set(upstream), {"repository", "tag", "commit"})
        raw = (self.release.root / "manifest.json").read_text()
        for needle in self.NEEDLES:
            for line in raw.splitlines():
                if needle in line:
                    self.assertIn('"repository"', line,
                                  f"manifest names {needle!r} outside the provenance record")

    def test_no_template_names_the_upstream_at_all(self):
        """Templates are authored here, so they have no excuse."""
        for template in self.release.templates():
            text = self.release.read(template["location"]).decode("utf-8", "replace")
            for needle in self.NEEDLES:
                self.assertNotIn(needle, text, template["target_path"])

    def test_release_reader_never_reads_outside_the_release_root(self):
        """`Release.read` resolves inside the release directory for every
        location the manifest names -- no `..` escape, no absolute path."""
        root = self.release.root.resolve()
        for record in self.release.manifest["artifacts"] + self.release.manifest["templates"]:
            resolved = (self.release.root / record["location"]).resolve()
            self.assertTrue(resolved.is_relative_to(root), record["location"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
