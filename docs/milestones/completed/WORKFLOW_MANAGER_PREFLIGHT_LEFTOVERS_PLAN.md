# Workflow Manager: The Gate Preflight's Test and Note Say the Whole Truth (Revision 1)

`work_item_id: preflight-leftovers` -- `governing_workflow_version: "2.2"`

**Deliverable:** the real-script priming test pins the next step the refusal
names, and the Priming bullet of `docs/ARCHITECTURE.md` says `--results` does
not relocate frozen discovery's release snapshot (roadmap row 33, issue #151,
items 1 and 4).

**Work item type:** `process`. **Base commit:** `f0f9095`
(`f0f90952b8c25938f43189460874d132aaad4b5c`, tip of `main`, Manager 1.14.8;
Workflow 2.25.5 installed, automatic gates). **Branch:**
`milestone/preflight-leftovers`. **Scope source:** `docs/ROADMAP.md` row 33
(added by this item, Current now, Done at acceptance). One test assertion and
one documentation sentence: no behaviour of the runner changes, no `src/`
change, no printed text. The pull-request title is a `test:` change and
**releases nothing** (the sentence rides along); check it with
`python3 tools/release/release.py check-title "test: ..."`. One mechanism:
the gate preflight's test and note say the whole truth. Two checkpoints, two
deliverable files, one review surface.

## 1. Each item checked against main (`f0f9095`)

| Item of #151 | Still open on main? | Evidence | Action |
| --- | --- | --- | --- |
| 1. the real-script test does not pin the next step | Yes | `test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` (`tests/test_parallel_runner.py`) asserts `"0.0.1"`, `"does not serve its manifest"` and `env[release_source.CACHE_ENV]`. `priming.prime` (`tests/parallel/priming.py`) ends the message with `remove {report['cache']}/{unserved}`. The fake-report case (`test_a_version_the_cache_does_not_serve_is_a_priming_error`) pins `/c/0.0.1`, but not on the real-script path | assert the step (section 2) |
| 2. the mapping of a finished item has no nested-run exception | Out of scope | `docs/ai-workflow/requirements/gate-preflight-mapping.json` is the record of completed work | leave it |
| 3. wording of a finished plan | Out of scope | the plan of a finished item (`docs/milestones/completed/`) | leave it |
| 4. `--results` does not relocate everything | Yes | `docs/ARCHITECTURE.md`'s Priming bullet states the free-space check and `--results` but not the residual. the snapshot sits outside the measured filesystem in either mode: a local run's `discover_and_select` runs before `make_run_dir`, `--run-shard` creates its run directory first (`tests/parallel/executor.py`); frozen discovery's subprocess calls `support.release(version)` (`tests/parallel/inventory.py`), which resolves through `ReleaseCache.resolve` and `_copy_snapshot` (`src/workflow_manager/source.py`) with `tempfile`'s default directory, the ambient `TMPDIR` | one sentence (section 3) |

Out of scope, stays as it is: `src/`, `tools/`, any behaviour of the runner,
`tests/parallel/resources.json`, `tests/parallel/priming.py` and
`tests/parallel/inventory.py` (read, not changed), and the issue's items 2 and
3.

## 2. Item 1: the real-script test pins the next step

In the asserted parts of the test, after the cache directory:

```python
        cache = env[release_source.CACHE_ENV]
        for part in ("0.0.1", "does not serve its manifest", cache,
                     f"remove {cache}/0.0.1"):
            self.assertIn(part, text)
```

`remove <cache>/<version>` is the one next step the refusal names, so the test
asserts it whole: the verb, the cache directory and the version. Nothing else
in the test changes.

## 3. Item 4: the residual, in one sentence

In the Priming bullet of `docs/ARCHITECTURE.md`, directly after the sentence
that ends "does not repeat the check.":

> `--results` moves the run directory only: frozen discovery still creates its
> release snapshot (`support.release()`) under the ambient `TMPDIR`, a
> filesystem the check does not then measure.

The sentence states no ordering of the snapshot and the run directory: it holds
for a local run and for `--run-shard` (which creates its run directory before
discovery), because the snapshot sits outside the measured filesystem in
either order. "Then" keeps it true for a run without `--results`, whose check
does measure that filesystem.

No milestone id appears in the page. The cache filesystem (priming writes the
release cache, which can be another filesystem than the run directory's,
before any unit starts) is left out of the sentence on purpose: the page does
not state a cache-filesystem limitation for the residual to sit next to, and a
full cache filesystem already fails at the start as `PrimingError`.

## 4. Failure-only mutations

Each is a `sed` on a fresh copy of the candidate (`command rm -rf $S/mut;
command cp -rf $S/cand $S/mut`; `cand` is a clone of the branch head). `T=test_parallel_runner.TestGatePreflight.test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve`,
run from `$S/mut/tests` as `python3 -B -m unittest $T` (needs the full
environment).

