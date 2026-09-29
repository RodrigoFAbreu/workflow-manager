# Workflow Manager: Trunk Model, Manager Releases and the Stopgap Test Profile (Revision 3)

`work_item_id: workflow-manager-trunk-model` -- `governing_workflow_version: "2.2"`

**Deliverable:** this repository works trunk-based, like the Workflow
Controller and SignalHub: a protected `main` changed only through
squash-merged pull requests whose Conventional-Commit title decides the
release; the Git tag as the only version authority; an automatic Workflow
Manager package release from `main`; a per-commit CI concurrency group for
`main`; and the stopgap test profile (a pull request runs the host tests
plus the newest Workflow release only, `main` and a nightly run keep the
full matrix), with all six of its rules.
**Governing workflow version:** `2.2` (the config default at creation).
**Work item type:** `process` (repository tooling and operating model; no
Workflow release, no product code).
**Base commit:** `b856a97346849fdf48bcdba2d6a5a9644699ab4b` (tip of `main`;
installed Workflow `2.6.0`, protocol `2.2` active).
**Branch:** `milestone/workflow-manager-trunk-model`, created from the base.
This repository has no Workflow Controller repository policy, so the
Controller does not create branches here; the milestone reaches `main`
through one pull request (section 9).
**Scope source:** `docs/ROADMAP.md` "At a glance" step **M1** and section
**10.1**, plus the user's milestone brief of 2026-09-29, whose seven
decisions are fixed inputs (section 1.1), not open questions.

**M1 releases the Manager only. It creates no Workflow release, and
`distribution/` stays byte-identical to the base (INV-1).**

## 1. Goal

### 1.1 Fixed inputs (decided by the user; this plan only says how)

1. **Trunk model**: a protected `main`, changed only through pull requests;
   required checks; no direct or force pushes and no deletion; "branches
   must be up to date" **not** required; one short-lived branch per
   milestone.
2. **Squash merges only, auto-merge enabled**, as in SignalHub (squash
   commit title = PR title).
3. **The PR title is a Conventional Commit**, validated by a required
   `PR title` check, and becomes the squash commit's subject. `feat` is a
   minor release, `fix` a patch, `!` a major; `docs`, `chore` and `ci`
   merge without a release.
4. **The Git tag is the only version authority.** `pyproject.toml` holds no
   hand-maintained version; the release computes the next version from the
   latest tag plus the commit types and sets the package version at build
   time; nobody edits a version by hand. This plan decides the first
   release's version (section 5.2, `OD-1`).
5. **A Manager package release is published from `main`**: built,
   verified, tagged, and a GitHub release with the artifact and
   `SHA256SUMS`; releases are serialized. It contains no Workflow release.
6. **A per-commit CI concurrency group for `main`**, so an intermediate
   `main` run is never cancelled.
7. **The stopgap test profile**, with its six rules each planned,
   implemented and tested (section 6).

### 1.2 What "done" means

- A pull request whose title is not a Conventional Commit cannot merge; its
  title check names the problem and, when valid, the release impact.
- Merging a `feat`/`fix`/`!` pull request produces exactly one GitHub
  release `vX.Y.Z` with a wheel, an sdist and `SHA256SUMS`, after -- and
  only after -- `main`'s full verification run for that commit is green. A
  `docs`/`chore`/`ci`/`test`/`style` pull request produces none.
- `workflow-manager --version` reports the release version for a released
  package, the tag version for a clean checkout exactly at a release tag,
  and "development build" otherwise.
- A pull request runs the host tests plus the newest Workflow release,
  unless a rule escalates it to the full matrix; `main` pushes and the
  nightly run always run the full matrix.
- The one required test check, `aggregate`, keeps its name whatever the
  shard count and profile.
- `python3 tests/run_all.py` (the local gate) still runs the full
  selection, unchanged.

## 2. Non-goals

- **No Workflow release and no change to `distribution/` or `migration/`**
  (INV-1). No change to `scripts/`, `.claude/commands/`, the managed
  `workflow-conformance.yml`, or the managed part of `CLAUDE.md` (INV-3).
- **Not M2.** No packaged Workflow releases, no `workflow` repository, no
  download/verify/install of Workflow packages, no removal of
  `distribution/`. The stopgap profile is removed by M2, not here.
- **Not W1/W2.** No Orchestration Protocol, no gate policy.
- **Nothing in the Workflow Controller repository.** In particular, no
  `.workflow-controller/policy.json` here (decision `OD-4`, section 8).
- **No change to the local gate.** Every Workflow gate in this repository
  still runs `python3 tests/run_all.py`, the full selection. The reduced
  selection is a CI pull-request check only (section 6.6).
- **No test is removed, skipped or weakened.** The full selection, its
  pinned counts and its exact-exception equality are unchanged; the
  stopgap only chooses *which selection a pull request's CI runs*.
- **No push, pull request, merge or settings change is made by an agent.**
  The managed `CLAUDE.md` says "Never push, merge, rebase, force-push, or
  open a pull request", and INV-3 keeps that text byte-identical, so this
  plan does not override it. Every push, pull request (M1's own and the C1
  probes), repository-settings or ruleset change, and merge is a **user**
  action at the cutover points section 9 names. `docs/RELEASING.md` and
  section 9 give the user the exact commands. No checkpoint exit, and no
  item of 1.2 that an agent must bring about, depends on one of those
  actions.

## 3. Investigation findings (measured at the base commit)

### 3.1 Packaging and version today

- `pyproject.toml`: setuptools (`setuptools>=68`, `setuptools.build_meta`),
  `name = "workflow-manager"`, static `version = "1.0.0"`, `src/` layout,
  console script `workflow-manager = "workflow_manager.cli:main"`. No
  runtime dependencies.
- **Nothing reads the version.** `grep` over `src/`, `tests/`, `tools/`
  finds no `importlib.metadata`, `__version__` or `pyproject` reader;
  `.workflow-manager/installation.json` records the *Workflow* version, not
  the Manager's. The CLI has no `--version`.
- **The Manager only works from a checkout.** `cli.py:45`:
  `MANAGER_ROOT = Path(__file__).resolve().parent.parent.parent`, and every
  command reads `<MANAGER_ROOT>/distribution/workflow/`. The user's install
  is `pipx install --editable <checkout>` (pipx metadata:
  `package_or_url` = the checkout, `pip_args: ["--editable"]`,
  `package_version: "1.0.0"`), so `MANAGER_ROOT` is the checkout. A wheel
  installed normally resolves `MANAGER_ROOT` to the environment's
  `lib/python3.X/`, which has no `distribution/`: `releases` prints the
  misleading "no distribution/ -- run tools/migrate.py first".
- `distribution/` is 48 MB (345 tracked files); `git archive HEAD | gzip`
  is 20.5 MB. The `build` frontend is **not** installed locally
  (`import build` fails; system Python 3.14.7, PEP 668-managed pip); CI
  can `pip install` it.

### 3.2 Tags, releases and GitHub settings (read-only `gh api`)

- **Tags exist locally, not on the remote.** `git tag`: the annotated
  `workflow-manager-v1.0.0` ("Workflow Manager v1.0.0 -- bootstrapper
  foundation", on `8a60eba`, 2026-09-05) and `bootstrapper-v1.0.0-rc1` (on
  `759d0da`). `git ls-remote --tags origin` lists none. `gh release list`
  lists none. Neither tag has the strict `vX.Y.Z` form.
- **Repository:** public; `allow_squash_merge`, `allow_merge_commit`,
  `allow_rebase_merge` all `true`; `squash_merge_commit_title:
  COMMIT_OR_PR_TITLE`, `squash_merge_commit_message: COMMIT_MESSAGES`;
  `allow_auto_merge: false`; `delete_branch_on_merge: false`; no rulesets;
  `main` not protected; default workflow permissions `read`.
- **CI history:** the last `main` push runs (`b856a97`, `b3010ba`) are
  green for both workflows. PR runs of `docs/roadmap-reorganization` show
  two `cancelled` verification runs, which is the per-ref PR group working
  as designed. The per-ref group also covers `main`, where it can cancel a
  pending intermediate run: the sharding milestone's open follow-up.

### 3.3 SignalHub, the model (read-only, `RodrigoFAbreu/SignalHub` at `v2.15.0`)

- `pr-title.yml`: `pull_request` types `opened, edited, reopened,
  synchronize`; one job, `name: Conventional Commit title`, running
  `python scripts/release/release.py check-title "$TITLE"` -- the same
  stdlib code the release uses. Regex
  `^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9._/-]+)\))?(?P<breaking>!)?: (?P<description>\S.*)$`;
  types `feat fix perf refactor docs test build ci chore style revert`.
- `release.py`: strict tags `vX.Y.Z`; latest = highest strict tag in
  `git tag --merged HEAD`; subjects from `git log --first-parent
  <tag>..HEAD`; bump = max over them; a non-Conventional subject counts as
  a patch with a `::warning::`; no subjects means nothing to release.
