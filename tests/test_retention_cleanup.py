#!/usr/bin/env python3
"""The retention cleanup preview (`workflow-manager retention-cleanup`).

Hermetic: the stub script of `test_retention_status` in a scratch managed
repository whose policy and adoption record are committed, no network, nothing
written into this repository. The stub-based cases run `cli.main` in-process with
the script-state seam patched (a stub is never the release's script);
`TestRealRules` runs the real rule in subprocesses against a release of the cache
that ships the script, with nothing patched. The command writes nothing and runs
no script verb but `report`; every test that could show otherwise checks it.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import support
from support import NEWEST_RELEASE, REPO_ROOT

import test_retention_status as rs
from frozen_runs import build_bootstrapped_repo
from test_operator_ux import git, help_of, tree_hash
from workflow_manager import fixture, cli, retention_alert as ra, retention_cleanup as rc, retention_policy as rp

COMMAND = "retention-cleanup"
SCRIPT = rs.SCRIPT
MIB = 2**20
POLICY = {"schema_version": 1, "mode": "both",
          "thresholds": {"finished_items": 10, "finished_folder_mib": 500}}


def entry(item_id, *, mib=0, size=None, tracked=0, archive=False):
    found = rs.finished(item_id, tracked=tracked, archive=archive)
    found["review_folder"]["bytes"] = mib * MIB if size is None else size
    return found


def oldest_first(*entries):
    """A report lists the newest first; the tests write the oldest first."""
    return rs.report(*reversed(entries))


def adopted(mode="both", **thresholds):
    policy = {"schema_version": 1, "mode": mode, "thresholds": thresholds}
    return rp.PolicyState(rp.ADOPTED, mode=mode, policy=policy, digest=rp.digest_of(policy))


def plan_for(report, mode="both", **thresholds):
    return rc.select(adopted(mode, **thresholds), report)


def ids(plan):
    return [item.work_item_id for item in plan.items]


class TestSelect(unittest.TestCase):
    def test_the_oldest_are_cleaned_first_and_every_action_comes_from_the_report(self):
        report = oldest_first(entry("a"), entry("b", archive=True), entry("c"))
        plan = plan_for(report, finished_items=1)
        self.assertEqual([(i.work_item_id, i.action) for i in plan.items],
                         [("a", rc.ARCHIVE_THEN_REMOVE), ("b", rc.REMOVE_ONLY),
                          ("c", rc.ARCHIVE_THEN_REMOVE)])
        self.assertEqual(plan.outcome, rc.SETTLED)

    def test_at_most_the_cap_per_run_and_a_candidate_is_left(self):
        plan = plan_for(oldest_first(*(entry(f"i{n}") for n in range(7))), finished_items=1)
        self.assertEqual(ids(plan), ["i0", "i1", "i2", "i3", "i4"])
        self.assertEqual(plan.outcome, rc.CAPPED)
        self.assertEqual(plan.after["finished_items"], 2)

    def test_the_cap_with_no_candidate_left_is_exhausted_not_cap(self):
        plan = plan_for(oldest_first(*(entry(f"i{n}") for n in range(5))), finished_items=1)
        self.assertEqual((len(plan.items), plan.outcome), (5, rc.SETTLED))
        plan = plan_for(oldest_first(*(entry(f"i{n}") for n in range(5)),
                                     entry("t", tracked=1)), finished_items=1)
        self.assertEqual((len(plan.items), plan.outcome), (5, rc.EXHAUSTED))

    def test_an_entry_with_tracked_files_is_skipped_with_its_reason_and_still_counts(self):
        plan = plan_for(oldest_first(entry("t", tracked=2), entry("a"), entry("b")),
                        finished_items=3)
        self.assertEqual(ids(plan), ["a"])
        self.assertEqual(plan.skipped, (("t", rc.REASON_TRACKED),))
        self.assertEqual(plan.before["finished_items"], 3)
        self.assertEqual(plan.after["finished_items"], 2)

    def test_exhausted_names_what_was_skipped(self):
        plan = plan_for(oldest_first(entry("t1", tracked=1), entry("t2", tracked=1),
                                     entry("a")), finished_items=1)
        self.assertEqual(plan.outcome, rc.EXHAUSTED)
        self.assertIn("  after this run: finished items 2: finished items still reached; no "
                      "further item is eligible (skipped: t1, t2); running it again will not "
                      "help", rc.preview_lines(plan))

    def test_exhausted_with_an_empty_plan_prints_a_preview_not_nothing_to_do(self):
        plan = plan_for(oldest_first(entry("t", tracked=1)), finished_items=1)
        self.assertEqual((plan.items, plan.outcome), ((), rc.EXHAUSTED))
        lines = rc.preview_lines(plan)
        self.assertIn("  would clean 0 of 1 finished items with a review folder, oldest first, "
                      "at most 5 per run:", lines)
        self.assertTrue(lines[0].startswith("retention cleanup: preview "))

    def test_an_id_the_engine_would_not_accept_is_skipped(self):
        for bad in ("Upper", "-lead", "a" * 65, "runtime", "archive", "has space", "x\n"):
            with self.subTest(bad=bad):
                plan = plan_for(oldest_first(entry(bad), entry("a")), finished_items=1)
                self.assertEqual(ids(plan), ["a"])
                self.assertEqual(len(plan.skipped), 1)
                self.assertEqual(plan.skipped[0][1], rc.REASON_ID)

    def test_nothing_to_do_below_every_limit(self):
        plan = plan_for(oldest_first(*(entry(f"i{n}") for n in range(4))),
                        finished_items=10, finished_folder_mib=500)
        self.assertEqual((plan.items, plan.outcome), ((), None))
        self.assertEqual(rc.preview_lines(plan), [
            "retention cleanup: nothing to do (finished items 4 of 10, finished folders 0 of "
            "500 MiB)"])

    def test_an_unset_threshold_is_not_printed(self):
        plan = plan_for(oldest_first(entry("a")), finished_items=10)
        self.assertEqual(rc.preview_lines(plan),
                         ["retention cleanup: nothing to do (finished items 1 of 10)"])

    def test_only_the_two_lowered_thresholds_take_part(self):
        report = oldest_first(*(entry(f"i{n}") for n in range(4)))
        report["totals"].update(archives=99, prunable=99)
        plan = plan_for(report, archives=1, prunable_archives=1, finished_items=10)
        self.assertEqual((plan.items, plan.outcome), ((), None))
        self.assertIn("nothing to do", rc.preview_lines(plan)[0])
        only = plan_for(report, archives=1, prunable_archives=1)
        self.assertEqual(rc.preview_lines(only), [
            "retention cleanup: nothing to do (the policy sets no threshold that cleanup can "
            "lower)"])

    def test_the_folder_limit_is_in_mib_at_the_limit_and_one_byte_below(self):
        for size, planned in ((MIB, ["a"]), (MIB - 1, [])):
            with self.subTest(size=size):
                plan = plan_for(oldest_first(entry("a", size=size)), finished_folder_mib=1)
                self.assertEqual(ids(plan), planned)

    def test_the_folder_threshold_alone_plans_by_bytes(self):
        report = oldest_first(entry("a", mib=300), entry("b", mib=300), entry("c", mib=1))
        plan = plan_for(report, finished_folder_mib=500)
        self.assertEqual(ids(plan), ["a"])
        self.assertEqual(plan.outcome, rc.SETTLED)

    def test_the_plan_stops_only_when_every_set_threshold_is_below(self):
        # items fall below 10 after three, bytes need eight: the cap stops it at five
        report = oldest_first(*(entry(f"i{n:02d}", mib=100) for n in range(12)))
        plan = plan_for(report, finished_items=10, finished_folder_mib=500)
        self.assertEqual(len(plan.items), 5)
        self.assertEqual(plan.outcome, rc.CAPPED)
        self.assertIn("finished folders still reached; stopped at the cap of 5 per run; run it "
                      "again", rc.preview_lines(plan)[-3])

    def test_the_rule_on_twelve_items_one_skipped_takes_three(self):
        plan = plan_for(oldest_first(entry("x", tracked=1), *(entry(f"i{n}") for n in range(11))),
                        finished_items=10)
        self.assertEqual(len(plan.items), 3)
        self.assertEqual(plan.outcome, rc.SETTLED)

    def test_an_archived_and_removed_item_is_not_a_candidate(self):
        gone = rs.finished("gone", folder=False)
        plan = plan_for(rs.report(*(entry(f"i{n}") for n in range(3)), gone), finished_items=2)
        self.assertEqual(plan.before["finished_items"], 3)
        self.assertNotIn("gone", ids(plan))


EXAMPLE = """\
retention cleanup: preview (nothing was written; mode {mode}, policy {policy}, plan {plan})
  thresholds reached: finished items 12 (limit 10), finished folders 612 MiB (limit 500 MiB)
  would clean 3 of 12 finished items with a review folder, oldest first, at most 5 per run:
    1. item-a: 210 MiB, archive then remove
    2. item-b: 3 MiB, remove only (already archived)
    3. item-c: 40 MiB, archive then remove
  skipped: item-x: Git tracks files under its review folder (the engine archives untracked folders only)
  after this run: finished items 9, finished folders 359 MiB: below every limit
  this release does not apply the plan. Prune is never part of cleanup; the archive store is not touched.
  next: apply it with the user-only commands, one item at a time: `python3 -I scripts/workflow_retention.py archive ID --apply`, then `remove ID --apply`
