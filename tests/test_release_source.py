#!/usr/bin/env python3
"""Workflow release packages and where they come from (plan 5.1-5.4).

Checkpoint CP1 of `workflow-manager-packaged-distribution` (5.1,
`D-Package-Format`): two builds of one release are byte-identical, members
come from the manifest rather than a directory walk, extraction refuses
anything a build could not have produced and leaves nothing behind when it
does, and the SHA256SUMS writer is the one the Manager's own release assets
use.

Checkpoint CP2 (5.2-5.4, `D-Release-Source`, `D-Pins`, `D-Release-Cache`,
and 5.5's `local_release`): a package is accepted only when it matches its
pin and the published SHA256SUMS; the cache re-verifies every hit and hands
out private snapshots checked under its lock, so bytes changed after a check
never reach a target; a local directory holding a published version must
match its pin. Sources are a local `http.server` on 127.0.0.1, `file://` and
local directories, each test with its own temporary cache: no real network.

Every release here is synthetic, built under `$TMPDIR`; the five real
releases are not built (CP4 does that).
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import gzip
import hashlib
import http.server
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from support import REPO_ROOT

from workflow_manager import install, package, source
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


# == CP2: source, pins and cache (plan 5.2-5.4) =============================

#: Templates `install.bootstrap` needs, so a synthetic release can be installed.
INSTALL_TEMPLATES = {
    "templates/docs/ai-workflow/WORKFLOW_STATE.json": b"{}\n",
    "templates/docs/ai-workflow/WORKFLOW_CONFIG.json": b"{}\n",
    "templates/docs/ACTIVE_MILESTONE.md": b"# active\n",
    "templates/.gitignore.workflow-fragment": b".ai-review/\n",
    "templates/CLAUDE.md": b"# managed\n<!-- workflow-manager:end -->\n",
}
ALTERED = b"#!/bin/sh\necho ALTERED-BYTES\n"


def _pins(*packages: package.Package, repository: str = "example/workflow") -> source.Pins:
    return source.Pins(repository=repository, releases={
        p.version: source.Pin(version=p.version, archive=p.archive.name,
                              sha256=package.file_sha256(p.archive),
                              manifest_sha256=package.file_sha256(p.manifest))
        for p in packages})


def _alter_consistently(tree: Path) -> None:
    """Rewrite one payload file and the manifest to match it, so the tree
    still passes `Release.verify()` but no longer matches its pin."""
    (tree / "payload/scripts/tool.sh").write_bytes(ALTERED)
    manifest = json.loads((tree / "manifest.json").read_text())
    for record in manifest["artifacts"]:
        if record["location"] == "payload/scripts/tool.sh":
            record["sha256"] = _sha(ALTERED)
            record["size"] = len(ALTERED)
    (tree / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    assert Release(tree).verify() == []


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the source directory, plus `/redirect/<n>/<path>`, which
    redirects `n` times before landing on `<path>`."""

    def do_GET(self):
        parts = self.path.split("/")
        if len(parts) > 3 and parts[1] == "redirect":
            left = int(parts[2])
            rest = "/".join(parts[3:])
            self.send_response(302)
            self.send_header("Location",
                             f"/redirect/{left - 1}/{rest}" if left > 1 else f"/{rest}")
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, *args):
        pass


