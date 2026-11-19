"""The unattended retention run's audit file (CP2).

One JSON object per line is appended to `retention-audit.jsonl` in
`$XDG_STATE_HOME/workflow-manager/` (a relative or empty `XDG_STATE_HOME` is ignored,
as the XDG rule says; the default is `~/.local/state/workflow-manager/`). The file is
outside the repository and outside the engine's archive store, so the clean-tree
check is untouched. It is opened append-only and written one whole line per
`os.write`: never seeked, truncated or rewritten.

Nothing calls this module yet; the run that uses it is the next checkpoint's.
"""

from __future__ import annotations

import datetime
import errno
import json
import os
import stat as stat_module
import uuid
from pathlib import Path

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
            fd = os.open(path, flags)
    except OSError as exc:
        why = ("it is a link" if exc.errno == errno.ELOOP else
               "it is a directory" if exc.errno == errno.EISDIR else
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
