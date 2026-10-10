"""Command-line entry point.

    python3 -m workflow_manager status    <target>
    python3 -m workflow_manager bootstrap <target> [--profile full|runtime] [--force]
    python3 -m workflow_manager update    <target> [--profile ...] [--force] [--dry-run]
    python3 -m workflow_manager doctor    <target>
    python3 -m workflow_manager verify    <target>
    python3 -m workflow_manager uninstall <target>
    python3 -m workflow_manager releases
    python3 -m workflow_manager package build <release-dir> --out <dir>
    python3 -m workflow_manager package verify <archive> [--sha256 H]
    python3 -m workflow_manager --version

Releases are published packages, pinned in the Manager's
`published_releases.json` and fetched through a verified cache
(`--release-source`, `--release-cache`); `--release-dir` installs an
unpackaged release directory instead. `--release-version` picks the release.
Without it, the two commands that *change* which release a repository is on
-- `bootstrap` and `update` -- mean the newest published release, and the two
that *report on* an installation -- `status` and `verify` -- mean the release
the target says it has, so they never quietly grade a repository against
something it was never installed from.

`doctor` and `update --dry-run` read a repository and report what an update
would do and which Workflow guarantees it would cross; they never write the
repository (they write the release cache and one temporary snapshot, both
outside it). `doctor` measures against the newest pinned release, or
`--release-version`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from importlib import metadata
from pathlib import Path

from . import advice
from . import source as release_source
from .compatibility import (
    ContainmentError,
    Destinations,
    data_files,
    data_findings,
    holds_data,
    missing_templates,
    plan_destinations,
    read_repository,
    read_work_items,
    render_report,
    render_work_in_flight,
    build_report,
)
from .install import (
    AlreadyManagedError,
    CollisionError,
    DriftError,
    InstallError,
    NotManagedError,
    bootstrap,
    plan_update,
    status,
    uninstall,
    update,
    verify,
)
from .installation import CorruptInstallationError, Installation, is_managed, not_managed_text
from .package import build_package, extract_package, file_sha256
from .release import (
    INSTALL_PROFILE_FULL,
    INSTALL_PROFILES,
    Release,
    ReleaseIntegrityError,
    _version_key,
)
from .source import (
    ReleaseCache,
    ReleaseNotPublishedError,
    ReleaseSource,
    ReleaseUnavailableError,
    cache_root,
    local_release,
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


# ---------------------------------------------------------------------------
# Resolving a release (`D-CLI`)
# ---------------------------------------------------------------------------

#: The errors that mean "no usable release": exit 1, with actionable text.
RELEASE_ERRORS = (ReleaseNotPublishedError, ReleaseUnavailableError, ReleaseIntegrityError)

MANAGER_ROOT_DEPRECATION = (
    "workflow-manager: --manager-root is deprecated and will be removed in a later release. "
    "Published releases need no option; use --release-dir <dir> for an unpackaged release."
)


def _pins():
    """The pin file, read at call time (tests point `source.PINS_PATH` elsewhere)."""
    return release_source.load_pins(release_source.PINS_PATH)


def _cache(args, pins) -> ReleaseCache:
    return ReleaseCache(cache_root(args.release_cache),
                        ReleaseSource.select(args.release_source), pins)


def _checkout_releases(checkout: Path) -> dict[str, Path]:
    """`<checkout>/distribution/workflow/<v>/` for every `v` present -- the
    deprecated `--manager-root` alias's layout, a plain path join."""
    base = Path(checkout) / "distribution" / "workflow"
    if not base.is_dir():
        return {}
    return {p.name: p for p in sorted(base.iterdir(), key=lambda p: _version_key(p.name))
            if (p / "manifest.json").is_file()}


def _alias_releases(args) -> dict[str, Path]:
    """The `--manager-root` alias's checkout releases; none without the alias."""
    return {} if args.manager_root is None else _checkout_releases(args.manager_root)


def _default_version(args, pins) -> str:
    """The newest pinned version, else the newest alias checkout version."""
    versions = pins.versions() or list(_alias_releases(args))
    if not versions:
        raise ReleaseNotPublishedError(
            "no Workflow release is published: this Manager pins none", kind="none-pinned")
    return versions[-1]


