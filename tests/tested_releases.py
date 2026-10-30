"""The tested set: the pinned releases plus the lock file's (plan 3.5, `D-Lock`).

What a run tests is data in the repository, never what the network says that
day. `tests/tested_releases.json` lists Workflow releases published after the
last pin, with their digests; the tested set is the pins plus those entries.
The lock is test data: it is not shipped in the wheel and the CLI never reads
it. This module is the one reader, shared by `tests/support.py`, the runner's
priming, `tools/release_lock.py` and the self-verify of `tools/release/package.py`. It imports only the standard library and
`workflow_manager`, and runs with `src/` on the path.

`WORKFLOW_MANAGER_TESTED_RELEASES=<path>` replaces the lock file for a run (the
nightly's, which adds the newest published release); pull-request and `main`
runs never set it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from workflow_manager import source
from workflow_manager.installation import Installation
from workflow_manager.package import SUMS_NAME, archive_name, file_sha256, manifest_asset_name
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


#: The cause `lock_conformance` and `support` both lead with.
NO_SUITE_COUNTS = "neither its manifest nor its lock entry carries the frozen suite counts"


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
        raise LockError(f"{entry.version}: {NO_SUITE_COUNTS} "
                        "(`tools/release_lock.py add` writes them)")
    return dict(entry.suites), tuple(entry.portability_exceptions or ())


#: A command that puts every tested release in the release cache and runs
#: nothing else (every runner mode but `--restore-barrier` primes first).
PRIME_COMMAND = "python3 tests/run_all.py --list"


def self_verify_env(repo_root: Path, workdir: Path, environ=None) -> dict[str, str]:
    """The environment of `workflow-manager verify <repo_root>` in this
    repository's own self-checks (`tools/release/package.py`, the runner's
    `TestManagedWorkflowUntouched`): `environ` with discovery off, so a release
    published since cannot change the proof (plan 3.5, RA-E1).

    When the checkout's installation records a tested release that has no pin
    (a lock entry), discovery is on, but its only source is a directory under
    `workdir` holding that release's three assets, copied from an entry of the
    release cache that is already complete under the lock's digests and checked
    against them again once copied, with a private cache under `workdir`. Any
    other recorded version stays pinned-only, so `verify` refuses it as
    unpinned. This never fetches: a missing or invalid entry is a `LockError`
    naming the priming the cache needs first (#56).
    `workdir` must not hold a `mirror` or `cache` directory yet."""
    environ = dict(os.environ if environ is None else environ)
    env = {**environ, source.PINNED_ONLY_ENV: "1"}
    try:
        version = Installation.read(Path(repo_root)).workflow_version
    except (OSError, ValueError, RuntimeError):
        return env  # `verify` reports the record itself
    pins = source.load_pins()
    lock = load_lock(lock_path(environ))
    if version in pins.releases or version not in lock:
        return env
    pin = lock[version].pin()
    # No source: the cache is only read, never filled (#56).
    cache = source.ReleaseCache(source.cache_root(environ=environ), None, tested_pins(pins, lock))
    if not cache.cached(version):
        raise LockError(
            f"{version}: the release cache {cache.root} holds no complete entry for it under "
            f"the lock's digests, and the self-verify never fetches: prime the tested set into "
            f"it first (`{PRIME_COMMAND}`; `tools/release/package.py` and every runner mode "
            f"prime it before they run)")
    entry = cache.entry(version)
    mirror = Path(workdir) / "mirror"
    (mirror / version).mkdir(parents=True)
    for name in (SUMS_NAME, archive_name(version), manifest_asset_name(version)):
        shutil.copy2(entry / name, mirror / version / name)
    copied = mirror / version
    if source.derive_pin(version, (copied / SUMS_NAME).read_text("utf-8", "replace")) != pin \
            or file_sha256(copied / pin.archive) != pin.sha256 \
            or file_sha256(copied / manifest_asset_name(version)) != pin.manifest_sha256:
        raise LockError(f"{version}: the cached assets do not match the lock's digests")
    env.update({source.SOURCE_ENV: str(mirror), source.PINNED_ONLY_ENV: "0",
                source.CACHE_ENV: str(Path(workdir) / "cache")})
    return env
