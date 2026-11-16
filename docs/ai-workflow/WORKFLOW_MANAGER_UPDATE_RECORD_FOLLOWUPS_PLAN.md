# Workflow Manager: The Update Report Advises Nothing Its Own Rules Refuse (Revision 2)

`work_item_id: update-record-followups` -- `governing_workflow_version: "2.2"`

**Deliverable:** the update and doctor report never advises a command that the
same report's own rules refuse; the strict `X.Y.Z` pattern has one home; one
code comment states the reason that holds; one dead test branch is gone. Issue
#233 (follow-ups of the dry-run parity, Manager 1.20.1). Roadmap row 47 (added
by this item, Current now, Done at acceptance). **Work item type:** `process`.
**Base commit:** `6fe15b4` (`6fe15b4ad17953a5b90b948cd2c73e42d82928f7`, tip of
`main`; Manager 1.20.1, Workflow 2.29.6 installed, automatic gates).
**Branch:** `milestone/update-record-followups`. **Release:** the text a
released command prints changes (point 2): the pull request title is `fix: the
update report names no verify command it refuses for a null or damaged record`
(`python3 tools/release/release.py check-title` says `fix, release impact
patch`: Manager 1.20.2, `docs/RELEASING.md`, releases run inside `ci.yml`,
`docs/ARCHITECTURE.md` "GitHub Actions layout"); the release-history row goes in
a `docs:` pull request afterwards. **Size:** one checkpoint, one mechanism
(*the report's advice agrees with the report's rules*); the release is the pull
request title, not a checkpoint; the plan is far under 300 lines: no split. Out
of scope: the retention commands, Workflow releases, new options, any change of
what `update` writes. Point 5 of the issue (plan text) is not editable here:
ignored.

## 1. Investigation (done at `6fe15b4`)

| Point | Class | Evidence | Consequence |
| --- | --- | --- | --- |
| 1. The null-record step's comment contradicts the code | TRUE-FIX-NEEDED | `advice.py:649-652` says the `--release-dir` clause is left out because `doctor` refuses a null record before reading any directory; `advice.py:656-660` then appends `--release-dir D is left out: name it too if D holds release X.Y.Z`. `source.local_release` (`source.py:1289-1292`) now refuses a null-manifest directory, so the directory can fail for its own reason. | rewrite the comment to the reason that holds; the printed text stays byte-identical |
| 2. The `not-verified` note advises a refused `verify` | TRUE-FIX-NEEDED, reproduced | `compatibility.py:1962-1966` builds the `verify` command with `options_for(recorded_release(facts))`, which is `options_for(None)` for a null or damaged record. Reproduced on `update --dry-run --release-dir D` (before text below): the note prints `workflow-manager --release-source S --release-cache C --release-dir D verify TARGET`. For a null record that command exits 1 with `version: the installation record has no workflow_version` and `next: a release directory is needed`; for a damaged one (`garbage`) it exits 1 with `holds release X, not the requested garbage`. The cause list in the note (offline, not pinned, failed verification) is also not the cause. `doctor` itself refuses such a record before the report, so only the dry run prints it. | for an unknown recorded release the note keeps its first sentence and says the record names no usable release; it prints no `verify` command |
| 3. Two copies of the strict pattern | TRUE-FIX-NEEDED | `compatibility._STRICT_RECORDED` (`:109`) and `source._STRICT_VERSION` (`:96`) are equal today, with no shared home, comment or test; `cli.cmd_dry_run` filters with `source.is_strict_version` (`cli.py:821`), the report's `unknown` with the copy. `compatibility.py:2355` already imports from `.source` lazily, and `source.py` does not import `compatibility`. | delete the copy; `recorded_release` calls `source.is_strict_version`; a table test |
| 4. A dead branch in `test_i3_verify_without_release_dir_after_a_scalar_install_asks_for_one` | TRUE-FIX-NEEDED | `tests/test_operator_ux_readonly.py:993` loops `(123, '')`; `version is None` (`:1003-1004`) never holds. Null-record `verify` stays covered by `tests/test_operator_ux.py:1169` and `tests/test_discovery.py:407`. | remove the branch |

