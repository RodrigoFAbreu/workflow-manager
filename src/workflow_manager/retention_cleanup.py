"""The retention cleanup preview: what an adopted `cleanup` or `both` policy would
archive and remove.

`workflow-manager retention-cleanup TARGET` checks, in order and without writing,
every precondition of an unattended cleanup (`preflight`), selects the finished
work items past the thresholds that archiving and removing can lower (`select`)
and prints the plan with its digest (`preview_lines`). It starts no process but
`git` until the cheap checks have passed, then runs the retention report once.
The preview never runs `archive`, `remove` or `prune`; `retention_run` applies
the plan, only for the sentence bound to its digest, and prune is never part of
cleanup.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import compatibility, retention, retention_alert, retention_policy, source

CLEANUP_FROM = (2, 25, 5)  # older engines can end in a traceback in the middle of a removal
CAP = 5                    # items one run plans, at most
AGE_KEY = retention_alert.AGE_KEY
COUNTED = ("finished_items", "finished_folder_mib")  # the count and size rules
LOWERED = COUNTED + (AGE_KEY,)  # what archiving and removing can lower
CLEANUP_MODES = ("cleanup", "both")
GIT_TIMEOUT_SECONDS = 30
PROBLEM_LIMIT = 5          # interrupted removals named in a refusal
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")  # the engine's pattern, applied with fullmatch
RESERVED_IDS = ("runtime", "archive")

ARCHIVE_THEN_REMOVE = "archive then remove"
REMOVE_ONLY = "remove only"
SETTLED, CAPPED, EXHAUSTED = "settled", "cap", "exhausted"
REASON_TRACKED = ("Git tracks files under its review folder "
                  "(the engine archives untracked folders only)")
REASON_ID = "its id is not one the engine accepts"
BY_HAND = ("by hand, one item at a time: the Workflow's user-only `/archive-finished-item ID`; "
           "for an item that is already archived, `python3 -I scripts/workflow_retention.py "
           "remove ID --apply` alone")
_SENTENCE = re.compile(r"run the retention cleanup ([0-9a-f]{%d})\." % retention_policy.DIGEST_SHOWN)


def sentence(plan_digest_value: str) -> str:
    """The sentence that confirms a plan: it names the first 12 characters of the
    plan's digest."""
    return f"Run the retention cleanup {plan_digest_value[:retention_policy.DIGEST_SHOWN]}."


def confirmation_holds(text, plan_digest_value: str) -> bool:
    """Whether `text` names the plan: after whitespace collapse and ignoring case,
    every match of the sentence carries the digest's first 12 characters, and there
    is at least one. Anything but a string is no confirmation."""
    if not isinstance(text, str):
        return False
    found = _SENTENCE.findall(" ".join(text.split()).lower())
    prefix = plan_digest_value[:retention_policy.DIGEST_SHOWN]
    return bool(found) and all(match == prefix for match in found)


class Refusal(Exception):
    """A refusal: `cause` and the one `step` to take. Nothing was written."""

    def __init__(self, cause: str, step: str):
        super().__init__(cause)
        self.cause = cause
        self.step = step


# ---------------------------------------------------------------------------
# The preflight
# ---------------------------------------------------------------------------

def _git(target: Path, *args: str,
         config: tuple[tuple[str, str], ...] = ()) -> subprocess.CompletedProcess:
    """`git -C TARGET ARGS`: bytes in, hermetic, nothing written by git. The
    Manager's own hermetic flags and environment apply (no optional locks, no
    fsmonitor hook, no hooks path, no untracked cache), so a configured hook never
    runs before the preflight completes."""
    # `GIT_CONFIG_PARAMETERS` (what a shell alias's `git -c` exports) outranks
    # `GIT_CONFIG_COUNT`, so it could switch a filter driver back on over the
    # overrides; it is dropped, for the discovery and the status alike. The pairs
    # go in through `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n`, so a driver name with
    # an `=` in it (which `-c key=value` splits at the first one) is switched off too.
    env = compatibility.git_env(config, drop_config_parameters=True)
    return subprocess.run(
        compatibility.git_argv(target, *args),
        capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False, env=env)


def _git_failed(error: Exception) -> Refusal:
    return Refusal(f"retention cleanup: Git could not be asked ({type(error).__name__})",
                   "run `git status` in the repository and fix what it names, then run the "
                   "command again")


