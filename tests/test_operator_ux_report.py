#!/usr/bin/env python3
"""Operator UX, report findings and `status`: the next step of each finding,
the Recovery section's withheld writes, and the work-in-flight block with its
destination containment (plan 3.4, 3.5, 3.5a).

Helpers come from `test_operator_ux`; this module holds only the cases.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from support import NEWEST_RELEASE, cli_env

import test_operator_ux as ux
from test_operator_ux import CONFIG, next_lines, run, tree_hash
from test_compatibility import fake_plan
from workflow_manager import compatibility as comp
from workflow_manager.install import CollisionError, Drift
from workflow_manager.installation import Installation

STATE = "docs/ai-workflow/WORKFLOW_STATE.json"
MILESTONE = "docs/ACTIVE_MILESTONE.md"


def write_state(repo: Path, work_items: dict, **extra) -> None:
    state = {"schema_version": 1, "active_work_item_id": None, "work_items": work_items}
    state.update(extra)
    (repo / STATE).write_text(json.dumps(state, indent=2) + "\n")


def item(phase="PLANNING", governing="2.2", wtype="process", **extra) -> dict:
    return {"phase": phase, "governing_workflow_version": governing,
            "work_item_type": wtype, **extra}


def block(stdout: str) -> str:
    """The `work in flight` block of `status`'s stdout."""
    lines = stdout.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("  work in flight"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("next: ")),
               len(lines))
    return "\n".join(lines[start:end])


