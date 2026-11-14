#!/usr/bin/env python3
"""The retention alert as JSON: `doctor --retention --json`.

Hermetic: the stub script of `test_retention_status` in a scratch managed
repository, no network. The scenarios run `cli.main` in-process with the
script-state seam patched (a stub is never the release's script), so the tests
read the real command's stdout, stderr and exit code. The whole-document goldens
hold the repository path as `<REPO>`. No test writes into this repository.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (puts the tests' own helpers on the path)

import test_retention_alert as tra
import test_retention_status as rs
from test_operator_ux import tree_hash
from workflow_manager import cli, retention, retention_alert as ra, retention_alert_json as raj
from workflow_manager import retention_policy as rp

SCRIPT = rs.SCRIPT
MIB = 2**20
GENERATED = tra.GENERATED
ALL_FIVE = {"schema_version": 1, "mode": "notify",
            "thresholds": {"finished_items": 2, "finished_folder_mib": 1, "archives": 3,
                           "prunable_archives": 2, "finished_max_age_days": 30}}
ONE_RULE = {"schema_version": 1, "mode": "notify", "thresholds": {"archives": 3}}
EVALUATED_KEYS = ["kind", "schema_version", "repo", "policy", "evaluation", "not_evaluated",
                  "report_complete", "alerts", "snapshot"]
ALERT_KEYS = ["rule", "threshold", "threshold_unit", "current_value", "value_unit", "lower_bound",
              "unknown_age", "reached", "state", "alert_key", "next"]
SNAPSHOT_KEYS = ["finished", "with_review_folder", "archived_and_removed", "finished_folder_bytes",
                 "archive_store", "prunable_archives", "interrupted_removals"]


@dataclass
class Ran:
    code: int
    out: str
    err: str


def aged_report(*entries, **overrides):
    rep = rs.report(*entries, generated_at=GENERATED, kept_recent=[], **overrides)
    return rep


def reached_report():
    """J1: count, size and age reached (one old item and one with no usable
    last transition counted apart), archives and prunable within."""
    old = [tra.old_entry("old-a"), tra.old_entry("old-b", when="2026-02-01T00:00:00Z")]
    unknown = tra.aged_entry("no-age", tra.MISSING)
    young = tra.aged_entry("young", tra.at(86400))
    rep = aged_report(*old, unknown, young)
    rep["totals"]["finished_folder_bytes"] = 3 * MIB + 5
    return rep


def clear_report():
    return aged_report(tra.aged_entry("young", tra.at(86400)))


class Base(tra.Base):
    def setUp(self):
        super().setUp()
        self.adopt(ALL_FIVE)

    def run_json(self, rep=None, *, seam=ra.SCRIPT_OK, argv=None, extra=(), **env) -> Ran:
        """`cli.main` on `doctor --retention --json` with the script-state seam patched."""
        if rep is not None:
            env["STUB_REPORT"] = str(self.put_report(rep))
        args = argv if argv is not None else ["doctor", "--retention", "--json", *extra,
                                              str(self.repo)]
        out, err = io.StringIO(), io.StringIO()
        seam_kwargs = ({"side_effect": seam} if isinstance(seam, BaseException)
                       else {"return_value": seam})
        with mock.patch.dict(os.environ, self.env(**env), clear=True), \
                mock.patch.object(cli, "_installed_script_state", **seam_kwargs), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(args)
            except SystemExit as exit_:
                code = exit_.code
        return Ran(code, out.getvalue(), err.getvalue())

    def shown(self, text: str) -> str:
        """The output with the repository's path as `<REPO>`."""
        for path in {str(self.repo.resolve()), str(self.repo)}:
            text = text.replace(path, "<REPO>")
        return text

    def doc(self, ran: Ran) -> dict:
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.err, "")
        return json.loads(ran.out)

    def check(self, name: str, text: str) -> None:
        self.assertEqual(self.shown(text), GOLDENS[name], name)

    def golden(self, name: str, ran: Ran) -> dict:
        self.assertEqual(ran.code, 0, ran.err)
        self.check(name, ran.out)
        return json.loads(ran.out)

    def text_alert(self, rep=None, *, seam=ra.SCRIPT_OK, **env) -> list[str]:
        if rep is not None:
            env["STUB_REPORT"] = str(self.put_report(rep))
        with mock.patch.dict(os.environ, self.env(**env), clear=True):
            return ra.alert_lines(self.repo, "2.22.0", lambda: seam)


