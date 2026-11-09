#!/usr/bin/env python3
"""The retention alert of `verify` and `doctor`.

Hermetic: the stub script of `test_retention_status` in a scratch managed
repository, no network. The stub-based cases run `cli.main` in-process with the
two script-state seams patched to `SCRIPT_OK` (a stub is never the release's
script); `TestScriptState` tests the real rule in subprocesses against a release
of the cache that ships the script, with nothing patched. No test writes into
this repository.
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
from support import NEWEST_RELEASE, REPO_ROOT, TESTED_VERSIONS, pinned_env

import test_retention_status as rs
from frozen_runs import build_bootstrapped_repo
from test_operator_ux import tree_hash
from workflow_manager import cli, retention, retention_alert as ra, retention_policy as rp

SCRIPT = rs.SCRIPT
POLICY = {"schema_version": 1, "mode": "notify",
          "thresholds": {"finished_items": 2, "finished_folder_mib": 1, "archives": 3,
                         "prunable_archives": 2}}
MIB = 2**20


def state(mode="notify", thresholds=None, adopted=True):
    policy = {"schema_version": 1, "mode": mode,
              "thresholds": thresholds if thresholds is not None else {"finished_items": 3}}
    return rp.PolicyState(rp.ADOPTED if adopted else rp.CHANGED,
                          mode=mode if adopted else "off", policy=policy, digest="ab" * 32)


def entries(count, folder=True):
    return [rs.finished(f"item-{i}", folder=folder) for i in range(count)]


def sized(rep, **totals):
    rep["totals"].update(totals)
    return rep


def status_of(results, key):
    return next(r for r in results if r.key == key)


class TestEvaluate(unittest.TestCase):
    def test_finished_items_at_the_limit_one_below_and_above(self):
        for count, expected in ((2, ra.WITHIN), (3, ra.REACHED), (4, ra.REACHED)):
            with self.subTest(count=count):
                results = ra.evaluate(state(), rs.report(*entries(count)))
                self.assertEqual([(r.status, r.value) for r in results], [(expected, count)])

    def test_archived_and_removed_items_do_not_count_toward_finished_items(self):
        rep = rs.report(*entries(10, folder=False))
        self.assertEqual(rep["totals"]["finished"], 10)
        results = ra.evaluate(state(), rep)
        self.assertEqual([(r.status, r.value) for r in results], [(ra.WITHIN, 0)])
        mixed = rs.report(*entries(10, folder=False), *entries(3))
        self.assertEqual(ra.evaluate(state(), mixed)[0].status, ra.REACHED)

    def test_the_folder_limit_is_in_mib(self):
        st = state(thresholds={"finished_folder_mib": 500})
        for size, expected in ((500 * MIB, ra.REACHED), (500 * MIB - 1, ra.WITHIN),
                               (500 * MIB + 1, ra.REACHED)):
            with self.subTest(size=size):
                rep = sized(rs.report(), finished_folder_bytes=size)
                result = ra.evaluate(st, rep)[0]
                self.assertEqual((result.status, result.value, result.limit),
                                 (expected, size, 500))

    def test_archives_and_prunable_at_and_below_the_limit(self):
        for key, field in (("archives", "archives"), ("prunable_archives", "prunable")):
            for number, expected in ((4, ra.WITHIN), (5, ra.REACHED), (6, ra.REACHED)):
                with self.subTest(key=key, number=number):
                    rep = sized(rs.report(), **{field: number})
                    self.assertEqual(ra.evaluate(state(thresholds={key: 5}), rep)[0].status,
                                     expected)

    def test_an_incomplete_report_below_the_limit_is_unknown_never_within(self):
        for incomplete in (
            {"complete": False},
            {"read_errors": [{"path": "/x", "error": "denied"}]},
            {"not_finished": [{"work_item_id": "a", "reason": "query_failed:timeout"}]},
        ):
            with self.subTest(incomplete=incomplete):
                rep = rs.report(*entries(2), **incomplete)
                result = ra.evaluate(state(), rep)[0]
                self.assertEqual((result.status, result.lower_bound), (ra.UNKNOWN, True))

    def test_an_incomplete_report_at_or_above_the_limit_is_reached(self):
        rep = rs.report(*entries(3), complete=False)
        result = ra.evaluate(state(), rep)[0]
        self.assertEqual((result.status, result.lower_bound), (ra.REACHED, True))

    def test_a_complete_report_is_not_a_lower_bound(self):
        self.assertFalse(ra.evaluate(state(), rs.report(*entries(3)))[0].lower_bound)

    def test_a_threshold_the_policy_omits_is_not_evaluated(self):
        results = ra.evaluate(state(thresholds={"archives": 1, "finished_items": 1}),
                              sized(rs.report(*entries(5)), archives=9, prunable=9))
        self.assertEqual([r.key for r in results], ["finished_items", "archives"])

    def test_no_report_makes_every_result_unknown(self):
        results = ra.evaluate(state(thresholds={"archives": 1, "finished_items": 1}), None)
        self.assertEqual([(r.status, r.value) for r in results],
                         [(ra.UNKNOWN, None), (ra.UNKNOWN, None)])

    def test_a_policy_that_is_not_alerting_evaluates_nothing(self):
        rep = sized(rs.report(*entries(9)), archives=99)
        for mode in ("off", "cleanup"):
            with self.subTest(mode=mode):
                self.assertEqual(ra.evaluate(state(mode=mode), rep), [])
        self.assertEqual(ra.evaluate(state(adopted=False), rep), [])
        self.assertEqual(ra.evaluate(state(mode="both"), rep)[0].status, ra.REACHED)


class Base(rs.Scratch):
    """A scratch managed repository (record at 2.22.0) with the stub installed
    and, unless a test says otherwise, `POLICY` adopted."""

    def setUp(self):
        super().setUp()
        self.install_stub()

    def adopt(self, policy=POLICY):
        path = rp.policy_path(self.repo)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(policy))
        rp.apply(self.repo, rp.usable_policy(self.repo), rp.sentence(rp.digest_of(policy)))

    def call(self, command, rep=None, *, flag=False, seam=ra.SCRIPT_OK, extra=(), **env):
        """`cli.main` in-process with both seams patched: `(code, out, err, seam calls)`."""
        if rep is not None:
            env["STUB_REPORT"] = str(self.put_report(rep))
        args = ["--release-version", support.PINNED_NEWEST, command, *extra]
        if flag:
            args.append("--retention")
        args.append(str(self.repo))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env(**env), clear=True), \
                mock.patch.object(ra, "script_state", return_value=seam) as verify_seam, \
                mock.patch.object(cli, "_installed_script_state", return_value=seam) as doctor_seam, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(args)
            except SystemExit as exit_:
                code = exit_.code
        return Result(code, out.getvalue(), err.getvalue(),
                      verify_seam.call_count + doctor_seam.call_count)

    def drop_policy(self):
        """Remove the policy file and its record (never the installation record)."""
        for path in (rp.policy_path(self.repo), rp.record_path(self.repo)):
            path.unlink(missing_ok=True)

    def script_calls(self) -> list[dict]:
        if not self.marker.exists():
            return []
        return [json.loads(line) for line in self.marker.read_text().splitlines()]

    def alert_block(self, out: str) -> list[str]:
        lines = out.splitlines()
        at = [i for i, line in enumerate(lines) if line.startswith("retention alert:")]
        self.assertEqual(len(at), 1, out)
        block = [lines[at[0]]]
        for line in lines[at[0] + 1:]:
            if not line.startswith("  "):
                break
            block.append(line)
        return block


@dataclass
class Result:
    code: int
    out: str
    err: str
    seam_calls: int


REACHED_TWO = lambda: sized(rs.report(*entries(3)), archives=1)  # noqa: E731


class TestGate(Base):
    def test_notify_and_both_run_the_script_once(self):
        for mode in ("notify", "both"):
            for command in ("verify", "doctor"):
                with self.subTest(mode=mode, command=command):
                    self.marker.unlink(missing_ok=True)
                    self.adopt(dict(POLICY, mode=mode))
                    got = self.call(command, REACHED_TWO())
                    self.assertEqual(got.seam_calls, 1)
                    self.assertEqual(len(self.script_calls()), 1)
                    self.assertIn("retention alert:", got.out)

    def test_off_and_cleanup_print_nothing_and_start_nothing(self):
        base = {c: self.call(c, REACHED_TWO()).out for c in ("verify", "doctor")}
        for mode in ("off", "cleanup"):
            for command in ("verify", "doctor"):
                with self.subTest(mode=mode, command=command):
                    self.marker.unlink(missing_ok=True)
                    self.adopt(dict(POLICY, mode=mode))
                    got = self.call(command, REACHED_TWO())
                    self.assertEqual(got.seam_calls, 0)
                    self.assertEqual(self.script_calls(), [])
                    self.assertNotIn("retention alert", got.out)
                    self.assertEqual(got.out, base[command])

    def test_every_state_but_adopted_is_silent_and_never_asks_about_the_script(self):
        base = {c: self.call(c, REACHED_TWO()).out for c in ("verify", "doctor")}
        record = rp.record_path(self.repo)
        states = {}

        def put(policy):
            path = rp.policy_path(self.repo)
            path.parent.mkdir(exist_ok=True)
            path.write_text(policy if isinstance(policy, str) else json.dumps(policy))

        for name, prepare in (
            (rp.NOT_ADOPTED, lambda: put(POLICY)),
            (rp.INVALID, lambda: put("{")),
            (rp.RECORD_INVALID, lambda: (put(POLICY), record.write_text("{}"))),
            (rp.CHANGED, lambda: (self.adopt(), put(dict(POLICY, mode="both")))),
            (rp.FILE_MISSING, lambda: (self.adopt(), rp.policy_path(self.repo).unlink())),
        ):
            self.drop_policy()
            prepare()
            self.assertEqual(rp.load(self.repo).state, name)
            for command in ("verify", "doctor"):
                with self.subTest(state=name, command=command):
                    self.marker.unlink(missing_ok=True)
                    got = self.call(command, REACHED_TWO())
                    self.assertEqual(got.seam_calls, 0)
                    self.assertEqual(self.script_calls(), [])
                    self.assertNotIn("retention alert", got.out)

    def test_an_absent_policy_is_byte_identical_and_asks_nothing(self):
        for command in ("verify", "doctor"):
            got = self.call(command, REACHED_TWO())
            self.assertEqual(got.seam_calls, 0)
            self.assertEqual(self.script_calls(), [])

    def test_the_script_state_callable_is_not_called_for_a_non_alerting_policy(self):
        counter = mock.Mock(return_value=ra.SCRIPT_OK)
        self.assertEqual(ra.alert_lines(self.repo, "2.22.0", counter), [])
        counter.assert_not_called()
        self.adopt(dict(POLICY, mode="cleanup"))
        self.assertEqual(ra.alert_lines(self.repo, "2.22.0", counter), [])
        counter.assert_not_called()


class TestOutput(Base):
    def setUp(self):
        super().setUp()
        self.adopt()

    def test_one_reached_threshold_prints_the_exact_block(self):
        digest = rp.load(self.repo).digest[:12]
        got = self.call("doctor", sized(rs.report(*entries(3)), archives=1))
        self.assertEqual(got.seam_calls, 1)   # the patched seam was reached (in-process)
        self.assertEqual(self.alert_block(got.out)[:2], [
            f"retention alert: 1 of 4 thresholds reached (mode notify, policy {digest})",
            "  finished items: 3, limit 2: reached"])
        self.assertTrue(self.alert_block(got.out)[2].startswith(
            "  next: in the repository, run `python3 -I scripts/workflow_retention.py archive "))

    def test_several_reached_and_the_folder_in_mib(self):
        rep = sized(rs.report(*entries(3)), finished_folder_bytes=5 * MIB + 7, archives=3,
                    prunable=0)
        block = self.alert_block(self.call("doctor", rep).out)
        self.assertIn("  finished items: 3, limit 2: reached", block)
        self.assertIn("  finished folders: 5 MiB, limit 1 MiB: reached", block)
        self.assertIn("  archives: 3, limit 3: reached", block)
        self.assertNotIn("prunable", "\n".join(block[:-1]))
        self.assertTrue(block[0].startswith("retention alert: 3 of 4 thresholds reached"))

    def test_a_lower_bound_reads_at_least_and_an_unknown_one_says_so(self):
        rep = sized(rs.report(*entries(3), complete=False), archives=1)
        block = self.alert_block(self.call("doctor", rep).out)
        self.assertIn("  finished items: at least 3, limit 2: reached", block)
        self.assertIn("  archives: at least 1, limit 3: not known (the report is incomplete)",
                      block)

    def test_a_folder_below_a_mib_never_prints_as_the_limit(self):
        rep = sized(rs.report(*entries(3)), finished_folder_bytes=MIB - 1)
        self.assertNotIn("finished folders", self.call("doctor", rep).out)
        rep = sized(rs.report(*entries(3), complete=False), finished_folder_bytes=MIB - 1)
        self.assertIn("finished folders: at least 0 MiB, limit 1 MiB: not known",
                      self.call("doctor", rep).out)

    def test_all_within_prints_nothing_and_equals_the_run_without_a_policy(self):
        rep = sized(rs.report(*entries(1)), archives=1)
        for command in ("verify", "doctor"):
            with self.subTest(command=command):
                with_policy = self.call(command, rep)
                self.drop_policy()
                without = self.call(command, rep)
                self.assertEqual(with_policy.out, without.out)
                self.assertNotIn("retention alert", with_policy.out)
                self.adopt()

    def test_verify_clean_prints_the_alert_after_the_result_line(self):
        self.set_version(support.PINNED_NEWEST)
        got = self.call("verify", REACHED_TWO())
        lines = got.out.splitlines()
        self.assertEqual(got.code, 0, got.out)
        self.assertIn("installation matches workflow", lines[0])
        self.assertTrue(lines[1].startswith("retention alert:"), got.out)

    def test_verify_with_problems_keeps_one_unindented_final_next_line(self):
        got = self.call("verify", REACHED_TWO())
        self.assertEqual(got.code, 1, got.out)
        lines = got.out.splitlines()
        self.assertIn("problem(s)", lines[0])
        unindented = [l for l in lines if l.startswith("next: ")]
        self.assertEqual(len(unindented), 1, got.out)
        self.assertTrue(lines[-1].startswith("next: "), got.out)
        alert = [i for i, l in enumerate(lines) if l.startswith("retention alert:")]
        self.assertEqual(len(alert), 1)
        self.assertLess(alert[0], len(lines) - 1)
        for line in lines[alert[0] + 1:-1]:
            self.assertTrue(line.startswith("  "), line)

    def test_doctor_with_the_option_makes_one_script_call(self):
        got = self.call("doctor", REACHED_TWO(), flag=True)
        self.assertEqual(len(self.script_calls()), 1)
        self.assertIn("retention (read-only", got.out)
        self.assertLess(got.out.index("retention (read-only"), got.out.index("retention alert:"))
        self.assertEqual(got.seam_calls, 1)

    def test_doctor_without_the_option_reached_the_evaluation(self):
        self.call("doctor", REACHED_TWO())
        calls = self.script_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["argv"][-4:-2], ["report", "--json"])

    def test_the_prune_line_and_the_alert_do_not_contradict(self):
        self.set_version("2.24.0")
        rep = sized(rs.report(*entries(1)), archives=2, prunable=2)
        got = self.call("doctor", rep, flag=True)
        self.assertNotIn("no command yet", got.out)
        self.assertIn("prunable archives: python3 -I scripts/workflow_retention.py prune ID "
                      "--apply removes one", got.out)
        self.assertIn("prune ID --apply` for each", got.out)

    def set_version(self, version):
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = version
        record.write_text(json.dumps(data, indent=2) + "\n")


class TestUnavailable(Base):
    def setUp(self):
        super().setUp()
        self.adopt()

    def one_line(self, out):
        block = self.alert_block(out)
        self.assertEqual(len(block), 2, out)
        self.assertTrue(block[0].startswith("retention alert: not evaluated: "), block)
        self.assertTrue(block[1].startswith("  next: "), block)
        return block

    def baseline_code(self, command, **kwargs):
        self.drop_policy()
        try:
            return self.call(command, **kwargs).code
        finally:
            self.adopt()

    def test_every_cause_prints_one_not_evaluated_line_and_keeps_the_exit_code(self):
        cases = {
            "no script": (lambda: (self.repo / SCRIPT).unlink(), {}, "no scripts/workflow_retention.py"),
            "refusing script": (None, {"STUB_MODE": "exit", "STUB_EXIT": "2",
                                       "STUB_STDERR": "error: no_origin: no origin\\nnext step: add origin"},
                                "no_origin: no origin"),
            "failing script": (None, {"STUB_MODE": "exit", "STUB_EXIT": "1"}, "status 1"),
            "malformed": (None, {"STUB_MODE": "raw"}, "not one JSON object"),
        }
        for name, (prepare, env, cause) in cases.items():
            for command in ("verify", "doctor"):
                with self.subTest(case=name, command=command):
                    self.install_stub()
                    if prepare:
                        prepare()
                    kwargs = dict(env)
                    rep = self.put_report("[1]") if name == "malformed" else None
                    if name == "malformed":
                        kwargs["STUB_REPORT"] = str(rep)
                    expected = self.baseline_code(command, **kwargs)
                    before = tree_hash(self.repo)
                    got = self.call(command, **kwargs)
                    self.assertEqual(got.code, expected)
                    self.assertIn(cause, self.one_line(got.out)[0])
                    self.assertEqual(tree_hash(self.repo), before)

    def test_a_timeout_refusal_is_one_line(self):
        refusal = retention.Outcome(refusal=retention.NotAvailable(
            "the report did not finish within 300 seconds", retention.STEP_RUN_DIRECTLY))
        with mock.patch.object(retention, "fetch", return_value=refusal):
            got = self.call("verify")
        block = self.one_line(got.out)
        self.assertIn("did not finish within 300 seconds", block[0])
        self.assertEqual(block[1], f"  next: {retention.STEP_RUN_DIRECTLY}")

    def test_an_incomplete_report_with_nothing_reached_is_not_evaluated(self):
        got = self.call("doctor", sized(rs.report(*entries(1), complete=False), archives=1))
        block = self.one_line(got.out)
        self.assertIn(ra.CAUSE_INCOMPLETE, block[0])
        self.assertEqual(block[1], f"  next: {retention.STEP_INCOMPLETE}")

    def test_an_evaluation_that_raises_prints_the_class_and_keeps_the_exit_code(self):
        expected = self.baseline_code("doctor", rep=REACHED_TWO())
        with mock.patch.object(ra, "evaluate", side_effect=KeyError("x")):
            got = self.call("doctor", REACHED_TWO())
        self.assertEqual(got.code, expected)
        self.assertIn("not evaluated: KeyError", self.one_line(got.out)[0])

    def test_a_script_state_that_raises_prints_the_class_and_keeps_the_exit_code(self):
        for command in ("verify", "doctor"):
            with self.subTest(command=command):
                expected = self.baseline_code(command, rep=REACHED_TWO())
                with mock.patch.object(ra, "script_state", side_effect=OSError("x")), \
                        mock.patch.object(cli, "_installed_script_state", side_effect=OSError("x")):
                    got = self.call_unpatched(command, REACHED_TWO())
                self.assertEqual(got.code, expected)
                self.assertIn("not evaluated: OSError", self.one_line(got.out)[0])
                self.assertEqual(self.script_calls(), [])

    def call_unpatched(self, command, rep):
        """`cli.main` with the caller's patches left in place (no seam patch)."""
        env = self.env(STUB_REPORT=str(self.put_report(rep)))
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--release-version", support.PINNED_NEWEST, command, str(self.repo)])
        return Result(code, out.getvalue(), "", 0)

    def test_a_modified_script_is_not_started(self):
        for command in ("verify", "doctor"):
            with self.subTest(command=command):
                self.marker.unlink(missing_ok=True)
                got = self.call(command, REACHED_TWO(), seam=ra.SCRIPT_MODIFIED)
                block = self.one_line(got.out)
                self.assertIn("does not match the release", block[0])
                self.assertEqual(block[1], f"  next: workflow-manager update {self.repo} --force")
                self.assertEqual(self.script_calls(), [])

    def test_doctor_with_the_option_runs_the_script_once_for_the_section_only(self):
        base = self.call("doctor", REACHED_TWO(), flag=True, seam=ra.SCRIPT_MODIFIED)
        self.assertEqual(len(self.script_calls()), 1)
        self.drop_policy()
        self.marker.unlink()
        plain = self.call("doctor", REACHED_TWO(), flag=True)
        self.assertEqual(len(self.script_calls()), 1)
        section = lambda out: out[out.index("retention (read-only"):].split("retention alert:")[0]  # noqa: E731
        self.assertIn("retention (read-only", plain.out)
        self.assertEqual(section(base.out).split("retention policy")[0].strip().splitlines()[-1:],
                         section(plain.out).strip().splitlines()[-1:])
        self.adopt()

    def test_an_installed_release_that_does_not_resolve_is_not_evaluated(self):
        got = self.call("doctor", REACHED_TWO(), seam=ra.SCRIPT_UNCHECKED)
        block = self.one_line(got.out)
        self.assertIn("the installed release cannot be checked", block[0])
        self.assertIn("WORKFLOW_MANAGER_RELEASE_SOURCE", block[1])
        self.assertEqual(self.script_calls(), [])

    def test_the_doctor_callable_checks_the_installed_release_read_only(self):
        with mock.patch.dict(os.environ, pinned_env(), clear=True):
            args = cli.build_parser().parse_args(["doctor", str(self.repo)])
            for installed in (7, "9.9.9"):
                with self.subTest(installed=installed):
                    destinations = cli._readonly_destinations(
                        args, installed if isinstance(installed, str) else None)
                    self.assertEqual(cli._installed_script_state(args, installed, destinations),
                                     ra.SCRIPT_UNCHECKED)
                    self.assertFalse((self.repo / ".workflow-manager" / "snapshots").exists())