Before text (null record, `update --dry-run --release-dir D`, paths shortened):
`[note] not-verified: the installed release could not be resolved` /
`Local edits ... still detected from the install record. This Manager cannot
compare ... (offline, the release is not pinned, or its package failed
verification), the comparison workflow-manager verify makes. workflow-manager
--release-source S --release-cache C --release-dir D verify TARGET makes that
comparison, or prints why it cannot.`

## 2. Design

### 2.1 The note (point 2)

In the `not-verified` branch of the next-step pass (`compatibility.py`), when
`recorded_release(facts)` is `None` the detail is replaced, otherwise it is
untouched (byte-identical, including the `verify` command):

`Local edits to release files are still detected from the install record. This
Manager cannot compare the installation with the installed release's published
package, the comparison `workflow-manager verify` makes, because the
installation record names no usable release (it is null, or not one X.Y.Z); the
update with an explicit --release-version records one.`

No command is built for that case (`options_for` is no longer called with
`None` there). The note keeps its id, severity and place, so the exit code and
the headline do not change. `docs/update.md` gets one sentence on the same
(its stamp is not moved: the page is not re-checked here).

### 2.2 One pattern (point 3)

`recorded_release` returns the name when `source.is_strict_version(name)`, else
`None`; `_STRICT_RECORDED` is deleted and `re` stays imported for other uses.
`compatibility` imports `is_strict_version` from `.source` at module level; a
cycle would show as an import error in every test file. The decision for every
shape is unchanged: the same pattern, `fullmatch`, `str` only.

### 2.3 The comment and the dead branch (points 1 and 4)

The comment in `advice.py` becomes: a `--release-dir` is left out of the command
because its release is not known (X.Y.Z is a placeholder), and a directory is
usable only if it holds exactly that release (a null-manifest or other-release
directory is refused at the source); the clause says so. The test loses its
`None` arm: the assertion is the `names` one.

## 3. Tests and failure-only mutations

Existing tests that pin the old note text (searched with `grep -rn 'not-verified\|makes that comparison' tests`):
`tests/test_operator_ux_report.py` (three tests, a valid record: unchanged),
`tests/test_doctor_cli.py` (two, valid record: unchanged) and
`tests/test_compatibility.py` (`test_an_unresolved_installed_release_is_a_note`
and its two siblings run on `Case.setUp`, which bootstraps a pinned
installation, so `recorded_release` is a valid version there and they keep the
valid-record branch: unchanged; T2 sets the record explicitly through
`facts.installation`). No test pins the old text of a null or damaged record. The docs: `docs/update.md` (the `not-verified`
bullet, still true) and `docs/exit-codes.md` (no wording of the note). The plan
documents and `docs/milestones/completed/*` are history.

| Test | Scenario | Mutation | Fails (to measure) |
| --- | --- | --- | --- |
| T1 table (`test_compatibility.py`) | `recorded_release` over `None`, `''`, `garbage`, `../escaped`, `123`, `True`, `1.2.3`, `2.12.0`, `0.0.0`, `01.2.3`, `1.2`, `1.2.3.4`, `1.2.3 `, `1.2.3\n`, and no installation at all: equal to a literal copy of the old pattern's decision and to `source.is_strict_version`; `compatibility` has no `_STRICT_RECORDED` | M3: re-add a looser own pattern (`\d+(\.\d+)*`) to `recorded_release` | T1, and T2 for `01.2.3`, `1.2` and `1.2.3.4` (the looser pattern accepts them, so they would print the valid-record note and its `verify` command) |
| T2 unit note | `build_report(..., installed_resolved=False)` with `facts.installation` set to `Installation(name, "full", {})` for each unknown shape of T1 (`None`, `''`, `garbage`, `../escaped`, `123`, `True`, `01.2.3`, `1.2`, `1.2.3.4`, `1.2.3 `, `1.2.3\n`) and to no installation: the new sentence, no `makes that comparison`, no `offline, the release is not pinned`; for a valid record the old detail and the command | M1: build the `verify` command for an unknown record again | T2, T3 |
| T3 end to end (`test_operator_ux_report.py`) | bootstrap a pinned release, set the record to `null`, `garbage`, `../escaped`, run `update --dry-run --release-dir D`: exit 0, the note, no `verify` command and no `makes that comparison`, the target's `tree_hash` equal before and after (no write) | M1 | T2, T3 |
| T4 the valid record | the three existing tests of `test_operator_ux_report.py` and the two of `test_doctor_cli.py` | M2: delete the `detail += f" `{verify}` makes that comparison, or prints why it cannot."` line, so no record gets the `verify` command | T2's valid-record arm and `test_operator_ux_report.py`'s existing tests that assert the command (`:326`, `:341`, `:410`); not `test_doctor_cli.py`'s two, which assert only the note's id |