class _SourceTest(_Tmp):
    """A published synthetic release in a local source directory, a local HTTP
    server over it, and a temporary cache of this test's own."""

    def setUp(self):
        super().setUp()
        cache = self.tmp / "cache"
        env = mock.patch.dict(os.environ, {source.CACHE_ENV: str(cache)})
        env.start()
        self.addCleanup(env.stop)
        # Every test here reads its own cache, never the machine's shared one.
        self.assertEqual(source.cache_root(), cache)
        self.cache_dir = cache
        self.release_dir = make_release(self.tmp / "release", templates=INSTALL_TEMPLATES)
        self.served = self.tmp / "served"
        self.pkg = package.build_package(self.release_dir, self.served / VERSION)
        self.pins = _pins(self.pkg)
        self.pristine = _tree(self.release_dir)

    def serve(self) -> str:
        """Start the local server; returns its URL template."""
        handler = functools.partial(_Handler, directory=str(self.served))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
        self.addCleanup(stop)
        self.stop_server = stop
        return f"http://127.0.0.1:{server.server_address[1]}/{{version}}/"

    def cache(self, source_value: str | None = None, pins=None) -> source.ReleaseCache:
        return source.ReleaseCache(
            source.cache_root(), source.ReleaseSource(source_value or str(self.served)),
            pins or self.pins)

    def counting(self, cache: source.ReleaseCache) -> list[str]:
        """Record every asset `cache` fetches."""
        fetched = []
        real = cache.source.fetch

        def fetch(version, name, dest):
            fetched.append(name)
            return real(version, name, dest)
        cache.source.fetch = fetch
        return fetched

    def offline(self, cache: source.ReleaseCache) -> None:
        def fetch(version, name, dest):
            raise source.ReleaseUnavailableError(f"offline: {name}")
        cache.source.fetch = fetch

    def resolved(self, cache: source.ReleaseCache, version: str = VERSION) -> Release:
        release = cache.resolve(version)
        self.addCleanup(release.close)
        return release

    def assertPristine(self, release: Release) -> None:
        self.assertEqual(_tree(release.root), self.pristine)


class TestPins(_Tmp):
    def write(self, data) -> Path:
        path = self.tmp / "pins.json"
        path.write_text(json.dumps(data))
        return path

    def good(self) -> dict:
        return {"schema_version": 1, "repository": "example/workflow",
                "releases": {"1.2.3": {"archive": "workflow-1.2.3.tar.gz",
                                       "sha256": "a" * 64, "manifest_sha256": "b" * 64}}}

    def test_the_shipped_pin_file_loads(self):
        pins = source.load_pins()
        self.assertEqual(pins.repository, "RodrigoFAbreu/workflow")
        self.assertEqual(source.PINS_PATH.parent, Path(source.__file__).parent)

    def test_the_pin_file_ships_as_package_data(self):
        text = (REPO_ROOT / "pyproject.toml").read_text()
        self.assertIn("[tool.setuptools.package-data]", text)
        self.assertIn('workflow_manager = ["published_releases.json"]', text)

    def test_a_well_formed_pin_file(self):
        pins = source.load_pins(self.write(self.good()))
        self.assertEqual(pins.versions(), ["1.2.3"])
        self.assertEqual(pins.source_record("1.2.3"), {
            "kind": "package", "repository": "example/workflow",
            "archive": "workflow-1.2.3.tar.gz", "sha256": "a" * 64})
        self.assertIsNone(pins.get("9.9.9"))

    def test_versions_are_ordered_numerically(self):
        data = self.good()
        entry = data["releases"].pop("1.2.3")
        for version in ("2.10.0", "2.9.0"):
            data["releases"][version] = dict(entry, archive=package.archive_name(version))
        self.assertEqual(source.load_pins(self.write(data)).versions(), ["2.9.0", "2.10.0"])

    def test_malformed_pin_files_are_refused(self):
        for name, change in (
                ("schema", lambda d: d.update(schema_version=2)),
                ("repository", lambda d: d.update(repository="")),
                ("archive", lambda d: d["releases"]["1.2.3"].update(archive="x.tar.gz")),
                ("digest", lambda d: d["releases"]["1.2.3"].update(sha256="A" * 64)),
                ("short", lambda d: d["releases"]["1.2.3"].update(manifest_sha256="b")),
                ("missing", lambda d: d["releases"]["1.2.3"].pop("manifest_sha256")),
                ("releases", lambda d: d.update(releases=[]))):
            with self.subTest(name):
                data = self.good()
                change(data)
                with self.assertRaises(ReleaseIntegrityError):
                    source.load_pins(self.write(data))
        (self.tmp / "pins.json").write_text("{")
        with self.assertRaises(ReleaseIntegrityError):
            source.load_pins(self.tmp / "pins.json")


