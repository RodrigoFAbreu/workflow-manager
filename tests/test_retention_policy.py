#!/usr/bin/env python3
"""The retention policy file: its strict loader, its adoption command and the
read-only block of `status --retention` and `doctor --retention`.

Hermetic: a scratch managed repository (the stub script of
`test_retention_status`), no network. No test writes into this repository.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import test_operator_ux as ux
import test_retention_status as rs
from support import REPO_ROOT, pinned_env
from test_operator_ux import run, tree_hash
from workflow_manager import cli, retention_policy as rp

GOOD = {"schema_version": 1, "mode": "both",
        "thresholds": {"finished_items": 10, "finished_folder_mib": 500,
                       "archives": 20, "prunable_archives": 5}}
ADOPT = "adopt-retention-policy"


class Base(rs.Scratch):
    """A scratch managed repository; helpers write the policy file and record."""

    def policy_file(self) -> Path:
        return rp.policy_path(self.repo)

    def record_file(self) -> Path:
        return rp.record_path(self.repo)

    def put(self, policy=GOOD, path=None):
        path = path or self.policy_file()
        path.parent.mkdir(exist_ok=True)
        if isinstance(policy, bytes):
            path.write_bytes(policy)
        elif isinstance(policy, str):
            path.write_text(policy)
        else:
            path.write_text(json.dumps(policy))
        return path

    def digest(self, policy=GOOD) -> str:
        return rp.digest_of(policy)

    def adopt(self, policy=GOOD):
        self.put(policy)
        proc = run(ADOPT, str(self.repo), "--confirm", rp.sentence(self.digest(policy)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def refused(self, *args, tree=True):
        before = tree_hash(self.repo)
        proc = run(ADOPT, str(self.repo), *args)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertTrue(proc.stderr.startswith("error: "), proc.stderr)
        self.assertRegex(proc.stderr, r"(?m)^next: ")
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(tree_hash(self.repo), before)
        return proc

    def errors(self, policy):
        return rp.policy_errors(policy)

    def state(self):
        return rp.load(self.repo)


def with_(**changes):
    policy = json.loads(json.dumps(GOOD))
    policy.update(changes)
    return policy


def threshold(**changes):
    policy = json.loads(json.dumps(GOOD))
    policy["thresholds"].update(changes)
    return policy


class TestSchema(Base):
    def test_a_valid_file_for_each_mode(self):
        for mode in rp.MODES:
            with self.subTest(mode=mode):
                self.assertEqual(self.errors(with_(mode=mode)), [])

    def test_off_may_keep_thresholds_and_may_have_none(self):
        self.assertEqual(self.errors({"schema_version": 1, "mode": "off"}), [])
        self.assertEqual(self.errors(with_(mode="off")), [])

    def test_a_mode_other_than_off_needs_a_threshold(self):
        for mode in ("notify", "cleanup", "both"):
            for thresholds in ({}, None):
                policy = {"schema_version": 1, "mode": mode}
                if thresholds is not None:
                    policy["thresholds"] = thresholds
                with self.subTest(mode=mode, thresholds=thresholds):
                    self.assertEqual(self.errors(policy),
                                     [f"mode {mode} needs at least one valid threshold"])

    def test_unknown_top_level_and_threshold_keys(self):
        self.assertEqual(self.errors(with_(extra=1)), ["unknown key 'extra'"])
        self.assertEqual(self.errors(threshold(ttl_days=3)), ["unknown threshold 'ttl_days'"])

    def test_missing_required_keys(self):
        self.assertEqual(self.errors({"mode": "off"}), ["schema_version is missing"])
        self.assertEqual(self.errors({"schema_version": 1}), ["mode is missing"])

    def test_schema_version_must_be_exactly_the_integer_one(self):
        for bad in (2, 0, True, 1.0, "1", None):
            with self.subTest(bad=bad):
                self.assertTrue(self.errors(with_(schema_version=bad)))

    def test_the_mode_is_lower_case_and_exact(self):
        for bad in ("Off", "BOTH", "on", "", None, 1, ["off"], "off "):
            with self.subTest(bad=bad):
                self.assertTrue(any(e.startswith("mode must be one of")
                                    for e in self.errors(with_(mode=bad))))

    def test_a_bool_is_not_an_integer_threshold(self):
        for value in (True, False):
            self.assertEqual(self.errors(threshold(archives=value)),
                             [f"thresholds.archives must be an integer, not {value!r}"])

    def test_a_float_or_string_threshold_is_refused(self):
        for value in (10.0, "10", None, [10]):
            with self.subTest(value=value):
                self.assertTrue(self.errors(threshold(finished_items=value)))

    def test_zero_is_refused_and_one_is_the_lower_bound(self):
        for key in rp.THRESHOLDS:
            with self.subTest(key=key):
                self.assertEqual(self.errors(threshold(**{key: 1})), [])
                self.assertEqual(self.errors(threshold(**{key: 0})),
                                 [f"thresholds.{key} must be from 1 to {rp.THRESHOLDS[key][0]}, not 0"])
                self.assertTrue(self.errors(threshold(**{key: -1})))

    def test_the_upper_bounds_are_inclusive(self):
        for key, (top, _) in rp.THRESHOLDS.items():
            with self.subTest(key=key):
                self.assertEqual(self.errors(threshold(**{key: top})), [])
                self.assertEqual(self.errors(threshold(**{key: top + 1})),
                                 [f"thresholds.{key} must be from 1 to {top}, not {top + 1}"])

    def test_thresholds_must_be_an_object(self):
        self.assertEqual(self.errors(with_(thresholds=[1])),
                         ["thresholds must be an object, not [1]"])

    def test_a_non_object_policy(self):
        self.assertEqual(self.errors([1]), ["the policy is not an object: [1]"])

    def test_a_refused_value_is_shown_through_repr_and_cut(self):
        problems = self.errors(with_(mode="x\x1b[31m" + "y" * 100))
        self.assertEqual(len(problems), 1)
        self.assertNotIn("\x1b", problems[0])
        self.assertIn("characters)", problems[0])

    def test_every_problem_is_listed(self):
        problems = self.errors({"schema_version": 2, "mode": "x", "thresholds": {"a": 1}, "z": 1})
        self.assertEqual(len(problems), 4)

    def test_file_refusals(self):
        cases = {
            "invalid utf-8": b"\xff\xfe{}",
            "invalid json": "{",
            "duplicate key": '{"schema_version":1,"mode":"off","mode":"off"}',
            "nested duplicate": '{"schema_version":1,"mode":"off","thresholds":{"archives":1,"archives":2}}',
            "NaN": '{"schema_version":1,"mode":"off","thresholds":{"archives":NaN}}',
            "Infinity": '{"schema_version":1,"mode":"off","thresholds":{"archives":Infinity}}',
            "deep": "[" * 5000 + "]" * 5000,
            "array": "[]",
            "lone surrogate": '{"schema_version":1,"mode":"off\\ud800"}',
            "empty": "",
        }
        for name, content in cases.items():
            with self.subTest(case=name):
                self.put(content)
                state = self.state()
                self.assertEqual((state.state, state.mode), (rp.INVALID, "off"))
                self.assertTrue(state.problems)
                self.assertIsNone(state.policy)

    def test_an_oversize_policy_is_refused_unparsed(self):
        self.put(json.dumps(with_(mode="off")) + " " * rp.POLICY_LIMIT)
        state = self.state()
        self.assertEqual(state.state, rp.INVALID)
        self.assertEqual(state.problems, (f"retention-policy.json is larger than {rp.POLICY_LIMIT} bytes",))

    def test_a_policy_at_the_limit_is_read(self):
        text = json.dumps(with_(mode="off"))
        self.put(text + " " * (rp.POLICY_LIMIT - len(text)))
        self.assertEqual(self.state().state, rp.NOT_ADOPTED)

    def test_oversize_record_is_refused(self):
        self.put()
        self.record_file().write_text(" " * (rp.RECORD_LIMIT + 1))
        state = self.state()
        self.assertEqual(state.state, rp.RECORD_INVALID)
        self.assertEqual(state.problems, (f"retention-adoption.json is larger than {rp.RECORD_LIMIT} bytes",))

    def test_a_symlinked_policy(self):
        real = self.outside / "real.json"
        self.put(GOOD, real)
        self.policy_file().parent.mkdir(exist_ok=True)
        self.policy_file().symlink_to(real)
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.INVALID, "off"))
        self.assertEqual(state.problems, ("retention-policy.json is a link",))

    def test_a_symlinked_record(self):
        self.adopt()
        real = self.outside / "record.json"
        real.write_bytes(self.record_file().read_bytes())
        self.record_file().unlink()
        self.record_file().symlink_to(real)
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.RECORD_INVALID, "off"))
        self.assertEqual(state.problems, ("retention-adoption.json is a link",))

    def test_a_directory_for_policy_or_record(self):
        self.policy_file().parent.mkdir(exist_ok=True)
        self.policy_file().mkdir()
        self.assertEqual(self.state().state, rp.INVALID)
        self.policy_file().rmdir()
        self.put()
        self.record_file().mkdir()
        self.assertEqual(self.state().state, rp.RECORD_INVALID)

    def test_a_symlinked_directory_is_refused_whatever_it_holds(self):
        real = self.outside / "wm"
        real.mkdir()
        self.put(GOOD, real / rp.POLICY_FILE)
        for name in (rp.RECORD_FILE,):
            (real / name).write_text("{}")
        target = self.repo / rp.DIRECTORY
        installed = (target / "installation.json").read_bytes()
        for child in list(target.iterdir()):
            child.unlink()
        target.rmdir()
        target.symlink_to(real)
        (real / "installation.json").write_bytes(installed)
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.INVALID, "off"))
        self.assertEqual(state.problems, (f"{rp.DIRECTORY} is a link",))

    def test_load_never_raises(self):
        with mock.patch.object(rp, "_load", side_effect=RuntimeError("boom")):
            state = rp.load(self.repo)
        self.assertEqual((state.state, state.mode), (rp.INVALID, "off"))


class TestStates(Base):
    def test_absent(self):
        state = self.state()
        self.assertEqual((state.state, state.mode, state.problems), (rp.ABSENT, "off", ()))

    def test_not_adopted(self):
        self.put()
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.NOT_ADOPTED, "off"))
        self.assertEqual(state.digest, self.digest())

    def test_adopted_carries_the_files_mode(self):
        for mode in ("notify", "cleanup", "both", "off"):
            with self.subTest(mode=mode):
                self.adopt(with_(mode=mode))
                state = self.state()
                self.assertEqual((state.state, state.mode), (rp.ADOPTED, mode))
                self.assertRegex(state.adopted_at, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_a_file_edited_after_adoption_is_changed_and_off(self):
        self.adopt()
        self.put(threshold(archives=21))
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.CHANGED, "off"))

    def test_a_reordered_file_with_the_same_content_stays_adopted(self):
        self.adopt()
        self.put('{"thresholds": {"prunable_archives": 5, "archives": 20, "finished_folder_mib": 500, '
                 '"finished_items": 10}, "mode": "both", "schema_version": 1}')
        self.assertEqual(self.state().state, rp.ADOPTED)

    def test_a_deleted_file_is_file_missing(self):
        self.adopt()
        self.policy_file().unlink()
        self.assertEqual((self.state().state, self.state().mode), (rp.FILE_MISSING, "off"))

    def test_an_invalid_file_beside_a_record_is_invalid(self):
        self.adopt()
        self.put("{")
        self.assertEqual(self.state().state, rp.INVALID)

    def _tamper(self, **changes):
        self.adopt()
        record = json.loads(self.record_file().read_text())
        record.update(changes)
        self.record_file().write_text(json.dumps(record))

    def test_a_tampered_record_digest_is_record_invalid(self):
        self._tamper(sha256="0" * 64)
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.RECORD_INVALID, "off"))
        self.assertEqual(state.problems, ("record sha256 is not the digest of its policy",))

    def test_a_tampered_record_policy_is_record_invalid(self):
        self._tamper(policy=threshold(archives=99))
        self.assertEqual(self.state().state, rp.RECORD_INVALID)

    def test_a_tampered_confirmation_is_record_invalid(self):
        self._tamper(confirmation="Adopt the retention policy 000000000000.")
        state = self.state()
        self.assertEqual((state.state, state.mode), (rp.RECORD_INVALID, "off"))
        self.assertEqual(state.problems, ("record confirmation does not name its policy",))

    def test_record_shape_refusals(self):
        self.adopt()
        good = json.loads(self.record_file().read_text())
        cases = {"extra key": dict(good, extra=1),
                 "missing key": {k: v for k, v in good.items() if k != "adopted_at"},
                 "version": dict(good, schema_version=2),
                 "timestamp": dict(good, adopted_at="yesterday"),
                 # a trailing newline would reach the status block raw
                 "timestamp newline": dict(good, adopted_at=good["adopted_at"] + "\n"),
                 "timestamp digits": dict(good, adopted_at="\u0662" + good["adopted_at"][1:])}
        for name, record in cases.items():
            with self.subTest(case=name):
                self.record_file().write_text(json.dumps(record))
                self.assertEqual(self.state().state, rp.RECORD_INVALID)
        self.record_file().write_text("[]")
        self.assertEqual(self.state().state, rp.RECORD_INVALID)

    def test_a_record_with_an_unrelated_digest_is_changed_not_adopted(self):
        self.adopt()
        self.put(threshold(archives=21))
        self.assertEqual(self.state().state, rp.CHANGED)

    def test_the_policy_file_alone_never_gives_a_mode(self):
        for mode in ("notify", "cleanup", "both"):
            self.put(with_(mode=mode))
            self.assertEqual(self.state().mode, "off")


class TestAdopt(Base):
    def test_preview_writes_nothing_and_prints_the_digest_and_sentence(self):
        self.put()
        before = tree_hash(self.repo)
        proc = run(ADOPT, str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(tree_hash(self.repo), before)
        digest = self.digest()
        self.assertIn(digest, proc.stdout)
        self.assertIn(f"Adopt the retention policy {digest[:12]}.", proc.stdout)
        self.assertIn("mode: both", proc.stdout)
        self.assertIn("not-adopted; mode off is in force", proc.stdout)
        self.assertFalse(self.record_file().exists())

    def test_not_managed_is_refused(self):
        proc = run(ADOPT, str(self.empty()))
        self.assertEqual(proc.returncode, 2)
        self.assertRegex(proc.stderr, r"(?m)^next: ")

    def test_an_absent_file_is_refused(self):
        proc = self.refused("--confirm", rp.sentence("0" * 64))
        self.assertIn("no retention policy file", proc.stderr)

    def test_an_invalid_file_is_refused_with_its_problems(self):
        self.put(with_(mode="nope"))
        proc = self.refused()
        self.assertIn("mode must be one of", proc.stderr)

    def test_refusals_for_the_sentence_leave_the_tree_unchanged(self):
        self.put()
        sentence = rp.sentence(self.digest())
        other = rp.sentence(self.digest(threshold(archives=1)))
        cases = {
            "empty": "",
            "no sentence": "yes please",
            "another digest": other,
            "zeros": "Adopt the retention policy 000000000000.",
            "no full stop": sentence[:-1],
            "short prefix": sentence[:-3] + ".",
            "long prefix": sentence[:-1] + "a.",
            "two digests": sentence + " " + other,
            "other words, wrong digest": "I agree. " + other,
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.refused("--confirm", text)

    def test_the_sentence_with_other_words_case_and_spacing_is_accepted(self):
        self.put()
        digest = self.digest()
        text = f"Yes:   ADOPT\n the  Retention policy {digest[:12].upper()}. thanks"
        # upper-case hex is folded: the digest compares as lower case
        proc = run(ADOPT, str(self.repo), "--confirm", text)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.state().state, rp.ADOPTED)

    def test_the_same_sentence_twice_is_accepted(self):
        self.put()
        sentence = rp.sentence(self.digest())
        proc = run(ADOPT, str(self.repo), "--confirm", sentence + " " + sentence)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_held_sentence_writes_exactly_the_record(self):
        proc = self.adopt()
        record = json.loads(self.record_file().read_text())
        self.assertEqual(list(record), ["schema_version", "sha256", "adopted_at", "confirmation", "policy"])
        self.assertEqual(record["sha256"], self.digest())
        self.assertEqual(record["policy"], GOOD)
        self.assertEqual(record["confirmation"], rp.sentence(self.digest()))
        self.assertEqual(rp.check_record(record), [])
        self.assertIn("nothing is archived, removed, pruned or sent", proc.stdout)
        leftovers = [p.name for p in self.record_file().parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_adoption_touches_nothing_else(self):
        self.put()
        before = tree_hash(self.repo, skip=(f"{rp.DIRECTORY}/{rp.RECORD_FILE}",))
        self.adopt()
        self.assertEqual(tree_hash(self.repo, skip=(f"{rp.DIRECTORY}/{rp.RECORD_FILE}",)), before)

    def test_re_adoption_after_a_change_replaces_the_record(self):
        self.adopt()
        self.put(threshold(archives=21))
        self.assertEqual(self.state().state, rp.CHANGED)
        changed = threshold(archives=21)
        proc = run(ADOPT, str(self.repo), "--confirm", rp.sentence(self.digest(changed)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.state().state, rp.ADOPTED)
        self.assertEqual(json.loads(self.record_file().read_text())["sha256"], self.digest(changed))

    def test_an_old_sentence_does_not_adopt_a_changed_file(self):
        old = rp.sentence(self.digest())
        self.adopt()
        self.put(threshold(archives=21))
        self.refused("--confirm", old)

    def test_an_oversize_confirmation_is_refused(self):
        self.put()
        self.refused("--confirm", rp.sentence(self.digest()) + " x" * rp.RECORD_LIMIT)

    def test_a_confirmation_with_a_lone_surrogate_is_refused(self):
        self.put()
        before = tree_hash(self.repo)
        arg = rp.sentence(self.digest()) + " \udcff"
        code = cli.main([ADOPT, str(self.repo), "--confirm", arg])
        self.assertEqual(code, 2)
        self.assertEqual(tree_hash(self.repo), before)

    def test_a_linked_directory_is_refused(self):
        self.put()
        real = self.outside / "elsewhere"
        real.mkdir()
        target = self.repo / rp.DIRECTORY
        keep = self.repo / "wm-real"
        target.rename(keep)
        target.symlink_to(keep)
        before = tree_hash(self.repo)
        proc = run(ADOPT, str(self.repo), "--confirm", rp.sentence(self.digest()))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(tree_hash(self.repo), before)

    def test_apply_itself_refuses_a_directory_swapped_for_a_link_after_the_load(self):
        self.put()
        state = rp.usable_policy(self.repo)
        target = self.repo / rp.DIRECTORY
        keep = self.repo / "wm-real"
        target.rename(keep)
        target.symlink_to(keep)
        before = tree_hash(self.repo)
        with self.assertRaises(rp.Refusal) as caught:
            rp.apply(self.repo, state, rp.sentence(state.digest))
        self.assertIn("is a link", caught.exception.cause)
        self.assertEqual(tree_hash(self.repo), before)

    def test_a_record_path_that_is_a_directory_is_refused(self):
        self.put()
        self.record_file().mkdir()
        proc = self.refused("--confirm", rp.sentence(self.digest()))
        self.assertIn("not a regular file", proc.stderr)

    def test_a_failed_replace_leaves_the_tree_unchanged_and_exits_1(self):
        self.put()
        before = tree_hash(self.repo)
        with mock.patch.object(rp.os, "replace", side_effect=OSError(28, "No space left on device")):
            code = cli.main([ADOPT, str(self.repo), "--confirm", rp.sentence(self.digest())])
        self.assertEqual(code, 1)
        self.assertEqual(tree_hash(self.repo), before)

    def test_the_stored_record_is_what_check_record_accepts(self):
        self.put()
        built = {"schema_version": 1, "sha256": self.digest(), "adopted_at": "2026-11-10T12:00:00Z",
                 "confirmation": rp.sentence(self.digest()), "policy": GOOD}
        self.assertEqual(rp.check_record(built), [])
        self.assertTrue(rp.check_record(dict(built, confirmation="x")))
        self.assertTrue(rp.check_record(dict(built, confirmation=rp.sentence(self.digest()) + "\ud800")))


class TestReport(Base):
    def setUp(self):
        super().setUp()
        self.install_stub()
        self.rep = self.put_report(rs.report(rs.finished("a-item")))

    def both_commands(self):
        for command in ("status", "doctor"):
            base = self.invoke(command, True, STUB_REPORT=str(self.rep))
            yield command, base

    def test_the_default_is_byte_identical(self):
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                got = self.invoke(command, True, STUB_REPORT=str(self.rep))
                self.assertNotIn("retention policy", got.stdout)
        self.assertNotIn("retention policy", self.invoke("status", False).stdout)

    def test_the_block_prints_before_the_report_and_changes_no_exit_code(self):
        self.adopt()
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                base, got = self.both(command, STUB_REPORT=str(self.rep))
                lines = got.stdout.splitlines()
                at = next(i for i, l in enumerate(lines) if l.startswith("retention policy: "))
                section = next(i for i, l in enumerate(lines) if l.startswith("retention ("))
                self.assertLess(at, section)
                self.assertEqual(lines[at + 1].strip()[:11], "thresholds:")
                self.assertIn("sends nothing, and cleans up only when retention-cleanup runs "
                              "with --confirm", lines[at + 2])
                self.assertNotIn("retention policy", base.stdout)

    def test_the_adopted_block_is_exact(self):
        self.adopt()
        got = self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout.splitlines()
        at = next(i for i, l in enumerate(got) if l.startswith("retention policy: "))
        self.assertRegex(got[at], rf"^retention policy: adopted, mode both \(digest {self.digest()[:12]}, "
                                  r"adopted \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\)$")
        self.assertEqual(got[at + 1], "  thresholds: finished items 10, finished folders 500 MiB, "
                                      "archives 20, prunable archives 5")
        self.assertEqual(got[at + 2], "  this Manager release reads the policy and, for notify and both, "
                                      "evaluates its thresholds in verify and doctor; it sends "
                                      "nothing, and cleans up only when retention-cleanup runs "
                                      "with --confirm")

    def test_each_other_state_names_mode_off(self):
        self.put()
        states = []
        # not-adopted
        got = self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout
        states.append((rp.NOT_ADOPTED, got))
        # changed
        self.adopt()
        self.put(threshold(archives=21))
        states.append((rp.CHANGED, self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout))
        # invalid
        self.put("{")
        states.append((rp.INVALID, self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout))
        # file-missing
        self.policy_file().unlink()
        states.append((rp.FILE_MISSING, self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout))
        # record-invalid
        self.put()
        self.record_file().write_text("{}")
        states.append((rp.RECORD_INVALID, self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout))
        for state, out in states:
            with self.subTest(state=state):
                self.assertIn(f"retention policy: {state} (", out)
                self.assertIn("mode off is in force", out)

    def test_a_policy_state_adds_no_unindented_next_line(self):
        self.put()
        for command in ("status", "doctor"):
            with self.subTest(command=command):
                base = self.invoke(command, True, STUB_REPORT=str(self.rep))
                lines = [l for l in base.stdout.splitlines() if l.startswith("next: ")]
                without = self.invoke(command, False)
                self.assertEqual(len(lines), len([l for l in without.stdout.splitlines()
                                                  if l.startswith("next: ")]))
        self.assertIn("  next: workflow-manager adopt-retention-policy", base.stdout)

    def test_a_control_character_in_a_problem_is_escaped(self):
        self.put(with_(mode="\x1b[31mred"))
        got = self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout
        self.assertNotIn("\x1b", got)
        self.assertIn("\\x1b", got)

    def test_at_most_five_problems_then_a_count(self):
        self.put({"schema_version": 2, "mode": "x", "a": 1, "b": 2, "c": 3, "d": 4, "e": 5})
        got = self.invoke("status", True, STUB_REPORT=str(self.rep)).stdout
        self.assertEqual(sum(l.startswith("  problem: ") for l in got.splitlines()), 5)
        self.assertRegex(got, r"(?m)^  and 2 more$")

    def test_the_block_prints_even_when_the_report_is_unavailable(self):
        self.put()
        got = self.invoke("status", True, STUB_MODE="exit", STUB_EXIT="3")
        self.assertIn("retention policy: not-adopted", got.stdout)
        self.assertIn("retention: not available", got.stdout)

    def test_without_the_option_nothing_is_printed(self):
        self.adopt()
        self.assertNotIn("retention policy", self.invoke("status", False).stdout)
        self.assertNotIn("retention policy", self.invoke("doctor", False).stdout)


class TestNothingElse(Base):
    def test_an_adopted_both_policy_makes_one_script_call_and_changes_nothing(self):
        self.install_stub()
        self.adopt()
        rep = self.put_report(rs.report(rs.finished("a-item", archive=True)))
        before = tree_hash(self.repo)
        for command in ("status", "doctor"):
            self.marker.unlink(missing_ok=True)
            self.invoke(command, True, STUB_REPORT=str(rep))
            calls = [json.loads(l) for l in self.marker.read_text().splitlines()]
            self.assertEqual(len(calls), 1, calls)
            self.assertIn("report", calls[0]["argv"])
            self.assertIn("--json", calls[0]["argv"])
            self.assertNotIn("archive", calls[0]["argv"])
        self.assertEqual(tree_hash(self.repo), before)

    def test_no_policy_command_other_than_adopt_writes_anything(self):
        self.adopt()
        before = tree_hash(self.repo)
        for argv in (["status"], ["verify"], ["doctor"]):
            run("--release-version", rs.PINNED_NEWEST, *argv, str(self.repo))
        self.assertEqual(tree_hash(self.repo), before)

    def test_the_module_never_runs_a_subprocess_or_the_script(self):
        text = (REPO_ROOT / "src/workflow_manager/retention_policy.py").read_text()
        for word in ("subprocess", "Popen", "workflow_retention", "os.system", "urllib", "socket"):
            self.assertNotIn(word, text)


class TestFollowUps(Base):
    """The four follow-ups of #192 and the two 'only reads' wording fixes."""

    def test_the_help_names_the_link_and_non_regular_file_refusals(self):
        own = " ".join(ux.help_of(ADOPT).split())
        self.assertIn(".workflow-manager is a link", own)
        self.assertIn("the record path is not a regular file", own)
        self.assertIn("evaluates its thresholds in verify and doctor", own)
        self.assertNotIn("only reads", own)

    def test_the_invalid_step_names_the_command(self):
        self.put(with_(mode="nope"))
        want = f"then run {rp.adopt_command(self.repo)} to preview it"
        state = self.state()
        self.assertEqual(state.state, rp.INVALID)
        self.assertIn(want, rp.block(state, self.repo)[-1])
        with self.assertRaises(rp.Refusal) as caught:
            rp.usable_policy(self.repo)
        self.assertIn(want, caught.exception.step)

    def test_an_impossible_adopted_at_is_a_problem(self):
        self.adopt()
        record = json.loads(self.record_file().read_text())
        self.assertEqual(rp.check_record(record), [])
        for stamp in ("2026-99-99T99:99:99Z", "2026-02-30T00:00:00Z", "2026-01-01T24:00:00Z",
                      "2026-01-01T00:00:60Z"):
            with self.subTest(stamp=stamp):
                problems = rp.check_record({**record, "adopted_at": stamp})
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("adopted_at is not a UTC timestamp", problems[0])

    def test_the_directory_is_synced_after_the_replace(self):
        self.put()
        target = self.repo / "synced.json"
        events = []
        real_replace, real_fsync, real_open = os.replace, os.fsync, os.open
        fds = {}

        def replace(src, dst):
            events.append("replace")
            return real_replace(src, dst)

        def opener(path, flags, *a, **k):
            fd = real_open(path, flags, *a, **k)
            if flags & os.O_DIRECTORY:
                fds[fd] = Path(path)
            return fd

        def fsync(fd):
            if fd in fds:
                events.append(("dirsync", fds[fd]))
            return real_fsync(fd)

        with mock.patch.object(os, "replace", replace), mock.patch.object(os, "open", opener), \
                mock.patch.object(os, "fsync", fsync):
            rp._write_atomically(target, b"{}\n")
        self.assertEqual(events, ["replace", ("dirsync", target.parent)])

    def test_a_failing_directory_sync_does_not_mask_the_write(self):
        target = self.repo / "synced.json"
        real_fsync = os.fsync
        dirs = set()
        real_open = os.open

        def opener(path, flags, *a, **k):
            fd = real_open(path, flags, *a, **k)
            if flags & os.O_DIRECTORY:
                dirs.add(fd)
            return fd

        def fsync(fd):
            if fd in dirs:
                raise OSError(5, "boom")
            return real_fsync(fd)

        with mock.patch.object(os, "open", opener), mock.patch.object(os, "fsync", fsync):
            rp._write_atomically(target, b"{}\n")
        self.assertEqual(target.read_bytes(), b"{}\n")
        self.assertEqual([p.name for p in target.parent.glob(".synced.json.*")], [])

    def test_the_old_only_reads_claim_is_gone(self):
        self.adopt()
        out = run(ADOPT, str(self.repo), "--confirm", rp.sentence(self.digest()))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("evaluates its thresholds in verify and doctor", out.stdout)
        self.assertNotIn("only reads", out.stdout)
        block = " ".join(rp.block(self.state(), self.repo))
        self.assertNotIn("only reads", block)
        page = (REPO_ROOT / "docs/retention.md").read_text()
        self.assertNotIn("only reads", page)
        self.assertIn(rp.block(self.state(), self.repo)[2].strip(), page)