The dead-branch removal and the comment have no behaviour: flows 3 and 5 prove
them. The unmutated tree passes every test of the touched files. The sets are
claims the implementer measures in a scratch copy and records; a difference is
repaired by changing the test or this table through an amendment, never by
weakening a claim.

**Golden (happy path and every record shape).** A scratch driver
(`$TMPDIR/repro/golden.py`, recorded in the implementation summary) bootstraps a
pinned release, sets the record to a valid version, `null`, `garbage`,
`../escaped`, `''` and `123`, and prints, for `update --dry-run --release-dir D`,
the same with `--release-version`, and `doctor --release-dir D`, rc, stdout and
stderr with the scratch path and version normalized; run once with the base `src`
(`git archive`) and once with the candidate. The valid record's three outputs are
byte-identical; the other shapes differ only in the `not-verified` note's detail.
The before set is already recorded (`$TMPDIR/repro/before`).

**Decision table for point 3 (before and after).** One table test (T1) and one
scratch run over the same list with the base `src` and the candidate: the old
and new predicates agree on every row.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The note, the shared pattern, the comment, the dead branch and the tests | - | 2 | 1 |

<!-- CP1 -->
### CP1 -- the note, the shared pattern, the comment, the dead branch and the tests

**Files:** `src/workflow_manager/advice.py`, `src/workflow_manager/compatibility.py`, `tests/test_compatibility.py`, `tests/test_operator_ux_report.py`, `tests/test_operator_ux_readonly.py`, `docs/update.md`.

Row 47 of docs/ROADMAP.md is already added (at planning, `Current`; Done at
acceptance): do not add it again. Then sections 2.1 to 2.3, tests T1 to T4, their
mutations, and the golden. `python3 tests/run_all.py --select
test_compatibility.py --select test_operator_ux_report.py --select
test_operator_ux_readonly.py --select test_operator_ux.py --select
test_doctor_cli.py --select test_docs.py` (run `python3 tests/run_all.py --list`
first if the release cache may lack a version), `python3 tools/check_docs.py`,
and `git diff --exit-code 6fe15b4ad17953a5b90b948cd2c73e42d82928f7 -- tools
.claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py
src/workflow_manager/source.py` (no output). docs/ROADMAP.md and
docs/ACTIVE_MILESTONE.md are excluded at both stages, not deliverables. The full
`python3 tests/run_all.py` runs at the implementation review and at acceptance,
never while a file is being written. Comments on #233 record what was done; it
closes at acceptance.
<!-- /CP1 -->

## 5. The declaration

