#!/usr/bin/env python3
"""The parallel verification tooling under `tests/parallel/` is deterministic,
covers exactly what a direct run covers, and fails closed.

Checkpoint CP1 of `workflow-manager-adaptive-test-sharding`: host inventory and
selection (T-INV-1, -2, -4, -5, host parts), the shared resource and
chunk-descriptor contracts (T-INV-8), tree identity and the snapshot, and the
per-unit host runner.

Checkpoint CP2: frozen discovery and selection (T-INV-1..5 frozen parts,
T-INV-7), the merge and its independent context (T-MRG-1, -2, -7), and the
unchanged matrix host assertions over merged and direct views (T-MRG-3..6).

Checkpoint CP3: timing history and the planner (T-PLN-1..9, T-PLN-8 at
function level) and the selection's independence from timing (T-INV-6).

Checkpoint CP4: isolation and the repository-integrity guard, function-level
(T-ISO-1..9, T-ISO-11..14). Every test that takes the run lock or applies the
barrier does it in a `scratch_checkout` (or a `scratch_worktree` of one),
never in the real checkout (plan 5.9, "Tests and the lock").

Checkpoint CP6: the CI pipeline `.github/workflows/workflow-manager-verify.yml`
(T-CI-1..5). Its steps' own scripts run against a `scratch_clone` of a scratch
checkout -- a fresh CI-like checkout -- with a stand-in `RUNNER_TEMP`.

`workflow-manager-trunk-model`'s CP5 updates T-CI-1 (the nightly trigger and
the per-commit concurrency group of `main`) and adds T-CI-7 (the one required
check also needs the new `package` job).
"""

from __future__ import annotations

import ast
import contextlib
import fnmatch
import io
import json
import math
import multiprocessing
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from support import CI_SUITES, NEWEST_RELEASE, REPO_ROOT

import frozen_runs
import test_bootstrap_e2e as bootstrap_e2e
import test_conformance_suite as conformance_suite
import test_update_path as update_path
from parallel import (canonical_json, cli, executor, inventory, isolation, matrix, plan_schema,
                      planner, report, resources, timings, tree, unit)
from workflow_manager.fixture import build_conformance_repo, configure_throwaway_repo, init_git_repo
import workflow_manager.package as package_module
from workflow_manager import source as release_source

TESTS_DIR = REPO_ROOT / "tests"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


def _git_repo(root: Path) -> Path:
    init_git_repo(root)
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    return root


def _commit_all(repo: Path, message: str = "c") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


class _RealHostInventory(unittest.TestCase):
    host: dict[str, list[str]]

    @classmethod
    def setUpClass(cls):
        cls.host = inventory.discover_host(REPO_ROOT)


# -- T-INV-1 / T-INV-2: host discovery ------------------------------------------

class TestHostInventoryIsDeterministic(_RealHostInventory):
    """T-INV-1 (host part)."""

    def test_repeated_discovery_is_byte_identical(self):
        first = inventory.discover(REPO_ROOT)
        second = inventory.discover(REPO_ROOT)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.host, self.host)

    def test_hash_seed_does_not_change_the_inventory(self):
        for seed in ("0", "1", "4242"):
            with self.subTest(seed=seed), mock.patch.dict(os.environ, {"PYTHONHASHSEED": seed}):
                self.assertEqual(canonical_json(inventory.discover_host(REPO_ROOT)),
                                 canonical_json(self.host))

    def test_a_copy_listed_in_reverse_order_yields_the_same_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            shutil.copytree(TESTS_DIR, copy / "tests",
                            ignore=shutil.ignore_patterns("__pycache__"))
            for tree_name in ("src", "tools"):
                (copy / tree_name).symlink_to(REPO_ROOT / tree_name)
            real_listdir = os.listdir
            calls = []

            def reversed_listdir(path="."):
                calls.append(path)
                return list(reversed(sorted(real_listdir(path))))

            with mock.patch("os.listdir", reversed_listdir):
                modules = inventory.host_modules(copy)
                found = inventory.discover_host(copy)
            self.assertTrue(calls, "the patched listing was never consulted")
            self.assertEqual(modules, sorted(modules, key=os.fsencode))
            self.assertEqual(canonical_json(found), canonical_json(self.host))

    def test_inventory_json_is_canonical(self):
        inv = inventory.discover(REPO_ROOT)
        parsed = json.loads(inv.to_json())
        self.assertEqual(parsed["schema_version"], inventory.SCHEMA_VERSION)
        self.assertEqual(parsed["tree_digest"], tree.tree_digest(REPO_ROOT))
        self.assertEqual(inv.to_json(), canonical_json(parsed))


class TestHostInventoryMatchesUnittest(_RealHostInventory):
    """T-INV-2 (host part): the inventory is exactly what unittest's own
    loader finds, as a set of test ids."""

    def test_inventory_equals_unittest_discover(self):
        script = textwrap.dedent("""
            import json, sys, unittest
            sys.dont_write_bytecode = True
            suite = unittest.defaultTestLoader.discover(".", pattern="test_*.py", top_level_dir=".")
            def walk(s):
                for t in s:
                    if isinstance(t, unittest.TestSuite):
                        yield from walk(t)
                    else:
                        yield t
            ids = [t.id() for t in walk(suite)]
            errors = unittest.defaultTestLoader.errors
            print(json.dumps({"ids": ids, "errors": errors}))
        """)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        proc = subprocess.run([sys.executable, "-B", "-c", script], cwd=str(TESTS_DIR),
                              capture_output=True, text=True, env=env, check=True)
        found = json.loads(proc.stdout.splitlines()[-1])
        self.assertEqual(found["errors"], [])
        expected = set()
        for test_id in found["ids"]:
            module, cls, method = test_id.split(".")
            expected.add(inventory.host_test_id(f"{module}.py", cls, method))
        ours = {t for tests in self.host.values() for t in tests}
        self.assertEqual(ours, expected)
        self.assertEqual(sum(len(t) for t in self.host.values()), len(found["ids"]))

    def test_every_unit_is_named_by_its_module_and_class(self):
        for unit_id, tests in self.host.items():
            module, cls = inventory.split_host_unit_id(unit_id)
            self.assertTrue(tests, unit_id)
            for test_id in tests:
                self.assertTrue(test_id.startswith(f"{module}::{cls}::"), test_id)

    def test_every_host_module_contributes_units(self):
        modules = {inventory.split_host_unit_id(u)[0] for u in self.host}
        self.assertEqual(modules, set(inventory.host_modules(REPO_ROOT)))


# -- T-INV-4 / T-INV-5: selection grammar (host forms) -----------------------------

SYNTHETIC = {
    "host:test_a.py::A": ["test_a.py::A::test_1", "test_a.py::A::test_2"],
    "host:test_a.py::B": ["test_a.py::B::test_1"],
    "host:test_b.py::C": ["test_b.py::C::test_x"],
}


class TestSelectionGrammar(_RealHostInventory):
    """T-INV-4 (host forms, union of repeated specs)."""

    def sel(self, *specs):
        return inventory.select(SYNTHETIC, list(specs)).units

    def test_no_spec_is_the_full_selection(self):
        self.assertEqual(self.sel(), {u: None for u in SYNTHETIC})
        full = inventory.select(self.host, [])
        self.assertEqual(full.unit_ids(), sorted(self.host))

    def test_module_class_and_test_forms(self):
        self.assertEqual(self.sel("test_a.py"), {"host:test_a.py::A": None, "host:test_a.py::B": None})
        self.assertEqual(self.sel("test_a.py::B"), {"host:test_a.py::B": None})
        self.assertEqual(self.sel("test_a.py::A::test_2"), {"host:test_a.py::A": ("test_2",)})

    def test_repeated_specs_select_the_union(self):
        self.assertEqual(
            self.sel("test_a.py::A::test_2", "test_b.py", "test_a.py::A::test_1"),
            {"host:test_a.py::A": ("test_1", "test_2"), "host:test_b.py::C": None})
        self.assertEqual(self.sel("test_b.py", "test_b.py"), {"host:test_b.py::C": None})

    def test_a_whole_class_absorbs_its_single_tests_in_either_order(self):
        for specs in (("test_a.py::A::test_1", "test_a.py::A"),
                      ("test_a.py::A", "test_a.py::A::test_1"),
                      ("test_a.py::A::test_1", "test_a.py")):
            with self.subTest(specs=specs):
                self.assertIsNone(self.sel(*specs)["host:test_a.py::A"])

    def test_selection_json_is_deterministic(self):
        one = inventory.select(SYNTHETIC, ["test_b.py", "test_a.py::A::test_2"]).to_json()
        two = inventory.select(dict(reversed(list(SYNTHETIC.items()))),
                               ["test_a.py::A::test_2", "test_b.py"]).to_json()
        self.assertEqual(one, two)

    def test_real_module_spec_selects_exactly_that_module(self):
        chosen = inventory.select(self.host, ["test_bootstrap.py"]).unit_ids()
        expected = sorted(u for u in self.host if u.startswith("host:test_bootstrap.py::"))
        self.assertTrue(expected)
        self.assertEqual(chosen, expected)


class TestSelectionRefusals(unittest.TestCase):
    """T-INV-5 (module, class, test): unknown names are usage errors, never an
    empty selection; malformed specs are syntax errors."""

    def test_unknown_names_raise(self):
        for spec in ("test_zzz.py", "test_a.py::Z", "test_a.py::A::test_9",
                     "frozen:9.9.9/conformance/workflow_state_test.py"):
            with self.subTest(spec=spec), self.assertRaises(inventory.UnknownSelectorError):
                inventory.select(SYNTHETIC, [spec])

    def test_malformed_specs_raise_syntax_errors(self):
        for spec in ("", "test_a", "a.py", "test_a.py::", "test_a.py::A::t::x", "test_a.py::1A",
                     "frozen:2.6/conformance/x.py", "frozen:2.6.0/conformance",
                     "host:test_a.py::A", " test_a.py"):
            with self.subTest(spec=spec), self.assertRaises(inventory.SelectSyntaxError):
                inventory.parse_spec(spec)

    def test_frozen_forms_parse(self):
        spec = inventory.parse_spec("frozen:2.6.0/conformance/workflow_state_test.py::TestFoo")
        self.assertEqual((spec.kind, spec.version, spec.fixture, spec.suite, spec.cls),
                         ("frozen", "2.6.0", "conformance", "workflow_state_test.py", "TestFoo"))

    def test_cli_reports_a_syntax_error_by_name_before_discovery(self):
        # A pre-lock refusal: it reads nothing but argv.
        proc = subprocess.run([sys.executable, str(TESTS_DIR / "run_all.py"), "--list",
                               "--select", "not a spec"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.startswith("run_all: error[SelectSyntaxError]: "), proc.stderr)


# -- T-INV-8: the shared contracts --------------------------------------------------

def _resources_doc(**overrides):
    doc = {
        "schema_version": 1,
        "resources": {
            "repo:tools": {"paths": ["tools/"], "description": "tools"},
            "repo:src": {"paths": ["src/"], "description": "code"},
        },
        "exclusive": {
            "host:test_a.py::A": {"resources": ["repo:tools"], "reason": "rmtree"},
            "host:test_a.py::B": {"resources": ["repo:src", "repo:tools"], "reason": "both"},
        },
    }
    doc.update(overrides)
    return doc


class TestResourcesContract(_RealHostInventory):
    """T-INV-8, `resources.load`."""

    def test_the_committed_declaration_loads_against_the_real_inventory(self):
        """It declares no resource and no exclusive unit; every `orphan_sources`
        id is a discovered unit, and every frozen one is `NEWEST_RELEASE`'s."""
        found = inventory.discover(REPO_ROOT)
        loaded = resources.load(REPO_ROOT, self.host, orphan_unit_ids=found.unit_ids())
        self.assertEqual(loaded.resources, {})
        self.assertEqual(loaded.exclusive_units(), ())
        doc = json.loads(resources.resources_path(REPO_ROOT).read_text())
        orphans = sorted(doc["orphan_sources"])
        self.assertTrue(orphans)
        self.assertEqual(sorted(set(orphans) - set(found.unit_ids())), [])
        for unit_id in orphans:
            if unit_id.startswith(inventory.FROZEN_PREFIX):
                with self.subTest(unit=unit_id):
                    self.assertEqual(inventory.split_frozen_unit_id(unit_id)[0], NEWEST_RELEASE)

    def test_a_valid_two_resource_file_reports_each_tree_union(self):
        loaded = resources.parse(_resources_doc(), SYNTHETIC)
        self.assertEqual(loaded.trees_for("host:test_a.py::A"), ("tools/",))
        self.assertEqual(loaded.trees_for("host:test_a.py::B"), ("src/", "tools/"))
        self.assertEqual(loaded.resources_of("host:test_a.py::B"), ("repo:src", "repo:tools"))
        self.assertEqual(loaded.trees_for("host:test_b.py::C"), ())
        self.assertFalse(loaded.is_exclusive("host:test_b.py::C"))

    def test_load_reads_the_file_under_the_given_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = resources.resources_path(Path(tmp))
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(_resources_doc()))
            self.assertEqual(resources.load(Path(tmp), SYNTHETIC).exclusive_units(),
                             ("host:test_a.py::A", "host:test_a.py::B"))
            path.write_text('{"schema_version": 1, "schema_version": 1}')
            with self.assertRaises(resources.ResourcesFileError):
                resources.load(Path(tmp), SYNTHETIC)

    def test_every_malformed_declaration_is_refused(self):
        def res(paths, description="d"):
            return {"resources": {"r": {"paths": paths, "description": description}},
                    "exclusive": {}}

        cases = {
            "wrong schema_version": _resources_doc(schema_version=2),
            # Review O8: the two cases below were accepted, or refused under the wrong tag.
            "float schema_version": _resources_doc(schema_version=1.0),
            "unhashable resource name": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": [["repo:tools"]], "reason": "x"}}),
            "undeclared resource": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": ["repo:nope"], "reason": "x"}}),
            "empty resources list": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": [], "reason": "x"}}),
            "empty reason": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": ["repo:tools"], "reason": " "}}),
            "unit not in inventory": _resources_doc(exclusive={
                "host:test_zzz.py::Z": {"resources": ["repo:tools"], "reason": "x"}}),
            "bare-string resource (revision-6 form)": _resources_doc(
                resources={"repo:tools": "tools/"}, exclusive={}),
            "empty paths": _resources_doc(**res([])),
            "non-string path": _resources_doc(**res([7])),
            "absolute path": _resources_doc(**res(["/tools/"])),
            "a tree M2 removed": _resources_doc(**res(["distribution/"])),
            "dot-dot component": _resources_doc(**res(["src/../tools/"])),
            "tests/ is not guarded": _resources_doc(**res(["tests/"])),
            "sub-path of a guarded tree": _resources_doc(**res(["src/workflow_manager/"])),
            "docs/ is not guarded": _resources_doc(**res(["docs/"])),
            "tree twice in one resource": _resources_doc(**res(["src/", "src/"])),
            "empty description": _resources_doc(**res(["src/"], description="")),
            "tree claimed by two resources": _resources_doc(resources={
                "a": {"paths": ["src/"], "description": "a"},
                "b": {"paths": ["src/"], "description": "b"}}, exclusive={}),
            "extra resource key": _resources_doc(resources={
                "a": {"paths": ["src/"], "description": "a", "x": 1}}, exclusive={}),
        }
        for name, doc in cases.items():
            with self.subTest(case=name), self.assertRaises(resources.ResourcesFileError):
                resources.parse(doc, SYNTHETIC)

    def test_guarded_trees_are_the_two_the_barrier_covers(self):
        self.assertEqual(resources.GUARDED_TREES, ("src/", "tools/"))


class TestChunkDescriptorContract(unittest.TestCase):
    """T-INV-8, `plan_schema`."""

    def chunk(self, **kw):
        base = dict(id="c1", shard_index=0, units=("host:b", "host:a"), estimate=1.5,
                    resources=("repo:tools",))
        base.update(kw)
        return plan_schema.ChunkDescriptor(**base)

    def test_round_trip_is_canonical(self):
        chunk = self.chunk()
        as_json = chunk.to_json()
        self.assertEqual(as_json["units"], ["host:a", "host:b"])
        self.assertEqual(plan_schema.ChunkDescriptor.from_json(as_json), chunk)
        self.assertEqual(canonical_json(plan_schema.ChunkDescriptor.from_json(
            json.loads(canonical_json(as_json))).to_json()), canonical_json(as_json))
        self.assertTrue(chunk.exclusive)
        self.assertFalse(self.chunk(resources=()).exclusive)

    def test_shard_chunks_returns_stored_order(self):
        a, b = self.chunk(id="z", units=("host:z",)), self.chunk(id="a", units=("host:a",),
                                                                 resources=())
        c = self.chunk(id="m", shard_index=1, units=("host:m",))
        plan = {"shards": [{"chunks": [a.to_json(), b.to_json()], "load": 3.0},
                           {"chunks": [c.to_json()]}], "other": 1}
        self.assertEqual(plan_schema.shard_chunks(plan), [[a, b], [c]])

    def test_a_chunk_missing_any_field_is_refused(self):
        for field in plan_schema.FIELDS:
            obj = self.chunk().to_json()
            del obj[field]
            with self.subTest(field=field), self.assertRaises(plan_schema.PlanSchemaError):
                plan_schema.shard_chunks({"shards": [{"chunks": [obj]}]})

    def test_malformed_descriptors_and_plans_are_refused(self):
        good = self.chunk().to_json()
        bad_chunks = [
            {**good, "extra": 1},
            {**good, "units": []},
            {**good, "units": ["host:b", "host:a"]},
            {**good, "units": ["host:a", "host:a"]},
            {**good, "estimate": -1},
            {**good, "estimate": float("nan")},
            {**good, "estimate": True},
            {**good, "shard_index": "0"},
            {**good, "id": ""},
            {**good, "shard_index": 1},  # stored in shard 0
        ]
        for obj in bad_chunks:
            with self.subTest(obj=obj), self.assertRaises(plan_schema.PlanSchemaError):
                plan_schema.shard_chunks({"shards": [{"chunks": [obj]}]})
        for plan in ({}, {"shards": {}}, {"shards": [{}]}, {"shards": [{"chunks": {}}]}):
            with self.subTest(plan=plan), self.assertRaises(plan_schema.PlanSchemaError):
                plan_schema.shard_chunks(plan)


# -- tree identity and the snapshot -------------------------------------------------

