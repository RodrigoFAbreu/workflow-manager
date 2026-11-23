# Workflow Manager: The Adoption Wording of the Unattended Retention Policy and Its Pins (Revision 2)

`work_item_id: unattended-adopt-wording` -- `governing_workflow_version: "2.2"`

Pull request title: `fix: tell the adopt preview to adopt again with the unattended sentence instead of running itself`

**Deliverable:** the three points of issue #259 (the optional findings of the
implementation reviews of the unattended retention policy item), one
mechanism: what the adopt output and the documentation say about adopting
again, and the tests that pin it. No new behaviour: one message in the
`adopt-retention-policy` preview, one test pin and one documentation sentence.

**Work item type:** `process`. **Base commit:**
`87c946035e6045b337b7bf09d764a4a9c5b152c8` (tip of `main`; Workflow 2.29.10
installed in this repository's record, automatic gates, default "2.2").
**Branch:** `milestone/unattended-adopt-wording`, bound by the Controller.
**Scope source:** issue #259 (no comments) and the work-item prompt. The title
is a `fix:` change because the text the adopt command prints changes in `src/`:
the Manager releases a patch (`python3 tools/release/release.py check-title`
reads release impact patch); the Controller waits for the release.
**Manager only**: no Workflow release, no pin, nothing under `.claude/`,
`scripts/`, `.workflow-manager/` or the managed documents of `docs/ai-workflow/`
is edited. **ROADMAP:** row 53 is added in the style of rows 50 to 52 with
status Current, and the last checkpoint marks it Done; the Controller runs
acceptance itself and will not edit the row. Nothing in this item runs
`retention-cleanup --unattended` or any archive, remove or prune command; the
tests drive scratch repositories only.

## 1. Verification of the three points on current main

1. **Confirmed.** `unattended_lines` in `src/workflow_manager/retention_policy.py`
   (line 259) has three heads. For a record that exists and is `adopted` with
   no unattended authorisation (`state.state == ADOPTED`, `state.unattended`
   is `None`; the file carries the key and was adopted only with the ordinary
   sentence) the head is, at lines 269 to 272, "unattended retention: the file
   declares it, but the adoption authorises nothing unattended; only the
   unattended sentence authorises it: run `workflow-manager
   adopt-retention-policy TARGET`". Its callers: `block` (lines 647 and 654,
   which `status` and `doctor` print), `src/workflow_manager/cli.py:1058` (the
   `retention-cleanup` preview) and `src/workflow_manager/cli.py:1000` (the
   `adopt-retention-policy` preview, `cmd_adopt_retention_policy`). In the
   adopt preview the operator is already running that command, and the lines
   printed after it (cli.py lines 1001 to 1007) show the unattended sentence,
   so "run it" is a loop. In `status`, `doctor` and the cleanup preview the
   advice is correct: those commands are not the adopt command. Pins: the
   constant `ADOPTED_ORDINARY` (tests/test_retention_unattended.py line 353),
   used by `test_the_helper_per_state` (line 397), the status block test (line
   459) and the cleanup preview test `test_an_ordinary_only_record_says_so_in_the_preview`
   (line 548, its pin at line 552). No existing test runs the adopt preview of a file that was
   adopted only with the ordinary sentence.
2. **Confirmed.** `test_a_mixed_confirmation_is_refused`
   (tests/test_retention_unattended.py line 269) asserts only
   `assertIn("mixes", proc.stderr)`. The refusal in
   `retention_policy.apply` (lines 568 to 571) has a cause and a `next:` line
   that nothing pins. Its sibling tests pin the cause by an exact `error: ...\n`
   line (`test_the_unattended_sentence_is_refused_for_a_file_without_the_key`,
   line 261) or by two substrings; the helper `refused` already checks exit 2,
   the `error: ` start, a `next: ` line, no traceback and an unchanged tree.
