#!/usr/bin/env python3
"""Operator UX, executed read-only and Workflow-data cases of plan section 4.

`test_operator_ux.py` holds the table-driven rows and the helpers; this module
holds the executed cases the plan makes the arbiter of P1: every printed
inspection command run in a hostile repository, the partial clone, the
same-text cases of (b), the mixed missing templates of (c), the malformed
files of (d), the paths of (e), and the Recovery cases of (i).

Every case runs the printed text as written and hashes the whole tree and
`.git` before and after.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from support import NEWEST_RELEASE, cli_env

import test_operator_ux as ux
from test_operator_ux import CONFIG, MILESTONE, RECORD, STATE, backticked, next_lines, run, tree_hash
from workflow_manager import advice
from workflow_manager.fixture import configure_throwaway_repo
from workflow_manager import compatibility as comp

PREFIX = "env GIT_NO_LAZY_FETCH=1 git "


def sh(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


def inspection_commands(output: str) -> list[str]:
    """Every backticked `env GIT_NO_LAZY_FETCH=1 git ...` command of `output`."""
    return [text for text in backticked(output) if text.startswith(PREFIX)]


def runnable(text: str) -> list[str]:
    """The argv of a printed command; a `REV` placeholder is a revision the
    operator picks, so the test picks HEAD."""
    return shlex.split(text.replace(" REV:", " HEAD:"))


def git_dir_hash(repo: Path) -> str:
    return tree_hash(repo / ".git")


class HostileRepoCase(ux.TargetCase):
    """A bootstrapped repository whose own config selects every helper a Git
    read could run: a clean filter, textconv, pager, fsmonitor, gpg."""

    def hostile(self, name="h") -> tuple[Path, Path]:
        repo = self.fresh(name)
        markers = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, markers, True)
        helper = lambda n, body: sh(markers.parent / f"{markers.name}-{n}.sh",
                                    f"echo {n} >> {markers}/{n}\n{body}")
        self.addCleanup(lambda: [p.unlink() for p in markers.parent.glob(f"{markers.name}-*.sh")])
        (repo / ".gitattributes").write_text("*.md filter=marker\n*.txt filter=marker\n"
                                             "*.json diff=tc\n")
        (repo / "notes.txt").write_text("notes\n")
        self.commit(repo, "hostile attributes")
        config = {
            "filter.marker.clean": helper("clean", "cat"),
            "filter.marker.smudge": helper("smudge", "cat"),
            "diff.tc.textconv": helper("textconv", 'cat "$1"'),
            "core.pager": helper("pager", "cat"),
            "core.fsmonitor": helper("fsmonitor", "exit 0"),
            "log.showSignature": "true",
            "gpg.program": helper("gpg", "exit 0"),
        }
        for key, value in config.items():
            ux.git(repo, "config", key, value)
        # Stale index stat data: the content is the same, the timestamp is not.
        os.utime(repo / "notes.txt", (1_000_000_000, 1_000_000_000))
        os.utime(repo / MILESTONE, (1_000_000_000, 1_000_000_000))
        return repo, markers

    def assertNoMarker(self, markers: Path):
        self.assertEqual(sorted(p.name for p in markers.iterdir()), [], "a helper ran")


class TestPrintedInspectionIsReadOnly(HostileRepoCase):
    """(g): the executed test is the arbiter of P1's read-only claim."""

    DELETIONS = (STATE, CONFIG, MILESTONE)

    def commands_for(self, repo: Path) -> list[str]:
        found = []
        for rel in self.DELETIONS:
            (repo / rel).unlink()
            for argv in (("verify",), ("doctor",)):
                found += inspection_commands(" ".join(next_lines_all(run(*argv, str(repo)))))
            (repo / rel).write_bytes((ux.Pristine.pristine() / rel).read_bytes())
        # T8: a record the Manager cannot read, with `*.json diff=tc` selected.
        (repo / RECORD).write_text("{bad")
        found += inspection_commands(" ".join(next_lines_all(run("verify", str(repo)))))
        (repo / RECORD).write_bytes((ux.Pristine.pristine() / RECORD).read_bytes())
        found.append(advice.git_command(repo, "rev-parse", "--git-dir").render())
        return found

    def test_the_hostile_repository_is_hostile_to_a_plain_status(self):
        repo, markers = self.hostile()
        copy = Path(tempfile.mkdtemp()) / "copy"
        self.addCleanup(shutil.rmtree, copy.parent, True)
        shutil.copytree(repo, copy, symlinks=True)
        ux.git(copy, "status", "--short")
        self.assertTrue((markers / "clean").exists(), "the reproducer: plain `git status` runs the filter")

    def test_the_manager_reads_run_no_helper_and_change_nothing(self):
        repo, markers = self.hostile()
        before = tree_hash(repo)
        for argv in (("verify",), ("status",), ("doctor",)):
            with self.subTest(command=argv[0]):
                proc = run(*argv, str(repo))
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertEqual(tree_hash(repo), before)
        self.assertNoMarker(markers)

    def test_every_printed_inspection_command_runs_no_helper_and_keeps_git_identical(self):
        repo, markers = self.hostile()
        commands = self.commands_for(repo)
        self.assertGreaterEqual(len(commands), 7, commands)
        self.assertTrue(any(" show " in c for c in commands) and any(" log " in c for c in commands))
        before, git_before = tree_hash(repo), git_dir_hash(repo)
        for text in dict.fromkeys(commands):
            with self.subTest(command=text):
                self.assertTrue(text.startswith(PREFIX), text)
                self.assertIn("--no-optional-locks", text)
                if " show " in text:
                    self.assertIn("--no-textconv", text)
                if " log " in text:
                    self.assertIn("--no-show-signature", text)
                proc = subprocess.run(runnable(text), capture_output=True, env=cli_env())
                self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(git_dir_hash(repo), git_before)
        self.assertEqual(tree_hash(repo), before)
        self.assertNoMarker(markers)

    def test_the_printed_show_prints_the_committed_bytes_not_a_textconv(self):
        repo, markers = self.hostile()
        (repo / STATE).unlink()
        text = next(c for c in inspection_commands(" ".join(next_lines_all(run("verify", str(repo)))))
                    if " show " in c)
        proc = subprocess.run(runnable(text), capture_output=True, env=cli_env())
        self.assertEqual(proc.stdout, (ux.Pristine.pristine() / STATE).read_bytes())
        self.assertNoMarker(markers)

    def test_recovery_under_a_true_predicate_prints_no_git_status(self):
        repo, markers = self.hostile()
        (repo / CONFIG).unlink()
        out = run("doctor", str(repo)).stdout
        recovery = out[out.index("\nRecovery"):]
        self.assertNotIn("status", recovery)
        self.assertNotIn("git -C", recovery)
        self.assertNoMarker(markers)


