# Workflow Manager: Release-Agnostic Manager (Revision 5)

`work_item_id: workflow-manager-release-agnostic` -- `governing_workflow_version: "2.2"`

**Deliverable:** a Manager release (a minor, from a `feat:` pull-request title)
that installs a Workflow release published after it, with no Manager pin pull
request and no Manager release for that Workflow release. The Manager finds
published releases itself, verifies each one by its published `SHA256SUMS` and
manifest digest, and reads the release-specific data it hard-codes today
(downgrade boundary, new-work-only fixes, gate-default change, frozen suite
counts, portability exceptions, minimum Manager version) from the release's
own manifest, falling back to its built-in data for the releases that predate
the fields.

**Work item type:** `process` (Manager tooling; no Workflow release).
**Base commit:** `dff497db9e5dc8511d5d64dc894b55a9cedc0842` (tip of `main`;
Workflow 2.12.0 installed here with automatic gates, no `GATE_POLICY.json`).
**Branch:** `milestone/workflow-manager-release-agnostic`. The milestone
reaches `main` through one pull request, opened and merged by the user. Its
title is `feat: ...`, which releases a Manager minor.
**Scope source:** `docs/ROADMAP.md` item 8 (this milestone adds it as the
current Next item); the owner's decision of 2026-10-11 and its agreed shape.
Size: at most 6 checkpoints; this plan has 5.

## 1. Goal, fixed inputs and non-goals

1. **Today's cost.** Every Workflow release forces a Manager pin pull request
   (`feat: pin Workflow X`), a Manager minor release that adds only the pin,
   and a second CI cycle. After this milestone a Workflow release is
   installable without any of those, unless the Manager's own machinery
   changes.
2. **Fixed inputs** (not re-decided here):
   - Published Workflow releases are immutable GitHub releases of
     `RodrigoFAbreu/workflow` with three assets each (`workflow-V.tar.gz`,
     `workflow-V.manifest.json`, `SHA256SUMS`).
   - Existing pins in `src/workflow_manager/published_releases.json` stay and
     are never changed. This milestone adds no pin and removes none.
   - Adding the manifest fields is a Workflow release's job, in the `workflow`
     repository. This milestone must not depend on that release landing
     first (section 5).
   - Every test stays hermetic: no network, no dependence on a release that
     appeared overnight.
3. **Non-goals.** Building or publishing any Workflow release; changing a
   pin; Controller work; RepFlow; a signature scheme (section 3.1 says why);
   removing the `--release-dir` or `--manager-root` paths.

### 1.1 Requirements

| Id | Requirement |
|---|---|
| R1 | Discovery and trust: the Manager discovers published releases and verifies an unpinned one by `SHA256SUMS` and manifest digest; pins stay authoritative for the releases they name (CP1). |
| R2 | Release metadata travels with the release: the manifest's optional `manager` block carries the per-release data, the Manager reads it when present and falls back to built-in data otherwise (CP2). |
| R3 | `min_manager_version`: an older Manager refuses a release that needs a newer one, naming the Manager version to install; bare `update` skips to the newest compatible release (CP2). |
| R4 | Deterministic CI: pull-request CI never changes behavior because a release appeared; the tested releases come from a lock file, and the nightly tests the newest published release (CP3). |
| R5 | Offline and cache: the release cache and the `WORKFLOW_MANAGER_RELEASE_SOURCE` mirror keep working, discovery never makes an offline run fail where it works today, and every test is hermetic (CP1, CP3). |
| R6 | Timings are keyed so a new release does not orphan them (CP4). |
| R7 | Documentation: "adding a pin" becomes "adding a release" (or is retired), `CLAUDE.md` matches, and the docs tell an operator what to do when a release is published (CP5). |
| R8 | The Workflow-side change is named precisely as a separate follow-up for the `workflow` repository (section 5, published as `docs/release-metadata.md` in CP5). |

## 2. What exists today

Cited at the base commit.

- **Pins are the only door.** `source.load_pins` reads the pin file;
  `ReleaseCache._pin` raises `ReleaseNotPublishedError(kind="unpinned")` for
  any other version; `_fetch` accepts a download only when archive and manifest
  match the pin **and** `SHA256SUMS` (`source.py`). `local_release` applies the
  pin to a `--release-dir` of a pinned version.
- **"Newest" is the newest pin.** `cli._default_version` returns
  `pins.versions()[-1]`; `bootstrap`, `update`, `doctor` and `update --dry-run`
  use it; `status` and `verify` resolve the version the record names.
- **Per-release data in code.** `compatibility.py` holds
  `DOWNGRADE_BOUNDARIES` (a `Boundary` whose `Signal`s carry detector
  functions), `NEW_WORK_ONLY` and `GATE_DEFAULT_CHANGES`, each with an entry
  for every pinned version (a test enforces it). `tests/support.py`'s
  `CI_SUITES` and `tests/portability_exceptions.json`'s `by_version` hold the
  frozen counts and exceptions, one entry per pinned version
  (`TestPinnedVersionsCarryTheirRecords`).
- **The test selection follows the pins.** `support.PINNED_VERSIONS`,
  `NEWEST_RELEASE` (the last pin) and `UPGRADE_FROM` (the one before) feed the
  frozen matrix; `tests/parallel/priming.py` primes every pin; the CI cache key
  is the hash of the pin file. A new pin therefore moves every pull request.
- **Timings are per release.** `tests/parallel/timings.json` keys frozen units
  as `frozen:<version>/<fixture>/<suite>::<Class>`. The committed file holds
  only `2.9.1` keys (about 3,480), so the estimates for the `2.12.0` classes
  are already orphaned and fall back to defaults.
- **The record.** `Installation.source` is a free object; `status` prints it.

## 3. Design

One principle per decision. Decisions marked **(user)** are listed again in
section 7 for the user to confirm or change; the plan proceeds on the
recommendation.

### 3.1 Trust model (D-Trust)

**Before.** To make an operator install a bad or mistaken release, an attacker
had to publish the assets **and** get a pin merged into this repository and a
Manager released and upgraded to. The pin is a digest in the wheel: a
re-published or altered asset fails even when `SHA256SUMS` agrees with it. A
transcription mistake in a pin fails closed at the next install.

**After.** Every party who can introduce a release changes. (1) The GitHub
publisher: publishing a release in `RodrigoFAbreu/workflow` reaches every
operator who runs a bare `update` or `bootstrap` with network access, and no
pin pull request stands in between. (2) **The release source is now a trust
root, which it was not before** (RA-L1-001). `--release-source`,
`WORKFLOW_MANAGER_RELEASE_SOURCE` (a directory or a URL template) and the
default URL used to serve bytes that had to match a pin compiled into the
wheel, so a hostile mirror could only fail an install. Now whoever controls a
mirror directory, a mirror URL or the environment variable is a publisher for
every version that is not pinned: by discovery for a directory mirror (3.7
row 3), by an explicit `--release-version` for a URL-template mirror (row 4).
(3) Whoever can write the release cache, as before, but with the source
binding below. The pins still bind the releases they name against every
source. `SHA256SUMS` and the manifest asset are
published by the same release, so they are no independent proof: they detect
corruption, a truncated or tampered transfer, a mismatched archive and a
partial re-publish, not a malicious or mistaken publisher. A mistaken release
(wrong manifest, wrong counts) is installable at once instead of after a pin
review. What stays: the extraction and manifest rules every install already
applies, and pins for every release they name. **Immutability is checked
only where the Manager can see it**: on the default source's listing path, a
release must report `immutable: true` and its absence is a failure (3.2). The
explicit `--release-version` path, the cache-hit path and every mirror cannot
express or re-check it, so for those the Manager relies on `SHA256SUMS`
alone; this is stated here, not implied.

