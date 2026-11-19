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
