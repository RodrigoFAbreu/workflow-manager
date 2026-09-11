#!/usr/bin/env python3
"""Authored-release production: apply a hand-authored overlay on top of a
verified base release to produce a second, sibling `distribution/workflow/
<successor-version>/` tree.

Kept separate from `tools/migrate.py`, whose contract stays "frozen upstream
tag -> distribution/" and is untouched by this tool (D-Authored-Release-1).
`tools/migrate.py` extracts upstream bytes it never authors; this tool builds
a release whose new/changed content originates in *this* repository --
`migration/overlays/<successor-version>/` -- layered on top of a named base
release's own already-verified content:

  1. verify the base release (`distribution/workflow/<base-version>/`)
     against its own committed `manifest.json` -- refuses to build from a
     base that does not match what it claims to be;
  2. classify every file under the overlay's own `payload/` tree through
     `migration/overlays/<successor-version>/classification.json` (same
     ruleset shape/category vocabulary `migration/classification.json`
     already defines -- first-match-wins rules -- scoped to only the
     overlay's own delta files, each declaring whether it `add`s a new path
     or `replace`s a base one, cross-checked against the base release's own
     manifest rather than trusted blindly);
  3. for every replaced file, record an additive `overlay_delta` field --
     `{"base_sha256": ..., "diff_sha256": ...}` -- a unified diff between the
     base file and the overlay file, so a full-file replacement carries
     provenance of *what changed*, not only what it changed to (I2);
  4. copy forward, byte-for-byte, every base payload/template/fixture file
     the overlay does not replace;
  5. write `distribution/workflow/<successor-version>/manifest.json`, whose
     `provenance` field (`{"origin": "authored", "base_release": ...,
     "overlay_commit": ...}`) distinguishes it from an upstream extraction's
     `{"origin": "upstream"}` (D-Authored-Release-2).

`distribution/workflow/<base-version>/` is only ever *read* here; output only
ever goes to `distribution/workflow/<successor-version>/`, a fresh sibling
directory -- `<base-version>` stays frozen (D-Authored-Release-3).

Usage:
    python3 tools/build_release.py --overlay migration/overlays/2.4.0 [--base 2.3.1]

`--check` re-derives everything into a temporary tree and diffs it against
what is committed, without writing -- exactly `tools/migrate.py --check`'s
own contract, adapted for a base+overlay input pair instead of a frozen
upstream commit. Reproducibility of the check needs the previously recorded
`provenance.overlay_commit` (the *build-time* HEAD, not the HEAD `--check`
happens to run under, which is later by at least the commit that added the
built tree itself) -- `--check` reads it back from the committed manifest
rather than re-deriving it, so a check run long after the build still
reproduces byte-for-byte.
"""

from __future__ import annotations

import argparse
import difflib
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
DISTRIBUTION_ROOT = REPO_ROOT / "distribution"

_EXPECTED_KINDS = ("added", "replaced")


class BuildReleaseError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, check=False)
    if proc.returncode != 0:
        raise BuildReleaseError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout.decode("utf-8")


# ---------------------------------------------------------------------------
# Overlay classification
# ---------------------------------------------------------------------------


class OverlaySpec:
    def __init__(self, spec: dict, overlay_dir: Path):
        self.spec = spec
        self.overlay_dir = overlay_dir
        self.workflow_version = spec["workflow_version"]
        self.base_workflow_version = spec["base_workflow_version"]
        self.categories = spec["categories"]
        self.rules: list[tuple[re.Pattern, dict, int]] = []
        for index, rule in enumerate(spec["rules"]):
            if rule["category"] not in self.categories:
                raise BuildReleaseError(
                    f"overlay rule {index} names unknown category {rule['category']!r}"
                )
            if rule.get("expected_kind") not in _EXPECTED_KINDS:
                raise BuildReleaseError(
                    f"overlay rule {index} must declare expected_kind: one of {_EXPECTED_KINDS}"
                )
            self.rules.append((re.compile(rule["pattern"]), rule, index))

    def classify(self, path: str) -> tuple[dict, int]:
        for compiled, rule, index in self.rules:
            if compiled.search(path):
                return rule, index
        raise BuildReleaseError(
            f"unclassified overlay payload path {path!r} -- every file under "
            f"{self.overlay_dir}/payload/ must match a rule in this overlay's own "
            f"classification.json"
        )


