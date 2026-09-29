# Architecture

Workflow Manager distributes a frozen Workflow release into other
repositories. Two things must never blur together, and the whole design is
arranged around keeping them apart:

- **Canonical distribution content** — immutable, versioned, byte-identical to
  a frozen upstream release. Lives in `distribution/`. Nothing writes to it
  except `tools/migrate.py`.
- **Target-repository state** — mutable, repository-local, owned by whoever
  runs the Workflow. Work items, approvals, bundles, checkpoints. Workflow
  Manager creates it once and afterwards never overwrites it.

An update replaces the first and preserves the second. That single sentence is
the reason for most of the structure below.

## Repository layout

```
migration/
  classification.json          ordered, first-match-wins ruleset over the frozen tree
  portability_exceptions.json  frozen tests a clean target cannot pass, with reasons
  overlays/<version>/           hand-authored delta for an authored release (see below)
    classification.json         same ruleset shape, scoped to the overlay's own files
    payload/                     new files, plus full replacements of base payload files
tools/
  migrate.py                   frozen upstream -> distribution/  (Phase A)
  build_release.py             base release + overlay -> distribution/  (an authored release)
  release/                     the Manager's own releases: titles, versions, packaging
  ci/                          the stopgap pull-request profile and nightly alarm (M2 removes it)
distribution/
  workflow/<version>/
    manifest.json              every upstream path's disposition, with digests
                               (an authored release's manifest also carries `provenance`
                               and, per replaced file, `overlay_delta` -- see below)
    payload/                   Workflow files, byte-identical, target-relative paths
    fixtures/                  host documents the frozen suite asserts on
    templates/                 clean repository-local initial state, and the
                               release-owned files migration renders rather
                               than copies
src/workflow_manager/
  release.py                   read and verify a release from its own manifest
  fixture.py                   build disposable repositories from a release
  install.py                   bootstrap, update, drift  (Phase B)
  installation.py              the installed-version record in a target
  cli.py                       command-line entry point
tests/                         stdlib unittest, no third-party dependencies
docs/
  MIGRATION.md                 the Phase-A record and its evidence, plus each
                               authored release's own provenance record
  ARCHITECTURE.md              this file
  defects/                     upstream defects found, documented, not repaired
  RELEASING.md                 how the Manager is released
.github/
  workflows/                   verification, PR title, release, and the managed conformance check
  repository/                  merge settings and the `main` ruleset, as reviewed data
```

## Why payload paths are target-relative

`distribution/workflow/2.3.1/payload/scripts/workflow_state.py` installs to
`<target>/scripts/workflow_state.py`. No rewriting, no path mapping.

That is not laziness. Frozen v2.3.1 has two hard layout dependencies:

- `docs/ai-workflow/dry-run/verify_372h_lock_primitive_predicate.py` resolves
  the repository root as `Path(__file__).resolve().parents[3]`.
- `workflow_state.py` imports `workflow_fingerprint` by bare name.

An installer that rewrote paths would be a place for both to break silently.
A copy cannot.

## Install profiles

| Profile | Categories | Use |
|---|---|---|
| `runtime` | `distribution` | The Workflow operates. 34 files. |
| `full` | `distribution` + `conformance` | The Workflow operates *and* its own conformance suite runs. 59 files — 58 payload files plus the conformance CI workflow. |

`full` is the default. A repository that installs `runtime` only gets the
tests without the documents several of them lint, so its suite would be red
for reasons that are not regressions — which is why the CI workflow that runs
them is a `conformance` file too, and is not installed under `runtime`.

`host-evidence` is in neither profile. Those two files are the upstream
repository's own documents, kept solely so the frozen suite can be run
unchanged as migration evidence.

## What the installer owns and what it does not

The question that decides every row below is **who writes to this file after
it is installed**. If the answer is the Workflow or the operator, the release
must never overwrite it. If the answer is nobody, it belongs to the release.

Release-owned — replaced wholesale on update, drift-checked against the
manifest, refused rather than overwritten when edited locally:

