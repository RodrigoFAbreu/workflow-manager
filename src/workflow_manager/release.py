"""Reading a migrated Workflow release from `distribution/`.

A *release* is one immutable directory tree produced by `tools/migrate.py`:

    distribution/workflow/<version>/
        manifest.json   every frozen upstream path's disposition
        payload/        Workflow files, byte-identical to the frozen release
        fixtures/       host documents the frozen conformance suite asserts on
        templates/      clean repository-local initial state

Nothing here reaches outside `distribution/`; a release is self-contained and
verifiable from its own manifest without access to the upstream repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

#: Payload files a target repository needs in order to *operate* the Workflow.
INSTALL_PROFILE_RUNTIME = "runtime"
#: Everything the frozen conformance suite needs as well.
INSTALL_PROFILE_FULL = "full"
INSTALL_PROFILES = (INSTALL_PROFILE_RUNTIME, INSTALL_PROFILE_FULL)

_PROFILE_CATEGORIES = {
    INSTALL_PROFILE_RUNTIME: ("distribution",),
    INSTALL_PROFILE_FULL: ("distribution", "conformance"),
}

#: Templates that become repository-local state in a target: written once when
#: the repository is first managed, and never replaced afterwards. The Workflow
#: writes to all of these at run time, so replacing one would destroy someone's
#: work.
STATE_TEMPLATES = (
    "docs/ai-workflow/WORKFLOW_STATE.json",
    "docs/ai-workflow/WORKFLOW_CONFIG.json",
    "docs/ACTIVE_MILESTONE.md",
)

#: Templates the *release* owns rather than the repository. Nothing in the
#: Workflow writes to these at run time; they exist to run a particular
#: release's suites, so they are installed, replaced and drift-checked exactly
#: like payload files. The category each one belongs to decides which profiles
#: install it -- the conformance CI is pointless in a repository that did not
#: install what it runs.
RELEASE_TEMPLATES = {
    ".github/workflows/workflow-conformance.yml": "conformance",
}

#: Templates contributed as a section to a file the target may already own.
GITIGNORE_TEMPLATE = ".gitignore.workflow-fragment"
CLAUDE_TEMPLATE = "CLAUDE.md"
MERGED_TEMPLATES = (GITIGNORE_TEMPLATE, CLAUDE_TEMPLATE)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReleaseIntegrityError(RuntimeError):
    """Release content on disk does not match the digest its manifest records."""


@dataclass(frozen=True)
class Artifact:
    """One payload, fixture, or release-template file, addressed by where it
    goes in a target."""

    target_path: str
    location: str
    sha256: str
    size: int
    executable: bool
    category: str


class Release:
    def __init__(self, root: Path):
        self.root = Path(root)
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"no manifest at {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text())
        self.version = self.manifest["workflow_version"]
        self.upstream = self.manifest["upstream"]

    # -- artifacts ---------------------------------------------------------

    @property
    def artifacts(self) -> list[Artifact]:
        return [
            Artifact(
                target_path=record["target_path"],
                location=record["location"],
                sha256=record["sha256"],
                size=record["size"],
                executable=record["executable"],
                category=record["category"],
            )
            for record in self.manifest["artifacts"]
        ]

    def payload_artifacts(self, profile: str = INSTALL_PROFILE_FULL) -> list[Artifact]:
        if profile not in INSTALL_PROFILES:
            raise ValueError(f"unknown install profile {profile!r}")
        wanted = _PROFILE_CATEGORIES[profile]
        return [a for a in self.artifacts if a.category in wanted]

    def fixture_artifacts(self) -> list[Artifact]:
        return [a for a in self.artifacts if a.category == "host-evidence"]

    def templates(self) -> list[dict]:
        return list(self.manifest["templates"])

    def release_template_artifacts(self, profile: str = INSTALL_PROFILE_FULL) -> list[Artifact]:
        """Release-owned templates, in the same shape as payload artifacts.

        They are rendered by migration rather than copied byte-for-byte, but a
        target treats them identically: installed from the release, replaced on
        update, and compared against the release when checking for drift.
        """
        if profile not in INSTALL_PROFILES:
            raise ValueError(f"unknown install profile {profile!r}")
        wanted = _PROFILE_CATEGORIES[profile]
        found = []
        for record in self.manifest["templates"]:
            category = RELEASE_TEMPLATES.get(record["target_path"])
            if category is None or category not in wanted:
                continue
            found.append(Artifact(
                target_path=record["target_path"],
                location=record["location"],
                sha256=record["sha256"],
                size=record["size"],
                executable=False,
                category=category,
            ))
        return found

    def installable(self, profile: str = INSTALL_PROFILE_FULL) -> list[Artifact]:
        """Everything a target installs *from the release* under `profile`.

        The single set `bootstrap`, `update` and `drift` all work from, so the
        three cannot disagree about what the release owns.
        """
        return self.payload_artifacts(profile) + self.release_template_artifacts(profile)

    def state_templates(self) -> list[dict]:
        """Templates that seed repository-local state, in `STATE_TEMPLATES` order."""
        by_path = {t["target_path"]: t for t in self.manifest["templates"]}
        return [by_path[rel] for rel in STATE_TEMPLATES]

    # -- content -----------------------------------------------------------

    def read(self, location: str) -> bytes:
        return (self.root / location).read_bytes()

    def read_verified(self, location: str, expected_sha256: str) -> bytes:
        """Release bytes, checked against the manifest before they are used.

        Installing is the moment the release's identity is asserted to a target
        repository. A `distribution/` that was damaged, partially checked out,
        or edited must not be able to pass itself off as the release it claims
        to be, so nothing is copied out of one without this check.
        """
        data = self.read(location)
        actual = sha256(data)
        if actual != expected_sha256:
            raise ReleaseIntegrityError(
                f"release {self.version} is damaged: {location} has digest {actual[:12]}, "
                f"its manifest records {expected_sha256[:12]}. "
                f"Re-derive it with tools/migrate.py before installing."
            )
        return data

    def verify(self) -> list[str]:
        """Every manifest entry present on disk with the recorded digest.

        Returns the list of problems; empty means the release is intact.
        """
        problems = []
        recorded = {}
        for record in self.manifest["artifacts"] + self.manifest["templates"]:
            recorded[record["location"]] = record
            path = self.root / record["location"]
            if not path.exists():
                problems.append(f"missing: {record['location']}")
                continue
            data = path.read_bytes()
            if sha256(data) != record["sha256"]:
                problems.append(f"digest mismatch: {record['location']}")
            if record.get("executable") and not path.stat().st_mode & 0o111:
                problems.append(f"not executable: {record['location']}")
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if rel == "manifest.json" or rel in recorded:
                continue
            if "__pycache__" in path.parts:
                # An interpreter that imported a payload module left bytecode
                # here. It is a build artifact, not release content.
                continue
            problems.append(f"untracked file in release: {rel}")
        return problems


def _version_key(name: str) -> tuple:
    """Order versions numerically where they are numeric, textually where they
    are not, so `2.3.10` sorts after `2.3.9` and anything unexpected still has
    a defined place instead of raising."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"[.\-_]", name)
    )


def release_root(repo_root: Path) -> Path:
    return Path(repo_root) / "distribution" / "workflow"


def available_versions(repo_root: Path) -> list[str]:
    """Every migrated release present, oldest first. Empty if there are none."""
    base = release_root(repo_root)
    if not base.is_dir():
        return []
    names = [p.name for p in base.iterdir() if (p / "manifest.json").exists()]
    return sorted(names, key=_version_key)


def find_release(repo_root: Path, version: str | None = None) -> Release:
    """The release directory for `version`, or the newest one present.

    Defaulting to the newest is what makes adding a second release a matter of
    adding a directory: `bootstrap` and `update` mean "the current release"
    unless an operator pins one. Commands that must speak about a *particular*
    installation resolve the version from the target's own record instead --
    see `cli._release_for_target`.
    """
    base = release_root(repo_root)
    if version is not None:
        return Release(base / version)
    versions = available_versions(repo_root)
    if not versions:
        raise ValueError(f"no migrated release under {base} -- run tools/migrate.py first")
    return Release(base / versions[-1])
