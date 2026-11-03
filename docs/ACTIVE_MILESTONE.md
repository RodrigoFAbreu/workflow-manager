# Active Milestone

## Milestone

`update-dry-run-match` -- implementation and technical approval complete, awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `76783c9`, branch `milestone/update-dry-run-match`): roadmap row 28 (#145, item 4). A `fix:` pull request title (releases a patch).

`update --dry-run` and the real `update` decide the same way on a record whose `workflow_version` is null: with `--release-version` or `--release-dir` both are accepted (the dry run previews, its header says `from a record with no workflow_version`, not `workflow None`); a run that must choose the release is refused by both with the same cause and step. A record damaged in another way, `doctor`, every other message and every exit code are unchanged. No Workflow change.

### CP1: the dry run's record check, its header, the tests and the docs -- complete

- `src/workflow_manager/cli.py` (the record check in `cmd_dry_run` runs only for a non-null record; `_print_dry_run` words a null record), a comment in `src/workflow_manager/advice.py`, `tests/test_operator_ux.py` (the agreement test, the header test, one row removed from the test that pinned the divergence), `docs/update.md`, `docs/common-problems.md` (commit `74d55a5`).

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 28 is **Current** (done at acceptance); this record.

### Failure-only mutations (each restores one old behaviour, then `python3 tests/run_all.py --select test_operator_ux.py`, restored afterwards)

| Mutation | Fails |
| --- | --- |
| (a) unconditional `_refuse_unparseable_record(installed)` in `cmd_dry_run` | `test_update_and_dry_run_decide_the_same_way_on_a_null_record`, the three accepted rows |
| (b) `_print_dry_run` back to `workflow {plan.current.workflow_version}` | `test_the_dry_run_header_names_a_null_record_in_words` and the agreement test's accepted rows |
| (c) the record check skipped on any explicit run, not only a null record | `test_the_record_is_the_cause_for_each_command_and_its_own_step` |
| (d) `floor=None` in `cmd_dry_run`'s `_choose_and_resolve` call | `test_update_and_dry_run_decide_the_same_way_on_a_null_record` (the refused row) and `test_a_null_record_is_refused_with_one_step_by_update_dry_run_and_doctor` |

Unmutated: `python3 tests/run_all.py --select test_operator_ux.py` green (130 tests, head `74d55a5`).

### Self-review

The full diff (`76783c9..1b7481c`) was read against plan sections 2 to 4, and the branch's `update --dry-run` was run by hand on a bootstrapped 2.25.5 repository whose record was set to `null`: with `--release-version 2.25.5` it exits 0, its header reads `from a record with no workflow_version to workflow 2.25.5`, and the real `update` with the same option prints the same changes and rewrites the record to `2.25.5`; without an option it is refused with the null-record cause and the step that ends in ` -- a real update, not a dry run`. No blocking or important finding. Two minor observations on the newly reachable preview, both outside this item's declared files and recorded for follow-up issues at acceptance:

1. When `--release-version` names the latest release, the report's Recovery step 2 ("re-run with the same command") renders a bare `workflow-manager update TARGET`, which a null record refuses (`compatibility.build_report` passes a `--release-version` to Recovery only when it differs from the latest). The refusal is safe and its `next:` names the right command. With `--release-dir` the step carries the directory and is right.
2. The real `update` prints `(no change)` while it rewrites a null record to the release; the dry run matches it, as the agreement test requires. The record rewrite is not listed by either.

## Functional review checklist

Hard gate (`AWAITING_FUNCTIONAL_REVIEW`): the user runs the flows below, then records findings. Code under test is `src/` at `74d55a5`, unchanged since (`git diff --quiet 74d55a5 HEAD -- src` is clean); base is `76783c9`. Expectations come from plan section 5 and were run under the sandbox rules below before this checklist was written. Flow 7 is not a functional flow.

### Setup

Sandbox rules, also the rules of the Controller's functional tester: no network (`unshare -rn`); no `gh`, `claude`, `codex` or `ssh` (no flow calls one, and any call that reaches a stand-in is a finding); nothing written inside the clone; scratch outside the clone and outside `/tmp`.

```sh
R=/home/rodrigo/Workspace/workflow-manager          # the product clone, read only
S=$(mktemp -d "$HOME/.cache/udm-fr.XXXXXX"); mkdir -p $S/base $S/cand $S/bin $S/cache
git -C $R archive 76783c91d01fc9e7db9cd2723e6fe08bdacc8956 src | tar -x -C $S/base
git -C $R archive 74d55a5 src | tar -x -C $S/cand
for t in gh claude codex ssh; do printf '#!/bin/sh\necho "%s $*" >> %s/refused.log; exit 127\n' $t $S > $S/bin/$t; chmod +x $S/bin/$t; done
wm() { w=$1; shift; env -i HOME="$HOME" PATH="$S/bin:/usr/bin:/bin" WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" unshare -rn python3 -I -c 'import sys;sys.path.insert(0,sys.argv.pop(1));from workflow_manager.cli import main;raise SystemExit(main())' "$S/$w/src" "$@"; }
tree() { (cd "$1" && find . -path '*/.git' -prune -o -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum); }
```

Test data: write `$S/mk.py` exactly as in plan section 5, then:

```sh
python3 -I $S/mk.py $S/rel 9.0.0           # a release
python3 -I $S/mk.py $S/relnull null        # a release whose manifest has a null version
git init -q $S/t && git -C $S/t config user.name sandbox && git -C $S/t config user.email sandbox@example.invalid
git -C $S/t commit -q --allow-empty -m init
wm base --release-dir $S/rel bootstrap $S/t
git -C $S/t add -A && git -C $S/t commit -qm b && cp -a $S/t $S/ok          # recorded 9.0.0
cp -a $S/ok $S/nb && python3 -I -c 'import json,sys;p=sys.argv[1]+"/.workflow-manager/installation.json";d=json.load(open(p));d["workflow_version"]=None;json.dump(d,open(p,"w"),indent=2)' $S/nb && git -C $S/nb commit -qam null-record    # JSON null, not the string "null"
cp -a $S/ok $S/g && python3 -I -c 'import json,sys;p=sys.argv[1]+"/.workflow-manager/installation.json";d=json.load(open(p));d["workflow_version"]="garbage";json.dump(d,open(p,"w"),indent=2)' $S/g && git -C $S/g commit -qam garbage
```

Each run gets its own copy (`cp -a $S/nb $S/n1`, and so on), so no run sees another's writes. A dry run writes nothing, so one copy can serve both builds for a byte comparison; real runs each take a fresh copy. `tree DIR` must be equal before and after a run. The paths in the outputs are the copies' own paths, so compare base and candidate on the same copy path.

### Flows

| # | Run | Expected result |
| --- | --- | --- |
| 1 | `wm base --release-dir $S/rel update --dry-run $S/n1` | exit 1; `error:` says the record has no `workflow_version` (it is null), which is not a version; `next:` ends ` -- a real update, not a dry run` |
| 1 | `wm base --release-dir $S/rel update $S/n2` | exit 0; `updated $S/n2 to workflow 9.0.0`; the record names `9.0.0` (the base divergence: the real run accepts what its dry run refuses) |
| 1 | `wm cand --release-dir $S/rel update --dry-run $S/n3` | exit 0; first line `would update $S/n3 from a record with no workflow_version to workflow 9.0.0     (dry run: nothing written)`, then `  would prepend managed CLAUDE.md section`; `tree` unchanged |
| 1 | `wm cand --release-dir $S/rel update $S/n4` | exit 0; `updated $S/n4 to workflow 9.0.0`, then `  prepended managed CLAUDE.md section`; the record names `9.0.0` |
| 2 | `wm cand --release-dir $S/relnull update --dry-run $S/n5` | exit 0; first line ends `to workflow None     (dry run: nothing written)`; `tree` unchanged |
| 2 | `wm cand --release-dir $S/relnull update $S/n6` | exit 0; `updated $S/n6 to workflow None`; the record is still null (known limitation below) |
| 3 | bare form: `wm base update --dry-run $S/n7` and `wm base update $S/n8`, then the same two with `wm cand` | every run exit 1 with the same `error:` line; the dry run's `next:` equals the real run's plus ` -- a real update, not a dry run`; base and candidate outputs byte-identical; `tree` unchanged for both dry and refused real runs |
| 4 | `wm base --release-dir $S/rel update --dry-run $S/g` and `wm cand ...` on the same copy | both exit 1 with `the installation record names 'garbage', which is not a version`; byte-identical; `tree` unchanged |
| 5 | `wm base --release-dir $S/rel update --dry-run $S/ok` and `wm cand ...` on the same copy | both exit 0, byte-identical; first line `would update $S/ok from workflow 9.0.0 to workflow 9.0.0     (dry run: nothing written)`; `tree` unchanged |
| 6 | `wm base --release-dir $S/rel doctor $S/d` and `wm cand ...` on the same copy | both exit 2, byte-identical; `error: could not resolve the target release: the installation record has no workflow_version (it is null)...`; `tree` unchanged |
| 7 | not a flow here: `python3 tests/run_all.py` | the automated gate, already recorded green at `d1e5e3c` (full selection, exit 0, 2329/2329 units, 15540 tests; `.ai-review/update-dry-run-match/current/TEST_RESULTS.md`). It needs the release cache or network, which the sandbox denies |

Afterwards: `rm -rf "$S"`. Any `refused.log` line means a flow reached a stand-in, which is a finding.

### Known limitations (out of scope; plan sections 6 and 7)

- A null-manifest release (`relnull`) is previewed by the dry run and written by the real run as `workflow None`, leaving the record null. Refusing it is release-input validation, a follow-up.
- `update --dry-run` still refuses a damaged but non-null record (`garbage`) that the real `update` with an explicit release accepts. Unchanged; follow-up.
- `doctor` still refuses a null record whatever the option. Unchanged.
- After an interrupted update that names the latest release, Recovery renders a bare `update`, which a null record refuses. The refusal's `next:` names the right command. The cause is in `compatibility.build_report`, outside this item (finding F-54ec80c9ea09).
- The real `update` prints `(no change)` while it rewrites a null record; the dry run matches it, as the agreement test requires (finding F-b372c827e418).

## Next action

Functional review (user, hard gate): run flows 1 to 6 above. Findings go to `.ai-review/update-dry-run-match/feedback/FUNCTIONAL_REVIEW.md`. If testing is clean, `/accept-milestone` (every checkpoint, CP1 and CP2, is `COMPLETE`). Findings go to `/apply-functional-review`, which routes each one: a same-scope fix to its bounded branch, a new or wider one to a remediation child item.