- `scripts/` (the payload's files only)
- `.claude/commands/`
- `docs/ai-workflow/` (the payload's files only)
- `.github/workflows/workflow-conformance.yml` — rendered from a template
  rather than copied byte-for-byte, but owned by the release all the same:
  nothing writes to it at run time and it exists to run *that release's*
  suites, so freezing it at install time would leave a repository running an
  older release's conformance gate forever. `full` profile only; under
  `runtime` the documents several of those suites lint are absent, so shipping
  the CI that runs them would hand a repository a red pipeline it cannot fix.

Created once, then never touched:

- `docs/ai-workflow/WORKFLOW_STATE.json`
- `docs/ai-workflow/WORKFLOW_CONFIG.json`
- `docs/ACTIVE_MILESTONE.md`
- `.ai-review/` (created by the Workflow itself at run time)

Merged, never replaced:

- `.gitignore` — the Workflow fragment is appended if absent
- `CLAUDE.md` — a managed section up to `<!-- workflow-manager:end -->`;
  anything below it is the repository's own

Neither merged file is owned, so neither is compared whole — but the
installer's *contribution* to each is checked, because losing it is silent and
expensive. A `.gitignore` that no longer ignores `.ai-review/` means the
repository has started tracking the Workflow's live runtime workspace.
`verify` reports both; the next `update` repairs both, leaving everything the
repository wrote where it was.

Nothing else in a target is touched. A repository that already keeps its own
file at a release path — `.claude/commands/` and `scripts/` are ordinary
names — stops the bootstrap with the list of collisions rather than losing
them; `--force` overwrites.

## The installation record

`.workflow-manager/installation.json` in the target records which release is
installed and the digest of every file installed from it. It is what makes
three things possible without guessing:

- **recognition** — an already-managed repository is one that has this file;
- **drift** — compare each recorded file's current digest against the manifest;
- **safe update** — a file that drifted is a local modification, and an update
  reports it rather than silently discarding it.

It is replaced by `os.replace`, never written in place. A record is the one
thing a target cannot reconstruct, and a reader must see either the previous
one or the complete new one — never half of either.

## Interruption

Neither `bootstrap` nor `update` is atomic. A repository is not a database,
and a rollback path that has itself never been interrupted is a worse promise
than none. What both operations are instead is **re-runnable**: every write
is idempotent, and the contract is that running the same command again
finishes the job.

| Interrupted | What is left | What repairs it |
|---|---|---|
| `bootstrap` | Some release files present, no installation record. `status` says *not a managed repository* — the half-install is never mistaken for a real one. | Run `bootstrap` again. The files already written hold the release's own bytes, so they are not collisions and not rewritten; state templates already written are recognised as this installer's, not as the repository's own. |
| `update` | A mix of the two releases on disk, the record still naming the old one. | Run `update` again. A file already holding the *incoming* release's bytes is not counted as a local edit, so the update resumes without `--force` — which would have discarded real edits along with the half-applied ones. |
| the record write | Nothing: the rename is atomic. | — |
| a hand-damaged record | `.workflow-manager/installation.json` unreadable. Every command refuses with the reason and the remedy. | Delete `.workflow-manager/` and run `bootstrap`. Repository-local state does not live there and is untouched. |

A genuine local edit still blocks a resumed update. Resumability is not a way
to lose an edit: the exemption is narrowly "this file already *is* what we are
about to write", nothing wider. It follows that *rolling back* after an
interrupted update is not resumption — the half-applied files match neither the
record nor the release being returned to, which is indistinguishable from a
local edit — so it refuses until `--force`. Finishing forward is the cheap
path; going back is the one that asks first.

## Release integrity

Installing is the moment a release asserts its identity to a repository, so
nothing is copied out of `distribution/` without being checked against the
manifest digest first. A `distribution/` that was damaged, partially checked
out, or edited fails the install rather than handing a target non-canonical
bytes under a canonical version label — which would also leave the record
describing files that are not there.

## Which release a command means

`distribution/` may hold several releases at once, and the two kinds of
command mean different things by "the release":

| Command | Default | Why |
|---|---|---|
| `bootstrap`, `update` | the newest release present | These *choose* which release a repository is on; "the current one" is the only sensible default, and `--release-version` pins. |
| `status`, `verify` | the release the target's own record names | These *report on* an installation. Grading a repository against a release it was never installed from would make every target look broken the moment a newer one landed. |

`status` never reports an installation it did not check. If no release is
available to compare against it says so; it cannot say "clean" without having
looked.

## Boundaries this design keeps

- Nothing in `distribution/` reads outside `distribution/`.
- Nothing in a release names the upstream checkout, except the manifest's
  provenance record and two lines of frozen design prose, both pinned by test.
- The bootstrapper is verified against disposable repositories only. It has no
  notion of a "real" consumer, and nothing here touches one.
- Controller orchestration is deliberately absent. The installation record and
  the drift report are the surfaces a controller would later build on.

## Verification strategy

Nothing here treats a successful copy as evidence. Each claim has a check that
would fail if the claim were false:

| Claim | What would catch it being false |
|---|---|
| The inventory is closed | An unclassified upstream path is a hard error in `tools/migrate.py`, not a warning. `test_migration_inventory.py` re-reads the frozen tree independently and compares. |
| Migrated bytes are the frozen bytes | Compared against `git show <commit>:<path>`, not against the manifest that was written from the same read. |
| The extraction is reproducible | `tools/migrate.py --check` re-derives into a temporary tree and diffs, including file modes. |
| Templates are deterministic | Generated twice and compared; a full re-extraction is compared digest-for-digest. |
| Templates satisfy the frozen contracts | Validated by the *migrated* `workflow_state` module, imported out of the payload. |
| Semantics are equivalent to frozen v2.3.1 | The frozen suite runs unchanged against a fixture built only from `distribution/`, and the test *counts* are asserted against the upstream baseline — a vanished or silently skipped test fails. |
| Nothing reaches back into RepFlow | No functional file in the release may name the upstream checkout; the two frozen prose lines that do are pinned by exact location and count. |
| No live state crossed over | `.ai-review/`, locks, journals, approvals and RepFlow product work items are each asserted absent. |
| A clean target behaves like v2.3.1 | The bootstrapper's own output runs the frozen suite; its failure set must *equal* the documented exception list — a new unportable test fails the build rather than being absorbed. |
| Updates preserve local work | A second release is synthesized so the release-to-release path is exercised for real: added, changed and dropped files, with live work-item state written through the installed module and compared byte-for-byte afterwards. |
| A damaged release cannot be installed | A release copy is tampered with and every install path is asserted to refuse it, with the target left untouched. |
| A bootstrap does not overwrite the repository's own files | A target is given its own file at a release path; the bootstrap must refuse and leave it byte-identical. |
| An interrupted operation is repairable by re-running it | `_write` is made to fail at each point in a bootstrap and at the first write of an update; the re-run must converge to a clean, verified installation with repository-local state intact. |
| A report is never given without a check | `status` on an unverified installation must not contain the word "clean"; with several releases present, `status` and `verify` must still grade a target against its own recorded version. |
| A merged file that lost the installer's section is not "clean" | The Workflow's ignore lines and the managed `CLAUDE.md` section are each deleted; `verify` must report both, an update must restore both, and the repository's own content in either file must survive and never be reported as drift. |

The dependency closure itself was derived by ablation rather than by reading:
each candidate file was removed from a disposable repository and the frozen
suites re-run. `docs/MIGRATION.md` records what that found.

## Verification execution

`python3 tests/run_all.py` is a thin shim over `tests/parallel/cli.py`. It
runs the full selection in parallel and is the one gate command. `--select`
narrows a run for development, but a targeted run is never a gate. One
reduced selection is a gate, in one place only: see "One reduced selection
is a gate, in one place" below. The design record is
`docs/ai-workflow/WORKFLOW_MANAGER_ADAPTIVE_TEST_SHARDING_PLAN.md`; the
trunk model's changes are recorded in
`docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md`.

- **Inventory.** The atomic units are host test classes
  (`test_x.py::Class`) and, for the frozen conformance matrix, frozen
  classes (`frozen:<version>/<fixture>/<suite>.py::Class`). Discovery is
  deterministic and imports without running anything. A frozen suite whose
  class total differs from its pin is a hard error, so a vanished test
  cannot shrink the inventory quietly.
- **Plan.** The planner assigns units to `n` shards by longest processing
  time first, using `tests/parallel/timings.json`. It chunks an oversized
  frozen suite at class granularity, and never splits one class. Every
  chunk of a frozen suite builds its own fresh fixture repository. The
  plan must partition the selection exactly (no unit missing, none twice),
  and the partition is checked when the plan is written, when a shard
  runs, and when results are aggregated.
- **Phases.** Phase A runs every shard's chunks. It starts with A0: each
  declared exclusive unit alone, one at a time. Phase B then runs the 15
  matrix host classes in merged mode. They assert over the frozen chunks'
  records, merged against a context built from the plan and never from the
  records. A merge that is incomplete, duplicated or foreign is refused.
  One implicit check does not carry over. In direct mode,
  `test_the_fixture_state_file_is_the_clean_template` and
  `test_the_target_carries_no_upstream_host_document` read the fixture
  after all seven suites ran in it, so they also caught a suite writing
  into its state file or host documents. In merged mode they read a fresh
  repository, and per-chunk residue is measured only for `bootstrapped`.
  The plan's E-MRG-3 measured every suite's full residue at CP2 and found
  none unclassified, but nothing re-checks it on later runs.
- **Resources.** `tests/parallel/resources.json` declares the units that
  must not overlap anything (today, only
  `TestMigrateDoesNotDeleteASiblingAuthoredRelease`, which rewrites
  `distribution/workflow/2.3.1/`) and the guarded trees each one may
  write.
- **Timing data is not Workflow state.** `timings.json` only orders and
  balances work. It never selects, adds or drops a test. Observed timings
  go to a per-user cache outside the checkout.
  `--update-timings --profile local|ci` folds them into the committed
  file, which is the only working-tree file the tooling writes.
- **Exit codes.** `0` is all green. `1` means a test failed. `2` is an
  infrastructure fault: incomplete or foreign results, a digest mismatch, a
  refused merge, a killed or recordless chunk, a repository-integrity
  violation, a held run lock, a refused root run, a usage error, an
  undeclared orphaned process (`OrphanProcessError`), a Linux chunk whose
  orphan check was unavailable (`OrphanCheckUnavailableError`), a declared
  frozen unit sharing a chunk (`OrphanDeclarationError`), a missing or
  invalid orphan report (`bad_orphan_report`), or a refused Git config
  environment (`GitConfigEnvError`); see "Orphaned processes" below. When a
  run has both, `2` wins, and every observed failure is still listed. Each
  failure in the report carries a one-line reproduction command.

**CI.** `.github/workflows/workflow-manager-verify.yml` runs on every pull
request, every push to `main`, a nightly `schedule` (`17 3 * * *`, the
default branch) and on dispatch. Its `plan` job writes the plan, and the
plan's shard list becomes the `shard` matrix; nothing in the file names a
shard. Each shard job runs one shard (`--run-shard`) and uploads its
results. The `aggregate` job verifies every result against the plan, runs
phase B and reports. Every file the tooling writes lives under
`$RUNNER_TEMP`, and every job checks out full history. The dispatch input
`shards` overrides the count, so `shards=1` is the single-shard reference,
which the policy below restricts. The managed `workflow-conformance.yml` is
a separate, installed file, and it is not a required check: `workflow-manager
update` owns it and may rename its job.

- **Profiles.** `push`, `schedule` and `workflow_dispatch` runs always plan
  the full selection. A pull request's `plan` job first runs
  `tools/ci/choose_profile.py`, which picks `full` or `newest-release`
  (`--newest-release-only`) and writes its reasons to the job summary; see
  "Stopgap test profile" below.
- **One required test check.** `aggregate` keeps its name whatever the shard
  count and whatever the profile. It needs `plan`, every `shard` and the
  `package` job, runs `if: always()`, and its first step fails, naming the
  job, when `plan` or `package` did not succeed. Its exit code is the
  verdict. The repository's required checks are `aggregate` and `PR title`'s
  `Conventional Commit title`, both from the GitHub Actions app
  (`.github/repository/ruleset-main.json`).
- **Packaging on every run.** The `package` job builds and verifies the
  wheel and sdist exactly as a release does (`tools/release/package.py
  --version 0.0.0+ci`), so a packaging break fails the pull request, not the
  release.
- **Concurrency.** The group is
  `workflow-manager-verify-<event>-<ref for a pull request, else sha>`, and
  only pull requests cancel in progress. A newer push to a pull request
  cancels its stale run; a `main` push, a nightly or a dispatch run gets its
  own per-commit group and is never cancelled.
- **Nightly.** The `schedule` run is the full selection of the default
  branch. Its `nightly-alarm` job opens (or comments on) a `nightly-red`
  issue when `aggregate` did not succeed, and closes it on the next green
  nightly.
- **Release.** `.github/workflows/release.yml` publishes the Manager package
  from `main` after `main`'s full run is green; see `docs/RELEASING.md`.

**One reduced selection is a gate, in one place.** The newest-release
selection (`--newest-release-only`) is the pull-request profile of
`workflow-manager-verify.yml`. There it is the required `aggregate` check, a
merge gate for pull requests, and nothing else.

- It applies only when `choose_profile.py` finds no full-matrix path and a
  green `main`. Otherwise the pull request runs the full selection.
- `main` pushes and the nightly run always run the full selection.
- The Manager release requires `main`'s full run for the released commit.
- Every Workflow gate in this repository (checkpoint verification,
  implementation review, acceptance) still runs `python3 tests/run_all.py`,
  the full selection.
- A newest-release run is never cited as full-suite evidence; its evidence
  line says `newest-release selection`.
- `--select` and `--fast` remain targeted runs, which are never a gate.

This exception is a stopgap: M2 removes it (see "Stopgap test profile").

**Measured (CP7, and at the post-review head `2b4c0fd`, 2026-09-27).** 16
CPUs locally, `ubuntu-latest` with Python 3.12 in CI.

| run | wall |
| --- | --- |
| local serial (`--jobs 1`) | 2421 s (CP7); 2374 s (`2b4c0fd`) |
| local default (8 workers) | median 411 s (CP7); 389 s (`2b4c0fd`) |
| local `--jobs 16` (10/10 green in a row) | median 308 s |
| CI single shard | 110.8 min |
| CI 16 shards | 8.0 min median without GitHub's queueing, 9.3 min with it (CP7); 7.6 / 8.2 min (`2b4c0fd`) |
| CI 19 shards | 6.9 min median without GitHub's queueing, 9.7 min with it |

Plans balance perfectly on paper, so wall time is bound by total work (about
3,400 s locally at 8-way contention, about 6,200 s in CI). In CI it is also
bound by hosted-runner speed variance of about 0.7-1.1x between shards of
equal predicted load. The 5-minute CI target needs about 24 shards, above
the Free plan's 20 concurrent jobs, which cap this account at 19. The
timing sources are recorded in `tests/parallel/timings.json`. Refresh them
from new runs with `--update-timings` when reports keep listing `timing
drifted` or `timing defaulted` units, or after adding or reshaping tests
enough to move the plan. A refresh is a large, reviewable diff, so fold one
batch of runs at a time, not every run. A multi-class chunk yields only its
group overhead, so per-class numbers come from a run planned one class per
chunk.

Against the plan's section 7, P-3 (CI under 5.5 min) is documented as
unreachable under the 20-job cap, per its own clause. Two misses are
recorded as **accepted deviations, pending the user's confirmation**:
- P-2: serial 1.120x the pre-sharding baseline at CP7, and 1.098x at
  `2b4c0fd`. Like-for-like, excluding the runner's own new test module, it
  is 1.086x and 1.063x.
- P-5 CI: prediction is within +/-25 % in 2 of 5 runs, or 5 of 5 excluding
  GitHub's queueing. Shard balance is within 1.15 in 3 of 5 runs.

`docs/ACTIVE_MILESTONE.md`'s CP7 has the numbers.

**CI cost (`D-CI-Cost`).** GitHub bills nothing for these runs, because the
repository is public. On a private repository, a full run would bill about
113-121 runner-minutes at 16-19 shards (each job rounded up to whole
minutes), against 112 for the single-shard reference.

**Serial and single-shard runs are exceptional evidence.** Normal
full-suite verification, every gate included, uses the default sharded path:
`python3 tests/run_all.py` locally, and the `workflow-manager-verify.yml`
pipeline at its configured shard count in CI (for a pull request, at the
profile `choose_profile.py` picks, under the exception above). Forcing one worker or one
shard for the full suite, with `--jobs 1`, `--plan-only --shards 1`, the CI
dispatch input `shards=1` or anything equivalent, adds no coverage. It runs
the same selection under the same exit contract, only slower (about 40 min
locally and 110 min in CI). It is therefore never a routine confidence
rerun, and never a quiet substitute for the sharded path. Run it only when:

1. the active approved plan or an acceptance criterion explicitly requires
   serial or reference evidence (the sharding milestone's P-0/P-2, for
   instance); or
2. there is a concrete debugging need to compare serial and sharded
   behaviour, such as a failure that appears in only one of them.

A targeted `--jobs 1 --select ...` run for a narrow check is ordinary
development and is not covered by this rule.

**Reuse equivalent evidence rather than re-running it.** When a plan asks
for serial evidence and an equivalent serial run already exists, cite that
run. The two are equivalent when all of these hold:

- both runs are `evidence: full selection` with the same `selection_digest`
  and `tests_digest`;
- the cited run's own `verdict:` line was the one the gate needs (`exit 0`
  for a green gate). Neither digest records a verdict: a red run and a
  green run of the same selection carry identical digests;
- nothing that affects what the suite tests or how it runs has changed
  between the two `head` commits. That means `src/`, `tools/`,
  `distribution/`, `migration/`, `scripts/`, the test modules, and the
  runner itself (`tests/run_all.py`, `tests/parallel/`, `tests/support.py`,
  `tests/frozen_runs.py`), plus, for CI evidence,
  `.github/workflows/workflow-manager-verify.yml`. Check with
  `git diff --stat <evidence head>..HEAD`. One narrow exception: a change
  confined to `tests/parallel/timings.json` still counts as no change when
  the evidence run's plan is unchanged by it -- the same profile and worker
  or shard count give the same `n` and the same chunks (ids and members) in
  the same shards at both heads. Check it by diffing those fields of
  `--plan-only` output at the two heads, and record that you did. Estimates
  only order and balance work, so an unchanged plan runs the same chunks
  the same way; a changed one does not qualify, even if only the chunking
  moved;
- the criterion does not explicitly demand a fresh measurement.

`tree_digest` is deliberately *not* on that list. It moves with any change
to the tree, so workflow-state bookkeeping, review records, documentation
or unrelated metadata would invalidate it, and by themselves those changes
never force another serial run. The evidence becomes stale, and a fresh run
is required, when any of the following changes:

- implementation code that affects tested behaviour;
- the inventory or the selection (a digest moves);
- the test execution semantics, or the serial runner itself;
- the criterion, which now demands a fresh number;
- anything else that concretely makes the old run no longer equivalent.

When you reuse a run, record the original run's identifier (its results
directory, or its CI run URL), its `head` and its verdict. Record its
`selection_digest`, `tests_digest` and test count, taken from the report's
`evidence:` line or `results.json`'s `identity`. Also record why it is still equivalent for the
current gate: the diff between the two heads and why it does not matter.
Every run prints that `evidence:` line and stores the same fields in
`results.json` (a CI shard stores them in its `shard-<k>.json`), so a later
gate can cite a run instead of repeating it.

