"""Where Workflow releases come from: source, pins and a verified cache
(`D-Release-Source`, `D-Pins`, `D-Release-Cache`).

A published release is a package (`package.py`) fetched from a *source* -- a
URL template or a local directory -- and accepted only when it matches its
*pin* in `published_releases.json`, the trust root the Manager ships with.
Accepted packages are kept, extracted, in a *cache* shared by every Manager
invocation on the machine. The cache is not trusted: every hit is checked
against the pin again, and every use goes through a private snapshot taken
and checked under the entry's lock, so nothing installed is ever read from a
shared path that could change after it was checked.

A local release directory (`--release-dir`, the `--manager-root` alias and
the checkout fallback) goes through `local_release`, which applies the same
pin to it when its version is published, and treats it as an unpublished
release in development when it is not.
"""

from __future__ import annotations

import atexit
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .install import InstallError
from .package import (
    MANIFEST_NAME,
    SUMS_NAME,
    archive_name,
    extract_package,
    file_sha256,
    manifest_asset_name,
)
from .release import Release, ReleaseIntegrityError, _version_key

PINS_PATH = Path(__file__).with_name("published_releases.json")
PINS_SCHEMA_VERSION = 1

SOURCE_ENV = "WORKFLOW_MANAGER_RELEASE_SOURCE"
CACHE_ENV = "WORKFLOW_MANAGER_RELEASE_CACHE"
DEFAULT_SOURCE = "https://github.com/RodrigoFAbreu/workflow/releases/download/v{version}/"

FETCH_TIMEOUT_SECONDS = 60
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_REDIRECTS = 5
LOOPBACK_HOSTS = ("localhost",)

COMPLETE_NAME = "complete"
TREE_NAME = "tree"

_HEX64 = re.compile(r"[0-9a-f]{64}")


class ReleaseNotPublishedError(InstallError):
    """The version has no pin, so no package of it can be installed.

    `kind` is `none-pinned` (the Manager pins nothing) or `unpinned`."""

    def __init__(self, message: str = "", *, kind: str | None = None):
        super().__init__(message)
        self.kind = kind


class ReleaseUnavailableError(InstallError):
    """The package could not be fetched, and nothing usable is cached.

    `kind` names the cause for `advice`; `version` and `source` are the facts
    its step quotes (the release asked for, the source directory)."""

    def __init__(self, message: str = "", *, kind: str | None = None,
                 version: str | None = None, source: str | None = None):
        super().__init__(message)
        self.kind, self.version, self.source = kind, version, source


