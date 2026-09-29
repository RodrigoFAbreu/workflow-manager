#!/usr/bin/env python3
"""The Manager's own version report and release packaging.

Checkpoint CP2 of `workflow-manager-trunk-model`: `--version`'s order of
answers (`D-Version-Report`), with installed metadata faked through an
injected lookup and every checkout branch a real temporary git repository
under `$TMPDIR`; the missing-distribution hint; and the pure parts of
`tools/release/package.py` (`D-Artifact`) -- the copy set, `SHA256SUMS`, and
the exact `--version` comparison. The real build runs only in CI (INV-5).
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import REPO_ROOT

from workflow_manager import cli

PACKAGE_PY = REPO_ROOT / "tools" / "release" / "package.py"


def _load_package_tool():
    spec = importlib.util.spec_from_file_location("workflow_manager_package_tool", PACKAGE_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


package = _load_package_tool()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _metadata(version):
    return lambda: version


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def make_repo(self, path: Path) -> Path:
        path.mkdir(parents=True)
        _git(path, "init", "-q", "-b", "main")
        _git(path, "config", "user.email", "t@example.invalid")
        _git(path, "config", "user.name", "t")
        _git(path, "config", "commit.gpgsign", "false")
        _git(path, "config", "tag.gpgsign", "false")
        (path / "tracked.txt").write_text("one\n")
        _git(path, "add", "tracked.txt")
        _git(path, "commit", "-q", "-m", "feat: first")
        return path


class InstalledMetadataTest(_Tmp):
    """Branch 1: a release version in the installed metadata wins."""

    def test_a_release_version_is_reported_as_is(self):
        root = self.make_repo(self.tmp / "repo")
        _git(root, "tag", "v9.9.9")
        self.assertEqual(cli.version_text(root, _metadata("1.4.2")), "workflow-manager 1.4.2")

    def test_a_release_version_needs_no_checkout(self):
        self.assertEqual(cli.version_text(self.tmp, _metadata("2.0.0")), "workflow-manager 2.0.0")

    def test_the_placeholder_is_not_a_release_version(self):
        self.assertEqual(cli.version_text(self.tmp, _metadata("0.0.0.dev0")),
                         "workflow-manager development build")

    def test_missing_metadata_falls_through(self):
        self.assertEqual(cli.version_text(self.tmp, _metadata(None)),
                         "workflow-manager development build")

    def test_the_default_lookup_answers_none_when_not_installed(self):
        with mock.patch.object(cli, "DISTRIBUTION_NAME", "workflow-manager-not-installed-xyz"):
            self.assertIsNone(cli._installed_version())


class CheckoutAtTagTest(_Tmp):
    """Branch 2: a clean checkout whose HEAD is a strict tag is that release."""

    def setUp(self):
        super().setUp()
        self.root = self.make_repo(self.tmp / "repo")

    def version(self):
        return cli.version_text(self.root, _metadata("0.0.0.dev0"))

    def test_a_clean_checkout_at_a_strict_tag(self):
        _git(self.root, "tag", "v1.2.3")
        self.assertEqual(self.version(), "workflow-manager 1.2.3 (checkout at v1.2.3)")

    def test_the_highest_strict_tag_on_head_wins(self):
        for tag in ("v1.9.0", "v1.10.0", "workflow-manager-v1.0.0", "v2.0"):
            _git(self.root, "tag", tag)
        self.assertEqual(self.version(), "workflow-manager 1.10.0 (checkout at v1.10.0)")

    def test_an_annotated_tag_counts(self):
        _git(self.root, "tag", "-a", "-m", "release", "v3.0.0")
        self.assertEqual(self.version(), "workflow-manager 3.0.0 (checkout at v3.0.0)")

    def test_a_tracked_modification_is_a_development_build(self):
        _git(self.root, "tag", "v1.2.3")
        (self.root / "tracked.txt").write_text("two\n")
        self.assertEqual(self.version(), "workflow-manager development build (v1.2.3-dirty)")

    def test_an_untracked_file_does_not_make_it_dirty(self):
        _git(self.root, "tag", "v1.2.3")
        (self.root / "untracked.txt").write_text("x\n")
        self.assertEqual(self.version(), "workflow-manager 1.2.3 (checkout at v1.2.3)")

    def test_a_commit_past_the_tag_is_a_development_build(self):
        _git(self.root, "tag", "v1.2.3")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", "fix: later")
        head = _git(self.root, "rev-parse", "--short", "HEAD")
        self.assertEqual(self.version(), f"workflow-manager development build (v1.2.3-1-g{head})")

    def test_only_legacy_tags_on_head_is_a_development_build(self):
        _git(self.root, "tag", "workflow-manager-v1.0.0")
        self.assertEqual(self.version(),
                         "workflow-manager development build (workflow-manager-v1.0.0)")


class DevelopmentBuildTest(_Tmp):
    """Branch 3, and every Git failure falling through to it."""

    def test_an_untagged_checkout_is_described_by_its_commit(self):
        root = self.make_repo(self.tmp / "repo")
        head = _git(root, "rev-parse", "--short", "HEAD")
        self.assertEqual(cli.version_text(root, _metadata(None)),
                         f"workflow-manager development build ({head})")

    def test_not_a_git_work_tree(self):
        self.assertEqual(cli.version_text(self.tmp, _metadata(None)),
                         "workflow-manager development build")

    def test_a_directory_inside_an_unrelated_repository_is_not_a_checkout(self):
        # A wheel without release metadata installed into a .venv inside some
        # other repository: MANAGER_ROOT is below that repository's top, whose
        # strict tag is not the Manager's version.
        other = self.make_repo(self.tmp / "other")
        _git(other, "tag", "v7.7.7")
        site = other / ".venv" / "lib" / "python3.12"
        site.mkdir(parents=True)
        self.assertEqual(cli.version_text(site, _metadata("0.0.0.dev0")),
                         "workflow-manager development build")

    def test_git_missing_falls_through(self):
        root = self.make_repo(self.tmp / "repo")
        _git(root, "tag", "v1.2.3")
        with mock.patch.object(cli.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertEqual(cli.version_text(root, _metadata(None)),
                             "workflow-manager development build")

    def test_a_git_timeout_falls_through(self):
        root = self.make_repo(self.tmp / "repo")
        timeout = subprocess.TimeoutExpired(["git"], cli._GIT_TIMEOUT_SECONDS)
        with mock.patch.object(cli.subprocess, "run", side_effect=timeout):
            self.assertEqual(cli.version_text(root, _metadata(None)),
                             "workflow-manager development build")

    def test_a_failing_describe_falls_through(self):
        root = self.make_repo(self.tmp / "repo")
        real = cli._git

        def fake(path, *args):
            return None if args[:1] == ("describe",) else real(path, *args)

        with mock.patch.object(cli, "_git", side_effect=fake):
            self.assertEqual(cli.version_text(root, _metadata(None)),
                             "workflow-manager development build")

    def test_a_failing_status_is_not_a_release(self):
        root = self.make_repo(self.tmp / "repo")
        _git(root, "tag", "v1.2.3")
        real = cli._git

        def fake(path, *args):
            return None if args[:1] == ("status",) else real(path, *args)

        with mock.patch.object(cli, "_git", side_effect=fake):
            self.assertEqual(cli.version_text(root, _metadata(None)),
                             "workflow-manager development build (v1.2.3)")


class VersionFlagTest(unittest.TestCase):
    """`--version` needs no subcommand and runs no Git call otherwise."""

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                cli.main(argv)
        return caught.exception.code, out.getvalue(), err.getvalue()

    def test_version_needs_no_subcommand(self):
        with mock.patch.object(cli, "version_text", return_value="workflow-manager 5.6.7"):
            code, out, err = self.run_main(["--version"])
        self.assertIn(code, (0, None))
        self.assertEqual(out, "workflow-manager 5.6.7\n")
        self.assertEqual(err, "")

    def test_version_wins_over_a_subcommand(self):
        with mock.patch.object(cli, "version_text", return_value="workflow-manager 5.6.7"):
            code, out, _ = self.run_main(["--version", "releases"])
        self.assertIn(code, (0, None))
        self.assertEqual(out, "workflow-manager 5.6.7\n")

    def test_an_ordinary_command_never_computes_the_version(self):
        with mock.patch.object(cli, "version_text", side_effect=AssertionError("computed")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["releases"]), 0)

    def test_the_real_entry_point_prints_one_line(self):
        env_src = str(REPO_ROOT / "src")
        proc = subprocess.run([sys.executable, "-c",
                               "import sys; sys.path.insert(0, sys.argv[1]); "
                               "from workflow_manager.cli import main; main(['--version'])",
                               env_src], capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout, r"^workflow-manager \S.*\n$")


class MissingDistributionHintTest(_Tmp):
    """Without `distribution/workflow/`, every command that needs a release
    names the likely cause (a wheel install) and the fix (`--manager-root`)."""

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--manager-root", str(self.tmp), *argv])
        return code, out.getvalue(), err.getvalue()

    def assert_hint(self, err):
        self.assertIn(f"no Workflow releases at {self.tmp / 'distribution' / 'workflow'}", err)
        self.assertIn("installed from a wheel, not run from a checkout", err)
        self.assertIn("--manager-root <workflow-manager checkout at the matching tag>", err)
        self.assertNotIn("migrate.py", err)

    def test_releases(self):
        code, out, err = self.run_cli("releases")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assert_hint(err)

    def test_bootstrap_and_update(self):
        target = self.tmp / "target"
        target.mkdir()
        for command in ("bootstrap", "update"):
            with self.subTest(command=command):
                code, _, err = self.run_cli(command, str(target))
                self.assertEqual(code, 2)
                self.assert_hint(err)

    def test_verify_and_status_of_a_managed_target(self):
        for command in ("verify", "status"):
            with self.subTest(command=command):
                code, _, err = self.run_cli(command, str(REPO_ROOT))
                self.assertEqual(code, 2)
                self.assert_hint(err)

    def test_a_pinned_release_version(self):
        code, _, err = self.run_cli("--release-version", "2.6.0", "status", str(self.tmp))
        self.assertEqual(code, 2)
        self.assert_hint(err)

    def test_status_of_an_unmanaged_target_needs_no_release(self):
        code, out, err = self.run_cli("status", str(self.tmp))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")

    def test_the_checkout_itself_still_lists_its_releases(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--manager-root", str(REPO_ROOT), "releases"]), 0)
        self.assertIn("2.6.0", out.getvalue())


class PackageCopySetTest(_Tmp):
    """The wheel and sdist are built from `pyproject.toml`, `README.md` and
    `src/` only -- never `distribution/`, tests or build debris."""

    def test_the_live_copy_set(self):
        dest = self.tmp / "project"
        dest.mkdir()
        copied = package.copy_project(REPO_ROOT, dest)
        self.assertIn("pyproject.toml", copied)
        self.assertIn("README.md", copied)
        self.assertIn("src/workflow_manager/cli.py", copied)
        for path in copied:
            with self.subTest(path=path):
                self.assertTrue(path in ("pyproject.toml", "README.md") or path.startswith("src/"))
                self.assertNotIn("__pycache__", path)
                self.assertNotIn(".egg-info", path)

    def test_debris_is_not_copied(self):
        source = self.tmp / "source"
        (source / "src" / "pkg" / "__pycache__").mkdir(parents=True)
        (source / "src" / "pkg.egg-info").mkdir(parents=True)
        (source / "distribution").mkdir()
        (source / "pyproject.toml").write_text('version = "0.0.0.dev0"\n')
        (source / "README.md").write_text("readme\n")
        (source / "src" / "pkg" / "__init__.py").write_text("")
        (source / "src" / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"\0")
        (source / "src" / "pkg" / "stale.pyc").write_bytes(b"\0")
        (source / "src" / "pkg.egg-info" / "PKG-INFO").write_text("x")
        (source / "distribution" / "big").write_text("x")
        dest = self.tmp / "dest"
        dest.mkdir()
        self.assertEqual(package.copy_project(source, dest),
                         ["README.md", "pyproject.toml", "src/pkg/__init__.py"])

    def test_a_missing_input_is_refused(self):
        source = self.tmp / "source"
        (source / "src").mkdir(parents=True)
        (source / "pyproject.toml").write_text("")
        dest = self.tmp / "dest"
        dest.mkdir()
        with self.assertRaisesRegex(package.PackageError, "README.md is missing"):
            package.copy_project(source, dest)

    def test_the_copy_takes_the_version_and_the_checkout_does_not(self):
        dest = self.tmp / "project"
        dest.mkdir()
        package.copy_project(REPO_ROOT, dest)
        before = (REPO_ROOT / "pyproject.toml").read_bytes()
        package.set_version(dest, "1.2.3")
        self.assertIn('\nversion = "1.2.3"\n', (dest / "pyproject.toml").read_text())
        self.assertEqual((REPO_ROOT / "pyproject.toml").read_bytes(), before)


class Sha256SumsTest(_Tmp):
    def test_format_order_and_self_exclusion(self):
        files = {"workflow_manager-1.2.3.tar.gz": b"sdist", "b.whl": b"", "A.txt": b"a\n"}
        for name, data in files.items():
            (self.tmp / name).write_bytes(data)
        (self.tmp / "subdir").mkdir()
        (self.tmp / package.SUMS_NAME).write_text("stale\n")
        path = package.write_sha256sums(self.tmp)
        expected = "".join(f"{hashlib.sha256(files[n]).hexdigest()}  {n}\n"
                           for n in sorted(files))
        self.assertEqual(path.read_text(), expected)

    def test_sha256sum_accepts_it(self):
        (self.tmp / "x.whl").write_bytes(b"wheel")
        (self.tmp / "x.tar.gz").write_bytes(b"sdist")
        package.write_sha256sums(self.tmp)
        try:
            proc = subprocess.run(["sha256sum", "--check", "--strict", package.SUMS_NAME],
                                  cwd=self.tmp, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            self.skipTest("sha256sum is not installed")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_an_empty_directory_is_refused(self):
        with self.assertRaisesRegex(package.PackageError, "no files"):
            package.sha256sums_text(self.tmp)


class VersionOutputCheckTest(unittest.TestCase):
    def test_exact_match(self):
        package.check_version_output("workflow-manager 1.2.3\n", "1.2.3")

    def test_mismatches(self):
        for output in ("workflow-manager 1.2.4", "workflow-manager 1.2.3 (checkout at v1.2.3)",
                       "workflow-manager development build", "workflow-manager 1.2.3.dev0",
                       "workflow_manager 1.2.3", "", "workflow-manager 1.2.3\nextra"):
            with self.subTest(output=output):
                with self.assertRaises(package.PackageError):
                    package.check_version_output(output, "1.2.3")

    def test_releases_output(self):
        out = "2.3.1  from workflow-v2.3.1 (1f954fbb6c68)  [upstream]  10 files\n2.4.0  from x\n"
        package.check_releases_output(out, ["2.4.0", "2.3.1"])
        with self.assertRaises(package.PackageError):
            package.check_releases_output(out, ["2.3.1"])
        with self.assertRaises(package.PackageError):
            package.check_releases_output("", ["2.3.1"])

    def test_the_live_release_set(self):
        versions = package.expected_release_versions(REPO_ROOT)
        self.assertIn("2.6.0", versions)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--manager-root", str(REPO_ROOT), "releases"])
        package.check_releases_output(out.getvalue(), versions)


class PackageCliTest(_Tmp):
    """Refusals that happen before any build is attempted."""

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(PACKAGE_PY), *args], capture_output=True,
                              text=True, timeout=120)

    def test_a_v_prefixed_version_is_refused(self):
        proc = self.run_tool("--version", "v1.2.3", "--out", str(self.tmp / "out"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("is not X.Y.Z", proc.stderr)
        self.assertFalse((self.tmp / "out").exists())

    def test_a_non_empty_out_dir_is_refused(self):
        out = self.tmp / "out"
        out.mkdir()
        (out / "leftover.whl").write_bytes(b"")
        proc = self.run_tool("--version", "1.2.3", "--out", str(out))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("is not empty", proc.stderr)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_tool("--out", str(self.tmp)).returncode, 2)


if __name__ == "__main__":
    unittest.main()
