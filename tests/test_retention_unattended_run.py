#!/usr/bin/env python3
"""The unattended retention cleanup: its authority check (CP1) and the `keep_recent`
selection.

Hermetic: the scratch base of `test_retention_cleanup` (a managed repository with the
stub script, the policy committed), no network, nothing written into this
repository. The authority checks are asserted at the function and through
`retention_cleanup.preflight`, each with its no-write proof; rows d to f are
stronger: no script call at all and no `git` process.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from support import REPO_ROOT
from unittest import mock

import test_retention_cleanup as tc
import test_retention_status as rs
from test_operator_ux import git, tree_hash
from workflow_manager import retention_alert as ra, retention_cleanup as rc, retention_policy as rp
from workflow_manager import retention_unattended as ru

UNATTENDED = {"cleanup": True, "prune": False, "keep_recent": 5, "ttl_days": 30,
              "prune_max_per_run": 3}
THRESHOLDS = {"finished_items": 10, "finished_folder_mib": 500}
OLD, YOUNG = tc.OLD, tc.YOUNG


def policy_with(unattended=UNATTENDED, mode="both", **thresholds):
    policy = {"schema_version": 1, "mode": mode, "thresholds": thresholds or dict(THRESHOLDS)}
    if unattended is not None:
        policy["unattended"] = dict(unattended)
    return policy


def state_for(unattended, mode="both", **thresholds):
    """An adopted state: `unattended` is what the adoption authorises (None: nothing)."""
    policy = policy_with(unattended, mode, **thresholds)
    return rp.PolicyState(rp.ADOPTED, mode=mode, policy=policy, digest=rp.digest_of(policy),
                          unattended=unattended)


def newest_first(*entries, **overrides):
    return rs.report(*entries, **overrides)


def many(count, **kw):
    return tc.many(count, **kw)


def planned(plan):
    return [item.work_item_id for item in plan.items]


class TestRefusalFunction(unittest.TestCase):
    """Rows d, e and f as a pure function of the state."""

    def test_an_authorising_state_is_not_refused(self):
        self.assertIsNone(rc.unattended_refusal(state_for(UNATTENDED), tc.EXAMPLE_TARGET))

    def test_row_d_no_unattended_key(self):
        state = state_for(None)
        refusal = rc.unattended_refusal(state, tc.EXAMPLE_TARGET)
        self.assertEqual(refusal.cause, "retention cleanup: --unattended is not authorised: the "
                                        "adopted policy has no unattended key")
        self.assertIn("unattended key", refusal.step)

    def test_row_e_the_key_without_the_unattended_sentence(self):
        policy = policy_with()
        state = rp.PolicyState(rp.ADOPTED, mode="both", policy=policy,
                               digest=rp.digest_of(policy), unattended=None)
        refusal = rc.unattended_refusal(state, tc.EXAMPLE_TARGET)
        self.assertEqual(refusal.cause, "retention cleanup: --unattended is not authorised: the "
                                        "adoption does not hold the unattended sentence")
        self.assertIn("adopt-retention-policy", refusal.step)

    def test_row_f_cleanup_false(self):
        refusal = rc.unattended_refusal(state_for({**UNATTENDED, "cleanup": False, "prune": True}),
                                        tc.EXAMPLE_TARGET)
        self.assertEqual(refusal.cause, "retention cleanup: --unattended is not authorised: "
                                        "unattended.cleanup is false")

    def test_only_the_state_is_asked_never_the_policy_key(self):
        """The policy says cleanup true; the state, which the adoption record decides, says
        nothing: refused."""
        state = state_for(UNATTENDED)
        state = rp.PolicyState(**{**state.__dict__, "unattended": None})
        self.assertIn("does not hold the unattended sentence",
                      rc.unattended_refusal(state, tc.EXAMPLE_TARGET).cause)


class Scratch(tc.Base):
    """`Base` with the file and its adoption replaced by an unattended one."""

    def adopt_unattended(self, policy=None, *, ordinary=False):
        policy = policy or policy_with()
        path = rp.policy_path(self.repo)
        path.write_text(json.dumps(policy))
        digest = rp.digest_of(policy)
        if ordinary:   # a record the loader accepts, with the ordinary sentence only
            record = {"schema_version": rp.SCHEMA_VERSION, "sha256": digest,
                      "adopted_at": "2026-11-01T00:00:00Z",
                      "confirmation": rp.sentence(digest), "policy": policy}
            rp.record_path(self.repo).write_bytes(rp.serialize_record(record))
        else:
            rp.apply(self.repo, rp.usable_policy(self.repo), rp.unattended_sentence(digest))
        self.commit(self.repo, "adopt unattended")

    def pre(self, rep=None, *, unattended=True, git_raises=False):
        """Run `rc.preflight` in-process; returns the `Cleared` or the `Refusal`."""
        env = self.env()
        if rep is not None:
            env["STUB_REPORT"] = str(self.put_report(rep))
        self.marker.unlink(missing_ok=True)
        with mock.patch.dict(os.environ, env, clear=True), contextlib_git(git_raises):
            try:
                return rc.preflight(self.repo, self.VERSION, lambda: ra.SCRIPT_OK,
                                    unattended=unattended)
            except rc.Refusal as refusal:
                return refusal

    def assert_refused(self, result, cause):
        self.assertIsInstance(result, rc.Refusal)
        self.assertEqual(result.cause, cause)
        self.assertTrue(result.step)


def contextlib_git(raises):
    """With `raises`, any `git` the preflight starts fails the test."""
    if not raises:
        return contextlib.nullcontext()
    return mock.patch.object(rc, "_git", side_effect=AssertionError("git was started"))


NO_KEY = ("retention cleanup: --unattended is not authorised: the adopted policy has no "
          "unattended key")
ORDINARY = ("retention cleanup: --unattended is not authorised: the adoption does not hold the "
            "unattended sentence")
CLEANUP_FALSE = "retention cleanup: --unattended is not authorised: unattended.cleanup is false"


class TestPreflightAuthority(Scratch):
    def refused_without_a_process(self, cause):
        """Rows d to f: no script call at all, no `git`, the tree and the index untouched."""
        self.stale_index()
        before = tree_hash(self.repo)
        result = self.pre(self.rep_, git_raises=True)
        self.assert_refused(result, cause)
        self.assertEqual(self.script_calls(), [])
        self.assertEqual(tree_hash(self.repo), before)

    def setUp(self):
        super().setUp()
        self.rep_ = many(12, mib=2)

    def test_row_d_a_file_without_the_key(self):
        self.refused_without_a_process(NO_KEY)   # the base adoption has no key

    def test_row_e_an_ordinary_adoption_of_a_file_with_the_key(self):
        self.adopt_unattended(ordinary=True)
        state = rp.load(self.repo)
        self.assertEqual((state.state, state.unattended), (rp.ADOPTED, None))
        self.refused_without_a_process(ORDINARY)

    def test_row_f_cleanup_false(self):
        self.adopt_unattended(policy_with({**UNATTENDED, "cleanup": False, "prune": True}))
        self.refused_without_a_process(CLEANUP_FALSE)

    def test_an_authorised_adoption_passes_and_reads_the_report_once(self):
        self.adopt_unattended()
        result = self.pre(self.rep_)
        self.assertIsInstance(result, rc.Cleared)
        self.assertEqual(result.state.unattended["keep_recent"], 5)
        self.assertEqual([c["argv"][1] for c in self.script_calls()], ["report"])

    def test_without_the_flag_the_authority_is_not_asked(self):
        """The confirmed run keeps today's preflight: a file without the key passes."""
        result = self.pre(self.rep_, unattended=False)
        self.assertIsInstance(result, rc.Cleared)

    def test_the_existing_refusals_still_win(self):
        policy, record = rp.policy_path(self.repo), rp.record_path(self.repo)
        good_policy, good_record = policy.read_bytes(), record.read_bytes()
        cases = {}

        def not_adopted():
            record.unlink()
            cases["want"] = f"retention policy: {rp.NOT_ADOPTED}"

        def absent():
            record.unlink()
            policy.unlink()
            cases["want"] = "retention cleanup: no retention policy is adopted"

        def invalid():
            policy.write_text("{")
            cases["want"] = f"retention policy: {rp.INVALID}"

        def record_invalid():
            record.write_text("{")
            cases["want"] = f"retention policy: {rp.RECORD_INVALID}"

        def changed():
            policy.write_text(json.dumps(policy_with(finished_items=11)))
            cases["want"] = f"retention policy: {rp.CHANGED}"

        def mode():
            self.adopt({**tc.POLICY, "mode": "notify"})
            self.commit(self.repo, "notify")
            cases["want"] = "the adopted mode is notify"

        for setup in (not_adopted, absent, invalid, record_invalid, changed, mode):
            with self.subTest(setup=setup.__name__):
                self.adopt_unattended()
                setup()
                result = self.pre(self.rep_, git_raises=True)
                self.assertIsInstance(result, rc.Refusal)
                self.assertIn(cases["want"], result.cause)
                self.assertNotIn("--unattended", result.cause)
                self.assertEqual(self.script_calls(), [])
                git(self.repo, "reset", "-q", "--hard", "HEAD")
                policy.write_bytes(good_policy)
                record.write_bytes(good_record)


