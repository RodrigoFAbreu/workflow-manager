#!/usr/bin/env python3
"""Build and prove the Workflow release packages (plan 6, checkpoint CP4).

    workflow_packages.py build (--from DIR | --commit SHA) --out DIR
                               [--pins FILE [--check]] [--prime]

Builds one package (`workflow_manager.package`, `D-Package-Format`) per
`<from>/<version>/` into `<out>/<version>/`, a layout any `--release-source`
directory accepts. Each package is proved before anything is written from it:

- it is built twice, and the two builds' assets are byte-identical;
- it is extracted into a scratch directory, and the extracted tree equals its
  source tree: the same file set, bytes and modes, nothing more or less.

`--commit SHA` builds from `git archive SHA distribution/workflow`, extracted
into a scratch directory, never from the working tree (which may carry
untracked `__pycache__/`). With `--pins FILE` the packages' digests are
written to FILE (`D-Pins`), or, with `--check`, compared with it: the pinned
versions must be exactly the built ones, with the same digests. `--prime`
then fills the release cache (`--release-cache`'s precedence, without the
option) from `<out>` through `ReleaseCache.ensure`, so every entry is
checked against the pins exactly as a download would be.

Prints the evidence table (`docs/MIGRATION.md`) on stdout. Exit codes: 0
success; 1 a build, proof or pin mismatch; 2 usage error.
"""

from __future__ import annotations

import argparse
import filecmp
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workflow_manager import package as workflow_package  # noqa: E402
from workflow_manager import source as release_source  # noqa: E402
from workflow_manager.release import ReleaseIntegrityError, _version_key  # noqa: E402

#: Where a Manager checkout keeps its releases, for `--commit`.
DISTRIBUTION_PATH = "distribution/workflow"
GIT_TIMEOUT_SECONDS = 120


class PackagesError(Exception):
    pass


@dataclass(frozen=True)
class Evidence:
    """One row of the evidence table."""

    version: str
    files: int
    archive_sha256: str
    manifest_sha256: str
    tar_sha256: str


