# Active Milestone

## Milestone

**Awaiting functional review.** `exit-codes-interrupt-row` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, implementation revision 1, base `a19f6a2`, branch `milestone/exit-codes-interrupt-row`): row 2 of the `retention-cleanup` table in `docs/exit-codes.md` says that an unattended prune interrupted before its first `prune --apply` exits 2, and one interrupted after a `prune --apply` was attempted exits 1. A test pins the clause. A follow-up of #276 (the Optional finding LPR1-003 of the previous item's plan review). Docs and one test pin only: no `src/` change and no release.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_EXIT_CODES_INTERRUPT_ROW_PLAN.md`.

Pull request title: `docs: say in the exit codes that an unattended prune interrupt before its first call exits 2`.

### Checkpoints

- CP1 -- the interrupt clause in row 2 and its pin: **complete** (`de862da`). Only `docs/exit-codes.md` (line 34, row 2) and `tests/test_retention_unattended.py` (`TestPage.test_the_exit_codes_row_names_an_interrupt_before_the_first_prune_apply`) changed.

### Verification state at `4be2b8e`

- Targeted selection `python3 tests/run_all.py --select test_retention_unattended.py`: exit 0, 63 tests.
- Full gate `python3 tests/run_all.py`: exit 0, 2491 of 2491 units, 16800 tests, `tree_digest` `677b68cd9772f0a2452e694b2ab510e244351456bcfc3f8d7b304ab1d786578f`.
- The pin fails against the base page (scratch copy, 4 failures) and passes on the candidate.

## Functional review checklist

**Scope.** Only one sentence of one row of one page changes, and it is pinned by a text test. No code path changes, so no flow below runs a retention command against a repository, and none of them needs `gh`, `claude`, `codex` or `ssh`.

**Setup.** A clone at the evidence commit of this checklist (the commit that adds this section), with a clean working tree. Python 3 with the standard library. Run every command from the repository root with `PYTHONDONTWRITEBYTECODE=1` so nothing is written into the clone. Flows 1 to 6 need no network and no release cache. Flow 7 is the full gate and is host-only.

**Test data.** None. No `retention-cleanup`, `--unattended`, `archive`, `remove` or `prune` command is run against any repository in this checklist.

**Sentence under review.** Row 2 of the `retention-cleanup` table in `docs/exit-codes.md` (line 34), as it must read:

> An unattended prune that stops before any per-item call or `prune --apply` was attempted exits 2 too: its refusal, a dry run that does not match the plan, or an interrupt that lands before the first `prune --apply` (while the policy or the fresh report is read, while its `started` audit line is written, or during the engine's dry run); an interrupt after a `prune --apply` was attempted exits 1.

**Flows.**

1. **Scope of the change.** Run `git diff --name-only a19f6a215fda91ba55b2dc5e785b509d05079cb3 HEAD`. Expected: only `docs/ai-workflow/WORKFLOW_MANAGER_EXIT_CODES_INTERRUPT_ROW_PLAN.md`, `docs/ai-workflow/WORKFLOW_STATE.json`, `docs/ai-workflow/registry/exit-codes-interrupt-row-artifacts.json`, `docs/ai-workflow/registry/exit-codes-interrupt-row-registry.json`, `docs/ai-workflow/requirements/exit-codes-interrupt-row-mapping.json`, `docs/exit-codes.md`, `tests/test_retention_unattended.py`, and this file (`docs/ACTIVE_MILESTONE.md`, from the evidence commit). Then run `git diff --exit-code a19f6a215fda91ba55b2dc5e785b509d05079cb3 HEAD -- src tools scripts .claude .workflow-manager docs/retention.md docs/ROADMAP.md`; expected: exit 0 and no output.

2. **The row reads as specified.** Run `git diff -U0 a19f6a215fda91ba55b2dc5e785b509d05079cb3 HEAD -- docs/exit-codes.md`. Expected: exactly one removed line and one added line, both on row 2 of the `retention-cleanup` table (line 34). The added line contains the sentence above, word for word, and the other sentences of row 2 (the refusals, the `--unattended` clauses and the `next:` line) are unchanged. The phrase `before any call of the run was attempted` no longer appears: `grep -c "before any call of the run was attempted" docs/exit-codes.md` prints `0`.

3. **Only the row changed, and the stamp did not.** `grep -n "Last checked with" docs/exit-codes.md` prints line 3 with `Workflow Manager 1.18.1, Workflow 2.29.3`, unchanged from the base. `git diff --stat a19f6a215fda91ba55b2dc5e785b509d05079cb3 HEAD -- docs/exit-codes.md` shows one line removed and one added; the page's other rows and the table header are unchanged.

4. **The sentence matches the code (reading only).** Run `grep -n "apply_attempted" src/workflow_manager/retention_prune.py` and `grep -n "exit_code = 1 if ran else 2" src/workflow_manager/retention_unattended.py`. Expected: `retention_prune.py` sets `result.apply_attempted = True` at about line 397, just before the first `--apply` call, and `retention_unattended.py` sets `exit_code = 1 if ran else 2` at about line 446. Read `run_phase` in `retention_prune.py` and confirm: an interrupt while the policy or the fresh report is read, while the `started` line is written, or during the engine's dry run stops with `apply_attempted` still false, so a run whose cleanup made no call exits 2; an interrupt during an apply call, while an `ok` line is written, or while the policy is read before a later item stops after `apply_attempted` is true, so it exits 1. If the code disagrees with the sentence, record a finding and do not accept the row (this is the plan's stop rule).

