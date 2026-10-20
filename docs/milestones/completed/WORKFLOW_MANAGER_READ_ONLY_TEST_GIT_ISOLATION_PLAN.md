# Workflow Manager: Host Tests Isolated from a Stray Ancestor `.git` (Revision 3)

`work_item_id: read-only-test-git-isolation` -- `governing_workflow_version: "2.2"`

**Deliverable:** a green change stays green when another process leaves a
`.git` above the test scratch (the shared `/tmp`). Test and runner code only:
no Manager behaviour change, no Manager release.

**Work item type:** `process` (test tooling). **Base commit:**
`2d1d5af389130d63e9b250d81c923e2c4dc8f81d` (tip of `main`; Workflow 2.18.1
installed, automatic gates, no `GATE_POLICY.json`). **Branch:**
`milestone/read-only-test-git-isolation`. **Scope source:** `docs/ROADMAP.md`
row 9 and its section 9; issue #66; the owner's go of 2026-10-20. The pull
request title is `test: ...`, which releases nothing (checked with
`python3 tools/release/release.py check-title`).

## 1. Problem and findings

The runner gives each chunk a private `TMPDIR`
(`<run dir>/tmp/<chunk>/`, `isolation.chunk_path`), and the run directory is
`tempfile.mkdtemp(prefix="wm-run-")` under the system temp directory. So every
test scratch lives under `/tmp/wm-run-*/tmp/...`, and a `/tmp/.git` made by
another process is an ancestor of all of it.

I reproduced both forms on this machine by pointing `TMPDIR` at a disposable
tree that holds a planted `.git` (never the real `/tmp`) and running the full
selection (`python3 tests/run_all.py`):

| Planted ancestor | Result | Failing tests |
| --- | --- | --- |
| an empty `.git` directory holding only `config.worktree` (the form seen on 2026-10-18 and 2026-10-19) | exit 1 | `test_read_only.py::TestContainmentFailsClosed::test_a_plain_directory_that_git_reports_as_no_repository_is_still_accepted` and `test_read_only.py::TestPlanDestinations::test_a_target_with_no_git_directory_protects_its_work_tree` (nothing else) |
| a valid repository (`git init`) | exit 1 | the same two, plus `test_compatibility.py::TestIncompleteInspection::test_not_a_git_repository`, the four `test_conformance_suite.py` / `test_bootstrap_e2e.py` / `test_update_path.py` fixture checks that assert over the frozen suites, and the frozen `workflow_state_test.py` and `workflow_state_completion_obligations_test.py` suites in all four fixtures (their `*unresolvable*` / `*not_a_git_repository*` cases, which expect a plain directory to be no repository) |

`test_parallel_runner.py::TestLockAndRecoveryThroughTheCli`'s SIGINT case also
failed twice in those runs, but it passed five of five reruns of that class
(three with the stray planted, two without): it is the known real-process
timing flake (workflow#32), unrelated, and out of scope.

**Why the issue's `GIT_CEILING_DIRECTORIES` alone is not enough.** The two
named tests fail for a second reason that Git's ceiling cannot reach.
`compatibility.protected_set` accepts a plain directory only when Git reports
no repository **and** `_has_dot_git_above(target)` finds no `.git` entry at or
above it, a `lexists` walk over the real path's ancestors that does not ask
Git (`src/workflow_manager/compatibility.py`, `_has_dot_git_above`). That is
deliberate fail-closed behaviour: any `.git` entry above the target, valid or
not, refuses the destination. The product is correct and stays unchanged.
Verified: with the empty stray, `git rev-parse --absolute-git-dir` already
reports "not a repository" (exit 128), and the refusal comes from the path
walk.

So two different mechanisms cover the two causes:

1. Git discovery (valid ancestor repository; the frozen suites cannot be
   edited here): `GIT_CEILING_DIRECTORIES` set by the runner to the chunk's
   private `TMPDIR`. Git then never ascends into that directory, so nothing
   above the scratch is discovered, in the host tests, in the frozen suites
   and, through `support.pinned_env` (4.2), in the `workflow_manager` CLI
   subprocesses host tests start. The current directory and everything below the ceiling are
   unaffected, so each test's own repositories (always created below `TMPDIR`)
   still resolve normally; the checkout under test lives outside `TMPDIR`.
   The ceiling bounds Git only: a CLI subprocess run against a plain
   directory still meets the product's unbounded path walk (D2), so such a
   test must create its plain directory where no ancestor can hold a `.git`,
   or not rely on the "no repository" answer.
2. The product's path walk (the two named tests, which assert exactly the
   "plain directory is accepted" path): a test-local helper that bounds the
   walk, and the ceiling, at the test's own scratch root.

