# Workflow Manager: Saying What a Null Installation Record Means, and One Next Step (Revision 3)

`work_item_id: null-record-wording` -- `governing_workflow_version: "2.2"`

**Deliverable:** what the Manager prints about an installation record whose
`workflow_version` is null names the fact and gives one next step (roadmap row
22, issue #108, the follow-ups of the operator polish, #84 item 1).

**Work item type:** `process`. **Base commit:** `4cbd162` (tip of `main`;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/null-record-wording`. **Scope source:** `docs/ROADMAP.md` row 22.
A `src/` change in the Manager: the pull request title is
`fix: ...`, which releases a patch (Manager 1.14.2; checked with
`python3 tools/release/release.py check-title`). One mechanism: the wording of
what is said about a null record and its next step. Two checkpoints.

## 1. The three points, checked against main (Manager 1.14.1)

Reproduced in a scratch repository bootstrapped with 2.12.0 whose record was
set to `"workflow_version": null`, release served from the cache:

1. **A leftover `None`.** `workflow-manager --release-version 2.12.0 verify|status
   TARGET` prints `version: installed None, release 2.12.0`
   (`verify` in `src/workflow_manager/install.py`). Still true.
2. **Two next steps.** `update`, `update --dry-run` and `doctor` end with
   `next: repair or re-bootstrap the installation record
   (.workflow-manager/installation.json), or fix it with `workflow-manager
   --release-version X.Y.Z update TARGET``
   (`_not_a_version` in `src/workflow_manager/advice.py`), while
   `docs/update.md` says every error ends with a `next:` line naming one step.
   Still true.
3. **A dry run told to run a real update.** The same line, under `update
   --dry-run`, says "fix it with `... update TARGET`" without saying that
   command writes. Still true.

None is already fixed.

## 2. Decisions

* **One step: the explicit update.** It is the only alternative that is a
  command, it is proven to repair the record (the existing case
  `test_an_update_naming_the_release_is_the_repair_and_is_not_refused`, which
  this item extends to a null record: today it covers only `garbage`, so
  NRW-PL-R1-002), and it
  keeps the operator's own work. Hand repair and re-bootstrap stay in
  `docs/common-problems.md`'s row and in `docs/update.md`, not in the line.
* **The null step**, for `update`, `update --dry-run` and `doctor` (they share
  one branch; a `status`/`verify` null record keeps its own step, see section 5),
  when the record was read and its `workflow_version` is null:
  `run `<fix>` (X.Y.Z is the release to install): it updates the installation
  record to that release`. Under `--dry-run` the line adds ` -- a real update,
  not a dry run`. `<fix>` is today's rendered command, so a withheld write
  (incomplete Workflow data) still prints the existing held step.
* **`--release-dir` is left out of the null step, and the step says only what
  the Manager knows** (NRW-PL-R1-001, NRW-PL-R2-002). The record check runs
  before the release directory is read, so at that point D's content is
  unknown (`Context.release_dir_version` is still `None`): D may be a
  null-manifest directory (the one the record was bootstrapped from; `_options`
  would carry it onto `update --release-version X.Y.Z`, which is refused, `REL
  holds release None, not the requested X.Y.Z`) or a genuine release directory
  whose record was damaged by hand (carrying it is what makes the step work for
  a release that is not published). The null step therefore renders `<fix>`
  without `--release-dir` (`--release-source` and `--release-cache` are still
  carried: they say where releases come from), so the printed command installs
  the published X.Y.Z and succeeds wherever the cache or source holds it. When
  the operator passed `--release-dir D`, the step ends with `; --release-dir D
  is left out: name it too if D holds release X.Y.Z`, a clause that asserts
  nothing about D's content; without the option nothing is added. Naming D
  too is a statement the operator checks, not one the Manager makes. This is a
  change in `advice.py` only; no other command's `--release-dir` handling
  changes.
* **Which commands reach the null step with `--release-dir`** (NRW-PL-R2-001,
  reproduced on 4cbd162): `update --dry-run` and `doctor` are refused (exits 1
  and 2) and print it; a bare `--release-dir D update` is **not** refused (it
  exits 0 and rewrites the record to the version D holds, or leaves it null
  with `(no change)` for a null-manifest D), so it prints no null step and this
  item changes nothing about it. Its asymmetry with the dry run is noted in the
  follow-up issue (NRW-PL-R2-O1), not fixed here.
* **The cause stays as it is** (`the installation record has no workflow_version
  (it is null), which is not a version: a release is named X.Y.Z`); the first
  clause names the fact, the step does not repeat it.
* **The `verify`/`status` problem line**, only when the record is null:
  `version: the installation record has no workflow_version, release <V>`. The
  line still starts `version: `, so the step table (`problem_step`) is
  unaffected. A non-null record keeps `version: installed <X>, release <V>`
  byte for byte.
* **Everything else is byte-identical:** a record naming a non-null bad value
  (`../escaped`, `garbage`) keeps its two-alternative step; no exit code, no
  state and no protocol changes.
* **`docs/update.md`** says what the `next:` line names for a null record and
  where the alternatives are. Its existing sentence ("Every error ends with a
  `next:` line naming one step") is already the contract and stays.

## 3. Tests

All run the real CLI (`python -m workflow_manager`) in a copy of the shared
bootstrapped scratch repository, with the record's `workflow_version` set to
null, the release served from the offline cache as the existing cases do.

* **`verify` and `status` with `--release-version <PINNED_NEWEST>`** (new,
  `tests/test_operator_ux.py`): exit 1, the output holds `version: the
  installation record has no workflow_version, release <V>` and not
  `installed None`; the tree is unchanged.
* **A null record with `--release-dir`** (new, `tests/test_operator_ux.py`,
  so `tests/test_operator_ux_readonly.py` and its scalar-release-directory I3
  cases stay unedited), two directories: REL, a copy of the published 2.12.0
  whose `manifest.json` holds `"workflow_version": null` (the record is
  bootstrapped from it), and D, an unmodified copy of 2.12.0 (the record of a
  second target is nulled by hand). For each, `--release-dir <dir> update
  --dry-run` and `--release-dir <dir> doctor` (exits 1 and 2): exactly one
  `next:` step, without `--release-dir`, ending `; --release-dir <dir> is left
  out: name it too if <dir> holds release X.Y.Z`, and no sentence about what
  the directory holds; running the printed command (X.Y.Z swapped for
  `<PINNED_NEWEST>`) exits 0 and rewrites the record to that version, and for
  D running it with `--release-dir D` added also exits 0 (the clause is true);
  the dry run leaves the tree unchanged. The bare `--release-dir REL update` is
  asserted only as it is today (exit 0, no null step), so a later change to it
  is visible.
* **An explicit update on a null record** (extended
  `test_an_update_naming_the_release_is_the_repair_and_is_not_refused`, which
  loops over the record values `"garbage"` and `None`): exit 0, the record
  rewritten to `<PINNED_NEWEST>`, no `is not a version`, no traceback
  (NRW-PL-R1-002).
* **A non-null record keeps its line** (existing
  `test_t15_unexpected_release_and_version_lines`, unchanged): `version:
  installed`.
* **`update`, `update --dry-run` and `doctor` on a null record** (changed
  `test_a_null_record_is_refused_by_a_bare_update_as_by_the_dry_run`, plus
  `doctor`): exit codes 1, 1 and 2 as before; exactly one `next:` line; the
  step is the exact text of section 2 (no ` or `, no `repair or re-bootstrap`);
  the dry run's step holds `not a dry run` and the bare update's does not; the
  tree is unchanged.
* **A non-null damaged record is untouched** (existing
  `test_the_record_is_the_cause_for_each_command_and_its_own_step`,
  unchanged): the two-alternative step.
* **`docs/update.md`** names the null-record step (`tests/test_docs.py`,
  beside `test_update_lists_the_not_a_version_refusal`).

**Failure-only mutations** (a scratch clone, never the repository; each passes
on the real code and fails as stated):

| Mutation | Must fail |
| --- | --- |
| `verify` prints `installed None` again | the `verify`/`status` case |
| the null step is the old two-alternative text | the `update`/dry-run/`doctor` case |
| the dry-run clause is dropped | the dry-run case |
| the clause is added to a bare update | the bare-update case |
| the null step is applied to a non-null bad record too | the unchanged non-null case |
| `--release-dir` is carried onto the null step again | the null-manifest REL case |
| the clause asserts D holds no version (the removed wording) | the genuine-directory D case |
| the `left out` clause is dropped | both release-directory cases |
| an explicit `--release-version V update` is refused on a null record | the extended explicit-update case |

Evidence at implementation: `python3 tests/run_all.py --select
test_operator_ux.py --select test_docs.py --select test_discovery.py` green,
each mutation failing the case named, then the full gate
`python3 tests/run_all.py`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The null-record wording, its docs and tests | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the wording, the docs and the tests

**Files:** `src/workflow_manager/install.py`, `src/workflow_manager/advice.py`, `docs/update.md`, `tests/test_operator_ux.py`, `tests/test_docs.py`.

Section 2 and section 3. `verify` builds the null `version:` line;
`_not_a_version` returns the single step when the record was read and is null
(`Context.installed_recorded` and `installed_version is None`), rendered
without `--release-dir`.

`tests/test_discovery.py`, `tests/test_operator_ux_readonly.py`,
`docs/common-problems.md` and `src/workflow_manager/source.py` are not edited
and are not named: the first two pin messages this item does not change (a
non-null record; `verify`'s scalar-release-directory case, which does not pass
through the null `update` step), and the row in the third is still true. The
new release-directory case lives in `tests/test_operator_ux.py`.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 22 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance, and `docs/ACTIVE_MILESTONE.md` records the milestone and the
mutation results. No version is edited: the `fix:` title releases Manager
1.14.2. Both files stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 5. Not in this item

* `status` and `verify` against a null record end with `a release directory
  holding None is needed` and the `status` header reads `workflow None (...)`.
  Issue #108 names neither; they are the same wording class. A record naming
  `""` likewise still prints `version: installed , release V`. The reviewers
  raised both (NRW-PL-R1-O1, -O2); each is dispositioned as a follow-up issue
  at acceptance, so one later item closes the class.
* `docs/common-problems.md` keeps both alternatives for the record.

## 6. Functional review

Every flow runs offline with python3 and git only, outside the repository.
Set up once: `S=$TMPDIR/fr; mkdir -p $S/home $S/cand $S/base`; the candidate is
`git archive HEAD | tar -x -C $S/cand` and the base is `git archive 4cbd162 |
tar -x -C $S/base`, both from this branch's repository; copy the release cache
(`command cp -r ~/.cache/workflow-manager/releases $S/cache`; run
`python3 tests/run_all.py --list` first if it lacks 2.12.0). Define, for each
of `cand` and `base`, `WM_<name>="env -i HOME=$S/home PATH=/usr/bin:/bin
PYTHONPATH=$S/<name>/src XDG_CACHE_HOME=$S/home/.cache
XDG_CONFIG_HOME=$S/home/.config XDG_DATA_HOME=$S/home/.local/share
WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache WORKFLOW_MANAGER_PINNED_ONLY=1
GIT_CONFIG_NOSYSTEM=1 python3 -m workflow_manager"`. Build the target: `git init
-q $S/t`, one commit, `$WM_cand --release-version 2.12.0 bootstrap $S/t`, then
`sed -i 's/"workflow_version": "[^"]*"/"workflow_version": null/'
$S/t/.workflow-manager/installation.json`. In the table, `$WM` is run once as
`$WM_cand` (candidate) and, where it says so, as `$WM_base` (base).

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `$WM --release-version 2.12.0 verify $S/t` and `... status $S/t` (candidate) | exit 1; the line `version: the installation record has no workflow_version, release 2.12.0`; no `installed None`; the base prints `installed None` |
| 2 | `$WM update $S/t` (candidate) | exit 1; one `next:` line: ``run `workflow-manager --release-version X.Y.Z update <t>` (X.Y.Z is the release to install): it updates the installation record to that release``; no ` or `; the base prints the two-alternative line |
| 3 | `$WM update --dry-run $S/t` (candidate) | exit 1; the same step ending ` -- a real update, not a dry run`; the record is still null afterwards |
| 4 | `$WM doctor $S/t` (candidate) | exit 2; the same step as flow 2 |
| 4a | Bootstrap a second target with `--release-dir REL` (a copy of 2.12.0 whose `manifest.json` has `"workflow_version": null`), then `$WM --release-dir REL update --dry-run <t2>` and `$WM --release-dir REL doctor <t2>` | exit 1 and 2; one `next:` step without `--release-dir`, ending `; --release-dir REL is left out: name it too if REL holds release X.Y.Z`; running that command with 2.12.0 exits 0 |
| 4b | Null the record of `$S/t` again and run `$WM --release-dir D update --dry-run $S/t` and `... doctor $S/t`, D an unmodified copy of 2.12.0 | exit 1 and 2; the same clause with D, no claim about what D holds; running the step with 2.12.0 exits 0, and with `--release-dir D` added exits 0 |
| 5 | Set the record to `"../escaped"`, then `$WM update --dry-run $S/t` on base and candidate | the two outputs are byte-identical (the two-alternative step) |
| 6 | In the clone, `python3 tests/run_all.py --select test_operator_ux.py --select test_docs.py` (needs the full environment) | exit 0 |

## 7. Risks

* The null branch is keyed on the record the context read; a record that cannot
  be read has `installed_recorded` false and keeps today's step (covered by the
  unchanged `unreadable` row of `test_operator_ux_docs.py`).
* Wording in `docs/update.md` is checked by one text assertion; the docs link
  checker is unaffected (no new link).

## 8. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
