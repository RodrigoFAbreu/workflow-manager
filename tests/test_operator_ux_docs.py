#!/usr/bin/env python3
"""Operator UX, documentation: the pages quote what the Manager prints.

Each row of `docs/common-problems.md` that quotes a Manager message is paired
with the case that raises it. The quoted fragment must be a substring of the
case's real output, and the row's fix must name the step the `next:` line
names. Every message `docs/exit-codes.md` quotes is checked the same way, and
so are the exit codes the table gives. A row that quotes something else (a
shell, `pipx`, a finding the report prints) is listed in `NOT_A_MESSAGE`; a
new row that is in neither place fails.
"""

from __future__ import annotations

import re
import unittest
import unittest.mock
from pathlib import Path

from support import NEWEST_RELEASE, REPO_ROOT

import test_operator_ux as ux
from test_operator_ux import next_lines, run

COMMON = REPO_ROOT / "docs" / "common-problems.md"
EXIT_CODES = REPO_ROOT / "docs" / "exit-codes.md"
RECORD = ".workflow-manager/installation.json"

#: Rows whose first column is not a Manager message, or is the report's own
#: finding (tested by `test_operator_ux_report`).
NOT_A_MESSAGE = (
    "`workflow-manager: command not found`",
    "`--version` prints `1.0.0` or \"development build\"",
    "A cache that seems stale or damaged",
    "`doctor` or `update --dry-run` reports a `blocked` finding",
    "`doctor` reports a `warning` finding",
    "`doctor` reports `incomplete-inspection`",
    "A repository went wrong after an update to 2.8.0 and gates behave differently",
    "An interrupted `bootstrap` or `update`, or `[Errno 13] Permission denied` and other "
    "file errors (exit 1)",
)


def rows(path: Path) -> dict[str, str]:
    """The first column to the last of the page's table rows."""
    table = {}
    for line in path.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| What you see") \
                or line.startswith("| Code"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) >= 2:
            table[cells[0]] = cells[-1]
    return table