- `release.yml`: `push` to `main`; `concurrency: release,
  cancel-in-progress: false` (a superseded pending run is covered by the
  next run's catch-up); the release re-runs CI as a reusable workflow
  before releasing; `gh release create "$NEXT" --target "$GITHUB_SHA"
  --generate-notes assets/*` creates tag and release in one step, so a
  failure before it leaves no tag.
- Packaging: `sdk/python/pyproject.toml` keeps a static placeholder
  `version = "0.0.0.dev0"`, never rewritten in the repository;
  `sdk_files.py` copies the project to a temporary directory, substitutes
  exactly one placeholder line, runs `python -m build`, installs the wheel
  into a fresh venv and requires `--version` to print exactly the version.
  CI runs the same script with `0.0.0+ci`. The CLI reports
  `importlib.metadata.version(...)`, or "development build" for a `.dev`
  version or a missing distribution.
- Settings: squash only, `squash_merge_commit_title: PR_TITLE`,
  `squash_merge_commit_message: BLANK`, auto-merge on, delete branch on
  merge; one ruleset on `~DEFAULT_BRANCH`: `deletion`, `non_fast_forward`,
  `required_linear_history`, `pull_request` (0 approvals, squash only),
  `required_status_checks` (GitHub Actions app, integration id `15368`),
  no bypass actors.
- **Two deliberate differences here.** (a) SignalHub releases every commit
  (a `docs` commit is a patch release); fixed input 3 says `docs`, `chore`
  and `ci` release nothing, so this plan has a "none" impact (5.1).
  (b) SignalHub requires "branches up to date" (`strict: true`); fixed
  input 1 says not here.

### 3.4 The Workflow Controller (read-only, installed and source `1.3.0`)

- An absent `.workflow-controller/policy.json` means milestone branches and
  releases are both off; the Controller runs the plain lifecycle on the
  current branch (`controller/repo_policy.py:290-297`).
- A policy must carry a **complete `release` section even when disabled**
  (`_parse_release` never branches on `enabled`), whose only admissible
  values are `trigger: "version_change"` and `version_source.kind:
  "pyproject"` -- the model fixed input 4 removes.
- Its draft pull request is titled with the **bare work-item id**
  (`milestone_branch.py:1101`), which is not a Conventional Commit, and its
  body tells a human to merge with "Create a merge commit". A squash merge
  is recorded as `MERGED_REWRITTEN` and gated once as
  `merge_method_rewrote_history`, with no automatic close-out
  (`milestone_branch.py:887-897`).
- The Controller's own C1 (squash merges, Conventional-Commit titles, tags
  as the version authority, a `MERGED_SQUASHED` close-out) is in
  `PLANNING`; its schema is not written yet.
- Policies are read from the committed tree at `HEAD`; adopting a
  hand-made branch needs the policy at `merge-base(origin/main, HEAD)`.

### 3.5 The test matrix and the cost of each profile

- `python3 tests/run_all.py --list` at the base: **4042 units** = 148 host
  classes + 3894 frozen classes (per release and fixture: `2.3.1` 223,
  `2.4.0` 233, `2.5.0` 265, `2.5.1` 266, `2.6.0` 311, each x3 fixtures).
- CI timing estimates (`tests/parallel/timings.json`, profile `ci`):
  host 467 s; frozen `2.3.1` 854 s, `2.4.0` 902 s, `2.5.0` 939 s, `2.5.1`
  946 s, `2.6.0` 2018 s; total 6125 s.
- **The newest-release selection**: every host class except the 12 matrix
  host classes of `2.3.1`-`2.5.1`, which leaves 136 host classes, plus the
  3 x 311 frozen classes of `2.6.0`, for **1069 units**. The planner
  (`--plan-only --profile ci`, emulated with `--select`) gives `n=11`
  shards, 2503 s of work, a predicted 263 s makespan. The full selection
  gives `n=16`, 6195 s, 423 s predicted (7.6-9.3 min measured). So a pull
  request does about 40 % of the full run's work and should take roughly
  4-6 min with GitHub's queueing.
- The existing CI structure tests (`tests/test_parallel_runner.py`,
  T-CI-1..5) pin the current triggers (`pull_request`, `push`,
  `workflow_dispatch`) and the per-ref concurrency group. They change with
  this milestone (6.4), and their stdlib YAML-subset parser
  (`load_workflow_yaml`) is reused for the new workflow files.

### 3.6 Squash merges and the Workflow's git-history readers

Squash merging (fixed input 2) drops a milestone branch's individual
commits and their `Workflow-*` trailers from `main`'s history. The body is
blank (`squash_merge_commit_message: BLANK`), so no trailer is copied onto
`main` either. A static read of the installed `scripts/workflow_state.py`
finds four kinds of history reader:

1. **Within-milestone readers**, for example `Workflow-Checkpoint` in
   `base_commit..head`, the bundle-generation-record chain, and the
   plan-approval trailers. They all run on the milestone branch before the
   merge, while those commits exist.
2. **The origination reference** (`rev-list --all --full-history --
   WORKFLOW_STATE.json`, `WFR-66`). It reads state *content*. The squash
   commit carries the item's final state, and a terminal item's id cannot
   be re-routed (`route_work_item` refuses `MILESTONE_COMPLETE` reuse).
3. **The activation trailer** (`Workflow-Activation: 2.2`). It is already
   on `main`, in pre-M1 history, which squash merges never rewrite.
4. **`_resolving_commits_trailers`.** It runs only in 2.6.0's cross-worktree
   upgrade bootstrap, for a pre-2.6.0 ("legacy") amendment resolution held
   by two or more worktree `HEAD`s, and an empty trailer set never
   produces a conflict.

No reader was found that needs a completed item's intermediate commits.
One question is not settled by reading, and CP6 proves it: whether any
reader resolves a SHA a completed item's state *records*
(`plan_approval`, `technical_approval`, `reviewed_implementation_head`)
once that SHA is unreachable, as it is in a fresh clone of a squashed
`main` (section 7).

## 4. Invariants (normative for every checkpoint)

- **INV-1 (no Workflow release).** `git diff b856a97 -- distribution
  migration` is empty at every checkpoint; `python3 tools/migrate.py
  --check` and every `build_release.py --overlay ... --check` still pass.
- **INV-2 (full selection unchanged in kind).** With no new flag,
  `run_all.py` still selects the whole inventory. Every one of the base's
  4042 units is still selected, including all 3894 frozen units with
  unchanged pinned counts. The only additions are the new host classes of
  this milestone's own test modules. The runner changes alter neither the
  unit set nor the `selection_digest` of a given inventory, and local gates
  keep running the full selection.
- **INV-3 (managed content untouched).** `workflow-manager verify .`
  prints `installation matches workflow 2.6.0`; `scripts/`,
  `.claude/commands/`, `.github/workflows/workflow-conformance.yml` and
  `CLAUDE.md`'s managed section are byte-identical to the base.
- **INV-4 (fail safe).** Every undecidable input chooses the stricter
  outcome: an unclassifiable path, an unreadable diff, an unreadable or
  non-green `main` history all mean **full matrix**. An unreadable tag
  set, a superseded commit, a non-full or foreign plan all mean **no
  release**.
- **INV-5 (stdlib tests).** New tests use the standard library only and
  run through `python3 tests/run_all.py`. `python -m build` runs in CI jobs
  only, never in a test.
- **INV-6 (versions are derived).** No file in the repository holds the
  Manager's release version. `pyproject.toml` holds only the placeholder
  `0.0.0.dev0`, and a test pins that.

## 5. Design: titles, versions, packages, releases

### 5.1 `D-Title-Grammar`: the Conventional Commit title and its release impact

`tools/release/release.py` (stdlib; the one implementation both the title
check and the release call) parses a title with SignalHub's regex (3.3),
applied to the stripped subject. The allowed types and their impact:

| impact | types |
| --- | --- |
| **major** | any type with `!` (for example `feat!:` or `fix(cli)!:`) |
| **minor** | `feat` |
| **patch** | `fix`, `perf`, `refactor`, `build`, `revert` |
| **none** | `docs`, `chore`, `ci`, `test`, `style` |

`feat`, `fix`, `!`, `docs`, `chore` and `ci` are fixed input 3. The other
five rows are this plan's choice (`OD-2`). The rule is that a type which can
change what the wheel ships or how it is built releases, and a type which
cannot does not. A `BREAKING CHANGE:` footer is not read, as in SignalHub.
The squash commit has no body.

`release.py check-title TITLE`:

- on a valid title, prints `valid title: <type>, release impact
  <major|minor|patch|none>` and exits 0;
- on an invalid one, prints the specific failure and the accepted form,
  then exits 1. The failures are: no `type: description` shape, an unknown
  type, an uppercase type, an empty scope, no space after the colon, or an
  empty description;
- on a usage error, exits 2.

### 5.2 `D-Version-Authority`: tags, next version, first release

