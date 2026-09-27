#!/usr/bin/env python3
"""CP8 (`workflow-review-artifact-and-concurrency-hardening`): disposable-
repository and linked-worktree acceptance for the authored `2.6.0` release
-- `docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`
section 7, CP8, scenarios 1-9 plus the closed-defect census.

Every scenario runs against a real, disposable Git repository under a temp
directory, installed by the real installer (`workflow_manager.install.
bootstrap`/`update`) from the real composed releases this repository ships
-- never a synthetic release, and never a real managed repository.

**The installed scripts, in subprocesses.** Nothing in this module imports a
release's `workflow_state`/`workflow_fingerprint` in-process: two releases'
modules must never share one Python module cache (`fixture.py`'s own
discipline), and a scenario that updates `2.5.1` to `2.6.0` mid-test would
otherwise keep running the old bytes. Each step instead runs `drive()`: a
`python3 -c` subprocess whose `sys.path` starts with *that checkout's own*
`scripts/` directory. A linked worktree on a branch that has not merged the
update therefore runs its own installed `2.5.1` scripts, exactly as a second
Claude Code session there would.

**The command-shaped drivers** (plan section 7, CP8, "Tooling scope"). The
drivers are the installed release's own acceptance-matrix harness
(`scripts/workflow_acceptance_matrix_test.py`'s `Scratch`/`Item`, part of
the `full` install profile), pointed at the installed repository. That
harness is the release's own executable account of each
`.claude/commands/*.md` step -- the `2.6.0` copy drives `/approve-review
plan` through its journal, reservation, closure proof and witness advance
(CP4-CP6) -- so no second, private reimplementation of a command exists
here. What this module adds on top lives in `_PRELUDE`, `_COMMAND_HELPERS`
and `_WORKFLOW_251_HELPERS`: `Item` re-pointed at a caller-chosen work-item
id; review feedback written the way `/review-plan` writes it, through the
release's own guard and resolver (the `2.6.0` harness's `feedback_dir()`
asserts the scoped layout, which a legacy item must not have); the
command steps the harness does not wrap (`/record-manual-plan-review`,
`/apply-plan-review`'s entry); and a `2.5.1` checkout's own amendment
request and resolution, which its harness predates.
`src/workflow_manager/fixture.py` is unchanged: its one driver,
`drive_synthetic_work_item_through_checkpoints`, drives the `2.3.1`/`2.4.0`
items scenario 4 needs. (It cannot drive a `2.6.0` target -- its publish
passes no `review_content_id`, which `2.6.0` requires -- and nothing here
asks it to.)

Slow: every class installs at least one release and drives full review
lifecycles through it. Run directly:

    python3 tests/test_workflow_2_6_0_hardening_disposable_repo.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from support import REPO_ROOT

from workflow_manager.fixture import drive_synthetic_work_item_through_checkpoints
from workflow_manager.install import bootstrap, drift, update
from workflow_manager.installation import Installation
from workflow_manager.release import find_release

FIXED_NOW = "2026-01-01T00:00:00Z"
UPDATED_NOW = "2026-02-01T00:00:00Z"

STATE_PATH = "docs/ai-workflow/WORKFLOW_STATE.json"
RESULT_MARKER = "@@CP8-RESULT@@ "

#: Defined in every `drive()` subprocess, ahead of the caller's body. Names
#: only what both the installed `2.5.1` and `2.6.0` harnesses provide; a
#: helper that needs a `2.6.0`-only entry point resolves it when called, so
#: the prelude itself imports cleanly under either release.
_PRELUDE = '''
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, {scripts!r})
import workflow_fingerprint as fingerprint
import workflow_state as ws
import workflow_acceptance_matrix_test as matrix

root = Path({root!r})
# `Scratch.attach` is 2.6.0-only; the same view, built by hand, works for
# the installed 2.5.1 harness too.
scratch = matrix.Scratch.__new__(matrix.Scratch)
scratch.root = root
scratch._worktrees = []
CLOCK = {clock!r}
RESULT = {{}}


def new_item(wid, wtype="process"):
    """A `matrix.Item` for work item `wid`, created in this checkout at
    `HEAD`. The harness's fixed profile ids are replaced, so several items
    can coexist in one repository."""
    item = matrix.Item(scratch, wtype)
    item.wid = wid
    item.plan_path = f"docs/ai-workflow/{{wid}}-plan.md"
    item.registry_path = f"docs/ai-workflow/registry/{{wid}}-registry.json"
    item.mapping_path = f"docs/ai-workflow/requirements/{{wid}}-mapping.json"
    item.artifacts_path = f"docs/ai-workflow/registry/{{wid}}-artifacts.json"
    item.deliverable = (f"scripts/{{wid}}_feature.py" if wtype == "process"
                        else f"app/src/main/kotlin/{{wid}}.kt")
    item.base_commit = scratch.head()
    item._clock = CLOCK
    harness_feedback_dir = item.feedback_dir

    def feedback_dir():
        # The 2.6.0 harness's `feedback_dir()` asserts the scoped layout,
        # which an item created before the update must not have: a legacy
        # item takes the production resolver, unasserted.
        if (hasattr(fingerprint, "resolve_feedback_layout")
                and fingerprint.resolve_feedback_layout(root, item.wid) != "scoped"):
            return root / fingerprint.ensure_feedback_dir(root, item.wid)
        return harness_feedback_dir()
    item.feedback_dir = feedback_dir
    return item


def attach_item(wid, wtype="process"):
    """The same work item seen from this checkout, `base_commit` read back
    from this checkout's own state."""
    item = new_item(wid, wtype)
    item.base_commit = item.entry()["base_commit"]
    return item


def feedback_text(item, status, *, role=None, bundle_id=None, work_item=None):
    lines = ["# Review Decision", "", f"Status: {{status}}", "",
             f"Reviewed bundle ID: {{bundle_id or item.bundle_id()}}",
             f"Reviewed base commit: {{item.base_commit}}",
             f"Work item: {{work_item or item.wid}}"]
    if role:
        lines.append(f"Reviewer role: {{role}}")
    return "\\n".join(lines + ["", ""])


def review_plan_write(item, status="APPROVE"):
    """`/review-plan` step 8's write on a `2.6.0` checkout: the ownership
    guard with `state=`, `ensure_feedback_dir`, then the write at the
    resolved path. Returns that path, repo-root-relative."""
    rel = fingerprint.resolve_feedback_dir(root, item.wid)
    path = root / rel / "REVIEW_FEEDBACK.md"
    existing = path.read_text() if path.is_file() else None
    fingerprint.assert_feedback_not_owned_by_other_work_item(
        existing, work_item_id=item.wid, state=item.state(),
    )
    rel = fingerprint.ensure_feedback_dir(root, item.wid)
    path = root / rel / "REVIEW_FEEDBACK.md"
    path.write_text(feedback_text(item, status, role="LOCAL_MODEL_PLAN_REVIEW"))
    return (rel / "REVIEW_FEEDBACK.md").as_posix()


def feedback_cli(wid):
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "workflow_fingerprint.py"),
         "--resolve-feedback-path", wid],
        cwd=str(root), capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def raised(fn, *args, **kwargs):
    """The raised exception's class name, or `None` when `fn` returned."""
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed silently
        return type(exc).__name__
    return None

