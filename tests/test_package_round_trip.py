#!/usr/bin/env python3
"""The five Workflow release packages reproduce the committed releases (plan 6).

Checkpoint CP4 of `workflow-manager-packaged-distribution`. Every package is
built from the base's committed tree, `git archive ec38979
distribution/workflow` -- never the working tree, which may carry untracked
`__pycache__/` -- and must extract to exactly that release: the same file
set, bytes and modes (INV-1). Its digests must be the pins the Manager ships
(`D-Pins`), and every committed release must be pinned, so no real release is
installed unpinned from CP4 on (`TestCheckoutReleasesArePinned`, 5.5).

`tools/workflow_packages.py`, the tool that built the pins, is tested here
too, on synthetic releases. This module is deleted in CP6 with
`distribution/`; the evidence stays in `docs/MIGRATION.md`, and what stays
permanent is `test_published_packages.py`'s `TestPinnedPackagesVerify`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from support import REPO_ROOT

from workflow_manager import package, source

#: The base commit whose committed `distribution/workflow/` the pins bind.
BASE_COMMIT = "ec389798dd8b5ef2d5da5ea6d654d10bc81784da"
RELEASES = ("2.3.1", "2.4.0", "2.5.0", "2.5.1", "2.6.0")
TOOL = REPO_ROOT / "tools" / "workflow_packages.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("workflow_packages_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through it
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _files(root: Path) -> dict[str, tuple[bytes, bool]]:
    """Every regular file under `root`: its bytes and executable bit. Written
    independently of the tool's own comparison, so the two cannot share a
    blind spot."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            if os.path.islink(os.path.join(dirpath, name)):
                raise AssertionError(f"{dirpath}/{name} is a link")
        for name in filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise AssertionError(f"{path} is not a regular file")
            found[path.relative_to(root).as_posix()] = (
                path.read_bytes(), bool(info.st_mode & stat.S_IXUSR))
    return found


class _Committed(unittest.TestCase):
    """The base's committed releases, extracted once per class."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="package-round-trip-")
        cls.tmp = Path(cls._tmp.name)
        cls.committed = tool.extract_committed(BASE_COMMIT, cls.tmp / "committed")
        cls.pins = source.load_pins(source.PINS_PATH)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestPackagesReproduceTheDistributionTree(_Committed):

    def test_the_committed_tree_holds_the_five_releases(self):
        self.assertEqual(sorted(tool.release_dirs(self.committed)), list(RELEASES))
        self.assertFalse(list(self.committed.rglob("__pycache__")),
                         "git archive must not carry the working tree's debris")

    def test_each_package_extracts_to_exactly_its_committed_release(self):
        for version in RELEASES:
            with self.subTest(version=version):
                release_dir = self.committed / version
                out = self.tmp / "round-trip" / version
                built = package.build_package(release_dir, out)
                extracted = package.extract_package(built.archive, out / "tree", version)
                want, got = _files(release_dir), _files(extracted.root)
                self.assertEqual(sorted(got), sorted(want))
                for path, (data, executable) in want.items():
                    self.assertEqual(got[path][0], data, path)
                    self.assertEqual(got[path][1], executable, f"{path}'s executable bit")

    def test_two_builds_are_byte_identical(self):
        for version in RELEASES:
            with self.subTest(version=version):
                first = package.build_package(self.committed / version, self.tmp / "a" / version)
                second = package.build_package(self.committed / version, self.tmp / "b" / version)
                for a, b in ((first.archive, second.archive), (first.manifest, second.manifest),
                             (first.sums, second.sums)):
                    self.assertEqual(a.read_bytes(), b.read_bytes(), a.name)

    def test_the_packages_are_the_pinned_ones(self):
        """The shipped pins are exactly these packages' digests, and the tool
        that wrote them reproduces the pin file byte for byte."""
        out = self.tmp / "pinned"
        evidence = tool.build_all(self.committed, out)
        self.assertEqual([row.version for row in evidence], list(RELEASES))
        for row in evidence:
            with self.subTest(version=row.version):
                pin = self.pins.get(row.version)
                self.assertEqual(pin.sha256, row.archive_sha256)
                self.assertEqual(pin.manifest_sha256, row.manifest_sha256)
                sums = (out / row.version / package.SUMS_NAME).read_text()
                self.assertIn(f"{pin.sha256}  {pin.archive}\n", sums)
                self.assertIn(f"{pin.manifest_sha256}  "
                              f"{package.manifest_asset_name(row.version)}\n", sums)
        tool.write_or_check_pins(evidence, source.PINS_PATH, check=True)
        self.assertEqual(self.pins.repository, "RodrigoFAbreu/workflow")


class TestCheckoutReleasesArePinned(_Committed):
    """Every committed release is published: the checkout fallback (5.5) is
    dead code for this repository's own releases from CP4 on."""

    def test_every_committed_release_is_pinned_and_matches_its_pin(self):
        committed = tool.release_dirs(self.committed)
        self.assertEqual(sorted(committed), self.pins.versions())
        for version, release_dir in committed.items():
            with self.subTest(version=version):
                pin = self.pins.get(version)
                self.assertIsNotNone(pin, f"{version} is committed but not pinned")
                self.assertEqual(package.file_sha256(release_dir / package.MANIFEST_NAME),
                                 pin.manifest_sha256)

    def test_the_working_trees_releases_are_the_committed_ones(self):
        """The checkout's own `distribution/workflow/<v>/manifest.json` -- the
        file a local-directory install binds to its pin -- is the committed
        one, so no fallback install of it can be unpinned."""
        for version in RELEASES:
            with self.subTest(version=version):
                manifest = REPO_ROOT / "distribution" / "workflow" / version / "manifest.json"
                self.assertEqual(package.file_sha256(manifest),
                                 self.pins.get(version).manifest_sha256)


