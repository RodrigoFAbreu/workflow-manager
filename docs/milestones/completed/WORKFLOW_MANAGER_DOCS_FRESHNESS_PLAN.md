# Workflow Manager: Each User Page Is Re-Checked Against The Current Release (Revision 1)

`work_item_id: docs-freshness` -- `governing_workflow_version: "2.2"`

**Deliverable:** the user pages named in section 2 say only what is true of
Workflow Manager 1.14.6 and Workflow 2.25.5, and their `Last checked with:`
stamp says so; `docs/ROADMAP.md` has its intro text, its `What's next` header
and its stamp in line with the table (roadmap row 27, issue #153).

**Work item type:** `process`. **Base commit:** `5788222`
(`578822299138a574178d899f108034bd5066df33`, tip of `main`; Workflow 2.25.5
installed, automatic gates). **Branch:** `milestone/docs-freshness`.
**Scope source:** `docs/ROADMAP.md` row 27 (added by this item, Current now,
Done at acceptance) and issue #153. **Release:** this is a `docs:` change and
**releases nothing**. The pull request title is `docs: re-check the install,
update, verify, development and release-history pages and the roadmap against
Manager 1.14.6 and Workflow 2.25.5` (`python3 tools/release/release.py
check-title` answers `valid title: docs, release impact none`). No code, test,
checker, installed-Workflow file or version changes. One mechanism: *each page
was re-checked against the current release and its stamp says so*. Three
checkpoints, one review surface (five pages and the roadmap). The plan is far
under 350 lines.

## 1. Sizing: the split made before the first review

Twelve `docs/*.md` pages open with `> For: ... Last checked with: ...`. Read
against the current CLI, the sandbox outputs and `src/workflow_manager/`, five
of them are certainly stale in their text, not only their stamp (the roadmap
is the sixth). The other six stamped pages were not checked in this item, so
their stamps **stay unchanged** (rule: a stamp moves only for a page that was
checked). So 12 stamped pages = 5 + the roadmap + 6 deferred. A seventh
deferred page, `docs/DOWNGRADE_POSTURE.md`, has a `> For:` block (lines 3 to
6) but **no** `Last checked with:` stamp, so it has nothing to keep or move.
The seven are the next item, which also decides which of them need a text
change: `docs/README.md`, `docs/glossary.md`, `docs/common-problems.md`,
`docs/exit-codes.md`, `docs/retention.md`, `docs/release-metadata.md`,
`docs/DOWNGRADE_POSTURE.md`. Keeping this item to six pages is the owner's
sizing guard (about 8 pages with a text change). Root `README.md` carries a
header too but is not a `docs/*.md` page: out of scope.

History pages: `docs/MIGRATION.md`, `docs/ARCHITECTURE.md` and
`docs/RELEASING.md` carry no `Last checked with:` stamp (searched with
`grep -n "Last checked" docs/*.md`); they are left unchanged.

## 2. The page table

`checked how`: R = read against the current text; S = every command the page
shows run in a sandbox (offline, empty release cache, or a copy of the cache
with `unshare -rn`), output compared; H = `--help` of the command compared;
C = source read. "Changed" is the plan's finding; implementation re-runs each
check and records the final answer in `docs/ACTIVE_MILESTONE.md`.

| page | checked how | text changed |
| --- | --- | --- |
| `docs/install.md` | R, S (`--version`, `releases`, `bootstrap`, `verify`, a non-repository target), H | yes |
| `docs/update.md` | R, S (`doctor`, `update`, `update --dry-run`, a non-managed target), H, C (`advice.py`) | yes |
| `docs/verify.md` | R, S (`status`, `verify`, `releases`), H | yes |
| `docs/development.md` | R, H (`tests/run_all.py --help`), C (`ARCHITECTURE.md` "Verification execution", `CLAUDE.md`) | yes |
| `docs/release-history.md` | R, `git tag` and `git log -1 --format=%ad <tag>` | yes |
| `docs/ROADMAP.md` | R, the Controller roadmap read for rows 5 and 6 | yes |
| `docs/README.md`, `docs/glossary.md`, `docs/common-problems.md`, `docs/exit-codes.md`, `docs/retention.md`, `docs/release-metadata.md`, `docs/DOWNGRADE_POSTURE.md` | not checked in this item | not decided; stamp unchanged (`docs/DOWNGRADE_POSTURE.md` has no stamp; the page is unchanged) |

## 3. What is stale, per page (the findings; the edits are CP1 to CP3)

**`docs/install.md`.** (a) "Step 2 prints `workflow-manager 1.5.0`" -- the
current number is `1.14.6`. (b) Step 3 says each line ends in `[cached]` or
`[not cached]` and that with no network only the pinned ones appear (both
stale whenever the cache holds a discovered release); a discovered release ends `[discovered, cached; no pin:
verified by github:...]` (sandbox). (c) Step 4 shows `bootstrapped workflow
2.12.0 (full) into ...`; a bare `bootstrap` now installs the newest release
(`2.25.5` in the sandbox), and the output ends with a `next:` line. (d) Step 5
shows `installation matches workflow 2.12.0` and omits the path prefix the
command prints (`repo: installation matches workflow 2.25.5`). The gate
paragraph (no `GATE_POLICY.json` on a fresh install, default `"2.2"`) is
confirmed true by the sandbox installation. Python 3.11 matches
`pyproject.toml`.

**`docs/update.md`.** (a) The "What you should see" block names
`updated ... to workflow 2.9.0` and `installation matches workflow 2.9.0`
(sandbox: `updated repo to workflow 2.25.5`, then `(no change)`). (b) The
long "Reading the report" bullets (Latest available, findings, recovery), the
exit statuses of `doctor` and `update --dry-run` and the null-record paragraph
are re-read against `advice.py`, `cli.py` and the sandbox report; a
statement that cannot be checked is reported in the record and the page keeps
its old stamp (section 6). `tests/test_docs.py`
`ReleaseAgnosticDocsTest` pins sentences of this page (the not-a-version
refusal, the null-record step and the upgrade-the-Manager remedy): they are
not reworded.

**`docs/verify.md`.** Step 1 shows `workflow 2.12.0 (full profile) -- clean`
and step 2 `installation matches workflow 2.12.0`: current `2.25.5` and the
`<path>:` prefix. The structure (`source:` line, `work in flight:`, `next:`)
is confirmed by the sandbox.

**`docs/development.md`.** (a) "(about 5 to 7 minutes)" is unverified
(no measured figure is recorded in `docs/`; `CLAUDE.md`'s `~5min` is an
excluded file, left as is on purpose): the duration is dropped and the sentence points at `docs/ARCHITECTURE.md`
("Verification execution") instead of inventing a number. (b) "primes the
release cache with every pinned version" -- every run primes every *tested*
version (the pins plus `tests/tested_releases.json`; `CLAUDE.md`). The pin
table is the pinned releases only and is correct (13 pins, 2.3.1 to 2.12.0,
the sandbox `releases --pinned-only` count).

**`docs/release-history.md`.** The table stops at 1.12.0 and lacks 1.8.0, so
it misses 1.8.0 and 1.13.0 to 1.14.6 (thirteen tags in total, from `git tag`: 1.8.0, five 1.13.x, seven 1.14.x).
Each missing row gets the tag's date and one plain-words line from the pull
request title; its "installs" column reads `2.3.1 and every later published
release` from 1.13.0 (the pins still end at 2.12.0). The second table gets one
row: Workflow 2.13.0 and later install with any Manager 1.13.0 or later (no
pin; `min_manager_version` decides). The page's other prose is accurate.

**`docs/ROADMAP.md`.** The stamp reads `1.13.2 / 2.18.4`. The intro of
`What's next` ("Items 1 to 4 and item 7 ... item 8 ... Items 5 and 6 wait on
the Controller") stops at row 8 while rows go to 27; "How to read" lacks the
status word **Current**. Rows 5 and 6 are still tracked in the Controller's
roadmap (C10 steps and C11 appear there; read, not copied), so they stay
`Waiting on ...` with the link. The `Done` and `Later` sections are history
and out of scope.

## 4. The edit rule

A statement is fixed only from something checked (a command output, a help
text, a source line, a tag, a roadmap row). A version shown as an *example* of
output is moved to what the same command prints now (`2.25.5` is the newest
release in the sandbox cache, `1.14.6` the Manager). No page names a work item
id or a checkpoint id (`tests/test_docs.py` fails them). `docs/ROADMAP.md` is
outside the link and command checks but stays well formed.

## 5. Checkpoints

| id | name | depends_on | complexity | session_target |
| --- | --- | --- | --- | --- |
| CP1 | The three command pages | - | 2 | 1 |
| CP2 | The release history and development pages | CP1 | 2 | 1 |
| CP3 | The roadmap and bookkeeping | CP2 | 1 | 1 |

<!-- CP1 -->
### CP1 -- the three command pages

**Files:** `docs/install.md`, `docs/update.md`, `docs/verify.md`.
Section 3 findings for the three pages, then each stamp becomes `Workflow
Manager 1.14.6, Workflow 2.25.5`. Every command the page shows is run in the
sandbox first; the answer per page is written into the record.
<!-- /CP1 -->

<!-- CP2 -->
### CP2 -- the release history and development pages

**Files:** `docs/release-history.md`, `docs/development.md`.
Section 3 findings for the two pages and their stamps. The new rows come from
`git tag` and `git log -1 --format=%ad`, not from memory.
<!-- /CP2 -->

<!-- CP3 -->
### CP3 -- the roadmap and bookkeeping

**Files:** `docs/ROADMAP.md`, `docs/ACTIVE_MILESTONE.md`.
`docs/ROADMAP.md` row 27 is Current when the plan starts and Done at
acceptance; this checkpoint also rewrites the intro and the `What's next`
header, adds the status word Current and moves the stamp. `docs/ACTIVE_MILESTONE.md`
records the milestone and the final page table. Both files stay excluded at
both stages by design (they are not deliverables).
<!-- /CP3 -->

## 6. The gate and the declaration

* The docs checker is `tools/check_docs.py`, run by `tests/test_docs.py`
  (`LiveRepositoryTest`) and `tests/test_operator_ux_docs.py`. At each
  checkpoint: `python3 tools/check_docs.py` (exit 0) and `python3
  tests/run_all.py --select test_docs.py --select test_operator_ux_docs.py`.
  The gate `python3 tests/run_all.py` runs at the implementation review and
  at acceptance, never while a file is being written. No test, checker or
  `tests/parallel/resources.json` is edited.
* The artifact declaration must classify every path above at both stages and
  protect the five pages as implementation-stage deliverables; the generated
  template leaves `docs/*.md` pages unclassified, so SELF_REVIEWING_PLAN
  added them to `docs/ai-workflow/registry/docs-freshness-artifacts.json`
  (plan stage: excluded; implementation stage: protected) before the first
  publish. `docs/ROADMAP.md` and `docs/ACTIVE_MILESTONE.md` stay excluded.
* A statement a page makes that cannot be checked offline is listed in the
  record and its page keeps the old stamp; the plan expects none, since every
  command runs in the sandbox and the rest is source or git reading.
* Hermetic: no network, no process left behind (sandbox commands run under
  `unshare -rn` and exit).

## 7. Functional review

Every flow runs offline in a sandbox: no network, no `gh`, no installs, no
sockets and a small tmpfs, **without a cached Workflow release** (`export
WORKFLOW_MANAGER_RELEASE_CACHE=$S/cache` on an empty directory, `S` a
scratch directory on disk). They are reader checks on the changed pages, run in
a checkout of the candidate. A flow's exit code is read with `; echo $?`, not
through a pipe.

| Flow | Do | Expect |
| --- | --- | --- |
| 1 | `python3 tools/check_docs.py; echo $?` | no output line other than the exit; `0` |
| 2 | `grep -n "Last checked with" docs/install.md docs/update.md docs/verify.md docs/development.md docs/release-history.md docs/ROADMAP.md` | six lines, each `Workflow Manager 1.14.6, Workflow 2.25.5.` |
| 3 | the same grep on `docs/README.md docs/glossary.md docs/common-problems.md docs/exit-codes.md docs/retention.md docs/release-metadata.md docs/DOWNGRADE_POSTURE.md` | six lines (`docs/DOWNGRADE_POSTURE.md` has no stamp and prints none), each exactly as at the base commit (stamp unchanged); and `git diff --exit-code 5788222 -- docs/README.md docs/glossary.md docs/common-problems.md docs/exit-codes.md docs/retention.md docs/release-metadata.md docs/DOWNGRADE_POSTURE.md; echo $?` prints `0` (the whole pages unchanged) |
| 4 | `workflow-manager --version`; `workflow-manager --pinned-only releases \| wc -l`; `workflow-manager --pinned-only releases \| sed -n '1p;$p'` | `workflow-manager 1.14.6`; `13`; first line starts `2.3.1`, last `2.12.0`, both end `[not cached]` (install.md step 3 and the pin table of development.md) |
| 5 | `git init plain; workflow-manager status plain; echo $?` then `workflow-manager verify plain; echo $?` and `workflow-manager update plain --dry-run; echo $?` | `not a managed repository (no .workflow-manager/installation.json)` and exit `0` for `status`; `error: plain is not a managed repository ...` and exit `2` for the other two, each followed by `next: ... bootstrap plain` (verify.md and update.md "If it fails") |
| 6 | `for t in $(git tag --list 'v1.*'); do grep -c "^| ${t#v} | " docs/release-history.md; done` (the match is anchored to the first column of the release table; the second table repeats Manager versions in its last column) | every count is `1` (every Manager tag has exactly one row) |
| 7 | `python3 tests/run_all.py --help; echo $?` and `grep -n "about 5 to 7" docs/development.md` | help prints, `0`; the grep prints nothing |
| 8 | `grep -n "^| 27 " docs/ROADMAP.md` and `grep -n "Items 1 to 4" docs/ROADMAP.md` | row 27 present, status `Current` (the functional review runs before `/accept-milestone`, which flips it to `Done`); the old intro sentence absent |

## 8. Risks

* A page example moved to `2.25.5` ages again with the next Workflow release;
  the page says "(or a newer number)" or "the newest release" where it can,
  so the stamp, not the example, carries the date.
* `docs/update.md`'s long bullets are the likeliest place for a statement the
  sandbox cannot reach (a `min_manager_version` case, a truncated listing);
  those are checked against the source text in `advice.py` and `cli.py`.
  Anything left unchecked is named in the record.
* The next item (the seven deferred pages) may find text changes; none is
  assumed here.

## 9. Open decisions

None for the owner. `docs/TECHNICAL_DECISIONS.md` does not exist in this
repository.
