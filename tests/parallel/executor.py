"""The executor: one plan, run locally or as CI shards and an aggregate (plan
sections 5.5, 5.8-5.11; INV-1, INV-6, INV-7, INV-8).

A local run, under the checkout run lock taken by `cli`:

1. snapshot the tree (before discovery, so discovery is inside the window);
2. discover, select and plan into the run directory (outside the checkout);
3. apply the write barrier;
4. phase A: pre-phase A0 runs every exclusive chunk alone, one at a time,
   with the barrier lifted for exactly its resources' trees; then one worker
   per shard runs that shard's shared chunks in plan order;
5. phase B: the matrix host classes in merged mode, against merge contexts
   built from the verified plan (never from the records);
6. restore the barrier, re-snapshot and compare;
7. append the observed timings to the user cache and report.

`--run-shard` is steps 1-4 and 6 for one shard of a verified plan, writing its
results to a directory; `--aggregate` verifies every shard's results against
the plan and runs steps 5-6. Every function takes `repo_root`; nothing here
reads a module-level root, and nothing here imports `support`,
`frozen_runs` or `parallel.matrix` -- the frozen side runs in subprocesses of
the checkout being verified (`parallel.frozen_chunk`).
"""

from __future__ import annotations

import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import canonical_json, isolation, planner, report, strict_json_loads
from . import resources as resources_mod
from . import timings as timings_mod
from . import tree as tree_mod
from .frozen_chunk import MERGE_REFUSED, is_frozen, spec_json
from .inventory import Inventory, discover, split_frozen_unit_id
from .plan_schema import ChunkDescriptor, shard_chunks
from .unit import unit_argv

RESULTS_SCHEMA_VERSION = 1
FROZEN_RECORDS = "frozen-records"
MERGE_CONTEXT = "merge-context"
SHARD_SUMMARY = "shard-{index}.json"
RECORDS_ENV = "WM_FROZEN_RECORDS"
CONTEXT_ENV = "WM_FROZEN_CONTEXT"

PHASE_A0 = "A0"
PHASE_A = "A"
PHASE_B = "B"


class ExecutorError(Exception):
    """A refusal after the lock: the run cannot be trusted or cannot start."""


class IntegrityError(ExecutorError):
    """The repository tree changed during the run (5.9 step 6)."""


class IncompleteResultsError(ExecutorError):
    """A planned chunk has no result, or a result names no planned chunk."""


class DuplicateResultError(ExecutorError):
    """Two results claim the same shard or the same chunk."""


class ForeignResultsError(ExecutorError):
    """A shard's results were produced for another plan or tree."""


class FrozenMergeError(ExecutorError):
    """A frozen record set is structurally incomplete, duplicated or foreign to
    the merge context built from the plan (5.5)."""


class InfrastructureFaultError(ExecutorError):
    """At least one chunk timed out, died without a record, or disagreed with
    its record (INV-7)."""


class ResultsDirError(ExecutorError):
    """`--results` names a directory that already holds files."""


class InterruptedRunError(ExecutorError):
    """The run was interrupted by a signal."""


class TimingSourceError(ExecutorError):
    """`--update-timings` was given a source that does not exist."""


# -- chunk results ----------------------------------------------------------------------

NOT_RUN = "not_run"
KNOWN_OUTCOMES = frozenset((isolation.PASSED, isolation.FAILED, NOT_RUN,
                            *isolation.INFRASTRUCTURE_OUTCOMES))


