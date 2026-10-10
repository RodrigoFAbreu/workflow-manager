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
    """The docs URLs of the `next:` lines. An example URL a step shows as a
    pattern (`https://host/releases/v{version}/`) is not a page."""
    found = [m.rstrip(".,;:)`") for line in next_lines(output) for m in URL_RE.findall(line)]
    return [url for url in found if not url.startswith("https://host/")]


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
        # One `next:` line: the repair, then T16's doctor clause.
        self.assertEqual(next_lines(status.stdout),
                         [f"{step[0]}; `workflow-manager doctor {repo}` reports what an update "
                          "would meet"])

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



# ---------------------------------------------------------------------------
# CP3: releases, sources, the cache, packages (R rows) and containment (C rows)
# ---------------------------------------------------------------------------

from unittest import mock

from workflow_manager import compatibility as comp
from workflow_manager import source as release_source
from workflow_manager.release import ReleaseIntegrityError


def main_in_process(*argv):
    """`cli.main` with its streams captured: for a case that needs a patched
    module attribute (the pin file, a size cap, a test seam)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ReleaseCase(TargetCase):
    """A mirror (a source directory holding a real release's three assets), a
    fresh cache and a copy of a release directory, each in a temporary folder."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        support.release(NEWEST_RELEASE)     # fills the shared cache
        cls.published = release_source.cache_root() / NEWEST_RELEASE

    def workdir(self) -> Path:
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        return Path(work.name)

    def mirror(self, base=None) -> Path:
        """`<mirror>/<version>/` with the three assets of the newest release."""
        mirror = (base or self.workdir()) / "mirror"
        folder = mirror / NEWEST_RELEASE
        folder.mkdir(parents=True)
        for name in (release_source.SUMS_NAME, f"workflow-{NEWEST_RELEASE}.tar.gz",
                     f"workflow-{NEWEST_RELEASE}.manifest.json"):
            shutil.copyfile(self.published / name, folder / name)
        return mirror

    def release_dir(self, base=None, version=None) -> Path:
        """A copy of the newest release directory; with `version`, a manifest
        that names it (an unpublished release)."""
        directory = (base or self.workdir()) / "release"
        shutil.copytree(support.release(NEWEST_RELEASE).root, directory)
        if version is not None:
            self.edit_manifest(directory, lambda m: m.update(workflow_version=version))
        return directory

    def edit_manifest(self, folder, change):
        target = Path(folder) / "manifest.json"
        manifest = json.loads(target.read_text())
        replacement = change(manifest)
        target.write_text(json.dumps(replacement.value if isinstance(replacement, Replace)
                                     else manifest))


import json


class Replace:
    """What a manifest edit returns to replace the whole manifest (`null` too)."""

    def __init__(self, value):
        self.value = value


class TestReleaseRows(ReleaseCase):
    def test_r2_an_unpublished_version_needs_a_newer_manager_or_a_directory(self):
        repo = self.empty()
        proc = self.check(Case(
            "R2", ["--release-version", "9.9.9", "bootstrap", str(repo)], exit_code=1,
            cause="release 9.9.9 is not published: this Manager has no pin for it (pinned:",
            step=["a published release needs a newer Manager that pins it",
                  "update.md#update-the-manager", "then run the command again",
                  f"`workflow-manager --release-version 9.9.9 --release-dir DIR bootstrap {repo}`"]))
        self.assertNotIn("installs only from a local directory", proc.stderr)

    def test_r2_carries_the_operators_own_command(self):
        repo = self.fresh()
        self.check(Case(
            "R2 status", ["--release-version", "9.9.9", "status", str(repo)], exit_code=1,
            cause="release 9.9.9 is not published",
            step=[f"`workflow-manager --release-version 9.9.9 --release-dir DIR status {repo}`"]))
        self.check(Case(
            "R2 dry-run", ["--release-version", "9.9.9", "update", str(repo), "--dry-run"],
            exit_code=1, cause="release 9.9.9 is not published",
            step=[f"--release-dir DIR update --dry-run {repo}`"]))

    def test_r1_no_pins_installs_only_an_unpackaged_directory(self):
        work = self.workdir()
        empty = work / "pins.json"
        empty.write_text('{"schema_version": 1, "repository": "example/workflow", "releases": {}}')
        repo = self.empty()
        with mock.patch.object(release_source, "PINS_PATH", empty):
            code, _, err = main_in_process("bootstrap", str(repo))
        self.assertEqual(code, 1)
        self.assertIn("error: no Workflow release is published: this Manager pins none\n", err)
        self.assertNotIn("Install an unpackaged", err)
        step = next_lines(err)[0]
        self.assertIn("upgrade the Manager (", step)
        self.assertIn(f"`workflow-manager --release-dir DIR bootstrap {repo}`", step)
        self.assertTrue(all(parses(argv) for argv in manager_commands(err)))
        self.assertTrue(all(resolves(url) for url in pages(err)))

    def test_r3_a_url_source_that_cannot_be_reached(self):
        repo = self.empty()
        cache = self.workdir() / "cache"
        proc = self.check(Case(
            "R3 url", ["--release-cache", str(cache), "--release-source",
                       "http://127.0.0.1:9/{version}/", "bootstrap", str(repo)],
            exit_code=1, cause="cannot fetch http://127.0.0.1:9/",
            step=["connect to the network and run the same command again",
                  f"a mirror that holds {NEWEST_RELEASE}/ (a directory, or a URL with {{version}})",
                  "--release-source MIRROR", f"--release-cache {cache}"]))
        self.assertFalse(is_managed_repo(repo))
        self.assertIn("bootstrap", next_lines(proc.stderr)[0])

    def test_r3_a_directory_source_without_the_release(self):
        work = self.workdir()
        source = work / "empty"
        source.mkdir()
        repo = self.empty()
        self.check(Case(
            "R3 directory", ["--release-cache", str(work / "cache"), "--release-source",
                             str(source), "bootstrap", str(repo)], exit_code=1,
            cause=f"cannot fetch {source}/{NEWEST_RELEASE}/",
            step=[f"the source directory {source} has no {NEWEST_RELEASE}/ with SHA256SUMS, the "
                  "archive and the manifest asset", "fix --release-source (or "
                  "$WORKFLOW_MANAGER_RELEASE_SOURCE), or leave it unset to download"]))

    def test_r4_a_url_source_without_a_version_field(self):
        repo = self.empty()
        self.check(Case(
            "R4", ["--release-source", "https://example.org/releases/", "bootstrap", str(repo)],
            exit_code=1, cause="release source 'https://example.org/releases/' has no {version} field",
            step=["write the source as a directory, or as a URL with {version} in it, for "
                  "example https://host/releases/v{version}/"]))

    def test_the_causes_that_already_name_their_fix_print_no_next_line(self):
        repo = self.empty()
        proc = run("--release-source", "ftp://example.org/{version}/", "bootstrap", str(repo))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("refusing release source", proc.stderr)
        self.assertEqual(next_lines(proc.stderr), [])
        cache = self.workdir() / "file"
        cache.write_text("not a directory")
        proc = run("--release-cache", str(cache), "bootstrap", str(repo))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot use the release cache", proc.stderr)
        self.assertEqual(next_lines(proc.stderr), [])

    def test_r5_a_source_answer_over_the_size_cap(self):
        work = self.workdir()
        mirror = self.mirror(work)
        repo = self.empty()
        with mock.patch.object(release_source, "MAX_ASSET_BYTES", 10):
            code, _, err = main_in_process("--release-cache", str(work / "cache"),
                                           "--release-source", str(mirror), "bootstrap", str(repo))
        self.assertEqual(code, 1)
        self.assertIn("is larger than 10 bytes", err)
        self.assertIn("the source answered with something that is not a Workflow package or a "
                      "safe redirect; check --release-source", next_lines(err)[0])

    def test_r7_a_cache_that_cannot_store_the_release(self):
        work = self.workdir()
        mirror = self.mirror(work)
        repo = self.empty()
        with mock.patch.object(release_source.os, "rename", side_effect=OSError(28, "No space")):
            code, _, err = main_in_process("--release-cache", str(work / "cache"),
                                           "--release-source", str(mirror), "bootstrap", str(repo))
        self.assertEqual(code, 1)
        self.assertIn(f"cannot store release {NEWEST_RELEASE} in the cache {work / 'cache'}", err)
        step = next_lines(err)[0]
        self.assertIn(f"free space or fix permissions on {work / 'cache'}, or choose another "
                      f"cache: `workflow-manager --release-source {mirror} --release-cache DIR "
                      f"bootstrap {repo}`", step)
        self.assertTrue(all(parses(argv) for argv in manager_commands(err)))

    def test_r8_a_tampered_archive_says_to_retry_then_report(self):
        work = self.workdir()
        mirror = self.mirror(work)
        archive = mirror / NEWEST_RELEASE / f"workflow-{NEWEST_RELEASE}.tar.gz"
        archive.write_bytes(archive.read_bytes() + b"x")
        repo = self.empty()
        proc = self.check(Case(
            "R8", ["--release-cache", str(work / "cache"), "--release-source", str(mirror),
                   "bootstrap", str(repo)], exit_code=1,
            cause=f"release {NEWEST_RELEASE}'s archive does not match its pin",
            step=["run the same command again (it downloads afresh). If the digests differ "
                  "again, install nothing from this download and report it to the Manager's "
                  "maintainer with this message"]))
        self.assertNotIn("Manager repository", proc.stderr)

    def test_r8_a_malformed_sums_file(self):
        work = self.workdir()
        mirror = self.mirror(work)
        (mirror / NEWEST_RELEASE / "SHA256SUMS").write_text("nonsense\n")
        repo = self.empty()
        self.check(Case(
            "R8 sums", ["--release-cache", str(work / "cache"), "--release-source", str(mirror),
                        "bootstrap", str(repo)], exit_code=1, cause="SHA256SUMS has a malformed line",
            step=["run the same command again"]))

    def test_r9_a_cache_entry_that_keeps_changing(self):
        work = self.workdir()
        mirror = self.mirror(work)
        repo = self.empty()

        def corrupt(snapshot, entry):
            (snapshot / "manifest.json").write_text("{}")

        with mock.patch.object(release_source.ReleaseCache, "_after_snapshot_copy",
                              staticmethod(corrupt)):
            code, _, err = main_in_process("--release-cache", str(work / "cache"),
                                           "--release-source", str(mirror), "bootstrap", str(repo))
        self.assertEqual(code, 1)
        self.assertIn("cache entry changed while it was being copied, twice", err)
        self.assertIn(f"another process is writing the release cache {work / 'cache'}; wait for it "
                      "to finish and run the command again", next_lines(err)[0])

    def test_r10_a_damaged_pin_file(self):
        work = self.workdir()
        pins = work / "pins.json"
        pins.write_text("{}")
        repo = self.empty()
        with mock.patch.object(release_source, "PINS_PATH", pins):
            code, _, err = main_in_process("bootstrap", str(repo))
        self.assertEqual(code, 1)
        self.assertIn(f"error: the pin file {pins} is malformed", err)
        self.assertIn("the Manager's own pin file is damaged; reinstall the Manager: "
                      + advice.page("update.md", "update-the-manager"), next_lines(err)[0])
        self.assertTrue(all(resolves(url) for url in pages(err)))

    def test_r11_a_release_directory_that_is_not_the_release_it_claims(self):
        repo = self.empty()
        step = ["use an unmodified copy of the release directory, or leave --release-dir out so "
                "the Manager uses the published, checksummed package"]
        edited = self.release_dir()
        victim = next(p for p in sorted(edited.rglob("*.py")))
        victim.write_text(victim.read_text() + "\n# edited\n")
        self.check(Case("R11 fails verification",
                        ["--release-dir", str(edited), "bootstrap", str(repo)], exit_code=1,
                        cause=f"release {NEWEST_RELEASE} at {edited} fails verification", step=step))
        claimed = self.release_dir()
        self.edit_manifest(claimed, lambda m: m.update(provenance={"origin": "tampered"}))
        self.check(Case("R11 claims published",
                        ["--release-dir", str(claimed), "bootstrap", str(repo)], exit_code=1,
                        cause=f"{claimed} claims published release {NEWEST_RELEASE}", step=step))
        self.check(Case("R11 version",
                        ["--release-dir", str(self.release_dir()), "--release-version", "7.7.7",
                         "bootstrap", str(repo)], exit_code=1,
                        cause="not the requested 7.7.7", step=step))
        nothing = self.workdir()
        self.check(Case("R11 not a release",
                        ["--release-dir", str(nothing), "bootstrap", str(repo)], exit_code=1,
                        cause=f"{nothing} is not a release", step=step))

    def test_r11_unsafe_location_and_link(self):
        repo = self.empty()
        step = ["use an unmodified copy of the release directory"]
        unsafe = self.release_dir(version="99.0.1")
        self.edit_manifest(unsafe, lambda m: m["artifacts"][0].update(location="../escape"))
        self.check(Case("R11 unsafe", ["--release-dir", str(unsafe), "bootstrap", str(repo)],
                        exit_code=1, cause="unsafe manifest location '../escape'", step=step))
        linked = self.release_dir(version="99.0.2")
        record = json.loads((linked / "manifest.json").read_text())["artifacts"][0]
        target = linked / record["location"]
        target.rename(target.with_name("moved"))
        target.symlink_to("moved")
        self.check(Case("R11 link", ["--release-dir", str(linked), "bootstrap", str(repo)],
                        exit_code=1, cause=f"{record['location']} is a link", step=step))

    def test_r12_a_damaged_release_file_names_the_directory_or_the_cache_step(self):
        directory = self.release_dir(version="99.0.3")
        record = json.loads((directory / "manifest.json").read_text())["artifacts"][0]
        (directory / record["location"]).write_bytes(b"changed")
        try:
            release = release_source.Release(directory)
            release.read_verified(record["location"], record["sha256"])
        except ReleaseIntegrityError as caught:
            error = caught
            self.assertEqual(error.kind, "damaged")
            self.assertIn(f"release 99.0.3 is damaged: {record['location']} has digest", str(error))
            self.assertNotIn("Refetch", str(error))
        else:
            self.fail("expected a ReleaseIntegrityError")
        args = argparse.Namespace(command="bootstrap", target=Path("/t"), release_version=None,
                                  release_source=None, release_cache=None, release_dir=Path("/d"),
                                  profile="full", force=False, dry_run=False)
        local = advice.next_step(error, advice.Context(args=args))
        self.assertIn("use an unmodified copy of the release directory", local)
        args.release_dir = None
        cached = advice.next_step(error, advice.Context(args=args))
        self.assertIn("run the command again", cached)
        self.assertIn("report it to the Manager's maintainer with this message", cached)

    def test_r13_a_package_that_is_not_what_its_digest_says(self):
        work = self.workdir()
        archive = self.published / f"workflow-{NEWEST_RELEASE}.tar.gz"
        step = ["download the archive again and compare it with SHA256SUMS: `sha256sum -c SHA256SUMS`"]
        self.check(Case("R13 digest", ["package", "verify", str(archive), "--sha256", "0" * 64],
                        exit_code=1, cause=f"{archive} has digest", step=step))
        broken = work / "broken.tar.gz"
        broken.write_bytes(b"not a gzip")
        self.check(Case("R13 unreadable", ["package", "verify", str(broken)], exit_code=1,
                        cause=f"{broken} is not a readable package", step=step))
        empty = work / "empty.tar.gz"
        import tarfile
        with tarfile.open(empty, "w:gz"):
            pass
        self.check(Case("R13 empty", ["package", "verify", str(empty)], exit_code=1,
                        cause=f"{empty} is empty", step=step))

    def test_r14_package_build_needs_a_release_directory(self):
        work = self.workdir()
        build = ["package build DIR --out OUT"]
        self.check(Case("R14 empty", ["package", "build", str(work), "--out", str(work / "o")],
                        exit_code=1, cause=f"{work} is not a release", step=build))
        edited = self.release_dir()
        victim = next(p for p in sorted(edited.rglob("*.py")))
        victim.write_text(victim.read_text() + "\n# edited\n")
        self.check(Case("R14 verification", ["package", "build", str(edited), "--out",
                                             str(work / "o")], exit_code=1,
                        cause=f"release {NEWEST_RELEASE} at {edited} fails verification", step=build))


def is_managed_repo(repo) -> bool:
    return (Path(repo) / RECORD).exists()


class TestWithheldRelease(ReleaseCase):
    """A step that would re-run or reprint a write is withheld while the
    target holds Workflow data and a state template is missing (3.2)."""

    def broken(self):
        repo = self.fresh()
        (repo / CONFIG).unlink()
        shutil.rmtree(repo / ".workflow-manager")
        return repo

    def test_r2_r8_and_r3_print_no_writing_command_and_no_again(self):
        repo = self.broken()
        work = self.workdir()
        mirror = self.mirror(work)
        archive = mirror / NEWEST_RELEASE / f"workflow-{NEWEST_RELEASE}.tar.gz"
        archive.write_bytes(archive.read_bytes() + b"x")
        cases = {
            "R2": ["--release-version", "9.9.9", "bootstrap", str(repo)],
            "R8": ["--release-cache", str(work / "c1"), "--release-source", str(mirror),
                   "bootstrap", str(repo)],
            "R3": ["--release-cache", str(work / "c2"), "--release-source",
                   "http://127.0.0.1:9/{version}/", "bootstrap", str(repo)],
        }
        for name, argv in cases.items():
            with self.subTest(name):
                proc = run(*argv)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                step = next_lines(proc.stderr)[0]
                self.assertNoWritingCommand(step)
                self.assertIn("common-problems.md#repair-workflow-data-by-hand", step)
                self.assertIn("do not run it again until the Workflow data named above is back "
                              "in place", step)
        self.assertFalse((repo / CONFIG).exists())

    def test_a_read_only_command_keeps_its_command_with_the_same_missing_template(self):
        repo = self.broken()
        proc = run("--release-version", "9.9.9", "status", str(repo))
        step = next_lines(proc.stderr)[0] if next_lines(proc.stderr) else ""
        self.assertIn(f"`workflow-manager --release-version 9.9.9 --release-dir DIR status {repo}`", step)


class TestManifestSweep(ReleaseCase):
    """3.3a: every manifest shape that crashed becomes a classified refusal;
    every shape that succeeded still does, with the same exit."""

    COMMANDS = ("package build", "bootstrap", "update", "update --dry-run", "verify", "status",
                "doctor")

    @staticmethod
    def make(name):
        return {
            "version list": lambda m: m.update(workflow_version=[1]),
            "version object": lambda m: m.update(workflow_version={"a": 1}),
            "version null": lambda m: m.update(workflow_version=None),
            "version empty": lambda m: m.update(workflow_version=""),
            "version number": lambda m: m.update(workflow_version=7),
            "version true": lambda m: m.update(workflow_version=True),
            "manifest null": lambda m: Replace(None),
            "manifest list": lambda m: Replace([]),
            "artifacts null": lambda m: m.update(artifacts=None),
            "artifacts object": lambda m: m.update(artifacts={}),
            "record not a mapping": lambda m: m.update(artifacts=["x"]),
            "templates missing": lambda m: m.pop("templates") and None,
            "upstream missing": lambda m: m.pop("upstream") and None,
            "location number": lambda m: m["artifacts"][0].update(location=7),
            "location null": lambda m: m["artifacts"][0].update(location=None),
        }[name]

    #: Exit per command, in `COMMANDS` order, after this milestone (3.3a). The
    #: unchanged cells equal the base's, recorded from the unchanged code.
    TABLE = {
        "version list":         (0, 1, 1, 1, 1, 1, 2),
        "version object":       (0, 1, 1, 1, 1, 1, 2),
        "version null":         (0, 0, 0, 0, 1, 1, 0),
        "version empty":        (0, 0, 0, 0, 1, 1, 0),
        "version number":       (0, 0, 0, 2, 1, 1, 2),
        "version true":         (0, 0, 0, 2, 1, 1, 2),
        "manifest null":        (1, 1, 1, 1, 1, 1, 2),
        "manifest list":        (1, 1, 1, 1, 1, 1, 2),
        "artifacts null":       (1, 1, 1, 1, 1, 1, 2),
        "artifacts object":     (1, 1, 1, 1, 1, 1, 2),
        "record not a mapping": (1, 1, 1, 1, 1, 1, 2),
        "templates missing":    (1, 1, 1, 1, 1, 1, 2),
        "upstream missing":     (1, 1, 1, 1, 1, 1, 2),
        "location number":      (1, 1, 1, 1, 1, 1, 2),
        "location null":        (1, 1, 1, 1, 1, 1, 2),
    }
    #: The same locations with `--release-version` equal to the manifest's own
    #: version: `_copy_snapshot` runs for every command (`package build` aside).
    REQUESTED = {"location number": (None, 1, 1, 1, 1, 1, 2),
                 "location null": (None, 1, 1, 1, 1, 1, 2)}

    def cell(self, name, command, requested=None):
        directory = self.release_dir(version="99.0.0")
        self.edit_manifest(directory, self.make(name))
        if command == "package build":
            return run("package", "build", str(directory), "--out", str(self.workdir() / "o")), None
        repo = self.empty() if command == "bootstrap" else self.fresh()
        options = ["--release-dir", str(directory)]
        if requested:
            options += ["--release-version", requested]
        words = command.split()
        argv = [*options, words[0], str(repo), *words[1:]]
        return run(*argv), repo

    def test_every_cell_by_value(self):
        from concurrent.futures import ThreadPoolExecutor
        Pristine.pristine()     # built once, before the cells copy it in parallel
        jobs = []
        for name, row in self.TABLE.items():
            for command, expected in zip(self.COMMANDS, row):
                jobs.append((name, command, expected, None))
        for name, row in self.REQUESTED.items():
            for command, expected in zip(self.COMMANDS, row):
                if expected is not None:
                    jobs.append((name, command, expected, "99.0.0"))
        with ThreadPoolExecutor(max_workers=8) as pool:
            cells = list(pool.map(lambda job: (job, self.cell(job[0], job[1], job[3])), jobs))
        for (name, command, expected, requested), (proc, repo) in cells:
            out = proc.stdout + proc.stderr
            with self.subTest(manifest=name, command=command, requested=requested):
                self.assertNotIn("Traceback", out)
                self.assertEqual(proc.returncode, expected, out)
                # `not a release version` (a number or boolean version) is an
                # existing refusal that was never a crash: its text is unchanged.
                scalar_refusal = name in ("version number", "version true") and expected == 2
                if (proc.returncode == 1 or (proc.returncode == 2 and command == "doctor")) \
                        and not scalar_refusal:
                    self.assertIn("error:", proc.stderr)
                    self.assertEqual(len(next_lines(proc.stderr)), 1, proc.stderr)
                if expected == 0 and command in ("bootstrap", "update"):
                    record = json.loads((repo / RECORD).read_text())
                    wanted = {"version null": None, "version empty": "", "version number": 7,
                              "version true": True}[name]
                    self.assertEqual(record["workflow_version"], wanted)

    def test_a_shape_error_names_the_manifest_and_the_cause(self):
        proc = self.cell("version list", "bootstrap")[0]
        self.assertIn("manifest.json at", proc.stderr)
        self.assertIn("is malformed: workflow_version is a list, not text", proc.stderr)
        proc = self.cell("location number", "bootstrap")[0]
        self.assertIn("is malformed: a location that is not text (7)", proc.stderr)
        self.assertIn("use an unmodified copy of the release directory", proc.stderr)
        proc = self.cell("artifacts null", "package build")[0]
        self.assertIn("is malformed:", proc.stderr)
        self.assertIn("package build DIR --out OUT", proc.stderr)


class TestContainmentRows(ReleaseCase):
    def doctor(self, repo, *options, env=None):
        return run(*options, "doctor", str(repo), env=env)

    def test_c2_a_cache_inside_the_repository(self):
        repo = self.fresh()
        cache = repo / ".git" / "mycache"
        self.check(Case(
            "C2 inside", ["--release-cache", str(cache), "doctor", str(repo)], exit_code=2,
            cause=f"the release cache {cache} lies inside",
            step=["choose another cache: `workflow-manager --release-cache DIR doctor "
                  f"{repo}`"]))
        self.assertFalse(cache.exists())

    def test_c2_a_cache_entry_that_resolves_inside(self):
        repo = self.fresh()
        cache = self.workdir() / "cache"
        cache.mkdir()
        inside = repo / "elsewhere"
        inside.mkdir()
        (cache / NEWEST_RELEASE).symlink_to(inside)
        self.check(Case(
            "C2 entry", ["--release-cache", str(cache), "doctor", str(repo)], exit_code=2,
            cause=f"the release cache entry {cache / NEWEST_RELEASE} resolves to",
            step=["choose another cache: `workflow-manager --release-cache DIR doctor"]))

    def test_c2_a_cache_entry_holding_a_link(self):
        repo = self.fresh()
        cache = self.workdir() / "cache"
        entry = cache / NEWEST_RELEASE
        entry.mkdir(parents=True)
        (entry / "stray").symlink_to("/etc")
        self.check(Case(
            "C2 link", ["--release-cache", str(cache), "doctor", str(repo)], exit_code=2,
            cause=f"the release cache entry {entry} holds a link",
            step=["remove that cache entry, or choose another cache: "
                  "`workflow-manager --release-cache DIR doctor"]))

    def test_c2_a_temporary_directory_named_in_the_environment(self):
        repo = self.fresh()
        inside = repo / "tmp"
        inside.mkdir()
        self.check(Case(
            "C2 tmp", ["doctor", str(repo)], exit_code=2, env=cli_env(TMPDIR=str(inside)),
            cause="a temporary directory named in the environment",
            step=["point the temporary-directory variable (TMPDIR, TEMP or TMP) at a directory "
                  "outside the repository, or unset it, then run the command again"]))

    def test_c3_git_that_cannot_run(self):
        repo = self.fresh()
        proc = self.check(Case(
            "C3 git", ["doctor", str(repo)], exit_code=2, env=cli_env(PATH=""),
            cause="could not check containment",
            step=["make sure Git runs here (`env GIT_NO_LAZY_FETCH=1 git -C", "rev-parse --git-dir`)",
                  "then run the command again"]))
        self.assertTrue(proc.stderr.startswith("error: could not resolve")
                        or "error: could not check containment" in proc.stderr
                        or "could not check containment" in proc.stderr)

    def test_c3_no_temporary_directory_outside_the_repository(self):
        repo = self.fresh()
        environ = {k: v for k, v in os.environ.items() if k not in ("TMPDIR", "TEMP", "TMP")}
        before = os.getcwd()
        os.chdir(repo)
        self.addCleanup(os.chdir, before)
        with mock.patch.dict(os.environ, environ, clear=True), \
                mock.patch.object(comp, "_TEMP_FIXED", ()):
            code, _, err = main_in_process("doctor", str(repo))
        self.assertEqual(code, 2)
        self.assertIn("error: no temporary directory outside the target", err)
        self.assertEqual(next_lines(err),
                         ["set TMPDIR to a writable directory outside the repository and run "
                          "the command again"])

    def test_c1_doctor_prints_the_release_cause_and_its_step(self):
        repo = self.fresh()
        proc = self.check(Case(
            "C1", ["--release-version", "9.9.9", "doctor", str(repo)], exit_code=2,
            cause="error: could not resolve the target release: release 9.9.9 is not published",
            step=["a published release needs a newer Manager that pins it",
                  f"--release-dir DIR doctor {repo}`"]))
        self.assertEqual(proc.stdout, "")

    def test_c1_doctor_with_a_cause_that_names_its_own_fix_has_no_next_line(self):
        repo = self.fresh()
        cache = self.workdir() / "file"
        cache.write_text("x")
        proc = run("--release-cache", str(cache), "doctor", str(repo))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("could not resolve the target release: cannot use the release cache",
                      proc.stderr)


class TestAdviceCp3Units(unittest.TestCase):
    def ctx(self, **attrs):
        args = argparse.Namespace(command="bootstrap", target=Path("/t"), release_version=None,
                                  release_source=None, release_cache=None, release_dir=None,
                                  manager_root=None, profile="full", force=False, dry_run=False)
        for key, value in attrs.items():
            setattr(args, key, value)
        return advice.Context(args=args, cache_dir="/c")

    def test_a_kind_without_a_row_has_no_step(self):
        for error in (release_source.ReleaseUnavailableError("m", kind="cache-unusable"),
                      release_source.ReleaseUnavailableError("m"),
                      ReleaseIntegrityError("m"), comp.ContainmentError("m")):
            self.assertIsNone(advice.next_step(error, self.ctx()), error)

    def test_the_kind_defaults_so_every_untouched_raise_site_compiles(self):
        self.assertIsNone(ReleaseIntegrityError("m").kind)
        self.assertIsNone(release_source.ReleaseUnavailableError("m").kind)
        self.assertIsNone(release_source.ReleaseNotPublishedError("m").kind)
        self.assertIsNone(comp.ContainmentError("m").kind)

    def test_the_release_and_containment_errors_ask_for_the_data_facts_on_a_write_only(self):
        write = argparse.Namespace(command="bootstrap", dry_run=False)
        read = argparse.Namespace(command="doctor", dry_run=False)
        for error in (ReleaseIntegrityError("m", kind="digest"),
                      release_source.ReleaseUnavailableError("m", kind="fetch-url"),
                      release_source.ReleaseNotPublishedError("m", kind="unpinned")):
            self.assertTrue(advice.needs_data(error, write))
            self.assertFalse(advice.needs_data(error, read))
        self.assertFalse(advice.needs_data(comp.ContainmentError("m", kind="git"), write))

    def test_the_operator_command_keeps_profile_dry_run_and_the_sources(self):
        context = self.ctx(command="update", dry_run=True, release_source="/s", release_cache="/k",
                           release_version="2.9.1", target=Path("/t"))
        error = release_source.ReleaseNotPublishedError("m", kind="unpinned")
        step = advice.next_step(error, context)
        self.assertIn("`workflow-manager --release-version 2.9.1 --release-source /s "
                      "--release-cache /k --release-dir DIR update --dry-run /t`", step)
        context = self.ctx(profile="runtime")
        step = advice.next_step(release_source.ReleaseNotPublishedError("m", kind="none-pinned"), context)
        self.assertIn("`workflow-manager --release-dir DIR bootstrap --profile=runtime /t`", step)

    def test_a_manager_root_alias_is_named_when_it_is_the_option_in_use(self):
        error = ReleaseIntegrityError("m", kind="local-release")
        self.assertIn("leave --manager-root out", advice.next_step(error, self.ctx(
            manager_root=Path("/m"))))
        self.assertIn("leave --release-dir out", advice.next_step(error, self.ctx(
            release_dir=Path("/d"))))

    def test_a_hyphen_target_gets_double_dash_in_the_reprinted_command(self):
        error = release_source.ReleaseNotPublishedError("m", kind="unpinned")
        step = advice.next_step(error, self.ctx(target=Path("-repo")))
        command = backticked(step)[0]
        self.assertTrue(command.endswith("bootstrap -- -repo"), command)
        self.assertTrue(parses(shlex.split(command)))


if __name__ == "__main__":
    unittest.main()