class TestGoldens(Base):
    def test_J1_reached(self):
        doc = self.golden("J1", self.run_json(reached_report()))
        self.assertEqual([a["state"] for a in doc["alerts"]],
                         ["reached", "reached", "reached", "clear", "clear"])

    def test_J2_all_clear(self):
        doc = self.golden("J2", self.run_json(clear_report()))
        self.assertEqual((doc["evaluation"], [a["reached"] for a in doc["alerts"]]),
                         ("evaluated", [False] * 5))

    def test_J3_incomplete_with_one_rule_reached(self):
        self.adopt({"schema_version": 1, "mode": "notify",
                    "thresholds": {"finished_items": 2, "archives": 3}})
        rep = rs.report(*tra.entries(3), complete=False)
        doc = self.golden("J3", self.run_json(rep))
        self.assertEqual([(a["state"], a["lower_bound"]) for a in doc["alerts"]],
                         [("reached", True), ("unknown", True)])

    def test_J4_incomplete_nothing_reached_is_not_evaluated(self):
        self.adopt({"schema_version": 1, "mode": "notify",
                    "thresholds": {"finished_items": 5, "archives": 3}})
        doc = self.golden("J4", self.run_json(rs.report(*tra.entries(1), complete=False)))
        self.assertEqual((doc["evaluation"], doc["report_complete"]), ("not_evaluated", False))
        self.assertTrue(all(a["state"] == "unknown" for a in doc["alerts"]))

    def test_J5_not_applicable_never_starts_the_script(self):
        cases = {"absent": lambda: self.drop_policy(),
                 "off": lambda: self.adopt(dict(ALL_FIVE, mode="off")),
                 "cleanup": lambda: self.adopt(dict(ALL_FIVE, mode="cleanup")),
                 "changed": lambda: rp.policy_path(self.repo).write_text(
                     json.dumps(dict(ALL_FIVE, mode="both")))}
        for name, prepare in cases.items():
            with self.subTest(policy=name):
                self.marker.unlink(missing_ok=True)
                prepare()
                doc = self.golden(f"J5-{name}", self.run_json(reached_report()))
                self.assertEqual((doc["evaluation"], doc["alerts"], doc["snapshot"]),
                                 ("not_applicable", [], None))
                self.assertFalse(self.marker.exists())
                self.adopt(ALL_FIVE)

    def test_J6_every_not_evaluated_cause(self):
        cases = {
            "no-script": (lambda: (self.repo / SCRIPT).unlink(), {}, {}),
            "refusing": (None, {}, {"STUB_MODE": "exit", "STUB_EXIT": "2",
                                    "STUB_STDERR": "error: no_origin: no origin\\nnext step: x"}),
            "malformed": (None, {"rep": "[1]"}, {"STUB_MODE": "raw"}),
            "modified": (None, {"seam": ra.SCRIPT_MODIFIED}, {}),
            "unchecked": (None, {"seam": ra.SCRIPT_UNCHECKED}, {}),
            "seam-raises": (None, {"seam": RuntimeError("boom")}, {}),
        }
        for name, (prepare, options, env) in cases.items():
            with self.subTest(cause=name):
                self.install_stub()
                if prepare:
                    prepare()
                rep = options.get("rep", reached_report())
                ran = self.run_json(rep, seam=options.get("seam", ra.SCRIPT_OK), **env)
                doc = self.golden(f"J6-{name}", ran)
                self.assertEqual((doc["evaluation"], doc["alerts"], doc["snapshot"]),
                                 ("not_evaluated", [], None))

    def test_J6_no_release_is_reached_through_document_only(self):
        doc = raj.document(self.repo, None, lambda: ra.SCRIPT_NO_RELEASE)
        self.check("J6-no-release", raj.render(doc))

    def test_J6_an_evaluation_that_raises(self):
        with mock.patch.object(ra, "evaluate", side_effect=ValueError("x")):
            doc = self.golden("J6-evaluate-raises", self.run_json(reached_report()))
        self.assertEqual(doc["not_evaluated"]["cause"], "ValueError")

    def test_J6_a_raise_inside_the_documents_own_boundary(self):
        with mock.patch.object(raj, "_snapshot", side_effect=KeyError("k")):
            doc = self.golden("J6-document-raises", self.run_json(reached_report()))
        self.assertEqual((doc["evaluation"], doc["not_evaluated"]["next"]),
                         ("not_evaluated", retention.STEP_RUN_DIRECTLY))

    def test_J8_long_ids_and_interrupted_removals(self):
        long_id = "x" * 64
        for name, removing in (("present", ["half-done", long_id]), ("empty", []), ("null", None)):
            with self.subTest(removing=name):
                entry = rs.finished(long_id, folder=False, archive=True)
                rep = rs.report(entry, *tra.entries(2))
                if removing is None:
                    del rep["removing"]
                else:
                    rep["removing"] = removing
                doc = self.golden(f"J8-{name}", self.run_json(rep))
                self.assertEqual(doc["snapshot"]["interrupted_removals"], removing)

    def test_D0_the_function_and_the_command_agree(self):
        ran = self.run_json(reached_report())
        env = {"STUB_REPORT": str(self.put_report(reached_report()))}
        with mock.patch.dict(os.environ, self.env(**env), clear=True):
            doc = raj.document(self.repo, "2.22.0", lambda: ra.SCRIPT_OK)
        self.assertEqual(raj.render(doc), ran.out)


