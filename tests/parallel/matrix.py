"""The frozen-suite matrix, as data (plan section 5.5). Nothing here runs.

`FROZEN_MATRIX` names the 15 matrix host classes -- the ones whose
`setUpClass` runs every `CI_SUITES[version]` suite in one disposable
repository -- with the `(version, fixture)` each one exercises. `CI_SUITES`
is a view of `tests/support.py`'s own table, the single source of the pinned
counts.

Frozen discovery reads both inside its discovery subprocess, from the
checkout it is pointed at, so a scratch checkout can replace this module
with its own literal.
"""

from __future__ import annotations

from support import CI_SUITES

#: The disposable-repository shapes a matrix host class builds:
#: `build_conformance_repo`, `build_target_repo`, and `install.bootstrap`
#: into an empty repository.
FIXTURES = ("conformance", "target", "bootstrapped")

FROZEN_MATRIX = {
    "host:test_conformance_suite.py::TestConformanceFixture231": ("2.3.1", "conformance"),
    "host:test_conformance_suite.py::TestConformanceFixture240": ("2.4.0", "conformance"),
    "host:test_conformance_suite.py::TestConformanceFixture250": ("2.5.0", "conformance"),
    "host:test_conformance_suite.py::TestConformanceFixture251": ("2.5.1", "conformance"),
    "host:test_conformance_suite.py::TestConformanceFixture260": ("2.6.0", "conformance"),
    "host:test_conformance_suite.py::TestBootstrappedTarget231": ("2.3.1", "target"),
    "host:test_conformance_suite.py::TestBootstrappedTarget240": ("2.4.0", "target"),
    "host:test_conformance_suite.py::TestBootstrappedTarget250": ("2.5.0", "target"),
    "host:test_conformance_suite.py::TestBootstrappedTarget251": ("2.5.1", "target"),
    "host:test_conformance_suite.py::TestBootstrappedTarget260": ("2.6.0", "target"),
    "host:test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite231": ("2.3.1", "bootstrapped"),
    "host:test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite240": ("2.4.0", "bootstrapped"),
    "host:test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite250": ("2.5.0", "bootstrapped"),
    "host:test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite251": ("2.5.1", "bootstrapped"),
    "host:test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite260": ("2.6.0", "bootstrapped"),
}

__all__ = ["CI_SUITES", "FIXTURES", "FROZEN_MATRIX"]
