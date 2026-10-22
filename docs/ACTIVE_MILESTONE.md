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

## Next action

CP2 (not-a-version, partial metadata, checksum tests).
