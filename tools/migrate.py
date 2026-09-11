#!/usr/bin/env python3
"""Deterministic extraction of the frozen Workflow release into this
repository's canonical distribution.

Reads the frozen upstream tag through `git show <commit>:<path>` only --
never the upstream working tree, which carries unrelated in-flight work --
classifies every path at that commit through `migration/classification.json`,
and materializes:

  distribution/workflow/<version>/payload/     byte-identical Workflow files
  distribution/workflow/<version>/fixtures/    host documents the frozen suite lints
  distribution/workflow/<version>/templates/   clean repository-local initial state
  distribution/workflow/<version>/manifest.json  every upstream path's disposition

The manifest is the migration inventory: every path at the frozen commit
appears in it exactly once, either as a materialized artifact with its
sha256 or as an exclusion carrying its category and rationale.

Usage:
    python3 tools/migrate.py [--upstream PATH] [--check]

`--check` re-derives everything into a temporary tree and diffs it against
what is committed, without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLASSIFICATION_PATH = REPO_ROOT / "migration" / "classification.json"
DEFAULT_UPSTREAM = Path.home() / "Workspace" / "repflow-android"

#: Categories whose files are copied verbatim into the payload.
PAYLOAD_CATEGORIES = ("distribution", "conformance")
#: Categories whose files are copied verbatim into the host fixture tree.
FIXTURE_CATEGORIES = ("host-evidence",)
#: Categories that are never materialized from upstream bytes.
EXCLUDED_CATEGORIES = ("template", "repo-local-state", "historical", "upstream-specific")


class MigrationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Frozen upstream access (read-only)
# ---------------------------------------------------------------------------


def _git(upstream: Path, *args: str, binary: bool = False):
    proc = subprocess.run(
        ["git", "-C", str(upstream), *args],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise MigrationError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout if binary else proc.stdout.decode("utf-8")


def frozen_tree(upstream: Path, commit: str) -> dict[str, dict]:
    """`{path: {"mode": ..., "blob": ...}}` for every file at `commit`."""
    entries: dict[str, dict] = {}
    for line in _git(upstream, "ls-tree", "-r", commit).splitlines():
        meta, path = line.split("\t", 1)
        mode, obj_type, blob = meta.split()
        if obj_type != "blob":
            raise MigrationError(f"unexpected object type {obj_type!r} at {path!r}")
        entries[path] = {"mode": mode, "blob": blob}
    return entries


def frozen_bytes(upstream: Path, commit: str, path: str) -> bytes:
    return _git(upstream, "show", f"{commit}:{path}", binary=True)


def verify_frozen_commit(upstream: Path, spec: dict) -> None:
    """The tag must still resolve to the commit the classification pins."""
    tag = spec["tag"]
    commit = spec["commit"]
    resolved = _git(upstream, "rev-list", "-n", "1", tag).strip()
    if resolved != commit:
        raise MigrationError(
            f"upstream tag {tag!r} resolves to {resolved!r}, not the pinned {commit!r}"
        )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class Classifier:
    def __init__(self, spec: dict):
        self.categories = spec["categories"]
        self.rules = []
        for index, rule in enumerate(spec["rules"]):
            if rule["category"] not in self.categories:
                raise MigrationError(f"rule {index} names unknown category {rule['category']!r}")
            self.rules.append((re.compile(rule["pattern"]), rule, index))

    def classify(self, path: str) -> tuple[dict, int]:
        for compiled, rule, index in self.rules:
            if compiled.search(path):
                return rule, index
        raise MigrationError(
            f"unclassified upstream path {path!r} -- every path at the frozen commit "
            f"must match a rule in migration/classification.json"
        )


# ---------------------------------------------------------------------------
# Template generation (deterministic, no upstream bytes except where noted)
# ---------------------------------------------------------------------------


def serialize_state(state: dict) -> bytes:
    """`workflow_state._serialize_state`'s canonical form, reproduced here so
    the generator does not import the payload it is generating: JSON, two-space
    indent, no ASCII escaping, insertion order preserved, one trailing newline.
    `tests/test_templates.py` asserts this against the migrated module."""
    return (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


CLEAN_STATE = {"schema_version": 1, "active_work_item_id": None, "work_items": {}}

GITIGNORE_FRAGMENT = """\
# --- AI Workflow (managed by workflow-manager) ---
.ai-review/
__pycache__/
*.pyc
"""

ACTIVE_MILESTONE_TEMPLATE = """\
# Active Milestone

## Milestone

None. No work item is active in this repository yet.

## Goal

Set by the work item's own plan document when one is activated.

## Current checkpoint

None.

## Current blockers

None.

## Active plan

None. `/milestone-plan` records the plan document path on the work item's
`WORKFLOW_STATE.json` entry when a work item is created.

## Functional review checklist

Empty. `/prepare-functional-review` writes the numbered checklist for the
active work item into this section; `/apply-functional-review` and
`/accept-milestone` read it back from here.

<!--
This file is `workflow_state.FUNCTIONAL_CHECKLIST_PATH`. It is
repository-local state: workflow-manager generates it once at bootstrap and
never overwrites it on update.
-->
"""

CLAUDE_MD_TEMPLATE = """\
# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

