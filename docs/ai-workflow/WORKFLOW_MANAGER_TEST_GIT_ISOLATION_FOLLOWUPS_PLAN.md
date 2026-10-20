# Workflow Manager: Follow-ups to the Host-Test Git Isolation (Revision 2)

`work_item_id: test-git-isolation-followups` -- `governing_workflow_version: "2.2"`

**Deliverable:** the three small test-helper fixes the reviews of
`read-only-test-git-isolation` deferred (issue #74). Test code only: no
Manager behaviour change, no Manager release.

**Work item type:** `process` (test tooling). **Base commit:**
`2d44ed16b324c57f357a261397252618ede9a1a5` (tip of `main`; Workflow 2.18.1
installed, automatic gates, no `GATE_POLICY.json`). **Branch:**
`milestone/test-git-isolation-followups`. **Scope source:** `docs/ROADMAP.md`
row 10 and its section 10; issue #74; the owner's request of 2026-10-20. The
pull request title is `test: ...`, which releases nothing (checked with
`python3 tools/release/release.py check-title`).

## 1. The three fixes

1. **Empty entries of an inherited `GIT_CEILING_DIRECTORIES` survive.** Git
   reads an empty component as "stop resolving symlinks for the entries after
   it". `isolation.ceiling_with` and `support.no_repository_above` both split
   the inherited list and drop empty components, so `/mnt/a::/mnt/b` becomes
   `/mnt/a:/mnt/b`. Both keep every component when re-joining. An unset or
   empty inherited value still contributes nothing (not one empty entry). The
   scratch ceiling still leads, and the no-duplicate rules stay as they are:
   `ceiling_with` does not repeat `first` when it already leads, and
   `no_repository_above` drops an inherited entry equal to its own root.
2. **`no_repository_above` counts `root/.git` for every target at or below
   `root`.** Its bounded walk returns False at `root` before looking at
   `root/.git`, so an invalid `.git` directly in `root` is accepted, where the
   product refuses it: `compatibility._has_dot_git_above` walks `.git` entries
   independently of Git (`src/workflow_manager/compatibility.py:2167`) and
   `protected_set` refuses containment when it finds one (`:2187`). Git's
   ceiling excludes the ceiling directory from *discovery* for a start below
   it, but that is not the product's behaviour, and the helper exists to mimic
   the product's walk, so it must not mask a product refusal that involves a
   test-owned `root/.git`. The walk checks `directory/.git` before the stop
   comparison, so `root/.git` counts for a target equal to or below `root`;
   only entries strictly above `root` stay excluded (review EPR-001).
3. **The subprocess in `TestAncestorRepositoryIsolation` gets a timeout of
   120 seconds.**
   `test_the_two_named_tests_pass_with_a_stray_repository_above_their_temporary_directory`
   calls `subprocess.run` with none, so a hang is bounded only by the chunk
   timeout. The two named tests run in a few seconds, so 120 s leaves wide CI
   headroom while still far below the chunk timeout; the precedent is
   `support.run_suite`'s `timeout=` argument (`tests/support.py`). A
   `subprocess.TimeoutExpired` already names the command and the bound, so a
   timeout failure identifies the subprocess and the 120 s.

Out of scope: anything under `src/` and `tools/` (the acceptance check is an
empty `git diff 2d44ed1 -- src tools`), the pins, the lock, the runner's
other behaviour, the docs (nothing they say changes).

## 2. Open decisions

| # | Decision | Recommendation | Why |
| --- | --- | --- | --- |
| D1 | Share one join helper between `isolation.py` and `support.py` | No; fix each in place | `support.py` does not import the runner package and each join has its own duplicate rule; two three-line changes are smaller than a new shared module |
| D2 | Make `root/.git` count for every target at or below `root` | Yes (reverses revision 1, which limited it to the target `root`; review EPR-001) | The product's own walk counts `root/.git` for a target below `root` and refuses; Git's ceiling semantics are not the product's, and accepting it would hide that refusal. Entries strictly above `root` stay excluded |

No row of `docs/TECHNICAL_DECISIONS.md` exists in this repository, so no
listed open decision is finalized here.

## 3. Tests (red first)

Each defect regression lands before its fix and is shown failing without it
(against `2d44ed1`). Some cases pass today by design and are **guards**, not
red tests: an empty or unset inherited value adds no empty entry, and the whole
value is restored on exit. At implementation the evidence records which tests
were shown red and which are guards (LPR-001, EPR-003). Expected red: the
empty-component cases, both `root/.git` refusals (target `root` and target
below `root`) and the timeout capture.

* `tests/test_orphan_processes.py`, next to the existing ceiling tests of
  `TestChunkEnvGitConfig`: an inherited `/mnt/a::/mnt/b` keeps its empty
  component after the private `TMPDIR`; a nested call stays idempotent for it;
  an empty inherited value adds no empty entry.
* `tests/test_read_only.py`, `TestAncestorRepositoryIsolation`: inside
  `no_repository_above` an inherited `/mnt/a::/mnt/b` is kept (empty component
  included) behind the root, and the whole value is restored on exit; an
  invalid `.git` directly in `root` is refused through the helper both when the
  target is `root` and when it is a plain directory below `root`, while a
  `.git` strictly above `root` is still ignored; the subprocess call carries
  `timeout=120` exactly (the call is captured with `subprocess.run` patched).

<!-- CP1 -->
## 4. Checkpoint CP1 -- the three test-helper fixes

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The three #74 test-helper fixes, each with a test that fails without it | - | 2 | 1 |

**Files:** `tests/parallel/isolation.py`, `tests/support.py`, `tests/test_orphan_processes.py`, `tests/test_read_only.py`, `docs/ROADMAP.md`.

Section 1's three fixes with section 3's tests, red first for each defect regression. The row 10
of `docs/ROADMAP.md` becomes Current at the start and Done at acceptance.
Evidence: each defect regression shown failing before its fix (guards named as such) and passing after;
`python3 tests/run_all.py --select test_orphan_processes.py` and `--select
test_read_only.py` green; the full gate `python3 tests/run_all.py` green
(the known SIGINT flake of workflow#32 rerun alone if it is the only
failure); `git diff 2d44ed1 -- src tools` empty.
<!-- /CP1 -->

## 5. Risks

* The empty-entry change touches the runner's environment for every chunk.
  Only an inherited value with an empty component differs from today, and the
  scratch ceiling still leads, so the Git discovery bound is unchanged.
* The `root/.git` case changes a test helper only. Both current callers pass a
  scratch directory below a `root` that holds no `.git`, so their results do
  not change; a test that planted `root/.git` and expected acceptance would now
  see the refusal (none exists today).
