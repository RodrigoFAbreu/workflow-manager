# Active Milestone

## Milestone

**Functional review.** `retention-pins-and-wording-2` (`governing_workflow_version: "2.2"`, `process`, plan revision 4, implementation revision 1, base `a243144`, branch `milestone/retention-pins-and-wording-2`): roadmap row 48

The retention report, alert and docs say exactly what the code does (#160, #222, #225, #216). An incomplete report whose forge queries all failed is shown as incomplete, one refusal helper replaces the duplicated block of `doctor`, and the retention wording and tests are pinned. A `fix:` change, Manager patch release 1.20.3.

### CP1: the note reads `complete`, one refusal helper -- complete

- `retention.py`: `_query_failed_note` returns `None` for an incomplete report, so `status`, `doctor`, `verify` and `retention-cleanup` show the incomplete report (cleanup refuses at step 8) instead of the forge note.
- `cli.py`: `_refuse_release_resolution(args, error)` replaces the two identical refusal blocks of `_doctor_json` and `cmd_doctor`; output unchanged.
- Tests: two fixtures get `"complete": True`; new incomplete, mixed-incomplete and complete-counterpart cases in `tests/test_retention_status.py`; a `TestPreflight` case in `tests/test_retention_cleanup.py` (refused at step 8, nothing written).
- Mutations M1 to M3 measured in scratch clones outside the repository: each fails the named tests. The golden of plan section 2.1 was not run as a separate script; the new tests cover the incomplete, mixed and complete reports. Narrow selection (`test_retention_status`, `_alert`, `_alert_json`, `_cleanup`, `test_doctor_cli`, `test_operator_ux`): verdict exit 0.
- `docs/ROADMAP.md`: row 48 added, Current.

### CP2: the tests and the docs -- complete

- `docs/retention.md`: one sentence in "If the report is incomplete" (an incomplete report is shown as incomplete even when every forge query failed; the forge cause is for a complete report), and the age-step bullet names the unreadable-archive exception (#160.1, #222.1).
- Links: the five `[Retention report](retention.md...)` links in `docs/README.md`, `update.md`, `verify.md` and `exit-codes.md` (two) read the page's title (#216.1).
- Tests: `TestDocs` pins the limits sentences (`2**63 - 1`, `INT_MAX`, the `invalid_id` clause and its code behaviour), the incomplete-report sentences and the link text; `TestAgeStep` pins the unreadable-archive clause; the release-below-2.21.0 scenario compares the whole line (#222.2); the release-option test's last case runs against `self.repo` with the corrupt record, and the `--manager-root` case asserts the deprecation line and the error line (#225.1, #225.3); the first report of the pushed-out test holds the archive (#225.4).
- KEEP: #222.3 (`1 items`) and the archived plan and declaration points of #216.
- Mutations M4 to M8 measured in a scratch copy outside the repository: each fails the named test. `python3 tools/check_docs.py` clean; `git diff` of `tools .claude scripts .workflow-manager tests/parallel` against the base is empty. Narrow selection (`test_retention_status`, `_alert`, `_alert_json`, `_cleanup`, `test_doctor_cli`, `test_operator_ux`, `test_docs`): verdict exit 0.

### Self-review and the full gate

- The full milestone diff matches the plan's file list and sections; no blocking or important finding, no code change.
- The plan's section 2.1 golden, not run at CP1, ran in a scratch directory outside the repository: base `src` (`a243144`) against the candidate (`9aa1513`) for the retention section, the alert text, the alert JSON and the cleanup preflight over 41 reports, the three refusal shapes and two adopted policies. 28 of 313 outputs differ, all for the four incomplete reports with no finished or kept item and only `query_failed` items (with or without `open_phase`, with or without read errors), each as the plan's table says; every other output is identical.
- Plan section 6 flows 1 to 7 and 9 give the expected results; the title check reads `valid title: fix, release impact patch`.
- Full gate: `evidence: full selection, local, 8 worker(s), head 9aa1513587073556fd8c27432fd022cd35219810, 2438/2438 units, 16481 tests, selection_digest 9957d343edee4613b59b75a4d916afa09d860b8240978644a6c90b09637c9ef4, tests_digest f7d7202276056f763121f95f0268abf00b36174f3aaae9a496a27706be5e40b0, tree_digest 984aa66960ddfc45c12976d89490168dab155b9617ef7408d3b488a8cc8fd3a9`, `verdict: exit 0`; the only orphans are the declared `orphan_sources`.

## Functional review checklist

You are checking that the retention report, the alert and the docs say what the code does, and that an incomplete report is shown as incomplete.

- **Technical approval:** implementation revision 1, reviewed content commit `904807103`. Both stages approved it: `LOCAL_MODEL_IMPLEMENTATION_REVIEW` (Claude Opus 5.5, round 1) and `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` (gpt-6.1-sol, round 1).
- **Automated verification:** current, no rerun needed. The full gate passed at `9aa1513` (`2438/2438 units`, `16481 tests`, `verdict: exit 0`). The code has not changed since: `git diff --stat 9aa1513..HEAD -- src tests tools tests/parallel` is empty. Only docs and state commits have landed (`9048071`, `f6ece98`, `098a22b`).
- **Where findings go:** `.ai-review/retention-pins-and-wording-2/feedback/FUNCTIONAL_REVIEW.md` (`.ai-review/` is git-ignored).

**Setup.**
- Python 3.11 or later, `git`, a Linux or macOS shell. Nothing to install, no feature flags.
- Test the branch head with a clean working tree. Flows 1 to 7 and 9 read the checkout; flow 10 works in a scratch clone:

```bash
export M=~/Workspace/workflow-manager
export T=$(mktemp -d) && git clone -q "$M" "$T/c"
```

- Flows 8 and 10 run `tests/run_all.py`, which primes the release cache before dispatch (`tests/parallel/cli.py:261`). A missing entry is fetched from GitHub. Offline, the run needs a complete release cache, or `WORKFLOW_MANAGER_RELEASE_SOURCE` pointing at a mirror. Without one it stops with `PrimingError`, exit 2.

**Sandbox.** Flows 1 to 7 and 9 need no network, no forge, no `claude`, `codex` or `ssh`, and write nothing: they run in the functional tester's sandbox. Flows 8 and 10 run only with a primed release cache and a writable temp directory outside the clone; they are not sandbox-runnable from a cold cache.

**Test data.** None. The flows read the checkout and the scratch clone only.

**Flows.** Expected results are those of the plan's section 6, checked against this branch's head on 2026-11-16 for flows 1 to 7 and 9.

1. **Scope of the change.** In `$M`, run `git diff --stat a2431446 -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md' ':!docs/milestones'`.
   Expect: 12 files, all of them `src/workflow_manager/retention.py`, `src/workflow_manager/cli.py`, the four retention tests (`test_retention_alert.py`, `test_retention_alert_json.py`, `test_retention_cleanup.py`, `test_retention_status.py`), the five pages (`docs/README.md`, `docs/exit-codes.md`, `docs/retention.md`, `docs/update.md`, `docs/verify.md`) and `docs/ROADMAP.md`.
2. **Untouched trees.** Run `git diff --exit-code a2431446 -- tools .claude scripts .workflow-manager tests/parallel README.md docs/glossary.md; echo $?`.
   Expect: no output and `0`.
3. **No page stamp moved.** Run `git diff a2431446 -- docs/retention.md docs/README.md docs/update.md docs/verify.md docs/exit-codes.md | grep -c '^[-+]> For:'`.
   Expect: `0`.
4. **Links read the page's title.** Run `grep -rn --exclude-dir=ai-workflow --exclude-dir=milestones --exclude=ACTIVE_MILESTONE.md '\[Retention report\](retention' docs README.md; echo $?`.
   Expect: no output and `1`. Then run `grep -rc --include='*.md' '\[Retention: the report, the policy, the alert and the cleanup\](retention.md' docs/README.md docs/update.md docs/verify.md docs/exit-codes.md`.
   Expect one count per file: `docs/README.md` 1, `docs/update.md` 1, `docs/verify.md` 1, `docs/exit-codes.md` 2.
5. **One guard in the code.** Run `git diff a2431446 -- src/workflow_manager/retention.py`.
   Expect: only the docstring of `_query_failed_note` and the added `if not report["complete"]: return None`, nothing else.
6. **The page says it.** Run `grep -n 'complete' docs/retention.md | sed -n 1,8p` and `grep -c 'cannot be read' docs/retention.md`.
   Expect: the new sentence in "If the report is incomplete" (line 52: an incomplete report is shown as incomplete even when every forge query failed), beside the existing sentence at line 46. The count is `1` or more.
7. **Docs check.** Run `python3 tools/check_docs.py; echo $?`.
   Expect: no problem line and `0`.
8. **Targeted selection, not a gate.** Run `python3 tests/run_all.py --select test_retention_status.py --select test_retention_alert.py --select test_retention_alert_json.py --select test_retention_cleanup.py --select test_docs.py; echo $?`.
   Expect: `verdict: exit 0` and `0`. This needs the release cache (see Setup).
9. **Roadmap row.** Run `grep -n -E '^\| 48 ' docs/ROADMAP.md` and `grep -c -E '^\| 49 ' docs/ROADMAP.md`.
   Expect: row 48 present with the last cell `Current`, then `0`.
10. **Mutations fail the named tests.** In `$T/c`, apply each mutation, run its selection, expect the failure, then restore the clone.
    - **M1:** delete the two lines `if not report["complete"]:` and `return None` from `_query_failed_note` in `src/workflow_manager/retention.py`. Run `python3 tests/run_all.py --select test_retention_status.py; echo $?`. Expect the incomplete-report tests to FAIL, `verdict: exit 1`, `1`. Restore with `git checkout -- src/workflow_manager/retention.py`.
    - **M4:** in `docs/retention.md`, change `2**63 - 1` (line 82) to `2**31 - 1`. Run `python3 tests/run_all.py --select test_docs.py; echo $?`. Expect the limits pin to FAIL, `verdict: exit 1`, `1`. Restore with `git checkout -- docs/retention.md`.
    - Restore the clone (`git status` is clean) and run `python3 tests/run_all.py --select test_retention_status.py; echo $?`. Expect `verdict: exit 0`, `0`: the unmutated clone passes.
    - Mutations M2, M3, M5 to M8 are in plan section 3 for a fuller pass. They are optional for this round.
    - This flow needs the release cache (see Setup).

**Known limitations and open items.** None of these blocks acceptance; each is an optional finding, to be dispositioned at `/accept-milestone`.
- Out of scope: the singular `1 item` form (`#222.3`, KEEP) and the archived plan and declaration points of `#216` (KEEP). The archived plans are bound records.
- `docs/retention.md:52`: the paragraph uses "incomplete" for failed forge queries as well. The new sentence means a report with read errors (the guard checks `complete`). The review suggests "report with read errors" in the new sentence. Judge whether it reads clearly.
- No gate test pins the `verify` or `doctor` alert text, or the `doctor --retention --json` document, for an incomplete report. The guard is pinned through the `status`, `doctor` and cleanup tests; the plan's section 2.1 golden covered the alert outputs once, in a scratch directory.
- Plan-stage optional findings (the `X1` comparison, the declaration's list of prefixes, the mutation wording) do not change behaviour.

**After testing.**
- Findings go to `.ai-review/retention-pins-and-wording-2/feedback/FUNCTIONAL_REVIEW.md`. Run `/apply-functional-review`: a same-scope fix takes the bounded branch, a wider one a `retention-pins-and-wording-2-remediation-<n>` child.
- Clean testing: `/accept-milestone`. Both checkpoints (CP1, CP2) are `COMPLETE`, so it is available.

## Next action

The user runs the functional review checklist above, at the checklist evidence commit this round records, and reports the result.