'''


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=check, capture_output=True, text=True,
    ).stdout


def drive(checkout: Path, body: str | tuple[str, ...], *, clock: int = 0,
          scripts: Path | None = None, helpers: str = "") -> dict:
    """Run `body` (after `_PRELUDE`) in a subprocess against `checkout`, with
    `checkout`'s own installed `scripts/` first on `sys.path` (or `scripts`,
    for a control arm run against another release's bytes). Returns the
    body's `RESULT` dict. `helpers` (module-level source, like
    `_COMMAND_HELPERS`) is inserted between the prelude and the
    body. A tuple `body` is a sequence of fragments, each dedented on its
    own. A failing body fails the test with its full output."""
    if isinstance(body, str):
        body = (body,)
    scripts = scripts or checkout / "scripts"
    source = (_PRELUDE.format(scripts=str(scripts), root=str(checkout), clock=clock)
              + textwrap.dedent(helpers) + "\n"
              + "\n".join(textwrap.dedent(fragment) for fragment in body)
              + f"\nprint({RESULT_MARKER!r} + json.dumps(RESULT, sort_keys=True))\n")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHON_COLORS"] = "0"
    proc = subprocess.run(
        [sys.executable, "-c", source], cwd=str(checkout), capture_output=True, text=True,
        env=env, timeout=900,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"driver failed in {checkout} ({scripts}):\n--- stdout ---\n{proc.stdout[-6000:]}"
            f"\n--- stderr ---\n{proc.stderr[-6000:]}"
        )
    line = next(l for l in reversed(proc.stdout.splitlines()) if l.startswith(RESULT_MARKER))
    return json.loads(line[len(RESULT_MARKER):])


class _InstalledRepoCase(unittest.TestCase):
    """One disposable repository per test, bootstrapped from `BASE_VERSION`
    and committed."""

    BASE_VERSION = "2.6.0"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="wf-cp8-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "cp8@example.invalid")
        _git(self.root, "config", "user.name", "CP8 Hardening")
        _git(self.root, "config", "commit.gpgsign", "false")
        bootstrap(self.root, find_release(REPO_ROOT, self.BASE_VERSION), now=FIXED_NOW)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", f"bootstrap workflow {self.BASE_VERSION}")
        self._clock = 0

    def clock(self) -> int:
        """A fresh, strictly later starting second for the next driver, so
        timestamps never run backwards across subprocesses. The harness
        renders its clock as a time of day on one date, so the steps stay
        well inside 24 hours."""
        self._clock += 2_000
        return self._clock

    def drive(self, body: str | tuple[str, ...], checkout: Path | None = None, **kwargs) -> dict:
        return drive(checkout or self.root, body, clock=self.clock(), **kwargs)

    def update_to(self, version: str, checkout: Path | None = None) -> list[str]:
        """`workflow_manager update`, then the update committed on its own:
        exactly the paths the installer owns (every managed path before or
        after, the installation record, the two merged files), never a
        live item's in-flight state or plan files. The working-tree
        `WORKFLOW_STATE.json` must be byte-identical across the update
        (INV-7: no update rewrites committed state)."""
        checkout = checkout or self.root
        release = find_release(REPO_ROOT, version)
        before = Installation.read(checkout)
        state_before = (checkout / STATE_PATH).read_bytes()
        _, changes = update(checkout, release, now=UPDATED_NOW)
        self.assertEqual((checkout / STATE_PATH).read_bytes(), state_before)
        self.assertEqual(drift(checkout, release), [])
        after = Installation.read(checkout)
        owned = sorted(set(before.managed) | set(after.managed)
                       | {".workflow-manager/installation.json", ".gitignore", "CLAUDE.md"})
        _git(checkout, "add", "-A", "--", *owned)
        _git(checkout, "commit", "-q", "-m", f"update workflow to {version}")
        return changes

    def add_worktree(self, name: str, at: str = "HEAD") -> Path:
        """A linked worktree of the disposable repository on a new branch
        `name` at `at` -- a second Claude Code session's checkout."""
        path = self.root.parent / name
        _git(self.root, "worktree", "add", "-q", "-b", name, str(path), at)
        return path

    def state(self, checkout: Path | None = None) -> dict:
        return json.loads(((checkout or self.root) / STATE_PATH).read_text())

    def installed_version(self, checkout: Path | None = None) -> str:
        record = (checkout or self.root) / ".workflow-manager" / "installation.json"
        return json.loads(record.read_text())["workflow_version"]


# ===========================================================================
# Scenario 1 -- a fresh 2.6.0 work item: scoped feedback, no collision
# ===========================================================================


class TestScenario1FreshItemsUseScopedFeedback(_InstalledRepoCase):
    """REQ-1/REQ-2: two concurrent items created under `2.6.0` each write
    local plan-review feedback at their own scoped path, never the shared
    flat one, and `--resolve-feedback-path` prints what the resolver
    resolves."""

    def test_two_concurrent_items_write_scoped_feedback_without_colliding(self):
        result = self.drive("""
            items = [new_item("item-a"), new_item("item-b")]
            for item in items:
                item.milestone_plan()
                item.generate_plan_bundle()
            RESULT["written"] = {item.wid: review_plan_write(item) for item in items}
            RESULT["cli"] = {item.wid: feedback_cli(item.wid) for item in items}
            RESULT["contract"] = {
                item.wid: fingerprint.resolve_feedback_path_contract(root, item.wid) for item in items
            }
            RESULT["layout_field"] = {
                item.wid: item.entry().get("feedback_layout") for item in items
            }
            for item in items:
                item.record_plan_reviews()
            # Item A's approval commit moves HEAD under item B's bundle; B
            # stays at its own review gate, its feedback untouched.
            items[0].approve_plan()
            RESULT["phases"] = {item.wid: item.entry()["phase"] for item in items}
            RESULT["owners"] = {
                item.wid: fingerprint.parse_review_feedback_binding_fields(
                    (root / RESULT["written"][item.wid]).read_text())["work_item"]
                for item in items
            }
        """)
        for wid in ("item-a", "item-b"):
            scoped = f".ai-review/{wid}/feedback/REVIEW_FEEDBACK.md"
            self.assertEqual(result["written"][wid], scoped)
            self.assertEqual(result["layout_field"][wid], "scoped")
            self.assertEqual(result["owners"][wid], wid)
            self.assertEqual(result["cli"][wid], result["contract"][wid])
            self.assertEqual(result["cli"][wid], {
                "work_item_id": wid, "layout": "scoped",
                "feedback_dir": f".ai-review/{wid}/feedback",
                "review_feedback_path": scoped,
                "functional_review_path": f".ai-review/{wid}/feedback/FUNCTIONAL_REVIEW.md",
            })
        self.assertEqual(result["phases"], {
            "item-a": "IMPLEMENTING", "item-b": "AWAITING_PLAN_APPROVAL"})
        self.assertFalse((self.root / ".ai-review" / "feedback").exists(),
                         "no 2.6.0 item may write the shared flat feedback directory")


# ===========================================================================
# Scenario 2 -- a completed 2.5.1 item's flat feedback survives the update
# ===========================================================================


class TestScenario2CompletedLegacyItemFlatFeedbackIsUntouched(_InstalledRepoCase):
    """REQ-1/REQ-2: item A runs to `MILESTONE_COMPLETE` under the installed
    `2.5.1`, leaving the shared flat `REVIEW_FEEDBACK.md` naming itself. After
    the update to `2.6.0`, new item B's local plan-review write lands at its
    scoped path and A's file is byte-for-byte untouched."""

    BASE_VERSION = "2.5.1"

    def test_new_item_writes_scoped_and_leaves_the_legacy_flat_file_alone(self):
        self.drive("""
            a = new_item("item-a")
            a.milestone_plan()
            a.generate_plan_bundle()
            a.write_feedback("APPROVE")
            a.record_plan_reviews()
            a.approve_plan()
            a.implement_checkpoint("CP1", {a.deliverable: "# item-a\\n"})
            a.generate_impl_bundle("implementation", expect_outcome="ordinary")
            a.write_feedback("APPROVE")
            a.approve_implementation()
            a.prepare_functional_review()
            a.accept_milestone()
            RESULT["phase"] = a.entry()["phase"]
        """)
        flat = self.root / ".ai-review" / "feedback" / "REVIEW_FEEDBACK.md"
        self.assertTrue(flat.is_file(), "a 2.5.1 item with no scoped feedback dir writes flat")
        flat_before = flat.read_bytes()
        self.assertIn(b"Work item: item-a", flat_before)
        self.assertEqual(self.state()["work_items"]["item-a"]["phase"], "MILESTONE_COMPLETE")

        self.update_to("2.6.0")
        result = self.drive("""
            b = new_item("item-b")
            b.milestone_plan()
            b.generate_plan_bundle()
            RESULT["written"] = review_plan_write(b)
            b.record_plan_reviews()
            RESULT["phase_b"] = b.entry()["phase"]
            RESULT["layouts"] = {
                wid: fingerprint.resolve_feedback_layout(root, wid) for wid in ("item-a", "item-b")
            }
        """)
        self.assertEqual(result["written"], ".ai-review/item-b/feedback/REVIEW_FEEDBACK.md")
        self.assertEqual(result["layouts"], {"item-a": "legacy-flat", "item-b": "scoped"})
        self.assertEqual(result["phase_b"], "AWAITING_PLAN_APPROVAL")
        self.assertEqual(flat.read_bytes(), flat_before)


# ===========================================================================
# Scenario 3 -- an active legacy item mid manual plan review is updated
# ===========================================================================


#: Command-step helpers for a `2.6.0` checkout, passed to `drive()` as
#: `helpers=`. Each follows its command file's steps in order, calling the
#: exact entry points the command names.
_COMMAND_HELPERS = '''
def record_manual_plan_review(item, round=1):
    """`/record-manual-plan-review` steps 4-7, for the verdict pasted at
    the item's resolved feedback path."""
    rel = fingerprint.resolve_feedback_dir(root, item.wid) / "REVIEW_FEEDBACK.md"
    content = (root / rel).read_text()
    fingerprint.assert_manual_feedback_names_work_item(content, work_item_id=item.wid)
    current, _ = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, item.wid)
    fingerprint.assert_bundle_not_rejected(root, item.wid)
    advisory = ws.assert_plan_review_bundle_bound(root, item.wid)
    fields = fingerprint.parse_review_feedback_binding_fields(content)
    stated = fingerprint.parse_feedback_review_content_id(content)
    ws.validate_manual_plan_review_preconditions(
        item.entry(), current_review_content_id=current,
        feedback_role="MANUAL_EXTERNAL_PLAN_REVIEW", feedback_review_content_id=stated,
    )
    fingerprint.assert_bundle_not_rejected(root, item.wid)
    item.tx(lambda state: ws.record_manual_plan_review(
        state, item.wid, verdict=fields["status"], bundle_id=fields["reviewed_bundle_id"],
        round=round, now=item.now(), current_review_content_id=current,
        feedback_role="MANUAL_EXTERNAL_PLAN_REVIEW", feedback_review_content_id=stated,
    ))
    return {"feedback_path": rel.as_posix(), "advisory": advisory,
            "phase": item.entry()["phase"]}


