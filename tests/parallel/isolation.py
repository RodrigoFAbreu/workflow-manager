"""Isolation and the repository-integrity guard (plan sections 5.7-5.9).

- `run_chunk` runs one chunk in its own process, in a new session, with the
  per-chunk environment and a private `TMPDIR`; it kills the chunk's whole
  process group on timeout and again once the chunk has exited, and
  classifies the outcome (a timeout or a missing record is an
  infrastructure fault, never a pass).
- `phase_a_order` puts every exclusive chunk into pre-phase A0, ahead of
  every shared chunk; `check_exclusive_windows` re-checks from recorded
  timestamps that no exclusive window overlapped any other.
- `acquire_run_lock` takes the checkout run lock under the per-worktree git
  dir (`<git dir>/wm-verify/run.lock`); it never waits.
- `apply_barrier`/`restore_barrier`/`recover_barrier` are the write barrier
  over `resources.GUARDED_TREES`, its crash marker and its lock-gated
  recovery.
- `attribute_integrity_diff` names the chunks a persistent tree change can
  be attributed to; `lint_tests` is the static writer lint.

Every function takes `repo_root`; nothing here reads a module-level root.
"""

from __future__ import annotations

import ast
import errno
import fcntl
import os
import shutil
import signal
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import canonical_json, strict_json_loads
from .plan_schema import ChunkDescriptor, shard_chunks
from .resources import GUARDED_TREES

STATE_DIR_NAME = "wm-verify"
LOCK_NAME = "run.lock"
MARKER_NAME = "barrier.json"
MARKER_SCHEMA_VERSION = 1

#: Per-chunk timeout: `max(600, 5 x estimate)`, capped (plan 5.9 step 4).
TIMEOUT_FLOOR = 600
TIMEOUT_FACTOR = 5
TIMEOUT_CAP = 3600

#: How often `run_chunk` polls a live chunk for exit or timeout.
POLL_SECONDS = 0.05

# Outcomes. The first two are the chunk's own verdict; every other one is an
# infrastructure fault (plan INV-7).
PASSED = "passed"
FAILED = "failed"
TIMED_OUT = "timed_out"
MISSING_RECORD = "missing_record"
BAD_RECORD = "bad_record"
RECORD_MISMATCH = "record_mismatch"
INFRASTRUCTURE_OUTCOMES = (TIMED_OUT, MISSING_RECORD, BAD_RECORD, RECORD_MISMATCH)


class IsolationError(Exception):
    """Base of every refusal this module raises."""


class RunLockHeldError(IsolationError):
    """Another run (or a chunk process it left behind) holds this checkout's
    run lock."""

    def __init__(self, message: str, holder: dict | None):
        super().__init__(message)
        self.holder = holder


class RootRefusedError(IsolationError):
    """Running as root disables the write barrier's effect."""


class BarrierError(IsolationError):
    """The barrier or its marker is not in a state this call can act on."""


class ExclusiveOverlapError(IsolationError):
    """An exclusive chunk's execution window overlapped another chunk's."""


# -- the per-worktree state directory -----------------------------------------------

def git_dir(repo_root: Path) -> Path:
    """`git rev-parse --absolute-git-dir`: the *per-worktree* git dir, so two
    linked worktrees never share a lock or a marker."""
    out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--absolute-git-dir"],
                         check=True, capture_output=True, text=True).stdout.strip()
    return Path(out)


def state_dir(repo_root: Path) -> Path:
    return git_dir(repo_root) / STATE_DIR_NAME


