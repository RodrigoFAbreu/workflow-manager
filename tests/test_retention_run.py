#!/usr/bin/env python3
"""The confirmed retention cleanup run (`retention-cleanup TARGET --confirm`).

Hermetic: a verb-aware stub script answers `report`, `archive`, `remove` and
`remove --apply` per a scenario table, in a scratch managed repository (the `Base`
of `test_retention_cleanup`). No network, no `gh`, nothing written into this
repository's work items. `TestEndToEnd` drives the release's own script through
its seams in a scratch repository.
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
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from support import NEWEST_RELEASE, REPO_ROOT

import test_retention_cleanup as tc
import test_retention_status as rs
from frozen_runs import build_bootstrapped_repo
from test_operator_ux import git, tree_hash
from workflow_manager import cli, retention, retention_alert as ra, retention_cleanup as rc
from workflow_manager import retention_policy as rp, retention_run as rr

SCRIPT = rs.SCRIPT
COMMAND = tc.COMMAND

RUN_STUB = r'''
import json, os, sys, time
argv = sys.argv[1:]
with open(os.environ["STUB_MARKER"], "a") as handle:
    handle.write(json.dumps({"argv": sys.argv, "cwd": os.getcwd()}) + "\n")
verb = argv[0]
if verb == "report":
    sys.stdout.write(open(os.environ["STUB_REPORT"]).read())
    sys.exit(0)
item = argv[1]
key = verb + (" --apply" if "--apply" in argv else "") + ":" + item
path = os.environ.get("STUB_SCENARIO")
spec = json.load(open(path)).get(key, {}) if path and os.path.exists(path) else {}
if spec.get("sleep"):
    time.sleep(spec["sleep"])
if "stdout" in spec:
    text = spec["stdout"]
    sys.stdout.write(text if isinstance(text, str) else json.dumps(text))
else:
    if verb == "archive":
        body = {"kind": "retention-archive", "mode": "apply", "work_item_id": item,
                "result": {"archived": True}}
    else:
        body = {"kind": "retention-remove", "mode": "apply" if "--apply" in argv else "dry-run",
                "work_item_id": item, "verify": {"matches": True},
                "result": {"removed": "--apply" in argv}}
    sys.stdout.write(json.dumps(body))
sys.stderr.write(spec.get("stderr", ""))
sys.exit(spec.get("exit", 0))
'''

MIB = tc.MIB


def refusal(code, message, step="fix it"):
    return {"exit": 2, "stdout": "", "stderr": f"error: {code}: {message}\nnext step: {step}\n"}


class RunBase(tc.Base):
    """`Base` with the verb-aware stub committed, and 12 finished items so that the
    plan is `item-00`, `item-01`, `item-02` (finished items 12 of 10)."""

    def setUp(self):
        super().setUp()
        (self.repo / SCRIPT).write_text(RUN_STUB)
        self.commit(self.repo, "run stub")
        self.scenario = self.outside / "scenario.json"
        self.rep = tc.many(12, mib=2)
        self.addCleanup(mock.patch.stopall)

    def plan(self, rep=None):
        return tc.plan_for(rep or self.rep, finished_items=10, finished_folder_mib=500)

    def sentence(self, rep=None):
        return rc.sentence(rc.plan_digest(self.plan(rep)))

    def go(self, scenario=None, *, confirm=True, rep=None, patches=(), **env):
        """Run the command in-process; `confirm` True is the plan's own sentence."""
        rep = rep or self.rep
        self.scenario.write_text(json.dumps(scenario or {}))
        self.marker.unlink(missing_ok=True)
        env["STUB_REPORT"] = str(self.put_report(rep))
        env["STUB_SCENARIO"] = str(self.scenario)
        text = self.sentence(rep) if confirm is True else confirm
        argv = ["--release-version", support.PINNED_NEWEST, COMMAND, str(self.repo)]
        if text is not None:
            argv += ["--confirm", text]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, self.env(**env), clear=True))
            stack.enter_context(mock.patch.object(cli, "_installed_script_state",
                                                  return_value=ra.SCRIPT_OK))
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            try:
                code = cli.main(argv)
            except SystemExit as exit_:
                code = exit_.code
        return tc.Out(code, out.getvalue(), err.getvalue())

    def refused(self, out, cause, step=None, *, started=False):
        """Exit 2 with `error:` and `next:`, nothing on stdout, and no engine verb
        beyond the report the preflight may read."""
        super().refused(out, cause, step, started=bool(self.script_calls()))
        self.assertEqual(self.keys(), [])

    def keys(self):
        """`verb[ --apply]:ID` of every engine call but the report, in order."""
        found = []
        for call in self.script_calls():
            argv = call["argv"][1:]
            if argv[0] != "report":
                found.append(argv[0] + (" --apply" if "--apply" in argv else "") + ":" + argv[1])
        return found


