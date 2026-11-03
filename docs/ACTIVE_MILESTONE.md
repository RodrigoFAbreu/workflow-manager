# Active Milestone

## Milestone

`docs-freshness` -- implementing (`governing_workflow_version: "2.2"`, `process`, plan revision 1, base `5788222`, branch `milestone/docs-freshness`): roadmap row 27 (#153). A `docs:` pull request title (releases nothing).

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