def _resolve(args, version: str | None, destinations: Destinations | None = None):
    """The release `version` (default: the newest) as a verified private
    snapshot. Precedence: `--release-dir`, the `--manager-root` alias when its
    checkout holds the version, then the pins through the cache, which refuse
    an unpinned version.

    `destinations` is the read-only commands' (`doctor`, `update --dry-run`):
    the validated snapshot parent and the no-follow lock leaf, threaded down so
    no hop falls back to the default temporary directory."""
    pins = _pins()
    parent = destinations.snapshot_parent if destinations else None
    if args.release_dir is not None:
        release = local_release(args.release_dir, version, pins, parent)
        args.resolved_release_dir_version = release.version
        return release
    if version is None:
        version = _default_version(args, pins)
    candidates = _alias_releases(args)
    if version in candidates:
        return local_release(candidates[version], version, pins, parent)
    return _cache(args, pins).resolve(version, snapshot_parent=parent,
                                      read_only=destinations is not None)


def _release(args):
    """What `bootstrap` and `update` install."""
    return _resolve(args, args.release_version)


def _release_for_target(args):
    """The release a *report* about `args.target` should be measured against.

    An installed repository is graded against the release it records, not
    against whatever happens to be newest -- otherwise every target would look
    broken the moment a new release was published.
    """
    if args.release_version is not None:
        return _resolve(args, args.release_version)
    if not is_managed(args.target):
        return None
    return _resolve(args, Installation.read(args.target).workflow_version)


def _describe_source(record: dict | None) -> str:
    if record is None:
        return "not recorded"
    if record.get("kind") == "local":
        return "(local, unpublished)"
    return (f"package {record.get('archive')} from {record.get('repository')} "
            f"(sha256 {record.get('sha256')})")


def _print_record(target: Path) -> None:
    """What `status` knows about a managed target without its release."""
    installation = Installation.read(target)
    print(f"workflow {installation.workflow_version} ({installation.profile} profile)")
    print(f"  source: {_describe_source(installation.source)}")
    print(f"  installed at {installation.installed_at}, updated at {installation.updated_at}")


def _context(args, *, with_data: bool = False) -> advice.Context:
    """The facts a `next:` line needs that the error and `args` do not hold.

    The installed version and source come from the record, best effort. The
    Workflow data facts are cheap `lexists()` checks, except the full findings
    list (it costs Git), which is computed only when `with_data` and the target
    holds Workflow data."""
    target = getattr(args, "target", None)
    try:
        cache = str(cache_root(getattr(args, "release_cache", None)))
    except RuntimeError:    # no home directory: the cache path is only named in a step
        cache = None
    base = dict(args=args, release_dir_version=getattr(args, "resolved_release_dir_version", None),
                cache_dir=cache)
    if target is None:
        return advice.Context(**base)
    installed, local = None, False
    try:
        if is_managed(target):
            record = Installation.read(target)
            installed = record.workflow_version
            local = bool(record.source) and record.source.get("kind") == "local"
    except Exception:  # noqa: BLE001 -- best effort: a damaged record is the error itself
        pass
    holds, missing = holds_data(target), missing_templates(target)
    findings, files = (), ()
    if with_data and holds:
        findings = data_findings(target)
        files = data_files(target, missing, findings)
    return advice.Context(installed_version=installed, installed_local=local, holds_data=holds,
                          missing_templates=missing, data_findings=findings, data_files=files,
                          **base)


def cmd_releases(args) -> int:
    pins = _pins()
    cache = ReleaseCache(cache_root(args.release_cache), None, pins)
    for version in pins.versions():
        pin = pins.get(version)
        state = "cached" if cache.cached(version) else "not cached"
        print(f"{version}  {pin.archive}  sha256 {pin.sha256}  [{state}]")
    candidates = _alias_releases(args)
    for version in candidates:
        if pins.get(version) is not None:
            continue
        release = Release(candidates[version])
        print(f"{release.version}  (--manager-root, unpublished)  from {release.upstream['tag']} "
              f"({release.upstream['commit'][:12]})  "
              f"[{release.provenance['origin']}]  "
              f"{len(release.installable(INSTALL_PROFILE_FULL))} files")
    if not pins.versions() and not candidates:
        print("workflow-manager: no Workflow release is published",
              file=sys.stderr)
    return 0


