#!/usr/bin/env python3
"""The unattended retention prune: its selection, plan digest and argv forms (CP1).

Hermetic and pure: `retention_prune.select` is driven with report dicts built from
the shape of the engine's report (`scripts/workflow_retention.py`, `_assemble`:
`archives[]` with `age_days`, `modified` and `item`, `finished[]` with
`review_folder.present`, `removing[]`). No process, no network, no file is written.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from support import REPO_ROOT
from test_operator_ux import help_of

import test_retention_cleanup as tc
import test_retention_status as rs
import test_retention_unattended_run as tur
from workflow_manager import retention_cleanup as rc, retention_policy as rp, retention_prune as rpr, retention_run as rr

TTL, CAP = 30, 3


def unattended(**overrides):
    return {"cleanup": True, "prune": True, "keep_recent": 5, "ttl_days": TTL,
            "prune_max_per_run": CAP, **overrides}


def archive(item_id, age, *, item="finished", modified="auto", **extra):
    found = {"name": f"{item_id}.tar.zst", "work_item_id": item_id, "age_days": age,
             "bytes": 10, "prunable": isinstance(age, int) and age > 30, "item": item}
    found["modified"] = "2026-01-01T00:00:00Z" if modified == "auto" else modified
    if modified is None:
        del found["modified"]
    found.update(extra)
    return found


def report(archives, *, gone=None, removing=(), folders=None):
    """A report whose `finished[]` lists every `finished` archive's item, folder gone
    unless named in `folders` (the ids whose review folder is present)."""
    folders = set(folders or ())
    entries = [rs.finished(a["work_item_id"], folder=a["work_item_id"] in folders)
               for a in archives if a.get("item") == "finished" and a["work_item_id"] not in (gone or ())]
    rep = rs.report(*entries)
    rep["archives"] = list(archives)
    rep["removing"] = list(removing)
    return rep


def chosen(rep, **overrides):
    return rpr.select(rep, unattended(**overrides), policy_digest="d" * 64)


class TestClassAndAge(unittest.TestCase):
    def test_only_the_finished_class_is_selected(self):
        rep = report([archive("fin", 40), archive("opn", 40, item="open"),
                      archive("rec", 40, item="recent"), archive("oth", 40, item="other")])
        self.assertEqual(chosen(rep).ids, ("fin",))
        self.assertEqual(chosen(rep).skipped, ())

    def test_the_ttl_boundary_is_strict(self):
        rep = report([archive("exact", TTL), archive("older", TTL + 1), archive("younger", TTL - 1)])
        self.assertEqual(chosen(rep).ids, ("older",))

    def test_the_policy_ttl_decides_not_the_reports_prunable_flag(self):
        rep = report([archive("a", 20, prunable=True, modified="2026-02-02T00:00:00Z"),
                      archive("b", 40, prunable=False, modified="2026-02-01T00:00:00Z")])
        self.assertEqual(chosen(rep).ids, ("b",))
        self.assertEqual(chosen(rep, ttl_days=14).ids, ("b", "a"))

    def test_a_non_integer_or_boolean_age_is_never_selected(self):
        for age in (True, 40.5, "40", None, [40]):
            with self.subTest(age=age):
                self.assertEqual(chosen(report([archive("a", age)])).ids, ())
        self.assertEqual(chosen(report([{k: v for k, v in archive("a", 40).items() if k != "age_days"}])).ids, ())

    def test_a_missing_or_non_string_modified_is_never_selected(self):
        for modified in (None, 5, ["x"]):
            with self.subTest(modified=modified):
                plan = chosen(report([archive("a", 40, modified=modified)]))
                self.assertEqual((plan.ids, plan.skipped), ((), (("a", rpr.AGE_NOT_KNOWN),)))

    def test_a_malformed_archive_entry_is_ignored(self):
        rep = report([archive("a", 40)])
        rep["archives"] += ["text", None, 7]
        self.assertEqual(chosen(rep).ids, ("a",))
        rep["archives"] = None
        self.assertEqual(chosen(rep).ids, ())


class TestExclusions(unittest.TestCase):
    def test_a_present_review_folder_is_excluded_with_its_reason(self):
        rep = report([archive("kept", 40), archive("gone", 41)], folders={"kept"})
        plan = chosen(rep)
        self.assertEqual((plan.ids, plan.skipped), (("gone",), (("kept", rpr.FOLDER_PRESENT),)))

    def test_a_missing_finished_entry_fails_closed(self):
        rep = report([archive("orphan", 40)], gone={"orphan"})
        plan = chosen(rep)
        self.assertEqual((plan.ids, plan.skipped), ((), (("orphan", rpr.FOLDER_PRESENT),)))

    def test_a_folder_fact_that_is_not_exactly_false_fails_closed(self):
        for folder in (None, "no", 0, {}, {"present": None}, {"present": 0}):
            with self.subTest(folder=folder):
                rep = report([archive("a", 40)])
                rep["finished"][0]["review_folder"] = folder
                self.assertEqual(chosen(rep).ids, ())

    def test_an_id_under_an_interrupted_removal_is_excluded(self):
        rep = report([archive("half", 40), archive("ok", 41)], removing=["half"])
        plan = chosen(rep)
        self.assertEqual((plan.ids, plan.skipped), (("ok",), (("half", rpr.REMOVAL_INTERRUPTED),)))

    def test_an_unacceptable_id_is_excluded(self):
        for bad in ("Upper", "-lead", "has space", "x" * 65, "runtime", "archive", ""):
            with self.subTest(item_id=bad):
                plan = chosen(report([archive(bad, 40)]))
                self.assertEqual((plan.ids, plan.skipped), ((), ((bad, rpr.UNACCEPTABLE_ID),)))
        self.assertEqual(chosen(report([archive(None, 40)])).skipped, (("?", rpr.UNACCEPTABLE_ID),))

    def test_skipped_lists_only_old_finished_archives(self):
        rep = report([archive("young", 5, ), archive("opn", 99, item="open")], folders={"young"})
        self.assertEqual(chosen(rep).skipped, ())

    def test_keep_recent_does_not_apply_to_prune(self):
        # the newest finished items stay as folders; an archive of one whose folder
        # is gone is exactly what prune is for
        rep = report([archive("newest-item", 40)])
        self.assertEqual(chosen(rep, keep_recent=50).ids, ("newest-item",))


class TestCapAndOrder(unittest.TestCase):
    def test_oldest_first_by_modified_and_the_cap_cuts_the_newest(self):
        rep = report([archive("a-new", 31, modified="2026-03-04T00:00:00Z"),
                      archive("b-mid", 35, modified="2026-03-03T00:00:00Z"),
                      archive("c-old", 90, modified="2026-03-02T00:00:00Z"),
                      archive("d-oldest", 99, modified="2026-03-01T00:00:00Z"),
                      archive("zzz-oldest", 99, modified="2026-03-01T00:00:00Z")])
        plan = chosen(rep)
        self.assertEqual(plan.ids, ("d-oldest", "zzz-oldest", "c-old"))
        self.assertEqual(plan.capped, 2)
        self.assertEqual(chosen(rep, prune_max_per_run=1).ids, ("d-oldest",))

    def test_the_order_is_by_modified_not_by_id_nor_by_age(self):
        rep = report([archive("aaa", 50, modified="2026-03-09T00:00:00Z"),
                      archive("zzz", 31, modified="2026-03-01T00:00:00Z")])
        self.assertEqual(chosen(rep).ids, ("zzz", "aaa"))

    def test_the_cap_counts_only_selectable_archives(self):
        rep = report([archive(f"p{n}", 40 + n) for n in range(5)] + [archive("shut", 99)], folders={"shut"})
        plan = chosen(rep)
        self.assertEqual((len(plan.ids), plan.capped, len(plan.skipped)), (CAP, 2, 1))

    def test_no_cap_reached_means_not_capped(self):
        plan = chosen(report([archive("a", 40)]))
        self.assertEqual((plan.ids, plan.capped), (("a",), 0))

    def test_a_repeated_id_is_planned_once(self):
        plan = chosen(report([archive("a", 40), archive("a", 40)]))
        self.assertEqual(plan.ids, ("a",))

    def test_an_empty_selection(self):
        for rep in (report([]), {"repository": "r"}):
            with self.subTest(rep=rep):
                plan = chosen(rep)
                self.assertEqual((plan.ids, plan.skipped, plan.capped), ((), (), 0))


class TestDigest(unittest.TestCase):
    def base(self):
        return report([archive("a", 40), archive("b", 41, modified="2026-02-01T00:00:00Z")])

    def test_stable_and_a_full_sha256(self):
        self.assertEqual(rpr.prune_digest(chosen(self.base())), rpr.prune_digest(chosen(self.base())))
        self.assertRegex(rpr.prune_digest(chosen(self.base())), r"^[0-9a-f]{64}$")

    def test_each_input_moves_it(self):
        base = rpr.prune_digest(chosen(self.base()))
        other_repo = self.base()
        other_repo["repository"] = "/elsewhere"
        reordered = self.base()
        reordered["archives"][0]["modified"] = "2026-03-01T00:00:00Z"
        variants = {
            "repository": chosen(other_repo),
            "policy": rpr.select(self.base(), unattended(), policy_digest="e" * 64),
            "ttl": chosen(self.base(), ttl_days=35),
            "ids": chosen(report([archive("a", 40), archive("c", 41)])),
            "order": chosen(reordered),
            "cap": chosen(self.base(), prune_max_per_run=1),
        }
        for label, plan in variants.items():
            with self.subTest(label=label):
                self.assertNotEqual(rpr.prune_digest(plan), base)

    def test_the_skipped_ids_do_not_move_it(self):
        extra = self.base()
        extra["archives"].append(archive("shut", 99))
        extra["finished"].append(rs.finished("shut", folder=True))
        self.assertEqual(rpr.prune_digest(chosen(extra)), rpr.prune_digest(chosen(self.base())))


class TestArgv(unittest.TestCase):
    def test_the_dry_run_form(self):
        self.assertEqual(rpr.argv_for(rpr.PRUNE, ["a", "b"], 30, "/r"),
                         ("prune", "a", "b", "--json", "--ttl-days", "30", "--repo-root", "/r"))

    def test_the_apply_form_carries_one_id(self):
        self.assertEqual(rpr.argv_for(rpr.APPLY, ["a"], 14, "/r"),
                         ("prune", "a", "--apply", "--json", "--ttl-days", "14", "--repo-root", "/r"))
        with self.assertRaises(ValueError):
            rpr.argv_for(rpr.APPLY, ["a", "b"], 30, "/r")

    def test_nothing_else_is_accepted(self):
        for args in ((rpr.PRUNE, [], 30, "/r"), (rpr.PRUNE, ["--apply"], 30, "/r"),
                     (rpr.PRUNE, ["A"], 30, "/r"), (rpr.PRUNE, [None], 30, "/r"),
                     (rpr.PRUNE, ["a"], "30", "/r"), (rpr.PRUNE, ["a"], True, "/r"),
                     ("archive", ["a"], 30, "/r"), ("", ["a"], 30, "/r")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                rpr.argv_for(*args)

    def test_no_archive_root_in_any_form(self):
        for form, ids in ((rpr.PRUNE, ["a", "b"]), (rpr.APPLY, ["a"])):
            argv = rpr.argv_for(form, ids, 30, "/r")
            self.assertNotIn("--archive-root", argv)
            self.assertEqual(argv[-2:], ("--repo-root", "/r"))
            self.assertIn("--ttl-days", argv)


class TestPure(unittest.TestCase):
    def test_the_module_opens_no_file_itself(self):
        # the selection, the digest and the argv forms are pure; the phase below them
        # reaches the engine only through `retention.launch_script` and `retention.fetch`
        tree = ast.parse((REPO_ROOT / "src" / "workflow_manager" / "retention_prune.py")
                         .read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(imported - {"__future__"}, {"hashlib", "json", "dataclasses", "pathlib"})
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(calls & {"open", "exec", "eval", "__import__"})

    def test_select_does_not_change_its_arguments(self):
        import copy
        rep, policy = report([archive("a", 40), archive("b", 99)], folders={"b"}), unattended()
        before = copy.deepcopy((rep, policy))
        rpr.select(rep, policy)
        self.assertEqual((rep, policy), before)


# ---------------------------------------------------------------------------
# The phase (CP2): a verb-aware stub engine in a scratch managed repository
# ---------------------------------------------------------------------------

PRUNE_STUB = r"""
import json, os, sys, time
argv = sys.argv[1:]
with open(os.environ["STUB_MARKER"], "a") as handle:
    handle.write(json.dumps({"argv": sys.argv, "cwd": os.getcwd()}) + "\n")
