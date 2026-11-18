# Active Milestone

## Milestone

**Complete.** `verify-command-note-pin` (`governing_workflow_version: "2.2"`, `process`, plan revision 3, implementation revision 1, base `a936581`, branch `milestone/verify-command-note-pin`): it has no roadmap row.

Pull request title: `test: pin the verify command in the not-verified note` (issue #245). One assertion in `test_a_valid_record_keeps_the_verify_command_in_the_note` (`tests/test_compatibility.py`) pins the rendered, backticked `workflow-manager verify <repo>` command in the `not-verified` note, so the test asserts what its name claims. A `test:` change: it releases nothing. Nothing under `src/`, `tools/` or any managed file changes.

### Verification state

- Full gate at implementation head `0f68fd5`: `python3 tests/run_all.py`, `verdict: exit 0`, 2451/2451 units, 16536 tests.
- Narrow selection `python3 tests/run_all.py --select test_compatibility.py`: the unmutated tree exits 0 (133 tests). Mutation M1 (the verify command dropped from the note) and M2 (the bare `workflow-manager verify` in place of the rendered command) each exit 1, and `test_a_valid_record_keeps_the_verify_command_in_the_note` is among the failures.
- Since `0f68fd5` only `docs/` bookkeeping has changed; `src/`, `tools/` and `tests/` are unchanged.

### Review and approval

- Plan approval: `CURRENT`, `POLICY_SATISFIED`, at plan revision 3, bound to `APPROVE` verdicts from `anthropic/claude-opus-5-5` (local) and `openai/gpt-6.1-sol` (manual).
- Technical approval: `CURRENT`, `POLICY_SATISFIED`, reviewed content commit `0f68fd5`: local implementation review `APPROVE` (`anthropic/claude-opus-5-5`), manual external implementation review `APPROVE` (`openai/gpt-6.1-sol`).

### Functional review and acceptance

- Functional evidence: flows 1 to 7 (checklist flows 1, 1b, 2, 3, 4, 4b and 5) passed at the approved content (flows 1 to 4 and 7 by the Controller's automated tester, flows 5 and 6 by an independent headless executor run).
- The four optional findings are dispositioned in `docs/ai-workflow/registry/verify-command-note-pin-dispositions.json` and `docs/milestones/completed/verify-command-note-pin-findings.md`: two `fixed`, two `follow-up` (issue #257: quote the target path in the expected command with `shlex.quote`).
- Accepted by policy (not by a person) on 2026-11-18: `/satisfy-gate acceptance`, pull request #256 at `1cfab5e`, checks green. A `test:` change, no release.

## Next action

No active work item. Run `/milestone-plan` for the next incomplete milestone in `docs/ROADMAP.md`.
