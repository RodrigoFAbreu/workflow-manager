#!/usr/bin/env python3
"""Discovery, trust and the cache (`workflow-manager-release-agnostic`, CP1;
plan 3.1-3.3, 3.7 and 4).

A release this Manager has no pin for is found by listing the source and
verified by its own `SHA256SUMS`; a pin still binds the releases it names; the
cache remembers which source a discovered entry came from. Every release here
is synthetic, served from a temporary directory or a loopback server, with a
private release cache per test: no real network, and never the primed cache.
"""

from __future__ import annotations

import ast
import contextlib
import http.server
import io
import json
import os
import shutil
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import test_bootstrap as tb
from support import REPO_ROOT

import workflow_manager.package as package_module
from workflow_manager import source as release_source
from workflow_manager.installation import Installation, is_managed
from workflow_manager.source import (
    Chooser,
    Deadline,
    DiscoveryFailure,
    ReleaseCache,
    ReleaseSource,
    parse_github_listing,
)

UNPINNED = "7.0.2"
NEWER = "7.0.3"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "github_releases_listing.json"


def _listing(versions, *, immutable=True, draft=False, prerelease=False, extra=()):
    entries = []
    for version in versions:
        entry = {"tag_name": f"v{version}", "draft": draft, "prerelease": prerelease,
                 "assets": [{"name": name} for name in (
                     "SHA256SUMS", package_module.archive_name(version),
                     package_module.manifest_asset_name(version))]}
        if immutable is not None:
            entry["immutable"] = immutable
        entries.append(entry)
    return json.dumps(list(extra) + entries).encode()


class TestGithubListingParser(unittest.TestCase):
    def test_the_recorded_response(self):
        listing = parse_github_listing(FIXTURE.read_bytes())
        self.assertEqual(list(listing.versions),
                         sorted(listing.versions, key=release_source._version_key))
        self.assertIn("2.12.0", listing.versions)
        self.assertTrue(listing.complete)
        self.assertEqual(listing.rejected, {})

    def test_candidates_must_be_published_immutable_releases(self):
        raw = json.loads(_listing(["1.0.0", "1.0.1", "1.0.2", "1.0.3"]))
        raw[0]["draft"] = True
        raw[1]["prerelease"] = True
        raw[2]["immutable"] = False
        del raw[3]["immutable"]
        raw.append({"tag_name": "nightly", "draft": False, "prerelease": False,
                    "immutable": True, "assets": []})
        raw.append({"tag_name": "v1.0", "immutable": True, "assets": []})
        raw.append({"tag_name": "v1.0.4", "draft": False, "prerelease": False,
                    "immutable": True, "assets": [{"name": "SHA256SUMS"}]})
        listing = parse_github_listing(json.dumps(raw).encode())
        self.assertEqual(listing.versions, ())
        self.assertEqual(listing.rejected, {
            "1.0.2": "it is not marked immutable", "1.0.3": "it is not marked immutable",
            "1.0.4": "it does not list its three assets"})

    def test_a_listing_of_exactly_one_page_may_be_truncated(self):
        full = parse_github_listing(_listing([f"1.0.{n}" for n in range(100)]))
        self.assertFalse(full.complete)
        self.assertTrue(parse_github_listing(_listing([f"1.0.{n}" for n in range(99)])).complete)

    def test_a_malformed_listing_is_a_discovery_failure(self):
        for raw in (b"[{\"tag_name\": ", b"{}", b"not json"):
            with self.subTest(raw=raw), self.assertRaises(DiscoveryFailure):
                parse_github_listing(raw)

    def test_the_pin_derived_from_sums_needs_exactly_two_well_formed_lines(self):
        archive, manifest = package_module.archive_name("1.2.3"), \
            package_module.manifest_asset_name("1.2.3")
        good = f"{'a' * 64}  {archive}\n{'b' * 64}  {manifest}\n"
        pin = release_source.derive_pin("1.2.3", good)
        self.assertEqual((pin.archive, pin.sha256, pin.manifest_sha256),
                         (archive, "a" * 64, "b" * 64))
        for bad in (good + f"{'c' * 64}  other\n", f"{'a' * 64}  {archive}\n",
                    good.replace("a" * 64, "A" * 64), good + "garbage\n", ""):
            with self.subTest(bad=bad), self.assertRaises(release_source.ReleaseIntegrityError):
                release_source.derive_pin("1.2.3", bad)


