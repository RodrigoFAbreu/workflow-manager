"""Workflow Manager — distribution, bootstrap, and update tooling for the
reusable AI development Workflow.

Workflow releases are published as packages. `published_releases.json` pins
each published version's digests, a local cache holds the verified packages,
and this package installs a resolved release into target repositories without
ever touching repository-local work-item state.
"""

import sys

# Run from a checkout that is itself the target of a read-only command, the
# Manager must not write bytecode into it (P1). Set before any submodule loads.
sys.dont_write_bytecode = True

from .installation import CorruptInstallationError, Installation, is_managed
from .release import Release, ReleaseIntegrityError

__all__ = [
    "CorruptInstallationError",
    "Installation",
    "Release",
    "ReleaseIntegrityError",
    "is_managed",
]
