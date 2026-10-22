# Workflow Manager: Last Follow-ups to the Host-Test Git Isolation (Revision 1)

`work_item_id: test-git-isolation-followups-2` -- `governing_workflow_version: "2.2"`

**Deliverable:** the two items issue #74 still lists after
`test-git-isolation-followups` (PR #76): a docstring and a guard for the valid-repository
boundary of `no_repository_above`, and empty ceiling markers tested at every
position. Test code only: no Manager behaviour change, no Manager release.

**Work item type:** `process` (test tooling). **Base commit:** `7ac6c26` (tip
of `main`; Workflow 2.18.2 installed, automatic gates, no `GATE_POLICY.json`).
**Branch:** `milestone/test-git-isolation-followups-2`. **Scope source:**
`docs/ROADMAP.md` row 11 and its section 11; issue #74 and its comment; the
owner's go of 2026-10-21. The pull request title is `test: ...`, which
releases nothing (checked with `python3 tools/release/release.py check-title`).

## 1. The two items

1. **Document the valid-repository boundary of `no_repository_above`.** The
   helper puts Git's ceiling at `root`. With a *valid* repository at `root`
   and a target below it, Git no longer finds that repository, while the
   helper's `.git` walk still counts `root/.git`, so the helper refuses
   (`ContainmentError`) where the unbounded product finds the repository and
   protects it. This fails closed and affects no current caller. The
   docstring says so and advises a fixture that needs such a repository to
   pass a `root` above it. A guard pins it cheaply: with a valid repository at
   `root` and a plain target below it, the product without the helper accepts
   and protects that repository, the helper with `root` refuses, and the
   helper with a `root` above the repository accepts and still protects it.
   It is a **guard** (the behaviour exists today), labelled as such.
2. **Empty ceiling markers at every position.** The existing empty-component
   tests exercise only an internal marker (`/mnt/a::/mnt/b`). Both
   `isolation.ceiling_with` (through `chunk_env`) and
   `support.no_repository_above` already keep every component, so the tests
   for a leading (`:/mnt/a`), trailing (`/mnt/a:`) and repeated
   (`/mnt/a:::/mnt/b`) marker are **guards**: each asserts that the result is
   the scratch ceiling followed by the inherited components split on the path
   separator, empty ones included, and that the value is restored on exit
   (`no_repository_above`) or stable under a nested call (`chunk_env`). They
   are parameterised with `subTest` and the internal case joins the same
   table.

Out of scope: anything under `src/` and `tools/` (the acceptance check is an
empty `git diff 7ac6c26 -- src tools`), the helpers' behaviour, the pins, the
lock, the runner.

## 2. Open decisions

| # | Decision | Recommendation | Why |
| --- | --- | --- | --- |
| D1 | Change the helper to find a valid repository at `root` | No; document it | Refusing is the safe direction, no caller needs the other, and a ceiling above the repository already gives the product's answer |
| D2 | One table of marker positions shared by both test files | No; each file keeps its own three-line table | The files do not import each other and the cases are one line each |

No "Open decision" row of `docs/TECHNICAL_DECISIONS.md` is touched (this
repository has none).

## 3. Tests

Every new test is a **guard**: the code already handles each case, so none
is red first and none is claimed as a regression test. The evidence records
that, and shows each guard passing.

* `tests/test_orphan_processes.py`, next to the existing ceiling tests of
  `TestChunkEnvGitConfig`: the internal, leading, trailing and repeated
  inherited values, each by `subTest`, give the private `TMPDIR` followed by
  the inherited components with empty ones kept, and a nested call returns the
  same value.
* `tests/test_read_only.py`, `TestAncestorRepositoryIsolation`: the same four
  values by `subTest` inside `no_repository_above`, the value restored on
  exit; and the valid-repository guard of item 1.

<!-- CP1 -->
## 4. Checkpoint CP1 -- the docstring and the guards

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The valid-repository docstring and guard, and empty ceiling markers at every position | - | 2 | 1 |

**Files:** `tests/support.py`, `tests/test_orphan_processes.py`, `tests/test_read_only.py`, `docs/ROADMAP.md`.

Section 1's two items with section 3's guards. Row 11 of `docs/ROADMAP.md`
becomes Current at the start of the plan and Done at acceptance.
Evidence: the new guards passing and named as guards;
`python3 tests/run_all.py --select test_orphan_processes.py` and `--select
test_read_only.py` green; the full gate `python3 tests/run_all.py` green
(the known SIGINT flake of workflow#32 rerun alone if it is the only
failure); `git diff 7ac6c26 -- src tools` empty. The reviewer's checks run
offline as written; the full gate is not a required reviewer flow.
<!-- /CP1 -->

## 5. Risks

* The guards read the environment of the helper only; none changes product
  code, so the risk is a flaky ceiling assumption on a host that inherits a
  `GIT_CEILING_DIRECTORIES`. Each test sets the inherited value itself.
* The docstring is the only non-test edit to `tests/support.py`; behaviour is
  untouched.