def _overlay_payload_paths(overlay_dir: Path) -> list[str]:
    payload_root = overlay_dir / "payload"
    paths = []
    for candidate in sorted(payload_root.rglob("*")):
        if not candidate.is_file():
            continue
        if "__pycache__" in candidate.parts:
            continue
        paths.append(candidate.relative_to(payload_root).as_posix())
    return paths


# ---------------------------------------------------------------------------
# Base-release verification (self-contained: no dependency on src/workflow_manager)
# ---------------------------------------------------------------------------


def _verify_base_release(base_root: Path, base_manifest: dict) -> None:
    problems = []
    for record in base_manifest["artifacts"] + base_manifest["templates"]:
        path = base_root / record["location"]
        if not path.exists():
            problems.append(f"missing: {record['location']}")
            continue
        data = path.read_bytes()
        if sha256(data) != record["sha256"]:
            problems.append(f"digest mismatch: {record['location']}")
    if problems:
        raise BuildReleaseError(
            f"base release {base_manifest['workflow_version']} at {base_root} failed "
            f"verification against its own manifest -- refusing to build on top of it: "
            f"{problems[:10]}{' ...' if len(problems) > 10 else ''}"
        )


# ---------------------------------------------------------------------------
# overlay_delta: byte-level provenance of a full-file replacement
# ---------------------------------------------------------------------------


