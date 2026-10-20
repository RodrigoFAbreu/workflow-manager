#!/usr/bin/env python3
"""The tested-releases lock and deterministic CI (`workflow-manager-release-agnostic`,
CP3; plan 3.5 and 4).

What a run tests is data in the repository: the pins plus `tests/tested_releases.json`
(the nightly's override aside). Every release here is synthetic (`7.0.x`, above
the pins), published into a temporary release-source directory; nothing reaches
the network, and every cache is private to its test.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

import support
import tested_releases
from support import REPO_ROOT, cli_env
from tested_releases import LockEntry, LockError

import test_bootstrap as tb
from frozen_runs import empty_repo
from parallel import canonical_json, priming
from test_parallel_runner import load_workflow_yaml
from workflow_manager import package as package_module
from workflow_manager import source as release_source

TESTS = REPO_ROOT / "tests"
VERIFY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "workflow-manager-verify.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
LOCK_TOOL = REPO_ROOT / "tools" / "release_lock.py"
SYNTHETIC = "7.0.2"
NEWER = "7.0.3"
#: The release a regression's child process has in its own lock, committed or
#: overriding: never one a `_LockedRelease` of that child builds.
LOCKED = "7.1.0"
SUITES = {"workflow_state_test.py": 12, "workflow_fingerprint_test.py": 3}
DIGEST = "ab" * 32


def entry_json(version: str = SYNTHETIC, **extra) -> dict:
    return {"archive": package_module.archive_name(version), "sha256": DIGEST,
            "manifest_sha256": DIGEST[::-1], **extra}


def lock_text(releases: dict | None = None, **top) -> str:
    return json.dumps({"schema_version": 1, "releases": releases or {}, **top})


class TestLockShape(unittest.TestCase):
    def test_the_committed_lock_is_valid_whether_empty_or_not(self):
        """Every release up to the last pin is pinned, so the committed lock
        lists only releases published after it -- none until one is added."""
        text = tested_releases.LOCK_PATH.read_text()
        lock = tested_releases.parse_lock(text)
        raw = json.loads(text)
        self.assertEqual(raw["schema_version"], 1)
        self.assertEqual(sorted(raw), ["releases", "schema_version"])
        self.assertEqual(sorted(raw["releases"]), list(lock))
        tested_releases.check_against_pins(lock, release_source.load_pins())
        self.assertEqual(tested_releases.dump_lock(lock), text)

    def test_a_valid_entry_round_trips_in_version_order(self):
        text = lock_text({NEWER: entry_json(NEWER), SYNTHETIC: entry_json(
            suites=SUITES, portability_exceptions=[{"suite": "a", "test": "b", "reason": "c"}])})
        lock = tested_releases.parse_lock(text)
        self.assertEqual(list(lock), [SYNTHETIC, NEWER])
        self.assertEqual(lock[SYNTHETIC].suites, SUITES)
        again = tested_releases.parse_lock(tested_releases.dump_lock(lock))
        self.assertEqual(again, lock)

    def test_malformed_locks_are_refused(self):
        cases = {
            "not json": "{",
            "schema": json.dumps({"schema_version": 2, "releases": {}}),
            "extra top key": lock_text(extra=1),
            "missing releases": json.dumps({"schema_version": 1}),
            "not a version": lock_text({"7.0": entry_json("7.0.0")}),
            "wrong archive": lock_text({SYNTHETIC: {**entry_json(), "archive": "workflow-9.9.9.tar.gz"}}),
            "short digest": lock_text({SYNTHETIC: {**entry_json(), "sha256": "ab"}}),
            "upper-case digest": lock_text({SYNTHETIC: {**entry_json(), "sha256": "AB" * 32}}),
            "unknown entry key": lock_text({SYNTHETIC: {**entry_json(), "note": "x"}}),
            "empty suites": lock_text({SYNTHETIC: entry_json(suites={})}),
            "bad count": lock_text({SYNTHETIC: entry_json(suites={"a_test.py": True})}),
            "exceptions not a list": lock_text({SYNTHETIC: entry_json(portability_exceptions={})}),
            "exception without a reason": lock_text({SYNTHETIC: entry_json(
                portability_exceptions=[{"suite": "a", "test": "b"}])}),
        }
        for name, text in cases.items():
            with self.subTest(name), self.assertRaises(LockError):
                tested_releases.parse_lock(text)

    def test_a_version_is_never_both_pinned_and_locked(self):
        pins = release_source.load_pins()
        pinned = pins.versions()[-1]
        lock = {pinned: LockEntry(pinned, package_module.archive_name(pinned), DIGEST, DIGEST)}
        with self.assertRaisesRegex(LockError, "both pinned and in the lock"):
            tested_releases.tested_pins(pins, lock)

    def test_a_lock_entry_must_be_newer_than_every_pin(self):
        pins = release_source.load_pins()
        lock = {"0.0.1": LockEntry("0.0.1", package_module.archive_name("0.0.1"), DIGEST, DIGEST)}
        with self.assertRaisesRegex(LockError, "older than the newest pin"):
            tested_releases.tested_pins(pins, lock)

    def test_the_tested_set_is_the_pins_plus_the_lock(self):
        pins = release_source.load_pins()
        empty = tested_releases.tested_versions(pins, {})
        self.assertEqual(empty, pins.versions())
        lock = {SYNTHETIC: LockEntry(SYNTHETIC, package_module.archive_name(SYNTHETIC),
                                     DIGEST, DIGEST, SUITES, ())}
        composite = tested_releases.tested_pins(pins, lock)
        self.assertEqual(composite.versions(), [*pins.versions(), SYNTHETIC])
        self.assertEqual(composite.get(SYNTHETIC).sha256, DIGEST)
        # The shipped pins are not touched: the CLI never reads the lock.
        self.assertNotIn(SYNTHETIC, release_source.load_pins().releases)

    def test_the_override_names_the_lock_a_run_reads(self):
        self.assertEqual(tested_releases.lock_path({}), tested_releases.LOCK_PATH)
        self.assertEqual(tested_releases.lock_path({tested_releases.OVERRIDE_ENV: "/x/l.json"}),
                         Path("/x/l.json"))
        self.assertEqual(tested_releases.OVERRIDE_ENV, "WORKFLOW_MANAGER_TESTED_RELEASES")

    def test_the_lock_is_test_data_the_wheel_does_not_carry(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text()
        self.assertNotIn("tested_releases", pyproject)
        src_text = "\n".join(p.read_text() for p in (REPO_ROOT / "src").rglob("*.py"))
        self.assertNotIn("tested_releases", src_text)
        self.assertNotIn("TESTED_RELEASES", src_text)

    def test_the_manifest_wins_over_the_lock_entry(self):
        entry = LockEntry(SYNTHETIC, package_module.archive_name(SYNTHETIC), DIGEST, DIGEST,
                          {"old_test.py": 1}, ())
        manifest = json.dumps({"manager": {"schema_version": 1, "conformance": {
            "suites": {"new_test.py": 5},
            "portability_exceptions": [{"suite": "new_test.py", "test": "T.t", "reason": "r"}]}}})
        suites, exceptions = tested_releases.lock_conformance(entry, manifest.encode())
        self.assertEqual(suites, {"new_test.py": 5})
        self.assertEqual([e["test"] for e in exceptions], ["T.t"])
        # No block in the manifest: the entry's own data, then a refusal without it.
        plain = json.dumps({"workflow_version": SYNTHETIC}).encode()
        self.assertEqual(tested_releases.lock_conformance(entry, plain)[0], {"old_test.py": 1})
        bare = LockEntry(SYNTHETIC, entry.archive, DIGEST, DIGEST)
        with self.assertRaisesRegex(LockError, "frozen suite counts"):
            tested_releases.lock_conformance(bare, None)


class _LockedRelease(unittest.TestCase):
    """A synthetic `7.0.2` published into a release-source directory beside
    symlinks to every real tested release, and a lock naming it."""

    #: The synthetic releases the class builds, each from the newest pin.
    synthetic = (SYNTHETIC, NEWER)

    @classmethod
    def setUpClass(cls):
        cls._class_tmp = tempfile.TemporaryDirectory()
        root = Path(cls._class_tmp.name)
        base = support.release(support.PINNED_VERSIONS[-1])
        cls.mirror = root / "mirror"
        cls.mirror.mkdir()
        for version in support.TESTED_VERSIONS:
            (cls.mirror / version).symlink_to(support.mirror_dir() / version)
        cls.trees = root / "trees"
        cls.built = {}
        for version in cls.synthetic:
            tree = tb.synthesize_next_release(base, cls.trees / version, version)
            cls.built[version] = package_module.build_package(tree.root, cls.mirror / version)

    @classmethod
    def tearDownClass(cls):
        cls._class_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.lock_file = self.tmp / "tested_releases.json"
        self.cache = self.tmp / "cache"

    def entry(self, version=SYNTHETIC, **extra) -> dict:
        built = self.built[version]
        return {"archive": built.archive.name, "sha256": package_module.file_sha256(built.archive),
                "manifest_sha256": package_module.file_sha256(built.manifest), **extra}

    def write_lock(self, releases: dict) -> Path:
        self.lock_file.write_text(lock_text(releases))
        return self.lock_file

    def env(self, **extra) -> dict:
        """A subprocess environment: the mirror as the source, a private cache,
        the lock as the override, discovery off (the tests' default). Each is
        set here, never inherited: `cli_env` turns discovery on for the
        parent's own nonempty lock."""
        return cli_env(**{release_source.SOURCE_ENV: str(self.mirror),
                          release_source.CACHE_ENV: str(self.cache),
                          release_source.PINNED_ONLY_ENV: "1",
                          tested_releases.OVERRIDE_ENV: str(self.lock_file), **extra})

    def python(self, code: str, env: dict | None = None, cwd: Path = TESTS):
        env = dict(env or self.env())
        env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(TESTS)])
        return subprocess.run([sys.executable, "-B", "-c", code], cwd=str(cwd), env=env,
                              capture_output=True, text=True)

    def tool(self, *args, env=None):
        proc = subprocess.run([sys.executable, "-B", str(LOCK_TOOL), *args], env={
            **(env or self.env()), "PYTHONPATH": ""}, capture_output=True, text=True)
        return proc

    def checkout(self) -> Path:
        """A minimal checkout for `priming.prime`: this tree's `src/` and the
        lock reader, with the lock file next to it."""
        root = self.tmp / "checkout"
        (root / "tests").mkdir(parents=True)
        (root / "src").symlink_to(REPO_ROOT / "src")
        shutil.copy2(TESTS / "tested_releases.py", root / "tests" / "tested_releases.py")
        shutil.copy2(self.lock_file, root / "tests" / "tested_releases.json")
        return root


