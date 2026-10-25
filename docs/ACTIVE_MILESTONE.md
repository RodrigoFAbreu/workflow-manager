# Active Milestone

## Milestone

`operator-polish` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan
revision 1, base `5c06591`, branch `milestone/operator-polish`): roadmap row 14,
issue #84. A `fix:` pull request title (`src/` changes). Plan:
`docs/ai-workflow/WORKFLOW_MANAGER_OPERATOR_POLISH_PLAN.md`.

### CP1: the four fixes -- complete

- `source.py`: the null-record cause in `not_a_version`; `_log_once` carries the
  `using release` log in `ReleaseCache.resolve`, so one invocation prints a
  discovery note once.
- `cli.py`: `main` clears the once-record on entry; `cmd_status` re-raises a typed
  not-a-version refusal before printing the record.
- Docs: `docs/exit-codes.md` and `docs/update.md` list the refusal with its exit codes.
- Tests: `tests/test_discovery.py`, `tests/test_operator_ux.py`,
  `tests/test_operator_ux_docs.py`, `tests/test_docs.py`. Commit `193f5c8`.

### CP2: bookkeeping -- complete

- Row 14 of `docs/ROADMAP.md` is marked Current (`dc1052b`); it becomes Done at
  acceptance. This file records the milestone. No version is edited.
- The nightly `package` job's cache key (item 5) ships in its own `ci:` pull request.

### Self-review and the full gate

- The first full gate at `0ac15aa` failed one test:
  `test_operator_ux_readonly.TestPrintedCommandsParse.test_i3_verify_without_release_dir_after_a_scalar_install_asks_for_one`
  (subtest `version=None`) asserted the old `the installation record names` text
  for a null record, a second assertion the plan did not list. Its null case now
  expects CP1's cause (`76c63b3`); `123` and `""` keep the `names` wording.
- Red-first, in a clone at `0ac15aa` with `src/`, `docs/exit-codes.md` and
  `docs/update.md` restored to `5c06591`: 8 of the new or changed tests fail (the
  null record, typed `status`, the per-invocation reset, the `installed is the
  target` case for `doctor` and `update --dry-run`, both null-record subtests in
  `test_operator_ux`, the `docs/update.md` bullet) and both new exit-code rows of
  `test_operator_ux_docs` fail. Three discovery-note subtests (`pinned target`,
  `two discovered releases`, `pinned installed`) are green there: they guard the
  sole and distinct notes that must stay (EPR-001).
- Full gate `python3 tests/run_all.py` at `76c63b3`: exit 0, 2279/2279 units,
  14919 tests.

## Functional review checklist

Scope: the four fixes of issue #84 (items 1 to 4). Item 5 (the nightly `package`
job's cache key) is a CI change in its own `ci:` pull request and is not tested
here.

Setup: bash, from a clean checkout of `milestone/operator-polish` at the reviewed
head. The flows run from source, with `-B` so no bytecode lands in the clone, and
offline: no network, no `gh`, no `claude`, `codex` or `ssh`. Every write goes to
`$WORK`, a scratch folder outside the clone.

```bash
export REPO=/home/rodrigo/Workspace/workflow-manager   # the checkout under test
export WORK=$HOME/operator-polish-check               # scratch, outside the clone
export PYTHONPATH=$REPO/src
rm -rf "$WORK" && mkdir -p "$WORK/mirror"
for v in 2.12.0 2.13.0 2.14.0; do cp -r ~/.cache/workflow-manager/releases/$v "$WORK/mirror/$v"; done
mgr() { python3 -B -m workflow_manager --release-source "$WORK/mirror" --release-cache "$WORK/cache" "$@"; }
C() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }

git init -q "$WORK/repo" && C "$WORK/repo" commit -q --allow-empty -m init
mgr --release-version 2.12.0 bootstrap "$WORK/repo" && C "$WORK/repo" add -A && C "$WORK/repo" commit -qm "bootstrap 2.12.0"

git init -q "$WORK/repo13" && C "$WORK/repo13" commit -q --allow-empty -m init
mgr --release-version 2.13.0 bootstrap "$WORK/repo13" && C "$WORK/repo13" add -A && C "$WORK/repo13" commit -qm "bootstrap 2.13.0"
```