# ---------------------------------------------------------------------------
# tools/workflow_packages.py, on synthetic releases
# ---------------------------------------------------------------------------


def _write_release(root: Path, version: str, extra: dict[str, bytes] | None = None) -> Path:
    """A synthetic release that verifies: one script, one doc, one template.
    `extra` files are written but not listed in the manifest."""
    directory = root / version
    manifest = {"workflow_version": version,
                "upstream": {"tag": f"workflow-v{version}", "commit": "0" * 40},
                "artifacts": [], "templates": []}
    for location, data, executable in (
            ("payload/scripts/run.sh", b"#!/bin/sh\necho run\n", True),
            ("payload/docs/guide.md", f"# guide {version}\n".encode(), False)):
        path = directory / location
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o755 if executable else 0o644)
        manifest["artifacts"].append({
            "target_path": location.split("/", 1)[1], "location": location,
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "executable": executable, "category": "distribution"})
    template = b"# managed\n"
    (directory / "templates").mkdir()
    (directory / "templates" / "CLAUDE.md").write_bytes(template)
    manifest["templates"].append({
        "target_path": "CLAUDE.md", "location": "templates/CLAUDE.md",
        "sha256": hashlib.sha256(template).hexdigest(), "size": len(template)})
    for location, data in (extra or {}).items():
        (directory / location).parent.mkdir(parents=True, exist_ok=True)
        (directory / location).write_bytes(data)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return directory


