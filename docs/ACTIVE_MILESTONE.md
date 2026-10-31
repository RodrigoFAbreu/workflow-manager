# Active Milestone

## Milestone

`null-record-wording` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `4cbd162`, branch `milestone/null-record-wording`): roadmap row 22 (#108). A `fix:` pull request title (Manager 1.14.2). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_NULL_RECORD_WORDING_PLAN.md`.

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

The scratch clone is outside the repository, which was never mutated. The full gate (`python3 tests/run_all.py`) runs at self-review.

## Next action

Step 2 of `/milestone-implement`: enter `SELF_REVIEWING_IMPLEMENTATION`, run the full gate, then the review bundle.
