"""The planner: adaptive shard count, chunking and duration-balanced
assignment (plan sections 5.3 and 5.4; INV-1, INV-3).

`build_plan` turns a selection into `plan.json`: phase-A chunks (every
non-matrix host class, and every frozen class grouped by `(version, fixture,
suite)` and split when a group is too big) assigned to `n` shards by LPT, and
the selected matrix host classes (phase B) assigned separately. Coverage
never depends on timing: whatever the estimates, the plan is emitted only
after `verify_partition` proves the shards partition the selection exactly.
The same inputs always give the same bytes -- every order is sorted with an
explicit tie-break on ids, and no clock, randomness or process state enters.

Exclusive units are learnt only from `resources.load` (a `Resources`
argument), and chunks are written only through `plan_schema.ChunkDescriptor`.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from pathlib import Path

from . import canonical_json, strict_json_loads
from . import timings as timings_mod
from .inventory import FROZEN_PREFIX, Selection, split_frozen_unit_id
from .plan_schema import ChunkDescriptor, PlanSchemaError, shard_chunks
from .resources import Resources
from .tree import tree_digest as compute_tree_digest

SCHEMA_VERSION = 1
CONFIG_SCHEMA_VERSION = 1
PROFILES = timings_mod.PROFILES
_ROUND = 3

CONFIG_KEYS = {
    "target_shard_seconds": float,
    "min_shards": int,
    "local_max_shards": int,
    "ci_max_shards": int,
    "default_unit_seconds": float,
    "default_group_overhead_seconds": float,
    "split_threshold_ratio": float,
    "ci_account_concurrent_job_limit": int,
}


class PlanError(Exception):
    """The planner cannot emit, or a shard cannot accept, a plan."""


class ConfigError(PlanError):
    """`tests/parallel/config.json` is malformed."""


class PartitionError(PlanError):
    """INV-1: the shards do not partition the selection exactly."""


class PlanDigestMismatchError(PlanError):
    """A plan's recorded `plan_digest` does not match its content."""


class TreeDigestMismatchError(PlanError):
    """A plan was made for a different tree than this checkout's."""


class ExclusiveMatrixUnitError(PlanError):
    """A matrix host class holds a resource: phase B has no A0 and never lifts
    the barrier, so it could not run exclusively."""


# -- config --------------------------------------------------------------------------

def config_path(repo_root: Path) -> Path:
    return Path(repo_root) / "tests" / "parallel" / "config.json"


def load_config(repo_root: Path) -> dict:
    path = config_path(repo_root)
    try:
        raw = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{path}: unreadable: {exc}") from exc
    return parse_config(raw, source=str(path))


def parse_config(raw, *, source: str = "config.json") -> dict:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", *CONFIG_KEYS}:
        raise ConfigError(f"{source}: keys must be exactly schema_version and "
                          f"{sorted(CONFIG_KEYS)}")
    if raw["schema_version"] != CONFIG_SCHEMA_VERSION or isinstance(raw["schema_version"], bool):
        raise ConfigError(f"{source}: schema_version must be {CONFIG_SCHEMA_VERSION}")
    config = {}
    for key, kind in CONFIG_KEYS.items():
        value = raw[key]
        ok = not isinstance(value, bool) and (
            isinstance(value, int) if kind is int else isinstance(value, (int, float)))
        floor_ok = ok and math.isfinite(value) and (
            value >= 0 if key == "default_group_overhead_seconds" else value > 0)
        if not floor_ok:
            raise ConfigError(f"{source}: {key} must be a positive {kind.__name__}, got {value!r}")
        config[key] = kind(value)
    if config["ci_account_concurrent_job_limit"] < 2:
        raise ConfigError(f"{source}: ci_account_concurrent_job_limit must be at least 2")
    return config


# -- shard count (5.3) ------------------------------------------------------------------

def max_shards(config: dict, profile: str, cpu_count: int) -> int:
    if profile == "local":
        return max(1, min(config["local_max_shards"], cpu_count))
    return max(1, min(config["ci_max_shards"], config["ci_account_concurrent_job_limit"] - 1))