**Why the user accepted it.** Both repositories have one owner. A pin
pull request added a review step, not an independent root of trust: the
account that can publish a release can merge the pin. Signatures would add an
independent root, but a signing key held by the same owner moves the problem
without solving it, and no scheme is in scope.

**Mitigations this milestone adds, none a new root of trust:**
- Pins stay authoritative. A discovered release whose version is pinned is
  checked against the pin, never against its own `SHA256SUMS`; a published
  `2.12.0` with different bytes is refused exactly as today.
- A release is installed only when `SHA256SUMS` lists exactly its archive and
  manifest asset with well-formed digests, both downloads match, the archive
  extracts under today's rules, the carried manifest equals the manifest
  asset byte for byte, its version is the requested one, and
  `Release.verify()` passes.
- The installation record keeps the archive digest (`source.sha256`) and adds
  `source.trust: "discovered"` and `source.from` (the source that served the
  bytes: `github:<repository>`, `dir:<path>` or `template:<url>`) for an
  unpinned release, so `status` says which trust and source applied. Older
  Managers read `Installation.source` as a free object, so the change is
  additive (said in `docs/ARCHITECTURE.md`, CP5).
- **Source binding of the cache (RA-L1-001).** A discovered cache entry records
  its trust (`discovered`) and `from` in a small `SOURCE` file next to its
  `complete` marker, written under the entry's lock with the entry. A
  discovered entry is a cache hit only when the current run names the same
  source (by default, `github:<repository>`; `--release-source` or the
  environment variable name another). Under a different source it is not
  reused, not offered, and not counted as "newest known locally" in the
  offline fallback: the run refetches from its own source or fails closed.
  Pinned entries carry no `SOURCE`: the pin binds them. `releases` and
  `status` read this one record rather than re-deriving trust.
- **`--pinned-only` (user).** A global option and the environment variable
  `WORKFLOW_MANAGER_PINNED_ONLY=1` restore today's rule: no discovery, an
  unpinned version is `ReleaseNotPublishedError(kind="unpinned")`. Recommended:
  yes; it is one boolean and gives an operator the old trust on demand.
- Stderr always names a discovered release when it is used (version, source
  and that this Manager has no pin for it); `update --dry-run` shows it before
  anything is written.

**Not detected (stated, not hidden).** A cache entry for a discovered release
is checked against its own recorded `SHA256SUMS`, so a local writer who
changes the archive and the sums together is not detected. That writer is the
same user who can already change the Manager; the old pin check was the
control against it, and it still applies to every pinned release.

### 3.2 Discovery (D-Discover)

Discovery lists candidate versions; it never trusts them.

