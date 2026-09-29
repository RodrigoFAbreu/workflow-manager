"""Command-line entry point.

    python3 -m workflow_manager status    <target>
    python3 -m workflow_manager bootstrap <target> [--profile full|runtime] [--force]
    python3 -m workflow_manager update    <target> [--profile ...] [--force]
    python3 -m workflow_manager verify    <target>
    python3 -m workflow_manager uninstall <target>
    python3 -m workflow_manager releases
    python3 -m workflow_manager --version

Every command takes `--release-version` to pick among the releases in
`distribution/`. Without it, the two commands that *change* which release a
repository is on -- `bootstrap` and `update` -- mean the newest release, and
the two that *report on* an installation -- `status` and `verify` -- mean the
release the target says it has, so they never quietly grade a repository
against something it was never installed from.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from .install import (
    AlreadyManagedError,
    CollisionError,
    DriftError,
    InstallError,
    NotManagedError,
    bootstrap,
    status,
    uninstall,
    update,
    verify,
)
from .installation import CorruptInstallationError, Installation, is_managed
from .release import (
    INSTALL_PROFILE_FULL,
    INSTALL_PROFILES,
    ReleaseIntegrityError,
    available_versions,
    find_release,
    release_root,
)

MANAGER_ROOT = Path(__file__).resolve().parent.parent.parent

DISTRIBUTION_NAME = "workflow-manager"
#: Only strict `vX.Y.Z` tags name a release (`tools/release/release.py`'s `TAG_RE`).
_STRICT_TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_GIT_TIMEOUT_SECONDS = 10


def _installed_version() -> str | None:
    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return None


def _git(root: Path, *args: str) -> str | None:
    """`git -C root ...`'s stripped stdout, or None on any failure: `--version`
    is never an error, so every Git problem falls through to the next line."""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=_GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _is_work_tree_top(root: Path) -> bool:
    """True only when `root` is itself the top of a Git work tree. A wheel
    installed into a `.venv` inside some *other* repository resolves
    MANAGER_ROOT below that repository's top, whose tags are not ours."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return False
    try:
        return Path(top).resolve() == Path(root).resolve()
    except OSError:
        return False


def _exact_release_tag(root: Path) -> str | None:
    """The highest strict tag on HEAD, when the tracked tree is clean."""
    tags = _git(root, "tag", "--points-at", "HEAD", "--list", "v[0-9]*")
    if tags is None:
        return None
    strict = [t for t in tags.splitlines() if _STRICT_TAG_RE.match(t)]
    if not strict:
        return None
    if _git(root, "status", "--porcelain", "--untracked-files=no") != "":
        return None
    return max(strict, key=lambda t: tuple(int(n) for n in _STRICT_TAG_RE.match(t).groups()))


def version_text(root: Path = MANAGER_ROOT, installed_version=_installed_version) -> str:
    """`--version`'s output (`D-Version-Report`), the first that applies:

    1. the installed distribution's metadata version, when it is a release
       version (not `.dev`, not missing);
    2. a clean checkout whose HEAD is a strict release tag is that release;
    3. a development build, described by `git describe` when `root` is the
       top of a Git work tree.
    """
    version = installed_version()
    if version and ".dev" not in version:
        return f"{DISTRIBUTION_NAME} {version}"
    if not _is_work_tree_top(root):
        return f"{DISTRIBUTION_NAME} development build"
    tag = _exact_release_tag(root)
    if tag is not None:
        return f"{DISTRIBUTION_NAME} {tag[1:]} (checkout at {tag})"
    described = _git(root, "describe", "--tags", "--always", "--dirty")
    if described:
        return f"{DISTRIBUTION_NAME} development build ({described})"
    return f"{DISTRIBUTION_NAME} development build"