def _log(message: str) -> None:
    print(f"workflow-manager: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pin:
    version: str
    archive: str
    sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class Pins:
    repository: str
    releases: dict[str, Pin]

    def get(self, version: str) -> Pin | None:
        return self.releases.get(version)

    def versions(self) -> list[str]:
        """Every pinned version, oldest first."""
        return sorted(self.releases, key=_version_key)

    def source_record(self, version: str) -> dict:
        """The installation record's `source` for bytes bound to this pin."""
        pin = self.releases[version]
        return {"kind": "package", "repository": self.repository,
                "archive": pin.archive, "sha256": pin.sha256}


def load_pins(path: Path = PINS_PATH) -> Pins:
    """The pin file, checked for shape. A malformed one is refused: it is the
    trust root, so guessing what it meant would defeat it."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
        if data["schema_version"] != PINS_SCHEMA_VERSION:
            raise ValueError(f"schema_version {data['schema_version']!r}")
        repository = data["repository"]
        if not isinstance(repository, str) or not repository:
            raise ValueError("repository is not a name")
        releases = {}
        for version, entry in data["releases"].items():
            pin = Pin(version=version, archive=entry["archive"], sha256=entry["sha256"],
                      manifest_sha256=entry["manifest_sha256"])
            if pin.archive != archive_name(version):
                raise ValueError(f"{version}: archive {pin.archive!r}")
            for digest in (pin.sha256, pin.manifest_sha256):
                if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
                    raise ValueError(f"{version}: digest {digest!r}")
            releases[version] = pin
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ReleaseIntegrityError(f"the pin file {path} is malformed: {exc}",
                                    kind="pin-file") from exc
    return Pins(repository=repository, releases=releases)


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_url(url: str) -> None:
    """`https://`, `file://`, or `http://` to a loopback host; nothing else."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme in ("https", "file"):
        return
    if parts.scheme == "http" and _is_loopback(parts.hostname):
        return
    raise ReleaseUnavailableError(
        f"refusing release source {url!r}: use https://, file://, or http:// to a loopback host")


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    """At most `MAX_REDIRECTS`, to any host, never to a weaker scheme."""

    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url).scheme
        new = urllib.parse.urlsplit(newurl).scheme
        if old == "https" and new != "https":
            raise ReleaseUnavailableError(
                f"refusing redirect from {req.full_url} to {newurl}: it drops https",
                kind="source-response")
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ReleaseSource:
    """A URL template with a `{version}` field, or a local directory holding
    `<version>/` subdirectories with the three assets."""

    def __init__(self, value: str):
        self.value = value
        if "://" in value:
            if "{version}" not in value:
                raise ReleaseUnavailableError(
                    f"release source {value!r} has no {{version}} field",
                    kind="no-version-field")
            _check_url(value)
            self.directory = None
        else:
            self.directory = Path(value)

    @classmethod
    def select(cls, option: str | None = None, environ=None) -> ReleaseSource:
        """`--release-source`, else the environment, else the default."""
        environ = os.environ if environ is None else environ
        return cls(option or environ.get(SOURCE_ENV) or DEFAULT_SOURCE)

    def location(self, version: str, name: str) -> str:
        if self.directory is not None:
            return str(self.directory / version / name)
        base = self.value.replace("{version}", urllib.parse.quote(version, safe=""))
        return base.rstrip("/") + "/" + urllib.parse.quote(name)

    def fetch(self, version: str, name: str, dest: Path) -> None:
        """Copy one asset to `dest`, capped at `MAX_ASSET_BYTES`. Any failure
        to obtain it is `ReleaseUnavailableError`."""
        where = self.location(version, name)
        try:
            if self.directory is not None:
                with open(where, "rb") as stream:
                    _copy_capped(stream, dest, where)
                return
            opener = urllib.request.build_opener(_RedirectHandler)
            with opener.open(where, timeout=FETCH_TIMEOUT_SECONDS) as stream:
                _copy_capped(stream, dest, where)
        except ReleaseUnavailableError:
            raise
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise ReleaseUnavailableError(
                f"cannot fetch {where}: {exc}",
                kind="fetch-directory" if self.directory is not None else "fetch-url",
                version=version,
                source=str(self.directory) if self.directory is not None else self.value,
            ) from exc


def _copy_capped(stream, dest: Path, where: str) -> None:
    total = 0
    with open(dest, "wb") as out:
        while chunk := stream.read(1 << 20):
            total += len(chunk)
            if total > MAX_ASSET_BYTES:
                raise ReleaseUnavailableError(
                    f"{where} is larger than {MAX_ASSET_BYTES} bytes", kind="source-response")
            out.write(chunk)


