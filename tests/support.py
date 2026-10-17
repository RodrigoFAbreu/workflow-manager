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


import tested_releases  # noqa: E402  (stdlib + workflow_manager; needs `src/` on the path)

from workflow_manager import source as _source  # noqa: E402

#: Every pinned version, oldest first (plan 7.1, `D-Tested-Releases`): the pins
#: alone, which is what the compatibility tests mean by "pinned".
PINNED_VERSIONS = _source.load_pins().versions()
#: The lock file's entries (`tests/tested_releases.json`, or the nightly's
#: override): releases published after the last pin (plan 3.5, `D-Lock`).
LOCK = tested_releases.load_lock()
#: The tested set, oldest first: the pins plus the lock.
TESTED_VERSIONS = tested_releases.tested_versions(lock=LOCK)
#: The release the frozen matrix runs: the highest tested version.
NEWEST_RELEASE = TESTED_VERSIONS[-1]
#: The release the `updated` fixture bootstraps before updating it to
#: `NEWEST_RELEASE`: the one below it, or None when only one is tested.
UPGRADE_FROM = TESTED_VERSIONS[-2] if len(TESTED_VERSIONS) > 1 else None
#: The newest pin and the one below it: what a suite that means the pins alone
#: (`pinned_env`) runs against, whatever the lock names. Equal to
#: `NEWEST_RELEASE`/`UPGRADE_FROM` while the lock is empty.
PINNED_NEWEST = PINNED_VERSIONS[-1]
PINNED_UPGRADE_FROM = PINNED_VERSIONS[-2] if len(PINNED_VERSIONS) > 1 else None

_RELEASES: dict = {}


def release(version: str):
    """Pinned release `version`, as a verified private snapshot taken from the
    release cache (plan 5.4), memoized per version for this process. The
    snapshot is removed at interpreter exit."""
    if version not in _RELEASES:
        from workflow_manager import source

        pins = tested_releases.tested_pins(source.load_pins(), LOCK)
        cache = source.ReleaseCache(source.cache_root(), source.ReleaseSource.select(), pins)
        _RELEASES[version] = cache.resolve(version)
    return _RELEASES[version]


def next_version(version: str) -> str:
    """`version` with its patch component plus one: a synthetic release that
    is never lower than `version`."""
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


# The host's own Git config (a system-wide Git LFS filter, say) must not leak
# into a test: it changes what `doctor` can inspect. Every suite imports this
# module, so the test process and its children read no system or global
# config; `/dev/null` is the empty file. Commit identity is the repository's
# own (`fixture.init_git_repo`) or a `-c` of the test's.
HERMETIC_GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
os.environ.update(HERMETIC_GIT_ENV)

#: No test discovers a release over the network (plan 3.7): a suite that needs
#: discovery sets this to "0" with a mirror directory or a loopback server and a
#: private release cache of its own. The runner exports the same value.
os.environ.setdefault("WORKFLOW_MANAGER_PINNED_ONLY", "1")


def cli_env(**extra: str) -> dict[str, str]:
    """A from-scratch environment for a `workflow_manager` subprocess (plan 7.1).

    It always names the parent's resolved release cache in
    `WORKFLOW_MANAGER_RELEASE_CACHE`, so a test that moves `HOME` on purpose
    still reads the cache every other test reads, and it carries
    `WORKFLOW_MANAGER_RELEASE_SOURCE` through when that is set. It sets the
    lock override to this process's own, empty when there is none, so a child
    that imports this module tests the same set, never an inherited one.
    Those are defaults: `extra` is applied last and overrides them.
    """
    env = pinned_env()
    if LOCK:
        # A lock-only release is not pinned: reach it through the hermetic
        # mirror and a process-private cache, as `mirror_env` does (plan 3.5).
        env.update({_source.SOURCE_ENV: str(mirror_dir()), _source.PINNED_ONLY_ENV: "0",
                    _source.CACHE_ENV: str(_lock_cache())})
    env.update(extra)
    return env


