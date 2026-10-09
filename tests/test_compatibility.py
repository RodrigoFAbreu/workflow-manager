#!/usr/bin/env python3
"""The compatibility reader, the three release tables and the findings.

Everything here runs on disposable repositories with hand-written state files:
the reader takes plain JSON. The release tables' *meaning* is checked against
the pinned 2.9.0 package's own code, not only their coverage of the pins.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from support import PINNED_VERSIONS

import workflow_manager.compatibility as comp
from workflow_manager.compatibility import (
    BLOCKED,
    NOTE,
    WARNING,
    Command,
    GitResult,
    RepositoryFacts,
    StageDeclarations,
    build_report,
    read_repository,
    render_command,
    render_report,
)
from workflow_manager.fixture import init_git_repo
from workflow_manager.install import (
    CollisionError,
    DriftError,
    LeftAlone,
    PlannedWrite,
    UpdatePlan,
    bootstrap,
)
from workflow_manager.installation import Installation

NOW = "2026-01-01T00:00:00Z"
STATE = comp.STATE_PATH
LATEST = PINNED_VERSIONS[-1]
HEX = "0" * 40


@contextlib.contextmanager
def workflow_modules(version: str = "2.9.0"):
    """The pinned release's own scripts, imported for the duration only."""
    scripts = str(support.release(version).root / "payload" / "scripts")
    names = ("workflow_state", "workflow_fingerprint", "workflow_gate_policy")
    saved = {n: sys.modules.pop(n) for n in names if n in sys.modules}
    sys.path.insert(0, scripts)
    try:
        yield {n: importlib.import_module(n) for n in names}
    finally:
        sys.path.remove(scripts)
        for n in names:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


def item(phase="IMPLEMENTING", governing="2.2", wtype="process", parent=None, **extra):
    return {"work_item_type": wtype, "phase": phase, "governing_workflow_version": governing,
            "parent_work_item_id": parent, **extra}


def state(items: dict, active=None, **top):
    return {"schema_version": 1, "active_work_item_id": active, "work_items": items, **top}


def artifacts(plan_protected=(), impl_protected=(), impl_prefixes=(), plan_excluded=(),
              impl_excluded=(), impl_excluded_prefixes=(), plan_stage=True, impl_stage=True):
    data = {"schema_version": 2}
    if plan_stage:
        data["plan_stage"] = {"protected_paths": list(plan_protected),
                              "excluded_paths": {p: "r" for p in plan_excluded},
                              "excluded_prefixes": {}}
    if impl_stage:
        data["implementation_stage"] = {
            "protected_paths": {p: "r" for p in impl_protected},
            "protected_prefixes": {p: "r" for p in impl_prefixes},
            "excluded_paths": {p: "r" for p in impl_excluded},
            "excluded_prefixes": {p: "r" for p in impl_excluded_prefixes}}
    return data


def fake_plan(target: Path, writes=(), removals=()) -> UpdatePlan:
    record = Installation.read(target)
    return UpdatePlan(
        target=target, current=record, updated=record, profile=record.profile, changes=[],
        removals=list(removals), writes=[PlannedWrite(p, b"x") for p in writes],
        left_alone=[LeftAlone("x", "y")])


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "target"
        init_git_repo(self.target)
        bootstrap(self.target, support.release(LATEST), now=NOW)

    def put(self, rel: str, data):
        path = self.target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data, indent=1) + "\n")

    def set_state(self, items, **kwargs):
        self.put(STATE, state(items, **kwargs))

    def set_artifacts(self, wid, **kwargs):
        self.put(comp.artifacts_relpath(wid), artifacts(**kwargs))

    def commit(self, message="work"):
        subprocess.run(["git", "-C", str(self.target), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.target), "commit", "-q", "--allow-empty", "-m", message],
                       check=True)

    def facts(self) -> RepositoryFacts:
        return read_repository(self.target)

    def report(self, plan=None, target=LATEST, installed=None, **kwargs):
        facts = kwargs.pop("facts", None) or self.facts()
        if installed:
            facts.installation = Installation(installed, "full", {})
        return build_report(facts, plan, target_version=target, latest_version=LATEST,
                            pinned_versions=PINNED_VERSIONS, **kwargs)


# ---------------------------------------------------------------------------


class TestTables(unittest.TestCase):
    def test_every_pinned_version_has_an_entry_in_each_table(self):
        for table in (comp.DOWNGRADE_BOUNDARIES, comp.NEW_WORK_ONLY, comp.GATE_DEFAULT_CHANGES):
            self.assertEqual(sorted(table, key=comp.version_key), PINNED_VERSIONS)

    def test_each_boundary_with_a_posture_has_signals_or_says_it_cannot_detect(self):
        for version, boundary in comp.DOWNGRADE_BOUNDARIES.items():
            if boundary.posture:
                self.assertTrue(boundary.signals or boundary.undetectable, version)

    def test_phase_classes_cover_2_9_0_known_phases(self):
        with workflow_modules() as m:
            known = set(m["workflow_state"].KNOWN_PHASES)
        self.assertEqual(comp.KNOWN_PHASES, known)
        classes = [comp.PLAN_PHASES, comp.IMPLEMENTING_OR_LATER_PHASES, comp.NON_ACTIVE_EXEMPT_PHASES]
        for phase in known:
            self.assertEqual(sum(phase in c for c in classes), 1, phase)

    def test_amending_plan_is_implementing_or_later(self):
        self.assertIn("AMENDING_PLAN", comp.IMPLEMENTING_OR_LATER_PHASES)

    def test_gate_modes_match_2_9_0_gate_mode(self):
        with workflow_modules() as m:
            gp = m["workflow_gate_policy"]
            self.assertEqual(
                {g: set(v) for g, v in comp.ALWAYS_HUMAN_GATES.items()},
                {g: set(v) for g, v in gp._ALWAYS_HUMAN.items()})
            for human in (False, True):
                effective = {"policy": {g: {"human": human} for g in gp.GATE_IDS}}
                for governing in comp.GOVERNING_VERSIONS:
                    for gate in gp.GATE_IDS:
                        self.assertEqual(
                            comp.gate_modes(governing, human)[gate],
                            gp.gate_mode(effective, gate, governing), (governing, gate, human))

    def test_ambient_exclusion_matches_2_9_0(self):
        with workflow_modules() as m:
            self.assertEqual(comp.AMBIENT_EXCLUDED_PATHS,
                             set(m["workflow_fingerprint"].TOOLING_AMBIENT_EXCLUDED_PATHS))


