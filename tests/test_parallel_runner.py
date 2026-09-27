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
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import support
from support import CI_SUITES, REPO_ROOT

import frozen_runs
import test_bootstrap_e2e as bootstrap_e2e
import test_conformance_suite as conformance_suite
from parallel import (canonical_json, inventory, matrix, plan_schema, planner, resources, timings,
                      tree, unit)

TESTS_DIR = REPO_ROOT / "tests"
EXCLUSIVE_UNIT = "host:test_amendment_update_path.py::TestMigrateDoesNotDeleteASiblingAuthoredRelease"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


def _git_repo(root: Path) -> Path:
    _git(root, "init", "-q", "-b", "main")
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
            for tree_name in ("distribution", "migration", "src", "tools"):
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
        chosen = inventory.select(self.host, ["test_templates.py"]).unit_ids()
        expected = sorted(u for u in self.host if u.startswith("host:test_templates.py::"))
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
            "repo:distribution": {"paths": ["distribution/"], "description": "dist"},
            "repo:src": {"paths": ["src/", "tools/"], "description": "code"},
        },
        "exclusive": {
            "host:test_a.py::A": {"resources": ["repo:distribution"], "reason": "rmtree"},
            "host:test_a.py::B": {"resources": ["repo:src", "repo:distribution"], "reason": "both"},
        },
    }
    doc.update(overrides)
    return doc


class TestResourcesContract(_RealHostInventory):
    """T-INV-8, `resources.load`."""

    def test_the_committed_declaration_loads_against_the_real_inventory(self):
        loaded = resources.load(REPO_ROOT, self.host)
        self.assertEqual(loaded.exclusive_units(), (EXCLUSIVE_UNIT,))
        self.assertIn(EXCLUSIVE_UNIT, self.host)
        self.assertEqual(loaded.resources["repo:distribution"].paths, ("distribution/",))
        self.assertEqual(loaded.trees_for(EXCLUSIVE_UNIT), ("distribution/",))
        self.assertTrue(loaded.exclusive[EXCLUSIVE_UNIT].reason)

    def test_a_valid_two_resource_file_reports_each_tree_union(self):
        loaded = resources.parse(_resources_doc(), SYNTHETIC)
        self.assertEqual(loaded.trees_for("host:test_a.py::A"), ("distribution/",))
        self.assertEqual(loaded.trees_for("host:test_a.py::B"),
                         ("distribution/", "src/", "tools/"))
        self.assertEqual(loaded.resources_of("host:test_a.py::B"), ("repo:distribution", "repo:src"))
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
            "undeclared resource": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": ["repo:nope"], "reason": "x"}}),
            "empty resources list": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": [], "reason": "x"}}),
            "empty reason": _resources_doc(exclusive={
                "host:test_a.py::A": {"resources": ["repo:distribution"], "reason": " "}}),
            "unit not in inventory": _resources_doc(exclusive={
                "host:test_zzz.py::Z": {"resources": ["repo:distribution"], "reason": "x"}}),
            "bare-string resource (revision-6 form)": _resources_doc(
                resources={"repo:distribution": "distribution/"}, exclusive={}),
            "empty paths": _resources_doc(**res([])),
            "non-string path": _resources_doc(**res([7])),
            "absolute path": _resources_doc(**res(["/distribution/"])),
            "dot-dot component": _resources_doc(**res(["src/../tools/"])),
            "tests/ is not guarded": _resources_doc(**res(["tests/"])),
            "sub-path of a guarded tree": _resources_doc(**res(["distribution/workflow/"])),
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

    def test_guarded_trees_are_the_four_the_barrier_covers(self):
        self.assertEqual(resources.GUARDED_TREES, ("distribution/", "migration/", "src/", "tools/"))


