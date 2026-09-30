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

It also records where the release came from, in an optional `source`:
`{"kind": "package", "repository", "archive", "sha256"}` for bytes bound to a
published package's pin, or `{"kind": "local"}` for an unpublished release
directory. A record written before sources existed has none, and still reads
and writes back unchanged: the field is additive, so `SCHEMA_VERSION` stays 1.

The record is the one thing a target cannot afford to lose, so it is written
by rename rather than in place: an interrupted write leaves the previous
record, never half of the new one.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

INSTALLATION_DIR = ".workflow-manager"
INSTALLATION_FILE = "installation.json"
SCHEMA_VERSION = 1


class CorruptInstallationError(RuntimeError):
    """The installation record exists but cannot be read as one."""


def installation_path(target: Path) -> Path:
    return Path(target) / INSTALLATION_DIR / INSTALLATION_FILE


def is_managed(target: Path) -> bool:
    return installation_path(target).exists()


@dataclass
class Installation:
    workflow_version: str
    profile: str
    upstream: dict
    provenance: dict = field(default_factory=lambda: {"origin": "upstream"})
    managed: dict = field(default_factory=dict)
    generated: dict = field(default_factory=dict)
    merged: dict = field(default_factory=dict)
    installed_at: str | None = None
    updated_at: str | None = None
    source: dict | None = None
    schema_version: int = SCHEMA_VERSION

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Key order is fixed and every map is sorted, so two installs of the
        same release produce identical bytes apart from the timestamps. A
        record without a `source` is written without the key."""
        data = {
            "schema_version": self.schema_version,
            "workflow_version": self.workflow_version,
            "profile": self.profile,
            "upstream": self.upstream,
            "provenance": self.provenance,
        }
        if self.source is not None:
            data["source"] = self.source
        return data | {
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
        if data.get("source") is not None and not isinstance(data["source"], dict):
            raise TypeError("source is not an object")
        return cls(
            workflow_version=data["workflow_version"],
            profile=data["profile"],
            upstream=data["upstream"],
            provenance=data.get("provenance", {"origin": "upstream"}),
            managed=dict(data.get("managed", {})),
            generated=dict(data.get("generated", {})),
            merged=dict(data.get("merged", {})),
            installed_at=data.get("installed_at"),
            updated_at=data.get("updated_at"),
            source=data.get("source"),
        )

    # -- io ----------------------------------------------------------------

    def write(self, target: Path) -> Path:
        """Replace the record atomically.

        `os.replace` on the same filesystem is the whole point: a reader either
        sees the record that was there before or the complete new one. Writing
        in place would let an interruption leave a truncated record, which
        every command reads and none can repair.
        """
        path = installation_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(self.serialize())
        os.replace(tmp, path)
        return path

    @classmethod
    def read(cls, target: Path) -> "Installation":
        path = installation_path(target)
        if not path.exists():
            raise FileNotFoundError(
                f"{target} is not a managed repository (no {INSTALLATION_DIR}/{INSTALLATION_FILE})"
            )
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise TypeError("record is not a JSON object")
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise CorruptInstallationError(
                f"the installation record at {path} is unreadable ({error}). "
                f"Delete {INSTALLATION_DIR}/ and re-run bootstrap to reinstall; "
                f"repository-local state is not stored there and is not affected."
            ) from error

    # -- queries -----------------------------------------------------------

    @property
    def all_paths(self) -> set[str]:
        return set(self.managed) | set(self.generated) | set(self.merged)
