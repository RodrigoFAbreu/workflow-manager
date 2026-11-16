# Active Milestone

## Milestone

**Functional review.** `priming-wording-and-alert-pins` (`governing_workflow_version: "2.2"`, `process`, plan revision 4, implementation revision 2, base `59beeea`, branch `milestone/priming-wording-and-alert-pins`): no roadmap row; the roadmap row and this narrative are written at acceptance.

Two small follow-ups from reviewed issues: the Priming bullet of `docs/ARCHITECTURE.md` says what is true about test-time fetches and about the filesystem the free-space check does not cover (#190, #168), and two gate tests pin what an incomplete retention report whose unfinished items are all `query_failed` shows, in the `doctor --retention --json` document and in the verify/doctor alert text (point 2 of #242). A `test:` change, no release.

### CP1: the Priming bullet wording -- complete

- `docs/ARCHITECTURE.md`: "the ambient `TMPDIR`, a filesystem the check does not then measure" becomes "the effective `TMPDIR`, a filesystem the check does not cover when `--results` is on another filesystem"; "no test fetches a release at test time" becomes "no test fetches a release from a remote host". Nothing else on the page changes; the page has no stamp.

### CP2: the two gate tests -- complete

- `tests/test_retention_alert_json.py`: new `test_J4_an_incomplete_report_whose_queries_all_failed_is_not_evaluated` in `TestGoldens`, with the new whole-document golden `J4-queries-failed` (the `J4` document with `current_value` 0 for both alerts and an all-zero snapshot), and a `complete=True` subcase checked by its fields (`evaluation` not evaluated, `report_complete` false, cause incomplete, every alert `unknown`).
- `tests/test_retention_alert.py`: new `test_an_incomplete_report_whose_queries_all_failed_is_not_evaluated` in `TestUnavailable`, for `verify` and `doctor`: one not-evaluated line with the incomplete cause, the `next:` line with `retention.STEP_INCOMPLETE`, and the baseline exit code.
- No `src/`, `tools/` or managed-file change.
- Verified at implementation revision 2 (`8342e14`): full gate `evidence: full selection, local, 8 worker(s), head 8342e14f010bf03e1e2a25e4bb97f9dec3da13f2, 2438/2438 units, 16487 tests`, `verdict: exit 0`; the narrow selection of the two files `verdict: exit 0` (110 tests); the mutation of `retention.py`'s `_query_failed_note` guard makes three tests fail, including `J4-queries-failed`.

### Review and approval

- Local implementation review: round 2 `APPROVE` (`anthropic/claude-opus-5-5`), round 1 `REVISE` (I1: the new tests missed the all-queries-failed scenario; fixed in `8342e14`).
- Manual external implementation review: round 2 `APPROVE` (`openai/gpt-6.1-sol`).
- Technical approval: `CURRENT`, `POLICY_SATISFIED`, bound to the round-2 bundle.
- Plan approval: `CURRENT`, `POLICY_SATISFIED`, at plan revision 4, bound to the `APPROVE` verdicts of `anthropic/claude-opus-5-5` (local) and `openai/gpt-6.1-sol` (manual) for that bundle. The optional plan-review finding PWA-L1-003 (M4 missing from Flow 6) is in the state's `optional_findings`; plan revision 4 puts M1 to M4 in flow 8 of this checklist. Optional findings are dispositioned at acceptance.

## Functional review checklist

Implementation revision 2; base `59beeea`; the candidate is the tip of `milestone/priming-wording-and-alert-pins`, which is this checklist's evidence commit. The automated gate was run at `8342e14` (the last code change). Since then only `docs/ai-workflow/WORKFLOW_STATE.json` has changed, so the gate is current; nothing under `src/`, `tools/`, `.claude/`, `scripts/`, `.workflow-manager/` or `tests/parallel/` differs from the base.

The change is a docs paragraph and two gate tests. There is no user-facing behaviour to exercise; each flow checks that the change is what the plan says and that the new tests fail when the behaviour they pin breaks.

### Setup

- Sandbox-runnable (flows 1 to 6 and 9): offline, with `git`, `grep`, `sed`, `tr`, `python3` and `-m unittest` only. No GitHub, no `gh`, no `claude`/`codex`/`ssh`, no install.
- Full environment (flows 7 and 8): they need the primed release cache that `tests/run_all.py` uses. Offline with no primed cache, `run_all.py` exits 2 (`PrimingError`) before any test runs. Run them on a machine with the cache primed, or with a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror.
- Scratch clone, outside the product clone: `S=$(mktemp -d)`, then `git clone --no-hardlinks /home/rodrigo/Workspace/workflow-manager "$S/cand"` and `cd "$S/cand"`. The clone holds the committed `HEAD`. Write logs only under `$S`; remove `$S` when done.
- `B=59beeea99ac8e976b835dc9ab6d8544ba207feb2`. Read each exit code with `; echo $?`, not through a pipe.

### Test data

None. The flows read the diff and run the test selections. Flow 8 applies the four mutations of the plan's section 3 to scratch copies, one at a time.

### Flows

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd "$S/cand" && git diff --name-only $B HEAD -- src tools tests docs .github .claude scripts .workflow-manager ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` then `git diff --name-only $B HEAD -- docs/ai-workflow` | First command: exactly `docs/ARCHITECTURE.md`, `tests/test_retention_alert.py`, `tests/test_retention_alert_json.py`. Second: the plan, the registry, the mapping, the artifacts file and `WORKFLOW_STATE.json`. Nothing under `src/`, `tools/`, `.claude/`, `scripts/`, `.workflow-manager/`, `tests/parallel/`. (`docs/ACTIVE_MILESTONE.md` is this checklist, excluded here because the plan's section 5 predates it.) |
| 2 | `tr '\n' ' ' < docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'no test fetches a release from a remote host.\{0,60\}'` and `tr '\n' ' ' < docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'the effective .TMPDIR., a filesystem the check does not cover when .--results. is on another filesystem'` | each prints one line: the first starts `no test fetches a release from a remote host:`, the second is the new TMPDIR sentence |
| 3 | the same `tr` pipe on `docs/ARCHITECTURE.md`, with `grep -c` for `release at test time`, `the ambient` and `does not then measure`; then `grep -c 'Last checked with' docs/ARCHITECTURE.md` | `0` for each old phrase; `0` for the stamp count (the page has no stamp, so none moved) |
| 4 | `cd "$S/cand" && git diff --exit-code $B HEAD -- docs/retention.md docs/update.md docs/exit-codes.md docs/glossary.md docs/install.md docs/development.md README.md tests/test_retention_status.py tests/test_docs.py tools src; echo $?` | `0` (pages and tests not re-checked were not touched) |
| 5 | `cd "$S/cand/tests" && python3 -m unittest test_retention_alert test_retention_alert_json > "$S/unit.log" 2>&1; echo $?`, then `tail -3 "$S/unit.log"`; then `cd "$S/cand" && grep -n 'queries_all_failed\|J4-queries-failed' tests/test_retention_alert*.py` | exit `0`; the log ends `Ran 110 tests` and `OK`; the grep finds `test_an_incomplete_report_whose_queries_all_failed_is_not_evaluated` in `test_retention_alert.py`, `test_J4_an_incomplete_report_whose_queries_all_failed_is_not_evaluated` and the golden key `"J4-queries-failed"` in `test_retention_alert_json.py` |
| 6 | `cd "$S/cand" && python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 7 | (full environment) `cd "$S/cand" && python3 tests/run_all.py --select test_retention_alert_json.py --select test_retention_alert.py --select test_docs.py; echo $?` | `verdict: exit 0`, exit `0`, no `OrphanProcessError`; the run includes both new tests (flow 5 shows they exist) |
| 8 | (full environment) in scratch copies of `$S/cand` outside the clone, one mutation per copy, applied with `sed -i` to that copy only: **M1** `src/workflow_manager/retention_alert.py` line 56, `sed -i '56s/ or failed$//'` (drops `or failed` from the return); **M2** `src/workflow_manager/retention_alert_json.py` line 103, `sed -i '103s/"report_complete": complete,/"report_complete": True,/'`; **M3** `src/workflow_manager/retention_alert.py` line 32, change the word `incomplete` in `CAUSE_INCOMPLETE` to `unfinished`; **M4** `src/workflow_manager/retention.py` line 52, change the word `named` in `STEP_INCOMPLETE` to `listed`. Each copy: `python3 tests/run_all.py --select test_retention_alert_json.py --select test_retention_alert.py --select test_retention_status.py` (one `--select` each). An unmutated copy first. (Equivalent in a copy: `cd tests && python3 -m unittest test_retention_alert test_retention_alert_json test_retention_status`.) | The unmutated copy passes. Each mutation has the named new test among its failures: M1 the new J test (`complete=True` subcase) and the new text test, M2 the new J test, M3 the new J test, M4 the new J test; the new text test passes under M3 and M4, because it names the constants. Do not compare the whole failing set (M2 also fails many existing goldens; that is expected). Check each copy's `git diff --stat` shows only its one line. |
| 9 | `python3 tools/release/release.py check-title "test: pin the alert for an incomplete report whose forge queries all failed, and tighten two priming sentences"; echo $?` | `valid title: test, release impact none`, then `0` |

Flows 5 and 6 are the offline equivalent of the gate: flow 5 runs the two changed test files directly (110 tests), which the implementation round ran as its narrow selection. Flows 7 and 8 are the gate itself and the mutation evidence.

### Known limitations

- The Priming bullet's wording has no pin. Prose is not what a gate pins (plan section 1); a later edit of the paragraph can undo it silently, and that is accepted.
- The `complete=True` subcase is checked by its fields, not by a second golden (the one-new-golden rule of the plan).
- No `src/` change: a defect in the product is out of scope for this item. A finding that needs one is recorded as a finding, not fixed here (plan section 6).
- Retention commands, Workflow releases, CI and the release pins are out of scope.
- The optional findings are dispositioned at acceptance, not here.

## Next action

Functional review: run the flows above and place any findings at `.ai-review/priming-wording-and-alert-pins/feedback/FUNCTIONAL_REVIEW.md`. Once testing is clean, `/accept-milestone` is the only acceptance command; both checkpoints (CP1, CP2) are `COMPLETE`. If testing finds a same-scope problem, `/apply-functional-review` takes its bounded branch; a new or wider problem goes to its broad branch.
