"""Command-line entry point.

    python3 -m workflow_manager status    <target>
    python3 -m workflow_manager bootstrap <target> [--profile full|runtime] [--force]
    python3 -m workflow_manager update    <target> [--profile ...] [--force]
    python3 -m workflow_manager verify    <target>
    python3 -m workflow_manager uninstall <target>
    python3 -m workflow_manager releases

Every command takes `--release-version` to pick among the releases in
`distribution/`. Without it, the two commands that *change* which release a
repository is on -- `bootstrap` and `update` -- mean the newest release, and
the two that *report on* an installation -- `status` and `verify` -- mean the
release the target says it has, so they never quietly grade a repository
against something it was never installed from.
"""

from __future__ import annotations

import argparse
import sys
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
)

MANAGER_ROOT = Path(__file__).resolve().parent.parent.parent


def _release(args):
    """The newest migrated release, or the pinned one."""
    return find_release(args.manager_root, args.release_version)


def _release_for_target(args):
    """The release a *report* about `args.target` should be measured against.

    An installed repository is graded against the release it records, not
    against whatever happens to be newest -- otherwise every target would look
    broken the moment a new release landed in `distribution/`.
    """
    if args.release_version is not None:
        return find_release(args.manager_root, args.release_version)
    if not is_managed(args.target):
        return None
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
    base = Path(args.manager_root) / "distribution" / "workflow"
    if not base.exists():
        print("no distribution/ — run tools/migrate.py first", file=sys.stderr)
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
