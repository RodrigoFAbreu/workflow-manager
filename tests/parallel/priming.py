"""Priming the release cache before discovery (plan 7.1, `D-Tested-Releases`).

Every pinned version of the checkout under test is resolved through
`ReleaseCache.ensure` -- the matrix needs the newest, the `updated` fixture
the one below it, and the pinned-package and hardening tests the rest -- in a
subprocess that imports the checkout's own `src/workflow_manager` and reads
its own pin file, so a scratch checkout primes only its own pins. The
resolved cache directory is then exported as `WORKFLOW_MANAGER_RELEASE_CACHE`
to discovery and to every unit the run starts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from . import strict_json_loads

CACHE_ENV = "WORKFLOW_MANAGER_RELEASE_CACHE"
SOURCE_ENV = "WORKFLOW_MANAGER_RELEASE_SOURCE"
PINNED_ONLY_ENV = "WORKFLOW_MANAGER_PINNED_ONLY"

_SCRIPT = """
import json, sys
from workflow_manager import source
root = source.cache_root().resolve()
where = source.ReleaseSource.select()
report = {"cache": str(root), "source": where.value, "versions": []}
try:
    pins = source.load_pins()
    cache = source.ReleaseCache(root, where, pins)
    for version in pins.versions():
        cache.ensure(version)
        report["versions"].append(version)
except Exception as exc:
    report["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report))
    sys.exit(3)
print(json.dumps(report))
"""


class PrimingError(Exception):
    """A pinned release could not be put in the cache: exit 2, naming the
    cache directory and the source."""


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
    return report


@contextmanager
def exported(cache: str):
    """`WORKFLOW_MANAGER_RELEASE_CACHE=cache` and `WORKFLOW_MANAGER_PINNED_ONLY=1`
    in this process's environment for the block -- inherited by discovery and
    by every unit, so no test discovers a release over the network -- restored
    after it."""
    saved = {name: os.environ.get(name) for name in (CACHE_ENV, PINNED_ONLY_ENV)}
    os.environ[CACHE_ENV] = cache
    os.environ[PINNED_ONLY_ENV] = "1"
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
