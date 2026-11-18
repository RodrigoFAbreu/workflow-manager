# Active Milestone

## Milestone

**In progress.** `unattended-retention-policy` (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `87d151c`, branch `milestone/unattended-retention-policy`): step A1 of issue #254, the `unattended` policy key and its own adoption sentence. Nothing runs unattended in this item.

Pull request title: `feat: add the unattended retention policy key and its own adoption sentence`.

### Checkpoints

- CP1 -- the unattended policy key and its validation: **complete**. `policy_errors` validates the closed `unattended` object (five required keys, floors and ceilings, the two cross rules); `describe_unattended` renders its settings; `tests/test_retention_unattended.py` and the vendored base module `tests/fixtures/retention_policy_base.py.txt` (blob `4b54c52`) pin the schema and the older-Manager fail-safe.
- CP2 -- the two adoption sentences, the record's kind and the adopt command: pending.
- CP3 -- the unattended text, the docs and the ROADMAP row: pending.

### Verification state

- CP1: `python3 tests/run_all.py --select test_retention_unattended.py --select test_retention_policy.py --select test_retention_status.py --select test_retention_cleanup.py`, `verdict: exit 0`. Mutations (unknown nested key accepted; vendored base accepting `unattended`) each fail the named tests.

## Next action

Run `/milestone-implement unattended-retention-policy` for CP2.