`docs/ai-workflow/registry/update-record-followups-artifacts.json` classifies the
six deliverables and the source, test and tool paths named below as evidence,
and protects every deliverable. The other paths the plan names only as read or
diffed evidence (`docs/exit-codes.md`, `docs/verify.md`, `docs/retention.md`,
`docs/README.md`, `README.md`, `docs/RELEASING.md`, `docs/ARCHITECTURE.md`,
`tools/release/release.py`, `tests/run_all.py`) are not deliverables and stay
unclassified: they are expected byte-identical (flow 2 diffs them) and a changed
unclassified path fails closed. The six
deliverables (`src/workflow_manager/advice.py`,
`src/workflow_manager/compatibility.py`, `tests/test_compatibility.py`,
`tests/test_operator_ux_report.py`, `tests/test_operator_ux_readonly.py`,
`docs/update.md`) are excluded at the plan stage and protected at the
implementation stage. Evidence paths get "named in the plan, not a deliverable"
entries: `src/workflow_manager/cli.py` and `src/workflow_manager/source.py`
(protected at the implementation stage, byte-identical), and
`tests/test_operator_ux.py`, `tests/test_doctor_cli.py`, `tests/test_discovery.py`,
`tests/test_docs.py` and `tools/check_docs.py` (run or read only: excluded at both
stages; the checker is protected, byte-identical). `docs/ROADMAP.md` and
`docs/ACTIVE_MILESTONE.md` stay excluded at both stages. `tests/parallel/resources.json`
is not edited and not named. SELF_REVIEWING_PLAN edits the generated template
before the first publish and checks the paths listed here at both stages.

## 6. Functional review

Offline greps and diffs in a checkout of the candidate; `BASE` is
`6fe15b4ad17953a5b90b948cd2c73e42d82928f7`. Exit codes are read with `; echo $?`,
not through a pipe; greps exclude `docs/ai-workflow` and `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only `advice.py`, `compatibility.py`, the three test files, `docs/update.md` and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py src/workflow_manager/source.py docs/exit-codes.md docs/verify.md README.md docs/README.md docs/retention.md; echo $?` | no output, `0` |
| 3 | `grep -n -B1 -A4 'null record: the one step' src/workflow_manager/advice.py` | the comment no longer says `doctor` refuses the record before it reads any directory; it gives the reason about the unknown release and the directory's own refusal |
| 4 | `grep -rn '_STRICT_RECORDED' src tests; echo $?` and `grep -n 'is_strict_version' src/workflow_manager/compatibility.py` | no match, `1`; the import and the one use in `recorded_release` |
| 5 | `grep -n 'has no workflow_version' tests/test_operator_ux_readonly.py; echo $?` | no match, `1` |
| 6 | the golden driver of section 3 on the base `src` and the candidate's, then `diff -r` of the two output directories | the valid record: no difference in any of its three files; every other shape: only the `not-verified` detail lines differ, and the new detail names no `verify` command |
| 7 | run `verify` with the `--release-dir` of the old note for a null record (base) and read the new note for the same record | the base note's command exits 1 with the null-record message; the candidate prints none |
| 8 | `grep -n -E '^\| 47 ' docs/ROADMAP.md` and `grep -c -E '^\| 48 ' docs/ROADMAP.md` | row 47 present, last cell `Current`; `0` |
| 9 | `python3 tools/check_docs.py; echo $?` and `grep -n 'Last checked with' docs/update.md` | no problem line, `0`; the stamp still reads `Workflow Manager 1.14.6, Workflow 2.25.5` |
| 10 | in a scratch copy apply M1, M2 and M3 of section 3, then `python3 tests/run_all.py --select` the touched test files | each fails the set the table states (measured, recorded in the implementation summary); the unmutated checkout passes |
| 11 | `python3 tools/release/release.py check-title "fix: the update report names no verify command it refuses for a null or damaged record"; echo $?` | `valid title: fix, release impact patch`, `0` |

## 7. Risks

* The new note names `--release-version` as the repair; it is true for the real
  update (a named release is accepted for a null or damaged record) and the
  recovery steps of the same report already print that command.
* A module-level import of `source` from `compatibility` could form a cycle; it
  would fail every test at import, so the first `--select` run shows it.

## 8. Open decisions

* **Decided here, for the owner to veto:** the note is kept (reworded) for an
  unknown record rather than dropped, since it still says the installation could
  not be compared and the exit code and headline must not move; `docs/update.md`
  gains a sentence without a stamp move.