class TestStepFor(unittest.TestCase):
    """`step_for` is the step `block` prints, extracted so `retention-cleanup` and the
    block never drift; `block`'s own output is the one it had before."""

    TARGET = Path("/t")

    def states(self):
        return [rp.PolicyState(name, problems=("a problem",))
                for name in (rp.FILE_MISSING, rp.INVALID, rp.NOT_ADOPTED, rp.RECORD_INVALID,
                             rp.CHANGED)]

    def test_block_ends_with_step_for_for_every_state_but_adopted_and_absent(self):
        for state in self.states():
            with self.subTest(state=state.state):
                self.assertEqual(rp.block(state, self.TARGET)[-1],
                                 f"  next: {rp.step_for(state.state, self.TARGET)}")

    def test_block_output_is_unchanged(self):
        adopt = "workflow-manager adopt-retention-policy /t"
        want = {
            rp.FILE_MISSING: ["retention policy: file-missing (the adoption record has no policy "
                              "file); mode off is in force", "  problem: a problem",
                              "  next: restore .workflow-manager/retention-policy.json, or "
                              "remove .workflow-manager/retention-adoption.json if the policy "
                              "is withdrawn"],
            rp.INVALID: ["retention policy: invalid (the policy file is refused); mode off is "
                         "in force", "  problem: a problem",
                         "  next: fix .workflow-manager/retention-policy.json as named, then "
                         f"run {adopt} to preview it"],
            rp.NOT_ADOPTED: ["retention policy: not-adopted (the policy file is valid and not "
                             "adopted); mode off is in force", "  problem: a problem",
                             f"  next: {adopt}"],
            rp.RECORD_INVALID: ["retention policy: record-invalid (the adoption record is "
                                "refused); mode off is in force", "  problem: a problem",
                                f"  next: {adopt}"],
            rp.CHANGED: ["retention policy: changed (the policy file changed since it was "
                         "adopted); mode off is in force", "  problem: a problem",
                         f"  next: {adopt}"],
        }
        for state in self.states():
            with self.subTest(state=state.state):
                self.assertEqual(rp.block(state, self.TARGET), want[state.state])
        self.assertEqual(rp.block(rp.PolicyState(rp.ABSENT), self.TARGET), [])

    def test_absent_has_the_first_contact_step_and_adopted_has_none(self):
        self.assertEqual(
            rp.step_for(rp.ABSENT, self.TARGET),
            'write .workflow-manager/retention-policy.json with mode "cleanup" or "both" '
            "(docs/retention.md shows the file), then run "
            "workflow-manager adopt-retention-policy /t")
        with self.assertRaises(ValueError):
            rp.step_for(rp.ADOPTED, self.TARGET)


