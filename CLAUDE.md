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

# CLAUDE.md

Guidance for Claude Code in the **workflow-manager** repository.

## What this repository is

Installer, bootstrap and update tooling for the reusable AI development
Workflow. Workflow releases are authored, built and published as packages in
the `workflow` repository (`RodrigoFAbreu/workflow`); this repository pins
the releases up to 2.12.0 by digest, discovers later ones and installs them
(verified by their own `SHA256SUMS`). It is *not* RepFlow, and no RepFlow
product work belongs here.

## Hard rules

- **`~/Workspace/repflow-android` is read-only.** `2.3.1`'s origin: if
  history ever needs it, read it through `git show <commit>:<path>` against
  the frozen tag `workflow-v2.3.1`
  (`1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6`). Never write to it, never
  create a worktree in it, never rely on its working tree — it carries an
  unrelated in-flight branch.
- **A published Workflow release is immutable, and so is its pin.** This
  repository never builds, edits or re-publishes a Workflow release. A pin in
  `src/workflow_manager/published_releases.json` is never changed, and none is
  added for a release after 2.12.0: a later release needs no pin and no
  Manager release (`docs/RELEASING.md`, "A new Workflow release"). `distribution/`, `migration/`,
  `tools/migrate.py` and `tools/build_release.py` are gone since M2; read
  them at `ec38979` if history needs them.
- **Never modify frozen Workflow semantics.** If testing a release surfaces a
  genuine defect, write it up under `docs/defects/` and stop there. Repairing
  it is a Workflow release's job, in the `workflow` repository, not this
  repository's.
- **Never migrate live work-item state.** Active `WORKFLOW_STATE` entries,
  `.ai-review/`, approvals, registries and mappings for someone else's work
  items are not defaults. Targets get clean templates.

## Before changing anything

```bash
python3 tests/run_all.py                          # the gate: full selection, in parallel (~5min)
python3 tests/run_all.py --select test_x.py       # run what you touched -- never a gate
python3 tests/run_all.py --jobs 1                 # serial reference (slow) -- exceptional evidence only
```

Run what you touched with `--select`; gates run `python3 tests/run_all.py`.
Every Workflow gate here (checkpoint, implementation review, acceptance)
and every CI run (pull request, `main` push, nightly) runs the same full
selection: the host tests plus the newest tested release's (pins plus
`tests/tested_releases.json`) frozen suites in four fixtures. Every run first
primes the release cache with every tested version and then runs offline; a version it cannot cache is `PrimingError`
(exit 2). The first run on a machine needs the network, or a
`WORKFLOW_MANAGER_RELEASE_SOURCE` mirror.
A full-suite serial or single-shard run (`--jobs 1`, `--shards 1`, CI
`shards=1`) is exceptional evidence, not a confidence rerun. Run one only
when the approved plan or an acceptance criterion requires it, or to debug
a serial/sharded discrepancy. If an equivalent run already exists, reuse and
cite it: same `selection_digest`/`tests_digest`, its own `verdict:` the one
the gate needs, and no change since its `head` to code, tests or the runner
(for CI evidence, the verify workflow too). Docs and workflow-state commits
don't count as changes. See `docs/ARCHITECTURE.md`'s "Verification execution"
for the equivalence and staleness rules and what to record.
A run makes `src/` and `tools/` read-only until it ends; see
`docs/ARCHITECTURE.md`'s "Verification execution".
A run fails (exit 2, `OrphanProcessError`) when a test leaves an orphaned
process behind. A test that orphans on purpose is declared, with a reason,
in `tests/parallel/resources.json`'s `orphan_sources`; see
`docs/ARCHITECTURE.md`'s "Orphaned processes".

## Branches, pull requests and releases

- **Trunk model.** `main` is protected by a ruleset
  (`.github/repository/ruleset-main.json`) and changes only through pull
  requests, merged by squash. One short-lived branch per milestone
  (`milestone/<work-item-id>`).
- **The pull-request title is the release.** It must be a Conventional
  Commit (`feat: ...`, `fix(cli): ...`, `feat!: ...`), checked by the
  required `Conventional Commit title` check, and it becomes the squash
  commit's subject. `feat` releases a minor, `fix`/`perf`/`refactor`/
  `build`/`revert` a patch, `!` a major; `docs`/`chore`/`ci`/`test`/`style`
  release nothing. Check one with `python3 tools/release/release.py
  check-title "<title>"`.
