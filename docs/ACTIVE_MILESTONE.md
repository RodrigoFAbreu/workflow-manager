# Active Milestone

## Milestone

**In progress.** `unattended-retention-policy` (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `87d151c`, branch `milestone/unattended-retention-policy`): step A1 of issue #254, the `unattended` policy key and its own adoption sentence. Nothing runs unattended in this item.

Pull request title: `feat: add the unattended retention policy key and its own adoption sentence`.

### Checkpoints

- CP1 -- the unattended policy key and its validation: **complete**. `policy_errors` validates the closed `unattended` object (five required keys, floors and ceilings, the two cross rules); `describe_unattended` renders its settings; `tests/test_retention_unattended.py` and the vendored base module `tests/fixtures/retention_policy_base.py.txt` (blob `4b54c52`) pin the schema and the older-Manager fail-safe.
- CP2 -- the two adoption sentences, the record's kind and the adopt command: **complete**. `unattended_sentence` and its holder; `check_record` accepts either sentence for a file with the key and refuses the unattended one for a file without it; `PolicyState.unattended` is set only for an adopted record holding the unattended sentence; `apply` refuses wrong-kind and mixed confirmations before the digest check, writing nothing; `adopt-retention-policy` prints the unattended sentence for a file with the key (help text names both). Tests in `tests/test_retention_unattended.py` (`TestSentences`).
- CP3 -- the unattended text, the docs and the ROADMAP row: **complete**. `retention_policy.unattended_lines` (with `NOT_ENFORCED`) is the one helper behind the `status`/`doctor` block, the adopt preview and, through `preview_lines`' new `extra` argument, the `retention-cleanup` preview (before its `next:` line, after the whole output when there is nothing to do); a file without the key prints nothing new. `docs/retention.md` documents the key, both sentences, the older-Manager fail-safe and the not-enforced status; ROADMAP row 50 added, Done. Tests: `TestText`, `TestCleanupPreview`, `TestPage`. `describe_unattended` (CP1) stays the settings line; the helper is `unattended_lines`.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended.py --select test_retention_policy.py --select test_retention_status.py --select test_retention_cleanup.py`, `verdict: exit 0`. Mutations (unknown nested key accepted; vendored base accepting `unattended`) each fail the named tests.
- CP2: the same four selections (one `--select` each), each `verdict: exit 0`. Mutation checks M9-M12 are run with the final verification.
- CP3: `--select` of `test_retention_unattended.py`, `test_retention_policy.py`, `test_retention_cleanup.py`, `test_retention_status.py`, `test_retention_alert.py`, `test_retention_alert_json.py`, `test_retention_run.py`, each `verdict: exit 0`. Mutations M13 (block without the lines), M14 (no not-enforced line) and M15 (cleanup preview without the extra) each fail the named tests in a scratch copy.

