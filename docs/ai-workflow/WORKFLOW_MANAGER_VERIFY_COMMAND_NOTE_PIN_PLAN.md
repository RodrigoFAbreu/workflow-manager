# Workflow Manager: Pin the Verify Command in the Not-Verified Note (Revision 3)

`work_item_id: verify-command-note-pin` -- `governing_workflow_version: "2.2"`

Pull request title: `test: pin the verify command in the not-verified note`

**Deliverable:** one assertion in
`test_a_valid_record_keeps_the_verify_command_in_the_note`
(`tests/test_compatibility.py`) that pins the rendered backticked
`workflow-manager verify <repo>` command in the `not-verified` note, so the
test finally asserts what its name claims (issue #245).

**Work item type:** `process`. **Base commit:** `a9365817f792972e9a6f932e30d694fea8df6a96`
(tip of `main`; Workflow 2.29.9 installed, automatic gates). **Branch:**
`milestone/verify-command-note-pin`, bound by the Controller. **Scope source:**
issue #245. The title is a `test:` change and **releases nothing**
(`python3 tools/release/release.py check-title "test: ..."` reads `valid title:
test, release impact none`). One mechanism: one assertion. Nothing under `src/`,
`tools/` or any managed file. **ROADMAP:** no row is added or edited (the
Controller runs acceptance itself and this trial item has no row).

## 1. Verification on current main (`a936581`)

* **TRUE-FIX-NEEDED.** `tests/test_compatibility.py:1311` to `1320`,
  `test_a_valid_record_keeps_the_verify_command_in_the_note`, asserts only the
  text after the command (`"makes that comparison, or prints why it cannot."`,
  line 1319) and the parenthesis before it (line 1320). Neither contains the
  command, so the test passes whether or not the command is present.
* **Code under test.** `src/workflow_manager/compatibility.py:1971` to `1973`
  builds `verify = manager_command("verify", target=repo, withheld=False,
  options=facts.options_for(installed)).render()` and appends
  ``f" `{verify}` makes that comparison, or prints why it cannot."``. With
  the `{verify}` command dropped from that f-string (so the note reads
  ``" makes that comparison, or prints why it cannot."``) every test of
  `TestMiscFindings` still passes: the neighbours only pin the bare
  `workflow-manager verify` (line 1265, the unresolved-release note) or its
  absence (lines 1304, 1309).
* **Rendered text, probed on `a936581`** (a scratch module under `$TMPDIR`
  that subclasses `TestMiscFindings`, nothing written in the repository), for
  the records `1.2.3` and `2.12.0` the note ends with: ``the comparison
  `workflow-manager verify` makes. `workflow-manager verify <target>` makes that
  comparison, or prints why it cannot.`` where `<target>` is `str(self.target)`
  (the temporary directory path; no `--release-version` or other option is
  rendered, since `facts.options_for` is empty here).

## 2. Design

**CP1, one assertion.** In `test_a_valid_record_keeps_the_verify_command_in_the_note`,
inside the `subTest` loop and before the existing two assertions, add

```
self.assertIn(f"`workflow-manager verify {self.target}` makes that comparison",
              found.detail)
```

It pins the opening backtick, the command word, the subcommand, the target
repository path and the closing backtick followed by the sentence, so the command
is no longer optional. The bare-command mention earlier in the note
(`workflow-manager verify` without a path) cannot satisfy it. The existing two
assertions stay (they pin the tail and the parenthesis).

If the new assertion exposes a product defect (for instance the command is not
rendered for a valid record), work stops and the defect is recorded as a finding;
nothing under `src/` is fixed here.

## 3. Failure-only mutation

On a fresh scratch copy of the candidate outside the repository, run
`python3 tests/run_all.py --select test_compatibility.py`. The unmutated
candidate passes. One mutation: **M1**,
`src/workflow_manager/compatibility.py:1973`, drop the verify command from the
note, ``detail += f" `{verify}` makes that comparison, or prints why it cannot."``
becomes ``detail += f" makes that comparison, or prints why it cannot."``. Before
this item, `test_a_valid_record_keeps_the_verify_command_in_the_note` still
passes under M1 (that is the defect); after it, the test **fails** in each
subTest of `VALID_RECORDS`. The expectation is "the named test is among the
failures", never a full failing set. A second mutation, **M2**: on the same line the command is kept but the
target dropped, the f-string uses the bare ``` `workflow-manager verify` ```
instead of `{verify}`. The new assertion fails under M2 as well, because the
repository path is part of the pin.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The verify-command assertion | - | 1 | 1 |

<!-- CP1 -->
### CP1 -- the verify-command assertion

**Files:** `tests/test_compatibility.py`.

The one assertion of section 2. This checkpoint does not touch the bookkeeping
files (`docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`); both stay excluded at both
stages. The workflow itself writes the functional-review checklist to
`docs/ACTIVE_MILESTONE.md` and commits it before the functional-review gate
(`.claude/commands/prepare-functional-review.md`, steps 3 and 3a), so that file
appears as modified at the branch head without being part of this checkpoint.
<!-- /CP1 -->

## 5. Functional review

All flows are offline greps and diffs in a clone `S/cand` of the branch head
(`S=$(mktemp -d "$HOME/.cache/vc-fr.XXXXXX")`, `git clone --no-hardlinks
<product clone> $S/cand`); they write nothing into the product clone. Flow 4 is
marked "(needs the full environment)": it needs the primed release cache that
`tests/run_all.py` needs.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- src tools tests .github .claude scripts .workflow-manager` | exactly `tests/test_compatibility.py` changed, a few insertions and no deletion; nothing under `src/`, `tools/`, `.github/`, `.claude/`, `scripts/` or `.workflow-manager/` |
| 1b | `cd $S/cand && git diff --name-status a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- docs` | only the declared planning and workflow bookkeeping files of this item: `docs/ai-workflow/WORKFLOW_MANAGER_VERIFY_COMMAND_NOTE_PIN_PLAN.md`, `docs/ai-workflow/registry/verify-command-note-pin-registry.json`, `docs/ai-workflow/registry/verify-command-note-pin-artifacts.json`, `docs/ai-workflow/requirements/verify-command-note-pin-mapping.json` (added) and `docs/ai-workflow/WORKFLOW_STATE.json` (modified; its deletions are the state's own transitions), plus `docs/ACTIVE_MILESTONE.md` (modified, only by the functional-review checklist commit; confirm with `git log --format=%s <base>..HEAD -- docs/ACTIVE_MILESTONE.md`, whose commits are checklist-evidence commits); no other path under `docs/`, in particular not `docs/ROADMAP.md` |
| 2 | `cd $S/cand && git diff -U3 a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- tests/test_compatibility.py` | the added lines hold one `assertIn` whose first argument is a backticked `workflow-manager verify` followed by the target path and `makes that comparison`; the two existing `assertIn` lines of that test are context, unchanged |
| 3 | `cd $S/cand && git diff --exit-code a9365817f792972e9a6f932e30d694fea8df6a96 HEAD -- src tools README.md docs/ARCHITECTURE.md tests/portability_exceptions.json tests/parallel/resources.json` | exit 0 (untouched) |
| 4 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_compatibility.py`; then in a scratch copy run ``sed -i 's|detail += f" `{verify}` makes that comparison|detail += f" makes that comparison|' src/workflow_manager/compatibility.py`` (M1 of section 3), check with `grep -n 'makes that comparison, or prints' src/workflow_manager/compatibility.py` that line 1973 no longer holds `{verify}`, and run the same selection | the first run exits 0; in the mutated copy `test_a_valid_record_keeps_the_verify_command_in_the_note` is among the failures |
| 5 | `python3 tools/release/release.py check-title "test: pin the verify command in the not-verified note"` | `valid title: test, release impact none` |

## 6. Risks

* The assertion embeds `str(self.target)`; if a later change renders the path
  differently (quoting, relative form) the test fails loudly, which is the point.
* A target path with characters that need shell quoting would render quoted; the
  test's temporary directory path has none, so the plain f-string holds.

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.

## 8. Review round 1 disposition (Revision 2)

All findings accepted; none rejected.

* **I1 (Important).** Flow 1 compared `docs` against the baseline, which
  includes this item's own plan, registry, declaration, mapping and
  `WORKFLOW_STATE.json`. Flow 1 now covers only the implementation scope
  (no `docs`) and the new flow 1b checks `docs` against the explicit list of
  declared bookkeeping files.
* **O1.** Flow 2 uses `git diff -U3` so the unchanged assertions appear as context.
* **LPR1-001.** Header corrected to Workflow 2.29.9.
* **LPR1-002.** Flow 4 spells out the exact `sed` expression and a `grep -n` check.

## 9. Review round 2 disposition (Revision 3)

All findings accepted; none rejected.

* **LPR2-001 (Important).** Validated against `.claude/commands/prepare-functional-review.md`
  (steps 3 and 3a commit only `docs/ACTIVE_MILESTONE.md` before the gate) and this
  item's own `excluded_paths`. Flow 1b now accepts `docs/ACTIVE_MILESTONE.md` as
  modified by the checklist commit, with a `git log` check, and still forbids
  `docs/ROADMAP.md` and any other undeclared path under `docs/`. CP1's sentence now
  says the checkpoint does not touch the file, not that the item never does.
