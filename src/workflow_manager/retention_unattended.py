"""The unattended retention run's audit file (CP2).

One JSON object per line is appended to `retention-audit.jsonl` in
`$XDG_STATE_HOME/workflow-manager/` (a relative or empty `XDG_STATE_HOME` is ignored,
as the XDG rule says; the default is `~/.local/state/workflow-manager/`). The file is
outside the repository and outside the engine's archive store, so the clean-tree
check is untouched. It is opened append-only and written one whole line per
`os.write`: never seeked, truncated or rewritten.

`run_command` is the unattended `retention-cleanup TARGET --unattended` flow: the
confirmed run with the per-plan sentence replaced by the recorded adoption, plus the
audit lines and the optional JSON document (plan sections 2.1 and 2.4).
"""

from __future__ import annotations

import datetime
import errno
import json
import os
import shlex
import stat as stat_module
import sys
import uuid
from pathlib import Path

from . import retention, retention_cleanup, retention_policy, retention_prune, retention_run

SCHEMA_VERSION = 1
AUDIT_NAME = "retention-audit.jsonl"
STATE_DIR_NAME = "workflow-manager"
DIR_MODE, FILE_MODE = 0o700, 0o600
# The engine's own default archive store, named once in `retention_policy`.
ARCHIVE_ROOT = retention_policy.ARCHIVE_ROOT

# The vocabulary of a line (plan section 2.3).
STEPS = ("archive", "verify", "remove", "plan", "preflight", "policy", "prune")
RESULTS = ("ok", "failed", "interrupted", "nothing-eligible", "started", "refused", "stopped")
FIELDS = ("schema_version", "time", "run_id", "repository", "policy_digest", "plan_digest",
          "item_id", "step", "engine_code", "result", "error")


class AuditError(Exception):
    """The audit file could not be used: `cause` and the one `step` to take."""

    def __init__(self, cause: str, step: str):
        super().__init__(cause)
        self.cause = cause
        self.step = step


class AuditRefusal(AuditError):
    """The file could not be opened (or its location or directory is unacceptable):
    raised before the run does anything."""


class AuditWriteError(AuditError):
    """A write to an open audit file failed or was short."""


def state_base(environ=None) -> Path:
    """`$XDG_STATE_HOME` when it is an absolute path, else `~/.local/state`."""
    environ = os.environ if environ is None else environ
    value = environ.get("XDG_STATE_HOME") or ""
    if value and os.path.isabs(value):
        return Path(value)
    home = environ.get("HOME") or str(Path.home())
    return Path(home) / ".local" / "state"


def audit_path(environ=None) -> Path:
    return state_base(environ) / STATE_DIR_NAME / AUDIT_NAME