class TestKeepRecent(unittest.TestCase):
    def plan(self, keep, report=None, **thresholds):
        report = report or many(12)
        state = state_for({**UNATTENDED, "keep_recent": keep},
                          **(thresholds or {"finished_items": 10}))
        return rc.select(state, report)

    def test_three_keeps_nothing_beyond_the_engine(self):
        report = many(12)
        plain = rc.select(tc.adopted("both", finished_items=10), report)
        three = self.plan(3, report)
        self.assertEqual(planned(three), planned(plain))
        self.assertEqual(three.kept, ())

    def test_five_keeps_two_more_than_the_engine(self):
        report = many(12)   # item-00 is the oldest, item-11 the newest
        plan = self.plan(5, report)
        self.assertEqual(plan.kept, ("item-11", "item-10"))
        self.assertEqual((plan.keep_recent, plan.engine_keep), (5, 3))
        self.assertEqual(planned(plan), ["item-00", "item-01", "item-02"])
        self.assertNotIn("item-11", planned(plan))
        self.assertEqual(plan.skipped, ())          # kept items are not listed as skipped
        self.assertEqual(plan.candidates, 12)       # but they still count in the numbers

    def test_the_boundary_is_keep_minus_the_engines_three(self):
        """11 items reach the limit of 10 and two removals bring them below it: the two oldest,
        and with keep 5 the kept ones are the newest two, not three."""
        plan = self.plan(5, many(11))
        self.assertEqual(plan.kept, ("item-10", "item-09"))
        self.assertEqual(planned(plan), ["item-00", "item-01"])

    def test_a_keep_larger_than_the_list_ends_no_further_item_is_eligible(self):
        report = many(12)
        plan = self.plan(100, report)
        self.assertEqual(plan.items, ())
        self.assertEqual(plan.outcome, rc.EXHAUSTED)
        self.assertEqual(len(plan.kept), 12)
        self.assertIn("  after this run: finished items 12: finished items still reached; no "
                      "further item is eligible; running it again will not help",
                      rc.preview_lines(plan, tc.EXAMPLE_TARGET))

    def test_a_threshold_only_the_kept_items_hold_up_ends_exhausted(self):
        # 12 items, limit 1; keep 11 holds the 8 newest, the 4 others are planned and the
        # 8 kept ones keep the count above the limit
        plan = self.plan(11, many(12), finished_items=1)
        self.assertEqual(planned(plan), ["item-00", "item-01", "item-02", "item-03"])
        self.assertEqual(plan.outcome, rc.EXHAUSTED)
        self.assertEqual(plan.after["finished_items"], 8)

    def test_a_kept_entry_without_a_review_folder_still_counts_toward_the_keep(self):
        newest = tc.entry("item-11")
        newest["review_folder"]["present"] = False
        entries = [tc.entry(f"item-{n:02d}") for n in range(11)] + [newest]
        report = tc.oldest_first(*entries)
        plan = self.plan(5, report)
        # the two newest ENTRIES are kept: item-11 (no folder) and item-10
        self.assertEqual(plan.kept, ("item-11", "item-10"))
        self.assertNotIn("item-10", planned(plan))
        self.assertEqual(plan.candidates, 11)

    def test_the_age_rule_never_plans_a_kept_item(self):
        age = rc.AGE_KEY
        entries = [tc.aged(f"item-{n:02d}", OLD) for n in range(8)]
        report = tc.oldest_first(*entries)
        report["keep_recent"] = 3
        state = state_for({**UNATTENDED, "keep_recent": 5}, mode="cleanup", **{age: 30})
        plan = rc.select(state, report)
        self.assertEqual(plan.kept, ("item-07", "item-06"))
        self.assertFalse(set(plan.kept) & set(planned(plan)))
        self.assertEqual(planned(plan), [f"item-{n:02d}" for n in range(5)])

    def test_nothing_is_kept_without_an_authorising_adoption(self):
        report = many(12)
        policy = policy_with()
        unauthorised = rp.PolicyState(rp.ADOPTED, mode="both", policy=policy,
                                      digest=rp.digest_of(policy), unattended=None)
        refused_cleanup = state_for({**UNATTENDED, "cleanup": False, "prune": True})
        for label, state in (("ordinary", unauthorised), ("cleanup false", refused_cleanup),
                             ("no key", tc.adopted("both", **THRESHOLDS))):
            with self.subTest(label):
                plan = rc.select(state, report)
                self.assertEqual((plan.kept, plan.keep_recent), ((), 0))
                self.assertNotIn("keep:", "\n".join(rc.preview_lines(plan, tc.EXAMPLE_TARGET)))

    def test_the_preview_without_an_authorising_adoption_is_todays_golden(self):
        report = many(12, mib=2)
        plan = rc.select(tc.adopted("both", finished_items=10, finished_folder_mib=500), report)
        lines = rc.preview_lines(plan, tc.EXAMPLE_TARGET)
        self.assertEqual(lines[0].split(" (")[0], "retention cleanup: preview")
        self.assertEqual([l for l in lines if "keep" in l], [])
        self.assertEqual(lines[3], "    1. item-00: 2 MiB, archive then remove")

    def test_the_preview_prints_one_keep_line_when_items_are_kept(self):
        plan = self.plan(5, many(12))
        lines = rc.preview_lines(plan, tc.EXAMPLE_TARGET)
        keep = [l for l in lines if "keep" in l.lower() and l.startswith("  keep:")]
        self.assertEqual(keep, ["  keep: the 5 newest finished items stay (the policy's "
                                "unattended keep_recent; the engine keeps 3, so 2 more here)"])

    def test_dry_run_equivalence_one_plan_one_digest(self):
        """The preview shows, and the confirmed and unattended runs execute, the plan
        `select` returns for the same state and report: one planner, one digest rule."""
        report = many(12, mib=2)
        state = state_for({**UNATTENDED, "keep_recent": 5}, finished_items=10,
                          finished_folder_mib=500)
        plan = rc.select(state, report)
        again = rc.select(state, report)
        self.assertEqual(plan, again)
        digest = rc.plan_digest(plan)
        self.assertIn(rc.sentence(digest), "\n".join(rc.preview_lines(plan, tc.EXAMPLE_TARGET)))
        # keep_recent changes the plan the same way for every reader of the state
        plain = rc.select(tc.adopted("both", finished_items=10, finished_folder_mib=500), report)
        self.assertNotEqual(rc.plan_digest(plain), digest)   # the policy digest differs anyway
        self.assertEqual(planned(plan), planned(plain))      # 12 over 10: the 3 oldest either way


