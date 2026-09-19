# Workflow 2.5.1: Plan-Amendment Checkpoint-ID Grammar Compatibility (Revision 5)

`work_item_id: workflow-2-5-1-checkpoint-id-compatibility` -- `governing_workflow_version: "2.1"`

**Deliverable release:** Workflow `2.5.1`
**Governing workflow version:** `2.1` (this work item's own governing version)
**Base commit:** `ce0f221b39467a8dd8417c9ea8818a14ada1bed8` (`implementation-review-two-stage`'s own completion commit -- the "chore(workflow): update installed workflow to 2.5.0" commit, the current tip of `main`)
**Deliverable:** a new authored Workflow release, `2.5.1`, built as `distribution/workflow/2.5.0/` (base, **unchanged, byte-for-byte immutable**) plus `migration/overlays/2.5.1/` (this milestone's own narrow overlay), per this repository's `CLAUDE.md` "Adding an authored Workflow release" process.

## 1. Goal

`workflow-controller-generation-1`, a real downstream repository, was
successfully upgraded from Workflow `2.3.1` to `2.5.0` with its live work
item preserved. That live work item legitimately carries checkpoint ids such
as `CP4B` and `CP6B` -- an inserted-checkpoint lettering convention that
predates Workflow `2.4.0`'s plan-amendment mechanism and that nothing in
`D-Registry`'s checkpoint-registry format (`docs/ai-workflow/WORKFLOW_V2_PLAN.md`)
has ever forbidden: a registry checkpoint `id` is, and has always been, an
unconstrained string (`workflow-v2-1-core`'s own real registry uses ids like
`WF4a-i`, `WF-Activate`, `WF8a-ii` -- none of them `CP<digits>`-shaped
either). `/request-plan-amendment` against that work item now fails, before
any mutation, with `AmendmentCheckpointIdShapeError` (`IMPL2-R1`), because
`workflow-2.4.0`'s plan-amendment mechanism (`D-Plan-Amendment-4`) introduced
a narrower, purely-numeric `CP<digits>` grammar for exactly one purpose --
matching the paired `<!-- CPn -->`/`<!-- /CPn -->` anchor-comment tags a plan
document uses to mark each checkpoint's own design prose -- and then used
that narrow grammar as a **precondition on every checkpoint id the work
item's registry already contains**, not merely on ids newly introduced by an
amendment. A pre-`2.4.0` work item whose checkpoint ids were never required
to be anchor-compatible, because the anchor mechanism did not exist yet when
those ids were assigned, is refused for a shape it was never told to avoid.

This milestone widens that one grammar -- and only that one grammar -- so
that the anchor mechanism accepts the checkpoint-id shapes real Workflow
milestones have actually used, while remaining exactly as strict as before
for every id shape it was never meant to admit (`workflow-v2-1-core`'s own
`WF4a-i` included). The fix ships as a new authored release, Workflow
`2.5.1`, built from the **unmodified** `2.5.0` base plus a narrowly-scoped
overlay -- `2.5.0` itself is never touched, per this repository's own
`CLAUDE.md` ("Each `distribution/workflow/<version>/` is generated, not
edited").

## 2. Non-goals (explicit, per the user's own constraints)

- **Not a `workflow-controller` change.** This milestone never reads,
  writes, or otherwise touches `~/Workspace/workflow-controller`. Its only
  job is to make `/request-plan-amendment` and the anchor-coverage
  validation it feeds correct for the checkpoint-id shapes that repository
  (and any other pre-`2.4.0` work item) legitimately carries. Proving the
  fix works uses a synthetic, disposable-repository fixture (§3, CP1/CP2),
  never that real repository's own live state -- `CLAUDE.md`'s "Never
  migrate live work-item state" boundary applies here even though this
  milestone touches no target repository's state file directly, because the
  reasoning (someone else's live work item is not this repository's to
  read, write, or depend on for its own tests) is the same one.
- **No other known defect is bundled.** `docs/defects/v2.3.1-003-*.md` and
  `docs/defects/v2.4.0-003-*.md` are prior, unrelated, already-untracked
  residue (§2.7's disposition of both is already final, recorded in the
  `implementation-review-two-stage` milestone) and are left exactly as they
  are -- untouched, untracked, unmentioned in either declarations file
  beyond the mechanical exclusion both already need (§4).
- **No Workflow `2.6` work.** Nothing here widens the review-scalability or
  finding-taxonomy work `implementation-review-two-stage` already shipped,
  and nothing here starts new design work. This is a single, narrow
  backward-compatibility correctness fix.
- **No `USER_OVERRIDE` anywhere.** Every gate this milestone passes through
  is passed the ordinary way -- external plan review, external technical
  review, the ordinary regression suite -- never an override basis.
- **`distribution/workflow/2.5.0/` is never edited.** Not its payload, not
  its manifest, not even a byte of whitespace. The only new committed
  release tree this milestone produces is `distribution/workflow/2.5.1/`.

## 3. Problem, precisely

Three sites in `scripts/workflow_state.py` (the module `migration/overlays/2.5.0/payload/scripts/workflow_state.py`
also carries, unchanged since `2.4.0` introduced it) all key off one pair of
constants:

```python
_CHECKPOINT_ANCHOR_RE = re.compile(r"<!--\s*(/?)CP(\d+)\s*-->")
_ANCHOR_COMPATIBLE_CHECKPOINT_ID_RE = re.compile(r"^CP\d+\Z")
```

- `checkpoint_id_supports_anchor(checkpoint_id)` -- the single function both
  call sites below actually call. It is, by its own docstring, meant to be
  "the single place that fact is checked" (`IMPL2-R1`'s own comment). It
  already **is** the single choke point; this milestone changes what it
  matches, not how many places check it.
- `request_plan_amendment`'s own checkpoint-id-shape precondition
  (`IMPL2-R1`, `~line 11059`): loads the work item's current registry and
  raises `AmendmentCheckpointIdShapeError`, naming every id
  `checkpoint_id_supports_anchor` rejects, **before superseding
  `plan_approval`** -- this is the exact call site `workflow-controller-generation-1`
  hits today.
- `validate_post_anchor_coverage` (`~line 3620`): the post-side check
  `apply_plan_approval` runs before computing any reconciliation outcome.
  For every checkpoint id in the *amended* registry, it raises the same
  `AmendmentCheckpointIdShapeError` (`IMPL3-O1`) if the id is anchor-
  incompatible, and `AmendmentAnchorCoverageError` if it lacks a
  well-formed anchor pair. Both call sites already resolve to the identical
  `checkpoint_id_supports_anchor` predicate -- so the planning objective
  "make amendment anchor parsing and `validate_post_anchor_coverage` use
  the same grammar" is **already structurally true** in `2.5.0`; the defect
  is that the one grammar both consult is narrower than it needs to be, not
  that there are two divergent grammars to reconcile.

`_CHECKPOINT_ANCHOR_RE`'s own capture group 2 (`\d+`) is what
`parse_checkpoint_anchor_spans` re-assembles into `"CP" + match.group(2)`
to key its span map -- so the anchor **tag** grammar and the anchor
**shape** grammar must change together, or a widened shape check would let
an id like `CP4B` past `request_plan_amendment`'s precondition only to fail,
unactionably, at `validate_post_anchor_coverage` two review rounds later,
because no anchor-comment tag for id `CP4B` could ever be recognized. This is exactly the
failure mode `IMPL2-R1`'s own comment already reasons about for the
`CP<digits>`-vs-`WF4a-i` case; the fix must not reintroduce the same class
of gap one level in.

**What checkpoint ids have actually been legal, historically.** `D-Registry`
(`docs/ai-workflow/WORKFLOW_V2_PLAN.md`) has never constrained a registry
checkpoint id's shape beyond "a string" -- confirmed directly against
`workflow-v2-1-core-registry.json`'s own 17 real ids (`WF0`, `WF1a`,
`WF4a-i`, `WF-Activate`, ... -- none `CP<digits>`-shaped) and against
`generate_registry`/`validate_registry_topological_order`, neither of which
imposes a shape rule. The `CP<digits>`-only anchor grammar was `2.4.0`'s
own, deliberately narrow, addition for one purpose (pairing anchor comments
in a plan document with the registry rows they describe) and was never
meant to be, and never documented as, a constraint on what a checkpoint id
may be in general. `workflow-controller-generation-1`'s `CP4B`/`CP6B`
convention -- an inserted checkpoint between two numbered ones, lettered
rather than renumbering every id after it -- is exactly the kind of
pre-`2.4.0` id shape `D-Registry`'s own unconstrained format always
permitted and that the anchor mechanism's narrower grammar accidentally
started refusing outright, rather than merely declining to anchor-annotate.

## 4. Design decision -- `D-Checkpoint-Id-Anchor-Grammar-Widening`

**Widen the anchor-compatible grammar to `CP<digits>` optionally followed by
exactly one uppercase letter**, and widen the anchor **tag** grammar
identically, so the two never diverge:

```python
_CHECKPOINT_ANCHOR_RE = re.compile(r"<!--\s*(/?)CP(\d+[A-Z]?)\s*-->")
_ANCHOR_COMPATIBLE_CHECKPOINT_ID_RE = re.compile(r"^CP\d+[A-Z]?\Z")
```

`parse_checkpoint_anchor_spans`'s existing `checkpoint_id = "CP" +
match.group(2)` line is unchanged -- group 2 now captures `"4B"` for
`CP4B` exactly as it already captures `"1"` for `CP1`, so the rest of the
paired-anchor/reconciliation machinery (`checkpoint_content_hash`,
`reconcile_checkpoints_after_amendment`, `select_next_checkpoint`, ...)
needs no change at all: it already treats a checkpoint id as an opaque
string key everywhere except these two regexes.

**Scope of the widening, and why it stops exactly here (narrowness is a
requirement, not an accident):**

- **Exactly one uppercase letter, never more, never lowercase, never
  digit-after-letter.** The only evidence this milestone has for a
  legitimate pre-`2.4.0` shape beyond bare digits is the user-supplied,
  concrete example set -- `CP1 CP2 CP3 CP4 CP4B CP5 CP6 CP6B CP7 CP8 CP9`
  -- all single, uppercase, trailing letters, the conventional shape for
  "a checkpoint inserted between `CP4` and `CP5` without renumbering
  everything after it." Widening further (multi-letter suffixes,
  lowercase, a letter followed by more digits, a letter before the
  digits) has no supporting evidence and would widen the anchor grammar's
  attack surface -- e.g. a stray, accidental `<!-- CPabc -->` in prose
  currently parses as *no* anchor tag at all (safe, `_CHECKPOINT_ANCHOR_RE`
  simply does not match it); the narrower widening here keeps that
  property for every shape but the one evidenced one.
- **`WF4a-i`, and every other non-`CP`-prefixed id, is still refused,
  unchanged.** `^CP\d+[A-Z]?\Z` does not match `WF4a-i` (wrong prefix) any
  more than `^CP\d+\Z` did. `TestCheckpointIdSupportsAnchor.test_non_cp_digits_shape_is_unsupported`
  (`scripts/workflow_state_test.py`) pins this today and continues to pass
  unmodified -- this milestone adds tests, it does not touch that one,
  which is the regression guarantee the "prove numeric-only IDs remain
  unchanged" planning objective asks for at the level of an existing,
  already-reviewed fixture.
- **The general registry format is untouched.** `generate_registry`,
  `validate_registry_topological_order`, `write_registry_and_mapping`,
  `route_work_item` -- nothing about how a checkpoint id is created,
  stored, or reused changes. Only the two constants above, the one
  function they back (`checkpoint_id_supports_anchor`), and the
  documentation describing them change. This is deliberately the smallest
  change that closes the reported defect.

**Every normative document that states the grammar's shape must say the
same widened shape, or the documentation and the code it describes diverge
the moment this ships** -- the "make `/request-plan-amendment` accept...`
planning objective is a behavior requirement, but a stale doc describing
the old, narrower shape is itself a defect this milestone must not
introduce. Sites (all inside `migration/overlays/2.5.1/payload/`, mirroring
each unchanged from `2.5.0`'s own payload except where the grammar's shape
is stated):

- `scripts/workflow_state.py` -- the two regex constants above, plus every
  docstring/comment/exception message that spells out `'CP<digits>'` as
  prose (`checkpoint_id_supports_anchor`'s own docstring,
  `parse_checkpoint_anchor_spans`'s module-level comment block,
  `validate_post_anchor_coverage`'s docstring and its own
  `AmendmentCheckpointIdShapeError` message text, `request_plan_amendment`'s
  docstring and its own `AmendmentCheckpointIdShapeError` message text).
  All read `'CP<digits>'` today; all become `'CP<digits>[A-Z]?'` (or
  equivalent prose, "CP followed by digits and an optional single
  uppercase letter") together, in the same checkpoint, so no comment is
  ever momentarily stale mid-review.
- `docs/ai-workflow/WORKFLOW_V2_PLAN.md`'s `D-Plan-Amendment-4` section --
  its own prose description of the anchor grammar and the shape
  precondition.
- `docs/ai-workflow/MILESTONE_WORKFLOW.md` (two sites: the
  `request_plan_amendment` entry-condition description, and the
  post-anchor-coverage description under `AMENDING_PLAN`/plan-approval).
- `docs/ai-workflow/WORKFLOW_V2_1_OPERATOR_REFERENCE.md` (three sites,
  mirroring `MILESTONE_WORKFLOW.md`'s two plus `/request-plan-amendment`'s
  own operator-reference entry).
- `.claude/commands/request-plan-amendment.md` -- the command's own
  documented precondition and anchor-tag format.

**Non-matching-placeholder convention, mandatory for every one of these
edits (`LOCAL_MODEL_PLAN_REVIEW` round 1, Important 1).** Every site above
already illustrates the anchor-comment grammar using a non-matching
placeholder in the id position -- `CPn` or `CP<n>` -- rather than an
anchor-shaped HTML comment naming a concrete, letter-suffixed id; that
convention is what keeps prose *about* the grammar from becoming a live,
parseable anchor tag once this milestone's own widened grammar ships
(`CP<n>`/`CPn` never matches `^CP\d+[A-Z]?\Z`, unlike a concrete example
id). CP2 must preserve that convention at every one of the sites above and
must not introduce a single literal, concrete, anchor-shaped tag naming a
real letter-suffixed id into any of them while illustrating the widened
shape -- an example needs only a placeholder id or a prose description
(naming the id without ever writing the opening/closing comment delimiters
around it), never a real tag. This is the same defect this very revision
just corrected in this plan document's own §3 (Important 1, below); CP2's
own SELF_REVIEWING_IMPLEMENTATION must confirm, for each site it touches,
that no literal matchable anchor tag was introduced.

**What does *not* need to change.** `docs/ai-workflow/REVIEW_PROTOCOL.md`,
`docs/ai-workflow/PLAN_REVIEW_WORKFLOW.md`, and every other command file
this milestone's own `grep` sweep (§6) found with no `CP<digits>` mention
are left untouched -- confirmed absent from the site list above, not merely
unmentioned.

## 5. Checkpoint registry

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | Widen the anchor-compatible checkpoint-id grammar and its tests | - | 2 | 1 |
| CP2 | Author and compose the 2.5.1 release; sync normative docs to the widened grammar; derive and write README.md's final 2.5.1 Status row | CP1 | 2 | 1 |
| CP3 | Full regression, release-composition parity checks, and read-back verification of README.md's 2.5.1 Status row | CP2 | 1 | 1 |

<!-- CP1 -->
**CP1 -- Widen the anchor-compatible checkpoint-id grammar and its tests.**
In `migration/overlays/2.5.1/payload/scripts/workflow_state.py` (both
`2.4.0`'s and `2.5.0`'s overlays already carry their own full copy of this
file -- `migration/overlays/2.4.0/payload/scripts/workflow_state.py` and
`migration/overlays/2.5.0/payload/scripts/workflow_state.py` -- so this is
not the overlay mechanism's first-ever touch of it; it is this milestone's
own first-ever copy, layered the same way `2.5.0`'s own copy layered onto
`2.4.0`'s, correcting a wording slip from an earlier revision that claimed
neither prior overlay needed to touch it at all): apply §4's regex/docstring/message
changes. In the sibling
`workflow_state_test.py` overlay copy, add:

- A legacy-shaped fixture registry carrying exactly the user-supplied set
  (`CP1 CP2 CP3 CP4 CP4B CP5 CP6 CP6B CP7 CP8 CP9`), exercised against
  `checkpoint_id_supports_anchor` (every id in the set returns `True`),
  `parse_checkpoint_anchor_spans`/`checkpoint_content_hash` (a well-formed
  anchor-comment pair for id `CP4B` is recognized and hashed exactly as
  a numeric-only pair is), `validate_post_anchor_coverage` (the full set
  passes when every id has a well-formed anchor pair), and
  `request_plan_amendment`'s own shape precondition (a registry containing
  the full set no longer raises `AmendmentCheckpointIdShapeError` --
  mirrors the existing `test_all_cp_digit_checkpoint_ids_are_unaffected`
  fixture pattern, extended to include the lettered ids).
- Malformed-id fail-closed cases, each asserted `False` from
  `checkpoint_id_supports_anchor` and still refused by
  `request_plan_amendment`/`validate_post_anchor_coverage`: a lowercase
  suffix (`CP4b`), a two-letter suffix (`CP4BC`), a letter-before-digit
  shape (`CPB4`), a letter followed by another digit (`CP4B1`), the
  existing `WF4a-i` case (already pinned, re-asserted unchanged), and the
  existing trailing-newline case (`CP1\n`, already pinned, re-asserted
  unchanged).
- A regression assertion that every currently-passing
  `TestCheckpointIdSupportsAnchor`/`TestCheckpointAnchorSpans`/
  `TestValidatePostAnchorCoverage`/`TestRequestPlanAmendment`/
  `TestApplyPlanApprovalAmendmentBranch` numeric-only-id test in `2.5.0`'s
  own suite continues to pass byte-for-byte against the widened regex,
  proving the "numeric-only IDs remain unchanged" objective at the level
  of the existing, already-reviewed fixtures rather than only new ones.
- A tag/shape coupling-invariant test (`LOCAL_MODEL_PLAN_REVIEW` round 1,
  optional finding OPT-2), pinning §3's own hazard that the anchor **tag**
  grammar and the anchor **id-shape** grammar are two separate regex
  literals that must widen together: for an enumerated corpus of candidate
  ids (the legacy set, every malformed case above, plus at least `CP0`,
  `CP04A`, `CP12Z`, `CP999A`, `CP4-B`, `CP4_B`, `cp4`, `CPB`), assert
  `checkpoint_id_supports_anchor(candidate) == (candidate in
  parse_checkpoint_anchor_spans(f"<!-- {candidate} -->x<!-- /{candidate}
  -->", strict=False))` for every candidate. Cheap, pure, no fixture file
  needed.

Narrowest relevant check: run the new/modified test classes directly
against the overlay copy
(`PYTHONPATH=migration/overlays/2.5.1/payload/scripts python3 -m unittest
workflow_state_test.TestCheckpointIdSupportsAnchor
workflow_state_test.TestCheckpointAnchorSpans
workflow_state_test.TestValidatePostAnchorCoverage
workflow_state_test.TestRequestPlanAmendment
workflow_state_test.TestApplyPlanApprovalAmendmentBranch -v`), plus a full
`workflow_state_test.py` run under the same `PYTHONPATH` to confirm no
unrelated test regresses.
<!-- /CP1 -->

<!-- CP2 -->
**CP2 -- Author and compose the 2.5.1 release; sync normative docs to the
widened grammar; derive and write `README.md`'s final `2.5.1` Status row.**
`migration/overlays/2.5.1/classification.json`
(`base_workflow_version: "2.5.0"`, one `replaced` rule for
`scripts/workflow_state.py`, one `replaced` rule for
`scripts/workflow_state_test.py`, one `replaced` rule apiece for each
normative document §4 names). Apply §4's documentation-site edits inside
the overlay payload. Run `python3 tools/build_release.py --overlay
migration/overlays/2.5.1` to compose `distribution/workflow/2.5.1/` from
the `2.5.0` base plus this overlay, then `--check` to confirm byte-for-byte
reproduction. `tests/support.py` gains the `2.5.1` `CI_SUITES` entry
(counts pinned to what the composed overlay payload actually produces, the
same pattern every prior release's entry uses).
`migration/portability_exceptions.json` gains the required, empty
`by_version["2.5.1"]` entry (`tests/support.py`'s
`expected_portability_exceptions` subscripts `by_version[workflow_version]`
unguarded, so an absent key is a `KeyError`, not a pass -- this release
introduces no new portability exception, so the entry is empty, exactly
`2.5.0`'s own `CP9`-established precedent). This checkpoint deliberately
does **not** add a `2.5.1` section to `docs/MIGRATION.md`: that path is
unclassified (fail-closed) at both the plan and implementation stage for
this work item (a pre-existing gap in the inherited generic template,
already documented as out-of-scope in `TEST_RESULTS.md`), and `2.5.0`
itself added no `docs/MIGRATION.md` record either -- no checkpoint in this
milestone writes `docs/MIGRATION.md`, `docs/ARCHITECTURE.md`, `src/`,
`tools/`, or `pyproject.toml`, and none should attempt to; doing so would
raise `UnclassifiedPathError` mid-implementation rather than silently
succeeding.

**This checkpoint owns, and must complete, all of the machinery that
deterministically produces the final `2.5.1` README Status-row values, and
writes that row itself (`LOCAL_MODEL_PLAN_REVIEW` round 4, Required
correction 2-3; corrects round 3's own CP2-to-CP3 move, `MANUAL_EXTERNAL_
PLAN_REVIEW` round 3, Important 1, which handed CP3 a value CP3 could not
structurally produce -- CP2, not CP3, is the checkpoint whose own
completion can both obtain and write those final values).** Concretely,
this checkpoint adds, as **required** deliverables -- never discretionary
ones:

- `TestBootstrappedRepositorySatisfiesTheFrozenSuite251` in
  `tests/test_bootstrap_e2e.py`, mirroring the existing `...231`/`...240`/
  `...250` siblings exactly (a concrete `unittest.TestCase` subclass of
  `_BootstrappedRepositorySatisfiesTheFrozenSuiteAssertions` with
  `WORKFLOW_VERSION = "2.5.1"`). The mixin's own docstring is explicit that
  it is "never itself a `unittest.TestCase`... never discovered and run on
  its own" -- a `2.5.1` bootstrapped-repository pass count exists only if
  this concrete sibling exists; no other machinery in this repository
  produces one.
- the `2.5.1` pin `tests/test_internal_references.py`'s
  `TestReadmeStatusTableMatchesCiSuites` requires: a `_README_2_5_1_ROW_RE`
  pattern (mirroring `_README_2_5_0_ROW_RE`'s own shape, "same suite set as
  `2.5.0`, plus N new cases") and a `test_2_5_1_row_matches_ci_suites`
  case, so `README.md`'s new row is machine-checked against
  `CI_SUITES["2.5.1"]` from the moment this checkpoint writes it, the same
  protection `IMPL12-B1` added for every prior release's row rather than
  leaving this one unpinned.

This checkpoint then runs both of these test classes, and the full,
non-`--fast` `tests/run_all.py` run whose output they both consume, itself;
derives the authoritative `2.5.1` suite/test totals (`CI_SUITES["2.5.1"]`),
the "new cases" delta against `2.5.0`, and the bootstrapped-repository pass
count directly from that run's own output; and writes `README.md`'s
`## Status` table `2.5.1` row (~lines 14-16) plus the matching
re-derivation command pair in its rebuild-commands section (~lines 79-86,
mirroring the existing `2.4.0`/`2.5.0` pair's shape) with those values --
all within this checkpoint's own completion, never deferred to CP3.
`README.md` is excluded (not protected) at this item's own plan stage, so
this write never stales this item's own plan approval; the obligation is
recorded here precisely so it is not silently dropped the way an excluded,
unmentioned path otherwise would be.

If `tests/test_conformance_suite.py`'s existing `...250`-suffixed test
classes (`TestConformanceFixture250`, `TestBootstrappedTarget250`,
`TestPortabilityExceptions250RequiredEmptyEntry`) have a structural sibling
worth adding for `2.5.1` (mirroring how `2.5.0` added its own `...250`
siblings of `2.4.0`'s `...240` classes), add the `...251` siblings here; a
`2.5.1` patch release this narrow may not warrant every one of those three.
**This remaining discretion is scoped to these three
`tests/test_conformance_suite.py` classes only -- none of which any CP2 or
CP3 obligation in this plan consumes -- and never extends to
`TestBootstrappedRepositorySatisfiesTheFrozenSuite251` or
`TestReadmeStatusTableMatchesCiSuites`'s `2.5.1` pin above, both of which
are required, not discretionary.** SELF_REVIEWING_IMPLEMENTATION must
record, explicitly, which of these three siblings were added and which
were deliberately declined and why, rather than silently matching or
silently diverging from `2.5.0`'s own count.

Narrowest relevant check: build + `--check`; `TestBootstrappedRepository
SatisfiesTheFrozenSuite251` and `TestReadmeStatusTableMatchesCiSuites` run
directly, plus the full, non-`--fast` `tests/run_all.py` run their derived
README values depend on; plus whatever other new `2.5.1`
conformance-fixture test classes this checkpoint added, run directly.
<!-- /CP2 -->

<!-- CP3 -->
**CP3 -- Full regression, release-composition parity checks, and read-back
verification of `README.md`'s `2.5.1` Status row.** This checkpoint's own
deliverable *is* the full regression: `python3 tests/run_all.py` (both
`--fast` and the full, non-`--fast` run) must be green, and the
clean-target failure set (`migration/portability_exceptions.json`) must
equal the documented exceptions for `2.5.1` -- no more, no fewer, per
`CLAUDE.md`'s own "Before changing anything" contract. Confirms
`distribution/workflow/2.5.0/`'s own byte content is provably unchanged by
this milestone (`git diff <base_commit> -- distribution/workflow/2.5.0/`
empty) as the final, mechanical proof of §2's "2.5.0 is never edited"
non-goal, alongside re-running `tools/build_release.py --overlay
migration/overlays/2.5.1 --check` one more time against the final tree.

`README.md`'s `2.5.1` release-inventory row is CP2's own deliverable, not
this checkpoint's (`LOCAL_MODEL_PLAN_REVIEW` round 4, Required correction
2-3; corrects round 3's own CP2-to-CP3 move, `MANUAL_EXTERNAL_PLAN_REVIEW`
round 3, Important 1, which had handed CP3 a value it could not
structurally produce -- §5/CP2 above now owns both deriving and writing the
row). This checkpoint's only obligation toward that row is **read-back
verification, never authorship**: it confirms the `2.5.1` row CP2 already
wrote in the `## Status` table (~lines 14-16) has suite/test counts equal
to `CI_SUITES["2.5.1"]` and a bootstrapped-repository count equal to
`TestBootstrappedRepositorySatisfiesTheFrozenSuite251`'s own pass total --
both checked against *this checkpoint's own* full, non-`--fast`
`tests/run_all.py` run immediately above, an independent re-run of the same
regression CP2 already ran, not a second derivation from anything else.
This checkpoint must not write, re-pin, or otherwise edit `README.md` or
any other implementation artifact CP2 already produced; if the read-back
disagrees with what CP2 wrote, that disagreement is a defect for CP2 to
fix, never something this checkpoint papers over by re-deriving or
rewriting the row itself.
<!-- /CP3 -->

## 6. Requirements traceability

| id | description | checkpoints |
| --- | --- | --- |
| REQ-1 | The plan-amendment anchor-compatibility grammar accepts legacy letter-suffixed checkpoint ids (the `CP<digits>[A-Z]?` shape, e.g. `CP4B`/`CP6B`) instead of rejecting them. | CP1 |
| REQ-2 | `request_plan_amendment`'s early shape precondition and `validate_post_anchor_coverage`'s post-side check consult the identical grammar (`checkpoint_id_supports_anchor` / `_ANCHOR_COMPATIBLE_CHECKPOINT_ID_RE`), never a second, independently-maintained copy. | CP1 |
| REQ-3 | Purely numeric `CP<digits>` checkpoint ids are provably unaffected by the widening (existing behavior preserved bit-for-bit). | CP1 |
| REQ-4 | Malformed ids (lowercase letter suffix, multi-letter suffix, letter-before-digit, non-`CP`-prefixed ids such as `WF4a-i`, trailing newline, etc.) still fail closed after the widening. | CP1 |
| REQ-5 | `distribution/workflow/2.5.0/` stays byte-for-byte immutable; the fix ships only as a new authored `distribution/workflow/2.5.1/` release, composed from the `2.5.0` base plus a narrowly-scoped overlay, and `tools/build_release.py --overlay migration/overlays/2.5.1 --check` reproduces it exactly. | CP2 |
| REQ-6 | Every normative document that describes the anchor-compatibility grammar's shape (`WORKFLOW_V2_PLAN.md`'s `D-Plan-Amendment-4`, `MILESTONE_WORKFLOW.md`, `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, `request-plan-amendment.md`) is updated in the `2.5.1` overlay payload to state the widened grammar, so no normative document and the code it describes diverge, and every such update continues to illustrate the grammar with a non-matching placeholder id (`CPn`/`CP<n>`) rather than a concrete, anchor-shaped tag. | CP2 |
| REQ-7 | The full repository regression suite (`tests/run_all.py`) is green for `2.5.1` with no new or widened portability exceptions beyond the required empty `by_version['2.5.1']` entry, and no unrelated defect or `2.6` work is bundled into this milestone. | CP3 |

## 7. `SELF_REVIEWING_PLAN`

- **Missing requirements/migration risk/usability gaps.** Checked whether
  the widening should also cover the `2.3.1`/`2.4.0` **fixture** trees
  under `distribution/workflow/{2.3.1,2.4.0}/payload/scripts/`: no -- both
  are frozen (`2.3.1`) or already-superseded base content (`2.4.0`, whose
  own `_CHECKPOINT_ANCHOR_RE` copy is `2.4.0`'s own already-shipped,
  reviewed content and out of this milestone's declared deliverable tree,
  §4's site list). Checked whether `parse_checkpoint_anchor_spans`'s
  malformed-tag handling needs any change for the widened capture group --
  no, `\d+[A-Z]?` introduces no new *algorithmic* failure mode in the
  balanced-tag matcher itself, since the widening only changes which
  strings the *id* portion of a tag matches, never the tag delimiter syntax
  (`<!--`/`-->`/`/`) the balancing algorithm actually parses. It does,
  however, change which strings *are a tag at all*: a string that was
  previously inert prose under `2.5.0`'s narrower grammar (a lettered id
  such as `CP4B` inside a literal `<!-- ... -->` comment) becomes a live,
  parseable anchor once this milestone's grammar ships, so any *document*,
  not the matcher, that already contains such a string can newly raise
  where it previously parsed clean -- this plan document's own §3 illustrated
  exactly that hazard in an earlier revision and was corrected precisely
  because of it (`LOCAL_MODEL_PLAN_REVIEW` round 1, Important 1); the
  documents in this milestone's own site list (§4) -- `WORKFLOW_V2_PLAN.md`'s
  `D-Plan-Amendment-4`, `MILESTONE_WORKFLOW.md`,
  `WORKFLOW_V2_1_OPERATOR_REFERENCE.md`, and `request-plan-amendment.md` --
  are the ones that could carry this exposure if the non-matching-placeholder
  convention were ever dropped from them; today none of the five §4 sites
  (including `scripts/workflow_state.py` itself) carries a concrete,
  letter-suffixed anchor-shaped example, so this is a forward-looking risk,
  not a present one, and §4's non-matching-placeholder mandate is what keeps
  every one of them, and every future document like them, on the inert side
  of that line. No migration
  risk to any already-committed `WORKFLOW_STATE.json`: this change touches
  no persisted vocabulary (no new phase, no new ledger key, no
  `governing_workflow_version` bump) -- `CLAUDE.md`'s "Downgrade posture"
  paragraph needs no `2.5.1` addition, confirmed by the absence of any new
  persisted phase/status/ledger-key introduced here (contrast `2.4.0`'s
  `NEEDS_REVALIDATION`/`SUPERSEDED` and `2.5.0`'s
  `LOCAL_MODEL_IMPLEMENTATION_REVIEW` ledger, both genuinely new
  vocabulary; this milestone introduces none).
- **Unnecessary complexity.** Considered widening `checkpoint_id_supports_anchor`
  to accept an arbitrary `[A-Za-z0-9-]+` suffix (maximum future-proofing)
  and rejected it (§4's own scoping argument): no evidence supports it, and
  every unit of extra grammar surface is extra surface a malformed or
  accidental anchor-like HTML comment in prose could newly satisfy.
  Considered a three-checkpoint split as possibly one checkpoint too many
  for a two-regex fix, and kept it anyway: CP1 (code+tests) and CP2
  (release composition + doc sync) are genuinely separable review units
  with different narrowest-check shapes, and CP3's full-regression
  obligation mirrors every prior authored release's own final checkpoint
  (`2.4.0`'s and `2.5.0`'s own precedent) rather than folding a
  multi-minute full-suite run into CP2's own narrower build/check
  iteration loop.
- **Missing tests.** §5/CP1 above already states the four test additions
  (legacy-shaped fixture, malformed-id fail-closed cases, unaffected-
  existing-fixture regression, tag-parsing/hash/coverage integration for
  the lettered shape) that this plan's own REQ-1 through REQ-4 require;
  none of the four is deferred to CP2/CP3.

## 8. `docs/TECHNICAL_DECISIONS.md` cross-check

Read in full. This milestone touches none of its ten open decision rows
(Gradle module split, Room schema, progression formulas, navigation
structure, backup location, notification-permission behavior, cross-day
workouts, substitutions, manual corrections, UI design system) -- all
product/toolchain decisions for a RepFlow-facing codebase this repository
does not contain. No row is silently finalized by this work.
