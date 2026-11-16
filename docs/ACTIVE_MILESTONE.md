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
