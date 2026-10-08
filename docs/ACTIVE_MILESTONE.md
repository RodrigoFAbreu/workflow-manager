# Active Milestone

## Milestone

`workflow-manager-update-ergonomics` (`governing_workflow_version: "2.2"`,
`process`, plan revision 6 approved by policy, base `bb54c76`, branch
`milestone/workflow-manager-update-ergonomics`): `workflow-manager doctor`
and `workflow-manager update --dry-run`, which read a repository and report
what an update would do and which Workflow guarantees it would cross,
without writing the repository. Full plan:
`docs/ai-workflow/WORKFLOW_MANAGER_UPDATE_ERGONOMICS_PLAN.md`.

## Current checkpoint

**CP1, CP2 and CP3 complete; CP4 is next.** CP1-CP5 are in the registry
(`docs/ai-workflow/registry/workflow-manager-update-ergonomics-registry.json`).

## Current blockers

None.

## Active plan

`docs/ai-workflow/WORKFLOW_MANAGER_UPDATE_ERGONOMICS_PLAN.md` (revision 6).

## Next action

`/milestone-implement workflow-manager-update-ergonomics` for CP4.

## Update ergonomics -- checkpoint log

### CP1 -- `plan_update` / `apply_update` (complete)

- `install.update` is now `plan_update` (decide, write nothing) followed by
  `apply_update` (write). `UpdatePlan` carries `changes`, `removals`,
  `writes` (`PlannedWrite`, relative path, `mode_only` for a repaired
  executable bit), `left_alone` (`LeftAlone(path, reason)`) and the record it
  would write. Beyond the plan's sketch it also carries `overwrites`: the
  locally modified release files a forced update discards, which the dry
  run's `would overwrite` annotations (CP3) need and nothing else records.
- The merges got a pure half, `_plan_merges`; `bootstrap` writes what it
  returns, so bootstrap and update share one merge implementation
  (`_apply_merges` is gone, it had no other caller).
- `apply_update(plan, release)` uses `release` only to refuse a plan made
  for another release. It writes through the module-global `_write`, once per
  file, in the old order (removals, release files, state templates, merges,
  record last), so the interrupt-at-every-write test counts what it did.
- Behaviour change, as the plan allows: every artifact is read and verified
  at plan time, so a corrupt cached artifact refuses before any write.
- Tests: `tests/test_update_plan.py` (new) pins planning as write-free,
  plan-then-apply equal to `update` (tree, record, change lines) for a clean
  update, same-release no-op, deleted state, changed merged files, a lost
  executable bit, a profile change and a forced update over a local edit,
  and identical refusals (local edit, collision, directory in the way under
  `--force`, unmanaged target, unknown profile).
- Verified: `python3 tests/run_all.py --select test_update_plan.py` (exit 0),
  and `--select test_bootstrap.py --select test_update_path.py` (453/453
  units, 2859 tests, exit 0). The full gate is CP5's.

### CP2 -- `compatibility.py` (complete)

- New `src/workflow_manager/compatibility.py`, no CLI and no Workflow
  imports. `run_git` is the one hermetic Git entry point (flags and
  environment of plan 3.2; returns `GitResult(returncode, stdout)`, `None`
  for a timeout or `OSError`). `read_repository(target)` reads the record,
  config, gate-policy presence, state, each item's artifacts declarations and
  registry ids, `plan-inputs/` directories, worktree count, amendment
  witnesses in the common Git dir (relative `rev-parse` paths resolved against
  the target), the dirty flag, and the two trailer searches (one anchored
  `--grep` each, `HEAD` only). Partial clones are detected from config first
  (exit 1 = key absent); a partial clone or a failed detection skips
  `status`/`log` and records a problem. Every unreadable part is a `problems`
  entry, never an exception.
- Two classifier copies (`classify_plan_stage`, no protected prefixes;
  `classify_implementation_stage`), the phase classes, `ALWAYS_HUMAN_GATES`
  and the ambient exclusion, each compared by test with the 2.9.0 package.