class TestAuditWriter(unittest.TestCase):
    """CP2: the audit file's location, modes, shape and write rules (plan 2.3)."""

    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="audit-"))
        self.addCleanup(shutil.rmtree, base, True)
        self.base = base.resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.state = self.base / "state"
        self.env = {"HOME": str(self.home), "XDG_STATE_HOME": str(self.state)}
        self.when = datetime.datetime(2026, 11, 19, 10, 30, 5, tzinfo=datetime.timezone.utc)
        self.opened = []

    def open(self, **kw):
        kw.setdefault("clock", lambda: self.when)
        kw.setdefault("run_id", "ab" * 16)
        audit = ru.open_audit(self.repo, self.env, **kw)
        self.opened.append(audit)
        self.addCleanup(audit.close)
        return audit

    def lines(self):
        return [json.loads(l) for l in (self.state / "workflow-manager" /
                                        "retention-audit.jsonl").read_text().splitlines()]

    def refusal(self, **kw):
        with self.assertRaises(ru.AuditRefusal) as caught:
            ru.open_audit(self.repo, self.env, **kw)
        self.assertTrue(caught.exception.cause.startswith("the audit file cannot be written: "))
        self.assertTrue(caught.exception.step)
        return caught.exception

    # -- shape --------------------------------------------------------------

    def test_every_kind_of_line_has_all_eleven_fields(self):
        audit = self.open()
        kinds = [("plan", "started"), ("archive", "ok"), ("verify", "failed"),
                 ("remove", "interrupted"), ("plan", "nothing-eligible"),
                 ("preflight", "refused"), ("policy", "stopped")]
        for step, result in kinds:
            audit.line(step, result)
        rows = self.lines()
        self.assertEqual(len(rows), len(kinds))
        for row, (step, result) in zip(rows, kinds):
            self.assertEqual(list(row), list(ru.FIELDS))
            self.assertEqual((row["step"], row["result"]), (step, result))
            self.assertEqual(row["schema_version"], 1)
            self.assertEqual([row[k] for k in ("policy_digest", "plan_digest", "item_id",
                                               "engine_code", "error")], [None] * 5)

    def test_the_fields_carry_what_the_caller_names(self):
        audit = self.open()
        audit.line("archive", "failed", policy_digest="p" * 64, plan_digest="d" * 64,
                   item_id="item-1", engine_code="ARCHIVE_EXISTS", error="line\nbreak \u00e9")
        row = self.lines()[0]
        self.assertEqual((row["policy_digest"], row["plan_digest"], row["item_id"],
                          row["engine_code"]), ("p" * 64, "d" * 64, "item-1", "ARCHIVE_EXISTS"))
        self.assertEqual(row["error"], "line\nbreak \u00e9")
        self.assertEqual(row["repository"], str(self.repo))
        raw = (self.state / "workflow-manager" / "retention-audit.jsonl").read_bytes()
        self.assertEqual(raw.count(b"\n"), 1)          # an embedded newline is escaped

    def test_the_time_is_iso_utc_and_the_run_id_is_32_hex(self):
        audit = self.open(clock=lambda: self.when.astimezone(
            datetime.timezone(datetime.timedelta(hours=2))))
        audit.line("plan", "started")
        self.assertEqual(self.lines()[0]["time"], "2026-11-19T10:30:05Z")
        self.assertEqual(self.lines()[0]["run_id"], "ab" * 16)
        default = ru.open_audit(self.repo, self.env)
        self.addCleanup(default.close)
        self.assertRegex(default.run_id, r"^[0-9a-f]{32}$")

    def test_an_unknown_step_or_result_is_a_bug(self):
        audit = self.open()
        with self.assertRaises(ValueError):
            audit.line("prune", "ok")
        with self.assertRaises(ValueError):
            audit.line("plan", "done")
        self.assertFalse((self.state / "workflow-manager" / "retention-audit.jsonl").read_text())

    # -- location -----------------------------------------------------------

    def test_the_default_path_and_the_xdg_override(self):
        self.assertEqual(ru.audit_path({"HOME": "/h"}),
                         Path("/h/.local/state/workflow-manager/retention-audit.jsonl"))
        self.assertEqual(ru.audit_path({"HOME": "/h", "XDG_STATE_HOME": "/x"}),
                         Path("/x/workflow-manager/retention-audit.jsonl"))

    def test_a_relative_or_empty_xdg_state_home_is_ignored(self):
        for value in ("relative/dir", "", "."):
            with self.subTest(value):
                self.assertEqual(ru.audit_path({"HOME": "/h", "XDG_STATE_HOME": value}),
                                 Path("/h/.local/state/workflow-manager/retention-audit.jsonl"))

    def test_the_archive_store_default_is_the_engines_own(self):
        engine = (REPO_ROOT / "scripts" / "workflow_retention.py").read_text()
        found = re.search(r'^DEFAULT_ARCHIVE_ROOT = "([^"]+)"$', engine, re.MULTILINE)
        self.assertEqual(found.group(1), ru.ARCHIVE_ROOT)
        self.assertEqual(ru.archive_store({"HOME": "/h"}), Path("/h/.local/share/workflow-archive"))

    def test_a_path_inside_the_repository_is_refused(self):
        self.env["XDG_STATE_HOME"] = str(self.repo / "state")
        self.refusal()
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_a_path_inside_the_archive_store_is_refused(self):
        self.env["XDG_STATE_HOME"] = str(self.home / ".local" / "share" / "workflow-archive" / "s")
        self.refusal()
        self.assertFalse((self.home / ".local" / "share").exists())

    def test_a_link_into_the_repository_is_refused_by_its_real_path(self):
        self.state.mkdir()
        (self.state / "workflow-manager").symlink_to(self.repo)
        self.refusal()
        self.assertEqual(list(self.repo.iterdir()), [])

    # -- modes --------------------------------------------------------------

    def test_directory_0700_and_file_0600_under_any_umask(self):
        for umask in (0o000, 0o077, 0o277):
            with self.subTest(umask=oct(umask)):
                shutil.rmtree(self.state, ignore_errors=True)
                old = os.umask(umask)
                try:
                    audit = self.open()
                finally:
                    os.umask(old)
                audit.line("plan", "started")
                self.assertEqual((self.state / "workflow-manager").stat().st_mode & 0o777, 0o700)
                self.assertEqual((self.state / "workflow-manager" / "retention-audit.jsonl")
                                 .stat().st_mode & 0o777, 0o600)

    def test_missing_parents_of_the_state_directory_are_created_0700(self):
        self.env["XDG_STATE_HOME"] = str(self.base / "a" / "b" / "state")
        old = os.umask(0o000)
        try:
            self.open()
        finally:
            os.umask(old)
        for name in ("a", "a/b", "a/b/state", "a/b/state/workflow-manager"):
            self.assertEqual((self.base / name).stat().st_mode & 0o777, 0o700, name)

    def test_an_existing_parent_is_not_inspected(self):
        self.state.mkdir(mode=0o777)
        os.chmod(self.state, 0o777)
        self.open().line("plan", "started")
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o777)

    # -- append only --------------------------------------------------------

    def test_two_runs_append_and_existing_bytes_stay(self):
        first = self.open()
        first.line("plan", "started")
        path = self.state / "workflow-manager" / "retention-audit.jsonl"
        before = path.read_bytes()
        first.close()
        second = self.open(run_id="cd" * 16)
        second.line("plan", "started")
        after = path.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual([r["run_id"] for r in self.lines()], ["ab" * 16, "cd" * 16])

    def test_the_open_flags_are_append_only(self):
        seen = []
        real = os.open

        def spy(path, flags, *rest, **kw):
            seen.append(flags)
            return real(path, flags, *rest, **kw)

        with mock.patch.object(ru.os, "open", spy):
            self.open()
        for flags in seen:
            self.assertTrue(flags & os.O_WRONLY and flags & os.O_APPEND and flags & os.O_NOFOLLOW)
            self.assertFalse(flags & (os.O_TRUNC | os.O_RDWR))

    def test_no_seek_truncate_or_rewrite_is_ever_called(self):
        audit = self.open()
        with mock.patch.object(os, "lseek") as seek, mock.patch.object(os, "ftruncate") as trunc, \
                mock.patch.object(os, "truncate") as trunc2:
            audit.line("plan", "started")
        for fake in (seek, trunc, trunc2):
            fake.assert_not_called()

    def test_one_os_write_per_line(self):
        calls = []

        def counting(fd, data):
            calls.append(data)
            return os.write(fd, data)

        audit = self.open(write=counting)
        for _ in range(3):
            audit.line("plan", "started")
        self.assertEqual(len(calls), 3)
        for data in calls:
            self.assertTrue(data.endswith(b"\n") and data.count(b"\n") == 1)

    # -- refusals -----------------------------------------------------------

    def test_a_link_in_place_of_the_file_is_refused(self):
        directory = self.state / "workflow-manager"
        directory.mkdir(parents=True, mode=0o700)
        target = self.base / "elsewhere"
        target.write_text("keep")
        (directory / "retention-audit.jsonl").symlink_to(target)
        self.assertIn("link", self.refusal().cause)
        self.assertEqual(target.read_text(), "keep")

    def test_a_directory_in_place_of_the_file_is_refused(self):
        directory = self.state / "workflow-manager"
        (directory / "retention-audit.jsonl").mkdir(parents=True, mode=0o700)
        self.assertIn("directory", self.refusal().cause)

    def _fifo(self):
        directory = self.state / "workflow-manager"
        directory.mkdir(parents=True, mode=0o700)
        path = directory / "retention-audit.jsonl"
        os.mkfifo(path, 0o600)
        return path

    def test_a_fifo_with_no_reader_is_refused_without_blocking(self):   # LIR-I1 (external)
        """A reader-opening timer is the safety net: a regression that blocks in open()
        is released after 3 s, and the test then fails on `released`."""
        import threading
        path = self._fifo()
        released = []

        def release():
            released.append(True)
            os.close(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        timer = threading.Timer(3, release)
        timer.start()
        try:
            with self.assertRaises(ru.AuditRefusal) as caught:
                ru.open_audit(self.repo, self.env)
        finally:
            timer.cancel()
        self.assertEqual(released, [], "open() blocked on the FIFO")
        self.assertIn("not a regular file", caught.exception.cause)

    def test_a_fifo_with_a_reader_is_refused(self):
        self._fifo_path = self._fifo()
        reader = os.open(self._fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(os.close, reader)
        self.assertIn("not a regular file", self.refusal().cause)

    def test_a_group_writable_file_is_refused(self):
        directory = self.state / "workflow-manager"
        directory.mkdir(parents=True, mode=0o700)
        path = directory / "retention-audit.jsonl"
        path.write_text("x\n")
        os.chmod(path, 0o664)
        self.assertIn("group- or world-writable", self.refusal().cause)
        self.assertEqual(path.read_text(), "x\n")

    def test_a_group_writable_directory_is_refused(self):
        directory = self.state / "workflow-manager"
        directory.mkdir(parents=True)
        os.chmod(directory, 0o770)
        self.assertIn("directory", self.refusal().cause)

    def test_a_file_owned_by_another_user_is_refused(self):
        directory = self.state / "workflow-manager"
        directory.mkdir(parents=True, mode=0o700)
        (directory / "retention-audit.jsonl").write_text("")
        real = os.stat

        def other(target, *a, **kw):
            info = real(target, *a, **kw)
            return os.stat_result((info.st_mode, info.st_ino, info.st_dev, info.st_nlink,
                                   os.getuid() + 1, info.st_gid, info.st_size,
                                   int(info.st_atime), int(info.st_mtime), int(info.st_ctime)))

        def fake_stat(target, *a, **kw):
            return other(target, *a, **kw) if isinstance(target, int) else real(target, *a, **kw)

        self.assertIn("not owned by you", self.refusal(stat=fake_stat).cause)

    def test_a_directory_owned_by_another_user_is_refused(self):
        real = os.stat

        def fake_stat(target, *a, **kw):
            info = real(target, *a, **kw)
            return os.stat_result((info.st_mode, info.st_ino, info.st_dev, info.st_nlink,
                                   os.getuid() + 1, info.st_gid, info.st_size,
                                   int(info.st_atime), int(info.st_mtime), int(info.st_ctime)))

        self.assertIn("directory", self.refusal(stat=fake_stat).cause)

    @unittest.skipIf(os.getuid() == 0, "root can write anywhere")
    def test_an_unwritable_directory_is_refused(self):
        self.state.mkdir()
        os.chmod(self.state, 0o500)
        self.addCleanup(os.chmod, self.state, 0o700)
        self.refusal()

    # -- write errors -------------------------------------------------------

    def test_a_write_error_raises_the_audit_error(self):
        def failing(fd, data):
            raise OSError(28, "No space left on device")

        audit = self.open(write=failing)
        with self.assertRaises(ru.AuditWriteError) as caught:
            audit.line("plan", "started")
        self.assertIn("No space left", caught.exception.cause)
        self.assertEqual(audit.lines, 0)

    def test_a_short_write_raises_the_audit_error(self):
        audit = self.open(write=lambda fd, data: os.write(fd, data[:10]))
        with self.assertRaises(ru.AuditWriteError) as caught:
            audit.line("plan", "started")
        self.assertIn("short write", caught.exception.cause)

    def test_an_open_failure_and_a_first_write_failure_are_different_errors(self):
        self.state.mkdir()
        (self.state / "workflow-manager").write_text("not a directory")
        with self.assertRaises(ru.AuditRefusal) as opened:
            ru.open_audit(self.repo, self.env)
        shutil.rmtree(self.state)

        def failing(fd, data):
            raise OSError(5, "I/O error")

        audit = self.open(write=failing)
        with self.assertRaises(ru.AuditWriteError) as wrote:
            audit.line("plan", "started")
        self.assertNotIsInstance(opened.exception, ru.AuditWriteError)
        self.assertNotIsInstance(wrote.exception, ru.AuditRefusal)
        self.assertTrue(issubclass(ru.AuditRefusal, ru.AuditError)
                        and issubclass(ru.AuditWriteError, ru.AuditError))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# CP3: the unattended run and its JSON document
# ---------------------------------------------------------------------------

import contextlib as _contextlib  # noqa: E402
import errno  # noqa: E402
import io  # noqa: E402
import support  # noqa: E402
import time  # noqa: E402
from unittest import mock as _mock  # noqa: E402

import test_retention_run as trun  # noqa: E402
from workflow_manager import cli, retention, retention_run as rr  # noqa: E402

full_run = trun.full_run
refusal = trun.refusal


class Cmd(trun.RunBase):
    """`RunBase` adopted with an unattended policy (keep_recent 5), and the scratch
    state directory the audit file goes to."""

    adopt_unattended = Scratch.adopt_unattended

    def setUp(self):
        super().setUp()
        self.adopt_unattended()
        self.state_home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_home, ignore_errors=True)
        self.audit_file = self.state_home / "workflow-manager" / "retention-audit.jsonl"

    def digest(self, rep=None):
        return rc.plan_digest(rc.select(rp.load(self.repo), rep or self.rep))

    def go_u(self, scenario=None, *, extra=("--unattended",), rep=None, patches=(),
             target=None, **env):
        rep = rep or self.rep
        self.scenario.write_text(json.dumps(scenario or {}))
        self.marker.unlink(missing_ok=True)
        env["STUB_REPORT"] = str(self.put_report(rep))
        env["STUB_SCENARIO"] = str(self.scenario)
        env.setdefault("XDG_STATE_HOME", str(self.state_home))
        argv = ["--release-version", support.PINNED_NEWEST, trun.COMMAND,
                str(target or self.repo), *extra]
        out, err = io.StringIO(), io.StringIO()
        with _contextlib.ExitStack() as stack:
            stack.enter_context(_mock.patch.dict(os.environ, self.env(**env), clear=True))
            stack.enter_context(_mock.patch.object(cli, "_installed_script_state",
                                                   return_value=ra.SCRIPT_OK))
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(_contextlib.redirect_stdout(out))
            stack.enter_context(_contextlib.redirect_stderr(err))
            try:
                code = cli.main(argv)
            except SystemExit as exit_:
                code = exit_.code
        return tc.Out(code, out.getvalue(), err.getvalue())

    def lines(self):
        if not self.audit_file.exists():
            return []
        return [json.loads(text) for text in self.audit_file.read_text().splitlines()]

    def write_seam(self, fail_on, error=None):
        """An `open_audit` that fails the `fail_on`-th write (1 based)."""
        real, count = os.write, []

        def write(fd, data):
            count.append(1)
            if len(count) == fail_on:
                raise error or OSError(errno.ENOSPC, "No space left on device")
            return real(fd, data)
        original = ru.open_audit
        return _mock.patch.object(
            ru, "open_audit", lambda *a, **kw: original(*a, **kw, write=write))

    def assert_nothing_written(self):
        self.assertEqual(self.keys(), [])
        self.assertFalse(self.audit_file.exists())


class TestUnattendedRun(Cmd):
    def test_it_runs_without_confirm_and_issues_the_confirmed_runs_calls(self):
        out = self.go_u()
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertEqual(self.keys(), full_run("item-00", "item-01", "item-02"))
        verbs = {c["argv"][1] for c in self.script_calls()}
        self.assertLessEqual(verbs, {"report", "archive", "remove"})   # never prune (M23)

    def test_the_text_is_the_confirmed_runs_plus_the_audit_line(self):
        sentence = rc.sentence(self.digest())
        confirmed = self.go(confirm=sentence)
        unattended = self.go_u()
        self.assertEqual(confirmed.code, 0, confirmed.err)
        self.assertEqual(unattended.out, confirmed.out + f"  audit: {self.audit_file}\n")

    def test_the_preview_and_the_confirmed_run_apply_the_same_keep(self):   # M9
        """Dry-run equivalence through the command: once the adoption authorises
        unattended cleanup, the preview and the confirmed run plan with keep_recent
        too. A keep of 13 holds item-11 to item-02, one of which (item-02) the
        thresholds alone would plan, so a preview without the keep would show
        another plan and another sentence."""
        self.adopt_unattended(policy_with({**UNATTENDED, "keep_recent": 13}))
        digest = self.digest()
        preview = self.go(confirm=None)
        self.assertEqual((preview.code, preview.err), (0, ""), preview.out)
        self.assertIn(rc.sentence(digest), preview.out)
        self.assertIn("  keep: the 13 newest finished items stay", preview.out)
        self.assertRegex(preview.out, r"\d\. item-01:")
        self.assertNotRegex(preview.out, r"\d\. item-02:")
        confirmed = self.go(confirm=rc.sentence(digest))
        self.assertEqual(confirmed.code, 0, confirmed.err)
        self.assertEqual(self.keys(), full_run("item-00", "item-01"))
        unattended = self.go_u()
        self.assertEqual(unattended.out, confirmed.out + f"  audit: {self.audit_file}\n")

    def test_the_audit_has_the_start_line_then_one_line_per_action(self):
        self.go_u()
        lines = self.lines()
        digest = self.digest()
        self.assertEqual([(l["step"], l["result"], l["item_id"]) for l in lines],
                         [("plan", "started", None)] + [
                             (step, "ok", item) for item in ("item-00", "item-01", "item-02")
                             for step in ("archive", "verify", "remove")])
        for line in lines:
            self.assertEqual(line["plan_digest"], digest)
            self.assertEqual(line["policy_digest"], rp.load(self.repo).digest)
            self.assertEqual(len(line["run_id"]), 32)
        self.assertEqual(len({l["run_id"] for l in lines}), 1)

    def test_the_audit_path_is_the_xdg_state_home_one(self):
        self.go_u()
        self.assertTrue(self.audit_file.is_file())
        self.assertEqual(ru.audit_path({"XDG_STATE_HOME": str(self.state_home)}), self.audit_file)

    def test_a_clean_run_leaves_the_tree_unchanged(self):
        self.stale_index()
        before = tree_hash(self.repo)
        self.assertEqual(self.go_u().code, 0)
        self.assertEqual(tree_hash(self.repo), before)

    def test_the_kept_items_are_never_run(self):
        rep = many(12, mib=2)
        out = self.go_u(rep=rep)
        self.assertEqual(out.code, 0)
        self.assertNotIn("item-10", "".join(self.keys()))
        self.assertNotIn("item-11", "".join(self.keys()))


class TestArgumentRefusals(Cmd):
    def test_confirm_with_unattended_is_refused_before_anything_is_read(self):   # M1
        out = self.go_u(extra=("--unattended", "--confirm", "x"))
        self.refused(out, "--confirm and --unattended cannot be combined")
        self.assert_nothing_written()
        self.assertFalse(self.state_home.joinpath("workflow-manager").exists())

    def test_json_without_unattended_is_refused_with_empty_stdout(self):   # M2
        out = self.go_u(extra=("--json",))
        self.refused(out, "--json is for the unattended run")
        self.assert_nothing_written()

    def test_a_target_that_is_not_managed_writes_no_audit_file(self):
        shutil.rmtree(self.repo / ".workflow-manager")
        out = self.go_u()
        self.assertEqual((out.code, out.out), (2, ""))
        self.assertIn("is not a managed repository", out.err)
        self.assert_nothing_written()
        self.assertFalse(self.state_home.joinpath("workflow-manager").exists())

    def test_a_corrupt_installation_record_writes_no_audit_file(self):
        (self.repo / ".workflow-manager" / "installation.json").write_text("{")
        out = self.go_u()
        self.assertEqual((out.code, out.out), (2, ""))
        self.assertEqual(self.script_calls(), [])
        self.assertFalse(self.state_home.joinpath("workflow-manager").exists())


class TestRefusalsAreAudited(Cmd):
    def preflight_line(self, out, cause):
        self.assertEqual((out.code, out.out), (2, ""), out.err)
        self.assertIn(cause, out.err)
        self.assertEqual(self.keys(), [])
        lines = self.lines()
        self.assertEqual([(l["step"], l["result"]) for l in lines], [("preflight", "refused")])
        self.assertIn(cause, lines[0]["error"])
        self.assertIsNone(lines[0]["plan_digest"])

    def test_rows_c_to_f_write_one_preflight_line(self):
        record, policy = rp.record_path(self.repo), rp.policy_path(self.repo)
        good_policy, good_record = policy.read_bytes(), record.read_bytes()

        def reset():
            git(self.repo, "reset", "-q", "--hard", "HEAD")
            policy.write_bytes(good_policy)
            record.write_bytes(good_record)
            shutil.rmtree(self.state_home / "workflow-manager", ignore_errors=True)

        def not_adopted():
            record.unlink()

        def no_key():
            self.adopt(tc.POLICY)
            self.commit(self.repo, "plain")

        def ordinary():
            self.adopt_unattended(ordinary=True)

        def cleanup_false():
            self.adopt_unattended(policy_with({**UNATTENDED, "cleanup": False, "prune": True}))

        for label, setup, cause in (
                ("c", not_adopted, f"retention policy: {rp.NOT_ADOPTED}"),
                ("d", no_key, NO_KEY), ("e", ordinary, ORDINARY),
                ("f", cleanup_false, CLEANUP_FALSE)):
            with self.subTest(row=label):
                setup()
                self.stale_index()
                before = tree_hash(self.repo)
                patches = [_mock.patch.object(rc, "_git", side_effect=AssertionError("git"))] \
                    if label in "def" else []
                out = self.go_u(patches=patches)
                self.preflight_line(out, cause)
                if label in "def":
                    self.assertEqual(self.script_calls(), [])   # no `report` either
                self.assertEqual(tree_hash(self.repo), before)
                reset()

    def test_each_later_preflight_refusal_writes_one_line(self):
        installation = self.repo / ".workflow-manager" / "installation.json"
        policy, record = rp.policy_path(self.repo), rp.record_path(self.repo)

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

        def unreadable_release():
            data = json.loads(installation.read_text())
            data["workflow_version"] = "02.25.5"
            installation.write_text(json.dumps(data, indent=2) + "\n")
            self.commit(self.repo, "unreadable")

        def missing_script():
            (self.repo / trun.SCRIPT).unlink()
            git(self.repo, "commit", "-q", "-am", "no script")

        modified = _mock.patch.object(cli, "_installed_script_state",
                                      return_value=ra.SCRIPT_MODIFIED)
        script = lambda flag: _mock.patch.object(cli, "_installed_script_state", return_value=flag)
        git_fails = _mock.patch.object(rc, "committed", side_effect=OSError("no git"))
        cases = [
            ("failed git", lambda: None, {"patches": [git_fails]}, "Git could not be asked"),
            ("unreadable release", unreadable_release, {}, "which is not a version"),
            ("script without a release", lambda: None,
             {"patches": [script(ra.SCRIPT_NO_RELEASE)]}, ra.CAUSE_NO_RELEASE),
            ("script unchecked", lambda: None,
             {"patches": [script(ra.SCRIPT_UNCHECKED)]}, ra.CAUSE_UNCHECKED),
            ("mode", mode, {}, "the adopted mode is notify"),
            ("uncommitted", uncommitted, {}, "is not committed at HEAD"),
            ("dirty", dirty, {}, "a tracked file is changed"),
            ("old release", old_release, {}, "older than 2.25.5"),
            ("modified script", lambda: None, {"patches": [modified]}, ra.CAUSE_MODIFIED),
            ("incomplete", lambda: None, {"rep": dict(self.rep, complete=False)},
             ra.CAUSE_INCOMPLETE),
            ("interrupted", lambda: None, {"rep": dict(self.rep, removing=["half-gone"])},
             "a removal was interrupted"),
            ("missing script", missing_script, {},
             "the repository has no scripts/workflow_retention.py"),
        ]
        for label, setup, kwargs, cause in cases:
            with self.subTest(label=label):
                head = git(self.repo, "rev-parse", "HEAD").stdout.strip()
                saved = {p: p.read_bytes() for p in (policy, record, installation)}
                shutil.rmtree(self.state_home / "workflow-manager", ignore_errors=True)
                try:
                    setup()
                    self.stale_index()
                    before = tree_hash(self.repo)
                    out = self.go_u(**kwargs)
                    self.preflight_line(out, cause)
                    self.assertEqual(tree_hash(self.repo), before)
                finally:
                    git(self.repo, "reset", "-q", "--hard", head)
                    for path, data in saved.items():
                        path.write_bytes(data)

    def test_a_refusal_whose_own_line_cannot_be_written_still_exits_2(self):   # LPR1-006
        (self.repo / "CLAUDE.md").write_text("dirty\n")
        out = self.go_u(patches=[self.write_seam(1)])
        self.assertEqual((out.code, out.out), (2, ""))
        lines = out.err.splitlines()
        self.assertEqual(lines[0], "error: retention cleanup: a tracked file is changed")
        self.assertTrue(lines[1].startswith(
            "error: the audit file could not record this refusal: "), out.err)
        self.assertEqual(self.keys(), [])


class TestAuditRefusals(Cmd):
    def test_an_unwritable_audit_directory_refuses_at_the_open(self):
        blocker = self.state_home / "blocker"
        blocker.write_text("a file")
        out = self.go_u(XDG_STATE_HOME=str(blocker))
        self.refused(out, "the audit file cannot be written")
        self.assertEqual(self.script_calls(), [])

    def test_a_first_write_failure_refuses_before_any_engine_verb(self):   # M16
        out = self.go_u(patches=[self.write_seam(1)])
        self.assertEqual((out.code, out.out), (2, ""))
        self.assertIn("the audit file cannot be written", out.err)
        self.assertEqual(self.keys(), [])
        self.assertEqual(self.lines(), [])

    def test_a_fifo_audit_path_exits_2_promptly_with_no_engine_call(self):   # LIR-I1 (external)
        import threading
        directory = self.state_home / "workflow-manager"
        directory.mkdir(parents=True, mode=0o700)
        fifo = directory / "retention-audit.jsonl"
        os.mkfifo(fifo, 0o600)
        released = []

        def release():
            released.append(True)
            os.close(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK))
        timer = threading.Timer(5, release)
        timer.start()
        try:
            out = self.go_u()
        finally:
            timer.cancel()
        self.assertEqual(released, [], "open() blocked on the FIFO")
        self.refused(out, "it is not a regular file")
        self.assertEqual(out.out, "")
        self.assertIn("next:", out.err)
        self.assertEqual(self.script_calls(), [])
        self.assertEqual(self.keys(), [])

    def test_the_audit_inside_the_repository_is_refused(self):
        out = self.go_u(XDG_STATE_HOME=str(self.repo / "state"))
        self.refused(out, "it is inside the repository")
        self.assertEqual(self.script_calls(), [])


