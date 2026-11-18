#!/usr/bin/env python3
"""The `unattended` policy key: its strict validation and its fail-safe for a
Manager that predates it. Hermetic: a scratch managed repository, no network, no
Git history (the base module is a vendored copy)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
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


if __name__ == "__main__":
    unittest.main()