3. **Confirmed, in three places** (plus a fourth sentence the change makes false,
   `docs/retention.md` line 162, see section 2). `docs/retention.md` line 158 ends "...so such
   a record changes from `adopted` to `record-invalid` when the Manager is
   updated, and the policy is adopted again; ...", and the same idea reads
   "Adding the key changes the policy digest, so the policy is adopted again"
   at lines 111 and 149. All three leave the subject out; nothing re-adopts a
   policy by itself (adoption is the owner's act, `docs/retention.md` says so
   elsewhere). None is already fixed.

## 2. Decisions

* **One parameter, not a text change in the shared line.** `unattended_lines`
  gains a keyword argument `adopting` (default `False`). It changes only the
  head of the "adopted without unattended authorisation" branch; every other
  state and every other caller is byte-identical. `cmd_adopt_retention_policy`
  passes `adopting=True`. The shared line stays as it is for `status`, `doctor`
  and the cleanup preview.
* **The new adopt-preview head**, exactly (one line, two-space indent):
  `  unattended retention: the file declares it, but the adoption authorises
  nothing unattended; only the unattended sentence authorises it: adopt again
  with the unattended sentence printed below`. It is true there: the preview
  prints that sentence a few lines later for every file with the key
  (`cli.py` line 1004). Only the clause after the last semicolon differs from
  the shared head.
* **The mixed-confirmation pin is the full stderr**, not substrings: for both
  policies the test uses today (with and without the key) the stderr is exactly
  `error: --confirm mixes the ordinary and the unattended adoption sentence`
  then `next: run workflow-manager adopt-retention-policy <target> to see the one
  sentence for this policy, then run it again with --confirm holding only that
  sentence`, each line ending with a newline, the target quoted as the shell
  would (the test builds it from the program name and `shlex.quote`, not from
  the code's own helper). No code change.
* **The docs say who adopts.** The three sentences name the owner: "so the
  owner adopts the policy again" (lines 111 and 149) and "and the owner adopts
  the policy again" (line 158, with the sentence's meaning kept: this is what
  the owner must do after the Manager is updated). The docs page keeps its
  header and its "Last checked with" stamp unchanged: this item changes
  wording, it does not re-check the page against a release.
* **`docs/retention.md` line 162 is qualified** (LPR1-001). The paragraph ends
  "The adopt preview and the `retention-cleanup` preview print the same lines; a
  file without the key prints none of this." After CP1 the adopt preview, for a
  file adopted with the ordinary sentence only, prints a different head from the
  one `status`, `doctor` and the cleanup preview print. CP2 amends the sentence to
  "The adopt preview and the `retention-cleanup` preview print the same lines,
  except that the adopt preview, for a file adopted with the ordinary sentence
  only, says to adopt again with the unattended sentence it prints below; a file
  without the key prints none of this."
* **Pins stay where they are.** The status, doctor and cleanup-preview pins
  (`ADOPTED_ORDINARY` and its three uses) keep the shared line; a new constant
  `ADOPTED_ORDINARY_ADOPT_PREVIEW` pins the adopt-preview text. The work-item
  prompt's line numbers 354 and 517 point at the constant and the cleanup
  preview class: neither needs to change, because the shared line does not.
  If implementation finds the shared line must change, that is more than a
  message change and the item stops and records a finding.

## 3. Tests and failure-only mutations

CP1 (`tests/test_retention_unattended.py`):

* **Helper, per state, with `adopting=True`** (new, beside
  `test_the_helper_per_state`): for the five states the file already loads
  (`unattended`, `ordinary`, `not-adopted`, `record-invalid`, `changed`) the
  result is the exact lines of `adopting=False` for every state but `ordinary`,
  whose head is the new constant; the enforcement lines after it are unchanged.
  A state without the key or without a valid file still returns `[]`.
* **The adopt preview through the command** (new): a file with the key adopted
  only with the ordinary sentence (a hand-written record, as the cleanup
  preview test does), then `adopt-retention-policy TARGET`: exit 0, the tree
  unchanged, the output holds the new head exactly once and the unattended
  sentence on a later line, and does not hold `adopt-retention-policy` inside
  the unattended line. The same file through the cleanup preview and the status
  block keeps the shared text (the existing pins).
