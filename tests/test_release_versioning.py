#!/usr/bin/env python3
"""Conventional Commit titles and tag-derived versions (`tools/release/release.py`).

Checkpoint CP1 of `workflow-manager-trunk-model`: the title grammar and its
release impact (`D-Title-Grammar`), strict tags, `next-version` from the
latest tag or the recorded baseline, `assert-not-superseded`,
`resolve-target`'s pick from injected run lists (`D-Version-Authority`),
`set-version`, and the `pyproject.toml` placeholder pin (INV-6). Every
history is a real temporary git repository under `$TMPDIR`.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

import test_parallel_runner as runner_tests
import test_release_workflows as release_tests
from parallel import canonical_json, planner
from workflow_manager.fixture import init_git_repo

RELEASE_PY = REPO_ROOT / "tools" / "release" / "release.py"


def _load_release_tool():
    spec = importlib.util.spec_from_file_location("workflow_manager_release_tool", RELEASE_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _load_release_tool()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RELEASE_PY), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=120)


class _Repo(unittest.TestCase):
    """A fresh repository per test; `commit` returns the new SHA."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        init_git_repo(self.repo)
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "config", "commit.gpgsign", "false")
        _git(self.repo, "config", "tag.gpgsign", "false")
        self._n = 0
        self.warnings: list[str] = []

    def commit(self, subject: str) -> str:
        self._n += 1
        (self.repo / f"f{self._n}").write_text(str(self._n))
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", subject)
        return _git(self.repo, "rev-parse", "HEAD")

    def tag(self, name: str, ref: str = "HEAD", annotated: bool = False) -> None:
        if annotated:
            _git(self.repo, "tag", "-a", "-m", name, name, ref)
        else:
            _git(self.repo, "tag", name, ref)

    def next_version(self, baseline_commit: str | None = None):
        baseline = ((1, 0, 0), baseline_commit or self.baseline)
        return release.next_version(self.repo, baseline=baseline, warn=self.warnings.append)


# -- D-Title-Grammar --------------------------------------------------------------


class TestTitleImpactTable(unittest.TestCase):
    EXPECTED = {
        "feat": "minor",
        "fix": "patch", "perf": "patch", "refactor": "patch", "build": "patch", "revert": "patch",
        "docs": "none", "chore": "none", "ci": "none", "test": "none", "style": "none",
    }

    def test_every_type_has_its_planned_impact(self):
        self.assertEqual(release.TYPE_IMPACT, self.EXPECTED)
        for type_, impact in self.EXPECTED.items():
            with self.subTest(type_=type_):
                self.assertEqual(release.parse_title(f"{type_}: do a thing").impact, impact)

    def test_bang_is_major_on_every_impact_row(self):
        for type_ in ("feat", "fix", "build", "docs", "chore", "ci", "test"):
            with self.subTest(type_=type_):
                self.assertEqual(release.parse_title(f"{type_}!: break it").impact, "major")
                self.assertEqual(release.parse_title(f"{type_}(cli)!: break it").impact, "major")

    def test_scopes(self):
        for scope in ("cli", "release/tools", "a.b_c-d", "v2"):
            with self.subTest(scope=scope):
                title = release.parse_title(f"fix({scope}): repair")
                self.assertEqual((title.type, title.scope, title.impact), ("fix", scope, "patch"))

    def test_github_squash_suffix_is_accepted(self):
        title = release.parse_title("feat(release): trunk model (#4)")
        self.assertEqual((title.type, title.impact), ("feat", "minor"))
        self.assertEqual(title.description, "trunk model (#4)")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(release.parse_title("  docs: x  \n").impact, "none")


