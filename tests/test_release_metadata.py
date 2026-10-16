#!/usr/bin/env python3
"""Release metadata and `min_manager_version` (`workflow-manager-release-agnostic`,
CP2; plan 3.4 and 4).

A release's manifest may carry a `manager` block with the data the Manager
hard-codes for the releases it was built with. Built-in data wins for those; a
later release uses its block, and a missing or unreadable block is an
`incomplete-inspection` warning, never a clean bill. Every release here is
synthetic (`7.0.x`, above the built-in data), served from a temporary directory
or a loopback server, with a private release cache per test.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import test_bootstrap as tb
from test_discovery import NEWER, UNPINNED, _listing, _Mirror, _Stub

import workflow_manager.cli as cli_module
import workflow_manager.compatibility as comp
import workflow_manager.package as package_module
from workflow_manager import advice
from workflow_manager import source as release_source
from workflow_manager.installation import Installation
from workflow_manager.release import (
    ManagerBlock,
    ReleaseIntegrityError,
    manager_version_ok,
    parse_manager_block,
)

POSTURE = "7.0.2 added a persisted shape an older release cannot read."
BLOCK = {
    "schema_version": 1,
    "min_manager_version": "1.0.0",
    "downgrade_boundary": {
        "posture": POSTURE,
        "undetectable": None,
        "signals": [{"name": "gate-evidence", "label": "gate evidence",
                     "detect": {"kind": "state-key", "key": "gate_evidence"}}],
    },
    "new_work_only": ["The 7.0.2 stamp is written only on new work items."],
    "gate_default_change": "",
    "conformance": {"suites": {"x_test.py": 3}, "portability_exceptions": []},
}


def block(**changes) -> dict:
    out = json.loads(json.dumps(BLOCK))
    for key, value in changes.items():
        if value is ...:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def facts(state=None, items=()):
    return SimpleNamespace(state=state or {}, items=list(items))


def item(**fields):
    base = dict(id="w", phase="IMPLEMENTING", governing="2.2", work_item_type="process",
                parent=None, entry={}, declarations=None, registry_ids=())
    base.update(fields)
    return comp.WorkItemFacts(**base)


class TestTheBlockReader(unittest.TestCase):
    def test_a_valid_block_parses(self):
        parsed = parse_manager_block(BLOCK)
        self.assertEqual(parsed.min_manager_version, "1.0.0")
        self.assertEqual(parsed.downgrade_boundary.posture, POSTURE)
        self.assertEqual(parsed.new_work_only, ("The 7.0.2 stamp is written only on new work items.",))
        self.assertEqual(parsed.conformance.suites, {"x_test.py": 3})
        self.assertEqual(parsed.missing_items(), ())

    def test_every_item_is_optional_and_a_missing_one_is_named(self):
        parsed = parse_manager_block({"schema_version": 1})
        self.assertEqual(parsed.missing_items(), ManagerBlock.ITEMS)
        self.assertIsNone(parsed.min_manager_version)

    def test_shape_errors_refuse_with_the_manifest_shape_kind(self):
        bad_signal = block()
        del bad_signal["downgrade_boundary"]["signals"][0]["detect"]
        cases = {
            "not an object": [],
            "no schema_version": {},
            "schema_version as text": {"schema_version": "1"},
            "schema_version true": {"schema_version": True},
            "a newer schema": {"schema_version": 2},
            "bad minimum": block(min_manager_version="1.x"),
            "numeric minimum": block(min_manager_version=1),
            "empty minimum": block(min_manager_version=""),
            "new_work_only not a list": block(new_work_only="text"),
            "new_work_only item": block(new_work_only=[1]),
            "gate change not text": block(gate_default_change=3),
            "boundary not an object": block(downgrade_boundary="x"),
            "boundary without posture": block(downgrade_boundary={"signals": []}),
            "signals not a list": block(downgrade_boundary={"posture": "", "signals": {}}),
            "signal without detect": bad_signal,
            "signal name not kebab-case": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "Bad_Name", "label": "l", "detect": {"kind": "state-key", "key": "k"}}]}),
            "unknown detector kind": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l", "detect": {"kind": "git-grep", "key": "k"}}]}),
            "state-key without key": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l", "detect": {"kind": "state-key"}}]}),
            "state-key empty key": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l", "detect": {"kind": "state-key", "key": ""}}]}),
            "state-value with a list value": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l",
                 "detect": {"kind": "state-value", "key": "k", "value": [1]}}]}),
            "state-value with a float": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l",
                 "detect": {"kind": "state-value", "key": "k", "value": 1.5}}]}),
            "item-governing with a number": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l", "detect": {"kind": "item-governing", "value": 2}}]}),
            "item-phase with no phases": block(downgrade_boundary={"posture": "", "signals": [
                {"name": "a", "label": "l", "detect": {"kind": "item-phase", "phases": []}}]}),
            "empty conformance": block(conformance={}),
            "conformance without exceptions": block(conformance={"suites": {}}),
            "conformance without suites": block(conformance={"portability_exceptions": []}),
            "suite count negative": block(conformance={
                "suites": {"x": -1}, "portability_exceptions": []}),
            "suite count a bool": block(conformance={
                "suites": {"x": True}, "portability_exceptions": []}),
            "exception without reason": block(conformance={
                "suites": {}, "portability_exceptions": [{"suite": "a", "test": "b"}]}),
        }
        for name, raw in cases.items():
            with self.subTest(name), self.assertRaises(ReleaseIntegrityError) as caught:
                parse_manager_block(raw)
            self.assertEqual(caught.exception.kind, "manifest-shape")

    def test_a_newer_schema_is_reported_as_needing_a_newer_manager(self):
        with self.assertRaisesRegex(ReleaseIntegrityError, "needs a newer Manager"):
            parse_manager_block({"schema_version": 2})

    def test_optional_fields_default(self):
        parsed = parse_manager_block(block(downgrade_boundary={"posture": ""}, conformance={
            "suites": {}, "portability_exceptions": [{"suite": "a", "test": "b", "reason": "r"}]}))
        self.assertIsNone(parsed.downgrade_boundary.undetectable)
        self.assertEqual(parsed.downgrade_boundary.signals, ())
        exception = parsed.conformance.portability_exceptions[0]
        self.assertEqual((exception.requires, exception.defect), (None, None))

    def test_minimum_version_comparison(self):
        for minimum, manager, ok in (
                (None, "1.0.0", True), ("1.13.0", "1.13.0", True), ("1.13.0", "1.14.0", True),
                ("1.13.0", "1.12.9", False), ("1.13.0", "1.9.0", False), ("1.2", "1.2.0", True),
                ("9.0.0", "0.0.0.dev0", True), ("9.0.0", None, True), ("9.0.0", "", True)):
            with self.subTest(minimum=minimum, manager=manager):
                self.assertIs(manager_version_ok(minimum, manager), ok)


class TestTheDeclarativeDetectors(unittest.TestCase):
    def detect(self, spec: dict, repo):
        parsed = parse_manager_block(block(downgrade_boundary={"posture": "p", "signals": [
            {"name": "s", "label": "l", "detect": spec}]}))
        return comp.boundary_from_block(parsed).signals[0].detect(repo)

    def test_state_key_finds_a_non_empty_key_anywhere(self):
        spec = {"kind": "state-key", "key": "gate_evidence"}
        self.assertTrue(self.detect(spec, facts({"work_items": {"a": {"gate_evidence": {"x": 1}}}})))
        self.assertFalse(self.detect(spec, facts({"work_items": {"a": {"gate_evidence": {}}}})))
        self.assertFalse(self.detect(spec, facts({})))

    def test_state_value_compares_after_parsing_and_type_aware(self):
        state = {"a": {"flag": True, "count": 1, "text": "1"}}
        for key, value, found in (
                ("flag", True, True), ("flag", 1, False), ("count", 1, True),
                ("count", True, False), ("count", "1", False), ("text", "1", True),
                ("text", 1, False), ("flag", None, False)):
            with self.subTest(key=key, value=value):
                spec = {"kind": "state-value", "key": key, "value": value}
                self.assertIs(bool(self.detect(spec, facts(state))), found)

    def test_item_detectors(self):
        items = [item(id="a", governing="2.2", phase="AMENDING_PLAN", entry={"stamp": True}),
                 item(id="b", governing="2.1", phase="MILESTONE_COMPLETE", entry={"stamp": 1})]
        repo = facts(items=items)
        self.assertEqual(len(self.detect({"kind": "item-governing", "value": "2.2"}, repo)), 1)
        self.assertEqual(len(self.detect({"kind": "item-phase", "phases": ["AMENDING_PLAN", "X"]},
                                         repo)), 1)
        self.assertEqual(self.detect({"kind": "item-field", "key": "stamp", "value": True}, repo),
                         ["a: stamp True"])
        self.assertEqual(self.detect({"kind": "item-field", "key": "stamp", "value": 1}, repo),
                         ["b: stamp 1"])
        self.assertEqual(self.detect({"kind": "item-field", "key": "missing", "value": None}, repo),
                         [])


class TestTheResolver(unittest.TestCase):
    def test_built_in_data_wins_even_when_a_block_is_present(self):
        metadata = comp.ReleaseMetadata(versions=("2.12.0",),
                                        blocks={"2.12.0": parse_manager_block(block())})
        data, missing = metadata.data("2.12.0")
        self.assertEqual(missing, ())
        self.assertIs(data.boundary, comp.DOWNGRADE_BOUNDARIES["2.12.0"])
        self.assertEqual(data.new_work_only, comp.NEW_WORK_ONLY["2.12.0"])
        self.assertEqual(comp.coverage_findings("2.11.0", "2.12.0", metadata), [])

    def test_an_unknown_version_without_a_block_is_neutral_and_flagged(self):
        metadata = comp.ReleaseMetadata(versions=("7.0.2",), blocks={"7.0.2": None})
        data, missing = metadata.data("7.0.2")
        self.assertEqual((data.boundary.posture, data.new_work_only, data.gate_change),
                         ("", (), ""))
        self.assertEqual(missing, ManagerBlock.ITEMS)
        found = comp.coverage_findings("2.12.0", "7.0.2", metadata)
        self.assertEqual([f.title for f in found], [comp.NO_DATA_TITLE])
        self.assertEqual({f.id for f in found}, {"incomplete-inspection"})
        self.assertIn("are not assessed", found[0].detail)

    def test_a_block_that_lacks_an_item_names_it(self):
        parsed = parse_manager_block({"schema_version": 1, "new_work_only": []})
        metadata = comp.ReleaseMetadata(versions=("7.0.2",), blocks={"7.0.2": parsed})
        found = comp.coverage_findings("2.12.0", "7.0.2", metadata)
        self.assertIn("lacks downgrade_boundary, gate_default_change, conformance",
                      found[0].detail)

    def test_the_range_is_directional(self):
        metadata = comp.ReleaseMetadata(versions=("7.0.2",), blocks={"7.0.2": None})
        self.assertEqual(len(comp.coverage_findings("2.12.0", "7.0.3", metadata)), 1)
        self.assertEqual(len(comp.coverage_findings("7.0.3", "2.12.0", metadata)), 1)
        self.assertEqual(len(comp.coverage_findings("7.0.2", "7.0.3", metadata)), 0)
        self.assertEqual(len(comp.coverage_findings("7.0.2", "7.0.1", metadata)), 1,
                         "a downgrade reads the installed release itself")
        self.assertEqual(comp.coverage_findings("7.0.3", "7.0.2", metadata), [],
                         "the target of a downgrade is not crossed")
        self.assertEqual(comp.coverage_findings("7.0.2", "7.0.2", metadata), [])

    def test_an_incomplete_catalog_is_one_finding_above_the_built_in_data(self):
        metadata = comp.ReleaseMetadata(catalog_incomplete="the listing may be truncated")
        found = comp.coverage_findings("2.12.0", "7.0.3", metadata)
        self.assertEqual([f.title for f in found], [comp.CATALOG_TITLE])
        self.assertIn("between 2.12.0 and 7.0.3", found[0].detail)
        self.assertEqual(comp.coverage_findings("2.11.0", "2.12.0", metadata), [])

    def test_the_titles_never_withhold_a_write(self):
        for title in comp.RELEASE_COVERAGE_TITLES:
            with self.subTest(title):
                finding = comp.Finding(comp.WARNING, "incomplete-inspection", title, "x")
                self.assertFalse(comp.writes_withheld([finding], (), True))
                self.assertIn(title, comp.PREDICATE_EXCLUDED)
                self.assertTrue(advice.coverage_step(title))
        other = comp.Finding(comp.WARNING, "incomplete-inspection", "something else", "x")
        self.assertTrue(comp.writes_withheld([other], (), True))

    def test_every_coverage_finding_this_module_emits_has_a_listed_title(self):
        metadata = comp.ReleaseMetadata(
            versions=("7.0.2", "7.0.3"), blocks={"7.0.2": None},
            unreadable={"7.0.3": "offline"}, catalog_incomplete="why")
        for finding in comp.coverage_findings("2.12.0", "7.0.4", metadata):
            self.assertIn(finding.title, comp.RELEASE_COVERAGE_TITLES)


class _Published(_Mirror):
    """A directory mirror whose `7.0.2` and `7.0.3` carry the blocks a test names."""

    UNPINNED_VERSIONS = ()

    def publish(self, mirror: Path, version: str, block=None):
        tree = tb.synthesize_next_release(
            tb.support.release(tb.NEWEST_RELEASE),
            self.tmp / "trees" / f"{version}-{len(list((self.tmp / 'trees').glob(version + '*')))
                                              if (self.tmp / 'trees').exists() else 0}", version)
        if block is not None:
            path = tree.root / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["manager"] = block
            path.write_text(json.dumps(manifest, indent=2) + "\n")
        package_module.build_package(tree.root, mirror / version)

    def mirror_of(self, releases: dict) -> Path:
        root = self.tmp / f"mirror-{len(list(self.tmp.glob('mirror-*')))}"
        root.mkdir()
        for version in self.PINNED:
            (root / version).symlink_to(self.source_dir / version)
        for version, block in releases.items():
            self.publish(root, version, block)
        return root

    def installed_at(self, version="7.0.0", source=None):
        self.assertEqual(self._cli("--release-version", version, "bootstrap", str(self.target),
                                   source_dir=source or self.source_dir), 0, self.cli_output)

    def doctor(self, *args, source):
        return self._cli(*args, "doctor", str(self.target), source_dir=source)


class TestReportsFromTheBlock(_Published):
    def test_a_block_drives_the_report_of_an_update(self):
        mirror = self.mirror_of({UNPINNED: block(gate_default_change="gates change")})
        self.installed_at("7.0.1")
        self.assertEqual(self.doctor(source=mirror), 1, self.cli_output)   # a gates warning
        self.assertIn("gates become automatic by default (7.0.2)", self.cli_stdout)
        self.assertIn("7.0.2: The 7.0.2 stamp is written only on new work items.", self.cli_stdout)
        self.assertNotIn("carries no compatibility data", self.cli_stdout)

    def test_a_downgrade_from_an_unpinned_release_reports_its_posture_and_signals(self):
        mirror = self.mirror_of({UNPINNED: block()})
        self.installed_at("7.0.1")
        self.assertEqual(self._cli("update", str(self.target), source_dir=mirror), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)
        state = self.target / "docs/ai-workflow/WORKFLOW_STATE.json"
        data = json.loads(state.read_text())
        data["gate_evidence"] = {"a": 1}
        state.write_text(json.dumps(data))
        self.assertEqual(self.doctor("--release-version", "7.0.1", source=mirror), 1,
                         self.cli_output)
        self.assertIn(f"Crossing {UNPINNED}: {POSTURE}", self.cli_stdout)
        self.assertIn("gate evidence: gate_evidence at gate_evidence", self.cli_stdout)

    def test_a_release_with_no_block_is_a_warning_not_a_clean_bill(self):
        mirror = self.mirror_of({UNPINNED: None})
        self.installed_at("7.0.1")
        self.assertEqual(self.doctor(source=mirror), 1, self.cli_output)
        self.assertIn(comp.NO_DATA_TITLE, self.cli_stdout)
        self.assertIn("inspection incomplete", self.cli_stdout)
        self.assertIn("not assessed", self.cli_stdout)
        self.assertNotIn("nothing found", self.cli_stdout)
        self.assertEqual(self._cli("update", str(self.target), source_dir=mirror), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)

    def test_a_block_of_the_wrong_shape_refuses_that_release(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version="x")})
        self.installed_at("7.0.1")
        for argv in (["--release-version", UNPINNED, "update"], ["update"]):
            with self.subTest(argv=argv):
                code = self._cli(*argv, str(self.target), source_dir=mirror)
                self.assertEqual(code, 1, self.cli_output)
                self.assertIn("manifest `manager` block", self.cli_stderr)
                self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")

    def test_the_advice_names_the_missing_metadata_and_never_the_data_repair(self):
        mirror = self.mirror_of({UNPINNED: None})
        self.installed_at("7.0.1")
        self.doctor(source=mirror)
        self.assertIn(f"read the release notes at {advice.WORKFLOW_RELEASES_URL}", self.cli_stdout)
        self.assertIn("`update` itself is not refused", self.cli_stdout)
        self.assertNotIn("repair-workflow-data-by-hand", self.cli_stdout)
        self.assertRegex(self.cli_stdout, r"workflow-manager .* update ")

    def test_a_repository_whose_own_data_is_unreadable_still_withholds_writes(self):
        mirror = self.mirror_of({UNPINNED: None})
        self.installed_at("7.0.1")
        (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").write_text("{not json")
        self.doctor(source=mirror)
        self.assertIn("repair-workflow-data-by-hand", self.cli_stdout)


class TestCrossedVersionCoverage(_Published):
    def explicit(self, mirror, *extra):
        return self._cli("--release-version", NEWER, *extra, "doctor", str(self.target),
                         source_dir=mirror)

    def test_an_intermediate_release_is_reported_from_a_directory_mirror(self):
        restricted = block(new_work_only=["Intermediate restriction."])
        mirror = self.mirror_of({UNPINNED: restricted, NEWER: block(new_work_only=[])})
        self.installed_at("7.0.1")
        self.assertEqual(self.explicit(mirror), 1, self.cli_output)
        self.assertIn("7.0.2: Intermediate restriction.", self.cli_stdout)
        self.assertNotIn(comp.CATALOG_TITLE, self.cli_stdout)

    def test_an_intermediate_release_is_reported_from_a_listing(self):
        mirror = self.mirror_of({UNPINNED: block(new_work_only=["From the listing."]),
                                 NEWER: block(new_work_only=[])})
        self.installed_at("7.0.1")
        self.stub(directory=mirror, listing=_listing(["7.0.0", "7.0.1", UNPINNED, NEWER]))
        code = self.run_default("--release-version", NEWER, "doctor", str(self.target))
        self.assertEqual(code, 1, self.cli_output)
        self.assertIn("7.0.2: From the listing.", self.cli_stdout)
        self.assertNotIn(comp.CATALOG_TITLE, self.cli_stdout)

    def test_a_template_mirror_cannot_enumerate_the_range(self):
        mirror = self.mirror_of({UNPINNED: block(), NEWER: block()})
        self.installed_at("7.0.1")
        stub = _Stub(mirror, b"[]")
        self.addCleanup(stub.server_close)
        self.addCleanup(stub.shutdown)
        code = self._cli("--release-version", NEWER, "doctor", str(self.target),
                         source_dir=stub.base + "/dl/{version}/")
        self.assertEqual(code, 1, self.cli_output)
        self.assertIn(comp.CATALOG_TITLE, self.cli_stdout)
        self.assertIn("a URL template and has no listing", self.cli_stdout)
        self.assertIn("name a source that lists its releases", self.cli_stdout)

    def test_a_possibly_truncated_listing_is_incomplete(self):
        mirror = self.mirror_of({UNPINNED: block(), NEWER: block()})
        self.installed_at("7.0.1")
        full = [f"1.0.{n}" for n in range(98)] + [UNPINNED, NEWER]
        self.stub(directory=mirror, listing=_listing(full))
        code = self.run_default("--release-version", NEWER, "doctor", str(self.target))
        self.assertEqual(code, 1, self.cli_output)
        self.assertIn("the listing may be truncated", self.cli_stdout)

    def test_an_intermediate_release_whose_manifest_is_unreachable_is_reported(self):
        mirror = self.mirror_of({UNPINNED: block(), NEWER: block()})
        self.installed_at("7.0.1")
        self.stub(directory=mirror, listing=_listing(["7.0.0", "7.0.1", UNPINNED, NEWER]),
                  block=(f"workflow-{UNPINNED}.manifest.json",))
        code = self.run_default("--release-version", NEWER, "doctor", str(self.target))
        self.assertEqual(code, 1, self.cli_output)
        self.assertIn(comp.UNREADABLE_DATA_TITLE, self.cli_stdout)
        self.assertIn(f"Workflow {UNPINNED}'s manifest could not be read", self.cli_stdout)
        self.assertNotIn("nothing found", self.cli_stdout)

    def test_a_listed_release_that_cannot_be_used_is_still_in_the_range(self):
        mirror = self.mirror_of({UNPINNED: block(), NEWER: block()})
        self.installed_at("7.0.1")
        raw = json.loads(_listing(["7.0.0", "7.0.1", UNPINNED, NEWER]))
        raw[2]["immutable"] = False
        extras = [{"tag_name": "v7.0.9", "draft": True, "prerelease": False, "immutable": True,
                   "assets": []}, {"tag_name": "nightly", "immutable": True, "assets": []},
                  {"tag_name": "v7.0.8", "draft": False, "prerelease": True, "immutable": True,
                   "assets": []}]
        self.stub(directory=mirror, listing=json.dumps(raw + extras).encode())
        code = self.run_default("--release-version", NEWER, "doctor", str(self.target))
        self.assertEqual(code, 1, self.cli_output)
        self.assertIn(comp.UNREADABLE_DATA_TITLE, self.cli_stdout)
        self.assertIn("Workflow 7.0.2's manifest could not be read: it is not marked immutable",
                      self.cli_stdout)
        self.assertNotIn("7.0.9", self.cli_stdout)
        self.assertNotIn("7.0.8", self.cli_stdout)
        self.assertNotIn(comp.CATALOG_TITLE, self.cli_stdout, "drafts and odd tags are not members")

    def test_a_downgrade_from_an_unpinned_release_offline_names_the_version(self):
        mirror = self.mirror_of({UNPINNED: block()})
        self.installed_at("7.0.1")
        self.assertEqual(self._cli("update", str(self.target), source_dir=mirror), 0)
        # the cache holds 7.0.2 (the installed release): read from its entry, offline
        dead = self.tmp / "dead"
        self.assertEqual(self._cli("--release-version", "7.0.1", "doctor", str(self.target),
                                   source_dir=mirror), 1, self.cli_output)
        self.assertIn(f"Crossing {UNPINNED}: {POSTURE}", self.cli_stdout)
        shutil.rmtree(self.cache / UNPINNED)
        self.assertEqual(self._cli("--release-version", "7.0.1", "doctor", str(self.target),
                                   source_dir=dead), 1, self.cli_output)
        self.assertIn(comp.UNREADABLE_DATA_TITLE, self.cli_stdout)
        self.assertIn(f"Workflow {UNPINNED}'s manifest could not be read", self.cli_stdout)
        self.assertNotIn("nothing found", self.cli_stdout)


class TestMinManagerVersion(_Published):
    NEEDS = "99.0.0"

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(cli_module, "_installed_version", return_value="1.13.0")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_explicit_version_that_needs_a_newer_manager_is_refused(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version=self.NEEDS)})
        for command in ("bootstrap", "update"):
            with self.subTest(command):
                repo = tb.empty_repo(self.tmp / f"r-{command}")
                if command == "update":
                    self.assertEqual(self._cli("--release-version", "7.0.1", "bootstrap",
                                               str(repo), source_dir=self.source_dir), 0)
                code = self._cli("--release-version", UNPINNED, command, str(repo),
                                 source_dir=mirror)
                self.assertEqual(code, 1, self.cli_output)
                self.assertIn(f"error: Workflow {UNPINNED} needs workflow-manager {self.NEEDS} "
                              "or newer; this is 1.13.0", self.cli_stderr)
                self.assertIn(f"next: upgrade the Manager to {self.NEEDS} or newer", self.cli_stderr)
                if command == "update":
                    self.assertEqual(Installation.read(repo).workflow_version, "7.0.1")

    def test_doctor_and_dry_run_refuse_an_explicit_version_too(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version=self.NEEDS)})
        self.installed_at("7.0.1")
        self.assertEqual(self._cli("--release-version", UNPINNED, "doctor", str(self.target),
                                   source_dir=mirror), 2, self.cli_output)
        self.assertIn("needs workflow-manager", self.cli_stderr)
        self.assertEqual(self._cli("--release-version", UNPINNED, "update", "--dry-run",
                                   str(self.target), source_dir=mirror), 1, self.cli_output)

    def test_a_bare_update_skips_it_with_one_note(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version="1.0.0"),
                                 NEWER: block(min_manager_version=self.NEEDS)})
        self.installed_at("7.0.0")
        self.assertEqual(self._cli("update", str(self.target), source_dir=mirror), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)
        self.assertEqual(self.cli_stderr.count(f"Workflow {NEWER} needs workflow-manager"), 1)
        self.assertIn("upgrade the Manager first", self.cli_stderr)

    def test_a_bare_bootstrap_skips_it_too(self):
        mirror = self.mirror_of({NEWER: block(min_manager_version=self.NEEDS)})
        self.assertEqual(self._cli("bootstrap", str(self.target), source_dir=mirror), 0,
                         self.cli_output)
        self.assertEqual(Installation.read(self.target).workflow_version, "7.0.1")
        self.assertIn(f"Workflow {NEWER} needs workflow-manager", self.cli_stderr)

    def test_the_skip_never_goes_below_the_installed_release(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version="1.0.0"),
                                 NEWER: block(min_manager_version=self.NEEDS)})
        self.installed_at("7.0.1")
        self.assertEqual(self._cli("update", str(self.target), source_dir=mirror), 0)
        self.assertEqual(Installation.read(self.target).workflow_version, UNPINNED)
        for argv in (["update"], ["update", "--dry-run"]):
            with self.subTest(argv=argv):
                mirror_two = self.mirror_of({UNPINNED: block(min_manager_version=self.NEEDS),
                                             NEWER: block(min_manager_version=self.NEEDS)})
                before = Installation.read(self.target).workflow_version
                code = self._cli(*argv, str(self.target), source_dir=mirror_two)
                self.assertEqual(code, 1, self.cli_output)
                self.assertIn(f"no usable release at or above the installed Workflow {before}",
                              self.cli_stderr)
                self.assertIn(f"next: upgrade the Manager to {self.NEEDS} or newer",
                              self.cli_stderr)
                self.assertEqual(Installation.read(self.target).workflow_version, before)

    def test_status_and_verify_only_note_it(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version=self.NEEDS)})
        with mock.patch.object(cli_module, "_installed_version", return_value="99.1.0"):
            self.installed_at("7.0.1")
            self.assertEqual(self._cli("update", str(self.target), source_dir=mirror), 0)
        for command in ("status", "verify"):
            with self.subTest(command):
                code = self._cli(command, str(self.target), source_dir=mirror)
                self.assertEqual(code, 0, self.cli_output)
                self.assertIn("note: Workflow 7.0.2 needs workflow-manager 99.0.0", self.cli_stderr)

    def test_a_development_build_satisfies_every_minimum(self):
        mirror = self.mirror_of({UNPINNED: block(min_manager_version=self.NEEDS)})
        for version in ("0.0.0.dev0", None):
            with self.subTest(version=version), \
                    mock.patch.object(cli_module, "_installed_version", return_value=version):
                repo = tb.empty_repo(self.tmp / f"dev-{version}")
                self.assertEqual(self._cli("--release-version", UNPINNED, "bootstrap", str(repo),
                                           source_dir=mirror), 0, self.cli_output)

    def test_a_built_in_release_ignores_its_block(self):
        self.assertIsNone(cli_module._needs_newer_manager(
            SimpleNamespace(version="2.12.0", manager=parse_manager_block(
                block(min_manager_version=self.NEEDS)))))


class TestTheDocs(unittest.TestCase):
    def test_the_new_error_has_an_advice_row_and_an_exit_code_row(self):
        error = release_source.incompatible("7.0.2", "1.14.0", "1.13.0")
        self.assertEqual(str(error),
                         "Workflow 7.0.2 needs workflow-manager 1.14.0 or newer; this is 1.13.0")
        step = advice.next_step(error, advice.Context())
        self.assertTrue(step.startswith("upgrade the Manager to 1.14.0 or newer ("), step)
        self.assertTrue(step.endswith("then run the same command again"), step)
        exit_codes = (Path(__file__).resolve().parent.parent / "docs" / "exit-codes.md").read_text()
        self.assertIn("needs a newer Manager", exit_codes)


if __name__ == "__main__":
    unittest.main()
