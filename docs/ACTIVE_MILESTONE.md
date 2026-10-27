# Active Milestone

## Milestone

`retention-status` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan
revision 7, base `3019c95`, branch `milestone/retention-status`): roadmap row 17,
issue #90. A `feat:` pull request title (`src/` changes; a Manager minor follows the
merge). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_STATUS_PLAN.md`.

### CP1: the opt-in retention section -- complete

- `src/workflow_manager/retention.py`: runs the repository's installed
  `scripts/workflow_retention.py report --json` in a subprocess (`python3 -I -B`, resolved
  absolute path, own session, 300-second timeout; on timeout the process group gets
  SIGTERM, then SIGKILL once the leader has exited or after two seconds, and only then
  is the leader reaped), validates the
  report's fields, and renders the section or one `retention: not available` note.
- `cli.py`: `--retention` on `status` and `doctor`; no other behaviour changes, and the
  option never changes an exit code.
- Docs: `docs/retention.md` (registered in `tools/check_docs.py`), `docs/exit-codes.md`,
  `docs/verify.md`, `docs/update.md`, `docs/README.md`.
- Tests: `tests/test_retention_status.py`, `tests/retention_recipe.py` (the real script
  driven through its `run`/`resolve` seams), `tests/fixtures/retention_report.json` (a
  report captured from the real 2.22.0 script).
- Deviation from the plan's text: the timeout ends the group with SIGTERM before SIGKILL
  (two seconds of grace). A bare SIGKILL re-parents the script's children to the runner's
  subreaper, which the orphan check counts even though they are dead; with SIGTERM first
  a script reaps its own children and the check stays clean.
- Deviation from the plan's file list: the page-specific documentation checks (the
  cause-and-step table built from `retention.py`, the index and exit-code rows, the
  coverage-versus-store wording) are in `tests/test_retention_status.py`'s `TestDocs`,
  not in `tests/test_docs.py`; `tests/test_docs.py` is unchanged and its `check_tree`
  run applies the header, internal-id and command-parse rules to the registered page.

### Self-review

- Fixed: a script that exits on SIGTERM while a child of its own ignores it. The child
  was never sent SIGKILL (the leader's reap ended the stop sequence), so it outlived the
  call and held the output pipes: the call blocked until that child exited. The group now
  always gets SIGKILL after the grace, and the leader is reaped only after that (an
  unreaped leader keeps the group id from being reused). The new test
  (`test_a_child_that_ignores_sigterm_is_killed_and_does_not_hold_the_call`) runs the call
  in a scratch child subreaper, so the adopted child never reaches the runner's orphan
  check; at the CP2 head it times out (the call waited the child's full 60 seconds).
- `docs/retention.md`: the case-6 row also names exit 2 without the refusal lines.
- Fixed (found by the first full gate, at `7a6d4bf`): `tests/retention_recipe.py`'s
  `init_origin` ran a bare `git init`, which `test_orphan_processes.py`'s `TestRoutingCheck`
  refuses; it now calls `init_git_repo` (`src/workflow_manager/fixture.py`), so the
  scratch repository gets the throwaway Git configuration every host test repository has.

### CP2: bookkeeping -- complete

Row 17 of `docs/ROADMAP.md` is Current (set when the plan started); it becomes Done at
acceptance. This file records the milestone. No version is edited.

### Verification

- Full gate, first run at `7a6d4bf`: `python3 tests/run_all.py` -> exit 1, one failure
  (`test_orphan_processes.py::TestRoutingCheck`, the recipe's bare `git init`; fixed in
  `ef52005`).
- Full gate, second run at `ef52005`: `python3 tests/run_all.py` -> exit 0 (full
  selection, 8 workers, 2302/2302 units, 15212 tests, orphan check on; `selection_digest
  20d92751...`, `tests_digest dfc9a75f...`, `tree_digest 2cb5d9dc...`).
- `python3 tools/check_docs.py` -> exit 0.
- Red first: with `3019c95`'s `src/` under `ef52005`'s tree (a scratch copy outside the
  repository), `python3 -m unittest test_retention_status` fails to import
  `workflow_manager.retention`, and `status --retention` and `doctor --retention` exit 2
  (`unrecognized arguments: --retention`). The SIGTERM-ignoring-child test also fails
  against `7a6d4bf`'s parent (it times out).
- Full gate at the implementation head `93e945f` (after the `7c1d8f0` fix of LIR2-001):
  `python3 tests/run_all.py` -> exit 0 (full selection, 8 workers, 2302/2302 units, 15217
  tests, orphan check on; `selection_digest 20d92751...`, `tests_digest 9e5d051b...`,
  `tree_digest f8b20128...`).
- Implementation review round 3 (`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` and
  `LOCAL_MODEL_IMPLEMENTATION_REVIEW`): APPROVE, no blocking or important findings. One
  Optional finding is open: EIR-003 (see Known limitations).

## Current checkpoint

None: CP1 and CP2 are complete. The item is at `AWAITING_FUNCTIONAL_REVIEW`; technical
approval is current.

## Next action

Manual functional review by the user, against the checklist below. The flows marked
"user-run" need real GitHub and cannot run offline; they are part of acceptance.

## Functional review checklist

Scope: `status --retention` and `doctor --retention`, the opt-in section of
`docs/retention.md`. Every flow except the last one is offline and needs no `gh`, no
network and no real GitHub.

### Setup

- Python 3.11 or later. Run the checkout's code from the repository root:
  `PYTHONPATH=src python3 -m workflow_manager` (the same command as `workflow-manager`;
  do not use the pipx-installed release).
- A scratch managed repository: a copy of a bootstrapped repository on Workflow 2.22.0,
  under your own scratch directory. Set `HOME`, `XDG_*` and `TMPDIR` to scratch
  directories, so the default archive root (`~/.local/share/workflow-archive`) is not
  read from the developer's machine.
- The stub `scripts/workflow_retention.py` for each flow below: a Python script that
  prints a fixed JSON report (or a fixed error and exit status) and, when the flow asks,
  records its `argv` and `cwd` and creates a marker file outside the repository.
- Fixture: `tests/fixtures/retention_report.json` (captured from the real 2.22.0 script;
  `complete` is false and it carries one `read_errors` entry). A "complete" variant is
  the same file with `complete` true and `read_errors` emptied.

### Test data

- Stub reports only (flows 1 to 10): the fixture and its variants.
- Flow 11: the real `scripts/workflow_retention.py` and `scripts/workflow_forge.py`,
  copied from this checkout, with a state that has no `MILESTONE_COMPLETE` item.
- Flow 12: a scratch clone of this repository, with `gh` signed in.

### Flows

Each flow records stdout, stderr and the exit code.

1. **Default output unchanged** (offline). Run `status <repo>` and `doctor <repo>`
   with no option. Expected: no line starts with `retention`; the stub's marker file is
   absent; the output is byte-identical to a run with the stub removed; the exit code is
   the same as the clean repository's baseline (0).
2. **`status --retention`, complete report** (offline). Stub prints the "complete"
   variant. Expected: the section appears after the work-in-flight block and before the
   final `next:` line (which stays the last line of the output). The header is
   `retention (read-only; the Workflow script made one forge query per finished item):`.
   The counts match the report's `totals` and `finished[].archive`. The exit code equals
   the baseline.
3. **`doctor --retention`** (offline). Same stub and report as flow 2. Expected: the
   section after the doctor report; the doctor's own findings and exit code are unchanged.
4. **`removing` key** (offline). Three runs: `removing` present and empty, shows
   `interrupted removals: none`; `removing` absent, shows `interrupted removals: not
   reported by this Workflow release`; `removing` naming an id that is not in `finished`,
   lists the id and prints no `remove` command.
5. **Incomplete report** (offline). (a) The fixture as it is: expected the first line
   `retention: INCOMPLETE`, the read error named (at most five paths, then a count), and
   numbers labelled as lower bounds. (b) One `not_finished` entry with reason
   `query_failed:rate_limited`: the same INCOMPLETE header, naming the item and the code.
   (c) Every candidate `query_failed`: the case-7 note (`retention: not available: the
   forge could not be queried (rate_limited, N items)`), not a clean report.
6. **Next command and capability** (offline). (a) An eligible item (finished, archive
   absent and readable, folder present, no tracked files): the printed command is
   `python3 -I scripts/workflow_retention.py archive ID --apply`, and the section says to
   run it without `--apply` first. (b) An archived finished item with its folder present
   and no tracked files: the `remove ID --apply` command. (c) Nothing to do: `next:
   nothing to archive`. (d) The record's `workflow_version` at 2.20.0 with an eligible
   item: no `archive` command, only `workflow-manager update TARGET`. The counts are
   still shown. (e) At 2.21.0 with an archived item: no `remove` command, only the update
   step. (f) A missing or unparseable version: no command at all.
   The Manager never runs any of these: check that the scratch tree is unchanged.
7. **Refusals, each one cause and one step** (offline). For each case the output has
   exactly one `retention: not available: CAUSE` line and one `  next: STEP` line (two
   spaces of indent), the exit code equals the baseline, and there is no `Traceback`.
   (a) `status` on a repository that is not managed: cause "not managed", step
   `workflow-manager bootstrap TARGET`, exit 0. (b) The script deleted: cause "the
   repository has no scripts/workflow_retention.py". (c) The script replaced by a link:
   the same cause. (d) The script exits 2 with `error: repository_unknown: ...` and
   `next step: ...`: its own two lines are passed through. (e) The script exits 1: a case-6
   note naming the exit status. (f) Stdout is not JSON: case 6. (g) `kind` is not
   `retention-report`, or `schema_version` is 2: case 6 with the update step. (h) A
   report missing a required field, or `finished` entries without `archive`: case 6,
   naming the field.
8. **Timeout leaves no process** (offline, about 5 minutes). Stub spawns a child that
   sleeps with a marker in its arguments, then sleeps itself. Expected after about 300
   seconds: `retention: not available: the report did not finish within 300 seconds` and
   `  next: run ...` (the script directly); the exit code is the baseline; the child's
   process is gone (look it up by the marker; a `grep` for the script's own name matches
   the grep itself).
9. **No writes** (offline). Hash the whole scratch tree, including `.git`, before and
   after flows 2 to 8, and once for the success path. Expected: equal hashes, and no
   `__pycache__` directory.
10. **Relative target and spaces** (offline). From the parent directory run
    `status --retention nested/repo` and the same for a path containing spaces. The stub
    records its `argv` and `cwd` to a file outside the repository. Expected: both are
    absolute and equal to the resolved target; the report renders; the exit code is the
    baseline.
11. **Real script, no forge query** (offline). Copy the real `scripts/workflow_retention.py`
    and `scripts/workflow_forge.py` into the scratch repository. Its state has no
    `MILESTONE_COMPLETE` item and its `origin` is a GitHub URL (no fetch). Expected: the
    section renders the real JSON with zero finished items, no read errors and no
    incomplete header. The sandbox's `gh` refusal log is empty (no forge call).
12. **Real forge** (user-run, not in the offline sandbox; required before acceptance).
    In a scratch clone of this repository, with `gh` signed in and the installed Workflow
    2.22.0 script: run `status --retention` and `doctor --retention`. Expected: the
    section, with finished counts matching what GitHub says about the merged pull
    requests; the exit codes are the baseline. Never run `archive` or `remove` in that
    clone. Compare the clone's tree before and after.

### Expected results summary

Every flow ends with the exit codes of the no-option run, no `Traceback` in any output,
and no change in the scratch tree.

### Known limitations

- EIR-003 (Optional, open): the renderer accepts negative integers, so a report with
  `finished_folder_bytes: -1` renders as `-1 B`. This does not change any exit code and
  produces no traceback. It is recorded as an Optional finding for disposition at
  acceptance; it is not a functional blocker.
- The Manager never runs `archive`, `remove` or any other script command, and it never
  prunes: prunable archives get no command, and the section says so.
- The 300-second timeout covers about ten times the forge time for 25 finished items. A
  repository with many more finished items gets the case-4 note.
- The report does not expose the archive index, `.partial` files, `zstd` or file-system
  boundaries; the script refuses those itself with its own next step, and the section
  claims nothing about them.

### After testing

- Clean run: `/accept-milestone` is the only acceptance command. It requires every
  checkpoint in this item's registry to be `COMPLETE`; CP1 and CP2 already are.
- Findings: write them to `.ai-review/retention-status/feedback/FUNCTIONAL_REVIEW.md`.
  `/apply-functional-review` routes each one: a bounded fix, or a
  `retention-status-remediation-<n>` child work item for wider scope.