def _write_atomic(path: Path, text: str) -> None:
    """Temporary name, `fsync`, rename, `fsync` the directory."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


# -- the checkout run lock (5.9 step 0) ----------------------------------------------

class RunLock:
    """A held `flock(LOCK_EX)` on `<git dir>/wm-verify/run.lock`.

    The file records the holder: executor pid, start time, and the process
    groups of its live chunks. Pass `fd` to every chunk process (`pass_fds`) so
    the lock stays held until the last chunk process has exited. The holder
    record is updated under a mutex, so worker threads may share one lock."""

    def __init__(self, repo_root: Path, path: Path, fd: int, holder: dict):
        self.repo_root = Path(repo_root)
        self.path = path
        self.fd = fd
        self.holder = holder
        self._mutex = threading.Lock()

    @property
    def held(self) -> bool:
        return self.fd >= 0

    def _publish(self) -> None:
        data = canonical_json(self.holder).encode()
        os.ftruncate(self.fd, 0)
        os.pwrite(self.fd, data, 0)
        os.fsync(self.fd)

    def add_chunk_pgid(self, pgid: int) -> None:
        with self._mutex:
            self.holder["chunk_pgids"] = sorted(set(self.holder["chunk_pgids"]) | {pgid})
            self._publish()

    def remove_chunk_pgid(self, pgid: int) -> None:
        with self._mutex:
            if self.fd >= 0:
                self.holder["chunk_pgids"] = sorted(set(self.holder["chunk_pgids"]) - {pgid})
                self._publish()

    def live_chunk_pgids(self) -> list[int]:
        with self._mutex:
            return list(self.holder["chunk_pgids"])

    def release(self) -> None:
        # Close only, never `LOCK_UN`: the lock belongs to the open file
        # description every chunk inherited, and unlocking it here would drop
        # it for a chunk that is still alive.
        if self.fd < 0:
            return
        os.close(self.fd)
        self.fd = -1

    def __enter__(self) -> "RunLock":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def _read_holder(path: Path) -> dict | None:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _group_exists(pgid) -> bool:
    if type(pgid) is not int or pgid <= 1:  # 0 would probe our own group
        return False
    try:
        os.killpg(pgid, 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OverflowError):
        return False
    return True


def _kill_hint(pgids) -> str:
    """How to free the lock by hand. The recorded groups are as of the
    holder's last update: after a SIGKILLed executor some may be gone and
    their ids reused, and a chunk started but not yet registered is missing,
    so the hint names only groups that still exist and says to verify first."""
    live = [p for p in pgids if _group_exists(p)]
    gone = [p for p in pgids if p not in live]
    hint = ""
    if gone:
        hint += f"; no longer running: {gone}"
    if live:
        hint += ("; verify each group still belongs to that run (ids can be reused) "
                 "before killing it: " + "; ".join(f"kill -- -{p}" for p in live))
    return hint + ("; a chunk not yet recorded is not listed -- any process holding "
                   "the lock file open keeps it held")


def acquire_run_lock(repo_root: Path, *, now: float | None = None) -> RunLock:
    """Take this checkout's run lock, or refuse at once (`RunLockHeldError`,
    naming the recorded holder and its chunk process groups). Never waits and
    never touches the barrier."""
    directory = state_dir(repo_root)
    directory.mkdir(exist_ok=True)
    path = directory / LOCK_NAME
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
            raise
        holder = _read_holder(path)
        pgids = (holder or {}).get("chunk_pgids") or []
        raise RunLockHeldError(
            f"{path} is held by another run: {holder!r} (its chunk process groups: "
            f"{pgids}{_kill_hint(pgids)})", holder) from None
    holder = {"pid": os.getpid(), "started_at": time.time() if now is None else now,
              "repo_root": str(Path(repo_root).resolve()), "chunk_pgids": []}
    lock = RunLock(repo_root, path, fd, holder)
    lock._publish()
    return lock


def _require_lock(repo_root: Path, lock: RunLock) -> None:
    if not isinstance(lock, RunLock) or not lock.held:
        raise BarrierError("the barrier is only ever touched under a held run lock")
    if lock.path != state_dir(repo_root) / LOCK_NAME:
        raise BarrierError(f"{lock.path} is not {repo_root}'s run lock")


# -- per-chunk execution (5.7, 5.9 step 4) ---------------------------------------------

def chunk_timeout(estimate: float) -> float:
    return min(TIMEOUT_CAP, max(TIMEOUT_FLOOR, TIMEOUT_FACTOR * float(estimate)))


def _safe_name(chunk_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in chunk_id)


@dataclass(frozen=True)
class ChunkPaths:
    record: Path
    log: Path
    tmp: Path


def chunk_paths(run_dir: Path, chunk_id: str) -> ChunkPaths:
    """Where `run_chunk` expects a chunk's record and puts its log and
    `TMPDIR` -- all inside `run_dir`, which lives outside the checkout (5.6)."""
    name = _safe_name(chunk_id)
    run_dir = Path(run_dir)
    return ChunkPaths(run_dir / "records" / f"{name}.json", run_dir / "logs" / f"{name}.log",
                      run_dir / "tmp" / name)


# -- quiet Git: the chunk environment's layer (D-Quiet-Git-Env) ---------------------------

#: `src/workflow_manager/fixture.py`, located from this file, never from a
#: `repo_root` argument: its `THROWAWAY_GIT_CONFIG` literal is the one
#: definition of the settings, read as data because the executor process never
#: imports `workflow_manager` (frozen_chunk.py's docstring).
FIXTURE_SOURCE = Path(__file__).resolve().parents[2] / "src" / "workflow_manager" / "fixture.py"

#: Where the executor builds the run's Git template, under its run directory.
GIT_TEMPLATE_DIR_NAME = "git-template"

#: What Git's own default template is read without: a user or system
#: `init.templateDir`, and any inherited config entries (an operator's
#: `-c init.templateDir=...` reaches a child through these).
_TEMPLATE_BUILD_DROPPED = ("GIT_TEMPLATE_DIR", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")


class GitConfigEnvError(IsolationError):
    """The inherited environment's Git config entries cannot be extended
    safely: a malformed `GIT_CONFIG_COUNT` series, or a
    `GIT_CONFIG_PARAMETERS` that sets one of the quiet keys (it outranks
    every `GIT_CONFIG_COUNT` entry) or cannot be parsed."""


def _load_throwaway_git_config() -> dict[str, str]:
    tree = ast.parse(FIXTURE_SOURCE.read_text(encoding="utf-8"), filename=str(FIXTURE_SOURCE))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None)
        if isinstance(target, ast.Name) and target.id == "THROWAWAY_GIT_CONFIG":
            value = ast.literal_eval(node.value)
            if (isinstance(value, dict) and value
                    and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())):
                return dict(value)
            break
    raise IsolationError(f"{FIXTURE_SOURCE}: no THROWAWAY_GIT_CONFIG string mapping")


THROWAWAY_GIT_CONFIG = _load_throwaway_git_config()


def _sq_token(text: str, i: int) -> tuple[str, int]:
    """One `sq_quote`d token of `GIT_CONFIG_PARAMETERS` starting at `text[i]`:
    `'...'`, where `'\\''` and `'\\!'` continue it with a literal `'` or `!`."""
    if i >= len(text) or text[i] != "'":
        raise ValueError(f"expected a quote at offset {i}")
    out = []
    i += 1
    while True:
        end = text.find("'", i)
        if end < 0:
            raise ValueError("unterminated quote")
        out.append(text[i:end])
        i = end + 1
        if text[i:i + 1] == "\\" and text[i + 1:i + 2] in ("'", "!") and text[i + 2:i + 3] == "'":
            out.append(text[i + 1])
            i += 3
            continue
        return "".join(out), i


def parse_git_config_parameters(text: str) -> list[tuple[str, str | None]]:
    """`GIT_CONFIG_PARAMETERS` as Git writes it (`git -c`): space-separated
    entries, each `'key'='value'`, `'key'=` (no value) or the older
    `'key=value'`. Raises `ValueError` on anything else."""
    entries = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        token, i = _sq_token(text, i)
        if text[i:i + 1] == "=":
            i += 1
            if text[i:i + 1] == "'":
                value, i = _sq_token(text, i)
                entries.append((token, value))
            else:
                entries.append((token, None))
        else:
            key, sep, value = token.partition("=")
            entries.append((key, value if sep else None))
        if i < len(text) and not text[i].isspace():
            raise ValueError(f"unexpected {text[i]!r} at offset {i}")
    return entries


def _git_config_count(env: dict) -> int:
    raw = env.get("GIT_CONFIG_COUNT")
    if raw is None:
        return 0
    if not (raw.isascii() and raw.isdigit()):
        raise GitConfigEnvError(
            f"GIT_CONFIG_COUNT={raw!r} is not a non-negative integer; Git would refuse "
            "every command under it")
    count = int(raw)
    for index in range(count):
        for name in (f"GIT_CONFIG_KEY_{index}", f"GIT_CONFIG_VALUE_{index}"):
            if name not in env:
                raise GitConfigEnvError(
                    f"GIT_CONFIG_COUNT={count} but {name} is not set; Git would refuse "
                    "every command under it")
    return count


def quiet_git_config(env: dict) -> dict:
    """Append `THROWAWAY_GIT_CONFIG` to `env`'s `GIT_CONFIG_COUNT` series, in
    place, and return `env` (plan 5.2).

    The parent's entries are kept and ours are numbered after them. A key is
    appended unless the *last* inherited value for it (matched
    case-insensitively, as Git does) is already ours, as the same string --
    Git uses a single-valued key's last value -- so a nested call appends
    nothing. A `GIT_CONFIG_PARAMETERS` that sets one of the keys would
    outrank anything appended here, so it is refused, as is one that cannot
    be parsed or a malformed `GIT_CONFIG_COUNT` series (`GitConfigEnvError`)."""
    wanted = {key.lower() for key in THROWAWAY_GIT_CONFIG}
    parameters = env.get("GIT_CONFIG_PARAMETERS")
    if parameters is not None:
        try:
            entries = parse_git_config_parameters(parameters)
        except ValueError as exc:
            raise GitConfigEnvError(
                f"GIT_CONFIG_PARAMETERS cannot be parsed ({exc}): {parameters!r}") from None
        clashes = sorted({key for key, _ in entries if key.lower() in wanted})
        if clashes:
            raise GitConfigEnvError(
                f"GIT_CONFIG_PARAMETERS sets {', '.join(clashes)}, which outranks the "
                "runner's quiet-Git settings; unset it (or drop those keys) and re-run")
    count = _git_config_count(env)
    last: dict[str, str] = {}
    for index in range(count):
        last[env[f"GIT_CONFIG_KEY_{index}"].lower()] = env[f"GIT_CONFIG_VALUE_{index}"]
    for key, value in THROWAWAY_GIT_CONFIG.items():
        if last.get(key.lower()) == value:
            continue
        env[f"GIT_CONFIG_KEY_{count}"] = key
        env[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    if count or "GIT_CONFIG_COUNT" in env:
        env["GIT_CONFIG_COUNT"] = str(count)
    return env


def check_git_env(environ: dict | None = None) -> None:
    """Refuse (`GitConfigEnvError`) an inherited environment `chunk_env` could
    not extend -- called by every mode that runs chunks, before any starts."""
    quiet_git_config(dict(os.environ if environ is None else environ))


def build_git_template(run_dir: Path) -> Path:
    """`<run_dir>/git-template/`: Git's own default template plus a `config`
    holding `THROWAWAY_GIT_CONFIG`, which Git copies into every repository
    `git init` or `git clone` creates (plan 5.2). Built once per run, before
    any chunk starts; returns its path."""
    run_dir = Path(run_dir)
    template = run_dir / GIT_TEMPLATE_DIR_NAME
    scratch = run_dir / "git-template-scratch"
    for path in (template, scratch):
        if path.exists():
            shutil.rmtree(path)
    env = {name: value for name, value in os.environ.items()
           if name not in _TEMPLATE_BUILD_DROPPED
           and not name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.pop("GIT_CONFIG_SYSTEM", None)
    try:
        subprocess.run(["git", "init", "-q", str(scratch)], check=True, capture_output=True,
                       env=env)
        template.mkdir(parents=True)
        for entry in sorted((scratch / ".git").iterdir()):
            if entry.name in ("HEAD", "config", "objects", "refs"):
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, template / entry.name, symlinks=True)
            else:
                shutil.copy2(entry, template / entry.name, follow_symlinks=False)
        for key, value in THROWAWAY_GIT_CONFIG.items():
            subprocess.run(["git", "config", "--file", str(template / "config"), key, value],
                           check=True, capture_output=True, env=env)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)
    return template


def chunk_env(tmpdir: Path, extra: dict | None = None, base: dict | None = None, *,
              git_template: Path | None = None) -> dict:
    """Today's environment minus `PYTHONPATH`/`FORCE_COLOR`, plus bytecode and
    colour off and the chunk's private `TMPDIR` (5.7), plus quiet Git (5.2 of
    the test-cleanup plan): `THROWAWAY_GIT_CONFIG` appended to the
    `GIT_CONFIG_*` series, and `GIT_TEMPLATE_DIR` set to `git_template` --
    or, when none is given, removed, so an inherited template never reaches
    a chunk. Raises `GitConfigEnvError` on an inherited series it cannot
    extend."""
    env = dict(os.environ if base is None else base)
    env.pop("PYTHONPATH", None)
    env.pop("FORCE_COLOR", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHON_COLORS"] = "0"
    env["TMPDIR"] = str(tmpdir)
    env.update(extra or {})
    if git_template is None:
        env.pop("GIT_TEMPLATE_DIR", None)
    else:
        env["GIT_TEMPLATE_DIR"] = str(git_template)
    return quiet_git_config(env)


def _make_removable(root: Path) -> None:
    """Add `u+rwx` to every directory under `root` -- a copy of a guarded tree
    made under the barrier arrives `u-w` (5.9, "The barrier propagates into
    copies")."""
    for dirpath, dirnames, _ in os.walk(root):
        for name in dirnames:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IRWXU)
    if root.is_dir() and not root.is_symlink():
        os.chmod(root, stat.S_IMODE(os.lstat(root).st_mode) | stat.S_IRWXU)