class TestObservedChanges(Base):
    """J7: the snapshot states facts of the moment; none of these pairs is proof of a
    transition, and the page says each cause is uncertain."""

    def setUp(self):
        super().setUp()
        self.adopt(ONE_RULE)    # one rule keeps the whole-document goldens short

    def snap(self, rep, golden=None):
        ran = self.run_json(rep)
        if golden is not None:
            self.check(golden, ran.out)
        doc = self.doc(ran)
        return doc["report_complete"], doc["snapshot"]

    def test_an_id_enters_and_then_leaves_archived_and_removed(self):
        kept = tra.entries(3)
        before = rs.report(rs.finished("gone", folder=True, archive=True), *kept)
        after = rs.report(rs.finished("gone", folder=False, archive=True), *kept)
        _, first = self.snap(before, "J7-before")
        _, second = self.snap(after, "J7-after")
        self.assertEqual((first["archived_and_removed"], second["archived_and_removed"]),
                         ([], ["gone"]))
        self.assertEqual((first["with_review_folder"], second["with_review_folder"]), (4, 3))
        _, third = self.snap(rs.report(rs.finished("gone", folder=False, archive=False), *kept))
        self.assertEqual((third["archived_and_removed"], third["archive_store"]), ([], 0))

    def test_an_item_pushed_out_of_the_newest_three_enters_with_its_archive_unchanged(self):
        item = rs.finished("moved", folder=False, archive=True)
        _, first = self.snap(rs.report(*tra.entries(2)))
        _, second = self.snap(rs.report(item, *tra.entries(2)))
        self.assertEqual((first["archived_and_removed"], first["archive_store"]), ([], 0))
        self.assertEqual((second["archived_and_removed"], second["archive_store"]), (["moved"], 1))

    def test_an_item_that_stops_being_eligible_leaves_with_its_archive_intact(self):
        item = rs.finished("family", folder=False, archive=True)
        _, first = self.snap(rs.report(item, *tra.entries(2)))
        rep = rs.report(*tra.entries(2))
        rep["totals"]["archives"] = 1       # the store still holds the archive
        _, second = self.snap(rep)
        self.assertEqual(first["archived_and_removed"], ["family"])
        self.assertEqual((second["archived_and_removed"], second["archive_store"]), ([], 1))

    def test_an_incomplete_observation_says_so_and_is_a_lower_bound(self):
        item = rs.finished("gone", folder=False, archive=True)
        complete, _ = self.snap(rs.report(item, *tra.entries(3)))
        incomplete, snapshot = self.snap(rs.report(*tra.entries(3), complete=False))
        self.assertEqual((complete, incomplete), (True, False))
        self.assertEqual(snapshot["archived_and_removed"], [])


class TestKeys(Base):
    def alert(self, rep, rule):
        doc = self.doc(self.run_json(rep))
        return next(a for a in doc["alerts"] if a["rule"] == rule)

    def test_K1_one_key_per_state_and_a_new_key_when_the_printed_value_changes(self):
        repo = str(self.repo.resolve())
        three = self.alert(rs.report(*tra.entries(3)), "finished_items")
        again = self.alert(rs.report(*tra.entries(3)), "finished_items")
        four = self.alert(rs.report(*tra.entries(4)), "finished_items")
        self.assertEqual(three["alert_key"], f"retention:{repo}:finished_items:reached:3")
        self.assertEqual(again["alert_key"], three["alert_key"])
        self.assertEqual(four["alert_key"], f"retention:{repo}:finished_items:reached:4")
        lower = self.alert(rs.report(*tra.entries(3), complete=False), "finished_items")
        self.assertEqual(lower["alert_key"], f"retention:{repo}:finished_items:reached:3+")
        clear = self.alert(rs.report(*tra.entries(1)), "finished_items")
        self.assertEqual(clear["alert_key"], f"retention:{repo}:finished_items:clear")
        unknown = self.alert(rs.report(*tra.entries(1), complete=False), "finished_items")
        self.assertEqual(unknown["alert_key"], f"retention:{repo}:finished_items:unknown")

    def test_K1_a_clear_rule_has_one_key_whatever_the_value(self):
        repo = str(self.repo.resolve())
        keys = set()
        for archives in (0, 1, 2):
            rep = rs.report(*tra.entries(1))
            rep["totals"]["archives"] = archives
            keys.add(self.alert(rep, "archives")["alert_key"])
        self.assertEqual(keys, {f"retention:{repo}:archives:clear"})

    def test_K1_the_folder_bucket_is_whole_mib_rounded_down(self):
        repo = str(self.repo.resolve())
        keys = []
        for size in (MIB, MIB + 1, 2 * MIB - 1, 2 * MIB):
            rep = rs.report(*tra.entries(1))
            rep["totals"]["finished_folder_bytes"] = size
            keys.append(self.alert(rep, "finished_folder_mib")["alert_key"])
        self.assertEqual(keys, [f"retention:{repo}:finished_folder_mib:reached:{n}"
                                for n in (1, 1, 1, 2)])