class TestStatusBlock(ux.TargetCase):
    def status(self, repo, **env):
        return run("status", str(repo), env=cli_env(**env) if env else None)

    def test_no_work_items_says_none(self):
        repo = self.fresh()
        proc = self.status(repo)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("  work in flight: none", proc.stdout)

    def test_terminal_items_only_says_none(self):
        repo = self.fresh()
        write_state(repo, {"old": item("MILESTONE_COMPLETE")})
        self.assertIn("  work in flight: none", self.status(repo).stdout)

    def test_one_active_item_is_listed_with_its_columns(self):
        repo = self.fresh()
        write_state(repo, {"a-item": item("PLANNING"), "done": item("MILESTONE_COMPLETE")},
                    active_work_item_id="a-item")
        proc = self.status(repo)
        self.assertEqual(proc.returncode, 0)
        text = block(proc.stdout)
        self.assertIn("work in flight: 1 active work item", text)
        self.assertRegex(text, r"a-item\s+PLANNING\s+process\s+governing 2\.2  \(active\)")
        self.assertNotIn("done", text)
        self.assertNotIn("inspection incomplete", text)

    def test_every_supported_governing_version_is_listed(self):
        repo = self.fresh()
        write_state(repo, {"one": item(governing="1"), "two-one": item(governing="2.1"),
                           "two-two": item(governing="2.2")})
        text = block(self.status(repo).stdout)
        for governing in ("1", "2.1", "2.2"):
            self.assertIn(f"governing {governing}", text)
        self.assertNotIn("incomplete", text)

    def test_more_than_ten_are_capped_with_a_count(self):
        repo = self.fresh()
        write_state(repo, {f"item-{n:02d}": item() for n in range(13)})
        text = block(self.status(repo).stdout)
        self.assertIn("13 active work items", text)
        self.assertIn("item-09", text)
        self.assertNotIn("item-10", text)
        self.assertIn("and 3 more", text)

    def test_the_state_file_missing_is_unknown_not_none(self):
        repo = self.fresh()
        (repo / STATE).unlink()
        proc = self.status(repo)
        text = block(proc.stdout)
        self.assertIn("work in flight: unknown (WORKFLOW_STATE.json is missing; "
                      f"workflow-manager doctor {repo} says what to do)", text)
        self.assertNotIn("none", text)

    def test_an_unreadable_or_foreign_state_is_could_not_be_read_not_none(self):
        for name, content in (("not json", "{bad"), ("a list", "[]"),
                              ("older schema", json.dumps({"schema_version": 0, "work_items": {}})),
                              ("newer schema", json.dumps({"schema_version": 2, "work_items": {}}))):
            with self.subTest(name):
                repo = self.fresh()
                (repo / STATE).write_text(content)
                proc = self.status(repo)
                text = block(proc.stdout)
                self.assertIn(f"work in flight: could not be read (workflow-manager doctor "
                              f"{repo} says why)", text)
                self.assertNotIn("none", text)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_an_unknown_governing_version_is_incomplete_never_none(self):
        repo = self.fresh()
        write_state(repo, {"future": item("IMPLEMENTING", governing="2.3")})
        proc = self.status(repo)
        text = block(proc.stdout)
        self.assertNotIn("work in flight: none", text)
        self.assertIn("inspection incomplete: 1 problem(s) (work item 'future' has "
                      "governing_workflow_version '2.3'", text)
        self.assertIn(f"workflow-manager doctor {repo} lists them", text)
        self.assertEqual(proc.returncode, 0)

    def test_an_unknown_phase_is_listed_and_counts_once(self):
        repo = self.fresh()
        write_state(repo, {"odd": item("SOMETHING_NEW"), "fine": item("PLANNING")})
        text = block(self.status(repo).stdout)
        self.assertIn("2 active work items", text)
        self.assertRegex(text, r"odd\s+SOMETHING_NEW\s+process\s+governing 2\.2  \(unknown phase\)")
        self.assertIn("inspection incomplete: 1 problem(s)", text)

    def test_a_malformed_entry_is_incomplete_and_the_rest_is_listed(self):
        repo = self.fresh()
        write_state(repo, {"bad": "text", "nophase": {"governing_workflow_version": "2.2"},
                           "good": item()})
        text = block(self.status(repo).stdout)
        self.assertIn("1 active work item", text)
        self.assertIn("good", text)
        self.assertIn("inspection incomplete: 2 problem(s)", text)
        self.assertNotIn("work in flight: none", text)

    def test_a_state_without_a_work_items_object_is_not_none(self):
        repo = self.fresh()
        (repo / STATE).write_text(json.dumps({"schema_version": 1}))
        text = block(self.status(repo).stdout)
        self.assertNotIn("work in flight: none", text)
        self.assertIn("inspection incomplete: 1 problem(s)", text)

    def test_the_next_line_names_doctor_and_is_the_only_one(self):
        repo = self.fresh()
        proc = self.status(repo)
        self.assertEqual(next_lines(proc.stdout),
                         [f"`workflow-manager doctor {repo}` reports what an update would meet"])
        for argv in ux.manager_commands(proc.stdout):
            self.assertTrue(ux.parses(argv), argv)

    def test_the_block_never_names_a_workflow_command(self):
        repo = self.fresh()
        write_state(repo, {"a-item": item("AWAITING_PLAN_APPROVAL")})
        text = self.status(repo).stdout
        self.assertNotIn("/approve", text)
        self.assertNotIn("/milestone", text)

    def test_the_reader_starts_no_git_and_writes_nothing(self):
        repo = self.fresh()
        write_state(repo, {"a-item": item()})
        before = tree_hash(repo)
        with mock.patch.object(comp, "run_git", side_effect=AssertionError("git ran")), \
                mock.patch.dict(os.environ, {"PATH": ""}):
            flight = comp.read_work_items(repo)
        self.assertEqual([i.id for i in flight.items], ["a-item"])
        self.assertEqual(tree_hash(repo), before)

    def test_the_block_is_printed_before_a_release_error(self):
        repo = self.fresh()
        write_state(repo, {"a-item": item()})
        proc = run("--release-version", "9.9.9", "status", str(repo))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("work in flight: 1 active work item", proc.stdout)
        self.assertIn("release 9.9.9 is not published", proc.stderr)
        self.assertEqual(len(next_lines(proc.stderr)), 1)

    def test_problems_and_the_doctor_clause_share_one_next_line(self):
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        proc = self.status(repo)
        self.assertEqual(proc.returncode, 1)
        lines = next_lines(proc.stdout)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith(
            f"`workflow-manager doctor {repo}` reports what an update would meet"))


