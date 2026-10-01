#!/usr/bin/env python3
"""Every pinned Workflow release package verifies (plan 6, `TestPinnedPackagesVerify`).

Checkpoint CP4 of `workflow-manager-packaged-distribution`, and permanent:
each version `published_releases.json` pins, obtained through the shared
release cache the way the CLI obtains it, re-verifies against its pin and
against its own manifest. The cache holds every pinned version before this
module runs (CP4 primed it; from CP5 the runner primes it), so a normal run
never fetches.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts src/ on sys.path)

from workflow_manager import package, source


class TestPinnedPackagesVerify(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pins = source.load_pins(source.PINS_PATH)
        cls.cache = source.ReleaseCache(source.cache_root(), source.ReleaseSource.select(),
                                        cls.pins)

    def test_something_is_pinned(self):
        self.assertTrue(self.pins.versions())
        self.assertEqual(self.pins.repository, "RodrigoFAbreu/workflow")

    def test_each_pinned_package_matches_its_pin_and_its_sums(self):
        for version in self.pins.versions():
            with self.subTest(version=version):
                pin = self.pins.get(version)
                entry = self.cache.ensure(version)
                self.assertEqual(package.file_sha256(entry / pin.archive), pin.sha256)
                manifest_asset = entry / package.manifest_asset_name(version)
                self.assertEqual(package.file_sha256(manifest_asset), pin.manifest_sha256)
                sums = (entry / package.SUMS_NAME).read_text()
                # `sha256sum`'s format, sorted by name (`package.sha256sums_text`).
                self.assertEqual(sums, f"{pin.manifest_sha256}  {manifest_asset.name}\n"
                                       f"{pin.sha256}  {pin.archive}\n")

    def test_each_pinned_package_extracts_to_a_release_that_verifies(self):
        """The archive itself, not only the cache's extracted tree: extracting
        it again yields its version, bound to the pinned manifest."""
        for version in self.pins.versions():
            with self.subTest(version=version):
                pin = self.pins.get(version)
                entry = self.cache.ensure(version)
                with tempfile.TemporaryDirectory(prefix="pinned-package-") as tmp:
                    release = package.extract_package(entry / pin.archive,
                                                      Path(tmp) / "tree", version)
                    self.assertEqual(release.version, version)
                    self.assertEqual(package.file_sha256(release.root / package.MANIFEST_NAME),
                                     pin.manifest_sha256)
                    self.assertEqual(release.verify(), [])

    def test_each_pinned_release_resolves_to_a_verified_snapshot(self):
        for version in self.pins.versions():
            with self.subTest(version=version):
                with self.cache.resolve(version) as release:
                    self.assertEqual(release.version, version)
                    self.assertEqual(release.source, self.pins.source_record(version))
                    self.assertEqual(
                        package.file_sha256(release.root / package.MANIFEST_NAME),
                        self.pins.get(version).manifest_sha256)
                    self.assertEqual(release.verify(), [])
                self.assertFalse(release.root.exists(), "the snapshot outlived its use")


if __name__ == "__main__":
    unittest.main()
