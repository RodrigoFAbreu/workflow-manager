# Workflow Manager: The Retention Policy File: Schema, Strict Loader, Adoption (Revision 2)

`work_item_id: retention-policy-file` -- `governing_workflow_version: "2.2"`

**Deliverable:** a retention policy file a managed repository's owner writes
and adopts, a strict loader that returns mode `off` for everything but a file
the owner adopted unchanged, the Manager command that adopts it, and a
read-only line of its state in the retention section (roadmap row 36; issues
#90 and RodrigoFAbreu/workflow#84). Nothing alerts, nothing is sent, nothing is
cleaned in this slice.

**Work item type:** `process`. **Base commit:** `0db1638`
(`0db1638ab4d0833218ad24283397a9329f3bb9bf`, tip of `main`, Manager 1.14.8;
Workflow 2.29.1 installed, automatic gates). **Branch:**
`milestone/retention-policy-file`. **Scope source:** the owner's decisions of
2026-11-03 and 2026-11-05 on #90 and wf#84 (mode `off | notify | cleanup |
both`, thresholds, an owner-adopted policy file, the gate policy as the
precedent). One mechanism: the retention policy file (schema, strict loader,
adoption). Two checkpoints. This is new command surface: after the merge a
Manager release (`feat`, minor) follows; CP2 gives the bookkeeping.

## 1. Investigation (done at `0db1638`, before any design)

### 1.1 How the gate policy works

* **Stored.** `docs/ai-workflow/GATE_POLICY.json`: the owner's committed file,
  in no release payload (a new installation has none). The adoption record
  lives in the Workflow's own `WORKFLOW_STATE.json` (`gate_policy_adoption`,
  `gate_policy_floor`).
* **Validated.** `workflow_gate_policy.policy_errors`: a closed schema, an
  unknown key refused at every level, `schema_version` exactly 1, booleans
  that are not integers, lists without repeats. `read_policy_file` never
  raises; a symlink, a non-regular file, unreadable bytes or invalid JSON is
  `valid: false` with its errors. The digest is the sha256 of the canonical
  bytes (sorted keys, compact separators, UTF-8).
* **Adopted.** `/adopt-gate-policy` (user-only): step 1 prints the digest and
  its first 12 hex characters; step 2 runs only when the user's own turn
  contains the literal `gate_policy` and that prefix
  (`validate_gate_policy_confirmation`). It refuses a file that differs from
  `HEAD`'s copy, records `{sha256, adopted_at, confirmation, policy body,
  history, lowered}`, makes one commit with a trailer and validates it.
* **Tamper detection and fail-closed.** The file is only a proposal: the
  effective policy is the stricter of the adopted body, the recorded floor and
  the file, so an edit can only tighten. The record is checked for
  self-consistency (`adoption_record_errors`: the digest of the body, the
  confirmation re-validated against it) and by the chain of commits that
  changed it, which survives a squash merge. A broken chain gives
  `provenance_failed`, every gate human.

### 1.2 What a retention policy reuses, and what it cannot

| Reused | Not reused, and why |
| --- | --- |
| A closed schema read strictly; an unknown key, a wrong type, a bool for an integer, an out-of-range number refused | The record in `WORKFLOW_STATE.json` and the commit chain: that file is the Workflow's, the Manager never writes it, and the Manager makes no commits |
| The file is a proposal and the record is the authority; the effective policy is the adopted body only while the file's digest equals the record's | Tighten-only floors: retention modes are not an ordered strictness, so any change of the file needs a new adoption, never a silent effect |
| The digest of canonical bytes; the record carries the body and the confirmation, both re-validated at every load | `/adopt-...` as a Workflow payload command: payload commands ship with a Workflow release, and this policy is the Manager's (owner, 2026-11-05) |
| A confirmation bound to the digest, so a sentence for one policy never authorizes another | |
| Every failure falls back to the safe value (mode `off`) | |

### 1.3 What the retention view measures

`retention.py` validates a report whose numbers are integers from 0 to
`INT_MAX` (2**63 - 1). The ones a threshold can use, and their units:

* `totals.finished`: finished work items past the 3 most recent (items);
* `totals.finished_folder_bytes`: bytes of their untracked review folders;
* `totals.archives`: archives in the store, finished or not (items);
* `totals.prunable`: archives older than `ttl_days` (items). `ttl_days`
  (default 30, at most 3650) and `keep_recent` (3) belong to the Workflow
  script; the Manager passes neither, and this policy does not carry them.

`PATH_LIMIT` (4096) bounds the paths the report carries. The policy carries no
path, so it uses none; its file is capped at 4096 bytes by the same figure, and
the target path printed in a message is the one the existing code already
prints.

### 1.4 Where the file lives

The installation record sorts a managed repository's files into `managed`
(payload files: replaced on update, compared by `verify`), `generated` (written
once) and `merged`. A path in none of them is the repository's own: `verify`
ignores it, `update` never rewrites it (it only refuses a release path that
collides with an unrecorded file), and `uninstall` removes only managed files
and then `.workflow-manager/`.

* `docs/ai-workflow/RETENTION_POLICY.json` would sit beside the gate policy,
  but that directory is the Workflow's: a later Workflow release (the first
  proposal on wf#84 was a Workflow-side file) could ship the same name and
  `update` would refuse it as a path in use.
* **Decision: `.workflow-manager/retention-policy.json` (the owner's proposal,
  committed by the owner) and `.workflow-manager/retention-adoption.json` (the
  Manager's record, committed by the owner).** The Manager's own directory, which
  no Workflow release writes, next to the tracked `installation.json`. Neither
  is managed, so `verify` and `update` ignore them. `uninstall` deletes the
  directory and so both: the policy returns to `off`, the safe direction, and
  the page says so. Changing `uninstall` is out of scope.

### 1.5 How the Manager adopts it

A new subcommand, `workflow-manager adopt-retention-policy TARGET [--confirm
TEXT]`. No existing command fits: `/adopt-gate-policy` adopts the gate policy
into Workflow state. A CLI cannot be user-only by construction, as the
Workflow's commands are by a flag the harness enforces; its control is the same
literal sentence, bound to the digest the preview prints, which no earlier turn
or earlier policy can supply. The page tells agents not to run it. Without
`--confirm` it is a read-only preview.

## 2. Design

### 2.1 The schema (`schema_version` 1, closed)

```json
{"schema_version": 1, "mode": "off",
 "thresholds": {"finished_items": 10, "finished_folder_mib": 500,
                "archives": 20, "prunable_archives": 5}}
```

| Key | Type and bounds | Meaning, evaluated by a later row |
| --- | --- | --- |
| `schema_version` | the integer 1 | a newer file is refused, so an older Manager falls back to `off` |
| `mode` | `off`, `notify`, `cleanup` or `both` (lower case, exact) | `off`: nothing; `notify`: tell the owner; `cleanup`: clean up silently; `both`: both |
| `thresholds.finished_items` | integer 1 to 100000 | `totals.finished` at or above it |
| `thresholds.finished_folder_mib` | integer 1 to 1048576 (1 TiB) | `totals.finished_folder_bytes` at or above this many MiB (1 MiB = 1048576 bytes, compared exactly) |
| `thresholds.archives` | integer 1 to 100000 | `totals.archives` at or above it |
| `thresholds.prunable_archives` | integer 1 to 100000 | `totals.prunable` at or above it |

`thresholds` and each key are optional; a missing key is not checked. Zero is
refused (it would cross always). A mode other than `off` needs at least one
threshold. `off` may keep thresholds. No notification target and no list of
permitted cleanup operations is in version 1: the sender is the Controller
lane's SignalHub interface, an owner decision not yet taken, and which
operations may run unattended belongs to the cleanup row. Closed keys mean a
later row raises `schema_version`, and an older Manager refuses that file.

### 2.2 The strict loader, `src/workflow_manager/retention_policy.py`

* `load(target) -> PolicyState` never raises and never writes. It first checks
  that `.workflow-manager` is not a link, then reads each of the two files with
  `O_NOFOLLOW`, requires a regular file, reads at most 4096 bytes for the policy
  (16384 for the record) and refuses a larger one without parsing it. The two
  link checks are separate mechanisms: the directory check does not rely on
  `O_NOFOLLOW`, which only covers the final path component.
* **Links and non-regular files.** `.workflow-manager` a link: state `invalid`,
  problem "`.workflow-manager` is a link", mode `off`, whatever the files hold
  (neither is read). The policy file a link or not a regular file: `invalid`.
  The record a link or not a regular file, beside a valid policy file:
  `record-invalid` (beside no policy file: `file-missing`, as for any record).
* A file is refused for: invalid UTF-8 or a lone surrogate, invalid JSON, a
  duplicate key at any level, `NaN`/`Infinity`, nesting too deep for the
  decoder, a non-object, an unknown key at either level, a wrong type (a bool
  or float for an integer, a string for a number), an out-of-range number, an
  unknown mode, and the rules of 2.1. `problems` lists every one found, each
  value shown through `retention._shown` (its `repr`, cut at 40 characters),
  so nothing reaches a terminal raw.
* The record is `{schema_version: 1, sha256, adopted_at, confirmation,
  policy}`, closed. It is refused unless `sha256` is the digest of the canonical
  bytes of `policy`, `policy` passes the schema, and `confirmation` holds for
  that digest.
* **One record check, two callers.** `check_record(record) -> list[str]`
  returns the problems of a record: its serialized bytes (the exact bytes
  apply would write) over 16384, a lone surrogate anywhere in it, the closed
  keys, the digest, the confirmation. `load` runs it on what it reads; the
  adoption command (2.3) runs it on the record it has built, before writing.
  So a record the loader would refuse is never written.
* States and the mode in force (only `adopted` carries a mode other than `off`):

| State | When | Mode in force |
| --- | --- | --- |
| `absent` | no policy file and no record | `off` |
| `file-missing` | a record, no policy file | `off` |
| `invalid` | the policy file is refused | `off` |
| `not-adopted` | a valid file, no record | `off` |
| `record-invalid` | a valid file, a refused record | `off` |
| `changed` | a valid file, a valid record, different digests | `off` |
| `adopted` | a valid file and a valid record with equal digests | the file's `mode` |

### 2.3 The adoption command

`adopt-retention-policy TARGET`: the target must be managed (else the usual
refusal, exit 2). It loads the file; an absent or invalid file is a refusal
with its problems. **Preview** (no `--confirm`, exit 0, writes nothing): the
path, the digest and its first 12 characters, the mode and thresholds, the
current state, and the sentence the confirmation must contain:

```
Adopt the retention policy 1a2b3c4d5e6f.
```

**Apply** (`--confirm TEXT`): after whitespace collapse and ignoring case, every
match of `adopt the retention policy ([0-9a-f]{12})\.` in `TEXT` must equal the
digest's first 12 characters, and there must be one; other words are allowed.
Anything else is a refusal that writes nothing. It then builds the exact record
and passes it through `check_record` (2.2): a `--confirm` that makes the
record over 16384 bytes, or that holds a lone surrogate (on Linux, argv bytes
that are not UTF-8 reach Python as surrogates), is refused, exit 2, nothing
written. It also refuses, exit 2, when `.workflow-manager` is a link or the record
path exists and is not a regular file. Only then it writes the record
atomically (a temporary file in the same directory, `fsync`, `os.replace`; the
temporary file is removed on any failure) and prints the digest, the mode, the
path to commit, and that nothing is archived, removed, pruned or sent by this
release. Re-adopting a changed file replaces the record. It never commits and
never touches the policy file, the installation record or Workflow state. A
file error exits 1 with the system's message, as every other command does.

### 2.4 The read-only report

The smallest honest surface is the existing retention section: `status
--retention` and `doctor --retention` print, before the script's report, a
block from `load`, **only when the state is not `absent`**. With no file and no
record the output is byte-identical to today's, which is the default
("nothing alerts, nothing cleans") and costs no new line. The block never
changes an exit code and never starts the script by itself:

```
retention policy: adopted, mode both (digest 1a2b3c4d5e6f, adopted 2026-11-10T12:00:00Z)
  thresholds: finished items 10, finished folders 500 MiB, archives 20, prunable archives 5
  this Manager release only reads the policy: it sends nothing and cleans nothing
```

Any other state prints `retention policy: STATE TEXT; mode off is in force`,
up to 5 problems then `and N more`, and one **indented** `  next:` line, like the retention section's own
(`status` keeps exactly one unindented final `next:` line, so the block adds
none) (`workflow-manager adopt-retention-policy TARGET` for `not-adopted`, `changed` and
`record-invalid`; fix the file named for `invalid`; restore or remove the
record for `file-missing`). `cli.py` prints it from one helper used at both
call sites, before `retention.section`. Where the block shows `next:` it is the
indented line above; the adopted block has none.

### 2.5 Documentation

One section "Retention policy" in `docs/retention.md` (the file, the schema
table, the states, the adoption sentence, the default, what this release does
not do) and a row in `docs/exit-codes.md` for the new command. The command is also added to
`cli.py`'s usage docstring and to `tests/test_operator_ux.py`'s
`TARGET_COMMANDS`, so its inventory test requires a summary in the top-level
help and a description with the exit codes. The page names no
internal milestone id; `tools/check_docs.py` passes unchanged (its command
check parses every fenced command of the page against the parser).

### 2.6 Not in this slice (the next rows, not added now)

1. The alert evaluation: thresholds against the retention report, and the
   warning in `verify`/`doctor`.
2. The notification sender: needs the Controller lane's SignalHub interface, an
   owner decision.
3. The automatic cleanup run: only under an adopted policy, and it must also
   require the policy file and the record to be committed at `HEAD`, say which
   operations may run unattended, and keep a record of what it did.
4. Policy fields for the time to live and the number of recent items kept.

`archive`, `remove`, `prune`, `retention.py` and the Workflow repository are unchanged.

## 3. Failure-only mutations

Each on a fresh copy of the candidate, one at a time, the named test or class
run alone from `tests/` with `python3 -B -m unittest`. The unmutated copy
passes; each mutation must make the named test fail.

| # | Mutation | Must fail |
| --- | --- | --- |
| M1 | the loader ignores an unknown key | `TestSchema` unknown top-level and threshold key |
| M2 | a bool is accepted as an integer | `TestSchema` bool threshold |
| M3 | the lower bound 1 becomes 0 | `TestSchema` zero threshold |
| M4 | a mode other than `off` is valid without a threshold | `TestSchema` mode without threshold |
| M5 | the size cap is removed | `TestSchema` oversize policy and oversize record |
| M6 | a duplicate key is accepted | `TestSchema` duplicate key |
| M7 | `O_NOFOLLOW` is dropped from the file read | `TestSchema` symlinked policy and symlinked record |
| M8 | `changed` reports mode in force | `TestStates` changed file is off |
| M9 | a record whose `sha256` is not the body's is accepted | `TestStates` tampered record |
| M10 | a record whose confirmation does not hold is accepted | `TestStates` tampered confirmation |
| M11 | `absent` prints a block | `TestReport` default is byte-identical |
| M12 | the block prints a problem value raw | `TestReport` control character |
| M13 | the confirmation compares no digest | `TestAdopt` wrong prefix |
| M14 | the full stop of the sentence is optional | `TestAdopt` sentence without the full stop |
| M15 | the preview writes the record | `TestAdopt` preview writes nothing |
| M16 | a refusal writes before it checks | `TestAdopt` each refusal's no-write proof |
| M17 | the failed-replace path keeps the temporary file | `TestAdopt` failed write leaves the tree unchanged |
| M18 | `section` also runs another script command | `TestNothingElse` one script call only |
| M19 | the `.workflow-manager` link check is removed (load and apply) | `TestSchema` symlinked directory; `TestAdopt` apply refuses to write through a linked directory |
| M20 | apply skips the pre-write `check_record` | `TestAdopt` oversize confirmation and lone-surrogate confirmation |
| M21 | the policy block prints an unindented `next:` line | `TestReport` a policy state adds no unindented `next:` line |

## 4. Tests, `tests/test_retention_policy.py`

* **TestSchema**: table-driven refusals for every rule of 2.1 and 2.2, with the
  exact `problems`; a valid file for each mode; the bounds at 1 and at the
  maximum, and one over each; a symlinked policy, a symlinked record, a record
  or policy that is a directory, and a symlinked `.workflow-manager`, each with
  the state 2.2 names.
* **TestStates**: one case per state of 2.2 with its mode in force; a file edited
  after adoption is `changed` and `off`; a deleted file is `file-missing`.
* **TestAdopt** (real CLI, scratch managed repository, no network): preview and
  every refusal (not managed, absent file, invalid file, no `--confirm` text, no
  sentence, another digest's sentence, wrong prefix, no full stop, two
  sentences with different digests, a `--confirm` that is valid but over 16 KB, a
`--confirm` with a lone surrogate, a linked `.workflow-manager`, a record path
that is a directory) leave `tree_hash` unchanged and exit 2; a held
  sentence writes exactly the record with exactly its keys; re-adoption after a
  change; a failed `os.replace` leaves the tree unchanged and exit 1.
* **TestReport**: with a stub script, `status --retention` and `doctor
  --retention` print the block for each state before the script's report, the
  exit code equals the code without the file, and the output of every
  non-adopted-or-absent case names `mode off is in force`; with no file the
  output equals today's byte for byte; a policy state adds no unindented `next:`
line, so `status` keeps its single final one.
* **TestNothingElse**: with an adopted `both` policy the stub script's marker
  records exactly one call (`report --json`), and no archive, folder or file
  outside the record changes: this slice sends and cleans nothing.
* **TestDocs**: the section, the exit-codes row and the `--help` text exist; the
  page names no work item id. The top-level help carries a summary for
  `adopt-retention-policy` and its own help a description with "Exit", and the
  usage docstring lists it (also pinned by `test_operator_ux.py`'s extended
  inventory).

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The policy file: schema, loader, adoption, report, docs | - | 3 | 1 |
| CP2 | Bookkeeping and the release | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the policy file: schema, loader, adoption, report, docs

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_policy.py`, `tests/test_operator_ux.py`, `docs/retention.md`, `docs/exit-codes.md`.

Sections 2 and 4. Then, in order: the mutations of section 3 in scratch copies,
`python3 tools/check_docs.py`, `python3 tests/run_all.py --select
test_retention_policy.py`, `--select test_retention_status.py`, `--select
test_operator_ux.py` and `--select test_docs.py`, and the full gate `python3 tests/run_all.py`. The evidence goes
in the milestone record at CP2.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping and the release

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 36 of `docs/ROADMAP.md` is added by this plan as Current and is Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the
mutation results. Both stay excluded at both stages. No version is edited: the
pull-request title is `feat: add the retention policy file and its adoption
command` (checked with `python3 tools/release/release.py check-title`), and the
release workflow computes the next minor from the tags after `main`'s run is
green (`docs/RELEASING.md`). After it publishes, the orchestrator's follow-up
`docs:` pull request, as for the earlier Manager releases, adds the new row to
`docs/release-history.md` and moves the `Last checked with:` stamps of
`docs/retention.md` and `docs/exit-codes.md` to the new Manager version; a comment
on #90 records the slice and lists section 2.6 as the next rows.
<!-- /CP2 -->

## 6. Functional review

Flows 1 to 6 write nothing into the product clone and need no network: they run
in a clone `S/cand` of the branch head (`S=$(mktemp -d "$TMPDIR/rp-fr.XXXXXX")`,
`git clone --no-hardlinks <product clone> $S/cand`). `S/t` is a new `git init`
directory holding a copy of this repository's `.workflow-manager/installation.json`
and a policy file. Flows 7 and 8 need the full environment and run last.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat 0db1638ab4d0833218ad24283397a9329f3bb9bf HEAD -- src tools tests docs .github scripts .claude` | `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_policy.py`, `tests/test_operator_ux.py`, `docs/retention.md`, `docs/exit-codes.md`, and the expected bookkeeping under `docs`: `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`, `docs/ai-workflow/WORKFLOW_STATE.json`, the plan, registry, mapping and artifacts files, and the functional-review checklist; nothing in `retention.py`, `scripts/`, `.claude/` or `.github/` |
| 2 | `grep -c 'def test' $S/cand/tests/test_retention_policy.py` and `grep -n '^class Test' $S/cand/tests/test_retention_policy.py` | the six classes of section 4 are present, with at least 45 tests |
| 3 | in `S/t` with a valid `mode: both` policy: `PYTHONPATH=$S/cand/src python3 -B -m workflow_manager adopt-retention-policy $S/t` | exit 0, the preview with the digest, its 12-character prefix and the sentence; no new file: `touch $S/stamp` before the run, then `find $S/t -newer $S/stamp` prints nothing |
| 4 | the same with `--confirm "adopt the retention policy 000000000000."`, then `--confirm "Adopt the retention policy <prefix>"` (no full stop), then `--confirm` holding the right sentence plus 20000 characters | each exit 2 with `error:` and `next:`, nothing written |
| 5 | the same with `--confirm "Adopt the retention policy <prefix>."`, then edit one threshold and run `adopt-retention-policy $S/t` again | exit 0 and `.workflow-manager/retention-adoption.json` with five keys; after the edit the preview says `changed` and no longer `adopted` |
| 6 | `grep -n 'retention-policy-file' $S/cand/docs/retention.md $S/cand/docs/exit-codes.md`; `python3 $S/cand/tools/check_docs.py` | no match in the first; the checker exits 0 |
| 7 | (needs the full environment) in `$S/cand`, apply M1 to M21 with `sed` in scratch copies and run the named tests; first the unmutated copy | the unmutated copy: OK; each mutation: FAILED |
| 8 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_retention_policy.py`, `--select test_retention_status.py`, `--select test_docs.py` | exit 0 each, no `OrphanProcessError` |

## 7. Risks

* The CLI cannot enforce user-only; a held sentence is the control, as with the
  Workflow's own commands. Section 2.6 item 3 adds the committed-at-`HEAD` check
  before any unattended run uses the policy.
* Whoever can write the repository can forge the file and the record together;
  the checks catch a hand edit of one. The gate policy's commit chain is not
  reused (section 1.2).
* `uninstall` deletes an adopted policy with `.workflow-manager/`; the result is
  `off`, documented, not changed.

## 8. Open decisions

None in this slice; the notification target (2.6 item 2) is the owner's.
