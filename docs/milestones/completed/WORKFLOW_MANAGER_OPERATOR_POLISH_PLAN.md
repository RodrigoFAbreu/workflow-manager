# Workflow Manager: Operator Polish from the Functional Review, #84 (Revision 1)

`work_item_id: operator-polish` -- `governing_workflow_version: "2.2"`

**Deliverable:** four wording and consistency fixes in what the CLI prints and
the docs say (issue #84, items 1 to 4): a null `workflow_version` in the
installation record is refused as "has no `workflow_version`", not as
`names None`; `doctor` prints the "discovered, no pin" note once per run;
`status` stops after a not-a-version refusal of the typed release; and
`docs/exit-codes.md` and `docs/update.md` list the not-a-version refusal with
its exit codes.

**Work item type:** `process`. **Base commit:** `5c06591` (tip of `main`;
Workflow 2.19.2 installed, automatic gates). **Branch:**
`milestone/operator-polish`. **Scope source:** `docs/ROADMAP.md` row 14 and the
text of issue #84. `src/` changes, so the pull request title is `fix: ...` (a
Manager patch release, 1.13.4, follows the merge; checked with `python3
tools/release/release.py check-title`). **Not in this milestone:** issue #84's
fifth item, the nightly `package` job's cache key, is a CI change and ships in
its own `ci:` pull request (no release). Exit codes, options, state, release
sources, pins and Workflow releases are unchanged: no new mechanism, no
exit-code change, two checkpoints (the sizing rule's limits).

## 1. Decisions

**Item 1: say what the record holds.** `source.not_a_version(version,
origin="record")` builds `the installation record names None, which is not a
version`. For `None` (a `null` `workflow_version`) the cause becomes `the
installation record has no workflow_version (it is null), which is not a
version: a release is named X.Y.Z`. Every other value keeps today's text
(`names 'weird', which is not a version`). The null wording deliberately keeps
the shared fragment `which is not a version`, so the existing
`docs/common-problems.md` row (which `docs/update.md` links for the fix) still
matches what an operator searches for, and that page needs no edit and no new
declaration (it is classified at neither stage; the plan chooses not to touch
it). The one existing test that asserts the old null text,
`tests/test_operator_ux.py`'s
`TestNotAVersionRows.test_a_null_record_is_refused_by_a_bare_update_as_by_the_dry_run`
(`CAUSE_RECORD.format(None)`), is updated to the new cause in CP1; every other
existing assertion (`names 'weird'`, `'../escaped'`) stays true unchanged. The step (`advice._not_a_version`, origin `record`) already names one next
step and is unchanged; the exit code (1 for a bare `update`) is unchanged.

**Item 2: each distinct discovery note prints once per invocation.**
`ReleaseCache.resolve` logs `using release V, discovered from SRC: this Manager
has no pin for it` whenever it opens a discovered release. `doctor` (and
`update --dry-run`, which shares the code) opens two: the target release, and
the installed one through `cli._installed_resolves`, a probe whose only result
is a boolean for the `not-verified` finding. The probe is a duplicate only when
it opens the same release from the same source as the target
(`cmd_doctor` resolves the target separately from the installed release,
`cli.py`): with a pinned or differently discovered target, the probe's note is
the sole or a distinct one and must stay (review EPR-001). Silencing the probe
is therefore wrong; the suppression is conditional on what was already said.
Decision: the note goes through `source._log_once`, which prints a message only
if the identical text (it names the release and the source) has not been
printed earlier in the invocation. The record is a module-level set in
`source.py`, cleared at the start of `cli.main`, so each invocation (a test
calls `main` repeatedly in one process) prints its notes afresh. Only the
discovery note uses it; every other stderr line (a discarded or refetched cache
entry, `not-verified`) is unchanged, and no signature changes: `resolve` and
`_installed_resolves` keep their parameters.

**Item 3: a refused typed release ends `status`.** `cmd_status` on a managed
target prints the record and the work in flight before it re-raises a release
error, so `--release-version v2.12.0 status T` prints the refusal after a full
report. Decision: when the error is `not-a-version` with origin `option` (the
operator typed a name that is no version, so no report can be measured against
it), `status` re-raises before printing anything, as `update` does. The typed refusal is
raised by `_resolve` (the cache's name check, `source.py`), which runs after
`_readonly_destinations`, so a containment error still prints the record first,
as today. The exit
code stays 1 (`main` maps the refusal as it does today). Other release errors
keep printing the record and the work in flight first, and a damaged record
(origin `record`) keeps printing the record, which shows the operator what
is wrong.

**Item 4: document the refusal.** `docs/exit-codes.md` gets two rows beside
the "no usable release" row: exit 1 for `bootstrap`, `update`, `update
--dry-run`, `verify` and `status` (a release name that is not `X.Y.Z`, or an
installation record whose `workflow_version` is not one, `null` included) and
exit 2 for `doctor` (same cause). `docs/update.md` "If it fails" gets one
bullet with the cause and the step, linking
[common problems](common-problems.md) for the fix. The text follows
`docs/common-problems.md`'s existing row (a bare name `X.Y.Z`, not `v2.12.0`;
`status` and `verify` accept a valid explicit `--release-version`).

## 2. Tests

All hermetic (the `_Mirror` fixtures of `tests/test_discovery.py`, no network),
no process left behind. Each behaviour test fails at `5c06591`.

* `tests/test_discovery.py`: a record with `"workflow_version": null` and a
  bare `update` exits 1, the cause names `no workflow_version`, never `None`,
  and the step is unchanged; `--release-version v2.12.0 status T` exits 1,
  prints the not-a-version refusal and nothing on stdout (no status report),
  and writes nothing. The discovery note is asserted by counting each distinct
  expected `using release` line on stderr, for `doctor` and for the shared
  `update --dry-run` path: a discovered installed release that is also the
  target (the note once); a discovered installed `7.0.2` with an explicit
  pinned `--release-version 7.0.1` target (the installed release's note, once,
  and none for the pinned one); a discovered installed `7.0.2` with a
  discovered `7.0.3` target (two lines, one naming each release, one each); a
  pinned installed release with a discovered target (the target's note once);
  and two successive `main` invocations in one process (each prints its note
  once, so the record is reset per invocation, not per process).
* `tests/test_operator_ux.py`: the null-record test above asserts the new
  cause for a bare `update` and the dry run (exit 1, step unchanged).
* `tests/test_operator_ux_docs.py`: the exit codes are checked by running the
  commands, as that file does for every other row: two rows are added to
  `EXIT_ROWS`/`FRAGMENTS` (a typed `status --release-version v2.12.0` case,
  exit 1, and a `doctor` case, exit 2, fragment `is not a version`), each with
  a meaning phrase no other row's meaning contains, so `documented_code`
  returns one code each and the page's codes equal the real ones.
* `tests/test_docs.py`: `docs/update.md` contains the `is not a version`
  refusal bullet linking [common problems](common-problems.md).

## 3. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The four fixes: null-record cause, one discovery note, status stops, docs | - | 2 | 1 |
| CP2 | Roadmap and active-milestone bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the four fixes

**Files:** `src/workflow_manager/source.py`, `src/workflow_manager/cli.py`, `docs/exit-codes.md`, `docs/update.md`, `tests/test_discovery.py`, `tests/test_operator_ux.py`, `tests/test_operator_ux_docs.py`, `tests/test_docs.py`.

Section 1, items 1 to 4, and section 2. `source.py`: the null-record cause in
`not_a_version`, and `_log_once` carrying the `using release` log in
`ReleaseCache.resolve`. `cli.py`: `main` clears the once-record on entry;
`cmd_status` re-raises a typed not-a-version refusal before printing the
record. `docs/exit-codes.md` and `docs/update.md`: the refusal with its exit
codes. Tests as in section 2, including the update of the existing null-record test
in `tests/test_operator_ux.py`.

Evidence: the three behaviour tests and the docs test fail first at `5c06591`
and are green after; `python3 tests/run_all.py --select test_discovery.py`,
`--select test_docs.py`, `--select test_operator_ux.py`, `--select
test_operator_ux_docs.py`, `--select test_doctor_cli.py` and `--select
test_operator_ux_report.py` green (the existing `names 'weird'` and
`'../escaped'` assertions stay green unchanged); the full gate `python3
tests/run_all.py` green.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 14 of `docs/ROADMAP.md` is marked Current when the plan starts and Done
at acceptance (item 5, the nightly cache key, noted as shipping in its own
`ci:` pull request); `docs/ACTIVE_MILESTONE.md` records the milestone. No
version is edited: the `fix:` pull request title releases the patch.

Both files stay excluded at both stages, as in every item: the workflow's own
commands write them after technical approval, so they are bookkeeping, not a
reviewed deliverable. Every deliverable (CP1) is implementation-protected.
<!-- /CP2 -->

## 4. Risks

* The once-record hides a discovery note only when an identical one (same
  release, same source) was already printed in the invocation. A probe that
  opens a different release than the target keeps its own note; a run whose
  target is the installed release (a bare `doctor` on an up-to-date
  repository) prints it once. The record is module state, reset by `main`, so
  a caller that drives `resolve` outside `main` is not deduplicated across
  calls it never reset: no such caller exists in `src/`.
* `status` for a typed not-a-version release no longer prints the record. The
  record is one `workflow-manager status T` away, and the refusal's step names
  the fix; the exit code is unchanged.
* The refusal wording is human output; scripts use the exit codes
  (`docs/exit-codes.md`).

## 5. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
