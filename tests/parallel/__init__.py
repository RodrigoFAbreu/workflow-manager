"""Deterministic inventory, planning and execution of this repository's own
verification suite (`tests/`). Stdlib only.

Nothing here is Workflow state: no module under `scripts/` or in a
Workflow release reads it, and no timing data ever decides whether a test
runs. Every entry point takes `repo_root` as an argument -- nothing in this
package reads a module-level repository root.
"""

from __future__ import annotations

import json


def canonical_json(obj) -> str:
    """Sorted keys, 2-space indent, trailing newline, no NaN/Infinity -- the
    one serialization every file this package writes uses, so equal content
    is always equal bytes."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False) + "\n"


def strict_json_loads(text: str):
    """`json.loads` that refuses duplicate object keys instead of silently
    keeping the last one. Nesting too deep to parse is a `ValueError` too, so
    every caller's corrupt-file path covers it."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate key {key!r}")
            out[key] = value
        return out
    try:
        return json.loads(text, object_pairs_hook=pairs)
    except RecursionError as exc:
        raise ValueError("JSON nested too deeply to parse") from exc