def review_plan_revise(item, round=1):
    """`/review-plan` with a `REVISE` verdict: the bound-bundle reader, the
    feedback write, then the ledger-less `REVISE` transition, which writes
    the `CONSUMED` record."""
    ws.validate_local_plan_review_preconditions_bound(root, item.entry())
    written = review_plan_write(item, "REVISE")
    digest, _ = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, item.wid)
    item.tx(lambda state: ws.record_local_plan_review(
        state, item.wid, verdict="REVISE", bundle_id=item.bundle_id(),
        review_content_id=digest, round=round, now=item.now(),
    ))
    return written


def apply_plan_review_entry(item):
    """`/apply-plan-review`'s [2.1] entry and step 1's acceptance rule, on
    the feedback at the item's resolved path. The caller then runs step 5
    (`item.apply_plan_review`: the edits and the publication) and step 5's
    single generation followed by step 7''s bind
    (`item.generate_plan_bundle`)."""
    ws.assert_plan_review_entry_phase(item.entry(), item.wid, command="/apply-plan-review")
    item.tx(lambda state: ws.ensure_plan_review_binding_marker(state, item.wid, item.now()))
    status = ws.plan_review_publication_status(root, item.state(), item.wid)["status"]
    rel = fingerprint.resolve_feedback_dir(root, item.wid) / "REVIEW_FEEDBACK.md"
    mode = ws.assert_apply_plan_review_feedback(
        item.entry(), item.wid, feedback_content=(root / rel).read_text(),
        publication_status=status,
    )
    return {"status": status, "feedback_path": rel.as_posix(), "mode": mode}


def chained(count, prefix="step"):
    """`count` chained checkpoints `CP1..CP<count>`, one requirement each."""
    checkpoints = [
        {"id": f"CP{i}", "name": f"{prefix} {i}", "depends_on": [f"CP{i - 1}"] if i > 1 else [],
         "complexity": "S", "session_target": 1}
        for i in range(1, count + 1)
    ]
    requirements = {f"R{i}": {"description": f"{prefix} {i}", "checkpoint_ids": [f"CP{i}"]}
                    for i in range(1, count + 1)}
    return checkpoints, requirements


def plan_to_implementing(item, checkpoints, requirements, implement=("CP1",)):
    """`/milestone-plan`, both plan reviews approving, `/approve-review
    plan`, then `/milestone-implement` for each checkpoint in `implement`.
    Runs on either installed release: a `2.6.0` checkout writes feedback
    the way `/review-plan` does, a `2.5.1` one through its own harness."""
    item.milestone_plan(checkpoints=checkpoints, requirements=requirements)
    item.generate_plan_bundle()
    if hasattr(fingerprint, "ensure_feedback_dir"):
        review_plan_write(item)
    else:
        item.write_feedback("APPROVE")
    item.record_plan_reviews()
    item.approve_plan()
    for checkpoint_id in implement:
        item.implement_checkpoint(checkpoint_id, {item.deliverable: f"# {checkpoint_id}\\n"})


def witness(item):
    return ws.read_amendment_witness(root, item.wid)
