"""`python3 tests/run_all.py`: the command every gate names (plan sections 5.9,
5.11, 5.12).

    python3 tests/run_all.py                       # the full selection, in parallel
    python3 tests/run_all.py --jobs 1              # the serial reference (INV-6)
    python3 tests/run_all.py --select SPEC ...     # targeted selection -- never a gate
    python3 tests/run_all.py --list [--select SPEC ...]
    python3 tests/run_all.py --plan-only --profile ci --out PLAN [--shards N]
    python3 tests/run_all.py --run-shard K --plan PLAN --results DIR
    python3 tests/run_all.py --aggregate DIR --plan PLAN
    python3 tests/run_all.py --update-timings --profile local|ci [--from PATH ...]
    python3 tests/run_all.py --restore-barrier

`--select` is repeatable (the union of its matches) and takes `test_x.py`,
`test_x.py::Class`, `test_x.py::Class::test_y`,
`frozen:<version>/<fixture>/<suite>.py` or
`frozen:<version>/<fixture>/<suite>.py::Class`.

Exit 0: every planned unit reported and every test passed. Exit 1: a test
failed or errored. Exit 2: an infrastructure fault (incomplete or foreign
results, a digest mismatch, a refused merge, a killed or recordless chunk, a
chunk that left undeclared orphaned processes (`OrphanProcessError`), a Linux
chunk without the orphan check (`OrphanCheckUnavailableError`), a declared
frozen orphan source sharing a chunk (`OrphanDeclarationError`), a
repository-integrity violation, another run holding this checkout's run
lock, a refused root run, a pinned release that cannot be put in the release
cache (`PrimingError`)) or a usage error (among them an inherited
`GIT_CONFIG_*` environment the chunk environment cannot extend,
`GitConfigEnvError`, refused before any chunk starts). Every exit-2 refusal prints
`run_all: error[<ErrorName>]: ...` as its first stderr line.

Order: arguments, path flags (never inside the repository) and `--select`
syntax are checked first, reading nothing but argv and `git rev-parse`; only
then is the checkout run lock taken (every mode takes it), and a barrier a
dead run left behind recovered; everything after that happens under the
lock. Every mode but `--restore-barrier` then primes the release cache with
every pinned version and exports it to discovery and to every unit (plan
7.1).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import traceback
from pathlib import Path

from . import executor, inventory, isolation, planner, priming, report
from . import resources as resources_mod
from .timings import PROFILES

#: Exceptions reported as tagged exit-2 refusals.
REFUSALS = (inventory.SelectSyntaxError, inventory.UnknownSelectorError,
            inventory.InventoryError, planner.PlanError, resources_mod.ResourcesFileError,
            isolation.IsolationError, executor.ExecutorError, priming.PrimingError)


class PathInsideRepositoryError(ValueError):
    """A path flag names a location inside the repository, where the tree
    digest would read it (5.6)."""


def _err(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _out(message: str) -> None:
    print(message, flush=True)


def refuse(exc: BaseException) -> int:
    _err(f"run_all: error[{type(exc).__name__}]: {exc}")
    return 2


def _jobs(text: str):
    if text == "auto":
        return text
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--jobs takes a positive integer or 'auto', "
                                         f"not {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError("--jobs must be at least 1")
    return value


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"must not be negative: {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 tests/run_all.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list", action="store_true", help="print the selected atomic units")
    modes.add_argument("--plan-only", action="store_true", help="write the plan and exit")
    modes.add_argument("--run-shard", type=_positive, metavar="K",
                       help="run shard K of --plan into --results (CI)")
    modes.add_argument("--aggregate", type=Path, metavar="DIR",
                       help="verify every shard's results under DIR against --plan, run "
                            "phase B and report (CI)")
    modes.add_argument("--update-timings", action="store_true",
                       help="fold observed timings into tests/parallel/timings.json")
    modes.add_argument("--restore-barrier", action="store_true",
                       help="restore a write barrier a killed run left behind, and exit")
    parser.add_argument("--select", action="append", default=[], metavar="SPEC",
                        help="targeted selection (repeatable); not a verification gate")
    parser.add_argument("--jobs", type=_jobs, default=None, metavar="N|auto",
                        help="local workers (default auto; 1 is the serial reference)")
    parser.add_argument("--profile", choices=PROFILES, help="timing profile (default local)")
    parser.add_argument("--shards", type=int, metavar="N", help="--plan-only: shard count")
    parser.add_argument("--out", type=Path, metavar="PATH", help="--plan-only: plan file")
    parser.add_argument("--plan", type=Path, metavar="PATH",
                        help="--run-shard/--aggregate: the plan")
    parser.add_argument("--results", type=Path, metavar="DIR",
                        help="results directory (required by --run-shard)")
    parser.add_argument("--from", dest="sources", action="append", default=[], type=Path,
                        metavar="PATH", help="--update-timings: history .jsonl or results dir")
    parser.add_argument("--whole-groups", action="store_true",
                        help="debug: never split a frozen execution group")
    parser.add_argument("--shuffle-seed", type=int, metavar="N",
                        help="debug: permute execution order (never the plan or the verdict)")
    parser.add_argument("--allow-root", action="store_true",
                        help="run as root although that disables the write barrier")
    return parser


def _mode(args) -> str:
    for name in ("list", "plan_only", "update_timings", "restore_barrier"):
        if getattr(args, name):
            return name
    if args.run_shard is not None:
        return "run_shard"
    if args.aggregate is not None:
        return "aggregate"
    return "run"


#: Which options each mode accepts, beyond the mode flag itself.
ALLOWED = {
    "run": {"select", "jobs", "results", "whole_groups", "shuffle_seed", "allow_root"},
    "list": {"select"},
    "plan_only": {"select", "profile", "shards", "out", "whole_groups"},
    "run_shard": {"plan", "results", "allow_root"},
    "aggregate": {"plan", "allow_root"},
    "update_timings": {"profile", "sources"},
    "restore_barrier": set(),
}
#: GitHub Actions' ceiling on the jobs one matrix may generate.
CI_MATRIX_LIMIT = 256
_DEFAULTS = {"select": [], "sources": [], "whole_groups": False,
             "allow_root": False}


def validate(parser, args) -> str:
    mode = _mode(args)
    given = {name for name in ALLOWED["run"] | {"profile", "shards", "out", "plan", "sources"}
             if getattr(args, name) != _DEFAULTS.get(name)}
    extra = sorted(given - ALLOWED[mode])
    if extra:
        flags = ", ".join("--" + e.replace("_", "-").replace("sources", "from") for e in extra)
        parser.error(f"{flags} cannot be used with "
                     f"{'a local run' if mode == 'run' else '--' + mode.replace('_', '-')}")
    if mode in ("run_shard", "aggregate") and args.plan is None:
        parser.error(f"--{mode.replace('_', '-')} needs --plan")
    if mode == "run_shard" and args.results is None:
        parser.error("--run-shard needs --results")
    if mode == "update_timings" and args.profile is None:
        parser.error("--update-timings needs --profile")
    if args.shards is not None and args.shards < 1:
        parser.error("--shards must be at least 1")
    if args.profile == "ci" and args.shards is not None and args.shards > CI_MATRIX_LIMIT:
        parser.error(f"--shards {args.shards} exceeds GitHub's {CI_MATRIX_LIMIT}-job matrix "
                     f"limit; the CI shard matrix could never run")
    return mode


def repository_root(repo_root: Path) -> Path:
    out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
                         check=True, capture_output=True, text=True).stdout.strip()
    return Path(out).resolve()


def check_paths(repo_root: Path, args) -> None:
    """Every output path, and every path a run reads results from, lies
    outside the repository root (5.6)."""
    root = repository_root(repo_root)

    def outside(flag: str, value) -> Path:
        resolved = Path(value).expanduser().resolve()
        if resolved == root or root in resolved.parents:
            raise PathInsideRepositoryError(
                f"--{flag} {value} is inside the repository ({root}); every file the tooling "
                f"writes or reads results from lives outside the checkout")
        return resolved

    for flag in ("out", "plan", "results", "aggregate"):
        value = getattr(args, flag)
        if value is not None:
            setattr(args, flag, outside(flag, value))
    args.sources = [outside("from", value) for value in args.sources]


def main(argv=None, *, repo_root: Path) -> int:
    """The whole command, against the checkout at `repo_root` -- the only root
    anything here ever reads; no flag or environment variable changes it.

    Any error the tool does not name itself (a failed `Popen`, `chmod` or git
    call, a full disk) is still an infrastructure fault: exit 2, tagged, with
    the traceback -- never the uncaught-exception exit 1 that means a test
    failed (5.11)."""
    try:
        return _main(argv, repo_root=Path(repo_root))
    except Exception as exc:  # noqa: BLE001 -- the exit-code contract
        code = refuse(exc)
        traceback.print_exc()
        return code


def _main(argv, *, repo_root: Path) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    mode = validate(parser, args)
    specs = list(args.select)
    try:
        check_paths(repo_root, args)
        parsed = [inventory.parse_spec(s) for s in specs]
    except (PathInsideRepositoryError, inventory.SelectSyntaxError) as exc:
        return refuse(exc)

    try:
        lock = isolation.acquire_run_lock(repo_root)
    except isolation.RunLockHeldError as exc:
        return refuse(exc)
    try:
        restored = isolation.recover_barrier(repo_root, lock)
        if restored:
            _out(f"recovered a write barrier a dead run left behind: {len(restored)} "
                 f"directories restored")
        if mode == "restore_barrier":
            if not restored:
                _out("no write barrier to restore")
            return 0
        primed = priming.prime(repo_root)
        with priming.exported(primed["cache"]):
            return _dispatch(mode, args, parsed, repo_root, lock)
    except REFUSALS as exc:
        return refuse(exc)
    finally:
        lock.release()


def _dispatch(mode, args, parsed, repo_root: Path, lock) -> int:
    """Run `mode` with the release cache primed and exported."""
    if mode == "list":
        return executor.list_units(repo_root, lock, specs=parsed, out=_out)
    if mode == "plan_only":
        return executor.plan_only(repo_root, lock, specs=parsed,
                                  profile=args.profile or "local", out_path=args.out,
                                  shards=args.shards, whole_groups=args.whole_groups,
                                  out=_out)
    if mode == "run_shard":
        return executor.run_shard(repo_root, lock, index=args.run_shard,
                                  plan_path=args.plan, results=args.results,
                                  allow_root=args.allow_root, out=_out, err=_err)
    if mode == "aggregate":
        return executor.aggregate(repo_root, lock, results_root=args.aggregate,
                                  plan_path=args.plan, allow_root=args.allow_root,
                                  out=_out, err=_err)
    if mode == "update_timings":
        return executor.update_timings(repo_root, lock, profile=args.profile,
                                       sources=args.sources, out=_out, err=_err)
    return executor.local_run(repo_root, lock, specs=parsed, jobs=args.jobs,
                              shuffle_seed=args.shuffle_seed,
                              whole_groups=args.whole_groups, allow_root=args.allow_root,
                              results=args.results, out=_out, err=_err)

