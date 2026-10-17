"""The tested set: the pinned releases plus the lock file's (plan 3.5, `D-Lock`).

What a run tests is data in the repository, never what the network says that
day. `tests/tested_releases.json` lists Workflow releases published after the
last pin, with their digests; the tested set is the pins plus those entries.
The lock is test data: it is not shipped in the wheel and the CLI never reads
it. This module is the one reader, shared by `tests/support.py`, the runner's
priming and `tools/release_lock.py`. It imports only the standard library and
`workflow_manager`, and runs with `src/` on the path.

`WORKFLOW_MANAGER_TESTED_RELEASES=<path>` replaces the lock file for a run (the
nightly's, which adds the newest published release); pull-request and `main`
runs never set it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from workflow_manager import source
from workflow_manager.package import archive_name
from workflow_manager.release import _version_key, parse_manifest_manager

LOCK_PATH = Path(__file__).with_name("tested_releases.json")
LOCK_SCHEMA_VERSION = 1
OVERRIDE_ENV = "WORKFLOW_MANAGER_TESTED_RELEASES"

_HEX64 = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class LockError(Exception):
    """The lock file is malformed, or contradicts the pins."""


@dataclass(frozen=True)
class LockEntry:
    version: str
    archive: str
    sha256: str
    manifest_sha256: str
    #: Frozen suite counts, present only while the release's manifest lacks the
    #: `conformance` block.
    suites: dict | None = None
    portability_exceptions: tuple | None = None

    def pin(self) -> source.Pin:
        return source.Pin(version=self.version, archive=self.archive, sha256=self.sha256,
                          manifest_sha256=self.manifest_sha256)

    def to_json(self) -> dict:
        data = {"archive": self.archive, "sha256": self.sha256,
                "manifest_sha256": self.manifest_sha256}
        if self.suites is not None:
            data["suites"] = dict(self.suites)
        if self.portability_exceptions is not None:
            data["portability_exceptions"] = [dict(item) for item in self.portability_exceptions]
        return data


def lock_path(environ=None) -> Path:
    """The lock a run reads: the override when set, else the committed file."""
    environ = os.environ if environ is None else environ
    return Path(environ[OVERRIDE_ENV]) if environ.get(OVERRIDE_ENV) else LOCK_PATH


def _parse_entry(version: str, raw) -> LockEntry:
    if not isinstance(raw, dict):
        raise LockError(f"{version}: the entry is not an object")
    unknown = set(raw) - {"archive", "sha256", "manifest_sha256", "suites", "portability_exceptions"}
    if unknown:
        raise LockError(f"{version}: unknown key(s) {sorted(unknown)}")
    if raw.get("archive") != archive_name(version):
        raise LockError(f"{version}: archive {raw.get('archive')!r}")
    for key in ("sha256", "manifest_sha256"):
        digest = raw.get(key)
        if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
            raise LockError(f"{version}: {key} {digest!r}")
    suites = raw.get("suites")
    if suites is not None:
        if not isinstance(suites, dict) or not suites:
            raise LockError(f"{version}: suites must be a non-empty object")
        for name, count in suites.items():
            if not isinstance(name, str) or type(count) is not int or count < 0:
                raise LockError(f"{version}: suite {name!r} needs a non-negative integer count")
    listed = raw.get("portability_exceptions")
    if listed is not None:
        if not isinstance(listed, list):
            raise LockError(f"{version}: portability_exceptions must be a list")
        for item in listed:
            if not isinstance(item, dict) or not all(
                    isinstance(item.get(key), str) for key in ("suite", "test", "reason")):
                raise LockError(f"{version}: a portability exception needs suite, test and reason")
        listed = tuple(listed)
    return LockEntry(version, raw["archive"], raw["sha256"], raw["manifest_sha256"],
                     dict(suites) if suites is not None else None, listed)


def parse_lock(text: str, where: str = "the lock file") -> dict[str, LockEntry]:
    """`{version: LockEntry}`, oldest first. A malformed lock is refused."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LockError(f"{where} is not JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise LockError(f"{where}: needs schema_version {LOCK_SCHEMA_VERSION}")
    if set(data) != {"schema_version", "releases"} or not isinstance(data["releases"], dict):
        raise LockError(f"{where}: needs exactly schema_version and a releases object")
    found = {}
    for version, raw in data["releases"].items():
        if not _VERSION.fullmatch(version):
            raise LockError(f"{where}: {version!r} is not a release version")
        found[version] = _parse_entry(version, raw)
    return {version: found[version] for version in sorted(found, key=_version_key)}


def load_lock(path: Path | None = None) -> dict[str, LockEntry]:
    path = Path(path) if path is not None else lock_path()
    try:
        text = path.read_text()
    except OSError as exc:
        raise LockError(f"cannot read the lock file {path}: {exc}") from exc
    return parse_lock(text, str(path))


def dump_lock(lock: dict[str, LockEntry]) -> str:
    ordered = sorted(lock, key=_version_key)
    return json.dumps({"schema_version": LOCK_SCHEMA_VERSION,
                       "releases": {v: lock[v].to_json() for v in ordered}},
                      indent=2, sort_keys=True) + "\n"


def check_against_pins(lock: dict[str, LockEntry], pins: source.Pins) -> None:
    """A version is in the pins or the lock, never both, and a lock entry is
    newer than every pin (the lock lists releases published after the last one)."""
    newest = pins.versions()[-1] if pins.releases else None
    for version in lock:
        if version in pins.releases:
            raise LockError(f"{version} is both pinned and in the lock file: remove it from the lock")
        if newest is not None and _version_key(version) < _version_key(newest):
            raise LockError(f"{version} is older than the newest pin {newest}: a lock entry "
                            "lists a release published after the last pin")


def tested_pins(pins: source.Pins | None = None,
                lock: dict[str, LockEntry] | None = None) -> source.Pins:
    """The pins plus the lock's entries, as one `Pins`: used only by the test
    tooling (the CLI keeps reading the pin file alone)."""
    pins = pins if pins is not None else source.load_pins()
    lock = lock if lock is not None else load_lock()
    check_against_pins(lock, pins)
    return source.Pins(repository=pins.repository,
                       releases={**pins.releases, **{v: e.pin() for v, e in lock.items()}})


def tested_versions(pins: source.Pins | None = None,
                    lock: dict[str, LockEntry] | None = None) -> list[str]:
    return tested_pins(pins, lock).versions()


def lock_conformance(entry: LockEntry, manifest: bytes | None) -> tuple[dict, tuple[dict, ...]]:
    """`(suites, portability exceptions)` of a lock-only release: its manifest's
    `conformance` block when the manifest carries one (the manifest wins), else
    the lock entry's own data."""
    if manifest is not None:
        block = parse_manifest_manager(manifest)
        if block is not None and block.conformance is not None:
            return (dict(block.conformance.suites),
                    tuple({"suite": item.suite, "test": item.test, "reason": item.reason}
                          for item in block.conformance.portability_exceptions))
    if entry.suites is None:
        raise LockError(f"{entry.version}: neither its manifest nor its lock entry carries "
                        "the frozen suite counts (`tools/release_lock.py add` writes them)")
    return dict(entry.suites), tuple(entry.portability_exceptions or ())