def _residue(tmp: Path) -> tuple[str, ...]:
    if not tmp.is_dir():
        return ()
    found = []
    for dirpath, dirnames, filenames in os.walk(tmp):
        for name in dirnames + filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), tmp))
    return tuple(sorted(found, key=os.fsencode))


def clean_tmpdir(tmp: Path) -> tuple[str, ...]:
    """List what a chunk left in its private `TMPDIR`, then remove it all,
    permissions reset first. Returns the residue (relative paths)."""
    tmp = Path(tmp)
    if not tmp.exists():
        return ()
    _make_removable(tmp)
    residue = _residue(tmp)
    shutil.rmtree(tmp)
    return residue


@dataclass(frozen=True)
class ChunkRun:
    chunk_id: str
    outcome: str
    returncode: int | None
    record: dict | None
    log_path: Path
    started_at: float
    ended_at: float
    pgid: int
    tmp_residue: tuple[str, ...] = ()
    detail: str = ""

    @property
    def infrastructure_fault(self) -> str | None:
        if self.outcome in INFRASTRUCTURE_OUTCOMES:
            return f"{self.outcome}: {self.detail}" if self.detail else self.outcome
        return None

    @property
    def window(self) -> "Window":
        return Window(self.chunk_id, self.started_at, self.ended_at)


