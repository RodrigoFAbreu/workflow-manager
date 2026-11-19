# Active Milestone

## Milestone

**In progress.** `unattended-retention-run` (`governing_workflow_version: "2.2"`, `process`, plan revision 5, base `73a5a72`, branch `milestone/unattended-retention-run`): step A2 of issue #254. `workflow-manager retention-cleanup TARGET --unattended` runs the archive-and-remove cleanup without the per-plan `--confirm` sentence, under the authority of the unattended adoption sentence (A1), with the Manager-side `keep_recent`, one audit line per action and per refusal outside the repository, and a `--json` document. Prune is not part of this item (A3).

Plan: `docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_RETENTION_RUN_PLAN.md`.

Pull request title: `feat: run the retention cleanup unattended under the adopted unattended policy, with an audit file`.

### Checkpoints

- CP1 -- the unattended authority check and the `keep_recent` selection: **complete**. `retention_cleanup.unattended_refusal` is the pure check of authority rows d to f (no `unattended` key, the adoption without the unattended sentence, `unattended.cleanup` false), asked of `PolicyState.unattended` only; `preflight` gains the keyword `unattended=False` and calls it at step 2b, right after the policy is known adopted with a cleanup mode and before anything starts a process. `select` now keeps back the newest `keep_recent - report.keep_recent` entries of `report["finished"]` (taken before the review-folder filter, never planned, not listed as skipped, still counted in the measured numbers) whenever the state authorises unattended cleanup, so the preview, the confirmed run and the unattended run share one plan and one digest rule. `Plan` gains `kept`, `keep_recent` and `engine_keep`; `preview_lines` prints the `keep:` line only when items are kept. Tests: `tests/test_retention_unattended_run.py`.
- CP2 -- the audit writer: **complete**. New module `retention_unattended.py`: `audit_path`/`state_base` (`$XDG_STATE_HOME` when absolute, else `~/.local/state`), `open_audit` (location refused inside the repository or the archive store by real path; missing parents and the `workflow-manager/` directory created `0700`; file `O_WRONLY|O_APPEND|O_NOFOLLOW`, created `0600` then `fchmod`; existing file or directory must be the user's and not group- or world-writable; `stat` seam; `AuditRefusal` with a cause and one step) and `Audit.line` (the eleven fields, one `os.write` per line, a failed or short write raises the distinct `AuditWriteError`; `clock`, `run_id` and `write` seams). Nothing calls it yet. Tests: `TestAuditWriter` in `tests/test_retention_unattended_run.py`.
- CP3 -- the unattended run and its JSON document: **complete**. `retention-cleanup TARGET --unattended [--json]`: `argument_refusal` (rows a and b, before anything is read), then the managed check and installation-record read, then `retention_unattended.run_command`: the audit is opened (refusal on failure), the preflight runs with `unattended=True` (every `Refusal` writes one `preflight` line, a failed write adds the audit cause to stderr), the plan is selected, an empty plan prints `nothing to do` (no line) or `nothing eligible` (one `plan` line), otherwise the `plan`/`started` line is written before the first action and `retention_run.run` runs with the new `unattended` (per-item re-read also requires the adoption to still authorise unattended cleanup) and `observer` parameters (one audit line per step; an observer failure after a succeeded step stops the run before the next call, exit 1, closing line says the step had succeeded). `--json` prints one `retention_cleanup_run` document on stdout, progress on stderr, nothing on stdout for a refusal. Tests: `tests/test_retention_unattended_run.py`.
- CP4 -- the status text, the docs and the ROADMAP row: **complete**. `NOT_ENFORCED` is now `enforced by retention-cleanup --unattended for the cleanup part (archive and remove); prune is not run unattended yet`, printed by every output that printed the old line; the adopted block's last line adds `or, under the adopted unattended policy, with --unattended` only for an unattended adoption with `cleanup` true (every other adopted state keeps today's bytes); the `adopt-retention-policy` help and the module docstring say the same. `docs/retention.md` documents the unattended run (authority and refusals, what the one-time adoption authorises, `keep_recent` and the keep line, nothing-to-do and nothing-eligible, the audit file with its eleven fields, location, modes and steps, `--json`, exit status, prune not yet unattended) and `docs/exit-codes.md` the `--unattended` and `--json` cases. ROADMAP row 51 added in row 50's style, Done in the item's own wording. Tests: A1's goldens moved to the new wording with the old line asserted absent (`tests/test_retention_unattended.py`), `TestBlockLastLine` in `tests/test_retention_policy.py`, page needles.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended_run.py --select test_retention_unattended.py --select test_retention_run.py --select test_retention_cleanup.py --select test_retention_policy.py`, 276 tests, `verdict: exit 0`. Mutations M3 (row d dropped), M6 (authority check removed from the preflight), M7 (`keep_recent` ignored) and M8 (`keep_recent` instead of `keep_recent - 3`) each fail the named tests of `test_retention_unattended_run.py`; the unmutated tree is green.
- CP2: `python3 tests/run_all.py --select test_retention_unattended_run.py`, 49 tests, `verdict: exit 0`. Mutations (no `O_APPEND`, no `fchmod`, short write accepted) each fail the named tests; the unmutated tree is green.
- CP3: `python3 tests/run_all.py --select test_retention_unattended_run.py`, 80 tests, `verdict: exit 0`; `--select test_retention_run.py --select test_retention_cleanup.py --select test_retention_unattended.py --select test_retention_policy.py --select test_retention_status.py`, 338 tests, `verdict: exit 0`. Mutations M16 (no start line), M17 (observer failure ignored) and M18 (re-read without the authority condition) each fail the named tests; the unmutated tree is green.
- CP4: `python3 tests/run_all.py --select test_retention_unattended.py --select test_retention_unattended_run.py --select test_retention_cleanup.py --select test_retention_status.py`, 288 tests, and `--select test_retention_policy.py` (87 tests), `--select test_docs.py --select test_operator_ux_docs.py --select test_operator_ux.py --select test_retention_run.py --select test_retention_alert.py`, each `verdict: exit 0`.
- Self-review (`c558a6e`, tests only): the full milestone diff was reviewed with no code finding. Every mutation of plan section 3 (M1 to M25, with M15 as M15a and M15b, and M20, M21 and M24 each as two) was run at `ea2e354` in a scratch clone. 27 of 29 failed their named tests. M9 and M19 survived: two test gaps, the code being correct. `test_the_preview_and_the_confirmed_run_apply_the_same_keep` (a keep that holds back an item the thresholds would plan) and `test_a_policy_adopted_again_with_another_digest_stops_the_run` (an adopted, authorising state with another digest) close them, and each fails under its mutation at `c558a6e`.
- Full gate: `python3 tests/run_all.py` at `c558a6e`, 2471/2471 units, 16677 tests, `verdict: exit 0` (an earlier run at `ea2e354` was also green, but it is superseded by the test change).
- Implementation revision 2 (after the local review round 2 and the external review round 2, APPROVE): `ddcd3d0` changed `src/workflow_manager/retention_unattended.py` (FIFO audit path refused without blocking) and its tests (85 tests in `test_retention_unattended_run.py`, green); `5d29b77` and later change docs and workflow state only. Full gate at `5d29b77`: `python3 tests/run_all.py`, 2471/2471 units, 16680 tests, `verdict: exit 0`. Current for this checklist.

