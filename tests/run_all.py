#!/usr/bin/env python3
"""Run every workflow-manager suite. Stdlib only.

    python3 tests/run_all.py           # everything
    python3 tests/run_all.py --fast    # skip the frozen-suite conformance run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

FAST_SUITES = (
    "test_migration_inventory.py",
    "test_payload_bytes.py",
    "test_templates.py",
    "test_no_live_state_imported.py",
    "test_internal_references.py",
    "test_bootstrap.py",
    "test_disposable_repo_fixtures.py",
    "test_amendment_update_path.py",
)
SLOW_SUITES = (
    "test_conformance_suite.py",
    "test_bootstrap_e2e.py",
    "test_implementation_review_two_stage_disposable_repo.py",
    "test_workflow_2_6_0_hardening_disposable_repo.py",
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true",
                        help="skip the suites that run the frozen conformance matrix")
    args = parser.parse_args(argv)

    suites = list(FAST_SUITES) + ([] if args.fast else list(SLOW_SUITES))
    suites = [s for s in suites if (TESTS_DIR / s).exists()]

    failures = []
    for suite in suites:
        started = time.monotonic()
        proc = subprocess.run([sys.executable, suite], cwd=str(TESTS_DIR),
                              capture_output=True, text=True)
        elapsed = time.monotonic() - started
        tail = (proc.stdout + proc.stderr).strip().splitlines()
        summary = tail[-1] if tail else "(no output)"
        status = "ok  " if proc.returncode == 0 else "FAIL"
        print(f"{status} {suite:<36} {elapsed:6.1f}s  {summary}")
        if proc.returncode != 0:
            failures.append((suite, proc.stdout + proc.stderr))

    for suite, output in failures:
        print(f"\n{'=' * 70}\n{suite}\n{'=' * 70}\n{output[-6000:]}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