- **Tags.** Only strict `vX.Y.Z` tags count (SignalHub's `TAG_RE`). The two
  legacy local tags do not match and are ignored. Tags are created only by
  the release workflow, through `gh release create`.
- **`release.py next-version`.** It takes the highest strict tag in `git
  tag --merged HEAD` and the subjects of `git log --first-parent
  <tag>..HEAD`. The bump is the highest impact among those subjects, so
  several unreleased commits (a catch-up) are released together at `HEAD`.
  If every subject is `none`, or the range is empty, it prints nothing and
  exits 0: nothing to release. A subject that is not a Conventional Commit
  can only reach `main` through a bypass. It counts as a patch and emits a
  `::warning::`, so it is released rather than lost, as in SignalHub.
- **The first release (`OD-1`, recommended: `1.1.0`).** With no strict tag
  reachable, the base is the recorded **baseline** `1.0.0` at commit
  `b856a97` (this milestone's base) and the range is `b856a97..HEAD`. The
  baseline is a named constant in `release.py`, used only while no strict
  tag is reachable. It must be an ancestor of `HEAD`, otherwise the release
  refuses. M1's own pull request is a `feat:`, so the first release is
  **`v1.1.0`**.
  - Why not `1.0.0`: every existing install of this package already
    reports `1.0.0` (the pipx metadata, and `pyproject.toml` at the base),
    and an annotated local tag `workflow-manager-v1.0.0` already names a
    different, older tree. Publishing a different tree as `1.0.0` would give
    one version two meanings. Treating the base as the last hand-versioned
    `1.0.0` and M1 as its first `feat` keeps the sequence honest.
  - The alternative, if the user prefers it, is a one-line change: set the
    first release to exactly `1.0.0` whatever the bump. Both are tested
    shapes.
- **`release.py resolve-target`** (5.4). It chooses the commit a release
  job publishes: the newest commit on `main`'s first-parent history whose
  own `push` verification run completed with `success`. It reads that run
  list through `gh api` (the same endpoint as rule 5, 6.2), keeps only
  `event == push` runs whose `head_sha` is on `git rev-list --first-parent
  origin/main`, and picks the one nearest `main`'s tip. The pick must be
  the triggering run's `head_sha` or a descendant of it. It prints the
  target SHA and that run's id. If the call, the parse or the git read
  fails, it falls back to the triggering run's own `head_sha` and run id
  with a `::warning::`. That run is itself a green push run, so the
  fallback is still safe (INV-4), only less live. The selection is a pure
  function of the run list and the first-parent order, and is unit-tested.
- **`release.py assert-not-superseded`.** It refuses when any strict tag
  points to a commit that is not an ancestor of `HEAD`. Serialized release
  runs can complete out of order (5.4), so an older green commit must never
  be tagged after a newer one. The refusal exits 3, and the release
  workflow treats exit 3 as "already covered by a newer release" (a notice,
  not a failure).
- **`release.py set-version DIR VERSION`.** It rewrites the single
  placeholder line `version = "0.0.0.dev0"` in `DIR/pyproject.toml`, where
  `DIR` is a temporary copy, never the checkout. It refuses zero or more
  than one placeholder, and a version not matching `X.Y.Z` or `X.Y.Z+local`
  (so `v1.2.3` is refused).
- **`pyproject.toml`**: `version = "1.0.0"` becomes `version =
  "0.0.0.dev0"`, with a comment saying the release sets the version at build
  time from the Git tag. A test pins the placeholder (INV-6).

### 5.3 `D-Version-Report` and `D-Artifact`: what the Manager reports and what a release ships

- **`workflow-manager --version`** (argparse `action="version"`, so it needs
  no subcommand). It prints the first of these that applies:
  1. `workflow-manager X.Y.Z`, when the installed distribution's metadata
     version (`importlib.metadata.version("workflow-manager")`) is a release
     version, meaning not `.dev` and not missing.
  2. `workflow-manager X.Y.Z (checkout at vX.Y.Z)`, when `MANAGER_ROOT` is
     the top of a Git work tree (`git -C MANAGER_ROOT rev-parse
     --show-toplevel` resolves to `MANAGER_ROOT` itself) whose `HEAD` is
     exactly a strict tag
     (`git describe --tags --exact-match --match 'v[0-9]*'`) and `git status
     --porcelain --untracked-files=no` is empty. The tag is the version
     authority, so a clean checkout at a release tag *is* that release. This
     is the supported way to run the Manager until M2.
  3. `workflow-manager development build (<git describe --tags --always
     --dirty>)`, when `MANAGER_ROOT` is the top of a Git work tree, by the
     same test. Plain `workflow-manager development build` otherwise.

  The top-level test matters: a wheel without release metadata (for
  example `pip install git+...`, which reports `0.0.0.dev0`) installed into
  a `.venv` inside some *other* repository resolves `MANAGER_ROOT` to
  `.venv/lib/python3.X/`. Git would find the enclosing repository there, and
  branches 2-3 would otherwise report that repository's tag as the
  Manager's version. Every Git call is bounded and fails soft to the next
  line: `--version` is never an error.
- **An existing editable install keeps stale metadata.** The user's pipx
  editable install still reports `workflow-manager 1.0.0` through branch 1
  until it is reinstalled, because its metadata was written from the old
  static version. `README.md` and `docs/RELEASING.md` say to run `pipx
  reinstall workflow-manager` once after M1.
- **A missing `distribution/` says what to do.** When `MANAGER_ROOT` has no
  `distribution/workflow/`, every command's error names the likely cause:
  the Manager is installed from a wheel, not run from a checkout. It also
  names the fix: `--manager-root <workflow-manager checkout at the matching
  tag>`, until M2. This replaces "run tools/migrate.py first".
- **The release artifact (`OD-3`).** A wheel
  (`workflow_manager-X.Y.Z-py3-none-any.whl`), an sdist
  (`workflow_manager-X.Y.Z.tar.gz`) and `SHA256SUMS`. GitHub also attaches
  its own source archives of the tag, which carry `distribution/`.
  - Until M2 the wheel is the Manager's *code*. It installs and reports its
    version, and it operates on releases through `--manager-root`. That flag
    is verified in the release job (5.4) against the checkout at the same
    commit.
  - **Rejected:** bundling `distribution/` (48 MB) into the wheel as package
    data. That is M2's packaged-release design, would change how releases
    are found, and would be thrown away by M2.
  - The release notes say the release contains no Workflow release, and
    which Workflow releases `distribution/` holds at that tag.
- **`tools/release/package.py --version V --out DIR [--manager-root R]`.**
  It copies the project (`pyproject.toml`, `README.md`, `src/`) to a
  temporary directory and calls `release.py set-version`. It then runs
  `python -m build --outdir DIR` and installs the wheel into a fresh venv.
  There it requires:
  - `workflow-manager --version` to print exactly `workflow-manager V`;
  - `workflow-manager --manager-root R releases` to list the releases in
    `R/distribution/`;
  - `workflow-manager --manager-root R verify R` to exit 0, when given.

  Finally it writes `SHA256SUMS` (`sha256sum`-compatible lines, sorted, over
  every file in `DIR`). The frontend is pinned in
  `.github/tools/requirements.txt` (`build==1.6.1`, SignalHub's pin). Its
  pure parts are unit-tested: the copy set, the digest file, and the
  version-output check.

### 5.4 `D-Release-Workflow`: `.github/workflows/release.yml`

```text
on: workflow_run [workflows: "Workflow manager verification", types: completed, branches: main]
permissions: contents: read
job release:
  if: workflow_run.event == 'push' && workflow_run.conclusion == 'success'
  concurrency: { group: workflow-manager-release, cancel-in-progress: false }
  permissions: { contents: write, actions: read }
  steps:
    checkout origin/main, fetch-depth 0
    release.py resolve-target            # TARGET_SHA, TARGET_RUN: newest green push run on main's first parent
    checkout ref = TARGET_SHA
    setup-python 3.12; fetch the frozen upstream   # the plan job's own environment, for the inventory rediscovery
    download artifact "plan" from run TARGET_RUN
    release.py assert-full-plan PLAN     # selection_kind == "full"; selection == the inventory rediscovered here; tree_digest == this checkout's
    release.py next-version              # empty -> notice "nothing to release", stop green
    release.py assert-not-superseded     # exit 3 -> notice "covered by a newer release", stop green
    pip install -r .github/tools/requirements.txt
    package.py --version X.Y.Z --out $RUNNER_TEMP/assets --manager-root $GITHUB_WORKSPACE
    gh release create vX.Y.Z --target TARGET_SHA --title vX.Y.Z --notes-file NOTES --generate-notes assets/*
```

- **Rule 2 by construction.** The release starts only from a *completed,
  successful* verification run of a *push* to `main`. That run's own plan
  must be the full selection, for exactly this tree
  (`assert-full-plan`). So a red `main` publishes nothing.
- **Where the inventory comes from** (manual external review, finding 1).
  The plan artifact records the selection but not the inventory
  (`tests/parallel/planner.py:316-343`). `assert-full-plan` therefore
  **rediscovers** it. It calls `tests.parallel.inventory.discover` on the
  `TARGET_SHA` checkout, in the plan job's own environment (Python 3.12,
  the frozen upstream fetched). It then requires that inventory's
  `tree_digest` to equal the plan's, and the plan's selection to equal
  exactly that inventory's unit set, with no partial class. An inventory
  identity carried in the artifact was rejected. The job that chose the
  selection would also produce it, so it would prove only that the plan
  agrees with itself. Rediscovery at the released tree is independent of
  the plan. The next green
  commit's run releases every unreleased commit up to it (catch-up), which
  is the fix-forward path.
- **Serialized.** The concurrency group is on the *job*, so a skipped run
  (a red or non-push verification) never takes a slot. GitHub keeps at most
  one pending job per group, and the most recently *queued* job replaces
  the pending one. A release job is queued when its verification run
  completes, and `main` runs are concurrent (6.4), so the replacing job can
  belong to an **older** commit. Interleaving (review round 1, finding 1):
  release R0 runs; B's verification finishes and B's job is pending; the
  older A's verification then finishes, and A's job replaces B's. Because
  the job publishes `resolve-target`'s pick rather than its own trigger's
  SHA, A's job finds B's completed green push run and releases up to B. A
  replaced job therefore never strands a commit whose green run had
  completed before the replacing job resolved its target. A run that
  completes later queues its own job. `assert-not-superseded` still covers
  out-of-order completion.
- **Residual, stated and accepted.** Only `resolve-target`'s fallback (an
  API or git failure in the one job that replaced B's) can leave B
  unreleased. The bound is the next release job on `main`: any later green
  `main` push releases B by catch-up. `docs/RELEASING.md` gives the
  recovery for a quiet `main`: re-run the release job of the latest green
  `main` push run from the Actions UI. It resolves its target afresh.
- **Atomic publication.** `gh release create` creates the tag and the
  release in one call, so a failure before it leaves no tag and the next
  run retries. A failed run is re-run from the Actions UI, since
  `workflow_run` re-runs with the same payload.
- `workflow_run` runs the workflow file from the default branch. The
  `event == 'push'` filter excludes pull-request runs, including a fork's
  branch named `main`.

### 5.5 `D-PR-Title-Check`: `.github/workflows/pr-title.yml`

The workflow is `name: PR title`, as in SignalHub, so the check shows as
"PR title / Conventional Commit title" and its required context is the job
name. `pull_request` types `opened, edited, reopened, synchronize`;
`permissions: contents: read`; one job `name: Conventional Commit title`
running
`python3 tools/release/release.py check-title "$TITLE"` with the title
passed through `env`, never interpolated into the script. This check name
is required (6.3).

## 6. Design: the stopgap test profile and CI

### 6.1 `D-Newest-Release-Selection`: the reduced selection in the runner

- New flag `--newest-release-only` for the run, `--list` and `--plan-only`
  modes. It is mutually exclusive with `--select` and `--fast`, and the
  refusal is a usage error, exit 2.
- **The selection.** The *newest release* is the highest version in
  `CI_SUITES` by numeric version order, which is `2.6.0` today. The
  selection holds every host unit except the `FROZEN_MATRIX` host classes
  of the other releases, plus the newest release's three matrix host
  classes, which pull in all of that release's frozen units. So
  `partial_frozen` is `false`, and phase B runs exactly the newest
  release's three matrix classes. When only one release exists it equals
  the full selection.
- **The plan records what it is.** A new plan field, `selection_kind`,
  takes one of three values:
  - `full`: no selection flag;
  - `newest-release`;
  - `targeted`: `--select` or `--fast`.

  `selection_digest` covers the unit set as before, so the full selection's
  digest is unchanged (INV-2).
- **Two derivations of "full", each governing one thing** (review round 1,
  finding 7). `selection_kind` is derived from the *flags*. The evidence
  label keeps the existing *set-equality* rule
  (`tests/parallel/report.py:199-201`: the selection equals the inventory
  and no class is partial), with `newest-release` added for a
  `--newest-release-only` selection that is not full by that rule. The two
  can disagree: `--newest-release-only` with a single release, or a
  `--select` covering everything, is `full` by set equality but not by
  flag. The evidence label follows set equality, as today, because it
  describes the units that ran. `release.py assert-full-plan` requires
  **both** `selection_kind == "full"` (no selection flag) **and** set
  equality with the inventory it rediscovers at the released tree (5.4).
  So the release never rests on a selection that merely happens to cover
  everything today, nor on a plan whose own label claims more than it
  selected.
- **The evidence says what it is.** `evidence_identity`'s `selection` field
  becomes `full`, `newest-release` or `targeted`. The line reads
  `evidence: newest-release selection, ...`, so newest-release evidence can
  never pass for full-suite evidence.
- It is marked as a stopgap (6.7).

### 6.2 `D-PR-Profile`: which selection a pull request runs (rules 1 and 5)

`tools/ci/choose_profile.py` runs in the verification workflow's `plan`
job. It writes `profile=full|newest-release` to `$GITHUB_OUTPUT` and a
reasons table to `$GITHUB_STEP_SUMMARY`. It decides like this:

1. Any event other than `pull_request` (`push`, `schedule`,
   `workflow_dispatch`) means **full**.
2. **Rule 1: the path classification.** The changed paths are `git diff
   --name-only --no-renames -z HEAD^1 HEAD` over the PR's merge ref.
   `HEAD^1` is the base tip and the merge ref is exactly what CI tests.
   `--no-renames` lists both sides of a rename, and deletions are listed
   too. If `HEAD` is not a two-parent merge, or git fails, the profile is
   **full** (INV-4). Each path is classified by
   `tools/ci/pr_profile_paths.json`. Its rules are exact paths or directory
   prefixes ending in `/`, with no globbing; the longest match wins. Each
   rule says `full` or `newest-release` and gives its reason. A path no
   rule matches is **full** ("unclassified"). Any `full` path makes the
   whole pull request **full**.
3. **Rule 5: `main`'s health.** The script reads
   `GET /repos/{repo}/actions/workflows/workflow-manager-verify.yml/runs?branch=main&status=completed&per_page=30`
   through `gh api`, with the job's token and `actions: read`. It keeps
   `event` in `{push, schedule}` and takes the newest run. If that run's
   `conclusion` is not `success` (red, cancelled or timed out), or no run
   exists, or the call or the parse fails, the profile is **full**. After a
   red nightly or a red `main` push, every pull request therefore runs the
   full matrix until a later full `main` run is green. That is a superset
   of "the next PR runs the full matrix" (`OD-8`), and it also covers the
   fix-forward PR rule 2 needs.
4. Otherwise the profile is **newest-release**.

A pull request whose check already passed is not re-run when `main` turns
red later. That is accepted, because nothing merges unverified: `main`'s
own full run covers the merge, and rule 2 holds the release.

**The path rules** (initial content; `full` unless marked):

| rule | profile | reason |
| --- | --- | --- |
| `distribution/` | full | rule 1: the Workflow releases themselves |
| `migration/` | full | produces `distribution/`; portability exceptions set frozen expectations |
| `tools/` | full | release producers, plus this stopgap's and the release's own code |
| `src/` | full | rule 1: the installer (`install.py`, `installation.py`, `release.py`) and the fixture builder (`fixture.py`) every frozen run goes through; `cli.py` is kept with them (fail safe) |
| `tests/support.py`, `tests/frozen_runs.py`, `tests/run_all.py`, `tests/parallel/` | full | rule 1: shared test infrastructure |
| `tests/test_conformance_suite.py`, `tests/test_bootstrap_e2e.py` | full | the 15 matrix host classes live here |
| `.github/` | full | CI and repository-settings definitions: a PR that changes CI proves the full pipeline |
| `pyproject.toml` | full | packaging |
| `docs/`, `README.md`, `CLAUDE.md`, `.gitignore` | newest-release | documentation and housekeeping, which no frozen suite reads |
| `.claude/`, `scripts/`, `.workflow-manager/` | newest-release | this repository's *installed* Workflow copy. Frozen suites run `distribution/` payloads in fresh fixtures, never these; the managed `workflow-conformance.yml` still runs them on every PR |
| each other `tests/test_*.py`, by exact path | newest-release | host test modules, which run in every profile. Every checkpoint that adds a test module also adds its rule here (CP4 classifies CP1-CP3's modules) |

**Proven complete.** A test classifies every path of the tree, meaning
every path `git ls-files` lists plus every untracked, unignored path `git
ls-files --others --exclude-standard` lists (the same notion of the tree
that `tree_digest` uses, `tests/parallel/tree.py`), and requires each one
to match an explicit rule, never the "unclassified" fallback. Including
untracked paths means a new test module fails the local full gate of the
checkpoint that adds it, before its commit, not the next checkpoint's gate
or CI. A new top-level path, or a new test module, therefore fails that
test until its PR classifies it. The PR that does so edits
`tools/ci/pr_profile_paths.json`, which is itself under `tools/`, so it
runs the full matrix (`OD-7`). The fallback is kept for paths that exist
only in a pull request's diff.

### 6.3 `D-Required-Check` (rule 3)

The one required test check is the verification workflow's `aggregate`
job, as today. It keeps its name whatever the shard count (the `shard N`
jobs are never required) and whatever the profile. It now also needs the
new `package` job (6.4). It runs `if: always()` and fails when `plan`,
any shard or `package` did not succeed. So a broken package build fails
the one required check, with no second test check to require. The
required set is `aggregate` plus `Conventional Commit title` (5.5), both
from the GitHub Actions app (`integration_id` 15368).

The managed `workflow-conformance` job is **not** required (`OD-5`). Its
file belongs to `workflow-manager update`, which can rename the job. A
rename would leave a required check that never reports, and every PR would
be locked out. It still runs on every pull request and push. Its seven
suites also run inside the `2.6.0` matrix classes in every profile.

### 6.4 `D-CI`: `.github/workflows/workflow-manager-verify.yml` changes

- **Triggers:** `pull_request`, `push` to `main`, `workflow_dispatch`
  (unchanged), plus `schedule` (`cron: "17 3 * * *"`, the nightly full run
  of the default branch).
- **Concurrency (fixed input 6):**
  ```yaml
  concurrency:
    group: workflow-manager-verify-${{ github.event_name }}-${{ github.event_name == 'pull_request' && github.ref || github.sha }}
    cancel-in-progress: ${{ github.event_name == 'pull_request' }}
  ```
  A pull request keeps its per-ref group, and a new push cancels its stale
  run. Every other run (push, nightly, dispatch) gets its own per-event,
  per-commit group and is never cancelled. The nightly and a push of the
  same SHA never share a group.
- **`plan` job:** gains `permissions: {contents: read, actions: read}`. It
  runs `choose_profile.py` before planning, then `run_all.py --plan-only
  --profile ci ... ${NEWEST:+--newest-release-only}`. It exposes `profile`
  as a job output and writes the choice and its reasons to the job
  summary. The `shard` job is unchanged.
- **New `package` job:** it installs `.github/tools/requirements.txt` and
  runs `tools/release/package.py --version 0.0.0+ci --out $RUNNER_TEMP/dist
  --manager-root $GITHUB_WORKSPACE`. This is the release's build-and-verify
  path on every run, so a packaging break is caught on the PR and not at
  release time. It needs no upstream fetch: `releases` and `verify` read
  only the checkout's own `distribution/` manifests.
- **Job budget.** `package` runs alongside the shards, so a full run holds
  at most 16 shards, `package`, `workflow-conformance` and the title check:
  19 jobs, under the account's 20-job cap. Concurrent pull requests queue,
  as today.
- **`aggregate`:** `needs: [plan, shard, package]`, `if: always()`. A first
  step fails, naming the cause, when `needs.plan.result` or
  `needs.package.result` is not `success`. The shard results are verified
  by the existing aggregate as today.
- **New `nightly-alarm` job (rule 5, "loud"):** `needs: aggregate`,
  `if: always() && github.event_name == 'schedule'`, `permissions: {issues:
  write}`. It runs `tools/ci/nightly_alarm.py`:
  - it first ensures the `nightly-red` label exists (`gh label create
    nightly-red --force`, idempotent; `issues: write` suffices), because
    `gh issue create --label` fails when the label is absent and the first
    red nightly would otherwise open nothing;
  - when `aggregate` did not succeed, it opens an issue titled "Nightly full
    verification failed" with the label `nightly-red`, or comments on the
    open one with the run URL;
  - on success it closes the open `nightly-red` issue with a comment.

  Issue notifications reach everyone watching the repository. The decision
  function (result and open issues in, actions out) is pure and
  unit-tested, and the `gh` calls are a thin shell.
- **README badge:** the workflow badge filtered to `event=schedule` shows
  the nightly result.
- **Workflow permissions** stay `contents: read` at the top; each job
  raises its own.
- GitHub disables scheduled workflows after 60 days without repository
  activity. `docs/RELEASING.md` says so, and says how to re-enable them.

### 6.5 CI structure tests

These extend `tests/test_parallel_runner.py`'s T-CI family, reusing
`load_workflow_yaml`, plus new ones for the new files. The tests of
stopgap-only wiring (T-CI-6 and T-CI-8) live in
`tests/test_stopgap_profile.py`, not in `tests/test_parallel_runner.py`
(manual external review, finding 2). M2 deletes that module whole, so no
test of removed code is left behind (6.7). They import
`load_workflow_yaml` from `tests/test_parallel_runner.py`.

- **T-CI-1 (updated):** triggers are exactly `pull_request`, `push`,
  `workflow_dispatch` and `schedule`; the concurrency group is exactly the
  expression in 6.4; cancellation is limited to pull requests.
- **T-CI-6 (profile wiring, in `tests/test_stopgap_profile.py`):** the `plan` job runs `choose_profile.py`
  before `run_all.py --plan-only`, passes `--newest-release-only` only from
  its output, and holds `actions: read`.
- **T-CI-7 (one required check):** `aggregate` needs `plan`, `shard` and
  `package`, runs `if: always()`, and fails on a non-success `plan` or
  `package`.
- **T-CI-8 (nightly alarm, in `tests/test_stopgap_profile.py`):** a
  `schedule` only, `issues: write` on that job only.
- **T-REL-1 (release workflow):**
  - the steps run `resolve-target` before the target checkout, and the
    plan artifact is downloaded from `TARGET_RUN`, never from
    `workflow_run.id`;
  - Python 3.12 is set up and the frozen upstream is fetched after the
    target checkout and before `assert-full-plan`, as in the verification
    workflow's `plan` job;
  - the trigger is `workflow_run` of `Workflow manager verification`
    (checked against the verification file's own `name:`), `completed`,
    `main`;
  - the job's `if` requires `push` and `success`, and its concurrency group
    is job-level with no cancellation;
  - the steps run in the order 5.4 gives: `assert-full-plan`, then
    `next-version`, then `assert-not-superseded`, before any
    `gh release create`;
  - `contents: write` appears on that job only.
- **T-PRT-1 (title workflow):** the event types are exactly
  `opened, edited, reopened, synchronize`; the job name is `Conventional
  Commit title`; the title passes through `env`.
- **T-SET-1 (settings as data):**
  - `.github/repository/ruleset-main.json`'s required contexts equal
    `{aggregate, Conventional Commit title}`, and each context is the
    `name` (or job id) of a job that exists in a workflow triggered on
    `pull_request`. A typo in a required check name, which would lock out
    every PR, fails here;
  - `strict_required_status_checks_policy` is `false`;
  - `allowed_merge_methods` is `["squash"]`;
  - the `deletion` and `non_fast_forward` rules are present;
  - `bypass_actors` is empty.

  `.github/repository/merge-settings.json` holds squash only, `PR_TITLE`,
  `BLANK`, auto-merge on and delete-branch-on-merge on.

### 6.6 `D-Gate-Policy` (rule 4): the reviewed change to `docs/ARCHITECTURE.md`

The sentence "`--select` narrows a run for development, but a targeted run
is never a gate", and the "Serial and single-shard runs" policy, are
amended. The new text:

> **One reduced selection is a gate, in one place.** The newest-release
> selection (`--newest-release-only`) is the pull-request profile of
> `workflow-manager-verify.yml`. There it is the required `aggregate`
> check, a merge gate for pull requests, and nothing else.
>
> - It applies only when `choose_profile.py` finds no full-matrix path and
>   a green `main`. Otherwise the pull request runs the full selection.
> - `main` pushes and the nightly run always run the full selection.
> - The Manager release requires `main`'s full run for the released
>   commit.
> - Every Workflow gate in this repository (checkpoint verification,
>   implementation review, acceptance) still runs `python3
>   tests/run_all.py`, the full selection.
> - A newest-release run is never cited as full-suite evidence; its
>   evidence line says `newest-release selection`.
> - `--select` and `--fast` remain targeted runs, which are never a gate.
>
> This exception is a stopgap: M2 removes it (6.7).

The decision is reviewed as part of this plan, and CP7 applies it verbatim
(adjusted only for wording review asks for).

### 6.7 `D-Stopgap-Removal` (rule 6): where M2 finds it

- **The marker, defined exactly** (review round 1, finding 2). Stopgap
  code and data carry the marker token `STOPGAP(M2)`, with a pointer to
  `docs/ARCHITECTURE.md`'s "Stopgap test profile", in one of two forms
  only:
  - a **line-leading comment**. In a Python file, it is a `COMMENT` token
    (`tokenize`) that starts with `# STOPGAP(M2)` and is the first token
    on its line. So a line of a multiline string never counts (manual
    external review, optional finding). In a YAML file, it is a line
    matching `^\s*# STOPGAP\(M2\)`;
  - a **JSON `"_comment"` key** whose string value starts with
    `STOPGAP(M2)` (`tools/ci/pr_profile_paths.json`).

  A file is *marked* when it holds at least one of those forms. A mention
  anywhere else (prose, an inline string) is not a marker.
- **The scanned set.** The tree as 6.2 defines it (tracked plus untracked,
  unignored), **minus documentation**: every path under `docs/` and every
  `*.md` path is excluded, explicitly. So this plan document, the
  `ARCHITECTURE.md` subsection that names the marker, `ROADMAP.md`'s
  pointer, `RELEASING.md` and `CLAUDE.md` never count, whatever they say.
- **The marked files** (code and data only, so M2 deletes or edits exactly
  these):
  - `tools/ci/choose_profile.py`;
  - `tools/ci/pr_profile_paths.json` (the `"_comment"` key);
  - `tools/ci/nightly_alarm.py`;
  - the `tests/parallel/` modules holding `--newest-release-only` code,
    each such block opened by the comment form;
  - `.github/workflows/workflow-manager-verify.yml` (the `choose_profile`
    step and the `nightly-alarm` job);
  - `tests/test_stopgap_profile.py`. It holds every test of stopgap code:
    CP3's and CP4's tests, T-CI-6, T-CI-8, and CP5's `assert-full-plan`
    cases that build a `--newest-release-only` plan.

  `tests/test_parallel_runner.py` and `tests/test_release_workflows.py`
  hold no stopgap test, so they are not marked. The permanent
  `assert-full-plan` cases (full, targeted, another tree's, an omitted
  unit) stay in `tests/test_release_workflows.py`.
- `docs/ARCHITECTURE.md` gains a "Stopgap test profile" subsection that
  lists exactly those files and says M2 removes them or their marked
  blocks, restores the single CI profile, and deletes the policy exception
  in 6.6. `docs/ROADMAP.md` 10.2's "The stopgap test profile (10.1) is
  removed" bullet points there.
- **Tested:**
  - the set of marked files in the scanned set equals the list in that
    subsection, so neither can drift from the other;
  - **a reference scan, independent of that list** (manual external
    review, finding 2). Every file in the scanned set that names a
    stopgap identifier must be marked. The identifiers are
    `newest-release-only`, `newest_release`, `choose_profile`,
    `nightly_alarm`, `nightly-alarm` and `pr_profile_paths`. So a test
    or code block of removed stopgap code, placed in an unlisted module,
    fails this test even when the list and the markers agree;
  - the exclusion: a `docs/` file and a `*.md` file that mention the
    token are not marked. Neither is a Python file that mentions it only
    inside a string, including a line of a multiline string that starts
    with `# STOPGAP(M2)`.

## 7. Design: squash-merge compatibility (`D-Squash-Compat`)

Fixed input 2 is not reopened. CP6 proves it is safe for *this* repository's
installed Workflow, and does so in three parts.

1. **Static audit, recorded in `docs/ARCHITECTURE.md`.** Every git history
   or object read in the installed `scripts/workflow_state.py` and
   `scripts/workflow_fingerprint.py` is found (`git log`, `rev-list`,
   `cat-file`, `show`, `merge-base`, `interpret-trailers`, `diff`). Each is
   classified as one of:
   - "branch-local, runs before the merge";
   - "reads state content";
   - "reads a SHA a completed item records";
   - "legacy/cross-worktree only".
2. **A permanent disposable-repository test**
   (`tests/test_squash_merge_compat.py`, history-independent, stdlib). It
   bootstraps `2.6.0` into a disposable repository and drives, through the
   installed Workflow API, an item that records approval and checkpoint
   commits with their trailers on a `milestone/<id>` branch. It then:
   - lands that branch on `main` as one squash commit with a blank body;
   - deletes the branch, expires the reflog, and runs `git gc
     --prune=now`, which is what a fresh clone sees;
   - asserts that on `main` the state validates, a new item routes and
     reaches its plan-stage publication status, the squashed item's id is
     refused for reuse, and `workflow-manager verify` is clean.
3. **A one-off scratch-clone check** of this repository, recorded in
   `docs/ACTIVE_MILESTONE.md`. The completed item's range
   `db4c7af..c1647c3` (PR #1's merge; `db4c7af` is the item's
   `base_commit`, while `c1647c3`'s first parent is `6cd0f97`) is squashed
   onto the item's `base_commit` `db4c7af`, in a scratch clone with every
   other ref deleted and pruned, so every SHA the item's state records
   becomes unreachable. The same assertions then run against the real,
   completed `workflow-manager-adaptive-test-sharding` item.

**Stop rule.** If any part finds a reader that fails once a completed
item's commits are unreachable, CP6 does not work around it. It writes the
finding up under `docs/defects/` as a Workflow defect, which the Workflow
lane repairs, and stops for the user, because fixed input 2 would then need
the user's decision about that defect. Nothing in `scripts/` changes
(INV-3).

## 8. Open decisions (recommendations, for the reviewers and the user)

- **OD-1: first release version.** The recommendation is **`v1.1.0`** (5.2):
  baseline `1.0.0` at `b856a97`, and M1 is a `feat`. The alternative is
  exactly `v1.0.0`.
- **OD-2: impact of the types the brief does not name.** The recommendation
  is `perf`, `refactor`, `build` and `revert` release a patch, and `test`
  and `style` release nothing (5.1). The Controller's C1 should use the same
  table: a cross-repository consistency point, noted in `docs/RELEASING.md`
  for C1.
- **OD-3: the release artifact before M2.** The recommendation is the wheel
  plus sdist of the Manager's code, with `--manager-root` or a checkout at
  the tag. Bundling `distribution/` in the wheel is rejected as M2's job
  (5.3).
- **OD-4: a Controller repository policy.** The recommendation is **not in
  M1.** Under Controller `1.3.0` a policy would do three things:
  - give every draft PR a non-Conventional title, the bare work-item id,
    which the required title check rejects;
  - end every squash merge in `MERGED_REWRITTEN`, a one-time gate with no
    automatic close-out;
  - require a complete `release` section, whose only admissible model is
    `version_change`/`pyproject`, which this milestone removes.

  Each of those is what the Controller's C1 changes, and C1's schema is not
  written yet. Adding the policy is recorded in `docs/ROADMAP.md` as a
  follow-up that becomes ready once a Controller release with C1 ships:
  milestone branches enabled, release section disabled, validated with that
  release's `workflow-controller inspect`. The policy must reach `main`
  before the milestone that first uses it starts, since adoption reads it
  at the branch point.
- **OD-5: required checks.** The recommendation is `aggregate` and
  `Conventional Commit title` only. The managed `workflow-conformance` job
  is not required (6.3).
- **OD-6: when the ruleset is switched on.** The recommendation is after
  M1's pull request has reported both checks under their exact names, and
  before it merges (section 9). M1 is then the first PR merged under
  protection, with no lockout.
- **OD-7: completeness friction.** A new top-level path or test module
  needs an explicit classification in its own PR (6.2). The recommendation
  is to accept this.
- **OD-8: rule 5's scope.** The recommendation is every PR runs full while
  `main`'s latest full run is not green, which is stricter than "the next
  PR" (6.2).

`docs/TECHNICAL_DECISIONS.md` does not exist at the base, so no "Open
decision" row is touched or silently finalized. The eight decisions above
are this plan's own and are listed for review.

## 9. Cutover: getting M1 itself onto a protected `main`

No step below is performed by a Workflow command or by an agent. Every
step marked **[user]** is a push, a pull request, a settings or ruleset
change, or a merge, and the managed `CLAUDE.md` rule ("Never push, merge,
rebase, force-push, or open a pull request") reserves each of them to the
user (section 2). The agent's part is to state the exact commands and to
read the results back read-only (`gh pr checks`, `gh run view`, `gh api`
GETs). The exact payloads are the reviewed files
`.github/repository/merge-settings.json` and
`.github/repository/ruleset-main.json`, and `docs/RELEASING.md` gives the
`git push`, `gh pr create` and `gh api` commands.

1. **C0: implementation, on this branch [user].** After CP7, the user
   pushes the branch and opens a **draft** PR titled
   `feat: trunk model, Manager releases and the stopgap PR test profile`.
   The PR runs the new workflows from its own merge ref:
   - the title check;
   - the verification profile, which is **full** because M1 touches
     `.github/`, `tools/`, `src/` and `tests/parallel/`;
   - the `package` job.

   These runs are the milestone's CI evidence. The functional-review
   checklist records their run URLs in `docs/ACTIVE_MILESTONE.md`; no
   checkpoint exit waits for them. No setting has changed yet, so nothing
   can lock the PR out.
2. **C1: functional-review probes [user], on throwaway draft PRs, closed
   unmerged.** The user pushes each probe branch and opens and closes each
   probe PR. Each probe targets the milestone branch, so it runs the
   milestone's workflows:
   - a docs-only probe must choose **newest-release**;
   - a probe touching `src/` must choose **full**;
   - a probe titled `Update things` must fail the title check;
   - a probe titled `docs: ...` must pass it with impact `none`.
3. **C2: after `/accept-milestone`, merge settings [user]:**
   - squash only;
   - squash title `PR_TITLE`, message `BLANK`;
   - auto-merge allowed;
   - delete the branch on merge.

   These are harmless to open PRs and make M1's own merge a squash.
4. **C3: the ruleset [user].** First the user pushes the acceptance
   commits `/accept-milestone` made, so the PR's head is the milestone's
   final head. Then read M1's PR checks **at that final head** (`gh pr
   checks <n> --json name,state`, read-only), never an earlier head's, and
   confirm both `aggregate` and `Conventional Commit title` reported,
   green, under exactly those names.
   Then create the ruleset from `ruleset-main.json`:
   - on `~DEFAULT_BRANCH`;
   - `deletion` and `non_fast_forward`;
   - `required_linear_history`;
   - `pull_request` with 0 approvals and squash only;
   - required checks with `strict: false`;
   - no bypass actors.

   The names were observed before they became required, so M1 cannot be
   locked out. If it somehow were, an administrator can still edit or
   disable the ruleset; that is the recovery, not a bypass actor.
5. **C4: merge M1 [user].** Mark the PR ready and merge it by
   squash, directly or through auto-merge. The squash subject is the PR
   title.
6. **C5: first release, post-merge verification, outside the Workflow's
   gates.**
   - `main`'s push run of the squash commit is **full**, and must be green.
   - The release workflow then publishes **`v1.1.0`** (`OD-1`) with the
     wheel, sdist and `SHA256SUMS`.
   - Check that `sha256sum -c SHA256SUMS` passes on the downloaded assets.
   - Check that a wheel installed into a fresh venv prints `workflow-manager
     1.1.0`.
   - Check that `git fetch --tags` shows `v1.1.0` on the squash commit.
   - If `main` is red, nothing is published: a `fix:` PR fixes forward and
     its merge publishes the release.
7. **C6: from the next milestone on.** One branch per milestone, PRs merged
   by squash with a Conventional-Commit title. The Controller policy waits
   for C1 (`OD-4`).

The first release is observable only after the Workflow's own acceptance,
because acceptance precedes the merge. The functional review therefore
covers C0-C1, once the user has done them. It also covers a scratch-clone simulation of C4-C5's version
step: M1's squash commit, with its PR title as the subject, is created on
`b856a97`, and `release.py next-version` must print `v1.1.0` there. C5 is
recorded in `docs/ACTIVE_MILESTONE.md` when it happens.

## 10. Checkpoint registry

Every checkpoint ends with:

- its own targeted tests: `python3 tests/run_all.py --select <modules>`;
- the INV-1 and INV-3 checks: `git diff b856a97 -- distribution migration
  scripts .claude/commands .github/workflows/workflow-conformance.yml` is
  empty, and `workflow-manager verify .` is clean;
- the full gate: `python3 tests/run_all.py`, which must be green.

<!-- registry-table:begin -->
| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Conventional Commit titles and tag-derived versions: tools/release/release.py (check-title, next-version, assert-not-superseded, set-version) and the pyproject placeholder | - | 3 | 1 |
| CP2 | Manager version reporting and release packaging: --version, the missing-distribution hint, tools/release/package.py and SHA256SUMS | CP1 | 3 | 1 |
| CP3 | Newest-release selection in the runner: --newest-release-only, selection_kind and the evidence label | - | 3 | 1 |
| CP4 | Pull-request profile chooser: path rules with a completeness proof, main-health escalation, and the nightly alarm decision | CP3 | 3 | 1 |
| CP5 | CI, title and release workflows, per-commit main concurrency, nightly run, and repository settings as reviewed data | CP2, CP4 | 4 | 1 |
| CP6 | Squash-merge compatibility: static audit, disposable-repository test and scratch-clone check | CP4 | 3 | 1 |
| CP7 | Documentation, the reviewed gate-policy change, the stopgap's M2 removal record and the cutover runbook | CP1, CP2, CP3, CP4, CP5, CP6 | 3 | 1 |
<!-- registry-table:end -->

### CP1: titles and versions

- **Files:** `tools/release/__init__.py`, `tools/release/release.py` (new);
  `pyproject.toml` (the placeholder).
- **Tests:** `tests/test_release_versioning.py` (new), using real temporary
  git repositories under `$TMPDIR`:
  - the title table: every type in 5.1, scopes, `!` on each impact row,
    the ` (#N)` suffix GitHub appends to a squash subject, and the
    rejections from 5.1;
  - tag parsing (strict form only, and the legacy tags ignored);
  - `next-version`:
    - the baseline gives `1.1.0` for a `feat`;
    - `none`-only ranges give empty output;
    - a catch-up takes the maximum bump;
    - the highest reachable tag wins (`v1.10.0` over `v1.9.0`);
    - a non-Conventional subject is a patch with a warning;
    - the baseline must be an ancestor of `HEAD`;
  - `assert-not-superseded`: exit 3 when a strict tag sits on a
    non-ancestor;
  - `resolve-target`, from injected run lists and a temporary repository's
    first-parent history: the newest green push run on `main` wins; the
    interleaving in 5.4 (older A's job replacing newer B's pending job)
    targets B; `pull_request`, red and off-`main` runs are ignored; a pick
    that is not the trigger or its descendant is refused; an API, parse or
    git failure falls back to the trigger with a warning;
  - `set-version`: refuses zero or two placeholders and a `v`-prefixed
    version, and never touches the checkout;
  - the `pyproject.toml` placeholder pin (INV-6);
  - exit codes 0/1/2/3.

### CP2: version report and packaging

- **Files:** `src/workflow_manager/cli.py` (`--version`, the
  missing-distribution hint); `tools/release/package.py` (new);
  `.github/tools/requirements.txt` (new); `README.md` (the `pipx
  reinstall` note, finding 6).
- **Tests:** `tests/test_manager_version.py` (new):
  - each branch of 5.3's order, with metadata faked through an injected
    lookup and temporary git repositories for the checkout branches;
  - Git failures fall through;
  - `MANAGER_ROOT` inside an unrelated enclosing Git work tree (a `.venv`
    in another repository carrying a strict tag) is not the top level, so
    branches 2-3 do not apply and the output is plain `development build`;
  - `--version` needs no subcommand;
  - the hint text when `distribution/workflow/` is absent.

  Plus `package.py`'s pure parts: the copy set, `SHA256SUMS` format and
  sorting, and the exact `--version` comparison. The real build is
  exercised by CP5's `package` job in CI (INV-5).

### CP3: newest-release selection

- **Files:** `tests/parallel/cli.py`, `tests/parallel/inventory.py`,
  `tests/parallel/planner.py`, `tests/parallel/report.py`.
- **Tests:** `tests/test_stopgap_profile.py` (new):
  - the newest release is computed by version order (a `2.10.0` fixture
    beats `2.9.0`);
  - the selection equals every host unit minus the other releases' matrix
    classes, plus the newest release's frozen units;
  - `partial_frozen` is false, and phase B holds the three newest matrix
    classes;
  - over the live inventory, the selection is exactly that structural set.
    The count is not pinned, because new host tests move it; at the base it
    was 1069 units (3.5);
  - the flag is exclusive with `--select`/`--fast` (exit 2);
  - `selection_kind` and the evidence label for all three kinds;
  - the full selection still holds every base unit, and for a fixed
    inventory its unit set and `selection_digest` are the same with or
    without this milestone's runner changes (INV-2);
  - a real `--newest-release-only --list` subprocess run.

### CP4: the profile chooser

- **Files:** `tools/ci/__init__.py`, `tools/ci/choose_profile.py`,
  `tools/ci/pr_profile_paths.json`, `tools/ci/nightly_alarm.py` (new).
- **Tests** (in `tests/test_stopgap_profile.py`):
  - completeness: every tracked path and every untracked, unignored path
    matches an explicit rule, and a new untracked test module with no rule
    fails it; CP1-CP3's test modules are classified here;
  - unknown paths are `full`;
  - every rule-1 area is `full`;
  - docs-only is `newest-release`;
  - longest match wins;
  - both sides of a rename are classified, and so are deletions;
  - a non-merge `HEAD` or a git failure is `full`;
  - main health, from injected API JSON: green gives newest-release; red,
    cancelled, empty, malformed or an API error gives `full`; `push` and
    `schedule` both count; `pull_request` and `workflow_dispatch` runs are
    ignored;
  - non-PR events are `full`;
  - the `$GITHUB_OUTPUT` and summary format;
  - `nightly_alarm`'s decision table: red with no open issue opens one; red
    with an open issue comments; green with an open issue closes it; green
    with none does nothing; a non-schedule event does nothing; every red
    case ensures the label first, so "label absent" still opens the issue.

### CP5: workflows and settings data

- **Files:** `.github/workflows/workflow-manager-verify.yml` (changed);
  `.github/workflows/pr-title.yml`, `.github/workflows/release.yml`,
  `.github/repository/ruleset-main.json`,
  `.github/repository/merge-settings.json` (new);
  `tools/release/release.py` (`assert-full-plan`);
  `tests/test_release_workflows.py` (new, T-REL-1, T-PRT-1, T-SET-1 and
  the permanent `assert-full-plan` cases) and its rule in
  `tools/ci/pr_profile_paths.json`; `tests/test_stopgap_profile.py`
  (T-CI-6, T-CI-8 and the stopgap `assert-full-plan` cases).
- **Tests:**
  - in `tests/test_parallel_runner.py`: T-CI-1 (updated) and T-CI-7;
  - in `tests/test_stopgap_profile.py`: T-CI-6 and T-CI-8 (6.5, 6.7);
  - T-REL-1, T-PRT-1 and T-SET-1 (6.5);
  - `assert-full-plan` against real `--plan-only` output, with the
    inventory rediscovered from the checkout (5.4). In
    `tests/test_release_workflows.py`:
    - a full plan for this tree passes;
    - a targeted plan and another tree's plan are refused;
    - a `--select` covering the whole inventory is refused (full by set
      equality, not by flag, 6.1);
    - a plan marked `selection_kind: full` whose selection omits one
      inventory unit is refused, and so is one with a partial class
      (manual external review, finding 1).

    In `tests/test_stopgap_profile.py` (6.7): a newest-release plan is
    refused, and so is a `--newest-release-only` plan over a one-release
    inventory, which is full by set equality but not by flag.

  T-CI-2..5 keep passing unchanged.

### CP6: squash-merge compatibility

- **Files:** `tests/test_squash_merge_compat.py` (new) and its rule in
  `tools/ci/pr_profile_paths.json` (so CP6 depends on CP4).
- **Evidence:**
  - the audit table and the scratch-clone evidence are recorded in the
    checkpoint log;
  - `docs/ARCHITECTURE.md` gets the audit's conclusion in CP7;
  - the section 7 stop rule applies.

### CP7: documentation, policy, removal record, cutover, CI evidence

- **Files:**
  - `CLAUDE.md`, below the managed marker only: a new "Branches, pull
    requests and releases" section, plus the "Before changing anything"
    lines that the gate policy touches;
  - `docs/ARCHITECTURE.md`:
    - "Verification execution": the CI paragraph, profiles, concurrency,
      nightly and release, and the 6.6 policy text;
    - the "Stopgap test profile" subsection, with the marked-file list;
    - the squash-compatibility conclusion;
  - `README.md`: how to install (a checkout at a tag, or the wheel with
    `--manager-root`), `--version`, badges and releases;
  - `docs/RELEASING.md` (new):
    - how a release happens (automatic) and the impact table;
    - the first release;
    - catch-up, fix-forward, re-running a failed release, and recovering a
      stranded release (5.4's residual);
    - `pipx reinstall workflow-manager` once after M1 (5.3);
    - verifying `SHA256SUMS`;
    - the settings and ruleset `gh api` commands;
    - the 60-day schedule caveat;
    - the C1 alignment note;
  - `docs/ROADMAP.md`: M1's status, 10.2's pointer, and the `OD-4`
    follow-up.
- **Tests:** the marker-set test (6.7), in `tests/test_stopgap_profile.py`:
  - the list equality;
  - the reference scan;
  - the documentation exclusion;
  - the string-mention cases, including the multiline-string line.
- **No CI evidence in this checkpoint.** CP7 completes on its local gates.
  The draft PR's CI runs (C0) need the user's push, so the
  functional-review checklist asks for them: `aggregate` and `Conventional
  Commit title` green, the full profile chosen, the `package` job green,
  with the run URLs recorded in `docs/ACTIVE_MILESTONE.md` (section 9).

## 11. Requirements traceability

| requirement | checkpoints |
| --- | --- |
| REQ-1 trunk model: protected `main` via a ruleset, PRs only, required checks, no force push or deletion, no up-to-date requirement, one branch per milestone | CP5, CP7 |
| REQ-2 squash-only merges with auto-merge; the PR title is the squash subject; squash merging is safe for the installed Workflow | CP5, CP6, CP7 |
| REQ-3 a required Conventional Commit PR-title check with the release-impact table | CP1, CP5 |
| REQ-4 the Git tag is the only version authority: derived next version, first release, build-time version, placeholder-only `pyproject.toml`, version reporting | CP1, CP2 |
| REQ-5 a serialized Manager package release from `main`: wheel, sdist and `SHA256SUMS` on a GitHub release; no Workflow release | CP2, CP5 |
| REQ-6 a per-commit CI concurrency group for `main` | CP5 |
| REQ-7 the stopgap profile: PR runs host plus newest release; `main` and nightly run the full matrix | CP3, CP4, CP5 |
| REQ-8 rule 1: fail-safe, proven-complete path classification escalates to the full matrix | CP4 |
| REQ-9 rule 2: the release waits for `main`'s full run; red `main` publishes nothing | CP1, CP5 |
| REQ-10 rule 3: one aggregate required check, stable across shard counts and profiles | CP5 |
| REQ-11 rule 4: the reviewed gate-policy change in `docs/ARCHITECTURE.md` | CP7 |
| REQ-12 rule 5: a loud nightly failure, and PRs escalate to full while `main` is not green | CP4, CP5 |
| REQ-13 rule 6: the stopgap's removal by M2 recorded where M2 finds it, and tested | CP7 |
| REQ-14 no Workflow release, `distribution/` byte-identical, managed content untouched, `workflow-manager verify .` clean | CP7 |
| REQ-15 the Controller-policy decision and the cutover plan, recorded | CP7 |

## 12. This milestone's own review logistics

- Governing version `2.2`: two-stage plan review (local, then manual
  external) and two-stage implementation review. The installed Workflow is
  `2.6.0`, and the item carries `feedback_layout: "scoped"`, so feedback
  lands in `.ai-review/workflow-manager-trunk-model/feedback/`.
- **The artifacts declaration** is generated from the `process` template
  and then fitted in `SELF_REVIEWING_PLAN` to this item's footprint.
  - **Implementation deliverables, protected at the implementation
    stage:**
    - `tools/` (prefix: the new `release/` and `ci/` packages, while
      `migrate.py` and `build_release.py` must stay unchanged);
    - `src/`, `tests/`, `pyproject.toml`;
    - the exact paths of the verification, title and release workflows,
      `.github/repository/` and `.github/tools/requirements.txt`;
    - `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`,
      `docs/RELEASING.md`.
  - **Must not change, protected so that any change is reviewed:**
    `distribution/`, `migration/`, `scripts/`, `.claude/commands/`,
    `.github/workflows/workflow-conformance.yml`.
  - `docs/ROADMAP.md` stays excluded as Workflow bookkeeping
    (`/accept-milestone` writes it), so the M2 removal list lives in the
    protected `docs/ARCHITECTURE.md` (6.7).
- The CI evidence, the section 9 probes, every push, pull request, settings
  change and merge are the user's actions (section 2 and section 9). They
  belong to the functional review and the cutover, never to a checkpoint's
  exit.

## 13. `SELF_REVIEWING_PLAN`

- **Coverage.** No test is removed or weakened. The full selection is
  byte-for-byte the same set (INV-2). A pull request runs 1069 of 4042
  units only when neither rule 1 nor rule 5 escalates it, and every commit
  on `main` still runs all 4042 before it can be released. The residual
  risk is a pull request whose change breaks an *older* release while
  touching only newest-release paths. That is possible only through a path
  no frozen run reads, and `main`'s full run catches it before any release
  (rule 2). This risk is what the stopgap accepts, and M2 ends it.
- **Rule 1's list is fail-safe, not clever.** Everything under `src/` is
  full, including `cli.py`, which no fixture imports. The cost is a full
  run on CLI-only PRs, and that is the safe side.
- **Release races** are handled by job-level serialization,
  `resolve-target` (a replacing job publishes the newest green `main`
  commit, not its own trigger), `assert-not-superseded` and catch-up. Each
  has a test or a structural check. The one residual (5.4) is stated and
  bounded.
- **Lockout** is prevented by the settings-as-data test (T-SET-1) and by
  observing the check names before requiring them (C3).
- **Unnecessary complexity, removed during self-review:**
  - a `workflow_dispatch` release trigger (a re-run covers it);
  - a separate `package` required check (folded into `aggregate`);
  - glob patterns in the path rules (exact paths and prefixes only);
  - a version file in the repository (INV-6).
- **Migration risk:** none to Workflow state. `pyproject.toml`'s placeholder
  changes an editable install's reported metadata version from `1.0.0` to
  `0.0.0.dev0` on its next reinstall. `--version` then reports a
  development build, or the tag for a clean tagged checkout, which is
  correct.
- **Usability:** the title check prints the impact; the plan job's summary
  says which profile ran and why; the release notes say what is in the
  release; `docs/RELEASING.md` is the one place for the release procedure.

## 14. Review dispositions

### Round 1 (`LOCAL_MODEL_PLAN_REVIEW`, bundle `4200dfd8`, `REVISE`)

Every finding was checked against the repository before it was applied.
All eight are accepted; none is rejected.

| finding | disposition | where |
| --- | --- | --- |
| 1 release stranded by an older job replacing a newer pending one | **Accepted, closed by design.** Confirmed: 6.4 makes `main` runs concurrent, and GitHub replaces the pending job with the most recently queued one. The release job now publishes `release.py resolve-target`'s pick (the newest green push run on `main`'s first parent), not its trigger's SHA, and downloads that run's plan. The "Serialized" bullet is corrected; the API-failure fallback is the one residual, stated and bounded, with the recovery in `docs/RELEASING.md` | 5.2, 5.4, 6.5 T-REL-1, CP1, CP7 |
| 2 marker-set test cannot pass | **Accepted.** Confirmed: this plan and the `ARCHITECTURE.md` subsection both contain the token. The marker is now two exact forms (a line-leading `# STOPGAP(M2)` comment, a `"_comment"` value), the scan excludes `docs/` and `*.md` explicitly, the list names code and data files only, and the exclusion is tested | 6.1, 6.7, CP7 |
| 3 section 9/2/12 vs the managed `CLAUDE.md` git restrictions | **Accepted.** Confirmed: `CLAUDE.md` line 30 at the base. Every push, PR, probe, settings change and merge is now a user action with the commands given; CP7's CI evidence moves to the functional review, so no checkpoint exit depends on it. CP7's registry name drops "and CI evidence" | 2, 9, 12, CP7 |
| 4 test modules vs rule 1's completeness test | **Accepted.** Confirmed: `tree_digest` covers untracked, unignored paths (`tests/parallel/tree.py:3-4`), `git ls-files` alone does not. The completeness test uses both; CP5 and CP6 name `pr_profile_paths.json` in their file lists; CP4 classifies CP1-CP3's modules; CP6 now depends on CP4 | 6.2, CP4, CP5, CP6 |
| 5 `nightly-red` label may not exist | **Accepted.** The alarm ensures the label idempotently first, and the decision table tests "label absent" | 6.4, CP4 |
| 6 `--version` in an unrelated enclosing work tree; stale pipx metadata | **Accepted.** Branches 2-3 require `rev-parse --show-toplevel` to be `MANAGER_ROOT`, with a test; `README.md` and `docs/RELEASING.md` say to run `pipx reinstall workflow-manager` after M1 | 5.3, CP2, CP7 |
| 7 which derivation of "full" governs | **Accepted.** Confirmed at `tests/parallel/report.py:199-201`. The evidence label keeps set equality; `assert-full-plan` requires both the flag-derived `selection_kind == "full"` and set equality; the disagreeing edge cases are tested | 6.1, CP5 |
| 8 PR #1's squash base | **Accepted, wording only.** Confirmed: `c1647c3`'s first parent is `6cd0f97`, and `git rev-list --count --first-parent db4c7af..6cd0f97` is 11. The simulation squashes `db4c7af..c1647c3` onto the item's `base_commit` `db4c7af` | 7 |
| Architecture note: C3 reads the checks at the final head | **Accepted.** C3 now starts by pushing the acceptance commits and reads the checks at that head | 9 C3 |
| Usability note: recovering a stranded release | **Accepted.** `docs/RELEASING.md` covers it | 5.4, CP7 |

### Manual external round 1 (`MANUAL_EXTERNAL_PLAN_REVIEW`, bundle `522346fc`, `REVISE`)

Every finding was checked against the repository before it was applied.
All three are accepted; none is rejected. No blocking findings were
raised.

| finding | disposition | where |
| --- | --- | --- |
| Important 1: the release gate's inventory source is unspecified | **Accepted.** Confirmed: the plan document `build_plan` writes (`tests/parallel/planner.py:316-343`) holds `selection` and `selection_digest`, but no inventory unit set. `assert-full-plan` now rediscovers the inventory at `TARGET_SHA` with `tests.parallel.inventory.discover`, in the plan job's environment, and requires matching `tree_digest` and exact set equality. An inventory identity in the artifact was rejected: it would prove only that the plan agrees with itself. New tests: a `full`-labelled plan omitting a unit, and one with a partial class, are refused | 5.4, 6.1, 6.5 T-REL-1, CP5 |
| Important 2: the M2 removal record misses T-CI-6's module | **Accepted.** Confirmed: CP5 put T-CI-6 (and T-CI-8, the nightly-alarm wiring, also stopgap) in the unlisted `tests/test_parallel_runner.py`. Both now live in the listed `tests/test_stopgap_profile.py`. So do the `assert-full-plan` cases that build a `--newest-release-only` plan. The marker-set test adds a reference scan that is independent of the list: every scanned file naming a stopgap identifier must be marked | 6.5, 6.7, CP5, CP7 |
| Optional: the line-leading pattern matches inside a multiline Python string | **Accepted.** Confirmed: `^\s*# STOPGAP\(M2\)` matches such a line. In Python files the marker is now a `tokenize` `COMMENT` token that is first on its line; YAML keeps the line pattern. The multiline-string case is tested | 6.7, CP7 |