This policy only removes redundant execution. It never weakens an explicit
acceptance criterion. It never hides a discrepancy between serial and
sharded results, which is itself a finding to investigate. It never reuses
evidence across materially different implementation or test states. A
required fresh serial run that exceeds a controller's drain or detach limit
is declared as an explicitly long-running operation, under the
Controller/Workflow protocol. It is never silently swapped for the sharded
path, nor the sharded path for it.

**The guarded trees are read-only while a run is live.** Every mode takes a
per-worktree run lock (`<git dir>/wm-verify/run.lock`). A run that
executes tests also removes write permission from every directory under
`distribution/`, `migration/`, `src/` and `tools/`. File modes are never
touched. This makes an undeclared test that creates, deletes or renames
something there fail by name. It also makes those trees read-only to you
until the run ends. Saving a new file there fails with `EACCES`, and so
does an editor's atomic-rename save, or a `git checkout`/`switch`/`stash`/
`pull` that touches them. A branch switch can be left half-applied. The
run restores the original modes when it ends, including on `SIGINT` and
`SIGTERM`. After a `SIGKILL`, the next run restores them first. Or run
`python3 tests/run_all.py --restore-barrier`, which refuses while any
process of the killed run is still alive.

A before/after snapshot of the tree, ignored files under the guarded trees
and `tests/` included, catches persistent changes. A static lint over
`tests/*.py` catches the writer patterns that neither the barrier nor the
snapshot sees. One gap remains: a transient in-place overwrite by code the
lint cannot see.