- Self-review (`d04164c`): no blocking finding in the milestone diff. Mutations M1-M16 of plan section 3 run in a scratch clone with `--select test_retention_unattended.py`: M10 and M2 did not fail their named tests (the record check masked the dropped `apply` refusal; `True` is refused by `keep_recent`'s floor anyway), so the wrong-kind refusal test now pins the command's own cause and the boolean-as-integer test adds `prune_max_per_run=True`; after that every mutation fails its named tests and the unmutated tree exits 0. `check_record` drops a condition `_names` already holds.
- Full gate at `d04164c`: `python3 tests/run_all.py`, 2459/2459 units, 16588 tests, selection_digest `3e1b9fab...`, tests_digest `0523c302...`, `verdict: exit 0`.

## Functional review checklist

Scope: `unattended-retention-policy` at implementation revision 2 (code head `aada17a`; the later commits change only docs and the state file). The release adds the optional `unattended` key of `.workflow-manager/retention-policy.json` and its own adoption sentence. It enforces nothing: no run becomes unattended in this release.

### Setup

- Work in a scratch clone, never in the product clone. Use a fresh, empty scratch directory `S` outside the product clone (the plan's default, `S=$(mktemp -d "$HOME/.cache/ur-fr.XXXXXX")`, if that location is writable), then `git clone --no-hardlinks <product clone> "$S/cand"`. The clone is the branch head.
- Flows 1-6 and 8 are offline: `git`, `grep` and `python3` on the clone only. No network, GitHub, `gh`, `claude`, `codex` or `ssh` is used.
- Flow 7 is the only flow that needs the full environment: the primed release cache that `tests/run_all.py` needs. It is not runnable in a sandbox without that cache.
- Every diff uses the base commit `87d151c7feebe3a9aebe1194508ab0d5bedf7973`.

### Test data

None. The flows read committed files only. Seed nothing, and do not create a policy file, a work item or a state change.

### Flows

Each flow is run from `$S/cand`. Every grep excludes `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect | Runs in sandbox |
| --- | --- | --- | --- |
| 1 | `git diff --name-status 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- src tests tools .github .claude scripts .workflow-manager` | exactly `M src/workflow_manager/cli.py`, `M src/workflow_manager/retention_cleanup.py`, `M src/workflow_manager/retention_policy.py`, `A tests/fixtures/retention_policy_base.py.txt`, `A tests/test_retention_unattended.py`; nothing under `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/` | yes |
| 2 | `git diff --name-status 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- docs` | `docs/retention.md` and `docs/ROADMAP.md` modified; this item's plan, registry, artifacts and mapping files added; `docs/ai-workflow/WORKFLOW_STATE.json` and `docs/ACTIVE_MILESTONE.md` modified; no other page | yes |
| 3 | `git diff --exit-code 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- docs/exit-codes.md docs/verify.md docs/update.md README.md tests/parallel/resources.json src/workflow_manager/retention_run.py src/workflow_manager/retention_alert.py src/workflow_manager/retention.py` | exit 0: no existing mechanism changed, and nothing runs unattended | yes |
| 4 | `grep -c "Adopt the unattended retention policy" docs/retention.md src/workflow_manager/retention_policy.py`, then `grep -n "unattended" docs/retention.md` | each file holds the sentence at least once; `docs/retention.md` shows the five keys, the two sentences, the older-Manager fail-safe and the not-yet-enforced status | yes |
| 5 | `grep -n "unattended-retention-policy" docs/retention.md docs/exit-codes.md` | no match (the docs name no internal id) | yes |
| 6 | `grep -n "^\| 50 " docs/ROADMAP.md`, then `git diff 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- docs/ROADMAP.md \| grep '^-' \| grep -v '^---'` | one row 50 naming #254 and A1, status `Done`; the diff removes no line (only additions) | yes |
| 7 | In `$S/cand`: `python3 tests/run_all.py --select test_retention_unattended.py`, then one run each with `--select test_retention_policy.py`, `--select test_retention_cleanup.py` and `--select test_retention_status.py`. Then, in a clone made with `git clone --depth 1 --no-hardlinks file://$S/cand $S/shallow`, the first selection again. Optional: apply mutation M9 of plan section 3 in a scratch copy and rerun the first selection | all four exit 0 (the first also in the `--depth 1` clone, where the fail-safe test passes without the base commit); with M9 the first selection exits 1 and the wrong-kind refusal test is among the failures | **no**: needs the full environment and the primed release cache |
| 8 | `python3 tools/release/release.py check-title "feat: add the unattended retention policy key and its own adoption sentence"` | `valid title: feat, release impact minor` | yes (local check only; the pull-request title check on GitHub is not run) |

Dry run of flows 1-6 and 8 by the preparer, in a scratch clone at `07621e0` (the code is the same as `aada17a`): all as expected. Flow 4 counts 1 in `retention_policy.py` and 2 in `docs/retention.md`; flow 5 exits 1 with no output, which is the expected no-match; flow 8 prints `valid title: feat, release impact minor`. Flow 7 was not run by the preparer. The full gate at `aada17a` (2459/2459 units, 16588 tests, `verdict: exit 0`) already ran the same selections, and the narrow `test_retention_unattended.py` run passed at that head.

### Known limitations and out of scope

- The `unattended` key is not enforced. `retention-cleanup` still needs its per-plan `--confirm`, and no run, alert or prune path changes.
- An older Manager refuses a file that carries `unattended` (state `invalid`) and treats the mode as `off`. That is documented; it is not testable here without an older Manager.
- A hand-written ordinary-only record for a file with the key reads `adopted` and authorises nothing unattended. The status block says so.
- A record from an earlier release whose free-form `--confirm` held the unattended sentence beside the ordinary one turns from `adopted` to `record-invalid`. This is the one state-changing case; it is intended and documented.
- No pull request, forge call or release is exercised by these flows. The release is a `feat:` minor, which the title check (flow 8) confirms locally.

## Next action

Functional review (manual). Run the checklist above against the checklist evidence commit recorded by `/prepare-functional-review`, and place any findings at `.ai-review/unattended-retention-policy/feedback/FUNCTIONAL_REVIEW.md`. Then `/accept-milestone`, or `/apply-functional-review` for findings.