class TestFailuresAreAudited(Cmd):
    def results(self):
        return [(l["step"], l["result"], l["item_id"]) for l in self.lines()]

    def test_an_archive_refusal_writes_a_failed_line_with_the_engine_code(self):
        out = self.go_u({"archive --apply:item-01": refusal("place_failed", "nope")})
        self.assertEqual(out.code, 1, out.err)
        self.assertEqual(self.keys(), full_run("item-00") + ["archive --apply:item-01"])
        last = self.lines()[-1]
        self.assertEqual((last["step"], last["result"], last["item_id"], last["engine_code"]),
                         ("archive", "failed", "item-01", "place_failed"))
        self.assertIn("nope", last["error"])
        self.assertIn("retention cleanup: stopped after 1 of 3 items", out.out)
        self.assertIn("  3. item-02: not attempted", out.out)

    def test_a_verify_mismatch_writes_a_failed_verify_line(self):
        body = {"kind": "retention-remove", "mode": "dry-run", "work_item_id": "item-00",
                "verify": {"matches": False}, "result": {"removed": False}}
        out = self.go_u({"remove:item-00": {"stdout": body}})
        self.assertEqual(out.code, 1)
        self.assertEqual(self.results()[-1], ("verify", "failed", "item-00"))

    def test_a_remove_timeout_writes_a_failed_remove_line(self):
        out = self.go_u({"remove --apply:item-00": {"sleep": 30}},
                        patches=[_mock.patch.object(rr, "CALL_TIMEOUT_SECONDS", 1)])
        self.assertEqual(out.code, 1)
        self.assertEqual(self.results()[-1], ("remove", "failed", "item-00"))

    def test_an_interrupt_writes_an_interrupted_line(self):
        out = self.go_u(patches=[trun.TestStop.interrupt_at(self, "remove:item-01")])
        self.assertEqual(out.code, 1)
        self.assertEqual(self.results()[-1], ("verify", "interrupted", "item-01"))
        self.assertIn("stopped at verify: interrupted", out.out)

    def test_a_policy_changed_before_item_two_writes_a_policy_line(self):   # M19
        real, count = rp.load, []

        def load(target):
            count.append(1)
            return rp.PolicyState(rp.CHANGED) if len(count) >= 3 else real(target)
        out = self.go_u(patches=[_mock.patch.object(rp, "load", load)])
        self.assertEqual(out.code, 1)
        self.assertEqual(self.keys(), full_run("item-00"))
        last = self.lines()[-1]
        self.assertEqual((last["step"], last["result"], last["item_id"]),
                         ("policy", "stopped", "item-01"))
        self.assertIn("the policy changed", last["error"])

    def test_a_policy_adopted_again_with_another_digest_stops_the_run(self):   # M19
        """The file and its record are replaced by another adopted, still authorising
        policy: the state is `adopted` and unattended cleanup is still authorised, so
        only the digest comparison stops the run."""
        import dataclasses
        real, count = rp.load, []
        other = dataclasses.replace(real(self.repo), digest="0" * 64)
        self.assertIsNotNone(other.unattended)

        def load(target):
            count.append(1)
            return other if len(count) >= 3 else real(target)
        out = self.go_u(patches=[_mock.patch.object(rp, "load", load)])
        self.assertEqual(out.code, 1)
        self.assertEqual(self.keys(), full_run("item-00"))
        last = self.lines()[-1]
        self.assertEqual((last["step"], last["result"], last["item_id"]),
                         ("policy", "stopped", "item-01"))
        self.assertIn("the policy changed", last["error"])

    def test_a_swapped_adoption_record_stops_the_run(self):   # M18
        """The record is swapped for an ordinary-only one: the policy digest is
        unchanged, so only the authority condition stops the run."""
        real, count = rp.load, []
        ordinary = rp.PolicyState(rp.ADOPTED, mode="both", policy=rp.load(self.repo).policy,
                                  digest=rp.load(self.repo).digest, unattended=None)

        def load(target):
            count.append(1)
            return ordinary if len(count) >= 3 else real(target)
        out = self.go_u(patches=[_mock.patch.object(rp, "load", load)])
        self.assertEqual(out.code, 1)
        self.assertEqual(self.keys(), full_run("item-00"))
        self.assertEqual(self.results()[-1], ("policy", "stopped", "item-01"))

    def test_a_write_failure_after_the_second_action_stops_before_the_third(self):   # M17
        # writes: start, archive ok, verify ok (fails)
        out = self.go_u(patches=[self.write_seam(3)])
        self.assertEqual(out.code, 1)
        self.assertEqual(self.keys(), ["archive --apply:item-00", "remove:item-00"])
        self.assertIn("had succeeded", out.out)
        self.assertIn("no further call was made", out.out)
        self.assertIn(str(self.audit_file), out.out)
        self.assertIn("audit line", out.err)
        self.assertEqual([l["step"] for l in self.lines()], ["plan", "archive"])