class TestClassifiersMatchTheWorkflow(unittest.TestCase):
    PATHS = [
        "scripts/a.py", "scripts/sub/b.py", ".claude/commands/x.md", "docs/ai-workflow/PLAN.md",
        "docs/ai-workflow/GATE_POLICY.json", "CLAUDE.md", ".gitignore", "app/Main.kt",
        ".workflow-manager/installation.json", ".workflow-manager/other.json", "README.md",
        "docs/x.md", "docs/ai-workflow/registry/a.json",
    ]

    def declarations(self):
        return dict(
            protected={"CLAUDE.md", "docs/ai-workflow/PLAN.md", "scripts/a.py"},
            excluded_paths={"README.md": "r", ".gitignore": "r", "scripts/a.py": "also excluded"},
            excluded_prefixes={"docs/": "r"})

    def test_plan_stage(self):
        d = self.declarations()
        stage = StageDeclarations(frozenset(d["protected"]), (), frozenset(d["excluded_paths"]),
                                  tuple(d["excluded_prefixes"]))
        with workflow_modules() as m:
            fp = m["workflow_fingerprint"]
            for path in self.PATHS:
                try:
                    expected = fp.classify_path(path, frozenset(d["protected"]), d["excluded_paths"],
                                                d["excluded_prefixes"])
                except fp.UnclassifiedPathError:
                    expected = comp.UNCLASSIFIED
                self.assertEqual(comp.classify_plan_stage(path, stage), expected, path)

    def test_a_stray_plan_stage_protected_prefix_changes_nothing(self):
        raw = {"protected_paths": ["CLAUDE.md"], "protected_prefixes": {"scripts/": "r"},
               "excluded_paths": {"README.md": "r"}}
        stage = comp._stage(raw)
        self.assertEqual(comp.classify_plan_stage("scripts/a.py", stage), comp.UNCLASSIFIED)

    def test_implementation_stage(self):
        protected = {"CLAUDE.md": "r", "docs/ai-workflow/PLAN.md": "r"}
        prefixes = {"scripts/": "r", ".claude/commands/": "r"}
        excluded = {"README.md": "r", "scripts/a.py": "an exclusion never overrides protection"}
        excluded_prefixes = {"docs/": "r"}
        stage = StageDeclarations(frozenset(protected), tuple(prefixes), frozenset(excluded),
                                  tuple(excluded_prefixes))
        with workflow_modules() as m:
            fp = m["workflow_fingerprint"]
            for path in self.PATHS:
                try:
                    expected = fp.classify_path_implementation_stage(
                        path, protected, prefixes, excluded, excluded_prefixes)
                except fp.UnclassifiedPathError:
                    expected = comp.UNCLASSIFIED
                self.assertEqual(comp.classify_implementation_stage(path, stage), expected, path)

    def test_artifacts_path_matches_2_9_0(self):
        with workflow_modules() as m:
            self.assertEqual(
                comp.artifacts_relpath("my-item_1"),
                m["workflow_fingerprint"].artifacts_path_for_work_item("my-item_1").as_posix())
        for bad in ("../x", "A", "", "a/b", "-a"):
            with self.assertRaises(ValueError):
                comp.artifacts_relpath(bad)


class TestRendering(unittest.TestCase):
    def test_render_command_quotes_for_a_shell(self):
        argv = ["git", "-C", "/tmp/a b/$x;y", "status"]
        self.assertEqual(render_command(argv), "git -C '/tmp/a b/$x;y' status")
        import shlex
        self.assertEqual(shlex.split(render_command(argv)), argv)

    def test_global_release_version_goes_before_the_subcommand(self):
        cmd = comp.manager_command("update", "/r", release_version="2.8.0")
        self.assertEqual(cmd.argv, ("workflow-manager", "--release-version", "2.8.0", "update", "/r"))
        self.assertEqual(cmd.argv[0], "workflow-manager")

    def test_an_unknown_family_is_refused(self):
        with self.assertRaises(ValueError):
            Command("shell", ("ls",))

    def test_versions(self):
        self.assertEqual(comp.version_key("2.5.1"), (2, 5, 1))
        with self.assertRaises(ValueError):
            comp.version_key("v2")


# ---------------------------------------------------------------------------


class TestReader(Case):
    def test_a_repository_without_a_record_is_not_managed(self):
        empty = Path(self._tmp.name) / "plain"
        init_git_repo(empty)
        facts = read_repository(empty)
        self.assertFalse(facts.managed)
        self.assertTrue(facts.problems)

    def test_a_corrupt_record_is_reported_with_its_own_remedy(self):
        (self.target / ".workflow-manager" / "installation.json").write_text("{")
        facts = self.facts()
        self.assertIn("unreadable", facts.installation_error)
        self.assertFalse(self.report(facts=facts).inspection_complete)

    def test_work_items_and_the_config_default_are_read(self):
        self.set_state({"a": item("PLANNING", "2.1", "product"),
                        "b": item("MILESTONE_COMPLETE", "1")}, active="a")
        facts = self.facts()
        self.assertEqual([(i.id, i.phase, i.governing, i.work_item_type) for i in facts.items],
                         [("a", "PLANNING", "2.1", "product"), ("b", "MILESTONE_COMPLETE", "1", "process")])
        self.assertEqual(facts.active_work_item_id, "a")
        self.assertEqual(facts.config_default, "2.2")
        self.assertFalse(facts.gate_policy_present)
        self.assertEqual(facts.problems, [])

    def test_active_and_legacy_definitions(self):
        self.set_state({"d": item("MILESTONE_COMPLETE", "1"), "l": item("LEGACY_READY", "1"),
                        "g": item("PLANNING", "1"), "n": item("PLANNING", "2.2")})
        by_id = {i.id: i for i in self.facts().items}
        self.assertFalse(by_id["d"].active)
        self.assertTrue(by_id["l"].active and by_id["l"].legacy)
        self.assertTrue(by_id["g"].legacy)
        self.assertFalse(by_id["n"].legacy)

    def test_the_gate_policy_file_is_noticed(self):
        self.put(comp.GATE_POLICY_PATH, comp.HUMAN_GATE_POLICY)
        self.assertTrue(self.facts().gate_policy_present)

    def test_reading_writes_nothing(self):
        self.set_state({"a": item()})
        self.set_artifacts("a")
        self.commit()
        before = sorted((p.relative_to(self.target).as_posix(), p.read_bytes() if p.is_file() else None)
                        for p in self.target.rglob("*") if ".git/" not in p.as_posix()
                        or p.name == "index")
        self.facts()
        after = sorted((p.relative_to(self.target).as_posix(), p.read_bytes() if p.is_file() else None)
                       for p in self.target.rglob("*") if ".git/" not in p.as_posix()
                       or p.name == "index")
        self.assertEqual(before, after)