def _exited(pid: int) -> bool:
    """True once `pid` has exited, *without* reaping it: the zombie keeps the
    pid (and so the process-group id) from being reused until the group has
    been killed."""
    info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return info is not None


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _classify(returncode: int, record_path: Path) -> tuple[str, dict | None, str]:
    if not record_path.exists():
        return MISSING_RECORD, None, f"no result record (runner exit {returncode})"
    try:
        record = strict_json_loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return BAD_RECORD, None, f"unreadable result record: {exc}"
    if not isinstance(record, dict):
        return BAD_RECORD, None, "result record is not an object"
    if returncode not in (0, 1):
        return RECORD_MISMATCH, record, f"runner exit {returncode} with a record"
    passed = record.get("passed")
    if isinstance(passed, bool) and passed != (returncode == 0):
        return RECORD_MISMATCH, record, f"runner exit {returncode} disagrees with its record"
    return (PASSED if returncode == 0 else FAILED), record, ""


def run_chunk(repo_root: Path, chunk_id: str, argv, *, run_dir: Path, timeout: float,
              cwd: Path | None = None, extra_env: dict | None = None,
              lock: RunLock | None = None, git_template: Path | None = None) -> ChunkRun:
    """Run one chunk in its own process and session.

    `argv` must make the chunk write its record to
    `chunk_paths(run_dir, chunk_id).record`. The chunk's stdout and stderr go
    to its log. With `lock`, the lock fd is passed to the chunk process and its
    process group is recorded in the lock file while it runs. On timeout the
    whole group is killed (`timed_out`); once the chunk process has exited, for
    any reason, its group is killed again so no descendant outlives it. The
    private `TMPDIR` is emptied afterwards and what was in it is reported.
    `git_template` is the run's Git template (`chunk_env`)."""
    paths = chunk_paths(run_dir, chunk_id)
    for directory in (paths.record.parent, paths.log.parent):
        directory.mkdir(parents=True, exist_ok=True)
    paths.record.unlink(missing_ok=True)
    if paths.tmp.exists():
        clean_tmpdir(paths.tmp)
    paths.tmp.mkdir(parents=True)
    env = chunk_env(paths.tmp, extra_env, git_template=git_template)
    pass_fds = (lock.fd,) if lock is not None else ()

    timed_out = False
    started_at = time.time()
    started = time.monotonic()
    proc = None
    log = open(paths.log, "wb")
    # The spawn is inside the `try`, so an interrupt landing at any point
    # once the chunk exists -- before its group is registered, too -- still
    # reaches the `finally` that kills that group.
    try:
        proc = subprocess.Popen([str(a) for a in argv], cwd=str(cwd or repo_root), env=env,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, pass_fds=pass_fds)
        log.close()
        if lock is not None:
            lock.add_chunk_pgid(proc.pid)
        while not _exited(proc.pid):
            if time.monotonic() - started >= timeout:
                timed_out = True
                break
            time.sleep(POLL_SECONDS)
    finally:
        log.close()
        if proc is not None:
            # A new session makes the child its own group leader, and the
            # leader is still unreaped here (a zombie, or alive on timeout),
            # so its group id cannot have been recycled.
            _kill_group(proc.pid)
            returncode = proc.wait()
            ended_at = time.time()
            if lock is not None and lock.held:
                lock.remove_chunk_pgid(proc.pid)
    pgid = proc.pid

    residue = clean_tmpdir(paths.tmp)
    if timed_out:
        outcome, record, detail = TIMED_OUT, None, f"killed after {timeout:g}s"
    else:
        outcome, record, detail = _classify(returncode, paths.record)
    return ChunkRun(chunk_id, outcome, returncode, record, paths.log, started_at, ended_at,
                    pgid, residue, detail)


