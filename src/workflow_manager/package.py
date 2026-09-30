"""A Workflow release as a package: build it, and extract it safely (`D-Package-Format`).

A package for version `V` is three release assets:

    workflow-V.tar.gz           gzip-compressed POSIX tar; one top-level
                                directory, `workflow-V/`, holding exactly the
                                release directory
    workflow-V.manifest.json    a byte copy of that release's manifest.json
    SHA256SUMS                  `sha256sum -c` lines for the two files above

The archive's members come from the release's manifest, never from a
directory walk, and every header field that could vary between builds is
fixed, so building the same release twice gives the same bytes. Extracting
one accepts only what a build could have produced, checks every file against
the manifest it carries, and publishes the tree by `rename`; any failure
raises `ReleaseIntegrityError` and leaves nothing behind.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .release import Release, ReleaseIntegrityError

SUMS_NAME = "SHA256SUMS"
MANIFEST_NAME = "manifest.json"
DIR_MODE = 0o755
EXECUTABLE_MODE = 0o755
FILE_MODE = 0o644
#: A release is about 10 MB unpacked. Anything near this is not a release,
#: and stopping here keeps a crafted archive from filling the disk.
MAX_UNPACKED_BYTES = 256 * 1024 * 1024

_ACCEPTED_FILE_TYPES = (tarfile.REGTYPE, tarfile.AREGTYPE)


def archive_name(version: str) -> str:
    return f"workflow-{version}.tar.gz"


def manifest_asset_name(version: str) -> str:
    return f"workflow-{version}.manifest.json"


def top_directory(version: str) -> str:
    return f"workflow-{version}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256sums_text(files: Iterable[Path]) -> str:
    """`sha256sum`'s text format (`<hex>  <name>`), one line per file, sorted
    by name. The Workflow packages and the Manager's own release assets both
    publish their SHA256SUMS through this one writer."""
    paths = sorted((Path(p) for p in files), key=lambda p: p.name)
    names = [p.name for p in paths]
    if len(set(names)) != len(names):
        raise ValueError(f"two files share a name: {names}")
    return "".join(f"{file_sha256(p)}  {p.name}\n" for p in paths)


@dataclass(frozen=True)
class Package:
    """The three assets of one built package."""

    version: str
    archive: Path
    manifest: Path
    sums: Path


def _relative_parts(name: str) -> tuple[str, ...]:
    """`name` split into components, refused unless it is a plain relative
    path: not absolute, no `..`, no empty or `.` component, no NUL."""
    if not name or "\0" in name or "\\" in name or name.startswith("/"):
        raise ReleaseIntegrityError(f"unsafe path {name!r}")
    parts = tuple(name.rstrip("/").split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise ReleaseIntegrityError(f"unsafe path {name!r}")
    return parts


def _manifest_records(manifest: dict) -> dict[str, dict]:
    """Every file the manifest lists, by location, `manifest.json` aside.
    Refuses an unsafe or repeated location."""
    try:
        records = list(manifest["artifacts"]) + list(manifest["templates"])
        by_location = {}
        for record in records:
            location = record["location"]
            if not isinstance(location, str):
                raise ReleaseIntegrityError(f"manifest location {location!r} is not a path")
            _relative_parts(location)
            if location == MANIFEST_NAME or location in by_location:
                raise ReleaseIntegrityError(f"manifest lists {location} twice")
            by_location[location] = record
    except (KeyError, TypeError) as exc:
        raise ReleaseIntegrityError(f"malformed manifest: {exc!r}") from exc
    return by_location


def _parent_directories(locations: Iterable[str]) -> set[str]:
    parents = set()
    for location in locations:
        parts = _relative_parts(location)
        for depth in range(1, len(parts)):
            parents.add("/".join(parts[:depth]))
    return parents


def _record_mode(record: dict) -> int:
    return EXECUTABLE_MODE if record.get("executable") else FILE_MODE


def _tarinfo(name: str, *, directory: bool, mode: int, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.size = size
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def _read_checked(root: Path, location: str, record: dict) -> bytes:
    """The bytes the archive will carry for `location`, checked against the
    manifest at the moment they are read, not only by the earlier verify."""
    path = root / location
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ReleaseIntegrityError(f"{location} is a link or lies outside the release")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record["sha256"] or len(data) != record["size"]:
        raise ReleaseIntegrityError(f"{location} does not match its manifest entry")
    return data


def build_package(release_dir: Path, out_dir: Path) -> Package:
    """Pack `release_dir` into its three assets in `out_dir`.

    Refuses a release that fails `Release.verify()`. Members are
    `manifest.json`, every manifest location and every parent directory of
    those, sorted, with `mtime = 0`, owner `0:0` and no owner names, mode
    `0755` for directories and executables and `0644` otherwise. The tar is
    USTAR, with a PAX header only where USTAR cannot hold a path; the gzip
    header has `mtime = 0` and no file name.
    """
    release_dir = Path(release_dir)
    try:
        release = Release(release_dir)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise ReleaseIntegrityError(f"{release_dir} is not a release: {exc}") from exc
    problems = release.verify()
    if problems:
        raise ReleaseIntegrityError(
            f"release {release.version} at {release_dir} fails verification: "
            + "; ".join(problems))
    records = _manifest_records(release.manifest)
    manifest_bytes = (release_dir / MANIFEST_NAME).read_bytes()

    top = top_directory(release.version)
    _relative_parts(top)
    members: dict[str, tuple[tarfile.TarInfo, bytes | None]] = {}
    members[top] = (_tarinfo(top, directory=True, mode=DIR_MODE), None)
    for directory in _parent_directories(records):
        name = f"{top}/{directory}"
        members[name] = (_tarinfo(name, directory=True, mode=DIR_MODE), None)
    for location, record in records.items():
        data = _read_checked(release_dir, location, record)
        name = f"{top}/{location}"
        members[name] = (_tarinfo(name, directory=False, mode=_record_mode(record),
                                  size=len(data)), data)
    name = f"{top}/{MANIFEST_NAME}"
    members[name] = (_tarinfo(name, directory=False, mode=FILE_MODE,
                              size=len(manifest_bytes)), manifest_bytes)

    tar_buffer = io.BytesIO()
    # PAX_FORMAT writes a plain USTAR header for every member that fits one,
    # and an extended header only for the one that does not.
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(members):
            info, data = members[name]
            tar.addfile(info, io.BytesIO(data) if data is not None else None)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / archive_name(release.version)
    manifest = out_dir / manifest_asset_name(release.version)
    sums = out_dir / SUMS_NAME
    gz_buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz_buffer, mtime=0,
                       compresslevel=9) as stream:
        stream.write(tar_buffer.getvalue())
    _write_atomically(archive, gz_buffer.getvalue())
    _write_atomically(manifest, manifest_bytes)
    _write_atomically(sums, sha256sums_text([archive, manifest]).encode("utf-8"))
    return Package(version=release.version, archive=archive, manifest=manifest, sums=sums)


def _write_atomically(path: Path, data: bytes) -> None:
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, FILE_MODE)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def extract_package(archive: Path, dest: Path, version: str | None = None) -> Release:
    """Extract `archive` to `dest` and return the release there.

    Accepts only regular files and directories whose paths are relative, have
    no `..` component and lie under the single top-level `workflow-V/`, where
    `V` is the version the carried manifest names (and `version`, when
    given). Refuses links, devices, FIFOs, duplicate members and absolute
    paths. The extracted file set must equal `manifest.json` plus the
    manifest's locations, and each file's sha256, size and executable bit
    must match its entry. The tree is extracted into a temporary sibling of
    `dest` and published by `rename`; any failure raises
    `ReleaseIntegrityError` and leaves nothing behind.
    """
    dest = Path(dest)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"{dest} already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", dir=dest.parent))
    try:
        tree = staging / "tree"
        tree.mkdir()
        try:
            _extract_into(Path(archive), tree, version)
        except (tarfile.TarError, EOFError, zlib.error, OSError) as exc:
            raise ReleaseIntegrityError(f"{archive} is not a readable package: {exc}") from exc
        os.rename(tree, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return Release(dest)


def _extract_into(archive: Path, tree: Path, version: str | None) -> None:
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    modes: dict[str, int] = {}
    top: str | None = None
    unpacked = 0
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            parts = _relative_parts(member.name)
            if top is None:
                top = parts[0]
            elif parts[0] != top:
                raise ReleaseIntegrityError(
                    f"member {member.name!r} lies outside the top-level directory {top}/")
            relative = "/".join(parts[1:])
            if relative in files or relative in directories:
                raise ReleaseIntegrityError(f"duplicate member {member.name!r}")
            if member.isdir():
                if member.mode != DIR_MODE:
                    raise ReleaseIntegrityError(
                        f"directory {member.name!r} has mode {member.mode:o}")
                directories.add(relative)
                continue
            if member.type not in _ACCEPTED_FILE_TYPES:
                raise ReleaseIntegrityError(
                    f"member {member.name!r} is not a regular file or directory")
            if not relative:
                raise ReleaseIntegrityError(f"top-level member {member.name!r} is a file")
            if member.mode not in (FILE_MODE, EXECUTABLE_MODE):
                raise ReleaseIntegrityError(f"file {member.name!r} has mode {member.mode:o}")
            unpacked += member.size
            if unpacked > MAX_UNPACKED_BYTES:
                raise ReleaseIntegrityError(
                    f"package unpacks to more than {MAX_UNPACKED_BYTES} bytes")
            stream = tar.extractfile(member)
            data = stream.read() if stream is not None else b""
            if len(data) != member.size:
                raise ReleaseIntegrityError(f"member {member.name!r} is truncated")
            files[relative] = data
            modes[relative] = member.mode

    if top is None:
        raise ReleaseIntegrityError(f"{archive} is empty")
    if MANIFEST_NAME not in files:
        raise ReleaseIntegrityError(f"{archive} carries no {MANIFEST_NAME}")
    try:
        manifest = json.loads(files[MANIFEST_NAME])
        manifest_version = manifest["workflow_version"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ReleaseIntegrityError(f"{archive} carries a malformed manifest: {exc!r}") from exc
    if version is not None and manifest_version != version:
        raise ReleaseIntegrityError(
            f"{archive} carries release {manifest_version!r}, not {version!r}")
    if top != top_directory(manifest_version):
        raise ReleaseIntegrityError(
            f"{archive}'s top-level directory is {top}/, expected "
            f"{top_directory(manifest_version)}/")
    if modes[MANIFEST_NAME] != FILE_MODE:
        raise ReleaseIntegrityError(f"{MANIFEST_NAME} has mode {modes[MANIFEST_NAME]:o}")

    records = _manifest_records(manifest)
    expected = set(records) | {MANIFEST_NAME}
    extra = sorted(set(files) - expected)
    missing = sorted(expected - set(files))
    if extra or missing:
        raise ReleaseIntegrityError(
            f"{archive}'s files differ from its manifest: extra {extra}, missing {missing}")
    stray = sorted(directories - _parent_directories(records) - {""})
    if stray:
        raise ReleaseIntegrityError(f"{archive} carries unexpected directories {stray}")
    for location, record in records.items():
        data = files[location]
        if hashlib.sha256(data).hexdigest() != record["sha256"] or len(data) != record["size"]:
            raise ReleaseIntegrityError(f"{location} does not match its manifest entry")
        if modes[location] != _record_mode(record):
            raise ReleaseIntegrityError(
                f"{location} has mode {modes[location]:o}, its manifest says "
                f"{'executable' if record.get('executable') else 'not executable'}")

    for relative, data in sorted(files.items()):
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, modes[relative])
    for relative in directories:
        (tree / relative).mkdir(parents=True, exist_ok=True)
    problems = Release(tree).verify()
    if problems:
        raise ReleaseIntegrityError("extracted release fails verification: " + "; ".join(problems))
