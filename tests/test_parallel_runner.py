#!/usr/bin/env python3
"""The parallel verification tooling under `tests/parallel/` is deterministic,
covers exactly what a direct run covers, and fails closed.

Checkpoint CP1 of `workflow-manager-adaptive-test-sharding`: host inventory and
selection (T-INV-1, -2, -4, -5, host parts), the shared resource and
chunk-descriptor contracts (T-INV-8), tree identity and the snapshot, and the
per-unit host runner.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from support import REPO_ROOT

from parallel import canonical_json, inventory, plan_schema, resources, tree, unit

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