def unified_diff_sha256(base_bytes: bytes, overlay_bytes: bytes, path: str) -> str:
    """sha256 of a unified diff between the base file and the overlay file.

    Reproducible from `base payload + this recorded diff` alone -- CP6's own
    conformance extension asserts exactly that reproduction (I2)."""
    try:
        base_text = base_bytes.decode("utf-8")
        overlay_text = overlay_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildReleaseError(
            f"{path}: overlay_delta diffing requires UTF-8 text content ({exc})"
        ) from exc
    diff = difflib.unified_diff(
        base_text.splitlines(keepends=True),
        overlay_text.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return sha256("".join(diff).encode("utf-8"))


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def _write_file(path: Path, data: bytes, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o755 if executable else 0o644)


def _count_by_category(artifacts: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in artifacts:
        counts[record["category"]] = counts.get(record["category"], 0) + 1
    return dict(sorted(counts.items()))


def build(
    base_version: str, overlay_dir: Path, base_dist_root: Path, out_dist_root: Path,
    *, now_commit: str | None = None,
) -> dict:
    """`base_dist_root` and `out_dist_root` are both `distribution/`-shaped
    roots (each containing a `workflow/<version>/` tree) but are deliberately
    two separate parameters, not one shared `out_root`: an ordinary build
    reads the base release and writes the successor release under the same
    real `distribution/`, but `--check` must read the base release from the
    real, committed `distribution/` while writing its trial rebuild into a
    throwaway temporary root -- the two are the same path only in the
    ordinary-build case."""
    overlay_spec = _load_json(overlay_dir / "classification.json")
    overlay = OverlaySpec(overlay_spec, overlay_dir)
    if overlay.base_workflow_version != base_version:
        raise BuildReleaseError(
            f"overlay {overlay_dir} targets base {overlay.base_workflow_version!r}, "
            f"not the requested {base_version!r}"
        )

    base_root = base_dist_root / "workflow" / base_version
    base_manifest_path = base_root / "manifest.json"
    if not base_manifest_path.exists():
        raise BuildReleaseError(
            f"no base release manifest at {base_manifest_path} -- run tools/migrate.py first"
        )
    base_manifest = _load_json(base_manifest_path)
    _verify_base_release(base_root, base_manifest)

    base_artifacts_by_path = {a["target_path"]: a for a in base_manifest["artifacts"]}
    base_templates_by_path = {t["target_path"]: t for t in base_manifest["templates"]}

    release_root = out_dist_root / "workflow" / overlay.workflow_version

    overlay_paths = _overlay_payload_paths(overlay_dir)
    rule_hits = [0] * len(overlay.rules)
    artifacts: list[dict] = []
    seen_overlay_paths: set[str] = set()

    for rel_path in overlay_paths:
        rule, rule_index = overlay.classify(rel_path)
        rule_hits[rule_index] += 1
        seen_overlay_paths.add(rel_path)

        source_path = overlay_dir / "payload" / rel_path
        data = source_path.read_bytes()
        executable = os.access(source_path, os.X_OK)

        base_artifact = base_artifacts_by_path.get(rel_path)
        if base_artifact is not None and base_artifact["location"] != f"payload/{rel_path}":
            # `base_artifacts_by_path` is keyed by `target_path`, which the
            # base manifest also assigns to non-`payload/` artifacts (the
            # `fixtures/` host-evidence documents install at a bare
            # target-relative path too). An overlay payload file whose
            # `target_path` collides with one of those is not a replacement
            # of it: treating it as one would record an `overlay_delta`
            # against the wrong base bytes and, worse, make the copy-forward
            # loop below skip the real base artifact -- silently dropping a
            # file from the release. Refuse and name it instead.
            raise BuildReleaseError(
                f"{rel_path}: the base release's artifact with this target_path lives at "
                f"{base_artifact['location']!r}, not 'payload/{rel_path}' -- an overlay "
                f"payload file cannot replace a non-payload base artifact"
            )
        actual_kind = "replaced" if base_artifact is not None else "added"
        expected_kind = rule["expected_kind"]
        if actual_kind != expected_kind:
            raise BuildReleaseError(
                f"{rel_path}: overlay classification declares expected_kind={expected_kind!r} "
                f"but the base release {'has' if base_artifact else 'has no'} this path -- "
                f"refusing to guess which is right"
            )

        record = {
            "target_path": rel_path,
            "location": f"payload/{rel_path}",
            "category": rule["category"],
            "rule": rule["pattern"],
            "rationale": rule["rationale"],
            "sha256": sha256(data),
            "size": len(data),
            "executable": executable,
        }
        if actual_kind == "replaced":
            base_bytes = (base_root / base_artifact["location"]).read_bytes()
            record["overlay_delta"] = {
                "base_sha256": base_artifact["sha256"],
                "diff_sha256": unified_diff_sha256(base_bytes, data, rel_path),
            }
        _write_file(release_root / "payload" / rel_path, data, executable)
        artifacts.append(record)

    unused = [overlay.rules[i][1]["pattern"] for i, hits in enumerate(rule_hits) if hits == 0]
    if unused:
        raise BuildReleaseError(
            f"overlay classification.json rule(s) matched no payload file under "
            f"{overlay_dir}/payload/: {unused}"
        )

    # Copy forward every base artifact the overlay does not replace --
    # `base_manifest["artifacts"]` already covers both `payload/` (category
    # `distribution`/`conformance`) and `fixtures/` (category
    # `host-evidence`) locations, exactly as `tools/migrate.py` writes them,
    # so this one loop carries both subtrees forward verbatim; the overlay
    # never touches host-evidence fixtures at all.
    for path, base_artifact in sorted(base_artifacts_by_path.items()):
        if path in seen_overlay_paths:
            continue
        data = (base_root / base_artifact["location"]).read_bytes()
        _write_file(release_root / base_artifact["location"], data, base_artifact["executable"])
        artifacts.append(dict(base_artifact))

    # Templates: 2.4.0's own suite-file set is identical to 2.3.1's (no
    # payload test file was added, removed, or renamed -- only three
    # existing suite files gained content changes), so the CI-workflow
    # template needs no regeneration here -- the deliberate no-op case
    # D-Authored-Release-5 names. Every base template is copied forward
    # unchanged; a future overlay that does change the suite-file set
    # replaces `templates/.github/workflows/workflow-conformance.yml` the
    # same way it replaces any other payload file, and this loop's
    # `seen_overlay_paths`-style skip would need extending to templates at
    # that point.
    templates: list[dict] = []
    for _path, base_template in sorted(base_templates_by_path.items()):
        data = (base_root / base_template["location"]).read_bytes()
        _write_file(release_root / base_template["location"], data, False)
        templates.append(dict(base_template))

    overlay_commit = now_commit if now_commit is not None else _git("rev-parse", "HEAD").strip()

    manifest = {
        "schema_version": 1,
        "workflow_version": overlay.workflow_version,
        # An authored release is still, transitively, provenanced from the
        # base release's own upstream tag -- copied forward unchanged, never
        # replaced (D-Authored-Release-2, B3).
        "upstream": base_manifest["upstream"],
        "provenance": {
            "origin": "authored",
            "base_release": base_version,
            "overlay_commit": overlay_commit,
        },
        "categories": base_manifest["categories"],
        "counts": {
            "artifacts": len(artifacts),
            "templates": len(templates),
            "by_category": _count_by_category(artifacts),
            "overlay_replaced": sum(1 for a in artifacts if "overlay_delta" in a),
            "overlay_added": sum(
                1 for a in artifacts
                if "overlay_delta" not in a and a["target_path"] not in base_artifacts_by_path
            ),
        },
        "artifacts": sorted(artifacts, key=lambda a: a["target_path"]),
        "templates": templates,
        # Carried forward unchanged: the overlay adds no new exclusion --
        # every excluded upstream path keeps the disposition the base
        # release's own migration already recorded for it.
        "exclusions": base_manifest.get("exclusions", []),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _write_file(release_root / "manifest.json", manifest_bytes, False)
    return manifest


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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--overlay", type=Path, required=True,
                        help="overlay directory, e.g. migration/overlays/2.4.0")
    parser.add_argument("--base", default=None,
                        help="base release version, e.g. 2.3.1 (default: the overlay's own "
                             "base_workflow_version)")
    parser.add_argument("--check", action="store_true",
                        help="re-derive into a temp tree and diff against what is committed")
    args = parser.parse_args(argv)

    overlay_dir = args.overlay if args.overlay.is_absolute() else REPO_ROOT / args.overlay
    spec_path = overlay_dir / "classification.json"
    if not spec_path.exists():
        print(f"error: no classification.json at {spec_path}", file=sys.stderr)
        return 2

    overlay_spec = _load_json(spec_path)
    version = overlay_spec["workflow_version"]
    base_version = args.base or overlay_spec["base_workflow_version"]
    release_root = DISTRIBUTION_ROOT / "workflow" / version

    if not args.check:
        if release_root.exists():
            shutil.rmtree(release_root)
        try:
            manifest = build(base_version, overlay_dir, DISTRIBUTION_ROOT, DISTRIBUTION_ROOT)
        except BuildReleaseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"built authored Workflow v{manifest['workflow_version']} from base "
              f"{base_version} + overlay {overlay_dir} "
              f"(overlay_commit {manifest['provenance']['overlay_commit'][:12]})")
        for key, value in manifest["counts"].items():
            print(f"  {key}: {value}")
        return 0

    pinned_commit = None
    existing_manifest_path = release_root / "manifest.json"
    if existing_manifest_path.exists():
        pinned_commit = _load_json(existing_manifest_path).get("provenance", {}).get("overlay_commit")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            build(base_version, overlay_dir, DISTRIBUTION_ROOT, Path(tmp), now_commit=pinned_commit)
            want = _tree_digest(Path(tmp) / "workflow" / version)
            have = _tree_digest(release_root) if release_root.exists() else {}
    except BuildReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if want == have:
        print(f"distribution/workflow/{version}/ matches a fresh build from base "
              f"{base_version} + overlay {overlay_dir}")
        return 0
    for rel in sorted(set(want) | set(have)):
        if want.get(rel) != have.get(rel):
            state = "missing" if rel not in have else ("extra" if rel not in want else "differs")
            print(f"{state}: {rel}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
