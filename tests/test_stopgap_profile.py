#!/usr/bin/env python3
"""The stopgap test profile: every test of stopgap code (plan section 6.7).

Checkpoint CP3 of `workflow-manager-trunk-model`
(`D-Newest-Release-Selection`): `--newest-release-only`'s selection, its
exclusivity with `--select`/`--fast`, the plan's `selection_kind`, the
evidence label for all three kinds, the full selection unchanged by this
milestone's runner changes (INV-2), and a real `--list` subprocess run in a
scratch checkout of three releases.

Checkpoint CP4 (`D-PR-Profile`): `tools/ci/choose_profile.py`'s path rules
and their completeness over the tree, the merge-ref diff, `main`'s health,
the non-PR events and the output format; and `tools/ci/nightly_alarm.py`'s
decision table.

Checkpoint CP5 (`D-CI`, plan 6.4-6.5): the stopgap wiring of
`workflow-manager-verify.yml` -- T-CI-6 (the `plan` job chooses the profile
before planning and passes `--newest-release-only` only from its output) and
T-CI-8 (the nightly alarm runs on a `schedule` only, and is the only job with
`issues: write`) -- and `release.py assert-full-plan`'s stopgap cases: a
newest-release plan is refused, even over a one-release inventory, where it
is full by set equality but not by flag.

Checkpoint CP7 (`D-Stopgap-Removal`, plan 6.7): the marked files equal the
list in `docs/ARCHITECTURE.md`'s "Stopgap test profile"; every file that
names a stopgap identifier is marked; documentation and string mentions
never count as markers.
"""

# STOPGAP(M2): this whole module tests the stopgap profile; see
# docs/ARCHITECTURE.md's "Stopgap test profile". M2 deletes it.

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tokenize
import unittest
import unittest.mock
from pathlib import Path

from support import CI_SUITES, REPO_ROOT

import test_parallel_runner as runner_tests
import test_release_workflows as release_tests
from parallel import canonical_json, cli, inventory, matrix, planner, report

#: The commit this milestone's plan was made against: its `tests/parallel/`
#: is the runner "without this milestone's changes" (INV-2).
BASE_COMMIT = "b856a97346849fdf48bcdba2d6a5a9644699ab4b"
FIXTURES = ("conformance", "target", "bootstrapped")


def _synthetic_frozen(versions=("2.9.0", "2.10.0")) -> inventory.FrozenInventory:
    """Every release has two suites and all three fixtures; `2.10.0` must
    beat `2.9.0` by numeric order, not by string order."""
    return inventory.FrozenInventory(
        matrix={f"host:test_m.py::M{v.replace('.', '')}{f[0]}": (v, f)
                for v in versions for f in FIXTURES},
        ci_suites={v: {"s_test.py": 3, "t_test.py": 1} for v in versions},
        classes={v: {"s_test.py": {"S1": ["test_a", "test_b"], "S2": ["test_c"]},
                     "t_test.py": {"T1": ["test_d"]}} for v in versions},
    )


def _synthetic_host(frozen: inventory.FrozenInventory) -> dict[str, list[str]]:
    host = {unit: [f"{unit[len('host:'):]}::test_p"] for unit in frozen.matrix}
    host["host:test_n.py::N"] = ["test_n.py::N::test_z"]
    host["host:test_n.py::O"] = ["test_n.py::O::test_y"]
    return dict(sorted(host.items()))


