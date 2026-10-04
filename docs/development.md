# Development

> For: people changing the Manager's own code or tests. Last checked with: Workflow Manager 1.4.0, Workflow 2.8.0.

Everything here is for contributors. If you only want to install or update the Workflow, use [Install](install.md) and [Update](update.md).

## Layout

```text
src/workflow_manager/  the Manager: packages, pins, source and cache, installer, CLI
  published_releases.json  the pins: the digest of every published Workflow release
tools/               the package builder, the Manager's release tooling and the docs checker
tests/               stdlib unittest, no third-party dependencies
docs/                user pages, plus the architecture, migration and releasing records
```

From a checkout, `PYTHONPATH=src python3 -m workflow_manager` is the same command as `workflow-manager`.

## Tests

```bash
python3 tests/run_all.py                      # the gate: everything, in parallel (about 7 minutes)
python3 tests/run_all.py --select test_x.py   # run what you touched -- never a gate
python3 tests/run_all.py --jobs 1             # serial reference (slow) -- exceptional evidence only
python3 tests/run_all.py --help               # every mode, flag and exit code
```

Run what you touched with `--select`; gates run `python3 tests/run_all.py`. CI runs the same full selection on every pull request, every push to `main` and nightly: the Manager's own tests, and the newest pinned release's frozen suites in four fixtures, one of them a repository updated from the release below it.

Every run first primes the release cache with every pinned version (the first time, from the network), then runs offline. A full-suite `--jobs 1` (or single-shard) run is exceptional evidence, run only when a plan requires it or to debug a serial or sharded difference. While a run is live, `src/` and `tools/` are read-only; see ["Verification execution"](ARCHITECTURE.md#verification-execution).

The documentation checks run inside the gate (`tests/test_docs.py`, using `tools/check_docs.py`). They check links and anchors, that task-page commands parse against the real command line, the page header, and that no internal ids leak onto user pages. Run them alone with `python3 tests/run_all.py --select test_docs.py`.

## The pinned Workflow releases

| Release | Origin | Suites against the fixture | Bootstrapped repository |
|---|---|---|---|
| `2.3.1` | upstream — the original project's tag `workflow-v2.3.1` | 7/7 suites, 1440 tests — matching the upstream baseline | 1439 of 1440 ([one documented exception](defects/v2.3.1-001-host-history-coupled-tests.md)) |
| `2.4.0` | authored in this repository — `2.3.1` base plus an overlay | 7/7 suites, 1498 tests — same suite set as `2.3.1`, plus 58 new cases | 1497 of 1498 (the same documented exception) |
| `2.5.0` | authored in this repository — `2.4.0` base plus an overlay | 7/7 suites, 1669 tests — same suite set as `2.4.0`, plus 171 new cases | 1669 of 1669 |
| `2.5.1` | authored in this repository — `2.5.0` base plus an overlay | 7/7 suites, 1681 tests — same suite set as `2.5.0`, plus 12 new cases | 1681 of 1681 |
| `2.6.0` | authored in this repository — `2.5.1` base plus an overlay | 7/7 suites, 2002 tests — same suite set as `2.5.1`, plus 321 new cases | 2002 of 2002 |
| `2.7.0` | published by the Workflow repository (orchestration protocol) | 8 of 8, 2275 tests | 2275 of 2275 |
| `2.8.0` | published by the Workflow repository (gate policy, pull-request reopening) | 9 of 9, 2650 tests | 2650 of 2650 |

The full test selection runs the newest pinned release's frozen suites; each older release was tested once, when it was built ([`MIGRATION.md`](MIGRATION.md)). Workflow releases are authored and published in the Workflow repository. The Manager learns of a new one through a pull request that adds its pin: see ["Workflow packages: adding a pin"](RELEASING.md#workflow-packages-adding-a-pin).

## Reading order

1. [`ARCHITECTURE.md`](ARCHITECTURE.md): the release/state boundary: packages, pins, source and cache, what the installer owns, and how the suite runs.
2. [`RELEASING.md`](RELEASING.md): how the Manager is versioned and released, how a Workflow release is pinned, and installing without a checkout.
3. [`MIGRATION.md`](MIGRATION.md): the historical record of the first five packages and how they came to be.
4. [`defects/`](defects/): upstream defects found, documented rather than repaired.
5. [`../CLAUDE.md`](../CLAUDE.md): the hard rules for working in this repository, including the downgrade posture.