- **Default source** (`DEFAULT_SOURCE`, the GitHub release downloads): the
  repository's releases listing, `https://api.github.com/repos/<repository>/
  releases?per_page=100` with `<repository>` from the pin file. A release
  is a candidate when it is not a draft or prerelease, its tag is
  `vMAJOR.MINOR.PATCH`, it lists the three assets, and the API reports
  `immutable: true`; **absence of the field is a failure** (the candidate is
  skipped like any other failing candidate, below). CP1 checks the field's real
  name and presence once against the live API and records that in
  `docs/ACTIVE_MILESTONE.md`; if the live API does not report it, the plan is
  amended before CP1 proceeds. A test uses a recorded response. One request, a timeout of its own
  (`DISCOVERY_TIMEOUT_SECONDS = 8` per request), the same https/redirect
  rules as asset fetches, a response size cap. A listing of exactly 100
  releases may be truncated (one page is read): it is usable for choosing, but
  its catalog is **incomplete** for the report (3.4, RA-E2).
- **Total deadline** (RA-E-O2). All the metadata requests of one command's
  choosing walk (the listing, and every candidate's `SHA256SUMS` and manifest
  request, headers and body reads included) share one deadline,
  `DISCOVERY_DEADLINE_SECONDS = 20`; each request's timeout is the smaller of
  8 seconds and what remains. When the deadline passes, the walk ends as an
  offline failure: one stderr line and the newest local release. The report's
  crossed-version reads (3.4) have a deadline of their own, the same size. The
  archive fetch keeps its existing 60-second asset timeout; it is not part of
  these deadlines.
- **Directory mirror** (`WORKFLOW_MANAGER_RELEASE_SOURCE=<dir>`): every
  `<dir>/<version>/` that holds the three assets.
- **URL-template mirror** (`.../{version}/`): has no listing, so no
  discovery. Explicit `--release-version V` still fetches `V` by template.
- **Where discovery runs.** Only where the Manager *chooses* a release with no
  version given: `bootstrap`, `update`, `doctor`, `update --dry-run` and
  `releases` (which prints a "published" column). `status` and `verify` never
  discover. An explicit `--release-version V` of an unpinned `V` does no
  listing *to choose*: cache first, then a direct fetch. The compatibility
  report's crossed-version catalog is a separate read (3.4, RA-E2) and does
  list when the range needs it, for an explicit version too.
- **Offline (R5).** Discovery never raises on the choosing path. Any failure
  (DNS, timeout, HTTP error, malformed listing) is one stderr line
  (`could not look for newer releases: REASON; using X`) and the choice falls
  back to the newest release known locally: the pins plus cache entries that
  carry a `complete` marker and, for a discovered entry, a `SOURCE` equal to
  the current source (3.1). **A failure while walking one candidate**
  (RA-L1-005b: the listing worked but the candidate's manifest asset or
  `SHA256SUMS` cannot be fetched or fails its checks: a rate-limited or
  blocked asset host, a proxy, a release still uploading, a failed `immutable`
  check) skips that candidate with the same one stderr line naming it, and the
  walk goes on to the next, ending at the newest local release. A primed cache
  with such a network therefore installs the newest pin, as today.
- **Archive availability is part of the fallback on the installing commands**
  (RA-E3). The walk above is metadata-only, so it can choose a candidate whose
  archive cannot be fetched (a proxy that serves the small assets and blocks
  the archive, a release still uploading). `update` and `bootstrap` therefore
  run the choice as a loop *outside* planning: for each candidate, newest
  first, `plan_destinations` runs on that candidate's cache leaves (so the
  containment checks are redone whenever the chosen version changes), then
  `ensure` fetches and verifies it under today's rules. An **availability**
  failure of the archive (unreachable, timeout, HTTP error, size cap, a partial
  body) skips the candidate with one stderr line naming it and the cause, and
  the loop continues down to the newest local release. An **integrity**
  failure (the archive's digest differs from `SHA256SUMS`, extraction or
  manifest-shape rules) is not skipped: it refuses with today's
  `ReleaseIntegrityError`, because masking a tampered archive by installing an
  older release hides the event. An explicit `--release-version V` never falls
  back. **`doctor` and `update --dry-run` run the same loop** (RA-E5): they
  acquire the chosen candidate's package into the release cache and verify it
  exactly as an install does, as they do today (`update --help`: a dry run
  writes the release cache and a temporary snapshot outside the repository,
  never the repository). So the plan they print is complete (`plan_update`
  reads the payload and template contents, including the `.gitignore` and
  `CLAUDE.md` merge fragments, which the manifest does not carry), and an
  archive that cannot be fetched or verified makes them skip, fall back or
  refuse exactly as the real `update` would, the floor included. Only
  `releases`, which plans nothing, fetches no archive.
- **In-memory, size-capped walk, finished before planning** (RA-L1-005a). The
  walk's reads (the listing, each candidate's `SHA256SUMS` and manifest asset)
  are held in memory, each with a byte cap, and write nothing to disk.
  Discovery and the walk finish before `plan_destinations`, in
  `_readonly_destinations` as in `update` and `bootstrap`, so the containment
  checks run on the cache leaves of the version actually chosen. `doctor` and
  `update --dry-run` therefore write nothing to the repository (the walk
  writes nothing at all; the package acquisition above writes only the
  release cache) and still check the chosen version's leaves. A primed cache therefore behaves exactly as it
  does today with the network down. The total deadline above keeps a stalled network
  from hanging `update`.
- **Which release is "newest" (user).** The newest version among pins, local
  cache entries and discovered candidates that is *compatible* with this
  Manager (3.4). Candidates are walked newest first; for an unpinned candidate
  the manifest asset is fetched and checked against `SHA256SUMS` (a small
  download) to read `min_manager_version`. Recommended: bare `update` and
  `bootstrap` default to it. The alternative (default stays the newest pin
  unless `--release-version` or `--latest` is given) keeps today's behavior and
  defeats the purpose.
- **A bare `update` never downgrades** (RA-L3-002). The installed release is a
  **floor** on every rule of the choosing path: the offline fallback ("newest
  release known locally"), the walk's per-candidate skips, the archive loop of
  RA-E3 and the `min_manager_version` skip. No candidate older than the
  installed release is ever chosen; the installed release itself is allowed
  (the existing "already current" handling). When the newest usable candidate
  is older than the installed release, bare `update` stops, installs nothing,
  writes nothing, and exits 1 with new `ReleaseFloorError(InstallError)` (an
  `advice` row): `error: no usable release at or above the installed Workflow
  X: REASON` with REASON one of "could not look for newer releases (offline)",
  "the archive of Y could not be fetched" or "Y needs workflow-manager Z or
  newer; this is W", and `next:` naming the matching step (retry with the
  network, `--release-source`, or upgrade the Manager). `update --dry-run`
  reports the same message and exits 1 (the real update would be refused).
  `bootstrap` has no installed release, so it has no floor. Only an explicit
  `--release-version` downgrades, as today, through the `downgrade` finding.
  The floor reads the installed version from the record; a record that does not
  give one parseable version has no floor and the run notes that it was not
  applied.

### 3.3 Pins and discovered releases coexist (D-Coexist)

`ReleaseCache._pin(version)` becomes `_trust(version)`, returning a `Pin` plus
`"pinned"` or `"discovered"`:

- pinned: the shipped pin, as today (every existing code path and test);
- unpinned and discovery allowed: a `Pin` **derived** from `SHA256SUMS`
  (archive name from `archive_name(version)`, the archive digest, the manifest
  asset's digest). On a fetch the sums come from the download; on a cache hit
  they come from the entry's own copy of `SHA256SUMS`.

`_is_hit`, `_fetch`, `ensure` and `resolve` (snapshot taken and checked under
the entry's lock) are otherwise unchanged, so the cache layout, the lock, the
private snapshot and "nothing installed is read from a shared path" hold for
discovered releases too. `local_release` keeps treating an unpinned
`--release-dir` as local and unpublished. The pin file's schema and contents
do not change.

### 3.4 Release metadata (D-Metadata)

The release's `manifest.json` gains one optional top-level key, `manager`. The
manifest is already covered by every digest, so the block is covered too. The
normative contract is below and is published as `docs/release-metadata.md`
(CP5) for the `workflow` repository to implement.

```json
"manager": {
  "schema_version": 1,
  "min_manager_version": "1.13.0",
  "downgrade_boundary": {
    "posture": "text; empty string when a downgrade loses nothing",
    "undetectable": "text or null",
    "signals": [
      {"name": "kebab-case", "label": "text",
       "detect": {"kind": "state-key", "key": "gate_evidence"}}
    ]
  },
  "new_work_only": ["text", "..."],
  "gate_default_change": "text; empty string for none",
  "conformance": {
    "suites": {"workflow_state_test.py": 1115},
    "portability_exceptions": [
      {"suite": "x_test.py", "test": "Class.test_name", "requires": "path or null",
       "reason": "text", "defect": "path or null"}
    ]
  }
}
```

- **Top-level keys optional**, each independently. A missing key means "no
  data for this item", resolved as below. **Nested objects are all-or-nothing
  on their required fields** (RA-E-O1): `conformance`, when present, needs both
  `suites` (a mapping from a suite file name to a non-negative integer) and
  `portability_exceptions` (a list), so `conformance: {}` or either subkey
  alone is a `manifest-shape` refusal, not a partial default; the built-in
  fallback applies only when the whole `conformance` block is absent.
  `downgrade_boundary`, when present, needs `posture` (a string); `undetectable`
  defaults to `null` and `signals` to `[]`. Each signal needs `name`, `label`
  and `detect`. Each portability exception needs `suite`, `test` and `reason`
  (strings); `requires` and `defect` default to `null`.
- **Detector vocabulary, closed, version 1:** `state-key` (`key`: the key
  appears anywhere in `WORKFLOW_STATE.json`), `state-value` (`key`, `value`),
  `item-governing` (`value`), `item-phase` (`phases`: list) and `item-field`
  (`key`, `value`). `key` is a non-empty string; `value` is a JSON scalar (string,
  integer, boolean or null) compared by equality **after parsing, type-aware**
  (`true` is not `1`, `"1"` is not `1`); `phases` is a non-empty list of
  strings; `item-governing`'s `value` is a string. The five code-only detectors of the built-in data
  (activation, plan-inputs directories, amendment witnesses, retirement
  trailer, letter-suffixed amendment) stay built-in for the releases that use
  them. A release that needs a detector the vocabulary lacks declares
  `min_manager_version` of a Manager that adds it, or states the condition in
  `undetectable`. **Other version-coded logic stays in the Manager**
  (RA-L1-010): `RETIRED_DEFAULT_FROM`, the `2.6.0` worktree finding and
  `gate_modes(governing)` are release knowledge outside the three tables and
  outside the block. A Workflow release that changes any of them needs a
  Manager release, and `min_manager_version` is how it says so.
- **Resolution (per version `V`).** `V` has built-in data (every release up to
  2.12.0): the built-in data, always; a `manager` block in such a manifest is
  ignored with a note. `V` has none: the block's value for each item, and for
  an item the block lacks, the neutral value (`Boundary("")`, `()`, `""`)
  plus one **`incomplete-inspection` warning** (RA-E4; the one wording, replacing
  the earlier "note"/"warning" mix), titled "Workflow V carries no
  compatibility data": "Workflow V was published after this Manager and its
  manifest carries no `manager` block (or lacks this item); its downgrade
  guarantees and notes cannot be assessed". Its step reads "read the release
  notes at PAGE, then decide; `update` itself is not refused". A missing
  compatibility assessment is therefore never a success: the report's
  `inspection_complete` is false, but the finding describes **the release's
  metadata, not the repository's data**, so it stays out of `writes_withheld`
  (RA-L3-001; see "Which predicate each finding feeds" below), `doctor` exits 1
  (`doctor_exit_code`: a warning), and the text says "not assessed", never
  "nothing found". `update` and `bootstrap` still install the release
  (installation is preserved ahead of the Workflow follow-up); `update
  --dry-run` prints the same warning and keeps its own exit rule (0 when the
  real update would not be refused).
- **Fail closed.** A `manager` block of the wrong shape, an unknown detector
  kind, a `schema_version` other than 1, or a version string that is not
  `\d+(\.\d+)*` refuses *that release* (`ReleaseIntegrityError`,
  `kind="manifest-shape"`) when it is chosen to install or report on. An
  unknown `schema_version` is reported as needing a newer Manager.
- **Report ranges** (RA-L1-004). The two directions read different ranges:
  an update crosses releases in (installed, target]; a **downgrade reads
  every release in (target, installed], the installed one included**
  (`_base_findings` reads `DOWNGRADE_BOUNDARIES[v]` for `target < v <=
  installed`). Built-in versions come from the tables. For every unpinned
  version in the range, the installed one among them, the report reads its
  `manager` block, in this order: the cache entry's manifest (a cache hit for
  that source); else a manifest-asset fetch verified against `SHA256SUMS`
  (in memory, size-capped, one small download per version, through the same
  source). If neither works (offline), or the manifest is read but carries no block,
  the crossed version gets the `incomplete-inspection` warning above, naming
  the version and the cause (RA-E4): not a silent gap, and a downgrade from an
  unpinned installed release to a pinned one is never reported as clean on
  missing data. (`not-verified`, a note, stays only for "the installed release
  could not be compared with its package", a different question.)
- **The crossed-version catalog and its completeness** (RA-E2). Resolving one
  manifest cannot show that no intermediate release was omitted, so the report
  first builds the list of versions in the range, independently of how the
  target was chosen. Versions up to the newest one with built-in data (2.12.0)
  are known from the tables, complete by construction. When the range reaches
  above it (`max(installed, target) > 2.12.0`), the catalog of the higher part
  is the union of the pins, the cache entries bound to this source, and the
  source's listing: the default source's releases listing (a separate read,
  also for an explicit `--release-version`, under the report deadline) or a
  directory mirror's directories. A catalog is **complete** only when the
  listing was read in full (a directory mirror; the GitHub listing with fewer
  than 100 entries). It is **incomplete** for a URL-template mirror (no
  listing), an unreachable or timed-out source, an unreadable listing and a
  possibly truncated one. An incomplete catalog adds one
  `incomplete-inspection` warning, "the releases between X and Y could not be
  enumerated; a release in between may carry a new-work-only restriction or a
  downgrade posture", with the step to name the missing source, or a
  mirror that lists. So an explicit update from 2.12.0 to 2.14.0 with an
  uncached 2.13.0 reports 2.13.0 from the listing when the source lists, and
  an incomplete-coverage warning when it cannot.
  **Membership** (RA-L3 optional): a catalog member is every listed entry with
  a `vMAJOR.MINOR.PATCH` tag that is not a draft and not a prerelease, whether
  or not the choosing walk could use it (no `immutable: true`, assets missing,
  unreadable manifest). A member the walk cannot use is still in the range, and
  its crossing gets the unreadable-metadata warning naming the version and the
  cause ("not marked immutable", "assets missing", ...), so it never vanishes
  from the report without a warning. Drafts, prereleases and odd tags are not
  published releases and are not members; they do not make the catalog
  incomplete.
- **Which predicate each finding feeds** (RA-L3-001; `writes_withheld` is one
  predicate shared by the report, the exception advice and the Recovery
  section, so a new finding that joins it changes the advice of every
  command). The three coverage findings of this milestone (the release's
  missing `manager` block or item, a crossed version whose metadata cannot be
  read, and an incomplete catalog) are about **release metadata**, not about
  the repository. Each is `incomplete-inspection` (so `inspection_complete` is
  false and `doctor` exits 1) with a title from a new set
  `RELEASE_COVERAGE_TITLES`, which joins `PREDICATE_EXCLUDED` exactly as
  `RECORD_UNREADABLE_TITLE` is, so `writes_withheld` ignores them, `_command`
  keeps printing `workflow-manager update`, and `data_step` is not printed for
  them. Each has its own step in `advice.py`, naming the real cause (release
  notes, the missing source or a mirror that lists, a Manager that has the
  data) and saying `update` is not refused. Findings about the repository's
  data (unreadable state, missing templates, unreadable Git) keep feeding the
  predicate unchanged. A test adds a title to the set only through
  `RELEASE_COVERAGE_TITLES` (a sweep over the findings this module can emit).
- **`min_manager_version` (R3).** Compared as an integer tuple with this
  Manager's own version (`cli._installed_version()`, which returns `None` for
  a missing distribution and `0.0.0.dev0` for an editable or source install).
  A **development build** is defined as `version_text` defines it: no version,
  or `.dev` in it. A development build satisfies every `min_manager_version`
  (an integer-tuple compare would otherwise refuse every release on it). Enforced where a release is *chosen to install or
  report on*: an explicit `--release-version V` (or `bootstrap`/`update` of
  `--release-dir`) whose `min_manager_version` is newer than this Manager is a
  refusal, new `ReleaseIncompatibleError(InstallError)` (exit 1, an `advice`
  row): `error: Workflow V needs workflow-manager 1.14.0 or newer; this is
  1.13.0` / `next: upgrade the Manager (PAGE), then run the same command
  again`. Bare `update` and `bootstrap` skip incompatible candidates and
  print one note naming the newest skipped release and the Manager version to
  install; the skip never lowers the choice below the installed release (3.2,
  RA-L3-002: a skip that leaves only older candidates stops `update` with
  `ReleaseFloorError`). `status` and `verify` do not refuse (they only read); they print a
  note. Exit codes are unchanged except this class, documented in
  `docs/exit-codes.md`.
- **Why a block in the manifest, not new assets.** The release is already
  three immutable, digest-checked assets; a fourth asset would need its own
  `SHA256SUMS` line, pin shape and fetch path. The manifest is read by
  every code path already.

### 3.5 Deterministic CI (D-Lock) (user)

Principle: **what a run tests is data in the repository, never what the
network says that day.**

- **How a lock-only release reaches the tests** (RA-L1-003). Once the lock
  names a release newer than the last pin, three things must keep working
  that CP3 proves with a synthetic lock-only release: (a) `support.release()`
  and priming resolve through the composite pins (pins plus lock), so they
  accept the version; (b) a CLI-driven test that touches `NEWEST_RELEASE`
  (`test_update_path.py` bootstraps `UPGRADE_FROM` then runs a bare `update`;
  about a dozen files do doctor, dry-run, read-only and operator-ux) gets
  `support.cli_env` with discovery on and a **local mirror directory built
  from the primed cache**, with no network, because `PINNED_ONLY=1` would
  choose the newest pin and refuse the lock-only version as `kind="unpinned"`;
  (c) record assertions compare against `support.expected_source_record(V)`,
  which returns `load_pins().source_record(V)` for a pinned version and the
  discovered record (`trust: "discovered"`, `from: dir:<mirror>`) for a
  lock-only one. With an empty lock the helper is the identity, so no
  existing test changes at CP3.
- **The lock file** `tests/tested_releases.json`: `{"schema_version": 1,
  "releases": {"V": {"archive", "sha256", "manifest_sha256", "suites"?,
  "portability_exceptions"?}}}`. It lists Workflow releases published after
  the last pin, with digests; it is test data, **not shipped in the wheel and
  not consulted by the CLI**. A version never appears both in the pins and the
  lock (a test). `suites` and `portability_exceptions` are present only while
  the release's manifest lacks the `conformance` block; once the manifest
  carries it, a lock entry is digests only and the manifest wins.
- **The tested set** is pins plus lock. `support.py` derives
  `TESTED_VERSIONS`, `NEWEST_RELEASE` (its last) and `UPGRADE_FROM` (the one
  before) from it; `PINNED_VERSIONS` keeps meaning the pins (the compatibility
  tests that need "every pinned version has built-in data" use it).
  `CI_SUITES` and `expected_portability_exceptions(V)` resolve a built-in
  version from today's tables and a lock-only version from its manifest or its
  lock entry.
- **Priming** (`tests/parallel/priming.py`) primes the tested set through a
  composite `Pins` (pins plus lock entries), used only by the test tooling,
  with the same digest checks.
- **Bumping the lock** is a non-releasing `chore:` pull request made with
  `tools/release_lock.py add V`: it downloads the published assets, verifies
  them (`SHA256SUMS`, `package verify` rules), writes the digests, and fills
  `suites` from the same discovery code the inventory uses when the manifest
  lacks the block. When the manifest lacks the `conformance` block,
  `portability_exceptions` defaults to the empty list (every entry for
  `2.10.0` to `2.12.0` is empty), and the maintainer reviews that default in
  the `chore:` pull request (RA-L1-008). The frozen matrix then runs the new release on the next
  pull request. Documented in `docs/RELEASING.md`. A bot that opens that pull
  request from the nightly's result is a later optional step, not this
  milestone (the user opens pull requests today).
- **Package proofs are deterministic too** (RA-E1). `tools/release/package.py`
  runs the installed wheel's `releases`, and `check_releases_output` requires
  exactly the pinned versions; with discovery on by default, a newly published
  release would fail that check, and the release workflow runs the same tool.
  The fix is in the shared tool, so both workflows get it: every command the
  tool runs against the installed wheel gets `WORKFLOW_MANAGER_PINNED_ONLY=1`
  (and no listing request) in its environment, and a test asserts that
  `package.py` is the only caller of the wheel's entry point in
  `workflow-manager-verify.yml` and `release.yml`. `package verify` of an
  archive is unaffected (it reads no source).
- **Nightly** tests the newest published release: the `plan` job runs
  `tools/release_lock.py latest` on `schedule` events, which writes the lock
  with the newest published release added, and passes it to every other job as
  the plan job's output; each job writes it to `$RUNNER_TEMP` and sets
  `WORKFLOW_MANAGER_TESTED_RELEASES=<path>`, the override the lock loader
  honours. The plan records the lock in its selection digest, so a shard
  running against a different lock is a digest mismatch (exit 2), as for any
  selection change. Pull-request and `main` runs never set the override.
  A red nightly because of a newly published release is the signal to fix
  the Manager or to wait for a corrected Workflow release; nothing blocks a
  pull request.
- **The CI cache key** becomes the hash of the pin file **and** the lock file,
  in all four places `workflow-manager-verify.yml` uses it. The nightly's
  cache key adds the run id (its set is not in the repository) and a
  `restore-keys` prefix on the pin and lock hash, so a nightly restores the
  pinned releases already cached and downloads only the new one
  (RA-L1-007). The `latest` command is passed `GITHUB_TOKEN`, since
  unauthenticated calls from shared runner IPs hit the 60-an-hour limit.
- **The "update from the previous release" fixture (decision).** The task
  recommended moving it into the Workflow release's own CI. Decision:
  **keep the `updated` fixture here**, driven by the lock (previous tested
  release to newest tested release), because it tests the Manager's update
  machinery against real releases and the lock makes it deterministic; and
  **also** name in the follow-up (section 5) a pre-publish check in the
  `workflow` repository (bootstrap the previous release, update to the
  candidate with a released Manager) so a broken update path is caught before
  publication, not after. With one tested release the fixture is omitted, as
  today.

### 3.6 Timings (D-Timing-Key)

`tests/parallel/timings.py` keys a frozen unit by `frozen:<fixture>/<suite>::
<Class>` (no version). The loader and the history fold normalize any
`frozen:<version>/...` id to that key; the writer emits only the new form; the
committed `timings.json` is rewritten once to it (a file confined to
`timings.json` counts as no change for the evidence rules). Unit ids in plans,
selectors and records keep their version: only the timing lookup key changes.
One selection contains one frozen version, so no two ids collapse. A class
that exists in the new release but not in the history gets the existing
new-unit rule. Side effect: the `2.9.1` history starts applying to the
`2.12.0` classes again.

### 3.7 Offline, cache and mirror (D-Offline)

Summarised so the tests can be written against it:

| Situation | Today | After |
|---|---|---|
| Primed cache, network down, bare `update` | newest pin, from cache | same release, one stderr line about discovery |
| Mirror directory with only pinned releases | works | works, nothing newer discovered |
| Mirror directory with a newer release | refused (unpinned) | installed, verified by that directory's `SHA256SUMS` |
| URL-template mirror, `--release-version V` unpinned | refused | fetched and verified |
| `--pinned-only` | n/a | today's behavior exactly |
| Test run | pins primed, offline | tested set primed, offline; discovery off |
| Discovered entry, later run names another source | n/a | entry not reused or offered; refetch from the run's own source |
| Newest release's metadata reachable, its archive blocked, newest pin primed | n/a (newest pin, from cache) | falls back to the newest compatible local release, one stderr line (3.2) |
| Package proof with a newly published release | pin-only listing | unchanged: the tool runs the wheel pinned-only (3.5) |
| Installed release newer than every usable candidate (offline, archive blocked, or its `min_manager_version` too new), bare `update` | n/a (cannot arise: installed is at most the newest pin) | installs nothing, exit 1, `ReleaseFloorError` naming the installed release and the reason (3.2); `--dry-run` reports the same, exit 1 |
| Same, explicit `--release-version` older than installed | `downgrade` warning, installs | unchanged |
| Target release carries no `manager` block | n/a | `doctor` exit 1 with the missing-metadata step and the `update` command printed; no Git/data-repair step (3.4) |

**Tests never reach the network.** `cli_env` sets
`WORKFLOW_MANAGER_PINNED_ONLY=1` by default (a test that exercises discovery
overrides it with `"0"` and a mirror directory or a loopback server), the
runner exports the same variable to every unit, and a sweep test fails when a
test starts `workflow_manager` through `subprocess` with an environment that
did not come from `cli_env`. **Discovery tests never touch the operator's real cache** (RA-L1-002).
`cli_env` passes the parent's resolved cache, and a local `run_all.py` primes
`~/.cache/workflow-manager/releases`, which the operator's pipx Manager also
reads. Every test that runs with `WORKFLOW_MANAGER_PINNED_ONLY=0` or fetches an
unpinned version therefore passes its own `--release-cache` /
`WORKFLOW_MANAGER_RELEASE_CACHE` under a temporary directory, never the primed
one, and a guard enforces it: the sweep below also fails a test that sets
`PINNED_ONLY=0` without a private cache, and the runner's end-of-run check
fails when the primed cache holds a version outside the tested set or a
discovered entry. The source binding (3.1) is a second barrier, not a
replacement for this one. The recorded GitHub response used for the default
source's parser is a fixture file; the parser has no code path to the network
in its unit tests.

## 4. Tests (all hermetic)

New files are discovered automatically; counts are not pinned for host tests.

- **CP1: `tests/test_discovery.py`.** A synthetic release `next_version(
  NEWEST_RELEASE)` is built with `package.build_package` from a modified copy
  of a cached release and placed in a mirror directory with a correct
  `SHA256SUMS`. Cases: discovery lists it; bare `update` into a repository on
  the previous release installs it, and the record carries `source.trust:
  "discovered"` and the archive digest; every refusal fails closed (archive
  digest not in `SHA256SUMS`, manifest asset not in `SHA256SUMS`, malformed
  line, `SHA256SUMS` missing the archive, carried manifest differing from the
  asset, version mismatch, extra files); a pinned version re-served with other
  bytes is refused by its pin though its `SHA256SUMS` agrees; `--pinned-only`
  and the env variable refuse the unpinned release with `kind="unpinned"` and
  never list; a URL-template mirror does not discover but fetches
  `--release-version`; offline (unreachable loopback port, unreadable
  directory) falls back to the newest cached release with one stderr line and
  exit 0; the 8-second bound by a stalled loopback server with the timeout
  patched small; the GitHub listing parser on a recorded response (drafts,
  prereleases, odd tags, missing assets, `immutable: false`, truncated JSON,
  oversize body, redirect to http); the cache hit path for a discovered entry
  (tampered archive, tampered `SHA256SUMS`, missing `complete`) discards and
  refetches or fails closed; `releases` shows pinned and discovered. Added for the review
  (RA-L1-001, 002, 005): a discovered entry fetched from mirror A is neither
  reused nor chosen as "newest known locally" by a run naming the default
  source or mirror B, and the record's `source.from` names the real source; the
  listing without `immutable: true` (field absent, false) skips the candidate;
  the listing reachable and the assets unreachable (manifest or `SHA256SUMS`
  fails) falls back to the newest local release with one stderr line and exit
  0; **the listing, `SHA256SUMS` and manifest reachable and the archive
  unreachable** (a loopback server that blocks only the archive) with the
  newest pin primed: bare `update` and `bootstrap` install the newest pin,
  one stderr line naming the skipped release, exit 0, and the destinations
  were planned again for the version finally chosen (RA-E3), while an archive
  whose digest disagrees with `SHA256SUMS` refuses instead of falling back, an
  explicit `--release-version` does not fall back, and `update --dry-run` and
  `doctor` on the same server agree with `update`: same skip line, same
  chosen version (or the same refusal for the digest mismatch), exit codes
  as their commands define, and the target tree byte-identical before and
  after (RA-E5); **an uncached target whose merge fragments change**
  (RA-E5): the synthetic release's `.gitignore` and `CLAUDE.md` fragments
  differ from the installed release's and nothing of it is cached, and
  `update --dry-run` prints the complete plan, both merges included, equal to
  the changes the real `update` then applies, with the target tree unchanged
  by the dry run and the package in the private cache; the total deadline (a server that answers each
  request just inside 8 seconds, timeouts patched small) ends the walk with
  the offline line; a read-only containment test (`doctor`, `update --dry-run`) with discovery
  on checks the chosen version's cache leaves and writes nothing to the repository; a guard test
  that a discovery test without a private cache fails. **The floor**
  (RA-L3-002): a repository whose record names a discovered release newer than
  everything usable, bare `update` and `update --dry-run` with (a) the network
  down and the cache holding only older entries, and (b) the archive blocked:
  nothing installed, nothing written, exit 1, `ReleaseFloorError` text naming
  the installed release and the reason; the same repository with the installed
  release itself reachable is a normal no-op; an explicit older
  `--release-version` still downgrades with the `downgrade` finding;
  `bootstrap` has no floor. The existing
  `kind="unpinned"` tests run with `--pinned-only`.
- **CP1: sweep.** The subprocess-environment sweep of 3.7, with a negative
  case proving it detects a violation.
- **CP2: `tests/test_release_metadata.py`.** Valid and invalid `manager`
  blocks (each shape error, an unknown detector kind, a wrong
  `schema_version`, a bad version string); built-in data wins for every
  built-in version even when a block is present; an unpinned release with a
  block drives the report (a `state-key` signal fires on a repository that
  carries the key; a posture crossing is reported; `new_work_only` and the
  gate-default change appear); with no block, the `incomplete-inspection` warning;
  **partial objects** (`conformance: {}`, one subkey, a signal without `detect`,
  a `state-value` with a list value, `true` against `1`) refuse or compare as
  specified; **missing compatibility data fails closed** (RA-E4): a release with
  no block, a crossed version with no block, and a crossed version whose
  metadata cannot be read each give an `incomplete-inspection` warning,
  `inspection_complete` false, `doctor` exit 1 and no "nothing found" wording,
  while `update` still installs; **crossed-version coverage** (RA-E2): an
  explicit update from the last built-in version to two versions later with an
  uncached, unpinned intermediate release carrying a new-work-only restriction
  is reported from a directory mirror and from a recorded GitHub listing, and
  reported as incomplete coverage for a URL-template mirror, offline and a
  100-entry listing; **printed advice** (RA-L3-001): for a repository whose target release
  carries no `manager` block, `doctor` and one refusal (drift `--force`) name
  the missing release metadata and print `workflow-manager update`, never the
  Git/data-repair step, and the sweep over `RELEASE_COVERAGE_TITLES`; a
  repository whose own data is unreadable still withholds the writes;
  catalog membership (RA-L3 optional): a listed release without `immutable:
  true`, with missing assets or unreadable in the range gets the warning naming
  the version, while a draft, prerelease or odd tag does not; the floor under
  `min_manager_version` (RA-L3-002): installed 2.14.0 needing a newer Manager
  than this one, bare `update` and `--dry-run` stop with `ReleaseFloorError`
  naming the Manager to install and install nothing, not 2.13.0;
  `min_manager_version` refusal for an explicit version, the skip-and-note for
  bare `update`, no refusal for `status`/`verify`, a development build
  passing; a range crossing an unpinned intermediate version, online and
  offline; **a downgrade from an installed unpinned release with a posture and
  signals to a pinned release** reports the crossing from the installed
  release's manifest (cache, then fetch), and offline reports the `incomplete-inspection` warning naming the version
  (RA-L1-004, RA-E4); a development build
  (`0.0.0.dev0`, `None`) passes `min_manager_version`; `docs/exit-codes.md` row; the `advice` row for
  `ReleaseIncompatibleError` quoted by the docs test.
- **CP3: `tests/test_tested_releases.py`.** Lock schema and shape; a version
  not in both pins and lock; the tested set, `NEWEST_RELEASE` and
  `UPGRADE_FROM` derived with a synthetic lock; `CI_SUITES` and expected
  exceptions for a lock-only version from the lock entry and from the manifest
  (the manifest wins); the override environment variable; priming through the
  composite pins against a mirror directory; `tools/release_lock.py add`,
  `check` and `latest` against a mirror directory (including a digest
  mismatch refusal); the workflow file's cache keys, nightly wiring and
  absence of the override on pull-request events (parsed from the YAML, as
  `test_release_workflows.py` does). `TestPinnedVersionsCarryTheirRecords`
  is generalised to the tested set. **Package verification** (RA-E1): with an
  additional discoverable release in a mirror directory and the environment
  naming it, `package.py`'s wheel check (`releases` output equal to the pins)
  still passes and issues no discovery request (a loopback source records
  none), and the two workflow files call the wheel's entry point only through
  `package.py`. **An end-to-end run against a synthetic
  lock-only release** (RA-L1-003): the `updated` fixture's bootstrap of the
  previous release followed by a bare `update` through the CLI, and
  `support.release()`, against a release in the lock and not in the pins,
  with the mirror-directory `cli_env` and the discovered-record assertion
  helper of 3.5.
- **CP4: timings tests** in `tests/test_parallel_runner.py`'s timing
  classes: the key function, old-form keys load as new, two forms of one
  unit fold into one estimate, the writer emits only the new form, the
  committed file loads with no warning and has no versioned key.
- **CP5: `tests/test_docs.py`** (and `test_operator_ux_docs.py`): the new and
  changed pages are in the index, link-checked, `RELEASING.md` has no
  "adding a pin" procedure, `CLAUDE.md` matches, `docs/release-metadata.md`
  carries the schema keys the code reads (a test compares its key list with
  the reader's).
- **The gate:** `python3 tests/run_all.py` at every checkpoint's end, with
  `--select` for what each checkpoint touched while developing.

## 5. The Workflow-side follow-up (R8)

Not done here, and this milestone does not wait for it. It is named so the
`workflow` repository can plan it as its own milestone. Published as
`docs/release-metadata.md` (CP5) and sent to the Workflow lane by the
orchestrator.

1. **Fields.** The build writes the `manager` block of section 3.4 into
   `manifest.json`: `schema_version` (1), `min_manager_version` (string
   `X.Y.Z`; the lowest Manager that reads this release correctly),
   `downgrade_boundary` (`posture` string, `undetectable` string or null,
   `signals` list of `{name, label, detect}` with `detect` from the closed
   vocabulary), `new_work_only` (list of strings), `gate_default_change`
   (string, empty for none), `conformance.suites` (suite file to test count)
   and `conformance.portability_exceptions` (list of `{suite, test,
   requires, reason, defect}`).
2. **Who fills them.** The release author writes
   `release/MANAGER_METADATA.json` in the milestone's pull request (posture,
   notes, gate change, exceptions, `min_manager_version`). The build copies it
   into the manifest and **computes** `conformance.suites` by test discovery
   (never hand-written), and refuses a hand-written value that disagrees.
3. **How its CI checks them.** (a) Schema validation against the contract in
   `docs/release-metadata.md`, including the detector vocabulary; (b) the
   counts equal discovery; (c) `min_manager_version` is not newer than the
   latest released Manager tag; (d) `posture` is non-empty when the release
   adds a persisted key, phase or status (the check the author's own
   `CLAUDE.md`-style downgrade paragraph used to be); (e) the manifest of a
   release up to 2.12.0 is never given a block (immutability); (f) a
   pre-publish fixture: bootstrap the previous published release, update to
   the candidate with the released Manager named by `min_manager_version`,
   and run the candidate's frozen suites in the result.
4. **Order.** The Manager reads the block when present and falls back
   otherwise, so the Workflow release may land before or after this
   milestone's release. Until it lands, a new Workflow release installs with
   an `incomplete-inspection` warning (doctor exit 1) and the maintainer's `chore:` lock bump supplies
   the suite counts.

## 6. Checkpoints

The table is generated from the registry.

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Discovery, trust and the cache: Discovery over directory, GitHub-listing and template sources, derived pins for unpinned releases, --pinned-only, offline-safe choosing path, source.trust in the record, hermetic test default | - | 4 | 1 |
| CP2 | Release metadata: the manifest manager block, validated reader, built-in fallback for releases up to 2.12.0, compatibility resolver, incomplete-inspection findings for missing data and crossed-version coverage, min_manager_version refusal and skip | CP1 | 4 | 1 |
| CP3 | Deterministic CI: tests/tested_releases.json lock, tested set in support/priming/matrix, tools/release_lock.py, nightly on the newest published release, cache key, deterministic package proof | CP1, CP2 | 4 | 1 |
| CP4 | Version-free timing keys: timings.py normalisation, committed timings.json rewritten once | - | 2 | 1 |
| CP5 | Documentation, roadmap item 8 and the Workflow-side contract (docs/release-metadata.md): RELEASING, ARCHITECTURE, CLAUDE.md, operator pages | CP1, CP2, CP3, CP4 | 3 | 1 |

<!-- CP1 -->
### CP1. Discovery, trust and the cache (R1, R5)

Files: `src/workflow_manager/source.py` (a `Discovery` class over the three
source kinds; `_trust`; derived pins; `PINNED_ONLY_ENV`; the GitHub listing
parser), `src/workflow_manager/cli.py` (`--pinned-only`; the choosing path
`_default_version` becomes `_choose_release` and never raises on discovery;
`releases` shows discovered; the one-line notes), `src/workflow_manager/
install.py` or `source.py` (`source.trust` in the record), `src/
workflow_manager/advice.py` (rows for the new notes and the `ReleaseFloorError` row; the floor of
3.2 in the choosing path),
`docs/exit-codes.md` (the `ReleaseFloorError` row), `tests/support.py` (`cli_env` default and the private-cache rule), `tests/parallel/priming.py` (export),
the cache's `SOURCE` file and source-bound hits (`source.py`),
`tests/test_discovery.py`, the sweep test, and the existing `unpinned` tests
(moved under `--pinned-only`). The install loop of 3.2 (`cli.py`: plan, ensure, archive-availability
fallback, total deadline), shared by `doctor` and `update --dry-run` (RA-E5). Checks the live API once for the `immutable`
field and records the result in `docs/ACTIVE_MILESTONE.md`.
<!-- /CP1 -->

<!-- CP2 -->
### CP2. Release metadata and `min_manager_version` (R2, R3)

Files: `src/workflow_manager/release.py` (`Release.manager`: a parsed,
validated block or `None`), `src/workflow_manager/compatibility.py` (the three
tables stay as the built-in data; a resolver `release_data(version, release)`
replaces direct table reads in `build_findings`, the crossing and
new-work-only helpers; the declarative detector builder; the
`incomplete-inspection` findings for missing data and crossed-version
coverage, `RELEASE_COVERAGE_TITLES` and its place in `PREDICATE_EXCLUDED`, and
the catalog of 3.4), `src/workflow_manager/cli.py` and `advice.py`
(`ReleaseIncompatibleError`, the skip-and-note, the floor, the coverage steps,
the `status`/`verify` note),
`docs/exit-codes.md`, `tests/test_release_metadata.py`, and the updates to
`tests/test_compatibility.py` for the resolver.
<!-- /CP2 -->

<!-- CP3 -->
### CP3. Deterministic CI: the lock file and the nightly (R4, R5)

Files: `tests/tested_releases.json` (empty `releases` object, since every
release up to 2.12.0 is pinned), `tests/support.py` (`TESTED_VERSIONS`,
`NEWEST_RELEASE`, `UPGRADE_FROM`, `CI_SUITES` and exceptions resolved per
source, the override variable), `tests/parallel/priming.py` and `matrix.py`
(composite pins, tested set), `tests/parallel/inventory.py` (a counting helper
the tool reuses; the lock in the selection digest), `tools/release_lock.py`
(`add`, `check`, `latest`), `.github/workflows/workflow-manager-verify.yml`
(cache key, nightly lock output), `tests/test_conformance_suite.py` (the
records test generalised), `tools/release/package.py` (pinned-only wheel
commands, RA-E1), `.github/workflows/release.yml` (checked, no change expected),
`tests/test_tested_releases.py`. With an empty lock
the tested set equals the pins, so the matrix does not change at this
checkpoint.
<!-- /CP3 -->

<!-- CP4 -->
### CP4. Version-free timing keys (R6)

Files: `tests/parallel/timings.py` (the key function, loader and fold
normalisation, the writer), `tests/parallel/timings.json` (rewritten once),
the timing tests in `tests/test_parallel_runner.py`.
<!-- /CP4 -->

<!-- CP5 -->
### CP5. Documentation, roadmap and the Workflow-side contract (R7, R8)

Files: `docs/RELEASING.md` ("Workflow packages: adding a pin" becomes "A new
Workflow release": nothing to do; the lock `chore:`; when a Manager release
is still needed, namely a change to the package format, the detector
vocabulary, the CLI, the metadata schema, or `RETIRED_DEFAULT_FROM`, the
`2.6.0` worktree finding or `gate_modes(governing)`), `docs/ARCHITECTURE.md` (the additive `source.trust`/`source.from` record fields; the cache's `SOURCE` file; Packages,
pins, source and cache; Which release a command means; Update planning;
Verification execution's tested releases, timings and CI; "What a new Workflow
release needs"), `CLAUDE.md` ("Adding a Workflow release" and the immutable
hard rule: a pin is still never changed, a release needs no pin; the downgrade
posture paragraphs become the built-in record for releases up to 2.12.0, later
ones carry theirs in the manifest), `docs/update.md` and `docs/install.md`
(what an operator does when a release is published: nothing, or
`workflow-manager update`; `--pinned-only`; the offline note; that `status`
and `verify` of a repository on a discovered release are refused as `unpinned`
under `--pinned-only` and `doctor` adds `not-verified`, RA-L1-009; `doctor`'s
"latest" wording names whether the latest release is pinned or discovered), `docs/exit-codes.md`,
`docs/common-problems.md`, `docs/README.md` (index), the new
`docs/release-metadata.md` (the section 3.4 contract and the section 5
follow-up), `docs/ROADMAP.md` (item 8 in the table and its section, Done at
acceptance), `docs/ACTIVE_MILESTONE.md`.
<!-- /CP5 -->

## 7. Open decisions

None of these is a row of `docs/TECHNICAL_DECISIONS.md` (this repository has no
such file). The plan proceeds on each recommendation; the user may change any
at plan approval.

| Id | Decision | Recommendation (in this plan) | Alternative |
|---|---|---|---|
| U-1 | Trust: unpinned releases verified by `SHA256SUMS` and manifest digest only; the release source becomes a trust root for unpinned versions, bound into the cache (3.1) | Accept; pins win for the releases they name | Keep pins for every release (status quo) |
| U-2 | `--pinned-only` / `WORKFLOW_MANAGER_PINNED_ONLY=1` (3.1) | Add it | No switch |
| U-3 | Bare `update`/`bootstrap` default to the newest compatible discovered release (3.2) | Yes | Newest pin unless `--latest`/`--release-version` |
| U-4 | CI determinism by lock file, nightly on the newest release (3.5) | Lock file bumped by a `chore:` pull request; a bot later | A bot now; or the nightly alone |
| U-5 | The `updated` fixture stays here (3.5) | Keep, plus a pre-publish check in the `workflow` repository | Move it entirely |
| U-6 | Discovery through the GitHub releases API (3.2) | Yes: one request, bounded, never fatal | A `latest-release` redirect (only the newest, no skipping of an incompatible one) |

## 8. Risks

- **The live API's shape.** The `immutable` field and rate limits (60 requests
  an hour unauthenticated) are checked once at CP1; a rate-limited run is the
  offline case, never an error.
- **Tests that assume "unpinned is refused".** They move under `--pinned-only`
  or to a mirror; CP1 lists them by running the suite, not by search.
- **A conformance sweep over the plan.** This plan lists no governing
  versions; the sweep runs before publication.
- **Stale built-in data.** Nothing adds built-in data after 2.12.0, so the
  `incomplete-inspection` warning is the visible symptom if the Workflow-side change
  is late.
- **Lock/pin overlap.** A release later pinned by hand would sit in both; a
  test fails until it is removed from the lock.

## 9. Review history

Earlier rounds' dispositions are recorded inline where each finding changed
the design (RA-L1-*, RA-L3-*, RA-E1 to RA-E4).

- **RA-E5** (external, revision 4; Important): accepted, first option.
  Revision 4's requirement that `doctor` and `update --dry-run` fetch no
  archive is removed, with its CP1 test. The read-only commands acquire and
  verify the chosen package into the release cache as they do today
  (`src/workflow_manager/cli.py` `cmd_dry_run`/`cmd_doctor` resolve a package
  and call `plan_update`; `update --help` already says a dry run writes the
  release cache), so their plan is complete and an archive that cannot be
  fetched or verified makes them fall back or refuse as `update` does (3.2).
  The replacement CP1 tests: an uncached target whose merge fragments change
  (complete plan printed, target tree unchanged) and an archive-only failure
  (dry run and update agree) (section 4). Destination containment and the
  RA-E1 to RA-E4 fixes are unchanged.
