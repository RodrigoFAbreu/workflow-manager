# Workflow Manager: Tests That Assert What They Claim, Third Pass (Revision 1)

`work_item_id: test-hygiene-3` -- `governing_workflow_version: "2.2"`

**Deliverable:** the existing tests of the discovery, release-metadata and
parallel-runner areas and of the update report assert what they claim: ten
points of four follow-up issues (#162 points 1 to 3, #164 points 1 to 4, #166
point 1, #239 points 1 and 2), each failing when the behaviour it names breaks
and leaking nothing. Roadmap row 49 (added by this item, Current now, Done at
acceptance). **Work item type:** `process`. **Base commit:** `26d6850`
(`26d6850bb050a6d66b3afc7d9c22de7e06b12525`, tip of `main`; Manager 1.20.3,
Workflow 2.29.6 installed, automatic gates). **Branch:**
`milestone/test-hygiene-3`. **Release:** none. The diff is four test files, one
line of `docs/update.md` and the roadmap row; `src/`, `tools/`, `.claude/`,
`scripts/`, `.workflow-manager/` and `tests/parallel/` stay byte-identical, and
no output of any command changes. The pull request title is `test: the
discovery, release-metadata, parallel-runner and update-report tests assert what
they claim`; `python3 tools/release/release.py check-title` says `valid title:
test, release impact none`. `docs/RELEASING.md` lists `test` (like `docs`,
`chore`, `ci`, `style`) as releasing nothing, so the docs line does not make it a
`docs:` or `fix:` change, and `docs/ARCHITECTURE.md` "GitHub Actions layout"
says releases run inside `ci.yml` only after a releasing title: `publish` finds
nothing to release. **Size:** two checkpoints, one mechanism (*a test asserts
what its name says*), about 200 lines of plan: no split. Out of scope: any `src/`
change, the retention commands, Workflow releases, CI. Every Optional review
finding gets a disposition at acceptance.

## 1. Investigation (done at `26d6850`)

Each point re-read against current main, with the hypothesis tested by a spike
(a patch kept outside the repository, applied, measured, reverted: the working
tree was clean again before this plan was written).

| Point | Class | Evidence on main |
| --- | --- | --- |
| #162.1 default whose cached block is for a newer Manager | TRUE-FIX-NEEDED | `tests/test_release_metadata.py:846` `TestTheLatestFilterKeepsTheDefault`, `:869` the cached case lists `99.0.0`, malformed and no block, no `schema_version: 2`; mutation `if version == default and exc.newer_manager: return None` in `cli.py` `_latest_filter` survives |
| #162.2 pin that is not built in, block read | TRUE-FIX-NEEDED | no test names a pin with a read block; `if version in pins: return None` after the built-in check survives (spike: 4 of 6 pin cases fail it) |
| #162.3 `docs/update.md` "could read" | TRUE-FIX-NEEDED | `docs/update.md:45` still reads "whose `manager` block neither this run nor the cache could read"; `_latest_filter` keeps a pin or the default only when `cached_manifest` is `None` |
| #164.1 control claims more than it shows | TRUE-FIX-NEEDED | `tests/test_discovery.py` `test_the_control_skips_exactly_where_the_probe_does` has a missing path and regular files; `_lists_links` tests `os.path.islink`, the probe tests the pair's own socket links; 256 `pipe:[1]` links split them (spike: control fails with `islink`) |
| #164.2 "first existing directory" untested | TRUE-FIX-NEEDED | `_lists_links` (`:947`) returns inside the loop; `if ...: return True` leaves `TestTheDescriptorProbe` green; the coupling cases patch one-entry tuples |
| #164.3 second `socketpair()` outside the first pair's `try` | TRUE-FIX-NEEDED | `test_the_helper_sees_a_socket_it_just_opened` (`:1339`, the first `socketpair()`; the second is `:1340`): a failing second allocation leaves descriptors 3 and 4 open (spike) |
| #164.4 `_lists_links(directories=None)` | TRUE-FIX-NEEDED, tests only | the one caller (`:1336`) passes nothing; `_lists_links` is a helper of the test file, so no `src/` change: iterate `_FD_DIRECTORIES`, `_blind_reason(directories)` stays (its callers pass one) |
| #166.1 sigterm/sigint test cleanup | TRUE-FIX-NEEDED | `tests/test_parallel_runner.py:4877`: the `finally` only writes the stop file; `_end_group` (`:2930`) is used by `_interrupt` and `TestEndGroup` only |
| #239.1 no-installation arm | TRUE-FIX-NEEDED | `tests/test_compatibility.py:1305`-`:1309`: the last block asserts `names no usable release` for `facts.installation = None`, which the CLI cannot produce |
| #239.2 redundant `assertIn("verify", ...)` | TRUE-FIX-NEEDED | `:1320`: `assertIn("verify", found.detail)` beside `makes that comparison, or prints why it cannot.` |

No point is ALREADY-FIXED or KEEP; none needs `src/` (point 4 of #164 is a test
helper). All ten are done here.

## 2. Design

### 2.1 Release metadata and the update page (#162.1 to .3), CP2

* The cached case of `test_a_default_whose_cached_block_is_read_is_judged_like_any_other_release`
  gains `7.0.6` with `{"manager": {"schema_version": 2}}` expecting `comp.NEWER_BLOCK`.
* A new test `test_a_pin_that_is_not_built_in_is_judged_like_any_other_release_when_its_block_is_read`
  uses pins `7.0.1` to `7.0.6` (none built in, asserted with `comp.has_builtin_data`):
  a cached minimum `99.0.0` (`"99.0.0"`), a cached newer block (`NEWER_BLOCK`), a cached
  non-object block (`MALFORMED_BLOCK`), a block the run read (`"99.0.0"`), a cached
  manifest with no block and a pin with no cached manifest (both `None`).
* `docs/update.md` line 45 reads "a pin or the default version with no trusted
  cached manifest is kept (one whose block was read is judged like any other
  release)". `TestTheDocs` pins the new sentence and that the old words are gone.
  The page's "Last checked with" stamp does not move: one sentence is not a
  re-check of the page (`python3 tools/check_docs.py` stays clean).

### 2.2 The descriptor probe (#164.1 to .4), CP1

* `_lists_links()` takes no parameter and answers what the probe asks: the
  first existing directory of `_FD_DIRECTORIES` lists the open socket pair's own
  links (`_own_links(pair) <= _socket_links((directory,))`), the pair closed in
  a `finally`. A directory of links to something else is no longer "listing".
* The control test gets a third stand-in, 256 `pipe:[1]` links, beside the missing
  path and the regular files: the probe skips, the control must skip with the same
  reason.
* A new test `test_the_first_existing_directory_decides_what_is_listed` patches
  `_FD_DIRECTORIES` to `(blind, real)` (False), `(absent, real)` (True) and
  `(real, blind)` (True), where `real` is the first existing directory of the
  host; it skips as the control does when the host lists nothing.
* In `test_the_helper_sees_a_socket_it_just_opened` the second `socketpair()`
  moves inside the `try` that closes the first pair.

### 2.3 The runner test and the report note (#166.1, #239.1, #239.2)

* The `finally` of `test_sigterm_and_sigint_kill_the_chunk_restore_the_barrier_and_exit_2`
  does what `_interrupt` does: `pgid = None` before the `try`, then every known chunk
  group through `_end_group` first, then the stop file, then `proc.kill()` and
  `communicate()` when the executor still runs, and an assertion that every group
  ended. The success path is unchanged: `pgid` is set to `None` right after `assertTrue(_dead(pgid))`, so `_end_group` never signals a group already dead and reaped (a reused pgid under the parallel runner would otherwise be hit by `os.killpg`).
* The no-installation arm of `test_an_unknown_record_gets_a_note_with_no_verify_command`
  asserts only what it can show: no ` verify ` outside the quoted
  `workflow-manager verify` words (the executable-command check the loop already
  uses). The `names no usable release` wording stays in the loop, where the record
  exists.
* `test_a_valid_record_keeps_the_verify_command_in_the_note` loses
  `assertIn("verify", found.detail)`; the two assertions beside it carry the check.

## 3. Failure-only mutations

Each runs in a scratch copy outside the repository (never in the working tree), with
`python3 tests/run_all.py --select` of the file or class; the unmutated candidate
passes. Spike results at `26d6850`:

| Mutation | Point | Fails |
| --- | --- | --- |
| M1 `if version == default and exc.newer_manager: return None` in `_latest_filter`'s `except` | #162.1 | the default case `7.0.6` |
| M2 `if version in pins: return None` after the built-in check; M2b the same inside the `except` | #162.2 | the pin test (M2: `7.0.1` to `7.0.4`; M2b: `7.0.2`, `7.0.3`) |
| M3 revert the `docs/update.md` sentence | #162.3 | `TestTheDocs` |
| M4 `_lists_links` tests `os.path.islink` of the pair's descriptor | #164.1 | the control, case "links to something other than a socket" |
| M5 `if matches: return True` in `_lists_links` | #164.2 | the new first-directory test, case "a blind directory first hides a listing one" |
| M6 the second `socketpair()` of the helper test raises | #164.3 | not a test failure: with the old order descriptors 3 and 4 stay open, with the new order both are closed (measured, reported) |
| M7 `self.fail("injected")` in place of the signal in the sigterm test | #166.1 | not a test failure that shows the fix: the test fails in both orders. Observed instead, for each `finally`, whether the chunk group is already dead when the `finally` ends (before the stop file is read) and the runner's orphan line. Expected: new order dead, old order alive until the chunk reads the stop file. If no difference can be shown, the fix is justified by inspection (the old order relies on the chunk honouring the stop file) and the report says so |
| M8b the "names no usable release" note also prints ` Run verify now.` for `installation = None` only | #239.1 | `test_an_unknown_record_gets_a_note_with_no_verify_command` (the last block alone) |

Mutation coverage (mapping R5): M1 to M5 and M8b are failure-only mutations of an assertion that can fail; M6 and M7 are measured evidence, not test failures (see their rows); the redundant assertion of #239.2 has no mutation: removing it changes nothing a
mutation could reach, the assertions beside it fail when `makes that comparison`
goes (measured in the same scratch copy).

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The descriptor probe and the runner test cleanup | - | 2 | 1 |
| CP2 | The latest filter, the update report note, the docs line and the roadmap row | CP1 | 2 | 1 |

<!-- CP1 -->
### CP1 -- the descriptor probe and the runner test cleanup

**Files:** `tests/test_discovery.py`, `tests/test_parallel_runner.py`.

Sections 2.2 and the first bullet of 2.3, mutations M4 to M7. Verify with
`python3 tests/run_all.py --select test_discovery.py --select
test_parallel_runner.py` (run `python3 tests/run_all.py --list` first if the
release cache may lack a version): verdict exit 0, only the declared orphan
sources reported. `git diff --exit-code 26d6850bb050a6d66b3afc7d9c22de7e06b12525
-- src tools .claude scripts .workflow-manager tests/parallel` (no output). The
full `python3 tests/run_all.py` runs at the implementation review and at
acceptance, never while a file is being written.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the latest filter, the update report note, the docs line and the roadmap row

**Files:** `tests/test_release_metadata.py`, `tests/test_compatibility.py`, `docs/update.md`.

Section 2.1 and the last two bullets of 2.3, mutations M1 to M3 and M8b. Add row
49 to docs/ROADMAP.md (Current, Done at acceptance), in the style of row 48: one
mechanism, the ten points, "Not in this slice", a `test:` change with no
release. Verify with `python3 tests/run_all.py --select test_release_metadata.py
--select test_compatibility.py --select test_docs.py`, `python3
tools/check_docs.py` and the same `git diff --exit-code`. docs/ROADMAP.md and
docs/ACTIVE_MILESTONE.md are excluded at both stages, not deliverables. Comments on
#162, #164, #166 and #239 record what was done; they close at acceptance.
<!-- /CP2 -->

## 5. The declaration

`docs/ai-workflow/registry/test-hygiene-3-artifacts.json` classifies the five
deliverables and protects them at the implementation stage; the five are
excluded at the plan stage, like every item's. The source and tool paths the
plan reads or diffs (`src/workflow_manager/cli.py`, `tools/check_docs.py`,
`tools/release/release.py`) are not deliverables: the first two are named as
byte-identical evidence and protected at the implementation stage (a change there is hashed and reviewed content), the third is
run only. `docs/ROADMAP.md` and `docs/ACTIVE_MILESTONE.md` stay excluded at both
stages. `tests/parallel/resources.json` is not edited and not named: no test here
orphans on purpose. SELF_REVIEWING_PLAN edits the generated template before the
first publish and checks that every path a Files paragraph names is classified at
both stages and every deliverable is protected.

## 6. Functional review

Greps and diffs (flow 10 needs the primed cache named there) in a checkout of the candidate; `BASE` is
`26d6850bb050a6d66b3afc7d9c22de7e06b12525`. Exit codes are read with `; echo $?`,
not through a pipe; greps exclude `docs/ai-workflow` and `docs/ACTIVE_MILESTONE.md`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --stat BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only the four test files, `docs/update.md` and `docs/ROADMAP.md` |
| 2 | `git diff --exit-code BASE -- src tools .claude scripts .workflow-manager tests/parallel README.md docs/README.md docs/retention.md docs/verify.md docs/exit-codes.md; echo $?` | no output, `0` |
| 3 | `git diff --numstat BASE -- docs/update.md` and `grep -c 'neither this run nor the cache could read' docs/update.md; echo $?` | `1	1	docs/update.md`; `0` then `1` |
| 4 | `grep -n 'with no trusted cached manifest is kept' docs/update.md` and `grep -n 'Last checked with' docs/update.md` | one match on line 45; the stamp still reads `Workflow Manager 1.14.6, Workflow 2.25.5` |
| 5 | `grep -n 'def _lists_links' tests/test_discovery.py` and `grep -c 'islink' tests/test_discovery.py; echo $?` | `def _lists_links() -> bool:`; `0` then `1` |
| 6 | `sed -n '/def test_sigterm_and_sigint_kill/,/def test_a_root_run_with_allow_root/p' tests/test_parallel_runner.py \| grep -c '_end_group'` | `1` |
| 7 | `grep -n 'assertIn("verify", found.detail)' tests/test_compatibility.py; echo $?` | no match, `1` |
| 8 | `grep -n -E '^\| 49 ' docs/ROADMAP.md` and `grep -c -E '^\| 50 ' docs/ROADMAP.md` | row 49 present, last cell `Current`; `0` |
| 9 | `python3 tools/check_docs.py; echo $?` | no problem line, `0` |
| 10 | with a primed release cache (or a `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror: `run_all.py --select` primes first and exits 2 with `PrimingError` otherwise), in a scratch copy apply M1 to M5 and M8b of section 3 (the implementation summary records each patch exactly: file and line), then `python3 tests/run_all.py --select` the touched file or class | each fails the test the table names (measured, recorded in the implementation summary); the unmutated checkout passes |
| 11 | `python3 tools/release/release.py check-title "test: the discovery, release-metadata, parallel-runner and update-report tests assert what they claim"; echo $?` | `valid title: test, release impact none`, `0` |

## 7. Risks

* `_lists_links` now uses the probe's own criterion, so the control and the probe
  agree by construction on every directory; the control test still proves the
  agreement on three stand-ins, so a later divergence fails it.
* The first-directory test depends on the host listing sockets: it skips with the
  control's reason otherwise (this host lists them).
* A pgid reused by an unrelated group is the exposure of `_end_group` on a dead group; the new `finally` avoids it on the success path (`pgid = None`), `_interrupt` keeps its own.
* The sigterm test's new `finally` calls `_lock_holder` after the run released the
  lock: `_interrupt` already does the same and gets `{}`.

## 8. Open decisions

* **Decided here, for the owner to veto:** the docs sentence keeps the parenthesis
  "one whose block was read is judged like any other release" next to the issue's
  "no trusted cached manifest", since a block the run read is judged even when the
  cache holds nothing; the page stamp does not move.