class TestWorkflowPackagesTool(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="workflow-packages-tool-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.releases = self.tmp / "releases"
        self.releases.mkdir()

    def _release(self, version, **kwargs):
        return _write_release(self.releases, version, **kwargs)

    def _pins_file(self) -> Path:
        path = self.tmp / "published_releases.json"
        path.write_text(json.dumps({"schema_version": 1, "repository": "o/workflow",
                                    "releases": {}}))
        return path

    def run_main(self, *argv, environ=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), \
                mock.patch.dict(os.environ, environ or {}):
            code = tool.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_build_writes_the_pins_and_the_evidence(self):
        self._release("1.0.0")
        self._release("1.1.0")
        pins = self._pins_file()
        code, out, err = self.run_main("build", "--from", str(self.releases), "--out",
                                       str(self.tmp / "out"), "--pins", str(pins))
        self.assertEqual(code, 0, err)
        loaded = source.load_pins(pins)
        self.assertEqual(loaded.versions(), ["1.0.0", "1.1.0"])
        self.assertEqual(loaded.repository, "o/workflow", "the repository is kept")
        for version in ("1.0.0", "1.1.0"):
            archive = self.tmp / "out" / version / package.archive_name(version)
            self.assertEqual(loaded.get(version).sha256, package.file_sha256(archive))
            self.assertIn(f"| {version} | 4 | `{loaded.get(version).sha256}` |", out)
        self.assertTrue(out.rstrip().endswith("| identical |"))
        self.assertEqual(pins.read_text(), tool.pins_text(json.loads(pins.read_text())))
        # --check agrees with what was written, and refuses a changed pin.
        code, _, err = self.run_main("build", "--from", str(self.releases), "--out",
                                     str(self.tmp / "again"), "--pins", str(pins), "--check")
        self.assertEqual(code, 0, err)
        document = json.loads(pins.read_text())
        document["releases"]["1.0.0"]["sha256"] = "0" * 64
        pins.write_text(tool.pins_text(document))
        code, _, err = self.run_main("build", "--from", str(self.releases), "--out",
                                     str(self.tmp / "third"), "--pins", str(pins), "--check")
        self.assertEqual(code, 1)
        self.assertIn("does not pin the built packages", err)
        self.assertEqual(json.loads(pins.read_text()), document, "--check never writes")

    def test_prime_fills_the_cache_through_the_pin_checks(self):
        self._release("1.0.0")
        pins = self._pins_file()
        cache = self.tmp / "cache"
        code, _, err = self.run_main(
            "build", "--from", str(self.releases), "--out", str(self.tmp / "out"),
            "--pins", str(pins), "--prime", environ={source.CACHE_ENV: str(cache)})
        self.assertEqual(code, 0, err)
        self.assertIn(f"primed {cache}", err)
        primed = source.ReleaseCache(cache, None, source.load_pins(pins))
        self.assertTrue(primed.cached("1.0.0"))

    def test_a_file_the_manifest_does_not_list_fails_the_round_trip(self):
        """A package holds only what the manifest names. `Release.verify()`
        tolerates `__pycache__/`, so a working tree's debris builds, but the
        package cannot reproduce that tree: the round trip refuses it, and
        the committed tree (`--commit`) never carries it (INV-1)."""
        self._release("1.0.0", extra={"payload/scripts/__pycache__/run.cpython-312.pyc": b"x"})
        code, _, err = self.run_main("build", "--from", str(self.releases), "--out",
                                     str(self.tmp / "out"))
        self.assertEqual(code, 1)
        self.assertIn("does not round-trip: missing payload/scripts/__pycache__", err)

    def test_a_mode_difference_fails_the_round_trip(self):
        directory = self._release("1.0.0")
        os.chmod(directory / "payload" / "docs" / "guide.md", 0o600)
        problems = tool.round_trip_differences(directory, self.tmp / "missing")
        self.assertTrue(problems)
        extracted = self.tmp / "copy"
        shutil.copytree(directory, extracted)
        os.chmod(extracted / "payload" / "docs" / "guide.md", 0o644)
        self.assertEqual(tool.round_trip_differences(directory, extracted),
                         ["payload/docs/guide.md: mode 644 is not 600"])

    def test_an_existing_package_directory_is_refused(self):
        self._release("1.0.0")
        (self.tmp / "out" / "1.0.0").mkdir(parents=True)
        code, _, err = self.run_main("build", "--from", str(self.releases), "--out",
                                     str(self.tmp / "out"))
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_usage_errors_exit_2(self):
        for argv in (["build", "--out", str(self.tmp)],
                     ["build", "--from", str(self.tmp), "--commit", "HEAD", "--out", "x"],
                     ["build", "--from", str(self.tmp), "--out", "x", "--check"],
                     ["build", "--from", str(self.tmp), "--out", "x", "--prime"]):
            with self.subTest(argv=argv):
                proc = subprocess.run([sys.executable, str(TOOL), *argv], capture_output=True,
                                      text=True, timeout=60, cwd=self.tmp)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("usage error", proc.stderr)

    def test_an_unknown_commit_is_a_build_failure(self):
        code, _, err = self.run_main("build", "--commit", "0" * 40, "--out",
                                     str(self.tmp / "out"))
        self.assertEqual(code, 1)
        self.assertIn("git archive", err)


if __name__ == "__main__":
    unittest.main()
