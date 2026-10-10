#!/usr/bin/env python3
"""Operator UX: every error says what to do next.

Subprocess tests through the entry point (`python3 -m workflow_manager`),
plus unit tests of `advice`. The helpers here -- command extraction and
parsing, page resolution, the table-driven runner -- are what later rows of
the table reuse: a case names its argv and what the output must hold, and the
runner checks the program name, the exit code, the `next:` line, that every
printed command parses, and that every printed page resolves.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

import support
from support import NEWEST_RELEASE, REPO_ROOT, cli_env

from frozen_runs import build_bootstrapped_repo, empty_repo

from workflow_manager import advice, cli

_spec = importlib.util.spec_from_file_location("check_docs", REPO_ROOT / "tools" / "check_docs.py")
check_docs = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_docs", check_docs)
_spec.loader.exec_module(check_docs)

GLOBAL_OPTIONS = ("--release-version", "--release-source", "--release-cache", "--release-dir")
TARGET_COMMANDS = ("bootstrap", "update", "verify", "status", "doctor", "uninstall")


def run(*args, env=None):
    return subprocess.run([sys.executable, "-m", "workflow_manager", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=env or cli_env())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def next_lines(output: str) -> list[str]:
    """The text of every `next:` line of `output`."""
    return [line[len("next: "):] for line in output.splitlines() if line.startswith("next: ")]


def backticked(text: str) -> list[str]:
    return re.findall(r"`([^`]+)`", text)


def manager_commands(output: str) -> list[list[str]]:
    """The argv of every backticked `workflow-manager ...` command in the
    `next:` lines of `output`."""
    found = []
    for line in next_lines(output):
        for text in backticked(line):
            if text.startswith("workflow-manager "):
                found.append(shlex.split(text))
    return found


def parses(argv: list[str]) -> bool:
    """Whether `argv` (a `workflow-manager ...` command) parses under the real
    parser. Never runs anything."""
    assert argv[0] == "workflow-manager", argv
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        try:
            cli.build_parser().parse_args(argv[1:])
        except SystemExit as exit_:
            return exit_.code == 0
    return True


URL_RE = re.compile(r"https://\S+")


def pages(output: str) -> list[str]:
    return [m.rstrip(".,;:)`") for line in next_lines(output) for m in URL_RE.findall(line)]


def resolves(url: str) -> bool:
    """Whether a docs URL names a file of the working tree and, when it has a
    fragment, a heading slug of that file (`tools/check_docs.py`'s rule)."""
    assert url.startswith(advice.DOCS_BASE), url
    parsed = urlparse(url)
    name = parsed.path[len(urlparse(advice.DOCS_BASE).path):]
    path = REPO_ROOT / "docs" / name
    if not path.is_file():
        return False
    if not parsed.fragment:
        return True
    return parsed.fragment in check_docs.anchors(path.read_text())


class Case:
    def __init__(self, name, argv, *, exit_code, cause, step=(), env=None, runnable=True):
        self.name, self.argv, self.exit_code = name, argv, exit_code
        self.cause, self.step, self.env = cause, tuple(step), env
        #: False for a pattern with placeholders, which is not meant to parse.
        self.runnable = runnable


class RowTest(unittest.TestCase):
    """The table-driven runner: one case per message."""

    def check(self, case: Case):
        proc = run(*case.argv, env=case.env)
        out = proc.stdout + proc.stderr
        with self.subTest(case=case.name):
            self.assertEqual(proc.returncode, case.exit_code, out)
            self.assertNotIn("Traceback", out)
            self.assertNotIn("workflow_manager", out.replace("python3 -m workflow_manager", ""))
            self.assertIn(case.cause, proc.stderr)
            steps = next_lines(proc.stderr)
            self.assertEqual(len(steps), 1, proc.stderr)
            for part in case.step:
                self.assertIn(part, steps[0])
            for argv in manager_commands(proc.stderr) if case.runnable else ():
                self.assertTrue(parses(argv), argv)
            for url in pages(proc.stderr):
                self.assertTrue(resolves(url), url)
        return proc


# ---------------------------------------------------------------------------
# Unit tests of the helpers and of advice
# ---------------------------------------------------------------------------

class TestAdviceUnits(unittest.TestCase):
    def test_page_builds_a_full_url_with_an_optional_anchor(self):
        self.assertTrue(advice.page("update.md").startswith("https://"))
        self.assertTrue(advice.page("update.md", "update-the-manager")
                        .endswith("/docs/update.md#update-the-manager"))

    def test_the_three_anchors_later_rows_link_exist(self):
        for name, anchor in (("update.md", "update-the-manager"),
                             ("common-problems.md", "an-install-stopped-part-way"),
                             ("common-problems.md", "repair-workflow-data-by-hand"),
                             ("exit-codes.md", "global-options")):
            with self.subTest(page=name, anchor=anchor):
                self.assertTrue(resolves(advice.page(name, anchor)))

    def test_a_missing_page_or_anchor_does_not_resolve(self):
        self.assertFalse(resolves(advice.page("no-such-page.md")))
        self.assertFalse(resolves(advice.page("update.md", "no-such-anchor")))

    def test_next_step_is_none_for_an_error_without_an_entry(self):
        self.assertIsNone(advice.next_step(ValueError("x"), advice.Context()))

    def test_next_step_walks_the_class_hierarchy(self):
        class Base(Exception):
            pass

        class Child(Base):
            pass

        advice._TABLE[Base] = lambda error, context: "base step"
        try:
            self.assertEqual(advice.next_step(Child(), advice.Context()), "base step")
        finally:
            del advice._TABLE[Base]

    def test_misplaced_options_come_in_parser_order(self):
        self.assertEqual(advice.misplaced_global_options(
            ["--release-dir", "/x", "--release-version=1", "stray"]),
            ["--release-version", "--release-dir"])

    def test_the_predicate_constants_are_exactly_these(self):
        self.assertEqual(advice.PREDICATE_EXCLUDED,
                         ("the repository is not managed (no installation record)",
                          "the installation record could not be read"))

    def test_writes_withheld(self):
        from workflow_manager.compatibility import Finding, WARNING
        inc = lambda title, detail="": Finding(WARNING, "incomplete-inspection", title, detail)
        record = inc(advice.RECORD_UNREADABLE_TITLE, "bad")
        unmanaged = inc("the inspection could not be completed", advice.NOT_MANAGED_PROBLEM
                        + "\nThis report is not a clean bill of health.")
        other = inc("the inspection could not be completed",
                    advice.NOT_MANAGED_PROBLEM + "\ngit could not run\nThis report is not a clean "
                    "bill of health.")
        withheld = advice.writes_withheld
        self.assertFalse(withheld([other], (), holds_data=False))
        self.assertFalse(withheld([record, unmanaged], (), holds_data=True))
        self.assertTrue(withheld([other], (), holds_data=True))
        self.assertTrue(withheld([], ("WORKFLOW_STATE.json",), holds_data=True))
        self.assertFalse(withheld([], ("WORKFLOW_STATE.json",), holds_data=False))

    def test_extraction_helpers(self):
        out = "x\nnext: run `workflow-manager --release-dir DIR bootstrap TARGET` or see " \
              "https://github.com/a/b/blob/main/docs/x.md#y.\n"
        self.assertEqual(manager_commands(out),
                         [["workflow-manager", "--release-dir", "DIR", "bootstrap", "TARGET"]])
        self.assertEqual(pages(out), ["https://github.com/a/b/blob/main/docs/x.md#y"])
        self.assertTrue(parses(["workflow-manager", "--release-dir", "DIR", "bootstrap", "TARGET"]))
        self.assertFalse(parses(["workflow-manager", "bootstrap", "TARGET", "--release-dir", "DIR"]))


# ---------------------------------------------------------------------------
# A1: a global option written after the command
# ---------------------------------------------------------------------------

class TestMisplacedGlobalOption(RowTest):
    def test_each_option_after_each_command(self):
        for command in TARGET_COMMANDS:
            for option in GLOBAL_OPTIONS:
                value = "1.0.0" if option == "--release-version" else "/nowhere"
                proc = self.check(Case(
                    f"{command} {option}", [command, "/target", option, value], exit_code=2,
                    cause=f"unrecognized arguments: {option} {value}",
                    step=("global options go before the command", f"[{option} ",
                          f"{command} TARGET", "exit-codes.md#global-options"),
                    runnable=False))
                self.assertTrue(proc.stderr.startswith("usage: workflow-manager "), proc.stderr)

    def test_releases_and_package_commands(self):
        self.check(Case("releases", ["releases", "--release-dir", "/x"], exit_code=2,
                        cause="unrecognized arguments: --release-dir /x",
                        step=("`workflow-manager [--release-dir DIR]`",), runnable=False))
        self.check(Case("package", ["package", "verify", "a.tgz", "--release-source", "/x"],
                        exit_code=2, cause="unrecognized arguments",
                        step=("[--release-source SOURCE] package SUBCOMMAND ARGS",), runnable=False))

    def test_several_misplaced_options_are_named_in_parser_order(self):
        proc = run("verify", "/t", "--release-dir", "/d", "--release-version=1")
        self.assertEqual(proc.returncode, 2)
        step = next_lines(proc.stderr)[0]
        self.assertIn("[--release-version VERSION] [--release-dir DIR] verify TARGET", step)

    def test_the_hint_is_a_pattern_of_placeholders_not_a_command(self):
        proc = run("update", "/secret/target", "--release-version", "9.9.9")
        step = next_lines(proc.stderr)[0]
        self.assertNotIn("9.9.9", step)
        self.assertNotIn("secret", step)
        for text in backticked(step):
            words = shlex.split(text.replace("[", "").replace("]", ""))
            self.assertEqual(words[0], "workflow-manager")
            # Every word is the program, an option name, the command word or an
            # upper-case placeholder: nothing the operator typed as a value.
            for word in words[1:]:
                self.assertTrue(word.startswith("--") or word == "update" or word.isupper(), word)

    def test_the_output_does_not_depend_on_the_target(self):
        a = run("update", "/one", "--release-dir", "/x").stderr
        b = run("update", "/two", "--release-dir", "/y").stderr
        self.assertEqual(next_lines(a), next_lines(b))

    def test_an_unrecognized_argument_that_is_not_a_global_option_has_no_next_line(self):
        proc = run("verify", "/t", "--bogus")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments: --bogus", proc.stderr)
        self.assertEqual(next_lines(proc.stderr), [])

    def test_a_global_option_before_the_command_is_accepted(self):
        proc = run("--release-version", "9.9.9", "releases")
        self.assertNotIn("unrecognized", proc.stderr)


# ---------------------------------------------------------------------------
# A2: the program name in every message
# ---------------------------------------------------------------------------

class TestProgramName(unittest.TestCase):
    def test_usage_and_errors_name_workflow_manager(self):
        for argv, fragment in ((["bootstrap"], "workflow-manager bootstrap: error: the following "
                                                 "arguments are required: target"),
                               (["bogus"], "workflow-manager: error: argument COMMAND: invalid choice"),
                               ([], "workflow-manager: error: the following arguments are required")):
            with self.subTest(argv=argv):
                proc = run(*argv)
                self.assertEqual(proc.returncode, 2)
                self.assertIn(fragment, proc.stderr)
                self.assertTrue(proc.stderr.startswith("usage: workflow-manager "), proc.stderr)
                self.assertNotIn("workflow_manager", proc.stderr)

    def test_help_names_workflow_manager(self):
        proc = run("--help")
        self.assertTrue(proc.stdout.startswith("usage: workflow-manager "), proc.stdout)


# ---------------------------------------------------------------------------
# A4, A5: help text
# ---------------------------------------------------------------------------

def help_of(*argv) -> str:
    proc = run(*argv, "--help")
    assert proc.returncode == 0, proc.stderr
    return " ".join(proc.stdout.split())


class TestHelpText(unittest.TestCase):
    def test_doctor_help_states_the_real_exit_codes(self):
        text = help_of("doctor")
        self.assertIn("Exit 0: no blocked or warning finding (notes alone still exit 0); "
                      "1: a blocked or warning finding, an incomplete inspection included; "
                      "2: could not check.", text)
        self.assertNotIn("nothing found", text)

    def test_every_subcommand_has_a_summary_and_a_description_with_exit_codes(self):
        top = help_of()
        for name in TARGET_COMMANDS + ("releases", "package"):
            with self.subTest(command=name):
                self.assertRegex(top, rf"\b{name}\s+\S")
                text = help_of(name)
                self.assertIn("Exit", text)
                self.assertGreater(len(text.split("positional")[0]), 120)

    def test_package_actions_have_descriptions(self):
        for action in ("build", "verify"):
            with self.subTest(action=action):
                self.assertGreater(len(help_of("package", action).split("positional")[0]), 80)

    def test_every_option_has_help(self):
        parser = cli.build_parser()
        stack = [parser]
        while stack:
            p = stack.pop()
            for action in p._actions:
                if isinstance(action, argparse._SubParsersAction):
                    continue
                if action.help is None and action.option_strings != ["-h", "--help"]:
                    self.fail(f"{p.prog}: {action.dest} has no help")
                if isinstance(action.choices, dict):
                    stack.extend(action.choices.values())

    def test_release_version_help_says_it_goes_before_the_command(self):
        text = help_of()
        self.assertIn("--release-version RELEASE_VERSION", text)
        self.assertRegex(text, r"the Workflow release to use; goes before the command")

    def test_the_program_epilog_points_to_the_exit_codes_page(self):
        for argv in ((), ("verify",)):
            with self.subTest(argv=argv):
                text = help_of(*argv)
                self.assertIn("exit-codes.md", text.replace("exit- codes", "exit-codes"))
                self.assertIn("Global options go before the command.", text)


# ---------------------------------------------------------------------------
# CP2: the target, the record and the refusals
# ---------------------------------------------------------------------------

STATE = "docs/ai-workflow/WORKFLOW_STATE.json"
CONFIG = "docs/ai-workflow/WORKFLOW_CONFIG.json"
MILESTONE = "docs/ACTIVE_MILESTONE.md"
RECORD = ".workflow-manager/installation.json"
LOG_READER = "env GIT_NO_LAZY_FETCH=1 git -C "


def run_in(cwd, *args, env=None):
    return subprocess.run([sys.executable, "-m", "workflow_manager", *args], cwd=str(cwd),
                          capture_output=True, text=True, env=env or cli_env())


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=cli_env())


