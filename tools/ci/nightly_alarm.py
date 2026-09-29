#!/usr/bin/env python3
"""Raise or clear the nightly full run's alarm (rule 5, "loud"; plan 6.4).

    nightly_alarm.py --event EVENT --result RESULT --repo OWNER/NAME --run-url URL

Run by the verification workflow's `nightly-alarm` job after `aggregate`.
For a `schedule` run whose `aggregate` result is not `success` it ensures
the `nightly-red` label exists, then opens an issue titled "Nightly full
verification failed" with that label, or comments on the open one. For a
green `schedule` run it closes every open `nightly-red` issue with a
comment. Any other event does nothing.

`decide` is the whole policy and is pure; the `gh` calls around it are a
thin shell. An unreadable issue list counts as no open issue, so a red
nightly still opens one. Exit codes: 0 every action succeeded; 1 a `gh`
call failed; 2 usage error.
"""

# STOPGAP(M2): the nightly full run's alarm; see docs/ARCHITECTURE.md's
# "Stopgap test profile". M2 deletes this file.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass

LABEL = "nightly-red"
LABEL_COLOR = "B60205"
LABEL_DESCRIPTION = "The nightly full verification run failed"
ISSUE_TITLE = "Nightly full verification failed"
GH_TIMEOUT = 60

ENSURE_LABEL, OPEN, COMMENT, CLOSE = "ensure-label", "open", "comment", "close"


class UsageError(Exception):
    """A malformed invocation. Exit 2."""


@dataclass(frozen=True)
class Action:
    kind: str
    issue: int | None = None
    body: str = ""


def decide(event: str, result: str, open_issues: list[int], run_url: str) -> list[Action]:
    """The actions for one run. `open_issues` are the numbers of the open
    `nightly-red` issues. Every red case ensures the label first, because
    `gh issue create --label` fails when the label is absent."""
    if event != "schedule":
        return []
    if result != "success":
        body = f"The nightly full verification run concluded `{result}`: {run_url}"
        if open_issues:
            return [Action(ENSURE_LABEL), Action(COMMENT, min(open_issues), body)]
        return [Action(ENSURE_LABEL), Action(OPEN, body=body)]
    body = f"The nightly full verification run is green again: {run_url}"
    return [Action(CLOSE, number, body) for number in sorted(open_issues)]


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)


def list_open_issues(repo: str) -> list[int]:
    proc = _gh("issue", "list", "--repo", repo, "--label", LABEL, "--state", "open",
               "--json", "number", "--limit", "100")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return [int(item["number"]) for item in json.loads(proc.stdout)]


def gh_args(action: Action, repo: str) -> list[str]:
    if action.kind == ENSURE_LABEL:
        return ["label", "create", LABEL, "--repo", repo, "--force",
                "--color", LABEL_COLOR, "--description", LABEL_DESCRIPTION]
    if action.kind == OPEN:
        return ["issue", "create", "--repo", repo, "--title", ISSUE_TITLE,
                "--label", LABEL, "--body", action.body]
    if action.kind == COMMENT:
        return ["issue", "comment", str(action.issue), "--repo", repo, "--body", action.body]
    if action.kind == CLOSE:
        return ["issue", "close", str(action.issue), "--repo", repo, "--comment", action.body]
    raise ValueError(f"unknown action {action.kind!r}")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="nightly_alarm.py", description=__doc__.splitlines()[0])
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--result", required=True, help="needs.aggregate.result")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--run-url", required=True)
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        print(f"nightly_alarm.py: usage error: {exc}", file=sys.stderr)
        return 2
    if args.event != "schedule":
        print(f"nightly_alarm.py: event {args.event!r} is not a nightly run; nothing to do",
              file=sys.stderr)
        return 0
    try:
        open_issues = list_open_issues(args.repo)
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError, KeyError,
            TypeError) as exc:
        print(f"::warning::cannot list open {LABEL} issues, assuming none: {exc}",
              file=sys.stderr)
        open_issues = []
    status = 0
    for action in decide(args.event, args.result, open_issues, args.run_url):
        try:
            proc = _gh(*gh_args(action, args.repo))
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"::error::gh {action.kind} failed: {exc}", file=sys.stderr)
            status = 1
            continue
        if proc.returncode != 0:
            print(f"::error::gh {action.kind} failed: {proc.stderr.strip()}", file=sys.stderr)
            status = 1
        else:
            print(f"nightly_alarm.py: {action.kind}"
                  + (f" #{action.issue}" if action.issue is not None else ""), file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
