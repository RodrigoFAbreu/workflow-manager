# Workflow Manager: "Latest available" Names Only Installable Releases, #85 (Revision 2)

`work_item_id: explicit-latest-floor` -- `governing_workflow_version: "2.2"`

**Deliverable:** on an explicit `--release-version` run, `doctor`'s "Latest
available" line no longer names a release whose `min_manager_version` is newer
than this Manager, and no longer names a discovered, non-pinned cached release
whose minimum it cannot read (no block in the inspected range, no cached
manifest that verifies), nor a cached release whose `manager` block this
Manager cannot parse, and the line's `(the release source has no listing)` suffix
is pinned by a test (issue #85, the two Optional findings MRF-IL1-O1 and
MRF-IL1-O2 of `manager-review-followups`).

**Work item type:** `process`. **Base commit:** `0d6ee1f` (tip of `main`;
Workflow 2.19.0 installed, automatic gates). **Branch:**
`milestone/explicit-latest-floor`. **Scope source:** `docs/ROADMAP.md` row 13
and the text of issue #85. `src/` changes, so the pull request title is
`fix: ...` (a Manager patch release follows the merge; checked with `python3
tools/release/release.py check-title`). Exit codes, options, state, release
sources, pins and Workflow releases are unchanged. One mechanism, one
checkpoint. Roadmap and active-milestone bookkeeping is not a deliverable of
this plan (section 2, EPR-003).

## 1. The defect

`cli._compatibility_report` builds the explicit run's latest from
`versions` (the pins), `cache.known_local()` and the default version, and
`compatibility.explicit_latest` adds `metadata.newest_read`. None of these is
checked against `min_manager_version`. The bare-update path does check it
(`cli._needs_newer_manager` in `_resolve_compatible`), so the line can name a
release that a bare `update` would skip with "needs workflow-manager X or
newer".

Which candidates can be affected: the pins up to 2.12.0 carry built-in data
and ignore a `manager` block (`has_builtin_data`); a later pin (the Manager's
own tests patch the pins to `7.0.0`/`7.0.1`), a release that is cached for this
source, or one listed and read, can carry a minimum. The cache is
shared by Manager versions, so a cached release written by a newer Manager and
then used by an older one is the realistic case. A release in the inspected
range already has its block in `metadata.blocks`; a cached release outside the
range (newer than the target) has none, but its cached manifest is readable
with no network (`ReleaseCache.cached_manifest`).

## 2. Decision

**Filter, and say what was left out.** Filtering alone would make the line
quietly name an older release while a newer one exists; qualifying alone would
still name an uninstallable release as "Latest available". The line is
defined as the newest release this run knows this Manager can use, so the
uninstallable candidate leaves the candidates, and the existing parenthesis
(the place the line already says what it leaves out) names the newest one
dropped:

```
Latest available 7.0.1 [pinned] (this Manager pins 7.0.0 ... 7.0.1) (7.0.2 needs workflow-manager 99.0.0 or newer: upgrade the Manager (<update-the-manager page>))
```

**Decision (EPR-002): the note names the cause and the next step.** The step is
the one `_note_incompatible` and `advice._floor` already give for the same
cause, "upgrade the Manager", with the same destination,
`advice.page(*advice.PAGE_UPDATE_MANAGER)` (`update.md#update-the-manager`);
no new page. The kinds of dropped release read:

* a minimum this Manager does not meet: `<v> needs workflow-manager <m> or
  newer: upgrade the Manager (<page>)`;
* a cached `manager` block this Manager cannot use (below): for a block written
  for a newer Manager (`ReleaseIntegrityError.newer_manager`), `<v> needs a
  newer workflow-manager: upgrade the Manager (<page>)`; for a malformed one,
  `<v> has a malformed manager block: use a newer Workflow release that
  corrects it` (the step `advice._manifest_shape` gives; a published release is
  never edited).

The operator sees the installable latest, and why a newer cached or listed
release is not it. A newer listed release that was dropped is never also
reported as "listed but was not assessed".

**How a candidate is judged.** `explicit_latest(known, metadata, needs)` takes
a `needs(version)` callable returning one of: None (the candidate stays); a
`min_manager_version` string this Manager does not meet (dropped, named);
`NEWER_BLOCK` or `MALFORMED_BLOCK` (sentinels, below: dropped, named);
`UNREADABLE` (a sentinel: dropped, not named). `cli` builds it from:

* a release with built-in data (`has_builtin_data`, the fixed table up to
  2.12.0): None (its block is ignored, as in `_needs_newer_manager`);
