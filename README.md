# Workflow Manager

[![Verification](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml/badge.svg?branch=main&event=push)](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml?query=branch%3Amain+event%3Apush)
[![Nightly](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml/badge.svg?event=schedule)](https://github.com/RodrigoFAbreu/workflow-manager/actions/workflows/workflow-manager-verify.yml?query=event%3Aschedule)
[![Release](https://img.shields.io/github/v/release/RodrigoFAbreu/workflow-manager?sort=semver)](https://github.com/RodrigoFAbreu/workflow-manager/releases)

Distribution, bootstrap, and update tooling for the reusable AI development
Workflow.

Workflow Manager installs published Workflow releases into other
repositories — without ever overwriting the work-item state those
repositories accumulate. A Workflow release is an immutable package,
published by the [`workflow`](https://github.com/RodrigoFAbreu/workflow)
repository and pinned here by digest; the Manager downloads it, verifies it
against the pin, and caches it.

## Status

The pinned Workflow releases, and their suites as recorded when each was
built:

| Release | Origin | Frozen/authored suite against the fixture | Bootstrapped repository |
|---|---|---|---|
| `2.3.1` | upstream — `repflow-android` tag `workflow-v2.3.1` (`1f954fbb6c68`) | 7/7 suites, 1440 tests — matching the upstream baseline | 1439 of 1440 ([one documented exception](docs/defects/v2.3.1-001-host-history-coupled-tests.md)) |
| `2.4.0` | authored in this repository — `2.3.1` base plus the plan-amendment-mechanism overlay | 7/7 suites, 1498 tests — same suite set as `2.3.1`, plus 58 new cases | 1497 of 1498 (the same documented exception) |
| `2.5.0` | authored in this repository — `2.4.0` base plus the implementation-review-two-stage overlay | 7/7 suites, 1669 tests — same suite set as `2.4.0`, plus 171 new cases | 1669 of 1669 |
| `2.5.1` | authored in this repository — `2.5.0` base plus the workflow-2-5-1-checkpoint-id-compatibility overlay | 7/7 suites, 1681 tests — same suite set as `2.5.0`, plus 12 new cases | 1681 of 1681 |
| `2.6.0` | authored in this repository — `2.5.1` base plus the workflow-review-artifact-and-concurrency-hardening overlay | 7/7 suites, 2002 tests — same suite set as `2.5.1`, plus 321 new cases | 2002 of 2002 |
| `2.7.0` | published by the `workflow` repository (W1: Orchestration Protocol v1, the `v2.6.0-001`/`-002` follow-ups) | 8/8 suites, 2275 tests — the `2.6.0` suite set plus `workflow_protocol_test.py` | 2275 of 2275 |

`workflow-manager releases` prints every pinned release with its archive
digest and whether it is cached. Every one installs, updates and verifies
through the same commands below. The full test selection runs the newest
pinned release's frozen suites; each older release was tested once, when it
was built ([`docs/MIGRATION.md`](docs/MIGRATION.md)).

## Layout

```
src/workflow_manager/  the Manager: packages, pins, source and cache, installer, CLI
  published_releases.json  the pins: the digest of every published Workflow release
tools/               the package builder, and the Manager's own release tooling
tests/               stdlib unittest, no third-party dependencies
docs/                the architecture, the migration and packaging record, releasing,
                     and upstream defects
```

## Install

Install a release wheel; no checkout is needed:

```bash
v=X.Y.Z   # see the releases page
gh release download "v$v" --repo RodrigoFAbreu/workflow-manager --dir "wm-$v"
(cd "wm-$v" && sha256sum -c SHA256SUMS)
pipx install "./wm-$v/workflow_manager-$v-py3-none-any.whl"
workflow-manager --version
```

Releases are published automatically from `main`; see
[`docs/RELEASING.md`](docs/RELEASING.md) and the
[releases page](https://github.com/RodrigoFAbreu/workflow-manager/releases).

## Use

```bash
workflow-manager releases                  # the pinned releases, and which are cached
workflow-manager status    /path/to/repo   # is it managed, is it clean
workflow-manager bootstrap /path/to/repo   # install into a fresh repo
workflow-manager verify    /path/to/repo   # drift against canonical
workflow-manager update    /path/to/repo   # move to another release
workflow-manager --version                 # the Manager's own version
```

From a checkout, `PYTHONPATH=src python3 -m workflow_manager` is the same
command.

The Git tag is the Manager's only version authority; `pyproject.toml` holds a
placeholder. `--version` reports the installed release, a clean checkout at a
release tag as that release, and anything else as a development build. An
existing `pipx install --editable` keeps the metadata it was installed with
(`1.0.0`), so run `pipx reinstall workflow-manager` once after updating past
the trunk model.

`bootstrap` installs everything the release owns, writes clean state from
templates, merges its section into `.gitignore` and `CLAUDE.md`, and records
everything, including where the release came from, in
`.workflow-manager/installation.json`. It refuses if the repository already
keeps its own file where a release file goes — `scripts/` and
`.claude/commands/` are ordinary names — and lists what collided; `--force`
overwrites.

`update` replaces release-owned files and leaves `WORKFLOW_STATE.json`,
`docs/ACTIVE_MILESTONE.md` and `.ai-review/` untouched. It refuses to run if a
release file was edited locally, so an intentional edit is seen rather than
discarded; `--force` overrides.

Nothing is installed unchecked. A downloaded package must match its pin and
its published `SHA256SUMS`, the cached tree is re-verified against the pin on
every use, and each file is checked against the release manifest as it is
copied, so a re-published, corrupted or edited release fails the install
instead of installing something else under its version number.

The first use of a release downloads it into
`~/.cache/workflow-manager/releases`; after that every command works offline.
`--release-source` (a mirror directory or URL template), `--release-cache`
and `--release-dir` (an unpackaged release in development) change where a
release comes from; see
[`docs/RELEASING.md`](docs/RELEASING.md#installing-a-release-without-a-checkout).

Neither operation is atomic; both are re-runnable. An interrupted bootstrap or
update is repaired by running the same command again — see
[the interruption contract](docs/ARCHITECTURE.md#interruption).

`bootstrap` and `update` mean the newest pinned release and take
`--release-version` to pick another, while `status` and `verify` measure a
target against the release its own record names.

## Workflow releases

Workflow releases are authored, built and published in the `workflow`
repository. The Manager learns of a new one through a pull request that adds
its pin; [`docs/RELEASING.md`](docs/RELEASING.md#workflow-packages-adding-a-pin)
has the steps and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#packages-pins-source-and-cache)
the design. The first five releases above were extracted (`2.3.1`) or authored
(`2.4.0` to `2.6.0`) in this repository before M2 moved them out; their
records are in [`docs/MIGRATION.md`](docs/MIGRATION.md), and
[`CLAUDE.md`](CLAUDE.md) keeps the downgrade posture an authored release
that widens closed state vocabulary creates.

## Tests

```bash
python3 tests/run_all.py                      # the gate: everything, in parallel (~5 minutes)
python3 tests/run_all.py --select test_x.py   # run what you touched -- never a gate
python3 tests/run_all.py --jobs 1             # serial reference (slow) -- exceptional evidence only
python3 tests/run_all.py --help               # every mode, flag and exit code
```

CI runs the same full selection on every pull request, every push to
`main` and nightly. It runs the Manager's own tests, and the newest pinned
release's frozen suites in four fixtures, one of them a repository updated
from the release below it.

Every run first primes the release cache with every pinned version (the
first time, from the network), then runs offline. Run what you touched with
`--select`; gates run `python3 tests/run_all.py`. A full-suite `--jobs 1`
(or single-shard) run is exceptional evidence, run only when a plan requires
it or to debug a serial/sharded difference. An equivalent earlier run is
cited, not repeated, using the `evidence:` line every run prints. While a run
is live, `src/` and `tools/` are read-only; see
[`docs/ARCHITECTURE.md`'s "Verification execution"](docs/ARCHITECTURE.md#verification-execution).

## Reading order

1. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the release/state
   boundary: packages, pins, source and cache, what the installer owns, and
   how the suite runs.
2. [`docs/RELEASING.md`](docs/RELEASING.md) — how the Manager itself is
   versioned and released, how a Workflow release is pinned, and installing
   without a checkout.
3. [`docs/MIGRATION.md`](docs/MIGRATION.md) — the historical record: what was
   extracted from `2.3.1` and how, each authored release's provenance, the
   five packages' evidence, and M2's removal of the in-repository trees.
4. [`docs/defects/`](docs/defects/) — upstream defects found, documented
   rather than repaired.

For the plan-amendment mechanism itself — a work item's operator reopening
its own approved plan mid-`IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` via
`/request-plan-amendment`, the `AMENDING_PLAN` state it enters, and how
checkpoints reconcile against the revised plan — see
`docs/ai-workflow/PLAN_AMENDMENT_MECHANISM_PLAN.md` (this repository's own
design record) and, in a repository running the installed `2.4.0` release,
its `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`'s own
`/request-plan-amendment` section (the operator-facing contract this release
ships).
