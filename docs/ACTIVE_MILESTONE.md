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

## Next action

Run `/milestone-implement unattended-retention-policy` again: every checkpoint is complete, so it enters self-review and runs the full verification.