class TestExitCodes(Base):
    def test_a_reached_threshold_changes_no_exit_code(self):
        for command in ("verify", "doctor"):
            with self.subTest(command=command):
                base = self.call(command, REACHED_TWO()).code
                self.adopt()
                got = self.call(command, REACHED_TWO())
                self.assertIn("retention alert: 1 of 4", got.out)
                self.assertEqual(got.code, base)
                self.drop_policy()

    def test_verify_stays_zero_on_a_clean_installation(self):
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = support.PINNED_NEWEST
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.adopt()
        self.assertEqual(self.call("verify", REACHED_TWO()).code, 0)


class TestNextStep(Base):
    def setUp(self):
        super().setUp()
        self.adopt()

    def step(self, rep, version="2.25.0", policy=POLICY):
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = version
        record.write_text(json.dumps(data, indent=2) + "\n")
        self.adopt(policy)
        block = self.alert_block(self.call("doctor", rep).out)
        return block[-1][len("  next: "):]

    def policy(self, **thresholds):
        return dict(POLICY, thresholds=thresholds)

    def test_archive_remove_and_the_update_step_by_release(self):
        only = self.policy(finished_items=1)
        step = self.step(rs.report(rs.finished("a"), rs.finished("b")), policy=only)
        self.assertIn("archive a --apply", step)
        step = self.step(rs.report(rs.finished("a", archive=True), rs.finished("b", archive=True)),
                         policy=only)
        self.assertIn("remove a --apply", step)
        step = self.step(rs.report(rs.finished("a"), rs.finished("b")), version="2.20.0", policy=only)
        self.assertIn("no `archive` command", step)

    def test_prune_by_release(self):
        only = self.policy(prunable_archives=1)
        rep = sized(rs.report(), archives=2, prunable=1)
        step = self.step(rep, "2.24.0", only)
        self.assertIn("scripts/workflow_retention.py report` to list the prunable archives", step)
        self.assertIn("prune ID --apply` for each", step)
        step = self.step(rep, "2.23.0", only)
        self.assertIn("no `prune` command", step)
        self.assertNotIn("prune ID --apply", step)

    def test_archives_reached_names_prune_only_when_something_is_prunable(self):
        only = self.policy(archives=2)
        step = self.step(sized(rs.report(), archives=2, prunable=1), "2.25.0", only)
        self.assertIn("prune ID --apply` for each", step)
        step = self.step(sized(rs.report(), archives=2, prunable=0), "2.25.0", only)
        self.assertIn("none can be pruned: raise thresholds.archives", step)
        self.assertIn("workflow-manager adopt-retention-policy", step)
        self.assertNotIn("prune ID", step)

    def test_causes_join_in_order_and_each_step_once(self):
        both = self.policy(finished_items=1, finished_folder_mib=1)
        rep = sized(rs.report(rs.finished("a"), rs.finished("b")), finished_folder_bytes=2 * MIB)
        step = self.step(rep, policy=both)
        self.assertEqual(step.count("archive a --apply"), 1)
        self.assertNotIn("; ", step)
        mixed = self.policy(finished_items=1, prunable_archives=1)
        rep = sized(rs.report(rs.finished("a")), archives=1, prunable=1)
        step = self.step(rep, policy=mixed)
        self.assertLess(step.index("archive a"), step.index("prune ID"))
        self.assertIn("; in the repository, run", step)

    def test_an_incomplete_report_joins_the_threshold_step_with_the_incomplete_step(self):
        only = self.policy(finished_items=1)
        rep = rs.report(rs.finished("a"), rs.finished("b"), complete=False)
        step = self.step(rep, policy=only)
        self.assertTrue(step.endswith("; " + retention.STEP_INCOMPLETE), step)
        self.assertIn("archive a --apply", step)
        self.assertNotEqual(step, retention.STEP_INCOMPLETE)


