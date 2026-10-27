#!/usr/bin/env python3
"""`status --retention` and `doctor --retention`: the opt-in retention section.

Hermetic: a stub `scripts/workflow_retention.py` in a scratch managed
repository prints a report built from one fixture captured from the real
script (`fixtures/retention_report.json`), or exits as told. The two
real-script cases at the end run the installed script's own copy and skip when
it is absent. No test writes into this repository.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from support import PINNED_NEWEST, REPO_ROOT, pinned_env

import retention_recipe as recipe
import test_operator_ux as ux
from test_operator_ux import run, run_in, tree_hash
from workflow_manager import retention

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retention_report.json"
SCRIPT = "scripts/workflow_retention.py"

STUB = r'''
import json, os, sys, time
marker = os.environ.get("STUB_MARKER")
if marker:
    with open(marker, "a") as handle:
        handle.write(json.dumps({"argv": sys.argv, "cwd": os.getcwd()}) + "\n")
mode = os.environ.get("STUB_MODE", "report")
if mode == "report":
    sys.stdout.write(open(os.environ["STUB_REPORT"]).read())
    if os.environ.get("STUB_WARN"):
        sys.stderr.write("warning: something\n")
elif mode == "raw":
    sys.stdout.buffer.write(open(os.environ["STUB_REPORT"], "rb").read())
elif mode == "exit":
    sys.stderr.write(os.environ.get("STUB_STDERR", "").replace("\\n", "\n"))
    sys.exit(int(os.environ["STUB_EXIT"]))
elif mode == "sleep":
    import signal, subprocess
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(os.environ["STUB_PIDFILE"], "w") as handle:
        handle.write(str(child.pid))
    def stop(*_):
        child.wait()
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    time.sleep(60)
elif mode == "stubborn":
    import subprocess
    child = subprocess.Popen([sys.executable, "-c", "import signal, time; "
                              "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
    with open(os.environ["STUB_PIDFILE"], "w") as handle:
        handle.write(str(child.pid))
    time.sleep(60)
'''


# Runs `retention.fetch` with a 1-second timeout as a child subreaper: the
# script's orphaned child is re-parented here, not to the runner's wrapper.
SUBREAPER = r"""
import ctypes, json, os, sys, time
from pathlib import Path
libc = ctypes.CDLL(None, use_errno=True)
if getattr(libc, "prctl", None) is None or libc.prctl(36, 1, 0, 0, 0) != 0:
    sys.exit(3)
sys.path.insert(0, os.environ["PYTHONPATH"])
from workflow_manager import retention
retention.TIMEOUT_SECONDS = 1
started = time.monotonic()
outcome = retention.fetch(Path(sys.argv[1]))
elapsed = time.monotonic() - started
pid = int(Path(sys.argv[2]).read_text())
def alive():
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return text.rsplit(")", 1)[1].split()[0] != "Z"
deadline = time.monotonic() + 5
while alive() and time.monotonic() < deadline:
    time.sleep(0.05)
survived = alive()
if survived:
    os.kill(pid, 9)
while True:
    try:
        os.waitpid(-1, 0)
    except ChildProcessError:
        break