ITEM_STEPS = ("archive --apply", "remove", "remove --apply")


def full_run(*ids):
    return [f"{step}:{item}" for item in ids for step in ITEM_STEPS]


class TestSentence(RunBase):
    def test_the_exact_sentence_runs(self):
        out = self.go()
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertEqual(self.keys(), full_run("item-00", "item-01", "item-02"))

    def test_another_plans_sentence_is_refused(self):
        other = tc.many(12, mib=2)
        other["finished"][-1]["work_item_id"] = "item-zz"
        out = self.go(confirm=self.sentence(other))
        self.refused(out, "--confirm does not hold the sentence")
        self.assertEqual(self.keys(), [])

    def test_the_plan_digest_binds_the_sentence(self):
        policy_sentence = f"Run the retention cleanup {self.plan().policy_digest[:12]}."
        self.refused(self.go(confirm=policy_sentence), "does not hold the sentence")
        self.assertEqual(self.keys(), [])

    def test_a_wrong_sentence_names_the_command_that_shows_the_plan(self):
        out = self.go(confirm="yes")
        self.assertIn("next: run workflow-manager retention-cleanup ", out.err)
        self.assertIn("to see the current plan and its sentence", out.err)

    def test_an_empty_sentence_is_a_refusal(self):
        self.refused(self.go(confirm=""), "does not hold the sentence")
        self.assertEqual(self.keys(), [])

    def test_no_flag_is_the_preview_and_runs_nothing(self):
        out = self.go(confirm=None)
        self.assertEqual((out.code, out.err), (0, ""))
        self.assertTrue(out.out.startswith("retention cleanup: preview "))
        self.assertEqual(self.keys(), [])

    def test_case_and_extra_words_are_accepted_two_digests_are_not(self):
        text = self.sentence()
        out = self.go(confirm=f"please  {text.upper()}\n thanks")
        self.assertEqual(out.code, 0, out.err)
        other = "Run the retention cleanup " + "0" * 12 + "."
        self.refused(self.go(confirm=f"{text} {other}"), "does not hold the sentence")

    def test_an_empty_plan_runs_nothing(self):
        out = self.go(rep=tc.many(3), confirm="whatever")
        self.assertEqual((out.code, out.err), (0, ""))
        self.assertTrue(out.out.startswith("retention cleanup: nothing to do"))
        self.assertEqual(self.keys(), [])

    def test_the_sentence_is_not_consulted_before_the_preflight(self):
        (self.repo / "CLAUDE.md").write_text("dirty\n")
        self.refused(self.go(confirm="anything"), "a tracked file is changed")


class TestOrder(RunBase):
    def test_the_order_of_calls(self):
        self.go()
        self.assertEqual(self.keys(), full_run("item-00", "item-01", "item-02"))

    def test_remove_apply_follows_a_verified_archive(self):
        self.go()
        keys = self.keys()
        for item in ("item-00", "item-01", "item-02"):
            self.assertLess(keys.index(f"archive --apply:{item}"), keys.index(f"remove:{item}"))
            self.assertLess(keys.index(f"remove:{item}"), keys.index(f"remove --apply:{item}"))

    def test_remove_only_issues_no_archive(self):
        rep = tc.oldest_first(*(tc.entry(f"item-{n:02d}", mib=2, archive=(n == 1))
                                for n in range(12)))
        out = self.go(rep=rep)
        self.assertEqual(out.code, 0, out.err)
        self.assertEqual(self.keys(), full_run("item-00") + ["remove:item-01",
                                                              "remove --apply:item-01"]
                         + full_run("item-02"))
        self.assertIn("  2. item-01: remove only, verified, removed", out.out)


class TestNoRemovalWithoutVerification(RunBase):
    def test_a_failed_verification_issues_no_removal(self):
        out = self.go({"remove:item-00": refusal("archive_mismatch", "item differs")})
        self.assertEqual(out.code, 1)
        self.assertEqual(self.keys(), ["archive --apply:item-00", "remove:item-00"])
        self.assertIn("item-00's folder is untouched", out.out)

    def test_a_verification_that_does_not_match_stops(self):
        body = {"kind": "retention-remove", "mode": "dry-run", "work_item_id": "item-00",
                "verify": {"matches": False}, "result": {"removed": False}}
        out = self.go({"remove:item-00": {"stdout": body}})
        self.assertEqual(out.code, 1)
        self.assertNotIn("remove --apply:item-00", self.keys())


