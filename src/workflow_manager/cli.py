"""Command-line entry point.

    python3 -m workflow_manager status   <target>
    python3 -m workflow_manager bootstrap <target> [--profile full|runtime]
    python3 -m workflow_manager update    <target> [--profile ...] [--force]
    python3 -m workflow_manager verify    <target>
    python3 -m workflow_manager uninstall <target>
    python3 -m workflow_manager releases

Every command takes `--release-version` to pick among the releases in
`distribution/`; with one release present it is optional.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .install import (
    AlreadyManagedError,
    DriftError,
    InstallError,
    NotManagedError,
    bootstrap,
    status,
    uninstall,
    update,
    verify,
)
from .release import INSTALL_PROFILE_FULL, INSTALL_PROFILES, find_release

MANAGER_ROOT = Path(__file__).resolve().parent.parent.parent


def _release(args):
    return find_release(args.manager_root, args.release_version)


def cmd_releases(args) -> int:
    base = Path(args.manager_root) / "distribution" / "workflow"
    if not base.exists():
        print("no distribution/ — run tools/migrate.py first", file=sys.stderr)
        return 1
    for path in sorted(base.iterdir()):
        if (path / "manifest.json").exists():
            from .release import Release
            release = Release(path)
            print(f"{release.version}  from {release.upstream['tag']} "
                  f"({release.upstream['commit'][:12]})  "
                  f"{len(release.payload_artifacts(INSTALL_PROFILE_FULL))} files")
    return 0


def cmd_status(args) -> int:
    try:
        release = _release(args)
    except (FileNotFoundError, ValueError):
        release = None
    result = status(args.target, release)
    print(result)
    return 0 if (not result.managed or not result.problems) else 1


def cmd_bootstrap(args) -> int:
    release = _release(args)
    installation = bootstrap(args.target, release, args.profile)
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
    release = _release(args)
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
    parser = argparse.ArgumentParser(prog="workflow_manager", description=__doc__)
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
    except (AlreadyManagedError, NotManagedError, InstallError, FileNotFoundError,
            ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