def archive_store(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    home = environ.get("HOME") or str(Path.home())
    return Path(home) / ARCHIVE_ROOT[2:]


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _refuse(why: str, path, step: str) -> AuditRefusal:
    return AuditRefusal(f"the audit file cannot be written: {why} ({path})", step)


def _make_dirs(directory: Path) -> None:
    """Create `directory` and its missing parents, each 0700. An existing parent is
    not inspected (it is the XDG state base)."""
    missing = []
    probe = directory
    while not probe.exists() and probe != probe.parent:
        missing.append(probe)
        probe = probe.parent
    for made in reversed(missing):
        try:
            os.mkdir(made, DIR_MODE)
        except FileExistsError:
            continue
        os.chmod(made, DIR_MODE)       # the umask only narrows; this makes it exact


class Audit:
    """An open audit file. `line` appends one record; `write`, `clock` and `run_id`
    are seams for the tests."""

    def __init__(self, fd: int, path: Path, repository: str, *, clock, run_id: str, write):
        self.fd, self.path, self.repository = fd, path, repository
        self.clock, self.run_id, self.write = clock, run_id, write
        self.lines = 0

    def record(self, step: str, result: str, *, policy_digest=None, plan_digest=None,
               item_id=None, engine_code=None, error=None) -> dict:
        if step not in STEPS:
            raise ValueError(f"no such audit step: {step!r}")
        if result not in RESULTS:
            raise ValueError(f"no such audit result: {result!r}")
        moment = self.clock().astimezone(datetime.timezone.utc)
        return {
            "schema_version": SCHEMA_VERSION,
            "time": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": self.run_id,
            "repository": self.repository,
            "policy_digest": policy_digest,
            "plan_digest": plan_digest,
            "item_id": item_id,
            "step": step,
            "engine_code": engine_code,
            "result": result,
            "error": error,
        }

    def line(self, step: str, result: str, **fields) -> dict:
        """Append one line: all eleven fields, one `os.write` of the whole encoded
        line plus a newline. A failed or short write raises `AuditWriteError`."""
        record = self.record(step, result, **fields)
        data = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
        step_text = f"inspect {self.path} (free space, permissions) and run again"
        try:
            written = self.write(self.fd, data)
        except OSError as exc:
            raise AuditWriteError(f"the audit file cannot be written: {exc.strerror or exc}",
                                  step_text) from exc
        if written != len(data):
            raise AuditWriteError(f"the audit file cannot be written: a short write "
                                  f"({written} of {len(data)} bytes)", step_text)
        self.lines += 1
        return record

    def close(self) -> None:
        if self.fd >= 0:
            try:
                os.close(self.fd)
            finally:
                self.fd = -1


def open_audit(repo_root, environ=None, *, archive_root=None, clock=None, run_id=None,
               write=os.write, stat=os.stat) -> Audit:
    """Open the audit file for appending, creating the directory (0700) and the file
    (0600) when absent, or raise `AuditRefusal`. `stat` is the seam through which the
    owner and mode checks look (a path or an open descriptor)."""
    environ = os.environ if environ is None else environ
    path = audit_path(environ)
    state_dir = path.parent
    step = "set XDG_STATE_HOME to a private directory outside the repository and the archive store"
    real_dir = os.path.realpath(state_dir)
    real_path = os.path.join(real_dir, AUDIT_NAME)
    for label, root in (("the repository", repo_root),
                        ("the archive store", archive_root or archive_store(environ))):
        if _inside(real_path, os.path.realpath(root)):
            raise _refuse(f"it is inside {label}", path, step)
    uid = os.getuid()

    try:
        _make_dirs(state_dir)
        info = stat(state_dir)
    except OSError as exc:
        raise _refuse(f"its directory cannot be created or read: {exc.strerror or exc}", path,
                      f"make {state_dir} a directory you own and can write") from exc
    if not stat_module.S_ISDIR(info.st_mode):
        raise _refuse("its directory is not a directory", path, f"remove {state_dir} and run again")
    if info.st_uid != uid or info.st_mode & 0o022:
        raise _refuse("its directory is not owned by you or is group- or world-writable", path,
                      f"run: chmod go-w {state_dir} (it must be yours)")

    flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    created = False
    try:
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, FILE_MODE)
            created = True
        except FileExistsError:
            # O_NONBLOCK: a FIFO with no reader must fail (ENXIO), never block; a
            # regular file ignores it. The check below refuses a FIFO that opens.
            fd = os.open(path, flags | os.O_NONBLOCK)
    except OSError as exc:
        why = ("it is a link" if exc.errno == errno.ELOOP else
               "it is a directory" if exc.errno == errno.EISDIR else
               "it is not a regular file" if exc.errno == errno.ENXIO else
               f"it cannot be opened: {exc.strerror or exc}")
        raise _refuse(why, path, f"fix or remove {path} and run again") from exc
    try:
        if created:
            os.fchmod(fd, FILE_MODE)        # the umask only narrows; this makes it exact
        info = stat(fd)
        if not stat_module.S_ISREG(info.st_mode):
            raise _refuse("it is not a regular file", path, f"remove {path} and run again")
        if info.st_uid != uid or info.st_mode & 0o022:
            raise _refuse("it is not owned by you or is group- or world-writable", path,
                          f"run: chmod go-w {path} (it must be yours)")
    except BaseException:
        os.close(fd)
        raise
    return Audit(fd, path, str(Path(repo_root).resolve()),
                 clock=clock or (lambda: datetime.datetime.now(datetime.timezone.utc)),
                 run_id=run_id or uuid.uuid4().hex, write=write)


# ---------------------------------------------------------------------------
# The unattended run (CP3)
# ---------------------------------------------------------------------------

KIND = "retention_cleanup_run"
DONE, STOPPED, NOTHING_TO_DO, NOTHING_ELIGIBLE = "done", "stopped", "nothing-to-do", \
    "nothing-eligible"

MIX_CAUSE = ("retention cleanup: --confirm and --unattended cannot be combined (the per-plan "
             "sentence and the adopted unattended policy are two authorities)")
JSON_CAUSE = "retention cleanup: --json is for the unattended run"


def argument_refusal(args) -> tuple[str, str] | None:
    """Rows a and b of the authority table: argument checks, before anything is read."""
    unattended = bool(getattr(args, "unattended", False))
    again = f"{retention.PROGRAM} retention-cleanup {shlex.quote(str(args.target))}"
    if unattended and args.confirm is not None:
        return MIX_CAUSE, f"run {again} --unattended alone, or {again} --confirm \"...\" alone"
    if getattr(args, "json", False) and not unattended:
        return JSON_CAUSE, f"add --unattended, or run {again} without --json"
    return None


def _fail(cause: str, step: str) -> int:
    print(f"error: {cause}", file=sys.stderr)
    print(f"next: {step}", file=sys.stderr)
    return 2