**Limitation: the barrier propagates into copies.** `shutil.copytree`
copies directory modes. So a copy of a guarded tree made during a run
arrives with read-only directories. Overwriting an existing file in the
copy works. Creating, deleting or renaming inside it fails with `EACCES`,
which is a false failure caused by the barrier. No test does this today. A
future test that needs to must restore `u+w` on its own copy first.

**Orphaned processes.** Git 2.55 detaches automatic maintenance
(`gc --auto`, `maintenance run --auto`) after commits, and the detached
process leaves the chunk's process group, so the runner's group kill misses
it. It is re-parented to the nearest subreaper, which under a Workflow
Controller is the Controller. A full run with the default Git config handed
42,158 orphans to an outer probe, and under Controller `1.3.0` they became
zombies until they filled the per-user process limit. The design record is
`docs/ai-workflow/WORKFLOW_MANAGER_TEST_CLEANUP_PLAN.md`. Two layers switch
the maintenance off at the source, and a leak check fails any run that still
orphans something.

- **The settings.** `THROWAWAY_GIT_CONFIG` in
  `src/workflow_manager/fixture.py` holds `maintenance.auto=false`,
  `gc.auto=0`, `maintenance.autoDetach=false` and `gc.autoDetach=false`.
  Nothing writes them outside a throwaway repository, a chunk's environment
  or the run's template directory. The global and system Git config are
  never touched.
