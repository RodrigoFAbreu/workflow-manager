#!/usr/bin/env python3
"""The unattended retention prune: its selection, plan digest and argv forms (CP1).

Hermetic and pure: `retention_prune.select` is driven with report dicts built from
the shape of the engine's report (`scripts/workflow_retention.py`, `_assemble`:
`archives[]` with `age_days`, `modified` and `item`, `finished[]` with
`review_folder.present`, `removing[]`). No process, no network, no file is written.
"""

from __future__ import annotations

import ast
import unittest

import support
from support import REPO_ROOT

import test_retention_status as rs
from workflow_manager import retention_prune as rpr

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
    def test_the_module_starts_no_process_and_reads_no_file(self):
        tree = ast.parse((REPO_ROOT / "src" / "workflow_manager" / "retention_prune.py")
                         .read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(imported - {"__future__"}, {"hashlib", "json", "dataclasses"})
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(calls & {"open", "exec", "eval", "__import__"})

    def test_select_does_not_change_its_arguments(self):
        import copy
        rep, policy = report([archive("a", 40), archive("b", 99)], folders={"b"}), unattended()
        before = copy.deepcopy((rep, policy))
        rpr.select(rep, policy)
        self.assertEqual((rep, policy), before)


if __name__ == "__main__":
    unittest.main()
