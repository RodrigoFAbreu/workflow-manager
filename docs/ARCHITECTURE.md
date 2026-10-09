# Architecture

Workflow Manager installs a published Workflow release into other
repositories. Two things must never blur together, and the whole design is
arranged around keeping them apart:

- **Canonical release content** — immutable, versioned, byte-identical to a
  published package whose digest the Manager pins. It reaches a machine as a
  download, lives in a verified per-user cache, and is never edited.
- **Target-repository state** — mutable, repository-local, owned by whoever
  runs the Workflow. Work items, approvals, bundles, checkpoints. Workflow
  Manager creates it once and afterwards never overwrites it.

An update replaces the first and preserves the second. That single sentence is
the reason for most of the structure below.

## Packages, pins, source and cache

Since M2 (`docs/ai-workflow/WORKFLOW_MANAGER_PACKAGED_DISTRIBUTION_PLAN.md`)
this repository holds no Workflow release. The release boundary is four
pieces, each with one job:

- **The package** (`src/workflow_manager/package.py`, `D-Package-Format`).
  Version `V` is three assets: `workflow-V.tar.gz`, whose single top-level
  `workflow-V/` directory holds exactly the release directory
  (`manifest.json`, `payload/`, `fixtures/`, `templates/`);
  `workflow-V.manifest.json`, a byte copy of that manifest; and
  `SHA256SUMS`. The archive is deterministic: members come from the manifest,
  never from a directory walk, sorted, with `mtime 0`, `0:0`, and modes
  `0755`/`0644` from the manifest's `executable` flag. Extraction accepts
  only regular files and directories under `workflow-V/`, requires the file
  set, digests, sizes and modes to equal the manifest's, stages the tree in a
  temporary sibling and publishes it by `rename`. Anything else is
  `ReleaseIntegrityError`, and nothing is left behind.
- **The pins** (`src/workflow_manager/published_releases.json`, `D-Pins`),
  shipped in the wheel. They are the trust root: for each published version,
  the archive name, its sha256 and the sha256 of its `manifest.json`. Only a
  pinned version installs from a package. A download is accepted only when
  the archive matches the pin **and** the published `SHA256SUMS`, and the
  manifest asset matches `manifest_sha256`, so a re-published asset is
  detected even when it agrees with a re-published `SHA256SUMS`.
- **The source** (`D-Release-Source`): `--release-source`, else
  `WORKFLOW_MANAGER_RELEASE_SOURCE`, else
  `https://github.com/RodrigoFAbreu/workflow/releases/download/v{version}/`.
  A URL template (`https://`; `file://`; `http://` only to a loopback host)
  or a local directory of `<version>/` subdirectories. Redirects never
  downgrade the scheme. Integrity never rests on the transport; the pins
  carry it.
- **The cache** (`D-Release-Cache`): `--release-cache`, else
  `WORKFLOW_MANAGER_RELEASE_CACHE`, else
  `$XDG_CACHE_HOME/workflow-manager/releases`, else
  `~/.cache/workflow-manager/releases`. An entry `<cache>/<V>/` holds the three
  assets, the extracted `tree/` and a `complete` marker written last. Under an
  `fcntl` lock on `<cache>/<V>.lock`, an entry is a hit only when `complete`
  names the pinned digest, the archive hashes to it, `tree/manifest.json`
  hashes to the pin's `manifest_sha256`, the manifest's version is `V`, and
  `Release(tree).verify()` passes. A hit does no network I/O. A miss or a
  broken entry is discarded (`discarding cache entry …` on stderr) and
  refetched; a broken entry is never used.

`ReleaseCache.resolve(V)` then copies the manifest-enumerated files into a
private snapshot (`mkdtemp`, `0700`), verifies **the snapshot** against the
pin, and returns a `Release` over it. Nothing after that reads the shared
cache, and every installed byte is read through `read_verified` against the
snapshot's manifest, so a writer that changes the cache after the lock is
released cannot reach a target. `ReleaseCache.ensure(V)` is the same without
the snapshot; the test runner's priming uses it.

A local, unpackaged directory (`--release-dir`, or the deprecated
`--manager-root` alias pointing at an old checkout's
`distribution/workflow/<V>/`) goes through `source.local_release`: a
directory claiming a **pinned** version must hash to that pin's
`manifest_sha256` or is refused, so an altered `2.6.0` is never installed as
`2.6.0`; a directory claiming an **unpinned** version is a release in
development, checked by `Release.verify()` only and recorded as
`source.kind: "local"`. Either way it is snapshotted first.