- **The environment layer** (`isolation.chunk_env`). Every chunk's
  environment appends the four pairs to the `GIT_CONFIG_COUNT` series. The
  parent's entries are kept, and a pair is appended only when the key's last
  inherited value differs (keys compare case-insensitively). A malformed
  series, or a `GIT_CONFIG_PARAMETERS` that sets one of the keys, includes
  a file (`include.path`, `includeIf.<condition>.path`) or cannot be
  parsed, is refused as `GitConfigEnvError` (exit `2`), because
  `GIT_CONFIG_PARAMETERS` outranks the series. An include in the series
  itself is kept: the four pairs come after it and win. The executor also builds
  `<run_dir>/git-template/` once per run, from Git's default template plus
  a `config` holding the four keys, and sets `GIT_TEMPLATE_DIR` to it, so
  every repository a chunk initialises or clones carries them in its own
  local config. This is the only layer that reaches the frozen suites'
  own repositories, and it also reaches the frozen engine's scratch evidence
  clone, whose named test runs Git with a `PATH`-only environment.
- **The per-repository layer.** `configure_throwaway_repo(root)` writes the
  keys into one repository, and `init_git_repo` calls it. Every host
  `git init` is an `init_git_repo` call, and every clone is followed by
  `configure_throwaway_repo` on its destination, so a direct run outside the
  runner is covered too. `test_orphan_processes.py`'s `TestRoutingCheck`
  statically checks every `init`/`clone` site in the host test modules, the
  runner and `src/workflow_manager/`, bound to the repository the site
  creates. A new site that bypasses the
  helpers fails the suite, unless it is in the check's reasoned exemption
  list.
