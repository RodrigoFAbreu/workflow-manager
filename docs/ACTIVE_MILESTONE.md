# Active Milestone

## Milestone

`manager-review-followups` (`governing_workflow_version: "2.2"`, `process`, plan
revision 10, base `3c7ad52`, branch `milestone/manager-review-followups`):
roadmap row 12, issues #39 to #52 (#50 stays open for its own milestone). A
`fix:` pull request title (`src/` changes). Plan:
`docs/ai-workflow/WORKFLOW_MANAGER_REVIEW_FOLLOWUPS_PLAN.md`.

### CP1: the floor's edges and the explicit-run "Latest available" -- complete

- `ReleaseFloorError` gains the kind `pinned-only` (`cli._floor_error`, chosen
  after `archive` and before `offline`/`none-at-floor`, with its step in
  `advice._floor`); its docstring names every kind (#39, #40, #47).
- `ReleaseMetadata` records `listed` and `listing`; `coverage.gather_metadata`
  fills them; `compatibility.explicit_latest` computes the latest of an explicit
  run (pins, locally known releases, newest listed release whose manifest was
  read) and the suffix; `Report.latest_note` renders it (#41).
- Docs: `ARCHITECTURE.md`, `exit-codes.md`, `common-problems.md`, `update.md`.
- Tests: `TestTheFloor` and `TestLatestAvailableOnAnExplicitRun` in
  `tests/test_discovery.py`, a floor-kind row test in `test_operator_ux.py`, and
  `TestTheListedReleasesOfTheMetadata` in `test_release_metadata.py`. The
  `doctor`-at-the-floor tests live in `test_discovery.py` (it has the mirror)
  rather than `test_doctor_cli.py`. I did not run them red against `3c7ad52`.

Verification: `--select` test_discovery, test_operator_ux, test_release_metadata,
test_doctor_cli, test_compatibility, test_docs green; full gate
`python3 tests/run_all.py` exit 0 (14658 tests, head `67c0eeb` plus this
checkpoint's working tree).

## CP2 -- not-a-version, partial metadata, checksum tests (#42, #43, #46)

- `source.py`: `ReleaseNotPublishedError` gains `origin` and the kind
  `not-a-version`; `not_a_version()` is raised where the source's `location`
  and the cache's `cached` and trust decision first see a non-strict name,
  before the pin or discovery question (a strict unpinned name stays `unpinned`).
- `cli.py`: `_refuse_unparseable_record` runs in `status`/`verify` (no typed
  `--release-version`, no `--release-dir`), `doctor`, `update --dry-run` and, via
  `_floor`, a bare `update`, which no longer installs over a damaged record.
- `advice.py`: the `not-a-version` row reads `origin` and the command. For
  `status`/`verify` it also names the unpackaged `--release-dir DIR` run, which
  the replaced scalar-record step did (found by the full gate).
- #43/#46: no parser change was needed; the new refusal rows, the accepted-partials
  table, the repeated-name tests and the cache-entry test all passed against the
  existing code. `docs/release-metadata.md` gains two sentences.
- Docs: `ARCHITECTURE.md`, `common-problems.md` (a paired row), `release-metadata.md`.
- Tests: `TestNotAVersionRows` (`test_operator_ux.py`), the non-strict and scalar
  tests in `test_discovery.py` and `test_operator_ux_readonly.py`, `test_release_source.py`.
  I did not run them red against the previous commit.

Verification: `--select` test_discovery, test_operator_ux, test_operator_ux_docs,
test_operator_ux_readonly, test_release_metadata green; full gate
`python3 tests/run_all.py` exit 0 (14667 tests, head `51f3a22` plus this
checkpoint's working tree) after one fix of the first run's single failure.

## CP3 -- the two CLI tests (#48, #49)

- #48, `TestOnlyAStrictVersionBuildsAPath` in `tests/test_discovery.py`: a record
  naming `../escaped` is driven through `status`, `verify`, `doctor`,
  `doctor --release-version`, `update --dry-run` (with and without an option) and a
  bare `update`; each gives its row's cause, step and exit code, and the tree
  around the cache and the target's files are unchanged. `status`/`verify` with a
  valid option report the version mismatch, not a refusal, and create nothing
  outside the cache.
- #49, `TestTheFloor` in `tests/test_discovery.py` (it has the mirror; the
  `doctor`-at-the-floor tests already live there since CP1, so
  `test_doctor_cli.py` is unchanged): `doctor` exits 0 on an up-to-date discovered
  installation whose cache entry is bound to a source that is now gone; the
  offline line is on stderr, nothing is written. The cache entry is only trusted
  for the very source that wrote it, so the source is the same path, removed.
- The synthesized mirror release carries no `manager` block; `doctor` still
  reports "nothing found" for it. Tests only; `src/` unchanged. The tests passed on
  the first run (the behaviour existed); I did not run them red.

Verification: `--select test_discovery.py` green (68 tests); full gate
`python3 tests/run_all.py` exit 0 (14669 tests, head `1d6ea94` plus this
checkpoint's working tree).

## CP4 -- orphan-key overlap, the nightly cache entry, the roadmap (#51, #52)

- #51: `resources.parse` records which `orphan_sources` key declared each unit and
  refuses a second declaration with a `ResourcesFileError` naming both keys and
  the unit (a concrete `frozen:<v>/...` key and a `frozen:*/...` key for the same
  unit; the later one used to overwrite the earlier). Test in
  `test_parallel_runner.py`: the overlap is refused with both keys named, and a
  wildcard plus a concrete key for different units load.
- #52: `tools/lock_digest.py` (`digest(lock, committed)`, plus a command line
  printing the key suffix: empty for an equal lock, else `-` and 16 hex digits).
  In `workflow-manager-verify.yml`, `plan`, `shard` and `aggregate` compute the
  suffix in a `digest` step before the cache step and use
  `steps.digest.outputs.suffix`; `package` keeps the base key. No cache key uses
  `github.run_id` any more. Tests in `test_release_workflows.py`
  (`TestLockDigest`, the key test). `ARCHITECTURE.md`'s "Nightly" bullet says it.
- The first full run found three existing tests that pinned the run-id key
  (`TestCiWorkflowStructure` and `TestOneRequiredCheck` in
  `test_parallel_runner.py`, `TestTheVerifyWorkflow` in `test_tested_releases.py`,
  which the plan's file list does not name); they now pin the digest suffix, the
  unsuffixed `package` key and the plan job's seven steps.
- Roadmap: the row and section 12 no longer list #50 among the fixes; the "Later"
  list keeps only #50 (the thirteen closed issues are gone). Row 12 turns Done at
  acceptance, not here.
- Dispositions (plan section 1): #44 and #45 dropped, #43 and #46 tests only,
  #50 follow-up, the rest fixed.

Verification: `--select test_parallel_runner.py` and
`--select test_release_workflows.py` green; the workflow file parses (its tests
load it). Full gate `python3 tests/run_all.py` exit 0 (14674 tests, head `db3ab6a`
plus this checkpoint's working tree) after fixing the first run's three failures.

## Self-review and the full gate

The full milestone diff (`3c7ad52..0110581`) was reviewed against the plan.
Corrections (`0110581`):

- The nightly's digest step now assigns `tools/lock_digest.py`'s output before
  writing it, so `bash -e` fails the step when the tool exits 2; an `echo` of
  the command substitution hid the failure and dropped the suffix. A test pins
  the assignment form.
- `docs/exit-codes.md`'s "Maintainer tools", which the tool's docstring cites,
  documents `tools/lock_digest.py`; a test pins the mention.

Red-first evidence (plan CP1, run after the fact): a clone at `0110581` with
`src/`, `tests/parallel/resources.py` and the verify workflow restored to
`3c7ad52` and `tools/lock_digest.py` removed, `--select` test_discovery,
test_operator_ux, test_operator_ux_readonly, test_release_metadata,
test_release_source, test_parallel_runner, test_release_workflows and
test_tested_releases: exit 1. 26 of the 32 new tests fail there (every
changed behaviour: the `pinned-only` kind, the explicit-run latest and its
suffixes, `not-a-version` and its record-sourced steps, the bare update over a
damaged record, the orphan-key overlap, the digest). The other six are guards,
as the plan says: the repeated-filename pin and cache-entry tests (#46), the
accepted partials (#43), `doctor` with an unreadable source (#49), the
`--pinned-only` latest line and the `update --release-version` repair route
(both unchanged). Five existing tests this milestone updated also fail there.

Full gate: `python3 tests/run_all.py` exit 0 at `0110581` (2250/2250 units,
14674 tests, selection_digest `a900814635eb`..., tests_digest `fa2ca93dbb9e`...).

## Functional review checklist

Scope: `manager-review-followups` (issues #39-#49, #51, #52; #50 stays open).
Every flow below runs offline against the pinned release cache, a scratch
target and the repository checkout; none needs GitHub, `claude`, `codex` or
`ssh`. Run them from a scratch directory outside the clone; the clone is
read-only.

### Setup

```bash
REPO=/home/rodrigo/Workspace/workflow-manager
S=$(mktemp -d); export HOME=$S/home XDG_CACHE_HOME=$S/cache PYTHONPATH=$REPO/src
mkdir -p $HOME $S/t && git -C $S/t init -q
wm() { python3 -m workflow_manager "$@"; }
```

Test data: none to seed. A bootstrap installs the pinned 2.12.0 into `$S/t`.
Needs the release cache (primed by a prior `run_all.py`) or a
`WORKFLOW_MANAGER_RELEASE_SOURCE` mirror.

### Flows

1. **Offline bootstrap with `--pinned-only`.**
   `wm --pinned-only bootstrap $S/t` then `wm --pinned-only status $S/t`.
   Expect: exit 0, "bootstrapped workflow 2.12.0 (full)", status names the same
   version and a package source.
2. **Damaged record: a non-version name (#42, #48).** Replace the record's
   `workflow_version` with `../escaped`:
   `sed -i 's/"workflow_version": "[^"]*"/"workflow_version": "..\/escaped"/' $S/t/.workflow-manager/installation.json`.
   Run `wm --pinned-only doctor $S/t`, `wm --pinned-only update --dry-run $S/t`,
   `wm --pinned-only update $S/t`, `wm --pinned-only verify $S/t`.
   Expect for each: exit 1 (doctor included), cause "the installation record
   names '../escaped', which is not a version: a release is named X.Y.Z", a
   `next:` step that names repairing the record or
   `--release-version X.Y.Z update`, and nothing created outside `$S/cache`
   (`find $S -newer` / compare `ls $S`); `$S/t` is unchanged by the bare
   `update`.
3. **Typed non-version option (#42).** `wm --release-version v2.12.0 status $S/t`
   (restore the record first). Expect exit 1, cause "release 'v2.12.0' is not a
   version: a release is named X.Y.Z", step "name a release as X.Y.Z" with
   `--release-version 2.12.0`; no mention of the installation record.
4. **Null record version (bare update).** Set `"workflow_version": null` in the
   record; `wm --pinned-only update $S/t`. Expect: refusal naming the record
   (not an install over it), exit 1, files untouched.
5. **Floor kind `pinned-only` (#39, #40, #47).** With the record restored and a
   newer release discoverable only through a mirror, a bare
   `wm --pinned-only update $S/t` that needs it: expect the floor error with
   the step "run the command again without --pinned-only (and with
   WORKFLOW_MANAGER_PINNED_ONLY unset)". Needs a mirror with a release above
   2.12.0; skip if none (the tests `TestTheFloor` cover it).
6. **Explicit-run "Latest available" (#41).** `wm --release-version 2.12.0
   status $S/t`: the report's Latest available line reflects pins, cached
   releases and the newest listed release whose manifest was read, with its
   suffix; with `--pinned-only` it names the pins only.
7. **`doctor` offline with a stale cache entry (#49).** On a clean
   up-to-date install with no network, `wm doctor $S/t` exits 0 with the
   offline line on stderr and writes nothing.
8. **Orphan-key overlap (#51).** In a scratch copy of
   `tests/parallel/resources.json` (never the clone's), declare both
   `frozen:2.12.0/<unit>` and `frozen:*/<unit>` for the same unit and load it
   with `python3 -c 'from tests.parallel import resources; ...'` from a
   copy of the repo; expect `ResourcesFileError` naming both keys and the
   unit. A wildcard plus a concrete key for different units loads. Simplest:
   `python3 tests/run_all.py --select test_parallel_runner.py` (writes
   scratch only if run from a writable copy).
9. **Nightly cache key (#52).** `python3 tools/lock_digest.py` (lock vs the
   committed one: run from the clone, read-only): an equal lock prints an
   empty suffix; a modified copy prints `-` and 16 hex digits; an unreadable
   lock exits 2. Confirm `.github/workflows/workflow-manager-verify.yml` uses
   `steps.digest.outputs.suffix` in `plan`, `shard`, `aggregate` and no cache
   key uses `github.run_id`.
10. **Docs.** `docs/release-metadata.md` says `signals` is not nullable and
    explicit `null` is accepted only on nullable fields; `exit-codes.md`,
    `common-problems.md`, `update.md` and `ARCHITECTURE.md` describe
    `pinned-only` and `not-a-version`.

### Known limitations and out of scope

- #50 (2.14.0 downgrade-posture wording) is a separate milestone.
- #44 and #45 were dropped; #43 and #46 added tests only (no parser change).
- Flow 5 needs a mirror holding a release above 2.12.0; the CI workflow change
  (flow 9) is only exercised for real by the next nightly/PR run.
- The red-first evidence is recorded above; no GitHub flow is needed.

## Next action

Functional testing by the user (gate); findings go to the scoped
`FUNCTIONAL_REVIEW.md`, then `/accept-milestone` or `/apply-functional-review`.
