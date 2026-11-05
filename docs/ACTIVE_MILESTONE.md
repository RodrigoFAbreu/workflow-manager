# Active Milestone

## Milestone

`preflight-leftovers` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `f0f9095`, branch `milestone/preflight-leftovers`): roadmap row 33 (#151, items 1 and 4). A `test:` pull request title (releases nothing; one documentation sentence rides along).

The gate preflight's test and note say the whole truth. `test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` also asserts the next step the refusal names (`remove <cache>/0.0.1`). The Priming bullet of `docs/ARCHITECTURE.md` says `--results` moves the run directory only: frozen discovery still creates its release snapshot (`support.release()`) under the ambient `TMPDIR`, a filesystem the check does not then measure. No behaviour, printed text or exit code changes; no `src/` change; no Workflow change. Items 2 and 3 of the issue stay as they are.

### CP1: the pinned next step and the residual sentence -- complete

- Commit `800c152`: `tests/test_parallel_runner.py`, `docs/ARCHITECTURE.md`.

### CP2: bookkeeping -- complete

- `docs/ROADMAP.md` row 33 (Current; Done at acceptance); this record.

### Failure-only mutations

Plan section 4, each on a fresh `git clone` of `800c152` (scratch copy), run as `python3 -B -m unittest test_parallel_runner.TestGatePreflight.test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` from `tests/`. The unmutated candidate passes (0.18 s).

| # | Mutation (`tests/parallel/priming.py`) | Candidate test | Base test file (`f0f9095`) |
| --- | --- | --- | --- |
| M1 | `remove {cache}/{version}` reworded to `delete ...` | fails: `remove <cache>/0.0.1` not found in the message | passes (the gap item 1 closes) |
| M2 | the step loses the version (`remove {cache}`) | fails at the same assertion | passes |

### Self-review

The diff against `f0f9095` was read against the plan: `tests/test_parallel_runner.py` (one assertion), `docs/ARCHITECTURE.md` (one sentence, no work-item id), plus the bookkeeping files; nothing under `src/` or `tools/`.

## Functional review checklist

Stage: `AWAITING_FUNCTIONAL_REVIEW`, implementation revision 1. The change is a `test:` change with one documentation sentence: no behaviour, printed text or exit code changes, no `src/` or `tools/` change. Plan section 6 is the source of these flows.

### Setup

- The flows run in a scratch clone, never the product clone:

  ```bash
  S=$(mktemp -d "$HOME/.cache/pl-fr.XXXXXX")
  git clone --no-hardlinks <product clone> "$S/cand"   # checks out the branch head
  cd "$S/cand"
  ```

- Run as a non-root user. Remove the scratch afterwards: `command rm -rf "$S"`.
- Flows 1 to 6 need no network, no `gh` and no agent CLI. Flows 7 to 9 run the repository's suite and need the primed release cache (`${XDG_CACHE_HOME:-$HOME/.cache}/workflow-manager/releases`, or a local `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror); `tests/run_all.py` primes that cache before it runs. If the sandbox cannot supply it, record flows 7 to 9 as not run; do not count a `PrimingError` as a product failure.

### Test data

None. Flow 6 builds its own synthetic release `0.0.1` inside a scratch checkout. Flows 7 and 8 edit scratch copies of `tests/parallel/priming.py` only.

### Flows

Each flow runs from `$S/cand` unless it says otherwise. Flows 1 to 5 write nothing.

| Flow | Do | Expected result |
| --- | --- | --- |
| 1 | `git diff --stat f0f90952b8c25938f43189460874d132aaad4b5c HEAD -- src tools tests docs/ARCHITECTURE.md` | Exactly `docs/ARCHITECTURE.md` and `tests/test_parallel_runner.py`; nothing under `src/` or `tools/`. |
| 2 | `grep -n 'remove {cache}/0.0.1' tests/test_parallel_runner.py`; then `git diff f0f90952b8c25938f43189460874d132aaad4b5c HEAD -- tests/test_parallel_runner.py \| grep -c '^-[^-]'` | One match, inside `test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve`. The count is at most 2 (the replaced lines); no other line of the file changes. |
| 3 | `tr '\n' ' ' < docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'does not repeat the check\. `--results` moves the run directory only.\{0,260\}'` | One match: it starts at "does not repeat the check." and names `support.release()`, the ambient `TMPDIR`, and that the check does not measure that filesystem. |
| 4 | `git diff f0f90952b8c25938f43189460874d132aaad4b5c HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|preflight-leftovers'` | `0`: no added line names a milestone or a work-item id. |
| 5 | `python3 tools/check_docs.py` | Exit 0. |
| 6 | In `$S/cand/tests`: `python3 -B -m unittest test_parallel_runner.TestGatePreflight.test_the_real_script_refuses_a_cache_that_fills_but_does_not_serve` | `OK`, 1 test, exit 0. |
| 7 | (needs the full environment) Fresh copy of `$S/cand`; in `tests/parallel/priming.py`, `s\|remove {report\['cache'\]}/{unserved}\|delete {report['cache']}/{unserved}\|`. Run flow 6's test. Then copy the base test file over (`git show f0f90952b8c25938f43189460874d132aaad4b5c:tests/test_parallel_runner.py`) and run it again. | Candidate: exit 1, `AssertionError` on `remove <cache>/0.0.1`. Base file: exit 0. |
| 8 | (needs the full environment) Fresh copy; in `tests/parallel/priming.py`, `s\|remove {report\['cache'\]}/{unserved}\|remove {report['cache']}\|`. Run the candidate test, then the base test file. | Candidate: exit 1, the same assertion. Base file: exit 0. |
| 9 | (needs the full environment) In `$S/cand`: `python3 tests/run_all.py --select test_parallel_runner.py`, then `python3 tests/run_all.py --select test_docs.py` | Exit 0 each; no `OrphanProcessError`. A `--select` run is not a gate. |

Verified before this checklist was written: flows 1 to 6 pass in a scratch clone of the branch head, and flow 6 passes under `unshare -rn` (a network namespace with only loopback), so it runs with no network.

### Known limitations and out of scope

- Items 2 and 3 of #151 stay as they are: both change records of finished work.
- Nothing under `src/`, `tools/` or `tests/parallel/` changes. The runner's behaviour, printed text and exit codes are unchanged.
- The `--results` sentence describes the usual case, where `--results` is on a different filesystem from `TMPDIR`. When they share a filesystem the check still measures the snapshot's location, so the sentence is conservative, not wrong.
- Open Optional finding (`docs/ARCHITECTURE.md:496`, implementation review round 1, `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`): the sentence could say "which the check does not cover when `--results` is on another filesystem". It does not block functional review; its disposition is recorded at acceptance.
- No serial or single-shard run was made: neither the plan nor an acceptance criterion requires one. CI has not run; the branch is not pushed.
