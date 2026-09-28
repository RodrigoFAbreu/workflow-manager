"""The run report and `results.json` (plan section 5.11, `D-Aggregation`).

First today's per-module lines (`ok  test_x.py   123.4s  Ran N tests  OK`,
the seconds summed over the module's chunks, frozen chunks counted under the
matrix module that judges them), then one block per failure or fault -- the
unit, the failing tests, the log, the last 6000 characters of output and a
one-line reproduction command -- then the shard summary.
"""

from __future__ import annotations

import hashlib
import shlex

from . import canonical_json
from .inventory import FROZEN_PREFIX, split_frozen_unit_id, split_host_unit_id

OUTPUT_TAIL = 6000
RUN_ALL = "python3 tests/run_all.py"

BARRIER_NOTE = (
    "write barrier applied: distribution/, migration/, src/ and tools/ are read-only until "
    "this run ends (saving a new file there, an editor's atomic save, or a git checkout/"
    "switch/stash/pull touching them fails with EACCES meanwhile); if the run is killed, "
    "`python3 tests/run_all.py --restore-barrier` restores them")

FAST_NOTE = ("run_all: --fast is a deprecated alias for a targeted --select of eight modules: "
             "targeted selection -- not a verification gate; gates run `python3 tests/run_all.py`")


def _q(text: str) -> str:
    return shlex.quote(text)


def reproduce(result, selection: dict) -> str:
    """The one-line command that re-runs exactly this chunk (5.11)."""
    units = result.chunk.units
    if units[0].startswith(FROZEN_PREFIX):
        return f"{RUN_ALL} --jobs 1 --whole-groups " + " ".join(f"--select {_q(u)}" for u in units)
    module, cls = split_host_unit_id(units[0])
    tests = selection.get(units[0])
    specs = [f"{module}::{cls}"] if not tests else [f"{module}::{cls}::{t}" for t in tests]
    return f"{RUN_ALL} --jobs 1 " + " ".join(f"--select {_q(s)}" for s in specs)


def status_of(result, judged: bool) -> str:
    if result.fault:
        return "ERR "
    if result.outcome == "not_run":
        return "SKIP"
    if result.outcome == "failed":
        return "fail" if judged else "FAIL"
    return "ok  "


def progress_line(result, done: int, total: int) -> str:
    width = len(str(max(total, done)))
    label = result.chunk.id if len(result.chunk.units) == 1 or result.kind == "frozen" \
        else result.chunk.units[0]
    tag = {"passed": "ok  ", "failed": "FAIL", "not_run": "SKIP"}.get(result.outcome, "ERR ")
    return (f"[{done:>{width}}/{total}] {tag} {result.phase:<2} {label} "
            f"{result.duration:.1f}s")


def _module_of(result, matrix: dict) -> str:
    unit = result.chunk.units[0]
    if unit.startswith(FROZEN_PREFIX):
        version, fixture, _, _ = split_frozen_unit_id(unit)
        for host, row in matrix.items():
            if tuple(row) == (version, fixture):
                return split_host_unit_id(host)[0]
        return f"frozen:{version}/{fixture}"
    return split_host_unit_id(unit)[0]


def module_lines(results, matrix: dict, judged) -> list[str]:
    """Today's columns, one line per host module."""
    modules: dict[str, dict] = {}
    for result in results:
        entry = modules.setdefault(_module_of(result, matrix),
                                   {"seconds": 0.0, "ran": 0, "fail": 0, "error": 0,
                                    "skipped": 0, "bad": False})
        entry["seconds"] += result.duration
        record = result.record if result.kind == "host" else None
        if record is not None:
            entry["ran"] += record.get("tests_run", 0)
            outcomes = record.get("outcomes", {}).values()
            entry["fail"] += sum(1 for o in outcomes if o == "fail")
            entry["error"] += sum(1 for o in outcomes if o in ("error", "unexpected_success"))
            entry["skipped"] += len(record.get("skipped", {}))
        if result.fault or result.outcome == "not_run" or (
                result.outcome == "failed" and not judged(result)):
            entry["bad"] = True
    lines = []
    for module in sorted(modules):
        entry = modules[module]
        if entry["bad"] or entry["fail"] or entry["error"]:
            status, summary = "FAIL", (f"Ran {entry['ran']} tests  FAILED (failures="
                                       f"{entry['fail']}, errors={entry['error']})")
        else:
            status = "ok  "
            summary = f"Ran {entry['ran']} tests  " + (
                "OK" if not entry["skipped"] else f"OK (skipped={entry['skipped']})")
        lines.append(f"{status} {module:<36} {entry['seconds']:6.1f}s  {summary}")
    return lines


