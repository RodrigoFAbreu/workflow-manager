# Workflow Manager: The Update Dry Run Matches the Real Update for Every Record Shape (Revision 2)

`work_item_id: update-dry-run-parity` -- `governing_workflow_version: "2.2"`

**Deliverable:** `update --dry-run` predicts exactly what the real `update`
does for every record shape (null, damaged, valid) and for a release
directory with a null manifest, a refusal names a cause and a step, and the
dry run still writes nothing (roadmap row 46, issue #158 points 1 to 5).

**Work item type:** `process`. **Base commit:** `da3c774`
(`da3c7747a65b5788d0f6d9530fcd379b52d7b6d2`, tip of `main`; Manager 1.20.0,
Workflow 2.29.5 installed, automatic gates). **Branch:**
`milestone/update-dry-run-parity`. **Scope source:** the owner's standing
order and issue #158 (read with all comments: there are none), roadmap row 46
(added by this item, Current now, Done at acceptance). The pull request title
is `fix: ...`, a **patch** release, Manager 1.20.1 (checked with `python3
tools/release/release.py check-title`; `docs/RELEASING.md` needs nothing more
for it, the release-history row goes in a `docs:` pull request afterwards).
One mechanism: *the dry run and the real run decide the same way for the same
input*. Two checkpoints, one review surface (the record and release-input
handling in `cli.py`, `compatibility.py` and `source.py`, with their tests and
four pages). Sizing: the measured prototype is 232 added and 65 deleted lines
over 11 files (section 3), under the 350-line limit; no split needed.

## 1. Each point on current main (evidence)

Every point was reproduced on `da3c774` with scratch repositories built from
the tests' own helpers (`build_bootstrapped_repo`, pinned release `2.12.0`).
`cli.py` lines are on the base commit.

| # | Class | Evidence on `da3c774` |
| --- | --- | --- |
| 1 | TRUE-FIX-NEEDED | `cli.py:806-810` (`cmd_dry_run`) refuses every non-null record with `_refuse_unparseable_record` before it knows whether the run chooses. With `--release-version 2.12.0` on a record `"garbage"` or `"../escaped"`: `update --dry-run` exit 1 (`the installation record names 'garbage', which is not a version`), the real `update` exit 0 (`updated T to workflow 2.12.0`). `tests/test_discovery.py:549-550` pins the dry-run refusal |
| 2 | TRUE-FIX-NEEDED | `source.local_release` (`source.py:1292-1298`) only checks that the manifest version is hashable, so a null passes. `--release-dir` of a null-manifest copy: dry run exit 0 `to workflow None`, real run `updated T to workflow None`. With a valid record `2.12.0` the real run also **destroys** it: the record afterwards is null (reproduced) |
| 3 | TRUE-FIX-NEEDED | `compatibility.py:2130` sets `explicit = None` when the target is the latest; `recovery_steps` (`compatibility.py:2031`, and the `--force` step, `compatibility.py:2054`) then renders `workflow-manager update T`, which a null or damaged record refuses. Reproduced on a null record with `--release-version 2.12.0`: Recovery step 2 reads `workflow-manager update p3d` while the refusal's own `next:` names `--release-version 2.12.0` |
| 4 | TRUE-FIX-NEEDED | `cli.py:734-735` prints `(no change)` for any empty change list; a null record meeting the same release prints `would update T from a record with no workflow_version to workflow 2.12.0` then `(no change)`, while the real run rewrites the record |
| 5a | TRUE-FIX-NEEDED | `advice.py:648-652`: the comment says the real update accepts a null-manifest release "and `doctor`, whose record check runs first, refuses" it; `doctor` refuses the null **record** before it reads any directory |
| 5b | TRUE-FIX-NEEDED | `docs/update.md:119` says a bare `--dry-run` leaves a `--release-dir` out; a bare dry run has none, only `doctor --release-dir DIR` prints the step with a directory |
| 5c | TRUE-FIX-NEEDED | `tests/test_operator_ux.py:1296-1304` (`_dry_and_real`) hashes only the dry-run copy; the real bare update's no-write is proven elsewhere |
| 5d | KEEP | The mutation table "differs in detail" from the plan's "nothing else changes" is text in a completed item's test results (`docs/milestones/completed/`), a historical record that is never edited; nothing to fix in code or pages |

## 2. The behaviour, point by point

**Point 1.** A named release is the repair the real update accepts (the
record is never read as a floor, `cli._release`). `cmd_dry_run` therefore
refuses a record only when the run must choose, through `_floor`, exactly as
the real run does; for a named release it accepts any record. **Safety
property: the recorded name never reaches a path, a cache question, a source
read or a version comparison.** The sites that touched it, all closed:

* `cli._readonly_destinations` and `cli._choose_and_resolve` plan destinations
  with the recorded name as a cache leaf: the dry run passes them only a
  strict `X.Y.Z` (`recorded` otherwise becomes `None`, "unknown");
* `cli._installed_resolves` asks the cache for the installed release: with
  `None` it answers `not-verified`, as for a null record today;
* the report: a prototype showed that merely lifting the refusal crashes in
  the report phase (`compatibility._lt` raises `not a release version:
  'garbage'` at `_base_findings`) and, for a comparable name such as `2.12`
  against a discovered release, would ask `cache.cached_manifest('2.12')`
  from `coverage.gather_metadata`. A new `compatibility.recorded_release(facts)`
  returns the record's release only when it is one strict `X.Y.Z`; the
  report (`_base_findings`, the `not-verified` step, `build_report`) and
  `cli._compatibility_report` read the record only through it, so a damaged
  name is "Installed release unknown", exactly as a null record already is.

The header names a damaged value as the record's own, escaped by `repr`,
never as a release: `would update T from a record whose workflow_version
'garbage' is not a version to workflow V     (dry run: nothing written)`.
Null stays `from a record with no workflow_version`; a recorded version
prints byte for byte as before. A run that must choose is refused by both
with the same cause and step (unchanged).

**Point 2.** `source.local_release` raises `ReleaseIntegrityError(kind=
"manifest-shape")` for a null manifest version, next to the existing check
for an unhashable one and before any pin lookup, snapshot or write:
`manifest.json at DIR is malformed: workflow_version is null, not text`, with
the existing step for that kind and a release directory (`use an unmodified
copy of the release directory, or leave --release-dir out ...`, exit 1). It
is the one place every command reads a release directory through, so
`bootstrap`, `update`, `update --dry-run`, `verify`, `status` and `doctor`
(after its record check) refuse it alike. Other non-text versions (a number,
`true`, `""`) are accepted today and stay so: out of scope, no new behaviour.

**Point 3.** `build_report` keeps the target version in every command the
report prints when the installation exists and its record is not one
strict `X.Y.Z`; the latest-release case of a valid record is untouched
(byte-identical), as is a missing installation.

**Point 4.** When the plan has no change, the dry run prints `(no change)` for
a valid recorded version (byte-identical) and `(no file changes; the
installation record would be rewritten to workflow V)` for a null or damaged
record. The real update's `(no change)` line is not changed: its first line
already names the version it wrote, and the parity test maps the one to the
other.

**Point 5.** The comment of `advice._not_a_version`, the sentence of
`docs/update.md` and the no-write assertion of `_dry_and_real` for the real
bare update (the refused real run's `tree_hash` is compared before and after).

## 3. What changes for the user, and what pins the old text

Released commands' output changes only here (every other message, exit code
and happy-path line is byte-identical: **golden**, 20 scenarios, 3 command
families, built from the pinned release, run on the base source and on the
prototype with paths normalised, `diff` empty -- valid and older recorded
versions, `--release-version`, `--release-dir`, bare, drift refusal, `doctor`,
`status`, `verify`, bootstrap, unmanaged):

| Input | Before | After |
| --- | --- | --- |
| `update --dry-run` with a named release, record damaged but not null | exit 1, `the installation record names X, which is not a version` | exit 0, preview, header `from a record whose workflow_version X is not a version`; `Installed release unknown` in the report |
| `--release-dir` of a null-manifest release, any command | accepted; `bootstrap` and a real `update` write `workflow None` (the record turns null) | exit 1, `manifest.json at DIR is malformed: workflow_version is null, not text`, one `next:`; nothing written |
| Recovery steps and commands of a report, record null or damaged, target is the latest | `workflow-manager update T` | `workflow-manager --release-version V update T` (also `--force`) |
| `update --dry-run`, null or damaged record, release with no file change | `(no change)` | `(no file changes; the installation record would be rewritten to workflow V)` |

Tests that pin the old behaviour (all edited in CP1; list searched with
`grep` over `tests/` and `docs/` for `dry-run` with a record, `null`
manifest, `workflow None`, `no workflow_version`, `is left out`):
`tests/test_discovery.py:549` (the `dry run, valid option` row of the
`../escaped` per-command table); in `tests/test_operator_ux.py` the
`dry-run with a valid option` case (`:1118`), `test_a_null_record_with_a_release_dir_names_one_step_without_it`
(a null-manifest `bootstrap`, matching `verify`/`status`, a bare
`--release-dir` update), `test_update_and_dry_run_decide_the_same_way_on_a_null_record`
(its `release-dir null manifest` row), `TestManifestSweep` (the `version null`
row `:1895` and the `wanted` map `:1954`), `_dry_and_real`; in
`tests/test_operator_ux_readonly.py:968,993,1004` the `None` manifest versions.
Pages: `docs/update.md:119`, `docs/common-problems.md:25` ("it still refuses
whatever the option"), `docs/exit-codes.md:21`, `docs/ARCHITECTURE.md:143-146`.
`docs/ROADMAP.md` row 28 and `docs/release-history.md` row 1.14.7 describe the
earlier fix as history and stay. A new `common-problems` table row would need
a paired case in `test_operator_ux_docs.py`; the null-manifest sentence goes
in `docs/update.md` and `docs/exit-codes.md` instead (`test_operator_ux_docs.py`
needs no edit; the prototype run proved it).

## 4. Tests and proofs (CP1)

* **Agreement** (`tests/test_operator_ux.py`, `TestNotAVersionRows`): the
  existing null-record test is kept with its `release-dir null manifest` row
  now `refused 1` by both runs (the refusal names the cause and one step and
  the record stays null); new
  `test_update_and_dry_run_decide_the_same_way_on_a_damaged_record` runs both
  commands on `garbage` and `../escaped` with `--release-version`,
  `--release-dir` (accepted by both) and bare (refused by both), compares the
  decisions, the changes (`_same_changes` maps the real `(no change)` to the
  dry run's record line), the header, `Installed release   unknown`, and that
  every printed `update` command keeps its release option.
  `_dry_and_real` takes the record value and asserts **no write on both
  sides**: the dry run always, the real run whenever it is refused (point 5c).
* **Safety** (`tests/test_discovery.py`, `TestOnlyAStrictVersionBuildsAPath`):
  for the names `../escaped`, `garbage`, `2.12`, `7.0.0/../7.0.0` and the
  options `--release-version 7.0.1` and a discovered release (above the
  built-in data, so the metadata path is exercised), the dry run exits 0 and
  spies on `ReleaseCache.resolve`, `cached`, `cached_manifest`,
  `ReleaseSource.inspect` and `plan_destinations` record every version they
  are given: the recorded name is never among them (and the spy list is not
  empty); a victim directory `escaped` next to the cache and the whole tree
  outside the cache are unchanged; the record still holds the name.
* **Null-manifest refusal** (`test_a_null_record_with_a_release_dir_...` and
  `TestManifestSweep`): `bootstrap`, `update`, `update --dry-run`, `verify`
  and `status` with a null-manifest directory exit 1 with the cause, one
  `next:` and an unchanged `tree_hash` (an empty repository, a null-record
  repository); `doctor` on a null record still prints the null-record step
  with the directory clause; the sweep row `version null` becomes
  `(0, 1, 1, 1, 1, 1, 2)`.
* Edited minimally: `tests/test_operator_ux_readonly.py` drops `None` from the
  two scalar-version loops (the null case is the new refusal).

**Failure-only mutations** (measured in a scratch copy outside the repository,
`python3 tests/run_all.py --select` of the four classes; each fails only the
named tests, the unmutated copy passes, `verdict: exit 0`):

| Mutation | Fails |
| --- | --- |
| M1 the dry run refuses a non-null damaged record again | the safety test; the damaged-record agreement test |
| M2 the recorded name goes to `_readonly_destinations`/`_choose_and_resolve` | the safety test |
| M3 `recorded_release` returns the raw record | the safety test; the damaged-record agreement test |
| M4 the null-manifest check removed | the sweep; the null-record agreement test; the release-dir test |
| M5 recovery drops the version when it is the latest | the damaged-record agreement test |
| M6 a record-only rewrite prints `(no change)` | both agreement tests |

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The record shapes, the null-manifest refusal, the recovery step, the dry-run wording, and the tests | - | 2 | 1 |
| CP2 | The pages that pin the old behaviour and the wording fixes | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the record shapes, the null-manifest refusal, the recovery step, the dry-run wording, and the tests

**Files:** `src/workflow_manager/cli.py`, `src/workflow_manager/compatibility.py`,
`src/workflow_manager/source.py`, `src/workflow_manager/advice.py` (comment
only), `tests/test_operator_ux.py`, `tests/test_discovery.py`,
`tests/test_operator_ux_readonly.py`.

Sections 2 to 4. `cli.py`: `cmd_dry_run` (the record check only through
`_floor`, a strict `installed` for the lookups), `_print_dry_run` (header and
the record line), `_compatibility_report` (`recorded_release`).
`compatibility.py`: `recorded_release`, its three uses and `build_report`'s
`explicit`. `source.py`: the null check in `local_release`. `advice.py`: the
comment only. Nothing else under `src/` changes; no option, no exit code, no
other message.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the pages that pin the old behaviour and the wording fixes

**Files:** `docs/update.md`, `docs/common-problems.md`, `docs/exit-codes.md`,
`docs/ARCHITECTURE.md`.

Section 3's pages: `update.md` (the `is not a version` bullet: only
`doctor --release-dir` prints the step with a directory; a null or damaged
record is accepted by a dry run that names a release, the header and the
record line; a null-manifest `--release-dir` is refused), `common-problems.md`
(the last sentence of the `is not a version` row), `exit-codes.md` (row 1: an
explicit release accepts a damaged record for `update` and `update --dry-run`;
the null-manifest refusal), `ARCHITECTURE.md` (which commands call
`_refuse_unparseable_record` and that the recorded name reaches no cache,
source or planner). No page names a milestone id. Roadmap row 46 is added by
this planning pass and is Done at acceptance; the roadmap and the active
milestone page are excluded at both stages and not deliverables.
<!-- /CP2 -->

## 6. Functional review

Every flow is offline, in a sandbox with no network, no `gh`, no installs and
**no Workflow release cache**: the targets are Git repositories built by hand
from a hand-made release directory (`--release-dir`), and the rest are greps
and diffs. The test suite is not a flow (flow 12). Setup, on disk (never
`/tmp`): `S=$(mktemp -d "$HOME/.cache/udp-fr.XXXXXX")`, `export
WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache`, `git archive
da3c7747a65b5788d0f6d9530fcd379b52d7b6d2 src | tar -x -C $S/base` and `git
archive <candidate head> src | tar -x -C $S/cand`, the runner `wm() { w=$1;
shift; python3 -I -c 'import sys;sys.path.insert(0,sys.argv.pop(1));from
workflow_manager.cli import main;raise SystemExit(main())' "$S/$w/src" "$@"; }`,
and the release builder `$S/mk.py DIR VERSION` (`VERSION` may be `null`)
written by the checklist (the same stdlib script the earlier dry-run item
used: a manifest, one payload file, the five templates). Then `mk.py $S/rel
9.0.0`, `mk.py $S/relnull null`, a Git repository `$S/t` bootstrapped with
`wm base --release-dir $S/rel bootstrap` and committed; one fresh `cp -a` copy
per run, with the record's `workflow_version` set to `null` (copies `n1` ...),
to `"garbage"` (`g1` ...), or left `9.0.0` (`ok`). `tree DIR` is `find DIR
-path '*/.git' -prune -o -type f -print0 | sort -z | xargs -0 sha256sum |
sha256sum`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | on fresh `g` copies: `wm base --release-dir $S/rel update --dry-run G1`, `wm base --release-dir $S/rel update G2`, then both with `wm cand` | base: dry run exit 1 (`names 'garbage', which is not a version`), real run exit 0 `updated G2 to workflow 9.0.0`. Candidate: dry run exit 0, first line `would update G1 from a record whose workflow_version 'garbage' is not a version to workflow 9.0.0     (dry run: nothing written)`, then `  would prepend managed CLAUDE.md section`; `tree` of the dry-run copy unchanged |
| 2 | flow 1 with the record `"../escaped"` and the candidate only, then `ls $S/..` and `ls $S/cache` | dry run exit 0 with the header naming `'../escaped'`; no `escaped` entry next to or inside the cache; `tree` of the copy unchanged |
| 3 | on fresh `g` copies: `wm cand update --dry-run G1`, `wm cand update G2` (no option) | both exit 1, the same `error:` line and cause, the dry run's `next:` identical to the real run's (a damaged, non-null record returns before the null-record suffix, `advice._not_a_version`); `tree` of both copies unchanged |
| 4 | on fresh `n` copies: `wm base --release-dir $S/relnull update --dry-run N1`, `wm base --release-dir $S/relnull update N2`, then both with `wm cand`; then `cat N2/.workflow-manager/installation.json` | base: both exit 0 and say `workflow None`; candidate: both exit 1, `manifest.json at ... is malformed: workflow_version is null, not text`, one `next:` (`use an unmodified copy of the release directory, or leave --release-dir out`), the record unchanged, `tree` of both copies unchanged |
| 5 | on a copy of `ok`: `wm base --release-dir $S/relnull update $S/ok1` and `wm cand ...` | base exit 0 and the record becomes null; candidate exit 1, the refusal of flow 4, the record still `9.0.0`, `tree` unchanged |
| 6 | `wm cand --release-dir $S/relnull bootstrap E` on an empty Git repository `E`, then `verify` and `status` with the same option on a copy of `ok` | exit 1 each with the same cause and one `next:`; `tree` of `E` and of the copy unchanged |
| 7 | on a fresh `n` copy whose files already equal the release (bootstrap `$S/rel`, set the record `null`, commit): `wm base --release-dir $S/rel update --dry-run N` and `wm cand ...` | base: `  (no change)`; candidate: `  (no file changes; the installation record would be rewritten to workflow 9.0.0)`; the other lines identical; `tree` unchanged |
| 8 | on a copy of `ok`: `wm base --release-dir $S/rel update --dry-run $S/ok1` and `wm cand ...`, then the same with `update`, `doctor`, `status`, `verify` | byte-identical output between base and candidate for every command (the happy path), paths aside |
| 9 | on a fresh `n` copy, edit a **managed** file the record lists (drift is measured only against `installation.managed`, `install.py:688`; `CLAUDE.md` is merged, so editing it is no drift): `F=$(python3 -I -c 'import json,sys;print(next(k for k in json.load(open(sys.argv[1]))["managed"] if k != "CLAUDE.md"))' N/.workflow-manager/installation.json)`, `echo x >> N/$F`, `tree N` recorded, then `wm cand --release-dir $S/rel update --dry-run N` and `wm cand --release-dir $S/rel update N`, then `grep -n 'workflow-manager'` of the Recovery lines | both exit 2 with the drift refusal naming `$F`; `tree N` equals the recorded hash after each; every printed `update` command, the ordinary one and the `--force` one, names the release option (`--release-dir $S/rel`); running the printed `--force` command on a fresh copy of the same edit exits 0 |
| 10 | `git diff --stat da3c7747a65b5788d0f6d9530fcd379b52d7b6d2 -- . ':!docs/ai-workflow' ':!.ai-review'` | only the 11 files of the two Files paragraphs and `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md` |
| 11 | `git diff --exit-code da3c7747a65b5788d0f6d9530fcd379b52d7b6d2 -- docs/retention.md docs/release-history.md docs/install.md docs/README.md src/workflow_manager/install.py src/workflow_manager/retention*.py`; then `grep -n 'whatever the option' docs/update.md docs/common-problems.md docs/exit-codes.md docs/ARCHITECTURE.md`, `grep -n 'bare .--dry-run' docs/update.md` | exit 0 (untouched); `whatever the option` is left only in the `doctor` sentence of `docs/common-problems.md`; `docs/update.md` says only `doctor --release-dir` prints the step with a directory, and none of the four pages names a milestone id (`grep -c 'update-dry-run-parity' docs/update.md docs/common-problems.md docs/exit-codes.md docs/ARCHITECTURE.md` is 0 for each) |
| 12 | (full environment) `python3 tests/run_all.py --select test_operator_ux.py --select test_discovery.py --select test_operator_ux_readonly.py --select test_operator_ux_docs.py --select test_docs.py`, then `python3 tools/check_docs.py`, then `python3 tests/run_all.py` | green, `check_docs` exit 0; each mutation of section 4 fails its named tests |

## 7. Risks and open decisions

* The null-manifest refusal is at the source, so it also stops `bootstrap`,
  `verify` and `status` with such a directory; they accepted it before (an
  existing test built one and pinned them healthy). That input was never a
  release (it names no version) and the old acceptance is what let the real
  update destroy a valid record; the change and its pins are listed in section 3.
* A manifest version that is a number, `true` or `""` is still accepted: the
  issue names only null, and widening the check would change more released
  behaviour than the issue asks. Left as is.
* The real `update` still prints `(no change)` for a record-only rewrite; only
  the dry run says it (the issue's point). Changing the real line would be a
  second output change with no owner request.
* Decisions for the owner: none. `docs/TECHNICAL_DECISIONS.md` does not exist
  in this repository. Point 5d is KEEP (a completed item's own record).
