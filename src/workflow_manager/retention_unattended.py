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

from . import retention, retention_cleanup, retention_run

SCHEMA_VERSION = 1
AUDIT_NAME = "retention-audit.jsonl"
STATE_DIR_NAME = "workflow-manager"
DIR_MODE, FILE_MODE = 0o700, 0o600
# The engine's own default archive store (`scripts/workflow_retention.py`,
# `DEFAULT_ARCHIVE_ROOT`); a test pins the two together.
ARCHIVE_ROOT = "~/.local/share/workflow-archive"

# The vocabulary of a line (plan section 2.3).
STEPS = ("archive", "verify", "remove", "plan", "preflight", "policy")
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


def _document(audit, plan, plan_digest_value, outcome, *, result=None, recorder=None,
              exit_code=0, audit_error=None) -> dict:
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
    return {
        "kind": KIND, "schema_version": SCHEMA_VERSION, "repository": audit.repository,
        "run_id": audit.run_id, "policy_digest": plan.policy_digest,
        "plan_digest": plan_digest_value, "outcome": outcome, "items": items,
        "done": result.done if result is not None else 0,
        "total": len(plan.items), "stopped": stopped,
        "thresholds_reached": list(plan.reached) if outcome == NOTHING_ELIGIBLE else [],
        "exit_code": exit_code,
        "audit": {"path": str(audit.path), "lines_written": audit.lines, "error": audit_error},
    }


def _print_document(document: dict) -> None:
    print(json.dumps(document, indent=2, sort_keys=False, ensure_ascii=True))


def run_command(args, preflight, *, environ=None, **seams) -> int:
    """`retention-cleanup TARGET --unattended [--json]`, after the caller has checked
    the arguments and that the target is managed with a readable record. `preflight`
    is called as `preflight(unattended=True)` and returns the `Cleared` state or
    raises `retention_cleanup.Refusal`. `seams` go to `open_audit` (tests)."""
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
        if not plan.items:
            return _empty(args, audit, plan, as_json)
        digest = retention_cleanup.plan_digest(plan)
        try:
            audit.line("plan", "started", policy_digest=policy_digest, plan_digest=digest)
        except AuditWriteError as failed:
            return _fail(failed.cause, failed.step)
        recorder = _Recorder(audit, policy_digest, digest)
        emit = (lambda line: print(line, file=sys.stderr, flush=True)) if as_json else None
        result = retention_run.run(args.target, plan, emit, unattended=True,
                                   observer=recorder, audit_where=str(audit.path))
        if not as_json:
            print(_audit_text(audit), flush=True)
        if result.exit_code != 0:
            print(f"error: {result.error}", file=sys.stderr)
            print(f"next: {result.next_step}", file=sys.stderr)
        if as_json:
            _print_document(_document(
                audit, plan, digest, DONE if result.exit_code == 0 else STOPPED,
                result=result, recorder=recorder, exit_code=result.exit_code,
                audit_error=result.audit_error))
        return result.exit_code
    finally:
        audit.close()


def _empty(args, audit: Audit, plan, as_json: bool) -> int:
    """An empty plan: nothing to do (no threshold reached; no line) or nothing
    eligible (a threshold reached that no item can lower; one `plan` line)."""
    if plan.outcome is None:
        if as_json:
            _print_document(_document(audit, plan, None, NOTHING_TO_DO))
        else:
            for line in retention_cleanup.preview_lines(plan, args.target):
                print(line)
        return 0
    digest = retention_cleanup.plan_digest(plan)
    try:
        audit.line("plan", "nothing-eligible", policy_digest=plan.policy_digest,
                   plan_digest=digest)
    except AuditWriteError as failed:
        return _fail(failed.cause, failed.step)
    if as_json:
        _print_document(_document(audit, plan, digest, NOTHING_ELIGIBLE))
        return 0
    left = ", ".join(retention_cleanup._measured(key, plan.before, with_limit=plan.thresholds)
                     for key in plan.reached)
    skipped = ""
    if plan.skipped:
        skipped = f", skipped: {', '.join(shown for shown, _ in plan.skipped)}"
    print(f"retention cleanup: nothing eligible ({left}; no item is eligible{skipped}; "
          "running it again will not help)")
    print(_audit_text(audit))
    return 0
