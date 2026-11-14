# Active Milestone

## Milestone

`retention-max-age` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 4, base `8ff4f43`, branch `milestone/retention-max-age`): roadmap row 43 (#215). A `feat:` pull request title (`feat: add an age threshold to the retention policy`, Manager 1.19.0); the release-history row follows in a `docs:` pull request.

One new optional policy key, `thresholds.finished_max_age_days` (integer, 1 to 3650): finished work items with a review folder, beyond the 3 most recent, whose last transition is more than N days before the report's own `generated_at` count toward the retention alert and are planned by `retention-cleanup`, oldest first, at most 5 per run. An item with no usable last transition is never old.

### CP1: the policy key and the alert line -- complete (`66ba841`)

- `retention_policy.THRESHOLDS` gains the key (maximum 3650, unit ` days`); `schema_version` stays 1. `retention_alert.aged(report, days)` is the one helper; `evaluate`, `_shown` and `render` special-case the key (label `finished older than N days`, reached at one old item).
- Tests: T1 to T3 (policy), A1 to A6 (alert). Roadmap row 43 added.

### CP2: the cleanup plan and the page -- complete (`d64d6c3`)

- `retention_cleanup.select` plans the age rule: `LOWERED` gains the key (reached at one old item not yet planned), the loop takes an item when a count or size threshold is reached or the item is old, `Plan.unknown_age`, the `age not known` line and the age wording in the preview. `docs/retention.md` documents the key, the older-Manager refusal, the alert line and the cleanup rule.
- Also: `retention_alert._moment` no longer calls `retention_policy._is_timestamp` (a private cross-use `TestNoPrivateCrossUse` forbids); it carries its own pattern.
- Tests: C1 to C8 (cleanup). The absent-key golden (flow 5) is identical except the `Result` repr's new `unknown_age` field.

### Self-review -- complete (`3c2e096`)

- Every mutation of plan section 3 measured in a scratch clone: three rows first differed from the table (A2, C1, `LOWERED`), each repaired by changing a test (C7 without an unknown-age item, the nothing-to-do case folded into C3, C2 reads the key with a default, C5 and C8 walk a young item first); after the repair all 18 measured sets equal the table.
- `docs/retention.md`: the alert example lists the age line where `render` prints it (before archives); the cleanup's "below its limit" sentence says what that means for the age threshold.
- Absent-key golden (flow 5): `describe`, `block`, `render` and `preview_lines` for three key-less policies over three reports are byte-identical at the base and the candidate (88 lines).
- Known limitation for the reviewers (the plan pins it): the age line's `next:` step is `retention.next_step`, which names the newest archivable item, possibly a young one.
- Full gate at `3c2e096`: `python3 tests/run_all.py`, 2410/2410 units, 16273 tests, `verdict: exit 0`.

### Implementation review -- complete (revision 2, `9507c9c`)

- Revision 1 was revised (`REVISE`: LIR1-001, an age-only confirmed run was not pinned to the five planned items); the fix is `9507c9c`, a test only. Revision 2 is approved by both stages: local `LOCAL_MODEL_IMPLEMENTATION_REVIEW` (Claude Opus 5.5, `APPROVE`) and manual external `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` (`APPROVE`).
- Technical approval recorded by policy (`cb7aa9f`, `POLICY_SATISFIED`).
- Full gate at `9507c9c` (the implementation summary's record): `python3 tests/run_all.py`, 2411/2411 units, 16274 tests, `verdict: exit 0`.

## Functional review checklist

Checklist for implementation revision 2. Run it on a clean checkout of the checklist's evidence commit on `milestone/retention-max-age`. `BASE` is `8ff4f435d8890d906dd167eac711434eaf751f03`. Flows 1 to 10 are plan section 6; the sandbox column says which can run offline.

**Setup**

- Tools: `git`, the repository's `python3`, `grep`, `sed`, `tar`, `diff`. No network, `gh`, `claude`, `codex` or `ssh` is needed for any flow here. The `retention-cleanup` preview and the alert in `verify`/`doctor` are not in this checklist: they need the forge report.
- Confirm `BASE` is in the clone (`git cat-file -e BASE`).
- Make every copy and driver under a scratch directory (`$TMPDIR`), never inside the product clone. Read exit codes with `; echo $?`, not through a pipe.

**Verification state**

- The full gate at `9507c9c` is the current evidence. No file under `src/`, `tests/`, `tools/`, `scripts/` or `docs/retention.md` has changed since it (checked at checklist preparation: the two later commits change `docs/ai-workflow` only).
- `.ai-review/retention-max-age/current/TEST_RESULTS.md` is the revision-1 record at `3c2e096` (2410/2410 units, 16273 tests). It is not updated for revision 2; the implementation summary carries the revision-2 gate.

**Test data**

- `tests/fixtures/retention_report.json` (`generated_at` `2026-10-27T00:00:00Z`), and the incomplete and empty-`finished` variants of flow 5.
- Flows 5 and 6 use a scratch driver that is not committed. It renders `describe`, `block`, `retention_alert.render` and `retention_cleanup.preview_lines`. Flow 6 uses an adopted `both` policy with `finished_max_age_days` 30 over a report of 7 old, 1 young and 1 unknown-age item.

**Flows**

| Flow | Sandbox | Do | Expect |
| --- | --- | --- | --- |
| 1 | offline | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only `retention_policy.py`, `retention_alert.py`, `retention_cleanup.py`, the three test files, `docs/retention.md` and `docs/ROADMAP.md` |
| 2 | offline | `git diff --exit-code BASE -- tools .claude scripts .workflow-manager tests/parallel src/workflow_manager/cli.py src/workflow_manager/retention.py src/workflow_manager/retention_run.py docs/exit-codes.md docs/verify.md README.md docs/README.md; echo $?` | no output, `0` |
| 3 | offline | `grep -n 'finished_max_age_days' src/workflow_manager/retention_policy.py` and `grep -n '^SCHEMA_VERSION' src/workflow_manager/retention_policy.py` | the entry with maximum 3650; `SCHEMA_VERSION = 1` |
| 4 | offline | `grep -n -e 'older Manager' -e 'finished_max_age_days' docs/retention.md` | the table row, and the sentence that an older Manager refuses the file and treats the mode as `off`; `schema_version` stays 1 |
| 5 | offline, needs the driver | `git archive BASE src \| tar -x -C $TMPDIR/base`; run the driver with `PYTHONPATH=$TMPDIR/base/src` and again with the candidate's `src`; `diff` the two outputs | no difference (the absent-key output is byte-identical) |
| 6 | offline, needs the driver | the driver on the candidate only, with the age-only policy | the alert line `finished older than 30 days: 7 items, 1 more with no usable last transition (not counted): reached`; the plan takes `old0` to `old4`, oldest first, and no young or unknown-age item; the `age not known` line; `after this run: finished older than 30 days 2` and the cap line (`stopped at the cap of 5 per run; run it again`); at most 5 items |
| 7 | offline | `grep -n -E '^. 43 ' docs/ROADMAP.md` and `grep -c -E '^. 44 ' docs/ROADMAP.md` | row 43 present, last cell `Current`; `0` |
| 8 | offline | `python3 tools/check_docs.py; echo $?` | no problem line; `0` |
| 9 | full environment: a primed release cache (a cold cache with no network exits 2, `PrimingError`) | in a scratch copy, apply with `sed` the mutations of T1, A1, A5, C3, C5 and the `LOWERED` one (the key removed) from plan section 3; run `python3 tests/run_all.py --select test_retention_policy.py --select test_retention_alert.py --select test_retention_cleanup.py --select test_retention_status.py` on each | T1 fails only T1; A1 fails A1 and C8; A5 fails only A5; C3 fails only C3; C5 fails only C5; with `LOWERED` changed, exactly C1 and C3 to C8 fail; the unmutated copy exits 0 |
| 10 | offline | `python3 tools/release/release.py check-title "feat: add an age threshold to the retention policy"; echo $?` | `valid title: feat, release impact minor`; `0` |

**Known limitations (out of scope for this item)**

- The age line's `next:` step names the newest archivable item, which may be a young one (pinned by the plan).
- An item with no usable `last_transition` is never old. The count and size rules may still plan it, as they do today.
- Not exercised here: the forge report, a real `retention-cleanup --confirm` run, and an installed Workflow 2.25.5 or later. The older-Manager refusal is documented, not run.
- The Controller-owned JSON alert output is a later item. The release-history row for 1.19.0 is a separate `docs:` pull request after acceptance.
- Flows 5 and 6 need a driver that is not in the repository.

**Next action:** functional review (`AWAITING_FUNCTIONAL_REVIEW`, implementation revision 2). Findings go to `.ai-review/retention-max-age/feedback/FUNCTIONAL_REVIEW.md`.