class TestStop(RunBase):
    def assert_stopped_after(self, out, keys):
        self.assertEqual(out.code, 1, out.out + out.err)
        self.assertEqual(self.keys(), keys)

    def test_the_first_failure_stops_before_any_further_call(self):
        for step in ITEM_STEPS:
            for item, before in (("item-00", []), ("item-01", full_run("item-00"))):
                with self.subTest(step=step, item=item):
                    out = self.go({f"{step}:{item}": refusal("place_failed", "nope")})
                    kept = [f"{s}:{item}" for s in ITEM_STEPS[:ITEM_STEPS.index(step) + 1]]
                    self.assert_stopped_after(out, before + kept)
                    self.assertIn("not attempted", out.out)
                    self.assertIn("  3. item-02: not attempted", out.out)

    def test_an_exit_zero_that_says_not_archived_stops(self):
        body = {"kind": "retention-archive", "mode": "apply", "work_item_id": "item-00",
                "result": {"archived": False}}
        out = self.go({"archive --apply:item-00": {"stdout": body}})
        self.assert_stopped_after(out, ["archive --apply:item-00"])

    def test_output_that_is_not_json_stops(self):
        out = self.go({"archive --apply:item-00": {"stdout": "not json"}})
        self.assert_stopped_after(out, ["archive --apply:item-00"])
        self.assertIn("not one JSON object", out.out)

    def test_a_step_must_return_its_own_shape(self):
        apply = {"kind": "retention-remove", "mode": "apply", "work_item_id": "item-00",
                 "result": {"removed": True}}
        dry = {"kind": "retention-remove", "mode": "dry-run", "work_item_id": "item-00",
               "verify": {"matches": True}, "result": {"removed": False}}
        arms = (("remove --apply:item-00", apply, full_run("item-00"),
                 (("id", {"work_item_id": "other"}), ("kind", {"kind": "retention-x"}),
                  ("mode", {"mode": "dry-run"}))),
                ("remove:item-00", dry, ["archive --apply:item-00", "remove:item-00"],
                 (("id", {"work_item_id": "other"}), ("kind", {"kind": "retention-x"}),
                  ("mode", {"mode": "apply"}), ("matches", {"verify": {"matches": False}}))))
        for key, good, kept, changes in arms:
            for label, change in changes:
                with self.subTest(step=key, label=label):
                    out = self.go({key: {"stdout": {**good, **change}}})
                    self.assert_stopped_after(out, kept)

    def test_a_timeout_stops_and_leaves_no_process(self):
        patches = [mock.patch.object(rr, "CALL_TIMEOUT_SECONDS", 1)]
        started = time.monotonic()
        out = self.go({"archive --apply:item-00": {"sleep": 30}}, patches=patches)
        self.assertLess(time.monotonic() - started, 20)
        self.assert_stopped_after(out, ["archive --apply:item-00"])
        self.assertIn("did not finish within 1 seconds", out.out)

    def interrupt_at(self, key):
        real = retention.launch_script

        def launch(root, *args, timeout):
            verb = args[0]
            if verb != "report" and key == verb + (" --apply" if "--apply" in args else "") \
                    + ":" + args[1]:
                raise KeyboardInterrupt
            return real(root, *args, timeout=timeout)
        return mock.patch.object(retention, "launch_script", launch)

    def test_an_interrupt_stops_and_reports(self):
        out = self.go(patches=[self.interrupt_at("remove:item-01")])
        self.assertEqual(out.code, 1)
        self.assertIn("  2. item-01: stopped at verify: interrupted", out.out)
        self.assertIn("  3. item-02: not attempted", out.out)
        self.assertIn("stopped after 1 of 3 items", out.out)

    def test_a_policy_changed_during_the_run_stops(self):
        real = rp.load
        count = []

        def load(target):
            count.append(1)
            if len(count) >= 3:   # the preflight, item 1, then item 2
                return rp.PolicyState(rp.CHANGED)
            return real(target)
        out = self.go(patches=[mock.patch.object(rp, "load", load)])
        self.assert_stopped_after(out, full_run("item-00"))
        self.assertIn("the policy changed", out.out + out.err)
        self.assertIn("  3. item-02: not attempted", out.out)

    def test_an_interrupt_while_reading_the_policy_claims_nothing(self):
        real = rp.load
        count = []

        def load(target):
            count.append(1)
            if len(count) >= 3:   # the preflight, item 1, then item 2
                raise KeyboardInterrupt
            return real(target)
        out = self.go(patches=[mock.patch.object(rp, "load", load)])
        self.assert_stopped_after(out, full_run("item-00"))
        self.assertIn("  2. item-01: stopped before any call for this item: interrupted", out.out)
        self.assertIn("item-01 was not touched", out.out)
        self.assertNotIn("None", out.out + out.err)
        self.assertNotIn("archived and verified", out.out)
        self.assertNotIn("policy changed", out.out + out.err)

    def test_a_step_one_stop_claims_not_archived_only_for_a_parsed_engine_refusal(self):
        timeout = [mock.patch.object(rr, "CALL_TIMEOUT_SECONDS", 1)]
        unexpected = {"kind": "retention-archive", "work_item_id": "other",
                      "result": {"archived": True}}
        cases = (
            ("timeout", {"archive --apply:item-00": {"sleep": 30}}, timeout),
            ("interrupt", {}, [self.interrupt_at("archive --apply:item-00")]),
            ("not json", {"archive --apply:item-00": {"stdout": "not json"}}, []),
            ("unexpected json", {"archive --apply:item-00": {"stdout": unexpected}}, []),
            ("unparsed exit", {"archive --apply:item-00": {"exit": 3, "stdout": ""}}, []),
        )
        for label, scenario, patches in cases:
            with self.subTest(label=label):
                out = self.go(scenario, patches=patches)
                self.assertEqual(out.code, 1, out.out + out.err)
                self.assertNotIn("was not archived", out.out)
                self.assertIn("item-00 may or may not be archived (the next preview shows "
                              "which) and its folder is untouched", out.out)
        out = self.go({"archive --apply:item-00": refusal("place_failed", "nope")})
        self.assertIn("item-00 was not archived and its folder is untouched", out.out)
        self.assertNotIn("may or may not", out.out)

    def test_a_script_that_cannot_start_was_not_archived(self):
        real = retention.launch_script

        def launch(root, *args, timeout):
            if args[0] == "archive":
                raise OSError("no exec")
            return real(root, *args, timeout=timeout)
        out = self.go(patches=[mock.patch.object(retention, "launch_script", launch)])
        self.assertIn("item-00 was not archived and its folder is untouched", out.out)

    def archive_stop(self, spec):
        """Run with `spec` as the archive step's answer; return the output after
        asserting that the stop never reached `verify` or `remove`."""
        before = tree_hash(self.repo)
        out = self.go({"archive --apply:item-00": spec})
        self.assertEqual(out.code, 1, out.out + out.err)
        self.assertEqual(self.keys(), ["archive --apply:item-00"])
        self.assertEqual(tree_hash(self.repo), before)
        self.assertIn("and its folder is untouched", out.out)
        return out

    def test_an_unsettled_undo_may_or_may_not_be_archived(self):
        spec = refusal("place_failed", "nope")
        spec["stderr"] = f"{rr.UNDO_WARNING}: x.partial\n" + spec["stderr"]
        out = self.archive_stop(spec)
        self.assertIn("item-00 may or may not be archived (the engine's undo could not "
                      "remove everything it created; the next preview shows which) and its "
                      "folder is untouched", out.out)
        self.assertNotIn("was not archived", out.out)

    def test_already_archived_says_this_run_did_not_create_one(self):
        out = self.archive_stop(refusal("already_archived", "an archive exists"))
        self.assertIn("this run did not create an archive for item-00 (one already exists) "
                      "and its folder is untouched", out.out)
        self.assertNotIn("was not archived", out.out)
        self.assertNotIn("may or may not", out.out)

    def test_already_archived_wins_over_an_undo_warning(self):
        spec = refusal("already_archived", "an archive exists")
        spec["stderr"] = f"{rr.UNDO_WARNING}: x.partial\n" + spec["stderr"]
        out = self.archive_stop(spec)
        self.assertIn("this run did not create an archive for item-00 (one already exists)",
                      out.out)
        self.assertNotIn("may or may not", out.out)

    def test_an_archive_step_stop_never_reaches_remove(self):
        warned = refusal("place_failed", "nope")
        warned["stderr"] = f"{rr.UNDO_WARNING}: x\n" + warned["stderr"]
        for label, spec in (("plain", refusal("place_failed", "nope")), ("warned", warned),
                            ("already", refusal("already_archived", "exists"))):
            with self.subTest(label=label):
                self.archive_stop(spec)

    def test_the_undo_warning_is_read_from_stderr_only(self):
        spec = refusal("place_failed", "nope")
        spec["stdout"] = f"{rr.UNDO_WARNING}: x\n"
        out = self.archive_stop(spec)
        self.assertIn("item-00 was not archived and its folder is untouched", out.out)

    def test_a_verify_stop_claims_no_archive(self):
        rep = tc.oldest_first(*(tc.entry(f"item-{n:02d}", mib=2, archive=(n == 0))
                                for n in range(12)))
        out = self.go({"remove:item-00": refusal("not_archived", "no index line")}, rep=rep)
        self.assertEqual(out.code, 1)
        self.assertNotIn("has an archive", out.out)
        self.assertIn("not_archived", out.out)
        self.assertIn("item-00's folder is untouched", out.out)

    def test_a_step_three_timeout_never_claims_the_folder_untouched(self):
        patches = [mock.patch.object(rr, "CALL_TIMEOUT_SECONDS", 1)]
        out = self.go({"remove --apply:item-00": {"sleep": 30}}, patches=patches)
        self.assertEqual(out.code, 1)
        self.assertNotIn("untouched", out.out)
        self.assertIn("state is unknown and may be partly removed", out.out)
        self.assertIn("remove item-00 --apply", out.out)

    def test_a_step_three_interrupt_never_claims_the_folder_untouched(self):
        out = self.go(patches=[self.interrupt_at("remove --apply:item-00")])
        self.assertNotIn("untouched", out.out)
        self.assertIn("state is unknown and may be partly removed", out.out)

    def test_a_step_three_engine_refusal_quotes_the_engine_and_never_claims_untouched(self):
        out = self.go({"remove --apply:item-00": refusal("folder_changed", "a file changed",
                                                          "look in .removing")})
        self.assertNotIn("untouched", out.out)
        self.assertIn("folder_changed", out.out)
        self.assertIn("next step (the engine's): look in .removing", out.out)
        self.assertIn("where its folder is: see the engine's message", out.out)

    def test_cross_device_stops_at_verification_and_names_the_cause(self):
        out = self.go({"remove:item-00": refusal("cross_device", "the store is on another file "
                                                 "system", "remove it by hand with --archive-root")})
        self.assert_stopped_after(out, ["archive --apply:item-00", "remove:item-00"])
        self.assertIn("cross_device", out.out)
        self.assertIn("remove it by hand with --archive-root", out.out)
        self.assertIn("folder is untouched", out.out)


