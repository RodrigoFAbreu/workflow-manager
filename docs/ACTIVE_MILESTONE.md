# Active Milestone

## Milestone

`docs-freshness` -- awaiting functional review (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `5788222`, branch `milestone/docs-freshness`): roadmap row 27 (#153). A `docs:` pull request title (releases nothing).

Each user page that opens with a `Last checked with:` stamp is read against the current commands and source, every statement that is no longer true is fixed, and only then the stamp moves to Workflow Manager 1.14.6, Workflow 2.25.5. No code, checker or installed-Workflow change.

### CP1: the three command pages -- complete

- `docs/install.md`, `docs/update.md`, `docs/verify.md`: the example outputs and version numbers moved to what the commands print now, and the stamps (commit `f807044`).

### CP2: the release history and development pages -- complete

- `docs/release-history.md` (the missing Manager tags and the new compatibility row) and `docs/development.md` (the unverified duration dropped, "tested" versions), and their stamps (commit `f8b1453`).

### CP3: the roadmap and bookkeeping -- complete

- `docs/ROADMAP.md`: the stamp, the status word **Current**, the `What's next` intro and row 27's wording. This record.

### Final page table

| Page | Stamp |
| --- | --- |
| `docs/install.md`, `docs/update.md`, `docs/verify.md`, `docs/development.md`, `docs/release-history.md`, `docs/ROADMAP.md` | Workflow Manager 1.14.6, Workflow 2.25.5 |
| `docs/README.md`, `docs/glossary.md`, `docs/common-problems.md`, `docs/exit-codes.md`, `docs/retention.md`, `docs/release-metadata.md`, `docs/DOWNGRADE_POSTURE.md` | not checked here; unchanged |

`python3 tools/check_docs.py` exits 0.

### How each page was checked (re-run at self-review)

Sandbox: a copy of the release cache (`WORKFLOW_MANAGER_RELEASE_CACHE`), every command under `unshare -rn` (no network), installed Manager 1.14.6.

| Page | Checked | Answer |
| --- | --- | --- |
| `docs/install.md` | `--version`; `releases` (pinned `[cached]`, discovered `[discovered, cached; no pin: verified by github:RodrigoFAbreu/workflow]`, the `could not look for newer releases` warning); `bootstrap` on a fresh repository (`bootstrapped workflow 2.25.5 (full) into repo`, the file counts, a `next:` line naming `verify`; no `GATE_POLICY.json`, default `"2.2"`); `verify` (`repo: installation matches workflow 2.25.5`, exit 0); `bootstrap` of a directory with no `.git` | every statement true |
| `docs/update.md` | `doctor` and `update --dry-run` on a repository bootstrapped at 2.25.4 (the three version lines, `incomplete-inspection` titled `the releases in the range could not be enumerated` with exit 1, Recovery, `left alone:`); `update` (`updated old to workflow 2.25.5`, five `updated` lines, `next:` naming `verify`), a second `update` (`(no change)`); `status`/`verify`/`update --dry-run`/`doctor` on a non-managed repository (exit 0, 2, 2, 2, each with its `next:` line); the remaining report bullets read against `advice.py` and `cli.py` | every statement true |
| `docs/verify.md` | `status` (`workflow 2.25.5 (full profile) — clean`, `source:`, `work in flight: none`, `next:`), `verify` | every statement true |
| `docs/development.md` | `tests/run_all.py --help` (exit 0); `--pinned-only releases` (13 lines, 2.3.1 to 2.12.0, `[not cached]` on an empty cache) | every statement true |
| `docs/release-history.md` | `git tag --list 'v1.*'` and `git log -1 --format=%ad --date=short <tag>`: every tag has exactly one row with its date | every statement true |
| `docs/ROADMAP.md` | rows 1 to 27 read against `git tag` and the tag subjects | rows 15, 22, 23 and 24 said `a test: change, no release`; they are `fix:` changes released as Manager 1.14.1 to 1.14.4 (fixed at self-review) |

No statement on these pages needed the network to check, so none keeps its old stamp.

### Self-review

The full diff (`5788222..3280d60`) was read against plan sections 2 to 4. Two findings, both fixed in the self-review commit: the roadmap's four wrong statuses above (the stamp claims the page was checked), and this record lacked the per-page answers the plan asks for (sections 2 and 6). Both files are excluded from review at both stages. No test, checker, code or deferred page changed (`git diff --exit-code 5788222 -- <the seven deferred pages>` exits 0).

## Functional review checklist

Reader checks on the six pages and the roadmap. The gate is green: `python3 tests/run_all.py` at `3280d60`, 2329/2329 units, 15538 tests, exit 0. No file under `src`, `tests`, `tools`, `scripts` or `.claude`, and not `pyproject.toml`, has changed since (`git diff --name-only 3280d60 HEAD -- src tests tools scripts .claude pyproject.toml` is empty); the commits since are docs and workflow state. `python3 tools/check_docs.py` exits 0.

### Setup

1. Check out the head of `milestone/docs-freshness` (the checklist evidence commit). In the product clone run only read commands.
2. `workflow-manager --version` prints `workflow-manager 1.14.6`. Flows 4 and 5 need that entry point on `PATH`; if the sandbox has none, record them as blocked, not failed.
3. A scratch area on disk, not `/tmp`, with an empty release cache:
   `S=$(mktemp -d "$HOME/.cache/docs-ff-XXXXXX"); mkdir -p "$S/cache" "$S/work"; export WORKFLOW_MANAGER_RELEASE_CACHE="$S/cache" PYTHONDONTWRITEBYTECODE=1`
4. Run every flow with no network (`unshare -rn`, or the sandbox's own no-network setup). No flow calls `gh`, `claude`, `codex`, `ssh` or the network.
5. Flows 4 and 5 run in `$S/work`, never in the clone. The other flows only read.

### Test data

None. Flow 5 makes its own scratch repository (`plain`) in `$S/work`. The other flows read the clone's files, tags and history (base commit `5788222`).

### Flows

Read each exit code with `; echo $?`, not through a pipe.

1. In the clone: `python3 tools/check_docs.py; echo $?`. Expected: no output line, then `0`.
2. In the clone: `grep -n "Last checked with" docs/install.md docs/update.md docs/verify.md docs/development.md docs/release-history.md docs/ROADMAP.md`. Expected: six lines, each ending `Last checked with: Workflow Manager 1.14.6, Workflow 2.25.5.`
3. In the clone: `grep -n "Last checked with" docs/README.md docs/glossary.md docs/common-problems.md docs/exit-codes.md docs/retention.md docs/release-metadata.md`. Expected: six lines with their old stamps (not moved). Then `git diff --exit-code 5788222 -- docs/README.md docs/glossary.md docs/common-problems.md docs/exit-codes.md docs/retention.md docs/release-metadata.md docs/DOWNGRADE_POSTURE.md; echo $?`. Expected: `0`. (`docs/DOWNGRADE_POSTURE.md` has no stamp and prints no line.)
4. In `$S/work`: `workflow-manager --version`. Expected: `workflow-manager 1.14.6`. Then `workflow-manager --pinned-only releases | wc -l`. Expected: `13`. Then `workflow-manager --pinned-only releases | sed -n '1p;$p'`. Expected: a `2.3.1` line and a `2.12.0` line, both ending `[not cached]`.
5. In `$S/work`: `git init -q plain; workflow-manager status plain; echo $?`. Expected: `not a managed repository (no .workflow-manager/installation.json)`, a `next:` line naming `bootstrap plain`, then `0`. Then `workflow-manager verify plain; echo $?` and `workflow-manager update plain --dry-run; echo $?`. Expected for each: `error: plain is not a managed repository ...`, a `next:` line, then `2`.
6. In the clone: `for t in $(git tag --list 'v1.*'); do printf "%s:%s " "$t" "$(grep -c "^| ${t#v} | " docs/release-history.md)"; done; echo`. Expected: every count is `1`.
7. In the clone: `python3 tests/run_all.py --help; echo $?`. Expected: the help text, then `0`. Then `grep -n "about 5 to 7" docs/development.md; echo $?`. Expected: no line, then `1`. (Only `--help` is a flow; the gate is not run again.)
8. In the clone: `grep -n "releases nothing | Current |$" docs/ROADMAP.md`. Expected: line 49, row 27, status `Current`. Then `grep -n "Items 1 to 4 and items 7 to 26 are done" docs/ROADMAP.md`. Expected: line 17. Then `grep -c "Item 8 (the release-agnostic Manager) is done" docs/ROADMAP.md`. Expected: `0`.
9. Read `docs/install.md`, `docs/update.md` and `docs/verify.md` as a new user would. Every example output and version number should match what flows 4 and 5 print (the `bootstrap`, `update` and `doctor` examples are checked in the self-review record above, not here). Any statement that is not true of Workflow Manager 1.14.6 and Workflow 2.25.5 is a finding for `FUNCTIONAL_REVIEW.md`.

Expected overall: flows 1 to 8 as above and no finding from flow 9. A flow that is blocked (flow 4 or 5 without `workflow-manager` on `PATH`) is recorded as blocked.

### Known limits

- The seven deferred pages keep their old stamps and are for the next item; flow 3 checks that they are unchanged.
- These flows do not reach the network: discovery (`releases` without `--pinned-only`, its `could not look for newer releases` warning), `update` to a newer release, and `doctor`'s `incomplete-inspection` example. Those were checked at self-review (see "How each page was checked").
- Example version numbers age with the next Workflow release; the stamp carries the date.
- Flow 6 checks one row per Manager tag. The dates and row wording were checked at self-review against `git log` and the tag subjects.