def _parse_sums(path: Path) -> dict[str, str]:
    sums = {}
    for line in path.read_text("utf-8", "replace").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        if match is None:
            raise ReleaseIntegrityError(f"{path.name} has a malformed line {line!r}",
                                        kind="digest")
        sums[match.group(2)] = match.group(1)
    return sums


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class SnapshotRelease(Release):
    """A `Release` read from a private copy that this invocation owns.

    `source` is the installation record's `source` for these bytes. The copy
    is removed by `close()` (or leaving the `with` block), and at interpreter
    exit as a backstop.
    """

    def __init__(self, root: Path, source: dict):
        super().__init__(root)
        self.source = source
        atexit.register(self.close)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        atexit.unregister(self.close)

    def __enter__(self) -> SnapshotRelease:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _copy_snapshot(tree: Path, dir: Path | None = None) -> Path:
    """The manifest-enumerated files of `tree`, copied into a fresh private
    directory with the modes the manifest records. The manifest is read from
    the copy, so the files copied are the ones the copied manifest names.

    `dir` is the parent of the fresh directory. The default is `tempfile`'s own
    choice; the read-only commands pass one they validated, so no probe file is
    ever written where `tempfile` would have looked."""
    snapshot = Path(tempfile.mkdtemp(prefix="workflow-release-", dir=dir))
    try:
        os.chmod(snapshot, 0o700)
        shutil.copyfile(tree / MANIFEST_NAME, snapshot / MANIFEST_NAME)
        manifest = json.loads((snapshot / MANIFEST_NAME).read_text())
        for record in manifest["artifacts"] + manifest["templates"]:
            location = record["location"]
            if not isinstance(location, str):
                raise ReleaseIntegrityError(
                    f"manifest.json at {tree} is malformed: a location that is not text "
                    f"({location!r})", kind="manifest-shape")
            parts = location.split("/")
            if location.startswith("/") or any(p in ("", ".", "..") for p in parts):
                raise ReleaseIntegrityError(f"unsafe manifest location {location!r}",
                                            kind="local-release")
            source = tree / location
            if source.is_symlink():
                raise ReleaseIntegrityError(f"{location} is a link", kind="local-release")
            dest = snapshot / location
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            os.chmod(dest, 0o755 if record.get("executable") else 0o644)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise ReleaseIntegrityError(f"cannot snapshot the release at {tree}: {exc}",
                                    kind="local-release") from exc
    except BaseException:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise
    return snapshot


def _snapshot_problems(snapshot: Path, version: str, manifest_sha256: str | None) -> list[str]:
    """Why `snapshot` is not release `version` bound to `manifest_sha256`
    (`None`: bound to its own manifest only). Empty means it is."""
    actual = file_sha256(snapshot / MANIFEST_NAME)
    if manifest_sha256 is not None and actual != manifest_sha256:
        return [f"manifest.json has digest {actual}, the pin records {manifest_sha256}"]
    try:
        release = Release(snapshot)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"unreadable manifest: {exc}"]
    if release.version != version:
        return [f"manifest names release {release.version!r}, not {version!r}"]
    return release.verify()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def cache_root(option: str | None = None, environ=None) -> Path:
    """`--release-cache`, else the environment, else the XDG cache directory."""
    environ = os.environ if environ is None else environ
    if option:
        return Path(option)
    if environ.get(CACHE_ENV):
        return Path(environ[CACHE_ENV])
    if environ.get("XDG_CACHE_HOME"):
        return Path(environ["XDG_CACHE_HOME"]) / "workflow-manager" / "releases"
    return Path.home() / ".cache" / "workflow-manager" / "releases"


