#!/usr/bin/env python3
"""`doctor` and `update --dry-run` never write the target (plan 3.6).

Destinations are decided by path arithmetic before anything is written; the
commands then run in a fresh process under a write-observing audit hook, with
path/mode/byte snapshots of the work tree and of the actual and common Git
directories taken before and after. The hook sees only the Manager's own
process; the Git subprocesses are covered by the hermetic contract and the
final-state snapshots (plus a trace of the Git commands that ran).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from support import NEWEST_RELEASE, REPO_ROOT, UPGRADE_FROM, cli_env

import audit_hook
import workflow_manager.compatibility as comp
from frozen_runs import build_bootstrapped_repo
from workflow_manager import source
from workflow_manager.fixture import init_git_repo
from workflow_manager.compatibility import ContainmentError, plan_destinations

DRIVER = r"""
import json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
import audit_hook
out, argv, protected = sys.argv[3], json.loads(sys.argv[4]), json.loads(sys.argv[5])
audit_hook.install(protected)
from workflow_manager import cli
code = cli.main(argv)
with open(out, "w") as handle:
    json.dump({"exit": code, "violations": audit_hook.VIOLATIONS}, handle)
"""

ALLOWED_GIT = {"rev-parse", "worktree", "config", "ls-files", "check-attr", "status", "log"}
FORBIDDEN_GIT = {"fetch", "gc", "maintenance", "add", "commit", "checkout", "reset", "restore",
                 "clean", "pull", "update-index", "stash", "merge", "rebase"}


def tree_snapshot(root: Path) -> dict:
    """Path -> (kind, mode, bytes or link text) for everything under `root`,
    `.git` included."""
    found = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            found[rel] = ("link", 0, os.readlink(path).encode())
        elif path.is_file():
            found[rel] = ("file", path.stat().st_mode & 0o7777, path.read_bytes())
        else:
            found[rel] = ("dir", path.stat().st_mode & 0o7777, b"")
    return found


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout


class Base(unittest.TestCase):
    """One bootstrapped, committed repository (`UPGRADE_FROM`, so an update
    has work to do), copied per test."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pristine = build_bootstrapped_repo(support.release(UPGRADE_FROM),
                                               Path(cls._tmp.name) / "pristine")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.addCleanup(self._work.cleanup)
        self.work = Path(self._work.name)
        self.repo = self.work / "repo"
        shutil.copytree(self.pristine, self.repo, symlinks=True)
        self.cache = self.work / "cache"
        shutil.copytree(source.cache_root(), self.cache, symlinks=True)

    def protected(self, repo: Path | None = None) -> list[str]:
        repo = repo or self.repo
        paths = {str(repo.resolve())}
        for flag in ("--absolute-git-dir", "--git-common-dir"):
            printed = git(repo, "rev-parse", flag).strip()
            paths.add(str((repo / printed).resolve()))
        return sorted(paths)

    def run_audited(self, argv, repo: Path | None = None, protected=None, **env):
        out = self.work / "audit.json"
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env.setdefault(source.CACHE_ENV, str(self.cache))
        proc = subprocess.run(
            [sys.executable, "-c", DRIVER, str(REPO_ROOT / "src"), str(REPO_ROOT / "tests"),
             str(out), json.dumps(argv), json.dumps(protected or self.protected(repo))],
            cwd=str(self.work), capture_output=True, text=True, env=cli_env(**env))
        result = json.loads(out.read_text()) if out.exists() else {"exit": None, "violations": []}
        return proc, result


# ---------------------------------------------------------------------------
# Destinations: path arithmetic only
# ---------------------------------------------------------------------------