def committed(target: Path) -> str | None:
    """`None` when the policy file and the adoption record are both at HEAD with
    exactly the working files' bytes; else the name of the first one that is not."""
    for path in (retention_policy.policy_path(target), retention_policy.record_path(target)):
        relative = f"{retention_policy.DIRECTORY}/{path.name}"
        shown = _git(target, "show", f"HEAD:./{relative}")   # a Git failure is `_git_failed`'s
        try:
            working = path.read_bytes()
        except OSError:
            return relative
        if shown.returncode != 0 or shown.stdout != working:
            return relative
    return None


def _filter_overrides(target: Path) -> tuple[tuple[str, str], ...]:
    """(key, value) pairs, passed through `GIT_CONFIG_*`, that switch off every
    configured filter driver. A driver's clean or process command runs when
    `git status` re-reads a file whose stat data no longer matches the index (Git
    LFS installs one globally), and it can write into the repository. An empty
    command is "no filter"; `required` is turned off so Git does not fail on it.
    The names come from every configuration scope."""
    done = _git(target, "config", "-z", "--name-only", "--get-regexp", r"^filter\.")
    if done.returncode not in (0, 1):
        raise Refusal("retention cleanup: `git config` failed",
                      "run `git config --list` in the repository and fix what it names, "
                      "then run the command again")
    drivers = set()
    for entry in done.stdout.decode("utf-8", "surrogateescape").split("\0"):
        # Git prints the section and the key in lower case and keeps the subsection
        # (the driver name), which is case-sensitive, as written.
        if entry.startswith("filter.") and "." in entry[len("filter."):]:
            drivers.add(entry[len("filter."):].rsplit(".", 1)[0])
    pairs: list[tuple[str, str]] = []
    for driver in sorted(drivers):
        for key in ("clean", "smudge", "process"):
            pairs.append((f"filter.{driver}.{key}", ""))
        pairs.append((f"filter.{driver}.required", "false"))
    return tuple(pairs)


def clean_tree(target: Path) -> bool:
    """True when no tracked file is changed. Untracked files (the review folders)
    are expected. `_git` keeps `git status` from refreshing, and so rewriting, the
    index, and from running a configured fsmonitor hook; `_filter_overrides` keeps
    it from running a configured clean or process filter, and `--ignore-submodules=dirty`
    keeps it out of a submodule's work tree (which reads the submodule's own
    configuration, not this one's) while a submodule whose HEAD moved is still a
    tracked change; so no process but `git` starts and nothing is written."""
    done = _git(target, "status", "--porcelain", "-z", "--untracked-files=no",
                "--ignore-submodules=dirty", config=_filter_overrides(target))
    if done.returncode != 0:
        raise Refusal("retention cleanup: `git status` failed",
                      "run `git status` in the repository and fix what it names, then run "
                      "the command again")
    return not done.stdout


def _policy_refusal(state, target: Path) -> Refusal:
    if state.state == retention_policy.ABSENT:
        return Refusal("retention cleanup: no retention policy is adopted (there is no "
                       f"{retention_policy.DIRECTORY}/{retention_policy.POLICY_FILE})",
                       retention_policy.step_for(state.state, target))
    words = retention_policy.WORDS[state.state]
    cause = f"retention policy: {state.state} ({words})"
    if state.state == retention_policy.INVALID and state.problems:
        cause += f": {state.problems[0]}"
    return Refusal(cause,
                   retention_policy.step_for(state.state, target))


@dataclass(frozen=True)
class Cleared:
    state: retention_policy.PolicyState
    report: dict