class TestNeverPrune(RunBase):
    def test_no_scenario_issues_prune_or_a_store_option(self):
        scenarios = [{}, {"remove:item-00": refusal("archive_mismatch", "x")},
                     {"archive --apply:item-01": {"stdout": "no"}}]
        for scenario in scenarios:
            self.go(scenario)
            for call in self.script_calls():
                argv = call["argv"][1:]
                with self.subTest(argv=argv):
                    self.assertIn(argv[0], ("report", "archive", "remove"))
                    for word in ("prune", "--archive-root", "--ttl-days"):
                        self.assertNotIn(word, argv)
                    self.assertEqual(argv[-2], "--repo-root")
                    self.assertEqual(argv[-1], str(self.repo.resolve()))

    def test_the_closed_argv_forms(self):
        self.assertEqual(rr.argv_for(rr.ARCHIVE, "a", "/r"),
                         ("archive", "a", "--apply", "--json", "--repo-root", "/r"))
        self.assertEqual(rr.argv_for(rr.VERIFY, "a", "/r"),
                         ("remove", "a", "--json", "--repo-root", "/r"))
        self.assertEqual(rr.argv_for(rr.REMOVE, "a", "/r"),
                         ("remove", "a", "--apply", "--json", "--repo-root", "/r"))
        with self.assertRaises(ValueError):
            rr.argv_for("prune", "a", "/r")

    def test_the_module_has_no_prune_verb(self):
        source = (Path(rr.__file__)).read_text()
        for line in source.splitlines():
            if "prune" in line.lower():
                self.assertRegex(line.lower(), r"never|no prune|`prune`.*no form|prune was not run",
                                 line)