AGE = "finished_max_age_days"
GOOD_DIGEST = "5fa01cefcc02203bca455416b220cca79da62c2b281d36bed3c30b4731574fa7"  # GOOD at 8ff4f43


def age_only(days, mode="cleanup"):
    return {"schema_version": 1, "mode": mode, "thresholds": {AGE: days}}


class TestAgeKey(Base):
    def test_the_age_key_is_valid_from_one_to_3650(self):
        for days in (1, 30, 3650):
            with self.subTest(days=days):
                self.assertEqual(self.errors(age_only(days)), [])
        for days in (0, 3651, True, 1.5, "30"):
            with self.subTest(days=days):
                self.assertTrue(self.errors(age_only(days)))
        self.assertEqual(self.errors(age_only(3651, mode="off")),
                         [f"thresholds.{AGE} must be from 1 to 3650, not 3651"])
        self.assertTrue(self.errors({**age_only(30), "schema_version": 2}))

    def test_the_digest_of_a_policy_without_the_key_is_unchanged(self):
        self.assertEqual(self.digest(GOOD), GOOD_DIGEST)
        with_key = threshold(**{AGE: 30})
        self.assertNotEqual(self.digest(with_key), GOOD_DIGEST)
        self.assertNotEqual(rp.sentence(self.digest(with_key)), rp.sentence(GOOD_DIGEST))
        self.assertNotEqual(self.digest(with_key), self.digest(threshold(**{AGE: 31})))

    def test_cleanup_mode_may_set_only_the_age_key(self):
        self.assertEqual(self.errors(age_only(30)), [])
        self.assertEqual(rp.describe(age_only(30)), "finished age limit 30 days")
        self.assertEqual(rp.describe(GOOD),
                         "finished items 10, finished folders 500 MiB, archives 20, "
                         "prunable archives 5")
        self.assertEqual(rp.SCHEMA_VERSION, 1)