def preflight(target: Path, version, script_state, record_refusal=None) -> Cleared:
    """Check every precondition in order, the first refusal winning, and return the
    adopted policy and the complete report. Raises `Refusal`. Steps 1 (the
    repository is managed) is the caller's; steps 2 to 6 start no process but
    `git`; the retention script starts at step 7."""
    target = Path(target)
    quoted = shlex.quote(str(target))
    # 2. the policy is adopted, with a mode that allows cleanup
    state = retention_policy.load(target)
    if state.state != retention_policy.ADOPTED:
        raise _policy_refusal(state, target)
    if state.mode not in CLEANUP_MODES:
        raise Refusal(f"retention cleanup: the adopted mode is {state.mode}, which does not "
                      "allow cleanup",
                      'set mode to "cleanup" or "both" in '
                      f"{retention_policy.DIRECTORY}/{retention_policy.POLICY_FILE}, then run "
                      f"{retention_policy.adopt_command(target)}")
    # 3. both files are at HEAD, unchanged
    try:
        missing = committed(target)
    except Exception as error:  # noqa: BLE001 -- a failed `git` is a refusal, never a traceback
        raise _git_failed(error) from error
    if missing is not None:
        raise Refusal(f"retention cleanup: {missing} is not committed at HEAD with the bytes "
                      "that were adopted",
                      f"commit {retention_policy.DIRECTORY}/{retention_policy.POLICY_FILE} and "
                      f"{retention_policy.DIRECTORY}/{retention_policy.RECORD_FILE}, then run "
                      "the command again")
    # 4. no tracked file is changed
    try:
        clean = clean_tree(target)
    except Refusal:
        raise
    except Exception as error:  # noqa: BLE001
        raise _git_failed(error) from error
    if not clean:
        raise Refusal("retention cleanup: a tracked file is changed",
                      "commit or restore the change, or run the command from a clean checkout")
    # 5. the release is one that can be trusted with an unattended removal
    # the strict validator the doctor applies: `02.25.5` and `2.25.5\n` are no release
    key = retention.release_key(version) if source.is_strict_version(version) else None
    if key is None:
        if record_refusal is not None:
            raise Refusal(*record_refusal())
        raise Refusal("retention cleanup: the installation record names no release that can be "
                      "read", f"{retention.PROGRAM} --release-version X.Y.Z update {quoted}")
    if key < CLEANUP_FROM:
        needed = ".".join(str(part) for part in CLEANUP_FROM)
        raise Refusal(f"retention cleanup: the installed Workflow release {version} is older "
                      f"than {needed} (an older engine can end in a traceback in the middle of "
                      "a removal)", f"{retention.PROGRAM} update {quoted}")
    # 6. the installed script is the release's own
    try:
        flag = script_state()
    except Exception:  # noqa: BLE001
        flag = retention_alert.SCRIPT_UNCHECKED
    if flag == retention_alert.SCRIPT_NO_RELEASE:
        raise Refusal(f"retention cleanup: {retention_alert.CAUSE_NO_RELEASE}",
                      f"{retention.PROGRAM} --release-version X.Y.Z update {quoted}")
    if flag == retention_alert.SCRIPT_UNCHECKED:
        raise Refusal(f"retention cleanup: {retention_alert.CAUSE_UNCHECKED}",
                      retention_alert.STEP_UNCHECKED)
    if flag != retention_alert.SCRIPT_OK:
        raise Refusal(f"retention cleanup: {retention_alert.CAUSE_MODIFIED}",
                      f"{retention.PROGRAM} update {quoted} --force")
    # 7. the report
    outcome = retention.fetch(target)
    if outcome.report is None:
        raise Refusal(outcome.refusal.cause, outcome.refusal.step)
    report = outcome.report
    # 8. the report is complete and no removal was interrupted
    if retention_alert.incomplete(report):
        raise Refusal(f"retention cleanup: {retention_alert.CAUSE_INCOMPLETE}",
                      retention.STEP_INCOMPLETE)
    interrupted = report.get("removing", [])
    if interrupted:
        shown = ", ".join(retention.shown(item) for item in interrupted[:PROBLEM_LIMIT])
        more = f" and {len(interrupted) - PROBLEM_LIMIT} more" if len(interrupted) > PROBLEM_LIMIT else ""
        raise Refusal(f"retention cleanup: a removal was interrupted ({shown}{more})",
                      "finish it with the user-only `python3 -I scripts/workflow_retention.py "
                      "remove ID --apply` in the repository, then run the command again")
    return Cleared(state, report)


# ---------------------------------------------------------------------------
# The selection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    work_item_id: str
    action: str   # ARCHIVE_THEN_REMOVE or REMOVE_ONLY
    bytes: int


@dataclass(frozen=True)
class Plan:
    repository: str
    policy_digest: str
    mode: str
    thresholds: dict            # the policy's lowered thresholds that are set
    before: dict                # LOWERED key -> the measured number (bytes for MiB)
    after: dict
    reached: tuple              # the keys at or above their limit before the run
    candidates: int             # finished items with a review folder
    items: tuple                # Item, in plan order
    skipped: tuple              # (id as shown, reason)
    outcome: str | None         # SETTLED, CAPPED, EXHAUSTED; None when there is nothing to do
    unknown_age: int = 0        # age key only: examined items with no usable last transition


