# Workflow Manager: The Unattended Retention Policy Key and Its Own Adoption Sentence (Revision 3)

`work_item_id: unattended-retention-policy` -- `governing_workflow_version: "2.2"`

Pull request title: `feat: add the unattended retention policy key and its own adoption sentence`

**Deliverable:** step A1 of the three unattended-retention steps of issue #254:
a new closed policy key `unattended`, its strict validation, a distinct
adoption sentence for it, and the text that says what an unattended adoption
would authorise and that this release does not enforce it. **Nothing runs
unattended in this item**: `retention-cleanup` keeps its per-plan `--confirm`
and its behaviour is unchanged.

**Work item type:** `process`. **Base commit:** `87d151c7feebe3a9aebe1194508ab0d5bedf7973`
(tip of `main`; Workflow 2.29.9 installed, automatic gates). **Branch:**
`milestone/unattended-retention-policy`, bound by the Controller. **Scope
source:** issue #254 (the owner's request and the design comment of 2026-11-18)
and the owner's decisions of 2026-11-18. The title is a `feat:` change: the
Manager releases a minor (`python3 tools/release/release.py check-title` reads
`valid title: feat, release impact minor`); the Controller waits for the release.
**Manager only**: no Workflow release is needed, no pin changes, nothing under
`.claude/`, `scripts/`, `.workflow-manager/` or the managed documents of
`docs/ai-workflow/` is edited. **ROADMAP:** row 50 (A1 of the three unattended
retention items, #254) is added in the style of rows 43 to 49 with status
Current, and the last checkpoint marks it Done in the item's own wording; the
Controller runs acceptance itself and will not edit the row.

Owner decisions of 2026-11-18, recorded for the later items (A2, A3) and only
*carried* by this item as the keys' documented meaning: archiving and the later
deletion of archives (prune) are to be automatic; the adopted values are
`keep_recent` 5 (engine floor 3), `ttl_days` 30 (floor 14), prune cap per run 3,
prune enabled from the first adoption (the key exists and is adopted together
with the cleanup key); the trigger is the lane heartbeat first, the Controller's
close-out later; audit and SignalHub reporting are A2. This item fixes the
floors and ranges, not the values: the owner chooses them in the file.

## 1. Verification on current main (`87d151c`)

* **The policy file is closed.** `src/workflow_manager/retention_policy.py:131`
  (`policy_errors`) refuses every top-level key but `schema_version`, `mode`
  and `thresholds`; a file with `unattended` today is `invalid`, so every
  released Manager already treats it as mode `off` (the fail-safe this item
  documents, not builds).
* **One adoption sentence.** `retention_policy.py:57` (`_SENTENCE`), `:183`
  (`sentence`), `:187` (`confirmation_holds`), `:216` (`check_record`, which
  requires the record's `confirmation` to name its policy) and `:412` (`apply`)
  know only `Adopt the retention policy DIGEST12.`. The record has the closed
  keys `schema_version`, `sha256`, `adopted_at`, `confirmation`, `policy`, so
  the record's own `confirmation` is the place that says which sentence adopted
  the digest.
* **The loader's result.** `PolicyState` (`:62`) carries `state`, `mode`,
  `problems`, `policy`, `digest`, `adopted_at`; `_load` (`:307`) returns
  `ADOPTED` only for a valid file and a valid record of the same digest.
* **Text.** `block` (`:471`) prints the status and doctor block; `describe`
  (`:357`) prints the thresholds; `cli.py:989` (`cmd_adopt_retention_policy`)
  prints the preview and the sentence; `cli.py:1017` (`cmd_retention_cleanup`)
  prints `retention_cleanup.preview_lines` (`retention_cleanup.py:412`) and
  runs only with the per-plan sentence.
* **Who reads the loaded policy.** `retention_cleanup.preflight`,
  `retention_alert` and `retention_run` read `retention_policy.load(...)` and
  use `state.mode`, `state.policy["thresholds"]` and `state.digest`; none reads
  another key, so a new key with a new optional state field changes none of
  them.
* **TRUE-FIX-NEEDED** for every requirement of the work-item prompt; none is
  already satisfied on `main`. Nothing here needs a Workflow release.

## 2. Design

One mechanism: the policy file's schema and its adoption. Principle: **a kind of
authority is a sentence of its own, bound to the digest, and the record says
which one was used**.

### 2.1 The key (CP1)

`unattended` is an optional top-level key of the policy file whose value is a
closed object with exactly these five keys, **all required** (no hidden
defaults: the numbers the later items act on are the owner's, written in the
file):

| Key | Value | Rule |
| --- | --- | --- |
| `cleanup` | boolean | archive and then remove finished items beyond `keep_recent` (A2) |
| `prune` | boolean | delete archives older than `ttl_days` (A3) |
| `keep_recent` | integer, 3 to 100000 | the Manager's own skip on top of the engine's 3 |
| `ttl_days` | integer, 14 to 3650 | the time to live of an archive |
| `prune_max_per_run` | integer, 1 to 100 | the prune cap per run |

Validation in the style of the existing keys, every problem listed by
`policy_errors`: an unknown nested key (`unknown key unattended.X`), a value
that is not an object, a missing key, a wrong type (a decimal, a string), a
boolean where an integer goes (`True` is not 3), a non-boolean where a boolean
goes, a number out of range, and a duplicate key (refused by the strict parser,
nested objects included). Two cross rules, so the key cannot contradict the
file: **at least one of `cleanup` and `prune` is true** (otherwise the key
authorises nothing), and **`mode` must be `cleanup` or `both`** (mode `off` keeps
its meaning, "nothing runs", and `notify` is alerts only). `schema_version`
stays 1: a file without the key means what it always meant, and its digest is
unchanged (a test pins it). Adding the key changes the digest, so the policy is
adopted again.

**Fail-safe for older Managers.** The file is closed, so an older Manager
refuses a file carrying `unattended` (`invalid`) and treats the mode as `off`:
it neither alerts nor cleans until it is updated. This is documented, and a
test pins that the key is the only thing that makes the file unknown to the
previous schema: it runs the **base commit's** `policy_errors` on the file, so it shows what a
released Manager does, not what a patched constant does. The base module comes
from a **vendored copy**, `tests/fixtures/retention_policy_base.py.txt`: the
exact bytes of `src/workflow_manager/retention_policy.py` at `87d151c7feebe3a9aebe1194508ab0d5bedf7973`
(git blob id `4b54c5219c3ab5517b529984980bc2e8f3e97f3a`), loaded as a scratch
module of the `workflow_manager` package (its one relative import, `.retention`,
resolves there). The test needs no Git history, because every CI test job checks
out with `fetch-depth: 1` and the base commit's objects are absent there (a
`git show` of it exits 128 in a shallow clone). A second test pins the copy: the
blob id computed from the fixture's bytes (`sha1` of `blob <size>\0<bytes>`)
equals the id above, so the fixture cannot drift; and, only when the base object
is present locally (`git cat-file -e`), it also equals `git show`'s bytes, and
otherwise that comparison is not run (the pinned id is the check that always
runs). The fixture is a `.txt` file so no tool collects or imports it as a
module; it is read-only test data, never edited.

### 2.2 The sentences and the record (CP2)

Two sentences, each bound to the policy digest:

* ordinary: `Adopt the retention policy DIGEST12.` (unchanged);
* unattended: `Adopt the unattended retention policy DIGEST12.` (the first 12
  characters of the digest and a full stop), whose pattern the ordinary one
  cannot match (the word `unattended` sits between), so neither sentence is a
  substring or an alias of the other.

The record keeps its closed keys: **no new record key**. The record's
`confirmation` is the digest-bound statement of the kind, and the loader derives
the kind from it. A file **with** the key is adopted by the unattended sentence;
a file **without** the key by the ordinary one.

* `check_record` (a record the loader refuses is never written): for a policy
  with the key, the confirmation must hold the unattended sentence or the
  ordinary one, every match naming the digest; for a policy without the key it
  must hold the ordinary one and no unattended sentence
  (`record confirmation is the unattended sentence, but the policy has no
  unattended key`).
* `PolicyState` gains `unattended: dict | None`: **the unattended settings the
  adoption authorises**, set only in the `adopted` state, when the policy has
  the key and the record's confirmation holds the unattended sentence for the
  digest; otherwise `None`. The loader's rule for a hand-written mixed record
  (both sentences, each naming the digest) is: **a record holding the unattended
  sentence for the digest authorises unattended, whatever else it holds**, so it
  reads `adopted` with `unattended` set (`apply` still refuses to write one).
  A file with the key adopted only with the
  ordinary sentence (a hand-written record; the command cannot write one) is
  `adopted`, with the file's mode and `unattended` `None`: it **authorises
  nothing unattended**, and every later reader asks `state.unattended`, never
  the policy dictionary. Every other state has `unattended` `None`.
* `apply` refuses a wrong-kind sentence before the digest check, writing nothing:
  the ordinary sentence for a file with the key (cause names the unattended
  sentence as the only adoption), the unattended sentence for a file without it,
  and any confirmation that mixes the kinds. A confirmation holding no sentence
  keeps today's cause text byte for byte.
* `workflow-manager adopt-retention-policy` prints, for a file with the key, the
  unattended sentence (and a line that only that sentence adopts the file) and
  for a file without it exactly today's output.

### 2.3 What is printed, and what is not enforced (CP3)

A single helper, `retention_policy.describe_unattended`, renders the unattended lines, used by the
`status`/`doctor` block, the `adopt-retention-policy` preview and the
`retention-cleanup` preview, so the three agree:

* a file with the key in the `adopted` state with `unattended` set:
  `  unattended retention: adopted with the unattended sentence: cleanup on,
  prune on, keep 5 recent, ttl 30 days, at most 3 prunes per run`;
* adopted with the ordinary sentence only: the file declares it, the adoption
  authorises nothing unattended, and the next step is the adopt command;
* any other state whose file is valid (`not-adopted`, `changed`,
  `record-invalid`): what an unattended adoption would authorise;
* in every case the line `  not enforced by this release: nothing runs
  unattended, and retention-cleanup still needs its per-plan --confirm`.

No such line is printed for a file without the key: every existing output stays
byte-identical (existing tests and a golden pin it). `retention_cleanup.
preview_lines` takes an optional `extra` list, placed before the `next:` line
(and, for the "nothing to do" outputs, after the whole output including the age
note that the thresholds branch appends, at `retention_cleanup.py:420-431`), so the `next:` and the
by-hand lines keep their positions; the plan digest, the plan and the confirmed
run are untouched.

`docs/retention.md` documents the five keys and their rules, the two sentences
and the record's kind, the fail-safe for older Managers, the states, and that the
key is **not yet enforced**. Docs must not name internal ids (a test pins it).

## 3. Failure-only mutations

Every test is run unmutated first, with one `--select` per file, because the
flag takes one spec each (`python3 tests/run_all.py --select
test_retention_unattended.py --select test_retention_policy.py --select
test_retention_cleanup.py --select test_retention_status.py`), then each mutation
below on a scratch copy outside the repository, checked with the selection of the
file that holds the named test (`test_retention_unattended.py` for every
mutation of the new key, sentences and text; the other three for the existing
behaviour they pin); the expectation is "the named tests are among the failures",
never a full failing set, and the unmutated tree exits 0.

| # | File and change | Must fail |
| --- | --- | --- |
| M1 | `retention_policy.py`: do not refuse an unknown nested key | the nested-key test |
| M2 | accept a boolean for `keep_recent` | the boolean-as-integer test |
| M3 | `keep_recent` floor 2 | the floor test (2 refused, 3 accepted) |
| M4 | `ttl_days` floor 13 | the floor test (13 refused, 14 accepted) |
| M5 | `prune_max_per_run` ceiling 101 | the ceiling test (100 accepted, 101 refused) |
| M6 | accept a non-boolean for `prune` | the wrong-type test |
| M7 | drop the mode rule | the mode test |
| M8 | drop the "needs cleanup or prune" rule | the no-authority test |
| M9 | `apply`: accept the ordinary sentence for a file with the key | the wrong-kind refusal test (and the no-write proof) |
| M10 | `apply`: accept the unattended sentence for a file without the key | the wrong-kind refusal test |
| M11 | `_load`: authorise unattended for an ordinary-only record | the ordinary-adoption test |
| M12 | the unattended pattern ignores the digest | the wrong-digest test |
| M13 | `block`: drop the unattended lines | the block golden |
| M14 | drop the "not enforced" line | the block, adopt-preview and cleanup-preview goldens |
| M15 | `cmd_retention_cleanup`: omit the extra lines | the cleanup-preview golden |
| M16 | `tests/fixtures/retention_policy_base.py.txt`: make `policy_errors` accept `unattended` | the fail-safe test and the blob-id pin |

Every refusal has its own **no-write proof**: the existing `refused` helper
compares `tree_hash` of the whole scratch repository before and after, and a new
case runs it for each of the wrong-kind refusals and the schema refusals reached
through `adopt-retention-policy`.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The unattended policy key and its validation | - | 2 | 1 |
| CP2 | The two adoption sentences, the record's kind and the adopt command | CP1 | 2 | 1 |
| CP3 | The unattended text, the docs and the ROADMAP row | CP2 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the unattended policy key and its validation

**Files:** `src/workflow_manager/retention_policy.py`, `tests/test_retention_unattended.py`, `tests/fixtures/retention_policy_base.py.txt`.

The constants and the nested validation of section 2.1 in `policy_errors`;
`describe_unattended`; the module docstring says nothing runs unattended.
`tests/test_retention_unattended.py` (new, reusing the scratch base of
`tests/test_retention_policy.py`): a valid file; each refusal of 2.1 (unknown
nested key, not an object, missing key for each of the five, wrong type, boolean
as integer, boolean expected, each floor and ceiling at both sides, duplicate
nested key through the loader, the two cross rules, every problem listed); the
digest of a file without the key unchanged; a file with the key is `invalid` and
mode `off` under the base commit's `policy_errors` (the fail-safe, run from the
vendored copy `tests/fixtures/retention_policy_base.py.txt`, not a patched
constant and not `git show`, so it runs in a `--depth 1` checkout); the
fixture's blob id equals `4b54c5219c3ab5517b529984980bc2e8f3e97f3a`, and the
fail-safe test still fails if the copy is changed to accept `unattended`. The key does not alter any
existing test's output.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the two adoption sentences, the record's kind and the adopt command

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_unattended.py`.

Section 2.2: the unattended sentence and its holder, `check_record`'s kind rule,
`PolicyState.unattended`, `_load`, `apply`'s wrong-kind refusal and the command's
preview and adoption output; the command's `--help` and `--confirm` help name
both sentences. Tests: the sentence strings and that neither sentence matches the
other's pattern; adoption of a file with the key by the unattended sentence
writes exactly the record (and `state.unattended` is the file's object); the
wrong-kind refusals (each with the no-write proof and `error:`/`next:`); a
wrong-digest unattended sentence; a mixed confirmation refused by `apply`, and
a hand-written mixed record read through the loader as `adopted` with
`unattended` set; a hand-written record
with the ordinary sentence for a file with the key reads `adopted`, the file's
mode, `unattended` `None`; a record with the unattended sentence for a file
without the key is `record-invalid`; the old preview and adoption output for a
file without the key is byte-identical.
<!-- /CP2 -->

<!-- CP3 -->
### CP3 -- the unattended text, the docs and the ROADMAP row

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/retention_cleanup.py`, `src/workflow_manager/cli.py`, `docs/retention.md`, `tests/test_retention_unattended.py`.