class TestNotAFalseAllClear(Base):
    def test_E1_only_an_evaluated_document_can_be_clear_or_reached(self):
        def with_policy(mode):
            self.adopt(dict(ALL_FIVE, mode=mode))
            return self.run_json(reached_report())

        scenarios = [
            ("not_applicable", lambda: with_policy("off")),
            ("not_applicable", lambda: with_policy("cleanup")),
            ("not_evaluated", lambda: self.run_json(reached_report(), seam=ra.SCRIPT_MODIFIED)),
            ("not_evaluated", lambda: self.run_json(reached_report(), seam=ra.SCRIPT_UNCHECKED)),
            ("not_evaluated", lambda: self.run_json("[1]", STUB_MODE="raw")),
            ("not_evaluated", lambda: self.run_json(rs.report(*tra.entries(1), complete=False))),
            ("evaluated", lambda: self.run_json(clear_report())),
        ]
        for index, (expected, scenario) in enumerate(scenarios):
            with self.subTest(scenario=index):
                self.adopt(ALL_FIVE)
                doc = self.doc(scenario())
                self.assertEqual(doc["evaluation"], expected, doc)
                if expected != "evaluated":
                    self.assertFalse(any(a["reached"] for a in doc["alerts"]), doc)
                    self.assertNotIn("clear", [a["state"] for a in doc["alerts"]])


