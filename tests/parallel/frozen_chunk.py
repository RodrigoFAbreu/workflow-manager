"""The frozen-suite side of the executor, run in a subprocess of the checkout
being verified (cwd `<repo_root>/tests/`), so it uses that checkout's own
`frozen_runs`, `support` and `workflow_manager` -- the executor process never
imports them (plan 5.1, 5.5).

    python3 -m parallel.frozen_chunk run --spec SPEC --record RECORD
    python3 -m parallel.frozen_chunk prepare-merge --plan PLAN \
        --inventory INVENTORY --records DIR --contexts DIR

`run` executes one planned frozen chunk through `frozen_runs.execute` in a
fresh disposable repository and writes its `FrozenRecord`: exit 0 when the
suite passed, 1 when it did not (a verdict, not a fault), 2 on a usage error
(no record).

`prepare-merge` builds one `MergeContext` per `(version, fixture)` whose
matrix host class is in the verified plan's phase B -- from the plan's frozen
chunks and the inventory's discovered class sets, never from the records --
writes them under `--contexts`, then merges the records of each against it.
Exit 0 when every merge is structurally complete, 3 (with one line per
refusal on stdout, as JSON) when any is refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import canonical_json, strict_json_loads
from .inventory import FROZEN_PREFIX, FrozenInventory, split_frozen_unit_id
from .plan_schema import shard_chunks

MERGE_REFUSED = 3


def frozen_chunk_classes(chunk) -> tuple[str, str, str, tuple[str, ...]]:
    """`(version, fixture, suite, sorted classes)` of a plan's frozen chunk."""
    parts = [split_frozen_unit_id(u) for u in chunk.units]
    version, fixture, suite, _ = parts[0]
    return version, fixture, suite, tuple(sorted(p[3] for p in parts))


def is_frozen(chunk) -> bool:
    return chunk.units[0].startswith(FROZEN_PREFIX)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _run(args) -> int:
    import frozen_runs

    spec = strict_json_loads(Path(args.spec).read_text(encoding="utf-8"))
    chunk = frozen_runs.FrozenChunk(spec["chunk_id"], spec["version"], spec["fixture"],
                                    spec["suite"], tuple(spec["classes"]),
                                    tuple(spec["enumerated"]))
    record = frozen_runs.execute(chunk, tree_digest=spec["tree_digest"],
                                 plan_digest=spec["plan_digest"],
                                 repo_root=frozen_runs.REPO_ROOT, timeout=int(spec["timeout"]))
    print(record.output[-6000:])
    _write_atomic(Path(args.record), record.to_json())
    return 0 if record.returncode == 0 and not record.timed_out else 1


def planned_contexts(plan: dict, frozen: FrozenInventory) -> dict:
    """`{(version, fixture): [FrozenChunk, ...]}` for every matrix row whose
    host class is in the plan's phase B."""
    import frozen_runs

    phase_b = {u for shard in shard_chunks(plan["phase_b"]) for c in shard for u in c.units}
    rows = {pair for unit, pair in frozen.matrix.items() if unit in phase_b}
    out: dict = {row: [] for row in sorted(rows)}
    for shard in shard_chunks(plan):
        for chunk in shard:
            if not is_frozen(chunk):
                continue
            version, fixture, suite, classes = frozen_chunk_classes(chunk)
            if (version, fixture) in out:
                out[(version, fixture)].append(
                    frozen_runs.FrozenChunk(chunk.id, version, fixture, suite, classes))
    return out


def _prepare_merge(args) -> int:
    import frozen_runs

    plan = strict_json_loads(Path(args.plan).read_text(encoding="utf-8"))
    inventory = strict_json_loads(Path(args.inventory).read_text(encoding="utf-8"))
    frozen = FrozenInventory.from_json(inventory["matrix"])
    refusals = []
    for (version, fixture), chunks in planned_contexts(plan, frozen).items():
        label = f"{version}/{fixture}"
        try:
            context = frozen_runs.MergeContext.from_chunks(
                version, fixture, chunks,
                {suite: sorted(frozen.classes[version][suite])
                 for suite in frozen.ci_suites[version]},
                tree_digest=plan["tree_digest"], plan_digest=plan["plan_digest"])
            frozen_runs.write_context(context, Path(args.contexts))
            frozen_runs.merge(frozen_runs.load_records(Path(args.records), version, fixture),
                              context, frozen_runs.REPO_ROOT)
        except frozen_runs.FrozenMergeError as exc:
            refusals.append({"row": label, "error": str(exc)})
    for refusal in refusals:
        print(json.dumps(refusal, sort_keys=True))
    return MERGE_REFUSED if refusals else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m parallel.frozen_chunk")
    sub = parser.add_subparsers(dest="mode", required=True)
    run = sub.add_parser("run")
    run.add_argument("--spec", required=True)
    run.add_argument("--record", required=True)
    prep = sub.add_parser("prepare-merge")
    for name in ("--plan", "--inventory", "--records", "--contexts"):
        prep.add_argument(name, required=True)
    args = parser.parse_args(argv)
    sys.dont_write_bytecode = True
    return _run(args) if args.mode == "run" else _prepare_merge(args)


def spec_json(chunk, frozen: FrozenInventory, *, tree_digest: str, plan_digest: str,
              timeout: float) -> str:
    """The `run --spec` document for one planned frozen chunk."""
    version, fixture, suite, classes = frozen_chunk_classes(chunk)
    methods = frozen.classes[version][suite]
    return canonical_json({
        "chunk_id": chunk.id, "version": version, "fixture": fixture, "suite": suite,
        "classes": list(classes),
        "enumerated": [f"{c}.{m}" for c in classes for m in methods[c]],
        "tree_digest": tree_digest, "plan_digest": plan_digest, "timeout": int(timeout),
    })


if __name__ == "__main__":
    raise SystemExit(main())
