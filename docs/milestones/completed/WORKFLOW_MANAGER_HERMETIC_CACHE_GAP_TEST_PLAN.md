# Workflow Manager: The Cache-Inside-Git Status Test Is Hermetic (Revision 1)

`work_item_id: hermetic-cache-gap-test` -- `governing_workflow_version: "2.2"`

**Deliverable:** `test_an_unmanaged_target_with_a_cache_inside_git_is_the_known_gap`
takes its release from a local mirror instead of GitHub, so it passes with no
network, and it still pins the known gap (roadmap row 35, issue #189).

**Work item type:** `process`. **Base commit:** `8569235`
(`8569235357ed88edd5487bbc6db98fd4c4166bc7`, tip of `main`, Manager 1.14.8;
Workflow 2.29.0 installed, automatic gates). **Branch:**
`milestone/hermetic-cache-gap-test`. **Scope source:** issue #189 and the
owner's order of 2026-11-09 (priority high: the required check failed in 3 of
the last 4 runs of that day only because of this test). The pull-request title
is a `test:` change and **releases nothing**; check it with
`python3 tools/release/release.py check-title "test: ..."`. One mechanism: the
cache-inside-git status test is hermetic. Two checkpoints, two deliverable
files, nothing under `src/`.

## 1. Investigation (done at `8569235`, before any design)

* **The defect.** The test runs the real CLI with `--release-version 2.12.0
  --release-cache <empty dir inside .git>` and no source. `--release-cache`
  replaces the primed cache the other tests inherit through `pinned_env()`
  (`source.CACHE_ENV`), so the cache holds nothing and `status` downloads the
  release's `SHA256SUMS` and manifest from GitHub. A GitHub 504 fails the
  required check.
* **How its neighbours get a release.** The class `TestStatusContainment`
  extends `ux.TargetCase`, which only builds targets. Every test of the class
  that needs a release uses the inherited primed cache (`run("status", ...)`),
  or gives `--release-source` an empty mirror on purpose
  (`test_an_empty_local_source_leaves_no_status_cache_under_git`). The helpers
  that build a mirror of the newest release (`mirror()`, `workdir()`) live in
  `ux.ReleaseCase`, a subclass of `TargetCase` whose `setUpClass` only primes
  the shared cache (`support.release(PINNED_NEWEST)`, which `Pristine` already
  does for the class).
* **Why the test needs both.** Its point (roadmap 3.6) is that for an
  unmanaged target the containment check never runs, so a cache inside `.git`
  is accepted: exit 0, "not a managed repository". That needs the cache path
  inside git, and a release to put in it: a fetch from a source. Only the
  source can be local.
* **Measured on a scratch clone of `8569235` under `unshare -rn` (no network),
  non-root, a read-only link to the primed cache:** the test fails with exit 1,
  `error: cannot fetch https://github.com/RodrigoFAbreu/workflow/releases/
  download/v2.12.0/SHA256SUMS: ... Network is unreachable`. With the fix of
  section 2 the same command passes (the class: 10 tests OK), and the cache
  `.git/c` then holds `2.12.0` and `2.12.0.lock`: the release was fetched
  from the mirror into the cache inside git, which is the gap.
* **Who else reaches the network at test time.** Section 6.

## 2. Design

* **The fix.** `TestStatusContainment` extends `ux.ReleaseCase` (every other
  test of the class is unchanged and green: the class gains helpers and a
  cache priming it already has). The test passes `--release-source
  str(self.mirror())` and keeps `--release-cache <target>/.git/c`. The
  mirror is a copy of the three assets of the newest release in a temporary
  directory the case cleans up.
* **The test keeps its meaning and gains one pin.** Its assertions on exit 0
  and on "not a managed repository" stay. It also asserts the release landed
  in the cache inside git by the literal path
  `<target>/.git/c/<PINNED_NEWEST>`: without it, a cache moved out of `.git`
  would still pass and the test would no longer exercise the gap. Its comment
  becomes a docstring that says the release comes from a mirror so the test
  needs no network.
* **One sentence of `docs/ARCHITECTURE.md`.** After "After priming, a run needs
  no network." it says that no test fetches a release at test time: a test
  that runs the CLI against a release the cache does not hold gives it a
  `--release-source` mirror or a `--release-dir`. It names no milestone.
* **No `src/` change, no other test, no workflow file, no shard change.**

## 3. Failure-only mutations

Each on a fresh copy of the candidate, one at a time, the named test run
**with no network** (`unshare -rn`, section 5) from `tests/` with `python3 -B
-m unittest`. The unmutated candidate passes the class offline; each mutation
must make the named test fail and nothing else.

| # | Mutation | Must fail |
| --- | --- | --- |
| M1 | delete `"--release-source", str(self.mirror()),` from the test's argv | the test, offline (exit 1, `Network is unreachable`); it passes online, which is why the test runs offline |
| M2 | change the cache to `self.workdir() / "c"` (outside `.git`) | the test, on the new literal-path pin (the status still exits 0) |
| M3 | change the expected message to "a managed repository " | the test, on the message pin |
| M4 | change the expected exit code `0` to `1` | the test, on the exit pin |

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The hermetic test and its sentence | - | 1 | 1 |
| CP2 | Bookkeeping | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the hermetic test and its sentence

**Files:** `tests/test_operator_ux_report.py`, `docs/ARCHITECTURE.md`.

