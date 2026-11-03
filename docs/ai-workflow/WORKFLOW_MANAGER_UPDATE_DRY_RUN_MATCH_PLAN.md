# Workflow Manager: `update` and `update --dry-run` Decide the Same Way on a Null Record (Revision 2)

`work_item_id: update-dry-run-match` -- `governing_workflow_version: "2.2"`

**Deliverable:** on an installation record whose `workflow_version` is null,
`update --dry-run` accepts the input the real `update` accepts and previews
it, and refuses the input the real `update` refuses with the same cause and
step (roadmap row 28, issue #145 item 4, the owner's decision of 2026-11-03).

**Work item type:** `process`. **Base commit:** `76783c9`
(`76783c91d01fc9e7db9cd2723e6fe08bdacc8956`, tip of `main`; Manager 1.14.6,
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/update-dry-run-match`. **Scope source:** the owner's order and
`docs/ROADMAP.md` row 28 (added by this item, Current now, Done at
acceptance). The pull request title is `fix: ...`, a **patch** release
(checked with `python3 tools/release/release.py check-title`). One
mechanism: *the dry run and the real run decide the same way for the same
input*. Two checkpoints, one review surface (one function of
`src/workflow_manager/cli.py`, one test class, two docs sentences). Sizing:
far under 350 lines; no split needed.

## 1. Which side is right (evidence, current main)

Reproduced offline on `76783c9` with a hand-made release (section 6): a Git
repository with a null record, `--release-dir D`.

| Run | Result on `76783c9` |
| --- | --- |
| `update --release-dir D T` | exit 0, `updated T to workflow 9.0.0`, the record now names `9.0.0` |
| `update --dry-run --release-dir D T` | exit 1, `the installation record has no workflow_version (it is null), which is not a version`, step ends ` -- a real update, not a dry run` |

The real run is correct; the dry run is wrong:

* `cli._release` (the real run) reads the record only when it must choose the
  release itself (`_floor`, the bare form). With `--release-version` or
  `--release-dir` the release is named, so the record is not a floor and is
  never read. `install.plan_update` uses the record for `managed`, `profile`,
  `generated`, `installed_at` and `merged` only, and writes
  `Installation(workflow_version=release.version, ...)`: an explicit update
  **rewrites** the record. That is a designed repair, not a slip.
* `advice._not_a_version` names exactly this run as the repair for a null
  record (`run workflow-manager --release-version X.Y.Z update T ... it
  updates the installation record to that release`), and the existing test
  `test_an_update_naming_the_release_is_the_repair_and_is_not_refused` pins
  that the explicit update is accepted. A preview that refuses the repair its
  own sibling prescribes is the defect.
* `cli.cmd_dry_run` says it makes "the same refusals (exit 2) as the real
  update" but opens with an unconditional `_refuse_unparseable_record`, before
  it knows whether the run chooses. The bare form is refused by `_floor` in
  both runs anyway; the unconditional line only adds the refusals of the
  explicit forms.

Is accepting wrong instead (a null-manifest release refused by both)? No, for
a different input. A release directory whose *manifest* has a null
`workflow_version` is accepted today by `source.local_release` (a null is
hashable), by `bootstrap`, `verify` and `status` (the existing test builds
one and pins `bootstrap` and matching `verify`/`status` as healthy), and the
real `update` then writes a null record with `updated T to workflow None`.
That is a property of the **release input**, shared by every command and
decided before either run reaches the record; the dry run and the real run
call the same `_resolve`, so after this change they agree on it too. Refusing
such a release is a separate mechanism (release-input validation) and is
left as a follow-up, not decided here (section 7).

## 2. The behaviour

The record check in `cmd_dry_run` runs only when the record is not null. A null
record is never refused by that line: on the bare form `_floor` refuses it
exactly as it does for the real run (`cli._release` -> `_floor`), and an
explicit `--release-version`/`--release-dir` never reads the record as a floor:

| Input on a null record | `update` | `update --dry-run` before | `update --dry-run` after |
| --- | --- | --- | --- |
| `--release-dir D` (any manifest) | accepted | refused | **accepted, previewed** |
| `--release-version X.Y.Z` | accepted | refused | **accepted, previewed** |
| neither (the run chooses) | refused: cause + step | refused: cause + step + ` -- a real update, not a dry run` | unchanged (same cause; the step differs only by that suffix, as pinned today) |

A null `installed` already flows safely through the read-only lookups
(`_readonly_destinations` and `_installed_resolves` guard `isinstance(str)`;
the report shows the existing `not-verified` note), so no new path reaches
the cache. The only text that changes is the dry run's header for the null
case, which would otherwise print Python's `None`:

* before (unreachable until now): `would update T from workflow None to
  workflow V     (dry run: nothing written)`;
* after: `would update T from a record with no workflow_version to workflow
  V     (dry run: nothing written)`. A recorded version prints byte for byte
  as before (`from workflow 1.0.0 to workflow V`); `to workflow V` is
  unchanged, so a null-manifest release still reads `to workflow None`, as
  the real run's `updated T to workflow None` does.

Not changed (byte-identical, section 3): every other message and exit code;
`doctor` (it keeps refusing a null record whatever the option, a separate
command); the `_not_a_version` step and its ` -- a real update, not a dry
run` suffix (still true for the bare dry run); a record that is damaged but
**not null** (`"garbage"`, `""`, a number, `"../escaped"`): `update
--dry-run` still refuses it whatever the option while the real `update` with
an explicit release accepts it. That residual is outside the owner's decision
(a null record) and "exit codes of other cases"; it is also not free: a
non-null damaged name must never reach a cache path (`TestOnlyAStrictVersionBuildsAPath`),
which needs its own proof. Recorded as a follow-up (section 7).

## 3. Tests (`tests/test_operator_ux.py`, class `TestNotAVersionRows`)

New `test_update_and_dry_run_decide_the_same_way_on_a_null_record`: for each
input of a table, build two copies of `damaged(None)`, run the real `update`
on one and `update --dry-run` on the other with the **same** global options,
reduce each run to a decision and assert the two decisions are equal:

* decision = (`accepted` | `refused` with exit code, the `error:` line, the
  `next:` line with ` -- a real update, not a dry run` removed), the target
  path normalised to `TARGET`;
* table: `--release-dir` of a genuine release copy (expected accepted),
  `--release-dir` of a null-manifest copy (accepted), `--release-version`
  `PINNED_NEWEST` (accepted), no option (refused, exit 1). The expected
  column is asserted too, so the test cannot pass by both runs failing;
* for each accepted row: the dry run's changes equal the real run's
  (`cli._would(real_line)` equals the dry line, one by one), the version in
  `to workflow V` is the one the real run's `updated T to workflow V` names
  and the one it wrote to the record, and the dry-run target's `tree_hash` is
  unchanged (no-write proof); for the refused row both targets' `tree_hash`
  are unchanged (the failure path's no-write proof).

New `test_the_dry_run_header_names_a_null_record_in_words` pins the exact
header of section 2 for a null record and, for a recorded version, the
unchanged `would update T from workflow V to workflow V     (dry run: nothing
written)` (byte-identical).

Edit of one existing test, the only one pinning the old divergence:
`test_a_null_record_with_a_release_dir_names_one_step_without_it` loops over
`update --dry-run` and `doctor` with `--release-dir` and expects both refused;
its `update --dry-run` row is removed (that input is now the agreement test's
accepted row), its `doctor` row and every assertion about the clause stay.
Searched `tests/` and `docs/` for the changed text and cases
(`a real update, not a dry run`, `whatever the option`, `damaged(None)`,
`left out`, `--dry-run` with a null record): nothing else pins them; the
non-null rows (`"../escaped"` in `test_operator_ux.py` and
`test_discovery.py`, `"garbage"`) stay green and prove the residual is
unchanged.

**Failure-only mutations** (each restores one old behaviour; the named case
fails and nothing else changes): (a) restore the unconditional
`_refuse_unparseable_record(installed)` in `cmd_dry_run` -- the agreement
test's two accepted `--release-*` rows fail; (b) `_print_dry_run` back to
`workflow {plan.current.workflow_version}` -- the header test fails; (c)
widen the guard so any record skips the check on an explicit run -- the
existing `"../escaped"` dry-run rows fail (the scope is null only); (d)
`floor=None` in `cmd_dry_run`'s `_choose_and_resolve` call -- with the guard
of CP1 (`installed is not None` only) nothing else refuses the bare null dry
run, so it chooses and previews a release and the agreement test's refused row
fails (the failure path is real, not vacuous; the bare refusal has a single
source, `_floor`, as in the real run).

Docs (two sentences, no milestone id in them): `docs/update.md` (the
`is not a version` bullet) says a bare `--dry-run` carries the
"real update" note and `doctor` leaves a `--release-dir` out, and that on a
`null` record `update --dry-run` accepts what the real `update` accepts;
`docs/common-problems.md` (the `is not a version` row) replaces "`doctor`,
`update --dry-run` and a bare `update` refuse the record whatever the
option" with the exact current rule, including that `update --dry-run` still
refuses a record damaged but not null. `test_docs.py`'s pins on these
sentences (`gets one step`, `the explicit update that rewrites the record`)
stay true and are not edited. `python3 tools/check_docs.py` stays at exit 0.

Evidence at implementation (needs the release cache or network, so it is
implementation validation, not a functional-review flow): `python3
tests/run_all.py --select test_operator_ux.py` green, each mutation failing
the case named, then `python3 tests/run_all.py`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The dry run's record check, its header, the tests and the docs | - | 2 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the dry run's record check, its header, the tests and the docs

**Files:** `src/workflow_manager/cli.py`, `src/workflow_manager/advice.py`
(comment only), `tests/test_operator_ux.py`,
`docs/update.md`, `docs/common-problems.md`.

Sections 2 and 3. `cli.py`: in `cmd_dry_run`, `_refuse_unparseable_record`
runs only when the record is not null (`installed is not None`; a null
record on the bare form is refused by `_floor`, as in the real run), and
`_print_dry_run` words a null `plan.current.workflow_version`. No other
function, option, message or exit code changes; nothing under `src/` other
than `cli.py`, except a comment-only edit of `advice._not_a_version`'s stale
comment (the record check no longer runs before the release directory is
read for `update --dry-run`, only for `doctor`; a null-manifest release is
accepted by the real `update`): no behaviour, message or line other than that
comment changes.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 28 of `docs/ROADMAP.md` is Current when the plan starts and Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: the `fix:` title releases a patch. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 5. Functional review

Every flow runs offline in a sandbox: no network, no `gh`, no installs, no
sockets, no zlib-ng, a small tmpfs, and **no Workflow release cache**. No flow
bootstraps a published release or fetches anything: the target is a Git
repository built by hand (a record whose `workflow_version` is null) and the
release is a hand-made directory with a manifest, used only through
`--release-dir`. The test suite is not a flow (flow 7).

Setup (a named scratch directory on disk, never `/tmp`, removed with `rm -rf
$S` at the end): `S=$(mktemp -d "$HOME/.cache/udm-fr.XXXXXX"); mkdir
$S/base $S/cand; export WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache`; `git
archive 76783c91d01fc9e7db9cd2723e6fe08bdacc8956 src | tar -x -C $S/base`
and `git archive <candidate head> src | tar -x -C $S/cand`; the runner
`wm() { w=$1; shift; python3 -I -c 'import sys;sys.path.insert(0,sys.argv.pop(1));from workflow_manager.cli import main;raise SystemExit(main())' "$S/$w/src" "$@"; }`
(`wm base ...` or `wm cand ...`). The release builder `$S/mk.py DIR VERSION`
(`VERSION` may be `null`):

```python
import hashlib, json, sys
from pathlib import Path
root, version = Path(sys.argv[1]), sys.argv[2]
state = b'{"schema_version": 1, "active_work_item_id": null, "work_items": {}}\n'
config = b'{"schema_version": 1, "default_workflow_version": "2.2", "supported_versions": ["1", "2.1", "2.2"]}\n'
art = {"payload/docs/guide.md": b"# guide\n"}
tpl = {"templates/docs/ai-workflow/WORKFLOW_STATE.json": state,
       "templates/docs/ai-workflow/WORKFLOW_CONFIG.json": config,
       "templates/docs/ACTIVE_MILESTONE.md": b"# a\n",
       "templates/.gitignore.workflow-fragment": b".ai-review/\n",
       "templates/CLAUDE.md": b"# managed\n"}
m = {"workflow_version": None if version == "null" else version,
     "upstream": {"tag": "workflow-v9.0.0", "commit": "0" * 40}, "artifacts": [], "templates": []}
for group, files in (("artifacts", art), ("templates", tpl)):
    for loc, data in files.items():
        p = root / loc; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        e = {"target_path": loc.split("/", 1)[1], "location": loc,
             "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if group == "artifacts":
            e.update(executable=False, category="distribution")
        m[group].append(e)
(root / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
```

Then: `python3 $S/mk.py $S/rel 9.0.0; python3 $S/mk.py $S/relnull null`;
`git init -q $S/t` with a user name and email configured and an empty first
commit; `wm base --release-dir $S/rel bootstrap $S/t`; commit all (`git add
-A; git commit -qm b`); `cp -a $S/t $S/ok` (a recorded `9.0.0`); then set
`workflow_version` to `null` in `$S/t/.workflow-manager/installation.json`
(`python3` and `json`), commit it, and copy it as `$S/n1`, `$S/n2`, `$S/n3`
... one copy per run, so no run sees another's writes; for flow 4 a copy
with the value `"garbage"`. `tree` below means `find DIR -path '*/.git'
-prune -o -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | on a fresh null copy each: `wm base --release-dir $S/rel update --dry-run COPY`, `wm base --release-dir $S/rel update COPY2`; then the same two with `wm cand` | base: dry run exit 1 (`the installation record has no workflow_version (it is null)`, step ending ` -- a real update, not a dry run`), real run exit 0 `updated COPY2 to workflow 9.0.0` and the record names `9.0.0` (the divergence). Candidate: dry run exit 0, first line `would update COPY from a record with no workflow_version to workflow 9.0.0     (dry run: nothing written)`, then `  would prepend managed CLAUDE.md section`; real run exit 0 with `  prepended managed CLAUDE.md section`; `tree` of the dry-run copy unchanged |
| 2 | flow 1 with `--release-dir $S/relnull` (candidate only for the new behaviour) | candidate: dry run exit 0, first line ends `to workflow None     (dry run: nothing written)`; real run exit 0 `updated COPY2 to workflow None`, the record is still null afterwards (a release-input matter, section 7); `tree` of the dry-run copy unchanged |
| 3 | on fresh null copies: `wm base update --dry-run COPY`, `wm base update COPY2`; then `wm cand` | both builds: both runs exit 1, the same `error:` line, the dry run's `next:` equal to the real run's plus ` -- a real update, not a dry run`; base and candidate outputs byte-identical (paths aside); `tree` of both copies unchanged |
| 4 | on the `"garbage"` copy: `wm base --release-dir $S/rel update --dry-run COPY` and `wm cand ...` | both: exit 1, `the installation record names 'garbage', which is not a version`, byte-identical (the residual of section 2 is unchanged); `tree` unchanged |
| 5 | on `$S/ok` (recorded `9.0.0`): `wm base --release-dir $S/rel update --dry-run $S/ok` and `wm cand ...` | both: exit 0, first line `would update $S/ok from workflow 9.0.0 to workflow 9.0.0     (dry run: nothing written)`, byte-identical to each other |
| 6 | on a fresh null copy: `wm base --release-dir $S/rel doctor COPY` and `wm cand ...` | both: exit 2, `error: could not resolve the target release: the installation record has no workflow_version (it is null)...`, byte-identical; `tree` unchanged |
| 7 | (needs the full environment: the Workflow release cache or network) `python3 tests/run_all.py --select test_operator_ux.py`, then `python3 tests/run_all.py` | green; the agreement and header tests pass, and each mutation of section 3 fails its named case |

## 6. Risks

* The guard is null-only on purpose; a reader may expect `update --dry-run`
  to accept every record the real `update` accepts. Section 2 and the docs say
  where the rule stops, and the follow-up (section 7) records the rest.
* The null-manifest release is accepted by both commands after this change
  and the real run leaves a null record; the preview now says so instead of
  hiding it behind a refusal. Refusing it is a release-input decision.
* `doctor` still refuses a null record whatever the option; it is a report on
  the record, not a preview of `update`, and its text is out of scope.

## 7. Open decisions and follow-ups

None for the owner in this item. Two follow-ups to record at acceptance
(issues, not rounds): (1) `update --dry-run` still refuses a record damaged
but not null while the real `update` with an explicit release accepts it
(needs a proof that the name never reaches a cache path); (2) a release
directory whose manifest has a null `workflow_version` is accepted by
`source.local_release` and every command (refuse it at the source, with a
cause and step). `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
