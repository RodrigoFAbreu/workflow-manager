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
narrows a run for development, but a targeted run is never a gate. The
design record is
`docs/ai-workflow/WORKFLOW_MANAGER_ADAPTIVE_TEST_SHARDING_PLAN.md`.

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
  violation, a held run lock, a refused root run, or a usage error. When a
  run has both, `2` wins, and every observed failure is still listed. Each
  failure in the report carries a one-line reproduction command.

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
- nothing that affects what the suite tests or how it runs has changed
  between the two `head` commits. That means `src/`, `tools/`,
  `distribution/`, `migration/`, `scripts/`, the test modules, and the
  runner itself (`tests/run_all.py`, `tests/parallel/`, `tests/support.py`,
  `tests/frozen_runs.py`). Check with `git diff --stat <evidence head>..HEAD`;
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
directory, or its CI run URL) and its `head`. Record its `selection_digest`,
`tests_digest` and test count, taken from the report's `evidence:` line or
`results.json`'s `identity`. Also record why it is still equivalent for the
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