class TestIncompleteInspection(Case):
    """Each cause is a finding, and a nonzero `doctor` exit, never a clean one."""

    def assertIncomplete(self, report, fragment):
        self.assertTrue(report.has("incomplete-inspection"), report.ids())
        detail = " ".join(f.detail for f in report.findings if f.id == "incomplete-inspection")
        self.assertIn(fragment, detail)
        self.assertFalse(report.inspection_complete)
        self.assertEqual(report.headline, "inspection incomplete")
        self.assertEqual(report.doctor_exit_code, 1)
        self.assertNotIn(BLOCKED, [f.severity for f in report.findings])   # N2: advisory

    def test_a_missing_state_file(self):
        (self.target / STATE).unlink()
        self.assertIncomplete(self.report(), "missing")

    def test_malformed_json(self):
        self.put(STATE, "{not json")
        self.assertIncomplete(self.report(), "cannot be read as JSON")

    def test_an_unsupported_schema_version(self):
        self.put(STATE, {"schema_version": 7, "work_items": {}})
        self.assertIncomplete(self.report(), "schema_version 7")

    def test_a_governing_version_outside_the_known_three(self):
        self.set_state({"a": item(governing="3.0")})
        self.assertIncomplete(self.report(), "governing_workflow_version '3.0'")

    def test_an_item_of_the_wrong_shape(self):
        self.set_state({"a": "oops"})
        self.assertIncomplete(self.report(), "is not an object")

    def test_a_field_of_the_wrong_shape(self):
        self.set_state({"a": item(wtype=7)})
        self.assertIncomplete(self.report(), "work_item_type")

    def test_an_unknown_phase_is_shown_and_treated_as_implementing_or_later(self):
        self.set_state({"a": item("BRAND_NEW_PHASE")})
        facts = self.facts()
        self.assertTrue(facts.items[0].implementing_or_later)
        self.assertIncomplete(self.report(facts=facts), "BRAND_NEW_PHASE")

    def test_a_missing_artifacts_file_for_an_active_item(self):
        self.set_state({"a": item()})
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py"]))
        self.assertIncomplete(report, "missing or unreadable")

    def test_an_artifacts_file_without_plan_stage(self):
        self.set_state({"a": item("PLANNING")})
        self.set_artifacts("a", plan_stage=False)
        self.assertIncomplete(self.report(plan=fake_plan(self.target)), "no plan_stage")

    def test_an_artifacts_file_without_implementation_stage_for_an_implementing_process_item(self):
        self.set_state({"a": item()})
        self.set_artifacts("a", impl_stage=False)
        self.assertIncomplete(self.report(plan=fake_plan(self.target)), "no implementation_stage")

    def test_a_configured_clean_filter_skips_status_without_running_it(self):
        self.commit()
        marker = self.target / "filter-ran"
        subprocess.run(["git", "-C", str(self.target), "config", "filter.x.clean",
                        f"touch {marker}; cat"], check=True)
        facts = self.facts()
        self.assertIsNone(facts.dirty)
        self.assertFalse(marker.exists())
        self.assertIncomplete(self.report(facts=facts), "clean/process filter")

    def test_a_failed_git_call_a_detector_needed(self):
        self.set_state({"a": item()})
        self.commit()
        real = comp.run_git

        def failing(repo, *args):
            return GitResult(128) if args[:1] == ("log",) else real(repo, *args)
        with mock.patch.object(comp, "run_git", failing):
            facts = self.facts()
        self.assertIsNone(facts.retirement_trailer)
        self.assertIncomplete(self.report(facts=facts), "`git log` failed")

    def test_not_a_git_repository(self):
        plain = Path(self._tmp.name) / "nogit"
        plain.mkdir()
        self.assertTrue(any("Git" in p for p in read_repository(plain).problems))

    def test_an_item_id_outside_the_workflow_grammar(self):
        self.set_state({"Bad/Id": item()})
        self.assertIncomplete(self.report(), "not a valid id")


class TestPartialClone(Case):
    def probe_log(self):
        calls = []
        real = comp.run_git

        def recording(repo, *args):
            calls.append(args)
            return real(repo, *args)
        return calls, recording

    def test_an_ordinary_repository_runs_status_and_log_and_is_complete(self):
        self.set_state({"a": item("PLANNING")})
        self.set_artifacts("a")
        self.commit()
        calls, recording = self.probe_log()
        with mock.patch.object(comp, "run_git", recording):
            facts = self.facts()
        verbs = [c[0] for c in calls]
        self.assertIn("status", verbs)
        self.assertIn("log", verbs)
        self.assertFalse(facts.partial_clone)
        self.assertEqual(facts.problems, [])
        self.assertEqual(facts.dirty, False)

    def test_a_partial_clone_skips_the_object_reads(self):
        subprocess.run(["git", "-C", str(self.target), "config", "extensions.partialClone", "origin"],
                       check=True)
        calls, recording = self.probe_log()
        with mock.patch.object(comp, "run_git", recording):
            facts = self.facts()
        verbs = [c[0] for c in calls]
        self.assertNotIn("status", verbs)
        self.assertNotIn("log", verbs)
        self.assertTrue(facts.partial_clone)
        self.assertIsNone(facts.dirty)
        self.assertTrue(any("partial clone" in p for p in facts.problems))

    def test_a_promisor_remote_alone_is_a_partial_clone(self):
        subprocess.run(["git", "-C", str(self.target), "config", "remote.origin.promisor", "true"],
                       check=True)
        self.assertTrue(self.facts().partial_clone)

    def test_a_failed_or_timed_out_detection_skips_the_reads_too(self):
        for bad in (GitResult(128), GitResult(None)):
            calls, recording = self.probe_log()
            real = comp.run_git

            def failing(repo, *args, bad=bad, recording=recording):
                if args[:2] == ("config", "--get"):
                    return bad
                return recording(repo, *args)
            with mock.patch.object(comp, "run_git", failing):
                facts = self.facts()
            self.assertNotIn("status", [c[0] for c in calls])
            self.assertTrue(any("detection failed" in p for p in facts.problems))

    def test_the_outcome_does_not_depend_on_git_honouring_no_lazy_fetch(self):
        subprocess.run(["git", "-C", str(self.target), "config", "extensions.partialClone", "origin"],
                       check=True)
        with mock.patch.object(comp, "_GIT_ENVIRONMENT",
                               {k: v for k, v in comp._GIT_ENVIRONMENT.items() if k != "GIT_NO_LAZY_FETCH"}):
            self.assertTrue(self.facts().partial_clone)


