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

import test_retention_cleanup as tc
import test_retention_status as rs
import test_retention_unattended_run as tur
from workflow_manager import retention_policy as rp, retention_prune as rpr, retention_run as rr

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


if __name__ == "__main__":
    unittest.main()
