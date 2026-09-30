# Workflow Manager: Distribution Rework, Packaged Workflow Releases (Revision 9)

`work_item_id: workflow-manager-packaged-distribution` -- `governing_workflow_version: "2.2"`

**Deliverable:** a Workflow release becomes a versioned, checksummed,
immutable package that the Manager downloads, verifies, caches and installs.
Today's five releases (`2.3.1` to `2.6.0`) are each built into a package that
is proved byte-for-byte identical to its `distribution/workflow/<version>/`
tree. They are then published in a new `workflow` repository.
`distribution/`, `migration/` and the migration tooling leave this
repository. The test suite shrinks to the Manager's own code, the newest
published release in its three fixtures, and the upgrade path onto it. The
stopgap test profile (M1, `STOPGAP(M2)`) is removed.
**Governing workflow version:** `2.2` (the config default at creation).
**Work item type:** `process`, the same as M1 and M1b. This is this
repository's tooling; it creates no Workflow release.
**Base commit:** `ec389798dd8b5ef2d5da5ea6d654d10bc81784da` (tip of `main`,
M1b's squash merge `#10`). At the base, the installed Workflow is `2.6.0`
and protocol `2.2` is active. `main`'s full run
`36693049114` and the Release run `36694260604` are both green.
**Branch:** `milestone/workflow-manager-packaged-distribution`, created from
the base. One pull request reaches `main`.
**Scope source:** `docs/ROADMAP.md`, "At a glance" step **M2** and section
**10.2**, plus section 6, which M2 replaces. Also the stopgap removal record
in `docs/ARCHITECTURE.md`'s "Stopgap test profile".

**M2 publishes the existing releases as packages. It creates no new Workflow
version and changes no byte of any release (INV-1).** The first new version
is W1, Workflow 2.7, which is built in the `workflow` repository.

## 1. Goal

### 1.1 Fixed inputs (from the roadmap)

1. **Workflow moves to its own repository, `workflow`.** That repository
   holds only the release in development, with its own version and its own
   release stream.
2. **A Workflow release is a package.** A versioned archive is published as
   a release asset, with `SHA256SUMS` and a manifest. It is immutable once
   published.
3. **Every earlier release is published as a package**, `2.3.1` to `2.6.0`,
   as a record. Each is checked byte for byte against today's
   `distribution/` tree before that tree is removed.
4. **The Manager downloads, verifies and installs.** `bootstrap` and
   `update --release-version X` fetch the package and check it against the
   published checksums. They refuse on any mismatch. Downloaded packages
   are cached locally, so an offline machine or CI can still install a
   version it already has.
5. **`distribution/` leaves this repository.** The Manager tests its own
   code, the newest release in its three fixtures, and the upgrade path
   from the release before it. Old releases are tested once, when they are
   built, and never again.
6. **The stopgap test profile is removed**, exactly as recorded in
   `docs/ARCHITECTURE.md`'s "Stopgap test profile". Its gate-policy
   exception goes with it.

### 1.2 What "done" means

- `python3 tools/workflow_packages.py build --from <dir> --out <dir>` builds
  five packages from the base's **committed** tree, never the working tree:
  `<dir>` is a scratch directory filled by `git archive ec38979
  distribution/workflow | tar -x` (the working tree carries untracked
  `payload/scripts/__pycache__/` in four releases today). Extracting each
  one gives exactly its `distribution/workflow/<version>/` tree at the
  base: the same file set, the same bytes and the same executable bits. Two
  builds give byte-identical archives. The archive digests are recorded as
  the Manager's pins (5.3), and the evidence is recorded in
  `docs/MIGRATION.md`.
- With an empty cache and network access to the published packages,
  `workflow-manager bootstrap <empty repo>` run from an installed wheel,
  with no checkout and no `--manager-root`, installs `2.6.0`. The target
  then passes `workflow-manager verify`, and its installation record names
  the package digest.
- With the cache primed and the network off, the same command succeeds.
  With nothing cached and no network, it fails with exit `1` and a message
  naming the version, the source URL and the cache directory.
- A package whose archive digest differs from the pin, or from the
  published `SHA256SUMS`, or whose contents differ from its manifest, is
  refused before anything is written to the target (exit `1`,
  `ReleaseIntegrityError`). A cached entry that fails verification is never
  used.
- `distribution/`, `migration/`, `tools/migrate.py`, `tools/build_release.py`
  and every `STOPGAP(M2)` file and block are gone. `git grep -n
  'STOPGAP(M2)'` outside `docs/` returns nothing.
- The full `python3 tests/run_all.py` at the milestone head is green. It
  runs the Manager's host tests, the newest release (`2.6.0`) in the three
  fixtures, and the update path from `2.5.1` (a fourth frozen fixture,
  `updated`, 7.1). Its total is recorded, and it is well under today's
  25,688 tests (estimate: about 9,000 -- `CI_SUITES["2.6.0"]` is 2,002,
  times four fixtures, plus about 1,000 host tests).
- The pull request runs that same full selection. There is no second
  profile.
- The cutover (section 9) is done: the `workflow` repository exists, and
  its releases `v2.3.1` to `v2.6.0` carry assets whose digests equal the
  pins. The pull request has merged, the Manager release it produces
  (`v1.2.0`, by the recommended title) is published, and its wheel
  bootstraps a scratch repository from the network.

## 2. Non-goals

- **No new Workflow version, and no change to any release's bytes.** The
  packages are the existing trees, packed. A defect found on the way is
  written up under `docs/defects/` and stops there.
- **Not W1.** The `workflow` repository gets the five releases' history and
  their published packages only. Its authoring layout, its own tests and CI
  and its release workflow for `2.7` are W1's job. M2 makes the packaging
  tool usable from there (`workflow-manager package build`), and nothing
  more.
- **No change to installed Workflow files in this repository.**
  `.claude/commands/`, `scripts/`, the installed `docs/ai-workflow/*.md`
  operator documents, the managed `.github/workflows/workflow-conformance.yml`
  and the managed part of `CLAUDE.md` stay byte-identical (INV-3). This
  repository keeps running the installed `2.6.0`.
- **No new install semantics.** The install, update, drift, verify and
  uninstall rules in `install.py` do not change. Only where a release comes
  from changes.
- **No push, pull request, merge, repository creation or settings change by
  an agent**, except where the user authorizes a cutover step (section 9).
- **Not the Controller repository policy** (M1's `OD-4` follow-up). It stays
  a separate follow-up.
- **Not Manager ergonomics** (roadmap section 5, `doctor`, dry-run update).

## 3. Investigation findings (at the base commit)

### 3.1 How the Manager finds a release today

- `src/workflow_manager/release.py` is the only code that locates releases.
  `release_root(repo_root)` is `<repo_root>/distribution/workflow`.
  `available_versions` lists the subdirectories that hold a `manifest.json`,
  and `find_release(root, version=None)` returns the pinned version or the
  newest one.
- `Release(root)` loads `manifest.json`. `verify()` checks every
  `artifacts` and `templates` entry for presence, sha256 and executable bit,
  and refuses any extra file (except `__pycache__`). `install.py` reads
  every byte through `read_verified`. **A release directory is already
  self-verifying.** A package only has to carry that directory unchanged,
  and the Manager keeps using `Release` on the extracted tree.
- `cli.py`'s `MANAGER_ROOT` is the checkout (`Path(__file__)` three levels
  up). `--manager-root` defaults to it. From a wheel it points into
  site-packages, and `missing_distribution_message` says "Until M2, pass
  --manager-root". `bootstrap`/`update` use `_release`; `status`/`verify`
  use `_release_for_target`, which grades a target against the version its
  record names.
- The installation record (`installation.py`, `SCHEMA_VERSION = 1`) holds
  `workflow_version`, `profile`, `upstream`, `provenance`, the three maps
  and timestamps. It records neither where the release came from nor any
  archive digest.
- There is no network code anywhere in `src/`.
- The wheel carries `src/` only. `distribution/` (48 MB) is not package
  data (`test_debris_is_not_copied`). M1's `OD-3` left shipping releases to
  M2.

### 3.2 The releases

| version | files | bytes | executable | origin |
|---|---|---|---|---|
| `2.3.1` | 67 | 7,686,199 | 2 | upstream extraction (`tools/migrate.py`) |
| `2.4.0` | 68 | 9,731,441 | 2 | authored overlay on `2.3.1` |
| `2.5.0` | 70 | 10,804,265 | 2 | authored overlay on `2.4.0` |
| `2.5.1` | 70 | 10,376,792 | 2 | authored overlay on `2.5.0` |
| `2.6.0` | 70 | 10,331,763 | 2 | authored overlay on `2.5.1` |

Each directory holds `manifest.json`, `payload/`, `fixtures/` and
`templates/`. Every file under them is listed in the manifest with its
sha256, size and executable bit. No tracked file sits under `distribution/`
outside a release directory.

### 3.3 What the tests spend

- `tests/parallel/matrix.py`'s `FROZEN_MATRIX` holds 15 host classes: five
  versions times three fixtures (`conformance`, `target`, `bootstrapped`).
  The inventory discovers frozen units from
  `distribution/workflow/<v>/payload/scripts` and checks them against
  `tests/support.py`'s `CI_SUITES` counts.
- `CI_SUITES` holds 1,440 to 2,002 tests per release, run three times each.
  That is about 25,000 of the 25,688 tests the last full gate ran (`ed233bd`).
  Keeping only `2.6.0` in its three fixtures leaves about 6,000 frozen tests,
  plus about 1,000 host tests.
- Nineteen host modules exist. The ones that depend on releases are listed
  in 7.2 with what happens to each.
- The CI verify workflow clones `repflow-android` at the frozen upstream
  commit, and every job checks out full history. Both serve migration-
  provenance tests that M2 retires
  (`TestAuthoredReleaseOverlayCommitIsReachable`, `test_payload_bytes`, and
  others). `release.yml`'s release job fetches the same upstream
  (`:65-70`, required by `test_release_workflows.py:130`), though nothing
  it runs needs it any more.
- `tests/parallel/resources.json` declares `orphan_sources` per release
  version, and an `exclusive` lock on `repo:distribution` for
  `TestMigrateDoesNotDeleteASiblingAuthoredRelease`.

### 3.4 The stopgap

`docs/ARCHITECTURE.md` lines 596-670 list the marked files: the verify
workflow, `tests/parallel/{cli,inventory,planner,report}.py`,
`tests/test_stopgap_profile.py` and `tools/ci/{choose_profile.py,
nightly_alarm.py,pr_profile_paths.json}`. It also says what to delete: four
files whole, plus every block that opens with the marker. The workflow
loses the `choose_profile` step, the `NEWEST` wiring, the `profile` output,
`actions: read` and the `nightly-alarm` job. The nightly schedule may stay.
It also removes "One reduced selection is a gate, in one place"
(lines 332-348) and itself. `selection_kind` and `release.py
assert-full-plan` stay. `test_stopgap_profile.py`'s
`TestAssertFullPlanRefusesTheStopgap` tests the permanent `assert-full-plan`
and therefore moves to `tests/test_release_versioning.py`. It is not
deleted.

### 3.5 Hosting

`RodrigoFAbreu/workflow-manager` is public. `RodrigoFAbreu/workflow` does
not exist yet (`gh repo view`: not found). The Manager's own releases
publish a wheel, an sdist and `SHA256SUMS` through `gh release create`
(`release.yml`). `tools/release/package.py` already writes a
`sha256sum -c`-compatible `SHA256SUMS`.

`docs/TECHNICAL_DECISIONS.md` does not exist in this repository, so there
is no "Open decision" row to check. This plan's own open decisions are in
section 8.

## 4. Invariants (normative for every checkpoint)

- **INV-1: release bytes are immutable.** Each package extracts to exactly
  the base's `distribution/workflow/<version>/` tree: the same paths, bytes
  and executable bits, nothing more and nothing less. No checkpoint edits a
  file under `distribution/` or `migration/`. CP6 deletes them only after
  CP4's proof is recorded.
- **INV-2: fail closed on integrity.** A **pinned** version is installed
  only from bytes bound to its pin: whatever the route (package, cache hit,
  `--release-dir`, the `--manager-root` alias, the checkout fallback), the
  release's `manifest.json` must hash to the pin's `manifest_sha256`, and
  every file must match that manifest. The binding holds until the bytes
  are used: the Manager installs from a private snapshot taken and verified
  under the cache lock, never from a shared path that can change after the
  check (5.4). An **unpinned** version is by definition unpublished. It is
  installable only from a local directory, checked against its own
  manifest alone, recorded as `source.kind: "local"` and shown as
  `(local, unpublished)` (5.5). An unknown version, a digest mismatch, an
  unsafe archive member, a local directory whose pinned version does not
  match its pin, or a cache entry that fails verification all refuse with a
  named error. They are never warnings. **The one bounded consequence of
  checkpoint order is CP3:** its pin file is empty, so to the Manager every
  release is unpublished, and the checkout fallback installs the base's
  committed trees under the unpinned rule, exactly as the base does today
  (`Release.verify()` only, no weaker). CP4 writes the pins, and from then on
  a CP4 test proves every `distribution/workflow/<v>/` is pinned and matches
  its pin, so no real release is ever again installed unpinned (CP3, CP4).
- **INV-3: this repository's installed Workflow is untouched.** The files
  `.workflow-manager/installation.json` lists as managed, generated or
  merged keep their bytes. `workflow-manager verify .` passes at every
  checkpoint, by the route the checkpoint's section names: through the
  checkout fallback (5.5) at CP3, through the primed cache from CP4 on.
- **INV-4: install semantics are unchanged.** For the same release,
  `bootstrap`/`update`/`uninstall` write the same target bytes as at the
  base. Only the installation record gains the `source` field (5.5).
- **INV-5: tests never need the network, except when priming.** Every unit
  test of download, verify and cache logic uses a local server or a local
  directory, and a temporary cache of its own. Everything else reads the
  shared release cache. The runner primes it with **every pinned version**
  before planning, and priming is the only step that may fetch.

## 5. Design: packages, source, cache, CLI

### 5.1 `D-Package-Format`

A package for version `V` is three release assets:

- `workflow-V.tar.gz`: a gzip-compressed POSIX tar. Its single top-level
  directory is `workflow-V/`, holding exactly the release directory
  (`manifest.json`, `payload/`, `fixtures/`, `templates/`).
- `workflow-V.manifest.json`: a byte copy of that `manifest.json`. Readers
  can inspect a release without downloading the archive.
- `SHA256SUMS`: `sha256sum -c`-compatible lines for the two files above,
  sorted by name.

**Deterministic build** (`workflow_manager.package.build_package(release_dir,
out_dir)`):
- members are **enumerated from the manifest, never from a directory
  walk**: `manifest.json`, every `artifacts` and `templates` location, and
  every parent directory of those, up to `workflow-V/`. Anything else in the
  release directory (`__pycache__/`, editor debris) is not packed, so a
  build from a directory carrying bytecode produces the same archive as a
  build from a clean one;
- members are sorted by path and include directories;
- `mtime = 0`, `uid = gid = 0`, empty `uname`/`gname`;
- modes are `0755` for directories and for files with the manifest's
  `executable: true`, and `0644` otherwise;
- the format is `USTAR`, falling back to PAX only for a path longer than
  USTAR allows;
- the gzip header has `mtime = 0` and no file name.

Before packing, the builder runs `Release(release_dir).verify()` and refuses
any tree that fails it. Two builds on one machine are byte-identical.
Across machines, only the uncompressed tar is guaranteed byte-identical:
the gzip stream depends on the zlib version. The published archive is the
one the pins name.

**Safe extraction** (`extract_package(archive, dest)`):
- it accepts only regular files and directories, whose paths are relative,
  have no `..` component and lie under `workflow-V/`;
- it refuses links, devices, FIFOs, duplicate members and absolute paths;
- the extracted file set must equal the manifest's `artifacts` and
  `templates` locations plus `manifest.json`, and every file's sha256, size
  and executable bit must match;
- the tree is extracted into a temporary sibling and published by `rename`.

Any failure raises `ReleaseIntegrityError` and leaves nothing behind.

### 5.2 `D-Release-Source`

Where packages come from, in precedence order:

1. `--release-source <url-or-dir>` (a global option);
2. the `WORKFLOW_MANAGER_RELEASE_SOURCE` environment variable;
3. the default,
   `https://github.com/RodrigoFAbreu/workflow/releases/download/v{version}/`.

The value is either a URL template with a `{version}` field or a local
directory holding `<version>/` subdirectories with the three assets. A URL
template's scheme is `https://`, `file://`, or `http://` **only when the
host is a loopback address** (`127.0.0.1`, `::1`, `localhost`), which is
what `test_release_source.py`'s local `http.server` uses. Integrity never
rests on the transport (the pins do, 5.3); the scheme rule only keeps a
typo from silently fetching over plain HTTP. **Redirects:** at most five,
to any host (GitHub's release downloads redirect to another host), and
never to a weaker scheme: an `https` URL that redirects to `http` is
refused (`ReleaseUnavailableError`), overriding `urllib`'s default. Fetching
uses `urllib.request` with a 60-second timeout and no retries or proxies
beyond the standard library's defaults. It reads `SHA256SUMS` first and then
the archive, and caps each asset at 64 MiB. No new dependency is added.

### 5.3 `D-Pins`: the trust root

`src/workflow_manager/published_releases.json` ships in the wheel as
package data:

```json
{"schema_version": 1,
 "repository": "RodrigoFAbreu/workflow",
 "releases": {"2.6.0": {"archive": "workflow-2.6.0.tar.gz",
                        "sha256": "<archive digest>",
                        "manifest_sha256": "<manifest.json digest>"}, ...}}
```

A version is installable from a package only if it is pinned there. A
download is accepted only if the archive's sha256 equals the pin **and**
the published `SHA256SUMS` line for it. The manifest asset must equal
`manifest_sha256`. A re-published asset or a changed `SHA256SUMS` is
therefore always detected, even when the two agree with each other.

The consequence: a new Workflow release (W1's `2.7.0`) becomes installable
through a Manager pull request that adds its pin. The title is a `feat:`,
so the change releases a new Manager. Recommended in section 8, `OD-M2-2`.

### 5.4 `D-Release-Cache`

The cache directory is, in precedence order:

1. `--release-cache <dir>`;
2. `WORKFLOW_MANAGER_RELEASE_CACHE`;
3. `$XDG_CACHE_HOME/workflow-manager/releases`;
4. `~/.cache/workflow-manager/releases`.

An entry is `<cache>/<version>/` and holds:
- the three assets;
- `tree/`, the extracted release;
- `complete`, written last, which holds the archive digest.

`resolve(version)`:
1. Under an `fcntl` lock on `<cache>/<version>.lock`, it reads the entry.
2. It is a **hit** when all of these hold:
   - `complete` names the pinned digest;
   - the cached archive hashes to it;
   - `sha256(tree/manifest.json)` equals the pin's `manifest_sha256`;
   - the manifest's own version equals the requested version;
   - `Release(tree).verify()` passes.

   `Release.verify()` alone checks the tree only against the tree's own
   `manifest.json` (`release.py:184`), so a consistently altered tree, or
   one left over from another extraction, would pass it. Binding
   `tree/manifest.json` to the pin closes that: the manifest carries every
   file's digest, so the pin plus `verify()` bind every installed byte
   transitively.
3. On a hit it does no network I/O.
4. Otherwise it removes the entry and fetches, verifies and extracts the
   package into a temporary sibling, which it renames into place. A broken
   entry is logged to stderr (`discarding cache entry …`) and replaced. It
   is never used.
5. **Still under the lock, it snapshots the entry.** It copies the
   manifest-enumerated files (`manifest.json`, every `artifacts` and
   `templates` location, the modes the manifest records) from `tree/` into a
   private directory (`tempfile.mkdtemp`, mode `0700`, outside the cache),
   and then verifies **the snapshot**, not `tree/`: `sha256(manifest.json)`
   equals the pin's `manifest_sha256`, the manifest's version equals the
   requested one, and `Release(snapshot).verify()` passes. A snapshot that
   fails (a writer that ignored the lock changed `tree/` during the copy)
   discards the entry and refetches once. If that refetch cannot be made
   (offline, or any other fetch failure), the entry is already gone, so
   this is the offline-miss case and raises `ReleaseUnavailableError`, the
   same error the end of this section names. If the refetch succeeds and
   the new snapshot fails too, it raises `ReleaseIntegrityError`. Neither
   path returns the altered bytes.
6. It returns `Release(snapshot)`, which owns the snapshot. The snapshot is
   removed when the invocation ends (a context manager in the CLI, an
   `atexit` hook as a backstop).

Nothing after step 6 reads the shared cache. `Release.__init__` parses the
snapshot's `manifest.json` (`release.py:81`), which step 5 just bound to
the pin, and every byte the installer writes is read through
`read_verified` against that parsed manifest (`install.py:358`). So a swap
of `tree/`'s manifest and payload after the lock is released, however
self-consistent, changes nothing that is installed, and it cannot leave a
partly written target either: the cache is no longer on the install's read
path. The snapshot itself is private to the invocation's user and process.
A same-user process that rewrites it could equally rewrite the Manager, so
that is outside this design's threat model, and even then `read_verified`
refuses a changed file rather than installing it.

`ReleaseCache.ensure(version)` is steps 1-4 without the snapshot. Priming
uses it (7.1), because priming installs nothing.

Concurrent test chunks share one cache safely because of the lock. The
cache holds only pinned, verified content, so the cache itself is not
trusted: every hit re-verifies, and every use goes through a snapshot.

A snapshot may gain `__pycache__/` when a host test imports a payload
module from it. That is harmless because `verify()` tolerates `__pycache__`
(`release.py:208`), and the shared `tree/` never gains one, because no test
reads it in place. `support.release(v)` (7.1) memoizes one snapshot per
version per test process, so a process copies each release at most once
(about 10 MB). Frozen suites do not run in place: `support.run_suite` runs
them in the fixture repository the installer built from the snapshot
(`frozen_runs.py:237`).

**The runner's write barrier does not cover the cache.** `GUARDED_TREES`
locks trees of the checkout. The cache lives outside it, is shared by
every checkout on the machine, and must stay writable for priming and for
other Manager invocations. Its integrity does not rest on the barrier: no
test writes the shared cache (the cache-logic tests each use a temporary
one, which `test_release_source.py` asserts through
`WORKFLOW_MANAGER_RELEASE_CACHE`). A mutation before a `resolve` is caught
by the hit check or by the snapshot check (steps 2 and 5), and a mutation
after it cannot reach the snapshot. The worst case is a discarded entry, a
refetch, and, when offline, a loud `ReleaseUnavailableError`. It is never a
run on wrong bytes.

### 5.5 `D-CLI`: what the commands do after M2

- `bootstrap` and `update` resolve `--release-version` (default: the newest
  pinned version) through the cache and source, then run the unchanged
  `install.bootstrap`/`install.update` on the resulting `Release`.
- `status` and `verify` resolve the version the target's record names, the
  same way. A target recording an unpinned version fails with exit `1`: it
  is not published, and verification needs `--release-dir`. The message
  names `--release-dir` as the remedy. `status` still prints what it knows
  without the release (the recorded version, profile, `source` and install
  time) before it reports the missing release.
- **The checkout fallback (CP3 to CP6 only).** Until CP6 deletes
  `distribution/`, a version that is **not pinned** resolves, when neither
  `--release-dir` nor `--manager-root` is given, to
  `MANAGER_ROOT/distribution/workflow/<version>/` if that directory exists.
  It is used as a `--release-dir` (`source.kind: "local"`) with a stderr
  note. The default version is the newest pinned one, else the newest
  fallback one. This keeps every CLI-driving test and INV-3's `verify .`
  green at CP3, while `published_releases.json` is still empty, without
  editing those tests twice. At CP3 this is INV-2's one bounded
  consequence of checkpoint order: the five real releases are unpinned
  there, so they install under the unpinned rule, exactly as at the base.
  From CP4 all five versions are pinned, and a CP4 test
  (`test_package_round_trip.py::TestCheckoutReleasesArePinned`, deleted in
  CP6 with its module) asserts that every
  `distribution/workflow/<v>/` in the committed tree is pinned and that its
  `manifest.json` hashes to the pin's `manifest_sha256`. From then on the
  fallback is dead code for this repository's releases, and it only ever
  serves a synthetic unpinned tree (the scratch checkout's `0.0.1` until
  CP5, 7.2.1). CP6 removes it
  together with `distribution/`, and a CP6 test asserts that an unpinned
  version with no `--release-dir` refuses with `ReleaseNotPublishedError`.
- **`release.py`'s discovery API.** `Release` stays unchanged.
  `release_root`, `available_versions` and `find_release` serve only the
  checkout fallback, the `--manager-root` alias and CP4's builder until
  CP6, which deletes all three. Their remaining importers move first:
  `cli.py` in CP3, `tests/frozen_runs.py` (`:57`) in CP5. The package's
  own `__init__.py` re-exports two of them (`:10`, `:17-18`); CP6 drops
  those re-exports in the same edit (`OD-M2-3`). The alias keeps
  working after CP6 as a plain path join in `cli.py`.
- `releases` lists every pinned version, with its digest and whether it is
  cached, plus (until CP6) any checkout-fallback version, marked
  `(checkout, unpublished)`. It exits `0` even when nothing is pinned. It
  does not use the network.
- **Local directories** (`--release-dir`, the `--manager-root` alias and the
  checkout fallback) all go through one function,
  `source.local_release(dir, requested_version, pins)`, which applies INV-2
  by the directory's own manifest version `V`:
  - `V` differs from the requested `--release-version`: refused
    (`ReleaseIntegrityError`, naming both);
  - `V` is **pinned**: `sha256(dir/manifest.json)` must equal the pin's
    `manifest_sha256`, or the command refuses with `ReleaseIntegrityError`
    naming the version, the directory and both digests. A match installs
    the pinned bytes, so it is recorded as the package would be
    (`source.kind: "package"`, the pin's `repository`, `archive` and
    `sha256`), with a stderr note that a local copy was used. An altered
    local `2.6.0` can therefore never be installed as `2.6.0`;
  - `V` is **unpinned**: the directory is an unpublished release in
    development, the scoped path W1 needs. It is checked by
    `Release.verify()` only and recorded as `source.kind: "local"`;
    `status` prints `(local, unpublished)`.

  Either way the directory is snapshotted and the snapshot verified before
  use, exactly as a cache entry is (5.4 steps 5-6, with the directory's own
  `fcntl` lock not taken: a local directory has no lock protocol, and the
  snapshot check is what binds its bytes).
- `--release-dir <dir>` (new) takes an **unpackaged** release directory,
  for example a `workflow` checkout while W1 is developed, under the rule
  above.
- `--manager-root <checkout>` stays for one release as a **deprecated
  alias**, and always prints a deprecation notice to stderr. When
  `<checkout>/distribution/workflow/<version>/` exists it is used as a
  `--release-dir`, under the same rule (a pinned version must match its
  pin); otherwise the command falls through to normal pinned
  resolution, so an existing invocation against a checkout without
  `distribution/` (every checkout after CP6) keeps working. With
  `releases`, the alias adds any checkout versions it finds to the pinned
  list. It is removed in a later release. `missing_distribution_message`
  goes.
- `package build <release-dir> --out <dir>` and `package verify <archive>
  [--sha256 H]` (new) expose 5.1 so the `workflow` repository's release
  workflow can use the same code in W1.
- The installation record gains an optional `source` object:
  `{"kind": "package", "repository": …, "archive": …, "sha256": …}` or
  `{"kind": "local"}`. A record without it (every record written before
  M2) still reads. `SCHEMA_VERSION` stays `1`, because the field is
  additive and optional. Tests prove old records round-trip.

New errors are `ReleaseNotPublishedError` (unpinned),
`ReleaseUnavailableError` (fetch failed and nothing cached) and the existing
`ReleaseIntegrityError`. All of them exit `1` through the CLI's existing
`InstallError` handling, with actionable text.

### 5.6 `D-Manager-Packaging`

`tools/release/package.py`'s role changes. Today it proves that the wheel
sees the checkout's releases. After M2 it proves that the wheel carries the
pins. It lands in **CP4**, not CP3: at CP3 nothing is pinned yet, and the
wheel, which has no checkout fallback of its own, could not `verify` the
checkout's `2.6.0`.
- `--manager-root` goes from `package.py`, and so does
  `expected_release_versions`' `distribution/workflow` walk
  (`package.py:103-106`). The expected list is read from the checkout's
  `src/workflow_manager/published_releases.json`.
- The smoke check still runs, from the installed wheel, outside any
  checkout:
  - `--version`;
  - `releases`, which must list exactly the pinned versions. It never uses
    the network (5.5);
  - `verify <checkout>`, which resolves the checkout's recorded version
    (`2.6.0`) through the cache.
- `published_releases.json` must be in the wheel.
- **Cache and network.** `package.py` passes its environment through to
  the smoke check. Both callers set `WORKFLOW_MANAGER_RELEASE_CACHE` to
  `${{ runner.temp }}/workflow-manager-releases` and restore that directory
  with the same `actions/cache` step and key as the test jobs (7.3):
  - the verify workflow's `package` job (`workflow-manager-verify.yml:172`);
  - `release.yml`'s "Build and verify the package" step (`:106`).
  On a cache miss, `verify` downloads the checkout's version from the
  published source. Since K2 precedes the pull request (9), that source
  exists whenever either job runs. That download is the release job's only
  new network dependency, and it is intended: it also proves that the
  released Manager can fetch what it pins.
- Both invocations lose `--manager-root "$GITHUB_WORKSPACE"` in CP4.
  `release.yml`'s notes line (`:114`, `ls distribution/workflow`) becomes
  the pinned version list, read from the checked-out
  `published_releases.json`, in the same checkpoint.
- `release.yml`'s "Fetch the frozen upstream" step (`:65-70`) and its
  `UPSTREAM_*` env go in **CP6**, with the verify workflow's clone (7.3).
  Nothing in the release job needs them after M2, and the step requirement
  at `test_release_workflows.py:130` goes with them.

A host test covers the pin-derived expected list and the `releases`
comparison without building a wheel. Building and installing the wheel
stays the CI `package` job's proof, as it is today: no host test builds
the wheel (`test_parallel_runner.py:4947-4960` checks the job's text).

## 6. Design: building and proving the five packages

`tools/workflow_packages.py build --from <dir> --out <dir> [--pins <file>]`:
- builds one package per `<dir>/<version>/`;
- re-extracts each package into a scratch directory and compares it with
  its source tree: file set, bytes and modes;
- builds each package twice and compares the archives;
- with `--pins`, writes or checks the pin file.

CP4 runs it on the base's committed `distribution/workflow/`, extracted
with `git archive ec38979 distribution/workflow` into a scratch directory
(1.2), and writes:
- the pins;
- the evidence table in `docs/MIGRATION.md`: version, file count, archive
  digest, manifest digest, uncompressed-tar digest, and "round trip:
  identical".

It also primes the default cache from those packages. That lets every later
gate run offline (INV-5), and the same files are the assets the cutover
publishes (9, `K2`).

A CP4 test, `tests/test_published_packages.py::TestPackagesReproduceTheDistributionTree`,
proves the round trip and the pins against `distribution/` while it still
exists. It never walks the working tree, which carries untracked
`__pycache__/`: it extracts the committed tree with the same `git archive
ec38979 distribution/workflow` the tool uses (1.2), and compares the
manifest-enumerated file set, bytes and modes. It does not need the
`repo:distribution` lock: that lock's only holder is an exclusive chunk,
which the runner runs alone in pre-phase A0 (`isolation.py:771-777`), so
nothing runs concurrently with it. CP6 deletes `distribution/`, and the test goes with it. Its evidence
stays in `docs/MIGRATION.md` and in CP4's commit, per "old releases are
tested once, when they are built". What stays permanent is the check that
each pinned package, obtained through the cache, re-verifies against its
pin and its own manifest (`TestPinnedPackagesVerify`). It covers every
pinned version, which priming (7.1) resolves, so it never fetches.

## 7. Design: the test suite after M2

### 7.1 `D-Tested-Releases`

`tests/support.py` defines two releases from the pins:
- `NEWEST_RELEASE`, the highest pinned version;
- `UPGRADE_FROM`, the one below it, or `None` when exactly one version
  is pinned.

At M2 these are `2.6.0` and `2.5.1`. Both are computed at import from the
pin list, and `UPGRADE_FROM` never indexes past it: with one pin (the
scratch checkout and `TestFrozenInventoryCountRefusal`'s layout, 7.2.1,
each pin only `0.0.1`) it is `None`, `FROZEN_MATRIX` omits the `updated`
class, and nothing else changes, so a one-pin run imports, discovers and
runs cleanly. The `updated` builder resolves `UPGRADE_FROM` lazily, when it
builds, and raises a named error if it is `None`. `test_update_path.py`
asserts that the real repository's pins give a non-`None` `UPGRADE_FROM`,
so the `updated` class can never drop out of the real matrix silently. Releases are obtained with
`support.release(version)`, which calls the cache resolver and memoizes the
returned snapshot per version per process (5.4). `CI_SUITES` and
`tests/portability_exceptions.json` keep **every pinned version's** entry,
unchanged: a published release is immutable, so its pinned counts and its
exceptions are frozen records, and the document-evidence tests that quote
them (7.2, `test_internal_references.py`; `test_conformance_suite.py`'s
`TestPortabilityExceptions250RequiredEmptyEntry`) keep their inputs. Only
`NEWEST_RELEASE`'s entry is run: the inventory reads `CI_SUITES` only for
the versions `FROZEN_MATRIX` names (`inventory.py:228-251`). A host test
asserts that the pinned versions, `CI_SUITES`'s keys and
`tests/portability_exceptions.json`'s `by_version` keys are the same set,
so adding W1's pin forces its counts and its (possibly empty) exceptions
entry, and no surviving test can subscript a version the data lacks.
`FROZEN_MATRIX` becomes four host classes, one per fixture, parameterized
by `NEWEST_RELEASE`. They replace the fifteen per-version classes and carry
no version in their names, so W1 renames nothing:
`test_conformance_suite.py::TestConformanceFixture` and
`::TestBootstrappedTarget`,
`test_bootstrap_e2e.py::TestBootstrappedRepositorySatisfiesTheFrozenSuite`,
and `test_update_path.py::TestUpdatedRepositorySatisfiesTheFrozenSuite`. The fourth fixture is new: **`updated`**, built by
bootstrapping `UPGRADE_FROM` and then running the real `update` to
`NEWEST_RELEASE` (a `frozen_runs.FIXTURE_BUILDERS` entry). Running the
newest frozen suites there as frozen units, rather than inside one host
test, keeps them chunked and parallel, and keeps their unit ids in the
frozen form that `orphan_sources` already uses.

The `updated` fixture in detail:
- **Builder.** A `FIXTURE_BUILDERS` entry still takes one release,
  `builder(release, dest)` (`frozen_runs.py:228`, `:561`), and that
  release is `NEWEST_RELEASE`. The builder resolves `UPGRADE_FROM` itself
  through `support.release`, bootstraps it, commits, runs `install.update`
  to the release it was given, and commits again, as
  `build_bootstrapped_repo` commits after `bootstrap`. The residue check
  therefore starts from a clean baseline.
- **Expected failure set.** It is the same set as `bootstrapped`'s, read
  from `tests/portability_exceptions.json` by version, and empty for
  `2.6.0`. No per-fixture key is added. If a newest suite fails only in the
  updated repository, that is an upstream defect, not an exception: it is
  written up under `docs/defects/`, no release byte changes, and the
  checkpoint stops for the user.
- **Post-run checks.** `_post_run_state` (`frozen_runs.py:199-206`)
  measures residue and `drift` for `updated` as well as `bootstrapped`.
  The `updated` host class asserts a clean `git status` and no drift after
  the suites, as `TestBootstrappedRepositorySatisfiesTheFrozenSuite*` does. The inventory discovers
frozen units from the resolved release's `payload/scripts` (its snapshot,
5.4). Unit ids keep their
`frozen:<v>/<fixture>/<suite>` form. `frozen_runs.release_digest` reads
`manifest.json` from the resolved release's root (`support.release(v)`)
instead of `distribution/workflow/<v>/`. The value is the same bytes'
digest, so chunk records and their merge check (`frozen_runs.py:217`,
`:458-479`) are unchanged.

**Priming.** Before the runner discovers the inventory, it resolves **every
pinned version** through `ReleaseCache.ensure` (5.4; `--plan-only`, local and
`--run-shard` modes alike): the
matrix needs the newest, the `updated` fixture the one below it, and
`TestPinnedPackagesVerify` and the `2.6.0` hardening test's scenario 4
(`2.3.1`, `2.4.0`) the rest. A failure exits `2` with the cache directory
and the source URL. The runner then exports the resolved cache directory
as `WORKFLOW_MANAGER_RELEASE_CACHE` to every unit it starts, so all units
read the directory priming filled.

**Subprocess environments.** Tests that build a subprocess environment from
scratch (`test_bootstrap_e2e.py:273`, `test_amendment_update_path.py:514`,
`test_bootstrap.py:1052`) take it from a new `support.cli_env(**extra)`,
which always sets `WORKFLOW_MANAGER_RELEASE_CACHE` to the parent's
resolved cache directory (so a test that points `HOME` at an empty
directory on purpose, like `test_bootstrap.py:1049`, still reads the primed
cache) and carries `WORKFLOW_MANAGER_RELEASE_SOURCE` through when it is
set. Those two are defaults: `cli_env(**extra)`'s keyword arguments are
applied last and override them. The runner exports the real cache to every
unit, including `test_parallel_runner.py`, so the scratch checkout (7.2.1)
passes its private cache and source explicitly this way; that override is
the only thing keeping a scratch run off the real cache, and CP5's "the
real cache is untouched" test proves it. A
host test asserts that no test module passes a literal `env={...}` to a
`workflow_manager` subprocess, so a new one cannot drop the cache again.

**CI.** Every test job sets `WORKFLOW_MANAGER_RELEASE_CACHE:
${{ runner.temp }}/workflow-manager-releases` at job level and restores
exactly that directory with `actions/cache`, keyed by the hash of
`published_releases.json`. The saved entry therefore holds all five
versions, and a normal CI run downloads nothing.

### 7.2 Module by module

| module | after M2 |
|---|---|
| `test_conformance_suite.py` | CP5, class by class (every class and helper below `:314`). The ten per-version matrix classes become `TestConformanceFixture` and `TestBootstrappedTarget` (7.1), reading the release through `support.release(NEWEST_RELEASE)`; the `find_release` import (`:69`) goes, and the portability check reads `tests/portability_exceptions.json`. **Stay, permanent:** `TestPortabilityExceptions250RequiredEmptyEntry` (`:838-878`), whose `2.3.1`/`2.4.0`/`2.5.0` entries CP5 keeps (7.1); and `TestAuthoredReleaseCiTemplateSuiteNames` (`:615-633`), rewritten to read each template through `support.release(v)` for every pinned version except `2.3.1` (the set it covers today, so W1's pin joins it with no edit), against `CI_SUITES[v]`, which CP5 keeps. **Move, in CP5, to a new module `tests/test_authored_release_tools.py`, on CP6's deletion list** (they read `migration/overlays/`, `tools/build_release.py` or `distribution/` directly, which live until CP6, and the module is outside CP5's layout assertion by being on that list): `_overlay_payload_roots` (`:314`), `_authored_release_versions` (`:331`), `TestAuthoredReleaseOverlayDelta` (`:362`), `TestBuildReleaseCollisionGuards` (`:492`), `TestAuthoredReleaseIsSelfConsistent` (`:595`), `TestAuthoredReleaseOverlayCommitIsReachable` (`:635`), `TestOverlayStateWriterClosure` (`:666`), `_load_release_module` (`:738`), `TestReleaseMetadataVersionClaimCorpus250` (`:758`) and `TestNoPayloadTestReadsAbovePayloadRoot` (`:817`). None is deleted before CP6, so the tools stay tested as long as they exist; none survives CP6, whose `distribution/`/`migration/`/`build_release.py` removal would break every one |
| `test_bootstrap_e2e.py` | matrix class parameterized (`TestBootstrappedRepositorySatisfiesTheFrozenSuite`, 7.1); "default is newest" asserts the newest **pinned** version, and its comment (`:281-289`, which names `distribution/workflow/2.4.0/` and `find_release`) is rewritten with it in CP5, as is `tests/parallel/inventory.py`'s module docstring (`:16-21`, `distribution/workflow/<version>/payload/scripts/`), which becomes "the cached release tree's `payload/scripts/`". CP5's layout assertion scans comments, so neither needs an exemption; `TestUpdatePreservesLiveWorkItemState` (`:183-191`), which bootstraps `2.3.1` through `find_release` and updates it to the same release, moves to `support.release(NEWEST_RELEASE)`. It tests a Manager behaviour (an update keeps live state), not an old release, so it follows the newest pin |
| `test_bootstrap.py` | pins `NEWEST_RELEASE` instead of `2.3.1`, in CP5: `BootstrapCase` (`:63`) reads `support.release(NEWEST_RELEASE)`, the `"2.3.1"` bootstrapped-version literals (`:79`, `:836`) become `NEWEST_RELEASE`, and the synthetic next release (`:532`, `:548-549`, `:752`, `:821`, `:840`, `:848`, `:932`, today hardcoded `"2.3.2"`) takes a version derived from `NEWEST_RELEASE` (its patch plus one, a support helper), so the "next" release is never lower than the installed one (the `Installation` dict literals at `:425-446` are record round-trips, not releases, and stay); CP3 rebuilds only `TestReleaseResolution`, whose own `2.3.1`/`2.3.2` layout (`:965-999`) goes with it; in CP6 `:1032`'s comment, which names `test_payload_bytes.py`, is reworded (CP6's retired-module assertion); `TestReleaseResolution` is rebuilt in CP3 on synthetic packages served from a local directory (pins, cache hits, discard and refetch, `--release-dir`, the checkout fallback), and its discovery-API tests (`available_versions`/`find_release`, `:980-985`, and the import at `:48-49`) stay until CP6 deletes that API and them with it. The `--manager-root` alias gets its own class, `TestManagerRootAlias` (CP3, permanent while the alias exists): given a temporary checkout holding `distribution/workflow/<v>/` for a synthetic **unpinned** `<v>`, the alias uses it as a `--release-dir` (`source.kind: "local"`) and prints the deprecation notice (5.5's positive branch); given the same layout for a **pinned** version (a pin file the test writes for a synthetic package) whose `manifest.json` has been altered consistently with an altered payload file, so `Release.verify()` passes, the alias refuses with `ReleaseIntegrityError` and writes nothing to the target; it builds that layout itself and does not depend on the repository's own `distribution/`, so it runs unchanged after CP6. The negative branch after CP6 is `test_manager_version.py:289-293`'s rewrite |
| `test_update_path.py` (new) | holds the `updated` fixture's matrix class (7.1), whose frozen units run the newest suites in the updated repository; plus host tests of `UPGRADE_FROM` bootstrapped, then `update` to `NEWEST_RELEASE`: the record (`workflow_version`, `source`), the managed bytes against the newest manifest, and `verify`. Beyond `test_workflow_2_6_0_hardening_disposable_repo.py`'s scenario 9, which drives `2.6.0`-specific in-flight items through a fixed `2.5.1`→`2.6.0` update, it is release-agnostic: it follows the pins, so W1's `2.7.0` pin retargets it to `2.6.0`→`2.7.0` with no edit |
| `test_release_source.py` (new) | 5.1-5.4 on synthetic packages, over a local `http.server` on `127.0.0.1` and over `file://`, each test with its own temporary cache: every refusal in INV-2, including a `tree/` whose `manifest.json` differs from the pin's `manifest_sha256` while `Release.verify()` passes, and a manifest whose version differs from the requested one; **the resolve/install boundary**: `resolve()` returns, then the test rewrites the cache entry's `tree/manifest.json` and one payload file into a self-consistent altered pair (and `complete`), then runs `install.bootstrap` on the returned `Release`, and asserts that every target byte equals the pinned package's and that the altered bytes appear nowhere in the target; **a writer that ignores the lock**, through a test seam called between the snapshot copy and the snapshot check, alters `tree/` and the copied file mid-snapshot, and `resolve()` discards, refetches and returns a snapshot that matches the pin, never the altered bytes; offline, the discarded entry cannot be refetched and `resolve()` raises `ReleaseUnavailableError` (5.4 step 5); and when the seam also alters the refetched entry's snapshot, `resolve()` raises `ReleaseIntegrityError` after exactly one refetch; the snapshot's lifetime (removed when the invocation ends); **pinned local directories**: for both `--release-dir` and the `--manager-root` alias, a directory holding a pinned version whose manifest and payload have been altered consistently (so `Release.verify()` passes) is refused with `ReleaseIntegrityError` before any target write, an unaltered one installs and is recorded as `source.kind: "package"`, and an unpinned one installs as `source.kind: "local"`; a `--release-dir` whose manifest version differs from `--release-version` is refused; a non-loopback `http://` template and an `https`→`http` redirect refused; the size cap, safe extraction, lock contention, offline hit and offline miss |
| `test_published_packages.py` (new) | `TestPinnedPackagesVerify` (permanent), alone |
| `test_package_round_trip.py` (new, CP4; deleted in CP6) | the CP4 round-trip class, which extracts `git archive ec38979 distribution/workflow` (6), and `TestCheckoutReleasesArePinned` on the same extraction (5.5, CP4). Its own module, on CP6's deletion list, so CP5's layout assertion needs no exemption for it and CP6's deletion list stays file-granular |
| `test_workflow_2_6_0_hardening_disposable_repo.py` | kept: it exercises the newest release. Every release it reads, including scenario 4's `2.3.1`/`2.4.0`, comes through `support.release` (its `find_release` import, `:66`, the literal `distribution/workflow/<v>/payload/scripts` path, `:624`, and `PAYLOAD_260`, `:1349`, used at `:1389`/`:1399`, which becomes `support.release("2.6.0").root / "payload"`, go), which priming has already resolved. `test_the_repository_level_guards_are_still_registered` (`:1416-1422`) reads `migration/portability_exceptions.json` and names `TestBootstrappedTarget260`; in CP5 it asserts `expected_portability_exceptions("2.6.0") == {}` (the moved file) and names `TestBootstrappedTarget`. Its second half (`:1423-1435`) is **v2.3.1-002's repository-level guard**: it asserts that `test_amendment_update_path.py` has host units in the full selection and in `FAST_ALIAS_SELECTION`. CP6 deletes both that module (`OD-M2-5`) and the alias (CP6), so in CP6 the guard is **retargeted, not retired**: it asserts that `test_update_path.py`, the update-path suite that follows the pins (this table), has host units and that all of them are in the full selection; the alias half goes with the alias. The payload-level v2.3.1-002 regression tests (`CLOSED_DEFECT_TESTS`, `:1352-1360`) are unchanged. The comment at `:946`, which names `tests/test_amendment_update_path.py` as the source of the `2.5.1` helpers' scripted sequence, is reworded in CP6 to cite the sequence without the retired module's name |
| `test_orphan_processes.py`, `test_squash_merge_compat.py`, `test_disposable_repo_fixtures.py` | release paths through `support.release`; `test_squash_merge_compat.py:233`'s `cli.main(["--manager-root", REPO_ROOT, "verify", …])` drops the alias in CP5 and verifies through the pins |
| `test_internal_references.py` | CP5. Its `docs/MIGRATION.md` evidence classes check a document, and `MIGRATION.md`'s historical records are kept verbatim (1.2, 6), so they stay. `TestMigrationEvidenceManifestFieldsMatchShippedManifest` (`:336-392`) and `TestAuthoredReleaseMigrationRecordMatchesShippedEvidence` (`:395-530`) read each manifest through `support.release(v)` (`:369`, `:430`), which gives the same bytes (`2.4.0` and `2.6.0` are pinned and primed); their regexes keep matching the record's literal text `` `distribution/workflow/<v>/manifest.json`'s `provenance` `` (`:352`, `:446`), which is document text, not a release lookup. The `CI_SUITES`- and portability-derived checks keep their inputs, because CP5 keeps every pinned version's entry (7.1), and stay unchanged: `TestMigrationEvidenceCountsMatchCiSuites` (`:278-333`), the fixture-row delta checks (`:492-508`, and `:527`'s `expected_portability_exceptions(version)` per authored release), and `TestReadmeStatusTableMatchesCiSuites` (`:533-691`, `CI_SUITES` and portability entries for `2.3.1` to `2.6.0`). CP7's `README.md` rewrite keeps the Status table rows that class pins. `ReferenceCase` (`:96-111`) and its four subclasses stay on **`2.3.1`**, through `support.release("2.3.1")` instead of `find_release` (`:98`; the import at `:21` goes): `TestCommandInventoryAndGoldenHashes` (`:220-275`) asserts `2.3.1`'s frozen fifteen-command corpus and its golden hashes, which describe that release and no other. `2.3.1` stays pinned, so the case is permanent |
| `test_manager_version.py` | `MissingDistributionHintTest` becomes the unpublished-version and unavailable-release messages (CP3). `test_the_live_release_set` (`:395-403`) compares `releases` with the pin-derived list and drops `--manager-root` (CP4, with 5.6). `test_the_checkout_itself_still_lists_its_releases` (`:289-293`) becomes, in CP6, a test that the alias on a checkout without `distribution/` prints its deprecation notice and lists the pins (5.5) |
| `test_parallel_runner.py` | the `package` job's command string (`:4958-4959`) drops `--manager-root` and the job gains the cache env and restore step (CP4, with 5.6); its `release_digest` uses (`:895`, `:1255`, `:1429`) follow `frozen_runs.release_digest` to the resolved release; the scratch-checkout apparatus moves to packages in CP5 and its last `distribution/`/`migration/` couplings go in CP6 (7.2.1); its write-barrier tests follow `GUARDED_TREES` down to `("src/", "tools/")` in CP6; its tests of the newest-release selection go with the stopgap. Its references to the per-version matrix classes follow their CP5 renames (7.1): `:874-877` and `:1044`/`:1360` (`TestConformanceFixture260` → `TestConformanceFixture`), `:1372` (`TestBootstrappedRepositorySatisfiesTheFrozenSuite260` → the unversioned name). In CP6, with the real declaration's only exclusive unit gone: `EXCLUSIVE_UNIT` (`:68`) is deleted; `TestResourcesContract.test_the_committed_declaration_loads_against_the_real_inventory` (`:289-296`) becomes "the committed declaration loads against the real inventory, declares no resource and no exclusive unit, every `orphan_sources` id is a discovered unit, and every `frozen:` id among them is a unit of `NEWEST_RELEASE`" (the five `host:` ids are discovered host units, 7.2's `resources.json` paragraph); `test_the_full_selection_plans_locally_and_in_ci` (`:2266-2270`) loses its A0 check; and `EXCLUSIVE_UNIT`'s third consumer, `test_todays_tests_are_clean_apart_from_the_declared_unit` (`:3519-3525`), which lints `test_amendment_update_path.py` and expects exactly `EXCLUSIVE_UNIT`, becomes `test_todays_tests_are_lint_clean`: the real tests produce no lint finding against the committed declaration, which declares no exclusive unit (the raw lint of the deleted file goes). From CP6 the A0 exclusivity proof is the scratch lock's alone (7.2.1, on `repo:tools`). Also in CP6, the real-inventory tests that name a retired module are retargeted to `test_bootstrap.py`, which M2 keeps: `test_real_module_spec_selects_exactly_that_module` (`:231-235`) selects `["test_bootstrap.py"]`, and `test_direct_module_runs_still_work` (`:3888-3893`) runs `python3 test_bootstrap.py TestInstallationRecord` and `python3 -m unittest test_bootstrap.TestInstallationRecord` (a class that needs no release, so the direct run stays cheap). With the `--fast` alias removed (CP6), `TestFastAliasAndDirectEntryPoints` loses its two alias tests (`:3869-3887`), becomes `TestDirectEntryPoints` and gains CP6's two runner tests (an ordinary run exits `0`; `--fast` is an unrecognized argument), and the module docstring's pointer to `tests/test_stopgap_profile.py` (`:29`) is dropped with that module |
| `tests/frozen_runs.py`, `tests/parallel/` (infrastructure) | `frozen_runs.py`: `release_digest` and the `find_release` import (`:57`) move to `support.release` (CP5), `FIXTURE_BUILDERS` gains `updated`. `parallel/resources.py`: `GUARDED_TREES` drops `distribution/` and `migration/` in CP6, which changes `isolation.py`'s barrier and `report.py`'s barrier message with it (`tree.py`'s `SNAPSHOT_IGNORED_TREES` follows) |
| `test_stopgap_profile.py` | deleted; `TestAssertFullPlanRefusesTheStopgap` moves to `test_release_versioning.py` |
| `test_payload_bytes.py`, `test_templates.py`, `test_migration_inventory.py`, `test_no_live_state_imported.py` | deleted with `migration/` and `tools/migrate.py`: they are `2.3.1`'s extraction evidence (`OD-M2-4`) |
| `test_amendment_update_path.py` (`2.3.1`→`2.4.0`), `test_implementation_review_two_stage_disposable_repo.py` (`2.4.0`→`2.5.0`) | deleted: they were those releases' acceptance evidence, and the releases are not tested again (`OD-M2-5`) |
| `test_release_versioning.py`, `test_release_workflows.py` | kept; the workflow-structure tests drop the stopgap jobs and gain the cache step. `test_release_workflows.py`'s release-job order check gains the cache step before the package step (CP4) and loses the "fetch the upstream" requirement (`:130`, CP6) |

`tests/parallel/resources.json`'s `orphan_sources` changes only in its
`frozen:` entries: CP5 keeps the `TestStateLock` entries for
`NEWEST_RELEASE` only and adds the same entry for the `updated` fixture
(`frozen:2.6.0/updated/workflow_state_completion_obligations_test.py::TestStateLock`,
same reason). Both land in CP5. Its five `host:` entries
(`test_orphan_processes.py::TestKilledChunks`,
`test_parallel_runner.py::TestExecutorLevelFaults`,
`::TestLockAndRecoveryThroughTheCli`, `::TestRunChunk` and
`::TestRunLockAndRecovery`) declare units in modules M2 keeps, which
orphan processes on purpose; they stay **unchanged through CP5 and CP6**,
and removing one would fail its unit with `OrphanProcessError` (exit `2`). The `repo:distribution` exclusive entry and
its resource definition stay until **CP6**, because their holder,
`test_amendment_update_path.py::TestMigrateDoesNotDeleteASiblingAuthoredRelease`,
lives until CP6. Its `tools/migrate.py` run without `--check`
`shutil.rmtree()`s the real `distribution/workflow/2.3.1/`, while
`distribution/` still has readers through CP5 (CP4's round-trip class,
`test_payload_bytes.py`, `test_templates.py`, `test_migration_inventory.py`
and `test_authored_release_tools.py`). CP6 deletes the holder, the
exclusive entry and the `repo:distribution` resource in one edit, together
with dropping `distribution/` from `GUARDED_TREES`: `resources.py:133`
refuses a resource path outside `GUARDED_TREES`.
After CP6 the committed `tests/parallel/resources.json` is `schema_version`
unchanged, `resources: {}`, `exclusive: {}`, and `orphan_sources` holding
exactly the five `host:` entries above, plus the `TestStateLock` entries
for `NEWEST_RELEASE`'s four fixtures (`conformance`, `bootstrapped`,
`target`, `updated`). `resources.parse`
accepts empty objects (`resources.py:113-114`), so the file needs no
schema change.
`migration/portability_exceptions.json`'s `by_version` moves to
`tests/portability_exceptions.json` in CP5, every entry unchanged and keyed
by version (7.1), so W1 adds its own beside them.

#### 7.2.1 The scratch checkout and `support.py`'s `migration/` reads

`scratch_checkout` (`test_parallel_runner.py:2553`) is the runner's only
end-to-end proof, and it copies `tests/support.py`, `tests/frozen_runs.py`
and `src/workflow_manager/` verbatim (`:2584-2587`). After CP5 those copies
resolve releases through the pins and the cache, so a scratch left on the
`distribution/workflow/0.0.1/` layout (`_write_scratch_release`,
`:2520-2541`) would prime and test the five **real** pinned releases, and
CP5's own gate would go red. The apparatus therefore moves to packages in
**CP5**, in the same edit as `support.py`, `frozen_runs.py` and the
inventory it copies:

- **The scratch release is a package.** `_write_scratch_release` builds the
  synthetic `0.0.1` tree in a temporary directory outside the scratch,
  packages it with CP1's `build_package`, and serves the three assets from a
  scratch-local directory. The scratch's copy of
  `src/workflow_manager/published_releases.json` is overwritten with one pin,
  `0.0.1`, for that package. Every `run_cli(scratch, …)` sets
  `WORKFLOW_MANAGER_RELEASE_SOURCE` to that directory's `file://` URL and
  `WORKFLOW_MANAGER_RELEASE_CACHE` to a scratch-private cache (via
  `support.cli_env`), so a scratch run primes and tests only `0.0.1`, and
  never reads or writes the real cache. `SCRATCH_PAYLOAD` (`:2347`) goes.
- **`damage_payload`** (`builder_raises`, `:3725`) can no longer damage the
  payload after the manifest: priming's hit check would refuse it (exit
  `2`), not the fixture builder (exit `1`). The case keeps its assertion,
  "a fixture-builder failure is `1`, not `2`", with a trigger that survives
  verification: a scratch package whose manifest verifies but lists no
  `.gitignore` fragment template, so `build_conformance_repo`
  (`fixture.py:138-141`) raises inside the builder. The parameter is renamed
  for what it now does.
- **`find_release`** (`:65`, `:4119`): `TestTestTreeHygiene`'s "builds a
  release" test resolves `0.0.1` through the scratch's own pins and cache
  (`support.release` in the scratch's environment) and asserts the tree came
  from the scratch cache, not the real one. The import goes.
- **`TestFrozenInventoryCountRefusal`'s layout** (`:773`): inventory
  discovery moves to the cached tree in CP5, so the layout becomes a
  one-pin package of the tiny suite served and cached in the test's
  temporary directory, and the discovery is pointed at that cache.
- **The scratch exclusive-lock tests** (`:2349-2398`) exercise a permanent
  runner feature, exclusive chunks alone in A0 (`isolation.py:771-777`).
  Their resource moves from `repo:distribution` over `distribution/` to
  `repo:tools` over `tools/`, a guarded tree that survives CP6
  (`resources.py:133` refuses anything outside `GUARDED_TREES`). The
  exclusive writer `rmtree()`s and rebuilds the scratch's `tools/` content,
  which the scratch already creates (`tools/.keep`, now a small tree), and
  the shared reader reads it.
- **`:344`'s sub-path case** is retargeted from `distribution/workflow/` to
  `src/workflow_manager/`, so it still tests the sub-path rule after CP6
  rather than failing for the "not a guarded tree" reason.
- **The scratch's `migration/` files** (`:2606-2610`):
  `portability_exceptions.json` moves to the scratch's
  `tests/portability_exceptions.json` in CP5, with `support.py`'s read.
  `migration/classification.json` stays until **CP6**, because `support.py`
  still reads it at import until then (below).

`support.py` reads `migration/` at import (`:17-20`), so every module that
imports it would fail at CP6 if that were missed:
- `PORTABILITY_EXCEPTIONS` reads `tests/portability_exceptions.json` in
  **CP5** (7.1).
- `CLASSIFICATION`, `FROZEN_COMMIT`, `FROZEN_TAG`, `UPSTREAM`,
  `upstream_available`, `frozen_paths` and `frozen_bytes` (`:18-60`) are
  deleted in **CP6**. Their only consumers are the modules CP6 deletes
  (`test_payload_bytes.py`, `test_templates.py`,
  `test_migration_inventory.py`, `test_no_live_state_imported.py`,
  `test_amendment_update_path.py`) and two CI-structure assertions,
  `test_parallel_runner.py:4718` (`UPSTREAM_TAG` against
  `CLASSIFICATION`) and `:4845` (`FROZEN_COMMIT` against the workflow's
  pinned upstream commit), which go in CP6 with the repflow clone and its
  env (7.3). `scratch_checkout` stops writing `migration/` in the same edit.

**The write-barrier lint** (`isolation.py:1029-1032`): `TOOL_SCRIPTS =
("migrate.py", "build_release.py")` and `TOOL_ENTRY_POINTS` name the tools
CP6 deletes. CP6 deletes both constants and the lint branches that read
them, and rewrites the lint fixtures (`test_parallel_runner.py:3449-3482`):
lines 1-2 and 5-6 of `TestWriters` and the two tool lines of `TestReaders`
go, and the `DIST`-rooted examples (`DIST` itself, `:3449`, and
`:3460`, `:3464`, `:3481-3482`) are rebased on `REPO_ROOT / "tools"`, so every remaining writer
shape is still proved flagged and every reader shape still proved clean.

### 7.3 CI after M2

`workflow-manager-verify.yml`:
- `plan` loses the stopgap step, the `profile` output and `actions: read`;
- the `nightly-alarm` job goes;
- the repflow clone and its env go, and so do `release.yml`'s upstream
  fetch step and its `UPSTREAM_*` env (5.6);
- `fetch-depth: 0` goes wherever no remaining test needs history;
- every job that runs tests sets `WORKFLOW_MANAGER_RELEASE_CACHE` to
  `${{ runner.temp }}/workflow-manager-releases` and restores that
  directory (`actions/cache`, keyed on
  `hashFiles('src/workflow_manager/published_releases.json')`) before
  priming (7.1);
- the nightly schedule stays, as a full run.

These land in CP6. The `package` job's and `release.yml`'s cache env,
cache restore and `package.py` invocation land earlier, in CP4 (5.6).

Pull requests, pushes and the nightly run the same full selection.
`release.yml` keeps `assert-full-plan`.

## 8. Open decisions (recommendations; the user decides)

- **`OD-M2-1`: hosting.** Recommendation:
  - a new **public** repository, `RodrigoFAbreu/workflow`;
  - GitHub releases `v2.3.1` to `v2.6.0`, each carrying the three assets,
    with `v2.6.0` marked latest;
  - the repository's "release immutability" setting turned on, so a
    published asset cannot be replaced.

  Creating the repository and changing its settings is the user's action
  (or an explicit authorization for `gh repo create`). This checkout's
  agent never does it unasked. The alternative is publishing the packages
  as assets of this repository's releases. It was rejected: that mixes two
  products' release streams, against "one product per repository".
- **`OD-M2-2`: the trust root.** Recommendation: pins shipped in the
  Manager (5.3). The alternative, trusting a downloaded `SHA256SUMS` alone,
  only detects corruption in transit: anyone who can replace the assets can
  replace the sums too. The cost is that each new Workflow release needs a
  small Manager `feat:` pull request. That fits the kanban loop, where the
  Controller can run it.
- **`OD-M2-3`: the title and the bump.** Recommendation: `feat: Workflow
  releases are downloaded, verified packages`, giving Manager `1.2.0`.
  `--manager-root` stays as a deprecated alias (5.5), so no existing
  invocation breaks. Two removals do not make it `feat!:`: the
  `available_versions`/`find_release` re-exports from `import
  workflow_manager` (CP6) are not a documented interface (the Manager's
  documented interface is its CLI; `README.md` and `docs/RELEASING.md`
  never name them, and `docs/ARCHITECTURE.md:717` describes them as
  internals of the release layout M2 removes), and `--fast` belongs to
  `tests/run_all.py`, which the package does not ship. The alternative, `feat!:` with `--manager-root`
  removed now, gives `2.0.0`.
- **`OD-M2-4`: retiring the migration tooling.** Recommendation: delete
  `migration/`, `tools/migrate.py`, `tools/build_release.py` and their
  provenance tests. Git history keeps them at the base `ec38979`, and
  `docs/MIGRATION.md` cites that commit. Authored releases are built in the
  `workflow` repository from now on, with no overlay mechanism: its tree is
  the release. The alternative is moving the tools to the `workflow`
  repository. It was rejected: that repository holds only the release in
  development, and these tools rebuild history.
- **`OD-M2-5`: retiring old-release acceptance tests.** Recommendation:
  delete the `2.3.1`→`2.4.0` and `2.4.0`→`2.5.0` disposable-repository
  tests, per "old releases are tested once". Keep the `2.6.0` hardening
  test, and add the `2.5.1`→`2.6.0` update path. **v2.3.1-002's
  repository-level guard** (the hardening test's `:1423-1435`: "the
  update-path suite is always run") is retargeted, not retired, from
  `test_amendment_update_path.py` to `test_update_path.py`, the update-path
  suite that follows the pins. The payload-level v2.3.1-002 regression
  tests are untouched. CP7's `docs/MIGRATION.md` M2 record states the
  retarget.
- **`OD-M2-6`: the `workflow` repository's seed history.** Recommendation:
  five commits on `main`, one per release, each with a tree equal to that
  release's directory plus a short `README.md`, tagged `v<version>`. Each
  tag then points at its own source, and `main` ends at `2.6.0`, the base
  W1 develops from. W1 may reorganize the layout. The alternative, one
  commit with all tags on it, loses that.
- **`OD-M2-7`: archive format.** Recommendation: `tar.gz`, which keeps
  executable bits and extracts with standard tools. The alternative, `zip`,
  handles POSIX modes poorly.

## 9. Cutover

These steps run after the implementation is technically approved and the
functional review is done, before acceptance. They follow M1's pattern:
each step's evidence is recorded in `docs/ACTIVE_MILESTONE.md`.

- **K1.** The user creates `RodrigoFAbreu/workflow` (public) and turns on
  release immutability, or explicitly authorizes the agent to do so with
  `gh`.
- **K2.** Seed and publish, as the user authorizes:
  - push the five seed commits and tags (`OD-M2-6`);
  - create releases `v2.3.1` to `v2.6.0`, attaching CP4's assets from the
    cache.
- **K3.** Verify from the network:
  - with an empty temporary cache, `workflow-manager releases`, then
    `bootstrap`/`verify` of a scratch repository for each pinned version;
  - `sha256sum -c SHA256SUMS` on each downloaded release;
  - every downloaded digest equals its pin.
- **K4.** Push the branch and open the pull request under the chosen title
  (the user's action, or authorized). CI's full selection must be green.
  Its first run downloads the packages from K2, which proves that path.
- **K5.** Squash-merge (M1b precedent: reported before and after). Then
  check that `main`'s full run is green and that the Manager release
  (`v1.2.0`) is published. `pipx install` its wheel into a scratch
  environment and bootstrap a scratch repository with no checkout.

K1-K5 need the network and a repository that does not exist yet, so no
implementation gate depends on them (INV-5). A problem found in K2-K5 goes
back through `/apply-functional-review`.

## 10. Checkpoint registry

<!-- registry-table:begin -->
| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Package format: deterministic build, safe verified extraction, shared SHA256SUMS writer | - | 2 | 1 |
| CP2 | Release source, pins and verified cache: fetch, pin and SHA256SUMS checks, locking, offline behaviour, named errors | CP1 | 3 | 1 |
| CP3 | CLI and install record: package-backed bootstrap/update/status/verify/releases, --release-source/--release-cache/--release-dir, package subcommand, deprecated --manager-root with pinned fall-through, checkout fallback, source field | CP2 | 3 | 1 |
| CP4 | Build and prove the five packages from the committed distribution/ tree, write the pins, prime the cache, record the evidence; Manager packaging and both workflows' package steps on the pins | CP3 | 2 | 1 |
| CP5 | Test suite on the release cache: NEWEST_RELEASE/UPGRADE_FROM, priming of every pinned version, four-class frozen matrix with the updated fixture, update-path test, module rework | CP4 | 4 | 1 |
| CP6 | Removal: distribution/, migration/, migration tooling, retired tests and the STOPGAP(M2) profile; CI on the release cache | CP5 | 3 | 1 |
| CP7 | Documentation, migration record and cutover runbook | CP6 | 2 | 1 |
<!-- registry-table:end -->

### CP1: package format

`src/workflow_manager/package.py`, with `build_package`, `extract_package`
and `sha256sums_text`. `tools/release/package.py` reuses the shared SHA256SUMS
writer. Tests: deterministic builds, safe-extraction refusals (links, `..`,
absolute paths, duplicates, extra or missing files, a wrong mode, a wrong
digest), a round trip on a synthetic release, and a build from a release
directory carrying `__pycache__/` that is byte-identical to a build from a
clean one (members come from the manifest, 5.1). The five real releases are
not built here.

### CP2: source, pins and cache

`src/workflow_manager/source.py`, with `ReleaseSource` and `ReleaseCache`
(`resolve` with its private snapshot, and `ensure`, 5.4),
`local_release` (the pin rule for local directories, 5.5) and the new
errors. `published_releases.json` is added (empty `releases`
until CP4) and listed as package data in `pyproject.toml`. Tests:
`tests/test_release_source.py` (5.2-5.4) over a local HTTP server and
`file://`. No real network.

### CP3: CLI and install record

`cli.py`:
- `bootstrap`, `update`, `status`, `verify` and `releases` resolve releases
  through the source;
- `--release-source`, `--release-cache`, `--release-dir` and the
  `package` subcommand are added;
- the `--manager-root` alias is deprecated;
- `missing_distribution_message` is removed;

- the checkout fallback (5.5) serves unpinned versions until CP6.

`installation.py` gains the `source` field. `tests/support.py` gains
`cli_env()` (7.1). `tools/release/package.py` and both workflow files are
**not** changed here: 5.6 lands in CP4, once versions are pinned.

Tests CP3 edits:
- `test_bootstrap.py`: `TestReleaseResolution` is rebuilt (pins, the
  checkout fallback, `--release-dir`), a new `TestManagerRootAlias` class
  tests the alias's positive branch and its deprecation notice on a
  temporary checkout it lays out itself (permanent, 7.2), and the
  empty-`HOME` class (`:1049`) takes its environment from `cli_env`;
- `test_manager_version.py`: `MissingDistributionHintTest` gets the new
  messages, and `cli.main(["releases"])` (`:229`) still exits `0` with an
  empty pin file;
- `test_bootstrap_e2e.py` (`:273`) and `test_amendment_update_path.py`
  (`:514`): their literal environments become `cli_env()`;
- `test_bootstrap.py`: a new record class proves that a record without
  `source` (every record written before M2) round-trips through
  `installation.Installation` unchanged.

**Why the full gate stays green at CP3** (challenge 2): with
`published_releases.json` empty, every CLI invocation without
`--release-dir` resolves through the checkout fallback to the same
`distribution/workflow/<v>/` directory it reads today. That covers
`test_bootstrap_e2e.py:269-317`, `test_amendment_update_path.py:507-515`,
`test_parallel_runner.py`'s `test_workflow_manager_verify_reports_no_drift`
(`verify REPO_ROOT`, `2.6.0`) and `test_manager_version.py:229`. Install
bytes are identical (INV-4); only the new record field differs, and no
existing test compares a whole record byte for byte (checked at CP3 by the
gate). INV-3 at CP3: `python3 -m workflow_manager verify .` passes through
the fallback, and the same command with `--release-dir
distribution/workflow/2.6.0` passes too; both are recorded.

**INV-2 at CP3.** CP3 is the only checkpoint where a real release installs
unpinned. The pin file is empty, so every release is unpublished to the
Manager, and the fallback applies the unpinned rule (5.5): the base's
committed tree, read through a verified snapshot and checked by
`Release.verify()`, which is what the base does today, plus the snapshot.
The pinned-version rules (the cache, the snapshot, the local-directory pin
check) are all built and tested at CP2-CP3 on synthetic pins, and they bind
the real releases from CP4, where `TestCheckoutReleasesArePinned` closes
the window (5.5). Reordering (writing the pins before the CLI) was
considered and rejected: CP4's packaging steps (5.6) need the CLI's pinned
resolution, and CP3's gate would then have to prove the fallback and the
pins together.

### CP4: build and prove the five packages

`tools/workflow_packages.py` runs on the scratch extraction of the base's
committed tree, `git archive ec38979 distribution/workflow | tar -x` (1.2,
6), never on the working tree's `distribution/workflow/`. It writes the
pins and primes the default cache. The `docs/MIGRATION.md` evidence table
is written. `tests/test_package_round_trip.py` holds the round-trip class
(which compares against the same extraction, 6; its own module, deleted in
CP6, 7.2), and `tests/test_published_packages.py` holds
`TestPinnedPackagesVerify`. `test_package_round_trip.py` also holds
`TestCheckoutReleasesArePinned`: every `distribution/workflow/<v>/` in the
same `git archive` extraction is pinned, and its `manifest.json` hashes to
the pin's `manifest_sha256` (5.5). It is deleted with the module in CP6.

Manager packaging (5.6) lands here too:
- `tools/release/package.py` loses `--manager-root` and reads its expected
  list from the pins;
- `workflow-manager-verify.yml`'s `package` job (`:172`) and `release.yml`'s
  build step (`:106`) lose `--manager-root "$GITHUB_WORKSPACE"` and gain
  the cache env and restore step;
- `release.yml`'s notes line (`:114`) reads the pins.

Tests CP4 edits for it: `test_parallel_runner.py:4958-4959` (the package
job's command and its cache step), `test_manager_version.py:395-403`
(`test_the_live_release_set`, on the pins), `test_release_workflows.py`
(the cache step before the package step), and a new host test that the
pin-derived expected list equals `published_releases.json`'s versions.

The full gate is green, with `distribution/` still present.

**Why the full gate stays green at CP4** (challenge 2): writing the pins
flips every pinned version from the checkout fallback to the cache, and
CP4 has already primed the default cache with all five packages. The
tests CP3 moved to `cli_env()` read that cache whatever `HOME` they set.
Every other test reads `distribution/` directly and is unaffected until
CP5. INV-3 at CP4: `verify .` passes through the cache, offline.

### CP5: the test suite on the release cache

`tests/support.py`:
- `NEWEST_RELEASE`, `UPGRADE_FROM` and `release()`;
- `CI_SUITES` keeps every pinned version's entry (7.1); only
  `FROZEN_MATRIX` narrows to `NEWEST_RELEASE`;
- `tests/portability_exceptions.json`, holding every existing `by_version`
  entry unchanged (7.1).

Also: the runner's priming step, `FROZEN_MATRIX` down to four classes (one
per fixture, the fourth being `updated`, 7.1), the
inventory on the cached tree, `test_update_path.py`, the module changes in
7.2 other than the deletions (including `test_conformance_suite.py`'s
class-by-class split, which creates `tests/test_authored_release_tools.py`,
and the `test_parallel_runner.py`/hardening-test references to the renamed
matrix classes), `resources.json`'s `orphan_sources` (its `frozen:` entries
reduced to `NEWEST_RELEASE`, plus the `updated` fixture's entries; its five
`host:` entries unchanged; the `repo:distribution` lock stays until CP6,
7.2), the `frozen_runs.py`
changes including `_post_run_state` for `updated` (7.1), and
`test_squash_merge_compat.py:233` dropping `--manager-root`. The
scratch-checkout apparatus moves to packages here (7.2.1: the scratch
package, pin file, source and cache; `damage_payload`'s new trigger;
`find_release` at `test_parallel_runner.py:65`/`:4119`;
`TestFrozenInventoryCountRefusal`'s layout; the scratch lock on
`repo:tools`; `:344` on `src/workflow_manager/`; the scratch's
`tests/portability_exceptions.json`). New tests: a scratch run primes and
tests only its own pinned `0.0.1` (the real pins never leak into it, and
the real cache is untouched), the retargeted scratch lock still proves
A0 exclusivity, and the pinned versions, `CI_SUITES`'s keys and
`tests/portability_exceptions.json`'s keys are one set (7.1). The full gate is green, with `distribution/` still present
but no longer read by any test module except the ones CP6 deletes.

A test asserts that no test **resolves a release through the checkout
layout**. It scans every `tests/**/*.py` outside CP6's named deletion list
(including `tests/parallel/` and `tests/frozen_runs.py`) and fails on:
- an import of `find_release`, `available_versions` or `release_root`;
- the release-directory layout, as the string `distribution/workflow` or
  as the path components `"distribution" / "workflow"`, anywhere in the
  source text, comments included.

Its exemptions are named, each scoped by `ast` to one class's line span
(or one file), each with a lifetime:
- `test_bootstrap.py::TestReleaseResolution`'s checkout-fallback and
  discovery-API tests, and the import at `:48-49`: **until CP6**, which
  deletes the fallback, the API and those tests together;
- `test_bootstrap.py::TestManagerRootAlias`: **permanent while the alias
  exists**; it tests the layout the alias is defined by (5.5);
- `test_internal_references.py::TestMigrationEvidenceManifestFieldsMatchShippedManifest`
  and `::TestAuthoredReleaseMigrationRecordMatchesShippedEvidence`:
  **permanent**; their regexes match `docs/MIGRATION.md`'s historical text,
  and their manifest reads go through `support.release(v)` (7.2);
- the write-barrier lint's fixture text in `test_parallel_runner.py`
  (`:3449-3482`): **until CP6**, which removes the retired tools from
  `TOOL_SCRIPTS` and rebases the `DIST` examples (7.2.1).

`tests/support.py:102`'s `CI_SUITES` comment is rewritten in CP5 (the
entries are frozen records, and only the newest is run), so it needs no
exemption. The same holds for `test_bootstrap_e2e.py:281-289`'s comment
and `tests/parallel/inventory.py:16-21`'s docstring, both rewritten in CP5
(7.2). What still reads the layout at CP5 without an exemption is only in
modules on CP6's deletion list, which the scan skips:
`test_authored_release_tools.py` and `test_package_round_trip.py` (7.2),
with the modules CP6 already deleted as `migration/`'s evidence.
`tests/parallel/resources.json` is not a module and is not scanned; its
`repo:distribution` reason goes in CP6. `support.py`'s
`migration/classification.json` read is not a `distribution/workflow`
reference and the assertion does not cover it; it goes in CP6. The
assertion is satisfiable at CP5 (by the exemptions above) and after CP6
(the two `until CP6` exemptions are removed from the test in the same edit
that deletes what they cover; a stale exemption naming a missing class
fails the test, so none lingers).

### CP6: removal

The following are deleted:
- `distribution/`, `migration/`, `tools/migrate.py` and
  `tools/build_release.py`;
- the retired test modules, by name: `test_payload_bytes.py`,
  `test_templates.py`, `test_migration_inventory.py`,
  `test_no_live_state_imported.py`, `test_amendment_update_path.py`,
  `test_implementation_review_two_stage_disposable_repo.py`,
  `test_stopgap_profile.py`, `test_authored_release_tools.py` (CP5's split
  of `test_conformance_suite.py`) and `test_package_round_trip.py` (CP4's
  round-trip class). Every retirement is module-granular, so this list and
  CP5's scan exclusion are the same set;
- the stopgap, per `docs/ARCHITECTURE.md`'s record;
- the checkout fallback (5.5), and `release.py`'s `release_root`,
  `available_versions` and `find_release`, with `test_bootstrap.py`'s
  fallback and discovery-API tests and their import (`:48-49`, `:980-985`);
  `TestManagerRootAlias` stays;
- `distribution/` and `migration/` from `GUARDED_TREES`, with the barrier
  message and the tests that name them (7.2);
- in the same edit, `resources.json`'s `repo:distribution` exclusive entry
  and resource definition, whose holder is deleted here, leaving
  `resources: {}` and `exclusive: {}` (7.2); its five `host:`
  `orphan_sources` entries stay; with them
  `test_parallel_runner.py`'s `EXCLUSIVE_UNIT` (`:68`), and the two
  real-declaration assertions are rewritten: the committed declaration
  loads, declares no exclusive unit, every `orphan_sources` id is a
  discovered unit and every `frozen:` one is `NEWEST_RELEASE`'s
  (`:289-296`), and the real-plan
  test drops its A0 check (`:2266-2270`), which the scratch lock carries
  (7.2);
- `release.yml`'s upstream fetch step and `UPSTREAM_*` env, with the
  `test_release_workflows.py:130` requirement (5.6);
- `support.py`'s `CLASSIFICATION`, `FROZEN_COMMIT`, `FROZEN_TAG`,
  `UPSTREAM` and upstream helpers, with `test_parallel_runner.py:4718` and
  `:4845`, and `scratch_checkout`'s `migration/` files (7.2.1);
- the deprecated `--fast` alias (`D-Fast-Flag`), which five of its eight
  modules' deletion leaves pointing at nothing. **Every** live reference
  goes in the same edit, because `validate()` reads each name in
  `ALLOWED["run"]` from `args` (`cli.py:197-198`), so one stale entry makes
  every ordinary run raise `AttributeError`. In `tests/parallel/cli.py`:
  `FAST_ALIAS_SELECTION` and its comment (`:50-61`); the `--fast` argument
  and its help text (`:139-141`); `"fast"` in `ALLOWED["run"]` (`:175`);
  `"fast": False` in `_DEFAULTS` (`:185`); the parser refusal
  (`:204-205`); the selection line, which becomes
  `specs = list(args.select)` (`:272`); and the note emission
  (`:283-284`). The stopgap block's `--fast` mentions (the
  `--newest-release-only` help at `:135` and the refusal at `:208-210`) go
  with the stopgap in the same checkpoint. Elsewhere: `report.FAST_NOTE`
  (`report.py:33-34`); `inventory.py`'s `--fast` mentions (`:425`,
  `:440`); `test_parallel_runner.py`'s `TestFastAliasAndDirectEntryPoints`
  alias tests (`:3865-3887`, 7.2); and the hardening test's alias half
  (`:1424-1435`, below). `test_amendment_update_path.py:448` and
  `test_stopgap_profile.py`'s `--fast` cases go with their modules. The
  retired-name assertion below also lists the identifiers
  `FAST_ALIAS_SELECTION`, `FAST_NOTE`, `args.fast` and the string
  `"--fast"` for every kept file under `tests/` (its exemptions: its own
  list, and `TestDirectEntryPoints`'s refusal test below, by `ast` span),
  so a missed site fails CP6's own gate by name. `TestDirectEntryPoints`
  gains two runner tests, both through `run_cli` on a scratch checkout:
  an ordinary run (no flags, and `--select test_scratch_extra.py`) exits
  `0`, which exercises `validate()` and the selection line with the flag
  gone; and `--fast` exits `2` with argparse's `unrecognized arguments`,
  so the flag is gone rather than silently ignored. It was deprecated in Manager `v1.1.0` and
  "survives one release"; M2's release is the next one, so it ends there.
  The runner is `tests/`, not the shipped package, so this is not a
  Manager interface change (`OD-M2-3`). `test_parallel_runner.py`'s alias
  tests go and its real-inventory tests move to `test_bootstrap.py` (7.2);
- the hardening test's v2.3.1-002 repository-level guard (`:1423-1435`)
  retargeted to `test_update_path.py`, and its `:946` comment reworded
  (7.2, `OD-M2-5`);
- `src/workflow_manager/__init__.py`: the `available_versions`/`find_release`
  import and `__all__` entries (`:10`, `:17-18`) go with the discovery API,
  and the module docstring (`:4`, "`distribution/` holds one immutable …
  copy") describes packages, pins and the cache instead (`OD-M2-3`);
- `isolation.py`'s `TOOL_SCRIPTS` and `TOOL_ENTRY_POINTS`, with the lint
  branches that read them and the lint fixtures' tool lines; the fixtures'
  `DIST` examples are rebased on `tools/`, and CP5's layout assertion loses
  its two `until CP6` exemptions (the lint fixtures and
  `TestReleaseResolution`'s fallback and discovery-API tests); its
  permanent ones stay (CP5).

A test asserts that no retired module is still named: no kept
`tests/**/*.py` (including `tests/parallel/` and `tests/frozen_runs.py`)
names, in code or comments, a module on the deletion list above, or one of
the retired `--fast` identifiers (the `--fast` item above). Its only
exemptions are its own lists of those names and
`TestDirectEntryPoints`'s `--fast` refusal test. It lives beside CP5's layout
assertion and closes the class of miss that CP5's assertion closes for
`distribution/workflow`. At the base its hits are exactly the ones this
checkpoint rewrites: `tests/parallel/cli.py`'s `FAST_ALIAS_SELECTION`,
`test_parallel_runner.py:29`, `:68`, `:232-233`, `:3524` and `:3890-3891`,
`test_workflow_2_6_0_hardening_disposable_repo.py:946` and `:1429-1430`,
and `test_bootstrap.py:1032` (the hits at `test_conformance_suite.py:469`
and `:597` are in classes CP5 moves to `test_authored_release_tools.py`,
which is on the list). `tests/parallel/timings.json` is not a module and is
not scanned: its entries for retired units are estimates nothing reads
once the units are gone, and they drop out at the next timing refresh.

`test_manager_version.py:289-293` is rewritten for the alias on a checkout
without `distribution/` (7.2). The CI changes in 7.3 land. `TestAssertFullPlanRefusesTheStopgap` moves.
The full gate is green, and its total is recorded.

### CP7: documentation and evidence

- `docs/ARCHITECTURE.md`:
  - the distribution/state boundary becomes the package, source and cache
    boundary;
  - the stopgap sections are removed;
  - "Verification execution" now covers priming.
- `docs/MIGRATION.md`: the M2 record, which cites `ec38979` as the last
  commit carrying `distribution/`, and records v2.3.1-002's
  repository-level guard's retarget to `test_update_path.py` (`OD-M2-5`),
  stating that the retargeted guard is narrower: it proves the pinned
  update path runs in the full selection, and no longer covers the
  `2.3.1`→`2.4.0` suite.
- `docs/RELEASING.md`:
  - a Workflow-packages section: how a pin is added;
  - installing without a checkout;
  - the K1-K5 cutover.
- `README.md`, including its `--fast` sentence (`:154`), which goes with the
  alias (CP6).
- `docs/ARCHITECTURE.md`'s `--fast` mention (`:346`) and its release-API
  table row for `available_versions()`/`find_release()` (`:717`).
- `CLAUDE.md`'s non-managed part:
  - the `--fast` sentence ("survives one release as a deprecated alias
    for a targeted `--select` of eight modules") is removed: the alias
    ended with M2's release (CP6);
  - the hard rules and the "Adding … release" sections are rewritten for
    packages and pins;
  - the downgrade posture is kept, with its `distribution/…` paths replaced
    by package references.

## 11. Requirements traceability

See `docs/ai-workflow/requirements/workflow-manager-packaged-distribution-mapping.json`.
REQ-1 package format (CP1, CP4); REQ-2 source and pins (CP2, CP3); REQ-3
cache and offline (CP2, CP5); REQ-4 CLI (CP3); REQ-5 byte-for-byte proof and
publication record (CP4, CP7); REQ-6 test reduction (CP5, CP6); REQ-7 removal
of `distribution/`, `migration/` and their tooling (CP6); REQ-8 stopgap
removal (CP6, CP7); REQ-9 documentation and cutover (CP7).

## 12. Review logistics

Plan review:
- a local `/review-plan`;
- then the manual external (Codex) round;
- then the user's `/approve-review plan`, which records the section 8
  decisions.

Every implementation gate runs the full `python3 tests/run_all.py`. From
CP4 onwards it runs offline, from the primed cache.

## 13. `SELF_REVIEWING_PLAN`

- **Order.** A package is proved (CP4) before anything stops reading
  `distribution/` (CP5), and that happens before anything is deleted (CP6).
  Each step can be reverted on its own.
- **Offline gates.** CP4 primes the cache, so nothing between CP4 and
  acceptance needs the `workflow` repository to exist. Only the cutover does.
- **The first PR run needs K2.** CI resolves packages from the default URL,
  so the pull request is pushed only after K2 (9, K4).
- **Compression determinism.** It is not assumed across machines (5.1). The
  pins are the digests of the archives that are actually published.
- **This repository's own install.** `verify .` after M2 resolves `2.6.0`
  through the cache, and INV-3 is checked at every checkpoint.
- **Test totals.** They fall sharply by design (about 9,000, 1.2). `CI_SUITES` pins still
  catch a silently skipped suite for the newest release; the older
  versions' entries stay as frozen records that nothing runs (7.1).
- **Between CP3 and CP4, nothing is pinned yet.** The checkout fallback
  (5.5) serves every version from `distribution/` in that window, so no
  CLI-driving test changes behaviour at CP3 and none is edited twice; CP3
  and CP4 each state why their full gate is green. CP4's pins flip the
  resolution to the cache. CP6 removes the fallback, and its test asserts
  that an unpinned version without `--release-dir` refuses with
  `ReleaseNotPublishedError`.
- **The path-rule check lives until CP6.** Every new module and file that
  CP1-CP5 add gets its own `tools/ci/pr_profile_paths.json` rule (`full`)
  until CP6 deletes the file together with `TestPathRulesAreComplete`.
  These include `tests/test_release_source.py`,
  `tests/test_published_packages.py`, `tests/test_package_round_trip.py`
  (CP4), `tests/test_authored_release_tools.py` (CP5),
  `tests/test_update_path.py` and `tests/portability_exceptions.json`.
- **The cache outside the checkout.** CP4 primes
  `~/.cache/workflow-manager/releases` on the machine that runs the gates.
  That is intended: it is the Manager's own default cache, it holds only
  pinned and verified content, and deleting it only forces a re-download.
  No gate writes it anywhere else.

## 14. Review dispositions

### Round 1 (`LOCAL_MODEL_PLAN_REVIEW`, revision 1, `REVISE`)

Every finding was checked against the base before it was applied.

- **F1, accepted as option (b).** Confirmed: `cli.py:50`'s `MANAGER_ROOT`
  and `:263`'s `--manager-root` default serve the CLI-driving tests the
  finding lists. Revision 2 adds the **checkout fallback** (5.5): an
  unpinned version resolves to `MANAGER_ROOT/distribution/workflow/<v>/`
  until CP6 removes it with `distribution/`. Option (a) was not taken
  because it would edit those tests at CP3 only for CP4 to change their
  route again. CP3 and CP4 each now state why their full gate is green and
  how INV-3 is checked, and CP3 names every test it edits.
- **F2, accepted.** Confirmed: `Release.verify()` (`release.py:184-214`)
  reads only the tree's own manifest. A hit now also requires
  `sha256(tree/manifest.json) == manifest_sha256` and a matching manifest
  version (5.4), and both refusals are in `test_release_source.py` (7.2).
- **F3, accepted.** (a) Priming resolves every pinned version (INV-5, 7.1),
  which also covers the hardening test's scenario 4 (`2.3.1`, `2.4.0`,
  `test_workflow_2_6_0_hardening_disposable_repo.py:624,639`), a reader the
  finding did not name. (b) Confirmed at `test_bootstrap_e2e.py:273`,
  `test_amendment_update_path.py:514` and, also unnamed by the finding,
  `test_bootstrap.py:1052`, which sets an empty `HOME` on purpose. Those
  environments come from `support.cli_env()`, which always passes the
  resolved cache directory, and CI names its cache directory explicitly
  (7.1, 7.3).
- **F4, accepted.** Confirmed: `frozen_runs.py:57,107-113,217,458-479`,
  `test_parallel_runner.py:895,1255,1429` and `resources.py:23`'s
  `GUARDED_TREES`. Their dispositions are in 7.1, 7.2, CP5 and CP6.
  `release.py`'s discovery API is kept until CP6 and then deleted (5.5).
  The cache stays outside the write barrier, and 5.4 records why.
- **F5, accepted.** Confirmed: `git status --ignored` shows untracked
  `payload/scripts/__pycache__/` under `2.4.0`-`2.6.0`. Package members
  come from the manifest (5.1), the base tree comes from `git archive` (1.2,
  6), and 5.4 records that frozen suites run from fixture copies
  (`frozen_runs.py:237`), not in place.
- **F6, accepted.** `http://` is allowed for loopback hosts only, and
  redirects never downgrade the scheme (5.2).
- **F7, accepted with a different mechanism.** Confirmed: `resources.json`
  declares `TestStateLock` only under `frozen:<v>/<fixture>/…` ids. Instead
  of adding a host-unit orphan entry, revision 2 runs the newest suites
  in the updated repository as a fourth frozen fixture, `updated` (7.1). The
  suites stay chunked and parallel, and the orphan entry keeps the frozen
  form (7.2). The difference from the hardening test's scenario 9 is
  recorded in 7.2's `test_update_path.py` row.
- **F8, accepted.** `CI_SUITES["2.6.0"]` sums to 2,002. The estimate is now
  about 9,000 (1.2).
- **F9, accepted.** 5.1's sentence is corrected.

### Round 2 (`LOCAL_MODEL_PLAN_REVIEW`, revision 2, `REVISE`)

Every finding was checked against the base before it was applied.

- **G1, accepted, with the change moved to CP4.** Confirmed:
  `workflow-manager-verify.yml:172` and `release.yml:106` pass
  `--manager-root "$GITHUB_WORKSPACE"`; `test_parallel_runner.py:4958-4959`
  pins the first; `package.py:103-106` walks `distribution/workflow`;
  `test_manager_version.py:292,395-403` and `test_squash_merge_compat.py:233`
  call the alias; `release.yml:65-70` fetches the upstream, and
  `test_release_workflows.py:130` requires it. 5.6 now names each
  invocation, the smoke check (`--version`, `releases`, and `verify
  <checkout>` through the cache) and its cache and network behaviour. The
  change itself moves from CP3 to CP4: at CP3 nothing is pinned, and the
  installed wheel has no checkout fallback, so `verify <checkout>` would
  fail there. The registry's CP3 and CP4 names change accordingly, and
  REQ-4 now maps to CP4 too. The alias falls through to the pins when the
  checkout has no `distribution/` (5.5), so the two alias callers keep
  working; `test_squash_merge_compat.py:233` still drops the alias (CP5),
  and `test_manager_version.py:292` is rewritten for the fall-through
  (CP6). The upstream fetch step goes in CP6. The requested wheel-building
  test is covered differently: a host test checks the pin-derived list,
  and building the wheel stays the CI `package` job's proof, because no
  host test builds a wheel today (`test_parallel_runner.py:4947-4960` checks
  the job's text only).
- **G2, accepted.** Confirmed: `resources.json:2-9,72-79` and
  `resources.py:133`. The `repo:distribution` entry and resource now go in
  CP6, in the same edit as the holder's deletion and `GUARDED_TREES` (7.2,
  CP5, CP6). CP4's round-trip class needs no lock of its own: the holder is
  exclusive, and an exclusive chunk runs alone in pre-phase A0
  (`isolation.py:771-777`, `executor.py:9`).
- **G3, accepted.** CP5 now says four classes. CP4 now says the tool runs
  on the `git archive` extraction.
- **G4, accepted.** 7.1 now states the `updated` builder (it resolves
  `UPGRADE_FROM` itself, and commits after `update`), the expected failure
  set (the same as `bootstrapped`'s, keyed by version; a failure only in
  the updated repository is a `docs/defects/` write-up, never an
  exception key), and the post-run checks (`_post_run_state` extended to
  `updated`).
- **G5, accepted.** The round-trip class compares against the `git archive`
  extraction and the manifest's file set (6).
- **G6, accepted.** Confirmed at `test_bootstrap_e2e.py:183-191`: it
  updates `2.3.1` to itself. It moves to `NEWEST_RELEASE` (7.2).
- **G7, accepted.** The review request's challenge list is renumbered in
  order.

### Round 3 (`LOCAL_MODEL_PLAN_REVIEW`, revision 3, `REVISE`)

The finding was checked against the base before it was applied.

- **H1, accepted, with the scratch conversion in CP5.** Confirmed:
  `test_parallel_runner.py:65,4119` (`find_release`), `:2347-2398`
  (`SCRATCH_PAYLOAD`, the scratch modules, `SCRATCH_RESOURCES` on
  `repo:distribution`), `:2520-2541`, `:2553` and `:2584-2587`
  (`scratch_checkout` copies `support.py`, `frozen_runs.py` and
  `src/workflow_manager/` verbatim), `:2606-2610` (its `migration/` files),
  `:773` (feeding `inventory.py:231`), `:344`; `support.py:17-20`;
  `isolation.py:1029-1032` and the lint fixtures at `:3449-3482`. The
  conversion is done in CP5, not split, because the scratch copies the
  very modules CP5 rewrites: left on the old layout it would prime the
  real pins and turn CP5's gate red. New section 7.2.1 gives each part its
  checkpoint. Three couplings the finding did not name are covered too:
  the `builder_raises` case (`:3725`), whose damaged payload priming would
  now refuse first, gets a trigger that survives verification;
  `test_parallel_runner.py:4718,4845` read `support.CLASSIFICATION` and
  `FROZEN_COMMIT`, so they go in CP6 with those names; and `support.py`'s
  upstream helpers (`:32-60`) have only CP6-deleted consumers. CP5's
  assertion now also matches the path-component form and has one named
  exemption (the lint fixtures), which CP6 removes. Both requested missing
  tests are in CP5.

### Round 4 (`LOCAL_MODEL_PLAN_REVIEW`, revision 4, `REVISE`)

Each finding was checked against the base before it was applied.

- **I1, accepted: the assertion is rescoped with named, lifetimed
  exemptions.** Confirmed: `test_bootstrap.py:48-49` imports
  `available_versions`/`find_release`, `:963` builds `"distribution" /
  "workflow"`, `:980-985` test the discovery API; `test_internal_references.py`
  reads manifests at `:369` and `:430` and matches the literal
  `distribution/workflow/<v>/manifest.json` text at `:352` and `:446`
  (`docs/MIGRATION.md:215`, `:272`); `support.py:102`'s comment. CP5's
  assertion now forbids resolving a release through the layout and names
  four exemptions with lifetimes (two until CP6, two permanent). The
  alias's positive branch gets a permanent class, `TestManagerRootAlias`
  in `test_bootstrap.py` (CP3), which lays out its own temporary checkout
  and so survives CP6. `test_internal_references.py` gets its own 7.2 row
  (CP5): the two manifest-quoting classes stay and read through
  `support.release(v)`; `TestMigrationEvidenceCountsMatchCiSuites` and the
  `2.6.0` fixture row's base-release delta checks go, because
  `CI_SUITES` keeps only the newest release (a coupling the finding did
  not name: `:278-333`, `:492-508`).
- **I2, accepted.** Confirmed: `test_parallel_runner.py:68`
  (`EXCLUSIVE_UNIT`), `:289-296` and `:2266-2270`; `resources.py:113-114`
  accepts empty objects. CP6 deletes the constant and rewrites both
  assertions (7.2's row, CP6's list), and 7.2 states the post-CP6
  `resources.json`: empty `resources` and `exclusive`, `orphan_sources` for
  `NEWEST_RELEASE`'s four fixtures.
- **O1, accepted.** 7.1 states the one-pin behaviour: `UPGRADE_FROM` is
  `None`, `FROZEN_MATRIX` omits `updated`, the builder resolves it lazily,
  and a real-repository test asserts it is not `None`.
- **O2, accepted.** 7.1 states that `cli_env(**extra)`'s keyword arguments
  override the cache and source defaults, and that the scratch relies on
  that override.
- **Missing tests.** Both are in the plan: `TestManagerRootAlias` (CP3,
  kept after CP6) and the rewritten `TestResourcesContract` test (CP6).

### Round 5 (`LOCAL_MODEL_PLAN_REVIEW`, revision 5, `REVISE`)

Each finding was checked against the base before it was applied.

- **J1, accepted, with a different fix for its first two causes.**
  Confirmed: `test_conformance_suite.py:615-633` subscripts
  `CI_SUITES[version]` for every authored release, `:838-878` calls
  `expected_portability_exceptions` for `2.5.0`/`2.3.1`/`2.4.0`
  (`support.py:186` subscripts unguarded), and the module imports
  `find_release` (`:69`) and builds the layout at the lines cited. The
  check found more readers of the old data than the finding lists:
  `test_internal_references.py`'s `TestReadmeStatusTableMatchesCiSuites`
  (`:533-691`) and `:527` read `CI_SUITES`/portability for `2.3.1` to
  `2.6.0`, and `test_workflow_2_6_0_hardening_disposable_repo.py:1416-1422`
  reads `migration/portability_exceptions.json` and names
  `TestBootstrappedTarget260`. So revision 6 no longer shrinks the data:
  `CI_SUITES` and `tests/portability_exceptions.json` keep every pinned
  version's entry as a frozen record, and only `FROZEN_MATRIX` narrows
  (the inventory reads `CI_SUITES` only for `FROZEN_MATRIX`'s versions,
  `inventory.py:228-251`). That also restores revision 5's deletions in
  `test_internal_references.py` (`:278-333`, `:492-508`). The layout
  cause is fixed by moving: `test_conformance_suite.py`'s 7.2 row now
  disposes of every class and helper below `:314` by name; two stay
  permanently (one rewritten on `support.release`), and ten move in CP5 to
  `tests/test_authored_release_tools.py`, which CP6 deletes. CP4's
  round-trip class gets its own module, `tests/test_package_round_trip.py`,
  for the same reason. CP6's deletion list now names every retired module,
  so every retirement is module-granular (the architecture concern). The
  per-version matrix classes get unversioned names (7.1), and
  `test_parallel_runner.py`'s references to them (`:874-877`, `:1044`,
  `:1360`, `:1372`) follow in CP5. The requested missing test (the keys
  of `CI_SUITES` and of the portability file equal the pins) is in 7.1
  and CP5.
- **J2, accepted.** Confirmed: `resources.json`'s `orphan_sources` holds
  the five `host:` entries named, all in modules M2 keeps. 7.2 states that
  they stay unchanged through CP5 and CP6, the post-CP6 content includes
  them, and the rewritten `TestResourcesContract` test asserts that every
  id is a discovered unit and every `frozen:` id is a `NEWEST_RELEASE`
  unit (7.2, CP5, CP6).
- **O1, accepted.** Confirmed: `ReferenceCase.setUp` (`:98`) and the
  import (`:21`). The case stays on `2.3.1` through
  `support.release("2.3.1")`: `TestCommandInventoryAndGoldenHashes`
  (`:220-275`) asserts `2.3.1`'s own command corpus and golden hashes.
- **O2, accepted.** Confirmed: `test_bootstrap_e2e.py:281-289` and
  `inventory.py:16-21`. Both are rewritten in CP5 (7.2 and CP5's
  assertion paragraph), with no exemption.

### Round 6 (`LOCAL_MODEL_PLAN_REVIEW`, revision 6, `REVISE`)

Each finding was checked against the base before it was applied.

- **K1, accepted.** Confirmed at every cited line:
  `tests/parallel/cli.py:52-61` names five modules CP6 deletes;
  `test_parallel_runner.py:231-235` selects `test_templates.py` over the
  real inventory, `:3883-3887` resolves the alias over it, `:3888-3893`
  runs `test_templates.py` directly, and `:3519-3525` reads
  `test_amendment_update_path.py` and expects `EXCLUSIVE_UNIT`;
  `test_workflow_2_6_0_hardening_disposable_repo.py:1423-1435` asserts that
  `test_amendment_update_path.py` is in the full selection and in the
  alias. Dispositions (7.2, CP6, CP7):
  - `--fast` is **removed** in CP6, not redefined: `v1.1.0` shipped it
    deprecated with "survives one release", and M2's release is the next.
    `CLAUDE.md`, `README.md:154` and `docs/ARCHITECTURE.md:346` lose their
    `--fast` sentences in CP7;
  - `:231-235` and `:3888-3893` move to `test_bootstrap.py` (the direct
    run on `TestInstallationRecord`, which needs no release); `:3519-3525`
    becomes "the real tests are lint-clean against a declaration with no
    exclusive unit";
  - v2.3.1-002's repository-level guard is **retargeted** to
    `test_update_path.py` (recorded in `OD-M2-5` and CP7's
    `docs/MIGRATION.md` record); its alias half goes with the alias;
  - the optional check is taken: CP6 adds a retired-module-name
    assertion beside CP5's layout assertion. A grep of every kept file at
    the base found three hits the finding does not list, all comments or
    docstrings: `test_parallel_runner.py:29`,
    `test_workflow_2_6_0_hardening_disposable_repo.py:946` and
    `test_bootstrap.py:1032`. CP6 rewords them. `tests/parallel/timings.json`'s
    retired entries are inert (`timings.load` keeps estimates only for
    lookup, and nothing looks up a unit that no longer exists), so they are
    left to the next refresh.
- **O1, accepted, with the docstring in CP6, not CP7.** Confirmed:
  `src/workflow_manager/__init__.py:4`, `:10`, `:17-18`. The docstring
  describes `distribution/`, which exists until CP6, so it changes in the
  same CP6 edit that drops the re-exports. `OD-M2-3` states why neither
  removal makes the title `feat!:`, and 5.5 names the `__init__` importer.
- **O2, accepted.** Confirmed: `test_bootstrap.py:63`, `:79`, `:836`, and
  `"2.3.2"` at `:532`, `:548-549`, `:752`, `:821`, `:840`, `:848`, `:932`.
  The `BootstrapCase` retarget is in CP5, and the synthetic next version is
  `NEWEST_RELEASE`'s patch plus one. `:965-999` belongs to
  `TestReleaseResolution`, which CP3 rebuilds.
- **O3, accepted.** Confirmed: `PAYLOAD_260` at `:1349`, used at `:1389` and
  `:1399`, is named in the hardening row.

### Round 7 (`LOCAL_MODEL_PLAN_REVIEW`, revision 7, `APPROVE`)

Optional findings only. O1 (the `cli.py` `--fast` sites at `:175`, `:185`,
`:272`, `:283-284`) is the same miss as the external round's I2 below and is
applied there. O2 (`docs/ARCHITECTURE.md`'s sections) and O3 (the
v2.3.1-002 retarget is weaker than the original guard) are carried by CP7:
its `docs/ARCHITECTURE.md` and `docs/MIGRATION.md` items, where the M2
record states that the retargeted guard proves the pinned update path runs
in the full selection, and no longer names the `2.3.1`→`2.4.0` suite.

### External round 1 (`MANUAL_EXTERNAL_PLAN_REVIEW`, revision 7, `REVISE`)

Each finding was checked against the base before it was applied.

- **B1 (cache verification separated from installation), accepted.**
  Confirmed: `Release.__init__` reads `manifest.json` from disk
  (`release.py:81-86`), and the installer checks each file against that
  parsed manifest (`install.py:358-360`, `read_verified`). With revision 7's
  `resolve()` returning `tree/` after releasing the lock, a self-consistent
  swap of manifest and payload between the two would install unpinned
  bytes, and a later swap would fail mid-install. Disposition (5.4 steps
  5-6, INV-2): `resolve()` snapshots the manifest-enumerated files into a
  private `0700` directory **under the lock**, verifies the snapshot
  against the pin, and returns `Release(snapshot)`, so the shared cache is
  never on the install's read path. Priming uses the snapshot-free
  `ensure()`; `support.release` memoizes one snapshot per version per
  process. The "a mid-run mutation is caught by the hit check" claim is
  replaced. The missing tests are added to `test_release_source.py` (7.2):
  the resolve/install boundary swap, and a lock-ignoring writer mid-snapshot.
- **B2 (local resolution bypasses pins), accepted.** Confirmed against 5.5
  as written: `--release-dir` and the alias checked only `Release.verify()`,
  which checks a tree against its own manifest (`release.py:184-212`).
  Disposition (5.5, INV-2): one `source.local_release` for `--release-dir`,
  the alias and the fallback. A pinned version must match its pin's
  `manifest_sha256` or is refused, and a match is recorded as the package.
  An unpinned version is the scoped unpublished path, recorded
  `source.kind: "local"`. A version that differs from `--release-version`
  is refused. `TestManagerRootAlias` uses an unpinned synthetic version for
  its positive branch and gains the altered-pinned refusal. Both local
  options are covered in `test_release_source.py` (7.2).
- **I1 (CP3's fallback vs INV-2), accepted: stated and bounded, order
  kept.** Confirmed: the pin file is empty at CP3 (CP2, 5.3), and the
  fallback installs the checkout's trees. INV-2 now distinguishes pinned
  from unpinned versions and names CP3 as the one checkpoint where the real
  releases are unpinned (no weaker than the base, which checks them by
  `Release.verify()` alone). CP4 closes the window with
  `TestCheckoutReleasesArePinned` (in `test_package_round_trip.py`, deleted
  in CP6). The reordering alternative is recorded and rejected in CP3's
  "INV-2 at CP3".
- **I2 (`--fast` removal leaves gate-breaking references), accepted.**
  Confirmed at `tests/parallel/cli.py:175` (`ALLOWED["run"]`), `:185`
  (`_DEFAULTS`), `:197-198` (`validate()` reads every `ALLOWED["run"]` name
  from `args`), `:272` (the selection) and `:283-284` (the note). CP6's
  item now lists every site, the stopgap block's two mentions (`:135`,
  `:208-210`) are assigned to the stopgap removal, the retired-name
  assertion covers the `--fast` identifiers, and `TestDirectEntryPoints`
  gains an ordinary run and a `--fast` refusal through the runner, so a
  stale reference fails inside CP6's gate.

### External round 2 (`MANUAL_EXTERNAL_PLAN_REVIEW`, revision 8, `REVISE`)

- **I1 (offline snapshot failure has conflicting required errors),
  accepted.** Confirmed: 5.4 step 5 said a failed snapshot is discarded and
  refetched once, the end of 5.4 said an offline refetch raises
  `ReleaseUnavailableError`, and the lock-ignoring-writer test in
  `test_release_source.py`'s row (7.2) required `ReleaseIntegrityError`
  offline. Local round 8 raised the same point as an optional finding.
  Disposition: the error follows the cause. A refetch that cannot be made is
  a fetch failure with nothing cached (the entry was just discarded), so it
  raises `ReleaseUnavailableError`, matching 5.5's definition ("fetch failed
  and nothing cached"). A refetch that succeeds but whose snapshot fails
  again raises `ReleaseIntegrityError`. 5.4 step 5 now states both, and the
  test row asserts both: `ReleaseUnavailableError` offline, and
  `ReleaseIntegrityError` after exactly one refetch when the seam alters
  the second snapshot as well.
