#!/usr/bin/env python3
"""Build and prove the Workflow Manager's release assets (`D-Artifact`).

    package.py --version X.Y.Z --out DIR

Copies the project (`pyproject.toml`, `README.md`, `src/`) to a temporary
directory, sets the version there (`release.py set-version`), builds a wheel
and an sdist into DIR with `python -m build`, and installs the wheel into a
fresh venv, where it requires:

- the wheel to carry the pins, `workflow_manager/published_releases.json`;
- `workflow-manager --version` to print exactly `workflow-manager X.Y.Z`;
- `workflow-manager releases` to list exactly the versions this checkout's
  `src/workflow_manager/published_releases.json` pins (`D-Manager-Packaging`);
- `workflow-manager verify <this checkout>` to exit 0, resolving the
  checkout's recorded Workflow release through the release cache.

Every command runs outside any checkout, with this process's environment:
`WORKFLOW_MANAGER_RELEASE_CACHE` and `WORKFLOW_MANAGER_RELEASE_SOURCE` reach
the wheel unchanged, so a primed cache means no download.

Finally it writes DIR/SHA256SUMS (`sha256sum`-compatible, sorted by name,
over every other file in DIR). The build frontend is CI's own
(`.github/tools/requirements.txt`); no test runs the real build (INV-5).

Exit codes: 0 success; 1 build or proof failure; 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "src"))
from release import VERSION_RE, ReleaseError, set_version  # noqa: E402

from workflow_manager import package as workflow_package  # noqa: E402

#: What the wheel and sdist are built from; nothing else of the checkout.
COPY_FILES = ("pyproject.toml", "README.md")
COPY_TREES = ("src",)
#: Build and editor debris a checkout's `src/` may hold; never shipped.
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.egg-info", "build", "dist")

SUMS_NAME = workflow_package.SUMS_NAME
#: The pins, where the checkout keeps them and where the wheel must carry them.
PINS_PATH = Path("src/workflow_manager/published_releases.json")
PINS_IN_WHEEL = "workflow_manager/published_releases.json"
DISTRIBUTION_NAME = "workflow-manager"
COMMAND_TIMEOUT_SECONDS = 600


class PackageError(Exception):
    pass


def copy_project(source: Path, destination: Path) -> list[str]:
    """Copy the build inputs of `source` into `destination`; returns the
    copied files' POSIX paths relative to `destination`, sorted."""
    for name in COPY_FILES:
        path = source / name
        if not path.is_file():
            raise PackageError(f"{path} is missing")
        shutil.copy2(path, destination / name)
    for name in COPY_TREES:
        path = source / name
        if not path.is_dir():
            raise PackageError(f"{path} is missing")
        shutil.copytree(path, destination / name, ignore=IGNORED)
    return sorted(p.relative_to(destination).as_posix()
                  for p in destination.rglob("*") if p.is_file())


def sha256sums_text(directory: Path) -> str:
    """`sha256sum`'s text format (`<hex>  <name>`), one line per regular file
    directly in `directory` other than SHA256SUMS itself, sorted by name.
    The format is the shared writer's, the one Workflow packages use too."""
    files = [p for p in directory.iterdir() if p.is_file() and p.name != SUMS_NAME]
    if not files:
        raise PackageError(f"{directory} holds no files to digest")
    return workflow_package.sha256sums_text(files)


def write_sha256sums(directory: Path) -> Path:
    path = directory / SUMS_NAME
    path.write_text(sha256sums_text(directory), encoding="utf-8")
    return path


def check_version_output(output: str, version: str) -> None:
    """The installed wheel must report exactly the version it was built as."""
    expected = f"{DISTRIBUTION_NAME} {version}"
    actual = output.strip()
    if actual != expected:
        raise PackageError(f"--version printed {actual!r}, expected {expected!r}")


def expected_release_versions(checkout: Path) -> list[str]:
    """The versions `checkout`'s pin file publishes: what `releases` must list."""
    path = checkout / PINS_PATH
    try:
        releases = json.loads(path.read_text())["releases"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PackageError(f"cannot read the pins at {path}: {exc}") from exc
    if not isinstance(releases, dict):
        raise PackageError(f"{path}'s releases is not a mapping")
    return sorted(releases)


def check_wheel_carries_pins(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        if PINS_IN_WHEEL not in archive.namelist():
            raise PackageError(f"{wheel.name} does not carry {PINS_IN_WHEEL}")


def check_releases_output(output: str, versions: list[str]) -> None:
    """`releases` must list each release, one per line, by its version."""
    listed = sorted(line.split()[0] for line in output.splitlines() if line.strip())
    if listed != sorted(versions):
        raise PackageError(f"releases listed {listed}, expected {sorted(versions)}")


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PackageError(f"{' '.join(argv)}: {exc}") from exc
    if proc.returncode != 0:
        raise PackageError(f"{' '.join(argv)} exited {proc.returncode}:\n"
                           f"{proc.stdout}{proc.stderr}")
    return proc


def _single(out: Path, pattern: str) -> Path:
    found = sorted(out.glob(pattern))
    if len(found) != 1:
        raise PackageError(f"expected one {pattern} in {out}, found {[p.name for p in found]}")
    return found[0]


def package(version: str, out: Path) -> None:
    if not VERSION_RE.match(version):
        raise PackageError(f"version {version!r} is not X.Y.Z or X.Y.Z+local")
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise PackageError(f"{out} is not empty: SHA256SUMS must cover only this build")
    with tempfile.TemporaryDirectory(prefix="workflow-manager-package-") as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        copy_project(REPO_ROOT, project)
        set_version(project, version)
        _run([sys.executable, "-m", "build", "--outdir", str(out), str(project)])
        wheel = _single(out, "*.whl")
        _single(out, "*.tar.gz")
        check_wheel_carries_pins(wheel)

        venv = Path(tmp) / "venv"
        _run([sys.executable, "-m", "venv", str(venv)])
        bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
        _run([str(bindir / "python"), "-m", "pip", "install", "--no-deps", "--no-index",
              str(wheel)])
        # Run outside any checkout, so only the wheel's own metadata answers.
        entry = str(bindir / DISTRIBUTION_NAME)
        check_version_output(_run([entry, "--version"], cwd=Path(tmp)).stdout, version)
        listed = _run([entry, "releases"], cwd=Path(tmp))
        check_releases_output(listed.stdout, expected_release_versions(REPO_ROOT))
        _run([entry, "verify", str(REPO_ROOT)], cwd=Path(tmp))
    write_sha256sums(out)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"package.py: usage error: {message}", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="package.py", description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package(args.version, args.out)
    except (PackageError, ReleaseError) as exc:
        print(f"package.py: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(sorted(p.name for p in args.out.iterdir())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
