# Active Milestone

## Milestone

**In progress.** `unattended-adopt-wording` (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `87c9460`, branch `milestone/unattended-adopt-wording`): the three points of issue #259, one mechanism: what the adopt output and the documentation say about adopting again, and the tests that pin it.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_ADOPT_WORDING_PLAN.md`.

Pull request title: `fix: tell the adopt preview to adopt again with the unattended sentence instead of running itself`.

### Checkpoints

- CP1 -- the adopt preview says to adopt again, and the mixed-confirmation refusal is pinned in full: **complete**. `retention_policy.unattended_lines(state, target, *, adopting=False)`: with `adopting` true, the head for a record adopted with the ordinary sentence only ends "adopt again with the unattended sentence printed below" instead of "run workflow-manager adopt-retention-policy TARGET"; `cmd_adopt_retention_policy` passes `adopting=True`; `status`, `doctor` and the cleanup preview keep the shared text. `test_a_mixed_confirmation_is_refused` pins the full stderr (cause and `next:` line) for both policies. New tests: the helper per state with `adopting=True`, the adopt preview through the command.
- CP2 -- the docs say the owner adopts again, and the ROADMAP row: **complete**. `docs/retention.md`: the three sentences now say "the owner adopts the policy again" (lines 111, 149, 158); the adopt-preview/cleanup-preview sentence is qualified for the adopt preview of a file adopted with the ordinary sentence only. `TestPage.test_the_page_says_the_owner_adopts_again` pins them. ROADMAP row 53 marked Done.

### Self-review

- The full diff against `87c9460` (`cli.py`, `retention_policy.py`, `tests/test_retention_unattended.py`, `docs/retention.md`, `docs/ROADMAP.md`): no correctness, layer or test gap in the code and test changes. One defect fixed: CP2 recorded row 53 as marked Done, but the row still read `Current`. It now reads "Done (accepted by policy; a `fix:` change, Manager patch release)", as the plan's CP2 says, and its point (3) also names the qualified preview sentence (optional plan finding LPR2-001).

### Verification state

- CP2: `python3 tests/run_all.py --select test_retention_unattended.py --select test_docs.py --select test_operator_ux_docs.py` (`verdict: exit 0`). Mutations (scratch copy outside the repository): both page reverts fail the page test; the unmutated control passes.
- CP1: `python3 tests/run_all.py --select test_retention_unattended.py` (59 tests), and `--select` of `test_retention_policy.py`, `test_retention_cleanup.py`, `test_retention_status.py`, `test_retention_alert.py` and `test_docs.py`, each `verdict: exit 0`. Mutations (scratch copy outside the repository): the CLI caller no longer passing `adopting`, and the helper ignoring it, fail the adopt-preview test (the latter also the helper test); rewording the `next:` clause, and rewording the cause while keeping "mixes", each fail the strengthened mixed-confirmation test. The unmutated control passes.

### Functional review checklist

Gate: `AWAITING_FUNCTIONAL_REVIEW`, implementation revision 1, CP1 and CP2 complete. The full gate ran at `3292b54` with `verdict: exit 0`; the only change since is `docs/ai-workflow/WORKFLOW_STATE.json`, which does not count as a change, so the automated state is current.

**Setup.** This repository at the evidence commit on `milestone/unattended-adopt-wording`, with Python 3 and the repository's test runner. Run the selection in flow 2 in a scratch copy under a new empty directory (`git clone` of the repository), never in the product clone: the tests hash the checkout. No network is needed once the frozen release cache is primed on this machine; the first run on a machine needs the network or `WORKFLOW_MANAGER_RELEASE_SOURCE`.

**Test data.** None. The tests build their own scratch managed repositories. No owner repository, policy file, record, archive or retention store is touched.

**Flows.** All five run in the sandbox: offline greps, diffs and one test selection. None needs GitHub, `gh`, `claude`, `codex`, `ssh`, a namespace or a host socket. Run them in order.