class TestStatusContainment(ux.TargetCase):
    """3.5a: `status` of a managed target proves its writes stay outside the
    target and its `.git`, or exits 1."""

    def test_no_git_exits_1_with_the_record_and_the_block_first(self):
        repo = self.fresh()
        proc = run("status", str(repo), env=cli_env(PATH=""))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"workflow {NEWEST_RELEASE} (full profile)", proc.stdout)
        self.assertIn("work in flight:", proc.stdout)
        self.assertIn("could not check containment", proc.stderr)
        self.assertEqual(len(next_lines(proc.stderr)), 1)
        self.assertIn("make sure Git runs here", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_doctor_keeps_its_exit_2_for_the_same_causes(self):
        repo = self.fresh()
        self.assertEqual(run("doctor", str(repo), env=cli_env(PATH="")).returncode, 2)
        cache = repo / ".git" / "mycache"
        self.assertEqual(run("--release-cache", str(cache), "doctor", str(repo)).returncode, 2)

    def test_a_cache_inside_git_exits_1_and_creates_nothing(self):
        repo = self.fresh()
        before = tree_hash(repo)
        cache = repo / ".git" / "mycache"
        proc = run("--release-cache", str(cache), "status", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"the release cache {cache} lies inside", proc.stderr)
        self.assertIn("choose another cache: `workflow-manager --release-cache DIR status",
                      next_lines(proc.stderr)[0])
        self.assertFalse(cache.exists())
        self.assertEqual(tree_hash(repo), before)

    def test_a_cache_symlinked_into_the_repository_is_refused(self):
        repo = self.fresh()
        work = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, work, True)
        inside = repo / "elsewhere"
        inside.mkdir()
        (work / "cache").symlink_to(inside)
        before = tree_hash(repo)
        proc = run("--release-cache", str(work / "cache"), "status", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("lies inside", proc.stderr)
        self.assertEqual(tree_hash(repo), before)

    def test_a_temporary_directory_inside_the_repository_is_refused(self):
        repo = self.fresh()
        inside = repo / "tmp"
        inside.mkdir()
        before = tree_hash(repo)
        proc = run("status", str(repo), env=cli_env(TMPDIR=str(inside)))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("a temporary directory named in the environment", proc.stderr)
        self.assertEqual(tree_hash(repo), before)

    def test_an_empty_local_source_leaves_no_status_cache_under_git(self):
        repo = self.fresh()
        before = tree_hash(repo)
        work = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, work, True)
        (work / "source").mkdir()
        proc = run("--release-cache", str(work / "cache"), "--release-source",
                   str(work / "source"), "status", str(repo))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse((repo / ".git" / "status-cache").exists())
        self.assertEqual(tree_hash(repo), before)

    def test_a_usable_cache_and_git_still_exit_0_and_write_outside(self):
        repo = self.fresh()
        before = tree_hash(repo)
        proc = run("status", str(repo))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("— clean", proc.stdout)
        self.assertEqual(tree_hash(repo), before)

    def test_an_unmanaged_target_keeps_exit_0_without_git_or_destination_check(self):
        for make in (self.empty, lambda: Path(tempfile.mkdtemp())):
            target = make()
            self.addCleanup(__import__("shutil").rmtree, target, True)
            with mock.patch.object(comp, "run_git", side_effect=AssertionError("git ran")):
                proc = run("status", str(target), env=cli_env(PATH=""))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("not a managed repository", proc.stdout)

    def test_an_unmanaged_target_with_an_unpublished_version_keeps_exit_1(self):
        target = self.empty()
        proc = run("--release-version", "9.9.9", "status", str(target))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("release 9.9.9 is not published", proc.stderr)

    def test_an_unmanaged_target_with_a_cache_inside_git_is_the_known_gap(self):
        # 3.6: unchanged at the base, tested as unchanged.
        target = self.empty()
        cache = target / ".git" / "c"
        proc = run("--release-version", NEWEST_RELEASE, "--release-cache", str(cache),
                   "status", str(target))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("not a managed repository", proc.stdout)


