"""Bootstrap, update, and verify a managed repository.

The whole module is arranged around one rule: **canonical distribution
content is replaced, repository-local state is not.** Every function here
either respects that rule or refuses.

Three operations:

`bootstrap`
    A repository that has never used the Workflow. Installs everything the
    release owns, writes clean state from templates, merges the two shared
    files, and records what it did. Refuses if the repository already has a
    file of its own where a release file goes, unless told to overwrite.

`update`
    A managed repository moving from one release to another. Replaces
    release-owned files, removes the ones the new release dropped, and leaves
    every generated state file exactly as it is. Refuses if a release-owned
    file was edited locally, unless told to discard those edits.

`verify` / `drift`
    Compares what is on disk against the release manifest and the installation
    record. This is what makes an update safe rather than hopeful: it runs
    before the update decides anything.

Neither operation is atomic -- a repository is not a database, and pretending
otherwise would be a lie with a rollback path in it. Both are instead
*re-runnable*: every write is idempotent, so an interrupted operation is
repaired by running the same command again. `docs/ARCHITECTURE.md` states the
contract that follows from that, and `tests/test_bootstrap.py` interrupts each
operation at every write to prove it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .installation import INSTALLATION_DIR, Installation, is_managed
from .release import (
    CLAUDE_TEMPLATE,
    GITIGNORE_TEMPLATE,
    INSTALL_PROFILE_FULL,
    INSTALL_PROFILES,
    Artifact,
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


class CollisionError(InstallError):
    """The repository already has its own file where a release file goes."""

    def __init__(self, message: str, collisions: list["Drift"]):
        super().__init__(message)
        self.collisions = collisions


class DriftError(InstallError):
    def __init__(self, message: str, drifted: list["Drift"]):
        super().__init__(message)
        self.drifted = drifted


@dataclass(frozen=True)
class Drift:
    path: str
    kind: str          # "modified" | "missing" | "unexpected" | "not-executable"
                       # | "occupied"
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


def _collisions(target: Path, incoming: dict[str, Artifact],
                already_ours: frozenset[str] | set[str] = frozenset()) -> list[Drift]:
    """Release paths the repository already occupies with something else.

    A path holding exactly the bytes the release is about to write is not a
    collision -- that is what makes an interrupted install re-runnable. A path
    the record already claims is not one either; that is drift, and `update`
    judges it against the record. A path that is not a file at all is always
    reported, recorded or not: nothing here can write through a directory, and
    saying so beats failing part-way with a traceback.
    """
    found = []
    for rel in sorted(incoming):
        path = target / rel
        if not path.exists():
            continue
        if not path.is_file():
            found.append(Drift(rel, "occupied", "a directory is in the way"))
        elif rel in already_ours:
            continue
        elif sha256(path.read_bytes()) != incoming[rel].sha256:
            found.append(Drift(rel, "occupied", "the repository has its own file here"))
    return found


def _merged_drift(target: Path, release: Release, templates: dict,
                  installation: Installation) -> list[Drift]:
    """What became of the two files the installer only contributes *part* of.

    It does not own either file, so it cannot compare them whole. What it can
    check is that its own contribution is still there -- and it must, because
    losing it is silent and expensive: without the ignore lines a repository
    starts tracking `.ai-review/`, the Workflow's live runtime workspace.
    """
    found: list[Drift] = []

    if ".gitignore" in installation.merged:
        fragment = release.read(templates[GITIGNORE_TEMPLATE]["location"])
        wanted = [
            line for line in fragment.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        path = target / ".gitignore"
        present = set(path.read_bytes().decode("utf-8", "replace").splitlines()) \
            if path.is_file() else set()
        gone = [line for line in wanted if line not in present]
        if gone:
            found.append(Drift(".gitignore", "modified",
                               "workflow entries removed: " + ", ".join(gone)))

    if "CLAUDE.md" in installation.merged:
        expected = sha256(managed_claude_section(
            release.read(templates[CLAUDE_TEMPLATE]["location"])))
        path = target / "CLAUDE.md"
        if not path.is_file():
            found.append(Drift("CLAUDE.md", "missing", "the managed section is gone"))
        elif sha256(managed_claude_section(path.read_bytes())) != expected:
            found.append(Drift("CLAUDE.md", "modified",
                               "the managed section differs from the release's"))
    return found


def _other_written_paths(release: Release) -> set[str]:
    """Target paths an operation writes that are not release artifacts: the
    state templates it may create and the two files it merges into."""
    return {t["target_path"] for t in release.state_templates()} | {".gitignore", "CLAUDE.md"}


def _blocked_paths(target: Path, paths: set[str]) -> list[Drift]:
    """Paths an operation must write through that are not files.

    Nothing here can write a file where a directory stands, so the operation
    says so up front instead of failing part-way through. Unlike a collision,
    this is not something `force` can decide its way past.
    """
    found = []
    for rel in sorted(paths):
        path = target / rel
        if path.exists() and not path.is_file():
            found.append(Drift(rel, "occupied", "a directory is in the way"))
    return found


def drift(target: Path, release: Release) -> list[Drift]:
    """Every difference between the target and what the record says is there.

    Release-owned files are compared against the *release manifest*, so a drift
    is "this differs from canonical", not merely "this changed since install".
    Generated files are compared against the record, since canonical has no
    opinion about them after they are created. Merged files are compared only
    over the part the installer contributed.
    """
    target = Path(target)
    installation = Installation.read(target)
    manifest_digests = {a.target_path: a for a in release.installable(installation.profile)}
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

    for rel in sorted(installation.generated):
        if not (target / rel).exists():
            found.append(Drift(rel, "missing", "repository-local state was deleted"))

    for rel in sorted(set(manifest_digests) - set(installation.managed)):
        if (target / rel).exists():
            found.append(Drift(rel, "unexpected", "present but not recorded as installed"))

    templates = {t["target_path"]: t for t in release.templates()}
    found += _merged_drift(target, release, templates, installation)

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
              force: bool = False, now: str | None = None) -> Installation:
    """Install the Workflow into a repository that has never used it.

    Refuses if the repository already keeps its own file where a release file
    goes -- `.claude/commands/` and `scripts/` are ordinary names, and a
    bootstrap that quietly replaced what it found there would destroy work no
    one asked it to touch. `force` overwrites those paths.
    """
    target = Path(target)
    if profile not in INSTALL_PROFILES:
        raise InstallError(f"unknown install profile {profile!r}")
    if not target.is_dir():
        raise InstallError(f"no directory at {target}")
    if not (target / ".git").exists():
        raise InstallError(f"{target} is not a Git repository")
    if is_managed(target):
        # Reading it first means a damaged record reports itself, with the
        # remedy, instead of being turned away with advice that cannot work.
        Installation.read(target)
        raise AlreadyManagedError(
            f"{target} is already managed; use update() to move it to another release"
        )

    incoming = {a.target_path: a for a in release.installable(profile)}
    occupied = [] if force else _collisions(target, incoming)
    occupied += _blocked_paths(target, _other_written_paths(release))
    if occupied:
        raise CollisionError(
            "refusing to bootstrap: the repository already has its own file at these "
            "release paths:\n  " + "\n  ".join(str(c) for c in occupied),
            occupied,
        )

    stamp = now or _now()
    installation = Installation(
        workflow_version=release.version,
        profile=profile,
        upstream=release.upstream,
        provenance=release.provenance,
        installed_at=stamp,
        updated_at=stamp,
    )

    for rel, artifact in sorted(incoming.items()):
        _write(target / rel, release.read_verified(artifact.location, artifact.sha256),
               artifact.executable)
        installation.managed[rel] = {
            "sha256": artifact.sha256,
            "executable": artifact.executable,
        }

    templates = {t["target_path"]: t for t in release.templates()}
    for template in release.state_templates():
        rel = template["target_path"]
        path = target / rel
        if path.exists():
            # Pre-existing repository state is never clobbered by a bootstrap.
            existing = sha256(path.read_bytes())
            installation.generated[rel] = {
                "sha256": existing,
                # Byte-identical to the template means an earlier run of this
                # bootstrap wrote it, not that the repository brought its own.
                "source": "template" if existing == template["sha256"] else "pre-existing",
            }
            continue
        _write(path, release.read_verified(template["location"], template["sha256"]))
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

    fragment = release.read_verified(templates[GITIGNORE_TEMPLATE]["location"],
                                     templates[GITIGNORE_TEMPLATE]["sha256"])
    merged, action = merge_gitignore(target, fragment)
    if action != "unchanged":
        _write(target / ".gitignore", merged)
        changes.append(f"{action} .gitignore workflow entries")
    installation.merged[".gitignore"] = {
        "fragment_sha256": templates[GITIGNORE_TEMPLATE]["sha256"],
        "action": action,
    }

    managed_section = release.read_verified(templates[CLAUDE_TEMPLATE]["location"],
                                            templates[CLAUDE_TEMPLATE]["sha256"])
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
    Repository-local state is never rewritten; a locally modified release file
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

    incoming = {a.target_path: a for a in release.installable(profile)}

    if not force:
        modified = _local_modifications(target, current, incoming)
        if modified:
            raise DriftError(
                "refusing to update: these release files were modified locally and would be "
                "overwritten:\n  " + "\n  ".join(str(d) for d in modified),
                modified,
            )
    occupied = [] if force else _collisions(target, incoming, already_ours=set(current.managed))
    occupied += _blocked_paths(
        target,
        _other_written_paths(release) | (set(current.managed) - set(incoming)),
    )
    if occupied:
        raise CollisionError(
            "refusing to update: this release needs paths the repository is using for "
            "something else:\n  " + "\n  ".join(str(c) for c in occupied),
            occupied,
        )

    stamp = now or _now()
    updated = Installation(
        workflow_version=release.version,
        profile=profile,
        upstream=release.upstream,
        provenance=release.provenance,
        installed_at=current.installed_at,
        updated_at=stamp,
        # A path the release has taken ownership of since the target was
        # installed stops being repository-local state; leaving a stale
        # `generated` entry behind would record it as both.
        generated={rel: rec for rel, rec in current.generated.items() if rel not in incoming},
        merged=dict(current.merged),
    )

    changes: list[str] = []

    for rel in sorted(set(current.managed) - set(incoming)):
        path = target / rel
        if path.is_file():
            path.unlink()
            _prune_empty_parents(path, target)
            changes.append(f"removed {rel}")

    for rel, artifact in sorted(incoming.items()):
        path = target / rel
        data = release.read_verified(artifact.location, artifact.sha256)
        before = path.read_bytes() if path.is_file() else None
        if before != data:
            _write(path, data, artifact.executable)
            changes.append(("added " if before is None else "updated ") + rel)
        elif artifact.executable and not path.stat().st_mode & 0o111:
            path.chmod(0o755)
            changes.append(f"fixed mode {rel}")
        updated.managed[rel] = {"sha256": artifact.sha256, "executable": artifact.executable}

    templates = {t["target_path"]: t for t in release.templates()}
    for template in release.state_templates():
        rel = template["target_path"]
        path = target / rel
        if path.exists():
            continue
        # A state file the repository never had (or deleted) is created from
        # the new release's template. An existing one is left untouched.
        _write(path, release.read_verified(template["location"], template["sha256"]))
        updated.generated[rel] = {"sha256": template["sha256"], "source": "template"}
        changes.append(f"created missing state {rel}")

    changes += _apply_merges(target, release, templates, updated)
    updated.write(target)
    return updated, changes


def _local_modifications(target: Path, installation: Installation,
                         incoming: dict[str, Artifact]) -> list[Drift]:
    """Release files that were edited locally and that this update would lose.

    Measured against the record, because the *installed* digests are what the
    repository agreed to. A file already holding the incoming release's bytes
    is excluded: that is a half-applied update, not someone's edit, and
    treating it as an edit would leave an interrupted update repairable only
    by `--force` -- which discards edits, the very thing the check protects.
    """
    found = []
    for rel, record in sorted(installation.managed.items()):
        path = target / rel
        if not path.is_file():
            continue
        digest = sha256(path.read_bytes())
        if digest == record["sha256"]:
            continue
        arriving = incoming.get(rel)
        if arriving is not None and digest == arriving.sha256:
            continue
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
    #: False when no release was available to check against. An unverified
    #: installation is never described as clean: saying "clean" without having
    #: looked is the one answer this command must not be able to give.
    verified: bool = False

    def __str__(self) -> str:
        if not self.managed:
            return "not a managed repository"
        head = f"workflow {self.workflow_version} ({self.profile} profile)"
        if self.problems:
            return f"{head} — {len(self.problems)} problem(s):\n  " + "\n  ".join(self.problems)
        if not self.verified:
            return f"{head} — not verified (no release to compare against)"
        return f"{head} — clean"


def status(target: Path, release: Release | None = None) -> Status:
    target = Path(target)
    if not is_managed(target):
        return Status(managed=False, problems=[], verified=True)
    installation = Installation.read(target)
    return Status(
        managed=True,
        workflow_version=installation.workflow_version,
        profile=installation.profile,
        problems=verify(target, release) if release is not None else [],
        verified=release is not None,
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
        # Only files this installer put there. Anything else at that path is
        # the repository's, and uninstalling the tooling is no licence to
        # remove it.
        if path.is_file():
            path.unlink()
            _prune_empty_parents(path, target)
            removed.append(rel)
    shutil.rmtree(target / INSTALLATION_DIR, ignore_errors=True)
    return removed
