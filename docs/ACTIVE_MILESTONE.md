# Active Milestone

## Milestone

`update-record-followups` -- implementing, self-review complete (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `6fe15b4`, branch `milestone/update-record-followups`): roadmap row 47 (#233). The pull request title is `fix: the update report names no verify command it refuses for a null or damaged record`, a patch release (Manager 1.20.2, checked with `tools/release/release.py check-title`: `valid title: fix, release impact patch`).

The update and doctor report never advises a command its own rules refuse. For a null or damaged installation record the `not-verified` note says that the record names no usable release and prints no `verify` command; the note of a valid record is byte-identical. The report's reading of the recorded release uses the one strict pattern (`source.is_strict_version`). One code comment states the reason that holds, and one dead test branch is gone.

The `docs/ROADMAP.md` row 47 is an uncommitted working-tree edit, deliberately: a planning row, not a deliverable.

### CP1: the note, the shared pattern, the comment, the dead branch and the tests -- complete (`25ac9be`)

- `compatibility.py`: `_STRICT_RECORDED` deleted; `recorded_release` calls `source.is_strict_version` (module-level import, no cycle). In the next-step pass the `not-verified` detail of an unknown record is the plan's sentence (section 2.1), with no command built; a valid record keeps the old detail and its `verify` command.
- `advice.py`: the null-record step's comment gives the reason that holds (the release is not known, and a directory is usable only if it holds exactly that release); the printed text is unchanged.
- `docs/update.md`: one sentence on the note of a null or damaged record (stamp not moved).
- Tests: T1 and T2 in `tests/test_compatibility.py`, T3 in `tests/test_operator_ux_report.py`; the dead `version is None` arm removed from `tests/test_operator_ux_readonly.py`.

### Self-review -- complete (one finding fixed)

- **Fixed (important):** functional-review flow 4 expects `grep -rn '_STRICT_RECORDED' src tests` to find nothing, but T1 asserted `hasattr(comp, "_STRICT_RECORDED")` and so named the deleted constant. T1 now asserts that `comp.is_strict_version` is `source.is_strict_version` and that `compatibility` holds no module-level compiled pattern equal to the old one under any name (stronger: a renamed copy fails too). Measured: M3 and a mutation that re-adds the copy (`_STRICT_RECORDED = re.compile(...)` beside `recorded_release`) both fail T1; the unmutated tree passes. A duplicated `None` in T2's loop was removed (no change in coverage).
- Mutations of plan section 3, measured in a scratch clone of `25ac9be` outside the repository (`python3 tests/run_all.py --select test_compatibility.py --select test_operator_ux_report.py --select test_operator_ux_readonly.py --select test_doctor_cli.py`): unmutated `verdict: exit 0`. M1 fails T2 (`test_an_unknown_record_gets_a_note_with_no_verify_command`) and T3 (`test_the_not_verified_note_of_a_null_or_damaged_record_names_no_verify_command`). M2 fails T2's valid arm (`test_a_valid_record_keeps_the_verify_command_in_the_note`) and the three report tests that assert the command (`test_the_not_verified_note_names_the_integrity_cause_and_verify`, `test_the_not_verified_verify_step_is_true_when_verify_finds_nothing_wrong`, `test_i1_the_verify_step_drops_a_release_dir_holding_another_release`), not `test_doctor_cli.py`. M3 fails T1 and T2 for `01.2.3`, `1.2` and `1.2.3.4`. Every set equals the plan's table.
- Golden (flow 6): `update --dry-run --release-dir D`, the same with `--release-version 2.12.0`, and `doctor --release-dir D`, for a valid, `null`, `garbage`, `../escaped`, `''` and `123` record, base `src` (`git archive 6fe15b4`) against the candidate. The valid record's three outputs are byte-identical; `doctor` is identical for every shape (it refuses the unknown record before the note); for each unknown shape the two `update` outputs differ in exactly one line, the `not-verified` detail, and the new detail names no `verify` command.
- Decision table (point 3): `recorded_release` over the fifteen rows of T1 (including no installation) gives identical results with the base and the candidate `src`.
- Flows 1, 2, 4, 5, 9 and 11 of plan section 6 run as stated and give the expected result.

### Full gate -- green

`python3 tests/run_all.py` at `e49f7b9`: full selection, 8 workers, 2438/2438 units, 16473 tests, `selection_digest 9957d343edee4613b59b75a4d916afa09d860b8240978644a6c90b09637c9ef4`, `tests_digest cce730f4ab75d8ab1e35f775411018cbf16552b55e8b53cf740720d70edc0d2b`, `verdict: exit 0`. The orphan check was on; the only orphans reported are the declared `orphan_sources`.

## Functional review checklist

Automated verification is current: the full gate ran at `e49f7b9`, and since then only `docs/ACTIVE_MILESTONE.md`, `docs/ai-workflow/WORKFLOW_STATE.json` and the uncommitted `docs/ROADMAP.md` row changed, so no code or test file differs from the gated tree.

### Setup

- A checkout of the candidate (the evidence commit on `milestone/update-record-followups`), run from the repository root. `BASE=6fe15b4ad17953a5b90b948cd2c73e42d82928f7`.
- Python 3 only. Flows 1 to 5, 8, 9 and 11 are read-only git, grep, `tools/check_docs.py` and `tools/release/release.py` runs: no network, no forge, no `claude`/`codex`/`ssh`.
- Flows 6, 7 and 10 need a scratch directory outside the clone (a scratch installation pinned to a release, a `git archive` of `BASE`'s `src`, or a scratch copy of the candidate). They never write inside the clone.

### Test data

No data is kept in the repository. Flows 6 and 7 use one scratch installation and a local release directory `D`, with the installation record set to each of: a valid version, `null`, `garbage`, `../escaped`, `''`, `123`.

### Flows

Sandbox column: **yes** = runs offline in the functional tester's sandbox; **no** = needs the full environment (noted under Known limitations).

| Flow | Sandbox | Do | Expect |
| --- | --- | --- | --- |
| 1 | yes | `git diff --stat $BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only `advice.py`, `compatibility.py`, `tests/test_compatibility.py`, `tests/test_operator_ux_report.py`, `tests/test_operator_ux_readonly.py`, `docs/update.md` and `docs/ROADMAP.md` |
| 2 | yes | `git diff --exit-code $BASE -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py src/workflow_manager/source.py docs/exit-codes.md docs/verify.md README.md docs/README.md docs/retention.md; echo $?` | no output, `0` |
| 3 | yes | `grep -n -B1 -A4 'null record: the one step' src/workflow_manager/advice.py` | the comment gives the reason about the unknown release and the directory's own refusal; it no longer says `doctor` refuses the record before it reads a directory |
| 4 | yes | `grep -rn '_STRICT_RECORDED' src tests; echo $?` and `grep -n 'is_strict_version' src/workflow_manager/compatibility.py` | no match, `1`; the import and the one use in `recorded_release` |
| 5 | yes | `grep -n 'has no workflow_version' tests/test_operator_ux_readonly.py; echo $?` | no match, `1` |
| 6 | no | Golden driver of plan section 3, run once on `$BASE`'s `src` (via `git archive`) and once on the candidate: `update --dry-run --release-dir D`, the same with `--release-version 2.12.0`, and `doctor --release-dir D`, for every record shape above. Then `diff -r` the two output directories | the valid record: no difference in any of its three outputs; every other shape: only the `not-verified` detail line differs, and the new detail names no `verify` command |
| 7 | no | For a `null` record: run the base `src`'s `verify --release-dir D`, then read the candidate's `update --dry-run --release-dir D` note for the same record | the base `verify` exits 1 with the null-record message; the candidate's note prints no `verify` command |
| 8 | yes | `grep -n -E '^\| 47 ' docs/ROADMAP.md` and `grep -c -E '^\| 48 ' docs/ROADMAP.md` | row 47 present, last cell `Current`; `0` |
| 9 | yes | `python3 tools/check_docs.py; echo $?` and `grep -n 'Last checked with' docs/update.md` | no problem line, `0`; the stamp still reads `Workflow Manager 1.14.6, Workflow 2.25.5` |
| 10 | no | In a scratch copy of the candidate, apply mutations M1, M2 and M3 of plan section 3 one at a time, then `python3 tests/run_all.py --select test_compatibility.py --select test_operator_ux_report.py --select test_operator_ux_readonly.py --select test_doctor_cli.py` | each mutation fails the set the plan's table states; the unmutated copy gives `verdict: exit 0` |
| 11 | yes | `python3 tools/release/release.py check-title "fix: the update report names no verify command it refuses for a null or damaged record"; echo $?` | `valid title: fix, release impact patch`, `0` |

Flows 1 to 5, 8, 9 and 11 were run at the candidate by the implementer and match the expectations above.

### Known limitations

- **Flow 6's golden driver is not in the repository.** Plan section 3 names `$TMPDIR/repro/golden.py`; that scratch file is not present in the run directory now. Flow 6 cannot be re-run as written until the driver is rebuilt. The shapes it covers are pinned by T2 and T3 in the test suite, which is a different check from the byte comparison of the three outputs.
- **Flows 6, 7 and 10 are not sandbox-runnable.** They need a scratch installation or copy, and `tests/run_all.py` primes the release cache first, which needs the network or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror unless the cache already holds every tested version (`python3 tests/run_all.py --list` fills it).
- Out of scope, as in the plan: the retention commands, Workflow releases, new options, any change of what `update` writes. The fix ships as Manager 1.20.2 only after the merge; #233 closes at acceptance.
- `docs/ROADMAP.md` row 47 is an uncommitted planning row, deliberately; it is not a deliverable and is not part of the evidence commit.