def shard_count(total: float, chunks: int, config: dict, profile: str, cpu_count: int,
                override: int | None = None) -> int:
    """`clamp(ceil(T / target), min_shards, max_shards(profile))`, never more
    than the chunk count; `override` (`--shards N`) is clamped to
    `[1, chunks]` instead. The hard cap wins over `min_shards`."""
    if chunks < 1:
        raise PlanError("nothing to plan: the selection has no phase-A chunk")
    if override is not None:
        return max(1, min(override, chunks))
    n_raw = math.ceil(total / config["target_shard_seconds"])
    n = min(max(n_raw, config["min_shards"]), max_shards(config, profile, cpu_count))
    return max(1, min(n, chunks))


# -- chunking and assignment (5.4) ---------------------------------------------------------

@dataclass(frozen=True)
class _Chunk:
    id: str
    units: tuple[str, ...]
    estimate: float
    resources: tuple[str, ...] = ()


def lpt(items, bins: int) -> list[list]:
    """Longest-processing-time-first: `items` are `(estimate, id, payload)`;
    sorted by `(-estimate, id)`, each goes to the bin with the smallest
    `(load, item count, bin index)`. The item count only breaks exact load
    ties, so a bin is never left empty while `bins <= len(items)`; LPT's 4/3
    bound holds for any tie-break."""
    loads = [0.0] * bins
    out: list[list] = [[] for _ in range(bins)]
    for estimate, item_id, payload in sorted(items, key=lambda item: (-item[0], item[1])):
        index = min(range(bins), key=lambda i: (loads[i], len(out[i]), i))
        out[index].append((estimate, item_id, payload))
        loads[index] += estimate
    return out


def _round(value: float) -> float:
    return round(value, _ROUND)


def _frozen_chunks(group: str, classes: list[tuple[str, float]], overhead: float,
                   threshold: float, whole_groups: bool) -> list[_Chunk]:
    """One `(version, fixture, suite)` group as `k` chunks, each paying the
    group overhead once (5.4 step 2)."""
    group_estimate = sum(e for _, e in classes) + overhead
    k = 1 if whole_groups or group_estimate <= threshold \
        else min(len(classes), math.ceil(group_estimate / threshold))
    bins = lpt([(e, u, u) for u, e in classes], k)
    return [_Chunk(f"{group}#{i + 1}", tuple(sorted(u for _, u, _ in members)),
                   _round(sum(e for e, _, _ in members) + overhead))
            for i, members in enumerate(bins)]


def make_chunks(unit_ids, estimates: dict[str, float], *, profile: str, config: dict,
                timings: timings_mod.Timings, resources: Resources,
                whole_groups: bool = False) -> list[_Chunk]:
    """Phase-A chunks: a host class is its own chunk, never split; frozen
    classes chunk per `(version, fixture, suite)` group."""
    threshold = config["split_threshold_ratio"] * config["target_shard_seconds"]
    chunks = []
    groups: dict[tuple[str, str, str], list[tuple[str, float]]] = {}
    for unit in sorted(unit_ids):
        if unit.startswith(FROZEN_PREFIX):
            version, fixture, suite, _ = split_frozen_unit_id(unit)
            groups.setdefault((version, fixture, suite), []).append((unit, estimates[unit]))
        else:
            chunks.append(_Chunk(unit, (unit,), _round(estimates[unit]),
                                 resources.resources_of(unit)))
    for (version, fixture, suite), classes in sorted(groups.items()):
        overhead = timings_mod.group_overhead(timings, profile, fixture,
                                              config["default_group_overhead_seconds"])
        chunks.extend(_frozen_chunks(f"frozen:{version}/{fixture}/{suite}", classes, overhead,
                                     threshold, whole_groups))
    return chunks


def _assign(chunks: list[_Chunk], n: int) -> list[list[_Chunk]]:
    """LPT over `n` shards; within a shard, exclusive chunks first (5.4 step
    4), each part in placement order."""
    shards = []
    for members in lpt([(c.estimate, c.id, c) for c in chunks], n):
        placed = [c for _, _, c in members]
        shards.append([c for c in placed if c.resources] + [c for c in placed if not c.resources])
    return shards


def _shard_docs(shards: list[list[_Chunk]]) -> list[dict]:
    return [{"chunks": [ChunkDescriptor(c.id, index, c.units, c.estimate, c.resources).to_json()
                        for c in shard],
             "load": _round(sum(c.estimate for c in shard))}
            for index, shard in enumerate(shards)]


# -- INV-1 --------------------------------------------------------------------------------

