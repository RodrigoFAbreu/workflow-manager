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
"""

from __future__ import annotations

import subprocess
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


def init_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Workflow Fixture")
    _git(root, "config", "commit.gpgsign", "false")


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
