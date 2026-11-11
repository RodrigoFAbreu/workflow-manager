"""The retention alert of `verify` and `doctor`.

For a policy that is adopted with mode `notify` or `both`, the four thresholds
are evaluated against the retention report the Manager already measures
(`retention.fetch`) and a `retention alert:` block is printed when one is
reached. Nothing is sent, nothing is cleaned, and no exit code changes: the
steps the block names are for the owner to run.

`evaluate` is pure. `alert_lines` is the one gate: it reads the policy first
(locally) and starts nothing, and never asks about the script, unless the
policy is alerting. It never starts the script when the script is not the
release's, and one boundary turns any exception into a `not evaluated` line.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from . import install, retention, retention_policy
from .installation import Installation

REACHED, WITHIN, UNKNOWN = "reached", "within", "unknown"
SCRIPT_OK, SCRIPT_MODIFIED, SCRIPT_UNCHECKED = "ok", "modified", "unchecked"
SCRIPT_NO_RELEASE = "no_release"
ALERT_MODES = ("notify", "both")

CAUSE_INCOMPLETE = "the retention report is incomplete (the numbers are lower bounds)"
CAUSE_MODIFIED = "the installed scripts/workflow_retention.py does not match the release"
CAUSE_UNCHECKED = "the installed release cannot be checked"
CAUSE_NO_RELEASE = "the installation record names no release"
STEP_UNCHECKED = ("run the command again with the network, or with "
                  "WORKFLOW_MANAGER_RELEASE_SOURCE set to a mirror")


@dataclass(frozen=True)
class Result:
    key: str            # a retention_policy.THRESHOLDS key
    status: str         # REACHED, WITHIN or UNKNOWN
    value: int | None   # the measured number (bytes for finished_folder_mib); None without a report
    limit: int          # the policy's number (MiB for finished_folder_mib)
    lower_bound: bool   # the report was incomplete


def alerting(state) -> bool:
    return state.state == retention_policy.ADOPTED and state.mode in ALERT_MODES


def _incomplete(report: dict) -> bool:
    failed = any(e["reason"].startswith("query_failed:") for e in report["not_finished"])
    return (not report["complete"]) or bool(report["read_errors"]) or failed


def _measured(key: str, report: dict) -> int:
    totals = report["totals"]
    if key == "finished_items":
        return sum(1 for e in report["finished"] if e["review_folder"]["present"])
    if key == "finished_folder_mib":
        return totals["finished_folder_bytes"]
    if key == "archives":
        return totals["archives"]
    return totals["prunable"]


def evaluate(state, report) -> list[Result]:
    """One `Result` per threshold the adopted policy sets, in THRESHOLDS order;
    `[]` unless `alerting(state)`. An incomplete report gives lower bounds: at or
    above the limit is still reached, below it is unknown, never within."""
    if not alerting(state):
        return []
    thresholds = state.policy.get("thresholds", {})
    incomplete = report is None or _incomplete(report)
    results = []
    for key in retention_policy.THRESHOLDS:
        if key not in thresholds:
            continue
        limit = thresholds[key]
        if report is None:
            results.append(Result(key, UNKNOWN, None, limit, True))
            continue
        value = _measured(key, report)
        bound = limit * 2**20 if key == "finished_folder_mib" else limit
        if value >= bound:
            status = REACHED
        else:
            status = UNKNOWN if incomplete else WITHIN
        results.append(Result(key, status, value, limit, incomplete))
    return results


# ---------------------------------------------------------------------------
# Is the installed script the release's?
# ---------------------------------------------------------------------------

def script_state(target: Path, release) -> str:
    """`SCRIPT_OK` only when the release's manifest lists the script, the
    installation record lists it as managed and `install.drift` reports nothing
    for it. A release with no script and no such file in the tree is `SCRIPT_OK`
    too (`retention.fetch` then says there is no script); a file there is not."""
    path = retention.SCRIPT.as_posix()
    target = Path(target)
    installation = Installation.read(target)
    in_manifest = any(a.target_path == path for a in release.installable(installation.profile))
    listed = path in installation.managed
    present = os.path.lexists(target / retention.SCRIPT)
    if not in_manifest and not listed and not present:
        return SCRIPT_OK
    if not (in_manifest and listed):
        return SCRIPT_MODIFIED
    if any(d.path == path for d in install.drift(target, release)):
        return SCRIPT_MODIFIED
    return SCRIPT_OK


# ---------------------------------------------------------------------------
# What is printed
# ---------------------------------------------------------------------------

def _not_evaluated(cause: str, step: str) -> list[str]:
    return [f"retention alert: not evaluated: {cause}", f"  next: {step}"]


def _prune_step(version, target: Path) -> str:
    key = retention._release_key(version)
    if key is None or key < retention.PRUNE_FROM:
        return (f"this Workflow release has no `prune` command; "
                f"{retention.PROGRAM} update {shlex.quote(str(target))}")
    return ("in the repository, run `python3 -I scripts/workflow_retention.py report` to list "
            "the prunable archives, then `python3 -I scripts/workflow_retention.py prune ID "
            "--apply` for each")


def _step(result: Result, report: dict, version, target: Path) -> str:
    if result.key in ("finished_items", "finished_folder_mib"):
        return retention.next_step(report, version, target)
    if result.key == "prunable_archives" or report["totals"]["prunable"] > 0:
        return _prune_step(version, target)
    observed = ("no prunable archive was observed (the report is incomplete)"
                if _incomplete(report) else "none can be pruned")
    return (f"no archive is past the time to live yet, so {observed}: raise "
            "thresholds.archives in the policy if the store is meant to be this large, "
            f"then adopt it again ({retention_policy.adopt_command(target)})")


def _shown(result: Result) -> tuple[str, str]:
    """The measured number and the limit, as printed."""
    mib = result.key == "finished_folder_mib"
    value = result.value // 2**20 if mib else result.value
    unit = " MiB" if mib else ""
    prefix = "at least " if result.lower_bound else ""
    return f"{prefix}{value}{unit}", f"{result.limit}{unit}"


def render(state, results: list[Result], report: dict, version, target: Path) -> list[str]:
    reached = [r for r in results if r.status == REACHED]
    unknown = [r for r in results if r.status == UNKNOWN]
    if not reached:
        if unknown:
            return _not_evaluated(CAUSE_INCOMPLETE, retention.STEP_INCOMPLETE)
        return []
    lines = [f"retention alert: {len(reached)} of {len(results)} thresholds reached "
             f"(mode {state.mode}, policy {state.digest[:retention_policy.DIGEST_SHOWN]})"]
    for result in results:
        if result.status == WITHIN:
            continue
        label = retention_policy.THRESHOLDS[result.key][1]
        value, limit = _shown(result)
        text = "reached" if result.status == REACHED else "not known (the report is incomplete)"
        lines.append(f"  {label}: {value}, limit {limit}: {text}")
    steps = []
    for result in reached:
        step = _step(result, report, version, target)
        if step not in steps:
            steps.append(step)
    if _incomplete(report) and retention.STEP_INCOMPLETE not in steps:
        steps.append(retention.STEP_INCOMPLETE)
    lines.append(f"  next: {'; '.join(steps)}")
    return lines


def alert_lines(target: Path, version, script_state, outcome=None) -> list[str]:
    """The alert's lines (none unless the policy is adopted with mode `notify` or
    `both`, and then none when every threshold is within). `script_state` is a
    zero-argument callable, called only for an alerting policy and inside this
    one exception boundary. `outcome` is a report the caller already fetched."""
    state = retention_policy.load(target)
    if not alerting(state):
        return []
    try:
        flag = script_state()
        if flag == SCRIPT_NO_RELEASE:
            return _not_evaluated(
                CAUSE_NO_RELEASE,
                f"{retention.PROGRAM} --release-version X.Y.Z update {shlex.quote(str(target))} "
                f"({retention.PROGRAM} releases lists them)")
        if flag == SCRIPT_UNCHECKED:
            return _not_evaluated(CAUSE_UNCHECKED, STEP_UNCHECKED)
        if flag != SCRIPT_OK:
            return _not_evaluated(
                CAUSE_MODIFIED, f"{retention.PROGRAM} update {shlex.quote(str(target))} --force")
        if outcome is None:
            outcome = retention.fetch(target)
        if outcome.report is None:
            return _not_evaluated(outcome.refusal.cause, outcome.refusal.step)
        results = evaluate(state, outcome.report)
        return render(state, results, outcome.report, version, target)
    except Exception as exc:  # one boundary: the alert never changes an exit code
        return _not_evaluated(type(exc).__name__, retention.STEP_RUN_DIRECTLY)