class TestRunGit(Case):
    def test_the_hermetic_flags_and_environment(self):
        argv = comp.git_argv(self.target, "status")
        for flag in ("--no-optional-locks", "core.fsmonitor=false", "core.untrackedCache=false",
                     "gc.auto=0", "maintenance.auto=false", "core.hooksPath=/dev/null"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[:3], ["git", "-C", str(self.target)])
        seen = {}

        def fake(argv, **kwargs):
            seen.update(kwargs["env"])
            return subprocess.CompletedProcess(argv, 0, "out", "")
        with mock.patch.object(comp.subprocess, "run", fake):
            comp.run_git(self.target, "status")
        self.assertEqual(seen["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(seen["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(seen["GIT_NO_LAZY_FETCH"], "1")

    def test_repository_selecting_variables_are_not_inherited(self):
        seen = {}

        def fake(argv, **kwargs):
            seen.update(kwargs["env"])
            return subprocess.CompletedProcess(argv, 0, "out", "")
        hostile = {name: "/elsewhere" for name in comp._REPOSITORY_SELECTORS}
        with mock.patch.dict(comp.os.environ, hostile), \
                mock.patch.object(comp.subprocess, "run", fake):
            comp.run_git(self.target, "status")
        self.assertEqual(set(seen) & comp._REPOSITORY_SELECTORS, set())
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                     "GIT_OBJECT_DIRECTORY"):
            self.assertIn(name, comp._REPOSITORY_SELECTORS)

    def test_exit_status_is_returned_and_failures_are_marked(self):
        absent = comp.run_git(self.target, "config", "--get", "extensions.partialClone")
        self.assertEqual((absent.returncode, absent.stdout), (1, ""))
        with mock.patch.object(comp.subprocess, "run", side_effect=OSError):
            self.assertIsNone(comp.run_git(self.target, "status").returncode)
        with mock.patch.object(comp.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("git", 1)):
            self.assertIsNone(comp.run_git(self.target, "status").returncode)

    def test_the_trailer_searches_are_two_anchored_greps_scoped_to_head(self):
        calls = []
        real = comp.run_git

        def recording(repo, *args):
            calls.append(args)
            return real(repo, *args)
        self.commit()
        with mock.patch.object(comp, "run_git", recording):
            self.facts()
        logs = [c for c in calls if c[0] == "log"]
        self.assertEqual(len(logs), 2)
        greps = sorted(g for c in logs for g in c if g.startswith("--grep="))
        self.assertEqual(greps, [r"--grep=^Workflow-Activation: 2\.2[[:space:]]*$",
                                 "--grep=^Workflow-Legacy-Retirement:"])
        for c in logs:
            self.assertEqual(c[-1], "HEAD")
            self.assertNotIn("--all", c)
            self.assertEqual(sum(a.startswith("--grep=") for a in c), 1)
            self.assertIn("--extended-regexp", c)
        self.assertEqual(sum("\\\\" in g for g in greps), 0)   # a single backslash

    def test_relative_git_common_dir_is_resolved_against_the_target(self):
        self.assertEqual(comp._resolve_git_path(Path("/a/b"), ".git\n"), Path("/a/b/.git"))
        self.assertEqual(comp._resolve_git_path(Path("/a/b"), "../.git"), Path("/a/.git"))
        self.assertEqual(comp._resolve_git_path(Path("/a/b"), "/x/.git"), Path("/x/.git"))


class TestTrailers(Case):
    def test_a_trailer_in_head_is_found_and_attributed(self):
        self.commit("retire\n\nWorkflow-Legacy-Retirement: old-item\nWorkflow-Work-Item: old-item")
        facts = self.facts()
        self.assertTrue(facts.retirement_trailer)
        self.assertFalse(facts.activation_trailer)

    def test_the_activation_trailer(self):
        self.commit("activate\n\nWorkflow-Activation: 2.2")
        facts = self.facts()
        self.assertTrue(facts.activation_trailer)
        self.assertFalse(facts.retirement_trailer)

    def test_a_message_quoting_the_name_mid_line_does_not_count(self):
        self.commit("we mention Workflow-Legacy-Retirement: x and Workflow-Activation: 2.2 in prose")
        facts = self.facts()
        self.assertFalse(facts.retirement_trailer)
        self.assertFalse(facts.activation_trailer)

    def test_a_trailer_on_another_ref_does_not_count(self):
        self.commit("base")
        subprocess.run(["git", "-C", str(self.target), "checkout", "-q", "-b", "side"], check=True)
        self.commit("retire\n\nWorkflow-Legacy-Retirement: old-item")
        subprocess.run(["git", "-C", str(self.target), "checkout", "-q", "main"], check=True)
        self.assertFalse(self.facts().retirement_trailer)

    def test_the_search_is_an_approximation_not_a_trailer_parse(self):
        # A line that starts with the trailer text but sits outside the final
        # trailer block still matches: the report words it "trailer-shaped".
        self.commit("subject\n\nWorkflow-Legacy-Retirement: x\n\nand then more prose")
        self.assertTrue(self.facts().retirement_trailer)
        self.set_state({})
        report = self.report(installed="2.9.0", target="2.8.0")
        self.assertIn("trailer-shaped", next(f for f in report.findings if f.id == "downgrade").detail)

    def test_an_unborn_head_has_no_trailers_and_no_problem(self):
        fresh = Path(self._tmp.name) / "fresh"
        init_git_repo(fresh)
        facts = read_repository(fresh)
        self.assertFalse(facts.retirement_trailer)
        self.assertFalse(any("git log" in p.lower() for p in facts.problems))


class TestWorktreesAndWitnesses(Case):
    def test_a_linked_worktree_is_counted(self):
        self.commit()
        linked = Path(self._tmp.name) / "linked"
        subprocess.run(["git", "-C", str(self.target), "worktree", "add", "-q", str(linked), "-b", "w"],
                       check=True)
        self.assertEqual(self.facts().worktree_count, 2)
        self.assertEqual(read_repository(linked).worktree_count, 2)

    def test_amendment_witnesses_are_listed_from_the_common_git_dir(self):
        claims = self.target / ".git" / comp.CLAIMS_RELDIR
        claims.mkdir(parents=True)
        (claims / ("a" * 64 + ".amendment.json")).write_text("{}")
        (claims / ("b" * 64 + ".json")).write_text("{}")
        self.assertEqual(self.facts().amendment_witnesses, ["a" * 64 + ".amendment.json"])

    def test_a_witness_is_found_from_a_linked_worktree_too(self):
        self.commit()
        linked = Path(self._tmp.name) / "linked"
        subprocess.run(["git", "-C", str(self.target), "worktree", "add", "-q", str(linked), "-b", "w"],
                       check=True)
        claims = self.target / ".git" / comp.CLAIMS_RELDIR
        claims.mkdir(parents=True)
        (claims / ("c" * 64 + ".amendment.json")).write_text("{}")
        self.assertEqual(len(read_repository(linked).amendment_witnesses), 1)


# ---------------------------------------------------------------------------


class TestHazardV240001(Case):
    """An update rewrites paths an active item's declarations protect."""

    def impl(self, **kwargs):
        self.set_state({"a": item(**kwargs.pop("item", {}))})
        self.set_artifacts("a", **kwargs)

    def finding(self, report, fid):
        return next(f for f in report.findings if f.id == fid)

    def test_a_process_item_at_implementing_with_protected_scripts(self):
        self.impl(impl_prefixes=["scripts/"], plan_excluded=["scripts/x.py"])
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py", "README.md"]))
        found = self.finding(report, "v2.4.0-001")
        self.assertEqual(found.severity, WARNING)
        self.assertIn("implementation stage", found.detail)
        self.assertIn("scripts/x.py", found.detail)
        self.assertIn("AWAITING_TECHNICAL_APPROVAL", found.detail)

    def test_the_same_item_at_a_plan_phase_has_no_implementation_stage_finding(self):
        self.impl(item={"phase": "PLANNING"}, impl_prefixes=["scripts/"], plan_excluded=["scripts/x.py"])
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py"]))
        self.assertFalse(report.has("v2.4.0-001"))

    def test_amending_plan_counts_as_implementing(self):
        self.impl(item={"phase": "AMENDING_PLAN"}, impl_prefixes=["scripts/"], plan_excluded=["scripts/x.py"])
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py"]))
        self.assertTrue(report.has("v2.4.0-001"))

    def test_a_removal_counts_like_a_write(self):
        self.impl(impl_prefixes=["scripts/"], plan_excluded=["scripts/x.py"])
        report = self.report(plan=fake_plan(self.target, removals=["scripts/x.py"]))
        self.assertTrue(report.has("v2.4.0-001"))

    def test_a_merge_only_update_triggers_when_the_item_protects_claude_md(self):
        self.impl(impl_protected=["CLAUDE.md"], plan_excluded=["CLAUDE.md"])
        report = self.report(plan=fake_plan(self.target, writes=["CLAUDE.md"]))
        self.assertIn("CLAUDE.md", self.finding(report, "v2.4.0-001").detail)

    def test_a_managed_docs_path_the_declarations_protect(self):
        path = "docs/ai-workflow/MILESTONE_WORKFLOW.md"
        self.impl(impl_protected=[path], plan_excluded=[path])
        report = self.report(plan=fake_plan(self.target, writes=[path]))
        self.assertIn(path, self.finding(report, "v2.4.0-001").detail)

    def test_an_exclusion_does_not_override_an_earlier_protection(self):
        path = "docs/ai-workflow/REVIEW_PROTOCOL.md"
        self.impl(impl_protected=[path], impl_excluded_prefixes=["docs/"], plan_excluded=[path])
        report = self.report(plan=fake_plan(self.target, writes=[path]))
        self.assertTrue(report.has("v2.4.0-001"))

    def test_an_excluded_path_is_not_a_hazard(self):
        self.impl(impl_prefixes=["scripts/"], impl_excluded=["README.md"], plan_excluded=["README.md"])
        report = self.report(plan=fake_plan(self.target, writes=["README.md"]))
        self.assertFalse(report.has("v2.4.0-001"))
        self.assertFalse(report.has("unclassified-paths"))

    def test_a_missing_declarations_file_falls_back_to_the_heuristic_and_says_so(self):
        self.set_state({"a": item()})
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py", ".claude/commands/y.md",
                                                                  "README.md"]))
        found = self.finding(report, "v2.4.0-001")
        self.assertIn("heuristic", found.detail)
        self.assertIn(".claude/commands/y.md", found.detail)
        self.assertNotIn("README.md", found.detail)
        self.assertTrue(report.has("incomplete-inspection"))

    def test_a_product_item_has_no_implementation_stage_finding(self):
        self.impl(item={"work_item_type": "product"}, impl_prefixes=["scripts/"],
                  plan_excluded=["scripts/x.py"])
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py"]))
        self.assertFalse(report.has("v2.4.0-001"))

    def test_an_implementing_product_item_without_implementation_stage_is_incomplete(self):
        self.impl(item={"work_item_type": "product"}, impl_stage=False,
                  plan_excluded=["scripts/x.py"])
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py"]))
        self.assertTrue(report.has("incomplete-inspection"))
        self.assertEqual(report.headline, "inspection incomplete")
        self.assertIn("no implementation_stage", report.findings[0].detail
                      if report.findings[0].id == "incomplete-inspection" else
                      next(f.detail for f in report.findings if f.id == "incomplete-inspection"))

    def test_a_product_item_that_plan_protects_a_managed_path(self):
        path = "docs/ai-workflow/REVIEW_PROTOCOL.md"
        self.impl(item={"work_item_type": "product", "phase": "PLANNING"}, plan_protected=[path])
        report = self.report(plan=fake_plan(self.target, writes=[path]))
        found = self.finding(report, "v2.4.0-001")
        self.assertIn("plan stage", found.detail)
        self.assertNotIn("implementation stage", found.detail)

    def test_a_plan_phase_item_that_plan_protects_a_managed_path(self):
        path = "docs/ai-workflow/MILESTONE_WORKFLOW.md"
        self.impl(item={"phase": "PLANNING"}, plan_protected=[path])
        report = self.report(plan=fake_plan(self.target, writes=[path]))
        self.assertIn("ReviewedContentDriftError", self.finding(report, "v2.4.0-001").detail)

    def test_a_completed_item_is_ignored(self):
        self.impl(item={"phase": "MILESTONE_COMPLETE"}, impl_prefixes=["scripts/"])
        report = self.report(plan=fake_plan(self.target, writes=["scripts/x.py"]))
        self.assertFalse(report.has("v2.4.0-001"))

    def test_no_plan_means_no_path_findings(self):
        self.impl(impl_prefixes=["scripts/"])
        self.assertFalse(self.report(plan=None).has("v2.4.0-001"))

    def test_the_old_target_warning(self):
        self.impl(impl_prefixes=["scripts/"])
        old = self.report(plan=fake_plan(self.target), target="2.5.1")
        self.assertTrue(old.has("v2.4.0-001-old"))
        self.assertFalse(self.report(plan=fake_plan(self.target), target="2.6.0").has("v2.4.0-001-old"))
        self.impl(item={"phase": "PLANNING"})
        self.assertFalse(self.report(plan=fake_plan(self.target), target="2.5.1").has("v2.4.0-001-old"))