- **The leak check.** Each chunk runs under `tests/parallel/reaper.py`, a
  stdlib-only wrapper (`python3 -I -S -B`) that makes itself a child
  subreaper and starts the chunk as its only child. Every orphan the chunk
  leaves is re-parented to the wrapper, which records it (its command line,
  or `[<comm>]` when that reads empty, as it does for Git's detached
  maintenance) and reaps it. After the chunk exits it waits for at most
  5 s, stopping at once when nothing is left, then kills and reaps the rest
  in a loop until none remains. It writes
  `<run_dir>/orphans/<chunk>.json` and exits with the chunk's own status,
  so the chunk's outcome is classified as before. Reaping lives in the
  wrapper, never in the runner, because the runner waits for its own
  children by pid and a reaper there would steal their exit statuses.
- **The verdict.** An undeclared orphan is an `OrphanProcessError` naming
  the chunk and the orphans' labels. A report that is missing, unreadable,
  another chunk's or inconsistent with the wrapper's exit is
  `bad_orphan_report`, never "no orphans". On Linux, a chunk whose wrapper
  could not run the check is `OrphanCheckUnavailableError`, decided on the
  report's own `platform`. On other platforms the report prints `orphan
  check: unavailable on this platform` and the run can still pass. All
  three apply in local, `--run-shard` and `--aggregate` modes, since a
  chunk's orphans travel in its `ChunkResult`. The report prints `orphan
  check: on`, and it lists every tolerated orphan by chunk.
- **Declared sources.** `tests/parallel/resources.json`'s optional
  `orphan_sources` maps an exact unit id, host or frozen, to a non-empty
  `reason`. An unknown unit is a schema error. Only a chunk that contains a
  declared unit has its orphans tolerated. A declared frozen class
  therefore runs in a chunk of its own (`<group>#<Class>`), and a chunk
  that mixes one with another unit is `OrphanDeclarationError`. The policy
  is to fix an orphan from this repository's own code at the source, and to
  declare it only when orphaning is the test's subject. An orphan from
  frozen code is declared with its class named. A declaration that
  tolerated nothing in a run is listed as unused. Today there are 20
  declarations: five host classes that kill chunk groups on purpose, and
  the frozen `TestStateLock` in all 15 release and fixture pairs, whose
  `multiprocessing` forkserver (the default on Python 3.14) outlives its
  chunk.
- **Whole-run use.** The same wrapper measures a whole run:

  ```bash
  python3 -I -S -B tests/parallel/reaper.py --report <file> --chunk-id whole-run -- python3 tests/run_all.py
  ```

  Its report lists every orphan that escaped the per-chunk wrappers. At
  the test-cleanup milestone's CP3, a full run under it, with no
  `GIT_CONFIG_*` exported, listed none, against 42,158 at the milestone's
  base. None of the orphans the per-chunk wrappers reaped was Git
  (`docs/ACTIVE_MILESTONE.md`, CP3).
- **Residuals.** On timeout, interrupt or `SIGKILL`, a chunk's wrapper
  dies with it, as does a wrapper whose own fault path cannot finish its
  kill loop. Orphans adopted after that go to the next subreaper up. The
  runner's own Git calls, the plan step and `prepare_merge` run outside
  any wrapper; they start no detached work. The check is off on non-Linux
  hosts, and says so. Code that runs `git init` or `git clone` under an
  environment it builds from scratch gets neither layer. No such site
  exists in this repository's code, and the leak check fails the run if a
  frozen one ever orphans. The managed `workflow-conformance.yml` runs the
  installed suites outside the runner, in CI only.

### Stopgap test profile

About 96% of the full selection re-runs the frozen suites of every
Workflow release in `distribution/`, in three fixtures each. Until M2 moves
the releases out of this repository (`docs/ROADMAP.md` 10.2), a pull request
may run a reduced selection instead: every host unit plus the newest
release's frozen units (`--newest-release-only`). It is a gate only as the
exception above states.

`tools/ci/choose_profile.py` decides, and any doubt means `full`:

- any event but `pull_request` is `full`;
- **rule 1:** every path of the merge ref's diff against its base (both
  sides of a rename, deletions too) is classified by the longest matching
  rule in `tools/ci/pr_profile_paths.json`. `distribution/`, `migration/`,
  `tools/`, `src/`, the shared test infrastructure, the matrix host modules,
  `.github/` and `pyproject.toml` are `full`; documentation, the installed
  Workflow copy and each other host test module (by exact path) are
  `newest-release`. An unmatched path is `full`, and a test proves every
  path of the tree, tracked and untracked, matches an explicit rule, so a
  new top-level path or test module must be classified in its own pull
  request, which then runs `full` because it edits `tools/`;
- **rule 5:** otherwise the newest completed `push` or `schedule` run of
  the verification workflow on `main` must be green; a red, cancelled or
  missing run, or an API failure, is `full`;
