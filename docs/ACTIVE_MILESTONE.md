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

## Functional review checklist

Item `retention-policy-file`, implementation revision 1, plan revision 2. The plan's section 6 holds the same flows; this is the run list.

**Automated verification (checked 2026-11-09):** the last full gate is `python3 tests/run_all.py` at head `43346d6`, `verdict: exit 0`. Nothing under `src/`, `tools/`, `tests/`, `scripts/`, `.claude/` or `.github/` has changed since, so it is current. No rerun is needed.

### Setup

- Python 3 and git. Nothing else: no network, no `gh`, no `claude`, `codex` or `ssh`, for flows 1 to 6.
- A scratch directory outside the product clone, on disk, not `/tmp`:

  ```
  S=$(mktemp -d "${TMPDIR:-$HOME}/rp-fr.XXXXXX")
  git clone --no-hardlinks <product clone> "$S/cand"
  git -C "$S/cand" remote remove origin
  export PYTHONPATH="$S/cand/src"
  touch "$S/stamp"
  ```

  Removing `origin` cuts the scratch clone off from the product clone, so nothing can push to it.
- The target, a managed repository holding only the installation record:

  ```
  mkdir -p "$S/t/.workflow-manager"
  cp <product clone>/.workflow-manager/installation.json "$S/t/.workflow-manager/"
  (cd "$S/t" && git init -q .)
  ```

### Test data

Write `$S/t/.workflow-manager/retention-policy.json` with exactly this line:

```
{"schema_version": 1, "mode": "both", "thresholds": {"finished_items": 10, "finished_folder_mib": 500, "archives": 20, "prunable_archives": 5}}
```

Its digest prefix is `5fa01cefcc02`. Take the prefix from the preview in flow 3, not from this page. Nothing else is seeded.

### Flows

Flows 1 to 6 need no network and write only under `$S`: they can run in the sandbox. Flows 7 and 8 need the full environment (a primed release cache, and the suites have failed in the Controller's sandbox before). Flow 9 looks up the release on GitHub.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git -C "$S/cand" diff --stat 0db1638ab4d0833218ad24283397a9329f3bb9bf HEAD -- src tools tests docs .github scripts .claude` | 13 files: `src/workflow_manager/cli.py`, `src/workflow_manager/retention_policy.py`, `tests/test_retention_policy.py`, `tests/test_operator_ux.py`, `docs/retention.md`, `docs/exit-codes.md`, and the bookkeeping under `docs`: `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`, `docs/ai-workflow/WORKFLOW_STATE.json`, the plan, the registry, mapping and artifacts files. Nothing under `scripts`, `.claude` or `.github` |
| 2 | `grep -c 'def test' "$S/cand/tests/test_retention_policy.py"` and `grep -n '^class Test' "$S/cand/tests/test_retention_policy.py"` | 71 tests; six classes: `TestSchema`, `TestStates`, `TestAdopt`, `TestReport`, `TestNothingElse`, `TestDocs` |
| 3 | `python3 -B -m workflow_manager adopt-retention-policy "$S/t"`, then `find "$S/t" -newer "$S/stamp"` | Exit 0. The preview prints `digest:` with its 12-character prefix, and the line `Adopt the retention policy <prefix>.`. The `find` prints nothing, so nothing was written |
| 4 | The same command with `--confirm` set to (a) `adopt the retention policy 000000000000.`, (b) `Adopt the retention policy <prefix>` with no full stop, (c) `Adopt the retention policy <prefix>.` followed by 20000 `x` characters | Each exits 2, with an `error:` line and a `next:` line on stderr. Case (c) reports `the record is larger than 16384 bytes`. `ls "$S/t/.workflow-manager"` still lists only `installation.json` and `retention-policy.json` |
| 5 | `--confirm "Adopt the retention policy <prefix>."`; then the same command without `--confirm`; then change `"finished_items": 10` to `11` in the policy file and run the command without `--confirm` again | Exit 0 and `adopted the retention policy <full digest>: mode both`. `.workflow-manager/retention-adoption.json` has five keys: `adopted_at`, `confirmation`, `policy`, `schema_version`, `sha256`. The preview then reads `state: adopted; mode both is in force`; after the edit it reads `state: changed; mode off is in force` |
| 6 | `grep -n 'retention-policy-file' "$S/cand/docs/retention.md" "$S/cand/docs/exit-codes.md"`; then `(cd "$S/cand" && python3 -B tools/check_docs.py)` | No match (grep exits 1). The checker exits 0 |
| 7 | Full environment, in `$S/cand`: apply each mutation M1 to M21 (plan section 3) with `sed` to a fresh copy, and run its named test alone from `tests/`; first the unmutated copy | Unmutated: passes. Each mutation: fails its named test. Already recorded at CP1; repeat only to confirm |
| 8 | Full environment, in `$S/cand`: `python3 tests/run_all.py --select test_retention_policy.py`, then `--select` for `test_retention_status.py`, `test_operator_ux.py` and `test_docs.py` | Exit 0 each, no `OrphanProcessError`. `--select` is evidence for this item, not the gate |
| 9 | Full environment, looks up the release on GitHub. Set `finished_items` back to 10 (the adopted content), then `python3 -B -m workflow_manager status --retention "$S/t"`; then change it to 11 again and repeat | The policy block, after the Workflow status lines and before the retention report: `retention policy: adopted, mode both (digest <prefix>, adopted <time>)`, then the thresholds line and `this Manager release only reads the policy: it sends nothing and cleans nothing`. After the change: `retention policy: changed (...); mode off is in force` with an indented `next:` line. The scratch target is not a complete Workflow repository, so the exit status is not part of the expectation |

### Known limitations (out of scope for this slice)

- Read-only. Nothing alerts, archives, removes, prunes or sends. The thresholds and modes are recorded, not applied; a later release evaluates them.
- The CLI cannot tell who runs it. The held sentence is the control, as with the Workflow's own commands, and an agent must not run `--confirm`.
- Whoever can write the repository can forge the policy and the record together. The checks catch a hand edit of one of them only.
- The record is not yet checked to be committed at `HEAD` (plan section 2.6 item 3, a later slice).
- `uninstall` deletes an adopted policy with `.workflow-manager/`; the mode is then `off`. Documented, not changed.
- Twelve Optional findings are recorded in `WORKFLOW_STATE.json` (plan and implementation review). None blocks this gate; each gets a recorded disposition at acceptance.

### Reporting

Findings go in `.ai-review/retention-policy-file/feedback/FUNCTIONAL_REVIEW.md`. Name the flow number for each.
