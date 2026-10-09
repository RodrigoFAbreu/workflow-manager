"""A write-observing audit hook (plan 3.6, "Evidence").

`install(protected)` records, in `VIOLATIONS`, every event of this process that
can write under one of the `protected` real paths: `open`/`os.open` with a
write-capable mode or flags, and `os.mkdir`, `rename`, `remove`, `rmdir`,
`chmod`, `symlink`, `link`, `truncate`, `utime`, `chown`, `chflags` (both ends
of a rename, link or symlink). A relative path resolves against the process's
cwd; a path given with a `dir_fd` against `/proc/self/fd/<n>` (CPython 3.12+
reports `shutil.rmtree`'s removals that way, with a bare entry name). An event
whose path cannot be resolved is recorded as `UNRESOLVED`, so the observation
never passes by failing to see. An audit hook sees this process only; it does
not see the Git subprocesses.
"""

from __future__ import annotations

import os
import sys

VIOLATIONS: list[str] = []

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
#: event -> positions of its path arguments, and of the dir_fd for each.
_PATH_EVENTS = {
    "os.mkdir": ((0,), (2,)),
    "os.remove": ((0,), (1,)),
    "os.rmdir": ((0,), (1,)),
    "os.chmod": ((0,), (2,)),
    "os.chown": ((0,), (3,)),
    "os.utime": ((0,), (3,)),
    "os.truncate": ((0,), ()),
    "os.chflags": ((0,), ()),
    "os.rename": ((0, 1), (2, 3)),
    "os.link": ((0, 1), (2, 3)),
    "os.symlink": ((1,), (2,)),
}


def _resolve(path, dir_fd) -> str | None:
    if isinstance(path, int):
        try:
            return os.readlink(f"/proc/self/fd/{path}")
        except OSError:
            return None
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, str):
        return None
    if os.path.isabs(path):
        return os.path.realpath(path)
    if dir_fd is not None and dir_fd != -1:
        try:
            base = os.readlink(f"/proc/self/fd/{dir_fd}")
        except OSError:
            return None
        return os.path.realpath(os.path.join(base, path))
    return os.path.realpath(os.path.join(os.getcwd(), path))


def _writes(event: str, args) -> bool:
    if event == "open":
        mode, flags = args[1], args[2]
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            return True
        return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)
    return True


def install(protected) -> None:
    roots = [os.path.realpath(p) for p in protected]

    def under(path: str) -> bool:
        return any(path == r or path.startswith(r + os.sep) for r in roots)

    def hook(event, args):
        if event == "open":
            positions, fds = (0,), ()
        elif event in _PATH_EVENTS:
            positions, fds = _PATH_EVENTS[event]
        else:
            return
        if not _writes(event, args):
            return
        for index, position in enumerate(positions):
            if position >= len(args):
                continue
            dir_fd = args[fds[index]] if index < len(fds) and fds[index] < len(args) else None
            resolved = _resolve(args[position], dir_fd)
            if resolved is None:
                VIOLATIONS.append(f"UNRESOLVED {event} {args[position]!r}")
            elif under(resolved):
                VIOLATIONS.append(f"{event} {resolved}")

    sys.addaudithook(hook)