class TestNothingElse(Base):
    def test_exactly_one_report_call_and_the_tree_is_unchanged(self):
        self.adopt()
        before = tree_hash(self.repo)
        for command in ("verify", "doctor"):
            self.marker.unlink(missing_ok=True)
            self.call(command, sized(rs.report(rs.finished("a"), rs.finished("b"),
                                               rs.finished("c")), prunable=5, archives=5))
            calls = self.script_calls()
            self.assertEqual(len(calls), 1, calls)
            self.assertEqual(calls[0]["argv"][1:4], ["report", "--json", "--repo-root"])
            self.assertEqual(tree_hash(self.repo), before)


class TestDocs(unittest.TestCase):
    def read(self, name):
        return (REPO_ROOT / "docs" / name).read_text()

    def test_the_alert_is_documented(self):
        self.assertIn("The retention alert", self.read("retention.md"))
        self.assertIn("retention alert", self.read("verify.md"))
        exit_codes = self.read("exit-codes.md")
        self.assertIn("retention alert", exit_codes)

    def test_no_page_names_the_work_item(self):
        for name in ("retention.md", "verify.md", "exit-codes.md"):
            # the section's own anchor, `#the-retention-alert`, is not an id
            self.assertNotIn("retention-alert", self.read(name).replace("the-retention-alert", ""))

    def test_the_policy_section_no_longer_claims_it_only_reads_the_policy(self):
        self.assertNotIn("This release only **reads**", self.read("retention.md"))