@dataclass
class ChunkResult:
    chunk: ChunkDescriptor
    phase: str
    shard: int
    kind: str                      # "host" or "frozen"
    outcome: str                   # an isolation outcome, or "not_run"
    started_at: float = 0.0
    ended_at: float = 0.0
    returncode: int | None = None
    record: dict | None = None
    log: str | None = None
    detail: str = ""
    tmp_residue: tuple[str, ...] = ()

    @property
    def fault(self) -> str | None:
        if self.outcome in isolation.INFRASTRUCTURE_OUTCOMES:
            return f"{self.outcome}: {self.detail}" if self.detail else self.outcome
        return None

    @property
    def duration(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def window(self) -> isolation.Window:
        return isolation.Window(self.chunk.id, self.started_at, self.ended_at,
                                self.chunk.exclusive)

    def to_json(self) -> dict:
        record = self.record
        if record is not None and self.kind == "frozen":
            # The full record is in `frozen-records/`; a summary keeps the tail
            # (which still holds unittest's summary line).
            record = {**record, "output": (record.get("output") or "")[-report.OUTPUT_TAIL:]}
        return {"chunk": self.chunk.to_json(), "phase": self.phase, "shard": self.shard,
                "kind": self.kind, "outcome": self.outcome, "started_at": self.started_at,
                "ended_at": self.ended_at, "returncode": self.returncode, "record": record,
                "log": self.log, "detail": self.detail, "tmp_residue": list(self.tmp_residue)}

    @classmethod
    def from_json(cls, obj) -> "ChunkResult":
        try:
            result = cls(ChunkDescriptor.from_json(obj["chunk"]), obj["phase"], obj["shard"],
                         obj["kind"], obj["outcome"], obj["started_at"], obj["ended_at"],
                         obj["returncode"], obj["record"], obj["log"], obj["detail"],
                         tuple(obj["tmp_residue"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise IncompleteResultsError(f"malformed chunk result: {exc}") from exc
        # An outcome `verdict_of` does not know would otherwise count as a pass.
        if result.outcome not in KNOWN_OUTCOMES:
            raise IncompleteResultsError(
                f"chunk result {result.chunk.id}: unknown outcome {result.outcome!r}")
        return result


def _kind(chunk: ChunkDescriptor) -> str:
    return "frozen" if is_frozen(chunk) else "host"


# -- the engine ---------------------------------------------------------------------------

class Engine:
    """Runs planned chunks under one held lock and one applied barrier."""

    def __init__(self, repo_root: Path, run_dir: Path, *, lock: isolation.RunLock,
                 plan: dict, inv: Inventory, resources: resources_mod.Resources,
                 barrier: isolation.Barrier | None, shuffle_seed: int | None = None,
                 progress=None):
        self.repo_root = Path(repo_root)
        self.run_dir = Path(run_dir)
        self.lock = lock
        self.plan = plan
        self.inv = inv
        self.resources = resources
        self.barrier = barrier
        self.shuffle_seed = shuffle_seed
        self.progress = progress
        self.results: list[ChunkResult] = []
        self.stop = threading.Event()
        self._mutex = threading.Lock()
        self._done = 0
        self.total = 0
        for directory in (FROZEN_RECORDS, MERGE_CONTEXT, "specs"):
            (self.run_dir / directory).mkdir(parents=True, exist_ok=True)

    # -- one chunk --------------------------------------------------------------------

    def _argv(self, chunk: ChunkDescriptor, record: Path, timeout: float) -> list:
        if is_frozen(chunk):
            spec = self.run_dir / "specs" / (record.stem + ".spec.json")
            spec.write_text(spec_json(chunk, self.inv.frozen, tree_digest=self.plan["tree_digest"],
                                      plan_digest=self.plan["plan_digest"],
                                      timeout=timeout + 60), encoding="utf-8")
            return [sys.executable, "-B", "-m", "parallel.frozen_chunk", "run",
                    "--spec", spec, "--record", record]
        unit_id = chunk.units[0]
        tests = self.plan["selection"].get(unit_id)
        return unit_argv(unit_id, record, tests or ())

    def run_one(self, chunk: ChunkDescriptor, phase: str, shard: int,
                extra_env: dict | None = None) -> ChunkResult:
        if self.stop.is_set():
            result = ChunkResult(chunk, phase, shard, _kind(chunk), "not_run",
                                 detail="the run was interrupted")
            self._finish(result)
            return result
        timeout = isolation.chunk_timeout(chunk.estimate)
        record = isolation.chunk_paths(self.run_dir, chunk.id).record
        run = isolation.run_chunk(self.repo_root, chunk.id, self._argv(chunk, record, timeout),
                                  run_dir=self.run_dir, timeout=timeout,
                                  cwd=self.repo_root / "tests", extra_env=extra_env,
                                  lock=self.lock)
        result = ChunkResult(chunk, phase, shard, _kind(chunk), run.outcome, run.started_at,
                             run.ended_at, run.returncode, run.record, str(run.log_path),
                             run.detail, run.tmp_residue)
        if result.kind == "frozen" and result.record is not None:
            if result.record.get("timed_out"):
                result.outcome = isolation.TIMED_OUT
                result.detail = "the frozen suite was killed on its own timeout"
            else:
                target = self.run_dir / FROZEN_RECORDS / (record.stem + ".record.json")
                shutil.copyfile(record, target)
        self._finish(result)
        return result

    def _finish(self, result: ChunkResult) -> None:
        with self._mutex:
            self.results.append(result)
            self._done += 1
            done = self._done
        if self.progress is not None:
            self.progress(report.progress_line(result, done, self.total))

    # -- phases -------------------------------------------------------------------------

    def _ordered(self, chunks, salt: int):
        chunks = list(chunks)
        if self.shuffle_seed is not None:
            random.Random(f"{self.shuffle_seed}:{salt}").shuffle(chunks)
        return chunks

    def run_a0(self, chunks) -> None:
        """Every exclusive chunk alone, one at a time, the barrier lifted for
        exactly the trees its resources declare and re-applied before the next
        chunk starts (5.8, 5.9)."""
        for chunk in chunks:
            if self.barrier is not None:
                self.barrier.lift(isolation.lift_trees(self.resources, chunk))
            try:
                self.run_one(chunk, PHASE_A0, chunk.shard_index)
            finally:
                if self.barrier is not None:
                    self.barrier.relock()

    def run_pool(self, shards, phase: str, extra_env: dict | None = None) -> None:
        """One worker thread per non-empty shard, each running its chunks in
        order (permuted by `--shuffle-seed`)."""
        work = [(index, self._ordered(chunks, index)) for index, chunks in enumerate(shards)
                if chunks]
        errors: list[BaseException] = []

        def worker(index, chunks):
            try:
                for chunk in chunks:
                    self.run_one(chunk, phase, index, extra_env)
            except BaseException as exc:  # noqa: BLE001 -- re-raised by the main thread
                errors.append(exc)
                self.stop.set()

        threads = [threading.Thread(target=worker, args=item, daemon=True) for item in work]
        for thread in threads:
            thread.start()
        try:
            for thread in threads:
                while thread.is_alive():
                    thread.join(0.2)
        except BaseException:
            self.interrupt()
            for thread in threads:
                thread.join(30)
            raise
        if errors:
            raise errors[0]

    def interrupt(self) -> None:
        """Stop starting chunks and kill every live chunk's process group."""
        self.stop.set()
        for pgid in self.lock.live_chunk_pgids():
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    # -- phase B -------------------------------------------------------------------------

    def prepare_merge(self) -> list[dict]:
        """Build the merge contexts from the verified plan and check every
        frozen record set against them, in the checkout's own interpreter
        environment. Returns the refusals (empty when every merge holds)."""
        inventory_path = self.run_dir / "inventory.json"
        plan_path = self.run_dir / "plan.json"
        (self.run_dir / "tmp").mkdir(exist_ok=True)
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "parallel.frozen_chunk", "prepare-merge",
             "--plan", str(plan_path), "--inventory", str(inventory_path),
             "--records", str(self.run_dir / FROZEN_RECORDS),
             "--contexts", str(self.run_dir / MERGE_CONTEXT)],
            cwd=str(self.repo_root / "tests"), capture_output=True, text=True,
            env=isolation.chunk_env(self.run_dir / "tmp"))
        if proc.returncode == 0:
            return []
        if proc.returncode == MERGE_REFUSED:
            return [strict_json_loads(line) for line in proc.stdout.splitlines() if line.strip()]
        return [{"row": "*", "error": f"prepare-merge exit {proc.returncode}: "
                                       f"{(proc.stdout + proc.stderr)[-3000:]}"}]

    def phase_b_env(self) -> dict:
        return {RECORDS_ENV: str(self.run_dir / FROZEN_RECORDS),
                CONTEXT_ENV: str(self.run_dir / MERGE_CONTEXT)}

    def run_phase_b(self, refused_rows) -> None:
        refused = set(refused_rows)
        shards = []
        for chunks in shard_chunks(self.plan["phase_b"]):
            keep = []
            for chunk in chunks:
                row = self.inv.frozen.matrix.get(chunk.units[0]) if self.inv.frozen else None
                if row is not None and f"{row[0]}/{row[1]}" in refused:
                    self._finish(ChunkResult(chunk, PHASE_B, -1, "host", "not_run",
                                             detail="its frozen merge was refused"))
                else:
                    keep.append(chunk)
            shards.append(keep)
        self.run_pool(shards, PHASE_B, self.phase_b_env())


# -- shared steps -------------------------------------------------------------------------

def check_results_dir(results: Path) -> None:
    results = Path(results)
    if results.exists() and (not results.is_dir() or any(results.iterdir())):
        raise ResultsDirError(f"--results {results} exists and is not an empty directory")


def make_run_dir(results: Path | None) -> tuple[Path, bool]:
    """`(run directory, whether it was created here as a temporary)`: the
    system temp dir's `wm-run-*`, or `--results` (outside the checkout, 5.6)."""
    if results is None:
        import tempfile
        return Path(tempfile.mkdtemp(prefix="wm-run-")), True
    check_results_dir(results)
    results = Path(results)
    results.mkdir(parents=True, exist_ok=True)
    return results, False


def discover_and_select(repo_root: Path, specs) -> tuple[Inventory, object]:
    from .inventory import select
    inv = discover(repo_root)
    return inv, select(inv.host, specs, inv.frozen)


def write_inputs(run_dir: Path, inv: Inventory, plan: dict) -> None:
    (run_dir / "inventory.json").write_text(inv.to_json(), encoding="utf-8")
    planner.write_plan(plan, run_dir / "plan.json")


@dataclass
class Guard:
    """The per-mode guards of 5.9: the step-1/6 snapshot, and optionally the
    write barrier (steps 3-5)."""

    repo_root: Path
    lock: isolation.RunLock
    allow_root: bool = False
    before: tree_mod.Snapshot | None = None
    barrier: isolation.Barrier | None = None
    diffs: list = field(default_factory=list)
    started: float = 0.0
    ended: float = 0.0

    def snapshot(self) -> None:
        self.started = time.time()
        self.before = tree_mod.snapshot(self.repo_root)

    def apply(self, say) -> None:
        self.barrier = isolation.apply_barrier(self.repo_root, self.lock,
                                               allow_root=self.allow_root)
        for warning in self.barrier.warnings:
            say(f"warning: {warning}")
        say(report.BARRIER_NOTE)

    def summary_warnings(self) -> list[str]:
        return [f"  {w}" for w in self.barrier.warnings] if self.barrier else []

    def restore(self) -> None:
        if self.barrier is not None:
            isolation.restore_barrier(self.repo_root, self.barrier)

    def compare(self) -> list:
        self.ended = time.time()
        self.diffs = tree_mod.compare(self.before, tree_mod.snapshot(self.repo_root))
        return self.diffs


def _install_signal_handlers():
    """SIGTERM raises like SIGINT does, so every `finally` (chunk kill, barrier
    restore, lock release) runs. Only possible on the main thread."""
    if threading.current_thread() is not threading.main_thread():
        return None

    def on_term(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")

    return signal.signal(signal.SIGTERM, on_term)


def _restore_signal_handlers(previous) -> None:
    if previous is not None:
        signal.signal(signal.SIGTERM, previous)


def refuse_root(allow_root: bool) -> None:
    if os.geteuid() == 0 and not allow_root:
        raise isolation.RootRefusedError("running as root disables the write barrier; "
                                         "refusing without --allow-root")


# -- verdict --------------------------------------------------------------------------------

@dataclass
class Verdict:
    code: int
    #: `(ErrorName, message)` for every infrastructure fault, in report order
    faults: list[tuple[str, str]]
    #: results that are test failures (exit 1)
    failures: list[ChunkResult]


def judged_rows(plan: dict, inv: Inventory) -> set[tuple[str, str]]:
    """`(version, fixture)` rows whose matrix host class is in phase B -- their
    frozen chunks' outcomes are judged by that class, not on their own."""
    phase_b = {u for shard in shard_chunks(plan["phase_b"]) for c in shard for u in c.units}
    matrix = inv.frozen.matrix if inv.frozen else {}
    return {tuple(row) for unit, row in matrix.items() if unit in phase_b}


def make_judged(plan: dict, inv: Inventory):
    rows = judged_rows(plan, inv)

    def judged(result: ChunkResult) -> bool:
        if result.kind != "frozen":
            return False
        version, fixture, _, _ = split_frozen_unit_id(result.chunk.units[0])
        return (version, fixture) in rows
    return judged


def verdict_of(results, judged, *, extra_faults=()) -> Verdict:
    faults = list(extra_faults)
    failures = []
    for result in results:
        if result.fault:
            faults.append(("InfrastructureFaultError", f"{result.chunk.id}: {result.fault}"))
        elif result.outcome == "not_run":
            faults.append(("InfrastructureFaultError", f"{result.chunk.id}: not run "
                                                       f"({result.detail})"))
        elif result.outcome == isolation.FAILED and not judged(result):
            failures.append(result)
    return Verdict(2 if faults else (1 if failures else 0), faults, failures)


def window_faults(results, *, per_shard: bool) -> list[tuple[str, str]]:
    """Re-check from the recorded timestamps that no exclusive window overlapped
    any other -- over the whole run locally, within each shard in CI (each
    shard is its own machine there)."""
    groups: dict = {}
    for result in results:
        if result.started_at:
            key = result.shard if per_shard and result.phase != PHASE_B else "run"
            groups.setdefault(key, []).append(result.window)
    faults = []
    for windows in groups.values():
        try:
            isolation.check_exclusive_windows(windows)
        except isolation.ExclusiveOverlapError as exc:
            faults.append(("ExclusiveOverlapError", str(exc)))
    return faults


def integrity_faults(repo_root: Path, guard: Guard, results) -> list[tuple[str, str]]:
    if not guard.diffs:
        return []
    attributions = isolation.attribute_integrity_diff(
        repo_root, guard.diffs, [r.window for r in results if r.started_at],
        run_started=guard.started, run_ended=guard.ended)
    return [("IntegrityError", f"{a.path} changed during the run ({a.before} -> {a.after}); "
                               f"chunks whose windows overlapped it ({a.basis}): "
                               f"{', '.join(a.suspects) or 'none'}") for a in attributions]


# -- timings ---------------------------------------------------------------------------------

def observations(results, profile: str) -> list:
    out = []
    for result in results:
        if result.record is not None and result.outcome in (isolation.PASSED, isolation.FAILED):
            out.extend(timings_mod.observations_from_record(result.record, profile))
    return out


def write_observations(obs, path: Path, *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a" if append else "w", encoding="utf-8") as handle:
        for o in obs:
            handle.write(o.to_json_line())


def append_side_effect(write, what: str, path, err) -> None:
    """Run one write the verdict does not depend on, after the report: an
    `OSError` becomes a warning, never an exit code."""
    try:
        write()
    except OSError as exc:
        err(f"warning: could not write the {what} to {path}: "
            f"{exc.strerror or exc}; the verdict is unchanged")


def drifted_chunks(results) -> list[str]:
    estimates = {r.chunk.id: r.chunk.estimate for r in results
                 if r.outcome in (isolation.PASSED, isolation.FAILED)}
    observed = {r.chunk.id: r.duration for r in results if r.chunk.id in estimates}
    return timings_mod.drifted(estimates, observed)


# -- the report -------------------------------------------------------------------------------

def run_identity(repo_root: Path, plan: dict, inv: Inventory, results, scope: str) -> dict:
    return report.evidence_identity(plan, results, inv.frozen.classes if inv.frozen else {},
                                    head=tree_mod.head_commit(repo_root),
                                    inventory_unit_ids=inv.unit_ids(), scope=scope)


def emit_report(out, *, plan: dict, inv: Inventory, results, verdict: Verdict, wall: float,
                run_dir: Path | None, judged, identity: dict, log_label=None,
                extra_summary=()) -> str:
    matrix = inv.frozen.matrix if inv.frozen else {}
    lines = [""] + report.module_lines(results, matrix, judged)
    selection = plan["selection"]
    shown = set()
    for result in sorted(results, key=lambda r: r.chunk.id):
        if result.fault or result.outcome == "not_run" or result in verdict.failures:
            lines += ["", report.failure_block(
                result, selection, log_label=log_label(result) if log_label else None)]
            shown.add(result.chunk.id)
    judged_failures = [r for r in results if r.outcome == isolation.FAILED and judged(r)]
    if judged_failures:
        lines += ["", "frozen chunks with a non-zero exit, judged by their matrix host class "
                      "(documented portability exceptions are expected here):"]
        for result in sorted(judged_failures, key=lambda r: r.chunk.id):
            failing = ", ".join((result.record or {}).get("failing", [])) or "(none listed)"
            lines.append(f"  {result.chunk.id}: {failing}")
    lines += [""] + report.shard_summary(plan, results, wall=wall,
                                         drifted=drifted_chunks(results), extra=extra_summary)
    if plan.get("partial_frozen"):
        lines.append(f"  {report_partial_note()}")
    for name, message in verdict.faults:
        lines.append(f"  fault [{name}]: {message}")
    lines.append(report.identity_line(identity))
    lines.append(f"verdict: exit {verdict.code}"
                 + (f"; results kept in {run_dir}" if run_dir is not None else ""))
    text = "\n".join(lines)
    out(text)
    return text


def report_partial_note() -> str:
    from .inventory import PARTIAL_FROZEN_NOTE
    return PARTIAL_FROZEN_NOTE


def finish_verdict(verdict: Verdict, err) -> int:
    if verdict.faults:
        name, message = verdict.faults[0]
        more = f" (and {len(verdict.faults) - 1} more; see the report)" \
            if len(verdict.faults) > 1 else ""
        err(f"run_all: error[{name}]: {message}{more}")
    return verdict.code


# -- modes --------------------------------------------------------------------------------------

def _progress(out):
    return lambda line: out(line)


def local_run(repo_root: Path, lock: isolation.RunLock, *, specs, jobs, shuffle_seed=None,
              whole_groups=False, allow_root=False, results=None, out=print, err=print,
              environ=None, cpu_count=None) -> int:
    """Steps 1-7 of 5.9 for one selection on this machine."""
    environ = os.environ if environ is None else environ
    refuse_root(allow_root)
    guard = Guard(Path(repo_root), lock, allow_root)
    guard.snapshot()
    started = time.monotonic()
    if results is not None:
        check_results_dir(results)
    inv, selection = discover_and_select(repo_root, specs)
    res = resources_mod.load(repo_root, list(inv.host))
    plan = planner.plan_checkout(repo_root, inv, selection, profile="local",
                                 shards=None if jobs in (None, "auto") else jobs,
                                 whole_groups=whole_groups, cpu_count=cpu_count)
    run_dir, temporary = make_run_dir(results)
    write_inputs(run_dir, inv, plan)
    out(f"run directory: {run_dir}")
    out(f"plan: {len(selection.units)} units, n={plan['n']} worker(s), "
        f"predicted {plan['predicted']['makespan']['total']:.1f}s")
    engine = Engine(repo_root, run_dir, lock=lock, plan=plan, inv=inv, resources=res,
                    barrier=None, shuffle_seed=shuffle_seed, progress=_progress(out))
    order = isolation.phase_a_order(plan)
    engine.total = sum(len(s) for s in shard_chunks(plan)) + \
        sum(len(s) for s in shard_chunks(plan["phase_b"]))
    refusals: list[dict] = []
    interrupted = False
    previous = _install_signal_handlers()
    try:
        guard.apply(out)
        engine.barrier = guard.barrier
        engine.run_a0(order.a0)
        engine.run_pool(order.shards, PHASE_A)
        if plan["phase_b"]["shards"]:
            refusals = engine.prepare_merge()
            engine.run_phase_b({r["row"] for r in refusals})
    except KeyboardInterrupt:
        engine.interrupt()
        interrupted = True
    finally:
        try:
            guard.restore()
        finally:
            _restore_signal_handlers(previous)
    guard.compare()
    wall = time.monotonic() - started

    results_list = engine.results
    judged = make_judged(plan, inv)
    extra = [("FrozenMergeError", f"{r['row']}: {r['error']}") for r in refusals]
    extra += window_faults(results_list, per_shard=False)
    extra += integrity_faults(Path(repo_root), guard, results_list)
    if interrupted:
        extra.append(("InterruptedRunError", "the run was interrupted"))
    verdict = verdict_of(results_list, judged, extra_faults=extra)

    obs = observations(results_list, "local")
    identity = run_identity(repo_root, plan, inv, results_list,
                            f"local, {plan['n']} worker(s)")
    (run_dir / "results.json").write_text(
        report.results_doc(results_list, verdict.code,
                           inv.frozen.classes if inv.frozen else {}, identity), encoding="utf-8")
    write_observations(obs, run_dir / "timings.jsonl", append=False)
    keep = not (temporary and verdict.code == 0)
    emit_report(out, plan=plan, inv=inv, results=results_list, verdict=verdict, wall=wall,
                run_dir=run_dir if keep else None, judged=judged, identity=identity,
                extra_summary=guard.summary_warnings())
    # Last, and never part of the verdict: the user-level history is an
    # incidental cache (5.2), so an unwritable one costs future estimates a
    # line, not this run its report or its exit code.
    append_side_effect(lambda: write_observations(obs, timings_mod.history_path(environ),
                                                  append=True),
                       "timing history", timings_mod.history_path(environ), err)
    if not keep:
        isolation.clean_tmpdir(run_dir)
    return finish_verdict(verdict, err)


def list_units(repo_root: Path, lock, *, specs, out=print) -> int:
    guard = Guard(Path(repo_root), lock)
    guard.snapshot()
    inv, selection = discover_and_select(repo_root, specs)
    for unit_id in selection.unit_ids():
        tests = selection.units[unit_id]
        out(unit_id if tests is None else f"{unit_id}  [{', '.join(tests)}]")
    if selection.partial_frozen:
        out(report_partial_note())
    _refuse_integrity(repo_root, guard)
    return 0


def _refuse_integrity(repo_root: Path, guard: Guard) -> None:
    if guard.compare():
        raise IntegrityError("; ".join(f"{d.path} ({d.before} -> {d.after})"
                                       for d in guard.diffs))


def plan_only(repo_root: Path, lock, *, specs, profile, out_path, shards=None,
              whole_groups=False, out=print, cpu_count=None) -> int:
    guard = Guard(Path(repo_root), lock)
    guard.snapshot()
    inv, selection = discover_and_select(repo_root, specs)
    plan = planner.plan_checkout(repo_root, inv, selection, profile=profile, shards=shards,
                                 whole_groups=whole_groups, cpu_count=cpu_count)
    if out_path is None:
        out_path = make_run_dir(None)[0] / "plan.json"
    planner.write_plan(plan, out_path)
    _refuse_integrity(repo_root, guard)
    out(f"plan written to {out_path}")
    out(f"n={plan['n']} shards, {sum(len(s['chunks']) for s in plan['shards'])} phase-A chunks, "
        f"{sum(len(s['chunks']) for s in plan['phase_b']['shards'])} phase-B units, "
        f"predicted {plan['predicted']['makespan']['total']:.1f}s, "
        f"plan_digest {plan['plan_digest']}")
    return 0


def run_shard(repo_root: Path, lock, *, index: int, plan_path: Path, results: Path,
              allow_root=False, out=print, err=print) -> int:
    """One CI shard: the plan's shard `index`, exclusive chunks first, under the
    lock, the snapshot and the barrier (5.9 "Guards per mode", 5.10)."""
    refuse_root(allow_root)
    guard = Guard(Path(repo_root), lock, allow_root)
    guard.snapshot()
    started = time.monotonic()
    plan = planner.load_plan(plan_path, repo_root)
    if not 0 <= index < plan["n"]:
        raise IncompleteResultsError(f"--run-shard {index}: the plan has shards 0..{plan['n'] - 1}")
    run_dir, _ = make_run_dir(results)
    inv = discover(repo_root)
    res = resources_mod.load(repo_root, list(inv.host))
    write_inputs(run_dir, inv, plan)
    shard = shard_chunks(plan)[index]
    engine = Engine(repo_root, run_dir, lock=lock, plan=plan, inv=inv, resources=res,
                    barrier=None, progress=_progress(out))
    engine.total = len(shard)
    interrupted = False
    previous = _install_signal_handlers()
    try:
        guard.apply(out)
        engine.barrier = guard.barrier
        engine.run_a0([c for c in shard if c.exclusive])
        engine.run_pool([[c for c in shard if not c.exclusive]], PHASE_A)
    except KeyboardInterrupt:
        engine.interrupt()
        interrupted = True
    finally:
        try:
            guard.restore()
        finally:
            _restore_signal_handlers(previous)
    guard.compare()
    wall = time.monotonic() - started
    for result in engine.results:
        result.shard = index
        if result.log:
            result.log = os.path.relpath(result.log, run_dir)
    summary = {
        "schema_version": RESULTS_SCHEMA_VERSION, "shard": index,
        "plan_digest": plan["plan_digest"], "tree_digest": plan["tree_digest"],
        "results": [r.to_json() for r in sorted(engine.results, key=lambda r: r.chunk.id)],
        "integrity": [message for _, message in integrity_faults(Path(repo_root), guard,
                                                                  engine.results)],
        "interrupted": interrupted, "wall": round(wall, 3),
        "identity": run_identity(repo_root, plan, inv, engine.results,
                                 f"shard {index} of {plan['n']}"),
    }
    (run_dir / SHARD_SUMMARY.format(index=index)).write_text(canonical_json(summary),
                                                             encoding="utf-8")
    write_observations(observations(engine.results, plan["profile"]), run_dir / "timings.jsonl",
                       append=False)
    judged = make_judged(plan, inv)
    extra = window_faults(engine.results, per_shard=True)
    extra += [("IntegrityError", m) for m in summary["integrity"]]
    if interrupted:
        extra.append(("InterruptedRunError", "the shard was interrupted"))
    verdict = verdict_of(engine.results, judged, extra_faults=extra)
    for result in engine.results:
        if result.log:
            result.log = str(run_dir / result.log)
    emit_report(out, plan=plan, inv=inv, results=engine.results, verdict=verdict, wall=wall,
                run_dir=run_dir, judged=judged, identity=summary["identity"],
                extra_summary=guard.summary_warnings())
    return finish_verdict(verdict, err)


def _load_shards(results_root: Path, plan: dict) -> list[tuple[Path, dict]]:
    """Every shard summary under `results_root`, verified against the plan:
    one per shard index, each for this plan and tree, each holding exactly its
    planned chunks once (INV-1 over what was actually received)."""
    found: dict[int, tuple[Path, dict]] = {}
    for path in sorted(Path(results_root).rglob("shard-*.json")):
        try:
            doc = strict_json_loads(path.read_text(encoding="utf-8"))
            index = doc["shard"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IncompleteResultsError(f"{path}: unreadable shard summary: {exc}") from exc
        if doc.get("plan_digest") != plan["plan_digest"] or \
                doc.get("tree_digest") != plan["tree_digest"]:
            raise ForeignResultsError(
                f"{path}: results for plan {doc.get('plan_digest')!r} / tree "
                f"{doc.get('tree_digest')!r}, not this plan ({plan['plan_digest']}) and tree "
                f"({plan['tree_digest']})")
        if index in found:
            raise DuplicateResultError(f"shard {index} has two result sets: {found[index][0]} "
                                       f"and {path}")
        found[index] = (path, doc)
    planned = shard_chunks(plan)
    missing = [i for i in range(plan["n"]) if i not in found]
    extra = sorted(i for i in found if not 0 <= i < plan["n"])
    if missing or extra:
        raise IncompleteResultsError(f"shard results missing for {missing}, unplanned {extra}")
    for index, chunks in enumerate(planned):
        path, doc = found[index]
        got = [r.get("chunk", {}).get("id") for r in doc.get("results", [])]
        if sorted(got) != sorted(c.id for c in chunks) or len(set(got)) != len(got):
            raise IncompleteResultsError(
                f"{path}: shard {index} reports chunks {sorted(got)}, the plan has "
                f"{sorted(c.id for c in chunks)}")
    return [found[i] for i in range(plan["n"])]


def aggregate(repo_root: Path, lock, *, results_root: Path, plan_path: Path, allow_root=False,
              out=print, err=print, environ=None) -> int:
    """The CI `aggregate` job: verify every shard's results against the plan,
    build the merge contexts from the plan, run phase B, report (5.10)."""
    environ = os.environ if environ is None else environ
    refuse_root(allow_root)
    guard = Guard(Path(repo_root), lock, allow_root)
    guard.snapshot()
    started = time.monotonic()
    plan = planner.load_plan(plan_path, repo_root)
    shards = _load_shards(results_root, plan)
    inv = discover(repo_root)
    res = resources_mod.load(repo_root, list(inv.host))
    run_dir, _ = make_run_dir(None)
    write_inputs(run_dir, inv, plan)
    engine = Engine(repo_root, run_dir, lock=lock, plan=plan, inv=inv, resources=res,
                    barrier=None, progress=_progress(out))
    received: list[ChunkResult] = []
    shard_integrity = []
    seen_records: set[str] = set()
    for path, doc in shards:
        for obj in doc["results"]:
            result = ChunkResult.from_json(obj)
            if result.log:
                result.log = str(path.parent / result.log)
            received.append(result)
        shard_integrity += [("IntegrityError", f"shard {doc['shard']}: {m}")
                            for m in doc.get("integrity", [])]
        if doc.get("interrupted"):
            shard_integrity.append(("InterruptedRunError", f"shard {doc['shard']} was interrupted"))
        for record in sorted((path.parent / FROZEN_RECORDS).glob("*.record.json")):
            if record.name in seen_records:
                raise DuplicateResultError(f"frozen record {record.name} arrived from two shards")
            seen_records.add(record.name)
            shutil.copyfile(record, run_dir / FROZEN_RECORDS / record.name)
    engine.total = sum(len(s) for s in shard_chunks(plan["phase_b"]))
    refusals: list[dict] = []
    interrupted = False
    previous = _install_signal_handlers()
    try:
        guard.apply(out)
        engine.barrier = guard.barrier
        if plan["phase_b"]["shards"]:
            refusals = engine.prepare_merge()
            engine.run_phase_b({r["row"] for r in refusals})
    except KeyboardInterrupt:
        engine.interrupt()
        interrupted = True
    finally:
        try:
            guard.restore()
        finally:
            _restore_signal_handlers(previous)
    guard.compare()
    wall = time.monotonic() - started
    results_list = received + engine.results
    judged = make_judged(plan, inv)
    extra = [("FrozenMergeError", f"{r['row']}: {r['error']}") for r in refusals]
    extra += window_faults(results_list, per_shard=True) + shard_integrity
    extra += integrity_faults(Path(repo_root), guard, engine.results)
    if interrupted:
        extra.append(("InterruptedRunError", "the aggregate was interrupted"))
    verdict = verdict_of(results_list, judged, extra_faults=extra)
    identity = run_identity(repo_root, plan, inv, results_list,
                            f"aggregate of {plan['n']} shard(s)")
    (run_dir / "results.json").write_text(
        report.results_doc(results_list, verdict.code,
                           inv.frozen.classes if inv.frozen else {}, identity), encoding="utf-8")
    text = emit_report(out, plan=plan, inv=inv, results=results_list, verdict=verdict,
                       wall=wall, run_dir=run_dir, judged=judged, identity=identity,
                       extra_summary=guard.summary_warnings())
    summary = environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        def append_summary():
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write("```\n" + text + "\n```\n")
        append_side_effect(append_summary, "step summary", summary, err)
    return finish_verdict(verdict, err)


def update_timings(repo_root: Path, lock, *, profile: str, sources, out=print, err=print,
                   environ=None, source_text=None) -> int:
    """Fold observations into the committed `tests/parallel/timings.json` --
    the one working-tree write the tooling makes, executing no test (5.2)."""
    environ = os.environ if environ is None else environ
    sources = list(sources) or [timings_mod.history_path(environ)]
    missing = [str(s) for s in sources if not Path(s).exists()]
    if missing:
        raise TimingSourceError(f"--update-timings: no such source {missing}")
    inv = discover(repo_root)
    before = timings_mod.load(repo_root)
    for warning in before.warnings:
        err(f"warning: {warning}")
    skipped: list[str] = []
    obs = timings_mod.read_observations(sources, profile, warnings=skipped)
    for warning in skipped:
        err(f"warning: {warning}")
    after = timings_mod.update(before, obs, profile, inventory_unit_ids=inv.unit_ids(),
                               source=source_text)
    path = timings_mod.write(after, repo_root)
    out(f"{path}: folded {len(obs)} {profile} observations")
    return 0