def _limit(key: str, thresholds: dict) -> int:
    if key == AGE_KEY:   # a count of old items not yet planned: reached at one; N is a duration
        return 1
    return thresholds[key] * 2**20 if key == "finished_folder_mib" else thresholds[key]


def _reached(numbers: dict, thresholds: dict, keys: tuple = LOWERED) -> tuple:
    return tuple(key for key in keys if key in thresholds and numbers[key] >= _limit(key, thresholds))


def _eligible(entry: dict) -> str | None:
    """`None` when the entry may be planned, else the reason it is skipped."""
    identifier = entry["work_item_id"]
    if _ID.fullmatch(identifier) is None or identifier in RESERVED_IDS:
        return REASON_ID
    if entry["review_folder"]["tracked_files"] > 0:
        return REASON_TRACKED
    return None


def select(state, report: dict) -> Plan:
    """The plan for an adopted policy and a complete report. Pure."""
    thresholds = {key: state.policy["thresholds"][key]
                  for key in LOWERED if key in state.policy.get("thresholds", {})}
    # The report lists the newest first; the oldest are cleaned first.
    candidates = [e for e in reversed(report["finished"]) if e["review_folder"]["present"]]
    before = {"finished_items": len(candidates),
              "finished_folder_mib": report["totals"]["finished_folder_bytes"]}
    old, unknown_age = (), 0
    if AGE_KEY in thresholds:
        old_ids, unknown_age = retention_alert.aged(report, thresholds[AGE_KEY])
        old = frozenset(old_ids)
        before[AGE_KEY] = len(old_ids)
    base = dict(repository=report["repository"], policy_digest=state.digest, mode=state.mode,
                thresholds=thresholds, before=before, candidates=len(candidates),
                unknown_age=unknown_age)
    reached = _reached(before, thresholds)
    if not reached:
        return Plan(**base, after=dict(before), reached=(), items=(), skipped=(), outcome=None)
    skipped, eligible = [], []
    for entry in candidates:
        reason = _eligible(entry)
        if reason is None:
            eligible.append(entry)
        else:
            shown = retention.shown(entry["work_item_id"]) if reason == REASON_ID \
                else entry["work_item_id"]
            skipped.append((shown, reason))
    after = dict(before)
    taken = []
    old_left = [e for e in eligible if e["work_item_id"] in old]   # old, eligible, not yet planned
    for entry in eligible:
        if len(taken) == CAP:
            break
        counted = bool(_reached(after, thresholds, COUNTED))
        is_old = entry["work_item_id"] in old
        if not counted and not old_left:
            break
        if not counted and not is_old:
            continue   # a young or unknown-age item is passed over by the age rule alone
        action = REMOVE_ONLY if entry["archive"]["present"] else ARCHIVE_THEN_REMOVE
        taken.append(Item(entry["work_item_id"], action, entry["review_folder"]["bytes"]))
        after["finished_items"] -= 1
        after["finished_folder_mib"] -= entry["review_folder"]["bytes"]
        if is_old:
            old_left.remove(entry)
            after[AGE_KEY] -= 1
    if not _reached(after, thresholds):
        outcome = SETTLED
    else:
        planned = {item.work_item_id for item in taken}
        more = [e for e in eligible if e["work_item_id"] not in planned]
        can_plan = bool(more) and (bool(_reached(after, thresholds, COUNTED))
                                   or any(e["work_item_id"] in old for e in more))
        outcome = CAPPED if len(taken) == CAP and can_plan else EXHAUSTED
    return Plan(**base, after=after, reached=reached, items=tuple(taken),
                skipped=tuple(skipped), outcome=outcome)


# ---------------------------------------------------------------------------
# The digest and the preview
# ---------------------------------------------------------------------------

def plan_digest(plan: Plan) -> str:
    """The full sha256 of the plan: the repository, the policy digest and the
    `[id, action]` pairs in order."""
    body = {"repository": plan.repository, "policy": plan.policy_digest,
            "items": [[item.work_item_id, item.action] for item in plan.items]}
    data = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("ascii")).hexdigest()


def _mib(value: int) -> int:
    return value // 2**20


def _age_label(thresholds: dict) -> str:
    return f"finished older than {thresholds[AGE_KEY]} days"