class TestTreeIdentity(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _git_repo(Path(self._tmp.name))
        (self.repo / ".gitignore").write_text("*.log\n__pycache__/\n")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.py").write_text("a = 1\n")
        (self.repo / "README").write_text("r\n")
        _commit_all(self.repo)
        self.clean = tree.tree_digest(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_clean_digest_is_stable_and_depends_on_head(self):
        self.assertEqual(tree.tree_digest(self.repo), self.clean)
        (self.repo / "README").write_text("r2\n")
        _commit_all(self.repo)
        self.assertNotEqual(tree.tree_digest(self.repo), self.clean)

    def test_a_dirty_tree_has_its_own_digest(self):
        (self.repo / "src" / "a.py").write_text("a = 2\n")
        dirty = tree.tree_digest(self.repo)
        self.assertNotEqual(dirty, self.clean)
        (self.repo / "src" / "a.py").write_text("a = 3\n")
        self.assertNotIn(tree.tree_digest(self.repo), (dirty, self.clean))
        (self.repo / "src" / "a.py").write_text("a = 1\n")
        self.assertEqual(tree.tree_digest(self.repo), self.clean)

    def test_an_executable_bit_change_changes_the_digest(self):
        (self.repo / "README").write_text("r2\n")
        modified = tree.tree_digest(self.repo)
        os.chmod(self.repo / "README", 0o755)
        self.assertNotIn(tree.tree_digest(self.repo), (modified, self.clean))

    def test_an_untracked_file_changes_it_and_an_ignored_file_does_not(self):
        (self.repo / "debug.log").write_text("x\n")
        self.assertEqual(tree.tree_digest(self.repo), self.clean)
        (self.repo / "new.txt").write_text("x\n")
        untracked = tree.tree_digest(self.repo)
        self.assertNotEqual(untracked, self.clean)
        (self.repo / "new.txt").write_text("y\n")
        self.assertNotEqual(tree.tree_digest(self.repo), untracked)

    def test_staged_renames_and_deletions_are_part_of_the_identity(self):
        _git(self.repo, "mv", "README", "README.md")
        renamed = tree.tree_digest(self.repo)
        self.assertNotEqual(renamed, self.clean)
        _git(self.repo, "mv", "README.md", "README")
        self.assertEqual(tree.tree_digest(self.repo), self.clean)
        (self.repo / "README").unlink()
        self.assertNotEqual(tree.tree_digest(self.repo), self.clean)

    def test_computing_a_digest_writes_nothing(self):
        before = tree.snapshot(self.repo)
        # A newer mtime with unchanged content leaves the index's stat cache
        # stale, which a plain `git status` would refresh by rewriting it.
        stamp = os.stat(self.repo / "src" / "a.py").st_mtime + 100
        os.utime(self.repo / "src" / "a.py", (stamp, stamp))
        index = (self.repo / ".git" / "index").read_bytes()
        tree.tree_digest(self.repo)
        self.assertEqual(tree.compare(before, tree.snapshot(self.repo)), [])
        self.assertEqual((self.repo / ".git" / "index").read_bytes(), index)

    def test_the_snapshot_sees_an_ignored_file_under_a_guarded_tree(self):
        before = tree.snapshot(self.repo)
        self.assertEqual(before.tree_digest, self.clean)
        (self.repo / "src" / "__pycache__").mkdir()
        (self.repo / "src" / "__pycache__" / "a.cpython-314.pyc").write_bytes(b"\0")
        (self.repo / "docs.log").write_text("outside every snapshot tree\n")
        after = tree.snapshot(self.repo)
        self.assertEqual(after.tree_digest, self.clean)  # ignored: not identity
        diffs = tree.compare(before, after)
        self.assertEqual([d.path for d in diffs], ["src/__pycache__/a.cpython-314.pyc"])
        self.assertEqual(diffs[0].before, tree.UNLISTED)
        self.assertTrue(diffs[0].after.startswith("file:"))

    def test_compare_reports_persistent_changes_only(self):
        before = tree.snapshot(self.repo)
        (self.repo / "src" / "a.py").write_text("changed\n")
        (self.repo / "src" / "a.py").write_text("a = 1\n")
        self.assertEqual(tree.compare(before, tree.snapshot(self.repo)), [])
        (self.repo / "src" / "a.py").write_text("changed\n")
        self.assertEqual([d.path for d in tree.compare(before, tree.snapshot(self.repo))],
                         ["src/a.py"])

    def test_compare_reports_head_movement(self):
        before = tree.snapshot(self.repo)
        _git(self.repo, "commit", "-q", "--allow-empty", "-m", "empty")
        diffs = tree.compare(before, tree.snapshot(self.repo))
        self.assertEqual([d.path for d in diffs], ["HEAD"])


# -- per-unit host execution ----------------------------------------------------------

SYNTHETIC_MODULE = '''
import os
import unittest


class Passing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.environ["WM_FIXTURE_LOG"], "a") as handle:
            handle.write("setUpClass\\n")

    def test_one(self):
        pass

    def test_two(self):
        pass

    @unittest.skip("not today")
    def test_skipped(self):
        pass


class Failing(unittest.TestCase):
    def test_ok(self):
        pass

    def test_bad(self):
        self.assertEqual(1, 2)

    def test_boom(self):
        raise RuntimeError("boom")

    def test_sub(self):
        for i in range(2):
            with self.subTest(i=i):
                self.assertEqual(i, 0)


class SkippingSubtests(unittest.TestCase):
    def test_skips_one(self):
        for i in range(2):
            with self.subTest(i=i):
                if i:
                    self.skipTest("odd")

    def test_fails_then_skips(self):
        for i in range(2):
            with self.subTest(i=i):
                if i:
                    self.skipTest("odd")
                self.assertEqual(i, 1)


class BrokenFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError("fixture")

    def test_never(self):
        pass
'''


class TestHostUnitExecution(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "repo"
        (cls.root / "tests").mkdir(parents=True)
        (cls.root / "tests" / "parallel").symlink_to(TESTS_DIR / "parallel")
        (cls.root / "tests" / "test_synthetic.py").write_text(SYNTHETIC_MODULE)
        cls.run_dir = Path(cls._tmp.name) / "run"
        cls.run_dir.mkdir()
        cls.fixture_log = Path(cls._tmp.name) / "fixture.log"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def launch(self, cls_name, tests=None, index=0):
        with mock.patch.dict(os.environ, {"WM_FIXTURE_LOG": str(self.fixture_log)}):
            return unit.launch(self.root, f"host:test_synthetic.py::{cls_name}", tests,
                               self.run_dir, index)

    def test_a_passing_class_records_every_outcome(self):
        run = self.launch("Passing", index=1)
        self.assertIsNone(run.infrastructure_fault)
        record = run.record
        self.assertEqual(run.returncode, 0)
        self.assertTrue(record["passed"])
        self.assertEqual(record["tests_run"], 3)
        prefix = "test_synthetic.py::Passing::"
        self.assertEqual(record["outcomes"], {prefix + "test_one": "ok", prefix + "test_two": "ok",
                                              prefix + "test_skipped": "skip"})
        self.assertEqual(record["skipped"], {prefix + "test_skipped": "not today"})
        self.assertEqual(record["failing"], [])
        self.assertLessEqual(record["started_at"], record["ended_at"])
        self.assertIn("Ran 3 tests", record["output_tail"])

    def test_selected_methods_run_inside_one_class_fixture(self):
        self.fixture_log.write_text("")
        run = self.launch("Passing", ["test_two", "test_one"], index=2)
        self.assertEqual(run.record["tests_requested"], ["test_one", "test_two"])
        self.assertEqual(sorted(run.record["ran"]), ["test_synthetic.py::Passing::test_one",
                                                     "test_synthetic.py::Passing::test_two"])
        self.assertEqual(self.fixture_log.read_text(), "setUpClass\n")

    def test_failures_errors_and_subtests_are_failing_ids(self):
        run = self.launch("Failing", index=3)
        self.assertIsNone(run.infrastructure_fault)
        self.assertEqual(run.returncode, 1)
        self.assertFalse(run.record["passed"])
        prefix = "test_synthetic.py::Failing::"
        self.assertEqual(run.record["failing"],
                         [prefix + "test_bad", prefix + "test_boom", prefix + "test_sub"])
        self.assertEqual(run.record["outcomes"][prefix + "test_boom"], "error")
        self.assertEqual(run.record["outcomes"][prefix + "test_ok"], "ok")

    def test_a_skipped_subtest_is_recorded_under_its_own_method(self):
        """Review O4: a skipped subtest reaches `addSkip` as a `_SubTest`,
        whose own method name is `runTest`; it belongs to its test method,
        and never hides that method's failed subtest."""
        run = self.launch("SkippingSubtests", index=8)
        self.assertIsNone(run.infrastructure_fault)
        prefix = "test_synthetic.py::SkippingSubtests::"
        self.assertEqual(run.record["outcomes"], {prefix + "test_fails_then_skips": "fail",
                                                  prefix + "test_skips_one": "skip"})
        self.assertEqual(run.record["skipped"], {prefix + "test_fails_then_skips": "odd",
                                                 prefix + "test_skips_one": "odd"})
        self.assertEqual(run.record["failing"], [prefix + "test_fails_then_skips"])
        self.assertEqual(sorted(run.record["ran"]), sorted(run.record["outcomes"]))

    def test_a_class_fixture_error_is_a_failure(self):
        run = self.launch("BrokenFixture", index=4)
        self.assertIsNone(run.infrastructure_fault)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.record["tests_run"], 0)
        self.assertEqual(len(run.record["failing"]), 1)
        self.assertIn("setUpClass", run.record["failing"][0])

    def test_an_unknown_unit_writes_no_record_and_is_an_infrastructure_fault(self):
        for cls_name, tests, index in (("Nope", None, 5), ("Passing", ["test_nope"], 6)):
            with self.subTest(cls=cls_name, tests=tests):
                run = self.launch(cls_name, tests, index=index)
                self.assertEqual(run.returncode, 2)
                self.assertIsNone(run.record)
                self.assertIn("no result record", run.infrastructure_fault)

    def test_units_write_no_bytecode(self):
        self.launch("Passing", index=7)
        self.assertEqual(list((self.root / "tests").glob("__pycache__")), [])


# == CP2: frozen-matrix decomposition ================================================

# -- T-INV-1 / T-INV-2 / T-INV-7: frozen discovery ------------------------------------

class TestFrozenInventory(unittest.TestCase):
    """T-INV-1 and T-INV-2 (frozen parts), T-INV-7."""

    @classmethod
    def setUpClass(cls):
        cls.frozen = inventory.discover_frozen(REPO_ROOT)

    def test_repeated_and_hash_seeded_discovery_is_byte_identical(self):
        expected = canonical_json(self.frozen.to_json())
        for seed in (None, "0", "4242"):
            env = {} if seed is None else {"PYTHONHASHSEED": seed}
            with self.subTest(seed=seed), mock.patch.dict(os.environ, env):
                self.assertEqual(canonical_json(inventory.discover_frozen(REPO_ROOT).to_json()),
                                 expected)

    def test_a_copy_listed_in_reverse_order_yields_the_same_frozen_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            shutil.copytree(TESTS_DIR, copy / "tests",
                            ignore=shutil.ignore_patterns("__pycache__"))
            for tree_name in ("src", "tools"):
                (copy / tree_name).symlink_to(REPO_ROOT / tree_name)
            real_listdir = os.listdir
            with mock.patch("os.listdir", lambda p=".": list(reversed(sorted(real_listdir(p))))):
                found = inventory.discover_frozen(copy)
            self.assertEqual(canonical_json(found.to_json()),
                             canonical_json(self.frozen.to_json()))

    def test_per_suite_totals_equal_the_pinned_counts_for_the_matrix_release(self):
        """Only the release the matrix runs is discovered; the other pinned
        versions' `CI_SUITES` entries are frozen records (plan 7.1)."""
        run = {NEWEST_RELEASE: CI_SUITES[NEWEST_RELEASE]}
        self.assertEqual(self.frozen.ci_suites, {v: dict(s) for v, s in run.items()})
        for version, suites in run.items():
            self.assertEqual(list(self.frozen.ci_suites[version]), list(suites))  # order kept
            self.assertEqual(sorted(self.frozen.classes[version]), sorted(suites))
            for suite, pinned in suites.items():
                with self.subTest(version=version, suite=suite):
                    found = self.frozen.classes[version][suite]
                    self.assertEqual(sum(len(m) for m in found.values()), pinned)

    def test_the_matrix_is_the_newest_release_times_every_fixture(self):
        self.assertEqual(sorted(self.frozen.matrix.values()),
                         sorted((NEWEST_RELEASE, f) for f in matrix.FIXTURES))
        self.assertEqual(len(self.frozen.matrix), 4)
        self.assertFalse([u for u in self.frozen.matrix if re.search(r"\d", u.split("::")[1])],
                         "matrix host classes carry no version in their names")

    def test_frozen_units_multiply_classes_by_fixture(self):
        units = self.frozen.units()
        per_release = {v: sum(len(c) for c in s.values()) for v, s in self.frozen.classes.items()}
        fixtures = len(matrix.FIXTURES)
        self.assertEqual(len(units), fixtures * sum(per_release.values()))
        self.assertEqual(sum(len(t) for t in units.values()),
                         fixtures * sum(CI_SUITES[NEWEST_RELEASE].values()))
        for unit_id in units:
            version, fixture, suite, cls = inventory.split_frozen_unit_id(unit_id)
            self.assertEqual(inventory.frozen_unit_id(version, fixture, suite, cls), unit_id)

    def test_the_full_inventory_carries_both_halves(self):
        inv = inventory.discover(REPO_ROOT)
        self.assertEqual(inv.frozen, self.frozen)
        self.assertTrue(set(self.frozen.matrix) <= set(inv.host))
        self.assertEqual(len(inv.unit_ids()), len(inv.host) + len(self.frozen.units()))
        parsed = json.loads(inv.to_json())
        self.assertEqual(set(parsed["frozen"]), set(self.frozen.units()))

    def test_discovery_leaves_the_tree_byte_identical(self):
        """T-INV-7: including ignored files under the guarded trees -- no new
        `__pycache__`."""
        before = tree.snapshot(REPO_ROOT)
        inventory.discover(REPO_ROOT)
        after = tree.snapshot(REPO_ROOT)
        self.assertEqual(tree.compare(before, after), [])
        self.assertEqual(before.ignored, after.ignored)


TINY_SUITE = '''
import unittest


class TestAlpha(unittest.TestCase):
    def test_one(self):
        pass

    def test_two(self):
        pass


class TestBeta(unittest.TestCase):
    def test_three(self):
        pass


if __name__ == "__main__":
    unittest.main()
'''


class TestFrozenInventoryCountRefusal(unittest.TestCase):
    """T-INV-3: a discovered total that differs from its pin is refused. A
    minimal layout of its own: a one-pin package of one tiny suite, served
    and cached beside the checkout, and a literal `matrix.py`."""

    @staticmethod
    def layout(tmp: Path, pinned: int) -> Path:
        """The checkout, at `tmp/checkout`. Its release lives in
        `tmp/releases` (`TestFrozenInventoryCountRefusal.env`)."""
        root = tmp / "checkout"
        shutil.copytree(TESTS_DIR / "parallel", root / "tests" / "parallel",
                        ignore=shutil.ignore_patterns("__pycache__", "matrix.py", "*.json"))
        shutil.copy2(TESTS_DIR / "support.py", root / "tests" / "support.py")
        (root / "tests" / "portability_exceptions.json").write_text(canonical_json(
            {"by_version": {"0.0.1": {"exceptions": []}}}))
        _writable_copy(REPO_ROOT / "src" / "workflow_manager", root / "src" / "workflow_manager",
                       ignore=shutil.ignore_patterns("__pycache__"))
        publish_synthetic_release(root, tmp / "releases", TINY_SUITE)
        (root / "tests" / "parallel" / "matrix.py").write_text(textwrap.dedent(f"""
            FIXTURES = ("conformance", "target", "bootstrapped")
            CI_SUITES = {{"0.0.1": {{"tiny_test.py": {pinned}}}}}
            FROZEN_MATRIX = {{"host:test_tiny.py::TestTiny": ("0.0.1", "conformance")}}
        """))
        return root

    @staticmethod
    def env(tmp: Path):
        """Discovery reads the layout's release through its own cache."""
        return mock.patch.dict(os.environ, synthetic_release_env(tmp / "releases"))

    def test_a_wrong_pin_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.layout(Path(tmp), pinned=4)
            with self.assertRaises(inventory.InventoryCountError) as caught, self.env(Path(tmp)):
                inventory.discover_frozen(root)
            self.assertIn("discovered 3 tests, CI_SUITES pins 4", str(caught.exception))

    def test_the_right_pin_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp, self.env(Path(tmp)):
            found = inventory.discover_frozen(self.layout(Path(tmp), pinned=3))
            self.assertEqual(found.classes, {"0.0.1": {"tiny_test.py": {
                "TestAlpha": ["test_one", "test_two"], "TestBeta": ["test_three"]}}})
            self.assertEqual(sorted(found.units()), [
                "frozen:0.0.1/conformance/tiny_test.py::TestAlpha",
                "frozen:0.0.1/conformance/tiny_test.py::TestBeta"])


# -- T-INV-4 / T-INV-5: selection grammar (frozen forms) ------------------------------

SYNTHETIC_FROZEN = inventory.FrozenInventory(
    matrix={"host:test_m.py::M1": ("1.0.0", "conformance"),
            "host:test_m.py::M2": ("1.0.0", "target")},
    ci_suites={"1.0.0": {"s_test.py": 3, "t_test.py": 1}},
    classes={"1.0.0": {"s_test.py": {"S1": ["test_a", "test_b"], "S2": ["test_c"]},
                       "t_test.py": {"T1": ["test_d"]}}},
)
SYNTHETIC_MATRIX_HOST = {
    "host:test_m.py::M1": ["test_m.py::M1::test_p", "test_m.py::M1::test_q"],
    "host:test_m.py::M2": ["test_m.py::M2::test_p"],
    "host:test_n.py::N": ["test_n.py::N::test_z"],
}


def _fz(fixture, suite, cls):
    return inventory.frozen_unit_id("1.0.0", fixture, suite, cls)


class TestFrozenSelection(unittest.TestCase):
    """T-INV-4 and T-INV-5, frozen parts."""

    def sel(self, *specs):
        return inventory.select(SYNTHETIC_MATRIX_HOST, list(specs), SYNTHETIC_FROZEN)

    def test_the_two_frozen_forms(self):
        chosen = self.sel("frozen:1.0.0/target/s_test.py")
        self.assertEqual(chosen.units, {_fz("target", "s_test.py", "S1"): None,
                                        _fz("target", "s_test.py", "S2"): None})
        chosen = self.sel("frozen:1.0.0/conformance/s_test.py::S2")
        self.assertEqual(chosen.units, {_fz("conformance", "s_test.py", "S2"): None})

    def test_a_frozen_only_selection_is_flagged_partial(self):
        self.assertTrue(self.sel("frozen:1.0.0/target/t_test.py").partial_frozen)
        # The flag is per matrix host class: M1 selected does not cover M2's.
        self.assertTrue(self.sel("test_m.py::M1", "frozen:1.0.0/target/t_test.py").partial_frozen)
        self.assertFalse(self.sel("test_m.py::M2", "frozen:1.0.0/target/t_test.py").partial_frozen)
        self.assertFalse(self.sel("test_n.py").partial_frozen)

    def test_a_matrix_host_class_brings_all_of_its_frozen_classes(self):
        conformance = {_fz("conformance", s, c): None for s, c in
                       (("s_test.py", "S1"), ("s_test.py", "S2"), ("t_test.py", "T1"))}
        for spec, host_tests in (("test_m.py::M1", None), ("test_m.py::M1::test_q", ("test_q",))):
            with self.subTest(spec=spec):
                chosen = self.sel(spec)
                self.assertEqual(chosen.units, {"host:test_m.py::M1": host_tests, **conformance})
                self.assertFalse(chosen.partial_frozen)
        module = self.sel("test_m.py")
        self.assertEqual(len(module.frozen_unit_ids()), 6)
        self.assertEqual(module.host_unit_ids(), ["host:test_m.py::M1", "host:test_m.py::M2"])

    def test_union_and_the_full_selection(self):
        chosen = self.sel("frozen:1.0.0/target/t_test.py", "frozen:1.0.0/target/t_test.py::T1",
                          "test_n.py")
        self.assertEqual(chosen.units, {_fz("target", "t_test.py", "T1"): None,
                                        "host:test_n.py::N": None})
        full = self.sel()
        self.assertEqual(full.unit_ids(), sorted([*SYNTHETIC_MATRIX_HOST,
                                                  *SYNTHETIC_FROZEN.units()]))
        self.assertFalse(full.partial_frozen)

    def test_unknown_frozen_names_raise(self):
        for spec in ("frozen:9.9.9/target/s_test.py", "frozen:1.0.0/bootstrapped/s_test.py",
                     "frozen:1.0.0/target/u_test.py", "frozen:1.0.0/target/s_test.py::S9"):
            with self.subTest(spec=spec), self.assertRaises(inventory.UnknownSelectorError):
                self.sel(spec)
        with self.assertRaises(inventory.UnknownSelectorError):
            inventory.select(SYNTHETIC_MATRIX_HOST, ["frozen:1.0.0/target/s_test.py"])

    def test_real_matrix_host_class_selects_its_311_frozen_classes(self):
        inv = inventory.discover(REPO_ROOT)
        chosen = inventory.select(inv.host, ["test_conformance_suite.py::TestConformanceFixture"],
                                  inv.frozen)
        self.assertEqual(chosen.host_unit_ids(),
                         ["host:test_conformance_suite.py::TestConformanceFixture"])
        self.assertEqual(len(chosen.frozen_unit_ids()),
                         sum(len(c) for c in inv.frozen.classes[NEWEST_RELEASE].values()))
        self.assertTrue(all(u.startswith(f"frozen:{NEWEST_RELEASE}/conformance/")
                            for u in chosen.frozen_unit_ids()))


# -- T-MRG-1 / -2 / -7: the merge ------------------------------------------------------

MERGE_VERSION = NEWEST_RELEASE


def _record(chunk_id, suite, classes, ran, *, failing=(), returncode=0, fixture="conformance",
            **overrides):
    fields = dict(
        chunk_id=chunk_id, version=MERGE_VERSION, fixture=fixture, suite=suite,
        classes=tuple(classes), returncode=returncode, ran=ran, failing=tuple(failing),
        output=f"<{chunk_id}>\nRan {ran} tests in 0.1s\n", tree_digest="T1", plan_digest="P1",
        release_digest=frozen_runs.release_digest(MERGE_VERSION))
    fields.update(overrides)
    return frozen_runs.FrozenRecord(**fields)


def _context(partition=None, *, tree_digest="T1", plan_digest="P1"):
    partition = partition or {"a_test.py": {"a#0": ("A1", "A2"), "a#1": ("A3",)},
                              "b_test.py": {"b#0": ("B1",)}}
    chunks = [frozen_runs.FrozenChunk(cid, MERGE_VERSION, "conformance", suite, classes)
              for suite, parts in partition.items() for cid, classes in parts.items()]
    discovered = {suite: sorted(c for parts in partition[suite].values() for c in parts)
                  for suite in partition}
    return frozen_runs.MergeContext.from_chunks(MERGE_VERSION, "conformance", chunks, discovered,
                                                tree_digest=tree_digest, plan_digest=plan_digest)


def _records():
    return [_record("a#0", "a_test.py", ("A1", "A2"), 5),
            _record("a#1", "a_test.py", ("A3",), 2, failing=("A3.test_x",), returncode=1),
            _record("b#0", "b_test.py", ("B1",), 4)]


class TestFrozenMerge(unittest.TestCase):
    """T-MRG-1 and T-MRG-2."""

    def test_a_complete_disjoint_record_set_merges(self):
        merged = frozen_runs.merge(_records(), _context())
        self.assertEqual(sorted(merged), ["a_test.py", "b_test.py"])
        a = merged["a_test.py"]
        self.assertEqual((a.ran, a.returncode, a.failing), (7, 1, frozenset({"A3.test_x"})))
        self.assertIn("===== chunk a#0 (A1, A2) =====\n<a#0>", a.output)
        self.assertIn("===== chunk a#1 (A3) =====\n<a#1>", a.output)
        self.assertLess(a.output.index("chunk a#0"), a.output.index("chunk a#1"))
        b = merged["b_test.py"]
        self.assertEqual((b.ran, b.returncode, b.failing), (4, 0, frozenset()))
        self.assertEqual(b.output, "<b#0>\nRan 4 tests in 0.1s\n")  # one chunk: unlabelled
        self.assertEqual(frozen_runs.merge(list(reversed(_records())), _context()), merged)

    def test_ran_is_none_when_any_chunk_has_no_summary(self):
        records = _records()
        records[1] = _record("a#1", "a_test.py", ("A3",), None, returncode=1)
        self.assertIsNone(frozen_runs.merge(records, _context())["a_test.py"].ran)

    def test_a_chunk_killed_by_a_signal_is_never_hidden_by_a_zero(self):
        """Self-review: `max(0, -11)` would read a segfaulted chunk that had
        already printed its summary as green; direct mode reports the crash."""
        records = _records()
        records[0] = _record("a#0", "a_test.py", ("A1", "A2"), 5, returncode=-11)
        records[1] = _record("a#1", "a_test.py", ("A3",), 2)
        self.assertEqual(frozen_runs.merge(records, _context())["a_test.py"].returncode, -11)
        records[1] = _record("a#1", "a_test.py", ("A3",), 2, failing=("A3.test_x",),
                             returncode=1)
        self.assertEqual(frozen_runs.merge(records, _context())["a_test.py"].returncode, -11)
        self.assertEqual(frozen_runs.merge(_records(), _context())["a_test.py"].returncode, 1)

    def test_structural_refusals(self):
        def replaced(index, record):
            records = _records()
            records[index] = record
            return records

        cases = {
            "a planned chunk with no record": _records()[:2],
            "two records for one chunk": _records() + [_records()[2]],
            "a record whose classes differ from its plan":
                replaced(1, _record("a#1", "a_test.py", ("A2",), 2)),
            "a record for an unplanned chunk":
                _records() + [_record("a#2", "a_test.py", ("A4",), 1)],
            "a record of a suite not in the context":
                _records() + [_record("c#0", "c_test.py", ("C1",), 1)],
            "a record of another fixture":
                replaced(2, _record("b#0", "b_test.py", ("B1",), 4, fixture="target")),
            "a foreign tree digest": replaced(2, _record("b#0", "b_test.py", ("B1",), 4,
                                                         tree_digest="T2")),
            "a foreign plan digest": replaced(2, _record("b#0", "b_test.py", ("B1",), 4,
                                                         plan_digest="P2")),
            "a foreign release digest": replaced(2, _record("b#0", "b_test.py", ("B1",), 4,
                                                            release_digest="0" * 64)),
            "a chunk killed on timeout": replaced(2, _record("b#0", "b_test.py", ("B1",), 4,
                                                             timed_out=True)),
        }
        for name, records in cases.items():
            with self.subTest(name), self.assertRaises(frozen_runs.FrozenMergeError):
                frozen_runs.merge(records, _context())

    def test_a_malformed_partition_is_refused_before_any_record_is_read(self):
        partitions = {
            "overlapping class sets": {"a_test.py": {"a#0": ("A1", "A2"), "a#1": ("A2", "A3")}},
            "an empty chunk": {"a_test.py": {"a#0": ("A1",), "a#1": ()}},
        }
        for name, partition in partitions.items():
            with self.subTest(name), self.assertRaises(frozen_runs.FrozenMergeError):
                _context(partition)
        chunk = frozen_runs.FrozenChunk("a#0", MERGE_VERSION, "conformance", "a_test.py", ("A1",))
        for name, discovered in (("a class of the suite in no chunk", {"a_test.py": ["A1", "A2"]}),
                                 ("a class not in the suite", {"a_test.py": []}),
                                 ("a suite with no chunk", {"a_test.py": ["A1"], "b_test.py": ["B1"]})):
            with self.subTest(name), self.assertRaises(frozen_runs.FrozenMergeError):
                frozen_runs.MergeContext.from_chunks(MERGE_VERSION, "conformance", [chunk],
                                                     discovered, tree_digest="T1", plan_digest="P1")

    def test_attribution_names_the_chunk_that_lost_tests(self):
        records = _records()
        records[0] = _record("a#0", "a_test.py", ("A1", "A2"), 3,
                             enumerated=tuple(f"A1.test_{i}" for i in range(5)))
        self.assertEqual(frozen_runs.merge(records, _context())["a_test.py"].attribution(),
                         {"a#0": 2})


class TestMergeContextIsIndependentProvenance(unittest.TestCase):
    """T-MRG-7: the expected values come from a separately supplied context,
    never from the records; merged mode refuses to run without one."""

    def test_a_self_consistent_record_set_for_another_plan_is_refused(self):
        self.assertEqual(sorted(frozen_runs.merge(_records(), _context())),
                         ["a_test.py", "b_test.py"])
        other_partition = {"a_test.py": {"a#0": ("A1",), "a#1": ("A2", "A3")},
                           "b_test.py": {"b#0": ("B1",)}}
        for name, context in (("plan digest", _context(plan_digest="P2")),
                              ("tree digest", _context(tree_digest="T2")),
                              ("chunk partition", _context(other_partition))):
            with self.subTest(name), self.assertRaises(frozen_runs.FrozenMergeError):
                frozen_runs.merge(_records(), context)

    def test_the_context_round_trips_canonically(self):
        context = _context()
        text = context.to_json()
        self.assertEqual(text, canonical_json(json.loads(text)))
        self.assertEqual(frozen_runs.MergeContext.from_json(text), context)
        self.assertEqual(frozen_runs.MergeContext.from_json(text).to_json(), text)
        for bad in (text.replace('"schema_version": 1', '"schema_version": 2'),
                    text.replace('"A3"', '"A2"'), "{}", "[]"):
            with self.assertRaises(frozen_runs.FrozenMergeError):
                frozen_runs.MergeContext.from_json(bad)

    def test_records_round_trip_and_a_malformed_record_is_refused(self):
        record = _records()[1]
        self.assertEqual(frozen_runs.FrozenRecord.from_json(record.to_json()), record)
        with tempfile.TemporaryDirectory() as tmp:
            for r in _records():
                frozen_runs.write_record(r, Path(tmp))
            loaded = frozen_runs.load_records(Path(tmp), MERGE_VERSION, "conformance")
            self.assertEqual(sorted(loaded, key=lambda r: r.chunk_id), _records())
            self.assertEqual(frozen_runs.load_records(Path(tmp), MERGE_VERSION, "target"), [])
            (Path(tmp) / "broken.record.json").write_text("{")
            with self.assertRaises(frozen_runs.FrozenMergeError):
                frozen_runs.load_records(Path(tmp), MERGE_VERSION, "conformance")

    def test_merged_mode_setupclass_refuses_without_an_authoritative_context(self):
        host = conformance_suite.TestConformanceFixture
        with tempfile.TemporaryDirectory() as tmp:
            records, contexts = Path(tmp) / "records", Path(tmp) / "contexts"
            records.mkdir()
            contexts.mkdir()
            foreign = frozen_runs.MergeContext.from_chunks(
                NEWEST_RELEASE, "conformance",
                [frozen_runs.FrozenChunk("x#0", NEWEST_RELEASE, "conformance", "x_test.py", ("X",))],
                {"x_test.py": ["X"]}, tree_digest="0" * 64, plan_digest="P")
            wrong_tree = Path(tmp) / "wrong-tree"
            frozen_runs.write_context(foreign, wrong_tree)
            cases = {
                "records without a context": ({frozen_runs.RECORDS_ENV: str(records)},
                                              "is set but WM_FROZEN_CONTEXT is not"),
                "no context file for (version, fixture)": (
                    {frozen_runs.RECORDS_ENV: str(records), frozen_runs.CONTEXT_ENV: str(contexts)},
                    f"no merge context for {NEWEST_RELEASE}/conformance"),
                "a context from another tree": (
                    {frozen_runs.RECORDS_ENV: str(records), frozen_runs.CONTEXT_ENV: str(wrong_tree)},
                    "is for tree " + "0" * 64),
            }
            for name, (env, message) in cases.items():
                clean = {k: v for k, v in os.environ.items()
                         if k not in (frozen_runs.RECORDS_ENV, frozen_runs.CONTEXT_ENV)}
                with self.subTest(name), mock.patch.dict(os.environ, {**clean, **env}, clear=True):
                    with self.assertRaisesRegex(frozen_runs.FrozenMergeError, re.escape(message)):
                        host.setUpClass()
                    self.assertIsNone(host.Run._run)


# -- T-MRG-3..6: the unchanged host assertions over a merged view ----------------------

SEP = "-" * 70


def _unittest_output(ran, failing=(), *, extra=(), summary=True):
    """What a frozen suite prints: one `FAIL:` block per failing test, then
    the summary unittest.main() writes."""
    lines = []
    for name in failing:
        cls, method = name.split(".")
        lines += ["=" * 70, f"FAIL: {method} (__main__.{name})", SEP, "AssertionError", ""]
    lines += list(extra)
    if summary:
        lines += [SEP, f"Ran {ran} tests in 1.234s", "",
                  f"FAILED (failures={len(failing)})" if failing or extra else "OK"]
    return "\n".join(lines) + "\n"


def _proc(output, returncode):
    return subprocess.CompletedProcess(["python3"], returncode, stdout=output, stderr="")


#: The view-reading assertions of each fixture kind's host classes.
VIEW_ASSERTIONS = {
    "conformance": ("test_every_frozen_suite_passes",
                    "test_every_suite_runs_the_frozen_number_of_tests"),
    "target": ("test_failures_are_exactly_the_documented_portability_exceptions",
               "test_every_suite_still_runs_the_frozen_number_of_tests",
               "test_suites_with_no_exception_pass_outright",
               "test_every_documented_exception_actually_fires"),
    "bootstrapped": ("test_failures_are_exactly_the_documented_exceptions",
                     "test_every_suite_runs_the_frozen_number_of_tests",
                     "test_the_acceptance_matrix_passes_outright",
                     "test_the_installation_verifies_clean_after_the_suite_ran",
                     "test_the_suite_left_the_repository_git_clean"),
}
#: The `updated` class shares the `bootstrapped` assertions (plan 7.1).
VIEW_ASSERTIONS["updated"] = VIEW_ASSERTIONS["bootstrapped"]
_LEGACY_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)


def _legacy_outcomes(fixture, version, procs, expected, residue, drift_found):
    """The pre-CP2 assertion bodies, verbatim in substance, over
    `{suite: CompletedProcess}` -- the oracle the rewritten bodies must
    agree with."""
    pinned = dict(CI_SUITES[version])

    def ran(proc):
        match = _LEGACY_RAN_RE.search(proc.stdout + proc.stderr)
        if match is None:
            raise AssertionError("no unittest summary")
        return int(match.group(1))

    def failures():
        actual = {}
        for suite, proc in procs.items():
            names = support.failing_tests(proc.stdout + proc.stderr)
            if names:
                actual[suite] = names
        assert actual == expected

    def counts():
        assert {suite: ran(proc) for suite, proc in procs.items()} == pinned

    def no_exception_pass():
        for suite, proc in procs.items():
            if suite not in expected:
                assert proc.returncode == 0

    def exceptions_fire():
        for suite, tests in expected.items():
            observed = support.failing_tests(procs[suite].stdout + procs[suite].stderr)
            assert tests & observed == tests

    bodies = {
        "test_every_frozen_suite_passes":
            lambda: [None for p in procs.values() if p.returncode != 0] == [] or _fail(),
        "test_every_suite_runs_the_frozen_number_of_tests": counts,
        "test_every_suite_still_runs_the_frozen_number_of_tests": counts,
        "test_failures_are_exactly_the_documented_portability_exceptions": failures,
        "test_failures_are_exactly_the_documented_exceptions": failures,
        "test_suites_with_no_exception_pass_outright": no_exception_pass,
        "test_every_documented_exception_actually_fires": exceptions_fire,
        "test_the_acceptance_matrix_passes_outright":
            lambda: procs["workflow_acceptance_matrix_test.py"].returncode == 0 or _fail(),
        "test_the_installation_verifies_clean_after_the_suite_ran":
            lambda: drift_found == [] or _fail(),
        "test_the_suite_left_the_repository_git_clean":
            lambda: [l for l in residue if "__pycache__" not in l
                     and not l.endswith(".pyc")] == [] or _fail(),
    }
    outcomes = {}
    for name in VIEW_ASSERTIONS[fixture]:
        try:
            bodies[name]()
            outcomes[name] = "pass"
        except AssertionError:
            outcomes[name] = "fail"
        except Exception:  # noqa: BLE001
            outcomes[name] = "error"
    return outcomes


def _fail():
    raise AssertionError


def _host_outcomes(host, fixture, view):
    """Run the host class's rewritten view-reading bodies against `view`,
    without its `setUpClass`."""
    run = frozen_runs.MatrixRun(host.WORKFLOW_VERSION, fixture, "merged", Path("/nonexistent"),
                                None, view)
    patches = ([mock.patch.object(host.Run, "results", view)] if hasattr(host, "Run") else
               [mock.patch.object(host, "results", view, create=True),
                mock.patch.object(host, "matrix_run", run, create=True)])
    outcomes = {}
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        for name in VIEW_ASSERTIONS[fixture]:
            result = unittest.TestResult()
            host(name).run(result)
            outcomes[name] = ("fail" if result.failures else "error" if result.errors else "pass")
    return outcomes


MATRIX_MODULES = {"test_conformance_suite.py": conformance_suite,
                  "test_bootstrap_e2e.py": bootstrap_e2e, "test_update_path.py": update_path}


def _matrix_hosts():
    for unit_id, (version, fixture) in matrix.FROZEN_MATRIX.items():
        module, cls = inventory.split_host_unit_id(unit_id)
        yield getattr(MATRIX_MODULES[module], cls), version, fixture


def _assertion_module(host):
    """The module whose `expected_portability_exceptions` the host's
    assertion bodies read: where the mixin that defines them lives."""
    for cls in host.__mro__:
        module = sys.modules[cls.__module__]
        if hasattr(module, "expected_portability_exceptions"):
            return module
    raise AssertionError(f"{host.__name__} reads no expected_portability_exceptions")


class _Scenario:
    """One synthetic outcome of every suite of a release: per suite, a list
    of chunks `(ran or None, failing, extra lines, returncode)`, plus
    residue and drift. `direct()` renders each suite as one whole-suite run,
    `merged()` as the chunks' records."""

    def __init__(self, version, fixture, expected):
        self.version, self.fixture = version, fixture
        self.chunks = {}
        for suite, pinned in CI_SUITES[version].items():
            failing = sorted(expected.get(suite, ()))
            half = pinned // 2
            self.chunks[suite] = [[half, [], [], 0],
                                  [pinned - half, failing, [], 1 if failing else 0]]
        self.residue, self.drift = [], []

    def _whole(self, suite):
        parts = self.chunks[suite]
        ran = None if any(p[0] is None for p in parts) else sum(p[0] for p in parts)
        failing = [f for p in parts for f in p[1]]
        extra = [e for p in parts for e in p[2]]
        return _unittest_output(ran, failing, extra=extra, summary=ran is not None), \
            max(p[3] for p in parts)

    def procs(self):
        return {suite: _proc(*self._whole(suite)) for suite in self.chunks}

    def direct(self):
        view = {}
        for index, (suite, proc) in enumerate(self.procs().items()):
            last = index == len(self.chunks) - 1
            chunk = frozen_runs.FrozenChunk(f"direct:{suite}", self.version, self.fixture, suite)
            record = frozen_runs.record_from_process(
                chunk, proc, residue=tuple(self.residue) if last else (),
                drift=tuple(self.drift) if last else ())
            view[suite] = frozen_runs.MergedResult.from_single(record)
        return view

    def merged(self):
        records, partition = [], {}
        for suite, parts in self.chunks.items():
            partition[suite] = {}
            for index, (ran, failing, extra, rc) in enumerate(parts):
                cid, classes = f"{suite}#{index}", (f"C{index}",)
                partition[suite][cid] = classes
                output = _unittest_output(ran, failing, extra=extra, summary=ran is not None)
                chunk = frozen_runs.FrozenChunk(cid, self.version, self.fixture, suite, classes)
                records.append(frozen_runs.record_from_process(
                    chunk, _proc(output, rc), tree_digest="T", plan_digest="P",
                    release_digest=frozen_runs.release_digest(self.version),
                    residue=tuple(self.residue) if index else (),
                    drift=tuple(self.drift) if index else ()))
        chunks = [frozen_runs.FrozenChunk(cid, self.version, self.fixture, suite, classes)
                  for suite, parts in partition.items() for cid, classes in parts.items()]
        discovered = {suite: sorted(c for cs in parts.values() for c in cs)
                      for suite, parts in partition.items()}
        context = frozen_runs.MergeContext.from_chunks(self.version, self.fixture, chunks,
                                                       discovered, tree_digest="T", plan_digest="P")
        return frozen_runs.merge(records, context)


def _baseline_failures(version, fixture):
    """Today's green outcome: a conformance fixture fails nothing; a clean
    target or bootstrapped repository fails exactly its documented
    portability exceptions."""
    return {} if fixture == "conformance" else support.expected_portability_exceptions(version)


ACCEPTANCE = "workflow_acceptance_matrix_test.py"
STALE = ("workflow_state_test.py", "TestStale.test_never_fails")


def _mutate(scenario, mutation):
    acceptance = scenario.chunks[ACCEPTANCE]
    if mutation == "extra failing test":
        acceptance[1][1] = acceptance[1][1] + ["TestExtra.test_new_failure"]
        acceptance[1][3] = 1
    elif mutation == "one missing test":
        acceptance[0][0] -= 1
    elif mutation == "non-empty residue":
        scenario.residue = ["?? stray-file.txt"]
    elif mutation == "only ignorable residue":
        scenario.residue = ["?? scripts/__pycache__/"]
    elif mutation == "non-empty drift":
        scenario.drift = ["modified: scripts/workflow_state.py"]
    elif mutation == "setUpClass error in one chunk":
        # unittest counts one ERROR and none of the class's tests
        acceptance[0][0] -= 3
        acceptance[0][2] = ["=" * 70, "ERROR: setUpClass (__main__.TestBroken)", SEP, ""]
        acceptance[0][3] = 1
    elif mutation == "suite crashes on import":
        acceptance[0] = [None, [], ["Traceback (most recent call last):", "ImportError: x"], 1]


MUTATIONS = (None, "extra failing test", "one missing test", "stale portability exception",
             "non-empty residue", "only ignorable residue", "non-empty drift",
             "setUpClass error in one chunk", "suite crashes on import")


class TestHostAssertionsOverTheMergedView(unittest.TestCase):
    """T-MRG-3, -4, -5, -6: every view-reading assertion of the four matrix
    classes reaches the same verdict over a merged view, over the direct
    view of the equivalent whole-suite runs, and -- as the oracle -- in its
    pre-CP2 form over those `CompletedProcess`es."""

    def test_predicate_equality_for_every_matrix_class_and_mutation(self):
        for host, version, fixture in _matrix_hosts():
            for mutation in MUTATIONS:
                expected = support.expected_portability_exceptions(version)
                if mutation == "stale portability exception":
                    expected = {**expected, STALE[0]: expected.get(STALE[0], set()) | {STALE[1]}}
                scenario = _Scenario(version, fixture, _baseline_failures(version, fixture))
                _mutate(scenario, mutation)
                with self.subTest(host=host.__name__, mutation=mutation), \
                        mock.patch.object(_assertion_module(host),
                                          "expected_portability_exceptions",
                                          lambda v, e=expected: e):
                    legacy = _legacy_outcomes(fixture, version, scenario.procs(), expected,
                                              scenario.residue, scenario.drift)
                    self.assertEqual(_host_outcomes(host, fixture, scenario.direct()), legacy)
                    self.assertEqual(_host_outcomes(host, fixture, scenario.merged()), legacy)
                    if mutation is None or mutation == "only ignorable residue":
                        self.assertEqual(set(legacy.values()), {"pass"})

    def test_every_mutation_is_caught_by_the_fixture_that_asserts_it(self):
        caught = {}
        for host, version, fixture in _matrix_hosts():
            for mutation in MUTATIONS[1:]:
                expected = support.expected_portability_exceptions(version)
                if mutation == "stale portability exception":
                    expected = {**expected, STALE[0]: expected.get(STALE[0], set()) | {STALE[1]}}
                scenario = _Scenario(version, fixture, _baseline_failures(version, fixture))
                _mutate(scenario, mutation)
                with mock.patch.object(_assertion_module(host),
                                       "expected_portability_exceptions",
                                       lambda v, e=expected: e):
                    outcomes = _host_outcomes(host, fixture, scenario.merged())
                if "fail" in outcomes.values():
                    caught.setdefault(mutation, set()).add(fixture)
                self.assertNotIn("error", outcomes.values(), (host.__name__, mutation))
        self.assertEqual(caught, {
            "extra failing test": {"conformance", "target", "bootstrapped", "updated"},
            "one missing test": {"conformance", "target", "bootstrapped", "updated"},
            "stale portability exception": {"target", "bootstrapped", "updated"},
            "non-empty residue": {"bootstrapped", "updated"},
            "non-empty drift": {"bootstrapped", "updated"},
            "setUpClass error in one chunk": {"conformance", "target", "bootstrapped", "updated"},
            "suite crashes on import": {"conformance", "target", "bootstrapped", "updated"},
        })

    def test_a_crashed_or_errored_chunk_merges_and_fails_as_a_test_failure(self):
        """T-MRG-3 and T-MRG-4, called out: no merge refusal, and the two
        count/pass assertions fail -- with today's message for a missing
        summary."""
        host = conformance_suite.TestConformanceFixture
        for mutation in ("setUpClass error in one chunk", "suite crashes on import"):
            scenario = _Scenario("2.6.0", "conformance", {})
            _mutate(scenario, mutation)
            view = scenario.merged()  # does not raise
            with self.subTest(mutation), mock.patch.object(host.Run, "results", view):
                for name in VIEW_ASSERTIONS["conformance"]:
                    result = unittest.TestResult()
                    host(name).run(result)
                    self.assertEqual((len(result.failures), len(result.errors)), (1, 0), name)
                    if mutation == "suite crashes on import" and "number" in name:
                        self.assertIn("no unittest summary in output:", result.failures[0][1])
        host = bootstrap_e2e.TestBootstrappedRepositorySatisfiesTheFrozenSuite
        scenario = _Scenario("2.6.0", "bootstrapped", {})
        _mutate(scenario, "suite crashes on import")
        with mock.patch.object(host, "results", scenario.merged(), create=True):
            result = unittest.TestResult()
            host("test_every_suite_runs_the_frozen_number_of_tests").run(result)
        self.assertEqual(len(result.failures), 1)
        self.assertIn(f"{ACCEPTANCE} produced no summary", result.failures[0][1])

    def test_a_builder_exception_is_a_record_the_merge_accepts(self):
        """T-MRG-6: `execute` turns a raising fixture builder into a
        build-error record; it merges, and the count/pass assertions fail as
        test failures."""
        def broken(release, dest):
            raise RuntimeError("builder exploded")

        chunk = frozen_runs.FrozenChunk("h#0", "2.6.0", "conformance",
                                        "workflow_test_harness_test.py", ("TestScratchRepoBasics",))
        with mock.patch.dict(frozen_runs.FIXTURE_BUILDERS, {"conformance": (broken, "repo")}):
            record = frozen_runs.execute(chunk, tree_digest="T", plan_digest="P")
        self.assertEqual((record.returncode, record.ran, record.failing), (1, None, ()))
        self.assertIn("builder exploded", record.build_error)
        self.assertEqual(record.output, record.build_error)
        context = frozen_runs.MergeContext.from_chunks(
            "2.6.0", "conformance", [chunk],
            {"workflow_test_harness_test.py": ["TestScratchRepoBasics"]},
            tree_digest="T", plan_digest="P")
        view = frozen_runs.merge([record], context)
        host = conformance_suite.TestConformanceFixture
        with mock.patch.object(host.Run, "results", view):
            self.assertEqual(_host_outcomes(host, "conformance", view),
                             {name: "fail" for name in VIEW_ASSERTIONS["conformance"]})


# -- the frozen invocation itself -------------------------------------------------------

class TestFrozenInvocation(unittest.TestCase):

    def test_run_suite_classes_run_exactly_those_classes_as_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            (scripts / "tiny_test.py").write_text(TINY_SUITE)
            whole = support.run_suite(Path(tmp), "tiny_test.py")
            beta = support.run_suite(Path(tmp), "tiny_test.py", classes=("TestBeta",))
            both = support.run_suite(Path(tmp), "tiny_test.py", classes=("TestAlpha", "TestBeta"))
        self.assertIn("Ran 3 tests", whole.stderr)
        self.assertIn("Ran 1 test ", beta.stderr)
        self.assertIn("Ran 3 tests", both.stderr)

    def test_execute_runs_a_real_chunk_in_a_fresh_repository_and_stamps_provenance(self):
        chunk = frozen_runs.FrozenChunk(
            "h#1", "2.6.0", "bootstrapped", "workflow_test_harness_test.py",
            ("TestScratchRepoCommitTrailers", "TestScratchRepoPlanDocs"))
        record = frozen_runs.execute(chunk, tree_digest="T", plan_digest="P")
        self.assertEqual((record.returncode, record.ran, record.failing), (0, 7, ()))
        self.assertEqual((record.tree_digest, record.plan_digest), ("T", "P"))
        self.assertEqual(record.release_digest, frozen_runs.release_digest("2.6.0"))
        self.assertEqual((record.residue, record.drift), ((), ()))
        self.assertFalse(record.timed_out)
        self.assertLessEqual(record.started_at, record.ended_at)

    def test_fixed_chunkings_partition_every_suite(self):
        frozen = inventory.discover_frozen(REPO_ROOT)
        for mode in ("two-chunk", "one-class"):
            chunks = frozen_runs.fixed_chunking(frozen, NEWEST_RELEASE, "target", mode)
            with self.subTest(mode):
                frozen_runs.MergeContext.from_chunks(
                    NEWEST_RELEASE, "target", chunks,
                    {s: list(c) for s, c in frozen.classes[NEWEST_RELEASE].items()},
                    tree_digest="T", plan_digest=frozen_runs.chunking_digest(chunks))
                per_suite = {}
                for chunk in chunks:
                    per_suite.setdefault(chunk.suite, []).append(chunk)
                for suite, parts in per_suite.items():
                    classes = frozen.classes[NEWEST_RELEASE][suite]
                    expected = (len(classes) if mode == "one-class" else min(2, len(classes)))
                    self.assertEqual(len(parts), expected, suite)
                    self.assertEqual(sum(len(c.enumerated) for c in parts),
                                     CI_SUITES[NEWEST_RELEASE][suite])


class TestFullStateSnapshot(unittest.TestCase):
    """The E-MRG-3 measurement sees worktree and git-dir state `git status`
    alone does not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _git_repo(Path(self._tmp.name))
        (self.repo / ".gitignore").write_text("ignored/\n")
        (self.repo / "a.txt").write_text("a\n")
        _commit_all(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def delta_keys(self, change):
        before = frozen_runs.full_state(self.repo)
        change()
        return [k for k, _, _ in frozen_runs.state_delta(before, frozen_runs.full_state(self.repo))]

    def test_every_kind_of_state_is_observed(self):
        def write(rel, text=""):
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

        cases = {
            "an ignored file": (lambda: write("ignored/x.bin", "x"), "worktree:ignored/x.bin"),
            "a new commit": (lambda: (write("b.txt", "b"), _commit_all(self.repo)), "git:HEAD"),
            "a branch": (lambda: _git(self.repo, "branch", "side"), "ref:refs/heads/side"),
            "a config key": (lambda: _git(self.repo, "config", "wm.test", "1"), "git:config"),
            "a hook": (lambda: write(".git/hooks/pre-commit", "#!/bin/sh\n"),
                       "gitdir:hooks/pre-commit"),
            "a Workflow claim": (lambda: write(".git/ai-workflow/claims/x.claim.json", "{}"),
                                 "gitdir:ai-workflow/claims/x.claim.json"),
        }
        for name, (change, key) in cases.items():
            with self.subTest(name):
                self.assertIn(key, self.delta_keys(change))

    def test_the_pre_classified_kinds(self):
        empty = "file:-:" + __import__("hashlib").sha256(b"").hexdigest()
        self.assertEqual(frozen_runs.classify_delta("worktree:scripts/__pycache__/m.cpython-314.pyc",
                                                    "!!:file:-:00"), "bytecode")
        self.assertEqual(frozen_runs.classify_delta("worktree:scripts/__pycache__/x.tmp",
                                                    "!!:file:-:00"), "bytecode")
        self.assertEqual(frozen_runs.classify_delta(
            "worktree:.ai-review/runtime/WORKFLOW_STATE.lock", f"!!:{empty}"), "flock")
        token = "a" * 64
        for key in ("worktree:.ai-review/runtime/PLAN_APPROVAL_MUTATION.guardlock",
                    "worktree:.ai-review/runtime/WORKTREE_IDENTITY.lock",
                    f"gitdir:ai-workflow/checkpoint-claims/{token}.guardlock",
                    f"gitdir:ai-workflow/checkpoint-claims/{token}.lifecycle.lock",
                    "gitdir:ai-workflow/identity-gap.lock"):
            with self.subTest(key):
                self.assertEqual(frozen_runs.classify_delta(key, empty), "flock")
                self.assertIsNone(frozen_runs.classify_delta(key, "file:-:" + "1" * 64))
        for key in (f"gitdir:ai-workflow/checkpoint-claims/{token}.claim.json",
                    "gitdir:ai-workflow/checkpoint-claims/abc.lifecycle.lock",
                    "worktree:.ai-review/runtime/OTHER.lock",
                    "gitdir:.ai-review/runtime/WORKFLOW_STATE.lock"):
            with self.subTest(key):
                self.assertIsNone(frozen_runs.classify_delta(key, empty))
        self.assertIsNone(frozen_runs.classify_delta("git:HEAD", "abc"))


# -- CP3: timing history and the planner -------------------------------------------------

PLAN_CONFIG = {
    "target_shard_seconds": 240.0, "min_shards": 2, "local_max_shards": 8, "ci_max_shards": 16,
    "default_unit_seconds": 30.0, "default_group_overhead_seconds": 0.5,
    "split_threshold_ratio": 0.5, "ci_account_concurrent_job_limit": 20,
}
NO_RESOURCES = resources.Resources({}, {})


def _config(**overrides):
    return {**PLAN_CONFIG, **overrides}


def _timings(local=None, ci=None, overhead=None, setup=None):
    units = {}
    for profile, values in (("local", local), ("ci", ci)):
        if values is not None:
            units[profile] = {u: timings.UnitTiming(float(s), 1) for u, s in values.items()}
    return timings.Timings(units=units, group_overhead=overhead or {},
                           ci_job_setup=setup or {})


def _host(module, cls):
    return inventory.host_unit_id(module, cls)


def _frozen(suite, cls, fixture="conformance", version="1.0.0"):
    return inventory.frozen_unit_id(version, fixture, suite, cls)


def _selection(unit_ids):
    return inventory.Selection({u: None for u in sorted(unit_ids)})


def _plan(unit_ids, estimates=None, *, matrix=(), config=None, profile="local",
          res=NO_RESOURCES, overhead=None, inventory_ids=None, timing=None, **options):
    options.setdefault("cpu_count", 16)
    if timing is None:
        timing = _timings(**{profile: estimates or {}},
                          overhead={profile: overhead} if overhead else None)
    return planner.build_plan(
        _selection(unit_ids), inventory_unit_ids=inventory_ids or unit_ids, matrix_units=matrix,
        timings=timing, config=config or dict(PLAN_CONFIG), profile=profile,
        tree_digest="T" * 64, resources=res, **options)


def _chunks(plan):
    return [c for shard in plan_schema.shard_chunks(plan) for c in shard]


def _all_plan_units(plan):
    return [u for shard in plan_schema.shard_chunks(plan) + plan_schema.shard_chunks(
        plan["phase_b"]) for c in shard for u in c.units]


def _random_scenario(rng):
    """A random inventory, selection, timing file and bounds (T-PLN-1)."""
    host = [_host(f"test_m{m}.py", f"C{c}") for m in range(rng.randint(1, 4))
            for c in range(rng.randint(1, 6))]
    frozen = [_frozen(f"s{g}_test.py", f"K{c}", fixture=rng.choice(matrix.FIXTURES))
              for g in range(rng.randint(0, 3)) for c in range(rng.randint(1, 30))]
    frozen = sorted(set(frozen))
    universe = host + frozen
    chosen = [u for u in universe if rng.random() < 0.8] or [universe[0]]
    matrix_units = [u for u in host if rng.random() < 0.2]
    if all(u in matrix_units for u in chosen):
        matrix_units = []

    def seconds():
        return rng.choice([0.0, round(rng.uniform(0, 5), 1), round(rng.uniform(0, 300), 1)])

    profile = rng.choice(timings.PROFILES)
    timing = _timings(**{profile: {u: seconds() for u in universe if rng.random() < 0.7}},
                      overhead={profile: {f: round(rng.uniform(0, 3), 2) for f in matrix.FIXTURES}})
    config = _config(target_shard_seconds=float(rng.randint(30, 300)),
                     min_shards=rng.randint(1, 3), local_max_shards=rng.randint(1, 16),
                     ci_max_shards=rng.randint(1, 24),
                     split_threshold_ratio=rng.choice([0.2, 0.5, 1.0]))
    options = {"shards": rng.choice([None, None, rng.randint(1, 20)]),
               "cpu_count": rng.randint(1, 16), "whole_groups": rng.random() < 0.2,
               "phase_b_workers": rng.randint(1, 8)}
    return dict(unit_ids=chosen, inventory_ids=universe, matrix=matrix_units, config=config,
                profile=profile, timing=timing, **options)


class TestPlanPartitionsTheSelection(unittest.TestCase):
    """T-PLN-1: INV-1 over randomized (seeded, recorded) inventories, timing
    files and bounds."""

    def test_every_random_plan_partitions_its_selection_exactly(self):
        import random
        for seed in range(60):
            with self.subTest(seed=seed):
                scenario = _random_scenario(random.Random(seed))
                plan = _plan(**scenario)
                units = _all_plan_units(plan)
                self.assertEqual(len(units), len(set(units)), f"seed {seed}: a unit twice")
                self.assertEqual(set(units), set(scenario["unit_ids"]), f"seed {seed}")
                shards = [set(u for c in s for u in c.units)
                          for s in plan_schema.shard_chunks(plan)]
                for i, left in enumerate(shards):
                    for right in shards[i + 1:]:
                        self.assertFalse(left & right, f"seed {seed}: shards intersect")
                self.assertEqual(len(shards), plan["n"])
                self.assertTrue(all(shards), f"seed {seed}: an empty shard")
                phase_b = {u for s in plan_schema.shard_chunks(plan["phase_b"])
                           for c in s for u in c.units}
                self.assertEqual(phase_b, set(scenario["unit_ids"]) & set(scenario["matrix"]))


class TestPlannerRefusesABrokenAssignment(unittest.TestCase):
    """T-PLN-2."""

    UNITS = [_host("test_a.py", c) for c in "ABCDE"]

    def test_a_dropped_or_duplicated_unit_is_refused(self):
        real = planner._assign

        def dropping(chunks, n):
            shards = real(chunks, n)
            longest = max(range(n), key=lambda i: len(shards[i]))
            shards[longest] = shards[longest][:-1]
            return shards

        def duplicating(chunks, n):
            shards = real(chunks, n)
            shards[-1] = shards[-1] + [shards[0][0]]
            return shards

        estimates = {u: 10.0 * i for i, u in enumerate(self.UNITS, 1)}
        for broken, message in ((dropping, r"missing \['host:"), (duplicating, r"duplicated \['host:")):
            with self.subTest(broken.__name__), mock.patch.object(planner, "_assign", broken), \
                    self.assertRaisesRegex(planner.PartitionError, message):
                _plan(self.UNITS, estimates)
        self.assertTrue(_plan(self.UNITS, estimates)["plan_digest"])

    def test_verify_partition_names_what_is_wrong(self):
        plan = _plan(self.UNITS, {u: 10 for u in self.UNITS})
        plan["selection"][_host("test_a.py", "Z")] = None
        with self.assertRaisesRegex(planner.PartitionError, "missing .*test_a.py::Z"):
            planner.verify_partition(plan)
        plan = _plan(self.UNITS, {u: 10 for u in self.UNITS})
        del plan["selection"][self.UNITS[0]]
        with self.assertRaisesRegex(planner.PartitionError, "not selected"):
            planner.verify_partition(plan)
        plan = _plan(self.UNITS, {u: 10 for u in self.UNITS})
        plan["shards"].append({"chunks": [], "load": 0})
        plan["n"] += 1
        with self.assertRaisesRegex(planner.PartitionError, "empty shard"):
            planner.verify_partition(plan)


_PLAN_IN_SUBPROCESS = r"""
import json, sys
from parallel import inventory, planner, resources, timings
doc = json.load(sys.stdin)
plan = planner.build_plan(
    inventory.Selection({u: None for u in doc["units"]}),
    inventory_unit_ids=doc["units"], matrix_units=set(doc["matrix"]),
    timings=timings.parse(doc["timings"]), config=doc["config"], profile="local",
    tree_digest="T" * 64, resources=resources.parse(doc["resources"], doc["units"]),
    cpu_count=8)
sys.stdout.write(planner.to_json(plan))
"""


class TestPlanIsDeterministic(unittest.TestCase):
    """T-PLN-3 (INV-3)."""

    def scenario(self):
        units = [_host("test_a.py", f"C{i}") for i in range(12)] + \
                [_frozen("s_test.py", f"K{i:02d}") for i in range(40)] + \
                [_frozen("t_test.py", f"K{i}", fixture="target") for i in range(5)]
        estimates = {u: float(7 * (i % 5) + 3) for i, u in enumerate(units)}
        return units, estimates

    def test_same_inputs_give_the_same_bytes_whatever_the_input_order(self):
        units, estimates = self.scenario()
        first = planner.to_json(_plan(units, estimates, matrix=[units[0]]))
        self.assertEqual(first, planner.to_json(_plan(units, estimates, matrix=[units[0]])))
        reordered = planner.build_plan(
            inventory.Selection({u: None for u in reversed(units)}),
            inventory_unit_ids=list(reversed(units)), matrix_units=[units[0]],
            timings=_timings(local=dict(reversed(list(estimates.items())))),
            config=dict(reversed(list(PLAN_CONFIG.items()))), profile="local",
            tree_digest="T" * 64, resources=NO_RESOURCES, cpu_count=16)
        self.assertEqual(first, planner.to_json(reordered))

    def test_hash_seed_does_not_enter_the_plan(self):
        units, estimates = self.scenario()
        timing_doc = json.loads(_timings(local=estimates).to_json())
        resource_doc = {"schema_version": 1,
                        "resources": {"r": {"paths": ["tools/"], "description": "d"}},
                        "exclusive": {units[3]: {"resources": ["r"], "reason": "x"}}}
        payload = json.dumps({"units": units, "matrix": [units[0]], "timings": timing_doc,
                              "config": PLAN_CONFIG, "resources": resource_doc})
        outputs = set()
        for seed in ("0", "1", "4242"):
            env = {**unit.unit_env(), "PYTHONHASHSEED": seed}
            proc = subprocess.run([sys.executable, "-B", "-c", _PLAN_IN_SUBPROCESS],
                                  cwd=str(TESTS_DIR), input=payload, capture_output=True,
                                  text=True, env=env, check=True)
            outputs.add(proc.stdout)
        self.assertEqual(len(outputs), 1)

    def test_equal_estimates_are_broken_by_unit_id(self):
        units = [_host("test_a.py", c) for c in "EDCBA"]
        plan = _plan(units, {u: 5.0 for u in units}, shards=2)
        self.assertEqual([[c.id for c in s] for s in plan_schema.shard_chunks(plan)],
                         [[_host("test_a.py", "A"), _host("test_a.py", "C"),
                           _host("test_a.py", "E")],
                          [_host("test_a.py", "B"), _host("test_a.py", "D")]])


class TestShardCount(unittest.TestCase):
    """T-PLN-4 (5.3 arithmetic)."""

    def test_n_is_the_clamped_ceiling(self):
        cfg = _config(target_shard_seconds=100.0, min_shards=2, local_max_shards=8)
        for total, chunks, cpu, expected in ((50, 30, 16, 2), (250, 30, 16, 3), (401, 30, 16, 5),
                                             (5000, 30, 16, 8), (5000, 30, 4, 4),
                                             (5000, 3, 16, 3), (50, 1, 16, 1), (0, 5, 16, 2)):
            with self.subTest(total=total, chunks=chunks, cpu=cpu):
                self.assertEqual(planner.shard_count(total, chunks, cfg, "local", cpu), expected)

    def test_the_override_is_clamped_to_the_chunk_count(self):
        for override, expected in ((1, 1), (5, 5), (100, 7), (0, 1)):
            with self.subTest(override=override):
                self.assertEqual(
                    planner.shard_count(10_000, 7, PLAN_CONFIG, "local", 16, override), expected)

    def test_ci_never_exceeds_the_concurrent_job_limit_minus_one(self):
        for limit, ci_max, expected in ((20, 16, 16), (10, 16, 9), (2, 16, 1), (40, 24, 24)):
            with self.subTest(limit=limit, ci_max=ci_max):
                cfg = _config(ci_account_concurrent_job_limit=limit, ci_max_shards=ci_max)
                self.assertEqual(planner.max_shards(cfg, "ci", 2), expected)
                self.assertEqual(planner.shard_count(10 ** 6, 100, cfg, "ci", 2), expected)

    def test_plans_record_n_and_never_leave_a_shard_empty(self):
        units = [_host("test_a.py", f"C{i}") for i in range(3)]
        plan = _plan(units, {u: 1000.0 for u in units})
        self.assertEqual(plan["n"], 3)
        self.assertEqual(len(plan["shards"]), 3)

    def test_the_critical_path_warning_appears_iff_c_exceeds_the_target(self):
        units = [_host("test_a.py", "Big"), _host("test_a.py", "Small")]
        for big, warned in ((240.0, False), (240.1, True), (10.0, False)):
            with self.subTest(big=big):
                plan = _plan(units, {units[0]: big, units[1]: 1.0})
                predicted = plan["predicted"]
                self.assertEqual(predicted["critical_path"], big)
                self.assertEqual(predicted["critical_path_chunk"], units[0])
                self.assertEqual(predicted["critical_path_warning"] is not None, warned)
                if warned:
                    self.assertIn(units[0], predicted["critical_path_warning"])


class TestChunking(unittest.TestCase):
    """T-PLN-5 (5.4 chunking, phase B, the predicted makespan)."""

    def test_a_group_under_the_threshold_is_one_chunk(self):
        classes = [_frozen("s_test.py", f"K{i}") for i in range(10)]
        plan = _plan(classes, {u: 11.0 for u in classes}, overhead={"conformance": 9.0})
        self.assertEqual([c.units for c in _chunks(plan)], [tuple(classes)])
        self.assertEqual(_chunks(plan)[0].estimate, 119.0)  # 110 + overhead, <= 0.5 x 240

    def test_a_larger_group_splits_into_exactly_k_chunks_covering_it_once(self):
        classes = [_frozen("s_test.py", f"K{i:02d}") for i in range(25)]
        estimates = {u: float(i + 1) for i, u in enumerate(classes)}   # 325 s
        plan = _plan(classes, estimates, overhead={"conformance": 5.0})
        chunks = _chunks(plan)
        self.assertEqual(len(chunks), math.ceil((325 + 5) / 120))
        units = [u for c in chunks for u in c.units]
        self.assertEqual(sorted(units), sorted(classes))
        for chunk in chunks:
            self.assertAlmostEqual(chunk.estimate, sum(estimates[u] for u in chunk.units) + 5.0)

    def test_k_never_exceeds_the_class_count(self):
        classes = [_frozen("s_test.py", "Huge"), _frozen("s_test.py", "Huger")]
        plan = _plan(classes, {classes[0]: 900.0, classes[1]: 1000.0})
        self.assertEqual(sorted(len(c.units) for c in _chunks(plan)), [1, 1])

    def test_host_classes_never_split(self):
        units = [_host("test_a.py", "Huge"), _host("test_a.py", "Tiny")]
        plan = _plan(units, {units[0]: 5000.0, units[1]: 0.1})
        self.assertEqual(sorted(c.units for c in _chunks(plan)), [(units[0],), (units[1],)])

    def test_whole_groups_splits_nothing_and_changes_no_selection(self):
        classes = [_frozen("s_test.py", f"K{i:02d}") for i in range(25)] + \
                  [_frozen("t_test.py", f"K{i:02d}", fixture="target") for i in range(25)]
        estimates = {u: 20.0 for u in classes}
        split = _plan(classes, estimates)
        whole = _plan(classes, estimates, whole_groups=True)
        self.assertGreater(len(_chunks(split)), 2)
        self.assertEqual(len(_chunks(whole)), 2)
        for key in ("selection", "selection_digest"):
            self.assertEqual(json.dumps(split[key]), json.dumps(whole[key]))

    def test_phase_b_units_get_their_own_assignment(self):
        hosts = [_host("test_m.py", f"M{i}") for i in range(5)]
        others = [_host("test_a.py", f"C{i}") for i in range(6)]
        frozen = [_frozen("s_test.py", f"K{i}") for i in range(4)]
        units = hosts + others + frozen
        estimates = {u: float(3 + i) for i, u in enumerate(units)}
        for profile, workers in (("local", None), ("ci", 2)):
            with self.subTest(profile=profile):
                plan = _plan(units, estimates, matrix=hosts, profile=profile,
                             phase_b_workers=workers)
                phase_a = {u for c in _chunks(plan) for u in c.units}
                phase_b = [c for s in plan_schema.shard_chunks(plan["phase_b"]) for c in s]
                self.assertEqual(sorted(u for c in phase_b for u in c.units), sorted(hosts))
                self.assertFalse(phase_a & set(hosts))
                self.assertEqual(plan["phase_b"]["workers"],
                                 plan["n"] if profile == "local" else 2)

    def test_the_predicted_makespan_is_the_sum_of_its_terms(self):
        hosts = [_host("test_m.py", f"M{i}") for i in range(3)]
        units = hosts + [_host("test_a.py", f"C{i}") for i in range(9)] + \
            [_frozen("s_test.py", f"K{i}") for i in range(30)]
        estimates = {u: float(1 + (7 * i) % 23) for i, u in enumerate(units)}
        exclusive = resources.parse(
            {"schema_version": 1, "resources": {"r": {"paths": ["tools/"], "description": "d"}},
             "exclusive": {units[4]: {"resources": ["r"], "reason": "x"}}},
            [u for u in units if u.startswith("host:")])
        local = _plan(units, estimates, matrix=hosts, res=exclusive)
        terms = local["predicted"]["makespan"]
        shards = plan_schema.shard_chunks(local)
        self.assertEqual(terms["exclusive_a0"], estimates[units[4]])
        self.assertAlmostEqual(terms["phase_a"], max(sum(c.estimate for c in s if not c.exclusive)
                                                     for s in shards))
        self.assertAlmostEqual(terms["phase_b"], max(
            sum(c.estimate for c in s) for s in plan_schema.shard_chunks(local["phase_b"])))
        self.assertAlmostEqual(terms["total"], terms["exclusive_a0"] + terms["phase_a"]
                               + terms["phase_b"])
        timing = _timings(ci=estimates, setup={"plan": 30.0, "shard": 60.0, "aggregate": 45.0})
        ci = _plan(units, matrix=hosts, profile="ci", timing=timing, res=exclusive,
                   phase_b_workers=2)
        terms = ci["predicted"]["makespan"]
        self.assertEqual(terms["plan_job"], 30.0)
        self.assertAlmostEqual(terms["shard_job"], 60.0 + max(s["load"] for s in ci["shards"]))
        self.assertAlmostEqual(terms["aggregate_job"],
                               45.0 + max(s["load"] for s in ci["phase_b"]["shards"]))
        self.assertAlmostEqual(terms["total"], terms["plan_job"] + terms["shard_job"]
                               + terms["aggregate_job"])


class TestLongestProcessingTimeFirst(unittest.TestCase):
    """T-PLN-6."""

    def test_hand_computed_assignments(self):
        items = [(7, "a", "a"), (6, "b", "b"), (5, "c", "c"), (4, "d", "d"), (3, "e", "e")]
        self.assertEqual([[i for _, i, _ in b] for b in planner.lpt(items, 2)],
                         [["a", "d", "e"], ["b", "c"]])
        self.assertEqual([[i for _, i, _ in b] for b in planner.lpt(items, 3)],
                         [["a"], ["b", "e"], ["c", "d"]])
        zeros = [(0.0, x, x) for x in "abc"]
        self.assertEqual([[i for _, i, _ in b] for b in planner.lpt(zeros, 3)],
                         [["a"], ["b"], ["c"]])

    def test_random_cases_are_within_four_thirds_of_the_optimum(self):
        import itertools
        import random
        rng = random.Random(20260927)
        for case in range(80):
            n = rng.randint(2, 3)
            sizes = [rng.randint(1, 40) for _ in range(rng.randint(n, 8))]
            items = [(float(s), f"u{i}", None) for i, s in enumerate(sizes)]
            makespan = max(sum(e for e, _, _ in b) for b in planner.lpt(items, n))
            best = min(max(sum(s for s, where in zip(sizes, a) if where == k) for k in range(n))
                       for a in itertools.product(range(n), repeat=len(sizes)))
            with self.subTest(case=case, sizes=sizes, n=n):
                self.assertLessEqual(makespan, best * 4 / 3 + 1e-9)


class TestTimingLifecycle(unittest.TestCase):
    """T-PLN-7 (5.2)."""

    A, B, C, D, E = (_host("test_a.py", c) for c in "ABCDE")
    F = _frozen("s_test.py", "K1")
    G = _frozen("s_test.py", "K2")

    def test_the_new_unit_estimate_falls_back_in_the_stated_order(self):
        timing = _timings(local={self.A: 10.0, self.B: 20.0, self.F: 4.0, "host:test_z.py::Gone": 999},
                          ci={self.A: 30.0, self.B: 40.0, self.C: 50.0,
                              "host:test_y.py::Gone": 1.0})
        inventory_ids = [self.A, self.B, self.C, self.D, self.E, self.F, self.G,
                         _host("test_q.py", "Q")]
        got = timings.estimate_units(timing, "local", inventory_ids, inventory_ids, 30.0)
        self.assertEqual(got[self.A], timings.Estimate(10.0, timings.MEASURED))
        # ratio = median(10/30, 20/40) = (1/3 + 1/2) / 2
        self.assertEqual(got[self.C].source, timings.OTHER_PROFILE)
        self.assertAlmostEqual(got[self.C].seconds, 50.0 * (1 / 3 + 1 / 2) / 2, places=2)
        self.assertEqual(got[self.D], timings.Estimate(15.0, timings.GROUP_MEDIAN))
        self.assertEqual(got[self.G], timings.Estimate(4.0, timings.GROUP_MEDIAN))
        self.assertEqual(got[_host("test_q.py", "Q")], timings.Estimate(30.0, timings.DEFAULT))
        # Orphaned entries inform nothing: test_z.py's 999 s is not a group peer
        # of a new test_z.py class, and no ratio exists without shared units.
        alone = timings.estimate_units(timing, "local", [_host("test_z.py", "New")],
                                       [_host("test_z.py", "New")], 30.0)
        self.assertEqual(alone[_host("test_z.py", "New")].source, timings.DEFAULT)

    def test_orphaned_and_drifted_units_are_reported_never_selected_or_dropped(self):
        units = [self.A, self.B]
        timing = _timings(local={self.A: 5.0, self.B: 5.0, self.C: 7.0})
        plan = _plan(units, timing=timing)
        self.assertEqual(plan["timing"]["orphaned"], [self.C])
        self.assertNotIn(self.C, _all_plan_units(plan))
        self.assertEqual(sorted(_all_plan_units(plan)), units)
        self.assertEqual(timings.drifted({self.A: 5.0, self.B: 5.0, self.D: 0.0},
                                         {self.A: 12.0, self.B: 6.0, self.D: 0.4}), [self.A])
        self.assertEqual(timings.drifted({self.A: 10.0}, {self.A: 4.0}), [self.A])
        kept = timings.update(timing, [timings.Observation("local", 12.0, "pass", "t1",
                                                           unit=self.A)], "local")
        self.assertIn(self.A, kept.units["local"])
        self.assertIn(self.C, kept.units["local"])   # no inventory given: nothing dropped

    def obs(self, unit, seconds, utc, outcome="pass", profile="local"):
        return timings.Observation(profile, seconds, outcome, utc, unit=unit)

    def test_update_keeps_the_median_of_the_last_five(self):
        observations = [self.obs(self.A, s, f"2026-01-0{i}") for i, s in
                        enumerate([100, 100, 100, 1, 2, 3, 4], 1)]
        observations.append(self.obs(self.A, 999, "2026-01-09", outcome="fail"))
        observations.append(self.obs(self.A, 999, "2026-01-09", profile="ci"))
        after = timings.update(timings.Timings(), list(reversed(observations)), "local")
        self.assertEqual(after.units["local"][self.A], timings.UnitTiming(3.0, 5))
        self.assertNotIn("ci", after.units)

        before = timings.Timings(units={"local": {self.A: timings.UnitTiming(10.0, 3),
                                                  self.B: timings.UnitTiming(10.0, 1)}})
        after = timings.update(before, [self.obs(self.A, 1, "t1"), self.obs(self.A, 2, "t2"),
                                        self.obs(self.B, 4.04, "t1")], "local")
        self.assertEqual(after.units["local"][self.A], timings.UnitTiming(10.0, 5))
        self.assertEqual(after.units["local"][self.B], timings.UnitTiming(7.0, 2))

    def test_update_drops_orphans_and_serializes_canonically(self):
        before = timings.Timings(units={"local": {self.A: timings.UnitTiming(1.0, 1),
                                                  self.C: timings.UnitTiming(1.0, 1)},
                                        "ci": {self.C: timings.UnitTiming(1.0, 1)}})
        observations = [self.obs(self.B, 1.26, "t2"), self.obs(self.A, 2.0, "t1"),
                        timings.Observation("local", 0.3141, "pass", "t1", fixture="target")]
        one = timings.update(before, observations, "local", inventory_unit_ids=[self.A, self.B],
                             source="s")
        two = timings.update(before, list(reversed(observations)), "local",
                             inventory_unit_ids=[self.A, self.B], source="s")
        self.assertEqual(one.to_json(), two.to_json())
        self.assertEqual(one.to_json(), canonical_json(json.loads(one.to_json())))
        doc = json.loads(one.to_json())
        self.assertEqual(doc["profiles"]["local"]["units"],
                         {self.A: {"seconds": 1.5, "samples": 2},
                          self.B: {"seconds": 1.3, "samples": 1}})
        self.assertEqual(doc["profiles"]["ci"]["units"], {})
        self.assertEqual(doc["group_overhead_seconds"], {"local": {"target": 0.31}})
        self.assertEqual(timings.parse(doc).to_json(), one.to_json())

    def test_a_corrupt_or_adversarial_file_degrades_to_defaults_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests" / "parallel").mkdir(parents=True)
            path = timings.timings_path(root)
            self.assertTrue(timings.load(root).warnings)          # missing
            # The last one is review O2: nesting too deep for `json` to parse.
            for text in ("{not json", "[]", '{"schema_version": 2, "profiles": {}}',
                         '{"schema_version": 1, "profiles": []}',
                         "[" * 200_000 + "]" * 200_000):
                with self.subTest(text=text[:40]):
                    path.write_text(text)
                    loaded = timings.load(root)
                    self.assertEqual(loaded.units, {})
                    self.assertEqual(len(loaded.warnings), 1)
                    est = timings.estimate_units(loaded, "local", [self.A], [self.A], 30.0)
                    self.assertEqual(est[self.A], timings.Estimate(30.0, timings.DEFAULT))
            path.write_text(json.dumps({"schema_version": 1, "profiles": {"local": {"units": {
                self.A: {"seconds": -1, "samples": 1}, self.B: {"seconds": 1e12, "samples": 1},
                self.C: {"seconds": 2.0, "samples": 9}, self.D: {"seconds": 3.0, "samples": 2},
                self.E: {"seconds": "7", "samples": 1}}, "source": "x"}},
                "group_overhead_seconds": {"local": {"target": -3}},
                "ci_job_setup_seconds": {"shard": float("nan")}}))
            loaded = timings.load(root)
            self.assertEqual(loaded.units, {"local": {self.D: timings.UnitTiming(3.0, 2)}})
            self.assertEqual(len(loaded.warnings), 6)
            self.assertEqual(loaded.group_overhead, {"local": {}})
            self.assertEqual(loaded.ci_job_setup, {})

    def test_observations_from_result_records(self):
        host = {"unit": self.A, "tests_requested": None, "passed": True, "duration": 1.25,
                "started_at": 0.0}
        self.assertEqual(timings.observations_from_record(host, "local"),
                         [timings.Observation("local", 1.25, "pass",
                                              "1970-01-01T00:00:00.000000Z", unit=self.A)])
        self.assertEqual(timings.observations_from_record(
            {**host, "tests_requested": ["test_x"]}, "local"), [])
        frozen = {"chunk_id": "c", "version": "1.0.0", "fixture": "target",
                  "suite": "s_test.py", "classes": ["K1"], "returncode": 0, "timed_out": False,
                  "build_error": None, "duration": 2.5, "started_at": 0.0, "tree_digest": "T",
                  "output": "..\n----\nRan 2 tests in 2.100s\n\nOK\n"}
        got = timings.observations_from_record(frozen, "ci")
        self.assertEqual([(o.unit, o.fixture, o.seconds, o.outcome) for o in got],
                         [(None, "target", 0.4, "pass"),
                          (_frozen("s_test.py", "K1", fixture="target"), None, 2.1, "pass")])
        multi = timings.observations_from_record({**frozen, "classes": ["K1", "K2"],
                                                  "returncode": 1}, "ci")
        self.assertEqual([(o.unit, o.fixture, o.outcome) for o in multi],
                         [(None, "target", "fail")])
        line = got[1].to_json_line()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "h.jsonl").write_text(line + "\n" + got[0].to_json_line())
            self.assertEqual(timings.read_observations([Path(tmp) / "h.jsonl"]), got[::-1])

    def test_a_history_line_keeps_its_own_profile(self):
        """Self-review: `--update-timings --profile ci` over the local history
        cache must fold nothing into `ci`."""
        lines = [self.obs(self.A, 5.0, "t1").to_json_line(),
                 self.obs(self.B, 7.0, "t1", profile="ci").to_json_line()]
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "h.jsonl"
            history.write_text("\n".join(lines) + "\n")
            got = timings.read_observations([history], "ci")
        self.assertEqual({(o.unit, o.profile) for o in got}, {(self.A, "local"), (self.B, "ci")})
        after = timings.update(timings.Timings(), got, "ci")
        self.assertEqual(set(after.units["ci"]), {self.B})

    def test_an_unreadable_history_line_is_skipped_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "h.jsonl"
            history.write_text(self.obs(self.A, 5.0, "t1").to_json_line().rstrip("\n") + "\n"
                               + '{"unit": "host:test_a.py::B", "seco' + "\n"
                               + self.obs(self.C, 6.0, "t2").to_json_line())
            warnings: list[str] = []
            got = timings.read_observations([history], warnings=warnings)
            self.assertEqual([o.unit for o in got], [self.A, self.C])
            self.assertEqual(warnings, [f"{history}:2: unreadable history line skipped"])
            self.assertEqual(len(timings.read_observations([history])), 2)

    def test_a_history_line_with_non_string_fields_is_skipped_with_a_warning(self):
        """Review O3: a line that parses but whose identifying fields are not
        strings is skipped like an unparsable one, never a `TypeError`."""
        bad = [{"unit": ["x"], "seconds": 1}, {"fixture": {"a": 1}, "seconds": 1},
               {"unit": self.B, "seconds": 1, "profile": 3},
               {"unit": self.B, "seconds": 1, "tree_digest": []}]
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "h.jsonl"
            history.write_text(self.obs(self.A, 5.0, "t1").to_json_line()
                               + "".join(json.dumps(obj) + "\n" for obj in bad))
            warnings: list[str] = []
            got = timings.read_observations([history], "local", warnings=warnings)
        self.assertEqual([o.unit for o in got], [self.A])
        self.assertEqual(warnings, [f"{history}:{n}: unreadable history line skipped"
                                    for n in range(2, 6)])
        after = timings.update(timings.Timings(), got, "local")
        self.assertEqual(set(after.units["local"]), {self.A})

    def test_a_ratio_that_is_not_a_valid_duration_falls_through(self):
        """Self-review: an adversarial file could make the profile ratio
        overflow to `inf` (or `inf x 0` give `nan`), and a finite ratio can
        still scale past a valid duration; neither may reach the planner."""
        # Non-finite per-unit ratios are left out of the median.
        timing = _timings(local={self.A: 1.0, self.D: 1.0, self.E: 4.0},
                          ci={self.A: 1e-320, self.D: 1e-320, self.E: 2.0, self.B: 3.0})
        ids = [self.A, self.B, self.D, self.E]
        got = timings.estimate_units(timing, "local", ids, ids, 30.0)
        self.assertEqual(got[self.B], timings.Estimate(6.0, timings.OTHER_PROFILE))
        # A finite ratio whose product is not a valid duration falls through.
        timing = _timings(local={self.A: 86400.0, self.D: 8.0},
                          ci={self.A: 1e-300, self.B: 1.0, self.C: 0.0})
        ids = [self.A, self.B, self.C, self.D]
        got = timings.estimate_units(timing, "local", ids, ids, 30.0)
        self.assertEqual(got[self.B], timings.Estimate(43204.0, timings.GROUP_MEDIAN))
        self.assertEqual(got[self.C], timings.Estimate(0.0, timings.OTHER_PROFILE))
        plan = _plan(ids, timing=timing)
        self.assertEqual(sorted(_all_plan_units(plan)), sorted(ids))

    def test_timing_warnings_do_not_name_the_checkout_path(self):
        """Warnings enter the plan: two checkouts of one tree plan identically
        (INV-3), with or without a timing file."""
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            loaded = [timings.load(Path(root)) for root in (one, two)]
            self.assertEqual(loaded[0].warnings, loaded[1].warnings)
            self.assertTrue(loaded[0].warnings[0].startswith("tests/parallel/timings.json: "))
            for root in (one, two):
                (Path(root) / "tests" / "parallel").mkdir(parents=True)
                timings.timings_path(Path(root)).write_text("{not json")
            loaded = [timings.load(Path(root)) for root in (one, two)]
            self.assertEqual(loaded[0].warnings, loaded[1].warnings)
            self.assertNotIn(one, loaded[0].warnings[0])

    def test_the_committed_files_load_cleanly(self):
        loaded = timings.load(REPO_ROOT)
        self.assertEqual(loaded.warnings, ())
        self.assertTrue(loaded.units["local"])
        self.assertEqual(set(loaded.group_overhead["local"]), set(matrix.FIXTURES))
        # Canonical on disk: a refresh rewrites it byte-for-byte reviewably.
        self.assertEqual(timings.timings_path(REPO_ROOT).read_text(), loaded.to_json())
        self.assertEqual(set(planner.load_config(REPO_ROOT)), set(planner.CONFIG_KEYS))


class TestConfig(unittest.TestCase):

    def test_bad_configs_are_refused(self):
        good = {"schema_version": 1, **PLAN_CONFIG}
        self.assertEqual(planner.parse_config(good), PLAN_CONFIG)
        for key, value in (("min_shards", 0), ("min_shards", 1.5), ("min_shards", True),
                           ("target_shard_seconds", -1), ("split_threshold_ratio", float("inf")),
                           ("ci_account_concurrent_job_limit", 1), ("schema_version", 2)):
            with self.subTest(key=key, value=value), self.assertRaises(planner.ConfigError):
                planner.parse_config({**good, key: value})
        with self.assertRaises(planner.ConfigError):
            planner.parse_config({k: v for k, v in good.items() if k != "min_shards"})
        self.assertEqual(planner.parse_config({**good, "default_group_overhead_seconds": 0})[
            "default_group_overhead_seconds"], 0.0)


class TestPlanProvenance(unittest.TestCase):
    """T-PLN-8, function level."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        (base / "repo").mkdir()
        self.repo = _git_repo(base / "repo")
        (self.repo / "f").write_text("f\n")
        _commit_all(self.repo)
        self.out = base / "out"
        self.out.mkdir()
        units = [_host("test_a.py", c) for c in "ABC"]
        self.plan = planner.build_plan(
            _selection(units), inventory_unit_ids=units, matrix_units=(),
            timings=_timings(local={u: 9.0 for u in units}), config=dict(PLAN_CONFIG),
            profile="local", tree_digest=tree.tree_digest(self.repo), resources=NO_RESOURCES,
            cpu_count=4)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, plan):
        return planner.write_plan(plan, self.out / "plan.json")

    def test_a_matching_plan_loads(self):
        self.assertEqual(planner.load_plan(self.write(self.plan), self.repo), self.plan)

    def test_a_plan_whose_content_does_not_match_its_digest_is_refused(self):
        tampered = json.loads(planner.to_json(self.plan))
        tampered["shards"][0]["chunks"][0]["estimate"] = 0.0
        with self.assertRaises(planner.PlanDigestMismatchError):
            planner.load_plan(self.write(tampered), self.repo)

    def test_a_plan_for_another_tree_is_refused(self):
        other = dict(self.plan, tree_digest="0" * 64)
        other["plan_digest"] = planner.plan_digest(other)
        with self.assertRaises(planner.TreeDigestMismatchError):
            planner.load_plan(self.write(other), self.repo)
        path = self.write(self.plan)
        (self.repo / "untracked").write_text("x\n")
        with self.assertRaises(planner.TreeDigestMismatchError):
            planner.load_plan(path, self.repo)

    def test_a_consistently_digested_plan_that_breaks_inv1_is_refused(self):
        broken = json.loads(planner.to_json(self.plan))
        broken["selection"]["host:test_a.py::Z"] = None
        broken["plan_digest"] = planner.plan_digest(broken)
        with self.assertRaises(planner.PartitionError):
            planner.load_plan(self.write(broken), self.repo)


