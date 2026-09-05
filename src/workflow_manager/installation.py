"""The record a managed repository keeps of what was installed into it.

`.workflow-manager/installation.json` is the only thing that makes a target
repository *recognizable*. Everything else about a bootstrap could be
reconstructed by guessing; the record means nothing has to be.

It holds three separate maps, because the three have different update rules:

`managed`
    Files copied from the release payload. Replaced wholesale on update, and
    compared against the manifest to detect drift.

`generated`
    Files written once from a template. Recorded so drift is *observable*, but
    never replaced: they are the repository's own state from the moment they
    are created.

`merged`
    Files the installer contributes a section to without owning the whole
    file (`.gitignore`, `CLAUDE.md`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

INSTALLATION_DIR = ".workflow-manager"
INSTALLATION_FILE = "installation.json"
SCHEMA_VERSION = 1


def installation_path(target: Path) -> Path:
    return Path(target) / INSTALLATION_DIR / INSTALLATION_FILE


def is_managed(target: Path) -> bool:
    return installation_path(target).exists()


@dataclass
class Installation:
    workflow_version: str
    profile: str
    upstream: dict
    managed: dict = field(default_factory=dict)
    generated: dict = field(default_factory=dict)
    merged: dict = field(default_factory=dict)
    installed_at: str | None = None
    updated_at: str | None = None
    schema_version: int = SCHEMA_VERSION

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Key order is fixed and every map is sorted, so two installs of the
        same release produce identical bytes apart from the timestamps."""
        return {
            "schema_version": self.schema_version,
            "workflow_version": self.workflow_version,
            "profile": self.profile,
            "upstream": self.upstream,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "managed": dict(sorted(self.managed.items())),
            "generated": dict(sorted(self.generated.items())),
            "merged": dict(sorted(self.merged.items())),
        }

    def serialize(self) -> bytes:
        return (json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> "Installation":
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported installation schema_version {data.get('schema_version')!r}; "
                f"this workflow-manager understands {SCHEMA_VERSION}"
            )
        return cls(
            workflow_version=data["workflow_version"],
            profile=data["profile"],
            upstream=data["upstream"],
            managed=dict(data.get("managed", {})),
            generated=dict(data.get("generated", {})),
            merged=dict(data.get("merged", {})),
            installed_at=data.get("installed_at"),
            updated_at=data.get("updated_at"),
        )

    # -- io ----------------------------------------------------------------

    def write(self, target: Path) -> Path:
        path = installation_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.serialize())
        return path

    @classmethod
    def read(cls, target: Path) -> "Installation":
        path = installation_path(target)
        if not path.exists():
            raise FileNotFoundError(
                f"{target} is not a managed repository (no {INSTALLATION_DIR}/{INSTALLATION_FILE})"
            )
        return cls.from_dict(json.loads(path.read_text()))

    # -- queries -----------------------------------------------------------

    @property
    def all_paths(self) -> set[str]:
        return set(self.managed) | set(self.generated) | set(self.merged)