def _measured(key: str, numbers: dict, *, with_limit: dict | None = None) -> str:
    if key == AGE_KEY:   # the number is a count of items; the limit is the label's own days
        return f"{_age_label(with_limit)} {numbers[key]}"
    label = retention_policy.THRESHOLDS[key][1]
    if key == "finished_folder_mib":
        text = f"{label} {_mib(numbers[key])} MiB"
        return text if with_limit is None else f"{text} (limit {with_limit[key]} MiB)"
    text = f"{label} {numbers[key]}"
    return text if with_limit is None else f"{text} (limit {with_limit[key]})"


def _names(keys, thresholds: dict) -> str:
    return " and ".join(_age_label(thresholds) if key == AGE_KEY
                        else retention_policy.THRESHOLDS[key][1] for key in keys)


def _age_note(plan: Plan) -> list[str]:
    if AGE_KEY not in plan.thresholds or not plan.unknown_age:
        return []
    return [f"  age not known: {plan.unknown_age} finished items with no usable last "
            "transition are never planned by the age rule"]


def preview_lines(plan: Plan, target) -> list[str]:
    """What `retention-cleanup` prints (stdout, exit 0). `target` is the repository as
    the operator typed it; the `next:` line names it, quoted for a shell."""
    if plan.outcome is None:
        if not plan.thresholds:
            return ["retention cleanup: nothing to do (the policy sets no threshold that "
                    "cleanup can lower)"]
        parts = []
        for key in LOWERED:
            if key not in plan.thresholds:
                continue
            if key == AGE_KEY:
                parts.append(_measured(key, plan.before, with_limit=plan.thresholds))
            elif key == "finished_folder_mib":
                parts.append(f"{retention_policy.THRESHOLDS[key][1]} "
                             f"{_mib(plan.before[key])} of {plan.thresholds[key]} MiB")
            else:
                parts.append(f"{retention_policy.THRESHOLDS[key][1]} "
                             f"{plan.before[key]} of {plan.thresholds[key]}")
        return [f"retention cleanup: nothing to do ({', '.join(parts)})", *_age_note(plan)]
    short = plan_digest(plan)[:retention_policy.DIGEST_SHOWN]
    lines = [f"retention cleanup: preview (nothing was written; mode {plan.mode}, policy "
             f"{plan.policy_digest[:retention_policy.DIGEST_SHOWN]}, plan {short})",
             "  thresholds reached: " + ", ".join(
                 _measured(key, plan.before, with_limit=plan.thresholds) for key in plan.reached),
             f"  would clean {len(plan.items)} of {plan.candidates} finished items with a review "
             f"folder, oldest first, at most {CAP} per run:"]
    for number, item in enumerate(plan.items, 1):
        action = item.action if item.action == ARCHIVE_THEN_REMOVE \
            else f"{item.action} (already archived)"
        lines.append(f"    {number}. {item.work_item_id}: {_mib(item.bytes)} MiB, {action}")
    for shown, reason in plan.skipped:
        lines.append(f"  skipped: {shown}: {reason}")
    lines.extend(_age_note(plan))
    left = tuple(key for key in LOWERED if key in plan.thresholds
                 and plan.after[key] >= _limit(key, plan.thresholds))
    numbers = [_measured(key, plan.after, with_limit=plan.thresholds) if key == AGE_KEY else
               f"{retention_policy.THRESHOLDS[key][1]} "
               f"{_mib(plan.after[key]) if key == 'finished_folder_mib' else plan.after[key]}"
               f"{' MiB' if key == 'finished_folder_mib' else ''}"
               for key in LOWERED if key in plan.thresholds]
    if plan.outcome == SETTLED:
        verdict = "below every limit"
    elif plan.outcome == CAPPED:
        verdict = f"{_names(left, plan.thresholds)} still reached; stopped at the cap of {CAP} per run; run it again"
    else:
        skipped = ""
        if plan.skipped:
            skipped = f" (skipped: {', '.join(shown for shown, _ in plan.skipped)})"
        verdict = (f"{_names(left, plan.thresholds)} still reached; no further item is eligible{skipped}; "
                   "running it again will not help")
    lines.append(f"  after this run: {', '.join(numbers)}: {verdict}")
    lines.append(f"  next: workflow-manager retention-cleanup {shlex.quote(str(target))} "
                 f"--confirm \"{sentence(plan_digest(plan))}\"")
    lines.append(f"  {BY_HAND}")
    return lines