| # | Mutation | Must happen |
| --- | --- | --- |
| M1 | reword the step: in `tests/parallel/priming.py`, `s\|remove {report\['cache'\]}/{unserved}\|delete {report['cache']}/{unserved}\|` | the candidate test fails on `assertIn(f"remove {cache}/0.0.1", ...)`; the base test file (`git show f0f9095:tests/test_parallel_runner.py`) passes the same mutation (the gap item 1 closes) |
| M2 | the step loses the version: `s\|remove {report\['cache'\]}/{unserved}\|remove {report['cache']}\|` | the candidate test fails on the same assertion; the base test file passes |

The unmutated candidate passes the test.

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The pinned next step and the residual sentence | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the pinned next step and the residual sentence

**Files:** `tests/test_parallel_runner.py`, `docs/ARCHITECTURE.md`.

Sections 2 and 3: the added assertion in the real-script test and the one
sentence in the Priming bullet. Run `python3 tools/check_docs.py` and
`python3 tests/run_all.py --select test_docs.py` on the page change, and
`python3 tests/run_all.py --select test_parallel_runner.py` on the test. M1
and M2 touch scratch copies only.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 33 of `docs/ROADMAP.md` is added by this plan as Current and is Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone and the mutation
results. No version is edited: a `test:` title releases nothing. Both files
stay excluded at both stages; the acceptance step writes them.
<!-- /CP2 -->

## 6. Functional review

Flows 1 to 5 run offline (no network, no `gh`, no installs) in a clone `S/cand`
of the branch head (`S=$(mktemp -d "$HOME/.cache/pl-fr.XXXXXX")`, `git clone
--no-hardlinks <product clone> $S/cand`) and write nothing into the product
clone. Flows 6 to 9 are marked "(needs the full environment)": they run the
repository's tests, which need the primed release cache (or a
`WORKFLOW_MANAGER_RELEASE_SOURCE` mirror) that `tests/run_all.py` needs; flow
9 is last. Run as a non-root user.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat f0f90952b8c25938f43189460874d132aaad4b5c HEAD -- src tools tests docs/ARCHITECTURE.md` | exactly `tests/test_parallel_runner.py` and `docs/ARCHITECTURE.md`; nothing under `src/` or `tools/` |
| 2 | `grep -n 'remove {cache}/0.0.1' $S/cand/tests/test_parallel_runner.py`; `git diff f0f90952b8c25938f43189460874d132aaad4b5c HEAD -- tests/test_parallel_runner.py \| grep -c '^-[^-]'` | one match, inside `test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve`; the count is the number of replaced lines (at most 2), no other line of the file changes |
| 3 | `tr '\n' ' ' < $S/cand/docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'does not repeat the check\. `--results` moves the run directory only.\{0,260\}'` | one match (newlines and indents are normalised) that starts at "does not repeat the check." and names `support.release()`, the ambient `TMPDIR` and that the check does not measure it |
| 4 | `git diff f0f90952b8c25938f43189460874d132aaad4b5c HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|preflight-leftovers'` | `0`: no added line names a milestone or a work-item id |
| 5 | `cd $S/cand && python3 tools/check_docs.py` | exit 0 |
| 6 | (needs the full environment) in `$S/cand/tests`: `python3 -B -m unittest test_parallel_runner.TestGatePreflight.test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` | exit 0 |
| 7 | (needs the full environment) fresh copy, M1; the candidate test | exit 1 at the `remove {cache}/0.0.1` assertion; then the base test file (`git show f0f90952b8c25938f43189460874d132aaad4b5c:tests/test_parallel_runner.py` copied over) with M1 passes |
| 8 | (needs the full environment) fresh copy, M2; the candidate test, then the base test file | candidate exit 1 at the same assertion; base file exit 0 |
| 9 | (needs the full environment) in `$S/cand`: `python3 tests/run_all.py --select test_parallel_runner.py` and `python3 tests/run_all.py --select test_docs.py` | exit 0 each, no `OrphanProcessError` |

Flows 1 to 5 write nothing. Flows 7 to 9 run in scratch checkouts under `$S`;
nothing is written into this repository.

## 7. Risks

* The asserted step is the exact text of `priming.prime`; rewording the
  message in a later item changes this test with it, which is its point.
* `report['cache']` is the directory the subprocess reports; the existing
  assertion already requires it to contain the environment's value, and the
  scratch cache path has no symlink to resolve, so the joined string matches.
  The candidate test run (flow 6) proves it.
* Running `tests/test_parallel_runner.py` directly with `python3 -m unittest`
  (outside `run_all.py`) makes each nested run check the real `TMPDIR`
  against 4 GiB; not a gate path.

## 8. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