## Functional review checklist

Gate: `AWAITING_FUNCTIONAL_REVIEW`, implementation revision 2, implementation head `5d29b77`, base `73a5a72`. The flows are those of plan section 5 (`docs/ai-workflow/WORKFLOW_MANAGER_UNATTENDED_RETENTION_RUN_PLAN.md`, revision 5). Changes from that section, all in how a command is written and not in what it checks: the table cells carry no `|` (flows 4, 6, 7), and flow 6(d) greps the code for the phrase's first half (see limitations).

### Setup

1. Run in a sandbox: no network; `gh`, `claude`, `codex` and `ssh` are stand-ins first on `PATH` that refuse and log; `PATH` is the stand-ins plus `/usr/bin:/bin`. Python 3 standard library only.
2. Make a scratch clone outside the product clone, and run every flow from it:

   ```
   B=73a5a7212b26238dd8a36a45c7a970c8518b3f52
   S=$(mktemp -d "$HOME/.cache/ur-run-fr.XXXXXX")
   git clone -q --no-hardlinks <product clone> "$S/cand"
   cd "$S/cand"
   ```

3. Nothing writes into the product clone. Flow 9 needs the full environment (network and the primed release cache) and is not sandbox-runnable.

### Test data

None. The flows read the committed tree of the scratch clone. Flow 8 checks that it writes nothing.

### Flows