"""


def example_report():
    return oldest_first(
        entry("item-x", mib=100, tracked=1), entry("item-a", mib=210),
        entry("item-b", mib=3, archive=True), entry("item-c", mib=40),
        *(entry(f"item-{n}", mib=32) for n in range(7)), entry("item-z", mib=35))


class TestPlanDigest(unittest.TestCase):
    def plan(self, report=None, mode="both", **thresholds):
        return plan_for(report or oldest_first(entry("a"), entry("b")),
                        mode, **(thresholds or {"finished_items": 1}))

    def test_stable_across_runs(self):
        self.assertEqual(rc.plan_digest(self.plan()), rc.plan_digest(self.plan()))
        self.assertRegex(rc.plan_digest(self.plan()), r"^[0-9a-f]{64}$")

    def test_moves_with_an_id_an_action_the_policy_and_the_repository(self):
        base = rc.plan_digest(self.plan())
        other_id = oldest_first(entry("a"), entry("c"))
        other_action = oldest_first(entry("a"), entry("b", archive=True))
        other_repo = oldest_first(entry("a"), entry("b"))
        other_repo["repository"] = "/somewhere/else"
        for label, plan in (("id", self.plan(other_id)), ("action", self.plan(other_action)),
                            ("policy", self.plan(finished_items=1, finished_folder_mib=9)),
                            ("repository", self.plan(other_repo))):
            with self.subTest(label=label):
                self.assertNotEqual(rc.plan_digest(plan), base)

    def test_the_mode_alone_does_not_move_it(self):
        # the policy digest covers the mode; the same policy text is one digest
        self.assertEqual(rc.plan_digest(self.plan(mode="both")),
                         rc.plan_digest(self.plan(mode="both")))


class TestExample(unittest.TestCase):
    def test_the_exact_block(self):
        plan = plan_for(example_report(), finished_items=10, finished_folder_mib=500)
        self.assertEqual(ids(plan), ["item-a", "item-b", "item-c"])
        want = EXAMPLE.format(mode="both", policy=plan.policy_digest[:12],
                              plan=rc.plan_digest(plan)[:12])
        self.assertEqual("\n".join(rc.preview_lines(plan)) + "\n", want)


class Base(rs.Scratch):
    """A scratch managed repository at the first release the cleanup accepts, the
    stub installed, `POLICY` adopted and everything committed."""

    VERSION = "2.25.5"

    def setUp(self):
        super().setUp()
        self.install_stub()
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = self.VERSION
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.adopt()
        self.commit(self.repo, "adopt")
        (self.repo / ".ai-review" / "some-item").mkdir(parents=True)
        (self.repo / ".ai-review" / "some-item" / "file").write_text("untracked review folder\n")

    def adopt(self, policy=None):
        policy = policy or POLICY
        path = rp.policy_path(self.repo)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(policy))
        rp.apply(self.repo, rp.usable_policy(self.repo), rp.sentence(rp.digest_of(policy)))

    def call(self, rep=None, *, seam=ra.SCRIPT_OK, command=COMMAND, **env):
        if rep is not None:
            env["STUB_REPORT"] = str(self.put_report(rep))
        self.marker.unlink(missing_ok=True)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env(**env), clear=True), \
                mock.patch.object(cli, "_installed_script_state", return_value=seam), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(["--release-version", support.PINNED_NEWEST, command,
                                 str(self.repo)])
            except SystemExit as exit_:
                code = exit_.code
        return Out(code, out.getvalue(), err.getvalue())

    def script_calls(self):
        if not self.marker.exists():
            return []
        return [json.loads(line) for line in self.marker.read_text().splitlines()]

    def stale_index(self):
        """Touch a tracked file so a plain `git status` would rewrite the index."""
        os.utime(self.repo / "CLAUDE.md", (1, 1))

    def refused(self, out, cause, step=None, *, started=False):
        self.assertEqual((out.code, out.out), (2, ""), out.err)
        lines = out.err.splitlines()
        self.assertEqual(len(lines), 2, out.err)
        self.assertTrue(lines[0].startswith("error: "), lines[0])
        self.assertIn(cause, lines[0])
        self.assertTrue(lines[1].startswith("next: "), lines[1])
        if step is not None:
            self.assertIn(step, lines[1])
        self.assertEqual(bool(self.script_calls()), started)

    def refusal_writes_nothing(self, rep=None, **env):
        self.stale_index()
        before = tree_hash(self.repo)
        out = self.call(rep, **env)
        self.assertEqual(tree_hash(self.repo), before)
        return out


@dataclass
class Out:
    code: int
    out: str
    err: str


def many(count=12, **kw):
    return oldest_first(*(entry(f"item-{n:02d}", **kw) for n in range(count)))


class TestPreflight(Base):
    def test_a_repository_that_is_not_managed(self):
        shutil.rmtree(self.repo / ".workflow-manager")
        out = self.call(many())
        self.assertEqual(out.code, 2)
        self.assertIn("is not a managed repository", out.err)
        self.assertEqual(self.script_calls(), [])

    def test_the_policy_states_each_refuse_with_their_own_cause_and_step(self):
        cases = {}
        path = rp.policy_path(self.repo)
        adoption = rp.record_path(self.repo)
        good = path.read_bytes()
        record = adoption.read_bytes()

        def reset():
            path.write_bytes(good)
            adoption.write_bytes(record)

        path.write_text(json.dumps({**POLICY, "mode": "off", "x": 1}))
        cases[rp.INVALID] = None
        reset()
        path.write_text(json.dumps({**POLICY, "mode": "cleanup"}))
        cases[rp.CHANGED] = None
        reset()
        adoption.unlink()
        cases[rp.NOT_ADOPTED] = None
        reset()
        adoption.write_text("{}")
        cases[rp.RECORD_INVALID] = None
        reset()
        path.unlink()
        cases[rp.FILE_MISSING] = None
        reset()
        for state in cases:
            with self.subTest(state=state):
                if state == rp.INVALID:
                    path.write_text(json.dumps({**POLICY, "mode": "off", "x": 1}))
                elif state == rp.CHANGED:
                    path.write_text(json.dumps({**POLICY, "mode": "cleanup"}))
                elif state == rp.NOT_ADOPTED:
                    adoption.unlink()
                elif state == rp.RECORD_INVALID:
                    adoption.write_text("{}")
                else:
                    path.unlink()
                loaded = rp.load(self.repo)
                self.assertEqual(loaded.state, state)
                out = self.refusal_writes_nothing(many())
                self.refused(out, f"retention policy: {state} ({rp._WORDS[state]})",
                             rp.step_for(state, self.repo))
                reset()

    def test_no_policy_at_all_is_the_exact_first_contact_message(self):
        rp.policy_path(self.repo).unlink()
        rp.record_path(self.repo).unlink()
        out = self.refusal_writes_nothing(many())
        self.refused(out, "retention cleanup: no retention policy is adopted (there is no "
                          ".workflow-manager/retention-policy.json)")
        self.assertEqual(out.err.splitlines()[1],
                         'next: write .workflow-manager/retention-policy.json with mode '
                         '"cleanup" or "both" (docs/retention.md shows the file), then run '
                         f"workflow-manager adopt-retention-policy {self.repo}")

    def test_the_mode_matrix(self):
        for mode, allowed in (("off", False), ("notify", False), ("cleanup", True),
                              ("both", True)):
            with self.subTest(mode=mode):
                self.adopt({**POLICY, "mode": mode})
                self.commit(self.repo, mode)
                out = self.refusal_writes_nothing(many(3))
                if allowed:
                    self.assertEqual(out.code, 0, out.err)
                else:
                    self.refused(out, f"the adopted mode is {mode}, which does not allow cleanup",
                                 'set mode to "cleanup" or "both"')

    def test_a_policy_file_that_was_never_committed(self):
        git(self.repo, "rm", "-q", "--cached", ".workflow-manager/retention-policy.json")
        git(self.repo, "commit", "-q", "-m", "untrack")
        out = self.refusal_writes_nothing(many())
        self.refused(out, ".workflow-manager/retention-policy.json is not committed at HEAD",
                     "commit .workflow-manager/retention-policy.json")

    def test_the_record_missing_from_head(self):
        git(self.repo, "rm", "-q", "--cached", ".workflow-manager/retention-adoption.json")
        git(self.repo, "commit", "-q", "-m", "untrack")
        out = self.refusal_writes_nothing(many())
        self.refused(out, ".workflow-manager/retention-adoption.json is not committed at HEAD")

    def test_a_policy_edited_and_re_adopted_after_the_commit_is_refused_at_committed(self):
        self.adopt({**POLICY, "thresholds": {"finished_items": 3}})
        self.assertEqual(rp.load(self.repo).state, rp.ADOPTED)
        out = self.refusal_writes_nothing(many())
        self.refused(out, "is not committed at HEAD with the bytes that were adopted")

    def test_a_dirty_tracked_file(self):
        with (self.repo / "CLAUDE.md").open("a") as handle:
            handle.write("an edit\n")
        out = self.refusal_writes_nothing(many())
        self.refused(out, "retention cleanup: a tracked file is changed", "commit or restore")

    def test_an_untracked_review_folder_is_accepted(self):
        # one the ignore rules hide (the setUp folder) and one they do not
        (self.repo / "scratch-notes").mkdir()
        (self.repo / "scratch-notes" / "file").write_text("untracked and not ignored\n")
        self.assertIn("scratch-notes/", git(self.repo, "status", "--porcelain").stdout)
        out = self.refusal_writes_nothing(many(3))
        self.assertEqual(out.code, 0, out.err)

    def test_the_release_floor(self):
        record = self.repo / ".workflow-manager" / "installation.json"
        for version, accepted in (("2.25.4", False), ("2.25.5", True), ("2.26.0", True),
                                  ("2.9.9", False)):
            with self.subTest(version=version):
                data = json.loads(record.read_text())
                data["workflow_version"] = version
                record.write_text(json.dumps(data, indent=2) + "\n")
                self.commit(self.repo, version)
                out = self.refusal_writes_nothing(many(3))
                if accepted:
                    self.assertEqual(out.code, 0, out.err)
                else:
                    self.refused(out, f"the installed Workflow release {version} is older than "
                                      "2.25.5", f"workflow-manager update {self.repo}")

    def test_a_record_with_no_release_is_refused_as_doctor_refuses_it(self):
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = None
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.commit(self.repo, "null")
        out = self.refusal_writes_nothing(many())
        self.refused(out, "could not resolve the target release: the installation record has "
                          "no workflow_version (it is null)")

    def test_a_noncanonical_release_name_is_a_malformed_record_before_the_script_state(self):
        record = self.repo / ".workflow-manager" / "installation.json"
        for version in ("02.25.5", "2.25.5\n"):
            with self.subTest(version=version):
                data = json.loads(record.read_text())
                data["workflow_version"] = version
                record.write_text(json.dumps(data, indent=2) + "\n")
                self.commit(self.repo, "malformed")
                with mock.patch.object(cli, "_installed_script_state",
                                       side_effect=AssertionError("resolved")):
                    out = self.refusal_writes_nothing(many())
                self.refused(out, "could not resolve the target release")
                self.assertNotIn(ra.CAUSE_UNCHECKED, out.err)

    def test_a_configured_fsmonitor_hook_never_runs_and_the_target_is_unchanged(self):
        marker = self.outside / "fsmonitor-ran"
        hook = self.outside / "fsmonitor.sh"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        git(self.repo, "config", "core.fsmonitor", str(hook))
        git(self.repo, "config", "core.hooksPath", str(self.outside / "hooks"))
        marker.unlink(missing_ok=True)   # `git config` itself may have woken it
        # a tracked change: the check still sees it, and the hook still never runs
        (self.repo / "CLAUDE.md").write_text("changed\n")
        out = self.refusal_writes_nothing(many())
        self.refused(out, "a tracked file is changed")
        self.assertFalse(marker.exists())
        # a clean tree: the preview succeeds, the hook never runs
        git(self.repo, "checkout", "--", "CLAUDE.md")
        marker.unlink(missing_ok=True)
        out = self.refusal_writes_nothing(many(3))
        self.assertEqual(out.code, 0, out.err)
        self.assertFalse(marker.exists())
        # a refusal after the tree check (step 5: no release) does not run it either
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = "02.25.5"
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.commit(self.repo, "malformed")
        marker.unlink(missing_ok=True)
        out = self.refusal_writes_nothing(many())
        self.refused(out, "could not resolve the target release")
        self.assertFalse(marker.exists())
        # a refusal before any Git call (the mode) does not run it either
        self.adopt({**POLICY, "mode": "notify"})
        out = self.refusal_writes_nothing(many())
        self.assertEqual(out.code, 2)
        self.assertFalse(marker.exists())

    def test_a_configured_clean_or_process_filter_never_runs_on_a_racily_dirty_file(self):
        marker = self.outside / "filter-ran"
        # a driver name is case-sensitive (`Probe` is not `probe`) and may hold an `=`
        for where, name in (("gitattributes", "probe"), ("info", "probe"),
                            ("gitattributes", "Probe"), ("info", "Mixed.Case"),
                            ("gitattributes", "a=b")):
            with self.subTest(where=where, name=name):
                attributes = f"CLAUDE.md filter={name}\n"
                if where == "info":
                    (self.repo / ".git" / "info").mkdir(exist_ok=True)
                    (self.repo / ".git" / "info" / "attributes").write_text(attributes)
                else:
                    (self.repo / ".gitattributes").write_text(attributes)
                    git(self.repo, "add", ".gitattributes")
                    git(self.repo, "commit", "-qm", "attributes")
                git(self.repo, "config", f"filter.{name}.clean", f"sh -c 'touch {marker}; cat'")
                git(self.repo, "config", f"filter.{name}.process", f"sh -c 'touch {marker}'")
                git(self.repo, "config", f"filter.{name}.required", "true")
                # a racily dirty file: same bytes, a stat the index no longer matches
                os.utime(self.repo / "CLAUDE.md", (946684800, 946684800))
                marker.unlink(missing_ok=True)
                out = self.refusal_writes_nothing(many(3))
                self.assertEqual(out.code, 0, out.err)
                self.assertFalse(marker.exists())
                # a tracked change is still seen, and the filter still never runs
                (self.repo / "CLAUDE.md").write_text("changed\n")
                out = self.refusal_writes_nothing(many())
                self.refused(out, "a tracked file is changed")
                self.assertFalse(marker.exists())
                for key in ("clean", "process", "required"):
                    git(self.repo, "config", "--unset", f"filter.{name}.{key}")
                git(self.repo, "checkout", "--", "CLAUDE.md")
                if where == "info":
                    (self.repo / ".git" / "info" / "attributes").unlink()
                else:
                    git(self.repo, "rm", "-q", ".gitattributes")
                    git(self.repo, "commit", "-qm", "no attributes")

    def test_a_filter_inherited_through_git_config_parameters_never_runs(self):
        # what a shell alias's `git -c filter.probe.process=...` exports; it outranks
        # `GIT_CONFIG_COUNT`, so it must not reach the preflight's Git calls
        marker = self.outside / "inherited-filter-ran"
        (self.repo / ".gitattributes").write_text("CLAUDE.md filter=probe\n")
        git(self.repo, "add", ".gitattributes")
        git(self.repo, "commit", "-qm", "attributes")
        command = f"sh -c 'touch {marker}'"
        # Git's own sq_quote form: a quote inside an entry is written as '\'' (shlex.quote's
        # '"'"' is a parse error to Git, which would make every Git call fail and this test vacuous)
        parameters = " ".join("'" + entry.replace("'", "'\\''") + "'" for entry in (
            f"filter.probe.process={command}", f"filter.probe.clean={command}",
            "filter.probe.required=true"))
        # sanity: Git parses the variable and the filter really is defined through it
        listed = subprocess.run(
            ["git", "config", "--get-regexp", r"^filter\."], cwd=self.repo, text=True,
            capture_output=True, env={**os.environ, "GIT_CONFIG_PARAMETERS": parameters})
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("filter.probe.process", listed.stdout)
        os.utime(self.repo / "CLAUDE.md", (946684800, 946684800))
        marker.unlink(missing_ok=True)
        # the destinations planner is outside this check (its Git calls are not the preflight's)
        with mock.patch.object(cli, "_readonly_destinations", return_value=None):
            out = self.refusal_writes_nothing(many(3), GIT_CONFIG_PARAMETERS=parameters)
            self.assertEqual(out.code, 0, out.err)
            self.assertFalse(marker.exists())
            (self.repo / "CLAUDE.md").write_text("changed\n")
            out = self.refusal_writes_nothing(many(), GIT_CONFIG_PARAMETERS=parameters)
        self.refused(out, "a tracked file is changed")
        self.assertFalse(marker.exists())

    def test_a_git_that_cannot_be_run_is_not_a_file_missing_at_head(self):
        for error in (subprocess.TimeoutExpired("git", 1), FileNotFoundError("git")):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(rc, "_git", side_effect=error):
                out = self.refusal_writes_nothing(many())
            self.refused(out, "Git could not be asked")

    def test_a_submodules_own_filter_never_runs_and_a_moved_submodule_is_still_refused(self):
        marker = self.outside / "submodule-filter-ran"
        source = self.outside / "sm-source"
        source.mkdir()
        fixture.init_git_repo(source)
        (source / ".gitattributes").write_text("b.txt filter=subf\n")
        (source / "b.txt").write_text("b\n")
        git(source, "add", ".")
        git(source, "-c", "maintenance.auto=false", "-c", "gc.auto=0", "commit", "-qm", "sub")
        git(self.repo, "-c", "protocol.file.allow=always", "-c", "maintenance.auto=false",
            "-c", "gc.auto=0", "submodule", "add", "-q",
            str(source), "sm")
        git(self.repo, "-c", "maintenance.auto=false", "-c", "gc.auto=0", "commit", "-qm",
            "add submodule")
        sub = self.repo / "sm"
        self.assertTrue((sub / "b.txt").is_file())
        git(sub, "config", "user.name", "t")
        git(sub, "config", "user.email", "t@example.com")
        git(sub, "config", "filter.subf.clean", f"sh -c 'touch {marker}; cat'")
        git(sub, "config", "filter.subf.required", "true")
        os.utime(sub / "b.txt", (946684800, 946684800))
        marker.unlink(missing_ok=True)
        out = self.refusal_writes_nothing(many(3))
        self.assertEqual(out.code, 0, out.err)
        self.assertFalse(marker.exists())
        # a submodule whose HEAD moved is still a tracked change
        git(sub, "config", "--unset", "filter.subf.clean")
        git(sub, "config", "--unset", "filter.subf.required")
        (sub / "c.txt").write_text("c\n")
        git(sub, "add", "c.txt")
        git(sub, "-c", "maintenance.auto=false", "-c", "gc.auto=0", "commit", "-qm", "moved")
        git(sub, "config", "filter.subf.clean", f"sh -c 'touch {marker}; cat'")
        git(sub, "config", "filter.subf.required", "true")
        os.utime(sub / "b.txt", (946684800, 946684800))
        out = self.refusal_writes_nothing(many())
        self.refused(out, "a tracked file is changed")
        self.assertFalse(marker.exists())

    def test_each_script_state_has_its_cause(self):
        for seam, cause in ((ra.SCRIPT_MODIFIED, ra.CAUSE_MODIFIED),
                            (ra.SCRIPT_UNCHECKED, ra.CAUSE_UNCHECKED),
                            (ra.SCRIPT_NO_RELEASE, ra.CAUSE_NO_RELEASE)):
            with self.subTest(seam=seam):
                out = self.refusal_writes_nothing(many(), seam=seam)
                self.refused(out, cause)

    def test_a_script_state_that_raises_is_unchecked(self):
        with mock.patch.object(cli, "_installed_script_state", side_effect=OSError("x")), \
                mock.patch.dict(os.environ, self.env(), clear=True), \
                contextlib.redirect_stderr(io.StringIO()) as err, \
                contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["--release-version", support.PINNED_NEWEST, COMMAND,
                             str(self.repo)])
        self.assertEqual(code, 2)
        self.assertIn(ra.CAUSE_UNCHECKED, err.getvalue())
        self.assertEqual(self.script_calls(), [])

    def test_steps_one_to_six_start_no_script(self):
        rp.record_path(self.repo).unlink()
        self.refusal_writes_nothing(many())
        with (self.repo / "CLAUDE.md").open("a") as handle:
            handle.write("x\n")
        self.refusal_writes_nothing(many(), seam=ra.SCRIPT_MODIFIED)
        self.assertEqual(self.script_calls(), [])

    def test_an_incomplete_report(self):
        for override in ({"complete": False}, {"read_errors": [{"path": "/x", "error": "no"}]},
                         {"not_finished": [{"work_item_id": "a",
                                            "reason": "query_failed:timeout"}]}):
            with self.subTest(override=override):
                rep = many()
                rep.update(override)
                self.refused(self.refusal_writes_nothing(rep), ra.CAUSE_INCOMPLETE,
                             "fix what is named", started=True)

    def test_an_interrupted_removal(self):
        rep = many()
        rep["removing"] = ["half-gone"]
        out = self.refusal_writes_nothing(rep)
        self.refused(out, "a removal was interrupted ('half-gone')", "remove ID --apply",
                     started=True)

    def test_a_refusal_of_the_report_is_passed_on(self):
        out = self.refusal_writes_nothing(STUB_MODE="exit", STUB_EXIT="2",
                                          STUB_STDERR="error: repository_unknown: no origin\\n"
                                                      "next step: add a remote")
        self.refused(out, "repository_unknown: no origin", "add a remote", started=True)

    def test_a_missing_script_is_the_reports_own_refusal(self):
        (self.repo / SCRIPT).unlink()
        git(self.repo, "commit", "-q", "-am", "no script")
        out = self.refusal_writes_nothing(many())
        self.refused(out, "the repository has no scripts/workflow_retention.py")


class TestPreview(Base):
    def test_the_exact_block_through_the_cli_for_both_and_cleanup(self):
        for mode in ("both", "cleanup"):
            with self.subTest(mode=mode):
                self.marker.unlink(missing_ok=True)
                self.adopt({**POLICY, "mode": mode})
                self.commit(self.repo, mode)
                out = self.call(example_report())
                self.assertEqual((out.code, out.err), (0, ""))
                plan = plan_for(example_report(), mode, finished_items=10, finished_folder_mib=500)
                want = EXAMPLE.format(mode=mode, policy=plan.policy_digest[:12],
                                      plan=rc.plan_digest(plan)[:12])
                self.assertEqual(out.out, want)
                self.assertIn(f"mode {mode}", out.out)

    def test_it_runs_exactly_one_report_and_nothing_else(self):
        self.call(example_report())
        calls = self.script_calls()
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(calls[0]["argv"][1], "report")
        self.assertNotIn("--apply", calls[0]["argv"])
        self.assertEqual({word for word in calls[0]["argv"][1:] if not word.startswith("-")
                          and word != str(self.repo.resolve())}, {"report"})

    def test_it_writes_nothing(self):
        self.stale_index()
        before = tree_hash(self.repo)
        self.call(example_report())
        self.assertEqual(tree_hash(self.repo), before)

    def test_nothing_to_do_exits_zero(self):
        out = self.call(many(3))
        self.assertEqual((out.code, out.err), (0, ""))
        self.assertEqual(out.out, "retention cleanup: nothing to do (finished items 3 of 10, "
                                  "finished folders 0 of 500 MiB)\n")


class TestOtherCommandsUnchanged(Base):
    """`verify`, `doctor` and `status` print what they print without the policy (a
    `cleanup` policy alerts nothing) and never start a script verb but `report`."""

    def lines(self, command):
        self.marker.unlink(missing_ok=True)
        out = self.call(many(), command=command)
        # the policy block names the mode and the digest, so it is left out
        text = [l for l in out.out.splitlines()
                if "retention policy" not in l and "thresholds:" not in l]
        return out, text

    def test_a_cleanup_policy_changes_nothing_in_the_other_commands(self):
        baseline = {}
        for mode in ("off", "cleanup"):
            self.adopt({**POLICY, "mode": mode})
            self.commit(self.repo, mode)
            for command in ("verify", "status", "doctor"):
                with self.subTest(mode=mode, command=command):
                    out, text = self.lines(command)
                    self.assertNotIn("retention cleanup", out.out)
                    self.assertEqual(self.script_calls(), [])
                    if mode == "off":
                        baseline[command] = (out.code, text)
                    else:
                        self.assertEqual((out.code, text), baseline[command])

    def test_a_both_policy_prints_no_preview_and_runs_no_cleanup_verb(self):
        for command in ("verify", "status", "doctor"):
            with self.subTest(command=command):
                out, _ = self.lines(command)
                self.assertNotIn("retention cleanup", out.out)
                for call in self.script_calls():
                    self.assertEqual(call["argv"][1], "report")


class TestRealRules(unittest.TestCase):
    """Nothing patched: the release's own script rule, in subprocesses."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pristine = build_bootstrapped_repo(support.release(NEWEST_RELEASE),
                                               Path(cls._tmp.name) / "pristine")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.repo = Path(self.work.name) / "r"
        shutil.copytree(self.pristine, self.repo, symlinks=True)
        self.marker = Path(self.work.name) / "marker"
        path = rp.policy_path(self.repo)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(POLICY))
        rp.apply(self.repo, rp.usable_policy(self.repo), rp.sentence(rp.digest_of(POLICY)))
        self.commit("adopt")

    def commit(self, message):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)

    def run_it(self):
        report = Path(self.work.name) / "report.json"
        report.write_text(json.dumps(many()))
        env = support.cli_env(STUB_MARKER=str(self.marker), STUB_REPORT=str(report))
        proc = subprocess.run([sys.executable, "-m", "workflow_manager", COMMAND,
                               str(self.repo)], cwd=str(REPO_ROOT), capture_output=True,
                              text=True, env=env)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        return proc

    def test_a_modified_script_is_never_started(self):
        (self.repo / SCRIPT).write_text(rs.STUB)
        self.commit("stub")
        proc = self.run_it()
        self.assertEqual((proc.returncode, proc.stdout), (2, ""), proc.stderr)
        self.assertIn(ra.CAUSE_MODIFIED, proc.stderr)
        self.assertFalse(self.marker.exists())

    def test_a_record_at_2_25_4_is_refused_before_any_script_starts(self):
        (self.repo / SCRIPT).write_text(rs.STUB)
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = "2.25.4"
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.commit("old")
        proc = self.run_it()
        self.assertEqual((proc.returncode, proc.stdout), (2, ""), proc.stderr)
        self.assertIn("older than 2.25.5", proc.stderr)
        self.assertFalse(self.marker.exists())

    def test_the_release_own_script_is_started_and_refuses_for_want_of_an_origin(self):
        proc = self.run_it()
        self.assertEqual((proc.returncode, proc.stdout), (2, ""), proc.stderr)
        self.assertIn("error: repository_unknown:", proc.stderr)
        self.assertIn("next: ", proc.stderr)