* **The mixed confirmation** (strengthened `test_a_mixed_confirmation_is_refused`):
  the exact stderr above for both policies.

CP2 (`tests/test_retention_unattended.py`, `TestPage`):

* The page holds the three owner sentences and the qualified sentence of line
  162 ("...print the same lines, except that the adopt preview, for a file adopted
  with the ordinary sentence only, says to adopt again with the unattended
  sentence it prints below"), and does not hold "and the policy is adopted again",
  "so the policy is adopted again" or "print the same lines; a file without the
  key".

**Failure-only mutations** (a scratch copy outside the repository, never the
repository; each passes on the real code and fails as stated, and the
unmutated control passes):

| Mutation | Must fail |
| --- | --- |
| `adopting` is ignored: the adopt preview prints the shared head again | the adopt-preview test and the helper test with `adopting=True` |
| the `next:` clause of the mixed refusal in `retention_policy.apply` is reworded | the strengthened mixed-confirmation test (the old substring test would pass) |
| the cause of the mixed refusal in `retention_policy.apply` is reworded but keeps the word "mixes" (the weakened pin: the old substring assertion would still pass) | the strengthened mixed-confirmation test |
| `docs/retention.md` line 158 reverts to "and the policy is adopted again", or line 162 reverts to the unqualified "print the same lines;" | the page test |

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The adopt preview says to adopt again, and the mixed-confirmation refusal is pinned in full | - | 2 | 1 |
| CP2 | The docs say the owner adopts again, and the ROADMAP row | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the adopt preview says to adopt again, and the mixed-confirmation refusal is pinned in full

**Files:** `src/workflow_manager/retention_policy.py`, `src/workflow_manager/cli.py`, `tests/test_retention_unattended.py`.

`unattended_lines(state, target, *, adopting=False)` in `retention_policy.py`
chooses the new head in the ordinary-adoption branch when `adopting` is true;
`cmd_adopt_retention_policy` in `cli.py` passes `adopting=True`; the other two
callers and `block` are untouched. The tests of section 3 for CP1 are added
(the helper test, the adopt-preview test, the strengthened mixed-confirmation
test) with the constant `ADOPTED_ORDINARY_ADOPT_PREVIEW`. Verification:
`python3 tests/run_all.py --select test_retention_unattended.py`, then
`--select` of `test_retention_policy.py`, `test_retention_cleanup.py`,
`test_retention_status.py`, `test_retention_alert.py` and `test_docs.py`, then
the mutations of section 3 (first two rows) on a scratch copy.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the docs say the owner adopts again, and the ROADMAP row

**Files:** `docs/retention.md`, `tests/test_retention_unattended.py`.

The three sentences and the qualified line-162 sentence of section 2, and the
`TestPage` pin of section 3. The
ROADMAP row 53 is added in the style of rows 50 to 52 with status Current when
this item is planned, and marked Done by this checkpoint, in the item's own
wording: "Done (accepted by policy; a `fix:` change, Manager patch release)".
Verification: `--select test_retention_unattended.py`, `test_docs.py` and
`test_operator_ux_docs.py`, the fourth mutation of section 3 (both variants), then the full
gate `python3 tests/run_all.py` once, at the last checkpoint.
<!-- /CP2 -->

## 5. Functional review

Flows are offline greps and diffs, listed in the checklist the Controller
prepares: the diff touches only the declared files, the three wording fixes and the qualified line-162
sentence read as specified, the status, doctor and cleanup-preview text is unchanged, and
pages and sources not named by this plan are identical to the base.

## 6. Risks and open decisions

* A third caller of `unattended_lines` that forgets `adopting` keeps the shared
  line, which is the safe default (it is correct everywhere but the adopt
  preview).
* The new head is longer than one terminal line; it is one logical line like
  its siblings.
* No row of `docs/TECHNICAL_DECISIONS.md` is touched. No open decision is
  finalised here.
