# Active Milestone

## Milestone

**In progress.** `unattended-adopt-wording` (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `87c9460`, branch `milestone/unattended-adopt-wording`): the three points of issue #259, one mechanism: what the adopt output and the documentation say about adopting again, and the tests that pin it.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_ADOPT_WORDING_PLAN.md`.

Pull request title: `fix: tell the adopt preview to adopt again with the unattended sentence instead of running itself`.

### Checkpoints

- CP1 -- the adopt preview says to adopt again, and the mixed-confirmation refusal is pinned in full: **complete**. `retention_policy.unattended_lines(state, target, *, adopting=False)`: with `adopting` true, the head for a record adopted with the ordinary sentence only ends "adopt again with the unattended sentence printed below" instead of "run workflow-manager adopt-retention-policy TARGET"; `cmd_adopt_retention_policy` passes `adopting=True`; `status`, `doctor` and the cleanup preview keep the shared text. `test_a_mixed_confirmation_is_refused` pins the full stderr (cause and `next:` line) for both policies. New tests: the helper per state with `adopting=True`, the adopt preview through the command.
- CP2 -- the docs say the owner adopts again, and the ROADMAP row: pending.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended.py` (59 tests), and `--select` of `test_retention_policy.py`, `test_retention_cleanup.py`, `test_retention_status.py`, `test_retention_alert.py` and `test_docs.py`, each `verdict: exit 0`. Mutations (scratch copy outside the repository): the CLI caller no longer passing `adopting`, and the helper ignoring it, fail the adopt-preview test (the latter also the helper test); rewording the `next:` clause, and rewording the cause while keeping "mixes", each fail the strengthened mixed-confirmation test. The unmutated control passes.