class TestUnclassifiedPaths(Case):
    def test_a_path_neither_stage_classifies(self):
        self.set_state({"a": item("PLANNING")})
        self.set_artifacts("a", plan_excluded=["README.md"])
        report = self.report(plan=fake_plan(self.target, writes=["README.md", ".claude/new.md"]))
        found = next(f for f in report.findings if f.id == "unclassified-paths")
        self.assertIn("plan stage: .claude/new.md", found.detail)
        self.assertNotIn("README.md", found.detail)
        self.assertIn("UnclassifiedPathError", found.detail)

    def test_the_stages_can_disagree_and_each_is_reported(self):
        self.set_state({"a": item()})
        self.set_artifacts("a", impl_prefixes=[".claude/"], plan_excluded=["README.md"])
        report = self.report(plan=fake_plan(self.target, writes=[".claude/settings.json"]))
        found = next(f for f in report.findings if f.id == "unclassified-paths")
        self.assertIn("plan stage: .claude/settings.json", found.detail)
        self.assertNotIn("implementation stage", found.detail)

    def test_the_installation_record_is_never_reported(self):
        self.set_state({"a": item()})
        self.set_artifacts("a")
        report = self.report(plan=fake_plan(self.target, writes=[comp.INSTALLATION_RECORD_PATH]))
        self.assertFalse(report.has("unclassified-paths"))

    def test_other_workflow_manager_paths_still_fail_closed(self):
        self.set_state({"a": item()})
        self.set_artifacts("a")
        report = self.report(plan=fake_plan(self.target, writes=[".workflow-manager/other.json"]))
        self.assertTrue(report.has("unclassified-paths"))