* else the block in `metadata.blocks`, when the run read it;
* else the block of the cache's own trusted manifest
  (`cache.cached_manifest`, parsed with `parse_manifest_manager`). **Decision
  (EPR-001): an absent block is not an unparseable one.** A manifest with no
  `manager` key gives no minimum, so the candidate stays (the line does not
  claim to validate a release). A manifest that verifies but whose block
  `parse_manifest_manager` refuses (`ReleaseIntegrityError`, `manifest-shape`)
  is a release this Manager cannot install: `_require_compatible` raises that
  same error on a bare `update`, and `known_local()` admits such an entry
  because it checks only the `complete` marker, the `SOURCE` and a parseable
  `SHA256SUMS`. Such a candidate is dropped, for every kind of candidate (a
  pin, the default version or a discovered entry alike), and named as above:
  `NEWER_BLOCK` when the error has `newer_manager` (an intact cached release
  declaring `schema_version: 2` with a `min_manager_version` of `99.0.0`, or
  any shape written for a newer Manager), `MALFORMED_BLOCK` otherwise. Only
  that error is caught, in `cli`'s `needs`; nothing is raised from the line,
  so exit codes are unchanged;
* else, when no minimum can be read because no cached manifest verifies:
  `UNREADABLE` for a **non-pinned discovered** cache entry only; None for a
  pinned version, the default version (`_default_version`, which may be an
  alias checkout that is neither built-in nor cached) and
  `metadata.newest_read`.

**Decision (PLR-ELF-1-001, PLR-ELF-2-001, PLR-ELF-3-001): trust, not built-in
data, decides what an unreadable minimum drops.** The candidates are
(`cli.py:_compatibility_report`, `explicit_latest`): the pins
(`pins.versions()`) and the default version, which the Manager itself vouches
for and which are never dropped for an unreadable minimum (only when a minimum
*is* read and not met); `cache.known_local()`, which returns every pin, cached
or not (`source.py:794`), plus the discovered entries it admits on their
`complete` marker, a matching `SOURCE` and a parseable `SHA256SUMS`
(`_local_pin`); and `metadata.newest_read`, a listed release whose block *was*
read. A listed release that was not read is never a candidate (it appears only
as "is listed but was not assessed"). The only candidates that can be
`UNREADABLE` are therefore non-pinned discovered cache entries that
`cached_manifest` refuses because the archive digest, the tree digest or
`Release.verify()` fails (`_is_hit`): a damaged cache entry. Dropping them
loses no installable release the line names today (every pin, the default
version and every read release stays, so the existing
`TestLatestAvailableOnAnExplicitRun` tests, `test_an_unlisted_run_is_named`
included, are unchanged). A damaged pinned entry is still named as before. A
dropped damaged entry is not named: its minimum is unknown, and resolving that
version re-fetches it and then applies `_require_compatible`, so a bare
`update` still decides.

The check is `manager_version_ok(minimum, _installed_version())`, the one
`_needs_newer_manager` uses, so a development build satisfies every minimum
here exactly as there. `ReleaseMetadata` gains `read_listed` (the listed
versions whose manifest was read); `newest_read` is the newest of them, so a
newest read release that needs a newer Manager no longer hides a lower
installable one.

No new option, no state, no network read: `cached_manifest` reads the local
cache only. Exit codes are unchanged (`docs/exit-codes.md`, a read-only reference).

**Decision (EPR-003): artifact classification.** `docs/exit-codes.md`,
`docs/RELEASING.md` and `tools/release/release.py` are named here only as
unchanged references (the exit codes, the `fix:` title and its `check-title`
command). The artifact declaration classifies all three at both stages:
excluded at the plan stage like the sibling items', and protected at the
implementation stage, so an edit to any of them is reviewed. `docs/ROADMAP.md`
and `docs/ACTIVE_MILESTONE.md` are not deliverables of this plan: it declares
no edit to either, so there is no documentation deliverable left outside
implementation protection (round 2 of the external review, EPR-003, accepted in
substance by removing the checkpoint that promised those edits). They stay
implementation-excluded because the workflow's own commands write them after
technical approval: `/prepare-functional-review` writes its checklist into
`docs/ACTIVE_MILESTONE.md` (`workflow_state.FUNCTIONAL_CHECKLIST_PATH`) and
`/accept-milestone` step 3 edits `docs/ROADMAP.md`
(`workflow_state._WORKFLOW_MACHINERY_PATHS`, `scripts/workflow_state.py`);
protecting either would stale the approval at the moment the machinery writes
it. The roadmap row 13 status flip and its wording are that acceptance
bookkeeping, owned by the commands, not prose this plan asks a reviewer to
approve. The accepted `manager-review-followups` item excluded the same two
files (`docs/ai-workflow/registry/manager-review-followups-artifacts.json`,
which also protects `docs/exit-codes.md` and excludes `tools/release/release.py`).
The deliverable documentation that is reviewed, `docs/update.md`, is protected.

