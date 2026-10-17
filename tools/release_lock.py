#!/usr/bin/env python3
"""Maintain the tested-releases lock, `tests/tested_releases.json` (plan 3.5).

    release_lock.py add VERSION [--lock FILE] [--release-source S]
    release_lock.py check [--lock FILE] [--release-source S]
    release_lock.py latest --out FILE [--lock FILE] [--release-source S]

The lock lists the Workflow releases published after the last pin, with their
digests, and is what a test run tests besides the pins. It is test data: not
shipped in the wheel, not read by the CLI.

- `add` downloads VERSION's published assets, verifies them the way a pin is
  (`SHA256SUMS` against the archive and the manifest asset, the package's own
  integrity checks), and writes the digests. While the release's manifest has
  no `conformance` block it also writes the frozen suite counts (the suites of
  the newest tested release plus any other non-demo `*_test.py` in the payload,
  counted by the runner's own discovery) and an empty `portability_exceptions`
  list, which the pull request's reviewer checks. Run it in a non-releasing
  `chore:` pull request.
- `check` validates the lock's shape and that no entry is also a pin, and
  compares each entry's digests with what the source publishes. Exit 1 on any
  mismatch.
- `latest` writes to `--out` the lock with the newest published release
  added when it is newer than every pin and tested release; the nightly's plan
  job uses it (with `GITHUB_TOKEN`, for the GitHub listing's rate limit) and
  the other jobs read the result through `WORKFLOW_MANAGER_TESTED_RELEASES`.
  The committed lock is never written.

Exit codes: 0 success; 1 a verification failure or a refused lock; 2 usage
(docs/exit-codes.md, "Maintainer tools").
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import tested_releases  # noqa: E402
from tested_releases import LockEntry, LockError  # noqa: E402

from workflow_manager import source  # noqa: E402
from workflow_manager.release import ReleaseIntegrityError, _version_key  # noqa: E402

#: The suite files the frozen CI does not run as conformance suites.
DEMO_SUFFIX = "_demo_test.py"


class ToolError(Exception):
    pass


def _source(option: str | None) -> source.ReleaseSource:
    return source.ReleaseSource.select(option)


def _verify(where: source.ReleaseSource, pins: source.Pins, version: str, pin: source.Pin,
            cache_root: Path) -> source.Release:
    """Fetch VERSION through the release cache under `pin` (the same checks a
    pinned release gets) and return the verified, snapshotted release."""
    own = source.Pins(repository=pins.repository, releases={version: pin})
    cache = source.ReleaseCache(cache_root, where, own)
    try:
        return cache.resolve(version)
    except (source.ReleaseUnavailableError, ReleaseIntegrityError, source.InstallError) as exc:
        raise ToolError(f"{version}: {exc}") from exc


def count_suites(scripts: Path, suites: list[str]) -> dict[str, int]:
    """Test counts of `suites` in a payload's `scripts/`, by the runner's own discovery."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONPATH=str(REPO_ROOT / "tests"), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-B", "-m", "parallel.inventory", "--discover-suites",
                           *suites], cwd=str(scripts), capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise ToolError(f"counting the suites failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}")
    found = json.loads(proc.stdout)
    return {suite: sum(len(methods) for methods in found[suite].values()) for suite in suites}


def _suite_names(scripts: Path, previous: dict | None) -> list[str]:
    names = set(previous or ())
    names |= {p.name for p in scripts.glob("*_test.py") if not p.name.endswith(DEMO_SUFFIX)}
    return sorted(names)


def _previous_suites(pins: source.Pins, lock: dict[str, LockEntry]) -> dict | None:
    """The suite table of the newest tested release (built in, or its lock entry)."""
    tested = tested_releases.tested_versions(pins, lock)
    if tested[-1] in lock:
        return lock[tested[-1]].suites
    import support  # noqa: PLC0415  (imports the whole test support; only `add` needs it)

    return support.CI_SUITES.get(tested[-1])