def tree_hash(root: Path, skip=()) -> str:
    """A digest of every file, directory and link below `root` (`.git` too)."""
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        digest.update(rel.encode() + b"\0")
        if path.is_symlink():
            digest.update(b"L" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"F" + path.read_bytes() + oct(path.stat().st_mode).encode())
        else:
            digest.update(b"D")
    return digest.hexdigest()


class Pristine:
    """One committed, bootstrapped repository shared by a class, copied per test."""
    _tmp = None
    _repo = None

    @classmethod
    def pristine(cls) -> Path:
        if Pristine._repo is None:
            Pristine._tmp = tempfile.TemporaryDirectory()
            Pristine._repo = build_bootstrapped_repo(support.release(NEWEST_RELEASE),
                                                     Path(Pristine._tmp.name) / "pristine")
        return Pristine._repo


class TargetCase(RowTest):
    """Helpers: a fresh copy of the managed repository, an empty Git repository."""

    def fresh(self, name="r") -> Path:
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        repo = Path(work.name) / name
        shutil.copytree(Pristine.pristine(), repo, symlinks=True)
        return repo

    def empty(self, name="e") -> Path:
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        return empty_repo(Path(work.name) / name)

    def commit(self, repo, message="work"):
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)

    def out(self, proc):
        return proc.stdout + proc.stderr

    def assertNoWritingCommand(self, text):
        for argv in manager_commands(text):
            words = [w for w in argv[1:] if not w.startswith("-")]
            self.assertFalse(argv[0] == "workflow-manager" and
                             any(w in ("update", "bootstrap") for w in argv[1:])
                             and "--dry-run" not in argv, argv)
        self.assertNotIn("--force", text)
        self.assertNotRegex(text.replace("do not run it again", ""), r"\bagain\b")


