"""The frozen-suite matrix, as data (plan section 5.5). Nothing here runs.

`FROZEN_MATRIX` names the matrix host classes -- the ones whose `setUpClass`
runs every `CI_SUITES[version]` suite in one disposable repository -- with
the `(version, fixture)` each one exercises: one class per fixture, all for
`NEWEST_RELEASE` (plan 7.1, `D-Tested-Releases`). `CI_SUITES` is a view of
`tests/support.py`'s own table, the single source of the pinned counts.

Frozen discovery reads both inside its discovery subprocess, from the
checkout it is pointed at, so a scratch checkout can replace this module
with its own literal.
"""

from __future__ import annotations

from support import CI_SUITES, NEWEST_RELEASE, UPGRADE_FROM

#: The disposable-repository shapes a matrix host class builds:
#: `build_conformance_repo`, `build_target_repo`, `install.bootstrap` into an
#: empty repository, and that bootstrap of `UPGRADE_FROM` updated to the
#: release under test.
FIXTURES = ("conformance", "target", "bootstrapped", "updated")

FROZEN_MATRIX = {
    "host:test_conformance_suite.py::TestConformanceFixture": (NEWEST_RELEASE, "conformance"),
    "host:test_conformance_suite.py::TestBootstrappedTarget": (NEWEST_RELEASE, "target"),
    "host:test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite":
        (NEWEST_RELEASE, "bootstrapped"),
}
#: With one pinned release there is nothing to update from, so the `updated`
#: class is omitted and nothing else changes.
if UPGRADE_FROM is not None:
    FROZEN_MATRIX["host:test_update_path.py::TestUpdatedRepositorySatisfiesTheFrozenSuite"] = (
        NEWEST_RELEASE, "updated")

__all__ = ["CI_SUITES", "FIXTURES", "FROZEN_MATRIX"]