1. **Scope.** `git diff --name-only 87c9460 HEAD` prints exactly these eleven paths: `docs/ACTIVE_MILESTONE.md`, `docs/ROADMAP.md`, `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_ADOPT_WORDING_PLAN.md`, `docs/ai-workflow/WORKFLOW_STATE.json`, `docs/ai-workflow/registry/unattended-adopt-wording-artifacts.json`, `docs/ai-workflow/registry/unattended-adopt-wording-registry.json`, `docs/ai-workflow/requirements/unattended-adopt-wording-mapping.json`, `docs/retention.md`, `src/workflow_manager/cli.py`, `src/workflow_manager/retention_policy.py` and `tests/test_retention_unattended.py`. `git diff --name-only 87c9460 HEAD -- .claude scripts .workflow-manager pyproject.toml` prints nothing.
   Expected: the eleven paths and the empty output.

2. **Pins.** In the scratch copy at the evidence commit: `python3 tests/run_all.py --select test_retention_unattended.py --select test_docs.py --select test_operator_ux_docs.py`.
   Expected: `verdict: exit 0`. These pins cover the adopt preview of a file adopted with the ordinary sentence only (the new head once, the unattended sentence on a later line), the helper with `adopting=True`, the exact stderr of the mixed-confirmation refusal (cause and `next:` line), the page sentences, and the unchanged `status`, `doctor` and cleanup-preview text. If the run exits 2 with `PrimingError`, the release cache is not primed in this sandbox: that is `reason` `environment`, not a finding.

3. **Who passes the adopting head.** `grep -rn "unattended_lines(" src/` prints five lines: the definition (`src/workflow_manager/retention_policy.py:259`), the two calls in `block` (`retention_policy.py:650` and `:657`), the cleanup preview (`src/workflow_manager/cli.py:1058`) and the adopt preview (`cli.py:1000`). `grep -rn "adopting=True" src/` prints one line, `cli.py:1000`.
   Expected: only the adopt preview passes `adopting=True`; `status`, `doctor` and the cleanup preview keep the shared head.

4. **The diff is the wording only.** `git diff -U0 87c9460 HEAD -- src/` changes one line in `cli.py` (the adopt preview call gains `adopting=True`) and, in `retention_policy.py`, only the signature, its docstring and the head of the adopted-without-authorisation branch.
   Expected: no other line of `src/` changed. The code paths for every other state are byte-identical to the base.

5. **Docs and ROADMAP wording.** `git diff --stat 87c9460 HEAD -- docs/retention.md` reports `4 insertions(+), 4 deletions(-)`. Then `grep -c "so the owner adopts the policy again" docs/retention.md` prints `2`; `grep -n "and the owner adopts the policy again; a hand-written record" docs/retention.md` prints one match on line 158; `grep -n "print the same lines, except that the adopt preview" docs/retention.md` prints one match on line 162; `grep -n "and the policy is adopted again\|so the policy is adopted again\|print the same lines; a file without the key" docs/retention.md` prints nothing. Finally `grep -n "^| 53 " docs/ROADMAP.md` shows the row's status as `Done (accepted by policy; a `fix:` change, Manager patch release)`.
   Expected: each count and line as stated.

**Expected result.** Flows 1 to 5 pass when each expected output above matches. A mismatch in flow 2 is a finding; a `PrimingError` is an environment failure.

**Known limitations and out of scope.**
- The change is one message and one keyword parameter. No policy enforcement, archive, remove or prune behaviour changes, and nothing in this item runs `retention-cleanup --unattended` or any archive command.
- Not exercised here: a real GitHub call, the owner's adoption of any policy (the owner's act), the Manager patch release (after acceptance, as the title says) and the Controller's acceptance.
- The mutation checks of plan section 3 ran at `3292b54` and are recorded in `.ai-review/unattended-adopt-wording/current/TEST_RESULTS.md`. They are not repeated in this checklist.
- Optional findings `F-c939785685a6` (plan line references in section 1), `F-f5884c700870` (row 53 point 3), `F-9bcaf4ea730c` (CP1 mutation list) and `F-a04152085a98` (helper `[]` case) are recorded in the state. Each gets a disposition at acceptance; none changes behaviour.
