"""Priming the release cache before discovery (plan 7.1, `D-Tested-Releases`).

Every pinned version of the checkout under test is resolved through
`ReleaseCache.ensure` -- the matrix needs the newest, the `updated` fixture
the one below it, and the pinned-package and hardening tests the rest -- in a
subprocess that imports the checkout's own `src/workflow_manager` and reads
its own pin file, so a scratch checkout primes only its own pins. The
resolved cache directory is then exported as `WORKFLOW_MANAGER_RELEASE_CACHE`
to discovery and to every unit the run starts.

Two refusals at the start of a run, before any unit starts, both exit 2: a
tested version the cache does not serve after priming (the read `support`
makes), and a run directory filesystem with less than `MIN_FREE_RUN_BYTES`
free (`TmpSpaceError`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from . import strict_json_loads

CACHE_ENV = "WORKFLOW_MANAGER_RELEASE_CACHE"
SOURCE_ENV = "WORKFLOW_MANAGER_RELEASE_SOURCE"
PINNED_ONLY_ENV = "WORKFLOW_MANAGER_PINNED_ONLY"
#: Internal: the pid of the outermost runner. A nested runner (the runner's own
#: tests start about thirty inside a unit) inherits it and skips the free-space
#: check the outer run already made. Not an option; it cannot lower the minimum.
GATE_PREFLIGHT_ENV = "WM_GATE_PREFLIGHT"

#: Free bytes a run needs where its run directory is created. A full run
#: (2328 units, 15523 tests, 8 workers, 2026-11-02) peaked at 1,989,292 KiB
#: (1.9 GiB) under its run directory; 4 GiB is 2.1 times that peak, room for a
#: missed sample, more workers and later locked releases.
MIN_FREE_RUN_BYTES = 4 * 1024**3

_SCRIPT = """
import json, sys
from workflow_manager import source
root = source.cache_root().resolve()
where = source.ReleaseSource.select()
report = {"cache": str(root), "source": where.value, "versions": []}
try:
    # The tested set: the pins plus the checkout's lock file (plan 3.5).
    sys.path.insert(0, "tests")
    import tested_releases
    pins = tested_releases.tested_pins()
    cache = source.ReleaseCache(root, where, pins)
    report["unserved"] = []
    for version in pins.versions():
        cache.ensure(version)
        report["versions"].append(version)
    # Read back what `support` reads: a version the cache does not serve now
    # would fail deep inside a unit.
    for version in report["versions"]:
        if not cache.cached_manifest(version):
            report["unserved"].append(version)
except Exception as exc:
    report["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report))
    sys.exit(3)
print(json.dumps(report))
"""


class PrimingError(Exception):
    """A pinned release could not be put in the cache: exit 2, naming the
    cache directory and the source."""


class TmpSpaceError(PrimingError):
    """The filesystem a run directory is created on has less than the minimum
    free space: exit 2, before anything is fetched or started."""


def check_free_space(path, minimum=None, free=None, lever="TMPDIR") -> None:
    """Refuse when `path` (its nearest existing ancestor, nothing is created)
    has fewer than `minimum` free bytes. `free` is the injected measurement;
    `lever` is the option the operator changes."""
    minimum = MIN_FREE_RUN_BYTES if minimum is None else minimum
    if free is None:
        probe = Path(path)
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        free = shutil.disk_usage(probe).free
    if free < minimum:
        gib = 1024**3
        raise TmpSpaceError(
            f"{path} has {free} bytes ({free / gib:.1f} GiB) free, and a run needs at "
            f"least {minimum} bytes ({minimum / gib:.1f} GiB) there: set {lever} to a "
            f"directory with that much free space and run again")


def nested_in_checked_run(environ=None) -> bool:
    """Whether an enclosing run (a live pid in `GATE_PREFLIGHT_ENV`) has already
    made the free-space check. A missing, malformed or dead value is `False`."""
    environ = os.environ if environ is None else environ
    try:
        pid = int(environ.get(GATE_PREFLIGHT_ENV, ""))
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (ValueError, OverflowError, OSError):
        return False
    return True


def prime(repo_root: Path, environ=None) -> dict:
    """Resolve every pinned version of `repo_root` into the release cache.
    Returns `{"cache": dir, "source": url, "versions": [...]}`."""
    environ = os.environ if environ is None else environ
    env = dict(environ)
    env["PYTHONPATH"] = str(Path(repo_root) / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, "-B", "-c", _SCRIPT], cwd=str(repo_root),
                          capture_output=True, text=True, env=env)
    try:
        report = strict_json_loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise PrimingError(f"priming the release cache failed (exit {proc.returncode}): "
                           f"{proc.stderr[-4000:]}") from exc
    if proc.returncode != 0 or "error" in report:
        raise PrimingError(
            f"cannot prime the release cache {report['cache']} from {report['source']}: "
            f"{report.get('error')}")
    if report.get("unserved"):
        unserved = report["unserved"][0]
        raise PrimingError(
            f"release {unserved} was primed into the cache {report['cache']} from "
            f"{report['source']} but the cache does not serve its manifest: when no other "
            f"run is using the cache, remove {report['cache']}/{unserved} and run again")
    return report


@contextmanager
def exported(cache: str):
    """`WORKFLOW_MANAGER_RELEASE_CACHE=cache` and `WORKFLOW_MANAGER_PINNED_ONLY=1`
    in this process's environment for the block -- inherited by discovery and
    by every unit, so no test discovers a release over the network -- restored
    after it. Also sets `GATE_PREFLIGHT_ENV` to this pid, so a nested runner does
    not repeat the free-space check."""
    names = (CACHE_ENV, PINNED_ONLY_ENV, GATE_PREFLIGHT_ENV)
    saved = {name: os.environ.get(name) for name in names}
    os.environ[CACHE_ENV] = cache
    os.environ[PINNED_ONLY_ENV] = "1"
    os.environ[GATE_PREFLIGHT_ENV] = str(os.getpid())
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def cache_entries(cache: str) -> set[str]:
    """The names directly under the release cache directory (none when absent)."""
    try:
        return set(os.listdir(cache))
    except OSError:
        return set()


def stray_entries(cache: str, before: set[str], pinned) -> list[str]:
    """Release entries the run added to the primed cache that are not a pinned
    version, or that were discovered (plan 3.7): a test reached the primed
    cache with discovery on instead of its own private one."""
    pinned = set(pinned)
    strays = []
    for name in sorted(cache_entries(cache) - before):
        if name.endswith(".lock") or name.startswith("."):
            continue
        entry = Path(cache) / name
        if name not in pinned or (entry / "SOURCE").exists():
            strays.append(name)
    return strays
