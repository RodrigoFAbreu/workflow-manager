"""Atomic units, deterministic discovery and the selection grammar (plan
section 5.1, `D-Inventory`).

A host atomic unit is one `unittest.TestCase` class of one `tests/test_*.py`
module, id `host:<module>.py::<Class>`; a class is never split, because its
`setUpClass` fixture is what the class proves things about. Frozen units
(`frozen:<version>/<fixture>/<suite>.py::<Class>`) are discovered from CP2 on.

Discovery imports each module in a subprocess (cwd `<repo_root>/tests/`, that
directory as `sys.path[0]`, bytecode writing off) and walks
`unittest.defaultTestLoader.loadTestsFromModule` -- the loader
`unittest.main()` uses -- so it sees exactly the tests a direct run sees. It
imports and never runs: no test, fixture or `setUpClass` is called.

The selection is a pure function of the inventory and the `--select`
specs; no timing data, shard count or profile is an input to it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from . import canonical_json, strict_json_loads
from .tree import tree_digest

SCHEMA_VERSION = 1
HOST_PREFIX = "host:"
FROZEN_PREFIX = "frozen:"
HOST_MODULE_RE = re.compile(r"test_\w+\.py")


class InventoryError(Exception):
    """Discovery could not produce a trustworthy inventory."""


class SelectSyntaxError(ValueError):
    """A `--select` spec matches none of the five spec forms."""


class UnknownSelectorError(ValueError):
    """A syntactically valid `--select` spec names something the inventory
    does not have -- a usage error, never an empty selection."""


# -- discovery ---------------------------------------------------------------

def host_modules(repo_root: Path) -> list[str]:
    """`tests/test_*.py` file names, sorted by byte order (never listing
    order)."""
    names = [n for n in os.listdir(Path(repo_root) / "tests") if HOST_MODULE_RE.fullmatch(n)]
    return sorted(names, key=os.fsencode)


def host_unit_id(module: str, cls: str) -> str:
    return f"{HOST_PREFIX}{module}::{cls}"


def host_test_id(module: str, cls: str, method: str) -> str:
    return f"{module}::{cls}::{method}"


def split_host_unit_id(unit_id: str) -> tuple[str, str]:
    if not unit_id.startswith(HOST_PREFIX) or unit_id.count("::") != 1:
        raise ValueError(f"not a host unit id: {unit_id!r}")
    module, cls = unit_id[len(HOST_PREFIX):].split("::")
    return module, cls


def _discovery_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def discover_host(repo_root: Path) -> dict[str, list[str]]:
    """`{host unit id: [test id, ...]}` for every host class that has at least
    one test, everything sorted."""
    repo_root = Path(repo_root)
    modules = host_modules(repo_root)
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "parallel.inventory", "--discover-host", *modules],
        cwd=str(repo_root / "tests"), capture_output=True, text=True, env=_discovery_env(),
    )
    if proc.returncode != 0:
        raise InventoryError(f"host discovery failed (exit {proc.returncode}):\n"
                             f"{proc.stderr[-6000:]}")
    try:
        found = strict_json_loads(proc.stdout)
    except ValueError as exc:
        raise InventoryError(f"host discovery printed no inventory: {exc}\n"
                             f"{proc.stdout[-2000:]}") from exc
    return {unit: sorted(tests) for unit, tests in sorted(found.items())}


@dataclass(frozen=True)
class Inventory:
    tree_digest: str
    host: dict[str, list[str]]

    def unit_ids(self) -> list[str]:
        return sorted(self.host)

    def to_json(self) -> str:
        return canonical_json({"schema_version": SCHEMA_VERSION,
                               "tree_digest": self.tree_digest,
                               "host": self.host})


def discover(repo_root: Path) -> Inventory:
    """The full inventory of `repo_root`. The digest is taken before discovery
    runs, so nothing discovery does can enter it."""
    digest = tree_digest(repo_root)
    return Inventory(tree_digest=digest, host=discover_host(repo_root))


def _discover_host_in_process(module_names: list[str]) -> dict[str, list[str]]:
    """Runs inside the discovery subprocess: import each module, load it the
    way `unittest.main()` does, and name each test by the module attribute its
    class is bound to (the name `python3 <module>.py <Class>` resolves)."""
    import contextlib
    import importlib

    sys.dont_write_bytecode = True
    loader = unittest.defaultTestLoader
    inventory: dict[str, list[str]] = {}
    for filename in module_names:
        stem = filename[:-3]
        with contextlib.redirect_stdout(sys.stderr):
            module = importlib.import_module(stem)
            suite = loader.loadTestsFromModule(module)
        if loader.errors:
            raise InventoryError(f"{filename}: loader errors:\n" + "\n".join(loader.errors))
        names: dict[int, str] = {}
        for attr in sorted(vars(module)):
            obj = vars(module)[attr]
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                names.setdefault(id(obj), attr)
        for test in _flatten(suite):
            if isinstance(test, unittest.loader._FailedTest):  # noqa: SLF001
                raise InventoryError(f"{filename}: cannot load {test.id()}")
            cls = type(test)
            if id(cls) not in names:
                raise InventoryError(f"{filename}: {cls.__qualname__} is not a module attribute")
            unit = host_unit_id(filename, names[id(cls)])
            inventory.setdefault(unit, []).append(
                host_test_id(filename, names[id(cls)], test._testMethodName))  # noqa: SLF001
    for unit, tests in inventory.items():
        if len(set(tests)) != len(tests):
            raise InventoryError(f"{unit}: a test id repeats")
    return inventory


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


# -- selection ---------------------------------------------------------------

_IDENT = r"[A-Za-z_]\w*"
_HOST_SPEC_RE = re.compile(rf"(?P<module>test_\w+\.py)(?:::(?P<cls>{_IDENT})(?:::(?P<test>{_IDENT}))?)?")
_FROZEN_SPEC_RE = re.compile(
    rf"frozen:(?P<version>\d+\.\d+\.\d+)/(?P<fixture>[a-z]+)/(?P<suite>\w+\.py)(?:::(?P<cls>{_IDENT}))?")


@dataclass(frozen=True)
class Spec:
    text: str
    kind: str  # "host" or "frozen"
    module: str | None = None
    cls: str | None = None
    test: str | None = None
    version: str | None = None
    fixture: str | None = None
    suite: str | None = None


def parse_spec(text: str) -> Spec:
    """Syntax only -- reads nothing but the string."""
    match = _HOST_SPEC_RE.fullmatch(text)
    if match:
        return Spec(text, "host", module=match["module"], cls=match["cls"], test=match["test"])
    match = _FROZEN_SPEC_RE.fullmatch(text)
    if match:
        return Spec(text, "frozen", version=match["version"], fixture=match["fixture"],
                    suite=match["suite"], cls=match["cls"])
    raise SelectSyntaxError(
        f"--select {text!r} matches none of: test_x.py, test_x.py::Class, "
        f"test_x.py::Class::test_y, frozen:<version>/<fixture>/<suite>.py, "
        f"frozen:<version>/<fixture>/<suite>.py::Class")


@dataclass(frozen=True)
class Selection:
    #: unit id -> None (every test of the unit) or the sorted method names to
    #: run inside that unit (its class fixture still runs once).
    units: dict[str, tuple[str, ...] | None]

    def unit_ids(self) -> list[str]:
        return sorted(self.units)

    def to_json(self) -> str:
        return canonical_json({unit: None if tests is None else list(tests)
                               for unit, tests in self.units.items()})


def select(host_inventory: dict[str, list[str]], specs) -> Selection:
    """The union of every spec's matches; no spec means the full selection.
    A spec that names anything the inventory lacks raises
    `UnknownSelectorError`."""
    parsed = [s if isinstance(s, Spec) else parse_spec(s) for s in specs]
    if not parsed:
        return Selection({unit: None for unit in sorted(host_inventory)})

    by_module: dict[str, list[str]] = {}
    for unit in host_inventory:
        module, _ = split_host_unit_id(unit)
        by_module.setdefault(module, []).append(unit)

    chosen: dict[str, set[str] | None] = {}

    def add(unit: str, test: str | None):
        if test is None or chosen.get(unit, set()) is None:
            chosen[unit] = None
        else:
            chosen.setdefault(unit, set()).add(test)

    for spec in parsed:
        if spec.kind == "frozen":
            raise UnknownSelectorError(
                f"--select {spec.text!r}: no frozen units are in the inventory")
        if spec.module not in by_module:
            raise UnknownSelectorError(f"--select {spec.text!r}: no host module {spec.module}")
        if spec.cls is None:
            for unit in by_module[spec.module]:
                add(unit, None)
            continue
        unit = host_unit_id(spec.module, spec.cls)
        if unit not in host_inventory:
            raise UnknownSelectorError(
                f"--select {spec.text!r}: {spec.module} has no test class {spec.cls}")
        if spec.test is None:
            add(unit, None)
            continue
        if host_test_id(spec.module, spec.cls, spec.test) not in host_inventory[unit]:
            raise UnknownSelectorError(
                f"--select {spec.text!r}: {spec.cls} has no test {spec.test}")
        add(unit, spec.test)

    return Selection({unit: None if tests is None else tuple(sorted(tests))
                      for unit, tests in sorted(chosen.items())})


def _main(argv: list[str]) -> int:
    if argv[:1] != ["--discover-host"]:
        print("usage: python3 -m parallel.inventory --discover-host <module.py> ...",
              file=sys.stderr)
        return 2
    try:
        found = _discover_host_in_process(argv[1:])
    except InventoryError as exc:
        print(f"InventoryError: {exc}", file=sys.stderr)
        return 3
    sys.stdout.write(canonical_json(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
