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

## Next action

CP3 (the two CLI tests).