# -- serialization of exclusive chunks (5.8) ---------------------------------------------

@dataclass(frozen=True)
class PhaseAOrder:
    #: every exclusive chunk, in plan order (shard index, then position)
    a0: tuple[ChunkDescriptor, ...]
    #: each shard's remaining shared chunks, in stored order
    shards: tuple[tuple[ChunkDescriptor, ...], ...]


def phase_a_order(plan) -> PhaseAOrder:
    """A0 first -- every exclusive chunk, one at a time, with nothing else
    alive -- then one worker per shard over its shared chunks."""
    shards = shard_chunks(plan)
    a0 = tuple(c for shard in shards for c in shard if c.exclusive)
    rest = tuple(tuple(c for c in shard if not c.exclusive) for shard in shards)
    return PhaseAOrder(a0, rest)


@dataclass(frozen=True)
class Window:
    chunk_id: str
    start: float
    end: float
    exclusive: bool = False


def _overlap(a: Window, b: Window) -> bool:
    return a.start < b.end and b.start < a.end


def check_exclusive_windows(windows) -> None:
    """Refuse (`ExclusiveOverlapError`) any exclusive window that overlaps any
    other window. Shared windows may overlap each other freely."""
    windows = sorted(windows, key=lambda w: (w.start, w.end, w.chunk_id))
    clashes = []
    for i, a in enumerate(windows):
        for b in windows[i + 1:]:
            if b.start >= a.end:
                break
            if (a.exclusive or b.exclusive) and _overlap(a, b):
                clashes.append((a.chunk_id, b.chunk_id))
    if clashes:
        raise ExclusiveOverlapError(f"exclusive chunk windows overlapped: {sorted(clashes)}")


# -- the write barrier (5.9 steps 3-6) -------------------------------------------------

def _guarded_dirs(repo_root: Path, trees) -> list[str]:
    """Every directory (never a symlink) under `trees`, relative to
    `repo_root`, sorted."""
    root = Path(repo_root)
    found = []
    for tree in trees:
        top = root / tree
        if not top.is_dir() or top.is_symlink():
            continue
        for dirpath, dirnames, _ in os.walk(top):
            rel = os.path.relpath(dirpath, root)
            found.append(rel)
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
    return sorted(set(found), key=os.fsencode)


def _under(rel: str, trees) -> bool:
    return any(rel == t.rstrip("/") or rel.startswith(t) for t in trees)


class Barrier:
    """An applied write barrier: the guarded directories `u-w`, their original
    modes recorded in `<git dir>/wm-verify/barrier.json`."""

    def __init__(self, repo_root: Path, marker: Path, modes: dict[str, int], meta: dict,
                 warnings: list[str]):
        self.repo_root = Path(repo_root)
        self.marker = marker
        self.modes = modes
        self.meta = meta
        self.warnings = warnings
        self.lifted: tuple[str, ...] = ()
        self.restored = False

    def _write_marker(self) -> None:
        _write_atomic(self.marker, canonical_json(
            {**self.meta, "schema_version": MARKER_SCHEMA_VERSION,
             "modes": {rel: self.modes[rel] for rel in sorted(self.modes, key=os.fsencode)}}))

    def _lock_dirs(self, rels) -> None:
        for rel in rels:
            path = self.repo_root / rel
            os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) & ~stat.S_IWUSR)

    def lift(self, trees) -> None:
        """Restore the recorded modes of every directory under `trees` -- the
        union of the running exclusive unit's resource `paths` (5.8)."""
        if self.lifted:
            raise BarrierError(f"already lifted for {self.lifted}")
        trees = tuple(sorted(trees))
        unknown = [t for t in trees if t not in GUARDED_TREES]
        if unknown:
            raise BarrierError(f"not guarded trees: {unknown}")
        for rel, mode in self.modes.items():
            if _under(rel, trees) and (self.repo_root / rel).is_dir():
                os.chmod(self.repo_root / rel, mode)
        self.lifted = trees

    def relock(self) -> None:
        """Re-apply the barrier over the lifted trees, recording the original
        mode of any directory the exclusive unit created and forgetting any it
        removed -- before the next chunk starts."""
        trees, self.lifted = self.lifted, ()
        if not trees:
            return
        current = _guarded_dirs(self.repo_root, trees)
        for rel in [r for r in self.modes if _under(r, trees)]:
            if rel not in current:
                del self.modes[rel]
        for rel in current:
            if rel not in self.modes:
                self.modes[rel] = stat.S_IMODE(os.lstat(self.repo_root / rel).st_mode)
        self._write_marker()
        self._lock_dirs(current)


