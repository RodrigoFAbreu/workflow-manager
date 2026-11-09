# Active Milestone

## Milestone

`retention-alert` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `7810ff6`, branch `milestone/retention-alert`): roadmap row 37 (#90, #192, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

Second slice of the owner's retention track: for a retention policy adopted with mode `notify` or `both`, `verify` and `doctor` evaluate the four thresholds against the retention report and print a `retention alert:` block when one is reached (one `not evaluated` line when the report cannot be had). The alert never starts a script that is not the release's, never changes an exit code, and sends and cleans nothing. The four follow-ups of #192 ride along in CP2.

### CP1: the alert: evaluation, verify and doctor wiring, tests, docs -- complete

- Files: `src/workflow_manager/retention_alert.py` (new: `evaluate`, `script_state`, `alert_lines`), `src/workflow_manager/retention.py` (`PRUNE_FROM`, the prunable line, `section(..., outcome)`), `src/workflow_manager/cli.py` (wiring, help text, `_installed_script_state`), `tests/test_retention_alert.py` (53 tests, nine classes), `tests/test_retention_status.py` (`TestPruneLine`), `docs/retention.md`, `docs/verify.md`, `docs/exit-codes.md`.
- Deviations from the plan text: none of substance. `not-executable` is not a case of the real script (the release lists it as non-executable), so `TestScriptState` covers modified, missing, unlisted and the no-script release; the doctor `--release-version` case picks the newest tested release whose script digest differs from the newest's (2.25.5 today) and skips when none does. The in-process `cli.main` helper asserts the patched seam's `call_count` in `TestGate` and `TestOutput`.
- Evidence: `python3 tools/check_docs.py` exit 0; `--select` of `test_retention_alert.py` (53 tests), `test_retention_status.py` (78), `test_retention_policy.py` (71), `test_operator_ux.py` and `test_docs.py` each `verdict: exit 0`.
- Failure-only mutations (plan section 3), each on a fresh copy, the named tests run alone from `tests/`: the unmutated copy passes and every mutation fails: M1 to M18 (M15 in two parts: order and the unindented `next:`), M24 to M27 (M27 in two parts), M29 to M36 (M34 and M36 in two parts each). M37 is not mutated mechanically: the stub-based cases assert the seam's `call_count` instead. M19 to M23 and M28 belong to CP2.

### CP2: the #192 follow-ups, bookkeeping and the release -- complete

- Files: `src/workflow_manager/retention_policy.py` (`_is_timestamp` with `strptime`, `_sync_directory` after the replace, the `invalid` and refusal steps name `adopt-retention-policy ... to preview it`, the adopted block's wording), `src/workflow_manager/cli.py` (help text names the link and non-regular-file refusals; adoption output and help no longer say "only reads"), `tests/test_retention_policy.py` (`TestFollowUps`, six tests; the exact-block test follows the new wording), `docs/retention.md` (the example line moves with `block`).
- Evidence: `--select test_retention_policy.py` (77 tests) `verdict: exit 0`; `python3 tools/check_docs.py` exit 0; full gate `python3 tests/run_all.py`: 2380/2380 units, 16086 tests, `verdict: exit 0`, head 3f08866, no `OrphanProcessError`.
- Failure-only mutations (fresh copy each, `TestFollowUps` run alone from `tests/`): the unmutated copy passes; M19, M20 (both places), M21, M22, M23 and M28 (block, adoption output, help, docs example) each fail.
- `grep -rn "only reads" src docs/retention.md` finds nothing. No version edited. PR title: `feat: warn in verify and doctor when an adopted retention threshold is reached`.

## Functional review checklist

Scope: the retention alert (`verify` and `doctor` for a retention policy adopted with mode `notify` or `both`, the `retention alert:` block and its one `not evaluated` line) and the four #192 follow-ups (the validation and wording of `adopt-retention-policy`).

Automated verification is current: the full gate `python3 tests/run_all.py` passed at head `67d9aa1` (2380/2380 units, 16086 tests, `verdict: exit 0`). Every later commit (`00fcb22`, `2ddfba7`) changes only `docs/ai-workflow/WORKFLOW_STATE.json`, so no code, test or runner file has changed since that gate.

### Setup

Flows 1 to 7 run offline in a scratch clone and write nothing into the product clone. Flows 8 to 10 need the full environment (the release cache, and the network for its first priming); they run last, outside the sandbox.

```
S=$(mktemp -d "$HOME/.cache/ra-fr.XXXXXX")
git clone --no-hardlinks <product clone> "$S/cand"
git -C "$S/cand" remote remove origin
export PYTHONPATH="$S/cand/src"
```

Use `$HOME/.cache` for the scratch directory, not `/tmp`. Flows 5 and 6 are Python snippets kept outside the clone; they put `$S/cand/src` on `sys.path` themselves, because `python3 -I` ignores `PYTHONPATH`.

### Test data

- Flows 1 to 7: no repository and no forge. Flows 5 and 6 build their values by hand, as given in those rows.
- Flow 10: a scratch managed repository installed from the newest tested release that ships `scripts/workflow_retention.py` (2.20.0 or later), with an adopted `notify` policy whose `finished_items` limit is 1.

### Flows

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd "$S/cand" && git diff --stat 7810ff66bd7b43b3b0ba60d7fa790cd630fd4732 HEAD -- src tools tests docs .github scripts .claude` | The code files `src/workflow_manager/retention_alert.py` (new), `retention.py`, `retention_policy.py`, `cli.py`, `tests/test_retention_alert.py`, `tests/test_retention_policy.py`, `tests/test_retention_status.py`, `docs/retention.md`, `docs/verify.md` and `docs/exit-codes.md`, plus bookkeeping under `docs` (roadmap, this file, state, the plan's registry, mapping and artifacts). Nothing under `scripts/`, `.claude/`, `.github/`, `tools/` or `tests/parallel/`. |
| 2 | `grep -n '^class Test' "$S/cand/tests/test_retention_alert.py"` | `TestEvaluate`, `TestGate`, `TestOutput`, `TestUnavailable`, `TestExitCodes`, `TestNextStep`, `TestNothingElse`, `TestDocs`, `TestScriptState`. `TestFollowUps` is in `tests/test_retention_policy.py`. |
| 3 | `grep -n 'retention alert' "$S/cand/docs/retention.md" "$S/cand/docs/verify.md" "$S/cand/docs/exit-codes.md"`, then `grep -n 'retention-alert' ` on the same three files and keep only the lines that do not contain `the-retention-alert` | The first grep matches in all three pages. The second keeps nothing: the only matches are the `#the-retention-alert` anchor links, so no page names the work item. |
| 4 | `python3 -m workflow_manager adopt-retention-policy --help`, then `verify --help` and `doctor --help` | The first names `.workflow-manager is a link` and `the record path is not a regular file`, and says it evaluates thresholds in verify and doctor. The other two name the retention alert and say it never changes the exit code. |
| 5 | `python3 -I` on a snippet that imports `retention_alert` and `retention_policy` from `$S/cand/src` and calls `retention_alert.evaluate`. The state is `retention_policy.PolicyState(retention_policy.ADOPTED, mode="notify", policy={"schema_version": 1, "mode": "notify", "thresholds": {...}}, digest="ab"*32)`. A report is a dict with `complete`, `read_errors` (empty), `not_finished` (empty), `finished` (a list of `{"review_folder": {"present": True}}` or `False` entries) and `totals` (`finished_folder_bytes`, `archives`, `prunable`, `finished`). Variants: A 10 present, `finished_items` 10. B 9 present, limit 10. C 8 present and 2 absent, limit 10. D 524288000 folder bytes, `finished_folder_mib` 500. E 524287999 bytes, limit 500. F 9 present with `complete` false, limit 10. G 10 present with `complete` false, limit 10. H mode `cleanup`, 5 present, limit 1. I state `CHANGED` (mode `off`), 5 present, limit 1. J mode `both`, report `None`, limit 10. | A reached (10). B within (9). C within (8). D reached (524288000 bytes, limit 500). E within. F unknown, lower bound. G reached, lower bound. H and I an empty list. J unknown, value `None`. |
| 6 | `python3 -I` on a snippet that calls `retention_policy.check_record` on a record built from `policy = {"schema_version": 1, "mode": "notify", "thresholds": {"finished_items": 3}}`, `digest = digest_of(policy)` and `{"schema_version": 1, "sha256": digest, "adopted_at": STAMP, "confirmation": sentence(digest), "policy": policy}`. Then `retention_policy.block(PolicyState(retention_policy.INVALID, problems=("the mode must be one of off, notify, cleanup, both",)), Path("/nonexistent/repo"))`. | A valid stamp gives no problem. `2026-99-99T99:99:99Z` and `2026-02-30T00:00:00Z` each give one problem, `record adopted_at is not a UTC timestamp`. The last line of the block is `next:` and names `workflow-manager adopt-retention-policy` with `to preview it`. |
| 7 | `python3 "$S/cand/tools/check_docs.py"` | Exit 0. |
| 8 | (full environment) In `$S/cand`, apply each mutation M1 to M37 of the plan's section 3 with `sed` to a scratch copy, and run its named test alone from `tests/`. First the unmutated copy. | The unmutated copy passes. Every mutation fails. |
| 9 | (full environment) `python3 tests/run_all.py --select test_retention_alert.py`, then the same for `test_retention_policy.py`, `test_retention_status.py`, `test_operator_ux.py` and `test_docs.py`. | Exit 0 for each, with no `OrphanProcessError`. |
| 10 | (full environment) In the scratch managed repository, with the script untouched: `workflow-manager verify` and `workflow-manager doctor`. Then replace `scripts/workflow_retention.py` with a stub that writes a marker file and reports 2 finished items, and run both again. Then delete the stub. | Untouched: the script's own answer, either the alert block or one `not evaluated` line carrying the script's refusal (the scratch repository has no forge). The exit code is the same as without the policy. With the stub: one `not evaluated` line saying the script does not match the release, with `next: workflow-manager update TARGET --force`, no marker file, and the same exit code as without the policy (`verify` still reports `modified`). Stub removed: the `missing` problem and the same line. |

### Known limitations and out of scope

- A complete answer needs `gh` signed in and the network. The flows 1 to 7 never reach a forge. Flow 10 reports the script's own refusal in a scratch repository with no forge; that is the expected result, not a defect.
- Cost (O1): every `verify` and `doctor` of an adopted `notify` or `both` repository runs the retention report, one forge query per finished work item: about 20 to 40 seconds for 25 items, 300 seconds at worst. A repository without such a policy pays nothing.
- No exit code changes (O2). A reached threshold never makes `verify` or `doctor` fail.
- `finished_items` counts finished work items whose review folder is still present, not `totals.finished`, so the owner's archive-then-remove step lowers it.
- An incomplete report with a number at or above its limit is reached (a lower bound); below the limit it is unknown, never within.
- Not built here: a switch to skip the evaluation for one run, notifications (sending), and cleanup. The alert is not a `doctor` `[warning]` finding.

### Where findings go

Findings go to `.ai-review/retention-alert/feedback/FUNCTIONAL_REVIEW.md`, the `functional_review_path` that `python3 scripts/workflow_fingerprint.py --resolve-feedback-path retention-alert` prints.