class TestCommand(Base):
    def test_every_key_is_present_in_every_document_in_order(self):
        for rep in (reached_report(), clear_report()):
            doc = self.doc(self.run_json(rep))
            self.assertEqual(list(doc), EVALUATED_KEYS)
            self.assertEqual(list(doc["snapshot"]), SNAPSHOT_KEYS)
            self.assertTrue(all(list(a) == ALERT_KEYS for a in doc["alerts"]))
        self.drop_policy()
        self.assertEqual(list(self.doc(self.run_json(reached_report()))), EVALUATED_KEYS)

    def test_X1_exit_zero_whenever_the_document_is_printed_even_where_text_exits_one(self):
        self.drop_policy()
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = support.PINNED_NEWEST
        record.write_text(json.dumps(data, indent=2) + "\n")
        managed = next(p for p in data["managed"] if not p.endswith(SCRIPT))
        (self.repo / managed).write_text("drifted\n")
        self.adopt(ALL_FIVE)
        text = self.call("doctor", reached_report(), flag=True)
        self.assertEqual(text.code, 1, text.out)
        ran = self.run_json(reached_report())
        self.assertEqual((ran.code, ran.err), (0, ""))

    def test_X1_refusals_before_any_document(self):
        text_args = ["doctor", "--retention"]
        record = self.repo / ".workflow-manager" / "installation.json"
        data = json.loads(record.read_text())
        data["workflow_version"] = support.PINNED_NEWEST   # so the text command resolves too
        original = json.dumps(data)
        cases = {}
        for label, version in (("unparseable", "not-a-version"), ("null", None)):
            def prepare(version=version):
                data = json.loads(original)
                data["workflow_version"] = version
                record.write_text(json.dumps(data))
            cases[label] = (prepare, [], str(self.repo))
        cases["not managed"] = (lambda: None, [], str(self.outside))
        cases["cache inside"] = (lambda: None, ["--release-cache", str(self.repo / ".cache")],
                                 str(self.repo))
        for label, (prepare, options, target) in cases.items():
            with self.subTest(case=label):
                record.write_text(original)
                prepare()
                text = self.run_json(argv=[*options, *text_args, target])
                ran = self.run_json(argv=[*options, *text_args, "--json", target])
                self.assertEqual((ran.code, ran.out), (2, ""), ran.err)
                self.assertEqual(ran.err, text.err)
                self.assertTrue(ran.err.startswith("error:"), ran.err)

    def test_X1_the_release_options_are_refused_before_anything_is_read(self):
        record = self.repo / ".workflow-manager" / "installation.json"
        for option, argv in (
            ("--release-version", ["--release-version", "2.22.0"]),
            ("--release-version", ["--release-version", "not-one"]),
            ("--release-dir", ["--release-dir", str(self.outside)]),
            ("--manager-root", ["--manager-root", str(self.outside)]),
        ):
            with self.subTest(argv=argv), mock.patch.object(cli, "_cache") as cache, \
                    mock.patch.object(cli, "_pins") as pins:
                ran = self.run_json(argv=[*argv, "doctor", "--retention", "--json",
                                          str(self.repo)])
                self.assertEqual((ran.code, ran.out), (2, ""))
                lines = [l for l in ran.err.splitlines() if not l.startswith("workflow-manager:")]
                self.assertEqual(len(lines), 1, ran.err)
                self.assertIn(f"error: {option}", lines[0])
                self.assertIn("--json", lines[0])
                cache.assert_not_called()
                pins.assert_not_called()
        record.write_text("{")
        ran = self.run_json(argv=["--release-version", "2.22.0", "doctor", "--retention", "--json",
                                  str(self.outside)])
        self.assertIn("error: --release-version", ran.err)   # the refusal wins over not managed

    def test_X1_json_needs_retention(self):
        ran = self.run_json(argv=["doctor", "--json", str(self.repo)])
        self.assertEqual((ran.code, ran.out), (2, ""))
        self.assertIn("--json", ran.err)

    def test_W1_nothing_is_written_and_only_the_document_is_printed(self):
        here = tree_hash(support.REPO_ROOT, skip=(".ai-review", ".git"))
        for rep, seam in ((reached_report(), ra.SCRIPT_OK), (reached_report(), ra.SCRIPT_MODIFIED)):
            before = tree_hash(self.repo)
            ran = self.run_json(rep, seam=seam)
            self.assertEqual(tree_hash(self.repo), before)
            self.assertEqual(ran.out.count("\n"), len(ran.out.splitlines()))
            self.assertEqual(json.loads(ran.out)["kind"], "retention_alert")
            self.assertTrue(ran.out.startswith("{\n") and ran.out.endswith("}\n"), ran.out)
        self.drop_policy()
        before = tree_hash(self.repo)
        self.run_json(reached_report())
        self.assertEqual(tree_hash(self.repo), before)
        self.assertEqual(tree_hash(support.REPO_ROOT, skip=(".ai-review", ".git")), here)

    def test_P1_the_script_starts_only_after_the_gate(self):
        for name, prepare in (
            ("absent", lambda: self.drop_policy()),
            ("off", lambda: self.adopt(dict(ALL_FIVE, mode="off"))),
            ("cleanup", lambda: self.adopt(dict(ALL_FIVE, mode="cleanup"))),
        ):
            with self.subTest(policy=name):
                self.marker.unlink(missing_ok=True)
                prepare()
                self.assertEqual(self.doc(self.run_json(reached_report()))["evaluation"],
                                 "not_applicable")
                self.assertEqual(self.script_calls(), [])
                self.adopt(ALL_FIVE)
        self.marker.unlink(missing_ok=True)
        self.doc(self.run_json(reached_report()))
        self.assertEqual(len(self.script_calls()), 1)


class TestSharedAssessment(Base):
    def test_S1_the_cause_and_step_are_the_text_alerts(self):
        cases = [
            ({"seam": ra.SCRIPT_MODIFIED}, {}),
            ({"seam": ra.SCRIPT_UNCHECKED}, {}),
            ({"seam": ra.SCRIPT_NO_RELEASE}, {}),
            ({"seam": ra.SCRIPT_OK}, {"STUB_MODE": "exit", "STUB_EXIT": "1"}),
            ({"seam": ra.SCRIPT_OK}, {"STUB_MODE": "raw", "rep": "[1]"}),
        ]
        for options, env in cases:
            with self.subTest(options=options, env=env):
                env = dict(env)
                rep = env.pop("rep", None) or reached_report()
                lines = self.text_alert(rep, seam=options["seam"], **env)
                doc = raj.document(self.repo, "2.22.0", lambda: options["seam"], None) \
                    if options["seam"] == ra.SCRIPT_NO_RELEASE else None
                if doc is None:
                    with mock.patch.dict(os.environ, self.env(
                            STUB_REPORT=str(self.put_report(rep)), **env), clear=True):
                        doc = raj.document(self.repo, "2.22.0", lambda: options["seam"])
                self.assertEqual(doc["evaluation"], "not_evaluated")
                self.assertEqual(lines, [
                    f"retention alert: not evaluated: {doc['not_evaluated']['cause']}",
                    f"  next: {doc['not_evaluated']['next']}"])

    def test_S1_the_raise_causes_agree_too(self):
        with mock.patch.object(ra, "evaluate", side_effect=ValueError("x")):
            with mock.patch.dict(os.environ, self.env(
                    STUB_REPORT=str(self.put_report(reached_report()))), clear=True):
                lines = ra.alert_lines(self.repo, "2.22.0", lambda: ra.SCRIPT_OK)
                doc = raj.document(self.repo, "2.22.0", lambda: ra.SCRIPT_OK)
        self.assertEqual(lines, ["retention alert: not evaluated: ValueError",
                                 f"  next: {retention.STEP_RUN_DIRECTLY}"])
        self.assertEqual(doc["not_evaluated"], {"cause": "ValueError",
                                                "next": retention.STEP_RUN_DIRECTLY})
        boom = RuntimeError("boom")
        lines = ra.alert_lines(self.repo, "2.22.0", mock.Mock(side_effect=boom))
        doc = raj.document(self.repo, "2.22.0", mock.Mock(side_effect=boom))
        self.assertEqual(lines[0], "retention alert: not evaluated: RuntimeError")
        self.assertEqual(doc["not_evaluated"]["cause"], "RuntimeError")