def _audit_text(audit) -> str:
    return f"  audit: {audit.path}"


class _Recorder:
    """The run's observer: appends one audit line per step and keeps the steps for
    the JSON document."""

    def __init__(self, audit: Audit, policy_digest: str, plan_digest: str):
        self.audit, self.policy_digest, self.plan_digest = audit, policy_digest, plan_digest
        self.steps: dict[str, list] = {}

    def __call__(self, step, item_id, result, engine_code, text):
        self.steps.setdefault(item_id, []).append(
            {"step": step, "result": result, "engine_code": engine_code, "error": text})
        self.audit.line(step, result, policy_digest=self.policy_digest,
                        plan_digest=self.plan_digest, item_id=item_id,
                        engine_code=engine_code, error=text)


def _prune_section(unattended, outcome: str, result=None) -> dict:
    """The document's `prune` section (plan section 2.5). `unattended` is the adopted
    object (None when there is none), `result` the phase's, when it ran."""
    enabled = outcome != "disabled"
    plan = result.plan if result is not None else None
    return {
        "enabled": bool(unattended and unattended.get("prune") is True),
        "outcome": outcome,
        "ttl_days": unattended["ttl_days"] if enabled else None,
        "max_per_run": unattended["prune_max_per_run"] if enabled else None,
        "plan_digest": result.digest if result is not None else None,
        "ids": list(plan.ids) if plan is not None else [],
        "results": [dict(entry) for entry in result.results] if result is not None else [],
        "skipped": [{"id": shown, "reason": why}
                    for shown, why in (plan.skipped if plan is not None else ())],
    }


def _document(audit, plan, plan_digest_value, outcome, *, result=None, recorder=None,
              exit_code=0, audit_error=None, prune=None, prune_result=None) -> dict:
    items = []
    stop = result.stop if result is not None else None
    for index, item in enumerate(plan.items):
        if result is not None and index < result.done:
            state = "done"
        elif stop is not None and stop["item_id"] == item.work_item_id:
            state = "stopped"
        else:
            state = "not-attempted"
        items.append({"id": item.work_item_id, "action": item.action, "result": state,
                      "steps": list(recorder.steps.get(item.work_item_id, ())) if recorder
                      else []})
    stopped = None
    if stop is not None:
        stopped = {"step": stop["step"], "item_id": stop["item_id"],
                   "engine_code": stop["engine_code"], "error": stop["error"],
                   "next_step": result.next_step}
    elif prune_result is not None and prune_result.stop is not None:
        later = prune_result.stop
        stopped = {"step": later["step"], "item_id": later["item_id"],
                   "engine_code": later["engine_code"], "error": later["error"],
                   "next_step": prune_result.next_step}
    document = {
        "kind": KIND, "schema_version": SCHEMA_VERSION, "repository": audit.repository,
        "run_id": audit.run_id, "policy_digest": plan.policy_digest,
        "plan_digest": plan_digest_value, "outcome": outcome, "items": items,
        "done": result.done if result is not None else 0,
        "total": len(plan.items), "stopped": stopped,
        "thresholds_reached": list(plan.reached) if outcome == NOTHING_ELIGIBLE else [],
        "exit_code": exit_code,
        "audit": {"path": str(audit.path), "lines_written": audit.lines, "error": audit_error},
    }
    document["prune"] = prune
    return document


def _print_document(document: dict) -> None:
    print(json.dumps(document, indent=2, sort_keys=False, ensure_ascii=True))


def _prune_observer(audit: Audit, policy_digest: str):
    def observe(step, item_id, result, engine_code, text, plan_digest):
        audit.line(step, result, policy_digest=policy_digest, plan_digest=plan_digest,
                   item_id=item_id, engine_code=engine_code, error=text)
    return observe


def _irreversible(count: int, total: int, *, done: bool) -> str:
    lead = (f"retention prune: done, {count} of {total} archives deleted" if done
            else f"retention prune: {count} of {total} archives were deleted before the stop")
    return (f"{lead}; a deleted archive cannot be undone; the archive store is {ARCHIVE_ROOT}, "
            "which the Manager does not back up")