class TestExclusivePlacement(unittest.TestCase):
    """T-PLN-9 (5.4 step 4, planner level)."""

    EXCL = _host("test_x.py", "Exclusive")
    SHARED = [_host("test_a.py", f"S{i}") for i in range(6)]

    def load_resources(self, root: Path, exclusive=True):
        (root / "tests" / "parallel").mkdir(parents=True)
        doc = {"schema_version": 1,
               "resources": {"repo:tools": {"paths": ["tools/"], "description": "the tree"}},
               "exclusive": {self.EXCL: {"resources": ["repo:tools"],
                                         "reason": "rewrites tools/"}} if exclusive
               else {}}
        resources.resources_path(root).write_text(json.dumps(doc))
        return resources.load(root, [self.EXCL, *self.SHARED])

    def test_a_matrix_host_class_declared_exclusive_is_refused(self):
        """Self-review: phase B has no A0 and never lifts the barrier, so an
        exclusive matrix class would run concurrently -- refuse it."""
        with tempfile.TemporaryDirectory() as tmp:
            res = self.load_resources(Path(tmp))
            with self.assertRaises(planner.ExclusiveMatrixUnitError) as ctx:
                _plan([self.EXCL, *self.SHARED], matrix=(self.EXCL,), res=res)
            self.assertIn(self.EXCL, str(ctx.exception))
            _plan([self.EXCL, *self.SHARED], matrix=(self.SHARED[0],), res=res)

    def test_the_exclusive_chunk_is_first_in_its_shard_whatever_the_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self.load_resources(Path(tmp))
            units = [self.EXCL, *self.SHARED]
            shards_seen = set()
            for shared in ([90, 80, 70, 60, 50, 40], [10, 20, 30, 40, 50, 60],
                           [5, 100, 5, 100, 5, 100], [100, 1, 1, 1, 1, 1]):
                estimates = {u: float(s) for u, s in zip(self.SHARED, shared)}
                estimates[self.EXCL] = 0.5
                with self.subTest(shared=shared):
                    plan = _plan(units, estimates, res=res, shards=3)
                    again = _plan(units, estimates, res=res, shards=3)
                    self.assertEqual(planner.to_json(plan), planner.to_json(again))
                    path = planner.write_plan(plan, Path(tmp) / "plan.json")
                    parsed = plan_schema.shard_chunks(json.loads(path.read_text()))
                    self.assertEqual(parsed, plan_schema.shard_chunks(plan))
                    holders = [i for i, s in enumerate(parsed)
                               if any(self.EXCL in c.units for c in s)]
                    self.assertEqual(len(holders), 1)
                    shard = parsed[holders[0]]
                    self.assertEqual(shard[0].units, (self.EXCL,))
                    self.assertEqual(shard[0].resources, ("repo:tools",))
                    self.assertTrue(len(shard) > 1)
                    self.assertTrue(all(not c.resources for s in parsed for c in s
                                        if self.EXCL not in c.units))
                    shards_seen.add(holders[0])
            self.assertGreater(len(shards_seen), 1, "the exclusive chunk's shard never varied")

    def test_without_an_exclusive_unit_the_order_is_plain_lpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self.load_resources(Path(tmp), exclusive=False)
            units = [self.EXCL, *self.SHARED]
            estimates = {u: float(s) for u, s in zip(units, [0.5, 90, 80, 70, 60, 50, 40])}
            plan = _plan(units, estimates, res=res, shards=3)
            expected = [[i for _, i, _ in b] for b in
                        planner.lpt([(e, u, u) for u, e in estimates.items()], 3)]
            self.assertEqual([[c.id for c in s] for s in plan_schema.shard_chunks(plan)],
                             expected)
            self.assertTrue(all(not c.resources for c in _chunks(plan)))