class ReleaseCache:
    """Verified, extracted packages under `<root>/<version>/`: the three
    assets, `tree/` and `complete` (the archive digest, written last)."""

    #: Test seam: called with (snapshot, entry) between the snapshot copy and
    #: the snapshot check, to stand in for a writer that ignores the lock.
    _after_snapshot_copy: Callable[[Path, Path], None] | None = None

    def __init__(self, root: Path, source: ReleaseSource, pins: Pins):
        self.root = Path(root)
        self.source = source
        self.pins = pins

    def entry(self, version: str) -> Path:
        return self.root / version

    def cached(self, version: str) -> bool:
        """Whether the entry holds the pinned package (no network, no lock)."""
        pin = self._pin(version)
        return self._is_hit(self.entry(version), pin)

    def _pin(self, version: str) -> Pin:
        pin = self.pins.get(version)
        if pin is None:
            raise ReleaseNotPublishedError(
                f"release {version} is not published: this Manager has no pin for it "
                f"(pinned: {', '.join(self.pins.versions()) or 'none'})", kind="unpinned")
        return pin

    @contextmanager
    def _locked(self, version: str, read_only: bool = False) -> Iterator[None]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if read_only:
                # A lock leaf that is, or becomes, a link fails (ELOOP) instead
                # of redirecting the write.
                flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
                handle = os.fdopen(os.open(self.root / f"{version}.lock", flags, 0o666), "a")
            else:
                handle = open(self.root / f"{version}.lock", "a")
        except OSError as exc:
            raise ReleaseUnavailableError(
                f"cannot use the release cache {self.root}: {exc} "
                f"(choose another with --release-cache or ${CACHE_ENV})",
                kind="cache-unusable") from exc
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _is_hit(self, entry: Path, pin: Pin) -> bool:
        try:
            if (entry / COMPLETE_NAME).read_text().strip() != pin.sha256:
                return False
            if file_sha256(entry / pin.archive) != pin.sha256:
                return False
            tree = entry / TREE_NAME
            if file_sha256(tree / MANIFEST_NAME) != pin.manifest_sha256:
                return False
            release = Release(tree)
            return release.version == pin.version and not release.verify()
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _discard(self, entry: Path, why: str) -> None:
        if entry.exists() or entry.is_symlink():
            _log(f"discarding cache entry {entry}: {why}")
            try:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except OSError as exc:
                raise ReleaseUnavailableError(
                    f"cannot discard the cache entry {entry} ({why}): {exc}. Remove it "
                    f"by hand, or choose another cache with --release-cache or "
                    f"${CACHE_ENV}", kind="cache-unusable") from exc

    def _fetch(self, pin: Pin) -> None:
        """Fetch, check and extract the package into a temporary sibling of
        the entry, then rename it into place. The entry must be absent."""
        version = pin.version
        staging = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=self.root))
        try:
            sums_path = staging / SUMS_NAME
            self.source.fetch(version, SUMS_NAME, sums_path)
            archive = staging / pin.archive
            self.source.fetch(version, pin.archive, archive)
            manifest_name = manifest_asset_name(version)
            manifest = staging / manifest_name
            self.source.fetch(version, manifest_name, manifest)

            sums = _parse_sums(sums_path)
            archive_digest = file_sha256(archive)
            if archive_digest != pin.sha256 or sums.get(pin.archive) != pin.sha256:
                raise ReleaseIntegrityError(
                    f"release {version}'s archive does not match its pin: downloaded "
                    f"{archive_digest}, {SUMS_NAME} lists {sums.get(pin.archive)}, "
                    f"the pin records {pin.sha256}", kind="digest")
            manifest_digest = file_sha256(manifest)
            if manifest_digest != pin.manifest_sha256 or \
                    sums.get(manifest_name) != pin.manifest_sha256:
                raise ReleaseIntegrityError(
                    f"release {version}'s manifest asset does not match its pin: downloaded "
                    f"{manifest_digest}, {SUMS_NAME} lists {sums.get(manifest_name)}, "
                    f"the pin records {pin.manifest_sha256}", kind="digest")

            extract_package(archive, staging / TREE_NAME, version)
            if file_sha256(staging / TREE_NAME / MANIFEST_NAME) != pin.manifest_sha256:
                raise ReleaseIntegrityError(
                    f"release {version}'s archive carries a manifest other than the pinned one",
                    kind="digest")
            (staging / COMPLETE_NAME).write_text(pin.sha256 + "\n")
            os.rename(staging, self.entry(version))
        except OSError as exc:
            raise ReleaseUnavailableError(
                f"cannot store release {version} in the cache {self.root}: {exc}",
                kind="cache-store") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _ensure_locked(self, pin: Pin) -> None:
        entry = self.entry(pin.version)
        if self._is_hit(entry, pin):
            return
        self._discard(entry, "it does not match the pin")
        self._fetch(pin)

    def ensure(self, version: str) -> Path:
        """Make the entry hold the pinned package, fetching only on a miss.
        Returns the entry. Installs nothing, so it takes no snapshot."""
        pin = self._pin(version)
        with self._locked(version):
            self._ensure_locked(pin)
        return self.entry(version)

    def resolve(self, version: str, *, snapshot_parent: Path | None = None,
                read_only: bool = False) -> SnapshotRelease:
        """The pinned release, from a private snapshot verified under the lock.

        `snapshot_parent` and `read_only` are the read-only commands' (3.6):
        the validated parent of the snapshot, and the no-follow lock leaf.

        A snapshot that fails its check discards the entry and refetches once:
        `ReleaseUnavailableError` when that refetch cannot be made,
        `ReleaseIntegrityError` when its snapshot fails too.
        """
        pin = self._pin(version)
        with self._locked(version, read_only):
            self._ensure_locked(pin)
            for attempt in (1, 2):
                entry = self.entry(version)
                try:
                    snapshot = _copy_snapshot(entry / TREE_NAME, snapshot_parent)
                except ReleaseIntegrityError as exc:
                    snapshot, problems = None, [str(exc)]
                else:
                    try:
                        if self._after_snapshot_copy is not None:
                            self._after_snapshot_copy(snapshot, entry)
                        problems = _snapshot_problems(snapshot, version, pin.manifest_sha256)
                    except BaseException:
                        shutil.rmtree(snapshot, ignore_errors=True)
                        raise
                    if not problems:
                        return SnapshotRelease(snapshot, self.pins.source_record(version))
                    shutil.rmtree(snapshot, ignore_errors=True)
                if attempt == 2:
                    raise ReleaseIntegrityError(
                        f"release {version}'s cache entry changed while it was being copied, "
                        f"twice: {'; '.join(problems)}", kind="cache-changed")
                self._discard(entry, "it changed while it was being copied: "
                              + "; ".join(problems))
                self._fetch(pin)
        raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# Local directories