class TestReportSteps(ux.ReleaseCase):
    def doctor(self, repo, *options, env=None):
        return run(*options, "doctor", str(repo), env=env)

    def test_the_not_verified_note_names_the_integrity_cause_and_verify(self):
        repo = self.fresh()
        work = self.workdir()
        (work / "source").mkdir()
        release_dir = self.release_dir()
        proc = run("--release-cache", str(work / "cache"), "--release-source",
                   str(work / "source"), "--release-dir", str(release_dir),
                   "doctor", str(repo))
        self.assertIn("[note] not-verified", proc.stdout)
        self.assertIn("offline, the release is not pinned, or its package failed verification",
                      proc.stdout)
        options = (f"--release-source {work / 'source'} --release-cache {work / 'cache'} "
                   f"--release-dir {release_dir}")
        self.assertIn(f"`workflow-manager {options} verify {repo}` prints the actual cause.",
                      proc.stdout)

    def test_a_downgrade_says_what_to_run_instead(self):
        repo = self.fresh()
        older = [v for v in support.PINNED_VERSIONS if v != NEWEST_RELEASE]
        if not older:
            self.skipTest("one pinned release")
        proc = self.doctor(repo, "--release-version", older[0])
        self.assertIn("[warning] downgrade", proc.stdout)
        self.assertIn(f"leave --release-version out: `workflow-manager doctor {repo}`", proc.stdout)

    def replayed(self, text, marker, repo, *, env=None):
        """The command printed after `marker`, run through the CLI."""
        match = re.search(re.escape(marker) + r"`(workflow-manager [^`]+)`", text)
        self.assertIsNotNone(match, text)
        argv = shlex.split(match.group(1))
        self.assertTrue(ux.parses(argv), argv)
        return argv, run(*argv[1:], env=env)

    def older_release_dir(self, version):
        directory = self.workdir() / "older"
        shutil.copytree(support.release(version).root, directory)
        return directory

    def test_i1_a_downgrade_step_drops_a_release_dir_holding_the_older_release(self):
        repo = self.fresh()
        older = [v for v in support.PINNED_VERSIONS if v != NEWEST_RELEASE]
        if not older:
            self.skipTest("one pinned release")
        directory = self.older_release_dir(older[-1])
        for options in (["--release-dir", str(directory)],
                        ["--release-version", older[-1], "--release-dir", str(directory)]):
            with self.subTest(options=options):
                proc = self.doctor(repo, *options)
                self.assertIn("[warning] downgrade", proc.stdout)
                argv, replay = self.replayed(proc.stdout, "leave --release-version out: ", repo)
                self.assertNotIn("--release-dir", argv)
                self.assertNotIn("[warning] downgrade", replay.stdout)
                self.assertNotIn(f"Target of this check {older[-1]}", replay.stdout)

    def test_i1_the_old_target_step_drops_a_release_dir_holding_another_release(self):
        repo = self.fresh()
        self.declare(repo)
        directory = self.older_release_dir("2.5.0")
        proc = self.doctor(repo, "--release-version", "2.5.0", "--release-dir", str(directory))
        self.assertIn("v2.4.0-001-old", proc.stdout)
        argv, replay = self.replayed(proc.stdout, "check a target of 2.6.0 or later: ", repo)
        self.assertNotIn("--release-dir", argv)
        self.assertIn("2.6.0", argv)
        self.assertNotEqual(replay.returncode, 2, replay.stdout + replay.stderr)
        self.assertNotIn("could not resolve", replay.stderr)

    def test_i1_the_verify_step_drops_a_release_dir_holding_another_release(self):
        repo = self.fresh()
        record = repo / ".workflow-manager/installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = "2.9.0"
        record.write_text(json.dumps(data, indent=2) + "\n")
        work = self.workdir()
        (work / "source").mkdir()
        directory = self.release_dir()
        proc = run("--release-cache", str(work / "cache"), "--release-source", str(work / "source"),
                   "--release-dir", str(directory), "doctor", str(repo))
        self.assertIn("[note] not-verified", proc.stdout)
        match = re.search(r"`(workflow-manager [^`]+ verify [^`]+)` prints the actual cause",
                          proc.stdout)
        self.assertIsNotNone(match, proc.stdout)
        argv = shlex.split(match.group(1))
        self.assertTrue(ux.parses(argv), argv)
        replay = run(*argv[1:])
        self.assertNotIn(str(directory), argv)
        self.assertIn("--release-source", argv)
        self.assertIn("--release-cache", argv)
        self.assertNotIn("holds release", replay.stderr)

    def report(self, repo, plan=None, refusal=None, target="2.9.1", installed=None):
        facts = comp.read_repository(repo)
        if installed:
            facts.installation = Installation(installed, "full", {})
        return comp.build_report(facts, plan, target_version=target, latest_version=NEWEST_RELEASE,
                                 pinned_versions=support.PINNED_VERSIONS, refusal=refusal,
                                 target_arg=str(repo))

    def finding(self, report, fid):
        return next(f for f in report.findings if f.id == fid)

    def declare(self, repo, wid="it", phase="IMPLEMENTING"):
        write_state(repo, {wid: item(phase)})
        art = repo / f"docs/ai-workflow/registry/{wid}-artifacts.json"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(json.dumps({
            "plan_stage": {"protected_prefixes": ["docs/ai-workflow/"]},
            "implementation_stage": {"protected_prefixes": ["scripts/"]}}))
        self.commit(repo)

    def test_the_old_target_finding_says_to_check_2_6_0_or_later(self):
        repo = self.fresh()
        self.declare(repo)
        found = self.finding(self.report(repo, target="2.5.0"), "v2.4.0-001-old")
        self.assertIn("What to do: check a target of 2.6.0 or later: "
                      f"`workflow-manager --release-version 2.6.0 doctor {repo}`", found.detail)

    def test_a_protected_path_says_finish_or_update_first_and_points_to_the_page(self):
        repo = self.fresh()
        self.declare(repo)
        found = self.finding(self.report(repo, plan=fake_plan(repo, writes=["scripts/x.py"])),
                             "v2.4.0-001")
        self.assertIn("What to do: finish the item (it reaches its final phase), or run the "
                      "update before the item starts implementing; ", found.detail)
        self.assertIn("update.md#check-before-you-update", found.detail)
        self.assertNotIn("park", found.detail)

    def test_the_update_clause_is_dropped_while_writes_are_withheld(self):
        repo = self.fresh()
        self.declare(repo)
        (repo / MILESTONE).unlink()
        found = self.finding(self.report(repo, plan=fake_plan(repo, writes=["scripts/x.py"])),
                             "v2.4.0-001")
        self.assertIn("What to do: finish the item (it reaches its final phase); ", found.detail)
        self.assertNotIn("run the update", found.detail)

    def test_unclassified_paths_point_to_the_installed_repair_procedure(self):
        repo = self.fresh()
        write_state(repo, {"it": item("PLANNING")})
        art = repo / "docs/ai-workflow/registry/it-artifacts.json"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(json.dumps({"plan_stage": {}, "implementation_stage": {}}))
        self.commit(repo)
        found = self.finding(self.report(repo, plan=fake_plan(repo, writes=["docs/new.md"])),
                             "unclassified-paths")
        self.assertIn('"Repairing an artifact declaration after an approval"', found.detail)
        self.assertIn("docs/ai-workflow/REVIEW_PROTOCOL.md", found.detail)

    def test_a_file_collision_carries_the_force_command_and_a_directory_does_not(self):
        repo = self.fresh()
        files = [Drift("scripts/x.py", "collision", "the repository has its own file here")]
        report = self.report(repo, refusal=CollisionError("refusing to update: in use", files))
        found = self.finding(report, "refused-collision")
        self.assertIn("What to do: move your own files away and run the update again, or add "
                      "--force to replace them with the release's:", found.detail)
        self.assertEqual([c.render() for c in found.commands],
                         [f"workflow-manager update --force {repo}"])
        directory = [Drift("scripts", "collision", "a directory is in the way")]
        report = self.report(repo, refusal=CollisionError("refusing to update: in use", directory))
        found = self.finding(report, "refused-collision")
        self.assertIn("(--force cannot replace either)", found.detail)
        self.assertEqual(found.commands, ())

    def test_a_collision_withholds_force_and_the_rerun_while_a_template_is_missing(self):
        repo = self.fresh()
        (repo / CONFIG).unlink()
        files = [Drift("scripts/x.py", "collision", "the repository has its own file here")]
        found = self.finding(self.report(repo, refusal=CollisionError("refusing to update", files)),
                             "refused-collision")
        self.assertEqual(found.commands, ())
        self.assertIn("Workflow data is missing or damaged", found.detail)
        self.assertIn("do not run it again until the Workflow data named above is back in place",
                      found.detail)
        self.assertNotIn("--force", found.detail)