- The three tables: `DOWNGRADE_BOUNDARIES` (signals as detectors over the
  facts, 2.7.0's undetectable orchestration hazard stated),
  `NEW_WORK_ONLY`, `GATE_DEFAULT_CHANGES`; each has an entry per pinned
  version, enforced by test.
- `build_report` -> `Report` of `Finding`s (every id of plan section 4),
  `RecoveryStep`s and `Command`s (family `manager`/`git`/`slash`, argv,
  `render_command` = `shlex.join`). The restore line is withheld unless the
  tree is known clean. `render_report` prints the fixed headings; the three
  version labels never share a line. `doctor_exit_code` is 1 for any
  `blocked`/`warning`.
- Not here (CP3): `plan_destinations`, the CLI, `read_only`/`snapshot_parent`
  threading, exit-2 mapping, parser/Git/slash validation of printed commands.
- Tests: `tests/test_compatibility.py` (99 tests, synthetic state files and
  throwaway repositories). Verified: `python3 tests/run_all.py --select
  test_compatibility.py` (16/16 units, exit 0); `--select test_update_plan.py
  --select test_docs.py --select test_internal_references.py --select
  test_release_workflows.py --select test_parallel_runner.py` (exit 0). The
  full gate is CP5's.

### CP3 -- the CLI and read-only enforcement (complete)

- `workflow-manager doctor <repo>` and `workflow-manager update <repo>
  --dry-run [--force] [--profile P]` (`cli.py`). The global `--release-version`
  names the target for both. `doctor` exits 0 with no blocked/warning finding, 1
  with one (an incomplete inspection is a warning), 2 when it could not check
  (not managed, corrupt record, target release unresolvable: it handles that
  itself so `main()`'s exit 1 stays unambiguous). An unresolvable *installed*
  release still produces the report, with `not-verified`. `--dry-run` prints
  `would ...` lines (one per `plan.changes` entry, `--force` annotated with the
  edit it discards), `left alone:`, then the report; a refusal prints the
  report, then re-raises so stderr and the exit (2, with the `--force` hint)
  are the real update's.
- `compatibility.plan_destinations(options, environ, target, versions)`: pure
  path arithmetic, creates and probes nothing. Protected set = realpath of the
  work tree and of `--absolute-git-dir`/`--git-common-dir` (relative output
  resolved against the target; a target with a `.git` entry whose
  directories cannot be resolved is refused). Refuses a cache root, a lock
  leaf or version directory that resolves into it, a symlink inside an
  existing version directory, and a `TMPDIR`/`TEMP`/`TMP` inside it; the
  snapshot parent is the first of `tempfile`'s candidates that is an
  accessible directory outside it. A target under `/tmp` is accepted (P3).
- `source.py`: `_copy_snapshot(tree, dir=None)`, `ReleaseCache.resolve(version,
  *, snapshot_parent=None, read_only=False)` (a `read_only` lock leaf is opened
  with `O_NOFOLLOW`, so a link fails with `ELOOP`) and `local_release(...,
  snapshot_parent=None)`; defaults leave `update`/`verify`/`bootstrap`
  unchanged. `cli._resolve(args, version, destinations)` threads both down.
- Tests: `tests/test_read_only.py` (25) with `tests/audit_hook.py` (the
  write-observing audit hook, self-tested with relative and `dir_fd` paths and
  an unresolvable event): destinations, resolver, byte/mode snapshots of the work
  tree and both Git directories (linked worktree included), a read-only copy,
  `core.fsmonitor` never run, a partial clone (no `status`/`log`, no fetch
  helper, with and without `GIT_NO_LAZY_FETCH`), and a `GIT_TRACE2_EVENT`
  trace of the Git commands run. `tests/test_doctor_cli.py` (24): exit codes,
  headings, dry-run/real-update parity (lines, drift and collision refusals,
  unpinned release), and every printed command validated by family (Manager
  through `build_parser()`, Git run in a repository whose path has spaces and
  metacharacters, slash against the release's command file), the restore line
  withheld when dirty or unknown, and the undo command run after a real update.
- Verified: `python3 tests/run_all.py --select test_doctor_cli.py --select
  test_read_only.py` (7/7 units, 49 tests, exit 0); `--select test_update_plan.py
  --select test_compatibility.py --select test_release_source.py --select
  test_bootstrap.py --select test_docs.py --select test_internal_references.py
  --select test_release_workflows.py --select test_parallel_runner.py --select
  test_orphan_processes.py` (145/145 units, 714 tests, exit 0). The full gate is
  CP5's.

## Checkpoint log

### CP1 -- package format (complete)

- **`D-Package-Format`** (`src/workflow_manager/package.py`):
  `build_package(release_dir, out_dir)` writes the three assets
  (`workflow-V.tar.gz`, `workflow-V.manifest.json`, `SHA256SUMS`) and
  returns them as a `Package`. It refuses a tree that fails
  `Release.verify()`, a manifest location that is unsafe or repeated, and a
  linked file or one that lies outside the release; each file's bytes are
  re-checked against the manifest as they are packed. Members come from
  the manifest (`manifest.json`, every location, every parent directory),
  sorted, `mtime 0`, `0:0`, no owner names, `0755`/`0644`; the tar is
  `PAX_FORMAT`, which writes a plain USTAR header for every member that
  fits one and a PAX header only for a path that does not; the gzip header
  has `mtime 0` and no name.
- `extract_package(archive, dest, version=None)` accepts only regular files
  and directories under the single top-level `workflow-V/` (`V` the carried
  manifest's version, and the requested one when given), with relative
  paths and no `..`; it refuses links, devices, FIFOs, duplicates, absolute
  paths, extra files or directories, missing files, a wrong digest or size,
  any file mode other than the manifest's `0644`/`0755`, a directory mode
  other than `0755`, a malformed manifest, and more than
  `MAX_UNPACKED_BYTES` (256 MiB) unpacked. It stages the tree in a
  temporary sibling of `dest`, re-runs `Release.verify()` there, and
  publishes by `rename`; every failure raises `ReleaseIntegrityError` and
  leaves nothing behind. It never calls `tarfile`'s own extraction.
- **Shared SHA256SUMS writer:** `package.sha256sums_text(files)`.
  `tools/release/package.py`'s `sha256sums_text(directory)` keeps its
  signature and its empty-directory refusal and delegates the format to it
  (it now puts `src/` on `sys.path`).
- **Tests:** `tests/test_release_source.py` (new; CP2 extends it with
  5.2-5.4): `TestDeterministicBuild`, `TestRoundTrip`, `TestSafeExtraction`,
  `TestSha256Sums` (36 tests, synthetic releases only).
  `tools/ci/pr_profile_paths.json` gains the module's own `full` rule
  (plan 13).
- **Verified:** `python3 tests/run_all.py --select test_release_source.py
  --select test_manager_version.py --select
  test_stopgap_profile.py::TestPathRulesAreComplete` -- 14/14 units, 84
  tests, exit 0. A scratch smoke check (not a test, not recorded as
  evidence; CP4 does it properly) built each of the five releases from
  `git archive ec38979 distribution/workflow` twice and extracted it: all
  five archives were byte-identical across builds and extracted to their
  source trees exactly.

### CP2 -- source, pins and cache (complete)

- **`D-Release-Source`** (`src/workflow_manager/source.py`):
  `ReleaseSource.select(option, environ)` takes `--release-source`, else
  `WORKFLOW_MANAGER_RELEASE_SOURCE`, else the `RodrigoFAbreu/workflow`
  release-download template. A value with `://` is a URL template, which
  must carry `{version}` and be `https://`, `file://`, or `http://` to a
  loopback host; anything else is a local directory of `<version>/`
  folders. Fetching uses `urllib.request` with a 60-second timeout, reads
  `SHA256SUMS` first, then the archive and the manifest asset, and caps
  each asset at 64 MiB. Redirects: at most five, to any host, never from
  `https` to anything else, and every hop must pass the scheme rule. Any
  failure to obtain an asset is `ReleaseUnavailableError`.
- **`D-Pins`:** `src/workflow_manager/published_releases.json` (empty
  `releases` until CP4) ships as package data (`pyproject.toml`'s new
  `[tool.setuptools.package-data]`). `load_pins` refuses a malformed pin
  file (schema, repository, archive name, digest shape) with
  `ReleaseIntegrityError`. A download is accepted only when the archive
  hashes to the pin **and** to its `SHA256SUMS` line, and the manifest
  asset hashes to `manifest_sha256` and to its line.
- **`D-Release-Cache`:** `cache_root(option, environ)` takes
  `--release-cache`, `WORKFLOW_MANAGER_RELEASE_CACHE`, `$XDG_CACHE_HOME`,
  then `~/.cache`. `ReleaseCache.ensure(version)` (5.4 steps 1-4, for
  priming) and `resolve(version)` (steps 1-6) work under an `fcntl` lock
  on `<cache>/<version>.lock`. A hit needs `complete` naming the pin, the
  cached archive hashing to it, `tree/manifest.json` hashing to
  `manifest_sha256`, the manifest naming the requested version and
  `Release.verify()`; anything else is logged (`discarding cache entry
  ...`), removed and refetched into a temporary sibling that is renamed
  into place, with `complete` written last. `resolve` then copies the
  manifest-enumerated files into a private `0700` directory and checks the
  copy against the pin; a failed copy discards the entry and refetches
  once (`ReleaseUnavailableError` if that cannot be done,
  `ReleaseIntegrityError` if the new copy fails too). It returns a
  `SnapshotRelease` (a `Release` subclass carrying the record's `source`),
  removed by `close()`/`with` and by an `atexit` backstop. An unpinned
  version is `ReleaseNotPublishedError`; an unusable cache directory is
  `ReleaseUnavailableError`. Both new errors subclass `InstallError`, so
  CP3's CLI reports them through its existing handling.
- **`local_release(dir, requested_version, pins)`** (5.5): refuses a
  directory whose manifest version differs from the requested one; a
  pinned version must match `manifest_sha256` (the error names the
  version, the directory and both digests) and is recorded as the package
  (`source.kind: "package"`, with a stderr note); an unpinned one is
  checked by its own manifest and recorded as `{"kind": "local"}`. Either
  way it is used through a verified snapshot, without a lock.
- **Tests** (`tests/test_release_source.py`, +58): `TestPins`,
  `TestSourceSelection`, `TestFetch` (local `http.server` on 127.0.0.1,
  `file://`, local directory; redirects, the five-hop limit, `https`->`http`
  and off-loopback `http` redirects, the size cap), `TestPinChecks`
  (republished archive with agreeing sums, sums or manifest asset against
  the pin, another version in the archive, unpinned), `TestCache` (entry
  layout, `ensure` takes no snapshot, offline hit and miss, seven kinds of
  broken entry each discarded and refetched, or `ReleaseUnavailableError`
  offline), `TestSnapshots` (private `0700` copy, the resolve/install
  boundary through `install.bootstrap`, the lock-ignoring writer seam
  online, offline and twice, `close`/`with`, the `atexit` backstop in a
  child process), `TestLocking` (four concurrent resolves fetch once;
  `resolve` waits for a held lock) and `TestLocalRelease`. Each test sets
  `WORKFLOW_MANAGER_RELEASE_CACHE` to its own temporary cache and asserts
  `cache_root()` resolves to it. The `--manager-root` alias's own
  local-directory test is CP3's, where the alias is wired.
- **Verified:** `python3 tests/run_all.py --select test_release_source.py`
  -- 12/12 units, 94 tests, exit 0; `--select test_manager_version.py
  --select test_stopgap_profile.py` -- 107 tests, exit 0; `--select
  test_orphan_processes.py --select test_release_versioning.py` -- 118
  tests, exit 0.

### CP3 -- CLI and install record (complete)

- **`D-CLI`** (`src/workflow_manager/cli.py`): `bootstrap`, `update`,
  `status` and `verify` resolve a release in one function, `_resolve`:
  `--release-dir` (through `local_release`), then the `--manager-root`
  alias when its checkout holds the version, then the pins through the
  cache (`ReleaseCache.resolve`), and last the **checkout fallback** --
  an unpinned version this Manager's own checkout holds under
  `distribution/workflow/<v>/`, used as a local release with a stderr note
  (CP3 to CP6 only). The default version is the newest pinned one, else the
  newest local candidate. Every release is used as a snapshot inside a
  `with` block. New global options: `--release-source`, `--release-cache`,
  `--release-dir`. `--manager-root` defaults to nothing, always prints a
  deprecation notice, and falls through to the pins when its checkout lacks
  the version. `missing_distribution_message` and `_require_distribution`
  are gone; `cli.py` no longer imports `find_release`.
- **Exit codes:** `ReleaseNotPublishedError`, `ReleaseUnavailableError` and
  `ReleaseIntegrityError` exit **1** with `error: ...` (plan 5.5, "All of
  them exit 1"). This changes `ReleaseIntegrityError`'s CLI exit from 2 to
  1; every other refusal still exits 2.
- `status` of a managed target prints a `source:` line (`package <archive>
  from <repository> (sha256 ...)`, `(local, unpublished)`, or `not
  recorded`); when the release cannot be resolved it first prints the
  recorded version, profile, source and install times, then the error,
  which names `--release-dir`.
- `releases` lists every pinned version (`<v>  <archive>  sha256 <digest>
  [cached|not cached]`, no network), then each unpinned local candidate as
  `<v>  (checkout, unpublished)  ...` (`(--manager-root, unpublished)` with
  the alias). It exits 0 with nothing pinned, noting that on stderr.
- `package build <release-dir> --out <dir>` and `package verify <archive>
  [--sha256 H]` wrap `build_package`/`extract_package`.
- **Install record** (`installation.py`, `install.py`): an optional
  `source` (the `SnapshotRelease.source` the resolver attached), written
  after `provenance` and omitted when absent, so a pre-M2 record round-trips
  byte for byte; a non-object `source` is a corrupt record.
  `SCHEMA_VERSION` stays 1.
- **Tests:** `tests/support.py` gains `cli_env(**extra)` (7.1), now used by
  `test_bootstrap_e2e.py`, `test_amendment_update_path.py` and the
  empty-`HOME` lifecycle test. `test_bootstrap.py`: `TestReleaseResolution`
  rebuilt on two synthetic packaged, pinned releases served from a local
  directory plus an unpinned checkout-fallback release (newest pinned
  default, INV-4 install bytes, cache hit without a source, discard and
  refetch, unavailable exit 1, update, reports against the recorded
  release, unpublished record needing `--release-dir`, `--release-dir`
  local/pinned/altered/wrong version, fallback, no-pin default,
  `releases`); new `TestManagerRootAlias` (unpinned positive branch with
  the notice, consistently altered pinned copy refused with nothing
  written, fall-through, `releases`), `TestSourceRecord` and
  `TestDiscoveryApi` (the `available_versions`/`find_release` tests, kept
  until CP6). `test_manager_version.py`: `MissingDistributionHintTest` now
  models a wheel install (no fallback, empty pins) and asserts the
  unpublished and unavailable messages and exit 1. `test_release_source.py`:
  `TestPackageCommand`.
- **INV-3:** `python3 -m workflow_manager verify .` -> exit 0 through the
  fallback ("release 2.6.0 is not published; using the checkout's
  unpublished copy"), and with `--release-dir distribution/workflow/2.6.0`
  -> exit 0; `status .` -> clean, `source: not recorded`.
- **Verified:** `python3 tests/run_all.py --select test_bootstrap.py
  --select test_manager_version.py --select test_bootstrap_e2e.py --select
  test_amendment_update_path.py --select test_squash_merge_compat.py
  --select test_release_source.py` -- 1352/1352 units, 8599 tests, exit 0
  (head `8e0042b` plus this checkpoint's first working tree); after the
  `package` tests and the diff review (import order, one digest read in
  `package verify`), the same selection -- 1353/1353 units, 8604 tests,
  exit 0 (`selection_digest f43674d9...`, `tests_digest d0151f3d...`).
  Targeted selections, not a gate.

### CP4 -- build and prove the five packages (complete)

- **`tools/workflow_packages.py build (--from DIR | --commit SHA) --out DIR
  [--pins FILE [--check]] [--prime]`** (plan 6): one package per release
  into `<out>/<v>/` (a `--release-source` directory layout); each built
  twice and compared byte for byte, then extracted and compared with its
  source tree (file set, bytes, modes); `--commit` extracts `git archive
  <sha> distribution/workflow`, never the working tree; `--pins` writes the
  pin file canonically (or `--check`s it); `--prime` fills the default
  cache through `ReleaseCache.ensure`. Prints the evidence table.
- **Run:** `build --commit ec38979 --out /tmp/m2-cp4/assets --pins
  src/workflow_manager/published_releases.json --prime`. All five round
  trips identical; two full runs `diff -r` identical; `sha256sum -c
  --strict` OK in every package directory. The evidence table is in
  `docs/MIGRATION.md` ("Packaged releases -- the five packages"). The pins
  now publish `2.3.1`-`2.6.0`; `~/.cache/workflow-manager/releases` holds
  all five.
- **Manager packaging (5.6):** `tools/release/package.py` loses
  `--manager-root`; the expected `releases` list is the checkout's pins;
  the wheel must carry `workflow_manager/published_releases.json`; the smoke
  check always runs `releases` and `verify <checkout>` from the wheel with
  the caller's environment. `workflow-manager-verify.yml`'s `package` job
  and `release.yml`'s build step gain an `actions/cache@v4` restore of
  `${{ runner.temp }}/workflow-manager-releases` keyed on
  `hashFiles('src/workflow_manager/published_releases.json')` and
  `WORKFLOW_MANAGER_RELEASE_CACHE`; the notes line lists the pinned
  versions. Smoke (outside the suite): `package.py --version 0.0.0+ci`
  from a scratch venv with `WORKFLOW_MANAGER_RELEASE_SOURCE=/nonexistent`
  -> exit 0 (wheel, sdist, SHA256SUMS; `releases` and `verify` through the
  primed cache, offline).
- **Tests:** new `tests/test_package_round_trip.py` (deleted in CP6):
  `TestPackagesReproduceTheDistributionTree` (round trip against the
  `git archive ec38979` extraction with an independent file comparison,
  byte-identical rebuild, pins reproduce byte for byte),
  `TestCheckoutReleasesArePinned` (every committed release is pinned and
  its manifest hashes to the pin; the working tree's manifests too), and
  `TestWorkflowPackagesTool` (the tool on synthetic releases: pins
  write/check, prime, `__pycache__` debris fails the round trip, mode
  difference, refusals, usage errors). New `tests/test_published_packages.py`:
  `TestPinnedPackagesVerify` (permanent: each pin's cached assets and
  `SHA256SUMS`, re-extraction, verified snapshot). Edited:
  `test_parallel_runner.py` (package job command, cache step and env),
  `test_release_workflows.py` (cache step before the build, keyed on the
  pins, no `--manager-root`, notes from the pins; three new mutants),
  `test_manager_version.py` (`test_the_live_release_set` on the pins
  without `--manager-root`; expected list = pins; wheel must carry the
  pins; `--manager-root` now a usage error). Both new modules have `full`
  rules in `tools/ci/pr_profile_paths.json`.
- **INV-3:** `python3 -m workflow_manager verify .` with
  `WORKFLOW_MANAGER_RELEASE_SOURCE=/nonexistent` -> exit 0 through the
  primed cache, offline; `releases` lists all five `[cached]`.
- **CI note:** `TestPinnedPackagesVerify` and every CLI test that resolves
  a pinned version read the cache. CI's shard jobs have no primed cache
  until CP5 (runner priming) and CP6 (cache restore); the packaging jobs
  download on a miss, which needs the cutover's `K2`. No implementation
  gate depends on CI (plan 9, INV-5).
- **Verified (gate):** `python3 tests/run_all.py` -- full selection, local,
  8 workers, head `92ef881` plus this checkpoint's working tree, 4122/4122
  units, 25,828 tests, `selection_digest f66d59fe...`, `tests_digest
  be0b5900...`, verdict exit 0, wall 398 s (20 declared orphan-source
  chunks tolerated).

### CP5 -- the test suite on the release cache (complete)

- **Tested releases (7.1):** `tests/support.py` computes `PINNED_VERSIONS`,
  `NEWEST_RELEASE` (`2.6.0`) and `UPGRADE_FROM` (`2.5.1`; `None` with one
  pin) from the pin file at import, and `release(v)` resolves a pinned
  release through the cache as a verified snapshot, memoized per process;
  `next_version(v)` gives the synthetic next release. `CI_SUITES` and
  `tests/portability_exceptions.json` (moved from `migration/`, every
  entry unchanged) keep all five versions as frozen records.
- **Matrix:** `tests/parallel/matrix.py` names four unversioned classes, all
  on `NEWEST_RELEASE`: `TestConformanceFixture`, `TestBootstrappedTarget`,
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite` and the new
  `test_update_path.py::TestUpdatedRepositorySatisfiesTheFrozenSuite`
  (omitted with one pin). `frozen_runs.py` gains the `updated` fixture
  (`build_updated_repo`: bootstrap `UPGRADE_FROM`, commit, `update`,
  commit; `NoUpgradeSourceError` with one pin), post-run residue/drift for
  it, and reads every release and `release_digest(version)` through
  `support.release`. Frozen discovery loads suites from the snapshot.
  1,244 frozen units (4 x 311).
- **Priming:** new `tests/parallel/priming.py`. Every mode except
  `--restore-barrier` resolves every pinned version with
  `ReleaseCache.ensure` in a subprocess on the checkout's own `src/` and pins,
  then exports `WORKFLOW_MANAGER_RELEASE_CACHE` for discovery and every
  unit. A failure is `PrimingError`, exit 2, naming the cache and the source.
- **Module rework (7.2):** `test_conformance_suite.py` split: the matrix
  classes plus `TestAuthoredReleaseCiTemplateSuiteNames` (every pinned
  version except `2.3.1`, through `support.release`), the new
  `TestPinnedVersionsCarryTheirRecords` (pins = `CI_SUITES` keys = exception
  keys) and `TestPortabilityExceptions250RequiredEmptyEntry` stay; the tool
  classes moved to the new `tests/test_authored_release_tools.py` (CP6
  deletes it). `test_bootstrap.py` runs on `NEWEST_RELEASE`, with
  `NEXT_RELEASE` as the synthetic next release. `test_bootstrap_e2e.py`
  (mixin gains `FIXTURE`; live-state update on the newest pin; the default
  is the newest pin). `test_internal_references.py`,
  `test_disposable_repo_fixtures.py`, `test_squash_merge_compat.py` (no
  `--manager-root`), `test_orphan_processes.py` and
  `test_workflow_2_6_0_hardening_disposable_repo.py` (guard names
  `TestBootstrappedTarget`, reads the moved exceptions) read releases through
  `support.release`. `resources.json`'s `frozen:` orphan sources keep
  `2.6.0` plus the `updated` fixture; the five `host:` entries and
  `repo:distribution` are unchanged. `timings.json` gains an `updated` group
  overhead (twice `bootstrapped`'s, an estimate until the next refresh).
- **Scratch checkout (7.2.1):** the scratch's `0.0.1` is a real package
  (`publish_synthetic_release`, `build_package`) served from and cached in a
  sibling `<scratch>.releases/` directory, and it is the scratch's one pin.
  `scratch_release_env` overrides the source and cache for `run_cli`,
  `start_cli`, `run_reproduction`, `main_in_process`, `run_ci_step`,
  `release_tests.run_assert_full_plan` and in-process discovery. Worktrees
  and clones map back to their scratch by name. `builder_raises` now uses a
  package whose manifest has no `.gitignore` fragment. The exclusive lock
  moved to `repo:tools` over the scratch's `tools/scratch/lib/bin/`, and the
  integrity tests use that tree. The `:344` sub-path case is now
  `src/workflow_manager/`. `TestFrozenInventoryCountRefusal`'s layout is a
  one-pin package too. The stopgap test's three-release scratch publishes
  `0.0.9`/`0.0.10` packages.
- **New tests:** `test_update_path.py` (the matrix class, the real pins
  define an update path, and a CLI bootstrap of `UPGRADE_FROM` then `update`:
  record, `source`, newest bytes, `verify`).
  `TestScratchReleaseIsolation`: a scratch run primes and tests only
  `0.0.1`, and the real cache is unchanged; an unprimable pin is
  `PrimingError`; the lock is on `tools/`. `TestTestTreeHygiene` resolves
  `0.0.1` with `support.release` in the scratch's environment.
  `test_internal_references.py`: `TestNoTestResolvesAReleaseThroughTheLayout`
  (imports of `find_release`/`available_versions`/`release_root`, the
  layout string or path components, comments included; scans
  `tests/**/*.py` minus CP6's deletion list; stale exemptions fail) and
  `TestNoLiteralCliEnvironment`.
- **Deviations, recorded:** the layout scan has four exemptions, not six.
  `TestReleaseResolution` and `TestManagerRootAlias` reach the layout only
  through calls (`release_root(...)`), which the scan does not flag. Listing
  them would trip the stale-exemption check. The remaining four are the
  `workflow_manager.release` import (until CP6), the two `MIGRATION.md`
  regex classes and `LINT_MODULE`.
  Scratch runs take the source/cache override as extra keys over the
  caller's environment, not through `support.cli_env`: `cli_env` resets
  `PYTHONPATH`/`PATH`/`HOME` to the real checkout's. The stopgap test's
  `STOPGAP_IDENTIFIERS` now match the stopgap's qualified names
  (`inventory.NEWEST_RELEASE`, `NEWEST_RELEASE_KIND`, `newest_release(`,
  ...), because the plan makes `support.NEWEST_RELEASE` permanent.
  `test_release_workflows.py`'s notes check says `distribution/` rather
  than the layout string.
- **Verified (gate):** `python3 tests/run_all.py`: full selection, local,
  8 workers, head `ce03624` plus this checkpoint's working tree, 1467/1467
  units, 8,925 tests, `selection_digest bc62a9da...`, `tests_digest
  60425a69...`, verdict exit 0, wall 274 s (9 declared orphan-source chunks
  tolerated). `distribution/` is still present and now read only by the
  modules on CP6's deletion list.

### CP6 -- removal (complete)

- **Deleted whole:** `distribution/`, `migration/`, `tools/migrate.py`,
  `tools/build_release.py`, the stopgap's `tools/ci/` (`choose_profile.py`,
  `nightly_alarm.py`, `pr_profile_paths.json`, and the now-empty package's
  `__init__.py`), and the nine retired test modules on the plan's list.
  `tools/workflow_packages.py` stays: it builds from `git archive <commit>`,
  never from the working tree.
- **Stopgap:** every `STOPGAP(M2)` block under `tests/parallel/` (and the
  `--newest-release-only` flag with them); in
  `workflow-manager-verify.yml` the profile step, the `NEWEST` wiring, the
  `profile` output, `actions: read` and the `nightly-alarm` job (the nightly
  schedule stays). `TestAssertFullPlanRefusesTheStopgap` moved to
  `test_release_versioning.py`: with the flag gone it relabels a real full
  plan `newest-release` (re-digested, so it still loads) and requires
  `assert-full-plan` to refuse it, and requires the runner to reject the
  flag as an unrecognized argument.
- **Checkout fallback and discovery API:** `release.py`'s `release_root`,
  `available_versions` and `find_release` are gone, with `__init__.py`'s
  re-exports; its docstring now describes packages, pins and the cache.
  `cli.py` resolves `--release-dir`, then the `--manager-root` alias (now a
  plain path join, `_checkout_releases`), then the pins; an unpinned version
  without `--release-dir` is `ReleaseNotPublishedError` (new test
  `test_an_unpinned_version_without_release_dir_is_not_published`), and with
  no pin there is no default. `release.py`'s damaged-release message no
  longer names `tools/migrate.py`. `TestReleaseResolution` lost the
  fallback tests, `TestDiscoveryApi` is gone, and `TestManagerRootAlias`
  builds the alias layout itself.
- **Runner:** `GUARDED_TREES` is `("src/", "tools/")`; the barrier message
  follows. `resources.json` is `resources: {}`, `exclusive: {}` and the nine
  orphan sources (five `host:`, four `2.6.0` `TestStateLock`).
  `isolation.py`'s `TOOL_SCRIPTS`/`TOOL_ENTRY_POINTS` and their lint
  branches are gone; the lint fixture is rebased on `REPO_ROOT / "tools"`.
  `--fast` is removed with every reference (`FAST_ALIAS_SELECTION`,
  `FAST_NOTE`, `ALLOWED`, `_DEFAULTS`, the refusal, the selection line, the
  note).
- **Tests rewritten (7.2):** `test_parallel_runner.py`: `EXCLUSIVE_UNIT`
  gone; the committed declaration declares no resource or exclusive unit,
  every orphan source is a discovered unit and every `frozen:` one is
  `NEWEST_RELEASE`'s; the real plan drops its A0 check;
  `test_todays_tests_are_lint_clean`; the real-inventory tests target
  `test_bootstrap.py`; synthetic resources use `tools/`/`src/`;
  `TestDirectEntryPoints` (an ordinary run, and `--select`, exit 0; the
  alias exits 2 as an unrecognized argument; direct runs of
  `test_bootstrap.TestInstallationRecord`); the CI checker drops the upstream
  and `fetch-depth` rules and requires, per test job, the job-level cache
  env and one pin-keyed `actions/cache` restore before `run_all.py`, plus
  exactly four jobs and a `shards`-only plan output (new mutants for each).
  `test_release_workflows.py` drops the upstream fetch (and gains an
  "upstream again" mutant). `support.py` drops `CLASSIFICATION`,
  `FROZEN_COMMIT`, `FROZEN_TAG`, `UPSTREAM` and the upstream helpers; the
  scratch checkouts write no `migration/`. `test_manager_version.py`: the
  alias on this checkout, which has no `distribution/`, prints the
  deprecation notice and lists the pins. The hardening test's v2.3.1-002
  guard is retargeted to `test_update_path.py` (narrower: it proves the
  pinned update path runs in the full selection; recorded for CP7's
  `MIGRATION.md`), and its `:946` comment no longer names the retired
  module.
- **Retired-name assertion:** `test_internal_references.py`'s
  `TestNoTestNamesARetiredModule` scans every `tests/**/*.py` for the nine
  retired module names and the alias identifiers; its only exemptions are
  its own two lists and `TestDirectEntryPoints.test_the_retired_alias_is_refused`.
  The layout scan now covers every test file, and its two `until CP6`
  exemptions are gone; `TestManagerRootAlias` is exempt `while the alias
  exists`, because it now names the alias's layout itself.
- **CI (7.3):** `plan`, `shard` and `aggregate` set
  `WORKFLOW_MANAGER_RELEASE_CACHE` at job level and restore it before
  `run_all.py` (every runner mode primes); the repflow clone, its env and
  `fetch-depth: 0` are gone (no remaining test reads history).
  `release.yml` loses its upstream fetch step and env.
- **Observations, not changed here:** `release.yml`'s `assert-full-plan`
  rediscovers the inventory, which reads `NEWEST_RELEASE` through the cache,
  and runs before the job's cache restore (5.6's order), so on a release
  run it downloads that one package from the published source (after the
  cutover's `K2`). `tools/workflow_packages.py` has no test module after
  `test_package_round_trip.py`'s planned deletion. Documentation still
  describes the removed trees and the stopgap; that is CP7.
- **Verified (gate):** `python3 tests/run_all.py`: full selection, local,
  8 workers, head `9255a34` plus this checkpoint's working tree, 1409/1409
  units, 8,737 tests, `selection_digest a1ba7718...`, `tests_digest
  69d9fb85...`, `tree_digest 03bf4446...`, verdict exit 0, wall 259 s (9
  declared orphan-source chunks tolerated).

### CP7 -- documentation and evidence (complete)

- **`docs/ARCHITECTURE.md`:** the distribution/state boundary is now the
  release/state boundary, with a new "Packages, pins, source and cache"
  section (package format, pins as the trust root, source and cache
  precedence, the hit rule, snapshots, local directories, the record's
  `source`). The layout, "Release integrity" (every verification hop, and
  `ReleaseNotPublishedError`/`ReleaseUnavailableError`), "Which release a
  command means" (the newest pin) and "Boundaries" follow. The verification
  table is rewritten around the package, pin, cache and update-path tests
  (every cited class exists); the retired migration checks are named as
  history. "Verification execution" gains "Priming" and "Tested releases"
  bullets, phase B's four matrix classes, no exclusive unit, the CI cache
  (no full-history checkout), one selection, no nightly alarm, the barrier on
  `src/` and `tools/` only and why the cache is outside it, nine orphan
  declarations, and the post-M2 total beside the sharding milestone's
  measurements. "One reduced selection is a gate, in one place" and
  "Stopgap test profile" are removed, with the `--fast` mention. The
  extension-point table swaps `available_versions()`/`find_release()` for
  `load_pins()`/`ReleaseCache.resolve()`/`local_release()` and adds
  `build_package()`/`extract_package()`. "What a second upstream release
  needs" becomes "What a new Workflow release needs" (a pin pull request),
  and "Authored releases" becomes a short history pointing at `ec38979`.
- **`docs/MIGRATION.md`:** a header note that the record is historical and
  that every path under the removed trees is read at `ec38979`; the CP4
  section in the past tense, with the `--check` rebuild command (run: exit
  0, all five "identical"); and the M2 record "M2 -- the trees leave this
  repository": `ec38979` as the last commit carrying `distribution/`, what
  CP6 deleted, "old releases are tested once" (`OD-M2-5`), and
  v2.3.1-002's repository-level guard retargeted to `test_update_path.py`,
  stated as narrower (it proves the pinned update path runs in the full
  selection and no longer covers `2.3.1`→`2.4.0`), with the base/CP5/CP6
  gate totals.
- **`docs/RELEASING.md`:** the intro names the `workflow` repository; the
  release job's smoke check (pins in the wheel, `releases`, `verify` through
  the cache); "Installing a release, without a checkout" (the source, cache,
  offline, air-gapped, `--release-dir` and the `--manager-root` alias);
  "Workflow packages: adding a pin" (download, `sha256sum -c`, `package
  verify`, the pin, `CI_SUITES` and exceptions, the gate, a `feat:` title,
  pins never edited); the nightly without an issue; and "Cutover: M2" with
  K1-K5 as commands. K2's seed loop and its per-tag check were dry-run in a
  temporary repository (no push): five commits, each tag's tree equal to its
  release at `ec38979` plus `README.md`. The trunk-model cutover is kept as
  history, noting that its `newest-release` probe no longer applies.
- **`README.md`:** the intro, layout, install (wheel, no checkout), use
  (`workflow-manager`), integrity and cache paragraphs, a "Workflow
  releases" section in place of "Re-deriving the distribution", the tests
  paragraph (one selection, priming, barrier on `src/` and `tools/`, no
  `--fast`, no stopgap) and the reading order. The Status table is unchanged
  (pinned by `test_internal_references.py`).
- **`CLAUDE.md`, below the managed marker only:** what the repository is;
  the hard rules (release and pin immutability replaces "generated, not
  edited"; defects stay write-ups); "Before changing anything" (one selection
  everywhere, priming, no `--fast`, barrier on `src/` and `tools/`, the
  `migrate.py --check` paragraph gone); "Where things are"; one "Adding a
  Workflow release" section (a pin pull request) in place of the upstream and
  authored procedures; the downgrade posture kept whole, its two
  `distribution/…` paths now the published packages' `payload/scripts/`.
  The managed part is byte-identical, and `workflow-manager verify .`
  reports `installation matches workflow 2.6.0`.
- **Left as they are:** `docs/ROADMAP.md` (not edited during a milestone),
  `docs/defects/` and the plan documents (records), and the code comments
  that name `distribution/workflow` on purpose (the alias in `cli.py`,
  `tools/workflow_packages.py --commit`).
- **Observation, not changed:** the real release cache holds an empty
  `0.0.1.lock` (a scratch-only version) dated 13:36 today, before CP5's
  commit; `TestScratchReleaseIsolation` checks that the listing is unchanged
  by a scratch run, so it is a leftover from CP5's development, not a
  recurring leak.
- **Verified (targeted):** `python3 tests/run_all.py --select
  test_internal_references.py --select
  test_parallel_runner.py::TestSerialEvidencePolicyIsDocumented --select
  test_manager_version.py --select test_release_workflows.py`: 26/26 units,
  105 tests, exit 0. The full gate runs at self-review (step 3).

### Self-review of the milestone diff and the full gate (`SELF_REVIEWING_IMPLEMENTATION`)

- `enter_self_reviewing_implementation` was a no-op. CP7's
  `complete_checkpoint` had already written the phase.
- The whole `ec38979..9247089` diff was reviewed:
  - `package.py`: deterministic members and headers, `_read_checked`'s
    link/escape refusal, `extract_package`'s member rules (single top,
    duplicates, types, modes, size cap, manifest-exact file and directory
    sets, digests), staging and `rename`;
  - `source.py`: pin-file shape, the scheme and redirect rules, the capped
    fetch, the double pin/`SHA256SUMS` check, the hit rule, `_discard`,
    `_fetch`'s staging, `resolve`'s snapshot-under-lock and single refetch,
    and `local_release`'s pinned/unpinned branches;
  - `cli.py`, `install.py`, `installation.py`: `_resolve`'s precedence,
    the `with` scopes around every snapshot, exit 1 for the three release
    errors, `status` with an unresolvable release, and the additive
    `source`;
  - `tools/workflow_packages.py`, `tools/release/package.py`,
    `tests/parallel/priming.py`, both workflows, and the test and doc
    changes.
- No finding was blocking or important, and nothing was changed. Two minor
  cases were checked and left as they are:
  - `releases` with the deprecated `--manager-root` pointing at a checkout
    whose manifest lacks `upstream.tag` raises a traceback (a `KeyError`
    the CLI does not map). It is reachable only through the deprecated
    alias and a malformed checkout;
  - an `OSError` from `shutil.rmtree` in `ReleaseCache._discard` (a cache
    entry the user cannot delete) escapes unwrapped rather than as
    `ReleaseUnavailableError`. The command still fails, only without the
    named error.
- INV checks: `git diff --stat ec38979 HEAD -- scripts .claude/commands
  .github/workflows/workflow-conformance.yml
  docs/ai-workflow/WORKFLOW_CONFIG.json` is empty; `CLAUDE.md` up to
  `<!-- workflow-manager:end -->` is byte-identical to the base;
  `PYTHONPATH=src python3 -m workflow_manager verify .` reports
  `installation matches workflow 2.6.0` (through the primed cache).
- **The full gate**, `python3 tests/run_all.py` at `9247089`, 2026-09-30
  (263.2 s wall, 8 workers):
  - `evidence: full selection, local, 8 worker(s), head 9247089e3a9e32829bc31c45a03a6a1deed85866,
    1409/1409 units, 8737 tests, selection_digest
    a1ba771858aa45abbadb14526fab4fcd48a32ba0cb4d0229669727ac182f793c,
    tests_digest 69d9fb85ff68b701113c9d664726fcd1e5f217365a926a84488ecec5c6297a34,
    tree_digest 11e4c4cb5ebfb964dcad8debd6fbb87c362d8e6895705a64e44e07887d42a9ec`,
    `verdict: exit 0`;
  - `orphan check: on`. Orphans were tolerated only in the nine declared
    `orphan_sources` chunks, none undeclared and none a Git process;
  - the selection and tests digests equal CP6's gate: CP7 changed only
    documentation.

## Functional review checklist

You are testing the Manager as an operator uses it after M2: releases come
from verified packages in a cache, never from a checkout's `distribution/`.
- **Round 2** (implementation revision 4). Round 1 (revision 2) passed flows
  1-8 and K1-K3. It found F1 in K4, which was fixed in `3e90d7b`, with its
  regression scanner hardened in `6bbd8ec`. Revisions 3 and 4 changed only
  `.github/workflows/workflow-manager-verify.yml`, two test modules and one
  `docs/ARCHITECTURE.md` paragraph, with no Manager code. Re-test K4 (the CI
  run) and flow 8's targeted run. Flows 1-7 exercise unchanged code (all
  passed in round 1) and are optional.
- **Technical approval:** commit `2216d5a`, implementation revision 4.
- **Where findings go:**
  `.ai-review/workflow-manager-packaged-distribution/feedback/FUNCTIONAL_REVIEW.md`.
- **Automated verification:** already current. The full gate passed on the
  final code (recorded at `4f42956` with the fix's tree: 1410/1410 units,
  8,746 tests, verdict 0). Only state commits have landed since.

**Setup.**
- Linux, Python 3.12 or later, Git, and an authenticated `gh` (cutover
  only).
- Run every flow offline against a PRIVATE copy of the release cache, so
  that nothing touches your real cache, with a release source that cannot
  be reached (a closed loopback port), so any unexpected download fails
  loudly:

```bash
export M=~/Workspace/workflow-manager T=$(mktemp -d)
cp -a ~/.cache/workflow-manager/releases "$T/cache"
export WORKFLOW_MANAGER_RELEASE_CACHE="$T/cache"
export WORKFLOW_MANAGER_RELEASE_SOURCE='http://127.0.0.1:9/{version}/'
wm() { PYTHONPATH="$M/src" python3 -m workflow_manager "$@"; }
newrepo() { git init -q "$1" && git -C "$1" commit -q --allow-empty -m init; }
```

**Test data.** Scratch Git repositories under `$T`, created by the flows.

**Flows.**

1. **The pinned releases.** `wm releases`. Expected: exactly `2.3.1`,
   `2.4.0`, `2.5.0`, `2.5.1` and `2.6.0`, each with its archive name, its
   pinned sha256, and `[cached]`.
2. **A fresh install from the cache.** `newrepo "$T/r1"; wm bootstrap
   "$T/r1"; wm verify "$T/r1"; wm status "$T/r1"`. Expected: `2.6.0`, the
   newest pin, is installed, and `verify` reports a clean installation.
   The installation record (`.workflow-manager/installation.json`) carries
   a `source` object naming the package and its digest.
3. **The update path.** `newrepo "$T/r2"; wm --release-version 2.5.1
   bootstrap "$T/r2"`, commit the result, then `wm update "$T/r2"; wm
   verify "$T/r2"`. Expected: the repository moves from `2.5.1` to `2.6.0`,
   and `verify` is clean.
4. **A damaged cache entry is never installed.** Change one byte of a file
   under `$T/cache/2.6.0/tree/`, then `newrepo "$T/r3"; wm bootstrap
   "$T/r3"; echo "rc=$?"`. Expected: the entry fails its check against the
   pin and is discarded. The refetch cannot reach the source, so the
   command fails with the named `ReleaseUnavailableError` and `rc=1`, and
   `$T/r3` gets no Workflow files. Restore with `rm -rf "$T/cache/2.6.0"`
   and copy it from the real cache again.
5. **An unpublished version is refused.** `wm --release-version 9.9.9
   bootstrap "$T/r3"; echo "rc=$?"`. Expected: `ReleaseNotPublishedError`
   and `rc=1`.
6. **A local directory for a pinned version must match its pin.** Copy
   `$T/cache/2.6.0/tree` to `$T/alt`, change one byte of a payload file,
   then `wm --release-dir "$T/alt" bootstrap "$T/r3"; echo "rc=$?"`.
   Expected: a named integrity refusal, `rc=1`, and nothing installed.
7. **The packages reproduce their pins.** `wm package build
   "$T/cache/2.6.0/tree" --out "$T/pkg"`, then `wm package verify
   "$T/pkg/workflow-2.6.0.tar.gz" --sha256 <2.6.0's pin from flow 1>`.
   Expected: the rebuilt archive verifies, and its digest equals the pin.
8. **The removals.** In `$M`: `distribution/`, `migration/`,
   `tools/migrate.py` and `tools/build_release.py` no longer exist.
   `python3 tests/run_all.py --fast` is rejected as an unknown option.
   `python3 tests/run_all.py --select test_release_source.py` passes with
   `verdict: exit 0`.

**The cutover (after this checklist; network; each step on the user's
go-ahead).**
- **K1 (done 2026-09-30).** `RodrigoFAbreu/workflow` was created public,
  release immutability is on (`immutable-releases`: `enabled: true`), and
  it is cloned empty at `~/Workspace/workflow`.
- **K2.** Push the five seed commits with tags `v2.3.1` to `v2.6.0`, and
  publish the five releases with their archive, manifest and `SHA256SUMS`
  assets.
- **K3.** With an empty temporary cache and the default source:
  `releases`, then `bootstrap`/`verify` of a scratch repository for each
  pinned version. `sha256sum -c SHA256SUMS` passes on each download, and
  every digest equals its pin.
- **K4.** Push the branch and open the pull request titled `feat: Workflow
  releases are downloaded, verified packages`. The full selection is green
  in CI; its first run downloads the K2 packages. Round 1: pull request #11
  was opened, and its verification workflow was rejected (run 36767970166;
  F1). Revision 3's run was green, starting from an empty CI cache (the
  first real download). Revision 4's run
  (https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36774307005)
  is green: 21 checks, `CLEAN`.
- **K5.** Squash-merge, check that `main`'s full run is green and that
  Manager `v1.2.0` is published, then `pipx install` its wheel into a
  scratch environment and bootstrap a scratch repository with no checkout.

A problem found in K2-K5 goes back through `/apply-functional-review`.

**Round 2 results (2026-10-01, revision 4, checklist `69da8f7`).**
- **K4:** pull request #11's CI on revision 4 is green: 21 checks, `CLEAN`
  ([run 36774307005](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36774307005)).
  The verification run on the checklist head `69da8f7`
  ([run 36788937581](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36788937581))
  is green too.
- **Flow 8's targeted run:** 19/19 units, 127 tests, `verdict: exit 0`.
- Flows 1-7 exercise code unchanged since round 1, where they all passed.

**Known limitations (out of scope here).**
- The network download path is proven only by K3 and K4, after this
  checklist.
- Archives are deterministic per machine, not across zlib versions. The
  pins name the published archives.
- Each new Workflow release needs a small Manager pull request that adds
  its pin (`OD-M2-2`).
- `--manager-root` survives one release as a deprecated alias.

## Previous milestone

`workflow-manager-test-cleanup` (M1b; `governing_workflow_version: "2.2"`,
`process`, plan revision 5 approved in `5446584` on basis
`EXTERNAL_APPROVE`, base `7dabd2e`, branch
`milestone/workflow-manager-test-cleanup`): this repository's tests stop
orphaning Git's detached background maintenance at the source, and the
runner fails any run whose tests leave orphaned processes behind. Full
plan: `docs/ai-workflow/WORKFLOW_MANAGER_TEST_CLEANUP_PLAN.md`.

## Current checkpoint

**Milestone complete.** `workflow-manager-test-cleanup` reached
`MILESTONE_COMPLETE` through `/accept-milestone` on 2026-09-30, with the
user's confirmation, and `active_work_item_id` is cleared.
- **Checkpoints:** CP1-CP3 are complete.
- **Technical approval:** commit `10eff23`, implementation revision 7.
  Both implementation-review stages approved.
- **Automated verification:** the full gate passed at `ed233bd` (4102/4102
  units, 25,688 tests). Only docs and state commits have landed since.
- **Functional review:** round 1 (revision 3) found F1, fixed in
  `944920a`. Round 2 (revision 7) passed every flow; the user accepted it
  with no findings filed. The round 2 evidence is recorded under the
  flows below.

The checkpoint log below is this milestone's permanent record.

## Current blockers

None. What remains after acceptance:
- squash-merge pull request #10 under its title `test: throwaway test
  repositories leave no orphaned Git processes` (a `test:` title, so it
  releases nothing), and check that `main`'s full run is green;
- between milestones, install the Workflow Controller release that carries
  the zombie-process fix, and drop `--max-steps 1` from this lane's
  Controller runs (`docs/ROADMAP.md`, 10.1b).

## Active plan

None, because the milestone is complete. The plan document stays at
`docs/ai-workflow/WORKFLOW_MANAGER_TEST_CLEANUP_PLAN.md` (revision 5)
instead of being archived: `docs/ARCHITECTURE.md` cites it as the design
record.

## Next action

`workflow-manager-test-cleanup` is complete. Next, once pull request #10
has merged and `main`'s full run is green, run `/milestone-plan` for the
next incomplete milestone in `docs/ROADMAP.md`: M2, "Distribution rework,
packaged Workflow releases" (section 10.2).

## Checkpoint log

### CP1 -- Git maintenance off at the source (complete)

- **`D-Quiet-Git`** (`src/workflow_manager/fixture.py`):
  `THROWAWAY_GIT_CONFIG` (`maintenance.auto=false`, `gc.auto=0`,
  `maintenance.autoDetach=false`, `gc.autoDetach=false`), plus
  `configure_throwaway_repo(root)`, which writes them into a repository's
  local config. `init_git_repo` calls it.
- **`D-Quiet-Git-Env`** (`tests/parallel/isolation.py`): `chunk_env`
  appends the four pairs to the `GIT_CONFIG_COUNT` series
  (`quiet_git_config`). It keeps the parent's entries, decides by each
  key's last inherited value (case-insensitive), re-appends all four after
  an include in the series (Git expands it where it stands; added for the
  local implementation review's round-2 finding), and is idempotent when
  nested. It refuses (`GitConfigEnvError`, a tagged exit 2) a malformed
  series, and a `GIT_CONFIG_PARAMETERS` that sets one of the keys, includes
  a file (`include.path`, `includeIf.<condition>.path`; added for the
  external implementation review's round-1 finding) or cannot be parsed.
  The parser reads Git's own `-c` encoding, checked against Git
  2.55.0's output. `chunk_env`/`run_chunk` take an optional
  `git_template`: `GIT_TEMPLATE_DIR` is set to it, or removed when it is
  omitted. `build_git_template(run_dir)` builds `<run_dir>/git-template/`
  from Git's default template (read with the user and system config off and
  every inherited `GIT_TEMPLATE_DIR`/`GIT_CONFIG_*`/`GIT_CONFIG_PARAMETERS`
  removed, which disposes of the plan review's three optional findings)
  plus a `config` holding the four keys.
- **Executor** (`tests/parallel/executor.py`): `local_run`, `run_shard`
  and `aggregate` call `isolation.check_git_env()` before anything runs.
  `Engine` builds the template once per run and passes it to every
  `run_chunk` and to `prepare_merge`'s `chunk_env`. `cli.py`'s docstring
  names the new refusal. It needed no code change, since
  `GitConfigEnvError` is an `IsolationError`, which is already in
  `REFUSALS`.
- **Routing** (`D-Quiet-Git-Repo`): the ten host `init` sites of plan 3.2
  are `init_git_repo` calls. `frozen_runs.empty_repo` and
  `test_bootstrap.empty_repo` are now just that call, and the rest keep
  their own identity and extra keys after it. The two clones
  (`test_squash_merge_compat._build`, `test_parallel_runner.scratch_clone`)
  are followed by `configure_throwaway_repo` on their destinations.
- **Tests** (`tests/test_orphan_processes.py`, new; an exact `full` rule in
  `tools/ci/pr_profile_paths.json`):
  - T-QG-1, `TestChunkEnvGitConfig`, 13 tests;
  - T-QG-2, `TestThrowawayRepositories`, 4 tests. They cover the helper,
    a configured clone, and a plain init and a plain clone under the
    template, whose `hooks/` and `info/` equal a default repository's.
    They also cover a direct `run_chunk` that drops an inherited
    `GIT_TEMPLATE_DIR`;
  - T-QG-5, `TestFrozenEvidenceClone`, 2 tests. The frozen `2.6.0`
    `_materialize_pinned_worktree_at_commit` runs unmodified from the
    payload, in a `-B` interpreter, under `patch.dict(os.environ)`. With
    the template, a `PATH`-only Git reports `local` for all four keys.
    Without it, it reports none of them. The payload's files are unchanged;
  - T-QG-4, `TestRoutingCheck`, 12 tests: the real tree, plus the rule's
    synthetic cases.

  `test_parallel_runner.py`'s `test_the_chunk_environment_and_session` now
  asserts the four pairs, and `GIT_TEMPLATE_DIR` both with and without a
  template.
- **Deviations from the plan's wording, both disclosed here:**
  - The executor process never imports `workflow_manager`
    (`frozen_chunk.py`'s docstring). So `isolation.py` reads
    `THROWAWAY_GIT_CONFIG` as a literal from `fixture.py`'s source with
    `ast`, located from its own `__file__`, instead of importing it. The
    definition stays single, and a T-QG-1 test asserts that the two values
    are equal.
  - T-QG-4's exemption list is no longer empty. It holds four entries,
    each with its reason:
    - `isolation.build_git_template`'s scratch `git init`, which reads
      Git's default template and never commits;
    - three deliberate plain sites in `test_orphan_processes.py`: the
      default-config baseline repository, and T-QG-2's plain `init` and
      plain `clone` under the template.

    A test keeps every exemption matched to a live site. Two of the
    module's own tuples looked like shape 3. They were rewritten, which
    changed no rule.
- **Verification:**
  - `run_all.py --select test_orphan_processes.py`: 4/4 units, 31 tests,
    exit 0;
  - every touched host module plus `test_bootstrap_e2e.py` and
    `test_disposable_repo_fixtures.py`: 1448/1448 units, 8901 tests, exit
    0;
  - INV-1's `git diff 7dabd2e` is empty, `workflow-manager verify .` is
    clean, and `CLAUDE.md` is unchanged;
  - the full gate, `python3 tests/run_all.py` over this checkpoint's tree
    (`tree_digest 60386226...`): 4092/4092 units, 25,655 tests, exit 0,
    `selection_digest 6e7a9c1b...`, `tests_digest 10276e31...`. Its only
    failed chunks are the documented `2.3.1`/`2.4.0`
    `workflow_integration_test.py` portability exceptions.

### CP2 -- the leak check, and every orphan source fixed or declared (complete)

- **The wrapper** (`tests/parallel/reaper.py`, new, stdlib-only, run as
  `python3 -I -S -B`): plan 5.4 steps 1-6. It makes itself a child
  subreaper, runs the chunk as its only child, and passes the lock fd on
  (`--pass-fd`). Every 10 ms it lists `/proc/self/task/*/children` and
  drains exited children (`waitid(P_ALL, WNOWAIT)`, record, then
  `waitpid`). Labels are the command line, else `[<comm>]`, else
  `[unknown]`, and a weak label is upgraded at reap time. After the chunk
  exits, a grace period of at most 5 s ends at once on `ECHILD`, followed
  by a kill-and-drain loop until `ECHILD`. The report is written
  atomically. Exit is the chunk's status, with a signal death re-raised
  (`SIG_DFL`, unblocked, `RLIMIT_CORE` 0, fallback `os._exit(128+n)`).
  Its own fault is exit 125, with no report, after a best-effort kill
  loop. An unsupported host reports `supported: false` with the reason.
  The test seams `--force-unsupported`/`--platform` are reached only
  through `isolation.REAPER_TEST_ARGS`, never through the environment, so
  an operator cannot forge a non-Linux platform.
- **The runner** (`isolation.py`): `run_chunk` launches the wrapper,
  located from `isolation.py`'s own path. It deletes a stale report first
  and, after an ordinary exit, validates the report: its schema, its
  `chunk_id`, and a `chunk_status` equal to the wrapper's exit. A failure
  there is the new infrastructure outcome `bad_orphan_report`, naming the
  report path. `ChunkRun`/`ChunkResult` carry `orphans`, `platform`,
  `supported` and `unsupported_reason` through the JSON round trip.
- **The verdict** (`executor.py`): `verdict_of(orphan_sources=)` adds
  `OrphanProcessError`, `OrphanCheckUnavailableError` (Linux, decided on
  the report's `platform`) and `OrphanDeclarationError`, in local,
  `--run-shard` and `--aggregate` modes. The three `resources.load`
  callers and `planner.plan_checkout` pass `orphan_unit_ids`.
- **The report** (`report.py`): one `orphan check:` line, a `tolerated
  orphans` section by chunk, and `orphan_sources unused in this run`.
  `cli.py`'s docstring names the three new exit-2 faults.
- **Declarations** (`resources.py`, `resources.json`): an optional
  `orphan_sources` key, with a non-empty `reason`, validated against the
  full inventory (or against the host ids when `orphan_unit_ids` is
  omitted). `planner.make_chunks` gives a declared frozen class its own
  chunk (`<group>#<Class>`). With no frozen declaration, the chunks are
  unchanged.
- **Tests** (`tests/test_orphan_processes.py`):
  - T-QG-3: `TestEnvironmentLayerUnderTheWrapper` and
    `TestFrozenCloneUnderTheWrapper`;
  - T-OC-1: `TestReaperDirect`, 11 tests;
  - T-OC-2: `TestOrphansThroughTheExecutor`, `TestBadOrphanReports` and
    `TestVerdictOfOrphans`;
  - T-OC-3: `TestOrphanSourcesSchema` and
    `TestFrozenDeclarationThroughTheModes`;
  - T-OC-4: `TestKilledChunks`.

  T-QG-5's setup moved into `_FrozenCloneCase`, which T-QG-3 reuses.
  T-QG-3 runs on Git 2.55.0, which it prints. The `ubuntu-latest` image
  (Ubuntu 24.04, image version `20260920.314.1`) documents Git 2.55.0 as
  well, so no extra verification on an older Git was needed.
- **Adapted, not weakened** (`test_parallel_runner.py`):
  - the chunk-session test now asserts that the chunk's session and group
    are its parent wrapper's;
  - the two `ChunkResult` round-trip tests carry an orphan check;
  - the real-file `resources.load` calls pass `orphan_unit_ids`;
  - `scratch_checkout`'s own validation load does full discovery only when
    the scratch declares `orphan_sources`.
- **Deviations, disclosed:**
  - `ChunkResult.from_json` also refuses a `passed`/`failed` result with no
    orphan check. That is fail-closed for `--aggregate`, and not in the
    plan's wording.
  - `run_chunk` takes an `interrupted` event, which the executor passes as
    `Engine.stop`. On the interrupt path the executor kills the group from
    outside, so the report is not read, exactly as on timeout (plan 5.4:
    "not the timeout or interrupt paths"). Without it, an interrupted run
    also reported a spurious `bad_orphan_report`.

**Orphan inventory** (full selection with the check on,
`/tmp/cp2-full1`, before any declaration). Each source is listed by chunk
and label, with its disposition:

| source | label | disposition |
| --- | --- | --- |
| `host:test_parallel_runner.py` classes using the spawn-context helpers (seen in `TestRefusalsAreDistinguishable`, `TestRunLockAndRecovery`) | `python3 -B -c from multiprocessing.resource_tracker import main;main(4)` / `[python3]` | **fixed at the source**: `tearDownModule` stops `multiprocessing`'s resource tracker, waiting for it |
| `host:test_parallel_runner.py::TestRunChunk` | 2 x `[python3]` | **declared**: the timeout and interrupt tests kill a chunk's group, wrapper included, and the chunk the wrapper had not reaped is re-parented (5.6) |
| `host:test_parallel_runner.py::TestExecutorLevelFaults` | 1 x `[python3]` | **declared**: the same, from its timeout test |
| `host:test_parallel_runner.py::TestLockAndRecoveryThroughTheCli` | the scratch run's `reaper.py` / chunk | **declared**: it SIGKILLs an executor while its chunk runs, and interrupts runs |
| `host:test_parallel_runner.py::TestRunLockAndRecovery` | the `_WAIT_FOR_FILE` child | **declared**: it SIGKILLs a helper executor whose chunk-like child holds the lock |
| `host:test_orphan_processes.py::TestKilledChunks` | 1-2 x `[python3]` | **declared**: T-OC-4 times out and interrupts chunks on purpose |
| `frozen:<2.3.1..2.6.0>/<conformance,target,bootstrapped>/workflow_state_completion_obligations_test.py::TestStateLock` (15 units) | `multiprocessing.forkserver` main, `resource_tracker` main, `[python3]` | **declared, frozen**: the default `multiprocessing` context (forkserver on Python 3.14) outlives the chunk; each declared class runs in its own chunk |

No Git process appeared among the orphans in any run (no `[git]` or
`git` label). An earlier run with the SIGINT test hanging was an artefact
of launching it from a shell `&` job, which ignores SIGINT; background runs
launched through the tool keep SIGINT's default.

- **Verification:**
  - `python3 -m unittest test_orphan_processes`: 58 tests, OK;
  - `run_all.py --select test_parallel_runner.py --select
    test_orphan_processes.py` exposed the sources above;
  - **full gate, run 1** (`/tmp/cp2-full2`): 4101/4101 units, 25,682
    tests, exit 0, `orphan check: on`, zero undeclared orphans, 20 chunks
    tolerated, no unused declaration;
  - **full gate, run 2** (`/tmp/cp2-full3`, the same tree): the same
    totals, exit 0, zero undeclared orphans;
  - both runs have `selection_digest b8ca6c1f...`, `tests_digest
    47b3b636...` and `tree_digest 3c65e8a3...`. The only failed chunks are
    the documented `2.3.1`/`2.4.0` `workflow_integration_test.py`
    portability exceptions;
  - INV-1's `git diff 7dabd2e` is empty, `workflow-manager verify .` is
    clean, and `CLAUDE.md` is unchanged.

### CP3 -- measurement, documentation and the milestone's evidence (complete)

- **Measurement** (plan 3.4 repeated under the wrapper's whole-run use,
  5.4). The command, run with the operator's `GIT_CONFIG_*` exports removed
  so that only this milestone's layers apply:

  ```bash
  env -u GIT_CONFIG_COUNT -u GIT_CONFIG_KEY_0 -u GIT_CONFIG_VALUE_0 \
      -u GIT_CONFIG_KEY_1 -u GIT_CONFIG_VALUE_1 \
    python3 -I -S -B tests/parallel/reaper.py --report /tmp/cp3-whole/outer.json \
      --chunk-id whole-run -- python3 tests/run_all.py --results /tmp/cp3-whole/results
  ```

  | run | verdict | orphans reaching the outer probe | Git among them | wall |
  | --- | --- | --- | --- | --- |
  | base `7dabd2e`, default Git config (plan 3.4) | exit 2 (the author's own edit, 3.4) | 42,158 | 31,731 seen as Git, plus 10,391 unread | 380 s |
  | base `7dabd2e`, the four keys exported (plan 3.4) | exit 0 | 36 | 0 | 370 s |
  | CP3 (head `2c0a926` plus this checkpoint's docs), nothing exported | exit 0 | **0** | **0** | 384 s |

  - The outer report (`outer.json`): `supported: true`, `platform: linux`,
    `chunk_status: 0` and `orphans: []`. Nothing escaped the per-chunk
    wrappers, and nothing ran outside a wrapper orphaned anything (plan
    5.6's "processes outside chunks").
  - The per-chunk reports: 333 of them, one per chunk, all `supported:
    true`. They recorded 37 orphans in 20 chunks, exactly the 20 declared
    `orphan_sources` (no undeclared orphan, no unused declaration). **No
    entry is Git**: no label is `[git]` or a `git` command line. The
    orphans are the declared frozen `TestStateLock` forkserver and
    resource-tracker processes, and the declared host kill tests'
    `[python3]`, scratch `reaper.py` and `_WAIT_FOR_FILE` children.
  - The wall time is one run, for information, not a target. It is within
    the noise of 3.4's rows.
- **Documentation:**
  - `docs/ARCHITECTURE.md`, "Verification execution": the exit-`2` list
    gains `OrphanProcessError`, `OrphanCheckUnavailableError`,
    `OrphanDeclarationError`, `bad_orphan_report` and `GitConfigEnvError`;
  - a new "Orphaned processes" paragraph gives the cause, the settings, the
    environment layer and its template, the per-repository layer and its
    routing check, the leak check, the verdict, `orphan_sources` and its
    policy, the whole-run use with this measurement, and plan 5.6's
    residuals;
  - `CLAUDE.md`, non-managed part: one paragraph saying that a run fails on
    an orphaned process, and that deliberate sources are declared in
    `orphan_sources`.
- **Verification:**
  - the full gate is the measured run above: 4101/4101 units, 25,682
    tests, exit 0, `orphan check: on`, `selection_digest b8ca6c1f...`,
    `tests_digest 47b3b636...`, `tree_digest c7db107f...`. Its only failed
    chunks are the documented `2.3.1`/`2.4.0`
    `workflow_integration_test.py` portability exceptions. The two digests
    equal CP2's two gates, since CP3 changes no code or test;
  - INV-1: `git diff 7dabd2e -- distribution migration scripts
    .claude/commands .github/workflows/workflow-conformance.yml` is empty,
    and `workflow-manager verify .` reports that the installation matches
    workflow 2.6.0;
  - INV-2: no test was removed or skipped, and no frozen pin or portability
    exception changed;
  - INV-3: `CLAUDE.md` up to `<!-- workflow-manager:end -->` is
    byte-identical to the base.

### Self-review of the milestone diff and the full gate (`SELF_REVIEWING_IMPLEMENTATION`)

- `enter_self_reviewing_implementation` was a no-op. CP3's
  `complete_checkpoint` had already written the phase.
- The whole `7dabd2e..3988c5c` diff was reviewed:
  - `tests/parallel/reaper.py`: recording, the drain order (record before
    reap), the grace period, the kill loop until `ECHILD`, the exit status
    pass-through and the own-fault path;
  - `tests/parallel/isolation.py`: `quiet_git_config` and its
    `GIT_CONFIG_PARAMETERS` parser, `build_git_template` (the plan
    review's `GIT_CONFIG_*` strip is in `_TEMPLATE_BUILD_DROPPED` plus the
    `KEY_`/`VALUE_` prefixes), `chunk_env`'s template handling, and
    `run_chunk`'s report validation;
  - `executor.py`, `planner.py`, `report.py` and `resources.py`: the
    three new verdict faults in all three modes, the `ChunkResult`
    round trip, the own chunk for a declared frozen class, and the
    `orphan_sources` schema;
  - `fixture.py`, the routed `init`/clone sites, `resources.json`, the new
    test module, and the docs.
- No finding was blocking or important, and nothing was changed. One
  reachable-in-theory case was checked and left as it is: a wrapper that
  survives re-raising the chunk's death signal exits `128+n`, which
  disagrees with the report's `chunk_status` and is therefore a
  `bad_orphan_report` fault. That fails closed, and only a signal whose
  default action is not to terminate can reach it.
- INV-1/INV-3: `git diff --stat 7dabd2e HEAD -- distribution migration
  scripts .claude/commands .github/workflows/workflow-conformance.yml` is
  empty. `CLAUDE.md` up to `<!-- workflow-manager:end -->` is
  byte-identical to the base.
- **The full gate**, `python3 tests/run_all.py --results /tmp/m1b-gate` at
  `3988c5c`, 2026-09-29 17:15-17:21 (380.5 s wall, 8 workers):
  - `evidence: full selection, local, 8 worker(s), head 3988c5c06b050cd59ceb01459aa8574eb3d330a6,
    4101/4101 units, 25682 tests, selection_digest
    b8ca6c1f6133fa0cdf10e9ac86d3a3d1f4dcdc290c641e5627f7b4911d6cb194,
    tests_digest 47b3b6364ed38a35b82fed9f354437ca0a6da96f4e189d0da0a712eb08364c14,
    tree_digest 1c2f4dafdf44691f9aee26609c43871d5e66fc55afc92cc6ff7845241b9bf6c2`,
    `verdict: exit 0`;
  - `orphan check: on`. The 333 per-chunk reports are all `supported:
    true`. They record 36 orphans in 20 chunks, exactly the 20 declared
    `orphan_sources`, with no undeclared orphan, no unused declaration,
    and **no Git process**;
  - every host module was OK. The only non-zero frozen chunks were the four
    documented `2.3.1`/`2.4.0` `workflow_integration_test.py` portability
    exceptions (`TestRetiredScopedRemediationLeavesNoLiveSurface`), which
    phase B judged as expected;
  - the selection and tests digests equal CP2's and CP3's, since no code
    or test changed after CP2.
- The whole-run outer-probe measurement (0 orphans reaching it) is CP3's,
  at `2c0a926` plus CP3's docs. Nothing in the code or tests changed since,
  so it was not repeated.

### Implementation review round 4 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Revision 4 (the functional-review fix F1, `944920a`) was reviewed
locally. F1 was judged correct. The one finding was test-only:

- **I1, important:**
  `TestReaperDirect::test_an_orphan_whose_cmdline_reads_empty_is_labelled_by_its_comm`
  had a race like F1's. The middle process exited while the daemon was
  still alive, so the wrapper could see it alive and label it by its
  inherited command line rather than `[python3]`. It failed once in the
  review's runner rerun. Fixed in `906e884`: in `zombie` mode the middle
  process waits, without reaping, until the daemon is a zombie, and only
  then exits. The test's daemon now sleeps 0.2 s before it exits, so the
  old ordering fails every time (negative control: 5 of 5 failures with
  the wait removed). Loop: 200 runs under 16 CPU-bound load processes, 0
  failures.
- **O-a, applied** (`9ba3b4d`): `is_git_label` applies the `git`/`git-*`
  rule to a bracketed `[<comm>]` too (`[git-remote-htt]` is Git,
  `[gitk-like]` is not).
- **O-b, applied:** the bundle now names `676a164` as F1's gate commit.
- **The full gate** at `9ba3b4d`: `evidence: full selection, local, 8
  worker(s), head 9ba3b4d6e47e10bef3f11de2ce565036bc43f4b7, 4102/4102
  units, 25687 tests, selection_digest 43d1394e..., tests_digest
  2ac5212b..., tree_digest 8c066271...`, `verdict: exit 0`, 389.2 s wall.
  `orphan check: on`, only the 20 declared `orphan_sources` chunks
  tolerated, no Git orphan.

### Implementation review round 5 (`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, `REVISE`)

Revision 5's local stage approved. The manual external stage returned
`REVISE` with three important, test-only findings, all in
`TestReaperDirect`, all accepted and reproduced:

- **I1:** `test_a_double_forked_setsid_sleeper_is_one_killed_orphan`
  required `"sleep 300"`, but the middle process could exit before the
  daemon exec'd, so the wrapper labelled it with its Python command line
  (revision 4's CI failure). Fixed in `8702136`: in `exec` mode the middle
  process exits only once the daemon's command line reads `sleep`. In
  `8a9acc0` the daemon execs 0.2 s late, so the old ordering fails every
  time (negative control: 3 of 3 failures with the wait removed).
- **I2:** the 2.5, 4 and 4.5 s wall-clock limits. **I3:** the short-lived
  daemon's `exited` fate, and the fork case's "more than 20 forks before
  the grace period ends". Fixed in `8702136`: `reaper.py` gains a
  `--grace-seconds` test seam (the runner never passes it). The clean,
  comm-label, short-lived and many-daemons cases run with a 3600 s grace
  period, which `reap`'s 120 s timeout always ends first, so returning at
  all proves an end on `ECHILD` and no self-exiting orphan is `killed`.
  The fork case's chunk exits, starting the default grace period, only
  after 21 forks. No wall-clock assertion remains.
- Load check: `TestReaperDirect` 3 times concurrently under 2 CPU-bound
  processes per CPU, all green; 5 more sequential runs green.
- **The full gate** at `8a9acc0`: `evidence: full selection, local, 8
  worker(s), head 8a9acc0d69d9c9ca11c915fc68ad0aa3761c864a, 4102/4102
  units, 25687 tests, selection_digest 43d1394e..., tests_digest
  2ac5212b..., tree_digest 9b1c8f52...`, `verdict: exit 0`, 384.6 s wall.
  `orphan check: on`, only the 20 declared `orphan_sources` chunks
  tolerated, no Git orphan.
- The review's acceptance criterion also asks for a green required CI run
  for the corrected revision. That needs a push, which is the user's.

### Implementation review round 6 (`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, `REVISE`)

Revision 6's local stage approved. The manual external stage returned
`REVISE` with two important, test-only findings, both in `_DOUBLE_FORK`'s
readiness waits, both accepted and reproduced. Fixed together in
`ed233bd`:

- **I1:** the middle process's wait for the daemon's `sleep` exec had no
  deadline. A daemon that died first stayed an unreaped zombie whose
  command line reads empty, so the middle process polled forever and the
  chunk blocked in `waitpid`; `reap`'s 120 s timeout kills only the
  wrapper. The middle process now fails at once on a daemon that is a
  zombie in `exec` mode, and after `TIMEOUT` (60 s) otherwise: it kills
  the daemon and exits 3, and the chunk fails on that status.
- **I2:** the chunk's own readiness loop fell through after 60 s, so a
  slow spawner could start the wrapper's kill grace with fewer than 21
  forks. On its deadline it now kills the daemon and exits 1, naming the
  state it waited for, so the test fails on its return code before the
  wrapper's check starts.
- Regression: `test_a_daemon_that_never_gets_ready_fails_the_chunk_with_its_state`
  (a daemon that exits before its exec, one that never execs, and one
  that never forks, with a 1 s `TIMEOUT` and `UNREACHABLE_GRACE`, so
  returning at all proves the daemon was killed).
- Negative control: the revision-6 template with a daemon that exits
  before its exec was still waiting after 15 s; the fixed one fails in
  0.02 s.
- Load check: `TestReaperDirect` 3 times concurrently under 2 CPU-bound
  processes per CPU, all green.
- **The full gate** at `ed233bd`: `evidence: full selection, local, 8
  worker(s), head ed233bd182437e9ee919c0924567ac7296c40e67, 4102/4102
  units, 25688 tests, selection_digest 43d1394e..., tests_digest
  d2553227..., tree_digest beac9d70...`, `verdict: exit 0`, 396.0 s wall.
  `orphan check: on`, only the 20 declared `orphan_sources` chunks
  tolerated, no Git orphan.

### Revision 7 approved

Revision 7's local stage (round 7) and manual external stage (round 7)
both returned `APPROVE`. Pull request #10's required CI on `f9dadd9` is
green: 21 checks pass (run
https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36651520532).
The user's technical approval is `10eff23`.

## Functional review checklist

You are testing the runner as an operator uses it: no orphaned Git
processes, and a run that fails when its tests leave a process behind.
- **Round 2** (implementation revision 7). Round 1 (revision 3) found F1,
  fixed in `944920a`. The later review rounds changed only
  `tests/test_orphan_processes.py`, making its assertions independent of
  timing. Re-test flows 1, 4 and 5; flows 2 and 3 exercise code that
  has not changed since round 1 (both passed then), and are optional.
- **Technical approval:** commit `10eff23`, implementation revision 7.
- **Where findings go:**
  `.ai-review/workflow-manager-test-cleanup/feedback/FUNCTIONAL_REVIEW.md`.
- **Automated verification:** already current. The full gate passed at
  `ed233bd`, the final code (4102/4102 units, 25,688 tests, verdict 0,
  orphan check on). Only docs and state commits have landed since.

**Setup.**
- Linux, Python 3.12 or later, Git 2.55 or later, and an authenticated `gh`
  (flow 5 only).
- Unset your own Git environment layers first, so that only this
  milestone's layers apply: `env -u GIT_CONFIG_COUNT -u GIT_CONFIG_KEY_0
  -u GIT_CONFIG_VALUE_0 -u GIT_CONFIG_KEY_1 -u GIT_CONFIG_VALUE_1 ...`.
- Run flow 1 in this checkout, with a clean working tree. Run flows 2-4 in
  a throwaway clone, so that no scratch test touches this repository:

```bash
export M=~/Workspace/workflow-manager
export T=$(mktemp -d) && git clone -q "$M" "$T/c"
git -C "$T/c" checkout -q milestone/workflow-manager-test-cleanup
```

**Test data.** None. Flow 2 adds one scratch test module to the clone.

**Flows.**

1. **The full gate under an outer probe (the milestone's point).** In `$M`:

   ```bash
   env -u GIT_CONFIG_COUNT -u GIT_CONFIG_KEY_0 -u GIT_CONFIG_VALUE_0 \
       -u GIT_CONFIG_KEY_1 -u GIT_CONFIG_VALUE_1 \
     python3 -I -S -B tests/parallel/reaper.py --report "$T/outer.json" \
       --chunk-id whole-run -- python3 tests/run_all.py --results "$T/results"
   ```

   Expected, in about 6.5 minutes:
   - `orphan check: on`, and a list of tolerated orphans by chunk: only the
     20 declared `orphan_sources` units (the frozen `TestStateLock`
     classes and five host kill tests);
   - `4102/4102 units`, `verdict: exit 0`. The only non-zero frozen chunks
     are the four documented `2.3.1`/`2.4.0` `workflow_integration_test.py`
     portability exceptions;
   - `$T/outer.json` has `"supported": true`, `"chunk_status": 0` and
     `"orphans": []`: nothing escaped the run. Before this milestone the
     same probe received 42,158 orphans, 31,731 of them Git.
   - While it runs, `ps -eo stat= | grep -c '^Z'` stays near zero.
   - Run it in the foreground, never started with `&`: a background start
     from a non-interactive shell ignores SIGINT for the whole tree, and
     one runner test then times out (observation O1 from round 1, not
     caused by this milestone).
2. **A leaked process fails the run.** In the clone, add a test that leaves
   a detached process behind:

   ```bash
   cd "$T/c" && cat > tests/test_zz_orphan_probe.py <<'PY'
   import subprocess, sys, unittest
   class TestLeavesADaemon(unittest.TestCase):
       def test_daemon(self):
           subprocess.run([sys.executable, "-c",
               "import os,time\nif os.fork()==0:\n    os.setsid()\n    time.sleep(20)\n"], check=True)
   PY
   python3 tests/run_all.py --select test_zz_orphan_probe.py; echo "rc=$?"
   ```

   Expected: the test itself prints `OK`, then `orphan check: on`,
   `verdict: exit 2`, and `run_all: error[OrphanProcessError]:
   host:test_zz_orphan_probe.py::TestLeavesADaemon: 1 orphaned process(es):
   1 x /usr/bin/python3 -c import os,time ...`, and `rc=2`. Remove the file
   afterwards.
3. **An inherited include is refused.** In the clone:

   ```bash
   printf '[maintenance]\n\tauto = true\n' > "$T/inc.cfg"
   GIT_CONFIG_PARAMETERS="'include.path'='$T/inc.cfg'" \
     python3 tests/run_all.py --select test_templates.py; echo "rc=$?"
   ```

   Expected: `run_all: error[GitConfigEnvError]: GIT_CONFIG_PARAMETERS sets
   include.path, and an included file outranks the runner's quiet-Git
   settings; unset it (or drop the include) and re-run`, and `rc=2`.
4. **Ordinary targeted runs still pass.** In the clone:
   `python3 tests/run_all.py --select test_orphan_processes.py` passes,
   with `orphan check: on` and `verdict: exit 0`.
5. **The pull request.** Pull request #10, titled `test: throwaway test
   repositories leave no orphaned Git processes` (`OD-1`), at head
   `f9dadd9` or later. Expected on `gh pr checks 10`:
   - `Conventional Commit title` green, with release impact `none`;
   - the verification `plan` job chooses `full` (the pull request touches
     `src/` and `tests/parallel/`, M1's stopgap rule 1);
   - all shards, `package` and `aggregate` green, and the shard logs say
     `orphan check: on`.

   Record the run URLs in this file. Round 1: run 36633871279 failed
   (F1). Revision 7: run 36651520532 is green.

**Round 2 results (2026-09-30, revision 7, clone head `f421fe0`).** Flows
1-4 ran in a throwaway clone with scratch directories; flow 5 is pull
request #10.
- **Flow 1:** `orphan check: on`, exactly the 20 declared `orphan_sources`
  chunks tolerated, 4102/4102 units, 25,688 tests, `verdict: exit 0`. The
  outer probe reported `"supported": true`, `"chunk_status": 0` and no
  orphans; at most 3 zombies were seen during the run.
- **Flow 2:** `OrphanProcessError` naming
  `host:test_zz_orphan_probe.py::TestLeavesADaemon`, `rc=2`.
- **Flow 3:** `GitConfigEnvError`, `rc=2`.
- **Flow 4:** 14/14 units, 64 tests, `orphan check: on`, `verdict: exit 0`.
- **Flow 5:** pull request #10 at `f421fe0`: 21 checks pass and one skips
  (the nightly alarm)
  ([run 36655080879](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36655080879)).

**Known limitations (out of scope here).**
- Non-Linux runs print a notice instead of checking (`OD-4`); CI enforces
  the check on Linux.
- The Workflow Controller's own zombie leak is the Controller lane's fix
  (C1b). This milestone removes this suite's orphans at the source; the
  Manager lane keeps running the Controller one step at a time until that
  fix is installed.
- Dynamic Git arguments are outside the static routing check (plan 5.6).
- Observation O1 (the runner has no SIGINT handler of its own) was already
  present at the base `7dabd2e`. It is recorded as a follow-up, not fixed
  here.

## Previous milestone

`workflow-manager-trunk-model` (`governing_workflow_version: "2.2"`,
`process`, plan revision 3 approved in `aede0df`, base `b856a97`): the
trunk model for this repository -- a protected, squash-only `main`,
Conventional Commit pull-request titles, tag-derived Manager versions and
releases, and a reduced newest-release pull-request profile as a stopgap.
Full plan: `docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md`.

## Current checkpoint

**Milestone complete.** `workflow-manager-trunk-model` reached
`MILESTONE_COMPLETE` through `/accept-milestone` on 2026-09-29, with the
user's confirmation, and `active_work_item_id` is cleared.
- **Checkpoints:** CP1-CP7 are complete.
- **Technical approval:** commit `7995695`, implementation revision 2.
  Both implementation-review stages approved.
- **Automated verification:** the full gate passed at `ed39920` (4088/4088
  units, 25,624 tests). Only docs and state commits have landed since.
- **Functional review:** accepted by the user against the checklist below,
  with no findings filed. Cutover steps C0-C1 ran; their evidence is
  recorded under flows 7 and 8.

The checkpoint log below is this milestone's permanent record.

## Current blockers

None. The cutover after acceptance (`docs/RELEASING.md`, "Cutover",
C2-C5) is complete (2026-09-29):
- **C2:** `merge-settings.json` applied: squash only, `PR_TITLE`/`BLANK`,
  auto-merge allowed, branches deleted on merge.
- **C3:** both required checks reported green, under their exact names, at
  pull request #4's final head `7dca707`
  ([aggregate](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36568676727),
  [Conventional Commit title](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36568676757)).
  Then ruleset `main` (id 24179602) was created from `ruleset-main.json`.
- **C4:** pull request #4 marked ready and squash-merged as `59158c6`
  (`feat: trunk model, Manager releases and the stopgap PR test profile
  (#4)`).
- **C5:** `main`'s push run was full and green
  ([run 36569800136](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36569800136)).
  The release workflow
  ([run 36570855470](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36570855470))
  published [`v1.1.0`](https://github.com/RodrigoFAbreu/workflow-manager/releases/tag/v1.1.0)
  on `59158c6`, with the wheel, the sdist and `SHA256SUMS`. `sha256sum -c`
  passes on the downloaded assets, and the wheel, installed into a fresh
  venv, prints `workflow-manager 1.1.0`.

## Active plan

None, because the milestone is complete. The plan document stays at
`docs/ai-workflow/WORKFLOW_MANAGER_TRUNK_MODEL_PLAN.md` (revision 3)
instead of being archived: `docs/ARCHITECTURE.md` and `docs/RELEASING.md`
cite it as the design record.

## Next action

`workflow-manager-trunk-model` is complete and merged. Next, run
`/milestone-plan` for the next incomplete milestone in
`docs/ROADMAP.md`. That is M1b, "Test cleanup, no orphaned Git
processes" (section 10.1b), the small milestone the agreed lane order
(2026-09-29) puts before M2.

## Checkpoint log

### CP1 -- Conventional Commit titles and tag-derived versions (complete)

- `tools/release/release.py` (new, stdlib): `check-title` (SignalHub's
  title regex on the stripped subject; the 5.1 impact table, `!` major on
  any type; each rejection names its failure and prints the accepted form),
  `next-version` (highest strict `vX.Y.Z` in `git tag --merged HEAD`, else
  the baseline `1.0.0` at `b856a97`, which must be an ancestor of `HEAD`;
  the bump is the highest impact over `git log --first-parent`; `none`-only
  or empty prints nothing; a non-Conventional subject is a patch with a
  `::warning::`), `assert-not-superseded` (exit 3 when a strict tag sits on
  a non-ancestor of `HEAD`), `resolve-target` (the newest completed green
  `push` run on `main`'s first parent, via `gh api`; a pick that is neither
  the trigger nor its descendant refuses; an API, parse or git failure, or
  no candidate, falls back to the trigger with a warning; `select_target`
  is pure), `set-version DIR VERSION` (rewrites the single placeholder
  line in a copy, never the checkout; `X.Y.Z` or `X.Y.Z+local` only).
  Exit codes 0/1/2/3.
- `pyproject.toml`: `version = "0.0.0.dev0"`, the placeholder, with a
  comment naming the Git tag as the only version authority (INV-6).
- Verification: `run_all.py --select test_release_versioning.py` 10/10
  units, 54 tests OK (every item of the plan's CP1 test list, on real
  temporary repositories). INV-1 and INV-3:
  `git diff b856a97 -- distribution migration scripts .claude/commands src .github/workflows/workflow-conformance.yml`
  empty. The new module's PR-profile rule is CP4's (plan 6.2).

### CP2 -- Manager version reporting and release packaging (complete)

- `src/workflow_manager/cli.py`: `--version` needs no subcommand and
  prints the first of plan 5.3's answers: the installed metadata version
  when it is a release (not `.dev`, not missing); `X.Y.Z (checkout at
  vX.Y.Z)` when `MANAGER_ROOT` is itself the top of a Git work tree, its
  tracked tree is clean and `HEAD` carries a strict tag; otherwise
  `development build (<git describe --tags --always --dirty>)`, or plain
  `development build` outside a work tree (so a `.venv` inside an
  unrelated repository never reports that repository's tag). Every Git
  call is bounded (10 s) and fails soft to the next answer. Two
  implementation choices, same behaviour as the plan's wording: the version
  is computed by a lazy `argparse.Action` (no Git call on ordinary
  commands) rather than a precomputed `action="version"` string, and the
  exact tag comes from `git tag --points-at HEAD` filtered to strict tags,
  highest first, rather than `git describe --exact-match`, which picks
  arbitrarily between several tags on one commit and can return a
  non-strict one.
- The missing-distribution hint: `releases`, `bootstrap`, `update`, and
  `status`/`verify` of a managed target (or with `--release-version`) now
  say the Manager is probably installed from a wheel and name
  `--manager-root <workflow-manager checkout at the matching tag>`,
  replacing "run tools/migrate.py first". `status` of an unmanaged target
  and `uninstall` still need no release.
- `tools/release/package.py` (new): copies `pyproject.toml`, `README.md`
  and `src/` (no caches or `egg-info`) to a temporary directory,
  `set_version`s it, runs `python -m build --outdir DIR`, installs the
  wheel into a fresh venv and requires `--version` to print exactly
  `workflow-manager V`, `--manager-root R releases` to list exactly `R`'s
  releases and `--manager-root R verify R` to exit 0; then writes a
  sorted, `sha256sum`-compatible `SHA256SUMS`. It refuses a non-empty
  `--out` so the sums cover only this build.
- `.github/tools/requirements.txt` (new): `build==1.6.1`. `README.md`:
  `--version`, the `pipx reinstall workflow-manager` note (finding 6) and
  `--manager-root` for a wheel install.
- Verification: `run_all.py --select test_manager_version.py --select
  test_bootstrap.py --select test_release_versioning.py` 36/36 units, 192
  tests OK (`test_manager_version.py`: 43 tests covering every item of the
  plan's CP2 list). Smoke evidence, outside the test suite (INV-5): with
  `build==1.6.1` in a throwaway venv, `package.py --version 1.1.0
  --manager-root .` built both assets, passed all three installed-wheel
  checks, and `sha256sum -c SHA256SUMS` accepted the result. INV-1/INV-3:
  the diff against `b856a97` over `distribution migration scripts
  .claude/commands .github/workflows/workflow-conformance.yml` is empty and
  `workflow-manager verify .` matches workflow 2.6.0.

### CP3 -- newest-release selection in the runner (complete)

- `tests/parallel/cli.py`: `--newest-release-only` for the run, `--list`
  and `--plan-only` modes; with `--select` or `--fast` it is a usage error,
  exit 2, refused from argv before the run lock. Every other mode refuses
  it through the existing per-mode option check.
- `tests/parallel/inventory.py`: `newest_release` (the highest `CI_SUITES`
  version by numeric order), the `NEWEST_RELEASE` spec, and
  `Selection.kind` (`full`, `targeted` or `newest-release`, derived from
  the flags and kept outside `to_json`, so `selection_digest` is unchanged).
  The selection is every host unit except the other releases' matrix host
  classes, plus the newest release's frozen units. `partial_frozen` is
  false, and phase B is the newest release's three matrix classes. A
  hand-built `Selection` defaults to `targeted`, the least it can claim
  (INV-4). The executor passes the spec through unchanged, so
  `executor.py` did not change.
- `tests/parallel/planner.py`: the plan's new `selection_kind`.
  `tests/parallel/report.py`: the evidence label keeps set equality, and
  adds `newest-release` for a newest-release plan that is not full by it.
- Every stopgap block opens with a line-leading `# STOPGAP(M2)` comment
  that points to `docs/ARCHITECTURE.md`'s "Stopgap test profile" (CP7
  writes that subsection).
- Live `--list --newest-release-only` at this checkpoint: 1088 units (155
  host + 3 x 311 frozen `2.6.0`), the plan's 1069 at the base plus the 19
  host classes CP1 and CP2 added. The full `--list` is 4061.
- Verification: `run_all.py --select test_stopgap_profile.py`: 6/6 units,
  14 tests OK, covering every item of the plan's CP3 test list. INV-2 is
  proved against the base runner itself: the base commit's
  `tests/parallel/` (`git archive b856a97`) selects byte-identical
  `to_json`, and the same `selection_digest`, over the live and a
  synthetic inventory. The real subprocess run uses a scratch checkout of
  releases `0.0.1`, `0.0.9` and `0.0.10`, where `0.0.10` must win. The
  regression run, `--select` of `test_parallel_runner.py`,
  `test_release_versioning.py`, `test_manager_version.py` and
  `test_stopgap_profile.py`, passed with 79/79 units and 323 tests OK. INV-1/INV-3: the diff against `b856a97`
  over `distribution migration scripts .claude/commands
  .github/workflows/workflow-conformance.yml` is empty.

### CP4 -- pull-request profile chooser (complete)

- `tools/ci/choose_profile.py` (new, stdlib): writes `profile=full` or
  `profile=newest-release` to `$GITHUB_OUTPUT` and a reasons table to
  `$GITHUB_STEP_SUMMARY` (stdout when unset). Any event but `pull_request`
  is `full` and reads nothing. Rule 1: the paths of `git diff --name-only
  --no-renames -z HEAD^1 HEAD` (both sides of a rename, deletions too),
  where `HEAD` must be a two-parent merge; each is classified by the
  longest matching rule, and an unmatched path is `full`. Rule 5, read
  only when no path already needs `full`: the newest (highest run id)
  `push` or `schedule` run in the `gh api` run list of
  `workflow-manager-verify.yml` on `main` must be `completed`/`success`.
  A git, API, parse or rule-file failure is `full` (INV-4). The table
  lists every path that chose `full` and caps the rest at 300 rows.
- `tools/ci/pr_profile_paths.json` (new): the plan 6.2 table as exact
  paths and `/`-ending prefixes, including an exact rule for each of the 14
  host test modules (CP1-CP3's three among them); its `"_comment"` starts
  with `STOPGAP(M2)`. The rule file is validated on load (known profile, a
  reason, relative path, no duplicates).
- `tools/ci/nightly_alarm.py` (new): `decide(event, result, open_issues,
  run_url)` is pure. A red `schedule` run ensures the `nightly-red` label
  (`gh label create --force`), then comments on the oldest open issue or
  opens "Nightly full verification failed". A green one closes every open
  `nightly-red` issue with a comment. Any other event does nothing. An
  unreadable issue list counts as none, so a red nightly still opens an
  issue. A failed `gh` action exits 1.
- `tools/ci/__init__.py` (new): a one-line docstring; it names no stopgap
  identifier. The three other files open with the `STOPGAP(M2)` marker.
- Verification: `run_all.py --select test_stopgap_profile.py`: 13/13
  units, 45 tests OK (31 new, covering every item of the plan's CP4 test
  list: completeness over the live tree, tracked and untracked, plus a
  scratch repository where a new untracked test module is unclassified and
  an ignored file is not listed; real merges for the rename, deletion,
  non-merge and git-failure cases; `main` health from injected JSON; the
  output format; the alarm's decision table and its `gh` shell with `_gh`
  patched). INV-1/INV-3: the diff against `b856a97` over `distribution
  migration scripts .claude/commands
  .github/workflows/workflow-conformance.yml` is empty, and
  `workflow-manager verify .` matches workflow 2.6.0. As for CP1-CP3, the
  full gate was not run at this checkpoint: under the Controller it leaks
  git zombies (about 1200 already held by this lane's Controller).

### CP5 -- workflows and settings data (complete)

- `.github/workflows/workflow-manager-verify.yml` (changed): a `schedule`
  trigger (`17 3 * * *`, the nightly full run); the concurrency group
  `workflow-manager-verify-<event>-<ref for a pull request, else sha>`,
  cancelled for pull requests only, so no `main` push, nightly or dispatch
  run is ever cancelled. The `plan` job holds `contents: read, actions:
  read`, runs `choose_profile.py` (step `profile`) before planning, passes
  `--newest-release-only` only through `NEWEST`, set from that step's
  output, and exports `profile`. A new `package` job runs `package.py
  --version 0.0.0+ci --manager-root $GITHUB_WORKSPACE` after installing
  `.github/tools/requirements.txt`. `aggregate` needs `[plan, shard,
  package]` and its first step (`id: needs`) fails naming the plan or
  package job's non-success result. A new `nightly-alarm` job (`needs:
  aggregate`, `if: always() && github.event_name == 'schedule'`,
  `contents: read, issues: write`) runs `nightly_alarm.py`. The profile
  step, the `NEWEST` wiring and the alarm job carry `# STOPGAP(M2)`.
- `.github/workflows/pr-title.yml` (new): `name: PR title`, `pull_request`
  types `opened, edited, reopened, synchronize`, one job `Conventional
  Commit title` running `release.py check-title "$TITLE"` with the title in
  `env`.
- `.github/workflows/release.yml` (new), plan 5.4: `workflow_run` of
  "Workflow manager verification", `completed`, `main`; the job requires a
  `push` run concluded `success`, holds `contents: write, actions: read`
  and the job-level group `workflow-manager-release` without cancellation.
  Steps: checkout of `main` (full history), `resolve-target` into
  `$GITHUB_OUTPUT`, checkout of the target (full history), Python 3.12, the
  pinned upstream fetch, the `plan` artifact downloaded from the target's
  run, `assert-full-plan`, `next-version` (empty: a notice, then every
  later step is skipped), `assert-not-superseded` (exit 3: a notice and
  `superseded=true`), `package.py --version X.Y.Z`, and `gh release create
  vX.Y.Z --target $TARGET_SHA --generate-notes` with notes saying the
  release holds no Workflow release and which releases `distribution/`
  holds.
- `.github/repository/ruleset-main.json` and `merge-settings.json` (new):
  the ruleset API payload (`~DEFAULT_BRANCH`; `deletion`,
  `non_fast_forward`, `required_linear_history`; `pull_request` with 0
  approvals and squash only; required checks `aggregate` and `Conventional
  Commit title` from app 15368, `strict: false`; no bypass actors) and the
  repository `PATCH` payload (squash only, `PR_TITLE`/`BLANK`, auto-merge,
  delete branch on merge). No setting was applied: that is the user's
  cutover (plan section 9).
- `tools/release/release.py assert-full-plan PLAN [--repo-dir DIR]`: loads
  the plan with the checkout's own runner (`planner.load_plan`: its
  `plan_digest`, this tree's `tree_digest`, its partition), rediscovers the
  inventory there (`inventory.discover`), and requires `selection_kind ==
  "full"`, the same `tree_digest`, and a selection equal to the inventory
  with no partial class. Any refusal exits 1.
- `tools/ci/pr_profile_paths.json`: an exact `newest-release` rule for
  `tests/test_release_workflows.py`.
- Tests: `tests/test_release_workflows.py` (new, 19 tests): T-REL-1
  (structure plus 12 mutations, and the `resolve-target` output format the
  later steps read), T-PRT-1 (structure, and the real step run with a
  title that would inject if interpolated), T-SET-1, and the permanent
  `assert-full-plan` cases over real scratch-checkout `--plan-only`
  output: a full plan passes; a targeted plan, a `--select` covering the
  whole inventory, another tree's plan and a tampered plan are refused;
  a `full` label omitting a unit, adding one, or selecting a class
  partially is refused. `tests/test_parallel_runner.py`: T-CI-1 updated
  (triggers, schedule, the exact group, `package` among the jobs and
  `aggregate`'s needs, five new mutations) and T-CI-7 (new: the `needs`
  step run for real over every result pair, and the `package` job).
  T-CI-2 supplies the new `NEWEST` step variable. `tests/test_stopgap_profile.py`:
  T-CI-6 (wiring, the real profile step choosing `full` for `push`, and the
  real plan step producing `full`/`newest-release` from `NEWEST` in a
  scratch clone), T-CI-8, and the stopgap `assert-full-plan` cases (a
  three-release newest-release plan is refused while the full one passes;
  over one release the newest-release selection equals the full one and is
  still refused). No permanent module names a stopgap identifier.
- Fixed on the way: CP4's `tests/test_stopgap_profile.py` tripped the
  runner's static write lint (`TestStaticLint`) in four places, all false
  positives of its flow-insensitive rootedness (a `path` bound to
  `REPO_ROOT` in `_load_tool` made every `path.write_text` look like a write
  under the checkout, and a literal `tools/migrate.py` read as a tool run
  without `--check`). Renamed the binding and used another `tools/` path in
  the classification case; no behaviour changed. CP4's targeted run could
  not see it, because the lint test lives in `test_parallel_runner.py`.
- Verification: `run_all.py --select` over `test_parallel_runner.py`,
  `test_stopgap_profile.py`, `test_release_workflows.py`,
  `test_release_versioning.py` and `test_manager_version.py`: every module
  green except the lint case above, which is green after the fix
  (`TestStaticLint` 3/3 and `test_stopgap_profile.py` 53/53 re-run).
  INV-1/INV-3: the diff against `b856a97` over `distribution migration
  scripts .claude/commands .github/workflows/workflow-conformance.yml` is
  empty, and `workflow-manager verify .` matches workflow 2.6.0. As for
  CP1-CP4, the full gate was not run at this checkpoint, because of the
  Controller's git-zombie leak (about 3500 held by this lane's Controller
  after these runs). The workflows themselves first run on GitHub at the
  cutover (C0).

### CP6 -- squash-merge compatibility (complete)

Plan section 7. The stop rule did not fire: no part found a reader that
fails once a completed item's commits are unreachable.

- **Static audit** (part 1), of every git history or object read in the
  installed `scripts/workflow_state.py` (WS) and
  `scripts/workflow_fingerprint.py` (FP). The conclusion goes into
  `docs/ARCHITECTURE.md` in CP7.

  | Reader | git ops | Where | Class |
  | --- | --- | --- | --- |
  | Trailer walkers (`_discover_trailer_commits` and its `discover_*_commits`, `_commit_trailers`) | `log base..head`, `interpret-trailers` | WS:1832-1927 | branch-local, runs before the merge |
  | `_is_ancestor` (entry reachability, amendment request, record intervals, obligations) | `merge-base --is-ancestor` | WS:2054 | branch-local |
  | Plan-approval transaction and commit verification (`_read_committed_bytes`, `assert_committed_path_set_matches`, journal and index checks) | `show`, `diff-tree`, `cat-file`, `rev-parse`, `diff --cached` | WS:2321-4017 | branch-local |
  | `load_pre_amendment_snapshot` | `ls-tree`, `cat-file` of the active item's `pre_amendment_approval_commit` | WS:2092-2107 | branch-local (only for an item in `AMENDING_PLAN`) |
  | Generation-record chain, provenance interval and recovery, technical-approval commit validation | `diff`, `rev-parse`, `show <c>:STATE` | WS:9066, 13939-14643 | branch-local |
  | Completion obligations (`resolve_completion_obligations` from `complete_work_item`) | `ls-tree`, `cat-file`, `show` | WS:10572-12501 | branch-local (runs once, at acceptance) |
  | FP `resolve_base`, `_read_bytes_at_source`, `_path_exists_at_source`, `_snapshot_commit`, changed-path diffs | `rev-parse`, `show`, `cat-file -e`, `ls-tree`, `diff` | FP:648-886, 1527 | branch-local (the active item's own commits) |
  | `origination_reference_commits`, `_checkpoint_status_at_commit`, `_identity_query_at_commit` | `rev-list --all --full-history -- STATE`, `ls-tree`, `cat-file` | WS:4982-5030, 8603 | reads state content |
  | `find_latest_activation_event` (`load_config` fallback only) | `log --first-parent HEAD` | WS:1850 | reads state content (reachable history, no recorded SHA) |
  | `_committed_blob`/`_rev_sha` (amendment witness, lifecycle views of worktree and branch tips) | `rev-parse --verify`, `cat-file` | WS:6935-6952 | legacy/cross-worktree only |
  | `_resolving_commits_trailers` | `rev-list HEAD -- STATE`, `log -1` | WS:7248 | legacy/cross-worktree only |
  | `verify_legacy_branch_reconciliation` (`promote_legacy_work_item`) | `merge-base`, `show` | WS:16049-16075 | legacy/cross-worktree only |

  No reader resolves a SHA that a completed item records. Every reader
  that resolves a recorded SHA gets it from the one active item the command
  names. The loops over every `work_items` entry, terminal ones included,
  are structural. The one that touches git (`validate_state(repo_root=)`,
  WS:16508) runs `ls-files` on each item's `registry_path` in the working
  tree, which the squash keeps. `workflow-manager verify` reads no history.
  The history-wide readers only enumerate reachable commits. The squash
  commit carries the terminal item's final state, so its id stays observed
  and reuse is refused (`route_work_item` raises
  `WorkItemTerminalReuseError` first).

  Two notes, neither a defect of squash merging a completed item:
  - Calling `implementing_entry_reachable` or `complete_work_item` on an
    already-completed item would fail closed (False, `VERIFIER_UNRESOLVABLE`
    or a raise), never silently. No command does this.
  - `verify_legacy_branch_reconciliation` requires a `LEGACY_READY` item's
    `reviewed_content_commit` to be an ancestor of `HEAD`, so a legacy
    branch integrated by squash could never be promoted. That is the
    dormant `D-Legacy` import path. This repository has no `LEGACY_READY`
    item, and all five completed items are `MILESTONE_COMPLETE`.
- **Disposable-repository test** (part 2),
  `tests/test_squash_merge_compat.py` (new, stdlib, history-independent, 4
  tests, about 3 s). It bootstraps `2.6.0` into a disposable repository and
  drives `sq-item` to `MILESTONE_COMPLETE` on `milestone/sq-item`. The
  drivers are the installed release's own acceptance-matrix harness, run
  in subprocesses through `test_workflow_2_6_0_hardening_disposable_repo`'s
  `drive()`. The branch is then squashed onto `main` with a blank body,
  the branch deleted, the reflog expired and the objects pruned with `gc
  --prune=now`. A `--no-local` clone is taken as well. The test asserts:
  - the branch carried `Workflow-Checkpoint`/`Workflow-Work-Item`
    trailers, while the squash commit has none, one parent and the
    branch's tree;
  - every branch commit the item records is gone in both checkouts: the
    plan-approval commit (CP1's `start_commit`) and
    `reviewed_implementation_head`/`reviewed_content_commit`.

  Then, in both the pruned repository and the clone:
  - `validate_state(repo_root=)` passes;
  - re-routing `sq-item` raises `WorkItemTerminalReuseError`;
  - a new item routes and reaches `plan_review_publication_status`
    `BOUND`, is plan-approved (`IMPLEMENTING`) and completes CP1
    (`SELF_REVIEWING_IMPLEMENTATION`);
  - `workflow-manager verify` matches workflow 2.6.0.

  The disposable item is governed by `"2.1"` (the template's default).
  Part 3 covers `"2.2"`.
- **Scratch-clone check** (part 3), one-off, not committed. The check was
  done in a `--no-local` clone of this repository:
  - a squash commit of `c1647c3`'s tree was made on parent `db4c7af` with
    the blank-body title `feat: adaptive test sharding (#1)`;
  - every ref but `refs/heads/main` was deleted, including `origin`, the
    tags and the other branches;
  - the reflog was expired and the objects pruned.

  All 8 branch commits that `workflow-manager-adaptive-test-sharding`
  records were then unreachable: the CP1-CP7 `start_commit`s `97ca7a0`,
  `cc1d6c3`, `ac9e7b6`, `ff5d383`, `2dc17e1`, `534174c` and `9774721`, and
  `reviewed_implementation_head` = `technical_approval.reviewed_content_commit`
  `de833c8`. Only `base_commit` `db4c7af` stayed reachable. There was no
  trailer in `db4c7af..main`. The tree was identical to `c1647c3`'s.

  At `c1647c3`, Workflow `2.5.1` was installed; `2.6.0` came in `0ac857b`.
  So the assertions ran in two arms:
  - with the tree's own `2.5.1`;
  - after `workflow_manager update` to `2.6.0` in a second such clone
    (`drift` `[]`, committed).

  In both arms:
  - the state validated, with the item `MILESTONE_COMPLETE` and no active
    item;
  - re-routing the item raised `WorkItemTerminalReuseError`;
  - a new item, governed by `"2.2"` (the activated default), reached
    `AWAITING_PLAN_APPROVAL` after both plan reviews (`BOUND` publication
    status under `2.6.0`), was approved (`IMPLEMENTING`) and completed CP1
    (`SELF_REVIEWING_IMPLEMENTATION`);
  - `workflow-manager verify` printed `installation matches workflow 2.5.1`
    or `2.6.0` respectively, before and after.
- `tools/ci/pr_profile_paths.json`: an exact `newest-release` rule for the
  new module. `tests/test_stopgap_profile.py` lists it among this
  milestone's modules.
- Verification: `run_all.py --select test_squash_merge_compat.py --select
  test_stopgap_profile.py --select test_parallel_runner.py::TestStaticLint`
  gave 18/18 units, 60 tests, exit 0. INV-1/INV-3: the diff against
  `b856a97` over `distribution migration scripts .claude/commands
  .github/workflows/workflow-conformance.yml` is empty (the only diff
  under `src/` is CP2's `cli.py`), and `workflow-manager verify .` matches
  workflow 2.6.0. As for CP1-CP5, the full gate was not run at this
  checkpoint.

### CP7 -- documentation, gate policy, removal record, cutover runbook (complete)

- `docs/ARCHITECTURE.md`:
  - "Verification execution": the opening names the one reduced gate; the
    CI paragraph now covers the nightly trigger, the profiles, the one
    required test check (`aggregate`, now also needing `package`), the
    `package` job, the per-commit concurrency and the release; plan 6.6's
    policy text is applied verbatim as "One reduced selection is a gate, in
    one place"; the serial-runs policy names the pull-request profile;
  - "Stopgap test profile" (new subsection): the chooser's rules, where
    the other rules are enforced, the marker's two forms, the list of the
    eight marked files between `stopgap-marked-files` comments, and what M2
    deletes (the four stopgap files whole, the marked blocks elsewhere, the
    policy exception and the subsection);
  - "Squash merges and the installed Workflow" (new section): CP6's
    conclusion, the test, the one-off check, and the two limits;
  - the layout lists `tools/release/`, `tools/ci/`, `.github/` and
    `docs/RELEASING.md`.
- `docs/RELEASING.md` (new): how a release happens and the impact table,
  the first release (`v1.1.0` over the `1.0.0` baseline at `b856a97`),
  fix-forward, catch-up, re-running a failed release, the stranded-release
  recovery (5.4's residual), installing and verifying `SHA256SUMS`, `pipx
  reinstall workflow-manager`, the settings and ruleset `gh api` commands,
  the 60-day schedule caveat, the C1 alignment note, and the section 9
  cutover runbook (C0-C6) with its `git push`/`gh pr create`/`gh pr
  checks` commands.
- `README.md`: verification, nightly (`event=schedule`) and release badges;
  an "Install" section (a checkout at a tag, or the wheel with
  `--manager-root`); the CI profile note; `RELEASING.md` in the reading
  order.
- `CLAUDE.md`, below the managed marker only: "Before changing anything"
  states the gate policy and the path-rule obligation; a new "Branches,
  pull requests and releases" section; `RELEASING.md` in "Where things
  are". `workflow-manager verify .` still matches workflow 2.6.0.
- `docs/ROADMAP.md`: 10.1's status (in progress, all checkpoints
  implemented), the `OD-4` Controller-policy follow-up, and 10.2's pointer
  to the "Stopgap test profile" subsection.
- `tests/test_stopgap_profile.py`: the marker-set tests (plan 6.7).
  `TestTheMarkedFilesAreRecorded`: the marked files of the scanned set
  (tree paths, tracked and untracked, minus `docs/` and `*.md`) equal the
  documented list; every file naming a stopgap identifier is marked; the
  policy exception and subsection are present.
  `TestWhatCountsAsAMarker`: the admitted forms; an inline string, a
  trailing comment, a multiline-string line, a docstring, a YAML string, a
  non-`_comment` JSON value and a non-code file are not markers; a
  scratch repository's `docs/` and `*.md` files are never scanned, while an
  unmarked or untracked code file naming an identifier is caught; the list
  is read only between its comments. Checked by mutation outside the suite:
  dropping `tests/parallel/report.py`'s marker unmarks it.
- Verification: `run_all.py --select test_stopgap_profile.py --select
  test_parallel_runner.py::TestStaticLint --select
  test_parallel_runner.py::TestSerialEvidencePolicyIsDocumented --select
  test_release_workflows.py`: 25/25 units, 84 tests, exit 0. INV-1/INV-3:
  the diff against `b856a97` over `distribution migration scripts
  .claude/commands .github/workflows/workflow-conformance.yml` is empty,
  and `workflow-manager verify .` matches workflow 2.6.0. No CI evidence at
  this checkpoint: the draft pull request's runs (C0) are the user's and
  belong to the functional review. As for CP1-CP6, the full gate was not
  run at this checkpoint; it runs at the wrap-up.

### Self-review of the milestone diff and the full gate (`SELF_REVIEWING_IMPLEMENTATION`)

- `enter_self_reviewing_implementation` was a no-op. CP7's
  `complete_checkpoint` had already written the phase.
- The whole `b856a97..cbbbffa` diff was reviewed:
  - `tools/release/`: the title grammar, `next-version`,
    `resolve-target`, `assert-full-plan`, `set-version` and `package.py`;
  - `tools/ci/`: the chooser, the path rules and the alarm;
  - the runner's `--newest-release-only` and `selection_kind`;
  - `cli.py`'s `--version` and the missing-`distribution/` hint;
  - the three workflows and the settings data;
  - the new test modules, and the docs.
- No finding was blocking or important, and nothing was changed.
- The review checked each fail-safe path against INV-4: an API, git or
  parse failure is `full` in the chooser, and a fallback or a refusal in
  the release. It also checked that the release never trusts the plan's
  own inventory, and that the workflows pass the title, SHAs and results
  through `env`, never through script interpolation.
- INV-1/INV-3: `git diff --stat b856a97 HEAD -- distribution migration
  scripts .claude .github/workflows/workflow-conformance.yml` is empty.
  `CLAUDE.md` changes only below the managed marker. `workflow-manager
  verify .` prints `installation matches workflow 2.6.0`.
- **The full gate**, the first of this milestone (none ran at CP1-CP7,
  because of the Controller's git-zombie leak), was `python3
  tests/run_all.py` at `cbbbffa`, 2026-09-29 11:38-11:45 (439 s wall, 8
  workers):
  - `evidence: full selection, local, 8 worker(s), head cbbbffad4b76f7c3f22ecfc6db8c559ec8ff5b94,
    4086/4086 units, 25620 tests, selection_digest
    1f9d81d3b17fa1a1726a3205cb784f2ae2fb9664dd9b0263a2b2ef4bbe178469,
    tests_digest 66af7ecc9edd2d726e0665fee05f18d940496e697836ae85a9415e990bbc58ba,
    tree_digest 61123d7437d37c3c735dd192ba5439e1fc0ac8ceda1520109b0ef7c095f5d8a8`,
    `verdict: exit 0`;
  - every host module was OK;
  - the only non-zero frozen chunks were the four documented `2.3.1`/`2.4.0`
    `workflow_integration_test.py` portability exceptions
    (`TestRetiredScopedRemediationLeavesNoLiveSurface`), which phase B
    judged as expected.
- The base had 4042 units. The 44 more are this milestone's new host
  classes (INV-2).
- The run was under this lane's Controller, with the one-step workaround.
  Afterwards the Controller held 49 zombies.

### Implementation review round 1 and its application (`APPLYING_REVIEW_FEEDBACK`)

- `LOCAL_MODEL_IMPLEMENTATION_REVIEW` round 1: `APPROVE`. The
  `MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW` round 1: `REVISE`, for bundle
  `7841f8e3...`, with no blocking finding and one important finding.
  `b9e0e0f` commits that review's phase write alone.
- **I1, accepted and fixed in `ed39920`.** M2's documented removal broke
  the runner. Reproduced: `report.py` imported `NEWEST_RELEASE_KIND`
  outside a marked block, and `cli.py`'s `ALLOWED`/`_DEFAULTS` named
  `newest_release_only` unmarked. Every dependent reference now sits in a
  marked block, including the help text and the comments naming the
  selection kind, so `tests/parallel/planner.py` joins the marked-file
  list. `TestTheRemovalRecordIsComplete` carries the removal out on a
  scratch checkout. No file under `tests/parallel/` may still name a
  stopgap identifier, and `--help`, `--list`, `--plan-only` and a real run
  must succeed. It failed before the fix, naming the leftovers in
  `cli.py`, `inventory.py`, `planner.py` and `report.py`.
- **Optional, applied.** The reference scan now also covers
  `newest-release`, `NEWEST_RELEASE` and `nightly-red`.
- **Optional, not applied (apparatus).** CP1-CP7 each cited targeted runs
  only. That is recorded above and cannot be repaired after the fact. The
  full gates at `cbbbffa` and `ed39920` cover the final code.
- **The full gate at the fix:** `python3 tests/run_all.py` at `ed39920`
  (388 s wall, 8 workers):
  - `evidence: full selection, local, 8 worker(s), head ed39920907a494eb2e63d39ffe2607d19327e0b1,
    4088/4088 units, 25624 tests, selection_digest
    f34791a5163c3e3093ba2f3259d8814bacafe7139831397a8c63df03aed01d34,
    tests_digest 35bbf0a847683b7d550fe41f26021509e3dab0b7e9323aa9adced0c10cc9a09e,
    tree_digest 64a850b3ea1d64f1e98f24946c576b7ca974ff2e48a19efab4e69f70e9cb450f`,
    `verdict: exit 0`;
  - the only non-zero frozen chunks were the same four documented
    `2.3.1`/`2.4.0` `workflow_integration_test.py` portability exceptions;
  - the two more units are the two new host classes.

## Functional review checklist

You are testing the trunk model as the repository owner uses it: titles,
versions, the release package, the reduced pull-request profile, and the
first pull request (cutover steps C0-C1, `docs/RELEASING.md`).
- **Technical approval:** commit `7995695`, implementation revision 2.
- **Where findings go:**
  `.ai-review/workflow-manager-trunk-model/feedback/FUNCTIONAL_REVIEW.md`.
- **Automated verification:** already current. The full gate passed at
  `ed39920` (4088/4088 units, 25,624 tests, `tests_digest 35bbf0a8...`).
  Only docs and state commits have landed since.

**Setup.**
- Python 3.12 or later, `git`, and an authenticated `gh` (flows 7-8 only).
- Run flows 1, 4 and 5 in this checkout, with a clean working tree. Run
  flows 2, 3 and 6 in a throwaway clone, so that no tag or scratch commit
  touches this repository:

```bash
export M=~/Workspace/workflow-manager
export T=$(mktemp -d) && git clone -q "$M" "$T/c"
```

**Test data.** None. Flow 2 creates a scratch squash commit and a tag in
the clone only.

**Flows.**

1. **Title check.** In `$M`:
   - `python3 tools/release/release.py check-title "feat: x"` prints
     `valid title: feat, release impact minor`, exit 0;
   - `"fix(cli): y"` gives impact `patch`, `"feat!: z"` gives `major`, and
     `"docs: d"` gives `none`;
   - `"Update things"` prints `invalid title: no 'type: description'
     shape` with the expected grammar and the type list, exit 1.
2. **The first release's version, simulated (C4-C5's version step).** In
   the clone:

   ```bash
   cd "$T/c" && git checkout -q -b sim b856a97
   git merge -q --squash milestone/workflow-manager-trunk-model
   git -c user.email=a@b -c user.name=t commit -q \
     -m "feat: trunk model, Manager releases and the stopgap PR test profile"
   python3 tools/release/release.py next-version --repo-dir .
   ```

   Expected: `1.1.0` (the recorded baseline `1.0.0` at `b856a97`, plus a
   `feat`), exit 0.
3. **`--version`.** Still in the clone, after flow 2:
   - `git tag v1.1.0 && PYTHONPATH=src python3 -m workflow_manager
     --version` prints `workflow-manager 1.1.0 (checkout at v1.1.0)`;
   - after `echo x >> README.md`, the same command prints
     `workflow-manager development build (v1.1.0-dirty)`. Undo it with
     `git checkout README.md`.
   - In `$M` (no strict tag yet), it prints `workflow-manager development
     build (...)`. The pipx-installed `workflow-manager` still prints
     `1.0.0` until it is reinstalled (`pipx reinstall workflow-manager`);
     that is expected, not a finding.
4. **The reduced pull-request selection.** In `$M`:
   - `python3 tests/run_all.py --list --newest-release-only | grep -c :`
     prints `1115`; the full `--list` prints `4088`;
   - the reduced list's only frozen release is `frozen:2.6.0`
     (`... | grep -o '^frozen:[0-9.]*' | sort -u`).
5. **The profile chooser, locally.** In `$M`:
   `GITHUB_OUTPUT=$T/out GITHUB_STEP_SUMMARY=/dev/null python3
   tools/ci/choose_profile.py --event push --repo-dir .` prints
   `profile: full`, and `$T/out` holds `profile=full`. Any non-PR event
   is always `full`.
6. **The release package.** Needs Python's `build` module, which CI
   installs:

   ```bash
   python3 -m venv "$T/v" && "$T/v/bin/pip" install -q build
   "$T/v/bin/python" "$M/tools/release/package.py" --version 1.1.0 --out "$T/assets"
   (cd "$T/assets" && sha256sum -c SHA256SUMS)
   ```

   Expected: exit 0; `$T/assets` holds `workflow_manager-1.1.0-py3-none-any.whl`,
   `workflow_manager-1.1.0.tar.gz` and `SHA256SUMS`; both files print
   `OK`. `git -C "$M" status` stays clean.
7. **C0: the milestone's pull request (your action).** Push the branch and
   open the draft pull request, with the commands in `docs/RELEASING.md`'s
   "Cutover" step 1. Expected on its checks (`gh pr checks <n>`):
   - `Conventional Commit title` green, and its summary says impact
     `minor`;
   - the verification `plan` job chooses `full` (the PR touches
     `.github/`, `src/`, `tools/` and `tests/parallel/`), and its summary
     table gives the reasons;
   - `package` and `aggregate` green.

   Record the run URLs in this file.

   **Recorded (2026-09-29).** Draft pull request
   [#4](https://github.com/RodrigoFAbreu/workflow-manager/pull/4) at
   `6ca29d4`:
   - `Conventional Commit title` green
     ([run 36566238193](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36566238193));
   - verification
     ([run 36566238056](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36566238056),
     `success`): `plan` chose `full` (16 shards, 309 phase-A chunks, 15
     phase-B units), and `package` and `aggregate` are green.
8. **C1: probes (your action).** Throwaway draft pull requests against
   `milestone/workflow-manager-trunk-model`, closed unmerged:
   - a docs-only change chooses `newest-release`;
   - a change under `src/` chooses `full`;
   - the title `Update things` fails the title check;
   - a `docs: ...` title passes it with impact `none`.

   **Recorded (2026-09-29).** Probes #5-#8, opened 12:13 and closed
   unmerged at 12:18 UTC. Closing them cancelled their remaining
   verification jobs, so those jobs show as failed without having failed a
   test.
   - #5 `docs: probe the newest-release profile`: `plan` chose
     `newest-release`
     ([run 36566708849](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36566708849)).
   - #6 `chore: probe the full profile`: `plan` chose `full`
     ([run 36566717357](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36566717357)).
     Its inventory and `package` then failed on the probe's own edit, an
     HTML comment written into a `.py` file under `src/`. That breakage is
     the probe's, not the profile's.
   - #7 `Update things`: the title check failed
     ([run 36566723520](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36566723520)).
   - #8 `docs: probe the title check`: the title check passed
     ([run 36566731686](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36566731686)).

**Known limitations (out of scope here).**
- The ruleset, the merge settings, the squash merge and the first real
  release (C2-C5) happen only after `/accept-milestone`, because
  acceptance precedes the merge. C5 is recorded here when it happens.
- A wheel needs `--manager-root` or a checkout until M2 bundles
  `distribution/`.
- The Workflow Controller still titles its pull requests with the bare
  work-item id (`OD-4`); this repository sets no Controller policy until
  the Controller's C1 release.
- A pull request whose reduced run passed is not re-run when `main` later
  turns red (plan 6.2); `main`'s own full run and the release gate cover
  it.

## Previous milestone

**Complete.** `workflow-manager-adaptive-test-sharding`
(`governing_workflow_version: "2.2"`, `process`, plan revision 7 approved
2026-09-26, base `db4c7af`): adaptive, duration-balanced parallel execution
of this repository's own verification suite (`tests/`), with no coverage
change. Full plan:
`docs/ai-workflow/WORKFLOW_MANAGER_ADAPTIVE_TEST_SHARDING_PLAN.md`.
Measured baseline: full serial verification 2162 s (36.0 min) at `db4c7af`.

## Current checkpoint

**Milestone complete.** `workflow-manager-adaptive-test-sharding` reached
`MILESTONE_COMPLETE` through `/accept-milestone` on 2026-09-27, with the
user's confirmation, and `active_work_item_id` is cleared.
- **Checkpoints:** CP1-CP7 are complete.
- **Technical approval:** commit `ff7a936`, on basis `EXTERNAL_APPROVE`,
  for bundle `17c8e92c...`. Both review stages approved: the local review
  in its round 2, and the manual external review in its round 1.
- **Accepted deviations:** the user confirmed P-2 and P-5 CI at
  `/approve-review implementation`. P-3 is documented-unreachable under its
  own clause.
- **Functional review:** clean, with no findings, against the checklist
  below (evidence commit `a16c4d2`). Claude ran all seven flows at the
  user's request.

The checkpoint log below is this milestone's permanent record.

## Current blockers

None. The open follow-ups are listed in `docs/ROADMAP.md`'s "Repository
tooling: adaptive test sharding" entry:
- a per-commit CI concurrency group for `main`;
- two optional runner-hardening items;
- the 5-minute CI target, blocked by the 20-job cap.

## Active plan

None, because the milestone is complete. The plan document stays at
`docs/ai-workflow/WORKFLOW_MANAGER_ADAPTIVE_TEST_SHARDING_PLAN.md`
(revision 7, plan approval `CURRENT`) instead of being archived.
`docs/ARCHITECTURE.md`'s "Verification execution" cites it as the design
record.

## Next action

`workflow-manager-adaptive-test-sharding` is complete. Next, run
`/milestone-plan` for the next incomplete milestone in `docs/ROADMAP.md`.
Its suggested execution order marks it NEXT: section 1.9, "Small
Controller <-> released 2.6 integration", the first step toward the
Workflow Orchestration Protocol foundation.

## Checkpoint log

### CP1 -- inventory, selection grammar, tree identity, shared contracts, per-unit host execution (complete)

- `tests/parallel/` (new package): `inventory.py` (host discovery in a
  subprocess through `loadTestsFromModule`, unit ids
  `host:<module>.py::<Class>`, the five-form `--select` grammar with
  `SelectSyntaxError`/`UnknownSelectorError`; frozen forms parse but select
  nothing until CP2), `tree.py` (`tree_digest`, `snapshot`, `compare`; git
  runs with `GIT_OPTIONAL_LOCKS=0` so a digest never rewrites the index),
  `unit.py` (one host class or selected methods in its own process, result
  record written atomically; a unit that cannot load writes no record and
  is an infrastructure fault), `resources.json` + `resources.py`
  (`load(repo_root, host_unit_ids)`, `GUARDED_TREES`, every 5.8 refusal),
  `plan_schema.py` (`ChunkDescriptor`, `shard_chunks`; plan shape
  `plan["shards"][i]["chunks"]`, a descriptor's `shard_index` must equal
  its shard's position).
- `tests/run_all.py`: `sys.dont_write_bytecode` before any import;
  `--list`, `--select`, `--jobs 1` (interim direct mode, no lock or barrier,
  not INV-6's serial reference); `run_all: error[<Name>]:` refusal tag.
  The no-flag and `--fast` paths are unchanged apart from
  `test_parallel_runner.py` joining the full run (not `--fast`, so the
  eight-module `--fast` set that `D-Fast-Flag` names is unchanged).
- Discovery at `97ca7a0`: 94 host classes, 349 host tests, matching the
  plan's 3.2 audit.
- Verification: `python3 tests/test_parallel_runner.py` 41/41 OK (T-INV-1,
  -2, -4, -5 host parts; T-INV-8; tree and unit tests); seven hand
  mutations of the new modules all killed (two initially survived and
  their tests were tightened: stale-index write, executable bit);
  `run_all.py --jobs 1 --select test_parallel_runner.py` 8 units green;
  `--jobs 1` over the eight `--fast` modules 48 units green in 11.8 s;
  `run_all.py --fast` green. INV-5:
  `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
  empty. No `__pycache__` appeared under `tests/parallel/`.

### CP2 -- frozen-matrix decomposition (complete)

- `tests/support.py`: `run_suite(..., classes=())` appends class names to
  argv; nothing else changes.
- `tests/parallel/matrix.py` (new, data only): `FROZEN_MATRIX` (the 15
  matrix host classes -> `(version, fixture)`), `FIXTURES`, and a
  `CI_SUITES` view imported from `support`.
- `tests/parallel/inventory.py`: frozen discovery (`discover_frozen`, read
  inside its own subprocess from the pointed-at checkout; one child per
  release, cwd that release's `payload/scripts/`; `InventoryCountError`
  when a suite's total differs from its pin), frozen unit ids
  `frozen:<version>/<fixture>/<suite>.py::<Class>`, the two frozen
  `--select` forms, a matrix host class pulling in all of its frozen
  classes, and the "partial frozen selection" flag.
- `tests/frozen_runs.py` (new): `FrozenChunk`, `FrozenRecord`, `execute`
  (fresh repository per chunk; a raising builder yields a build-error
  record; a timeout yields a `timed_out` record), `MergeContext` (canonical
  `to_json`/`from_json`, validated partition), `merge` (structural checks
  only, every expected value from the context and the release manifest),
  `MergedResult` (`combine`/`from_single`, per-chunk attribution),
  `open_matrix_run` (direct mode when `WM_FROZEN_RECORDS` is unset; merged
  mode refuses a missing `WM_FROZEN_CONTEXT`, a missing context file, and
  a context for another tree), the full-state snapshot
  (`full_state`/`state_delta`/`classify_delta`, `FLOCK_TARGETS` with their
  2.6.0 source lines), and the `--evidence
  {merged,one-class,residue,compare}` driver.
- `tests/test_conformance_suite.py`, `tests/test_bootstrap_e2e.py`: the 15
  matrix classes' `setUpClass` goes through `open_matrix_run`; assertions
  read `MergedResult` fields. No assertion removed, no expected value
  changed. `bootstrapped` residue and drift are now measured after every
  suite invocation and unioned (5.5, "strictly more attribution").
- `tests/run_all.py`: `--jobs 1` runs frozen classes selected without their
  host class as one chunk per suite, without host assertions.
- Tests: `python3 tests/test_parallel_runner.py` 74/74 OK (T-INV-1..5 frozen
  parts, T-INV-3, T-INV-7, T-MRG-1..7).
- Evidence (`python3 tests/frozen_runs.py --evidence ... --out <scratch>`,
  one process per release x mode, then `--evidence compare`, exit 0):
  - **E-MRG-1** direct == merged over the fixed two-chunk chunking, for all
    15 release x fixture rows: identical per-suite `ran`, `failing` and
    pass/fail, and every host assertion passes in both modes.
  - **E-MRG-2** one class per chunk (223 / 233 / 265 / 266 / 311 chunks per
    fixture for 2.3.1 / 2.4.0 / 2.5.0 / 2.5.1 / 2.6.0): equal to direct for
    all 15 rows.
  - **E-MRG-3** full repository and git-dir state delta per suite, in
    today's sequential order, all 15 rows, run without
    `PYTHONDONTWRITEBYTECODE` (as direct mode runs): **no unclassified
    delta**. The only deltas are pre-classified bytecode caches:
    `scripts/__pycache__/workflow_state.cpython-314.pyc` (after
    `workflow_state_test.py`),
    `scripts/__pycache__/workflow_fingerprint.cpython-314.pyc` (after
    `workflow_fingerprint_test.py`) and, in 2.6.0 only,
    `scripts/__pycache__/workflow_acceptance_matrix_test.cpython-314.pyc`.
    No `flock` target, ref, config, worktree, hook or git-dir artifact
    delta appeared. Per 5.5's decision rule, the fresh-repository model
    (`D-Frozen-Run-Fresh-Repo`) loses nothing observable, and no
    `sequential-canary` is needed. A first E-MRG-3 pass run with
    `PYTHONDONTWRITEBYTECODE=1` saw zero deltas; it was re-run in the real
    environment for fidelity. E-MRG-1's direct leg also ran with bytecode
    writing off (the benign difference 5.5 notes).
  - The tree's status and `tree_digest` were identical before and after all
    evidence runs.
- `python3 tests/run_all.py` (direct mode, full selection): every module
  OK, exit 0 (`test_conformance_suite.py` 1444 s, `test_bootstrap_e2e.py`
  707 s, run concurrently with the E-MRG-3 re-run).
- INV-5:
  `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
  empty.

### CP3 -- timing history and planner (complete)

- `tests/parallel/timings.py` (new, 5.2): the `timings.json` format
  (`Timings`, `load`/`parse`: a missing, corrupt or wrong-schema file gives
  empty estimates plus one warning; each invalid value -- negative, NaN,
  over 24 h, a bool or string, `samples` outside 1..5 -- is dropped with a
  warning), `estimate_units` (5.2's new-unit order: measured, other profile
  x median profile ratio, median of the same module or
  `version/fixture/suite`, `default_unit_seconds`; orphaned entries inform
  nothing), `orphaned`, `drifted`, `Observation` (the history-line format;
  a `fixture` line is a group-overhead observation),
  `observations_from_record` (host `parallel.unit` records; frozen records
  give the group overhead as wall minus unittest's own `Ran ... in Xs`,
  and a one-class chunk also gives its class's time), `read_observations`,
  `update`, and `python3 -m parallel.timings --from ... --profile ...`,
  the fold CP5's `--update-timings` will wrap.
- `tests/parallel/planner.py` (new, 5.3/5.4/INV-1..3): `load_config`
  (`ConfigError`), `max_shards`/`shard_count`, `lpt`, `make_chunks` (a host
  class is one chunk; a frozen `(version, fixture, suite)` group over
  `split_threshold_ratio x target_shard_seconds` splits into
  `min(classes, k)` LPT chunks, each paying the group overhead once;
  `whole_groups` splits nothing), `build_plan` (phase A over `n` shards,
  exclusive chunks first in their shard; phase B -- selected matrix host
  classes -- over `n` workers locally or `phase_b_workers` in CI; the
  predicted makespan terms of 5.4 step 5 and their total; the
  critical-path warning; defaulted/orphaned/warning lists; `plan_digest`),
  `verify_partition` (`PartitionError`), `load_plan`
  (`PlanDigestMismatchError`, `TreeDigestMismatchError`, INV-1 re-check),
  and `plan_checkout` (the same over a checkout's own config, timings and
  resources). Chunks are written only through
  `plan_schema.ChunkDescriptor`; exclusivity comes only from a
  `resources.load` result.
- Three refinements the plan text does not spell out, none of which
  changes a contract: (1) LPT picks the smallest `(load, chunk count,
  index)` -- the count only breaks exact load ties, so zero-estimate
  chunks never leave a shard empty (the 4/3 bound holds for any
  tie-break); (2) only the median and sample count are stored, so `update`
  lets the stored estimate stand in for its own samples as the oldest
  values when fewer than 5 new ones exist, and a fixture's group overhead
  is the median of all new overhead observations (0.01 s); (3) `drifted`
  ignores differences under 1 s, so sub-second classes do not drift on
  every run (drift stays advisory).
- `tests/parallel/config.json`: the initial 5.3 bounds (target 240 s,
  min 2, local max 8, CI max 16, default unit 30 s, default group overhead
  0.5 s, split ratio 0.5, CI account job limit 20).
- `tests/parallel/timings.json`, seeded by the committed tooling:
  `python3 -m parallel.timings --profile local --from <CP2 E-MRG-2
  one-class records> --from <host run>`. 3890 frozen classes (the four
  documented portability-exception classes fail and fall back to their
  suite median) from CP2's E-MRG-2 records, and 105 non-matrix host classes
  from one serial `parallel.unit` pass over `ac9e7b6` plus CP3's tree (the
  two CP3 test classes that needed this file failed in that pass and use
  their module median). Group overhead: conformance 0.28 s, target
  0.36 s, bootstrapped 0.38 s. **Not tuned:** E-MRG-2 ran up to five
  chunk processes concurrently, so the frozen values are inflated. They
  sum to 3744 s against the 2162 s serial baseline, and the largest class
  is 64.8 s where section 3 measured 22.5 s serially. It does not change
  the local `n`, which clamps to 8 either way. The `ci` profile and
  `ci_job_setup_seconds` are empty until CP6; matrix host classes (phase
  B) use the new-unit rule until CP5 measures them. CP7 refreshes both
  profiles (the profile's `source` text says so).
- Real full selection with the committed files, `cpu_count` 16: local
  `n` 8, 229 phase-A chunks, shard loads 473.2 s each (max/mean 1.00), the
  critical path 117.3 s (under the 240 s target, no warning), A0 0.7 s;
  21 units on the new-unit rule, none orphaned. The CI profile plans
  (`n` 16), but it uses 30 s defaults until CP6 seeds it.
- Tests: `python3 tests/test_parallel_runner.py` 110/110 OK: T-PLN-1 (60
  seeded random scenarios), T-PLN-2..7, T-PLN-8 (function level), T-PLN-9,
  T-INV-6 (seven timing-file variants, byte-identical inventory and
  selections), config refusals, and the real checkout planning the full
  selection. 17 hand mutations of `planner.py`/`timings.py` were all killed. One
  survived at first (keeping the first five samples instead of the last
  five), because the fixture's two windows happened to share a median;
  the fixture was changed and the mutant is now killed.
- `python3 tests/run_all.py --jobs 1 --select test_parallel_runner.py`: 28
  units green, exit 0. INV-5:
  `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
  empty. No `__pycache__` appeared under `tests/parallel/`.

### CP4 -- isolation, declared exclusive units and integrity guard (complete)

- `tests/parallel/isolation.py` (new, 5.7-5.9). Every function takes
  `repo_root`:
  - `run_chunk` runs one chunk in its own session (`start_new_session`)
    with `chunk_env` (today's environment minus `PYTHONPATH`/`FORCE_COLOR`,
    plus `PYTHONDONTWRITEBYTECODE=1`, `PYTHON_COLORS=0` and a private
    `TMPDIR` at `<run>/tmp/<chunk>/`). The log goes to `<run>/logs/`. It
    polls for exit with `waitid(WNOWAIT)`, so the group leader stays
    unreaped (and its pgid cannot be recycled) until `killpg(SIGKILL)` has
    hit the whole group. That kill happens on timeout (`timed_out`) and
    again after every exit, so no descendant outlives its chunk.
  - Outcome classification: `passed`/`failed` are the chunk's own verdict.
    `timed_out`, `missing_record`, `bad_record` and `record_mismatch` (an
    exit code outside 0/1, or one that contradicts the record's `passed`)
    are infrastructure faults.
  - `clean_tmpdir` adds `u+rwx` to every directory first, reports the
    residue against the chunk and removes it. `chunk_timeout` implements
    `max(600, 5 x estimate)` capped at 3600 s.
  - `phase_a_order(plan)` reads the plan only through
    `plan_schema.shard_chunks`. A0 holds every exclusive chunk in plan
    order (shard index, then position); each shard keeps its shared chunks
    in stored order. `check_exclusive_windows` raises
    `ExclusiveOverlapError` when an exclusive window overlaps any other
    window, using half-open intervals, so windows that only touch do not
    overlap.
  - `acquire_run_lock` takes `flock(LOCK_EX|LOCK_NB)` on
    `<git rev-parse --absolute-git-dir>/wm-verify/run.lock` and never
    waits. The lock file records the holder: pid, start time and the
    process groups of its live chunks. `run_chunk(lock=...)` passes the
    fd to the chunk (`pass_fds`) and records the chunk's pgid while it
    runs. `RunLockHeldError` carries the holder and prints
    `kill -- -<pgid>` for each live chunk.
  - `apply_barrier` requires a held lock for that checkout and refuses
    `RootRefusedError` when `os.geteuid() == 0` unless `allow_root`. It
    also refuses when a marker already exists (recover first). It writes
    `<git dir>/wm-verify/barrier.json` (the original mode of every
    guarded directory, pid and start time; temp name, `fsync`, rename,
    directory `fsync`) before the first `chmod u-w`. Directories already
    lacking `u+w` produce a warning and are restored to that same mode.
  - `Barrier.lift(trees)` restores the recorded modes under exactly the
    given trees, which must be `GUARDED_TREES` members. `lift_trees`
    derives them from the chunk's resources' `paths`, never from a
    name. `Barrier.relock()` re-walks the lifted trees: it records the
    original mode of any directory the exclusive unit created, forgets
    removed ones, rewrites the marker, then re-applies `u-w`.
  - `restore_barrier` is idempotent. `recover_barrier` requires the held
    lock, validates the marker's shape and paths, restores and deletes
    it, and is a no-op without a marker.
  - `attribute_integrity_diff`: for each `tree.compare` difference it
    names the chunks whose windows overlapped the run. When the path
    still exists and its mtime falls inside some windows, it narrows to
    those chunks (`basis: "mtime"`); otherwise it names every chunk in the
    run (`basis: "run"`).
  - `lint_source`/`lint_tests` is 5.9's static lint over `tests/*.py`, done
    with the AST. It flags a list or tuple argv naming
    `migrate.py`/`build_release.py` without `--check`;
    `install.bootstrap`/`update` with a `REPO_ROOT`-rooted target; the
    `tools` writers (`migrate.migrate`/`write_file`/`main`,
    `build_release.build`/`main`) given any rooted argument; rooted
    `rmtree`/`os.remove`/`unlink`/`write_text`/`write_bytes`/`open(...,
    w|a|x)`; and `copy*`/`rename`/`replace` into a rooted destination (a
    rooted *source* is a read). "Rooted" follows `/`, `+`, `str`/`Path`/
    `os.path.join`, f-strings, path-preserving methods,
    `support.REPO_ROOT`, and names assigned from rooted expressions,
    flow-insensitively per scope. A finding inside a unit that
    `resources.json` declares exclusive is exempt; a module-level helper
    has no unit and is never exempt.
- Two additions beyond the plan's function list, neither of which changes
  a contract: `Barrier.lift`/`relock` are methods on the applied barrier
  (the A0 lifting 5.9 describes needs somewhere to keep the recorded
  modes), and `unit.unit_argv` factors out the host-chunk command that
  `unit.launch` already built. `launch` is unchanged in behaviour. The
  barrier's `SIGINT`/`SIGTERM` restore belongs to CP5's executor, which
  owns the process.
- `tests/test_parallel_runner.py`:
  - `scratch_checkout(root, *, resources=...)` git-inits `root` with its
    own git dir. It copies `tests/parallel/` without `matrix.py` and
    replaces `resources.json` with a synthetic one: `repo:distribution` ->
    `["distribution/"]`, with `TestScratchExclusiveWriter` exclusive.
    It writes the synthetic host modules `test_scratch_exclusive.py`
    (rmtree-and-restore of the payload) and `test_scratch_shared.py`, and
    the four guarded trees (a `0.0.1` payload, `migration/`, `src/`,
    `tools/`). It refuses the real root, any path inside it, and any root
    sharing its git dir, and refuses a declaration that fails
    `resources.load` against the scratch's own discovered host inventory.
  - `scratch_worktree(scratch)` makes a sibling linked worktree.
  - The helper processes `_hold_lock_and_barrier` and
    `_hold_lock_with_child_then_hang` are module-level functions taking
    `scratch_root`, started through `get_context("spawn").Process`. Every
    lock-reaching call's root is a name bound to
    `scratch_checkout(...)`/`scratch_worktree(...)`, or that parameter
    (5.9's accepted root forms).
  - CP5 adds the frozen-chunk parts (`run_all.py`, `frozen_runs.py`,
    `support.py`, `src/workflow_manager/`, the full synthetic release,
    `matrix.py`).
- Tests (T-ISO-1..9, T-ISO-11..14, function-level, 31 new):
  - `TestRunChunk` covers T-ISO-1 (a timeout kills a grandchild; a normal
    exit leaves no descendant), T-ISO-2 (`os._exit` gives
    `missing_record`), the mismatch and garbled-record faults, T-ISO-3
    (residue reported and removed), the chunk environment and session,
    and the timeout formula.
  - `TestPhaseAOrder` covers T-ISO-4: 1 exclusive among 16 shards x 50,
    at three shard indices and three positions; one shard; several
    exclusive chunks; the window checks.
  - `TestWriteBarrier` covers T-ISO-5 (the undeclared writer fails with
    `PermissionError` under the barrier and passes lifted; snapshot and
    modes are unchanged), T-ISO-6 (an in-place overwrite escapes the
    barrier and the snapshot, asserted, and the lint flags the rooted
    form), T-ISO-7 (an ignored file is attributed by mtime, a deleted
    tracked file to the whole run), T-ISO-12 (copies arrive `u-w`,
    creating in them raises `PermissionError`, overwriting works, and
    cleanup removes the copy) and T-ISO-14, plus relock over
    created and removed directories.
  - `TestRunLockAndRecovery` covers T-ISO-8 (the helper is SIGKILLed with
    its child alive; the refusal names the child's pgid, the directories
    stay `u-w`, and once the child exits the lock is acquired and recovery
    restores every pre-run mode; no-marker recovery is a no-op; the root
    refusal is tested with `os.geteuid` patched), T-ISO-11, T-ISO-13, lock
    fd inheritance and pgid recording, and lock-required refusals.
  - `TestStaticLint` covers T-ISO-9: 19 numbered writer lines flagged
    exactly, reads not flagged, a declared unit exempt, and today's
    `tests/` clean. The only raw finding in the real tree is line 453 of
    `test_amendment_update_path.py`, inside the declared unit.
- Verification:
  - `python3 tests/test_parallel_runner.py`: 141/141 OK (21.7 s).
  - 20 hand mutations of `isolation.py` were all killed. Two survived at
    first: the chunk's pgid was never recorded in the lock file, and
    `pass_fds` was dropped. Both came from the same gap: nothing checked
    what a chunk sees of the lock. The new test covers it. Its first
    version compared the fd with a reused fd number; it now `fstat`s the
    inherited fd before opening anything.
  - `python3 tests/run_all.py --jobs 1 --select test_parallel_runner.py`:
    34 units green, exit 0.
  - INV-5:
    `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
    is empty. No `__pycache__` appeared under `tests/parallel/`.
  - No `[evidence]` run. The phase-A-under-barrier evidence is CP5's
    E-EXE-2.

### CP5 -- local parallel executor, aggregation and compatibility (complete)

- `tests/run_all.py` is now the thin shim of 5.9: `sys.exit(parallel.cli.main(
  sys.argv[1:], repo_root=<derived from __file__>))`, with bytecode writing
  off before any import.
- `tests/parallel/cli.py` (new): the argument parser, per-mode option checks
  and the pre-lock steps. It refuses a path flag (`--out`, `--plan`,
  `--results`, `--aggregate`) inside the repository
  (`PathInsideRepositoryError`) and checks `--select` syntax, before taking
  the lock. Then it takes the run lock in every mode and recovers a dead
  run's barrier. Every refusal after that is tagged
  `run_all: error[<ErrorName>]: ...` with exit 2. `FAST_ALIAS_SELECTION`
  holds the eight modules of the deprecated `--fast` alias
  (`D-Fast-Flag`, default outcome), which prints "targeted selection --
  not a verification gate".
- `tests/parallel/executor.py` (new): the `Engine` (A0 with the barrier
  lifted for exactly the unit's resource trees, one worker thread per
  shard, phase B in merged mode against merge contexts built from the
  verified plan, and an interrupt that kills every live chunk group).
  Also `local_run`, `list_units`, `plan_only`, `run_shard`, `aggregate`
  and `update_timings`, with the 5.9 guards per mode, the verdict (exit 2
  wins over 1, and every failure is still listed), the exclusive-window
  re-check, integrity attribution and the history append. `SIGTERM` is
  turned into the same unwind as `SIGINT`, so the barrier is restored and
  the lock released.
- `tests/parallel/frozen_chunk.py` (new): the frozen side of a chunk and
  the phase-B `prepare-merge`, run as subprocesses of the checkout being
  verified.
- `tests/parallel/report.py` (new, 5.11): today's per-module lines, one
  block per failure (unit, failing tests, log, output tail, reproduction
  command, with `--whole-groups` and one `--select` per class for a frozen
  chunk), the shard summary, and `results.json`.
- `isolation.RunLock`'s holder record is updated under a mutex so worker
  threads can share it (`live_chunk_pgids` for the interrupt).
  `timings.read_observations` counts an observation once when a results
  directory holds both the record and the history line made from it.
- The declared assertion change of 5.12 in
  `test_workflow_2_6_0_hardening_disposable_repo.py`
  (`test_the_repository_level_guards_are_still_registered`, v2.3.1-002). It
  now asserts that every host class of `test_amendment_update_path.py` is
  in the full inventory and in `FAST_ALIAS_SELECTION`'s resolved
  selection. The comment-only edits of 5.12 were made to it and to
  `test_amendment_update_path.py`.
- Docs: `README.md` and `CLAUDE.md` "Before changing anything" now carry
  the measured timings, `--select` for targeted runs and no tier wording.
  `docs/ARCHITECTURE.md` has a new "Verification execution" section.
- Found and fixed during this checkpoint's review, both surfaced by the
  evidence runs:
  - A local run removed each chunk's `TMPDIR` residue without reporting it
    (5.9 requires residue to be reported against its chunk). The shard
    summary now prints `TMPDIR residue: none`, or each chunk with its
    paths, and `results.json` carries `tmp_residue` per unit. Covered by
    `TestExecutorPieces.test_tmpdir_residue_is_reported_against_its_chunk`.
  - That reporting then showed that `test_parallel_runner.py`'s own CLI
    tests leaked the run directories a failing run keeps on purpose
    (`wm-run-*`, into the real `$TMPDIR` when run directly). `_CliCase` now
    points `TMPDIR` and `tempfile.tempdir` at the test's own temporary
    directory. Verified: a direct run adds no `/tmp/wm-run-*`, and a run
    under the lock reports no residue for the module. The 69
    `/tmp/wm-run-*` directories left by earlier direct runs were not
    removed.
- Tests: section 6.5 T-EXE-1..11 (`TestExitCodeContract`, `TestReport`,
  `TestSerialAndParallelAgree`, `TestPathFlagsStayOutsideTheRepository`,
  `TestFastAliasAndDirectEntryPoints`, `TestRefusalsAreDistinguishable`,
  `TestTestTreeHygiene`, `TestRunShardProvenance`,
  `TestExecutorLevelFaults`, `TestExclusiveWaitUnderLoad`,
  `TestLockAndRecoveryThroughTheCli`), plus `TestExecutorPieces`.
  `scratch_checkout` now also carries the frozen-chunk parts (a synthetic
  `0.0.1` release with manifest, `migration/` files, `matrix.py`,
  `frozen_runs.py`, `support.py` and `src/workflow_manager/`).
  `python3 tests/test_parallel_runner.py`: 175/175 OK (56 s).
- Evidence (the six full runs, one after another on this tree, 16 CPUs;
  the git status was identical before and after):

  | run | wall | exit |
  | --- | --- | --- |
  | `--jobs 1` | 2394 s | 0 |
  | `--jobs auto` (n=8) | 438 s | 0 |
  | `--jobs 8` | 440 s | 0 |
  | `--shuffle-seed 11` / `22` / `33` | 453 / 461 / 475 s | 0 |

  - **E-EXE-1.** All six runs executed the identical set of 25,394 test
    ids (4034 atomic units), with identical per-unit outcomes, per-module
    `Ran N` counts and verdicts. For all 105 release x fixture x suite
    combinations, the frozen per-suite totals (24,870 in all) equal the
    `CI_SUITES` pins that direct mode asserts, and all 15 matrix host
    classes pass their unchanged assertions in merged mode. That is CP2's
    direct == merged comparison, over the planner's default chunking. The
    only frozen failures are the four documented
    `TestRetiredScopedRemediationLeavesNoLiveSurface` exceptions (2.3.1 and
    2.4.0, `bootstrapped` and `target`), judged by their host classes.
  - **E-EXE-2.** Phase A of the real selection ran under the write barrier
    at `--jobs 1` and `--jobs 8`, green: no unit besides the declared one
    writes to a guarded tree, and the integrity comparison was clean. A0
    took 0.8 s in every run. The run directory's `tmp/` was empty after
    cleanup in every run.
    `TMPDIR` residue was **not** none: it was reported and removed. It
    came from three sources:
    - `test_parallel_runner.py`'s own `wm-run-*` leak, fixed above;
    - the frozen `2.6.0` `workflow_state_test.py` (all three fixtures,
      every run), which leaves 9 `wf-lifecycle-worker-*` directories;
    - the frozen `2.4.0` `target` `workflow_integration_test.py` (the
      `--jobs 1` run only), which left two `wf-harness-test-*` repositories
      with in-flight git pack temporaries.

    The frozen payload is not this repository's to change, and direct
    mode leaks the same directories into `/tmp`. So these are recorded
    here as observations, not fixed. The per-chunk `TMPDIR` is exactly
    what contains them now.
  - **E-EXE-3.** Two runs were green: `python3 tests/test_parallel_runner.py`
    directly (175 OK), and `run_all.py --select test_parallel_runner.py
    --select test_workflow_2_6_0_hardening_disposable_repo.py::TestClosedDefectCensus`
    under the held lock (exit 0, residue none). The module was also green
    as a chunk of all six full runs above. The rewritten
    `test_the_repository_level_guards_are_still_registered` was green
    directly and under the lock. Patching `inventory.discover` to drop
    `test_amendment_update_path.py`'s classes makes it fail.
  - The evidence runs came before the `_CliCase` `TMPDIR` fix. That fix
    changes only where those tests' temporary run directories live, not
    which tests exist or their verdicts. It was verified separately under
    the lock, as above.
- INV-5:
  `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
  empty.

### CP6 -- dynamic CI pipeline generated from the plan (complete)

- **`D-CI-Cost` resolved by the user (2026-09-27), proposal column:**
  triggers `pull_request` + `push` to `main` + `workflow_dispatch`, with
  PR runs cancelled in progress per ref; the account is on the GitHub
  **Free** plan with a concurrent-job limit of **20**, so
  `ci_max_shards` stays **16** (the cap would be 19). Both values were
  already what `tests/parallel/config.json` holds
  (`ci_account_concurrent_job_limit: 20`, `ci_max_shards: 16`), so the
  config is unchanged.
- `.github/workflows/workflow-manager-verify.yml` (new, 5.10):
  - `plan`: checkout, Python 3.12, fetch the frozen upstream into
    `$HOME/Workspace/repflow-android` (shallow fetch of tag
    `workflow-v2.3.1`, then a hard check that it resolves to
    `1f954fbb...`), `run_all.py --plan-only --profile ci --out
    "$RUNNER_TEMP/plan.json"` (plus `--shards` from the dispatch input,
    for the `--shards 1` reference), and `shards=[0..n-1]` to
    `$GITHUB_OUTPUT`; uploads `plan.json`.
  - `shard`: matrix `${{ fromJSON(needs.plan.outputs.shards) }}`,
    `fail-fast: false`; same setup; `--run-shard` into
    `$RUNNER_TEMP/out/`; uploads it as `results-shard-<k>` with
    `if: always()`.
  - `aggregate`: `needs: [plan, shard]`, `if: always()`; no upstream
    fetch; downloads the plan and every `results-shard-*` artifact, runs
    `--aggregate`, writes the report to `$GITHUB_STEP_SUMMARY`; its exit
    code is the verdict. Its own run directory is uploaded as
    `results-aggregate` (phase-B timings for CP7's `--update-timings`).
  - Every step that runs `run_all.py` sets `TMPDIR` under `$RUNNER_TEMP`,
    so no tool output (the aggregate's run directory included) lands in
    the checkout or outside `$RUNNER_TEMP`.
  - The managed `workflow-conformance.yml` is untouched.
- Tests (section 6.6), in `tests/test_parallel_runner.py`:
  - T-CI-1 `TestCiWorkflowStructure`: a stdlib parser for the block-YAML
    subset the file uses (refusing anything outside it) and
    `ci_workflow_problems`, which checks the plan-driven matrix,
    `fail-fast`, `aggregate`'s `needs`/`if`, every path flag and artifact
    path under `$RUNNER_TEMP`/`runner.temp`, `TMPDIR`, the per-job modes,
    Python 3.12, the triggers and concurrency of `D-CI-Cost`, and the
    upstream fetch pinning `1f954fbb6c689ec690fefe5a2f27b1e4a0ca6db6`
    (plan and shard jobs, identical; none in `aggregate`). Eleven
    mutations of the file are each caught.
  - T-CI-2 `TestCiTreeIdentity`: the workflow's own `run:` scripts, run
    verbatim with `bash -eo pipefail` in `scratch_clone`s of a scratch
    checkout (a fresh CI-like checkout per job) with a stand-in
    `RUNNER_TEMP`. The plan's `tree_digest` equals each shard job's
    checkout digest and shard summary, `$GITHUB_OUTPUT` gets
    `shards=[0,1]`, the aggregate (with results laid out as the artifact
    download does) exits 0 and writes the step summary, and no job's
    checkout digest changes. With `RUNNER_TEMP` inside the checkout, both
    the plan and the shard step are refused (`PathInsideRepositoryError`).
  - T-CI-3 `TestCiAggregateRefusals`: in the artifact layout, exit 2 for a
    missing shard (`IncompleteResultsError`), a shard from another plan
    (`ForeignResultsError`), and a complete, self-consistent frozen record
    set re-cut into another chunk partition, stamped for this plan and
    tree (`FrozenMergeError`, the context being built from `plan.json`).
  - T-CI-4 `TestManagedWorkflowUntouched`: `workflow-conformance.yml`
    still matches its `installation.json` digest, the new file is not a
    managed file, and `python3 -m workflow_manager verify` reports
    "installation matches workflow 2.5.1".
  - T-CI-5 `TestCiGuardsInAFreshCheckout`: in a clone with no untracked or
    ignored file, a host unit and the phase-B matrix class each run a
    subprocess with the environment replaced wholesale (no
    `PYTHONDONTWRITEBYTECODE`) importing `src/scratchpkg`. `--run-shard`
    and `--aggregate` are green and leave no `__pycache__` under `src/`.
    With `Barrier._lock_dirs` patched out, each leaves
    `src/scratchpkg/__pycache__` and fails with exit 2 (`IntegrityError`).
  - `scratch_clone` is a new accepted root in T-EXE-7's lock-reach scan,
    like `scratch_worktree`, and the scan's mutation list gained "a clone
    of the real checkout".
- Verification: the ten new tests pass under Python 3.14.7 and, with
  T-EXE-1 and T-EXE-8, under Python 3.12.14 (the CI interpreter).
  `python3 tests/run_all.py --jobs 1 --select test_parallel_runner.py`:
  exit 0, 185 tests OK, `TMPDIR` residue none (under the real run lock and
  barrier, so T-CI-4's `verify` ran there too). `python3.12 tests/run_all.py
  --plan-only --profile ci` on the real checkout planned `n=16`.
- **`[evidence]`, CI (recorded 2026-09-27).** The user authorized Claude to
  push `main` and run the workflow for this evidence.
  1. Push run 1, at `51a1193` (16 shards):
     <https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36317161829>.
     **Failed, and exposed a CP6 defect.** Shard 9 failed
     `test_conformance_suite.py::TestAuthoredReleaseOverlayCommitIsReachable`
     for all four authored releases (`2.4.0`, `2.5.0`, `2.5.1`, `2.6.0`):
     each release's recorded `overlay_commit` "is not an ancestor of HEAD",
     because `actions/checkout`'s default is a depth-1 clone. Every other
     test was green. The aggregate reported the failure as exit 1 (a test
     failure), not as an infrastructure fault, which is the 5.11 contract.
     **Fix, commit `a20ca3d`:** every job checks out with `fetch-depth: 0`.
     T-CI-1 requires it, and the mutation list gained "a shallow checkout".
     That commit carries only a `Workflow-Work-Item` trailer, not a
     second `Workflow-Checkpoint: CP6`, which would make
     `discover_checkpoint_commits` ambiguous. `51a1193` is still CP6's
     checkpoint commit, and discovery was re-checked after the fix.
  2. Push run 2, at `a20ca3d` (16 shards):
     <https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36317866360>.
     **Green: 18/18 jobs, aggregate verdict exit 0.** Wall time from the plan
     job's start to the aggregate's end was 12 min 36 s (12:06:05-12:18:41
     UTC).
     - Setup, from job start to the `run_all.py` step: plan 5 s (compute
       6 s), shards 5-8 s, aggregate 8 s (compute 13 s).
     - Shard compute ran from 4 min 13 s (shard 13) to 11 min 42 s
       (shard 4). The `ci` timing profile is still empty, so every unit
       was estimated at `default_unit_seconds`, and the plan predicted
       121,246 s of total work against about 6,570 s observed. CP7 folds
       these results in.
     - All 13 host modules were OK. The only frozen chunk failures are the
       four documented `TestRetiredScopedRemediationLeavesNoLiveSurface`
       exceptions (`2.3.1` and `2.4.0`, `bootstrapped` and `target`), judged
       by their host classes.
     - The `TMPDIR` residue is the nine `2.6.0` `workflow_state_test.py`
       chunks' `wf-lifecycle-worker-*` directories, as recorded locally at
       CP5.
     - **O2:** `host:test_bootstrap_e2e.py::TestCliDrivesTheSameOperations`
       ran in **shard 12**, green (0.9 s). That shard applied the write
       barrier, reported no `IntegrityError`, had `TMPDIR` residue none, and
       ended with `verdict: exit 0`.
  3. The `--shards 1` CI reference (P-0's CI counterpart),
     `gh workflow run workflow-manager-verify.yml -f shards=1` at `a20ca3d`:
     <https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36318597506>.
     **Green: aggregate verdict exit 0.** Wall time was 1 h 50 min 50 s
     (12:19:28-14:10:18 UTC). Its single shard took 6,572.6 s of compute
     (1 h 49 min 59 s as a job). It shows the same four documented frozen
     exceptions, `TestCliDrivesTheSameOperations` green, and the same
     residue.

     Sharding at 16 therefore cut CI wall time **from 110.8 min to 12.6
     min (8.8x)** before any CI timing data existed. The account's
     concurrent-job limit is 20 (Free plan, `D-CI-Cost`). In run 1, two
     of the 16 shards queued briefly behind it, since the managed
     conformance job runs on the same push.
  - CP7 uses the downloaded results artifacts of run 2 and of the
    reference run to seed the `ci` profile and `ci_job_setup_seconds`.
- **Required check.** Making `aggregate` the one required status check is a
  branch-protection (or ruleset) setting on `main`, done by the user in the
  repository settings. CP6 first noted that the Free plan offers no branch
  protection for private repositories. The user has since made the
  repositories public (2026-09-27), and on public repositories the Free plan
  does offer it, so the check can now be enforced.
- INV-5:
  `git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
  empty.

### CP7 -- performance acceptance, tuning, committed timing seed, stress runs and full regression (complete; two accepted deviations confirmed by the user)

Commits: `11e996e` (the code, tuned timings and docs the measurements ran
against), `6cd0f97` (direct CI per-class timings), and this checkpoint's
commit (records only). Hardware: the section 3 workstation, 16 CPUs, Python
3.14.7; CI is `ubuntu-latest` with Python 3.12.

**Timing seed and tuning.**
- *Local profile.* Rebuilt from CP7 measurements only, replacing CP3's
  inflated seed (3744 s summed against a 2162 s serial run). The source is
  one full run at 8 workers (the P-1 condition) with
  `target_shard_seconds` temporarily 0.01, so every frozen class ran as
  its own chunk and got its own time. That covers 4035 of the 4042 units.
  The other 7 are the classes that failed in that run and use the new-unit
  rule; see "Found and fixed" below.
- *CI profile.* A first fold of push run 36317866360 and the reference
  run measured only 130 units: host classes and phase B. A multi-class
  chunk yields only its group overhead (5.2), so every frozen class was a
  ratio estimate. That left CI shard balance at 1.14-1.18. So, as the user
  directed (2026-09-27), one CI run was taken with one class per chunk:
  run 36330161250, on a throwaway branch `cp7-ci-timing-measurement`
  (`11e996e` plus `target_shard_seconds` 0.01), deleted afterwards.
  Folding it gives **4023 directly measured CI units** (`6cd0f97`). The
  local plan's chunk assignment is byte-identical before and after that
  fold, so the local runs at `11e996e` stay equivalent evidence.
- `ci_job_setup_seconds` is plan 9 s, shard 11 s, aggregate 15 s. Each is
  the job's wall time minus its `run_all.py` step (median, run
  36317866360), plus the 2 s scheduling gap before a dependent job.
- `config.json` is unchanged. Every tuned plan already balances to a
  predicted max/mean of 1.000, so the makespan is bound by total work, not
  by chunking. No bound was changed.

**Results against section 7.**

| id | measured | threshold | result |
| --- | --- | --- | --- |
| P-0 | local 2162 s (section 3.1, at `db4c7af`); CI `--shards 1` reference: run 36318597506, 6572.6 s shard compute, 110.8 min wall (CP6) | reference only | recorded |
| P-1 | `--jobs auto` (8 workers) at `11e996e`: 425.8 / 410.8 / 406.1 s, all exit 0 | median <= 420 s | **met** (median 410.8 s) |
| P-1 at `--jobs 16` | 10 runs, from P-4: 299.4-319.1 s, median 308 s | reported, no threshold | recorded |
| P-2 | `--jobs 1` at `11e996e`: 2421.2 s, exit 0; per-unit outcomes, executed test ids (`tests_digest 6bb22c22...`, 25,411 tests) and verdict identical to all three P-1 runs | <= 1.10 x P-0 (2378.2 s) | **missed as measured: 1.120 x**; at the post-review head 1.098 x. Accepted deviation, confirmed by the user (below) |
| P-3 | see the CI table below | median at the higher shard count <= 5.5 min | **not met; documented-unreachable** under its own "if unreachable" clause (review ruling, round 1). Floor quantified below |
| P-4 | `--jobs 16`, 10 consecutive runs: 10/10 exit 0, zero retries | 10/10 green | **met** |
| P-5 local | from P-1: predicted 424.7 s against actual 406-426 s (within 5 %); shard max/mean 1.025-1.026; discovery + planning 1.1-1.2 s; barrier apply 0.004 s and restore 0.001 s (141 directories) | +/-25 %; <= 1.15; <= 20 s; <= 5 s | **met** |
| P-5 CI | see below | +/-25 %; <= 1.15 | **partly met**. Accepted deviation, confirmed by the user (below) |

**P-2, the miss and its like-for-like figure.** P-0 was measured at
`db4c7af`, before `tests/test_parallel_runner.py` existed. That module is
73.4 s of new serial test work in P-2, not per-chunk repository overhead,
which is what the threshold protects ("fresh repository per chunk must not
cost more than 10 %"). Without it, P-2 is 2347.8 s, **1.086 x P-0**.
Both figures are recorded. Whether to judge the criterion on the
like-for-like figure is left to the implementation review, and this ledger
does not claim it was met. The run is fresh evidence, not reused: the
serial-evidence policy (below) makes CP5's `--jobs 1` run at `534174c`
stale, since both the runner and the inventory changed after it.

**P-3 and P-5 CI.** All runs are at `6cd0f97` (direct CI timings), exit 0,
`tests_digest 6bb22c22...`. Wall runs from the plan job's start to the
aggregate's end. "Queue" is the time from the plan job's end to the last
shard's start.

| run | shards | wall | queue | wall - queue | predicted | shard max/mean |
| --- | --- | --- | --- | --- | --- | --- |
| [36333123741](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36333123741) (push) | 16 | 644 s | 163 s | 483 s | 423 s | 1.177 |
| [36334507166](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36334507166) | 16 | 472 s | 4 s | 470 s | 423 s | 1.091 |
| [36333799173](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36333799173) | 19 | 623 s | 206 s | 419 s | 362 s | 1.083 |
| [36334988012](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36334988012) | 19 | 536 s | 132 s | 406 s | 362 s | 1.230 |

- **Sampling.** Per the user's 2026-09-27 direction, one 16/19 pair was
  run first. It came out contradictory (balance 1.177 against 1.083), so
  one second sample of each was taken. That restores section 7's two runs
  per shard count. The four earlier runs at `11e996e` (ratio-estimated CI
  timings: 36326202990, 36326698697, 36327254254, 36328046906) are kept as
  the "before" measurement. They were all exit 0, with walls of
  483/521/749/451 s and balance 1.141/1.180/1.160/1.171.
- **P-3: not met.** The median wall at 19 shards is 580 s (9.7 min), and
  at 16 it is 558 s. Without GitHub's queueing, the medians are 413 s
  (6.9 min) and 477 s. The remainder, quantified:
  - critical-path chunk 197.3 s
    (`host:test_parallel_runner.py::TestExclusiveWaitUnderLoad`);
  - per-job setup: plan 9 s, shard 11 s, aggregate 15 s;
  - plan compute 5-6 s, aggregate compute 9-13 s (phase B 2.7-4.3 s);
  - per-shard compute about 325 s mean at 19 shards (CI total work about
    6,200 s);
  - queueing of 4-206 s before the last shard started, although every run
    stayed under the 20-job cap.

  Perfectly balanced on equal-speed runners, 19 shards is still about
  6.0 min. Reaching 5 min needs about 24 shards, and the Free plan's
  20-job cap forbids that (`D-CI-Cost`: limit 20, so at most 19 shards).
  Coverage was not reduced to close the gap.
- **P-5 CI prediction.** Measured as P-5 specifies, with queueing
  included, 1 of 4 runs is within +/-25 % (+11.5 %, +48 %, +52 %, +72 %).
  Queueing is GitHub's scheduling, which 5.4 step 5's model (setup plus
  compute) does not cover. Without it, all four are within +11 % to +16 %.
- **P-5 CI balance.** 2 of 4 runs are within 1.15 (1.083, 1.091), and the
  median is 1.134 (it was 1.166 before the direct timings). The rest is
  runner-to-runner speed variance: shards with identical predicted loads
  ran at 0.73-1.12x of prediction, with a per-run median of 0.98-1.05. So
  the estimates are now centred correctly, but a static plan cannot absorb
  hosted-runner variance. Flagged for review. A fix would need dynamic
  work distribution across CI jobs, or more shards than the account
  allows. Neither is in this milestone's scope.

**Accepted deviations (confirmed by the user at `/approve-review implementation`, 2026-09-27).** Section 7 gives P-3 an
"if unreachable, the remainder is documented quantitatively" clause, and the
round-1 review accepted P-3 under it. P-2 and P-5 CI have no such clause, so
they are recorded here as explicit deviations from section 7 for the user to
confirm or reject at `/approve-review implementation`. They are **not**
recorded as met. The post-review evidence is in "Implementation review round
1" below.
- **P-2** (`--jobs 1` <= 1.10 x P-0 = 2378.2 s).
  - Raw: 2421.2 s = **1.120 x** at `11e996e` (missed); 2374.0 s =
    **1.098 x** at the post-review head `2b4c0fd`. The second is inside the
    threshold by only 4.2 s, well within run-to-run variance, so this record
    does not rely on it.
  - Like-for-like, excluding `tests/test_parallel_runner.py` (new serial
    work that did not exist at P-0): **1.086 x** at `11e996e`, **1.063 x**
    at `2b4c0fd` (that module ran 76.8 s serially there).
  - The review's ruling: like-for-like is the correct reading of the
    threshold's purpose ("fresh repository per chunk must not cost more
    than 10 %"), but the plan does not define that comparison.
- **P-5 CI prediction** (+/-25 %). As P-5 specifies, queueing included: 2
  of 5 runs within (the four CP7 runs at +11.5/+48/+52/+72 %, and run
  36344165589 at `2b4c0fd`, +16 %). Excluding GitHub's queueing, which 5.4
  step 5's model does not cover: 5 of 5, +7 % to +16 %.
- **P-5 CI balance** (shard max/mean <= 1.15). 3 of 5 runs within (1.083,
  1.091, and 1.081 at `2b4c0fd`); the misses are 1.177 and 1.230. This is a
  genuine miss: hosted-runner speed varies 0.73-1.12x between shards of
  equal predicted load, and a static plan cannot absorb that.

**`D-CI-Cost`: billed runner-minutes per full run.** GitHub's billing API
(`actions/runs/<id>/timing`) reports **0 billable ms** for every run above:
standard hosted runners are free on public repositories, and the repository
has been public since 2026-09-27. The private-repository equivalent, which is
what `D-CI-Cost` budgets, is each job's duration rounded up to whole minutes,
summed over the run's jobs (from the runs' job pages):

| run | shards | jobs | job time | billed-minute equivalent |
| --- | --- | --- | --- | --- |
| 36318597506 (reference) | 1 | 3 | 6,646 s | 112 |
| 36333123741 | 16 | 18 | 6,175 s | 113 |
| 36334507166 | 16 | 18 | 6,382 s | 114 |
| 36344165589 (post-review) | 16 | 18 | 6,533 s | 118 |
| 36333799173 | 19 | 21 | 6,523 s | 121 |
| 36334988012 | 19 | 21 | 6,476 s | 118 |

So a full run costs about **113-121 billed minutes** at 16-19 shards, against
112 for the single-shard reference: sharding adds only per-job setup and
rounding. At 2,000 free private minutes a month, that is about 16-17 full
runs.

**`D-Fixture-Reuse` (5.14): closed, no follow-up.** Measured in isolation
(median of 5), the `bootstrapped` fixture builds in 0.057 s (`2.3.1`) and
0.066 s (`2.6.0`), the same as `conformance` and `target`. Per-chunk group
overhead (build, interpreter start and suite import) is 0.26-0.32 s locally
and 0.53-0.56 s on CI. That is about 0.3 % of the local critical path
(119.2 s), far under the 10 % trigger.

**User-directed addition: the serial and single-shard evidence policy
(2026-09-27).**
- `docs/ARCHITECTURE.md`'s "Verification execution" now states the
  policy. Full-suite serial or single-shard runs are exceptional evidence,
  run only when a plan or criterion requires them or to debug a
  serial/sharded discrepancy. An equivalent earlier run is cited, not
  repeated. The section defines when evidence is equivalent (same
  `selection_digest` and `tests_digest`, and no change to code, tests or
  runner between the two heads; `tree_digest` and documentation or state
  commits do not count) and when it is stale. It says what a reuse record
  cites. It keeps the guarantees: never weaken a criterion, never hide a
  discrepancy, and never silently swap a required long run for the sharded
  path. `CLAUDE.md` and `README.md` point to it, and mark the `--jobs 1`
  command "exceptional evidence only".
- Every run now prints an `evidence:` line and records the same fields in
  `results.json` (as `identity`) or `shard-<k>.json`: `full` or `targeted`
  selection, scope, `head`, `tree_digest`, `selection_digest`, unit counts,
  test count and `tests_digest` (`report.evidence_identity`).
- Applied in this checkpoint: P-2 was run fresh because the equivalence
  failed, and the `6cd0f97` fold was shown not to change the local plan,
  so P-1, P-2 and P-4 were reused rather than re-run.
- The Workflow's own commands (`.claude/commands/milestone-implement.md`
  step 3, for instance) are frozen, managed release content, so they were
  not edited. Carrying the policy into the Workflow itself would be a
  Workflow release's job.
- Tests: `TestEvidenceIdentity`, `TestEvidenceIdentityThroughTheCli` (every
  executing mode; a local full run and a 1-shard CI run share one
  `tests_digest`), and `TestSerialEvidencePolicyIsDocumented` (the docs
  mark every serial command and name the fields the runner records).

**Found and fixed** (by the first local measurement run, where 3 tests
failed):
- `scratch_checkout` copied the real `tests/parallel/config.json` into every
  scratch checkout, so tuning the real config changed scratch tests'
  chunking. Two tests failed that way
  (`TestCiAggregateRefusals`' partition test and `TestReport`'s multi-class
  reproduction). Scratch checkouts now write their own `SCRATCH_CONFIG`,
  guarded by `TestScratchCheckout.test_it_carries_its_own_planner_config_never_the_real_one`.
  Both tests were re-verified with a deliberately skewed real config.
- `_dead()` (CP4's helper) raised `ProcessLookupError` when a process was
  reaped between its `open` and `read` of `/proc/<pid>/stat`. It now
  treats that ESRCH as dead. That was the root cause of the one
  `TestRunChunk.test_a_timeout_kills_the_whole_process_group` error, and
  P-4's ten runs were clean after the fix.

**Observations, not changed.**
- `TMPDIR` residue in every full run is 3-4 chunks, the frozen `2.6.0`
  `wf-lifecycle-worker-*` directories already recorded at CP5. It is
  reported and removed.
- The P-4 runs at `--jobs 16` took about 50 % longer than predicted
  (213 s), because the local profile was measured at the 8-worker default.
  P-5 scores only the P-1 and P-3 runs.
- GitHub now force-runs the Node 20 actions (`checkout@v4`,
  `setup-python@v5`, `upload-artifact@v4`, `download-artifact@v4`) on
  Node 24 and warns about it. That is harmless today, and bumping the
  action majors is a follow-up.

**Final regression.** The full selection is green:
- locally in parallel (P-1 and P-4) and at `--jobs 1` (P-2), at `11e996e`;
- in CI, all eight P-3 runs, at `11e996e` and `6cd0f97`.

That includes `tools/migrate.py --check` and every authored release's
`build_release.py --check`, which run inside the suite. After `11e996e`,
the tree changed only in `tests/parallel/timings.json`'s `ci` profile (the
local plan is proven identical) and in documentation or workflow state, so
under the policy above those runs stand as this checkpoint's evidence.
INV-5:
`git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
empty.

### Self-review of the milestone diff (`SELF_REVIEWING_IMPLEMENTATION`)

The whole `db4c7af..5c8f7ef` diff was reviewed in three parts: the
executor, isolation and CLI; the inventory, planner and timings; and the
frozen merge, the edits to existing tests, the CI workflow and the docs.
No finding was blocking. Four were important, all confirmed against the code
and fixed:

- **A barrier that failed part-way through was never undone in-process.**
  `apply_barrier` writes the marker first, and the guard only receives the
  `Barrier` once it returns. A `chmod` error, or a SIGINT/SIGTERM while the
  directories were being locked, left some of them `u-w`, and only the next
  run or `--restore-barrier` fixed that. `apply_barrier` now restores and
  deletes the marker on any exception before re-raising (5.9).
- **An unexpected error exited 1**, the test-failure code, because Python
  exits 1 on an uncaught exception. Examples: a failed `Popen`, `chmod` or
  git call, a full disk, or an unwritable timing cache after a green run.
  `cli.main` now maps every error the tool does not name itself to a tagged
  exit 2, followed by the traceback (5.11).
- **`read_observations` overwrote every history line's own profile.** As a
  result, `--update-timings --profile ci` fed from the local cache would
  fold local durations into the committed `ci` estimates. A line now keeps
  its own profile, and `profile` applies only to records and to lines that
  have none.
- **A signal-killed frozen chunk could be hidden by a zero.**
  `MergedResult.returncode` was `max(...)`, so a chunk that printed its
  summary and then crashed (`-11`) merged to 0 and read as green, where
  direct mode fails. A negative code now wins. 5.5 says "max". This is a
  deliberate, strictly fail-closed deviation from it.

Minor findings, also fixed:
- **`RunLock.release` unlocked for everyone.** It called `LOCK_UN` on the
  open file description every chunk had inherited. It now only closes its
  fd, so a live chunk keeps the lock.
- **An `--allow-root` run was not flagged in the report.** 5.9 requires it.
  The barrier now carries a warning, and every mode's shard summary prints it.
- **`--aggregate` counted an unknown chunk outcome as a pass.** An unknown
  outcome is now `IncompleteResultsError`.
- **A matrix host class declared exclusive would have been accepted.**
  Phase B has no A0 step and never lifts the barrier, so the planner now
  refuses it (`ExclusiveMatrixUnitError`). No such declaration exists today.
- **An adversarial timing file could reach the planner as `inf`/`nan`.**
  Non-finite profile ratios are now dropped, and an estimate that is not a
  valid duration falls through to the next rule.
- **A truncated line in the shared history cache crashed
  `--update-timings`.** It is now skipped with a warning.
- **Timing warnings named the checkout's absolute path.** Those warnings
  enter the plan, so two checkouts of one tree digested differently
  (INV-3). They now name the file relative to the checkout.
- **`results.json` dropped a frozen `setUpClass` error.** It is rendered
  `module.Class`, and the per-unit `failing` filter missed it. It is now
  attributed to its class.
- **The rewritten bootstrapped cleanliness check no longer saw what the
  class's own generation-script method left in the target.** Before
  sharding, the live `git status` ran after that method. A new method,
  `test_the_target_is_still_git_clean_after_this_class_ran`, restores that
  coverage. It sorts after both methods and is not a view-reading predicate.
  This adds one test to each of the five bootstrapped matrix classes.
- **`docs/ARCHITECTURE.md`'s reuse rule never required the cited run's
  verdict**, and the `tests_digest` docstring claimed "tests that actually
  ran". The rule now requires the cited run's verdict and records it, and
  the docstring says what the digest actually covers.

Not changed, recorded for the reviewer:
- `plan_schema` raises `TypeError` instead of `PlanSchemaError` on a
  hand-edited plan with mixed-type `units`. That only happens with a
  hand-made plan.
- A PR run cancelled by `cancel-in-progress` still runs its `aggregate` to
  a red result. `if: always()` is kept: `!cancelled()` would let the
  required check be skipped, and a skipped check counts as passing.
- `CLAUDE.md` does not repeat `docs/ARCHITECTURE.md`'s note that
  `--shards 1` takes effect only with `--plan-only`.

Tests: 14 new, in `tests/test_parallel_runner.py` (206 OK directly). Each
names the fix it covers, including the first SIGTERM and SIGINT tests of
the executor. Reverting each fix while its test runs was caught in all 15
cases. `test_bootstrap_e2e.py` has its new method.

Gate, `python3 tests/run_all.py` (8 workers, 16 CPUs):
- **Before the fixes, at `5c8f7ef`:** exit 0, 404.1 s wall, 25,411 tests,
  `tests_digest 6bb22c22...`.
- **On the fixed tree:** exit 0, 409.8 s wall (predicted 424.7 s), 4042/4042
  units, 25,430 tests (+19: the 14 new runner tests plus one method in each
  of the five bootstrapped classes), `selection_digest 787699b6...`,
  `tests_digest d227f2ef...`, `tree_digest 1f2fa583...`. The only frozen
  failures were the four documented `TestRetiredScopedRemediationLeavesNoLiveSurface`
  exceptions, judged by their host classes.

That second run includes `tools/migrate.py --check` and every authored
release's `build_release.py --check`, which run inside the suite. INV-5:
`git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml`
is empty.

### Implementation review round 1 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Bundle `f5352210...`, `review_content_id 0d83e66b...`, reviewed head
`1704c5d`. 0 blocking, 3 important, 11 optional. Every finding was reproduced
against the code before it was fixed. Each fix's test was checked against
the pre-fix source and failed there.

**Important.**
- **I1, fixed (`a5d4909`).** `local_run` appended to the user-level timing
  history before `results.json` and the report, so an unwritable cache
  turned a green run into a report-less exit 2. It now writes
  `results.json`, emits the report, and appends last. A failed append is a
  **warning, never a fault**: 5.2 treats the history as an incidental,
  never-committed cache, so a lost line costs future estimates, not this
  run's verdict. Also checked:
  - `aggregate`'s `GITHUB_STEP_SUMMARY` append already came after the
    report, but could still flip exit 0 to 2. It gets the same treatment.
  - `run_shard` writes only its own results directory, the artifact the
    aggregate needs, so a failure there stays a fault.

  Tests: a green run and a failing run with an unwritable history path, and
  an aggregate with an unwritable step summary.
- **I2, done: fresh evidence at the post-fix head `2b4c0fd`**, one run
  each, taken after every code fix had landed. Per the serial-evidence
  policy's clause 1, the approved plan requires this evidence, so none of
  it is a confidence rerun.
  - *Local parallel gate:* `python3 tests/run_all.py`, 8 workers. **Exit
    0**, 388.7 s wall (predicted 424.7 s), 4042/4042 units, 25,436 tests,
    `selection_digest 787699b6...`, `tests_digest f55cbcd9...`,
    `tree_digest 103b9cc5...`.
  - *Local serial:* `python3 tests/run_all.py --jobs 1`. **Exit 0**,
    2374.0 s wall, with the same `selection_digest`, `tests_digest` and
    test count. **INV-6 holds.** Every one of the 4042 units has identical
    `outcome`, `failing`, `ran` and `tests` in both runs' `results.json`
    (3892 passed and 150 failed in each; the 150 are the frozen units of the
    four documented portability-exception chunks, judged by their host
    classes).
  - *CI:* run
    [36344165589](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36344165589)
    (`workflow_dispatch`, the planner's default 16 shards). The user
    authorized it on 2026-09-27: `2b4c0fd` was pushed to a throwaway branch,
    `apply-review-i2-ci-evidence`, the branch was deleted afterwards, and
    `main` was not pushed. **Green: 18/18 jobs, aggregate verdict exit 0.**
    It has the same `selection_digest`, `tests_digest` and 25,436 tests;
    its `tree_digest 454bd145...` differs from the local runs' only because
    the local tree held the uncommitted round-1 `WORKFLOW_STATE.json` phase
    write. Wall 491 s, with 38 s of queueing; predicted 423.4 s (+16 %,
    +7 % without the queueing). Shard max/mean 1.081. Critical path
    `host:test_parallel_runner.py::TestExclusiveWaitUnderLoad`, 197.3 s.
    The four documented frozen exceptions and the `2.6.0`
    `wf-lifecycle-worker-*` residue are as before.
  - All three include `tools/migrate.py --check` and every authored
    release's `build_release.py --check`.
- **I3, done.** CP7 above now carries "Accepted deviations (pending user
  confirmation)", for P-2 raw and like-for-like and for P-5 CI prediction
  and balance, and marks P-3 documented-unreachable under its clause. It
  records `D-CI-Cost`'s billed runner-minutes per full run, qualifies CP7's
  status, and uses the numbers from the I2 reruns. `docs/ARCHITECTURE.md`'s
  summary says the same.

**Optional.**
- **O1, fixed (`9393294`).** `docs/ARCHITECTURE.md`'s equivalence rule now
  states the exact carve-out CP7 relied on: a `timings.json`-only change
  counts when the evidence run's plan (`n`, chunk ids and members, shards)
  is unchanged at both heads, checked with `--plan-only`. It also adds
  `workflow-manager-verify.yml` to what CI evidence watches, and
  `CLAUDE.md`'s summary gains the verdict condition.
- **O2, fixed (`5c144f5`).** `strict_json_loads` reports a `RecursionError`
  as a `ValueError`. That covers every caller's corrupt-file path at once:
  timings, history, records, plans, shard summaries and resources.
- **O3, fixed (`5c144f5`).** A history line with a non-string `unit`,
  `fixture`, `profile` or `tree_digest` is skipped with a warning.
- **O4, fixed (`e3a5169`).** A skipped subtest is recorded under its own
  test method, and never overwrites that method's failed subtest.
- **O5, fixed (`fdf6515`).** `--from` is refused inside the repository.
- **O6, fixed (`622a32d`).** The spawn is inside `run_chunk`'s `try`, so an
  interrupt landing right after it still kills the chunk's group.
- **O7, fixed (`9f71901`).** The lock-refusal hint lists groups that are
  gone separately, offers `kill` only for groups that still exist, says to
  verify first, and notes that an unrecorded chunk is not listed.
- **O8, fixed (`3798aaa`).** An unhashable resource name and
  `schema_version: 1.0` are `ResourcesFileError`.
- **O9, partly fixed (`d0efbab`).** Every CI job sets `timeout-minutes`:
  plan 30, shard 180 (the single-shard reference needs about 111), and
  aggregate 60. `--plan-only --profile ci` refuses `--shards` above 256,
  GitHub's matrix limit.
  - **Not applied:** a per-commit concurrency group for pushes to `main`.
    Plan 5.10 prescribes "a `concurrency` group per ref" (`D-CI-Cost`), so
    changing it is a plan decision for the user, not an optional fix.
  - The residual it leaves: an intermediate `main` push whose run is still
    *pending* when a newer one queues is cancelled by GitHub, and that
    commit gets no verdict.
- **O10, not changed.** The reviewer agrees that the tautological clause
  matches 5.12's own wording, so it is not a deviation. Rewriting 5.12's
  declared replacement assertion is outside an optional fix.
- **O11, recorded (`2b4c0fd`).** `docs/ARCHITECTURE.md` states that merged
  mode does not repeat direct mode's implicit check that no suite writes
  into the fixture's state file or host documents. Only E-MRG-3 (CP2)
  covers it.

**Concerns noted, not changed.**
- The committed `timings.json` seed will dominate future diffs.
  `docs/ARCHITECTURE.md` now says when to refresh it.
- The CI critical-path chunk is this milestone's own
  `TestExclusiveWaitUnderLoad`: 197.3 s, against the roughly 62 s section
  3.5 expected. It does not bind at 16-19 shards, but it would near the 24
  shards the 5-minute target needs. That is a follow-up if the job limit
  ever rises.

INV-5 at `2b4c0fd`:
`git diff db4c7af -- distribution migration scripts .claude/commands src tools .github/workflows/workflow-conformance.yml pyproject.toml docs/MIGRATION.md`
is empty.

## Functional review checklist

You are testing `python3 tests/run_all.py` as an operator uses it.
- **Technical approval:** commit `ff7a936`, implementation revision 2.
- **Where findings go:** `.ai-review/feedback/FUNCTIONAL_REVIEW.md`.
- **Automated verification:** already current. The full gate passed at
  `35e8717` (4042/4042 units, 25,436 tests, `tests_digest f55cbcd9...`).
  Only state commits have landed since.

**Setup.**
- Python 3.12 or later, and a Linux or macOS shell.
- Nothing needs installing, and there are no feature flags.
- Run flows 1-3 in this checkout, with a clean working tree. Run flows 4-6
  in a throwaway clone, so that no scratch test touches this repository:

```bash
export M=~/Workspace/workflow-manager
export T=$(mktemp -d) && git clone -q "$M" "$T/c"
```

**Test data.** None beyond the scratch test modules that flows 4-6 add to
the clone.

**Flows.**

1. **Full gate.** In `$M`, run `python3 tests/run_all.py; echo "rc=$?"`.
   Expected:
   - progress lines `[n/259] ok ...`;
   - one `ok` line for each of the 13 host modules;
   - a block listing exactly four frozen chunks with a non-zero exit. They
     are the documented `2.3.1`/`2.4.0` `bootstrapped`/`target`
     `TestRetiredScopedRemediationLeavesNoLiveSurface` exceptions;
   - a shard summary with 8 workers;
   - an `evidence:` line with `4042/4042 units`, `25436 tests` and
     `tests_digest f55cbcd9...`;
   - `verdict: exit 0` and `rc=0`, in about 6.5-7 minutes. The serial
     baseline was 36 minutes.
   - While it runs, `test -w distribution || echo read-only` prints
     `read-only`. Once it ends, `distribution/` is writable again and
     `git status` is clean.
2. **Targeted selection, and not a gate.**
   - `python3 tests/run_all.py --list --select test_templates.py` lists
     `host:test_templates.py::<Class>` units only.
   - `python3 tests/run_all.py --select test_templates.py` passes in
     seconds, and its `evidence:` line says `targeted selection`.
   - `python3 tests/run_all.py --select nope.py; echo $?` prints
     `run_all: error[SelectSyntaxError]` naming the five accepted forms,
     then `2`.
   - `python3 tests/run_all.py --fast` prints the deprecation note, which
     says it is a targeted `--select` of eight modules.
3. **CI plan and its guards.**
   - `python3 tests/run_all.py --plan-only --profile ci --out $T/plan.json`
     prints `plan written to ...` and `n=16 shards, ... plan_digest ...`.
   - `--profile ci --shards 300` is refused: it exceeds the 256-job matrix
     limit, exit 2.
   - `--out docs/x.json` is refused with `error[PathInsideRepositoryError]`,
     exit 2, and nothing is written.
4. **A failing test is exit 1, with a reproduction command.** In `$T/c`,
   create `tests/test_zz_scratch.py` holding a class `TestScratchFails`
   whose test does `self.assertEqual(1, 2)`. Then run
   `python3 tests/run_all.py --select test_zz_scratch.py; echo $?`.
   Expected:
   - a `FAIL test_zz_scratch.py` module line;
   - a failure block naming
     `host:test_zz_scratch.py::TestScratchFails`, with `failing:`, `log:`
     and `reproduce: python3 tests/run_all.py --jobs 1 --select ...`;
   - the traceback;
   - `verdict: exit 1`, and `1`.
5. **Undeclared writes are caught.** In the same clone:
   - A test that writes `distribution/zz_probe.txt` fails with a
     permission error, because the write barrier holds. That is exit 1.
   - A test that writes `docs/zz_probe.txt` passes itself, but the run
     reports `fault [IntegrityError]: docs/zz_probe.txt changed during the
     run`, naming the chunk. That is exit 2.
6. **Concurrency and interruption.** In the clone, add a test that sleeps
   30 s.
   - Start `python3 tests/run_all.py --select <it>`.
   - While it runs, start a second run in another terminal. It is refused
     at once with `error[RunLockHeldError]`, which names the holder and
     its chunk process groups. Exit 2.
   - Press Ctrl-C in the first terminal. It ends with
     `error[InterruptedRunError]`, exit 2.
   - Afterwards, `distribution/` is writable again, and
     `ps -eo args | grep parallel.unit` shows no leftover chunk.
7. **Optional: CI.** Look at run
   [36344165589](https://github.com/RodrigoFAbreu/workflow-manager/actions/runs/36344165589)
   (`workflow-manager-verify`):
   - a `plan` job, 16 `shard` jobs and an `aggregate` job;
   - `aggregate` is the verdict, exit 0, with the same `tests_digest`.

   A fresh CI run needs a push. That is your call, and it is not required
   for this review.

**Known limitations and out of scope.**
- Accepted deviations, already confirmed:
  - P-2: serial `--jobs 1` runs at 1.098-1.120x the baseline.
  - P-5 CI: prediction and balance vary with GitHub queueing and runner
    speed.
- P-3 (CI under 5.5 min) cannot be reached under the 20-job cap. CI takes
  about 7-10 min.
- The frozen `2.6.0` `workflow_state_test.py` leaves `wf-lifecycle-worker-*`
  residue in `TMPDIR`. The runner reports it and removes it. It is frozen
  content, so it is not fixable here.
- The first full gate on a machine without a timing history is estimated
  from the committed `tests/parallel/timings.json`. `timing drifted` or
  `timing defaulted` lines are informational.
- A `--jobs 1` serial run (about 40 min) is exceptional evidence, not a
  flow to test (see `docs/ARCHITECTURE.md`).
- Optional review findings left open:
  - A post-report cleanup failure can exit 2 after printing exit 0.
  - An interrupt inside `Popen`'s few-millisecond fork-to-exec window is
    not covered.
  - The per-commit `main` CI concurrency group is a follow-up.
- This repository's own unrelated working-tree edits are not part of this
  milestone.

---

# Previous milestone (complete): `workflow-review-artifact-and-concurrency-hardening`


## Milestone

**Complete.** `workflow-review-artifact-and-concurrency-hardening`
(`governing_workflow_version: "2.2"`, plan approved at revision 8): Workflow
`2.6.0` — review-artifact, publication and concurrency hardening.
Full plan: `docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`.

## Goal

Close the Workflow correctness defects and gaps that `docs/ROADMAP.md`
section 1 groups under review artifacts, review publication, approval commit
integrity, legacy active-work-item compatibility, amendment artifacts and
cross-worktree concurrency, as one bounded hardening release. Deliverable: a
new authored Workflow release, `2.6.0`, built as `distribution/workflow/2.5.1/`
(base, unchanged, byte-for-byte immutable) plus `migration/overlays/2.6.0/`,
per this repository's `CLAUDE.md` "Adding an authored Workflow release"
process. See the plan's section 2 for non-goals.

## Current checkpoint

**Milestone complete.** `workflow-review-artifact-and-concurrency-hardening`
reached `MILESTONE_COMPLETE` via `/accept-milestone` after user-confirmed
functional testing against the checklist below (flows 1-7, evidence commit
`c1e2bf5`) found no product findings; `active_work_item_id` is cleared. The
checkpoint narrative below (CP1-CP9) is this milestone's own permanent
record and is left in place rather than deleted.

**CP9 complete** (9 of 9 checkpoints). Every registry checkpoint is
complete and technically approved. Next: the functional review (see
"Functional review checklist" below).

### CP1 — Release-derived exact-path classification of the legacy installation record

Implements the plan's section 5.2, `D-Tooling-Ambient-Classification` (the
legacy-item half of `v2.4.0-001`; requirement `REQ-3`). Delivered in
`migration/overlays/2.6.0/` (this milestone's first overlay files, each a
full replacement starting from the `2.5.1` base copy):

- `payload/scripts/workflow_fingerprint.py`: new
  `TOOLING_AMBIENT_EXCLUDED_PATHS = frozenset({".workflow-manager/installation.json"})`.
  `classify_path` and `classify_path_implementation_stage` consult it only
  after every declared classification has failed, immediately before the
  `UnclassifiedPathError` raise. No other line of the module changed.
- `payload/scripts/workflow_fingerprint_test.py`: new
  `TestToolingAmbientExcludedPaths` (8 tests) — fallback classification at
  both stages with a `2.5.1` control arm (constant patched empty), explicit
  protected declaration still wins, siblings
  (`installation.json.tmp`, `other.json`, `.workflow-manager/`, bare and
  nested look-alikes) still raise, full-projection invariance with and
  without the fallback, and digest invariance: with the record unchanged
  every digest is identical; after an uncommitted and then a committed
  record change every digest (plan worktree/commit, implementation
  worktree/commit) that raised under `2.5.1` now equals its pre-change
  recorded value.
- `payload/scripts/workflow_state_test.py`: new
  `TestImplementingEntryReachableAfterInstallationRecordUpdate` — a
  2.3.1-shaped item stays `implementing_entry_reachable` after a committed
  installation-record change; the control arm raises `UnclassifiedPathError`.
- `payload/docs/ai-workflow/REVIEW_PROTOCOL.md`: the classification
  paragraph under "Computing `review_content_id`".
- `payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md`: new section
  `D-Tooling-Ambient-Classification` carrying section 5.2's justification.
- `classification.json`: `base_workflow_version: "2.5.1"`, one `replaced`
  rule per touched file. Later checkpoints add their own rules.

Every test/doc change is additive; no pre-existing test was modified.

**Verified state.** Run inside a temporary tree composed from
`distribution/workflow/2.5.1/payload/` overlaid with
`migration/overlays/2.6.0/payload/` (tests resolve sibling files relative to
their own directory, so a bare `PYTHONPATH` split fails on
`prepare-ai-review.sh`):

- `python3 -m unittest workflow_fingerprint_test workflow_fingerprint_generalization_test`:
  305 tests, OK.
- `workflow_state_test`'s new class plus `TestImplementingEntryReachableSecondItem`,
  the `ReviewMaterialLifecycle*`, `GoverningVersionEnumerationSweepTest` and
  `ApplyingReviewFeedbackVersionClaimSweepTest` classes (the new
  `WORKFLOW_V2_PLAN.md` section is swept by them): 51 tests, OK.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP2 — Working-tree-anchored `AMENDMENT_DIFF.patch`

Implements the plan's section 5.5, the `D-Plan-Amendment-5` revision
(`v2.4.0-003`; requirement `REQ-8`). Delivered in `migration/overlays/2.6.0/`:

- `payload/scripts/prepare-ai-review.sh` (first overlay replacement): the
  `AMENDMENT_DIFF.patch` block drops `..HEAD` and writes
  `git diff --no-renames <amendment_base_commit> -- <pathspec>`, anchored at
  the working tree. The pathspec is the sorted union of the
  `plan_stage.protected_paths` declared at `amendment_base_commit` (empty
  when the declaration is absent there), the ones declared now, and
  `<id>-artifacts.json` itself. A leading `#` preamble names
  `work_item_id`, `amendment_id`, `amendment_base_commit`, `plan_revision`
  and `review_content_id`. The block moved to just after `--write-manifest`
  (still after the pin, before the archive), so the preamble carries the
  manifest's own `review_content_id`. Nothing else in the script changed;
  the archive line item 341 guards is untouched.
  **`--no-renames` is an implementation finding, not in the plan text:**
  section 5.5 says Git's rename detection is not relied on, but `git diff`
  applies it by default (`diff.renames`), and the rename test failed
  without the flag — the patch showed `rename from/to`, not
  `deleted file` + `new file`.
- `payload/scripts/workflow_fingerprint_generalization_test.py`: new
  `TestPrepareAiReviewShAmendmentDiffWorkingTreeAnchor` (13 tests), driving
  the real script in scratch repositories. It covers every case CP2 names:
  - an uncommitted plan edit is present, with a `..HEAD` control arm that
    is empty;
  - an untracked new protected file appears as `new file`, and is
    untracked again afterwards (no lingering intent-to-add);
  - a dropped-and-deleted path appears as `deleted file`;
  - a rename appears as `deleted file` + `new file` and passes
    `git apply --check`;
  - a dropped-but-kept path appears as its content diff when changed, and
    only in the declaration hunk when unchanged;
  - with the declaration absent at the base, the patch equals the
    current-only form;
  - non-protected edits are absent;
  - the archive member is byte-identical to the on-disk patch;
  - `bundle_id` is identical with and without the patch (on disk and in
    the archive's `current/`);
  - the file is removed after resolution;
  - the preamble fields equal the manifest's and the state's;
  - `git apply --check` accepts the patch at `amendment_base_commit`.
- `payload/.claude/commands/request-plan-amendment.md` step 4,
  `payload/docs/ai-workflow/REVIEW_PROTOCOL.md` "Bundle structure", and
  `payload/docs/ai-workflow/WORKFLOW_V2_PLAN.md` `D-Plan-Amendment-5` (new
  "Working-tree anchor" paragraph): restated to the working-tree anchor.
  The command keeps the mention-only generator wording that
  `workflow_integration_test.py`'s census pins.
- `classification.json`: three new `replaced` rules (`prepare-ai-review.sh`,
  the generalization test, `request-plan-amendment.md`); the existing
  `REVIEW_PROTOCOL.md`/`WORKFLOW_V2_PLAN.md` rules' rationales now cover
  CP2's delta too.

Every test change is additive; no pre-existing test was modified.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay (committed there as one scratch commit):

- `python3 -m unittest workflow_fingerprint_generalization_test`: 92 tests, OK
  (the new class alone: 13, OK).
- `python3 -m unittest workflow_integration_test`: 260 tests, 3 errors.
  Every error is in `TestRetiredScopedRemediationLeavesNoLiveSurface`, which
  reads the repository-level `docs/ACTIVE_MILESTONE.md`. The payload tree
  has none. The pure `2.5.1` payload has the identical failure set.
- `python3 -m unittest workflow_state_test` (its doc sweeps read the edited
  `WORKFLOW_V2_PLAN.md`): 854 tests, 2 errors. Both are
  `TestCanonicalStateSerialization` live-state tests with no live
  `WORKFLOW_STATE.json` in the payload tree. The pure `2.5.1` payload has the
  identical 2 errors.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP3 — Per-work-item feedback layout

Implements the plan's section 5.1, `D-Feedback-Layout` (requirements
`REQ-1`, `REQ-2`). Delivered in `migration/overlays/2.6.0/`.

**Pre-edit evidence (section 6.2's downgrade paragraph depends on it).**
Run against `distribution/workflow/2.5.1/payload/scripts/` before any edit:
`2.5.1`'s `validate_state` has **no** work-item key allowlist —
`_validate_work_item` checks `work_item_id`, type, kind, phase, checkpoint
statuses, the review-stage ledgers, the block pins and the approval
records only. A state whose every entry carries `feedback_layout:
"scoped"`, and one carrying `feedback_layout: "bogus"`, both validate
cleanly: the key is **ignored, not rejected**. The committed-field sets
(`ORDINARY_`/`RECOVERED_BUNDLE_GENERATION_RECORD_FIELDS`,
`TECHNICAL_APPROVAL_COMMIT_FIELDS`) are *field-diff* allowlists; a key
written once at creation and never changed never appears in a later
commit's field diff, so none of them sees it either. Consequence for
CP7's downgrade paragraph: a downgraded repository does not fail — it
silently resolves scoped items' feedback by the legacy rule.

- `payload/scripts/workflow_fingerprint.py`:
  - `resolve_feedback_layout` (`scoped` / `legacy-scoped` / `legacy-flat`)
    reads the item's entry from the worktree's `WORKFLOW_STATE.json`;
    `resolve_feedback_dir` (signature unchanged) is built on it. A
    `"scoped"` item resolves `.ai-review/<id>/feedback` with no existence
    gate. An entry without the field, no entry, or no state file keeps the
    unchanged rule. A symlinked, non-JSON or non-object state file refuses
    (`FeedbackLayoutUndecidableError`), as does any other field value,
    `null` and non-strings included (`UnknownFeedbackLayoutError`).
  - `ensure_feedback_dir` creates the resolved directory;
    `mark_functional_review_consumed` now calls it.
  - `resolve_feedback_path_contract` and the
    `--resolve-feedback-path <id>` CLI (one JSON object, same function).
  - `assert_feedback_not_owned_by_other_work_item(..., state=None)`: with
    `state`, a foreign owner at a terminal phase is non-blocking for a
    legacy writer only; a non-terminal or state-absent owner, or any
    foreign file under a scoped writer, still refuses.
    `FEEDBACK_OWNER_TERMINAL_PHASES` is pinned equal to
    `workflow_state.TERMINAL_PHASES` (the module cannot import
    `workflow_state`).
  - `assert_manual_feedback_names_work_item` /
    `ManualFeedbackForeignWorkItemError`.
- `payload/scripts/workflow_state.py` (first overlay replacement): the
  stamp in `route_work_item`'s fresh-id branch and
  `create_remediation_child_work_item`; `_validate_work_item` refuses an
  unknown value. Nothing else changed.
- Tests: new `TestFeedbackLayout` (16) in `workflow_fingerprint_test.py`
  and `TestFeedbackLayoutStamp` (6) in `workflow_state_test.py`, covering
  every CP3 test bullet. An unhashable layout value (`["scoped"]`) first
  surfaced a raw `TypeError` from the membership test; both checks now
  type-check first (INV-3). Re-pointed pins, none deleted:
  `TestBundleLayoutResolver`, `TestFunctionalReviewConsumedMarker` and
  `TestReviewImplementationWritebackCrossWorkItemIsolation` now state their
  legacy scope (their fixtures have no state file); the acceptance-matrix
  `feedback_dir()` helper asserts the scoped layout and creates the
  directory through `ensure_feedback_dir`.
- Normative docs: `REVIEW_PROTOCOL.md` gains the "Feedback directory"
  subsection (the one normative definition, including the CLI contract for
  Controller); `MILESTONE_WORKFLOW.md`'s eight hard-coded flat paths become
  `<feedback_dir>` plus one definition; notes in
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, `PLAN_REVIEW_WORKFLOW.md` and
  `IMPLEMENTATION_REVIEW_WORKFLOW.md`; a new `WORKFLOW_V2_PLAN.md` section
  `D-Feedback-Layout`.
- Commands: `apply-functional-review`, `apply-implementation-review`,
  `apply-plan-review`, `approve-review`, `milestone-plan`,
  `prepare-functional-review`, `record-manual-plan-review`,
  `record-manual-implementation-review`, `review-functional`,
  `review-implementation` and `review-plan` now define `<feedback_dir>` by
  `feedback_layout` and print the exact resolved path wherever the operator
  must paste or find feedback. The three review writers pass `state=` to
  the ownership guard and call `ensure_feedback_dir` before writing;
  `/prepare-functional-review` calls it before reporting; both
  `/record-manual-*-review` commands run
  `assert_manual_feedback_names_work_item` before any state write.
- `classification.json`: new `replaced` rules for every newly overlaid
  file; the existing rules' rationales now cover CP3's delta too.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay (committed there as one scratch commit):

- `python3 -m unittest workflow_fingerprint_test workflow_fingerprint_generalization_test workflow_acceptance_matrix_test`:
  480 tests, OK (18 skipped).
- `python3 -m unittest workflow_state_test`: 860 tests, 2 errors — the same
  two `TestCanonicalStateSerialization` live-state errors as CP2 (no live
  `WORKFLOW_STATE.json` in the payload tree).
- `python3 -m unittest workflow_integration_test`: 260 tests, 3 errors — the
  same three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors as CP2.
- `workflow_state_demo_test`, `workflow_fingerprint_demo_test`,
  `workflow_test_harness_test`, `workflow_state_completion_obligations_test`:
  187 tests, 13 failures + 27 errors, a failure set identical, test for
  test, to the pure `2.5.1` payload's (these read real repository history).
- `workflow_fingerprint.py --resolve-feedback-path` smoke run: one JSON
  object, `legacy-flat` with no state file.
- Every overlay payload file is matched by a `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP4 — Bundle-bound plan-review publication

Implements the plan's section 5.3, `D-Plan-Review-Bundle-Binding` (revises
`D-Plan-Revision-Publication`; requirement `REQ-4`). Delivered in
`migration/overlays/2.6.0/`. `"1"`-governed behavior is unchanged
throughout.

**Mechanical enumeration (section 5.3 item 1), recorded before the edits:**

- *`workflow_state.py` predicates reading a plan-stage phase:*
  - `validate_local_plan_review_preconditions` (`== AWAITING_LOCAL_PLAN_REVIEW`)
    and `validate_manual_plan_review_preconditions`
    (`== AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`) are unaffected: only
    stronger, because the bind is now the sole writer of the first.
  - `record_local_plan_review`/`record_manual_plan_review` gain the
    `CONSUMED` write on `REVISE`.
  - `request_plan_amendment` (`_AMENDMENT_REQUEST_ALLOWED_PHASES`) gains
    the `CONSUMED` write.
  - `apply_plan_approval` has no phase precondition; `/approve-review plan`
    step 2's reader now gates it.
  - `BUNDLE_GENERATION_LEGAL_SOURCE_PHASES`/`CHECKPOINT_START_LEGAL_PHASES`
    contain no plan-stage phase: unaffected.
  - No predicate treated `AMENDING_PLAN` as "not yet under review"; the
    generator has no phase check (the bind decides).
- *Commands reading the post-publication phase:* `/review-plan`,
  `/record-manual-plan-review`, `/approve-review plan` step 2 (now the
  readers), `/milestone-plan` and `/apply-plan-review` (new entry),
  `/apply-functional-review` (remediation child), `/request-plan-amendment`
  (next step). `/milestone-implement` checks `IMPLEMENTING` only:
  unaffected.
- *Writers attempted at a ready phase and their decided behavior:*
  - `route_work_item` and `publish_plan_revision` refuse with
    `PlanReviewInProgressError`.
  - The generator is a wrapper-only regeneration that binds nothing.
  - `bind_plan_review_bundle` is idempotent at local review and refuses
    with `PlanReviewAlreadyReadyError` elsewhere.
  - `withdraw_plan_review` is the exit.
- *`route_work_item` resume callers:* only `/milestone-plan` step 1, reached
  at `PLANNING`/`REVISING_PLAN`/`AMENDING_PLAN` after the entry's
  withdrawal. The remediation child's re-declaration runs at `PLANNING`.
- *Protected edits before the publish, per command:*
  - `/milestone-plan`: steps 3-5 edit, and the publish sits at the new
    step-5 publication point.
  - `/apply-plan-review`: steps 3-5 edit, and the publish is in step 5
    after the regeneration, re-embed and staging. Its later steps write
    only `plan-inputs/`.
- *Exits between publish and bind:* only the generator-failure exits (each
  reporting the explicit-id re-run, row 9) and a bind refusal (same
  report). `apply-plan-review.md` step 6 is `"1"`-only, and 7'.2's second
  generation is removed.

**Delivered:**

- `payload/scripts/workflow_state.py`:
  - The publication split:
    - mirror-only `publish_plan_revision` with a required
      `review_content_id` and the `PUBLISHED` record;
    - the plan-stage allow-list on it and on `route_work_item`'s resume
      branch.
  - The `plan_review_binding` record (`CONSUMED`/`PUBLISHED`/`BOUND`) and
    its `validate_state` INV-3 check.
  - `CONSUMED` writes in both `REVISE` writers and
    `request_plan_amendment`, plus `ensure_plan_review_binding_marker`
    (the INV-7 legacy marker).
  - `bind_plan_review_bundle` and `withdraw_plan_review`.
  - `verify_plan_review_bundle`, with the cause-named
    `PlanReviewBundleUnverifiedError`/`ReviewedContentDriftError`.
  - `plan_review_publication_status` (the total table) and its read-only
    `--plan-review-publication-status` CLI.
  - The readers `assert_plan_review_bundle_bound`/
    `validate_local_plan_review_preconditions_bound`.
  - `assert_plan_review_entry_phase`, `assert_plan_review_withdrawal_allowed`
    and `assert_apply_plan_review_feedback`.
  - 15 named errors.
  - `transition_to_awaiting_local_plan_review` is retired: it always
    raises `PlanReviewWriterRetiredError`.
- `payload/scripts/workflow_fingerprint.py` and `prepare-ai-review.sh`:
  - Plan-stage-only staging generation: the plan stage builds in
    `current.staging-<token>/current/` with `.pin.staging-<token>/`, and
    the archive and `AMENDMENT_DIFF.patch` are staged too.
  - Author inputs come from `plan-inputs/`
    (`resolve_plan_review_inputs_dir`, `seed_plan_review_inputs`).
  - `finalize_staged_plan_bundle_generation`:
    - on success it promotes everything and clears `REJECTED`;
    - on failure it discards the staging area, with no withdrawal and no
      marker.
    - This is the deliberate `WFR-67` revision.
  - Implementation/post-fix keep the in-place path; its checks were
    factored unchanged into `_closing_bundle_generation_check`.
  - **Implementation detail, not in the plan text:** the staging area
    holds its bundle in a `current/` child so that item 341's archive
    guard (the positional argument is the bare literal `current`) holds
    unchanged.
- Commands and normative docs:
  - `milestone-plan`: the entry (row 1, withdrawal, marker, status), step 3
    without its publish, the step-5 publication point, and step 6's bind.
  - `apply-plan-review`: the entry, step 1's `REVISE`-only rule, step 5's
    publish on every round, step 6 as `"1"`-only, and step 7' as
    verify-plus-bind.
  - `review-plan`, `record-manual-plan-review`, `approve-review` (step 2),
    `apply-functional-review` and `request-plan-amendment`.
  - `REVIEW_PROTOCOL.md` (`<plan_inputs_dir>`, staging, the `WFR-67`
    revision stated as deliberate), `WORKFLOW_V2_PLAN.md` (revised
    `D-Plan-Revision-Publication`, new `D-Plan-Review-Bundle-Binding`),
    `MILESTONE_WORKFLOW.md`, `PLAN_REVIEW_WORKFLOW.md` and the operator
    reference.
  - `/milestone-plan`'s publication point is a `[2.1]` bullet closing
    step 5 rather than a new numbered step, because a golden test
    hash-pins steps 1-5 with the `[2.1]` bullets stripped.
- Tests:
  - New unit classes in `workflow_state_test.py` (37 tests).
  - `TestPrepareAiReviewShPlanStageStaging` in
    `workflow_fingerprint_generalization_test.py` (8).
  - 13 real-repository scenario classes in
    `workflow_acceptance_matrix_test.py` (85), covering every CP4 test
    bullet.
- **Pre-existing tests re-pointed, none deleted:**
  - Publish phase-flip pins, the retired transition, `route_work_item`
    resume fixtures (moved to a plan-stage phase), and both phase-writer
    censuses.
  - The acceptance driver now follows 2.6.0's command order: stage,
    publish the fresh id, `plan-inputs/`, generate, verify and bind.
    Every plan document gains checkpoint anchors.
  - Rows B13, B14 and F4 re-planned mid-implementation through 2.5.1's
    in-place re-publish, which 2.6.0 deliberately refuses. They now go
    through `/request-plan-amendment`. B14 reaches the B8 wedge via an
    amendment from `SELF_REVIEWING_IMPLEMENTATION`, since no plan
    re-entry exists from `AWAITING_FUNCTIONAL_REVIEW`.
  - The six restated command files' golden hashes are re-recorded.
- **Recorded edge, for review:** at a ready phase, deleting the plan
  document, registry or mapping refuses at the readers and the status
  function with the named `InvalidPlanStageMetadataPathError`, not row 4a.
  The plan's own section 5.3 item 6 limits `F = ⊥` to
  `AbsentProtectedPathError`/`PlanRevisionMismatchError`, "any other
  failure refuses (INV-3)". The withdrawal exit still works (pinned by
  `test_deleted_metadata_path_is_a_named_refusal_and_withdrawal_still_exits`).
- `classification.json`: CP4 rationales on every touched rule. The test
  rules state that pre-existing tests were re-pointed.

**Verified state.** Run in a temporary tree composed from the `2.5.1`
payload plus this overlay:

- `workflow_fingerprint_test` + `workflow_fingerprint_generalization_test`:
  342 tests, OK.
- `workflow_acceptance_matrix_test`: 231 tests, OK (18 skipped).
- `workflow_state_test`: 897 tests, 2 errors. These are the same two
  `TestCanonicalStateSerialization` live-state errors as CP2/CP3.
- `workflow_integration_test`: 260 tests, 3 errors. These are the same
  three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors.
- Demo/harness/obligations suites: 40 failing, identical test for test to
  the pure `2.5.1` payload.
- Every overlay payload file is matched by a `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP5 — Plan-approval commit closure and committed-truth verification

Implements the plan's section 5.4, `D-Plan-Approval-Closure` (items 1-6;
item 7 declined as planned). Delivered in `migration/overlays/2.6.0/`.

**Delivered:**

- `payload/scripts/workflow_fingerprint.py`:
  - `resolve_plan_stage_approval_commit_paths` returns every declared
    `plan_stage.protected_paths` entry (plan, registry and mapping first),
    `WORKFLOW_STATE.json`, the unchanged conditional artifacts-declaration
    member, and the removals: protected under `HEAD`'s committed
    declaration, tracked at `HEAD`, and absent from both the current
    declaration and the worktree. A first approval has none.
  - `PlanApprovalCommitPlan` gains `protected_paths` and `removal_paths`,
    both defaulted, so hand-built plans still construct.
  - `read_plan_stage_manifest_base_commit` and
    `read_plan_stage_manifest_protected_paths`.
  - `compute_review_content_id_plan_stage_at_commit` is documented as
    accepting any tree-ish. No code change was needed: every Git read it
    makes already accepts a bare tree.
- `payload/scripts/workflow_state.py`:
  - `resolve_fresh_plan_approval_members` (step 4a, read-only). It runs:
    - the empty-index precondition, whose refusal now names the
      staged-`git mv` remedy;
    - the member set;
    - per-member freshness against the bound bundle. A protected member
      is compared with its `files/` capture, otherwise with its blob at
      the bundle's `MANIFEST.md` `base_commit`, otherwise it refuses. A
      removal member must be neither captured nor declared.
    - Every failure is `ReviewedContentDriftError`. A stale
      declaration's `StaleArtifactsDeclarationError` is chained under it.
  - `assert_plan_approval_member_set_unchanged`: step 5's re-resolution
    inside the guarded window.
  - `prove_plan_approval_index_closure` (step 6.3a): `git write-tree`,
    then the identity at that tree. Every removal must be absent.
  - `verify_plan_approval_commit`: the one post-commit verification. It
    derives the work item from the committed state and runs the two-sided
    path-set check (`assert_committed_plan_approval_closure` for the
    closure side).
  - `classify_post_commit_verification_failure`: the amend gate.
  - `verify_post_approval_manifest_match` gains
    `MissingApprovalRecordError` at both stages and an optional explicit
    `expected_review_content_id`.
  - `stage_plan_approval_commit_paths` stages an absent member as a
    deletion.
  - The journal gains an optional `removal_paths`. A `2.5.1` journal
    reads as `[]`.
  - 5 named errors.
- `approve-review.md`: steps 4a, 4c, 5, the new 6.3a, 6a/6a1, 6b's range
  and 6d, plus the implementation-stage verifier bullet.
  `milestone-plan.md`: the member-set sentence in step 3.
  `WORKFLOW_V2_PLAN.md`: new `D-Plan-Approval-Closure` section.
- Tests:
  - `Item.approve_plan` in the acceptance matrix is now a
    **command-shaped driver**. It follows the command's real data flow
    through steps 2-6d: the bound-bundle check, the fresh member set, the
    in-window re-resolution, the proof, `verify_plan_approval_commit`, the
    amend gate and the rollback. A resumable `complete_plan_approval`
    covers the rest. There is no hand-built post-state. All 231
    pre-existing rows pass through it unchanged.
  - 4 new scenario classes (31 tests) cover every CP5 test bullet. The
    amend-gate rows use real one-shot `pre-commit` hooks.
  - `TestPlanApprovalClosureUnits` (11 unit tests).
- **Pre-existing tests re-pointed, none deleted:** three integration tests
  pinned `2.5.1`'s fixed four/five-member set on a fixture whose
  declaration protects two further documents. The `approve-review.md` and
  `milestone-plan.md` golden hashes are re-recorded.
- **Implementation details, not in the plan text, for review:**
  - **An extra path is not amended.** An extra path in the approval
    commit (`CommittedPathSetMismatchError`) classifies
    `RECORD_OR_INPUT`: stop, no amend. The amend re-stages members and
    cannot remove a path, so an amend there could never succeed. This
    matches the frozen bootstrap design's "recovery corrects content,
    never membership". The closure side's content failures get their own
    `CommittedProtectedContentMismatchError`, which classifies
    `TREE_CONTENT`.
  - **Revision errors stop.** A hook that corrupts the plan document's
    `(Revision N)` title makes the committed-tree recompute raise a
    revision error. That classifies `RECORD_OR_INPUT` (stop), the
    conservative reading of INV-5.
  - **Step 6d's closing check is narrowed** to a clean index and clean
    members. A de-protected path left in the worktree legitimately
    survives the approval.
  - **6a1 re-stages the journal's members,** never a fresh resolution,
    because `HEAD` is by then the approval commit.
  - **The CP6 precondition is not built yet.** 6a1's
    `assert_amendment_resolution_held` precondition is named in the
    command as CP6's addition.

**Verified state.** Run in a temporary Git repository composed from the
`2.5.1` payload plus this overlay:

- `workflow_acceptance_matrix_test`: 262 tests, OK (18 skipped). That is
  the 231 pre-existing rows, now driven through the command-shaped
  driver, plus the 31 new ones.
- `workflow_state_test`: 908 tests, 2 errors. These are the same two
  `TestCanonicalStateSerialization` live-state errors as CP2-CP4.
- `workflow_integration_test`: 260 tests, 3 errors. These are the same
  three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors.
- `workflow_fingerprint_test` + `workflow_fingerprint_generalization_test`:
  342 tests, OK.
- Demo/harness/obligations suites: 40 failing, identical test for test to
  the pure `2.5.1` payload.
- Every overlay payload file is matched by a `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP6 — Repository-global lifecycle lock and amendment witness

Implements the plan's section 5.6, `D-Repo-Global-Lifecycle` (closes
`v2.4.0-002`; INV-6, INV-10). Delivered in `migration/overlays/2.6.0/`.

**Pre-edit evidence (section 6.2's downgrade paragraph depends on it).** Run
against `distribution/workflow/2.5.1/payload/scripts/` before any edit:
`2.5.1`'s `validate_state` has no `amendment_history` entry-key check, so a
state whose resolved entry carries `resolved_review_content_id` (a hex
string, or even an integer) validates cleanly. The key is **ignored, not
rejected**, the same finding CP3 recorded for `feedback_layout`.

**Delivered:**

- `payload/scripts/workflow_state.py`:
  - **Primitive (9)**, `lifecycle_lock`: a per-work-item `flock` at
    `<git-common-dir>/ai-workflow/checkpoint-claims/<token>.lifecycle.lock`,
    never unlinked. It is a pure source. A process-local held-set
    (`_held_primitives`), which every existing `flock` and lease now
    registers in, must be empty when it is taken
    (`LifecycleLockOrderError`).
  - **The amendment witness**, `<token>.amendment.json`
    (`OPEN`/`RESOLVING`/`RESOLVED`/`NONE`), written by tempfile plus
    `os.replace`. A torn, symlinked or unknown-shaped witness refuses
    (`AmendmentWitnessUnavailableError`).
  - `amendment_request_projection_sha256` and
    `amendment_resolution_projection_sha256`.
  - The lag probe, with `workflow_release_version_key` ordering versions
    numerically and treating an unorderable version as lagging.
  - The upgrade bootstrap (the request and resolution fork checks, the
    legacy trailer comparison, and no `NONE` sentinel while a worktree
    lags), the two orphan tests with their evidence-bound clear literals,
    and the predicate list (`_evaluate_lifecycle`).
  - `claim_checkpoint` runs (9) → (2) → witness check → phase check →
    publish. `adopt_claim` and an absent-claim `take_over_claim` take (9)
    before (6)/(5); the takeover's guarded window moved, unchanged, into
    `_take_over_claim_window`.
  - `request_plan_amendment` refuses without (9)
    (`LifecycleLockNotHeldError`). `request_plan_amendment_transaction` is
    the one entry point, and it publishes the `OPEN` witness before the
    state.
  - The resolution side: `reserve_amendment_resolution` (4d),
    `assert_amendment_resolution_held` (6a1), `advance_amendment_witness`
    (6c1), `release_amendment_resolution` (after 6b), and
    `stage_plan_approval_members` with `first_commit`/`amend_recovery`
    modes.
  - `apply_plan_approval` records `resolved_review_content_id`.
    `open_plan_approval_journal` refuses an amendment-resolving transaction
    while a claim is live.
  - 11 named errors under `LifecycleRefusalError`.
- `payload/docs/ai-workflow/dry-run/verify_372h_*.py`: primitive 9, the five
  (9) edges as code-derivable, the stated totals (16 edges, 9/7) replacing
  the hard-coded 11 and 6/5, the re-anchored `(6)→(8)` mutation, and a new
  regression that removes both `(9)→(8)` evidence paths.
- Commands:
  - `approve-review.md`: the entry table under 4b, the new 4d, step 5's
    `first_commit` staging, 6a1's held check and `amend_recovery` staging,
    6b's token capture and release, and the new 6c1 advance before 6d.
  - `request-plan-amendment.md`: steps 1-2 (the closed race, the new entry
    point, every refusal and its remedy).
  - `milestone-implement.md` (new to the overlay): step 1d's lifecycle
    refusals and remedies, and step 1c's routing to them.
- `WORKFLOW_V2_PLAN.md`: the edge table, the primitive list, the totals,
  the blocking list, the acyclicity argument, the `(2)→(8)` paragraph,
  `D-Plan-Amendment-1`'s bullet (now repository-wide), and a new
  `D-Repo-Global-Lifecycle` section.
- Tests, with every CP6 test bullet 1-29 covered:
  - `workflow_state_test.py` (51 new tests):
    - `TestCrossWorktreeAmendmentClaimResidualXModelR9B1` is inverted
      into `TestCrossWorktreeAmendmentClaimRaceIsClosed` (tests 1-4,
      including real-process races in both orders);
    - `TestAmendmentClaimRaceRealProcesses` keeps the same-worktree races
      (test 16);
    - new classes for tests 5-13i and 19-28 at the unit level, with real
      linked worktrees, `SIGKILL`ed workers and real plan-approval
      journals.
  - `workflow_acceptance_matrix_test.py`: the command-shaped driver gains
    4d, the staging modes, 6a1's held check, 6b's capture-then-release and
    the 6c1 advance, with hook seams. The new
    `RepoGlobalLifecycleAcrossWorktrees` (18 rows) drives
    `/approve-review plan` in worker processes that pause or `SIGKILL` at a
    named step (tests 8, 17, 18, 22, 23, 25, 26, 27, 28).
  - `workflow_integration_test.py`: `TestApproveReviewLifecycleEntryTable`
    (test 29).
- **Pre-existing tests changed, none deleted:**
  - four tests that acquired a lease to stand in for a live holder now
    release it at the end, because the held-set correctly carried it into
    every later test in the process;
  - `TestRequestPlanAmendment` calls the pure mutator holding (9);
  - the golden hashes of `approve-review.md` and `milestone-implement.md`
    are re-recorded.
- **Deviation from the plan text, for review.** The census finds
  **sixteen** edges, not the fifteen section 5.6 states, with a **9/7**
  split, not 8/7. The extra edge is `(9)→(3)`: an absent-claim
  `take_over_claim` must hold (9) across its publication, and that
  publication's guarded (5) window already establishes this worktree's
  identity (the existing `(5)→(3)` edge). Avoiding the edge would mean
  writing the identity before the takeover's re-verification, which
  breaks its "refuse, having mutated nothing" contract. The edge is
  blocking but acyclic: the blocking sources `{1, 5, 8, 9}` and targets
  `{2, 3, 6}` stay disjoint. The script, the plan table and
  `WORKFLOW_V2_PLAN.md` all state 16 and 9/7.
- **Implementation details, not in the plan text, for review:**
  - The witness is always written with every field; a field a status does
    not use is `null`.
  - A bootstrap-written `OPEN` at seq S has a `previous` derived from the
    requester's entry S-1 (a `RESOLVED` witness), or `NONE` when S is 1,
    so a rollback never returns to "absent".
  - A rollback always writes `previous`, even a `NONE` the bootstrap
    left unwritten because a worktree lagged (bootstrap step 6: "never to
    absent"). The lagging checks run on every acquisition anyway.
  - An unreadable state file in any worktree makes the `OPEN` orphan test
    undecidable, so the literal is offered and can clear the witness.
  - The `amend_recovery` evidence is the proof object
    `assert_amendment_resolution_held` returns, passed to the staging
    entry. The held check takes (9), and the staging runs inside a guarded
    window, where (9) cannot be taken.
  - An owner's `advance_amendment_witness` with a journal raises
    `AmendmentResolutionHeldError` if the witness does not end `RESOLVED`
    with the pinned digest, and 6c1 then stops without closing the journal.
  - `milestone-implement.md` step 1d now states that `claim_checkpoint`
    returns the claim record (the token is its `owner_token` field). This
    session tripped on the old wording while claiming CP6: it recovered
    through the documented `CONTINUE_CLAIM` path, and the claim, the state
    write and the token are correct.

**Independent review of the implementation against section 5.6**
(a read-only review agent, before commit). Four defects were confirmed:
- **Fixed:** an unreadable state file made the `OPEN` orphan test refuse
  with no literal, and the literal itself could not clear it;
- **Fixed:** the impossible reservation case raised
  `AmendmentResolutionConflictError`, whose remedy is wrong; it is now
  `AmendmentWitnessUnavailableError` (INV-3);
- **Fixed:** a rollback could delete the witness;
- **Not fixed, a plan-level gap -- needs a decision in review:** an
  amendment written by a lagging `2.5.1` worktree becomes invisible once
  that worktree merges the `2.6.0` update. That merge is the remedy
  `LaggingWorktreeAmendmentError` names, but once the worktree stops
  lagging, section 5.6 reads no other worktree's state under a `NONE` or
  `RESOLVED` witness, and CP6 test 13d asserts exactly that. So a claim or
  an amendment request from another worktree is then admitted while that
  amendment is open. Closing this needs the plan to choose between
  (a) always scanning other worktrees' states (dropping test 13d's cost
  property), (b) re-bootstrapping (adopting the amendment as `OPEN`) when
  a worktree first stops lagging, or (c) narrowing the remedy to "finish or
  discard it before merging the update". The implementation follows the
  plan's text. The only change: that worktree's own request and
  reservation now refuse naming the unrecorded amendment, instead of the
  wrong "merge the resolved amendment first" (regression test
  `test_an_updated_worktree_names_its_own_unrecorded_amendment`).

The reviewer also noted, without calling it a defect: with no witness,
the lag checks run before the bootstrap, as test 13g requires. So a lagging
worktree's stale unresolved entry blocks every lifecycle operation for the
item until it updates, whereas the same state under an existing witness
passes. The outcome depends on order, and the plan could settle it
explicitly.

**Verified state.** Run in a temporary Git repository composed from the
`2.5.1` payload plus this overlay:

- `workflow_state_test`: 959 tests, 2 errors (1 skipped: the pin against
  the real `release._version_key` runs only where `workflow_manager` is
  importable; run separately with `PYTHONPATH=src`, it passes). The 2
  errors are the same two `TestCanonicalStateSerialization` live-state
  errors as CP2-CP5.
- `workflow_acceptance_matrix_test`: 280 tests, OK (18 skipped). That is
  the 262 CP5 rows, all through the extended driver, plus the 18 new ones.
- `workflow_integration_test`: 267 tests, 3 errors. These are the same
  three `TestRetiredScopedRemediationLeavesNoLiveSurface` errors.
- `workflow_fingerprint_test` + `workflow_fingerprint_generalization_test`:
  342 tests, OK.
- Demo/harness/obligations suites: 40 failing, identical test for test to
  the pure `2.5.1` payload.
- Both `verify_372h_*.py` scripts pass standalone: 9 primitives, 12
  code-derivable plus 4 orchestrated edges, 9/7, acyclic, and every
  regression including the new `(9)→(8)` one.
- Every overlay payload file (29) is matched by exactly one
  `classification.json` rule.
- `python3 tests/run_all.py --fast`: all green.
- INV-9: `git diff b2060bf -- distribution/workflow/` is empty.

### CP7 — Compose the `2.6.0` release

Implements the plan's CP7 and section 6.2 (requirement `REQ-10`).

- `migration/overlays/2.6.0/classification.json` was already complete: each
  of the 29 overlay payload files is matched by exactly one rule, so
  nothing changed there.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0`
  composed `distribution/workflow/2.6.0/`: 63 artifacts (39
  `distribution`, 22 `conformance`, 2 `host-evidence`), 6 templates, 29
  `overlay_replaced`, 0 `overlay_added`, `overlay_commit` `736e170`
  (CP6). The `--check` run reproduces it byte for byte.
- `tests/support.py` `CI_SUITES["2.6.0"]`, counted from the composed
  payload's own suites. Five suites differ from `2.5.1`: fingerprint 242,
  state 959, integration 267, acceptance matrix 280 and generalization
  100. Harness (19) and obligations (106) are unchanged.
  Total 1973, or 292 more than `2.5.1`'s 1681. The same loader count
  reproduces the pinned `2.5.1` values.
- `migration/portability_exceptions.json` gets the empty
  `by_version["2.6.0"]`. No genuine exception arose.
- Per-release classes: `TestConformanceFixture260` and
  `TestBootstrappedTarget260` (`tests/test_conformance_suite.py`),
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite260`
  (`tests/test_bootstrap_e2e.py`), and
  `TestReadmeStatusTableMatchesCiSuites.test_2_6_0_row_matches_ci_suites`
  (`tests/test_internal_references.py`). Because five suites move, its "new
  cases" is the whole-release delta against `2.5.1`, not `2.5.1`'s
  two-suite sum.
- `README.md`: `2.6.0` Status row and rebuild commands. `docs/MIGRATION.md`:
  new "Workflow v2.6.0 — an authored release" record with its own downgrade
  posture. `CLAUDE.md`: the authored-release list, plus the `2.6.0`
  downgrade paragraph. That paragraph cites CP3's and CP6's mechanical
  finding (ignored, not rejected, so the failure is silent), lists section
  6.2's five conditions, and states the mixed-release posture.
- `docs/defects/v2.4.0-001`, `-002` and `-003` each get a status-line
  update and a "`2.6.0` disposition" section citing their tests. `-001`:
  closed, plus the out-of-scope process-item update hazard (section 3.2).
  `-002`: closed, qualified, with section 5.6's residual quoted verbatim.
  `-003`: closed (repair form 1).
- **CP6 test portability defect, found by this checkpoint's full run and
  fixed in the overlay.** Eight git calls in CP6's `workflow_state_test.py`
  tests (`TestRepoGlobalLifecycleClaimAndAmendment`,
  `TestAmendmentWitnessCrashRecovery`, `TestAmendmentWitnessUpgradeBootstrap`,
  `TestAmendmentBootstrapResolutionFork`) named the branch `main` literally.
  `ScratchRepo`'s `git init -q` names it from `init.defaultBranch`, and the
  conformance harness isolates git config (`GIT_CONFIG_GLOBAL=/dev/null`,
  `tests/support.py`), so it was `master` there. The result was 7 errors
  against both the fixture and the bootstrapped target. CP6's narrow checks
  had passed only under a global config that sets `main`. A new
  `_primary_branch(root)` helper (`git symbolic-ref --short HEAD`) replaces
  every literal. The test count is unchanged (959), no assertion changed,
  the shared base `ScratchRepo` fixture is untouched, and
  `distribution/workflow/2.6.0/` was rebuilt from the overlay. It is not a
  portability exception: the test was wrong, so `by_version["2.6.0"]`
  stays empty.

**Verified state.**

- `python3 tests/run_all.py` (full, non-`--fast`), after the CP6
  test-portability fix above: 11/11 files OK, including
  `test_conformance_suite.py` (1360.8s: `TestConformanceFixture260` and
  `TestBootstrappedTarget260` green, 1973 tests) and
  `test_bootstrap_e2e.py` (665.4s:
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite260`'s failure set
  equals the empty `by_version["2.6.0"]`). The README row's values
  (1973, +292, 1973 of 1973) come from this run. The run before the fix
  failed exactly as described above: 3 conformance failures and 1
  bootstrap-e2e failure, all caused by the branch-name literal.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check`:
  reproduces `distribution/workflow/2.6.0/` byte for byte.
- `python3 tools/migrate.py --check`: OK.
- INV-9: `git diff b2060bf -- distribution/workflow/2.5.1/` is empty.

### CP8 — Disposable-repository and linked-worktree acceptance

Implements the plan's CP8 (requirements `REQ-1` to `REQ-9` and `REQ-11`
end to end). New `tests/test_workflow_2_6_0_hardening_disposable_repo.py`,
registered in `tests/run_all.py`'s slow tier next to the `2.5.0`
disposable suite.

**How it drives the installed release.** Every test installs real
releases with `workflow_manager.install.bootstrap`/`update`. Every step
then runs in a subprocess whose `sys.path` starts with that checkout's own
installed `scripts/`, so a `2.5.1`→`2.6.0` update mid-test really switches
bytes, and a lagging linked worktree really runs `2.5.1`. The
command-shaped drivers are the installed release's own acceptance-matrix
harness (`Scratch`/`Item`, part of the `full` profile), pointed at the
installed repository. The module adds only:

- `Item` re-pointed at a chosen work-item id, so several items coexist;
- review feedback written the way `/review-plan` writes it, through the
  release's own guard and resolver;
- the command steps the harness does not wrap: `/record-manual-plan-review`
  steps 4-7, `/review-plan`'s `REVISE`, `/apply-plan-review`'s entry;
- for `2.5.1` checkouts, their own amendment request and resolution, which
  the `2.5.1` harness predates.

`src/workflow_manager/fixture.py`, `tools/` and `pyproject.toml` are
unchanged.

**One class per scenario** (18 tests):

1. Two concurrent fresh items write local plan-review feedback at
   `.ai-review/<id>/feedback/`, never the flat directory.
   `--resolve-feedback-path` prints exactly `resolve_feedback_path_contract`.
2. A `2.5.1` item runs to `MILESTONE_COMPLETE`, leaving flat feedback.
   After the update, a new item's local review lands at its scoped path,
   and A's file is byte-identical.
3. A `2.5.1` item waits at `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW` with an
   unconsumed flat `REVISE`, and the update is committed.
   `/record-manual-plan-review` and `/apply-plan-review` both resolve the
   flat file. The item goes to `REVISING_PLAN` with a `CONSUMED` record,
   then back to `AWAITING_LOCAL_PLAN_REVIEW`, bound at revision 2.
4. `2.3.1` and `2.4.0` product items run without a local exclude, and the
   update is committed. `implementing_entry_reachable` holds, the plan
   digest equals the recorded approval, and the implementation digest
   equals its pre-update value. A novel committed path still raises
   `UnclassifiedPathError`. The control arm runs the base release's own
   bytes against the same history:
   - `2.3.1` wedges at both stages;
   - `2.4.0` wedges only at the implementation stage, because its
     generator already excluded `.workflow-manager/` at the plan stage.
5. Both section 3.3 variants, stale `TEST_RESULTS.md` and stale
   `REVIEW_REQUEST.md`, after the publish:
   - the item stays at `REVISING_PLAN`, row 9 (`PUBLISHED_UNBOUND`);
   - `current/` is byte-identical, with no `REJECTED` and no staging
     leftovers;
   - the reader refuses;
   - the re-run binds at revision 2, a single bump.
6. A brand-new, untracked protected companion:
   - the approval commit contains it;
   - the identity recomputed from that commit equals the approved one;
   - exactly one approval commit exists;
   - the worktree is clean.
   This holds in session, and after a crash right after the commit, when a
   new process takes the transaction over and completes it.
7. Three tests:
   - *Fresh `2.6.0`, two worktrees.* Claim first, and the amendment refuses
     with `AmendmentCheckpointActiveError`, naming the claimant. Amendment
     first, and the claim refuses with `AmendmentInFlightError` while the
     claimant's own state says `IMPLEMENTING`, with nothing published. Once
     the amendment resolves, the unmerged worktree gets
     `StaleLifecycleStateError` ("merge the resolved amendment first") and
     is admitted after the merge.
   - *Mixed release.* A lagging worktree alone refuses nothing, and no
     `NONE` sentinel is written. Its `2.5.1` amendment request makes an
     updated claim refuse with `LaggingWorktreeAmendmentError` (evidence:
     worktree, branch, `2.5.1`, seq 1), still with no sentinel.
   - *Resolution.* `main` and `b` carry the same open amendment and approve
     different amended plans:
     - `main` dies right after 4d, so `b` refuses with
       `AmendmentResolutionReservedError`;
     - `main`'s takeover rolls back and releases, then `main` re-approves;
     - the witness is `RESOLVED` with `main`'s committed resolution digest;
     - `b` then refuses with `StaleLifecycleStateError`;
     - exactly two approval commits exist (round 1 plus one resolution).

     A lagging worktree carrying the same open seq resolves it unreserved
     with its `2.5.1` scripts and a different plan. The next `2.6.0` claim
     refuses with `AmendmentResolutionConflictError` (recorded = the
     winner's digest), and the witness stays unchanged.
8. During an open amendment, `AMENDMENT_DIFF.patch` is non-empty and shows
   the uncommitted amended plan. The archive member is byte-identical.
9. Four `2.5.1` items are caught by the update. Their committed state blob
   is unchanged by the update commit.
   - `IMPLEMENTING` completes `CP2`.
   - `AWAITING_LOCAL_PLAN_REVIEW` passes the bound-bundle reader with
     nothing back-filled, then records the local `APPROVE`.
   - `AMENDING_PLAN` has no witness before the first (9) holder. Its
     entry marker is the non-legacy `CONSUMED` record from the superseded
     approval. It resolves through `/approve-review plan`, and the witness
     ends `RESOLVED` at seq 1.
   - `REVISING_PLAN` mid-apply works as follows:
     - a publish before the entry refuses with
       `LegacyPlanReviewBindingUnknownError`;
     - the entry writes the legacy marker at revision 1;
     - a same-revision publish then refuses with
       `ConsumedPlanReviewContentError` and writes no state;
     - one advance binds at revision 2.

Plus `TestClosedDefectCensus`:

- the named `v2.3.1-001`/`-002`/`-003` tests (section 3.8) exist in the
  composed payload;
- they pass in an installed `2.6.0` repository: 44 tests, one skip, the
  host-note test, which skips by design without RepFlow's note;
- `by_version["2.6.0"]` is empty, `TestBootstrappedTarget260` exists, and
  `test_amendment_update_path.py` is still in the fast tier;
- `v2.3.1-003` is re-proved end to end: a first approval with no state file
  at `HEAD`, through `verify_plan_approval_commit`, commits the state as
  `100644`.

**Payload defects found: none.** No scenario exposed a payload defect, so
the overlay, `distribution/workflow/2.6.0/` and the CI counts are
untouched.

**Two expectations were corrected against the plan text.** Both times the
engine was right and the first draft of the test was wrong:

- **Scenario 9.** Section 6.1 names `LegacyPlanReviewBindingUnknownError`
  for the refusal *before* the marker exists. After the marker, the
  same-revision refusal is `ConsumedPlanReviewContentError`. The test now
  pins both.
- **Scenario 7.** A resolver that dies *after* its approval commit does not
  leave `AmendmentResolutionReservedError` for the other worktree: the
  committed resolution is visible, so predicate step 1 self-heals the
  witness to `RESOLVED`, and the other side gets `StaleLifecycleStateError`
  (CP6 test 8). So the test crashes the resolver after 4d instead.

**Observation, not fixed:** `fixture.drive_synthetic_work_item_through_checkpoints`
cannot drive a `2.6.0` target. Its publish passes no `review_content_id`,
which `2.6.0` requires for a two-stage item (`TypeError`). No test asks it
to; it is used only against `2.3.1`/`2.4.0`.

**Verified state.**

- `python3 tests/test_workflow_2_6_0_hardening_disposable_repo.py`:
  18 tests, OK (about 28s).
- `python3 tests/run_all.py --fast`: all green.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check`:
  reproduces `distribution/workflow/2.6.0/` byte for byte.
- INV-9: `git diff b2060bf -- distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/`
  is empty.
- The new test file and `tests/run_all.py` classify as
  implementation-stage protected (`tests/`) under this item's declaration.

### CP9 — Full regression, release parity and closed-defect regression verification

Implements the plan's CP9 (requirements `REQ-9` and `REQ-10`). This
checkpoint is verification-only and writes no artifact. No disagreement was
found, so no owning checkpoint needed a fix.

**Verified state** (all run in this checkpoint, from `HEAD` `813ac82`):

- `python3 tests/run_all.py --fast`: all 8 fast suites OK.
- `python3 tests/run_all.py` (full): all 12 suites OK, exit 0.
  `test_conformance_suite.py` took 1336.6s, `test_bootstrap_e2e.py` 666.9s,
  `test_implementation_review_two_stage_disposable_repo.py` 11.4s and
  `test_workflow_2_6_0_hardening_disposable_repo.py` 28.0s.
- Clean-target failure set: `TestBootstrappedTarget260` and
  `TestBootstrappedRepositorySatisfiesTheFrozenSuite260` passed. Both
  assert that the failure set equals `by_version["2.6.0"]` exactly, and
  that set is empty. `TestConformanceFixture260` passed its per-suite count
  equality against `CI_SUITES["2.6.0"]`.
- `python3 tools/build_release.py --overlay migration/overlays/2.6.0 --check`:
  `distribution/workflow/2.6.0/` matches a fresh build from base `2.5.1`
  plus the overlay.
- `python3 tools/migrate.py --check`: `distribution/workflow/2.3.1/` matches
  a fresh extraction of the frozen upstream release.
- INV-9: `git diff b2060bf -- distribution/workflow/{2.3.1,2.4.0,2.5.0,2.5.1}/`
  is empty (0 lines).
- README's `2.6.0` row reads "7/7 suites, 1973 tests ... 1973 of 1973".
  That agrees with `CI_SUITES["2.6.0"]`
  (242 + 959 + 19 + 267 + 280 + 106 + 100 = 1973 across 7 suites) and with
  the empty `by_version["2.6.0"]`. The conformance run above asserts both.
- `v2.3.1-001/-002/-003` (`REQ-9`): still regression-protected by CP8's
  census tests, which passed in the full run.

**Process note.** The first `--fast` run overlapped the full run, which was
regenerating `distribution/`, so `test_disposable_repo_fixtures.py` briefly
saw no `2.3.1/manifest.json`. That was a harness collision, not a defect.
Run on its own afterwards, `--fast` passed, and the full run's own fast
tier passed too.

The unrelated working-tree changes to `.gitignore`,
`.workflow-manager/installation.json` and `docs/ROADMAP.md` were there
before this checkpoint. They were left untouched and not committed.

## Implementation review round 1 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `9b929aeb…93c6`, `review_content_id`
`b70c675f…b308`, `implementation_revision` 1. It had no Blocking findings
and five Important ones. Each was reproduced before any change, with a new
test that fails on the reviewed code. All five are fixed in the `2.6.0`
overlay, and the release was rebuilt.

- **Important 4 (CP2): non-UTF-8 protected content.** Fixed.
  `AMENDMENT_DIFF.patch` is now captured and written as bytes.
- **Important 5 (CP2): git-config sensitivity.** Fixed. Every option that
  shapes the patch is pinned on the command line: `--literal-pathspecs`,
  `--no-ext-diff`, `--no-textconv`, `--no-color`, `a/` `b/` prefixes,
  `--no-renames` and `--binary`. The new test regenerates under a hostile
  `GIT_CONFIG_GLOBAL` (`noprefix`, `mnemonicPrefix`, `renames = copies`,
  an external diff and `color = always`). The patch must be
  byte-identical and still pass `git apply --check`.
- **Important 1 (CP4): re-bound content reaching plan approval.**
  **Partially resolved.** The user dispositioned this on 2026-09-25.
  - Closed: the stale-approval shortcut. `apply_plan_approval` refuses a
    `TWO_STAGE_PLAN_REVIEW_VERSIONS` item at any phase other than
    `AWAITING_PLAN_APPROVAL` (`PlanApprovalPhaseError`, `799b80d`), and
    `approve-review.md` step 0 says so.
  - Still open: withdraw → detour → restore can re-bind the same
    `review_content_id` for a *fresh* review, and both stages must then
    approve it again. Section 5.3's "never re-binds" wording, and the
    recovery-table row that mirrors it, remain stronger than the
    implementation.
  - Why it stays open: enforcing that wording needs a design/schema change,
    such as a consumed-content history. Plan revision 8 pins `consumed` as a
    single slot. The change cannot be introduced while this item is at
    `APPLYING_REVIEW_FEEDBACK`, because `/request-plan-amendment` accepts
    only `IMPLEMENTING`/`SELF_REVIEWING_IMPLEMENTATION`. The user directed
    that no consumed-history schema be invented in this round.
  - Mandatory follow-up: recorded as
    `docs/defects/v2.6.0-001-withdrawn-plan-content-can-rebind-after-a-detour.md`,
    which names both acceptable resolutions (enforce, or narrow normatively)
    and the regression test either one must satisfy.
- **Important 2 (CP6): unreadable committed state wedging the witness.**
  Fixed. An unreadable committed `WORKFLOW_STATE.json` in another worktree
  now makes the test undecidable. The refusal carries the evidence-bound
  literal, and the literal clears it. This covers every read that
  previously raised: `RESOLVING` step 1 (resolver `HEAD`, resolver branch
  tip), step 2a (`_resolution_visible_anywhere`, which now also returns
  the unreadable reasons), `clear_amendment_resolution`'s scan, and the
  `OPEN` orphan test's branch-tip and requester reads.
- **Important 3 (CP6): upgrade-topology wedge.** Fixed. While the witness
  is absent, a lagging worktree's unresolved entry counts as recorded if
  the bootstrap would record the same entry (same seq, request projection
  and `amendment_base_commit`) from a `2.6.0` worktree: any non-lagging
  one, or the evaluating one. Both reported topologies are tests now.
  An entry held only by lagging worktrees still refuses (plan test 13g,
  unchanged). A lagging worktree whose working tree already carries the
  update is told to commit it, not to merge it.

Optional findings:

- **Applied:**
  - 1: the archive includes `AMENDMENT_DIFF.patch` at the plan stage only.
  - 3: `--literal-pathspecs`.
  - 4: the gitignored-new-protected-file gap is documented in
    `prepare-ai-review.sh`.
  - 5: `--no-renames` on the empty-index and post-staging checks.
  - 7: the witness publish fsyncs its directory.
  - 8: `request_plan_amendment_transaction` rolls the `OPEN` witness back
    when the state publish raises. It does not roll back if the state
    already holds the entry or cannot be read.
  - 10: `apply-plan-review.md` step 5 notes the forced revision advance
    for a legacy-marked item.
  - 11: the overlay classification says 12 named errors.
  - 12: `docs/MIGRATION.md` now says `2.4.0` is recorded.
- **Not applied, with reasons:**
  - 2: a failure-injection test for `PlanStagePromotionError`, and the
    skipped `clear_rejected_marker_if_present` on a late cleanup failure.
    This needs a promotion-crash harness. The skipped marker clear fails
    safe: the next generation clears it.
  - 6: re-checking 6a1's re-staged members against
    `review_content_manifest`. The post-amend verification already
    refuses a drifted member. The cost is one wasted amend attempt, not a
    wrong commit.
  - 9: a `git stash` of committed-but-unapproved `AMENDING_PLAN` state.
    This is a residual to document through the amendment above, alongside
    section 5.6's other residuals.
  - 13: CP8 concurrency depth. REQ-7's concurrency evidence stays with
    CP6's real-process race tests, as the reviewer notes.

The counts move from 1973 to 1989 (+16): `workflow_state_test.py` from 959
to 972, and `workflow_fingerprint_generalization_test.py` from 100 to 103.
`tests/support.py` and `README.md` are updated to match.

## Implementation review round 2 (`MANUAL_EXTERNAL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `2629fcaf…6f4e`, `review_content_id`
`11b4eac4…64bf`, `implementation_revision` 2.
`LOCAL_MODEL_IMPLEMENTATION_REVIEW` round 2 had approved the same content.
The reviewer accepted Important 1's partial disposition and found Important
2-5 resolved. There were no Blocking findings and one new Important one.

- **I1 (CP5): approval staging and closure were not literal- or
  byte-safe.** Fixed. Reproduced first against the reviewed code:
  - An absent `*.md` removal member made `git rm --cached -- '*.md'` unstage
    every tracked Markdown file, which is worse than the review described.
  - A present `*.md` member staged a worktree-edited `a.md`.
  - A non-ASCII member came back C-quoted from `--name-only`.

  Every case refused (`UnexpectedStagedPathSetError`,
  `CommittedPathSetMismatchError`).

  Now:
  - `stage_plan_approval_commit_paths` runs `git add`/`git rm --cached`
    under `--literal-pathspecs`.
  - The empty-index, post-staging and post-commit path-set checks read
    `-z` output through `_git_path_set`, which decodes with `os.fsdecode`.
  - The new `assert_staged_path_set_within` backs `/approve-review` step
    6.3, so the operator never compares quoted output by eye.
  - `_snapshot_commit` and the tracked-metadata checks use
    `--literal-pathspecs`, so a leading-`:` member is not read as pathspec
    magic.

  The same defect sat at two more boundaries a declared path crosses, and
  both are fixed too:
  - `prepare-ai-review.sh`'s untracked-file `git add -N` and its exit-trap
    `git reset`. The reset could also unstage unrelated staged files that
    matched a glob-named untracked file.
  - `/milestone-plan` step 3's intent-to-add instruction.

  `approve-review.md` steps 4a, 6.3 and 6d follow. New
  `PlanApprovalClosureLiteralPaths` (5 rows) drives the real
  `Item.approve_plan` with these members:
  - an ASCII control;
  - `docs/ai-workflow/*.md`;
  - `[DW]ECOY.md` and `:WI_MAGIC.md`;
  - `désign.md`;
  - an absent `*.md` removal member.

  Each row asserts the exact committed member set, and that a tracked,
  worktree-edited decoy the glob would match stays unstaged and
  uncommitted.
- **O1 applied.** `AMENDMENT_DIFF.patch` pins `-U3`, and its `git diff`
  runs with `GIT_DIFF_OPTS` removed. A mid-file edit under
  `diff.context=0` plus `GIT_DIFF_OPTS=--unified=0` stays byte-identical
  and `git apply --check`-clean. The new test fails without the fix.
- **O2 applied.** The current-only-form oracle pins the implementation's
  own diff options.
- **O4 applied.** The `v2.6.0-001` defect record now lists
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md` among the documents to reconcile.
- **O3 not applied.** Aligning `_bootstrap_derivable_entries` with the
  RESOLVED-witness asymmetric topology changes CP6's derivation rule, not a
  boundary. The current refusal fails closed and the documented remedy
  (merge the update into the lagging worktree) works. The reviewer rated
  it a later cleanup.
- **O5 not applied.** Each remaining bare `LifecycleStateUnreadableError`
  site needs its own remedy text and test. It fails closed today.

The counts move from 1989 to 1995 (+6):
- `workflow_acceptance_matrix_test.py`: 280 → 285.
- `workflow_fingerprint_generalization_test.py`: 103 → 104.

## Implementation review round 3 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `1cba8013…f9f34`, `review_content_id`
`3bb5e04c…dcda`, `implementation_revision` 3. It had no Blocking findings
and one Important finding, the residual of round 2's I1.

- **I1-residual: `load_pre_amendment_snapshot` read a declared path as
  a pathspec.** Fixed. Reproduced first: with both `x` and `:x` tracked,
  `git ls-tree HEAD -- ':x'` returns `x`'s blob, so an amended approval
  with a legal `:`-leading `plan_path` was refused
  (`AmendmentPreSnapshotUnreproducibleError`). For `:(glob)…` and `:!…`
  it was a Git error instead. The cross-check now runs `git
  --literal-pathspecs ls-tree`. There are two new regressions:
  - `AmendedApprovalLiteralMetadataPath` drives a real amended approval
    whose `plan_path` is `:proc-item-plan.md`, with a tracked decoy
    `proc-item-plan.md`.
  - `DeclaredPathGitReads` calls the function directly with `:plan.md`,
    `:(glob)*.md` and `:!plan.md`.

  Both fail with the fix reverted.
- **Re-sweep (acceptance criterion 2).** I checked every `git … --
  <path>` and `<rev>:<path>` call in `workflow_state.py`,
  `workflow_fingerprint.py` and `prepare-ai-review.sh`:
  - The rest of the plain `--` calls pass a fixed constant, not a declared
    path: the state path, the `scripts/` and `.claude/commands/` surface
    prefixes, or `.`.
  - `<rev>:<path>` reads are literal, because the path grammar rejects
    `.`/`..` components and a leading `/`.

  The sweep found one more defect in the same class:
  `verify_staged_blob_sha256` read `:<path>`, and Git parses `:0:x.md` as
  index stage 0 of `x.md`. A fifth member named `0:x.md` was therefore
  checked against the wrong blob. It now reads `:0:<path>`. The new
  `DeclaredPathGitReads` row fails with this fix reverted.
- **O1 applied, with a narrowed premise.**
  `workflow_fingerprint.literal_pathspec_env()` drops
  `GIT_GLOB_PATHSPECS`/`GIT_NOGLOB_PATHSPECS`/`GIT_ICASE_PATHSPECS` for
  every `--literal-pathspecs` call. `prepare-ai-review.sh` unsets them
  once, which also covers the Python it runs.

  The review said 2.5.1 worked under all three modes. That holds only for
  `GIT_NOGLOB_PATHSPECS`. `git ls-tree` rejects glob/icase magic outright
  ("pathspec magic not supported by this command"). 2.5.1's own plain
  `ls-tree -- <path>` reads (the identity-reference scan on
  `route_work_item`, and `_snapshot_commit`) therefore already failed
  under the other two. The lifecycle row pins the real regression
  (`GIT_NOGLOB_PATHSPECS`). A per-call-site row covers all three modes on
  the literal reads, and the generator row covers all three plus
  `GIT_DIFF_OPTS`. Full-lifecycle support for glob/icase modes would
  scrub every Git call. That is a pre-existing limitation outside this
  item.
- **O2 applied.** The dead journal term is removed. A new row commits
  tab, double-quote and backslash members exactly.
- **O3 applied.** The generalization oracle's `_git` scrubs
  `GIT_DIFF_OPTS` and the conflicting pathspec modes. The new row fails
  with the scrub reverted.
- **O4 applied.**
  - `approve-review.md` and `DirtyIndexBeforeStagingError` now recommend
    `git --literal-pathspecs restore --staged`.
  - `milestone-plan.md` step 5.3 and `apply-plan-review.md` now say `git
    --literal-pathspecs add -N`.
  - The empty-index check is credited to
    `assert_plan_approval_index_clean`.

  The matrix harness's own step-3 simulation (`Item.stage_plan_files`)
  was still a bare `git add -N`. It is now literal to match.

The counts move from 1995 to 2002 (+7):
- `workflow_acceptance_matrix_test.py`: 285 → 291.
- `workflow_fingerprint_generalization_test.py`: 104 → 105.

## Implementation review round 4 (`LOCAL_MODEL_IMPLEMENTATION_REVIEW`, `REVISE`)

Feedback bound to bundle `6855d548…a3e`, `review_content_id`
`4472240b…6ab`, `implementation_revision` 4. It had no Blocking findings
and one Important finding. The round-3 fixes were confirmed load-bearing
by mutation.

- **I1: `docs/MIGRATION.md`'s `2.6.0` record was stale and unpinned.**
  Fixed. Reproduced first: the record still quoted round 1's
  `overlay_commit` (`736e170`, "the CP6 commit"), 1973 fixture tests, the
  per-suite deltas `853→959`, `146→280` and `79→100`, and "1973 of 1973".
  The shipped manifest and `CI_SUITES["2.6.0"]` say `a886069`, 2002
  (+321), `853→972`, `146→291`, `79→105` and "2002 of 2002". The two
  existing pin classes hard-code `2.4.0`, so nothing caught this.
  - The record now matches, and the provenance sentence no longer claims
    the CP6 commit.
  - New `TestAuthoredReleaseMigrationRecordMatchesShippedEvidence` in
    `tests/test_internal_references.py`. It is table-driven by release
    and scoped to each release's own `## Workflow v<version>` section. It
    pins the Base release, Provenance JSON, Overlay counts, Manifest
    counts (per category), the fixture total, the "plus N new cases"
    delta, every quoted per-suite `a→b` (and that exactly the moved
    suites are quoted), and the bootstrapped row. It checks them against
    the manifest, `CI_SUITES` and `expected_portability_exceptions`.
    Against the stale text it failed three tests: provenance, fixture and
    bootstrapped.
  - The pin then did its job within this round. Each O1/O2 rebuild moved
    `overlay_commit` (to `cc12398`, then `201c82d`), and the provenance
    test failed until the record was updated in the same commit.
- **O1 applied.** The `git mv` row of `PlanApprovalClosureMembers` now
  runs the remedy exactly as printed: `git --literal-pathspecs restore
  --staged`.
- **O2 applied.** `approve-review.md`'s remedy text says the three
  pathspec-mode variables must be unset, because Git refuses
  `--literal-pathspecs` combined with any of them.
  `TestGoldenCommandFileHashes`' recorded hash for that file is
  re-recorded (`644b1cd6…` → `65d60c81…`), in a separate commit.

The suite counts are unchanged at 2002. `test_internal_references.py`
gains six tests.

## Functional review checklist

Technical approval: commit `7175de8` (implementation revision 5, basis
`EXTERNAL_APPROVE`). You are testing the composed `distribution/workflow/2.6.0/`
release as an operator would use it: installed into a throwaway repository.
Put findings in `.ai-review/feedback/FUNCTIONAL_REVIEW.md`.

**Setup.** From this checkout:

```bash
export M=~/Workspace/workflow-manager PYTHONPATH=~/Workspace/workflow-manager/src
export T=$(mktemp -d)        # every flow below works under $T
```

No feature flags. The only test data is the throwaway repositories and work
items each flow creates.

**All seven flows are required**, in order. Flows 4-6 build on each other:
flow 4 creates work item `<A>`, flow 5 leaves `<A>` at
`AWAITING_LOCAL_PLAN_REVIEW` with its amendment still open, and flow 6 uses
a second item `<B>`. Replace `<A>`/`<B>` with the ids
`/milestone-plan` reports.

Flows 1-3, flow 4.0's seed, flow 4.3's direct-writer refusal and flow 7 were dry-run while
this checklist was prepared. The rest of flows 4-6 state the documented
`2.6.0` contract.

1. **Release is present and reproducible.**
   - `python3 -m workflow_manager --manager-root $M releases` lists `2.6.0
     ... [authored]`.
   - `python3 $M/tools/build_release.py --overlay $M/migration/overlays/2.6.0 --check`
     exits 0.
   - Expected: both succeed; nothing under `$M` changes (`git -C $M status`).
2. **Fresh install.**
   ```bash
   git init -q $T/a && git -C $T/a commit -q --allow-empty -m init
   python3 -m workflow_manager --manager-root $M bootstrap $T/a
   python3 -m workflow_manager --manager-root $M status $T/a
   python3 -m workflow_manager --manager-root $M verify $T/a
   cd $T/a && git add -A && git commit -qm "install 2.6.0"
   python3 scripts/workflow_fingerprint.py --resolve-feedback-path demo-item
   ```
   - Expected: `bootstrapped workflow 2.6.0 (full)`, 62 managed files;
     `status` says `clean`; `verify` says `installation matches workflow
     2.6.0`.
   - Expected: the last command prints one JSON object with `"layout":
     "legacy-flat"` and `.ai-review/feedback/...` paths. There is no state
     entry for `demo-item`, so the legacy rule applies.
3. **Update from `2.5.1`; the installation record no longer wedges
   classification** (`v2.4.0-001`, CP1).
   ```bash
   git init -q $T/b && cd $T/b && git commit -q --allow-empty -m init
   python3 -m workflow_manager --manager-root $M --release-version 2.5.1 bootstrap .
   git add -A && git commit -qm "install 2.5.1"
   python3 -m workflow_manager --manager-root $M update . && git add -A && git commit -qm "update 2.6.0"
   python3 -m workflow_manager --manager-root $M verify .
   python3 -c "import sys; sys.path.insert(0,'scripts'); import workflow_fingerprint as wf
   print(wf.classify_path('.workflow-manager/installation.json', frozenset(), {}, {}))
   print(wf.classify_path_implementation_stage('.workflow-manager/installation.json', {}, {}, {}, {}))
   wf.classify_path('.workflow-manager/other.json', frozenset(), {}, {})"
   ```
   - Expected: `updated . to workflow 2.6.0`; `verify` matches `2.6.0`.
   - Expected: `excluded` twice, then `UnclassifiedPathError` for
     `other.json`. The fallback covers exactly one path, not the directory.
   - Print order is not part of the check. When stdout and stderr are piped
     or captured, the traceback can appear before the two `excluded` lines.
     Pass if you see both `excluded` results and the `UnclassifiedPathError`
     naming `.workflow-manager/other.json`, in any order.
4. **Work item `<A>`: plan review through approval, driven by Claude Code
   in `$T/a`** (CP3, CP4, CP5).
   0. **Seed the milestone (test data).** A fresh install has no
      `docs/ROADMAP.md`, and its `docs/ACTIVE_MILESTONE.md` says "None".
      `/milestone-plan` with no argument decides what to plan from those two
      files, and its id argument only selects an *existing* item. So give it
      a milestone before you start:
      ```bash
      cd $T/a
      printf '# Roadmap\n\n## Next milestone: hello-file\n\nAdd a `hello.txt` file containing "hello". One checkpoint.\n' > docs/ROADMAP.md
      git add docs/ROADMAP.md && git commit -qm "roadmap: hello-file"
      ```
      Then open a Claude Code session in `$T/a`.
   1. **Declare a new protected companion before the bundle exists.** Run
      `/milestone-plan` with no argument. It plans `hello-file`; note the id
      it reports as `<A>`. Create `docs/<A>-notes.md` with any
      text, and do **not** `git add` it. Before the plan bundle is
      generated, make sure `docs/ai-workflow/registry/<A>-artifacts.json`
      lists `docs/<A>-notes.md` in `plan_stage.protected_paths`. Ask Claude
      to add it while it writes the declaration, or edit the file yourself
      before it generates. If you add it after the bundle is generated, you
      have edited reviewed content, and that needs a new review round.
   2. **Bound, scoped.** Once `/milestone-plan` reports the item at
      `AWAITING_LOCAL_PLAN_REVIEW`:
      - `python3 scripts/workflow_state.py --plan-review-publication-status <A>`
        prints one JSON object whose `status` is exactly `"BOUND"`.
      - `python3 scripts/workflow_fingerprint.py --resolve-feedback-path <A>`
        prints `"layout": "scoped"` and `.ai-review/<A>/feedback/...` paths.
      - `2.6.0` stages the plan author files in `plan-inputs/`. The
        generator copies them into the bundle; it doesn't write them into
        `current/`. Check both:
        ```bash
        ls .ai-review/<A>/plan-inputs/
        for f in REVIEW_REQUEST.md TEST_RESULTS.md CONTEXT_FILES.txt; do
          cmp .ai-review/<A>/plan-inputs/$f .ai-review/<A>/current/$f && echo "$f same"
        done
        ```
        Expected: `ls` lists at least `REVIEW_REQUEST.md`, `TEST_RESULTS.md`
        and `CONTEXT_FILES.txt`, and the loop prints `same` for all three.
   3. **Required refusal: plan review is in progress.** At that same
      `AWAITING_LOCAL_PLAN_REVIEW` phase, run both checks below. Neither may
      write anything: `git status --porcelain` and the `status` in step 2
      are unchanged afterwards.
      - The in-place writer refuses. This calls the same writer
        `/milestone-plan` and `/apply-plan-review` use to publish a plan
        revision, and discards the result:
        ```bash
        python3 -c "import sys,json; sys.path.insert(0,'scripts'); import workflow_state as ws
        s=json.load(open('docs/ai-workflow/WORKFLOW_STATE.json')); w=s['work_items']['<A>']
        ws.publish_plan_revision(s,'<A>',w['plan_revision']+1,'2026-01-01T00:00:00Z',review_content_id='0'*64)"
        ```
        Expected: `PlanReviewInProgressError`, naming `<A>`, the phase and
        `/milestone-plan <A>` as the withdrawal exit.
      - `/milestone-plan` with **no argument** refuses with
        `PlanReviewWithdrawalNeedsExplicitIdError`, before any write.
      - Do **not** run `/milestone-plan <A>` with the id here. At a ready
        phase, that form is the sanctioned withdrawal, not a refusal. It
        discards both review stages and would force a new round.
   4. **Scoped feedback.** `/review-plan <A>` writes
      `.ai-review/<A>/feedback/REVIEW_FEEDBACK.md`. Nothing new appears
      under `.ai-review/feedback/`.
   5. **Optional `REVISE` round.** If you give a `REVISE`, `/apply-plan-review
      <A>` reaches the next round with a single `plan_revision` bump.
      `.ai-review/<A>/current/` is replaced only when generation succeeds:
      no `.ai-review/<A>/current.staging-*` directory remains, and there is
      no `REJECTED` marker.
   6. **Required refusal: another item's manual feedback.** Once `<A>` is at
      `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, write
      `.ai-review/<A>/feedback/REVIEW_FEEDBACK.md` with
      `Reviewer role: MANUAL_EXTERNAL_PLAN_REVIEW`, `Status: APPROVE` and
      `Work item: some-other-item`, then run `/record-manual-plan-review <A>`.
      Expected: `ManualFeedbackForeignWorkItemError`, naming both
      `some-other-item` and `<A>`. The phase is still
      `AWAITING_MANUAL_EXTERNAL_PLAN_REVIEW`, and
      `docs/ai-workflow/WORKFLOW_STATE.json` is unchanged. Then paste a
      genuine manual verdict naming `<A>` and re-run the command to continue.
      `/record-manual-implementation-review` makes the same check
      (`assert_manual_feedback_names_work_item`); this flow exercises it
      through the plan-stage command only.
   7. **Approval closes over the companion.** `/approve-review plan <A>`
      creates exactly one approval commit.
      - `git show --stat HEAD` lists `docs/<A>-notes.md`, the file that was
        untracked until now.
      - `git ls-tree HEAD docs/<A>-notes.md` shows it in the committed tree.
      - `git status --porcelain` prints nothing. `.ai-review/` is ignored by
        the install's `.gitignore` fragment.
      - `<A>` is now at `IMPLEMENTING`.
5. **Open amendment on `<A>` shows the uncommitted plan** (CP2). Start from
   flow 4's end state: `<A>` at `IMPLEMENTING`. Do not run
   `/milestone-implement`. An amendment is only accepted from
   `IMPLEMENTING` or `SELF_REVIEWING_IMPLEMENTATION`.
   1. Run `/request-plan-amendment <A>`. `<A>` moves to `AMENDING_PLAN`.
   2. Edit `<A>`'s plan document, and do not commit the edit.
   3. Run `/milestone-plan <A>` while `<A>` is in `AMENDING_PLAN`. It
      generates the amended plan bundle, then publishes and binds it, so
      `<A>` moves to `AWAITING_LOCAL_PLAN_REVIEW`. The amendment stays open
      (unresolved) until an approval resolves it.
   4. Expected: `.ai-review/<A>/AMENDMENT_DIFF.patch` is non-empty
      and contains your uncommitted edit. Its leading `#` preamble names
      `work_item_id`, `amendment_id`, `amendment_base_commit`,
      `plan_revision` and `review_content_id`.
   5. The patch applies at `amendment_base_commit`. Copy that value from the
      preamble:
      ```bash
      git worktree add --detach $T/check <amendment_base_commit>
      git -C $T/check apply --check $T/a/.ai-review/<A>/AMENDMENT_DIFF.patch && echo applies
      git worktree remove $T/check
      ```
   6. Leave `<A>` here: at `AWAITING_LOCAL_PLAN_REVIEW`, with its amendment
      open and its plan edit uncommitted. Don't review or approve it. Flow 6
      does not use it.
6. **Two linked worktrees cannot race an amendment on `<B>`** (CP6,
   `v2.4.0-002`). A second item is needed because flow 5 deliberately left
   `<A>` at `AWAITING_LOCAL_PLAN_REVIEW`, with its amendment still open. A
   checkpoint claim is illegal there, and so is a second amendment request.
   Keep this setup order so that the merge in step 3 really brings `<B>`
   into the linked worktree:
   1. In `$T/a`, on `main`, create the linked worktree **before `<B>`
      exists**: `git worktree add $T/a-wt -b wt`.
   2. Still in `$T/a` on `main`, plan and approve a second tiny item `<B>`.
      - **Point the milestone documents at `<B>` first.** Otherwise a
        no-argument `/milestone-plan` resolves to `<A>`, which is at a ready
        phase, and refuses with `PlanReviewWithdrawalNeedsExplicitIdError`
        (flow 4.3's refusal). A brand-new id can't be passed as an
        argument. In `docs/ROADMAP.md`, mark `hello-file` as in progress
        (not next) and add `## Next milestone: bye-file` ("Add a `bye.txt`
        file containing "bye". One checkpoint."). In
        `docs/ACTIVE_MILESTONE.md`, replace the `## Milestone` section's body
        with `Next: bye-file (see docs/ROADMAP.md)`. Commit exactly those two
        files: `git commit -m "roadmap: bye-file" -- docs/ROADMAP.md
        docs/ACTIVE_MILESTONE.md`.
      - Run `/milestone-plan` with no argument. Expected: it creates a
        **new** item for `bye-file` (note its id as `<B>`) and leaves `<A>`'s
        entry untouched. If it refuses with
        `PlanReviewWithdrawalNeedsExplicitIdError` instead, the documents
        still resolve to `<A>`. Fix them and re-run. Never run
        `/milestone-plan <A>`.
      - Take `<B>` through the same review and approval sequence as flow 4:
        `/review-plan <B>`, a genuine manual verdict naming `<B>` via
        `/record-manual-plan-review <B>`, then `/approve-review plan <B>`.
        Skip only flow 4's companion document (4.1) and its refusal checks
        (4.3, and 4.6's foreign-feedback step).
      - Expected: `<B>` is at `IMPLEMENTING`. `git log -1 --format=%B`
        ends with `Workflow-Plan-Approval:` and `Workflow-Work-Item: <B>`.
        The index is clean (`git diff --cached --quiet` exits 0).
        `git status --porcelain` still lists `<A>`'s plan document as
        modified; that is flow 5's deliberately uncommitted edit, and it is
        expected.
   3. Bring `<B>` into the worktree: `git -C $T/a-wt merge --ff-only main`.
      Confirm that `$T/a-wt` sees `<B>` at `IMPLEMENTING`:
      ```bash
      python3 -c "import json; print(json.load(open('$T/a-wt/docs/ai-workflow/WORKFLOW_STATE.json'))['work_items']['<B>']['phase'])"
      ```
   4. The claim is taken and released with the same functions
      `/milestone-implement` calls at steps 1d and 1f, so no checkpoint has
      to be implemented. Run each of these from `$T/a-wt`. `<CP>` is
      `<B>`'s first checkpoint id, for example `CP1`.
      ```bash
      # CLAIM
      python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import workflow_state as ws
      print(ws.claim_checkpoint(Path.cwd(), '<B>', '<CP>', now='2026-09-26T00:00:00Z')['checkpoint_id'])"
      # RELEASE
      python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import workflow_state as ws
      ws.release_checkpoint(Path.cwd(), '<B>', '<CP>', owner_token=ws.resolve_claim(Path.cwd(), '<B>')['owner_token'], now='2026-09-26T00:00:00Z')"
      # SHOW
      python3 -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import workflow_state as ws
      print(ws.resolve_claim(Path.cwd(), '<B>'))"
      ```
   5. **Order 1, the claim first.**
      - CLAIM in `$T/a-wt` prints `<CP>`.
      - In `$T/a`, `/request-plan-amendment <B>` refuses with
        `AmendmentCheckpointActiveError`, naming `$T/a-wt` as the
        claimant. `<B>` stays at `IMPLEMENTING` in `$T/a`.
      - RELEASE in `$T/a-wt`, then SHOW prints `None`.
   6. **Order 2, the amendment first.**
      - In `$T/a`, `/request-plan-amendment <B>` succeeds, and `<B>` moves
        to `AMENDING_PLAN` in `$T/a`.
      - CLAIM in `$T/a-wt` refuses with `AmendmentInFlightError`, even
        though `$T/a-wt`'s own state still says `IMPLEMENTING` (check it
        with step 3's command).
      - SHOW prints `None`: no claim was published.
7. **Required: the automated disposable-repository suite.** This is part of
   the functional acceptance evidence, not an optional extra. It drives the
   cases a manual pass can't reach safely: in-flight `2.5.1` items at four
   phases being updated, an in-flight flat-feedback item, forced
   plan-bundle generation failures, mixed-release worktrees, and a crash
   followed by a takeover in a new process.
   ```bash
   python3 $M/tests/test_workflow_2_6_0_hardening_disposable_repo.py -v
   ```
   Expected: `Ran 18 tests`, then `OK` (about 30s). Record the final lines
   in your functional-review notes.

**Known limitations and out of scope.**
- Mixed-release worktrees remain unsupported. A `2.5.1` worktree that has
  not merged the update neither takes the lifecycle lock nor reads the
  witness; `2.6.0` only narrows that window. The authoritative record is
  the residual quoted in the `2.6.0` disposition of
  `docs/defects/v2.4.0-002-amendment-claim-race-crosses-worktree-boundary.md`,
  which is "closed, qualified" there. It is not `v2.6.0-001`.
- **Accepted follow-up, non-gating: `v2.6.0-001`** (withdrawn plan-stage
  content can re-bind after a detour;
  `docs/defects/v2.6.0-001-withdrawn-plan-content-can-rebind-after-a-detour.md`).
  `2.6.0` closes the stale-approval shortcut. It doesn't close the re-bind
  itself, which a later Workflow release must decide. **No flow in this
  checklist exercises it.** Flow 4.3 deliberately avoids the
  `/milestone-plan <A>` withdrawal. It stays covered by the automated
  tests in the `2.6.0` payload's `scripts/workflow_state_test.py`:
  `TestPlanApprovalPhaseGate` (including
  `test_withdraw_detour_restore_never_reaches_plan_approval`) and
  `TestConsumedPlanReviewBindingWriters`. The conformance suite runs both.
  Don't record the residual re-bind as a functional finding.
- Downgrading below `2.6.0` fails silently, not loudly. See `CLAUDE.md`'s
  `2.6.0` downgrade paragraph. Don't treat that as a finding.
- `fixture.drive_synthetic_work_item_through_checkpoints` cannot drive a
  `2.6.0` target (CP8 observation). Nothing uses it that way.
- **Known issue, non-gating:** `scripts/workflow_state.py
  --plan-review-publication-status <unknown-id>` exits 1 with a raw
  `KeyError` traceback, not a named refusal. It was observed while this
  checklist was prepared, and this checklist-only change deliberately
  leaves it unfixed. No required flow passes an unknown id. Record it as a
  finding only if you judge it matters, or if it blocks a required flow.
- This repository's own unrelated working-tree edits (`.gitignore`,
  `.workflow-manager/installation.json`, `docs/ROADMAP.md`) are not part
  of this milestone.

### Closing state at its acceptance (historical)

- **Blockers:** none. Important 1's residual was dispositioned as a
  mandatory follow-up (`v2.6.0-001`), not as a blocker.
- **Plan:** stays at
  `docs/ai-workflow/WORKFLOW_REVIEW_ARTIFACT_AND_CONCURRENCY_HARDENING_PLAN.md`
  (revision 8), because `docs/MIGRATION.md` and the shipped `2.6.0`
  payload's `WORKFLOW_V2_PLAN.md` cite it as a permanent design record.
- **Next action at the time:** `/milestone-plan`. The roadmap was realigned
  afterwards, in `db4c7af`.
