# Workflow Manager

Distribution, bootstrap, and update tooling for the reusable AI development
Workflow.

Workflow Manager holds one immutable, byte-verified copy of each frozen
Workflow release and installs it into other repositories — without ever
overwriting the work-item state those repositories accumulate.

## Status

| | |
|---|---|
| Migrated release | **Workflow v2.3.1** |
| Source | `repflow-android` tag `workflow-v2.3.1` (`1f954fbb6c68`) |
| Frozen suite against the conformance fixture | **7/7 suites, 1440 tests — matching the upstream baseline** |
| Frozen suite in a bootstrapped repository | 1439 of 1440 ([one documented exception](docs/defects/v2.3.1-001-host-history-coupled-tests.md)) |

## Layout

```
migration/       classification ruleset and portability exceptions
tools/migrate.py frozen upstream release -> distribution/
distribution/    the canonical, immutable release content
src/             the bootstrapper
tests/           stdlib unittest, no third-party dependencies
docs/            the migration record, the architecture, and upstream defects
```

## Use

```bash
python3 -m workflow_manager releases                 # what is available
python3 -m workflow_manager status    /path/to/repo   # is it managed, is it clean
python3 -m workflow_manager bootstrap /path/to/repo   # install into a fresh repo
python3 -m workflow_manager verify    /path/to/repo   # drift against canonical
python3 -m workflow_manager update    /path/to/repo   # move to another release
```

`bootstrap` installs the payload, writes clean state from templates, merges
its section into `.gitignore` and `CLAUDE.md`, and records everything in
`.workflow-manager/installation.json`.

`update` replaces payload files and leaves `WORKFLOW_STATE.json`,
`docs/ACTIVE_MILESTONE.md` and `.ai-review/` untouched. It refuses to run if a
managed file was edited locally, so an intentional edit is seen rather than
discarded; `--force` overrides.

## Re-deriving the distribution

```bash
python3 tools/migrate.py            # rebuild distribution/ from the frozen tag
python3 tools/migrate.py --check    # prove the committed tree is reproducible
```

Both read the upstream repository through `git show` only. Nothing here ever
writes to it.

## Tests

```bash
python3 tests/run_all.py            # everything (~7 minutes)
python3 tests/run_all.py --fast     # skip the frozen conformance matrix
```

The upstream-comparison tests skip cleanly when the upstream repository is not
present: a migrated release is verifiable from its own manifest alone.

## Reading order

1. [`docs/MIGRATION.md`](docs/MIGRATION.md) — what was extracted, how the
   dependency closure was derived, and the evidence.
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the distribution/state
   boundary and why the layout is what it is.
3. [`docs/defects/`](docs/defects/) — upstream defects found during migration,
   documented rather than repaired.