class TestTargetRows(TargetCase):
    def test_t1_no_directory(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        missing = str(Path(work.name) / "nope")
        proc = self.check(Case("T1", ["bootstrap", missing], exit_code=2,
                               cause=f"error: no directory at {missing}",
                               step=(f"`git init {missing}`", f"`workflow-manager bootstrap {missing}` again")))
        self.assertNotIn("--force", proc.stderr)

    def test_t1_leading_hyphen_target_is_executed_as_printed(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        proc = run_in(work.name, "bootstrap", "--", "-repo")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        step = next_lines(proc.stderr)[0]
        self.assertIn("`git init -- -repo`", step)
        self.assertIn("`workflow-manager bootstrap -- -repo`", step)
        commands = backticked(step)
        self.assertEqual(subprocess.run(shlex.split(commands[0]), cwd=work.name, capture_output=True,
                                        env=cli_env()).returncode, 0)
        again = shlex.split(commands[1])
        self.assertTrue(parses(again), again)
        self.assertEqual(run_in(work.name, *again[1:]).returncode, 0)

    def test_t2_not_a_git_repository(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        plain = Path(work.name) / "plain"
        plain.mkdir()
        self.check(Case("T2", ["bootstrap", str(plain)], exit_code=2,
                        cause=f"error: {plain} is not a Git repository",
                        step=(f"`git init {plain}`", "the one holding .git",
                              f"`workflow-manager bootstrap {plain}` again")))

    def test_t2_a_subdirectory_of_a_repository_fails_the_same_way(self):
        repo = self.empty()
        (repo / "sub").mkdir()
        proc = run("bootstrap", str(repo / "sub"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("is not a Git repository", proc.stderr)

    def test_t3_already_managed_names_the_version_and_the_update_command(self):
        repo = self.fresh()
        proc = self.check(Case("T3", ["bootstrap", str(repo)], exit_code=2,
                               cause=f"error: {repo} is already managed (workflow {NEWEST_RELEASE} is installed)",
                               step=(f"`workflow-manager update {repo}`", f"`workflow-manager doctor {repo}`")))
        self.assertNotIn("update()", proc.stderr)

    def test_t4_t5_unmanaged_targets_get_the_bootstrap_command(self):
        repo = self.empty()
        cause = f"error: {repo} is not a managed repository (no .workflow-manager/installation.json)"
        for argv in (["update", str(repo), "--dry-run"], ["update", str(repo)],
                     ["verify", str(repo)], ["doctor", str(repo)]):
            self.check(Case(f"T4/T5 {argv[0]}", argv, exit_code=2, cause=cause,
                            step=(f"`workflow-manager bootstrap {repo}`",)))

    def test_t6_uninstall_of_an_unmanaged_target(self):
        repo = self.empty()
        self.check(Case("T6", ["uninstall", str(repo)], exit_code=2,
                        cause=f"error: {repo} is not a managed repository (no .workflow-manager/installation.json)",
                        step=("nothing to uninstall", f"`workflow-manager status {repo}`")))

    def test_t7_status_of_an_unmanaged_target_prints_the_step_on_stdout_and_exits_0(self):
        repo = self.empty()
        proc = run("status", str(repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("not a managed repository (no .workflow-manager/installation.json)", proc.stdout)
        step = next_lines(proc.stdout)
        self.assertEqual(len(step), 1)
        self.assertIn(f"`workflow-manager bootstrap {repo}` to install the Workflow", step[0])

    def test_t7_leading_hyphen_target_keeps_flags_before_the_positional(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        empty_repo(Path(work.name) / "-repo")
        proc = run_in(work.name, "status", "--", "-repo")
        self.assertIn("`workflow-manager bootstrap -- -repo`", proc.stdout)


class TestRecordRows(TargetCase):
    def damage(self, repo, how):
        record = repo / RECORD
        if how == "truncated":
            record.write_text("{ truncated")
        elif how == "directory":
            record.unlink()
            record.mkdir()
        elif how == "binary":
            record.write_bytes(b"\xff\xfe")
        elif how == "schema-none":
            record.write_text('{"schema_version": null}')
        elif how == "schema-str":
            record.write_text('{"schema_version": "1"}')
        elif how == "schema-0":
            record.write_text('{"schema_version": 0}')
        elif how == "schema-2":
            record.write_text('{"schema_version": 2}')

    def test_t8_t20_t9_a_record_that_cannot_be_read_takes_the_same_step(self):
        for how in ("truncated", "directory", "binary", "schema-none", "schema-str", "schema-0"):
            repo = self.fresh()
            self.damage(repo, how)
            for command in ("status", "verify", "update", "uninstall", "doctor", "bootstrap"):
                with self.subTest(how=how, command=command):
                    proc = self.check(Case(
                        f"T8 {how} {command}", [command, str(repo)], exit_code=2,
                        cause=f"error: the installation record at {repo / RECORD} is unreadable (",
                        step=(f"delete {repo}/.workflow-manager",
                              f"`workflow-manager --release-version V bootstrap {repo}`",
                              "a bootstrap with no version installs the newest release",
                              LOG_READER + f"{repo} --no-optional-locks --no-pager log --oneline "
                              "--no-show-signature -- .workflow-manager/installation.json",
                              "--no-textconv REV:.workflow-manager/installation.json")))
                    self.assertNotIn("log -p", proc.stderr)
                    self.assertNotIn("Delete .workflow-manager/ and re-run bootstrap", proc.stderr)

    def test_t8_the_binary_record_names_its_path(self):
        repo = self.fresh()
        self.damage(repo, "binary")
        proc = run("status", str(repo))
        self.assertIn(str(repo / RECORD), proc.stderr)

    def test_t20_a_directory_exits_2_not_a_traceback(self):
        repo = self.fresh()
        self.damage(repo, "directory")
        proc = run("status", str(repo))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("is a directory", proc.stderr)

    def test_t9_a_newer_schema_says_to_upgrade_the_manager(self):
        repo = self.fresh()
        self.damage(repo, "schema-2")
        self.check(Case("T9", ["status", str(repo)], exit_code=2,
                        cause="was written by a newer Manager (schema_version 2; this one understands 1)",
                        step=("upgrade the Manager", "update.md#update-the-manager")))

    def test_t8_a_record_nobody_can_read_has_no_delete_step_and_exits_1(self):
        if os.geteuid() == 0:
            self.skipTest("root reads mode 000 files")
        repo = self.fresh()
        record = repo / RECORD
        record.chmod(0)
        self.addCleanup(record.chmod, 0o644)
        for command in ("status", "update"):
            with self.subTest(command=command):
                proc = run(command, str(repo))
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                step = next_lines(proc.stderr)
                self.assertEqual(len(step), 1)
                self.assertNotIn("delete", step[0])
                self.assertNotIn("bootstrap", step[0])

    def test_t10_a_profile_the_record_does_not_know(self):
        import json
        repo = self.fresh()
        record = json.loads((repo / RECORD).read_text())
        record["profile"] = "bogus"
        (repo / RECORD).write_text(json.dumps(record))
        for argv in (["update", str(repo)], ["update", str(repo), "--dry-run"]):
            with self.subTest(argv=argv):
                self.check(Case("T10", argv, exit_code=2, cause="error: unknown install profile 'bogus'",
                                step=("names a profile this Manager does not know",
                                      "upgrade the Manager", "update.md#update-the-manager",
                                      f"delete {repo}/.workflow-manager",
                                      f"`workflow-manager --release-version V bootstrap {repo}`")))


class TestRefusals(TargetCase):
    def edit(self, repo, rel="scripts/workflow_state.py"):
        (repo / rel).write_text("# edited\n")

    def test_t11_drift_names_force_dry_run_and_the_version(self):
        repo = self.fresh()
        self.edit(repo)
        proc = self.check(Case("T11", ["update", str(repo)], exit_code=2,
                               cause="refusing to update: these release files were modified locally",
                               step=("keep a copy of any file a `modified:` line above names",
                                     f"`workflow-manager update --force {repo}`",
                                     f"`workflow-manager update --dry-run {repo}` previews it first")))
        self.assertNotIn("re-run with --force", proc.stderr)
        self.assertNotIn("git diff", proc.stderr)
        self.assertFalse(proc.stderr.startswith("error:"))

    def test_t11_carries_the_operators_release_version_and_source(self):
        repo = self.fresh()
        self.edit(repo)
        proc = run("--release-version", NEWEST_RELEASE, "--release-cache", str(support.cli_env()[
            "WORKFLOW_MANAGER_RELEASE_CACHE"]), "update", str(repo))
        step = next_lines(proc.stderr)[0]
        self.assertIn(f"`workflow-manager --release-version {NEWEST_RELEASE} --release-cache ", step)
        for argv in manager_commands(proc.stderr):
            self.assertTrue(parses(argv), argv)

    def test_t12_files_in_the_way_name_the_force_command_for_the_right_command(self):
        repo = self.empty()
        (repo / ".claude" / "commands").mkdir(parents=True)
        (repo / ".claude" / "commands" / "milestone-plan.md").write_text("mine\n")
        self.check(Case("T12 bootstrap", ["bootstrap", str(repo)], exit_code=2,
                        cause="refusing to bootstrap: the repository already has its own file",
                        step=("move your own files away and run the same command again, or add --force",
                              f"`workflow-manager bootstrap --force {repo}`")))
        repo = self.fresh()
        data = repo / "scripts" / "workflow_state.py"
        data.unlink()
        # A file of the repository's own where the release puts one it records.
        record_path = repo / RECORD
        import json
        record = json.loads(record_path.read_text())
        record["managed"].pop("scripts/workflow_state.py")
        record_path.write_text(json.dumps(record))
        data.write_text("mine\n")
        self.check(Case("T12 update", ["update", str(repo)], exit_code=2,
                        cause="refusing to update: this release needs paths the repository is using",
                        step=(f"`workflow-manager update --force {repo}`",)))

    def test_t12_a_directory_in_the_way_never_offers_force(self):
        repo = self.empty()
        (repo / ".claude" / "commands" / "milestone-plan.md").mkdir(parents=True)
        proc = self.check(Case("T12 dir", ["bootstrap", str(repo)], exit_code=2,
                               cause="occupied: .claude/commands/milestone-plan.md (a directory is in the way)",
                               step=("move or remove that directory", "--force cannot replace either",
                                     f"`workflow-manager bootstrap {repo}` again")))
        self.assertNotIn("`workflow-manager bootstrap --force", proc.stderr)

    def test_t12_mixed_file_and_directory_takes_the_directory_text(self):
        repo = self.empty()
        commands = repo / ".claude" / "commands"
        commands.mkdir(parents=True)
        (commands / "milestone-plan.md").write_text("mine\n")
        (commands / "milestone-implement.md").mkdir()
        proc = run("bootstrap", str(repo))
        self.assertEqual(proc.returncode, 2)
        step = next_lines(proc.stderr)[0]
        self.assertIn("--force cannot replace either", step)
        self.assertNotIn("`workflow-manager bootstrap --force", step)

    def test_t13_a_directory_where_a_release_file_goes_is_refused_with_force_too(self):
        for command in ("bootstrap", "update"):
            with self.subTest(command=command):
                repo = self.empty() if command == "bootstrap" else self.fresh()
                target = repo / "scripts" / "workflow_state.py"
                if target.exists():
                    target.unlink()
                target.mkdir(parents=True)
                before = tree_hash(repo)
                proc = run(command, str(repo), "--force")
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("occupied: scripts/workflow_state.py (a directory is in the way)", proc.stderr)
                self.assertEqual(tree_hash(repo), before, "nothing of the release was written")

    def test_t18_a_file_where_a_release_directory_goes(self):
        for command in ("bootstrap", "update"):
            for ancestor in (".claude", "scripts"):
                for force in (False, True):
                    with self.subTest(command=command, ancestor=ancestor, force=force):
                        repo = self.empty()
                        if command == "update":
                            repo = self.fresh()
                        shutil.rmtree(repo / ancestor, ignore_errors=True)
                        (repo / ancestor).write_text("a file\n")
                        before = tree_hash(repo)
                        argv = [command, str(repo)] + (["--force"] if force else [])
                        proc = run(*argv)
                        self.assertEqual(proc.returncode, 2, proc.stderr)
                        self.assertNotIn("Traceback", proc.stderr)
                        self.assertIn(f"occupied: {ancestor} (it is a file, not a directory)", proc.stderr)
                        self.assertIn("--force cannot replace either", next_lines(proc.stderr)[0])
                        self.assertEqual(tree_hash(repo), before)

    def test_t19_a_file_at_the_record_directory(self):
        for force in (False, True):
            with self.subTest(force=force):
                repo = self.empty()
                (repo / ".workflow-manager").write_text("a file\n")
                before = tree_hash(repo)
                proc = run("bootstrap", str(repo), *(["--force"] if force else []))
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("occupied: .workflow-manager (it is a file, not a directory)", proc.stderr)
                self.assertEqual(tree_hash(repo), before)

    def test_a_directory_at_the_record_tmp_is_refused_and_a_leftover_file_is_not(self):
        repo = self.fresh()
        tmp = repo / (RECORD + ".tmp")
        tmp.mkdir()
        before = tree_hash(repo)
        proc = run("update", str(repo))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn(f"occupied: {RECORD}.tmp (a directory is in the way)", proc.stderr)
        self.assertEqual(tree_hash(repo), before)
        tmp.rmdir()
        tmp.write_text("leftover of an interrupted write\n")
        proc = run("update", str(repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(tmp.exists(), "the write replaced the leftover")
        leftover = self.empty()
        (leftover / ".workflow-manager").mkdir()
        (leftover / (RECORD + ".tmp")).write_text("leftover\n")
        self.assertEqual(run("bootstrap", str(leftover)).returncode, 0)


class TestOSErrors(TargetCase):
    def needs_permissions(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores permissions")

    def test_t14_a_read_only_directory_is_a_message_and_the_rerun_works(self):
        self.needs_permissions()
        repo = self.empty()
        scripts = repo / "scripts"
        scripts.mkdir()
        scripts.chmod(0o555)
        self.addCleanup(scripts.chmod, 0o755)
        proc = run("bootstrap", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("error: [Errno 13] Permission denied", proc.stderr)
        step = next_lines(proc.stderr)
        self.assertEqual(len(step), 1)
        self.assertIn("fix the cause named above, then run the same command again", step[0])
        self.assertIn("partial write", step[0])
        self.assertIn("an-install-stopped-part-way", step[0])
        scripts.chmod(0o755)
        self.assertEqual(run("bootstrap", str(repo)).returncode, 0)

    def test_t14_read_only_commands_never_mention_force_or_a_partial_write(self):
        self.needs_permissions()
        repo = self.fresh()
        locked = repo / "scripts" / "workflow_state.py"
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        for argv in (["verify", str(repo)], ["update", str(repo), "--dry-run"]):
            with self.subTest(argv=argv):
                proc = run(*argv)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                step = next_lines(proc.stderr)[0]
                self.assertIn("this command writes nothing in the repository", step)
                self.assertNotIn("--force", step)
                self.assertNotIn("partial write", step)

    def test_t14_uninstall_has_its_own_text(self):
        self.needs_permissions()
        repo = self.fresh()
        parent = repo / "scripts"
        parent.chmod(0o555)
        self.addCleanup(parent.chmod, 0o755)
        proc = run("uninstall", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("it removes only what is left", next_lines(proc.stderr)[0])


class TestProblemLines(TargetCase):
    def test_t15_a_modified_release_file_gets_the_update_with_the_installed_version(self):
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        proc = run("verify", str(repo))
        self.assertEqual(proc.returncode, 1)
        step = next_lines(proc.stdout)
        self.assertEqual(len(step), 1)
        self.assertIn(f"`workflow-manager --release-version {NEWEST_RELEASE} update {repo}`", step[0])
        self.assertIn(f"`workflow-manager --release-version {NEWEST_RELEASE} update --dry-run {repo}`", step[0])
        self.assertIn('add --force if a line says "modified: PATH"', step[0])
        status = run("status", str(repo))
        self.assertEqual(status.returncode, 1)
        self.assertEqual(next_lines(status.stdout), step)

    def test_t15_unexpected_release_and_version_lines(self):
        repo = self.fresh()
        removed = repo / "scripts" / "workflow_state.py"
        removed.unlink()
        extra = repo / "docs" / "ACTIVE_MILESTONE.md"
        proc = run("verify", str(repo))
        self.assertIn("missing: scripts/workflow_state.py", proc.stdout)
        self.assertIn("put the release's files back", next_lines(proc.stdout)[0])
        # A comparison with another release is a `version:` line.
        other = [v for v in support.PINNED_VERSIONS if v != NEWEST_RELEASE]
        if other:
            proc = run("--release-version", other[0], "verify", str(repo))
            self.assertIn("version: installed", proc.stdout)
            step = next_lines(proc.stdout)[0]
            self.assertIn("leave out --release-version and --release-dir", step)
            self.assertIn(f"`workflow-manager --release-version {other[0]} update {repo}`", step)

    def test_t15_a_missing_data_file_gets_the_workflow_data_step_and_no_update(self):
        repo = self.fresh()
        (repo / CONFIG).unlink()
        proc = run("verify", str(repo))
        self.assertEqual(proc.returncode, 1)
        step = next_lines(proc.stdout)[0]
        self.assertIn(f"{LOG_READER}{repo} --no-optional-locks --no-pager log --oneline "
                      f"--no-show-signature -- {CONFIG}", step)
        self.assertIn(f"{LOG_READER}{repo} --no-optional-locks --no-pager show --no-textconv "
                      f"HEAD:{CONFIG}", step)
        self.assertIn("common-problems.md#repair-workflow-data-by-hand", step)
        self.assertIn("this Manager prints no command that writes it, and an update is not a repair", step)
        for word in ("restore", "checkout", "stash", "workflow-manager update", "workflow-manager bootstrap"):
            self.assertNotIn(word, step)
        for argv in manager_commands(proc.stdout):
            self.assertTrue(parses(argv))

    def test_t15_the_printed_history_readers_run_and_change_nothing(self):
        repo = self.fresh()
        (repo / CONFIG).unlink()
        step = next_lines(run("verify", str(repo)).stdout)[0]
        before = tree_hash(repo)
        committed = (Pristine.pristine() / CONFIG).read_bytes()
        for text in backticked(step):
            if not text.startswith("env GIT_NO_LAZY_FETCH=1 git "):
                continue
            proc = subprocess.run(shlex.split(text), capture_output=True, env=cli_env())
            self.assertEqual(proc.returncode, 0, text)
            if " show " in text:
                self.assertEqual(proc.stdout, committed)
        self.assertEqual(tree_hash(repo), before)

    def test_t15_options_are_carried_by_the_command_specific_rule(self):
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        cache = cli_env()["WORKFLOW_MANAGER_RELEASE_CACHE"]
        proc = run("--release-cache", cache, "verify", str(repo))
        step = next_lines(proc.stdout)[0]
        self.assertIn(f"`workflow-manager --release-version {NEWEST_RELEASE} --release-cache {cache} "
                      f"update {repo}`", step)
        for argv in manager_commands(proc.stdout):
            self.assertTrue(parses(argv), argv)

    def test_t15_a_release_dir_of_another_version_is_left_out_and_the_repair_succeeds(self):
        if support.UPGRADE_FROM is None:
            self.skipTest("one pinned release")
        older = support.UPGRADE_FROM
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        repo = build_bootstrapped_repo(support.release(older), Path(work.name) / "r")
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        newest = Path(work.name) / "newest"
        shutil.copytree(support.release(NEWEST_RELEASE).root, newest)
        proc = run("--release-version", NEWEST_RELEASE, "--release-dir", str(newest), "verify", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        step = next_lines(proc.stdout)[0]
        self.assertIn("leave out --release-version and --release-dir to compare with workflow "
                      f"{older}", step)
        self.assertIn(f"`workflow-manager --release-version {NEWEST_RELEASE} --release-dir {newest} "
                      f"update {repo}`", step)

    def test_t15_the_ordinary_repair_drops_a_release_dir_that_is_not_the_installed_release(self):
        context = advice.Context(
            args=argparse.Namespace(command="verify", target=Path("/t"), release_version="2.9.1",
                                    release_source=None, release_cache=None,
                                    release_dir=Path("/newest"), profile=None),
            installed_version="2.6.0", release_dir_version="2.9.1")
        step = advice.problem_step(context, ["modified: scripts/x.py"])
        self.assertIn("`workflow-manager --release-version 2.6.0 update /t`", step)
        self.assertIn("--release-dir /newest holds 2.9.1, so it is left out; the installed release "
                      "2.6.0 comes from the cache or --release-source", step)
        self.assertNotIn("--release-dir /newest update", step)


class TestSuccessNext(TargetCase):
    def test_t17_bootstrap_and_update_end_with_verify_and_review(self):
        repo = self.empty()
        proc = run("bootstrap", str(repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(next_lines(proc.stdout),
                         [f"run `workflow-manager verify {repo}`, then review and commit what "
                          f"changed (`git -C {repo} status`)"])
        proc = run("update", str(repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("(no change)", proc.stdout)
        self.assertEqual(len(next_lines(proc.stdout)), 1)
        for argv in manager_commands(proc.stdout):
            self.assertTrue(parses(argv))

    def test_t17_a_leading_hyphen_target_keeps_the_positional_last(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        empty_repo(Path(work.name) / "-repo")
        proc = run_in(work.name, "bootstrap", "--", "-repo")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("`workflow-manager verify -- -repo`", proc.stdout)
        verify = run_in(work.name, "verify", "--", "-repo")
        self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_the_success_line_carries_a_release_source_and_cache(self):
        repo = self.empty()
        cache = cli_env()["WORKFLOW_MANAGER_RELEASE_CACHE"]
        proc = run("--release-cache", cache, "bootstrap", str(repo))
        self.assertIn(f"`workflow-manager --release-cache {cache} verify {repo}`", proc.stdout)


class TestWorkflowDataWithheld(TargetCase):
    """P1: while a state template is missing from a target that holds Workflow
    data, no printed text offers a command that writes it."""

    def break_config(self, repo):
        (repo / CONFIG).unlink()

    def assertWithheld(self, text):
        self.assertNoWritingCommand(text)
        for word in ("git restore", "checkout --", "git stash"):
            self.assertNotIn(word, text)

    def test_t3_with_a_missing_template_prints_no_update(self):
        repo = self.fresh()
        self.break_config(repo)
        proc = run("bootstrap", str(repo))
        self.assertEqual(proc.returncode, 2)
        step = next_lines(proc.stderr)[0]
        self.assertWithheld(step)
        self.assertIn("common-problems.md#repair-workflow-data-by-hand", step)
        self.assertIn(f"`workflow-manager doctor {repo}` shows what an update would do", step)
        self.assertFalse((repo / CONFIG).exists(), "the printed text must not recreate it")

    def test_t11_t12_with_a_missing_template_withhold_force(self):
        repo = self.fresh()
        self.break_config(repo)
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        proc = run("update", str(repo))
        self.assertEqual(proc.returncode, 2)
        step = next_lines(proc.stderr)[0]
        self.assertWithheld(step)
        self.assertIn(f"`workflow-manager update --dry-run {repo}` previews", step)

    def test_t8_with_a_missing_template_withholds_bootstrap_and_names_the_data(self):
        repo = self.fresh()
        self.break_config(repo)
        (repo / RECORD).write_text("{ truncated")
        proc = run("status", str(repo))
        step = next_lines(proc.stderr)[0]
        self.assertIn(f"delete {repo}/.workflow-manager", step)
        self.assertIn(CONFIG, step)
        self.assertIn("No bootstrap command is offered until the Workflow data named above is back in place", step)
        self.assertNoWritingCommand(step)

    def test_t8_with_every_template_intact_keeps_the_bootstrap_and_costs_no_data(self):
        repo = self.fresh()
        state = repo / STATE
        state.write_text(state.read_text() + "\n")
        (repo / RECORD).write_text("{ truncated")
        proc = run("status", str(repo))
        step = next_lines(proc.stderr)[0]
        self.assertNotIn("No bootstrap command is offered", step)
        before = {rel: (repo / rel).read_bytes() for rel in (STATE, CONFIG, MILESTONE)}
        shutil.rmtree(repo / ".workflow-manager")
        again = run("--release-version", NEWEST_RELEASE, "bootstrap", str(repo))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(before, {rel: (repo / rel).read_bytes() for rel in (STATE, CONFIG, MILESTONE)})

    def test_an_unmanaged_target_with_data_and_nothing_missing_keeps_bootstrap_with_the_caveat(self):
        repo = self.fresh()
        self.assertEqual(run("uninstall", str(repo)).returncode, 0)
        proc = run("status", str(repo))
        step = next_lines(proc.stdout)[0]
        self.assertIn(f"`workflow-manager bootstrap {repo}`", step)
        self.assertIn("installs the newest release over state an older release wrote", step)
        self.assertIn(f"`workflow-manager --release-version V bootstrap {repo}`", step)
        before = {rel: (repo / rel).read_bytes() for rel in (STATE, CONFIG, MILESTONE)}
        self.assertEqual(run("bootstrap", str(repo)).returncode, 0)
        self.assertEqual(before, {rel: (repo / rel).read_bytes() for rel in (STATE, CONFIG, MILESTONE)})

    def test_an_unmanaged_target_with_data_and_a_missing_template_gets_no_bootstrap(self):
        repo = self.fresh()
        self.assertEqual(run("uninstall", str(repo)).returncode, 0)
        self.break_config(repo)
        proc = run("status", str(repo))
        self.assertEqual(proc.returncode, 0)
        step = next_lines(proc.stdout)[0]
        self.assertWithheld(step)
        self.assertIn("No bootstrap command is offered", step)

    def test_a_fresh_repository_keeps_its_bootstrap_without_running_git(self):
        repo = self.empty()
        env = cli_env(PATH="")
        for argv in (["status", str(repo)],):
            proc = run(*argv, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(f"`workflow-manager bootstrap {repo}`", proc.stdout)

    def test_an_unmanaged_target_with_data_and_no_git_fails_closed(self):
        repo = self.fresh()
        self.assertEqual(run("uninstall", str(repo)).returncode, 0)
        proc = run("status", str(repo), env=cli_env(PATH=""))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        step = next_lines(proc.stdout)[0]
        self.assertIn("No bootstrap command is offered", step)
        self.assertNoWritingCommand(step)

    def test_t14_a_write_failure_with_a_missing_template_withholds_the_rerun(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores permissions")
        repo = self.fresh()
        self.break_config(repo)
        record = repo / RECORD
        parent = repo / "scripts"
        (parent / "workflow_state.py").unlink()
        parent.chmod(0o555)
        self.addCleanup(parent.chmod, 0o755)
        proc = run("update", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        step = next_lines(proc.stderr)[0]
        self.assertNoWritingCommand(step)
        self.assertIn("do not run it again until the Workflow data named above is back in place", step)
        self.assertFalse((repo / CONFIG).exists())

    def test_every_workflow_data_step_uses_only_the_vetted_commands(self):
        repo = self.fresh()
        self.break_config(repo)
        (repo / STATE).write_text("{ not json")
        out = run("status", str(repo))
        for case in (run("verify", str(repo)), run("bootstrap", str(repo))):
            for text in backticked(" ".join(next_lines(case.stdout + case.stderr))):
                if text.startswith("cp -p -- ") or text.startswith("ls -ld -- "):
                    continue
                if text.startswith(("env ", "git ")):
                    self.assertTrue(
                        text.startswith("env GIT_NO_LAZY_FETCH=1 git ") and (
                            " --no-pager log --oneline --no-show-signature -- " in text
                            or " --no-pager show --no-textconv " in text), text)


class TestAdviceCp2Units(unittest.TestCase):
    def ctx(self, **kw):
        args = argparse.Namespace(command="bootstrap", target=Path("/t"), release_version=None,
                                  release_source=None, release_cache=None, release_dir=None,
                                  profile="full", force=False, dry_run=False)
        for key in [k for k in kw if k.startswith("a_")]:
            setattr(args, key[2:], kw.pop(key))
        return advice.Context(args=args, **kw)

    def test_manager_command_withholds_writes_but_not_dry_run(self):
        from workflow_manager import compatibility as comp
        self.assertIsNone(comp.manager_command("update", target="/t", withheld=True))
        self.assertIsNone(comp.manager_command("bootstrap", "--force", target="/t", withheld=True))
        self.assertIsNotNone(comp.manager_command("update", "--dry-run", target="/t", withheld=True))
        self.assertIsNotNone(comp.manager_command("doctor", target="/t", withheld=True))
        self.assertEqual(comp.manager_command("update", "--force", target="/t", withheld=False).argv,
                         ("workflow-manager", "update", "--force", "/t"))

    def test_a_hyphen_target_gets_double_dash_after_the_flags(self):
        from workflow_manager import compatibility as comp
        argv = comp.manager_command("update", "--force", target="-repo", withheld=False).argv
        self.assertEqual(argv, ("workflow-manager", "update", "--force", "--", "-repo"))
        self.assertTrue(parses(list(argv)))

    def test_git_command_prefix_and_init(self):
        from workflow_manager import compatibility as comp
        self.assertEqual(comp.git_command("/r", "log").argv,
                         ("env", "GIT_NO_LAZY_FETCH=1", "git", "-C", "/r", "--no-optional-locks", "log"))
        self.assertEqual(comp.git_command("/r", "status", inspection=False).argv,
                         ("git", "-C", "/r", "status"))
        self.assertEqual(comp.git_init_command("-r").argv, tuple("git init -- -r".split()))
        self.assertEqual(comp.git_init_command("r").argv, tuple("git init r".split()))

    def test_rerun_phrase(self):
        from workflow_manager import compatibility as comp
        self.assertEqual(comp.rerun_phrase(True, False, "P"), "run the same command again")
        self.assertEqual(comp.rerun_phrase(False, True, "P"), "run the same command again")
        self.assertIn("do not run it again until the Workflow data named above is back in place (P)",
                      comp.rerun_phrase(True, True, "P"))

    def test_options_drop_a_release_dir_of_another_version_and_say_so(self):
        context = self.ctx(a_release_dir=Path("/d"), release_dir_version="2.6.0")
        options, note = advice._options(context, "2.9.1")
        self.assertEqual(options, ())
        self.assertIn("--release-dir /d holds 2.6.0, so it is left out", note)
        options, note = advice._options(context, "2.6.0")
        self.assertEqual(options, (("--release-dir", Path("/d")),))
        self.assertIsNone(note)

    def test_a_local_source_record_gets_no_command_when_the_directory_differs(self):
        context = self.ctx(installed_version="9.9.9", installed_local=True, release_dir_version="2.6.0")
        step = advice.problem_step(context, ["modified: scripts/x.py"])
        self.assertIn("a release directory holding 9.9.9 is needed: run the command again with "
                      "--release-dir DIR", step)
        self.assertNotIn("workflow-manager", step)

    def test_data_step_for_a_malformed_file_copies_to_the_first_free_name(self):
        from workflow_manager.compatibility import DataFile
        context = self.ctx(data_files=(DataFile(STATE, "malformed", STATE + ".bak.1"),),
                           holds_data=True)
        step = advice.data_step(context)
        self.assertIn(f"`cp -p -- /t/{STATE} /t/{STATE}.bak.1`", step)
        unreadable = advice.data_step(self.ctx(data_files=(DataFile(STATE, "unreadable"),)))
        self.assertIn(f"`ls -ld -- /t/{STATE}`", unreadable)
        self.assertNotIn("cp -p", unreadable)
        self.assertNotIn("chmod", unreadable)

    def test_data_files_name_a_free_backup_and_never_overwrite_one(self):
        from workflow_manager.compatibility import data_files
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs/ai-workflow").mkdir(parents=True)
            (root / STATE).write_text("{ bad")
            (root / (STATE + ".bak")).write_text("older copy")
            from workflow_manager.compatibility import Finding, WARNING
            finding = Finding(WARNING, "incomplete-inspection", "the inspection could not be completed",
                              f"{STATE} cannot be read as JSON (x)")
            files = data_files(root, (), (finding,))
            self.assertEqual([(f.path, f.state, f.backup) for f in files],
                             [(STATE, "malformed", STATE + ".bak.1")])

    def test_predicate_rows_ask_for_the_data_facts(self):
        from workflow_manager.install import AlreadyManagedError, TargetNotFoundError
        args = argparse.Namespace(command="update", dry_run=False)
        self.assertTrue(advice.needs_data(AlreadyManagedError("x"), args))
        self.assertFalse(advice.needs_data(TargetNotFoundError("x"), args))
        self.assertTrue(advice.needs_data(PermissionError("x"), args))
        self.assertFalse(advice.needs_data(PermissionError("x"),
                                           argparse.Namespace(command="verify", dry_run=False)))
        self.assertFalse(advice.needs_data(PermissionError("x"),
                                           argparse.Namespace(command="update", dry_run=True)))

    def test_the_schema_error_distinguishes_newer_from_damaged(self):
        from workflow_manager.installation import UnsupportedInstallationSchemaError as E
        self.assertTrue(E("m", 2).newer)
        for value in (None, "1", 0, 1, True, -1):
            self.assertFalse(E("m", value).newer, value)



if __name__ == "__main__":
    unittest.main()