class TestRefusalsWriteNothing(RunBase):
    """Every refusal, with a valid-looking sentence, writes nothing: no engine write
    verb, the same repository tree, no archive store and an empty scratch TMPDIR."""

    def scratch(self):
        home, tmp = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return home, tmp

    def refuse(self, cause, *, rep=None, confirm=True, patches=()):
        """Run with a scratch HOME and TMPDIR and assert that nothing was written."""
        home, tmp = self.scratch()
        self.stale_index()
        before = tree_hash(self.repo)
        out = self.go(confirm=self.sentence() if confirm is True else confirm, rep=rep,
                      patches=[*patches, mock.patch.object(tempfile, "tempdir", None)],
                      HOME=str(home), TMPDIR=str(tmp))   # tempdir is cached: reset it
        self.assertEqual((out.code, out.out), (2, ""), out.err)
        self.assertIn(cause, out.err)
        self.assertEqual(self.keys(), [])
        self.assertEqual(tree_hash(self.repo), before)
        self.assertFalse((home / ".local" / "share" / "workflow-archive").exists())
        self.assertEqual(list(tmp.iterdir()), [])
        return out

    def test_every_preflight_refusal_with_a_sentence(self):
        policy, record = rp.policy_path(self.repo), rp.record_path(self.repo)
        installation = self.repo / ".workflow-manager" / "installation.json"
        modified = mock.patch.object(cli, "_installed_script_state",
                                     return_value=ra.SCRIPT_MODIFIED)

        def not_adopted():
            record.unlink()

        def mode():
            self.adopt({**tc.POLICY, "mode": "notify"})
            self.commit(self.repo, "notify")

        def uncommitted():
            git(self.repo, "rm", "-q", "--cached", ".workflow-manager/retention-policy.json")
            git(self.repo, "commit", "-q", "-m", "untrack")

        def dirty():
            (self.repo / "CLAUDE.md").write_text("dirty\n")

        def old_release():
            data = json.loads(installation.read_text())
            data["workflow_version"] = "2.25.4"
            installation.write_text(json.dumps(data, indent=2) + "\n")
            self.commit(self.repo, "old")

        def missing_script():
            (self.repo / SCRIPT).unlink()
            git(self.repo, "commit", "-q", "-am", "no script")

        incomplete = dict(self.rep, complete=False)
        interrupted = dict(self.rep, removing=["half-gone"])
        cases = [
            ("policy not adopted", not_adopted, {}, f"retention policy: {rp.NOT_ADOPTED}"),
            ("mode", mode, {}, "the adopted mode is notify"),
            ("uncommitted policy file", uncommitted, {},
             ".workflow-manager/retention-policy.json is not committed at HEAD"),
            ("dirty tree", dirty, {}, "a tracked file is changed"),
            ("old release", old_release, {}, "older than 2.25.5"),
            ("modified script", lambda: None, {"patches": [modified]}, ra.CAUSE_MODIFIED),
            ("incomplete report", lambda: None, {"rep": incomplete}, ra.CAUSE_INCOMPLETE),
            ("interrupted removal", lambda: None, {"rep": interrupted},
             "a removal was interrupted"),
            ("missing script", missing_script, {},
             "the repository has no scripts/workflow_retention.py"),
        ]
        for label, setup, kwargs, cause in cases:
            with self.subTest(label=label):
                head = git(self.repo, "rev-parse", "HEAD").stdout.strip()
                saved = {p: p.read_bytes() for p in (policy, record, installation)}
                try:
                    setup()
                    self.refuse(cause, **kwargs)
                finally:
                    git(self.repo, "reset", "-q", "--hard", head)
                    for path, data in saved.items():
                        path.write_bytes(data)

    def test_a_wrong_sentence_writes_nothing(self):
        for text in ("no", "", "I confirm cleanup of plan 0123456789ab"):
            with self.subTest(text=text):
                self.refuse("does not hold the sentence", confirm=text)


