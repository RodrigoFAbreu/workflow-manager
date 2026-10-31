# Active Milestone

## Milestone

`null-record-wording` -- in progress (`governing_workflow_version: "2.2"`, `process`, plan revision 3, base `4cbd162`, branch `milestone/null-record-wording`): roadmap row 22 (#108). A `fix:` pull request title (Manager 1.14.2). Plan: `docs/ai-workflow/WORKFLOW_MANAGER_NULL_RECORD_WORDING_PLAN.md`.

What the Manager says about an installation record whose `workflow_version` is null, and its next step: `verify` and `status` with an explicit release no longer print `None`; the `update`, `update --dry-run` and `doctor` `next:` line names one step (the explicit update that rewrites the record); under `--dry-run` that step says it is a real update; a `--release-dir` is left out of the step. Messages outside the null record and every exit code are unchanged.

### CP1: the wording, the docs and the tests -- complete

- `verify` (`install.py`) says the record has no `workflow_version`; `_not_a_version` (`advice.py`) returns the single step for a read, null record, built without `--release-dir`.
- `docs/update.md` names the step; new and changed cases in `tests/test_operator_ux.py` and `tests/test_docs.py`.

### CP2: bookkeeping -- complete

- This record. `docs/ROADMAP.md` row 22 is Current and is Done at acceptance. No version is edited.

### Mutation results (scratch clone of `03f6117`, `python3 tests/run_all.py --select test_operator_ux.py --select test_docs.py --select test_discovery.py`)

The candidate passes: 43 of 43 units, 279 tests, exit 0. Each mutation exits 1 and fails the case the plan names (extra failures listed):

| Mutation | Failed |
| --- | --- |
| `verify` prints `installed None` again | the `verify`/`status` case |
| the null step is the old two-alternative text | the `update`/dry-run/`doctor` case, the null-manifest REL case |
| the dry-run clause is dropped | the `update`/dry-run/`doctor` case, the release-directory case |
| the clause is added to a bare update | the `update`/dry-run/`doctor` case, the release-directory case |
| the null step is applied to a non-null bad record too | the unchanged non-null case, plus two other damaged-record cases |
| `--release-dir` is carried onto the null step again | the null-manifest REL case |
| the clause asserts D holds no version | the genuine-directory D case |
| the `left out` clause is dropped | the release-directory case (REL and D are subtests of it) |
| an explicit `--release-version V update` is refused on a null record | the extended explicit-update case, the release-directory case, `test_t4_t5_unmanaged_targets_get_the_bootstrap_command` |

The scratch clone is outside the repository, which was never mutated. The full gate ran at `7240ca8` and again after the review fix at `00849e9` (exit 0; see the setup check below).

## Functional review checklist

Scope: the null-record wording (plan section 2). Plan section 6 holds the flows; this checklist repeats them with the setup they need. Every flow runs offline with `python3` and `git` only, in a scratch area outside the product clone. No flow uses `gh`, `claude`, `codex`, `ssh` or the network.

### Setup

- **Tools:** `python3` and `git` from `/usr/bin` (the flows use `PATH=/usr/bin:/bin`).
- **Scratch area, outside the product clone:** `S=$HOME/.cache/nrw-fr`. The product clone is only read, by `git archive`; no flow writes to it.

  ```
  mkdir -p "$S/home" "$S/cand" "$S/base"
  git archive HEAD | tar -x -C "$S/cand"
  git archive 4cbd162 | tar -x -C "$S/base"
  ```

  `cand` is the code under test: this branch's `HEAD`, whose `src/` and `tests/` equal the reviewed post-fix `00849e9`. `base` is the parent of the change, for comparison.
- **Release cache, copied:** `command cp -r ~/.cache/workflow-manager/releases "$S/cache"` (about 540 MB). It must hold `2.12.0`. A version it lacks needs the network and fails as `PrimingError`: an environment fault, not a defect.
- **Command wrapper**, defined once per shell: `wm cand ...` runs the candidate, `wm base ...` runs the base.

  ```
  wm() { root=$1; shift; env -i HOME="$S/home" PATH=/usr/bin:/bin PYTHONPATH="$S/$root/src" XDG_CACHE_HOME="$S/home/.cache" XDG_CONFIG_HOME="$S/home/.config" XDG_DATA_HOME="$S/home/.local/share" WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" WORKFLOW_MANAGER_PINNED_ONLY=1 GIT_CONFIG_NOSYSTEM=1 python3 -m workflow_manager "$@"; }
  ```
- **Target `t` (flows 1 to 5):**

  ```
  git init -q "$S/t" && git -C "$S/t" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  wm cand --release-version 2.12.0 bootstrap "$S/t"
  sed -i 's/"workflow_version": "[^"]*"/"workflow_version": null/' "$S/t/.workflow-manager/installation.json"
  ```
- **Null-manifest directory `REL` and target `t2` (flow 4a):**

  ```
  command cp -r "$S/cache/2.12.0/tree" "$S/REL"
  sed -i 's/"workflow_version": "[^"]*"/"workflow_version": null/' "$S/REL/manifest.json"
  git init -q "$S/t2" && git -C "$S/t2" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  wm cand --release-dir "$S/REL" bootstrap "$S/t2"
  ```

  Bootstrap takes **no** `--release-version`. With one, the Manager refuses it (`holds release None, not the requested 2.12.0`); this is the setup the test suite uses too.
- **Genuine directory `D` (flow 4b):** `command cp -r "$S/cache/2.12.0/tree" "$S/D"`, unmodified.
- **Test data:** nothing beyond the above.

### Flows

Run them in the order given: flow 4b starts by nulling `t` again, and flow 5 leaves `t` with an escaped record.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `wm cand --release-version 2.12.0 verify "$S/t"`, then the same with `status` | Exit 1 each. The line `version: the installation record has no workflow_version, release 2.12.0`; no `installed None`. `wm base --release-version 2.12.0 verify "$S/t"` prints `version: installed None, release 2.12.0`. |
| 2 | `wm cand update "$S/t"` | Exit 1. One `next:` line: ``run `workflow-manager --release-version X.Y.Z update <t>` (X.Y.Z is the release to install): it updates the installation record to that release``. No ` or ` and no `repair or re-bootstrap`. `wm base update "$S/t"` prints the two-alternative line instead. |
| 3 | `wm cand update --dry-run "$S/t"` | Exit 1. The same step, ending ` -- a real update, not a dry run`. The record stays null: `grep -c '"workflow_version": null' "$S/t/.workflow-manager/installation.json"` prints `1`. |
| 4 | `wm cand doctor "$S/t"` | Exit 2. The flow 2 step follows `could not resolve the target release:`. |
| 4a | On `t2`, in order: `wm cand --release-dir "$S/REL" verify "$S/t2"` and `... status "$S/t2"`; then `wm cand --release-dir "$S/REL" update --dry-run "$S/t2"` and `wm cand --release-dir "$S/REL" doctor "$S/t2"`; then the printed step with `2.12.0` for `X.Y.Z` and no `--release-dir`: `wm cand --release-version 2.12.0 update "$S/t2"` | `verify` and `status`: exit 0, no `version:` line (matching null versions are no drift). Dry run: exit 1. `doctor`: exit 2. Each prints exactly one `next:` line, the flow 2 step ending `; --release-dir <REL path> is left out: name it too if <REL path> holds release X.Y.Z`. The printed update: exit 0, and the record reads `"workflow_version": "2.12.0"`. |
| 4b | Null `t` again (the target step's `sed`). Then `wm cand --release-dir "$S/D" update --dry-run "$S/t"` and `wm cand --release-dir "$S/D" doctor "$S/t"`; then `wm cand --release-version 2.12.0 --release-dir "$S/D" update "$S/t"`; null `t` again; then `wm cand --release-version 2.12.0 update "$S/t"` | Dry run: exit 1. `doctor`: exit 2. Each prints one `next:` line ending `; --release-dir <D path> is left out: name it too if <D path> holds release X.Y.Z`, with no sentence about what `D` holds. Both printed updates: exit 0, and the record reads `"workflow_version": "2.12.0"`. |
| 5 | `sed -i 's/"workflow_version": [^,}]*/"workflow_version": "..\/escaped"/' "$S/t/.workflow-manager/installation.json"`, then `wm base update --dry-run "$S/t" > "$S/b.out" 2>&1; wm cand update --dry-run "$S/t" > "$S/c.out" 2>&1; cmp "$S/b.out" "$S/c.out"` | `cmp` prints nothing: the two outputs are byte-identical (a non-null bad record keeps the two-alternative step). Both exit 1. |
| 6 | In a scratch clone, not the product clone: `git clone -q /home/rodrigo/Workspace/workflow-manager "$S/clone" && git -C "$S/clone" checkout -q milestone/null-record-wording`, then `cd "$S/clone" && WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" python3 tests/run_all.py --select test_operator_ux.py --select test_docs.py` | Exit 0. The runner writes run files, so it runs only in the scratch clone. Not run during preparation (see the setup check). |

### Setup check (preparation)

Flows 1 to 5, 4a and 4b were run once at this preparation, from `git archive HEAD` in a scratch area outside the clone, with the setup above. Every expectation held. One correction came out of that run and is applied above: bootstrap from `REL` takes no `--release-version`. Flow 6 was not run.

Automated verification: the full gate ran at `00849e9` (exit 0, 2326 of 2326 units, 15504 tests), as recorded in the round 2 implementation summary. The bundle holds no digest-bearing evidence line for that head. Since `00849e9` only `docs/ai-workflow/WORKFLOW_STATE.json` changed, so no rerun was made.

### Environment, not defects

- `PrimingError` (exit 2): a version the cache lacks.
- `holds release None, not the requested 2.12.0`, or `is not a managed repository`: the setup skipped or mis-ran a bootstrap (see above).
- A write refused inside the product clone is the sandbox limit. No flow writes there.

### Known limitations (out of scope)

- `verify` and `status` against a null record still end with `next: a release directory holding None is needed: run the command again with --release-dir DIR`, and `status` still reads `workflow None (full profile)`. These are plan section 5 (NRW-PL-R1-O1, NRW-PL-R1-O2), dispositioned as follow-up issues at acceptance. Not a regression.
- A record of `""` still prints `version: installed , release V`. Same class, same follow-up.
- A bare `--release-dir REL update` on a null record is not refused and prints no null step (NRW-PL-R2-O1). Kept as it is; follow-up.
- `docs/common-problems.md` keeps both repair alternatives for a null record. Kept as it is.
- No version is edited. The `fix:` title releases Manager 1.14.2 at acceptance.

## Next action

Functional review: run flows 1 to 6 in the order above and report each exit code and expectation. Findings go to `.ai-review/null-record-wording/feedback/FUNCTIONAL_REVIEW.md`, then `/review-functional`. Once testing is clean, `/accept-milestone` is the only acceptance command.