Section 2.3: the shared helper and its use in `block`, the adopt preview and
`retention-cleanup`'s preview (through `preview_lines`' `extra`), goldens for
each state (adopted with the unattended sentence, adopted ordinary-only, not
adopted, changed, record-invalid, no key at all), a cleanup-preview golden in
the age-threshold case with the age note present (`extra` after it), and that the confirmed run and
the plan digest are untouched. The page `docs/retention.md` documents the keys,
the two sentences, the fail-safe and the not-yet-enforced status, with tests that
pin its needles and that it names no internal id. Row 50 is added to
docs/ROADMAP.md (status Current, in the style of rows 43 to 49; the "What's next"
sentence is left as the neighbours leave it) and, as the last act of this
checkpoint, marked Done in the item's own wording; the file docs/ROADMAP.md is
implementation-excluded by design and is not a deliverable.
<!-- /CP3 -->

## 5. Functional review

Flows are offline greps and diffs in a clone `S/cand` of the branch head
(`S=$(mktemp -d "$HOME/.cache/ur-fr.XXXXXX")`, `git clone --no-hardlinks <product
clone> $S/cand`); they write nothing into the product clone. Flow 7 is marked
"(needs the full environment)": it needs the primed release cache that
`tests/run_all.py` needs. Every grep excludes `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --name-status 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- src tests tools .github .claude scripts .workflow-manager` | only `src/workflow_manager/retention_policy.py`, `src/workflow_manager/retention_cleanup.py`, `src/workflow_manager/cli.py` modified and `tests/test_retention_unattended.py` and `tests/fixtures/retention_policy_base.py.txt` added; nothing under `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/` |
| 2 | `cd $S/cand && git diff --name-status 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- docs` | `docs/retention.md` and `docs/ROADMAP.md` modified, plus this item's own planning and bookkeeping files (plan, registry, artifacts, mapping added; `docs/ai-workflow/WORKFLOW_STATE.json` and `docs/ACTIVE_MILESTONE.md` modified); no other page |
| 3 | `cd $S/cand && git diff --exit-code 87d151c7feebe3a9aebe1194508ab0d5bedf7973 HEAD -- docs/exit-codes.md docs/verify.md docs/update.md README.md tests/parallel/resources.json src/workflow_manager/retention_run.py src/workflow_manager/retention_alert.py src/workflow_manager/retention.py` | exit 0 (untouched: nothing executes unattended, no existing mechanism changed) |
| 4 | `cd $S/cand && grep -c "Adopt the unattended retention policy" docs/retention.md src/workflow_manager/retention_policy.py` | each file holds the sentence at least once; and `grep -n "unattended" docs/retention.md` shows the five keys, the two sentences, the older-Manager fail-safe and the not-yet-enforced status |
| 5 | `cd $S/cand && grep -n "unattended-retention-policy" docs/retention.md docs/exit-codes.md` | no match (docs name no internal id) |
| 6 | `cd $S/cand && grep -n "^| 50 " docs/ROADMAP.md` | one row naming #254 and A1, status Done in the item's own wording; row 49 and the rows above are unchanged (`git diff` of the file shows only added lines) |
| 7 | (needs the full environment) in `$S/cand`, and again after `git clone --depth 1 --no-hardlinks file://<S>/cand <S>/shallow` for the first selection only: `python3 tests/run_all.py --select test_retention_unattended.py`, then one run each with `--select test_retention_policy.py`, `--select test_retention_cleanup.py` and `--select test_retention_status.py` | all four exit 0 (and the first one in the `--depth 1` clone, where the fail-safe test passes without the base commit); with mutation M9 of section 3 applied in a scratch copy the first selection exits 1 and the wrong-kind refusal test is among the failures |
| 8 | `python3 tools/release/release.py check-title "feat: add the unattended retention policy key and its own adoption sentence"` | `valid title: feat, release impact minor` |

