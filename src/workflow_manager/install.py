"""Bootstrap, update, and verify a managed repository.

The whole module is arranged around one rule: **canonical distribution
content is replaced, repository-local state is not.** Every function here
either respects that rule or refuses.

Three operations:

`bootstrap`
    A repository that has never used the Workflow. Installs the payload,
    writes clean state from templates, merges the two shared files, and
    records what it did.

`update`
    A managed repository moving from one release to another. Replaces payload
    files, removes payload files the new release dropped, and leaves every
    generated state file exactly as it is. Refuses if a managed file was
    edited locally, unless told to discard those edits.

`verify` / `drift`
    Compares what is on disk against the release manifest and the installation
    record. This is what makes an update safe rather than hopeful: it runs
    before the update decides anything.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .installation import Installation, is_managed
from .release import (
    CLAUDE_TEMPLATE,
    GITIGNORE_TEMPLATE,
    INSTALL_PROFILE_FULL,
    INSTALL_PROFILES,
    STATE_TEMPLATES,
    Release,
    sha256,
)

#: Everything above this marker in a target's CLAUDE.md is ours to replace.
CLAUDE_END_MARKER = "<!-- workflow-manager:end -->"


class InstallError(RuntimeError):
    pass


class AlreadyManagedError(InstallError):
    pass


class NotManagedError(InstallError):
    pass


class DriftError(InstallError):
    def __init__(self, message: str, drifted: list["Drift"]):
        super().__init__(message)
        self.drifted = drifted


@dataclass(frozen=True)
class Drift:
    path: str
    kind: str          # "modified" | "missing" | "unexpected" | "not-executable"
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.kind}: {self.path}{f' ({self.detail})' if self.detail else ''}"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write(path: Path, data: bytes, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o755 if executable else 0o644)


def _prune_empty_parents(path: Path, stop: Path) -> None:
    parent = path.parent
    while parent != stop and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


# ---------------------------------------------------------------------------
# Merged files
# ---------------------------------------------------------------------------


def merge_gitignore(target: Path, fragment: bytes) -> tuple[bytes, str]:
    """Append the Workflow's ignore lines to the target's own `.gitignore`.

    Idempotent: a line already ignored is not added again, so repeated
    bootstraps and updates converge instead of accumulating.
    """
    path = target / ".gitignore"
    existing = path.read_bytes() if path.exists() else b""
    existing_lines = set(existing.decode("utf-8", "replace").splitlines())
    wanted = fragment.decode("utf-8").splitlines()
    missing = [
        line for line in wanted
        if line.strip() and not line.lstrip().startswith("#") and line not in existing_lines
    ]
    if not missing:
        return existing, "unchanged"
    prefix = existing
    if prefix and not prefix.endswith(b"\n"):
        prefix += b"\n"
    if prefix:
        prefix += b"\n"
    return prefix + fragment, ("created" if not existing else "appended")


def merge_claude_md(target: Path, managed: bytes) -> tuple[bytes, str]:
    """Replace the managed section of `CLAUDE.md`, preserving everything the
    repository wrote below `CLAUDE_END_MARKER`.

    A `CLAUDE.md` with no marker is the repository's own file and is left
    alone entirely: the managed section is prepended above it, and the
    repository's content becomes the tail.
    """
    path = target / "CLAUDE.md"
    if not path.exists():
        return managed, "created"
    existing = path.read_bytes()
    text = existing.decode("utf-8", "replace")
    if CLAUDE_END_MARKER in text:
        tail = text.split(CLAUDE_END_MARKER, 1)[1]
        return managed.decode("utf-8").rstrip("\n").encode("utf-8") + tail.encode("utf-8"), "replaced"
    tail = "\n" + text.lstrip("\n")
    return managed + tail.encode("utf-8"), "prepended"


def managed_claude_section(data: bytes) -> bytes:
    """The part of a `CLAUDE.md` this installer owns, for digest purposes."""
    text = data.decode("utf-8", "replace")
    if CLAUDE_END_MARKER in text:
        head = text.split(CLAUDE_END_MARKER, 1)[0] + CLAUDE_END_MARKER
        return head.encode("utf-8")
    return data


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def drift(target: Path, release: Release) -> list[Drift]:
    """Every difference between the target and what the record says is there.

    Managed files are compared against the *release manifest*, so a drift is
    "this differs from canonical", not merely "this changed since install".
    Generated files are compared against the record, since canonical has no
    opinion about them after they are created.
    """
    target = Path(target)
    installation = Installation.read(target)
    manifest_digests = {a.target_path: a for a in release.payload_artifacts(installation.profile)}
    found: list[Drift] = []

    for rel, record in sorted(installation.managed.items()):
        path = target / rel
        if not path.exists():
            found.append(Drift(rel, "missing"))
            continue
        data = path.read_bytes()
        artifact = manifest_digests.get(rel)
        expected = artifact.sha256 if artifact else record["sha256"]
        if sha256(data) != expected:
            found.append(Drift(rel, "modified"))
        elif record.get("executable") and not path.stat().st_mode & 0o111:
            found.append(Drift(rel, "not-executable"))

    for rel, record in sorted(installation.generated.items()):
        path = target / rel
        if not path.exists():
            found.append(Drift(rel, "missing", "repository-local state was deleted"))

    for rel in sorted(set(manifest_digests) - set(installation.managed)):
        if (target / rel).exists():
            found.append(Drift(rel, "unexpected", "present but not recorded as installed"))

    return found


def verify(target: Path, release: Release) -> list[str]:
    """Problems with the installation, as plain strings. Empty means healthy."""
    problems = [str(d) for d in drift(target, release)]
    problems += [f"release: {p}" for p in release.verify()]
    installation = Installation.read(Path(target))
    if installation.workflow_version != release.version:
        problems.append(
            f"version: installed {installation.workflow_version}, release {release.version}"
        )
    return problems


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap(target: Path, release: Release, profile: str = INSTALL_PROFILE_FULL,
              now: str | None = None) -> Installation:
    """Install the Workflow into a repository that has never used it."""
    target = Path(target)
    if profile not in INSTALL_PROFILES:
        raise InstallError(f"unknown install profile {profile!r}")
    if not target.is_dir():
        raise InstallError(f"no directory at {target}")
    if not (target / ".git").exists():
        raise InstallError(f"{target} is not a Git repository")
    if is_managed(target):
        raise AlreadyManagedError(
            f"{target} is already managed; use update() to move it to another release"
        )

    stamp = now or _now()
    installation = Installation(
        workflow_version=release.version,
        profile=profile,
        upstream=release.upstream,
        installed_at=stamp,
        updated_at=stamp,
    )

    for artifact in release.payload_artifacts(profile):
        _write(target / artifact.target_path, release.read(artifact.location), artifact.executable)
        installation.managed[artifact.target_path] = {
            "sha256": artifact.sha256,
            "executable": artifact.executable,
        }

    templates = {t["target_path"]: t for t in release.templates()}
    for rel in STATE_TEMPLATES:
        template = templates[rel]
        data = release.read(template["location"])
        path = target / rel
        if path.exists():
            # Pre-existing repository state is never clobbered by a bootstrap.
            installation.generated[rel] = {"sha256": sha256(path.read_bytes()),
                                           "source": "pre-existing"}
            continue
        _write(path, data)
        installation.generated[rel] = {"sha256": template["sha256"], "source": "template"}

    _apply_merges(target, release, templates, installation)
    installation.write(target)
    return installation


def _apply_merges(target: Path, release: Release, templates: dict,
                  installation: Installation) -> list[str]:
    """Contribute the Workflow's sections to the two shared files.

    Returns only the merges that actually altered a file, so re-running an
    update on an unchanged release reports no change rather than claiming one.
    """
    changes: list[str] = []

    fragment = release.read(templates[GITIGNORE_TEMPLATE]["location"])
    merged, action = merge_gitignore(target, fragment)
    if action != "unchanged":
        _write(target / ".gitignore", merged)
        changes.append(f"{action} .gitignore workflow entries")
    installation.merged[".gitignore"] = {
        "fragment_sha256": templates[GITIGNORE_TEMPLATE]["sha256"],
        "action": action,
    }

    managed_section = release.read(templates[CLAUDE_TEMPLATE]["location"])
    path = target / "CLAUDE.md"
    before = path.read_bytes() if path.exists() else None
    merged, action = merge_claude_md(target, managed_section)
    if merged != before:
        _write(path, merged)
        changes.append(f"{action} managed CLAUDE.md section")
    installation.merged["CLAUDE.md"] = {
        "managed_section_sha256": sha256(managed_claude_section(managed_section)),
        "action": action,
    }
    return changes


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update(target: Path, release: Release, profile: str | None = None,
           force: bool = False, now: str | None = None) -> tuple[Installation, list[str]]:
    """Move a managed repository to `release`.

    Returns the new installation record and a list of the changes made.
    Repository-local state is never rewritten; a locally modified managed file
    stops the update unless `force` is set, so an edit someone made on purpose
    is not thrown away without being seen.
    """
    target = Path(target)
    if not is_managed(target):
        raise NotManagedError(
            f"{target} is not a managed repository; use bootstrap() first"
        )
    current = Installation.read(target)
    profile = profile or current.profile
    if profile not in INSTALL_PROFILES:
        raise InstallError(f"unknown install profile {profile!r}")

    if not force:
        modified = [d for d in _drift_against_installed(target, current) if d.kind == "modified"]
        if modified:
            raise DriftError(
                "refusing to update: these managed files were modified locally and would be "
                "overwritten:\n  " + "\n  ".join(str(d) for d in modified),
                modified,
            )

    stamp = now or _now()
    updated = Installation(
        workflow_version=release.version,
        profile=profile,
        upstream=release.upstream,
        installed_at=current.installed_at,
        updated_at=stamp,
        generated=dict(current.generated),
        merged=dict(current.merged),
    )

    changes: list[str] = []
    incoming = {a.target_path: a for a in release.payload_artifacts(profile)}

    for rel in sorted(set(current.managed) - set(incoming)):
        path = target / rel
        if path.exists():
            path.unlink()
            _prune_empty_parents(path, target)
            changes.append(f"removed {rel}")

    for rel, artifact in sorted(incoming.items()):
        path = target / rel
        data = release.read(artifact.location)
        before = path.read_bytes() if path.exists() else None
        if before != data:
            _write(path, data, artifact.executable)
            changes.append(("added " if before is None else "updated ") + rel)
        elif artifact.executable and not path.stat().st_mode & 0o111:
            path.chmod(0o755)
            changes.append(f"fixed mode {rel}")
        updated.managed[rel] = {"sha256": artifact.sha256, "executable": artifact.executable}

    templates = {t["target_path"]: t for t in release.templates()}
    for rel in STATE_TEMPLATES:
        path = target / rel
        if path.exists():
            continue
        # A state file the repository never had (or deleted) is created from
        # the new release's template. An existing one is left untouched.
        _write(path, release.read(templates[rel]["location"]))
        updated.generated[rel] = {"sha256": templates[rel]["sha256"], "source": "template"}
        changes.append(f"created missing state {rel}")

    changes += _apply_merges(target, release, templates, updated)
    updated.write(target)
    return updated, changes


def _drift_against_installed(target: Path, installation: Installation) -> list[Drift]:
    """Drift measured against the record alone -- used by `update` before a
    release is applied, when the *installed* digests are the right baseline."""
    found = []
    for rel, record in sorted(installation.managed.items()):
        path = target / rel
        if not path.exists():
            found.append(Drift(rel, "missing"))
        elif sha256(path.read_bytes()) != record["sha256"]:
            found.append(Drift(rel, "modified"))
    return found


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@dataclass
class Status:
    managed: bool
    workflow_version: str | None = None
    profile: str | None = None
    problems: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.managed:
            return "not a managed repository"
        head = f"workflow {self.workflow_version} ({self.profile} profile)"
        if not self.problems:
            return f"{head} — clean"
        return f"{head} — {len(self.problems)} problem(s):\n  " + "\n  ".join(self.problems)


def status(target: Path, release: Release | None = None) -> Status:
    target = Path(target)
    if not is_managed(target):
        return Status(managed=False, problems=[])
    installation = Installation.read(target)
    problems = verify(target, release) if release is not None else []
    return Status(
        managed=True,
        workflow_version=installation.workflow_version,
        profile=installation.profile,
        problems=problems,
    )


def uninstall(target: Path) -> list[str]:
    """Remove managed payload files and the installation record.

    Repository-local state stays: uninstalling the tooling is not a reason to
    delete a repository's work-item history.
    """
    target = Path(target)
    installation = Installation.read(target)
    removed = []
    for rel in sorted(installation.managed):
        path = target / rel
        if path.exists():
            path.unlink()
            _prune_empty_parents(path, target)
            removed.append(rel)
    shutil.rmtree(target / ".workflow-manager", ignore_errors=True)
    return removed
