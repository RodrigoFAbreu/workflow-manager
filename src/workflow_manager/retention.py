"""The opt-in retention section of `status --retention` and `doctor --retention`.

The section reports a managed repository's finished work items, their review
folders and their archives by running the repository's own installed
`scripts/workflow_retention.py report --json` (read-only) in a subprocess and
rendering its JSON. The Manager never imports the script and never runs any
other command of it (`archive`, `remove`): the commands it prints are for the
user to run. Nothing here changes an exit code or writes a file.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROGRAM = "workflow-manager"
SCRIPT = Path("scripts") / "workflow_retention.py"
TIMEOUT_SECONDS = 300
SCHEMA_VERSION = 1
KIND = "retention-report"

# The first Workflow release whose script has each command.
ARCHIVE_FROM = (2, 21, 0)
REMOVE_FROM = (2, 22, 0)

_RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_REFUSAL = re.compile(r"^error: ([A-Za-z0-9_]+): (.*)$")
_NEXT_STEP = re.compile(r"^next step: (.*)$")

STEP_RUN_DIRECTLY = "run `python3 -I scripts/workflow_retention.py report` in the repository"
STEP_UPDATE_MANAGER = "update workflow-manager to the newest release"
STEP_REINSTALL = "reinstall workflow-manager (`pipx reinstall workflow-manager`)"
STEP_FORGE = "install gh and run `gh auth login`, then run the command again"
STEP_INCOMPLETE = "fix what is named, then run the command again"


@dataclass(frozen=True)
class NotAvailable:
    cause: str
    step: str


@dataclass(frozen=True)
class Outcome:
    """What running the script gave: a validated report, or why there is none."""
    report: dict | None = None
    refusal: NotAvailable | None = None


def not_managed_note(target: Path) -> NotAvailable:
    return NotAvailable("the repository is not managed by workflow-manager",
                        f"{PROGRAM} bootstrap {shlex.quote(str(target))}")


def _update_step(target: Path) -> str:
    return f"{PROGRAM} update {shlex.quote(str(target))}"


def no_script_note(target: Path) -> NotAvailable:
    return NotAvailable(
        f"the repository has no {SCRIPT.as_posix()} (the Workflow release that ships it is "
        "2.20.0 or later)", _update_step(target))


def render_note(note: NotAvailable) -> list[str]:
    return [f"retention: not available: {note.cause}", f"  next: {note.step}"]


def _release_key(version) -> tuple[int, int, int] | None:
    match = _RELEASE.match(version) if isinstance(version, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def _script_is_regular(script: Path) -> bool:
    try:
        return script.is_file() and not script.is_symlink()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Running the script
# ---------------------------------------------------------------------------

GRACE_SECONDS = 2


def _signal_group(proc: subprocess.Popen, sig) -> None:
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _leader_exited(proc: subprocess.Popen) -> bool:
    """Whether the leader has exited, without reaping it (`WNOWAIT`): an
    unreaped leader keeps its pid, the group's id, from being reused."""
    try:
        return os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True