class TestTheRealCheckoutPlans(unittest.TestCase):
    """The committed config, timings and resources plan the real full
    selection: every unit exactly once, within the bounds."""

    def test_the_full_selection_plans_locally_and_in_ci(self):
        inv = inventory.discover(REPO_ROOT)
        selection = inventory.select(inv.host, [], inv.frozen)
        for profile in timings.PROFILES:
            with self.subTest(profile=profile):
                plan = planner.plan_checkout(REPO_ROOT, inv, selection, profile=profile,
                                             cpu_count=8)
                units = _all_plan_units(plan)
                self.assertEqual(sorted(units), selection.unit_ids())
                self.assertEqual(len(units), len(set(units)))
                self.assertLessEqual(plan["n"], planner.max_shards(plan["bounds"], profile, 8))
                self.assertEqual(plan["tree_digest"], inv.tree_digest)


# -- T-INV-6: the selection never depends on timing -------------------------------------

class TestSelectionIgnoresTiming(unittest.TestCase):
    """T-INV-6 (INV-2): discovery and selection over a checkout are
    byte-identical whatever its `timings.json` holds."""

    HOST_MODULE = textwrap.dedent('''
        import unittest

        class TestTiny(unittest.TestCase):
            def test_host(self):
                pass

        class TestOther(unittest.TestCase):
            def test_a(self):
                pass

            def test_b(self):
                pass
    ''')

    def layout(self, tmp: Path) -> Path:
        root = TestFrozenInventoryCountRefusal.layout(tmp, pinned=3)
        (root / "tests" / "test_tiny.py").write_text(self.HOST_MODULE)
        _git_repo(root)
        _commit_all(root)
        return root

    def variants(self, real_units):
        adversarial = {u: {"seconds": s, "samples": 1}
                       for u, s in zip(real_units, (0, -5, float("nan"), 1e12))}
        return {
            "none": None,
            "empty": "",
            "corrupt": "{\"schema_version\": 1, \"profiles\": {",
            "schema": json.dumps({"schema_version": 7, "profiles": {}}),
            "orphans": _timings(local={"host:test_gone.py::Gone": 5.0}).to_json(),
            "adversarial": json.dumps({"schema_version": 1, "profiles": {
                "local": {"units": adversarial, "source": "x"}}}),
            "real": timings.timings_path(REPO_ROOT).read_text(),
        }

    def test_selections_are_byte_identical_under_every_timing_file(self):
        with tempfile.TemporaryDirectory() as tmp, TestFrozenInventoryCountRefusal.env(Path(tmp)):
            root = self.layout(Path(tmp))
            first = inventory.discover(root)
            path = timings.timings_path(root)
            specs = ([], ["test_tiny.py::TestTiny"], ["test_tiny.py::TestOther::test_b"],
                     ["frozen:0.0.1/conformance/tiny_test.py::TestBeta"])
            outputs = {}
            for name, text in self.variants(first.unit_ids()).items():
                if text is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(text)
                inv = inventory.discover(root)
                outputs[name] = [canonical_json(inv.unit_ids())] + [
                    inventory.select(inv.host, spec, inv.frozen).to_json() for spec in specs]
                loaded = timings.load(root)
                plan = planner.build_plan(
                    inventory.select(inv.host, [], inv.frozen),
                    inventory_unit_ids=inv.unit_ids(), matrix_units=inv.frozen.matrix,
                    timings=loaded, config=dict(PLAN_CONFIG), profile="local",
                    tree_digest=inv.tree_digest, resources=NO_RESOURCES, cpu_count=4)
                self.assertEqual(sorted(_all_plan_units(plan)), sorted(inv.unit_ids()), name)
            self.assertEqual(len({json.dumps(v) for v in outputs.values()}), 1, outputs)


# == CP4: isolation and the repository-integrity guard ================================

# -- the scratch checkout (plan 5.9, "Tests and the lock") ----------------------------

SCRATCH_EXCLUSIVE_UNIT = "host:test_scratch_exclusive.py::TestScratchExclusiveWriter"
SCRATCH_SHARED_UNIT = "host:test_scratch_shared.py::TestScratchReader"
#: A small tree under the scratch's `tools/` -- a guarded tree that outlives
#: CP6 -- which the exclusive writer removes and rebuilds and the shared reader
#: reads.
SCRATCH_TOOLS = "tools/scratch/lib/bin"
SCRATCH_TOOL = "tools/scratch/lib/bin/tiny_tool.py"

SCRATCH_EXCLUSIVE_MODULE = '''
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestScratchExclusiveWriter(unittest.TestCase):
    """Removes and rebuilds a directory of the scratch `tools/` tree -- the
    shape of a test that rewrites a guarded tree in place."""

    def test_rmtree_and_restore(self):
        target = ROOT / "tools" / "scratch"
        backup = Path(tempfile.mkdtemp()) / "scratch"
        shutil.copytree(target, backup)
        shutil.rmtree(target)
        shutil.copytree(backup, target)
'''

SCRATCH_SHARED_MODULE = '''
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestScratchReader(unittest.TestCase):
    def test_reads_the_tool(self):
        path = ROOT / "tools" / "scratch" / "lib" / "bin" / "tiny_tool.py"
        self.assertIn("scratch tool", path.read_text())
'''

SCRATCH_RESOURCES = {
    "schema_version": 1,
    "resources": {
        "repo:tools": {
            "paths": ["tools/"],
            "description": "the scratch checkout's tools/ tree",
        },
    },
    "exclusive": {
        SCRATCH_EXCLUSIVE_UNIT: {
            "resources": ["repo:tools"],
            "reason": "rmtree()s and rebuilds tools/scratch",
        },
    },
}


def _same_checkout_as_real(root: Path) -> bool:
    real = REPO_ROOT.resolve()
    resolved = root.resolve()
    return resolved == real or real in resolved.parents


#: The scratch release's frozen suite: three classes, so a split group can hold
#: a multi-class chunk.
SCRATCH_SUITE = '''
import unittest


class TestAlpha(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)

    def test_two(self):
        self.assertTrue(True)


class TestBeta(unittest.TestCase):
    def test_three(self):
        self.assertTrue(True)


class TestGamma(unittest.TestCase):
    def test_four(self):
        self.assertTrue(FOUR)


FOUR = True

if __name__ == "__main__":
    unittest.main()
'''
SCRATCH_SUITE_TESTS = 4
SCRATCH_MATRIX_UNIT = "host:test_scratch_matrix.py::TestScratchMatrix"
SCRATCH_FROZEN_SUITE = "frozen:0.0.1/conformance/tiny_test.py"

#: Variants of the scratch suite for the executor-level verdicts of T-MRG-3/-4
#: (T-EXE-1): a failing test, a class whose `setUpClass` errors, and a suite
#: that crashes on import -- only inside a fixture repository (one with a
#: `.git`), so discovery, which imports the payload copy, still sees it whole.
SCRATCH_SUITE_VARIANTS = {
    "failing": SCRATCH_SUITE.replace("FOUR = True", "FOUR = False"),
    "setupclass_error": SCRATCH_SUITE.replace(
        "class TestBeta(unittest.TestCase):\n",
        "class TestBeta(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n"
        "        raise RuntimeError(\"setUpClass boom\")\n\n"),
    "import_crash": "import pathlib\n" + SCRATCH_SUITE.replace(
        "import unittest\n",
        "import unittest\nif (pathlib.Path(__file__).resolve().parents[1] / \".git\").exists():\n"
        "    raise RuntimeError(\"import boom\")\n", 1),
}

SCRATCH_MATRIX_PY = '''"""The scratch checkout's matrix: one matrix host class over one synthetic
release, with a literal CI_SUITES -- never a view of `support`'s."""

FIXTURES = ("conformance", "target", "bootstrapped")
FROZEN_MATRIX = {
    "host:test_scratch_matrix.py::TestScratchMatrix": ("0.0.1", "conformance"),
}
CI_SUITES = {"0.0.1": {"tiny_test.py": PINNED}}
'''

SCRATCH_MATRIX_MODULE = '''
import unittest

from frozen_runs import open_matrix_run
from parallel.matrix import CI_SUITES


class TestScratchMatrix(unittest.TestCase):
    """The shape of the four real matrix host classes, over the scratch release:
    direct/merged `setUpClass` through `open_matrix_run`, unchanged assertions
    over the per-suite view."""

    @classmethod
    def setUpClass(cls):
        cls.run_ = open_matrix_run("0.0.1", "conformance")

    @classmethod
    def tearDownClass(cls):
        cls.run_.cleanup()

    def test_every_frozen_suite_passes(self):
        failed = {s: r.output for s, r in self.run_.results.items() if r.returncode != 0}
        self.assertEqual(sorted(failed), [], "\\n".join(failed.values())[-4000:])

    def test_every_suite_runs_the_frozen_number_of_tests(self):
        self.assertEqual({s: r.ran for s, r in self.run_.results.items()}, CI_SUITES["0.0.1"])

    def test_the_fixture_state_file_is_the_clean_template(self):
        self.assertTrue((self.run_.root / "docs/ai-workflow/WORKFLOW_STATE.json").is_file())
'''

#: The scratch checkout's own planner configuration -- never the real
#: `tests/parallel/config.json`, which CP7 tunes, so a scratch test's chunking
#: does not move with it.
SCRATCH_CONFIG = {
    "ci_account_concurrent_job_limit": 20, "ci_max_shards": 16,
    "default_group_overhead_seconds": 0.5, "default_unit_seconds": 30, "local_max_shards": 8,
    "min_shards": 2, "schema_version": 1, "split_threshold_ratio": 0.5,
    "target_shard_seconds": 240,
}

#: Templates the fixture builders place (`build_conformance_repo`,
#: `build_target_repo`).
SCRATCH_TEMPLATES = {
    ".gitignore.workflow-fragment": "__pycache__/\n",
    "docs/ai-workflow/WORKFLOW_STATE.json": '{"work_items": {}}\n',
    "docs/ai-workflow/WORKFLOW_CONFIG.json": "{}\n",
    "docs/ACTIVE_MILESTONE.md": "# Active Milestone\n",
}


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _scratch_manifest(files: dict[str, bytes], templates: dict[str, bytes],
                      version: str = "0.0.1") -> dict:
    """A `version` manifest over `files` (payload) and `templates`, every
    digest matching by construction."""
    return {
        "schema_version": 1, "workflow_version": version,
        "upstream": {"repository": "scratch", "tag": "scratch", "commit": "0" * 40},
        "artifacts": [{"target_path": rel[len("payload/"):], "location": rel,
                       "sha256": _sha256(data), "size": len(data),
                       "executable": False, "category": "conformance"}
                      for rel, data in files.items()],
        "templates": [{"target_path": t, "location": f"templates/{t}",
                       "sha256": _sha256(body), "size": len(body)}
                      for t, body in templates.items()],
    }


def synthetic_release_env(releases: Path) -> dict[str, str]:
    """`WORKFLOW_MANAGER_RELEASE_SOURCE`/`_CACHE` for a synthetic release
    published under `releases` by `publish_synthetic_release`: its `file://`
    source and its private cache. These override the real cache the runner
    exports, which is the only thing keeping a synthetic run off it (7.1)."""
    return {release_source.SOURCE_ENV: (releases / "source").as_uri() + "/{version}/",
            release_source.CACHE_ENV: str(releases / "cache")}


def publish_synthetic_release(checkout: Path, releases: Path, suite: str, *,
                              templates=None, version: str = "0.0.1") -> None:
    """Package a synthetic release `version` whose payload is `suite` (as
    `scripts/tiny_test.py`) and whose templates are `templates` (default
    `SCRATCH_TEMPLATES`), serve it from `releases/source/`, and pin it in
    `checkout`'s copy of `src/workflow_manager/`: the one pin for `0.0.1`,
    an added one for any other version. Everything lives outside `checkout`,
    so a run's tree digest never sees it."""
    templates = SCRATCH_TEMPLATES if templates is None else templates
    files = {"payload/scripts/tiny_test.py": suite.encode()}
    bodies = {t: body.encode() for t, body in templates.items()}
    tree = releases / "trees" / version
    for rel, data in [*files.items(), *((f"templates/{t}", b) for t, b in bodies.items())]:
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_bytes(data)
    (tree / "manifest.json").write_text(canonical_json(_scratch_manifest(files, bodies, version)))
    built = package_module.build_package(tree, releases / "source" / version)
    pin_file = checkout / "src" / "workflow_manager" / "published_releases.json"
    pins = ({"schema_version": 1, "repository": "scratch/workflow", "releases": {}}
            if version == "0.0.1" else json.loads(pin_file.read_text()))
    pins["releases"][version] = {
        "archive": built.archive.name, "sha256": package_module.file_sha256(built.archive),
        "manifest_sha256": package_module.file_sha256(built.manifest)}
    pin_file.write_text(canonical_json(pins))


def scratch_releases(scratch_root: Path) -> Path:
    """Where `scratch_checkout` published a scratch's release: a sibling of
    the scratch, shared by its linked worktrees and clones (`-wtN`,
    `-cloneN`), which carry the same pin."""
    root = Path(scratch_root)
    name = root.name
    while True:
        stripped = re.sub(r"-(wt|clone)\d+$", "", name)
        if stripped == name:
            break
        name = stripped
    return root.parent / f"{name}.releases"


def scratch_release_env(scratch_root: Path) -> dict[str, str]:
    """The release source and private cache every run in `scratch_root` uses
    (7.2.1): it primes and tests only its own `0.0.1`, and never reads or
    writes the real cache."""
    return synthetic_release_env(scratch_releases(scratch_root))


def _writable_copy(src: Path, dst: Path, **kwargs) -> None:
    """`copytree`, then `u+rwx` on every copied directory: a copy made while
    the real checkout's barrier is applied arrives `u-w` (5.9)."""
    shutil.copytree(src, dst, **kwargs)
    isolation._make_removable(dst)  # noqa: SLF001


def scratch_checkout(root: Path, *, resources=SCRATCH_RESOURCES, modules=None,
                     suite: str = SCRATCH_SUITE, pinned: int = SCRATCH_SUITE_TESTS,
                     timings_units=None, no_gitignore_template: bool = False) -> Path:
    """A throwaway git checkout at `root` with its own git dir (hence its own
    run lock and marker), complete enough for `run_all.py` to run for real:

    - verbatim copies of `tests/run_all.py`, `tests/frozen_runs.py`,
      `tests/support.py`, `tests/parallel/` and `src/workflow_manager/`;
    - `tests/parallel/matrix.py` replaced by a literal naming only the
      synthetic matrix host class, `resources.json` by `resources`,
      `config.json` by `SCRATCH_CONFIG`, and
      `timings.json` by one holding only `timings_units` (local profile);
    - a synthetic release `0.0.1` whose payload is `suite`, pinned at
      `pinned` tests: a package served and cached beside the scratch
      (`scratch_releases`) and the one pin of the scratch's
      `published_releases.json` (`no_gitignore_template` leaves the
      `.gitignore` fragment out of a manifest that still verifies, so the
      conformance fixture builder raises);
    - `tests/portability_exceptions.json` in the shape `support` reads, a small `tools/` tree, and synthetic host
      modules: the declared exclusive writer, a shared reader, the matrix
      host class, and `modules` (`{file name: source}`).

    Refuses the real checkout, anything inside it, and any root sharing its
    git dir; refuses a `resources` declaration its own host inventory
    fails."""
    root = Path(root)
    if _same_checkout_as_real(root):
        raise ValueError(f"scratch_checkout refuses the real checkout: {root}")
    root.mkdir(parents=True)
    _git_repo(root)
    if isolation.git_dir(root) == isolation.git_dir(REPO_ROOT):
        raise ValueError(f"scratch_checkout refuses a root sharing the real git dir: {root}")
    tests = root / "tests"
    _writable_copy(TESTS_DIR / "parallel", tests / "parallel",
                   ignore=shutil.ignore_patterns("__pycache__", "matrix.py", "resources.json",
                                                 "timings.json", "config.json"))
    for name in ("run_all.py", "frozen_runs.py", "support.py"):
        shutil.copy2(TESTS_DIR / name, tests / name)
    _writable_copy(REPO_ROOT / "src" / "workflow_manager", root / "src" / "workflow_manager",
                   ignore=shutil.ignore_patterns("__pycache__"))
    (tests / "parallel" / "resources.json").write_text(canonical_json(resources))
    (tests / "parallel" / "config.json").write_text(canonical_json(SCRATCH_CONFIG))
    (tests / "parallel" / "matrix.py").write_text(SCRATCH_MATRIX_PY.replace("PINNED", str(pinned)))
    (tests / "parallel" / "timings.json").write_text(timings.Timings(
        units={"local": {u: timings.UnitTiming(s, 1) for u, s in (timings_units or {}).items()}},
        sources={"local": "scratch"}).to_json())
    (tests / "test_scratch_exclusive.py").write_text(SCRATCH_EXCLUSIVE_MODULE)
    (tests / "test_scratch_shared.py").write_text(SCRATCH_SHARED_MODULE)
    (tests / "test_scratch_matrix.py").write_text(SCRATCH_MATRIX_MODULE)
    for name, source in (modules or {}).items():
        (tests / name).write_text(textwrap.dedent(source))
    templates = {t: body for t, body in SCRATCH_TEMPLATES.items()
                 if not (no_gitignore_template and t == ".gitignore.workflow-fragment")}
    publish_synthetic_release(root, scratch_releases(root), suite, templates=templates)
    (tests / "portability_exceptions.json").write_text(canonical_json(
        {"by_version": {"0.0.1": {"exceptions": []}}}))
    (root / "src" / "scratchpkg").mkdir(parents=True)
    (root / "src" / "scratchpkg" / "__init__.py").write_text("")
    (root / "tools").mkdir()
    (root / "tools" / ".keep").write_text("")
    (root / SCRATCH_TOOLS).mkdir(parents=True)
    (root / SCRATCH_TOOL).write_text("# the scratch tool\n")
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n*.ignored\n")
    _commit_all(root, "scratch")
    # Valid by construction: loads against the scratch's own host inventory.
    resources_module_load(root)
    return root


def resources_module_load(root: Path) -> resources.Resources:
    # Frozen discovery only when there is an `orphan_sources` key to check
    # against it: some scratch releases are miscounted on purpose.
    declared = json.loads(resources.resources_path(root).read_text()).get("orphan_sources")
    with mock.patch.dict(os.environ, scratch_release_env(root)):
        every = inventory.discover(root).unit_ids() if declared else None
    return resources.load(root, inventory.discover_host(root), orphan_unit_ids=every)


def scratch_worktree(scratch: Path) -> Path:
    """A linked worktree of `scratch`, as a sibling inside the same temporary
    directory -- its own per-worktree git dir, hence its own lock and marker."""
    index = 0
    while (scratch.parent / f"{scratch.name}-wt{index}").exists():
        index += 1
    path = scratch.parent / f"{scratch.name}-wt{index}"
    _git(scratch, "worktree", "add", "-q", "-b", f"wt{index}", str(path))
    return path


def scratch_clone(scratch: Path) -> Path:
    """A fresh `git clone` of `scratch`, as a sibling inside the same temporary
    directory -- what a CI job's checkout is: the same commit, its own git dir,
    no untracked or ignored file (plan 5.10)."""
    if _same_checkout_as_real(scratch):
        raise ValueError(f"scratch_clone refuses the real checkout: {scratch}")
    index = 0
    while (scratch.parent / f"{scratch.name}-clone{index}").exists():
        index += 1
    path = scratch.parent / f"{scratch.name}-clone{index}"
    subprocess.run(["git", "clone", "-q", str(scratch), str(path)], check=True,
                   capture_output=True)
    configure_throwaway_repo(path)
    return path


def _guarded_modes(root: Path) -> dict[str, int]:
    """`{relative dir: mode}` for every directory under the guarded trees."""
    modes = {}
    for guarded in resources.GUARDED_TREES:
        for dirpath, _, _ in os.walk(root / guarded):
            modes[os.path.relpath(dirpath, root)] = stat.S_IMODE(os.lstat(dirpath).st_mode)
    return modes


def _writable(mode: int) -> bool:
    return bool(mode & stat.S_IWUSR)


def _dead(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] == "Z"
    except (FileNotFoundError, ProcessLookupError):
        # Gone before the open, or reaped between the open and the read (ESRCH).
        return True


def _wait_until(predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _script_argv(code: str, *args) -> list[str]:
    return [sys.executable, "-B", "-c", textwrap.dedent(code), *map(str, args)]


#: A chunk process that waits for `argv[1]` to exist -- the lock fd it was
#: handed stays open until then.
_WAIT_FOR_FILE = """
import os, sys, time
while not os.path.exists(sys.argv[1]):
    time.sleep(0.05)
"""


# -- helper processes (module-level, started with the "spawn" context; 5.9) -------

def _hold_lock_and_barrier(scratch_root, ready_path, stop_path):
    """Take the scratch checkout's run lock, apply the barrier, report ready,
    and hold both until `stop_path` exists; then restore and release."""
    lock = isolation.acquire_run_lock(scratch_root)
    isolation.recover_barrier(scratch_root, lock)
    barrier = isolation.apply_barrier(scratch_root, lock)
    Path(ready_path).write_text(json.dumps({"pid": os.getpid()}))
    while not os.path.exists(stop_path):
        time.sleep(0.05)
    isolation.restore_barrier(scratch_root, barrier)
    lock.release()


def _hold_lock_with_child_then_hang(scratch_root, ready_path, stop_path):
    """Take the lock, apply the barrier, hand the lock fd to a chunk-like child
    (which lives until `stop_path` exists), report ready, and hang until
    killed -- a SIGKILLed executor with a chunk still running."""
    lock = isolation.acquire_run_lock(scratch_root)
    isolation.recover_barrier(scratch_root, lock)
    isolation.apply_barrier(scratch_root, lock)
    child = subprocess.Popen(_script_argv(_WAIT_FOR_FILE, stop_path), start_new_session=True,
                             pass_fds=(lock.fd,))
    lock.add_chunk_pgid(child.pid)
    Path(ready_path).write_text(json.dumps({"pid": os.getpid(), "child": child.pid}))
    while True:
        time.sleep(60)


def tearDownModule():
    """The spawn context's helpers start `multiprocessing`'s resource tracker,
    which would otherwise exit only after this module's chunk has, orphaned
    (test-cleanup plan 5.4's policy: wait for what the test started)."""
    from multiprocessing import resource_tracker
    resource_tracker._resource_tracker._stop()  # noqa: SLF001


class _ScratchCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.run_dir = self.tmp / "run"
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        # A failed test may leave a barrier behind; never leave u-w residue.
        for dirpath, dirnames, _ in os.walk(self.tmp):
            for name in dirnames:
                path = os.path.join(dirpath, name)
                if not os.path.islink(path):
                    os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IRWXU)
        self._tmp.cleanup()

    def wait_ready(self, path: Path, process) -> dict:
        self.assertTrue(_wait_until(lambda: path.exists() or not process.is_alive()),
                        "helper process never reported ready")
        self.assertTrue(path.exists(), f"helper process exited with {process.exitcode}")
        return json.loads(path.read_text())