class TestPages(unittest.TestCase):
    """D1: the pages carry the shape, the key rule, the observed-not-proven reading and the exit rule."""

    @classmethod
    def setUpClass(cls):
        cls.page = (support.REPO_ROOT / "docs" / "retention.md").read_text()
        cls.codes = (support.REPO_ROOT / "docs" / "exit-codes.md").read_text()
        cls.section = cls.page.split("## The retention alert as JSON\n", 1)[1].split("\n## ", 1)[0]

    def test_D1_every_key_and_value_is_named(self):
        for name in EVALUATED_KEYS + ALERT_KEYS + SNAPSHOT_KEYS:
            with self.subTest(key=name):
                self.assertIn(f"`{name}`", self.section)
        for value in ("evaluated", "not_evaluated", "not_applicable", "reached", "clear", "unknown",
                      "retention_alert", "report_complete: false", "finished_max_age_days"):
            with self.subTest(value=value):
                self.assertIn(value, self.section)

    def test_D1_the_rules_and_the_readings(self):
        for sentence in ("compares two **complete** ones",
                         "observed change of uncertain cause",
                         "no `archived` and no `deleted` state",
                         "never parses one",
                         "ignores an alert whose `state` it does not know",
                         "`12` to `12+` is a new key",
                         "a moved repository is a new identity",
                         "`repo` and `alert_key` are the identity",
                         "are refused with it",
                         "exits 0 whenever it prints the document"):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, self.section)

    def test_D1_the_order_of_the_alerts_is_the_codes(self):
        row = next(line for line in self.section.splitlines() if line.startswith("| `alerts` |"))
        named = row.split("always in this order: ", 1)[1].split(".", 1)[0]
        self.assertEqual(named, ", ".join(f"`{key}`" for key in rp.THRESHOLDS))

    def test_D1_the_exit_rule_is_on_both_pages(self):
        self.assertIn("exits 0 whenever it prints its document", self.page)
        rows = [line for line in self.codes.splitlines() if "`doctor --retention --json`" in line]
        self.assertEqual([line.split("|")[1].strip() for line in rows], ["0", "2"])
        self.assertIn("retention.md#the-retention-alert-as-json", rows[0])


class TestTextUnchanged(Base):
    def test_T1_the_text_alert_is_the_bases_bytes(self):
        reached = self.text_alert(reached_report())
        self.assertEqual(reached, TEXT_GOLDENS["reached"].replace("<REPO>", str(self.repo)).splitlines())
        self.adopt({"schema_version": 1, "mode": "notify",
                    "thresholds": {"finished_items": 5, "archives": 3}})
        incomplete = self.text_alert(rs.report(*tra.entries(1), complete=False))
        self.assertEqual(incomplete, TEXT_GOLDENS["incomplete"].splitlines())


# The base's text alert, captured at 84e6e3f.
TEXT_GOLDENS = {
    "reached":
        "retention alert: 3 of 5 thresholds reached (mode notify, policy 28d4cfda7c9b)\n"
        "  finished items: 4, limit 2: reached\n"
        "  finished folders: 3 MiB, limit 1 MiB: reached\n"
        "  finished older than 30 days: 2 items, 1 more with no usable last transition (not counted): reached\n"
        "  next: in the repository, run `python3 -I scripts/workflow_retention.py archive old-a --apply` (run it without `--apply` first for a dry run); in the repository, run `python3 -I scripts/workflow_retention.py archive old-b --apply` (run it without `--apply` first for a dry run)",
    "incomplete":
        "retention alert: not evaluated: the retention report is incomplete (the numbers are lower bounds)\n"
        "  next: fix what is named, then run the command again",
}

