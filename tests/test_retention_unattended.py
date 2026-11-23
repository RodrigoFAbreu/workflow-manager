#!/usr/bin/env python3
"""The `unattended` policy key: its strict validation and its fail-safe for a
Manager that predates it. Hermetic: a scratch managed repository, no network, no
Git history (the base module is a vendored copy)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

from support import REPO_ROOT
from test_retention_policy import GOOD, Base, with_
from workflow_manager import retention_policy as rp
from workflow_manager.retention import shown

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "retention_policy_base.py.txt"
BASE_COMMIT = "87d151c7feebe3a9aebe1194508ab0d5bedf7973"
BASE_BLOB = "4b54c5219c3ab5517b529984980bc2e8f3e97f3a"
GOOD_DIGEST = "5fa01cefcc02203bca455416b220cca79da62c2b281d36bed3c30b4731574fa7"

UNATTENDED = {"cleanup": True, "prune": True, "keep_recent": 5, "ttl_days": 30,
              "prune_max_per_run": 3}


def unattended(**changes):
    value = dict(UNATTENDED)
    value.update(changes)
    return value


_DEFAULT = object()


def with_unattended(value=_DEFAULT, **changes):
    policy = with_(**changes)
    policy["unattended"] = unattended() if value is _DEFAULT else value
    return policy


def base_module():
    """The base commit's `retention_policy`, loaded from the vendored copy as a
    scratch module of the `workflow_manager` package."""
    name = "workflow_manager._retention_policy_base"
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(FIXTURE))
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "workflow_manager"
    sys.modules[name] = module
    try:
        exec(compile(FIXTURE.read_text(encoding="utf-8"), str(FIXTURE), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


class TestKey(Base):
    def test_a_valid_file(self):
        self.assertEqual(self.errors(with_unattended()), [])
        self.assertEqual(self.errors(with_unattended(mode="cleanup")), [])
        for flags in ({"cleanup": True, "prune": False}, {"cleanup": False, "prune": True}):
            self.assertEqual(self.errors(with_unattended(unattended(**flags))), [])

    def test_the_value_must_be_an_object(self):
        for bad in (None, True, 5, "x", [], [UNATTENDED]):
            with self.subTest(bad=bad):
                self.assertEqual(self.errors(with_unattended(bad)),
                                 [f"unattended must be an object, not {shown(bad)}"])

    def test_an_unknown_nested_key(self):
        value = unattended(extra=1)
        self.assertEqual(self.errors(with_unattended(value)), ["unknown key unattended.'extra'"])

    def test_each_of_the_five_keys_is_required(self):
        for key in rp.UNATTENDED_KEYS:
            value = unattended()
            del value[key]
            with self.subTest(key=key):
                self.assertTrue(f"unattended.{key} is missing" in self.errors(with_unattended(value)))
        self.assertEqual(len(rp.UNATTENDED_KEYS), 5)

    def test_a_non_boolean_where_a_boolean_goes(self):
        for key in rp.UNATTENDED_BOOLEANS:
            for bad in (1, 0, "true", None, 1.0):
                with self.subTest(key=key, bad=bad):
                    errors = self.errors(with_unattended(unattended(**{key: bad})))
                    self.assertIn(f"unattended.{key} must be true or false, not {bad!r}", errors)

    def test_wrong_types_where_an_integer_goes(self):
        for key in rp.UNATTENDED_INTEGERS:
            for bad in (5.0, "5", None, [5], True, False):
                with self.subTest(key=key, bad=bad):
                    errors = self.errors(with_unattended(unattended(**{key: bad})))
                    self.assertIn(f"unattended.{key} must be an integer, not {bad!r}", errors)

    def test_a_boolean_is_not_the_integer_three(self):
        self.assertTrue(self.errors(with_unattended(unattended(keep_recent=True))))
        # True is 1, inside prune_max_per_run's range: only the type rule refuses it.
        self.assertEqual(self.errors(with_unattended(unattended(prune_max_per_run=True))),
                         ["unattended.prune_max_per_run must be an integer, not True"])

    def test_floors_and_ceilings_at_both_sides(self):
        for key, (low, high) in rp.UNATTENDED_INTEGERS.items():
            for value, ok in ((low - 1, False), (low, True), (high, True), (high + 1, False)):
                with self.subTest(key=key, value=value):
                    errors = self.errors(with_unattended(unattended(**{key: value})))
                    if ok:
                        self.assertEqual(errors, [])
                    else:
                        self.assertEqual(errors, [f"unattended.{key} must be from {low} to "
                                                  f"{high}, not {value}"])
        self.assertEqual(rp.UNATTENDED_INTEGERS, {"keep_recent": (3, 100000),
                                                  "ttl_days": (14, 3650),
                                                  "prune_max_per_run": (1, 100)})

    def test_a_duplicate_nested_key_through_the_loader(self):
        text = ('{"schema_version":1,"mode":"both","thresholds":{"archives":20},'
                '"unattended":{"cleanup":true,"cleanup":false,"prune":true,'
                '"keep_recent":5,"ttl_days":30,"prune_max_per_run":3}}')
        self.put(text)
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.INVALID, "off"))
        self.assertIn("duplicate key 'cleanup'", " ".join(state.problems))

    def test_the_cross_rule_needs_cleanup_or_prune(self):
        errors = self.errors(with_unattended(unattended(cleanup=False, prune=False)))
        self.assertEqual(errors, ["unattended needs cleanup or prune to be true"])

    def test_the_cross_rule_needs_mode_cleanup_or_both(self):
        for mode in ("off", "notify"):
            with self.subTest(mode=mode):
                self.assertEqual(self.errors(with_unattended(mode=mode)),
                                 [f"unattended needs mode cleanup or both, not {mode}"])

    def test_every_problem_is_listed(self):
        errors = self.errors(with_unattended({"cleanup": 1, "extra": 1, "keep_recent": 2},
                                             mode="off"))
        self.assertEqual(len(errors), 7, errors)

    def test_the_loader_lists_the_problems_of_a_bad_key(self):
        self.put(with_unattended(unattended(ttl_days=13)))
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.INVALID, "off"))
        self.assertTrue(any("unattended.ttl_days" in p for p in state.problems))


class TestDigest(Base):
    def test_a_file_without_the_key_keeps_its_digest(self):
        self.assertEqual(rp.digest_of(GOOD), GOOD_DIGEST)

    def test_the_key_changes_the_digest(self):
        self.assertNotEqual(rp.digest_of(with_unattended()), GOOD_DIGEST)



class TestFailSafe(Base):
    def test_the_base_commit_refuses_the_key(self):
        base = base_module()
        self.assertEqual(base.policy_errors(GOOD), [])
        errors = base.policy_errors(with_unattended())
        self.assertEqual(errors, ["unknown key 'unattended'"])

    def test_the_key_is_the_only_thing_the_base_refuses(self):
        base = base_module()
        policy = with_unattended()
        del policy["unattended"]
        self.assertEqual(base.policy_errors(policy), [])
        self.assertEqual(rp.policy_errors(policy), [])

    def test_the_fixture_is_the_base_commits_blob(self):
        data = FIXTURE.read_bytes()
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        self.assertEqual(blob, BASE_BLOB)
        probe = subprocess.run(["git", "cat-file", "-e", f"{BASE_COMMIT}:src/workflow_manager/"
                                "retention_policy.py"], cwd=REPO_ROOT, capture_output=True)
        if probe.returncode == 0:
            shown = subprocess.run(["git", "show", f"{BASE_COMMIT}:src/workflow_manager/"
                                    "retention_policy.py"], cwd=REPO_ROOT, capture_output=True,
                                   check=True).stdout
            self.assertEqual(shown, data)


class TestDescribe(unittest.TestCase):
    def test_the_settings_line(self):
        self.assertEqual(rp.describe_unattended(UNATTENDED),
                         "cleanup on, prune on, keep 5 recent, ttl 30 days, "
                         "at most 3 prunes per run")
        self.assertEqual(rp.describe_unattended(unattended(cleanup=False, prune=False)),
                         "cleanup off, prune off, keep 5 recent, ttl 30 days, "
                         "at most 3 prunes per run")


from test_retention_policy import ADOPT, run, tree_hash  # noqa: E402


class TestSentences(Base):
    def keyed(self):
        policy = with_unattended()
        self.put(policy)
        return policy, self.digest(policy)

    def adopt_with(self, policy, text):
        self.put(policy)
        return run(ADOPT, str(self.repo), "--confirm", text)

    def test_the_sentence_strings_and_that_neither_matches_the_other(self):
        digest = "ab" * 32
        self.assertEqual(rp.sentence(digest), "Adopt the retention policy abababababab.")
        self.assertEqual(rp.unattended_sentence(digest),
                         "Adopt the unattended retention policy abababababab.")
        self.assertFalse(rp.confirmation_holds(rp.unattended_sentence(digest), digest))
        self.assertFalse(rp.unattended_confirmation_holds(rp.sentence(digest), digest))
        self.assertTrue(rp.confirmation_holds(rp.sentence(digest), digest))
        self.assertTrue(rp.unattended_confirmation_holds(rp.unattended_sentence(digest), digest))

    def test_the_unattended_sentence_adopts_a_file_with_the_key(self):
        policy, digest = self.keyed()
        proc = run(ADOPT, str(self.repo), "--confirm", rp.unattended_sentence(digest))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        record = json.loads(self.record_file().read_text())
        self.assertEqual(sorted(record), sorted(rp._RECORD_KEYS))
        self.assertEqual(record["confirmation"], rp.unattended_sentence(digest))
        self.assertEqual(record["policy"], policy)
        state = self.state()
        self.assertEqual(state.state, rp.ADOPTED)
        self.assertEqual(state.mode, "both")
        self.assertEqual(state.unattended, policy["unattended"])

    def test_the_preview_of_a_file_with_the_key_prints_the_unattended_sentence(self):
        _, digest = self.keyed()
        before = tree_hash(self.repo)
        proc = run(ADOPT, str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(tree_hash(self.repo), before)
        self.assertIn(f"  {rp.unattended_sentence(digest)}", proc.stdout)
        self.assertIn("only the unattended sentence adopts it", proc.stdout)
        self.assertNotIn(f"  {rp.sentence(digest)}", proc.stdout)

    def test_the_preview_of_a_file_without_the_key_is_unchanged(self):
        self.put()
        digest = self.digest()
        proc = run(ADOPT, str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.endswith(
            "nothing was written. Only the repository's owner adopts a policy: to adopt "
            f"this file, --confirm must contain the sentence\n  {rp.sentence(digest)}\n"),
            proc.stdout)
        self.assertNotIn("unattended key", proc.stdout)
        self.assertNotIn("unattended retention", proc.stdout)

    def test_the_ordinary_sentence_is_refused_for_a_file_with_the_key(self):
        _, digest = self.keyed()
        proc = self.refused("--confirm", rp.sentence(digest))
        self.assertIn("only the unattended sentence adopts it", proc.stderr)
        self.assertIn(rp.unattended_sentence(digest), proc.stderr)
        self.assertFalse(self.record_file().exists())

    def test_the_unattended_sentence_is_refused_for_a_file_without_the_key(self):
        self.put()
        proc = self.refused("--confirm", rp.unattended_sentence(self.digest()))
        # The command's own wrong-kind refusal, not the record check behind it.
        self.assertIn("error: --confirm holds the unattended sentence, but the policy file has "
                      "no unattended key\n", proc.stderr)
        self.assertFalse(self.record_file().exists())

    def test_a_mixed_confirmation_is_refused(self):
        for policy in (with_unattended(), GOOD):
            self.put(policy)
            digest = self.digest(policy)
            text = f"{rp.sentence(digest)} {rp.unattended_sentence(digest)}"
            proc = self.refused("--confirm", text)
            again = f"workflow-manager adopt-retention-policy {shlex.quote(str(self.repo))}"
            self.assertEqual(
                proc.stderr,
                "error: --confirm mixes the ordinary and the unattended adoption sentence\n"
                f"next: run {again} to see the one sentence for this policy, then run it again "
                "with --confirm holding only that sentence\n")

    def test_a_wrong_digest_unattended_sentence_is_refused(self):
        self.keyed()
        proc = self.refused("--confirm", rp.unattended_sentence("0" * 64))
        self.assertIn("does not contain the sentence for this policy's digest", proc.stderr)

    def test_a_confirmation_without_a_sentence_keeps_the_old_cause(self):
        for policy in (with_unattended(), GOOD):
            self.put(policy)
            proc = self.refused("--confirm", "yes please")
            self.assertIn("error: --confirm does not contain the sentence for this policy's "
                          "digest\n", proc.stderr)

    def test_schema_refusals_through_the_command_write_nothing(self):
        self.put(with_unattended(unattended(keep_recent=2)))
        proc = self.refused()
        self.assertIn("unattended.keep_recent", proc.stderr)
        self.assertFalse(self.record_file().exists())

    def write_record(self, policy, confirmation):
        self.put(policy)
        record = {"schema_version": 1, "sha256": self.digest(policy),
                  "adopted_at": "2026-11-18T10:00:00Z", "confirmation": confirmation,
                  "policy": policy}
        self.record_file().write_bytes(rp.serialize_record(record))
        return self.state()

    def test_a_hand_written_mixed_record_reads_adopted_with_unattended_set(self):
        policy = with_unattended()
        digest = self.digest(policy)
        state = self.write_record(policy, f"{rp.sentence(digest)} {rp.unattended_sentence(digest)}")
        self.assertEqual(state.state, rp.ADOPTED)
        self.assertEqual(state.unattended, policy["unattended"])

    def test_an_ordinary_only_record_authorises_nothing_unattended(self):
        policy = with_unattended()
        state = self.write_record(policy, rp.sentence(self.digest(policy)))
        self.assertEqual(state.state, rp.ADOPTED)
        self.assertEqual(state.mode, "both")
        self.assertIsNone(state.unattended)

    def test_an_unattended_record_for_a_file_without_the_key_is_invalid(self):
        state = self.write_record(GOOD, rp.unattended_sentence(self.digest()))
        self.assertEqual(state.state, rp.RECORD_INVALID)
        self.assertEqual(state.mode, "off")
        self.assertIsNone(state.unattended)
        self.assertIn("record confirmation is the unattended sentence, but the policy has no "
                      "unattended key", state.problems)

    def test_a_record_with_a_wrong_digest_in_either_sentence_is_invalid(self):
        policy = with_unattended()
        digest = self.digest(policy)
        state = self.write_record(
            policy, f"{rp.unattended_sentence(digest)} {rp.sentence('0' * 64)}")
        self.assertEqual(state.state, rp.RECORD_INVALID)

    def test_every_other_state_has_no_unattended(self):
        policy = with_unattended()
        self.assertIsNone(self.state().unattended)
        self.put(policy)
        self.assertIsNone(self.state().unattended)
        self.write_record(policy, rp.unattended_sentence(self.digest(policy)))
        self.put(with_unattended(unattended(ttl_days=31)))
        changed = self.state()
        self.assertEqual(changed.state, rp.CHANGED)
        self.assertIsNone(changed.unattended)


import test_retention_cleanup as trc  # noqa: E402
import test_retention_status as rs  # noqa: E402

TARGET = Path("/t")
DECLARES = ("  unattended retention: the file declares cleanup on, prune on, keep 5 recent, "
            "ttl 30 days, at most 3 prunes per run; adopting it with the unattended sentence "
            "would authorise that")
ADOPTED_UNATTENDED = ("  unattended retention: adopted with the unattended sentence: cleanup on, "
                      "prune on, keep 5 recent, ttl 30 days, at most 3 prunes per run")
ADOPTED_ORDINARY = ("  unattended retention: the file declares it, but the adoption authorises "
                    "nothing unattended; only the unattended sentence authorises it: run "
                    "workflow-manager adopt-retention-policy /t")
ADOPTED_ORDINARY_ADOPT_PREVIEW = (
    "  unattended retention: the file declares it, but the adoption authorises "
    "nothing unattended; only the unattended sentence authorises it: adopt again with "
    "the unattended sentence printed below")
ENFORCED = ["  enforced by retention-cleanup --unattended: it archives and removes, then prunes "
            "archives of finished items whose review folder is already gone, older than 30 "
            "days, at most 3 per run, never one under an interrupted removal",
            "  deleting an archive cannot be undone; the archive store is "
            "~/.local/share/workflow-archive, which the Manager does not back up"]
ENFORCED_NO_PRUNE = ["  enforced by retention-cleanup --unattended for the cleanup part (archive "
                     "and remove); unattended.prune is false, so no archive is pruned"]
STALE_ENFORCED = "prune is not run unattended yet"
OLD_NOT_ENFORCED = ("not enforced by this release: nothing runs unattended, and retention-cleanup "
                    "still needs its per-plan --confirm")
OLD_BLOCK_LAST = ("cleans up only when retention-cleanup runs with --confirm")
UNATTENDED_BLOCK_LAST = ("  this Manager release reads the policy and, for notify and both, "
                         "evaluates its thresholds in verify and doctor; it sends nothing, and "
                         "cleans up only when retention-cleanup runs with --confirm or, under "
                         "the adopted unattended policy, with --unattended")


class TestText(Base):
    """The unattended lines of every output, each state."""

    keyed = TestSentences.keyed
    write_record = TestSentences.write_record

    def load_for(self, how):
        policy = with_unattended()
        digest = self.digest(policy)
        self.record_file().unlink(missing_ok=True)
        if how == "unattended":
            return self.write_record(policy, rp.unattended_sentence(digest))
        if how == "ordinary":
            return self.write_record(policy, rp.sentence(digest))
        if how == "not-adopted":
            self.put(policy)
        elif how == "changed":
            self.write_record(policy, rp.unattended_sentence(digest))
            self.put(with_unattended(unattended(ttl_days=31)))
        elif how == "record-invalid":
            self.write_record(policy, "no sentence")
        return self.state()

    def test_the_helper_per_state(self):
        want = {"unattended": ADOPTED_UNATTENDED, "ordinary": ADOPTED_ORDINARY,
                "not-adopted": DECLARES, "record-invalid": DECLARES}
        for how, head in want.items():
            with self.subTest(how=how):
                self.assertEqual(rp.unattended_lines(self.load_for(how), TARGET),
                                 [head, *ENFORCED])

    def test_the_helper_with_adopting_changes_only_the_ordinary_head(self):
        for how in ("unattended", "ordinary", "not-adopted", "record-invalid", "changed"):
            with self.subTest(how=how):
                state = self.load_for(how)
                plain = rp.unattended_lines(state, TARGET)
                lines = rp.unattended_lines(state, TARGET, adopting=True)
                if how == "ordinary":
                    self.assertEqual(lines, [ADOPTED_ORDINARY_ADOPT_PREVIEW, *ENFORCED])
                    self.assertEqual(lines[1:], plain[1:])
                else:
                    self.assertEqual(lines, plain)
        self.put()
        self.record_file().unlink(missing_ok=True)
        self.assertEqual(rp.unattended_lines(self.state(), TARGET, adopting=True), [])
        self.assertEqual(rp.unattended_lines(self.state(), TARGET), [])
        self.policy_file().unlink()
        self.assertEqual(rp.unattended_lines(self.state(), TARGET, adopting=True), [])
        self.assertEqual(rp.unattended_lines(self.state(), TARGET), [])
        self.put("not json")
        self.assertEqual(rp.unattended_lines(self.state(), TARGET, adopting=True), [])
        self.assertEqual(rp.unattended_lines(self.state(), TARGET), [])

    def test_the_adopt_preview_of_an_ordinary_only_record_says_to_adopt_again(self):
        policy = with_unattended()
        digest = self.digest(policy)
        self.write_record(policy, rp.sentence(digest))
        before = tree_hash(self.repo)
        proc = run(ADOPT, str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(tree_hash(self.repo), before)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines.count(ADOPTED_ORDINARY_ADOPT_PREVIEW), 1, proc.stdout)
        head = lines.index(ADOPTED_ORDINARY_ADOPT_PREVIEW)
        sentence_at = lines.index(f"  {rp.unattended_sentence(digest)}")
        self.assertLess(head, sentence_at)
        self.assertNotIn("adopt-retention-policy", lines[head])
        self.assertNotIn(": run workflow-manager adopt-retention-policy", proc.stdout)

    def test_prune_false_says_so_in_every_state(self):
        for how in ("unattended", "ordinary", "not-adopted", "changed"):
            with self.subTest(how=how):
                policy = with_unattended(unattended(prune=False))
                self.record_file().unlink(missing_ok=True)
                digest = self.digest(policy)
                if how == "unattended":
                    state = self.write_record(policy, rp.unattended_sentence(digest))
                elif how == "ordinary":
                    state = self.write_record(policy, rp.sentence(digest))
                elif how == "not-adopted":
                    self.put(policy)
                    state = self.state()
                else:
                    self.write_record(policy, rp.unattended_sentence(digest))
                    self.put(with_unattended(unattended(prune=False, ttl_days=31)))
                    state = self.state()
                lines = rp.unattended_lines(state, TARGET)
                self.assertEqual(lines[1:], ENFORCED_NO_PRUNE)
                self.assertEqual(len(lines), 2)

    def test_the_enforcement_text_carries_the_policy_numbers(self):
        lines = rp.enforcement_lines(unattended(ttl_days=45, prune_max_per_run=7))
        self.assertIn("older than 45 days, at most 7 per run", lines[0])
        self.assertIn(rp.ARCHIVE_ROOT, lines[1])
        self.assertEqual(len(lines), 2)

    def test_a_changed_file_describes_the_file_not_the_record(self):
        state = self.load_for("changed")
        self.assertEqual(state.state, rp.CHANGED)
        self.assertEqual(rp.unattended_lines(state, TARGET),
                         [DECLARES.replace("ttl 30", "ttl 31"),
                          *[line.replace("30 days", "31 days") for line in ENFORCED]])

    def test_no_line_without_the_key_or_without_a_valid_file(self):
        self.put()
        self.assertEqual(rp.unattended_lines(self.state(), TARGET), [])
        self.adopt()
        self.assertEqual(rp.unattended_lines(self.state(), TARGET), [])
        self.assertEqual(rp.unattended_lines(rp.PolicyState(rp.ABSENT), TARGET), [])
        self.assertEqual(rp.unattended_lines(
            rp.PolicyState(rp.INVALID, problems=("x",)), TARGET), [])

    def test_the_status_block_before_the_next_line(self):
        for how in ("not-adopted", "record-invalid", "changed"):
            with self.subTest(how=how):
                lines = rp.block(self.load_for(how), TARGET)
                self.assertEqual(lines[-4][:len("  unattended retention:")],
                                 "  unattended retention:")
                self.assertEqual(lines[-3:-1], ENFORCED if how != "changed" else
                                 [line.replace("30 days", "31 days") for line in ENFORCED])
                self.assertTrue(lines[-1].startswith("  next: "))
        adopted = rp.block(self.load_for("unattended"), TARGET)
        self.assertTrue(adopted[1].startswith("  thresholds: "))
        self.assertEqual(adopted[2:5], [ADOPTED_UNATTENDED, *ENFORCED])
        self.assertEqual(rp.block(self.load_for("ordinary"), TARGET)[2], ADOPTED_ORDINARY)

    def test_a_block_without_the_key_is_byte_identical_to_the_old_one(self):
        self.adopt()
        lines = rp.block(self.state(), TARGET)
        self.assertEqual(len(lines), 3)
        self.assertNotIn("unattended", "\n".join(lines))

    def test_the_adopt_preview_prints_the_lines_after_the_state(self):
        self.keyed()
        proc = run(ADOPT, str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        at = [n for n, line in enumerate(lines) if line.startswith("state: ")][0]
        self.assertEqual(lines[at + 1][:len("  unattended retention:")], "  unattended retention:")
        self.assertEqual(lines[at + 2:at + 4], ENFORCED)
        self.assertTrue(lines[at + 4].startswith("nothing was written."))

    def test_the_status_command_prints_the_block(self):
        policy = with_unattended()
        self.write_record(policy, rp.unattended_sentence(self.digest(policy)))
        out = self.section("status", rs.report()).stdout
        self.assertIn(ADOPTED_UNATTENDED, out)
        self.assertEqual(out.count(ENFORCED[0]), 1)
        self.assertEqual(out.count(ENFORCED[1]), 1)

    def test_the_cleanup_preview_puts_the_extra_before_next_and_after_nothing_to_do(self):
        extra = rp.unattended_lines(self.load_for("unattended"), TARGET)
        report = trc.oldest_first(*(trc.entry(f"i{n}") for n in range(3)))
        plan = trc.plan_for(report, finished_items=1)
        plain = trc.rc.preview_lines(plan, trc.EXAMPLE_TARGET)
        with_extra = trc.rc.preview_lines(plan, trc.EXAMPLE_TARGET, extra)
        at = [n for n, line in enumerate(plain) if line.startswith("  next: ")][0]
        self.assertEqual(with_extra, plain[:at] + extra + plain[at:])
        self.assertEqual(with_extra[-2][:8], "  next: ")
        nothing = trc.plan_for(trc.oldest_first(trc.entry("a")), finished_items=10)
        self.assertEqual(trc.rc.preview_lines(nothing, trc.EXAMPLE_TARGET, extra),
                         trc.rc.preview_lines(nothing, trc.EXAMPLE_TARGET) + extra)
        unset = trc.plan_for(report, archives=1)
        self.assertEqual(trc.rc.preview_lines(unset, trc.EXAMPLE_TARGET, extra)[1:], extra)
        self.assertEqual(trc.rc.preview_lines(plan, trc.EXAMPLE_TARGET, []), plain)

    def test_the_age_note_comes_before_the_extra_in_the_nothing_to_do_output(self):
        extra = ["  X", "  Y"]
        plan = trc.age_plan(trc.oldest_first(trc.aged("a", trc.YOUNG), trc.aged("u", None)))
        lines = trc.rc.preview_lines(plan, trc.EXAMPLE_TARGET, extra)
        self.assertEqual(lines[-2:], extra)
        self.assertIn("  age not known:", lines[-3])

    def test_the_extra_changes_neither_the_plan_nor_its_digest(self):
        report = trc.oldest_first(*(trc.entry(f"i{n}") for n in range(3)))
        plan = trc.plan_for(report, finished_items=1)
        digest = trc.rc.plan_digest(plan)
        trc.rc.preview_lines(plan, trc.EXAMPLE_TARGET, ["  X"])
        self.assertEqual(trc.rc.plan_digest(plan), digest)
        self.assertEqual(trc.rc.plan_digest(trc.plan_for(report, finished_items=1)), digest)


class TestCleanupPreview(trc.Base):
    """`retention-cleanup`'s own preview, through the command: the unattended lines sit
    before its `next:` line, and a file without the key prints none."""

    def keyed(self, sentence=rp.unattended_sentence):
        policy = {**trc.POLICY, "unattended": UNATTENDED}
        path = rp.policy_path(self.repo)
        path.write_text(json.dumps(policy))
        record = rp.record_path(self.repo)
        if sentence is rp.unattended_sentence:
            rp.apply(self.repo, rp.usable_policy(self.repo), sentence(rp.digest_of(policy)))
        else:
            record.write_bytes(rp.serialize_record({
                "schema_version": 1, "sha256": rp.digest_of(policy),
                "adopted_at": "2026-11-18T10:00:00Z",
                "confirmation": sentence(rp.digest_of(policy)), "policy": policy}))
        self.commit(self.repo, "adopt the keyed policy")
        return policy

    def test_the_preview_carries_the_lines_before_next_and_the_digest_is_the_plans(self):
        self.keyed()
        out = self.call(trc.many())
        self.assertEqual(out.code, 0, out.err)
        lines = out.out.splitlines()
        at = [n for n, line in enumerate(lines) if line.startswith("  next: ")][0]
        self.assertEqual(lines[at - 3:at], [ADOPTED_UNATTENDED, *ENFORCED])
        self.assertEqual(lines[at + 1].strip(), trc.rc.BY_HAND)
        sentence_ = lines[at].split('--confirm "', 1)[1].rstrip('"')
        # the printed sentence is the plan's own: the confirmed run still holds it
        self.assertRegex(sentence_, r"^.+ [0-9a-f]{12}\.$")

    def test_an_ordinary_only_record_says_so_in_the_preview(self):
        self.keyed(rp.sentence)
        out = self.call(trc.many())
        self.assertEqual(out.code, 0, out.err)
        self.assertIn(f"  unattended retention: the file declares it, but the adoption "
                      f"authorises nothing unattended; only the unattended sentence authorises "
                      f"it: run workflow-manager adopt-retention-policy {self.repo}", out.out)
        self.assertEqual(out.out.count(ENFORCED[0]), 1)

    def test_a_file_without_the_key_prints_neither_line(self):
        out = self.call(trc.many())
        self.assertEqual(out.code, 0, out.err)
        self.assertNotIn("unattended retention", out.out)
        self.assertNotIn("not enforced", out.out)
        self.assertNotIn("enforced by", out.out)

    def test_the_nothing_to_do_preview_ends_with_the_lines(self):
        self.keyed()
        out = self.call(trc.oldest_first(trc.entry("a")))
        self.assertEqual(out.code, 0, out.err)
        self.assertEqual(out.out.splitlines()[-3:], [ADOPTED_UNATTENDED, *ENFORCED])
        self.assertTrue(out.out.startswith("retention cleanup: nothing to do"))


class TestPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = " ".join((REPO_ROOT / "docs" / "retention.md").read_text().split())

    def test_the_page_documents_the_key_the_sentences_and_the_status(self):
        for needle in (
                "### The unattended key",
                "`cleanup`", "`prune`", "`keep_recent`", "`ttl_days`", "`prune_max_per_run`",
                "3 to 100000", "14 to 3650", "1 to 100",
                "at least one of `cleanup` and `prune` is `true`",
                "`mode` is `cleanup` or `both`",
                "Adopt the unattended retention policy",
                "The ordinary sentence, `Adopt the retention policy`, is refused",
                "An older Manager refuses a file carrying `unattended`",
                "`retention-cleanup TARGET --unattended`",
                "enforced by retention-cleanup --unattended: it archives and removes, then prunes "
                "archives of finished items whose review folder is already gone, older than N "
                "days, at most M per run, never one under an interrupted removal",
                "deleting an archive cannot be undone; the archive store is "
                "~/.local/share/workflow-archive, which the Manager does not back up",
                "unattended.prune is false, so no archive is pruned",
                "It authorises pruning too only when the file's `unattended.prune` is `true`, "
                "within its numbers",
                "### The unattended prune", "`review-folder-present`", "`removal-interrupted`",
                "Dry-run equivalence", "`prune ID --apply`", "`nothing-to-prune`",
                "`max_per_run`", "`skipped`", "left for a later run",
                "retention-audit.jsonl",
                "`nothing-eligible`",
                "the N newest entries of the report's finished list",
                "retention-cleanup runs with --confirm or, under the adopted unattended policy, "
                "with --unattended",
                "an `unattended retention:` line",
                "reads `record-invalid` and the mode in force is `off`",
                "reads `adopted` and authorises unattended"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.page)

    def test_the_page_says_the_owner_adopts_again(self):
        self.assertEqual(self.page.count("so the owner adopts the policy again"), 2)
        for needle in (
                "and the owner adopts the policy again; a hand-written record",
                "print the same lines, except that the adopt preview, for a file adopted with "
                "the ordinary sentence only, says to adopt again with the unattended sentence "
                "it prints below"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.page)
        for needle in ("and the policy is adopted again", "so the policy is adopted again",
                       "print the same lines; a file without the key"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, self.page)

    def test_the_page_says_what_a_stop_and_the_cap_print(self):
        exit_codes = " ".join((REPO_ROOT / "docs" / "exit-codes.md").read_text().split())
        for text, needle in (
                (self.page, "Archives beyond the cap are not listed and are left for a later run."),
                (self.page, "`retention prune: stopped after N of M archives; `"),
                (self.page, "only when at least one archive was deleted, `retention prune: N of M "
                            "archives were deleted before the stop; `"),
                (exit_codes, "`retention cleanup: stopped after N of M items; `"),
                (exit_codes, "`retention prune: stopped after N of M archives; `"),
                (exit_codes, "the `stopped` line is what tells a stop apart")):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        for text, needle in (
                (self.page, "counted as `capped`"),
                (self.page, "(after a stop, `N of M archives were deleted before the stop`)"),
                (exit_codes, "closing line is what tells a stop apart"),
                (exit_codes, "closing `retention cleanup: stopped` line says")):
            with self.subTest(stale=needle):
                self.assertNotIn(needle, text)

    def test_the_page_says_an_interrupt_during_an_audit_write_is_recorded(self):
        for needle in (
                "An `interrupted` line is also written when the run is interrupted while the "
                "`started` line or an archive's `ok` line is being written",
                "for the `ok` line the archive is already deleted"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.page)

    def test_the_page_names_no_internal_id(self):
        for needle in ("unattended-retention-policy", "#254", "A1", "CP3", "WORKFLOW_STATE"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, self.page)

    def test_the_sentence_of_the_page_is_the_codes(self):
        self.assertIn(rp.unattended_sentence("0" * 64).split(" 0")[0], self.page)
        self.assertIn(ENFORCED[0].strip().replace("30 days", "N days").replace("3 per", "M per"), self.page)

    def test_the_old_not_enforced_wording_is_gone_from_the_code_and_the_pages(self):
        self.assertNotIn(OLD_NOT_ENFORCED, self.page)
        for stale in (STALE_ENFORCED, "never run unattended yet", "Prune is not yet unattended"):
            self.assertNotIn(stale, self.page)
        for stale in ("`prune` and `unattended.ttl_days` and `prune_max_per_run` are read and "
                      "validated, and used by nothing", "The Manager never runs any of them",
                      "Neither is run by the Manager", "Prune is never part of cleanup"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.page)
        self.assertNotIn("**not enforced yet**", self.page)
        self.assertNotIn("This release does not enforce the key", self.page)
        for path in (REPO_ROOT / "src" / "workflow_manager").glob("*.py"):
            with self.subTest(path=path.name):
                text = " ".join(path.read_text().split())
                self.assertNotIn(OLD_NOT_ENFORCED, text)
                self.assertNotIn(STALE_ENFORCED, text)
                self.assertNotIn("nothing runs unattended", path.read_text())
        exit_codes = " ".join((REPO_ROOT / "docs" / "exit-codes.md").read_text().split())
        self.assertNotIn(OLD_NOT_ENFORCED, exit_codes)
        self.assertIn("--unattended", exit_codes)
        self.assertIn("--json", exit_codes)

    def test_the_block_last_line_page_and_help_carry_the_unattended_form(self):
        self.assertIn(UNATTENDED_BLOCK_LAST.strip(), self.page)
        self.assertIn("this Manager release reads the policy and, for notify and both, evaluates "
                      "its thresholds in verify and doctor; it sends nothing, and cleans up only "
                      "when retention-cleanup runs with --confirm ```", self.page)
        self.assertIn("with --unattended when the file carries the unattended key", " ".join(
            run(ADOPT, "--help").stdout.split()))

    def test_the_pages_name_no_internal_id_for_the_run(self):
        pages = self.page + " " + " ".join(
            (REPO_ROOT / "docs" / "exit-codes.md").read_text().split())
        for needle in ("unattended-retention-run", "LPR", "EPR", "CP4", "M22", "M24"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, pages)

    def test_the_roadmap_row_names_the_issue_and_the_step_and_is_done(self):
        rows = [line for line in (REPO_ROOT / "docs" / "ROADMAP.md").read_text().splitlines()
                if line.startswith("| 50 |")]
        self.assertEqual(len(rows), 1)
        self.assertIn("#254", rows[0])
        self.assertIn("A1", rows[0])
        self.assertTrue(rows[0].rstrip().endswith("| Done (accepted by policy; a `feat:` change) |"))


if __name__ == "__main__":
    unittest.main()