def verify_partition(plan: dict) -> None:
    """INV-1 over a plan document: every shard is non-empty; phase-A and
    phase-B chunks together hold every selected unit exactly once and nothing
    else; a frozen chunk holds one group's classes, a host chunk one class."""
    try:
        phase_a = shard_chunks(plan)
        phase_b = shard_chunks(plan["phase_b"])
    except (PlanSchemaError, KeyError, TypeError) as exc:
        raise PartitionError(f"plan chunk lists are malformed: {exc}") from exc
    if len(phase_a) != plan.get("n") or any(not shard for shard in phase_a + phase_b):
        raise PartitionError(f"plan has {len(phase_a)} shards for n={plan.get('n')!r}, "
                             f"or an empty shard")
    seen: dict[str, str] = {}
    duplicated = []
    for chunk in (c for shard in phase_a + phase_b for c in shard):
        frozen = [u for u in chunk.units if u.startswith(FROZEN_PREFIX)]
        if frozen and (len(frozen) != len(chunk.units)
                       or len({split_frozen_unit_id(u)[:3] for u in frozen}) != 1):
            raise PartitionError(f"chunk {chunk.id} mixes execution groups: {chunk.units}")
        if not frozen and len(chunk.units) != 1:
            raise PartitionError(f"host chunk {chunk.id} holds {len(chunk.units)} classes")
        for unit in chunk.units:
            if unit in seen:
                duplicated.append(f"{unit} (chunks {seen[unit]} and {chunk.id})")
            seen[unit] = chunk.id
    selected = set(plan.get("selection", {}))
    missing = sorted(selected - set(seen))
    extra = sorted(set(seen) - selected)
    if duplicated or missing or extra:
        raise PartitionError(f"shards do not partition the selection: duplicated {duplicated}, "
                             f"missing {missing}, not selected {extra}")


# -- the plan -------------------------------------------------------------------------------

