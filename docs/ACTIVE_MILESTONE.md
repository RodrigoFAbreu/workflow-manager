# Active Milestone

## Milestone

**In progress.** `unattended-retention-prune` (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `7e0ab69`, branch `milestone/unattended-retention-prune`): step A3 of issue #254. `workflow-manager retention-cleanup TARGET --unattended`, after its archive-and-remove phase, also prunes the archives the adopted unattended policy has aged out (`unattended.prune` true): class `finished` only, strictly older than `unattended.ttl_days`, only items whose review folder is already gone, never an id under an interrupted removal, at most `unattended.prune_max_per_run`, oldest first, and only after the engine's own dry run lists exactly the planned set.

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_RETENTION_PRUNE_PLAN.md`.

Pull request title: `feat: prune old archives in the unattended retention run under the adopted unattended policy`.

### Checkpoints

- CP1 -- the prune selection, its plan digest and its two argv forms: **complete**. New pure module `retention_prune.py`: `select(report, unattended, policy_digest=)` returns a `PrunePlan` (ids oldest first by `(modified, id)`, cut at `prune_max_per_run`, `skipped` with `review-folder-present`, `removal-interrupted`, `unacceptable-id` or `age-not-known`, `capped`), reading `archives[]` defensively and selecting by `age_days > ttl_days` itself, never by the report's `prunable` flag; a missing `finished[]` entry fails closed as folder present; `prune_digest` is the sha256 of repository, policy digest, ttl and the ids in order; `argv_for` builds the dry-run form and the one-id apply form, each with `--ttl-days` and `--repo-root`, never `--archive-root`. Nothing calls it yet. Tests: `tests/test_retention_unattended_prune.py`.
- CP2 -- the prune phase: policy re-read, dry-run equivalence, per-id apply, audit lines: **complete**. `retention_prune.run_phase` re-reads the policy before the fresh report, the dry run and every apply (`retention_run.policy_holds`, extracted from `run`, with an `extra` predicate that `unattended.prune` is still true), selects, writes the `prune`/`started` line before any prune call, requires the engine's dry run to list exactly the planned ids (set comparison, `kind`, `mode`, `ttl_days`, empty `removed`), then applies one id per call and checks `result.removed` is exactly that id; the first failure stops it with one audit line (`prune` `failed`/`refused`/`interrupted`, or `policy` `stopped`/`interrupted`). `retention_run.run` gains a `closing` clause parameter (default: today's line); `retention_unattended.STEPS` gains `prune`. Nothing calls the phase yet.
- CP3 -- the unattended command runs the phase; the JSON document, text and exit codes: not started.
- CP4 -- the status text, the docs and the ROADMAP row: not started.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended_prune.py`, 28 tests, `verdict: exit 0`. Mutations M1 to M9, M26, M27 and M28 of plan section 3 (on a scratch copy outside the repository, the module preloaded in place of the real one) each fail the named tests; the unmutated control passes. M8 (the report's `prunable` flag instead of `age_days`) fails the ttl test too.
- CP2: `python3 tests/run_all.py --select test_retention_unattended_prune.py` (61 tests, `verdict: exit 0`), and `--select` of `test_retention_run.py`, `test_retention_unattended_run.py`, `test_retention_unattended.py`, `test_retention_cleanup.py` and `test_retention_policy.py`, each `verdict: exit 0`. Mutations M10, M11, M12, M14, M15 and M16 (scratch copy, module preloaded) each fail the named tests.

## Next action

CP3, on the next `/milestone-implement unattended-retention-prune`.