class Docs(ux.ReleaseCase):
    def run_case(self, name):
        """The exit code, the whole output and the `next:` line of case `name`."""
        proc = getattr(self, f"case_{name}")()
        return proc.returncode, proc.stdout + proc.stderr, " ".join(next_lines(proc.stdout + proc.stderr))

    def case_misplaced(self):
        return run("update", str(self.empty()), "--release-version", NEWEST_RELEASE)

    def case_no_command(self):
        return run()

    def case_no_directory(self):
        return run("bootstrap", str(self.workdir() / "nope"))

    def case_not_git(self):
        plain = self.workdir() / "plain"
        plain.mkdir()
        return run("bootstrap", str(plain))

    def case_already(self):
        return run("bootstrap", str(self.fresh()))

    def case_unmanaged(self):
        return run("verify", str(self.empty()))

    def case_collision(self):
        repo = self.empty()
        (repo / "scripts").mkdir()
        (repo / "scripts" / "workflow_state.py").write_text("mine\n")
        return run("bootstrap", str(repo))

    def edited(self):
        repo = self.fresh()
        with (repo / "scripts" / "workflow_state.py").open("a") as handle:
            handle.write("# edit\n")
        return repo

    def case_drift(self):
        repo = self.edited()
        self.commit(repo)
        return run("update", str(repo))

    def case_problems(self):
        return run("verify", str(self.edited()))

    def case_cannot_fetch(self):
        work = self.workdir()
        return run("--release-cache", str(work / "cache"), "--release-source",
                   str(work / "empty"), "bootstrap", str(self.empty()))

    def case_digest(self):
        work = self.workdir()
        mirror = self.mirror(work)
        archive = mirror / NEWEST_RELEASE / f"workflow-{NEWEST_RELEASE}.tar.gz"
        archive.write_bytes(archive.read_bytes() + b"x")
        return run("--release-cache", str(work / "cache"), "--release-source", str(mirror),
                   "bootstrap", str(self.empty()))

    def case_unpublished(self):
        return run("--release-version", "9.9.9", "bootstrap", str(self.empty()))

    def case_unreadable(self):
        repo = self.fresh()
        (repo / RECORD).write_text("{")
        return run("verify", str(repo))

    def case_newer(self):
        repo = self.fresh()
        text = (repo / RECORD).read_text()
        (repo / RECORD).write_text(text.replace('"schema_version": 1', '"schema_version": 2', 1))
        return run("verify", str(repo))

    def case_doctor_unmanaged(self):
        return run("doctor", str(self.empty()))

    def case_status_unmanaged(self):
        return run("status", str(self.empty()))

    def case_in_flight(self):
        return run("status", str(self.fresh()))

    #: first column of common-problems.md -> (case, fragments the output must
    #: hold, words the row's fix and the `next:` line must both hold)
    ROWS = {
        "`unrecognized arguments: --release-version ...` (or another global option)":
            ("misplaced", ["unrecognized arguments: --release-version"], ["global options"]),
        "`the following arguments are required: COMMAND` or `invalid choice`":
            ("no_command", ["the following arguments are required: COMMAND"], []),
        "`no directory at ...`": ("no_directory", ["no directory at"], ["git init"]),
        "`is not a Git repository`": ("not_git", ["is not a Git repository"], ["git init"]),
        "`is already managed (workflow X is installed)`":
            ("already", ["is already managed (workflow"], ["update"]),
        "`is not a managed repository`":
            ("unmanaged", ["is not a managed repository"], ["bootstrap"]),
        "`refusing to bootstrap: the repository already has its own file at these release "
        "paths`": ("collision", ["refusing to bootstrap: the repository already has its own "
                                 "file at these release paths", "occupied:"], ["--force"]),
        "`refusing to update: these release files were modified locally`":
            ("drift", ["refusing to update: these release files were modified locally",
                       "modified:"], ["--force", "--dry-run"]),
        "`verify` prints `N problem(s)`":
            ("problems", ["1 problem(s)", "modified:"], ["update", "--force"]),
        "`cannot fetch ...`":
            ("cannot_fetch", ["cannot fetch"], ["--release-source"]),
        "`does not match its pin` or `is damaged`":
            ("digest", ["does not match its pin"], ["again"]),
        "`release X is not published: this Manager has no pin for it`":
            ("unpublished", ["is not published: this Manager has no pin for it"],
             ["update.md#update-the-manager"]),
        "`the installation record at ... is unreadable`":
            ("unreadable", ["the installation record at", "is unreadable"], ["bootstrap"]),
        "`was written by a newer Manager`":
            ("newer", ["was written by a newer Manager"], ["update.md#update-the-manager"]),
        "`status` prints `work in flight:`": ("in_flight", ["work in flight:"], []),
    }

    def test_every_common_problems_row_is_paired_with_a_case_or_listed(self):
        table = rows(COMMON)
        for first in table:
            self.assertTrue(first in self.ROWS or first in NOT_A_MESSAGE, first)
        for first in self.ROWS:
            self.assertIn(first, table)

    def test_each_quoted_message_is_in_the_real_output_and_the_fix_names_the_step(self):
        table = rows(COMMON)
        for first, (name, fragments, shared) in self.ROWS.items():
            with self.subTest(row=first):
                _, text, step = self.run_case(name)
                for fragment in fragments:
                    self.assertIn(fragment, text)
                for word in shared:
                    self.assertIn(word, step)
                fix = table[first]
                for word in shared:
                    if word in ("global options", "again", "update.md#update-the-manager"):
                        continue        # the page link and prose are not the command
                    self.assertIn(word, fix)

    #: case -> (the command column the row names, a phrase of its meaning column):
    #: the row the case is bound to; its code is read from the page.
    EXIT_ROWS = {
        "misplaced": ("every command", "did not parse"),
        "no_command": ("every command", "did not parse"),
        "already": ("`bootstrap`", "already managed"),
        "unmanaged": ("`verify`", "is not managed"),
        "collision": ("`bootstrap`", "files in the way"),
        "drift": ("`update`", "edited locally"),
        "problems": ("`verify`", "N problem(s)"),
        "cannot_fetch": ("`bootstrap`", "No usable release"),
        "digest": ("`bootstrap`", "No usable release"),
        "unreadable": ("`verify`", "record is unreadable"),
        "newer": ("`verify`", "record is unreadable"),
        "in_flight": ("every command", "It succeeded"),
        "doctor_unmanaged": ("`doctor`", "It could not check"),
        "status_unmanaged": ("every command", "or not managed"),
    }
    FRAGMENTS = {
        "misplaced": "unrecognized", "no_command": "required",
        "already": "is already managed", "unmanaged": "is not a managed",
        "collision": "refusing to bootstrap", "drift": "refusing to update",
        "problems": "problem(s)", "cannot_fetch": "cannot fetch",
        "digest": "does not match", "unreadable": "is unreadable",
        "newer": "newer Manager", "in_flight": "work in flight:",
        "doctor_unmanaged": "is not a managed", "status_unmanaged": "not a managed",
    }

    @staticmethod
    def documented_code(command, phrase):
        """The one code the page gives the row whose command column holds `command`
        and whose meaning holds `phrase`; fails when no row, or several codes, match."""
        codes = set()
        for line in EXIT_CODES.read_text().splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if len(cells) == 4 and cells[0].isdigit() and command in cells[1] and phrase in cells[2]:
                codes.add(int(cells[0]))
        return codes

    def test_the_exit_codes_page_quotes_messages_the_manager_prints(self):
        text = EXIT_CODES.read_text()
        self.assertEqual(set(self.EXIT_ROWS), set(self.FRAGMENTS))
        for name, (command, phrase) in self.EXIT_ROWS.items():
            with self.subTest(name):
                got, output, _ = self.run_case(name)
                self.assertEqual(self.documented_code(command, phrase), {got},
                                 f"{name}: the page gives these codes for the row; "
                                 f"the command exited {got}\n{output}")
                self.assertIn(self.FRAGMENTS[name], output)
        for quote in ("`N problem(s)`", "`modified:`", "`--force`", "`TMPDIR`",
                      "`--release-cache`", "`next:`", "`error:`"):
            self.assertIn(quote, text)

    def test_a_drifted_documented_code_fails_the_check(self):
        """The check can fail: with the page's `verify` refusal changed from 2 to 3 the
        documented code no longer equals the real one."""
        original = EXIT_CODES.read_text()
        drifted = original.replace("| 2 | `verify` | The repository is not managed",
                                   "| 3 | `verify` | The repository is not managed")
        self.assertNotEqual(drifted, original)
        got, _, _ = self.run_case("unmanaged")
        with unittest.mock.patch.object(Path, "read_text", lambda self_, *a, **k:
                                        drifted if self_ == EXIT_CODES else original):
            self.assertNotEqual(self.documented_code("`verify`", "is not managed"), {got})

    def test_every_page_a_message_links_to_resolves(self):
        urls = set()
        for name in ("misplaced", "unpublished", "newer", "unreadable"):
            urls.update(ux.pages(self.run_case(name)[1]))
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(ux.resolves(url), url)


if __name__ == "__main__":
    unittest.main()