# ---------------------------------------------------------------------------


def local_release(directory: Path, requested_version: str | None, pins: Pins,
                  snapshot_parent: Path | None = None) -> SnapshotRelease:
    """An unpackaged release directory, under the pin rule (INV-2).

    Its own manifest's version `V` must equal `requested_version` when one is
    given. A pinned `V` must match its pin's `manifest_sha256`, and is then
    recorded as the package it is a copy of; an unpinned `V` is an unpublished
    release, checked against its own manifest and recorded as local. Either
    way it is used through a verified private snapshot.
    """
    directory = Path(directory)
    try:
        version = Release(directory).version
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReleaseIntegrityError(f"{directory} is not a release: {exc}",
                                    kind="local-release") from exc
    if requested_version is not None and version != requested_version:
        raise ReleaseIntegrityError(
            f"{directory} holds release {version}, not the requested {requested_version}",
            kind="local-release")
    try:
        hash(version)
    except TypeError:
        raise ReleaseIntegrityError(
            f"manifest.json at {directory} is malformed: workflow_version is a "
            f"{type(version).__name__}, not text", kind="manifest-shape") from None
    pin = pins.get(version)
    if pin is not None:
        actual = file_sha256(directory / MANIFEST_NAME)
        if actual != pin.manifest_sha256:
            raise ReleaseIntegrityError(
                f"{directory} claims published release {version}, but its manifest.json "
                f"has digest {actual} and the pin records {pin.manifest_sha256}",
                kind="local-release")
        source = pins.source_record(version)
    else:
        source = {"kind": "local"}
    snapshot = _copy_snapshot(directory, snapshot_parent)
    problems = _snapshot_problems(snapshot, version, pin.manifest_sha256 if pin else None)
    if problems:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise ReleaseIntegrityError(
            f"release {version} at {directory} fails verification: " + "; ".join(problems),
            kind="local-release")
    if pin is not None:
        _log(f"using a local copy of published release {version} from {directory}")
    return SnapshotRelease(snapshot, source)
