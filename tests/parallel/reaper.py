"""The per-chunk leak check (test-cleanup plan 5.4, `D-Orphan-Check`).

    python3 -I -S -B reaper.py --report FILE --chunk-id ID [--pass-fd FD] -- ARGV...

Stdlib-only, and run outside the `parallel` package (`-I -S`), so it imports
nothing from it. It makes itself a child subreaper, starts `ARGV` (the chunk)
as its only child with the environment and standard streams unchanged, and
passes `--pass-fd` (the run lock) on to it.

1. **Recording.** Until the chunk has exited, every 10 ms it lists its
   children (`/proc/self/task/*/children`) and records every new pid other
   than the chunk's, then drains exited children one at a time: a
   `waitid(P_ALL, WNOWAIT)` names one without reaping it, its entry is
   recorded or completed, and only then does `waitpid` reap it. Every pid a
   wait returns, other than the chunk's, is an orphan, listed or not. An
   entry's label is its command line, or `[<comm>]` when that reads empty (a
   process already exiting, as Git's detached maintenance is when it is
   adopted), or `[unknown]`.
2. **Termination.** Every live descendant of the chunk is in this process's
   subtree, so `ECHILD` proves nothing is left. After the chunk exits it
   keeps draining for a grace period of at most 5 s, ending at once on
   `ECHILD`, then kills every child by pid and drains, in a loop until
   `ECHILD`.
3. **Report and exit.** It writes the report atomically, then exits with the
   chunk's status: an exit code as itself, a signal death by re-raising the
   signal (`os._exit(128 + n)` if it survives that).
4. **Its own faults** exit `125` with no report, after killing the chunk and
   running the kill loop as a best effort.
5. **Unsupported hosts** (no `prctl`, a failing `prctl`, or no `children`
   file) run the chunk unchanged and report `"supported": false` with the
   reason. The runner decides what that means.

`--force-unsupported` and `--platform` are test seams (the runner's
`isolation.REAPER_TEST_ARGS`); the runner itself never passes them.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import resource
import signal
import subprocess
import sys
import time
import traceback

SCHEMA_VERSION = 1
PR_SET_CHILD_SUBREAPER = 36
POLL_SECONDS = 0.01
GRACE_SECONDS = 5.0
FAULT_EXIT = 125
UNSUPPORTED_REASONS = ("no-prctl", "prctl-failed", "no-children-file")


def _prctl_subreaper(on: bool) -> bool:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl  # AttributeError where there is none
    prctl.restype = ctypes.c_int
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                      ctypes.c_ulong]
    return prctl(PR_SET_CHILD_SUBREAPER, 1 if on else 0, 0, 0, 0) == 0


def become_subreaper(forced: str | None) -> str | None:
    """Make this process a child subreaper; `None`, or why the check is
    unavailable here. It never runs the check with an empty listing."""
    if forced in ("no-prctl", "prctl-failed"):
        return forced
    try:
        if not _prctl_subreaper(True):
            return "prctl-failed"
    except (OSError, AttributeError):
        return "no-prctl"
    if forced == "no-children-file" or \
            not os.path.exists(f"/proc/self/task/{os.getpid()}/children"):
        try:
            _prctl_subreaper(False)
        except (OSError, AttributeError):
            pass
        return "no-children-file"
    return None


def children() -> set[int]:
    pids: set[int] = set()
    for task in os.listdir("/proc/self/task"):
        try:
            with open(f"/proc/self/task/{task}/children", encoding="ascii") as handle:
                pids.update(int(p) for p in handle.read().split())
        except FileNotFoundError:
            continue
    return pids


def label(pid: int) -> tuple[str, bool]:
    """`(label, from the command line)`: `/proc/<pid>/cmdline` joined with
    spaces, else `[<comm>]`, else `[unknown]`."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            raw = handle.read()
    except OSError:
        raw = b""
    text = " ".join(p.decode("utf-8", "replace") for p in raw.split(b"\0") if p)
    if text:
        return text, True
    try:
        with open(f"/proc/{pid}/comm", "rb") as handle:
            comm = handle.read().decode("utf-8", "replace").strip()
    except OSError:
        comm = ""
    return f"[{comm or 'unknown'}]", False