class TestReport(RunBase):
    def head(self):
        plan = self.plan()
        return (f"retention cleanup: running plan {rc.plan_digest(plan)[:12]} (mode both, "
                f"policy {plan.policy_digest[:12]}), 3 items\n")

    def test_a_clean_run(self):
        out = self.go()
        self.assertEqual(out.out, self.head() + (
            "  1. item-00: archived 2 MiB, verified, removed\n"
            "  2. item-01: archived 2 MiB, verified, removed\n"
            "  3. item-02: archived 2 MiB, verified, removed\n"
            "retention cleanup: done, 3 of 3 items archived and removed; Git is unchanged "
            "(the review folders were untracked); prune was not run\n"))

    def test_a_stopped_run_says_what_was_done_and_not_done(self):
        out = self.go({"remove:item-01": refusal(
            "archive_mismatch", "the review folder differs from its archive in 1 entry: "
            "REVIEW.md (differs)", "restore it")})
        self.assertEqual(out.out, self.head() + (
            "  1. item-00: archived 2 MiB, verified, removed\n"
            "  2. item-01: stopped at verify (archive_mismatch): the review folder differs from "
            "its archive in 1 entry: REVIEW.md (differs)\n"
            "     next step (the engine's): restore it\n"
            "  3. item-02: not attempted\n"
            "retention cleanup: stopped after 1 of 3 items; item-01's folder is "
            "untouched; nothing was committed or needs committing\n"))
        self.assertTrue(out.err.startswith("error: retention cleanup: item-01: stopped at verify"))
        self.assertIn("next: restore it", out.err)

    def policy_at_item_one(self, kind):
        """Item 1's policy read (the second `load`: the preflight's was the first)."""
        real = rp.load
        count = []

        def load(target):
            count.append(1)
            if len(count) >= 2:
                if kind == "interrupt":
                    raise KeyboardInterrupt
                return rp.PolicyState(rp.CHANGED)
            return real(target)
        return mock.patch.object(rp, "load", load)

    def test_exit_codes(self):
        self.assertEqual(self.go().code, 0)
        self.assertEqual(self.go({"archive --apply:item-00": refusal("x_y", "z")}).code, 1)
        self.assertEqual(self.go(confirm="no").code, 2)
        self.assertEqual(self.go(confirm=None).code, 0)
        # exit 2: stopped before the first per-item call (only the preflight's report ran)
        for kind in ("changed", "interrupt"):
            with self.subTest(before_item_one=kind):
                before = tree_hash(self.repo)
                out = self.go(patches=[self.policy_at_item_one(kind)])
                self.assertEqual(out.code, 2, out.out + out.err)
                self.assertEqual(self.keys(), [])
                self.assertEqual(tree_hash(self.repo), before)
        # exit 1: the first per-item call was attempted, even if its script never started
        out = self.go({"archive --apply:item-00": refusal("x_y", "z")})
        self.assertEqual((out.code, self.keys()), (1, ["archive --apply:item-00"]))
        real = retention.launch_script

        def cannot_start(root, *args, timeout):
            if args[0] == "report":
                return real(root, *args, timeout=timeout)
            raise OSError("no such interpreter")
        out = self.go(patches=[mock.patch.object(retention, "launch_script", cannot_start)])
        self.assertEqual(out.code, 1, out.out + out.err)
        self.assertIn("the script could not be started", out.out)
        # exit 1: a remove-only first item stopped at its verification (the dry run)
        rep = tc.oldest_first(*(tc.entry(f"item-{n:02d}", mib=2, archive=(n == 0))
                                for n in range(12)))
        out = self.go({"remove:item-00": refusal("archive_mismatch", "differs")}, rep=rep)
        self.assertEqual((out.code, self.keys()), (1, ["remove:item-00"]))

    def test_the_run_is_flushed_as_it_goes(self):
        events = []

        class Recorder(io.StringIO):
            def write(self, text):
                events.append(("write", text))
                return super().write(text)

            def flush(self):
                events.append(("flush", None))

        self.scenario.write_text("{}")
        with mock.patch.dict(os.environ, self.env(STUB_REPORT=str(self.put_report(self.rep)),
                                                  STUB_SCENARIO=str(self.scenario)), clear=True), \
                mock.patch.object(sys, "stdout", Recorder()):
            rr.run(self.repo, self.plan())
        lines = [i for i, (kind, text) in enumerate(events) if kind == "write" and text == "\n"]
        self.assertGreaterEqual(len(lines), 5)
        for index in lines:
            self.assertEqual(events[index + 1], ("flush", None), events[index:index + 2])

    def test_nothing_is_committed(self):
        self.stale_index()
        head = git(self.repo, "rev-parse", "HEAD").stdout
        before = tree_hash(self.repo)
        self.assertEqual(self.go().code, 0)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout, head)
        self.assertEqual(tree_hash(self.repo), before)


