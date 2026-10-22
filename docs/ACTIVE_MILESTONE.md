# Active Milestone

## Milestone

`manager-review-followups` -- complete (`governing_workflow_version: "2.2"`, `process`, plan
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

## Next action

`manager-review-followups` is complete (accepted by policy 2026-10-22; the
Manager patch release follows the pull request's merge). No milestone is ready
for `/milestone-plan`: roadmap row 6 (M3) waits on the Controller's kanban
runner (C11), and #50 stays open for its own milestone.
