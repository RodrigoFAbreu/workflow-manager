#!/usr/bin/env python3
"""CP8 (`plan-amendment-mechanism`): disposable-repository update-path
validation -- `docs/ai-workflow/PLAN_AMENDMENT_MECHANISM_PLAN.md` section 4.

Every scenario here runs against a real, disposable Git repository under a
temp directory, bootstrapped from the real `2.3.1` release and updated to
the real, authored `2.4.0` release this repository ships -- never against a
synthetic release, and never against `~/Workspace/workflow-controller` or
any other real managed repository (REQ-13/REQ-14).

`TestUpdatePathNormalRepository` is scenario 1. `TestUpdatePathImplementing
FullAmendmentRehearsal` is scenario 2, continued past the update into the
full new sequence -- request amendment, an amended registry/plan (two
previously-COMPLETE checkpoints conservatively flipped to
`NEEDS_REVALIDATION` by the legacy no-anchor pre side, one never-started
checkpoint left alone, one brand-new checkpoint), reconciliation, and
resumed implementation to `SELF_REVIEWING_IMPLEMENTATION` -- which is also
section 4's items 2, 5, and 12. `TestUpdatePathSelfReviewingImplementation`
is scenario 3, the shorter variant (update, then a bare
`/request-plan-amendment`).

Slow (~10-20s per scenario): each bootstraps a real release and runs a full
synthetic implementation history through it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT

from workflow_manager.fixture import drive_synthetic_work_item_through_checkpoints
from workflow_manager.install import bootstrap, drift, update, verify
from workflow_manager.release import find_release

FIXED_NOW = "2026-01-01T00:00:00Z"
UPDATED_NOW = "2026-02-01T00:00:00Z"
AMENDMENT_NOW = "2026-03-01T00:00:00Z"
REAPPROVAL_NOW = "2026-03-02T00:00:00Z"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    ).stdout


def _run_installed(target: Path, script: str) -> str:
    """Runs `script` as a subprocess against the target's own installed
    `scripts/` -- the same "never an in-process import" discipline
    `fixture.py`'s own driver uses, so this always exercises whichever
    release is currently installed at `target`, never this source tree's
    copies."""
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=str(target), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"installed-module driver failed in {target}:\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


def _state(target: Path) -> dict:
    return json.loads((target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())


def _implementing_entry_reachable(target: Path, work_item_id: str, base_commit: str) -> bool:
    """Same "never an in-process import" discipline as `_run_installed`
    itself (OPUS-R145-005): the two call sites in this file that used to
    `sys.path.insert`/`__import__("workflow_state")` directly imported
    whichever release's copy happened to already be on `sys.path` from an
    earlier call in the same test process, rather than exercising the
    target's own installed `scripts/` the way every other check in this
    file does. Harmless in practice today (only the `2.4.0` copy is ever
    imported in this module), but a needless divergence from the discipline
    `fixture.py`'s own docstring states -- and it leaves deleted temp
    directories on `sys.path` for the rest of the test process. Routed
    through the same subprocess mechanism instead."""
    scripts_dir = str(target / "scripts")
    script = f"""