The installation record carries an optional `source` object, `{"kind":
"package", "repository", "archive", "sha256"}` or `{"kind": "local"}`.
Records written before M2 lack it and still read; `SCHEMA_VERSION` stays `1`.

## Repository layout

```
src/workflow_manager/
  release.py                   read and verify a release from its own manifest
  package.py                   build, verify and safely extract a release package
  source.py                    pins, release source, verified release cache, local directories
  published_releases.json      the pins: the trust root, shipped in the wheel
  fixture.py                   build disposable repositories from a release
  install.py                   bootstrap, update, drift
  installation.py              the installed-version record in a target
  cli.py                       command-line entry point
tools/
  workflow_packages.py         build and prove packages from a committed release tree
  release/                     the Manager's own releases: titles, versions, packaging
tests/                         stdlib unittest, no third-party dependencies
  portability_exceptions.json  frozen tests a clean target cannot pass, per pinned version
docs/
  MIGRATION.md                 the Phase-A record, each authored release's record,
                               and the M2 packaging and removal record
  ARCHITECTURE.md              this file
  defects/                     upstream defects found, documented, not repaired
  RELEASING.md                 how the Manager is released, and how a pin is added
.github/
  workflows/                   verification, PR title, release, and the managed conformance check
  repository/                  merge settings and the `main` ruleset, as reviewed data
```

A release directory, inside a package or a cache entry's `tree/`, is:

```
manifest.json                  every path's disposition, with digests
payload/                       Workflow files, byte-identical, target-relative paths
fixtures/                      host documents the frozen suite asserts on
templates/                     clean repository-local initial state, and the
                               release-owned files rendered rather than copied
```

## Why payload paths are target-relative

A release's `payload/scripts/workflow_state.py` installs to
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

## Update planning

`update` is `plan_update` (decide, write nothing) followed by `apply_update`
(write). `UpdatePlan` carries the changes, removals, writes (including a
repaired executable bit), what is left alone, the locally modified files a
forced update would overwrite, and the record that would be written.
`bootstrap` and `update` share one merge planner. `apply_update` takes the
release only to refuse a plan made for another one, and writes in the old
order (removals, release files, state templates, merges, record last), so the
interruption contract below is unchanged.