def lift_trees(resources, chunk: ChunkDescriptor) -> tuple[str, ...]:
    """The guarded trees an exclusive chunk's barrier window lifts: the union of
    the `paths` of the resources it holds. Nothing is inferred from a
    resource's name."""
    trees = set()
    for name in chunk.resources:
        if name not in resources.resources:
            raise BarrierError(f"chunk {chunk.id} holds undeclared resource {name!r}")
        trees.update(resources.resources[name].paths)
    return tuple(sorted(trees))


def apply_barrier(repo_root: Path, lock: RunLock, *, allow_root: bool = False,
                  now: float | None = None) -> Barrier:
    """Remove `u+w` from every directory under the guarded trees, after writing
    the marker. Only under a held run lock, and only after `recover_barrier`
    (so every mode recorded here is an original)."""
    _require_lock(repo_root, lock)
    if os.geteuid() == 0 and not allow_root:
        raise RootRefusedError("running as root disables the write barrier; refusing "
                               "without allow_root")
    marker = state_dir(repo_root) / MARKER_NAME
    if marker.exists():
        raise BarrierError(f"{marker} exists: recover_barrier first")
    rels = _guarded_dirs(repo_root, GUARDED_TREES)
    modes = {rel: stat.S_IMODE(os.lstat(Path(repo_root) / rel).st_mode) for rel in rels}
    warnings = [f"{rel} already lacks u+w before the barrier; it is restored to that mode"
                for rel, mode in modes.items() if not mode & stat.S_IWUSR]
    if os.geteuid() == 0:
        # Allowed only by `allow_root`; the report flags it (5.9).
        warnings.insert(0, "running as root (--allow-root): the write barrier does not stop "
                           "root's writes, so this run's barrier guarantees nothing")
    meta = {"pid": os.getpid(), "started_at": time.time() if now is None else now,
            "repo_root": str(Path(repo_root).resolve())}
    barrier = Barrier(repo_root, marker, modes, meta, warnings)
    try:
        barrier._write_marker()
        barrier._lock_dirs(rels)
    except BaseException:
        # A failure or signal part-way through leaves some directories `u-w`
        # and the caller no `Barrier` to restore: undo it here (5.9).
        restore_barrier(repo_root, barrier)
        raise
    return barrier


def _restore_modes(repo_root: Path, modes: dict[str, int]) -> list[str]:
    restored = []
    for rel in sorted(modes, key=os.fsencode):
        path = Path(repo_root) / rel
        if path.is_dir() and not path.is_symlink():
            os.chmod(path, modes[rel])
            restored.append(rel)
    return restored