Test data: the mirror holds `2.12.0` (pinned by this Manager) and `2.13.0` and
`2.14.0` (discovered, not pinned). `$WORK/repo` is installed at 2.12.0 and
`$WORK/repo13` at 2.13.0. Each flow that changes a record works on a copy.

Flows (exit code, stdout, stderr as stated):

1. **Null record is refused with its cause** (item 1).
   `cp -r "$WORK/repo" "$WORK/null"`, then set `"workflow_version"` to `null` in
   `$WORK/null/.workflow-manager/installation.json`.
   - `mgr update "$WORK/null"`: exit 1, stdout empty. stderr says `the installation
     record has no workflow_version (it is null), which is not a version: a release
     is named X.Y.Z`, with a `next:` line. The text has no `None`.
   - `mgr update --dry-run "$WORK/null"`: exit 1, the same cause.
   - `mgr doctor "$WORK/null"`: exit 2, `could not resolve the target release: the
     installation record has no workflow_version (it is null)`.
   - `mgr status "$WORK/null"`: exit 1, and the record prints first
     (`workflow None (full profile)`), as a damaged record always has.

2. **The discovery note prints once per invocation** (item 2). Each `using release`
   line is counted on stderr.
   - `mgr doctor "$WORK/repo13"` (target 2.14.0): exit 0, two lines, one naming
     `2.14.0` and one naming `2.13.0`, each once.
   - `mgr --release-version 2.13.0 doctor "$WORK/repo13"` (installed = target): exit
     0, exactly one `using release 2.13.0` line.
   - `mgr --release-version 2.13.0 update --dry-run "$WORK/repo13"`: exit 0, exactly
     one `using release 2.13.0` line.
   - `mgr --release-version 2.13.0 doctor "$WORK/repo"` (pinned installed 2.12.0,
     discovered target): exit 0, exactly one `using release 2.13.0` line.

3. **A typed invalid release ends `status`** (item 3).
   - `mgr --release-version v2.12.0 status "$WORK/repo"`: exit 1, stdout empty
     (0 bytes), stderr `error: release 'v2.12.0' is not a version: a release is
     named X.Y.Z`, with a `next:` line that names `--release-version 2.12.0`.
   - `mgr --release-version 2.12.0 status "$WORK/repo"`: exit 0, first line
     `workflow 2.12.0 (full profile) — clean`.
   - `mgr status "$WORK/repo"`: exit 0, the same report.

4. **The docs name the refusal and its exit codes** (item 4). Read, do not run:
   - `docs/exit-codes.md`: the exit 1 row lists `bootstrap`, `update`, `update
     --dry-run`, `verify` and `status`; the exit 2 row lists `doctor`. Both say the
     release is not `X.Y.Z` or the record's `workflow_version` is not one, `null`
     included. They match flows 1 and 3.
   - `docs/update.md`, "If it fails": one bullet begins with `is not a version`,
     says `null` is not a version, and links [common problems](common-problems.md).

5. **Regression on a healthy repository**:
   - `mgr verify "$WORK/repo"`: exit 0.
   - `mgr update --dry-run "$WORK/repo"`: exit 0, the `would ...` lines and the
     report print as before.

Known limitations, out of scope for this milestone:

- The live GitHub listing and download are not exercised. The flows use a local
  mirror; the discovery note's text for a GitHub source is the same code path,
  with a different source name.
- The exact wording of human output is checked by the tests; this checklist
  checks the exit codes and the cause lines.
- Issue #84 item 5 (the nightly cache key) is not in this milestone.

Automated verification: the last full gate, `python3 tests/run_all.py` at
`76c63b3` (exit 0, 2279/2279 units, 14919 tests), is current. Only `docs/` and
`WORKFLOW_STATE.json` changed since it, so it is not rerun.

## Current checkpoint

CP1 and CP2 are complete, and so are the self-review and the full gate. The
milestone is at the functional review: the checklist above is ready for manual
testing.

## Next action

Run the functional review checklist. Findings go to
`.ai-review/operator-polish/feedback/FUNCTIONAL_REVIEW.md`, and
`/apply-functional-review` routes them. Once testing is clean and every checkpoint
is `COMPLETE`, `/accept-milestone` records acceptance.