class TestScriptState(unittest.TestCase):
    """The real rule, in subprocesses, nothing patched: a release of the cache
    that ships the script, in a scratch installation of it."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.release = support.release(NEWEST_RELEASE)
        cls.pristine = build_bootstrapped_repo(cls.release, Path(cls._tmp.name) / "pristine")
        digest = lambda v: next(  # noqa: E731
            a.sha256 for a in support.release(v).installable("full")
            if a.target_path == SCRIPT)
        newest = digest(NEWEST_RELEASE)
        cls.other = next((v for v in reversed(TESTED_VERSIONS)
                          if tuple(map(int, v.split("."))) >= (2, 20, 0) and digest(v) != newest),
                         None)

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
        policy = {"schema_version": 1, "mode": "notify", "thresholds": {"finished_items": 1}}
        path.write_text(json.dumps(policy))
        rp.apply(self.repo, rp.usable_policy(self.repo), rp.sentence(rp.digest_of(policy)))

    def state(self, release=None):
        return ra.script_state(self.repo, release or self.release)

    def stub(self):
        script = self.repo / SCRIPT
        script.write_text(rs.STUB)
        script.chmod(0o755)

    def unlist(self):
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        del data["managed"][SCRIPT]
        record.write_text(json.dumps(data, indent=2) + "\n")

    def both(self, *extra):
        report = rs.report(rs.finished("a"), rs.finished("b"))
        path = Path(self.work.name) / "report.json"
        path.write_text(json.dumps(report))
        out = {}
        for command in ("verify", "doctor"):
            env = support.cli_env(STUB_MARKER=str(self.marker), STUB_REPORT=str(path))
            proc = subprocess.run(
                [sys.executable, "-m", "workflow_manager", *extra, command, str(self.repo)],
                cwd=str(REPO_ROOT), capture_output=True, text=True, env=env)
            self.assertNotIn("Traceback", proc.stdout + proc.stderr)
            out[command] = proc.stdout
        return out

    def test_the_releases_own_script_is_ok(self):
        self.assertEqual(self.state(), ra.SCRIPT_OK)

    def test_every_other_case_is_modified(self):
        script = self.repo / SCRIPT
        script.write_bytes(script.read_bytes() + b"# x\n")
        self.assertEqual(self.state(), ra.SCRIPT_MODIFIED)
        shutil.copyfile(self.pristine / SCRIPT, script)
        self.assertEqual(self.state(), ra.SCRIPT_OK)
        script.unlink()
        self.assertEqual(self.state(), ra.SCRIPT_MODIFIED)

    def test_a_script_the_record_does_not_list_is_modified(self):
        self.unlist()
        self.assertEqual(self.state(), ra.SCRIPT_MODIFIED)

    def test_a_release_without_the_script_is_ok_without_a_file_and_modified_with_one(self):
        old = support.release(support.PINNED_NEWEST)
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_bootstrapped_repo(old, Path(tmp) / "old")
            self.assertFalse((repo / SCRIPT).exists())
            self.assertEqual(ra.script_state(repo, old), ra.SCRIPT_OK)
            (repo / SCRIPT).parent.mkdir(exist_ok=True)
            (repo / SCRIPT).write_text(rs.STUB)
            self.assertEqual(ra.script_state(repo, old), ra.SCRIPT_MODIFIED)

    def assert_not_started(self, outputs):
        for command, out in outputs.items():
            with self.subTest(command=command):
                self.assertIn("retention alert: not evaluated: the installed "
                              "scripts/workflow_retention.py does not match the release", out)
                self.assertIn(f"  next: workflow-manager update {self.repo} --force", out)
        self.assertFalse(self.marker.exists())

    def test_a_stub_modified_unlisted_or_missing_is_never_started(self):
        self.stub()
        self.assert_not_started(self.both())
        self.unlist()
        self.assert_not_started(self.both())

    def test_a_missing_script_is_not_started_either(self):
        (self.repo / SCRIPT).unlink()
        self.assert_not_started(self.both())

    def test_the_releases_own_script_reaches_the_evaluation(self):
        for command, out in self.both().items():
            with self.subTest(command=command):
                self.assertIn("retention alert: not evaluated: ", out)
                for bad in ("does not match", "FileNotFoundError", "cannot be checked"):
                    self.assertNotIn(bad, out)

    def test_doctor_judges_the_installed_release_not_the_candidate(self):
        if self.other is None:
            self.skipTest("no tested release has a different script")
        out = self.both("--release-version", self.other)["doctor"]
        self.assertIn("retention alert: not evaluated: ", out)
        for bad in ("does not match", "FileNotFoundError", "cannot be checked"):
            self.assertNotIn(bad, out)


if __name__ == "__main__":
    unittest.main()