class TestChunkDescriptorContract(unittest.TestCase):
    """T-INV-8, `plan_schema`."""

    def chunk(self, **kw):
        base = dict(id="c1", shard_index=0, units=("host:b", "host:a"), estimate=1.5,
                    resources=("repo:distribution",))
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
            for tree_name in ("distribution", "migration", "src", "tools"):
                (copy / tree_name).symlink_to(REPO_ROOT / tree_name)
            real_listdir = os.listdir
            with mock.patch("os.listdir", lambda p=".": list(reversed(sorted(real_listdir(p))))):
                found = inventory.discover_frozen(copy)
            self.assertEqual(canonical_json(found.to_json()),
                             canonical_json(self.frozen.to_json()))

    def test_per_suite_totals_equal_the_pinned_counts_for_every_release(self):
        self.assertEqual(self.frozen.ci_suites, {v: dict(s) for v, s in CI_SUITES.items()})
        for version, suites in CI_SUITES.items():
            self.assertEqual(list(self.frozen.ci_suites[version]), list(suites))  # order kept
            self.assertEqual(sorted(self.frozen.classes[version]), sorted(suites))
            for suite, pinned in suites.items():
                with self.subTest(version=version, suite=suite):
                    found = self.frozen.classes[version][suite]
                    self.assertEqual(sum(len(m) for m in found.values()), pinned)

    def test_the_matrix_is_every_release_times_every_fixture(self):
        self.assertEqual(sorted(self.frozen.matrix.values()),
                         sorted((v, f) for v in CI_SUITES for f in matrix.FIXTURES))
        self.assertEqual(len(self.frozen.matrix), 15)

    def test_frozen_units_multiply_classes_by_fixture(self):
        units = self.frozen.units()
        per_release = {v: sum(len(c) for c in s.values()) for v, s in self.frozen.classes.items()}
        self.assertEqual(len(units), 3 * sum(per_release.values()))
        self.assertEqual(sum(len(t) for t in units.values()),
                         3 * sum(sum(s.values()) for s in CI_SUITES.values()))
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
    minimal layout of its own: one release payload with one tiny suite, and a
    literal `matrix.py`."""

    def layout(self, root: Path, pinned: int) -> Path:
        scripts = root / "distribution" / "workflow" / "0.0.1" / "payload" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "tiny_test.py").write_text(TINY_SUITE)
        shutil.copytree(TESTS_DIR / "parallel", root / "tests" / "parallel",
                        ignore=shutil.ignore_patterns("__pycache__", "matrix.py", "*.json"))
        (root / "tests" / "parallel" / "matrix.py").write_text(textwrap.dedent(f"""
            FIXTURES = ("conformance", "target", "bootstrapped")
            CI_SUITES = {{"0.0.1": {{"tiny_test.py": {pinned}}}}}
            FROZEN_MATRIX = {{"host:test_tiny.py::TestTiny": ("0.0.1", "conformance")}}
        """))
        return root

    def test_a_wrong_pin_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.layout(Path(tmp), pinned=4)
            with self.assertRaises(inventory.InventoryCountError) as caught:
                inventory.discover_frozen(root)
            self.assertIn("discovered 3 tests, CI_SUITES pins 4", str(caught.exception))

    def test_the_right_pin_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
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
        chosen = inventory.select(inv.host, ["test_conformance_suite.py::TestConformanceFixture260"],
                                  inv.frozen)
        self.assertEqual(chosen.host_unit_ids(),
                         ["host:test_conformance_suite.py::TestConformanceFixture260"])
        self.assertEqual(len(chosen.frozen_unit_ids()),
                         sum(len(c) for c in inv.frozen.classes["2.6.0"].values()))
        self.assertTrue(all(u.startswith("frozen:2.6.0/conformance/")
                            for u in chosen.frozen_unit_ids()))


# -- T-MRG-1 / -2 / -7: the merge ------------------------------------------------------

MERGE_VERSION = "2.6.0"


def _record(chunk_id, suite, classes, ran, *, failing=(), returncode=0, fixture="conformance",
            **overrides):
    fields = dict(
        chunk_id=chunk_id, version=MERGE_VERSION, fixture=fixture, suite=suite,
        classes=tuple(classes), returncode=returncode, ran=ran, failing=tuple(failing),
        output=f"<{chunk_id}>\nRan {ran} tests in 0.1s\n", tree_digest="T1", plan_digest="P1",
        release_digest=frozen_runs.release_digest(REPO_ROOT, MERGE_VERSION))
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
        host = conformance_suite.TestConformanceFixture260
        with tempfile.TemporaryDirectory() as tmp:
            records, contexts = Path(tmp) / "records", Path(tmp) / "contexts"
            records.mkdir()
            contexts.mkdir()
            foreign = frozen_runs.MergeContext.from_chunks(
                "2.6.0", "conformance",
                [frozen_runs.FrozenChunk("x#0", "2.6.0", "conformance", "x_test.py", ("X",))],
                {"x_test.py": ["X"]}, tree_digest="0" * 64, plan_digest="P")
            wrong_tree = Path(tmp) / "wrong-tree"
            frozen_runs.write_context(foreign, wrong_tree)
            cases = {
                "records without a context": ({frozen_runs.RECORDS_ENV: str(records)},
                                              "is set but WM_FROZEN_CONTEXT is not"),
                "no context file for (version, fixture)": (
                    {frozen_runs.RECORDS_ENV: str(records), frozen_runs.CONTEXT_ENV: str(contexts)},
                    "no merge context for 2.6.0/conformance"),
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


def _matrix_hosts():
    for unit_id, (version, fixture) in matrix.FROZEN_MATRIX.items():
        module, cls = inventory.split_host_unit_id(unit_id)
        yield getattr(conformance_suite if module == "test_conformance_suite.py" else bootstrap_e2e,
                      cls), version, fixture


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
                    release_digest=frozen_runs.release_digest(REPO_ROOT, self.version),
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
    """T-MRG-3, -4, -5, -6: every view-reading assertion of the 15 matrix
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
                        mock.patch.object(sys.modules[host.__module__],
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
                with mock.patch.object(sys.modules[host.__module__],
                                       "expected_portability_exceptions",
                                       lambda v, e=expected: e):
                    outcomes = _host_outcomes(host, fixture, scenario.merged())
                if "fail" in outcomes.values():
                    caught.setdefault(mutation, set()).add(fixture)
                self.assertNotIn("error", outcomes.values(), (host.__name__, mutation))
        self.assertEqual(caught, {
            "extra failing test": {"conformance", "target", "bootstrapped"},
            "one missing test": {"conformance", "target", "bootstrapped"},
            "stale portability exception": {"target", "bootstrapped"},
            "non-empty residue": {"bootstrapped"},
            "non-empty drift": {"bootstrapped"},
            "setUpClass error in one chunk": {"conformance", "target", "bootstrapped"},
            "suite crashes on import": {"conformance", "target", "bootstrapped"},
        })

    def test_a_crashed_or_errored_chunk_merges_and_fails_as_a_test_failure(self):
        """T-MRG-3 and T-MRG-4, called out: no merge refusal, and the two
        count/pass assertions fail -- with today's message for a missing
        summary."""
        host = conformance_suite.TestConformanceFixture260
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
        host = bootstrap_e2e.TestBootstrappedRepositorySatisfiesTheFrozenSuite260
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
        host = conformance_suite.TestConformanceFixture260
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
        self.assertEqual(record.release_digest, frozen_runs.release_digest(REPO_ROOT, "2.6.0"))
        self.assertEqual((record.residue, record.drift), ((), ()))
        self.assertFalse(record.timed_out)
        self.assertLessEqual(record.started_at, record.ended_at)

    def test_fixed_chunkings_partition_every_suite(self):
        frozen = inventory.discover_frozen(REPO_ROOT)
        for mode in ("two-chunk", "one-class"):
            chunks = frozen_runs.fixed_chunking(frozen, "2.3.1", "target", mode)
            with self.subTest(mode):
                frozen_runs.MergeContext.from_chunks(
                    "2.3.1", "target", chunks,
                    {s: list(c) for s, c in frozen.classes["2.3.1"].items()},
                    tree_digest="T", plan_digest=frozen_runs.chunking_digest(chunks))
                per_suite = {}
                for chunk in chunks:
                    per_suite.setdefault(chunk.suite, []).append(chunk)
                for suite, parts in per_suite.items():
                    classes = frozen.classes["2.3.1"][suite]
                    expected = (len(classes) if mode == "one-class" else min(2, len(classes)))
                    self.assertEqual(len(parts), expected, suite)
                    self.assertEqual(sum(len(c.enumerated) for c in parts),
                                     CI_SUITES["2.3.1"][suite])


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
                        "resources": {"r": {"paths": ["distribution/"], "description": "d"}},
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
            for text in ("{not json", "[]", '{"schema_version": 2, "profiles": {}}',
                         '{"schema_version": 1, "profiles": []}'):
                with self.subTest(text=text):
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
               "resources": {"repo:distribution": {"paths": ["distribution/"],
                                                   "description": "the tree"}},
               "exclusive": {self.EXCL: {"resources": ["repo:distribution"],
                                         "reason": "rewrites distribution/"}} if exclusive
               else {}}
        resources.resources_path(root).write_text(json.dumps(doc))
        return resources.load(root, [self.EXCL, *self.SHARED])

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
                    self.assertEqual(shard[0].resources, ("repo:distribution",))
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
                first = [s[0] for s in plan_schema.shard_chunks(plan)
                         if any(EXCLUSIVE_UNIT in c.units for c in s)]
                self.assertEqual([c.units for c in first], [(EXCLUSIVE_UNIT,)])


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

    def layout(self, root: Path) -> Path:
        TestFrozenInventoryCountRefusal.layout(None, root, pinned=3)
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
        with tempfile.TemporaryDirectory() as tmp:
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

if __name__ == "__main__":
    unittest.main(verbosity=1)
