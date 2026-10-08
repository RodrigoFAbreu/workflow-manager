#!/usr/bin/env python3
"""`plan_update` / `apply_update` are `update` split in two, behaviour unchanged.

The existing update tests (`test_bootstrap.py`, `test_update_path.py`) are the
oracle for what an update does. These pin the split itself: planning writes
nothing, planning then applying equals `update` in tree, record and change
lines, and every refusal is raised identically.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from test_bootstrap import (
    FIXED_NOW,
    NEXT_RELEASE,
    BootstrapCase,
    synthesize_next_release,
)

import workflow_manager.install as install_module
from workflow_manager.install import (
    CollisionError,
    DriftError,
    InstallError,
    NotManagedError,
    PlannedWrite,
    UpdatePlan,
    apply_update,
    bootstrap,
    plan_update,
    update,
)
from workflow_manager.installation import Installation

LATER = "2027-01-01T00:00:00Z"
DROPPED = ".claude/commands/prepare-review.md"
CHANGED = "docs/ai-workflow/REVIEW_PROTOCOL.md"
ADDED = "docs/ai-workflow/WHATS_NEW.md"
STATE = "docs/ai-workflow/WORKFLOW_STATE.json"


def snapshot(root: Path) -> dict[str, tuple[int, bytes | None]]:
    """Path -> (mode, bytes) for everything under `root`, `.git` included."""
    found = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            found[rel] = (-1, str(path.readlink()).encode())
        elif path.is_file():
            found[rel] = (path.stat().st_mode & 0o7777, path.read_bytes())
        else:
            found[rel] = (path.stat().st_mode & 0o7777, None)
    return found


class UpdatePlanCase(BootstrapCase):
    def setUp(self):
        super().setUp()
        bootstrap(self.target, self.release, now=FIXED_NOW)
        self.next_release = synthesize_next_release(
            self.release, Path(self._tmp.name) / "r2", NEXT_RELEASE, change_ci=True)
        (self.target / STATE).write_text('{"schema_version": 1, "work_items": {}}\n')

    def twin(self, name: str) -> Path:
        """A byte-identical copy of the target, to run the other path on."""
        copy = Path(self._tmp.name) / name
        shutil.copytree(self.target, copy, symlinks=True)
        return copy

    def assertParity(self, mutate=None, **options):
        """`update` on one copy equals `plan_update` + `apply_update` on another."""
        mutate = mutate or (lambda root: None)
        direct, planned = self.twin("direct"), self.twin("planned")
        mutate(direct)
        mutate(planned)
        updated, changes = update(direct, self.next_release, now=LATER, **options)
        plan = plan_update(planned, self.next_release, now=LATER, **options)
        applied = apply_update(plan, self.next_release)
        self.assertEqual(plan.changes, changes)
        self.assertEqual(applied, updated)
        self.assertEqual(Installation.read(planned), Installation.read(direct))
        self.assertEqual(
            {k: v for k, v in snapshot(planned).items()},
            {k: v for k, v in snapshot(direct).items()},
        )
        return plan


class TestPlanningWritesNothing(UpdatePlanCase):
    def test_planning_leaves_the_tree_untouched(self):
        before = snapshot(self.target)
        plan = plan_update(self.target, self.next_release, now=LATER)
        self.assertEqual(snapshot(self.target), before)
        self.assertIsInstance(plan, UpdatePlan)

    def test_a_refused_plan_writes_nothing_either(self):
        (self.target / CHANGED).write_text("mine\n")
        before = snapshot(self.target)
        with self.assertRaises(DriftError):
            plan_update(self.target, self.next_release, now=LATER)
        self.assertEqual(snapshot(self.target), before)


class TestPlanThenApplyEqualsUpdate(UpdatePlanCase):
    def test_a_clean_release_to_release_update(self):
        plan = self.assertParity()
        self.assertIn(f"removed {DROPPED}", plan.changes)
        self.assertIn(f"updated {CHANGED}", plan.changes)
        self.assertIn(f"added {ADDED}", plan.changes)
        self.assertEqual(plan.removals, [DROPPED])

    def test_updating_to_the_same_release_plans_no_change(self):
        plan = plan_update(self.target, self.release, now=LATER)
        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.removals, [])
        self.assertEqual(plan.writes, [])

    def test_a_deleted_state_file_is_recreated(self):
        plan = self.assertParity(lambda root: (root / STATE).unlink())
        self.assertIn(f"created missing state {STATE}", plan.changes)
        self.assertIn(STATE, {w.path for w in plan.writes})

    def test_a_changed_merged_file(self):
        def mutate(root):
            (root / "CLAUDE.md").write_text("# mine\n")
            (root / ".gitignore").write_text("build/\n")
        plan = self.assertParity(mutate)
        self.assertIn("CLAUDE.md", {w.path for w in plan.writes})

    def test_a_lost_executable_bit_is_a_mode_only_write(self):
        script = "scripts/prepare-ai-review.sh"

        def mutate(root):
            (root / script).chmod(0o644)
        plan = self.assertParity(mutate)
        # The synthetic release leaves this file's bytes alone, so only the
        # mode is repaired.
        planned = {w.path: w for w in plan.writes}
        self.assertEqual(planned[script], PlannedWrite(script, None, True, mode_only=True))
        self.assertIn(f"fixed mode {script}", plan.changes)

    def test_a_profile_change(self):
        plan = self.assertParity(profile="runtime")
        self.assertEqual(plan.profile, "runtime")
        self.assertTrue(plan.removals)

    def test_a_forced_update_over_a_local_edit(self):
        plan = self.assertParity(lambda root: (root / CHANGED).write_text("mine\n"), force=True)
        self.assertEqual(plan.overwrites, [CHANGED])

    def test_an_unforced_plan_has_no_overwrites(self):
        self.assertEqual(plan_update(self.target, self.next_release, now=LATER).overwrites, [])


class TestRefusalsAreRaisedIdentically(UpdatePlanCase):
    def assertSameRefusal(self, error, mutate, **options):
        direct, planned = self.twin("direct"), self.twin("planned")
        mutate(direct)
        mutate(planned)
        with self.assertRaises(error) as expected:
            update(direct, self.next_release, now=LATER, **options)
        with self.assertRaises(error) as actual:
            plan_update(planned, self.next_release, now=LATER, **options)
        self.assertEqual(str(actual.exception).replace(str(planned), ""),
                         str(expected.exception).replace(str(direct), ""))
        return actual.exception

    def test_local_edit(self):
        exc = self.assertSameRefusal(DriftError, lambda r: (r / CHANGED).write_text("mine\n"))
        self.assertEqual([d.path for d in exc.drifted], [CHANGED])

    def test_collision_with_the_repositorys_own_file(self):
        exc = self.assertSameRefusal(CollisionError, lambda r: (r / ADDED).write_text("mine\n"))
        self.assertEqual([c.path for c in exc.collisions], [ADDED])

    def test_directory_in_the_way_survives_force(self):
        def mutate(root):
            (root / DROPPED).unlink()
            (root / DROPPED).mkdir()
        exc = self.assertSameRefusal(CollisionError, mutate, force=True)
        self.assertEqual([c.path for c in exc.collisions], [DROPPED])

    def test_not_managed(self):
        with self.assertRaises(NotManagedError):
            plan_update(Path(self._tmp.name) / "nowhere", self.release)

    def test_unknown_profile(self):
        with self.assertRaises(InstallError):
            plan_update(self.target, self.release, profile="bogus")


class TestLeftAlone(UpdatePlanCase):
    def reasons(self, plan):
        return {entry.path: entry.reason for entry in plan.left_alone}

    def test_state_files_identical_files_merged_files_and_the_runtime_workspace(self):
        plan = plan_update(self.target, self.next_release, now=LATER)
        reasons = self.reasons(plan)
        self.assertEqual(reasons[STATE], "repository-local state")
        self.assertEqual(reasons[".ai-review/"], "the Workflow's runtime workspace")
        self.assertIn("CLAUDE.md", reasons)
        self.assertIn(".gitignore", reasons)
        untouched = next(p for p in sorted(reasons) if reasons[p] == "already identical to the release")
        self.assertNotIn(untouched, {w.path for w in plan.writes})

    def test_nothing_changed_is_never_also_written(self):
        plan = plan_update(self.target, self.next_release, now=LATER)
        self.assertFalse({e.path for e in plan.left_alone} & {w.path for w in plan.writes} - {"CLAUDE.md", ".gitignore"})


class TestApplyKeepsItsContract(UpdatePlanCase):
    def test_a_plan_for_another_release_is_not_applied(self):
        plan = plan_update(self.target, self.next_release, now=LATER)
        before = snapshot(self.target)
        with self.assertRaises(InstallError):
            apply_update(plan, self.release)
        self.assertEqual(snapshot(self.target), before)

    def test_apply_writes_through_the_module_global_once_per_file(self):
        plan = plan_update(self.target, self.next_release, now=LATER)
        expected = sum(1 for w in plan.writes if not w.mode_only)
        self.assertGreater(expected, 1, "an update that writes nothing proves nothing")
        calls = []
        real = install_module._write
        install_module._write = lambda path, data, executable=False: (
            calls.append(path), real(path, data, executable))[1]
        try:
            apply_update(plan, self.next_release)
        finally:
            install_module._write = real
        self.assertEqual(len(calls), expected)
        self.assertEqual(
            [p.relative_to(self.target).as_posix() for p in calls],
            [w.path for w in plan.writes if not w.mode_only],
        )


if __name__ == "__main__":
    unittest.main()