'''


class TestScenario3LegacyManualPlanReviewSurvivesTheUpdate(_InstalledRepoCase):
    """REQ-2/REQ-11 (section 6.1, rows 1 and 3): a `2.5.1` item waiting at
    `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, the reviewer's `REVISE` verdict
    already pasted into the shared flat file, is updated to `2.6.0`.
    `/record-manual-plan-review` and `/apply-plan-review` both still find
    that flat file, and the item proceeds through its next gate back to
    `AWAITING_LOCAL_PLAN_REVIEW`, bound."""

    BASE_VERSION = "2.5.1"

    def test_record_and_apply_find_the_flat_file_and_the_item_proceeds(self):
        self.drive("""
            item = new_item("legacy-item")
            item.milestone_plan()
            item.generate_plan_bundle()
            item.write_feedback("APPROVE", role="LOCAL_MODEL_PLAN_REVIEW")
            digest, _ = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, item.wid)
            item.tx(lambda state: ws.record_local_plan_review(
                state, item.wid, verdict="APPROVE", bundle_id=item.bundle_id(),
                review_content_id=digest, round=1, now=item.now(),
            ))
            # The manual reviewer's verdict, pasted and not yet recorded.
            item.write_feedback("REVISE", role="MANUAL_EXTERNAL_PLAN_REVIEW",
                                extra=f"review_content_id: {digest}\\n\\n## Important\\n\\n- Tighten CP1.\\n")
        """)
        entry = self.state()["work_items"]["legacy-item"]
        self.assertEqual(entry["phase"], "AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW")
        self.assertNotIn("feedback_layout", entry)
        self.assertNotIn("plan_review_binding", entry)
        flat = self.root / ".ai-review" / "feedback" / "REVIEW_FEEDBACK.md"
        self.assertIn(b"Status: REVISE", flat.read_bytes())
        committed_state = _git(self.root, "rev-parse", f"HEAD:{STATE_PATH}")

        self.update_to("2.6.0")
        self.assertEqual(_git(self.root, "rev-parse", f"HEAD:{STATE_PATH}"), committed_state)
        result = self.drive(helpers=_COMMAND_HELPERS, body="""
            item = attach_item("legacy-item")
            RESULT["layout"] = fingerprint.resolve_feedback_layout(root, item.wid)
            RESULT["record"] = record_manual_plan_review(item)
            RESULT["binding_after_record"] = item.entry().get("plan_review_binding", {}).get("status")
            RESULT["apply"] = apply_plan_review_entry(item)
            item.apply_plan_review(2, plan_body="Plan body, revised per the manual review.\\n")
            item.generate_plan_bundle()
            entry = item.entry()
            RESULT["after"] = {"phase": entry["phase"], "plan_revision": entry["plan_revision"],
                               "binding": entry["plan_review_binding"]["status"]}
        """)
        self.assertEqual(result["layout"], "legacy-flat")
        self.assertEqual(result["record"]["feedback_path"], ".ai-review/feedback/REVIEW_FEEDBACK.md")
        self.assertEqual(result["record"]["phase"], "REVISING_PLAN")
        self.assertEqual(result["binding_after_record"], "CONSUMED")
        self.assertEqual(result["apply"]["feedback_path"], ".ai-review/feedback/REVIEW_FEEDBACK.md")
        self.assertEqual(result["apply"]["status"], "NEEDS_EDIT")
        self.assertEqual(result["apply"]["mode"], "bundle")
        self.assertEqual(result["after"], {
            "phase": "AWAITING_LOCAL_PLAN_REVIEW", "plan_revision": 2, "binding": "BOUND"})


# ===========================================================================
# Scenario 4 -- 2.3.1/2.4.0 items, no local exclude, a committed update
# ===========================================================================


_DIGESTS = """
entry = json.loads((root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())["work_items"][WID]
try:
    RESULT["reachable"] = ws.implementing_entry_reachable(root, entry, entry["base_commit"])
except Exception as exc:  # noqa: BLE001
    RESULT["reachable"] = type(exc).__name__
RESULT["approved"] = entry["plan_approval"]["approved_review_content_id"]
try:
    RESULT["plan"] = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, WID)[0]
except Exception as exc:  # noqa: BLE001
    RESULT["plan"] = type(exc).__name__
try:
    classification = fingerprint.load_implementation_stage_classification(
        root, fingerprint.artifacts_path_for_work_item(WID))
    RESULT["implementation"] = fingerprint.compute_review_content_id_implementation_stage_at_commit(
        root, entry["base_commit"], "HEAD", entry["work_item_type"], WID, *classification)[0]
except Exception as exc:  # noqa: BLE001
    RESULT["implementation"] = type(exc).__name__
"""


class _Scenario4:
    """REQ-3 (section 6.1, row 2; `v2.4.0-001`): an item created under an
    older release whose generated declarations do not know
    `.workflow-manager/installation.json`, in a repository that tracks that
    record (no `.git/info/exclude` mitigation). The update to `2.6.0` is
    committed, so the record's change lands inside the item's own
    `base_commit..HEAD` interval. Under `2.6.0` the item stays reachable,
    its digests are unchanged, and a genuinely novel path still refuses.
    The control arm runs the base release's own bytes against the same
    committed history and shows the wedge `2.6.0` removes."""

    WID = "legacy-product"
    #: What the base release's own `implementing_entry_reachable` answers on
    #: the committed update. `2.4.0`'s generator already excluded
    #: `.workflow-manager/` at the plan stage (the forward-only `v2.4.0-001`
    #: repair), so only the implementation stage wedges there.
    CONTROL_REACHABLE: object = "UnclassifiedPathError"

    def _digests(self, scripts: Path | None = None) -> dict:
        return self.drive(f"WID = {self.WID!r}\n" + _DIGESTS, scripts=scripts)

    def test_committed_update_keeps_the_item_reachable_with_unchanged_digests(self):
        exclude = self.root / ".git" / "info" / "exclude"
        self.assertNotIn(".workflow-manager", exclude.read_text() if exclude.exists() else "")
        drive_synthetic_work_item_through_checkpoints(
            self.root, work_item_id=self.WID, work_item_type="product",
            checkpoint_ids=("CP1", "CP2"), now=FIXED_NOW,
        )
        _git(self.root, "ls-files", "--error-unmatch", ".workflow-manager/installation.json")
        pre = self._digests()
        self.assertIs(pre["reachable"], True)
        self.assertEqual(pre["plan"], pre["approved"])

        self.update_to("2.6.0")
        changed = _git(self.root, "diff", "--name-only", "HEAD~1", "HEAD").split()
        self.assertIn(".workflow-manager/installation.json", changed)

        post = self._digests()
        self.assertIs(post["reachable"], True)
        self.assertEqual(post["plan"], post["approved"])
        self.assertEqual(post["plan"], pre["plan"])
        self.assertEqual(post["implementation"], pre["implementation"])

        # Control arm: the base release's own bytes, same committed history.
        control = self._digests(
            scripts=REPO_ROOT / "distribution" / "workflow" / self.BASE_VERSION / "payload" / "scripts")
        self.assertEqual(control["reachable"], self.CONTROL_REACHABLE)
        self.assertEqual(control["implementation"], "UnclassifiedPathError")

        # A genuinely novel path is still refused: the fallback is exact-path.
        (self.root / "novel").mkdir()
        (self.root / "novel" / "unclassified.txt").write_text("not declared anywhere\n")
        _git(self.root, "add", "novel/unclassified.txt")
        _git(self.root, "commit", "-q", "-m", "a path no declaration classifies")
        novel = self._digests()
        self.assertEqual(novel["reachable"], "UnclassifiedPathError")
        self.assertEqual(novel["implementation"], "UnclassifiedPathError")


class TestScenario4From231(_Scenario4, _InstalledRepoCase):
    BASE_VERSION = "2.3.1"


class TestScenario4From240(_Scenario4, _InstalledRepoCase):
    BASE_VERSION = "2.4.0"
    CONTROL_REACHABLE = True


# ===========================================================================
# Scenario 5 -- plan-review remediation through both generation failures
# ===========================================================================


class TestScenario5RemediationSurvivesForcedGenerationFailures(_InstalledRepoCase):
    """REQ-4 (section 3.3's two variants, recovery table row 9): a local
    `REVISE`, then `/apply-plan-review` whose step-5 generation fails after
    the publish -- a stale `TEST_RESULTS.md` (variant 1: `2.5.1` withdrew
    the bundle) or a stale `REVIEW_REQUEST.md` (variant 2: `2.5.1` left a
    mixed bundle). Under `2.6.0` the item stays at its non-ready phase at
    row 9 with the previous `current/` byte-identical; the explicit-id
    re-run regenerates and binds, and the whole round advances the plan
    revision exactly once."""

    VARIANTS = {
        "stale_test_results": {"test_results": "stage: plan (revision 1)\nhead: HEAD\n\nstale\n"},
        "stale_review_request": {"review_request": f"# Review request\n\nreview_content_id: {'a' * 64}\n"},
    }

    def _round(self, variant: str) -> dict:
        return self.drive(helpers=_COMMAND_HELPERS, body=f"""
            import hashlib
            def tree_digest(path):
                h = hashlib.sha256()
                for p in sorted(path.rglob("*")):
                    if p.is_file():
                        h.update(p.relative_to(path).as_posix().encode() + b"\\0" + p.read_bytes())
                return h.hexdigest()

            item = new_item("remediated")
            item.milestone_plan()
            item.generate_plan_bundle()
            RESULT["first_revision"] = item.entry()["plan_revision"]
            RESULT["feedback"] = review_plan_revise(item)
            RESULT["after_revise"] = item.entry()["phase"]
            RESULT["entry"] = apply_plan_review_entry(item)
            current = root / fingerprint.resolve_bundle_dir(root, item.wid, stage="plan")
            before = tree_digest(current)
            item.apply_plan_review(2, plan_body="Plan body, revised.\\n")
            proc = item.generate_plan_bundle(check=False, **{self.VARIANTS[variant]!r})
            status = ws.plan_review_publication_status(root, item.state(), item.wid)
            RESULT["failed"] = {{
                "returncode": proc.returncode, "phase": item.entry()["phase"],
                "row": status["row"], "status": status["status"],
                "mirror": item.entry()["plan_revision"],
                "current_unchanged": tree_digest(current) == before,
                "rejected": (current.parent / "REJECTED").exists(),
                "staging_left": sorted(p.name for p in current.parent.glob("*staging-*")),
            }}
            RESULT["reader_refuses"] = raised(
                ws.validate_local_plan_review_preconditions_bound, root, item.entry())
            # The explicit-id re-run: row 9 resumes at step 5's generation,
            # then step 7''s bind -- never a second revision advance.
            item.generate_plan_bundle()
            entry = item.entry()
            RESULT["retried"] = {{
                "phase": entry["phase"], "mirror": entry["plan_revision"],
                "registry": item.registry()["plan_revision"],
                "binding": entry["plan_review_binding"]["status"],
                "reader": raised(ws.validate_local_plan_review_preconditions_bound, root, entry),
            }}
        """)

    def _assert_variant(self, variant: str):
        result = self._round(variant)
        self.assertEqual(result["first_revision"], 1)
        self.assertEqual(result["feedback"], ".ai-review/remediated/feedback/REVIEW_FEEDBACK.md")
        self.assertEqual(result["after_revise"], "REVISING_PLAN")
        self.assertEqual(result["entry"]["status"], "NEEDS_EDIT")
        failed = result["failed"]
        self.assertNotEqual(failed["returncode"], 0)
        self.assertEqual(failed["phase"], "REVISING_PLAN", "a failed generation never reads ready")
        self.assertEqual((failed["row"], failed["status"]), ("9", "PUBLISHED_UNBOUND"))
        self.assertEqual(failed["mirror"], 2)
        self.assertTrue(failed["current_unchanged"])
        self.assertFalse(failed["rejected"])
        self.assertEqual(failed["staging_left"], [])
        self.assertIsNotNone(result["reader_refuses"])
        self.assertEqual(result["retried"], {
            "phase": "AWAITING_LOCAL_PLAN_REVIEW", "mirror": 2, "registry": 2,
            "binding": "BOUND", "reader": None,
        })

    def test_variant_1_stale_test_results(self):
        self._assert_variant("stale_test_results")

    def test_variant_2_stale_review_request(self):
        self._assert_variant("stale_review_request")


# ===========================================================================
# Scenario 6 -- plan approval closes over a brand-new protected companion
# ===========================================================================


COMPANION = "docs/ai-workflow/closure-item-design.md"


class TestScenario6ApprovalClosesOverANewCompanion(_InstalledRepoCase):
    """REQ-5/REQ-6 (section 3.4): the item's declaration protects a
    companion document that exists only in the working tree. The approval
    commit contains it, the identity recomputed from that commit equals the
    approved one, and exactly one approval commit exists -- both in one
    session and when the session crashes right after the commit and a new
    process takes the transaction over and completes it."""

    PLAN = f"""
        item = new_item("closure-item")
        scratch.write({COMPANION!r}, "Companion design notes, brand new.\\n")
        declarations = ws.generate_artifacts_declarations(
            item.wid, item.plan_path, item.registry_path, item.mapping_path,
            work_item_type=item.wtype)
        declarations["plan_stage"]["protected_paths"].append({COMPANION!r})
        item.milestone_plan(artifacts=declarations)
        RESULT["companion_tracked"] = scratch.git(
            "ls-files", "--error-unmatch", {COMPANION!r}, check=False).returncode == 0
        item.generate_plan_bundle()
        review_plan_write(item)
        item.record_plan_reviews()
    """

    VERIFY = f"""
        item = attach_item("closure-item")
        entry = item.entry()
        approved = entry["plan_approval"]["approved_review_content_id"]
        commit = ws.discover_plan_approval_commit(root, item.wid, approved, item.base_commit, "HEAD")
        RESULT["verify"] = {{
            "phase": entry["phase"], "status": entry["plan_approval"]["status"],
            "companion_in_commit": {COMPANION!r} in scratch.git(
                "diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.split(),
            "companion_bytes": scratch.git("show", f"{{commit}}:{COMPANION}").stdout,
            "identity_equal": fingerprint.compute_review_content_id_plan_stage_at_commit_for_work_item(
                root, item.wid, commit, base=item.base_commit)[0] == approved,
            "approval_commits": sum(
                1 for body in scratch.git("log", "--format=%B%x00", "HEAD").stdout.split("\\0")
                if f"Workflow-Plan-Approval: {{approved}}" in body),
            "journal": ws.read_plan_approval_journal(root),
            "reachable": ws.implementing_entry_reachable(root, entry, item.base_commit),
            "clean": scratch.git("status", "--porcelain").stdout,
        }}
    """

    def _assert_closed(self, result: dict):
        verify = result["verify"]
        self.assertEqual((verify["phase"], verify["status"]), ("IMPLEMENTING", "CURRENT"))
        self.assertTrue(verify["companion_in_commit"])
        self.assertEqual(verify["companion_bytes"], "Companion design notes, brand new.\n")
        self.assertTrue(verify["identity_equal"])
        self.assertEqual(verify["approval_commits"], 1)
        self.assertIsNone(verify["journal"])
        self.assertTrue(verify["reachable"])
        self.assertEqual(verify["clean"], "")

    def test_in_session_approval(self):
        result = self.drive(helpers=_COMMAND_HELPERS, body=(self.PLAN, """
            item.approve_plan()
        """, self.VERIFY))
        self.assertFalse(result["companion_tracked"])
        self._assert_closed(result)

    def test_crash_after_commit_then_takeover_in_a_new_process(self):
        crashed = self.drive(helpers=_COMMAND_HELPERS, body=(self.PLAN, """
            RESULT["commit"] = item.approve_plan(stop_after="commit")
            RESULT["journal_open"] = ws.read_plan_approval_journal(root) is not None
        """))
        self.assertTrue(crashed["journal_open"])
        self.assertEqual(_git(self.root, "rev-parse", "HEAD").strip(), crashed["commit"])
        # A new session: the evidence, the user's literal, the takeover, then
        # steps 6a-6d from durable state alone.
        result = self.drive(("""
            item = attach_item("closure-item")
            evidence = ws.plan_approval_takeover_evidence(root)
            RESULT["outcome"] = evidence["outcome"]
            token = ws.take_over_plan_approval_transaction(
                root, work_item_id=item.wid, now=item.now(),
                user_authorization=ws.plan_approval_takeover_authorization_literal(evidence),
                evidence=evidence,
            )
            RESULT["completed"] = item.complete_plan_approval(token)
        """, self.VERIFY))
        self.assertEqual(result["outcome"], "COMMITTED")
        self.assertEqual(result["completed"], crashed["commit"])
        self._assert_closed(result)


# ===========================================================================
# Scenario 7 -- cross-worktree amendment/checkpoint contention
# ===========================================================================


class TestScenario7CrossWorktreeContentionOnAFreshInstall(_InstalledRepoCase):
    """REQ-7 (`v2.4.0-002`, INV-6): two linked worktrees of one `2.6.0`
    repository, both at `IMPLEMENTING` with `CP1` complete. In each order
    exactly one side proceeds and the other refuses without publishing
    anything; a worktree whose state predates a resolved amendment is
    refused until it merges the resolution."""

    WID = "contended"

    def test_both_orders_and_the_stale_state_case(self):
        self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = new_item({self.WID!r})
            plan_to_implementing(item, *chained(3))
        """)
        b = self.add_worktree("b")

        # Claim first (in b): the amendment in main refuses, naming b.
        claimed = self.drive(checkout=b, body=f"""
            item = attach_item({self.WID!r})
            RESULT["claim"] = ws.claim_checkpoint(root, item.wid, "CP2", now=item.now())["checkpoint_id"]
        """)
        self.assertEqual(claimed["claim"], "CP2")
        refused = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            try:
                item.request_amendment("contended")
            except ws.AmendmentCheckpointActiveError as exc:
                RESULT["error"], RESULT["detail"] = type(exc).__name__, str(exc)
            RESULT["phase"] = item.entry()["phase"]
            RESULT["witness"] = witness(item)["status"]
        """)
        self.assertEqual(refused["error"], "AmendmentCheckpointActiveError")
        self.assertIn(os.path.realpath(b), refused["detail"])
        self.assertEqual((refused["phase"], refused["witness"]), ("IMPLEMENTING", "NONE"))
        self.drive(checkout=b, body=f"""
            item = attach_item({self.WID!r})
            ws.release_checkpoint(root, item.wid, "CP2",
                                  owner_token=ws.resolve_claim(root, item.wid)["owner_token"],
                                  now=item.now())
        """)

        # Amendment first (in main): the claim in b refuses while b's own
        # state still says IMPLEMENTING, and publishes no claim.
        amended = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            item.request_amendment("the design changed", commit=True)
            RESULT["phase"] = item.entry()["phase"]
            RESULT["witness"] = [witness(item)["status"], witness(item)["amendment_seq"]]
        """)
        self.assertEqual((amended["phase"], amended["witness"]), ("AMENDING_PLAN", ["OPEN", 1]))
        refused = self.drive(checkout=b, body=f"""
            item = attach_item({self.WID!r})
            RESULT["local_phase"] = item.entry()["phase"]
            RESULT["error"] = raised(ws.claim_checkpoint, root, item.wid, "CP2", now=item.now())
            RESULT["claim"] = ws.resolve_claim(root, item.wid)
        """)
        self.assertEqual(refused, {"local_phase": "IMPLEMENTING", "error": "AmendmentInFlightError",
                                   "claim": None})

        # The amendment resolves in main; b, still on its pre-amendment
        # state, is stale until it merges the resolution.
        resolved = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            item.amend_plan(2, *chained(3, prefix="amended step"))
            item.generate_plan_bundle()
            review_plan_write(item)
            item.record_plan_reviews(round=2)
            item.approve_plan()
            RESULT["phase"] = item.entry()["phase"]
            RESULT["witness"] = witness(item)["status"]
        """)
        self.assertEqual((resolved["phase"], resolved["witness"]), ("IMPLEMENTING", "RESOLVED"))
        stale = self.drive(checkout=b, body=f"""
            item = attach_item({self.WID!r})
            try:
                ws.claim_checkpoint(root, item.wid, "CP2", now=item.now())
            except ws.StaleLifecycleStateError as exc:
                RESULT["error"], RESULT["detail"] = type(exc).__name__, str(exc)
            RESULT["claim"] = ws.resolve_claim(root, item.wid)
        """)
        self.assertEqual(stale["error"], "StaleLifecycleStateError")
        self.assertIn("merge the resolved amendment first", stale["detail"])
        self.assertIsNone(stale["claim"])
        _git(b, "merge", "-q", "--ff-only", "main")
        admitted = self.drive(checkout=b, body=f"""
            item = attach_item({self.WID!r})
            RESULT["claim"] = ws.claim_checkpoint(root, item.wid, "CP2", now=item.now())["checkpoint_id"]
        """)
        self.assertEqual(admitted["claim"], "CP2")


#: `/approve-review plan` completed from durable state by a new session:
#: the journal's evidence, the user's literal, the takeover, then 6a-6d.
_TAKE_OVER_AND_COMPLETE = """
def take_over_and_complete(item):
    evidence = ws.plan_approval_takeover_evidence(root)
    token = ws.take_over_plan_approval_transaction(
        root, work_item_id=item.wid, now=item.now(),
        user_authorization=ws.plan_approval_takeover_authorization_literal(evidence),
        evidence=evidence,
    )
    return item.complete_plan_approval(token)
"""


#: A `2.5.1` checkout's own `/request-plan-amendment` (no lock, no
#: witness) and its own `/approve-review plan` resolution of the open
#: amendment -- `2.5.1`'s harness predates both, so these follow
#: `tests/test_amendment_update_path.py`'s scripted 2.4.0-era sequence.
_WORKFLOW_251_HELPERS = """
def request_amendment_251(item, reason):
    item.tx(lambda state: ws.request_plan_amendment(
        state, item.wid, reason, repo_root=root, now=item.now()))


def resolve_amendment_251(item, checkpoints, requirements, plan_body):
    work_item = item.entry()
    entry = work_item["amendment_history"][-1]
    pre_plan_text, pre_registry = ws.load_pre_amendment_snapshot(
        root, item.wid, item.plan_path, item.registry_path, entry)
    revision = work_item["plan_revision"] + 1
    registry = ws.generate_registry(item.wid, revision, checkpoints)
    mapping = ws.generate_mapping(item.wid, requirements, registry=registry)
    ws.write_registry_and_mapping(
        root, Path(item.registry_path), Path(item.mapping_path), registry, mapping)
    plan_text = (f"# {item.wid} plan (Revision {revision})\\n\\n{plan_body}\\n"
                 + "".join(f"<!-- {c['id']} -->\\n{c['id']} -- {c['name']}.\\n<!-- /{c['id']} -->\\n\\n"
                           for c in registry["checkpoints"])
                 + ws.render_registry_markdown(registry) + "\\n")
    scratch.write(item.plan_path, plan_text)
    item.tx(lambda state: ws.publish_plan_revision(state, item.wid, revision, item.now()))
    digest, projection = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, item.wid)
    now = item.now()
    record = ws.build_approval_record(
        basis="USER_OVERRIDE", stage="plan", user_confirmation=f"plan {item.wid}", now=now,
        reviewed_bundle_id=f"lagging-{item.wid}", approved_review_content_id=digest,
        review_content_manifest=projection["review_content_manifest"])
    item.tx(lambda state: ws.apply_plan_approval(
        state, item.wid, record, now, pre_registry=pre_registry, pre_plan_text=pre_plan_text,
        post_registry=registry, post_plan_text=plan_text))
    return scratch.commit(
        f"chore({item.wid}): plan-stage approval (2.5.1, lagging worktree)",
        {"Workflow-Plan-Approval": digest, "Workflow-Work-Item": item.wid})
"""


class TestScenario7MixedReleaseWorktrees(_InstalledRepoCase):
    """REQ-7's mixed-release half (revision 3, `LPR-R2-003`; revision 7,
    `MPR-R1-I1`). The repository starts on `2.5.1`; `main` merges the
    `2.6.0` update, and a linked worktree on a branch that has not merged it
    keeps running its own installed `2.5.1` scripts."""

    BASE_VERSION = "2.5.1"
    WID = "mixed"

    def _implementing_under_251(self):
        self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = new_item({self.WID!r})
            plan_to_implementing(item, *chained(2))
        """)

    def test_a_lagging_worktrees_amendment_refuses_an_updated_claim_and_no_sentinel_is_written(self):
        self._implementing_under_251()
        lag = self.add_worktree("lagging")
        self.update_to("2.6.0")
        self.assertEqual((self.installed_version(), self.installed_version(lag)), ("2.6.0", "2.5.1"))

        # A lagging worktree alone refuses nothing, but no NONE sentinel.
        admitted = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            claim = ws.claim_checkpoint(root, item.wid, "CP2", now=item.now())
            RESULT["claim"] = claim["checkpoint_id"]
            RESULT["witness"] = witness(item)
            ws.release_checkpoint(root, item.wid, "CP2", owner_token=claim["owner_token"],
                                  now=item.now())
        """)
        self.assertEqual(admitted, {"claim": "CP2", "witness": None})

        lagging = self.drive(checkout=lag, helpers=_COMMAND_HELPERS + _WORKFLOW_251_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            request_amendment_251(item, "requested from the lagging worktree")
            RESULT["phase"] = item.entry()["phase"]
        """)
        self.assertEqual(lagging["phase"], "AMENDING_PLAN")
        refused = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            try:
                ws.claim_checkpoint(root, item.wid, "CP2", now=item.now())
            except ws.LaggingWorktreeAmendmentError as exc:
                RESULT["error"], RESULT["evidence"] = type(exc).__name__, exc.evidence
            RESULT["claim"] = ws.resolve_claim(root, item.wid)
            RESULT["witness"] = witness(item)
        """)
        self.assertEqual(refused["error"], "LaggingWorktreeAmendmentError")
        self.assertEqual(os.path.realpath(refused["evidence"]["worktree"]), os.path.realpath(lag))
        self.assertEqual((refused["evidence"]["branch"], refused["evidence"]["installed_version"],
                          refused["evidence"]["seq"]), ("lagging", "2.5.1", 1))
        self.assertIsNone(refused["claim"])
        self.assertIsNone(refused["witness"], "no NONE sentinel while a worktree lags")

    def test_one_resolution_per_amendment_across_updated_and_lagging_worktrees(self):
        self._implementing_under_251()
        pre_update = _git(self.root, "rev-parse", "HEAD").strip()
        self.update_to("2.6.0")
        requested = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            item.request_amendment("one resolution per sequence", commit=True)
            RESULT["witness"] = [witness(item)["status"], witness(item)["amendment_seq"]]
            RESULT["head"] = scratch.head()
        """)
        self.assertEqual(requested["witness"], ["OPEN", 1])
        b = self.add_worktree("b")

        # Each updated worktree amends differently and passes both reviews.
        amend = """
            item = attach_item({wid!r})
            item.amend_plan(2, *chained({count}, prefix={prefix!r}), plan_body={body!r})
            item.generate_plan_bundle()
            review_plan_write(item)
            item.record_plan_reviews(round=2)
            RESULT["phase"] = item.entry()["phase"]
        """
        for checkout, count, prefix in ((self.root, 2, "amended in main"), (b, 3, "amended in b")):
            reviewed = self.drive(checkout=checkout, helpers=_COMMAND_HELPERS, body=amend.format(
                wid=self.WID, count=count, prefix=prefix, body=f"Plan body, {prefix}.\n"))
            self.assertEqual(reviewed["phase"], "AWAITING_PLAN_APPROVAL")

        # main's session dies right after step 4d reserved the resolution:
        # the reservation stays live (RESOLVING, its journal still open).
        crashed = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            class SessionDied(BaseException):
                pass

            def die(_journal):
                raise SessionDied()

            item = attach_item({self.WID!r})
            head = scratch.head()
            try:
                item.approve_plan(hooks={{"after_reserve": die}})
            except SessionDied:
                pass
            RESULT["head_unchanged"] = scratch.head() == head
            RESULT["journal_open"] = ws.read_plan_approval_journal(root) is not None
            RESULT["witness"] = witness(item)["status"]
        """)
        self.assertEqual(crashed, {"head_unchanged": True, "journal_open": True,
                                   "witness": "RESOLVING"})
        attempt = f"""
            item = attach_item({self.WID!r})
            item.stage_plan_files()
            head = scratch.head()
            try:
                item.approve_plan()
            except ws.LifecycleRefusalError as exc:
                RESULT["error"], RESULT["detail"] = type(exc).__name__, str(exc)
            RESULT["head_unchanged"] = scratch.head() == head
            RESULT["journal"] = ws.read_plan_approval_journal(root)
        """
        reserved = self.drive(checkout=b, helpers=_COMMAND_HELPERS, body=attempt)
        self.assertEqual(reserved["error"], "AmendmentResolutionReservedError")
        self.assertIn(os.path.realpath(self.root), reserved["detail"])
        self.assertTrue(reserved["head_unchanged"])
        self.assertIsNone(reserved["journal"])

        # A new session in main takes the transaction over: nothing was
        # committed, so 6b rolls it back and releases the reservation in
        # band; a fresh `/approve-review plan` then reserves and commits.
        completed = self.drive(helpers=_COMMAND_HELPERS + _TAKE_OVER_AND_COMPLETE, body=f"""
            item = attach_item({self.WID!r})
            RESULT["taken_over"] = take_over_and_complete(item)
            RESULT["released"] = witness(item)["status"]
            item.stage_plan_files()
            RESULT["commit"] = item.approve_plan()
            entry = json.loads(scratch.git("show", f"HEAD:{STATE_PATH}").stdout)[
                "work_items"][item.wid]["amendment_history"][0]
            RESULT["committed_digest"] = ws.amendment_resolution_projection_sha256(entry)
            RESULT["witness"] = witness(item)
        """)
        self.assertIsNone(completed["taken_over"])
        self.assertEqual(completed["released"], "OPEN")
        self.assertEqual(completed["witness"]["status"], "RESOLVED")
        self.assertEqual(completed["witness"]["resolution_projection_sha256"],
                         completed["committed_digest"], "the witness records the winner's digest")
        stale = self.drive(checkout=b, helpers=_COMMAND_HELPERS, body=attempt)
        self.assertEqual(stale["error"], "StaleLifecycleStateError")
        self.assertTrue(stale["head_unchanged"])
        approvals = [line for line in _git(self.root, "log", "--all", "--format=%B").splitlines()
                     if line.startswith("Workflow-Plan-Approval: ")]
        self.assertEqual(len(approvals), 2, "round 1's approval plus exactly one resolution")

        # A lagging worktree carrying the same open seq 1 (its branch never
        # merged the update) resolves it unreserved, with its own 2.5.1
        # scripts and a different plan; the next 2.6.0 (9) holder refuses.
        lag = self.add_worktree("lagging", at=pre_update)
        (lag / STATE_PATH).write_text(_git(self.root, "show", f"{requested['head']}:{STATE_PATH}"))
        _git(lag, "commit", "-q", "-am", "carry the open amendment (no update merged)")
        lagged = self.drive(checkout=lag, helpers=_COMMAND_HELPERS + _WORKFLOW_251_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            RESULT["commit"] = resolve_amendment_251(
                item, *chained(4, prefix="lagging"),
                plan_body="Plan body, resolved in the lagging worktree.")
            RESULT["phase"] = item.entry()["phase"]
        """)
        self.assertEqual(lagged["phase"], "IMPLEMENTING")
        conflict = self.drive(helpers=_COMMAND_HELPERS, body=f"""
            item = attach_item({self.WID!r})
            before = ws.read_amendment_witness_bytes(root, item.wid)
            try:
                ws.claim_checkpoint(root, item.wid, "CP2", now=item.now())
            except ws.AmendmentResolutionConflictError as exc:
                RESULT["error"], RESULT["evidence"] = type(exc).__name__, exc.evidence
            RESULT["witness_unchanged"] = ws.read_amendment_witness_bytes(root, item.wid) == before
            RESULT["claim"] = ws.resolve_claim(root, item.wid)
        """)
        self.assertEqual(conflict["error"], "AmendmentResolutionConflictError")
        self.assertEqual(os.path.realpath(conflict["evidence"]["worktree"]), os.path.realpath(lag))
        self.assertEqual(conflict["evidence"]["recorded"], completed["committed_digest"])
        self.assertNotEqual(conflict["evidence"]["divergent"], completed["committed_digest"])
        self.assertTrue(conflict["witness_unchanged"])
        self.assertIsNone(conflict["claim"])


# ===========================================================================
# Scenario 8 -- AMENDMENT_DIFF.patch during an open amendment
# ===========================================================================


class TestScenario8AmendmentDiffReflectsTheUncommittedAmendment(_InstalledRepoCase):
    """REQ-8 (`v2.4.0-003`): during an open amendment the plan bundle's
    `AMENDMENT_DIFF.patch` is non-empty -- it shows the uncommitted amended
    plan under review -- and the archive's member is byte-identical."""

    def test_patch_is_non_empty_and_the_archive_member_matches(self):
        result = self.drive(helpers=_COMMAND_HELPERS, body="""
            import tarfile
            item = new_item("amended")
            item.milestone_plan()
            item.generate_plan_bundle()
            review_plan_write(item)
            item.record_plan_reviews()
            item.approve_plan()
            item.implement_checkpoint("CP1", {item.deliverable: "# amended\\n"})
            item.request_amendment("the design changed", commit=True)
            item.amend_plan(2, plan_body="Plan body, amended to the new design.\\n")
            item.generate_plan_bundle()
            item_root = root / ".ai-review" / item.wid
            patch = (item_root / "AMENDMENT_DIFF.patch").read_bytes()
            with tarfile.open(item_root / "review-bundle.tar.gz") as tar:
                member = tar.extractfile("AMENDMENT_DIFF.patch").read()
            RESULT["phase"] = item.entry()["phase"]
            RESULT["patch"] = patch.decode()
            RESULT["member_equal"] = member == patch
            RESULT["plan_committed_unchanged"] = "amended to the new design" not in scratch.git(
                "show", f"HEAD:{item.plan_path}").stdout
        """)
        self.assertEqual(result["phase"], "AWAITING_LOCAL_PLAN_REVIEW")
        self.assertTrue(result["plan_committed_unchanged"], "the amendment is still uncommitted")
        self.assertIn("+Plan body, amended to the new design.", result["patch"])
        self.assertIn("docs/ai-workflow/amended-plan.md", result["patch"])
        self.assertTrue(result["member_equal"])


# ===========================================================================
# Scenario 9 -- update 2.5.1 -> 2.6.0 with items in flight
# ===========================================================================


class TestScenario9UpdateWithItemsInFlight(_InstalledRepoCase):
    """REQ-11 (section 6.1; INV-7): four `2.5.1` items caught mid-flight by
    the update -- `AWAITING_LOCAL_PLAN_REVIEW`, `IMPLEMENTING`,
    `AMENDING_PLAN`, and `REVISING_PLAN` mid-apply with no
    `plan_review_binding`. The update leaves the committed state
    byte-identical, and each item then proceeds through its next gate under
    `2.6.0`.

    Two legacy-flat items with live feedback would share the one flat
    `REVIEW_FEEDBACK.md` (the `2.5.1` behavior `D-Feedback-Layout` keeps for
    legacy items), so the two plan-stage items get their per-item
    directory under `2.5.1` first, which the legacy rule then honors
    (`legacy-scoped`)."""

    BASE_VERSION = "2.5.1"

    def test_each_item_proceeds_through_its_next_gate(self):
        setup = self.drive(helpers=_COMMAND_HELPERS + _WORKFLOW_251_HELPERS, body="""
            implementing = new_item("implementing")
            plan_to_implementing(implementing, *chained(2))

            amending = new_item("amending")
            plan_to_implementing(amending, *chained(2))
            request_amendment_251(amending, "the design changed before the update")
            scratch.commit("chore(amending): request plan amendment",
                           {"Workflow-Work-Item": amending.wid},
                           paths=["docs/ai-workflow/WORKFLOW_STATE.json"])

            local = new_item("local-review")
            (root / ".ai-review" / local.wid / "feedback").mkdir(parents=True)
            local.milestone_plan()
            local.generate_plan_bundle()

            revising = new_item("revising")
            (root / ".ai-review" / revising.wid / "feedback").mkdir(parents=True)
            revising.milestone_plan()
            revising.generate_plan_bundle()
            revising.write_feedback("REVISE", role="LOCAL_MODEL_PLAN_REVIEW",
                                    extra="## Important\\n\\n- Split CP1.\\n")
            digest, _ = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, revising.wid)
            revising.tx(lambda state: ws.record_local_plan_review(
                state, revising.wid, verdict="REVISE", bundle_id=revising.bundle_id(),
                review_content_id=digest, round=1, now=revising.now()))
            # /apply-plan-review, interrupted mid-apply: the plan document
            # edited, nothing regenerated or published yet.
            scratch.write(revising.plan_path, scratch.read(revising.plan_path).replace(
                "Plan body.", "Plan body, partly revised."))
            RESULT["phases"] = {wid: e["phase"] for wid, e in local.state()["work_items"].items()}
        """)
        self.assertEqual(setup["phases"], {
            "implementing": "IMPLEMENTING", "amending": "AMENDING_PLAN",
            "local-review": "AWAITING_LOCAL_PLAN_REVIEW", "revising": "REVISING_PLAN"})
        for entry in self.state()["work_items"].values():
            self.assertNotIn("plan_review_binding", entry)
            self.assertNotIn("feedback_layout", entry)
        _git(self.root, "add", STATE_PATH)
        _git(self.root, "commit", "-q", "-m", "checkpoint the in-flight state before the update")
        committed = _git(self.root, "rev-parse", f"HEAD:{STATE_PATH}")

        self.update_to("2.6.0")
        self.assertEqual(_git(self.root, "rev-parse", f"HEAD:{STATE_PATH}"), committed)
        self.assertEqual(_git(self.root, "diff", "--name-only", "HEAD~1", "HEAD", "--", STATE_PATH), "")

        result = self.drive(helpers=_COMMAND_HELPERS, body="""
            # IMPLEMENTING: the next checkpoint, through /milestone-implement.
            implementing = attach_item("implementing")
            implementing.implement_checkpoint("CP2", {implementing.deliverable: "# CP2\\n"})
            RESULT["implementing"] = implementing.entry()["phase"]

            # AWAITING_LOCAL_PLAN_REVIEW: /review-plan's bound-bundle reader
            # accepts the verifying legacy bundle and writes nothing; the
            # local APPROVE is recorded.
            local = attach_item("local-review")
            ws.validate_local_plan_review_preconditions_bound(root, local.entry())
            RESULT["local_written"] = review_plan_write(local)
            digest, _ = fingerprint.compute_review_content_id_plan_stage_for_work_item(root, local.wid)
            local.tx(lambda state: ws.record_local_plan_review(
                state, local.wid, verdict="APPROVE", bundle_id=local.bundle_id(),
                review_content_id=digest, round=1, now=local.now()))
            RESULT["local"] = [local.entry()["phase"], "plan_review_binding" in local.entry()]

            # AMENDING_PLAN: no witness until the first (9) holder; the
            # entry marker is the non-legacy CONSUMED record from the
            # superseded approval; the amended plan binds, both reviews
            # pass, and /approve-review plan's step 4d establishes the
            # witness by the scan, then resolves it.
            amending = attach_item("amending")
            RESULT["amending_witness_before"] = witness(amending)
            superseded = amending.entry()["amendment_history"][-1]["superseded_plan_approval"]
            amending.tx(lambda state: ws.ensure_plan_review_binding_marker(state, amending.wid, amending.now()))
            RESULT["amending_marker"] = amending.entry()["plan_review_binding"]["consumed"]
            RESULT["amending_superseded"] = superseded["approved_review_content_id"]
            amending.amend_plan(2, *chained(2, prefix="amended step"))
            amending.generate_plan_bundle()
            review_plan_write(amending)
            amending.record_plan_reviews(round=2)
            amending.approve_plan()
            RESULT["amending"] = [amending.entry()["phase"], witness(amending)["status"],
                                  witness(amending)["amendment_seq"]]

            # REVISING_PLAN mid-apply: a publish before the entry refuses as
            # unknown; the entry writes the fail-closed legacy marker at the
            # current mirror; publishing at that revision then refuses as
            # consumed; one revision advance publishes, generates and binds.
            revising = attach_item("revising")
            RESULT["before_marker"] = raised(revising.publish)
            RESULT["revising_entry"] = apply_plan_review_entry(revising)
            RESULT["revising_marker"] = revising.entry()["plan_review_binding"]["consumed"]
            before = (root / "docs/ai-workflow/WORKFLOW_STATE.json").read_bytes()
            RESULT["same_revision"] = raised(
                revising.apply_plan_review, 1, plan_body="Plan body, partly revised.\\n")
            RESULT["same_revision_wrote_state"] = (
                (root / "docs/ai-workflow/WORKFLOW_STATE.json").read_bytes() != before)
            revising.apply_plan_review(2, plan_body="Plan body, revised: CP1 split.\\n")
            revising.generate_plan_bundle()
            entry = revising.entry()
            RESULT["revising"] = [entry["phase"], entry["plan_revision"],
                                  entry["plan_review_binding"]["status"]]
        """)
        self.assertEqual(result["implementing"], "SELF_REVIEWING_IMPLEMENTATION")
        self.assertEqual(result["local_written"],
                         ".ai-review/local-review/feedback/REVIEW_FEEDBACK.md")
        self.assertEqual(result["local"], ["AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW", False],
                         "nothing is back-filled for a verifying legacy ready item")
        self.assertIsNone(result["amending_witness_before"])
        self.assertEqual(result["amending_marker"], {
            "review_content_id": result["amending_superseded"], "plan_revision": 1, "legacy": False})
        self.assertEqual(result["amending"], ["IMPLEMENTING", "RESOLVED", 1])
        self.assertEqual(result["revising_entry"]["status"], "EDIT_IN_PROGRESS")
        self.assertEqual(result["revising_entry"]["mode"], "durable")
        self.assertEqual(result["revising_marker"], {
            "review_content_id": None, "plan_revision": 1, "legacy": True})
        self.assertEqual(result["before_marker"], "LegacyPlanReviewBindingUnknownError")
        self.assertEqual(result["same_revision"], "ConsumedPlanReviewContentError")
        self.assertFalse(result["same_revision_wrote_state"])
        self.assertEqual(result["revising"], ["AWAITING_LOCAL_PLAN_REVIEW", 2, "BOUND"])


# ===========================================================================
# Closed-defect census -- v2.3.1-001/-002/-003 stay regression-protected
# ===========================================================================


PAYLOAD_260 = REPO_ROOT / "distribution" / "workflow" / "2.6.0" / "payload"

#: Section 3.8's named regression tests, per closed defect: `(module,
#: [Class or Class.test_method, ...])`, all in `payload/scripts/`.
CLOSED_DEFECT_TESTS = {
    "v2.3.1-001": [("workflow_integration_test", [
        "TestRetiredScopedRemediationLeavesNoLiveSurface."
        "test_the_historical_status_note_carries_a_dated_correction"])],
    "v2.3.1-002": [("workflow_state_test", [
        "TestRequestPlanAmendment", "TestReconcileCheckpointsAfterAmendment",
        "TestAmendmentClaimRaceRealProcesses", "TestApplyPlanApprovalAmendmentBranch"])],
    "v2.3.1-003": [("workflow_integration_test", [
        "TestPlanApprovalStateBlobPinAndMaterialize."
        "test_pin_defaults_to_mode_100644_when_state_path_absent_at_head"])],
}


def _defined_names(module_path: Path) -> set[str]:
    """Every top-level class and `Class.method` defined in `module_path`."""
    import ast
    names = set()
    for node in ast.parse(module_path.read_text()).body:
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
            names.update(f"{node.name}.{item.name}" for item in node.body
                         if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return names


class TestClosedDefectCensus(_InstalledRepoCase):
    """REQ-9 (section 3.8): the named regression tests for `v2.3.1-001`,
    `-002` and `-003` exist in the composed `2.6.0` payload and pass in a
    repository installed from it; the repository-level guards they rely on
    are still registered; and `v2.3.1-003` is re-proved end to end through
    `2.6.0`'s new committed-truth verifier, as section 3.8's "Interaction
    with this release" requires."""

    def test_the_named_regression_tests_exist_in_the_2_6_0_payload(self):
        for defect, modules in CLOSED_DEFECT_TESTS.items():
            for module, names in modules:
                defined = _defined_names(PAYLOAD_260 / "scripts" / f"{module}.py")
                for name in names:
                    with self.subTest(defect=defect, test=f"{module}.{name}"):
                        self.assertIn(name, defined)

    def test_the_named_regression_tests_pass_in_an_installed_2_6_0_repository(self):
        ids = [f"{module}.{name}" for modules in CLOSED_DEFECT_TESTS.values()
               for module, names in modules for name in names]
        for module in {m for modules in CLOSED_DEFECT_TESTS.values() for m, _ in modules}:
            self.assertEqual((self.root / "scripts" / f"{module}.py").read_bytes(),
                             (PAYLOAD_260 / "scripts" / f"{module}.py").read_bytes())
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHON_COLORS="0",
                   GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", *ids], cwd=str(self.root / "scripts"),
            capture_output=True, text=True, env=env, timeout=1800,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-6000:])
        self.assertRegex(proc.stderr, r"\nOK( \(skipped=\d+\))?\n")
        for defect, modules in CLOSED_DEFECT_TESTS.items():
            for _module, names in modules:
                for name in names:
                    with self.subTest(defect=defect, test=name):
                        self.assertIn(f"({_module}.{name}", proc.stderr)

    def test_the_repository_level_guards_are_still_registered(self):
        # v2.3.1-001: a clean 2.6.0 target has no documented exception, and
        # the per-release bootstrapped-target class asserts exactly that.
        self.assertEqual(json.loads((REPO_ROOT / "migration" / "portability_exceptions.json")
                                    .read_text())["by_version"]["2.6.0"], {"exceptions": []})
        self.assertIn("TestBootstrappedTarget260",
                      _defined_names(REPO_ROOT / "tests" / "test_conformance_suite.py"))
        # v2.3.1-002: this suite is in the full inventory, so every gate run
        # executes it, and in `parallel.cli.FAST_ALIAS_SELECTION`, so the
        # deprecated `--fast` alias runs it too.
        from parallel import cli, inventory
        found = inventory.discover(REPO_ROOT)
        update_path = {unit for unit in found.host
                       if inventory.split_host_unit_id(unit)[0] == "test_amendment_update_path.py"}
        self.assertTrue(update_path, "test_amendment_update_path.py has no host class")
        full = set(inventory.select(found.host, [], found.frozen).unit_ids())
        self.assertLessEqual(update_path, full)
        alias = set(inventory.select(found.host, list(cli.FAST_ALIAS_SELECTION),
                                     found.frozen).unit_ids())
        self.assertLessEqual(update_path, alias)

    def test_v2_3_1_003_first_approval_with_no_state_at_head_through_the_new_verifier(self):
        _git(self.root, "rm", "-q", "--cached", STATE_PATH)
        _git(self.root, "commit", "-q", "-m", "a repository whose state file was never committed")
        self.assertEqual(_git(self.root, "ls-tree", "HEAD", "--", STATE_PATH), "")
        result = self.drive(helpers=_COMMAND_HELPERS, body="""
            item = new_item("first-approval")
            item.milestone_plan()
            item.generate_plan_bundle()
            review_plan_write(item)
            item.record_plan_reviews()
            journal = {}
            commit = item.approve_plan(hooks={"after_commit": journal.update})
            RESULT["verified"] = raised(ws.verify_plan_approval_commit, root, journal, commit)
            RESULT["phase"] = item.entry()["phase"]
            RESULT["state_entry"] = scratch.git("ls-tree", commit, "--", "docs/ai-workflow/WORKFLOW_STATE.json").stdout.split()[:2]
            RESULT["journal"] = ws.read_plan_approval_journal(root)
        """)
        self.assertIsNone(result["verified"])
        self.assertEqual(result["phase"], "IMPLEMENTING")
        self.assertEqual(result["state_entry"], ["100644", "blob"])
        self.assertIsNone(result["journal"])


if __name__ == "__main__":
    unittest.main()
