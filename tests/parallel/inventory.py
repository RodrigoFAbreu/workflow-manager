"""Atomic units, deterministic discovery and the selection grammar (plan
section 5.1, `D-Inventory`).

A host atomic unit is one `unittest.TestCase` class of one `tests/test_*.py`
module, id `host:<module>.py::<Class>`; a class is never split, because its
`setUpClass` fixture is what the class proves things about. A frozen atomic
unit is one class of one frozen suite, in one fixture kind, for one release,
id `frozen:<version>/<fixture>/<suite>.py::<Class>`.

Discovery imports each module in a subprocess (cwd `<repo_root>/tests/`, that
directory as `sys.path[0]`, bytecode writing off) and walks
`unittest.defaultTestLoader.loadTestsFromModule` -- the loader
`unittest.main()` uses -- so it sees exactly the tests a direct run sees. It
imports and never runs: no test, fixture or `setUpClass` is called.

Frozen discovery reads `FROZEN_MATRIX`/`CI_SUITES` (`tests/parallel/
matrix.py`) inside its own discovery subprocess, from the checkout it is
pointed at, then loads each release's suites from that release's own
`distribution/workflow/<version>/payload/scripts/` -- the bytes every fixture
copies -- one child process per release, and refuses a per-suite total that
differs from the pinned count (`InventoryCountError`).

The selection is a pure function of the inventory and the `--select`
specs (or `--newest-release-only`); no timing data, shard count or profile
is an input to it.
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


class InventoryCountError(InventoryError):
    """A frozen suite's discovered test total differs from its pinned
    `CI_SUITES` count."""


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


def frozen_unit_id(version: str, fixture: str, suite: str, cls: str) -> str:
    return f"{FROZEN_PREFIX}{version}/{fixture}/{suite}::{cls}"


def split_frozen_unit_id(unit_id: str) -> tuple[str, str, str, str]:
    """`(version, fixture, suite, class)`."""
    match = _FROZEN_UNIT_RE.fullmatch(unit_id)
    if match is None:
        raise ValueError(f"not a frozen unit id: {unit_id!r}")
    return match["version"], match["fixture"], match["suite"], match["cls"]


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
class FrozenInventory:
    #: matrix host unit id -> (version, fixture)
    matrix: dict[str, tuple[str, str]]
    #: version -> suite -> pinned test count, in `CI_SUITES` order
    ci_suites: dict[str, dict[str, int]]
    #: version -> suite -> class -> sorted test method names
    classes: dict[str, dict[str, dict[str, list[str]]]]

    def host_of(self, version: str, fixture: str) -> str | None:
        for unit, pair in self.matrix.items():
            if pair == (version, fixture):
                return unit
        return None

    def units_of(self, version: str, fixture: str) -> list[str]:
        """Every frozen unit id of one matrix host class, sorted."""
        return sorted(frozen_unit_id(version, fixture, suite, cls)
                      for suite, classes in self.classes[version].items() for cls in classes)

    def units(self) -> dict[str, list[str]]:
        """`{frozen unit id: [test id, ...]}` over every matrix row, sorted."""
        out = {}
        for version, fixture in self.matrix.values():
            for suite, classes in self.classes[version].items():
                for cls, methods in classes.items():
                    unit = frozen_unit_id(version, fixture, suite, cls)
                    out[unit] = [f"{unit}::{m}" for m in methods]
        return dict(sorted(out.items()))

    def to_json(self) -> dict:
        return {"matrix": {u: list(p) for u, p in self.matrix.items()},
                "ci_suites": [[v, list(s.items())] for v, s in self.ci_suites.items()],
                "classes": self.classes}

    @classmethod
    def from_json(cls, obj) -> "FrozenInventory":
        return cls(matrix={u: tuple(p) for u, p in sorted(obj["matrix"].items())},
                   ci_suites={v: dict(s) for v, s in obj["ci_suites"]},
                   classes=obj["classes"])


@dataclass(frozen=True)
class Inventory:
    tree_digest: str
    host: dict[str, list[str]]
    frozen: FrozenInventory | None = None

    def unit_ids(self) -> list[str]:
        return sorted(self.host) + (sorted(self.frozen.units()) if self.frozen else [])

    def to_json(self) -> str:
        doc = {"schema_version": SCHEMA_VERSION, "tree_digest": self.tree_digest,
               "host": self.host}
        if self.frozen is not None:
            doc["frozen"] = self.frozen.units()
            doc["matrix"] = self.frozen.to_json()
        return canonical_json(doc)


def discover(repo_root: Path) -> Inventory:
    """The full inventory of `repo_root`. The digest is taken before discovery
    runs, so nothing discovery does can enter it."""
    digest = tree_digest(repo_root)
    host = discover_host(repo_root)
    frozen = discover_frozen(repo_root)
    absent = sorted(set(frozen.matrix) - set(host))
    if absent:
        raise InventoryError(f"FROZEN_MATRIX names host classes discovery did not find: {absent}")
    return Inventory(tree_digest=digest, host=host, frozen=frozen)


def discover_frozen(repo_root: Path) -> FrozenInventory:
    """The frozen half of the inventory, discovered in a subprocess that reads
    `tests/parallel/matrix.py` from `repo_root`."""
    repo_root = Path(repo_root)
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "parallel.inventory", "--discover-frozen", str(repo_root)],
        cwd=str(repo_root / "tests"), capture_output=True, text=True, env=_discovery_env(),
    )
    if proc.returncode == 4:
        raise InventoryCountError(proc.stderr.strip().splitlines()[-1])
    if proc.returncode != 0:
        raise InventoryError(f"frozen discovery failed (exit {proc.returncode}):\n"
                             f"{proc.stderr[-6000:]}")
    try:
        return FrozenInventory.from_json(strict_json_loads(proc.stdout))
    except (ValueError, KeyError, TypeError) as exc:
        raise InventoryError(f"frozen discovery printed no inventory: {exc}\n"
                             f"{proc.stdout[-2000:]}") from exc


def _discover_frozen_in_process(repo_root: Path) -> dict:
    """Runs inside the frozen discovery subprocess (cwd `<repo_root>/tests/`):
    read the matrix, then list each release's suites in a child process of
    its own, since every release ships modules of the same names."""
    from . import matrix

    versions = sorted({version for version, _ in matrix.FROZEN_MATRIX.values()})
    classes = {}
    for version in versions:
        if version not in matrix.CI_SUITES:
            raise InventoryError(f"FROZEN_MATRIX names release {version}, which CI_SUITES lacks")
        suites = list(matrix.CI_SUITES[version])
        scripts = repo_root / "distribution" / "workflow" / version / "payload" / "scripts"
        env = _discovery_env()
        env["PYTHONPATH"] = str(repo_root / "tests")
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "parallel.inventory", "--discover-suites", *suites],
            cwd=str(scripts), capture_output=True, text=True, env=env,
        )
        if proc.returncode != 0:
            raise InventoryError(f"release {version}: suite discovery failed "
                                 f"(exit {proc.returncode}):\n{proc.stderr[-6000:]}")
        found = strict_json_loads(proc.stdout)
        for suite in suites:
            total = sum(len(methods) for methods in found[suite].values())
            pinned = matrix.CI_SUITES[version][suite]
            if total != pinned:
                raise InventoryCountError(
                    f"{version}/{suite}: discovered {total} tests, CI_SUITES pins {pinned}")
        classes[version] = {suite: found[suite] for suite in suites}
    return {
        "matrix": {unit: list(pair) for unit, pair in sorted(matrix.FROZEN_MATRIX.items())},
        "ci_suites": [[v, list(matrix.CI_SUITES[v].items())] for v in versions],
        "classes": classes,
    }


def _discover_suites_in_process(suites: list[str]) -> dict[str, dict[str, list[str]]]:
    """Runs with cwd (hence `sys.path[0]`) one release's `payload/scripts/`:
    `{suite: {class attribute name: [test method, ...]}}`, each suite loaded
    as `unittest.main()` loads its `__main__`."""
    import contextlib
    import importlib

    sys.dont_write_bytecode = True
    loader = unittest.defaultTestLoader
    out = {}
    for suite_file in suites:
        with contextlib.redirect_stdout(sys.stderr):
            module = importlib.import_module(suite_file[:-3])
            suite = loader.loadTestsFromModule(module)
        if loader.errors:
            raise InventoryError(f"{suite_file}: loader errors:\n" + "\n".join(loader.errors))
        names = _class_names(module)
        found: dict[str, list[str]] = {}
        for test in _flatten(suite):
            if isinstance(test, unittest.loader._FailedTest):  # noqa: SLF001
                raise InventoryError(f"{suite_file}: cannot load {test.id()}")
            cls = type(test)
            if id(cls) not in names:
                raise InventoryError(f"{suite_file}: {cls.__qualname__} is not a module attribute")
            found.setdefault(names[id(cls)], []).append(test._testMethodName)  # noqa: SLF001
        for cls_name, methods in found.items():
            if len(set(methods)) != len(methods):
                raise InventoryError(f"{suite_file}::{cls_name}: a test repeats")
        out[suite_file] = {c: sorted(m) for c, m in sorted(found.items())}
    return out


def _class_names(module) -> dict[int, str]:
    """`id(class) -> attribute name` for every `TestCase` class bound in the
    module -- the name `python3 <module>.py <Class>` resolves."""
    names: dict[int, str] = {}
    for attr in sorted(vars(module)):
        obj = vars(module)[attr]
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            names.setdefault(id(obj), attr)
    return names


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
        names = _class_names(module)
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
_FROZEN_UNIT_RE = re.compile(
    rf"frozen:(?P<version>\d+\.\d+\.\d+)/(?P<fixture>[a-z]+)/(?P<suite>\w+\.py)::(?P<cls>{_IDENT})")

#: The report line for a selection with frozen units but not their matrix
#: host class.
PARTIAL_FROZEN_NOTE = "partial frozen selection: host matrix assertions not evaluated"


@dataclass(frozen=True)
class Spec:
    text: str
    kind: str  # "host", "frozen" or `NEWEST_RELEASE_KIND`
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


# STOPGAP(M2): the newest-release selection; see docs/ARCHITECTURE.md's
# "Stopgap test profile".
#: `Spec.kind` of the `--newest-release-only` selection, and its
#: `Selection.kind`.
NEWEST_RELEASE_KIND = "newest-release"
#: The spec `--newest-release-only` passes where `--select` passes its specs;
#: never combined with another spec.
NEWEST_RELEASE = Spec("--newest-release-only", NEWEST_RELEASE_KIND)


def version_key(version: str) -> tuple[int, ...]:
    """Numeric version order: `2.10.0` sorts after `2.9.0`."""
    return tuple(int(part) for part in version.split("."))


def newest_release(frozen: FrozenInventory) -> str | None:
    """The highest version in `CI_SUITES` by numeric order, or None when no
    release is in the inventory."""
    return max(frozen.ci_suites, key=version_key, default=None)


def _select_newest_release(host_inventory: dict[str, list[str]],
                           frozen: FrozenInventory | None) -> "Selection":
    """Every host unit except the other releases' matrix host classes, plus
    the newest release's frozen units -- which its own matrix host classes,
    kept, bring in whole. So no frozen unit is partial, and with a single
    release this is the full selection."""
    units = dict.fromkeys(host_inventory)
    if frozen is not None:
        newest = newest_release(frozen)
        for unit, (version, _) in frozen.matrix.items():
            if version != newest:
                units.pop(unit, None)
        units.update(dict.fromkeys(u for u in frozen.units()
                                   if split_frozen_unit_id(u)[0] == newest))
    return Selection(dict(sorted(units.items())), kind=NEWEST_RELEASE_KIND)


# End of the STOPGAP(M2) block.
#: `Selection.kind` of the whole inventory (no selection flag) and of a
#: `--select`/`--fast` selection.
FULL_KIND = "full"
TARGETED_KIND = "targeted"


@dataclass(frozen=True)
class Selection:
    #: unit id -> None (every test of the unit) or the sorted method names to
    #: run inside that unit (its class fixture still runs once). Frozen units
    #: always map to None.
    units: dict[str, tuple[str, ...] | None]
    #: Frozen units are selected whose matrix host class is not, so the host
    #: matrix assertions over them are not evaluated -- a debugging aid,
    #: never a gate (`PARTIAL_FROZEN_NOTE`).
    partial_frozen: bool = False
    #: Which flags made it: `full` (none), `targeted` (`--select`/`--fast`)
    #: or `newest-release`. Derived from the flags, never from the unit set,
    #: and outside `to_json`, so `selection_digest` covers the units alone.
    #: A selection built by hand claims the least: `targeted`.
    kind: str = TARGETED_KIND

    def unit_ids(self) -> list[str]:
        return sorted(self.units)

    def host_unit_ids(self) -> list[str]:
        return [u for u in self.unit_ids() if u.startswith(HOST_PREFIX)]

    def frozen_unit_ids(self) -> list[str]:
        return [u for u in self.unit_ids() if u.startswith(FROZEN_PREFIX)]

    def to_json(self) -> str:
        return canonical_json({unit: None if tests is None else list(tests)
                               for unit, tests in self.units.items()})


def select(host_inventory: dict[str, list[str]], specs,
           frozen: FrozenInventory | None = None) -> Selection:
    """The union of every spec's matches; no spec means the full selection.
    A matrix host class, however it is selected, brings in all of its frozen
    classes (its assertions need them). A spec that names anything the
    inventory lacks raises `UnknownSelectorError`."""
    parsed = [s if isinstance(s, Spec) else parse_spec(s) for s in specs]
    matrix = frozen.matrix if frozen is not None else {}
    if not parsed:
        units = {unit: None for unit in host_inventory}
        units.update({unit: None for unit in (frozen.units() if frozen else ())})
        return Selection(dict(sorted(units.items())), kind=FULL_KIND)
    # STOPGAP(M2): the newest-release selection; see docs/ARCHITECTURE.md's
    # "Stopgap test profile".
    if any(spec.kind == NEWEST_RELEASE_KIND for spec in parsed):
        if len(parsed) != 1:
            raise SelectSyntaxError("--newest-release-only cannot be combined with --select")
        return _select_newest_release(host_inventory, frozen)
    # End of the STOPGAP(M2) block.

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
        if unit in matrix:
            for frozen_unit in frozen.units_of(*matrix[unit]):
                chosen[frozen_unit] = None

    for spec in parsed:
        if spec.kind == "frozen":
            for unit in _frozen_matches(spec, frozen):
                chosen[unit] = None
            continue
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

    partial = any(frozen.host_of(*split_frozen_unit_id(unit)[:2]) not in chosen
                  for unit in chosen if unit.startswith(FROZEN_PREFIX))
    return Selection({unit: None if tests is None else tuple(sorted(tests))
                      for unit, tests in sorted(chosen.items())}, partial_frozen=partial,
                     kind=TARGETED_KIND)


def _frozen_matches(spec: Spec, frozen: FrozenInventory | None) -> list[str]:
    where = f"--select {spec.text!r}"
    if frozen is None:
        raise UnknownSelectorError(f"{where}: no frozen units are in the inventory")
    if spec.version not in frozen.classes:
        raise UnknownSelectorError(f"{where}: no frozen release {spec.version}")
    if frozen.host_of(spec.version, spec.fixture) is None:
        raise UnknownSelectorError(f"{where}: release {spec.version} has no fixture "
                                   f"{spec.fixture}")
    suites = frozen.classes[spec.version]
    if spec.suite not in suites:
        raise UnknownSelectorError(f"{where}: release {spec.version} has no frozen suite "
                                   f"{spec.suite}")
    if spec.cls is None:
        names = sorted(suites[spec.suite])
    elif spec.cls in suites[spec.suite]:
        names = [spec.cls]
    else:
        raise UnknownSelectorError(f"{where}: {spec.suite} has no test class {spec.cls}")
    return [frozen_unit_id(spec.version, spec.fixture, spec.suite, name) for name in names]


def _main(argv: list[str]) -> int:
    modes = {
        "--discover-host": lambda args: _discover_host_in_process(args),
        "--discover-frozen": lambda args: _discover_frozen_in_process(Path(args[0])),
        "--discover-suites": lambda args: _discover_suites_in_process(args),
    }
    if argv[:1] not in ([m] for m in modes):
        print("usage: python3 -m parallel.inventory "
              "{--discover-host <module.py> ...|--discover-frozen <repo root>|"
              "--discover-suites <suite.py> ...}", file=sys.stderr)
        return 2
    try:
        found = modes[argv[0]](argv[1:])
    except InventoryCountError as exc:
        print(f"InventoryCountError: {exc}", file=sys.stderr)
        return 4
    except InventoryError as exc:
        print(f"InventoryError: {exc}", file=sys.stderr)
        return 3
    sys.stdout.write(canonical_json(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
