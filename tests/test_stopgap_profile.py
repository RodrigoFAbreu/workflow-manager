#!/usr/bin/env python3
"""The stopgap test profile: every test of stopgap code (plan section 6.7).

Checkpoint CP3 of `workflow-manager-trunk-model`
(`D-Newest-Release-Selection`): `--newest-release-only`'s selection, its
exclusivity with `--select`/`--fast`, the plan's `selection_kind`, the
evidence label for all three kinds, the full selection unchanged by this
milestone's runner changes (INV-2), and a real `--list` subprocess run in a
scratch checkout of three releases.
"""

# STOPGAP(M2): this whole module tests the stopgap profile; see
# docs/ARCHITECTURE.md's "Stopgap test profile". M2 deletes it.

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from support import CI_SUITES, REPO_ROOT

import test_parallel_runner as runner_tests
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


if __name__ == "__main__":
    unittest.main()