class TestSourceSelection(unittest.TestCase):
    def test_precedence(self):
        env = {source.SOURCE_ENV: "/from/env"}
        self.assertEqual(source.ReleaseSource.select("/opt", env).value, "/opt")
        self.assertEqual(source.ReleaseSource.select(None, env).value, "/from/env")
        self.assertEqual(source.ReleaseSource.select(None, {}).value, source.DEFAULT_SOURCE)

    def test_the_default_names_the_workflow_repository(self):
        self.assertEqual(
            source.ReleaseSource(source.DEFAULT_SOURCE).location("2.6.0", "SHA256SUMS"),
            "https://github.com/RodrigoFAbreu/workflow/releases/download/v2.6.0/SHA256SUMS")

    def test_a_local_directory(self):
        found = source.ReleaseSource("/srv/releases").location("2.6.0", "SHA256SUMS")
        self.assertEqual(found, "/srv/releases/2.6.0/SHA256SUMS")

    def test_accepted_schemes(self):
        for value in ("https://example.com/{version}/", "file:///srv/{version}/",
                      "http://127.0.0.1:8000/{version}/", "http://localhost/{version}",
                      "http://[::1]:9/{version}/"):
            with self.subTest(value):
                source.ReleaseSource(value)

    def test_refused_templates(self):
        for value in ("http://example.com/{version}/", "http://10.0.0.1/{version}/",
                      "ftp://example.com/{version}/", "https://example.com/latest/"):
            with self.subTest(value), self.assertRaises(source.ReleaseUnavailableError):
                source.ReleaseSource(value)

    def test_cache_precedence(self):
        env = {source.CACHE_ENV: "/env-cache", "XDG_CACHE_HOME": "/xdg"}
        self.assertEqual(source.cache_root("/opt", env), Path("/opt"))
        self.assertEqual(source.cache_root(None, env), Path("/env-cache"))
        self.assertEqual(source.cache_root(None, {"XDG_CACHE_HOME": "/xdg"}),
                         Path("/xdg/workflow-manager/releases"))
        self.assertEqual(source.cache_root(None, {}),
                         Path.home() / ".cache" / "workflow-manager" / "releases")

    def test_new_errors_exit_through_install_error(self):
        self.assertTrue(issubclass(source.ReleaseNotPublishedError, install.InstallError))
        self.assertTrue(issubclass(source.ReleaseUnavailableError, install.InstallError))


