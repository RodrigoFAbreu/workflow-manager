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
import importlib.util
import io
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

import support
from support import REPO_ROOT, cli_env

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


if __name__ == "__main__":
    unittest.main()
