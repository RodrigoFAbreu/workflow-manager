# Architecture

Workflow Manager distributes a frozen Workflow release into other
repositories. Two things must never blur together, and the whole design is
arranged around keeping them apart:

- **Canonical distribution content** — immutable, versioned, byte-identical to
  a frozen upstream release. Lives in `distribution/`. Nothing writes to it
  except `tools/migrate.py`.
- **Target-repository state** — mutable, repository-local, owned by whoever
  runs the Workflow. Work items, approvals, bundles, checkpoints. Workflow
  Manager creates it once and afterwards never overwrites it.

An update replaces the first and preserves the second. That single sentence is
the reason for most of the structure below.

## Repository layout

```
migration/
  classification.json          ordered, first-match-wins ruleset over the frozen tree
  portability_exceptions.json  frozen tests a clean target cannot pass, with reasons
tools/
  migrate.py                   frozen upstream -> distribution/  (Phase A)
distribution/
  workflow/<version>/
    manifest.json              every upstream path's disposition, with digests
    payload/                   Workflow files, byte-identical, target-relative paths
    fixtures/                  host documents the frozen suite asserts on
    templates/                 clean repository-local initial state
src/workflow_manager/
  release.py                   read and verify a release from its own manifest
  fixture.py                   build disposable repositories from a release
  install.py                   bootstrap, update, drift  (Phase B)
  installation.py              the installed-version record in a target
  cli.py                       command-line entry point
tests/                         stdlib unittest, no third-party dependencies
docs/
  MIGRATION.md                 the Phase-A record and its evidence
  ARCHITECTURE.md              this file
  defects/                     upstream defects found, documented, not repaired
```

## Why payload paths are target-relative

`distribution/workflow/2.3.1/payload/scripts/workflow_state.py` installs to
`<target>/scripts/workflow_state.py`. No rewriting, no path mapping.

That is not laziness. Frozen v2.3.1 has two hard layout dependencies:

- `docs/ai-workflow/dry-run/verify_372h_lock_primitive_predicate.py` resolves
  the repository root as `Path(__file__).resolve().parents[3]`.
- `workflow_state.py` imports `workflow_fingerprint` by bare name.

An installer that rewrote paths would be a place for both to break silently.
A copy cannot.

## Install profiles

| Profile | Categories | Use |
|---|---|---|
| `runtime` | `distribution` | The Workflow operates. 34 files. |
| `full` | `distribution` + `conformance` | The Workflow operates *and* its own conformance suite runs. 58 files. |

`full` is the default. A repository that installs `runtime` only gets the
tests without the documents several of them lint, so its suite would be red
for reasons that are not regressions.

`host-evidence` is in neither profile. Those two files are the upstream
repository's own documents, kept solely so the frozen suite can be run
unchanged as migration evidence.

## What the installer owns and what it does not

Owned — replaced wholesale on update, drift-checked against the manifest:

- `scripts/` (the payload's files only)
- `.claude/commands/`
- `docs/ai-workflow/` (the payload's files only)

Created once, then never touched:

- `docs/ai-workflow/WORKFLOW_STATE.json`
- `docs/ai-workflow/WORKFLOW_CONFIG.json`
- `docs/ACTIVE_MILESTONE.md`
- `.ai-review/` (created by the Workflow itself at run time)

Merged, never replaced:

- `.gitignore` — the Workflow fragment is appended if absent
- `CLAUDE.md` — a managed section up to `<!-- workflow-manager:end -->`;
  anything below it is the repository's own

## The installation record

`.workflow-manager/installation.json` in the target records which release is
installed and the digest of every file installed from it. It is what makes
three things possible without guessing:

- **recognition** — an already-managed repository is one that has this file;
- **drift** — compare each recorded file's current digest against the manifest;
- **safe update** — a file that drifted is a local modification, and an update
  reports it rather than silently discarding it.

## Boundaries this design keeps

- Nothing in `distribution/` reads outside `distribution/`.
- Nothing in a release names the upstream checkout, except the manifest's
  provenance record and two lines of frozen design prose, both pinned by test.
- The bootstrapper is verified against disposable repositories only. It has no
  notion of a "real" consumer, and nothing here touches one.
- Controller orchestration is deliberately absent. The installation record and
  the drift report are the surfaces a controller would later build on.

## Verification strategy

Nothing here treats a successful copy as evidence. Each claim has a check that
would fail if the claim were false:

| Claim | What would catch it being false |
|---|---|
| The inventory is closed | An unclassified upstream path is a hard error in `tools/migrate.py`, not a warning. `test_migration_inventory.py` re-reads the frozen tree independently and compares. |
| Migrated bytes are the frozen bytes | Compared against `git show <commit>:<path>`, not against the manifest that was written from the same read. |
| The extraction is reproducible | `tools/migrate.py --check` re-derives into a temporary tree and diffs, including file modes. |
| Templates are deterministic | Generated twice and compared; a full re-extraction is compared digest-for-digest. |
| Templates satisfy the frozen contracts | Validated by the *migrated* `workflow_state` module, imported out of the payload. |
| Semantics are equivalent to frozen v2.3.1 | The frozen suite runs unchanged against a fixture built only from `distribution/`, and the test *counts* are asserted against the upstream baseline — a vanished or silently skipped test fails. |
| Nothing reaches back into RepFlow | No functional file in the release may name the upstream checkout; the two frozen prose lines that do are pinned by exact location and count. |
| No live state crossed over | `.ai-review/`, locks, journals, approvals and RepFlow product work items are each asserted absent. |
| A clean target behaves like v2.3.1 | The bootstrapper's own output runs the frozen suite; its failure set must *equal* the documented exception list — a new unportable test fails the build rather than being absorbed. |
| Updates preserve local work | A second release is synthesized so the release-to-release path is exercised for real: added, changed and dropped files, with live work-item state written through the installed module and compared byte-for-byte afterwards. |

The dependency closure itself was derived by ablation rather than by reading:
each candidate file was removed from a disposable repository and the frozen
suites re-run. `docs/MIGRATION.md` records what that found.

## Extension points

The bootstrapper is deliberately small. These are the seams later Workflow
Manager functionality and Controller integration are meant to build on, rather
than reaching into the internals:

| Seam | What it gives a caller |
|---|---|
| `Release` | A migrated release, addressed by version, verifiable from its own manifest. Adding a second release is adding a directory, not changing code. |
| `Release.payload_artifacts(profile)` | The install set. A new profile is one entry in `_PROFILE_CATEGORIES`. |
| `Installation` | What a repository has, as data. A Controller asking "which of my repositories are on which release" reads these files; it does not need to inspect trees. |
| `drift()` / `verify()` | A structured answer (`Drift(path, kind, detail)`), not a printed report. Fleet-wide health is a loop over targets. |
| `update()` | Returns the new record and the list of changes. Safe by default: it refuses rather than discarding local edits, so an orchestrator does not need its own guard. |
| `build_target_repo()` / `build_conformance_repo()` | Disposable repositories from a release. Any new operation can be proven against one before it touches a real consumer. |

Deliberately absent: orchestration across repositories, scheduling, rollback
history beyond `update()`'s symmetry, and any notion of a "real" consumer.
Those are Controller concerns, and building them here would fix decisions that
should stay open.

### What a second release needs

1. A classification entry for its tag and commit.
2. `python3 tools/migrate.py`, producing `distribution/workflow/<version>/`.
3. `python3 tests/run_all.py` — the conformance fixture must be green, and the
   clean target's failure set must equal the documented exceptions.

`update()` already handles files added, changed, and dropped between releases;
`tests/test_bootstrap.py::TestReleaseToReleaseUpdate` proves that against a
synthesized second release rather than waiting for a real one.