class TestLegacy(Case):
    def finding(self, report, wid):
        return next(f for f in report.findings if f.id == "legacy-active" and wid in f.title)

    def test_an_active_governing_1_item_is_named(self):
        self.set_state({"a": item("IMPLEMENTING", "1")}, active="a")
        report = self.report()
        found = self.finding(report, "a")
        self.assertEqual(found.severity, WARNING)
        self.assertEqual(found.commands, ())
        self.assertIn("LEGACY_READY", found.detail)

    def test_a_dormant_item_is_offered_retirement_for_a_2_9_0_target(self):
        self.set_state({"a": item("LEGACY_READY", "1"), "b": item("PLANNING", "2.2")}, active="b")
        found = self.finding(self.report(target="2.9.0"), "a")
        self.assertEqual([c.argv for c in found.commands], [("/retire-legacy-work-item", "a")])
        self.assertEqual(found.commands[0].family, comp.FAMILY_SLASH)

    def test_not_offered_for_an_older_target(self):
        self.set_state({"a": item("LEGACY_READY", "1")}, active="zzz")
        found = self.finding(self.report(target="2.8.0"), "a")
        self.assertEqual(found.commands, ())
        self.assertIn("2.9.0", found.detail)

    def test_not_offered_for_the_active_pointer(self):
        self.set_state({"a": item("LEGACY_READY", "1")}, active="a")
        found = self.finding(self.report(target="2.9.0"), "a")
        self.assertEqual(found.commands, ())
        self.assertIn("active", found.detail)

    def test_not_offered_with_unfinished_children(self):
        self.set_state({"a": item("LEGACY_READY", "1"), "kid": item("PLANNING", "2.2", parent="a")},
                       active="kid")
        found = self.finding(self.report(target="2.9.0"), "a")
        self.assertEqual(found.commands, ())
        self.assertIn("kid", found.detail)

    def test_a_finished_child_does_not_block(self):
        self.set_state({"a": item("LEGACY_READY", "1"),
                        "kid": item("MILESTONE_COMPLETE", "2.2", parent="a")}, active="zzz")
        self.assertTrue(self.finding(self.report(target="2.9.0"), "a").commands)

    def test_not_offered_for_a_non_dormant_item(self):
        self.set_state({"a": item("AWAITING_USER_ACCEPTANCE", "1")}, active="zzz")
        self.assertIn("AWAITING_USER_ACCEPTANCE", self.finding(self.report(target="2.9.0"), "a").detail)

    def test_the_retirement_advice_matches_the_published_writer(self):
        with workflow_modules() as m:
            ws = m["workflow_state"]
            cases = {
                "ok": (state({"a": item("LEGACY_READY", "1")}, active="b"), True),
                "active": (state({"a": item("LEGACY_READY", "1")}, active="a"), False),
                "phase": (state({"a": item("PLANNING", "1")}, active="b"), False),
                "kids": (state({"a": item("LEGACY_READY", "1"),
                                "k": item("PLANNING", "2.2", parent="a")}, active="b"), False),
            }
            for name, (st, offered) in cases.items():
                confirmation = f"I confirm retirement of a"
                try:
                    with mock.patch.object(ws, "validate_user_only_confirmation", lambda *a, **k: None):
                        ws.retire_legacy_work_item(st, "a", NOW, confirmation)
                    accepted = True
                except (ws.LegacyRetirementWrongPhaseError, ws.LegacyRetirementActiveItemError,
                        ws.LegacyRetirementUnfinishedChildrenError):
                    accepted = False
                self.set_state(st["work_items"], active=st["active_work_item_id"])
                facts = self.facts()
                command, _ = comp._retirement_advice(facts, next(i for i in facts.items if i.id == "a"),
                                                     "2.9.0")
                self.assertEqual((command is not None), accepted, name)
                self.assertEqual(accepted, offered, name)


class TestGatesChange(Case):
    def test_crossing_2_8_0_without_a_policy(self):
        self.set_state({"p": item("PLANNING", "1"), "q": item("PLANNING", "2.1"),
                        "r": item("PLANNING", "2.2"), "done": item("MILESTONE_COMPLETE", "2.2")})
        found = next(f for f in self.report(installed="2.7.0", target="2.9.0").findings
                     if f.id == "gates-change")
        self.assertEqual(found.severity, WARNING)
        detail = found.detail
        self.assertIn("p (governing 1): becomes automatic: acceptance; stays human: "
                      "plan_approval, technical_approval", detail)
        self.assertIn("q (governing 2.1): becomes automatic: plan_approval, acceptance; "
                      "stays human: technical_approval", detail)
        self.assertIn("r (governing 2.2): becomes automatic: plan_approval, technical_approval, "
                      "acceptance; stays human: none", detail)
        self.assertNotIn("done", detail)
        self.assertIn('"human_approval": true', detail)
        self.assertIn(comp.GATE_POLICY_PATH, detail)

    def test_the_gate_table_drives_the_finding(self):
        self.set_state({"r": item("PLANNING", "2.2")})
        table = {v: "" for v in PINNED_VERSIONS}
        for entries, expected in (({"2.9.0": "2.9.0 moves gates"}, True), ({}, False)):
            with mock.patch.object(comp, "GATE_DEFAULT_CHANGES", {**table, **entries}):
                found = self.report(installed="2.8.0", target="2.9.0").has("gates-change")
            self.assertEqual(found, expected)

    def test_not_when_a_policy_exists_or_the_range_misses_2_8_0(self):
        self.set_state({"r": item("PLANNING", "2.2")})
        self.assertFalse(self.report(installed="2.8.0", target="2.9.0").has("gates-change"))
        self.assertFalse(self.report(installed="2.5.0", target="2.7.0").has("gates-change"))
        self.put(comp.GATE_POLICY_PATH, comp.HUMAN_GATE_POLICY)
        self.assertFalse(self.report(installed="2.7.0", target="2.9.0").has("gates-change"))