class TestFetch(_SourceTest):
    def test_over_http(self):
        cache = self.cache(self.serve())
        self.assertPristine(self.resolved(cache))

    def test_over_file_urls(self):
        cache = self.cache(self.served.as_uri() + "/{version}/")
        self.assertPristine(self.resolved(cache))

    def test_from_a_local_directory(self):
        self.assertPristine(self.resolved(self.cache()))

    def test_sums_first_then_the_archive(self):
        cache = self.cache()
        fetched = self.counting(cache)
        cache.ensure(VERSION)
        self.assertEqual(fetched[:2], [package.SUMS_NAME, self.pkg.archive.name])

    def test_redirects_are_followed(self):
        url = self.serve().replace("/{version}/", "/redirect/5/{version}/")
        self.assertPristine(self.resolved(self.cache(url)))

    def test_more_than_five_redirects_are_refused(self):
        url = self.serve().replace("/{version}/", "/redirect/6/{version}/")
        with self.assertRaises(source.ReleaseUnavailableError):
            self.cache(url).ensure(VERSION)
        self.assertFalse((self.cache_dir / VERSION).exists())

    def test_a_redirect_from_https_to_http_is_refused(self):
        handler = source._RedirectHandler()
        request = urllib.request.Request("https://example.com/a")
        for target in ("http://127.0.0.1/a", "http://example.com/a"):
            with self.subTest(target), self.assertRaises(source.ReleaseUnavailableError):
                handler.redirect_request(request, None, 302, "Found", {}, target)
        self.assertIsNotNone(handler.redirect_request(
            request, None, 302, "Found", {}, "https://objects.example.net/a"))

    def test_a_redirect_to_plain_http_off_loopback_is_refused(self):
        handler = source._RedirectHandler()
        request = urllib.request.Request("http://127.0.0.1/a")
        with self.assertRaises(source.ReleaseUnavailableError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://example.com/a")

    def test_a_missing_asset_is_unavailable(self):
        with self.assertRaises(source.ReleaseUnavailableError):
            self.cache(self.serve().replace("/{version}/", "/nowhere/{version}/")).ensure(VERSION)

    def test_the_size_cap(self):
        for where in (None, self.serve()):
            with self.subTest(where or "directory"), \
                    mock.patch.object(source, "MAX_ASSET_BYTES", 100), \
                    self.assertRaises(source.ReleaseUnavailableError):
                self.cache(where).ensure(VERSION)
        self.assertFalse((self.cache_dir / VERSION).exists())
        self.assertEqual([p.name for p in self.cache_dir.iterdir()], [f"{VERSION}.lock"])


class TestPinChecks(_SourceTest):
    def republish(self, archive: bytes | None = None, sums: str | None = None,
                  manifest: bytes | None = None) -> None:
        folder = self.served / VERSION
        if archive is not None:
            self.pkg.archive.write_bytes(archive)
        if manifest is not None:
            self.pkg.manifest.write_bytes(manifest)
        if sums is None:
            sums = package.sha256sums_text([self.pkg.archive, self.pkg.manifest])
        (folder / package.SUMS_NAME).write_text(sums)

    def other_archive(self) -> bytes:
        other = make_release(self.tmp / "other", templates=dict(INSTALL_TEMPLATES, **{
            "templates/docs/ACTIVE_MILESTONE.md": b"# other\n"}))
        return package.build_package(other, self.tmp / "other-out").archive.read_bytes()

    def assertRefused(self):
        with self.assertRaises(ReleaseIntegrityError):
            self.cache().ensure(VERSION)
        self.assertFalse((self.cache_dir / VERSION).exists())
        self.assertEqual([p.name for p in self.cache_dir.iterdir()], [f"{VERSION}.lock"])

    def test_a_republished_archive_and_sums_that_agree(self):
        self.republish(archive=self.other_archive())
        self.assertRefused()

    def test_a_sums_file_that_disagrees_with_the_pin(self):
        self.republish(sums=f"{'0' * 64}  {self.pkg.archive.name}\n"
                            f"{self.pins.get(VERSION).manifest_sha256}  {self.pkg.manifest.name}\n")
        self.assertRefused()

    def test_a_sums_file_without_the_archive(self):
        self.republish(sums=f"{self.pins.get(VERSION).manifest_sha256}  {self.pkg.manifest.name}\n")
        self.assertRefused()

    def test_a_malformed_sums_file(self):
        self.republish(sums="not a sums line\n")
        self.assertRefused()

    def test_a_manifest_asset_that_differs_from_the_pin(self):
        self.republish(manifest=b"{}\n")
        self.assertRefused()

    def test_an_archive_carrying_another_version(self):
        other = make_release(self.tmp / "other", version="1.0.0", templates=INSTALL_TEMPLATES)
        built = package.build_package(other, self.tmp / "other-out")
        folder = self.served / VERSION
        shutil.rmtree(folder)
        folder.mkdir()
        shutil.copyfile(built.archive, folder / self.pkg.archive.name)
        shutil.copyfile(built.manifest, folder / self.pkg.manifest.name)
        pins = _pins(package.Package(VERSION, folder / self.pkg.archive.name,
                                     folder / self.pkg.manifest.name, folder / "SHA256SUMS"))
        (folder / package.SUMS_NAME).write_text(package.sha256sums_text(
            [folder / self.pkg.archive.name, folder / self.pkg.manifest.name]))
        with self.assertRaises(ReleaseIntegrityError):
            self.cache(pins=pins).ensure(VERSION)
        self.assertFalse((self.cache_dir / VERSION).exists())

    def test_an_unwritable_cache_is_unavailable(self):
        self.cache_dir.write_text("not a directory")
        with self.assertRaises(source.ReleaseUnavailableError):
            self.cache().ensure(VERSION)

    def test_an_unpinned_version_is_not_published(self):
        with self.assertRaises(source.ReleaseNotPublishedError):
            self.cache().resolve("1.0.0")
        with self.assertRaises(source.ReleaseNotPublishedError):
            self.cache().ensure("1.0.0")
        self.assertFalse(self.cache_dir.exists())


class TestCache(_SourceTest):
    def test_an_entry_holds_the_assets_the_tree_and_complete(self):
        entry = self.cache().ensure(VERSION)
        self.assertEqual(entry, self.cache_dir / VERSION)
        self.assertEqual(sorted(p.name for p in entry.iterdir()), sorted(
            [self.pkg.archive.name, self.pkg.manifest.name, package.SUMS_NAME,
             "tree", "complete"]))
        self.assertEqual((entry / "complete").read_text().strip(),
                         self.pins.get(VERSION).sha256)
        self.assertEqual(_tree(entry / "tree"), self.pristine)
        self.assertTrue(self.cache().cached(VERSION))

    def test_ensure_takes_no_snapshot(self):
        cache = self.cache()
        with mock.patch.object(source, "_copy_snapshot") as copy:
            cache.ensure(VERSION)
            cache.ensure(VERSION)
        copy.assert_not_called()

    def test_an_offline_hit(self):
        self.cache().ensure(VERSION)
        cache = self.cache()
        self.offline(cache)
        self.assertPristine(self.resolved(cache))
        cache.ensure(VERSION)

    def test_an_offline_miss(self):
        cache = self.cache()
        self.offline(cache)
        with self.assertRaises(source.ReleaseUnavailableError):
            cache.resolve(VERSION)
        with self.assertRaises(source.ReleaseUnavailableError):
            cache.ensure(VERSION)

    def test_a_stopped_server_is_an_offline_miss(self):
        cache = self.cache(self.serve())
        self.stop_server()
        with self.assertRaises(source.ReleaseUnavailableError):
            cache.ensure(VERSION)

    def broken_entries(self):
        """Ways a cache entry can stop matching its pin."""
        def tree_altered_consistently(entry):
            _alter_consistently(entry / "tree")

        def complete_names_another_digest(entry):
            (entry / "complete").write_text("0" * 64 + "\n")

        def complete_missing(entry):
            (entry / "complete").unlink()

        def archive_altered(entry):
            (entry / self.pkg.archive.name).write_bytes(b"not the archive")

        def payload_file_damaged(entry):
            (entry / "tree/payload/docs/guide.md").write_bytes(b"damaged\n")

        def untracked_file(entry):
            (entry / "tree/payload/extra.md").write_bytes(b"extra\n")

        def manifest_names_another_version(entry):
            path = entry / "tree/manifest.json"
            path.write_text(path.read_text().replace(f'"{VERSION}"', '"1.0.0"'))

        return (tree_altered_consistently, complete_names_another_digest, complete_missing,
                archive_altered, payload_file_damaged, untracked_file,
                manifest_names_another_version)

    def test_a_broken_entry_is_discarded_and_refetched(self):
        for breakage in self.broken_entries():
            with self.subTest(breakage.__name__):
                entry = self.cache().ensure(VERSION)
                breakage(entry)
                self.assertFalse(self.cache().cached(VERSION))
                cache = self.cache()
                fetched = self.counting(cache)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    release = self.resolved(cache)
                self.assertPristine(release)
                self.assertIn("discarding cache entry", stderr.getvalue())
                self.assertIn(self.pkg.archive.name, fetched)
                self.assertTrue(self.cache().cached(VERSION))

    def test_a_broken_entry_offline_is_unavailable(self):
        for breakage in self.broken_entries():
            with self.subTest(breakage.__name__):
                entry = self.cache().ensure(VERSION)
                breakage(entry)
                cache = self.cache()
                self.offline(cache)
                with contextlib.redirect_stderr(io.StringIO()), \
                        self.assertRaises(source.ReleaseUnavailableError):
                    cache.resolve(VERSION)
                self.assertFalse(entry.exists())


class TestSnapshots(_SourceTest):
    def test_resolve_returns_a_private_snapshot(self):
        release = self.resolved(self.cache())
        self.assertIsInstance(release, source.SnapshotRelease)
        self.assertFalse(release.root.is_relative_to(self.cache_dir))
        self.assertEqual(release.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(release.version, VERSION)
        self.assertEqual(release.source, self.pins.source_record(VERSION))
        self.assertPristine(release)

    def test_each_resolve_has_its_own_snapshot(self):
        cache = self.cache()
        first, second = self.resolved(cache), self.resolved(cache)
        self.assertNotEqual(first.root, second.root)

    def test_the_snapshot_holds_only_manifest_files(self):
        entry = self.cache().ensure(VERSION)
        pycache = entry / "tree/payload/scripts/__pycache__"
        pycache.mkdir()
        (pycache / "tool.cpython-311.pyc").write_bytes(b"bytecode")
        self.assertPristine(self.resolved(self.cache()))

    def test_the_resolve_install_boundary(self):
        """Bytes changed in the cache after `resolve()` returns never reach the target."""
        release = self.resolved(self.cache())
        entry = self.cache_dir / VERSION
        _alter_consistently(entry / "tree")
        (entry / "complete").write_text(self.pins.get(VERSION).sha256 + "\n")
        target = self.tmp / "target"
        (target / ".git").mkdir(parents=True)
        install.bootstrap(target, release, now="2026-09-30T00:00:00Z")
        for location, (data, _executable) in self.pristine.items():
            if location == "manifest.json":
                continue
            target_path = location.split("/", 1)[1]
            if target_path in (".gitignore.workflow-fragment", "CLAUDE.md"):
                continue
            self.assertEqual((target / target_path).read_bytes(), data, target_path)
        for path in target.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"ALTERED-BYTES", path.read_bytes(), path)

    def seam(self, cache: source.ReleaseCache, times: int) -> list[int]:
        """A writer that ignores the lock: alters `tree/` and the copied file
        between the snapshot copy and its check, the first `times` times."""
        calls = []

        def alter(snapshot: Path, entry: Path) -> None:
            calls.append(1)
            if len(calls) <= times:
                (entry / "tree/payload/docs/guide.md").write_bytes(b"swapped\n")
                (snapshot / "payload/docs/guide.md").write_bytes(b"swapped\n")
        cache._after_snapshot_copy = alter
        return calls

    def test_a_writer_that_ignores_the_lock(self):
        cache = self.cache()
        cache.ensure(VERSION)
        calls = self.seam(cache, times=1)
        fetched = self.counting(cache)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            release = self.resolved(cache)
        self.assertPristine(release)
        self.assertEqual(len(calls), 2)
        self.assertEqual(fetched.count(self.pkg.archive.name), 1)
        self.assertIn("changed while it was being copied", stderr.getvalue())
        self.assertTrue(self.cache().cached(VERSION))

    def test_a_writer_that_ignores_the_lock_while_offline(self):
        cache = self.cache()
        cache.ensure(VERSION)
        self.seam(cache, times=1)
        self.offline(cache)
        with contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(source.ReleaseUnavailableError):
            cache.resolve(VERSION)
        self.assertFalse((self.cache_dir / VERSION).exists())

    def test_a_writer_that_alters_the_refetched_entry_too(self):
        cache = self.cache()
        cache.ensure(VERSION)
        calls = self.seam(cache, times=2)
        fetched = self.counting(cache)
        before = self.snapshots()
        with contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(ReleaseIntegrityError):
            cache.resolve(VERSION)
        self.assertEqual(len(calls), 2)
        self.assertEqual(fetched.count(self.pkg.archive.name), 1)
        self.assertEqual(self.snapshots() - before, set(), "a refused snapshot was left behind")

    def snapshots(self) -> set[Path]:
        return set(Path(tempfile.gettempdir()).glob("workflow-release-*"))

    def test_close_removes_the_snapshot(self):
        release = self.cache().resolve(VERSION)
        self.assertTrue(release.root.is_dir())
        release.close()
        self.assertFalse(release.root.exists())
        with self.cache().resolve(VERSION) as release:
            root = release.root
            self.assertTrue(root.is_dir())
        self.assertFalse(root.exists())

    def test_the_snapshot_is_removed_when_the_invocation_ends(self):
        pin = self.pins.get(VERSION)
        pins_file = self.tmp / "pins.json"
        pins_file.write_text(json.dumps({
            "schema_version": 1, "repository": "example/workflow",
            "releases": {VERSION: {"archive": pin.archive, "sha256": pin.sha256,
                                   "manifest_sha256": pin.manifest_sha256}}}))
        script = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "from pathlib import Path\n"
            "from workflow_manager import source\n"
            "cache = source.ReleaseCache(Path(sys.argv[2]), source.ReleaseSource(sys.argv[3]),"
            " source.load_pins(Path(sys.argv[4])))\n"
            "print(cache.resolve(sys.argv[5]).root)\n")
        proc = subprocess.run(
            [sys.executable, "-c", script, str(REPO_ROOT / "src"), str(self.cache_dir),
             str(self.served), str(pins_file), VERSION],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        root = Path(proc.stdout.strip())
        self.assertTrue(root.name.startswith("workflow-release-"), root)
        self.assertFalse(root.exists())


class TestLocking(_SourceTest):
    def test_concurrent_resolves_fetch_once(self):
        cache = self.cache()
        fetched = self.counting(cache)
        results, errors = [], []

        def run():
            try:
                release = cache.resolve(VERSION)
                self.addCleanup(release.close)
                results.append(release)
            except Exception as exc:  # reported below
                errors.append(exc)
        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        self.assertEqual(fetched.count(self.pkg.archive.name), 1)
        for release in results:
            self.assertPristine(release)

    def test_resolve_waits_for_the_lock(self):
        self.cache_dir.mkdir()
        cache = self.cache()
        done = threading.Event()
        results = []

        def run():
            release = cache.resolve(VERSION)
            self.addCleanup(release.close)
            results.append(release)
            done.set()
        with open(self.cache_dir / f"{VERSION}.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            self.assertFalse(done.wait(0.5), "resolve() did not wait for the entry's lock")
            self.assertFalse((self.cache_dir / VERSION).exists())
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertTrue(done.wait(120))
        thread.join(timeout=10)
        self.assertPristine(results[0])


class TestLocalRelease(_SourceTest):
    def local(self, directory: Path, version: str | None = VERSION, pins=None):
        release = source.local_release(directory, version, pins or self.pins)
        self.addCleanup(release.close)
        return release

    def test_a_pinned_directory_is_recorded_as_the_package(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            release = self.local(self.release_dir)
        self.assertEqual(release.source, self.pins.source_record(VERSION))
        self.assertIn("local copy of published release", stderr.getvalue())
        self.assertFalse(release.root.is_relative_to(self.release_dir))
        self.assertPristine(release)

    def test_the_requested_version_defaults_to_the_directory(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.local(self.release_dir, None).version, VERSION)

    def test_an_altered_pinned_directory_is_refused_before_any_write(self):
        _alter_consistently(self.release_dir)
        target = self.tmp / "target"
        (target / ".git").mkdir(parents=True)
        with self.assertRaises(ReleaseIntegrityError) as caught:
            source.local_release(self.release_dir, VERSION, self.pins)
        self.assertIn(VERSION, str(caught.exception))
        self.assertIn(str(self.release_dir), str(caught.exception))
        self.assertIn(self.pins.get(VERSION).manifest_sha256, str(caught.exception))
        self.assertEqual([p.name for p in target.iterdir()], [".git"])

    def test_a_damaged_pinned_directory_is_refused(self):
        (self.release_dir / "payload/docs/guide.md").write_bytes(b"damaged\n")
        with self.assertRaises(ReleaseIntegrityError):
            source.local_release(self.release_dir, VERSION, self.pins)

    def test_an_unpinned_directory_is_local(self):
        release = self.local(self.release_dir, pins=source.Pins("example/workflow", {}))
        self.assertEqual(release.source, {"kind": "local"})
        self.assertPristine(release)

    def test_an_unpinned_directory_still_verifies(self):
        (self.release_dir / "payload/docs/guide.md").write_bytes(b"damaged\n")
        with self.assertRaises(ReleaseIntegrityError):
            source.local_release(self.release_dir, VERSION, source.Pins("example/workflow", {}))

    def test_an_unpinned_consistently_altered_directory_is_local(self):
        _alter_consistently(self.release_dir)
        release = self.local(self.release_dir, pins=source.Pins("example/workflow", {}))
        self.assertEqual(release.source, {"kind": "local"})

    def test_another_version_than_requested_is_refused(self):
        with self.assertRaises(ReleaseIntegrityError) as caught:
            source.local_release(self.release_dir, "1.0.0", self.pins)
        self.assertIn("1.0.0", str(caught.exception))
        self.assertIn(VERSION, str(caught.exception))

    def test_a_directory_without_a_release(self):
        with self.assertRaises(ReleaseIntegrityError):
            source.local_release(self.tmp, VERSION, self.pins)

    def test_an_installed_local_release_matches_the_package(self):
        with contextlib.redirect_stderr(io.StringIO()):
            release = self.local(self.release_dir)
        target = self.tmp / "target"
        (target / ".git").mkdir(parents=True)
        install.bootstrap(target, release, now="2026-09-30T00:00:00Z")
        self.assertEqual((target / "scripts/tool.sh").read_bytes(),
                         self.pristine["payload/scripts/tool.sh"][0])



class TestPackageCommand(_Tmp):
    """`workflow_manager package build|verify` (5.5): the CLI face of 5.1, for
    the `workflow` repository's own release workflow."""

    def _cli(self, *argv):
        from workflow_manager import cli

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["package", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_build_writes_what_build_package_writes(self):
        release = make_release(self.tmp / "release")
        code, out, _ = self._cli("build", str(release), "--out", str(self.tmp / "cli"))
        self.assertEqual(code, 0)
        direct = package.build_package(release, self.tmp / "direct")
        for built in (direct.archive, direct.manifest, direct.sums):
            self.assertEqual((self.tmp / "cli" / built.name).read_bytes(), built.read_bytes())
            self.assertIn(built.name, out)

    def test_build_refuses_a_release_that_fails_verification(self):
        release = make_release(self.tmp / "release")
        (release / "payload/docs/guide.md").write_bytes(b"changed\n")
        code, _, err = self._cli("build", str(release), "--out", str(self.tmp / "out"))
        self.assertEqual(code, 1)
        self.assertIn("fails verification", err)

    def test_verify_accepts_a_package_and_its_digest(self):
        built = package.build_package(make_release(self.tmp / "release"), self.tmp / "out")
        digest = package.file_sha256(built.archive)
        for argv in ([str(built.archive)], [str(built.archive), "--sha256", digest]):
            with self.subTest(argv=argv):
                code, out, _ = self._cli("verify", *argv)
                self.assertEqual(code, 0)
                self.assertIn(f"release {VERSION}", out)
                self.assertIn("verified", out)

    def test_verify_refuses_another_digest(self):
        built = package.build_package(make_release(self.tmp / "release"), self.tmp / "out")
        code, _, err = self._cli("verify", str(built.archive), "--sha256", "0" * 64)
        self.assertEqual(code, 1)
        self.assertIn("0" * 64, err)

    def test_verify_refuses_an_unsafe_archive(self):
        archive = self.tmp / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(f"{TOP}/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        code, _, err = self._cli("verify", str(archive))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error: "), err)


if __name__ == "__main__":
    unittest.main()