class _VersionAction(argparse.Action):
    """`action="version"`, computed only when asked for: no Git call runs on
    an ordinary command."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS,
                 help="print the Manager's own version and exit"):
        super().__init__(option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(version_text())
        parser.exit()


def missing_distribution_message(manager_root: Path) -> str:
    return (
        f"no Workflow releases at {release_root(manager_root)}: this Manager is "
        f"probably installed from a wheel, not run from a checkout. Until M2, pass "
        f"--manager-root <workflow-manager checkout at the matching tag>."
    )


def _require_distribution(manager_root: Path) -> None:
    if not release_root(manager_root).is_dir():
        raise InstallError(missing_distribution_message(manager_root))


def _release(args):
    """The newest migrated release, or the pinned one."""
    _require_distribution(args.manager_root)
    return find_release(args.manager_root, args.release_version)


def _release_for_target(args):
    """The release a *report* about `args.target` should be measured against.

    An installed repository is graded against the release it records, not
    against whatever happens to be newest -- otherwise every target would look
    broken the moment a new release landed in `distribution/`.
    """
    if args.release_version is not None:
        _require_distribution(args.manager_root)
        return find_release(args.manager_root, args.release_version)
    if not is_managed(args.target):
        return None
    _require_distribution(args.manager_root)
    version = Installation.read(args.target).workflow_version
    available = available_versions(args.manager_root)
    if version not in available:
        raise InstallError(
            f"{args.target} records workflow {version}, which is not in "
            f"{Path(args.manager_root) / 'distribution' / 'workflow'} "
            f"(present: {', '.join(available) or 'none'}). "
            f"Nothing can be verified against a release that is not here."
        )
    return find_release(args.manager_root, version)


def cmd_releases(args) -> int:
    if not release_root(args.manager_root).is_dir():
        print(f"error: {missing_distribution_message(args.manager_root)}", file=sys.stderr)
        return 1
    for version in available_versions(args.manager_root):
        release = find_release(args.manager_root, version)
        print(f"{release.version}  from {release.upstream['tag']} "
              f"({release.upstream['commit'][:12]})  "
              f"[{release.provenance['origin']}]  "
              f"{len(release.installable(INSTALL_PROFILE_FULL))} files")
    return 0


def cmd_status(args) -> int:
    result = status(args.target, _release_for_target(args))
    print(result)
    if not result.managed:
        return 0
    return 0 if (result.verified and not result.problems) else 1


def cmd_bootstrap(args) -> int:
    release = _release(args)
    installation = bootstrap(args.target, release, args.profile, force=args.force)
    print(f"bootstrapped workflow {installation.workflow_version} "
          f"({installation.profile}) into {args.target}")
    print(f"  {len(installation.managed)} managed files, "
          f"{len(installation.generated)} state files, "
          f"{len(installation.merged)} merged files")
    return 0


def cmd_update(args) -> int:
    release = _release(args)
    installation, changes = update(args.target, release, args.profile, force=args.force)
    print(f"updated {args.target} to workflow {installation.workflow_version}")
    for change in changes:
        print(f"  {change}")
    if not changes:
        print("  (no change)")
    return 0


def cmd_verify(args) -> int:
    release = _release_for_target(args)
    if release is None:
        raise NotManagedError(f"{args.target} is not a managed repository; nothing to verify")
    problems = verify(args.target, release)
    if not problems:
        print(f"{args.target}: installation matches workflow {release.version}")
        return 0
    print(f"{args.target}: {len(problems)} problem(s)")
    for problem in problems:
        print(f"  {problem}")
    return 1


def cmd_uninstall(args) -> int:
    removed = uninstall(args.target)
    print(f"removed {len(removed)} managed files from {args.target}")
    print("repository-local state (WORKFLOW_STATE.json, ACTIVE_MILESTONE.md) was kept")
    return 0


COMMANDS = {
    "releases": cmd_releases,
    "status": cmd_status,
    "bootstrap": cmd_bootstrap,
    "update": cmd_update,
    "verify": cmd_verify,
    "uninstall": cmd_uninstall,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflow_manager", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--manager-root", type=Path, default=MANAGER_ROOT,
                        help="the workflow-manager checkout holding distribution/")
    parser.add_argument("--version", action=_VersionAction)
    parser.add_argument("--release-version", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("releases", help="list migrated releases")

    for name in ("status", "verify", "uninstall"):
        p = sub.add_parser(name)
        p.add_argument("target", type=Path)

    p = sub.add_parser("bootstrap")
    p.add_argument("target", type=Path)
    p.add_argument("--profile", choices=INSTALL_PROFILES, default=INSTALL_PROFILE_FULL)
    p.add_argument("--force", action="store_true",
                   help="overwrite files the repository already keeps at release paths")

    p = sub.add_parser("update")
    p.add_argument("target", type=Path)
    p.add_argument("--profile", choices=INSTALL_PROFILES, default=None)
    p.add_argument("--force", action="store_true",
                   help="overwrite managed files that were modified locally")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except DriftError as error:
        print(str(error), file=sys.stderr)
        print("\nre-run with --force to discard those local edits", file=sys.stderr)
        return 2
    except CollisionError as error:
        print(str(error), file=sys.stderr)
        print("\nre-run with --force to replace those files with the release's",
              file=sys.stderr)
        return 2
    except (AlreadyManagedError, NotManagedError, InstallError, CorruptInstallationError,
            ReleaseIntegrityError, FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