Section 2. Then, in order: the test offline in a scratch clone and M1 to M4
(section 3), `python3 tools/check_docs.py`, `python3 tests/run_all.py --select
test_operator_ux_report.py` and `--select test_docs.py`, and the full gate
`python3 tests/run_all.py` (with the network or the primed cache). The
evidence goes in the milestone record at CP2. Any other network-reaching test
found in section 6 is listed as a follow-up on #189 and not fixed here.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Row 35 of `docs/ROADMAP.md` is added by this plan as Current and is Done at
acceptance; `docs/ACTIVE_MILESTONE.md` records the milestone, the offline
measurement and the mutation results. No version is edited: a `test:` title
releases nothing. Both files stay excluded at both stages; the acceptance step
writes them.
<!-- /CP2 -->

## 5. Functional review

Flows 1 to 5 write nothing into the product clone and need no network: they
run in a clone `S/cand` of the branch head (`S=$(mktemp -d
"$HOME/.cache/hc-fr.XXXXXX")`, `git clone --no-hardlinks <product clone>
$S/cand`; `python3 -m compileall -q $S/cand/src`). Flows 6 and 7 are marked
"(needs the full environment)": they need the primed release cache that
`tests/run_all.py` needs, and run last. Offline means `env -i
PATH=/usr/bin:/bin HOME=$S/home XDG_CACHE_HOME=$S/cache TMPDIR=$S/tmp
PYTHONDONTWRITEBYTECODE=1 unshare -rn`, with `$S/cache/workflow-manager/
releases` a copy or a link of `~/.cache/workflow-manager/releases`.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `cd $S/cand && git diff --stat 8569235357ed88edd5487bbc6db98fd4c4166bc7 HEAD -- src tools tests docs/ARCHITECTURE.md .github` | exactly `tests/test_operator_ux_report.py` and `docs/ARCHITECTURE.md`; nothing under `src/`, `tools/`, `.github/` |
| 2 | `grep -n 'class TestStatusContainment\|"--release-source"' $S/cand/tests/test_operator_ux_report.py` | the class extends `ux.ReleaseCase`; the known-gap test passes `"--release-source"` with `str(self.mirror())` and keeps `"--release-cache"` on a path under `.git` |
| 3 | `grep -n 'not a managed repository\|returncode, 0' $S/cand/tests/test_operator_ux_report.py` and `sed -n '/def test_an_unmanaged_target_with_a_cache_inside_git/,/^$/p'` | the exit-0 and message assertions are still there, plus the literal `.git`/`c`/`PINNED_NEWEST` path pin, under a docstring that says the release comes from a mirror |
| 4 | `tr '\n' ' ' < $S/cand/docs/ARCHITECTURE.md \| tr -s ' ' \| grep -o 'After priming, a run needs no network.\{0,400\}'`; `git diff 8569235 HEAD -- docs/ARCHITECTURE.md \| grep '^+' \| grep -ci 'milestone\|hermetic-cache-gap'` | the sentence about `--release-source` and `--release-dir` follows; the count is `0` |
| 5 | in scratch copies of `$S/cand`, apply M1 to M4 with `sed` (one copy each), run `cd tests && <offline prefix> python3 -B -m unittest test_operator_ux_report.TestStatusContainment.test_an_unmanaged_target_with_a_cache_inside_git_is_the_known_gap`; first the unmutated copy | the unmutated copy: OK; M1, M2, M3, M4: each FAILED (1 failure), M1 with `Network is unreachable` in the message |
| 6 | (needs the full environment) in `$S/cand`: `python3 tools/check_docs.py`; `python3 tests/run_all.py --select test_operator_ux_report.py` and `--select test_docs.py` | exit 0 each, no `OrphanProcessError` |
| 7 | (needs the full environment) the same test offline in the unmutated copy, then the class `test_operator_ux_report.TestStatusContainment` offline | OK, 10 tests |

## 6. Network-reaching tests (follow-ups)

Measured, not only grepped. The full selection of an unmodified clone of
`8569235` (2363 units, 15952 tests) ran under `unshare -rn` with the primed
cache linked in: every fetch error of the 371 chunks names a host. Exactly one
names `https://github.com`: this item's test. One names `https://example.invalid`
(a test that asks for an unreachable host on purpose) and the rest name
`127.0.0.1:<port>`, the local servers of the discovery and release-source
tests, which fail only because `unshare -rn` leaves the loopback interface
down; that and the root user of the sandbox (`--allow-root`) account for the
other failures of that run (`test_parallel_runner`, `test_orphan_processes`,
`test_discovery`, ...), none of which fetch from a release host. The grep for a
CLI run with `--release-version` and no source, cache or directory
(`tests/test_operator_ux_docs.py`, `test_operator_ux.py`, `test_manager_version.py`,
`test_bootstrap.py`) finds runs that inherit the primed cache from
`pinned_env()`, and the offline run shows them passing. **No other
network-reaching test was found: the follow-up list is empty.** A different
sandbox with the loopback up would be needed to prove the loopback tests green;
that is not this item's claim.

## 7. Risks

* `ReleaseCase.setUpClass` primes the shared cache once more for the class,
  which `Pristine` already did; a machine with no cache still needs the
  network or a mirror at priming, as for every run.
* The literal-path pin ties the test to the cache's layout
  (`<cache>/<version>`), which `docs/ARCHITECTURE.md` documents and
  `TestCache` pins.
* Running the test file directly with `python3 -m unittest` (outside
  `run_all.py`) is not a gate path; it is used for the offline and mutation
  evidence only, as in earlier items.

## 8. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
