"""Shared helpers for the workflow-manager test suites. Stdlib only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

#: Importing payload modules must not leave `__pycache__` inside a cached
#: release tree -- it is meant to be byte-for-byte inspectable.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

PORTABILITY_EXCEPTIONS = json.loads(
    (REPO_ROOT / "tests" / "portability_exceptions.json").read_text()
)


def _pinned_versions() -> list[str]:
    from workflow_manager import source

    return source.load_pins().versions()


#: Every pinned version, oldest first (plan 7.1, `D-Tested-Releases`).
PINNED_VERSIONS = _pinned_versions()
#: The release the frozen matrix runs: the highest pinned version.
NEWEST_RELEASE = PINNED_VERSIONS[-1]
#: The release the `updated` fixture bootstraps before updating it to
#: `NEWEST_RELEASE`: the one below it, or None when only one is pinned.
UPGRADE_FROM = PINNED_VERSIONS[-2] if len(PINNED_VERSIONS) > 1 else None

_RELEASES: dict = {}


def release(version: str):
    """Pinned release `version`, as a verified private snapshot taken from the
    release cache (plan 5.4), memoized per version for this process. The
    snapshot is removed at interpreter exit."""
    if version not in _RELEASES:
        from workflow_manager import source

        pins = source.load_pins()
        cache = source.ReleaseCache(source.cache_root(), source.ReleaseSource.select(), pins)
        _RELEASES[version] = cache.resolve(version)
    return _RELEASES[version]


def next_version(version: str) -> str:
    """`version` with its patch component plus one: a synthetic release that
    is never lower than `version`."""
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def cli_env(**extra: str) -> dict[str, str]:
    """A from-scratch environment for a `workflow_manager` subprocess (plan 7.1).

    It always names the parent's resolved release cache in
    `WORKFLOW_MANAGER_RELEASE_CACHE`, so a test that moves `HOME` on purpose
    still reads the cache every other test reads, and it carries
    `WORKFLOW_MANAGER_RELEASE_SOURCE` through when that is set. Those are
    defaults: `extra` is applied last and overrides them.
    """
    from workflow_manager import source

    env = {
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path.home()),
        source.CACHE_ENV: str(source.cache_root()),
    }
    if os.environ.get(source.SOURCE_ENV):
        env[source.SOURCE_ENV] = os.environ[source.SOURCE_ENV]
    env.update(extra)
    return env


def run_suite(repo: Path, suite: str, timeout: int = 1800,
              classes=()) -> subprocess.CompletedProcess:
    """One frozen conformance suite, run the way the frozen CI runs it:
    from `scripts/`, with no PYTHONPATH help.

    `classes` names test classes of the suite to run instead of all of them;
    they are appended to argv, where the suite's own bare `unittest.main()`
    resolves them against `__main__` -- the same code path as a whole-suite
    run.

    `PYTHON_COLORS=0` pins Python 3.13+'s traceback colorizer off regardless
    of the invoking shell's own `FORCE_COLOR`/`NO_COLOR` -- `failing_tests`
    below parses captured output for plain `FAIL: `/`ERROR: ` line prefixes,
    which a colorized run wraps in ANSI escapes and silently stops matching
    (found empirically: a developer shell with `FORCE_COLOR` set reproduces
    it every time, even though the captured stream is a pipe, never a tty)."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("FORCE_COLOR", None)
    env["PYTHON_COLORS"] = "0"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return subprocess.run(
        [sys.executable, suite, *classes], cwd=str(repo / "scripts"),
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def failing_tests(output: str) -> set[str]:
    """`{ClassName.test_name}` for every FAIL/ERROR line in unittest output."""
    names = set()
    for line in output.splitlines():
        if line.startswith(("FAIL: ", "ERROR: ")):
            head = line.split(": ", 1)[1].split(" ", 1)[0]
            qualified = line.split("(", 1)[1].rstrip(")") if "(" in line else head
            # "__main__.Class.test" -> "Class.test"
            parts = qualified.split(".")
            names.add(".".join(parts[-2:]) if len(parts) >= 2 else qualified)
    return names


#: The frozen suites the upstream CI runs on every pull request, with the
#: exact test counts each release's own payload produces -- one inner dict
#: per pinned version. A published release is immutable, so every entry is a
#: frozen record and stays; only `NEWEST_RELEASE`'s is run, by the matrix
#: host classes, which assert these numbers so a silently-skipped test is a
#: failure, not a pass. `2.3.1` is frozen upstream content and its counts never
#: move; `2.4.0` is this repository's own first authored release (D-Authored-
#: Release-2) -- its counts are pinned to what that release's own overlay
#: payload actually produces, re-derived whenever the overlay changes.
CI_SUITES = {
    "2.3.1": {
        "workflow_fingerprint_test.py": 218,
        "workflow_state_test.py": 616,
        "workflow_test_harness_test.py": 19,
        "workflow_integration_test.py": 256,
        "workflow_acceptance_matrix_test.py": 146,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 79,
    },
    "2.4.0": {
        "workflow_fingerprint_test.py": 218,
        "workflow_state_test.py": 673,
        "workflow_test_harness_test.py": 19,
        "workflow_integration_test.py": 257,
        "workflow_acceptance_matrix_test.py": 146,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 79,
    },
    #: `2.5.0` is this repository's second authored release (the plan-
    #: amendment mechanism's own successor, D-Implementation-Review-Stages):
    #: its counts are pinned to what that release's own overlay payload
    #: actually produces, re-derived whenever the overlay changes.
    "2.5.0": {
        "workflow_fingerprint_test.py": 218,
        "workflow_state_test.py": 841,
        "workflow_test_harness_test.py": 19,
        "workflow_integration_test.py": 260,
        "workflow_acceptance_matrix_test.py": 146,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 79,
    },
    #: `2.5.1` is this repository's third authored release
    #: (`D-Checkpoint-Id-Anchor-Grammar-Widening`): a narrow overlay on top
    #: of the unmodified `2.5.0` base, replacing only `scripts/
    #: workflow_state.py`/`workflow_state_test.py` and four normative
    #: documents. Every suite's count is identical to `2.5.0`'s own except
    #: `workflow_state_test.py`, which gains the checkpoint-id-anchor-
    #: grammar-widening tests CP1 added; counts pinned to what that
    #: release's own overlay payload actually produces.
    "2.5.1": {
        "workflow_fingerprint_test.py": 218,
        "workflow_state_test.py": 853,
        "workflow_test_harness_test.py": 19,
        "workflow_integration_test.py": 260,
        "workflow_acceptance_matrix_test.py": 146,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 79,
    },
    #: `2.6.0` is this repository's fourth authored release
    #: (workflow-review-artifact-and-concurrency-hardening): an overlay on
    #: top of the unmodified `2.5.1` base, replacing both engine modules,
    #: every frozen suite except `workflow_test_harness_test.py`/
    #: `workflow_state_completion_obligations_test.py`, the review commands
    #: and the normative documents. Same suite set as `2.5.1`; counts pinned
    #: to what that release's own overlay payload actually produces.
    "2.6.0": {
        "workflow_fingerprint_test.py": 242,
        "workflow_state_test.py": 972,
        "workflow_test_harness_test.py": 19,
        "workflow_integration_test.py": 267,
        "workflow_acceptance_matrix_test.py": 291,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 105,
    },
}


def expected_portability_exceptions(workflow_version: str) -> dict:
    """`{suite: {test, ...}}` for the documented portability exceptions of one
    release, from `tests/portability_exceptions.json`'s per-version
    `by_version[workflow_version]["exceptions"]` list -- the one place both
    `tests/test_conformance_suite.py`'s `TestBootstrappedTarget*` and
    `tests/test_bootstrap_e2e.py`'s `TestBootstrappedRepositorySatisfiesThe
    FrozenSuite*` derive their expected-failure set from, so the two never
    drift apart on how a record maps to an expectation."""
    expected: dict = {}
    for record in PORTABILITY_EXCEPTIONS["by_version"][workflow_version]["exceptions"]:
        expected.setdefault(record["suite"], set()).add(record["test"])
    return expected
