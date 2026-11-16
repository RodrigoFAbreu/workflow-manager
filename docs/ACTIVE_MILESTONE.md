# Active Milestone

## Milestone

**Complete.** `priming-wording-and-alert-pins` (`governing_workflow_version: "2.2"`, `process`, plan revision 4, implementation revision 2, base `59beeea`, branch `milestone/priming-wording-and-alert-pins`): it has no roadmap row.

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

### Functional review and acceptance

- Functional evidence: flows 1 to 9 passed at the approved content (flows 1 to 4, 6 and 9 by the Controller's automated tester, flows 5, 7 and 8 by an independent headless executor run). The one optional plan-review finding (PWA-L1-003) is dispositioned `fixed` in `docs/ai-workflow/registry/priming-wording-and-alert-pins-dispositions.json`.
- Accepted by policy (not by a person) on 2026-11-16: `/satisfy-gate acceptance`, pull request #247 at `645aa6e`, checks green. A `test:` change, no release.

## Next action

No active work item. Run `/milestone-plan` for the next incomplete milestone in `docs/ROADMAP.md`.
