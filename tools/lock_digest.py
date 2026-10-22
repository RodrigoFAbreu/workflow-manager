#!/usr/bin/env python3
"""The cache-key suffix of the nightly's tested-releases lock (#52).

    lock_digest.py LOCK COMMITTED

Prints the suffix the verification workflow appends to its release-cache key:
nothing when LOCK, parsed, equals COMMITTED (formatting is irrelevant), so the
nightly shares the key the `main` push run saved and saves nothing; otherwise
`-` and the first 16 hex digits of LOCK's canonical SHA-256, so a new release
saves one entry and the nightlies after it hit that entry.

Exit codes: 0 success; 2 usage or an unreadable lock
(docs/exit-codes.md, "Maintainer tools").
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def digest(lock_path: Path, committed_path: Path) -> str:
    """`""` when the two files hold the same JSON value, else the first 16 hex
    digits of the lock's canonical (sorted, compact) SHA-256."""
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    if lock == json.loads(Path(committed_path).read_text(encoding="utf-8")):
        return ""
    canonical = json.dumps(lock, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: lock_digest.py LOCK COMMITTED", file=sys.stderr)
        return 2
    try:
        found = digest(Path(args[0]), Path(args[1]))
    except (OSError, ValueError) as exc:
        print(f"lock_digest: {exc}", file=sys.stderr)
        return 2
    print(f"-{found}" if found else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