class TestTitleRejections(unittest.TestCase):
    CASES = {
        "Add a feature": "no 'type: description' shape",
        "feat add a feature": "no 'type: description' shape",
        "": "no 'type: description' shape",
        "feature: add": "unknown type 'feature'",
        "Feat: add": "type 'Feat' must be lowercase",
        "FIX(cli): x": "type 'FIX' must be lowercase",
        "fix(): repair": "empty scope '()'",
        "fix(Cli): repair": "scope 'Cli' may only contain",
        "fix:repair": "no space after the colon",
        "fix:": "empty description",
        "fix:   ": "empty description",
        "fix(cli)!:": "empty description",
        "fix:  repair": "more than one space after the colon",
    }

    def test_each_rejection_names_its_failure(self):
        for title, reason in self.CASES.items():
            with self.subTest(title=title):
                with self.assertRaises(release.InvalidTitle) as ctx:
                    release.parse_title(title)
                self.assertIn(reason, str(ctx.exception))


class TestCheckTitleCli(unittest.TestCase):
    def test_valid_title_prints_type_and_impact(self):
        proc = _run_cli("check-title", "feat(cli)!: new flag (#7)")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "valid title: feat, release impact major")
        proc = _run_cli("check-title", "docs: readme")
        self.assertEqual(proc.stdout.strip(), "valid title: docs, release impact none")

    def test_invalid_title_exits_1_naming_failure_and_form(self):
        proc = _run_cli("check-title", "Update stuff")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid title: no 'type: description' shape", proc.stderr)
        self.assertIn("expected '<type>[(<scope>)][!]: <description>'", proc.stderr)
        self.assertIn("feat", proc.stderr)

    def test_usage_errors_exit_2(self):
        for argv in ([], ["check-title"], ["check-title", "a", "b"], ["no-such-command"],
                     ["resolve-target", "--repo", "o/r", "--trigger-sha", "abc", "--trigger-run", "1"],
                     ["resolve-target", "--repo", "o/r", "--trigger-sha", "a" * 40,
                      "--trigger-run", "x"]):
            with self.subTest(argv=argv):
                self.assertEqual(_run_cli(*argv).returncode, 2)


# -- strict tags ------------------------------------------------------------------


class TestStrictTags(unittest.TestCase):
    def test_only_strict_vxyz_counts(self):
        tags = ["v1.2.3", "v0.0.1", "v10.0.0", "workflow-manager-v1.0.0", "bootstrapper-v1.0.0-rc1",
                "1.2.3", "v1.2", "v1.2.3-rc1", "v01.2.3", "V1.2.3", "v1.2.3.4"]
        self.assertEqual(release.strict_tags(tags),
                         {"v1.2.3": (1, 2, 3), "v0.0.1": (0, 0, 1), "v10.0.0": (10, 0, 0)})

    def test_bump(self):
        self.assertEqual(release.bump((1, 4, 2), "major"), (2, 0, 0))
        self.assertEqual(release.bump((1, 4, 2), "minor"), (1, 5, 0))
        self.assertEqual(release.bump((1, 4, 2), "patch"), (1, 4, 3))
        with self.assertRaises(ValueError):
            release.bump((1, 4, 2), "none")

    def test_baseline_is_this_milestones_base(self):
        self.assertEqual(release.BASELINE_VERSION, (1, 0, 0))
        self.assertEqual(release.BASELINE_COMMIT, "b856a97346849fdf48bcdba2d6a5a9644699ab4b")


# -- next-version -----------------------------------------------------------------


