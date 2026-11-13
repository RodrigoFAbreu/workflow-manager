# Workflow Manager: The Stale User Pages Are Re-Checked And Two Wording Points Are Exact (Revision 3)

`work_item_id: docs-restamp` -- `governing_workflow_version: "2.2"`

**Deliverable:** every stamped user page the first re-check left alone says
only what is true of Workflow Manager 1.18.1 and Workflow 2.29.3, and its
`Last checked with:` stamp says so; a page that was not re-checked keeps its
stamp and the record says why. `docs/release-history.md` row 1.14.6 describes
a null and an empty recorded version separately. Roadmap row 41 (added by
this item, Current now, Done at acceptance) is this item (issue #156).

**Work item type:** `process`. **Base commit:** `bfd255f`
(`bfd255fa2aee3e1558ce6e2ffda5ddca24b2c842`, tip of `main`; Manager 1.18.1,
Workflow 2.29.3 installed, automatic gates). **Branch:**
`milestone/docs-restamp`. **Release:** a `docs:` change **releases nothing**
(`docs/RELEASING.md`; `python3 tools/release/release.py check-title` on the
pull request title `docs: re-check the remaining user pages against Manager
1.18.1 and Workflow 2.29.3` must answer release impact none). No release
checkpoint. No source, test, checker, CI, installed-Workflow or
`tests/parallel/resources.json` change. One mechanism: *a page's stamp moves
only because the page was re-checked*. Two checkpoints, one review surface
(docs pages). The plan is far under 300 lines, so no split is needed.

## 1. What the issue asks, and what main already has

1. **Six stamped pages unchecked, one unstamped.** At the base the stamps
   read: `docs/README.md`, `docs/exit-codes.md`, `docs/common-problems.md`
   Manager 1.8.0, Workflow 2.12.0; `docs/glossary.md` 1.5.0, 2.9.0;
   `docs/release-metadata.md` 1.12.0, 2.12.0; `docs/retention.md` 1.13.2,
   2.22.0. The project `README.md` (a user page the checker covers) reads
   1.8.0, 2.12.0 as well: the issue's list says "docs/README.md" only, but the
   goal is every stamped user page, so the project `README.md` is **added**
   and handled like the others (drop it from CP2 if the owner objects; nothing
   else depends on it).
2. **Row 1.14.6 of `docs/release-history.md`** says a missing or empty
   recorded version is named "in words ... instead of `None` or a blank".
   Source truth (`record_head` in `src/workflow_manager/install.py`,
   `_directory_step` in `src/workflow_manager/advice.py`): a null record
   reads `no workflow_version recorded`; an empty one is shown quoted as
   `''`. The row describes the two separately.
3. **Roadmap rows 25 and 26 are already fixed on `main`.** Their status cells
   read `Done (accepted by policy; a `fix:` change, Manager 1.14.5)` and
   `... 1.14.6)`, like rows 15 and 22 to 24, and nothing in the file says
   "follows the merge" for them (verified at the base). No edit; flow 5 pins
   that.
4. **`docs/DOWNGRADE_POSTURE.md` has no stamp, and gets none.** The checker
   (`tools/check_docs.py`) applies its header rule to `USER_PAGES` only, and
   `DOWNGRADE_POSTURE.md` is not one (like `docs/ARCHITECTURE.md`,
   `docs/RELEASING.md` and `docs/MIGRATION.md`, the maintainer references,
   none stamped). Its header is a multi-line `> For:` block, which the
   checker's single-line header pattern would reject if the page were ever
   added to `USER_PAGES`. The checker would not reject a stamp added now, but
   nothing would ever check or age it, and the page governs releases up to
   2.12.0 only, so a stamp would claim a re-check of text that no later
   release changes. `docs/release-metadata.md` is the contrasting case, and
   is stamped for the opposite reason: it carries a stamp already and is
   re-checked here, although it is not in `USER_PAGES` either, so the checker
   says nothing about its header and flow 2 is the only check of its stamp.
   Adding a page to `USER_PAGES` (for either page) is a checker change, out
   of scope. `DOWNGRADE_POSTURE.md` is left byte for byte (flow 3). Open
   decision, section 8.

## 2. Phase 1 investigation (inside CP1 and CP2) and the stamp rule

For each page: read it against the current CLI (`workflow-manager --help` and
each command's `--help`), the sandbox output of each command it shows (offline
under `unshare -rn`, an empty release cache on disk), the source it describes
(`src/workflow_manager/` -- `cli.py`, `advice.py`, `install.py`, the
`retention*.py` modules, `compatibility.py`, `manifest` code) and the other
pages (links, terms, exit codes). Fix every statement no longer true. **A
stamp moves to `Workflow Manager 1.18.1, Workflow 2.29.3` only for a page
whose every statement was checked**; a statement that cannot be checked
offline is listed and its page keeps the old stamp (the plan expects none).
Order: `docs/exit-codes.md` and `docs/retention.md` first (the retention track
-- the policy file and `adopt-retention-policy`, the alert in `verify` and
`doctor`, the `retention-cleanup` preview and the confirmed run -- changed
them most), then the others.

The result is a table in `docs/ACTIVE_MILESTONE.md`: page | checked how |
text changed | stamp moved or kept, and why. `git diff --exit-code <base> --
<pages>` is the proof that a page not re-checked was not touched.

Leads from reading the pages before planning (to confirm or refute, not
findings): `docs/exit-codes.md` and `docs/retention.md` already describe the
newer commands under an old stamp, so they may need only the stamp plus a
check of each row against `retention_run.py`/`retention_cleanup.py`;
`docs/README.md`'s "I want to..." table has a row for the retention report but
none for adopting a policy or the cleanup; `docs/glossary.md`,
`docs/common-problems.md` and the project `README.md` name no retention term
or command; `docs/release-metadata.md` shows `min_manager_version` `1.13.0`
and its field list should be read against the manifest reader.

**Constraints on the edits.** Tests pin sentences of these pages
(`tests/test_docs.py`, `tests/test_operator_ux_docs.py`,
`tests/test_retention_run.py`' `TestDocsSayExitCodes`, `tests/test_retention_cleanup.py`,
`tests/test_release_metadata.py`): a pinned sentence is not reworded (no test
is edited); if one must change, the item stops and says so. No page names a
work item or checkpoint id (the checker fails it). A version shown as an
example of output is moved to what the command prints now (read from the
sandbox, never from memory). `docs/ROADMAP.md`'s stamp and the stamps of
`docs/install.md`, `docs/update.md`, `docs/verify.md`,
`docs/development.md` and `docs/release-history.md` were set by earlier
re-checks and are **not** touched here (not in the issue; the record states
this).

## 3. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The retention track's pages and the term pages | - | 2 | 1 |
| CP2 | The map, the metadata page, the history row and the roadmap | CP1 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the retention track's pages and the term pages

**Files:** `docs/exit-codes.md`, `docs/retention.md`,
`docs/common-problems.md`, `docs/glossary.md`.

`docs/exit-codes.md` first: every row (the retention rows included) against
the exit paths of the code and the sandbox; the preview and refusal rows of
`adopt-retention-policy` and `retention-cleanup` against `--help` and the
modules. Then `docs/retention.md` the same way (the policy file, the alert,
the preview, the confirmed run, the report text the last item corrected).
Then `docs/common-problems.md` (each error it quotes against the message
text in the code) and `docs/glossary.md` (each term against the current
behaviour; a retention term is added only if a page that uses it is unclear
without it). Stamps move per section 2. The findings are recorded in
`docs/ACTIVE_MILESTONE.md` after each page.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the map, the metadata page, the history row and the roadmap

**Files:** `README.md`, `docs/README.md`, `docs/release-metadata.md`,
`docs/release-history.md`, `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.

`docs/README.md`: the map rows and links against the current pages (a row for
adopting a retention policy and the cleanup if the retention page is the right
home). `docs/release-metadata.md`: its fields, defaults and refusals against
the manifest reader and `docs/RELEASING.md`. The project `README.md`: its
quick start against the sandbox output. `docs/release-history.md`: row 1.14.6
only, rewritten to say that a null record reads `no workflow_version
recorded` and an empty one is shown quoted as `''` (its stamp is not moved).
`docs/ROADMAP.md`: row 41 is Current when the plan starts and Done at
acceptance; rows 25 and 26 are verified, not edited. `docs/ACTIVE_MILESTONE.md`
holds the record. Both of these two files are excluded at both stages by
design and are not deliverables.
<!-- /CP2 -->

## 4. The gate and the declaration

* At each checkpoint: `python3 tools/check_docs.py` (exit 0) and `python3
  tests/run_all.py --select test_docs.py --select test_operator_ux_docs.py
  --select test_release_metadata.py --select test_retention_run.py --select
  test_retention_cleanup.py` (run `python3 tests/run_all.py --list` first if
  the release cache may lack a version). The full `python3 tests/run_all.py`
  runs at the implementation review and at acceptance, never while a file is
  being written, since the run makes `src/` and `tools/` read-only and the
  tree must not change under it. Hermetic: no network, no process left behind
  (sandbox commands run under `unshare -rn` and exit).
* The artifact declaration (`docs/ai-workflow/registry/docs-restamp-artifacts.json`)
  must classify every path this plan names at both stages and protect every
  deliverable. The generated template leaves the `docs/*.md` pages
  unclassified and excludes the project `README.md` at the implementation
  stage; SELF_REVIEWING_PLAN edits it before the first publish: the eight
  deliverable pages (the four of CP1, `README.md`, `docs/README.md`,
  `docs/release-metadata.md`, `docs/release-history.md`) are excluded at the
  plan stage and protected at the implementation stage; `docs/ROADMAP.md` and
  `docs/ACTIVE_MILESTONE.md` stay excluded at both. A page that ends up
  unchanged stays declared (a protected path need not change).
* The record (the per-page table in `docs/ACTIVE_MILESTONE.md`) is not bound
  by either stage's declaration: a later edit to it never stales the
  technical approval, and flows 2, 3 and 9 depend on it. The reviewer reads
  it at the reviewed head, and the functional review reads it in the
  checkout of the candidate.

## 5. Functional review

Every flow is an offline grep or diff in a checkout of the candidate (no
network, no `gh`, no installs); `BASE` is `bfd255fa2aee3e1558ce6e2ffda5ddca24b2c842`.
Exit codes are read with `; echo $?`, not through a pipe. Every pattern
below is written so it means the same raw or rendered: row anchors use
`grep -E` with a leading `^.` (the `.` matches the row's opening pipe, so no
cell contains a pipe character, which would split a table cell when rendered)
and `[.]`, alternatives use repeated `-e`, and no cell holds a shell
pipeline. Each command was run against
`BASE` and its output is the one stated.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `git diff --name-only BASE -- . ':!docs/ai-workflow' ':!docs/ACTIVE_MILESTONE.md'` | only the eight deliverable pages of section 4 and `docs/ROADMAP.md` (no `src/`, `tests/`, `tools/`, `.github/`, `.claude/`, `scripts/`, `.workflow-manager/` path, no `docs/DOWNGRADE_POSTURE.md`) |
| 2 | `grep -n "Last checked with" README.md docs/README.md docs/glossary.md docs/common-problems.md docs/exit-codes.md docs/retention.md docs/release-metadata.md` | seven lines, each ending `Workflow Manager 1.18.1, Workflow 2.29.3.` -- except a page the record lists as not re-checked, whose line equals its line at BASE (`git grep -n "Last checked with" BASE -- <page>`) |
| 3 | `git diff --exit-code BASE -- docs/DOWNGRADE_POSTURE.md docs/install.md docs/update.md docs/verify.md docs/development.md; echo $?`, then the same command on every page the record lists as not re-checked | `0` for each (the whole page unchanged), and `grep -c "Last checked with" docs/DOWNGRADE_POSTURE.md` prints `0` |
| 4 | `grep -n -E '^. 1[.]14[.]6 ' docs/release-history.md`, then `grep -n "no workflow_version recorded" src/workflow_manager/install.py src/workflow_manager/advice.py` | the row names `no workflow_version recorded` for a null record and `''` (quoted) for an empty one, in two separate statements, and no longer says "None or a blank" for both; the source lines print |
| 5 | `grep -c -E '^. 2[56] .*Manager 1[.]14[.][56]\)' docs/ROADMAP.md` and `grep -c -E '^. 2[56] .*follows the merge' docs/ROADMAP.md` | `2` and `0` (rows 25 and 26 carry concrete statuses, unedited) |
| 6 | `grep -n -E '^. 41 ' docs/ROADMAP.md` and `grep -c -E '^. 42 ' docs/ROADMAP.md` | row 41 present, its last cell `Current` (the functional review runs before `/accept-milestone`, which flips it to Done); `0` |
| 7 | `python3 tools/check_docs.py; echo $?` | no problem line; `0` |
| 8 | `PYTHONPATH=src python3 -m workflow_manager --help` (or the installed `workflow-manager --help`), then `grep -c -e adopt-retention-policy -e retention-cleanup docs/exit-codes.md docs/retention.md` | the help lists both commands; each page prints a count above `0` (true at `BASE` too: it shows the pages still name both commands, not that the stamp moved; that is flow 9's per-page row) |
| 9 | `git diff --stat BASE -- docs/exit-codes.md docs/retention.md` and read the record's table in `docs/ACTIVE_MILESTONE.md` | each page has its row: what was checked, what changed, stamp moved or kept and why; no page the table calls re-checked still holds a statement the table lists as unchecked |

## 6. Risks

* A page's stamp moves with an example that ages with the next release; the
  page says "the newest release" where it can, so the stamp carries the date.
* A pinned sentence needs a change: the item stops (no test edits are in
  scope) and the pinned sentence is reported for a follow-up.
* The review surface is the volume of reading, not a mechanism: every edit is
  a statement checked against a command, a source line or another page.

## 7. Self-review notes (SELF_REVIEWING_PLAN)

Checked: every checkpoint has its anchor pair; every backtick span in a Files
paragraph is a path; no page named here is a work-item id; row 41 follows row
40 in the file's style; the issue's three points are answered (1 by CP1 and
CP2, 2 by CP2, 3 verified already fixed); the root `README.md` addition is
stated as a decision.

## 8. Open decisions

* **For the owner, no blocker:** `docs/DOWNGRADE_POSTURE.md` stays unstamped
  (section 1.4); stamping it means adding it to the checker's pages and
  widening the header rule to its multi-line block, a checker change for a
  later item. `docs/TECHNICAL_DECISIONS.md` does not exist in this repository.