def pinned_env(**extra: str) -> dict[str, str]:
    """`cli_env` as it is while the lock is empty, whatever the lock names:
    pinned-only, on the parent's resolved release cache. For a suite that
    means the pins alone -- the pinned-only Manager's messages and exit codes,
    against `PINNED_NEWEST` -- never one that reaches a lock-only release.
    `extra` is applied last and overrides it."""
    from workflow_manager import source

    env = {
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path.home()),
        source.CACHE_ENV: str(source.cache_root()),
        source.PINNED_ONLY_ENV: "1",
        tested_releases.OVERRIDE_ENV: os.environ.get(tested_releases.OVERRIDE_ENV, ""),
        **HERMETIC_GIT_ENV,
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
    #: `2.7.0` is the first release published by the `workflow` repository
    #: (W1, Orchestration Protocol v1, built and released there, pinned
    #: here). It adds an eighth suite, `workflow_protocol_test.py`, which
    #: its `workflow-conformance.yml` template runs; counts pinned to what
    #: the published package actually produces.
    "2.7.0": {
        "workflow_fingerprint_test.py": 256,
        "workflow_state_test.py": 1011,
        "workflow_test_harness_test.py": 22,
        "workflow_integration_test.py": 267,
        "workflow_acceptance_matrix_test.py": 291,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 105,
        "workflow_protocol_test.py": 217,
    },
    #: `2.8.0` is the second release published by the `workflow` repository
    #: (W2, the declarative gate policy and pull-request reopening, on
    #: Orchestration Protocol 1.1). It adds a ninth suite,
    #: `workflow_gate_policy_test.py`, which its `workflow-conformance.yml`
    #: template runs; counts pinned to what the published package actually
    #: produces.
    "2.8.0": {
        "workflow_fingerprint_test.py": 257,
        "workflow_state_test.py": 1011,
        "workflow_test_harness_test.py": 22,
        "workflow_integration_test.py": 275,
        "workflow_acceptance_matrix_test.py": 291,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 105,
        "workflow_protocol_test.py": 298,
        "workflow_gate_policy_test.py": 285,
    },
    #: `2.9.0` is the third release published by the `workflow` repository
    #: (W3, legacy-item retirement, the 2.2 default for new installations and
    #: the `v2.6.0-003` fix, on Orchestration Protocol 1.2). Same nine suites;
    #: counts pinned to what the published package actually produces.
    "2.9.0": {
        "workflow_fingerprint_test.py": 257,
        "workflow_state_test.py": 1070,
        "workflow_test_harness_test.py": 22,
        "workflow_integration_test.py": 276,
        "workflow_acceptance_matrix_test.py": 291,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 105,
        "workflow_protocol_test.py": 314,
        "workflow_gate_policy_test.py": 292,
    },
    #: `2.9.1` is a fix release (W4, workflow#13: review-stage REVISE writes
    #: committed alone, APPROVE writes left uncommitted). Same nine suites;
    #: counts pinned to what the published package actually produces.
    "2.9.1": {
        "workflow_fingerprint_test.py": 257,
        "workflow_state_test.py": 1088,
        "workflow_test_harness_test.py": 22,
        "workflow_integration_test.py": 279,
        "workflow_acceptance_matrix_test.py": 331,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 105,
        "workflow_protocol_test.py": 314,
        "workflow_gate_policy_test.py": 292,
    },
    #: `2.9.2` is a fix release (workflow#19, #20: a generation record is the
    #: last commit, and the Workflow-* trailers are the final paragraph alone).
    #: Same nine suites; counts pinned to what the published package produces.
    "2.9.2": {
        "workflow_fingerprint_test.py": 257,
        "workflow_state_test.py": 1090,
        "workflow_test_harness_test.py": 22,
        "workflow_integration_test.py": 289,
        "workflow_acceptance_matrix_test.py": 353,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 105,
        "workflow_protocol_test.py": 314,
        "workflow_gate_policy_test.py": 292,
    },
    #: `2.10.0` refuses new work items under a "2.1" default and runs its CI
    #: suites in parallel inside one job. Same nine suites; counts pinned to
    #: what the published package produces.
    "2.10.0": {
        "workflow_fingerprint_test.py": 257,
        "workflow_state_test.py": 1102,
        "workflow_test_harness_test.py": 25,
        "workflow_integration_test.py": 292,
        "workflow_acceptance_matrix_test.py": 381,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 106,
        "workflow_protocol_test.py": 320,
        "workflow_gate_policy_test.py": 292,
    },
    #: `2.11.0` checks a plan revision's checkpoint anchors before any plan review.
    #: Same nine suites; counts pinned to what the published package produces.
    "2.11.0": {
        "workflow_fingerprint_test.py": 257,
        "workflow_state_test.py": 1112,
        "workflow_test_harness_test.py": 27,
        "workflow_integration_test.py": 300,
        "workflow_acceptance_matrix_test.py": 415,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 112,
        "workflow_protocol_test.py": 320,
        "workflow_gate_policy_test.py": 292,
    },
    #: `2.12.0` converges review rounds (`CHANGES_SINCE_REVIEW.md`, verdict shape checks,
    #: Orchestration Protocol 1.4). Same nine suites; counts pinned to what the published
    #: package produces.
    "2.12.0": {
        "workflow_fingerprint_test.py": 269,
        "workflow_state_test.py": 1115,
        "workflow_test_harness_test.py": 27,
        "workflow_integration_test.py": 300,
        "workflow_acceptance_matrix_test.py": 415,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 125,
        "workflow_protocol_test.py": 330,
        "workflow_gate_policy_test.py": 292,
    },
}