`workflow-manager doctor` and `update --dry-run` (`src/workflow_manager/
compatibility.py`) use the plan to report what an update would do and which
Workflow guarantees it would cross. They never write the repository: Git is
run with a hermetic environment and flags, the work tree and Git directories
are protected by path arithmetic before anything is resolved, and a partial
clone skips the commands that would fetch. A configured Git clean/process
filter is arbitrary code that `git status` could run on a tracked file whose
`filter` attribute selects it, so when a configured driver is selected by a
tracked path (decided read-only, by `config`, `ls-files` and `check-attr`,
which run no filter), or that cannot be ruled out, the tree-state check is
skipped and reported as an incomplete inspection. A driver that no tracked path
selects (Git LFS installed system-wide, say) never runs, and the check goes
ahead. The path lists cross `run_git(..., raw=True)`, which keeps every byte
(a non-UTF-8 name, a `\r` in a name) intact; on a very large index the pipe can
exceed `GIT_TIMEOUT_SECONDS` and fails closed with the same warning. A
filter configured in a submodule cannot run either: the status call passes
`--ignore-submodules=dirty`, which compares only a submodule's HEAD with the
recorded commit: a moved gitlink, staged or not, still reads as modified, and
edits inside a submodule's work tree do not (an update never writes there). The
package disables bytecode writing as it loads, so a checkout that is both the
Manager's source and the target gains no `.pyc` except the package's own
`__init__`, which Python compiles before any code of it can run. Any link
inside the release cache is refused, whether or not it resolves into the
target (broader than the path arithmetic needs). What they do write is the release
cache (a missing release is fetched, under the cache's lock) and one
temporary copy of the release, in a directory outside the repository. The
release knowledge the report needs is three tables in `compatibility.py`
(`DOWNGRADE_BOUNDARIES`, `NEW_WORK_ONLY`, `GATE_DEFAULT_CHANGES`), each with an
entry for every pinned version (`GATE_DEFAULT_CHANGES` uses `""` for none),
enforced by a test; the report reads each table.

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
nothing is installed that was not checked first, at every hop: the downloaded
archive against its pin and `SHA256SUMS`, the extracted tree against its
manifest, the cache entry against the pin on every hit, the private snapshot
against the pin again, and each file against the snapshot's manifest digest as
it is copied. A package that was re-published, corrupted in transit, damaged
in the cache or edited fails the install (`ReleaseIntegrityError`, exit `1`)
before anything is written to the target, rather than handing it
non-canonical bytes under a canonical version label — which would also leave
the record describing files that are not there.

A release that cannot be obtained fails as loudly. An unpinned version with no
`--release-dir` is `ReleaseNotPublishedError`; a pinned version that is not
cached and cannot be fetched is `ReleaseUnavailableError`, naming the version,
the source URL and the cache directory. Both exit `1`. With the cache primed,
every command works offline.

## Which release a command means

Several releases are pinned at once, and the two kinds of command mean
different things by "the release":

| Command | Default | Why |
|---|---|---|
| `bootstrap`, `update` | the newest pinned release | These *choose* which release a repository is on; "the current one" is the only sensible default, and `--release-version` pins. |
| `status`, `verify` | the release the target's own record names | These *report on* an installation. Grading a repository against a release it was never installed from would make every target look broken the moment a newer one landed. |

`status` never reports an installation it did not check. If no release is
available to compare against it says so; it cannot say "clean" without having
looked. A target recording an unpinned version needs `--release-dir` for
`status` and `verify`; `status` still prints what it knows without it (the
recorded version, profile, `source` and install time).

## Boundaries this design keeps

- Nothing in a release reads outside its own tree.
- Nothing in a release names the upstream checkout, except the manifest's
  provenance record and two lines of frozen design prose.
- Nothing in this repository composes a Workflow release. Releases are built
  and published from the `workflow` repository; this repository pins them.
- The bootstrapper is verified against disposable repositories only. It has no
  notion of a "real" consumer, and nothing here touches one.
- Controller orchestration is deliberately absent. The installation record and
  the drift report are the surfaces a controller would later build on.

## Verification strategy

Nothing here treats a successful copy as evidence. Each claim has a check that
would fail if the claim were false:

| Claim | What would catch it being false |
|---|---|
| A package is deterministic | `test_release_source.py`'s `TestDeterministicBuild`: two builds are byte-identical, members are manifest-enumerated, and bytecode or debris in the release directory changes nothing. |
| A package reproduces its release | `TestRoundTrip` extracts a build and compares file set, bytes and modes. For the five published releases this was proved once, when they were built, against the committed trees at `ec38979`; `docs/MIGRATION.md` records it. |
| Extraction cannot escape or smuggle | `TestSafeExtraction`: links, devices, absolute paths, `..`, duplicates, extra or missing files, wrong digests, sizes or modes, and oversize archives are each refused, with nothing left behind. |
| A published package is the pinned one | `TestPinChecks`: an archive that differs from its pin or from `SHA256SUMS`, or a manifest asset that differs from `manifest_sha256`, is refused, including a re-published pair that agree with each other. `test_published_packages.py`'s `TestPinnedPackagesVerify` re-verifies every pinned package, through the cache, on every run. |
| A cache entry is never trusted | `TestCache`, `TestSnapshots`, `TestLocking`: a damaged, foreign or half-written entry is discarded and refetched; a tree altered during the snapshot is caught; a change after the snapshot reaches nothing; offline with nothing cached is a named `ReleaseUnavailableError`. |
| A local directory cannot impersonate a published release | `TestLocalRelease`: a directory claiming a pinned version must hash to the pin; an unpinned one installs as `source.kind: "local"`. |
| Semantics of the newest release are intact | The newest pinned release's frozen suites run unchanged in four fixtures (conformance, clean target, bootstrapped, and updated from the release below it), and the test *counts* are asserted against `tests/support.py`'s `CI_SUITES` — a vanished or silently skipped test fails. |
| A clean target behaves like the release | The bootstrapper's own output runs the frozen suite; its failure set must *equal* `tests/portability_exceptions.json`'s entry for that version — a new unportable test fails the build rather than being absorbed. |
| Every pinned version carries its records | `TestPinnedVersionsCarryTheirRecords`: the pins, `CI_SUITES`' keys and the exceptions' `by_version` keys are the same set, so a new pin cannot land without its counts and exceptions. |
| The real update path works | `test_update_path.py` bootstraps the release below the newest, updates it through the CLI, and runs the newest frozen suites in the result (the `updated` fixture). |
| Updates preserve local work | A second release is synthesized so the release-to-release path is exercised for real: added, changed and dropped files, with live work-item state written through the installed module and compared byte-for-byte afterwards. |
| A damaged release cannot be installed | A release copy is tampered with and every install path is asserted to refuse it, with the target left untouched. |
| A bootstrap does not overwrite the repository's own files | A target is given its own file at a release path; the bootstrap must refuse and leave it byte-identical. |
| An interrupted operation is repairable by re-running it | `_write` is made to fail at each point in a bootstrap and at the first write of an update; the re-run must converge to a clean, verified installation with repository-local state intact. |
| A report is never given without a check | `status` on an unverified installation must not contain the word "clean"; with several releases pinned, `status` and `verify` must still grade a target against its own recorded version. |
| A merged file that lost the installer's section is not "clean" | The Workflow's ignore lines and the managed `CLAUDE.md` section are each deleted; `verify` must report both, an update must restore both, and the repository's own content in either file must survive and never be reported as drift. |
| No test reaches a release around the pins | `test_internal_references.py`'s `TestNoTestResolvesAReleaseThroughTheLayout` fails any test that names the old release-directory layout or imports the retired discovery API, and `TestNoLiteralCliEnvironment` any subprocess environment that would drop the primed cache. |

The dependency closure of `2.3.1` was derived by ablation rather than by
reading: each candidate file was removed from a disposable repository and the
frozen suites re-run. `docs/MIGRATION.md` records what that found, and the
migration-era checks (inventory closure, byte identity with the upstream tag,
reproducible extraction and authored-overlay composition) that ran until M2
retired them with the trees they checked.

## Verification execution

`python3 tests/run_all.py` is a thin shim over `tests/parallel/cli.py`. It
runs the full selection in parallel and is the one gate command. `--select`
narrows a run for development, but a targeted run is never a gate. There is
no other selection: pull requests, `main` pushes, the nightly run and every
Workflow gate run the same full one. The design record is
`docs/ai-workflow/WORKFLOW_MANAGER_ADAPTIVE_TEST_SHARDING_PLAN.md`; the
trunk model's changes are recorded in
`docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md`, and M2's (priming,
the tested releases, one selection) in
`docs/ai-workflow/WORKFLOW_MANAGER_PACKAGED_DISTRIBUTION_PLAN.md`, 7.