5. **The new pin passes on the candidate.** From the repository root run `cd tests && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../src python3 -m unittest test_retention_unattended.TestPage`. Expected: `Ran 11 tests`, `OK`. No runner, no network and no release cache are needed.

6. **The pin fails against the base page and the planned mutations.** Create a scratch directory outside the clone, `git archive HEAD` into it, and work only in that copy. Each case must fail the single test `test_retention_unattended.TestPage.test_the_exit_codes_row_names_an_interrupt_before_the_first_prune_apply` with `PYTHONPATH=<scratch>/src`, and the unmutated control must pass.
   - (a) Put the base page into the copy: `git show a19f6a215fda91ba55b2dc5e785b509d05079cb3:docs/exit-codes.md > <scratch>/docs/exit-codes.md`. Expected: `FAILED (failures=4)`.
   - (b) In the copy, drop the parenthesis from the interrupt clause (the words `(while the policy` and the text after them, up to `dry run)`). Expected: failure.
   - (c) In the copy, change the after-apply half's `exits 1` to `exits 2`. Expected: failure.
   - Control: the unmutated copy passes. Delete the scratch directory afterwards.

7. **Full gate (host only).** From the repository root run `python3 tests/run_all.py` once, without a time limit short of about 20 minutes (the run is about 15 minutes at 8 workers). Expected: `verdict: exit 0` with 2491 of 2491 units. It needs the release cache primed (network, or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror). If the sandbox cannot prime the cache, the run exits 2 with `PrimingError`: that is `failed` with reason `environment`, not a product failure. A killed run leaves `src/` and `tools/` read-only; restore them with `python3 tests/run_all.py --restore-barrier`.

**Known limitations and out of scope.**

- The clause is pinned by a text test and verified by reading the code. No flow fires a real interrupt against a repository.
- Row 1, `docs/retention.md` (line 438) and the refusal wording of row 2 are unchanged and out of scope. The `docs/exit-codes.md` stamp is unchanged by design (one row was re-checked, not the page).
- A non-interrupt stop (a changed policy, an unreadable report, an unwritable `started` line) exits 2 by the same rule, but the clause names only the interrupt cases; this is deliberate (the issue's scope).
- No release: the change is `docs:`/`test:` and releases nothing.

**Where findings go.** `.ai-review/exit-codes-interrupt-row/feedback/FUNCTIONAL_REVIEW.md`. Run `/apply-functional-review` on it when it exists.

**Evidence.** The commit that adds this section records the checklist identity (`Workflow-Functional-Checklist` trailer). Report its SHA and blob to the user.

## Next action

Manual functional testing of flows 1 to 7 above. Place findings at `.ai-review/exit-codes-interrupt-row/feedback/FUNCTIONAL_REVIEW.md`. Once testing is clean, `/accept-milestone` is the only acceptance command, and it requires every checkpoint in this item's registry to be `COMPLETE` (CP1 is).