def _lock_conformance(version: str) -> tuple[dict, tuple]:
    """Suite counts and exceptions of a lock-only release: the manifest's
    `conformance` block when the primed cache holds the manifest, else the
    lock entry's own (plan 3.5)."""
    pins = tested_releases.tested_pins(_source.load_pins(), LOCK)
    cache = _source.ReleaseCache(_source.cache_root(), None, pins)
    return tested_releases.lock_conformance(LOCK[version], cache.cached_manifest(version))


for _version in LOCK:
    CI_SUITES[_version] = _lock_conformance(_version)[0]


_MIRROR: list = []


def mirror_dir() -> Path:
    """A release-source directory holding every tested release's three assets,
    copied from the primed cache (memoized per process, removed at exit): the
    no-network source a CLI-driven test uses to install a lock-only release
    (plan 3.5). A test using it passes its own private release cache too."""
    if not _MIRROR:
        import atexit
        import shutil
        import tempfile

        from workflow_manager.package import SUMS_NAME, archive_name, manifest_asset_name

        root = Path(tempfile.mkdtemp(prefix="wm-mirror-"))
        atexit.register(shutil.rmtree, root, True)
        cache = _source.cache_root()
        for version in TESTED_VERSIONS:
            (root / version).mkdir()
            for name in (SUMS_NAME, archive_name(version), manifest_asset_name(version)):
                shutil.copy2(cache / version / name, root / version / name)
        _MIRROR.append(root)
    return _MIRROR[0]


_LOCK_CACHE: list = []


def _lock_cache() -> Path:
    """The private release cache `cli_env` names while the lock is non-empty
    (memoized per process, removed at exit)."""
    if not _LOCK_CACHE:
        import atexit
        import shutil
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="wm-lock-cache-"))
        atexit.register(shutil.rmtree, root, True)
        _LOCK_CACHE.append(root)
    return _LOCK_CACHE[0]


def mirror_env(private_cache: Path, **extra: str) -> dict[str, str]:
    """`cli_env` with discovery on, the mirror directory as the source and a
    private release cache (never the primed one, plan 3.7)."""
    return cli_env(**{_source.SOURCE_ENV: str(mirror_dir()), _source.PINNED_ONLY_ENV: "0",
                      _source.CACHE_ENV: str(private_cache)}, **extra)


def expected_source_record(version: str) -> dict:
    """The installation record's `source` for `version`: the pin's for a pinned
    version (identity when the lock is empty), the discovered record from the
    mirror directory for a lock-only one."""
    pins = _source.load_pins()
    if version in pins.releases:
        return pins.source_record(version)
    pin = LOCK[version].pin()
    return {"kind": "package", "repository": pins.repository, "archive": pin.archive,
            "sha256": pin.sha256, "trust": "discovered", "from": "dir:" + str(mirror_dir())}


def expected_portability_exceptions(workflow_version: str) -> dict:
    """`{suite: {test, ...}}` for the documented portability exceptions of one
    release, from `tests/portability_exceptions.json`'s per-version
    `by_version[workflow_version]["exceptions"]` list -- the one place both
    `tests/test_conformance_suite.py`'s `TestBootstrappedTarget*` and
    `tests/test_bootstrap_e2e.py`'s `TestBootstrappedRepositorySatisfiesThe
    FrozenSuite*` derive their expected-failure set from, so the two never
    drift apart on how a record maps to an expectation."""
    expected: dict = {}
    if workflow_version in LOCK:
        records = _lock_conformance(workflow_version)[1]
    else:
        records = PORTABILITY_EXCEPTIONS["by_version"][workflow_version]["exceptions"]
    for record in records:
        expected.setdefault(record["suite"], set()).add(record["test"])
    return expected
