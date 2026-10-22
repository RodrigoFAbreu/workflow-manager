# Workflow Manager: Review Follow-up Clean-up, #39 to #52 (Revision 10)

`work_item_id: manager-review-followups` -- `governing_workflow_version: "2.2"`

**Deliverable:** the fourteen Optional findings of the release-agnostic Manager
(PR #38), issues #39 to #52, each with one disposition (section 1): clearer
floor and version refusals, specified `doctor` edges, stricter release metadata
and checksum tests, and test and CI hygiene. #50 (`_http_read`) is a follow-up
for its own later milestone, not part of this one.

**Work item type:** `process`. **Base commit:** `3c7ad52` (tip of `main`;
Workflow 2.18.3 installed, automatic gates, no `GATE_POLICY.json`). **Branch:**
`milestone/manager-review-followups`. **Scope source:** `docs/ROADMAP.md`
row 12 and its section 12; issues #39 to #52; the owner's go of 2026-10-22.
`src/` changes, so the pull request title is `fix: ...` (a Manager patch
release follows the merge; checked with `python3 tools/release/release.py
check-title`). No pin, version or frozen Workflow semantic changes.

## 1. Dispositions

Reading the code at `3c7ad52` showed that two findings are already satisfied;
the plan says so instead of re-doing them.

| Issue | Disposition | What |
| --- | --- | --- |
| #39 | fix | The two floor edges are specified and tested (section 2.1). |
| #40 | fix | A new floor refusal kind, `pinned-only` (section 2.1). |
| #41 | fix | `doctor`'s "Latest available" on an explicit `--release-version` run (section 2.2). |
| #42 | fix | A dedicated `not-a-version` refusal kind (section 2.3). |
| #43 | fix, tests only | `docs/release-metadata.md` already specifies partial objects ("Nested objects are all-or-nothing"), `parse_manager_block` implements it, and the table in `test_shape_errors_refuse_with_the_manifest_shape_kind` covers `conformance: {}`. The gaps are the fields no row exercises; section 2.4 adds them. |
| #44 | dropped | A `manager` block of the wrong shape keeps refusing that whole release (fail closed, `docs/release-metadata.md`, "Fail closed"). Offering an older release instead would hide a damaged publication behind a quiet downgrade; no change. |
| #45 | dropped | `ReleaseSource.inspect` already reads `SHA256SUMS` and the manifest asset and cross-checks their digests and the named version before any archive is fetched. A further pre-screen of a pinned release adds two requests on a cache-first path and changes no outcome, since the check on the installed bytes must stay. Not small enough to justify. |
| #46 | fix, tests only | `_parse_sums_text` already refuses a repeated filename ("lists X twice", `kind="digest"`), and `TestTheSumsFile` pins it for the parser. Section 2.4 pins the two callers (the derived pin and the cache entry's stored `SHA256SUMS`). |
| #47 | fix | `ReleaseFloorError`'s docstring names every kind (section 2.1). |
| #48 | fix | The CLI traversal test (section 2.5). |
| #49 | fix | The CLI `doctor` test (section 2.5). |
| #50 | follow-up | Removed from this milestone by the owner (2026-10-22); the issue stays open for its own later milestone (below). `_http_read` is unchanged. |
| #51 | fix | The overlap of a concrete and a `frozen:*` orphan key is refused (section 2.6). |
| #52 | fix | The nightly saves a cache entry only when its lock differs from the committed one (section 2.7). |

**#50 is a follow-up.** Three external review rounds each found a deeper
cancellation case in the standard-library HTTP client, and the issue itself calls
the leak harmless in the one-shot CLI, so the owner removed it from this
milestone. What those rounds learned, for the later milestone: name resolution
must be cancellable, which `getaddrinfo` in a thread is not, so it needs a
killable child process that is reaped at the deadline; socket ownership is one
rule, the worker closes what it opens and the caller only shuts down; an HTTPS
read through a proxy connects, sends `CONNECT` and only then wraps in TLS; the
TLS host identity is the origin's, never the proxy's, and wants a certificate
test of its own; and the cancellation registration must follow the response
stream through its final close, because `HTTPConnection.getresponse()` closes
the connection while the response still owns the descriptor, so a blocked body
read has to stay cancellable.

## 2. Decisions

### 2.1 The floor's edges (#39, #40, #47)

The installed release is a floor on every rule of the choosing path
(`docs/ARCHITECTURE.md`); the two edges outside bare `update` follow from it.

1. **`update --pinned-only` (or `WORKFLOW_MANAGER_PINNED_ONLY`) where the
   installed release is discovered and the newest pin is below it.** The floor
   wins: nothing is installed, nothing is written, exit 1, with a new
   `ReleaseFloorError` kind `pinned-only`. Cause: `no usable release at or
   above the installed Workflow X: --pinned-only offers only the releases this
   Manager pins, and the newest of them is P`. Next step: run the command
   again without `--pinned-only` (and with `WORKFLOW_MANAGER_PINNED_ONLY`
   unset) so the Manager may install the release it discovers. That is the one
   step: going back to an older release is unsupported once newer records exist
   (`docs/DOWNGRADE_POSTURE.md`), so the message does not offer it. It is chosen
   before `offline` and `none-at-floor` (a run that never reads the source
   cannot be offline), and after `archive` (an archive that failed to fetch is
   the more specific cause). Today it is reported as `none-at-floor` ("the
   source was read"), which is false for this run.
2. **`doctor` when nothing usable reaches the floor.** `doctor` chooses the
   release exactly as `update --dry-run` does, so the same refusal arises. It
   prints nothing on stdout, `error: could not resolve the target release: ...`
   and the refusal's `next:` line on stderr, and exits **2** ("could not check",
   as for every release it cannot resolve); it never exits 0 or 1 for a
   release it did not measure. When the installed release is itself usable (a
   pin, or a cache entry for this source), it is the candidate at the floor and
   `doctor` reports on it normally, with the offline line, whatever the source.
3. `ReleaseFloorError`'s docstring lists the kinds `offline`, `archive`,
   `manager`, `none-at-floor` and `pinned-only`, and what `installed`,
   `version` and `needs` carry for each.

Specified in `docs/ARCHITECTURE.md` (the paragraph on the floor),
`docs/exit-codes.md` (the `update` row and a `doctor` exit 2 row) and
`docs/common-problems.md` (the message). Tests in `tests/test_discovery.py`
(`TestTheFloor`) and `tests/test_doctor_cli.py`, offline against a local
mirror: pinned-only with a discovered installed release (exit 1, the cause
text, the step names `--pinned-only` and the environment variable, nothing
written); `archive` still wins over `pinned-only`; `doctor` at the floor (exit
2, empty stdout, same step); the variable form; and `advice` has a row for the
kind (the table-coverage test in `tests/test_operator_ux.py`).

### 2.2 "Latest available" on an explicit run (#41)

On an explicit `--release-version` run the line must neither hide a newer
release this run can know to be usable nor present a release as usable that it
has not shown to be. "Latest available" is the newest of three sets, none of
which costs a network request beyond the metadata pass the run already makes:

* the pins;
* the releases already known locally to this run (`ReleaseCache.known_local`:
  cache entries for this source whose stored `SHA256SUMS` derive a pin);
* the newest listed release **whose manifest this run read**: the newest
  version of `listing.versions` that is in `ReleaseMetadata.blocks`. This is
  not the overall newest listed release: when that one is unreadable or
  unassessed, a lower listed release the run did read still counts.

A release that is listed but whose manifest was not read is *not* a candidate
for the line; it is named in the suffix instead (below). A listing carries two
different facts: `listing.rejected` (asset names or immutability failed, never
a candidate) and a listed version whose manifest could not be read afterwards
(`metadata.unreadable`, `coverage.py` `except _UNREADABLE`). The first draft of
this section excluded only the first. Metadata also inspects only the range
crossed between the installed and the target release (`is_inspected`), so a
listed release above that range is *unassessed*, not unreadable.

`_compatibility_report` therefore computes `latest` *after* `gather_metadata`,
which records on `ReleaseMetadata`: `newest_listed` (the newest strict version
in `listing.versions`, or none; never from `listing.rejected`) beside the
existing `catalog_incomplete` (discovery off, listing failed, no listing,
truncated). The line's version is `max(pins, known_local, newest_read)`, where
`newest_read` is the newest version in `listing.versions` that is in `blocks`
(none if no listed release was read); `newest_listed` serves the suffix only.
When `newest_listed` is above that version, the line gains the
suffix `(X is listed but was not assessed)` if it is not in `unreadable`
(outside the inspected range), or `(X is listed but its manifest could not be
read)` if it is. The metadata pass lists only when discovery is on, the
installed and target releases differ and either is above 2.12.0
(`coverage.py` `gather_metadata`); otherwise nothing was listed. The marker
stays `[pinned]` or `[discovered, not pinned]`. The completeness suffix is
worded from those facts, on an explicit run only: none when the listing was read
and nothing newer is unassessed or unreadable;
`(the release source was not listed)` when no listing was attempted and
discovery is on; `(the release source could not be listed)` when the attempt
failed; `(the release source listing may be truncated)` when the listing was
read but `listing.complete` is false (`newest_listed` is then the newest of
what was read); `(the release source has no listing)` for a URL-template source,
whose `listing(...)` returns none: nothing failed, nothing was listed; none
under `--pinned-only` (the line shows the pins alone and the page already says
so). When both a completeness and a newer-listed suffix apply they are
joined in one parenthesis, newer-listed first. A bare run is unchanged (it
already raises "latest" to the release it chose). `build_report`'s `explicit`
flag (`target_version != latest_version`) is unchanged in code, and its
consequence is intended: an explicit `--release-version` equal to the newer
cached discovered release is the latest, so the findings' steps are the ones of
a bare run. `docs/update.md` ("Reading the report") defines Latest available as
the newest release this Manager can use; it is reworded to the pins, the
releases already cached for this source and the newest listed release whose
manifest was read, with the suffixes (`docs/update.md` is the one page that defines it).

Tests, all offline against a local mirror: an explicit older version with a
newer cached discovered release shows the discovered release as latest, with
the marker and the suffix; `--pinned-only` shows the pins alone and no suffix;
an explicit `doctor --release-version <older>` on a post-2.12.0 installation,
whose metadata pass lists a release newer than the pins and the cache know and
reads its manifest, shows that release as latest with its `[discovered, not
pinned]` marker and no "not listed" suffix; a failing listing shows the `could
not be listed` suffix; **a newest listed release with an unreadable manifest**
(`listing.versions` holds it, `rejected` is empty, `metadata.unreadable` has it)
is not the latest and the suffix names it as unreadable. Every such mirror
is built so that a directory listing still lists the release: `_list_directory`
(`src/workflow_manager/source.py`) lists a version folder only when
`SHA256SUMS`, the archive and the manifest asset all exist as files, so a
folder with a missing asset is never in `listing.versions`. The manifest asset is
therefore present and unreadable: its bytes do not match the digest its
`SHA256SUMS` line records (`kind="digest"`), or it is malformed JSON whose
digest matches; both fall in `_UNREADABLE`. And the installed version in these
tests is at or above the newest listed release (for example equal to it), because
`in_range` reads a downgrade as `(target, installed]`: below it, the newest
release is outside the range, never inspected, and gets the "not assessed"
suffix instead; **a listed release
above the inspected range** is not the latest and the suffix names it as not
assessed; and no test run makes a request beyond the listing and the range's
manifests (the mirror counts its reads).
**Mixed readable and unreadable listing** (the regression for the case where
the newest listed release hides a lower one the run did read): the three listed
releases are all above 2.12.0 (for example 2.19.0 to 2.19.2), because
`gather_metadata` skips any release with built-in data (`has_builtin_data`, 2.12.0
and earlier), so a lower one would never reach `blocks`; an installation
newer than the explicit target, a listing of three releases, the newest
unreadable (its manifest asset present but with a digest that does not match
its `SHA256SUMS` line, and the installed version equal to it so that the range
reaches it) and a lower one readable and not cached, shows the lower one as the latest with its `[discovered, not pinned]`
marker and the suffix `(X is listed but its manifest could not be read)` naming
the newest; the mirror's read count shows no request beyond the listing and the
range's manifests.
`tests/test_release_metadata.py` covers the new `ReleaseMetadata` fields
(`newest_listed`, and the newest-read selection with the same mixed listing).

### 2.3 A malformed version (#42)

A version that is not `X.Y.Z` (`v2.12.0`, `2.12`, `2.12.0-rc1`, a number, a
path) is refused with `ReleaseNotPublishedError` kind **`not-a-version`**,
wherever the source or the cache first rejects a non-strict version (the
location of an asset, the cache's trust decision, its `cached` check), before
any pin or discovery question. The cause: `release 'v2.12.0' is not a version:
a release is named X.Y.Z`. The one next step: name a release as X.Y.Z, for
example `--release-version 2.12.0` (without a leading `v`); `workflow-manager
releases` lists the names. When the version came from the target's installation record
(`.workflow-manager/installation.json`) and not from an option the operator
typed (see the per-command table below), the cause is `the installation record names 'X', which is not a version:
a release is named X.Y.Z`; it never tells the operator to change an option
they did not use, and its step never names a run the same command refuses (the
per-command steps are in the table below). The two origins are told apart by a
fact on the error, not by `context.args.release_version` (which is set on a
`doctor --release-version 2.18.3` run whose *record* is the damaged input):
`ReleaseNotPublishedError` gains a keyword `origin`, `"option"` by default (the
source and cache rejections, which only ever see a version the operator typed
or a pin lookup) and `"record"` when `cli.py`'s helper raises it. The `advice`
row reads `error.origin` and, for `"record"`, the command from
`context.args.command` (and `update --dry-run` from `args.dry_run`).

Which command resolves the record, and where the refusal is raised (checked in
the code at `3c7ad52`: only `status` and `verify` resolve the record's version
through the cache; `doctor`, `update --dry-run` and a bare `update` walk
candidates through `_choose_and_resolve(floor=_floor(args))`, and today a
non-strict record gives them a stderr note, a floor of none, the newest release
chosen, and then `compatibility.version_key`'s bare `ValueError` in the report,
exit 2 with no `next:` line; a bare `update` would install over the record):

| command | where the refusal is raised | exit | record-sourced next step |
| --- | --- | --- | --- |
| `status`, `verify` | typed `--release-version`: the cache/source rejection, through `_resolve` and `_release_for_target`, `origin` `"option"`. No option: the helper `_refuse_unparseable_record(installed)` runs first. `cmd_status`: inside its existing `try`, before `_readonly_destinations`, so the `except RELEASE_ERRORS` branch prints the record and the work in flight before the refusal, as it does for every other release error. `cmd_verify` has no `try` and no record printing: the helper is its first statement, before `_release_for_target`, and the error reaches the top-level handler like any other release error. `origin` `"record"` | 1 | repair or re-bootstrap the record, or run the same command with `--release-version X.Y.Z` (these two resolve `args.release_version or installed`, so the run is not refused) |
| `doctor` (bare or with `--release-version`) | the helper, called first inside `cmd_doctor`'s existing `try`, whatever the option: the report compares against the installed version, which must be strict | 2 (the existing "could not resolve the target release" path, plus its `next:` line) | repair or re-bootstrap the record, or fix it with `update --release-version X.Y.Z`; never `doctor --release-version`, which the helper refuses too |
| `update --dry-run` (bare or with `--release-version`) | the helper, called first in `cmd_dry_run`, before any plan is printed, whatever the option | 1 | the same as `doctor`; never `update --dry-run --release-version` |
| bare `update` | `_floor` calls the helper instead of printing its "names no parseable release" note and returning none: a bare update no longer installs the newest release over a damaged record (fail closed) | 1 | the same as `doctor` |
| `update --release-version X.Y.Z` | unchanged: the operator named the release, which is the repair route the steps above name | as today | none |

`_floor` still returns none for a target that is not managed or whose record
cannot be read at all (the command reports that itself); only a record that
reads but names a non-strict `workflow_version` (a string that is not `X.Y.Z`,
a number, a boolean) is refused. The helper builds the same
`ReleaseNotPublishedError` as the source, kind `not-a-version`, so one `advice`
row serves both origins, branching on `error.origin` and the command. The refusals exit 1 like the other release errors,
except `doctor`'s documented exit 2. Replaces
`unpinned` for these inputs only; a well-formed unknown version keeps `unpinned`.
Test: the existing non-strict table in `tests/test_discovery.py` now expects the
new kind, `tests/test_release_source.py` covers the pinned-only path, and
`tests/test_operator_ux.py` pins the cause and the step through the CLI, for
the typed option and for the record-sourced version separately; and, for the
record-sourced version, once per row of the table above, with that command's
own cause, step and exit code, including `doctor --release-version <valid>` and
`update --dry-run --release-version <valid>` on a `../escaped` record: each
reports the record as the cause (never the typed option), its step names no
run that command refuses, and its exit code is its row's (section 2.5).

### 2.4 Release metadata and checksums (#43, #46)

No behaviour change. `docs/release-metadata.md` already says what a partial
object means (a required field is required, the listed fields default); the
tests make each statement true. New rows in the refusal table of
`tests/test_release_metadata.py`: an exception without `suite` or without
`test`; a signal without `name` or without `label`; `suites` not an object;
`portability_exceptions` an object; an exception that is not an object;
`undetectable`, `requires` or `defect` of the wrong type; `posture` null;
`conformance` null. A table of the accepted partials checks the defaults
(`requires` and `defect` null, `undetectable` null, `signals` empty). Where a
row shows the code accepts something the page refuses, the code is fixed to
refuse it (fail closed) and the sentence stays; where the page is silent, one
sentence is added. For #46: a repeated filename in a release's `SHA256SUMS` is
refused by `derive_pin` (`ReleaseIntegrityError`) and, for a cache entry's
stored `SHA256SUMS`, not trusted (`_local_pin` catches the same error and returns
none, so `known_local` omits the entry and `_trust` re-derives from the source),
each with a test saying exactly that: for the entry, "not trusted and not
served", and `docs/release-metadata.md` says the file lists exactly the archive and
the manifest asset, once each.

### 2.5 Two CLI tests (#48, #49)

* #48, `tests/test_discovery.py`: an installation record whose
  `workflow_version` is `"../escaped"` is driven through `status`, `verify`,
  `doctor` and `update --dry-run` with a private cache and a local mirror. Each
  (plus `doctor --release-version <valid>` and `update --dry-run --release-version <valid>`,
  and `status`/`verify` with and without the option) exits with the refusal,
  cause, step and exit code its own row of section 2.3's
  table gives (never a traceback or a bare `ValueError`; the record is the cause,
  and no option the operator did not type is named). The exception is
  `status` and `verify` with a valid option: they do not refuse on the
  record, and the test checks their normal reporting and verification against
  the explicit release, possibly reporting a version mismatch with the
  record, not a malformed-record refusal. A bare `update` also
  leaves the target's files unchanged (nothing is installed over the record);
  and the file tree around the cache
  (its parent, including a would-be `escaped` sibling) is identical before and
  after: nothing outside the cache is created or removed.
* #49, `tests/test_doctor_cli.py`: `doctor` exits 0 on an up-to-date post-2.12.0
  installation (a discovered release with a complete `manager` block, already
  cached) when `--release-source` names an unreadable source (a missing
  directory): the installed release is the candidate at the floor, the offline
  line is on stderr, and nothing is written.

### 2.6 Overlapping orphan keys (#51)

`parse` in `tests/parallel/resources.py` refuses a concrete
`frozen:<v>/<fixture>/<suite>::<Class>` key and a `frozen:*/...` key that
expand to the same unit: `ResourcesFileError` naming both keys and the unit,
instead of letting the later one overwrite the earlier. Test in
`tests/test_parallel_runner.py`, next to the existing `orphan_sources` schema
cases: the overlap is refused with both keys named; a concrete key and a
`frozen:*` key for different units are accepted.

### 2.7 The nightly's cache entry (#52)

The nightly's cache key adds the run id, so every run saves a new entry. It
adds instead a digest of the nightly lock that is empty when the lock equals
the committed `tests/tested_releases.json` (parsed, so formatting is
irrelevant) and otherwise the first 16 hex digits of the lock's canonical
SHA-256. The rule is a script, `tools/lock_digest.py` (a function
`digest(lock_path, committed_path)` and a command line the workflow steps call),
so `tests/test_release_workflows.py` unit-tests it and the workflow only calls
it. An unchanged lock gives the pull-request key, which the `main` push run
saved (a scheduled run restores only caches saved on the default branch): an
exact hit, so nothing is saved. A new release changes the digest once, saves
once, and later nightlies hit that entry. Four steps carry the key today (`plan` at line 92, `shard` at 139, `package` at
179, `aggregate` at 222): `plan`, `shard` and `aggregate` compute the digest the
same way, in a step before the cache step, from the nightly lock file the job
already writes (`aggregate` writes the nightly lock too); `package` has no
`needs: plan`, never sees the nightly lock and primes only the committed set, so
its key is the unsuffixed base key (the hash of the two committed files), with
no digest, which keeps it from saving the committed set under the new-release
digest key and racing the `plan` job's save. `restore-keys` is unchanged. Only
`.github/workflows/workflow-manager-verify.yml` changes (it is not managed by
Workflow; `workflow-conformance.yml` is and is not touched). Test in
`tests/test_release_workflows.py`: the whole workflow file no longer uses
`github.run_id` in any cache key (all four steps); `package`'s key has no
digest; the key starts with the shared prefix (existing
test); `digest` on a lock equal to the committed one (a reformatted copy included)
yields an empty string and on another lock a stable 16-hex string.

### 2.8 Review dispositions

External round 1 (revision 5 to 6):

* EPR-001: accepted; section 2.2 separates listed from read (revised again in round 2).
* EPR-004: accepted; section 2.3's table describes `cmd_verify` separately.
* EPR-005: accepted; CP2's evidence command puts the global options first.
* EPR-002 and EPR-003 (the `_http_read` cancellation and its TLS test): accepted
  then; see "#50" below.

External round 2 (revision 6 to 7), with the local reviewer's round-6 Optionals:

* EPR-001 and MRF-L6-O1: accepted. The latest is the newest listed release whose
  manifest was read, not only the overall newest listed one, which stays for the
  suffix; the mixed readable/unreadable regression is in section 2.2, with no
  extra network call. Checked in `coverage.py`: a lower listed release inside
  the inspected range is read (`blocks`) even when a higher one is unreadable.
* EPR-002, EPR-003, EPR-006, EPR-007 and MRF-L6-O2, -O3 (resolution, the gated
  TLS test, socket ownership, proxy tunnelling): accepted then; see "#50" below.

Local round 7 (revision 7 to 8):

* MRF-L7-I1: accepted. Checked in `_list_directory` (`source.py`): a version
  folder is listed only with all three assets, and `in_range` reads a downgrade
  as `(target, installed]`. Section 2.2's unreadable-newest tests now use a
  present but unreadable manifest and an installation at or above the newest
  listed release.
* MRF-L7-I2 and MRF-L7-O1 (the caller's wait and the resolver-stall test):
  accepted then; see "#50" below.

External round 3 (revision 8 to 9), with the local reviewer's round-8 Optional:

* EPR-008 and EPR-010: resolved by the owner's removal of #50 (2026-10-22), not
  rejected on the merits. The section they criticised (response-stream
  cancellation lifetime, TLS host identity) no longer exists in this plan, so
  neither the gated body-read regression nor the certificate fixture is
  required here. Both findings are carried into the #50 paragraph of section 1
  for the later milestone.
* EPR-009: accepted. `docs/DOWNGRADE_POSTURE.md`, which section 2.1 cites, is
  classified at both stages in the artifacts file as an excluded read-only
  reference this item never edits.
* MRF-L8-O1: accepted. Checked in `coverage.py` (`gather_metadata` filters
  `has_builtin_data`, 2.12.0 and earlier): section 2.2's mixed-listing test now
  says the three listed releases are above 2.12.0.
* The verdict asks the resolver, proxy, gated TLS and mutation checks to be
  retained. They existed only for #50 and leave with it by the owner's decision;
  the section 1 paragraph records them for the later milestone. Everything else
  it asks to retain (installation and pin preservation, the stable nightly keys,
  the unchanged pull-request keys) is unchanged.

External round 4 (revision 9 to 10), with the local reviewer's round-9 Optional:

* EPR-011: accepted. `tools/release/release.py`, the pull-request title check
  that the plan's header names, was excluded only at the plan stage (by the
  tools directory prefix). The artifacts file now also excludes it at the
  implementation stage as a read-only reference this item never edits. Every
  repository path the plan names in backticks was then checked with the
  installed Workflow classifier at both stages; no other gap exists.
* EPR-012: accepted. Section 2.5 now says `status` and `verify` with a valid
  option exercise normal reporting and verification against the explicit
  release, possibly a version mismatch, not a malformed-record refusal;
  section 2.3's table is unchanged.
* MRF-L9-O1: accepted as a statement of intent, no further plan text. At
  acceptance CP4's roadmap edit removes the thirteen lines of closed issues
  (#39 to #49, #51, #52) from the "Review follow-ups" list in "Later" and
  leaves only #50's line, so the list never names a closed issue as open work.

**#50 across rounds.** Every `_http_read` finding of rounds 1 to 3 (EPR-002,
-003, -006, -007, -008, -010 and the local MRF-L6-O2, -O3, MRF-L7-I2, -O1) was
about the design of section 2.6 of revisions 5 to 8, which the owner removed
from the milestone in revision 9. Their substance is the paragraph in section 1.

## 3. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The floor's edges and the explicit-run "Latest available" | - | 3 | 1 |
| CP2 | A not-a-version refusal, partial metadata and checksum tests | CP1 | 2 | 1 |
| CP3 | The two CLI tests | CP1, CP2 | 1 | 1 |
| CP4 | Orphan-key overlap, the nightly cache entry and the roadmap | - | 2 | 1 |

<!-- CP1 -->
### CP1 -- the floor's edges and "Latest available" (#39, #40, #41, #47)

**Files:** `src/workflow_manager/cli.py`, `src/workflow_manager/advice.py`, `src/workflow_manager/source.py`, `src/workflow_manager/compatibility.py`, `docs/ARCHITECTURE.md`, `docs/exit-codes.md`, `docs/common-problems.md`, `src/workflow_manager/coverage.py`, `docs/update.md`, `tests/test_discovery.py`, `tests/test_doctor_cli.py`, `tests/test_operator_ux.py`, `tests/test_release_metadata.py`.

Sections 2.1 and 2.2. `_floor_error` gains the `pinned-only` kind (and names the
newest pin), `advice._floor` its step, `ReleaseFloorError`'s docstring every
kind; the latest comes from the pins, the locally known releases and the newest
listed release whose manifest was read, with the suffixes of section 2.2.
Evidence: the new tests failing first at `3c7ad52` where they describe a
changed behaviour (the `none-at-floor` text for `--pinned-only`; the hidden
latest) and green after; `python3 tests/run_all.py --select test_discovery.py`,
`--select test_doctor_cli.py` and `--select test_operator_ux.py` green; the
full gate `python3 tests/run_all.py` green. The reviewer's commands run
offline against a local release mirror.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- not-a-version, partial metadata, checksum tests (#42, #43, #46; #44 and #45 dropped)

**Files:** `src/workflow_manager/source.py`, `src/workflow_manager/advice.py`, `src/workflow_manager/cli.py`, `src/workflow_manager/release.py`, `docs/release-metadata.md`, `docs/common-problems.md`, `tests/test_release_metadata.py`, `tests/test_release_source.py`, `tests/test_discovery.py`, `tests/test_operator_ux.py`.

Sections 2.3 and 2.4. The `not-a-version` kind and its `advice` row; `_refuse_unparseable_record` in `cli.py`, called by `cmd_doctor`, `cmd_dry_run`, `_floor` and, with no typed option, `status` and `verify`; the `origin` keyword on `ReleaseNotPublishedError` and the per-command record-sourced steps in `advice.py`; the
metadata rows and the sums tests. A row that shows a wrong acceptance is fixed
in the parser of `src/workflow_manager/release.py` (a fail-closed tightening). Evidence: `--select test_release_metadata.py`,
`test_release_source.py`, `test_discovery.py`, `test_operator_ux.py` green; the
CLI run `workflow-manager --release-version v2.12.0 --release-source <mirror>
update <target>` (global options before the command) prints the new cause and step, exit 1; the full gate
green.
<!-- /CP2 -->

<!-- CP3 -->
### CP3 -- the two CLI tests (#48, #49)

**Files:** `tests/test_discovery.py`, `tests/test_doctor_cli.py`.

Section 2.5 (the #48 test asserts section 2.3's per-command table): the
traversal-version test through `status`, `verify`, `doctor` and `update
--dry-run`, and the unreadable-source `doctor` test. Tests only; `src/` is
unchanged here. Evidence: `--select test_discovery.py` and `--select test_doctor_cli.py` green; the full
gate green.
<!-- /CP3 -->

<!-- CP4 -->
### CP4 -- orphan-key overlap, the nightly cache entry, the roadmap (#51, #52)

**Files:** `tests/parallel/resources.py`, `tests/test_parallel_runner.py`, `.github/workflows/workflow-manager-verify.yml`, `tools/lock_digest.py`, `tests/test_release_workflows.py`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

Sections 2.6 and 2.7. `docs/ARCHITECTURE.md`'s verification section says the
nightly's key. Row 12 of `docs/ROADMAP.md` is Current at the start of this plan
and becomes Done at acceptance; its row and section 12 no longer list #50 among
the fixes, and the Later list's #50 line says the issue stays open for its own
milestone (section 1's paragraph); `docs/ACTIVE_MILESTONE.md` records the
dispositions of section 1. Evidence: `--select test_parallel_runner.py` and
`--select test_release_workflows.py` green; the workflow file parses and the
key expression is shown; the full gate green.
<!-- /CP4 -->

## 5. Risks

* `doctor` exit 2 at the floor is a stated choice (section 2.1); a reviewer who
  wants exit 1 changes one sentence and one test.
* The nightly's behaviour can only be proven by the workflow running; the
  tests pin the key expression and the digest rule, and the first nightly after
  the merge is the live check (an exact hit in its log).
* Two findings are already satisfied (#43, #46 in code); the plan adds their
  missing tests only and says so rather than re-implementing.