def _stop_group(proc: subprocess.Popen) -> None:
    """End the script's whole process group and reap its leader: SIGTERM first,
    so the script can reap what it started, then, once the leader has exited or
    after a short grace, SIGKILL for whatever is left in the group (a child
    that ignores SIGTERM included), and only then the reap."""
    _signal_group(proc, signal.SIGTERM)
    deadline = time.monotonic() + GRACE_SECONDS
    while time.monotonic() < deadline:
        if hasattr(os, "waitid") and _leader_exited(proc):
            break
        time.sleep(0.05)
    _signal_group(proc, signal.SIGKILL)
    try:
        proc.communicate(timeout=GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        # Something that left the group still holds the pipes: stop reading.
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()
        proc.wait()


def _run(root: Path):
    """`(returncode, stdout bytes, stderr bytes)`, or a `NotAvailable`. On
    timeout (or any interruption) the whole process group is ended and the
    leader reaped, so nothing the script started outlives the call."""
    argv = [sys.executable, "-I", "-B", str(root / SCRIPT), "report", "--json",
            "--repo-root", str(root)]
    try:
        proc = subprocess.Popen(argv, cwd=str(root), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except OSError as error:
        return NotAvailable(f"the Python running workflow-manager cannot start: {error}",
                            STEP_REINSTALL)
    try:
        out, err = proc.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _stop_group(proc)
        return NotAvailable(
            f"the report did not finish within {TIMEOUT_SECONDS} seconds", STEP_RUN_DIRECTLY)
    except BaseException:
        _stop_group(proc)
        raise
    return proc.returncode, out, err


class _Invalid(Exception):
    """A report that parsed but cannot be rendered; the text names the field."""


def _type_name(value) -> str:
    return type(value).__name__


def _need(obj, key, kinds, where):
    if not isinstance(obj, dict):
        raise _Invalid(f"{where} is {_type_name(obj)}, not an object")
    if key not in obj:
        raise _Invalid(f"{where}.{key} is missing" if where else f"{key} is missing")
    value = obj[key]
    ok = isinstance(value, kinds) and not (kinds is int and isinstance(value, bool))
    if not ok:
        name = getattr(kinds, "__name__", "value")
        raise _Invalid(f"{where}.{key} is {_type_name(value)}, not {name}" if where
                       else f"{key} is {_type_name(value)}, not {name}")
    if kinds is str:
        _printable(value, f"{where}.{key}" if where else key)
    return value


def _printable(text: str, name: str) -> None:
    """A string the report carries must be printable (no unpaired surrogate)."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise _Invalid(f"{name} is not valid text") from None


def _validate(report: dict) -> None:
    _need(report, "complete", bool, "")
    for entry in _need(report, "read_errors", list, ""):
        _need(entry, "path", str, "read_errors[]")
        _need(entry, "error", str, "read_errors[]")
    _need(report, "repository", str, "")
    _need(report, "archive_dir", str, "")
    _need(report, "ttl_days", int, "")
    _need(report, "keep_recent", int, "")
    finished = _need(report, "finished", list, "")
    for entry in finished:
        _need(entry, "work_item_id", str, "finished[]")
        folder = _need(entry, "review_folder", dict, "finished[]")
        _need(folder, "present", bool, "finished[].review_folder")
        _need(folder, "tracked_files", int, "finished[].review_folder")
        _need(folder, "bytes", int, "finished[].review_folder")
        archive = _need(entry, "archive", dict, "finished[]")
        _need(archive, "present", bool, "finished[].archive")
        _need(archive, "readable", bool, "finished[].archive")
    for entry in _need(report, "kept_recent", list, ""):
        _need(entry, "work_item_id", str, "kept_recent[]")
    for entry in _need(report, "not_finished", list, ""):
        _need(entry, "work_item_id", str, "not_finished[]")
        _need(entry, "reason", str, "not_finished[]")
    totals = _need(report, "totals", dict, "")
    for key in ("finished", "finished_folder_bytes", "archives", "prunable"):
        _need(totals, key, int, "totals")
    if totals["finished"] != len(finished):
        raise _Invalid(f"totals.finished is {totals['finished']} but finished lists "
                       f"{len(finished)}")
    if "removing" in report:
        removing = report["removing"]
        if not isinstance(removing, list) or not all(isinstance(i, str) for i in removing):
            raise _Invalid(f"removing is {_type_name(removing)}, not a list of strings")
        for item in removing:
            _printable(item, "removing")


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "no message"


def _other_failure(cause: str) -> Outcome:
    return Outcome(refusal=NotAvailable(cause, STEP_RUN_DIRECTLY))


def _query_failed_note(report: dict) -> NotAvailable | None:
    """Case 7: the report is valid but the forge answered for no candidate."""
    failed = [e for e in report["not_finished"] if e["reason"].startswith("query_failed:")]
    answered = [e for e in report["not_finished"]
                if e["reason"] == "no_pull_request" or e["reason"].startswith("pr_not_merged:")]
    if not failed or answered or report["finished"] or report["kept_recent"]:
        return None
    code = failed[0]["reason"].split(":", 1)[1]
    return NotAvailable(f"the forge could not be queried ({code}, {len(failed)} items)",
                        STEP_FORGE)


def fetch(target: Path) -> Outcome:
    """Run the installed script once and return its validated report, or the
    one reason there is none (the refusal order of `docs/retention.md`)."""
    root = Path(target).resolve()
    if not _script_is_regular(root / SCRIPT):
        return Outcome(refusal=no_script_note(target))
    result = _run(root)
    if isinstance(result, NotAvailable):
        return Outcome(refusal=result)
    code, out, err = result
    stderr = err.decode("utf-8", "replace")
    if code == 2:
        lines = stderr.splitlines()
        cause = next((m.groups() for m in map(_REFUSAL.match, lines) if m), None)
        step = next((m.group(1) for m in map(_NEXT_STEP.match, lines) if m), None)
        if cause is not None and step is not None:
            return Outcome(refusal=NotAvailable(f"{cause[0]}: {cause[1]}", step))
        return _other_failure(
            f"the script exited with status 2 without a refusal ({_first_line(stderr)})")
    if code != 0:
        return _other_failure(
            f"the script exited with status {code} ({_first_line(stderr)})")
    try:
        text = out.decode("utf-8")
    except UnicodeDecodeError:
        return _other_failure("the script's output is not UTF-8 text")
    try:
        report = json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: JSON nested past the decoder's depth
        return _other_failure("the script's output is not one JSON object")
    if not isinstance(report, dict):
        return _other_failure("the script's output is not one JSON object")
    if report.get("kind") != KIND:
        return Outcome(refusal=NotAvailable(
            f"the script's report has kind {report.get('kind')!r}, not {KIND!r}",
            STEP_UPDATE_MANAGER))
    if report.get("schema_version") != SCHEMA_VERSION or isinstance(
            report.get("schema_version"), bool):
        return Outcome(refusal=NotAvailable(
            f"the script's report has schema_version {report.get('schema_version')!r}; "
            f"this workflow-manager reads {SCHEMA_VERSION}", STEP_UPDATE_MANAGER))
    try:
        _validate(report)
    except _Invalid as invalid:
        return _other_failure(f"the script's report is malformed: {invalid}")
    note = _query_failed_note(report)
    if note is not None:
        return Outcome(refusal=note)
    return Outcome(report=report)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _size(count: int) -> str:
    for unit, shift in (("B", 0), ("KiB", 10), ("MiB", 20)):
        if count < 1 << (shift + 10):
            return f"{count} B" if unit == "B" else f"{count / (1 << shift):.1f} {unit}"
    try:
        return f"{count / (1 << 30):.1f} GiB"
    except OverflowError:  # beyond float range: whole GiB, never a traceback
        return f"{count >> 30} GiB"


def _listed(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def _run_script(command: str, item: str) -> str:
    return (f"in the repository, run `python3 -I scripts/workflow_retention.py {command} "
            f"{shlex.quote(item)} --apply`")


def next_step(report: dict, version, target: Path) -> str:
    """The one thing for the user to do: the first of archive, remove, resume an
    interrupted removal. A command the installed Workflow release lacks is
    replaced by the update step."""
    removing = report.get("removing", [])
    finished = report["finished"]
    kind = item = None
    for entry in finished:
        folder, archive = entry["review_folder"], entry["archive"]
        if (not archive["present"] and archive["readable"] and folder["present"]
                and folder["tracked_files"] == 0):
            kind, item = "archive", entry["work_item_id"]
            break
    if kind is None:
        for entry in finished:
            folder, archive = entry["review_folder"], entry["archive"]
            if (archive["present"] and archive["readable"] and folder["present"]
                    and folder["tracked_files"] == 0 and entry["work_item_id"] not in removing):
                kind, item = "remove", entry["work_item_id"]
                break
    if kind is None:
        for entry in finished:
            folder, archive = entry["review_folder"], entry["archive"]
            if (entry["work_item_id"] in removing and archive["present"] and archive["readable"]
                    and folder["tracked_files"] == 0 and not folder["present"]):
                kind, item = "remove", entry["work_item_id"]
                break
    if kind is None:
        return "nothing to archive"
    needed = ARCHIVE_FROM if kind == "archive" else REMOVE_FROM
    key = _release_key(version)
    if key is None or key < needed:
        return (f"this Workflow release has no `{kind}` command; "
                f"{PROGRAM} update {shlex.quote(str(target))}")
    text = _run_script(kind, item)
    if kind == "archive":
        text += " (run it without `--apply` first for a dry run)"
    return text


def render(report: dict, version, target: Path) -> list[str]:
    finished = report["finished"]
    totals = report["totals"]
    unknown = [e for e in finished if not e["archive"]["readable"]]
    archived = [e for e in finished if e["archive"]["present"] and e["archive"]["readable"]]
    removing = report.get("removing")
    failed = [e for e in report["not_finished"] if e["reason"].startswith("query_failed:")]
    errors = report["read_errors"]
    incomplete = (not report["complete"]) or bool(failed)

    lines = []
    if incomplete:
        lines.append("retention: INCOMPLETE (read-only); the numbers below are lower bounds")
        if errors:
            paths = [f"{e['path']} ({e['error']})" for e in errors]
            lines.append(f"  could not read: {_listed(paths)}")
        elif not report["complete"]:
            lines.append("  the script reports an incomplete read")
        if failed:
            tried = [f"{e['work_item_id']} ({e['reason'].split(':', 1)[1]})" for e in failed]
            lines.append(f"  not checked against the forge: {_listed(tried)}")
    else:
        lines.append("retention (read-only; the Workflow script made one forge query per "
                     "finished item):")
    lines.append(f"  repository {report['repository']}, archive directory "
                 f"{report['archive_dir']}, time to live {report['ttl_days']} days")
    unknown_text = f" ({len(unknown)} unknown)" if unknown else ""
    lines.append(f"  finished work items: {totals['finished']} (review folders "
                 f"{_size(totals['finished_folder_bytes'])}), kept as the most recent: "
                 f"{len(report['kept_recent'])}")
    lines.append(f"  with an archive: {len(archived)} of {totals['finished']}{unknown_text}; "
                 f"archive store: {totals['archives']} archives, {totals['prunable']} "
                 f"prunable (older than {report['ttl_days']} days)")
    if totals["prunable"]:
        lines.append("  prunable archives get no command yet: the Workflow has none for them")
    if removing is None:
        lines.append("  interrupted removals: not reported by this Workflow release")
    else:
        lines.append(f"  interrupted removals: {', '.join(removing) if removing else 'none'}")
    step = STEP_INCOMPLETE if incomplete else next_step(report, version, target)
    lines.append(f"  next: {step}")
    return lines


def section(target: Path, version) -> list[str]:
    """The lines to print under `--retention` for a managed repository."""
    outcome = fetch(target)
    if outcome.report is None:
        return render_note(outcome.refusal)
    try:
        return render(outcome.report, version, target)
    except Exception as exc:  # one boundary: no report may change an exit code
        return render_note(NotAvailable(
            f"the script's report is malformed: {type(exc).__name__}", STEP_RUN_DIRECTLY))