class TestScratchCheckout(_ScratchCase):

    def test_it_carries_its_own_planner_config_never_the_real_one(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        self.assertEqual(json.loads((scratch / "tests" / "parallel" / "config.json").read_text()),
                         SCRATCH_CONFIG)
        self.assertEqual(planner.load_config(scratch)["target_shard_seconds"],
                         SCRATCH_CONFIG["target_shard_seconds"])

    def test_the_real_checkout_is_refused(self):
        for root in (REPO_ROOT, REPO_ROOT / "tests" / "scratch-here"):
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    scratch_checkout(root)
        self.assertFalse((REPO_ROOT / "tests" / "scratch-here").exists())

    def test_it_has_its_own_git_dir(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        self.assertNotEqual(isolation.git_dir(scratch), isolation.git_dir(REPO_ROOT))
        self.assertEqual(_git(scratch, "status", "--porcelain"), "")


# -- T-ISO-1 / -2 / -3: one chunk, its process group, its outcome, its TMPDIR -------

class TestRunChunk(_ScratchCase):

    def run_script(self, chunk_id, code, *args, timeout=60, extra_env=None, git_template=None):
        record = isolation.chunk_paths(self.run_dir, chunk_id).record
        return isolation.run_chunk(self.tmp, chunk_id, _script_argv(code, record, *args),
                                   run_dir=self.run_dir, timeout=timeout, extra_env=extra_env,
                                   git_template=git_template)

    def test_a_timeout_kills_the_whole_process_group(self):
        pid_file = self.tmp / "grandchild.pid"
        started = time.monotonic()
        run = self.run_script("sleeper", """
            import subprocess, sys, time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            open(sys.argv[2], "w").write(str(child.pid))
            time.sleep(120)
        """, pid_file, timeout=1.5)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(run.outcome, isolation.TIMED_OUT)
        self.assertIsNotNone(run.infrastructure_fault)
        self.assertIsNone(run.record)
        grandchild = int(pid_file.read_text())
        self.assertTrue(_wait_until(lambda: _dead(grandchild)), "grandchild survived its chunk")
        self.assertTrue(_dead(run.pgid))

    def test_an_interrupt_right_after_the_spawn_still_kills_the_chunk_group(self):
        """Review O6: an interrupt landing after `Popen` returns but before the
        chunk's cleanup is armed -- here, while its log is being closed --
        must not leave the chunk running."""
        spawned: list[subprocess.Popen] = []
        real_popen, real_open = subprocess.Popen, open

        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            spawned.append(proc)
            self.addCleanup(proc.wait)
            self.addCleanup(isolation._kill_group, proc.pid)
            return proc

        class InterruptOnFirstClose:
            def __init__(self, handle):
                self.handle, self.fired = handle, False

            def fileno(self):
                return self.handle.fileno()

            def close(self):
                self.handle.close()
                if not self.fired:
                    self.fired = True
                    raise KeyboardInterrupt

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.close()

        def log_open(path, mode="r", *args, **kwargs):
            handle = real_open(path, mode, *args, **kwargs)
            return InterruptOnFirstClose(handle) if mode == "wb" else handle

        with mock.patch.object(subprocess, "Popen", popen), \
                mock.patch.object(isolation, "open", log_open, create=True), \
                self.assertRaises(KeyboardInterrupt):
            self.run_script("interrupted", "import time; time.sleep(120)")
        self.assertEqual(len(spawned), 1)
        self.assertTrue(_wait_until(lambda: _dead(spawned[0].pid)),
                        "the chunk outlived the interrupt")

    def test_a_normal_exit_leaves_no_descendant_behind(self):
        pid_file = self.tmp / "grandchild.pid"
        started = time.monotonic()
        run = self.run_script("leaver", """
            import json, subprocess, sys
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            open(sys.argv[2], "w").write(str(child.pid))
            open(sys.argv[1], "w").write(json.dumps({"passed": True}))
        """, pid_file)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(run.outcome, isolation.PASSED)
        self.assertIsNone(run.infrastructure_fault)
        grandchild = int(pid_file.read_text())
        self.assertTrue(_wait_until(lambda: _dead(grandchild)), "grandchild outlived its chunk")

    def test_a_runner_that_dies_without_a_record_is_an_infrastructure_fault(self):
        run = self.run_script("crasher", "import os; os._exit(0)")
        self.assertEqual(run.outcome, isolation.MISSING_RECORD)
        self.assertEqual(run.returncode, 0)
        self.assertIn("no result record", run.infrastructure_fault)

    def test_a_record_that_disagrees_with_the_exit_code_is_an_infrastructure_fault(self):
        cases = (("passed-but-1", True, 1), ("failed-but-0", False, 0), ("exit-3", False, 3))
        for chunk_id, passed, code in cases:
            with self.subTest(chunk=chunk_id):
                run = self.run_script(chunk_id, f"""
                    import json, sys
                    open(sys.argv[1], "w").write(json.dumps({{"passed": {passed}}}))
                    sys.exit({code})
                """)
                self.assertEqual(run.outcome, isolation.RECORD_MISMATCH)
                self.assertIsNotNone(run.infrastructure_fault)
        run = self.run_script("garbled", "import sys; open(sys.argv[1], 'w').write('{')")
        self.assertEqual(run.outcome, isolation.BAD_RECORD)

    def test_a_failing_chunk_is_a_verdict_not_a_fault(self):
        run = self.run_script("failing", """
            import json, sys
            open(sys.argv[1], "w").write(json.dumps({"passed": False}))
            sys.exit(1)
        """)
        self.assertEqual(run.outcome, isolation.FAILED)
        self.assertIsNone(run.infrastructure_fault)

    def test_orphaned_tmpdir_files_are_reported_against_the_chunk_and_removed(self):
        run = self.run_script("litterer", """
            import json, os, sys
            tmp = os.environ["TMPDIR"]
            os.makedirs(os.path.join(tmp, "sub"))
            open(os.path.join(tmp, "a.txt"), "w").write("x")
            open(os.path.join(tmp, "sub", "b.txt"), "w").write("y")
            open(sys.argv[1], "w").write(json.dumps({"passed": True}))
        """)
        self.assertEqual(run.outcome, isolation.PASSED)
        self.assertEqual(run.tmp_residue, ("a.txt", "sub", "sub/b.txt"))
        self.assertFalse(isolation.chunk_paths(self.run_dir, "litterer").tmp.exists())

    def test_the_chunk_environment_and_session(self):
        template = self.tmp / "git-template"
        for git_template in (None, template):
            with self.subTest(git_template=git_template), \
                    mock.patch.dict(os.environ, {"PYTHONPATH": "/nowhere", "FORCE_COLOR": "1",
                                                 "GIT_TEMPLATE_DIR": "/elsewhere"}):
                run = self.run_script("env", """
                    import json, os, sys
                    env = {k: os.environ.get(k) for k in
                           ("PYTHONPATH", "FORCE_COLOR", "PYTHONDONTWRITEBYTECODE",
                            "PYTHON_COLORS", "TMPDIR", "WM_EXTRA", "GIT_TEMPLATE_DIR")}
                    # The leak check's wrapper leads the session and group
                    # and is the chunk's parent (test-cleanup plan 5.4).
                    env["own_session"] = os.getsid(0) == os.getpgid(0) == os.getppid()
                    last = {}
                    for i in range(int(os.environ.get("GIT_CONFIG_COUNT", "0"))):
                        last[os.environ[f"GIT_CONFIG_KEY_{i}"].lower()] = \
                            os.environ[f"GIT_CONFIG_VALUE_{i}"]
                    env["git_config"] = last
                    open(sys.argv[1], "w").write(json.dumps({"passed": True, "env": env}))
                """, extra_env={"WM_EXTRA": "1"}, git_template=git_template)
                env = run.record["env"]
                self.assertIsNone(env["PYTHONPATH"])
                self.assertIsNone(env["FORCE_COLOR"])
                self.assertEqual((env["PYTHONDONTWRITEBYTECODE"], env["PYTHON_COLORS"],
                                  env["WM_EXTRA"]), ("1", "0", "1"))
                self.assertEqual(env["TMPDIR"],
                                 str(isolation.chunk_paths(self.run_dir, "env").tmp))
                self.assertEqual(env["GIT_TEMPLATE_DIR"],
                                 None if git_template is None else str(git_template))
                for key, value in isolation.THROWAWAY_GIT_CONFIG.items():
                    self.assertEqual(env["git_config"].get(key.lower()), value, key)
                self.assertTrue(env["own_session"])
                self.assertLessEqual(run.started_at, run.ended_at)

    def test_the_timeout_formula(self):
        self.assertEqual(isolation.chunk_timeout(0), 600)
        self.assertEqual(isolation.chunk_timeout(200), 1000)
        self.assertEqual(isolation.chunk_timeout(10_000), 3600)


# -- T-ISO-4: A0 ordering and the exclusive-window check ------------------------------

def _descriptor(chunk_id, shard, *, exclusive=False, estimate=1.0):
    return plan_schema.ChunkDescriptor(chunk_id, shard, (f"host:test_{chunk_id}.py::C",),
                                       estimate, ("repo:tools",) if exclusive else ())


def _synthetic_plan(shards):
    return {"shards": [{"chunks": [c.to_json() for c in chunks]} for chunks in shards]}


class TestPhaseAOrder(unittest.TestCase):

    def test_the_exclusive_chunk_runs_first_whatever_its_shard(self):
        for exclusive_shard in (0, 7, 15):
            for position in (0, 25, 50):
                with self.subTest(shard=exclusive_shard, position=position):
                    shards = [[_descriptor(f"s{i}c{j}", i) for j in range(50)] for i in range(16)]
                    exclusive = _descriptor("excl", exclusive_shard, exclusive=True)
                    shards[exclusive_shard].insert(position, exclusive)
                    order = isolation.phase_a_order(_synthetic_plan(shards))
                    self.assertEqual(order.a0, (exclusive,))
                    self.assertEqual([list(s) for s in order.shards],
                                     [[c for c in s if not c.exclusive] for s in shards])
                    self.assertFalse(any(c.exclusive for s in order.shards for c in s))

    def test_one_shard_puts_the_exclusive_chunk_first(self):
        shared = [_descriptor(f"c{j}", 0) for j in range(5)]
        exclusive = _descriptor("excl", 0, exclusive=True)
        order = isolation.phase_a_order(_synthetic_plan([shared[:3] + [exclusive] + shared[3:]]))
        self.assertEqual(order.a0, (exclusive,))
        self.assertEqual(order.shards, (tuple(shared),))

    def test_several_exclusive_chunks_keep_plan_order(self):
        e1, e2, e3 = (_descriptor(n, s, exclusive=True) for n, s in (("e1", 0), ("e2", 1), ("e3", 1)))
        plan = _synthetic_plan([[_descriptor("a", 0), e1], [e2, _descriptor("b", 1), e3]])
        self.assertEqual(isolation.phase_a_order(plan).a0, (e1, e2, e3))

    def test_a_malformed_plan_is_refused(self):
        with self.assertRaises(plan_schema.PlanSchemaError):
            isolation.phase_a_order({"shards": [{"chunks": [{"id": "x"}]}]})

    def test_exclusive_windows(self):
        W = isolation.Window
        shared = [W("a", 0, 10), W("b", 5, 15), W("c", 1, 20)]
        isolation.check_exclusive_windows(shared)
        isolation.check_exclusive_windows(shared + [W("x", 20, 30, True), W("y", -5, 0, True)])
        for clash in (W("x", 19, 30, True), W("x", 2, 3, True), W("x", -5, 0.5, True)):
            with self.subTest(window=clash):
                with self.assertRaises(isolation.ExclusiveOverlapError):
                    isolation.check_exclusive_windows(shared + [clash])
        with self.assertRaises(isolation.ExclusiveOverlapError):
            isolation.check_exclusive_windows([W("x", 0, 10, True), W("y", 9, 12, True)])


# -- T-ISO-5 / -6 / -7 / -12 / -14: the barrier and the snapshot, in a scratch -----

class TestWriteBarrier(_ScratchCase):

    def run_host(self, scratch_root, unit_id, lock, index):
        chunk_id = f"{index:02d}-{unit_id}"
        record = isolation.chunk_paths(self.run_dir, chunk_id).record
        return isolation.run_chunk(scratch_root, chunk_id, unit.unit_argv(unit_id, record),
                                   run_dir=self.run_dir, timeout=120,
                                   cwd=scratch_root / "tests", lock=lock)

    def test_a_barrier_that_fails_part_way_is_undone_before_the_error_propagates(self):
        """Self-review: a `chmod` error or a signal while the barrier is being
        applied left directories `u-w` with nothing in-process to restore
        them (5.9)."""
        scratch = scratch_checkout(self.tmp / "scratch")
        pre_modes = _guarded_modes(scratch)
        real = isolation.Barrier._lock_dirs
        for error in (PermissionError(1, "chmod refused"), KeyboardInterrupt("signal 15")):
            locked = []

            def part_way(barrier, rels, error=error, locked=locked):
                rels = list(rels)
                real(barrier, rels[: len(rels) // 2])
                locked.append(sum(not _writable(m) for m in _guarded_modes(scratch).values()))
                raise error
            with self.subTest(error=type(error).__name__):
                with isolation.acquire_run_lock(scratch) as lock, \
                        mock.patch.object(isolation.Barrier, "_lock_dirs", part_way):
                    with self.assertRaises(type(error)):
                        isolation.apply_barrier(scratch, lock)
                self.assertGreater(locked[0], 0)
                self.assertEqual(_guarded_modes(scratch), pre_modes)
                self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())

    def test_a_root_barrier_allowed_by_allow_root_is_flagged(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        with isolation.acquire_run_lock(scratch) as lock:
            with mock.patch("os.geteuid", return_value=0):
                barrier = isolation.apply_barrier(scratch, lock, allow_root=True)
            isolation.restore_barrier(scratch, barrier)
            self.assertIn("running as root (--allow-root)", barrier.warnings[0])
            plain = isolation.apply_barrier(scratch, lock)
            isolation.restore_barrier(scratch, plain)
            self.assertFalse(any("root" in w for w in plain.warnings))

    def test_a_transient_structural_writer_is_refused_unless_lifted(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        declared = resources_module_load(scratch)
        chunk = plan_schema.ChunkDescriptor("excl", 0, (SCRATCH_EXCLUSIVE_UNIT,), 1.0,
                                            declared.resources_of(SCRATCH_EXCLUSIVE_UNIT))
        pre_modes = _guarded_modes(scratch)
        before = tree.snapshot(scratch)
        with isolation.acquire_run_lock(scratch) as lock:
            barrier = isolation.apply_barrier(scratch, lock)
            try:
                refused = self.run_host(scratch, SCRATCH_EXCLUSIVE_UNIT, lock, 1)
                self.assertEqual(refused.outcome, isolation.FAILED)
                self.assertEqual(refused.record["failing"],
                                 ["test_scratch_exclusive.py::TestScratchExclusiveWriter"
                                  "::test_rmtree_and_restore"])
                self.assertIn("PermissionError", refused.record["output_tail"])
                self.assertEqual(lock.holder["chunk_pgids"], [])

                barrier.lift(isolation.lift_trees(declared, chunk))
                lifted = self.run_host(scratch, SCRATCH_EXCLUSIVE_UNIT, lock, 2)
                barrier.relock()
                self.assertEqual(lifted.outcome, isolation.PASSED, lifted.record)
                self.assertFalse(any(_writable(m) for m in _guarded_modes(scratch).values()))
            finally:
                isolation.restore_barrier(scratch, barrier)
        self.assertEqual(tree.compare(before, tree.snapshot(scratch)), [])
        self.assertEqual(_guarded_modes(scratch), pre_modes)

    def test_a_transient_in_place_overwrite_is_the_documented_gap(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        target = scratch / SCRATCH_TOOL
        before = tree.snapshot(scratch)
        with isolation.acquire_run_lock(scratch) as lock:
            barrier = isolation.apply_barrier(scratch, lock)
            try:
                record = isolation.chunk_paths(self.run_dir, "overwrite").record
                run = isolation.run_chunk(scratch, "overwrite", _script_argv("""
                    import json, sys
                    path = sys.argv[2]
                    original = open(path, "rb").read()
                    open(path, "wb").write(b"clobbered")
                    open(path, "wb").write(original)
                    open(sys.argv[1], "w").write(json.dumps({"passed": True}))
                """, record, target), run_dir=self.run_dir, timeout=60, lock=lock)
            finally:
                isolation.restore_barrier(scratch, barrier)
        # Not caught by the barrier (file modes are untouched) ...
        self.assertEqual(run.outcome, isolation.PASSED)
        # ... nor by the snapshot (the bytes were restored) ...
        self.assertEqual(tree.compare(before, tree.snapshot(scratch)), [])
        # ... but flagged by the static lint when the path is REPO_ROOT-rooted.
        findings = isolation.lint_source(textwrap.dedent('''
            import unittest
            from support import REPO_ROOT

            class TestOverwrite(unittest.TestCase):
                def test_it(self):
                    path = REPO_ROOT / "distribution" / "x.py"
                    original = path.read_bytes()
                    path.write_bytes(b"clobbered")
                    path.write_bytes(original)
        '''), "test_overwrite.py")
        self.assertEqual([(f.unit, f.pattern) for f in findings],
                         [("host:test_overwrite.py::TestOverwrite", ".write_bytes() under REPO_ROOT")] * 2)

    def test_a_persistent_writer_is_reported_and_attributed(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        leak = scratch / SCRATCH_TOOLS / "leak.ignored"
        tracked = scratch / "tools" / ".keep"
        before = tree.snapshot(scratch)
        run_started = time.time()
        idle = """
            import json, sys, time
            time.sleep(0.2)
            open(sys.argv[1], "w").write(json.dumps({"passed": True}))
        """
        runs = []
        for chunk_id, code, args in (
                ("idle-1", idle, ()),
                ("writer", """
                    import json, os, sys, time
                    time.sleep(0.2)
                    open(sys.argv[2], "w").write("left behind")
                    os.remove(sys.argv[3])
                    time.sleep(0.2)
                    open(sys.argv[1], "w").write(json.dumps({"passed": True}))
                """, (leak, tracked)),
                ("idle-2", idle, ())):
            record = isolation.chunk_paths(self.run_dir, chunk_id).record
            runs.append(isolation.run_chunk(scratch, chunk_id, _script_argv(code, record, *args),
                                            run_dir=self.run_dir, timeout=60))
        run_ended = time.time()
        diffs = tree.compare(before, tree.snapshot(scratch))
        self.assertEqual(sorted(d.path for d in diffs),
                         sorted([f"{SCRATCH_TOOLS}/leak.ignored", "tools/.keep"]))
        windows = [r.window for r in runs] + [isolation.Window("before-the-run", 0, 1)]
        attributed = isolation.attribute_integrity_diff(
            scratch, diffs, windows, run_started=run_started, run_ended=run_ended)
        by_path = {a.path: a for a in attributed}
        self.assertEqual(by_path[f"{SCRATCH_TOOLS}/leak.ignored"].suspects, ("writer",))
        self.assertEqual(by_path[f"{SCRATCH_TOOLS}/leak.ignored"].basis, "mtime")
        self.assertEqual(by_path["tools/.keep"].suspects, ("idle-1", "idle-2", "writer"))
        self.assertEqual(by_path["tools/.keep"].basis, "run")

    def test_the_barrier_propagates_into_copies_and_cleanup_removes_them(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        with isolation.acquire_run_lock(scratch) as lock:
            barrier = isolation.apply_barrier(scratch, lock)
            try:
                record = isolation.chunk_paths(self.run_dir, "copier").record
                run = isolation.run_chunk(scratch, "copier", _script_argv("""
                    import json, os, shutil, stat, sys
                    copy = os.path.join(os.environ["TMPDIR"], "copy")
                    shutil.copytree(os.path.join(sys.argv[2], "tools"), copy)
                    dirs = [d for d, _, _ in os.walk(copy)]
                    read_only = all(not os.stat(d).st_mode & stat.S_IWUSR for d in dirs)
                    try:
                        open(os.path.join(copy, "new.txt"), "w").write("x")
                        create = "created"
                    except PermissionError:
                        create = "PermissionError"
                    existing = os.path.join(copy, "scratch", "lib", "bin", "tiny_tool.py")
                    open(existing, "w").write("overwritten")
                    result = {"passed": True, "dirs": len(dirs), "read_only": read_only,
                              "create": create, "overwrite": open(existing).read()}
                    open(sys.argv[1], "w").write(json.dumps(result))
                """, record, scratch), run_dir=self.run_dir, timeout=60, lock=lock)
            finally:
                isolation.restore_barrier(scratch, barrier)
        self.assertEqual(run.outcome, isolation.PASSED, run.record)
        self.assertGreater(run.record["dirs"], 3)
        self.assertTrue(run.record["read_only"])
        self.assertEqual(run.record["create"], "PermissionError")
        self.assertEqual(run.record["overwrite"], "overwritten")
        self.assertIn("copy", run.tmp_residue)
        self.assertIn("copy/scratch/lib/bin/tiny_tool.py", run.tmp_residue)
        self.assertFalse(isolation.chunk_paths(self.run_dir, "copier").tmp.exists())

    def test_scratch_declarations_are_valid_and_lifting_follows_paths(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        declared = resources_module_load(scratch)
        self.assertIn(SCRATCH_EXCLUSIVE_UNIT, inventory.discover_host(scratch))
        self.assertEqual(declared.exclusive_units(), (SCRATCH_EXCLUSIVE_UNIT,))
        stray = json.loads(json.dumps(SCRATCH_RESOURCES))
        stray["exclusive"] = {"host:test_bootstrap.py::TestInstallationRecord":
                              stray["exclusive"][SCRATCH_EXCLUSIVE_UNIT]}
        with self.assertRaises(resources.ResourcesFileError):
            scratch_checkout(self.tmp / "stray", resources=stray)

        chunk = plan_schema.ChunkDescriptor("excl", 0, (SCRATCH_EXCLUSIVE_UNIT,), 1.0,
                                            declared.resources_of(SCRATCH_EXCLUSIVE_UNIT))
        self.assertEqual(isolation.lift_trees(declared, chunk), ("tools/",))
        with isolation.acquire_run_lock(scratch) as lock:
            barrier = isolation.apply_barrier(scratch, lock)
            try:
                barrier.lift(isolation.lift_trees(declared, chunk))
                for rel, mode in _guarded_modes(scratch).items():
                    with self.subTest(dir=rel):
                        self.assertEqual(_writable(mode), rel.startswith("tools"))
                barrier.relock()
                self.assertFalse(any(_writable(m) for m in _guarded_modes(scratch).values()))
                with self.assertRaises(isolation.BarrierError):
                    barrier.lift(("tests/",))
            finally:
                isolation.restore_barrier(scratch, barrier)

    def test_relock_covers_directories_the_exclusive_unit_created(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        pre_modes = _guarded_modes(scratch)
        with isolation.acquire_run_lock(scratch) as lock:
            barrier = isolation.apply_barrier(scratch, lock)
            try:
                barrier.lift(("tools/",))
                (scratch / "tools" / "new").mkdir()
                shutil.rmtree(scratch / SCRATCH_TOOLS)
                barrier.relock()
                self.assertFalse(_writable(os.lstat(scratch / "tools" / "new").st_mode))
                marker = json.loads((isolation.state_dir(scratch) / "barrier.json").read_text())
                self.assertIn("tools/new", marker["modes"])
                self.assertNotIn(SCRATCH_TOOLS, marker["modes"])
            finally:
                isolation.restore_barrier(scratch, barrier)
        self.assertTrue(_writable(os.lstat(scratch / "tools" / "new").st_mode))
        expected = {r: m for r, m in pre_modes.items() if not r.startswith(SCRATCH_TOOLS)}
        expected["tools/new"] = _guarded_modes(scratch)["tools/new"]
        self.assertEqual(_guarded_modes(scratch), expected)


# -- T-ISO-8 / -11 / -13: the run lock, recovery and linked worktrees ---------------

class TestRunLockAndRecovery(_ScratchCase):

    def test_the_refusal_hint_names_only_groups_that_still_exist(self):
        """Review O7: after a SIGKILLed executor the recorded groups are
        frozen; a group that is gone (and whose id may be reused) is never
        offered as a `kill` target, and the hint says to verify first."""
        scratch = scratch_checkout(self.tmp / "scratch")
        live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                start_new_session=True)
        self.addCleanup(live.wait)
        self.addCleanup(isolation._kill_group, live.pid)
        gone = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        gone.wait()
        with isolation.acquire_run_lock(scratch) as held:
            for pgid in (live.pid, gone.pid):
                held.add_chunk_pgid(pgid)
            with self.assertRaises(isolation.RunLockHeldError) as ctx:
                isolation.acquire_run_lock(scratch)
        message = str(ctx.exception)
        self.assertIn(f"kill -- -{live.pid}", message)
        self.assertNotIn(f"kill -- -{gone.pid}", message)
        self.assertIn(f"no longer running: [{gone.pid}]", message)
        self.assertIn("verify each group still belongs to that run", message)
        self.assertIn("a chunk not yet recorded is not listed", message)

    def test_recovery_acts_only_on_a_dead_owner(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        pre_modes = _guarded_modes(scratch)
        ready, stop = self.tmp / "ready", self.tmp / "stop"
        helper = multiprocessing.get_context("spawn").Process(
            target=_hold_lock_with_child_then_hang, args=(scratch, str(ready), str(stop)))
        helper.start()
        try:
            child = self.wait_ready(ready, helper)["child"]
        finally:
            os.kill(helper.pid, signal.SIGKILL)
            helper.join(30)
        self.assertEqual(helper.exitcode, -signal.SIGKILL)

        with self.assertRaises(isolation.RunLockHeldError) as ctx:
            isolation.acquire_run_lock(scratch)
        self.assertEqual(ctx.exception.holder["chunk_pgids"], [child])
        self.assertIn(f"kill -- -{child}", str(ctx.exception))
        self.assertFalse(any(_writable(m) for m in _guarded_modes(scratch).values()))
        self.assertTrue((isolation.state_dir(scratch) / "barrier.json").exists())

        stop.write_text("")
        self.assertTrue(_wait_until(lambda: _dead(child)))
        lock = None
        deadline = time.monotonic() + 15
        while lock is None:
            try:
                lock = isolation.acquire_run_lock(scratch)
            except isolation.RunLockHeldError:
                self.assertLess(time.monotonic(), deadline, "the lock outlived the child")
                time.sleep(0.05)
        with lock:
            restored = isolation.recover_barrier(scratch, lock)
            self.assertEqual(sorted(restored), sorted(pre_modes))
            self.assertEqual(_guarded_modes(scratch), pre_modes)
            self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())
            self.assertEqual(isolation.recover_barrier(scratch, lock), [])

    def test_releasing_the_lock_leaves_it_to_a_chunk_still_holding_the_fd(self):
        """Self-review: `LOCK_UN` on the shared open file description dropped
        the lock for a still-running chunk; `release` now only closes."""
        scratch = scratch_checkout(self.tmp / "scratch")
        stop = self.tmp / "stop"
        lock = isolation.acquire_run_lock(scratch)
        child = subprocess.Popen(_script_argv(_WAIT_FOR_FILE, stop), start_new_session=True,
                                 pass_fds=(lock.fd,))
        try:
            lock.release()
            self.assertFalse(lock.held)
            with self.assertRaises(isolation.RunLockHeldError):
                isolation.acquire_run_lock(scratch)
        finally:
            stop.write_text("")
            child.wait(30)
        with isolation.acquire_run_lock(scratch) as again:
            self.assertTrue(again.held)

    def test_a_chunk_holds_the_lock_fd_and_its_group_is_recorded_while_it_runs(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        with isolation.acquire_run_lock(scratch) as lock:
            record = isolation.chunk_paths(self.run_dir, "holder").record
            run = isolation.run_chunk(scratch, "holder", _script_argv("""
                import json, os, sys
                inherited = os.fstat(int(sys.argv[3]))  # before anything else opens an fd
                same_file = os.path.samestat(inherited, os.stat(sys.argv[2]))
                result = {"passed": True, "holder": json.load(open(sys.argv[2])),
                          "same_file": same_file}
                open(sys.argv[1], "w").write(json.dumps(result))
            """, record, lock.path, lock.fd), run_dir=self.run_dir, timeout=60, lock=lock)
            self.assertEqual(run.outcome, isolation.PASSED, run.record)
            self.assertTrue(run.record["same_file"])
            self.assertEqual(run.record["holder"]["chunk_pgids"], [run.pgid])
            self.assertEqual(run.record["holder"]["pid"], os.getpid())
            self.assertEqual(json.loads(lock.path.read_text())["chunk_pgids"], [])

    def test_the_barrier_is_only_touched_under_the_lock(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        other = scratch_checkout(self.tmp / "other")
        lock = isolation.acquire_run_lock(scratch)
        lock.release()
        with self.assertRaises(isolation.BarrierError):
            isolation.apply_barrier(scratch, lock)
        with isolation.acquire_run_lock(other) as foreign:
            with self.assertRaises(isolation.BarrierError):
                isolation.recover_barrier(scratch, foreign)
        with isolation.acquire_run_lock(scratch) as held:
            barrier = isolation.apply_barrier(scratch, held)
            with self.assertRaises(isolation.BarrierError):
                isolation.apply_barrier(scratch, held)  # a marker exists: recover first
            isolation.restore_barrier(scratch, barrier)
            isolation.restore_barrier(scratch, barrier)  # idempotent

    def test_root_is_refused_unless_allowed(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        pre_modes = _guarded_modes(scratch)
        with isolation.acquire_run_lock(scratch) as lock, \
                mock.patch("os.geteuid", return_value=0):
            with self.assertRaises(isolation.RootRefusedError):
                isolation.apply_barrier(scratch, lock)
            self.assertEqual(_guarded_modes(scratch), pre_modes)
            self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())
            barrier = isolation.apply_barrier(scratch, lock, allow_root=True)
            isolation.restore_barrier(scratch, barrier)
        self.assertEqual(_guarded_modes(scratch), pre_modes)

    def test_a_directory_already_read_only_is_warned_about_and_kept(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        tools = scratch / "tools"
        os.chmod(tools, 0o555)
        pre_modes = _guarded_modes(scratch)
        with isolation.acquire_run_lock(scratch) as lock:
            barrier = isolation.apply_barrier(scratch, lock)
            isolation.restore_barrier(scratch, barrier)
        self.assertEqual(len(barrier.warnings), 1)
        self.assertIn("tools", barrier.warnings[0])
        self.assertEqual(_guarded_modes(scratch), pre_modes)

    def test_one_lock_per_checkout(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        pre_modes = _guarded_modes(scratch)
        ready, stop = self.tmp / "ready", self.tmp / "stop"
        holder = multiprocessing.get_context("spawn").Process(
            target=_hold_lock_and_barrier, args=(scratch, str(ready), str(stop)))
        holder.start()
        try:
            holder_pid = self.wait_ready(ready, holder)["pid"]
            applied = _guarded_modes(scratch)
            self.assertFalse(any(_writable(m) for m in applied.values()))
            started = time.monotonic()
            with self.assertRaises(isolation.RunLockHeldError) as ctx:
                isolation.acquire_run_lock(scratch)
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(ctx.exception.holder["pid"], holder_pid)
            self.assertEqual(_guarded_modes(scratch), applied)
        finally:
            stop.write_text("")
            holder.join(30)
        self.assertEqual(holder.exitcode, 0)
        self.assertEqual(_guarded_modes(scratch), pre_modes)
        self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())

    def test_linked_worktrees_have_their_own_lock_and_barrier(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        worktree = scratch_worktree(scratch)
        main_modes, wt_modes = _guarded_modes(scratch), _guarded_modes(worktree)
        self.assertNotEqual(isolation.state_dir(scratch), isolation.state_dir(worktree))
        with isolation.acquire_run_lock(scratch) as main_lock, \
                isolation.acquire_run_lock(worktree) as wt_lock:
            main_barrier = isolation.apply_barrier(scratch, main_lock)
            wt_barrier = isolation.apply_barrier(worktree, wt_lock)
            try:
                self.assertTrue((isolation.state_dir(scratch) / "barrier.json").exists())
                self.assertTrue((isolation.state_dir(worktree) / "barrier.json").exists())
                isolation.restore_barrier(scratch, main_barrier)
                self.assertEqual(_guarded_modes(scratch), main_modes)
                self.assertFalse(any(_writable(m) for m in _guarded_modes(worktree).values()))
                self.assertEqual(isolation.recover_barrier(scratch, main_lock), [])
                self.assertFalse(any(_writable(m) for m in _guarded_modes(worktree).values()))
                with self.assertRaises(isolation.BarrierError):
                    isolation.recover_barrier(worktree, main_lock)
            finally:
                isolation.restore_barrier(worktree, wt_barrier)
        self.assertEqual(_guarded_modes(worktree), wt_modes)


# -- T-ISO-9: the static writer lint ---------------------------------------------------

LINT_MODULE = '''
import os
import shutil
import subprocess
import sys
from pathlib import Path
import unittest

import support
from support import REPO_ROOT
from workflow_manager import install

TOOLS = REPO_ROOT / "tools"


class TestWriters(unittest.TestCase):
    def test_all(self):
        install.bootstrap(REPO_ROOT, release)                                             # 1
        install.update(target=REPO_ROOT / "sub", release=release)                        # 2
        shutil.rmtree(TOOLS / "release")                                                   # 3
        os.remove(str(REPO_ROOT / "README.md"))                                            # 4
        (REPO_ROOT / "a").unlink()                                                         # 5
        (support.REPO_ROOT / "b").write_text("x")                                          # 6
        target = TOOLS / "c"
        target.write_bytes(b"x")                                                           # 7
        open(REPO_ROOT / "d", "a")                                                         # 8
        open(os.path.join(REPO_ROOT, "e"), mode="x")                                       # 9
        (REPO_ROOT / "f").open("w")                                                        # 10
        shutil.copy2(src, REPO_ROOT / "g")                                                 # 11
        shutil.copytree(src, dst=f"{REPO_ROOT}/h")                                         # 12
        os.replace(src, REPO_ROOT / "i")                                                   # 13
        Path(src).rename(REPO_ROOT / "j")                                                  # 14


class TestReaders(unittest.TestCase):
    def test_none(self):
        install.bootstrap(Path(tmp) / "target", release)
        shutil.copytree(REPO_ROOT / "tools" / "release", dest)   # a copy out of the tree
        shutil.copy(TOOLS / "x", Path(tmp) / "x")
        (REPO_ROOT / "README.md").read_text()
        open(REPO_ROOT / "README.md")
        open(REPO_ROOT / "README.md", "rb")
        Path(tmp).joinpath("x").write_text("fine")
        shutil.rmtree(tmp)
        os.rename(REPO_ROOT / "x", tmp)


def helper():
    shutil.rmtree(REPO_ROOT / "k")                                                         # 15
'''


class TestStaticLint(unittest.TestCase):

    def test_every_pattern_is_flagged_and_reads_are_not(self):
        findings = isolation.lint_source(LINT_MODULE, "test_lint.py")
        lines = LINT_MODULE.splitlines()
        numbered = {int(line.rsplit("# ", 1)[1]): index + 1 for index, line in enumerate(lines)
                    if re.search(r"# \d+$", line)}
        self.assertEqual(sorted(f.line for f in findings), sorted(numbered.values()), findings)
        self.assertEqual({f.unit for f in findings},
                         {"host:test_lint.py::TestWriters", None})

    def test_a_declared_unit_is_exempt(self):
        declared = resources.parse({
            "schema_version": 1,
            "resources": {"r": {"paths": ["tools/"], "description": "d"}},
            "exclusive": {"host:test_lint.py::TestWriters": {"resources": ["r"], "reason": "x"}},
        }, ["host:test_lint.py::TestWriters"])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tests").mkdir()
            (Path(tmp) / "tests" / "test_lint.py").write_text(LINT_MODULE)
            findings = isolation.lint_tests(Path(tmp), declared)
        self.assertEqual([f.unit for f in findings], [None])

    def test_todays_tests_are_lint_clean(self):
        """Against the committed declaration, which declares no exclusive unit."""
        inv = inventory.discover(REPO_ROOT)
        declared = resources.load(REPO_ROOT, list(inv.host), orphan_unit_ids=inv.unit_ids())
        self.assertEqual(declared.exclusive_units(), ())
        self.assertEqual([str(f) for f in isolation.lint_tests(REPO_ROOT, declared)], [])



# == CP5: the executor, the CLI and the report (T-EXE-1..11) ==========================

def run_cli(scratch_root, *argv, env, timeout=600) -> subprocess.CompletedProcess:
    """`python3 <scratch>/tests/run_all.py ARGV` -- always a scratch checkout's own
    runner, never the real one (5.9, "Tests and the lock"), on its own release
    source and cache (`scratch_release_env`)."""
    return subprocess.run([sys.executable, str(scratch_root / "tests" / "run_all.py"),
                           *map(str, argv)], cwd=str(scratch_root), capture_output=True,
                          text=True, env={**env, **scratch_release_env(scratch_root)},
                          timeout=timeout)


def start_cli(scratch_root, *argv, env) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(scratch_root / "tests" / "run_all.py"),
                             *map(str, argv)], cwd=str(scratch_root), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            env={**env, **scratch_release_env(scratch_root)})


def run_reproduction(scratch_root, command: str, *, env) -> subprocess.CompletedProcess:
    """Run a report's `python3 tests/run_all.py ...` reproduction line in the
    scratch checkout it came from."""
    words = shlex.split(command)
    assert words[:2] == ["python3", "tests/run_all.py"], command
    return subprocess.run([sys.executable, str(scratch_root / "tests" / "run_all.py"),
                           *words[2:]], cwd=str(scratch_root), capture_output=True, text=True,
                          env={**env, **scratch_release_env(scratch_root)}, timeout=600)


def main_in_process(scratch_root, *argv) -> tuple[int, str, str]:
    """`cli.main` in this process, against a scratch checkout, on its own
    release source and cache."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.dict(os.environ, scratch_release_env(scratch_root)):
        code = cli.main([str(a) for a in argv], repo_root=scratch_root)
    return code, out.getvalue(), err.getvalue()


def assert_refusal(case: unittest.TestCase, code: int, stderr: str, name: str) -> None:
    """The shared refusal assertion (T-EXE-6): exit 2 and the error tag of
    exactly `name` on the first stderr line."""
    case.assertEqual(code, 2, stderr)
    first = stderr.splitlines()[0] if stderr else ""
    case.assertTrue(first.startswith(f"run_all: error[{name}]: "), stderr[-3000:])


def _results(results_dir: Path) -> dict:
    return json.loads((Path(results_dir) / "results.json").read_text())["units"]


def _lock_holder(scratch_root) -> dict:
    try:
        return json.loads((isolation.state_dir(scratch_root) / "run.lock").read_text())
    except (OSError, ValueError):
        return {}


FAILING_HOST_MODULE = """
import unittest


class TestScratchFailing(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)

    def test_bad(self):
        self.assertEqual(1, 2)
"""

CRASH_MODULE = """
import os
import unittest


class TestScratchCrash(unittest.TestCase):
    def test_dies_before_any_record(self):
        os._exit(0)
"""

SLEEP_MODULE = """
import time
import unittest


class TestScratchSleep(unittest.TestCase):
    def test_sleeps_past_its_timeout(self):
        time.sleep(120)
"""

WRITER_MODULE = """
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestScratchWriter(unittest.TestCase):
    def test_overwrites_a_tracked_file_in_place(self):
        (ROOT / "tools" / ".keep").write_text("written during the run")
"""

WAIT_MODULE = """
import os
import time
import unittest


class TestScratchWait(unittest.TestCase):
    def test_waits_for_the_stop_file(self):
        deadline = time.monotonic() + 120
        while not os.path.exists(os.environ["WM_SCRATCH_STOP"]):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
"""


def _trivial_module(prefix: str, classes: int = 2) -> str:
    return "import unittest\n\n" + "".join(
        f"\nclass Test{prefix}{i:03d}(unittest.TestCase):\n    def test_it(self):\n"
        f"        self.assertTrue(True)\n" for i in range(classes))


class _CliCase(_ScratchCase):
    """Every run writes its timing history under this test's own cache, and its
    run directory (kept on purpose after a failing run) under this test's own
    temporary directory, so both go when the test does."""

    def setUp(self):
        super().setUp()
        temp = self.tmp / "tmp"
        temp.mkdir()
        for patcher in (mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.tmp / "cache"),
                                                     "TMPDIR": str(temp)}),
                        mock.patch.object(tempfile, "tempdir", str(temp))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.env = dict(os.environ)


# -- T-EXE-1: the exit-code contract ----------------------------------------------------

class TestExitCodeContract(_CliCase):

    def test_everything_passing_is_0(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        proc = run_cli(scratch, "--results", self.tmp / "r", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        units = _results(self.tmp / "r")
        self.assertEqual({u["outcome"] for u in units.values()}, {"passed"})
        self.assertIn(SCRATCH_MATRIX_UNIT, units)
        self.assertEqual(units[SCRATCH_MATRIX_UNIT]["phase"], "B")
        self.assertTrue((self.tmp / "cache" / "workflow-manager" / "test-timings.jsonl").exists())

    def test_one_failing_host_test_is_1(self):
        scratch = scratch_checkout(self.tmp / "scratch",
                                   modules={"test_scratch_failing.py": FAILING_HOST_MODULE})
        proc = run_cli(scratch, "--select", "test_scratch_failing.py", env=self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("failing: test_scratch_failing.py::TestScratchFailing::test_bad", proc.stdout)
        self.assertNotIn("error[", proc.stderr)

    def test_one_frozen_chunk_with_a_failing_test_is_1(self):
        scratch = scratch_checkout(self.tmp / "scratch", suite=SCRATCH_SUITE_VARIANTS["failing"])
        for argv in ((), ("--select", SCRATCH_FROZEN_SUITE)):
            with self.subTest(argv=argv):
                proc = run_cli(scratch, *argv, env=self.env)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("TestGamma.test_four", proc.stdout)
                self.assertNotIn("error[", proc.stderr)

    def test_an_unwritable_timing_history_keeps_the_report_and_the_verdict(self):
        # A regular file where the cache directory should be: the history
        # append fails with an `OSError` whoever runs the test.
        blocker = self.tmp / "not-a-directory"
        blocker.write_text("")
        env = dict(self.env, XDG_CACHE_HOME=str(blocker))
        cases = {"green": ({}, 0, "passed"),
                 "failing": ({"test_scratch_failing.py": FAILING_HOST_MODULE}, 1, "failed")}
        for name, (modules, code, outcome) in cases.items():
            with self.subTest(case=name):
                scratch = scratch_checkout(self.tmp / name, modules=modules)
                argv = ("--select", "test_scratch_failing.py") if modules else ()
                proc = run_cli(scratch, *argv, "--results", self.tmp / f"r-{name}", env=env)
                self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
                self.assertNotIn("error[", proc.stderr)
                self.assertIn("warning: could not write the timing history", proc.stderr)
                self.assertIn("the verdict is unchanged", proc.stderr)
                self.assertIn("evidence: ", proc.stdout)
                self.assertIn(f"verdict: exit {code}", proc.stdout)
                units = _results(self.tmp / f"r-{name}")
                self.assertIn(outcome, {u["outcome"] for u in units.values()})
                self.assertTrue((self.tmp / f"r-{name}" / "timings.jsonl").exists())
                if modules:
                    self.assertIn(
                        "failing: test_scratch_failing.py::TestScratchFailing::test_bad",
                        proc.stdout)

    def test_setupclass_errors_import_crashes_and_builder_failures_are_1_not_2(self):
        cases = {"setupclass_error": {"suite": SCRATCH_SUITE_VARIANTS["setupclass_error"]},
                 "import_crash": {"suite": SCRATCH_SUITE_VARIANTS["import_crash"]},
                 "builder_raises": {"no_gitignore_template": True}}
        for name, options in cases.items():
            with self.subTest(case=name):
                scratch = scratch_checkout(self.tmp / name, **options)
                proc = run_cli(scratch, "--results", self.tmp / f"r-{name}", env=self.env)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("error[", proc.stderr)
                units = _results(self.tmp / f"r-{name}")
                self.assertEqual(units[SCRATCH_MATRIX_UNIT]["outcome"], "failed")

    def test_a_chunk_killed_before_writing_its_record_is_2(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={"test_scratch_crash.py": CRASH_MODULE})
        proc = run_cli(scratch, "--select", "test_scratch_crash.py", env=self.env)
        assert_refusal(self, proc.returncode, proc.stderr, "InfrastructureFaultError")
        self.assertIn("host:test_scratch_crash.py::TestScratchCrash", proc.stderr)
        self.assertIn("missing_record", proc.stdout)

    def test_a_failure_plus_an_infrastructure_fault_is_2_and_the_failure_is_listed(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={
            "test_scratch_crash.py": CRASH_MODULE, "test_scratch_failing.py": FAILING_HOST_MODULE})
        proc = run_cli(scratch, "--select", "test_scratch_crash.py",
                       "--select", "test_scratch_failing.py", env=self.env)
        assert_refusal(self, proc.returncode, proc.stderr, "InfrastructureFaultError")
        self.assertIn("failing: test_scratch_failing.py::TestScratchFailing::test_bad", proc.stdout)


# -- T-EXE-2: the report ------------------------------------------------------------------

MODULE_LINE_RE = re.compile(r"^(ok  |FAIL) (test_\w+\.py)\s+\d+\.\ds  Ran \d+ tests  (OK|FAILED)",
                            re.MULTILINE)


class TestReport(_CliCase):

    def test_module_lines_failure_blocks_and_a_reproduction_that_reproduces(self):
        scratch = scratch_checkout(self.tmp / "scratch",
                                   modules={"test_scratch_failing.py": FAILING_HOST_MODULE})
        proc = run_cli(scratch, "--results", self.tmp / "r", env=self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        lines = dict((m.group(2), m.group(1)) for m in MODULE_LINE_RE.finditer(proc.stdout))
        self.assertEqual(lines, {"test_scratch_exclusive.py": "ok  ",
                                 "test_scratch_failing.py": "FAIL",
                                 "test_scratch_matrix.py": "ok  ",
                                 "test_scratch_shared.py": "ok  "})
        block = proc.stdout.split("host:test_scratch_failing.py::TestScratchFailing  (A,", 1)[1]
        self.assertIn("failing: test_scratch_failing.py::TestScratchFailing::test_bad", block)
        log = re.search(r"  log: (\S+)", block).group(1)
        self.assertTrue(Path(log).is_file())
        self.assertIn("AssertionError", block)
        command = re.search(r"  reproduce: (.+)", block).group(1)
        self.assertEqual(command, "python3 tests/run_all.py --jobs 1 "
                                  "--select test_scratch_failing.py::TestScratchFailing")
        again = run_reproduction(scratch, command, env=self.env)
        self.assertEqual(again.returncode, 1, again.stdout + again.stderr)
        self.assertEqual(re.findall(r"failing: (\S+)", again.stdout),
                         re.findall(r"failing: (\S+)", block))

    def test_a_failing_multi_class_frozen_chunk_reproduces_as_one_invocation(self):
        suite = SCRATCH_FROZEN_SUITE
        scratch = scratch_checkout(
            self.tmp / "scratch", suite=SCRATCH_SUITE_VARIANTS["failing"],
            timings_units={f"{suite}::TestAlpha": 100.0, f"{suite}::TestBeta": 10.0,
                           f"{suite}::TestGamma": 10.0})
        proc = run_cli(scratch, "--select", suite, "--results", self.tmp / "r", env=self.env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        units = _results(self.tmp / "r")
        self.assertEqual(units[f"{suite}::TestBeta"]["chunk"], units[f"{suite}::TestGamma"]["chunk"])
        self.assertNotEqual(units[f"{suite}::TestAlpha"]["chunk"],
                            units[f"{suite}::TestGamma"]["chunk"])
        command = re.search(r"  reproduce: (.+--whole-groups.+)", proc.stdout).group(1)
        self.assertEqual(command, "python3 tests/run_all.py --jobs 1 --whole-groups "
                                  f"--select {suite}::TestBeta --select {suite}::TestGamma")
        again = run_reproduction(scratch, command + f" --results {self.tmp / 'again'}",
                                 env=self.env)
        self.assertEqual(again.returncode, 1, again.stdout + again.stderr)
        rerun = _results(self.tmp / "again")
        self.assertEqual(sorted(rerun), [f"{suite}::TestBeta", f"{suite}::TestGamma"])
        self.assertEqual(len({u["chunk"] for u in rerun.values()}), 1)
        self.assertEqual(rerun[f"{suite}::TestGamma"]["failing"],
                         units[f"{suite}::TestGamma"]["failing"])
        self.assertEqual(rerun[f"{suite}::TestGamma"]["failing"], ["TestGamma.test_four"])
        self.assertIn(inventory.PARTIAL_FROZEN_NOTE, again.stdout)


# -- T-EXE-3: serial and parallel runs agree; shuffling permutes only the order ----------

class TestSerialAndParallelAgree(_CliCase):

    def test_jobs_1_and_jobs_4_and_shuffled_runs_execute_the_same_units(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={
            f"test_scratch_bulk{i}.py": _trivial_module(f"Bulk{i}_", 3) for i in range(4)})
        runs = {}
        for label, argv in (("jobs1", ("--jobs", "1")), ("jobs4", ("--jobs", "4")),
                            ("seed1", ("--jobs", "1", "--shuffle-seed", "1")),
                            ("seed2", ("--jobs", "1", "--shuffle-seed", "2")),
                            ("seed3", ("--jobs", "1", "--shuffle-seed", "3"))):
            proc = run_cli(scratch, *argv, "--results", self.tmp / label, env=self.env)
            self.assertEqual(proc.returncode, 0, f"{label}: {proc.stdout}{proc.stderr}")
            runs[label] = _results(self.tmp / label)
        reference = runs["jobs1"]
        for label, units in runs.items():
            with self.subTest(run=label):
                self.assertEqual(sorted(units), sorted(reference))
                self.assertEqual({u: v["outcome"] for u, v in units.items()},
                                 {u: v["outcome"] for u, v in reference.items()})
                self.assertEqual({u: v["tests"] for u, v in units.items()},
                                 {u: v["tests"] for u, v in reference.items()})

        def order(units):
            shared = [(v["window"][0], u) for u, v in units.items() if v["phase"] == "A"]
            return [u for _, u in sorted(shared)]
        orders = {label: tuple(order(runs[label])) for label in ("seed1", "seed2", "seed3")}
        self.assertGreater(len(set(orders.values())), 1, "shuffling never changed the order")


# -- T-EXE-4: path flags never point inside the repository --------------------------------

class TestPathFlagsStayOutsideTheRepository(_CliCase):

    def test_every_path_flag_refuses_a_path_inside_the_repository(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        inside = scratch / "tests" / "out"
        outside = self.tmp / "plan.json"
        for argv in (("--plan-only", "--out", inside),
                     ("--run-shard", "0", "--plan", inside, "--results", self.tmp / "r"),
                     ("--run-shard", "0", "--plan", outside, "--results", inside),
                     ("--results", inside),
                     ("--aggregate", inside, "--plan", outside),
                     ("--aggregate", self.tmp, "--plan", scratch / "plan.json"),
                     # Review O5: --from only reads, but 5.6 covers every path flag.
                     ("--update-timings", "--profile", "local", "--from", scratch / "tests"),
                     ("--update-timings", "--profile", "local",
                      "--from", outside, "--from", inside)):
            with self.subTest(argv=argv):
                proc = run_cli(scratch, *argv, env=self.env)
                assert_refusal(self, proc.returncode, proc.stderr, "PathInsideRepositoryError")
        self.assertFalse(inside.exists())
        self.assertFalse(isolation.state_dir(scratch).exists(), "a pre-lock refusal took the lock")


# -- T-EXE-5: the runner without the retired alias, and the direct entry points ---------

class TestDirectEntryPoints(_CliCase):

    def test_an_ordinary_run_succeeds(self):
        """`validate()` and the selection line, with the alias gone (CP6)."""
        scratch = scratch_checkout(self.tmp / "scratch",
                                   modules={"test_scratch_extra.py": _trivial_module("Extra", 1)})
        for argv in ((), ("--select", "test_scratch_extra.py")):
            with self.subTest(argv=argv):
                results = self.tmp / f"r{len(argv)}"
                proc = run_cli(scratch, *argv, "--results", results, env=self.env)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertTrue(_results(results))

    def test_the_retired_alias_is_refused(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        proc = run_cli(scratch, "--fast", env=self.env)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("unrecognized arguments: --fast", proc.stderr)

    def test_direct_module_runs_still_work(self):
        for argv in ([sys.executable, "test_bootstrap.py", "TestInstallationRecord"],
                     [sys.executable, "-m", "unittest", "test_bootstrap.TestInstallationRecord"]):
            with self.subTest(argv=argv):
                proc = subprocess.run(argv, cwd=str(TESTS_DIR), capture_output=True, text=True,
                                      env=dict(self.env, PYTHONDONTWRITEBYTECODE="1"))
                self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
                self.assertRegex(proc.stderr, r"\nOK\n")


# -- T-EXE-6: refusals are distinguishable --------------------------------------------------

def _plan_only(case, scratch_root, *argv) -> Path:
    plan = case.tmp / f"plan-{len(list(case.tmp.glob('plan-*')))}.json"
    proc = run_cli(scratch_root, "--plan-only", "--out", plan, *argv, env=case.env)
    case.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
    return plan


def _tampered(plan: Path) -> Path:
    doc = json.loads(plan.read_text())
    doc["predicted"]["total_work"] += 1
    out = plan.with_name("tampered-" + plan.name)
    out.write_text(canonical_json(doc))
    return out


class TestRefusalsAreDistinguishable(_CliCase):

    def test_a_held_lock_is_reported_as_itself(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        tampered = _tampered(_plan_only(self, scratch))
        ready, stop = self.tmp / "ready", self.tmp / "stop"
        holder = multiprocessing.get_context("spawn").Process(
            target=_hold_lock_and_barrier, args=(scratch, str(ready), str(stop)))
        holder.start()
        try:
            self.wait_ready(ready, holder)
            # (a) aimed at a plan-digest mismatch, it gets the lock refusal ...
            proc = run_cli(scratch, "--run-shard", "0", "--plan", tampered,
                           "--results", self.tmp / "r", env=self.env)
            assert_refusal(self, proc.returncode, proc.stderr, "RunLockHeldError")
            # ... and the shared assertion, pointed at the wrong name, fails.
            with self.assertRaises(AssertionError):
                assert_refusal(self, proc.returncode, proc.stderr, "PlanDigestMismatchError")
            # (b) pre-lock refusals are still reported as themselves.
            usage = run_cli(scratch, "--jobs", "0", env=self.env)
            self.assertEqual(usage.returncode, 2)
            self.assertIn("usage:", usage.stderr)
            self.assertNotIn("RunLockHeldError", usage.stderr)
            inside = run_cli(scratch, "--results", scratch / "tests" / "r", env=self.env)
            assert_refusal(self, inside.returncode, inside.stderr, "PathInsideRepositoryError")
            syntax = run_cli(scratch, "--list", "--select", "not a spec", env=self.env)
            assert_refusal(self, syntax.returncode, syntax.stderr, "SelectSyntaxError")
        finally:
            stop.write_text("")
            holder.join(30)

    def test_an_unexpected_error_is_an_infrastructure_fault_never_exit_1(self):
        """Self-review: an error the tool does not name (a failed `Popen`,
        `chmod` or git call, a full disk) exited 1 -- a test failure (5.11)."""
        scratch = scratch_checkout(self.tmp / "scratch")
        failure = OSError(24, "Too many open files")
        with mock.patch.object(executor, "list_units", side_effect=failure):
            code, _, err = main_in_process(scratch, "--list")
        assert_refusal(self, code, err, "OSError")
        self.assertIn("Traceback", err)
        with isolation.acquire_run_lock(scratch) as lock:   # released on the way out
            self.assertTrue(lock.held)

    def test_with_the_lock_free_each_refusal_reports_its_own_tag(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        plan = _plan_only(self, scratch)
        unknown = run_cli(scratch, "--list", "--select", "test_nope.py", env=self.env)
        assert_refusal(self, unknown.returncode, unknown.stderr, "UnknownSelectorError")
        unknown_frozen = run_cli(scratch, "--list", "--select",
                                 "frozen:0.0.1/conformance/tiny_test.py::TestNope", env=self.env)
        assert_refusal(self, unknown_frozen.returncode, unknown_frozen.stderr,
                       "UnknownSelectorError")
        digest = run_cli(scratch, "--run-shard", "0", "--plan", _tampered(plan),
                         "--results", self.tmp / "r1", env=self.env)
        assert_refusal(self, digest.returncode, digest.stderr, "PlanDigestMismatchError")
        miscounted = scratch_checkout(self.tmp / "miscounted", pinned=99)
        count = run_cli(miscounted, "--list", env=self.env)
        assert_refusal(self, count.returncode, count.stderr, "InventoryCountError")


# -- T-EXE-7: test-tree hygiene ---------------------------------------------------------------

#: The functions that reach a checkout's run lock (5.9, round 5 O1).
LOCK_FUNCS = ("acquire_run_lock", "apply_barrier", "restore_barrier", "recover_barrier")
#: The only tests allowed to run the real checkout's `run_all.py`: pre-lock
#: refusals, which never reach the lock.
PRE_LOCK_TESTS = ("test_cli_reports_a_syntax_error_by_name_before_discovery",)
CLI_ENTRY = "main"
_SUBPROCESS_FUNCS = ("run", "Popen", "check_output", "check_call", "call")


def lock_reach_violations(source: str) -> list[str]:
    """T-EXE-7's AST scan: every lock-reaching call and every subprocess that
    names `run_all.py` must be rooted at an accepted form (5.9)."""
    module = ast.parse(source)
    parents = {}
    for node in ast.walk(module):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    call_in_string = re.compile(r"\b(?:%s|cli\.main)\s*\(" % "|".join(LOCK_FUNCS))
    violations = [f"line {n.lineno}: a string constant calls a lock-reaching function"
                  for n in ast.walk(module)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and call_in_string.search(n.value)]
    top_level = {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}

    def enclosing_function(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return None

    def bindings(function) -> dict[str, list]:
        found: dict[str, list] = {}
        for sub in ast.walk(function) if function is not None else ():
            if isinstance(sub, ast.Assign):
                for target in sub.targets:
                    if isinstance(target, ast.Name):
                        found.setdefault(target.id, []).append(sub.value)
            elif isinstance(sub, ast.withitem) and isinstance(sub.optional_vars, ast.Name):
                found.setdefault(sub.optional_vars.id, []).append(sub.context_expr)
        return found

    param_ok: dict[str, bool] = {}

    def accepted(expr, function, seen=()) -> bool:
        if isinstance(expr, ast.Call):
            name = expr.func.id if isinstance(expr.func, ast.Name) else \
                getattr(expr.func, "attr", None)
            if name == "scratch_checkout":
                return True
            if name in ("scratch_worktree", "scratch_clone"):
                return bool(expr.args) and accepted(expr.args[0], function, seen)
            if name in ("str", "Path") and len(expr.args) == 1:
                return accepted(expr.args[0], function, seen)
            return False
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            return isinstance(expr.right, ast.Constant) and accepted(expr.left, function, seen)
        if isinstance(expr, ast.Name):
            if expr.id == "scratch_root" and function is not None \
                    and function.name in top_level and \
                    "scratch_root" in [a.arg for a in function.args.args]:
                return scratch_root_ok(function)
            values = bindings(function).get(expr.id)
            if not values or expr.id in seen:
                return False
            return all(accepted(v, function, seen + (expr.id,)) for v in values)
        return False

    def scratch_root_ok(function) -> bool:
        if function.name in param_ok:
            return param_ok[function.name]
        param_ok[function.name] = False  # recursion guard
        index = [a.arg for a in function.args.args].index("scratch_root")
        sites = []
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == function.name:
                keyword = [k.value for k in node.keywords if k.arg == "scratch_root"]
                sites.append((node, keyword[0] if keyword else
                              (node.args[index] if len(node.args) > index else None)))
            target = [k.value for k in node.keywords if k.arg == "target"]
            if target and isinstance(target[0], ast.Name) and target[0].id == function.name:
                args = [k.value for k in node.keywords if k.arg == "args"]
                value = args[0].elts[index] if args and isinstance(args[0], ast.Tuple) \
                    and len(args[0].elts) > index else None
                sites.append((node, value))
        ok = bool(sites) and all(v is not None and accepted(v, enclosing_function(n))
                                 for n, v in sites)
        param_ok[function.name] = ok
        return ok

    def exempt(node) -> bool:
        function = enclosing_function(node)
        return function is not None and function.name in PRE_LOCK_TESTS

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        function = enclosing_function(node)
        func = node.func
        root = None
        if isinstance(func, ast.Attribute) and func.attr in LOCK_FUNCS:
            root = node.args[0] if node.args else \
                next((k.value for k in node.keywords if k.arg == "repo_root"), None)
            what = func.attr
        elif isinstance(func, ast.Attribute) and func.attr == "main" and \
                isinstance(func.value, ast.Name) and func.value.id == "cli":
            root = next((k.value for k in node.keywords if k.arg == "repo_root"), None)
            what = "cli.main"
        elif isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_FUNCS and \
                isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            names = [n for arg in node.args for n in ast.walk(arg)
                     if isinstance(n, ast.Constant) and n.value == "run_all.py"]
            if not names:
                continue
            what = "a subprocess naming run_all.py"
            path = names[0]
            while isinstance(parents.get(path), ast.BinOp) and parents[path].right is path \
                    or isinstance(parents.get(path), ast.BinOp) and parents[path].left is path:
                path = parents[path]
            root = path.left if isinstance(path, ast.BinOp) else None
            while isinstance(root, ast.BinOp):
                root = root.left
        else:
            continue
        if exempt(node):
            continue
        if root is None or not accepted(root, function):
            violations.append(f"line {node.lineno}: {what} is not rooted at a scratch checkout")
    return violations


#: The release cache this process was given (the runner's primed one),
#: captured before any test moves `XDG_CACHE_HOME`.
REAL_RELEASE_CACHE = release_source.cache_root()


def _cache_listing(cache: Path) -> dict[str, tuple]:
    """`{entry: (its `complete` marker's bytes and mtime)}` for a cache root:
    enough to see an entry added, replaced or refetched."""
    listing = {}
    if cache.is_dir():
        for entry in sorted(cache.iterdir()):
            marker = entry / "complete"
            listing[entry.name] = ((marker.read_bytes(), marker.stat().st_mtime_ns)
                                   if marker.is_file() else None)
    return listing


class TestScratchReleaseIsolation(_CliCase):
    """Plan 7.2.1: a scratch run primes and tests only its own pinned `0.0.1`,
    from its own source into its own cache; the real pins never leak into it
    and the real cache is untouched."""

    def test_a_scratch_run_primes_and_tests_only_its_own_pin(self):
        before = _cache_listing(REAL_RELEASE_CACHE)
        scratch = scratch_checkout(self.tmp / "scratch")
        proc = run_cli(scratch, "--results", self.tmp / "r", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr)
        frozen = {u for u in _results(self.tmp / "r") if u.startswith("frozen:")}
        self.assertTrue(frozen)
        self.assertEqual({inventory.split_frozen_unit_id(u)[0] for u in frozen}, {"0.0.1"})
        private = Path(scratch_release_env(scratch)[release_source.CACHE_ENV])
        self.assertEqual(sorted(p.name for p in private.iterdir()), ["0.0.1", "0.0.1.lock"])
        self.assertEqual(_cache_listing(REAL_RELEASE_CACHE), before)
        self.assertNotIn("0.0.1", before)

    def test_a_pin_that_cannot_be_primed_is_exit_2_naming_the_cache_and_the_source(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        shutil.rmtree(scratch_releases(scratch) / "source")
        env = scratch_release_env(scratch)
        proc = run_cli(scratch, "--list", env=self.env)
        assert_refusal(self, proc.returncode, proc.stderr, "PrimingError")
        self.assertIn(env[release_source.CACHE_ENV], proc.stderr)
        self.assertIn(env[release_source.SOURCE_ENV], proc.stderr)
        self.assertIn("ReleaseUnavailableError", proc.stderr)

    def test_the_scratch_exclusive_lock_holds_tools_a_tree_that_outlives_cp6(self):
        declared = SCRATCH_RESOURCES["resources"]["repo:tools"]["paths"]
        self.assertEqual(declared, ["tools/"])
        self.assertIn("tools/", resources.GUARDED_TREES)


class TestTestTreeHygiene(_CliCase):

    def test_the_scratch_checkout_refuses_the_real_one_and_builds_a_release(self):
        for root in (REPO_ROOT, REPO_ROOT / "tests" / "scratch-here"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                scratch_checkout(root)
        scratch = scratch_checkout(self.tmp / "scratch")
        self.assertNotEqual(isolation.git_dir(scratch), isolation.git_dir(REPO_ROOT))
        # `support.release` in the scratch's own environment resolves its one
        # pin through its own source and cache, never the real ones.
        env = scratch_release_env(scratch)
        proc = subprocess.run(
            [sys.executable, "-B", "-c", "import json, support; r = support.release('0.0.1'); "
             "print(json.dumps([support.PINNED_VERSIONS, r.version, r.verify(), r.source]))"],
            cwd=str(scratch / "tests"), capture_output=True, text=True,
            env={**os.environ, **env})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [["0.0.1"], "0.0.1", [], {
            "kind": "package", "repository": "scratch/workflow",
            "archive": "workflow-0.0.1.tar.gz",
            "sha256": release_source.load_pins(
                scratch / "src" / "workflow_manager" / "published_releases.json"
            ).get("0.0.1").sha256}])
        cache = Path(env[release_source.CACHE_ENV])
        self.assertTrue((cache / "0.0.1" / "complete").is_file())
        self.assertFalse((release_source.cache_root() / "0.0.1").exists())
        pins = release_source.load_pins(scratch / "src" / "workflow_manager" /
                                        "published_releases.json")
        release = release_source.ReleaseCache(
            cache, release_source.ReleaseSource(env[release_source.SOURCE_ENV]),
            pins).resolve("0.0.1")
        self.addCleanup(release.close)
        repo = build_conformance_repo(release, self.tmp / "fixture")
        self.assertTrue((repo / "scripts" / "tiny_test.py").is_file())
        self.assertEqual(support.run_suite(repo, "tiny_test.py").returncode, 0)

    def test_every_lock_reaching_call_in_this_module_is_rooted_at_a_scratch_checkout(self):
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertEqual(lock_reach_violations(source), [])

    def test_the_scan_catches_each_mutation(self):
        source = Path(__file__).read_text(encoding="utf-8")
        mutants = {
            "a lock call on REPO_ROOT":
                f"\n\ndef _mutant():\n    isolation.{LOCK_FUNCS[0]}(REPO_ROOT)\n",
            "cli.main on the real root":
                f"\n\ndef _mutant():\n    cli.{CLI_ENTRY}([], repo_root=REPO_ROOT)\n",
            "an unbound scratch_root call site":
                "\n\ndef _mutant():\n    run_cli(TESTS_DIR.parent, '--list', env={})\n",
            "a clone of the real checkout":
                "\n\ndef _mutant():\n    run_cli(scratch_clone(REPO_ROOT), '--list', env={})\n",
            "a -c string calling the lock":
                "\n\n_MUTANT = " + repr(f"import parallel.isolation as i; i.{LOCK_FUNCS[0]}(r)")
                + "\n",
            "the real run_all.py outside a pre-lock test":
                "\n\ndef _mutant():\n    subprocess.run([sys.executable, str(TESTS_DIR / "
                "'run_all.py')])\n",
        }
        for label, text in mutants.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(lock_reach_violations(source + text), [])


# -- T-EXE-8: a shard refuses a plan for another plan digest or tree ----------------------

class TestRunShardProvenance(_CliCase):

    def test_run_shard_refuses_a_foreign_plan(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        plan = _plan_only(self, scratch)
        tampered = run_cli(scratch, "--run-shard", "0", "--plan", _tampered(plan),
                           "--results", self.tmp / "r1", env=self.env)
        assert_refusal(self, tampered.returncode, tampered.stderr, "PlanDigestMismatchError")
        (scratch / "tests" / "untracked.txt").write_text("another tree")
        foreign = run_cli(scratch, "--run-shard", "0", "--plan", plan,
                          "--results", self.tmp / "r2", env=self.env)
        assert_refusal(self, foreign.returncode, foreign.stderr, "TreeDigestMismatchError")

    def test_shards_and_the_aggregate_round_trip(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        plan = _plan_only(self, scratch, "--profile", "ci", "--shards", "2")
        self.assertEqual(json.loads(plan.read_text())["n"], 2)
        out = self.tmp / "out"
        for index in (0, 1):
            proc = run_cli(scratch, "--run-shard", index, "--plan", plan,
                           "--results", out / f"shard-{index}", env=self.env)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        summary = self.tmp / "summary.md"
        proc = run_cli(scratch, "--aggregate", out, "--plan", plan,
                       env=dict(self.env, GITHUB_STEP_SUMMARY=str(summary)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("verdict: exit 0", summary.read_text())
        self.assertIn("B  host:test_scratch_matrix.py::TestScratchMatrix", proc.stdout)

        # An unwritable step summary is a warning after the report, never exit 2.
        blocked = run_cli(scratch, "--aggregate", out, "--plan", plan,
                          env=dict(self.env, GITHUB_STEP_SUMMARY=str(self.tmp / "no" / "s.md")))
        self.assertEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("verdict: exit 0", blocked.stdout)
        self.assertIn("warning: could not write the step summary", blocked.stderr)

        shutil.move(str(out / "shard-1"), str(self.tmp / "held-back"))
        missing = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        assert_refusal(self, missing.returncode, missing.stderr, "IncompleteResultsError")
        shutil.move(str(self.tmp / "held-back"), str(out / "shard-1"))
        doc_path = out / "shard-1" / "shard-1.json"
        doc = json.loads(doc_path.read_text())
        doc["plan_digest"] = "0" * 64
        doc_path.write_text(canonical_json(doc))
        foreign = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        assert_refusal(self, foreign.returncode, foreign.stderr, "ForeignResultsError")


# -- T-EXE-9: executor-level faults -------------------------------------------------------

class TestExecutorLevelFaults(_CliCase):

    def test_a_chunk_past_its_timeout_is_killed_and_named(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={"test_scratch_sleep.py": SLEEP_MODULE})
        with mock.patch.object(isolation, "TIMEOUT_FLOOR", 2), \
                mock.patch.object(isolation, "TIMEOUT_CAP", 2):
            started = time.monotonic()
            code, out, err = main_in_process(scratch, "--select", "test_scratch_sleep.py")
        self.assertLess(time.monotonic() - started, 60)
        assert_refusal(self, code, err, "InfrastructureFaultError")
        self.assertIn("host:test_scratch_sleep.py::TestScratchSleep: timed_out", err)
        self.assertFalse(any(not _writable(m) for m in _guarded_modes(scratch).values()))

    def test_a_chunk_that_exits_without_a_record_is_named(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={"test_scratch_crash.py": CRASH_MODULE})
        code, out, err = main_in_process(scratch, "--select", "test_scratch_crash.py")
        assert_refusal(self, code, err, "InfrastructureFaultError")
        self.assertIn("host:test_scratch_crash.py::TestScratchCrash: missing_record", err)

    def test_a_persistent_writer_fails_the_run_at_step_6_and_is_attributed(self):
        scratch = scratch_checkout(self.tmp / "scratch",
                                   modules={"test_scratch_writer.py": WRITER_MODULE})
        code, out, err = main_in_process(scratch, "--select", "test_scratch_writer.py",
                                         "--select", "test_scratch_shared.py")
        assert_refusal(self, code, err, "IntegrityError")
        self.assertIn("tools/.keep changed during the run", err)
        self.assertIn("host:test_scratch_writer.py::TestScratchWriter", err)


# -- T-EXE-10: the exclusive unit never waits, whatever the load --------------------------

class TestExclusiveWaitUnderLoad(_CliCase):
    WORKERS, PER_WORKER = 16, 50

    def _load(self, exclusive_seconds: float) -> dict:
        """`scratch_checkout` options: 16 x 50 shared units of 1.0-1.2 s and the
        exclusive unit at `exclusive_seconds` -- placed first by LPT (shard 0)
        when it is the largest, last (shard 15) when it is the smallest."""
        count = self.WORKERS * self.PER_WORKER
        units = {f"host:test_scratch_load.py::TestLoad{i:03d}": 1.0 + (i % 3) / 10
                 for i in range(count)}
        units[SCRATCH_EXCLUSIVE_UNIT] = exclusive_seconds
        return {"modules": {"test_scratch_load.py": _trivial_module("Load", count)},
                "timings_units": units}

    def test_the_exclusive_unit_starts_first_and_alone_whatever_its_shard(self):
        shards = set()
        for exclusive_seconds in (2.0, 0.5):
            with self.subTest(exclusive_seconds=exclusive_seconds):
                scratch = scratch_checkout(self.tmp / f"scratch-{exclusive_seconds}",
                                           **self._load(exclusive_seconds))
                results_dir = self.tmp / f"r-{exclusive_seconds}"
                proc = run_cli(scratch, "--jobs", self.WORKERS, "--select", "test_scratch_load.py",
                               "--select", "test_scratch_exclusive.py", "--results", results_dir,
                               env=self.env)
                self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr)
                plan = json.loads((results_dir / "plan.json").read_text())
                self.assertEqual(plan["n"], self.WORKERS)
                shared = [len([c for c in s["chunks"] if not c["resources"]])
                          for s in plan["shards"]]
                self.assertEqual(sum(shared), self.WORKERS * self.PER_WORKER)
                self.assertTrue(all(abs(n - self.PER_WORKER) <= 1 for n in shared), shared)
                units = _results(results_dir)
                exclusive = units.pop(SCRATCH_EXCLUSIVE_UNIT)
                shards.add(exclusive["shard"])
                self.assertEqual(exclusive["phase"], "A0")
                first_shared = min(u["window"][0] for u in units.values())
                self.assertLessEqual(exclusive["window"][1], first_shared)
                self.assertIn("A0 (exclusive, alone): 1 chunk(s)", proc.stdout)
        self.assertEqual(len(shards), 2, "the exclusive unit's shard index was not varied")

    def test_in_a_single_shard_the_exclusive_unit_runs_first(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        proc = run_cli(scratch, "--jobs", "1", "--select", "test_scratch_shared.py",
                       "--select", "test_scratch_exclusive.py", "--results", self.tmp / "r",
                       env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        units = _results(self.tmp / "r")
        self.assertLessEqual(units[SCRATCH_EXCLUSIVE_UNIT]["window"][1],
                             units[SCRATCH_SHARED_UNIT]["window"][0])

    def test_the_aggregator_refuses_a_doctored_overlapping_window(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        plan = _plan_only(self, scratch, "--profile", "ci", "--shards", "1",
                          "--select", "test_scratch_shared.py",
                          "--select", "test_scratch_exclusive.py")
        out = self.tmp / "out"
        proc = run_cli(scratch, "--run-shard", "0", "--plan", plan, "--results", out / "s0",
                       env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        honest = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        self.assertEqual(honest.returncode, 0, honest.stdout + honest.stderr)
        doc_path = out / "s0" / "shard-0.json"
        doc = json.loads(doc_path.read_text())
        by_unit = {r["chunk"]["units"][0]: r for r in doc["results"]}
        shared = by_unit[SCRATCH_SHARED_UNIT]
        by_unit[SCRATCH_EXCLUSIVE_UNIT]["ended_at"] = shared["started_at"] + 0.01
        doc_path.write_text(canonical_json(doc))
        doctored = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        assert_refusal(self, doctored.returncode, doctored.stderr, "ExclusiveOverlapError")


# -- T-EXE-11: the lock, recovery and linked worktrees through the CLI --------------------

class TestLockAndRecoveryThroughTheCli(_CliCase):

    def _wait_for_chunk(self, scratch_root, process) -> list[int]:
        def running():
            return bool(_lock_holder(scratch_root).get("chunk_pgids")) or process.poll() is not None
        self.assertTrue(_wait_until(running, 60), "the chunk never started")
        if process.poll() is not None:
            self.fail(f"the executor exited early: {process.communicate()}")
        return _lock_holder(scratch_root)["chunk_pgids"]

    def test_a_killed_executor_keeps_the_checkout_locked_until_its_chunk_exits(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={"test_scratch_wait.py": WAIT_MODULE})
        pre_modes = _guarded_modes(scratch)
        stop = self.tmp / "stop"
        executor_proc = start_cli(scratch, "--select", "test_scratch_wait.py",
                                  env=dict(self.env, WM_SCRATCH_STOP=str(stop)))
        try:
            pgid = self._wait_for_chunk(scratch, executor_proc)[0]
            os.kill(executor_proc.pid, signal.SIGKILL)
            executor_proc.communicate(timeout=30)
            for argv in (("--list",), ("--restore-barrier",)):
                with self.subTest(argv=argv):
                    proc = run_cli(scratch, *argv, env=self.env)
                    assert_refusal(self, proc.returncode, proc.stderr, "RunLockHeldError")
                    self.assertIn(f"kill -- -{pgid}", proc.stderr)
            self.assertFalse(any(_writable(m) for m in _guarded_modes(scratch).values()))
            self.assertTrue((isolation.state_dir(scratch) / "barrier.json").exists())
        finally:
            stop.write_text("")
        self.assertTrue(_wait_until(lambda: not _lock_holder(scratch).get("chunk_pgids")
                                    or _dead(pgid), 60))
        recovered = None
        deadline = time.monotonic() + 30
        while recovered is None or recovered.returncode != 0:
            self.assertLess(time.monotonic(), deadline, recovered and recovered.stderr)
            recovered = run_cli(scratch, "--restore-barrier", env=self.env)
            time.sleep(0.1)
        self.assertIn("recovered a write barrier", recovered.stdout)
        self.assertEqual(_guarded_modes(scratch), pre_modes)
        self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())
        again = run_cli(scratch, "--restore-barrier", env=self.env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("no write barrier to restore", again.stdout)

    def test_sigterm_and_sigint_kill_the_chunk_restore_the_barrier_and_exit_2(self):
        """Self-review: `_install_signal_handlers`/`Engine.interrupt` had no
        test; only SIGKILL did."""
        for signum in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=signum.name):
                scratch = scratch_checkout(self.tmp / signum.name,
                                           modules={"test_scratch_wait.py": WAIT_MODULE})
                pre_modes = _guarded_modes(scratch)
                stop = self.tmp / f"stop-{signum.name}"   # only the signal ends the chunk
                proc = start_cli(scratch, "--select", "test_scratch_wait.py",
                                 env=dict(self.env, WM_SCRATCH_STOP=str(stop)))
                try:
                    pgid = self._wait_for_chunk(scratch, proc)[0]
                    self.assertFalse(any(_writable(m) for m in _guarded_modes(scratch).values()))
                    os.kill(proc.pid, signum)
                    out, err = proc.communicate(timeout=60)
                finally:
                    stop.write_text("")
                assert_refusal(self, proc.returncode, err, "InterruptedRunError")
                self.assertTrue(_dead(pgid))
                self.assertEqual(_guarded_modes(scratch), pre_modes)
                self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())
                again = run_cli(scratch, "--restore-barrier", env=self.env)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertIn("no write barrier to restore", again.stdout)

    def test_a_root_run_with_allow_root_is_flagged_in_the_report(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        with mock.patch("os.geteuid", return_value=0):
            code, out, err = main_in_process(scratch, "--allow-root",
                                             "--select", "test_scratch_shared.py")
        self.assertEqual(code, 0, out + err)
        self.assertIn("running as root (--allow-root)", out.split("\nshards: ", 1)[1])

    def test_a_root_run_without_allow_root_is_refused(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        pre_modes = _guarded_modes(scratch)
        with mock.patch("os.geteuid", return_value=0):
            code, out, err = main_in_process(scratch, "--select", "test_scratch_shared.py")
        assert_refusal(self, code, err, "RootRefusedError")
        self.assertEqual(_guarded_modes(scratch), pre_modes)

    def test_a_second_executor_in_one_checkout_is_refused_in_every_mode(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={"test_scratch_wait.py": WAIT_MODULE})
        pre_modes = _guarded_modes(scratch)
        stop = self.tmp / "stop"
        first = start_cli(scratch, "--select", "test_scratch_wait.py",
                          env=dict(self.env, WM_SCRATCH_STOP=str(stop)))
        try:
            self._wait_for_chunk(scratch, first)
            applied = _guarded_modes(scratch)
            marker = (isolation.state_dir(scratch) / "barrier.json").read_bytes()
            self.assertFalse(any(_writable(m) for m in applied.values()))
            for argv in (("--list",), ("--plan-only", "--out", self.tmp / "p.json"),
                         ("--restore-barrier",), ("--select", "test_scratch_shared.py")):
                with self.subTest(argv=argv):
                    proc = run_cli(scratch, *argv, env=self.env)
                    assert_refusal(self, proc.returncode, proc.stderr, "RunLockHeldError")
                    self.assertEqual(proc.stdout, "")
                    self.assertEqual(_guarded_modes(scratch), applied)
                    self.assertEqual((isolation.state_dir(scratch) / "barrier.json").read_bytes(),
                                     marker)
            self.assertFalse((self.tmp / "p.json").exists())
        finally:
            stop.write_text("")
        out, err = first.communicate(timeout=120)
        self.assertEqual(first.returncode, 0, out + err)
        self.assertEqual(_guarded_modes(scratch), pre_modes)
        self.assertFalse((isolation.state_dir(scratch) / "barrier.json").exists())

    def test_linked_worktrees_run_concurrently_and_never_touch_each_other(self):
        scratch = scratch_checkout(self.tmp / "scratch", modules={"test_scratch_wait.py": WAIT_MODULE})
        worktree = scratch_worktree(scratch)
        main_modes, wt_modes = _guarded_modes(scratch), _guarded_modes(worktree)
        stops = {"main": self.tmp / "stop-main", "wt": self.tmp / "stop-wt"}
        main_run = start_cli(scratch, "--select", "test_scratch_wait.py",
                             env=dict(self.env, WM_SCRATCH_STOP=str(stops["main"])))
        wt_run = start_cli(worktree, "--select", "test_scratch_wait.py",
                           env=dict(self.env, WM_SCRATCH_STOP=str(stops["wt"])))
        try:
            self._wait_for_chunk(scratch, main_run)
            self._wait_for_chunk(worktree, wt_run)
            self.assertFalse(any(_writable(m) for m in _guarded_modes(scratch).values()))
            self.assertFalse(any(_writable(m) for m in _guarded_modes(worktree).values()))
            stops["main"].write_text("")
            out, err = main_run.communicate(timeout=120)
            self.assertEqual(main_run.returncode, 0, out + err)
            self.assertEqual(_guarded_modes(scratch), main_modes)
            self.assertFalse(any(_writable(m) for m in _guarded_modes(worktree).values()))
            self.assertTrue((isolation.state_dir(worktree) / "barrier.json").exists())
        finally:
            for stop in stops.values():
                stop.write_text("")
        out, err = wt_run.communicate(timeout=120)
        self.assertEqual(wt_run.returncode, 0, out + err)
        self.assertEqual(_guarded_modes(worktree), wt_modes)


# -- CP5 unit-level pieces ------------------------------------------------------------------

class TestExecutorPieces(unittest.TestCase):

    def test_a_chunk_result_round_trips(self):
        chunk = plan_schema.ChunkDescriptor("c", 1, ("host:test_a.py::A",), 2.0, ("r",))
        result = executor.ChunkResult(chunk, "A0", 1, "host", "passed", 1.0, 2.5, 0,
                                      {"passed": True}, "/log", "", ("x",),
                                      ({"pid": 7, "cmdline": "[git]", "fate": "exited"},),
                                      "linux", True, None)
        again = executor.ChunkResult.from_json(json.loads(json.dumps(result.to_json())))
        self.assertEqual(again, result)
        self.assertEqual(again.window, isolation.Window("c", 1.0, 2.5, True))
        with self.assertRaises(executor.IncompleteResultsError):
            executor.ChunkResult.from_json({"chunk": chunk.to_json()})

    def test_an_unknown_outcome_in_received_results_is_refused(self):
        """Self-review: `verdict_of` counted an outcome it does not know as a
        pass, so an edited shard artifact could turn the aggregate green."""
        chunk = plan_schema.ChunkDescriptor("c", 0, ("host:test_a.py::A",), 1.0)
        doc = executor.ChunkResult(chunk, "A", 0, "host", "failed", platform="linux",
                                   supported=True).to_json()
        self.assertEqual(executor.ChunkResult.from_json(doc).outcome, "failed")
        with self.assertRaises(executor.IncompleteResultsError):
            executor.ChunkResult.from_json({**doc, "outcome": "skipped"})

    def test_the_verdict_precedence(self):
        chunk = plan_schema.ChunkDescriptor("c", 0, ("host:test_a.py::A",), 1.0)
        frozen = plan_schema.ChunkDescriptor("f", 0, ("frozen:1.0.0/conformance/s.py::K",), 1.0)

        def result(outcome, c=chunk, kind="host"):
            return executor.ChunkResult(c, "A", 0, kind, outcome)
        never = lambda r: False  # noqa: E731
        always = lambda r: True  # noqa: E731
        self.assertEqual(executor.verdict_of([result("passed")], never).code, 0)
        self.assertEqual(executor.verdict_of([result("failed")], never).code, 1)
        self.assertEqual(executor.verdict_of([result("failed", frozen, "frozen")], always).code, 0)
        self.assertEqual(executor.verdict_of([result("failed", frozen, "frozen")], never).code, 1)
        mixed = executor.verdict_of([result("failed"), result("timed_out")], never)
        self.assertEqual((mixed.code, len(mixed.failures)), (2, 1))
        self.assertEqual(executor.verdict_of([result("passed")], never,
                                             extra_faults=[("IntegrityError", "x")]).code, 2)

    def test_tmpdir_residue_is_reported_against_its_chunk(self):
        plan = {"n": 1, "profile": "local", "shards": [{"load": 1.0}], "timing": {},
                "predicted": {"total_work": 1.0, "critical_path": 1.0,
                              "critical_path_chunk": "c", "makespan": {"total": 1.0}}}
        chunk = plan_schema.ChunkDescriptor("c", 0, ("host:test_a.py::A",), 1.0)
        clean = executor.ChunkResult(chunk, "A", 0, "host", "passed", 1.0, 2.0)
        dirty = executor.ChunkResult(chunk, "A", 0, "host", "passed", 1.0, 2.0,
                                     tmp_residue=("stray.txt",))
        self.assertIn("  TMPDIR residue: none",
                      report.shard_summary(plan, [clean], wall=1.0, drifted=[]))
        lines = report.shard_summary(plan, [dirty], wall=1.0, drifted=[])
        self.assertIn("  TMPDIR residue (removed): 1 chunk(s)", lines)
        self.assertIn("    c: stray.txt", lines)
        doc = json.loads(report.results_doc([dirty], 0, {}))
        self.assertEqual(doc["units"]["host:test_a.py::A"]["tmp_residue"], ["stray.txt"])

    def test_an_observation_read_twice_counts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = {"chunk_id": "c", "version": "1.0.0", "fixture": "conformance",
                      "suite": "s.py", "classes": ["K"], "returncode": 0,
                      "output": "Ran 1 test in 0.5s\n", "timed_out": False, "build_error": None,
                      "duration": 1.0, "started_at": 100.0, "tree_digest": "T"}
            (Path(tmp) / "frozen-records").mkdir()
            (Path(tmp) / "frozen-records" / "c.record.json").write_text(json.dumps(record))
            with open(Path(tmp) / "timings.jsonl", "w") as handle:
                for obs in timings.observations_from_record(record, "local"):
                    handle.write(obs.to_json_line())
            found = timings.read_observations([tmp], "local")
        self.assertEqual(len(found), 2)


# == CP6: the CI pipeline (T-CI-1..5) =====================================================

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "workflow-manager-verify.yml"
MANAGED_WORKFLOW = ".github/workflows/workflow-conformance.yml"
CI_JOBS = ("plan", "shard", "aggregate")
#: The job every run holds besides `CI_JOBS`: the release's build-and-verify path.
CI_PACKAGE_JOB = "package"
#: The nightly full run of the default branch (plan 6.4).
CI_SCHEDULE = [{"cron": "17 3 * * *"}]
#: The concurrency group: per ref for a pull request, per event and commit for
#: every other run, so no `main` commit's run is ever cancelled (plan 6.4).
CI_CONCURRENCY_GROUP = ("workflow-manager-verify-${{ github.event_name }}-${{ github.event_name "
                        "== 'pull_request' && github.ref || github.sha }}")
#: The aggregate's first step, which fails it when `plan` or `package` did not succeed.
CI_NEEDS_STEP = "needs"
CI_MATRIX = "${{ fromJSON(needs.plan.outputs.shards) }}"
#: The release cache every test job primes (plan 7.1, 7.3): its directory, and
#: the `actions/cache` inputs that restore it, keyed on the pins.
CI_RELEASE_CACHE = "${{ runner.temp }}/workflow-manager-releases"
CI_RELEASE_CACHE_INPUTS = {
    "path": CI_RELEASE_CACHE,
    "key": "workflow-releases-${{ hashFiles('src/workflow_manager/published_releases.json') }}"}
#: `run_all.py`'s path flags, each of which must name a path under `$RUNNER_TEMP`.
CI_PATH_FLAG_RE = re.compile(r'(--(?:out|plan|results|aggregate))\s+("[^"]*"|\S+)')
_YAML_KEY_RE = re.compile(r"([A-Za-z0-9_.-]+):(?: +(.*))?$")


def load_workflow_yaml(text: str):
    """The block-style YAML subset the workflow is written in -- mappings, `- `
    sequences, `|` literal blocks, one-line `[a, b]` lists and plain or
    quoted scalars -- with the stdlib only. Anything outside the subset (tabs,
    anchors, aliases, tags, flow mappings, folded blocks, trailing comments,
    duplicate keys) is refused rather than misread."""
    lines = text.splitlines()
    pos = 0

    def refuse(message):
        raise ValueError(f"line {pos + 1}: {message}")

    def indent(line):
        return len(line) - len(line.lstrip(" "))

    def skip():
        nonlocal pos
        while pos < len(lines) and (not lines[pos].strip() or lines[pos].lstrip().startswith("#")):
            pos += 1

    def scalar(raw):
        raw = raw.strip()
        if not raw or raw in ("~", "null"):
            return None
        if raw[0] in "&*!{>|%@`":
            refuse(f"unsupported YAML: {raw!r}")
        if raw[0] in "\"'":
            if len(raw) < 2 or raw[-1] != raw[0]:
                refuse(f"unterminated or trailing text after a quoted scalar: {raw!r}")
            return raw[1:-1]
        if " #" in raw:
            refuse(f"trailing comment: {raw!r}")
        if raw[0] == "[":
            if raw[-1] != "]":
                refuse(f"unterminated list: {raw!r}")
            return [scalar(part) for part in raw[1:-1].split(",") if part.strip()]
        if raw in ("true", "false"):
            return raw == "true"
        if re.fullmatch(r"-?[0-9]+", raw):
            return int(raw)
        return raw

    def literal(level):
        nonlocal pos
        body, inner = [], None
        while pos < len(lines):
            line = lines[pos]
            if line.strip():
                if indent(line) <= level:
                    break
                inner = indent(line) if inner is None else inner
                if indent(line) < inner:
                    refuse("a literal block dedents below its first line")
                body.append(line[inner:])
            else:
                body.append("")
            pos += 1
        if inner is None:
            refuse("empty literal block")
        while not body[-1]:
            body.pop()
        return "\n".join(body) + "\n"

    def value(rest, level):
        if rest == "|":
            return literal(level)
        if rest:
            return scalar(rest)
        skip()
        if pos < len(lines) and indent(lines[pos]) > level:
            return block(indent(lines[pos]))
        if pos < len(lines) and indent(lines[pos]) == level and \
                lines[pos][level:].startswith("- "):
            return sequence(level)
        return None

    def block(level):
        return sequence(level) if lines[pos][level:].startswith("- ") else mapping(level)

    def mapping(level):
        nonlocal pos
        out = {}
        while True:
            skip()
            if pos >= len(lines) or indent(lines[pos]) < level:
                return out
            line = lines[pos]
            if "\t" in line:
                refuse("tab character")
            if indent(line) != level:
                refuse(f"unexpected indentation: {line!r}")
            match = _YAML_KEY_RE.match(line[level:])
            if not match:
                refuse(f"not a mapping entry: {line.strip()!r}")
            key = match.group(1)
            if key in out:
                refuse(f"duplicate key {key!r}")
            pos += 1
            out[key] = value(match.group(2) or "", level)

    def sequence(level):
        nonlocal pos
        items = []
        while True:
            skip()
            if pos >= len(lines) or indent(lines[pos]) != level or \
                    not lines[pos][level:].startswith("- "):
                return items
            content = lines[pos][level + 2:]
            if _YAML_KEY_RE.match(content):
                # `- key: value` opens a mapping whose keys align with `key`.
                lines[pos] = " " * (level + 2) + content
                items.append(mapping(level + 2))
            else:
                pos += 1
                items.append(scalar(content))

    doc = mapping(0)
    skip()
    if pos < len(lines):
        refuse(f"unparsed content: {lines[pos]!r}")
    return doc


#: The single-shard CI reference's measured job time (CP6, run 36318597506:
#: 110.8 minutes) with a margin.
CI_SERIAL_SHARD_MINUTES = 150


def ci_workflow() -> dict:
    return load_workflow_yaml(CI_WORKFLOW.read_text(encoding="utf-8"))


def ci_run_all_step(doc: dict, job: str) -> dict:
    """The one step of `job` that runs `tests/run_all.py`."""
    steps = [s for s in doc["jobs"][job]["steps"] if "tests/run_all.py" in (s.get("run") or "")]
    if len(steps) != 1:
        raise AssertionError(f"{job}: {len(steps)} steps run tests/run_all.py, not 1")
    return steps[0]


def ci_job_steps(job: dict) -> list[dict]:
    """A job's steps after the aggregate's leading `needs` check, if any."""
    steps = job.get("steps") or []
    return steps[1:] if steps and steps[0].get("id") == CI_NEEDS_STEP else steps


def ci_workflow_problems(doc: dict) -> list[str]:
    """T-CI-1's structural checks over the parsed workflow; `[]` when it holds."""
    problems = []

    def need(condition, message):
        if not condition:
            problems.append(message)

    triggers = doc.get("on") or {}
    need(sorted(triggers) == ["pull_request", "push", "schedule", "workflow_dispatch"],
         f"triggers are {sorted(triggers)} (pull_request, push to main, the nightly schedule, "
         f"dispatch)")
    need((triggers.get("push") or {}).get("branches") == ["main"], "push is not limited to main")
    need(triggers.get("schedule") == CI_SCHEDULE,
         f"the schedule is {triggers.get('schedule')!r}, not {CI_SCHEDULE}")
    concurrency = doc.get("concurrency") or {}
    need(concurrency.get("group") == CI_CONCURRENCY_GROUP,
         f"the concurrency group is {concurrency.get('group')!r}, not the per-commit one of main")
    need(concurrency.get("cancel-in-progress") == "${{ github.event_name == 'pull_request' }}",
         "cancel-in-progress is not limited to pull requests")
    need("env" not in doc, "the workflow has a global env (M2 removed the upstream fetch's)")

    jobs = doc.get("jobs") or {}
    need(set(CI_JOBS) | {CI_PACKAGE_JOB} <= set(jobs),
         f"jobs are {sorted(jobs)}, missing {sorted(set(CI_JOBS) | {CI_PACKAGE_JOB} - set(jobs))}")
    plan, shard, aggregate = ((jobs.get(name) or {}) for name in CI_JOBS)
    for name in CI_JOBS:
        minutes = (jobs.get(name) or {}).get("timeout-minutes")
        need(isinstance(minutes, int) and 0 < minutes < 360,
             f"{name}: timeout-minutes is {minutes!r}, not below GitHub's 360-minute default")
    need((shard.get("timeout-minutes") or 0) >= CI_SERIAL_SHARD_MINUTES,
         f"the shard timeout would kill the single-shard reference "
         f"(about {CI_SERIAL_SHARD_MINUTES} minutes)")
    need((plan.get("outputs") or {}).get("shards") == "${{ steps.plan.outputs.shards }}",
         "the plan job does not export its plan step's shard list")
    strategy = shard.get("strategy") or {}
    need(strategy.get("matrix") == {"shard": CI_MATRIX},
         f"the shard matrix is {strategy.get('matrix')!r}, not exactly {CI_MATRIX}")
    need(strategy.get("fail-fast") is False, "the shard matrix is not fail-fast: false")
    need(shard.get("needs") == "plan", "the shard job does not need the plan job")
    need(aggregate.get("needs") == ["plan", "shard", CI_PACKAGE_JOB],
         "aggregate does not need [plan, shard, package]")
    need(aggregate.get("if") == "always()", "aggregate does not run if: always()")

    modes = {"plan": "--plan-only --profile ci", "shard": "--run-shard", "aggregate": "--aggregate"}
    for name in CI_JOBS:
        job = jobs.get(name) or {}
        steps = ci_job_steps(job)
        need([s.get("uses") for s in steps[:2]] == ["actions/checkout@v4", "actions/setup-python@v5"],
             f"{name}: does not start with checkout and setup-python")
        need(len(steps) > 1 and steps[1].get("with") == {"python-version": "3.12"},
             f"{name}: python is not 3.12")
        need(bool(steps) and "with" not in steps[0],
             f"{name}: the checkout is configured (no test needs history since M2)")
        # GitHub has no `runner` context in a job-level `env`: a job that sets
        # the cache there is rejected with the whole workflow (functional
        # finding F1). The step that runs the tests sets it instead.
        need("WORKFLOW_MANAGER_RELEASE_CACHE" not in (job.get("env") or {}),
             f"{name}: WORKFLOW_MANAGER_RELEASE_CACHE is set at job level, where GitHub has no runner context")
        test_steps = [s for s in steps if "tests/run_all.py" in (s.get("run") or "")]
        need(bool(test_steps) and all((s.get("env") or {}).get("WORKFLOW_MANAGER_RELEASE_CACHE")
                                      == CI_RELEASE_CACHE for s in test_steps),
             f"{name}: the run_all.py step does not set WORKFLOW_MANAGER_RELEASE_CACHE to {CI_RELEASE_CACHE}")
        restores = [i for i, s in enumerate(steps)
                    if (s.get("uses") or "").split("@")[0] == "actions/cache"]
        runners = [i for i, s in enumerate(steps) if "tests/run_all.py" in (s.get("run") or "")]
        need(len(restores) == 1 and steps[restores[0]].get("with") == CI_RELEASE_CACHE_INPUTS,
             f"{name}: the release cache is not restored exactly once, keyed on the pins")
        need(bool(restores) and bool(runners) and restores[0] < runners[0],
             f"{name}: the release cache is not restored before run_all.py primes it")
        runs = [s.get("run") or "" for s in steps]
        invocations = [line for run in runs for line in run.splitlines()
                       if "tests/run_all.py" in line]
        need(len(invocations) == 1, f"{name}: {len(invocations)} run_all.py invocations")
        for line in invocations:
            need(f"python3 tests/run_all.py {modes[name]}" in line,
                 f"{name}: run_all.py is not run with {modes[name]}")
            for flag, path in CI_PATH_FLAG_RE.findall(line):
                need(path.strip('"').startswith("$RUNNER_TEMP/"),
                     f"{name}: {flag} {path} is not under $RUNNER_TEMP")
        for run in runs:
            if "tests/run_all.py" in run:
                need('export TMPDIR="$RUNNER_TEMP/' in run.split("tests/run_all.py", 1)[0],
                     f"{name}: TMPDIR is not under $RUNNER_TEMP before run_all.py")
        for step in steps:
            if (step.get("uses") or "").split("@")[0] in ("actions/upload-artifact",
                                                        "actions/download-artifact"):
                need(str((step.get("with") or {}).get("path", "")).startswith("${{ runner.temp }}"),
                     f"{name}: artifact path {step.get('with')} is not under runner.temp")
        need(not any("UPSTREAM" in run for run in runs), f"{name}: fetches an upstream")

    # The single CI profile (M2 removed the pull-request stopgap).
    need(sorted(jobs) == sorted(CI_JOBS + (CI_PACKAGE_JOB,)),
         f"jobs are {sorted(jobs)}, not exactly plan, shard, package and aggregate")
    need(sorted(plan.get("outputs") or {}) == ["shards"], "the plan job exports more than shards")
    need("permissions" not in plan, "the plan job has its own permissions")
    need(len(plan.get("steps") or []) == 5,
         "the plan job is not checkout, python, cache, plan and upload")

    plan_steps = [s for s in plan.get("steps") or [] if s.get("id") == "plan"]
    need(len(plan_steps) == 1 and '"shards=' in plan_steps[0].get("run", "")
         and '>> "$GITHUB_OUTPUT"' in plan_steps[0].get("run", ""),
         "the plan step does not write shards= to $GITHUB_OUTPUT")
    uploads = [s for s in shard.get("steps") or []
               if (s.get("uses") or "").startswith("actions/upload-artifact@")]
    need(len(uploads) == 1 and uploads[0].get("if") == "always()",
         "the shard results are not uploaded if: always()")
    return problems


def _python3_on_path(directory: Path) -> str:
    """A `bin` directory whose `python3` is this interpreter, for PATH."""
    directory.mkdir(exist_ok=True)
    if not (directory / "python3").exists():
        (directory / "python3").symlink_to(sys.executable)
    return str(directory)


def run_ci_step(scratch_root, job: str, *, runner_temp: Path, env: dict, step_env: dict,
                github_env=None) -> subprocess.CompletedProcess:
    """Run the real workflow's `run_all.py` step of `job` verbatim, the way
    GitHub runs a `run:` step (`bash -e` with pipefail, in the checkout), in a
    scratch checkout with `runner_temp` standing in for `$RUNNER_TEMP`.
    `step_env` supplies the step's own `env:` values, key for key, except
    `WORKFLOW_MANAGER_RELEASE_CACHE`: the scratch checkout's private cache
    (`scratch_release_env`) always stands in for it."""
    scratch_root = Path(scratch_root)
    if _same_checkout_as_real(scratch_root):
        raise ValueError(f"run_ci_step refuses the real checkout: {scratch_root}")
    step = ci_run_all_step(ci_workflow(), job)
    if set(step_env) != set(step.get("env") or {}) - {release_source.CACHE_ENV}:
        raise AssertionError(f"{job}: the step's env is {sorted(step.get('env') or {})}, "
                             f"the test supplies {sorted(step_env)}")
    bin_dir = _python3_on_path(Path(runner_temp).parent / "bin")
    full = dict(env, RUNNER_TEMP=str(runner_temp), PATH=bin_dir + os.pathsep + env["PATH"],
                **step_env, **(github_env or {}), **scratch_release_env(scratch_root))
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                          cwd=str(scratch_root), capture_output=True, text=True, env=full,
                          timeout=600)


def ci_artifact_dir(doc: dict, shard: int) -> str:
    """The directory a shard's results land in under the aggregate's download
    path: the shard job's artifact name, checked against the pattern the
    aggregate job downloads."""
    upload = next(s for s in doc["jobs"]["shard"]["steps"]
                  if (s.get("uses") or "").startswith("actions/upload-artifact@"))
    name = upload["with"]["name"].replace("${{ matrix.shard }}", str(shard))
    patterns = [s["with"]["pattern"] for s in doc["jobs"]["aggregate"]["steps"]
                if "pattern" in (s.get("with") or {})]
    if len(patterns) != 1 or not fnmatch.fnmatchcase(name, patterns[0]):
        raise AssertionError(f"artifact {name!r} is not downloaded by the aggregate ({patterns})")
    return name


# -- T-CI-1: the workflow's structure -----------------------------------------------------

class TestCiWorkflowStructure(unittest.TestCase):

    def test_the_workflow_file_holds_every_structural_rule(self):
        self.assertEqual(ci_workflow_problems(ci_workflow()), [])

    def test_each_mutation_is_caught(self):
        text = CI_WORKFLOW.read_text(encoding="utf-8")
        mutants = {
            "a literal shard list": (CI_MATRIX, "[0, 1, 2]"),
            "fail-fast": ("fail-fast: false", "fail-fast: true"),
            "aggregate needs only the shards": ("needs: [plan, shard, package]", "needs: [shard]"),
            "aggregate skips the package": ("needs: [plan, shard, package]",
                                            "needs: [plan, shard]"),
            "no nightly run": (re.compile(r"^  schedule:\n    - cron: .*\n", re.M), ""),
            "a per-ref group for main": ("&& github.ref || github.sha }}", "}}-${{ github.ref }}"),
            "main's runs cancelled": ("cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
                                      "cancel-in-progress: true"),
            "aggregate skipped on failure": (re.compile(r"^    if: always\(\)$", re.M),
                                             "    if: success()"),
            "a results dir in the checkout": ('--results "$RUNNER_TEMP/out/"', "--results out/"),
            "a plan in the checkout": ('--out "$RUNNER_TEMP/plan.json"', "--out plan.json"),
            "TMPDIR left at /tmp": (re.compile(r'^ *export TMPDIR="\$RUNNER_TEMP/tmp"\n', re.M), ""),
            "an upstream again": ("\njobs:\n", "\nenv:\n  UPSTREAM_URL: x\n\njobs:\n"),
            "a job without the release cache": (
                "SHARDS: ${{ inputs.shards }}\n"
                "          WORKFLOW_MANAGER_RELEASE_CACHE: ${{ runner.temp }}/workflow-manager-releases\n",
                "SHARDS: ${{ inputs.shards }}\n"),
            "the release cache at job level again": (
                "  plan:\n    runs-on: ubuntu-latest\n",
                "  plan:\n    runs-on: ubuntu-latest\n    env:\n"
                "      WORKFLOW_MANAGER_RELEASE_CACHE: ${{ runner.temp }}/workflow-manager-releases\n"),
            "a cache key off the pins": ("hashFiles('src/workflow_manager/published_releases.json')",
                                         "hashFiles('pyproject.toml')"),
            "no cache restore before a run": (
                re.compile(r"^      - name: Restore the release cache\n(?:        .*\n)+", re.M), ""),
            "a nightly alarm again": ("\n  aggregate:\n", "\n  nightly-alarm:\n    runs-on: x\n"
                                      "\n  aggregate:\n"),
            "a profile output again": ("      shards: ${{ steps.plan.outputs.shards }}\n",
                                       "      shards: ${{ steps.plan.outputs.shards }}\n"
                                       "      profile: x\n"),
            "a push to any branch": ("    branches: [main]\n", ""),
            "a full-history checkout": ("      - uses: actions/checkout@v4\n      - uses",
                                        "      - uses: actions/checkout@v4\n        with:\n"
                                        "          fetch-depth: 0\n      - uses"),
            "an artifact path in the workspace": ("path: ${{ runner.temp }}/out/\n",
                                                  "path: out/\n"),
            # Review O9.
            "no plan timeout": ("    timeout-minutes: 30\n", ""),
            "a shard timeout too short for shards=1": ("timeout-minutes: 180",
                                                       "timeout-minutes: 60"),
        }
        for label, (old, new) in mutants.items():
            with self.subTest(mutation=label):
                mutated = old.sub(new, text, count=1) if isinstance(old, re.Pattern) \
                    else text.replace(old, new, 1)
                self.assertNotEqual(mutated, text, "the mutation did not apply")
                self.assertNotEqual(ci_workflow_problems(load_workflow_yaml(mutated)), [])

    def test_a_shard_count_beyond_the_matrix_limit_is_refused(self):
        """Review O9: the `shards` dispatch input is otherwise unbounded, and a
        matrix above GitHub's limit fails without saying why."""
        parser = cli.build_parser()
        for shards, refused in ((cli.CI_MATRIX_LIMIT, False), (cli.CI_MATRIX_LIMIT + 1, True)):
            with self.subTest(shards=shards):
                args = parser.parse_args(["--plan-only", "--profile", "ci", "--shards", str(shards)])
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    if refused:
                        with self.assertRaises(SystemExit) as ctx:
                            cli.validate(parser, args)
                        self.assertEqual(ctx.exception.code, 2)
                        self.assertIn("matrix limit", stderr.getvalue())
                    else:
                        self.assertEqual(cli.validate(parser, args), "plan_only")

    def test_the_parser_refuses_what_it_does_not_understand(self):
        for text in ("a: &x 1\n", "a: *x\n", "a: {b: 1}\n", "a: 1 # c\n", "a:\n\tb: 1\n",
                     "a: 1\na: 2\n", "a: >\n  folded\n", "a:\n  b: 1\n c: 2\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_workflow_yaml(text)
        self.assertEqual(load_workflow_yaml("a:\n  - x: 1\n    y: [p, q]\n  - z\nb: |\n  l1\n\n"
                                            "    l2\nc: 'q: r'\n"),
                         {"a": [{"x": 1, "y": ["p", "q"]}, "z"], "b": "l1\n\n  l2\n",
                          "c": "q: r"})


# -- T-CI-7: one required check, which also needs the package ---------------------------------

def run_needs_step(plan_result: str, package_result: str) -> subprocess.CompletedProcess:
    """The aggregate's `needs` step, verbatim, as GitHub runs a `run:` step."""
    step = ci_workflow()["jobs"]["aggregate"]["steps"][0]
    env = dict(os.environ, PLAN_RESULT=plan_result, PACKAGE_RESULT=package_result)
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                          capture_output=True, text=True, env=env, timeout=60)


class TestOneRequiredCheck(unittest.TestCase):

    def test_aggregate_needs_plan_shard_and_package_always(self):
        jobs = ci_workflow()["jobs"]
        aggregate = jobs["aggregate"]
        self.assertEqual(aggregate["needs"], ["plan", "shard", CI_PACKAGE_JOB])
        self.assertEqual(aggregate["if"], "always()")
        first = aggregate["steps"][0]
        self.assertEqual(first.get("id"), CI_NEEDS_STEP)
        self.assertEqual(first["env"], {"PLAN_RESULT": "${{ needs.plan.result }}",
                                        "PACKAGE_RESULT": "${{ needs.package.result }}"})
        # The shard jobs are never required by name: aggregate verifies their results.
        self.assertNotIn("name", aggregate)

    def test_a_non_success_plan_or_package_fails_it_naming_the_cause(self):
        self.assertEqual(run_needs_step("success", "success").returncode, 0)
        for plan_result, package_result, named in (
                ("failure", "success", "the plan job concluded failure"),
                ("success", "failure", "the package job concluded failure"),
                ("success", "cancelled", "the package job concluded cancelled"),
                ("skipped", "success", "the plan job concluded skipped")):
            with self.subTest(plan=plan_result, package=package_result):
                proc = run_needs_step(plan_result, package_result)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn(f"::error::{named}", proc.stdout)

    def test_the_package_job_is_the_releases_own_build_and_verify_path(self):
        package = ci_workflow()["jobs"][CI_PACKAGE_JOB]
        self.assertIsInstance(package.get("timeout-minutes"), int)
        self.assertLess(package["timeout-minutes"], 360)
        self.assertNotIn("needs", package)
        steps = package["steps"]
        self.assertEqual([s.get("uses") for s in steps[:2]],
                         ["actions/checkout@v4", "actions/setup-python@v5"])
        self.assertEqual(steps[1]["with"], {"python-version": "3.12"})
        run = "\n".join(s.get("run") or "" for s in steps)
        self.assertIn("python3 -m pip install -r .github/tools/requirements.txt", run)
        self.assertIn('python3 tools/release/package.py --version 0.0.0+ci '
                      '--out "$RUNNER_TEMP/dist"\n', run)
        self.assertNotIn("--manager-root", run, "the wheel resolves releases through its pins")
        self.assertNotIn("UPSTREAM_URL", run, "the package job needs no upstream")
        self.assertLess(run.index("pip install"), run.index("package.py"))
        # The release cache (plan 5.6): restored before the build, and named
        # to the build, so `verify` downloads only on a cache miss.
        cache_dir = "${{ runner.temp }}/workflow-manager-releases"
        restore = [i for i, s in enumerate(steps)
                   if (s.get("uses") or "").split("@")[0] == "actions/cache"]
        build = [i for i, s in enumerate(steps) if "package.py" in (s.get("run") or "")]
        self.assertEqual(len(restore), 1)
        self.assertEqual(len(build), 1)
        self.assertLess(restore[0], build[0])
        self.assertEqual(steps[restore[0]]["with"], {
            "path": cache_dir,
            "key": "workflow-releases-"
                   "${{ hashFiles('src/workflow_manager/published_releases.json') }}"})
        self.assertEqual(steps[build[0]]["env"], {"WORKFLOW_MANAGER_RELEASE_CACHE": cache_dir})

    def test_only_a_pull_request_run_is_cancelled(self):
        concurrency = ci_workflow()["concurrency"]
        self.assertEqual(concurrency["group"], CI_CONCURRENCY_GROUP)
        self.assertEqual(concurrency["cancel-in-progress"],
                         "${{ github.event_name == 'pull_request' }}")


# -- T-CI-2: the plan and shard jobs agree on the tree ---------------------------------------

class TestCiTreeIdentity(_CliCase):

    def test_the_workflow_steps_run_end_to_end_with_one_tree_digest(self):
        doc = ci_workflow()
        scratch = scratch_checkout(self.tmp / "scratch")
        plan_job = scratch_clone(scratch)
        temp = self.tmp / "rt-plan"
        temp.mkdir()
        github_output = temp / "github-output"
        proc = run_ci_step(plan_job, "plan", runner_temp=temp, env=self.env,
                           step_env={"SHARDS": "2"}, github_env={"GITHUB_OUTPUT": str(github_output)})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        plan = json.loads((temp / "plan.json").read_text())
        self.assertEqual(plan["tree_digest"], tree.tree_digest(plan_job))
        self.assertEqual(github_output.read_text(), "shards=[0,1]\n")

        downloads = self.tmp / "rt-aggregate" / "out"
        for index in json.loads(github_output.read_text().split("=", 1)[1]):
            shard_job = scratch_clone(scratch)
            self.assertEqual(tree.tree_digest(shard_job), plan["tree_digest"])
            shard_temp = self.tmp / f"rt-shard-{index}"
            shard_temp.mkdir()
            shutil.copy2(temp / "plan.json", shard_temp / "plan.json")
            proc = run_ci_step(shard_job, "shard", runner_temp=shard_temp, env=self.env,
                               step_env={"SHARD": str(index)})
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            summary = json.loads((shard_temp / "out" / f"shard-{index}.json").read_text())
            self.assertEqual(summary["tree_digest"], plan["tree_digest"])
            self.assertEqual(tree.tree_digest(shard_job), plan["tree_digest"],
                             "the shard wrote into its checkout")
            shutil.copytree(shard_temp / "out", downloads / ci_artifact_dir(doc, index))

        aggregate_job = scratch_clone(scratch)
        shutil.copy2(temp / "plan.json", downloads.parent / "plan.json")
        step_summary = self.tmp / "step-summary.md"
        proc = run_ci_step(aggregate_job, "aggregate", runner_temp=downloads.parent, env=self.env,
                           step_env={}, github_env={"GITHUB_STEP_SUMMARY": str(step_summary)})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("verdict: exit 0", step_summary.read_text())
        self.assertIn("B  host:test_scratch_matrix.py::TestScratchMatrix", proc.stdout)
        run_dirs = [p for p in (downloads.parent / "tmp").iterdir() if p.name.startswith("wm-run-")]
        self.assertEqual(len(run_dirs), 1, "the aggregate's run directory is not under "
                                           "$RUNNER_TEMP/tmp")
        self.assertTrue((run_dirs[0] / "results.json").is_file())
        for job in (plan_job, aggregate_job):
            self.assertEqual(tree.tree_digest(job), plan["tree_digest"])

    def test_outputs_placed_inside_the_checkout_are_refused(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        job = scratch_clone(scratch)
        inside = job / "runner-temp"
        inside.mkdir()
        proc = run_ci_step(job, "plan", runner_temp=inside, env=self.env, step_env={"SHARDS": ""},
                           github_env={"GITHUB_OUTPUT": str(self.tmp / "github-output")})
        assert_refusal(self, proc.returncode, proc.stderr, "PathInsideRepositoryError")
        self.assertFalse((inside / "plan.json").exists())

        outside = self.tmp / "rt"
        outside.mkdir()
        proc = run_ci_step(scratch, "plan", runner_temp=outside, env=self.env,
                           step_env={"SHARDS": ""},
                           github_env={"GITHUB_OUTPUT": str(self.tmp / "github-output")})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        shutil.copy2(outside / "plan.json", inside / "plan.json")
        proc = run_ci_step(job, "shard", runner_temp=inside, env=self.env, step_env={"SHARD": "0"})
        assert_refusal(self, proc.returncode, proc.stderr, "PathInsideRepositoryError")
        self.assertFalse((inside / "out").exists())


# -- T-CI-3: the aggregate refuses incomplete and foreign results ----------------------------

def _record_files(root: Path) -> dict[tuple[str, ...], Path]:
    """`{classes: path}` for every frozen record under `root`."""
    found = {}
    for path in sorted(Path(root).rglob("*.record.json")):
        found[tuple(json.loads(path.read_text())["classes"])] = path
    return found


def _ci_shards(case, scratch_root, plan: Path, out: Path) -> None:
    """Every shard of `plan`, each into its artifact's directory under `out`
    (the aggregate job's download layout)."""
    doc = ci_workflow()
    for index in range(json.loads(plan.read_text())["n"]):
        proc = run_cli(scratch_root, "--run-shard", index, "--plan", plan,
                       "--results", out / ci_artifact_dir(doc, index), env=case.env)
        case.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestCiAggregateRefusals(_CliCase):

    def test_a_missing_shard_and_a_foreign_plan_digest_are_2(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        plan = _plan_only(self, scratch, "--profile", "ci", "--shards", "2")
        out = self.tmp / "out"
        _ci_shards(self, scratch, plan, out)
        honest = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        self.assertEqual(honest.returncode, 0, honest.stdout + honest.stderr)

        held_back = self.tmp / "held-back"
        shutil.move(str(out / ci_artifact_dir(ci_workflow(), 1)), str(held_back))
        missing = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        assert_refusal(self, missing.returncode, missing.stderr, "IncompleteResultsError")
        self.assertIn("missing for [1]", missing.stderr)
        shutil.move(str(held_back), str(out / ci_artifact_dir(ci_workflow(), 1)))

        other = _plan_only(self, scratch, "--profile", "ci", "--shards", "1")
        foreign_out = self.tmp / "foreign"
        _ci_shards(self, scratch, other, foreign_out)
        mixed = self.tmp / "mixed"
        shutil.copytree(out / ci_artifact_dir(ci_workflow(), 1), mixed / "results-shard-1")
        shutil.copytree(foreign_out / ci_artifact_dir(ci_workflow(), 0), mixed / "results-shard-0")
        foreign = run_cli(scratch, "--aggregate", mixed, "--plan", plan, env=self.env)
        assert_refusal(self, foreign.returncode, foreign.stderr, "ForeignResultsError")

    def test_a_self_consistent_record_set_for_another_frozen_partition_is_2(self):
        suite = SCRATCH_FROZEN_SUITE
        scratch = scratch_checkout(
            self.tmp / "scratch",
            timings_units={f"{suite}::TestAlpha": 100.0, f"{suite}::TestBeta": 10.0,
                           f"{suite}::TestGamma": 10.0})
        plan = _plan_only(self, scratch, "--shards", "2")
        out = self.tmp / "out"
        _ci_shards(self, scratch, plan, out)
        honest = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        self.assertEqual(honest.returncode, 0, honest.stdout + honest.stderr)

        # Re-cut the planned (Alpha | Beta Gamma) into (Alpha Beta | Gamma): every
        # record stays well-formed, stamped for this plan and tree, and the two
        # together still cover the suite exactly once.
        records = _record_files(out)
        self.assertEqual(sorted(records), [("TestAlpha",), ("TestBeta", "TestGamma")])
        first = json.loads(records[("TestAlpha",)].read_text())
        second = json.loads(records[("TestBeta", "TestGamma")].read_text())
        beta = [t for t in second["enumerated"] if t.startswith("TestBeta.")]
        first.update(classes=["TestAlpha", "TestBeta"], ran=first["ran"] + 1,
                     enumerated=sorted(first["enumerated"] + beta))
        second.update(classes=["TestGamma"], ran=second["ran"] - 1,
                      enumerated=[t for t in second["enumerated"] if t not in beta])
        for doc in (first, second):
            doc["output"] = re.sub(r"Ran \d+ tests?", f"Ran {doc['ran']} tests", doc["output"])
        self.assertEqual(first["plan_digest"], json.loads(plan.read_text())["plan_digest"])
        records[("TestAlpha",)].write_text(canonical_json(first))
        records[("TestBeta", "TestGamma")].write_text(canonical_json(second))
        recut = run_cli(scratch, "--aggregate", out, "--plan", plan, env=self.env)
        assert_refusal(self, recut.returncode, recut.stderr, "FrozenMergeError")


# -- T-CI-4: the managed workflow is untouched ------------------------------------------------

class TestManagedWorkflowUntouched(unittest.TestCase):

    def test_the_managed_workflow_matches_its_installation_record(self):
        managed = json.loads((REPO_ROOT / ".workflow-manager" / "installation.json")
                             .read_text())["managed"]
        self.assertEqual(_sha256((REPO_ROOT / MANAGED_WORKFLOW).read_bytes()),
                         managed[MANAGED_WORKFLOW]["sha256"])
        self.assertNotIn(str(CI_WORKFLOW.relative_to(REPO_ROOT)), managed)

    def test_workflow_manager_verify_reports_no_drift(self):
        proc = subprocess.run([sys.executable, "-B", "-m", "workflow_manager", "verify",
                               str(REPO_ROOT)], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"),
                                       PYTHONDONTWRITEBYTECODE="1"), timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("installation matches workflow", proc.stdout)


# -- T-CI-5: a fresh CI checkout keeps its guards ---------------------------------------------

#: A unit whose subprocess replaces the environment wholesale -- so no
#: `PYTHONDONTWRITEBYTECODE` -- and imports a package from `src/`.
SRC_IMPORT_TEST = '''
    def test_a_wholesale_environment_imports_from_src(self):
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src")}
        proc = subprocess.run([sys.executable, "-c", "import scratchpkg"], env=env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
'''
SRC_IMPORT_HEADER = ("import os\nimport subprocess\nimport sys\nfrom pathlib import Path\n\n"
                     "ROOT = Path(__file__).resolve().parents[1]\n")
SRC_IMPORT_MODULE = (SRC_IMPORT_HEADER + "import unittest\n\n\n"
                     "class TestScratchSrcImport(unittest.TestCase):\n"
                     + textwrap.dedent(SRC_IMPORT_TEST).replace("\n", "\n    ").rstrip() + "\n")
#: The phase-B matrix host class with the same test added, so `--aggregate`
#: runs one too.
SRC_IMPORT_MATRIX_MODULE = SRC_IMPORT_HEADER + SCRATCH_MATRIX_MODULE.rstrip() + "\n" + \
    textwrap.dedent(SRC_IMPORT_TEST).replace("\n", "\n    ").rstrip() + "\n"


class TestCiGuardsInAFreshCheckout(_CliCase):

    def _pycache(self, job: Path) -> list[str]:
        return sorted(str(p.relative_to(job)) for p in (job / "src").rglob("__pycache__"))

    def test_the_barrier_keeps_a_wholesale_environment_from_writing_bytecode(self):
        scratch = scratch_checkout(self.tmp / "scratch",
                                   modules={"test_scratch_src_import.py": SRC_IMPORT_MODULE,
                                            "test_scratch_matrix.py": SRC_IMPORT_MATRIX_MODULE})
        job = scratch_clone(scratch)
        ignored = _git(job, "status", "--porcelain", "--ignored", "--untracked-files=all")
        self.assertEqual(ignored.strip(), "", "the fresh checkout is not clean")
        plan = self.tmp / "plan.json"
        code, out, err = main_in_process(job, "--plan-only", "--profile", "ci", "--shards", "1",
                                         "--out", plan)
        self.assertEqual(code, 0, out + err)
        phase_b = [c["units"] for s in json.loads(plan.read_text())["phase_b"]["shards"]
                   for c in s["chunks"]]
        self.assertEqual(phase_b, [[SCRATCH_MATRIX_UNIT]])

        # Guarded: green, and nothing under src/.
        code, out, err = main_in_process(job, "--run-shard", "0", "--plan", plan,
                                         "--results", self.tmp / "guarded" / "s0")
        self.assertEqual(code, 0, out + err)
        summary = json.loads((self.tmp / "guarded" / "s0" / "shard-0.json").read_text())
        self.assertIn("host:test_scratch_src_import.py::TestScratchSrcImport",
                      [u for r in summary["results"] for u in r["chunk"]["units"]])
        self.assertEqual(self._pycache(job), [])
        code, out, err = main_in_process(job, "--aggregate", self.tmp / "guarded", "--plan", plan)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._pycache(job), [])

        # The barrier forcibly disabled: the .pyc is written and step 6 fails.
        no_barrier = mock.patch.object(isolation.Barrier, "_lock_dirs",
                                       lambda self, *args, **kwargs: None)
        with no_barrier:
            code, out, err = main_in_process(job, "--run-shard", "0", "--plan", plan,
                                             "--results", self.tmp / "unguarded" / "s0")
        assert_refusal(self, code, err, "IntegrityError")
        self.assertEqual(self._pycache(job), ["src/scratchpkg/__pycache__"])
        shutil.rmtree(job / "src" / "scratchpkg" / "__pycache__")
        with no_barrier:
            code, out, err = main_in_process(job, "--aggregate", self.tmp / "guarded",
                                             "--plan", plan)
        assert_refusal(self, code, err, "IntegrityError")
        self.assertEqual(self._pycache(job), ["src/scratchpkg/__pycache__"])


# == Serial/single-shard evidence policy: the evidence identity ==========================
#
# User-directed during CP7: a full-suite serial or single-shard run is exceptional
# evidence, and an equivalent earlier run is cited rather than repeated
# (`docs/ARCHITECTURE.md`'s "Verification execution"). Citing needs an identity
# every run records.

POLICY_DOCS = ("CLAUDE.md", "docs/development.md")
IDENTITY_FIELDS = ("head", "selection_digest", "tests_digest")


def _host_result(unit_id, tests):
    chunk = plan_schema.ChunkDescriptor(unit_id, 0, (unit_id,), 1.0)
    return executor.ChunkResult(chunk, "A", 0, "host", "passed", 1.0, 2.0, 0,
                                {"ran": list(tests), "failing": []})


def _identity_plan(selection):
    return {"selection": selection, "selection_digest": "S", "tree_digest": "T",
            "profile": "local", "n": 1}


class TestEvidenceIdentity(unittest.TestCase):
    UNITS = ("host:test_a.py::A", "host:test_b.py::B")

    def _identity(self, selection, results):
        return report.evidence_identity(_identity_plan(selection), results, {}, head="H",
                                        inventory_unit_ids=self.UNITS, scope="local, 1 worker(s)")

    def test_only_every_inventory_unit_whole_is_a_full_selection(self):
        results = [_host_result(u, [f"{u}::test_x"]) for u in self.UNITS]
        whole = dict.fromkeys(self.UNITS)
        self.assertEqual(self._identity(whole, results)["selection"], "full")
        for label, selection in (("one unit", {self.UNITS[0]: None}),
                                 ("a method subset", dict(whole, **{self.UNITS[1]: ["test_x"]}))):
            with self.subTest(label):
                self.assertEqual(self._identity(selection, results)["selection"], "targeted")

    def test_a_test_added_to_an_existing_class_moves_tests_digest_only(self):
        whole = dict.fromkeys(self.UNITS)
        before = self._identity(whole, [_host_result(u, [f"{u}::test_x"]) for u in self.UNITS])
        after = self._identity(whole, [_host_result(u, [f"{u}::test_x", f"{u}::test_y"])
                                       for u in self.UNITS])
        self.assertEqual(before["selection_digest"], after["selection_digest"])
        self.assertNotEqual(before["tests_digest"], after["tests_digest"])
        self.assertEqual((before["tests"], after["tests"]), (2, 4))
        reordered = self._identity(whole, [_host_result(u, [f"{u}::test_x"])
                                           for u in reversed(self.UNITS)])
        self.assertEqual(reordered["tests_digest"], before["tests_digest"])

    def test_a_frozen_setupclass_error_is_attributed_to_its_class(self):
        unit = "frozen:1.0.0/conformance/s.py::K"
        chunk = plan_schema.ChunkDescriptor("f", 0, (unit, "frozen:1.0.0/conformance/s.py::L"),
                                            1.0)
        result = executor.ChunkResult(chunk, "A", 0, "frozen", "failed", 1.0, 2.0, 1,
                                      {"ran": 3, "failing": ["__main__.K", "K.test_a",
                                                             "L.test_b"]})
        entries = report.unit_entries([result], {})
        self.assertEqual(entries[unit]["failing"], ["__main__.K", "K.test_a"])
        self.assertEqual(entries["frozen:1.0.0/conformance/s.py::L"]["failing"], ["L.test_b"])

    def test_the_line_names_every_field_a_reuse_record_cites(self):
        identity = self._identity(dict.fromkeys(self.UNITS),
                                  [_host_result(u, [f"{u}::t"]) for u in self.UNITS])
        line = report.identity_line(identity)
        self.assertTrue(line.startswith("evidence: full selection, local, 1 worker(s), head H,"))
        for field in IDENTITY_FIELDS[1:] + ("tree_digest",):
            self.assertIn(f"{field} {identity[field]}", line)


class TestEvidenceIdentityThroughTheCli(_CliCase):

    def test_every_executing_mode_records_its_identity(self):
        scratch = scratch_checkout(self.tmp / "scratch")
        head = _git(scratch, "rev-parse", "HEAD").strip()
        proc = run_cli(scratch, "--results", self.tmp / "full", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads((self.tmp / "full" / "results.json").read_text())
        plan = json.loads((self.tmp / "full" / "plan.json").read_text())
        identity = doc["identity"]
        self.assertEqual((identity["selection"], identity["head"]), ("full", head))
        self.assertEqual(identity["selection_digest"], plan["selection_digest"])
        self.assertEqual(identity["tree_digest"], plan["tree_digest"])
        self.assertEqual(identity["tests"], len({t for u in doc["units"].values()
                                                 for t in u["tests"]}))
        self.assertIn(report.identity_line(identity), proc.stdout)

        targeted = run_cli(scratch, "--jobs", "1", "--select", "test_scratch_shared.py",
                           "--results", self.tmp / "targeted", env=self.env)
        self.assertEqual(targeted.returncode, 0, targeted.stdout + targeted.stderr)
        self.assertIn("evidence: targeted selection, local, 1 worker(s)", targeted.stdout)

        ci_plan = _plan_only(self, scratch, "--profile", "ci", "--shards", "1")
        out = self.tmp / "ci"
        shard = run_cli(scratch, "--run-shard", "0", "--plan", ci_plan, "--results", out / "s0",
                        env=self.env)
        self.assertEqual(shard.returncode, 0, shard.stdout + shard.stderr)
        self.assertEqual(json.loads((out / "s0" / "shard-0.json").read_text())
                         ["identity"]["scope"], "shard 0 of 1")
        aggregate = run_cli(scratch, "--aggregate", out, "--plan", ci_plan, env=self.env)
        self.assertEqual(aggregate.returncode, 0, aggregate.stdout + aggregate.stderr)
        self.assertIn("evidence: full selection, aggregate of 1 shard(s)", aggregate.stdout)
        self.assertIn(f"tests_digest {identity['tests_digest']}", aggregate.stdout,
                      "the sharded and the local full run executed different test sets")


class TestSerialEvidencePolicyIsDocumented(unittest.TestCase):

    def test_every_serial_reference_command_is_marked_exceptional(self):
        for name in POLICY_DOCS:
            lines = [line for line in (REPO_ROOT / name).read_text().splitlines()
                     if re.match(r"python3 tests/run_all\.py --jobs 1\s", line)]
            with self.subTest(doc=name):
                self.assertTrue(lines)
                for line in lines:
                    self.assertIn("exceptional evidence", line)

    def test_the_policy_names_the_fields_the_runner_records(self):
        text = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text()
        section = text.split("## Verification execution", 1)[1].split("\n## ", 1)[0]
        self.assertIn("**Serial and single-shard runs are exceptional evidence.**", section)
        self.assertIn("**Reuse equivalent evidence rather than re-running it.**", section)
        identity = TestEvidenceIdentity()._identity(
            dict.fromkeys(TestEvidenceIdentity.UNITS),
            [_host_result(u, [f"{u}::t"]) for u in TestEvidenceIdentity.UNITS])
        for field in IDENTITY_FIELDS + ("tree_digest",):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", section)
                self.assertIn(field, identity)
        for name in POLICY_DOCS:
            self.assertIn("Verification execution", (REPO_ROOT / name).read_text())


if __name__ == "__main__":
    unittest.main(verbosity=1)