def _numeric(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def _structural(host, frozen: inventory.FrozenInventory) -> list[str]:
    """The newest-release selection by its definition, computed here without
    the runner: every host unit but the other releases' matrix classes, plus
    the newest release's frozen units."""
    newest = max(frozen.ci_suites, key=_numeric)
    others = {u for u, (v, _) in frozen.matrix.items() if v != newest}
    frozen_units = [u for u in frozen.units() if u.startswith(f"frozen:{newest}/")]
    return sorted([u for u in host if u not in others] + frozen_units)


def _plan(selection, *, host, frozen):
    return planner.build_plan(
        selection, inventory_unit_ids=sorted(host) + sorted(frozen.units()),
        matrix_units=frozen.matrix, timings=runner_tests._timings(),  # noqa: SLF001
        config=dict(runner_tests.PLAN_CONFIG), profile="ci", tree_digest="T" * 64,
        resources=runner_tests.NO_RESOURCES, cpu_count=4)


class TestNewestReleaseSelection(unittest.TestCase):

    def setUp(self):
        self.frozen = _synthetic_frozen()
        self.host = _synthetic_host(self.frozen)

    def select(self, frozen=None):
        frozen = frozen or self.frozen
        return inventory.select(_synthetic_host(frozen), [inventory.NEWEST_RELEASE], frozen)

    def test_the_newest_release_is_chosen_by_version_order(self):
        self.assertEqual(inventory.newest_release(self.frozen), "2.10.0")
        self.assertEqual(inventory.newest_release(_synthetic_frozen(("2.10.0", "2.9.0"))),
                         "2.10.0")
        self.assertEqual(inventory.newest_release(_synthetic_frozen(("1.0.0", "0.10.0"))),
                         "1.0.0")
        frozen = self.select().frozen_unit_ids()
        self.assertTrue(frozen)
        self.assertTrue(all(u.startswith("frozen:2.10.0/") for u in frozen), frozen)

    def test_host_minus_other_matrix_classes_plus_the_newest_frozen_units(self):
        chosen = self.select()
        self.assertEqual(chosen.unit_ids(), _structural(self.host, self.frozen))
        self.assertEqual(chosen.host_unit_ids(),
                         ["host:test_m.py::M2100b", "host:test_m.py::M2100c",
                          "host:test_m.py::M2100t", "host:test_n.py::N", "host:test_n.py::O"])
        self.assertEqual(len(chosen.frozen_unit_ids()), 3 * 3)
        self.assertTrue(all(tests is None for tests in chosen.units.values()))
        self.assertEqual(chosen.kind, "newest-release")

    def test_no_frozen_unit_is_partial_and_phase_b_is_the_newest_matrix_classes(self):
        chosen = self.select()
        self.assertFalse(chosen.partial_frozen)
        plan = _plan(chosen, host=self.host, frozen=self.frozen)
        self.assertFalse(plan["partial_frozen"])
        phase_b = sorted(u for shard in plan["phase_b"]["shards"] for c in shard["chunks"]
                         for u in c["units"])
        self.assertEqual(phase_b, sorted(u for u, (v, _) in self.frozen.matrix.items()
                                         if v == "2.10.0"))
        self.assertEqual(len(phase_b), 3)

    def test_a_single_release_selects_everything(self):
        frozen = _synthetic_frozen(("3.0.0",))
        full = inventory.select(_synthetic_host(frozen), [], frozen)
        self.assertEqual(self.select(frozen).unit_ids(), full.unit_ids())

    def test_it_is_never_combined_with_another_spec(self):
        with self.assertRaises(inventory.SelectSyntaxError):
            inventory.select(self.host, [inventory.NEWEST_RELEASE, "test_n.py"], self.frozen)


class TestSelectionKindAndEvidenceLabel(unittest.TestCase):
    """`selection_kind` follows the flags; the evidence label follows set
    equality, with `newest-release` for a newest-release plan that is not
    full by it (review round 1, finding 7)."""

    def setUp(self):
        self.frozen = _synthetic_frozen()
        self.host = _synthetic_host(self.frozen)
        self.inventory_ids = sorted(self.host) + sorted(self.frozen.units())

    def kinds(self, specs, *, frozen=None):
        frozen = frozen or self.frozen
        host = _synthetic_host(frozen)
        selection = inventory.select(host, specs, frozen)
        plan = _plan(selection, host=host, frozen=frozen)
        identity = report.evidence_identity(
            plan, [], {}, head="H", inventory_unit_ids=sorted(host) + sorted(frozen.units()),
            scope="aggregate of 1 shards")
        return plan["selection_kind"], identity["selection"], report.identity_line(identity)

    def test_the_three_kinds(self):
        cases = (([], "full", "full"),
                 ([inventory.NEWEST_RELEASE], "newest-release", "newest-release"),
                 (["test_n.py"], "targeted", "targeted"))
        for specs, kind, label in cases:
            with self.subTest(kind=kind):
                plan_kind, identity_kind, line = self.kinds(specs)
                self.assertEqual((plan_kind, identity_kind), (kind, label))
                self.assertTrue(line.startswith(f"evidence: {label} selection, "), line)

    def test_where_the_flags_and_set_equality_disagree(self):
        single = _synthetic_frozen(("3.0.0",))
        self.assertEqual(self.kinds([inventory.NEWEST_RELEASE], frozen=single)[:2],
                         ("newest-release", "full"))
        everything = ["test_m.py", "test_n.py"]
        self.assertEqual(self.kinds(everything)[:2], ("targeted", "full"))

    def test_a_hand_built_selection_claims_the_least(self):
        self.assertEqual(inventory.Selection({}).kind, "targeted")


def _base_select_json(inventory_doc: dict) -> str:
    """`inventory.select(host, [], frozen).to_json()` computed by the base
    commit's own `tests/parallel/`, extracted into a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", BASE_COMMIT,
                                  "tests/parallel"], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive, check=True)
        (tmp / "inventory.json").write_text(canonical_json(inventory_doc))
        code = textwrap.dedent("""
            import json, sys
            from parallel import inventory
            doc = json.loads(open(sys.argv[1]).read())
            frozen = inventory.FrozenInventory.from_json(doc["frozen"])
            sys.stdout.write(inventory.select(doc["host"], [], frozen).to_json())
        """)
        return subprocess.run([sys.executable, "-B", "-c", code, str(tmp / "inventory.json")],
                              cwd=str(tmp / "tests"), check=True, capture_output=True,
                              text=True).stdout


class TestTheFullSelectionIsUnchanged(unittest.TestCase):
    """INV-2: for a fixed inventory, the full selection's unit set and
    `selection_digest` are those of the base commit's runner."""

    def assert_same_as_base(self, host, frozen):
        current = inventory.select(host, [], frozen)
        base_json = _base_select_json({"host": host, "frozen": frozen.to_json()})
        self.assertEqual(current.to_json(), base_json)
        self.assertEqual(current.unit_ids(), sorted([*host, *frozen.units()]))
        plan = _plan(current, host=host, frozen=frozen)
        self.assertEqual(plan["selection_digest"],
                         hashlib.sha256(base_json.encode("utf-8")).hexdigest())
        self.assertEqual(plan["selection_kind"], "full")

    def test_a_synthetic_inventory(self):
        frozen = _synthetic_frozen()
        self.assert_same_as_base(_synthetic_host(frozen), frozen)

    def test_the_live_inventory(self):
        inv = inventory.discover(REPO_ROOT)
        self.assert_same_as_base(inv.host, inv.frozen)
        frozen = inv.frozen.units()
        # Every frozen unit of every release and fixture, at its pinned count.
        self.assertEqual(len(frozen), len(matrix.FIXTURES) * sum(
            len(classes) for version in CI_SUITES
            for classes in inv.frozen.classes[version].values()))
        self.assertEqual(set(inv.frozen.ci_suites), set(CI_SUITES))


class TestTheLiveNewestReleaseSelection(unittest.TestCase):

    def test_it_is_exactly_the_structural_set(self):
        inv = inventory.discover(REPO_ROOT)
        chosen = inventory.select(inv.host, [inventory.NEWEST_RELEASE], inv.frozen)
        self.assertEqual(chosen.unit_ids(), _structural(inv.host, inv.frozen))
        newest = max(CI_SUITES, key=_numeric)
        self.assertEqual(inventory.newest_release(inv.frozen), newest)
        kept = sorted(u for u, (v, _) in matrix.FROZEN_MATRIX.items() if v == newest)
        self.assertEqual(len(kept), 3)
        self.assertTrue(set(kept) <= set(chosen.host_unit_ids()))
        self.assertFalse(chosen.partial_frozen)


def _in_process(*argv) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            code = cli.main(list(argv), repo_root=REPO_ROOT)
        except SystemExit as exc:
            code = exc.code
    return code, err.getvalue()


class TestTheFlagIsExclusive(unittest.TestCase):
    """Usage errors, exit 2, refused from argv alone -- before the checkout
    run lock is taken, so this is safe against the real checkout."""

    def test_with_select_or_fast(self):
        for extra in (["--select", "test_bootstrap.py"], ["--fast"]):
            for mode in ([], ["--list"], ["--plan-only"]):
                with self.subTest(extra=extra, mode=mode):
                    code, err = _in_process(*mode, "--newest-release-only", *extra)
                    self.assertEqual(code, 2)
                    # `--fast` is a local run's flag alone, so outside one the
                    # mode check refuses it first.
                    self.assertIn("--fast cannot be used with" if extra == ["--fast"] and mode
                                  else "--newest-release-only cannot be combined", err)

    def test_outside_the_selecting_modes(self):
        code, err = _in_process("--restore-barrier", "--newest-release-only")
        self.assertEqual(code, 2)
        self.assertIn("--newest-release-only cannot be used with --restore-barrier", err)


SCRATCH_NEWER_MATRIX_MODULE = '''
import unittest


class TestScratchMatrixVERSION(unittest.TestCase):
    def test_listed_only(self):
        self.assertTrue(True)
'''


class TestARealListRun(runner_tests._CliCase):  # noqa: SLF001
    """`--newest-release-only --list` (and `--plan-only`) as a subprocess, in a
    scratch checkout of three releases: `0.0.1`, `0.0.9` and `0.0.10`."""

    VERSIONS = ("0.0.1", "0.0.9", "0.0.10")

    def make_scratch(self) -> Path:
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        workflow = scratch / "distribution" / "workflow"
        rows = {runner_tests.SCRATCH_MATRIX_UNIT: ("0.0.1", "conformance")}
        for version in self.VERSIONS[1:]:
            shutil.copytree(workflow / "0.0.1", workflow / version)
            tag = version.replace(".", "")
            module = f"test_scratch_matrix{tag}.py"
            (scratch / "tests" / module).write_text(
                SCRATCH_NEWER_MATRIX_MODULE.replace("VERSION", tag))
            rows[f"host:{module}::TestScratchMatrix{tag}"] = (version, "conformance")
        (scratch / "tests" / "parallel" / "matrix.py").write_text(
            'FIXTURES = ("conformance", "target", "bootstrapped")\n'
            f"FROZEN_MATRIX = {rows!r}\n"
            f"CI_SUITES = {{v: {{'tiny_test.py': {runner_tests.SCRATCH_SUITE_TESTS}}} "
            f"for v in {self.VERSIONS!r}}}\n")
        runner_tests._commit_all(scratch, "three releases")  # noqa: SLF001
        self.rows = rows
        return scratch

    def test_list_and_plan_only(self):
        scratch = self.make_scratch()
        full = runner_tests.run_cli(scratch, "--list", env=self.env)
        self.assertEqual(full.returncode, 0, full.stderr)
        newest = runner_tests.run_cli(scratch, "--list", "--newest-release-only", env=self.env)
        self.assertEqual(newest.returncode, 0, newest.stderr)
        listed = newest.stdout.split()
        dropped = sorted(u for u, (v, _) in self.rows.items() if v != "0.0.10")
        expected = sorted(u for u in full.stdout.split()
                          if u not in dropped and not u.startswith("frozen:")) + \
            sorted(u for u in full.stdout.split() if u.startswith("frozen:0.0.10/"))
        self.assertEqual(sorted(listed), sorted(expected))
        self.assertIn("host:test_scratch_matrix0010.py::TestScratchMatrix0010", listed)
        self.assertEqual(len([u for u in listed if u.startswith("frozen:")]), 3)
        self.assertNotIn(inventory.PARTIAL_FROZEN_NOTE, newest.stdout)

        out = self.tmp / "plan.json"
        proc = runner_tests.run_cli(scratch, "--plan-only", "--newest-release-only",
                                    "--out", out, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = json.loads(out.read_text())
        self.assertEqual(plan["selection_kind"], "newest-release")
        self.assertEqual(sorted(plan["selection"]), sorted(expected))


# -- CP4: the pull-request profile chooser ----------------------------------------


def _load_tool(name: str):
    source = REPO_ROOT / "tools" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"workflow_manager_ci_{name}", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


choose_profile = _load_tool("choose_profile")
nightly_alarm = _load_tool("nightly_alarm")

LIVE_RULES = choose_profile.load_rules()
GREEN_RUNS = [{"id": 7, "event": "push", "status": "completed", "conclusion": "success"}]


def _no_call():
    raise AssertionError("must not be consulted")


def _git_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    runner_tests._git_repo(root)  # noqa: SLF001
    runner_tests._git(root, "config", "commit.gpgsign", "false")  # noqa: SLF001
    return root


def _write(repo: Path, rel: str, text: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class _TempDir(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)


class TestPathRulesAreComplete(_TempDir):
    """Every path of the tree matches an explicit rule, never the
    "unclassified" fallback (plan 6.2, `OD-7`)."""

    def test_every_tree_path_matches_a_rule(self):
        paths = choose_profile.tree_paths(REPO_ROOT)
        self.assertIn("tests/test_stopgap_profile.py", paths)
        unmatched = [p for p in paths if choose_profile.match_rule(p, LIVE_RULES) is None]
        self.assertEqual(unmatched, [], "classify these in tools/ci/pr_profile_paths.json")

    def test_every_test_module_has_its_own_exact_rule(self):
        modules = [p for p in choose_profile.tree_paths(REPO_ROOT)
                   if p.startswith("tests/test_") and p.endswith(".py") and "/" not in p[6:]]
        self.assertIn("tests/test_release_versioning.py", modules)
        for module in modules:
            with self.subTest(module=module):
                self.assertEqual(choose_profile.match_rule(module, LIVE_RULES).path, module)

    def test_this_milestones_modules_are_classified(self):
        for module in ("tests/test_release_versioning.py", "tests/test_manager_version.py",
                       "tests/test_stopgap_profile.py", "tests/test_release_workflows.py",
                       "tests/test_squash_merge_compat.py"):
            with self.subTest(module=module):
                rule = choose_profile.match_rule(module, LIVE_RULES)
                self.assertEqual((rule.path, rule.profile), (module, "newest-release"))

    def test_a_new_untracked_test_module_fails_it(self):
        repo = _git_repo(self.tmp / "repo")
        _write(repo, ".gitignore", "__pycache__/\n")
        _write(repo, "docs/a.md")
        runner_tests._commit_all(repo)  # noqa: SLF001
        _write(repo, "tests/test_brand_new.py")
        _write(repo, "tests/__pycache__/ignored.pyc")
        paths = choose_profile.tree_paths(repo)
        self.assertEqual(paths, [".gitignore", "docs/a.md", "tests/test_brand_new.py"])
        unmatched = [p for p in paths if choose_profile.match_rule(p, LIVE_RULES) is None]
        self.assertEqual(unmatched, ["tests/test_brand_new.py"])

    def test_the_rule_file_is_a_marked_stopgap(self):
        doc = json.loads(choose_profile.RULES_PATH.read_text())
        self.assertTrue(doc["_comment"].startswith("STOPGAP(M2)"))


class TestPathClassification(unittest.TestCase):

    def profile(self, path, rules=LIVE_RULES):
        return choose_profile.classify(path, rules)[0]

    def test_unknown_paths_are_full(self):
        for path in ("new_top_level.txt", "newdir/x.py", "tests/test_unknown.py",
                     "tests/fixtures/data.json", "docs", "docsx/a.md", "READM.md"):
            with self.subTest(path=path):
                profile, reason = choose_profile.classify(path, LIVE_RULES)
                self.assertEqual(profile, "full")
                self.assertIn("unclassified", reason)

    def test_every_rule_1_area_is_full(self):
        for path in ("distribution/workflow/2.6.0/manifest.json", "migration/classification.json",
                     "tools/release/release.py", "tools/ci/pr_profile_paths.json",
                     "src/workflow_manager/install.py", "src/workflow_manager/cli.py",
                     "tests/support.py", "tests/frozen_runs.py", "tests/run_all.py",
                     "tests/parallel/planner.py", "tests/test_conformance_suite.py",
                     "tests/test_bootstrap_e2e.py", ".github/workflows/workflow-manager-verify.yml",
                     ".github/tools/requirements.txt", "pyproject.toml"):
            with self.subTest(path=path):
                self.assertEqual(self.profile(path), "full")

    def test_documentation_and_the_installed_copy_are_newest_release(self):
        for path in ("docs/ROADMAP.md", "docs/ai-workflow/WORKFLOW_STATE.json", "README.md",
                     "CLAUDE.md", ".gitignore", ".claude/commands/milestone-plan.md",
                     "scripts/workflow_state.py", ".workflow-manager/installation.json",
                     "tests/test_bootstrap.py"):
            with self.subTest(path=path):
                self.assertEqual(self.profile(path), "newest-release")

    def test_the_longest_match_wins(self):
        rules = [choose_profile.Rule("a/", "full", "outer"),
                 choose_profile.Rule("a/b/", "newest-release", "inner"),
                 choose_profile.Rule("a/b/c.py", "full", "exact")]
        self.assertEqual(choose_profile.classify("a/b/d.py", rules), ("newest-release", "`a/b/`: inner"))
        self.assertEqual(self.profile("a/x.py", rules), "full")
        self.assertEqual(self.profile("a/b/c.py", rules), "full")
        self.assertEqual(self.profile("a/b/c.pyc", rules), "newest-release")
        # An exact rule is not a prefix, and a prefix needs its slash.
        self.assertIsNone(choose_profile.match_rule("a/b/c.py/x", rules[2:]))
        self.assertIsNone(choose_profile.match_rule("ab/x", rules))

    def test_a_malformed_rule_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            bad = ({"rules": []}, {"rules": [{"path": "a/", "profile": "fast", "reason": "r"}]},
                   {"rules": [{"path": "a/", "profile": "full"}]},
                   {"rules": [{"path": "/a", "profile": "full", "reason": "r"}]},
                   {"rules": [{"path": "a", "profile": "full", "reason": " "}]},
                   {"rules": [{"path": "a", "profile": "full", "reason": "r"}] * 2}, [])
            for doc in bad:
                with self.subTest(doc=doc):
                    path.write_text(json.dumps(doc))
                    with self.assertRaises(choose_profile.ProfileError):
                        choose_profile.load_rules(path)
            path.write_text("{not json")
            with self.assertRaises(choose_profile.ProfileError):
                choose_profile.load_rules(path)


class TestTheMergeRefDiff(_TempDir):
    """`git diff --name-only --no-renames HEAD^1 HEAD` over a real merge."""

    def merge_repo(self) -> Path:
        repo = _git_repo(self.tmp / "repo")
        _write(repo, "src/mod.py", "a\n" * 20)
        _write(repo, "docs/gone.md")
        _write(repo, "docs/kept.md")
        runner_tests._commit_all(repo, "base")  # noqa: SLF001
        runner_tests._git(repo, "checkout", "-q", "-b", "topic")  # noqa: SLF001
        runner_tests._git(repo, "mv", "src/mod.py", "docs/moved.py")  # noqa: SLF001
        runner_tests._git(repo, "rm", "-q", "docs/gone.md")  # noqa: SLF001
        runner_tests._commit_all(repo, "rename and delete")  # noqa: SLF001
        runner_tests._git(repo, "checkout", "-q", "main")  # noqa: SLF001
        _write(repo, "docs/main-only.md")
        runner_tests._commit_all(repo, "main moves on")  # noqa: SLF001
        runner_tests._git(repo, "merge", "-q", "--no-ff", "-m", "merge", "topic")  # noqa: SLF001
        return repo

    def test_both_sides_of_a_rename_and_deletions_are_listed(self):
        repo = self.merge_repo()
        paths = choose_profile.changed_paths(repo)
        self.assertEqual(paths, ["docs/gone.md", "docs/moved.py", "src/mod.py"])
        decision = choose_profile.decide("pull_request", LIVE_RULES, lambda: paths, _no_call)
        self.assertEqual(decision.profile, "full")
        self.assertIn(("`src/mod.py`", "full"), [row[:2] for row in decision.reasons])

    def test_a_non_merge_head_is_full(self):
        repo = _git_repo(self.tmp / "repo")
        _write(repo, "docs/a.md")
        runner_tests._commit_all(repo)  # noqa: SLF001
        _write(repo, "docs/b.md")
        runner_tests._commit_all(repo)  # noqa: SLF001
        with self.assertRaisesRegex(choose_profile.ProfileError, "not a two-parent merge"):
            choose_profile.changed_paths(repo)
        decision = choose_profile.decide(
            "pull_request", LIVE_RULES, lambda: choose_profile.changed_paths(repo), _no_call)
        self.assertEqual(decision.profile, "full")

    def test_a_git_failure_is_full(self):
        not_a_repo = self.tmp / "plain"
        not_a_repo.mkdir()
        decision = choose_profile.decide(
            "pull_request", LIVE_RULES, lambda: choose_profile.changed_paths(not_a_repo),
            _no_call)
        self.assertEqual(decision.profile, "full")
        self.assertIn("undecidable", decision.reasons[-1][2])


class TestMainHealth(unittest.TestCase):
    """Rule 5, from injected API JSON."""

    @staticmethod
    def run_(id_, event="push", conclusion="success"):
        return {"id": id_, "event": event, "status": "completed", "conclusion": conclusion}

    def profile(self, runs):
        def get_runs():
            if isinstance(runs, Exception):
                raise runs
            return runs
        return choose_profile.decide("pull_request", LIVE_RULES, lambda: ["docs/a.md"],
                                     get_runs).profile

    def test_green_main_allows_the_newest_release_profile(self):
        self.assertEqual(self.profile([self.run_(3)]), "newest-release")
        self.assertEqual(self.profile([self.run_(3, "schedule")]), "newest-release")

    def test_the_newest_push_or_schedule_run_decides(self):
        self.assertEqual(self.profile([self.run_(5, "schedule", "failure"), self.run_(4)]), "full")
        self.assertEqual(self.profile([self.run_(4, "push", "failure"), self.run_(5, "schedule")]),
                         "newest-release")
        self.assertEqual(self.profile([self.run_(6), self.run_(5, "push", "failure")]),
                         "newest-release")

    def test_red_cancelled_or_timed_out_is_full(self):
        for conclusion in ("failure", "cancelled", "timed_out", None):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.profile([self.run_(3, conclusion=conclusion)]), "full")

    def test_pull_request_and_dispatch_runs_are_ignored(self):
        runs = [self.run_(9, "pull_request"), self.run_(8, "workflow_dispatch"),
                self.run_(2, "push", "failure")]
        self.assertEqual(self.profile(runs), "full")
        runs = [self.run_(9, "pull_request", "failure"), self.run_(8, "workflow_dispatch", "failure"),
                self.run_(2)]
        self.assertEqual(self.profile(runs), "newest-release")

    def test_empty_malformed_or_an_api_error_is_full(self):
        for runs in ([], [self.run_(9, "pull_request")], None, {"workflow_runs": []}, ["run"],
                     [{"id": "9", "event": "push", "status": "completed", "conclusion": "success"}],
                     [{"id": True, "event": "push", "status": "completed", "conclusion": "success"}],
                     choose_profile.ProfileError("gh api failed: HTTP 403")):
            with self.subTest(runs=runs):
                self.assertEqual(self.profile(runs), "full")


class TestTheDecision(unittest.TestCase):

    def test_non_pull_request_events_are_full_without_reading_anything(self):
        for event in ("push", "schedule", "workflow_dispatch", "merge_group"):
            with self.subTest(event=event):
                decision = choose_profile.decide(event, LIVE_RULES, _no_call, _no_call)
                self.assertEqual(decision.profile, "full")

    def test_docs_only_with_green_main_is_newest_release(self):
        decision = choose_profile.decide("pull_request", LIVE_RULES,
                                         lambda: ["docs/ROADMAP.md", "README.md"],
                                         lambda: GREEN_RUNS)
        self.assertEqual(decision.profile, "newest-release")
        self.assertEqual([row[1] for row in decision.reasons], ["newest-release"] * 4)

    def test_one_full_path_decides_and_main_is_not_consulted(self):
        decision = choose_profile.decide("pull_request", LIVE_RULES,
                                         lambda: ["docs/a.md", "src/workflow_manager/cli.py"],
                                         _no_call)
        self.assertEqual(decision.profile, "full")
        self.assertEqual(decision.reasons[-1][0], "main's health")


class TestTheOutput(_TempDir):
    """`profile=...` to `$GITHUB_OUTPUT`, the reasons table to the summary."""

    def run_main(self, *argv, env=None):
        out, summary = self.tmp / "output", self.tmp / "summary"
        env = {"GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary), **(env or {})}
        err = io.StringIO()
        with unittest.mock.patch.dict(os.environ, env), contextlib.redirect_stderr(err):
            code = choose_profile.main(list(argv))
        return code, out.read_text() if out.exists() else "", \
            summary.read_text() if summary.exists() else "", err.getvalue()

    def test_a_push_run(self):
        code, output, summary, _ = self.run_main("--event", "push")
        self.assertEqual((code, output), (0, "profile=full\n"))
        self.assertEqual(summary, "### Test profile: `full`\n\n| input | profile | reason |\n"
                                  "| --- | --- | --- |\n| event `push` | full | only a pull "
                                  "request runs a reduced profile |\n")

    def test_a_pull_request_that_touches_src(self):
        repo = _git_repo(self.tmp / "repo")
        _write(repo, "docs/a.md")
        runner_tests._commit_all(repo)  # noqa: SLF001
        runner_tests._git(repo, "checkout", "-q", "-b", "topic")  # noqa: SLF001
        _write(repo, "src/x.py")
        runner_tests._commit_all(repo)  # noqa: SLF001
        runner_tests._git(repo, "checkout", "-q", "main")  # noqa: SLF001
        runner_tests._git(repo, "merge", "-q", "--no-ff", "-m", "m", "topic")  # noqa: SLF001
        code, output, summary, _ = self.run_main("--event", "pull_request", "--repo", "o/n",
                                                 "--repo-dir", str(repo))
        self.assertEqual((code, output), (0, "profile=full\n"))
        self.assertIn("| `src/x.py` | full | `src/`: rule 1:", summary)

    def test_a_broken_rule_file_is_full(self):
        rules = self.tmp / "rules.json"
        rules.write_text("[]")
        code, output, summary, _ = self.run_main("--event", "push", "--rules", str(rules))
        self.assertEqual((code, output), (0, "profile=full\n"))
        self.assertIn("| path rules | full | undecidable:", summary)

    def test_usage_errors(self):
        for argv in ((), ("--event", "pull_request")):
            with self.subTest(argv=argv):
                code, output, _, err = self.run_main(*argv)
                self.assertEqual((code, output), (2, ""))
                self.assertIn("usage error", err)

    def test_the_table_escapes_cells_and_bounds_its_rows(self):
        decision = choose_profile.Decision("full", [("`a|b.md`", "newest-release", "x|y")])
        self.assertIn("| `a\\|b.md` | newest-release | x\\|y |",
                      choose_profile.summary_markdown(decision))
        many = [(f"`docs/{i}.md`", "newest-release", "r") for i in range(400)]
        many.insert(350, ("`src/late.py`", "full", "r"))
        table = choose_profile.summary_markdown(choose_profile.Decision("full", many))
        self.assertIn("`src/late.py`", table)
        self.assertEqual(sum(1 for line in table.splitlines() if line.startswith("| `")),
                         choose_profile.MAX_SUMMARY_PATHS)
        self.assertIn(f"| {401 - choose_profile.MAX_SUMMARY_PATHS} more paths |", table)


class TestNightlyAlarmDecision(unittest.TestCase):
    URL = "https://github.com/o/n/actions/runs/1"

    def kinds(self, event, result, open_issues):
        return [(a.kind, a.issue) for a in nightly_alarm.decide(event, result, open_issues, self.URL)]

    def test_the_decision_table(self):
        self.assertEqual(self.kinds("schedule", "failure", []),
                         [("ensure-label", None), ("open", None)])
        self.assertEqual(self.kinds("schedule", "cancelled", [12]),
                         [("ensure-label", None), ("comment", 12)])
        self.assertEqual(self.kinds("schedule", "failure", [15, 12]),
                         [("ensure-label", None), ("comment", 12)])
        self.assertEqual(self.kinds("schedule", "success", [12]), [("close", 12)])
        self.assertEqual(self.kinds("schedule", "success", [15, 12]), [("close", 12), ("close", 15)])
        self.assertEqual(self.kinds("schedule", "success", []), [])
        for event in ("push", "pull_request", "workflow_dispatch"):
            for result in ("success", "failure"):
                self.assertEqual(self.kinds(event, result, [12]), [])

    def test_every_red_case_ensures_the_label_first(self):
        for result in ("failure", "cancelled", "skipped", "timed_out"):
            for open_issues in ([], [3]):
                actions = nightly_alarm.decide("schedule", result, open_issues, self.URL)
                self.assertEqual(actions[0].kind, "ensure-label")
                self.assertIn(self.URL, actions[1].body)

    def test_the_gh_calls(self):
        label = nightly_alarm.gh_args(nightly_alarm.Action("ensure-label"), "o/n")
        self.assertEqual(label[:3], ["label", "create", "nightly-red"])
        self.assertIn("--force", label)
        opened = nightly_alarm.gh_args(nightly_alarm.Action("open", body="b"), "o/n")
        self.assertEqual(opened[:2], ["issue", "create"])
        self.assertEqual(opened[opened.index("--title") + 1], "Nightly full verification failed")
        self.assertEqual(opened[opened.index("--label") + 1], "nightly-red")
        self.assertEqual(nightly_alarm.gh_args(nightly_alarm.Action("close", 4, "b"), "o/n")[:3],
                         ["issue", "close", "4"])

    def test_a_non_schedule_run_calls_nothing(self):
        with unittest.mock.patch.object(nightly_alarm, "_gh", side_effect=AssertionError), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(nightly_alarm.main(["--event", "push", "--result", "failure",
                                                 "--repo", "o/n", "--run-url", self.URL]), 0)

    def test_an_unreadable_issue_list_still_opens_an_issue(self):
        calls = []

        def fake_gh(*args):
            calls.append(args[:2])
            if args[:2] == ("issue", "list"):
                return subprocess.CompletedProcess(args, 1, "", "HTTP 502")
            return subprocess.CompletedProcess(args, 0, "", "")

        with unittest.mock.patch.object(nightly_alarm, "_gh", side_effect=fake_gh), \
                contextlib.redirect_stderr(io.StringIO()):
            code = nightly_alarm.main(["--event", "schedule", "--result", "failure",
                                       "--repo", "o/n", "--run-url", self.URL])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("issue", "list"), ("label", "create"), ("issue", "create")])


# -- CP5: the stopgap wiring of the verification workflow ----------------------------

VERIFY_JOBS = ["aggregate", "nightly-alarm", "package", "plan", "shard"]


def _plan_job_steps() -> tuple[list[dict], int, int]:
    steps = runner_tests.ci_workflow()["jobs"]["plan"]["steps"]
    [profile] = [i for i, s in enumerate(steps) if "tools/ci/choose_profile.py" in (s.get("run") or "")]
    [plan] = [i for i, s in enumerate(steps) if "tests/run_all.py" in (s.get("run") or "")]
    return steps, profile, plan


class TestProfileWiring(runner_tests._CliCase):  # noqa: SLF001
    """T-CI-6: the `plan` job chooses the profile, then plans with
    `--newest-release-only` only when the chooser said so."""

    def test_the_plan_job_chooses_before_it_plans(self):
        job = runner_tests.ci_workflow()["jobs"]["plan"]
        steps, profile, plan = _plan_job_steps()
        self.assertLess(profile, plan)
        self.assertEqual(steps[profile]["id"], "profile")
        self.assertEqual(steps[profile]["env"]["EVENT"], "${{ github.event_name }}")
        self.assertEqual(steps[profile]["env"]["GH_TOKEN"], "${{ github.token }}")
        self.assertEqual(steps[plan]["env"]["NEWEST"],
                         "${{ steps.profile.outputs.profile == 'newest-release' && '1' || '' }}")
        self.assertEqual(steps[plan]["run"].count("--newest-release-only"), 1)
        self.assertIn("${NEWEST:+--newest-release-only}", steps[plan]["run"])
        self.assertEqual(job["permissions"], {"contents": "read", "actions": "read"})
        self.assertEqual(job["outputs"]["profile"], "${{ steps.profile.outputs.profile }}")
        for other, body in runner_tests.ci_workflow()["jobs"].items():
            if other != "plan":
                with self.subTest(job=other):
                    self.assertNotIn("--newest-release-only", json.dumps(body))

    def test_a_non_pull_request_event_chooses_full_through_the_real_step(self):
        steps, profile, _ = _plan_job_steps()
        output = self.tmp / "github-output"
        summary = self.tmp / "summary.md"
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", steps[profile]["run"]],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
            env=dict(self.env, EVENT="push", REPO="o/n", GH_TOKEN="",
                     GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(output.read_text(), "profile=full\n")
        self.assertIn("### Test profile: `full`", summary.read_text())

    def test_the_plan_step_follows_newest(self):
        """The real `plan` step, in a scratch clone: `NEWEST=1` plans the
        newest-release selection, empty plans the full one."""
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        for newest, kind in (("", "full"), ("1", "newest-release")):
            with self.subTest(newest=newest):
                job = runner_tests.scratch_clone(scratch)
                temp = self.tmp / f"rt-{kind}"
                temp.mkdir()
                proc = runner_tests.run_ci_step(
                    job, "plan", runner_temp=temp, env=self.env,
                    step_env={"SHARDS": "", "NEWEST": newest},
                    github_env={"GITHUB_OUTPUT": str(temp / "github-output")})
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(json.loads((temp / "plan.json").read_text())["selection_kind"],
                                 kind)


class TestNightlyAlarmWiring(unittest.TestCase):
    """T-CI-8: the alarm runs after `aggregate`, on a `schedule` only, and is
    the only job that may write issues."""

    def test_the_alarm_job(self):
        doc = runner_tests.ci_workflow()
        self.assertEqual(sorted(doc["jobs"]), VERIFY_JOBS)
        alarm = doc["jobs"]["nightly-alarm"]
        self.assertEqual(alarm["needs"], "aggregate")
        self.assertEqual(alarm["if"], "always() && github.event_name == 'schedule'")
        self.assertEqual(alarm["permissions"], {"contents": "read", "issues": "write"})
        [step] = [s for s in alarm["steps"] if "tools/ci/nightly_alarm.py" in (s.get("run") or "")]
        self.assertEqual(step["env"]["RESULT"], "${{ needs.aggregate.result }}")
        self.assertEqual(step["env"]["EVENT"], "${{ github.event_name }}")
        for flag in ("--event", "--result", "--repo", "--run-url"):
            self.assertIn(flag, step["run"])

    def test_issues_write_is_on_that_job_only(self):
        doc = runner_tests.ci_workflow()
        self.assertEqual(doc["permissions"], {"contents": "read"})
        for name, job in doc["jobs"].items():
            if name != "nightly-alarm":
                with self.subTest(job=name):
                    self.assertNotIn("issues", job.get("permissions") or {})

    def test_the_nightly_runs_the_full_selection(self):
        """A `schedule` event is never a pull request, so the chooser says full."""
        self.assertEqual(runner_tests.ci_workflow()["on"]["schedule"], [{"cron": "17 3 * * *"}])
        decision = choose_profile.decide("schedule", LIVE_RULES, _no_call, _no_call)
        self.assertEqual(decision.profile, "full")


# -- CP5: assert-full-plan refuses the newest-release selection ----------------------


class TestAssertFullPlanRefusesTheStopgap(runner_tests._CliCase):  # noqa: SLF001
    """`release.py assert-full-plan` against real `--newest-release-only`
    plans: the release never rests on the pull-request profile."""

    VERSIONS = TestARealListRun.VERSIONS
    make_scratch = TestARealListRun.make_scratch

    def assert_refused(self, scratch: Path, plan: Path) -> None:
        proc = release_tests.run_assert_full_plan(scratch, plan, self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("selection_kind is 'newest-release'", proc.stderr)

    def test_a_newest_release_plan_is_refused(self):
        scratch = self.make_scratch()
        plan = runner_tests._plan_only(self, scratch, "--profile", "ci",  # noqa: SLF001
                                       "--newest-release-only")
        self.assert_refused(scratch, plan)
        full = runner_tests._plan_only(self, scratch, "--profile", "ci")  # noqa: SLF001
        proc = release_tests.run_assert_full_plan(scratch, full, self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_over_one_release_it_is_full_by_set_equality_but_still_refused(self):
        scratch = runner_tests.scratch_checkout(self.tmp / "scratch")
        newest = runner_tests._plan_only(self, scratch, "--newest-release-only")  # noqa: SLF001
        full = runner_tests._plan_only(self, scratch)  # noqa: SLF001
        self.assertEqual(json.loads(newest.read_text())["selection"],
                         json.loads(full.read_text())["selection"])
        self.assert_refused(scratch, newest)


# -- CP7: where M2 finds the stopgap (plan 6.7) ---------------------------------------

MARKER = "STOPGAP(M2)"
STOPGAP_IDENTIFIERS = ("newest-release-only", "newest_release", "choose_profile",
                       "nightly_alarm", "nightly-alarm", "pr_profile_paths")
YAML_MARKER = re.compile(r"^\s*# STOPGAP\(M2\)", re.MULTILINE)
LIST_BEGIN = "<!-- stopgap-marked-files:begin -->"
LIST_END = "<!-- stopgap-marked-files:end -->"


def _is_documentation(rel: str) -> bool:
    return rel.startswith("docs/") or rel.endswith(".md")


def _python_marked(text: str) -> bool:
    """A `COMMENT` token starting with `# STOPGAP(M2)` that is the first token
    on its line; a line of a (multiline) string is a `STRING` token, never
    this."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return False
    return any(tok.type == tokenize.COMMENT and tok.string.startswith(f"# {MARKER}")
               and not tok.line[:tok.start[1]].strip() for tok in tokens)


def _json_marked(value) -> bool:
    if isinstance(value, dict):
        comment = value.get("_comment")
        if isinstance(comment, str) and comment.startswith(MARKER):
            return True
        return any(_json_marked(v) for v in value.values())
    if isinstance(value, list):
        return any(_json_marked(v) for v in value)
    return False


def is_marked(rel: str, text: str) -> bool:
    """Whether `rel` carries the marker in one of its two admitted forms."""
    if _is_documentation(rel):
        return False
    if rel.endswith(".py"):
        return _python_marked(text)
    if rel.endswith((".yml", ".yaml")):
        return bool(YAML_MARKER.search(text))
    if rel.endswith(".json"):
        try:
            return _json_marked(json.loads(text))
        except ValueError:
            return False
    return False


def scanned_files(repo: Path) -> dict[str, str]:
    """The tree as plan 6.2 defines it, minus documentation, read as text."""
    files = {}
    for rel in choose_profile.tree_paths(repo):
        path = repo / rel
        if _is_documentation(rel) or not path.is_file() or path.is_symlink():
            continue
        files[rel] = path.read_bytes().decode("utf-8", errors="replace")
    return files


def documented_marked_files(architecture: str) -> list[str]:
    section = architecture.split("### Stopgap test profile", 1)[1]
    listing = section.split(LIST_BEGIN, 1)[1].split(LIST_END, 1)[0]
    return re.findall(r"^- `([^`]+)`$", listing, re.MULTILINE)


class TestTheMarkedFilesAreRecorded(unittest.TestCase):
    """Rule 6: M2 finds every stopgap file from `docs/ARCHITECTURE.md`."""

    @classmethod
    def setUpClass(cls):
        cls.files = scanned_files(REPO_ROOT)
        cls.architecture = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text()

    def test_the_marked_files_equal_the_documented_list(self):
        documented = documented_marked_files(self.architecture)
        self.assertEqual(documented, sorted(set(documented)))
        marked = sorted(rel for rel, text in self.files.items() if is_marked(rel, text))
        self.assertEqual(marked, documented)

    def test_every_file_naming_a_stopgap_identifier_is_marked(self):
        naming = [rel for rel, text in self.files.items()
                  if any(name in text for name in STOPGAP_IDENTIFIERS)]
        self.assertIn("tools/ci/choose_profile.py", naming)
        self.assertEqual([rel for rel in naming if not is_marked(rel, self.files[rel])], [])

    def test_the_gate_policy_exception_is_recorded_as_a_stopgap(self):
        section = self.architecture.split("## Verification execution", 1)[1].split("\n## ", 1)[0]
        self.assertIn("**One reduced selection is a gate, in one place.**", section)
        self.assertIn("This exception is a stopgap: M2 removes it", section)
        self.assertIn("### Stopgap test profile", section)


class TestWhatCountsAsAMarker(_TempDir):
    """The two admitted forms, and every mention that is not one."""

    def test_the_admitted_forms(self):
        self.assertTrue(is_marked("a.py", "x = 1\n# STOPGAP(M2): here\n"))
        self.assertTrue(is_marked("a.py", "def f():\n    # STOPGAP(M2): here\n    pass\n"))
        self.assertTrue(is_marked("w.yml", "jobs:\n  # STOPGAP(M2): here\n"))
        self.assertTrue(is_marked("r.json", json.dumps({"_comment": "STOPGAP(M2): rules"})))
        self.assertTrue(is_marked("r.json", json.dumps({"a": [{"_comment": "STOPGAP(M2)."}]})))

    def test_string_mentions_are_not_markers(self):
        cases = {
            "an inline string": 'x = "# STOPGAP(M2): not a marker"\n',
            "a trailing comment": "x = 1  # STOPGAP(M2): not first on its line\n",
            "a multiline-string line": 'DOC = """\n# STOPGAP(M2): inside a string\n"""\n',
            "a docstring": 'def f():\n    """STOPGAP(M2)."""\n',
            "the wrong spelling": "# STOPGAP: M2\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.assertFalse(is_marked("a.py", text))
        self.assertFalse(is_marked("w.yml", "run: echo '# STOPGAP(M2)'\n"))
        self.assertFalse(is_marked("r.json", json.dumps({"note": "STOPGAP(M2)"})))
        self.assertFalse(is_marked("r.json", json.dumps({"_comment": "see STOPGAP(M2)"})))
        self.assertFalse(is_marked("notes.txt", "# STOPGAP(M2)\n"))

    def test_documentation_is_never_scanned(self):
        repo = _git_repo(self.tmp / "repo")
        _write(repo, "docs/plan.py", "# STOPGAP(M2): choose_profile\n")
        _write(repo, "docs/notes.txt", "newest_release\n")
        _write(repo, "NOTES.md", "# STOPGAP(M2): nightly_alarm\n")
        _write(repo, "sub/README.md", "# STOPGAP(M2)\n")
        _write(repo, "tools/marked.py", "# STOPGAP(M2): choose_profile\n")
        _write(repo, "tools/unmarked.py", 'NAME = "pr_profile_paths"\n')
        runner_tests._commit_all(repo)  # noqa: SLF001
        _write(repo, "tools/untracked.py", "import nightly_alarm\n")
        files = scanned_files(repo)
        self.assertEqual(sorted(files), ["tools/marked.py", "tools/unmarked.py",
                                         "tools/untracked.py"])
        self.assertFalse(is_marked("docs/plan.py", "# STOPGAP(M2)\n"))
        naming_unmarked = [rel for rel, text in files.items()
                           if any(n in text for n in STOPGAP_IDENTIFIERS)
                           and not is_marked(rel, text)]
        self.assertEqual(naming_unmarked, ["tools/unmarked.py", "tools/untracked.py"])

    def test_the_documented_list_is_read_between_its_markers(self):
        text = textwrap.dedent(f"""\
            ### Stopgap test profile

            - `not/listed.py`
            {LIST_BEGIN}
            - `a/b.py`
            - `c.json`
            {LIST_END}
            - `after.py`
            """)
        self.assertEqual(documented_marked_files(text), ["a/b.py", "c.json"])


if __name__ == "__main__":
    unittest.main()