def _print_error(args, error, text=None) -> None:
    """The cause on stderr, then the error's `next:` line when the table has one."""
    print(text if text is not None else f"error: {error}", file=sys.stderr)
    context = _context(args, with_data=advice.needs_data(error, args))
    step = advice.next_step(error, context)
    if step is not None:
        print(f"next: {step}", file=sys.stderr)


def _print_in_flight(args) -> None:
    for line in render_work_in_flight(read_work_items(args.target), str(args.target)):
        print(line)


def cmd_status(args) -> int:
    if not is_managed(args.target):
        # Unchanged: nothing is resolved without --release-version, and no
        # destination check or Git runs (3.5a, 3.6).
        release = _release_for_target(args)
        with release if release is not None else nullcontext():
            result = status(args.target, release)
        print(result)
        print(f"next: {advice.unmanaged_status_step(_context(args, with_data=True))}")
        return 0
    # A managed target: the record and the work in flight are read first, then the
    # destinations are validated before anything is resolved, so `status` writes
    # nothing in the repository or its `.git` directory (3.5a).
    installed = Installation.read(args.target).workflow_version
    try:
        destinations = _readonly_destinations(args, installed)
        release = _resolve(args, args.release_version or installed, destinations)
    except ContainmentError as error:
        _print_record(args.target)
        _print_in_flight(args)
        _print_error(args, error)
        return 1
    except RELEASE_ERRORS:
        _print_record(args.target)
        _print_in_flight(args)
        raise
    with release:
        result = status(args.target, release)
    print(result)
    print(f"  source: {_describe_source(Installation.read(args.target).source)}")
    _print_in_flight(args)
    context = _context(args, with_data=bool(result.problems))
    step = advice.problem_step(context, result.problems)
    doctor = advice.doctor_step(context)
    print(f"next: {step + '; ' + doctor if step is not None else doctor}")
    return 0 if (result.verified and not result.problems) else 1


def cmd_bootstrap(args) -> int:
    with _release(args) as release:
        installation = bootstrap(args.target, release, args.profile, force=args.force)
    print(f"bootstrapped workflow {installation.workflow_version} "
          f"({installation.profile}) into {args.target}")
    print(f"  {len(installation.managed)} managed files, "
          f"{len(installation.generated)} state files, "
          f"{len(installation.merged)} merged files")
    print(f"next: {advice.success_step(_context(args))}")
    return 0


def _readonly_destinations(args, installed: str | None) -> Destinations:
    """Decide, before anything is written, where the cache and the snapshot go
    (plan 3.6). The versions are the releases the resolver will open."""
    pins = _pins()
    versions = []
    if args.release_dir is None:
        try:
            versions.append(args.release_version or _default_version(args, pins))
        except ReleaseNotPublishedError:
            pass
    if installed and isinstance(installed, str):    # a number names no cache entry
        versions.append(installed)
    return plan_destinations(args, os.environ, args.target, versions)


_DRY_VERBS = {"removed": "would remove", "added": "would add", "updated": "would update",
              "fixed": "would fix", "created": "would create", "appended": "would append",
              "replaced": "would replace", "prepended": "would prepend"}


def _would(change: str) -> str:
    verb, _, rest = change.partition(" ")
    if verb not in _DRY_VERBS:
        raise ValueError(f"no dry-run verb for the change {change!r}; add {verb!r} to _DRY_VERBS")
    return f"{_DRY_VERBS[verb]} {rest}"


def _print_dry_run(args, plan, release) -> None:
    print(f"would update {args.target} from workflow {plan.current.workflow_version} to "
          f"workflow {release.version}     (dry run: nothing written)")
    overwrites = set(plan.overwrites)
    for change in plan.changes:
        note = ""
        if change.split(" ", 1)[-1] in overwrites:
            note = "     (discards your local edit; --force)"
        print(f"  {_would(change)}{note}")
    if not plan.changes:
        print("  (no change)")
    print("left alone:")
    for kept in plan.left_alone:
        print(f"  {kept.path}   {kept.reason}")


def _compatibility_report(args, plan, refusal, release, installed_resolved: bool):
    """The report for `release` as the target, with the facts read from `args.target`."""
    pins = _pins()
    versions = pins.versions()
    try:
        latest = _default_version(args, pins)
    except ReleaseNotPublishedError:
        latest = None
    facts = read_repository(args.target)
    return build_report(
        facts, plan, target_version=release.version, latest_version=latest,
        pinned_versions=versions, refusal=refusal, installed_resolved=installed_resolved,
        target_arg=str(args.target))