- a git failure, or a head that is not a two-parent merge, is `full`.

The other rules are enforced elsewhere: the release waits for `main`'s full
run (`release.py assert-full-plan`, rule 2), `aggregate` is the one required
test check (rule 3), the gate policy is the exception above (rule 4), and a
red nightly opens an issue (rule 5).

**Where M2 finds it (rule 6).** Stopgap code and data carry the marker
`STOPGAP(M2)` in one of two forms only: a line-leading comment (`#
STOPGAP(M2)`, the first token on its line in Python, or a line matching
`^\s*# STOPGAP\(M2\)` in YAML), or a JSON `"_comment"` value that starts with
`STOPGAP(M2)`. Documentation (`docs/` and every `*.md`) is never scanned.
The marked files are exactly:

<!-- stopgap-marked-files:begin -->
- `.github/workflows/workflow-manager-verify.yml`
- `tests/parallel/cli.py`
- `tests/parallel/inventory.py`
- `tests/parallel/planner.py`
- `tests/parallel/report.py`
- `tests/test_stopgap_profile.py`
- `tools/ci/choose_profile.py`
- `tools/ci/nightly_alarm.py`
- `tools/ci/pr_profile_paths.json`
<!-- stopgap-marked-files:end -->

M2 deletes `tools/ci/choose_profile.py`, `tools/ci/nightly_alarm.py`,
`tools/ci/pr_profile_paths.json` and `tests/test_stopgap_profile.py` whole,
and in the other files removes each block that opens with the marker (in
`tests/parallel/`, down to its `End of the STOPGAP(M2) block.` line). Every
reference the runner's stopgap depends on sits inside such a block,
including the `NEWEST_RELEASE_KIND` import, the `newest_release_only`
entries of the mode tables, the `--newest-release-only` help text and the
comments that name its selection kind, so that removal alone leaves a
working runner. That restores the single CI profile: the `choose_profile`
step and the `NEWEST` wiring leave the `plan` job, the `nightly-alarm` job
leaves the workflow (the nightly run itself may stay), and `plan`'s
`profile` output and `actions: read` go with them. M2 also deletes the
exception "One reduced selection is a gate, in one place" above and this
subsection. `tests/test_stopgap_profile.py` proves the list above equals the
marked files, and that every file that names a stopgap identifier
(`newest-release`, `newest_release`, `NEWEST_RELEASE`, `choose_profile`,
`nightly_alarm`, `nightly-alarm`, `nightly-red`, `pr_profile_paths`) is
marked, so a stopgap block left in an unlisted file fails the suite. It also
carries the removal out on a scratch checkout: after deleting every marked
block under `tests/parallel/`, no file there names a stopgap identifier, and
the runner's `--help`, `--list`, `--plan-only` and a real run succeed while
`--newest-release-only` is an unknown argument.
`selection_kind` in `tests/parallel/planner.py` and `release.py
assert-full-plan` are permanent and stay.

## Squash merges and the installed Workflow

`main` takes only squash merges, so once a milestone's pull request merges,
its branch commits (plan approval, checkpoints, bundle-generation records,
technical approval) become unreachable after the branch is deleted and
garbage-collected. That is safe for the installed Workflow `2.6.0`,
established by `workflow-manager-trunk-model`'s CP6 (its record is in
`docs/ACTIVE_MILESTONE.md`):