def _tail(result) -> str:
    text = ""
    if result.log:
        try:
            with open(result.log, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            text = ""
    if not text and result.record:
        text = result.record.get("output_tail") or result.record.get("output") or ""
    return text[-OUTPUT_TAIL:]


def failure_block(result, selection: dict, *, log_label: str | None = None) -> str:
    rule = "=" * 70
    lines = [rule, f"{result.chunk.id}  ({result.phase}, shard {result.shard})", rule]
    if len(result.chunk.units) > 1 or result.kind == "frozen":
        lines += [f"  unit: {u}" for u in result.chunk.units]
    if result.fault:
        lines.append(f"  infrastructure fault: {result.fault}")
    elif result.outcome == "not_run":
        lines.append(f"  not run: {result.detail}")
    for name in (result.record or {}).get("failing", []):
        lines.append(f"  failing: {name}")
    lines.append(f"  log: {log_label or result.log or '(none)'}")
    lines.append(f"  reproduce: {reproduce(result, selection)}")
    tail = _tail(result)
    if tail:
        lines.append(tail)
    return "\n".join(lines)


def results_doc(results, verdict: int, frozen_classes: dict, identity: dict | None = None) -> str:
    """`results.json`: per-unit outcome, duration, test ids and failing ids,
    plus the run's evidence identity."""
    doc = {"schema_version": 1, "verdict": verdict,
           "units": unit_entries(results, frozen_classes)}
    if identity is not None:
        doc["identity"] = identity
    return canonical_json(doc)


def unit_entries(results, frozen_classes: dict) -> dict:
    units = {}
    for result in results:
        record = result.record or {}
        window = [result.started_at, result.ended_at]
        if result.kind == "host":
            unit = result.chunk.units[0]
            units[unit] = {"outcome": result.outcome, "duration": round(result.duration, 3),
                           "phase": result.phase, "chunk": result.chunk.id,
                           "shard": result.shard, "window": window,
                           "tests": record.get("ran", []), "failing": record.get("failing", []),
                           "tmp_residue": list(result.tmp_residue)}
            continue
        failing = record.get("failing", [])
        for unit in result.chunk.units:
            version, _, suite, cls = split_frozen_unit_id(unit)
            methods = frozen_classes.get(version, {}).get(suite, {}).get(cls, [])
            units[unit] = {"outcome": result.outcome, "duration": round(result.duration, 3),
                           "phase": result.phase, "chunk": result.chunk.id,
                           "shard": result.shard, "window": window, "ran": record.get("ran"),
                           "tests": [f"{unit}::{m}" for m in methods],
                           # `Class.test`, or `module.Class` for a setUpClass error.
                           "failing": [f for f in failing
                                       if cls in (f.split(".", 1)[0], f.rsplit(".", 1)[-1])],
                           "tmp_residue": list(result.tmp_residue)}
    return dict(sorted(units.items()))


def evidence_identity(plan: dict, results, frozen_classes: dict, *, head: str,
                      inventory_unit_ids, scope: str) -> dict:
    """What a run's evidence is evidence *of*, so a later gate can cite it
    instead of re-running it (the serial/single-shard evidence policy,
    `docs/ARCHITECTURE.md`'s "Verification execution"):

    - `selection`: `full` when the plan selects every inventory unit whole,
      else `targeted` -- a targeted run is never full-suite evidence;
    - `scope`: the mode and its shape (`local --jobs N`, `shard K of N`,
      `aggregate of N shards`);
    - `head`, `tree_digest`: the revision, and the exact tree (which a
      documentation-only change also moves);
    - `selection_digest`: the selected unit set;
    - `tests`, `tests_digest`: the test ids the reported units hold, sorted
      (a host unit's from its record, a frozen unit's from the inventory
      whatever its outcome) -- which also moves when a test method is added
      to an existing class, where `selection_digest` does not. Neither digest
      says the run was green: evidence cites the verdict separately."""
    units = unit_entries(results, frozen_classes)
    tests = sorted({t for entry in units.values() for t in entry["tests"]})
    selection = plan["selection"]
    full = set(selection) == set(inventory_unit_ids) and \
        all(v is None for v in selection.values())
    return {"selection": "full" if full else "targeted", "scope": scope, "head": head,
            "tree_digest": plan["tree_digest"], "selection_digest": plan["selection_digest"],
            "selected_units": len(selection), "reported_units": len(units),
            "tests": len(tests),
            "tests_digest": hashlib.sha256("\n".join(tests).encode("utf-8")).hexdigest(),
            "profile": plan["profile"], "n": plan["n"]}


def identity_line(identity: dict) -> str:
    return (f"evidence: {identity['selection']} selection, {identity['scope']}, "
            f"head {identity['head'] or '(unborn)'}, {identity['reported_units']}/"
            f"{identity['selected_units']} units, {identity['tests']} tests, "
            f"selection_digest {identity['selection_digest']}, "
            f"tests_digest {identity['tests_digest']}, tree_digest {identity['tree_digest']}")


def shard_summary(plan: dict, results, *, wall: float, drifted, extra=()) -> list[str]:
    """`n`, predicted vs actual loads, A0's window, every chunk's `TMPDIR`
    residue (5.9: reported against its chunk before it is removed), phase B,
    and the timing lists the plan and the run produced."""
    predicted = plan["predicted"]
    lines = [f"shards: n={plan['n']} (profile {plan['profile']}), "
             f"total work predicted {predicted['total_work']:.1f}s, "
             f"critical path {predicted['critical_path']:.1f}s ({predicted['critical_path_chunk']})"]
    if predicted.get("critical_path_warning"):
        lines.append(f"  warning: {predicted['critical_path_warning']}")
    actual: dict[int, float] = {}
    for result in results:
        if result.phase in ("A", "A0"):
            actual[result.chunk.shard_index] = actual.get(result.chunk.shard_index, 0.0) \
                + result.duration
    for index, shard in enumerate(plan["shards"]):
        lines.append(f"  shard {index}: predicted {shard['load']:.1f}s, "
                     f"actual {actual.get(index, 0.0):.1f}s")
    a0 = [r for r in results if r.phase == "A0" and r.started_at]
    if a0:
        start, end = min(r.started_at for r in a0), max(r.ended_at for r in a0)
        lines.append(f"  A0 (exclusive, alone): {len(a0)} chunk(s), window {end - start:.1f}s "
                     f"[{start:.3f} .. {end:.3f}]")
    residue = sorted((r.chunk.id, r.tmp_residue) for r in results if r.tmp_residue)
    if residue:
        lines.append(f"  TMPDIR residue (removed): {len(residue)} chunk(s)")
        lines += [f"    {chunk}: {', '.join(paths)}" for chunk, paths in residue]
    else:
        lines.append("  TMPDIR residue: none")
    phase_b = [r for r in results if r.phase == "B" and r.started_at]
    if phase_b:
        start, end = min(r.started_at for r in phase_b), max(r.ended_at for r in phase_b)
        lines.append(f"  phase B: {len(phase_b)} matrix host class(es), {end - start:.1f}s")
    terms = ", ".join(f"{k} {v:.1f}s" for k, v in predicted["makespan"].items())
    lines.append(f"  predicted makespan: {terms}; actual wall {wall:.1f}s")
    timing = plan.get("timing", {})
    for label, items in (("defaulted", sorted(timing.get("defaulted", {}))),
                         ("orphaned", timing.get("orphaned", [])), ("drifted", drifted)):
        if items:
            shown = ", ".join(items[:10]) + (f", ... ({len(items)} in all)"
                                             if len(items) > 10 else "")
            lines.append(f"  timing {label}: {shown}")
    for warning in timing.get("warnings", []):
        lines.append(f"  timing warning: {warning}")
    lines.extend(extra)
    return lines