- **Priming.** Every mode but `--restore-barrier` first resolves **every
  pinned version** of the checkout under test into the release cache
  (`tests/parallel/priming.py`, `ReleaseCache.ensure`), in a subprocess that
  imports the checkout's own `src/` and reads its own pins, then exports the
  resolved directory as `WORKFLOW_MANAGER_RELEASE_CACHE` to discovery and to
  every unit. A version that cannot be put in the cache is `PrimingError`
  (exit `2`), naming the cache directory and the source. After priming, a run
  needs no network. `support.cli_env()` carries the cache (and
  `WORKFLOW_MANAGER_RELEASE_SOURCE`, when set) into every from-scratch
  subprocess environment, so a test that moves `HOME` still reads the primed
  cache; a scratch checkout passes its own private source and cache the same
  way and never touches the real one.
- **Tested releases.** `tests/support.py` derives `NEWEST_RELEASE` (the
  highest pin) and `UPGRADE_FROM` (the one below it, or `None` with one pin)
  from the pins, and `support.release(v)` returns a verified snapshot through
  the cache, memoized per process. Only `NEWEST_RELEASE`'s frozen suites run,
  in four fixtures: `conformance`, `target`, `bootstrapped`, and `updated`
  (bootstrap `UPGRADE_FROM`, commit, `update` to the newest, commit). Every
  older pinned release is immutable and was tested once, when it was built;
  its `CI_SUITES` counts and portability exceptions stay as frozen records.
  A new pin moves the matrix to the new release with no renamed class.
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
  declared exclusive unit alone, one at a time. Phase B then runs the four
  matrix host classes (one per fixture) in merged mode. They assert over the frozen chunks'
  records, merged against a context built from the plan and never from the
  records. A merge that is incomplete, duplicated or foreign is refused.
  One implicit check does not carry over. In direct mode,
  `test_the_fixture_state_file_is_the_clean_template` and
  `test_the_target_carries_no_upstream_host_document` read the fixture
  after all seven suites ran in it, so they also caught a suite writing
  into its state file or host documents. In merged mode they read a fresh
  repository, and per-chunk residue is measured only for `bootstrapped` and
  `updated`.
  The plan's E-MRG-3 measured every suite's full residue at CP2 and found
  none unclassified, but nothing re-checks it on later runs.
