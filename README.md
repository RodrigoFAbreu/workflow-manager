# Workflow Manager

Distribution, bootstrap, and update tooling for the reusable AI development
Workflow.

Workflow Manager holds one immutable, byte-verified copy of each frozen
Workflow release and installs it into other repositories — without ever
overwriting the work-item state those repositories accumulate.

## Status

| Release | Origin | Frozen/authored suite against the fixture | Bootstrapped repository |
|---|---|---|---|
| `2.3.1` | upstream — `repflow-android` tag `workflow-v2.3.1` (`1f954fbb6c68`) | 7/7 suites, 1440 tests — matching the upstream baseline | 1439 of 1440 ([one documented exception](docs/defects/v2.3.1-001-host-history-coupled-tests.md)) |
| `2.4.0` | authored in this repository — `2.3.1` base plus the plan-amendment-mechanism overlay | 7/7 suites, 1498 tests — same suite set as `2.3.1`, plus 58 new cases | 1497 of 1498 (the same documented exception) |
| `2.5.0` | authored in this repository — `2.4.0` base plus the implementation-review-two-stage overlay | 7/7 suites, 1669 tests — same suite set as `2.4.0`, plus 171 new cases | 1669 of 1669 |
| `2.5.1` | authored in this repository — `2.5.0` base plus the workflow-2-5-1-checkpoint-id-compatibility overlay | 7/7 suites, 1681 tests — same suite set as `2.5.0`, plus 12 new cases | 1681 of 1681 |
| `2.6.0` | authored in this repository — `2.5.1` base plus the workflow-review-artifact-and-concurrency-hardening overlay | 7/7 suites, 1995 tests — same suite set as `2.5.1`, plus 314 new cases | 1995 of 1995 |

`workflow_manager releases` prints every release present, each release's own
`provenance` distinguishing an upstream extraction from an authored one; both
kinds install, update, and verify through the same commands below.

## Layout

```
migration/           classification ruleset, portability exceptions, and
                     any authored release's own overlay
tools/migrate.py     frozen upstream release -> distribution/
tools/build_release.py  base release + overlay -> distribution/ (authored)
distribution/        the canonical, immutable release content
src/                 the bootstrapper
tests/               stdlib unittest, no third-party dependencies
docs/                the migration record, the architecture, and upstream defects
```

## Use

```bash
python3 -m workflow_manager releases                  # what is available
python3 -m workflow_manager status    /path/to/repo   # is it managed, is it clean
python3 -m workflow_manager bootstrap /path/to/repo   # install into a fresh repo
python3 -m workflow_manager verify    /path/to/repo   # drift against canonical
python3 -m workflow_manager update    /path/to/repo   # move to another release
```

`bootstrap` installs everything the release owns, writes clean state from
templates, merges its section into `.gitignore` and `CLAUDE.md`, and records
everything in `.workflow-manager/installation.json`. It refuses if the
repository already keeps its own file where a release file goes — `scripts/`
and `.claude/commands/` are ordinary names — and lists what collided;
`--force` overwrites.

`update` replaces release-owned files and leaves `WORKFLOW_STATE.json`,
`docs/ACTIVE_MILESTONE.md` and `.ai-review/` untouched. It refuses to run if a
release file was edited locally, so an intentional edit is seen rather than
discarded; `--force` overrides.

Nothing is copied out of `distribution/` without being checked against the
release manifest first, so a damaged distribution fails the install instead of
installing something else under its version number.

Neither operation is atomic; both are re-runnable. An interrupted bootstrap or
update is repaired by running the same command again — see
[the interruption contract](docs/ARCHITECTURE.md#interruption).

With more than one release in `distribution/`, `bootstrap` and `update` mean
the newest and take `--release-version` to pin one, while `status` and
`verify` measure a target against the release its own record names.

## Re-deriving the distribution

```bash
python3 tools/migrate.py            # rebuild distribution/ from the frozen tag
python3 tools/migrate.py --check    # prove the committed tree is reproducible
```

Both read the upstream repository through `git show` only. Nothing here ever
writes to it.

An authored release (`2.4.0`, `2.5.0`, `2.5.1`, `2.6.0`) is re-derived the
same way, from its own base release and overlay instead of an upstream tag:

```bash
python3 tools/build_release.py --overlay migration/overlays/2.4.0            # rebuild
python3 tools/build_release.py --overlay migration/overlays/2.4.0 --check    # prove it reproduces
python3 tools/build_release.py --overlay migration/overlays/2.5.0            # same, for 2.5.0
python3 tools/build_release.py --overlay migration/overlays/2.5.0 --check    # prove it reproduces
python3 tools/build_release.py --overlay migration/overlays/2.5.1            # same, for 2.5.1
python3 tools/build_release.py --overlay migration/overlays/2.5.1 --check    # prove it reproduces
python3 tools/build_release.py --overlay migration/overlays/2.6.0            # same, for 2.6.0
python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check    # prove it reproduces
```

See [`docs/ARCHITECTURE.md`'s "Authored releases"](docs/ARCHITECTURE.md#authored-releases)
for the mechanism and [`CLAUDE.md`](CLAUDE.md) for the operator procedure for
adding either kind of release, including the downgrade posture an authored
release that widens closed state vocabulary creates.

## Tests

```bash
python3 tests/run_all.py            # everything (~7 minutes)
python3 tests/run_all.py --fast     # skip the frozen conformance matrix
```

The upstream-comparison tests skip cleanly when the upstream repository is not
present: a migrated release is verifiable from its own manifest alone.

## Reading order

1. [`docs/MIGRATION.md`](docs/MIGRATION.md) — what was extracted from `2.3.1`
   and how the dependency closure was derived, plus `2.4.0`'s own authored
   provenance record, both with their evidence.
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the distribution/state
   boundary, why the layout is what it is, and how an authored release is
   composed and verified.
3. [`docs/defects/`](docs/defects/) — upstream defects found during migration,
   documented rather than repaired.

For the plan-amendment mechanism itself — a work item's operator reopening
its own approved plan mid-`IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION` via
`/request-plan-amendment`, the `AMENDING_PLAN` state it enters, and how
checkpoints reconcile against the revised plan — see
`docs/ai-workflow/PLAN_AMENDMENT_MECHANISM_PLAN.md` (this repository's own
design record) and, in a repository running the installed `2.4.0` release,
its `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md`'s own
`/request-plan-amendment` section (the operator-facing contract this release
ships).