class Reaper:
    """Records and reaps everything re-parented to this process while one
    chunk (`chunk_pid`, its only direct child) runs."""

    def __init__(self, chunk_pid: int):
        self.chunk_pid = chunk_pid
        self.chunk_status: int | None = None
        #: pid -> `[label, from the command line]`, for listed, unreaped orphans
        self.live: dict[int, list] = {}
        self.killed: set[int] = set()
        self.orphans: list[dict] = []

    def list_children(self) -> set[int]:
        pids = children()
        for pid in pids:
            if pid != self.chunk_pid and pid not in self.live:
                self.live[pid] = list(label(pid))
        return pids

    def drain(self) -> bool:
        """Reap every exited child, recording each orphan first; `True` on
        `ECHILD` (nothing is left), `False` when live children remain."""
        while True:
            try:
                info = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            except ChildProcessError:
                return True
            if info is None or info.si_pid == 0:
                return False
            pid = info.si_pid
            if pid == self.chunk_pid:
                _, status = os.waitpid(pid, 0)
                self.chunk_status = os.waitstatus_to_exitcode(status)
                continue
            entry = self.live.pop(pid, None)
            if entry is None or not entry[1]:
                # Never listed, or listed with an empty command line: label it
                # now, while it is still an unreaped zombie with a `comm`.
                fresh = label(pid)
                if entry is None or fresh[1] or fresh[0] != "[unknown]":
                    entry = list(fresh)
            os.waitpid(pid, 0)
            self.orphans.append({"pid": pid, "cmdline": entry[0],
                                 "fate": "killed" if pid in self.killed else "exited"})
            self.killed.discard(pid)

    def kill_until_echild(self) -> None:
        """Kill every child by pid and drain, until `ECHILD` -- never a single
        pass: an orphan forking just before its kill hands its child to the
        next pass."""
        while True:
            for pid in self.list_children():
                if pid == self.chunk_pid and self.chunk_status is not None:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    continue
                if pid != self.chunk_pid:
                    self.killed.add(pid)
            if self.drain():
                return
            time.sleep(POLL_SECONDS)

    def supervise(self) -> None:
        while self.chunk_status is None:
            self.list_children()
            if self.drain() or self.chunk_status is not None:
                break
            time.sleep(POLL_SECONDS)
        deadline = time.monotonic() + GRACE_SECONDS
        while True:
            self.list_children()
            if self.drain():
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(POLL_SECONDS)
        self.kill_until_echild()


def write_report(path: str, doc: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def exit_like(status: int) -> None:
    """Exit with the chunk's status: an exit code as itself, a death by signal
    `n` by re-raising `n`, so the runner classifies the wrapper exactly as it
    would have classified the chunk."""
    sys.stdout.flush()
    sys.stderr.flush()
    if status >= 0:
        os._exit(status)
    signum = -status
    try:
        signal.signal(signum, signal.SIG_DFL)
    except (OSError, ValueError, RuntimeError):
        pass  # SIGKILL and SIGSTOP cannot be changed, nor blocked
    try:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, [signum])
        soft_hard = resource.getrlimit(resource.RLIMIT_CORE)
        resource.setrlimit(resource.RLIMIT_CORE, (0, soft_hard[1]))
    except (OSError, ValueError):
        pass
    os.kill(os.getpid(), signum)
    os._exit(128 + signum)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="reaper.py")
    parser.add_argument("--report", required=True)
    parser.add_argument("--chunk-id", required=True)
    parser.add_argument("--pass-fd", type=int, action="append", default=[])
    parser.add_argument("--force-unsupported", choices=UNSUPPORTED_REASONS)
    parser.add_argument("--platform", default=sys.platform)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("no chunk command after --")
    return args


def main(argv: list[str]) -> None:
    args = parse_args(argv)
    reaper = None
    try:
        for fd in args.pass_fd:
            os.fstat(fd)  # a closed fd is the wrapper's own fault
        reason = become_subreaper(args.force_unsupported)
        proc = subprocess.Popen(args.command, pass_fds=tuple(args.pass_fd))
        reaper = Reaper(proc.pid)
        if reason is None:
            reaper.supervise()
        else:
            _, status = os.waitpid(proc.pid, 0)
            reaper.chunk_status = os.waitstatus_to_exitcode(status)
        proc.returncode = reaper.chunk_status  # reaped here; never by `Popen`
        write_report(args.report, {
            "schema_version": SCHEMA_VERSION, "chunk_id": args.chunk_id,
            "platform": args.platform, "supported": reason is None,
            "unsupported_reason": reason, "chunk_status": reaper.chunk_status,
            "orphans": reaper.orphans})
    except BaseException:  # noqa: BLE001 -- never a report it cannot stand behind
        traceback.print_exc()
        try:
            if reaper is not None:
                reaper.kill_until_echild()
        except BaseException:  # noqa: BLE001 -- what is left goes to the next subreaper up
            traceback.print_exc()
        sys.stderr.flush()
        os._exit(FAULT_EXIT)
    exit_like(reaper.chunk_status)


if __name__ == "__main__":
    main(sys.argv[1:])
