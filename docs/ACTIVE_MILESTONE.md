# Active Milestone

## Milestone

**Awaiting functional review.** `unattended-prune-interrupt` (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `a9dda89`, branch `milestone/unattended-prune-interrupt`): an interrupt that lands while the unattended prune writes its `started` or `ok` audit line stops the phase with `interrupted` instead of escaping (#264 point 3). A Manager patch release (`fix:`).

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_PRUNE_INTERRUPT_PLAN.md`.

Pull request title: `fix: stop the unattended prune cleanly on an interrupt during its audit writes`.

### Checkpoints

- CP1 -- the two interrupt handlers and their tests: **complete**. `run_phase` handles `KeyboardInterrupt` on the `started` write and on the `ok` write; two tests in `TestAuditFailures` pin the stop, the audit line and the text. The three code mutations (either clause deleted, "the apply had succeeded" dropped) fail them.
- CP2 -- the Audit lines clause and its pin: **complete**. `docs/retention.md`'s Audit lines paragraph says an `interrupted` line is also written when the run is interrupted while the `started` line or an archive's `ok` line is written (the archive is already deleted for the latter); a `TestPage` pin holds both halves and fails against the base wording.

### Self-review

Self-review of the milestone diff: one gap fixed. The two interrupt tests now also pin the `interrupted` audit line's own text (plain `interrupted` for the `started` write; for the `ok` write the full text of the stop, so the line says the archive is deleted). A mutation that writes the plain `interrupted` text on the `ok` line now fails the `ok` test.

## Functional review checklist

Implementation revision 1. The product code is at `cddfe97`; the commits after it (`a841d9f`, `9ff94bf`) change only `docs/ai-workflow/WORKFLOW_STATE.json`, so the full-gate evidence at `cddfe97` still stands. Base `a9dda89`.

### Setup

- Checkout of `milestone/unattended-prune-interrupt` at the checklist evidence commit, working tree clean. Python 3 standard library only.
- Flows 1 to 6 need no network, no `gh`, no forge, no `claude`, `codex` or `ssh`, and no PID namespace. Flow 6 works in a scratch copy outside the clone.
- The full gate `python3 tests/run_all.py` is not repeated here. It primes the release cache and needs the network (or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror), so it is a host run; its evidence is recorded in `.ai-review/unattended-prune-interrupt/current/TEST_RESULTS.md`.

### Test data

None. The tests build report dicts and scratch repositories in memory and in temporary directories. Do not run `retention-cleanup --unattended`, or any archive, remove or prune command, against a real repository or the real archive store.

### Flows

Run them in order. Each expected result is what the command must print or show.

1. **Scope.** `git diff --name-status a9dda8980619aafcdee5d3fbff6f7fd07a74552b HEAD` lists exactly these ten paths: `M docs/ACTIVE_MILESTONE.md`, `A docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_PRUNE_INTERRUPT_PLAN.md`, `M docs/ai-workflow/WORKFLOW_STATE.json`, `A docs/ai-workflow/registry/unattended-prune-interrupt-artifacts.json`, `A docs/ai-workflow/registry/unattended-prune-interrupt-registry.json`, `A docs/ai-workflow/requirements/unattended-prune-interrupt-mapping.json`, `M docs/retention.md`, `M src/workflow_manager/retention_prune.py`, `M tests/test_retention_unattended.py`, `M tests/test_retention_unattended_prune.py`. Then `git diff --name-only a9dda8980619aafcdee5d3fbff6f7fd07a74552b HEAD -- .claude scripts .workflow-manager docs/ROADMAP.md docs/exit-codes.md` prints nothing.

2. **The two interrupt handlers.** `git diff a9dda8980619aafcdee5d3fbff6f7fd07a74552b HEAD -- src/workflow_manager/retention_prune.py` shows 8 added lines and no removed line, with two `except KeyboardInterrupt:` clauses:
   - **`started` write:** after `note("prune", None, "started", first=True)`, before `except Exception as failed`. It writes `note("prune", None, "interrupted", None, interrupted_line)` and returns `stop("prune", None, interrupted_line)`. The plain text `interrupted` is the stop text.
   - **`ok` write:** around `observer("prune", item_id, "ok", None, None, digest)`, before `except Exception as audit`. Its text is `interrupted; the apply had succeeded (the archive is deleted); no further call was made`. It writes `note("prune", item_id, "interrupted", None, text)` and returns `stop("prune", item_id, f"{item_id}: {text}")`.
   - `entry["result"] = "done"` stays before the `ok` write, so an interrupted archive still counts as deleted.

3. **Docs.** `git diff a9dda8980619aafcdee5d3fbff6f7fd07a74552b HEAD -- docs/retention.md` changes one line: the Audit lines paragraph (about line 432). The new sentences read "An `interrupted` line is also written when the run is interrupted while the `started` line or an archive's `ok` line is being written; for the `ok` line the archive is already deleted, and the `interrupted` line says so and stands in for the lost `ok` line." No other paragraph changes. `docs/exit-codes.md` is unchanged (flow 1).

4. **Tests read as planned.** `git diff a9dda8980619aafcdee5d3fbff6f7fd07a74552b HEAD -- tests/` adds the two `TestAuditFailures` interrupt tests, the `TestPage` pin, and the self-review's pin of the `interrupted` line's text. Check that the `started` test asserts: outcome `stopped`, stop item `None`, the phase text `retention prune: stopped after 0 of 3 archives; interrupted`, no engine call, no `done` entry, last audit line `("prune", "interrupted", None)`, and an unchanged tree. Check that the `ok` test asserts: stop item `b-mid`, the text with "the apply had succeeded" and "the archive is deleted", results `done, done, not-attempted`, and the stop line `stopped after 2 of 3 archives`.

5. **Offline tests, unmutated.** From the clone's `tests/` directory, with `PYTHONDONTWRITEBYTECODE=1`, run each command and expect `OK`: `python3 -m unittest test_retention_unattended_prune` (`Ran 90 tests`), `python3 -m unittest test_retention_unattended` (`Ran 62 tests`), and `python3 -m unittest test_docs test_operator_ux_docs` (`Ran 49 tests`). Nothing is written into the clone.

6. **Mutation probes, in a scratch copy.** `git archive HEAD | tar -x -C <scratch dir>` (a directory under `$HOME/.cache`, not `/tmp`), apply one edit, run the module's `unittest` as in flow 5, and delete the scratch copy. Each mutation must fail as stated:
   - delete the `started` `except KeyboardInterrupt:` clause: the `KeyboardInterrupt` escapes `run_phase` and aborts the run with a traceback and no `OK` or `FAILED` summary. This is the expected failure, not a pass.
   - delete the `ok` `except KeyboardInterrupt:` clause: the same abort.
   - drop "the apply had succeeded" from the `ok` text: `FAIL: test_an_interrupt_while_an_ok_line_is_written_says_the_archive_is_deleted`, `FAILED (failures=1)`.
   - revert `docs/retention.md`'s Audit lines paragraph to the base wording: a `FAIL` in `test_retention_unattended`'s `TestPage` test that pins the new clause.
   - write the plain `interrupted` text on the `ok` audit line: the same `FAIL` as the third mutation.

### Known limitations and out of scope

- An interrupt during the `ok` write comes after the archive is deleted, so the run cannot undo the deletion. It says so and records it; the `ok` line itself is lost and the `interrupted` line stands in for it. The entry is `done`, and the stop line counts it.
- A second interrupt while the `interrupted` line is being written escapes `note`, which swallows only `Exception`. This is the same in every other handler of the phase and is out of scope.
- Points 1 and 2 of #264 are not in this item: they belong to `retention-followup-pins`. The cleanup loop (`src/workflow_manager/retention_run.py`) is untouched.
- Nothing here runs `retention-cleanup --unattended` against a real repository, the real archive store or the real engine; the tests drive `run_phase` with a fake observer and scratch fixtures.
- Plan line citations for the base commit drift by one or two lines (plan-review optional finding `LPR1-001`). No behaviour depends on them; it is dispositioned at acceptance.

## Next action

Manual functional review of this checklist (flows 1 to 6). Findings go to `.ai-review/unattended-prune-interrupt/feedback/FUNCTIONAL_REVIEW.md`. Once the review is clean, `/accept-milestone` is the acceptance command; both checkpoints (CP1, CP2) are complete. Findings are routed by `/apply-functional-review`.
