"""Assembling a disposable Git repository from a migrated release.

Two shapes matter, and they are deliberately different:

`build_conformance_repo`
    Reproduces the frozen upstream host context closely enough for the
    frozen v2.3.1 suite to run unchanged: the full payload, plus the
    `host-evidence` fixtures the suite asserts dated paragraphs of, plus
    clean templates for the two repository-local state files. This is the
    equivalence evidence -- if the frozen suite is green here, the migrated
    bytes behave as they did upstream.

`build_target_repo`
    What a *managed target repository* actually looks like after bootstrap:
    the payload plus generated clean state, and no upstream host history at
    all. Some frozen tests cannot pass here by construction -- see
    `docs/defects/v2.3.1-001-host-history-coupled-tests.md`.

`drive_synthetic_work_item_through_checkpoints`
    Lands a `build_target_repo`-shaped repository in `IMPLEMENTING` (some
    checkpoints `COMPLETE`, the rest untouched) or `SELF_REVIEWING_
    IMPLEMENTATION` (every checkpoint `COMPLETE`), scripted through the
    *installed* `workflow_state`/`workflow_fingerprint` modules the same
    way `tests/test_bootstrap_e2e.py`'s own `_write_live_state` already
    drives a single `PLANNING`-phase item without a live Claude session --
    generalized here into a reusable disposable-repository fixture for
    `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` (CP7). It runs as a
    subprocess against the target's own `scripts/` (never this
    repository's, and never an in-process `import`, since two different
    releases' modules must never share Python's module cache within one
    test process), producing a real, reachable plan-approval commit
    (`Workflow-Plan-Approval:`/`Workflow-Work-Item:` trailers) and one
    real checkpoint commit (`Workflow-Checkpoint:`/`Workflow-Work-Item:`
    trailers) per completed checkpoint -- so `implementing_entry_reachable`,
    `discover_plan_approval_commit` and `discover_checkpoint_commits` all
    resolve exactly as they would for a repository a live session produced.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .release import (
    GITIGNORE_TEMPLATE,
    INSTALL_PROFILE_FULL,
    RELEASE_TEMPLATES,
    STATE_TEMPLATES,
    Release,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    ).stdout


#: Git's automatic maintenance, off in every throwaway repository a test
#: creates (`D-Quiet-Git`): no `git maintenance run --auto` and no `git gc
#: --auto` after a commit, and the two `autoDetach` keys keep any run that
#: still happens in the foreground, so nothing a test starts is orphaned.
#: The one definition: `tests/parallel/isolation.py` reads this literal from
#: this file's source (the executor process never imports this package).
THROWAWAY_GIT_CONFIG = {
    "maintenance.auto": "false",
    "gc.auto": "0",
    "maintenance.autoDetach": "false",
    "gc.autoDetach": "false",
}


def configure_throwaway_repo(root: Path) -> None:
    """Write `THROWAWAY_GIT_CONFIG` into `root`'s local config -- the
    per-repository layer, for a repository made outside `init_git_repo` (a
    `git clone`, which does not inherit its source's config)."""
    for key, value in THROWAWAY_GIT_CONFIG.items():
        _git(root, "config", key, value)


def init_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Workflow Fixture")
    _git(root, "config", "commit.gpgsign", "false")
    configure_throwaway_repo(root)


def write_artifact(release: Release, artifact, dest_root: Path) -> Path:
    path = dest_root / artifact.target_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(release.read_verified(artifact.location, artifact.sha256))
    path.chmod(0o755 if artifact.executable else 0o644)
    return path


def write_template(release: Release, template: dict, dest_root: Path) -> Path:
    path = dest_root / template["target_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(release.read_verified(template["location"], template["sha256"]))
    path.chmod(0o644)
    return path


def _place_payload(release: Release, dest: Path, profile: str) -> None:
    """Everything the release owns under `profile` -- the same set `bootstrap`
    installs, so a fixture and a bootstrapped target cannot diverge."""
    for artifact in release.installable(profile):
        write_artifact(release, artifact, dest)


def _place_state_templates(release: Release, dest: Path) -> None:
    """Only the two repository-local state files the Workflow itself reads.

    `docs/ACTIVE_MILESTONE.md` is deliberately absent: in this fixture it comes
    from the frozen host document instead, which is the whole point of the
    conformance run. The `.gitignore` fragment is an installer concern, not a
    conformance one, so it is not placed here either.
    """
    wanted = {
        rel for rel in STATE_TEMPLATES if rel.startswith("docs/ai-workflow/")
    }
    for template in release.templates():
        if template["target_path"] in wanted:
            write_template(release, template, dest)


def build_conformance_repo(release: Release, dest: Path, commit: bool = True) -> Path:
    dest = Path(dest)
    init_git_repo(dest)
    _place_payload(release, dest, INSTALL_PROFILE_FULL)
    for artifact in release.fixture_artifacts():
        write_artifact(release, artifact, dest)
    _place_state_templates(release, dest)
    fragment = next(t for t in release.templates()
                    if t["target_path"] == GITIGNORE_TEMPLATE)
    (dest / ".gitignore").write_bytes(
        release.read_verified(fragment["location"], fragment["sha256"])
    )
    if commit:
        _git(dest, "add", "-A")
        _git(dest, "commit", "-q", "-m", f"workflow v{release.version} conformance fixture")
    return dest


def build_target_repo(release: Release, dest: Path, profile: str = INSTALL_PROFILE_FULL,
                      commit: bool = True) -> Path:
    """A clean managed repository: payload plus generated state, no host history."""
    dest = Path(dest)
    init_git_repo(dest)
    _place_payload(release, dest, profile)
    for template in release.templates():
        if template["target_path"] in RELEASE_TEMPLATES:
            continue                      # already placed as release content
        if template["target_path"] == GITIGNORE_TEMPLATE:
            (dest / ".gitignore").write_bytes(
                release.read_verified(template["location"], template["sha256"]))
        else:
            write_template(release, template, dest)
    if commit:
        _git(dest, "add", "-A")
        _git(dest, "commit", "-q", "-m", f"workflow v{release.version} install")
    return dest


# ---------------------------------------------------------------------------
# Disposable-repository fixtures for IMPLEMENTING/SELF_REVIEWING_IMPLEMENTATION
# ---------------------------------------------------------------------------

#: Executed with `sys.executable -c` inside the target repository, its own
#: `scripts/` already on `sys.path` -- so every call below runs the exact
#: `workflow_state`/`workflow_fingerprint` bytes this specific release
#: installed, never this source tree's copies. Every value the caller
#: supplies is substituted as a Python literal via `repr()`, never
#: interpolated as text, so no value can break out of its own expression.
_DRIVER_SCRIPT = """
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, {scripts_dir!r})
import workflow_fingerprint as fingerprint
import workflow_state as ws

root = Path({root!r})
work_item_id = {work_item_id!r}
work_item_type = {work_item_type!r}
checkpoint_ids = {checkpoint_ids!r}
complete_checkpoint_ids = {complete_checkpoint_ids!r}
now = {now!r}


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
    ).stdout


def _commit(subject, trailers):
    _git("add", "-A")
    body = subject + "\\n\\n" + "\\n".join(f"{{k}}: {{v}}" for k, v in trailers.items())
    _git("commit", "-q", "-m", body)
    return _git("rev-parse", "HEAD").strip()


base_commit = _git("rev-parse", "HEAD").strip()

plan_path = f"docs/ai-workflow/{{work_item_id}}-plan.md"
registry_path = f"docs/ai-workflow/registry/{{work_item_id}}-registry.json"
mapping_path = f"docs/ai-workflow/requirements/{{work_item_id}}-mapping.json"
artifacts_path = str(fingerprint.artifacts_path_for_work_item(work_item_id))

checkpoints = [
    {{
        "id": cid, "name": f"synthetic checkpoint {{cid}}",
        "depends_on": ([checkpoint_ids[i - 1]] if i else []),
        "complexity": 1, "session_target": 1,
    }}
    for i, cid in enumerate(checkpoint_ids)
]
requirements = {{
    f"R{{i + 1}}": {{"description": f"synthetic requirement for {{cid}}", "checkpoint_ids": [cid]}}
    for i, cid in enumerate(checkpoint_ids)
}}

config = json.loads((root / "docs/ai-workflow/WORKFLOW_CONFIG.json").read_text())


def _route(state):
    return ws.route_work_item(
        state, config, work_item_id=work_item_id, work_item_type=work_item_type,
        work_item_kind=work_item_type, plan_path=plan_path, registry_path=registry_path,
        plan_revision=1, now=now, mapping_path=mapping_path, base_commit=base_commit,
        repo_root=root,
    )


ws.state_transaction(root, _route)

registry = ws.generate_registry(work_item_id, 1, checkpoints)
mapping = ws.generate_mapping(work_item_id, requirements, registry=registry)
ws.write_registry_and_mapping(root, Path(registry_path), Path(mapping_path), registry, mapping)

declarations = ws.generate_artifacts_declarations(
    work_item_id, plan_path, registry_path, mapping_path, work_item_type=work_item_type,
)
(root / artifacts_path).parent.mkdir(parents=True, exist_ok=True)
(root / artifacts_path).write_text(json.dumps(declarations, indent=2) + "\\n")

(root / plan_path).parent.mkdir(parents=True, exist_ok=True)
(root / plan_path).write_text(
    f"# {{work_item_id}} plan (Revision 1)\\n\\nSynthetic fixture.\\n\\n"
    + ws.render_registry_markdown(registry) + "\\n"
)

# `resolve_plan_stage_metadata` requires each declared path to be a
# *tracked* path -- intent-to-add, exactly like `/milestone-plan` step 3
# (`Item.stage_plan_files`): tracked but left uncommitted, since the
# approval commit below is what actually commits them.
_git("add", "-N", "--", plan_path, registry_path, mapping_path, artifacts_path)


def _publish(state):
    return ws.publish_plan_revision(state, work_item_id, 1, now)


ws.state_transaction(root, _publish)

review_content_id, projection = fingerprint.compute_review_content_id_plan_stage_for_work_item(
    root, work_item_id,
)
record = ws.build_approval_record(
    basis="USER_OVERRIDE", stage="plan", user_confirmation=f"plan {{work_item_id}}",
    now=now, reviewed_bundle_id=f"synthetic-fixture-{{work_item_id}}",
    approved_review_content_id=review_content_id,
    review_content_manifest=projection["review_content_manifest"],
)


def _approve(state):
    return ws.apply_plan_approval(state, work_item_id, record, now)


ws.state_transaction(root, _approve)
approval_commit = _commit(
    f"chore({{work_item_id}}): plan-stage approval (synthetic fixture)",
    {{"Workflow-Plan-Approval": review_content_id, "Workflow-Work-Item": work_item_id}},
)

for cid in checkpoint_ids:
    if cid not in complete_checkpoint_ids:
        break
    start_commit = _git("rev-parse", "HEAD").strip()

    def _in_progress(state, cid=cid, start_commit=start_commit):
        return ws.transition_checkpoint_in_progress(state, work_item_id, cid, start_commit, now)

    ws.state_transaction(root, _in_progress)

    deliverable = root / "scripts" / f"{{work_item_id}}-{{cid}}.txt"
    deliverable.parent.mkdir(parents=True, exist_ok=True)
    deliverable.write_text(f"synthetic deliverable for {{cid}}\\n")

    def _complete(state, cid=cid):
        return ws.complete_checkpoint(state, work_item_id, cid, registry, now, repo_root=root)

    ws.state_transaction(root, _complete)
    _commit(
        f"feat({{work_item_id}}): {{cid}} (synthetic fixture)",
        {{"Workflow-Checkpoint": cid, "Workflow-Work-Item": work_item_id}},
    )

final_state = json.loads((root / "docs/ai-workflow/WORKFLOW_STATE.json").read_text())
print(json.dumps({{
    "work_item_id": work_item_id,
    "base_commit": base_commit,
    "approval_commit": approval_commit,
    "head": _git("rev-parse", "HEAD").strip(),
    "phase": final_state["work_items"][work_item_id]["phase"],
}}))
"""


def drive_synthetic_work_item_through_checkpoints(
    dest: Path, *, work_item_id: str = "fixture-item", work_item_type: str = "process",
    checkpoint_ids: tuple[str, ...] = ("CP1", "CP2", "CP3"),
    complete_checkpoint_ids: tuple[str, ...] | None = None,
    now: str = "2026-01-01T00:00:00Z",
) -> dict:
    """Drive a synthetic work item, in `dest` (a repository already built by
    `build_target_repo`/`bootstrap`), through plan approval and through
    every checkpoint named in `complete_checkpoint_ids` -- landing the
    repository in `IMPLEMENTING` (a proper prefix) or
    `SELF_REVIEWING_IMPLEMENTATION` (every id in `checkpoint_ids`).

    `complete_checkpoint_ids` must be a prefix of `checkpoint_ids`
    (`depends_on` chains them in order) -- defaults to every id but the
    last, landing in `IMPLEMENTING` with one checkpoint left. Pass
    `complete_checkpoint_ids=checkpoint_ids` for `SELF_REVIEWING_
    IMPLEMENTATION`.

    Returns `{"work_item_id", "base_commit", "approval_commit", "head",
    "phase"}` -- `base_commit` is what a caller passes to
    `implementing_entry_reachable`/`/request-plan-amendment`-style checks,
    `head` is the repository's tip once this returns.
    """
    dest = Path(dest)
    if complete_checkpoint_ids is None:
        complete_checkpoint_ids = tuple(checkpoint_ids[:-1])
    prefix_len = len(complete_checkpoint_ids)
    if tuple(checkpoint_ids[:prefix_len]) != tuple(complete_checkpoint_ids):
        raise ValueError(
            f"complete_checkpoint_ids {complete_checkpoint_ids!r} is not a prefix of "
            f"checkpoint_ids {checkpoint_ids!r}"
        )
    script = _DRIVER_SCRIPT.format(
        scripts_dir=str(dest / "scripts"), root=str(dest), work_item_id=work_item_id,
        work_item_type=work_item_type, checkpoint_ids=list(checkpoint_ids),
        complete_checkpoint_ids=list(complete_checkpoint_ids), now=now,
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=str(dest), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"synthetic work item driver failed for {work_item_id!r} in {dest}:\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])