# The whole documents, with the repository path as <REPO>.
GOLDENS = {
    "J1": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 2,
      "threshold_unit": "items",
      "current_value": 4,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": null,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_items:reached:4",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive old-a --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "finished_folder_mib",
      "threshold": 1,
      "threshold_unit": "MiB",
      "current_value": 3,
      "value_unit": "MiB",
      "lower_bound": false,
      "unknown_age": null,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_folder_mib:reached:3",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive old-a --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "finished_max_age_days",
      "threshold": 30,
      "threshold_unit": "days",
      "current_value": 2,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": 1,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_max_age_days:reached:2",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive old-b --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    },
    {
      "rule": "prunable_archives",
      "threshold": 2,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:prunable_archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 4,
    "with_review_folder": 4,
    "archived_and_removed": [],
    "finished_folder_bytes": 3145733,
    "archive_store": 0,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J2": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 2,
      "threshold_unit": "items",
      "current_value": 1,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_items:clear",
      "next": null
    },
    {
      "rule": "finished_folder_mib",
      "threshold": 1,
      "threshold_unit": "MiB",
      "current_value": 0,
      "value_unit": "MiB",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_folder_mib:clear",
      "next": null
    },
    {
      "rule": "finished_max_age_days",
      "threshold": 30,
      "threshold_unit": "days",
      "current_value": 0,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": 0,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_max_age_days:clear",
      "next": null
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    },
    {
      "rule": "prunable_archives",
      "threshold": 2,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:prunable_archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 1,
    "with_review_folder": 1,
    "archived_and_removed": [],
    "finished_folder_bytes": 2048,
    "archive_store": 0,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J3": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "4026b07611e2c4ad18f98246d8ee5ad1c5b4ad36b53f120d4112625247f70782"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": false,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 2,
      "threshold_unit": "items",
      "current_value": 3,
      "value_unit": "items",
      "lower_bound": true,
      "unknown_age": null,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_items:reached:3+",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive item-0 --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": true,
      "unknown_age": null,
      "reached": false,
      "state": "unknown",
      "alert_key": "retention:<REPO>:archives:unknown",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 3,
    "with_review_folder": 3,
    "archived_and_removed": [],
    "finished_folder_bytes": 6144,
    "archive_store": 0,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J4": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "5a880862f2ee85bacbc3f59ef726679b18e3d202f7552982ca7bf5f8078c6340"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "the retention report is incomplete (the numbers are lower bounds)",
    "next": "fix what is named, then run the command again"
  },
  "report_complete": false,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 5,
      "threshold_unit": "items",
      "current_value": 1,
      "value_unit": "items",
      "lower_bound": true,
      "unknown_age": null,
      "reached": false,
      "state": "unknown",
      "alert_key": "retention:<REPO>:finished_items:unknown",
      "next": null
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": true,
      "unknown_age": null,
      "reached": false,
      "state": "unknown",
      "alert_key": "retention:<REPO>:archives:unknown",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 1,
    "with_review_folder": 1,
    "archived_and_removed": [],
    "finished_folder_bytes": 2048,
    "archive_store": 0,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J5-absent": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "absent",
    "mode": "off",
    "digest": null
  },
  "evaluation": "not_applicable",
  "not_evaluated": null,
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J5-off": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "off",
    "digest": "6e255dbceaffdca3b90c9f8dbc89c2bd07feb9233da383a21d8f13d042e487f2"
  },
  "evaluation": "not_applicable",
  "not_evaluated": null,
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J5-cleanup": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "cleanup",
    "digest": "c5ad0fbb2bf21d94f373fbe87c940f55adc35829b3c65947d74b087cde6c37f6"
  },
  "evaluation": "not_applicable",
  "not_evaluated": null,
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J5-changed": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "changed",
    "mode": "off",
    "digest": null
  },
  "evaluation": "not_applicable",
  "not_evaluated": null,
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-document-raises": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "KeyError",
    "next": "run `python3 -I scripts/workflow_retention.py report` in the repository"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-evaluate-raises": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "ValueError",
    "next": "run `python3 -I scripts/workflow_retention.py report` in the repository"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-no-script": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "the repository has no scripts/workflow_retention.py (the Workflow release that ships it is 2.20.0 or later)",
    "next": "workflow-manager update <REPO>"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-refusing": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "no_origin: no origin",
    "next": "x"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-malformed": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "the script's output is not one JSON object",
    "next": "run `python3 -I scripts/workflow_retention.py report` in the repository"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-modified": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "the installed scripts/workflow_retention.py does not match the release",
    "next": "workflow-manager update <REPO> --force"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-unchecked": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "the installed release cannot be checked",
    "next": "run the command again with the network, or with WORKFLOW_MANAGER_RELEASE_SOURCE set to a mirror"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-seam-raises": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "RuntimeError",
    "next": "run `python3 -I scripts/workflow_retention.py report` in the repository"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J6-no-release": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "not_evaluated",
  "not_evaluated": {
    "cause": "the installation record names no release",
    "next": "workflow-manager --release-version X.Y.Z update <REPO> (workflow-manager releases lists them)"
  },
  "report_complete": null,
  "alerts": [],
  "snapshot": null
}
""",
    "J7-before": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "0eac9d9f2d077028dce3363ec2c39a5e96a5fedb7193f1b3853a13e76056b98f"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 1,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 4,
    "with_review_folder": 4,
    "archived_and_removed": [],
    "finished_folder_bytes": 8192,
    "archive_store": 1,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J7-after": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "0eac9d9f2d077028dce3363ec2c39a5e96a5fedb7193f1b3853a13e76056b98f"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 1,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 4,
    "with_review_folder": 3,
    "archived_and_removed": [
      "gone"
    ],
    "finished_folder_bytes": 6144,
    "archive_store": 1,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J8-present": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 2,
      "threshold_unit": "items",
      "current_value": 2,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": null,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_items:reached:2",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive item-0 --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "finished_folder_mib",
      "threshold": 1,
      "threshold_unit": "MiB",
      "current_value": 0,
      "value_unit": "MiB",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_folder_mib:clear",
      "next": null
    },
    {
      "rule": "finished_max_age_days",
      "threshold": 30,
      "threshold_unit": "days",
      "current_value": 0,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": 0,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_max_age_days:clear",
      "next": null
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 1,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    },
    {
      "rule": "prunable_archives",
      "threshold": 2,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:prunable_archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 3,
    "with_review_folder": 2,
    "archived_and_removed": [
      "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ],
    "finished_folder_bytes": 4096,
    "archive_store": 1,
    "prunable_archives": 0,
    "interrupted_removals": [
      "half-done",
      "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ]
  }
}
""",
    "J8-empty": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 2,
      "threshold_unit": "items",
      "current_value": 2,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": null,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_items:reached:2",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive item-0 --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "finished_folder_mib",
      "threshold": 1,
      "threshold_unit": "MiB",
      "current_value": 0,
      "value_unit": "MiB",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_folder_mib:clear",
      "next": null
    },
    {
      "rule": "finished_max_age_days",
      "threshold": 30,
      "threshold_unit": "days",
      "current_value": 0,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": 0,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_max_age_days:clear",
      "next": null
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 1,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    },
    {
      "rule": "prunable_archives",
      "threshold": 2,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:prunable_archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 3,
    "with_review_folder": 2,
    "archived_and_removed": [
      "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ],
    "finished_folder_bytes": 4096,
    "archive_store": 1,
    "prunable_archives": 0,
    "interrupted_removals": []
  }
}
""",
    "J8-null": """\
{
  "kind": "retention_alert",
  "schema_version": 1,
  "repo": "<REPO>",
  "policy": {
    "state": "adopted",
    "mode": "notify",
    "digest": "28d4cfda7c9b053fe67831b08f8114fb131651e7cd7553f45dbe094e9129a8b9"
  },
  "evaluation": "evaluated",
  "not_evaluated": null,
  "report_complete": true,
  "alerts": [
    {
      "rule": "finished_items",
      "threshold": 2,
      "threshold_unit": "items",
      "current_value": 2,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": null,
      "reached": true,
      "state": "reached",
      "alert_key": "retention:<REPO>:finished_items:reached:2",
      "next": "in the repository, run `python3 -I scripts/workflow_retention.py archive item-0 --apply` (run it without `--apply` first for a dry run)"
    },
    {
      "rule": "finished_folder_mib",
      "threshold": 1,
      "threshold_unit": "MiB",
      "current_value": 0,
      "value_unit": "MiB",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_folder_mib:clear",
      "next": null
    },
    {
      "rule": "finished_max_age_days",
      "threshold": 30,
      "threshold_unit": "days",
      "current_value": 0,
      "value_unit": "items",
      "lower_bound": false,
      "unknown_age": 0,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:finished_max_age_days:clear",
      "next": null
    },
    {
      "rule": "archives",
      "threshold": 3,
      "threshold_unit": "archives",
      "current_value": 1,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:archives:clear",
      "next": null
    },
    {
      "rule": "prunable_archives",
      "threshold": 2,
      "threshold_unit": "archives",
      "current_value": 0,
      "value_unit": "archives",
      "lower_bound": false,
      "unknown_age": null,
      "reached": false,
      "state": "clear",
      "alert_key": "retention:<REPO>:prunable_archives:clear",
      "next": null
    }
  ],
  "snapshot": {
    "finished": 3,
    "with_review_folder": 2,
    "archived_and_removed": [
      "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    ],
    "finished_folder_bytes": 4096,
    "archive_store": 1,
    "prunable_archives": 0,
    "interrupted_removals": null
  }
}
""",
}


if __name__ == "__main__":
    unittest.main()
