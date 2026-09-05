"""Workflow Manager — distribution tooling for the reusable AI development
Workflow.

`distribution/` holds one immutable, byte-verified copy of each migrated
Workflow release. This package reads those releases and builds disposable
repositories from them.
"""

from .release import Release, find_release

__all__ = ["Release", "find_release"]