class TestNothingToRun(Cmd):
    def test_no_threshold_reached_is_nothing_to_do_and_writes_no_line(self):
        rep = many(5, mib=2)
        out = self.go_u(rep=rep)
        self.assertEqual((out.code, out.err), (0, ""))
        self.assertIn("nothing to do", out.out)
        self.assertNotIn("--confirm", out.out)
        self.assertEqual(self.keys(), [])
        self.assertEqual(self.lines(), [])

    def hold_everything(self):
        self.adopt_unattended(policy_with({**UNATTENDED, "keep_recent": 100}))

    def test_a_threshold_held_by_keep_recent_is_nothing_eligible(self):   # LPR1-002
        self.hold_everything()
        out = self.go_u()
        self.assertEqual((out.code, out.err), (0, ""), out.out)
        self.assertIn("retention cleanup: nothing eligible (", out.out)
        self.assertIn("running it again will not help", out.out)
        self.assertNotIn("--confirm", out.out)
        self.assertEqual(self.keys(), [])
        lines = self.lines()
        self.assertEqual([(l["step"], l["result"]) for l in lines], [("plan", "nothing-eligible")])
        self.assertEqual(lines[0]["plan_digest"],
                         rc.plan_digest(rc.select(rp.load(self.repo), self.rep)))