class TestTheTestedSetFromALock(_LockedRelease):
    def test_support_derives_the_set_the_matrix_and_the_counts_from_the_override(self):
        self.write_lock({SYNTHETIC: self.entry(suites=SUITES, portability_exceptions=[
            {"suite": "workflow_state_test.py", "test": "T.t", "reason": "r"}])})
        proc = self.python(
            "import json, support\n"
            "from parallel import matrix\n"
            "print(json.dumps({'tested': support.TESTED_VERSIONS[-2:], 'pinned': "
            "support.PINNED_VERSIONS[-1], 'newest': support.NEWEST_RELEASE, "
            "'from': support.UPGRADE_FROM, 'suites': support.CI_SUITES[support.NEWEST_RELEASE], "
            "'exceptions': {k: sorted(v) for k, v in "
            "support.expected_portability_exceptions(support.NEWEST_RELEASE).items()}, "
            "'matrix': sorted({v for v, _ in matrix.FROZEN_MATRIX.values()}), "
            "'fixtures': len(matrix.FROZEN_MATRIX)}))")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertEqual(got["tested"], [got["pinned"], SYNTHETIC])
        self.assertEqual(got["newest"], SYNTHETIC)
        self.assertEqual(got["from"], got["pinned"])
        self.assertEqual(got["suites"], SUITES)
        self.assertEqual(got["exceptions"], {"workflow_state_test.py": ["T.t"]})
        self.assertEqual(got["matrix"], [SYNTHETIC])
        self.assertEqual(got["fixtures"], 4)

    def test_a_lock_that_contradicts_the_pins_fails_support_at_import(self):
        pinned = release_source.load_pins().versions()[-1]
        self.write_lock({pinned: {**self.entry(), "archive": package_module.archive_name(pinned)}})
        proc = self.python("import support")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("both pinned and in the lock", proc.stderr)

    def test_the_selection_differs_when_the_lock_does(self):
        """A shard running against another lock plans other frozen units, so its
        `selection_digest` differs from the plan's and the run is refused."""
        self.write_lock({})
        code = ("import json\nfrom parallel import matrix\n"
                "print(json.dumps(sorted(matrix.FROZEN_MATRIX)))\n"
                "print(json.dumps(sorted(set(v for v, _ in matrix.FROZEN_MATRIX.values()))))")
        plain = self.python(code)
        self.write_lock({SYNTHETIC: self.entry(suites=SUITES)})
        locked = self.python(code)
        self.assertEqual((plain.returncode, locked.returncode), (0, 0), plain.stderr + locked.stderr)
        # An empty lock tests the pins alone, whatever this process's own lock.
        self.assertEqual(json.loads(plain.stdout.splitlines()[1]), [support.PINNED_VERSIONS[-1]])
        self.assertEqual(json.loads(locked.stdout.splitlines()[1]), [SYNTHETIC])


