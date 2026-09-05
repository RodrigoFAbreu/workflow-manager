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
#: writes to all of these, so replacing one would destroy someone's work.
STATE_TEMPLATES = (
    "docs/ai-workflow/WORKFLOW_STATE.json",
    "docs/ai-workflow/WORKFLOW_CONFIG.json",
    "docs/ACTIVE_MILESTONE.md",
    ".github/workflows/workflow-conformance.yml",
)

#: Templates contributed as a section to a file the target may already own.
GITIGNORE_TEMPLATE = ".gitignore.workflow-fragment"
CLAUDE_TEMPLATE = "CLAUDE.md"
MERGED_TEMPLATES = (GITIGNORE_TEMPLATE, CLAUDE_TEMPLATE)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Artifact:
    """One payload or fixture file, addressed by where it goes in a target."""

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

    # -- content -----------------------------------------------------------

    def read(self, location: str) -> bytes:
        return (self.root / location).read_bytes()

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


def find_release(repo_root: Path, version: str | None = None) -> Release:
    """The release directory for `version`, or the only one present."""
    base = Path(repo_root) / "distribution" / "workflow"
    if version is not None:
        return Release(base / version)
    candidates = sorted(p for p in base.iterdir() if (p / "manifest.json").exists())
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one release under {base}, found {[p.name for p in candidates]}"
        )
    return Release(candidates[0])
