# Active Milestone

## Milestone

`retention-policy-file` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 2, base `0db1638`, branch `milestone/retention-policy-file`): roadmap row 36 (#90, wf#84). A `feat:` pull request title; a Manager release (minor) follows.

First slice of the owner's retention track: the retention policy file (`.workflow-manager/retention-policy.json`, closed and strict), its strict loader (`src/workflow_manager/retention_policy.py`, mode `off` unless the file is adopted unchanged), the `workflow-manager adopt-retention-policy` command (read-only preview; with the literal sentence bound to the digest it writes `.workflow-manager/retention-adoption.json`) and a read-only block in `status --retention` and `doctor --retention`. Nothing alerts, nothing is sent, nothing is cleaned in this slice.

### CP1: the policy file: schema, loader, adoption, report, docs -- complete

- Files: `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_policy.py` (70 tests, six classes), `tests/test_operator_ux.py` (`TARGET_COMMANDS`), `docs/retention.md`, `docs/exit-codes.md`.
- One deviation from the plan text, to the safe side: a refusal for a wrong `--confirm` does not print the sentence again (the preview is the one place it appears). One test is added beyond the plan's list: `apply` itself refuses a directory swapped for a link after the load (M19's apply half is unreachable through the CLI, because the load already reports a link).
- Evidence: `python3 tools/check_docs.py` exit 0; `--select` of `test_retention_policy.py` (71 tests), `test_retention_status.py` (74), `test_operator_ux.py` (130) and `test_docs.py` (44) each exit 0; the full gate `python3 tests/run_all.py`: full selection, 2369/2369 units, 16023 tests, 8 workers, head `50c505c` plus the CP1 working tree, `verdict: exit 0`.
- Failure-only mutations M1 to M21 (plan section 3), each on a fresh copy, the named test run alone from `tests/`: the unmutated copy passes, and every mutation fails its named test (M1 and M19 in two parts each: unknown key at either level; the load check and the apply check; M5 in two parts: policy and record size).

### CP2: bookkeeping and the release -- pending

- `docs/ROADMAP.md` row 36 (Done at acceptance); this record's final form.
