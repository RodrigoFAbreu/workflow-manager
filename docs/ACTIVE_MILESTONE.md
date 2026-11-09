# Active Milestone

## Milestone

`retention-policy-file` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `0db1638`, branch `milestone/retention-policy-file`): roadmap row 36 (#90, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

First slice of the owner's retention track: the retention policy file (`.workflow-manager/retention-policy.json`, closed and strict), its strict loader (`src/workflow_manager/retention_policy.py`, mode `off` unless the file is adopted unchanged), the `workflow-manager adopt-retention-policy` command (read-only preview; with the literal sentence bound to the digest it writes `.workflow-manager/retention-adoption.json`) and a read-only block in `status --retention` and `doctor --retention`. Nothing alerts, nothing is sent, nothing is cleaned in this slice.

### CP1: the policy file: schema, loader, adoption, report, docs -- complete

- Files: `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_policy.py` (70 tests, six classes), `tests/test_operator_ux.py` (`TARGET_COMMANDS`), `docs/retention.md`, `docs/exit-codes.md`.
- One deviation from the plan text, to the safe side: a refusal for a wrong `--confirm` does not print the sentence again (the preview is the one place it appears). One test is added beyond the plan's list: `apply` itself refuses a directory swapped for a link after the load (M19's apply half is unreachable through the CLI, because the load already reports a link).
- Evidence: `python3 tools/check_docs.py` exit 0; `--select` of `test_retention_policy.py` (71 tests), `test_retention_status.py` (74), `test_operator_ux.py` (130) and `test_docs.py` (44) each exit 0; the full gate `python3 tests/run_all.py`: full selection, 2369/2369 units, 16023 tests, 8 workers, head `50c505c` plus the CP1 working tree, `verdict: exit 0`.
- Failure-only mutations M1 to M21 (plan section 3), each on a fresh copy, the named test run alone from `tests/`: the unmutated copy passes, and every mutation fails its named test (M1 and M19 in two parts each: unknown key at either level; the load check and the apply check; M5 in two parts: policy and record size).

### CP2: bookkeeping and the release -- complete

- Files: `docs/ROADMAP.md` (row 36, Current; Done at acceptance), this record.
- No version is edited. The pull-request title `feat: add the retention policy file and its adoption command` passes `python3 tools/release/release.py check-title` (feat, release impact minor); the release workflow computes the minor from the tags after `main`'s run is green.
- After the release publishes, the orchestrator's follow-up `docs:` pull request adds the row to `docs/release-history.md` and moves the `Last checked with:` stamps of `docs/retention.md` and `docs/exit-codes.md`; a comment on #90 records the slice and lists plan section 2.6 as the next rows.

### Self-review and full gate

- One confirmed defect, fixed in `43346d6`: `check_record` matched `adopted_at` with `^...$` and `\d`, so a record whose timestamp ended in a newline, or used non-ASCII digits, was accepted, and the newline reached the `status --retention` block raw. It is now a full match of ASCII digits; `TestStates.test_record_shape_refusals` gains both cases, and each fails on the old check (run alone from `tests/` on a scratch copy holding the old module) and passes on the fix.
- No other finding: the loader, the adoption command, the block and the pages agree with plan sections 2.1 to 2.5; nothing in `retention.py`, `scripts/`, `.claude/` or `.github/` changed.
- Evidence: `--select test_retention_policy.py` exit 0 (71 tests); the full gate `python3 tests/run_all.py`: full selection, local, 8 workers, head `43346d6`, 2369/2369 units, 16023 tests, `verdict: exit 0`.