class TestPlanDestinations(Base):
    def destinations(self, env=None, cache=None, versions=(), repo=None):
        env = {"HOME": str(self.work)} if env is None else env
        opts = mock.Mock(release_cache=str(cache if cache is not None else self.cache))
        return plan_destinations(opts, env, repo or self.repo, versions)

    def test_a_target_under_the_system_temporary_directory_is_accepted(self):
        found = self.destinations()
        self.assertEqual(found.cache_root, self.cache.resolve())
        self.assertNotIn(self.repo.resolve(), [found.snapshot_parent, *found.snapshot_parent.parents])
        self.assertTrue(found.snapshot_parent.is_dir())

    def test_a_temporary_directory_named_in_the_environment_inside_the_target_is_refused(self):
        link = self.work / "link-to-git"
        link.symlink_to(self.repo / ".git")
        for name in ("TMPDIR", "TEMP", "TMP"):
            for value in (self.repo, self.repo / ".git", self.repo / "docs", link):
                with self.subTest(name=name, value=str(value)), \
                        self.assertRaises(ContainmentError):
                    self.destinations(env={name: str(value)})

    def test_an_outside_temporary_directory_is_the_snapshot_parent(self):
        elsewhere = self.work / "tmp"
        elsewhere.mkdir()
        self.assertEqual(self.destinations(env={"TMPDIR": str(elsewhere)}).snapshot_parent,
                         elsewhere.resolve())

    def test_nothing_is_created_and_tempfile_is_never_asked(self):
        before = tree_snapshot(self.repo)
        with mock.patch("tempfile.gettempdir", side_effect=AssertionError("gettempdir")), \
                mock.patch("tempfile.mkdtemp", side_effect=AssertionError("mkdtemp")), \
                mock.patch("tempfile.mkstemp", side_effect=AssertionError("mkstemp")):
            self.destinations(versions=[NEWEST_RELEASE])
            with self.assertRaises(ContainmentError):
                self.destinations(env={"TMPDIR": str(self.repo)})
        self.assertEqual(tree_snapshot(self.repo), before)

    def test_no_usable_temporary_directory_is_refused(self):
        with mock.patch("os.access", return_value=False), self.assertRaises(ContainmentError):
            self.destinations()

    def test_a_cache_root_inside_the_target_is_refused(self):
        link = self.work / "cache-link"
        link.symlink_to(self.repo / ".git")
        for cache in (self.repo / "cache", self.repo / ".git" / "cache", link, link / "x"):
            with self.subTest(cache=str(cache)), self.assertRaises(ContainmentError):
                self.destinations(cache=cache)

    def test_a_cache_root_from_the_environment_is_checked_too(self):
        opts = mock.Mock(release_cache=None)
        with self.assertRaises(ContainmentError):
            plan_destinations(opts, {source.CACHE_ENV: str(self.repo / "c")}, self.repo)
        with self.assertRaises(ContainmentError):
            plan_destinations(opts, {"XDG_CACHE_HOME": str(self.repo)}, self.repo)

    def test_a_lock_leaf_or_version_directory_that_is_a_link_into_the_target_is_refused(self):
        for leaf in (f"{NEWEST_RELEASE}.lock", NEWEST_RELEASE):
            cache = self.work / f"cache-{leaf}"
            cache.mkdir()
            for aim in (self.repo / "new-file", self.repo / ".git" / "x"):
                with self.subTest(leaf=leaf, aim=str(aim)):
                    (cache / leaf).unlink(missing_ok=True)
                    (cache / leaf).symlink_to(aim)
                    with self.assertRaises(ContainmentError):
                        self.destinations(cache=cache, versions=[NEWEST_RELEASE])
        self.assertFalse((self.repo / "new-file").exists())

    def test_a_link_inside_an_existing_version_directory_is_refused(self):
        (self.cache / NEWEST_RELEASE / "tree" / "stray").symlink_to(self.work)
        with self.assertRaises(ContainmentError):
            self.destinations(versions=[NEWEST_RELEASE])

    def test_a_cache_inside_a_linked_worktrees_common_git_directory_is_refused(self):
        linked = self.work / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(linked))
        for repo in (linked, self.repo):
            with self.subTest(repo=str(repo)), self.assertRaises(ContainmentError):
                self.destinations(cache=self.repo / ".git" / "worktrees" / "c", repo=repo)

    def test_a_relative_git_common_dir_is_resolved_against_the_target(self):
        # `rev-parse --git-common-dir` prints `.git` here; the process cwd is elsewhere.
        self.assertEqual(git(self.repo, "rev-parse", "--git-common-dir").strip(), ".git")
        previous = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, previous)
        with self.assertRaises(ContainmentError):
            self.destinations(cache=self.repo / ".git" / "c")

    def test_a_git_directory_that_cannot_be_resolved_fails_closed(self):
        with mock.patch.object(comp, "run_git", return_value=comp.GitResult(128, "")), \
                self.assertRaises(ContainmentError):
            self.destinations()

    def test_a_target_with_no_git_directory_protects_its_work_tree(self):
        bare = self.work / "plain"
        bare.mkdir()
        with self.assertRaises(ContainmentError):
            self.destinations(cache=bare / "c", repo=bare)
        self.assertEqual(self.destinations(repo=bare).protected, (bare.resolve(),))


