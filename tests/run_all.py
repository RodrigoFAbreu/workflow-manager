#!/usr/bin/env python3
"""Run every workflow-manager suite. Stdlib only.

    python3 tests/run_all.py           # everything
    python3 tests/run_all.py --fast    # skip the frozen-suite conformance run
    python3 tests/run_all.py --list [--select SPEC ...]
    python3 tests/run_all.py --jobs 1 [--select SPEC ...]

`--select` is repeatable (the union of its matches) and takes
`test_x.py`, `test_x.py::Class`, `test_x.py::Class::test_y`,
`frozen:<version>/<fixture>/<suite>.py` or
`frozen:<version>/<fixture>/<suite>.py::Class`. It is targeted selection for
debugging -- never a verification gate. `--jobs 1` runs each selected host
class in its own process, one at a time, in direct mode (the matrix classes
run their frozen suites in `setUpClass`, as today); frozen classes selected
without their matrix host class run as one chunk per suite in a fresh
repository, with no host assertions. It takes no run lock and no write
barrier.
"""

from __future__ import annotations

import sys

# Before anything else is imported: the tooling's own imports must not write
# `__pycache__` into the checkout.
sys.dont_write_bytecode = True

import argparse  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))

from parallel import inventory, tree, unit  # noqa: E402

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
    "test_parallel_runner.py",
)


def refuse(exc: Exception) -> int:
    print(f"run_all: error[{type(exc).__name__}]: {exc}", file=sys.stderr)
    return 2


def run_modules(fast: bool) -> int:
    suites = list(FAST_SUITES) + ([] if fast else list(SLOW_SUITES))
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


def _summary(record: dict) -> str:
    failed = sum(1 for o in record["outcomes"].values() if o == "fail")
    errored = sum(1 for o in record["outcomes"].values() if o in ("error", "unexpected_success"))
    skipped = len(record["skipped"])
    text = f"Ran {record['tests_run']} tests  "
    if record["passed"]:
        return text + ("OK" if not skipped else f"OK (skipped={skipped})")
    return text + f"FAILED (failures={failed}, errors={errored})"


def reproduce(unit_id: str, tests) -> str:
    module, cls = inventory.split_host_unit_id(unit_id)
    specs = [f"{module}::{cls}"] if not tests else [f"{module}::{cls}::{t}" for t in tests]
    return "python3 tests/run_all.py --jobs 1 " + " ".join(f"--select '{s}'" for s in specs)


def reproduce_frozen(unit_ids) -> str:
    return "python3 tests/run_all.py --jobs 1 " + " ".join(f"--select '{u}'" for u in unit_ids)


def run_frozen_chunks(repo_root: Path, selection: inventory.Selection,
                      frozen: inventory.FrozenInventory) -> tuple[int, int]:
    """Frozen units selected without their matrix host class, one chunk per
    `(version, fixture, suite)`, each in a fresh repository. Returns
    `(chunks, failed chunks)`."""
    import frozen_runs

    host_units = set(selection.host_unit_ids())
    groups: dict[tuple[str, str, str], list[str]] = {}
    for unit_id in selection.frozen_unit_ids():
        version, fixture, suite, cls = inventory.split_frozen_unit_id(unit_id)
        if frozen.host_of(version, fixture) not in host_units:  # else its host class runs it
            groups.setdefault((version, fixture, suite), []).append(cls)
    if not groups:
        return 0, 0
    digest = tree.tree_digest(repo_root)
    failed = 0
    for (version, fixture, suite), classes in sorted(groups.items()):
        chunk = frozen_runs.FrozenChunk(f"{version}/{fixture}/{suite}", version, fixture, suite,
                                        tuple(sorted(classes)))
        record = frozen_runs.execute(chunk, tree_digest=digest, plan_digest=None,
                                     repo_root=repo_root)
        ok = record.returncode == 0 and not record.timed_out
        failed += not ok
        label = f"frozen:{chunk.id} [{len(classes)} classes]"
        summary = f"Ran {record.ran} tests  " + ("OK" if ok else f"FAILED (rc {record.returncode})")
        print(f"{'ok  ' if ok else 'FAIL'} {label:<78} {record.duration:6.1f}s  {summary}",
              flush=True)
        if not ok:
            for name in record.failing:
                print(f"  failing: {name}")
            units = [inventory.frozen_unit_id(version, fixture, suite, c) for c in sorted(classes)]
            print(f"  reproduce: {reproduce_frozen(units)}")
            print(record.output[-6000:])
    return len(groups), failed


