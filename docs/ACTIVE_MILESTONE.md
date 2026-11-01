# Active Milestone

## Milestone

`retention-view-hardening` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `e5fa61f`, branch `milestone/retention-view-hardening`): roadmap row 23 (#116, items 1 and 2). A `fix:` pull request title (releases Manager 1.14.3; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_VIEW_HARDENING_PLAN.md`.

`status --retention` and `doctor --retention` print nothing from the engine's JSON report until it has passed a stricter validation: no string with a control character (Unicode category Cc, U+2028, U+2029), every integer in 0 to 2**63 - 1, every string within a stated length, and the `kind` and `schema_version` refusals echo a cut, escaped value. Items 3 to 6 of #116 stay open.

### CP1: the validation and its tests -- complete

- `retention.py`: limits (`INT_MAX`, `PATH_LIMIT`, `ERROR_LIMIT`, `ID_LIMIT`, `SHOWN_LIMIT`), the integer range in `_need`, the control-character and length checks in `_printable`, `_shown` for the two echoes; an `invalid_id` entry's id is exempt (the Manager never prints it).
- `tests/test_retention_status.py`: `TestHardenedValidation` and the extended range case (commit `51086fb`).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 23 is Current and is Done at acceptance.

### Mutation results (scratch clone of `51086fb`, `test_retention_status` run directly: the candidate passes 61 of 61)

Each mutation exits 1 and fails the case the plan names (extra failures listed):

| Mutation | Failed |
| --- | --- |
| the control-character scan removed | the control-character case, the forged-line/escape end-to-end case, plus two `invalid_id` cases |
| only the U+2028/U+2029 clause removed | the control-character case (the separators are among its subtests) |
| `\x85` (C1) no longer refused | the control-character case |
| the length check removed | both length cases, plus the `invalid_id` case |
| the length limit off by one | both length cases |
| the lower bound removed | the integer-range cases |
| the upper bound removed | the integer-range cases, plus the `totals.finished` upper-bound case |
| the range applied to `bytes` only | the every-integer-field case, plus the upper-bound case |
| `removing` items skipped by the scan | the `removing` control-character and length cases |
| the `invalid_id` exemption removed | the `invalid_id` case |
| the exemption widened to every `not_finished` id | the `invalid_id` case, plus the control-character and length cases |
| `kind` echoed untruncated | the echo case |
| `schema_version` echoed untruncated | the echo case |
| `_shown` returns the raw string instead of `repr` | the echo case, plus `test_shown_keeps_a_short_value...` and `test_other_failures_are_case_six` |

The scratch clone is outside the repository, which was never mutated.

## Functional review checklist

The candidate is this branch's tree (`git archive HEAD`); the base is `e5fa61f`. Every flow runs offline with `python3` and `git` only: no network, no `gh`, no GitHub, no `claude`/`codex`/`ssh`, no remote and no origin. Nothing is written inside the product clone; all writes go to a scratch directory. The scratch needs about 50 MB, most of it the 2.12.0 release cache entry.

### Setup

Set `REPO` to the clone, then run once:

```bash
S=$HOME/.cache/wm-fr; rm -rf "$S"; mkdir -p "$S/home" "$S/cand" "$S/base" "$S/cache"
git -C "$REPO" archive HEAD | tar -x -C "$S/cand"
git -C "$REPO" archive e5fa61f2bb3e75b1321f7cf4c90a73688ef8215d | tar -x -C "$S/base"
command cp -r ~/.cache/workflow-manager/releases/2.12.0 ~/.cache/workflow-manager/releases/2.12.0.lock "$S/cache/"
git init -q "$S/t" && git -C "$S/t" -c user.email=a@b -c user.name=fr commit -q --allow-empty -m init
_wm() { src=$1; shift; env -i R="$R" HOME=$S/home PATH=/usr/bin:/bin XDG_CACHE_HOME=$S/home/.cache XDG_CONFIG_HOME=$S/home/.config XDG_DATA_HOME=$S/home/.local/share WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache WORKFLOW_MANAGER_PINNED_ONLY=1 GIT_CONFIG_NOSYSTEM=1 python3 -I -c 'import sys, runpy; sys.path.insert(0, sys.argv[1]); sys.argv = ["workflow_manager"] + sys.argv[2:]; runpy.run_module("workflow_manager", run_name="__main__", alter_sys=True)' "$src" "$@"; }
wm_cand() { _wm "$S/cand/src" "$@"; }
wm_base() { _wm "$S/base/src" "$@"; }
R= wm_cand --release-version 2.12.0 bootstrap "$S/t"
mkdir -p "$S/t/scripts"
printf '%s\n' 'import os, sys' 'sys.stdout.write(open(os.environ["R"]).read())' > "$S/t/scripts/workflow_retention.py"
python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); d["complete"]=True; d["read_errors"]=[]; json.dump(d, open(sys.argv[2],"w"))' "$REPO/tests/fixtures/retention_report.json" "$S/ok.json"
R=$S/ok.json wm_cand status --retention "$S/t"   # must show the retention section, no KeyError
```

Each flow's crafted report is `$S/ok.json` with one field changed, written with `json.dump` to `$S/<flow>.json`, and run as `R=$S/<flow>.json wm_cand <command> --retention "$S/t"` and the same with `wm_base`, for `status` and `doctor`. Compare each flow's exit codes with `base`; the stub target has an untracked script, so the exit codes are not 0 by design.

### Test data

One scratch target repository bootstrapped at Workflow 2.12.0 (`$S/t`) with the stub engine above, and the valid report `$S/ok.json` (`tests/fixtures/retention_report.json`, `complete` true, `read_errors` empty). No real repository data is used.

### Flows

| Flow | Do | Expect (candidate) | Base |
| --- | --- | --- | --- |
| 1 | `repository` = `"a\nretention: forged"` | the two-line note `retention: not available: the script's report is malformed: repository contains a control character`; no `forged` in output | prints the forged second line |
| 2 | `read_errors` = one entry with `error` `"\u001b[31mred"`; `complete` false | the two-line note; no ESC byte (`grep -c "$(printf '\033')"` is 0) | prints the ESC |
| 3 | `repository` = `"a b"`, then separately `"a b"` | the two-line note for each | prints the separator |
| 4 | `totals.finished_folder_bytes` = `-1` | the note `totals.finished_folder_bytes is out of range (0 to 2**63 - 1)` | prints `-1 B` |
| 5 | `totals.finished_folder_bytes` = `10**400` (written as a literal integer) | the two-line note | one line of 465 characters |
| 6 | `repository` = 4097 `a`, then 4096 `a` | 4097: the note `repository is longer than 4096 characters`; 4096: the section prints | both print |
| 7 | `kind` = 5000 `x`; then `schema_version` = `10**400` | one note each, the echo cut to 40 characters and ending `... (N characters)` (the cause is 114 and 130 characters) | echoes the whole value |
| 8 | the valid report `$S/ok.json` | the section prints, `grep -c 'retention: not available'` is 0; `diff` of `cand` and `base` output is empty for both commands, exit codes equal | same |
| 9 | the retention tests, in a scratch copy: `cd "$S/cand" && git init -q && git add -A && git -c user.email=a@b -c user.name=fr commit -qm scratch && env -i HOME=$S/home PATH=/usr/bin:/bin WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache GIT_CONFIG_NOSYSTEM=1 python3 -I tests/run_all.py --select test_retention_status.py` | exit 0, `Ran 61 tests OK` | n/a |

Flow 9 runs in the scratch copy, not in `$REPO` as the plan's section 6 says: the runner writes into its working tree and needs a git repository, which the archive copy lacks.

Preparer's dry run, at `75fa536`: flows 1 to 8 were run in this exact shape for both trees, and every expectation above held. Flow 9 passed (61 of 61) in the same scratch layout. The whole run was repeated with networking removed (`unshare -rn`), with the same output. That run needed `--allow-root` for flow 9, because a user namespace is root; the sandbox itself is not expected to need it.

### Known limitations (out of scope for this item)

- Items 3 to 6 of #116 (the rate-limit step, the link and limit items, wording, checklist notes).
- Category `Cf` characters (bidirectional overrides) are not refused; a `removing` list is not bounded in length (#116 item 4). Both are follow-ups (plan section 5).
- The script's own stderr (`error:` and `next step:` lines on exit 2) is passed through unchanged; sanitising it is a follow-up.
- `doctor` exits 1 on the stub target in both trees (its dirty tree), and `status` exits 0; these are the baseline, not defects.

## Next action

Manual functional review of the checklist above, against the evidence commit (`/prepare-functional-review`'s step 3a). Findings go to `.ai-review/retention-view-hardening/feedback/FUNCTIONAL_REVIEW.md`; `/apply-functional-review` routes them. Once testing is clean, `/accept-milestone` closes the item, after its checkpoints are all `COMPLETE` (CP1 and CP2 are).
