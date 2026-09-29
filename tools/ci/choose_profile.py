#!/usr/bin/env python3
"""Choose a verification run's test profile (`D-PR-Profile`, plan 6.2).

    choose_profile.py --event EVENT [--repo OWNER/NAME] [--repo-dir DIR] [--rules FILE]

Writes `profile=full` or `profile=newest-release` to `$GITHUB_OUTPUT` and a
reasons table to `$GITHUB_STEP_SUMMARY` (to stdout when either is unset).
The decision:

1. any event other than `pull_request` is `full`;
2. rule 1: every path `git diff --name-only --no-renames -z HEAD^1 HEAD`
   lists over the pull request's merge ref is classified by
   `pr_profile_paths.json` (exact paths or directory prefixes ending in
   `/`, longest match wins, an unmatched path is `full`); any `full` path
   makes the run `full`. A `HEAD` that is not a two-parent merge, or a git
   failure, is `full`;
3. rule 5: the newest completed `push` or `schedule` run of the
   verification workflow on `main` must have concluded `success`; a red,
   cancelled or missing run, or an API or parse failure, is `full`;
4. otherwise `newest-release`.

Every undecidable input chooses `full` (INV-4). Exit codes: 0 a profile was
chosen; 1 the output could not be written; 2 usage error.
"""

# STOPGAP(M2): the pull-request profile chooser; see docs/ARCHITECTURE.md's
# "Stopgap test profile". M2 deletes this file.

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

RULES_PATH = Path(__file__).resolve().parent / "pr_profile_paths.json"

FULL = "full"
NEWEST_RELEASE = "newest-release"
PROFILES = (FULL, NEWEST_RELEASE)

VERIFY_WORKFLOW = "workflow-manager-verify.yml"
#: The events of a full run on `main` whose result rule 5 reads.
MAIN_EVENTS = ("push", "schedule")
GIT_TIMEOUT = 60
GH_TIMEOUT = 60
#: Summary rows beyond this many paths are counted, not listed.
MAX_SUMMARY_PATHS = 300


class ProfileError(Exception):
    """An input the chooser cannot read; the caller turns it into `full`."""


class UsageError(Exception):
    """A malformed invocation. Exit 2."""


# -- path rules ------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    path: str
    profile: str
    reason: str

    def matches(self, path: str) -> bool:
        return path.startswith(self.path) if self.path.endswith("/") else path == self.path


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    """The rules of `pr_profile_paths.json`, validated; `ProfileError` on any
    malformed entry, so a broken rule file can never narrow a run."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProfileError(f"cannot read {path}: {exc}") from exc
    entries = doc.get("rules") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ProfileError(f"{path}: 'rules' must be a non-empty list")
    rules: list[Rule] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "profile", "reason"}:
            raise ProfileError(f"{path}: malformed rule {entry!r}")
        rule = Rule(entry["path"], entry["profile"], entry["reason"])
        if not isinstance(rule.path, str) or not rule.path or rule.path.startswith("/"):
            raise ProfileError(f"{path}: rule path must be a relative path: {rule.path!r}")
        if rule.profile not in PROFILES:
            raise ProfileError(f"{path}: rule {rule.path!r} has unknown profile {rule.profile!r}")
        if not isinstance(rule.reason, str) or not rule.reason.strip():
            raise ProfileError(f"{path}: rule {rule.path!r} gives no reason")
        if rule.path in seen:
            raise ProfileError(f"{path}: duplicate rule {rule.path!r}")
        seen.add(rule.path)
        rules.append(rule)
    return rules


def match_rule(path: str, rules: list[Rule]) -> Rule | None:
    """The longest rule matching `path`, or None."""
    hits = [rule for rule in rules if rule.matches(path)]
    return max(hits, key=lambda rule: len(rule.path)) if hits else None


def classify(path: str, rules: list[Rule]) -> tuple[str, str]:
    """`(profile, reason)` for one path; an unmatched path is `full`."""
    rule = match_rule(path, rules)
    if rule is None:
        return FULL, "unclassified: no rule matches this path"
    return rule.profile, f"`{rule.path}`: {rule.reason}"


# -- git -------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProfileError(f"git {' '.join(args)} failed: {exc}") from exc
    if proc.returncode != 0:
        raise ProfileError(f"git {' '.join(args)} failed: "
                           f"{proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def _split_z(raw: bytes) -> list[str]:
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def changed_paths(repo: Path) -> list[str]:
    """Both sides of every change between the merge ref's base parent and
    itself: `HEAD` must be a two-parent merge (a pull request's merge ref)."""
    parents = _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) != 3:
        raise ProfileError(f"HEAD is not a two-parent merge ({len(parents) - 1} parents)")
    return sorted(set(_split_z(
        _git(repo, "diff", "--name-only", "--no-renames", "-z", "HEAD^1", "HEAD"))))


def tree_paths(repo: Path) -> list[str]:
    """Every tracked path plus every untracked, unignored one: the tree as
    `tests/parallel/tree.py`'s `tree_digest` sees it."""
    tracked = _split_z(_git(repo, "ls-files", "-z"))
    untracked = _split_z(_git(repo, "ls-files", "-z", "--others", "--exclude-standard"))
    return sorted(set(tracked) | set(untracked))


# -- main's health ---------------------------------------------------------------