def plan_digest(plan: dict) -> str:
    body = {k: v for k, v in plan.items() if k != "plan_digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def selection_doc(selection: Selection) -> dict:
    return {unit: None if tests is None else list(tests)
            for unit, tests in sorted(selection.units.items())}


def build_plan(selection: Selection, *, inventory_unit_ids, matrix_units, timings, config: dict,
               profile: str, tree_digest: str, resources: Resources, shards: int | None = None,
               cpu_count: int | None = None, phase_b_workers: int | None = None,
               whole_groups: bool = False) -> dict:
    """The plan for `selection` (5.4 step 6), verified by INV-1 before it is
    returned.

    `inventory_unit_ids` is the full inventory (orphans and group medians are
    judged against it); `matrix_units` the matrix host class ids (phase B).
    `cpu_count` bounds the local shard count; `phase_b_workers` is the CI
    aggregate job's pool (default `cpu_count`) -- locally phase B runs on the
    same `n` workers as phase A."""
    if profile not in PROFILES:
        raise PlanError(f"unknown profile {profile!r}")
    cpu_count = cpu_count or os.cpu_count() or 1
    matrix_units = set(matrix_units)
    unit_ids = selection.unit_ids()
    estimates = timings_mod.estimate_units(timings, profile, unit_ids, inventory_unit_ids,
                                           config["default_unit_seconds"])
    seconds = {u: e.seconds for u, e in estimates.items()}

    phase_a_units = [u for u in unit_ids if u not in matrix_units]
    phase_b_units = [u for u in unit_ids if u in matrix_units]
    chunks = make_chunks(phase_a_units, seconds, profile=profile, config=config, timings=timings,
                         resources=resources, whole_groups=whole_groups)
    total = _round(sum(c.estimate for c in chunks))
    n = shard_count(total, len(chunks), config, profile, cpu_count, shards)
    phase_a = _assign(chunks, n)

    b_chunks = [_Chunk(u, (u,), _round(seconds[u]), resources.resources_of(u))
                for u in phase_b_units]
    exclusive_b = sorted(c.id for c in b_chunks if c.resources)
    if exclusive_b:
        raise ExclusiveMatrixUnitError(
            f"matrix host classes cannot be declared exclusive (phase B runs them "
            f"concurrently, under the barrier): {exclusive_b}")
    workers = n if profile == "local" else (phase_b_workers or cpu_count)
    workers = max(1, min(workers, len(b_chunks))) if b_chunks else 0
    phase_b = _assign(b_chunks, workers) if b_chunks else []

    critical = max(chunks, key=lambda c: (c.estimate, c.id))
    target = config["target_shard_seconds"]
    phase_b_makespan = _round(max((sum(c.estimate for c in s) for s in phase_b), default=0.0))
    if profile == "local":
        exclusive = _round(sum(c.estimate for s in phase_a for c in s if c.resources))
        shared = _round(max(sum(c.estimate for c in s if not c.resources) for s in phase_a))
        terms = {"exclusive_a0": exclusive, "phase_a": shared, "phase_b": phase_b_makespan}
    else:
        setup = {kind: timings.ci_job_setup.get(kind, 0.0) for kind in timings_mod.CI_JOB_KINDS}
        terms = {"plan_job": _round(setup["plan"]),
                 "shard_job": _round(setup["shard"] + max(sum(c.estimate for c in s)
                                                          for s in phase_a)),
                 "aggregate_job": _round(setup["aggregate"] + phase_b_makespan)}
    terms["total"] = _round(sum(terms.values()))

    plan = {
        "schema_version": SCHEMA_VERSION,
        "tree_digest": tree_digest,
        "profile": profile,
        "selection": selection_doc(selection),
        "selection_digest": hashlib.sha256(selection.to_json().encode("utf-8")).hexdigest(),
        "partial_frozen": selection.partial_frozen,
        "bounds": {**config, "cpu_count": cpu_count,
                   "max_shards": max_shards(config, profile, cpu_count),
                   "shards_override": shards, "whole_groups": whole_groups},
        "n": n,
        "shards": _shard_docs(phase_a),
        "phase_b": {"workers": workers, "shards": _shard_docs(phase_b)},
        "predicted": {
            "total_work": total,
            "critical_path": critical.estimate,
            "critical_path_chunk": critical.id,
            "critical_path_warning": (
                f"chunk {critical.id} ({critical.estimate}s: {', '.join(critical.units)}) "
                f"exceeds target_shard_seconds {target}s and bounds wall time"
                if critical.estimate > target else None),
            "makespan": terms,
        },
        "timing": {
            "defaulted": {u: e.source for u, e in estimates.items()
                          if e.source != timings_mod.MEASURED},
            "orphaned": timings_mod.orphaned(timings, inventory_unit_ids),
            "warnings": list(timings.warnings),
        },
    }
    verify_partition(plan)
    plan["plan_digest"] = plan_digest(plan)
    return plan


def plan_checkout(repo_root: Path, inv, selection: Selection, *, profile: str, **options) -> dict:
    """`build_plan` over `repo_root`'s own `config.json`, `timings.json` and
    `resources.json`, for an inventory `inv` discovered from the same
    checkout (its `tree_digest` is the plan's)."""
    from . import resources as resources_mod
    return build_plan(
        selection, inventory_unit_ids=inv.unit_ids(),
        matrix_units=inv.frozen.matrix if inv.frozen is not None else (),
        timings=timings_mod.load(repo_root), config=load_config(repo_root), profile=profile,
        tree_digest=inv.tree_digest, resources=resources_mod.load(repo_root, list(inv.host)),
        **options)


def to_json(plan: dict) -> str:
    return canonical_json(plan)


def write_plan(plan: dict, path: Path) -> Path:
    path = Path(path)
    path.write_text(to_json(plan), encoding="utf-8")
    return path


def load_plan(path: Path, repo_root: Path) -> dict:
    """A plan a shard may run: its `plan_digest` matches its content, its
    `tree_digest` is this checkout's, and it still partitions its own
    selection (INV-1, re-checked before anything runs)."""
    try:
        plan = strict_json_loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"{path}: unreadable plan: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != SCHEMA_VERSION:
        raise PlanError(f"{path}: not a schema-{SCHEMA_VERSION} plan")
    recorded, actual = plan.get("plan_digest"), plan_digest(plan)
    if recorded != actual:
        raise PlanDigestMismatchError(f"{path}: plan_digest {recorded!r} does not match its "
                                      f"content ({actual})")
    here = compute_tree_digest(repo_root)
    if plan.get("tree_digest") != here:
        raise TreeDigestMismatchError(f"{path}: plan is for tree {plan.get('tree_digest')!r}, "
                                      f"this checkout is {here}")
    verify_partition(plan)
    return plan