class TestContainmentFailsClosed(Base):
    """Every Git lookup the containment decision rests on, failing in turn,
    below a linked worktree and at a root: the destination is refused and
    nothing is created inside either Git directory."""

    def failing(self, flag, returncode):
        real = comp.run_git

        def run(repo, *args, **kwargs):
            if flag in args:
                return comp.GitResult(returncode, "")
            return real(repo, *args, **kwargs)
        return mock.patch.object(comp, "run_git", run)

    def targets(self):
        linked = self.work / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(linked))
        below = linked / "component"
        shutil.copytree(self.pristine, below, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        common = self.repo / ".git"
        shutil.copytree(self.cache, common / "mgr-cache", symlinks=True)
        return {"below a linked worktree": below, "a linked worktree": linked, "a root": self.repo}, common

    def test_a_failed_lookup_refuses_both_commands_and_creates_nothing_in_a_git_directory(self):
        targets, common = self.targets()
        for flag in ("--absolute-git-dir", "--git-common-dir"):
            for returncode in (None, 1, 128):
                for label, target in targets.items():
                    for command in ("doctor", "update --dry-run"):
                        with self.subTest(flag=flag, returncode=returncode, target=label,
                                          command=command):
                            git_dirs = [Path(p) for p in self.protected(target) if p != str(target.resolve())]
                            before = [tree_snapshot(d) for d in git_dirs]
                            locks = sorted(common.rglob("*.lock"))
                            argv = [command.split()[0], str(target), *command.split()[1:]]
                            err = []
                            with self.failing(flag, returncode), \
                                    mock.patch.dict(os.environ, {source.CACHE_ENV: str(common / "mgr-cache")}), \
                                    mock.patch("sys.stderr") as stderr:
                                code = support_main(argv)
                                err = "".join(c.args[0] for c in stderr.write.call_args_list)
                            self.assertNotEqual(code, 0)
                            self.assertIn("could not check containment", err)
                            self.assertEqual([tree_snapshot(d) for d in git_dirs], before)
                            self.assertEqual(sorted(common.rglob("*.lock")), locks)

    def test_a_listing_that_prints_a_missing_directory_is_refused(self):
        real = comp.run_git

        def run(repo, *args, **kwargs):
            if "--git-common-dir" in args:
                return comp.GitResult(0, str(self.work / "nowhere") + "\n")
            return real(repo, *args, **kwargs)
        with mock.patch.object(comp, "run_git", run), self.assertRaises(ContainmentError):
            plan_destinations(mock.Mock(release_cache=str(self.cache)), {"HOME": str(self.work)},
                              self.repo, ())

    def test_a_plain_directory_that_git_reports_as_no_repository_is_still_accepted(self):
        plain = self.work / "plain-dir"
        plain.mkdir()
        self.assertEqual(plan_destinations(mock.Mock(release_cache=str(self.cache)),
                                           {"HOME": str(self.work)}, plain, ()).protected,
                         (plain.resolve(),))

    def test_a_timed_out_lookup_in_a_plain_directory_is_refused(self):
        plain = self.work / "plain-dir"
        plain.mkdir()
        with mock.patch.object(comp, "run_git", return_value=comp.GitResult(None, "")), \
                self.assertRaises(ContainmentError):
            plan_destinations(mock.Mock(release_cache=str(self.cache)), {"HOME": str(self.work)},
                              plain, ())


def support_main(argv):
    from workflow_manager import cli
    return cli.main(argv)


class TestResolverIsReadOnly(Base):
    def test_a_lock_leaf_that_is_a_link_fails_before_any_write(self):
        cache = self.work / "linked-cache"
        cache.mkdir()
        (cache / f"{NEWEST_RELEASE}.lock").symlink_to(self.repo / "new-file")
        resolver = source.ReleaseCache(cache, None, source.load_pins())
        with self.assertRaises(source.ReleaseUnavailableError):
            resolver.resolve(NEWEST_RELEASE, read_only=True)
        self.assertFalse((self.repo / "new-file").exists())

    def test_the_snapshot_is_made_under_the_given_parent(self):
        parent = self.work / "snapshots"
        parent.mkdir()
        resolver = source.ReleaseCache(self.cache, None, source.load_pins())
        with resolver.resolve(NEWEST_RELEASE, snapshot_parent=parent, read_only=True) as release:
            self.assertEqual(release.root.parent, parent)
        self.assertEqual(list(parent.iterdir()), [])


# ---------------------------------------------------------------------------
# The commands, in a fresh process, observed
# ---------------------------------------------------------------------------


#: What a refused destination exits: `status` ends 1 (3.5a), the others 2.
REFUSED_EXIT = {"status": 1}

COMMANDS = {
    "doctor": ["doctor"],
    "update --dry-run": ["update", "--dry-run"],
    "update --dry-run --force": ["update", "--dry-run", "--force"],
}


#: The commands whose whole runs are audited for writes: `status` joined them in
#: Operator UX (3.5a); the filter-specific tests below stay with `COMMANDS`.
AUDITED = {**COMMANDS, "status": ["status"]}


class TestCommandsDoNotWriteTheTarget(Base):
    def argv(self, command, repo=None):
        verb, *rest = AUDITED[command]
        return [verb, str(repo or self.repo), *rest]

    def check(self, command, repo=None, expected=(0, 1), **env):
        repo = repo or self.repo
        roots = [repo] + [Path(p) for p in self.protected(repo)]
        before = [tree_snapshot(r) for r in dict.fromkeys(roots)]
        proc, result = self.run_audited(self.argv(command, repo), repo, **env)
        self.assertIn(result["exit"], expected, proc.stdout + proc.stderr)
        self.assertEqual(result["violations"], [], proc.stderr)
        self.assertEqual([tree_snapshot(r) for r in dict.fromkeys(roots)], before)
        return proc, result

    def test_nothing_is_written_to_the_work_tree_or_the_git_directory(self):
        for command in AUDITED:
            with self.subTest(command=command):
                self.check(command)

    def test_a_dirty_tree_is_not_touched_either(self):
        (self.repo / "scratch.txt").write_text("untracked\n")
        (self.repo / "README.md").write_text("edited\n")
        git(self.repo, "add", "README.md")
        (self.repo / "README.md").write_text("edited again\n")
        for command in AUDITED:
            with self.subTest(command=command):
                self.check(command)

    def test_a_linked_worktree_and_the_common_git_directory_are_untouched(self):
        linked = self.work / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(linked))
        for command in AUDITED:
            for repo in (linked, self.repo):
                with self.subTest(command=command, repo=repo.name):
                    self.check(command, repo)

    def test_a_forbidden_temporary_directory_is_refused_before_anything_is_written(self):
        for value in (self.repo, self.repo / ".git"):
            for name in ("TMPDIR", "TEMP", "TMP"):
                for command in AUDITED:
                    with self.subTest(name=name, value=value.name, command=command):
                        proc, result = self.check(
                            command, expected=(REFUSED_EXIT.get(command, 2),),
                            **{name: str(value)})
                        self.assertIn("lies inside", proc.stderr)

    def test_a_cache_inside_the_target_is_refused_before_any_lock_exists(self):
        for command in AUDITED:
            with self.subTest(command=command):
                inside = self.repo / "new-cache"
                before = tree_snapshot(self.repo)
                proc, result = self.run_audited(
                    ["--release-cache", str(inside), *self.argv(command)])
                self.assertEqual(result["exit"], REFUSED_EXIT.get(command, 2),
                                 proc.stdout + proc.stderr)
                self.assertEqual(result["violations"], [])
                self.assertFalse(inside.exists())
                self.assertEqual(tree_snapshot(self.repo), before)

    def test_a_read_only_copy_runs(self):
        if os.geteuid() == 0:
            self.skipTest("a superuser ignores the permission bits")
        for path in [self.repo, *self.repo.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
        self.addCleanup(lambda: [p.chmod(p.stat().st_mode | 0o700)
                                 for p in [self.repo, *self.repo.rglob("*")] if not p.is_symlink()])
        for command in AUDITED:
            with self.subTest(command=command):
                self.check(command)

    def test_a_configured_fsmonitor_hook_never_runs(self):
        marker = self.work / "fsmonitor-ran"
        hook = self.work / "fsmonitor.sh"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        git(self.repo, "config", "core.fsmonitor", str(hook))
        git(self.repo, "config", "core.hooksPath", str(self.work / "hooks"))
        # `git config` itself changed .git/config: snapshot after, then run.
        for command in COMMANDS:
            with self.subTest(command=command):
                self.check(command)
        self.assertFalse(marker.exists())

    def test_a_configured_clean_filter_never_runs(self):
        marker = self.work / "filter-ran"
        readme = self.repo / "README.md"
        readme.write_text("tracked\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "r")
        git(self.repo, "config", "filter.review.clean", f"touch {marker}; cat")
        (self.repo / ".git" / "info").mkdir(exist_ok=True)
        (self.repo / ".git" / "info" / "attributes").write_text("README.md filter=review\n")
        readme.write_text("trackeX\n")   # same size, so only a filter run could tell
        for command in COMMANDS:
            with self.subTest(command=command):
                self.check(command)
        self.assertFalse(marker.exists())

    def test_a_filter_selected_outside_a_target_below_the_git_root_never_runs(self):
        marker = self.work / "filter-ran"
        parent = self.work / "parent"
        init_git_repo(parent)
        component = parent / "component"
        shutil.copytree(self.pristine, component, symlinks=True,
                        ignore=shutil.ignore_patterns(".git"))
        (parent / "outside.txt").write_text("tracked\n")
        (parent / ".gitattributes").write_text("outside.txt filter=x\n")
        git(parent, "add", "-A")
        git(parent, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "r")
        git(parent, "config", "filter.x.clean", f"touch {marker}; cat")
        (parent / "outside.txt").write_text("trackeX\n")   # same size
        for command in COMMANDS:
            with self.subTest(command=command):
                self.check(command, repo=component)
        self.assertFalse(marker.exists())

    def _filtered_root(self, root: Path, marker: Path) -> bool:
        """Make `root` a bootstrapped repository whose tracked README.md selects
        a clean filter, with the work tree edited so that only a filter run
        could tell. False when the filesystem refuses the name."""
        try:
            shutil.copytree(self.pristine, root, symlinks=True)
        except OSError:
            return False
        (root / "README.md").write_text("tracked\n")
        (root / ".gitattributes").write_text("README.md filter=x\n")
        git(root, "add", "README.md", ".gitattributes")
        git(root, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "r")
        return True

    def test_a_root_path_that_normalizes_to_another_repository_never_redirects_the_selection(self):
        # `repo ` and `repo\n` lose their last byte to a `.strip()`, `repo\rx`
        # reads back as `repo\nx` in text mode: each altered path names an
        # ordinary repository with no filter configured.
        marker = self.work / "filter-ran"
        for name, altered in (("repo ", "repo"), ("repo\n", "repo"), ("repo\rx", "repo\nx")):
            ordinary = self.work / altered
            if not ordinary.exists():
                shutil.copytree(self.pristine, ordinary, symlinks=True)
            root = self.work / name
            if not self._filtered_root(root, marker):
                continue
            below = root / "component"
            shutil.copytree(self.pristine, below, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            linked = self.work / (name + "-linked")
            git(root, "worktree", "add", "-q", "-b", "side-" + str(len(name)) + str(ord(name[-1])),
                str(linked))
            git(root, "config", "filter.x.clean", f"touch {marker}; cat")
            (root / "README.md").write_text("trackeX\n")   # same size
            (linked / "README.md").write_text("trackeX\n")
            for label, target in (("root", root), ("below the root", below), ("linked", linked)):
                for command in COMMANDS:
                    with self.subTest(root=name, target=label, command=command):
                        proc, _ = self.check(command, repo=target, expected=(0, 1, 2))
                        self.assertIn("clean/process filter", proc.stdout + proc.stderr)
                        self.assertFalse(marker.exists())

    def test_a_root_path_that_normalizes_to_another_repository_never_redirects_containment_or_witnesses(self):
        # The same names as the selection test above: `repo ` and `repo\n` lose
        # a byte to a `.strip()`, `repo\rx` reads back as `repo\nx` in text
        # mode. The neighbour holds a witness of its own; the target's Git
        # directory must still be protected and its own witness the one listed.
        for name, altered in (("repo ", "repo"), ("repo\n", "repo"), ("repo\rx", "repo\nx")):
            neighbour = self.work / altered
            if not neighbour.exists():
                shutil.copytree(self.pristine, neighbour, symlinks=True)
            (neighbour / ".git" / comp.CLAIMS_RELDIR).mkdir(parents=True, exist_ok=True)
            (neighbour / ".git" / comp.CLAIMS_RELDIR / "FOREIGN.amendment.json").write_text("{}")
            root = self.work / name
            try:
                shutil.copytree(self.pristine, root, symlinks=True)
            except OSError:
                continue
            below = root / "component"
            shutil.copytree(self.pristine, below, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            linked = self.work / (name + "-linked")
            git(root, "worktree", "add", "-q", "-b", "side-" + str(len(name)) + str(ord(name[-1])),
                str(linked))
            (root / ".git" / comp.CLAIMS_RELDIR).mkdir(parents=True, exist_ok=True)
            (root / ".git" / comp.CLAIMS_RELDIR / "MINE.amendment.json").write_text("{}")
            for label, target in (("root", root), ("below the root", below), ("linked", linked)):
                with self.subTest(root=name, target=label):
                    inside = root / ".git" / "mgr-cache"
                    with self.assertRaises(ContainmentError):
                        plan_destinations(mock.Mock(release_cache=str(inside)), {"HOME": str(self.work)},
                                          target, ())
                    if label != "below the root":
                        self.assertEqual(comp.read_repository(target).amendment_witnesses,
                                         ["MINE.amendment.json"])

    def test_a_clean_filter_configured_in_a_submodule_never_runs(self):
        marker = self.work / "filter-ran"
        sub = self.work / "sm-origin"
        init_git_repo(sub)
        (sub / "f.txt").write_text("tracked\n")
        git(sub, "add", "f.txt")
        git(sub, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "s")
        git(self.repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sm")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "r")
        inner = self.repo / "sm"
        git(inner, "config", "filter.r.clean", f"touch {marker}; cat")
        modules = self.repo / ".git" / "modules" / "sm" / "info"
        modules.mkdir(parents=True, exist_ok=True)
        (modules / "attributes").write_text("f.txt filter=r\n")
        (inner / "f.txt").write_text("trackeX\n")   # same size
        for command in COMMANDS:
            with self.subTest(command=command):
                self.check(command)
        self.assertFalse(marker.exists())

    def test_a_moved_gitlink_reads_as_dirty_without_running_a_submodule_filter(self):
        marker = self.work / "filter-ran"
        sub = self.work / "sm-origin"
        init_git_repo(sub)
        (sub / "f.txt").write_text("tracked\n")
        git(sub, "add", "f.txt")
        git(sub, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "s")
        git(self.repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sm")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "r")
        inner = self.repo / "sm"
        git(inner, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "move")
        # Configure the filter only after the move: the test's own commit must not run it.
        git(inner, "config", "filter.r.clean", f"touch {marker}; cat")
        modules = self.repo / ".git" / "modules" / "sm" / "info"
        modules.mkdir(parents=True, exist_ok=True)
        (modules / "attributes").write_text("f.txt filter=r\n")
        (inner / "f.txt").write_text("trackeX\n")   # same size
        for staged in (False, True):
            if staged:
                git(self.repo, "add", "sm")
            with self.subTest(staged=staged):
                facts = comp.read_repository(self.repo)
                self.assertIs(facts.dirty, True)
        self.assertFalse(marker.exists())

    def test_startup_writes_no_bytecode_without_the_suppressing_environment(self):
        source_copy = self.repo / "src"
        shutil.copytree(REPO_ROOT / "src", source_copy, ignore=shutil.ignore_patterns("__pycache__"))
        env = cli_env(PYTHONPATH=str(source_copy))
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env[source.CACHE_ENV] = str(self.cache)
        for command in COMMANDS:
            with self.subTest(command=command):
                subprocess.run([sys.executable, "-m", "workflow_manager", *self.argv(command)],
                               cwd=str(self.work), capture_output=True, text=True, env=env)
                written = sorted(p.relative_to(source_copy).as_posix()
                                 for p in source_copy.rglob("*.pyc"))
                # The package's own __init__ is compiled before it can set
                # sys.dont_write_bytecode: the one file that cannot be avoided.
                self.assertLessEqual(set(written), {"workflow_manager/__pycache__/__init__.cpython-%d%d.pyc"
                                                    % sys.version_info[:2]}, written)

    def test_only_the_contracted_git_commands_ran(self):
        trace = self.work / "trace2.json"
        proc, result = self.run_audited(["doctor", str(self.repo)], GIT_TRACE2_EVENT=str(trace))
        self.assertEqual(result["exit"], 0, proc.stdout + proc.stderr)
        seen = []
        for line in trace.read_text().splitlines():
            event = json.loads(line)
            if event.get("event") == "start":
                seen.append(set(event["argv"]))
        self.assertTrue(seen)
        for argv in seen:
            with self.subTest(argv=sorted(argv)[:6]):
                self.assertEqual(len(argv & ALLOWED_GIT), 1, argv)
                self.assertFalse(argv & FORBIDDEN_GIT, argv)
        ran = set().union(*seen)
        # An ordinary repository: both partial-clone probes exit 1, so the
        # object reads run (`status`, `log`) and nothing is incomplete.
        self.assertTrue({"status", "log"} <= ran)
        self.assertNotIn("incomplete", proc.stdout.lower())

    def test_a_configured_filter_is_decided_by_read_only_queries(self):
        """With a driver configured, `doctor` asks the index and the attributes
        which drivers tracked paths select, using only the contracted commands;
        it runs `status` exactly when none is selected."""
        marker = self.work / "filter-ran"
        config = self.work / "global-gitconfig"
        config.write_text(f'[filter "lfs"]\n\tclean = touch {marker}; cat\n'
                          f'\tprocess = touch {marker}; cat\n\trequired = true\n')
        readme = self.repo / "README.md"
        readme.write_text("tracked\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "r")
        for selected in (False, True):
            with self.subTest(selected=selected):
                (self.repo / ".gitattributes").write_text("README.md filter=lfs\n" if selected else "")
                readme.write_text("trackeX\n" if selected else "tracked\n")
                trace = self.work / "trace2.json"
                trace.unlink(missing_ok=True)
                proc, result = self.run_audited(["doctor", str(self.repo)], GIT_TRACE2_EVENT=str(trace),
                                                GIT_CONFIG_GLOBAL=str(config))
                self.assertIn(result["exit"], (0, 1), proc.stdout + proc.stderr)
                self.assertEqual(result["violations"], [])
                ran = set()
                for line in trace.read_text().splitlines():
                    event = json.loads(line)
                    if event.get("event") == "start":
                        self.assertFalse(set(event["argv"]) & FORBIDDEN_GIT, event["argv"])
                        self.assertEqual(len(set(event["argv"]) & ALLOWED_GIT), 1, event["argv"])
                        ran |= set(event["argv"])
                self.assertTrue({"ls-files", "check-attr"} <= ran, ran)
                self.assertEqual("status" in ran, not selected)
                self.assertFalse(marker.exists())

    def test_a_partial_clone_runs_no_object_read_and_no_fetch_helper(self):
        helper = self.work / "uploadpack.sh"
        marker = self.work / "uploadpack-ran"
        helper.write_text(f"#!/bin/sh\ntouch {marker}\n")
        helper.chmod(0o755)
        git(self.repo, "config", "extensions.partialClone", "origin")
        git(self.repo, "config", "remote.origin.url", str(self.work / "nowhere"))
        git(self.repo, "config", "remote.origin.promisor", "true")
        git(self.repo, "config", "remote.origin.uploadpack", str(helper))
        trace = self.work / "trace2.json"
        # run_git sets GIT_NO_LAZY_FETCH itself; the property without it is
        # covered by patching _GIT_ENVIRONMENT in test_compatibility.py.
        for extra in ({},):
            with self.subTest(env=extra):
                trace.unlink(missing_ok=True)
                proc, result = self.run_audited(["doctor", str(self.repo)],
                                                GIT_TRACE2_EVENT=str(trace), **extra)
                self.assertEqual(result["exit"], 1, proc.stdout + proc.stderr)
                self.assertIn("incomplete-inspection", proc.stdout)
                self.assertIn("partial clone", proc.stdout)
                ran = set()
                for line in trace.read_text().splitlines():
                    event = json.loads(line)
                    if event.get("event") == "start":
                        ran |= set(event["argv"])
                self.assertFalse(ran & {"status", "log"}, ran)
                self.assertFalse(marker.exists())


class TestTheAuditHookSeesWhatItExcludes(unittest.TestCase):
    """The observation proves what it claims: it flags every kind of write
    under a scratch target, with relative and `dir_fd` paths, and fails an
    event it cannot resolve."""

    CHILD = r"""
import json, os, shutil, sys
sys.path.insert(0, sys.argv[1])
import audit_hook
scratch = os.path.realpath(sys.argv[2])
audit_hook.install([scratch])
os.makedirs(scratch + "/tree/sub")
open(scratch + "/tree/sub/f", "w").write("x")
shutil.rmtree(scratch + "/tree")                      # dir_fd removals on 3.12+
os.chdir(scratch)
os.symlink("a", "link"); os.unlink("link")           # relative symlink, remove
fd = os.open("created", os.O_CREAT | os.O_WRONLY)    # os.open with O_CREAT
os.close(fd)
os.utime("created", (1, 1))
os.chmod("created", 0o600)
os.rename("created", "renamed")
dfd = os.open(scratch, os.O_RDONLY)
os.mkdir("viadirfd", dir_fd=dfd)
os.rmdir("viadirfd", dir_fd=dfd)
os.close(dfd)
try:
    os.utime("renamed", (1, 1), dir_fd=987654)        # a dir_fd that does not resolve
except OSError:
    pass
open("renamed").read()                                 # a read: never flagged
json.dump(audit_hook.VIOLATIONS, sys.stdout)
"""

    def test_every_write_is_flagged_and_an_unresolvable_event_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-c", self.CHILD, str(REPO_ROOT / "tests"), tmp],
                capture_output=True, text=True, check=True)
        found = json.loads(proc.stdout)
        text = "\n".join(found)
        for expected in ("os.mkdir", "os.remove", "os.rmdir", "os.symlink", "os.utime", "os.chmod",
                         "os.rename", "open"):
            self.assertIn(expected, text)
        self.assertTrue(any(line.startswith("UNRESOLVED os.utime") for line in found), found)
        # Two write opens (the file and the O_CREAT one); the final plain read is not flagged.
        self.assertEqual(sum(line.startswith("open ") for line in found), 2, found)


if __name__ == "__main__":
    unittest.main(verbosity=2)
