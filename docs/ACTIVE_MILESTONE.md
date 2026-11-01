# Active Milestone

## Milestone

`null-record-wording` -- complete (accepted by policy; `governing_workflow_version: "2.2"`, `process`, plan revision 3, base `4cbd162`, branch `milestone/null-record-wording`): roadmap row 22 (#108). A `test:` pull request title (releases nothing). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_NULL_RECORD_WORDING_PLAN.md`.

What the Manager says about an installation record whose `workflow_version` is null, and its next step: `verify` and `status` with an explicit release no longer print `None`; the `update`, `update --dry-run` and `doctor` `next:` line names one step (the explicit update that rewrites the record); under `--dry-run` that step says it is a real update; a `--release-dir` is left out of the step. Messages outside the null record and every exit code are unchanged.

### CP1: the wording, the docs and the tests -- complete

- `verify` (`install.py`) says the record has no `workflow_version`; `_not_a_version` (`advice.py`) returns the single step for a read, null record, built without `--release-dir`.
- `docs/update.md` names the step; new and changed cases in `tests/test_operator_ux.py` and `tests/test_docs.py`.

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 22 is Current and is Done at acceptance. No version is edited.

### Mutation results (scratch clone of `03f6117`, `python3 tests/run_all.py --select test_operator_ux.py --select test_docs.py --select test_discovery.py`)

The candidate passes: 43 of 43 units, 279 tests, exit 0. Each mutation exits 1 and fails the case the plan names (extra failures listed):

| Mutation | Failed |
| --- | --- |
| `verify` prints `installed None` again | the `verify`/`status` case |
| the null step is the old two-alternative text | the `update`/dry-run/`doctor` case, the null-manifest REL case |
| the dry-run clause is dropped | the `update`/dry-run/`doctor` case, the release-directory case |
| the clause is added to a bare update | the `update`/dry-run/`doctor` case, the release-directory case |
| the null step is applied to a non-null bad record too | the unchanged non-null case, plus two other damaged-record cases |
| `--release-dir` is carried onto the null step again | the null-manifest REL case |
| the clause asserts D holds no version | the genuine-directory D case |
| the `left out` clause is dropped | the release-directory case (REL and D are subtests of it) |
| an explicit `--release-version V update` is refused on a null record | the extended explicit-update case, the release-directory case, `test_t4_t5_unmanaged_targets_get_the_bootstrap_command` |

The scratch clone is outside the repository, which was never mutated. The full gate ran at `7240ca8` and again after the review fix at `00849e9` (revision 2: exit 0, same selection and tests digests as the local implementation review's run at `cf31245`).

## Functional review

Flows 1 to 6 from the checklist passed on the candidate (the Controller's automated tester, workflow-controller 1.26.0, run `controller:20261031T234218Z-0f6f5eae`). The milestone was accepted by policy; the six Optional findings are dispositioned in `docs/milestones/completed/null-record-wording-findings.md` (2 fixed, 2 dropped with reasons, 4 follow-ups on #145).

## Next action

Roadmap row 22 is Done (a `test:` change, no release). The pull request (#146) merges after the acceptance commit. Open follow-up: issue #145. Then `/milestone-plan` when one is chosen.
