#!/usr/bin/env python3
"""Conventional Commit titles and tag-derived versions for the Workflow Manager.

The one implementation both the pull-request title check and the release
workflow call (`D-Title-Grammar`, `D-Version-Authority`). Stdlib only.

The Git tag is the only version authority: no file in the repository holds
the Manager's release version. `pyproject.toml` carries the placeholder
`0.0.0.dev0`, which `set-version` rewrites in a temporary copy at build time.

Subcommands:

    check-title TITLE          validate a pull-request title, print its impact
    next-version               print the next release version, or nothing
    assert-not-superseded      refuse when a strict tag is not an ancestor of HEAD
    resolve-target ...         pick the newest green push run on main's first parent
    set-version DIR VERSION    rewrite DIR/pyproject.toml's single placeholder

Exit codes: 0 success; 1 invalid title, refusal or failure; 2 usage error;
3 superseded (`assert-not-superseded`: already covered by a newer release).
Every undecidable input refuses rather than releasing (INV-4).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_SUPERSEDED = 3

#: SignalHub's title grammar, applied to the stripped subject.
TITLE_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9._/-]+)\))?(?P<breaking>!)?: (?P<description>\S.*)$"
)
#: A looser shape used only to name what is wrong with an invalid title.
_LOOSE_TITLE_RE = re.compile(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:(?P<rest>.*)$")

MAJOR, MINOR, PATCH, NONE = "major", "minor", "patch", "none"
_IMPACT_RANK = {NONE: 0, PATCH: 1, MINOR: 2, MAJOR: 3}

#: Release impact per type (plan 5.1; `OD-2` for the types the brief does not
#: name). A type that can change what the wheel ships or how it is built
#: releases; a type that cannot does not. `!` on any type is a major release.
TYPE_IMPACT = {
    "feat": MINOR,
    "fix": PATCH,
    "perf": PATCH,
    "refactor": PATCH,
    "build": PATCH,
    "revert": PATCH,
    "docs": NONE,
    "chore": NONE,
    "ci": NONE,
    "test": NONE,
    "style": NONE,
}

ACCEPTED_FORM = (
    "expected '<type>[(<scope>)][!]: <description>', type one of "
    + ", ".join(sorted(TYPE_IMPACT))
)

#: Only strict `vX.Y.Z` tags count (SignalHub's `TAG_RE`).
TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
#: `set-version` accepts `X.Y.Z` or `X.Y.Z+local`, never a `v` prefix.
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(\+[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?$")

#: The last hand-versioned release: `1.0.0` at this milestone's base commit.
#: Used only while no strict tag is reachable from HEAD (`OD-1`).
BASELINE_VERSION = (1, 0, 0)
BASELINE_COMMIT = "b856a97346849fdf48bcdba2d6a5a9644699ab4b"

PLACEHOLDER_LINE = 'version = "0.0.0.dev0"'

VERIFY_WORKFLOW = "workflow-manager-verify.yml"
GIT_TIMEOUT = 60
GH_TIMEOUT = 60


class ReleaseError(Exception):
    """A refusal: the release must not proceed. Exit 1."""


class SupersededError(ReleaseError):
    """A strict tag sits on a commit HEAD does not contain. Exit 3."""


class UsageError(Exception):
    """A malformed invocation. Exit 2."""


def _warn(message: str) -> None:
    print(f"::warning::{message}", file=sys.stderr)


# -- titles ----------------------------------------------------------------------


@dataclass(frozen=True)
class Title:
    type: str
    scope: str | None
    breaking: bool
    description: str

    @property
    def impact(self) -> str:
        return MAJOR if self.breaking else TYPE_IMPACT[self.type]


class InvalidTitle(ValueError):
    """A title that is not a Conventional Commit; the message names why."""


def parse_title(title: str) -> Title:
    subject = title.strip()
    match = TITLE_RE.match(subject)
    if match and match["type"] in TYPE_IMPACT:
        return Title(match["type"], match["scope"], bool(match["breaking"]), match["description"])
    raise InvalidTitle(_diagnose(subject))


def _diagnose(subject: str) -> str:
    loose = _LOOSE_TITLE_RE.match(subject)
    if not loose:
        return "no 'type: description' shape"
    type_ = loose["type"]
    if type_ != type_.lower():
        return f"type '{type_}' must be lowercase"
    if type_ not in TYPE_IMPACT:
        return f"unknown type '{type_}'"
    scope = loose["scope"]
    if scope is not None:
        if scope == "":
            return "empty scope '()'"
        if not re.fullmatch(r"[a-z0-9._/-]+", scope):
            return f"scope '{scope}' may only contain a-z, 0-9, '.', '_', '/' and '-'"
    rest = loose["rest"]
    if not rest.strip():
        return "empty description"
    if not rest.startswith(" "):
        return "no space after the colon"
    return "more than one space after the colon"


def title_impact(subject: str) -> tuple[str, bool]:
    """Impact of a first-parent subject, and whether it was Conventional.

    A non-Conventional subject can only reach `main` through a bypass. It
    counts as a patch, so it is released rather than lost.
    """
    try:
        return parse_title(subject).impact, True
    except InvalidTitle:
        return PATCH, False


# -- git -------------------------------------------------------------------------


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseError(f"git {' '.join(args)} failed: {exc}") from exc
    if check and proc.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    proc = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise ReleaseError(
        f"cannot decide whether {ancestor} is an ancestor of {descendant}: {proc.stderr.strip()}"
    )


def parse_tag(tag: str) -> tuple[int, int, int] | None:
    match = TAG_RE.match(tag)
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def strict_tags(tags: Iterable[str]) -> dict[str, tuple[int, int, int]]:
    return {tag: version for tag in tags if (version := parse_tag(tag)) is not None}


def format_version(version: tuple[int, int, int]) -> str:
    return "%d.%d.%d" % version


def bump(version: tuple[int, int, int], impact: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if impact == MAJOR:
        return (major + 1, 0, 0)
    if impact == MINOR:
        return (major, minor + 1, 0)
    if impact == PATCH:
        return (major, minor, patch + 1)
    raise ValueError(f"no release for impact {impact!r}")


# -- next-version ----------------------------------------------------------------


def next_version(
    repo: Path,
    *,
    baseline: tuple[tuple[int, int, int], str] = (BASELINE_VERSION, BASELINE_COMMIT),
    warn: Callable[[str], None] = _warn,
) -> str | None:
    """The next release version at HEAD, or None when nothing releases.

    Base: the highest strict tag in `git tag --merged HEAD`; with none, the
    recorded baseline, which must be an ancestor of HEAD. The bump is the
    highest impact among the subjects of `git log --first-parent base..HEAD`.
    """
    merged = _git(repo, "tag", "--merged", "HEAD").stdout.split()
    tags = strict_tags(merged)
    if tags:
        base_tag = max(tags, key=tags.__getitem__)
        base_version, base_ref = tags[base_tag], f"refs/tags/{base_tag}"
    else:
        base_version, base_ref = baseline
        if not _is_ancestor(repo, base_ref, "HEAD"):
            raise ReleaseError(
                f"no strict vX.Y.Z tag is reachable and the baseline commit {base_ref} "
                "is not an ancestor of HEAD"
            )
    log = _git(repo, "log", "--first-parent", "--format=%s", f"{base_ref}..HEAD").stdout
    impact = NONE
    for subject in log.splitlines():
        subject_impact, conventional = title_impact(subject)
        if not conventional:
            warn(f"not a Conventional Commit subject, released as a patch: {subject!r}")
        if _IMPACT_RANK[subject_impact] > _IMPACT_RANK[impact]:
            impact = subject_impact
    if impact == NONE:
        return None
    return format_version(bump(base_version, impact))


# -- assert-not-superseded -------------------------------------------------------


def assert_not_superseded(repo: Path) -> None:
    """Refuse when any strict tag points to a commit that is not an ancestor
    of HEAD: an older green commit must never be tagged after a newer one."""
    for tag in sorted(strict_tags(_git(repo, "tag", "--list").stdout.split())):
        commit = _git(repo, "rev-list", "-n", "1", f"refs/tags/{tag}").stdout.strip()
        if not _is_ancestor(repo, commit, "HEAD"):
            raise SupersededError(f"tag {tag} ({commit}) is not an ancestor of HEAD")


# -- resolve-target --------------------------------------------------------------


def select_target(runs: list, first_parent: list[str]) -> tuple[str, int] | None:
    """The newest completed, successful `push` run on the first-parent chain.

    `first_parent` is `git rev-list --first-parent <main>` (tip first). Runs
    whose `head_sha` is off that chain are ignored. Several runs of one SHA
    resolve to the highest run id. Raises `ValueError` on a malformed run.
    """
    position = {sha: index for index, sha in enumerate(first_parent)}
    best: tuple[int, int, str] | None = None
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError(f"run is not an object: {run!r}")
        sha, run_id = run["head_sha"], run["id"]
        if not isinstance(sha, str) or not isinstance(run_id, int) or isinstance(run_id, bool):
            raise ValueError(f"malformed run: {run!r}")
        if run.get("event") != "push" or run.get("status") != "completed":
            continue
        if run.get("conclusion") != "success" or sha not in position:
            continue
        key = (-position[sha], run_id, sha)
        if best is None or key > best:
            best = key
    return None if best is None else (best[2], best[1])


def fetch_verify_runs(repo_slug: str, *, workflow: str = VERIFY_WORKFLOW) -> list:
    endpoint = (
        f"/repos/{repo_slug}/actions/workflows/{workflow}/runs"
        "?branch=main&status=completed&per_page=30"
    )
    try:
        proc = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True,
                              timeout=GH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseError(f"gh api {endpoint} failed: {exc}") from exc
    if proc.returncode != 0:
        raise ReleaseError(f"gh api {endpoint} failed: {proc.stderr.strip()}")
    try:
        runs = json.loads(proc.stdout)["workflow_runs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ReleaseError(f"cannot parse the run list: {exc}") from exc
    if not isinstance(runs, list):
        raise ReleaseError("cannot parse the run list: workflow_runs is not a list")
    return runs


def resolve_target(
    repo: Path,
    trigger_sha: str,
    trigger_run: int,
    fetch_runs: Callable[[], list],
    *,
    ref: str = "origin/main",
    warn: Callable[[str], None] = _warn,
) -> tuple[str, int]:
    """The commit and run a release job publishes (plan 5.2, 5.4).

    The pick must be the trigger or its descendant, else the release refuses.
    An API, parse or git failure falls back to the trigger itself -- a green
    push run by construction -- with a warning.
    """
    try:
        runs = fetch_runs()
        first_parent = _git(repo, "rev-list", "--first-parent", ref).stdout.split()
        picked = select_target(runs, first_parent)
    except (ReleaseError, ValueError, KeyError, TypeError) as exc:
        warn(f"resolve-target fell back to the triggering run {trigger_run} ({trigger_sha}): {exc}")
        return trigger_sha, trigger_run
    if picked is None:
        warn(f"no green push run on {ref}'s first parent; using the triggering run {trigger_run}")
        return trigger_sha, trigger_run
    sha, run_id = picked
    if sha != trigger_sha:
        try:
            descends = _is_ancestor(repo, trigger_sha, sha)
        except ReleaseError as exc:
            warn(f"resolve-target fell back to the triggering run {trigger_run} ({trigger_sha}): {exc}")
            return trigger_sha, trigger_run
        if not descends:
            raise ReleaseError(
                f"picked run {run_id} ({sha}) is neither the triggering commit {trigger_sha} "
                "nor its descendant"
            )
    return sha, run_id


# -- set-version -----------------------------------------------------------------


def set_version(directory: Path, version: str) -> None:
    """Rewrite the single placeholder line in `directory/pyproject.toml`.

    `directory` is a temporary copy of the project, never the checkout.
    """
    if not VERSION_RE.match(version):
        raise ReleaseError(f"version {version!r} is not X.Y.Z or X.Y.Z+local")
    if directory.resolve() == REPO_ROOT:
        raise ReleaseError("set-version rewrites a temporary copy, never the checkout")
    path = directory / "pyproject.toml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        raise ReleaseError(f"cannot read {path}: {exc}") from exc
    hits = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == PLACEHOLDER_LINE]
    if len(hits) != 1:
        raise ReleaseError(f"{path} has {len(hits)} placeholder lines {PLACEHOLDER_LINE!r}, expected 1")
    index = hits[0]
    ending = lines[index][len(PLACEHOLDER_LINE):]
    lines[index] = f'version = "{version}"{ending}'
    path.write_text("".join(lines), encoding="utf-8")


# -- CLI -------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="release.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    title = sub.add_parser("check-title", help="validate a Conventional Commit title")
    title.add_argument("title")

    for name in ("next-version", "assert-not-superseded"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--repo-dir", type=Path, default=Path.cwd())

    target = sub.add_parser("resolve-target")
    target.add_argument("--repo-dir", type=Path, default=Path.cwd())
    target.add_argument("--repo", required=True, help="owner/name, for gh api")
    target.add_argument("--trigger-sha", required=True)
    target.add_argument("--trigger-run", required=True, type=int)
    target.add_argument("--ref", default="origin/main")

    version = sub.add_parser("set-version")
    version.add_argument("directory", type=Path)
    version.add_argument("version")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        if args.command == "resolve-target" and not re.fullmatch(r"[0-9a-f]{40}", args.trigger_sha):
            raise UsageError(f"--trigger-sha must be a full 40-hex commit: {args.trigger_sha!r}")
    except UsageError as exc:
        print(f"release.py: usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        if args.command == "check-title":
            try:
                title = parse_title(args.title)
            except InvalidTitle as exc:
                print(f"invalid title: {exc}", file=sys.stderr)
                print(ACCEPTED_FORM, file=sys.stderr)
                return EXIT_FAIL
            print(f"valid title: {title.type}, release impact {title.impact}")
        elif args.command == "next-version":
            version = next_version(args.repo_dir)
            if version is not None:
                print(version)
        elif args.command == "assert-not-superseded":
            assert_not_superseded(args.repo_dir)
        elif args.command == "resolve-target":
            sha, run_id = resolve_target(
                args.repo_dir, args.trigger_sha, args.trigger_run,
                lambda: fetch_verify_runs(args.repo), ref=args.ref,
            )
            print(f"target_sha={sha}")
            print(f"target_run={run_id}")
        elif args.command == "set-version":
            set_version(args.directory, args.version)
    except SupersededError as exc:
        print(f"release.py: superseded: {exc}", file=sys.stderr)
        return EXIT_SUPERSEDED
    except ReleaseError as exc:
        print(f"release.py: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