verb = argv[0]
if verb == "report":
    sys.stdout.write(open(os.environ["STUB_REPORT"]).read())
    sys.exit(0)
apply = "--apply" in argv
ttl = int(argv[argv.index("--ttl-days") + 1])
ids = []
for word in argv[1:]:
    if word.startswith("--"):
        break
    ids.append(word)
key = "prune" + (" --apply:" + ids[0] if apply else ":dry")
path = os.environ.get("STUB_SCENARIO")
spec = json.load(open(path)).get(key, {}) if path and os.path.exists(path) else {}
if spec.get("sleep"):
    time.sleep(spec["sleep"])
if "stdout" in spec:
    text = spec["stdout"]
    sys.stdout.write(text if isinstance(text, str) else json.dumps(text))
    sys.stderr.write(spec.get("stderr", ""))
    sys.exit(spec.get("exit", 0))
store = os.environ.get("STUB_ARCHIVES")
entries, refused = [], None
for item_id in sorted(set(ids)):
    entry = {"work_item_id": item_id, "name": item_id + ".tar.zst", "item": "finished",
             "bytes": 1, "modified": "x", "age_days": 99}
    if store:       # engine-faithful: a new look at the file on every call
        archive = os.path.join(store, item_id + ".tar.zst")
        entry["age_days"] = int((time.time() - os.stat(archive).st_mtime) // 86400)
        if entry["age_days"] <= ttl:
            refused = item_id
    entries.append(entry)
if refused or spec.get("exit"):
    code = "not_prunable" if refused else "archive_changed"
    sys.stderr.write("error: %s: %s\nnext step: look again\n" % (code, refused or ids[0]))
    sys.exit(2)
removed = []
if apply:
    removed = list(ids)
    if store:
        os.unlink(os.path.join(store, ids[0] + ".tar.zst"))
sys.stdout.write(json.dumps({"kind": "retention-prune", "mode": "apply" if apply else "dry-run",
                             "ttl_days": ttl, "archives": entries, "result": {"removed": removed}}))
"""

GEN = "2026-11-19T00:00:00Z"
UNATT = {"cleanup": True, "prune": True, "keep_recent": 5, "ttl_days": TTL,
         "prune_max_per_run": CAP}


class Phase(tur.Scratch):
    """A scratch repository adopted with an unattended policy that has `prune` true,
    the prune stub committed, and the report of three old archives."""

    def setUp(self):
        super().setUp()
        (self.repo / rs.SCRIPT).write_text(PRUNE_STUB)
        self.adopt_unattended(tur.policy_with(unattended=dict(UNATT)))
        self.state = rp.load(self.repo)
        self.scenario = self.outside / "scenario.json"
        self.lines, self.said = [], []
        self.write_scenario({})
        self.rep = report([archive("a-oldest", 90, modified="2026-03-01T00:00:00Z"),
                           archive("b-mid", 60, modified="2026-03-02T00:00:00Z"),
                           archive("c-new", 40, modified="2026-03-03T00:00:00Z")])
        self.env = {"STUB_REPORT": str(self.put_report(self.rep)),
                    "STUB_SCENARIO": str(self.scenario)}

    def write_scenario(self, scenario):
        self.scenario.write_text(json.dumps(scenario))

    def observer(self, *line):
        self.lines.append(line)

    def go(self, *, observer=None, load=None, **env):
        """Run the phase; `load` replaces `retention_policy.load` (a callable of the
        call number and the real state)."""
        self.marker.unlink(missing_ok=True)
        environ = rs.pinned_env(STUB_MARKER=str(self.marker), **{**self.env, **env})
        calls = {"n": 0}
        real = rp.load

        def loader(target):
            calls["n"] += 1
            state = real(target)
            return load(calls["n"], state) if load else state

        with mock.patch.dict(os.environ, environ, clear=True), \
                mock.patch.object(rp, "load", loader):
            return rpr.run_phase(self.repo, dict(UNATT), self.state.digest, self.said.append,
                                 observer=observer or self.observer, audit_where="/audit")

    def verbs(self):
        """The engine calls but the report: `prune ID...` or `prune --apply ID`."""
        found = []
        for call in self.script_calls():
            argv = call["argv"][1:]
            if argv[0] != "report":
                found.append(" ".join(argv[:argv.index("--json")]))
        return found

    def reports(self):
        return [c for c in self.script_calls() if c["argv"][1] == "report"]

    def audit(self):
        return [(l[0], l[2], l[1]) for l in self.lines]

    def assert_stopped(self, result, step, item_id, audit):
        self.assertEqual(result.outcome, rpr.STOPPED)
        self.assertEqual((result.stop["step"], result.stop["item_id"]), (step, item_id))
        self.assertEqual(self.audit()[-1], audit)

    def tree(self):
        return tc.tree_hash(self.repo) if hasattr(tc, "tree_hash") else tur.tree_hash(self.repo)


class TestHappyPath(Phase):
    def test_one_report_one_dry_run_and_one_apply_per_id_in_order(self):
        before = self.tree()
        result = self.go()
        self.assertEqual(result.outcome, rpr.DONE)
        root = str(self.repo.resolve())
        self.assertEqual(self.verbs(), [
            "prune a-oldest b-mid c-new",
            "prune a-oldest --apply", "prune b-mid --apply", "prune c-new --apply"])
        self.assertEqual(len(self.reports()), 1)
        tail = ["--json", "--ttl-days", "30", "--repo-root", root]
        for call in self.script_calls()[1:]:
            self.assertEqual(call["argv"][-5:], tail)
            self.assertNotIn("--archive-root", call["argv"])
        self.assertEqual(self.audit(), [("prune", "started", None)] + [("prune", "ok", i) for i in
                                                                      ("a-oldest", "b-mid", "c-new")])
        self.assertEqual([e["result"] for e in result.results], ["done"] * 3)
        self.assertEqual(result.digest, rpr.prune_digest(result.plan))
        self.assertTrue(all(l[5] == result.digest for l in self.lines))
        self.assertEqual(before, self.tree())

    def test_the_cap_and_the_order_reach_the_engine_as_selected(self):
        self.rep["archives"].append(archive("d-newest", 35, modified="2026-03-04T00:00:00Z"))
        self.rep["finished"].append(rs.finished("d-newest", folder=False))
        self.rep["totals"]["finished"] = 4
        self.env["STUB_REPORT"] = str(self.put_report(self.rep))
        result = self.go()
        self.assertIsNotNone(result.plan, result.error)
        self.assertEqual(result.plan.ids, ("a-oldest", "b-mid", "c-new"))
        self.assertEqual(result.plan.capped, 1)
        self.assertNotIn("d-newest", " ".join(self.verbs()))

    def test_an_empty_selection_writes_no_line_and_calls_nothing_more(self):
        self.rep["archives"] = []
        self.env["STUB_REPORT"] = str(self.put_report(self.rep))
        result = self.go()
        self.assertEqual((result.outcome, self.lines, self.verbs()), (rpr.NOTHING_TO_PRUNE, [], []))
        self.assertEqual(len(self.reports()), 1)

    def test_an_old_archive_whose_folder_is_present_is_never_named(self):
        # the wedge hazard: the engine would delete it, so no prune call may name it
        rep = report([archive("a-oldest", 90), archive("kept-folder", 99)], folders={"kept-folder"})
        self.env["STUB_REPORT"] = str(self.put_report(rep))
        result = self.go()
        self.assertEqual(result.outcome, rpr.DONE)
        self.assertNotIn("kept-folder", " ".join(self.verbs()))
        self.assertEqual(result.plan.skipped, (("kept-folder", rpr.FOLDER_PRESENT),))

    def test_an_id_under_removal_is_never_applied(self):
        rep = report([archive("a-oldest", 90), archive("half", 99)], removing=["half"])
        self.env["STUB_REPORT"] = str(self.put_report(rep))
        self.go()
        self.assertNotIn("half", " ".join(self.verbs()))


class TestPolicyReread(Phase):
    def swap(self, n_at, **change):
        def load(n, state):
            if n < n_at:
                return state
            if "prune" in change:
                return dataclasses.replace(state, unattended={**state.unattended, "prune": False})
            if "ordinary" in change:
                return dataclasses.replace(state, unattended=None)
            return dataclasses.replace(state, digest="0" * 64)
        return load

    def test_a_change_before_the_report_stops_before_any_call(self):
        before = self.tree()
        result = self.go(load=self.swap(1))
        self.assert_stopped(result, "policy", None, ("policy", "stopped", None))
        self.assertEqual((self.script_calls(), result.apply_attempted), ([], False))
        self.assertEqual(before, self.tree())

    def test_a_change_before_the_dry_run_stops_after_the_report_and_the_started_line(self):
        result = self.go(load=self.swap(2))
        self.assert_stopped(result, "policy", None, ("policy", "stopped", None))
        self.assertEqual((len(self.reports()), self.verbs()), (1, []))
        self.assertEqual(self.audit()[0], ("prune", "started", None))

    def test_a_change_before_the_second_apply_leaves_the_first_done(self):
        result = self.go(load=self.swap(4))
        self.assert_stopped(result, "policy", "b-mid", ("policy", "stopped", "b-mid"))
        self.assertEqual(self.verbs(), ["prune a-oldest b-mid c-new", "prune a-oldest --apply"])
        self.assertEqual([e["result"] for e in result.results], ["done", "stopped", "not-attempted"])
        self.assertTrue(result.apply_attempted)

    def test_prune_withdrawn_stops_the_phase(self):
        for n in (1, 2, 4):
            with self.subTest(call=n):
                self.lines.clear()
                result = self.go(load=self.swap(n, prune=True))
                self.assertEqual(result.stop["step"], "policy")
                self.assertEqual(self.audit()[-1][:2], ("policy", "stopped"))

    def test_a_record_swapped_for_an_ordinary_only_adoption_stops(self):
        for n in (1, 2, 4):
            with self.subTest(call=n):
                self.assertEqual(self.go(load=self.swap(n, ordinary=True)).stop["step"], "policy")

    def test_an_unreadable_policy_is_a_changed_policy(self):
        def boom(n, state):
            raise OSError("gone")
        self.assertEqual(self.go(load=boom).stop["step"], "policy")

    def test_an_interrupt_during_a_policy_reread_is_a_policy_interrupted_line(self):
        for n, item in ((1, None), (2, None), (4, "b-mid")):
            with self.subTest(call=n):
                self.lines.clear()

                def load(call, state, n=n):
                    if call == n:
                        raise KeyboardInterrupt
                    return state
                result = self.go(load=load)
                self.assert_stopped(result, "policy", item, ("policy", "interrupted", item))


class TestFreshReport(Phase):
    def test_an_unavailable_report_is_one_refused_line_and_no_call(self):
        self.env["STUB_REPORT"] = str(self.put_report("not json"))
        result = self.go()
        self.assert_stopped(result, "prune", None, ("prune", "refused", None))
        self.assertEqual((self.verbs(), result.apply_attempted), ([], False))

    def test_an_incomplete_report_is_refused(self):
        rep = dict(self.rep, complete=False, read_errors=[{"path": "x", "error": "y"}])
        self.env["STUB_REPORT"] = str(self.put_report(rep))
        result = self.go()
        self.assert_stopped(result, "prune", None, ("prune", "refused", None))
        self.assertEqual(self.verbs(), [])

    def test_an_interrupt_during_the_report_or_the_dry_run(self):
        with mock.patch.object(rpr.retention, "fetch", side_effect=KeyboardInterrupt):
            result = self.go()
        self.assert_stopped(result, "prune", None, ("prune", "interrupted", None))
        self.assertEqual(self.script_calls(), [])
        self.lines.clear()
        real = rpr.retention.launch_script

        def launch(root, *args, timeout):
            if args[0] != "report":
                raise KeyboardInterrupt
            return real(root, *args, timeout=timeout)
        with mock.patch.object(rpr.retention, "launch_script", launch):
            result = self.go()
        self.assert_stopped(result, "prune", None, ("prune", "interrupted", None))
        self.assertEqual(self.audit()[0], ("prune", "started", None))
        self.assertFalse(result.apply_attempted)


class TestDryRunEquivalence(Phase):
    def dry(self, **doc):
        body = {"kind": "retention-prune", "mode": "dry-run", "ttl_days": TTL,
                "archives": [{"work_item_id": i, "item": "finished"}
                             for i in ("a-oldest", "b-mid", "c-new")],
                "result": {"removed": []}}
        body.update(doc)
        return {"prune:dry": {"stdout": body}}

    def assert_no_apply(self, scenario):
        before = self.tree()
        self.write_scenario(scenario)
        result = self.go()
        self.assert_stopped(result, "prune", None, ("prune", "refused", None))
        self.assertEqual(len(self.verbs()), 1)
        self.assertFalse(result.apply_attempted)
        self.assertEqual(before, self.tree())
        self.lines.clear()
        return result

    def test_a_dry_run_that_matches_applies(self):
        self.write_scenario(self.dry())
        self.assertEqual(self.go().outcome, rpr.DONE)

    def test_one_id_too_few_one_too_many_a_twice_listed_id_or_another_class(self):
        names = ("a-oldest", "b-mid", "c-new")
        entry = lambda i, item="finished": {"work_item_id": i, "item": item}   # noqa: E731
        cases = {"too few": [entry(i) for i in names[:2]],
                 "too many": [entry(i) for i in names] + [entry("z")],
                 "twice": [entry(i) for i in names] + [entry("a-oldest")],
                 "class": [entry("a-oldest"), entry("b-mid"), entry("c-new", "open")],
                 "not a dict": ["a-oldest", "b-mid", "c-new"]}
        for label, archives in cases.items():
            with self.subTest(label):
                self.assert_no_apply(self.dry(archives=archives))

    def test_the_wrong_mode_ttl_kind_or_a_non_empty_removed(self):
        for label, doc in {"mode": {"mode": "apply"}, "ttl": {"ttl_days": 14},
                           "ttl bool": {"ttl_days": True}, "kind": {"kind": "retention-remove"},
                           "removed": {"result": {"removed": ["a-oldest"]}},
                           "no result": {"result": None}}.items():
            with self.subTest(label):
                self.assert_no_apply(self.dry(**doc))

    def test_a_refusal_a_status_a_timeout_or_unreadable_output(self):
        refusal = {"exit": 2, "stdout": "", "stderr": "error: not_prunable: x\nnext step: wait\n"}
        for label, spec in {"refusal": refusal, "status": {"exit": 3, "stdout": ""},
                            "not json": {"stdout": "nope"}, "list": {"stdout": "[]"}}.items():
            with self.subTest(label):
                result = self.assert_no_apply({"prune:dry": spec})
                if label == "refusal":
                    self.assertEqual(result.stop["engine_code"], "not_prunable")
        with mock.patch.object(rpr, "CALL_TIMEOUT_SECONDS", 1):
            self.write_scenario({"prune:dry": {"sleep": 30}})
            result = self.go()
        self.assertEqual(self.audit()[-1], ("prune", "refused", None))
        self.assertEqual((len(self.verbs()), result.apply_attempted), (1, False))

    def test_an_order_difference_is_not_a_difference(self):
        doc = self.dry()["prune:dry"]["stdout"]
        doc["archives"].reverse()
        self.write_scenario({"prune:dry": {"stdout": doc}})
        self.assertEqual(self.go().outcome, rpr.DONE)


class TestApplyFailures(Phase):
    def test_a_refusal_at_the_second_apply_stops_there_and_keeps_the_first(self):
        spec = {"exit": 2, "stdout": "", "stderr": "error: archive_changed: b-mid\nnext step: look\n"}
        self.write_scenario({"prune --apply:b-mid": spec})
        result = self.go()
        self.assert_stopped(result, "prune", "b-mid", ("prune", "failed", "b-mid"))
        self.assertEqual(result.stop["engine_code"], "archive_changed")
        self.assertEqual(self.verbs()[-1], "prune b-mid --apply")
        self.assertEqual(len(self.verbs()), 3)
        self.assertEqual([e["result"] for e in result.results], ["done", "stopped", "not-attempted"])
        self.assertEqual(result.done, 1)

    def apply_stops(self, spec):
        self.write_scenario({"prune --apply:a-oldest": spec})
        result = self.go()
        self.assert_stopped(result, "prune", "a-oldest", ("prune", "failed", "a-oldest"))
        self.assertEqual(len(self.verbs()), 2)
        return result

    def test_a_status_unreadable_output_or_a_wrong_removed_stops(self):
        for spec in ({"exit": 1, "stdout": ""}, {"stdout": "nope"},
                     {"stdout": {"kind": "retention-prune", "mode": "apply", "ttl_days": TTL,
                                 "result": {"removed": ["other"]}}},
                     {"stdout": {"kind": "retention-prune", "mode": "apply", "ttl_days": TTL,
                                 "result": {"removed": []}}},
                     {"stdout": {"kind": "retention-prune", "mode": "dry-run", "ttl_days": TTL,
                                 "result": {"removed": ["a-oldest"]}}}):
            with self.subTest(spec=spec):
                self.lines.clear()
                self.apply_stops(spec)

    def test_a_timeout_stops_at_that_id(self):
        with mock.patch.object(rpr, "CALL_TIMEOUT_SECONDS", 1):
            self.apply_stops({"sleep": 30})

    def test_an_interrupt_during_an_apply_stops_at_that_id(self):
        real = rpr.retention.launch_script
        seen = {"n": 0}

        def launch(root, *args, timeout):
            seen["n"] += args[0] != "report"
            if seen["n"] == 2:          # the dry run is the first engine call
                raise KeyboardInterrupt
            return real(root, *args, timeout=timeout)
        with mock.patch.object(rpr.retention, "launch_script", launch):
            result = self.go()
        self.assert_stopped(result, "prune", "a-oldest", ("prune", "interrupted", "a-oldest"))
        self.assertTrue(result.apply_attempted)
        self.assertEqual(len(result.calls), 2)      # the interrupted call never ran the stub


class TestAuditFailures(Phase):
    def failing(self, at):
        count = {"n": 0}

        def observer(*line):
            count["n"] += 1
            if count["n"] == at:
                raise OSError("disk full")
            self.lines.append(line)
        return observer

    def test_the_started_line_unwritable_issues_no_prune_call(self):
        before = self.tree()
        result = self.go(observer=self.failing(1))
        self.assertEqual(result.outcome, rpr.STOPPED)
        self.assertEqual((self.verbs(), result.apply_attempted), ([], False))
        self.assertIn("disk full", result.audit_error)
        self.assertEqual(before, self.tree())

    def test_a_write_failure_after_the_second_apply_stops_before_the_third(self):
        result = self.go(observer=self.failing(3))     # started, a ok, b ok(fails)
        self.assertEqual(result.outcome, rpr.STOPPED)
        self.assertEqual(self.verbs()[-1], "prune b-mid --apply")
        self.assertEqual(len(self.verbs()), 3)
        self.assertEqual([e["result"] for e in result.results], ["done", "done", "not-attempted"])
        self.assertIn("had succeeded", result.error)
        self.assertIsNotNone(result.audit_error)

    def interrupting(self, at):
        count = {"n": 0}

        def observer(*line):
            count["n"] += 1
            if count["n"] == at:
                raise KeyboardInterrupt
            self.lines.append(line)
        return observer

    def test_an_interrupt_while_the_started_line_is_written_stops_interrupted(self):
        before = self.tree()
        result = self.go(observer=self.interrupting(1))
        self.assert_stopped(result, "prune", None, ("prune", "interrupted", None))
        self.assertEqual((self.verbs(), result.calls, result.apply_attempted), ([], [], False))
        self.assertIn("retention prune: stopped after 0 of 3 archives; interrupted", self.said)
        self.assertTrue(all(e["result"] in ("not-attempted", "stopped") for e in result.results))
        self.assertEqual(before, self.tree())
        self.assertEqual(self.lines[-1][3:5], (None, "interrupted"))

    def test_an_interrupt_while_an_ok_line_is_written_says_the_archive_is_deleted(self):
        result = self.go(observer=self.interrupting(3))     # started, a ok, b ok (interrupted)
        self.assert_stopped(result, "prune", "b-mid", ("prune", "interrupted", "b-mid"))
        for text in ("interrupted", "the apply had succeeded", "the archive is deleted"):
            self.assertIn(text, result.error)
        self.assertEqual(self.lines[-1][3], None)
        self.assertEqual(f"retention prune: b-mid: {self.lines[-1][4]}", result.error)
        self.assertEqual(self.verbs()[-1], "prune b-mid --apply")
        self.assertEqual(len(self.verbs()), 3)
        self.assertEqual([e["result"] for e in result.results], ["done", "done", "not-attempted"])
        self.assertTrue(result.apply_attempted)
        self.assertTrue(any("stopped after 2 of 3 archives" in s for s in self.said))

    def test_a_failing_line_for_a_stop_is_recorded_and_the_stop_stands(self):
        self.write_scenario({"prune:dry": {"stdout": "nope"}})
        result = self.go(observer=self.failing(2))
        self.assertEqual(result.outcome, rpr.STOPPED)
        self.assertIn("disk full", result.audit_error)
        self.assertEqual(self.verbs(), ["prune a-oldest b-mid c-new"])


class TestEngineFaithful(Phase):
    """The stub looks at each archive file on every call, as the real engine builds a
    new report per invocation."""

    def setUp(self):
        super().setUp()
        self.store = self.outside / "store"
        self.store.mkdir()
        for name, days in (("a-oldest", 90), ("b-mid", 60), ("c-new", 40)):
            path = self.store / f"{name}.tar.zst"
            path.write_bytes(b"x")
            self.age(name, days)
        self.env["STUB_ARCHIVES"] = str(self.store)

    def age(self, name, days):
        stamp = time.time() - days * 86400 - 60
        os.utime(self.store / f"{name}.tar.zst", (stamp, stamp))

    def observer_hook(self, action):
        def observer(*line):
            self.lines.append(line)
            if line[2] == "started":
                action()
        return observer

    def test_a_changed_mtime_that_stays_old_is_accepted_and_applied(self):
        result = self.go(observer=self.observer_hook(lambda: self.age("b-mid", 45)))
        self.assertEqual(result.outcome, rpr.DONE)
        self.assertFalse(list(self.store.iterdir()))

    def test_an_archive_that_became_young_makes_the_dry_run_refuse(self):
        result = self.go(observer=self.observer_hook(lambda: self.age("b-mid", 5)))
        self.assert_stopped(result, "prune", None, ("prune", "refused", None))
        self.assertEqual(result.stop["engine_code"], "not_prunable")
        self.assertEqual((len(self.verbs()), result.apply_attempted), (1, False))
        self.assertEqual(len(list(self.store.iterdir())), 3)

    def test_an_archive_that_became_young_after_the_dry_run_makes_its_apply_refuse(self):
        seen = {"n": 0}
        real = rpr.retention.launch_script

        def launch(root, *args, timeout):
            seen["n"] += args[0] != "report"
            if seen["n"] == 3:          # the second apply: b-mid is touched before its own
                self.age("b-mid", 5)
            return real(root, *args, timeout=timeout)
        with mock.patch.object(rpr.retention, "launch_script", launch):
            result = self.go()
        self.assert_stopped(result, "prune", "b-mid", ("prune", "failed", "b-mid"))
        self.assertEqual(result.stop["engine_code"], "not_prunable")
        self.assertEqual(sorted(p.name for p in self.store.iterdir()), ["b-mid.tar.zst", "c-new.tar.zst"])
        self.assertEqual(len(self.verbs()), 3)


class TestAuditStepVocabulary(unittest.TestCase):
    def test_prune_is_a_step_with_each_phase_result(self):
        self.assertIn("prune", tur.ru.STEPS)
        for result in ("started", "ok", "failed", "interrupted", "refused"):
            self.assertIn(result, tur.ru.RESULTS)


class TestRunHelpers(unittest.TestCase):
    def test_the_closing_clause_defaults_to_the_confirmed_runs_line(self):
        source = Path(rr.__file__).read_text()
        self.assertIn("; prune was not run", source)

    def test_policy_holds_calls_the_extra_predicate_last(self):
        state = rp.PolicyState(rp.ADOPTED, digest="d", unattended={"cleanup": True, "prune": False})
        with mock.patch.object(rp, "load", return_value=state):
            self.assertTrue(rr.policy_holds("/x", "d", unattended=True))
            self.assertFalse(rr.policy_holds("/x", "d", unattended=True,
                                             extra=rpr.prune_still_allowed))
            self.assertFalse(rr.policy_holds("/x", "other", unattended=True, extra=lambda s: True))
        with mock.patch.object(rp, "load", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                rr.policy_holds("/x", "d")


# ---------------------------------------------------------------------------
# The command (CP3): the cleanup phase, then the prune phase, through `cli.main`
# ---------------------------------------------------------------------------

COMBINED_STUB = (
    "import sys\nSRC_PRUNE = %r\nSRC_RUN = %r\n"
    "exec(compile(SRC_PRUNE if sys.argv[1] == 'prune' else SRC_RUN, 'stub', 'exec'))\n"
) % (PRUNE_STUB, tur.trun.RUN_STUB)
OLD_ARCHIVES = ("old-a", "old-b", "old-c")
CLEANED = tur.full_run("item-00", "item-01", "item-02")
PRUNED = ["prune:old-a", "prune --apply:old-a", "prune --apply:old-b", "prune --apply:old-c"]
IRREVERSIBLE = ("a deleted archive cannot be undone; the archive store is "
                "~/.local/share/workflow-archive, which the Manager does not back up")


def with_archives(rep, ids=OLD_ARCHIVES, *, ages=(90, 60, 40)):
    """`rep` plus archives of finished items whose folder is gone."""
    rep = json.loads(json.dumps(rep))
    rep["archives"] = [archive(i, age, modified=f"2026-03-0{n + 1}T00:00:00Z")
                       for n, (i, age) in enumerate(zip(ids, ages))]
    for i in ids:
        gone = rs.finished(i, folder=False, archive=True)
        rep["finished"].append(gone)
    rep["totals"]["finished"] = len(rep["finished"])
    return rep


class Command(tur.Cmd):
    """The unattended command with `unattended.prune` true and a stub that answers
    the cleanup verbs and `prune`."""

    PRUNE_ON = True

    def setUp(self):
        super().setUp()
        (self.repo / rs.SCRIPT).write_text(COMBINED_STUB)
        self.adopt_unattended(tur.policy_with(unattended=dict(UNATT, prune=self.PRUNE_ON)))
        self.rep = with_archives(self.rep)

    def doc(self, out):
        return json.loads(out.out)

    def planned(self, rep=None):
        return tur.planned(rc.select(rp.load(self.repo), rep or self.rep))

    def prune_lines(self):
        return [l for l in self.lines() if l["step"] == "prune"]


class TestCleansAndPrunes(Command):
    def test_calls_in_order_a_report_then_the_dry_run_then_the_applies(self):
        self.assertEqual(self.planned(), ["item-00", "item-01", "item-02"], "fixture")
        out = self.go_u()
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertEqual(self.keys(), CLEANED + PRUNED)
        names = [c["argv"][1] for c in self.script_calls()]
        self.assertEqual(names.count("report"), 2)      # the preflight's and the phase's
        self.assertEqual(names[-5], "report")
        self.assertEqual(len(self.script_calls()), 1 + 9 + 1 + 4)

    def test_the_text_has_the_cleanup_lines_the_prune_lines_and_the_audit_line_last(self):
        out = self.go_u()
        text = out.out.splitlines()
        self.assertEqual(text[-1], f"  audit: {self.audit_file}")
        self.assertEqual(text[-2], f"retention prune: done, 3 of 3 archives deleted; {IRREVERSIBLE}")
        self.assertEqual(text[-5:-2], [f"  old-{x}: pruned" for x in "abc"])
        done = [l for l in text if l.startswith("retention cleanup: done")]
        self.assertEqual(len(done), 1)
        self.assertNotIn("prune was not run", out.out)
        self.assertTrue(done[0].endswith("(the review folders were untracked)"), done[0])

    def test_the_audit_has_the_cleanup_lines_then_the_prune_lines(self):
        self.go_u()
        lines = self.lines()
        self.assertEqual([(l["step"], l["result"], l["item_id"]) for l in lines[10:]],
                         [("prune", "started", None)] + [("prune", "ok", i) for i in OLD_ARCHIVES])
        digest = rpr.prune_digest(rpr.select(self.rep, dict(UNATT),
                                            policy_digest=rp.load(self.repo).digest))
        self.assertTrue(all(l["plan_digest"] == digest for l in lines[10:]))
        self.assertEqual({l["policy_digest"] for l in lines}, {rp.load(self.repo).digest})
        self.assertEqual(len({l["run_id"] for l in lines}), 1)

    def test_a_run_with_nothing_to_clean_still_prunes(self):
        self.rep = with_archives(tc.many(5, mib=2))
        out = self.go_u(rep=self.rep)
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertEqual(self.keys(), PRUNED)
        self.assertIn("nothing to do", out.out)
        self.assertEqual(out.out.splitlines()[-1], f"  audit: {self.audit_file}")
        self.assertIn(IRREVERSIBLE, out.out)

    def test_nothing_eligible_prints_its_own_lines_then_the_prune_lines_then_audit(self):
        self.adopt_unattended(tur.policy_with(unattended=dict(UNATT, keep_recent=100)))
        out = self.go_u()
        text = out.out.splitlines()
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertTrue(text[0].startswith("retention cleanup: nothing eligible ("), text[0])
        self.assertEqual(text[-1], f"  audit: {self.audit_file}")
        self.assertEqual(self.keys(), PRUNED)
        self.assertEqual([(l["step"], l["result"]) for l in self.lines()],
                         [("plan", "nothing-eligible"), ("prune", "started")] +
                         [("prune", "ok")] * 3)

    def test_nothing_to_prune_prints_one_line_and_its_skips_and_no_audit_line(self):
        rep = tc.many(5, mib=2)
        rep["archives"] = [archive("old-a", 10), archive("kept", 90)]
        rep["finished"].append(tc.entry("kept", archive=True))
        rep["totals"]["finished"] = len(rep["finished"])
        out = self.go_u(rep=rep)
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertIn("nothing to do", out.out)
        tail = out.out.splitlines()[-2:]
        self.assertEqual(tail[0], "retention prune: nothing to prune (ttl_days 30, at most 3 per run)")
        self.assertEqual(tail[1], "  skipped: kept (review-folder-present)")
        self.assertNotIn("audit:", out.out)
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.keys(), [])

    def test_the_confirmed_run_never_prunes_and_keeps_its_bytes(self):
        out = self.go(confirm=rc.sentence(self.digest()), rep=self.rep)
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertTrue(out.out.endswith(
            "(the review folders were untracked); prune was not run\n"), out.out)
        self.assertEqual(self.keys(), CLEANED)

    def test_cleanup_false_with_prune_true_is_still_refused(self):
        self.adopt_unattended(tur.policy_with(unattended=dict(UNATT, cleanup=False)))
        out = self.go_u()
        self.assertEqual((out.code, out.out), (2, ""))
        self.assertIn("unattended.cleanup is false", out.err)
        self.assertEqual(self.keys(), [])
        self.assertEqual([(l["step"], l["result"]) for l in self.lines()], [("preflight", "refused")])


class TestPruneDisabled(Command):
    PRUNE_ON = False

    def test_the_text_audit_and_calls_are_the_cleanups_alone(self):
        out = self.go_u()
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertEqual(self.keys(), CLEANED)
        self.assertTrue(out.out.endswith(
            f"(the review folders were untracked); prune was not run\n  audit: {self.audit_file}\n"))
        self.assertEqual(len(self.lines()), 10)
        self.assertEqual({l["step"] for l in self.lines()}, {"plan", "archive", "verify", "remove"})

    def test_the_document_has_the_prune_key_disabled(self):
        doc = self.doc(self.go_u(extra=("--unattended", "--json")))
        self.assertEqual(doc["prune"], {"enabled": False, "outcome": "disabled", "ttl_days": None,
                                        "max_per_run": None, "plan_digest": None, "ids": [],
                                        "results": [], "skipped": []})
        self.assertEqual((doc["schema_version"], doc["outcome"], doc["done"]), (1, "done", 3))

    def test_nothing_to_do_text_is_todays(self):
        out = self.go_u(rep=tc.many(5, mib=2))
        self.assertIn("nothing to do", out.out)
        self.assertNotIn("audit:", out.out)
        self.assertNotIn("retention prune", out.out)


class TestPruneStops(Command):
    def apply_refusal(self, item):
        return {f"prune --apply:{item}": {"exit": 2, "stdout": "",
                                          "stderr": "error: archive_changed: x\nnext step: look\n"}}

    def test_an_apply_failure_after_a_clean_cleanup_exits_1(self):
        out = self.go_u(self.apply_refusal("old-b"))
        self.assertEqual(out.code, 1, out.out)
        self.assertEqual(self.keys(), CLEANED + PRUNED[:3])
        self.assertIn("error: retention prune: old-b:", out.err)
        self.assertIn("next: look", out.err)
        self.assertEqual(out.out.splitlines()[-1], f"  audit: {self.audit_file}")
        self.assertIn("retention prune: stopped after 1 of 3 archives", out.out)
        self.assertIn(f"1 of 3 archives were deleted before the stop; {IRREVERSIBLE}", out.out)
        self.assertEqual(self.prune_lines()[-1]["result"], "failed")

    def test_an_apply_failure_with_nothing_to_clean_exits_1(self):
        out = self.go_u(self.apply_refusal("old-a"), rep=with_archives(tc.many(5, mib=2)))
        self.assertEqual(out.code, 1, out.out)
        self.assertEqual(self.keys(), PRUNED[:2])
        self.assertIn("retention prune: stopped after 0 of 3 archives", out.out)
        self.assertNotIn("were deleted before the stop", out.out)

    def test_a_dry_run_that_differs_with_nothing_to_clean_exits_2_and_applies_nothing(self):
        bad = {"prune:dry": {"stdout": {"kind": "retention-prune", "mode": "dry-run",
                                        "ttl_days": 30, "archives": [], "result": {"removed": []}}}}
        out = self.go_u(bad, rep=with_archives(tc.many(5, mib=2)))
        self.assertEqual(out.code, 2, out.out)
        self.assertEqual(self.keys(), ["prune:old-a"])
        self.assertIn("error: retention prune:", out.err)

    def test_a_dry_run_that_differs_after_a_cleanup_exits_1(self):
        bad = {"prune:dry": {"stdout": "nope"}}
        out = self.go_u(bad)
        self.assertEqual(out.code, 1, out.out)
        self.assertEqual(self.keys(), CLEANED + ["prune:old-a"])

    def test_an_unreadable_report_in_the_phase_stops_it_with_nothing_to_clean(self):
        real, seen = tur.retention.fetch, {"n": 0}

        def fetch(target):
            seen["n"] += 1
            return real(target) if seen["n"] == 1 else real(target.parent / "absent")
        out = self.go_u(rep=tc.many(5, mib=2),
                        patches=[mock.patch.object(tur.retention, "fetch", fetch)])
        self.assertEqual(out.code, 2, out.out)
        self.assertEqual(self.keys(), [])
        self.assertEqual([(l["step"], l["result"]) for l in self.lines()], [("prune", "refused")])
        self.assertIn("error: retention prune: the fresh report is not available", out.err)

    def test_a_policy_that_stops_allowing_prune_stops_before_any_prune_call(self):
        real = tur.rr.policy_holds

        def holds(*args, extra=None, **kw):
            return False if extra is not None else real(*args, extra=extra, **kw)
        out = self.go_u(patches=[mock.patch.object(tur.rr, "policy_holds", holds)])
        self.assertEqual(out.code, 1, out.out)         # the cleanup attempted something
        self.assertEqual([k for k in self.keys() if k.startswith("prune")], [])
        self.assertEqual((self.lines()[-1]["step"], self.lines()[-1]["result"]), ("policy", "stopped"))
        self.assertIn("error: retention prune: the policy changed", out.err)

    def test_a_cleanup_stop_calls_no_prune_and_exits_as_the_cleanup_does(self):
        stop = {"archive --apply:item-01": tur.refusal("place_failed", "nope")}
        out = self.go_u(stop)
        self.assertEqual(out.code, 1)
        self.assertEqual([k for k in self.keys() if k.startswith("prune")], [])
        self.assertEqual(len([c for c in self.script_calls() if c["argv"][1] == "report"]), 1)
        self.assertNotIn("retention prune", out.out)
        self.assertEqual(out.out.splitlines()[-1], f"  audit: {self.audit_file}")
        self.assertIn("error: retention cleanup: item-01:", out.err)

    def test_the_audit_stop_after_an_apply_says_it_had_succeeded(self):
        out = self.go_u(patches=[self.write_seam(13)])   # the line after old-b's apply
        self.assertEqual(out.code, 1, out.out)
        self.assertIn("the apply had succeeded", out.err)
        self.assertEqual(self.keys(), CLEANED + PRUNED[:3])


class TestPruneJson(Command):
    def go_j(self, *a, **kw):
        return self.go_u(*a, extra=("--unattended", "--json"), **kw)

    def test_a_done_document_and_only_the_document_on_stdout(self):
        out = self.go_j()
        doc = self.doc(out)
        self.assertEqual(out.code, 0, out.err)
        self.assertEqual((doc["schema_version"], doc["outcome"], doc["exit_code"], doc["done"]),
                         (1, "done", 0, 3))
        prune = doc["prune"]
        self.assertEqual((prune["enabled"], prune["outcome"], prune["ttl_days"],
                          prune["max_per_run"]), (True, "done", 30, 3))
        self.assertEqual(prune["ids"], list(OLD_ARCHIVES))
        self.assertEqual([(r["id"], r["result"]) for r in prune["results"]],
                         [(i, "done") for i in OLD_ARCHIVES])
        self.assertEqual(prune["plan_digest"], self.prune_lines()[0]["plan_digest"])
        self.assertEqual(prune["skipped"], [])
        self.assertEqual(doc["audit"]["lines_written"], 14)
        self.assertIn("  old-a: pruned", out.err)
        self.assertIn(IRREVERSIBLE, out.err)
        self.assertNotIn("old-a", out.out.replace('"old-a"', ""))

    def test_a_prune_stop_document(self):
        out = self.go_j({"prune --apply:old-b": {"exit": 2, "stdout": "",
                                                 "stderr": "error: archive_changed: x\nnext step: look\n"}})
        doc = self.doc(out)
        self.assertEqual((out.code, doc["exit_code"], doc["outcome"]), (1, 1, "stopped"))
        self.assertEqual({k: doc["stopped"][k] for k in ("step", "item_id", "engine_code")},
                         {"step": "prune", "item_id": "old-b", "engine_code": "archive_changed"})
        self.assertEqual(doc["stopped"]["next_step"], "look")
        self.assertEqual([r["result"] for r in doc["prune"]["results"]],
                         ["done", "stopped", "not-attempted"])
        self.assertEqual(doc["prune"]["outcome"], "stopped")
        self.assertEqual(doc["done"], 3)     # the cleanup phase's own count

    def test_a_cleanup_stop_document_says_not_attempted(self):
        out = self.go_j({"archive --apply:item-01": tur.refusal("place_failed", "nope")})
        doc = self.doc(out)
        self.assertEqual((out.code, doc["outcome"], doc["stopped"]["step"]), (1, "stopped", "archive"))
        self.assertEqual(doc["prune"], {"enabled": True, "outcome": "not-attempted", "ttl_days": 30,
                                        "max_per_run": 3, "plan_digest": None, "ids": [],
                                        "results": [], "skipped": []})

    def test_a_nothing_to_prune_document_lists_the_skips(self):
        rep = tc.many(5, mib=2)
        rep["archives"] = [archive("kept", 90)]
        rep["finished"].append(tc.entry("kept", archive=True))
        rep["totals"]["finished"] = len(rep["finished"])
        out = self.go_j(rep=rep)
        doc = self.doc(out)
        self.assertEqual((out.code, doc["outcome"]), (0, "nothing-to-do"))
        self.assertEqual(doc["prune"]["outcome"], "nothing-to-prune")
        self.assertEqual(doc["prune"]["skipped"], [{"id": "kept", "reason": "review-folder-present"}])
        self.assertEqual((doc["prune"]["ids"], doc["prune"]["plan_digest"]), ([], None))
        self.assertIn("nothing to prune", out.err)

    def test_a_prune_stop_with_nothing_to_clean_keeps_the_cleanups_outcome_stopped(self):
        out = self.go_j({"prune:dry": {"stdout": "nope"}}, rep=with_archives(tc.many(5, mib=2)))
        doc = self.doc(out)
        self.assertEqual((out.code, doc["exit_code"], doc["outcome"]), (2, 2, "stopped"))
        self.assertEqual(doc["stopped"]["step"], "prune")
        self.assertEqual(doc["prune"]["outcome"], "stopped")


class TestHelpAndWording(unittest.TestCase):
    def test_the_old_statements_are_gone_and_the_new_ones_say_the_limits(self):
        text = " ".join(help_of(tc.COMMAND).split())
        self.assertNotIn("Prune is never run.", text)
        self.assertNotIn("Prune is never run\"", text)
        for words in ("Prune is never run by the confirmed run", "unattended.prune is true",
                      "older than unattended.ttl_days", "unattended.prune_max_per_run",
                      "cannot be undone", "not backed up", "prune --apply was attempted"):
            self.assertIn(words, text)
        self.assertEqual(text.count("Prune is never run"), 1)

    def test_the_policy_page_does_not_say_prune_is_never_run(self):
        page = " ".join((REPO_ROOT / "docs" / "retention.md").read_text().split())
        self.assertNotIn("prune is never run.", page)
        self.assertIn("prune is run only by `--unattended`, under an adopted `unattended.prune`", page)

    def test_the_unattended_run_section_names_the_prune_phase_as_its_added_action(self):
        page = " ".join((REPO_ROOT / "docs" / "retention.md").read_text().split())
        self.assertNotIn("it adds authority and evidence, never new actions", page)
        self.assertIn("the only action it adds is the prune phase, under an adopted `unattended.prune` "
                      "(see [The unattended prune](#the-unattended-prune))", page)
        self.assertIn("(the prune phase, below, adds its own)", page)


if __name__ == "__main__":
    unittest.main()
