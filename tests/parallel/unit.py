"""Run one host chunk -- a class, or selected methods of it -- in its own
process, and write its result record.

    python3 -m parallel.unit --unit host:test_x.py::Class [--test test_y ...] \
        --record <path outside the checkout>

Run with cwd `<repo_root>/tests/`. The class runs through `unittest`, so its
`setUpClass`/`tearDownClass` run exactly once, as in a direct module run.
Exit 0 when every test passed, 1 when any failed or errored, 2 on a usage
error (no record is written then -- a missing record is an infrastructure
fault for whoever launched the unit).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import subprocess
import sys
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

from . import canonical_json, strict_json_loads
from .inventory import host_test_id, split_host_unit_id

RECORD_SCHEMA_VERSION = 1
OUTPUT_TAIL_CHARS = 6000


class _RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, module: str, cls: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._module, self._cls = module, cls
        self.ran_ids: list[str] = []
        self.outcomes: dict[str, str] = {}
        self.skip_reasons: dict[str, str] = {}
        self.failing_ids: list[str] = []

    def _id(self, test) -> str:
        method = getattr(test, "_testMethodName", None)
        if method is None:  # a class/module fixture error holder
            return host_test_id(self._module, self._cls, str(test))
        return host_test_id(self._module, self._cls, method)

    def _fail(self, test, outcome: str):
        tid = self._id(test)
        self.outcomes[tid] = outcome
        if tid not in self.failing_ids:
            self.failing_ids.append(tid)

    def startTest(self, test):
        super().startTest(test)
        self.ran_ids.append(self._id(test))

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.setdefault(self._id(test), "ok")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._fail(test, "fail")

    def addError(self, test, err):
        super().addError(test, err)
        self._fail(test, "error")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[self._id(test)] = "skip"
        self.skip_reasons[self._id(test)] = reason

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.outcomes[self._id(test)] = "expected_failure"

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._fail(test, "unexpected_success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._fail(test, "fail" if issubclass(err[0], test.failureException) else "error")


def run_unit(unit_id: str, tests: list[str] | None) -> dict:
    """Run the unit in this process and return its record."""
    module_file, cls_name = split_host_unit_id(unit_id)
    with contextlib.redirect_stdout(sys.stderr):
        module = importlib.import_module(module_file[:-3])
    cls = getattr(module, cls_name, None)
    if not (isinstance(cls, type) and issubclass(cls, unittest.TestCase)):
        raise LookupError(f"{module_file} has no test class {cls_name}")
    loader = unittest.defaultTestLoader
    if tests:
        missing = [t for t in tests if not callable(getattr(cls, t, None))]
        if missing:
            raise LookupError(f"{cls_name} has no test {missing}")
        suite = unittest.TestSuite(cls(t) for t in tests)
    else:
        suite = loader.loadTestsFromTestCase(cls)

    stream = io.StringIO()
    runner = unittest.TextTestRunner(
        stream=stream, verbosity=2,
        resultclass=lambda *a, **k: _RecordingResult(*a, module=module_file, cls=cls_name, **k))
    started_at = time.time()
    started = time.monotonic()
    result = runner.run(suite)
    duration = time.monotonic() - started
    ended_at = time.time()
    output = stream.getvalue()
    sys.stderr.write(output)
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "unit": unit_id,
        "tests_requested": sorted(tests) if tests else None,
        "tests_run": result.testsRun,
        "ran": result.ran_ids,
        "outcomes": dict(sorted(result.outcomes.items())),
        "skipped": dict(sorted(result.skip_reasons.items())),
        "failing": sorted(result.failing_ids),
        "passed": result.wasSuccessful(),
        "duration": round(duration, 3),
        "started_at": started_at,
        "ended_at": ended_at,
        "output_tail": output[-OUTPUT_TAIL_CHARS:],
    }


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m parallel.unit")
    parser.add_argument("--unit", required=True)
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--record", required=True, type=Path)
    args = parser.parse_args(argv)
    sys.dont_write_bytecode = True
    try:
        record = run_unit(args.unit, args.test or None)
    except (ValueError, LookupError, ImportError) as exc:
        print(f"parallel.unit: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    _write_atomic(args.record, canonical_json(record))
    return 0 if record["passed"] else 1


# -- launcher side -------------------------------------------------------------

@dataclass(frozen=True)
class UnitRun:
    unit: str
    returncode: int
    record: dict | None
    log_path: Path
    wall: float

    @property
    def infrastructure_fault(self) -> str | None:
        if self.record is None:
            return f"no result record (runner exit {self.returncode})"
        if self.returncode not in (0, 1) or (self.returncode == 0) != self.record["passed"]:
            return f"runner exit {self.returncode} disagrees with its record"
        return None


def unit_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def unit_argv(unit_id: str, record_path: Path, tests=()) -> list[str]:
    """The command that runs one host chunk (cwd `<repo_root>/tests/`)."""
    argv = [sys.executable, "-B", "-m", "parallel.unit", "--unit", unit_id,
            "--record", str(record_path)]
    for test in tests or ():
        argv += ["--test", test]
    return argv


def launch(repo_root: Path, unit_id: str, tests, run_dir: Path, index: int) -> UnitRun:
    """Run one host unit in its own process, cwd `<repo_root>/tests/`, and
    collect its record and log from `run_dir` (outside the checkout)."""
    stem = f"{index:04d}"
    record_path = run_dir / f"{stem}.record.json"
    log_path = run_dir / f"{stem}.log"
    argv = unit_argv(unit_id, record_path, tests)
    started = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(argv, cwd=str(Path(repo_root) / "tests"), env=unit_env(),
                              stdout=log, stderr=subprocess.STDOUT)
    wall = time.monotonic() - started
    record = None
    if record_path.exists():
        record = strict_json_loads(record_path.read_text(encoding="utf-8"))
    return UnitRun(unit_id, proc.returncode, record, log_path, wall)


if __name__ == "__main__":
    raise SystemExit(main())