class TestNextVersionFromBaseline(_Repo):
    def setUp(self):
        super().setUp()
        self.commit("chore: history before the baseline")
        self.baseline = self.commit("Merge pull request #3 from x/y")

    def test_baseline_gives_1_1_0_for_a_feat(self):
        self.commit("feat: trunk model (#4)")
        self.assertEqual(self.next_version(), "1.1.0")
        self.assertEqual(self.warnings, [])

    def test_empty_range_releases_nothing(self):
        self.assertIsNone(self.next_version())

    def test_none_only_range_releases_nothing(self):
        for subject in ("docs: a", "chore: b", "ci: c", "test: d", "style: e"):
            self.commit(subject)
        self.assertIsNone(self.next_version())

    def test_catch_up_takes_the_maximum_bump(self):
        self.commit("fix: a")
        self.commit("feat: b")
        self.commit("docs: c")
        self.assertEqual(self.next_version(), "1.1.0")
        self.commit("refactor!: d")
        self.assertEqual(self.next_version(), "2.0.0")

    def test_non_conventional_subject_is_a_patch_with_a_warning(self):
        self.commit("docs: a")
        self.commit("Hotfix pushed around protection")
        self.assertEqual(self.next_version(), "1.0.1")
        self.assertEqual(len(self.warnings), 1)
        self.assertIn("Hotfix pushed around protection", self.warnings[0])

    def test_baseline_must_be_an_ancestor_of_head(self):
        _git(self.repo, "checkout", "-q", "--orphan", "other")
        self.commit("feat: unrelated history")
        with self.assertRaisesRegex(release.ReleaseError, "not an ancestor of HEAD"):
            self.next_version()

    def test_unknown_baseline_refuses(self):
        self.commit("feat: x")
        with self.assertRaises(release.ReleaseError):
            self.next_version(baseline_commit="0" * 40)

    def test_only_first_parent_subjects_count(self):
        _git(self.repo, "checkout", "-q", "-b", "side")
        self.commit("feat: on a side branch")
        _git(self.repo, "checkout", "-q", "main")
        self.commit("docs: on main")
        _git(self.repo, "merge", "-q", "--no-ff", "-m", "chore: merge side", "side")
        self.assertIsNone(self.next_version())

    def test_legacy_tags_are_ignored(self):
        self.tag("workflow-manager-v1.0.0", annotated=True)
        self.tag("bootstrapper-v1.0.0-rc1")
        self.commit("fix: x")
        self.assertEqual(self.next_version(), "1.0.1")


class TestNextVersionFromTags(_Repo):
    def setUp(self):
        super().setUp()
        self.baseline = self.commit("chore: root")

    def test_latest_strict_tag_is_the_base(self):
        self.commit("feat: a")
        self.tag("v1.1.0")
        self.commit("fix: b")
        self.assertEqual(self.next_version(), "1.1.1")

    def test_highest_reachable_tag_wins_numerically(self):
        self.commit("feat: a")
        self.tag("v1.9.0")
        self.commit("feat: b")
        self.tag("v1.10.0", annotated=True)
        self.commit("feat: c")
        self.assertEqual(self.next_version(), "1.11.0")

    def test_unreachable_tags_are_not_the_base(self):
        self.commit("feat: a")
        self.tag("v1.1.0")
        _git(self.repo, "checkout", "-q", "-b", "side")
        self.commit("feat!: elsewhere")
        self.tag("v2.0.0")
        _git(self.repo, "checkout", "-q", "main")
        self.commit("fix: b")
        self.assertEqual(self.next_version(), "1.1.1")

    def test_nothing_since_the_tag_releases_nothing(self):
        self.commit("feat: a")
        self.tag("v1.1.0")
        self.assertIsNone(self.next_version())
        self.commit("ci: b")
        self.assertIsNone(self.next_version())

    def test_tag_ignores_the_baseline(self):
        self.commit("feat: a")
        self.tag("v3.0.0")
        self.commit("fix: b")
        self.assertEqual(self.next_version(baseline_commit="0" * 40), "3.0.1")

    def test_cli_prints_version_or_nothing(self):
        self.commit("feat: a")
        self.tag("v1.1.0")
        proc = _run_cli("next-version", cwd=self.repo)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)
        self.commit("Bypassed title")
        proc = _run_cli("next-version", "--repo-dir", str(self.repo))
        self.assertEqual((proc.returncode, proc.stdout), (0, "1.1.1\n"), proc.stderr)
        self.assertIn("::warning::", proc.stderr)

    def test_cli_refuses_without_tag_or_baseline_exit_1(self):
        self.commit("feat: a")
        proc = _run_cli("next-version", cwd=self.repo)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_cli_outside_a_repository_exits_1(self):
        proc = _run_cli("next-version", "--repo-dir", str(self.repo / "missing"))
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))


# -- assert-not-superseded --------------------------------------------------------