import json
import sys
sys.path.insert(0, {scripts_dir!r})
import workflow_state as ws
from pathlib import Path
root = Path({str(target)!r})
state = json.loads((root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())
entry = state["work_items"][{work_item_id!r}]
print(ws.implementing_entry_reachable(root, entry, {base_commit!r}))
"""
    return _run_installed(target, script).strip().splitlines()[-1] == "True"


class _RealReleaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_release = find_release(REPO_ROOT, "2.3.1")
        cls.successor_release = find_release(REPO_ROOT, "2.4.0")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir(parents=True)
        _git(self.target, "init", "-q", "-b", "main")
        _git(self.target, "config", "user.email", "cp8@example.invalid")
        _git(self.target, "config", "user.name", "CP8 Update Path")
        _git(self.target, "config", "commit.gpgsign", "false")
        # docs/defects/v2.4.0-001-workflow-manager-installation-record-
        # unclassified-at-plan-stage.md, mitigation (1): a live work item's
        # own plan-stage classification (generated under 2.3.1, or under an
        # unfixed 2.4.0 build) may not yet know about this path, so an
        # `update()`-driven change to it must never land inside a live
        # item's own base_commit..HEAD interval. Nothing about `install`'s
        # own behavior requires this file to be tracked (it is read from
        # the working tree, never from Git history) -- excluded locally,
        # never via the release's own (frozen, upstream-inherited)
        # `.gitignore` fragment.
        (self.target / ".git" / "info" / "exclude").write_text(".workflow-manager/\n")
        bootstrap(self.target, self.base_release, now=FIXED_NOW)
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "bootstrap workflow 2.3.1")


class TestUpdatePathNormalRepository(_RealReleaseCase):
    """Section 4, scenario 1: a normal `PLANNING`/no-open-work-item
    repository, updated from the real `2.3.1` to the real `2.4.0`."""

    def test_update_preserves_state_and_verifies_clean_against_the_successor(self):
        state_before = (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text()
        _, changes = update(self.target, self.successor_release, now=UPDATED_NOW)
        self.assertTrue(changes, "an update from 2.3.1 to 2.4.0 must change at least one file")
        self.assertEqual(
            (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text(), state_before,
        )
        self.assertEqual(drift(self.target, self.successor_release), [])
        self.assertEqual(verify(self.target, self.successor_release), [])

    def test_the_new_amendment_command_is_installed_after_the_update(self):
        update(self.target, self.successor_release, now=UPDATED_NOW)
        self.assertTrue(
            (self.target / ".claude/commands/request-plan-amendment.md").exists(),
        )


class TestUpdatePathImplementingFullAmendmentRehearsal(_RealReleaseCase):
    """Section 4, scenario 2, continued into the full new sequence -- also
    covers items 2, 5, 6 (dependency closure), and 12 (legacy no-anchor
    conservative default) in one rehearsal."""

    WORK_ITEM_ID = "amend-me"

    def test_implementing_survives_update_then_amends_reconciles_and_resumes(self):
        # --- Drive to IMPLEMENTING under 2.3.1: CP1/CP2 complete, CP3 open. ---
        result = drive_synthetic_work_item_through_checkpoints(
            self.target, work_item_id=self.WORK_ITEM_ID,
            checkpoint_ids=("CP1", "CP2", "CP3"), complete_checkpoint_ids=("CP1", "CP2"),
            now=FIXED_NOW,
        )
        self.assertEqual(result["phase"], "IMPLEMENTING")
        state_before = (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text()

        # --- Update to the real, authored 2.4.0 release. ---
        update(self.target, self.successor_release, now=UPDATED_NOW)
        self.assertEqual(
            (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text(), state_before,
        )
        self.assertEqual(drift(self.target, self.successor_release), [])
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "update workflow to 2.4.0")

        scripts_dir = str(self.target / "scripts")
        self.assertTrue(
            _implementing_entry_reachable(self.target, self.WORK_ITEM_ID, result["base_commit"]),
            "the pre-existing plan approval must still be reachable immediately after update",
        )

        # --- /request-plan-amendment, for the first time on this updated repo. ---
        request_script = f"""
import sys
sys.path.insert(0, {scripts_dir!r})
import workflow_state as ws
from pathlib import Path
root = Path({str(self.target)!r})
def mutate(state):
    return ws.request_plan_amendment(
        state, {self.WORK_ITEM_ID!r}, "found a defect mid-implementation",
        repo_root=root, now={AMENDMENT_NOW!r},
    )
ws.state_transaction(root, mutate)
"""
        _run_installed(self.target, request_script)
        state = _state(self.target)
        entry = state["work_items"][self.WORK_ITEM_ID]
        self.assertEqual(entry["phase"], "AMENDING_PLAN")
        self.assertEqual(entry["plan_approval"]["status"], "SUPERSEDED")
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "request plan amendment")

        # --- /milestone-plan produces the amended plan/registry/mapping,
        # then /approve-review plan reconciles and re-approves. Exactly one
        # new checkpoint (CP4); CP1/CP2/CP3 keep their registry rows'
        # meaning but the pre-amendment plan text (2.3.1's own un-anchored
        # `render_registry_markdown` output) carries zero `<!-- CPn -->`
        # anchors at all -- the exact legacy shape a repository migrated
        # from 2.3.1 has -- so every shared id is conservatively flipped
        # (item 12/B4-new.1), never silently treated as unchanged.
        reapprove_script = f"""
import json
import sys
sys.path.insert(0, {scripts_dir!r})
import workflow_fingerprint as fingerprint
import workflow_state as ws
from pathlib import Path

root = Path({str(self.target)!r})
work_item_id = {self.WORK_ITEM_ID!r}
state = json.loads((root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())
work_item = state["work_items"][work_item_id]
entry = work_item["amendment_history"][-1]

pre_plan_text, pre_registry = ws.load_pre_amendment_snapshot(
    root, work_item_id, work_item["plan_path"], work_item["registry_path"], entry,
)
assert "<!--" not in pre_plan_text, "the pre-amendment plan text must be the legacy un-anchored shape"

post_checkpoints = [
    {{"id": "CP1", "name": "synthetic checkpoint CP1", "depends_on": [],
      "complexity": 1, "session_target": 1}},
    {{"id": "CP2", "name": "synthetic checkpoint CP2, revised", "depends_on": ["CP1"],
      "complexity": 1, "session_target": 1}},
    {{"id": "CP3", "name": "synthetic checkpoint CP3", "depends_on": ["CP2"],
      "complexity": 1, "session_target": 1}},
    {{"id": "CP4", "name": "synthetic checkpoint CP4, new", "depends_on": ["CP3"],
      "complexity": 1, "session_target": 1}},
]
post_registry = ws.generate_registry(work_item_id, work_item["plan_revision"] + 1, post_checkpoints)
requirements = {{
    f"R{{i + 1}}": {{"description": f"amended requirement for {{c['id']}}", "checkpoint_ids": [c["id"]]}}
    for i, c in enumerate(post_checkpoints)
}}
post_mapping = ws.generate_mapping(work_item_id, requirements, registry=post_registry)
ws.write_registry_and_mapping(
    root, Path(work_item["registry_path"]), Path(work_item["mapping_path"]), post_registry, post_mapping,
)

post_plan_text = (
    f"# {{work_item_id}} plan (Revision {{work_item['plan_revision'] + 1}})\\n\\n"
    "Amended: found a defect mid-implementation.\\n\\n"
    "<!-- CP1 -->Checkpoint 1, unchanged in substance.<!-- /CP1 -->\\n\\n"
    "<!-- CP2 -->Checkpoint 2, revised design.<!-- /CP2 -->\\n\\n"
    "<!-- CP3 -->Checkpoint 3, unchanged in substance.<!-- /CP3 -->\\n\\n"
    "<!-- CP4 -->Checkpoint 4, newly added by this amendment.<!-- /CP4 -->\\n"
    + ws.render_registry_markdown(post_registry) + "\\n"
)
(root / work_item["plan_path"]).write_text(post_plan_text)

declarations = ws.generate_artifacts_declarations(
    work_item_id, work_item["plan_path"], work_item["registry_path"], work_item["mapping_path"],
    work_item_type=work_item["work_item_type"],
)
artifacts_path = str(fingerprint.artifacts_path_for_work_item(work_item_id))
(root / artifacts_path).write_text(json.dumps(declarations, indent=2) + "\\n")

def _publish(state):
    return ws.publish_plan_revision(state, work_item_id, work_item["plan_revision"] + 1, {AMENDMENT_NOW!r})
ws.state_transaction(root, _publish)

review_content_id, projection = fingerprint.compute_review_content_id_plan_stage_for_work_item(
    root, work_item_id,
)
record = ws.build_approval_record(
    basis="EXTERNAL_APPROVE", stage="plan", user_confirmation=f"plan {{work_item_id}}",
    now={REAPPROVAL_NOW!r}, reviewed_bundle_id=f"synthetic-amendment-{{work_item_id}}",
    approved_review_content_id=review_content_id,
    review_content_manifest=projection["review_content_manifest"],
)

def _approve(state):
    return ws.apply_plan_approval(
        state, work_item_id, record, {REAPPROVAL_NOW!r},
        pre_registry=pre_registry, pre_plan_text=pre_plan_text,
        post_registry=post_registry, post_plan_text=post_plan_text,
    )
ws.state_transaction(root, _approve)
print(review_content_id)
"""
        stdout = _run_installed(self.target, reapprove_script)
        review_content_id = stdout.strip().splitlines()[-1]
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m",
             f"approve plan\n\nWorkflow-Plan-Approval: {review_content_id}\n"
             f"Workflow-Work-Item: {self.WORK_ITEM_ID}")

        state = _state(self.target)
        entry = state["work_items"][self.WORK_ITEM_ID]
        self.assertEqual(entry["phase"], "IMPLEMENTING")
        self.assertEqual(entry["amendment_history"][-1]["resolved_at_plan_revision"], entry["plan_revision"])
        # Item 12/B4-new.1: the legacy no-anchor pre side conservatively
        # flips both previously-COMPLETE checkpoints.
        self.assertEqual(entry["checkpoints"]["CP1"]["status"], "NEEDS_REVALIDATION")
        self.assertEqual(entry["checkpoints"]["CP2"]["status"], "NEEDS_REVALIDATION")
        # CP3 was never started and CP4 is brand new -- neither is in the
        # live checkpoints map yet.
        self.assertNotIn("CP3", entry["checkpoints"])
        self.assertNotIn("CP4", entry["checkpoints"])

        # Item 5: implementing_entry_reachable holds immediately after the
        # amended plan's approval, against the item's own unchanged
        # base_commit.
        self.assertTrue(
            _implementing_entry_reachable(self.target, self.WORK_ITEM_ID, result["base_commit"]),
        )

        # --- Resume implementation: drive every remaining/revalidated
        # checkpoint to COMPLETE, reaching SELF_REVIEWING_IMPLEMENTATION. ---
        registry = json.loads((self.target / entry["registry_path"]).read_text())
        for checkpoint_id in ("CP1", "CP2", "CP3", "CP4"):
            resume_script = f"""
import sys
sys.path.insert(0, {scripts_dir!r})
import json
import subprocess
import workflow_state as ws
from pathlib import Path

root = Path({str(self.target)!r})
work_item_id = {self.WORK_ITEM_ID!r}
checkpoint_id = {checkpoint_id!r}
registry = json.loads(Path({str((self.target / entry["registry_path"]))!r}).read_text())
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

def _in_progress(state):
    return ws.transition_checkpoint_in_progress(state, work_item_id, checkpoint_id, head, {AMENDMENT_NOW!r})
ws.state_transaction(root, _in_progress)

deliverable = root / "scripts" / f"{{work_item_id}}-{{checkpoint_id}}-resumed.txt"
deliverable.write_text("resumed after amendment\\n")

def _complete(state):
    return ws.complete_checkpoint(state, work_item_id, checkpoint_id, registry, {AMENDMENT_NOW!r}, repo_root=root)
ws.state_transaction(root, _complete)
"""
            _run_installed(self.target, resume_script)
            _git(self.target, "add", "-A")
            _git(self.target, "commit", "-q", "-m",
                 f"feat({self.WORK_ITEM_ID}): {checkpoint_id} (resumed after amendment)\n\n"
                 f"Workflow-Checkpoint: {checkpoint_id}\nWorkflow-Work-Item: {self.WORK_ITEM_ID}")

        final_state = _state(self.target)
        final_entry = final_state["work_items"][self.WORK_ITEM_ID]
        self.assertEqual(final_entry["phase"], "SELF_REVIEWING_IMPLEMENTATION")
        for checkpoint_id in ("CP1", "CP2", "CP3", "CP4"):
            self.assertEqual(final_entry["checkpoints"][checkpoint_id]["status"], "COMPLETE")


class TestUpdatePathSelfReviewingImplementation(_RealReleaseCase):
    """Section 4, scenario 3: every checkpoint already complete -- the
    exact shape of the real Controller's own blocker -- updated, then a
    bare `/request-plan-amendment`."""

    WORK_ITEM_ID = "amend-me-sri"

    def test_self_reviewing_implementation_survives_update_then_amends(self):
        result = drive_synthetic_work_item_through_checkpoints(
            self.target, work_item_id=self.WORK_ITEM_ID,
            checkpoint_ids=("CP1", "CP2"), complete_checkpoint_ids=("CP1", "CP2"),
            now=FIXED_NOW,
        )
        self.assertEqual(result["phase"], "SELF_REVIEWING_IMPLEMENTATION")
        state_before = (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text()

        update(self.target, self.successor_release, now=UPDATED_NOW)
        self.assertEqual(
            (self.target / "docs/ai-workflow/WORKFLOW_STATE.json").read_text(), state_before,
        )
        self.assertEqual(drift(self.target, self.successor_release), [])
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "update workflow to 2.4.0")

        scripts_dir = str(self.target / "scripts")
        request_script = f"""
import sys
sys.path.insert(0, {scripts_dir!r})
import workflow_state as ws
from pathlib import Path
root = Path({str(self.target)!r})
def mutate(state):
    return ws.request_plan_amendment(
        state, {self.WORK_ITEM_ID!r}, "one more change before technical approval",
        repo_root=root, now={AMENDMENT_NOW!r},
    )
ws.state_transaction(root, mutate)
"""
        _run_installed(self.target, request_script)
        entry = _state(self.target)["work_items"][self.WORK_ITEM_ID]
        self.assertEqual(entry["phase"], "AMENDING_PLAN")
        self.assertEqual(entry["plan_approval"]["status"], "SUPERSEDED")
        self.assertEqual(entry["amendment_history"][-1]["requested_from_phase"],
                         "SELF_REVIEWING_IMPLEMENTATION")


class TestMigrateDoesNotDeleteASiblingAuthoredRelease(unittest.TestCase):
    """Section 4, item 8 (B1): an ordinary `python3 tools/migrate.py`
    regeneration is scoped to its own release directory alone -- it must
    neither delete nor report as `extra:` a sibling authored release."""

    def test_migrate_check_still_passes_with_2_4_0_present(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "migrate.py"), "--check"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_fresh_regeneration_leaves_authored_siblings_untouched(self):
        # O6: `2.5.0` is now a second authored sibling in the same
        # `distribution/`, alongside `2.4.0` -- both must survive an
        # ordinary `tools/migrate.py` regeneration of `2.3.1` untouched.
        successor_dirs = [
            REPO_ROOT / "distribution" / "workflow" / "2.4.0",
            REPO_ROOT / "distribution" / "workflow" / "2.5.0",
        ]
        before_bytes_by_dir = {
            successor_dir: (successor_dir / "manifest.json").read_bytes()
            for successor_dir in successor_dirs
        }
        # `tools/migrate.py` (no `--check`) `shutil.rmtree`s the real,
        # tracked `distribution/workflow/2.3.1/` before rebuilding it in
        # place, against this developer's real working tree -- there is no
        # temporary-root override to redirect that at (OPUS-R145-003). The
        # restore below must therefore run on *every* exit from this point
        # on, including a failed `returncode` assertion: a migrate failure
        # after the `rmtree` (a partial write, a disk error, a
        # `classification.json` mid-edit) must never leave the real
        # `2.3.1/` deleted or partial with no restore at all -- which is
        # exactly what happened when the `returncode` assertion sat ahead
        # of this `try:` rather than inside it. This suite is in the full
        # inventory, so every gate run executes it -- `python3
        # tests/run_all.py`, the very command `CLAUDE.md` tells every
        # contributor to run *before changing anything* -- and in
        # `parallel.cli.FAST_ALIAS_SELECTION`, so the deprecated `--fast`
        # alias runs it too, i.e. precisely when
        # `tools/migrate.py`/`migration/classification.json` are most likely
        # to be mid-edit and this failure mode most likely to fire.
        try:
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "tools" / "migrate.py")],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            for successor_dir, before_bytes in before_bytes_by_dir.items():
                self.assertTrue(successor_dir.exists(), "the sibling authored release must survive")
                self.assertEqual((successor_dir / "manifest.json").read_bytes(), before_bytes)
        finally:
            # Never leave the real repository's tracked distribution/
            # tree modified by this test -- restore it via git regardless
            # of outcome. `checkout --` alone restores tracked paths only;
            # a divergent regeneration could also have left a stray
            # untracked file behind (a renamed/added path under the same
            # directory), so `clean -fd` removes anything `checkout --`
            # itself cannot touch, scoped to this one directory alone.
            #
            # IMPL2-O3: each restore step is independent and must run even
            # if the other one fails -- `check=True` on the first call
            # would raise *inside* `finally:` the moment `checkout --`
            # itself failed, skipping `clean -fd` entirely and replacing
            # whatever exception was already propagating with an unrelated
            # `CalledProcessError`, losing the original diagnostic. Neither
            # call uses `check=True` here; both always run, and any
            # restore failure is asserted (and so still reported) only
            # after both have been attempted.
            restore_failures = []
            for restore_args in (
                ["git", "-C", str(REPO_ROOT), "checkout", "--", "distribution/workflow/2.3.1"],
                ["git", "-C", str(REPO_ROOT), "clean", "-fd", "--", "distribution/workflow/2.3.1"],
            ):
                result = subprocess.run(restore_args, capture_output=True, text=True)
                if result.returncode != 0:
                    restore_failures.append((restore_args, result.stdout + result.stderr))
            assert not restore_failures, (
                f"restoring distribution/workflow/2.3.1 failed: {restore_failures}"
            )


class TestReleaseCliAgainstTheAuthoredManifest(unittest.TestCase):
    """Section 4, item 10: Release/cli/install against the authored 2.4.0
    manifest -- no `KeyError`, and `provenance`/`upstream` both read back
    correctly."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir(parents=True)
        _git(self.target, "init", "-q", "-b", "main")
        _git(self.target, "config", "user.email", "cp8@example.invalid")
        _git(self.target, "config", "user.name", "CP8 Update Path")
        _git(self.target, "config", "commit.gpgsign", "false")

    def _cli(self, *args, release_version=None):
        argv = [sys.executable, "-m", "workflow_manager"]
        if release_version is not None:
            argv += ["--release-version", release_version]
        argv += list(args)
        return subprocess.run(
            argv, cwd=str(REPO_ROOT), capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin",
                 "HOME": str(Path.home())},
        )

    def test_release_provenance_and_upstream_read_correctly(self):
        release = find_release(REPO_ROOT, "2.4.0")
        self.assertEqual(release.provenance["origin"], "authored")
        self.assertEqual(release.provenance["base_release"], "2.3.1")
        self.assertEqual(release.upstream["tag"], "workflow-v2.3.1")

    def test_cli_releases_lists_both_the_upstream_and_the_authored_release(self):
        proc = self._cli("releases")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("2.3.1", proc.stdout)
        self.assertIn("2.4.0", proc.stdout)

    def test_bootstrap_status_and_update_all_work_against_2_4_0_explicitly(self):
        bootstrapped = self._cli("bootstrap", str(self.target), release_version="2.4.0")
        self.assertEqual(bootstrapped.returncode, 0, bootstrapped.stderr)
        self.assertIn("bootstrapped workflow 2.4.0", bootstrapped.stdout)

        status = self._cli("status", str(self.target))
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("2.4.0", status.stdout)

        updated = self._cli("update", str(self.target), release_version="2.4.0")
        self.assertEqual(updated.returncode, 0, updated.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