## 6. Risks

* **A later item reads the policy dictionary instead of `state.unattended`** and
  so honours an ordinary-only adoption. Mitigated: the module docstring and the
  docs say the one question is `state.unattended`, and a test pins that the
  ordinary-only record gives `None`.
* **A hand-written ordinary-only record for a file with the key reads
  `adopted`** (it is a valid adoption of the ordinary settings). It authorises
  nothing unattended and the block says so; making it `record-invalid` would
  also disable the ordinary mode for a file the owner adopted in good faith.
* **Cross rules.** `mode` must be `cleanup` or `both` and one of `cleanup` and
  `prune` must be true; both are conservative (a file that would be accepted
  later can be loosened in a minor release, a file already adopted cannot be
  tightened), and both are documented.
* **The one way an existing valid record changes state.** For a policy without
  the key, `check_record` refuses a confirmation that holds an unattended
  sentence. A record written by an earlier release whose free-form `--confirm`
  held the unattended sentence beside the ordinary one would turn from `adopted`
  to `record-invalid`, and the mode to `off`. That is very unlikely, it fails safe,
  and it is the only record that changes state; it is meant, and the docs
  and this section say so.
* **The policy size limit** (4096 bytes) leaves ample room for the five keys.

## 7. Open decisions

None for the owner: the values (5, 30, 3, prune on) are the owner's decisions of
2026-11-18 and are chosen in the policy file, not in code. Two design choices of
this plan are marked for the reviewers: all five nested keys are required (no
hidden defaults), and `unattended` needs `mode` `cleanup` or `both`.
`docs/TECHNICAL_DECISIONS.md` does not exist in this repository.