| Flow | Sandbox | Do | Expect |
| --- | --- | --- | --- |
| 1 | yes | `git diff --name-status $B HEAD -- src tests tools .github .claude scripts .workflow-manager` | M `cli.py`, `retention_cleanup.py`, `retention_policy.py`, `retention_run.py`, `tests/test_retention_policy.py`, `tests/test_retention_unattended.py`; A `retention_unattended.py`, `tests/test_retention_unattended_run.py`. Nothing under `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/`. |
| 2 | yes | `git diff --name-status $B HEAD -- docs` | M `ACTIVE_MILESTONE.md`, `ROADMAP.md`, `WORKFLOW_STATE.json`, `exit-codes.md`, `retention.md`; A the plan, `registry/unattended-retention-run-registry.json`, `registry/unattended-retention-run-artifacts.json`, `requirements/unattended-retention-run-mapping.json`. No other page. |
| 3 | yes | `git diff --exit-code $B HEAD -- docs/verify.md docs/update.md docs/release-history.md README.md tests/parallel/resources.json src/workflow_manager/retention_alert.py src/workflow_manager/retention_alert_json.py src/workflow_manager/retention.py` | Exit 0. |
| 4 | yes | `grep -n -e "retention-cleanup TARGET --unattended" -e "retention-audit.jsonl" -e keep_recent -e 0600 -e 0700 docs/retention.md`, then `grep -n unattended docs/exit-codes.md` | The page names the command, the audit file with its modes and `keep_recent`. The exit-code grep shows the flag in the `retention-cleanup` rows. |
| 5 | yes | `grep -rn -e unattended-retention -e "#254" -e "#259" docs/retention.md docs/exit-codes.md` | No match (exit 1). |
| 6 | yes | (a) `grep -rn "nothing runs unattended, and retention-cleanup" src docs/retention.md`; (b) `grep -rn "prune is not run unattended yet" src docs/retention.md`; (c) `grep -n -e 'retention-cleanup runs with --confirm"' -e 'retention-cleanup runs with --confirm$' src/workflow_manager/retention_policy.py docs/retention.md`; (d) `grep -n "with --confirm or, under the adopted unattended" src/workflow_manager/retention_policy.py docs/retention.md`; (e) `grep -n "with --unattended" src/workflow_manager/retention_policy.py src/workflow_manager/cli.py docs/retention.md` | (a) no match. (b) one match in `retention_policy.py` and one in `docs/retention.md`. (c) exactly two: the no-authority literal in `retention_policy.py` (line 623) and the no-key block in `docs/retention.md` (line 173). (d) one match in each file (`retention_policy.py:618`, `docs/retention.md:179`). (e) matches in the unattended policy line, the `adopt-retention-policy` help in `cli.py` and the page. |
| 7 | yes | `grep -n "^| 5[01] " docs/ROADMAP.md`, then `git diff $B HEAD -- docs/ROADMAP.md` | Rows 50 and 51. Row 51 names #254 and A2 with status `Done (accepted by policy; a feat: change)`. The diff adds lines only: no `-` line. |
| 8 | yes | `XDG_STATE_HOME="$S/state" PYTHONPATH=src python3 -m workflow_manager retention-cleanup "$S" --unattended --confirm x; echo $?; ls "$S/state"`, then `XDG_STATE_HOME="$S/state" PYTHONPATH=src python3 -m workflow_manager retention-cleanup "$S" --json; echo $?` | First run: exit 2, stderr says `--confirm and --unattended cannot be combined`, `$S/state` does not exist. Second run (`--json` alone): exit 2, empty stdout. |
| 9 | no (full environment) | In `$S/cand`: `python3 tests/run_all.py --select test_retention_unattended_run.py`, then one run each with `--select test_retention_unattended.py`, `--select test_retention_run.py`, `--select test_retention_cleanup.py`, `--select test_retention_policy.py` and `--select test_retention_status.py` | All six exit 0. With mutation M16 of plan section 3 applied in a scratch copy, the first selection exits 1 and the first-write-fails test is among the failures. |
| 10 | yes | `python3 tools/release/release.py check-title "feat: run the retention cleanup unattended under the adopted unattended policy, with an audit file"` | `valid title: feat, release impact minor`. |

### Known limitations

- The flows are greps, diffs and argument refusals. They do not run an unattended cleanup against a real archive store, a real managed installation or a real forge. The run's behaviour (archive, verify, remove, the audit lines, the `--json` document, the FIFO refusal) is covered by `tests/test_retention_unattended_run.py` and the mutation evidence above, not by these flows.
- Flow 6(d) differs from the plan's wording. The code side of the phrase is split across two concatenated string literals (`retention_policy.py:618-619`), so a grep for the full phrase cannot match the source. The checklist greps the first half of the phrase in the code and the full phrase in the page. The rendered text is pinned by the byte-for-byte block tests. The plan is not edited: it is at an approved revision.
- Out of scope: prune is not run unattended (A3). A refusal under `--json` writes nothing to stdout, by design (plan 2.4).
- The optional findings recorded in `WORKFLOW_STATE.json` have no disposition yet. Each gets one at acceptance.

## Next action

Functional review: the user runs the checklist above in a scratch clone and writes any findings to `.ai-review/unattended-retention-run/feedback/FUNCTIONAL_REVIEW.md`. Then `/review-functional` (optional) and `/apply-functional-review` for each finding. Nothing else is open for this item.