## Semi-autonomous workflow gates

Work follows the state machine in `docs/ai-workflow/MILESTONE_WORKFLOW.md`.
Claude works autonomously between gates but must stop and wait at every hard
gate that document names -- see its "Hard gates summary" for the current
count and list, which changes as the workflow evolves; do not hardcode a
count here.

Use the commands in `.claude/commands/` to drive each state. Do not skip a
gate because the diff looks small.

## Workflow documents

- Milestone state machine: `docs/ai-workflow/MILESTONE_WORKFLOW.md`
- Two-stage plan review: `docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`
- Bundle mechanics and feedback format: `docs/ai-workflow/REVIEW_PROTOCOL.md`
- Phase/command reference: `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`
- Current work-item state: `docs/ai-workflow/WORKFLOW_STATE.json` (ground
  truth -- never inferred from plan text)
- Active work item narrative: `docs/ACTIVE_MILESTONE.md`

## Git restrictions

- Commits are normally prohibited. Only commit when a workflow command
  explicitly authorizes it after verification gates pass.
- Never push, merge, rebase, force-push, or open a pull request.
- Don't touch unrelated working-tree changes.

<!--
Sections above this marker are managed by workflow-manager and are replaced
on update. Add repository-specific guidance below it; it is never touched.
-->

<!-- workflow-manager:end -->
"""

CI_WORKFLOW_TEMPLATE_HEADER = """\
# AI Workflow conformance suites (managed by workflow-manager).
#
# These are exactly the hermetic, stdlib-only suites the frozen Workflow
# release runs on every pull request. The two `*_demo_test.py` suites are
# deliberately absent: they classify content from a fixed historical base
# commit, so an unrelated later change would fail them for reasons that are
# not a Workflow regression. Run those explicitly when you want them.
name: Workflow conformance

on:
  pull_request:
  push:
    branches: [main]

jobs:
  workflow-conformance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