class TestWorkflowDataInTheReport(ux.TargetCase):
    """P1 in findings and Recovery: no printed command writes Workflow data."""

    def doctor(self, repo, *options, env=None):
        return run(*options, "doctor", str(repo), env=env)

    def recovery(self, stdout: str) -> str:
        return stdout.split("Recovery", 1)[1]

    def assertNoWrite(self, text):
        """No backticked command writes: only `cp -p`, `ls -ld` and the vetted
        history readers are printed, and no Manager `update` or `bootstrap`."""
        for command in ux.backticked(text):
            words = command.split()
            self.assertNotIn("--force", words, command)
            self.assertFalse(words[:1] == ["workflow-manager"] and
                             any(w in ("update", "bootstrap") for w in words), command)
            if "git" in words:
                self.assertRegex(command, r"(log --oneline --no-show-signature|show --no-textconv|"
                                          r"rev-parse --git-dir)")
        for word in ("git restore", "git clean", "checkout --", "git stash"):
            self.assertNotIn(word, text)

    def test_a_missing_template_withholds_every_writing_command_in_recovery(self):
        repo = self.fresh()
        (repo / MILESTONE).unlink()
        self.commit(repo)
        proc = self.doctor(repo)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("[warning] incomplete-inspection: a Workflow data file is missing",
                      proc.stdout)
        rec = self.recovery(proc.stdout)
        self.assertIn("No command that writes the repository is offered: the Workflow data "
                      "problem named above needs your decision first (", rec)
        self.assertIn("review the working tree by hand", rec.replace("Review", "review"))
        self.assertNotIn("git status", rec)
        for word in ("git restore", "git clean", "update", "bootstrap", "--force"):
            self.assertNotIn(word, rec)

    def test_a_missing_template_finding_carries_the_p1_step(self):
        repo = self.fresh()
        (repo / CONFIG).unlink()
        self.commit(repo)
        proc = self.doctor(repo)
        text = proc.stdout.split("Recovery")[0]
        self.assertIn("What to do: Workflow data is missing or damaged", text)
        self.assertIn("repair-workflow-data-by-hand", text)
        self.assertNoWrite(text)
        self.assertFalse((repo / CONFIG).exists())

    def test_malformed_state_gets_a_copy_aside_and_withholds_recovery(self):
        repo = self.fresh()
        (repo / STATE).write_text("{bad")
        self.commit(repo)
        before = tree_hash(repo)
        proc = self.doctor(repo)
        self.assertIn("cannot be read as JSON", proc.stdout)
        self.assertIn(f"cp -p -- {repo}/{STATE} {repo}/{STATE}.bak", proc.stdout)
        self.assertNoWrite(proc.stdout)
        self.assertIn("No command that writes the repository is offered",
                      self.recovery(proc.stdout))
        self.assertEqual(tree_hash(repo), before)

    def test_an_unknown_schema_version_says_to_upgrade_the_manager(self):
        for version in (0, 2):
            with self.subTest(version=version):
                repo = self.fresh()
                (repo / STATE).write_text(json.dumps({"schema_version": version,
                                                      "work_items": {}}))
                self.commit(repo)
                proc = self.doctor(repo)
                self.assertIn("What to do: upgrade the Manager: ", proc.stdout)
                self.assertIn("update.md#update-the-manager", proc.stdout)
                self.assertIn("No command that writes the repository is offered",
                              self.recovery(proc.stdout))

    def test_declarations_missing_for_a_current_item_withholds_recovery(self):
        repo = self.fresh()
        write_state(repo, {"it": item("PLANNING")})
        self.commit(repo)
        proc = self.doctor(repo)
        self.assertIn("declarations could not be fully read", proc.stdout)
        self.assertIn("it-artifacts.json is missing or unreadable", proc.stdout)
        self.assertIn("What to do: Workflow data is missing or damaged", proc.stdout)
        self.assertIn("No command that writes the repository is offered",
                      self.recovery(proc.stdout))

    def test_a_legacy_item_without_declarations_says_finish_it(self):
        repo = self.fresh()
        write_state(repo, {"old": item("LEGACY_READY", governing="1", wtype="product")})
        self.commit(repo)
        proc = self.doctor(repo)
        self.assertIn("What to do: a legacy item has no declarations: finish it", proc.stdout)

    def test_a_git_problem_names_the_check_to_run(self):
        repo = self.fresh()
        facts = comp.read_repository(repo)
        facts.problems.append("`git worktree list` failed: linked worktrees were not counted")
        findings = comp.build_findings(facts, None, target=None, target_arg=str(repo))
        found = next(f for f in findings if f.title == "the inspection could not be completed")
        self.assertIn(f"What to do: make sure `env GIT_NO_LAZY_FETCH=1 git -C {repo} "
                      "--no-optional-locks rev-parse --git-dir` works here, or review the named "
                      "parts by hand", found.detail)

    def test_any_other_problem_says_to_fix_it_and_run_doctor_again(self):
        repo = self.fresh()
        facts = comp.read_repository(repo)
        facts.problems.append("work item 'x' is not an object")
        findings = comp.build_findings(facts, None, target=None, target_arg=str(repo))
        found = next(f for f in findings if f.title == "the inspection could not be completed")
        self.assertIn(f"What to do: fix what is named and run `workflow-manager doctor {repo}` again",
                      found.detail)

    def test_the_withholding_predicate_is_unchanged_by_the_steps(self):
        for breakage in (lambda r: (r / STATE).write_text("{bad"),
                         lambda r: (r / CONFIG).unlink(),
                         lambda r: write_state(r, {"it": item()}),
                         lambda r: None):
            repo = self.fresh()
            breakage(repo)
            facts = comp.read_repository(repo)
            plain = comp.build_findings(facts, None, target=None, steps=False)
            stepped = comp.build_findings(facts, None, target=None, target_arg=str(repo))
            missing, holds = facts.missing_templates, facts.holds_data
            self.assertEqual(comp.writes_withheld(plain, missing, holds),
                             comp.writes_withheld(stepped, missing, holds))
            self.assertEqual(comp.writes_withheld(plain, missing, holds),
                             comp.writes_withheld(comp.data_findings(repo), missing, holds))

    def test_a_clean_repository_keeps_the_baseline_recovery(self):
        repo = self.fresh()
        rec = self.recovery(self.doctor(repo).stdout)
        self.assertIn("Before the update", rec)
        self.assertIn("git -C", rec)
        self.assertIn("An update that stopped half way is re-run with the same command", rec)
        self.assertIn("restore --source=HEAD --staged --worktree -- .", rec)
        self.assertNotIn("No command that writes", rec)

    def test_a_legacy_ready_item_keeps_its_slash_command_while_writes_are_withheld(self):
        repo = self.fresh()
        write_state(repo, {"old": item("LEGACY_READY", governing="1", wtype="product")})
        (repo / MILESTONE).unlink()
        self.commit(repo)
        proc = self.doctor(repo)
        rec = self.recovery(proc.stdout)
        self.assertIn("No command that writes the repository is offered", rec)
        self.assertIn("/retire-legacy-work-item old", proc.stdout)


class TestCollisionAndDriftFindings(ux.TargetCase):
    def test_a_drift_refusal_keeps_the_force_sentence_when_nothing_is_missing(self):
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        self.commit(repo)
        proc = run("update", str(repo), "--dry-run")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("run the update with --force to discard them", proc.stdout)

    def test_a_drift_refusal_withholds_force_while_a_template_is_missing(self):
        repo = self.fresh()
        (repo / "scripts" / "workflow_state.py").write_text("# edited\n")
        (repo / CONFIG).unlink()
        self.commit(repo)
        proc = run("update", str(repo), "--dry-run")
        self.assertEqual(proc.returncode, 2)
        findings = proc.stdout.split("Recovery")[0]
        self.assertNotIn("run the update with --force", findings)
        self.assertIn("Workflow data is missing or damaged", findings)
        rec = proc.stdout.split("Recovery", 1)[1]
        self.assertNotIn("--force", rec)
        self.assertFalse((repo / CONFIG).exists())


if __name__ == "__main__":
    unittest.main()
