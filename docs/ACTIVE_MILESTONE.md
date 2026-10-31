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

The scratch clone is outside the repository, which was never mutated. The full gate ran at `7240ca8` and again after the review fix at `00849e9` (revision 2: exit 0, same selection and tests digests as the local implementation review's run at `cf31245`).

## Functional review checklist

Scope: the null-record wording (plan section 2). Plan section 6 holds the flows; this checklist repeats them with the setup they need, numbered 1 to 8 for the Controller's flow labels. Plan flows 4a, 4b, 5 and 6 are flows 5, 6, 7 and 8 here. Every flow runs offline with `python3` and `git` only, outside the product clone. No flow calls `gh`, `claude`, `codex`, `ssh`, the network or a host socket, and none needs a pull request.

### Setup

- **Tools:** `python3` and `git` from `/usr/bin` and `/bin`. The `wm` wrapper below puts a `bin/` of refusing stand-ins for `gh`, `claude`, `codex` and `ssh` first on `PATH`. In the Controller's sandbox its own `bin/` plays that role.
- **Scratch area, writable and outside the product clone:** `S=$HOME/.cache/nrw-fr`. If the sandbox's writable scratch directory is elsewhere, set `S` to it; remove an earlier `$S` first. The product clone is only read (`git -C "$REPO" archive`, `git clone --bare`); no flow writes to it.

  ```
  REPO=$(git rev-parse --show-toplevel)
  S=$HOME/.cache/nrw-fr
  mkdir -p "$S/home" "$S/cand" "$S/base" "$S/bin" "$S/tmp"
  git -C "$REPO" archive HEAD | tar -x -C "$S/cand"
  git -C "$REPO" archive 4cbd162 | tar -x -C "$S/base"
  command cp -r ~/.cache/workflow-manager/releases "$S/cache"
  for t in gh claude codex ssh; do
    printf '#!/bin/sh\necho "refused %s $*" >> "%s/stand-in.log"\nexit 1\n' "$t" "$S" > "$S/bin/$t"
    chmod +x "$S/bin/$t"
  done
  ```

  `cand` is the code under test: this branch's `HEAD` (`6defca8` when this was prepared), whose `src/` and `tests/` equal the reviewed post-fix `00849e9`. `base` is the parent of the change. `cache` must hold `2.12.0`; a version it lacks needs the network and fails as `PrimingError`, an environment fault, not a defect.
- **Command wrapper**, defined once per shell: `wm cand ...` runs the candidate, `wm base ...` runs the base.

  ```
  wm() {
    root=$1; shift
    env -i HOME="$S/home" PATH="$S/bin:/usr/bin:/bin" PYTHONPATH="$S/$root/src" \
      XDG_CACHE_HOME="$S/home/.cache" XDG_CONFIG_HOME="$S/home/.config" \
      XDG_DATA_HOME="$S/home/.local/share" WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" \
      WORKFLOW_MANAGER_PINNED_ONLY=1 GIT_CONFIG_NOSYSTEM=1 PYTHONDONTWRITEBYTECODE=1 \
      python3 -m workflow_manager "$@"
  }
  ```
- **Target `t` (flows 1 to 4, 6 and 7):**

  ```
  git init -q "$S/t" && git -C "$S/t" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  wm cand --release-version 2.12.0 bootstrap "$S/t"
  sed -i 's/"workflow_version": "[^"]*"/"workflow_version": null/' "$S/t/.workflow-manager/installation.json"
  ```
- **Null-manifest directory `REL` and target `t2` (flow 5):**

  ```
  command cp -r "$S/cache/2.12.0/tree" "$S/REL"
  sed -i 's/"workflow_version": "[^"]*"/"workflow_version": null/' "$S/REL/manifest.json"
  git init -q "$S/t2" && git -C "$S/t2" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  wm cand --release-dir "$S/REL" bootstrap "$S/t2"
  ```

  Bootstrap takes **no** `--release-version` here: with one, the Manager refuses (`holds release None, not the requested 2.12.0`).
- **Genuine directory `D` (flow 6):** `command cp -r "$S/cache/2.12.0/tree" "$S/D"`, unmodified.
- **Test data:** nothing beyond the above.

### Flows

Run them in the order given. Flow 6 starts by nulling `t` again, and flow 7 leaves `t` with an escaped record.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `wm cand --release-version 2.12.0 verify "$S/t"`, then the same with `status`; and `wm base --release-version 2.12.0 verify "$S/t"` | Candidate `verify` and `status`: exit 1 each, the line `version: the installation record has no workflow_version, release 2.12.0`, and no `installed None`. Base `verify`: exit 1 and `version: installed None, release 2.12.0`. |
| 2 | `wm cand update "$S/t"`; and `wm base update "$S/t"` | Candidate: exit 1 and one `next:` line: ``run `workflow-manager --release-version X.Y.Z update <t>` (X.Y.Z is the release to install): it updates the installation record to that release``, with no ` or ` and no `repair or re-bootstrap`. Base: exit 1 and the two-alternative line (`repair or re-bootstrap ... or fix it with ...`). |
| 3 | `wm cand update --dry-run "$S/t"` | Exit 1. The flow 2 step, ending ` -- a real update, not a dry run`. `grep -c '"workflow_version": null' "$S/t/.workflow-manager/installation.json"` prints `1`: the record is still null. |
| 4 | `wm cand doctor "$S/t"` | Exit 2. The flow 2 step follows `could not resolve the target release:`. |
| 5 | On `t2`, with `REL`: `wm cand --release-dir "$S/REL" verify "$S/t2"` and `status`; then `wm cand --release-dir "$S/REL" update --dry-run "$S/t2"` and `doctor`; then the step the dry run printed, with `2.12.0` for `X.Y.Z` and the `--release-dir` clause left out: `wm cand --release-version 2.12.0 update "$S/t2"` | `verify` and `status`: exit 0, no `version:` line (a matching null version is no drift). Dry run: exit 1. `doctor`: exit 2. Each prints one `next:` line, the flow 2 step ending `; --release-dir <REL> is left out: name it too if <REL> holds release X.Y.Z`. The printed update: exit 0, and `grep -o '"workflow_version": "[^"]*"' "$S/t2/.workflow-manager/installation.json"` prints `"workflow_version": "2.12.0"`. |
| 6 | Null `t` again (the `sed` under Target `t`). Then `wm cand --release-dir "$S/D" update --dry-run "$S/t"` and `wm cand --release-dir "$S/D" doctor "$S/t"`; then `wm cand --release-version 2.12.0 --release-dir "$S/D" update "$S/t"`; null `t` again; then `wm cand --release-version 2.12.0 update "$S/t"` | Dry run: exit 1. `doctor`: exit 2. Each prints one `next:` line ending `; --release-dir <D> is left out: name it too if <D> holds release X.Y.Z`, with no sentence about what `D` holds. Both printed updates: exit 0, and the record reads `"workflow_version": "2.12.0"`. |
| 7 | `sed -i 's/"workflow_version": [^,}]*/"workflow_version": "..\/escaped"/' "$S/t/.workflow-manager/installation.json"`, then `wm base update --dry-run "$S/t" > "$S/b.out" 2>&1; wm cand update --dry-run "$S/t" > "$S/c.out" 2>&1; cmp "$S/b.out" "$S/c.out"` | `cmp` exits 0 and prints nothing: the two outputs are byte-identical, the two-alternative step. Both runs exit 1. |

Flow 8 is the test run. It runs in a scratch clone of a scratch origin, never in the product clone:

```
git clone -q --bare "$REPO" "$S/origin.git"
git clone -q -b milestone/null-record-wording "$S/origin.git" "$S/clone"
cd "$S/clone" && python3 -m compileall -q src && \
env -i HOME="$S/home" PATH="$S/bin:/usr/bin:/bin" TMPDIR="$S/tmp" \
  XDG_CACHE_HOME="$S/home/.cache" WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" \
  GIT_CONFIG_NOSYSTEM=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 tests/run_all.py --select test_operator_ux.py --select test_docs.py
```

Expect exit 0: `24/24 units, 171 tests`, `verdict: exit 0`. Add `--allow-root` after `run_all.py` only if `id -u` prints `0`. The `compileall` line is required; see Environment below.

After flow 8, the stand-in check: `test ! -e "$S/stand-in.log" && echo "no stand-in was called"` prints `no stand-in was called`. A line in `$S/stand-in.log` names a flow that reached `gh`, `claude`, `codex` or `ssh`, and that flow has failed.

### Setup check (preparation)

At this preparation the flows were run as one script under `unshare -rn` (no network), with the refusing stand-ins first on `PATH` and every command taken from this section, in a scratch area outside the clone. Every expectation held for flows 1 to 7 and the stand-in check. Flow 8 exited 0 (24 of 24 units, 171 tests) only after two environment corrections now applied above: bootstrap from `REL` takes no `--release-version`, and a fresh clone needs `python3 -m compileall -q src` and `PYTHONDONTWRITEBYTECODE=1`. A test's `pinned_env()` otherwise writes `src/workflow_manager/__pycache__` during the run, and the integrity check reports that as an unlisted change. This is a setup check, not functional-review evidence; the flows were not run by a person.

Automated verification: the full gate ran at `00849e9` (exit 0, 2326 of 2326 units, 15504 tests), as recorded in the round 2 implementation summary. Since then `git diff 00849e9 HEAD -- src tests scripts tools` is empty; only docs and workflow state changed, so no rerun was made.

### Environment, not defects

- `PrimingError` (exit 2): a version the cache lacks.
- `holds release None, not the requested 2.12.0`, or `is not a managed repository`: the setup skipped or mis-ran a bootstrap (see above).
- `IntegrityError` in flow 8 naming `src/workflow_manager/__pycache__/`: the clone was not precompiled, or `PYTHONDONTWRITEBYTECODE=1` was dropped.
- Flow 8 refusing to run as root: add `--allow-root`, only when `id -u` prints `0`.
- A write refused inside the product clone is the sandbox limit. No flow writes there.

### Known limitations (out of scope)

- `verify` and `status` against a null record still end with `next: a release directory holding None is needed: run the command again with --release-dir DIR`, and `status` still reads `workflow None (full profile)`. These are plan section 5 (NRW-PL-R1-O1, NRW-PL-R1-O2), dispositioned as follow-up issues at acceptance. Not a regression.
- A record of `""` still prints `version: installed , release V`. Same class, same follow-up.
- A bare `--release-dir REL update` on a null record is not refused and prints no null step (NRW-PL-R2-O1). Kept as it is; follow-up.
- `docs/common-problems.md` keeps both repair alternatives for a null record. Kept as it is.
- No version is edited. The `fix:` title releases Manager 1.14.2 at acceptance.

## Next action

Functional review: run flows 1 to 8 in the order above, then the stand-in check, and report each exit code and expectation. Findings go to `.ai-review/null-record-wording/feedback/FUNCTIONAL_REVIEW.md`, then `/review-functional`. Once testing is clean, `/accept-milestone` is the only acceptance command.