- **Static audit.** Every git history or object read in
  `scripts/workflow_state.py` and `scripts/workflow_fingerprint.py` is
  branch-local (it runs on the active item's own branch, before the merge),
  reads state *content* (reachable commits only, never a recorded SHA), or
  is legacy/cross-worktree only. None resolves a SHA a completed item
  records. The one loop over every work item that touches git
  (`validate_state(repo_root=)`) reads each item's registry in the working
  tree, which the squash keeps. `workflow-manager verify` reads no history.
- **Tested.** `tests/test_squash_merge_compat.py` drives an item to
  `MILESTONE_COMPLETE` in a disposable repository, squashes its branch onto
  `main` with a blank body, deletes the branch, expires the reflog and
  prunes, then, in the repository and in a fresh clone, requires the state
  to validate, the item's id to be refused for reuse, a new item to be
  planned, approved and implemented, and `workflow-manager verify` to be
  clean.
- **Checked once on this repository.** A scratch clone with
  `workflow-manager-adaptive-test-sharding`'s branch squashed and pruned
  passed the same assertions under `2.5.1` and after an update to `2.6.0`.

Two limits, neither a problem today. Calling `implementing_entry_reachable`
or `complete_work_item` on an already-completed item fails closed; no
command does. And the dormant `D-Legacy` import path
(`verify_legacy_branch_reconciliation`) needs a `LEGACY_READY` item's
reviewed commit to be an ancestor of `HEAD`, so a legacy branch integrated
by squash could never be promoted; this repository has no such item.

## Extension points

The bootstrapper is deliberately small. These are the seams later Workflow
Manager functionality and Controller integration are meant to build on, rather
than reaching into the internals:

| Seam | What it gives a caller |
|---|---|
| `Release` | A migrated release, addressed by version, verifiable from its own manifest. Adding a second release is adding a directory, not changing code. |
| `Release.installable(profile)` | The install set — payload plus release-owned templates. `bootstrap`, `update` and `drift()` all read it, so they cannot disagree about what the release owns. A new profile is one entry in `_PROFILE_CATEGORIES`. |
| `available_versions()` / `find_release()` | Which releases exist and which one a command means. Adding a release is adding a directory. |
| `Installation` | What a repository has, as data. A Controller asking "which of my repositories are on which release" reads these files; it does not need to inspect trees. |
| `drift()` / `verify()` | A structured answer (`Drift(path, kind, detail)`), not a printed report, covering release-owned, generated and merged content alike. Fleet-wide health is a loop over targets. |
| `Status.verified` | Whether a report was actually measured against a release. A fleet view that treats "unverified" as "healthy" is the bug this field exists to prevent. |
| `update()` | Returns the new record and the list of changes. Safe by default: it refuses rather than discarding local edits, so an orchestrator does not need its own guard. |
| `build_target_repo()` / `build_conformance_repo()` | Disposable repositories from a release. Any new operation can be proven against one before it touches a real consumer. |

Deliberately absent: orchestration across repositories, scheduling, rollback
history beyond `update()`'s symmetry, and any notion of a "real" consumer.
Those are Controller concerns, and building them here would fix decisions that
should stay open.

### What a second upstream release needs

1. A classification entry for its tag and commit.
2. `python3 tools/migrate.py`, producing `distribution/workflow/<version>/`.
3. `python3 tests/run_all.py` — the conformance fixture must be green, and the
   clean target's failure set must equal the documented exceptions.

Nothing else. `bootstrap` and `update` already mean the newest release, and
`status` and `verify` already resolve a target's own version, so a second
release changes no code and no command line.

`update()` already handles files added, changed, and dropped between releases;
`tests/test_bootstrap.py::TestReleaseToReleaseUpdate` proves that against a
synthesized second release rather than waiting for a real one, and
`TestReleaseResolution` proves the resolution rules against a `distribution/`
holding two.

## Authored releases

Not every new release is a new upstream tag. `2.4.0` (the plan-amendment
mechanism, `docs/ai-workflow/PLAN_AMENDMENT_MECHANISM_PLAN.md`) originates in
*this* repository: a small, hand-written change to Workflow behavior that has
no upstream commit to extract it from. `tools/build_release.py` is a second,
separate producer of a `distribution/workflow/<version>/` tree, kept apart
from `tools/migrate.py` (whose "frozen upstream tag -> `distribution/`"
contract stays untouched) precisely because the two trust boundaries differ:
`migrate.py` only ever copies bytes it can check against `git show
<commit>:<path>`; `build_release.py` composes bytes this repository itself
authored.

**The composition.** A base release (already migrated, already verified
against its own manifest) plus an overlay
(`migration/overlays/<version>/payload/` at the same target-relative paths
`distribution/workflow/<version>/payload/` uses, classified by
`migration/overlays/<version>/classification.json`, the same ruleset shape
`migration/classification.json` uses): every base file the overlay does not
name is copied forward byte-for-byte; every file it names either adds a new
path or replaces a base one, cross-checked against the base release's own
manifest rather than trusted blindly.

**Byte-level provenance for the authored half.** `tools/migrate.py`'s
manifest already gives the upstream half of a release "this exact file, this
exact upstream commit." An authored release needs the same discipline for
the half nothing upstream can vouch for: every file the overlay *replaces*
(not merely adds) gets an additive `overlay_delta` field —
`{"base_sha256": "<the base file's own hash>", "diff_sha256": "<sha256 of a
unified diff between the base file and the overlay file>"}` — so a full-file
replacement carries a record of *what changed*, not only what it changed to.
`tools/build_release.py --check` re-derives the whole tree from the base
release plus the overlay and diffs it against what is committed, exactly
`tools/migrate.py --check`'s own contract adapted to a base+overlay input;
`TestAuthoredReleaseOverlayDelta` additionally reproduces every recorded
`overlay_delta` from `base payload + diff` alone.

**`manifest.json.provenance`** is the field that distinguishes an authored
release from an extracted one: `{"origin": "upstream"}` (the default a
manifest predating this field reads as) for one `tools/migrate.py` produced,
or `{"origin": "authored", "base_release": "<version>", "overlay_commit":
"<this repository's own commit at build time>"}` for one
`tools/build_release.py` produced. It sits *alongside* the existing
`upstream` key, never replacing it — `Release.__init__`, `cli.py`,
`install.py` and `installation.py` all read `manifest["upstream"]`
unconditionally, so an authored release's manifest keeps the base release's
own upstream triple, copied forward: an authored release is still,
transitively, provenanced from that upstream tag, just not *directly*.
`Installation` persists the same `provenance` into a bootstrapped target's
own record, additively, so `status` can report which kind of release a
target was bootstrapped from without a schema bump on either side.

**Nothing about installing, updating, or reporting on a release changes.**
`Release.installable(profile)`, `bootstrap`, `update`, `drift()`, `status`
and `verify` all read a release through the same manifest/payload shape
regardless of how it was produced — an authored release is exactly as
installable as an extracted one, because by the time it is committed under
`distribution/workflow/<version>/` the two are the same shape of tree. The
per-release conformance matrix (`tests/support.py`'s `CI_SUITES` and
`migration/portability_exceptions.json`'s `by_version`, both keyed by
`workflow_version` since `2.4.0`) is what actually proves that: each
release's own frozen/authored suite runs, and passes or documents its own
exceptions, independently of any other release present in the same
`distribution/`.

See `docs/MIGRATION.md`'s "Workflow v2.4.0" section for the concrete record
— what was authored, the exact provenance values, and the evidence — and
`CLAUDE.md`'s "Adding an authored Workflow release" for the operator
procedure, including the downgrade posture an authored release that widens a
closed vocabulary (a new `CHECKPOINT_STATUSES`/`APPROVAL_STATUSES` member, for
instance) creates.