class TestDocs(unittest.TestCase):
    def test_the_page_has_the_section_and_the_exit_codes_row(self):
        page = (REPO_ROOT / "docs/retention.md").read_text()
        self.assertIn("## Retention policy", page)
        for needle in (".workflow-manager/retention-policy.json", "adopt-retention-policy",
                       "Adopt the retention policy", "mode off", "retention-adoption.json"):
            self.assertIn(needle, page)
        codes = (REPO_ROOT / "docs/exit-codes.md").read_text()
        self.assertRegex(codes, r"(?m)^\| [012] \| `adopt-retention-policy`")

    def test_the_docs_name_no_work_item_id(self):
        for name in ("retention.md", "exit-codes.md"):
            self.assertNotIn("retention-policy-file", (REPO_ROOT / "docs" / name).read_text())

    def test_help_and_usage_list_the_command(self):
        top = ux.help_of()
        self.assertRegex(top, rf"\b{ADOPT}\s+\S")
        own = ux.help_of(ADOPT)
        self.assertIn("Exit", own)
        self.assertIn("--confirm", own)
        self.assertIn("adopt-retention-policy <target>", cli.__doc__)

    def test_the_command_is_in_the_inventory(self):
        self.assertIn(ADOPT, ux.TARGET_COMMANDS)


if __name__ == "__main__":
    unittest.main()