def _remove_marker(marker: Path) -> None:
    marker.unlink(missing_ok=True)
    dir_fd = os.open(marker.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def restore_barrier(repo_root: Path, barrier: Barrier) -> None:
    """Restore every recorded mode, then delete the marker. Idempotent."""
    if barrier.restored:
        return
    if Path(repo_root).resolve() != barrier.repo_root.resolve():
        raise BarrierError(f"barrier belongs to {barrier.repo_root}, not {repo_root}")
    barrier.lifted = ()
    _restore_modes(repo_root, barrier.modes)
    _remove_marker(barrier.marker)
    barrier.restored = True


def recover_barrier(repo_root: Path, lock: RunLock) -> list[str]:
    """Undo a barrier a dead run left behind: restore the marker's recorded
    modes and delete it. Only under a held run lock -- which a start can take
    only once every process of the marker's run has exited. Returns the
    restored directories; no marker is a no-op."""
    _require_lock(repo_root, lock)
    marker = state_dir(repo_root) / MARKER_NAME
    if not marker.exists():
        return []
    try:
        raw = strict_json_loads(marker.read_text(encoding="utf-8"))
        modes = raw["modes"]
        if raw.get("schema_version") != MARKER_SCHEMA_VERSION or not isinstance(modes, dict) \
                or not all(isinstance(m, int) and not isinstance(m, bool) for m in modes.values()):
            raise ValueError("unexpected shape")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BarrierError(f"{marker}: unreadable barrier marker ({exc}); restore u+w on "
                           f"{', '.join(GUARDED_TREES)} by hand and delete it") from exc
    for rel in modes:
        if os.path.isabs(rel) or ".." in Path(rel).parts or not _under(rel + "/", GUARDED_TREES):
            raise BarrierError(f"{marker}: {rel!r} is not under a guarded tree")
    restored = _restore_modes(repo_root, modes)
    _remove_marker(marker)
    return restored


# -- attribution of a persistent change (5.9 step 6) -------------------------------------

@dataclass(frozen=True)
class Attribution:
    path: str
    before: str
    after: str
    #: the chunk ids the change is attributed to
    suspects: tuple[str, ...]
    #: "mtime" -- the path's modification time falls inside these chunks'
    #: windows; "run" -- no narrower evidence, so every chunk whose window
    #: overlapped the run
    basis: str


def attribute_integrity_diff(repo_root: Path, diffs, windows, *, run_started: float,
                             run_ended: float) -> list[Attribution]:
    """For each difference `tree.compare` reported, name the chunks whose
    execution windows overlapped the run -- narrowed to the windows containing
    the path's modification time when it still exists and one does."""
    in_run = [w for w in windows if w.start < run_ended and run_started < w.end]
    everyone = tuple(sorted({w.chunk_id for w in in_run}))
    out = []
    for diff in diffs:
        suspects, basis = everyone, "run"
        if diff.path != "HEAD":
            try:
                mtime = os.lstat(Path(repo_root) / diff.path).st_mtime
            except OSError:
                mtime = None
            if mtime is not None:
                hit = tuple(sorted({w.chunk_id for w in in_run if w.start <= mtime <= w.end}))
                if hit:
                    suspects, basis = hit, "mtime"
        out.append(Attribution(diff.path, diff.before, diff.after, suspects, basis))
    return out


# -- the static writer lint (5.9) ---------------------------------------------------------

ROOT_NAME = "REPO_ROOT"
TOOL_SCRIPTS = ("migrate.py", "build_release.py")
#: `tools` functions that write the tree they are given.
TOOL_ENTRY_POINTS = {("migrate", "migrate"), ("migrate", "write_file"), ("migrate", "main"),
                     ("build_release", "build"), ("build_release", "main")}
INSTALL_WRITERS = ("bootstrap", "update")
REMOVERS = {("shutil", "rmtree"), ("os", "remove"), ("os", "unlink"), ("os", "rmdir"),
            ("os", "removedirs")}
RECEIVER_WRITERS = ("unlink", "write_text", "write_bytes", "rmdir")
DEST_WRITERS = {("shutil", "copy"), ("shutil", "copy2"), ("shutil", "copyfile"),
                ("shutil", "copytree"), ("shutil", "copymode"), ("shutil", "copystat"),
                ("os", "rename"), ("os", "replace"), ("os", "renames")}
PATH_PRESERVING = ("resolve", "absolute", "joinpath", "with_name", "with_suffix", "with_stem",
                   "expanduser")


@dataclass(frozen=True)
class LintFinding:
    module: str
    line: int
    unit: str | None
    pattern: str
    source: str

    def __str__(self) -> str:
        where = self.unit or f"{self.module} (module level)"
        return f"{self.module}:{self.line}: {self.pattern} in {where}: {self.source}"


def _dotted(node) -> tuple[str, ...] | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return None


def _walk_scope(body):
    """Every node of `body`, not descending into nested functions, classes or
    lambdas (they are scopes of their own)."""
    stack = list(reversed(body))
    while stack:
        node = stack.pop()
        yield node
        for child in reversed(list(ast.iter_child_nodes(node))):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                      ast.Lambda)):
                stack.append(child)


class _Scope:
    def __init__(self, rooted: set[str]):
        self.rooted = set(rooted)