- **Never edit a version.** The Git tag `vX.Y.Z` is the only version
  authority; `pyproject.toml`'s `0.0.0.dev0` is a placeholder a test pins.
  The release workflow computes, builds, tags and publishes the Manager
  package after `main`'s full run is green. It never creates a Workflow
  release.
- **Settings are data.** `.github/repository/` holds the merge settings and
  the ruleset; the repository owner applies them with the `gh api` commands
  in `docs/RELEASING.md`. Pushing, opening or merging a pull request and
  changing settings stay the user's (see "Git restrictions" above).
- **Squash merges are safe for the installed Workflow**: no reader resolves
  a SHA a completed item records (`docs/ARCHITECTURE.md`, "Squash merges
  and the installed Workflow"). Re-check that before installing a Workflow
  release that adds a history reader.

## Where things are

- The release/state boundary (packages, pins, discovery and trust, metadata,
  source, cache):
  `docs/ARCHITECTURE.md`
- How the Manager is released, what a new Workflow release needs, the
  settings commands and M2's cutover (K1-K5): `docs/RELEASING.md`
- The migration and packaging record and its evidence: `docs/MIGRATION.md`
- The pins: `src/workflow_manager/published_releases.json`
- The `manager` block a Workflow release carries: `docs/release-metadata.md`
- Frozen suite counts per release up to 2.12.0: `tests/support.py`'s
  `CI_SUITES`; for a later release, the lock (`tests/tested_releases.json`) or
  its manifest
- Frozen tests a clean target cannot pass, with reasons:
  `tests/portability_exceptions.json`

## Adding a Workflow release

A Workflow release is authored, built and published in the `workflow`
repository, never here, and **needs nothing here to be installable**: the
Manager discovers it, verifies it by its published `SHA256SUMS` and manifest
digest, and reads its downgrade posture, new-work-only fixes, gate-default
change, frozen suite counts, portability exceptions and `min_manager_version`
from the manifest's `manager` block (`docs/release-metadata.md`). A release
without the block installs with an `incomplete-inspection` warning, and
`doctor` exits 1 until the block exists. To have this repository's tests
cover the release in every pull request, one non-releasing `chore:` pull
request adds it to the lock (`docs/RELEASING.md`, "A new Workflow release"):

1. `python3 tools/release_lock.py add <version>`: downloads the published
   assets, verifies them and writes the entry to `tests/tested_releases.json`
   (the frozen suite counts, discovered, and an empty
   `portability_exceptions` list the reviewer checks, while the manifest has
   no `conformance` block).
2. `python3 tools/release_lock.py check`, then `python3 tests/run_all.py`.
   The matrix moves to the new release and the `updated` fixture updates the
   previous one to it. The conformance suite must be green against the
   fixture, and the clean target's failure set must equal the documented
   exceptions — no more, no fewer.

The nightly run adds the newest published release to the tested set without a
commit. The three tables in `compatibility.py`, `CI_SUITES` in
`tests/support.py` and `tests/portability_exceptions.json` are the built-in
record for the releases up to 2.12.0 and are not extended. A Manager release is
needed only when a Workflow release changes something the manifest cannot
carry: the package format, the detector vocabulary of the `manager` block,
the CLI, the metadata schema, `RETIRED_DEFAULT_FROM`, the `2.6.0` worktree
finding or `gate_modes(governing)`.

The first five releases pinned (`2.3.1` to `2.6.0`) were extracted (`2.3.1`)
or authored as a base plus an overlay (`2.4.0` to `2.6.0`) in this repository
before M2; `2.7.0` and later are built and published by the `workflow`
repository;
`docs/MIGRATION.md` records each, and `docs/ARCHITECTURE.md`'s "Authored
releases (history)" the mechanism. The downgrade posture in `docs/DOWNGRADE_POSTURE.md` governs every
release up to 2.12.0 and is their built-in record; a later release carries its
own in its manifest.

**Downgrade posture.** Downgrading a repository to an older Workflow release is
**unsupported** once it has used anything the older release cannot read: older
releases either wedge on newer persisted vocabulary or silently ignore it and drop
its guarantees. Never run `workflow_manager update --release-version <older>`
against a repository that has driven work items under the newer release,
requested a plan amendment, activated `"2.2"`, or written any record a release
introduced, without first checking that release's posture: per release up to
2.12.0 in [`docs/DOWNGRADE_POSTURE.md`](docs/DOWNGRADE_POSTURE.md), and for a later
release in its manifest's `manager` block (`docs/release-metadata.md`).