class _Stub(http.server.ThreadingHTTPServer):
    """A loopback stand-in for the default source: `/releases` is the listing and
    `/dl/<version>/<asset>` the downloads."""

    daemon_threads = True

    def __init__(self, directory: Path, listing, *, block=(), stall=0.0):
        self.directory, self.listing, self.block, self.stall = directory, listing, block, stall
        self.requests: list[str] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.requests.append(self.path)
                if outer.stall:
                    time.sleep(outer.stall)
                if self.path.startswith("/releases"):
                    return self._send(200, outer.listing() if callable(outer.listing)
                                      else outer.listing)
                parts = self.path.split("/")
                if len(parts) == 4 and parts[1] == "dl" and parts[3] not in outer.block:
                    path = outer.directory / parts[2] / parts[3]
                    if path.is_file():
                        return self._send(200, path.read_bytes())
                self._send(404, b"no")

            def _send(self, code, body):
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

        super().__init__(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def patches(self):
        return (mock.patch.object(release_source, "DEFAULT_SOURCE",
                                  self.base + "/dl/{version}/"),
                mock.patch.object(release_source, "GITHUB_LISTING_URL", self.base + "/releases"))


class _Mirror(tb._PackagedReleases):
    """`7.0.0` and `7.0.1` are pinned; `7.0.2` and `7.0.3` are published in
    `self.mirror` (a directory of `<version>/`) and pinned nowhere."""

    UNPINNED_VERSIONS = (UNPINNED, NEWER)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(cls._class_tmp.name)
        base = tb.support.release(tb.NEWEST_RELEASE)
        cls.mirror = root / "mirror"
        cls.mirror.mkdir()
        for version in cls.PINNED:
            cls.mirror.joinpath(version).symlink_to(cls.source_dir / version)
        for version in cls.UNPINNED_VERSIONS:
            tree = tb.synthesize_next_release(base, root / "trees" / version, version)
            package_module.build_package(tree.root, cls.mirror / version)

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {release_source.PINNED_ONLY_ENV: "0"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(release_source.SOURCE_ENV, None)
        self.tmp = Path(self._tmp.name)

    def variant(self, mutate, version=UNPINNED) -> Path:
        """A mirror like `self.mirror` whose `version` was changed by `mutate(dir)`."""
        root = self.tmp / f"variant-{len(list(self.tmp.glob('variant-*')))}"
        root.mkdir()
        for entry in self.mirror.iterdir():
            if entry.name != version:
                (root / entry.name).symlink_to(entry.resolve())
        shutil.copytree(self.mirror / version, root / version)
        mutate(root / version)
        return root

    def bootstrap_at(self, version="7.0.0"):
        self.assertEqual(self._cli("--pinned-only", "--release-version", version, "bootstrap",
                                   str(self.target), source_dir=self.source_dir), 0,
                         self.cli_output)

    def run_default(self, *args):
        """The CLI against the default source (patched to a stub) and the test's cache."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tb.cli_module.main(["--release-cache", str(self.cache), *args])
        self.cli_stdout, self.cli_stderr = out.getvalue(), err.getvalue()
        self.cli_output = self.cli_stdout + self.cli_stderr
        return code

    def stub(self, directory=None, listing=None, **kwargs):
        stub = _Stub(directory or self.mirror,
                     listing or _listing([*self.PINNED, *self.UNPINNED_VERSIONS]), **kwargs)
        self.addCleanup(stub.server_close)
        self.addCleanup(stub.shutdown)
        for patcher in stub.patches():
            patcher.start()
            self.addCleanup(patcher.stop)
        return stub


class TestDiscoveryOverADirectory(_Mirror):
    def test_a_bare_update_installs_the_newest_unpinned_release(self):
        self.bootstrap_at("7.0.0")
        self.assertEqual(self._cli("update", str(self.target), source_dir=self.mirror), 0,
                         self.cli_output)
        record = Installation.read(self.target)
        self.assertEqual(record.workflow_version, NEWER)
        built = self.mirror / NEWER / package_module.archive_name(NEWER)
        self.assertEqual(record.source, {
            "kind": "package", "repository": "example/workflow",
            "archive": built.name, "sha256": package_module.file_sha256(built),
            "trust": "discovered", "from": f"dir:{self.mirror}"})
        self.assertIn(f"using release {NEWER}, discovered from dir:{self.mirror}",
                      self.cli_stderr)
        self.assertIn("no pin", self.cli_stderr)

    def test_status_and_doctor_name_the_trust_and_source_of_a_discovered_release(self):
        self.bootstrap_at("7.0.0")
        self.assertEqual(self._cli("status", str(self.target), source_dir=self.mirror), 0,
                         self.cli_output)
        self.assertNotIn("discovered", self.cli_stdout)
        self._cli("update", str(self.target), source_dir=self.mirror)
        self._cli("status", str(self.target), source_dir=self.mirror)
        self.assertIn(f"discovered from dir:{self.mirror}", self.cli_stdout)
        self._cli("doctor", str(self.target), source_dir=self.mirror)
        self.assertIn(f"discovered from dir:{self.mirror}", self.cli_stdout)
        self.assertIn("[discovered, not pinned]", self.cli_stdout)

    def test_the_cache_entry_records_its_source(self):
        self.bootstrap_at("7.0.0")
        self._cli("update", str(self.target), source_dir=self.mirror)
        stored = json.loads((self.cache / NEWER / "SOURCE").read_text())
        self.assertEqual(stored, {"trust": "discovered", "from": f"dir:{self.mirror}"})
        self.assertFalse((self.cache / "7.0.0" / "SOURCE").exists(), "the pin binds a pinned entry")

    def test_bootstrap_installs_the_newest_too(self):
        self.assertEqual(self._cli("bootstrap", str(self.target), source_dir=self.mirror), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, NEWER)

    def test_pinned_only_never_lists_and_refuses_an_unpinned_version(self):
        for argv, env in ((["--pinned-only"], {}), ([], {release_source.PINNED_ONLY_ENV: "1"})):
            with self.subTest(argv=argv, env=env), mock.patch.dict(os.environ, env):
                repo = tb.empty_repo(self.tmp / f"t{len(argv)}{len(env)}")
                code = self._cli(*argv, "--release-version", UNPINNED, "bootstrap", str(repo),
                                 source_dir=self.mirror)
                self.assertEqual(code, 1)
                self.assertIn(f"release {UNPINNED} is not published", self.cli_stderr)
                self.assertFalse(is_managed(repo))
                code = self._cli(*argv, "bootstrap", str(repo), source_dir=self.mirror)
                self.assertEqual(code, 0, self.cli_output)
                self.assertEqual(Installation.read(repo).workflow_version, "7.0.1")
                self.assertNotIn("discovered", self.cli_output)

    def test_releases_shows_the_pinned_and_the_discovered(self):
        self.assertEqual(self._cli("releases", source_dir=self.mirror), 0, self.cli_output)
        lines = {line.split()[0]: line for line in self.cli_stdout.splitlines()}
        self.assertEqual(list(lines), ["7.0.0", "7.0.1", UNPINNED, NEWER])
        self.assertIn("[discovered, not cached;", lines[NEWER])
        self._cli("--release-version", NEWER, "bootstrap", str(self.target),
                  source_dir=self.mirror)
        self._cli("releases", source_dir=self.mirror)
        self.assertIn("[discovered, cached;", self.cli_stdout)
        self._cli("--pinned-only", "releases", source_dir=self.mirror)
        self.assertEqual([line.split()[0] for line in self.cli_stdout.splitlines()],
                         ["7.0.0", "7.0.1"])

    def test_an_explicit_unpinned_version_is_fetched_and_verified(self):
        self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(self.target),
                                   source_dir=self.mirror), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)


class TestEveryRefusalFailsClosed(_Mirror):
    """Each variant changes one thing about `7.0.2`'s published assets."""

    def asset(self, directory: Path, suffix: str, version: str = UNPINNED) -> Path:
        return directory / f"workflow-{version}.{suffix}"

    def rewrite_sums(self, directory: Path, transform):
        sums = directory / "SHA256SUMS"
        sums.write_text(transform(sums.read_text()))

    def test_sums_problems_make_an_explicit_install_refuse(self):
        archive, manifest = f"workflow-{UNPINNED}.tar.gz", f"workflow-{UNPINNED}.manifest.json"

        def drop(name):
            return lambda d: self.rewrite_sums(d, lambda t: "".join(
                line + "\n" for line in t.splitlines() if not line.endswith(name)))

        cases = {
            "archive digest not in sums": lambda d: self.rewrite_sums(
                d, lambda t: t.replace(t.splitlines()[0][:8], "00000000")),
            "manifest asset missing from sums": drop(manifest),
            "archive missing from sums": drop(archive),
            "malformed line": lambda d: self.rewrite_sums(d, lambda t: t + "not a sum line\n"),
            "an extra file": lambda d: self.rewrite_sums(d, lambda t: t + f"{'c' * 64}  extra\n"),
            "manifest asset differs": lambda d: self.asset(d, "manifest.json").write_text(
                self.asset(d, "manifest.json").read_text() + " "),
            "wrong version": lambda d: self.asset(d, "manifest.json").write_text(
                self.asset(d, "manifest.json").read_text().replace(
                    f'"workflow_version": "{UNPINNED}"', '"workflow_version": "7.9.9"')),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                root = self.variant(mutate)
                repo = tb.empty_repo(self.tmp / f"repo-{len(list(self.tmp.glob('repo-*')))}")
                code = self._cli("--release-version", UNPINNED, "bootstrap", str(repo),
                                 source_dir=root)
                self.assertEqual(code, 1, self.cli_output)
                self.assertFalse(is_managed(repo))

    def test_a_candidate_that_fails_its_checks_is_skipped_when_choosing(self):
        root = self.variant(lambda d: self.rewrite_sums(d, lambda t: t + "garbage\n"),
                            version=NEWER)
        self.assertEqual(self._cli("bootstrap", str(self.target), source_dir=root), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)
        self.assertIn(f"could not use release {NEWER}", self.cli_stderr)
        self.assertIn("skipping it", self.cli_stderr)

    def test_an_archive_whose_digest_disagrees_refuses_instead_of_falling_back(self):
        def damage(directory):
            archive = self.asset(directory, "tar.gz", NEWER)
            archive.write_bytes(archive.read_bytes() + b"x")
        root = self.variant(damage, version=NEWER)
        self.assertEqual(self._cli("bootstrap", str(self.target), source_dir=root), 1)
        self.assertIn("archive does not match", self.cli_stderr)
        self.assertFalse(is_managed(self.target))

    def test_a_pinned_version_served_with_other_bytes_is_refused_by_its_pin(self):
        def altered(directory):
            archive = directory / "workflow-7.0.1.tar.gz"
            archive.write_bytes(archive.read_bytes() + b"x")
            sums = package_module.sha256sums_text(
                [archive, directory / "workflow-7.0.1.manifest.json"])
            (directory / "SHA256SUMS").write_text(sums)
        root = self.variant(altered, version="7.0.1")
        self.assertEqual(self._cli("--release-version", "7.0.1", "bootstrap", str(self.target),
                                   source_dir=root), 1)
        self.assertIn("does not match its pin", self.cli_stderr)
        self.assertEqual(self._cli("--release-version", "7.0.1", "--pinned-only", "bootstrap",
                                   str(self.target), source_dir=root), 1)

    def test_a_pinned_release_is_never_inspected(self):
        stub = self.stub(listing=_listing(["7.0.0", "7.0.1"]))
        self.assertEqual(self.run_default("bootstrap", str(self.target)), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")
        self.assertTrue(all(not p.endswith("SHA256SUMS") or "7.0.1" in p for p in stub.requests))


class TestOnlyAStrictVersionBuildsAPath(_Mirror):
    """RA-IMPL-R6-001: a version that is not `X.Y.Z` -- from `--release-version`
    or a target's record -- is refused before any cache path or source read, so
    nothing outside the cache root is created or removed."""

    BAD = ("../escaped", "2.12", "v2.12.0", "", "a/b", "7.0.2/../7.0.2")

    def outside(self):
        return sorted(p.name for p in self.tmp.iterdir())

    def test_a_traversal_version_given_by_option_touches_nothing(self):
        # What the reviewer reproduced: a source that serves a parseable
        # SHA256SUMS at the traversed location, and a cache next to it.
        victim = self.mirror.parent / "escaped"
        victim.mkdir()
        (victim / "SHA256SUMS").write_text("0" * 64 + "  workflow-../escaped.tar.gz\n")
        before = sorted(p.name for p in self.mirror.parent.iterdir())
        for bad in self.BAD:
            with self.subTest(version=bad):
                repo = tb.empty_repo(self.tmp / f"repo-{len(list(self.tmp.glob('repo-*')))}")
                code = self._cli("--release-version", bad, "bootstrap", str(repo),
                                 source_dir=self.mirror)
                self.assertEqual(code, 1, self.cli_output)
                self.assertNotIn("Traceback", self.cli_output)
                self.assertTrue(victim.is_dir())
                self.assertEqual(sorted(p.name for p in self.mirror.parent.iterdir()), before)
                self.assertFalse(self.cache.exists() and any(self.cache.iterdir()),
                                 list(self.cache.iterdir()) if self.cache.exists() else None)

    def test_the_cache_refuses_a_non_strict_version_before_any_path(self):
        cache = ReleaseCache(self.cache, ReleaseSource(str(self.mirror)),
                             release_source.load_pins(self.pins_path), discover=True)
        for bad in (*self.BAD, 123, None):
            with self.subTest(version=bad):
                with self.assertRaises(release_source.ReleaseNotPublishedError) as caught:
                    cache.resolve(bad)
                self.assertEqual(caught.exception.kind, "unpinned")
                self.assertRaises(release_source.ReleaseNotPublishedError, cache.cached, bad)
                self.assertIsNone(cache.cached_manifest(bad))
                self.assertRaises(release_source.ReleaseNotPublishedError,
                                  cache.source.inspect, bad)
        self.assertFalse(self.cache.exists() and any(self.cache.iterdir()))

    def test_verify_after_a_scalar_record_gives_the_release_dir_advice_under_discovery(self):
        for value in (123, ""):
            with self.subTest(value=value):
                repo = tb.empty_repo(self.tmp / f"repo-{len(list(self.tmp.glob('repo-*')))}")
                self.assertEqual(self._cli("--pinned-only", "--release-version", "7.0.0",
                                           "bootstrap", str(repo)), 0, self.cli_output)
                record = repo / ".workflow-manager" / "installation.json"
                text = record.read_text()
                record.write_text(text.replace('"workflow_version": "7.0.0"',
                                               f'"workflow_version": {json.dumps(value)}'))
                code = self._cli("verify", str(repo), source_dir=self.mirror)
                self.assertNotIn("Traceback", self.cli_output)
                self.assertIn("--release-dir DIR", self.cli_output)
                self.assertNotEqual(code, 0)


class TestOffline(_Mirror):
    def test_a_missing_source_directory_falls_back_to_the_newest_pin(self):
        self.bootstrap_at("7.0.1")
        self.assertEqual(self._cli("update", str(self.target), source_dir=self.tmp / "absent"), 0,
                         self.cli_output)
        self.assertIn("could not look for newer releases", self.cli_stderr)
        self.assertIn("using 7.0.1", self.cli_stderr)
        self.assertEqual(self.cli_stderr.count("could not look for newer releases"), 1)

    def test_an_unreachable_server_falls_back_to_the_cached_pin(self):
        stub = self.stub()
        base = stub.base
        stub.shutdown()
        stub.server_close()
        self.bootstrap_at("7.0.1")
        with mock.patch.object(release_source, "DEFAULT_SOURCE", base + "/dl/{version}/"), \
                mock.patch.object(release_source, "GITHUB_LISTING_URL", base + "/releases"):
            self.assertEqual(self.run_default("update", str(self.target)), 0, self.cli_output)
        self.assertIn("could not look for newer releases", self.cli_stderr)
        self.assertIn("using 7.0.1", self.cli_stderr)

    def test_the_request_bound_ends_a_stalled_listing(self):
        self.stub(stall=2.0)
        self.bootstrap_at("7.0.1")
        began = time.monotonic()
        with mock.patch.object(release_source, "DISCOVERY_TIMEOUT_SECONDS", 0.3):
            code = self.run_default("update", str(self.target))
        self.assertEqual(code, 0, self.cli_output)
        self.assertLess(time.monotonic() - began, 1.8)
        self.assertIn("could not look for newer releases", self.cli_stderr)

    def test_the_total_deadline_ends_the_walk(self):
        self.stub(stall=0.25)
        self.bootstrap_at("7.0.1")
        with mock.patch.object(release_source, "DISCOVERY_TIMEOUT_SECONDS", 1.0), \
                mock.patch.object(release_source, "DISCOVERY_DEADLINE_SECONDS", 0.6):
            code = self.run_default("update", str(self.target))
        self.assertEqual(code, 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")
        self.assertIn("could not look for newer releases", self.cli_stderr)

    def test_a_listed_release_without_immutable_true_is_skipped(self):
        for immutable in (False, None):
            with self.subTest(immutable=immutable):
                repo = tb.empty_repo(self.tmp / f"r{immutable}")
                stub = self.stub(listing=_listing(["7.0.0", "7.0.1", UNPINNED],
                                                  immutable=immutable))
                self.assertEqual(self.run_default("bootstrap", str(repo)), 0, self.cli_output)
                self.assertEqual(Installation.read(repo).workflow_version, "7.0.1")
                self.assertIn(f"skipping release {UNPINNED}: it is not marked immutable",
                              self.cli_stderr)
                stub.shutdown()

    def test_unreachable_candidate_assets_fall_back_to_the_newest_local_release(self):
        self.stub(block=(f"workflow-{NEWER}.manifest.json", f"workflow-{UNPINNED}.manifest.json"))
        self.assertEqual(self.run_default("bootstrap", str(self.target)), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")
        self.assertIn(f"could not use release {NEWER}", self.cli_stderr)
        self.assertIn(f"could not use release {UNPINNED}", self.cli_stderr)


class TestArchiveAvailability(_Mirror):
    """The listing, `SHA256SUMS` and manifest are reachable; one archive is not."""

    def blocked(self):
        return self.stub(block=(f"workflow-{NEWER}.tar.gz",))

    def test_bootstrap_and_update_use_the_next_release_down(self):
        self.blocked()
        self.assertEqual(self.run_default("bootstrap", str(self.target)), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)
        self.assertIn(f"could not fetch release {NEWER}", self.cli_stderr)
        self.assertIn("trying an older one", self.cli_stderr)

    def test_dry_run_and_doctor_choose_what_update_chooses_and_write_nothing(self):
        self.bootstrap_at("7.0.0")
        self.blocked()
        before = sorted(p.relative_to(self.target).as_posix()
                        for p in self.target.rglob("*") if ".git/" not in p.as_posix())
        for command in (("update", "--dry-run"), ("doctor",)):
            with self.subTest(command=command):
                self.run_default(*command, str(self.target))
                self.assertIn(f"could not fetch release {NEWER}", self.cli_stderr)
                self.assertIn(UNPINNED, self.cli_output)
        after = sorted(p.relative_to(self.target).as_posix()
                       for p in self.target.rglob("*") if ".git/" not in p.as_posix())
        self.assertEqual(before, after)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.0")
        self.assertEqual(self.run_default("update", str(self.target)), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)

    def test_an_explicit_version_never_falls_back(self):
        self.blocked()
        self.assertEqual(self.run_default("--release-version", NEWER, "bootstrap",
                                          str(self.target)), 1)
        self.assertFalse(is_managed(self.target))
        self.assertNotIn("trying an older one", self.cli_stderr)

    def test_the_destinations_are_planned_again_for_the_version_finally_chosen(self):
        self.bootstrap_at("7.0.0")
        self.blocked()
        planned = []
        real = tb.cli_module.plan_destinations

        def spy(options, environ, target, versions=()):
            planned.append(list(versions))
            return real(options, environ, target, versions)
        with mock.patch.object(tb.cli_module, "plan_destinations", spy):
            self.run_default("update", "--dry-run", str(self.target))
        self.assertEqual([p[0] for p in planned], [NEWER, UNPINNED])


class TestTemplateMirror(_Mirror):
    def test_a_url_template_has_no_listing_but_serves_an_explicit_version(self):
        stub = self.stub()
        template = stub.base + "/dl/{version}"
        self.assertIsNone(ReleaseSource(template).listing("example/workflow", Deadline()))
        self.assertEqual(self._cli("bootstrap", str(self.target), source_dir=template), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")
        self.assertFalse([p for p in stub.requests if p.startswith("/releases")])
        repo = tb.empty_repo(self.tmp / "explicit")
        self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(repo),
                                   source_dir=template), 0, self.cli_output)
        record = Installation.read(repo).source
        self.assertEqual((record["trust"], record["from"]), ("discovered", f"template:{template}"))


class TestTheCacheIsBoundToItsSource(_Mirror):
    def cache_for(self, directory) -> ReleaseCache:
        return ReleaseCache(self.cache, ReleaseSource(str(directory)), release_source.load_pins(
            self.pins_path), discover=True)

    def test_a_discovered_entry_is_not_reused_under_another_source(self):
        self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(self.target),
                                   source_dir=self.mirror), 0, self.cli_output)
        same = self.cache_for(self.mirror)
        other_dir = self.tmp / "other"
        shutil.copytree(self.mirror, other_dir, symlinks=True)
        other = self.cache_for(other_dir)
        self.assertTrue(same.cached(UNPINNED))
        self.assertIn(UNPINNED, same.known_local())
        self.assertFalse(other.cached(UNPINNED))
        self.assertNotIn(UNPINNED, other.known_local())
        pinned_only = ReleaseCache(self.cache, ReleaseSource(str(self.mirror)),
                                   release_source.load_pins(self.pins_path))
        self.assertNotIn(UNPINNED, pinned_only.known_local())

    def test_another_source_refetches_and_records_itself(self):
        self._cli("--release-version", UNPINNED, "bootstrap", str(self.target),
                  source_dir=self.mirror)
        other_dir = self.tmp / "other"
        shutil.copytree(self.mirror, other_dir, symlinks=True)
        repo = tb.empty_repo(self.tmp / "second")
        self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(repo),
                                   source_dir=other_dir), 0, self.cli_output)
        self.assertEqual(Installation.read(repo).source["from"], f"dir:{other_dir}")
        stored = json.loads((self.cache / UNPINNED / "SOURCE").read_text())
        self.assertEqual(stored["from"], f"dir:{other_dir}")

    def test_a_tampered_entry_is_discarded_and_fetched_again(self):
        self._cli("--release-version", UNPINNED, "bootstrap", str(self.target),
                  source_dir=self.mirror)
        archive = self.cache / UNPINNED / package_module.archive_name(UNPINNED)
        archive.write_bytes(archive.read_bytes() + b"x")
        repo = tb.empty_repo(self.tmp / "again")
        self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(repo),
                                   source_dir=self.mirror), 0, self.cli_output)
        self.assertIn("discarding cache entry", self.cli_stderr)
        for name in ("SHA256SUMS", "complete"):
            with self.subTest(name=name):
                (self.cache / UNPINNED / name).unlink()
                repo = tb.empty_repo(self.tmp / f"again-{name}")
                self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(repo),
                                           source_dir=self.mirror), 0, self.cli_output)
                self.assertTrue((self.cache / UNPINNED / name).is_file())


    def test_a_manifest_replaced_after_the_hit_check_is_not_served(self):
        self._cli("--release-version", UNPINNED, "bootstrap", str(self.target),
                  source_dir=self.mirror)
        cache = self.cache_for(self.mirror)
        manifest = self.cache / UNPINNED / "tree" / "manifest.json"
        genuine = manifest.read_bytes()
        self.assertEqual(cache.cached_manifest(UNPINNED), genuine)
        real = cache._is_hit

        def hit_then_replace(*args, **kwargs):
            hit = real(*args, **kwargs)
            manifest.write_bytes(b'{"manager": {}}')     # another source's invocation
            return hit

        with mock.patch.object(cache, "_is_hit", hit_then_replace):
            self.assertIsNone(cache.cached_manifest(UNPINNED))


