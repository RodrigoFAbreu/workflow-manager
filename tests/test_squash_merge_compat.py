#!/usr/bin/env python3
"""Squash-merge compatibility of the installed Workflow (`D-Squash-Compat`).

Checkpoint CP6 of `workflow-manager-trunk-model`, plan section 7 part 2. A
squash merge with a blank body drops a milestone branch's own commits, and
their `Workflow-*` trailers, from `main`'s history. Once the branch is gone
and its objects are pruned -- what a fresh clone of `main` sees -- every SHA
the completed item's state records on the branch is unreachable. This module
proves the installed `2.6.0` still works on such a `main`.

One disposable repository, bootstrapped from `2.6.0` by the real installer,
drives item `sq-item` from plan to `MILESTONE_COMPLETE` on
`milestone/sq-item` through the installed release's own acceptance-matrix
harness, the same drivers `test_workflow_2_6_0_hardening_disposable_repo.py`
uses (installed scripts, in subprocesses). The branch then lands on `main`
as one squash commit with a blank body; the branch is deleted, the reflog
expired and the objects pruned. On that `main`, and on a fresh clone of it:

- the state validates;
- a new item routes, reaches its bound plan-stage publication status, is
  approved and completes a checkpoint;
- the squashed item's id is refused for reuse;
- `workflow-manager verify` is clean.

History-independent and stdlib only (INV-5). Slow: it drives two full
lifecycles. Run directly:

    python3 tests/test_squash_merge_compat.py
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import support

import test_workflow_2_6_0_hardening_disposable_repo as hardening

from workflow_manager import cli
from workflow_manager.fixture import configure_throwaway_repo, init_git_repo
from workflow_manager.install import bootstrap

VERSION = "2.6.0"
ITEM = "sq-item"
BRANCH = f"milestone/{ITEM}"
NEW_ITEM = "next-item"
SQUASH_TITLE = f"feat: {ITEM}"
STATE_PATH = "docs/ai-workflow/WORKFLOW_STATE.json"
_SHA = re.compile(r"^[0-9a-f]{40}$")

_git = hardening._git


def _recorded_shas(value) -> set[str]:
    """Every full SHA anywhere in a work-item state entry."""
    if isinstance(value, str):
        return {value} if _SHA.match(value) else set()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return set().union(*(_recorded_shas(v) for v in value)) if value else set()
    return set()


def _has_commit(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True).returncode == 0


class TestSquashMergedItemOnMain(unittest.TestCase):
    """Plan section 7 part 2: a squashed, pruned `main`, then a fresh clone
    of it. Built once; each test works on its own checkout."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="wf-squash-")
        tmp = Path(cls._tmp.name)
        cls.root = tmp / "repo"
        cls.root.mkdir()
        cls.clock = 0
        try:
            cls._build(tmp)
        except BaseException:
            cls._tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def _drive(cls, checkout: Path, body: str) -> dict:
        cls.clock += 2_000
        return hardening.drive(checkout, body, clock=cls.clock)

    @classmethod
    def _build(cls, tmp: Path) -> None:
        root = cls.root
        init_git_repo(root)
        _git(root, "config", "user.email", "squash@example.invalid")
        _git(root, "config", "user.name", "Squash Compat")
        _git(root, "config", "commit.gpgsign", "false")
        bootstrap(root, support.release(VERSION), now=hardening.FIXED_NOW)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"chore: bootstrap workflow {VERSION}")
        cls.main_before = _git(root, "rev-parse", "HEAD").strip()

        _git(root, "checkout", "-q", "-b", BRANCH)
        cls._drive(root, f"""
            item = new_item({ITEM!r})
            item.milestone_plan()
            item.generate_plan_bundle()
            item.write_feedback("APPROVE")
            item.record_plan_reviews()
            item.approve_plan()
            item.implement_checkpoint("CP1", {{item.deliverable: "# {ITEM}\\n"}})
            item.generate_impl_bundle("implementation", expect_outcome="ordinary")
            item.write_feedback("APPROVE")
            item.approve_implementation()
            item.prepare_functional_review()
            item.accept_milestone()
        """)
        cls.branch_tip = _git(root, "rev-parse", "HEAD").strip()
        cls.branch_tree = _git(root, "rev-parse", "HEAD^{tree}").strip()
        cls.branch_trailers = _git(
            root, "log", "--format=%(trailers:only,unfold)", f"{cls.main_before}..{BRANCH}")
        cls.entry = json.loads((root / STATE_PATH).read_text())["work_items"][ITEM]
        cls.branch_only = sorted(
            sha for sha in _recorded_shas(cls.entry)
            if _has_commit(root, sha) and subprocess.run(
                ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, cls.main_before],
                capture_output=True).returncode != 0
        )

        # Squash onto main with a blank body, then forget the branch.
        _git(root, "checkout", "-q", "main")
        _git(root, "merge", "-q", "--squash", BRANCH)
        _git(root, "commit", "-q", "-m", SQUASH_TITLE)
        cls.squash = _git(root, "rev-parse", "HEAD").strip()
        _git(root, "branch", "-q", "-D", BRANCH)
        _git(root, "reflog", "expire", "--expire=now", "--all")
        _git(root, "gc", "-q", "--prune=now")

        cls.clone = tmp / "clone"
        _git(tmp, "clone", "-q", "--no-local", str(root), str(cls.clone))
        configure_throwaway_repo(cls.clone)
        _git(cls.clone, "config", "user.email", "squash@example.invalid")
        _git(cls.clone, "config", "user.name", "Squash Compat")
        _git(cls.clone, "config", "commit.gpgsign", "false")

    # ------------------------------------------------------------------
    # The history the assertions run against
    # ------------------------------------------------------------------

    def test_the_branch_carried_workflow_trailers_that_main_does_not(self):
        self.assertEqual(self.entry["phase"], "MILESTONE_COMPLETE")
        self.assertIn("Workflow-Checkpoint: CP1", self.branch_trailers)
        self.assertIn(f"Workflow-Work-Item: {ITEM}", self.branch_trailers)
        for repo in (self.root, self.clone):
            with self.subTest(repo=repo.name):
                self.assertEqual(_git(repo, "log", "-1", "--format=%B", self.squash),
                                 SQUASH_TITLE + "\n\n")
                self.assertEqual(_git(repo, "rev-parse", f"{self.squash}^@").split(),
                                 [self.main_before])
                self.assertEqual(
                    _git(repo, "log", "--format=%(trailers)", self.squash).strip(), "")
                self.assertEqual(_git(repo, "rev-parse", f"{self.squash}^{{tree}}").strip(),
                                 self.branch_tree)

    def test_every_branch_sha_the_item_records_is_unreachable(self):
        # At least the plan approval and the reviewed implementation head.
        self.assertIn(self.entry["reviewed_implementation_head"], self.branch_only)
        self.assertGreaterEqual(len(self.branch_only), 2, self.branch_only)
        for repo in (self.root, self.clone):
            for sha in [self.branch_tip, *self.branch_only]:
                with self.subTest(repo=repo.name, sha=sha):
                    self.assertFalse(_has_commit(repo, sha))

    # ------------------------------------------------------------------
    # The Workflow on the squashed main
    # ------------------------------------------------------------------

    def test_the_pruned_repository(self):
        self.assert_main_is_usable(self.root)

    def test_a_fresh_clone(self):
        self.assert_main_is_usable(self.clone)

    def assert_main_is_usable(self, checkout: Path) -> None:
        result = self._drive(checkout, f"""
            state = json.loads((root / {STATE_PATH!r}).read_text())
            ws.validate_state(state, repo_root=root)
            RESULT["squashed_phase"] = state["work_items"][{ITEM!r}]["phase"]
            config = json.loads((root / "docs/ai-workflow/WORKFLOW_CONFIG.json").read_text())
            RESULT["reuse"] = raised(lambda: ws.state_transaction(root, lambda s: ws.route_work_item(
                s, config, work_item_id={ITEM!r}, work_item_type="process",
                work_item_kind="process", plan_path="docs/ai-workflow/{ITEM}-plan.md",
                registry_path="docs/ai-workflow/registry/{ITEM}-registry.json", plan_revision=1,
                now="2026-01-02T00:00:00Z",
                mapping_path="docs/ai-workflow/requirements/{ITEM}-mapping.json",
                base_commit=scratch.head(), repo_root=root,
            )))
            item = new_item({NEW_ITEM!r})
            item.milestone_plan()
            item.generate_plan_bundle()
            RESULT["publication"] = ws.plan_review_publication_status(
                root, item.state(), item.wid)["status"]
            RESULT["bound"] = ws.PLAN_REVIEW_STATUS_BOUND
            item.write_feedback("APPROVE")
            item.record_plan_reviews()
            item.approve_plan()
            RESULT["approved_phase"] = item.entry()["phase"]
            item.implement_checkpoint("CP1", {{item.deliverable: "# {NEW_ITEM}\\n"}})
            RESULT["implemented_phase"] = item.entry()["phase"]
            ws.validate_state(item.state(), repo_root=root)
        """)
        self.assertEqual(result["squashed_phase"], "MILESTONE_COMPLETE")
        self.assertEqual(result["reuse"], "WorkItemTerminalReuseError")
        self.assertEqual(result["publication"], result["bound"])
        self.assertEqual(result["approved_phase"], "IMPLEMENTING")
        self.assertEqual(result["implemented_phase"], "SELF_REVIEWING_IMPLEMENTATION")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["verify", str(checkout)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn(f"installation matches workflow {VERSION}", out.getvalue())


if __name__ == "__main__":
    unittest.main()
