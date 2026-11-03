# Active Milestone

## Milestone

`docs-freshness` -- complete, accepted by policy (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `5788222`, branch `milestone/docs-freshness`): roadmap row 27 (#153). A `docs:` pull request title (releases nothing).

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

## Next action

The next incomplete milestone in `docs/ROADMAP.md`, ready for `PLANNING`: `/milestone-plan`. Items 5 and 6 wait on the Controller; no other item is open.