## 3. The no-listing suffix

`test_a_template_mirror_cannot_enumerate_the_range` already runs
`--release-version <v> doctor` through a URL-template source and asserts the
catalog text. It also asserts the "Latest available" line ends with
`(the release source has no listing)`. This is a test only.

## 4. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Filter the explicit run's latest by min_manager_version; pin the no-listing suffix | - | 2 | 1 |

<!-- CP1 -->
### CP1 -- filter the explicit run's latest; pin the no-listing suffix

**Files:** `src/workflow_manager/cli.py`, `src/workflow_manager/compatibility.py`, `docs/update.md`, `tests/test_release_metadata.py`.

Section 2 and 3. `compatibility.py`: `ReleaseMetadata.read_listed`,
`newest_read` defined through it, and `explicit_latest(known, metadata, needs)`
dropping candidates `needs` rejects and adding the section 2 note (cause plus
the "upgrade the Manager (<page>)" step) for the newest one dropped above the
latest. `cli.py`: the
`needs` callable beside `_needs_newer_manager`, passed from
`_compatibility_report`. `docs/update.md`: the "Latest available" bullet says
the line never names a release whose minimum this Manager does not meet, shows
the new parenthesis with its next step, says a cached release whose `manager`
block this Manager cannot use is not named either, and that a damaged,
non-pinned cached entry (no readable minimum) is not named, while a pin or
the default version without a readable manifest always is. Tests in `tests/test_release_metadata.py`:

* a unit test of `explicit_latest` (a newest read release that needs a newer
  Manager is dropped, the lower installable one is the latest, the note names
  the dropped one with the "upgrade the Manager" step (asserting the page) and
  not "was not assessed"; `NEWER_BLOCK` and `MALFORMED_BLOCK` are dropped and
  named with their own steps; `UNREADABLE` is dropped and not named; no
  `needs` keeps today's result);
* a CLI test in `TestMinManagerVersion` (a newer Manager caches a release that
  needs it; the older Manager's `--release-version <lower> doctor` names the
  installable latest and the dropped release in the parenthesis, with the
  `update-the-manager` page; a development-build Manager still names the
  cached release);
* a CLI test of EPR-001 (an intact cached release, non-built-in, whose
  manifest declares `schema_version: 2` and `min_manager_version: "99.0.0"`,
  the newest known: `known_local()` admits it, this Manager cannot parse the
  block, so it is not the latest and the parenthesis names it with the upgrade
  step; the exit code of the same `doctor` run is the one it has without the
  entry; a second case, a cached release whose block is malformed rather than
  newer, is named with the "newer Workflow release" step; a cached release
  with no `manager` key at all stays the latest);
* a CLI test of the damaged entry (a non-pinned version, for example `7.0.3`
  cached by discovery, with an intact `SHA256SUMS` and a damaged tree, which
  would otherwise be the newest: it is
  not named as the latest, and not named in the parenthesis, so the lower
  installable release is);
* the no-listing assertion of section 3.

Evidence: the `min_manager_version` tests (the unit test, the first CLI test),
the unparseable-block test and the damaged-tree test fail first at `0d6ee1f` and are green after; the
no-listing assertion is green at `0d6ee1f` and after (it pins behaviour that
already exists, the URL-template source already reports `no-listing`); the
existing `TestLatestAvailableOnAnExplicitRun` tests, `test_an_unlisted_run_is_named`
(a patched, non-built-in pin `7.0.1` with no block and no cached manifest is
still the latest) and `test_an_unreadable_newest_release_does_not_hide_a_lower_readable_one`
included, stay green unchanged;
`python3 tests/run_all.py --select test_release_metadata.py`,
`--select test_discovery.py`, `--select test_docs.py` green; the full gate
`python3 tests/run_all.py` green, hermetic (the existing mirror fixtures, no
process left behind).
<!-- /CP1 -->

## 5. Risks

* The `needs` callable reads a cached manifest for every non-built-in
  candidate without a block. The candidates are the pins, the default version
  and the cache's entries, so the cost is a few small local reads on a `doctor`
  run.
* A cached release whose block cannot be parsed is dropped whatever its kind,
  because a bare `update` refuses it; a release with no block at all is never
  dropped (section 2).
* Only a non-pinned discovered cache entry whose minimum cannot be read
  because no cached manifest verifies is dropped silently. By construction these are cached entries `cached_manifest` refuses
  (a damaged archive or tree); no pin (cached or not, built-in or not), default
  version or listed-and-read release is dropped for an unreadable minimum
  (section 2), so no installable release the line names today disappears.
* The "needs" parenthesis is wording a script could match; the line is
  human output, and the exit codes and other lines do not change.

## 6. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