Tests that legitimately need upward discovery: none found. The full-run
experiment above is the evidence; CP2, once both mechanisms exist, re-runs it
with the fix and both plantings and the run must be green. (CP1 alone cannot
pass a planted full gate: the two named tests fail on the product's path walk
until CP2's helper wraps them -- external review EPR-001.)

## 2. Scope

In scope: `tests/parallel/isolation.py` (`chunk_env`), a helper and
`pinned_env` in `tests/support.py`, the two tests, regression tests, docs. Out of scope:
anything under `src/` and `tools/` (the acceptance check is an empty
`git diff 2d1d5af -- src tools`), the pins, the lock, `tests/parallel/unit.py`
(`launch` and `unit_env` are unused by the executor, which goes through
`isolation.run_chunk`), the frozen suites, and the SIGINT flake.

## 3. Open decisions

| # | Decision | Recommendation | Why |
| --- | --- | --- | --- |
| D1 | Where the ceiling goes: runner (`chunk_env`), the tests, or both | Runner for Git discovery; a test-local helper for the product path walk | The runner is the only place that reaches the frozen suites; the helper is the only thing that reaches the path walk; no other test needs either |
| D2 | Make the product honour `GIT_CEILING_DIRECTORIES` in `_has_dot_git_above` | No | It would loosen a fail-closed safety check for every user to fix a test-environment problem; the issue itself says the product is right |
| D3 | A runner preflight that refuses (exit 2) when an ancestor of the run directory holds `.git` | No | It would turn a red-looking green change into a differently red one; the goal is a gate that stays green |
| D4 | Ceiling value | The chunk's private `TMPDIR`, prepended to any inherited ceiling list | Its children are the whole scratch; an inherited entry (a user's network mount) is kept; the value is idempotent across `chunk_env(chunk_env(...))` |
| D5 | Regression shape | Unit proof on `chunk_env` with a planted valid repository, plus an end-to-end rerun of the two named tests in a subprocess whose `TMPDIR` sits below a planted `.git` (empty form and valid form) | The end-to-end test fails if either the helper or the two tests' use of it is removed; the unit proof fails without the runner ceiling |

No row of `docs/TECHNICAL_DECISIONS.md` exists in this repository (the file is
absent), so no listed open decision is finalized here.

## 4. Design

### 4.1 Runner

`isolation.chunk_env(tmpdir, ...)` adds `GIT_CEILING_DIRECTORIES` to the
returned environment: `str(tmpdir)` first, then any inherited entries, unless
`str(tmpdir)` is already the first entry (idempotent). Nothing else about the
environment changes. `executor.prepare_merge` is the second `chunk_env` caller
(`chunk_env(self.run_dir / "tmp", ...)`): the merge-preparation subprocess gets
its ceiling at `<run dir>/tmp`, the parent of every chunk `TMPDIR`, which is
harmless and correct. `check_git_env` is untouched (the ceiling is not a
`GIT_CONFIG_*` series).

### 4.2 Test helper

`support.pinned_env` (which `cli_env` and `mirror_env` build on) builds its
environment from scratch and would drop the runner's ceiling, so it copies
`GIT_CEILING_DIRECTORIES` from `os.environ` when set, the way it already copies
`WORKFLOW_MANAGER_RELEASE_SOURCE`.

`tests/support.py` also gains `no_repository_above(root)`, a context manager that,
for its duration, (a) sets `GIT_CEILING_DIRECTORIES` in `os.environ` to
`root` (kept in front of inherited entries) and (b) replaces
`compatibility._has_dot_git_above` with a walk that stops at `root`
(exclusive, the way Git treats a ceiling; paths are compared as real paths,
because `_has_dot_git_above` walks `os.path.realpath(target)`, so the walk
stops at `os.path.realpath(root)` and a `TMPDIR` behind a symlink such as
macOS `/var` -> `/private/var` still meets it; the ceiling value itself stays
as given, since Git resolves symlinks in ceiling entries), so `.git` entries at or below the
target and inside `root` still refuse. Both are restored on exit. The two
named tests wrap their body in `with support.no_repository_above(self.work):`.

### 4.3 Regression tests

