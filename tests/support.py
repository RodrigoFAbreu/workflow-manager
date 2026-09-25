"""Shared helpers for the workflow-manager test suites. Stdlib only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

#: Importing payload modules must not leave `__pycache__` inside the
#: canonical distribution -- it is meant to be byte-for-byte inspectable.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

CLASSIFICATION = json.loads((REPO_ROOT / "migration" / "classification.json").read_text())
PORTABILITY_EXCEPTIONS = json.loads(
    (REPO_ROOT / "migration" / "portability_exceptions.json").read_text()
)

#: Set WORKFLOW_MANAGER_UPSTREAM to point the upstream-comparison tests at a
#: different clone. They skip when it is absent -- the migrated distribution
#: must be verifiable from its own manifest without the upstream repository.
UPSTREAM = Path(
    os.environ.get("WORKFLOW_MANAGER_UPSTREAM", str(Path.home() / "Workspace" / "repflow-android"))
)

FROZEN_COMMIT = CLASSIFICATION["upstream"]["commit"]
FROZEN_TAG = CLASSIFICATION["upstream"]["tag"]


def upstream_available() -> bool:
    if not (UPSTREAM / ".git").exists():
        return False
    proc = subprocess.run(
        ["git", "-C", str(UPSTREAM), "cat-file", "-e", f"{FROZEN_COMMIT}^{{commit}}"],
        capture_output=True,
    )
    return proc.returncode == 0


def frozen_paths() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(UPSTREAM), "ls-tree", "-r", "--name-only", FROZEN_COMMIT],
        check=True, capture_output=True, text=True,
    ).stdout
    return out.splitlines()


def frozen_bytes(path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(UPSTREAM), "show", f"{FROZEN_COMMIT}:{path}"],
        check=True, capture_output=True,
    ).stdout


def run_suite(repo: Path, suite: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    """One frozen conformance suite, run the way the frozen CI runs it:
    from `scripts/`, with no PYTHONPATH help.

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
        [sys.executable, suite], cwd=str(repo / "scripts"),
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
#: per `distribution/workflow/<version>/`. `tests/test_conformance_suite.py`
#: and `tests/test_bootstrap_e2e.py` assert these numbers so a silently-
#: skipped test is a failure, not a pass, for whichever release a given test
#: class exercises. `2.3.1` is frozen upstream content and its counts never
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
        "workflow_state_test.py": 959,
        "workflow_test_harness_test.py": 19,
        "workflow_integration_test.py": 267,
        "workflow_acceptance_matrix_test.py": 280,
        "workflow_state_completion_obligations_test.py": 106,
        "workflow_fingerprint_generalization_test.py": 103,
    },
}


def expected_portability_exceptions(workflow_version: str) -> dict:
    """`{suite: {test, ...}}` for the documented portability exceptions of one
    release, from `migration/portability_exceptions.json`'s per-version
    `by_version[workflow_version]["exceptions"]` list -- the one place both
    `tests/test_conformance_suite.py`'s `TestBootstrappedTarget*` and
    `tests/test_bootstrap_e2e.py`'s `TestBootstrappedRepositorySatisfiesThe
    FrozenSuite*` derive their expected-failure set from, so the two never
    drift apart on how a record maps to an expectation."""
    expected: dict = {}
    for record in PORTABILITY_EXCEPTIONS["by_version"][workflow_version]["exceptions"]:
        expected.setdefault(record["suite"], set()).add(record["test"])
    return expected