class TestDowngrade(Case):
    def downgrade(self, target, installed="2.9.0", **kwargs):
        report = self.report(installed=installed, target=target, **kwargs)
        return next((f for f in report.findings if f.id == "downgrade"), None)

    def test_no_downgrade_no_finding(self):
        self.assertIsNone(self.downgrade("2.9.0"))
        self.assertIsNone(self.downgrade("2.9.0", installed="2.8.0"))

    def test_it_is_unsupported_and_never_says_safe(self):
        self.set_state({})
        found = self.downgrade("2.8.0")
        self.assertIn("unsupported", found.detail)
        self.assertIn("not a statement that the downgrade is safe", found.detail)
        self.assertEqual(found.severity, WARNING)

    def test_only_crossed_boundaries_are_listed(self):
        self.set_state({})
        detail = self.downgrade("2.8.0").detail
        self.assertIn("Crossing 2.9.0", detail)
        self.assertNotIn("Crossing 2.8.0", detail)
        detail = self.downgrade("2.6.0").detail
        for crossed in ("2.9.0", "2.8.0", "2.7.0"):
            self.assertIn(f"Crossing {crossed}", detail)
        self.assertNotIn("Crossing 2.6.0", detail)

    def assertSignal(self, version, name, setup, expect=True):
        setup()
        facts = self.facts()
        signal = next(s for s in comp.DOWNGRADE_BOUNDARIES[version].signals if s.name == name)
        found = signal.detect(facts)
        self.assertEqual(bool(found), expect, (version, name, found))
        return found

    def test_each_boundary_signal_with_and_without(self):
        S = self.set_state
        cases = [
            ("2.4.0", "needs-revalidation",
             lambda: S({"a": item(checkpoints={"CP1": {"status": "NEEDS_REVALIDATION"}})}),
             lambda: S({"a": item(checkpoints={"CP1": {"status": "COMPLETE"}})})),
            ("2.4.0", "superseded",
             lambda: S({"a": item(plan_approval={"status": "SUPERSEDED"})}),
             lambda: S({"a": item(plan_approval={"status": "CURRENT"})})),
            ("2.4.0", "amendment",
             lambda: S({"a": item("AMENDING_PLAN")}),
             lambda: S({"a": item()})),
            ("2.4.0", "amendment",
             lambda: S({"a": item(amendment_history=[{"sequence": 1}])}),
             lambda: S({"a": item(amendment_history=[])})),
            ("2.5.0", "governing-2.2", lambda: S({"a": item(governing="2.2")}),
             lambda: S({"a": item(governing="2.1")})),
            ("2.5.0", "implementation-review-phase",
             lambda: S({"a": item("AWAITING_LOCAL_IMPLEMENTATION_REVIEW")}),
             lambda: S({"a": item("AWAITING_EXTERNAL_IMPLEMENTATION_REVIEW")})),
            ("2.5.0", "implementation-review-stages",
             lambda: S({"a": item(implementation_review_stages=[{"stage": "LOCAL"}])}),
             lambda: S({"a": item(implementation_review_stages=None)})),
            ("2.5.1", "suffixed-amendment",
             lambda: S({"a": item("AMENDING_PLAN", checkpoints={"CP4B": {}})}),
             lambda: S({"a": item("AMENDING_PLAN", checkpoints={"CP4": {}})})),
            ("2.5.1", "suffixed-amendment",
             lambda: S({"a": item("AMENDING_PLAN", checkpoints={"CP4B": {}})}),
             lambda: S({"a": item(checkpoints={"CP4B": {}})})),
            ("2.6.0", "feedback-layout", lambda: S({"a": item(feedback_layout="scoped")}),
             lambda: S({"a": item(feedback_layout="flat")})),
            ("2.6.0", "plan-review-binding", lambda: S({"a": item(plan_review_binding={"x": 1})}),
             lambda: S({"a": item(plan_review_binding=None)})),
            ("2.6.0", "plan-inputs",
             lambda: (S({"a": item()}), (self.target / ".ai-review/a/plan-inputs").mkdir(parents=True)),
             lambda: (S({"a": item()}), shutil.rmtree(self.target / ".ai-review/a/plan-inputs"),
                      (self.target / ".ai-review/a/current").mkdir(parents=True))),
            ("2.6.0", "resolved-review-content-id",
             lambda: S({"a": item(amendment_history=[{"resolved_review_content_id": "abc"}])}),
             lambda: S({"a": item(amendment_history=[{"resolved_review_content_id": None}])})),
            ("2.7.0", "consumed-plan-review-content-ids",
             lambda: S({"a": item(consumed_plan_review_content_ids=["abc"])}),
             lambda: S({"a": item(consumed_plan_review_content_ids=[])})),
            ("2.8.0", "policy-satisfied",
             lambda: S({"a": item(plan_approval={"basis": "POLICY_SATISFIED"})}),
             lambda: S({"a": item(plan_approval={"basis": "EXTERNAL_APPROVE"})})),
            ("2.8.0", "gate-evidence", lambda: S({"a": item(gate_evidence={"x": 1})}),
             lambda: S({"a": item()})),
            ("2.8.0", "reopenings", lambda: S({"a": item(reopenings=[{"x": 1}])}),
             lambda: S({"a": item(reopenings=[])})),
            ("2.8.0", "acceptance-satisfaction",
             lambda: S({"a": item(acceptance_satisfaction={"x": 1})}), lambda: S({"a": item()})),
            ("2.8.0", "ledger-audit",
             lambda: S({"a": item(plan_review_stages=[{"run_ref": "session:local x"}])}),
             lambda: S({"a": item(plan_review_stages=[{}])})),
            ("2.8.0", "gate-policy-adoption",
             lambda: S({}, gate_policy_adoption={"policy": 1}), lambda: S({})),
            ("2.8.0", "gate-policy-floor",
             lambda: S({}, gate_policy_floor={"x": 1}), lambda: S({})),
        ]
        for version, name, present, absent in cases:
            with self.subTest(version=version, name=name):
                self.assertSignal(version, name, present, True)
                self.assertSignal(version, name, absent, False)

    def test_activation_signals(self):
        self.set_state({})
        self.assertTrue(self.assertSignal("2.5.0", "activation", lambda: None))   # the config default
        self.put(comp.CONFIG_PATH, {"schema_version": 1, "default_workflow_version": "2.1"})
        self.assertSignal("2.5.0", "activation", lambda: None, expect=False)
        self.commit("activate\n\nWorkflow-Activation: 2.2")
        self.assertSignal("2.5.0", "activation", lambda: None, expect=True)

    def test_the_retirement_signal_and_the_witness_signal(self):
        self.set_state({})
        self.assertSignal("2.9.0", "legacy-retirement", lambda: None, expect=False)
        self.commit("r\n\nWorkflow-Legacy-Retirement: x")
        self.assertSignal("2.9.0", "legacy-retirement", lambda: None, expect=True)
        claims = self.target / ".git" / comp.CLAIMS_RELDIR
        claims.mkdir(parents=True)
        (claims / ("d" * 64 + ".amendment.json")).write_text("{}")
        self.assertSignal("2.6.0", "amendment-witness", lambda: None, expect=True)

    def test_a_registry_file_supplies_letter_suffixed_ids(self):
        self.set_state({"a": item("AMENDING_PLAN")})
        self.put("docs/ai-workflow/registry/a-registry.json", {"checkpoints": [{"id": "CP6B"}]})
        self.assertSignal("2.5.1", "suffixed-amendment", lambda: None, expect=True)

    def test_the_report_names_what_it_found_and_what_it_cannot_detect(self):
        self.set_state({"a": item(consumed_plan_review_content_ids=["abc"])})
        detail = self.downgrade("2.6.0").detail
        self.assertIn("consumed_plan_review_content_ids", detail)
        self.assertIn("a hazard the report cannot detect", detail)
        self.assertIn("Orchestration Protocol", detail)
        self.set_state({})
        self.assertIn("no signal", self.downgrade("2.8.0").detail)


