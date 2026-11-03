# Active Milestone

## Milestone

`version-message-wording` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `10213e0`, branch `milestone/version-message-wording`): roadmap row 26 (#145, items 1 and 2). A `fix:` pull request title (releases a Manager patch; no version is edited). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_VERSION_MESSAGE_WORDING_PLAN.md`.

A version taken from the installation record is named in words in the messages that quote it: a null reads as `no workflow_version recorded` (the `next:` line of `verify` and `status`, and the `status` header), an empty value as `''` (the `status` header and the `verify` `version:` line). Every other value, message and exit code is byte-identical. No Workflow change.

### CP1: the wording, its function and its tests -- complete

- `install.record_head` (used by `Status.__str__` and `cli._print_record`), the null branch of `advice._directory_step`, the quoted empty value in `install.verify`, and `TestNotAVersionRows.test_a_version_the_operator_did_not_type_is_named_in_words` (commit `c90589e`).

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 26 is Current; the acceptance step marks it Done.

### Mutation results (scratch copy of `c90589e` outside the repository, `python3 tests/run_all.py --select test_operator_ux.py::TestNotAVersionRows`; the candidate passes)

Each mutation exits 1 and fails the case the plan names:

| Mutation | Failed |
| --- | --- |
| (a) `_directory_step` null branch removed | `test_a_version_the_operator_did_not_type_is_named_in_words` (null) |
| (b) `record_head` null branch removed | same case (null) |
| (c) `record_head` empty branch removed | same case (empty) |
| (d) `verify` without the quoting | same case (empty) |
| (e) `_print_record` back to its own f-string | same case (null and empty; `_print_record` only) |
| (f) `shlex.quote` of `_not_a_version`'s directory removed | existing `test_a_null_record_with_a_release_dir_names_one_step_without_it` (`null-manifest update --dry-run`, `null-manifest doctor`) |

No mutation survives. `python3 tests/run_all.py --select test_operator_ux.py` at `c90589e`: 128 tests, `verdict: exit 0`.

### Self-review of the full diff

- The new test now asserts both commands end to end for the empty value too, as the plan's section 3 says (`verify`: the step alone; `status`: the step, `; `, then `advice.doctor_step` built on the same context), and the `status` line exactly instead of by prefix; the number case no longer builds a scratch repository it does not use. Code unchanged. `python3 tests/run_all.py --select test_operator_ux.py::TestNotAVersionRows`: 10 tests, `verdict: exit 0`.

## Functional review checklist

Candidate: code head `b9ba561` (`src/` is identical at `b42e478`; the commits after it change only `docs/ai-workflow/WORKFLOW_STATE.json`). Base: `10213e0`. Automated verification at `b9ba561`: `python3 tests/run_all.py`, full selection, 2329/2329 units, 15538 tests, `verdict: exit 0` (`.ai-review/version-message-wording/current/TEST_RESULTS.md`).

### Setup

No install, no network, no release cache, no `gh`, `claude`, `codex` or `ssh`. Run from the repository root with Python 3. The flows read the repository through `git archive` and write only to a scratch directory on disk, outside the repository and not `/tmp`:

```bash
S=$(mktemp -d "$HOME/.cache/vmw-fr.XXXXXX")
mkdir -p "$S/base" "$S/cand"
git archive 10213e0 src | tar -x -C "$S/base"
git archive b9ba561 src | tar -x -C "$S/cand"
cat > "$S/h.py" <<'EOF'
import sys,argparse
from pathlib import Path
sys.path.insert(0,sys.argv[1]+"/src")
from workflow_manager import advice,install
def step(v): return advice.problem_step(advice.Context(args=argparse.Namespace(command="verify",target=Path("/t"),release_version="2.12.0",release_source=None,release_cache=None,release_dir=None,profile=None),installed_version=v,installed_recorded=True),["version: x"])
exec(sys.argv[2])
EOF
```

Run each flow as `python3 -I "$S/h.py" "$S/cand" "<code>"` (or `"$S/base"` where a flow says so). Each flow is its own process. All six flows were run once against both trees with `env -i PATH=/usr/bin:/bin unshare -rn`; they produced the strings below.

### Test data

None to seed. The inputs are the literal values in the code strings: a null (`None`), an empty value (`''`), a number (`123`) and `'1.0.0'`.

### Flows

Each expected line must match exactly. A mismatch is a finding.

| Flow | Code (`<code>`) | Expect on `cand` | Base (`10213e0`), for comparison |
| --- | --- | --- | --- |
| 1 | `print(step(None))` | `a release directory is needed (no workflow_version recorded): run the command again with --release-dir DIR` | `a release directory holding None is needed: ...` |
| 2 | `print(install.Status(True,None,'full',['p'],True))` | first line `no workflow_version recorded (full profile) — 1 problem(s):` | `workflow None (full profile) — 1 problem(s):` |
| 3 | `print(install.Status(True,'','full',[],True))` | `workflow '' (full profile) — clean` | `workflow  (full profile) — clean` (two spaces) |
| 4 | `print(step(''))` | `a release directory holding '' is needed: run the command again with --release-dir DIR` (same on base) | same |
| 5 | `print(step(123));print(install.Status(True,123,'full',[],True));print(install.Status(True,'1.0.0','full',['p'],False))` | `a release directory holding 123 is needed: ...`, then `workflow 123 (full profile) — clean`, then `workflow 1.0.0 (full profile) — 1 problem(s):` and `  p` (same on base) | same |
| 6 | `print(install.record_head(None,'full'));print(install.record_head('','runtime'));print(install.record_head('2.12.0','full'))` | `no workflow_version recorded (full profile)`, `workflow '' (runtime profile)`, `workflow 2.12.0 (full profile)` (candidate only; `record_head` does not exist on base) | n/a |

Flows 1 to 3 and 6 are the changed wording. Flows 4 and 5 must not change.

### Known limitations

- The flows call the changed functions through the harness, not the `workflow_manager` command line. The command-line paths (`verify` and `status --release-version V` on a null or empty record) are asserted by `TestNotAVersionRows` in `tests/test_operator_ux.py`, which the full gate ran at `b9ba561`. They need the release cache, so they are not offline flows here.
- Out of scope and unchanged: `update` vs `update --dry-run` on a null record (issue #145, item 4, stays open); `AlreadyManagedError` and the dry-run lines of `update`, which still print a recorded version as-is. Issue #145 item 3 (the unquoted `--release-dir` in `_not_a_version`) was already fixed on `main`, so this change does not touch it.
- A number or other non-text value keeps its present text on purpose.
- No Workflow change, no exit-code change, no version edited (a `fix:` patch on merge).

### Cleanup

```bash
rm -rf "$S"
```

## Next action

Functional review (user). Run the flows above and place any findings at `.ai-review/version-message-wording/feedback/FUNCTIONAL_REVIEW.md`. Clean testing goes to `/accept-milestone`, the only acceptance command, which requires every checkpoint to be `COMPLETE` (CP1 and CP2 are). Findings go to `/apply-functional-review`.
