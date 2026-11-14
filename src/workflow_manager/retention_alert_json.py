"""The retention alert as one JSON document (`doctor --retention --json`).

The second renderer of `retention_alert.assess`: the same decisions as the text
alert, so the two cannot disagree. The document states current facts only. It
never says a work item was archived or deleted, because one report cannot prove
a transition; a consumer that keeps the previous document compares the two
(`docs/retention.md`). Every key is always present (`null` when it does not
apply) and the insertion order is fixed, so the same inputs give the same bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import retention, retention_alert as ra, retention_policy

KIND = "retention_alert"
SCHEMA_VERSION = 1

NOT_APPLICABLE, NOT_EVALUATED, EVALUATED = "not_applicable", "not_evaluated", "evaluated"
STATE_REACHED, STATE_CLEAR, STATE_UNKNOWN = "reached", "clear", "unknown"

_UNITS = {  # rule: (threshold unit, value unit)
    "finished_items": ("items", "items"),
    "finished_folder_mib": ("MiB", "MiB"),
    "archives": ("archives", "archives"),
    "prunable_archives": ("archives", "archives"),
    ra.AGE_KEY: ("days", "items"),
}
_STATES = {ra.REACHED: STATE_REACHED, ra.WITHIN: STATE_CLEAR, ra.UNKNOWN: STATE_UNKNOWN}


def _repo(target: Path) -> str:
    return str(Path(target).resolve())


def _policy(state) -> dict:
    return {"state": state.state, "mode": state.mode,
            "digest": state.digest if state.state == retention_policy.ADOPTED else None}


def _value(result: ra.Result) -> int | None:
    if result.value is None:
        return None
    return result.value // 2**20 if result.key == "finished_folder_mib" else result.value


def _alert_key(repo: str, result: ra.Result, state: str, value) -> str:
    key = f"retention:{repo}:{result.key}:{state}"
    if state == STATE_REACHED:
        key += f":{value}{'+' if result.lower_bound else ''}"
    return key


def _alert(repo: str, result: ra.Result, report, version, target: Path) -> dict:
    state = _STATES[result.status]
    threshold_unit, value_unit = _UNITS[result.key]
    value = _value(result)
    reached = result.status == ra.REACHED
    return {
        "rule": result.key,
        "threshold": result.limit,
        "threshold_unit": threshold_unit,
        "current_value": value,
        "value_unit": value_unit,
        "lower_bound": result.lower_bound,
        "unknown_age": result.unknown_age if result.key == ra.AGE_KEY else None,
        "reached": reached,
        "state": state,
        "alert_key": _alert_key(repo, result, state, value),
        "next": ra._step(result, report, version, target) if reached else None,
    }


def _snapshot(report: dict) -> dict:
    finished = report["finished"]
    removed = sorted(e["work_item_id"] for e in finished
                     if e["archive"]["present"] and e["archive"]["readable"]
                     and not e["review_folder"]["present"])
    totals = report["totals"]
    return {
        "finished": len(finished),
        "with_review_folder": sum(1 for e in finished if e["review_folder"]["present"]),
        "archived_and_removed": removed,
        "finished_folder_bytes": totals["finished_folder_bytes"],
        "archive_store": totals["archives"],
        "prunable_archives": totals["prunable"],
        "interrupted_removals": list(report["removing"]) if "removing" in report else None,
    }


def _document(target: Path, state, evaluation: str, not_evaluated, alerts, snapshot,
              complete) -> dict:
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "repo": _repo(target),
        "policy": _policy(state),
        "evaluation": evaluation,
        "not_evaluated": ({"cause": not_evaluated[0], "next": not_evaluated[1]}
                          if not_evaluated is not None else None),
        "report_complete": complete,
        "alerts": alerts,
        "snapshot": snapshot,
    }


def _build(target: Path, version, found: ra.Assessment) -> dict:
    state = found.state
    if not ra.alerting(state):
        return _document(target, state, NOT_APPLICABLE, None, [], None, None)
    if found.not_evaluated is not None:
        return _document(target, state, NOT_EVALUATED, found.not_evaluated, [], None, None)
    report, repo = found.report, _repo(target)
    alerts = [_alert(repo, r, report, version, target) for r in found.results]
    complete = not ra.incomplete(report)
    unknown = any(r.status == ra.UNKNOWN for r in found.results)
    reached = any(r.status == ra.REACHED for r in found.results)
    if unknown and not reached:  # as the text: an incomplete report with no rule reached
        return _document(target, state, NOT_EVALUATED,
                         (ra.CAUSE_INCOMPLETE, retention.STEP_INCOMPLETE), alerts,
                         _snapshot(report), complete)
    return _document(target, state, EVALUATED, None, alerts, _snapshot(report), complete)


def document(target: Path, version, script_state, outcome=None) -> dict:
    """The alert as a dict. `script_state` and `outcome` are as for
    `retention_alert.assess`. One boundary: an exception while building the
    document is a `not_evaluated` document naming its type."""
    found = ra.assess(target, script_state, outcome)
    try:
        return _build(target, version, found)
    except Exception as exc:  # the alert never changes an exit code
        if not ra.alerting(found.state):
            return _document(target, found.state, NOT_APPLICABLE, None, [], None, None)
        return _document(target, found.state, NOT_EVALUATED,
                         (type(exc).__name__, retention.STEP_RUN_DIRECTLY), [], None, None)


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2) + "\n"
