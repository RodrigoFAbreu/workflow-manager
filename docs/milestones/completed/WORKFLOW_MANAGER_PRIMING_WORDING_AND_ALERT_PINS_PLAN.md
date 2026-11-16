# Workflow Manager: Priming Wording and the Incomplete-Report Alert Pins (Revision 4)

`work_item_id: priming-wording-and-alert-pins` -- `governing_workflow_version: "2.2"`

Pull request title: `test: pin the alert for an incomplete report whose forge queries all failed, and tighten two priming sentences`

**Deliverable:** (A) the Priming bullet of `docs/ARCHITECTURE.md` says what is
true about test-time fetches and about the filesystem the free-space check does
not cover (issues #190 and #168); (B) two gate tests pin what an incomplete
retention report whose unfinished items are all `query_failed` shows: the
`doctor --retention --json` document and the verify/doctor alert text (point 2
of issue #242).

**Work item type:** `process`. **Base commit:** `59beeea`
(`59beeea99ac8e976b835dc9ab6d8544ba207feb2`, tip of `main`, Manager 1.20.3;
Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/priming-wording-and-alert-pins`. **Scope source:** the owner's
standing order to queue reviewed follow-ups when the queue is empty. The
pull-request title is a `test:` change and **releases nothing**
(`python3 tools/release/release.py check-title "test: ..."` reads `valid title:
test, release impact none`). Two mechanisms, each small: one docs paragraph,
two gate tests. Nothing under `src/`, `tools/` or any managed file.

## 1. Verification on current main (`59beeea`)

* **#190 -- TRUE-FIX-NEEDED.** `docs/ARCHITECTURE.md` line 498 to 499 says "no
  test fetches a release at test time". The loopback servers of
  `tests/test_discovery.py` (`_Stub`, a `ThreadingHTTPServer` on 127.0.0.1) and
  a fill from a `--release-source` mirror are intentional fetches from a local
  source, so the sentence is too strong; the true claim is that no test fetches
  from a remote host.
* **#168 -- TRUE-FIX-NEEDED.** Lines 493 to 494 say "the effective `TMPDIR`"
  for the check and lines 495 to 496 say "the ambient `TMPDIR`, a filesystem
  the check does not then measure" for the snapshot. Both are the same value
  (`tempfile`'s default), so "effective" matches; and `--results` and `TMPDIR`
  can share a filesystem, in which case the check does measure it, so the
  sentence must say the check does not cover it when `--results` is on another
  filesystem.
* **No pin of either sentence.** `grep` of `tests/` and `tools/` finds neither
  the old nor the new words (`tools/check_docs.py` checks freshness stamps and
  links, and this page carries no stamp). The new sentences get no new pin:
  issue #190 itself says the change is only worth a release together with a real
  change to that paragraph, and prose wording is not what a gate pins.
* **#242 point 2 -- TRUE-FIX-NEEDED (points 1 and 3 are fixed or moot and are
  not touched).** Status and doctor text for an incomplete report whose items
  are all `query_failed` are pinned by `test_an_incomplete_report_whose_queries_all_failed_is_the_report`
  (`tests/test_retention_status.py`). Not pinned: (i) the `doctor --retention
  --json` document for it, (ii) the verify/doctor alert text for it. The probe
  below was run on `59beeea` (a scratch module under `$TMPDIR`, nothing written
  in the repository): the report `rs.report(complete=False, not_finished=[two
  query_failed items])` with the policy of `J4` gives exit 0 and a document
  identical to `J4`'s golden except `current_value` 0 for both alerts and an
  all-zero `snapshot` (`finished` 0, `with_review_folder` 0, byte counts 0):
  `evaluation` `not_evaluated`, `not_evaluated.cause` the incomplete cause,
  `report_complete` false. The code path is
  `src/workflow_manager/retention_alert.py:55` to `56` (`failed`) and `236`,
  and `retention_alert_json.py:103` and `122`.

## 2. Design

**CP1, the docs paragraph.** In the Priming bullet of `docs/ARCHITECTURE.md`:
"the ambient `TMPDIR`, a filesystem the check does not then measure" becomes
"the effective `TMPDIR`, a filesystem the check does not cover when `--results`
is on another filesystem"; "no test fetches a release at test time" becomes "no
test fetches a release from a remote host". Nothing else on the page changes
and no stamp moves (the page has none).

**CP2, two gate tests**, no `src/` change, in the existing patterns:

* `tests/test_retention_alert_json.py`: a new test in `TestGoldens` after `J4`,
  `test_J4_an_incomplete_report_whose_queries_all_failed_is_not_evaluated`, with
  the policy of `J4` (`finished_items` 5, `archives` 3, `notify`) and the report
  `rs.report(complete=False, not_finished=<two query_failed items, reasons
  `query_failed:gh_missing` and `query_failed:forge_timeout`>)`, calls
  `self.golden("J4-queries-failed", ...)` and asserts `evaluation` is
  `not_evaluated`, `report_complete` is false, `not_evaluated["cause"]` is
  `ra.CAUSE_INCOMPLETE` and every alert is `unknown`. It also holds a subcase
  for the shape the engine really produces when only the forge queries fail:
  `rs.report(complete=True, read_errors=[], not_finished=<the same two
  query_failed items>)`, with no finished entries. The subcase is checked by
  its fields, not by a second golden (so the one-new-golden rule holds):
  `evaluation` is `not_evaluated`, `report_complete` is **false** (the document's
  `complete` is `not ra.incomplete(report)`, `retention_alert_json.py:117`, and
  `ra.incomplete` is true for a `query_failed:` reason, so the field is false for
  `complete=True` as well; probed on `59beeea`, review finding PWA-L3-001),
  `not_evaluated["cause"]` is `ra.CAUSE_INCOMPLETE` and every alert is
  `unknown`. While `complete` is false the `failed` term of
  `retention_alert.py:56` is invisible (`not report["complete"]` already makes
  the report incomplete), so only this subcase pins it, through `evaluation` and
  `report_complete`: under M1 they flip to `evaluated` and true (review finding
  PWA-L1-001). The pattern of the file
  requires one new whole-document string, `"J4-queries-failed"` in `GOLDENS`,
  which is the `J4` string with the two `current_value` lines and the snapshot
  counts changed to 0; it is generated from the real command output once and
  reviewed against `J4`, never hand-guessed.
* `tests/test_retention_alert.py`: a new test in `TestUnavailable` after
  `test_an_incomplete_report_with_nothing_reached_is_not_evaluated`,
  `test_an_incomplete_report_whose_queries_all_failed_is_not_evaluated`, for
  `("verify", "doctor")` with the same report, asserting through `one_line` that
  the alert is the one not-evaluated line with `ra.CAUSE_INCOMPLETE` and the next
  line `  next: ` plus `retention.STEP_INCOMPLETE`, and that the exit code equals
  the baseline code with no policy (`baseline_code`), as its neighbours do. The
  same subcase (`complete=True`, no read errors, only `query_failed` items) runs
  here with the same assertions, so the `failed` term is pinned at the text
  level too.
  The existing text goldens need no change (no new string: the assertions name
  the constants).

If either test exposes a product defect, work stops and the defect is recorded
as a finding; nothing under `src/` is fixed here.

## 3. Failure-only mutations

Each on a fresh scratch copy of the candidate outside the repository, one at a
time, `tests/test_retention_alert_json.py`, `tests/test_retention_alert.py` and
`tests/test_retention_status.py` run with `python3 tests/run_all.py --select
<file>` (one `--select` each). The unmutated candidate passes; each mutation
must make the named new test **one of the failures**. Existing tests that pin
the same code also fail (M2 alone fails 16 of them: every document goldens
`report_complete`), and the table's "also fails" column is illustrative, not a
set to reproduce: the expectation is "the named new test is among the failures",
never "nothing else fails" and never "the failing set equals a list" (review
findings PWA-L1-002, PWA-L2-001).

| # | Mutation | Must fail (the new test) / also fails (illustrative) |
| --- | --- | --- |
| M1 | `src/workflow_manager/retention_alert.py:56`: remove `or failed` from the returned expression (a report with failed queries is no longer incomplete). `and not failed` is not used: `and` binds tighter than `or`, so it is a no-op (PWA-L1-001) | the new text test and the new J test (both through the `complete=True` subcase), and the existing `query_failed:timeout` subcase of `test_an_incomplete_report_below_the_limit_is_unknown_never_within` |
| M2 | `src/workflow_manager/retention_alert_json.py:103`: `"report_complete": True` | the new J test (golden and assertion), and many existing tests whose goldens hold `"report_complete": false` (the `J3`, `J4`, `J5`, `J6` families and `TestObservedChanges`) |
| M3 | `src/workflow_manager/retention_alert.py:32`: change one word of `CAUSE_INCOMPLETE` | the new J test (the golden holds the literal cause), `J4`'s golden (`tests/test_retention_alert_json.py` line 815) and `TEXT_GOLDENS["incomplete"]` (line 563, `TestTextUnchanged`); no new text test (it names the constant, which is the pattern of its neighbour) |
| M4 | `src/workflow_manager/retention.py:52`, `STEP_INCOMPLETE`: change one word | the new J test (golden); also `J4`, `TestTextUnchanged` T1 and `TestIncomplete.test_read_errors_are_listed_with_a_cap_of_five` in `test_retention_status.py`; the new text test is unaffected by design (constant) -- recorded, and run in Flow 6 so the unaffected result is observed, not a defect |

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The Priming bullet wording | - | 1 | 1 |
| CP2 | The two gate tests | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the Priming bullet wording

**Files:** `docs/ARCHITECTURE.md`.

The two edits of section 2 (#190, #168). Docs only.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the two gate tests

**Files:** `tests/test_retention_alert_json.py`, `tests/test_retention_alert.py`.

The two tests and the one golden string of section 2. Bookkeeping
(`docs/ROADMAP.md` row, `docs/ACTIVE_MILESTONE.md`) is written at acceptance and
stays excluded at both stages.
<!-- /CP2 -->

## 5. Functional review

All flows are offline greps and diffs in a clone `S/cand` of the branch head
(`S=$(mktemp -d "$HOME/.cache/pw-fr.XXXXXX")`, `git clone --no-hardlinks
<product clone> $S/cand`); they write nothing into the product clone. Flows 5
and 6 are marked "(needs the full environment)": they need the primed release
cache `tests/run_all.py` needs.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat 59beeea99ac8e976b835dc9ab6d8544ba207feb2 HEAD -- src tools tests docs .github .claude scripts .workflow-manager` | exactly `docs/ARCHITECTURE.md`, `tests/test_retention_alert.py` and `tests/test_retention_alert_json.py` (plus the plan, registry, mapping and findings files under `docs/ai-workflow/` and `docs/milestones/`); nothing under `src/`, `tools/`, `.claude/`, `scripts/`, `.workflow-manager/`, `tests/parallel/` |
| 2 | `tr '\n' ' ' < $S/cand/docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'no test fetches a release from a remote host.\{0,60\}'` and `... grep -o 'the effective .TMPDIR., a filesystem the check does not cover when .--results. is on another filesystem'` | each prints one line |
| 3 | the same `tr` pipe on `docs/ARCHITECTURE.md`, `grep -c` for the old phrases (`release at test time`, `the ambient`, `does not then measure`) | 0 for each; `grep -c 'Last checked with' docs/ARCHITECTURE.md` is 0 (no stamp exists, so none moved) |
| 4 | `cd $S/cand && git diff --exit-code 59beeea99ac8e976b835dc9ab6d8544ba207feb2 HEAD -- docs/retention.md docs/update.md docs/exit-codes.md docs/glossary.md docs/install.md docs/development.md README.md tests/test_retention_status.py tests/test_docs.py tools src` | exit 0: pages and tests not re-checked were not touched |
| 5 | (needs the full environment) in `$S/cand`: `python3 tools/check_docs.py`; `python3 tests/run_all.py --select test_retention_alert_json.py --select test_retention_alert.py --select test_docs.py` | exit 0 each, no `OrphanProcessError`; the two new tests appear in the run (`grep -n 'queries_all_failed\|J4-queries-failed' tests/test_retention_alert*.py` finds both tests and the golden key) |
| 6 | (needs the full environment) in scratch copies of `$S/cand`, apply M1 to M4 of section 3 with `sed` (one copy each) and run `python3 tests/run_all.py --select` of the three files of section 3 | in each copy the named new test is among the failures (M4: the new text test passes); no failing set is compared; the unmutated copy passes |
| 7 | `python3 tools/release/release.py check-title "test: pin the alert for an incomplete report whose forge queries all failed, and tighten two priming sentences"` | `valid title: test, release impact none` |

## 6. Risks

* The new J golden is a whole-document string; it is generated once from the
  command's real output (probe in section 1) and compared with `J4`'s, so a
  difference other than the zeros is a finding, not something to paper over.
* The docs edit has no pin: a later edit of the paragraph can undo it silently;
  that is accepted for prose (section 1).
* A mutation that changes `STEP_INCOMPLETE` or `CAUSE_INCOMPLETE` is caught by
  the golden, not by the text test, which names the constants like its
  neighbours do.
* The `complete=True` subcase must be a shape the engine can produce; if
  `rs.report` refuses it or the probe differs from the fields above, work stops
  and it is recorded as a finding (nothing under `src/` is fixed here).

## 7. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