class TestDocs(unittest.TestCase):
    def test_the_help_names_the_preview_the_floor_and_prune(self):
        text = " ".join(help_of(COMMAND).split())
        for words in ("preview", "2.25.5", "writes nothing", "Prune is never part of cleanup",
                      "at most 5 per run", "Exit 0"):
            self.assertIn(words, text)

    def test_the_retention_page_names_the_command_the_floor_and_prune(self):
        page = " ".join((REPO_ROOT / "docs" / "retention.md").read_text().split())
        self.assertIn("workflow-manager retention-cleanup", page)
        self.assertIn("2.25.5", page)
        self.assertIn("Prune is never part of cleanup", page)

    def test_the_exit_codes_page_has_the_command(self):
        page = (REPO_ROOT / "docs" / "exit-codes.md").read_text()
        self.assertIn("retention-cleanup", page)


class TestCommandNameIsNotAnInternalId(unittest.TestCase):
    """`tools/check_docs.py` does not count a Manager command as an internal id,
    even when a work item is named after the command it built."""

    def test_a_manager_command_is_not_an_internal_id_even_when_a_work_item_has_its_name(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_docs_for_cleanup", REPO_ROOT / "tools" / "check_docs.py")
        check_docs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check_docs)
        header = "> For: operators. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0."
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in (
                    ("docs/ai-workflow/WORKFLOW_STATE.json",
                     json.dumps({"work_items": {"item-one": {}, "item-two": {}}})),
                    ("docs/glossary.md",
                     "# Title\n\n" + header + "\n\nRun `workflow-manager item-one`, not item-two.\n")):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            problems = [p for p in check_docs.check_pages(root, ("item-one",)) if "glossary" in p]
        self.assertEqual(len(problems), 1)
        self.assertIn("'item-two'", problems[0])


if __name__ == "__main__":
    unittest.main()
