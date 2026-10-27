"""The real `scripts/workflow_retention.py` driven through its own seams in a
scratch managed repository (the conformance recipe of the retention-status plan).

The forge is not a stub `gh`: the recipe runs the real script in a test-only
`python3 -I -B -c` subprocess that calls `main` with `run=` and `resolve=`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ("workflow_retention.py", "workflow_forge.py")
STATE = "docs/ai-workflow/WORKFLOW_STATE.json"

DRIVER = r"""
import json, sys
sys.path.insert(0, "scripts")
import workflow_retention as wr
root = sys.argv[1]
def resolve(repo_root):
    return {"path": "/usr/bin/gh", "sha256": "0" * 64}
def run(argv, timeout):
    commit = argv[argv.index("--search") + 1]
    repo = argv[argv.index("--repo") + 1]
    return json.dumps([{"number": 7, "url": "https://github.com/" + repo + "/pull/7",
                        "state": "MERGED", "headRefOid": commit}])
sys.exit(wr.main(["report", "--json", "--repo-root", root], run=run, resolve=resolve))
"""

COMPLETE = "MILESTONE_COMPLETE"


def available() -> bool:
    return all((REPO_ROOT / "scripts" / name).is_file() for name in SCRIPTS)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def copy_scripts(repo: Path) -> None:
    (repo / "scripts").mkdir(exist_ok=True)
    for name in SCRIPTS:
        shutil.copyfile(REPO_ROOT / "scripts" / name, repo / "scripts" / name)


def write_state(repo: Path, items: dict) -> None:
    path = repo / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "active_work_item_id": None,
                                "work_items": items}, indent=2) + "\n")


def complete(n: int) -> dict:
    return {"phase": COMPLETE, "work_item_type": "process", "governing_workflow_version": "2.2",
            "reviewed_implementation_head": f"{n:040x}", "last_transition": f"2026-10-0{n}T00:00:00Z"}


def init_origin(repo: Path) -> None:
    git(repo, "init", "-q")
    git(repo, "remote", "add", "origin", "https://github.com/octo/example.git")


def build_recipe(repo: Path, home: Path, *, extra_archive: str | None = None) -> None:
    """Four merged items (three kept, the oldest finished), one open item, a
    finished review folder with a tracked file, and a symlinked `.removing`."""
    init_origin(repo)
    copy_scripts(repo)
    items = {f"item-{n}": complete(n) for n in (1, 2, 3, 4)}
    items["open-item"] = {"phase": "IMPLEMENTING", "work_item_type": "process",
                          "governing_workflow_version": "2.2"}
    write_state(repo, items)
    folder = repo / ".ai-review" / "item-1"
    folder.mkdir(parents=True)
    (folder / "REVIEW.md").write_text("review\n")
    git(repo, "add", "-f", ".ai-review/item-1/REVIEW.md")
    archive_dir = home / ".local" / "share" / "workflow-archive" / "example"
    archive_dir.mkdir(parents=True)
    (archive_dir / ".removing").symlink_to(home)
    if extra_archive:
        (archive_dir / f"{extra_archive}.tar.zst").write_bytes(b"archive")


def run_real(repo: Path, home: Path) -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "LANG": "C.UTF-8"}
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", DRIVER, str(repo)], cwd=str(repo),
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    return json.loads(proc.stdout)
