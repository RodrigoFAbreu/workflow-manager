"""Workflow Manager — distribution, bootstrap, and update tooling for the
reusable AI development Workflow.

`distribution/` holds one immutable, byte-verified copy of each migrated
Workflow release. This package reads those releases and installs them into
target repositories without ever touching repository-local work-item state.
"""

from .installation import CorruptInstallationError, Installation, is_managed
from .release import Release, ReleaseIntegrityError, available_versions, find_release

__all__ = [
    "CorruptInstallationError",
    "Installation",
    "Release",
    "ReleaseIntegrityError",
    "available_versions",
    "find_release",
    "is_managed",
]
