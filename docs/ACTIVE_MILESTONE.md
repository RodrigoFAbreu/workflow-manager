# Active Milestone

## Milestone

**In progress.** `unattended-retention-policy` (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `87d151c`, branch `milestone/unattended-retention-policy`): step A1 of issue #254, the `unattended` policy key and its own adoption sentence. Nothing runs unattended in this item.

Pull request title: `feat: add the unattended retention policy key and its own adoption sentence`.

### Checkpoints

- CP1 -- the unattended policy key and its validation: **complete**. `policy_errors` validates the closed `unattended` object (five required keys, floors and ceilings, the two cross rules); `describe_unattended` renders its settings; `tests/test_retention_unattended.py` and the vendored base module `tests/fixtures/retention_policy_base.py.txt` (blob `4b54c52`) pin the schema and the older-Manager fail-safe.
- CP2 -- the two adoption sentences, the record's kind and the adopt command: **complete**. `unattended_sentence` and its holder; `check_record` accepts either sentence for a file with the key and refuses the unattended one for a file without it; `PolicyState.unattended` is set only for an adopted record holding the unattended sentence; `apply` refuses wrong-kind and mixed confirmations before the digest check, writing nothing; `adopt-retention-policy` prints the unattended sentence for a file with the key (help text names both). Tests in `tests/test_retention_unattended.py` (`TestSentences`).
- CP3 -- the unattended text, the docs and the ROADMAP row: pending.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended.py --select test_retention_policy.py --select test_retention_status.py --select test_retention_cleanup.py`, `verdict: exit 0`. Mutations (unknown nested key accepted; vendored base accepting `unattended`) each fail the named tests.
- CP2: the same four selections (one `--select` each), each `verdict: exit 0`. Mutation checks M9-M12 are run with the final verification.

## Next action

Run `/milestone-implement unattended-retention-policy` for CP3.