- **Resources.** `tests/parallel/resources.json` declares the units that
  must not overlap anything and the guarded trees each one may write. Today
  it declares none (`resources: {}`, `exclusive: {}`); its `orphan_sources`
  are described below.
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
`$RUNNER_TEMP`. In every job that runs tests, and in the `package` job, the
step that runs them sets `WORKFLOW_MANAGER_RELEASE_CACHE` to
`${{ runner.temp }}/workflow-manager-releases` (a step-level `env`: GitHub has
no `runner` context in a job-level one, and rejects the whole workflow for
it), and the job restores that directory with `actions/cache`, keyed on the hash of
`src/workflow_manager/published_releases.json`, before priming; a normal run
downloads nothing. The dispatch input
`shards` overrides the count, so `shards=1` is the single-shard reference,
which the policy below restricts. The managed `workflow-conformance.yml` is
a separate, installed file, and it is not a required check: `workflow-manager
update` owns it and may rename its job.

- **One selection.** Every event plans the full selection; the `plan` job's
  only output is the shard list.
- **One required test check.** `aggregate` keeps its name whatever the shard
  count. It needs `plan`, every `shard` and the
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
  branch. A red nightly shows on the README's badge and in the Actions tab;
  nothing opens an issue.
- **Release.** `.github/workflows/release.yml` publishes the Manager package
  from `main` after `main`'s full run is green; see `docs/RELEASING.md`.

**Measured before M2 (the sharding milestone's CP7, and at its post-review
head `2b4c0fd`, 2026-09-27),** when the full selection re-ran the frozen
suites of all five releases (about 25,700 tests). 16 CPUs locally,
`ubuntu-latest` with Python 3.12 in CI. After M2's removal the full
selection is 1,409 units and 8,737 tests, 259 s locally at 8 workers (M2's
CP6 gate); the table below is kept as the sharding milestone's record.

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
pipeline at its configured shard count in CI. Forcing one worker or one
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
  between the two `head` commits. That means `src/` (the pins included,
  which fix the releases tested), `tools/`, `scripts/`, the test modules and
  their data (`tests/portability_exceptions.json`), and the
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
`src/` and `tools/`. File modes are never
touched. This makes an undeclared test that creates, deletes or renames
something there fail by name. It also makes those trees read-only to you
until the run ends. Saving a new file there fails with `EACCES`, and so
does an editor's atomic-rename save, or a `git checkout`/`switch`/`stash`/
`pull` that touches them. A branch switch can be left half-applied. The
run restores the original modes when it ends, including on `SIGINT` and
`SIGTERM`. After a `SIGKILL`, the next run restores them first. Or run
`python3 tests/run_all.py --restore-barrier`, which refuses while any
process of the killed run is still alive.