class TestPrimingAndTheEndToEndRun(_LockedRelease):
    """Priming through the composite pins, then the whole path with a release in
    the lock and not in the pins (RA-L1-003): `support.release()`, a CLI-driven
    bootstrap-then-update, and the discovered-record assertion helper."""

    def test_priming_resolves_the_tested_set_from_the_mirror(self):
        self.write_lock({SYNTHETIC: self.entry(suites=SUITES)})
        report = priming.prime(self.checkout(), self.env())
        self.assertEqual(report["versions"], [*release_source.load_pins().versions(), SYNTHETIC])
        entry = self.cache / SYNTHETIC
        self.assertTrue((entry / "complete").is_file())
        # Primed under the lock's digests: no SOURCE file (trusted as a pin), so the
        # runner's stray-entry check accepts it as a tested version.
        self.assertFalse((entry / "SOURCE").exists())
        self.assertEqual(priming.stray_entries(str(self.cache), set(), report["versions"]), [])

    def test_a_lock_digest_that_the_package_does_not_match_is_refused(self):
        wrong = self.entry(suites=SUITES)
        wrong["sha256"] = DIGEST
        self.write_lock({SYNTHETIC: wrong})
        with self.assertRaises(priming.PrimingError):
            priming.prime(self.checkout(), self.env())

    def test_support_and_the_cli_run_a_release_that_only_the_lock_names(self):
        self.write_lock({SYNTHETIC: self.entry(suites=SUITES)})
        priming.prime(self.checkout(), self.env())
        target = empty_repo(self.tmp / "consumer")
        script = f"""
import json, subprocess, sys, tempfile
from pathlib import Path
import support
from workflow_manager.installation import Installation
assert support.NEWEST_RELEASE == {SYNTHETIC!r}, support.NEWEST_RELEASE
assert support.release({SYNTHETIC!r}).version == {SYNTHETIC!r}
private = Path(tempfile.mkdtemp())
env = support.mirror_env(private / "cache")
def cli(*args):
    return subprocess.run([sys.executable, "-m", "workflow_manager", *args], env=env,
                          capture_output=True, text=True)
first = cli("--release-version", support.UPGRADE_FROM, "bootstrap", {str(target)!r})
second = cli("update", {str(target)!r})
record = Installation.read(Path({str(target)!r}))
print(json.dumps({{"codes": [first.returncode, second.returncode],
                   "err": first.stderr + second.stderr,
                   "version": record.workflow_version, "source": record.source,
                   "expected": support.expected_source_record({SYNTHETIC!r}),
                   "pinned": support.expected_source_record(support.UPGRADE_FROM)}}))
"""
        proc = self.python(script)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertEqual(got["codes"], [0, 0], got["err"])
        self.assertEqual(got["version"], SYNTHETIC)
        self.assertEqual(got["source"], got["expected"])
        self.assertEqual(got["source"]["trust"], "discovered")
        self.assertEqual(release_source.load_pins().source_record(
            release_source.load_pins().versions()[-1]), got["pinned"])