def main_health(runs) -> tuple[bool, str]:
    """Whether the newest `push`/`schedule` run in `runs` succeeded, and why.

    `runs` is the API's `workflow_runs` list. Other events are ignored; the
    newest run is the highest run id. A malformed list or run, or no run,
    is unhealthy.
    """
    if not isinstance(runs, list):
        return False, "the run list is malformed"
    newest = None
    for run in runs:
        if not isinstance(run, dict):
            return False, f"malformed run {run!r}"
        if run.get("event") not in MAIN_EVENTS:
            continue
        run_id = run.get("id")
        if not isinstance(run_id, int) or isinstance(run_id, bool):
            return False, f"malformed run id {run_id!r}"
        if newest is None or run_id > newest["id"]:
            newest = run
    if newest is None:
        return False, "no completed push or schedule run on main"
    described = f"run {newest['id']} ({newest['event']}) concluded {newest.get('conclusion')!r}"
    if newest.get("status") != "completed" or newest.get("conclusion") != "success":
        return False, f"main is not green: {described}"
    return True, f"main is green: {described}"


def fetch_main_runs(repo_slug: str, *, workflow: str = VERIFY_WORKFLOW) -> list:
    endpoint = (f"/repos/{repo_slug}/actions/workflows/{workflow}/runs"
                "?branch=main&status=completed&per_page=30")
    try:
        proc = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True,
                              timeout=GH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProfileError(f"gh api {endpoint} failed: {exc}") from exc
    if proc.returncode != 0:
        raise ProfileError(f"gh api {endpoint} failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)["workflow_runs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ProfileError(f"cannot parse the run list: {exc}") from exc


# -- the decision ----------------------------------------------------------------


@dataclass
class Decision:
    profile: str
    #: `(input, profile, reason)` rows, in the order they were decided.
    reasons: list[tuple[str, str, str]] = field(default_factory=list)


def decide(
    event: str,
    rules: list[Rule],
    get_paths: Callable[[], list[str]],
    get_runs: Callable[[], list],
) -> Decision:
    """The profile for one run. `get_paths` and `get_runs` are called only
    when needed, and any `ProfileError` they raise chooses `full`."""
    if event != "pull_request":
        return Decision(FULL, [(f"event `{event}`", FULL, "only a pull request runs a reduced profile")])
    decision = Decision(NEWEST_RELEASE, [(f"event `{event}`", NEWEST_RELEASE, "pull request")])
    try:
        paths = get_paths()
    except ProfileError as exc:
        decision.profile = FULL
        decision.reasons.append(("changed paths", FULL, f"undecidable: {exc}"))
        return decision
    for path in paths:
        profile, reason = classify(path, rules)
        decision.reasons.append((f"`{path}`", profile, reason))
        if profile == FULL:
            decision.profile = FULL
    if not paths:
        decision.reasons.append(("changed paths", NEWEST_RELEASE, "the merge changes no path"))
    if decision.profile == FULL:
        decision.reasons.append(("main's health", FULL, "not consulted: a path already needs full"))
        return decision
    try:
        healthy, why = main_health(get_runs())
    except ProfileError as exc:
        healthy, why = False, f"undecidable: {exc}"
    decision.reasons.append(("main's health", NEWEST_RELEASE if healthy else FULL, why))
    if not healthy:
        decision.profile = FULL
    return decision


# -- output ----------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def summary_markdown(decision: Decision) -> str:
    lines = [f"### Test profile: `{decision.profile}`", "",
             "| input | profile | reason |", "| --- | --- | --- |"]
    rows = decision.reasons
    paths = [row for row in rows if row[0].startswith("`")]
    hidden = 0
    if len(paths) > MAX_SUMMARY_PATHS:
        # Keep every path that chose full, then as many others as fit.
        keep = {id(row) for row in paths if row[1] == FULL}
        for row in paths:
            if len(keep) >= MAX_SUMMARY_PATHS:
                break
            keep.add(id(row))
        hidden = len(paths) - len(keep)
        rows = [row for row in rows if not row[0].startswith("`") or id(row) in keep]
    lines += [f"| {_cell(a)} | {b} | {_cell(c)} |" for a, b, c in rows]
    if hidden:
        lines.append(f"| {hidden} more paths | {NEWEST_RELEASE} | not listed |")
    return "\n".join(lines) + "\n"


def _append(env_var: str, text: str) -> None:
    target = os.environ.get(env_var)
    if not target:
        sys.stdout.write(text)
        return
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(text)


# -- CLI -------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="choose_profile.py", description=__doc__.splitlines()[0])
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--repo", help="owner/name, for gh api (needed for pull_request)")
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--rules", type=Path, default=RULES_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        if args.event == "pull_request" and not args.repo:
            raise UsageError("--repo is required for a pull_request event")
    except UsageError as exc:
        print(f"choose_profile.py: usage error: {exc}", file=sys.stderr)
        return 2

    def get_paths() -> list[str]:
        return changed_paths(args.repo_dir)

    def get_runs() -> list:
        return fetch_main_runs(args.repo)

    try:
        rules = load_rules(args.rules)
    except ProfileError as exc:
        rules = []
        broken = str(exc)
    else:
        broken = None
    decision = decide(args.event, rules, get_paths, get_runs)
    if broken is not None:
        decision.profile = FULL
        decision.reasons.append(("path rules", FULL, f"undecidable: {broken}"))
    try:
        _append("GITHUB_OUTPUT", f"profile={decision.profile}\n")
        _append("GITHUB_STEP_SUMMARY", summary_markdown(decision))
    except OSError as exc:
        print(f"choose_profile.py: cannot write the output: {exc}", file=sys.stderr)
        return 1
    print(f"profile: {decision.profile}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
