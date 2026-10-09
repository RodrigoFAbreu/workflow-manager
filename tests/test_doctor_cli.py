#!/usr/bin/env python3
"""`workflow-manager doctor` and `update --dry-run` through the entry point.

Exit codes, the fixed report headings, parity of the dry run with the real
update (the same change lines, the same refusal text and exit), and every
command the report prints validated by its family: Manager commands through
the real parser, Git commands by running them against a repository whose path
has spaces and shell metacharacters, slash commands against the release's
command file.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support
from support import NEWEST_RELEASE, REPO_ROOT, UPGRADE_FROM, cli_env

from frozen_runs import build_bootstrapped_repo
from workflow_manager import cli, source
from workflow_manager.compatibility import FAMILY_GIT, FAMILY_MANAGER, FAMILY_SLASH

WEIRD = "my repo $x;y 'q'"
STATE = "docs/ai-workflow/WORKFLOW_STATE.json"
HEADINGS = ("Repository", "Installed release", "Latest available", "Target of this check",
            "Work items (governing version is a protocol version, not a release)",
            "Config default for new work items:", "Findings --", "Fixes that apply only to new work",
            "Recovery")


def run(*args, env=None):
    return subprocess.run([sys.executable, "-m", "workflow_manager", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=env or cli_env())


def git(repo: Path, *args: str, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True,
                          text=True)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pristine = build_bootstrapped_repo(support.release(UPGRADE_FROM),
                                               Path(cls._tmp.name) / WEIRD)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def fresh(self, name="repo") -> Path:
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        repo = Path(work.name) / (WEIRD if name == "weird" else name)
        shutil.copytree(self.pristine, repo, symlinks=True)
        return repo

    def commit(self, repo: Path, message="work"):
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)


class TestDoctorExitCodes(Base):
    def test_a_clean_repository_exits_0_with_every_heading(self):
        proc = run("doctor", str(self.fresh()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for heading in HEADINGS:
            self.assertIn(heading, proc.stdout)
        self.assertIn("Findings -- nothing found", proc.stdout)

    def test_the_three_versions_are_labelled_and_never_share_a_line(self):
        out = run("doctor", str(self.fresh())).stdout
        self.assertRegex(out, rf"(?m)^Installed release   {re.escape(UPGRADE_FROM)}")
        self.assertRegex(out, rf"(?m)^Latest available    {re.escape(NEWEST_RELEASE)}")
        self.assertRegex(out, rf"(?m)^Target of this check {re.escape(NEWEST_RELEASE)}")

    def test_a_warning_exits_1(self):
        repo = self.fresh()
        (repo / "scratch.txt").write_text("dirty\n")
        proc = run("doctor", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("dirty-tree", proc.stdout)

    def test_a_downgrade_is_a_warning_not_an_error(self):
        proc = run("--release-version", "2.3.1", "doctor", str(self.fresh()))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("downgrade", proc.stdout)

    def test_a_target_that_is_not_managed_exits_2(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, True)
        proc = run("doctor", str(empty))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not a managed repository", proc.stderr)

    def test_a_corrupt_record_exits_2(self):
        repo = self.fresh()
        (repo / ".workflow-manager" / "installation.json").write_text("{not json")
        proc = run("doctor", str(repo))
        self.assertEqual(proc.returncode, 2, proc.stdout)

    def test_an_unpinned_target_release_exits_2_not_1(self):
        proc = run("--release-version", "9.9.9", "doctor", str(self.fresh()))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("could not resolve the target release", proc.stderr)

    def test_an_unavailable_target_release_exits_2(self):
        empty_cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_cache, True)
        proc = run("--release-cache", str(empty_cache), "--release-source", str(empty_cache / "src"),
                   "doctor", str(self.fresh()), env=cli_env(**{source.CACHE_ENV: str(empty_cache)}))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_an_unresolvable_installed_release_still_reports(self):
        # A cache holding only the target release: the installed one cannot be resolved.
        cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, cache, True)
        shutil.copytree(source.cache_root() / NEWEST_RELEASE, cache / NEWEST_RELEASE, symlinks=True)
        proc = run("--release-cache", str(cache), "--release-source", str(cache / "nowhere"),
                   "doctor", str(self.fresh()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("not-verified", proc.stdout)
        self.assertIn("still detected from the install record", proc.stdout)
        self.assertNotIn("was not checked", proc.stdout)

    def test_an_incomplete_inspection_is_never_exit_0(self):
        repo = self.fresh()
        (repo / STATE).write_text("{broken")
        self.commit(repo)
        proc = run("doctor", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("inspection incomplete", proc.stdout)
        # ... and the update itself is not refused for it.
        self.assertEqual(run("update", str(repo), "--dry-run").returncode, 0)


class TestDryRun(Base):
    def real_update_lines(self, repo, *extra):
        proc = run("update", str(repo), *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [line for line in proc.stdout.splitlines()[1:] if line.startswith("  ")]

    def test_the_dry_run_lists_what_the_real_update_then_does(self):
        dry_repo, real_repo = self.fresh("a"), self.fresh("b")
        dry = run("update", str(dry_repo), "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        lines = dry.stdout.splitlines()
        self.assertTrue(lines[0].startswith(f"would update {dry_repo} from workflow {UPGRADE_FROM} "
                                            f"to workflow {NEWEST_RELEASE}"))
        self.assertIn("(dry run: nothing written)", lines[0])
        would = lines[1:lines.index("left alone:")]
        real = self.real_update_lines(real_repo)
        self.assertEqual(would, [f"  {cli._would(line.strip())}" for line in real])
        self.assertIn("left alone:", lines)
        self.assertIn("Findings --", dry.stdout)

    # The oracle is literal: it must not be built from cli._would, the function under test.
    PAST_TO_WOULD = {"removed": "would remove", "added": "would add", "updated": "would update",
                     "fixed": "would fix", "created": "would create", "appended": "would append",
                     "replaced": "would replace", "prepended": "would prepend"}

    def literal_would(self, line: str) -> str:
        verb, _, rest = line.strip().partition(" ")
        return f"  {self.PAST_TO_WOULD[verb]} {rest}"

    def merge_fixture(self, name, claude_md):
        repo = self.fresh(name)
        (repo / ".gitignore").write_text("# mine\nbuild/\n")
        (repo / "CLAUDE.md").write_text(claude_md)
        self.commit(repo)
        return repo

    def test_merge_changes_read_like_the_real_update(self):
        managed = (self.pristine / "CLAUDE.md").read_text()
        self.assertIn("<!-- workflow-manager:end -->", managed)
        cases = {
            "replaced": managed.replace("workflow", "wurkflow", 1) + "\nmine\n",
            "prepended": "# my own claude file\n",
        }
        for expected, claude_md in cases.items():
            with self.subTest(expected):
                dry_repo = self.merge_fixture(f"d-{expected}", claude_md)
                real_repo = self.merge_fixture(f"r-{expected}", claude_md)
                dry = run("update", str(dry_repo), "--dry-run")
                self.assertEqual(dry.returncode, 0, dry.stderr)
                lines = dry.stdout.splitlines()
                would = lines[1:lines.index("left alone:")]
                real = self.real_update_lines(real_repo)
                self.assertIn(f"  {expected} managed CLAUDE.md section", real)
                self.assertIn("  appended .gitignore workflow entries", real)
                self.assertEqual(would, [self.literal_would(line) for line in real])
                self.assertIn("  would append .gitignore workflow entries", would)
                imperative = {"replaced": "replace", "prepended": "prepend"}[expected]
                self.assertIn(f"  would {imperative} managed CLAUDE.md section", would)

    def test_every_change_verb_has_a_dry_run_verb(self):
        # Every action a merge can report (read off its return statements) and every
        # verb plan_update puts at the head of a change line.
        import ast
        import inspect
        from workflow_manager import install
        emitted = {"added", "updated", "removed", "fixed", "created"}
        for func in (install.merge_gitignore, install.merge_claude_md):
            for node in ast.walk(ast.parse(inspect.getsource(func).lstrip())):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
                    emitted |= {c.value for c in ast.walk(node.value.elts[1])
                                if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        self.assertTrue({"appended", "replaced", "prepended"} <= emitted)
        for verb in emitted - {"unchanged"}:
            with self.subTest(verb):
                self.assertIn(verb, cli._DRY_VERBS)
        with self.assertRaises(ValueError):
            cli._would("frobnicated x")

    def test_a_dry_run_changes_nothing_a_real_update_would(self):
        repo = self.fresh()
        before = git(repo, "status", "--porcelain").stdout
        run("update", str(repo), "--dry-run")
        self.assertEqual(git(repo, "status", "--porcelain").stdout, before)

    def test_a_refusal_has_the_real_updates_text_and_exit(self):
        dry_repo, real_repo = self.fresh("a"), self.fresh("b")
        for repo in (dry_repo, real_repo):
            (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
            self.commit(repo)
        dry = run("update", str(dry_repo), "--dry-run")
        real = run("update", str(real_repo))
        self.assertEqual((dry.returncode, real.returncode), (2, 2))
        self.assertEqual(dry.stderr.replace(str(dry_repo), "R"), real.stderr.replace(str(real_repo), "R"))
        self.assertIn("re-run with --force", dry.stderr)
        self.assertIn("refused-drift", dry.stdout)

    def test_a_drifted_repository_with_an_unresolvable_installed_release_reports_both(self):
        # Local edits are detected from the install record, not the release package.
        cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, cache, True)
        shutil.copytree(source.cache_root() / NEWEST_RELEASE, cache / NEWEST_RELEASE, symlinks=True)
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        self.commit(repo)
        proc = run("--release-cache", str(cache), "--release-source", str(cache / "nowhere"),
                   "update", str(repo), "--dry-run")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("[blocked] refused-drift", proc.stdout)
        self.assertIn("[note] not-verified", proc.stdout)
        self.assertIn("still detected from the install record", proc.stdout)
        self.assertNotIn("was not checked", proc.stdout)

    def test_a_collision_is_refused_like_the_real_update(self):
        dry_repo, real_repo = self.fresh("a"), self.fresh("b")
        for repo in (dry_repo, real_repo):
            (repo / ".claude" / "commands" / "retire-legacy-work-item.md").write_text("mine\n")
            self.commit(repo)
        dry = run("update", str(dry_repo), "--dry-run")
        real = run("update", str(real_repo))
        self.assertEqual((dry.returncode, real.returncode), (2, 2), dry.stdout + dry.stderr)
        self.assertEqual(dry.stderr.replace(str(dry_repo), "R"), real.stderr.replace(str(real_repo), "R"))
        self.assertIn("refused-collision", dry.stdout)

    def test_force_lists_the_edits_it_would_discard(self):
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        self.commit(repo)
        dry = run("update", str(repo), "--dry-run", "--force")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertRegex(dry.stdout, r"would update scripts/workflow_state\.py +\(discards your local edit")

    def test_a_target_that_is_not_managed_is_refused(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, True)
        proc = run("update", str(empty), "--dry-run")
        self.assertEqual(proc.returncode, 2)

    def test_an_unpinned_release_exits_as_the_real_update_does(self):
        repo = self.fresh()
        dry = run("--release-version", "9.9.9", "update", str(repo), "--dry-run")
        real = run("--release-version", "9.9.9", "update", str(repo))
        self.assertEqual((dry.returncode, dry.stderr), (real.returncode, real.stderr))
        self.assertEqual(dry.returncode, 1)

    def test_help_says_where_the_commands_write(self):
        for argv in (["doctor", "--help"], ["update", "--help"]):
            out = run(*argv).stdout
            self.assertIn("never the repository", " ".join(out.split()))


# ---------------------------------------------------------------------------
# Printed commands, by family
# ---------------------------------------------------------------------------

LEGACY_STATE = {"schema_version": 1, "active_work_item_id": None, "work_items": {
    "old-item": {"work_item_type": "product", "phase": "LEGACY_READY",
                 "governing_workflow_version": "1", "parent_work_item_id": None}}}


def printed_commands(output: str) -> list[tuple[str, list[str]]]:
    """(family, argv) for every indented command line of a report."""
    found = []
    for line in output.splitlines():
        text = line.strip()
        if not line.startswith("      ") and not line.startswith("       "):
            continue
        if text.startswith("workflow-manager "):
            found.append((FAMILY_MANAGER, shlex.split(text)))
        elif text.startswith("git "):
            found.append((FAMILY_GIT, shlex.split(text)))
        elif text.startswith("/"):
            found.append((FAMILY_SLASH, shlex.split(text)))
    return found


class TestPrintedCommands(Base):
    def scenarios(self):
        clean = self.fresh("weird")
        dirty = self.fresh("weird")
        (dirty / "scratch.txt").write_text("x\n")
        drift = self.fresh("weird")
        (drift / "scripts" / "workflow_state.py").write_text("# edited\n")
        self.commit(drift)
        legacy = self.fresh("weird")
        (legacy / STATE).write_text(json.dumps(LEGACY_STATE))
        self.commit(legacy)
        return {"clean": clean, "dirty": dirty, "drift": drift, "legacy": legacy}

    def test_every_printed_command_is_valid_for_its_family(self):
        for name, repo in self.scenarios().items():
            for argv in (["doctor", str(repo)], ["update", str(repo), "--dry-run"]):
                proc = run(*argv)
                with self.subTest(scenario=name, command=argv[0]):
                    commands = printed_commands(proc.stdout + proc.stderr)
                    self.assertTrue(commands, proc.stdout)
                    for family, words in commands:
                        self.validate(family, words, repo)

    def validate(self, family, words, repo):
        if family == FAMILY_MANAGER:
            self.assertEqual(words[0], "workflow-manager")
            ns = cli.build_parser().parse_args(words[1:])
            self.assertEqual(ns.target, repo)
            self.assertIn(ns.command, ("update", "doctor"))
        elif family == FAMILY_GIT:
            self.assertEqual(words[:3], ["git", "-C", str(repo)])
            self.assertEqual(git(repo, *words[3:], check=False).returncode, 0, words)
            self.assertNotIn("clean -d", " ".join(words))      # the preview, never the destructive form
            if words[3] == "clean":
                self.assertIn("-n", words)
        else:
            name = words[0].lstrip("/")
            command_file = support.release(NEWEST_RELEASE).root / "payload" / ".claude" / "commands" / f"{name}.md"
            self.assertTrue(command_file.is_file(), command_file)
            text = command_file.read_text()
            self.assertIn("argument-hint:", text)
            self.assertIn("work-item-id", text)
            self.assertEqual(len(words), 2)

    def test_the_restore_line_is_withheld_for_a_dirty_tree(self):
        out = run("doctor", str(self.scenarios()["dirty"])).stdout
        self.assertNotIn("restore", out)
        self.assertIn("status --short", out)

    def test_the_restore_line_is_withheld_when_cleanliness_is_unknown(self):
        repo = self.fresh()
        git(repo, "config", "extensions.partialClone", "origin")
        out = run("doctor", str(repo)).stdout
        self.assertIn("incomplete-inspection", out)
        self.assertNotIn("restore", out)

    def test_the_restore_line_is_offered_for_a_clean_tree(self):
        out = run("doctor", str(self.fresh())).stdout
        self.assertIn("restore --source=HEAD --staged --worktree -- .", out)
        self.assertIn("clean -n -d", out)

    def test_retirement_is_offered_only_for_an_eligible_item(self):
        legacy = self.scenarios()["legacy"]
        self.assertIn("/retire-legacy-work-item old-item", run("doctor", str(legacy)).stdout)
        older = run("--release-version", "2.8.0", "doctor", str(legacy)).stdout
        self.assertNotIn("/retire-legacy-work-item old-item", older.replace("exists from", ""))

    def test_the_undo_command_restores_the_tree_a_real_update_changed(self):
        repo = self.fresh("weird")
        doctor = run("doctor", str(repo)).stdout
        restore = next(words for family, words in printed_commands(doctor)
                       if family == FAMILY_GIT and "restore" in words)
        before = git(repo, "rev-parse", "HEAD:").stdout
        self.assertEqual(run("update", str(repo)).returncode, 0)
        self.assertNotEqual(git(repo, "status", "--porcelain").stdout, "")
        done = subprocess.run(restore, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        # Tracked files are back; the files the update added remain untracked,
        # which is what the `clean -n -d` preview lists.
        self.assertEqual(git(repo, "diff", "HEAD", "--stat").stdout, "")
        self.assertEqual(git(repo, "rev-parse", "HEAD:").stdout, before)
        status = git(repo, "status", "--porcelain").stdout.splitlines()
        self.assertTrue(status)
        self.assertTrue(all(line.startswith("??") for line in status), status)
        preview = next(words for family, words in printed_commands(doctor)
                       if family == FAMILY_GIT and "clean" in words)
        listed = subprocess.run(preview, capture_output=True, text=True).stdout
        self.assertIn("Would remove", listed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