"""

#: The hermetic suites, in the order the frozen upstream CI runs them.
#: `tests/test_templates.py` proves this list equals the set of
#: `python3 <suite>` commands in the frozen upstream ci.yml.
CI_SUITES = (
    "workflow_fingerprint_test.py",
    "workflow_state_test.py",
    "workflow_test_harness_test.py",
    "workflow_integration_test.py",
    "workflow_acceptance_matrix_test.py",
    "workflow_state_completion_obligations_test.py",
    "workflow_fingerprint_generalization_test.py",
)


def render_ci_workflow() -> bytes:
    lines = [CI_WORKFLOW_TEMPLATE_HEADER.rstrip("\n")]
    for suite in CI_SUITES:
        lines.append(f"      - name: {suite}")
        lines.append("        working-directory: scripts")
        lines.append(f"        run: python3 {suite}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_templates(upstream: Path, commit: str) -> dict[str, dict]:
    """`{target path: {"bytes": ..., "source": ...}}`.

    `source` records how each template was derived, so the manifest states
    which templates are authored here and which are carried over verbatim
    from a frozen upstream file that was already generic.
    """
    config_bytes = frozen_bytes(upstream, commit, "docs/ai-workflow/WORKFLOW_CONFIG.json")
    return {
        "docs/ai-workflow/WORKFLOW_STATE.json": {
            "bytes": serialize_state(CLEAN_STATE),
            "source": "generated: empty state in workflow_state._serialize_state's canonical form",
        },
        "docs/ai-workflow/WORKFLOW_CONFIG.json": {
            "bytes": config_bytes,
            "source": "identity: frozen docs/ai-workflow/WORKFLOW_CONFIG.json is already "
                      "repository-generic (schema_version/default/supported versions only)",
        },
        "docs/ACTIVE_MILESTONE.md": {
            "bytes": ACTIVE_MILESTONE_TEMPLATE.encode("utf-8"),
            "source": "generated: clean functional-checklist scaffold; the frozen upstream file "
                      "is 1857 lines of RepFlow milestone narrative and is never copied",
        },
        "CLAUDE.md": {
            "bytes": CLAUDE_MD_TEMPLATE.encode("utf-8"),
            "source": "generated: Workflow-owned agent guidance only; the frozen upstream "
                      "CLAUDE.md is RepFlow/Android product routing and is never copied. "
                      "Installed as a managed section so a target's own CLAUDE.md survives",
        },
        ".gitignore.workflow-fragment": {
            "bytes": GITIGNORE_FRAGMENT.encode("utf-8"),
            "source": "generated: the Workflow-owned lines of the frozen .gitignore, merged "
                      "into the target's own .gitignore rather than replacing it",
        },
        ".github/workflows/workflow-conformance.yml": {
            "bytes": render_ci_workflow(),
            "source": "generated: the frozen ci.yml's seven hermetic Workflow suite steps, "
                      "lifted out of RepFlow's interleaved Gradle jobs",
        },
    }


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_file(path: Path, data: bytes, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o755 if executable else 0o644)


def migrate(upstream: Path, out_root: Path) -> dict:
    spec = json.loads(CLASSIFICATION_PATH.read_text())
    verify_frozen_commit(upstream, spec["upstream"])
    commit = spec["upstream"]["commit"]
    version = spec["workflow_version"]
    classifier = Classifier(spec)

    tree = frozen_tree(upstream, commit)
    release_root = out_root / "workflow" / version

    artifacts: list[dict] = []
    exclusions: list[dict] = []
    rule_hits = [0] * len(spec["rules"])

    for path in sorted(tree):
        rule, rule_index = classifier.classify(path)
        rule_hits[rule_index] += 1
        category = rule["category"]
        record = {
            "upstream_path": path,
            "category": category,
            "rule": rule["pattern"],
            "rationale": rule["rationale"],
        }
        if category in PAYLOAD_CATEGORIES or category in FIXTURE_CATEGORIES:
            data = frozen_bytes(upstream, commit, path)
            executable = tree[path]["mode"] == "100755"
            subtree = "payload" if category in PAYLOAD_CATEGORIES else "fixtures"
            write_file(release_root / subtree / path, data, executable)
            record.update({
                "location": f"{subtree}/{path}",
                "target_path": path,
                "sha256": sha256(data),
                "size": len(data),
                "executable": executable,
            })
            artifacts.append(record)
        elif category in EXCLUDED_CATEGORIES:
            record["upstream_sha256"] = sha256(frozen_bytes(upstream, commit, path))
            exclusions.append(record)
        else:
            raise MigrationError(f"category {category!r} has no materialization policy")

    templates = []
    for target_path, template in sorted(build_templates(upstream, commit).items()):
        write_file(release_root / "templates" / target_path, template["bytes"])
        templates.append({
            "target_path": target_path,
            "location": f"templates/{target_path}",
            "sha256": sha256(template["bytes"]),
            "size": len(template["bytes"]),
            "derivation": template["source"],
        })

    unused = [
        spec["rules"][i]["pattern"]
        for i, hits in enumerate(rule_hits)
        if hits == 0 and not spec["rules"][i].get("expect_no_match")
    ]
    unexpected_hits = [
        spec["rules"][i]["pattern"]
        for i, hits in enumerate(rule_hits)
        if hits and spec["rules"][i].get("expect_no_match")
    ]
    if unexpected_hits:
        raise MigrationError(
            f"rules declared expect_no_match but matched upstream paths: {unexpected_hits}"
        )

    manifest = {
        "schema_version": 1,
        "workflow_version": version,
        "upstream": spec["upstream"],
        "categories": spec["categories"],
        "counts": {
            "upstream_paths": len(tree),
            "artifacts": len(artifacts),
            "exclusions": len(exclusions),
            "templates": len(templates),
            "by_category": _count_by_category(artifacts, exclusions),
        },
        "unmatched_rules": unused,
        "artifacts": artifacts,
        "templates": templates,
        "exclusions": exclusions,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    write_file(release_root / "manifest.json", manifest_bytes)
    return manifest


def _count_by_category(artifacts, exclusions) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in list(artifacts) + list(exclusions):
        counts[record["category"]] = counts.get(record["category"], 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _tree_digest(root: Path) -> dict[str, str]:
    digest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            mode = "x" if os.access(path, os.X_OK) else "-"
            digest[rel] = f"{mode}:{sha256(path.read_bytes())}"
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--check", action="store_true",
                        help="re-derive into a temp tree and diff against what is committed")
    args = parser.parse_args(argv)

    if not (args.upstream / ".git").exists():
        print(f"error: no git repository at {args.upstream}", file=sys.stderr)
        return 2

    # The destructive step and the `--check` comparison are both scoped to
    # this one release directory, derived from the same
    # `migration/classification.json` field `migrate()` itself reads --
    # never a literal version string -- so a later authored release
    # (`distribution/workflow/<successor-version>/`, an untouched sibling)
    # is neither destroyed by an ordinary regeneration nor reported as
    # `extra:` by `--check` (D-Authored-Release-3).
    spec = json.loads(CLASSIFICATION_PATH.read_text())
    version = spec["workflow_version"]
    out_root = REPO_ROOT / "distribution"
    release_root = out_root / "workflow" / version

    if not args.check:
        if release_root.exists():
            shutil.rmtree(release_root)
        manifest = migrate(args.upstream, out_root)
        print(f"migrated Workflow v{manifest['workflow_version']} from "
              f"{manifest['upstream']['tag']} ({manifest['upstream']['commit'][:12]})")
        for key, value in manifest["counts"].items():
            print(f"  {key}: {value}")
        if manifest["unmatched_rules"]:
            print(f"  WARNING unmatched rules: {manifest['unmatched_rules']}")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        migrate(args.upstream, Path(tmp))
        want = _tree_digest(Path(tmp) / "workflow" / version)
        have = _tree_digest(release_root) if release_root.exists() else {}
    if want == have:
        print(f"distribution/workflow/{version}/ matches a fresh extraction of the "
              f"frozen upstream release")
        return 0
    for rel in sorted(set(want) | set(have)):
        if want.get(rel) != have.get(rel):
            state = "missing" if rel not in have else ("extra" if rel not in want else "differs")
            print(f"{state}: {rel}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