class TestMiscFindings(Case):
    def test_dirty_tree(self):
        self.commit()
        self.assertFalse(self.report().has("dirty-tree"))
        (self.target / "scratch.txt").write_text("x")
        report = self.report()
        self.assertEqual(next(f for f in report.findings if f.id == "dirty-tree").severity, WARNING)

    def test_worktrees(self):
        self.commit()
        linked = Path(self._tmp.name) / "linked"
        subprocess.run(["git", "-C", str(self.target), "worktree", "add", "-q", str(linked), "-b", "w"],
                       check=True)
        self.assertTrue(self.report(installed="2.5.1", target="2.6.0").has("worktrees"))
        self.assertFalse(self.report(installed="2.6.0", target="2.7.0").has("worktrees"))
        self.assertFalse(self.report(installed="2.5.0", target="2.5.1").has("worktrees"))

    def test_new_work_only_notes_cover_the_range_installed_to_target(self):
        report = self.report(installed="2.8.0", target="2.9.0")
        notes = [f for f in report.findings if f.id == "new-work-only"]
        self.assertTrue(notes)
        self.assertTrue(all(f.severity == NOTE and f.title.startswith("2.9.0") for f in notes))
        self.assertIn("never edits an existing WORKFLOW_CONFIG.json", " ".join(f.title for f in notes))
        self.assertEqual([f for f in self.report(installed="2.9.0", target="2.9.0").findings
                          if f.id == "new-work-only"], [])

    def test_the_refusals_are_blocked_findings_that_quote_the_text(self):
        drift = self.report(refusal=DriftError("refusing to update: edited", []))
        found = next(f for f in drift.findings if f.id == "refused-drift")
        self.assertEqual(found.severity, BLOCKED)
        self.assertIn("refusing to update: edited", found.detail)
        self.assertIn("--force", found.detail)
        coll = self.report(refusal=CollisionError("refusing: in use", []))
        self.assertEqual(next(f for f in coll.findings if f.id == "refused-collision").severity, BLOCKED)
        self.assertEqual(drift.headline, "the update would be refused")

    def test_an_unresolved_installed_release_is_a_note(self):
        self.commit()
        report = self.report(installed_resolved=False)
        found = next(f for f in report.findings if f.id == "not-verified")
        self.assertEqual(found.severity, NOTE)
        self.assertEqual(report.doctor_exit_code, 0)

    def test_a_clean_repository_reports_nothing_and_exits_zero(self):
        self.set_state({})
        self.commit()
        report = self.report()
        self.assertEqual(report.ids(WARNING) + report.ids(BLOCKED), [])
        self.assertEqual(report.doctor_exit_code, 0)
        self.assertEqual(report.headline, "nothing found")


class TestReportText(Case):
    def test_headings_and_the_three_version_labels(self):
        self.set_state({"a": item("PLANNING", "2.1")}, active="a")
        text = render_report(self.report(target="2.8.0", installed="2.7.0", plan=fake_plan(self.target)))
        for heading in ("Repository", "Installed release", "Latest available", "Target of this check",
                        "Work items (governing version is a protocol version, not a release)",
                        "Config default for new work items:", "Findings", "Fixes that apply only to new work",
                        "Recovery"):
            self.assertIn(heading, text)
        for label in ("Installed release", "Latest available", "Target of this check"):
            self.assertEqual(sum(label in line for line in text.splitlines()), 1, label)
        for line in text.splitlines():
            self.assertLessEqual(sum(label in line for label in
                                     ("Installed release", "Latest available", "Target of this check")), 1)
        self.assertIn("GOVERNING", text)

    def test_the_recovery_restore_line_is_withheld_when_dirty_or_unknown(self):
        self.commit()
        clean = render_report(self.report())
        self.assertIn("restore --source=HEAD --staged --worktree", clean)
        self.assertIn("clean -n -d", clean)
        self.assertIn("discards ALL uncommitted changes", clean)
        self.assertNotIn("clean -d -f", clean)
        (self.target / "x.txt").write_text("x")
        dirty = render_report(self.report())
        self.assertNotIn("restore", dirty)
        self.assertIn("status --short", dirty)
        facts = self.facts()
        facts.dirty = None
        self.assertNotIn("restore", render_report(self.report(facts=facts)))

    def test_recovery_commands_have_families_and_the_global_option_goes_first(self):
        self.commit()
        report = self.report(target="2.8.0", installed="2.7.0", refusal=DriftError("x", []))
        commands = [c for step in report.recovery for c in step.commands]
        self.assertTrue(commands)
        for command in commands:
            self.assertIn(command.family, comp.FAMILIES)
        updates = [c for c in commands if c.family == comp.FAMILY_MANAGER]
        self.assertTrue(updates)
        for command in updates:
            self.assertEqual(command.argv[:3], ("workflow-manager", "--release-version", "2.8.0"))
            self.assertEqual(command.argv[3], "update")
        self.assertTrue(any("--force" in c.argv for c in updates))

    def test_a_path_with_spaces_and_metacharacters_is_quoted(self):
        weird = Path(self._tmp.name) / "my repo $(x);y"
        init_git_repo(weird)
        bootstrap(weird, support.release(LATEST), now=NOW)
        subprocess.run(["git", "-C", str(weird), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(weird), "commit", "-q", "-m", "i"], check=True)
        report = build_report(read_repository(weird), None, target_version=LATEST, latest_version=LATEST,
                              pinned_versions=PINNED_VERSIONS, target_arg=str(weird))
        import shlex
        for step in report.recovery:
            for command in step.commands:
                self.assertEqual(shlex.split(command.render()), list(command.argv))
        self.assertIn(shlex.quote(str(weird)), render_report(report))

    def test_incomplete_headline_and_empty_work_items(self):
        (self.target / STATE).unlink()
        text = render_report(self.report())
        self.assertIn("inspection incomplete", text)


if __name__ == "__main__":
    unittest.main()