* `test_orphan_processes.py::TestChunkEnvGitConfig` gains tests that
  `chunk_env` sets the ceiling to the private `TMPDIR`, keeps an inherited
  entry after it, and is idempotent; and a test that plants a valid
  repository in a disposable tree above a chunk `TMPDIR` and shows `git
  rev-parse` in a plain subdirectory finds it without the ceiling and reports
  "not a git repository" with `chunk_env`'s environment.
* A check, placed in the existing test module that
  already covers `support.pinned_env`/`cli_env` (found at implementation time;
  `test_orphan_processes.py` otherwise): `pinned_env()` and `cli_env()` carry
  an inherited `GIT_CEILING_DIRECTORIES` and carry none when it is unset.
* `test_read_only.py` gains `TestAncestorRepositoryIsolation`: in a disposable
  tree under its own scratch it (a) pins that the product still refuses a
  target below a planted `.git` without the helper, (b) shows
  `plan_destinations` accepts the plain directory inside the helper, for the
  empty and the valid planting, and (c) reruns the two named tests in a
  subprocess (`python3 -m unittest`, `cwd=tests/`, `TMPDIR` below the planting,
  the runner's ceiling scrubbed from the environment) and requires exit 0.
  The planting is always below the test's own scratch, never `/tmp`.

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The runner's Git discovery ceiling: chunk_env sets GIT_CEILING_DIRECTORIES to the chunk's private TMPDIR and support.pinned_env forwards it, with unit tests and an unplanted full gate | - | 2 | 1 |
| CP2 | The product-path helper support.no_repository_above, its use in the two named tests, the end-to-end regression class, and the docs | CP1 | 3 | 1 |

<!-- CP1 -->
### CP1 -- the runner's Git discovery ceiling

**Files:** `tests/parallel/isolation.py`, `tests/support.py` (pinned_env), `tests/test_orphan_processes.py`.

`chunk_env` sets `GIT_CEILING_DIRECTORIES` (4.1), `pinned_env` forwards it
(4.2) and the unit tests of 4.3's first and second bullets land with it. Evidence,
achievable with CP1's work alone: `--select test_orphan_processes.py` and
`--select test_parallel_runner.py` green, the unit proof that `git rev-parse`
below a planted repository finds nothing under `chunk_env`'s environment, and
the ordinary full gate green apart from the SIGINT flake, which is rerun alone.
No planted-ancestor full gate is claimed here: the two named tests still meet
the product's path walk until CP2.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the product-path helper, the two tests, the end-to-end regression, docs

**Files:** `tests/support.py`, `tests/test_read_only.py`, `docs/ARCHITECTURE.md`, `docs/development.md`, `docs/ROADMAP.md`.

The helper (4.2), its use in the two named tests, `TestAncestorRepositoryIsolation`
(4.3). Docs: `docs/ARCHITECTURE.md`'s "Verification execution" gains a
bullet saying the runner gives every chunk a Git discovery ceiling at its
private `TMPDIR`, that `pinned_env` forwards it to CLI subprocesses, that the product's `.git`
walk is path-based and is bounded per test by `support.no_repository_above`,
and that a stray ancestor `.git` therefore cannot turn a change red -- except
that a CLI subprocess run against a plain directory still meets the unbounded
walk, so such a test creates its directory where no ancestor can hold a `.git`; `docs/development.md` gains one sentence
under "Tests" saying new tests that need a plain directory use the same helper
and never rely on `/tmp` being free of a repository (the CLI-subprocess limit is stated there too). `docs/ROADMAP.md` row 9
becomes Current now and Done at acceptance. Evidence: `--select
test_read_only.py` and `--select test_docs.py` green; the regression class
fails with the helper removed (shown once, then restored); the final full gate
green under both plantings (empty and valid), `TMPDIR` below each, apart from
the SIGINT flake, which is rerun alone; `git diff 2d1d5af -- src tools` empty.
<!-- /CP2 -->

## 6. Tests

Section 4.3. Existing tests are unchanged apart from the two named ones
(wrapped in the helper).

## 7. Risks

* A ceiling at the chunk `TMPDIR` would hide a repository created at `TMPDIR`
  itself and queried from below it, and Git still ascends from a cwd that
  equals the ceiling (verified), so a Git command run with cwd exactly the
  chunk `TMPDIR` still discovers a stray ancestor; `tempfile` always makes a
  subdirectory, so this is small. None exists; the planted full runs in CP2 prove it.
* `support.no_repository_above` patches a private product function. The
  regression class pins the product's unpatched fail-closed behaviour, so the
  patch cannot silently become the only thing that is tested.