print(json.dumps({"cause": outcome.refusal.cause, "elapsed": elapsed, "survived": survived}))
"""


def fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def finished(item_id="old-item", *, folder=True, tracked=0, archive=False, readable=True) -> dict:
    entry = copy.deepcopy(fixture()["finished"][0])
    entry["work_item_id"] = item_id
    entry["review_folder"].update(present=folder, tracked_files=tracked, bytes=2048 if folder else 0)
    entry["archive"].update(present=archive, readable=readable)
    return entry


def report(*entries, **overrides) -> dict:
    """The fixture with its `finished` list replaced and everything else kept
    consistent: no read error, complete, `removing` empty."""
    rep = fixture()
    rep["finished"] = list(entries)
    rep["complete"] = True
    rep["read_errors"] = []
    rep["removing"] = []
    rep["totals"].update(finished=len(entries), archives=sum(e["archive"]["present"] for e in entries),
                         prunable=0, finished_folder_bytes=sum(e["review_folder"]["bytes"] for e in entries))
    rep.update(overrides)
    return rep


def alive(pid: int) -> bool:
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return text.rsplit(")", 1)[1].split()[0] != "Z"


class Scratch(ux.TargetCase):
    """A scratch managed repository (record at 2.22.0) with the stub installed."""

    def setUp(self):
        self.repo = self.fresh()
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = "2.22.0"
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.outside, ignore_errors=True))
        self.marker = self.outside / "marker"

    def install_stub(self, repo=None):
        script = (repo or self.repo) / SCRIPT
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(STUB)

    def put_report(self, rep, name=None) -> Path:
        self._reports = getattr(self, "_reports", 0) + 1
        path = self.outside / (name or f"report-{self._reports}.json")
        path.write_text(rep if isinstance(rep, str) else json.dumps(rep))
        return path

    def env(self, **extra):
        return pinned_env(STUB_MARKER=str(self.marker), **extra)

    def invoke(self, command, retention_flag, repo=None, *, cwd=None, target=None, **env):
        args = ["--release-version", PINNED_NEWEST, command]
        if retention_flag:
            args.append("--retention")
        args.append(str(target or repo or self.repo))
        if cwd is not None:
            return run_in(cwd, *args, env=self.env(**env))
        return run(*args, env=self.env(**env))

    def both(self, command, **env):
        """`(baseline, with)`: the same command without and with the option;
        the exit codes must agree."""
        base = self.invoke(command, False, **env)
        got = self.invoke(command, True, **env)
        self.assertEqual(got.returncode, base.returncode, got.stdout + got.stderr)
        self.assertNotIn("Traceback", got.stdout + got.stderr)
        return base, got

    def section(self, command, rep, **env):
        path = self.put_report(rep)
        _, got = self.both(command, STUB_REPORT=str(path), **env)
        return got

    def one_note(self, got, cause):
        lines = [l for l in got.stdout.splitlines() if l.startswith("retention:")]
        self.assertEqual(len(lines), 1, got.stdout)
        self.assertIn(cause, lines[0])
        self.assertTrue(lines[0].startswith("retention: not available: "), lines[0])
        at = got.stdout.splitlines().index(lines[0])
        step = got.stdout.splitlines()[at + 1]
        self.assertTrue(step.startswith("  next: "), step)
        return step[len("  next: "):]


class TestDefaultOff(Scratch):
    def test_status_and_doctor_do_not_depend_on_the_script(self):
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                absent = self.invoke(command, False)
                self.install_stub()
                rep = self.put_report(report(finished()))
                present = self.invoke(command, False, STUB_REPORT=str(rep))
                (self.repo / SCRIPT).unlink()
                self.assertEqual((absent.stdout, absent.stderr, absent.returncode),
                                 (present.stdout, present.stderr, present.returncode))
                self.assertNotRegex(present.stdout + present.stderr, r"(?m)^\s*retention[ :(]")
                self.assertFalse(self.marker.exists())

    def test_the_option_is_listed_only_for_status_and_doctor(self):
        for command in ("status", "doctor"):
            self.assertIn("--retention", run(command, "--help").stdout)
        for command in ("verify", "update", "bootstrap", "uninstall"):
            self.assertNotIn("--retention", run(command, "--help").stdout)


class TestRendering(Scratch):
    def setUp(self):
        super().setUp()
        self.install_stub()

    def test_a_complete_report_prints_the_section_before_the_last_next_line(self):
        rep = report(finished("a-item"), finished("b-item", archive=True))
        got = self.section("status", rep)
        lines = got.stdout.splitlines()
        self.assertTrue(lines[-1].startswith("next: "), lines[-1])
        header = next(i for i, l in enumerate(lines) if l.startswith("retention ("))
        self.assertLess(header, len(lines) - 1)
        text = "\n".join(lines[header:])
        self.assertIn("finished work items: 2 (review folders 4.0 KiB), kept as the most recent: 3", text)
        self.assertIn("with an archive: 1 of 2; archive store: 1 archives, 0 prunable "
                      "(older than 30 days)", text)
        self.assertIn("interrupted removals: none", text)
        self.assertEqual(sum(1 for l in lines if l.startswith("next: ")), 1)

    def test_doctor_prints_the_section_after_the_report(self):
        got = self.section("doctor", report(finished("a-item")))
        lines = got.stdout.splitlines()
        self.assertTrue(any(l.startswith("retention (") for l in lines))
        self.assertLess(max(i for i, l in enumerate(lines) if not l.startswith(" ") and l and
                            not l.startswith("retention")) or 0, len(lines))
        self.assertTrue(lines[-1].startswith("  next: "), lines[-1])

    def test_removing_present_empty_present_with_ids_and_absent(self):
        rep = report(finished("a-item", archive=True, folder=False))
        rep["removing"] = ["a-item", "ghost"]
        self.assertIn("interrupted removals: a-item, ghost", self.section("status", rep).stdout)
        rep = report(finished("a-item"))
        del rep["removing"]
        self.assertIn("interrupted removals: not reported by this Workflow release",
                      self.section("status", rep).stdout)

    def test_unknown_extra_keys_are_ignored(self):
        rep = report(finished("a-item"))
        rep["something_new"] = {"x": 1}
        rep["finished"][0]["extra"] = 1
        self.assertIn("retention (", self.section("status", rep).stdout)

    def test_stderr_warnings_with_a_valid_report_are_dropped(self):
        got = self.section("status", report(finished()), STUB_WARN="1")
        self.assertIn("retention (", got.stdout)
        self.assertNotIn("warning: something", got.stdout + got.stderr)

    def test_exit_codes_do_not_change_for_a_problem_carrying_repository(self):
        (self.repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        base, got = self.both("status", STUB_REPORT=str(self.put_report(report(finished()))))
        self.assertEqual(base.returncode, 1)
        self.assertIn("retention (", got.stdout)

    def test_a_relative_target_and_a_path_with_spaces_pass_absolute_paths(self):
        parent = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(parent, ignore_errors=True))
        nested = parent / "nested dir" / "repo"
        nested.parent.mkdir()
        __import__("shutil").copytree(self.repo, nested, symlinks=True)
        path = self.put_report(report(finished()))
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                self.marker.unlink(missing_ok=True)
                base = self.invoke(command, False, cwd=parent, target="nested dir/repo",
                                   STUB_REPORT=str(path))
                got = self.invoke(command, True, cwd=parent, target="nested dir/repo",
                                  STUB_REPORT=str(path))
                self.assertEqual(got.returncode, base.returncode, got.stdout + got.stderr)
                self.assertIn("retention (", got.stdout)
                call = json.loads(self.marker.read_text().splitlines()[0])
                resolved = str(nested.resolve())
                self.assertEqual(call["cwd"], resolved)
                self.assertEqual(call["argv"][0], str(nested.resolve() / SCRIPT))
                self.assertEqual(call["argv"][1:], ["report", "--json", "--repo-root", resolved])

    def test_status_of_an_unmanaged_repository_prints_the_not_managed_note(self):
        empty = self.empty()
        got = run("status", "--retention", str(empty), env=self.env())
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        step = self.one_note(got, "the repository is not managed by workflow-manager")
        self.assertTrue(step.startswith("workflow-manager bootstrap "), step)
        self.assertEqual(sum(1 for l in got.stdout.splitlines() if l.startswith("next: ")), 1)


class TestArchiveCoverage(Scratch):
    """EPR-005: coverage counts finished items; the store totals are separate."""

    def setUp(self):
        super().setUp()
        self.install_stub()

    def test_an_unrelated_archive_never_reads_as_one_of_zero(self):
        rep = report()
        rep["totals"]["archives"] = 1
        for command in ("status", "doctor"):
            out = self.section(command, rep).stdout
            self.assertIn("with an archive: 0 of 0; archive store: 1 archives", out)
            self.assertNotIn("1 of 0", out)

    def test_coverage_comes_from_finished_only(self):
        rep = report(finished("a", archive=True), finished("b"), finished("c", archive=False, readable=False))
        rep["totals"]["archives"] = 6
        rep["totals"]["prunable"] = 2
        for command in ("status", "doctor"):
            out = self.section(command, rep).stdout
            self.assertIn("with an archive: 1 of 3 (1 unknown); archive store: 6 archives, 2 prunable", out)

    def test_store_figures_and_coverage_move_independently(self):
        base = report(finished("a", archive=True), finished("b"))
        text = self.section("status", base).stdout
        stores = copy.deepcopy(base)
        stores["totals"]["archives"] = 9
        stores["totals"]["prunable"] = 4
        out = self.section("status", stores).stdout
        self.assertIn("with an archive: 1 of 2; archive store: 9 archives, 4 prunable", out)
        self.assertIn("with an archive: 1 of 2; archive store: 1 archives, 0 prunable", text)
        flipped = copy.deepcopy(base)
        flipped["finished"][1]["archive"].update(present=True)
        out = self.section("status", flipped).stdout
        self.assertIn("with an archive: 2 of 2; archive store: 1 archives, 0 prunable", out)

    def test_the_real_script_counts_an_unrelated_archive_in_the_store_only(self):
        if not recipe.available():
            self.skipTest("the installed retention script is absent")
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = Path(tmp) / "repo", Path(tmp) / "home"
            repo.mkdir(), home.mkdir()
            recipe.build_recipe(repo, home, extra_archive="unrelated")
            rep = recipe.run_real(repo, home)
        self.assertEqual(rep["totals"]["archives"], 1)
        self.assertEqual(sum(1 for e in rep["finished"] if e["archive"]["present"]), 0)
        lines = retention.render(rep, "2.22.0", Path("/x"))
        self.assertTrue(any("with an archive: 0 of 1" in l and "archive store: 1 archives" in l
                            for l in lines), lines)


class TestNextStep(unittest.TestCase):
    TARGET = Path("/path/to/repo")

    def step(self, rep, version="2.22.0"):
        return retention.next_step(rep, version, self.TARGET)

    def test_archive_first_then_remove_then_the_interrupted_removal(self):
        rep = report(finished("done-a", archive=True), finished("todo-b"))
        self.assertEqual(self.step(rep),
                         "in the repository, run `python3 -I scripts/workflow_retention.py archive "
                         "todo-b --apply` (run it without `--apply` first for a dry run)")
        rep = report(finished("done-a", archive=True))
        self.assertEqual(self.step(rep), "in the repository, run `python3 -I "
                                         "scripts/workflow_retention.py remove done-a --apply`")
        rep = report(finished("half", archive=True, folder=False))
        rep["removing"] = ["half"]
        self.assertEqual(self.step(rep), "in the repository, run `python3 -I "
                                         "scripts/workflow_retention.py remove half --apply`")
        self.assertEqual(self.step(report()), "nothing to archive")

    def test_items_the_script_would_refuse_get_no_command(self):
        cases = {
            "folder absent": [finished("a", folder=False)],
            "tracked files, unarchived": [finished("a", tracked=2)],
            "unreadable archive": [finished("a", readable=False)],
            "archived with tracked files": [finished("a", archive=True, tracked=1)],
            "archived with unreadable archive": [finished("a", archive=True, readable=False)],
        }
        for name, entries in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.step(report(*entries)), "nothing to archive")
        rep = report(finished("a", archive=True))
        rep["removing"] = ["a"]
        self.assertEqual(self.step(rep), "nothing to archive")      # a leftover and its folder is back
        rep = report(finished("a", archive=True, folder=False))
        rep["removing"] = ["ghost"]                                 # not in finished
        self.assertEqual(self.step(rep), "nothing to archive")
        rep = report(finished("a", archive=False, folder=False))
        rep["removing"] = ["a"]                                     # archive absent
        self.assertEqual(self.step(rep), "nothing to archive")
        rep = report(finished("a", archive=True, folder=False, readable=False))
        rep["removing"] = ["a"]
        self.assertEqual(self.step(rep), "nothing to archive")
        rep = report(finished("a", archive=True, folder=False, tracked=1))
        rep["removing"] = ["a"]
        self.assertEqual(self.step(rep), "nothing to archive")

    def test_capability_by_the_recorded_workflow_release(self):
        unarchived = report(finished("a"))
        archived = report(finished("a", archive=True))
        update = f"workflow-manager update {self.TARGET}"
        self.assertIn(update, self.step(unarchived, "2.20.0"))
        self.assertIn("no `archive` command", self.step(unarchived, "2.20.0"))
        self.assertIn("archive a --apply", self.step(unarchived, "2.21.0"))
        self.assertIn("no `remove` command", self.step(archived, "2.21.0"))
        self.assertIn(update, self.step(archived, "2.21.0"))
        self.assertIn("remove a --apply", self.step(archived, "2.22.0"))
        self.assertIn("remove a --apply", self.step(archived, "2.30.1"))
        for version in (None, "", "v2.22.0", 2, "2.22", "latest"):
            with self.subTest(version=version):
                self.assertIn(update, self.step(unarchived, version))
                self.assertNotIn("--apply", self.step(archived, version))

    def test_an_id_with_shell_characters_is_quoted(self):
        step = self.step(report(finished("a b")))
        self.assertIn(shlex.quote("a b"), step)


class TestCapabilityEndToEnd(Scratch):
    def test_the_recorded_release_decides_which_command_is_offered(self):
        self.install_stub()
        path = self.put_report(report(finished("a")))
        record = self.repo / ".workflow-manager" / "installation.json"
        for version, expected in (("2.20.0", "no `archive` command"), ("2.22.0", "archive a --apply")):
            with self.subTest(version=version):
                data = json.loads(record.read_text())
                data["workflow_version"] = version
                record.write_text(json.dumps(data))
                got = self.invoke("status", True, STUB_REPORT=str(path))
                self.assertIn(expected, got.stdout)


class TestIncomplete(Scratch):
    def setUp(self):
        super().setUp()
        self.install_stub()

    def test_read_errors_are_listed_with_a_cap_of_five(self):
        rep = report(finished("a"))
        rep["complete"] = False
        rep["read_errors"] = [{"path": f"/p/{n}", "error": "denied"} for n in range(7)]
        out = self.section("status", rep).stdout
        self.assertIn("retention: INCOMPLETE", out)
        self.assertIn("lower bounds", out)
        self.assertIn("/p/4 (denied) and 2 more", out)
        self.assertNotIn("/p/5", out)
        self.assertIn("next: fix what is named, then run the command again", out.replace("  next", "next"))
        self.assertNotIn("retention (read-only", out)

    def test_some_failed_queries_are_incomplete_and_listed_by_id_and_code(self):
        rep = report(finished("a"))
        rep["not_finished"] = [{"work_item_id": "q-one", "phase": "MILESTONE_COMPLETE",
                                "reason": "query_failed:forge_unavailable"}]
        out = self.section("doctor", rep).stdout
        self.assertIn("retention: INCOMPLETE", out)
        self.assertIn("q-one (forge_unavailable)", out)

    def test_every_query_failing_is_the_forge_note_with_the_first_code(self):
        rep = report()
        rep["kept_recent"] = []
        rep["not_finished"] = [
            {"work_item_id": "o", "phase": "IMPLEMENTING", "reason": "open_phase"},
            {"work_item_id": "a", "phase": "MILESTONE_COMPLETE", "reason": "query_failed:gh_missing"},
            {"work_item_id": "b", "phase": "MILESTONE_COMPLETE", "reason": "query_failed:forge_timeout"},
        ]
        got = self.section("status", rep)
        step = self.one_note(got, "the forge could not be queried (gh_missing, 2 items)")
        self.assertEqual(step, retention.STEP_FORGE)

    def test_no_item_queried_is_a_complete_report_with_nothing_finished(self):
        rep = report()
        rep["kept_recent"] = []
        rep["not_finished"] = [{"work_item_id": "o", "phase": "IMPLEMENTING", "reason": "open_phase"}]
        out = self.section("status", rep).stdout
        self.assertIn("retention (read-only", out)
        self.assertIn("finished work items: 0", out)
        self.assertIn("nothing to archive", out)
        self.assertNotIn("INCOMPLETE", out)
        self.assertNotIn("not available", out)


class TestNotAvailable(Scratch):
    def test_script_absent_and_script_a_link(self):
        got = self.both("status")[1]
        step = self.one_note(got, "the repository has no scripts/workflow_retention.py "
                                  "(the Workflow release that ships it is 2.20.0 or later)")
        self.assertTrue(step.startswith("workflow-manager update "), step)
        target = self.outside / "real.py"
        target.write_text(STUB)
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / SCRIPT).symlink_to(target)
        got = self.both("status", STUB_REPORT=str(self.put_report(report())))[1]
        self.one_note(got, "the repository has no scripts/workflow_retention.py")

    def test_the_script_refuses_and_its_cause_and_step_pass_through(self):
        self.install_stub()
        stderr = "error: repository_unknown: origin is not a github.com repository\\nnext step: add an origin remote"
        got = self.both("doctor", STUB_MODE="exit", STUB_EXIT="2", STUB_STDERR=stderr)[1]
        step = self.one_note(got, "repository_unknown: origin is not a github.com repository")
        self.assertEqual(step, "add an origin remote")

    def test_other_failures_are_case_six(self):
        self.install_stub()
        cases = {
            "exit 1": (dict(STUB_MODE="exit", STUB_EXIT="1", STUB_STDERR="boom"),
                       "exited with status 1 (boom)", retention.STEP_RUN_DIRECTLY),
            "exit 2 without refusal lines": (dict(STUB_MODE="exit", STUB_EXIT="2", STUB_STDERR="oops\\nmore"),
                                             "exited with status 2 without a refusal (oops)",
                                             retention.STEP_RUN_DIRECTLY),
            "bad json": (dict(STUB_REPORT=str(self.put_report("not json"))), "not one JSON object",
                         retention.STEP_RUN_DIRECTLY),
            "json list": (dict(STUB_REPORT=str(self.put_report("[1]"))), "not one JSON object",
                          retention.STEP_RUN_DIRECTLY),
            "wrong kind": (dict(STUB_REPORT=str(self.put_report(dict(fixture(), kind="other")))),
                           "kind 'other'", retention.STEP_UPDATE_MANAGER),
            "schema 2": (dict(STUB_REPORT=str(self.put_report(dict(fixture(), schema_version=2)))),
                         "schema_version 2", retention.STEP_UPDATE_MANAGER),
        }
        for name, (env, cause, step) in cases.items():
            with self.subTest(name=name):
                got = self.both("status", **env)[1]
                self.assertEqual(self.one_note(got, cause), step)

    def test_stdout_that_is_not_utf8(self):
        self.install_stub()
        path = self.outside / "raw"
        path.write_bytes(b"\xff\xfe{}")
        got = self.both("status", STUB_MODE="raw", STUB_REPORT=str(path))[1]
        self.assertEqual(self.one_note(got, "not UTF-8 text"), retention.STEP_RUN_DIRECTLY)

    def test_the_interpreter_cannot_start(self):
        self.install_stub()
        with mock.patch.object(retention.sys, "executable", str(self.outside / "no-such-python")):
            outcome = retention.fetch(self.repo)
        self.assertIn("cannot start", outcome.refusal.cause)
        self.assertEqual(outcome.refusal.step, retention.STEP_REINSTALL)
        self.assertEqual(retention.render_note(outcome.refusal)[1], "  next: " + retention.STEP_REINSTALL)

    def test_timeout_names_the_limit_and_leaves_no_process(self):
        self.install_stub()
        pidfile = self.outside / "pid"
        env = {"STUB_MODE": "sleep", "STUB_PIDFILE": str(pidfile)}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(retention, "TIMEOUT_SECONDS", 1):
            started = time.monotonic()
            outcome = retention.fetch(self.repo)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(outcome.refusal.step, retention.STEP_RUN_DIRECTLY)
        self.assertIn("did not finish within", outcome.refusal.cause)
        pid = int(pidfile.read_text())
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(pid), "the script's child outlived the call")

    def test_a_child_that_ignores_sigterm_is_killed_and_does_not_hold_the_call(self):
        # The script exits on SIGTERM and leaves a child that ignores it. The
        # call runs in a scratch child subreaper (`SUBREAPER`), which adopts
        # and reaps that child, so the runner's own orphan check stays strict.
        if not sys.platform.startswith("linux"):
            self.skipTest("a child subreaper needs Linux")
        self.install_stub()
        pidfile = self.outside / "pid"
        env = pinned_env(STUB_MODE="stubborn", STUB_PIDFILE=str(pidfile),
                         PYTHONPATH=str(Path(retention.__file__).resolve().parents[1]))
        proc = subprocess.run([sys.executable, "-I", "-B", "-c", SUBREAPER, str(self.repo),
                               str(pidfile)], capture_output=True, text=True, env=env, timeout=60)
        if proc.returncode == 3:
            self.skipTest("prctl(PR_SET_CHILD_SUBREAPER) is unavailable")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        got = json.loads(proc.stdout)
        self.assertIn("did not finish within", got["cause"])
        self.assertLess(got["elapsed"], 15)
        self.assertFalse(got["survived"], "a child that ignores SIGTERM outlived the call")

    def test_the_timeout_constant_is_300_seconds(self):
        self.assertEqual(retention.TIMEOUT_SECONDS, 300)
        self.assertIn("within 300 seconds", "the report did not finish within "
                      f"{retention.TIMEOUT_SECONDS} seconds")


class TestMalformedReports(Scratch):
    def setUp(self):
        super().setUp()
        self.install_stub()

    def case_six(self, rep, fragment):
        got = self.both("status", STUB_REPORT=str(self.put_report(rep)))[1]
        step = self.one_note(got, "the script's report is malformed")
        self.assertIn(fragment, got.stdout)
        self.assertEqual(step, retention.STEP_RUN_DIRECTLY)

    def test_kind_and_version_alone(self):
        self.case_six({"schema_version": 1, "kind": "retention-report"}, "complete is missing")

    def test_each_required_field_missing_and_wrongly_typed(self):
        paths = [("complete",), ("read_errors",), ("repository",), ("archive_dir",), ("ttl_days",),
                 ("keep_recent",), ("finished",), ("kept_recent",), ("not_finished",), ("totals",),
                 ("finished", 0, "work_item_id"), ("finished", 0, "review_folder"),
                 ("finished", 0, "review_folder", "present"), ("finished", 0, "review_folder", "tracked_files"),
                 ("finished", 0, "review_folder", "bytes"), ("finished", 0, "archive"),
                 ("finished", 0, "archive", "present"), ("finished", 0, "archive", "readable"),
                 ("kept_recent", 0, "work_item_id"), ("not_finished", 0, "work_item_id"),
                 ("not_finished", 0, "reason"), ("totals", "finished"),
                 ("totals", "finished_folder_bytes"), ("totals", "archives"), ("totals", "prunable"),
                 ("read_errors", 0, "path"), ("read_errors", 0, "error")]
        for path in paths:
            for mode in ("missing", "wrong"):
                with self.subTest(path=path, mode=mode):
                    rep = fixture()
                    holder = rep
                    for key in path[:-1]:
                        holder = holder[key]
                    if mode == "missing":
                        del holder[path[-1]]
                    else:
                        holder[path[-1]] = {"x": 1} if not isinstance(holder[path[-1]], (dict, list)) else "str"
                    self.assertRaises(retention._Invalid, retention._validate, rep)

    def test_a_finished_entry_without_archive_and_the_end_to_end_note(self):
        rep = report(finished())
        del rep["finished"][0]["archive"]
        self.case_six(rep, "finished[].archive is missing")

    def test_an_unpaired_surrogate_falls_back_for_both_commands(self):
        # EIR-002: it cannot be printed, so it is refused before any output.
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                rep = report(finished())
                rep["repository"] = "\ud800"
                path = self.put_report(rep)
                got = self.both(command, STUB_REPORT=str(path))[1]
                self.one_note(got, "the script's report is malformed")
                self.assertIn("repository is not valid text", got.stdout)

    def test_a_huge_byte_count_is_rendered_without_a_traceback_for_both_commands(self):
        # EIR-001: beyond float range the size is whole GiB, the exit code unchanged.
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                rep = report(finished())
                rep["totals"]["finished_folder_bytes"] = 10 ** 400
                path = self.put_report(rep)
                got = self.both(command, STUB_REPORT=str(path))[1]
                self.assertNotIn("not available", got.stdout)

    def test_size_is_exact_for_ordinary_counts_and_safe_beyond_float_range(self):
        self.assertEqual(retention._size(5), "5 B")
        self.assertEqual(retention._size(1536), "1.5 KiB")
        self.assertEqual(retention._size(3 << 20), "3.0 MiB")
        self.assertEqual(retention._size(5 << 30), "5.0 GiB")
        self.assertTrue(retention._size(10 ** 400).endswith(" GiB"))

    def test_a_bool_is_not_an_int_and_a_string_is_not_a_bool(self):
        rep = report(finished())
        rep["ttl_days"] = True
        self.case_six(rep, "ttl_days is bool, not int")
        rep = report(finished())
        rep["complete"] = "yes"
        self.case_six(rep, "complete is str, not bool")

    def test_totals_finished_must_equal_the_list(self):
        rep = report(finished())
        rep["totals"]["finished"] = 2
        self.case_six(rep, "totals.finished is 2 but finished lists 1")

    def test_removing_must_be_a_list_of_strings(self):
        rep = report(finished())
        rep["removing"] = [1]
        self.case_six(rep, "removing is list, not a list of strings")


class TestNoWrites(Scratch):
    def test_no_path_writes_anything_or_leaves_bytecode(self):
        self.install_stub()
        reports = {
            "success": dict(STUB_REPORT=str(self.put_report(report(finished())))),
            "exit": dict(STUB_MODE="exit", STUB_EXIT="1", STUB_STDERR="x"),
            "garbage": dict(STUB_REPORT=str(self.put_report("nope"))),
        }
        for name, env in reports.items():
            with self.subTest(name=name):
                before = tree_hash(self.repo)
                got = self.invoke("status", True, **env)
                self.assertNotIn("Traceback", got.stdout + got.stderr)
                self.assertEqual(tree_hash(self.repo), before)
                self.assertEqual(list(self.repo.rglob("__pycache__")), [])
        (self.repo / SCRIPT).unlink()
        before = tree_hash(self.repo)
        self.invoke("doctor", True)
        self.assertEqual(tree_hash(self.repo), before)


class TestRealScript(Scratch):
    def setUp(self):
        super().setUp()
        if not recipe.available():
            self.skipTest("the installed retention script is absent")
        self.home = self.outside / "home"
        self.home.mkdir()

    def test_no_finished_item_runs_with_no_forge_query(self):
        recipe.init_origin(self.repo)
        recipe.copy_scripts(self.repo)
        state = json.loads((self.repo / recipe.STATE).read_text())
        state["work_items"] = {"open-item": {"phase": "IMPLEMENTING"}}
        (self.repo / recipe.STATE).write_text(json.dumps(state))
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                base = self.invoke(command, False, HOME=str(self.home))
                got = self.invoke(command, True, HOME=str(self.home))
                self.assertEqual(got.returncode, base.returncode, got.stdout + got.stderr)
                self.assertIn("finished work items: 0", got.stdout)
                self.assertIn("nothing to archive", got.stdout)

    def test_the_fixture_has_the_real_reports_keys_and_types(self):
        repo = self.outside / "recipe-repo"
        repo.mkdir()
        recipe.build_recipe(repo, self.home)
        real = recipe.run_real(repo, self.home)
        if not real["read_errors"]:
            self.skipTest("the recipe produced no read_errors entry on this machine")
        self.assertEqual(shape(real), shape(fixture()))

    def test_every_validated_field_exists_in_the_fixture(self):
        retention._validate(fixture())
        rep = report(finished())
        retention._validate(rep)


def shape(value):
    """Keys and types, with list elements merged by position-free sorted shapes."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