def _plan_or_refusal(args, release):
    try:
        return plan_update(args.target, release, args.profile, force=args.force), None
    except (DriftError, CollisionError) as refusal:
        return None, refusal


def cmd_dry_run(args) -> int:
    """`update --dry-run`: the plan `update` would apply, printed; the same
    refusals (exit 2) as the real update, with the report printed first."""
    if not is_managed(args.target):
        raise NotManagedError(not_managed_text(args.target))
    installed = Installation.read(args.target).workflow_version
    destinations = _readonly_destinations(args, installed)
    with _resolve(args, args.release_version, destinations) as release:
        plan, refusal = _plan_or_refusal(args, release)
        installed_resolved = _installed_resolves(args, installed, destinations)
        if plan is not None:
            _print_dry_run(args, plan, release)
            print()
        report = _compatibility_report(args, plan, refusal, release, installed_resolved)
        print(render_report(report), end="")
    if refusal is not None:
        raise refusal
    return 0


def _installed_resolves(args, installed: str, destinations: Destinations) -> bool:
    """Whether the installed release can be resolved (`not-verified` when not).

    Always through the cache: `--release-dir` and `--manager-root` are not
    consulted, so an offline run with them may add a `not-verified` note.
    """
    if not isinstance(installed, str):
        return False        # a number or a boolean names no cache entry
    try:
        _cache(args, _pins()).resolve(
            installed, snapshot_parent=destinations.snapshot_parent, read_only=True).close()
    except RELEASE_ERRORS:
        return False
    return True


def cmd_doctor(args) -> int:
    """Report what an update would meet. Exit 0 with no blocked or warning
    finding, 1 with one, 2 when it could not check."""
    if not is_managed(args.target):
        raise NotManagedError(not_managed_text(args.target))
    installed = Installation.read(args.target).workflow_version
    destinations = _readonly_destinations(args, installed)
    try:
        release = _resolve(args, args.release_version, destinations)
    except RELEASE_ERRORS as error:
        print(f"error: could not resolve the target release: {error}", file=sys.stderr)
        step = advice.next_step(error, _context(args))
        if step is not None:
            print(f"next: {step}", file=sys.stderr)
        return 2
    with release:
        plan, refusal = _plan_or_refusal(args, release)
        installed_resolved = _installed_resolves(args, installed, destinations)
        report = _compatibility_report(args, plan, refusal, release, installed_resolved)
    print(render_report(report), end="")
    return report.doctor_exit_code


def cmd_update(args) -> int:
    if args.dry_run:
        return cmd_dry_run(args)
    with _release(args) as release:
        installation, changes = update(args.target, release, args.profile, force=args.force)
    print(f"updated {args.target} to workflow {installation.workflow_version}")
    for change in changes:
        print(f"  {change}")
    if not changes:
        print("  (no change)")
    print(f"next: {advice.success_step(_context(args))}")
    return 0


def cmd_verify(args) -> int:
    release = _release_for_target(args)
    if release is None:
        raise NotManagedError(not_managed_text(args.target))
    with release:
        problems = verify(args.target, release)
    if not problems:
        print(f"{args.target}: installation matches workflow {release.version}")
        return 0
    print(f"{args.target}: {len(problems)} problem(s)")
    for problem in problems:
        print(f"  {problem}")
    print(f"next: {advice.problem_step(_context(args, with_data=True), problems)}")
    return 1


def cmd_uninstall(args) -> int:
    removed = uninstall(args.target)
    print(f"removed {len(removed)} managed files from {args.target}")
    print("repository-local state (WORKFLOW_STATE.json, ACTIVE_MILESTONE.md) was kept")
    return 0


def cmd_package(args) -> int:
    if args.package_command == "build":
        built = build_package(args.release_dir, args.out)
        for path in (built.archive, built.manifest, built.sums):
            print(path)
        return 0
    if args.sha256 is not None:
        actual = file_sha256(args.archive)
        if actual != args.sha256.lower():
            raise ReleaseIntegrityError(f"{args.archive} has digest {actual}, not {args.sha256}",
                                        kind="package")
    with tempfile.TemporaryDirectory(prefix="workflow-package-") as tmp:
        release = extract_package(args.archive, Path(tmp) / "tree")
        print(f"{args.archive}: release {release.version}, "
              f"{len(release.artifacts) + len(release.templates())} files, verified")
    return 0


