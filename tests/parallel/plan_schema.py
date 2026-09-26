"""The plan's chunk-descriptor contract (plan section 5.4 step 6).

The planner writes a plan's chunk lists only through `ChunkDescriptor.to_json`,
and every reader goes through `shard_chunks` -- so the planner and `isolation`
depend on this module, never on each other.

Plan shape read here: `plan["shards"]` is a list whose element `i` is an
object carrying `"chunks"`, the ordered list of shard `i`'s descriptors. Other
keys of a plan or of a shard object belong to the planner and are not read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SHARDS_KEY = "shards"
CHUNKS_KEY = "chunks"
FIELDS = ("id", "shard_index", "units", "estimate", "resources")


class PlanSchemaError(ValueError):
    """A plan or chunk descriptor does not have the contract's shape."""


def _sorted_unique(values, what: str) -> tuple[str, ...]:
    values = tuple(values)
    if any(not isinstance(v, str) or not v for v in values):
        raise PlanSchemaError(f"{what} must be non-empty strings: {values!r}")
    if len(set(values)) != len(values):
        raise PlanSchemaError(f"{what} contains a duplicate: {values!r}")
    return tuple(sorted(values))


@dataclass(frozen=True)
class ChunkDescriptor:
    id: str
    shard_index: int
    units: tuple[str, ...]
    estimate: float
    resources: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise PlanSchemaError(f"chunk id must be a non-empty string: {self.id!r}")
        if isinstance(self.shard_index, bool) or not isinstance(self.shard_index, int) \
                or self.shard_index < 0:
            raise PlanSchemaError(f"chunk {self.id}: bad shard_index {self.shard_index!r}")
        units = _sorted_unique(self.units, f"chunk {self.id} units")
        if not units:
            raise PlanSchemaError(f"chunk {self.id} has no units")
        if isinstance(self.estimate, bool) or not isinstance(self.estimate, (int, float)) \
                or not math.isfinite(self.estimate) or self.estimate < 0:
            raise PlanSchemaError(f"chunk {self.id}: bad estimate {self.estimate!r}")
        object.__setattr__(self, "units", units)
        object.__setattr__(self, "resources",
                           _sorted_unique(self.resources, f"chunk {self.id} resources"))

    @property
    def exclusive(self) -> bool:
        return bool(self.resources)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "shard_index": self.shard_index,
            "units": list(self.units),
            "estimate": self.estimate,
            "resources": list(self.resources),
        }

    @classmethod
    def from_json(cls, obj) -> "ChunkDescriptor":
        if not isinstance(obj, dict):
            raise PlanSchemaError(f"chunk descriptor must be an object: {obj!r}")
        missing = [f for f in FIELDS if f not in obj]
        if missing:
            raise PlanSchemaError(f"chunk descriptor {obj.get('id')!r} is missing {missing}")
        extra = sorted(set(obj) - set(FIELDS))
        if extra:
            raise PlanSchemaError(f"chunk descriptor {obj.get('id')!r} has unknown fields {extra}")
        for key in ("units", "resources"):
            if not isinstance(obj[key], list):
                raise PlanSchemaError(f"chunk {obj['id']!r}: {key} must be a list")
            if list(obj[key]) != sorted(obj[key]):
                raise PlanSchemaError(f"chunk {obj['id']!r}: {key} are not sorted")
        return cls(obj["id"], obj["shard_index"], tuple(obj["units"]),
                   obj["estimate"], tuple(obj["resources"]))


def shard_chunks(plan) -> list[list[ChunkDescriptor]]:
    """Each shard's chunk descriptors, in stored order. Refuses a malformed
    descriptor and a descriptor whose `shard_index` is not its shard's."""
    if not isinstance(plan, dict) or not isinstance(plan.get(SHARDS_KEY), list):
        raise PlanSchemaError(f"plan has no {SHARDS_KEY!r} list")
    out = []
    for index, shard in enumerate(plan[SHARDS_KEY]):
        if not isinstance(shard, dict) or not isinstance(shard.get(CHUNKS_KEY), list):
            raise PlanSchemaError(f"shard {index} has no {CHUNKS_KEY!r} list")
        chunks = [ChunkDescriptor.from_json(c) for c in shard[CHUNKS_KEY]]
        for chunk in chunks:
            if chunk.shard_index != index:
                raise PlanSchemaError(
                    f"chunk {chunk.id} records shard_index {chunk.shard_index} "
                    f"but is stored in shard {index}")
        out.append(chunks)
    return out