class TestAssertNotSuperseded(_Repo):
    def setUp(self):
        super().setUp()
        self.a = self.commit("feat: a")
        self.b = self.commit("fix: b")

    def test_tags_on_ancestors_pass(self):
        self.tag("v1.1.0", self.a)
        self.tag("v1.1.1", self.b, annotated=True)
        release.assert_not_superseded(self.repo)
        self.assertEqual(_run_cli("assert-not-superseded", cwd=self.repo).returncode, 0)

    def test_tag_on_a_non_ancestor_exits_3(self):
        self.tag("v1.1.1", self.b)
        _git(self.repo, "checkout", "-q", "--detach", self.a)
        with self.assertRaises(release.SupersededError):
            release.assert_not_superseded(self.repo)
        proc = _run_cli("assert-not-superseded", cwd=self.repo)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("v1.1.1", proc.stderr)

    def test_legacy_tags_are_not_considered(self):
        self.tag("workflow-manager-v1.0.0", self.b, annotated=True)
        _git(self.repo, "checkout", "-q", "--detach", self.a)
        release.assert_not_superseded(self.repo)

    def test_unreadable_repository_exits_1(self):
        proc = _run_cli("assert-not-superseded", "--repo-dir", str(self.repo / "missing"))
        self.assertEqual(proc.returncode, 1)


# -- resolve-target ---------------------------------------------------------------


def _run(run_id, sha, event="push", conclusion="success", status="completed"):
    return {"id": run_id, "head_sha": sha, "event": event, "conclusion": conclusion,
            "status": status, "head_branch": "main"}