COMMANDS = {
    "releases": cmd_releases,
    "status": cmd_status,
    "bootstrap": cmd_bootstrap,
    "update": cmd_update,
    "doctor": cmd_doctor,
    "verify": cmd_verify,
    "uninstall": cmd_uninstall,
    "package": cmd_package,
}


class _Parser(argparse.ArgumentParser):
    """Names the program `workflow-manager` in every message and, when a global
    option was written after the command (A1), ends the error with the pattern
    that puts it first. Subcommand parsers are instances of it too."""

    def parse_args(self, args=None, namespace=None):
        self._argv = list(sys.argv[1:] if args is None else args)
        return super().parse_args(args, namespace)

    def _command_word(self) -> str | None:
        """The first word of the arguments that is a subcommand: not an option,
        and not the value of one of the global options before it."""
        valued = {option for option, _ in advice.GLOBAL_OPTIONS} | {"--manager-root"}
        skip = False
        for token in getattr(self, "_argv", []):
            if skip:
                skip = False
            elif token in valued:
                skip = True
            elif not token.startswith("-"):
                return token if token in COMMANDS else None
        return None

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n" + self._hint(message))

    def _hint(self, message: str) -> str:
        prefix = "unrecognized arguments: "
        if not message.startswith(prefix):
            return ""
        misplaced = advice.misplaced_global_options(message[len(prefix):].split())
        if not misplaced:
            return ""
        return f"next: {advice.global_option_step(misplaced, self._command_word())}\n"


_GLOBAL_OPTIONS_NOTE = "Global options go before the command."