def next_lines_all(proc) -> list[str]:
    """The `next:` lines and the doctor `What to do` text of a finished run."""
    return [line.strip() for line in (proc.stdout + proc.stderr).splitlines()
            if line.startswith("next: ") or "What to do:" in line]


class TestPartialClone(ux.TargetCase):
    """(g) Round 13 R4-I-1: the absent promised object is never fetched by a
    printed command."""

    def clone(self) -> tuple[Path, Path]:
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        origin = work / "origin"
        shutil.copytree(ux.Pristine.pristine(), origin, symlinks=True)
        ux.git(origin, "config", "uploadpack.allowFilter", "true")
        target = work / "clone"
        proc = subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "clone", "-q",
                               "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                               "--no-checkout", "--filter=blob:none", f"file://{origin}", str(target)], capture_output=True, text=True,
                              env=cli_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        configure_throwaway_repo(target)
        ux.git(target, "checkout", "HEAD", "--", ".", f":!{STATE}")
        self.assertFalse((target / STATE).exists())
        return origin, target

    def packs(self, repo: Path) -> set[str]:
        return {p.name for p in (repo / ".git" / "objects" / "pack").glob("*")}

    def test_the_printed_show_of_an_absent_promised_object_fails_without_fetching(self):
        _, target = self.clone()
        text = next(c for c in inspection_commands(" ".join(next_lines_all(run("verify", str(target)))))
                    if " show " in c and STATE in c)
        before = git_dir_hash(target)
        proc = subprocess.run(runnable(text), capture_output=True, text=True, env=cli_env())
        self.assertEqual(proc.returncode, 128, proc.stderr)
        self.assertEqual(git_dir_hash(target), before)

    def test_the_same_command_without_the_prefix_fetches_on_a_copy(self):
        _, target = self.clone()
        text = next(c for c in inspection_commands(" ".join(next_lines_all(run("verify", str(target)))))
                    if " show " in c and STATE in c)
        copy = target.parent / "copy"
        shutil.copytree(target, copy, symlinks=True)
        packs = self.packs(copy)
        argv = shlex.split(text.replace(PREFIX, "git ").replace(str(target), str(copy)))
        proc = subprocess.run(argv, capture_output=True, env=cli_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotEqual(self.packs(copy), packs, "the reproducer: a pack file appears")

    def test_the_manager_reads_of_a_partial_clone_fetch_nothing(self):
        _, target = self.clone()
        before = git_dir_hash(target)
        for command in ("verify", "status", "doctor"):
            self.assertNotIn("Traceback", run(command, str(target)).stderr)
        self.assertEqual(git_dir_hash(target), before)


class TestEveryRowUnderATruePredicate(unittest.TestCase):
    """(j)(5): every `_TABLE` row reachable from `bootstrap` and `update`,
    rendered under a predicate-true context, prints no command that writes,
    no `--force` and no re-run."""

    #: A containment error is raised by `status`/`doctor` and by the cache
    #: checks of the read paths, never by `bootstrap` or `update`.
    UNREACHABLE = (comp.ContainmentError,)

    def errors(self, cls):
        from workflow_manager import install, installation
        from workflow_manager.install import Drift
        in_the_way = [Drift("a", "occupied", "a directory is in the way")]
        modified = [Drift("a", "modified")]
        row = advice._TABLE[cls]
        kinds = [None]
        if row.__closure__:
            rows = [c.cell_contents for c in row.__closure__ if isinstance(c.cell_contents, dict)]
            kinds = list(rows[0]) if rows else [None]
        if cls is install.CollisionError:
            return [cls("m", in_the_way), cls("m", modified)]
        if cls is install.DriftError:
            return [cls("m", modified)]
        if cls is installation.UnsupportedInstallationSchemaError:
            return [cls("m", 2), cls("m", None), cls("m", "1")]
        if cls is OSError:
            return [PermissionError("m"), OSError(28, "no space")]
        if kinds != [None]:
            return [cls("m", kind=kind) for kind in kinds]
        return [cls("m")]

    def context(self, command, withheld=True, **args):
        import argparse
        base = dict(command=command, target=Path("/t"), release_version=None,
                    release_source="/s", release_cache="/k", release_dir=None, manager_root=None,
                    profile="full", force=False, dry_run=False)
        base.update(args)
        extra = (dict(missing_templates=(CONFIG,), holds_data=True,
                      data_files=(comp.DataFile(CONFIG, "missing"),)) if withheld else {})
        return advice.Context(args=argparse.Namespace(**base), cache_dir="/k",
                              installed_version="2.9.1", **extra)

    def test_the_context_is_predicate_true(self):
        self.assertTrue(self.context("bootstrap").withheld)
        self.assertFalse(self.context("bootstrap", withheld=False).withheld)

    def test_no_row_prints_a_write_command_force_or_a_rerun(self):
        checked = 0
        for cls in advice._TABLE:
            if cls in self.UNREACHABLE:
                continue
            for command in ("bootstrap", "update"):
                context = self.context(command)
                for error in self.errors(cls):
                    with self.subTest(row=cls.__name__, command=command,
                                      kind=getattr(error, "kind", None)):
                        step = advice.next_step(error, context)
                        checked += 1
                        if step is None:
                            continue
                        for text in backticked(step):
                            words = shlex.split(text)
                            if words[:1] == ["workflow-manager"]:
                                self.assertFalse(
                                    any(w in ("update", "bootstrap") for w in words)
                                    and "--dry-run" not in words, text)
                        self.assertNotIn("--force", step)
                        self.assertNotIn("git restore", step)
                        self.assertNotIn("git checkout", step)
                        self.assertNotRegex(step.replace("do not run it again", ""),
                                            r"\bagain\b|same command")
        self.assertGreater(checked, 40)

    def test_the_walk_is_not_vacuous_a_predicate_false_context_prints_the_command(self):
        from workflow_manager.install import Drift, DriftError
        error = DriftError("m", [Drift("a", "modified")])
        self.assertIn("--force", advice.next_step(error, self.context("update", withheld=False)))
        self.assertNotIn("--force", advice.next_step(error, self.context("update")))


# ---------------------------------------------------------------------------
# Scenarios: one function per damaged repository, shared by the cases and the
# no-traceback sweep.
# ---------------------------------------------------------------------------

TEMPLATES = (STATE, CONFIG, MILESTONE)
DECLARATIONS = "docs/ai-workflow/registry/item-a-artifacts.json"
MALFORMED = "{ not json\n"
WITHHELD_LINE = ("No command that writes the repository is offered: the Workflow data problem "
                 "named above needs your decision first")
COMMIT_ARGS = ("-c", "user.email=t@example.invalid", "-c", "user.name=T")


def pristine_bytes(rel: str) -> bytes:
    return (ux.Pristine.pristine() / rel).read_bytes()


def commit(repo: Path, message="work") -> None:
    ux.git(repo, "add", "-A")
    ux.git(repo, *COMMIT_ARGS, "commit", "-q", "-m", message)


def normalized(text: str, repo: Path) -> str:
    return text.replace(str(repo), "R")


def next_text(proc, repo: Path) -> str:
    return normalized("\n".join(next_lines(proc.stdout + proc.stderr)), repo)


def recovery_of(out: str) -> str:
    return out[out.index("\nRecovery"):]


def add_item_with_declarations(repo: Path, declarations: str | None = "{bad") -> None:
    state = json.loads((repo / STATE).read_text())
    state["work_items"]["item-a"] = {"phase": "IMPLEMENTING", "governing_workflow_version": "2.2",
                                     "work_item_type": "process", "parent_work_item_id": None}
    (repo / STATE).write_text(json.dumps(state, indent=2) + "\n")
    if declarations is not None:
        (repo / DECLARATIONS).parent.mkdir(parents=True, exist_ok=True)
        (repo / DECLARATIONS).write_text(declarations)
    commit(repo, "item")


def make_staged_deletion(repo):
    ux.git(repo, "rm", "-q", CONFIG)


def make_modified_staged_then_deleted(repo):
    (repo / CONFIG).write_text("staged-work\n")
    ux.git(repo, "add", CONFIG)
    (repo / CONFIG).unlink()


def make_staged_never_committed(repo):
    ux.git(repo, "rm", "-q", CONFIG)
    ux.git(repo, *COMMIT_ARGS, "commit", "-q", "-m", "rm")
    (repo / CONFIG).write_text("x\n")
    ux.git(repo, "add", CONFIG)
    (repo / CONFIG).unlink()


def make_head_and_index_lack_it(repo):
    ux.git(repo, "rm", "-q", CONFIG)
    ux.git(repo, *COMMIT_ARGS, "commit", "-q", "-m", "rm")


def make_broken_head(repo):
    ux.git(repo, "branch", "other")
    (repo / ".git" / "refs" / "heads" / "main").write_text("1" * 40 + "\n")
    (repo / CONFIG).unlink()


def make_plain_deletion(repo):
    (repo / CONFIG).unlink()


B_SCENARIOS = {
    "staged deletion": make_staged_deletion,
    "modified, staged, then deleted": make_modified_staged_then_deleted,
    "staged, never committed, then deleted": make_staged_never_committed,
    "HEAD and index lack the path": make_head_and_index_lack_it,
    "broken HEAD, data on another ref": make_broken_head,
    "plain deletion": make_plain_deletion,
}


class DataCase(ux.TargetCase):
    def noTraceback(self, proc):
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        return proc

    def go(self, *argv, env=None):
        return self.noTraceback(run(*argv, env=env))

    def run_printed(self, text: str, cwd=None, **kw):
        return subprocess.run(runnable(text), capture_output=True, cwd=cwd, env=cli_env(), **kw)

    def assertNoWrite(self, text: str):
        for word in ("git restore", "git checkout", "git stash", "git reset", "git rm", "--force"):
            self.assertNotIn(word, text)
        for command in backticked(text):
            words = shlex.split(command)
            if words[:1] == ["workflow-manager"] and "--dry-run" not in words:
                self.assertFalse({"update", "bootstrap"} & set(words), command)
        for word in ("restore", "checkout --", "stash", "reset"):
            self.assertNotRegex(text, rf"\b{word}\b")


class TestSameTextForEveryGitState(DataCase):
    """(b): one missing template, whatever Git holds, prints the same text."""

    def baseline(self):
        repo = self.fresh("base")
        make_plain_deletion(repo)
        return next_text(self.go("verify", str(repo)), repo)

    def test_every_git_state_prints_the_baseline_text(self):
        base = self.baseline()
        self.assertIn("repair-workflow-data-by-hand", base)
        self.assertNoWrite(base)
        for name, make in B_SCENARIOS.items():
            with self.subTest(name):
                if name == "unreadable state":
                    needs_permissions(self)
                repo = self.fresh("r")
                make(repo)
                proc = self.go("verify", str(repo))
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertEqual(next_text(proc, repo), base)

    def test_an_unborn_head_prints_the_baseline_text(self):
        from workflow_manager.fixture import init_git_repo
        from workflow_manager.install import bootstrap
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        repo = work / "r"
        init_git_repo(repo)
        bootstrap(repo, support.release(NEWEST_RELEASE), now="2026-01-01T00:00:00Z")
        (repo / CONFIG).unlink()
        self.assertNotEqual(ux.git(repo, "rev-parse", "--verify", "-q", "HEAD").returncode, 0)
        proc = self.go("verify", str(repo))
        self.assertEqual(next_text(proc, repo), self.baseline())
        before = tree_hash(repo)
        for text in inspection_commands(" ".join(next_lines(proc.stdout))):
            self.run_printed(text)             # `show HEAD:` fails: nothing to read, nothing written
        self.assertEqual(tree_hash(repo), before)

    def test_git_that_refuses_prints_the_baseline_text(self):
        base = self.baseline()
        repo = self.fresh("r")
        make_plain_deletion(repo)
        proc = self.go("verify", str(repo), env=cli_env(PATH=""))
        self.assertEqual(next_text(proc, repo), base)
        with mock.patch.object(comp, "run_git", return_value=comp.GitResult(128)):
            code, out, err = ux.main_in_process("verify", str(repo))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(normalized("\n".join(next_lines(out + err)), repo), base)

    def test_the_printed_commands_write_nothing_and_still_reach_the_data(self):
        for name, make in B_SCENARIOS.items():
            with self.subTest(name):
                if name == "unreadable state":
                    needs_permissions(self)
                repo = self.fresh("r")
                make(repo)
                before = tree_hash(repo)
                commands = inspection_commands(" ".join(next_lines(self.go("verify", str(repo)).stdout)))
                self.assertEqual(len(commands), 2, commands)
                for text in commands:
                    proc = self.run_printed(text)
                    if name == "broken HEAD, data on another ref":
                        self.assertNotEqual(proc.returncode, 0)     # HEAD names nothing
                        other = text.replace(" HEAD:", " other:").replace(" log ", " log other ")
                        other = self.run_printed(other)
                        self.assertEqual(other.returncode, 0, other.stderr)
                        if " show " in text:
                            self.assertEqual(other.stdout, pristine_bytes(CONFIG))
                    elif name == "staged deletion" or name == "plain deletion":
                        self.assertEqual(proc.returncode, 0, proc.stderr)
                        if " show " in text:
                            self.assertEqual(proc.stdout, pristine_bytes(CONFIG))
                self.assertEqual(tree_hash(repo), before)


class TestMixedMissingTemplates(DataCase):
    """(c): state, config and ACTIVE_MILESTONE.md missing together."""

    HOW = ("never tracked", "in the index", "only on another ref")

    def make(self, repo: Path, hows: tuple[str, str, str]):
        """Each template is, per `hows`, tracked only in the index and the
        history of this branch ("in the index"), absent from every ref
        ("never tracked"), or present only on the branch `other`."""
        never = [rel for rel, how in zip(TEMPLATES, hows) if how == "never tracked"]
        elsewhere = [rel for rel, how in zip(TEMPLATES, hows) if how == "only on another ref"]
        ux.git(repo, "branch", "other")
        if never:
            ux.git(repo, "checkout", "-q", "other")
            ux.git(repo, "rm", "-q", "--cached", *never)
            ux.git(repo, *COMMIT_ARGS, "commit", "-q", "--amend", "--no-edit")
            ux.git(repo, "checkout", "-q", "main")
        if never or elsewhere:
            ux.git(repo, "rm", "-q", "--cached", *never, *elsewhere)
            ux.git(repo, *COMMIT_ARGS, "commit", "-q", "--amend", "--no-edit")
        for rel in TEMPLATES:
            (repo / rel).unlink()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")

    def combos(self):
        import itertools
        return list(itertools.product(self.HOW, repeat=3))

    def test_no_update_command_is_printed_for_any_combination(self):
        for hows in self.combos():
            with self.subTest(hows=hows):
                repo = self.fresh("r")
                self.make(repo, hows)
                for command in ("verify", "status"):
                    proc = self.go(command, str(repo))
                    out = proc.stdout + proc.stderr
                    self.assertNotRegex(out, r"workflow-manager( --\S+ \S+)* (update|bootstrap)\b(?! .*--dry-run)")
                    self.assertNotIn("--force", out)
                self.assertTrue(all(not (repo / rel).exists() for rel in TEMPLATES))

    def test_doctor_withholds_every_writing_command(self):
        for hows in (self.combos()[0], self.combos()[-1], ("in the index",) * 3):
            with self.subTest(hows=hows):
                repo = self.fresh("r")
                self.make(repo, hows)
                out = self.go("doctor", str(repo)).stdout
                recovery = recovery_of(out)
                self.assertIn(WITHHELD_LINE, recovery)
                for word in ("workflow-manager update", "--force", "bootstrap", "git restore",
                             "git clean"):
                    self.assertNotIn(word, recovery)

    def test_update_force_text_prints_the_data_step_instead_of_its_command(self):
        repo = self.fresh("r")
        self.make(repo, ("in the index",) * 3)
        proc = self.go("update", str(repo))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        step = next_lines(proc.stderr)[0]
        self.assertNoWrite(step)
        self.assertIn("repair-workflow-data-by-hand", step)

    def test_update_anyway_would_recreate_all_three_which_is_why_it_is_withheld(self):
        repo = self.fresh("r")
        self.make(repo, ("in the index",) * 3)
        copy = repo.parent / "copy"
        shutil.copytree(repo, copy, symlinks=True)
        proc = run("update", "--force", str(copy))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for rel in TEMPLATES:
            self.assertTrue((copy / rel).exists(), rel)
        for rel in TEMPLATES:
            self.assertFalse((repo / rel).exists(), "the original stays untouched")

    def test_no_template_missing_keeps_the_ordinary_update_command(self):
        repo = self.fresh("r")
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        proc = self.go("verify", str(repo))
        commands = ux.manager_commands(proc.stdout)
        plain = [c for c in commands if "update" in c and "--dry-run" not in c]
        self.assertEqual(len(plain), 1, proc.stdout)
        self.assertEqual(plain[0][-1], str(repo))
        self.assertTrue(ux.parses(plain[0]))


def what_to_do(out: str) -> str:
    """The `What to do:` lines of a doctor report."""
    return "\n".join(line for line in out.splitlines() if "What to do:" in line)


def needs_permissions(case: unittest.TestCase) -> None:
    if os.geteuid() == 0:
        case.skipTest("root ignores permissions")


class TestMalformedDataFiles(DataCase):
    """(d): an existing malformed state, config or declarations file."""

    FILES = {"state": STATE, "config": CONFIG, "declarations": DECLARATIONS}
    EDITS = ("uncommitted", "committed", "staged")

    def build(self, rel: str, edit: str, name="r") -> Path:
        repo = self.fresh(name)
        if rel == DECLARATIONS:
            add_item_with_declarations(repo, "{}")
        if edit == "committed":
            (repo / rel).write_text(MALFORMED)
            commit(repo, "malformed")
        elif edit == "uncommitted":
            (repo / rel).write_text(MALFORMED)
        else:                                  # staged, and edited further in the tree
            (repo / rel).write_text(MALFORMED)
            ux.git(repo, "add", rel)
            (repo / rel).write_text(MALFORMED + "more\n")
        (repo / rel).chmod(0o640)
        return repo

    def test_the_printed_cp_keeps_bytes_and_mode_and_update_leaves_the_file_alone(self):
        for label, rel in self.FILES.items():
            for edit in self.EDITS:
                with self.subTest(file=label, edit=edit):
                    repo = self.build(rel, edit)
                    original = (repo / rel).read_bytes()
                    doctor = self.go("doctor", str(repo))
                    steps = what_to_do(doctor.stdout)
                    copy = f"cp -p -- {repo}/{rel} {repo}/{rel}.bak"
                    self.assertIn(f"`{copy}`", steps)
                    self.assertNoWrite(steps)
                    for word in ("restore", "checkout", "bootstrap"):
                        self.assertNotIn(word, steps)
                    proc = self.run_printed(copy)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    backup = repo / f"{rel}.bak"
                    self.assertEqual(backup.read_bytes(), original)
                    self.assertEqual(stat.S_IMODE(backup.stat().st_mode),
                                     stat.S_IMODE((repo / rel).stat().st_mode))
                    backup.unlink()
                    update = self.go("update", str(repo))
                    self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
                    self.assertEqual((repo / rel).read_bytes(), original)

    def test_an_existing_backup_moves_the_printed_destination_and_survives(self):
        repo = self.build(STATE, "uncommitted")
        (repo / f"{STATE}.bak").write_text("earlier copy\n")
        steps = what_to_do(self.go("doctor", str(repo)).stdout)
        copy = f"cp -p -- {repo}/{STATE} {repo}/{STATE}.bak.1"
        self.assertIn(f"`{copy}`", steps)
        self.assertEqual(self.run_printed(copy).returncode, 0)
        self.assertEqual((repo / f"{STATE}.bak").read_text(), "earlier copy\n")
        self.assertEqual((repo / f"{STATE}.bak.1").read_bytes(), (repo / STATE).read_bytes())


class TestUnreadableAndAwkwardPaths(DataCase):
    """(e): mode-000 files, and targets with spaces, quotes and a leading hyphen."""

    def test_an_unreadable_state_file_says_check_permissions_and_prints_ls(self):
        needs_permissions(self)
        for rel in (STATE, DECLARATIONS):
            with self.subTest(rel):
                repo = self.fresh("r")
                if rel == DECLARATIONS:
                    add_item_with_declarations(repo, "{}")
                (repo / rel).chmod(0)
                self.addCleanup((repo / rel).chmod, 0o644)
                steps = what_to_do(self.go("doctor", str(repo)).stdout)
                self.assertIn("check the permissions and owner of", steps)
                ls = f"ls -ld -- {repo}/{rel}"
                self.assertIn(f"`{ls}`", steps)
                for word in ("chmod", "cp -p", "restore", "checkout"):
                    self.assertNotIn(word, steps)
                before = tree_hash(repo, skip=(rel,))     # the file itself cannot be read
                proc = self.run_printed(ls)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                for text in inspection_commands(steps):
                    self.assertEqual(self.run_printed(text).returncode, 0)
                self.assertEqual(tree_hash(repo, skip=(rel,)), before)

    def awkward(self, name: str, base: str | None = None) -> tuple[Path, Path]:
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        repo = work / name
        shutil.copytree(ux.Pristine.pristine(), repo, symlinks=True)
        (repo / STATE).write_text(MALFORMED)
        return work, repo

    def check_printed_commands_run_as_written(self, doctor_argv, cwd, repo, shown):
        proc = ux.run_in(cwd, *doctor_argv)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        steps = what_to_do(proc.stdout)
        original = (repo / STATE).read_bytes()
        git_before = git_dir_hash(repo)
        copy = [t for t in backticked(steps) if t.startswith("cp -p -- ")]
        self.assertEqual(len(copy), 1, steps)
        self.assertEqual(shlex.split(copy[0]), ["cp", "-p", "--", f"{shown}/{STATE}",
                                                f"{shown}/{STATE}.bak"])
        for text in inspection_commands(steps):
            proc = subprocess.run(shlex.split(text), cwd=cwd, capture_output=True, env=cli_env())
            self.assertEqual(proc.returncode, 0, (text, proc.stderr))
            if " show " in text:
                self.assertEqual(proc.stdout, pristine_bytes(STATE))
        self.assertEqual(git_dir_hash(repo), git_before)
        proc = subprocess.run(shlex.split(copy[0]), cwd=cwd, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((repo / f"{STATE}.bak").read_bytes(), original)

    def test_a_target_with_spaces_and_quotes(self):
        work, repo = self.awkward("my repo 'q' $x;y")
        self.check_printed_commands_run_as_written(("doctor", str(repo)), work, repo, repo)

    def test_a_leading_hyphen_target(self):
        work, repo = self.awkward("-repo")
        self.check_printed_commands_run_as_written(("doctor", "--", "-repo"), work, repo, "-repo")

    def test_a_leading_hyphen_target_with_a_missing_template(self):
        work, repo = self.awkward("-repo")
        (repo / STATE).write_bytes(pristine_bytes(STATE))
        (repo / CONFIG).unlink()
        proc = ux.run_in(work, "verify", "--", "-repo")
        step = next_lines(proc.stdout)[0]
        for text in inspection_commands(step):
            self.assertEqual(subprocess.run(shlex.split(text), cwd=work, capture_output=True,
                                            env=cli_env()).returncode, 0, text)


class TestRecoveryWithholds(DataCase):
    """(i): each case run through `doctor`; Recovery holds the stated line and
    none of the writing commands."""

    WRITING = ("workflow-manager update", "workflow-manager --release-version", "--force",
               "bootstrap", "git restore", "git clean")

    def committed_malformed_state(self, repo):
        (repo / STATE).write_text(MALFORMED)
        commit(repo, "malformed state")

    def hidden_edits(self, repo):
        self.committed_malformed_state(repo)
        ux.git(repo, "update-index", "--assume-unchanged", STATE)
        (repo / STATE).write_text("{ other malformed edits\n")

    def declarations(self, repo):
        add_item_with_declarations(repo, "{bad")

    def schema(self, version):
        def make(repo):
            state = json.loads((repo / STATE).read_text())
            state["schema_version"] = version
            (repo / STATE).write_text(json.dumps(state) + "\n")
            commit(repo, "schema")
        return make

    def no_milestone(self, repo):
        (repo / MILESTONE).unlink()

    def unreadable(self, repo):
        needs_permissions(self)
        (repo / STATE).chmod(0)
        self.addCleanup((repo / STATE).chmod, 0o644)

    def cases(self):
        return {
            "(1) malformed declarations": self.declarations,
            "(2) committed malformed state": self.committed_malformed_state,
            "(3) hidden by assume-unchanged": self.hidden_edits,
            "(4) unknown schema_version": self.schema(99),
            "(4) non-integer schema_version": self.schema("x"),
            "(5) missing ACTIVE_MILESTONE.md": self.no_milestone,
            "(6) unreadable state": self.unreadable,
        }

    def check(self, repo: Path, *, drift=False) -> str:
        proc = self.go("doctor", str(repo))
        recovery = recovery_of(proc.stdout)
        self.assertIn(WITHHELD_LINE, recovery)
        for word in self.WRITING:
            self.assertNotIn(word, recovery)
        # One predicate, one answer: the finding details withhold too.
        self.assertNoWrite(what_to_do(proc.stdout).replace("--dry-run", ""))
        return proc.stdout

    def test_each_case_withholds_every_writing_command(self):
        for name, make in self.cases().items():
            with self.subTest(name):
                if name == "unreadable state":
                    needs_permissions(self)
                repo = self.fresh("r")
                make(repo)
                self.check(repo)

    def test_a_refused_drift_together_with_each_case_withholds_the_force_step_too(self):
        for name, make in self.cases().items():
            with self.subTest(name):
                if name == "unreadable state":
                    needs_permissions(self)
                repo = self.fresh("r")
                make(repo)
                (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
                out = self.check(repo)
                self.assertIn("refused-drift", out)

    def test_hidden_edits_survive_and_the_baseline_restore_would_have_discarded_them(self):
        repo = self.fresh("r")
        self.hidden_edits(repo)
        self.assertEqual(ux.git(repo, "status", "--short").stdout, "")     # the tree looks clean
        copy = repo.parent / "copy"
        shutil.copytree(repo, copy, symlinks=True)
        restore = ux.git(copy, "restore", "--source=HEAD", "--staged", "--worktree", "--", ".")
        self.assertEqual(restore.returncode, 0, restore.stderr)
        self.assertEqual((copy / STATE).read_text(), MALFORMED, "the reproducer: edits discarded")
        before = (repo / STATE).read_bytes()
        out = self.check(repo)
        self.assertEqual((repo / STATE).read_bytes(), before)
        self.assertNotIn("restore", out.replace("repair-workflow-data-by-hand", ""))

    def test_no_such_problem_keeps_the_baseline_recovery_by_value(self):
        repo = self.fresh("r")
        out = self.go("doctor", str(repo)).stdout
        recovery = recovery_of(out)
        self.assertNotIn(WITHHELD_LINE, recovery)
        self.assertIn("restore --source=HEAD --staged --worktree -- .", recovery)
        self.assertRegex(recovery, r"workflow-manager( --release-version \S+)? update ")
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        commit(repo, "drift")
        drift = recovery_of(self.go("doctor", str(repo)).stdout)
        self.assertIn("--force", drift)


class TestSweepForCrashes(DataCase):
    # Not named `...Traceback...`: the class name is in the temporary path.
    """Every reachable case above, through every read command and the dry run."""

    def test_no_case_prints_a_traceback(self):
        cases = dict(B_SCENARIOS)
        cases["malformed state"] = lambda r: (r / STATE).write_text(MALFORMED)
        cases["malformed config, committed"] = lambda r: (
            (r / CONFIG).write_text(MALFORMED), commit(r, "bad"))
        cases["malformed declarations"] = lambda r: add_item_with_declarations(r, "{bad")
        cases["unreadable state"] = lambda r: (r / STATE).chmod(0)
        cases["staged malformed state"] = lambda r: (
            (r / STATE).write_text(MALFORMED), ux.git(r, "add", STATE))
        cases["hidden by assume-unchanged"] = lambda r: TestRecoveryWithholds().hidden_edits(r)
        cases["mixed missing"] = lambda r: TestMixedMissingTemplates().make(r, ("in the index",) * 3)
        for name, make in cases.items():
            with self.subTest(name):
                if name == "unreadable state":
                    needs_permissions(self)
                repo = self.fresh("r")
                make(repo)
                self.addCleanup(lambda p=repo / STATE: p.exists() and p.chmod(0o644))
                for argv in (("verify",), ("status",), ("doctor",), ("update", "--dry-run"),
                             ("update",), ("bootstrap",)):
                    proc = run(*argv, str(repo))
                    self.assertNotIn("Traceback", proc.stdout + proc.stderr, (name, argv))
                    self.assertIn(proc.returncode, (0, 1, 2), (name, argv))


class TestDamagedRegistryAndMapping(DataCase):
    """Implementation review round 2, I2: a registry or mapping file that exists and
    cannot be read is an incomplete inspection, so no printed text offers a command
    that writes Workflow data or `git status`."""

    REGISTRY = "docs/ai-workflow/registry/item-a-registry.json"
    MAPPING = "docs/ai-workflow/requirements/item-a-mapping.json"
    VALID = json.dumps({"plan_stage": {"protected_prefixes": ["docs/ai-workflow/"]},
                        "implementation_stage": {"protected_prefixes": ["scripts/"]}})

    def damaged(self, rel, content):
        repo = self.fresh()
        add_item_with_declarations(repo, self.VALID)
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(content)
        commit(repo, "damaged")
        return repo

    def test_each_damage_is_an_incomplete_inspection_that_withholds_writes(self):
        cases = (("registry", self.REGISTRY, MALFORMED), ("registry list", self.REGISTRY, "[]"),
                 ("registry checkpoints", self.REGISTRY, '{"checkpoints": 3}'),
                 ("registry entries", self.REGISTRY, '{"checkpoints": [1]}'),
                 ("mapping", self.MAPPING, MALFORMED), ("mapping list", self.MAPPING, "[]"))
        for name, rel, content in cases:
            with self.subTest(name):
                repo = self.damaged(rel, content)
                proc = run("doctor", str(repo))
                out = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, 1, out)
                self.assertIn("incomplete-inspection", out)
                self.assertIn(rel, out)
                self.assertNotIn("Traceback", out)
                for text in (recovery_of(out), next_text(run("bootstrap", str(repo)), repo)):
                    self.assertNoWritingCommand(text)
                    self.assertNotIn("git restore", text)
                    self.assertNotIn(f"{repo} status", text)

    def test_a_readable_registry_and_mapping_cost_nothing(self):
        repo = self.damaged(self.REGISTRY, '{"checkpoints": [{"id": "CP1"}]}')
        (repo / self.MAPPING).parent.mkdir(parents=True, exist_ok=True)
        (repo / self.MAPPING).write_text("{}")
        commit(repo, "mapping")
        self.assertNotIn(self.REGISTRY, run("doctor", str(repo)).stdout)

    def test_an_absent_registry_and_mapping_are_not_damage(self):
        repo = self.fresh()
        add_item_with_declarations(repo, self.VALID)
        for rel in (self.REGISTRY, self.MAPPING):
            self.assertNotIn(rel, run("doctor", str(repo)).stdout)

    def test_a_terminal_items_damaged_registry_is_not_read(self):
        repo = self.fresh()
        add_item_with_declarations(repo, self.VALID)
        state = json.loads((repo / STATE).read_text())
        state["work_items"]["item-a"]["phase"] = "MILESTONE_COMPLETE"
        (repo / STATE).write_text(json.dumps(state, indent=2) + "\n")
        (repo / self.REGISTRY).parent.mkdir(parents=True, exist_ok=True)
        (repo / self.REGISTRY).write_text(MALFORMED)
        commit(repo, "done")
        self.assertNotIn(self.REGISTRY, run("doctor", str(repo)).stdout)

    def test_i6_a_terminal_items_registry_with_odd_checkpoints_does_not_crash(self):
        for value in ("null", "3", "true", '"x"', "{}"):
            with self.subTest(checkpoints=value):
                repo = self.fresh()
                add_item_with_declarations(repo, self.VALID)
                state = json.loads((repo / STATE).read_text())
                state["work_items"]["item-a"]["phase"] = "MILESTONE_COMPLETE"
                (repo / STATE).write_text(json.dumps(state, indent=2) + "\n")
                (repo / self.REGISTRY).parent.mkdir(parents=True, exist_ok=True)
                (repo / self.REGISTRY).write_text('{"checkpoints": %s}' % value)
                commit(repo, "done")
                for argv in (("doctor", str(repo)), ("update", "--dry-run", str(repo))):
                    out = run(*argv)
                    text = out.stdout + out.stderr
                    self.assertNotIn("Traceback", text, argv)
                    self.assertNotIn(self.REGISTRY, text, argv)


class TestPrintedCommandsParse(ux.TargetCase):
    """Implementation review round 2, I1, I3 and I4."""

    def test_i1_a_global_option_value_with_a_leading_hyphen_is_printed_as_one_argument(self):
        command = comp.manager_command("verify", withheld=False, target="/t",
                                       options=(("--release-dir", "-release"),),
                                       release_version="-v")
        argv = shlex.split(command.render())
        self.assertIn("--release-dir=-release", argv)
        self.assertIn("--release-version=-v", argv)
        self.assertTrue(ux.parses(argv), argv)

    def test_i1_the_already_managed_refusal_prints_commands_that_parse(self):
        repo = self.fresh()
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        shutil.copytree(support.release(NEWEST_RELEASE).root, Path(work.name) / "-release")
        proc = ux.run_in(work.name, "--release-dir=-release", "bootstrap", str(repo))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        commands = ux.manager_commands(proc.stderr)
        self.assertTrue(commands)
        for argv in commands:
            self.assertIn("--release-dir=-release", argv)
            self.assertTrue(ux.parses(argv), argv)

    def release_dir(self, version):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        directory = Path(work.name) / "release"
        shutil.copytree(support.release(NEWEST_RELEASE).root, directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["workflow_version"] = version
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return directory

    def test_i3_repair_advice_for_a_scalar_release_version_is_executable(self):
        for version in (123, True, "", None):
            with self.subTest(version=version):
                directory = self.release_dir(version)
                repo = self.empty()
                self.assertEqual(run("--release-dir", str(directory), "bootstrap", str(repo)).returncode, 0)
                (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
                proc = run("--release-dir", str(directory), "verify", str(repo))
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                commands = ux.manager_commands(proc.stdout)
                self.assertTrue(commands)
                for argv in commands:
                    self.assertNotIn("--release-version", argv)
                    self.assertIn("--release-dir", argv)
                    self.assertTrue(ux.parses(argv), argv)
                update = next(a for a in commands if "update" in a and "--dry-run" not in a)
                again = run(*update[1:])
                self.assertNotIn("holds release", again.stdout + again.stderr)
                self.assertNotIn("Traceback", again.stdout + again.stderr)
                self.assertEqual(again.returncode, 2, again.stdout + again.stderr)   # drift, not a crash
                self.assertIn("modified: scripts/workflow_state.py", again.stdout + again.stderr)
                at = update.index("update") + 1
                forced = run(*update[1:at], "--force", *update[at:])
                self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)

    def test_i3_verify_without_release_dir_after_a_scalar_install_asks_for_one(self):
        for version in (123, "", None):
            with self.subTest(version=version):
                directory = self.release_dir(version)
                repo = self.empty()
                self.assertEqual(run("--release-dir", str(directory), "bootstrap", str(repo)).returncode, 0)
                (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
                proc = run("verify", str(repo))
                out = proc.stdout + proc.stderr
                self.assertNotIn("Traceback", out)
                self.assertNotIn("leave out", out, out)
                self.assertIn("--release-dir DIR", out)
                if version is None:     # only `null` resolves to the newest pin, so it compares
                    self.assertIn("a release directory holding None", out, out)
                again = run("--release-dir", str(directory), "verify", str(repo))
                commands = ux.manager_commands(again.stdout)
                update = next(a for a in commands if "update" in a and "--dry-run" not in a)
                at = update.index("update") + 1
                forced = run(*update[1:at], "--force", *update[at:])
                self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)

    def test_i3_a_scalar_version_without_its_release_dir_asks_for_one(self):
        context = advice.Context(
            args=argparse.Namespace(command="verify", target=Path("/t"), release_version=None,
                                    release_source=None, release_cache=None, release_dir=None,
                                    profile=None),
            installed_version=123)
        step = advice.problem_step(context, ["modified: scripts/x.py"])
        self.assertIn("a release directory holding 123 is needed", step)
        self.assertNotIn("--release-version", step)

    def test_i4_an_unhashable_installed_version_is_a_damaged_record_not_a_traceback(self):
        for value in ("[]", "{}", "[1]"):
            with self.subTest(value=value):
                repo = self.fresh()
                text = (repo / RECORD).read_text()
                (repo / RECORD).write_text(
                    text.replace(f'"workflow_version": "{NEWEST_RELEASE}"',
                                 f'"workflow_version": {value}'))
                for argv in (("doctor",), ("verify",), ("status",), ("update", "--dry-run"),
                             ("update",)):
                    proc = run(*argv, str(repo))
                    out = proc.stdout + proc.stderr
                    self.assertNotIn("Traceback", out, argv)
                    self.assertEqual(proc.returncode, 2, (argv, out))
                    self.assertIn("is unreadable", out)
                    self.assertTrue(next_lines(out), argv)

    def test_i4_a_scalar_version_in_the_record_is_still_accepted(self):
        from workflow_manager.installation import Installation
        data = json.loads((self.fresh() / RECORD).read_text())
        for version in (123, True, None, "x"):
            data["workflow_version"] = version
            self.assertEqual(Installation.from_dict(data).workflow_version, version)


if __name__ == "__main__":
    unittest.main(verbosity=2)