The release cache lives outside the checkout, is shared by every checkout on
the machine and must stay writable for priming, so the barrier does not cover
it. Its integrity does not rest on the barrier: no test writes the shared
cache (the cache tests each use a temporary one), every hit re-verifies
against the pins, and every use goes through a verified snapshot. The worst
case of a mutated entry is a discarded entry and a refetch, or offline a loud
`ReleaseUnavailableError`, never a run on wrong bytes.

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
  inherited value differs (keys compare case-insensitively) or an include
  in the series comes after it. A malformed
  series, or a `GIT_CONFIG_PARAMETERS` that sets one of the keys, includes
  a file (`include.path`, `includeIf.<condition>.path`) or cannot be
  parsed, is refused as `GitConfigEnvError` (exit `2`), because
  `GIT_CONFIG_PARAMETERS` outranks the series. An include in the series
  itself is kept. Git expands it where it stands, so all four pairs are
  appended after the last one and win. The executor also builds
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
  tolerated nothing in a run is listed as unused. Today there are nine
  declarations: five host classes that kill chunk groups on purpose, and
  the frozen `TestStateLock` in the newest release's four fixtures, whose
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
| `Release` | A release tree, verifiable from its own manifest. Every `Release` a command installs from is a private, pin-verified snapshot. |
| `Release.installable(profile)` | The install set — payload plus release-owned templates. `bootstrap`, `update` and `drift()` all read it, so they cannot disagree about what the release owns. A new profile is one entry in `_PROFILE_CATEGORIES`. |
| `load_pins()` / `ReleaseCache.resolve()` / `local_release()` | Which releases are published, and a verified `Release` for one of them, from the cache or from a local directory. Adding a release is adding a pin. |
| `build_package()` / `extract_package()` | The package format, for any producer of releases; `workflow-manager package build`/`verify` expose it to the `workflow` repository's own release job. |
| `Installation` | What a repository has, as data. A Controller asking "which of my repositories are on which release" reads these files; it does not need to inspect trees. |
| `drift()` / `verify()` | A structured answer (`Drift(path, kind, detail)`), not a printed report, covering release-owned, generated and merged content alike. Fleet-wide health is a loop over targets. |
| `Status.verified` | Whether a report was actually measured against a release. A fleet view that treats "unverified" as "healthy" is the bug this field exists to prevent. |
| `update()` | Returns the new record and the list of changes. Safe by default: it refuses rather than discarding local edits, so an orchestrator does not need its own guard. |
| `build_target_repo()` / `build_conformance_repo()` | Disposable repositories from a release. Any new operation can be proven against one before it touches a real consumer. |

Deliberately absent: orchestration across repositories, scheduling, rollback
history beyond `update()`'s symmetry, and any notion of a "real" consumer.
Those are Controller concerns, and building them here would fix decisions that
should stay open.

### What a new Workflow release needs

A Workflow release is built, tested and published in the `workflow`
repository (`RodrigoFAbreu/workflow`), as three release assets per version
(see "Packages, pins, source and cache" above). The Manager learns of it
through one `feat:` pull request here:

1. Add its pin to `src/workflow_manager/published_releases.json`: the archive
   name, the archive's sha256 and its `manifest.json`'s sha256, taken from the
   published assets and checked with `sha256sum -c SHA256SUMS`.
2. Add its frozen suite counts to `tests/support.py`'s `CI_SUITES` and its
   (possibly empty) entry to `tests/portability_exceptions.json`'s
   `by_version`; `TestPinnedVersionsCarryTheirRecords` fails until both
   exist.
3. `python3 tests/run_all.py`. Priming fetches the new package once; the
   matrix moves to it (`NEWEST_RELEASE`) and the `updated` fixture updates to
   it from the previous release (`UPGRADE_FROM`). The conformance fixture must
   be green, and the clean target's failure set must equal the documented
   exceptions.

Nothing else. `bootstrap` and `update` already mean the newest pinned release,
and `status` and `verify` already resolve a target's own version, so a new
release changes no code and no command line. `docs/RELEASING.md` has the
operator steps.

`update()` already handles files added, changed, and dropped between releases;
`tests/test_bootstrap.py::TestReleaseToReleaseUpdate` proves that against a
synthesized second release, and `TestReleaseResolution` proves the
resolution rules against a set of packaged releases.

## Authored releases (history)

`2.3.1` was extracted from a frozen upstream tag; `2.4.0`, `2.5.0`, `2.5.1`
and `2.6.0` were authored in this repository, each as a base release plus a
hand-written overlay composed by `tools/build_release.py`, with every
replaced file recording an `overlay_delta` (the base file's sha256 plus the
sha256 of a unified diff against it) and `manifest.json` recording a
`provenance` of `{"origin": "authored", "base_release", "overlay_commit"}`
next to the base's `upstream` triple. Those manifests are part of the
published packages and are unchanged, and `Installation` still copies
`provenance` into a target's record.

The composition tooling (`migration/`, `tools/migrate.py`,
`tools/build_release.py`) and the `distribution/` trees it produced were
retired by M2 (`OD-M2-4`). They remain in Git history at `ec38979`, the last
commit that carries them, and `docs/MIGRATION.md` records each release's
evidence. From `2.7` on, a release is authored in the `workflow` repository,
whose tree is the release: there is no overlay mechanism.

The downgrade posture an authored release that widens closed state vocabulary
creates is unchanged; `CLAUDE.md`'s "Adding a Workflow release" states it as an
operator instruction.
