"""Declared non-overlappable tests (plan section 5.8, `D-Resources`).

`<repo_root>/tests/parallel/resources.json` declares every resource and every
unit that needs one exclusively, and, optionally, the units whose orphaned
processes the leak check tolerates (`orphan_sources`, test-cleanup plan
5.4). This loader is the only reader of that file: the planner's placement,
`isolation`'s A0 ordering and barrier lifting, the verdict's orphan check
and the static lint all go through `load`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import strict_json_loads

SCHEMA_VERSION = 1

#: The one list of trees the write barrier covers (plan 5.9). A resource's
#: `paths` entries must each be exactly one of these -- the barrier locks and
#: lifts whole trees, so no sub-path form exists.
GUARDED_TREES = ("distribution/", "migration/", "src/", "tools/")


class ResourcesFileError(Exception):
    """`resources.json` is malformed or inconsistent with the host inventory."""


@dataclass(frozen=True)
class Resource:
    name: str
    paths: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class Exclusive:
    unit: str
    resources: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class OrphanSource:
    unit: str
    reason: str


@dataclass(frozen=True)
class Resources:
    resources: dict[str, Resource]
    exclusive: dict[str, Exclusive]
    #: unit id -> why its orphans are tolerated (host or frozen)
    orphan_sources: dict[str, OrphanSource] = field(default_factory=dict)

    def is_exclusive(self, unit_id: str) -> bool:
        return unit_id in self.exclusive

    def exclusive_units(self) -> tuple[str, ...]:
        return tuple(sorted(self.exclusive))

    def resources_of(self, unit_id: str) -> tuple[str, ...]:
        """Sorted names of the resources `unit_id` holds exclusively; empty for
        a shared unit."""
        entry = self.exclusive.get(unit_id)
        return entry.resources if entry else ()

    def trees_for(self, unit_id: str) -> tuple[str, ...]:
        """The union of the guarded trees of every resource `unit_id` holds --
        exactly what the barrier lifts while it runs; empty for a shared unit."""
        trees = set()
        for name in self.resources_of(unit_id):
            trees.update(self.resources[name].paths)
        return tuple(sorted(trees))


def resources_path(repo_root: Path) -> Path:
    return Path(repo_root) / "tests" / "parallel" / "resources.json"


def load(repo_root: Path, host_unit_ids, *, orphan_unit_ids=None) -> Resources:
    """Load and validate `<repo_root>/tests/parallel/resources.json`.

    `host_unit_ids` is the host inventory the caller already discovered; every
    exclusive unit must be one of them. `orphan_unit_ids` is the full
    inventory (host and frozen) `orphan_sources` keys are validated against;
    omitted, they are validated against the host ids, so a frozen declaration
    read by a caller that forgot it is refused. The loader never runs
    discovery."""
    path = resources_path(repo_root)
    try:
        raw = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResourcesFileError(f"{path}: unreadable: {exc}") from exc
    return parse(raw, host_unit_ids, source=str(path), orphan_unit_ids=orphan_unit_ids)


REQUIRED_KEYS = frozenset({"schema_version", "resources", "exclusive"})
OPTIONAL_KEYS = frozenset({"orphan_sources"})


def parse(raw, host_unit_ids, *, source: str = "resources.json",
          orphan_unit_ids=None) -> Resources:
    def fail(message: str):
        raise ResourcesFileError(f"{source}: {message}")

    if not isinstance(raw, dict) or not REQUIRED_KEYS <= set(raw) <= REQUIRED_KEYS | OPTIONAL_KEYS:
        fail("top level must be an object with exactly schema_version, resources, exclusive, "
             "and optionally orphan_sources")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != SCHEMA_VERSION:
        fail(f"schema_version must be {SCHEMA_VERSION}, got {raw['schema_version']!r}")
    if not isinstance(raw["resources"], dict) or not isinstance(raw["exclusive"], dict):
        fail("resources and exclusive must be objects")

    resources: dict[str, Resource] = {}
    owner_of_tree: dict[str, str] = {}
    for name in sorted(raw["resources"]):
        spec = raw["resources"][name]
        if not isinstance(spec, dict) or set(spec) != {"paths", "description"}:
            fail(f"resource {name!r} must be an object with exactly paths and description")
        paths = spec["paths"]
        if not isinstance(paths, list) or not paths:
            fail(f"resource {name!r}: paths must be a non-empty list")
        seen = set()
        for entry in paths:
            if not isinstance(entry, str):
                fail(f"resource {name!r}: path {entry!r} is not a string")
            if entry.startswith("/"):
                fail(f"resource {name!r}: path {entry!r} is absolute")
            if ".." in entry.split("/"):
                fail(f"resource {name!r}: path {entry!r} has a '..' component")
            if entry not in GUARDED_TREES:
                fail(f"resource {name!r}: path {entry!r} is not one of {GUARDED_TREES}")
            if entry in seen:
                fail(f"resource {name!r}: tree {entry!r} listed twice")
            seen.add(entry)
            if entry in owner_of_tree:
                fail(f"tree {entry!r} is claimed by both {owner_of_tree[entry]!r} and {name!r}")
            owner_of_tree[entry] = name
        description = spec["description"]
        if not isinstance(description, str) or not description.strip():
            fail(f"resource {name!r}: description must be a non-empty string")
        resources[name] = Resource(name, tuple(sorted(paths)), description)

    known_units = set(host_unit_ids)
    exclusive: dict[str, Exclusive] = {}
    for unit in sorted(raw["exclusive"]):
        spec = raw["exclusive"][unit]
        if not isinstance(spec, dict) or set(spec) != {"resources", "reason"}:
            fail(f"exclusive {unit!r} must be an object with exactly resources and reason")
        held = spec["resources"]
        if not isinstance(held, list) or not held:
            fail(f"exclusive {unit!r}: resources must be a non-empty list")
        for name in held:
            if not isinstance(name, str):
                fail(f"exclusive {unit!r}: resource {name!r} is not a string")
        if len(set(map(str, held))) != len(held):
            fail(f"exclusive {unit!r}: a resource is listed twice")
        for name in held:
            if name not in resources:
                fail(f"exclusive {unit!r}: names undeclared resource {name!r}")
        reason = spec["reason"]
        if not isinstance(reason, str) or not reason.strip():
            fail(f"exclusive {unit!r}: reason must be a non-empty string")
        if unit not in known_units:
            fail(f"exclusive unit {unit!r} is not in the host inventory")
        exclusive[unit] = Exclusive(unit, tuple(sorted(held)), reason)

    raw_sources = raw.get("orphan_sources", {})
    if not isinstance(raw_sources, dict):
        fail("orphan_sources must be an object")
    inventory = set(known_units if orphan_unit_ids is None else orphan_unit_ids)
    orphan_sources: dict[str, OrphanSource] = {}
    for unit in sorted(raw_sources):
        spec = raw_sources[unit]
        if not isinstance(spec, dict) or set(spec) != {"reason"}:
            fail(f"orphan_sources {unit!r} must be an object with exactly reason")
        reason = spec["reason"]
        if not isinstance(reason, str) or not reason.strip():
            fail(f"orphan_sources {unit!r}: reason must be a non-empty string")
        if unit not in inventory:
            fail(f"orphan_sources unit {unit!r} is not in the "
                 f"{'host ' if orphan_unit_ids is None else ''}inventory")
        orphan_sources[unit] = OrphanSource(unit, reason)

    return Resources(resources, exclusive, orphan_sources)