class _Linter(ast.NodeVisitor):
    def __init__(self, module: str, source: str):
        self.module = module
        self.source = source
        self.findings: list[LintFinding] = []
        self.classes: list[str] = []
        self.scopes: list[_Scope] = [_Scope({ROOT_NAME})]

    # -- rootedness ---------------------------------------------------------------

    def rooted(self, node) -> bool:
        """The expression is a path at or under `REPO_ROOT`, syntactically."""
        if isinstance(node, ast.Name):
            return node.id in self.scopes[-1].rooted or any(
                node.id in s.rooted for s in self.scopes[:1])
        if isinstance(node, ast.Attribute):
            return node.attr == ROOT_NAME  # `support.REPO_ROOT`
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self.rooted(node.left)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.rooted(node.left)
        if isinstance(node, ast.JoinedStr):
            first = node.values[0] if node.values else None
            return isinstance(first, ast.FormattedValue) and self.rooted(first.value)
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name in (("str",), ("Path",), ("pathlib", "Path"), ("os", "fspath"),
                        ("os", "path", "join"), ("os", "path", "abspath"),
                        ("os", "path", "realpath"), ("os", "path", "normpath")):
                return bool(node.args) and self.rooted(node.args[0])
            if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_PRESERVING:
                return self.rooted(node.func.value)
        return False

    def rooted_anywhere(self, node) -> bool:
        if self.rooted(node):
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return any(self.rooted_anywhere(e) for e in node.elts)
        if isinstance(node, ast.Starred):
            return self.rooted_anywhere(node.value)
        return False

    # -- scopes -------------------------------------------------------------------

    def _collect_assignments(self, body, scope: _Scope) -> None:
        # Flow-insensitive, to a fixed point: `a = REPO_ROOT / "x"; b = a / "y"`.
        assigns = []
        for sub in _walk_scope(body):
            if isinstance(sub, ast.Assign):
                assigns.append((sub.targets, sub.value))
            elif isinstance(sub, (ast.AnnAssign, ast.NamedExpr)) and sub.value is not None:
                assigns.append(([sub.target], sub.value))
            elif isinstance(sub, ast.withitem) and sub.optional_vars is not None:
                assigns.append(([sub.optional_vars], sub.context_expr))
        self.scopes.append(scope)
        try:
            changed = True
            while changed:
                changed = False
                for targets, value in assigns:
                    if self.rooted(value):
                        for target in targets:
                            if isinstance(target, ast.Name) and target.id not in scope.rooted:
                                scope.rooted.add(target.id)
                                changed = True
        finally:
            self.scopes.pop()

    def visit_Module(self, node):
        self._collect_assignments(node.body, self.scopes[0])
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def _visit_function(self, node):
        scope = _Scope(self.scopes[-1].rooted if len(self.scopes) > 1 else set())
        self._collect_assignments(node.body, scope)
        self.scopes.append(scope)
        self.generic_visit(node)
        self.scopes.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    # -- patterns -----------------------------------------------------------------

    def flag(self, node, pattern: str) -> None:
        unit = f"host:{self.module}::{self.classes[0]}" if self.classes else None
        segment = ast.get_source_segment(self.source, node) or ""
        self.findings.append(LintFinding(self.module, node.lineno, unit, pattern,
                                         " ".join(segment.split())[:200]))

    def visit_List(self, node):
        self._check_tool_argv(node)
        self.generic_visit(node)

    def visit_Tuple(self, node):
        self._check_tool_argv(node)
        self.generic_visit(node)

    def _check_tool_argv(self, node) -> None:
        # A nested literal is checked on its own visit.
        strings = [c.value for e in node.elts if not isinstance(e, (ast.List, ast.Tuple))
                   for c in ast.walk(e) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        if any(s.rsplit("/", 1)[-1] in TOOL_SCRIPTS for s in strings) and "--check" not in strings:
            self.flag(node, "tools script without --check")

    def visit_Call(self, node):
        name = _dotted(node.func)
        func = node.func
        args = list(node.args)
        kwargs = {k.arg: k.value for k in node.keywords if k.arg}

        if name and len(name) >= 2 and name[-1] in INSTALL_WRITERS and name[-2] == "install":
            target = args[0] if args else kwargs.get("target")
            if target is not None and self.rooted(target):
                self.flag(node, f"install.{name[-1]} into REPO_ROOT")
        if name and len(name) >= 2 and (name[-2], name[-1]) in TOOL_ENTRY_POINTS:
            if any(self.rooted_anywhere(a) for a in args + list(kwargs.values())):
                self.flag(node, f"{name[-2]}.{name[-1]} on REPO_ROOT")
        if name and len(name) >= 2 and (name[-2], name[-1]) in REMOVERS:
            path = args[0] if args else kwargs.get("path")
            if path is not None and self.rooted(path):
                self.flag(node, f"{name[-2]}.{name[-1]} under REPO_ROOT")
        elif isinstance(func, ast.Attribute) and func.attr in RECEIVER_WRITERS \
                and (name is None or len(name) < 2 or name[-2] not in ("os", "shutil")):
            if self.rooted(func.value):
                self.flag(node, f".{func.attr}() under REPO_ROOT")
        if name == ("open",) or (name and name[-2:] in (("io", "open"),)):
            mode = args[1] if len(args) > 1 else kwargs.get("mode")
            if args and self.rooted(args[0]) and self._writes(mode):
                self.flag(node, "open() for writing under REPO_ROOT")
        elif isinstance(func, ast.Attribute) and func.attr == "open" and name != ("os", "open") \
                and self.rooted(func.value):
            mode = args[0] if args else kwargs.get("mode")
            if self._writes(mode):
                self.flag(node, ".open() for writing under REPO_ROOT")
        if name and len(name) >= 2 and (name[-2], name[-1]) in DEST_WRITERS:
            dest = args[1] if len(args) > 1 else kwargs.get("dst")
            if dest is not None and self.rooted(dest):
                self.flag(node, f"{name[-2]}.{name[-1]} into REPO_ROOT")
        elif isinstance(func, ast.Attribute) and func.attr in ("rename", "replace") \
                and (name is None or len(name) < 2 or name[-2] not in ("os", "shutil")):
            dest = args[0] if args else kwargs.get("target")
            if dest is not None and self.rooted(dest):
                self.flag(node, f".{func.attr}() into REPO_ROOT")
        self.generic_visit(node)

    @staticmethod
    def _writes(mode) -> bool:
        return isinstance(mode, ast.Constant) and isinstance(mode.value, str) \
            and any(c in mode.value for c in "wax")


def lint_source(source: str, module: str) -> list[LintFinding]:
    """Every writer pattern of 5.9 in one module's source, declared or not."""
    linter = _Linter(module, source)
    linter.visit(ast.parse(source, filename=module))
    return sorted(linter.findings, key=lambda f: (f.line, f.pattern))


def lint_tests(repo_root: Path, resources) -> list[LintFinding]:
    """The lint over `<repo_root>/tests/*.py`, minus findings inside a unit
    `resources` declares exclusive. A heuristic, not a proof: a write made by
    helper code outside `tests/`, or through a dynamically assembled path, is
    invisible to it (5.9)."""
    tests_dir = Path(repo_root) / "tests"
    findings = []
    for name in sorted(os.listdir(tests_dir), key=os.fsencode):
        path = tests_dir / name
        if not name.endswith(".py") or not path.is_file():
            continue
        for finding in lint_source(path.read_text(encoding="utf-8"), name):
            if finding.unit is None or not resources.is_exclusive(finding.unit):
                findings.append(finding)
    return findings