class TestABodyReadKeepsToTheDeadline(unittest.TestCase):
    def test_a_trickling_body_reaches_the_deadline(self):
        now = [0.0]
        deadline = Deadline(1.0, clock=lambda: now[0])

        class Trickle:
            def read1(self, size):
                now[0] += 0.4                  # one byte per 0.4s
                return b"x"

            def read(self, size):              # blocks until `size` bytes: the old path
                raise AssertionError("a bounded read must use read1")

        with self.assertRaises(DiscoveryFailure) as caught:
            release_source._read_capped(Trickle(), 1 << 20, "http://example.invalid/", deadline)
        self.assertTrue(caught.exception.expired)

    def test_trickling_response_headers_reach_the_deadline(self):
        import socket

        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        stop = threading.Event()

        def trickle():
            conn, _ = server.accept()
            try:
                conn.recv(4096)
                conn.sendall(b"HTTP/1.1 200 OK\r\n")
                while not stop.is_set():
                    conn.sendall(b"X")             # one header byte every 40 ms
                    time.sleep(0.04)
            except OSError:
                pass
            finally:
                conn.close()

        thread = threading.Thread(target=trickle, daemon=True)
        thread.start()
        self.addCleanup(server.close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(stop.set)
        url = f"http://127.0.0.1:{server.getsockname()[1]}/"
        started = time.monotonic()
        with self.assertRaises(DiscoveryFailure) as caught:
            release_source._http_read(url, 1 << 20, Deadline(0.3))
        self.assertTrue(caught.exception.expired)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_a_plain_stream_is_still_read(self):
        import io as _io
        self.assertEqual(release_source._read_capped(_io.BytesIO(b"abc"), 10, "x", None), b"abc")


class TestTheSumsFile(unittest.TestCase):
    def test_a_repeated_filename_is_refused(self):
        line = "a" * 64 + "  workflow-1.0.0.tar.gz"
        with self.assertRaises(release_source.ReleaseIntegrityError):
            release_source._parse_sums_text(
                line + "\n" + "b" * 64 + "  workflow-1.0.0.manifest.json\n" + line + "\n", "SHA256SUMS")


class TestTheFloor(_Mirror):
    """A bare `update` never installs a release older than the installed one."""

    def install_discovered(self):
        self.assertEqual(self._cli("--release-version", NEWER, "bootstrap", str(self.target),
                                   source_dir=self.mirror), 0, self.cli_output)
        shutil.rmtree(self.cache)

    def snapshot(self):
        return {p.relative_to(self.target).as_posix(): p.read_bytes()
                for p in self.target.rglob("*") if p.is_file() and ".git/" not in p.as_posix()}

    def test_offline_with_only_older_entries_installs_nothing(self):
        self.install_discovered()
        before = self.snapshot()
        for command in (("update",), ("update", "--dry-run")):
            with self.subTest(command=command):
                code = self._cli(*command, str(self.target), source_dir=self.tmp / "absent")
                self.assertEqual(code, 1, self.cli_output)
                self.assertIn(f"error: no usable release at or above the installed Workflow "
                              f"{NEWER}: could not look for newer releases (offline)",
                              self.cli_stderr)
                self.assertIn("next:", self.cli_stderr)
        self.assertEqual(self.snapshot(), before)

    def test_a_listing_with_nothing_at_the_floor_is_not_called_offline(self):
        self.install_discovered()
        older = self.tmp / "older"
        older.mkdir()
        for entry in self.mirror.iterdir():
            if entry.name != NEWER:
                (older / entry.name).symlink_to(entry.resolve())
        before = self.snapshot()
        for command in (("update",), ("update", "--dry-run")):
            with self.subTest(command=command):
                code = self._cli(*command, str(self.target), source_dir=older)
                self.assertEqual(code, 1, self.cli_output)
                self.assertIn(f"error: no usable release at or above the installed Workflow "
                              f"{NEWER}: the release source offers no release at or above it",
                              self.cli_stderr)
                self.assertNotIn("offline", self.cli_stderr)
                self.assertIn("next: the source was read and holds no release at or above it",
                              self.cli_stderr)
        self.assertEqual(self.snapshot(), before)

    def test_a_blocked_archive_installs_nothing(self):
        self.install_discovered()
        self.stub(block=(f"workflow-{NEWER}.tar.gz",))
        before = self.snapshot()
        self.assertEqual(self.run_default("update", str(self.target)), 1, self.cli_output)
        self.assertIn(f"the archive of {NEWER} could not be fetched", self.cli_stderr)
        self.assertEqual(self.snapshot(), before)

    def test_the_installed_release_itself_is_a_no_op(self):
        self.install_discovered()
        self.assertEqual(self._cli("update", str(self.target), source_dir=self.mirror), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, NEWER)

    def test_an_explicit_older_version_still_downgrades(self):
        self.install_discovered()
        self.assertEqual(self._cli("--release-version", "7.0.1", "update", str(self.target),
                                   source_dir=self.mirror), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")

    def test_bootstrap_has_no_floor(self):
        self.bootstrap_at("7.0.1")
        self.target = tb.empty_repo(self.tmp / "second")
        self.assertEqual(self._cli("bootstrap", str(self.target),
                                   source_dir=self.tmp / "absent"), 0, self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")

    def test_an_unreadable_installed_version_has_no_floor_and_says_so(self):
        err = io.StringIO()
        with mock.patch.object(tb.cli_module, "is_managed", return_value=True), \
                mock.patch.object(tb.cli_module.Installation, "read",
                                  return_value=mock.Mock(workflow_version="weird")), \
                contextlib.redirect_stderr(err):
            floor = tb.cli_module._floor(mock.Mock(target=self.target))
        self.assertIsNone(floor)
        self.assertIn("names no parseable release", err.getvalue())


class TestChooser(_Mirror):
    def test_candidates_are_newest_first_and_lazy(self):
        cache = ReleaseCache(self.cache, ReleaseSource(str(self.mirror)),
                             release_source.load_pins(self.pins_path), discover=True)
        walk = Chooser(cache).candidates()
        self.assertEqual(next(walk), NEWER)
        self.assertEqual(list(walk), [UNPINNED, "7.0.1", "7.0.0"])

    def test_the_floor_cuts_the_walk(self):
        cache = ReleaseCache(self.cache, ReleaseSource(str(self.mirror)),
                             release_source.load_pins(self.pins_path), discover=True)
        chooser = Chooser(cache, floor=UNPINNED)
        self.assertEqual(list(chooser.candidates()), [NEWER, UNPINNED])
        self.assertTrue(chooser.cut_by_floor)

    def test_pinned_only_offers_the_pins_alone(self):
        cache = ReleaseCache(self.cache, ReleaseSource(str(self.mirror)),
                             release_source.load_pins(self.pins_path))
        self.assertEqual(list(Chooser(cache).candidates()), ["7.0.1", "7.0.0"])


class TestTestsStayHermetic(unittest.TestCase):
    """Plan 3.7: no test discovers over the network, and a discovery test never
    touches the operator's real release cache."""

    @staticmethod
    def offenders(text: str, name: str) -> list[str]:
        found = []
        if "PINNED_ONLY" in text and ('"0"' in text or "'0'" in text):
            if not any(token in text for token in ("release-cache", "RELEASE_CACHE", "CACHE_ENV",
                                                    "self.cache")):
                found.append(f"{name}: sets discovery on with no private release cache")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and "workflow_manager" in (
                    ast.get_source_segment(text, node) or ""):
                keyword = next((k.value for k in node.keywords if k.arg == "env"), None)
                if isinstance(keyword, ast.Dict):
                    found.append(f"{name}:{node.lineno}: a literal env for workflow_manager")
        return found

    def test_the_default_test_environment_is_pinned_only(self):
        import support
        # A committed or overriding lock moves the helper to discovery mode
        # through a private mirror and cache (support.cli_env).
        self.assertEqual(support.cli_env()[release_source.PINNED_ONLY_ENV],
                         "0" if support.LOCK else "1")
        self.assertEqual(support.cli_env(**{release_source.PINNED_ONLY_ENV: "0"})
                         [release_source.PINNED_ONLY_ENV], "0")
        self.assertEqual(os.environ.get(release_source.PINNED_ONLY_ENV), "1")

    def test_no_test_file_turns_discovery_on_without_a_private_cache(self):
        found = []
        for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
            found += self.offenders(path.read_text(encoding="utf-8"), path.name)
        self.assertEqual(found, [])

    def test_the_runner_notices_a_release_a_test_left_in_the_primed_cache(self):
        from parallel import priming
        import tempfile
        with tempfile.TemporaryDirectory() as cache:
            Path(cache, "7.0.0").mkdir()
            Path(cache, "7.0.0.lock").write_text("")
            before = priming.cache_entries(cache)
            self.assertEqual(priming.stray_entries(cache, before, ["7.0.0"]), [])
            Path(cache, "9.9.9").mkdir()
            Path(cache, "9.9.9.lock").write_text("")
            self.assertEqual(priming.stray_entries(cache, before, ["7.0.0"]), ["9.9.9"])
            Path(cache, "7.0.1").mkdir()
            Path(cache, "7.0.1", "SOURCE").write_text("{}")
            self.assertEqual(priming.stray_entries(cache, before, ["7.0.0", "7.0.1"]),
                             ["7.0.1", "9.9.9"])

    def test_the_floor_step_names_the_installed_release_and_the_remedy(self):
        from workflow_manager import advice
        for kind, remedy in (("offline", "connect to the network"),
                             ("archive", "serves the release's archive"),
                             ("none-at-floor", "holds no release at or above it"),
                             ("manager", "upgrade the Manager")):
            with self.subTest(kind=kind):
                error = release_source.ReleaseFloorError("m", kind=kind, installed="2.14.0")
                step = advice.next_step(error, advice.Context())
                self.assertIn(remedy, step)
                self.assertIn("2.14.0", step)

    def test_the_sweep_detects_a_violation(self):
        bad = ("import subprocess\n"
               "env = {'WORKFLOW_MANAGER_PINNED_ONLY': '0'}\n"
               "subprocess.run(['x', 'workflow_manager'], env={'A': '1'})\n")
        self.assertEqual(len(self.offenders(bad, "bad.py")), 2)
        good = ("import subprocess\nfrom support import cli_env\n"
                "env = cli_env(WORKFLOW_MANAGER_PINNED_ONLY='0', "
                "WORKFLOW_MANAGER_RELEASE_CACHE='/tmp/x')\n")
        self.assertEqual(self.offenders(good, "good.py"), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