def add_entry(version: str, lock_file: Path, where: source.ReleaseSource,
              previous_suites: dict | None = None) -> LockEntry:
    pins = source.load_pins()
    lock = tested_releases.load_lock(lock_file) if lock_file.exists() else {}
    if version in pins.releases:
        raise ToolError(f"{version} is pinned: a pinned release is not added to the lock. "
                        f"Every pin is already tested in every run, so no lock change is "
                        f"needed; `add` is for a release published after the last pin "
                        f"(see `python3 tools/release_lock.py check`)")
    if version in lock:
        raise ToolError(f"{version} is already in the lock")
    try:
        candidate = where.inspect(version)
    except (source.ReleaseUnavailableError, ReleaseIntegrityError) as exc:
        raise ToolError(f"{version}: {exc}") from exc
    with tempfile.TemporaryDirectory(prefix="release-lock-") as tmp:
        release = _verify(where, pins, version, candidate.pin, Path(tmp))
        block = release.manager
        entry = LockEntry(version, candidate.pin.archive, candidate.pin.sha256,
                          candidate.pin.manifest_sha256)
        if block is None or block.conformance is None:
            scripts = Path(release.root) / "payload" / "scripts"
            names = _suite_names(scripts, previous_suites)
            entry = LockEntry(version, entry.archive, entry.sha256, entry.manifest_sha256,
                              count_suites(scripts, names), ())
    candidate_lock = {**lock, version: entry}
    tested_releases.check_against_pins(candidate_lock, pins)
    lock_file.write_text(tested_releases.dump_lock(candidate_lock))
    return entry


def check_lock(lock_file: Path, where: source.ReleaseSource) -> list[str]:
    """Problems found (empty when the lock is sound)."""
    pins = source.load_pins()
    try:
        lock = tested_releases.load_lock(lock_file)
        tested_releases.check_against_pins(lock, pins)
    except LockError as exc:
        return [str(exc)]
    problems = []
    for version, entry in lock.items():
        try:
            pin = where.inspect(version).pin
        except (source.ReleaseUnavailableError, ReleaseIntegrityError) as exc:
            problems.append(f"{version}: {exc}")
            continue
        if (pin.sha256, pin.manifest_sha256) != (entry.sha256, entry.manifest_sha256):
            problems.append(f"{version}: the lock's digests differ from the published ones")
    return problems


def _github_listing(pins: source.Pins) -> source.Listing:
    url = source.GITHUB_LISTING_URL.format(repository=pins.repository)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as stream:
            return source.parse_github_listing(stream.read(source.MAX_LISTING_BYTES))
    except (OSError, ValueError, source.DiscoveryFailure) as exc:
        raise ToolError(f"cannot list the published releases at {url}: {exc}") from exc


def latest_lock(lock_file: Path, where: source.ReleaseSource) -> dict[str, LockEntry]:
    pins = source.load_pins()
    lock = tested_releases.load_lock(lock_file)
    if where.directory is None and where.value == source.DEFAULT_SOURCE:
        listing = _github_listing(pins)
    else:
        listing = where.listing(pins.repository, source.Deadline(60))
        if listing is None:
            raise ToolError("this release source has no listing: name a directory or the default")
    tested = tested_releases.tested_versions(pins, lock)
    newer = [v for v in listing.versions if _version_key(v) > _version_key(tested[-1])]
    if not newer:
        return lock
    newest = max(newer, key=_version_key)
    lock = dict(lock)
    with tempfile.TemporaryDirectory(prefix="release-lock-") as tmp:
        scratch = Path(tmp) / "tested_releases.json"
        scratch.write_text(tested_releases.dump_lock(lock))
        add_entry(newest, scratch, where, _previous_suites(pins, lock))
        return tested_releases.load_lock(scratch)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"release_lock.py: usage error: {message}", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="release_lock.py", description=__doc__.splitlines()[0])
    parser.add_argument("--lock", type=Path, default=tested_releases.LOCK_PATH)
    parser.add_argument("--release-source")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    add = sub.add_parser("add")
    add.add_argument("version")
    sub.add_parser("check")
    latest = sub.add_parser("latest")
    latest.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    where = _source(args.release_source)
    try:
        if args.command == "add":
            entry = add_entry(args.version, args.lock, where,
                              _previous_suites(source.load_pins(),
                                               tested_releases.load_lock(args.lock)))
            print(json.dumps({args.version: entry.to_json()}, indent=2, sort_keys=True))
        elif args.command == "check":
            problems = check_lock(args.lock, where)
            for problem in problems:
                print(f"release_lock.py: {problem}", file=sys.stderr)
            return 1 if problems else 0
        else:
            lock = latest_lock(args.lock, where)
            args.out.write_text(tested_releases.dump_lock(lock))
            print(json.dumps(sorted(lock, key=_version_key)))
    except (ToolError, LockError) as exc:
        print(f"release_lock.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
