"""Timing history: format, lifecycle and estimates (plan section 5.2,
`D-Timing-History`).

`<repo_root>/tests/parallel/timings.json` holds the committed estimates: per
profile (`local`, `ci`) and per atomic unit, the median of the most recent
observed durations (at most 5), rounded to 0.1 s; per profile and fixture the
fixed cost of one frozen execution group; per CI job kind its setup time.

Timing data only ever shapes *how* a selection is scheduled. Nothing here is
an input to discovery or selection (INV-2), no Workflow module reads it, and
a missing, corrupt or adversarial file degrades every estimate to a default
with a warning -- never to a refusal, never to a smaller selection.

Observed history (never committed) is JSON lines, one per executed unit:
`unit`, `profile`, `seconds`, `outcome`, `tree_digest`, `utc`. A line that
carries `fixture` in place of `unit` is a group-overhead observation.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import canonical_json, strict_json_loads
from .inventory import FROZEN_PREFIX, split_frozen_unit_id, split_host_unit_id

SCHEMA_VERSION = 1
PROFILES = ("local", "ci")
CI_JOB_KINDS = ("plan", "shard", "aggregate")
#: Samples a unit estimate is the median of.
MAX_SAMPLES = 5
#: A stored duration above this is not a measurement; it is dropped with a
#: warning and the unit falls back to the new-unit rule.
MAX_SECONDS = 24 * 3600.0
#: Drift is advisory; below this absolute difference it is not reported, so
#: sub-second classes do not drift on every run.
DRIFT_FLOOR_SECONDS = 1.0
PASS = "pass"

#: How a unit's estimate was obtained (5.2 "New unit"), in fallback order.
MEASURED, OTHER_PROFILE, GROUP_MEDIAN, DEFAULT = (
    "measured", "other_profile", "group_median", "default")

_UNITTEST_RAN_RE = re.compile(r"^Ran (\d+) tests? in ([0-9.]+)s", re.MULTILINE)


def timings_path(repo_root: Path) -> Path:
    return Path(repo_root) / "tests" / "parallel" / "timings.json"


def history_path(environ) -> Path:
    """`$XDG_CACHE_HOME/workflow-manager/test-timings.jsonl` (default
    `~/.cache/...`) -- outside every checkout (5.6)."""
    base = environ.get("XDG_CACHE_HOME") or str(Path(environ.get("HOME", "~")) / ".cache")
    return Path(base).expanduser() / "workflow-manager" / "test-timings.jsonl"


# -- the committed file ------------------------------------------------------------

@dataclass(frozen=True)
class UnitTiming:
    seconds: float
    samples: int


@dataclass(frozen=True)
class Timings:
    #: profile -> unit id -> estimate
    units: dict[str, dict[str, UnitTiming]] = field(default_factory=dict)
    #: profile -> free-text provenance of that profile's numbers
    sources: dict[str, str] = field(default_factory=dict)
    #: profile -> fixture -> seconds
    group_overhead: dict[str, dict[str, float]] = field(default_factory=dict)
    #: CI job kind -> seconds
    ci_job_setup: dict[str, float] = field(default_factory=dict)
    #: What `load` had to ignore, for the report. Never serialized.
    warnings: tuple[str, ...] = ()

    def profile_units(self, profile: str) -> dict[str, UnitTiming]:
        return self.units.get(profile, {})

    def to_json(self) -> str:
        return canonical_json({
            "schema_version": SCHEMA_VERSION,
            "profiles": {
                profile: {
                    "units": {unit: {"seconds": t.seconds, "samples": t.samples}
                              for unit, t in sorted(self.units.get(profile, {}).items())},
                    "source": self.sources.get(profile, ""),
                }
                for profile in PROFILES if profile in self.units or profile in self.sources
            },
            "group_overhead_seconds": {p: dict(sorted(self.group_overhead[p].items()))
                                       for p in PROFILES if p in self.group_overhead},
            "ci_job_setup_seconds": dict(sorted(self.ci_job_setup.items())),
        })


def _valid_seconds(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 <= value <= MAX_SECONDS)


def load(repo_root: Path) -> Timings:
    """The committed estimates, or empty `Timings` carrying a warning when the
    file is missing, unreadable, corrupt or of another schema. Individual
    invalid values (negative, NaN, absurdly large, wrong type) are dropped with
    a warning each; everything valid is kept."""
    path = timings_path(repo_root)
    if not path.exists():
        return Timings(warnings=(f"{path}: no timing file; every estimate is a default",))
    try:
        raw = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Timings(warnings=(f"{path}: unreadable ({exc}); every estimate is a default",))
    return parse(raw, source=str(path))


def parse(raw, *, source: str = "timings.json") -> Timings:
    def ignored(reason: str) -> Timings:
        return Timings(warnings=(f"{source}: {reason}; every estimate is a default",))

    if not isinstance(raw, dict):
        return ignored("top level is not an object")
    if raw.get("schema_version") != SCHEMA_VERSION or isinstance(raw.get("schema_version"), bool):
        return ignored(f"schema_version {raw.get('schema_version')!r} is not {SCHEMA_VERSION}")
    warnings: list[str] = []
    units: dict[str, dict[str, UnitTiming]] = {}
    sources: dict[str, str] = {}
    profiles = raw.get("profiles", {})
    if not isinstance(profiles, dict):
        return ignored("profiles is not an object")
    for profile in sorted(profiles):
        body = profiles[profile]
        if profile not in PROFILES or not isinstance(body, dict) \
                or not isinstance(body.get("units", {}), dict):
            warnings.append(f"{source}: profile {profile!r} ignored")
            continue
        kept = {}
        for unit in sorted(body.get("units", {})):
            entry = body["units"][unit]
            samples = entry.get("samples") if isinstance(entry, dict) else None
            seconds = entry.get("seconds") if isinstance(entry, dict) else None
            if not _valid_seconds(seconds) or isinstance(samples, bool) \
                    or not isinstance(samples, int) or not 1 <= samples <= MAX_SAMPLES:
                warnings.append(f"{source}: {profile} estimate for {unit} ignored: {entry!r}")
                continue
            kept[unit] = UnitTiming(float(seconds), samples)
        units[profile] = kept
        if isinstance(body.get("source"), str):
            sources[profile] = body["source"]

    group_overhead: dict[str, dict[str, float]] = {}
    overhead = raw.get("group_overhead_seconds", {})
    for profile in sorted(overhead) if isinstance(overhead, dict) else ():
        values = overhead[profile]
        if profile not in PROFILES or not isinstance(values, dict):
            warnings.append(f"{source}: group overhead for {profile!r} ignored")
            continue
        group_overhead[profile] = {}
        for fixture in sorted(values):
            if _valid_seconds(values[fixture]):
                group_overhead[profile][fixture] = float(values[fixture])
            else:
                warnings.append(f"{source}: {profile} group overhead for {fixture} ignored: "
                                f"{values[fixture]!r}")

    ci_job_setup: dict[str, float] = {}
    setup = raw.get("ci_job_setup_seconds", {})
    for kind in sorted(setup) if isinstance(setup, dict) else ():
        if kind in CI_JOB_KINDS and _valid_seconds(setup[kind]):
            ci_job_setup[kind] = float(setup[kind])
        else:
            warnings.append(f"{source}: CI job setup {kind!r} ignored: {setup[kind]!r}")
    return Timings(units, sources, group_overhead, ci_job_setup, tuple(warnings))


# -- estimates ---------------------------------------------------------------------

@dataclass(frozen=True)
class Estimate:
    seconds: float
    source: str  # MEASURED, OTHER_PROFILE, GROUP_MEDIAN or DEFAULT


def estimate_group(unit_id: str) -> str:
    """The new-unit rule's "same group": the module of a host unit, the
    `version/fixture/suite` of a frozen one."""
    if unit_id.startswith(FROZEN_PREFIX):
        version, fixture, suite, _ = split_frozen_unit_id(unit_id)
        return f"frozen:{version}/{fixture}/{suite}"
    return "host:" + split_host_unit_id(unit_id)[0]


def other_profile(profile: str) -> str:
    return "ci" if profile == "local" else "local"


def profile_ratio(timings: Timings, profile: str, known_units) -> float | None:
    """Median of active/other over units measured in both profiles (and still
    in the inventory); `None` when no such unit exists."""
    active = timings.profile_units(profile)
    other = timings.profile_units(other_profile(profile))
    ratios = [active[u].seconds / other[u].seconds for u in sorted(known_units)
              if u in active and u in other and other[u].seconds > 0]
    return statistics.median(ratios) if ratios else None


def estimate_units(timings: Timings, profile: str, unit_ids, inventory_unit_ids,
                   default_unit_seconds: float) -> dict[str, Estimate]:
    """An estimate for every unit of `unit_ids`, by 5.2's order: the active
    profile's value; else the other profile's value x the profile ratio; else
    the median of the active profile's known units of the same group; else
    `default_unit_seconds`. Only units still in the inventory count as known --
    an orphaned entry informs nothing."""
    inventory_unit_ids = set(inventory_unit_ids)
    active = {u: t for u, t in timings.profile_units(profile).items() if u in inventory_unit_ids}
    other = {u: t for u, t in timings.profile_units(other_profile(profile)).items()
             if u in inventory_unit_ids}
    ratio = profile_ratio(timings, profile, inventory_unit_ids)
    by_group: dict[str, list[float]] = {}
    for unit in sorted(active):
        by_group.setdefault(estimate_group(unit), []).append(active[unit].seconds)

    out = {}
    for unit in sorted(unit_ids):
        if unit in active:
            out[unit] = Estimate(active[unit].seconds, MEASURED)
        elif unit in other and ratio is not None:
            out[unit] = Estimate(round(other[unit].seconds * ratio, 3), OTHER_PROFILE)
        elif estimate_group(unit) in by_group:
            out[unit] = Estimate(statistics.median(by_group[estimate_group(unit)]), GROUP_MEDIAN)
        else:
            out[unit] = Estimate(float(default_unit_seconds), DEFAULT)
    return out


def group_overhead(timings: Timings, profile: str, fixture: str, default: float) -> float:
    return timings.group_overhead.get(profile, {}).get(fixture, float(default))


def orphaned(timings: Timings, inventory_unit_ids) -> list[str]:
    """Estimated units (any profile) no longer in the inventory: ignored by
    every estimate, listed in the report, dropped by `update`."""
    present = set(inventory_unit_ids)
    return sorted({u for p in timings.units.values() for u in p if u not in present})


def drifted(estimates: dict[str, float], observed: dict[str, float]) -> list[str]:
    """Units whose observed duration is outside `[0.5x, 2x]` of the estimate
    (and more than `DRIFT_FLOOR_SECONDS` away from it). Advisory only."""
    out = []
    for unit in sorted(set(estimates) & set(observed)):
        est, obs = estimates[unit], observed[unit]
        if abs(obs - est) > DRIFT_FLOOR_SECONDS and not 0.5 * est <= obs <= 2 * est:
            out.append(unit)
    return out


# -- observations and refresh ------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    """One observed duration. Exactly one of `unit` and `fixture` is set; a
    `fixture` observation is the fixed cost of one frozen execution group."""
    profile: str
    seconds: float
    outcome: str
    utc: str
    unit: str | None = None
    fixture: str | None = None
    tree_digest: str | None = None

    def to_json_line(self) -> str:
        doc = {"profile": self.profile, "seconds": self.seconds, "outcome": self.outcome,
               "utc": self.utc, "tree_digest": self.tree_digest}
        doc["unit" if self.unit is not None else "fixture"] = self.unit or self.fixture
        return json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _utc(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


def _from_json_line(obj, profile: str | None) -> Observation | None:
    if not isinstance(obj, dict) or not _valid_seconds(obj.get("seconds")):
        return None
    if (obj.get("unit") is None) == (obj.get("fixture") is None):
        return None
    return Observation(profile=obj.get("profile") if profile is None else profile,
                       seconds=float(obj["seconds"]), outcome=str(obj.get("outcome")),
                       utc=str(obj.get("utc", "")), unit=obj.get("unit"),
                       fixture=obj.get("fixture"), tree_digest=obj.get("tree_digest"))


def observations_from_record(obj, profile: str) -> list[Observation]:
    """Observations from one result record: a host unit record
    (`parallel.unit`) or a frozen chunk record (`frozen_runs.FrozenRecord`).

    A host record of a *partial* run (selected methods only) says nothing about
    its class and yields nothing. A frozen record yields its group overhead
    (wall minus unittest's own `Ran ... in Xs`) and, for a one-class chunk, that
    class's duration; a multi-class chunk's time cannot be attributed per
    class, so it yields the overhead only."""
    if "unit" in obj and "tests_requested" in obj:
        if obj["tests_requested"] is not None:
            return []
        return [Observation(profile, round(float(obj["duration"]), 3),
                            PASS if obj["passed"] else "fail", _utc(obj["started_at"]),
                            unit=obj["unit"])]
    if "chunk_id" in obj:
        match = _UNITTEST_RAN_RE.search(obj.get("output") or "")
        if match is None:
            return []
        passed = obj["returncode"] == 0 and not obj["timed_out"] and obj["build_error"] is None
        outcome, utc, digest = (PASS if passed else "fail"), _utc(obj["started_at"]), \
            obj.get("tree_digest")
        class_seconds = float(match.group(2))
        out = [Observation(profile, round(max(0.0, obj["duration"] - class_seconds), 3),
                           outcome, utc, fixture=obj["fixture"], tree_digest=digest)]
        if len(obj["classes"]) == 1:
            unit = f"frozen:{obj['version']}/{obj['fixture']}/{obj['suite']}::{obj['classes'][0]}"
            out.append(Observation(profile, round(class_seconds, 3), outcome, utc, unit=unit,
                                   tree_digest=digest))
        return out
    return []


def read_observations(paths, profile: str | None = None) -> list[Observation]:
    """Observations from history files (`*.jsonl`) and result directories
    (every `*.record.json` and `*.jsonl` below them), in a deterministic
    order. `profile` overrides a history line's own profile and is required
    for records, which carry none."""
    out: list[Observation] = []
    for path in map(Path, paths):
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        for file in files:
            if file.name.endswith(".jsonl"):
                for line in file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        obs = _from_json_line(strict_json_loads(line), profile)
                        if obs is not None:
                            out.append(obs)
            elif file.name.endswith(".record.json"):
                if profile is None:
                    raise ValueError(f"{file}: a result record needs an explicit profile")
                out.extend(observations_from_record(
                    strict_json_loads(file.read_text(encoding="utf-8")), profile))
    return out


def update(timings: Timings, observations, profile: str, *, inventory_unit_ids=None,
           source: str | None = None) -> Timings:
    """Fold passing observations of `profile` into `timings`.

    A unit's new estimate is the median of its most recent `MAX_SAMPLES`
    values, rounded to 0.1 s. Only the median and sample count are stored, so
    when fewer than `MAX_SAMPLES` new values exist the stored estimate stands
    in for its own samples as the oldest values. A fixture's group overhead is
    the median of every new overhead observation, rounded to 0.01 s. When
    `inventory_unit_ids` is given, orphaned units are dropped from every
    profile. Failing observations are never folded."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    indexed = sorted(
        ((o.utc, i, o) for i, o in enumerate(observations)
         if o.profile == profile and o.outcome == PASS),
        key=lambda item: (item[0], item[1]))
    per_unit: dict[str, list[float]] = {}
    per_fixture: dict[str, list[float]] = {}
    for _, _, obs in indexed:
        if obs.unit is not None:
            per_unit.setdefault(obs.unit, []).append(obs.seconds)
        else:
            per_fixture.setdefault(obs.fixture, []).append(obs.seconds)

    units = {p: dict(v) for p, v in timings.units.items()}
    current = units.setdefault(profile, {})
    for unit, values in per_unit.items():
        values = values[-MAX_SAMPLES:]
        previous = current.get(unit)
        if previous is not None and len(values) < MAX_SAMPLES:
            values = [previous.seconds] * min(previous.samples, MAX_SAMPLES - len(values)) + values
        current[unit] = UnitTiming(round(statistics.median(values), 1), len(values))
    if inventory_unit_ids is not None:
        present = set(inventory_unit_ids)
        units = {p: {u: t for u, t in v.items() if u in present} for p, v in units.items()}

    overhead = {p: dict(v) for p, v in timings.group_overhead.items()}
    for fixture, values in per_fixture.items():
        overhead.setdefault(profile, {})[fixture] = round(statistics.median(values), 2)
    sources = dict(timings.sources)
    if source is not None:
        sources[profile] = source
    sources.setdefault(profile, "")
    return Timings(units, sources, overhead, dict(timings.ci_job_setup))


def write(timings: Timings, repo_root: Path) -> Path:
    path = timings_path(repo_root)
    path.write_text(timings.to_json(), encoding="utf-8")
    return path


def main(argv=None, repo_root: Path | None = None) -> int:
    """Fold observations into `<repo_root>/tests/parallel/timings.json` -- the
    function CP5's `run_all.py --update-timings` wraps. Executes no test."""
    parser = argparse.ArgumentParser(prog="python3 -m parallel.timings")
    parser.add_argument("--from", dest="sources", action="append", required=True, type=Path,
                        metavar="PATH", help="a history .jsonl file or a results directory")
    parser.add_argument("--profile", required=True, choices=PROFILES)
    parser.add_argument("--source", help="provenance text recorded for the profile")
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    args = parser.parse_args(argv)
    root = (args.repo_root or Path.cwd().parent).resolve()
    from .inventory import discover
    inv = discover(root)
    before = load(root)
    for warning in before.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    after = update(before, read_observations(args.sources, args.profile), args.profile,
                   inventory_unit_ids=inv.unit_ids(), source=args.source)
    print(write(after, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