_EXIT_CODES = (
    "Exit codes: 0 succeeded; 1 a problem was found, or no usable release; 2 the command "
    "line did not parse, or the command refused to run. The table per command is at "
    + advice.page("exit-codes.md") + ".")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=advice.PROGRAM, description=__doc__,
        epilog=_GLOBAL_OPTIONS_NOTE + " " + _EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--manager-root", type=Path, default=None,
                        help="deprecated: a workflow-manager checkout holding "
                             "distribution/workflow/<version>/")
    parser.add_argument("--version", action=_VersionAction)
    parser.add_argument("--release-version", default=None,
                        help="the Workflow release to use; goes before the command "
                             "(default: bootstrap and update use the newest published "
                             "release, status and verify the release the target records)")
    parser.add_argument("--release-source", default=None,
                        help="where packages come from: a URL template with {version}, "
                             f"or a directory of <version>/ (default: ${release_source.SOURCE_ENV}, "
                             "else the published releases); goes before the command")
    parser.add_argument("--release-cache", default=None,
                        help=f"the release cache directory (default: ${release_source.CACHE_ENV}, "
                             "else the user cache directory); goes before the command")
    parser.add_argument("--release-dir", type=Path, default=None,
                        help="install an unpackaged release directory instead of a package; "
                             "goes before the command")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def command(name, summary, description):
        return sub.add_parser(name, help=summary, description=description + " " + _EXIT_CODES,
                              epilog=_GLOBAL_OPTIONS_NOTE)

    p = command("releases", "list published releases",
                "List the Workflow releases this Manager pins and whether each is in the "
                "release cache. Reads the pin file and the cache; writes nothing. "
                "Exit 0 when it lists.")

    p = command("package", "build or verify a Workflow release package",
                "`package build DIR --out OUT` writes a release directory's package, its "
                "manifest asset and SHA256SUMS to OUT. `package verify ARCHIVE [--sha256 H]` "
                "checks an archive against its manifest, and against H when given, in a "
                "temporary directory. Neither touches a repository. Exit 0 when it finishes, "
                "1 when the directory or archive is not a valid release.")
    package_sub = p.add_subparsers(dest="package_command", required=True, metavar="ACTION")
    q = package_sub.add_parser("build", help="build a package from a release directory",
                               description="Build the package, its manifest asset and "
                                           "SHA256SUMS from a release directory (the one "
                                           "holding manifest.json) into --out.")
    q.add_argument("release_dir", type=Path, help="the release directory holding manifest.json")
    q.add_argument("--out", type=Path, required=True, help="where to write the three files")
    q = package_sub.add_parser("verify", help="check a package archive",
                               description="Extract the archive into a temporary directory and "
                                           "check every file against its manifest.")
    q.add_argument("archive", type=Path, help="the package archive to check")
    q.add_argument("--sha256", default=None, help="also require the archive to have this digest")

    p = command("doctor", "report what an update would meet in a repository",
                "Read a repository and report what an update would do and which Workflow "
                "guarantees it would cross. Writes the release cache and a temporary snapshot "
                "outside the repository, never the repository. Exit 0: no blocked or warning "
                "finding (notes alone still exit 0); 1: a blocked or warning finding, an "
                "incomplete inspection included; 2: could not check.")
    p.add_argument("target", type=Path, help="the managed repository to inspect")
    p.set_defaults(profile=None, force=False)

    p = command("status", "show a repository's installation and whether it is intact",
                "Print the release a managed repository records, its source, and whether its "
                "files match that release. Writes nothing in the repository. Exit 0: intact, "
                "or not managed; 1: problems found or no usable release; 2: the record is "
                "unreadable.")
    p.add_argument("target", type=Path, help="the repository to look at")

    p = command("verify", "check that a repository matches its installed release",
                "Compare a managed repository's installed files with its release and list "
                "every difference. Writes nothing. Exit 0: matches; 1: problems found or no "
                "usable release; 2: the repository is not managed or its record is unreadable.")
    p.add_argument("target", type=Path, help="the managed repository to check")

    p = command("uninstall", "remove the files the Manager installed",
                "Remove the files the installation record lists and the record itself. "
                "Repository-local state (WORKFLOW_STATE.json, ACTIVE_MILESTONE.md and the like) "
                "is kept. Exit 0: removed; 2: the repository is not managed or its record is "
                "unreadable.")
    p.add_argument("target", type=Path, help="the managed repository to uninstall")

    p = command("bootstrap", "install the Workflow into a Git repository",
                "Install a Workflow release into a Git repository that is not yet managed: the "
                "release's files, blank state templates where none exist, the merged "
                "CLAUDE.md and .gitignore entries, and the installation record. Writes the "
                "repository. Exit 0: installed; 2: refused (not a repository, already "
                "managed, files in the way).")
    p.add_argument("target", type=Path, help="the Git repository to install into")
    p.add_argument("--profile", choices=INSTALL_PROFILES, default=INSTALL_PROFILE_FULL,
                   help="which files to install (default: %(default)s)")
    p.add_argument("--force", action="store_true",
                   help="overwrite files the repository already keeps at release paths")

    p = command("update", "move a managed repository to another release",
                "Move a managed repository to the newest published release, or to "
                "--release-version (which goes before the command). Writes the repository "
                "unless --dry-run. Exit 0: updated; 2: refused (not managed, files edited "
                "locally, paths in use).")
    p.add_argument("target", type=Path, help="the managed repository to update")
    p.add_argument("--profile", choices=INSTALL_PROFILES, default=None,
                   help="which files to install (default: the one the record names)")
    p.add_argument("--force", action="store_true",
                   help="overwrite managed files that were modified locally")
    p.add_argument("--dry-run", action="store_true",
                   help="print what the update would do and the compatibility report; writes the "
                        "release cache and a temporary snapshot outside the repository, never "
                        "the repository")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.manager_root is not None:
        print(MANAGER_ROOT_DEPRECATION, file=sys.stderr)

    def fail(error, code, text=None):
        _print_error(args, error, text)
        return code

    try:
        return COMMANDS[args.command](args)
    except RELEASE_ERRORS as error:
        return fail(error, 1)
    except (DriftError, CollisionError) as error:
        # These two print without the `error:` prefix: their first words are
        # quoted by the documentation.
        return fail(error, 2, text=str(error))
    except (AlreadyManagedError, NotManagedError, InstallError, CorruptInstallationError,
            FileNotFoundError, ValueError) as error:
        return fail(error, 2)
    except OSError as error:
        return fail(error, 1)


if __name__ == "__main__":
    raise SystemExit(main())
