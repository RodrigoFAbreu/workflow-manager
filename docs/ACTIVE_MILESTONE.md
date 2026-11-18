# Active Milestone

## Milestone

`verify-command-note-pin` (`governing_workflow_version: "2.2"`, `process`, plan revision 3, implementation revision 1, base `a936581`, branch `milestone/verify-command-note-pin`). It has no roadmap row.

Pull request title: `test: pin the verify command in the not-verified note` (issue #245). One assertion in `test_a_valid_record_keeps_the_verify_command_in_the_note` (`tests/test_compatibility.py`) pins the rendered, backticked `workflow-manager verify <repo>` command in the `not-verified` note, so the test asserts what its name claims. A `test:` change: it releases nothing (`valid title: test, release impact none`). Nothing under `src/`, `tools/` or any managed file changes.

### Verification state

- Full gate at implementation head `0f68fd5`: `python3 tests/run_all.py`, `verdict: exit 0`, 2451/2451 units, 16536 tests.
- Narrow selection `python3 tests/run_all.py --select test_compatibility.py`: the unmutated tree exits 0 (133 tests). Mutation M1 (the verify command dropped from the note) and M2 (the bare `workflow-manager verify` in place of the rendered command) each exit 1, and `test_a_valid_record_keeps_the_verify_command_in_the_note` is among the failures.
- Since `0f68fd5` only `docs/ai-workflow/WORKFLOW_STATE.json` has changed (`ce3e0b2`, `d532253`). `src/`, `tools/` and `tests/` are unchanged, so no rerun is needed.

### Review and approval

- Plan approval: `CURRENT`, `POLICY_SATISFIED`, at plan revision 3, bound to `APPROVE` verdicts from `anthropic/claude-opus-5-5` (local) and `openai/gpt-6.1-sol` (manual) for that bundle.
- Technical approval: `CURRENT`, `POLICY_SATISFIED`, reviewed content commit `0f68fd5`: local implementation review `APPROVE` (`anthropic/claude-opus-5-5`), manual external implementation review `APPROVE` (`openai/gpt-6.1-sol`).
- Optional findings from plan review (`LPR1-001`, `LPR1-002`, `O1`, `LPR3-001`) are recorded in the state's `optional_findings`. They are dispositioned at acceptance, not here.

## Functional review checklist

### Setup

- Flows 1, 1b, 2, 3 and 5 are git and grep only, and run offline in the sandbox. They need no `gh`, `claude`, `codex` or `ssh`.
- Flows 4 and 4b need the full environment. They run `tests/run_all.py`, which primes the release cache before it runs offline. On a machine with no primed cache, priming needs the network or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror. A `PrimingError` (exit 2) means the flow did not run. It is not a failure.
- Scratch space: `S=$(mktemp -d "$HOME/.cache/vc-fr.XXXXXX")`, then `git clone --no-hardlinks <product clone> "$S/cand"`. The clone checks out the branch head, which includes this checklist commit. Run each flow from `cd "$S/cand"`. Flows only read the product clone and write under `$S`. Nothing is written inside the product clone.
- Baseline for every diff: `a9365817f792972e9a6f932e30d694fea8df6a96` (tip of `main`, Workflow 2.29.9 installed).

### Test data

None to seed. The new assertion uses the temporary directory that the test itself creates. The mutation copies for flows 4 and 4b are fresh clones, `$S/m1` and `$S/m2`, made outside `$S/cand`.

### Flows

**Flow 1. Only the test file changed in the implementation scope.** Run `cd "$S/cand" && git diff --stat a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- src tools tests .github .claude scripts .workflow-manager`.
Expected: exactly `tests/test_compatibility.py` changed, with a few insertions and no deletions. Nothing under `src/`, `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/`.

**Flow 1b. Only the declared bookkeeping changed under `docs/`.** Run `cd "$S/cand" && git diff --name-status a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- docs`.
Expected: only these paths:
- `docs/ai-workflow/WORKFLOW_MANAGER_VERIFY_COMMAND_NOTE_PIN_PLAN.md`, `docs/ai-workflow/registry/verify-command-note-pin-registry.json`, `docs/ai-workflow/registry/verify-command-note-pin-artifacts.json` and `docs/ai-workflow/requirements/verify-command-note-pin-mapping.json`, all added;
- `docs/ai-workflow/WORKFLOW_STATE.json`, modified;
- `docs/ACTIVE_MILESTONE.md`, modified. Confirm with `git log --format=%s a9365817f792972e9a6f932e30d694fea8df6a96..HEAD -- docs/ACTIVE_MILESTONE.md`: the only commits are checklist-evidence commits.

No other path under `docs/`, and in particular not `docs/ROADMAP.md`.

**Flow 2. The new assertion pins the rendered command.** Run `cd "$S/cand" && git diff -U3 a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- tests/test_compatibility.py`.
Expected: the added lines hold one `assertIn` whose first argument is a backticked `workflow-manager verify`, then the target path, then `makes that comparison`. Its second argument is `found.detail`. The two existing `assertIn` lines of that test appear as unchanged context.

**Flow 3. Product code is untouched.** Run `cd "$S/cand" && git diff --exit-code a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- src tools README.md docs/ARCHITECTURE.md tests/portability_exceptions.json tests/parallel/resources.json`.
Expected: exit 0.

**Flow 4. The selection passes, and M1 breaks the named test (full environment).**
1. In `$S/cand`: `python3 tests/run_all.py --select test_compatibility.py`. Expected: `verdict: exit 0`.
2. `git clone --no-hardlinks <product clone> "$S/m1" && cd "$S/m1"`, then `sed -i 's|detail += f" `{verify}` makes that comparison|detail += f" makes that comparison|' src/workflow_manager/compatibility.py`.
3. Check the mutation with `grep -n 'makes that comparison, or prints' src/workflow_manager/compatibility.py`. Line 1973 must no longer hold `{verify}`.
4. `python3 tests/run_all.py --select test_compatibility.py`. Expected: `verdict: exit 1`, and `test_a_valid_record_keeps_the_verify_command_in_the_note` is among the failures, in subTests `1.2.3`, `2.12.0` and `0.0.0`.

**Flow 4b. M2 breaks the same test (full environment).** Use a fresh clone `"$S/m2"`, then `sed -i 's|`{verify}` makes that comparison|`workflow-manager verify` makes that comparison|' src/workflow_manager/compatibility.py`. Check with the same `grep -n`: line 1973 must hold the bare `workflow-manager verify`, not `{verify}`. Then run the selection. Expected: `verdict: exit 1`, with the same test failing in the same subTests, and no other test failing.

**Flow 5. The title is a release-free `test:` title.** Run `cd "$S/cand" && python3 tools/release/release.py check-title "test: pin the verify command in the not-verified note"`.
Expected: `valid title: test, release impact none`.

### Known limitations and out of scope

- Optional finding `LPR3-001` (recorded in the state, and in the plan's risks, section 6): the assertion embeds the raw `str(self.target)`, but the renderer quotes the path with `shlex.join`. A temporary directory whose path has spaces or other shell-unsafe characters would make flows 2, 4 and 4b fail for an environment reason, not a product defect. If that happens, record it as an environment note. Do not fix it in this item.
- This item changes no product behavior. It adds one assertion, and no release follows from it.
- The implementation-round mutation evidence (M1 and M2) is recorded in `.ai-review/verify-command-note-pin/current/TEST_RESULTS.md`. Flows 4 and 4b repeat it on demand.

## Next action

Functional review gate, `verify-command-note-pin`: the user runs flows 1 to 5 (flows 4 and 4b need the full environment). Testing findings go in `.ai-review/verify-command-note-pin/feedback/FUNCTIONAL_REVIEW.md`, and `/apply-functional-review` routes them. When testing is clean, `/accept-milestone` is the only acceptance command.