class TestTheLockTool(_LockedRelease):
    def test_add_writes_digests_and_leaves_pins_alone(self):
        self.write_lock({})
        proc = self.tool("--lock", str(self.lock_file), "--release-source", str(self.mirror),
                         "add", SYNTHETIC)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        written = tested_releases.load_lock(self.lock_file)
        self.assertEqual(written[SYNTHETIC].sha256, self.entry()["sha256"])
        self.assertEqual(written[SYNTHETIC].manifest_sha256, self.entry()["manifest_sha256"])
        # The synthetic manifest has no `conformance` block: the counts come from the
        # payload, by the runner's own discovery, and the exceptions default to none.
        self.assertEqual(written[SYNTHETIC].portability_exceptions, ())
        self.assertIsNotNone(written[SYNTHETIC].suites)
        self.assertEqual(self.tool("--lock", str(self.lock_file), "--release-source",
                                   str(self.mirror), "check").returncode, 0)

    def test_add_refuses_a_pinned_version_a_duplicate_and_a_digest_mismatch(self):
        self.write_lock({})
        pinned = release_source.load_pins().versions()[-1]
        args = ("--lock", str(self.lock_file), "--release-source", str(self.mirror))
        refused = self.tool(*args, "add", pinned)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("is pinned", refused.stderr)
        self.assertIn("no lock change is needed", refused.stderr)
        self.assertEqual(tested_releases.load_lock(self.lock_file), {})
        self.assertEqual(self.tool(*args, "add", SYNTHETIC).returncode, 0)
        self.assertIn("already in the lock", self.tool(*args, "add", SYNTHETIC).stderr)
        # A published SHA256SUMS that disagrees with the archive is refused, nothing written.
        broken = self.tmp / "broken"
        shutil.copytree(self.mirror / SYNTHETIC, broken / NEWER, symlinks=True)
        (broken / NEWER / "SHA256SUMS").write_text(
            (self.mirror / SYNTHETIC / "SHA256SUMS").read_text().replace(SYNTHETIC, NEWER))
        before = self.lock_file.read_text()
        bad = self.tool("--lock", str(self.lock_file), "--release-source", str(broken), "add", NEWER)
        self.assertEqual(bad.returncode, 1, bad.stderr)
        self.assertEqual(self.lock_file.read_text(), before)

    def test_check_finds_a_digest_that_differs_from_the_published_one(self):
        wrong = self.entry()
        wrong["sha256"] = DIGEST
        self.write_lock({SYNTHETIC: wrong})
        proc = self.tool("--lock", str(self.lock_file), "--release-source", str(self.mirror), "check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("differ from the published", proc.stderr)

    def test_check_refuses_a_malformed_lock_and_an_entry_that_is_pinned(self):
        self.lock_file.write_text("{")
        self.assertEqual(self.tool("--lock", str(self.lock_file), "--release-source",
                                   str(self.mirror), "check").returncode, 1)
        pinned = release_source.load_pins().versions()[-1]
        self.write_lock({pinned: {**self.entry(), "archive": package_module.archive_name(pinned)}})
        proc = self.tool("--lock", str(self.lock_file), "--release-source", str(self.mirror), "check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("both pinned", proc.stderr)

    def test_latest_adds_the_newest_published_release_and_never_the_committed_lock(self):
        committed = tested_releases.LOCK_PATH.read_text()
        self.write_lock({})
        out = self.tmp / "nightly.json"
        proc = self.tool("--lock", str(self.lock_file), "--release-source", str(self.mirror),
                         "latest", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lock = tested_releases.load_lock(out)
        self.assertEqual(list(lock), [NEWER])
        self.assertEqual(lock[NEWER].sha256, self.entry(NEWER)["sha256"])
        self.assertEqual(tested_releases.LOCK_PATH.read_text(), committed)
        self.assertEqual(json.loads(self.lock_file.read_text())["releases"], {})

    def test_latest_changes_nothing_when_nothing_newer_is_published(self):
        only_pins = self.tmp / "pins-only"
        only_pins.mkdir()
        # Built from the pins, never from the tested set: a release in this
        # process's own lock would be the newer one `latest` adds.
        for version in support.PINNED_VERSIONS:
            (only_pins / version).symlink_to(support.mirror_dir() / version)
        self.write_lock({})
        out = self.tmp / "nightly.json"
        proc = self.tool("--lock", str(self.lock_file), "--release-source", str(only_pins),
                         "latest", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(tested_releases.load_lock(out), {})

    def test_the_tool_has_a_usage_exit(self):
        self.assertEqual(self.tool("bogus").returncode, 2)


class TestThePackageProofIsDeterministic(_LockedRelease):
    """RA-E1: a Workflow release published since the pins cannot change the
    Manager's own package proof."""

    @staticmethod
    def _load_package_tool():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "release_package_tool", REPO_ROOT / "tools" / "release" / "package.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_wheel_commands_run_pinned_only(self):
        tool = self._load_package_tool()
        with unittest.mock.patch.dict(os.environ, {tool.PINNED_ONLY_ENV: "0"}):
            self.assertEqual(tool.wheel_env()[tool.PINNED_ONLY_ENV], "1")
        source = (REPO_ROOT / "tools" / "release" / "package.py").read_text()
        for command in ('"--version"', '"releases"', '"verify"'):
            line = next(line for line in source.splitlines()
                        if "_run([" in line and f", {command}" in line)
            self.assertIn("env=env", line, command)

    def test_a_published_but_unpinned_release_does_not_change_what_releases_lists(self):
        """`releases` of the pinned-only wheel lists exactly the pins, with a newer
        release discoverable in the environment's source and no listing asked."""
        tool = self._load_package_tool()
        env = {**self.env(), "PYTHONPATH": str(REPO_ROOT / "src"),
               release_source.PINNED_ONLY_ENV: "0"}
        env.update({k: v for k, v in tool.wheel_env().items()
                    if k == tool.PINNED_ONLY_ENV})
        proc = subprocess.run([sys.executable, "-m", "workflow_manager", "releases"], env=env,
                              capture_output=True, text=True, cwd=str(self.tmp))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        tool.check_releases_output(proc.stdout, tool.expected_release_versions(REPO_ROOT))
        self.assertNotIn(SYNTHETIC, proc.stdout)
        self.assertNotIn(NEWER, proc.stdout)

    def test_the_wheels_entry_point_is_only_called_through_package_py(self):
        """The verify workflow and the release workflow run no `workflow-manager`
        command of their own: they go through `package.py`."""
        for path in (VERIFY_WORKFLOW, RELEASE_WORKFLOW):
            text = path.read_text()
            lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
            for line in lines:
                self.assertIsNone(
                    re.search(r"(^|[\s;&|(])workflow-manager\s+(?!verif)", line), (path.name, line))
                self.assertNotIn("python3 -m workflow_manager", line, path.name)
                self.assertNotIn("workflow_manager.cli", line, path.name)
        self.assertIn("tools/release/package.py", VERIFY_WORKFLOW.read_text())
        self.assertIn("tools/release/package.py", RELEASE_WORKFLOW.read_text())


class TestSelfVerifyOfAnUnpinnedInstallation(_LockedRelease):
    """#56: this checkout's own `verify` -- `package.py`'s and the runner's
    `TestManagedWorkflowUntouched` -- passes when the installation records a
    tested release that has no pin, from an offline source of the tested set
    alone, and still refuses a release outside it."""

    def setUp(self):
        super().setUp()
        self.write_lock({SYNTHETIC: self.entry(suites=SUITES)})
        # The release cache the self-checks read, empty until `prime()` puts
        # the lock-only release in it, as the runner and package.py do first.
        self.primed = self.tmp / "primed"
        patcher = unittest.mock.patch.dict(os.environ, {
            "PYTHONPATH": str(REPO_ROOT / "src"),
            release_source.SOURCE_ENV: str(self.mirror),
            release_source.CACHE_ENV: str(self.primed),
            release_source.PINNED_ONLY_ENV: "1",
            tested_releases.OVERRIDE_ENV: str(self.lock_file)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def installed_at(self, version: str) -> Path:
        target = empty_repo(self.tmp / f"consumer-{version}")
        env = self.env(**{release_source.PINNED_ONLY_ENV: "0",
                          release_source.CACHE_ENV: str(self.tmp / "install-cache")})
        proc = subprocess.run([sys.executable, "-B", "-m", "workflow_manager",
                               "--release-version", version, "bootstrap", str(target)],
                              env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return target

    def workdir(self) -> Path:
        return Path(tempfile.mkdtemp(dir=self.tmp))

    def prime(self) -> Path:
        """The lock-only release in the primed cache under the lock's digests."""
        where = release_source.ReleaseSource.select(
            environ={release_source.SOURCE_ENV: str(self.mirror)})
        pins = tested_releases.tested_pins(lock=tested_releases.load_lock(self.lock_file))
        return release_source.ReleaseCache(self.primed, where, pins).ensure(SYNTHETIC)

    def blocked_network(self) -> list:
        """Every way the Manager reaches a release source, made to record the
        attempt and fail; the list it returns holds the attempts."""
        attempts = []

        def blocked(name):
            def refuse(*args, **kwargs):
                attempts.append(name)
                raise AssertionError(f"{name} reached the network")
            return refuse
        for name in ("fetch", "read", "listing", "inspect"):
            patcher = unittest.mock.patch.object(release_source.ReleaseSource, name,
                                                 blocked(name))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = unittest.mock.patch("urllib.request.urlopen", blocked("urlopen"))
        patcher.start()
        self.addCleanup(patcher.stop)
        # The default source: GitHub, which the reviewer's probe saw fetched.
        patcher = unittest.mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(release_source.SOURCE_ENV)
        return attempts

    def test_the_environment_is_the_lock_release_alone_offline(self):
        self.prime()
        env = tested_releases.self_verify_env(self.installed_at(SYNTHETIC), self.workdir())
        self.assertEqual(env[release_source.PINNED_ONLY_ENV], "0")
        mirror = Path(env[release_source.SOURCE_ENV])
        self.assertEqual([p.name for p in mirror.iterdir()], [SYNTHETIC])
        self.assertNotEqual(env[release_source.CACHE_ENV], str(self.primed))
        self.assertTrue((self.primed / SYNTHETIC / "complete").is_file())
        self.assertFalse((self.primed / SYNTHETIC / "SOURCE").exists(), "bound by the lock")

    def test_any_other_record_keeps_the_proof_pinned_only(self):
        for repo in (self.installed_at(NEWER), empty_repo(self.tmp / "unmanaged")):
            env = tested_releases.self_verify_env(repo, self.workdir())
            self.assertEqual(env[release_source.PINNED_ONLY_ENV], "1")
            self.assertEqual(env[release_source.SOURCE_ENV], str(self.mirror))
        self.assertFalse((self.primed / NEWER).exists())

    def test_a_cache_miss_fails_without_a_fetch(self):
        target = self.installed_at(SYNTHETIC)
        attempts = self.blocked_network()
        with self.assertRaisesRegex(LockError, r"never fetches.*python3 tests/run_all\.py --list"):
            tested_releases.self_verify_env(target, self.workdir())
        tool = TestThePackageProofIsDeterministic._load_package_tool()
        with self.assertRaisesRegex(tool.PackageError, "never fetches"):
            tool.self_verify([sys.executable, "-B", "-m", "workflow_manager"], target,
                             self.workdir())
        self.assertEqual(attempts, [])
        self.assertFalse((self.primed / SYNTHETIC).exists())

    def test_an_invalid_cache_entry_fails_without_a_fetch(self):
        target = self.installed_at(SYNTHETIC)
        entry = self.prime()
        archive = entry / self.built[SYNTHETIC].archive.name
        archive.write_bytes(archive.read_bytes() + b"tampered")
        before = archive.read_bytes()
        attempts = self.blocked_network()
        with self.assertRaisesRegex(LockError, "never fetches"):
            tested_releases.self_verify_env(target, self.workdir())
        self.assertEqual(attempts, [])
        self.assertEqual(archive.read_bytes(), before, "neither repaired nor refetched")

    def test_a_lock_digest_the_assets_do_not_match_is_refused(self):
        target = self.installed_at(SYNTHETIC)
        self.prime()
        wrong = self.entry(suites=SUITES)
        wrong["sha256"] = DIGEST
        self.write_lock({SYNTHETIC: wrong})
        tool = TestThePackageProofIsDeterministic._load_package_tool()
        with self.assertRaises(tool.PackageError):
            tool.self_verify([sys.executable, "-B", "-m", "workflow_manager"], target,
                             self.workdir())

    def test_package_py_verifies_a_lock_only_installation(self):
        self.prime()
        tool = TestThePackageProofIsDeterministic._load_package_tool()
        command = [sys.executable, "-B", "-m", "workflow_manager"]
        tool.self_verify(command, self.installed_at(SYNTHETIC), self.workdir())
        with self.assertRaisesRegex(tool.PackageError, "no pin"):
            tool.self_verify(command, self.installed_at(NEWER), self.workdir())

    def test_the_runner_verifies_a_lock_only_installation(self):
        from test_parallel_runner import self_verify

        self.prime()
        proc = self_verify(self.installed_at(SYNTHETIC), self)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(f"installation matches workflow {SYNTHETIC}", proc.stdout)
        proc = self_verify(self.installed_at(NEWER), self)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("no pin", proc.stderr)


class TestTheVerifyWorkflow(unittest.TestCase):
    """The workflow file's cache keys, the nightly wiring and the absence of the
    override on pull-request events, parsed from the YAML."""

    @classmethod
    def setUpClass(cls):
        cls.text = VERIFY_WORKFLOW.read_text(encoding="utf-8")
        cls.doc = load_workflow_yaml(cls.text)
        cls.jobs = cls.doc["jobs"]

    def steps(self, job):
        return self.jobs[job]["steps"]

    def test_the_four_cache_restores_are_keyed_by_the_pins_and_the_lock(self):
        total = 0
        for job in ("plan", "shard", "package", "aggregate"):
            caches = [s for s in self.steps(job) if str(s.get("uses", "")).startswith("actions/cache@")]
            self.assertEqual(len(caches), 1, job)
            key = caches[0]["with"]["key"]
            for name in ("src/workflow_manager/published_releases.json", "tests/tested_releases.json"):
                self.assertIn(name, key, job)
            # The nightly's set is not in the repository: its key adds the run id and the
            # restore key is the prefix of pins and lock alone, so pinned releases are restored.
            self.assertIn("github.run_id", key, job)
            self.assertIn("github.event_name == 'schedule'", key, job)
            restore = caches[0]["with"]["restore-keys"].strip()
            self.assertTrue(key.startswith(restore.split("${{")[0]), job)
            self.assertNotIn("run_id", restore, job)
            total += 1
        self.assertEqual(total, 4)

    def test_the_plan_job_adds_the_newest_release_on_the_schedule_only(self):
        plan = self.steps("plan")
        latest = [s for s in plan if "release_lock.py latest" in (s.get("run") or "")]
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["if"].strip(), "${{ github.event_name == 'schedule' }}")
        self.assertIn("GITHUB_TOKEN", latest[0]["env"])
        self.assertEqual(self.jobs["plan"]["outputs"]["lock"], "${{ steps.lock.outputs.lock }}")
        self.assertLess(plan.index(latest[0]), next(
            i for i, s in enumerate(plan) if s.get("id") == "plan"))
        self.assertIn("WORKFLOW_MANAGER_TESTED_RELEASES=", latest[0]["run"])

    def test_every_job_that_runs_tests_receives_the_lock_on_the_schedule_only(self):
        for job in ("shard", "aggregate"):
            steps = self.steps(job)
            handed = [s for s in steps if "WORKFLOW_MANAGER_TESTED_RELEASES" in (s.get("run") or "")]
            self.assertEqual(len(handed), 1, job)
            self.assertEqual(handed[0]["if"].strip(), "${{ github.event_name == 'schedule' }}")
            self.assertEqual(handed[0]["env"]["LOCK"], "${{ needs.plan.outputs.lock }}")
            runs = next(i for i, s in enumerate(steps) if "tests/run_all.py" in (s.get("run") or ""))
            self.assertLess(steps.index(handed[0]), runs, job)

    def test_nothing_else_sets_the_override(self):
        """Pull-request and `main` runs never set it: it appears only in the steps above,
        each guarded by the schedule event (the plan's step by its `if`)."""
        for job, steps in self.jobs.items():
            for step in steps["steps"]:
                if "WORKFLOW_MANAGER_TESTED_RELEASES" in (step.get("run") or "") or \
                        "WORKFLOW_MANAGER_TESTED_RELEASES" in json.dumps(step.get("env", {})):
                    self.assertIn("schedule", step.get("if", ""), (job, step.get("name")))
        self.assertNotIn("WORKFLOW_MANAGER_TESTED_RELEASES", json.dumps(self.doc.get("env", {})))


class TestTheScratchCheckoutsCarryTheLock(unittest.TestCase):
    def test_a_scratch_checkout_tests_only_its_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            from test_parallel_runner import scratch_checkout

            root = scratch_checkout(Path(tmp) / "scratch")
            self.assertEqual(json.loads((root / "tests" / "tested_releases.json").read_text()),
                             {"schema_version": 1, "releases": {}})
            self.assertTrue((root / "tests" / "tested_releases.py").is_file())
            self.assertEqual(canonical_json({"schema_version": 1, "releases": {}}),
                             (root / "tests" / "tested_releases.json").read_text())


class TestANonEmptyLockKeepsTheRunnerAndTheHostTestsGreen(_LockedRelease):
    """RA-EXT-001: the committed lock is empty, so nothing else exercises a lock
    that selects a newer release. A child process gets a lock naming `7.1.0`,
    once as its committed file and once as the nightly's override, and the
    runner's planning and the host tests that read the lock run under it: an
    empty-committed-lock assertion, frozen orphan ids naming a fixed release, a
    pinned-only expectation or a "pins only" mirror built from the tested set
    fails here."""

    synthetic = (SYNTHETIC, NEWER, LOCKED)

    #: Host tests whose expectation depends on the lock the process reads.
    HOST_TARGETS = (
        "test_tested_releases.TestLockShape.test_the_committed_lock_is_valid_whether_empty_or_not",
        "test_tested_releases.TestTheTestedSetFromALock.test_the_selection_differs_when_the_lock_does",
        "test_tested_releases.TestTheLockTool."
        "test_latest_changes_nothing_when_nothing_newer_is_published",
        "test_discovery.TestTestsStayHermetic.test_the_default_test_environment_is_pinned_only",
    )

    def locked(self) -> str:
        """Prime `7.1.0` into the private cache and return its lock text, in
        the committed file's own format."""
        lock = tested_releases.parse_lock(lock_text({LOCKED: self.entry(
            LOCKED, suites=support.CI_SUITES[support.PINNED_VERSIONS[-1]],
            portability_exceptions=[])}))
        text = tested_releases.dump_lock(lock)
        self.lock_file.write_text(text)
        priming.prime(self.checkout(), self.env())
        return text

    def committed_tests_dir(self, text: str) -> Path:
        """This tree's `tests/` with `text` as its committed lock: every entry
        a symlink except the lock reader, copied so that its `LOCK_PATH` is
        the lock beside it."""
        root = self.tmp / "committed-tests"
        root.mkdir()
        for entry in TESTS.iterdir():
            if entry.name not in ("tested_releases.py", "tested_releases.json", "__pycache__"):
                (root / entry.name).symlink_to(entry)
        shutil.copy2(TESTS / "tested_releases.py", root / "tested_releases.py")
        (root / "tested_releases.json").write_text(text)
        return root

    def run_targets(self, env: dict, tests_dir: Path) -> None:
        env = {**env, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(tests_dir)])}
        for target in self.HOST_TARGETS:
            with self.subTest(target=target):
                proc = subprocess.run(
                    [sys.executable, "-B", "-c",
                     "import sys, unittest, support\n"
                     f"assert support.NEWEST_RELEASE == {LOCKED!r}, support.NEWEST_RELEASE\n"
                     "sys.exit(not unittest.main(module=None, argv=['x', sys.argv[1]], "
                     "exit=False).result.wasSuccessful())", target],
                    cwd=str(tests_dir), env=env, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_host_tests_pass_under_a_nonempty_committed_lock(self):
        tests_dir = self.committed_tests_dir(self.locked())
        self.run_targets(self.env(**{tested_releases.OVERRIDE_ENV: ""}), tests_dir)

    def test_the_host_tests_pass_under_the_nightly_override(self):
        self.locked()
        self.run_targets(self.env(), TESTS)

    def test_the_runner_plans_with_the_committed_orphan_declarations(self):
        self.locked()
        proc = self.python(
            "import json, support\n"
            "from parallel import inventory, planner, resources\n"
            "inv = inventory.discover(support.REPO_ROOT)\n"
            "loaded = resources.load(support.REPO_ROOT, list(inv.host), "
            "orphan_unit_ids=inv.unit_ids())\n"
            "frozen = sorted(u for u in loaded.orphan_sources if u.startswith('frozen:'))\n"
            "plan = planner.plan_checkout(support.REPO_ROOT, inv, "
            "inventory.select(inv.host, frozen, inv.frozen), profile='local')\n"
            "chunks = [c['units'] for s in plan['shards'] for c in s['chunks']]\n"
            "print(json.dumps({'frozen': frozen, 'alone': all([u] in chunks for u in frozen)}))")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertEqual(len(got["frozen"]), 4)
        self.assertTrue(all(u.startswith(f"frozen:{LOCKED}/") for u in got["frozen"]), got)
        self.assertTrue(got["alone"], got)


class TestLockedReleaseEnvironment(unittest.TestCase):
    def test_the_subprocess_environment_is_pinned_only_whatever_the_lock(self):
        """`_LockedRelease.env` sets discovery off itself: with this process's
        own lock nonempty, `cli_env` alone would turn it on."""
        case = types.SimpleNamespace(mirror=Path("/m"), cache=Path("/c"), lock_file=Path("/l"))
        with unittest.mock.patch.object(support, "LOCK", {"9.9.9": object()}), \
                unittest.mock.patch.object(support, "mirror_dir", return_value=Path("/x")), \
                unittest.mock.patch.object(support, "_lock_cache", return_value=Path("/y")):
            env = _LockedRelease.env(case)
        self.assertEqual(env[release_source.PINNED_ONLY_ENV], "1")
        self.assertEqual(env[release_source.SOURCE_ENV], "/m")
        self.assertEqual(env[release_source.CACHE_ENV], "/c")
        self.assertEqual(env[tested_releases.OVERRIDE_ENV], "/l")


class TestCliEnvFollowsTheLock(unittest.TestCase):
    def test_a_non_empty_lock_names_the_mirror_discovery_and_a_private_cache(self):
        from workflow_manager import source
        with unittest.mock.patch.object(support, "LOCK", {"9.9.9": object()}), \
                unittest.mock.patch.object(support, "mirror_dir", return_value=Path("/m")), \
                unittest.mock.patch.object(support, "_lock_cache", return_value=Path("/c")):
            env = cli_env()
            self.assertEqual(env[source.SOURCE_ENV], "/m")
            self.assertEqual(env[source.PINNED_ONLY_ENV], "0")
            self.assertEqual(env[source.CACHE_ENV], "/c")
            self.assertEqual(cli_env(**{source.PINNED_ONLY_ENV: "1"})[source.PINNED_ONLY_ENV], "1")
        with unittest.mock.patch.object(support, "LOCK", {}):
            self.assertEqual(cli_env()[source.PINNED_ONLY_ENV], "1")

    def test_a_child_reads_the_lock_this_process_reads(self):
        """The override is set in every `cli_env`, never inherited from
        elsewhere: this process's own, or empty for the committed file."""
        override = tested_releases.OVERRIDE_ENV
        with unittest.mock.patch.dict(os.environ, {override: "/nightly.json"}):
            self.assertEqual(cli_env()[override], "/nightly.json")
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop(override, None)
            self.assertEqual(cli_env()[override], "")

    def test_the_runners_git_ceiling_is_carried_and_only_when_set(self):
        name = "GIT_CEILING_DIRECTORIES"
        with unittest.mock.patch.dict(os.environ, {name: "/chunk:/mnt"}):
            self.assertEqual(support.pinned_env()[name], "/chunk:/mnt")
            self.assertEqual(cli_env()[name], "/chunk:/mnt")
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop(name, None)
            self.assertNotIn(name, support.pinned_env())
            self.assertNotIn(name, cli_env())


if __name__ == "__main__":
    unittest.main()