def run_command(args, preflight, *, environ=None, **seams) -> int:
    """`retention-cleanup TARGET --unattended [--json]`, after the caller has checked
    the arguments and that the target is managed with a readable record. `preflight`
    is called as `preflight(unattended=True)` and returns the `Cleared` state or
    raises `retention_cleanup.Refusal`. `seams` go to `open_audit` (tests).

    The cleanup phase runs first; when the adopted policy has `unattended.prune` true
    and the cleanup phase did not stop, the prune phase follows (a nothing-to-do or
    nothing-eligible cleanup included)."""
    as_json = bool(getattr(args, "json", False))
    try:
        audit = open_audit(args.target, environ, **seams)
    except AuditRefusal as refusal:
        return _fail(refusal.cause, refusal.step)
    try:
        try:
            cleared = preflight(unattended=True)
        except retention_cleanup.Refusal as refusal:
            try:
                audit.line("preflight", "refused", error=refusal.cause)
            except AuditWriteError as failed:
                print(f"error: {refusal.cause}", file=sys.stderr)
                print(f"error: the audit file could not record this refusal: {failed.cause}",
                      file=sys.stderr)
                print(f"next: {refusal.step}", file=sys.stderr)
                return 2
            return _fail(refusal.cause, refusal.step)
        plan = retention_cleanup.select(cleared.state, cleared.report)
        policy_digest = plan.policy_digest
        unattended = cleared.state.unattended
        prune_on = bool(unattended and unattended.get("prune") is True)
        if as_json:
            emit = lambda line: print(line, file=sys.stderr, flush=True)  # noqa: E731
        else:
            emit = lambda line: print(line, flush=True)  # noqa: E731

        digest = None
        result = recorder = None
        if plan.items:
            digest = retention_cleanup.plan_digest(plan)
            try:
                audit.line("plan", "started", policy_digest=policy_digest, plan_digest=digest)
            except AuditWriteError as failed:
                return _fail(failed.cause, failed.step)
            recorder = _Recorder(audit, policy_digest, digest)
            result = retention_run.run(args.target, plan, emit if as_json else None,
                                       unattended=True, observer=recorder,
                                       audit_where=str(audit.path),
                                       closing="" if prune_on else None)
            cleanup_stopped = result.exit_code != 0
            outcome = STOPPED if cleanup_stopped else DONE
        else:
            cleanup_stopped = False
            if plan.outcome is None:
                outcome = NOTHING_TO_DO
                if not as_json:
                    for line in retention_cleanup.preview_lines(plan, args.target):
                        print(line)
            else:
                outcome = NOTHING_ELIGIBLE
                digest = retention_cleanup.plan_digest(plan)
                try:
                    audit.line("plan", "nothing-eligible", policy_digest=policy_digest,
                               plan_digest=digest)
                except AuditWriteError as failed:
                    return _fail(failed.cause, failed.step)
                if not as_json:
                    left = ", ".join(retention_cleanup._measured(key, plan.before,
                                                                 with_limit=plan.thresholds)
                                     for key in plan.reached)
                    skipped = ""
                    if plan.skipped:
                        skipped = f", skipped: {', '.join(shown for shown, _ in plan.skipped)}"
                    print(f"retention cleanup: nothing eligible ({left}; no item is eligible"
                          f"{skipped}; running it again will not help)")

        prune_result = None
        prune_outcome = "disabled"
        if prune_on and cleanup_stopped:
            prune_outcome = "not-attempted"
        elif prune_on:
            prune_result = retention_prune.run_phase(
                args.target, unattended, policy_digest, emit,
                observer=_prune_observer(audit, policy_digest), audit_where=str(audit.path))
            prune_outcome = prune_result.outcome
            ttl, cap = unattended["ttl_days"], unattended["prune_max_per_run"]
            if prune_outcome == retention_prune.NOTHING_TO_PRUNE:
                emit(f"retention prune: nothing to prune (ttl_days {ttl}, at most {cap} per run)")
                if prune_result.plan is not None:
                    for shown, why in prune_result.plan.skipped:
                        emit(f"  skipped: {shown} ({why})")
            elif prune_result.done:
                emit(_irreversible(prune_result.done, len(prune_result.results),
                                   done=prune_outcome == retention_prune.DONE))
        prune_stopped = prune_result is not None and prune_result.outcome == retention_prune.STOPPED

        if cleanup_stopped:
            exit_code = result.exit_code
        elif prune_stopped:
            ran = bool(result is not None and result.calls) or prune_result.apply_attempted
            exit_code = 1 if ran else 2
        else:
            exit_code = 0
        if prune_stopped:
            outcome = STOPPED

        if not as_json and (plan.items or audit.lines or prune_stopped):
            print(_audit_text(audit), flush=True)
        failed_phase = result if cleanup_stopped else prune_result if prune_stopped else None
        if failed_phase is not None:
            print(f"error: {failed_phase.error}", file=sys.stderr)
            print(f"next: {failed_phase.next_step}", file=sys.stderr)
        if as_json:
            audit_error = (result.audit_error if result is not None else None) or (
                prune_result.audit_error if prune_result is not None else None)
            _print_document(_document(
                audit, plan, digest, outcome, result=result, recorder=recorder,
                exit_code=exit_code, audit_error=audit_error,
                prune=_prune_section(unattended, prune_outcome, prune_result),
                prune_result=prune_result))
        return exit_code
    finally:
        audit.close()
