#!/usr/bin/env python3
"""Workflow release packages: format, build and safe extraction (`D-Package-Format`).

Checkpoint CP1 of `workflow-manager-packaged-distribution` (plan 5.1): two
builds of one release are byte-identical, members come from the manifest
rather than a directory walk, extraction refuses anything a build could not
have produced and leaves nothing behind when it does, and the SHA256SUMS
writer is the one the Manager's own release assets use. Every release here
is synthetic, built under `$TMPDIR`; the five real releases are not built
(CP4 does that).
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

from workflow_manager import package
from workflow_manager.release import Release, ReleaseIntegrityError

VERSION = "9.8.7"
TOP = f"workflow-{VERSION}"

#: location -> (bytes, executable). Artifacts, then templates.
ARTIFACTS = {
    "payload/scripts/tool.sh": (b"#!/bin/sh\necho hi\n", True),
    "payload/docs/guide.md": (b"# guide\n", False),
    "fixtures/host/evidence.md": (b"evidence\n", False),
}
TEMPLATES = {
    "templates/CLAUDE.md": b"# managed\n",
    "templates/docs/ai-workflow/WORKFLOW_STATE.json": b"{}\n",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_release(root: Path, version: str = VERSION, artifacts=None, templates=None) -> Path:
    """A synthetic release directory with a manifest that verifies."""
    artifacts = ARTIFACTS if artifacts is None else artifacts
    templates = TEMPLATES if templates is None else templates
    root.mkdir(parents=True)
    manifest = {"workflow_version": version,
                "upstream": {"tag": f"workflow-v{version}", "commit": "0" * 40},
                "artifacts": [], "templates": []}
    for location, (data, executable) in artifacts.items():
        path = root / location
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o755 if executable else 0o644)
        manifest["artifacts"].append({
            "target_path": location.split("/", 1)[1], "location": location,
            "sha256": _sha(data), "size": len(data), "executable": executable,
            "category": "distribution"})
    for location, data in templates.items():
        path = root / location
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest["templates"].append({
            "target_path": location.split("/", 1)[1], "location": location,
            "sha256": _sha(data), "size": len(data)})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return root


def _tree(root: Path) -> dict[str, tuple[bytes, bool]]:
    """Every file under `root`: its bytes and executable bit."""
    return {p.relative_to(root).as_posix(): (p.read_bytes(), bool(p.stat().st_mode & 0o111))
            for p in sorted(root.rglob("*")) if p.is_file()}


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wm-package-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class TestDeterministicBuild(_Tmp):
    def test_two_builds_are_byte_identical(self):
        release = make_release(self.tmp / "release")
        first = package.build_package(release, self.tmp / "a")
        second = package.build_package(release, self.tmp / "b")
        for a, b in ((first.archive, second.archive), (first.manifest, second.manifest),
                     (first.sums, second.sums)):
            self.assertEqual(a.read_bytes(), b.read_bytes(), a.name)

    def test_the_three_assets(self):
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "out")
        self.assertEqual(sorted(p.name for p in (self.tmp / "out").iterdir()),
                         ["SHA256SUMS", f"workflow-{VERSION}.manifest.json",
                          f"workflow-{VERSION}.tar.gz"])
        self.assertEqual(built.version, VERSION)
        self.assertEqual(built.manifest.read_bytes(), (release / "manifest.json").read_bytes())
        self.assertEqual(built.sums.read_text(), "".join(
            f"{_sha(p.read_bytes())}  {p.name}\n"
            for p in sorted((built.archive, built.manifest), key=lambda p: p.name)))

    def test_bytecode_and_debris_are_not_packed(self):
        clean = make_release(self.tmp / "clean")
        dirty = make_release(self.tmp / "dirty")
        (dirty / "payload" / "scripts" / "__pycache__").mkdir()
        (dirty / "payload" / "scripts" / "__pycache__" / "tool.cpython-314.pyc").write_bytes(b"\0")
        a = package.build_package(clean, self.tmp / "a")
        b = package.build_package(dirty, self.tmp / "b")
        self.assertEqual(a.archive.read_bytes(), b.archive.read_bytes())

    def test_member_headers(self):
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "out")
        raw = built.archive.read_bytes()
        self.assertEqual(raw[:2], b"\x1f\x8b")
        self.assertEqual(raw[4:8], b"\0\0\0\0", "gzip mtime must be 0")
        self.assertFalse(raw[3] & 0x08, "gzip header must carry no file name")
        with tarfile.open(built.archive, "r:gz") as tar:
            members = tar.getmembers()
        names = [m.name for m in members]
        self.assertEqual(names, sorted(names))
        self.assertEqual(names, [
            TOP, f"{TOP}/fixtures", f"{TOP}/fixtures/host", f"{TOP}/fixtures/host/evidence.md",
            f"{TOP}/manifest.json", f"{TOP}/payload", f"{TOP}/payload/docs",
            f"{TOP}/payload/docs/guide.md", f"{TOP}/payload/scripts",
            f"{TOP}/payload/scripts/tool.sh", f"{TOP}/templates", f"{TOP}/templates/CLAUDE.md",
            f"{TOP}/templates/docs", f"{TOP}/templates/docs/ai-workflow",
            f"{TOP}/templates/docs/ai-workflow/WORKFLOW_STATE.json"])
        for member in members:
            with self.subTest(member=member.name):
                self.assertEqual((member.mtime, member.uid, member.gid, member.uname,
                                  member.gname), (0, 0, 0, "", ""))
                expected = 0o755 if member.isdir() or member.name.endswith(".sh") else 0o644
                self.assertEqual(member.mode, expected)
                self.assertIn(member.type, (tarfile.DIRTYPE, tarfile.REGTYPE))
        self.assertNotIn(b"PaxHeader", gzip.decompress(raw), "every path fits USTAR")

    def test_a_long_path_falls_back_to_pax(self):
        long_location = "payload/" + "/".join(["d" * 60] * 3) + "/file.md"
        artifacts = dict(ARTIFACTS, **{long_location: (b"long\n", False)})
        release = make_release(self.tmp / "release", artifacts=artifacts)
        built = package.build_package(release, self.tmp / "out")
        self.assertIn(b"PaxHeader", gzip.decompress(built.archive.read_bytes()))
        extracted = package.extract_package(built.archive, self.tmp / "x")
        self.assertEqual((extracted.root / long_location).read_bytes(), b"long\n")

    def test_a_release_that_fails_verification_is_refused(self):
        release = make_release(self.tmp / "release")
        (release / "payload" / "docs" / "guide.md").write_bytes(b"edited\n")
        with self.assertRaisesRegex(ReleaseIntegrityError, "digest mismatch"):
            package.build_package(release, self.tmp / "out")
        self.assertFalse((self.tmp / "out").exists())

    def test_an_untracked_file_is_refused(self):
        release = make_release(self.tmp / "release")
        (release / "payload" / "extra.md").write_text("x")
        with self.assertRaisesRegex(ReleaseIntegrityError, "untracked"):
            package.build_package(release, self.tmp / "out")

    def test_a_manifest_location_outside_the_release_is_refused(self):
        release = make_release(self.tmp / "release")
        (self.tmp / "outside.md").write_bytes(b"x")
        manifest = json.loads((release / "manifest.json").read_text())
        manifest["artifacts"].append({
            "target_path": "outside.md", "location": "../outside.md", "sha256": _sha(b"x"),
            "size": 1, "executable": False, "category": "distribution"})
        (release / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ReleaseIntegrityError, "unsafe path"):
            package.build_package(release, self.tmp / "out")

    def test_a_linked_file_is_refused(self):
        release = make_release(self.tmp / "release")
        target = release / "payload" / "docs" / "guide.md"
        real = self.tmp / "real.md"
        real.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(real)
        with self.assertRaisesRegex(ReleaseIntegrityError, "link"):
            package.build_package(release, self.tmp / "out")

    def test_a_directory_without_a_manifest_is_refused(self):
        (self.tmp / "empty").mkdir()
        with self.assertRaisesRegex(ReleaseIntegrityError, "not a release"):
            package.build_package(self.tmp / "empty", self.tmp / "out")


class TestRoundTrip(_Tmp):
    def test_extraction_gives_back_the_release(self):
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "out")
        extracted = package.extract_package(built.archive, self.tmp / "extracted", VERSION)
        self.assertIsInstance(extracted, Release)
        self.assertEqual(extracted.version, VERSION)
        self.assertEqual(extracted.verify(), [])
        self.assertEqual(_tree(extracted.root), _tree(release))
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()),
                         ["extracted", "out", "release"], "no staging directory left behind")

    def test_the_carried_manifest_names_the_requested_version(self):
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "out")
        with self.assertRaisesRegex(ReleaseIntegrityError, "not '1.0.0'"):
            package.extract_package(built.archive, self.tmp / "x", "1.0.0")
        self.assertFalse((self.tmp / "x").exists())

    def test_an_existing_destination_is_refused(self):
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "out")
        (self.tmp / "x").mkdir()
        with self.assertRaises(FileExistsError):
            package.extract_package(built.archive, self.tmp / "x")


def _member(name: str, data: bytes | None = None, *, mode: int | None = None,
            kind: bytes = tarfile.REGTYPE, linkname: str = "") -> tuple[tarfile.TarInfo, bytes | None]:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if data is None and kind == tarfile.REGTYPE else kind
    info.mode = mode if mode is not None else (0o755 if info.type == tarfile.DIRTYPE else 0o644)
    info.size = len(data) if data is not None and info.type == tarfile.REGTYPE else 0
    info.linkname = linkname
    return info, data


class TestSafeExtraction(_Tmp):
    """Each archive here is a good package's member list with one change."""

    def setUp(self):
        super().setUp()
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "good")
        with tarfile.open(built.archive, "r:gz") as tar:
            self.good = [(m, tar.extractfile(m).read() if m.isfile() else None)
                         for m in tar.getmembers()]
        self.dest = self.tmp / "dest"

    def _archive(self, members) -> Path:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for info, data in members:
                tar.addfile(info, io.BytesIO(data) if data is not None else None)
        path = self.tmp / "crafted.tar.gz"
        path.write_bytes(gzip.compress(buffer.getvalue()))
        return path

    def _without(self, name: str):
        return [(m, d) for m, d in self.good if m.name != name]

    def _replacing(self, name: str, member):
        return [member if m.name == name else (m, d) for m, d in self.good]

    def _refused(self, members, pattern: str):
        archive = self._archive(members)
        with self.assertRaisesRegex(ReleaseIntegrityError, pattern):
            package.extract_package(archive, self.dest)
        self.assertFalse(self.dest.exists())
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()),
                         ["crafted.tar.gz", "good", "release"], "nothing left behind")

    def test_the_unchanged_members_extract(self):
        package.extract_package(self._archive(self.good), self.dest)
        self.assertEqual(_tree(self.dest), _tree(self.tmp / "release"))

    def test_a_symlink(self):
        link = _member(f"{TOP}/payload/docs/link.md", kind=tarfile.SYMTYPE,
                       linkname="guide.md")
        self._refused(self.good + [link], "not a regular file")

    def test_a_hard_link(self):
        link = _member(f"{TOP}/payload/docs/link.md", kind=tarfile.LNKTYPE,
                       linkname=f"{TOP}/payload/docs/guide.md")
        self._refused(self.good + [link], "not a regular file")

    def test_a_device_and_a_fifo(self):
        for kind in (tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                self._refused(self.good + [_member(f"{TOP}/payload/dev", kind=kind)],
                              "not a regular file")

    def test_a_dot_dot_component(self):
        self._refused(self.good + [_member(f"{TOP}/../escape.md", b"x")], "unsafe path")
        self._refused(self.good + [_member(f"{TOP}/payload/../../escape.md", b"x")],
                      "unsafe path")

    def test_an_absolute_path(self):
        self._refused(self.good + [_member("/tmp/escape.md", b"x")], "unsafe path")

    def test_a_member_outside_the_top_directory(self):
        self._refused(self.good + [_member("elsewhere/file.md", b"x")], "outside the top-level")

    def test_a_wrong_top_directory(self):
        renamed = []
        for member, data in self.good:
            copy = _member(member.name.replace(TOP, "workflow-1.0.0", 1), data,
                           mode=member.mode)
            renamed.append(copy)
        self._refused(renamed, "top-level directory is workflow-1.0.0/")

    def test_a_duplicate_member(self):
        name = f"{TOP}/payload/docs/guide.md"
        duplicate = next((m, d) for m, d in self.good if m.name == name)
        self._refused(self.good + [duplicate], "duplicate member")

    def test_an_extra_file(self):
        self._refused(self.good + [_member(f"{TOP}/payload/extra.md", b"x")],
                      r"extra \['payload/extra.md'\]")

    def test_an_extra_directory(self):
        self._refused(self.good + [_member(f"{TOP}/payload/empty")], "unexpected directories")

    def test_a_missing_file(self):
        self._refused(self._without(f"{TOP}/payload/docs/guide.md"),
                      r"missing \['payload/docs/guide.md'\]")

    def test_a_missing_manifest(self):
        self._refused(self._without(f"{TOP}/manifest.json"), "carries no manifest.json")

    def test_a_wrong_digest(self):
        name = f"{TOP}/payload/docs/guide.md"
        self._refused(self._replacing(name, _member(name, b"# gUide\n")),
                      "does not match its manifest entry")

    def test_a_wrong_mode(self):
        name = f"{TOP}/payload/scripts/tool.sh"
        data = ARTIFACTS["payload/scripts/tool.sh"][0]
        self._refused(self._replacing(name, _member(name, data, mode=0o644)), "has mode 644")
        name = f"{TOP}/payload/docs/guide.md"
        data = ARTIFACTS["payload/docs/guide.md"][0]
        self._refused(self._replacing(name, _member(name, data, mode=0o755)), "has mode 755")
        self._refused(self._replacing(name, _member(name, data, mode=0o4644)), "has mode 4644")

    def test_a_malformed_manifest(self):
        name = f"{TOP}/manifest.json"
        self._refused(self._replacing(name, _member(name, b"not json")), "malformed manifest")

    def test_an_empty_archive(self):
        self._refused([], "is empty")

    def test_a_corrupt_archive(self):
        path = self.tmp / "crafted.tar.gz"
        path.write_bytes(b"\x1f\x8b not really gzip")
        with self.assertRaisesRegex(ReleaseIntegrityError, "not a readable package"):
            package.extract_package(path, self.dest)
        self.assertFalse(self.dest.exists())

    def test_an_oversized_member(self):
        original = package.MAX_UNPACKED_BYTES
        package.MAX_UNPACKED_BYTES = 16
        self.addCleanup(setattr, package, "MAX_UNPACKED_BYTES", original)
        self._refused(self.good, "unpacks to more than 16 bytes")


class TestSha256Sums(_Tmp):
    def test_the_format(self):
        (self.tmp / "b.tar.gz").write_bytes(b"archive")
        (self.tmp / "a.json").write_bytes(b"{}")
        text = package.sha256sums_text([self.tmp / "b.tar.gz", self.tmp / "a.json"])
        self.assertEqual(text, f"{_sha(b'{}')}  a.json\n{_sha(b'archive')}  b.tar.gz\n")

    def test_a_repeated_name_is_refused(self):
        (self.tmp / "d").mkdir()
        (self.tmp / "x").write_bytes(b"1")
        (self.tmp / "d" / "x").write_bytes(b"2")
        with self.assertRaises(ValueError):
            package.sha256sums_text([self.tmp / "x", self.tmp / "d" / "x"])

    def test_sha256sum_accepts_a_package(self):
        release = make_release(self.tmp / "release")
        built = package.build_package(release, self.tmp / "out")
        try:
            proc = subprocess.run(["sha256sum", "--check", "--strict", built.sums.name],
                                  cwd=built.sums.parent, capture_output=True, text=True,
                                  timeout=60)
        except FileNotFoundError:
            self.skipTest("sha256sum is not installed")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_manager_release_tool_uses_the_shared_writer(self):
        spec = importlib.util.spec_from_file_location(
            "workflow_manager_package_tool", REPO_ROOT / "tools" / "release" / "package.py")
        tool = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = tool
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(tool)
        self.assertIs(tool.workflow_package, package)
        self.assertEqual(tool.SUMS_NAME, package.SUMS_NAME)
        (self.tmp / "x.whl").write_bytes(b"wheel")
        self.assertEqual(tool.sha256sums_text(self.tmp),
                         package.sha256sums_text([self.tmp / "x.whl"]))


if __name__ == "__main__":
    unittest.main()
