"""Tree identity and the repository snapshot (plan sections 5.6 and 5.9).

`tree_digest(repo_root)` is sha256 over `HEAD` plus the byte content of every
tracked-and-modified and untracked-unignored path, so a dirty working tree
has its own identity; a clean checkout's digest depends on `HEAD` alone.

`snapshot(repo_root)` captures the same inputs plus every *ignored* file
under the guarded trees and `tests/` (`__pycache__` included), and
`compare(before, after)` lists every path whose state differs -- the
persistent-change half of the repository-integrity guard.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .resources import GUARDED_TREES

#: Trees whose ignored files the snapshot also records.
SNAPSHOT_IGNORED_TREES = GUARDED_TREES + ("tests/",)

#: How a path the snapshot did not list is described in a comparison: clean
#: (tracked and unmodified) or absent.
UNLISTED = "unlisted"


def _git(repo_root: Path, *args: str) -> bytes:
    env = dict(os.environ)
    # `git status` may otherwise refresh and rewrite the index; a digest
    # must never write anything.
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(["git", "-C", str(repo_root), *args], check=True,
                          capture_output=True, env=env).stdout


def _head(repo_root: Path) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    proc = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--verify", "-q", "HEAD"],
                          capture_output=True, text=True, env=env)
    return proc.stdout.strip()  # empty on an unborn branch


def head_commit(repo_root: Path) -> str:
    """`HEAD`'s commit id, or `""` on an unborn branch; writes nothing."""
    return _head(repo_root)


def describe(path: Path) -> str:
    """Content-level description of one path: kind, executable bit and the
    sha256 of its bytes (or of its link target)."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "absent"
    if stat.S_ISLNK(st.st_mode):
        return "link:" + hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    if stat.S_ISDIR(st.st_mode):
        return "dir"
    if stat.S_ISREG(st.st_mode):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        executable = "x" if st.st_mode & 0o100 else "-"
        return f"file:{executable}:{digest.hexdigest()}"
    return f"other:{stat.S_IFMT(st.st_mode):o}"


def _status_paths(repo_root: Path) -> list[str]:
    raw = _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    tokens = raw.split(b"\0")
    paths = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        code, path = token[:2], token[3:]
        paths.append(os.fsdecode(path))
        if b"R" in code or b"C" in code:
            paths.append(os.fsdecode(tokens[i]))  # the rename/copy source
            i += 1
    return sorted(set(paths))


def _ignored_paths(repo_root: Path, trees) -> list[str]:
    raw = _git(repo_root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard",
               "--", *trees)
    return sorted({os.fsdecode(p) for p in raw.split(b"\0") if p})


@dataclass(frozen=True)
class Snapshot:
    head: str
    status: dict[str, str] = field(default_factory=dict)
    ignored: dict[str, str] = field(default_factory=dict)

    @property
    def tree_digest(self) -> str:
        return _digest(self.head, self.status)


def _digest(head: str, status: dict[str, str]) -> str:
    digest = hashlib.sha256()
    digest.update(b"HEAD\0" + head.encode() + b"\n")
    for path in sorted(status, key=os.fsencode):
        digest.update(os.fsencode(path) + b"\0" + status[path].encode() + b"\n")
    return digest.hexdigest()


def _status_entries(repo_root: Path) -> dict[str, str]:
    root = Path(repo_root)
    return {p: describe(root / p) for p in _status_paths(root)}


def tree_digest(repo_root: Path) -> str:
    return _digest(_head(repo_root), _status_entries(repo_root))


def snapshot(repo_root: Path, ignored_trees=SNAPSHOT_IGNORED_TREES) -> Snapshot:
    root = Path(repo_root)
    return Snapshot(
        head=_head(root),
        status=_status_entries(root),
        ignored={p: describe(root / p) for p in _ignored_paths(root, ignored_trees)},
    )


@dataclass(frozen=True)
class Difference:
    path: str
    before: str
    after: str


def compare(before: Snapshot, after: Snapshot) -> list[Difference]:
    """Every path whose recorded state differs, sorted; `HEAD` movement is
    reported as the pseudo-path `HEAD`. Empty means no persistent change."""
    diffs = []
    if before.head != after.head:
        diffs.append(Difference("HEAD", before.head or "unborn", after.head or "unborn"))
    old = {**before.status, **before.ignored}
    new = {**after.status, **after.ignored}
    for path in sorted(set(old) | set(new), key=os.fsencode):
        a, b = old.get(path, UNLISTED), new.get(path, UNLISTED)
        if a != b:
            diffs.append(Difference(path, a, b))
    return diffs