def extract_committed(commit: str, dest: Path, repo: Path = REPO_ROOT) -> Path:
    """`git archive <commit> distribution/workflow`, extracted under `dest`.
    Returns `dest/distribution/workflow`, holding one directory per release."""
    try:
        proc = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit,
                               DISTRIBUTION_PATH], capture_output=True,
                              timeout=GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PackagesError(f"git archive {commit}: {exc}") from exc
    if proc.returncode != 0:
        raise PackagesError(f"git archive {commit} exited {proc.returncode}: "
                            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tar:
        tar.extractall(dest, filter="data")
    return Path(dest) / DISTRIBUTION_PATH


def release_dirs(root: Path) -> dict[str, Path]:
    """`<root>/<version>/` for every directory holding a `manifest.json`."""
    return {p.name: p for p in sorted(Path(root).iterdir(), key=lambda p: _version_key(p.name))
            if (p / workflow_package.MANIFEST_NAME).is_file()}


def tree_listing(root: Path) -> dict[str, tuple[str, int]]:
    """Every entry under `root`: a file's sha256 and mode, or a directory's
    `"dir"` and mode. Anything else (a link, a device) is refused."""
    listing = {}
    for path in sorted(Path(root).rglob("*")):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            listing[relative] = ("dir", stat.S_IMODE(info.st_mode))
        elif stat.S_ISREG(info.st_mode):
            listing[relative] = (workflow_package.file_sha256(path), stat.S_IMODE(info.st_mode))
        else:
            raise PackagesError(f"{path} is neither a file nor a directory")
    return listing


def round_trip_differences(source: Path, extracted: Path) -> list[str]:
    """How the tree a package extracts to differs from its source tree:
    file set, bytes and modes. Directory modes are the package's own
    (`0755`), so only a directory's presence is compared."""
    want, got = tree_listing(source), tree_listing(extracted)
    problems = [f"missing {p}" for p in sorted(set(want) - set(got))]
    problems += [f"extra {p}" for p in sorted(set(got) - set(want))]
    for path in sorted(set(want) & set(got)):
        (want_digest, want_mode), (got_digest, got_mode) = want[path], got[path]
        if want_digest != got_digest:
            problems.append(f"{path}: {got_digest} is not {want_digest}")
        elif want_digest != "dir" and want_mode != got_mode:
            problems.append(f"{path}: mode {got_mode:o} is not {want_mode:o}")
    return problems


def _tar_sha256(archive: Path) -> str:
    with gzip.open(archive, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def build_one(release_dir: Path, out: Path, scratch: Path) -> Evidence:
    """Build `release_dir`'s package into `out`, and prove it."""
    built = workflow_package.build_package(release_dir, out)
    again = workflow_package.build_package(release_dir, scratch / "again")
    for first, second in ((built.archive, again.archive), (built.manifest, again.manifest),
                          (built.sums, again.sums)):
        if not filecmp.cmp(first, second, shallow=False):
            raise PackagesError(f"release {built.version}: two builds of {first.name} differ")
    release = workflow_package.extract_package(built.archive, scratch / "tree", built.version)
    problems = round_trip_differences(release_dir, release.root)
    if problems:
        raise PackagesError(f"release {built.version} does not round-trip: "
                            + "; ".join(problems[:20]))
    files = sum(1 for p in release.root.rglob("*") if p.is_file())
    return Evidence(version=built.version, files=files,
                    archive_sha256=workflow_package.file_sha256(built.archive),
                    manifest_sha256=workflow_package.file_sha256(built.manifest),
                    tar_sha256=_tar_sha256(built.archive))


def build_all(root: Path, out: Path) -> list[Evidence]:
    """Build and prove one package per release under `root`, each into
    `out/<version>/`."""
    releases = release_dirs(root)
    if not releases:
        raise PackagesError(f"{root} holds no release")
    evidence = []
    for version, release_dir in releases.items():
        if (out / version).exists():
            raise PackagesError(f"{out / version} already exists")
        with tempfile.TemporaryDirectory(prefix=f"workflow-packages-{version}-") as tmp:
            row = build_one(release_dir, out / version, Path(tmp))
        if row.version != version:
            raise PackagesError(f"{release_dir} holds release {row.version}, not {version}")
        evidence.append(row)
    return evidence


def pins_document(evidence: list[Evidence], repository: str) -> dict:
    return {
        "schema_version": release_source.PINS_SCHEMA_VERSION,
        "repository": repository,
        "releases": {row.version: {"archive": workflow_package.archive_name(row.version),
                                   "sha256": row.archive_sha256,
                                   "manifest_sha256": row.manifest_sha256}
                     for row in evidence},
    }


def pins_text(document: dict) -> str:
    """The pin file's canonical form: sorted keys, two-space indent."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def write_or_check_pins(evidence: list[Evidence], path: Path, check: bool) -> None:
    existing = release_source.load_pins(path)
    wanted = pins_text(pins_document(evidence, existing.repository))
    if check:
        if path.read_text() != wanted:
            actual = {v: (p.sha256, p.manifest_sha256) for v, p in existing.releases.items()}
            built = {r.version: (r.archive_sha256, r.manifest_sha256) for r in evidence}
            raise PackagesError(f"{path} does not pin the built packages: pinned {actual}, "
                                f"built {built}")
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(wanted)
    os.replace(temporary, path)


def prime(out: Path, pins_path: Path, versions: list[str]) -> Path:
    """Fill the release cache from `out` through the pinned-download path."""
    pins = release_source.load_pins(pins_path)
    cache = release_source.ReleaseCache(release_source.cache_root(),
                                        release_source.ReleaseSource(str(out)), pins)
    for version in versions:
        cache.ensure(version)
    return cache.root


def evidence_table(evidence: list[Evidence]) -> str:
    lines = ["| version | files | archive sha256 | manifest sha256 | uncompressed tar sha256 "
             "| round trip |",
             "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r.version} | {r.files} | `{r.archive_sha256}` | `{r.manifest_sha256}` "
              f"| `{r.tar_sha256}` | identical |" for r in evidence]
    return "\n".join(lines) + "\n"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"workflow_packages.py: usage error: {message}", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="workflow_packages.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    build = sub.add_parser("build")
    origin = build.add_mutually_exclusive_group(required=True)
    origin.add_argument("--from", dest="from_dir", type=Path)
    origin.add_argument("--commit")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--pins", type=Path, default=None)
    build.add_argument("--check", action="store_true",
                       help="compare the packages with --pins instead of writing it")
    build.add_argument("--prime", action="store_true",
                       help="fill the release cache from --out, checked against --pins")
    args = parser.parse_args(argv)
    if (args.check or args.prime) and args.pins is None:
        parser.error("--check and --prime need --pins")
    try:
        with tempfile.TemporaryDirectory(prefix="workflow-packages-source-") as tmp:
            root = args.from_dir if args.commit is None else \
                extract_committed(args.commit, Path(tmp))
            args.out.mkdir(parents=True, exist_ok=True)
            evidence = build_all(root, args.out)
        if args.pins is not None:
            write_or_check_pins(evidence, args.pins, args.check)
        if args.prime:
            cache = prime(args.out, args.pins, [row.version for row in evidence])
            print(f"primed {cache}", file=sys.stderr)
    except (PackagesError, ReleaseIntegrityError, release_source.ReleaseUnavailableError,
            OSError) as exc:
        print(f"workflow_packages.py: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(evidence_table(evidence))
    return 0


if __name__ == "__main__":
    sys.exit(main())