class TestEndToEnd(unittest.TestCase):
    """The release's own script through its own seams, in a scratch repository."""

    DRIVER = r"""
import json, sys
sys.path.insert(0, "scripts")
import workflow_retention as wr
def resolve(repo_root):
    return {"path": "/usr/bin/gh", "sha256": "0" * 64}
def run(argv, timeout):
    commit = argv[argv.index("--search") + 1]
    repo = argv[argv.index("--repo") + 1]
    return json.dumps([{"number": 7, "url": "https://github.com/" + repo + "/pull/7",
                        "state": "MERGED", "headRefOid": commit}])
sys.exit(wr.main(sys.argv[1:], run=run, resolve=resolve))
"""

    @classmethod
    def setUpClass(cls):
        if shutil.which("zstd") is None:
            raise unittest.SkipTest("zstd is not on PATH: the real engine cannot archive")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pristine = build_bootstrapped_repo(support.release(NEWEST_RELEASE),
                                               Path(cls._tmp.name) / "pristine")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_tmp"):
            cls._tmp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.home = self.work / "home"
        self.home.mkdir()
        self.repo = self.work / "r"
        shutil.copytree(self.pristine, self.repo, symlinks=True)
        git(self.repo, "remote", "add", "origin", "https://github.com/octo/example.git")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.com")
        state = self.repo / "docs" / "ai-workflow" / "WORKFLOW_STATE.json"
        items = {}
        for n in range(1, 8):
            items[f"item-{n:02d}"] = {
                "phase": "MILESTONE_COMPLETE", "work_item_type": "process",
                "governing_workflow_version": "2.2",
                "reviewed_implementation_head": f"{n:040x}",
                "last_transition": f"2026-10-{n:02d}T00:00:00Z"}
            folder = self.repo / ".ai-review" / f"item-{n:02d}"
            folder.mkdir(parents=True)
            (folder / "REVIEW.md").write_text(f"review {n}\n")
        state.write_text(json.dumps({"schema_version": 1, "active_work_item_id": None,
                                     "work_item_type": None, "work_items": items}, indent=2) + "\n")
        policy = {"schema_version": 1, "mode": "cleanup", "thresholds": {"finished_items": 3}}
        path = rp.policy_path(self.repo)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(policy))
        rp.apply(self.repo, rp.usable_policy(self.repo), rp.sentence(rp.digest_of(policy)))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "state")

    def launcher(self):
        driver = self.DRIVER
        real_home = self.home

        def launch(root, *args, timeout):
            env = {**os.environ, "HOME": str(real_home)}
            proc = subprocess.run([sys.executable, "-I", "-B", "-c", driver, *args],
                                  cwd=str(root), capture_output=True, timeout=timeout, env=env)
            return proc.returncode, proc.stdout, proc.stderr
        return launch

    def invoke(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(retention, "launch_script", self.launcher()), \
                mock.patch.object(cli, "_installed_script_state", return_value=ra.SCRIPT_OK), \
                mock.patch.dict(os.environ, support.cli_env(), clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--release-version", NEWEST_RELEASE, COMMAND, str(self.repo), *extra])
        return tc.Out(code, out.getvalue(), err.getvalue())

    def test_the_real_engine_archives_verifies_and_removes(self):
        preview = self.invoke()
        self.assertEqual(preview.code, 0, preview.err)
        sentence = next(line for line in preview.out.splitlines() if "--confirm" in line)
        sentence = sentence.split('"')[1]
        head = git(self.repo, "rev-parse", "HEAD").stdout
        status = git(self.repo, "status", "--porcelain").stdout
        out = self.invoke("--confirm", sentence)
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertIn("retention cleanup: done, ", out.out)
        store = self.home / ".local" / "share" / "workflow-archive" / "example"
        removed = [line for line in out.out.splitlines() if line.endswith("removed")]
        self.assertTrue(removed, out.out)
        for line in removed:
            item = line.split(".")[1].split(":")[0].strip()
            self.assertTrue((store / f"{item}.tar.zst").is_file())
            self.assertFalse((self.repo / ".ai-review" / item).exists())
        self.assertIn("index.jsonl", {p.name for p in store.iterdir()})
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout, head)
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, status)
        again = self.invoke()
        self.assertEqual(again.code, 0, again.err)
        self.assertIn("retention cleanup: nothing to do", again.out)
        for line in removed:
            self.assertNotIn(line.split(":")[0].split(". ")[1], again.out)