class TestResolveTarget(_Repo):
    """Plan 5.4's interleaving and the fallbacks, over a real first-parent chain."""

    def setUp(self):
        super().setUp()
        self.r0 = self.commit("feat: r0")
        self.a = self.commit("fix: a")
        self.b = self.commit("fix: b")
        _git(self.repo, "update-ref", "refs/remotes/origin/main", self.b)

    def resolve(self, runs, trigger_sha, trigger_run, **kwargs):
        def fetch():
            if isinstance(runs, Exception):
                raise runs
            return runs
        return release.resolve_target(self.repo, trigger_sha, trigger_run, fetch,
                                      warn=self.warnings.append, **kwargs)

    def test_newest_green_push_run_wins(self):
        runs = [_run(30, self.b), _run(20, self.a), _run(10, self.r0)]
        self.assertEqual(self.resolve(runs, self.b, 30), (self.b, 30))
        self.assertEqual(self.warnings, [])

    def test_older_job_replacing_newer_pending_job_targets_the_newer(self):
        # R0 released; B's job pending; the older A's verification completes and
        # its job replaces B's. A's job must still release up to B.
        runs = [_run(20, self.a), _run(30, self.b), _run(10, self.r0)]
        self.assertEqual(self.resolve(runs, self.a, 20), (self.b, 30))

    def test_pull_request_red_and_incomplete_runs_are_ignored(self):
        runs = [_run(35, self.b, event="pull_request"), _run(34, self.b, conclusion="failure"),
                _run(33, self.b, conclusion="cancelled"), _run(32, self.b, status="in_progress"),
                _run(31, self.b, event="schedule"), _run(20, self.a)]
        self.assertEqual(self.resolve(runs, self.a, 20), (self.a, 20))

    def test_runs_off_mains_first_parent_are_ignored(self):
        _git(self.repo, "checkout", "-q", "-b", "side", self.a)
        side = self.commit("feat: side")
        _git(self.repo, "checkout", "-q", "main")
        _git(self.repo, "merge", "-q", "--no-ff", "-m", "chore: merge", "side")
        merge = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "update-ref", "refs/remotes/origin/main", merge)
        runs = [_run(50, side), _run(20, self.a)]
        self.assertEqual(self.resolve(runs, self.a, 20), (self.a, 20))
        runs = [_run(60, "f" * 40), _run(20, self.a)]
        self.assertEqual(self.resolve(runs, self.a, 20), (self.a, 20))

    def test_rerun_of_one_commit_takes_the_highest_run_id(self):
        runs = [_run(30, self.b), _run(31, self.b), _run(20, self.a)]
        self.assertEqual(self.resolve(runs, self.b, 30), (self.b, 31))

    def test_pick_that_does_not_descend_from_the_trigger_is_refused(self):
        _git(self.repo, "checkout", "-q", "--orphan", "rewritten")
        other = self.commit("feat: rewritten main")
        _git(self.repo, "update-ref", "refs/remotes/origin/main", other)
        with self.assertRaisesRegex(release.ReleaseError, "neither the triggering commit"):
            self.resolve([_run(40, other), _run(20, self.a)], self.a, 20)

    def test_pick_older_than_the_trigger_is_refused(self):
        with self.assertRaises(release.ReleaseError):
            self.resolve([_run(10, self.r0)], self.b, 30)

    def test_api_failure_falls_back_to_the_trigger(self):
        result = self.resolve(release.ReleaseError("gh api: HTTP 502"), self.a, 20)
        self.assertEqual(result, (self.a, 20))
        self.assertEqual(len(self.warnings), 1)
        self.assertIn("HTTP 502", self.warnings[0])

    def test_parse_failure_falls_back_to_the_trigger(self):
        for runs in ([{"id": 1}], [{"id": "x", "head_sha": self.b}], ["nope"], None):
            with self.subTest(runs=runs):
                self.warnings.clear()
                self.assertEqual(self.resolve(runs, self.a, 20), (self.a, 20))
                self.assertEqual(len(self.warnings), 1)

    def test_git_failure_falls_back_to_the_trigger(self):
        runs = [_run(30, self.b)]
        self.assertEqual(self.resolve(runs, self.a, 20, ref="refs/remotes/origin/nope"), (self.a, 20))
        self.assertEqual(len(self.warnings), 1)

    def test_no_candidate_falls_back_to_the_trigger(self):
        self.assertEqual(self.resolve([], self.a, 20), (self.a, 20))
        self.assertEqual(len(self.warnings), 1)

    def test_select_target_is_pure(self):
        chain = [self.b, self.a, self.r0]
        runs = [_run(20, self.a), _run(30, self.b)]
        self.assertEqual(release.select_target(runs, chain), (self.b, 30))
        self.assertEqual(release.select_target(list(reversed(runs)), chain), (self.b, 30))
        self.assertIsNone(release.select_target([], chain))

    def test_cli_falls_back_when_gh_is_unavailable(self):
        env_path = str(Path(self._tmp.name) / "empty-bin")
        Path(env_path).mkdir()
        git = shutil.which("git")
        (Path(env_path) / "git").symlink_to(git)
        proc = subprocess.run(
            [sys.executable, str(RELEASE_PY), "resolve-target", "--repo-dir", str(self.repo),
             "--repo", "o/r", "--trigger-sha", self.a, "--trigger-run", "20"],
            capture_output=True, text=True, timeout=120, env={"PATH": env_path},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, f"target_sha={self.a}\ntarget_run=20\n")
        self.assertIn("::warning::", proc.stderr)


# -- set-version ------------------------------------------------------------------