def run_units_serially(repo_root: Path, selection: inventory.Selection,
                       frozen: inventory.FrozenInventory) -> int:
    run_dir = Path(tempfile.mkdtemp(prefix="wm-run-"))
    runs = []
    started = time.monotonic()
    for index, unit_id in enumerate(selection.host_unit_ids()):
        tests = selection.units[unit_id]
        run = unit.launch(repo_root, unit_id, tests, run_dir, index)
        runs.append((run, tests))
        fault = run.infrastructure_fault
        if fault:
            status, summary = "ERR ", fault
        else:
            status = "ok  " if run.record["passed"] else "FAIL"
            summary = _summary(run.record)
        print(f"{status} {unit_id:<78} {run.wall:6.1f}s  {summary}", flush=True)
    chunks, failed_chunks = run_frozen_chunks(repo_root, selection, frozen)
    wall = time.monotonic() - started

    faults = [(r, t) for r, t in runs if r.infrastructure_fault]
    failures = [(r, t) for r, t in runs if not r.infrastructure_fault and not r.record["passed"]]
    for run, tests in faults + failures:
        print(f"\n{'=' * 70}\n{run.unit}\n{'=' * 70}")
        if run.record:
            for failing in run.record["failing"]:
                print(f"  failing: {failing}")
        else:
            print(f"  {run.infrastructure_fault}")
        print(f"  log: {run.log_path}")
        print(f"  reproduce: {reproduce(run.unit, tests)}")
        print(run.log_path.read_text(encoding="utf-8", errors="replace")[-6000:])
    print(f"\n{len(runs)} units{f', {chunks} frozen chunks' if chunks else ''}, "
          f"{wall:.1f}s wall", end="")
    if selection.partial_frozen:
        print(f"; {inventory.PARTIAL_FROZEN_NOTE}", end="")
    if faults or failures or failed_chunks:
        print(f"; results kept in {run_dir}")
        return 2 if faults else 1
    print()
    shutil.rmtree(run_dir, ignore_errors=True)
    return 0


def main(argv=None, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true",
                        help="skip the suites that run the frozen conformance matrix")
    parser.add_argument("--list", action="store_true",
                        help="print the selected atomic units and exit")
    parser.add_argument("--select", action="append", default=[], metavar="SPEC",
                        help="targeted selection (repeatable); not a verification gate")
    parser.add_argument("--jobs", type=int, metavar="N",
                        help="run each selected host class in its own process; only 1 "
                             "(serial) is supported")
    args = parser.parse_args(argv)
    if args.fast and (args.list or args.select or args.jobs is not None):
        parser.error("--fast cannot be combined with --list, --select or --jobs")
    if args.jobs is not None and args.jobs != 1:
        parser.error("only --jobs 1 is supported")

    if not (args.list or args.select or args.jobs is not None):
        return run_modules(args.fast)

    try:
        specs = [inventory.parse_spec(s) for s in args.select]
        inv = inventory.discover(repo_root)
        selection = inventory.select(inv.host, specs, inv.frozen)
    except (inventory.SelectSyntaxError, inventory.UnknownSelectorError,
            inventory.InventoryError) as exc:
        return refuse(exc)

    if args.list:
        for unit_id in selection.unit_ids():
            tests = selection.units[unit_id]
            print(unit_id if tests is None else f"{unit_id}  [{', '.join(tests)}]")
        if selection.partial_frozen:
            print(inventory.PARTIAL_FROZEN_NOTE)
        return 0
    return run_units_serially(repo_root, selection, inv.frozen)


if __name__ == "__main__":
    raise SystemExit(main())