class TestDocsSayExitCodes(unittest.TestCase):
    """The exit-code criterion is the code's: the first per-item call was attempted."""

    def squashed(self, name):
        return " ".join((REPO_ROOT / "docs" / name).read_text().split())

    def test_the_pages_state_the_first_per_item_call_criterion(self):
        for name in ("retention.md", "exit-codes.md"):
            with self.subTest(page=name):
                text = self.squashed(name)
                self.assertIn("after its first per-item call (`archive --apply`, the "
                              "verification or `remove --apply`) was attempted, even if its "
                              "script could not be started", text)
                self.assertNotIn("after an engine call started", text)
        self.assertIn("or stopped before that first call", self.squashed("retention.md"))
        self.assertIn("or the run stopped before that first call", self.squashed("exit-codes.md"))
        self.assertIn("or the policy changed before a later item", self.squashed("exit-codes.md"))
        self.assertIn("2 when it refuses or stops before that first call",
                      self.squashed("retention.md"))

    def test_the_old_wording_is_nowhere(self):
        for path in (REPO_ROOT / "src" / "workflow_manager" / "retention_run.py",
                     REPO_ROOT / "src" / "workflow_manager" / "cli.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("after an engine call started", " ".join(path.read_text().split()))

    def test_the_loose_criterion_is_nowhere(self):
        for path in (REPO_ROOT / "docs" / "retention.md",
                     REPO_ROOT / "src" / "workflow_manager" / "cli.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("stopped after it started", " ".join(path.read_text().split()))


if __name__ == "__main__":
    unittest.main()