class TestJson(Cmd):
    def doc(self, out):
        return json.loads(out.out)

    def test_a_done_document_and_nothing_else_on_stdout(self):
        out = self.go_u(extra=("--unattended", "--json"))
        self.assertEqual(out.code, 0, out.err)
        doc = self.doc(out)
        self.assertEqual((doc["kind"], doc["schema_version"], doc["outcome"], doc["exit_code"]),
                         ("retention_cleanup_run", 1, "done", 0))
        self.assertEqual(doc["plan_digest"], self.digest())
        self.assertEqual(doc["policy_digest"], rp.load(self.repo).digest)
        self.assertEqual((doc["done"], doc["total"], doc["stopped"]), (3, 3, None))
        self.assertEqual([i["result"] for i in doc["items"]], ["done"] * 3)
        self.assertEqual([s["step"] for s in doc["items"][0]["steps"]],
                         ["archive", "verify", "remove"])
        self.assertEqual(doc["audit"], {"path": str(self.audit_file), "lines_written": 10,
                                        "error": None})
        self.assertEqual(doc["run_id"], self.lines()[0]["run_id"])
        self.assertIn("retention cleanup: running plan", out.err)   # progress on stderr
        self.assertEqual(doc["repository"], self.lines()[0]["repository"])

    def test_a_stopped_document(self):
        out = self.go_u({"archive --apply:item-01": refusal("place_failed", "nope")},
                        extra=("--unattended", "--json"))
        self.assertEqual(out.code, 1)
        doc = self.doc(out)
        self.assertEqual((doc["outcome"], doc["done"], doc["exit_code"]), ("stopped", 1, 1))
        self.assertEqual([i["result"] for i in doc["items"]],
                         ["done", "stopped", "not-attempted"])
        self.assertEqual({k: doc["stopped"][k] for k in ("step", "item_id", "engine_code")},
                         {"step": "archive", "item_id": "item-01", "engine_code": "place_failed"})
        self.assertTrue(doc["stopped"]["next_step"])

    def test_a_stop_before_the_first_call_prints_the_document_and_exits_2(self):
        out = self.go_u(extra=("--unattended", "--json"), patches=[
            _mock.patch.object(rp, "load", side_effect=[rp.load(self.repo)] +
                               [rp.PolicyState(rp.CHANGED)] * 5)])
        self.assertEqual(out.code, 2, out.err)
        doc = self.doc(out)
        self.assertEqual((doc["outcome"], doc["exit_code"], doc["stopped"]["step"]),
                         ("stopped", 2, "policy"))
        self.assertEqual(self.keys(), [])

    def test_nothing_to_do_and_nothing_eligible_documents(self):
        out = self.go_u(rep=many(5, mib=2), extra=("--unattended", "--json"))
        doc = self.doc(out)
        self.assertEqual((out.code, doc["outcome"], doc["items"], doc["thresholds_reached"]),
                         (0, "nothing-to-do", [], []))
        self.assertEqual(self.lines(), [])
        self.adopt_unattended(policy_with({**UNATTENDED, "keep_recent": 100}))
        out = self.go_u(extra=("--unattended", "--json"))
        doc = self.doc(out)
        self.assertEqual((out.code, doc["outcome"]), (0, "nothing-eligible"))
        self.assertEqual(doc["thresholds_reached"], ["finished_items"])
        self.assertEqual(doc["plan_digest"], self.lines()[0]["plan_digest"])

    def test_a_refusal_prints_nothing_on_stdout(self):
        (self.repo / "CLAUDE.md").write_text("dirty\n")
        out = self.go_u(extra=("--unattended", "--json"))
        self.assertEqual((out.code, out.out), (2, ""))
        self.assertIn("error:", out.err)
        self.assertIn("next:", out.err)

    def test_an_audit_failure_after_an_action_is_in_the_document(self):
        out = self.go_u(patches=[self.write_seam(3)], extra=("--unattended", "--json"))
        self.assertEqual(out.code, 1)
        doc = self.doc(out)
        self.assertEqual(doc["outcome"], "stopped")
        self.assertIn("audit file cannot be written", doc["audit"]["error"])
        self.assertEqual(doc["audit"]["lines_written"], 2)