class TestSetVersion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        shutil.copy(REPO_ROOT / "pyproject.toml", self.dir / "pyproject.toml")
        self.checkout_bytes = (REPO_ROOT / "pyproject.toml").read_bytes()

    def tearDown(self):
        self.assertEqual((REPO_ROOT / "pyproject.toml").read_bytes(), self.checkout_bytes)

    def text(self) -> str:
        return (self.dir / "pyproject.toml").read_text()

    def test_rewrites_the_single_placeholder(self):
        release.set_version(self.dir, "1.2.3")
        self.assertIn('\nversion = "1.2.3"\n', self.text())
        self.assertEqual(self.text(), self.checkout_bytes.decode().replace(
            'version = "0.0.0.dev0"', 'version = "1.2.3"'))

    def test_accepts_a_local_version(self):
        proc = _run_cli("set-version", str(self.dir), "0.0.0+ci")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('\nversion = "0.0.0+ci"\n', self.text())

    def test_refuses_malformed_versions(self):
        for version in ("v1.2.3", "1.2", "1.2.3.dev1", "01.2.3", "1.2.3+", "", "1.2.3 "):
            with self.subTest(version=version):
                with self.assertRaises(release.ReleaseError):
                    release.set_version(self.dir, version)
        self.assertEqual(_run_cli("set-version", str(self.dir), "v1.2.3").returncode, 1)
        self.assertIn('version = "0.0.0.dev0"', self.text())

    def test_refuses_zero_placeholders(self):
        release.set_version(self.dir, "1.2.3")
        with self.assertRaisesRegex(release.ReleaseError, "has 0 placeholder"):
            release.set_version(self.dir, "1.2.4")

    def test_refuses_two_placeholders(self):
        (self.dir / "pyproject.toml").write_text(self.text() + '\nversion = "0.0.0.dev0"\n')
        with self.assertRaisesRegex(release.ReleaseError, "has 2 placeholder"):
            release.set_version(self.dir, "1.2.3")

    def test_refuses_a_missing_file(self):
        (self.dir / "pyproject.toml").unlink()
        with self.assertRaises(release.ReleaseError):
            release.set_version(self.dir, "1.2.3")

    def test_never_touches_the_checkout(self):
        with self.assertRaisesRegex(release.ReleaseError, "never the checkout"):
            release.set_version(REPO_ROOT, "1.2.3")
        self.assertEqual(_run_cli("set-version", str(REPO_ROOT), "1.2.3").returncode, 1)


# -- INV-6 ------------------------------------------------------------------------


class TestPyprojectHoldsOnlyThePlaceholder(unittest.TestCase):
    def test_version_is_the_placeholder(self):
        lines = (REPO_ROOT / "pyproject.toml").read_text().splitlines()
        versions = [line for line in lines if line.startswith("version")]
        self.assertEqual(versions, [release.PLACEHOLDER_LINE])
        self.assertEqual(release.PLACEHOLDER_LINE, 'version = "0.0.0.dev0"')


# -- assert-full-plan against the retired pull-request profile ---------------------


class TestAssertFullPlanRefusesTheStopgap(runner_tests._CliCase):  # noqa: SLF001
    """`release.py assert-full-plan` never rests a release on a plan the retired
    pull-request profile (`--newest-release-only`, removed by M2) made. Such a
    plan said `selection_kind: "newest-release"`; on a one-release scratch its
    selection equals the full one, so only the label can refuse it."""

    def relabelled(self, plan: Path, kind: str) -> Path:
        """`plan` with `selection_kind` set to `kind` and its `plan_digest`
        recomputed, so it still loads as a runnable plan."""
        doc = json.loads(plan.read_text())
        doc["selection_kind"] = kind
        doc["plan_digest"] = planner.plan_digest(doc)
        out = plan.with_name(f"{kind}-{plan.name}")
        out.write_text(canonical_json(doc))
        return out

    def test_a_newest_release_plan_is_refused_though_its_selection_is_full(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        full = runner_tests._plan_only(self, scratch, "--profile", "ci")  # noqa: SLF001
        proc = release_tests.run_assert_full_plan(scratch, full, self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        newest = self.relabelled(full, "newest-release")
        self.assertEqual(json.loads(newest.read_text())["selection"],
                         json.loads(full.read_text())["selection"])
        proc = release_tests.run_assert_full_plan(scratch, newest, self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("selection_kind is 'newest-release'", proc.stderr)
        self.assertNotIn("not runnable", proc.stderr)

    def test_the_runner_no_longer_makes_one(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        proc = runner_tests.run_cli(scratch, "--plan-only", "--newest-release-only",
                                    "--out", str(self.tmp / "plan.json"), env=self.env)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("unrecognized arguments: --newest-release-only", proc.stderr)


if __name__ == "__main__":
    unittest.main()
