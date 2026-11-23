# Active Milestone

## Milestone

**Awaiting functional review.** `retention-followup-pins` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `d2be4f8`, branch `milestone/retention-followup-pins`): tests and two docs sentences brought into line with the code (#257, #270, #264 points 1 and 2). Tests and docs only: no `src/` change, no release.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_RETENTION_FOLLOWUP_PINS_PLAN.md`.

Pull request title: `test: pin the retention follow-ups and say in the docs what the code prints`.

### Checkpoints

- CP1 -- the tests: a quoted verify command and the adopting helper's empty states: **complete**. The `not-verified` note is compared with `shlex.join`, a spaced target is pinned, and the adopting helper test covers a missing and an invalid policy file. Both mutations (`" ".join`, a guard that lets an empty policy through) fail the new tests.
- CP2 -- the docs say what the code prints, and their pins: **complete**. `docs/retention.md` says archives beyond the cap are left for a later run and what a prune stop prints; `docs/exit-codes.md` names both stop lines; `TestPage` and the zero-deleted stop test pin them. The four docs/code mutations fail the new tests; the full gate passed (16780 tests).

### Functional review checklist

Implementation revision 1, reviewed implementation head `bca9633`. The plan's section 5 is the source: the flows below are offline greps and diffs. Everything here is read-only: no flow writes inside the clone.

**Setup.** Check out `milestone/retention-followup-pins` at the checklist evidence commit. The base commit `d2be4f8aeb374c7ebe5a610d09a5e98edd5ce971` must be present (`git cat-file -e d2be4f8^{commit}`). Tools: `git`, `grep`, `diff`, `sed`, `python3`. No network, no `gh`, no `claude`, `codex` or `ssh` is needed.

**Test data.** None. Nothing is seeded: the flows read committed files and the base commit.

**Sandbox flows (1 to 8, run offline by the functional tester).**

1. **The changed files are exactly the five declared.** Run `git diff --name-only d2be4f8 HEAD -- ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'`. Expected: exactly `docs/exit-codes.md`, `docs/retention.md`, `tests/test_compatibility.py`, `tests/test_retention_unattended.py` and `tests/test_retention_unattended_prune.py`, and nothing else.
2. **No product code, roadmap or version changed.** Run `git diff --exit-code d2be4f8 HEAD -- src scripts .claude .workflow-manager docs/ROADMAP.md pyproject.toml`. Expected: exit 0 with no output.
3. **The page stamps are unchanged.** Run `diff <(git show d2be4f8:docs/retention.md | head -3) <(git show HEAD:docs/retention.md | head -3)`, then the same for `docs/exit-codes.md`. Expected: both exit 0 with no output. Both pages still say `Last checked with: Workflow Manager 1.18.1, Workflow 2.29.3`.
4. **The cap sentence (#264 point 1).** Run `grep -n 'Archives beyond the cap' docs/retention.md`. Expected: one line, 426, reading "Archives beyond the cap are not listed and are left for a later run." Run `grep -c 'counted as `capped`' docs/retention.md`. Expected: `0`. Run `grep -rn '\.capped' src/workflow_manager/`. Expected: no output, so no code reads the field that the old sentence described.
5. **The prune stop text (#264 point 2).** Run `grep -c '(after a stop, ' docs/retention.md`. Expected: `0`. Run `grep -c 'only when at least one archive was deleted, `retention prune: N of M archives were deleted before the stop; `' docs/retention.md`. Expected: `1`. The printed line exists in code: `grep -rln 'were deleted before the stop' src/workflow_manager/` names `retention_unattended.py`, and the deleted-count branch is `elif prune_result.done:` (line 437).
6. **The exit-code row names both stop lines (#264 point 2).** Run `grep -c 'closing line is what tells a stop apart' docs/exit-codes.md`. Expected: `0`. Run `grep -c 'the `stopped` line is what tells a stop apart' docs/exit-codes.md`. Expected: `1`. Run `grep -o 'retention cleanup: stopped after N of M items; ' docs/exit-codes.md` and `grep -o 'retention prune: stopped after N of M archives; ' docs/exit-codes.md`. Each expected: one match. The code prints both: `grep -rn 'retention cleanup: stopped after {' src/workflow_manager/` has 3 matches, and `grep -rn 'retention prune: stopped after {' src/workflow_manager/` has one, at `retention_prune.py:308`.
7. **The pins name the corrected text (#257, #270).** Run `grep -c 'verify {self.target}' tests/test_compatibility.py`. Expected: `0`. Run `grep -n 'shlex.join(\["workflow-manager", "verify"' tests/test_compatibility.py`. Expected: one match, at line 1320. Run `grep -n 'test_the_verify_command_in_the_note_quotes_a_target_with_a_space' tests/test_compatibility.py`. Expected: one match. Run `grep -n 'self.put("not json")' tests/test_retention_unattended.py`. Expected: one match in the adopting helper test. Run `grep -c 'left for a later run' tests/test_retention_unattended.py`. Expected: `2` (the page needle and the new docs pin).
8. **The diff reads as the plan specifies.** Run `git diff d2be4f8 HEAD -- docs/retention.md docs/exit-codes.md tests/` and read it against the plan's sections 2 and 3. Expected: every added or removed line is one of the decided wording changes or test pins, and no other line changes.

**Host flows (9 and 10, run by the operator on the host, not the sandbox).** They need the release cache, which a first run fills from the network, and they write their run directory.

9. Run `python3 tests/run_all.py --select test_compatibility.py`, then the same with `--select test_retention_unattended.py`, `--select test_retention_unattended_prune.py`, `--select test_docs.py` and `--select test_operator_ux_docs.py`. Expected: each exits 0. These are the plan's section 4 checks, not the gate. The gate evidence is the full run recorded at CP2 (16780 tests).
10. Optional: repeat one failure-only mutation from the plan's section 3 on a scratch copy outside the clone, for example reverting `docs/exit-codes.md` to "closing `retention cleanup: stopped` line says what was done". Expected: `TestPage` fails. The reviewer did not repeat the recorded mutations.

**Known limitations and out of scope.**

- #264 point 3, the `KeyboardInterrupt` handling in the prune apply, is a `src/` change and is not taken here. #264 stays open for it.
- Three plan-review optional findings are recorded with no disposition: LPR1-001 (the "ends with" wording in the plan's section 2), LPR1-002 (building the spaced target directly rather than copying the fixture) and the §1.1 coverage wording. Each gets a recorded disposition at acceptance.
- The pages' header stamps are kept on purpose (Workflow Manager 1.18.1, Workflow 2.29.3). This item changes wording and does not re-check a page against a release.
- No release, no ROADMAP row and no `src/` change.

**What to do with the results.** If testing is clean, `/accept-milestone` is the only acceptance command, and both checkpoints are already `COMPLETE`. If a flow finds a problem, place the findings at `.ai-review/retention-followup-pins/feedback/FUNCTIONAL_REVIEW.md` and run `/apply-functional-review`.