class TestDocs(unittest.TestCase):
    PAGE = REPO_ROOT / "docs" / "retention.md"

    def test_the_page_is_registered_and_clean(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_docs", REPO_ROOT / "tools" / "check_docs.py")
        check_docs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check_docs)
        self.assertIn("docs/retention.md", check_docs.USER_PAGES)
        self.assertIn("docs/retention.md", check_docs.COMMAND_PAGES)
        self.assertEqual(check_docs.check_tree(REPO_ROOT), [])

    def test_the_index_and_the_exit_code_page_carry_it(self):
        self.assertIn("(retention.md)", (REPO_ROOT / "docs" / "README.md").read_text())
        codes = (REPO_ROOT / "docs" / "exit-codes.md").read_text()
        self.assertIn("`status --retention`, `doctor --retention`", codes)
        self.assertIn("never changes an exit code", codes)
        self.assertIn("(retention.md)", (REPO_ROOT / "docs" / "verify.md").read_text())
        self.assertIn("(retention.md)", (REPO_ROOT / "docs" / "update.md").read_text())

    def test_every_cause_the_code_can_build_is_on_the_page(self):
        text = " ".join(self.PAGE.read_text().split())
        target = Path("/t")
        causes = [
            retention.not_managed_note(target).cause,
            retention.no_script_note(target).cause,
            "the Python running workflow-manager cannot start",
            f"the report did not finish within {retention.TIMEOUT_SECONDS} seconds",
            "the script's report is malformed",
            "the forge could not be queried",
        ]
        for cause in causes:
            with self.subTest(cause=cause):
                self.assertIn(cause, text)
        for step in (retention.STEP_REINSTALL, retention.STEP_RUN_DIRECTLY,
                     retention.STEP_UPDATE_MANAGER, retention.STEP_FORGE):
            with self.subTest(step=step):
                self.assertIn(step, text)

    def test_the_page_separates_finished_coverage_from_the_store(self):
        text = " ".join(self.PAGE.read_text().split())
        self.assertIn("counts finished work items only", text)
        self.assertIn("separate count of every archive", text)


if __name__ == "__main__":
    unittest.main()
